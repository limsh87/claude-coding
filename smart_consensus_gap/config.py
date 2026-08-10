# -*- coding: utf-8 -*-
"""SCG_ORIGINAL_REPRO_V1 — 설정 (명세 §25).

┌ 설계 의도 ─────────────────────────────────────────────────────────────────────────┐
│ §0-3 / §27 은 "성과를 본 뒤 파라미터를 바꾸지 말 것"을 요구한다. 이것을 약속이 아니라 │
│ 구조로 강제한다:                                                                    │
│   1. §25 기본값을 _BASE_SNAPSHOT(리터럴)과 SCGConfig(데이터클래스 기본값) 두 곳에    │
│      이중으로 적는다. 둘이 어긋나면 감사에서 BASE_CONFIG_MODIFIED 로 CRITICAL 실패.  │
│   2. 강건성 변형은 자유 오버라이드가 아니라 사전 등록된 레지스트리에서만 나온다.       │
│      레지스트리 항목은 축(axis) 하나만 바꾸도록 생성 시점에 검증한다(one-at-a-time).  │
│   3. 따라서 "카테시안 전수탐색으로 최고 CAGR 찾기"(§27)는 이 파일을 고치지 않는 한    │
│      실행 자체가 불가능하고, 고치면 감사에 즉시 잡힌다.                               │
└────────────────────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ════════════════════════════════════════════════════════════════════════════════════════
#  전략 식별
# ════════════════════════════════════════════════════════════════════════════════════════
SPEC_ID = "SCG_ORIGINAL_REPRO_V1"
SOURCE_DOC = "IBK투자증권 이정빈, 「바텀업 퀀트 – 알파 포트폴리오 전략」(2020-08-20)"

# 실행 모드 (§0-2)
MODE_ORIGINAL_EXACT = "ORIGINAL_EXACT"
MODE_PUBLIC_REPRO = "PUBLIC_REPRO"
MODE_AUTO = "AUTO"  # discover 단계가 벤더 필드 가용성으로 결정

# 전략 식별자 (§2)
STRAT_SCG_SINGLE_RAW = "SCG_SINGLE_RAW"
STRAT_SCG_SINGLE_Z = "SCG_SINGLE_Z"
STRAT_IBK_7F_EXACT = "IBK_7F_EXACT"
STRAT_IBK_6F_PUBLIC = "IBK_6F_PUBLIC_REPRO"
STRAT_5F_NO_SCG = "IBK_5F_PUBLIC_NO_SCG"          # §15 절제(ablation) 전용
STRAT_7F_SP_PROXY = "PUBLIC_7F_SP_PROXY"          # §8 experimental — 공식결과 아님

OFFICIAL_STRATEGIES = (STRAT_SCG_SINGLE_RAW, STRAT_SCG_SINGLE_Z,
                       STRAT_IBK_7F_EXACT, STRAT_IBK_6F_PUBLIC)
EXPERIMENTAL_STRATEGIES = (STRAT_7F_SP_PROXY,)

# 수치 상수 (§5.3, §6, §4)
EPS_NUMERIC_FLOOR = 1e-6
DENOM_NEAR_ZERO_TOL = 1e-8
MIN_ANALYST_COUNT = 3
SKILL_CLIP_LO, SKILL_CLIP_HI = 0.25, 4.0
BIAS_CLIP = 0.50

# ════════════════════════════════════════════════════════════════════════════════════════
#  §25 기본값 — 리터럴 스냅샷 (변조 감지용 원본)
#  ★ 이 딕셔너리와 SCGConfig 의 기본값이 다르면 감사가 실패한다. 절대 한쪽만 고치지 말 것.
#    (그리고 어느 쪽이든 "성과를 본 뒤" 고치는 것은 §27 위반이다)
# ════════════════════════════════════════════════════════════════════════════════════════
_BASE_SNAPSHOT: Dict[str, Any] = {
    "mode": "PUBLIC_REPRO",
    "universe": "KOSPI200_PIT",
    "rebalance_months": [3, 6, 9, 12],
    "n_holdings": 30,
    "portfolio_weight": "MARKET_CAP",
    "active_estimate_window_days": 90,
    "recency_half_life_days": 30,
    "accuracy_max_events": 12,
    "accuracy_event_half_life": 4,
    "shrink_k": 4,
    "analyst_weight_cap": 0.35,
    "factor_winsor_lo": 0.01,
    "factor_winsor_hi": 0.99,
    "scorer": "Z_RAW_EQUAL",
    "transaction_cost_bps": 35,
    "execution": "NEXT_TRADING_DAY_OPEN",
    "bootstrap_n": 2000,
    "random_seed": 20260810,
    "max_full_runtime_seconds": 4 * 60 * 60,
    "twelve_mf_source": "VENDOR_IF_AVAILABLE",
}

# 유니버스 (§10)
UNIVERSE_PRIMARY = "KOSPI200_PIT"
UNIVERSE_SENSITIVITY = "KOSPI_ALL_COVERED_PIT"

# 스코어러 (§9)
SCORER_Z = "Z_RAW_EQUAL"
SCORER_RANK = "RANK_EQUAL"

# 체결 (§12)
EXEC_NEXT_OPEN = "NEXT_TRADING_DAY_OPEN"
EXEC_SAME_CLOSE = "SAME_DAY_CLOSE"    # 진단용. 공식 성과 금지.


# ════════════════════════════════════════════════════════════════════════════════════════
#  스테이지 런타임 예산 (§19) — 분 단위
# ════════════════════════════════════════════════════════════════════════════════════════
STAGE_BUDGET_MINUTES: Dict[str, float] = {
    "S0_DISCOVERY": 10,
    "S1_NORMALIZE": 30,
    "S2_PIT_SNAPSHOT": 40,
    "S3_ANALYST_SKILL": 60,
    "S4_5_CONSENSUS_FACTORS": 45,
    "S6_BACKTEST": 15,
    "S7_ROBUSTNESS": 50,
    "S8_AUDIT": 20,
}
TOTAL_BUDGET_MINUTES = 240.0


@dataclass
class SCGConfig:
    """§25 기본값. 기본값 변경은 곧 재현 정의의 변경이며 감사에 기록된다."""

    # ── 모드 / 유니버스 ────────────────────────────────────────────────────────────────
    mode: str = "PUBLIC_REPRO"
    universe: str = "KOSPI200_PIT"

    # ── 포트폴리오 (§11) ──────────────────────────────────────────────────────────────
    rebalance_months: Tuple[int, ...] = (3, 6, 9, 12)
    n_holdings: int = 30
    portfolio_weight: str = "MARKET_CAP"

    # ── 컨센서스 재구성 (§4, §5) ──────────────────────────────────────────────────────
    active_estimate_window_days: int = 90
    recency_half_life_days: float = 30.0
    accuracy_max_events: int = 12
    accuracy_event_half_life: float = 4.0
    shrink_k: float = 4.0
    analyst_weight_cap: float = 0.35

    # ── 스코어링 (§9) ────────────────────────────────────────────────────────────────
    factor_winsor_lo: float = 0.01
    factor_winsor_hi: float = 0.99
    scorer: str = "Z_RAW_EQUAL"

    # ── 실행/비용 (§12, §13) ─────────────────────────────────────────────────────────
    transaction_cost_bps: float = 35.0
    execution: str = "NEXT_TRADING_DAY_OPEN"

    # ── 통계 (§17) ──────────────────────────────────────────────────────────────────
    bootstrap_n: int = 2000
    random_seed: int = 20260810
    max_full_runtime_seconds: int = 4 * 60 * 60

    # ── 12MF 소스 (§7.3) — 벤더/합성 혼합 금지. variant_id 로 구분한다. ────────────────
    twelve_mf_source: str = "VENDOR_IF_AVAILABLE"

    # ── 백테스트 구간 (데이터 가용성으로 클리핑되며 매니페스트에 실제 구간을 기록) ────────
    backtest_start: str = "2016-06-30"
    backtest_end: str = "2026-06-30"

    # ── 실행 제어 (재현 정의와 무관한 운영 파라미터 → 스냅샷 대조 대상 아님) ──────────────
    run_id: str = ""
    output_root: str = "outputs"
    cache_root: str = ""
    data_roots: Tuple[str, ...] = ()
    variant_id: str = "BASE"
    variant_axis: str = "BASE"
    run_robustness: bool = True
    run_bootstrap: bool = True
    synthetic: bool = False               # 합성 픽스처 리허설 여부
    synthetic_seed: int = 20260810
    log_level: str = "INFO"
    reference_fixture_path: str = ""
    max_workers: int = 0                  # 0 → 자동

    # ── 파생 ────────────────────────────────────────────────────────────────────────
    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        if isinstance(self.rebalance_months, list):
            self.rebalance_months = tuple(self.rebalance_months)
        if isinstance(self.data_roots, list):
            self.data_roots = tuple(self.data_roots)
        if not self.cache_root:
            self.cache_root = os.path.join(os.getcwd(), "scg_cache")
        if not self.reference_fixture_path:
            self.reference_fixture_path = os.path.join(
                os.getcwd(), "smart_consensus_gap", "reference", "reference_20200630.csv")

    # 운영 파라미터(재현 정의와 무관) — 스냅샷 대조에서 제외한다.
    _OPERATIONAL_FIELDS = (
        "run_id", "output_root", "cache_root", "data_roots", "variant_id", "variant_axis",
        "run_robustness", "run_bootstrap", "synthetic", "synthetic_seed", "log_level",
        "reference_fixture_path", "max_workers", "backtest_start", "backtest_end",
    )

    @property
    def out_dir(self) -> str:
        return os.path.join(self.output_root, f"scg_{self.run_id}")

    @property
    def is_exact(self) -> bool:
        return self.mode == MODE_ORIGINAL_EXACT

    @property
    def mode_tag(self) -> str:
        """모든 출력 파일/로그/차트 제목에 붙는 모드 표기 (§0-2)."""
        return f"[{self.mode}]"

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["rebalance_months"] = list(self.rebalance_months)
        d["data_roots"] = list(self.data_roots)
        return d

    def definition_dict(self) -> Dict[str, Any]:
        """재현 정의를 이루는 필드만. 지문(fingerprint)과 스냅샷 대조의 대상."""
        d = self.to_dict()
        for k in self._OPERATIONAL_FIELDS:
            d.pop(k, None)
        return d

    def fingerprint(self) -> str:
        return hashlib.sha1(
            json.dumps(self.definition_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]

    def replace(self, **kw: Any) -> "SCGConfig":
        return dataclasses.replace(self, **kw)


def base_config(**kw: Any) -> SCGConfig:
    return SCGConfig(**kw)


def base_snapshot_diff(cfg: SCGConfig) -> List[str]:
    """§25 리터럴 스냅샷과 현재 '기본' 설정의 차이. BASE variant 에서 비어 있어야 한다."""
    cur = cfg.definition_dict()
    diffs: List[str] = []
    for k, v in _BASE_SNAPSHOT.items():
        got = cur.get(k, "<MISSING>")
        if isinstance(v, list):
            got = list(got) if isinstance(got, (list, tuple)) else got
        if got != v:
            diffs.append(f"{k}: snapshot={v!r} actual={got!r}")
    return diffs


# ════════════════════════════════════════════════════════════════════════════════════════
#  §16 사전 정의 강건성 변형 — one-variable-at-a-time 만 허용
# ════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class RobustnessVariant:
    variant_id: str
    axis: str
    overrides: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


def _v(vid: str, axis: str, note: str = "", **overrides: Any) -> RobustnessVariant:
    return RobustnessVariant(vid, axis, dict(overrides), note)


#  ★ 각 항목은 정확히 한 축만 건드린다. 아래 _validate_variants() 가 이를 강제한다.
PREDEFINED_ROBUSTNESS_VARIANTS: Tuple[RobustnessVariant, ...] = (
    # SCG 재구성 축
    _v("HL15", "recency_half_life_days", "최신성 반감기 15일", recency_half_life_days=15.0),
    _v("HL60", "recency_half_life_days", "최신성 반감기 60일", recency_half_life_days=60.0),
    _v("ACC4", "accuracy_max_events", "정확도 이벤트 4개", accuracy_max_events=4),
    _v("ACC8", "accuracy_max_events", "정확도 이벤트 8개", accuracy_max_events=8),
    _v("CAP25", "analyst_weight_cap", "애널리스트 가중 상한 25%", analyst_weight_cap=0.25),
    _v("CAP50", "analyst_weight_cap", "애널리스트 가중 상한 50%", analyst_weight_cap=0.50),
    # 포트폴리오 축
    _v("N20", "n_holdings", "20종목", n_holdings=20),
    _v("N50", "n_holdings", "50종목", n_holdings=50),
    _v("RANK", "scorer", "퍼센타일 랭크 스코어러", scorer=SCORER_RANK),
    _v("EQW", "portfolio_weight", "동일가중", portfolio_weight="EQUAL"),
    _v("UNIV_COVERED", "universe", "커버리지 KOSPI 전체", universe=UNIVERSE_SENSITIVITY),
)


def _validate_variants() -> None:
    seen = set()
    for v in PREDEFINED_ROBUSTNESS_VARIANTS:
        if v.variant_id in seen:
            raise ValueError(f"강건성 변형 ID 중복: {v.variant_id}")
        seen.add(v.variant_id)
        if len(v.overrides) != 1:
            raise ValueError(
                f"{v.variant_id}: one-variable-at-a-time 위반 — {list(v.overrides)} "
                "(§16: 카테시안 전수탐색 금지)")
        (k,) = tuple(v.overrides)
        if k != v.axis:
            raise ValueError(f"{v.variant_id}: axis={v.axis} 와 override 키={k} 불일치")
        if k not in _BASE_SNAPSHOT and k not in {f.name for f in dataclasses.fields(SCGConfig)}:
            raise ValueError(f"{v.variant_id}: 알 수 없는 설정 키 {k}")


_validate_variants()


def variant_configs(cfg: SCGConfig) -> List[Tuple[RobustnessVariant, SCGConfig]]:
    """BASE 를 고정한 채 사전 정의 변형만 생성한다."""
    out: List[Tuple[RobustnessVariant, SCGConfig]] = []
    for v in PREDEFINED_ROBUSTNESS_VARIANTS:
        out.append((v, cfg.replace(variant_id=v.variant_id, variant_axis=v.axis, **v.overrides)))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
#  팩터 정의 (§1, §7, §9)
# ════════════════════════════════════════════════════════════════════════════════════════
FACTOR_SP = "SURPRISE_PROB"
FACTOR_FQ1 = "FQ1_EPS_YOY"
FACTOR_FY1 = "FY1_EPS_YOY"
FACTOR_SCG = "SCG"
FACTOR_REV = "EPS12MF_REV_1M"
FACTOR_INST = "INST_20D"
FACTOR_FGN = "FOREIGN_20D"

#  원문 7팩터는 모두 동일 별(★) 가중 → 동일가중 평균 (§1, §9)
FACTORS_7F = (FACTOR_SP, FACTOR_FQ1, FACTOR_FY1, FACTOR_SCG, FACTOR_REV, FACTOR_INST, FACTOR_FGN)
FACTORS_6F = (FACTOR_FQ1, FACTOR_FY1, FACTOR_SCG, FACTOR_REV, FACTOR_INST, FACTOR_FGN)
FACTORS_5F_NO_SCG = (FACTOR_FQ1, FACTOR_FY1, FACTOR_REV, FACTOR_INST, FACTOR_FGN)

#  모든 팩터는 "높을수록 좋다" (§9.1)
FACTOR_DIRECTION: Dict[str, int] = {f: +1 for f in FACTORS_7F}

STRATEGY_FACTORS: Dict[str, Tuple[str, ...]] = {
    STRAT_IBK_7F_EXACT: FACTORS_7F,
    STRAT_IBK_6F_PUBLIC: FACTORS_6F,
    STRAT_5F_NO_SCG: FACTORS_5F_NO_SCG,
    STRAT_7F_SP_PROXY: FACTORS_7F,
    STRAT_SCG_SINGLE_RAW: (FACTOR_SCG,),
    STRAT_SCG_SINGLE_Z: (FACTOR_SCG,),
}

# 재현 가정 태깅 (§1) — 원문이 공개하지 않은 부분을 명시적으로 표시한다.
OPERATIONAL_REPRODUCTION_ASSUMPTIONS: Tuple[Tuple[str, str], ...] = (
    ("SMART_CONSENSUS_WEIGHTS",
     "원문/FnGuide 는 애널리스트별 가중 수식을 공개하지 않는다. 최신성×정확도×편향보정의 "
     "3요소 재구성이며 벤더 산식의 복제가 아니다. (§5.1)"),
    ("FACTOR_COMBINATION",
     "원문은 7팩터를 어떤 표준화로 합산했는지 완전한 계산식을 공개하지 않는다. "
     "횡단면 z-score 동일가중 평균은 재현 가정이다. (§9.1)"),
    ("WINSORIZATION",
     "1%/99% 횡단면 윈저라이즈는 composite 안정화를 위한 재현 가정이며 raw 값은 보존한다. (§6)"),
    ("SURPRISE_PROBABILITY",
     "벤더 서프라이즈 확률 산식은 공개되지 않아 PUBLIC_REPRO 공식 결과에서 제외한다. (§8)"),
    ("FQ1_FY1_TARGET_RESOLUTION",
     "리밸런싱 시점의 FQ1/FY1 은 '해당 시점까지 실적이 발표되지 않은 최초 회계기간'으로 "
     "정의했다. 원문은 정의를 명시하지 않는다."),
    ("ACCURACY_EVENT_COUNT",
     "shrinkage 의 n 은 실제 사용된(최대 ACCURACY_MAX_EVENTS 로 절단된) 실현 이벤트 수다."),
    ("SYNTHETIC_12MF",
     "벤더 12MF 가 없을 때 FY1/FY2 잔여월 가중 합성을 쓴다. 벤더/합성 혼합은 금지하며 "
     "variant_id 로 구분한다. (§7.3)"),
)

__all__ = [n for n in dir() if not n.startswith("__")]
