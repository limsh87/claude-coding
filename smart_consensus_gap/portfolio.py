# -*- coding: utf-8 -*-
"""포트폴리오 구성 (§11) + 회전율/비용 정의 (§13).

원문 재현에는 섹터 상한·변동성 가중·개별 종목 상한을 **추가하지 않는다**(§11).
실무형 변형이 필요하면 그것은 별도 전략이지 원문 재현이 아니다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import SCGConfig

HOLDING_COLUMNS = ["asof", "exec_date", "strategy", "variant_id", "mode", "company_code",
                   "rank", "score", "weight", "market_cap", "weight_scheme", "coverage_flag"]


def compute_weights(mcap: np.ndarray, scheme: str) -> np.ndarray:
    """시총가중(원문) 또는 동일가중(강건성). 시총 결측은 그 종목을 제외한다."""
    m = np.asarray(mcap, dtype=float)
    if scheme == "EQUAL":
        w = np.ones(len(m))
    else:
        w = np.where(np.isfinite(m) & (m > 0), m, np.nan)
    tot = np.nansum(w)
    if not np.isfinite(tot) or tot <= 0:
        return np.full(len(m), np.nan)
    return w / tot


def build_holdings(selected: "pd.DataFrame", rebal: "pd.DataFrame", cfg: SCGConfig,
                   strategy: str, mode: str, score_col: str = "composite") -> "pd.DataFrame":
    """리밸런싱별 목표 비중. 후보가 N 에 못 미치면 그대로 두고 coverage_flag 로 남긴다."""
    if selected is None or not len(selected):
        return pd.DataFrame(columns=HOLDING_COLUMNS)
    exec_map = dict(zip(rebal["signal_date"], rebal["exec_date"]))
    parts = []
    for t, g in selected[selected["selected"]].groupby("asof", observed=True):
        g = g.sort_values("rank", kind="mergesort").copy()
        w = compute_weights(g["market_cap"].to_numpy(dtype=float), cfg.portfolio_weight)
        keep = np.isfinite(w)
        g = g.loc[keep].copy()
        w = w[keep]
        if len(g) and np.nansum(w) > 0:
            w = w / np.nansum(w)
        g["weight"] = w
        g["asof"] = t
        g["exec_date"] = exec_map.get(t, pd.NaT)
        g["strategy"] = strategy
        g["variant_id"] = cfg.variant_id
        g["mode"] = mode
        g["weight_scheme"] = cfg.portfolio_weight
        g["score"] = g[score_col].to_numpy(dtype=float) if score_col in g.columns else np.nan
        g["coverage_flag"] = "OK" if len(g) >= int(cfg.n_holdings) else \
            f"SHORT_{len(g)}of{int(cfg.n_holdings)}"
        parts.append(g.reindex(columns=HOLDING_COLUMNS))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=HOLDING_COLUMNS)


def turnover(w_new: Dict[str, float], w_old_post: Dict[str, float]) -> float:
    """§13 — 0.5 * Σ|w_new − w_old_post_return|. 전량 교체 시 1.0."""
    keys = set(w_new) | set(w_old_post)
    return 0.5 * float(sum(abs(w_new.get(k, 0.0) - w_old_post.get(k, 0.0)) for k in keys))


def cost_of(turn: float, bps: float) -> float:
    """§13 — 편도 회전율 × bps."""
    return float(turn) * float(bps) / 10000.0


__all__ = ["compute_weights", "build_holdings", "turnover", "cost_of", "HOLDING_COLUMNS"]
