# -*- coding: utf-8 -*-
"""GovernmentDemand(c,t) — 외생적 정부수요.   §20 · §45 · §83

★ 이 파일의 유일한 규율: **winner 를 보기 전에 계산한다.**
   정부수요는 발주계획·사전규격·입찰공고에서만 만든다. 기업의 낙찰액으로 정의하면
   그것은 '정부수요'가 아니라 '그 기업 실적'이고, 축이 두 개가 아니라 하나가 된다.

산출
  D1 flow  : 신규로 등장한 정부수요 (lifecycle 증분 — §8/§11 이중계산 불가)
  D2 stock : 시점 t 에 이미 공개되어 있고 아직 집행되지 않은 파이프라인 잔량
  §45 LOFO : 시점 t 까지 '이미 알려진' 낙찰이 기업 i 인 건을 i 의 수요에서 뺀다.
             (미래 낙찰자를 쓰면 그 자체가 누수이므로 '알려진' 것만 쓴다)
  §83      : 반복발주(기존 수주기업 대상)와 카테고리 전체 성장을 분리한다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import month_range
from graph.lifecycle import stage_ladder, STAGE_RANK
# ── /PACKAGE IMPORTS ──

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

PRE_AWARD_STAGES = ("PLAN", "PRESPEC", "BID")
PIPELINE_MAX_AGE_M = 24          # 낙찰이 관측되지 않은 채 이만큼 지나면 파이프라인에서 소멸시킨다
WARMUP_NOTE_M = 36               # §19 좌측절단 경고문에 쓰는 권장 warm-up 개월


def preaward_ladder(events: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """winner 를 보기 전 단계만으로 계단함수를 만든다 — 이것이 외생성의 정의다."""
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)]
    if not len(pre):
        LOG.warn("PLAN/PRESPEC/BID 이벤트가 없습니다 — 외생 수요축을 만들 수 없습니다(§20).")
        return pd.DataFrame(columns=["opportunity_id", "available_at", "stage", "stage_rank",
                                     "best_amount", "demand_flow", "is_advance", "is_revision"])
    return stage_ladder(pre, amount_col)


def opportunity_attrs(events: pd.DataFrame) -> pd.DataFrame:
    """opportunity 의 카테고리/기관/유형 — 가장 이른 사전단계 문서 기준(사후 정보 사용 안 함)."""
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)]
    src = pre if len(pre) else events
    return (src.sort_values("available_at", kind="stable")
            .groupby("opportunity_id", as_index=False)
            .agg(category_cd=("category_cd", "first"), category_nm=("category_nm", "first"),
                 agency_cd=("agency_cd", "first"), proc_type=("proc_type", "first"),
                 license_req=("license_req", "first"), region_limit=("region_limit", "first"),
                 broad_category=("broad_category", "first") if "broad_category" in src.columns
                 else ("category_cd", "first")))


def award_known_at(events: pd.DataFrame, firm_col: str = "stock_code") -> pd.DataFrame:
    """각 opportunity 의 낙찰자가 '언제부터 알려졌는가'. §45 LOFO 와 파이프라인 소멸에 쓴다."""
    a = events[(events["stage"] == "AWARD")]
    if not len(a):
        return pd.DataFrame(columns=["opportunity_id", "award_known_at", firm_col])
    return (a.sort_values("available_at", kind="stable")
            .groupby("opportunity_id", as_index=False)
            .agg(award_known_at=("available_at", "min"),
                 **{firm_col: (firm_col, "first")} if firm_col in a.columns else {}))


def demand_panel(events: pd.DataFrame, months: pd.DatetimeIndex,
                 amount_col: str = "amount") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(카테고리×월 수요패널, opportunity 단위 수요흐름).

    반환 패널 컬럼:
      category_cd, month, demand_flow, pipeline_stock, n_new_opp, demand_flow_12m
    전부 groupby/cumsum 벡터화 — 카테고리 루프 없음.
    """
    lad = preaward_ladder(events, amount_col)
    if not len(lad):
        return (pd.DataFrame(columns=["category_cd", "month", "demand_flow", "pipeline_stock"]),
                lad)
    attrs = opportunity_attrs(events)
    lad = lad.merge(attrs, on="opportunity_id", how="left")
    lad["month"] = pd.to_datetime(lad["available_at"]) + pd.offsets.MonthEnd(0)

    # opportunity 의 첫 관측 여부 — '신규 조달건 수'는 단계전진 횟수가 아니다
    lad = lad.sort_values(["opportunity_id", "available_at"], kind="stable")
    lad["is_first_seen"] = ~lad.duplicated(subset=["opportunity_id"], keep="first")

    midx = pd.Series(np.arange(len(months)), index=months)
    lad["_mi"] = lad["month"].map(midx)
    n_before = int(lad["_mi"].isna().sum())
    lad = lad.dropna(subset=["_mi"]).copy()
    lad["_mi"] = lad["_mi"].astype("int32")
    if n_before:
        # 창 밖(주로 창 시작 이전)의 단계관측은 버려진다 → 그만큼 flow 합이 최종금액합보다 작다.
        # 이것은 좌측절단(§19)이며 숨기지 않는다. warm-up 구간을 두는 이유가 이것이다.
        LOG.info(f"수요 계단관측 {n_before:,}건이 분석창 밖이라 제외되었습니다(좌측절단 §19) — "
                 f"창 시작 전 {WARMUP_NOTE_M}개월 warm-up 수집이 필요한 이유입니다.")

    # ── D1 flow ────────────────────────────────────────────────────────────
    flow = (lad.groupby(["category_cd", "_mi"], as_index=False, observed=True)
            .agg(demand_flow=("demand_flow", "sum"),
                 n_new_opp=("is_first_seen", "sum")))

    # ── D2 pipeline stock: +증분 / 낙찰(또는 노후화) 시점에 -잔액 ────────────
    ak = award_known_at(events)
    last_state = (lad.sort_values(["opportunity_id", "_mi"], kind="stable")
                  .groupby("opportunity_id", as_index=False)
                  .agg(last_mi=("_mi", "last"), last_amt=("best_amount", "last"),
                       category_cd=("category_cd", "last")))
    exit_tbl = last_state.merge(ak[["opportunity_id", "award_known_at"]], on="opportunity_id", how="left")
    aw_mi = ((pd.to_datetime(exit_tbl["award_known_at"]) + pd.offsets.MonthEnd(0))
             .map(midx))
    stale_mi = exit_tbl["last_mi"] + PIPELINE_MAX_AGE_M
    exit_tbl["exit_mi"] = np.fmin(aw_mi.fillna(np.inf).to_numpy(), stale_mi.to_numpy())
    exit_tbl = exit_tbl[np.isfinite(exit_tbl["exit_mi"])]
    exit_tbl = exit_tbl[exit_tbl["exit_mi"] < len(months)]
    neg = exit_tbl.assign(_mi=exit_tbl["exit_mi"].astype("int32"),
                          delta=-exit_tbl["last_amt"])[["category_cd", "_mi", "delta"]]
    pos = lad.rename(columns={"demand_flow": "delta"})[["category_cd", "_mi", "delta"]]
    deltas = (pd.concat([pos, neg], ignore_index=True)
              .groupby(["category_cd", "_mi"], as_index=False, observed=True)["delta"].sum())

    # 조밀 격자 위에서 cumsum → 재고
    cats = pd.Index(pd.unique(pd.concat([flow["category_cd"], deltas["category_cd"]]).dropna()))
    grid = pd.MultiIndex.from_product([cats, np.arange(len(months))],
                                      names=["category_cd", "_mi"]).to_frame(index=False)
    P = (grid.merge(flow, on=["category_cd", "_mi"], how="left")
             .merge(deltas, on=["category_cd", "_mi"], how="left"))
    for c in ("demand_flow", "n_new_opp", "delta"):
        P[c] = P[c].fillna(0.0)
    P = P.sort_values(["category_cd", "_mi"], kind="stable")
    P["pipeline_stock"] = P.groupby("category_cd", observed=True)["delta"].cumsum().clip(lower=0)
    P["demand_flow_12m"] = (P.groupby("category_cd", observed=True)["demand_flow"]
                            .transform(lambda s: s.rolling(12, min_periods=1).sum()))
    P["demand_flow_3m"] = (P.groupby("category_cd", observed=True)["demand_flow"]
                           .transform(lambda s: s.rolling(3, min_periods=1).sum()))
    P["month"] = months.to_numpy()[P["_mi"].to_numpy()]
    P = P.drop(columns=["delta", "_mi"])
    LOG.ok(f"정부수요 패널: {P['category_cd'].nunique():,}개 품목 × {len(months)}개월 = {len(P):,}행 "
           f"(winner 정보 미사용 — 외생축)")
    return P.reset_index(drop=True), lad


def lofo_adjustment(lad: pd.DataFrame, events: pd.DataFrame, months: pd.DatetimeIndex,
                    firm_col: str = "stock_code") -> pd.DataFrame:
    """§45 Leave-One-Firm-Out — 시점 t 까지 '이미 알려진' 낙찰자가 i 인 건의 수요를 (i,c,t) 에서 뺀다.

    미래 낙찰자를 쓰면 그 자체가 누수이므로 award_known_at <= t 인 건만 뺀다.
    반환: [firm, category_cd, month, own_flow_known, own_stock_known]
    """
    a = events[(events["stage"] == "AWARD") & events[firm_col].notna()]
    if not len(a) or not len(lad):
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "own_flow_known"])
    ak = (a.sort_values("available_at", kind="stable")
          .groupby("opportunity_id", as_index=False)
          .agg(award_known_at=("available_at", "min"), **{firm_col: (firm_col, "first")}))
    L = lad.merge(ak, on="opportunity_id", how="inner")
    # 그 낙찰이 알려진 이후의 월에만 차감한다
    L["known_month"] = pd.to_datetime(L["award_known_at"]) + pd.offsets.MonthEnd(0)
    L = L[L["month"] >= L["known_month"]]
    if not len(L):
        return pd.DataFrame(columns=[firm_col, "category_cd", "month", "own_flow_known"])
    out = (L.groupby([firm_col, "category_cd", "month"], as_index=False, observed=True)
           .agg(own_flow_known=("demand_flow", "sum")))
    return out


def exogeneity_split(events: pd.DataFrame, panel: pd.DataFrame, months: pd.DatetimeIndex,
                     firm_col: str = "stock_code") -> pd.DataFrame:
    """§83 — 카테고리 전체 성장 vs '기존 수주기업에 대한 반복발주'를 분리한다.

    반환 패널에 다음을 덧붙인다:
      incumbent_share  : 그 카테고리에서 직전 36M 낙찰이 상위 3개사에 집중된 정도
      new_agency_flow  : 그 카테고리에 '처음 등장한 발주기관'이 만든 수요 비중
    """
    if not len(panel):
        return panel
    a = events[(events["stage"] == "AWARD")].copy()
    P = panel.copy()
    if len(a):
        a["month"] = pd.to_datetime(a["available_at"]) + pd.offsets.MonthEnd(0)
        top = (a.groupby(["category_cd", "month", "supplier_bizno"], as_index=False, observed=True)
               ["amount"].sum())
        top["rk"] = top.groupby(["category_cd", "month"], observed=True)["amount"].rank(
            ascending=False, method="first")
        agg = top.groupby(["category_cd", "month"], as_index=False, observed=True).agg(
            tot=("amount", "sum"), top3=("amount", lambda s: s.nlargest(3).sum()))
        agg["incumbent_share"] = agg["top3"] / agg["tot"].replace(0, np.nan)
        P = P.merge(agg[["category_cd", "month", "incumbent_share"]],
                    on=["category_cd", "month"], how="left")
    else:
        P["incumbent_share"] = np.nan
    pre = events[events["stage"].isin(PRE_AWARD_STAGES)].copy()
    if len(pre):
        pre["month"] = pd.to_datetime(pre["available_at"]) + pd.offsets.MonthEnd(0)
        first_seen = pre.groupby(["category_cd", "agency_cd"], observed=True)["month"].transform("min")
        pre["is_new_agency"] = pre["month"] == first_seen
        na = (pre.groupby(["category_cd", "month"], as_index=False, observed=True)
              .agg(tot_amt=("amount", "sum")))
        na2 = (pre[pre["is_new_agency"]].groupby(["category_cd", "month"], as_index=False, observed=True)
               .agg(new_agency_amt=("amount", "sum")))
        na = na.merge(na2, on=["category_cd", "month"], how="left")
        na["new_agency_flow_share"] = na["new_agency_amt"].fillna(0) / na["tot_amt"].replace(0, np.nan)
        P = P.merge(na[["category_cd", "month", "new_agency_flow_share"]],
                    on=["category_cd", "month"], how="left")
    return P
