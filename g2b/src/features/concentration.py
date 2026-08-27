# -*- coding: utf-8 -*-
"""집중도 · 대형계약 의존 · 계약변경.   §33 · §34 · §40 · §41 · §42 · §43

  §33 AGENCY_HHI = Σ s_a²      §34 CATEGORY_HHI
  §40 CONTRACT_REVISION_RATIO = final_known_contract / initial_contract
      단 t 시점에는 '그때까지 알려진 revision' 만 쓴다.
  §41 TOP1_SHARE / TOP3_SHARE — PRIMARY 와 분리된 risk diagnostic
  §42 처음부터 hard exclusion 하지 않는다. 연속형 risk score 로 만든다.
  §43 PROC_RISK 는 G2B_DWA 와 섞지 않은 상태로 먼저 검정한다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from features.capability import _decay_expand
# ── /PACKAGE IMPORTS ──

from typing import Optional, Sequence

import numpy as np
import pandas as pd


def _hhi(events: pd.DataFrame, months: pd.DatetimeIndex, dim: str, firm_col: str,
         amount_col: str, lookback_m: int, out_name: str) -> pd.DataFrame:
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].dropna(subset=[dim]).copy()
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month", out_name])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)
    o = e.groupby([firm_col, dim, "month"], as_index=False, observed=True).agg(amt=("amt", "sum"))
    R = _decay_expand(o, [firm_col, dim], months, lookback_m, 1e9, "amt", "amt_w")
    R["tot"] = R.groupby([firm_col, "month"], observed=True)["amt_w"].transform("sum")
    R["s2"] = (R["amt_w"] / R["tot"].replace(0, np.nan)) ** 2
    return (R.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(**{out_name: ("s2", "sum")}))


def build_concentration(events: pd.DataFrame, months: pd.DatetimeIndex,
                        firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                        lookback_m: int = 12) -> pd.DataFrame:
    """AGENCY_HHI · CATEGORY_HHI · TOP1/TOP3_SHARE."""
    A = _hhi(events, months, "agency_cd", firm_col, amount_col, lookback_m, "AGENCY_HHI")
    C = _hhi(events, months, "category_cd", firm_col, amount_col, lookback_m, "CATEGORY_HHI")
    out = A.merge(C, on=[firm_col, "month"], how="outer") if len(A) or len(C) else \
        pd.DataFrame(columns=[firm_col, "month"])

    # §41 단일 초대형 계약 의존 — TTM 내 최대 계약 / TTM 총액
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if len(e):
        e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
        e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)
        deal = e.groupby([firm_col, "opportunity_id", "month"], as_index=False, observed=True) \
                .agg(amt=("amt", "sum"))
        D = _decay_expand(deal, [firm_col, "opportunity_id"], months, lookback_m, 1e9, "amt", "amt_w")
        D = D[D["amt_w"] > 0]
        if len(D):
            D["rk"] = D.groupby([firm_col, "month"], observed=True)["amt_w"].rank(
                ascending=False, method="first")
            tot = (D.groupby([firm_col, "month"], as_index=False, observed=True)
                   .agg(tot=("amt_w", "sum")))
            t1 = (D[D["rk"] <= 1].groupby([firm_col, "month"], as_index=False, observed=True)
                  .agg(top1=("amt_w", "sum")))
            t3 = (D[D["rk"] <= 3].groupby([firm_col, "month"], as_index=False, observed=True)
                  .agg(top3=("amt_w", "sum")))
            T = tot.merge(t1, on=[firm_col, "month"], how="left").merge(
                t3, on=[firm_col, "month"], how="left")
            T["TOP1_SHARE"] = T["top1"] / T["tot"].replace(0, np.nan)
            T["TOP3_SHARE"] = T["top3"] / T["tot"].replace(0, np.nan)
            out = out.merge(T[[firm_col, "month", "TOP1_SHARE", "TOP3_SHARE"]],
                            on=[firm_col, "month"], how="outer")
    return out.reset_index(drop=True)


def contract_revision(events: pd.DataFrame, months: pd.DatetimeIndex,
                      firm_col: str = "stock_code") -> pd.DataFrame:
    """§40 — 시점 t 까지 '알려진' 계약변경만 반영한 증액/감액/취소 지표."""
    c = events[(events["stage"] == "CONTRACT") & events[firm_col].notna()].copy()
    if not len(c):
        return pd.DataFrame(columns=[firm_col, "month"])
    c["month"] = pd.to_datetime(c["available_at"]) + pd.offsets.MonthEnd(0)
    c = c.sort_values(["opportunity_id", "available_at"], kind="stable")
    g = c.groupby("opportunity_id", sort=False, observed=True)
    c["initial_amt"] = g["amount"].transform("first")
    c["prev_amt"] = g["amount"].shift(1)
    c["delta"] = pd.to_numeric(c["amount"], errors="coerce") - c["prev_amt"]
    c["is_increase"] = c["delta"] > 0
    c["is_decrease"] = c["delta"] < 0
    st = c.get("status_raw", pd.Series("", index=c.index)).astype(str)
    c["is_cancel"] = st.str.contains("취소|해지|DLT|삭제", regex=True, na=False)
    c["rev_ratio"] = pd.to_numeric(c["amount"], errors="coerce") / c["initial_amt"].replace(0, np.nan)
    out = (c.groupby([firm_col, "month"], as_index=False, observed=True)
           .agg(CONTRACT_REVISION_RATIO=("rev_ratio", "mean"),
                contract_increase_n=("is_increase", "sum"),
                contract_decrease_n=("is_decrease", "sum"),
                contract_cancel_n=("is_cancel", "sum"),
                contract_delta_amt=("delta", "sum")))
    return out


def proc_risk_score(F: pd.DataFrame, cols: Sequence[str] = ("AGENCY_HHI", "CATEGORY_HHI",
                                                            "TOP1_SHARE"),
                    month_col: str = "month") -> pd.Series:
    """§42·§43 — 연속형 risk score. hard exclusion 을 하지 않는다.

    각 위험 축을 월별 횡단면 백분위로 만든 뒤 평균. PRIMARY alpha 와 섞지 않는다.
    """
    use = [c for c in cols if c in F.columns]
    if not use:
        return pd.Series(np.nan, index=F.index)
    pct = pd.DataFrame(index=F.index)
    for c in use:
        pct[c] = F.groupby(month_col, observed=True)[c].rank(pct=True)
    return pct.mean(axis=1)
