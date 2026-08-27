# -*- coding: utf-8 -*-
"""커버리지 게이트와 기업매칭 품질.   §51 · §52 · §50"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from entity.dart_crosswalk import mapping_quality
from backtest.universe import coverage_gate
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


def entity_gate(events: pd.DataFrame, amount_col: str = "amount") -> Tuple[pd.DataFrame, dict]:
    """§52 — 상장기업 관련 낙찰/계약금액 중 exact / verified / ambiguous / unmatched 비중."""
    a = events[events["stage"].isin(["AWARD", "CONTRACT"])]
    q = mapping_quality(a, amount_col)
    if not len(q):
        return q, {"verdict": "NO_DATA", "exact_amount_share": np.nan}
    exact = float(q.loc[q["map_type"].isin(["EXACT_ID", "VERIFIED_MANUAL"]), "금액비중"].sum())
    res = {"exact_amount_share": exact,
           "ambiguous_share": float(q.loc[q["map_type"] == "AMBIGUOUS", "금액비중"].sum()),
           "unmatched_share": float(q.loc[q["map_type"] == "UNMATCHED", "금액비중"].sum()),
           "out_of_validity_share": float(q.loc[q["map_type"] == "OUT_OF_VALIDITY",
                                                "금액비중"].sum())}
    # 상장사 귀속 금액은 전체 조달의 일부일 수밖에 없다(비상장 공급자가 다수).
    # 따라서 게이트는 '전체 대비'가 아니라 '식별된 것 중 exact 비중'으로 본다.
    ident = exact + res["ambiguous_share"]
    res["exact_among_identified"] = (exact / ident) if ident > 0 else np.nan
    res["verdict"] = ("PASS" if (pd.notna(res["exact_among_identified"]) and
                                 res["exact_among_identified"] >= 0.90) else "REVIEW")
    return q, res


def observability_report(events: pd.DataFrame, months: pd.DatetimeIndex,
                         firm_col: str = "stock_code") -> pd.DataFrame:
    """§50 — 월별 procurement-observable 기업 수 (현재 명단 소급 금지의 실증)."""
    from backtest.universe import procurement_observable
    o = procurement_observable(events, months, firm_col)
    if not len(o):
        return pd.DataFrame()
    return (o.groupby("month", observed=True)[firm_col].nunique()
            .rename("procurement_observable_N").reset_index())


def monthly_gate(F: pd.DataFrame, score_col: str, universe: Optional[pd.DataFrame],
                 top_pct: float = 0.20, gates: Optional[dict] = None
                 ) -> Tuple[pd.DataFrame, dict]:
    T, res = coverage_gate(F, score_col, universe, top_pct, gates)
    if res["verdict"] != "PASS":
        LOG.warn(f"[§51 SAMPLE_COLLAPSE] scored 중앙값 {res['scored']['median']:.0f} / "
                 f"p10 {res['scored']['p10']:.0f} / top bucket 중앙값 "
                 f"{res['top_bucket']['median']:.0f} — 성과와 무관하게 표본붕괴로 표시합니다.")
    else:
        LOG.ok(f"[§51] 커버리지 게이트 통과 — scored 중앙값 {res['scored']['median']:.0f}, "
               f"top bucket 중앙값 {res['top_bucket']['median']:.0f}")
    return T, res
