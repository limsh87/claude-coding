# -*- coding: utf-8 -*-
"""거래비용 — §59. 고정 0bp 백테스트를 최종성과로 쓰지 않는다.

  commission + 당시 제도의 증권거래세(매도) + bid-ask/slippage + market impact
  1× / 2× / 3× 스트레스 배수를 함께 산출한다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# 당시 제도 기준 매도 증권거래세(농특세 포함, bp). backtest_policy.yaml 과 같은 값.
SELL_TAX_SCHEDULE: List[dict] = [
    {"from": "2015-01-01", "KOSPI": 30.0, "KOSDAQ": 30.0},
    {"from": "2019-06-03", "KOSPI": 25.0, "KOSDAQ": 25.0},
    {"from": "2021-01-01", "KOSPI": 23.0, "KOSDAQ": 23.0},
    {"from": "2023-01-01", "KOSPI": 20.0, "KOSDAQ": 20.0},
    {"from": "2025-01-01", "KOSPI": 18.0, "KOSDAQ": 18.0},
]


def sell_tax_bps(months, market=None) -> pd.Series:
    """월별·시장별 매도세(bp). 현재 세율을 과거에 소급하지 않는다."""
    sch = pd.DataFrame(SELL_TAX_SCHEDULE)
    sch["from"] = pd.to_datetime(sch["from"])
    sch = sch.sort_values("from")
    ms = pd.Series(months)
    idx = np.searchsorted(sch["from"].to_numpy(),
                          pd.to_datetime(ms).to_numpy(), side="right") - 1
    idx = np.clip(idx, 0, len(sch) - 1)
    if market is None:
        return pd.Series(sch["KOSPI"].to_numpy()[idx], index=ms.index)
    mk = pd.Series(market).astype(str).str.upper()
    out = np.where(mk.str.contains("KOSDAQ").to_numpy(), sch["KOSDAQ"].to_numpy()[idx],
                   sch["KOSPI"].to_numpy()[idx])
    return pd.Series(out, index=ms.index)


def transaction_cost(weights_prev: pd.Series, weights_new: pd.Series, month,
                     market: Optional[pd.Series] = None, commission_bps: float = 1.5,
                     slippage_bps: float = 15.0, adv: Optional[pd.Series] = None,
                     portfolio_krw: float = 1e9, impact_coef: float = 10.0,
                     multiplier: float = 1.0) -> float:
    """한 리밸런싱의 총비용(포트폴리오 대비 비율). 세금은 매도에만 매긴다."""
    idx = weights_prev.index.union(weights_new.index)
    wp = weights_prev.reindex(idx).fillna(0.0)
    wn = weights_new.reindex(idx).fillna(0.0)
    d = wn - wp
    buy, sell = d.clip(lower=0), (-d).clip(lower=0)
    turn = float(buy.sum() + sell.sum())
    mk = market.reindex(idx) if market is not None else None
    tax = sell_tax_bps(pd.Series([month] * len(idx), index=idx), mk) / 1e4
    cost = (commission_bps / 1e4) * turn + float((sell * tax).sum()) + (slippage_bps / 1e4) * turn
    if adv is not None:
        a = pd.to_numeric(adv.reindex(idx), errors="coerce").replace(0, np.nan)
        participation = ((buy + sell) * portfolio_krw / a).clip(upper=1.0).fillna(0.0)
        cost += float(((impact_coef / 1e4) * np.sqrt(participation) * (buy + sell)).sum())
    return float(cost * multiplier)


def cost_table(turnover: pd.Series, gross: pd.Series, costs: pd.Series) -> pd.DataFrame:
    return pd.DataFrame([{"월평균 회전율": float(turnover.mean()),
                          "연환산 회전율": float(turnover.mean() * 12),
                          "월평균 비용(bp)": float(costs.mean() * 1e4),
                          "연환산 비용(%)": float(costs.mean() * 12 * 100),
                          "총수익(연,%)": float(gross.mean() * 12 * 100),
                          "순수익(연,%)": float((gross - costs).mean() * 12 * 100)}])
