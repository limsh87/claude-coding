# -*- coding: utf-8 -*-
"""PIT 투자 유니버스.   §49 · §50 · §51 · §57

  · 상장폐지 종목을 제거한 현재 종목목록을 과거 전체 기간에 쓰지 않는다(§3.2 §57).
  · 조달기업만으로 universe 를 사후 정의하지 않는다 — All tradable 과
    PIT procurement-observable 을 각각 보고한다(§50).
  · 매월 커버리지 게이트를 출력한다(§51). 미달이면 성과와 무관하게 SAMPLE_COLLAPSE.

가격 원천 우선순위 (캐시활용 최우선)
  ① 사용자의 PIT 한국주식 가격 DB (공용 인덱스 krx_ohlcv_daily / security_master)
  ② 없으면 SMOKE 합성 시장
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import to_code6, as_ts_series
from core.vault import get_vault
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

EXCLUDE_NAME_PAT = r"스팩|SPAC|우선주|리츠|REIT|ETN|상장지수"


def load_market_panel(months: pd.DatetimeIndex) -> Optional[pd.DataFrame]:
    """공용 인덱스의 일봉 → 월말 패널. 사용자가 이미 가진 PIT 가격 DB 를 그대로 재사용한다."""
    V = get_vault()
    px = V.get_table(CFG.SHARED_REUSE_TABLES["price"], scope="shared")
    if px is None or not len(px):
        LOG.warn("공용 인덱스에 krx_ohlcv_daily 가 없습니다 — SMOKE 합성 시장으로 진행합니다.")
        return None
    d = px.copy()
    cols = {c.lower(): c for c in d.columns}
    pick = lambda *n: next((cols[x] for x in n if x in cols), None)
    c_code, c_date = pick("code", "stock_code", "ticker"), pick("date", "dt", "trade_date")
    c_close = pick("adj_close", "close", "종가")
    if not all((c_code, c_date, c_close)):
        LOG.warn(f"krx_ohlcv_daily 스키마를 해석하지 못했습니다 (code={c_code}, date={c_date}, "
                 f"close={c_close}) — 합성 시장으로 진행합니다.")
        return None
    d["stock_code"] = d[c_code].map(to_code6)
    d["date"] = as_ts_series(d[c_date])
    d = d.dropna(subset=["stock_code", "date"])
    d["month"] = d["date"] + pd.offsets.MonthEnd(0)
    c_shares = pick("shares_outstanding", "shares", "listed_shares", "상장주식수")
    c_val = pick("turnover_value", "value", "거래대금", "amount")
    agg = {"close": (c_close, "last")}
    if c_shares:
        agg["shares"] = (c_shares, "last")
    if c_val:
        agg["turnover_value"] = (c_val, "mean")
    M = d.groupby(["stock_code", "month"], as_index=False, observed=True).agg(**agg)
    M = M.sort_values(["stock_code", "month"], kind="stable")
    M["ret"] = M.groupby("stock_code", observed=True)["close"].pct_change()
    M["mcap"] = M["close"] * M["shares"] if "shares" in M.columns else np.nan
    sm = V.get_table(CFG.SHARED_REUSE_TABLES["security_master"], scope="shared")
    if sm is not None and len(sm):
        s = sm.copy()
        idc = [c for c in s.columns if c.lower() in ("code", "stock_code", "ticker")]
        if idc:
            s["stock_code"] = s[idc[0]].map(to_code6)
            keep = [c for c in s.columns if c.lower() in
                    ("market", "sector", "name", "listing_date", "delisting_date")]
            M = M.merge(s[["stock_code"] + keep].drop_duplicates("stock_code"),
                        on="stock_code", how="left")
    LOG.ok(f"공용 캐시 가격 패널 재사용: {M['stock_code'].nunique():,}종목 × {len(M):,}행")
    return M[M["month"].isin(months)]


def build_universe(market: pd.DataFrame, months: pd.DatetimeIndex,
                   min_turnover: float = 3e8) -> pd.DataFrame:
    """PIT 유니버스 판정. 각 게이트에서 몇 종목이 떨어지는지 반드시 남긴다(§51)."""
    m = market.copy()
    if "month" not in m.columns:
        raise KeyError("market 패널에 month 가 없습니다.")
    m["in_listed"] = True
    nm = m.get("name", pd.Series("", index=m.index)).astype(str)
    m["not_excluded"] = ~nm.str.contains(EXCLUDE_NAME_PAT, regex=True, na=False)
    tv = pd.to_numeric(m.get("turnover_value"), errors="coerce")
    m["liquid"] = tv.isna() | (tv >= min_turnover)     # 거래대금 정보가 없으면 배제하지 않는다
    m["has_price"] = pd.to_numeric(m.get("ret"), errors="coerce").notna()
    m["in_universe"] = m["in_listed"] & m["not_excluded"] & m["liquid"] & m["has_price"]
    return m


def universe_decay_table(u: pd.DataFrame) -> pd.DataFrame:
    """어느 게이트에서 표본이 붕괴하는지 — 선택편향 감사표."""
    gates = ["in_listed", "not_excluded", "liquid", "has_price", "in_universe"]
    rows, prev = [], None
    for g in gates:
        if g not in u.columns:
            continue
        n = int(u[g].sum())
        rows.append({"게이트": g, "통과 관측": n,
                     "직전 대비 감소": (prev - n) if prev is not None else 0})
        prev = n
    return pd.DataFrame(rows)


def procurement_observable(events: pd.DataFrame, months: pd.DatetimeIndex,
                           firm_col: str = "stock_code") -> pd.DataFrame:
    """§50 — t 시점까지 낙찰이 '관측된' 기업. 현재 명단을 과거에 소급하지 않는다."""
    a = events[(events["stage"].isin(["AWARD", "CONTRACT"])) & events[firm_col].notna()]
    if not len(a):
        return pd.DataFrame(columns=[firm_col, "month", "observable"])
    first = (a.groupby(firm_col, observed=True)["available_at"].min()
             .rename("first_observed_at").reset_index())
    first["first_month"] = pd.to_datetime(first["first_observed_at"]) + pd.offsets.MonthEnd(0)
    grid = first.merge(pd.DataFrame({"month": months}), how="cross")
    grid = grid[grid["month"] >= grid["first_month"]]
    grid["observable"] = True
    return grid[[firm_col, "month", "observable"]]


def coverage_gate(F: pd.DataFrame, score_col: str, universe: Optional[pd.DataFrame],
                  top_pct: float = 0.20, gates: Optional[dict] = None) -> Tuple[pd.DataFrame, dict]:
    """§51 — 매월 universe_N / mapped_N / scored_N / top_bucket_N 과 median·p10·min."""
    gates = gates or {"median_scored_firms_min": 100, "p10_scored_firms_min": 60,
                      "median_holdings_min": 20}
    if universe is not None and len(universe) and "in_universe" in universe.columns:
        u = (universe[universe["in_universe"]].groupby("month", observed=True)["stock_code"]
             .nunique().rename("universe_N"))
    else:
        u = pd.Series(dtype=int, name="universe_N")
    mapped = (F.dropna(subset=["stock_code"]).groupby("month", observed=True)["stock_code"]
              .nunique().rename("mapped_firms_N"))
    sc = F.dropna(subset=[score_col])
    scored = sc.groupby("month", observed=True)["stock_code"].nunique().rename("scored_firms_N")
    top = (scored * top_pct).apply(np.floor).rename("top_bucket_N")
    T = pd.concat([u, mapped, scored, top], axis=1).fillna(0).astype(int).reset_index(
        names="month")
    stat = lambda s: {"median": float(np.median(s)) if len(s) else 0.0,
                      "p10": float(np.percentile(s, 10)) if len(s) else 0.0,
                      "min": float(np.min(s)) if len(s) else 0.0}
    nz = T[T["scored_firms_N"] > 0]
    res = {"universe": stat(T["universe_N"]), "scored": stat(nz["scored_firms_N"]),
           "top_bucket": stat(nz["top_bucket_N"]), "months": len(T),
           "months_with_scores": len(nz)}
    res["pass_median_scored"] = bool(res["scored"]["median"] >= gates["median_scored_firms_min"])
    res["pass_p10_scored"] = bool(res["scored"]["p10"] >= gates["p10_scored_firms_min"])
    res["pass_median_holdings"] = bool(res["top_bucket"]["median"] >= gates["median_holdings_min"])
    res["verdict"] = ("PASS" if all((res["pass_median_scored"], res["pass_p10_scored"],
                                     res["pass_median_holdings"])) else "SAMPLE_COLLAPSE")
    return T, res
