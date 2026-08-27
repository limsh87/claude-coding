# -*- coding: utf-8 -*-
"""PIT 시각 3종 + 필드 등급(CLASS A/B/C) 레지스트리.

명세 §6 — 각 레코드에 세 시간을 구분한다.
    event_time            실제로 사건이 일어난 시각 (발주예정시기·공고일·개찰일·계약체결일)
    source_published_at   원천이 그 정보를 공개한 시각 (등록일시·공고일시)
    available_at          우리가 그 정보를 쓸 수 있게 된 시각 = published + 공개지연

명세 §6.1 — 필드 3등급
    CLASS A  당시 공개시각과 값이 확정적으로 복원됨            → 사용 허용
    CLASS B  변경이력으로 PIT 복원 가능                        → revision 유효기간 복원 후 사용
    CLASS C  현재 API 가 과거 '최종값'만 반환하고 변경과정 불명 → 역사적 백테스트 사용 금지
             (PIT_UNCERTIFIED 로 표시)
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core.log import LOG
from core.io import as_ts_series
# ── /PACKAGE IMPORTS ──

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

PIT_COLS = ("event_time", "source_published_at", "available_at")

# ── 공개지연(일). 발표가 장마감 전인지 확실하지 않으면 보수적으로 잡는다(§53) ──────────
#    나라장터는 등록 즉시 공개되지만 API 반영 지연이 존재하므로 스테이지별로 보수값을 둔다.
PUBLICATION_LAG_DAYS: Dict[str, float] = {
    "PLAN": 1.0,        # 발주계획: 게시 후 API 반영 지연
    "PRESPEC": 1.0,     # 사전규격
    "BID": 1.0,         # 입찰공고
    "AWARD": 1.0,       # 개찰/낙찰
    "CONTRACT": 2.0,    # 계약: 체결 후 등록까지 통상 더 걸린다
    "DART": 0.0,        # DART 는 접수시각 자체가 공개시각
}

# ══════════════════════════════════════════════════════════════════════════════
#  필드 등급 레지스트리 (§6.1)
#  ★ 여기 없는 필드는 자동으로 CLASS C 로 간주된다 — 모르면 쓰지 않는다가 기본값이다.
# ══════════════════════════════════════════════════════════════════════════════
FIELD_CLASS: Dict[str, str] = {}
FIELD_CLASS_NOTE: Dict[str, str] = {}


def declare(cls: str, fields: Sequence[str], note: str = "") -> None:
    assert cls in ("A", "B", "C")
    for f in fields:
        FIELD_CLASS[f] = cls
        FIELD_CLASS_NOTE[f] = note


declare("A", ["stage", "stage_rank", "doc_id", "agency_cd", "agency_nm", "proc_type",
              "event_time", "source_published_at", "available_at", "region_limit",
              "license_req", "category_cd", "category_nm", "broad_category"],
        "공고문에 그대로 실려 당시 값이 확정 복원됨")
declare("A", ["plan_budget_amt", "prespec_budget_amt", "bid_base_amt", "bid_est_amt"],
        "각 단계 공고 시점의 금액 — 그 시점 문서에 확정 기재")
declare("A", ["award_amt", "award_rate", "expected_price", "open_dt", "supplier_bizno",
              "supplier_nm", "bidder_count", "award_rank"],
        "개찰 결과는 개찰 시점에 확정 공개")
declare("B", ["bid_amt_current", "contract_amt_current", "bid_status", "contract_status",
              "revision_no", "valid_from", "valid_to", "is_cancelled", "is_rebid"],
        "변경이력 API 로 각 리비전의 유효기간을 복원해 사용")
declare("C", ["contract_final_amt", "contract_revision_ratio_final", "lifecycle_final_outcome",
              "final_winner", "total_contract_including_future_change",
              "reached_stage", "max_stage_rank", "winner_bizno", "winner_nm", "last_seen",
              "t_CONTRACT", "amt_CONTRACT"],
        "현재 API 가 과거 최종값만 반환 — 변경과정 복원 불가 → 역사적 백테스트 사용 금지")

# ── 정규 스키마 컬럼 (collectors.base.CANON_COLS) 등급 ─────────────────────────
#    'amount' 는 단계별 공고문에 확정 기재되지만 변경공고로 바뀔 수 있으므로 CLASS B 다:
#    리비전 유효구간을 복원해야만 PIT 로 쓸 수 있다. 이 구분을 흐리면 §8 이 무의미해진다.
declare("B", ["amount", "attributed_amount", "doc_seq", "amount_kind"],
        "각 판본 금액 — 변경이력으로 유효기간 복원 후 사용(§8)")
declare("A", ["title", "method", "share_ratio"],
        "공고문·개찰결과에 그 시점 값이 그대로 기재됨")
declare("B", ["status_raw"],
        "공고종류/상태는 변경공고로 바뀐다 — 리비전 유효기간 복원 후 사용")
declare("A", ["service", "operation", "raw_uid", "opportunity_id", "pit_stage",
              "published_imputed", "demand_agency_cd", "demand_agency_nm",
              "link_bid_no", "link_plan_no", "link_prespec_no", "link_contract_no",
              "link_method", "link_score", "link_known_at", "giant_component",
              "consortium_flag", "consortium_unknown_share", "alloc_mode",
              "map_type", "stock_code", "synthetic", "broad_category", "month"],
        "수집 시점에 확정되어 이후 바뀌지 않는 식별·구조 필드")


def field_class(name: str) -> str:
    return FIELD_CLASS.get(name, "C")


def assert_pit_safe(cols: Sequence[str], where: str = "") -> None:
    """CLASS C 필드가 팩터 계산에 들어오면 즉시 막는다. 우회 파라미터를 두지 않는다."""
    bad = [c for c in cols if field_class(c) == "C"]
    if bad:
        raise PermissionError(
            f"[PIT_UNCERTIFIED] CLASS C 필드를 역사적 계산에 사용할 수 없습니다 (§6.1): {bad}"
            + (f" — 위치: {where}" if where else "")
            + "\n  CLASS C = 현재 API 가 과거 '최종값'만 돌려주고 변경과정을 알 수 없는 필드입니다.")


def class_table() -> pd.DataFrame:
    return pd.DataFrame({"field": list(FIELD_CLASS), "pit_class": list(FIELD_CLASS.values()),
                         "note": [FIELD_CLASS_NOTE.get(f, "") for f in FIELD_CLASS]}
                        ).sort_values(["pit_class", "field"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PIT 스탬프 부여
# ══════════════════════════════════════════════════════════════════════════════
def stamp(df: pd.DataFrame, event_col: str, published_col: Optional[str] = None,
          stage: str = "BID", lag_days: Optional[float] = None) -> pd.DataFrame:
    """event_time / source_published_at / available_at 세 컬럼을 붙인다.

    published 가 없으면 event_time 을 공개시각으로 쓰되, 그 사실이 감사표에 남도록
    `published_imputed` 플래그를 세운다. 조용히 같은 값으로 만들지 않는다.
    """
    d = df.copy()
    ev = as_ts_series(d[event_col]) if event_col in d.columns else pd.Series(pd.NaT, index=d.index)
    if published_col and published_col in d.columns:
        pb = as_ts_series(d[published_col])
        imputed = pb.isna()
        pb = pb.fillna(ev)
    else:
        pb = ev.copy()
        imputed = pd.Series(True, index=d.index)
    lag = float(PUBLICATION_LAG_DAYS.get(stage, 1.0) if lag_days is None else lag_days)
    d["event_time"] = ev
    d["source_published_at"] = pb
    # 공개시각을 모르면 event_time 기준이므로 보수적으로 지연을 더 얹는다.
    extra = np.where(imputed.to_numpy(), 1.0, 0.0)
    d["available_at"] = pb + pd.to_timedelta(lag + extra, unit="D")
    d["published_imputed"] = imputed.to_numpy()
    d["pit_stage"] = stage
    return d


def require_pit(df: pd.DataFrame, where: str = "") -> pd.DataFrame:
    """PIT 컬럼이 없으면 KeyError 로 거부한다 — 우회 인자를 의도적으로 만들지 않았다."""
    miss = [c for c in PIT_COLS if c not in df.columns]
    if miss:
        raise KeyError(f"PIT 컬럼 누락 {miss} — {where or 'unknown'} (명세 §6). "
                       f"pit.timestamps.stamp() 을 먼저 통과시키십시오.")
    bad = int((df["available_at"] < df["source_published_at"]).sum())
    if bad:
        raise ValueError(f"available_at < source_published_at 인 행 {bad:,}개 — {where}. "
                         f"이는 정의상 불가능하며 미래누수의 직접 증거입니다.")
    return df


def audit_lag(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """event → published → available 지연 분포. 커버리지 보고서(§94 01_PIT_AUDIT)용."""
    d = require_pit(df, name)
    lag1 = (d["source_published_at"] - d["event_time"]).dt.total_seconds() / 86400.0
    lag2 = (d["available_at"] - d["source_published_at"]).dt.total_seconds() / 86400.0
    q = lambda s, p: float(np.nanpercentile(s.dropna(), p)) if s.notna().any() else np.nan
    return pd.DataFrame([{
        "table": name, "rows": len(d),
        "event_time_결측률": float(d["event_time"].isna().mean()),
        "published_추정률": float(d.get("published_imputed", pd.Series(False, index=d.index)).mean()),
        "pub-event_p50": q(lag1, 50), "pub-event_p95": q(lag1, 95),
        "avail-pub_p50": q(lag2, 50),
        "event_min": d["event_time"].min(), "event_max": d["event_time"].max(),
    }])


# ══════════════════════════════════════════════════════════════════════════════
#  파생 피처 등급 (§6.1 확장)
#
#  파생 피처는 '원천 필드'가 아니라 그 함수다. 따라서 등급은 입력의 등급을 물려받는다:
#  아래 목록은 전부 CLASS A/B 입력만으로, 시점 t 까지 available_at 인 이벤트만 써서
#  계산된다는 것을 개발자가 명시적으로 선언한 것이다.
#
#  ★ 여기 없는 피처는 자동으로 CLASS C 가 되어 파이프라인이 멈춘다.
#    새 피처를 추가하려면 반드시 여기에 등급을 선언해야 한다 — 그것이 이 장치의 목적이다.
# ══════════════════════════════════════════════════════════════════════════════
DERIVED_FEATURES = [
    # capability / TAM (§17 §21)
    "capability", "decayed_award", "firm_decayed_total", "n_obs_36m", "first_award_month",
    "months_since_first_award", "warmed_up", "agency_share", "capability_hhi",
    "n_active_categories",
    "eligible_demand_flow", "eligible_demand_flow_3m", "eligible_demand_flow_12m",
    "eligible_pipeline_stock", "eligible_demand_flow_lofo",
    # 정부수요 (§20 §24 §45 §83)
    "demand_flow", "demand_flow_3m", "demand_flow_12m", "demand_flow_w", "pipeline_stock",
    "n_new_opp", "own_flow_known", "incumbent_share", "new_agency_flow_share",
    "best_amount", "is_advance", "is_revision", "is_first_seen", "amount_increment",
    "D1_DS_YOY", "D1_DS_YOY_LOFO", "D2_PIPELINE", "D2_PIPELINE_YOY",
    # 단계확률 (§22 §23)
    "p_contract", "n_train", "p_source",
    # 수주 실현 (§25 §26 §27)
    "award_amt", "award_n", "contract_amt", "contract_n",
    "award_amt_3m", "award_amt_6m", "award_amt_12m", "award_amt_ttm", "award_amt_prev9m",
    "award_n_3m", "award_n_6m", "award_n_12m", "contract_amt_12m", "award_ttm_lag12",
    "win_accel_rate", "win_accel_log", "W_PRIMARY",
    "WIN_MCAP", "WIN_MCAP_3M", "WIN_SALES", "CONTRACT_MCAP", "CONTRACT_SALES",
    "pit_revenue", "sales_filing_ts",
    # 저변 (§30 §31 §32)
    "new_agency_count", "new_agency_amt", "tot_agency_amt", "new_agency_award_share",
    "active_agency_count", "new_category_count", "new_category_amt", "tot_category_amt",
    "new_category_award_share", "active_category_count",
    "repeat_pairs", "active_pairs", "REPEAT_WIN_RATE", "breadth_warmed_up",
    # 경쟁·낙찰률 (§35 §36 §37) — 진단용이며 PRIMARY 부호를 붙이지 않는다
    "award_rate_use", "award_rate_mean", "resid_award_rate", "award_rate_n",
    "bidder_count_mean", "resid_bidder_count", "fail_rate", "rebid_rate",
    "FAIL_RATE_exposure", "REBID_RATE_exposure",
    # 집중도·위험 (§33 §34 §40 §41 §42 §43)
    "AGENCY_HHI", "CATEGORY_HHI", "TOP1_SHARE", "TOP3_SHARE", "PROC_RISK",
    "CONTRACT_REVISION_RATIO", "contract_increase_n", "contract_decrease_n",
    "contract_cancel_n", "contract_delta_amt",
    # PRIMARY (§28 §44)
    "P_D", "P_W", "G2B_DWA",
    "P_D_raw", "P_W_raw", "G2B_DWA_raw", "P_D_sec", "P_W_sec", "G2B_DWA_sec",
    "P_D_secsz", "P_W_secsz", "G2B_DWA_secsz",
    # 시장 속성 (PIT 가격 DB 에서 온 당시 값)
    "sector", "market", "mcap", "turnover_value", "ret", "close", "shares", "name",
    "listing_date", "delisting_date", "delisted",
]
declare("A", DERIVED_FEATURES,
        "CLASS A/B 입력만으로 available_at <= t 이벤트에서 계산된 파생 피처")

# 미래수익률 계열 — 신호에 들어가면 절대 안 되는 것들을 명시적으로 C 로 못박는다(§1.1 §7)
declare("C", ["forward_return", "future_price", "future_market_cap", "future_financial",
              "future_contract_outcome", "future_winner", "future_revenue",
              "fwd_ret_1m", "fwd_ret_3m", "fwd_ret_6m", "fwd_ret_12m",
              "fwd_award_3m", "fwd_award_6m", "fwd_award_12m",
              "fwd_contract_3m", "fwd_contract_6m", "fwd_contract_12m"],
        "미래정보 — 신호/팩터 입력으로 사용 금지. 성과검정과 메커니즘 검정에서만 등장한다.")
