#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""11 — 메커니즘 검정 (§29 §39 §46 §63 §64 §80 §82 §84)."""
from _common import *                                          # noqa: F401,F403
import pandas as pd
from audit.mechanism import (causal_chain, revenue_lag_analysis, decomposition,
                             nested_comparison, bucket_2x2, secondary_family_fdr,
                             stage_information_value, event_study)
from features.competition import pipeline_conversion, win_conversion


def main() -> int:
    header("11 메커니즘 검정", "§80 인과사슬 · §84 최종 비교")
    if CFG.future_return_lock():
        LOG.err("FUTURE_RETURN_LOCK 이 걸려 있습니다. 09 를 먼저 실행하십시오.")
        return 1
    S = require("scored", "10_backtest_primary.py")
    L = require("events_lifecycle", "05_build_lifecycle.py")
    rc = next((c for c in S.columns if c.startswith("fwd_ret_")), None)
    if rc is None:
        LOG.err("forward return 컬럼이 없습니다.")
        return 1

    cc = causal_chain(S)
    LOG.table(cc.astype(str).values.tolist(), list(cc.columns), title="§80 인과 사슬")
    save("mech_causal_chain", cc)

    pc = pipeline_conversion(L)
    if len(pc):
        LOG.table(pc.astype(str).values.tolist(), list(pc.columns), title="§39 단계 전환율")
        save("mech_pipeline_conversion", pc)
    wc = win_conversion(L)
    LOG.table(wc.astype(str).values.tolist(), list(wc.columns), title="§38 입찰→낙찰 전환")
    save("mech_win_conversion", wc)

    dec = decomposition(S, rc)
    LOG.table(dec.astype(str).values.tolist(), list(dec.columns),
              title="§63 Demand / Win / Alignment 분해")
    save("mech_decomposition", dec)

    nc = nested_comparison(S, rc)
    LOG.table(nc.astype(str).values.tolist(), list(nc.columns),
              title="§84 최종 비교 — 복잡한 Demand Graph 가 단순 낙찰금액/시총보다 나은가")
    save("mech_nested_comparison", nc)

    b2 = bucket_2x2(S, rc)
    LOG.table(b2.astype(str).values.tolist(), list(b2.columns), title="§29 2×2 메커니즘")
    save("mech_2x2", b2)

    sec = ["D1_DS_YOY", "D2_PIPELINE_YOY", "WIN_MCAP", "WIN_SALES", "win_accel_rate",
           "new_agency_count", "new_category_award_share", "REPEAT_WIN_RATE",
           "AGENCY_HHI", "CATEGORY_HHI", "TOP1_SHARE", "CONTRACT_REVISION_RATIO",
           "resid_bidder_count", "PROC_RISK"]
    fdr = secondary_family_fdr(S, rc, sec)
    if len(fdr):
        LOG.table(fdr.astype(str).values.tolist(), list(fdr.columns),
                  title="§78 Secondary family + BH/FDR")
        save("mech_secondary_fdr", fdr)

    sales = load("pit_sales")
    rl = revenue_lag_analysis(S, sales)
    LOG.table(rl.astype(str).values.tolist(), list(rl.columns),
              title="§46 §47 계약 → 매출 인식 지연 (MECHANISM_VALIDATION_ONLY)")
    save("mech_revenue_lag", rl)

    es = event_study(L, None)
    LOG.table(es.astype(str).values.tolist(), list(es.columns), title="§82 이벤트 스터디")
    save("mech_event_study", es)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
