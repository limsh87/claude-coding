# -*- coding: utf-8 -*-
"""파이프라인 배선 — 수집 → lifecycle → graph → PIT 피처 → 저장.

★ 사용자 필수 요구사항의 구현부:
   · 캐시활용 최우선 : 공용 인덱스에 있으면 절대 재수집하지 않는다.
   · 신규 수집 데이터 → **공용 인덱스**(다른 전략도 재사용 가능한 원본/범용 정제본)
   · 이 연구의 해석물 → **전용 인덱스**(lifecycle · graph · feature · backtest)

§89 최종 산출물 파일명을 그대로 만든다.
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import month_range, atomic_write_parquet, df_hash, write_json
from core.vault import get_vault
from core.http import RawStore
from collectors.order_plan import SPEC_ORDER_PLAN, collect_order_plan
from collectors.prespec import SPEC_PRESPEC, collect_prespec
from collectors.bid import SPEC_BID_NOTICE, collect_bid
from collectors.award import SPEC_AWARD_INFO, collect_award
from collectors.contract import SPEC_CONTRACT, collect_contract
from collectors.process import SPEC_PROC_BID, collect_process
from collectors.dart import fetch_corp_codes, fetch_company_profiles, load_pit_financials
from collectors.synthetic import build_world, build_market, crosswalk_from_world
from collectors.base import CANON_COLS
from pit.timestamps import stamp
from graph.lifecycle import resolve_opportunities, opportunity_lifecycle
from graph.demand_graph import build_graph
from entity.dart_crosswalk import build_crosswalk, attach_stock_code
from entity.consortium import allocate
from features.capability import build_capability, agency_capability
from features.government_demand import demand_panel, lofo_adjustment, exogeneity_split
from features.eligible_tam import (stage_probability, build_eligible_tam, maturity_distribution,
                                   stage_weighted_demand)
from features.win_features import build_win_features, add_size_normalization, breadth_features
from features.competition import (award_rate_features, competition_features, failure_features,
                                  pipeline_conversion, win_conversion)
from features.concentration import build_concentration, contract_revision, proc_risk_score
from features.g2b_dwa import build_demand_axis, build_win_axis, build_dwa
from backtest.universe import load_market_panel, build_universe, procurement_observable
# ── /PACKAGE IMPORTS ──

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 서비스명 → (ServiceSpec, 수집함수). 단일파일 빌드에서도 이름이 충돌하지 않도록
# 각 수집기는 고유한 SPEC_*/collect_* 이름을 쓴다.
COLLECTORS = {
    "order_plan": (SPEC_ORDER_PLAN, collect_order_plan),
    "prespec": (SPEC_PRESPEC, collect_prespec),
    "bid": (SPEC_BID_NOTICE, collect_bid),
    "award": (SPEC_AWARD_INFO, collect_award),
    "contract": (SPEC_CONTRACT, collect_contract),
    "process": (SPEC_PROC_BID, collect_process),
}


# ══════════════════════════════════════════════════════════════════════════════
#  1. 수집 / 적재
# ══════════════════════════════════════════════════════════════════════════════
def collect_events(start: str, end: str, services: Optional[List[str]] = None
                   ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """FULL 모드 수집. 캐시(raw 매니페스트/공용 인덱스)에 있으면 네트워크에 나가지 않는다."""
    V = get_vault()
    parts, audits = [], []
    for name in (services or list(COLLECTORS)):
        spec, collect_fn = COLLECTORS[name]
        tbl = CFG.SHARED_CONTRIB_TABLES[name]
        cached = V.get_table(tbl, scope="shared")
        if CFG.RUN_MODE == "CACHED":
            if cached is not None and len(cached):
                LOG.ok(f"[{name}] 공용 캐시 {len(cached):,}행 재사용 (CACHED 모드 — 신규 수집 없음)")
                parts.append(cached)
            else:
                LOG.warn(f"[{name}] 공용 캐시가 없습니다 (CACHED 모드이므로 수집하지 않음)")
            continue
        LOG.info(f"[{name}] 수집 시작 {start} ~ {end}")
        D, A = collect_fn(start, end)
        audits.append(A)
        if cached is not None and len(cached):
            # append-merge: 기존 캐시를 버리지 않고 합집합으로만 늘린다
            key = [c for c in ("service", "doc_id", "doc_seq", "stage", "event_time")
                   if c in cached.columns and c in D.columns]
            D = (pd.concat([cached, D], ignore_index=True)
                 .drop_duplicates(subset=key or None, keep="last"))
        if D is not None and len(D):
            V.put_table(tbl, D, scope="shared", domain="procurement",
                        source=f"나라장터 {name} (data.go.kr {spec.portal_id})",
                        extra={"start": start, "end": end})
            parts.append(D)
    V.flush("shared")
    E = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CANON_COLS)
    A = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()
    return E, A


def load_events(start: str = None, end: str = None, smoke_scale: int = 260
                ) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """실행모드에 맞춰 이벤트를 얻는다. SMOKE 는 합성 세계."""
    start = start or CFG.TARGET_START
    end = end or CFG.TARGET_END
    ctx: Dict[str, pd.DataFrame] = {}
    if CFG.RUN_MODE == "SMOKE":
        W = build_world(start, end, opp_per_month=smoke_scale)
        ctx.update(W)
        E = W["events"]
        E["broad_category"] = E["license_req"]
        return E, ctx
    E, A = collect_events(start, end)
    ctx["collect_audit"] = A
    if len(E) and "available_at" not in E.columns:
        E = stamp(E, "event_time", "source_published_at", stage="BID")
    return E, ctx


def load_crosswalk(events: pd.DataFrame, ctx: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """§13 §14 — 사업자등록번호 exact match 우선. 캐시 우선."""
    V = get_vault()
    if CFG.RUN_MODE == "SMOKE" and "suppliers" in ctx:
        cw = crosswalk_from_world(ctx)
        return cw
    cached = V.get_table(CFG.SHARED_CONTRIB_TABLES["crosswalk"], scope="shared")
    if cached is not None and len(cached) and CFG.RUN_MODE == "CACHED":
        LOG.ok(f"공용 캐시 crosswalk {len(cached):,}행 재사용")
        return cached
    cc = fetch_corp_codes()
    listed = cc[cc["stock_code"].notna()]["corp_code"].astype(str).tolist() if len(cc) else []
    prof = fetch_company_profiles(listed)
    lh = None
    sm = V.get_table(CFG.SHARED_REUSE_TABLES["listing_snapshots"], scope="shared")
    if sm is not None and len(sm):
        lh = sm
    cw = build_crosswalk(prof, corp_codes=cc, listing_history=lh)
    if len(cw):
        V.put_table(CFG.SHARED_CONTRIB_TABLES["crosswalk"], cw, scope="shared", domain="entity",
                    source="G2B bizr_no ↔ DART bizr_no exact match")
        V.flush("shared")
    return cw


def load_market(months: pd.DatetimeIndex, ctx: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """PIT 가격/시총/섹터 패널. 사용자 보유 PIT DB(공용 인덱스) 최우선."""
    if CFG.RUN_MODE != "SMOKE":
        M = load_market_panel(months)
        if M is not None and len(M):
            return M
    if "suppliers" in ctx:
        return build_market(ctx)["panel"]
    LOG.warn("가격 패널을 얻지 못했습니다 — 백테스트를 수행할 수 없습니다.")
    return pd.DataFrame(columns=["stock_code", "month", "ret", "mcap", "sector", "market"])


# ══════════════════════════════════════════════════════════════════════════════
#  2. GOLD — lifecycle · graph
# ══════════════════════════════════════════════════════════════════════════════
def build_gold(events: pd.DataFrame, crosswalk: pd.DataFrame,
               use_attr_linkage: bool = False) -> Dict[str, object]:
    L, diag = resolve_opportunities(events, use_attr=use_attr_linkage)
    L = attach_stock_code(L, crosswalk)
    L = allocate(L, "primary")
    if "broad_category" not in L.columns:
        L["broad_category"] = L.get("license_req", L["proc_type"])
    lc = opportunity_lifecycle(L)
    G = build_graph(L, crosswalk)
    return {"events": L, "link_diag": diag, "lifecycle": lc,
            "graph_nodes": G.nodes, "graph_edges": G.edges, "graph": G}


# ══════════════════════════════════════════════════════════════════════════════
#  3. PIT 피처
# ══════════════════════════════════════════════════════════════════════════════
def build_features(L: pd.DataFrame, months: pd.DatetimeIndex, market: pd.DataFrame,
                   pit_sales: Optional[pd.DataFrame] = None,
                   maturity_days: int = 365,
                   demand_col: str = "D1_DS_YOY",
                   win_col: str = "win_accel_log",
                   neutral_mode: str = "sector_size") -> Dict[str, pd.DataFrame]:
    """§17~§44 전체. 반환 dict 는 §89 산출물 이름을 따른다."""
    cap = build_capability(L, months)
    dem, lad = demand_panel(L, months)
    dem = exogeneity_split(L, dem, months)
    sp = stage_probability(L, months, maturity_days=maturity_days)
    swd = stage_weighted_demand(lad, sp, months)
    if len(swd):
        dem = dem.merge(swd, on=["category_cd", "month"], how="left")
        dem["demand_flow_w"] = dem["demand_flow_w"].fillna(0.0)
    lofo = lofo_adjustment(lad, L, months)
    tam = build_eligible_tam(cap, dem, lofo=lofo)

    win = build_win_features(L, months)
    win = add_size_normalization(win, market, pit_sales)
    brd = breadth_features(L, months)
    arf = award_rate_features(L, months)
    cmp_ = competition_features(L, months)
    fail = failure_features(L, months, cap)
    con = build_concentration(L, months)
    rev = contract_revision(L, months)

    F = build_demand_axis(tam)
    for X in (build_win_axis(win, primary=win_col), brd, arf, cmp_, fail, con, rev):
        if X is not None and len(X):
            F = F.merge(X, on=["stock_code", "month"], how="outer")
    # add_size_normalization 이 이미 mcap 을 붙였을 수 있다 → 중복 병합은 mcap_x/mcap_y 를 만든다
    mk = [c for c in ("sector", "market", "mcap", "turnover_value")
          if c in market.columns and c not in F.columns]
    if mk:
        F = F.merge(market[["stock_code", "month"] + mk], on=["stock_code", "month"], how="left")
    dup = [c for c in F.columns if c.endswith(("_x", "_y"))]
    if dup:
        raise RuntimeError(f"병합 접미사 충돌 컬럼이 생겼습니다: {dup} — 중복 병합을 제거하십시오.")
    F["PROC_RISK"] = proc_risk_score(F)
    F = build_dwa(F, demand_col=demand_col, win_col="W_PRIMARY", neutral_mode=neutral_mode)
    return {"company_capability_monthly": cap, "government_demand_monthly": dem,
            "eligible_tam_monthly": tam, "company_g2b_features_monthly": F,
            "stage_probability": sp, "demand_ladder": lad,
            "agency_capability": agency_capability(L, months)}


# ══════════════════════════════════════════════════════════════════════════════
#  4. 저장 — 로컬 data/ + 구글드라이브(공용/전용)
# ══════════════════════════════════════════════════════════════════════════════
GOLD_FILES = {"lifecycle": "g2b_opportunity_lifecycle", "crosswalk": "g2b_company_crosswalk",
              "graph_nodes": "g2b_demand_graph_nodes", "graph_edges": "g2b_demand_graph_edges",
              "contract_history": "g2b_contract_history"}
PIT_FILES = {"company_capability_monthly": "company_capability_monthly",
             "government_demand_monthly": "government_demand_monthly",
             "eligible_tam_monthly": "eligible_tam_monthly",
             "company_g2b_features_monthly": "company_g2b_features_monthly"}


def save_outputs(gold: Dict[str, object], feats: Dict[str, pd.DataFrame],
                 crosswalk: pd.DataFrame, backtest: Optional[Dict[str, pd.DataFrame]] = None
                 ) -> pd.DataFrame:
    """§89 산출물을 로컬과 드라이브에 남긴다. 공용/전용 구분은 재사용성 기준이다."""
    CFG.ensure_dirs()
    V = get_vault()
    rows = []

    def _put(df: pd.DataFrame, local_dir: str, name: str, scope: str, domain: str):
        if df is None or not len(df):
            rows.append({"산출물": name, "행수": 0, "위치": "—", "인덱스": "—"})
            return
        p = os.path.join(local_dir, f"{name}.parquet")
        atomic_write_parquet(df, p)
        V.put_table(name, df, scope=scope, domain=domain, source="g2b_demand_graph_v1",
                    extra={"run_id": CFG.run_id(), "df_sha256": df_hash(df)})
        rows.append({"산출물": name, "행수": len(df), "위치": os.path.relpath(p, CFG.PROJECT_ROOT),
                     "인덱스": ("공용 " + CFG.GDRIVE_SHARED_NS) if scope == "shared"
                                else ("전용 " + CFG.GDRIVE_PRIVATE_NS)})

    # 공용: 다른 전략도 그대로 쓸 수 있는 원장 (crosswalk, 계약이력)
    _put(crosswalk, CFG.GOLD_DIR, GOLD_FILES["crosswalk"], "shared", "entity")
    ev = gold.get("events")
    if isinstance(ev, pd.DataFrame) and len(ev):
        ch = ev[ev["stage"] == "CONTRACT"]
        _put(ch, CFG.GOLD_DIR, GOLD_FILES["contract_history"], "shared", "procurement")
        _put(ev, CFG.GOLD_DIR, "g2b_events_normalized", "shared", "procurement")
    # 전용: 이 연구의 해석물
    _put(gold.get("lifecycle"), CFG.GOLD_DIR, GOLD_FILES["lifecycle"], "private", "graph")
    _put(gold.get("graph_nodes"), CFG.GOLD_DIR, GOLD_FILES["graph_nodes"], "private", "graph")
    _put(gold.get("graph_edges"), CFG.GOLD_DIR, GOLD_FILES["graph_edges"], "private", "graph")
    for k, nm in PIT_FILES.items():
        _put(feats.get(k), CFG.PIT_DIR, nm, "private", "features")
    if backtest:
        for k, df in backtest.items():
            if isinstance(df, pd.DataFrame) and len(df):
                _put(df, CFG.BACKTEST_DIR, f"g2b_dwa_{k}", "private", "backtest")
    V.flush()
    V.compact("shared")
    V.compact("private")
    T = pd.DataFrame(rows)
    LOG.table(T.values.tolist(), list(T.columns), ["l", "r", "l", "l"],
              title="§89 산출물 저장 (로컬 + 구글드라이브 공용/전용 인덱스)")
    write_json(os.path.join(CFG.AUDIT_DIR, f"run_{CFG.run_id()}.json"),
               {"stamp": CFG.run_stamp(), "outputs": rows})
    return T
