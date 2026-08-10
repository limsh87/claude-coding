# -*- coding: utf-8 -*-
"""Stage 4 — 일반 컨센서스(§4) + PUBLIC_REPRO 스마트 컨센서스(§5) + Smart Gap(§6).

┌ 반드시 지켜야 하는 것 ──────────────────────────────────────────────────────────────┐
│ · 일반 컨센서스 = estimator 별 최신 1건의 **단순평균**. 가중평균이 아니다(§4).          │
│ · 최소 unique estimator 3명. 미달이면 컨센서스 자체가 결측이다(0으로 채우지 않는다).    │
│ · SCG_RAW = (smart - general) / general. 분모에 abs 를 씌우지 않는다(§0-4, §27).       │
│ · 스마트 컨센서스는 **역산 가능**해야 한다(§5.5, §28). 그래서 성분 감사표에 estimator   │
│   단위의 raw/adjusted/age/recency/skill/bias/final weight 를 전부 남긴다.             │
│ · 이것은 FnGuide 비공개 산식의 복제가 아니라 공개 원리 기반 재구성이다(§5.1).           │
└────────────────────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import (BIAS_CLIP, DENOM_NEAR_ZERO_TOL, EPS_NUMERIC_FLOOR, MIN_ANALYST_COUNT,
                     SCGConfig)
from .util import LOG, group_codes, group_sum, mad

MAX_CAP_ITERATIONS = 64

GENERAL_COLUMNS = ["asof", "company_code", "fiscal_period", "metric", "general_consensus",
                   "median", "std", "mad", "min", "max", "analyst_count", "broker_count",
                   "estimate_age_median", "sufficient"]

AUDIT_COLUMNS = ["asof", "company_code", "fiscal_period", "metric", "estimator_id",
                 "broker_name_norm", "analyst_name_norm", "published_at", "age_days",
                 "estimate_raw", "bias", "bias_scale", "estimate_adj", "w_recency", "skill",
                 "w_raw", "w_final", "n_events"]


# ════════════════════════════════════════════════════════════════════════════════════════
#  일반 컨센서스
# ════════════════════════════════════════════════════════════════════════════════════════
def general_consensus(snap: "pd.DataFrame", metric: str = "EPS",
                      min_analysts: int = MIN_ANALYST_COUNT) -> "pd.DataFrame":
    """estimator 별 최신 1건이 이미 골라진 스냅샷을 받아 (company, fiscal_period) 별 통계."""
    if snap is None or not len(snap):
        return pd.DataFrame(columns=GENERAL_COLUMNS)
    d = snap[snap["metric"] == metric]
    if not len(d):
        return pd.DataFrame(columns=GENERAL_COLUMNS)

    g = d.groupby(["company_code", "fiscal_period"], observed=True)
    out = g.agg(
        general_consensus=("estimate_value", "mean"),
        median=("estimate_value", "median"),
        std=("estimate_value", lambda s: float(np.std(s.to_numpy(dtype=float), ddof=1))
             if len(s) > 1 else np.nan),
        min=("estimate_value", "min"),
        max=("estimate_value", "max"),
        analyst_count=("estimator_id", "nunique"),
        broker_count=("broker_name_norm", "nunique"),
        estimate_age_median=("age_days", "median"),
    ).reset_index()
    m = g["estimate_value"].apply(lambda s: mad(s.to_numpy(dtype=float))).reset_index(name="mad")
    out = out.merge(m, on=["company_code", "fiscal_period"], how="left")
    out["asof"] = d["asof"].iloc[0]
    out["metric"] = metric
    out["sufficient"] = out["analyst_count"] >= int(min_analysts)
    # 미달이면 컨센서스 자체를 결측으로 만든다 (§4: 0 대체 금지)
    out.loc[~out["sufficient"], "general_consensus"] = np.nan
    return out[GENERAL_COLUMNS]


# ════════════════════════════════════════════════════════════════════════════════════════
#  가중치 상한 재분배 (§5.5)
# ════════════════════════════════════════════════════════════════════════════════════════
def apply_weight_cap(w: np.ndarray, g: np.ndarray, ng: int, cap: float
                     ) -> Tuple[np.ndarray, np.ndarray]:
    """그룹별 합=1 을 유지한 채 개별 가중을 cap 이하로. (가중치, 그룹별 infeasible 플래그)

    n*cap < 1 이면 어떤 배분도 두 조건을 동시에 만족할 수 없다 → 동일가중으로 낮추고 플래그.
    """
    w = np.asarray(w, dtype=np.float64).copy()
    size = np.bincount(g, minlength=ng).astype(float)
    infeasible = size * cap < 1.0 - 1e-12

    tot = group_sum(w, g, ng)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(tot[g] > 0, w / tot[g], np.nan)
    # infeasible 그룹은 즉시 동일가중
    if infeasible.any():
        w = np.where(infeasible[g], 1.0 / np.maximum(size[g], 1.0), w)

    for _ in range(MAX_CAP_ITERATIONS):
        over = (w > cap + 1e-12) & ~infeasible[g]
        if not over.any():
            break
        excess = group_sum(np.where(over, w - cap, 0.0), g, ng)
        free = group_sum(np.where(~over, w, 0.0), g, ng)
        scale = np.where(free > 1e-15, 1.0 + excess / np.where(free > 1e-15, free, 1.0), 1.0)
        w = np.where(over, cap, w * scale[g])
    return w, infeasible


# ════════════════════════════════════════════════════════════════════════════════════════
#  스마트 컨센서스
# ════════════════════════════════════════════════════════════════════════════════════════
def smart_consensus(snap: "pd.DataFrame", general: "pd.DataFrame", skills: "pd.DataFrame",
                    cfg: SCGConfig, metric: str = "EPS", keep_audit: bool = True
                    ) -> Tuple["pd.DataFrame", "pd.DataFrame"]:
    """(결과, 성분 감사표). 결과 컬럼: company_code, fiscal_period, smart_consensus, flags."""
    empty = pd.DataFrame(columns=["asof", "company_code", "fiscal_period", "metric",
                                  "smart_consensus", "weight_sum", "max_weight",
                                  "weight_cap_infeasible", "n_used"])
    if snap is None or not len(snap):
        return empty, pd.DataFrame(columns=AUDIT_COLUMNS)
    d = snap[snap["metric"] == metric].copy()
    if not len(d):
        return empty, pd.DataFrame(columns=AUDIT_COLUMNS)

    # 충분 표본(≥3명) 그룹만 대상 — 일반 컨센서스가 결측이면 스마트도 정의하지 않는다
    ok_keys = general.loc[general["sufficient"].astype(bool), ["company_code", "fiscal_period"]]
    d = d.merge(ok_keys, on=["company_code", "fiscal_period"], how="inner")
    if not len(d):
        return empty, pd.DataFrame(columns=AUDIT_COLUMNS)

    sk = skills[["estimator_id", "bias", "skill", "n_events"]] if skills is not None and len(skills) \
        else pd.DataFrame(columns=["estimator_id", "bias", "skill", "n_events"])
    d = d.merge(sk, on="estimator_id", how="left")
    d["skill"] = d["skill"].astype(float).fillna(1.0)          # 이력 없음 → skill 1 (§5.3)
    d["bias"] = d["bias"].astype(float).fillna(0.0)
    d["n_events"] = d["n_events"].fillna(0).astype("int64")

    d = d.merge(general[["company_code", "fiscal_period", "general_consensus"]],
                on=["company_code", "fiscal_period"], how="left")

    age = d["age_days"].to_numpy(dtype=float)
    d["w_recency"] = np.power(2.0, -age / float(cfg.recency_half_life_days))
    d["w_raw"] = d["w_recency"].to_numpy() * d["skill"].to_numpy()

    # §5.4 편향 보정 — 현재 일반 컨센서스 스케일로 되돌린다
    bias = np.clip(d["bias"].to_numpy(dtype=float), -BIAS_CLIP, BIAS_CLIP)
    bias_scale = np.maximum(np.abs(d["general_consensus"].to_numpy(dtype=float)), EPS_NUMERIC_FLOOR)
    d["bias_scale"] = bias_scale
    d["estimate_adj"] = d["estimate_value"].to_numpy(dtype=float) - bias * bias_scale

    g, ng = group_codes(d[["company_code", "fiscal_period"]])
    w, infeasible = apply_weight_cap(d["w_raw"].to_numpy(dtype=float), g, ng,
                                     float(cfg.analyst_weight_cap))
    d["w_final"] = w

    sm = group_sum(w * d["estimate_adj"].to_numpy(dtype=float), g, ng)
    wsum = group_sum(w, g, ng)
    wmax = np.zeros(ng)
    np.maximum.at(wmax, g, w)
    size = np.bincount(g, minlength=ng)

    keys = d[["company_code", "fiscal_period"]].to_numpy()
    #  그룹 대표행 = 그룹 내 최소 인덱스. 초기값을 len(d) 로 두어야 minimum.at 이 올바르다.
    first = np.full(ng, len(d) - 1, dtype=np.int64)
    np.minimum.at(first, g, np.arange(len(d), dtype=np.int64))

    res = pd.DataFrame({
        "asof": d["asof"].iloc[0],
        "company_code": keys[first, 0],
        "fiscal_period": keys[first, 1],
        "metric": metric,
        "smart_consensus": sm,
        "weight_sum": wsum,
        "max_weight": wmax,
        "weight_cap_infeasible": infeasible,
        "n_used": size,
    })
    res.loc[res["n_used"] < MIN_ANALYST_COUNT, "smart_consensus"] = np.nan

    audit = d.reindex(columns=[c for c in AUDIT_COLUMNS if c != "estimate_raw"]).copy()
    audit["estimate_raw"] = d["estimate_value"].to_numpy(dtype=float)
    audit = audit[AUDIT_COLUMNS] if keep_audit else pd.DataFrame(columns=AUDIT_COLUMNS)
    return res, audit


# ════════════════════════════════════════════════════════════════════════════════════════
#  Smart Gap (§6)
# ════════════════════════════════════════════════════════════════════════════════════════
def smart_gap(general: "pd.DataFrame", smart: "pd.DataFrame") -> "pd.DataFrame":
    """SCG_RAW = (C_smart - C_general) / C_general. 원문 산식 그대로. abs 금지."""
    cols = ["asof", "company_code", "fiscal_period", "general_consensus", "smart_consensus",
            "SCG_RAW", "scg_flag", "analyst_count"]
    if general is None or not len(general):
        return pd.DataFrame(columns=cols)
    m = general.merge(smart[["company_code", "fiscal_period", "smart_consensus"]],
                      on=["company_code", "fiscal_period"], how="left") \
        if smart is not None and len(smart) else general.assign(smart_consensus=np.nan)

    gc = m["general_consensus"].to_numpy(dtype=float)
    sc = m["smart_consensus"].to_numpy(dtype=float)
    scg = np.full(len(m), np.nan)
    flag = np.array(["OK"] * len(m), dtype=object)

    near_zero = np.isfinite(gc) & (np.abs(gc) < DENOM_NEAR_ZERO_TOL)
    flag[near_zero] = "DENOM_NEAR_ZERO"
    missing = ~np.isfinite(gc) | ~np.isfinite(sc)
    flag[missing & ~near_zero] = "MISSING_CONSENSUS"
    calc = np.isfinite(gc) & np.isfinite(sc) & ~near_zero
    scg[calc] = (sc[calc] - gc[calc]) / gc[calc]        # ★ 분모는 C_general 원형

    m["SCG_RAW"] = scg
    m["scg_flag"] = flag
    return m[cols]


# ════════════════════════════════════════════════════════════════════════════════════════
#  단위 테스트 (§26-9) — 산식 자체가 변형되지 않았음을 매 실행 확인
# ════════════════════════════════════════════════════════════════════════════════════════
def scg_formula_unit_tests() -> "pd.DataFrame":
    """SCG 산식/가중치 캡/편향보정의 성질을 고정한다. 실패는 CRITICAL 이다."""
    rows: List[Dict[str, Any]] = []

    def chk(name: str, cond: bool, detail: str = "") -> None:
        rows.append({"test": name, "passed": bool(cond), "detail": detail})

    # 1. 기본 산식
    gen = pd.DataFrame({"asof": [pd.Timestamp("2020-06-30")] * 4,
                        "company_code": ["000001", "000002", "000003", "000004"],
                        "fiscal_period": ["2020Q3"] * 4, "metric": ["EPS"] * 4,
                        "general_consensus": [100.0, -50.0, 1e-12, np.nan],
                        "median": np.nan, "std": np.nan, "mad": np.nan, "min": np.nan,
                        "max": np.nan, "analyst_count": [5, 5, 5, 5], "broker_count": [5, 5, 5, 5],
                        "estimate_age_median": [10.0] * 4, "sufficient": [True] * 4})
    sm = pd.DataFrame({"company_code": ["000001", "000002", "000003", "000004"],
                       "fiscal_period": ["2020Q3"] * 4,
                       "smart_consensus": [110.0, -40.0, 5e-13, 10.0]})
    out = smart_gap(gen, sm).set_index("company_code")
    chk("SCG_양수분모", abs(out.loc["000001", "SCG_RAW"] - 0.10) < 1e-12,
        f"{out.loc['000001', 'SCG_RAW']}")
    # 음수 분모: (−40 − (−50)) / (−50) = −0.2. abs 를 썼다면 +0.2 가 나온다.
    chk("SCG_음수분모_abs금지", abs(out.loc["000002", "SCG_RAW"] - (-0.2)) < 1e-12,
        f"{out.loc['000002', 'SCG_RAW']} (abs 사용 시 +0.2)")
    chk("SCG_0분모_플래그", out.loc["000003", "scg_flag"] == "DENOM_NEAR_ZERO"
        and not np.isfinite(out.loc["000003", "SCG_RAW"]), str(out.loc["000003", "scg_flag"]))
    chk("SCG_컨센결측_전파", not np.isfinite(out.loc["000004", "SCG_RAW"]), "")

    # 2. 가중치 캡
    g = np.array([0, 0, 0, 0, 1, 1, 1])
    w0 = np.array([100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    w, inf = apply_weight_cap(w0, g, 2, 0.35)
    s0 = w[:4].sum(); s1 = w[4:].sum()
    chk("가중합_1", abs(s0 - 1) < 1e-10 and abs(s1 - 1) < 1e-10, f"{s0},{s1}")
    chk("가중상한_준수", w.max() <= 0.35 + 1e-9, f"max={w.max():.6f}")
    chk("캡_infeasible_미발생", not inf.any(), f"{inf}")
    w2, inf2 = apply_weight_cap(np.array([1.0, 1.0]), np.array([0, 0]), 1, 0.35)
    chk("캡_infeasible_감지", bool(inf2[0]) and abs(w2.sum() - 1) < 1e-12, f"{w2},{inf2}")

    # 3. 편향 보정 방향 — 과대추정(bias>0) 애널리스트는 하향 조정되어야 한다
    snap = pd.DataFrame({
        "asof": [pd.Timestamp("2020-06-30")] * 3,
        "company_code": ["000001"] * 3, "fiscal_period": ["2020Q3"] * 3, "metric": ["EPS"] * 3,
        "estimator_id": ["A::a", "B::b", "C::c"], "broker_name_norm": ["A", "B", "C"],
        "analyst_name_norm": ["a", "b", "c"],
        "published_at": [pd.Timestamp("2020-06-20")] * 3, "age_days": [10.0] * 3,
        "estimate_value": [100.0, 100.0, 100.0], "report_id": ["1", "2", "3"]})
    skills = pd.DataFrame({"estimator_id": ["A::a", "B::b", "C::c"], "bias": [0.10, 0.0, 0.0],
                           "skill": [1.0, 1.0, 1.0], "n_events": [12, 12, 12]})
    gen2 = general_consensus(snap)
    from .config import SCGConfig as _Cfg
    res, aud = smart_consensus(snap, gen2, skills, _Cfg())
    sc = float(res["smart_consensus"].iloc[0])
    gc = float(gen2["general_consensus"].iloc[0])
    chk("편향보정_방향", sc < gc, f"smart={sc:.4f} general={gc:.4f} (과대편향은 하향이어야)")
    exp = 100.0 - (0.10 * 100.0) / 3.0
    chk("편향보정_크기", abs(sc - exp) < 1e-9, f"{sc} vs 기대 {exp}")
    chk("감사표_역산가능", abs(float((aud["w_final"] * aud["estimate_adj"]).sum()) - sc) < 1e-9,
        "성분 가중합이 smart consensus 와 일치해야 한다 (§5.5)")

    # 4. 최소 애널리스트 수
    snap2 = snap.iloc[:2].copy()
    gen3 = general_consensus(snap2)
    chk("최소3명_미달_결측", bool(gen3["general_consensus"].isna().all()),
        f"{gen3['general_consensus'].tolist()}")

    # 5. 최신성 가중 단조성 — 가중 상한이 걸리지 않을 만큼 estimator 를 두고 본다.
    #    (3명뿐이면 상한 35% 가 곧바로 바인딩되어 최신성이 아니라 상한을 검정하게 된다)
    ages = [0.0, 10.0, 20.0, 30.0, 40.0]
    n5 = len(ages)
    snap4 = pd.DataFrame({
        "asof": [pd.Timestamp("2020-06-30")] * n5,
        "company_code": ["000001"] * n5, "fiscal_period": ["2020Q3"] * n5, "metric": ["EPS"] * n5,
        "estimator_id": [f"B{i}::a{i}" for i in range(n5)],
        "broker_name_norm": [f"B{i}" for i in range(n5)],
        "analyst_name_norm": [f"a{i}" for i in range(n5)],
        "published_at": [pd.Timestamp("2020-06-30") - pd.Timedelta(days=int(a)) for a in ages],
        "age_days": ages, "estimate_value": [100.0] * n5,
        "report_id": [str(i) for i in range(n5)]})
    sk5 = pd.DataFrame({"estimator_id": snap4["estimator_id"], "bias": 0.0, "skill": 1.0,
                        "n_events": 12})
    res4, aud4 = smart_consensus(snap4, general_consensus(snap4), sk5, _Cfg())
    wf = aud4.sort_values("age_days")["w_final"].to_numpy()
    chk("가중상한_미바인딩", float(wf.max()) <= 0.35 + 1e-12, f"max={wf.max():.4f}")
    chk("최신성_단조감소", bool(np.all(np.diff(wf) < 0)), f"{np.round(wf, 6)}")
    chk("반감기_30일", abs(wf[3] / wf[0] - 0.5) < 1e-9, f"ratio={wf[3]/wf[0]:.6f}")

    return pd.DataFrame(rows)


__all__ = ["general_consensus", "smart_consensus", "smart_gap", "apply_weight_cap",
           "scg_formula_unit_tests", "GENERAL_COLUMNS", "AUDIT_COLUMNS"]
