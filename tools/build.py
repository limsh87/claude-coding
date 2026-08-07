#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCD v2 빌더 — 공용 코어 + 선택된 센서팩을 하나의 자립 실행 파일로 조립한다.

각 전략 파일은 독립적으로 완결되어야 한다:
  백테스트 → 성과검증 → 강건성검사 → 해석표 출력까지 그 파일 하나로 전부 수행된다.
불필요한 팩 코드는 아예 포함하지 않는다(경량화).
"""
from __future__ import annotations
import os, sys, re, hashlib, datetime, subprocess, ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "strategies")

CORE_PRE = ["00_header.py", "01_bootstrap.py", "02_kernel.py", "03_util.py",
            "04_vault.py", "05_http.py"]
CORE_INGEST = {
    "universe": "10_ingest_universe.py",
    "price": "11_ingest_price.py",
    "dart": "12_ingest_dart_fin.py",
    "research": "13_ingest_research.py",
    "entity": "14_entity_research.py",
}
CORE_MID = ["20_pit.py", "21_axes.py", "29_pack_registry.py"]
PACK_FILES = {"C": "p_c_capital.py", "N": "p_n_employment.py", "D": "p_d_text.py",
              "X": "p_x_customs.py", "P": "p_p_procurement.py"}
CORE_POST = ["30_policy.py", "40_score.py", "41_backtest.py", "50_robust.py",
             "60_report.py", "70_contracts.py", "75_rehearsal.py", "80_selftest.py",
             "90_main.py"]

STRATEGIES = [
    dict(sid="PACK_C", fname="tcd_v2_01_pack_c_capital.py", packs=["C"],
         name="PACK-C 자본배분 체제 전환",
         desc="제국 건설을 멈추고 자본을 돌려주기 시작하는 전환을 탐지한다. "
              "핵심은 TP_P1 — 주주환원을 늘리면서 투자도 함께 늘리는 기업. "
              "대부분의 기업은 둘 중 하나를 택하므로, 둘 다 늘린다는 것은 현금창출력이 "
              "계단 상승했다는 뜻이다. 데이터가 전부 DART 정형 공시라 가장 빨리 검정된다."),
    dict(sid="PACK_N", fname="tcd_v2_02_pack_n_employment.py", packs=["N"],
         name="PACK-N 국민연금 고용",
         desc="고용은 되돌릴 수 없는 비용 지불이다. 핵심은 한계임금(wage_premium) — "
              "신규 채용자의 임금이 기존 평균보다 비싸면 역량 확충이고, 싸면 보조금 유인 채용이다. "
              "보조금 필터가 별도 패치가 아니라 산식 자체에 내장되어 있다."),
    dict(sid="PACK_D", fname="tcd_v2_03_pack_d_text.py", packs=["D"],
         name="PACK-D 공시텍스트 경직성",
         desc="Lazy Prices(JF 2020). 공시는 전년 문안을 복사하므로 '바뀌었다는 것 자체'가 신호다. "
              "주 용도는 V7 거부권 — 다른 신호가 매수를 가리키는데 위험요인·우발부채 문단이 "
              "급변했다면 센서가 못 본 무언가가 있다. 단독 알파 원천으로 세우지 말 것."),
    dict(sid="PACK_X", fname="tcd_v2_04_pack_x_customs.py", packs=["X"],
         name="PACK-X 관세청 수출",
         desc="물량·단가·목적지·신규세번을 월 단위로 동시 관측하는 유일한 공개 데이터셋. "
              "핵심은 x2(수출단가 잔차) — GPM과 달리 원가 노이즈가 0인 순수 가격결정력 측정치다. "
              "HS↔기업 매핑이 선행되어야 하며, 전 종목이 아니라 과점 품목에만 적용한다."),
    dict(sid="PACK_P", fname="tcd_v2_05_pack_p_procurement.py", packs=["P"],
         name="PACK-P 조달청 낙찰",
         desc="낙찰업체가 사업자등록번호로 직접 식별되므로 매핑 문제가 구조적으로 없다. "
              "낙찰률(q2)은 수출단가와 같은 성질의 순수 가격 지표다. "
              "방산·원전 레짐 편승 위험이 크므로 R7 레짐 분할이 필수 통과 조건이다."),
    dict(sid="INTEGRATED", fname="tcd_v2_00_integrated_all_packs.py",
         packs=["C", "N", "D", "X", "P"],
         name="통합 (전 센서팩)",
         desc="5개 센서팩을 모두 활성화하고 공용축 B·C·D와 함께 동일가중 합성한다(C7). "
              "데이터가 없는 팩은 V4 부분거부권으로 자동 무효화되고 그 사실이 로그에 남는다. "
              "팩별 기여는 R5 절제 검사에서 귀속된다."),
]


def read(name: str) -> str:
    with open(os.path.join(BUILD, name), encoding="utf-8") as f:
        return f.read()


def strip_shebang_and_future(src: str, keep_header: bool) -> str:
    """헤더 파일이 아닌 조각에서 shebang / coding / __future__ 를 제거한다."""
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


def build_one(spec: dict, version: str) -> str:
    parts = []
    order = (CORE_PRE + list(CORE_INGEST.values()) + CORE_MID +
             [PACK_FILES[p] for p in spec["packs"]] + CORE_POST)
    for i, fn in enumerate(order):
        src = read(fn)
        src = strip_shebang_and_future(src, keep_header=(i == 0))
        parts.append(src)
    blob = "\n".join(parts)

    packs_repr = "[" + ", ".join(f'"{p}"' for p in spec["packs"]) + "]"
    human = ", ".join(f"PACK-{p}" for p in spec["packs"])
    blob = (blob.replace("@@STRATEGY_ID@@", spec["sid"])
                .replace("@@STRATEGY_NAME@@", spec["name"])
                .replace("@@STRATEGY_DESC@@", spec["desc"])
                .replace("@@ACTIVE_PACKS_HUMAN@@", human)
                .replace("@@ACTIVE_PACKS@@", packs_repr)
                .replace("@@BUILD_VERSION@@", version)
                .replace("@@FILENAME@@", spec["fname"]))
    if "@@" in blob:
        leftovers = sorted(set(re.findall(r"@@\w+@@", blob)))
        raise SystemExit(f"치환되지 않은 플레이스홀더: {leftovers}")
    return blob


def check(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)          # 문법 검사
    # 중복 최상위 정의 감지 (조립 사고의 대표 증상)
    seen, dups = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                dups.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    if dups:
        raise SystemExit(f"{os.path.basename(path)}: 최상위 이름 중복 → {dups[:6]}")


def main():
    os.makedirs(OUT, exist_ok=True)
    version = datetime.datetime.now().strftime("v2.%Y%m%d.%H%M")
    made = []
    for spec in STRATEGIES:
        blob = build_one(spec, version)
        path = os.path.join(OUT, spec["fname"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(blob)
        check(path)
        n_lines = blob.count("\n") + 1
        made.append((spec["fname"], n_lines, len(blob)))
        print(f"  ✔ {spec['fname']:<44} {n_lines:>6,}줄  {len(blob)/1024:>7.1f}KB  "
              f"팩={','.join(spec['packs'])}")
    print(f"\n빌드 {version} — {len(made)}개 전략 파일 생성 → {OUT}")
    return made


if __name__ == "__main__":
    main()
