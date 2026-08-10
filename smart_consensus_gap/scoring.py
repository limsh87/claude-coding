# -*- coding: utf-8 -*-
"""횡단면 스코어링 (§9).

두 가지만 한다.
  1. composite 입력 전용으로 1%/99% 윈저라이즈 → z-score(기본) 또는 퍼센타일 랭크(강건성).
     ★ 원본 raw 값(SCG_RAW 등)은 절대 덮어쓰지 않는다(§6).
  2. 필요한 팩터가 하나라도 없으면 그 종목은 **후보에서 제외**한다. 0 으로 채우지 않는다(§9.1).

원문 7팩터는 모두 동일한 별(★) 가중이므로 합성은 동일가중 평균이다. 다만 '어떤 표준화로
합산했는지'는 원문에 없으므로 이 선택 자체가 재현 가정이며 config 에 태깅되어 있다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import FACTOR_DIRECTION, SCORER_RANK, SCORER_Z, SCGConfig
from .util import pct_rank, winsorize, zscore


def score_column(x: np.ndarray, cfg: SCGConfig) -> np.ndarray:
    v = winsorize(np.asarray(x, dtype=float), cfg.factor_winsor_lo, cfg.factor_winsor_hi)
    return zscore(v) if cfg.scorer == SCORER_Z else pct_rank(v)


def cross_section_scores(df: "pd.DataFrame", factors: Sequence[str], cfg: SCGConfig
                         ) -> "pd.DataFrame":
    """한 시점(asof) 안에서의 스코어. df 는 이미 단일 asof 로 필터되어 있어야 한다."""
    out = df.copy()
    if not len(out):
        for f in factors:
            out[f"score_{f}"] = np.array([], dtype=float)
        out["composite"] = np.array([], dtype=float)
        out["complete"] = np.array([], dtype=bool)
        return out

    complete = np.ones(len(out), dtype=bool)
    cols: List[np.ndarray] = []
    for f in factors:
        raw = out[f].to_numpy(dtype=float) if f in out.columns else np.full(len(out), np.nan)
        raw = raw * float(FACTOR_DIRECTION.get(f, 1))
        s = score_column(raw, cfg)
        out[f"score_{f}"] = s
        out[f"input_{f}"] = winsorize(raw, cfg.factor_winsor_lo, cfg.factor_winsor_hi)
        complete &= np.isfinite(raw)
        cols.append(s)

    #  동일가중 평균. 어차피 complete 가 아닌 행은 아래에서 NaN 이 되므로, 전부 NaN 인 열에서
    #  nanmean 경고가 뜨지 않도록 합/개수로 직접 계산한다.
    mat = np.vstack(cols) if cols else np.zeros((0, len(out)))
    if mat.size:
        fin = np.isfinite(mat)
        cnt = fin.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            comp = np.where(cnt > 0, np.where(fin, mat, 0.0).sum(axis=0) / np.maximum(cnt, 1), np.nan)
    else:
        comp = np.full(len(out), np.nan)
    comp = np.where(complete, comp, np.nan)      # 부족 팩터 자동대체 금지 (§9.1)
    out["composite"] = comp
    out["complete"] = complete
    return out


def score_all(fac: "pd.DataFrame", factors: Sequence[str], cfg: SCGConfig) -> "pd.DataFrame":
    if fac is None or not len(fac):
        return pd.DataFrame()
    parts = [cross_section_scores(g, factors, cfg) for _, g in fac.groupby("asof", observed=True)]
    return pd.concat(parts, ignore_index=True)


def rank_and_select(scored: "pd.DataFrame", n_holdings: int, score_col: str = "composite"
                    ) -> "pd.DataFrame":
    """시점별 내림차순 정렬 후 상위 N. 동점은 종목코드 오름차순으로 결정적으로 끊는다."""
    if scored is None or not len(scored):
        return pd.DataFrame()
    parts = []
    for t, g in scored.groupby("asof", observed=True):
        d = g[np.isfinite(g[score_col].to_numpy(dtype=float))].copy()
        d = d.sort_values([score_col, "company_code"], ascending=[False, True], kind="mergesort")
        d["rank"] = np.arange(1, len(d) + 1)
        d["selected"] = d["rank"] <= int(n_holdings)
        d["candidates_n"] = len(d)
        parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def strategy_score_column(strategy: str, cfg: SCGConfig) -> str:
    """SCG 단독 전략은 composite 대신 지정된 컬럼으로 정렬한다(§2 A/B)."""
    from .config import STRAT_SCG_SINGLE_RAW, STRAT_SCG_SINGLE_Z
    if strategy == STRAT_SCG_SINGLE_RAW:
        return "SCG_RAW"                    # 원형 그대로 내림차순 (윈저·표준화 없음)
    if strategy == STRAT_SCG_SINGLE_Z:
        return "composite"                  # 윈저 후 z-score 1개 팩터 = composite 와 동일
    return "composite"


__all__ = ["score_column", "cross_section_scores", "score_all", "rank_and_select",
           "strategy_score_column"]
