#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""12 — 강건성 (§65~§75).

LOAO/LOCO/mega-deal 은 이벤트를 지우고 **피처를 다시 만들어** 측정한다.
'뺐다'고 말하면서 피처를 그대로 두면 검사가 아니라 연출이다.
"""
from _common import *                                          # noqa: F401,F403
import pandas as pd
import pipeline as P
from audit.robustness import (by_period, leave_one_year_out, leave_one_out_rebuild,
                              mega_contract_sensitivity, drop_top_contributors,
                              by_bucket, cost_stress, summarize)
from backtest.portfolio import attach_forward_return


def main() -> int:
    header("12 강건성", "§65~§75")
    if CFG.future_return_lock():
        LOG.err("FUTURE_RETURN_LOCK 이 걸려 있습니다. 09 를 먼저 실행하십시오.")
        return 1
    S = require("scored", "10_backtest_primary.py")
    L = require("events_lifecycle", "05_build_lifecycle.py")
    market = require("market", "08_build_features.py")
    rc = next((c for c in S.columns if c.startswith("fwd_ret_")), None)
    months = months_for_research()
    sales = load("pit_sales")

    tables = {}
    tables["기간(§65)"] = by_period(S, "G2B_DWA", rc)
    tables["LOYO(§66)"] = leave_one_year_out(S, "G2B_DWA", rc)
    tables["시장(§72)"] = by_bucket(S, "G2B_DWA", rc, "market")
    tables["시총(§71)"] = by_bucket(S, "G2B_DWA", rc, "mcap")
    tables["업종(§73)"] = by_bucket(S, "G2B_DWA", rc, "sector")
    tables["비용(§59)"] = cost_stress(S, "G2B_DWA", rc)
    tables["상위기여제거(§70)"] = drop_top_contributors(S, "G2B_DWA", rc)

    def rebuild(events: pd.DataFrame) -> pd.DataFrame:
        f = P.build_features(events, months, market,
                             pit_sales=(sales if sales is not None and len(sales) else None))
        return attach_forward_return(f["company_g2b_features_monthly"], market)

    LOG.info("§67 §68 §69 는 피처를 재구축합니다 — 시간이 걸립니다.")
    tables["LOAO(§67)"] = leave_one_out_rebuild(L, rebuild, "G2B_DWA", rc, "agency_cd", top_k=3)
    tables["LOCO(§68)"] = leave_one_out_rebuild(L, rebuild, "G2B_DWA", rc, "category_cd", top_k=3)
    tables["초대형계약(§69)"] = mega_contract_sensitivity(L, rebuild, "G2B_DWA", rc)

    for k, T in tables.items():
        if T is not None and len(T):
            LOG.table(T.astype(str).values.tolist(), list(T.columns), title=k)
            save("robust_" + k.split("(")[0], T)
    Sm = summarize(tables)
    LOG.table(Sm.astype(str).values.tolist(), list(Sm.columns), title="강건성 요약")
    save("robust_summary", Sm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
