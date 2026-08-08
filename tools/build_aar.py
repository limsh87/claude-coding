#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-AAR 빌더 — 조각 소스를 하나의 자립 실행 파일로 조립한다.

산출물은 파일 하나로 완결된다: 수집 → 정제 → 신호 → 백테스트 → 성과검증 →
가설검정 → 강건성 → 해석표 → 최종판정까지 그 파일 하나로 전부 수행된다.
"""
from __future__ import annotations
import ast
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build_aar")
OUT = os.path.join(ROOT, "strategies")

# 파일명 접두 숫자 = 계층 = 조립 순서.
ORDER = [
    "00_header.py",        # 설정 (키·경로·격자)
    "01_bootstrap.py",     # 환경·의존성·pandas 2/3 양립
    "02_kernel.py",        # 로깅·스테이지·I/O원장·진단
    "03_util.py",          # 유틸 + 수치커널(EB 축소, FE 흡수)
    "04_vault.py",         # 드라이브 캐시 3계층
    "05_http.py",          # HTTP + 응답 영속 캐시
    "06_quota.py",         # API 잔여 호출량 실시간 추적
    "07_stats.py",         # 통계 검증 커널
    "10_universe.py",      # marcap · PIT 유니버스 · 시총 · PIT저장소
    "11_price.py",         # 월간 패널 · 폐지 처리 · 벤치마크
    "12_dart_events.py",   # 실적발표월 · 공시건수
    "13_research.py",      # 한경 + 네이버 리포트 수집
    "14_ledger.py",        # 원장 · 애널리스트 · 인물추적 · Phase0
    "30_attention.py",     # 주의패널 → 축소 → 통제회귀 → VAS
    "31_drops.py",         # 커버리지 철회 인과분해
    "32_signal.py",        # AAR_pos/neg/total · 포트폴리오
    "40_backtest.py",      # 백테스트 엔진 · 비용
    "50_hypo.py",          # H1~H5 + BH-FDR
    "51_robust.py",        # 강건성 R1~R10
    "60_report.py",        # 리포트 · 최종판정
    "70_contracts.py",     # 계약 자동검정
    "80_selftest.py",      # 합성 스모크
    "90_main.py",          # 오케스트레이터
]

STRATEGY = dict(
    sid="ARC_AAR",
    fname="arc_aar_analyst_attention.py",
    name="애널리스트 주의 재배분 (양방향 현시선호 신호)",
    desc=("애널리스트가 '무엇을 말했는가'를 전혀 읽지 않는다. 대신 고정된 주의 예산을 "
          "어디에 재배분했는가만 본다. 매도의견이 사실상 0이고 목표주가가 제도적으로 "
          "상향 편향된 한국 시장에서, 표명된 의견을 읽는 모든 팩터는 검열된 분포 위에서 "
          "작동한다. 주의 배분은 검열되지 않는다. 특히 커버리지 철회를 '인사이동'과 "
          "'자발적 철회'로 인과 분해하면, 공매도 제약 아래 관측 가능한 사실상 유일한 "
          "음(−) 신호를 얻는다."),
)


def read(name: str) -> str:
    with open(os.path.join(BUILD, name), encoding="utf-8") as f:
        return f.read()


def strip_header(src: str, keep: bool) -> str:
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


def check(path: str) -> None:
    """문법 + 최상위 이름 중복 검사.

    ★ 함수/클래스뿐 아니라 **최상위 변수 중복도** 잡는다. 두 조각이 같은 전역 상수를
      정의하면 조용히 뒤엣것이 이기는데(예: 헤더의 TAX_SCHEDULE 을 백테스트 조각이
      다시 정의), 그건 설정이 무시되는 것이라 사용자가 절대 눈치채지 못한다."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    seen, dups = {}, []
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        for nm in names:
            if nm.startswith("_") and nm.isupper() is False and len(nm) <= 2:
                continue
            if nm in seen:
                dups.append((nm, seen[nm], node.lineno))
            seen[nm] = node.lineno
    # 재대입이 정당한 전역(런타임에 채워지는 핸들)은 예외로 둔다
    allow = {"VAULT", "PIT", "fdr", "yf", "smapi", "rapidfuzz_fuzz", "fitz", "RESULT"}
    dups = [d for d in dups if d[0] not in allow]
    if dups:
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:8]}")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("aar.%Y%m%d.%H%M")
    parts = []
    for i, fn in enumerate(ORDER):
        parts.append(strip_header(read(fn), keep=(i == 0)))
    blob = "\n".join(parts)
    blob = (blob.replace("@@STRATEGY_ID@@", STRATEGY["sid"])
                .replace("@@STRATEGY_NAME@@", STRATEGY["name"])
                .replace("@@STRATEGY_DESC@@", STRATEGY["desc"])
                .replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", STRATEGY["fname"]))
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")

    path = os.path.join(OUT, STRATEGY["fname"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {STRATEGY['fname']:<40} {n:>6,}줄  {len(blob)/1024:>7.1f}KB")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
