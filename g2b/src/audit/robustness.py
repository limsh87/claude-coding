# -*- coding: utf-8 -*-
"""강건성 검사.   §65 ~ §73

  §65 전체 / 초기·중기·후기 1/3 / 연도별
  §66 Leave-One-Year-Out
  §67 Leave-One-Agency-Out        ← 이벤트를 지우고 피처를 다시 만든다(기관 제거는 수요도 바꾼다)
  §68 Leave-One-Category-Out      ← 같은 이유로 재구축
  §69 Mega contract 상위 0.1/0.5/1% 제거·윈저
  §70 상위 성과기여 1/3/5/10 종목 제거
  §71 시총버킷 · §72 시장(KOSPI/KOSDAQ) · §73 업종별 기여

재구축형 검사는 rebuild_fn(events)->scored_panel 콜백을 받는다.
'해당 기관을 뺐다'고 말하면서 피처는 그대로 두면 검사가 아니라 연출이다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from backtest.portfolio import build_portfolio
from backtest.statistics import perf_table, newey_west_t
# ── /PACKAGE IMPORTS ──

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _run(F: pd.DataFrame, score_col: str, ret_col: str, label: str,
         top_pct: float = 0.20, min_holdings: int = 10, **kw) -> pd.DataFrame:
    pf = build_portfolio(F, score_col, ret_col, top_pct=top_pct, min_holdings=min_holdings, **kw)
    if not len(pf["returns"]):
        return pd.DataFrame([{"구분": label, "관측월": 0, "판정": "표본부족"}])
    bm = F.dropna(subset=[ret_col]).groupby("month", observed=True)[ret_col].mean()
    R = pf["returns"].set_index("month")
    ex = (R["net_ret"] - bm.reindex(R.index)).dropna()
    t = perf_table(ex, label=label).iloc[0]
    return pd.DataFrame([{"구분": label, "관측월": int(t["관측월"]),
                          "순초과(연,%)": 100 * float(t["연환산수익"]),
                          "NW_t": float(t["NW_t"]), "MDD": float(t["MDD"]),
                          "적중률": float(t["적중률"]),
                          "평균보유": float(pf["returns"]["holdings"].mean())}])


def by_period(F: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """§65 — 전체 / 1·2·3분기간 / 연도별."""
    d = F.dropna(subset=[score_col, ret_col])
    if not len(d):
        return pd.DataFrame()
    months = np.sort(d["month"].unique())
    n = len(months)
    parts = [_run(d, score_col, ret_col, "전체")]
    for k, nm in ((0, "초기 1/3"), (1, "중기 1/3"), (2, "후기 1/3")):
        sel = months[int(n * k / 3): int(n * (k + 1) / 3)]
        parts.append(_run(d[d["month"].isin(sel)], score_col, ret_col, nm))
    for y, g in d.groupby(d["month"].dt.year):
        parts.append(_run(g, score_col, ret_col, f"{y}년"))
    return pd.concat(parts, ignore_index=True)


def leave_one_year_out(F: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """§66 — 특정 연도 의존 여부."""
    d = F.dropna(subset=[score_col, ret_col])
    parts = [_run(d, score_col, ret_col, "전체")]
    for y in sorted(d["month"].dt.year.unique()):
        parts.append(_run(d[d["month"].dt.year != y], score_col, ret_col, f"{y} 제외"))
    return pd.concat(parts, ignore_index=True)


def leave_one_out_rebuild(events: pd.DataFrame, rebuild_fn: Callable[[pd.DataFrame], pd.DataFrame],
                          score_col: str, ret_col: str, dim: str, top_k: int = 5,
                          amount_col: str = "amount") -> pd.DataFrame:
    """§67 · §68 — 상위 기관/품목을 하나씩 빼고 **피처를 다시 만들어** 재측정한다."""
    if dim not in events.columns:
        return pd.DataFrame()
    tot = (events.groupby(dim, observed=True)[amount_col].sum()
           .sort_values(ascending=False).head(top_k))
    base = rebuild_fn(events)
    parts = [_run(base, score_col, ret_col, "전체(재구축)")]
    for k in tot.index:
        sub = events[events[dim] != k]
        try:
            F = rebuild_fn(sub)
            parts.append(_run(F, score_col, ret_col, f"{dim}={k} 제외"))
        except Exception as e:                                 # noqa: BLE001
            parts.append(pd.DataFrame([{"구분": f"{dim}={k} 제외", "관측월": 0,
                                        "판정": f"재구축 실패 {type(e).__name__}"}]))
    return pd.concat(parts, ignore_index=True)


def mega_contract_sensitivity(events: pd.DataFrame,
                              rebuild_fn: Callable[[pd.DataFrame], pd.DataFrame],
                              score_col: str, ret_col: str,
                              quantiles: Sequence[float] = (0.001, 0.005, 0.01),
                              amount_col: str = "amount", mode: str = "drop") -> pd.DataFrame:
    """§69 — 상위 0.1/0.5/1% 계약을 제거(또는 윈저)하고 재측정."""
    parts = [_run(rebuild_fn(events), score_col, ret_col, "전체")]
    a = pd.to_numeric(events[amount_col], errors="coerce")
    for q in quantiles:
        thr = float(a.quantile(1 - q))
        if mode == "drop":
            sub = events[~(a > thr)]
            lab = f"상위 {q * 100:.1f}% 계약 제거"
        else:
            sub = events.copy()
            sub[amount_col] = a.clip(upper=thr)
            lab = f"상위 {q * 100:.1f}% 윈저"
        try:
            parts.append(_run(rebuild_fn(sub), score_col, ret_col, lab))
        except Exception as e:                                 # noqa: BLE001
            parts.append(pd.DataFrame([{"구분": lab, "관측월": 0,
                                        "판정": f"재구축 실패 {type(e).__name__}"}]))
    return pd.concat(parts, ignore_index=True)


def drop_top_contributors(F: pd.DataFrame, score_col: str, ret_col: str,
                          ks: Sequence[int] = (1, 3, 5, 10)) -> pd.DataFrame:
    """§70 — 성과기여 상위 종목을 빼도 살아남는가."""
    pf = build_portfolio(F, score_col, ret_col)
    if not len(pf["holdings"]):
        return pd.DataFrame()
    H = pf["holdings"]
    contrib = (H.assign(_c=H["w"] * H[ret_col]).groupby("stock_code", observed=True)["_c"]
               .sum().sort_values(ascending=False))
    parts = [_run(F, score_col, ret_col, "전체")]
    for k in ks:
        drop = set(contrib.head(k).index)
        parts.append(_run(F[~F["stock_code"].isin(drop)], score_col, ret_col,
                          f"상위기여 {k}종목 제외"))
    return pd.concat(parts, ignore_index=True)


def by_bucket(F: pd.DataFrame, score_col: str, ret_col: str, col: str,
              n_bins: int = 4, labels: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """§71 §72 §73 — 시총버킷 / 시장 / 업종별."""
    d = F.dropna(subset=[score_col, ret_col])
    if col not in d.columns or not len(d):
        return pd.DataFrame()
    if pd.api.types.is_numeric_dtype(d[col]):
        lab = list(labels or ["Micro", "Small", "Mid", "Large"])[:n_bins]
        d = d.assign(_b=d.groupby("month", observed=True)[col].transform(
            lambda s: pd.qcut(s.rank(method="first"), min(n_bins, max(1, s.nunique())),
                              labels=lab[:min(n_bins, max(1, s.nunique()))], duplicates="drop")))
    else:
        d = d.assign(_b=d[col].astype(str))
    parts = []
    for b, g in d.groupby("_b", observed=True):
        parts.append(_run(g, score_col, ret_col, f"{col}={b}", min_holdings=5))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def cost_stress(F: pd.DataFrame, score_col: str, ret_col: str,
                multipliers: Sequence[float] = (1.0, 2.0, 3.0)) -> pd.DataFrame:
    """§59 — 비용 1×/2×/3× 스트레스."""
    return pd.concat([_run(F, score_col, ret_col, f"비용 {m:g}×", cost_multiplier=m)
                      for m in multipliers], ignore_index=True)


def summarize(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """강건성 요약 — 몇 개 분할에서 양(+)이 유지되었나."""
    rows = []
    for name, T in tables.items():
        if T is None or not len(T) or "순초과(연,%)" not in T.columns:
            rows.append({"검사": name, "분할수": 0, "양수비율": np.nan, "최악": np.nan})
            continue
        v = pd.to_numeric(T[T["구분"] != "전체"]["순초과(연,%)"], errors="coerce").dropna()
        rows.append({"검사": name, "분할수": len(v),
                     "양수비율": float((v > 0).mean()) if len(v) else np.nan,
                     "최악": float(v.min()) if len(v) else np.nan,
                     "중앙값": float(v.median()) if len(v) else np.nan})
    return pd.DataFrame(rows)
