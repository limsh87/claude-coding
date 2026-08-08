#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-NCQ 빌더 — TCD v2 의 검증된 코어 + ARC-NCQ 전용 모듈을 하나의 자립 실행 파일로 조립한다.

재사용 원칙:
  · build/ 의 코어(부트스트랩·커널·유틸·Vault·HTTP·유니버스·가격·리서치·엔티티·PIT)는
    **그대로** 가져다 쓴다. 이미 실전에서 깨진 곳을 다 고쳐 놓은 코드다.
  · 전략 고유 계층(유니버스 압축·이벤트 판정·텍스트·백테스트·강건성·리포트)만 새로 쓴다.
  · 공용 인덱스(_shared)를 TCD v2 와 공유하므로 캐시가 그대로 재활용된다.
"""
from __future__ import annotations
import os, re, ast, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "build")
NCQ = os.path.join(ROOT, "build_ncq")
OUT = os.path.join(ROOT, "strategies")

# (디렉터리, 파일명) 순서 = 조립 순서
PARTS = [
    (NCQ,  "ncq_00_header.py"),          # 설정·자격증명 (파일 최상단)
    (CORE, "01_bootstrap.py"),           # 환경감지·의존성·표준 임포트
    (CORE, "02_kernel.py"),              # LOG / PIPE / 에러 국소화 / I/O 원장
    (CORE, "03_util.py"),                # 날짜·해시·원자적IO·병렬·횡단면 통계
    (CORE, "04_vault.py"),               # 구글드라이브 공용/전용 인덱스 (절대 1원칙)
    (CORE, "05_http.py"),                # 세션·스로틀·인코딩 자동판별
    (CORE, "06_dartkey.py"),             # DART 키 풀 — 실시간 잔량·다중키 자동전환
    (CORE, "10_ingest_universe.py"),     # 종목 마스터 (FDR/KIND/DART/스냅샷)
    (CORE, "11_ingest_price.py"),        # 가격 폴백 체인
    (CORE, "13_ingest_research.py"),     # 한경컨센서스 / 네이버 리서치
    (CORE, "14_entity_research.py"),     # 증권사 정규화 · 애널리스트 원장 · 연결 감사
    (CORE, "20_pit.py"),                 # PIT 저장소 · Universe · 셀
    (NCQ,  "ncq_05_budget.py"),          # Phase 예산 · 열화 사다리 · 매니페스트
    (NCQ,  "ncq_08_sources.py"),         # KRX-free 소스 계층 (생존자편향·PIT 주식수)
    (NCQ,  "ncq_10_universe.py"),        # Phase 0
    (NCQ,  "ncq_20_index.py"),           # Phase 1
    (NCQ,  "ncq_30_coverage.py"),        # Phase 2
    (NCQ,  "ncq_40_text.py"),            # Phase 3·4·5
    (NCQ,  "ncq_50_backtest.py"),        # Phase 6
    (NCQ,  "ncq_60_robust.py"),          # 강건성 · 사전등록 검정 · 민감도
    (NCQ,  "ncq_70_report.py"),          # 리포팅 · 진단 9종 · 해석표 · 흐름지도
    (NCQ,  "ncq_80_verify.py"),          # 계약검정 · 카나리 · 리허설 · 스모크
    (NCQ,  "ncq_90_main.py"),            # 오케스트레이터
]

TARGET = "arc_ncq_v1_new_coverage_quality.py"

# 코어에서 가져오지만 이 전략이 쓰지 않는 최상위 이름 (중복 정의 검사에서 제외)
ALLOWED_DUPES: set = set()


def read(d: str, name: str) -> str:
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def strip_header(src: str, keep: bool) -> str:
    """헤더가 아닌 조각에서 shebang / coding / __future__ 제거 (조립 시 문법 오류가 된다)."""
    if keep:
        return src
    out = []
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith("#!") or s.startswith("# -*- coding") or \
           s.startswith("from __future__ import"):
            continue
        out.append(ln)
    return "\n".join(out)


def build(version: str) -> str:
    chunks = []
    for i, (d, fn) in enumerate(PARTS):
        src = read(d, fn)
        src = strip_header(src, keep=(i == 0))
        chunks.append(f"\n# {'=' * 92}\n# 조립 블록 {i:02d}: {fn}\n# {'=' * 92}\n")
        chunks.append(src)
    blob = "\n".join(chunks)
    blob = (blob.replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", TARGET))
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> dict:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)          # ① 문법
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen and node.name not in ALLOWED_DUPES:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:                                       # ② 최상위 중복 정의 (조립 사고의 대표 증상)
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:8]}")

    # ③ 첫 블록 이후에 import 문이 남아 있으면 조립이 깨진 것
    bad_imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.lineno > 400:
            nm = getattr(node, "module", None) or ",".join(a.name for a in node.names)
            bad_imports.append((nm, node.lineno))
    # ④ 정의 없이 호출되는 최상위 이름 대략 점검 (오탐이 많아 경고만)
    return {"lines": src.count("\n") + 1, "bytes": len(src), "defs": len(seen),
            "late_imports": bad_imports}


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("ncq1.%Y%m%d.%H%M")
    blob = build(version)
    path = os.path.join(OUT, TARGET)
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    info = check(path)
    print(f"  ✔ {TARGET}")
    print(f"    {info['lines']:,}줄 · {info['bytes']/1024:.1f}KB · 최상위 정의 {info['defs']}개")
    if info["late_imports"]:
        print(f"    ⚠ 늦은 import {len(info['late_imports'])}건: {info['late_imports'][:5]}")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
