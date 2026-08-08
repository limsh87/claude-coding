#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-BDF 빌더 — build_bdf/ 조각들을 하나의 자립 실행 파일로 조립한다.

조립 결과는 그 파일 하나로 완결된다:
  Phase 0 게이트 → 수집 → 이벤트 → 백테스트 → 성과검증 → 강건성 → 해석표 → 최종판정
Colab / JupyterLab 어디서든 한 셀에 붙여넣거나 `python <파일>` 로 실행하면 동일하게 동작한다.

조립 순서는 파일명 정렬이 아니라 아래 ORDER 로 명시한다 — 의존 방향이 번호와 다른 곳이 있다.
"""
from __future__ import annotations
import os, sys, re, ast, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build_bdf")
OUT = os.path.join(ROOT, "strategies")

# 의존 순서 (앞이 뒤에 이름을 공급한다)
ORDER = [
    "00_header.py",          # 설정 상수 (모든 모듈이 참조)
    "01_bootstrap.py",       # 환경·의존성·numpy shim (서드파티 import 전에 shim)
    "02_kernel.py",          # LOG / PIPE / 예외
    "03_util.py",            # 원시 유틸 (atomic write, PIT, 통계)
    "04_vault.py",           # 구글드라이브 공용/전용 인덱스
    "05_http.py",            # HTTP 계층
    "06_compat.py",          # 버전 호환 (03/04/05 가 함수 내부에서 참조)
    "10_universe.py",        # 종목 마스터
    "11_price.py",           # 가격 · 시가총액 사다리
    "12_datagokr.py",        # 공공데이터 (KRX 대체 축)
    "13_ingest_research.py", # 한경 · 네이버 리서치
    "15_broker_map.py",      # ★ 14 보다 먼저 — normalize_broker 가 BrokerMap 에 위임한다
    "14_entity_research.py", # 리포트 원장 · 애널리스트 원장
    "16_flow.py",            # 거래원 / 투자자별 플로우
    "17_phase0.py",          # Phase 0 게이트
    "20_pit.py",             # PIT 유니버스
    "30_events.py",          # 매수성 이벤트
    "35_signal.py",          # 이중디민 · 통제회귀
    "41_backtest.py",        # 이벤트드리븐 엔진
    "45_eventstudy.py",      # CAR
    "50_stats.py",           # 부트스트랩 / PBO / DSR / 워크포워드 / 플라시보
    "55_hypotheses.py",      # H1~H5
    "60_report.py",          # 산출물
    "70_validate.py",        # 계약 / 스모크 / 리허설
    "90_main.py",            # 오케스트레이터
]

STRATEGIES = [
    dict(sid="ARC_BDF", fname="arc_bdf_report_broker_flow.py",
         name="리포트 × 자사 거래원 플로우",
         desc=("리서치의 가치는 발간 자체가 아니라 세일즈 채널을 통한 배포 강도에 있다. "
               "한국은 종목별 거래원(회원사) 매매동향이 상위 5개 창구 기준으로 일별 공개되는 "
               "드문 시장이고, 이 데이터는 배포 강도의 관측 가능한 그림자다. "
               "매수성 리포트를 낸 증권사의 창구에서 순매수가 동반되면 확증(롱), "
               "순매도가 나오면 물량 분배(배제)로 읽는다. "
               "거래원 과거 이력이 확보되지 않으면 Phase 0 게이트가 자동으로 "
               "ARC-BDF-PROXY(투자 주체 기반)로 전환하고, 그 사실을 모든 산출물에 명시한다.")),
]


def read(name: str) -> str:
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def strip_head(src: str, keep: bool) -> str:
    """헤더 조각이 아닌 파일에서 shebang / coding / __future__ 를 제거한다."""
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


def build_one(spec: dict, version: str) -> str:
    parts = []
    for i, fn in enumerate(ORDER):
        parts.append(strip_head(read(fn), keep=(i == 0)))
    blob = "\n".join(parts)
    blob = (blob.replace("@@STRATEGY_ID@@", spec["sid"])
                .replace("@@STRATEGY_NAME@@", spec["name"])
                .replace("@@STRATEGY_DESC@@", spec["desc"])
                .replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", spec["fname"]))
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)

    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:8]}")

    # 자유 변수 검사 — 조립 후 정의되지 않은 전역을 쓰면 실행 중간에 NameError 가 난다
    defined = set(dir(__builtins__) if not isinstance(__builtins__, dict) else __builtins__)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.alias):
            defined.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, (ast.comprehension,)):
            pass
        elif isinstance(node, ast.Global):
            defined.update(node.names)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
            and isinstance(n.ctx, ast.Load)}
    free = sorted(x for x in used - defined if not x.startswith("__"))
    if free:
        raise SystemExit(f"{os.path.basename(path)}: 정의되지 않은 이름 {free[:12]} "
                         f"— 조립 순서(ORDER)나 오타를 확인하세요.")

    # 금지 패턴 (자가검정 계약)
    banned = [
        (r"\.ptp\(", "ndarray.ptp() 는 numpy 2 에서 제거됨 → np.ptp(x) 사용"),
        (r"datetime64\[ns\]", "해상도 하드코딩 금지 → DT64 상수 사용"),
        # safe_read_html 내부의 유일한 호출(pd.read_html(**k))만 허용한다
        (r"pd\.read_html\((?!\*\*k\))", "pd.read_html 직접 호출 금지 → safe_read_html"),
        (r"Timestamp\.utcnow\(", "폐기 예고 API → now_kst() 사용"),
        (r"np\.array\([^)]*copy=False", "numpy 2 에서 ValueError → np.asarray 사용"),
        (r"include_groups\s*=", "pandas 3 에서 ValueError → gb_apply 사용"),
    ]
    # 주석·문서화 문자열은 검사 대상이 아니다(설명문에 패턴이 나오는 것은 정상이다)
    lines = src.split("\n")
    in_doc = False
    code_lines = []
    for i, ln in enumerate(lines):
        st = ln.strip()
        q3 = st.count('"""') + st.count("'''")
        if in_doc:
            code_lines.append((i + 1, ""))
            if q3 % 2 == 1:
                in_doc = False
            continue
        if st.startswith("#"):
            code_lines.append((i + 1, ""))
            continue
        if q3 % 2 == 1:
            in_doc = True
            code_lines.append((i + 1, ln.split('"""')[0].split("'''")[0]))
            continue
        code_lines.append((i + 1, re.sub(r"#.*$", "", ln)))
    for pat, why in banned:
        hits = [n for n, ln in code_lines if re.search(pat, ln)]
        if hits:
            raise SystemExit(f"{os.path.basename(path)}: 금지 패턴 {pat!r} @줄 {hits[:5]} — {why}")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("bdf.%Y%m%d.%H%M")
    made = []
    for spec in STRATEGIES:
        blob = build_one(spec, version)
        path = os.path.join(OUT, spec["fname"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(blob)
        check(path)
        n = blob.count("\n") + 1
        made.append((spec["fname"], n, len(blob)))
        print(f"  ✔ {spec['fname']:<44} {n:>6,}줄  {len(blob)/1024:>7.1f}KB")
    print(f"\n빌드 {version} — {len(made)}개 파일 → {OUT}")
    return made


if __name__ == "__main__":
    main()
