# -*- coding: utf-8 -*-
"""포트폴리오 구성과 백테스트 실행.   §53 · §55 · §56 · §57 · §59

  · 월말까지 공개된 데이터로 신호 → 다음 거래일부터 매매(T+1).
    구현상 신호월 t 의 성과는 t+1 월 수익률과 매칭한다. 같은 달 수익률을 절대 쓰지 않는다.
  · 미래수익률 진입점은 attach_forward_return() 하나뿐이고 잠금이 걸려 있다(§1.1).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from backtest.costs import transaction_cost
from backtest.statistics import perf_table, quantile_returns
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def attach_forward_return(F: pd.DataFrame, market: pd.DataFrame, firm_col: str = "stock_code",
                          month_col: str = "month", ret_col: str = "ret",
                          horizon: int = 1) -> pd.DataFrame:
    """t 월 신호 ↔ t+horizon 월 수익률. **미래수익률 진입점 — 잠금 통과 필수.**"""
    CFG.assert_returns_unlocked(f"forward_return(h={horizon})")
    mk = market[[firm_col, month_col, ret_col]].dropna(subset=[month_col]).copy()
    mk["_sig_month"] = ((pd.to_datetime(mk[month_col]) - pd.DateOffset(months=horizon))
                        + pd.offsets.MonthEnd(0))
    fwd = mk.rename(columns={ret_col: f"fwd_ret_{horizon}m"})[
        [firm_col, "_sig_month", f"fwd_ret_{horizon}m"]]
    out = F.merge(fwd, left_on=[firm_col, month_col], right_on=[firm_col, "_sig_month"],
                  how="left").drop(columns=["_sig_month"])
    return out


def build_portfolio(F: pd.DataFrame, score_col: str, ret_col: str, top_pct: float = 0.20,
                    weighting: str = "equal", month_col: str = "month",
                    firm_col: str = "stock_code", min_holdings: int = 10,
                    max_weight: float = 0.10, cost_multiplier: float = 1.0,
                    commission_bps: float = 1.5, slippage_bps: float = 15.0,
                    apply_costs: bool = True) -> Dict[str, pd.DataFrame]:
    """상위 top_pct Long-only 포트폴리오. 반환: returns / holdings / summary."""
    base = [month_col, firm_col, score_col, ret_col]
    extra = [c for c in ("market", "turnover_value", "mcap", "sector") if c in F.columns]
    d = F[[c for c in base if c in F.columns] + extra].dropna(subset=[score_col, ret_col])
    empty = {"returns": pd.DataFrame(), "holdings": pd.DataFrame(), "summary": pd.DataFrame()}
    if not len(d):
        return empty
    d = d.sort_values([month_col, score_col], ascending=[True, False], kind="stable").copy()
    d["rk"] = d.groupby(month_col, observed=True)[score_col].rank(ascending=False, method="first")
    d["n_month"] = d.groupby(month_col, observed=True)[score_col].transform("count")
    H = d[(d["rk"] <= np.maximum(np.floor(d["n_month"] * top_pct), min_holdings)) &
          (d["n_month"] >= min_holdings)].copy()
    if not len(H):
        return empty
    if weighting == "equal":
        H["w_raw"] = 1.0
    elif weighting == "rank":
        H["w_raw"] = H.groupby(month_col, observed=True)["rk"].transform("max") - H["rk"] + 1.0
    elif weighting == "cap":
        H["w_raw"] = pd.to_numeric(H.get("mcap"), errors="coerce").fillna(1.0)
    else:
        raise ValueError(f"알 수 없는 가중방식: {weighting}")
    H["w"] = H["w_raw"] / H.groupby(month_col, observed=True)["w_raw"].transform("sum")
    H["w"] = H["w"].clip(upper=max_weight)
    H["w"] = H["w"] / H.groupby(month_col, observed=True)["w"].transform("sum")

    gross = (H.assign(_x=H["w"] * H[ret_col]).groupby(month_col, as_index=False, observed=True)
             .agg(gross_ret=("_x", "sum"), holdings=("w", "size"), max_w=("w", "max")))
    rows: List[dict] = []
    prev = pd.Series(dtype=float)
    for mth, g in H.groupby(month_col, sort=True, observed=True):
        cur = g.set_index(firm_col)["w"]
        idx = cur.index.union(prev.index)
        turn = float((cur.reindex(idx).fillna(0.0) - prev.reindex(idx).fillna(0.0)).abs().sum())
        c = (transaction_cost(prev, cur, mth,
                              market=g.set_index(firm_col)["market"] if "market" in g else None,
                              commission_bps=commission_bps, slippage_bps=slippage_bps,
                              adv=g.set_index(firm_col)["turnover_value"]
                              if "turnover_value" in g else None,
                              multiplier=cost_multiplier) if apply_costs else 0.0)
        rows.append({month_col: mth, "turnover": turn, "cost": c})
        prev = cur
    R = gross.merge(pd.DataFrame(rows), on=month_col, how="left")
    R["cost"] = R["cost"].fillna(0.0)
    R["net_ret"] = R["gross_ret"] - R["cost"]
    summ = pd.concat([perf_table(R["gross_ret"], label=f"{score_col} gross"),
                      perf_table(R["net_ret"], label=f"{score_col} net")], ignore_index=True)
    summ["평균보유종목"] = float(R["holdings"].mean())
    summ["중앙보유종목"] = float(R["holdings"].median())
    summ["월평균회전율"] = float(R["turnover"].mean())
    return {"returns": R, "holdings": H, "summary": summ}


def benchmark_returns(F: pd.DataFrame, ret_col: str, month_col: str = "month") -> pd.Series:
    """유니버스 동일가중 벤치마크 — Q5-Universe 초과수익의 기준."""
    return F.dropna(subset=[ret_col]).groupby(month_col, observed=True)[ret_col].mean()


def run_backtest(F: pd.DataFrame, market: pd.DataFrame, score_col: str, top_pct: float = 0.20,
                 weighting: str = "equal", cost_multiplier: float = 1.0, horizon: int = 1,
                 quantiles: int = 5, min_holdings: int = 10) -> Dict[str, object]:
    """PRIMARY 백테스트 한 번의 전체 실행."""
    Fx = attach_forward_return(F, market, horizon=horizon)
    rc = f"fwd_ret_{horizon}m"
    pf = build_portfolio(Fx, score_col, rc, top_pct=top_pct, weighting=weighting,
                         cost_multiplier=cost_multiplier, min_holdings=min_holdings)
    qr, qt = quantile_returns(Fx, score_col, rc, q=quantiles)
    bm = benchmark_returns(Fx, rc)
    excess = pd.DataFrame()
    if len(pf["returns"]):
        R = pf["returns"].set_index("month")
        excess = pd.DataFrame({"gross_excess": R["gross_ret"] - bm.reindex(R.index),
                               "net_excess": R["net_ret"] - bm.reindex(R.index)}).dropna()
    return {"returns": pf["returns"], "holdings": pf["holdings"], "summary": pf["summary"],
            "quantile_returns": qr, "quantile_table": qt, "benchmark": bm,
            "excess": excess, "scored": Fx, "ret_col": rc}
