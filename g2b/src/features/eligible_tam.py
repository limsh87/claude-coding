# -*- coding: utf-8 -*-
"""Firm Eligible TAM 과 단계전환확률.   §21 · §22 · §23

    EligibleTAM(i,t) = Σ_c Capability(i,c,t) × GovernmentDemand(c,t)

  정교한 버전(§21):
    Σ_opportunity amount × capability_match × license_match × region_match × stage_probability

§22 발주계획 100억과 계약 100억을 같은 확률로 보지 않는다 → P(contract | stage) 를 곱한다.
§23 그 확률은 반드시 walk-forward 로 추정한다.
      · training_end < t
      · 아직 결과가 관측되지 않은 최근 건은 training label 에서 제거 (MATURITY_EMBARGO)
      · category → broad category → procurement type → global 로 hierarchical shrinkage
      · 표본이 작은 세부품목 확률을 직접 추정하지 않는다
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from graph.lifecycle import STAGE_RANK
from features.government_demand import PRE_AWARD_STAGES, opportunity_attrs
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_MATURITY_DAYS = 365      # §23 사전 동결 대상 — 실제 분포를 보고 정한 뒤 preregistration 에 고정
SHRINK_K = 25.0                  # 경험적 베이즈 축소 강도 (상위 계층으로 backoff)


def maturity_distribution(events: pd.DataFrame) -> pd.DataFrame:
    """단계 → 계약까지 걸린 실제 일수 분포. MATURITY_EMBARGO 를 '수익률 보기 전에' 정하는 근거."""
    ct = (events[events["stage"] == "CONTRACT"].sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False).agg(t_contract=("available_at", "min")))
    if not len(ct):
        return pd.DataFrame()
    rows = []
    for st in ("PLAN", "PRESPEC", "BID", "AWARD"):
        s = (events[events["stage"] == st].sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False).agg(t_stage=("available_at", "min")))
        if not len(s):
            continue
        m = s.merge(ct, on="opportunity_id", how="inner")
        d = (m["t_contract"] - m["t_stage"]).dt.total_seconds() / 86400.0
        d = d[d >= 0]
        if not len(d):
            continue
        rows.append({"stage": st, "표본": len(d), "p25": float(d.quantile(.25)),
                     "중앙값": float(d.median()), "p75": float(d.quantile(.75)),
                     "p90": float(d.quantile(.90)), "p95": float(d.quantile(.95))})
    return pd.DataFrame(rows)


def _labels(events: pd.DataFrame, maturity_days: int) -> pd.DataFrame:
    """단계별 (코호트, 결과, 라벨가용시각). 결과는 'maturity_days 안에 계약에 도달했는가'."""
    attrs = opportunity_attrs(events)
    ct = (events[events["stage"] == "CONTRACT"].sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False).agg(t_contract=("available_at", "min")))
    out = []
    for st in ("PLAN", "PRESPEC", "BID", "AWARD"):
        s = (events[events["stage"] == st].sort_values("available_at", kind="stable")
             .groupby("opportunity_id", as_index=False).agg(t_stage=("available_at", "min")))
        if not len(s):
            continue
        m = s.merge(ct, on="opportunity_id", how="left").merge(attrs, on="opportunity_id", how="left")
        horizon = m["t_stage"] + pd.Timedelta(days=maturity_days)
        m["outcome"] = (m["t_contract"].notna() & (m["t_contract"] <= horizon)).astype(float)
        # 라벨은 지평 도달 시점에야 확정된다. 그 전에 쓰면 미래를 보는 것이다.
        m["label_available_at"] = horizon
        m["stage"] = st
        out.append(m[["opportunity_id", "stage", "t_stage", "label_available_at", "outcome",
                      "category_cd", "broad_category", "proc_type"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _running(lbl: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """라벨가용시각 순 누적 (합, 건수). 이후 as-of 로 어느 시점에든 walk-forward 조회 가능."""
    keys = list(keys)
    d = lbl.sort_values("label_available_at", kind="stable").copy()
    g = d.groupby(keys, sort=False, observed=True)
    d["_s"] = g["outcome"].cumsum()
    d["_n"] = g.cumcount() + 1
    return (d[keys + ["label_available_at", "_s", "_n"]]
            .drop_duplicates(subset=keys + ["label_available_at"], keep="last"))


def stage_probability(events: pd.DataFrame, months: pd.DatetimeIndex,
                      maturity_days: int = DEFAULT_MATURITY_DAYS,
                      shrink_k: float = SHRINK_K) -> pd.DataFrame:
    """walk-forward P(contract | stage, category) — 계층 축소 포함.

    반환: [stage, category_cd, month, p_contract, n_train, p_source]
    각 month 에서 label_available_at <= month 인 라벨만 사용한다(§23).
    """
    lbl = _labels(events, maturity_days)
    if not len(lbl):
        return pd.DataFrame(columns=["stage", "category_cd", "month", "p_contract", "n_train"])
    lvl = {"cat": ["stage", "category_cd"], "broad": ["stage", "broad_category"],
           "ptype": ["stage", "proc_type"], "glob": ["stage"]}
    run = {k: _running(lbl, v) for k, v in lvl.items()}

    cells = lbl[["stage", "category_cd", "broad_category", "proc_type"]].drop_duplicates()
    grid = cells.merge(pd.DataFrame({"month": months}), how="cross")
    grid = grid.sort_values("month", kind="stable")
    for k, keys in lvl.items():
        r = run[k].sort_values("label_available_at", kind="stable")
        grid = pd.merge_asof(grid, r.rename(columns={"_s": f"s_{k}", "_n": f"n_{k}"}),
                             left_on="month", right_on="label_available_at", by=keys,
                             direction="backward", allow_exact_matches=True)
        grid = grid.drop(columns=["label_available_at"])
        grid[f"s_{k}"] = grid[f"s_{k}"].fillna(0.0)
        grid[f"n_{k}"] = grid[f"n_{k}"].fillna(0.0)

    # 위에서부터 내려오며 축소: global → ptype → broad → category
    p = np.where(grid["n_glob"] > 0, grid["s_glob"] / grid["n_glob"].replace(0, np.nan), 0.5)
    p = pd.Series(p, index=grid.index).fillna(0.5)
    for k in ("ptype", "broad", "cat"):
        s, n = grid[f"s_{k}"], grid[f"n_{k}"]
        p = (s + shrink_k * p) / (n + shrink_k)
    grid["p_contract"] = p.clip(0.0, 1.0)
    grid["n_train"] = grid["n_cat"]
    grid["p_source"] = np.where(grid["n_cat"] >= 30, "category",
                                np.where(grid["n_broad"] >= 30, "broad",
                                         np.where(grid["n_ptype"] >= 30, "proc_type", "global")))
    out = grid[["stage", "category_cd", "month", "p_contract", "n_train", "p_source"]]
    LOG.ok(f"단계전환확률(walk-forward, embargo {maturity_days}일): {len(out):,}행 · "
           f"평균 P(계약|BID)={out.loc[out['stage'] == 'BID', 'p_contract'].mean():.3f}")
    return out.reset_index(drop=True)


def stage_weighted_demand(lad: pd.DataFrame, sprob: pd.DataFrame,
                          months: pd.DatetimeIndex) -> pd.DataFrame:
    """단계확률 가중 정부수요 — (category × month). §22 의 구현.

    발주계획 단계의 100억은 P(contract|PLAN) 만큼만 수요로 센다.
    """
    if not len(lad):
        return pd.DataFrame(columns=["category_cd", "month", "demand_flow_w", "pipeline_w"])
    d = lad.copy()
    if len(sprob):
        d = d.merge(sprob[["stage", "category_cd", "month", "p_contract"]],
                    on=["stage", "category_cd", "month"], how="left")
        d["p_contract"] = d["p_contract"].fillna(d.groupby("stage")["p_contract"].transform("mean"))
    else:
        d["p_contract"] = 1.0
    d["p_contract"] = d["p_contract"].fillna(1.0)
    d["demand_flow_w"] = d["demand_flow"] * d["p_contract"]
    out = (d.groupby(["category_cd", "month"], as_index=False, observed=True)
           .agg(demand_flow_w=("demand_flow_w", "sum")))
    return out


def build_eligible_tam(capability: pd.DataFrame, demand: pd.DataFrame,
                       firm_col: str = "stock_code",
                       demand_cols: Sequence[str] = ("demand_flow", "demand_flow_3m",
                                                     "demand_flow_12m", "pipeline_stock"),
                       lofo: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """pit/eligible_tam_monthly.parquet (§89).

    EligibleTAM(i,t) = Σ_c Capability(i,c,t) × Demand(c,t)
    벡터화: capability(firm,cat,month) ⨝ demand(cat,month) → groupby(firm,month) 합.
    """
    if capability is None or not len(capability) or demand is None or not len(demand):
        return pd.DataFrame(columns=[firm_col, "month"])
    use = [c for c in demand_cols if c in demand.columns]
    M = capability[[firm_col, "category_cd", "month", "capability", "decayed_award",
                    "warmed_up"]].merge(
        demand[["category_cd", "month"] + use], on=["category_cd", "month"], how="left")
    for c in use:
        M[c] = M[c].fillna(0.0)
        M["_w_" + c] = M["capability"].fillna(0.0) * M[c]
    if lofo is not None and len(lofo):
        M = M.merge(lofo, on=[firm_col, "category_cd", "month"], how="left")
        M["own_flow_known"] = M["own_flow_known"].fillna(0.0)
        # §45 자기 자신의 '이미 알려진' 낙찰건이 만든 수요는 그 기업의 TAM 에서 뺀다
        M["_w_demand_flow_lofo"] = (M["capability"].fillna(0.0) *
                                    (M["demand_flow"] - M["own_flow_known"]))
    # lambda 집계는 그룹 수만큼 파이썬 호출이 일어난다 → 미리 컬럼으로 만들고 sum 으로 끝낸다
    M["_active"] = (M["capability"].fillna(0.0) > 0.01).astype("int32")
    M["_cap2"] = M["capability"].fillna(0.0) ** 2
    agg = {("eligible_" + c): ("_w_" + c, "sum") for c in use}
    if "_w_demand_flow_lofo" in M.columns:
        agg["eligible_demand_flow_lofo"] = ("_w_demand_flow_lofo", "sum")
    T = (M.groupby([firm_col, "month"], as_index=False, observed=True)
         .agg(**agg, n_active_categories=("_active", "sum"),
              capability_hhi=("_cap2", "sum"), warmed_up=("warmed_up", "max")))
    LOG.ok(f"EligibleTAM: {T[firm_col].nunique():,}개 기업 × 월 = {len(T):,}행")
    return T
