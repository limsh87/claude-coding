#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARC-SACN 빌더 — 공용 코어(build/) + SACN 전용 조각(build_sacn/) 을 자립 실행 파일로 조립.

TCD v2 의 build/ 조각을 '수정 없이' 재사용한다. 두 전략이 같은 공용 캐시 인덱스를
공유하려면 수집·정제 계층이 문자 그대로 같아야 하기 때문이다.
재사용하지 않는 TCD 전용 계층(센서팩·축·스코어·TCD 백테스트)은 아예 포함하지 않는다.
"""
from __future__ import annotations
import os, sys, re, ast, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "build")
SACN = os.path.join(ROOT, "build_sacn")
OUT = os.path.join(ROOT, "strategies")

# (디렉터리, 파일명) — 조립 순서가 곧 실행 순서다.
ORDER = [
    (SACN, "s00_header.py"),        # 설정 (키 입력부 최상단)
    (CORE, "01_bootstrap.py"),      # 환경·의존성           [재사용]
    (SACN, "s02_root.py"),          # resolve_project_root  (SPEC §2.1)
    (CORE, "02_kernel.py"),         # 로깅·스테이지·I/O원장  [재사용]
    (CORE, "03_util.py"),           # 유틸·PIT·통계          [재사용]
    (CORE, "04_vault.py"),          # 드라이브 캐시(절대1원칙)[재사용]
    (CORE, "05_http.py"),           # HTTP·스로틀·인코딩     [재사용]
    (SACN, "s07_perf.py"),          # 출력봉인·회로차단·캐시원장 (신규)
    (SACN, "s06_dart.py"),          # DART 실시간 호출량 관리 (교체)
    (CORE, "10_ingest_universe.py"),# 종목마스터·상장폐지     [재사용]
    (SACN, "s10b_krxbulk.py"),      # KRX 인증·MDC 벌크·증권유형 (신규)
    (SACN, "s11_price.py"),         # 가격 다중소스          (전면 재작성)
    (SACN, "s12_market_meta.py"),   # 시총·BM·제외플래그·업종 (전면 재작성)
    (SACN, "s13_research.py"),      # 한경·네이버 리포트     (전면 재작성)
    (CORE, "14_entity_research.py"),# 애널리스트 원장        [재사용]
    (SACN, "s15_analyst.py"),       # 식별 보강·Phase0·IPW   (신규)
    (CORE, "20_pit.py"),            # PIT store · Universe   [재사용]
    (SACN, "s21_universe.py"),      # SPEC §5 유니버스       (신규)
    (SACN, "s22_link.py"),          # 링크 행렬 · 스킬       (신규)
    (SACN, "s23_signal.py"),        # SACN 신호 · 직교화     (신규)
    (SACN, "s30_backtest.py"),      # 분위 백테스트          (신규)
    (SACN, "s40_stats.py"),         # 부트스트랩·PBO·DSR·WF  (신규)
    (SACN, "s41_hypothesis.py"),    # H1~H4 · 메커니즘       (신규)
    (SACN, "s50_report.py"),        # 성과·강건성·해석·산출물 (신규)
    (SACN, "s60_validate.py"),      # 계약·스모크·리허설     (신규)
    (SACN, "s90_main.py"),          # 오케스트레이터         (신규)
]

SPEC = dict(
    sid="ARC_SACN",
    fname="arc_sacn_shared_coverage_network.py",
    name="공동커버리지 네트워크 모멘텀 (Shared Analyst Coverage Network Momentum)",
)


def read(d: str, name: str) -> str:
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def strip_head(src: str, keep: bool) -> str:
    if keep:
        return src
    return "\n".join(l for l in src.split("\n")
                     if not (l.strip().startswith("#!")
                             or l.strip().startswith("# -*- coding")
                             or l.strip().startswith("from __future__ import")))


def build(version: str) -> str:
    parts = []
    for i, (d, fn) in enumerate(ORDER):
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            raise SystemExit(f"조각 없음: {p}")
        parts.append(f"\n# {'='*90}\n# 조각: {fn}\n# {'='*90}\n"
                     + strip_head(read(d, fn), keep=(i == 0)))
    blob = "\n".join(parts)
    blob = (blob.replace("@@STRATEGY_ID@@", SPEC["sid"])
                .replace("@@STRATEGY_NAME@@", SPEC["name"])
                .replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", SPEC["fname"]))
    left = sorted(set(re.findall(r"@@\w+@@", blob)))
    if left:
        raise SystemExit(f"치환되지 않은 플레이스홀더: {left}")
    return blob


def check(path: str) -> None:
    """문법 + 최상위 중복정의 + 정의 전 사용(모듈 레벨) 검사."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"최상위 이름 중복 → {dups[:8]}")
    print(f"  · 문법 OK · 최상위 정의 {len(seen)}개 · 중복 0")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("sacn.%Y%m%d.%H%M")
    blob = build(version)
    path = os.path.join(OUT, SPEC["fname"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    n = blob.count("\n") + 1
    print(f"  ✔ {SPEC['fname']}  {n:,}줄  {len(blob)/1024:.1f}KB")
    print(f"\n빌드 {version} → {path}")
    return path


if __name__ == "__main__":
    main()
