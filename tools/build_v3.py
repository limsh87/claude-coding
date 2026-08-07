#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCD v3 빌더 — 검증된 v2 코어(L0/L1 인프라) + v3 전략 스파인을 자립 실행 파일로 조립한다.

설계 결정: 수집·캐시·HTTP·PIT·백테스트 엔진은 이미 실전에서 다듬어진 v2 조각을 **그대로**
재사용하고, 전략 고유부(센서·TP·스코어·강건성·리포트·오케스트레이션)만 v3 로 새로 쓴다.
v2 의 축 기반 스코어링(40_score/50_robust/60_report/90_main)은 v3 스펙과 다르므로 포함하지
않는다 — 죽은 코드를 남기지 않기 위함이다(경량화 지시).
"""
from __future__ import annotations
import os, re, ast, sys, builtins, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B2, B3 = os.path.join(ROOT, "build"), os.path.join(ROOT, "build_v3")
OUT = os.path.join(ROOT, "strategies")

# (디렉터리, 파일명) — 조립 순서가 곧 실행 순서다. 모듈 레벨 부수효과가 있는 조각의
# 순서를 바꾸면 조용히 깨진다(예: KRX 자격증명 → pykrx import, KRX=KRXAuth(...) 인스턴스화).
ORDER = [
    (B3, "00_header.py"),          # 설정 (KRX/DART 키, 드라이브 경로, 전략 파라미터)
    (B2, "01_bootstrap.py"),       # 환경감지·의존성·시드 (KRX 자격증명 → os.environ)
    (B2, "02_kernel.py"),          # LOG / PIPE(스테이지·IO원장·한글진단)
    (B2, "03_util.py"),            # 날짜·해시·원자IO·레이트리미터·병렬·벡터화 통계
    (B2, "04_vault.py"),           # 구글드라이브 공용/전용 인덱스 (append-only)
    (B2, "05_http.py"),            # 세션·인코딩·차단감지
    (B3, "06_env.py"),             # 캐시루트 해석 + 런타임 예산
    (B2, "10_ingest_universe.py"), # FDR/KIND/pykrx/DART corpCode → 종목마스터
    (B2, "11_ingest_price.py"),    # KRX 마켓플레이스 + 4중 폴백 가격체인 + 수급
    (B2, "12_ingest_dart_fin.py"), # DART 재무·공시목록
    (B2, "13_ingest_research.py"), # 한경컨센서스 · 네이버리서치
    (B2, "14_entity_research.py"), # 리포트↔애널리스트 원장
    (B2, "20_pit.py"),             # PITStore · Universe
    (B3, "22_canary.py"),          # K1~K9
    (B3, "30_emp.py"),             # empSttus 확장 + C15 한계임금
    (B3, "31_policy.py"),          # 정책 캘린더 (R10)
    (B3, "32_sensors.py"),         # 패널조립 · CORE-D · EMP-LITE · U축 · U-MID
    (B3, "40_score.py"),           # TP(clip×clip) · 거부권 · Signal
    (B2, "41_backtest.py"),        # 백테스트 엔진 · 비용 · 성과지표
    (B3, "50_robust.py"),          # R0·R1·R2-N·R3·R5·R7·R8·R10
    (B3, "60_report.py"),          # 성과·해석·진단카드·원장지도
    (B3, "70_contracts.py"),       # 계약 자동검정
    (B2, "75_rehearsal.py"),       # 실경로 리허설 (+v3 훅)
    (B3, "80_selftest.py"),        # 합성 스모크
    (B3, "90_main.py"),            # 오케스트레이터 (마지막이어야 한다)
]

SPEC = dict(
    sid="TCD_V3_CORE_D_EMP_LITE",
    fname="tcd_v3_core_d_emp_lite.py",
    name="CORE-D + EMP-LITE (DART 직원현황 기반 한계임금 전환 코어)",
    bt_start="2016-08-01", bt_end="2026-07-31",
)

# 리허설 훅이 참조하는 등 '정의는 코어에 있고 호출은 가드 뒤'인 이름들.
KNOWN_OPTIONAL = {
    "build_nps_panel", "build_text_similarity", "fetch_customs_trade", "fetch_dart_documents",
    "fetch_nps_workplaces", "fetch_procurement", "resolve_nps_to_corp",
}


def read(d: str, name: str) -> str:
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def strip_header(src: str, keep: bool) -> str:
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


def assemble(version: str) -> str:
    parts = [strip_header(read(d, n), keep=(i == 0)) for i, (d, n) in enumerate(ORDER)]
    blob = "\n".join(parts)
    repl = {
        "@@STRATEGY_ID@@": SPEC["sid"], "@@STRATEGY_NAME@@": SPEC["name"],
        "@@BUILD_VERSION@@": version, "@@FILENAME@@": SPEC["fname"],
        "@@BT_START@@": SPEC["bt_start"], "@@BT_END@@": SPEC["bt_end"],
    }
    for k, v in repl.items():
        blob = blob.replace(k, v)
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)                       # ① 문법

    # ② 최상위 이름 중복 (조립 사고의 대표 증상)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"최상위 이름 중복 → {dups[:8]}")

    # ③ 미정의 이름 (오타·조각 누락을 실행 전에 잡는다)
    bound = set(dir(builtins))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            bound.update(n.names)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
            and isinstance(n.ctx, ast.Load)}
    missing = sorted(used - bound - KNOWN_OPTIONAL)
    if missing:
        raise SystemExit(f"미정의 이름 {len(missing)}개: {missing[:20]}")

    # ④ 스펙 §0 원칙의 소스 수준 확인 (주석이 아니라 코드로 지켜지는지)
    if "np.maximum(za, 0.0) * np.maximum(zb, 0.0)" not in src:
        raise SystemExit("원칙2 위반 — TP 가 clip(z,0)×clip(z,0) 형태가 아닙니다")
    if re.search(r"groupby\([^)]*\)\s*\.\s*apply\s*\(", src):
        raise SystemExit("원칙3 위반 — groupby(...).apply( 가 있습니다 (수십 배 느립니다)")
    if not re.search(r"direction\s*=\s*[\"']backward[\"']", src):
        raise SystemExit("원칙1 위반 — merge_asof(direction='backward') 가 보이지 않습니다")
    if "-1.0" not in src:
        raise SystemExit("원칙7 위반 — 상장폐지 -100% 처리가 보이지 않습니다")
    return


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("v3.%Y%m%d.%H%M")
    blob = assemble(version)
    path = os.path.join(OUT, SPEC["fname"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {SPEC['fname']:<38} {n:>6,}줄  {len(blob)/1024:>7.1f}KB")
    print(f"     조각 {len(ORDER)}개 (v2 코어 재사용 "
          f"{sum(1 for d, _ in ORDER if d == B2)}개 + v3 신규 "
          f"{sum(1 for d, _ in ORDER if d == B3)}개)")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
