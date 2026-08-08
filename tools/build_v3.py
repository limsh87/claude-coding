#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCD v3 빌더 — 검증된 v2 코어(L0/L1) + v3 MICRO-FW 전략층을 자립 실행 파일로 조립한다.

경량화 원칙: 이 전략이 쓰지 않는 것은 아예 포함하지 않는다.
  제외: 센서팩 5종(C/N/D/X/P) · 정책 캘린더 · v2 축/스코어/백테스트/강건성/리포트/계약/리허설
  포함: 부트스트랩·커널·유틸·볼트(드라이브 캐시)·HTTP·유니버스·가격·DART·리서치·엔티티·PIT
        + v3 신규(시총 PIT · 관리종목/감사의견 · 마이크로 패널/센서 · 방화벽 · 백테스트 · 강건성)
"""
from __future__ import annotations
import os, sys, re, ast, datetime, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "build")
V3 = os.path.join(ROOT, "build_v3")
OUT = os.path.join(ROOT, "strategies")
TARGET = "tcd_v3_02_micro_firewall.py"

PARTS = [
    (V3, "00_header.py"),          # 사용자 설정 (KRX ID/PW · DART 키 · 드라이브 인덱스)
    (V2, "01_bootstrap.py"),       # 환경탐지 · 의존성 · 병렬 전략
    (V2, "02_kernel.py"),          # 로깅 · 스테이지 · I/O 원장 · 에러 국소화
    (V2, "03_util.py"),            # PIT 프레임 · 셀 정규화 · 병렬 · 통계
    (V2, "04_vault.py"),           # ★ 구글드라이브 공용/전용 인덱스 (append-only)
    (V2, "05_http.py"),            # 세션 · 인코딩 · 레이트리밋
    (V2, "10_ingest_universe.py"),  # FDR/KIND/pykrx/DART corpcode → 종목 마스터
    (V2, "11_ingest_price.py"),    # KRX 마켓플레이스 인증 → 가격 다중소스 폴백
    (V2, "12_ingest_dart_fin.py"),  # DART 재무 · 공시목록
    (V2, "13_ingest_research.py"),  # 한경컨센서스 · 네이버 리서치
    (V2, "14_entity_research.py"),  # 보고서↔애널리스트↔종목 원장
    (V2, "20_pit.py"),             # PIT 저장소 · 유니버스(C2)
    (V3, "15_ingest_mcap.py"),     # ★신규: 시가총액·상장주식수 PIT
    (V3, "16_ingest_watchlist.py"),  # ★신규: 관리종목·감사의견·거래정지 PIT
    (V3, "17_dart_budget.py"),   # ★신규: 런타임 예산 강제 + DART 수집 사다리
    (V3, "30_micro_panel.py"),     # L1 센서(§8) · 셀(C14) · 유니버스 게이트(§6)
    (V3, "35_firewall_score.py"),  # S1_FIREWALL(§7) · 거부권 · TP · 신호
    (V3, "41_backtest_micro.py"),  # 백테스트(§10)
    (V3, "50_robust_micro.py"),    # R0 · R2-M · R3 · R5-M · R9
    (V3, "60_report_micro.py"),    # 성과검증 · 해석표 · 진단카드
    (V3, "70_canary.py"),          # K1~K6
    (V3, "80_selftest_micro.py"),  # 계약검정 · 합성 스모크
    (V3, "90_main_micro.py"),      # 오케스트레이션
]

DROP_FUNCS = {                     # 코어에서 이 전략이 안 쓰는 함수 (경량화)
    "12_ingest_dart_fin.py": ["fetch_dart_employees"],
    "11_ingest_price.py": ["fetch_investor_flows"],
}


def _strip_top_level_funcs(src: str, names) -> str:
    """모듈 최상위 함수 정의만 안전하게 제거한다(AST 기준 — 정규식으로 자르지 않는다)."""
    if not names:
        return src
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    cut = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            cut.append((start, node.end_lineno))
    for start, end in sorted(cut, reverse=True):
        del lines[start:end]
    return "\n".join(lines)


def read(dirname: str, name: str, keep_header: bool) -> str:
    with open(os.path.join(dirname, name), encoding="utf-8") as f:
        src = f.read()
    src = _strip_top_level_funcs(src, DROP_FUNCS.get(name))
    if keep_header:
        return src
    out = []
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith("#!") or s.startswith("# -*- coding") or \
           s.startswith("from __future__ import"):
            continue
        out.append(ln)
    return "\n".join(out)


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)                      # ① 문법
    seen, dups = {}, []                                       # ② 최상위 이름 중복
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"최상위 이름 중복 → {dups[:8]}")
    try:                                                      # ③ 미정의 이름
        r = subprocess.run([sys.executable, "-m", "pyflakes", path],
                           capture_output=True, text=True, timeout=180)
        und = [l for l in (r.stdout or "").split("\n") if "undefined name" in l]
        if und:
            raise SystemExit("미정의 이름 발견:\n  " + "\n  ".join(und[:25]))
    except FileNotFoundError:
        print("  (pyflakes 미설치 — 미정의 이름 검사 생략)")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("v3.%Y%m%d.%H%M")
    blob = "\n".join(read(d, n, keep_header=(i == 0)) for i, (d, n) in enumerate(PARTS))
    blob = blob.replace("@@BUILD_VERSION@@", version).replace("@@FILENAME@@", TARGET)
    if "@@" in blob:
        left = sorted(set(re.findall(r"@@\w+@@", blob)))
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    path = os.path.join(OUT, TARGET)
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {TARGET}  {n:,}줄  {len(blob)/1024:.1f}KB   빌드 {version}")
    return path


if __name__ == "__main__":
    main()
