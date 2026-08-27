# -*- coding: utf-8 -*-
"""PRIMARY FACTOR — Demand-Win Alignment.   §24 · §28 · §29 · §44

    P_D = 횡단면 백분위(정부수요 이동 D)   ∈ [0,1]
    P_W = 횡단면 백분위(실제 수주 증가 W)  ∈ [0,1]

    G2B_DWA = sqrt(P_D × P_W)

  기하평균이므로 두 신호가 **모두** 높아야 높다. hard filter 를 쓰지 않아 표본이 붕괴하지 않고,
  한 축만 극단적으로 높은 기업이 억제된다(§28).

§24 D1 = DS_YOY = log1p(EligibleDemandFlow_3M_t) − log1p(EligibleDemandFlow_3M_{t−12})
    D2 = ExpectedGovernmentPipeline_12M  (t 시점에 이미 공개되어 있고 미래에 집행될 파이프라인)
§44 raw / sector-neutral / sector+log(mcap)-neutral 세 버전을 모두 만든다. PRIMARY 는 세 번째.
§29 2×2 메커니즘 검정 버킷도 여기서 만든다 (파라미터 탐색 도구로 쓰지 않는다).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

EPS = 1e-12


def xsec_pct(F: pd.DataFrame, col: str, month_col: str = "month",
             min_n: int = 20) -> pd.Series:
    """월별 횡단면 백분위 [0,1]. 표본이 min_n 미만인 달은 NaN — 가짜 순위를 만들지 않는다."""
    if col not in F.columns:
        return pd.Series(np.nan, index=F.index)
    v = pd.to_numeric(F[col], errors="coerce")
    g = v.groupby(F[month_col], observed=True)
    r = g.rank(pct=True, method="average")
    n = g.transform("count")
    return r.where(n >= min_n)


def neutralize(F: pd.DataFrame, col: str, month_col: str = "month",
               sector_col: str = "sector", size_col: str = "mcap",
               mode: str = "sector_size") -> pd.Series:
    """§44 — raw / sector / sector_size 중립화. 월별 OLS 잔차(더미+log시총)를 벡터적으로 계산.

    조달수요는 건설·방산·IT서비스에 집중되므로, 중립화를 하지 않으면
    '정부조달 산업에 투자한 효과'를 '기업선별 알파'로 오인하게 된다.
    """
    y = pd.to_numeric(F[col], errors="coerce")
    if mode == "raw":
        return y
    out = pd.Series(np.nan, index=F.index)
    has_sec = sector_col in F.columns
    has_size = size_col in F.columns and mode == "sector_size"
    for _, idx in F.groupby(month_col, observed=True).indices.items():
        idx = np.asarray(idx)
        yy = y.to_numpy()[idx]
        ok = np.isfinite(yy)
        if ok.sum() < 10:
            continue
        parts = [np.ones((ok.sum(), 1))]
        if has_sec:
            sec = pd.Categorical(F[sector_col].to_numpy()[idx][ok])
            if len(sec.categories) > 1:
                D = np.zeros((ok.sum(), len(sec.categories) - 1))
                codes = sec.codes
                for j in range(1, len(sec.categories)):
                    D[:, j - 1] = (codes == j).astype(float)
                parts.append(D)
        if has_size:
            sz = pd.to_numeric(pd.Series(F[size_col].to_numpy()[idx][ok]), errors="coerce")
            sz = np.log(sz.clip(lower=1.0)).to_numpy()
            sz = np.nan_to_num(sz, nan=float(np.nanmean(sz)) if np.isfinite(sz).any() else 0.0)
            parts.append(sz.reshape(-1, 1))
        X = np.hstack(parts)
        try:
            beta, *_ = np.linalg.lstsq(X, yy[ok], rcond=None)
            res = yy[ok] - X @ beta
        except Exception:                                      # noqa: BLE001
            continue
        pos = idx[ok]
        out.iloc[pos] = res
    return out


def build_demand_axis(T: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """§24 — D1(신규공고 Flow YoY) 과 D2(Forward Pipeline)."""
    d = T.sort_values([firm_col, "month"], kind="stable").copy()
    g = d.groupby(firm_col, sort=False, observed=True)
    flow3 = d.get("eligible_demand_flow_3m")
    if flow3 is None:
        d["eligible_demand_flow_3m"] = 0.0
        flow3 = d["eligible_demand_flow_3m"]
    d["_l3"] = np.log1p(flow3.clip(lower=0))
    d["_l3_lag12"] = g["_l3"].shift(12)
    d["D1_DS_YOY"] = d["_l3"] - d["_l3_lag12"]
    pipe = d.get("eligible_pipeline_stock")
    d["D2_PIPELINE"] = np.log1p(pipe.clip(lower=0)) if pipe is not None else np.nan
    if pipe is not None:
        d["_lp"] = np.log1p(pipe.clip(lower=0))
        d["D2_PIPELINE_YOY"] = d["_lp"] - g["_lp"].shift(12)
    lofo = d.get("eligible_demand_flow_lofo")
    if lofo is not None:
        d["_ll"] = np.log1p(lofo.clip(lower=0))
        d["D1_DS_YOY_LOFO"] = d["_ll"] - g["_ll"].shift(12)
    return d.drop(columns=[c for c in ("_l3", "_l3_lag12", "_lp", "_ll") if c in d.columns])


def build_win_axis(W: pd.DataFrame, firm_col: str = "stock_code",
                   primary: str = "win_accel_log") -> pd.DataFrame:
    """§25~§27 — W 축. PRIMARY 산식은 preregistration 에서 하나만 동결한다."""
    d = W.copy()
    if primary not in d.columns:
        raise KeyError(f"W축 PRIMARY 산식 '{primary}' 이 피처에 없습니다. "
                       f"사용가능: {[c for c in d.columns if c.startswith('win_')]}")
    d["W_PRIMARY"] = pd.to_numeric(d[primary], errors="coerce")
    return d


def build_dwa(F: pd.DataFrame, demand_col: str = "D1_DS_YOY", win_col: str = "W_PRIMARY",
              month_col: str = "month", min_n: int = 20,
              neutral_mode: str = "sector_size") -> pd.DataFrame:
    """G2B_DWA = sqrt(P_D × P_W). raw/sector/sector_size 세 버전 모두 산출(§44)."""
    d = F.copy()
    d["_D_raw"] = pd.to_numeric(d[demand_col], errors="coerce")
    d["_W_raw"] = pd.to_numeric(d[win_col], errors="coerce")
    for mode, tag in (("raw", "raw"), ("sector", "sec"), ("sector_size", "secsz")):
        Dn = neutralize(d, "_D_raw", month_col, mode=mode)
        Wn = neutralize(d, "_W_raw", month_col, mode=mode)
        d[f"P_D_{tag}"] = xsec_pct(d.assign(_x=Dn), "_x", month_col, min_n)
        d[f"P_W_{tag}"] = xsec_pct(d.assign(_x=Wn), "_x", month_col, min_n)
        d[f"G2B_DWA_{tag}"] = np.sqrt(d[f"P_D_{tag}"].clip(0, 1) * d[f"P_W_{tag}"].clip(0, 1))
    tag = {"raw": "raw", "sector": "sec", "sector_size": "secsz"}[neutral_mode]
    d["P_D"] = d[f"P_D_{tag}"]
    d["P_W"] = d[f"P_W_{tag}"]
    d["G2B_DWA"] = d[f"G2B_DWA_{tag}"]
    n_ok = int(d["G2B_DWA"].notna().sum())
    LOG.ok(f"G2B_DWA 산출: {n_ok:,}개 기업×월 유효 (중립화={neutral_mode}, "
           f"D={demand_col}, W={win_col})")
    return d


def mechanism_2x2(F: pd.DataFrame, month_col: str = "month") -> pd.DataFrame:
    """§29 — Demand High/Low × Win High/Low 버킷. 진단용이며 파라미터 탐색에 쓰지 않는다."""
    d = F.dropna(subset=["P_D", "P_W"]).copy()
    if not len(d):
        return pd.DataFrame()
    d["D_hi"] = d["P_D"] >= 0.5
    d["W_hi"] = d["P_W"] >= 0.5
    d["bucket"] = np.where(d["D_hi"] & d["W_hi"], "D_high_W_high",
                    np.where(d["D_hi"] & ~d["W_hi"], "D_high_W_low",
                      np.where(~d["D_hi"] & d["W_hi"], "D_low_W_high", "D_low_W_low")))
    return d


def factor_family(F: pd.DataFrame) -> Dict[str, str]:
    """§84 최종 비교표에 들어갈 5개 팩터의 컬럼 매핑."""
    return {
        "1_Award_Amount_only": "award_amt_12m",
        "2_Award_over_MCap": "WIN_MCAP",
        "3_Demand_Shift_only": "D1_DS_YOY",
        "4_Win_Acceleration_only": "W_PRIMARY",
        "5_Demand_Win_Alignment": "G2B_DWA",
    }
