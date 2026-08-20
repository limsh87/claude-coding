# -*- coding: utf-8 -*-
"""경쟁강도 · 낙찰률 · 유찰/재입찰 · 전환율.   §35 · §36 · §37 · §38 · §39

★ 이 파일의 모든 변수는 PRIMARY 팩터가 아니라 **진단용**이다(§76).
  경제적 부호가 조달방식마다 다르므로 성과를 본 뒤 부호를 뒤집는 짓을 막기 위해
  여기서는 부호를 붙이지 않고 값만 만든다. V2 에 넣으려면 별도 preregistration 이 필요하다.

§35 bidder_count 는 절대값이 아니라 (category × method × year × agency_type) 내 상대값으로 본다.
§36 낙찰률은 제도 차이가 있으므로 raw 비교 금지 → ResidualAwardRate.
§37 높은 유찰률은 반드시 악재가 아니다 → 임의의 음(-) 부호를 넣지 않는다.
§38 참여업체 전체정보가 불완전하면 NOT_IDENTIFIABLE 로 두고 가짜 conversion rate 를 만들지 않는다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import safe_div
# ── /PACKAGE IMPORTS ──

from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _cell_residual(d: pd.DataFrame, value: str, cells: Sequence[str], min_n: int = 20) -> pd.Series:
    """셀 내 평균 대비 잔차. 셀 표본이 작으면 상위 셀로 backoff 하고, 끝내 작으면 NaN."""
    v = pd.to_numeric(d[value], errors="coerce")
    out = pd.Series(np.nan, index=d.index)
    remaining = pd.Series(True, index=d.index)
    for k in range(len(cells), 0, -1):
        key = list(cells[:k])
        g = v.groupby([d[c] for c in key], observed=True)
        mu = g.transform("mean")
        n = g.transform("size")
        ok = remaining & (n >= min_n) & v.notna()
        out[ok] = (v - mu)[ok]
        remaining &= ~ok
        if not bool(remaining.any()):
            break
    return out


def award_rate_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                        firm_col: str = "stock_code") -> pd.DataFrame:
    """§36 — ResidualAwardRate 를 (category × method × year) 안에서 계산한 뒤 기업×월로 집계."""
    a = events[(events["stage"] == "AWARD")].copy()
    if not len(a):
        return pd.DataFrame(columns=[firm_col, "month"])
    rate = pd.to_numeric(a.get("award_rate"), errors="coerce")
    fallback = safe_div(a.get("amount"), a.get("expected_price")) * 100.0
    a["award_rate_use"] = rate.where(rate.between(30, 130), fallback)
    a["year"] = pd.to_datetime(a["available_at"]).dt.year
    a["resid_award_rate"] = _cell_residual(a, "award_rate_use",
                                           ["category_cd", "method", "year"])
    a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    f = a[a[firm_col].notna()]
    if not len(f):
        return pd.DataFrame(columns=[firm_col, "month"])
    W = (f.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(award_rate_mean=("award_rate_use", "mean"),
              resid_award_rate=("resid_award_rate", "mean"),
              award_rate_n=("award_rate_use", "count")))
    cov = float(a["award_rate_use"].notna().mean())
    if cov < 0.2:
        LOG.warn(f"예정가격/낙찰률 보유율 {cov * 100:.1f}% — §36 낙찰률 지표가 사실상 죽습니다. "
                 f"결과 해석 시 반드시 감안하십시오.")
    return W


def competition_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                         firm_col: str = "stock_code") -> pd.DataFrame:
    """§35 — 기업이 노출된 시장의 상대적 경쟁강도."""
    a = events[(events["stage"] == "AWARD")].copy()
    if not len(a) or "bidder_count" not in a.columns:
        return pd.DataFrame(columns=[firm_col, "month"])
    a["year"] = pd.to_datetime(a["available_at"]).dt.year
    a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    bc = pd.to_numeric(a["bidder_count"], errors="coerce")
    if bc.notna().mean() < 0.05:
        LOG.warn("bidder_count 보유율이 5% 미만 — 경쟁강도(§35)를 NOT_IDENTIFIABLE 로 둡니다.")
        return pd.DataFrame(columns=[firm_col, "month"])
    a["resid_bidder_count"] = _cell_residual(a, "bidder_count", ["category_cd", "method", "year"])
    f = a[a[firm_col].notna()]
    return (f.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(bidder_count_mean=("bidder_count", "mean"),
                 resid_bidder_count=("resid_bidder_count", "mean")))


def failure_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                     capability: Optional[pd.DataFrame] = None,
                     firm_col: str = "stock_code") -> pd.DataFrame:
    """§37 — 기업이 '노출된 시장'의 유찰률·재입찰률. 부호를 붙이지 않는다.

    기업 단위 유찰은 관측되지 않으므로 (기업 역량비중 × 카테고리 유찰률) 로 노출도를 만든다.
    """
    b = events[events["stage"] == "BID"].copy()
    if not len(b):
        return pd.DataFrame(columns=[firm_col, "month"])
    st = b.get("status_raw", pd.Series("", index=b.index)).astype(str)
    b["is_failed"] = st.str.contains("유찰", na=False)
    b["is_rebid"] = st.str.contains("재입찰|재공고", regex=True, na=False)
    b["month"] = pd.to_datetime(b["available_at"]) + pd.offsets.MonthEnd(0)
    cat = (b.groupby(["category_cd", "month"], as_index=False, observed=True)
           .agg(fail_rate=("is_failed", "mean"), rebid_rate=("is_rebid", "mean"),
                n_bid=("is_failed", "size")))
    if capability is None or not len(capability):
        return cat.rename(columns={"category_cd": "category_cd"})
    M = capability[[firm_col, "category_cd", "month", "capability"]].merge(
        cat, on=["category_cd", "month"], how="left")
    M["_f"] = M["capability"] * M["fail_rate"]
    M["_r"] = M["capability"] * M["rebid_rate"]
    return (M.groupby([firm_col, "month"], as_index=False, observed=True)
            .agg(FAIL_RATE_exposure=("_f", "sum"), REBID_RATE_exposure=("_r", "sum")))


def win_conversion(events: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """§38 — wins / participated_bids.

    참여업체 전체정보가 복원되지 않으면 승자만으로 가짜 conversion rate 를 만들지 않는다.
    그런 경우 NOT_IDENTIFIABLE 한 줄만 반환한다.
    """
    part_cols = [c for c in ("participant_bizno", "prcbdr_bizno", "bidder_bizno")
                 if c in events.columns]
    if not part_cols:
        LOG.warn("입찰 참여업체 명부가 없습니다 → WIN_CONVERSION = NOT_IDENTIFIABLE (§38). "
                 "승자만으로 전환율을 만들지 않습니다.")
        return pd.DataFrame([{"status": "NOT_IDENTIFIABLE",
                              "reason": "참여업체 전체정보 부재 — 승자편향 전환율 생성 금지(§38)"}])
    p = events.dropna(subset=part_cols[:1])
    won = p.get("award_rank", pd.Series(np.nan, index=p.index)) == 1
    return (p.assign(won=won).groupby(part_cols[0], as_index=False)
            .agg(participated=("won", "size"), wins=("won", "sum"))
            .assign(WIN_CONVERSION=lambda d: d["wins"] / d["participated"].replace(0, np.nan)))


def pipeline_conversion(events: pd.DataFrame) -> pd.DataFrame:
    """§39 — category/agency 단위 단계전환율. 기업단위보다 이 수준에서 측정한다."""
    if not len(events):
        return pd.DataFrame()
    st = (events.groupby(["opportunity_id", "stage"], as_index=False, observed=True)
          .agg(t=("available_at", "min")))
    piv = st.pivot_table(index="opportunity_id", columns="stage", values="t", aggfunc="min")
    attrs = (events.sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False)
             .agg(category_cd=("category_cd", "first"), agency_cd=("agency_cd", "first"),
                  proc_type=("proc_type", "first")))
    P = attrs.merge(piv.reset_index(), on="opportunity_id", how="left")
    pairs = [("PLAN", "BID", "plan_to_bid"), ("PRESPEC", "BID", "prespec_to_bid"),
             ("BID", "AWARD", "bid_to_award"), ("AWARD", "CONTRACT", "award_to_contract")]
    rows = []
    for src, dst, nm in pairs:
        if src not in P.columns:
            continue
        has_src = P[src].notna()
        has_dst = P[dst].notna() if dst in P.columns else pd.Series(False, index=P.index)
        g = (P[has_src].assign(_ok=has_dst[has_src].astype(float))
             .groupby(["proc_type"], as_index=False, observed=True)
             .agg(n=("_ok", "size"), rate=("_ok", "mean")))
        g["transition"] = nm
        rows.append(g)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
