# -*- coding: utf-8 -*-
"""사전등록 동결 · 시험 장부 · FUTURE_RETURN_LOCK 해제.   §1.1 · §77 · §78

동결이란 무엇인가:
  ① 4개 config YAML + audit/trial_ledger.json 의 내용을 확정하고
  ② 그 SHA256 을 audit/prereg_hash.txt 에 기록하는 것.
그 이후에만 FUTURE_RETURN_LOCK 이 풀린다. 동결 이후 파일을 고치면 해시가 어긋나
잠금이 자동으로 다시 걸린다 — 사후에 정의를 바꾸는 것을 구조로 막는다.

★ 동결 시점에 넣는 데이터 기반 값(MATURITY_EMBARGO, USABLE_START_DATE)은
  반드시 '수익률을 보기 전' 감사 결과로만 정한다(§23 §48).
"""
from __future__ import annotations
# ── PACKAGE IMPORTS ──
from core import config as CFG
from core.log import LOG
from core.io import write_json, read_json, atomic_write_text
# ── /PACKAGE IMPORTS ──

import os
import datetime as _dt
from typing import Any, Dict, List, Optional

import pandas as pd

# §77 — 시작 전 모두 등록해야 하는 알파 후보 전체 장부
TRIAL_CANDIDATES: List[Dict[str, Any]] = [
    {"id": "D1", "name": "Demand Flow", "column": "D1_DS_YOY", "family": "demand",
     "spec": "§24", "hypothesis": "역량정합 신규 정부수요의 YoY 증가가 향후 수익률을 예측한다"},
    {"id": "D2", "name": "Forward Pipeline", "column": "D2_PIPELINE_YOY", "family": "demand",
     "spec": "§24", "hypothesis": "이미 공개되었으나 미집행인 파이프라인 잔량 증가가 선행신호다"},
    {"id": "W1", "name": "Award / MCap", "column": "WIN_MCAP", "family": "win",
     "spec": "§26", "hypothesis": "시총 대비 수주 규모가 클수록 향후 수익률이 높다"},
    {"id": "W2", "name": "Award / Sales", "column": "WIN_SALES", "family": "win",
     "spec": "§26", "hypothesis": "PIT 매출 대비 수주 규모가 클수록 향후 수익률이 높다"},
    {"id": "W3", "name": "Win Acceleration", "column": "win_accel_log", "family": "win",
     "spec": "§27", "hypothesis": "수주의 가속(TTM 로그차분)이 향후 수익률을 예측한다"},
    {"id": "A1", "name": "Demand-Win Alignment", "column": "G2B_DWA", "family": "primary",
     "spec": "§28", "hypothesis": "수요이동과 수주전환이 동시에 강한 기업이 초과수익을 낸다",
     "is_primary": True},
    {"id": "B1", "name": "New Agency Breadth", "column": "new_agency_count", "family": "breadth",
     "spec": "§30", "hypothesis": "신규 발주기관 확대가 고객저변 확장을 뜻한다"},
    {"id": "B2", "name": "New Category Entry", "column": "new_category_award_share",
     "family": "breadth", "spec": "§31", "hypothesis": "신규 사업영역 진입이 성장을 예고한다"},
    {"id": "B3", "name": "Repeat Win", "column": "REPEAT_WIN_RATE", "family": "breadth",
     "spec": "§32", "hypothesis": "반복수주는 경쟁력일 수도, 의존성일 수도 있다 — 부호 미확정"},
    {"id": "R1", "name": "Agency Concentration", "column": "AGENCY_HHI", "family": "risk",
     "spec": "§33", "hypothesis": "발주기관 집중은 위험이다 — 부호 미확정"},
    {"id": "R2", "name": "Category Concentration", "column": "CATEGORY_HHI", "family": "risk",
     "spec": "§34", "hypothesis": "품목 집중은 위험이다 — 부호 미확정"},
    {"id": "R3", "name": "Mega Deal", "column": "TOP1_SHARE", "family": "risk",
     "spec": "§41", "hypothesis": "단일 초대형 계약 의존은 위험이다 — 부호 미확정"},
    {"id": "R4", "name": "Contract Revision", "column": "CONTRACT_REVISION_RATIO",
     "family": "risk", "spec": "§40", "hypothesis": "계약 감액·취소는 악재다 — 부호 미확정"},
    {"id": "C1", "name": "Competition", "column": "resid_bidder_count", "family": "diagnostic",
     "spec": "§35 §76", "hypothesis": "경쟁강도 — 부호가 조달방식마다 다르므로 PRIMARY 에 넣지 않는다"},
]


def build_trial_ledger(extra: Optional[List[dict]] = None) -> dict:
    """§77 — 성과를 보기 전에 후보를 전부 등록한다. 나중에 추가하려면 여기 먼저 등록해야 한다."""
    return {
        "version": "v1",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "rule": ("성과를 본 뒤 후보를 추가하거나 정의를 바꾸지 않는다. "
                 "추가 후보가 생기면 성과를 보기 전에 이 장부에 등록한다(§77)."),
        "primary": "A1",
        "multiple_testing": {"method": "BH/FDR", "q": 0.10,
                             "scope": "primary 를 제외한 secondary family 전체(§78)"},
        "candidates": TRIAL_CANDIDATES + list(extra or []),
        "n_candidates": len(TRIAL_CANDIDATES) + len(extra or []),
    }


def _patch_yaml_scalar(path: str, key: str, value: Any) -> bool:
    """'key: null' 한 줄을 실측값으로 채운다. YAML 재작성(주석 유실)을 피하려고 줄 단위로 바꾼다."""
    if not os.path.exists(path):
        return False
    src = open(path, encoding="utf-8").read()
    out, done = [], False
    for ln in src.split("\n"):
        stripped = ln.strip()
        if not done and stripped.startswith(key + ":"):
            indent = ln[:len(ln) - len(ln.lstrip())]
            rest = ln.split("#", 1)
            comment = ("  #" + rest[1]) if len(rest) > 1 else ""
            v = "null" if value is None else (f'"{value}"' if isinstance(value, str) else str(value))
            out.append(f"{indent}{key}: {v}{comment}")
            done = True
        else:
            out.append(ln)
    if done:
        atomic_write_text(path, "\n".join(out))
    return done


def freeze(maturity_embargo_days: Optional[int] = None,
           usable_start_date: Optional[str] = None,
           extra_candidates: Optional[List[dict]] = None,
           notes: str = "") -> dict:
    """사전등록 동결. 반환은 기록된 매니페스트."""
    CFG.ensure_dirs()
    materialize_templates()
    missing = [f for f in CFG.PREREG_FILES if not os.path.exists(os.path.join(CFG.CONFIG_DIR, f))]
    if missing:
        raise FileNotFoundError(f"사전등록 파일이 없습니다: {missing} — config/ 를 먼저 작성하십시오.")

    if maturity_embargo_days is not None:
        ok = _patch_yaml_scalar(os.path.join(CFG.CONFIG_DIR, "factor_preregistration.yaml"),
                                "maturity_embargo_days", int(maturity_embargo_days))
        LOG.info(f"MATURITY_EMBARGO = {maturity_embargo_days}일 동결 "
                 f"(실측 분포 기반, 수익률 미열람 상태) {'✔' if ok else '— 키를 찾지 못함'}")
    if usable_start_date is not None:
        ok = _patch_yaml_scalar(os.path.join(CFG.CONFIG_DIR, "universe_definition.yaml"),
                                "usable_start_date", str(usable_start_date))
        LOG.info(f"USABLE_START_DATE = {usable_start_date} 동결 "
                 f"(데이터 커버리지만 보고 결정) {'✔' if ok else '— 키를 찾지 못함'}")

    write_json(CFG.TRIAL_LEDGER, build_trial_ledger(extra_candidates))
    man = CFG.prereg_manifest()
    rec = {"frozen_at": _dt.datetime.now().isoformat(timespec="seconds"),
           "files": man, "run_stamp": CFG.run_stamp(), "notes": notes,
           "declaration": ("이 시점 이후에만 미래수익률을 열람한다. 이 파일들을 수정하면 "
                           "해시가 어긋나 FUTURE_RETURN_LOCK 이 자동으로 다시 걸린다.")}
    write_json(CFG.PREREG_HASH_FILE, rec)
    st = CFG.prereg_status()
    if not st["frozen"]:
        raise RuntimeError(f"동결 실패: {st['reason']}")
    LOG.ok("사전등록 동결 완료 — FUTURE_RETURN_LOCK = FALSE")
    for k, v in man.items():
        LOG.info(f"  {k}  sha256={v[:16]}…")
    return rec


def verify() -> pd.DataFrame:
    st = CFG.prereg_status()
    man = st["manifest"]
    rec = (st["recorded"] or {}).get("files", {})
    rows = [{"파일": k, "현재 sha256": v[:16] + "…",
             "동결 sha256": (rec.get(k, "—")[:16] + "…") if rec.get(k) else "—",
             "일치": "✔" if rec.get(k) == v else "✖"} for k, v in sorted(man.items())]
    rows.append({"파일": "FUTURE_RETURN_LOCK", "현재 sha256": "",
                 "동결 sha256": "", "일치": "FALSE(해제)" if st["frozen"] else "TRUE(잠김)"})
    return pd.DataFrame(rows)


def ledger_table() -> pd.DataFrame:
    d = read_json(CFG.TRIAL_LEDGER, {}) or {}
    c = d.get("candidates", [])
    if not c:
        return pd.DataFrame()
    return pd.DataFrame([{"ID": x["id"], "이름": x["name"], "컬럼": x["column"],
                          "계열": x["family"], "명세": x["spec"],
                          "PRIMARY": "★" if x.get("is_primary") else "",
                          "가설": x["hypothesis"][:52]} for x in c])

# ══════════════════════════════════════════════════════════════════════════════
#  사전등록 YAML 템플릿 (단일파일 배포용 내장본)
#  config/ 에 파일이 없으면 이 템플릿을 '쓰기'만 한다. 이미 있으면 절대 덮어쓰지 않는다
#  — 사용자가 손으로 고친 사전등록을 코드가 되돌리면 §1.1 이 무의미해지기 때문이다.
# ══════════════════════════════════════════════════════════════════════════════
PREREG_TEMPLATES = {
    "factor_preregistration.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  G2B-DEMAND-GRAPH-V1 — 팩터 사전등록 (§1.1)
#  이 파일이 동결(SHA256 기록)되기 전에는 FUTURE_RETURN_LOCK 이 풀리지 않는다.
#  동결 이후 이 파일을 고치면 해시가 어긋나 잠금이 자동으로 다시 걸린다.
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
frozen_by: "scripts/09_freeze_preregistration.py"

primary_factor:
  name: G2B_DWA
  formula: "sqrt(P_D * P_W)"
  description: "Demand-Win Alignment — 역량정합 정부수요 이동(D)과 실제 수주전환(W)의 기하평균"
  neutralization: sector_size          # §44 PRIMARY 는 sector + log(mcap) 중립
  min_cross_section_n: 20              # 월별 스코어 기업이 이보다 적으면 그 달은 NaN
  # ── D 축 (정부수요 이동) ──────────────────────────────────────────────────
  demand_axis:
    column: D1_DS_YOY
    formula: "log1p(EligibleDemandFlow_3M_t) - log1p(EligibleDemandFlow_3M_{t-12})"
    source_stages: [PLAN, PRESPEC, BID]     # §20 winner 를 보기 전 단계만
    leave_one_firm_out: true                # §45 (이미 알려진 자사 낙찰건 제외)
    stage_probability_weighted: true        # §22
  # ── W 축 (실제 수주 전환) ─────────────────────────────────────────────────
  win_axis:
    column: win_accel_log
    formula: "log1p(TTM award) - log1p(TTM award 12M ago)"
    alternative_not_used: win_accel_rate    # §27 둘 다 산출하되 PRIMARY 는 하나만 동결
    amount_basis: attributed_amount         # §16 컨소시엄 지분 반영, 지분불명은 제외

capability:                                  # §17
  lookback_months: 36
  halflife_months: 18
  source_stages: [AWARD]
  normalization: "share of firm's decayed award across categories"
  warmup_required_months: 36                 # §19

stage_probability:                           # §22 §23
  method: walk_forward_hierarchical_shrinkage
  hierarchy: [category, broad_category, proc_type, global]
  shrink_k: 25.0
  maturity_embargo_days: 427  # ← 09 스크립트가 실측 분포 p90 으로 채우고 동결
  training_rule: "label_available_at <= t 인 라벨만 사용 (training_end < t)"

secondary_factors:                           # §78 PRIMARY 는 하나, 나머지는 전부 Secondary
  - D1_DS_YOY
  - D2_PIPELINE_YOY
  - WIN_MCAP
  - WIN_SALES
  - win_accel_rate
  - new_agency_count
  - new_category_award_share
  - REPEAT_WIN_RATE
  - AGENCY_HHI
  - CATEGORY_HHI
  - TOP1_SHARE
  - CONTRACT_REVISION_RATIO
  - resid_bidder_count
multiple_testing: "BH/FDR q=0.10 across secondary family"

risk_track:                                  # §42 §43 — PRIMARY 와 섞지 않는다
  name: PROC_RISK
  components: [AGENCY_HHI, CATEGORY_HHI, TOP1_SHARE]
  combination: "mean of monthly cross-sectional percentiles"
  hard_exclusion: false
  mixed_with_primary: false

nested_comparison:                           # §84 §99 — 이 표가 연구의 최종 판정 근거
  - Award_Amount_only
  - Award_over_MCap
  - Demand_Shift_only
  - Win_Acceleration_only
  - Demand_Win_Alignment
decision_rule: "Full 모델이 단순모델을 명백히 이기지 못하면 단순모델을 채택한다(§99)."
""",
    "universe_definition.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  투자 유니버스 정의 (§49 · §50 · §51)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
markets: [KOSPI, KOSDAQ]
security_type: 보통주
exclude:
  - SPAC
  - 우선주
  - ETF
  - ETN
  - REITs            # §49 별도 취급
point_in_time: true
survivorship_bias_free: true
delisted_included: true
delisting_return: -1.0                # 정리매매 정보가 없으면 -100% (누락 처리 금지)
admin_issue_rule: "관리·정지 여부는 당시 정보 기준으로만 판정"

liquidity:
  min_20d_turnover_value_krw: 300000000
  applied_at: signal_date

procurement_observability:            # §50 — 조달기업만으로 universe 를 사후 정의하지 않는다
  report_both: true
  definitions:
    all_tradable: "PIT 상장 보통주 전체"
    procurement_observable: "t 시점까지 G2B 낙찰이 1건 이상 '관측된' 기업"
  forbidden: "현재 나라장터 등록업체 명단으로 과거 universe 를 만드는 것"

usable_start_date: "2018-01-31"  # ← 01/03 감사 결과로 09 스크립트가 채우고 동결
usable_end_date: "2026-07-31"
warmup_months: 36

coverage_gate:                        # §51
  median_scored_firms_min: 100
  p10_scored_firms_min: 60
  median_holdings_min: 20
  fail_label: SAMPLE_COLLAPSE

entity_mapping_gate:                  # §52
  primary_allowed_types: [EXACT_ID, VERIFIED_MANUAL]
  forbidden: "기업명 fuzzy matching 만으로 자동 확정"
  report_shares_by: amount
""",
    "pit_policy.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  Point-in-Time 정책 (§6 · §7 · §8 · §11 · §53 · §57 · §58)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
timestamps: [event_time, source_published_at, available_at]
revision_fields: [valid_from, valid_to, revision_no]

publication_lag_days:                 # available_at = source_published_at + lag
  PLAN: 1
  PRESPEC: 1
  BID: 1
  AWARD: 1
  CONTRACT: 2
  DART: 0
imputed_published_extra_lag_days: 1   # 공개시각을 모르면 보수적으로 하루 더

field_classes:                        # §6.1
  A: "당시 공개시각·값이 확정 복원 → 사용 허용"
  B: "변경이력으로 각 리비전 유효기간 복원 후 사용"
  C: "과거 최종값만 반환·변경과정 불명 → 역사적 백테스트 사용 금지 (PIT_UNCERTIFIED)"
unknown_field_default: C              # 모르면 쓰지 않는다

double_counting:                      # §8 §11
  rule: "opportunity 별 '가장 진척된 단계' 계단함수의 증분만 신규수요로 센다"
  guarantee: "증분 총합 == 최종 알려진 금액 (구조적 보존)"
  cancel_rebid_handling: "금액이 아니라 상태변수로 보관"

signal_timing:                        # §53
  rebalance: MONTHLY
  signal_cutoff: "월말까지 available_at 이 도달한 정보만"
  execution: "T+1 (장마감 전 공개 여부가 불확실하면 보수적으로 T+1)"

price_pit:                            # §57
  forbidden:
    - "현재 수정주가 파일에서 상폐종목 삭제"
    - "현재 상장주식수 과거 소급"
    - "현재 섹터분류 과거 소급"
  total_return: true
  include_delisting_loss: true

financial_pit:                        # §58
  rule: "filing_timestamp <= signal_timestamp 인 최신 재무제표만"
  filing_timestamp_source: "rcept_no 앞 8자리 (접수일자)"
  fallback_if_missing: "결산일 + 90일 (보수적)"

consortium:                           # §16
  primary_rule: "지분 있으면 지분비율, 없으면 UNKNOWN_SHARE_CONSORTIUM 으로 금액 팩터 제외"
  sensitivity_modes: [equal_split, winner_only, full_allocation]

linkage:                              # §10
  priority: [OFFICIAL_ID, PROCESS_LEDGER, DETERMINISTIC_ATTR, TEXT_SIMILARITY]
  primary_enabled: [OFFICIAL_ID, PROCESS_LEDGER]
  record_fields: [link_method, link_score, link_known_at]
  rule: "애매한 연결을 억지로 확정하지 않는다. 연결 실패 != 사건 실패(§2.F)"
""",
    "backtest_policy.yaml": r"""
# ══════════════════════════════════════════════════════════════════════════════
#  백테스트 정책 (§53 ~ §62, §79)
# ══════════════════════════════════════════════════════════════════════════════
version: "v1"
rebalance: MONTHLY
execution_lag: "T+1"
portfolio:
  primary: "G2B_DWA 상위 20% (Long-only)"
  quantiles: 5
  report: [Q1, Q2, Q3, Q4, Q5, "Q5-Universe", "Q5-Q1"]
  weighting_primary: equal_weight       # §56
  weighting_secondary: rank_weight
  weighting_diagnostic: cap_weight
  max_position_weight: 0.10
  min_holdings: 10

costs:                                  # §59 고정 0bp 백테스트를 최종성과로 쓰지 않는다
  commission_bps: 1.5
  slippage_bps: 15.0
  market_impact_model: "sqrt(participation) * spread_proxy"
  sell_tax_schedule:                    # 당시 제도 기준 (매도 시 거래세, KOSPI 는 농특세 포함)
    - {from: "2015-01-01", kospi_bps: 30.0, kosdaq_bps: 30.0}
    - {from: "2019-06-03", kospi_bps: 25.0, kosdaq_bps: 25.0}
    - {from: "2021-01-01", kospi_bps: 23.0, kosdaq_bps: 23.0}
    - {from: "2023-01-01", kospi_bps: 20.0, kosdaq_bps: 20.0}
    - {from: "2025-01-01", kospi_bps: 18.0, kosdaq_bps: 18.0}
  stress_multipliers: [1.0, 2.0, 3.0]

statistics:                             # §60 §61 §62
  report: [CAGR, ann_return, volatility, Sharpe, MDD, Calmar, turnover,
           avg_holdings, median_holdings, hit_ratio]
  newey_west_lags: 6
  ic: [spearman, rank]
  fama_macbeth_controls: [log_mcap, value, momentum, profitability, volatility, sector_FE]

pass_criteria:                          # §79
  DATA_PASS: ["PIT 복원 가능", "exact match 충분", "표본 붕괴 없음",
              "lifecycle 중복제거 성공", "revision 처리 성공"]
  ALPHA_PASS: {net_alpha_gt: 0.0, newey_west_t_min: 2.0, late_period_direction: positive}
  STRONG_PASS: {net_annual_excess_min: 0.03, newey_west_t_min: 2.0,
                late_period_positive: true, cost_2x_positive: true,
                loyo_mostly_positive: true, mega_deal_removed_positive: true,
                top_contributors_removed_positive: true}
  rule: "숫자를 못 넘겼다고 정의를 바꾸어 다시 탐색하지 않는다."

robustness_required:                    # §65 ~ §75
  - time_thirds
  - by_year
  - leave_one_year_out
  - leave_one_agency_out
  - leave_one_category_out
  - mega_contract_winsorize: [0.001, 0.005, 0.01]
  - drop_top_contributors: [1, 3, 5, 10]
  - by_size_bucket
  - by_market
  - by_sector
  - placebo_permutation
  - temporal_placebo
""",
}


def materialize_templates() -> list:
    """config/ 에 없는 사전등록 파일만 템플릿으로 생성한다. 반환은 생성된 파일 목록."""
    CFG.ensure_dirs()
    made = []
    for fn, body in PREREG_TEMPLATES.items():
        p = os.path.join(CFG.CONFIG_DIR, fn)
        if not os.path.exists(p):
            atomic_write_text(p, body)
            made.append(fn)
    if made:
        LOG.info(f"사전등록 템플릿 생성: {made} (기존 파일은 건드리지 않았습니다)")
    return made
