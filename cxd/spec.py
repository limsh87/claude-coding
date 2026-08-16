# -*- coding: utf-8 -*-
"""사전등록 상수(SPEC) + 동결 장치 — U250-F1 / F-11 CXD v1.0.

명세서 PART 3.2·PART 5 의 금지사항은 "그러지 않겠다"는 약속이 아니라 **구조**여야 한다.
  · CXD 상수는 SpecLock 으로 잠긴다 → 실행 중 대입하면 SpecViolation
  · 어블레이션 arm 은 4개에서 상한이 걸린다 → 5번째 등록 시 예외 (KILL-6)
  · 미래수익률은 ReturnLock 이 잠그고, 사람이 해제 사유를 적어야만 열린다
  · 폐기(KILL) 발동 후 해상도·PIT·창길이·임계값을 바꿔 되살리는 경로를 만들지 않았다
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class SpecViolation(Exception):
    """사전등록 위반. 코드를 고치기 전에 명세 개정(버전 상향)을 먼저 하라는 뜻."""


class KillCriteria(Exception):
    """PART 5 폐기 조건 발동. 되살리기 금지 — 새 팩터 ID 로 재등재해야 한다."""


class SpecLock(dict):
    """한 번 정해진 값은 실행 중 바뀌지 않는다."""

    def __init__(self, name: str, d: dict):
        super().__init__(d)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_frozen", True)

    def __setitem__(self, k, v):
        if getattr(self, "_frozen", False):
            raise SpecViolation(
                f"[{self._name}] 사전등록 상수 '{k}' 를 실행 중에 바꾸려 했습니다. "
                f"명세서 PART 5 '되살리기 금지' 위반입니다. 정말 바꿔야 한다면 코드가 아니라 "
                f"명세서 버전을 올리고 새 팩터 ID 로 trials ledger 에 등재하세요.")
        super().__setitem__(k, v)

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


FACTOR_ID = "F-11"
FACTOR_CODE = "CXD"
SPEC_VERSION = "1.0"
SPEC_TITLE = "관세청 통관데이터 기반 산업-기업 성장 괴리"

# ── PART 0. 상속받는 프레임 (읽기 전용. CXD 는 여기에 쓰지 않는다) ──────────────────────────
FRAME = SpecLock("FRAME", dict(
    universe="U250",                    # 7게이트, 250종목, 분기 리밸런싱
    event_filter="F1",                  # CB/BW/제3자배정 유상증자/최대주주변경, 직전 12M
    candidate_set="C1",                 # C1 = U250 − F1사건, 중앙값 ≈ 171종목
    anchor_cagr_spread=0.046500,        # C1 − U250 순 CAGR = +4.6500%p ± 0.0100%p
    anchor_tol=0.000100,
    research_start="2016-08-01",
    research_end="2026-07-31",
    n_rebalances=41,
    anchor_factor="RESC",               # 성분 P_RS, P_EG
    pit_rule="rcept_dt + 1 거래일",
))

# ── PART 3.2 동결 상수 — 성과를 보기 전에 고정. 튜닝 금지 ───────────────────────────────────
CXD = SpecLock("CXD", dict(
    CELL_AXIS="SINSUNGJIL_SEBUN",   # Phase 0(G-C6)에서 최종 확정 후 동결
    KSIC_LEVEL=3,                    # 소분류
    CUSTOMS_PIT_DAYS=45,             # 참조월말 + 45일
    FGR_LOOKBACK_Q=8,                # 주 버전 = 2년
    FGR_ALT_Q=4,                     # 어블레이션 arm
    TREND_MONTHS=60,
    COLLAPSE_FLOOR=0.50,
    MIN_CELL_COV=0.90,               # IEG 결측 셀 비율 상한 10%
    GATE_LINK_RATIO=0.40,            # G-C3 통과 기준
    GATE_JACCARD=0.70,               # G-C2 매핑 오염 기준
    MAX_ABLATION_ARM=4,              # 5번째 arm 생성 금지
))

# ── 파생 규약 (명세서 본문에 명시된 것만. 추가 자유도를 만들지 않는다) ──────────────────────
RULES = SpecLock("RULES", dict(
    winsor=(0.01, 0.99),             # §3.1 [2][5] winsorize
    resid_x=("P_RS", "P_EG", "RET_12M", "LOG_MKTCAP"),   # §3.1 [6]
    div_x="IEG",                     # §3.1 [5] 풀링 횡단면 회귀 1개 계수
    trend_active_min=0.0,            # §3.1 [3] TREND ≥ 0 → 활성, 미만은 결측
    gate_g1_map_rate=0.60,           # G-C1 중앙 ≥ 60%
    gate_g5_rank_drift=0.05,         # G-C5 중앙 ≤ 5%p
    gate_g7_trend_flip=0.10,         # G-C7 ≤ 10%
    gate_g8_goodwill_cov=0.70,       # G-C8 ≥ 70%
    corr_kill_resc=0.50,             # KILL-3
    corr_kill_idr=0.60,              # KILL-4
    trend_window_recheck_max=1,      # G-C7 실패 시 재검토 1회만
    direction="higher_is_buy",       # §3.1 [7] 사전 확정. 사후 부호 반전 금지
))

# ── PART 3.3 어블레이션 arm — 정확히 4개. 추가 금지 (KILL-6 을 구조로 강제) ─────────────────
@dataclass
class Arm:
    key: str
    name: str
    purpose: str
    use_product: bool          # DIV_z × (−IEG_z) 곱 구조 사용 여부
    signal: str                # "product" | "div" | "negieg"
    include_declining: bool    # 구조쇠퇴 셀(TREND<0) 포함 여부


class ArmRegistry:
    """어블레이션 arm 등록기. 4개를 넘기면 KILL-6 — 그 자체가 규약 위반이다."""

    def __init__(self):
        self._a: Dict[str, Arm] = {}

    def add(self, arm: Arm) -> Arm:
        if arm.key in self._a:
            return self._a[arm.key]
        if len(self._a) >= CXD["MAX_ABLATION_ARM"]:
            raise KillCriteria(
                f"[KILL-6] 어블레이션 arm 이 {CXD['MAX_ABLATION_ARM']}개를 초과하려 했습니다 "
                f"(추가 시도: {arm.key}). 명세서 PART 5 KILL-6 — 그 자체가 규약 위반입니다.")
        self._a[arm.key] = arm
        return arm

    def all(self) -> List[Arm]:
        return list(self._a.values())

    def get(self, key: str) -> Arm:
        return self._a[key]


ARMS = ArmRegistry()
ARMS.add(Arm("A", "주 명세 (3.1 전문)", "본안",
             use_product=True, signal="product", include_declining=False))
ARMS.add(Arm("B", "DIV 단독 (곱 제거)", "조건화가 기여하는가",
             use_product=False, signal="div", include_declining=False))
ARMS.add(Arm("C", "−IEG_z 단독", "산업 간 성분이 실제로 0인가 (APS 재현)",
             use_product=False, signal="negieg", include_declining=False))
ARMS.add(Arm("D", "구조쇠퇴 셀 포함", "R-10 분해가 기여하는가",
             use_product=True, signal="product", include_declining=True))

PRIMARY_ARM = "A"
CONTROL_ARM = "B"      # KILL-5: A 가 B 를 사전 마진 초과로 이기지 못하면 폐기
#   ★ '사전 마진' 은 결과를 보기 전에 고정되어야 한다. 명세서가 수치를 주지 않았으므로
#     앵커(+4.6500%p)의 1/10 을 사전 지정하고 그 사실을 명시한다. 사후 조정 금지.
KILL5_MARGIN_CAGR = 0.004650


# ── PART 5 폐기 조건 ────────────────────────────────────────────────────────────────────────
KILL_SPEC = {
    "KILL-1": "G-C3 실패 (통관-매출 연결 부재) → 즉시 폐기, 재시도 금지",
    "KILL-2": "G-C4 실패 (조건화 기제 전제 붕괴) → 곱 구조 폐기, arm B 로 강등",
    "KILL-3": "|ρ(CXD, RESC)| > 0.5 → 실행 중단 및 보고",
    "KILL-4": "|ρ(CXD, IDR)| > 0.6 → 중복. 커버리지 높은 쪽만 채택",
    "KILL-5": "Phase 2 에서 arm A 가 arm B 를 사전 마진 초과로 이기지 못함 → 폐기",
    "KILL-6": "어블레이션 arm 이 4개를 초과하려는 시도 → 그 자체가 규약 위반",
}


@dataclass
class KillLedger:
    """발동한 폐기 조건을 기록한다. 은폐 금지 — 보고서에 그대로 실린다."""
    fired: List[dict] = field(default_factory=list)

    def fire(self, code: str, detail: str, hard: bool = True) -> None:
        self.fired.append(dict(code=code, spec=KILL_SPEC.get(code, ""), detail=detail, hard=hard))
        if hard:
            raise KillCriteria(f"[{code}] {KILL_SPEC.get(code, '')} — {detail}")

    def note(self, code: str, detail: str) -> None:
        """하드 중단 없이 기록만 (강등 계열)."""
        self.fired.append(dict(code=code, spec=KILL_SPEC.get(code, ""), detail=detail, hard=False))

    @property
    def any_hard(self) -> bool:
        return any(f["hard"] for f in self.fired)


# ── FUTURE_RETURN_LOCK — PART 6 STEP 10. 해제는 사람이 한다 ────────────────────────────────
class ReturnLock:
    """미래수익률 봉인.

    명세서 PART 6: `⛔ FUTURE_RETURN_LOCK 해제는 사람이 한다`.
    '보지 않겠다'는 의지가 아니라 잠금이어야 한다. 수익률 조회는 전부 이 잠금을 통과하며,
    열리기 전에 요청하면 예외로 중단되고 **시도 횟수까지 센다**(명세서 머리말 '미래수익률 접근').
    """

    def __init__(self):
        self.opened = False
        self.reason = ""
        self.blocked = 0
        self.accesses = 0

    def open(self, reason: str) -> None:
        if not reason or not str(reason).strip():
            raise SpecViolation("FUTURE_RETURN_LOCK 해제에는 사람이 적은 사유가 필요합니다.")
        self.opened = True
        self.reason = str(reason).strip()

    def require(self, what: str) -> None:
        if not self.opened:
            self.blocked += 1
            raise SpecViolation(
                f"FUTURE_RETURN_LOCK — 미래수익률 접근이 차단되었습니다 (요청: {what}). "
                f"명세서 PART 6 STEP 10: 해제는 사람이 합니다. "
                f"Phase 0 게이트가 통과하기 전에는 열 수 없습니다.")
        self.accesses += 1


LOCK = ReturnLock()


# ── trials ledger (BH-FDR q=0.10 family) ────────────────────────────────────────────────────
TRIALS_LEDGER_ROW = dict(
    factor_id=FACTOR_ID, code=FACTOR_CODE, name=SPEC_TITLE,
    family="U250-F1 BH-FDR q=0.10", spec_version=SPEC_VERSION,
    arms=CXD["MAX_ABLATION_ARM"], registered_before_returns=True,
)
BH_FDR_Q = 0.10


def spec_sha256() -> str:
    """사전등록 상수 전체의 해시. 실행 로그·보고서에 남겨 사후 변조를 확인할 수 있게 한다."""
    payload = json.dumps({
        "factor_id": FACTOR_ID, "spec_version": SPEC_VERSION,
        "frame": dict(FRAME), "cxd": dict(CXD), "rules": dict(RULES),
        "arms": [a.__dict__ for a in ARMS.all()],
        "kill": KILL_SPEC, "kill5_margin": KILL5_MARGIN_CAGR, "bh_fdr_q": BH_FDR_Q,
    }, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── PART 8 정직성 기록 — 결과 해석 시 반드시 병기 ───────────────────────────────────────────
UNVERIFIED_LOG: List[dict] = [
    dict(item="관세청 과거 vintage 부재 → 개정 look-ahead 소급 검증 불가",
         status="UNVERIFIED (영구)", kind="방법론적 한계"),
    dict(item="DART induty_code PIT vintage 부재 → 잔여 분류 오염",
         status="부분 통제 (G-C2 로 상한만 측정)", kind="방법론적 한계"),
    dict(item="M&A·연결범위 변동 기인 매출성장",
         status="부분 통제 (F1 이 조달경로 차단, 자기자금 인수는 통과)", kind="방법론적 한계"),
    dict(item="조건화 기제(IEG = SNR 조절자)의 경제적 근거",
         status="가설 — G-C4 로 필요조건만 검증", kind="미검증 가설"),
    dict(item="ISTANS HS↔KSIC 연계의 정밀도", status="미측정", kind="실현가능성 불확실"),
    dict(item="산업 간 성분의 예측력 부재 (APS 계열 보고)",
         status="문헌 근거 있음", kind="실증 근거 — arm C 로 자체 재현"),
]


def add_unverified(item: str, status: str, kind: str = "실행 중 발견") -> None:
    UNVERIFIED_LOG.append(dict(item=item, status=status, kind=kind))
