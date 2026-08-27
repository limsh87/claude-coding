# -*- coding: utf-8 -*-
"""기업 실행력 — WIN_REALIZATION 계열.   §25 · §26 · §27 · §30 · §31 · §32

  §25 award_amount_3M / 6M / 12M, contract_amount_12M
  §26 반드시 기업크기로 정규화: WIN_MCAP = award/PIT_market_cap, WIN_SALES = award/PIT_last_known_sales
      매출은 t 시점에 '공개된' 마지막 DART 재무제표만 쓴다(§58) — 미래 사업보고서 소급 금지.
  §27 낙찰 가속도 — 두 산식을 모두 산출하되 PRIMARY 는 사전등록에서 하나만 동결.
  §30 NEW_AGENCY (과거 36M 미거래 기관), §31 NEW_CATEGORY (36M clean history 필수)
  §32 REPEAT_WIN_RATE (기관×품목)

수요가 늘어도 회사가 못 따내면 의미가 없다 — 이 축이 W 다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import safe_div
from features.capability import _decay_expand
# ── /PACKAGE IMPORTS ──

from typing import Optional, Sequence

import numpy as np
import pandas as pd


def _monthly_firm(events: pd.DataFrame, stage: str, months: pd.DatetimeIndex,
                  firm_col: str, amount_col: str) -> pd.DataFrame:
    e = events[(events["stage"] == stage) & events[firm_col].notna() & events[amount_col].notna()]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month", "amt", "n"])
    e = e.copy()
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    g = (e.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(amt=(amount_col, "sum"), n=(amount_col, "size")))
    return g[g["month"].isin(months)]


def _dense(panel: pd.DataFrame, months: pd.DatetimeIndex, firm_col: str,
           value_cols: Sequence[str]) -> pd.DataFrame:
    if not len(panel):
        return pd.DataFrame(columns=[firm_col, "month"] + list(value_cols))
    firms = pd.Index(pd.unique(panel[firm_col]))
    grid = pd.MultiIndex.from_product([firms, months], names=[firm_col, "month"]).to_frame(index=False)
    out = grid.merge(panel, on=[firm_col, "month"], how="left")
    for c in value_cols:
        out[c] = out[c].fillna(0.0)
    return out.sort_values([firm_col, "month"], kind="stable").reset_index(drop=True)


def build_win_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                       firm_col: str = "stock_code",
                       amount_col: str = "attributed_amount") -> pd.DataFrame:
    """수주 실현 피처 (기업×월). 전부 groupby+rolling 벡터화."""
    aw = _monthly_firm(events, "AWARD", months, firm_col, amount_col)
    ct = _monthly_firm(events, "CONTRACT", months, firm_col, amount_col)
    if not len(aw) and not len(ct):
        LOG.warn("낙찰/계약 이벤트가 없어 WIN 피처를 만들 수 없습니다.")
        return pd.DataFrame(columns=[firm_col, "month"])
    A = _dense(aw.rename(columns={"amt": "award_amt", "n": "award_n"}), months, firm_col,
               ["award_amt", "award_n"])
    if len(ct):
        C = _dense(ct.rename(columns={"amt": "contract_amt", "n": "contract_n"}), months, firm_col,
                   ["contract_amt", "contract_n"])
        W = A.merge(C, on=[firm_col, "month"], how="outer")
    else:
        W = A.assign(contract_amt=0.0, contract_n=0.0)
    for c in ("award_amt", "award_n", "contract_amt", "contract_n"):
        W[c] = W[c].fillna(0.0)
    W = W.sort_values([firm_col, "month"], kind="stable")
    g = W.groupby(firm_col, sort=False, observed=True)
    for w in (3, 6, 12):
        W[f"award_amt_{w}m"] = g["award_amt"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
        W[f"award_n_{w}m"] = g["award_n"].transform(lambda s, w=w: s.rolling(w, min_periods=1).sum())
    W["contract_amt_12m"] = g["contract_amt"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    W["award_amt_ttm"] = W["award_amt_12m"]

    # §27 두 가지 가속도 산식 — PRIMARY 는 preregistration 에서 하나만 고른다
    W["award_amt_prev9m"] = g["award_amt"].transform(
        lambda s: s.shift(3).rolling(9, min_periods=3).sum())
    W["win_accel_rate"] = (W["award_amt_3m"] / 3.0) - (W["award_amt_prev9m"] / 9.0)
    W["award_ttm_lag12"] = g["award_amt_ttm"].transform(lambda s: s.shift(12))
    W["win_accel_log"] = np.log1p(W["award_amt_ttm"].clip(lower=0)) - \
                         np.log1p(W["award_ttm_lag12"].clip(lower=0))
    return W.reset_index(drop=True)


def add_size_normalization(W: pd.DataFrame, market: Optional[pd.DataFrame],
                           pit_sales: Optional[pd.DataFrame], firm_col: str = "stock_code"
                           ) -> pd.DataFrame:
    """§26 — WIN_MCAP / WIN_SALES. 매출은 §58 에 따라 '그 시점에 공개된' 것만 쓴다."""
    out = W.copy()
    if market is not None and len(market):
        mk = market[[firm_col, "month", "mcap"]].dropna()
        out = out.merge(mk, on=[firm_col, "month"], how="left")
        out["WIN_MCAP"] = safe_div(out["award_amt_12m"], out["mcap"])
        out["WIN_MCAP_3M"] = safe_div(out["award_amt_3m"], out["mcap"])
        out["CONTRACT_MCAP"] = safe_div(out["contract_amt_12m"], out["mcap"])
    else:
        out["WIN_MCAP"] = np.nan
        LOG.warn("시가총액이 없어 WIN_MCAP(§26)을 계산할 수 없습니다.")
    if pit_sales is not None and len(pit_sales):
        s = pit_sales.sort_values("filing_ts", kind="stable")
        left = out.sort_values("month", kind="stable")
        # merge_asof: month 시점에 이미 '접수'된 마지막 재무제표만 붙는다 (§58)
        out = pd.merge_asof(left, s[[firm_col, "filing_ts", "revenue"]].rename(
            columns={"filing_ts": "sales_filing_ts", "revenue": "pit_revenue"}),
            left_on="month", right_on="sales_filing_ts", by=firm_col, direction="backward",
            allow_exact_matches=True)
        out["WIN_SALES"] = safe_div(out["award_amt_12m"], out["pit_revenue"])
        out["CONTRACT_SALES"] = safe_div(out["contract_amt_12m"], out["pit_revenue"])
    else:
        out["WIN_SALES"] = np.nan
        LOG.warn("PIT 매출이 없어 WIN_SALES(§26)를 계산할 수 없습니다 — NOT_IDENTIFIABLE 로 보고합니다.")
    return out


def breadth_features(events: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code", lookback_m: int = 36,
                     recent_m: int = 12, amount_col: str = "attributed_amount") -> pd.DataFrame:
    """§30 NEW_AGENCY · §31 NEW_CATEGORY · §32 REPEAT_WIN.

    '신규'는 과거 36개월에 거래하지 않았던 기관/품목이다. 36M clean history 가 없는 기업에서는
    계산하지 않는다(§19 좌측절단) → warmed_up=False 로 표시하고 값을 NaN 으로 둔다.
    """
    e = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month"])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    e = e[e["month"].isin(months)]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "month"])
    e["amt"] = pd.to_numeric(e[amount_col], errors="coerce").fillna(0.0)

    rows = []
    for dim, col in (("agency", "agency_cd"), ("category", "category_cd")):
        o = (e.dropna(subset=[col]).groupby([firm_col, col, "month"], as_index=False, observed=True)
             .agg(amt=("amt", "sum")))
        if not len(o):
            continue
        # 최근 12M 거래 / 과거 36M 거래 (감쇠 없음 = halflife 무한)
        rec = _decay_expand(o.assign(one=1.0), [firm_col, col], months, recent_m, 1e9, "one", "n_recent")
        rec_amt = _decay_expand(o, [firm_col, col], months, recent_m, 1e9, "amt", "amt_recent")
        old = _decay_expand(o.assign(one=1.0), [firm_col, col], months, lookback_m + recent_m,
                            1e9, "one", "n_all")
        M = rec.merge(rec_amt, on=[firm_col, col, "month"], how="outer") \
               .merge(old, on=[firm_col, col, "month"], how="outer")
        for c in ("n_recent", "amt_recent", "n_all"):
            M[c] = M[c].fillna(0.0)
        # 과거 36M(=n_all - n_recent) 에 없었고 최근 12M 에 있으면 '신규'
        M["is_new"] = (M["n_recent"] > 0) & ((M["n_all"] - M["n_recent"]) <= 0)
        M["_act"] = (M["n_recent"] > 0).astype("int32")
        F = (M.groupby([firm_col, "month"], as_index=False, observed=True)
             .agg(**{f"new_{dim}_count": ("is_new", "sum"),
                     f"active_{dim}_count": ("_act", "sum")}))
        na = (M[M["is_new"]].groupby([firm_col, "month"], as_index=False, observed=True)
              .agg(**{f"new_{dim}_amt": ("amt_recent", "sum")}))
        tot = (M.groupby([firm_col, "month"], as_index=False, observed=True)
               .agg(**{f"tot_{dim}_amt": ("amt_recent", "sum")}))
        F = F.merge(na, on=[firm_col, "month"], how="left").merge(tot, on=[firm_col, "month"], how="left")
        F[f"new_{dim}_award_share"] = (F[f"new_{dim}_amt"].fillna(0.0) /
                                       F[f"tot_{dim}_amt"].replace(0, np.nan))
        rows.append(F)
    if not rows:
        return pd.DataFrame(columns=[firm_col, "month"])
    B = rows[0]
    for r in rows[1:]:
        B = B.merge(r, on=[firm_col, "month"], how="outer")

    # §32 REPEAT_WIN — 같은 (기관×품목)에서 이전 수주 이후 재수주한 비율
    pair = (e.dropna(subset=["agency_cd", "category_cd"])
            .groupby([firm_col, "agency_cd", "category_cd", "month"], as_index=False, observed=True)
            .agg(amt=("amt", "sum")))
    if len(pair):
        p_recent = _decay_expand(pair.assign(one=1.0), [firm_col, "agency_cd", "category_cd"],
                                 months, recent_m, 1e9, "one", "n_recent")
        p_all = _decay_expand(pair.assign(one=1.0), [firm_col, "agency_cd", "category_cd"],
                              months, lookback_m + recent_m, 1e9, "one", "n_all")
        PP = p_recent.merge(p_all, on=[firm_col, "agency_cd", "category_cd", "month"], how="outer")
        PP[["n_recent", "n_all"]] = PP[["n_recent", "n_all"]].fillna(0.0)
        PP["is_repeat"] = (PP["n_recent"] > 0) & ((PP["n_all"] - PP["n_recent"]) > 0)
        PP["is_active"] = PP["n_recent"] > 0
        R = (PP.groupby([firm_col, "month"], as_index=False, observed=True)
             .agg(repeat_pairs=("is_repeat", "sum"), active_pairs=("is_active", "sum")))
        R["REPEAT_WIN_RATE"] = R["repeat_pairs"] / R["active_pairs"].replace(0, np.nan)
        B = B.merge(R, on=[firm_col, "month"], how="outer")

    first = e.groupby(firm_col, observed=True)["month"].min().rename("first_award_month")
    B = B.merge(first, left_on=firm_col, right_index=True, how="left")
    msf = ((B["month"].dt.year - B["first_award_month"].dt.year) * 12 +
           (B["month"].dt.month - B["first_award_month"].dt.month))
    B["breadth_warmed_up"] = msf >= lookback_m
    for c in [c for c in B.columns if c.startswith(("new_", "REPEAT_"))]:
        B.loc[~B["breadth_warmed_up"], c] = np.nan       # §19 warm-up 없으면 계산하지 않는다
    LOG.ok(f"breadth 피처: {len(B):,}행 (warm-up 충족 {B['breadth_warmed_up'].mean() * 100:.0f}%)")
    return B.reset_index(drop=True)
