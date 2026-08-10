# -*- coding: utf-8 -*-
"""Stage 7 — 강건성 (§16) + 팩터 절제 (§15).

두 가지 규칙만 지키면 된다.
  1. 변형은 **사전 등록된 것만**, **한 번에 한 축만**. config.PREDEFINED_ROBUSTNESS_VARIANTS
     가 생성 시점에 이를 강제하므로 여기서는 그대로 순회하기만 한다.
  2. 결과 중 가장 좋은 것을 골라 공식 성과로 승격하지 않는다. 전부 출력하고, BASE 를 고정한다.

성능: 팩터 스냅샷 재계산이 필요한 축(컨센서스 재구성·유니버스)만 다시 만들고,
포트폴리오 축(N·스코어러·가중)은 **캐시된 스냅샷을 재사용**한다(§18 Stage 7).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import (FACTORS_5F_NO_SCG, FACTORS_6F, PREDEFINED_ROBUSTNESS_VARIANTS,
                     STRAT_5F_NO_SCG, STRAT_IBK_6F_PUBLIC, SCGConfig, variant_configs)
from .util import LOG, fmt_table

#  이 축들이 바뀌면 스마트 컨센서스/유니버스가 달라지므로 팩터를 다시 만들어야 한다.
RECOMPUTE_AXES = {"recency_half_life_days", "accuracy_max_events", "analyst_weight_cap",
                  "universe", "active_estimate_window_days", "twelve_mf_source"}

ROBUSTNESS_COLUMNS = ["variant_id", "axis", "override", "recomputed", "strategy", "n_rebalances",
                      "CAGR", "ann_vol", "Sharpe", "MDD", "excess_CAGR", "information_ratio",
                      "turnover_per_rebalance", "note"]


def run_robustness(cfg: SCGConfig, strategy: str,
                   factor_fn: Callable[[SCGConfig], "pd.DataFrame"],
                   evaluate_fn: Callable[[SCGConfig, "pd.DataFrame", str], Dict[str, Any]],
                   base_fac: "pd.DataFrame") -> "pd.DataFrame":
    rows: List[Dict[str, Any]] = []

    base_metrics = evaluate_fn(cfg, base_fac, strategy)
    rows.append(_row("BASE", "BASE", "-", False, strategy, base_metrics,
                     "기준 설정 (§25). 이 값이 공식 성과다."))

    for variant, vcfg in variant_configs(cfg):
        need = variant.axis in RECOMPUTE_AXES
        try:
            fac = factor_fn(vcfg) if need else base_fac
            m = evaluate_fn(vcfg, fac, strategy)
            note = variant.note
        except Exception as e:  # noqa: BLE001 — 한 변형의 실패가 전체를 죽이지 않게 한다
            m, note = {}, f"실패: {type(e).__name__}: {e}"
            LOG.warning(f"  변형 {variant.variant_id} 실패: {type(e).__name__}: {e}")
        ov = ", ".join(f"{k}={v}" for k, v in variant.overrides.items())
        rows.append(_row(variant.variant_id, variant.axis, ov, need, strategy, m, note))

    out = pd.DataFrame(rows).reindex(columns=ROBUSTNESS_COLUMNS)
    return out


def _row(vid: str, axis: str, override: str, recomputed: bool, strategy: str,
         m: Dict[str, Any], note: str) -> Dict[str, Any]:
    d = {"variant_id": vid, "axis": axis, "override": override, "recomputed": recomputed,
         "strategy": strategy, "note": note}
    for k in ("n_rebalances", "CAGR", "ann_vol", "Sharpe", "MDD", "excess_CAGR",
              "information_ratio", "turnover_per_rebalance"):
        d[k] = m.get(k, np.nan)
    return d


def factor_ablation(cfg: SCGConfig, base_fac: "pd.DataFrame",
                    evaluate_factors_fn: Callable[[SCGConfig, "pd.DataFrame", Sequence[str], str],
                                                  Dict[str, Any]]) -> "pd.DataFrame":
    """§15 — 6F vs 5F(SCG 제거). 나머지 팩터도 leave-one-out 으로 모두 출력한다.

    ★ '어느 조합이 제일 좋은지 고르기' 위한 표가 아니다. SCG 제거의 효과를 다른 팩터
      제거의 효과와 같은 자로 재기 위한 표다.
    """
    rows: List[Dict[str, Any]] = []
    full = evaluate_factors_fn(cfg, base_fac, FACTORS_6F, STRAT_IBK_6F_PUBLIC)
    rows.append({"spec": "6F_FULL", "removed": "-", "factors": ",".join(FACTORS_6F),
                 **_metrics_subset(full)})
    for f in FACTORS_6F:
        sub = tuple(x for x in FACTORS_6F if x != f)
        name = STRAT_5F_NO_SCG if sub == FACTORS_5F_NO_SCG else f"5F_NO_{f}"
        m = evaluate_factors_fn(cfg, base_fac, sub, name)
        rows.append({"spec": name, "removed": f, "factors": ",".join(sub), **_metrics_subset(m)})
    out = pd.DataFrame(rows)
    if len(out) and "CAGR" in out.columns:
        base_cagr = out.loc[out["spec"] == "6F_FULL", "CAGR"]
        base_ir = out.loc[out["spec"] == "6F_FULL", "information_ratio"]
        b1 = float(base_cagr.iloc[0]) if len(base_cagr) else np.nan
        b2 = float(base_ir.iloc[0]) if len(base_ir) else np.nan
        out["delta_CAGR_vs_full"] = out["CAGR"] - b1
        out["delta_IR_vs_full"] = out["information_ratio"] - b2
    return out


def _metrics_subset(m: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("n_rebalances", "CAGR", "ann_vol", "Sharpe", "Sortino", "MDD", "Calmar",
            "excess_CAGR", "information_ratio", "tracking_error", "turnover_per_rebalance",
            "hit_ratio_monthly")
    return {k: m.get(k, np.nan) for k in keys}


def log_robustness(rob: "pd.DataFrame") -> None:
    if rob is None or not len(rob):
        LOG.info("  (강건성 결과 없음)")
        return
    LOG.info(fmt_table(rob[["variant_id", "axis", "override", "recomputed", "CAGR", "Sharpe",
                            "MDD", "excess_CAGR"]], max_rows=30))
    LOG.info("  ※ 위 표에서 가장 좋은 변형을 골라 공식 성과로 쓰지 않는다(§16, §27). "
             "BASE 가 공식이다.")


__all__ = ["run_robustness", "factor_ablation", "log_robustness", "RECOMPUTE_AXES",
           "ROBUSTNESS_COLUMNS"]
