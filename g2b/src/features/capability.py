# -*- coding: utf-8 -*-
"""기업의 '잘하는 영역' — Capability(i,c,t).   §17 · §18 · §19

정의 (PRIMARY — 과거 계약·낙찰만 사용, 미래정보 없음)

    decayed(i,c,t) = Σ_{k: t-L < t_k <= t}  award(i,c,t_k) · λ^(t - t_k)
    Capability(i,c,t) = decayed(i,c,t) / Σ_c decayed(i,c,t)

  L = lookback (기본 36개월), λ = 0.5^(1/half_life)

§18 첫 수주 이전 기업은 capability 를 알 수 없다 → 억지 추론하지 않고 결측으로 둔다.
§19 NEW_CATEGORY_ENTRY / NEW_AGENCY_ENTRY 는 36M warm-up 이 없는 기업에서 계산하지 않는다.

벡터화: (firm,cat,month) 희소 관측을 36개월 영향창으로 한 번 전개한 뒤 groupby-sum 한다.
        기업 루프·월 루프가 없다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import month_range
# ── /PACKAGE IMPORTS ──

from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_LOOKBACK_M = 36
DEFAULT_HALFLIFE_M = 18.0


def award_observations(events: pd.DataFrame, amount_col: str = "attributed_amount",
                       stages: Sequence[str] = ("AWARD",),
                       firm_col: str = "stock_code") -> pd.DataFrame:
    """(firm, category, agency, month, amount) 희소 관측. available_at 기준 월 배정(§53)."""
    e = events[events["stage"].isin(stages)].copy()
    e = e[e[firm_col].notna() & e[amount_col].notna()]
    if not len(e):
        return pd.DataFrame(columns=[firm_col, "category_cd", "agency_cd", "month", "amount"])
    e["month"] = pd.to_datetime(e["available_at"]) + pd.offsets.MonthEnd(0)
    g = (e.groupby([firm_col, "category_cd", "agency_cd", "month"], as_index=False, observed=True)
         [amount_col].sum().rename(columns={amount_col: "amount"}))
    return g


def _decay_expand(obs: pd.DataFrame, key_cols: Sequence[str], months: pd.DatetimeIndex,
                  lookback_m: int, halflife_m: float, value_col: str = "amount",
                  out_col: str = "decayed") -> pd.DataFrame:
    """희소 관측 → 36개월 영향창 전개 → 감쇠 가중합. 결과는 (key..., month, decayed).

    exp 감쇠이므로 관측 t_k 는 t_k..t_k+L-1 개월에만 영향을 준다. 그 창만 전개한다.
    """
    key_cols = list(key_cols)
    if obs is None or not len(obs):
        return pd.DataFrame(columns=key_cols + ["month", out_col])
    midx = pd.Series(np.arange(len(months)), index=months)
    o = obs.copy()
    o["_mi"] = o["month"].map(midx)
    o = o.dropna(subset=["_mi"])
    if not len(o):
        return pd.DataFrame(columns=key_cols + ["month", out_col])
    o["_mi"] = o["_mi"].astype("int32")
    lam = 0.5 ** (1.0 / max(halflife_m, 1e-6))
    off = np.arange(lookback_m, dtype="int32")
    w = lam ** off
    n = len(o)
    rep_i = np.repeat(np.arange(n), lookback_m)
    tgt = o["_mi"].to_numpy()[rep_i] + np.tile(off, n)
    val = o[value_col].to_numpy()[rep_i] * np.tile(w, n)
    keep = tgt < len(months)
    D = pd.DataFrame({c: o[c].to_numpy()[rep_i][keep] for c in key_cols})
    D["_mi"] = tgt[keep]
    D[out_col] = val[keep]
    R = D.groupby(key_cols + ["_mi"], as_index=False, observed=True)[out_col].sum()
    R["month"] = months.to_numpy()[R["_mi"].to_numpy()]
    return R.drop(columns=["_mi"])


def build_capability(events: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                     lookback_m: int = DEFAULT_LOOKBACK_M,
                     halflife_m: float = DEFAULT_HALFLIFE_M,
                     stages: Sequence[str] = ("AWARD",)) -> pd.DataFrame:
    """pit/company_capability_monthly.parquet (§89).

    반환: [firm, category_cd, month, decayed_award, capability, firm_decayed_total,
           n_obs_36m, first_award_month, months_since_first_award, warmed_up]
    """
    obs = award_observations(events, amount_col, stages, firm_col)
    if not len(obs):
        LOG.warn("낙찰 관측이 없어 capability 를 만들 수 없습니다(§18 억지 추론 금지).")
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "capability"])
    dec = _decay_expand(obs, [firm_col, "category_cd"], months, lookback_m, halflife_m,
                        "amount", "decayed_award")
    cnt = _decay_expand(obs.assign(one=1.0), [firm_col, "category_cd"], months,
                        lookback_m, 1e9, "one", "n_obs_36m")     # halflife 무한 = 단순 건수
    C = dec.merge(cnt, on=[firm_col, "category_cd", "month"], how="left")
    C["firm_decayed_total"] = C.groupby([firm_col, "month"], observed=True)["decayed_award"].transform("sum")
    C["capability"] = C["decayed_award"] / C["firm_decayed_total"].replace(0, np.nan)

    first = obs.groupby(firm_col, observed=True)["month"].min().rename("first_award_month")
    C = C.merge(first, left_on=firm_col, right_index=True, how="left")
    C["months_since_first_award"] = (
        (C["month"].dt.year - C["first_award_month"].dt.year) * 12 +
        (C["month"].dt.month - C["first_award_month"].dt.month))
    C["warmed_up"] = C["months_since_first_award"] >= lookback_m     # §19
    LOG.ok(f"capability: {C[firm_col].nunique():,}개 기업 × {C['category_cd'].nunique():,}개 품목 "
           f"= {len(C):,}행 (lookback {lookback_m}M, 반감기 {halflife_m:.0f}M)")
    return C


def agency_capability(events: pd.DataFrame, months: pd.DatetimeIndex,
                      firm_col: str = "stock_code", amount_col: str = "attributed_amount",
                      lookback_m: int = DEFAULT_LOOKBACK_M,
                      halflife_m: float = DEFAULT_HALFLIFE_M) -> pd.DataFrame:
    """발주기관 축 역량 — §30 NEW_AGENCY 와 §33 집중도의 입력."""
    obs = award_observations(events, amount_col, ("AWARD",), firm_col)
    if not len(obs):
        return pd.DataFrame(columns=[firm_col, "agency_cd", "month", "decayed_award"])
    A = _decay_expand(obs, [firm_col, "agency_cd"], months, lookback_m, halflife_m,
                      "amount", "decayed_award")
    A["firm_decayed_total"] = A.groupby([firm_col, "month"], observed=True)["decayed_award"].transform("sum")
    A["agency_share"] = A["decayed_award"] / A["firm_decayed_total"].replace(0, np.nan)
    return A


def capability_persistence(C: pd.DataFrame, firm_col: str = "stock_code",
                           horizons: Sequence[int] = (12, 24, 36)) -> pd.DataFrame:
    """capability 가 실제로 지속적인지 진단 — 지속성이 없으면 '잘하는 영역' 개념 자체가 무너진다."""
    if C is None or not len(C):
        return pd.DataFrame()
    d = C[[firm_col, "category_cd", "month", "capability"]].dropna()
    rows = []
    for h in horizons:
        fut = d.copy()
        fut["month"] = fut["month"] - pd.DateOffset(months=h)
        m = d.merge(fut, on=[firm_col, "category_cd", "month"], suffixes=("", "_fwd"))
        if len(m) > 10:
            rows.append({"수평선(개월)": h, "표본": len(m),
                         "자기상관(Spearman)": float(m["capability"].corr(m["capability_fwd"],
                                                                        method="spearman"))})
    return pd.DataFrame(rows)
