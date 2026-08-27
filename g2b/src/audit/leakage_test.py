# -*- coding: utf-8 -*-
"""누수 탐지기와 카나리아 테스트.   §7 · §74 · §75 · §93

§93 이 파일의 존재 이유:
   의도적으로 미래 낙찰정보를 t 이전 데이터에 삽입한 mock dataset 을 만들고
   **누수 탐지기가 그것을 실패시키는지** 확인한다.
   이 테스트가 통과하지 못하면 본 백테스트 실행을 금지한다.

탐지기는 세 층이다.
  L1 구조 탐지  : 시각 자체가 불가능한 행 (available_at < published, 개찰 전 낙찰자 공개 등)
  L2 사용 탐지  : 시점 t 의 피처가 available_at > t 인 이벤트를 썼는가
  L3 통계 탐지  : 미래 정부수요가 과거 수익률을 설명하는가 (§75 temporal placebo)
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from pit.timestamps import field_class, PIT_COLS
from backtest.statistics import newey_west_t, information_coefficient
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


class LeakageDetected(Exception):
    """누수가 탐지되면 조용히 로그만 남기지 않고 파이프라인을 세운다."""


# ══════════════════════════════════════════════════════════════════════════════
#  L1 — 구조 탐지
# ══════════════════════════════════════════════════════════════════════════════
def scan_events(E: pd.DataFrame) -> pd.DataFrame:
    """이벤트 원장 자체의 시간 모순을 찾는다. 반환은 위반 요약표(빈 표 = 정상)."""
    v: List[dict] = []
    if E is None or not len(E):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    miss = [c for c in PIT_COLS if c not in E.columns]
    if miss:
        v.append({"검사": "PIT_COLUMNS", "위반건수": len(E), "설명": f"PIT 컬럼 누락 {miss}"})
        return pd.DataFrame(v)
    n = int((E["available_at"] < E["source_published_at"]).sum())
    if n:
        v.append({"검사": "AVAIL_BEFORE_PUBLISH", "위반건수": n,
                  "설명": "공개되기 전에 사용가능해진 행 — 정의상 불가능"})
    # 낙찰/계약은 사건이 일어나기 전에 공개될 수 없다
    late = E[E["stage"].isin(["AWARD", "CONTRACT"])]
    if len(late):
        n = int((late["source_published_at"] < late["event_time"]).sum())
        if n:
            v.append({"검사": "PUBLISH_BEFORE_EVENT", "위반건수": n,
                      "설명": "개찰/계약 이전에 결과가 공개된 행 — 미래정보 삽입의 전형적 흔적"})
    # 낙찰자가 입찰공고보다 먼저 알려진 경우
    if "opportunity_id" in E.columns:
        bid = (E[E["stage"] == "BID"].groupby("opportunity_id")["available_at"].min()
               .rename("t_bid"))
        aw = (E[E["stage"] == "AWARD"].groupby("opportunity_id")["available_at"].min()
              .rename("t_award"))
        j = pd.concat([bid, aw], axis=1).dropna()
        if len(j):
            n = int((j["t_award"] < j["t_bid"]).sum())
            if n:
                v.append({"검사": "WINNER_BEFORE_BID", "위반건수": n,
                          "설명": "입찰공고보다 먼저 알려진 낙찰자 — §7 직접 위반"})
    return pd.DataFrame(v) if v else pd.DataFrame(columns=["검사", "위반건수", "설명"])


def scan_feature_inputs(feature_cols: Sequence[str]) -> pd.DataFrame:
    """§6.1 — 팩터 입력에 CLASS C 필드가 섞였는지."""
    bad = [c for c in feature_cols if field_class(c) == "C"]
    return pd.DataFrame([{"검사": "CLASS_C_FIELD", "위반건수": len(bad),
                          "설명": f"PIT_UNCERTIFIED 필드 사용: {bad}"}] if bad else [],
                        columns=["검사", "위반건수", "설명"])


# ══════════════════════════════════════════════════════════════════════════════
#  L2 — 사용 탐지 (시점 t 피처가 t 이후 이벤트를 봤는가)
# ══════════════════════════════════════════════════════════════════════════════
def scan_panel_provenance(panel: pd.DataFrame, events: pd.DataFrame,
                          firm_col: str = "stock_code", month_col: str = "month",
                          value_col: str = "award_amt_12m", window_m: int = 12) -> pd.DataFrame:
    """기업×월 피처값이 그 시점에 알려진 이벤트만으로 설명되는지 대조 검증한다.

    award_amt_12m 을 available_at 기준으로 독립 재계산해 원 패널과 비교한다.
    원 패널이 더 크면 = 아직 몰랐던 낙찰을 이미 세고 있다 = 누수.
    """
    if panel is None or not len(panel) or events is None or not len(events):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    a = events[(events["stage"] == "AWARD") & events[firm_col].notna()].copy()
    if not len(a):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    amt = "attributed_amount" if "attributed_amount" in a.columns else "amount"
    a["m"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
    obs = a.groupby([firm_col, "m"], as_index=False, observed=True)[amt].sum()
    p = panel[[firm_col, month_col, value_col]].dropna()
    if not len(p):
        return pd.DataFrame(columns=["검사", "위반건수", "설명"])
    chk = p.merge(obs.rename(columns={"m": month_col}), on=[firm_col, month_col], how="left")
    ref = (obs.sort_values("m").set_index("m").groupby(firm_col)[amt]
           .rolling(f"{window_m * 31}D").sum().reset_index()
           .rename(columns={"m": month_col, amt: "ref"}))
    chk = chk.merge(ref, on=[firm_col, month_col], how="left")
    bad = chk[chk["ref"].notna() & (chk[value_col] > chk["ref"] * 1.001 + 1.0)]
    return pd.DataFrame([{"검사": "PANEL_AHEAD_OF_EVENTS", "위반건수": len(bad),
                          "설명": f"{value_col} 이 그 시점 관측 누적을 초과한 행"}]
                        if len(bad) else [], columns=["검사", "위반건수", "설명"])


# ══════════════════════════════════════════════════════════════════════════════
#  L3 — 통계 탐지 (§74 permutation placebo, §75 temporal placebo)
# ══════════════════════════════════════════════════════════════════════════════
def permutation_placebo(F: pd.DataFrame, score_col: str, ret_col: str, n_perm: int = 200,
                        month_col: str = "month", seed: int = 20260820) -> pd.DataFrame:
    """§74 — 같은 달 안에서 신호를 섞어 null 분포를 만든다. 실제 IC 가 얼마나 극단적인가."""
    d = F[[month_col, score_col, ret_col]].dropna()
    if len(d) < 50:
        return pd.DataFrame()
    real, _ = information_coefficient(d, score_col, ret_col, month_col)
    if not len(real):
        return pd.DataFrame()
    real_ic = float(real["평균IC"].iloc[0])
    rg = np.random.default_rng(seed)
    codes = d[month_col].astype("category").cat.codes.to_numpy()
    order = np.argsort(codes, kind="stable")
    s_sorted = d[score_col].to_numpy()[order]
    starts = np.searchsorted(codes[order], np.arange(codes.max() + 1), side="left")
    ends = np.searchsorted(codes[order], np.arange(codes.max() + 1), side="right")
    null = np.empty(n_perm)
    base = d.iloc[order].reset_index(drop=True)
    for i in range(n_perm):
        sh = s_sorted.copy()
        for a, b in zip(starts, ends):
            if b - a > 1:
                sh[a:b] = rg.permutation(sh[a:b])
        tmp = base.assign(**{score_col: sh})
        r, _ = information_coefficient(tmp, score_col, ret_col, month_col)
        null[i] = float(r["평균IC"].iloc[0]) if len(r) else np.nan
    null = null[np.isfinite(null)]
    if not len(null):
        return pd.DataFrame()
    p = float((np.abs(null) >= abs(real_ic)).mean())
    return pd.DataFrame([{"검정": "permutation_placebo(§74)", "실제 평균IC": real_ic,
                          "null 평균": float(null.mean()), "null 표준편차": float(null.std(ddof=1)),
                          "z": (real_ic - null.mean()) / (null.std(ddof=1) + 1e-12),
                          "양측 p": p, "순열수": len(null)}])


def temporal_placebo(F: pd.DataFrame, score_col: str, market: pd.DataFrame,
                     firm_col: str = "stock_code", month_col: str = "month",
                     lead_months: int = 12) -> pd.DataFrame:
    """§75 — '미래 신호'가 '과거 수익률'을 설명하면 leakage 의심. 비정상적으로 강하면 재감사."""
    mk = market[[firm_col, month_col, "ret"]].copy()
    fut = F[[firm_col, month_col, score_col]].copy()
    fut[month_col] = (pd.to_datetime(fut[month_col]) - pd.DateOffset(months=lead_months)
                      + pd.offsets.MonthEnd(0))
    j = mk.merge(fut.rename(columns={score_col: "future_signal"}),
                 on=[firm_col, month_col], how="inner").dropna()
    if len(j) < 100:
        return pd.DataFrame()
    summ, _ = information_coefficient(j, "future_signal", "ret", month_col)
    if not len(summ):
        return pd.DataFrame()
    ic = float(summ["평균IC"].iloc[0])
    t = float(summ["IC_t"].iloc[0])
    return pd.DataFrame([{"검정": f"temporal_placebo(§75, lead={lead_months}M)",
                          "미래신호→과거수익 IC": ic, "IC_t": t, "표본": int(summ["월수"].iloc[0]),
                          "판정": ("LEAKAGE_SUSPECT" if abs(t) >= 3.0 else
                                  "WARN" if abs(t) >= 2.0 else "OK"),
                          "해석": ("미래 정부수요가 과거 주가를 설명한다면 타임스탬프/PIT 를 "
                                 "재감사해야 한다(§75)")}])


# ══════════════════════════════════════════════════════════════════════════════
#  §93 카나리아 — 탐지기가 실제로 실패시키는지 증명한다
# ══════════════════════════════════════════════════════════════════════════════
def make_canary_events(E: pd.DataFrame, n_inject: int = 50, seed: int = 20260820) -> pd.DataFrame:
    """미래 낙찰정보를 입찰 이전 시점으로 앞당긴 오염 데이터셋을 만든다."""
    rg = np.random.default_rng(seed)
    d = E.copy()
    aw = d.index[(d["stage"] == "AWARD")].to_numpy()
    if len(aw) == 0:
        raise ValueError("AWARD 이벤트가 없어 카나리아를 만들 수 없습니다.")
    pick = rg.choice(aw, size=min(n_inject, len(aw)), replace=False)
    # 낙찰 결과를 개찰 400일 전에 '알고 있었던' 것처럼 앞당긴다
    d.loc[pick, "available_at"] = d.loc[pick, "available_at"] - pd.Timedelta(days=400)
    d.loc[pick, "source_published_at"] = d.loc[pick, "available_at"]
    d.loc[pick, "_canary"] = True
    d["_canary"] = d.get("_canary", pd.Series(False, index=d.index)).fillna(False)
    return d


def make_canary_signal(F: pd.DataFrame, ret_col: str, score_col: str = "G2B_DWA",
                       strength: float = 0.6, seed: int = 20260820) -> pd.DataFrame:
    """신호에 미래수익률을 직접 섞은 오염본 — 하네스가 둔감하지 않은지 검증한다(R1a 형)."""
    rg = np.random.default_rng(seed)
    d = F.copy()
    r = pd.to_numeric(d[ret_col], errors="coerce")
    rk = r.groupby(d["month"], observed=True).rank(pct=True)
    base = pd.to_numeric(d[score_col], errors="coerce")
    d[score_col + "_CONTAMINATED"] = (1 - strength) * base.fillna(0.5) + strength * rk.fillna(0.5)
    return d


def run_canary(E: pd.DataFrame) -> Tuple[bool, pd.DataFrame]:
    """(통과여부, 표). 오염본에서 탐지기가 반드시 위반을 잡아야 한다."""
    clean = scan_events(E)
    canary = scan_events(make_canary_events(E))
    n_clean = int(clean["위반건수"].sum()) if len(clean) else 0
    n_canary = int(canary["위반건수"].sum()) if len(canary) else 0
    passed = (n_clean == 0) and (n_canary > 0)
    tab = pd.DataFrame([
        {"데이터셋": "정상(clean)", "탐지 위반건수": n_clean, "기대": "0", "판정": "✔" if n_clean == 0 else "✖"},
        {"데이터셋": "오염(canary)", "탐지 위반건수": n_canary, "기대": ">0",
         "판정": "✔" if n_canary > 0 else "✖"}])
    if passed:
        LOG.ok("§93 누수 카나리아 통과 — 탐지기가 삽입된 미래정보를 실패시켰습니다.")
    else:
        LOG.err("§93 누수 카나리아 실패 — 본 백테스트 실행을 금지합니다.")
    return passed, tab


def gate_or_raise(E: pd.DataFrame) -> pd.DataFrame:
    """본 백테스트 전에 반드시 통과해야 하는 관문(§93)."""
    passed, tab = run_canary(E)
    if not passed:
        raise LeakageDetected(
            "§93 누수 카나리아가 통과하지 못했습니다. 탐지기가 미래정보 삽입을 잡지 못하는 상태에서는 "
            "백테스트 결과를 신뢰할 수 없으므로 실행을 중단합니다.")
    return tab
