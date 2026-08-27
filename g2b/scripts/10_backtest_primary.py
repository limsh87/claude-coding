#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""10 — PRIMARY 백테스트 (§53~§62).

실행 전 관문 두 개를 통과해야 한다:
  ① §1.1 FUTURE_RETURN_LOCK 이 풀려 있어야 한다 (09 동결 완료)
  ② §93 누수 카나리아를 통과해야 한다
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from audit.leakage_test import gate_or_raise, temporal_placebo, permutation_placebo
from audit.coverage import monthly_gate
from backtest.portfolio import run_backtest
from backtest.statistics import information_coefficient, fama_macbeth, quantile_returns
from backtest.costs import cost_table


def main() -> int:
    header("10 PRIMARY 백테스트", "§53~§62 — G2B_DWA 상위 20% Long-only")
    if CFG.future_return_lock():
        LOG.err("FUTURE_RETURN_LOCK 이 걸려 있습니다. 09_freeze_preregistration.py 를 먼저 실행하십시오.")
        return 1
    L = require("events_lifecycle", "05_build_lifecycle.py")
    F = require("company_g2b_features_monthly", "08_build_features.py")
    market = require("market", "08_build_features.py")

    LOG.info("§93 누수 카나리아 관문…")
    tab = gate_or_raise(L)
    LOG.table(tab.astype(str).values.tolist(), list(tab.columns))
    save("canary", tab)

    # §48 USABLE_START_DATE 적용 (동결값)
    import yaml
    ud = yaml.safe_load(open(os.path.join(CFG.CONFIG_DIR, "universe_definition.yaml"),
                             encoding="utf-8"))
    usable = ud.get("usable_start_date")
    if usable:
        F = F[F["month"] >= pd.Timestamp(usable)]
        LOG.info(f"동결된 USABLE_START_DATE {usable} 적용 → {F['month'].min():%Y-%m} 부터")

    T, res = monthly_gate(F, "G2B_DWA", None)
    save("coverage_monthly", T)
    write_json(os.path.join(CFG.AUDIT_DIR, "coverage_gate.json"), res)
    if res["verdict"] != "PASS":
        LOG.warn("§51 SAMPLE_COLLAPSE — 성과가 좋아도 그렇게 보고합니다.")

    bt = run_backtest(F, market, "G2B_DWA", top_pct=0.20, weighting="equal")
    if not len(bt["returns"]):
        LOG.err("포트폴리오를 만들 수 없습니다 (표본 부족).")
        return 1
    rc = bt["ret_col"]
    save("primary_returns", bt["returns"])
    save("primary_holdings", bt["holdings"])
    save("primary_quantiles", bt["quantile_returns"].reset_index())
    save("scored", bt["scored"])

    LOG.table(bt["summary"].T.reset_index().astype(str).values.tolist(), ["지표", "gross", "net"],
              title="§60 PRIMARY 성과표")
    LOG.table(bt["quantile_table"].astype(str).values.tolist(),
              list(bt["quantile_table"].columns), title="§55 분위 성과 (monotonicity)")
    save("primary_summary", bt["summary"])
    save("primary_quantile_table", bt["quantile_table"])

    ex = bt["excess"]
    if len(ex):
        from backtest.statistics import perf_table
        E = pd.concat([perf_table(ex["gross_excess"], label="Q_top - Universe (gross)"),
                       perf_table(ex["net_excess"], label="Q_top - Universe (net)")],
                      ignore_index=True)
        LOG.table(E.astype(str).values.tolist(), list(E.columns), title="§61 초과수익 검정")
        save("primary_excess", E)

    ic, ics = information_coefficient(bt["scored"], "G2B_DWA", rc)
    if len(ic):
        LOG.table(ic.astype(str).values.tolist(), list(ic.columns), title="§61 IC")
        save("primary_ic", ic)
        save("primary_ic_series", ics)

    import numpy as np
    Sx = bt["scored"].copy()
    Sx["log_mcap"] = np.log(pd.to_numeric(Sx.get("mcap"), errors="coerce").clip(lower=1.0))
    fm = fama_macbeth(Sx, rc, ["G2B_DWA", "log_mcap"])
    if len(fm):
        LOG.table(fm.astype(str).values.tolist(), list(fm.columns),
                  title="§62 Fama-MacBeth (스타일 프록시 여부)")
        save("primary_fama_macbeth", fm)

    ct = cost_table(bt["returns"]["turnover"], bt["returns"]["gross_ret"], bt["returns"]["cost"])
    LOG.table(ct.T.reset_index().astype(str).values.tolist(), ["항목", "값"], title="§59 비용")
    save("primary_costs", ct)

    tp = temporal_placebo(F, "G2B_DWA", market)
    if len(tp):
        LOG.table(tp.astype(str).values.tolist(), list(tp.columns), title="§75 Temporal placebo")
        save("temporal_placebo", tp)
        if tp["판정"].iloc[0] == "LEAKAGE_SUSPECT":
            LOG.err("미래신호가 과거수익을 강하게 설명합니다 — 타임스탬프/PIT 재감사가 필요합니다(§75).")
    pp = permutation_placebo(bt["scored"], "G2B_DWA", rc, n_perm=100)
    if len(pp):
        LOG.table(pp.astype(str).values.tolist(), list(pp.columns), title="§74 Permutation placebo")
        save("permutation_placebo", pp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
