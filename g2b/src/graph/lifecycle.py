# -*- coding: utf-8 -*-
"""G2B Opportunity Lifecycle — §9 통합, §11 이중계산 방지의 구현체.

핵심 산식 (이 파일의 존재 이유)
─────────────────────────────────────────────────────────────────────────────
  시점 t 에서 한 조달건 o 의 정부수요는
      best_known_amount(o, t) = '그때까지 알려진 가장 진척된 단계'의 금액
  이고, 신규 정부수요 flow 는 그 계단함수의 **증분**이다.

      demand_flow(o, t) = Δ_t best_known_amount(o, t)

  이 한 줄이 §8(수정공고 중복금지)과 §11(plan+bid+award+contract 4중계상 금지)을
  동시에 해결한다. 증분의 총합은 항상 마지막으로 알려진 금액과 정확히 같으므로
  어떤 순서로 집계해도 이중계산이 원천적으로 불가능하다.

  1 plan → N bids, N plans → 1 bid, 1 bid → 재입찰 N회, 1 award → 복수 계약
  모두 허용된다 — 강제 1:1 매칭을 하지 않는다(§9).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from graph.linker import build_edges, doc_key, LINK_METHOD_SCORE
from collectors.base import STAGE_RANK
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE_ORDER = ["PLAN", "PRESPEC", "BID", "AWARD", "CONTRACT"]   # STAGE_RANK 는 collectors.base 가 원천

GIANT_COMPONENT_DOCS = 200          # 이보다 큰 덩어리는 '과잉병합'으로 표시한다


def _connected_components(edges: pd.DataFrame) -> pd.DataFrame:
    """이분 간선(doc↔key) → 연결요소. scipy 로 완전 벡터화 (문서 수백만 건도 수 초)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    docs = pd.Index(pd.unique(edges["doc"]))
    keys = pd.Index(pd.unique(edges["key"]))
    di = docs.get_indexer(edges["doc"])
    ki = keys.get_indexer(edges["key"]) + len(docs)
    n = len(docs) + len(keys)
    A = coo_matrix((np.ones(len(edges), dtype=np.int8), (di, ki)), shape=(n, n))
    ncomp, lab = connected_components(A, directed=False)
    return pd.DataFrame({"doc": docs, "comp": lab[:len(docs)]})


def resolve_opportunities(E: pd.DataFrame, use_attr: bool = False,
                          use_process: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """이벤트에 opportunity_id 를 부여한다. 반환 (이벤트+opportunity_id, 연결 진단표)."""
    if E is None or not len(E):
        return E, pd.DataFrame()
    ed = build_edges(E, use_official=True, use_process=use_process, use_attr=use_attr)
    if not len(ed):
        out = E.copy()
        out["opportunity_id"] = "OPP_" + doc_key(out)
        out["link_method"] = "ISOLATED"
        out["link_score"] = 0.0
        out["link_known_at"] = out["available_at"]
        return out, pd.DataFrame()
    comp = _connected_components(ed)
    dk = doc_key(E)
    out = E.copy()
    out["_doc"] = dk.to_numpy()
    out = out.merge(comp, left_on="_doc", right_on="doc", how="left").drop(columns=["doc"])
    out["comp"] = out["comp"].fillna(-1).astype("int64")
    # 안정적 opportunity_id: 연결요소의 가장 이른 available_at + 최소 doc key 로 결정 (§88 재현성)
    anchor = (out.sort_values(["comp", "available_at", "_doc"], kind="stable")
              .groupby("comp", as_index=False).first()[["comp", "_doc"]]
              .rename(columns={"_doc": "_anchor"}))
    out = out.merge(anchor, on="comp", how="left")
    out["opportunity_id"] = "OPP_" + pd.util.hash_pandas_object(
        out["_anchor"].astype(str), index=False).astype("uint64").astype(str).str.slice(0, 15)

    # 각 문서에 붙은 연결근거 중 가장 강한 것
    best = (ed.sort_values("link_score", ascending=False, kind="stable")
            .drop_duplicates(subset=["doc"], keep="first")[["doc", "method", "link_score"]])
    out = out.merge(best.rename(columns={"doc": "_doc", "method": "link_method"}),
                    on="_doc", how="left")
    out["link_method"] = out["link_method"].fillna("ISOLATED")
    out["link_score"] = out["link_score"].fillna(0.0)
    # link_known_at: 그 연결을 알 수 있었던 시각 = 같은 opportunity 내 문서들의 available_at 누적 최대
    out = out.sort_values(["opportunity_id", "available_at"], kind="stable")
    out["link_known_at"] = out.groupby("opportunity_id")["available_at"].cummax()

    sizes = out.groupby("opportunity_id")["_doc"].nunique()
    giant = sizes[sizes > GIANT_COMPONENT_DOCS]
    if len(giant):
        LOG.warn(f"과잉병합 의심 opportunity {len(giant):,}개 (문서 {GIANT_COMPONENT_DOCS}개 초과, "
                 f"최대 {int(sizes.max()):,}). 연결근거를 재검토해야 합니다 — "
                 f"억지 확정 대신 진단표에 남깁니다(§10).")
        out["giant_component"] = out["opportunity_id"].isin(giant.index)
    else:
        out["giant_component"] = False

    diag = pd.DataFrame([{
        "이벤트": len(out), "문서": int(out["_doc"].nunique()),
        "opportunity": int(out["opportunity_id"].nunique()),
        "문서/opportunity_평균": float(sizes.mean()), "최대": int(sizes.max()),
        "과잉병합_opportunity": int(len(giant)),
        "단계2개이상_보유": int((out.groupby("opportunity_id")["stage"].nunique() > 1).sum()),
    }])
    LOG.ok(f"lifecycle 해석: 이벤트 {len(out):,} → opportunity {out['opportunity_id'].nunique():,} "
           f"(문서/건 평균 {sizes.mean():.2f})")
    return out.drop(columns=["_doc", "_anchor", "comp"]), diag


def stage_ladder(E: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """§11 핵심. opportunity 별 '가장 진척된 단계' 계단함수와 그 증분(신규 정부수요)을 만든다.

    반환 컬럼
      opportunity_id, available_at, stage, stage_rank, best_amount, demand_flow,
      is_advance(단계 전진), is_revision(같은 단계 내 금액변경)
    전부 groupby+cummax+diff 로 벡터화. opportunity 루프 없음.
    """
    need = ["opportunity_id", "available_at", "stage", amount_col]
    miss = [c for c in need if c not in E.columns]
    if miss:
        raise KeyError(f"stage_ladder 입력 컬럼 누락: {miss}")
    d = E[E[amount_col].notna()].copy()
    if not len(d):
        return pd.DataFrame(columns=["opportunity_id", "available_at", "stage", "stage_rank",
                                     "best_amount", "demand_flow", "is_advance", "is_revision"])
    d["stage_rank"] = d["stage"].map(STAGE_RANK).astype("float64")
    d = d.dropna(subset=["stage_rank"])
    # 같은 시각·같은 단계에 여러 문서가 있으면 금액을 합산해 한 관측으로 만든다
    d = (d.groupby(["opportunity_id", "available_at", "stage", "stage_rank"], as_index=False,
                   observed=True)[amount_col].sum())
    d = d.sort_values(["opportunity_id", "available_at", "stage_rank"], kind="stable")
    g = d.groupby("opportunity_id", sort=False)
    run_max = g["stage_rank"].cummax()
    # '현재 최고 단계 이상'인 관측만 상태를 바꾼다. 뒤늦게 도착한 하위단계 문서는 상태를 되돌리지 않는다.
    d["is_state_change"] = d["stage_rank"].to_numpy() >= run_max.to_numpy()
    s = d[d["is_state_change"]].copy()
    s["best_amount"] = s[amount_col]
    gs = s.groupby("opportunity_id", sort=False)
    prev_amt = gs["best_amount"].shift(1)
    prev_rank = gs["stage_rank"].shift(1)
    s["demand_flow"] = s["best_amount"] - prev_amt.fillna(0.0)
    s["is_advance"] = (prev_rank.isna()) | (s["stage_rank"] > prev_rank)
    s["is_revision"] = (~s["is_advance"])
    return s[["opportunity_id", "available_at", "stage", "stage_rank", "best_amount",
              "demand_flow", "is_advance", "is_revision"]].reset_index(drop=True)


def opportunity_lifecycle(E: pd.DataFrame) -> pd.DataFrame:
    """gold/g2b_opportunity_lifecycle.parquet (§89) — opportunity 1행 요약.

    ⚠ 여기 담기는 '최종' 컬럼은 사후 요약이며 CLASS C 다. 팩터에 쓰면 assert_pit_safe 가 막는다.
    """
    if E is None or not len(E):
        return pd.DataFrame()
    d = E.copy()
    d["stage_rank"] = d["stage"].map(STAGE_RANK)
    first_by_stage = (d.sort_values("available_at", kind="stable")
                      .groupby(["opportunity_id", "stage"], as_index=False)
                      .agg(first_available=("available_at", "first"),
                           first_event=("event_time", "first"), amt=("amount", "first")))
    piv = first_by_stage.pivot_table(index="opportunity_id", columns="stage",
                                     values="first_available", aggfunc="min")
    piv.columns = [f"t_{c}" for c in piv.columns]
    amt = first_by_stage.pivot_table(index="opportunity_id", columns="stage",
                                     values="amt", aggfunc="sum")
    amt.columns = [f"amt_{c}" for c in amt.columns]
    base = (d.sort_values("available_at", kind="stable").groupby("opportunity_id", as_index=False)
            .agg(agency_cd=("agency_cd", "first"), agency_nm=("agency_nm", "first"),
                 category_cd=("category_cd", "first"), category_nm=("category_nm", "first"),
                 proc_type=("proc_type", "first"), title=("title", "first"),
                 first_seen=("available_at", "min"), last_seen=("available_at", "max"),
                 max_stage_rank=("stage_rank", "max"), n_events=("stage", "size"),
                 n_stages=("stage", "nunique")))
    out = base.merge(piv.reset_index(), on="opportunity_id", how="left") \
              .merge(amt.reset_index(), on="opportunity_id", how="left")
    win = (d[d["supplier_bizno"].notna()].sort_values("available_at", kind="stable")
           .groupby("opportunity_id", as_index=False)
           .agg(winner_bizno=("supplier_bizno", "last"), winner_nm=("supplier_nm", "last"),
                winner_known_at=("available_at", "min")))
    out = out.merge(win, on="opportunity_id", how="left")
    out["reached_stage"] = out["max_stage_rank"].map({v: k for k, v in STAGE_RANK.items()})
    return out


def double_count_audit(E: pd.DataFrame, amount_col: str = "amount") -> pd.DataFrame:
    """§11 이 실제로 작동했는지 수치로 증명한다. 회귀 테스트가 이 표를 본다."""
    lad = stage_ladder(E, amount_col)
    naive_all = float(pd.to_numeric(E[amount_col], errors="coerce").sum())
    by_stage = E.groupby("stage")[amount_col].sum()
    correct = float(lad["demand_flow"].sum())
    last_known = float(lad.sort_values(["opportunity_id", "available_at"])
                       .groupby("opportunity_id")["best_amount"].last().sum())
    rows = [{"측정": "전 단계 단순합산(금지된 계산)", "금액": naive_all},
            *[{"측정": f"  └ {s} 단계 합", "금액": float(v)} for s, v in by_stage.items()],
            {"측정": "lifecycle 증분합(정답)", "금액": correct},
            {"측정": "opportunity 최종 알려진 금액 합", "금액": last_known},
            {"측정": "제거된 이중계상액", "금액": naive_all - correct},
            {"측정": "이중계상 배수", "금액": (naive_all / correct) if correct else np.nan}]
    return pd.DataFrame(rows)
