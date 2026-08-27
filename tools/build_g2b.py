#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2B-DEMAND-GRAPH-V1 단일파일 빌더.

g2b/src/ 의 모듈들을 **하나의 자립 실행 파일**로 조립한다.
Colab / JupyterLab 한 셀에 붙여넣거나 `python strategies/g2b_demand_graph_v1.py` 로 실행하면
  수집(캐시 우선) → lifecycle → graph → PIT 피처 → 사전등록 동결 → 백테스트 →
  메커니즘 → 강건성 → 보고서
까지 전부 수행하고 구글드라이브 공용/전용 인덱스에 적재한다.

조립 규칙
  · 각 모듈의 `# ── PACKAGE IMPORTS ──` ~ `# ── /PACKAGE IMPORTS ──` 블록만 제거한다.
    (패키지 형태에서는 정상 import, 단일파일에서는 불필요)
  · 표준/서드파티 import 는 상단으로 hoist 한다.
  · `CFG` 는 모듈 자기 자신을 가리키는 shim 으로 대체한다.
  · 조립 후 AST 파싱 + 최상위 이름 중복 검사를 통과해야 한다.
"""
from __future__ import annotations

import ast
import datetime as _dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "g2b", "src")
OUT = os.path.join(ROOT, "strategies")
OUT_NAME = "g2b_demand_graph_v1.py"

# 의존 순서 — 모듈 수준 실행(declare/BUDGET 생성)이 있으므로 순서가 중요하다.
ORDER = [
    "core/config.py", "core/log.py", "core/io.py", "core/vault.py", "core/http.py",
    "pit/timestamps.py", "pit/revisions.py", "pit/asof.py",
    "collectors/base.py", "collectors/order_plan.py", "collectors/prespec.py",
    "collectors/bid.py", "collectors/award.py", "collectors/contract.py",
    "collectors/process.py", "collectors/dart.py", "collectors/synthetic.py",
    "entity/dart_crosswalk.py", "entity/company_history.py", "entity/consortium.py",
    "graph/linker.py", "graph/lifecycle.py", "graph/demand_graph.py",
    "features/capability.py", "features/government_demand.py", "features/eligible_tam.py",
    "features/win_features.py", "features/competition.py", "features/concentration.py",
    "features/g2b_dwa.py",
    "backtest/universe.py", "backtest/costs.py", "backtest/statistics.py",
    "backtest/portfolio.py",
    "audit/prereg.py", "audit/pit_audit.py", "audit/leakage_test.py", "audit/coverage.py",
    "audit/robustness.py", "audit/mechanism.py",
    "pipeline.py",
]

PKG_START = "# ── PACKAGE IMPORTS ──"
PKG_END = "# ── /PACKAGE IMPORTS ──"

HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  G2B-DEMAND-GRAPH-V1
#  나라장터 정부수요 이동 → 기업역량 정합 → 실제 수주 전환  투자전략 연구 엔진
#  build: @@BUILD_VERSION@@
#
#  «기업이 잘하고 있다"를 사는 것이 아니라, 그 기업이 과거부터 경쟁력을 입증한 사업영역으로
#    외생적인 정부수요가 이동하고 있으며, 해당 기업이 그 증가한 수요를 실제 수주로
#    전환하고 있는지를 측정한다.»
#
#  ── 이 파일 하나로 끝납니다 ──────────────────────────────────────────────────────────────
#   Colab / JupyterLab 한 셀에 붙여넣거나 `python @@FILENAME@@` 로 실행하십시오.
#
#   실행 순서 (§97 연구 우선순위 — 순서를 바꾸지 않습니다)
#     [1] API historical depth 실측      [2] PIT 복원 가능성
#     [3] 낙찰기업 ↔ 상장회사 exact mapping [4] lifecycle 중복 제거
#     [5] 기업 capability                 [6] Eligible Government TAM
#     [7] Demand Shift                    [8] Win Realization
#     [9] Demand-Win Alignment            [10] Future return  ← 사전등록 동결 이후에만
#
#  ── 필수 설정 (환경변수) ─────────────────────────────────────────────────────────────────
#     DATA_GO_KR_SERVICE_KEY   공공데이터포털 일반 인증키(Decoding)
#     OPENDART_API_KEY         OpenDART 인증키
#     G2B_RUN_MODE             SMOKE | FULL | CACHED   (기본 SMOKE)
#     G2B_GDRIVE_ROOT          구글드라이브 캐시 루트 (기본 /content/drive/MyDrive/tcd_cache)
#
#  ── 구글드라이브 인덱스 ──────────────────────────────────────────────────────────────────
#     공용 _shared   : 원본·범용 정제본 (G2B 원장 6종, crosswalk, 계약이력) — 다른 전략도 재사용
#     전용 g2b_dg_v1 : 이 연구의 해석물 (lifecycle, graph, feature, backtest)
#     기존 캐시를 삭제·덮어쓰기하지 않습니다. 저널은 append-only 입니다.
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations
'''

DRIVER = '''

# ============================================================================================
#  단일파일 실행 드라이버 — §91 의 01~13 을 인프로세스로 순차 수행한다.
# ============================================================================================
def _md_table(df, max_rows: int = 200, floatfmt: str = "{:,.4g}") -> str:
    if df is None or not len(df):
        return "_(행 없음)_\\n"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
        else:
            d[c] = d[c].astype(str)
    cols = [str(c) for c in d.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in d.iterrows():
        out.append("| " + " | ".join(str(x).replace("|", "\\\\|") for x in r.tolist()) + " |")
    return "\\n".join(out) + "\\n"


def run_research(smoke_scale: int = 260) -> dict:
    """전 과정 실행. 반환 dict 에 모든 산출 테이블이 담긴다."""
    ensure_dirs()
    t0 = time.time()
    res: dict = {}
    LOG.banner("G2B-DEMAND-GRAPH-V1", f"mode={RUN_MODE}  run_id={run_id()}")
    LOG.info("§97 순서: API depth → PIT → 매핑 → lifecycle → capability → TAM → "
             "Demand → Win → Alignment → Future return")

    # [1~2] 수집 (캐시 우선)
    with LOG.stage("[1-2] 수집 · PIT 원장"):
        months = month_range(
            (pd.Timestamp(TARGET_START) - pd.DateOffset(months=WARMUP_MONTHS)).strftime("%Y-%m-%d"),
            TARGET_END)
        E, ctx = load_events(smoke_scale=smoke_scale)
        if not len(E):
            LOG.err("수집된 이벤트가 없습니다 → FINAL_DECISION = DATA_BLOCKED (§96)")
            return {"verdict": "DATA_BLOCKED", "reason": "이벤트 수집 실패"}
        viol = scan_events(E)
        if len(viol):
            LOG.table(viol.astype(str).values.tolist(), list(viol.columns), title="PIT 구조 위반")
            return {"verdict": "PIT_BLOCKED", "reason": "PIT 구조 위반", "violations": viol}
        LOG.ok("PIT 구조 위반 없음")

    # [3] 기업 매핑
    with LOG.stage("[3] 기업 매핑 (사업자등록번호 exact match)"):
        cw = load_crosswalk(E, ctx)
        res["crosswalk"] = cw

    # [4] lifecycle + graph
    with LOG.stage("[4] lifecycle · demand graph (이중계산 제거)"):
        gold = build_gold(E, cw)
        L = gold["events"]
        dc = double_count_audit(L)
        LOG.table(dc.assign(금액=lambda d: (d["금액"] / 1e8).round(1)).astype(str).values.tolist(),
                  ["측정", "금액(억원)"], title="§11 이중계산 제거 검증")
        res["double_count"] = dc
        q, eg = entity_gate(L)
        LOG.table(q.astype(str).values.tolist(), list(q.columns), title="§52 매칭 품질")
        res["entity_gate"] = q
        res["entity_gate_summary"] = eg
        gate_or_raise(L)          # §93 카나리아

    # [5~9] 피처
    with LOG.stage("[5-9] capability → TAM → Demand → Win → Alignment"):
        market = load_market(months, ctx)
        md = maturity_distribution(L)
        emb = int(md["p90"].max()) if len(md) else 365
        LOG.info(f"§23 MATURITY_EMBARGO = {emb}일 (실측 p90 최댓값, 수익률 미열람)")
        sales = load_pit_financials()
        feats = build_features(L, months, market,
                               pit_sales=(sales if len(sales) else None), maturity_days=emb)
        F = feats["company_g2b_features_monthly"]
        res.update(feats)
        res["market"] = market
        bad = scan_feature_inputs([c for c in F.columns if not c.startswith("_")])
        if len(bad):
            LOG.table(bad.astype(str).values.tolist(), list(bad.columns))
            return {"verdict": "PIT_BLOCKED", "reason": "CLASS C 필드가 피처에 혼입"}

    # 사전등록 동결 — 여기까지가 수익률 미열람 구간
    with LOG.stage("사전등록 동결 (§1.1) — 이 이후에만 미래수익률을 연다"):
        cov_m = (E.assign(month=pd.to_datetime(E["available_at"]) + pd.offsets.MonthEnd(0))
                 .groupby("month", observed=True).agg(n=("stage", "size"),
                                                      stages=("stage", "nunique")).reset_index())
        st = cov_m[(cov_m["stages"] >= 3) & (cov_m["n"] >= max(50, int(cov_m["n"].median() * .25)))]
        usable = ((pd.Timestamp(st["month"].min()) + pd.DateOffset(months=WARMUP_MONTHS)
                   + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d") if len(st) else None)
        try:
            freeze(maturity_embargo_days=emb, usable_start_date=usable,
                   notes="단일파일 실행 — 커버리지·성숙분포만 사용, 수익률 미열람 상태에서 동결")
        except FileNotFoundError as e:
            LOG.warn(f"사전등록 파일이 없어 동결을 건너뜁니다: {e}")
        LOG.table(verify().astype(str).values.tolist(), list(verify().columns), title="동결 검증")
        if usable:
            F = F[F["month"] >= pd.Timestamp(usable)]

    if future_return_lock():
        LOG.err("FUTURE_RETURN_LOCK 이 걸려 있어 수익률 검정을 수행할 수 없습니다. "
                "config/ 4개 YAML 과 audit/trial_ledger.json 을 배치한 뒤 다시 실행하십시오.")
        res["verdict"] = "PIT_BLOCKED"
        return res

    # [10] 백테스트 · 메커니즘 · 강건성
    with LOG.stage("[10] PRIMARY 백테스트"):
        T, cov = monthly_gate(F, "G2B_DWA", None)
        res["coverage_monthly"], res["coverage_gate"] = T, cov
        bt = run_backtest(F, market, "G2B_DWA", top_pct=0.20, weighting="equal")
        res["backtest"] = bt
        if not len(bt["returns"]):
            res["verdict"] = "SAMPLE_COLLAPSE"
            return res
        rc = bt["ret_col"]
        LOG.table(bt["summary"].T.reset_index().astype(str).values.tolist(),
                  ["지표", "gross", "net"], title="§60 성과표")
        LOG.table(bt["quantile_table"].astype(str).values.tolist(),
                  list(bt["quantile_table"].columns), title="§55 분위 성과")
        ic, _ = information_coefficient(bt["scored"], "G2B_DWA", rc)
        res["ic"] = ic
        LOG.table(ic.astype(str).values.tolist(), list(ic.columns), title="§61 IC")
        tp = temporal_placebo(F, "G2B_DWA", market)
        if len(tp):
            LOG.table(tp.astype(str).values.tolist(), list(tp.columns), title="§75 Temporal placebo")
            res["temporal_placebo"] = tp

    with LOG.stage("메커니즘 검정 (§63 §80 §84)"):
        S = bt["scored"]
        res["causal_chain"] = causal_chain(S)
        res["decomposition"] = decomposition(S, rc)
        res["nested"] = nested_comparison(S, rc)
        res["bucket_2x2"] = bucket_2x2(S, rc)
        for k, title in (("causal_chain", "§80 인과 사슬"), ("decomposition", "§63 분해"),
                         ("nested", "§84 ★최종 비교 — Demand Graph vs 단순 낙찰금액/시총"),
                         ("bucket_2x2", "§29 2×2")):
            if len(res[k]):
                LOG.table(res[k].astype(str).values.tolist(), list(res[k].columns), title=title)

    with LOG.stage("강건성 (§65~§73)"):
        rb = {"기간(§65)": by_period(S, "G2B_DWA", rc),
              "LOYO(§66)": leave_one_year_out(S, "G2B_DWA", rc),
              "시장(§72)": by_bucket(S, "G2B_DWA", rc, "market"),
              "시총(§71)": by_bucket(S, "G2B_DWA", rc, "mcap"),
              "업종(§73)": by_bucket(S, "G2B_DWA", rc, "sector"),
              "비용(§59)": cost_stress(S, "G2B_DWA", rc),
              "상위기여제거(§70)": drop_top_contributors(S, "G2B_DWA", rc)}
        for k, Tb in rb.items():
            if Tb is not None and len(Tb):
                LOG.table(Tb.astype(str).values.tolist(), list(Tb.columns), title=k)
        res["robustness"] = rb
        res["robust_summary"] = summarize(rb)
        LOG.table(res["robust_summary"].astype(str).values.tolist(),
                  list(res["robust_summary"].columns), title="강건성 요약")

    # 판정 + 저장
    ex = bt["excess"]
    net_t = float(hac_t(ex["net_excess"])) if len(ex) else float("nan")
    net_ann = float(ex["net_excess"].mean() * 12) if len(ex) else float("nan")
    if RUN_MODE == "SMOKE":
        verdict = "DATA_BLOCKED"
    elif cov["verdict"] != "PASS":
        verdict = "SAMPLE_COLLAPSE"
    elif not np.isfinite(net_t):
        verdict = "DATA_BLOCKED"
    elif net_t >= 2.0 and net_ann >= 0.03:
        verdict = "STRONG_PASS"
    elif net_t >= 2.0 and net_ann > 0:
        verdict = "PASS"
    elif net_t >= 1.0 and net_ann > 0:
        verdict = "WEAK_EVIDENCE"
    else:
        verdict = "NO_ALPHA"
    res["verdict"] = verdict

    save_outputs(gold, feats, cw, {"portfolios": bt["returns"]})
    get_vault().report()
    LOG.banner(f"FINAL DECISION: {verdict}",
               f"순초과 {net_ann * 100:.2f}%p/yr · NW t {net_t:.2f} · "
               f"소요 {time.time() - t0:.0f}s")
    if RUN_MODE == "SMOKE":
        LOG.warn("SMOKE 모드 결과는 합성 데이터입니다 — 연구 결론이 아닙니다. "
                 "실증 판정은 키를 넣고 G2B_RUN_MODE=FULL 로 실행하십시오.")
    return res


def hac_t(x) -> float:
    return newey_west_t(x)[2]


if __name__ == "__main__":
    run_research()
'''


def read(rel: str) -> str:
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return f.read()


def strip_module(src: str) -> tuple[str, list[str]]:
    """PACKAGE IMPORTS 블록 제거 + 상단 import hoist. (본문, hoist된 import 줄)."""
    out, imports, in_pkg = [], [], False
    for ln in src.split("\n"):
        s = ln.strip()
        if s.startswith(PKG_START):
            in_pkg = True
            continue
        if s.startswith(PKG_END):
            in_pkg = False
            continue
        if in_pkg:
            continue
        if s.startswith("#!") or s.startswith("# -*- coding") or s.startswith("from __future__"):
            continue
        # 최상위 표준/서드파티 import 만 hoist (들여쓰기된 지연 import 는 그대로 둔다)
        if (ln.startswith("import ") or ln.startswith("from ")) and " import " not in ln[:0]:
            if ln.startswith("import ") or (ln.startswith("from ") and " import " in ln):
                imports.append(ln.rstrip())
                continue
        out.append(ln)
    return "\n".join(out), imports


def build() -> str:
    version = _dt.datetime.now().strftime("v1.%Y%m%d.%H%M")
    bodies, imports = [], []
    for rel in ORDER:
        body, imps = strip_module(read(rel))
        imports += imps
        bodies.append(f"\n\n# {'=' * 90}\n#  {rel}\n# {'=' * 90}\n" + body.strip("\n"))
    # import 중복 제거 (순서 보존)
    seen, uniq = set(), []
    for i in imports:
        k = i.strip()
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    uniq.append("import time")
    shim = (
        "\n\n# ── 단일파일 shim: CFG 는 이 모듈 자신을 가리킨다 "
        "(패키지 형태의 `from core import config as CFG` 대체) ──\n"
        "CFG = sys.modules[__name__]\n")
    blob = (HEADER + "\n" + "\n".join(sorted(set(u for u in uniq if u.startswith("import ")))) +
            "\n" + "\n".join(u for u in uniq if u.startswith("from ")) + shim +
            "\n".join(bodies) + DRIVER)
    blob = blob.replace("@@BUILD_VERSION@@", version).replace("@@FILENAME@@", OUT_NAME)
    if "@@" in blob:
        left = sorted(set(re.findall(r"@@\w+@@", blob)))
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
        raise SystemExit(f"최상위 이름 중복 → {dups[:8]}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    blob = build()
    path = os.path.join(OUT, OUT_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)
    check(path)
    print(f"  ✔ {OUT_NAME}  {blob.count(chr(10)) + 1:,}줄  {len(blob) / 1024:.1f}KB  "
          f"({len(ORDER)}개 모듈)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
