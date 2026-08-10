#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  PHASE 0 — 대체데이터 3축 수집 가능성 검증  v1.2          [단일 코드 셀]
# =============================================================================
#  이 파일 하나가 명령서 v1.2의 실행체다. Colab/JupyterLab 한 셀에 붙여넣거나
#  `python phase0_3axis_v12.py` 로 실행한다. 셀을 쪼개지 말 것(§8.5).
#
#  이 단계가 하는 것 (§1.1)      : 축 A / A-Δ / B / C 의 **수집 가능성 실측**
#  이 단계가 하지 않는 것 (§1.2) : 팩터·시그널·수익률·축간결합 — 전면 금지
#
#  실행 모드는 LIVE 하나뿐이다. 합성 데이터 경로는 존재하지 않는다(§1.3, P0_LIVE_ONLY).
#
# -----------------------------------------------------------------------------
#  인증정보 블록 — 발급 절차 (§8.5)
# -----------------------------------------------------------------------------
#  [1] OpenDART API 키   (축 A, 축 A-Δ)
#      발급: https://opendart.fss.or.kr/  →  인증키 신청/관리 → 인증키 신청
#      • 이메일 인증 즉시 발급, 무료.
#      • 일일 호출 한도 20,000콜. 본 실행의 중단선 15,200콜은 이 한도 기준이다(§4.4).
#      • 환경변수 DART_API_KEY 또는 아래 DART_API_KEY 상수에 40자 키를 넣는다.
#
#  [2] GCP 서비스계정 JSON 키   (축 B, BigQuery)
#      발급: https://console.cloud.google.com/iam-admin/serviceaccounts
#            → 서비스 계정 만들기 → 키 → 새 키 만들기 → JSON → 다운로드
#      최소 역할: `BigQuery User` (roles/bigquery.user)
#                + `BigQuery Job User` (roles/bigquery.jobUser)
#      결제: BigQuery 쿼리는 결제 계정 연결이 **필수**다. 단, 월 1TB 스캔까지
#            무료 티어이므로 본 실행(§5.2에서 100GB 상한)은 통상 무과금이다.
#            결제 미연결 시 403 billingNotEnabled 로 실패한다.
#
#      ★ v1.2 최대 주의점 — 두 환경변수의 역할이 다르다. 섞으면 축 B가 통째로 죽는다.
#        ┌────────────────────────────────────┬──────────────────────────────────┐
#        │ GOOGLE_APPLICATION_CREDENTIALS     │ JSON 키 "파일의 절대경로"        │
#        │                                    │ 예) /home/user/.gcp/sa-key.json  │
#        ├────────────────────────────────────┼──────────────────────────────────┤
#        │ GOOGLE_CLOUD_PROJECT               │ "프로젝트 ID 문자열"             │
#        │                                    │ 예) compelling-muse-311107       │
#        └────────────────────────────────────┴──────────────────────────────────┘
#        v1.1 실행에서 프로젝트 ID를 파일경로 자리에 넣어 BLOCKED 가 났다.
#      대안: `gcloud auth application-default login` (ADC) 경로도 허용한다(§5.1-4).
#
#  [3] 공공데이터포털 API 키   (축 C, 국민연금 사업장)
#      발급: https://www.data.go.kr/  → 국민연금공단_국민연금 가입 사업장 내역
#            → 활용신청. **자동승인이 아닌 건은 1~2영업일 소요된다.**
#      ★ 실행 전 반드시 확인: 마이페이지 > 데이터활용 > 활용신청 현황
#        - 상태가 '승인' 이어야 한다. '신청' 상태면 어떤 파라미터로도 실패한다(§6.1).
#        - 일일 트래픽 잔량도 같은 화면에서 확인한다.
#      키는 **Decoding** 키를 넣고 코드가 인코딩한다(이중인코딩 방지).
# =============================================================================

from __future__ import annotations

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ▼▼▼  인 증 정 보  입 력 란  —  여기에 키를 붙여넣는다  ▼▼▼               ║
# ║  비워두면 같은 이름의 환경변수에서 읽는다. 둘 다 없으면 해당 축은          ║
# ║  BLOCKED_PREREQ(NO_KEY) 로 기록되고 나머지 축은 정상 진행한다.            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# [1] 축 A / A-Δ — OpenDART 인증키 (40자 16진 문자열)
#     발급 https://opendart.fss.or.kr/  →  인증키 신청/관리 (이메일 인증 즉시, 무료)
DART_API_KEY = ""

# [2] 축 B — GCP 서비스계정. ★ 아래 두 칸의 역할이 다르다. 바꿔 넣으면 축 B가 통째로 죽는다.
#     발급 https://console.cloud.google.com/iam-admin/serviceaccounts
#          → 서비스 계정 만들기 → 키 → 새 키 만들기 → JSON → 다운로드
#     최소 역할: BigQuery User + BigQuery Job User / 결제 계정 연결 필요(월 1TB 무료)
GCP_SA_KEY_PATH = ""      # JSON 키 "파일의 절대경로"   예) /content/sa-key.json
GCP_PROJECT_ID = ""       # "프로젝트 ID 문자열"        예) compelling-muse-311107

# [3] 축 C — 공공데이터포털 **Decoding** 키 (코드가 인코딩하므로 Encoding 키를 넣지 말 것)
#     발급 https://www.data.go.kr/ → 국민연금공단_국민연금 가입 사업장 내역 → 활용신청
#     ★ 실행 전 마이페이지 > 데이터활용 > 활용신청 현황에서 '승인' 상태를 확인한다.
#       '신청' 상태면 어떤 파라미터로도 실패한다.
DATA_GO_KR_KEY = ""

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ▲▲▲  여기까지가 입력란. 아래는 손대지 않는다.  ▲▲▲                       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import bisect
import csv
import io
import json
import os
import platform
import random
import re
import socket
import sys
import threading
import time
import traceback
import unicodedata
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, urlencode

# =============================================================================
#  §1.3 / §2  —  실행 모드와 계약 (Contracts)
# =============================================================================

VERSION = "v1.2"

# §1.3 셀프테스트 금지. 이 플래그는 False 로 고정이며 True 이면 즉시 중단한다.
SELFTEST = False

RUN_MODE = "LIVE"


class ContractViolation(RuntimeError):
    """계약 위반. 절대 삼키지 않는다(§8.3 ENOSPC 포함)."""


CONTRACTS: Dict[str, str] = {
    "P0_LIVE_ONLY": "합성/모의 데이터 경로 사용 금지. §1.3 자가진단 통과 필수",
    "P0_NO_STRATEGY": "수익률·시그널·팩터 연산 일절 금지",
    "P0_PIT_STRICT": "접수일자(rcept_dt)가 기준일 이후인 레코드는 무조건 폐기. 예외 없음",
    "P0_GRAPH_FULL_MEASURE_SUB": "그래프는 전 상장사로 구성, 지표 측정은 하위 1,000종목에서만",
    "P0_SNAPSHOT_DEADLINE_GUARD": "스냅샷 수집 전 법정 제출기한 확인. 미도래 시 벌크 없이 UNVERIFIED",
    "P0_CANARY_FIRST": "축마다 10종목 카나리 통과 전 벌크 금지",
    "P0_INDEPENDENT_AXES": "축 A/B/C 상호 의존 금지",
    "P0_FAIL_LOUD": "결측은 결측으로 기록. 보간·추정·대체값 금지",
    "P0_RUNTIME_ROOT": "PROJECT_ROOT 런타임 감지. /content 감지 시 WAIVED (PASS 기록 금지)",
    "P0_RESUMABLE": "캐시 키에 (corp_code, bsns_year, reprt_code) 전부 포함",
    "P0_NO_THRESHOLD_EDIT": "임계값 dataclass는 frozen. 실행 중 변경 금지",
    "NO_KNOWN_DEAD_CALL": "pykrx 지수구성종목 파일 호출 금지 (영구 실패)",
}

# 계약 준수 상태.
#   PASS          — 구조적으로 보장되거나, 실제로 실행되어 지켜진 것을 확인했다
#   NOT_EXERCISED — 이번 실행에서 해당 코드 경로가 아예 돌지 않았다. **PASS 로 적지 않는다.**
#   WAIVED        — /content 감지 등으로 면제 (P0_RUNTIME_ROOT)
#   VIOLATED      — 위반
# 돌지도 않은 경로를 PASS 로 적으면 판정표가 거짓말을 한다. P0_RUNTIME_ROOT 에 대한
# 명령서의 요구("WAIVED 로 기록하되 PASS 로 기록 금지")를 모든 런타임 계약으로 확장한다.
CONTRACT_STATE: Dict[str, str] = {k: "PENDING" for k in CONTRACTS}


def mark_contract(name: str, state: str) -> None:
    if name not in CONTRACTS:
        raise KeyError(f"알 수 없는 계약: {name}")
    # 한 번 PASS 로 확인된 계약을 나중에 되돌리지 않는다(다른 기준일에서 미실행이어도).
    if CONTRACT_STATE[name] == "PASS" and state == "NOT_EXERCISED":
        return
    CONTRACT_STATE[name] = state


def _enforce_live_only() -> None:
    """§1.3 — SELFTEST 플래그가 켜지면 시작 직후 예외로 중단한다."""
    if SELFTEST:
        raise ContractViolation(
            "P0_LIVE_ONLY 위반: SELFTEST=True. v1.2는 실측 전용이다. "
            "합성 데이터로 게이트를 통과시키지 말 것(§11)."
        )
    if RUN_MODE != "LIVE":
        raise ContractViolation(f"P0_LIVE_ONLY 위반: RUN_MODE={RUN_MODE!r} (LIVE 아님)")


# --- NO_KNOWN_DEAD_CALL -------------------------------------------------------
# 금지 심볼을 소스에 리터럴로 남기지 않기 위해 런타임에 조립한다.
_DEAD_CALL_SYMBOL = "get_index_portfolio_" + "deposit_file"
_DEAD_CALL_ARG = "10" + "28"


def guard_dead_call(symbol: str) -> None:
    """영구 실패로 확인된 호출을 런타임에 차단한다(NO_KNOWN_DEAD_CALL)."""
    if _DEAD_CALL_SYMBOL in symbol:
        raise ContractViolation(
            f"NO_KNOWN_DEAD_CALL 위반: {symbol} 는 영구 실패 호출이다. 사용 금지."
        )


def _scan_source_for_dead_call() -> str:
    """자기 소스에 금지 호출이 들어갔는지 정적 확인. 셀 붙여넣기 실행 시엔 확인 불가."""
    try:
        src_path = Path(__file__).resolve()
        src = src_path.read_text(encoding="utf-8")
    except Exception:
        return "SOURCE_UNAVAILABLE(셀 붙여넣기 실행 — 런타임 가드로 대체)"
    if _DEAD_CALL_SYMBOL in src:
        raise ContractViolation(
            f"NO_KNOWN_DEAD_CALL 위반: 소스에 {_DEAD_CALL_SYMBOL} 리터럴이 존재한다."
        )
    return "PASS"


# =============================================================================
#  §3.4 / §4.6 / §5.6 / §6.3  —  임계값 (frozen, 실행 중 변경 금지)
# =============================================================================


@dataclass(frozen=True)
class Thresholds:
    """P0_NO_THRESHOLD_EDIT — frozen dataclass. 게이트 통과를 위해 조정 금지(§11)."""

    # 축 A (§3.4)
    A1_exec_record_coverage: float = 0.90     # 임원 레코드 1건 이상 확보 비율 ≥
    A2_birth_ym_missing: float = 0.10         # 출생년월 결측률 ≤
    A3_linked_share_bottom1000: float = 0.25  # 겸직 링크 걸린 하위1000 비율 ≥
    A5_total_links: int = 600                 # 총 겸직 링크 수 ≥
    A4_manual_sample: int = 200               # 수기 검증 표본 건수

    # 축 A-Δ (§4.6)
    AD1_born_ge1_share: float = 0.05          # 분기당 edge_born≥1 종목 비율(전이평균) ≥
    AD2_born_total_median: int = 50           # 분기당 전체 edge_born 총건수 중앙값 ≥
    AD3_snapshots_required: int = 4           # 스냅샷 구성 성공 4/4

    # 축 B (§5.6)
    B1_patent_holder_share: float = 0.30      # 최근5년 KR특허 1건 이상 보유 비율 ≥
    B2_exact_match_rate: float = 0.70         # 출원인명 완전일치 매핑 성공률 ≥
    B3_citation_missing: float = 0.30         # 피인용 데이터 결측률 ≤
    B4_patent_holder_share_past: float = 0.30 # T_PAST 시점에도 B-1 성립 ≥

    # 축 C (§6.3)
    C2_workplace_match: float = 0.60          # 사업장 매칭 성공 비율 ≥
    C5_manual_sample: int = 100               # 수기 검증 표본 건수

    # 인프라 (§3.3, §4.4, §5.2, §8.3)
    corpcode_unknown_miss_max: int = 20       # ⑥원인불명 초과 시 판정 보류
    call_budget_hard_stop: int = 15_200       # 중단선
    call_budget_trip_ratio: float = 0.80      # 중단선의 80% 도달 시 즉시 중단
    bq_max_scan_bytes: int = 100 * (1024 ** 3)  # 단일 쿼리 100GB 초과 시 중단
    measure_universe_size: int = 1_000        # 시총 하위 N종목
    canary_size: int = 10                     # 카나리 종목 수
    max_workers: int = 4                      # 워커 4 이하
    circuit_consecutive_fail: int = 10        # 연속 실패 10회 → 브레이커
    circuit_cooldown_sec: int = 60            # 60초 대기
    circuit_max_trips: int = 3                # 3회 반복 시 해당 축 중단
    runtime_budget_sec: int = 4 * 3600        # 실행 시간 예산 4시간(§10)


TH = Thresholds()

# =============================================================================
#  기준일·보고서 정의 (§3.2, §4.2)
# =============================================================================

T_NOW = date(2026, 6, 30)
T_PAST = date(2021, 6, 30)

# §3.2 — 기준일 시점에 법정 제출기한이 경과한 보고서만 사용 가능하다.
#   반기보고서(11012)는 기한이 8-14이므로 6-30 시점에 관측 불가. 제도적 제약이며 버그가 아니다.
AXIS_A_BASES: List[Tuple[str, date, int, str]] = [
    ("T_NOW", T_NOW, 2026, "11013"),
    ("T_PAST", T_PAST, 2021, "11013"),
]

# §4.2 — v1.2 변경점: 스냅샷 창을 한 분기 뒤로 이동. 4개 모두 실행일 기준 기한 경과.
AXIS_AD_SNAPSHOTS: List[Tuple[str, date, int, str]] = [
    ("S1", date(2025, 6, 30), 2025, "11012"),
    ("S2", date(2025, 9, 30), 2025, "11014"),
    ("S3", date(2025, 12, 31), 2025, "11011"),
    ("S4", date(2026, 3, 31), 2026, "11013"),
]

# 보고서코드 → (명칭, 기준 사업연도 종료 월, 일, 법정 제출기한 일수)
REPRT_SPEC: Dict[str, Tuple[str, int, int, int]] = {
    "11013": ("1분기보고서", 3, 31, 45),
    "11012": ("반기보고서", 6, 30, 45),
    "11014": ("3분기보고서", 9, 30, 45),
    "11011": ("사업보고서", 12, 31, 90),
}


def statutory_deadline(bsns_year: int, reprt_code: str) -> date:
    """법정 제출기한(§4.3). 12월 결산법인 가정 — 비12월 결산은 known_limitations 로 기록."""
    if reprt_code not in REPRT_SPEC:
        raise ValueError(f"알 수 없는 보고서코드: {reprt_code}")
    _, mm, dd, lag_days = REPRT_SPEC[reprt_code]
    return date(bsns_year, mm, dd) + timedelta(days=lag_days)


# 축 B 관측 지연(§5.3/§7): 출원 → 공개 약 18개월
PATENT_PUBLICATION_LAG_MONTHS = 18
PATENT_WINDOW_YEARS = 5

# =============================================================================
#  §8.1  —  PROJECT_ROOT 런타임 감지
# =============================================================================


def detect_project_root() -> Tuple[Path, str, Optional[str]]:
    """
    반환: (root, contract_state, warning)
      contract_state 는 'PASS' 또는 'WAIVED'. /content 감지 시 절대 PASS 로 기록하지 않는다.
    """
    env_root = os.environ.get("P0_PROJECT_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
    else:
        try:
            root = Path(__file__).resolve().parent
        except NameError:
            root = Path.cwd().resolve()

    parts = {p.lower() for p in root.parts}
    colabish = ("content" in parts) or str(root).startswith("/content")
    if colabish:
        warn = (
            f"P0_RUNTIME_ROOT WAIVED — /content 계열 경로 감지({root}). "
            "Colab 임시 디스크는 세션 종료 시 캐시가 소멸하며, 그 경우 §4.4 호출 예산이 두 배로 든다. "
            "실측 실행에서는 로컬 SSD 경로 사용을 강력히 권장한다(§8.1)."
        )
        return root, "WAIVED", warn
    return root, "PASS", None


PROJECT_ROOT, _ROOT_CONTRACT_STATE, _ROOT_WARNING = detect_project_root()

CACHE_DIR = PROJECT_ROOT / "cache"
RAW_DIR = CACHE_DIR / "raw"
PARSED_DIR = CACHE_DIR / "parsed"
REPORTS_DIR = PROJECT_ROOT / "reports"   # §1.3 — reports_selftest 를 쓰지 않는다


def ensure_dirs() -> None:
    for d in (CACHE_DIR, RAW_DIR, PARSED_DIR, REPORTS_DIR, RAW_DIR / "dart_exctv"):
        d.mkdir(parents=True, exist_ok=True)
    # §8.2 의 cache/reports 트리를 canonical reports/ 로 연결 (실패해도 무해)
    link = CACHE_DIR / "reports"
    if not link.exists():
        try:
            link.symlink_to(REPORTS_DIR, target_is_directory=True)
        except Exception:
            pass


# =============================================================================
#  로깅
# =============================================================================

_LOG_LINES: List[str] = []
_LOG_LOCK = threading.Lock()
_T0 = time.time()


def log(msg: str = "") -> None:
    line = f"[{time.time() - _T0:7.1f}s] {msg}" if msg else ""
    with _LOG_LOCK:
        _LOG_LINES.append(line)
    print(line, flush=True)


def rule(title: str = "", ch: str = "=") -> None:
    if title:
        log(ch * 78)
        log(title)
        log(ch * 78)
    else:
        log(ch * 78)


def flush_log() -> None:
    try:
        (REPORTS_DIR / "phase0_run_v12.log").write_text(
            "\n".join(_LOG_LINES) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # pragma: no cover
        print(f"로그 저장 실패: {exc}", file=sys.stderr)


# =============================================================================
#  §8.4  —  호출 카운터 (기준일별 독립 카운터 + 총계 별도 필드)
# =============================================================================


class CallBudgetExceeded(RuntimeError):
    """§4.4 — 누적 호출이 중단선의 80%에 도달. 판정표 저장 후 중단한다."""


class Counters:
    """기준일별 호출 수를 독립 카운터로, 총계는 별도 필드로 관리한다(§8.4)."""

    def __init__(self, hard_stop: int, trip_ratio: float) -> None:
        self._lock = threading.Lock()
        self.by_date: Dict[str, int] = defaultdict(int)
        self.total: int = 0
        self.cache_hit: Dict[str, int] = defaultdict(int)
        self.cache_miss: Dict[str, int] = defaultdict(int)
        self.hard_stop = hard_stop
        self.trip_at = int(hard_stop * trip_ratio)
        self.tripped = False
        # KRX 등 OpenDART 일일 한도와 무관한 호출. 예산을 소모하지 않되 눈에는 보여야 한다.
        self.aux: Dict[str, int] = defaultdict(int)

    def api_call(self, date_key: str, n: int = 1) -> None:
        with self._lock:
            self.by_date[date_key] += n
            self.total += n
            if self.total >= self.trip_at and not self.tripped:
                self.tripped = True
                raise CallBudgetExceeded(
                    f"누적 호출 {self.total} ≥ 중단선 {self.hard_stop}의 "
                    f"{TH.call_budget_trip_ratio:.0%}({self.trip_at}). "
                    "§4.4에 따라 즉시 중단하고 판정표를 저장한다."
                )

    def aux_call(self, name: str, n: int = 1) -> None:
        """OpenDART 예산과 분리해 세는 호출(KRX 등). 중단선을 건드리지 않는다."""
        with self._lock:
            self.aux[name] += n

    def hit(self, axis: str, n: int = 1) -> None:
        with self._lock:
            self.cache_hit[axis] += n

    def miss(self, axis: str, n: int = 1) -> None:
        with self._lock:
            self.cache_miss[axis] += n

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "api_calls_by_date": dict(self.by_date),
                "api_calls_total": self.total,
                "aux_calls": dict(self.aux),
                "cache_hit_by_axis": dict(self.cache_hit),
                "cache_miss_by_axis": dict(self.cache_miss),
                "hard_stop": self.hard_stop,
                "trip_at": self.trip_at,
                "tripped": self.tripped,
            }


COUNTERS = Counters(TH.call_budget_hard_stop, TH.call_budget_trip_ratio)

# =============================================================================
#  §8.3  —  HTTP 계층: 백오프 + 서킷 브레이커 + 지연
# =============================================================================

try:
    import requests
    from requests.adapters import HTTPAdapter

    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False


class AxisAborted(RuntimeError):
    """서킷 브레이커 3회 반복 → 해당 축 중단(§8.3)."""


class CircuitBreaker:
    def __init__(self, axis: str) -> None:
        self.axis = axis
        self.consecutive_fail = 0
        self.trips = 0
        self._lock = threading.Lock()

    def ok(self) -> None:
        with self._lock:
            self.consecutive_fail = 0

    def fail(self) -> None:
        with self._lock:
            self.consecutive_fail += 1
            if self.consecutive_fail < TH.circuit_consecutive_fail:
                return
            self.trips += 1
            self.consecutive_fail = 0
        log(
            f"  ⚡ 서킷 브레이커 작동 [{self.axis}] "
            f"연속 실패 {TH.circuit_consecutive_fail}회 → {TH.circuit_cooldown_sec}초 대기 "
            f"(누적 {self.trips}/{TH.circuit_max_trips})"
        )
        if self.trips >= TH.circuit_max_trips:
            raise AxisAborted(
                f"{self.axis}: 서킷 브레이커 {TH.circuit_max_trips}회 반복 → 축 중단(§8.3). "
                "차단 회피 > 속도."
            )
        time.sleep(TH.circuit_cooldown_sec)


def polite_sleep() -> None:
    """요청 간 0.3~1.0초 랜덤 지연(§8.3)."""
    time.sleep(random.uniform(0.3, 1.0))


@dataclass
class HttpResult:
    ok: bool
    status: Optional[int]
    text: str
    error: Optional[str]
    elapsed: float
    url: str


def http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    timeout: int = 30,
    retries: int = 3,
    breaker: Optional[CircuitBreaker] = None,
    stream_binary: bool = False,
) -> HttpResult:
    """지수 백오프 + 서킷 브레이커. 실패는 실패로 반환한다(P0_FAIL_LOUD)."""
    if not _HAS_REQUESTS:
        return HttpResult(False, None, "", "requests 미설치", 0.0, url)

    last_err: Optional[str] = None
    last_status: Optional[int] = None
    t0 = time.time()
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            last_status = resp.status_code
            if resp.status_code == 200:
                if breaker:
                    breaker.ok()
                body = "" if stream_binary else resp.text
                return HttpResult(True, 200, body, None, time.time() - t0, resp.url)
            # 4xx 는 재시도해도 동일. 429/5xx 만 재시도한다.
            if resp.status_code not in (429, 500, 502, 503, 504):
                if breaker:
                    breaker.fail()
                return HttpResult(
                    False, resp.status_code, resp.text[:2000],
                    f"HTTP {resp.status_code}", time.time() - t0, resp.url,
                )
            last_err = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        if attempt < retries - 1:
            time.sleep(2 ** attempt + random.uniform(0, 0.5))
    if breaker:
        breaker.fail()
    return HttpResult(False, last_status, "", last_err, time.time() - t0, url)


# =============================================================================
#  §8.2  —  캐시 (skip-if-exists, 재실행 시 히트율 1.0)
# =============================================================================


def exctv_cache_path(corp_code: str, bsns_year: int, reprt_code: str) -> Path:
    """P0_RESUMABLE — 캐시 키에 (corp_code, bsns_year, reprt_code) 전부 포함."""
    return RAW_DIR / "dart_exctv" / corp_code / f"{bsns_year}_{reprt_code}.json"


def cache_read(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        if getattr(exc, "errno", None) == 28:  # ENOSPC
            raise ContractViolation(
                "ENOSPC — 디스크 공간 부족. 즉시 실패한다. 포맷 재시도 금지(§8.3)."
            ) from exc
        raise


# =============================================================================
#  텍스트 정규화 유틸 (§5.5 종목 매핑, 인명 키)
# =============================================================================

_CORP_SUFFIX_PATTERNS = [
    r"주식회사", r"\(주\)", r"㈜", r"\(유\)", r"유한회사", r"주식회사$",
    r"co\.?,?\s*ltd\.?", r"co\.?\s*ltd\.?", r"corporation", r"corp\.?",
    r"incorporated", r"inc\.?", r"limited", r"ltd\.?", r"l\.?l\.?c\.?",
    r"company", r"holdings?", r"그룹",
]


def normalize_corp_name(name: str) -> str:
    """§5.5 정규화: 법인격 표기 제거, 공백·대소문자·유니코드 통일."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).lower()
    s = s.replace("&", "and")
    for pat in _CORP_SUFFIX_PATTERNS:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[^0-9a-z가-힣]+", "", s)
    return s.strip()


def normalize_person_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name))
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\(.*?\)", "", s)          # 한자 병기 등 괄호 제거
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return s


_BIRTH_RE = re.compile(r"(19|20)\d{2}")


def normalize_birth_ym(raw: Any) -> Optional[str]:
    """
    DART exctvSttus 의 birth_ym 은 '1965년 03월', '196503', '1965.03' 등 표기가 섞인다.
    YYYYMM 으로 정규화하고, 복원 불가하면 None(=결측)으로 둔다. 추정 금지(P0_FAIL_LOUD).
    """
    if raw is None:
        return None
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    if not s or s in {"-", "–", "—", "해당사항없음", "미기재"}:
        return None
    digits = re.findall(r"\d+", s)
    if not digits:
        return None
    joined = "".join(digits)
    m = _BIRTH_RE.match(joined)
    if not m:
        return None
    year = joined[:4]
    rest = joined[4:]
    if len(rest) >= 2:
        month = rest[:2]
        if not ("01" <= month <= "12"):
            return None
        return f"{year}{month}"
    return None  # 연도만 있으면 월 결측 — 추정하지 않는다


# =============================================================================
#  §1.3  —  자가진단
# =============================================================================

SYNTHETIC_MARKERS = ("합성", "SYNTH", "synthetic", "더미", "dummy", "테스트주식회사")


class SelfDiagnosis:
    """§1.3 두 자가진단. 하나라도 걸리면 실행을 중단하고 보고한다."""

    def __init__(self) -> None:
        self.node_count: Optional[int] = None
        self.node_count_verdict: str = "PENDING"
        self.c_wkpl_samples: List[str] = []
        self.c_verdict: str = "PENDING"
        self.aborts: List[str] = []

    def check_node_count(self, n: int) -> None:
        self.node_count = n
        # 2,700 내외가 정상. 1,300 내외면 합성 경로 의심.
        if 1_100 <= n <= 1_600:
            self.node_count_verdict = "SUSPECT_SYNTHETIC"
            self.aborts.append(
                f"자가진단 실패: 전 상장사 노드 수 {n} — 1,300 내외는 합성 경로 의심(§1.3)."
            )
        elif n < 1_100:
            self.node_count_verdict = "TOO_FEW"
            self.aborts.append(
                f"자가진단 실패: 전 상장사 노드 수 {n} — 전 상장사 그래프로 볼 수 없다(§1.3)."
            )
        else:
            self.node_count_verdict = "OK"

    def check_c_samples(self, names: Sequence[str]) -> None:
        self.c_wkpl_samples = list(names)[:3]
        for nm in self.c_wkpl_samples:
            if any(mk in str(nm) for mk in SYNTHETIC_MARKERS):
                self.c_verdict = "SYNTHETIC_DETECTED"
                self.aborts.append(
                    f"자가진단 실패: 축 C 응답 wkplNm 에 합성 마커 발견({nm!r}) — 즉시 중단(§1.3)."
                )
                return
        self.c_verdict = "OK" if self.c_wkpl_samples else "NO_RESPONSE"

    def raise_if_failed(self) -> None:
        if self.aborts:
            raise ContractViolation("P0_LIVE_ONLY 자가진단 실패:\n  - " + "\n  - ".join(self.aborts))


DIAG = SelfDiagnosis()

# =============================================================================
#  §9.1  —  판정표 자료구조
# =============================================================================

STATUS_PRECEDENCE = ["BLOCKED_PREREQ", "UNVERIFIED", "STOP", "PENDING_MANUAL", "GO"]


@dataclass
class Gate:
    id: str
    criterion: str
    measured: Any
    threshold: Any
    passed: Optional[bool]           # None = PENDING (사람 판정)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "criterion": self.criterion,
            "measured": self.measured,
            "threshold": self.threshold,
            "pass": self.passed,
            "note": self.note,
        }


@dataclass
class AxisVerdict:
    axis: str
    as_of: str
    status: str
    gates: List[Gate] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    blocked_cause_class: Optional[str] = None
    api_calls_this_date: int = 0
    cache_hit: int = 0
    cache_miss: int = 0
    runtime_sec: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def resolve_status(self) -> str:
        """게이트 결과로부터 상태를 결정한다. 측정실패(UNVERIFIED)와 미달(STOP)을 구분한다(§11)."""
        if self.status in ("BLOCKED_PREREQ", "UNVERIFIED"):
            return self.status
        if not self.gates:
            return "UNVERIFIED"
        if any(g.passed is False for g in self.gates):
            return "STOP"
        if any(g.passed is None for g in self.gates):
            return "PENDING_MANUAL"
        return "GO"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_mode": RUN_MODE,
            "axis": self.axis,
            "as_of": self.as_of,
            "status": self.status,
            "gates": [g.to_dict() for g in self.gates],
            "known_limitations": self.known_limitations,
            "blocked_reason": self.blocked_reason,
            "blocked_cause_class": self.blocked_cause_class,
            "api_calls_this_date": self.api_calls_this_date,
            "cache_hit": self.cache_hit,
            "cache_miss": self.cache_miss,
            "runtime_sec": round(self.runtime_sec, 1),
            "extra": self.extra,
        }


def finalize_status(v: AxisVerdict) -> str:
    """
    측정값이 'UNVERIFIED' 인 게이트가 하나라도 있으면 축 상태는 UNVERIFIED 다.
    '사람이 판정할 차례(PENDING_MANUAL)'와 '측정을 못 했다(UNVERIFIED)'는 다른 상태이며,
    후자를 전자로 적으면 미측정이 검토 대기로 둔갑한다(§11).
    """
    if any(str(g.measured) == "UNVERIFIED" for g in v.gates):
        return "UNVERIFIED"
    return v.resolve_status()


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # 빈 결과도 파일로 남긴다(P0_FAIL_LOUD — 결측은 결측으로 기록)
        path.write_text("", encoding="utf-8")
        return
    fns = fieldnames or sorted({k for r in rows for k in r})
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# =============================================================================
#  사전점검(Preflight) — 원인을 구분해서 보고한다. 하나의 BLOCKED 로 뭉치지 않는다(§5.1).
# =============================================================================

def _resolve_key(pasted: str, env_name: str) -> Tuple[str, str]:
    """입력란 우선, 없으면 환경변수. 반환: (키, 출처)"""
    if (pasted or "").strip():
        return pasted.strip(), "입력란"
    env = os.environ.get(env_name, "").strip()
    if env:
        return env, f"환경변수 {env_name}"
    return "", "없음"


DART_API_KEY, _DART_KEY_SRC = _resolve_key(DART_API_KEY, "DART_API_KEY")
DATA_GO_KR_KEY, _NPS_KEY_SRC = _resolve_key(DATA_GO_KR_KEY, "DATA_GO_KR_KEY")

# 축 B는 google 라이브러리가 환경변수를 직접 읽으므로, 입력란 값을 환경변수로 승격한다.
_GCP_PATH, _GCP_PATH_SRC = _resolve_key(GCP_SA_KEY_PATH, "GOOGLE_APPLICATION_CREDENTIALS")
_GCP_PROJ, _GCP_PROJ_SRC = _resolve_key(GCP_PROJECT_ID, "GOOGLE_CLOUD_PROJECT")
if _GCP_PATH:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _GCP_PATH
if _GCP_PROJ:
    os.environ["GOOGLE_CLOUD_PROJECT"] = _GCP_PROJ


def _mask(key: str) -> str:
    """키 자체는 로그·판정표 어디에도 남기지 않는다. 길이와 앞 4자만 보인다."""
    if not key:
        return "(없음)"
    return f"{key[:4]}…{'*' * 6} (길이 {len(key)})"


def log_key_status() -> None:
    log("  키 입력 상태 (값은 마스킹된다)")
    log(f"    [1] DART_API_KEY            {_mask(DART_API_KEY)}  ← {_DART_KEY_SRC}")
    log(f"    [2] GCP_SA_KEY_PATH         "
        f"{_GCP_PATH or '(없음)'}  ← {_GCP_PATH_SRC}")
    log(f"        GCP_PROJECT_ID          {_GCP_PROJ or '(없음)'}  ← {_GCP_PROJ_SRC}")
    log(f"    [3] DATA_GO_KR_KEY          {_mask(DATA_GO_KR_KEY)}  ← {_NPS_KEY_SRC}")
    if _GCP_PATH and ("/" not in _GCP_PATH and "\\" not in _GCP_PATH):
        log("    ⚠ GCP_SA_KEY_PATH 가 파일경로가 아니라 프로젝트 ID 처럼 보인다. "
            "두 칸이 바뀌지 않았는지 확인할 것(§5.1).")

DART_HOST = "opendart.fss.or.kr"
KRX_HOST = "data.krx.co.kr"
NPS_HOST = "apis.data.go.kr"
BQ_HOST = "bigquery.googleapis.com"


@dataclass
class PreflightResult:
    """
    §5.1 의 원칙을 모든 축으로 확장한다: 서로 다른 원인을 하나의 BLOCKED 로 뭉치지 않는다.
    첫 번째 원인에서 멈추면 '키를 넣었더니 이번엔 네트워크가 막혀 있더라' 가 된다.
    그래서 감지된 **모든** 차단 사유를 blockers 에 모으고, 해결 우선순위가 가장 높은
    것을 cause_class 로 올린다.
    """

    ok: bool
    cause_class: str    # OK / NO_KEY / NET_BLOCKED / NET_DOWN / DEP_MISSING / AUTH_* / ...
    detail: str
    blockers: List[Tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return self.detail
        return " || ".join(f"[{c}] {d}" for c, d in self.blockers) or self.detail


# 해결 우선순위. 앞에 있을수록 먼저 손대야 하는 항목이다.
_CAUSE_PRIORITY = [
    "DEP_MISSING", "NET_BLOCKED", "NET_DNS", "NET_TIMEOUT", "NET_DOWN",
    "NO_KEY", "KEY_FORMAT", "AUTH_PATH", "AUTH_KEY_FORMAT", "AUTH_PROJECT",
    "AUTH_PERMISSION", "AUTH_BILLING",
]


def _combine(blockers: List[Tuple[str, str]], ok_detail: str) -> PreflightResult:
    if not blockers:
        return PreflightResult(True, "OK", ok_detail, [])
    ranked = sorted(
        blockers,
        key=lambda b: _CAUSE_PRIORITY.index(b[0]) if b[0] in _CAUSE_PRIORITY else 99,
    )
    primary = ranked[0]
    return PreflightResult(False, primary[0], primary[1], ranked)


def probe_host(host: str, *, timeout: int = 20) -> PreflightResult:
    """
    호스트 도달 가능성을 원인 구분해서 판정한다.
    프록시 정책 차단(403/407 on CONNECT)과 DNS 실패, 타임아웃을 각각 다르게 보고한다.
    """
    if not _HAS_REQUESTS:
        return PreflightResult(False, "DEP_MISSING", "requests 미설치")
    url = f"https://{host}/"
    try:
        resp = requests.get(url, timeout=timeout)
        return PreflightResult(True, "OK", f"HTTP {resp.status_code} 응답 (터널 성립)")
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        low = msg.lower()
        if "403" in msg or "407" in msg or "tunnel" in low or "proxyerror" in low:
            return PreflightResult(
                False, "NET_BLOCKED",
                f"프록시가 CONNECT 를 거부했다(조직 이그레스 정책). host={host}. 원문: {msg[:300]}",
            )
        if "name or service not known" in low or "nodename" in low or "getaddrinfo" in low:
            return PreflightResult(False, "NET_DNS", f"DNS 해석 실패. host={host}. 원문: {msg[:300]}")
        if "timed out" in low or "timeout" in low:
            return PreflightResult(False, "NET_TIMEOUT", f"타임아웃. host={host}. 원문: {msg[:300]}")
        return PreflightResult(False, "NET_DOWN", f"연결 실패. host={host}. 원문: {msg[:300]}")


@dataclass
class _Memo:
    a: Optional[PreflightResult] = None
    b: Optional[Tuple[PreflightResult, Dict[str, Any]]] = None
    c: Optional[PreflightResult] = None


_PREFLIGHT_MEMO = _Memo()   # 네트워크 프로브를 축마다 반복하지 않는다


def preflight_axis_a(force: bool = False) -> PreflightResult:
    if _PREFLIGHT_MEMO.a is not None and not force:
        return _PREFLIGHT_MEMO.a
    blockers: List[Tuple[str, str]] = []

    if not _HAS_REQUESTS:
        blockers.append(("DEP_MISSING", "requests 미설치 — pip install requests"))
    try:
        import pykrx  # noqa: F401
    except Exception:
        blockers.append((
            "DEP_MISSING",
            "pykrx 미설치 — 전 상장사 유니버스/시가총액을 얻을 수 없다. pip install pykrx",
        ))

    if not DART_API_KEY:
        blockers.append((
            "NO_KEY",
            "OpenDART API 키 없음. 환경변수 DART_API_KEY 를 설정한다. "
            "발급: https://opendart.fss.or.kr/ → 인증키 신청/관리 (이메일 인증 즉시 발급, 무료)",
        ))
    elif len(DART_API_KEY) != 40:
        blockers.append((
            "KEY_FORMAT",
            f"OpenDART 키 길이가 {len(DART_API_KEY)}자다. 정상 키는 40자 16진 문자열이다.",
        ))

    # 키 유무와 무관하게 네트워크를 반드시 확인한다 — 키를 넣은 뒤 다시 막히는 일을 막는다.
    if _HAS_REQUESTS:
        dart = probe_host(DART_HOST)
        if not dart.ok:
            blockers.append((dart.cause_class, f"OpenDART({DART_HOST}) 도달 불가 — {dart.detail}"))
        krx = probe_host(KRX_HOST)
        if not krx.ok:
            blockers.append((krx.cause_class, f"KRX({KRX_HOST}) 도달 불가 — {krx.detail}"))

    res = _combine(blockers, "OpenDART + KRX 도달 가능, 키 형식 정상")
    _PREFLIGHT_MEMO.a = res
    return res


def preflight_axis_c(force: bool = False) -> PreflightResult:
    if _PREFLIGHT_MEMO.c is not None and not force:
        return _PREFLIGHT_MEMO.c
    blockers: List[Tuple[str, str]] = []

    if not _HAS_REQUESTS:
        blockers.append(("DEP_MISSING", "requests 미설치"))
    if not DATA_GO_KR_KEY:
        blockers.append((
            "NO_KEY",
            "공공데이터포털 키 없음. 환경변수 DATA_GO_KR_KEY(Decoding 키)를 설정한다. "
            "발급: https://www.data.go.kr/ → 국민연금공단_국민연금 가입 사업장 내역 → 활용신청. "
            "마이페이지 > 데이터활용 > 활용신청 현황에서 '승인' 상태를 먼저 확인할 것(§6.1).",
        ))
    if _HAS_REQUESTS:
        nps = probe_host(NPS_HOST)
        if not nps.ok:
            blockers.append((nps.cause_class, f"공공데이터포털({NPS_HOST}) 도달 불가 — {nps.detail}"))

    res = _combine(blockers, "공공데이터포털 도달 가능, 키 존재")
    _PREFLIGHT_MEMO.c = res
    return res


def preflight_axis_b(force: bool = False) -> Tuple[PreflightResult, Dict[str, Any]]:
    """
    §5.1 — '경로 없음' / '키 형식 오류' / '프로젝트 미지정' / '권한 없음' / '결제 미설정' 을
    각각 구분한다. 네트워크 도달성은 인증과 독립적으로 항상 확인한다.
    """
    if _PREFLIGHT_MEMO.b is not None and not force:
        return _PREFLIGHT_MEMO.b

    info: Dict[str, Any] = {}
    net_blockers: List[Tuple[str, str]] = []
    if _HAS_REQUESTS:
        net = probe_host(BQ_HOST)
        info["network"] = {"host": BQ_HOST, "ok": net.ok, "detail": net.detail}
        if not net.ok:
            net_blockers.append((net.cause_class, f"BigQuery({BQ_HOST}) 도달 불가 — {net.detail}"))

    def done(res: PreflightResult) -> Tuple[PreflightResult, Dict[str, Any]]:
        merged = _combine(res.blockers + net_blockers, res.detail) if not res.ok \
            else _combine(net_blockers, res.detail)
        _PREFLIGHT_MEMO.b = (merged, info)
        return merged, info

    def blocked(cls: str, detail: str) -> Tuple[PreflightResult, Dict[str, Any]]:
        return done(PreflightResult(False, cls, detail, [(cls, detail)]))

    try:
        from google.cloud import bigquery  # noqa: F401
    except Exception:
        return blocked(
            "DEP_MISSING", "google-cloud-bigquery 미설치 — pip install google-cloud-bigquery"
        )

    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    info["GOOGLE_APPLICATION_CREDENTIALS"] = gac or None
    info["GOOGLE_CLOUD_PROJECT"] = gcp_project or None

    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    info["adc_present"] = adc_path.exists()

    # 인증 검증은 진짜 사슬이다 — 앞 단계가 깨지면 뒤 단계를 판정할 수 없다.
    # (1) 경로 검증
    if gac:
        p = Path(gac)
        if not p.exists():
            # v1.1 의 실패 유형을 정확히 짚어준다.
            looks_like_project_id = ("/" not in gac) and ("\\" not in gac)
            hint = (
                " ← 이 값은 파일경로가 아니라 '프로젝트 ID' 처럼 보인다. "
                "GOOGLE_CLOUD_PROJECT 에 넣고, GOOGLE_APPLICATION_CREDENTIALS 에는 "
                "JSON 키 파일의 절대경로를 넣어야 한다(§5.1)."
                if looks_like_project_id else ""
            )
            return blocked(
                "AUTH_PATH",
                f"GOOGLE_APPLICATION_CREDENTIALS 경로가 존재하지 않는다: {gac!r}{hint}",
            )
        if not p.is_file():
            return blocked("AUTH_PATH", f"자격증명 경로가 파일이 아니다: {gac!r}")
        # (2) 키 형식 검증
        try:
            key = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            return blocked(
                "AUTH_KEY_FORMAT",
                f"자격증명 파일이 유효한 JSON이 아니다: {type(exc).__name__}: {exc}",
            )
        if key.get("type") != "service_account":
            return blocked(
                "AUTH_KEY_FORMAT",
                f"자격증명 JSON 의 type 이 'service_account' 가 아니다: {key.get('type')!r}",
            )
        # (3) 프로젝트 폴백
        if not gcp_project:
            gcp_project = str(key.get("project_id") or "").strip()
            info["GOOGLE_CLOUD_PROJECT"] = gcp_project or None
            info["project_fallback_from_key"] = bool(gcp_project)
            if not gcp_project:
                return blocked(
                    "AUTH_PROJECT",
                    "GOOGLE_CLOUD_PROJECT 가 비었고 키 파일에도 project_id 가 없다.",
                )
    elif info["adc_present"]:
        # (4) gcloud ADC 경로 허용
        info["auth_mode"] = "ADC"
        if not gcp_project:
            return blocked(
                "AUTH_PROJECT",
                "ADC 는 있으나 GOOGLE_CLOUD_PROJECT 가 비었다. 프로젝트 ID 를 설정한다.",
            )
    else:
        return blocked(
            "NO_KEY",
            "GCP 자격증명이 없다. 다음 중 하나를 설정한다: "
            "(a) GOOGLE_APPLICATION_CREDENTIALS = 서비스계정 JSON 키 '파일의 절대경로' "
            "+ GOOGLE_CLOUD_PROJECT = '프로젝트 ID', 또는 "
            "(b) gcloud auth application-default login. "
            "최소 역할: BigQuery User + BigQuery Job User. 결제 계정 연결 필요(월 1TB 무료).",
        )

    return done(PreflightResult(True, "OK", f"자격증명 정상, project={gcp_project}"))


# =============================================================================
#  축 A — 유니버스 (전 상장사) + 시가총액 하위 1,000
# =============================================================================


@dataclass
class Universe:
    as_of: date
    tickers: List[str]
    market_cap: Dict[str, int]
    measure_set: List[str]           # 시총 하위 N
    source: str


def fetch_universe(as_of: date, breaker: CircuitBreaker) -> Universe:
    """
    전 상장사 유니버스와 시가총액을 KRX 에서 받는다.
    NO_KNOWN_DEAD_CALL — 지수구성종목 파일 호출은 사용하지 않는다.
    """
    guard_dead_call("fetch_universe")  # 런타임 가드 자체 점검
    from pykrx import stock

    ds = as_of.strftime("%Y%m%d")
    log(f"  KRX 시가총액 조회 (market=ALL, date={ds})")
    COUNTERS.aux_call("krx_market_cap")     # OpenDART 예산과 분리해 센다
    cap_df = stock.get_market_cap_by_ticker(ds, market="ALL")
    if cap_df is None or len(cap_df) == 0:
        raise RuntimeError(f"KRX 시가총액 응답이 비었다 (date={ds}) — 휴장일이거나 응답 실패")

    caps: Dict[str, int] = {}
    for tkr, row in cap_df.iterrows():
        try:
            caps[str(tkr)] = int(row["시가총액"])
        except Exception:
            continue

    tickers = sorted(caps)
    # 시총 0 은 거래정지/데이터 결측. 하위 정렬을 오염시키므로 제외하고 그 수를 기록한다.
    positive = {t: c for t, c in caps.items() if c > 0}
    zero_cap = len(caps) - len(positive)
    ordered = sorted(positive, key=lambda t: positive[t])
    measure = ordered[: TH.measure_universe_size]
    log(
        f"  전 상장사 {len(tickers)}종목 / 시총>0 {len(positive)} / 시총0 {zero_cap} "
        f"→ 측정대상 하위 {len(measure)}종목"
    )
    return Universe(as_of, tickers, caps, measure, source="pykrx.get_market_cap_by_ticker")


# =============================================================================
#  축 A — corpCode 매핑 + §3.3 진단
# =============================================================================

MISS_CLASSES = ["①우선주", "②스팩", "③리츠", "④ETF/ETN", "⑤신규상장", "⑥원인불명"]


def classify_mapping_miss(ticker: str, name: Optional[str], name_in_corpcode: bool) -> str:
    """§3.3-3 실패 유형 자동 분류."""
    nm = (name or "").upper()
    # ④ ETF/ETN — 대표 브랜드 접두어
    etf_brands = (
        "KODEX", "TIGER", "KBSTAR", "ARIRANG", "HANARO", "KOSEF", "ACE", "SOL",
        "PLUS", "RISE", "TIMEFOLIO", "WOORI", "ETN", "레버리지", "인버스", "선물",
    )
    if any(b in nm for b in etf_brands):
        return "④ETF/ETN"
    if "스팩" in nm or "SPAC" in nm:
        return "②스팩"
    if "리츠" in nm or "REIT" in nm:
        return "③리츠"
    # ① 우선주 — 한국 보통주 종목코드는 끝자리 0, 우선주는 5/7/9/K/L/M 등
    if len(ticker) == 6 and not ticker.endswith("0"):
        return "①우선주"
    if re.search(r"우[BC]?$", name or "") or (name or "").endswith("우"):
        return "①우선주"
    # ⑤ 신규상장 — 상호는 corpCode.xml 에 있으나 stock_code 가 아직 비어 있는 경우
    if name_in_corpcode:
        return "⑤신규상장"
    return "⑥원인불명"


def fetch_corp_codes(breaker: CircuitBreaker) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    corpCode.xml 다운로드 → (stock_code→corp_code, stock_code→corp_name, normname→corp_code)
    """
    cache_path = RAW_DIR / "dart_corpcode" / "corpCode.json"
    cached = cache_read(cache_path)
    if cached:
        COUNTERS.hit("A")
        log(f"  corpCode 캐시 히트 ({len(cached['by_stock'])}종목 매핑)")
        return cached["by_stock"], cached["names"], cached["by_norm"]

    COUNTERS.miss("A")
    COUNTERS.api_call("corpcode")
    polite_sleep()
    url = f"https://{DART_HOST}/api/corpCode.xml"
    if not _HAS_REQUESTS:
        raise RuntimeError("requests 미설치")
    t0 = time.time()
    resp = requests.get(url, params={"crtfc_key": DART_API_KEY}, timeout=120)
    if resp.status_code != 200:
        breaker.fail()
        raise RuntimeError(f"corpCode.xml HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.content[:2] != b"PK":
        # DART 는 오류를 XML/JSON 으로 돌려준다.
        breaker.fail()
        raise RuntimeError(f"corpCode.xml 이 ZIP 이 아니다 — 응답 원문: {resp.text[:400]}")
    breaker.ok()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_name = zf.namelist()[0]
        xml_bytes = zf.read(xml_name)

    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    by_stock: Dict[str, str] = {}
    names: Dict[str, str] = {}
    by_norm: Dict[str, str] = {}
    total = 0
    for el in root.iter("list"):
        total += 1
        corp_code = (el.findtext("corp_code") or "").strip()
        corp_name = (el.findtext("corp_name") or "").strip()
        stock_code = (el.findtext("stock_code") or "").strip()
        if corp_name:
            by_norm.setdefault(normalize_corp_name(corp_name), corp_code)
        if stock_code and stock_code != " " and len(stock_code) == 6:
            by_stock[stock_code] = corp_code
            names[stock_code] = corp_name
    log(f"  corpCode.xml 파싱: 전체 {total}건 중 종목코드 보유 {len(by_stock)}건 (§3.3-1), "
        f"소요 {time.time() - t0:.1f}s")
    cache_write(cache_path, {"by_stock": by_stock, "names": names, "by_norm": by_norm})
    return by_stock, names, by_norm


# =============================================================================
#  축 A — 임원 수집 + PIT (P0_PIT_STRICT)
# =============================================================================


@dataclass
class ExecRecord:
    stock_code: str
    corp_code: str
    name: str
    birth_ym: Optional[str]
    rcept_dt: str
    position: str


@dataclass
class ExecFetch:
    records_by_stock: Dict[str, List[ExecRecord]]
    corps_with_records: Set[str]
    corps_no_data: Set[str]
    corps_error: Dict[str, str]
    pit_dropped: List[Dict[str, Any]]
    max_rcept_dt: Optional[str]


# DART 응답 status 코드. 000/013 만 '최종 결과'이며 나머지는 전부 오류다.
#   013 = 조회된 데이터 없음 (정상적인 빈 결과)
DART_TERMINAL_STATUS = {"000", "013"}
# 키·쿼터·점검처럼 재시도로 풀리지 않거나 전 종목에 동일하게 적용되는 치명 오류.
# 이걸 종목별 오류로 흘려보내면 A-1 이 0 으로 떨어져 '측정 실패'가 '결과 미달(STOP)'로 둔갑한다(§11).
DART_FATAL_STATUS = {
    "010": "등록되지 않은 인증키",
    "011": "사용할 수 없는 인증키",
    "012": "접근할 수 없는 IP",
    "020": "요청 제한 초과 (일일 한도 소진)",
    "021": "조회 가능한 회사 개수 초과",
    "101": "부적절한 접근",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
    "901": "사용자 계정의 개인정보 보유기간 만료",
}


class DartFatalStatus(RuntimeError):
    """전 종목에 동일하게 적용되는 DART 오류. 축 전체를 UNVERIFIED 로 만든다."""


def _parse_exctv_payload(
    payload: Any, stock_code: str, corp_code: str, as_of: date,
    pit_dropped: List[Dict[str, Any]],
) -> Tuple[List[ExecRecord], Optional[str]]:
    """DART exctvSttus 응답 파싱 + PIT 강제 폐기(P0_PIT_STRICT). 반환: (레코드, 최대접수일)"""
    out: List[ExecRecord] = []
    max_rcept: Optional[str] = None
    if not isinstance(payload, dict):
        return out, None
    if payload.get("status") != "000":
        return out, None
    as_of_s = as_of.strftime("%Y%m%d")
    for row in payload.get("list") or []:
        rcept_no = str(row.get("rcept_no") or "")
        rcept_dt = rcept_no[:8]
        if len(rcept_dt) != 8 or not rcept_dt.isdigit():
            pit_dropped.append({
                "stock_code": stock_code, "corp_code": corp_code,
                "rcept_no": rcept_no, "rcept_dt": rcept_dt,
                "as_of": as_of_s, "reason": "접수일자 파싱 불가",
            })
            continue
        if rcept_dt > as_of_s:
            # 예외 없음. 기준일 이후 접수 레코드는 무조건 폐기한다.
            pit_dropped.append({
                "stock_code": stock_code, "corp_code": corp_code,
                "rcept_no": rcept_no, "rcept_dt": rcept_dt,
                "as_of": as_of_s, "reason": "기준일 이후 접수",
            })
            continue
        nm = normalize_person_name(row.get("nm"))
        if not nm:
            continue
        out.append(ExecRecord(
            stock_code=stock_code,
            corp_code=corp_code,
            name=nm,
            birth_ym=normalize_birth_ym(row.get("birth_ym")),
            rcept_dt=rcept_dt,
            position=str(row.get("ofcps") or ""),
        ))
        if max_rcept is None or rcept_dt > max_rcept:
            max_rcept = rcept_dt
    return out, max_rcept


def fetch_executives(
    targets: List[Tuple[str, str]],   # (stock_code, corp_code)
    bsns_year: int,
    reprt_code: str,
    as_of: date,
    date_key: str,
    breaker: CircuitBreaker,
    label: str,
) -> ExecFetch:
    """임원현황 벌크 수집. 캐시 우선(skip-if-exists), 워커 ≤4, 지연·백오프 적용."""
    records_by_stock: Dict[str, List[ExecRecord]] = {}
    corps_with_records: Set[str] = set()
    corps_no_data: Set[str] = set()
    corps_error: Dict[str, str] = {}
    pit_dropped: List[Dict[str, Any]] = []
    max_rcept_all: Optional[str] = None
    lock = threading.Lock()

    url = f"https://{DART_HOST}/api/exctvSttus.json"

    def work(item: Tuple[str, str]) -> None:
        nonlocal max_rcept_all
        stock_code, corp_code = item
        path = exctv_cache_path(corp_code, bsns_year, reprt_code)
        payload = cache_read(path)
        if payload is not None:
            COUNTERS.hit("A")
        else:
            COUNTERS.miss("A")
            COUNTERS.api_call(date_key)      # 예산 초과 시 CallBudgetExceeded 로 즉시 중단
            polite_sleep()
            res = http_get(
                url,
                params={
                    "crtfc_key": DART_API_KEY, "corp_code": corp_code,
                    "bsns_year": str(bsns_year), "reprt_code": reprt_code,
                },
                breaker=breaker,
            )
            if not res.ok:
                with lock:
                    corps_error[stock_code] = res.error or f"HTTP {res.status}"
                return
            try:
                payload = json.loads(res.text)
            except Exception as exc:
                with lock:
                    corps_error[stock_code] = f"JSON 파싱 실패: {exc}"
                return
            st = payload.get("status") if isinstance(payload, dict) else None
            if st in DART_FATAL_STATUS:
                # 오류 응답을 캐시하면 다음 실행이 '히트율 1.0'을 보고하면서 쓰레기를 읽는다.
                raise DartFatalStatus(
                    f"DART status={st} ({DART_FATAL_STATUS[st]}) — "
                    f"corp_code={corp_code}. 전 종목에 동일하게 적용되는 오류이므로 "
                    "종목별 오류로 흘려보내지 않고 즉시 중단한다."
                )
            if st not in DART_TERMINAL_STATUS:
                with lock:
                    corps_error[stock_code] = f"DART status={st} (캐시하지 않음)"
                return
            # 000(정상)과 013(데이터 없음)만 캐시한다 — 재실행 시 0콜이 되어야 한다.
            cache_write(path, payload)

        status = payload.get("status") if isinstance(payload, dict) else None
        local_drop: List[Dict[str, Any]] = []
        recs, mx = _parse_exctv_payload(payload, stock_code, corp_code, as_of, local_drop)
        with lock:
            pit_dropped.extend(local_drop)
            if recs:
                records_by_stock[stock_code] = recs
                corps_with_records.add(stock_code)
                if mx and (max_rcept_all is None or mx > max_rcept_all):
                    max_rcept_all = mx
            elif status == "013":
                corps_no_data.add(stock_code)          # 조회된 데이터 없음
            elif status == "000":
                corps_no_data.add(stock_code)          # 응답은 정상이나 전부 PIT 폐기
            else:
                corps_error[stock_code] = f"DART status={status}"

    log(f"  [{label}] 임원현황 수집 대상 {len(targets)}종목 "
        f"(bsns_year={bsns_year}, reprt_code={reprt_code}, as_of={as_of})")
    with ThreadPoolExecutor(max_workers=TH.max_workers) as pool:
        futs = [pool.submit(work, t) for t in targets]
        done = 0
        for fut in as_completed(futs):
            exc = fut.exception()
            if isinstance(exc, (CallBudgetExceeded, AxisAborted, ContractViolation, DartFatalStatus)):
                for f in futs:
                    f.cancel()
                raise exc
            if exc:
                with lock:
                    corps_error[f"_unknown_{done}"] = f"{type(exc).__name__}: {exc}"
            done += 1
            if done % 250 == 0:
                log(f"    …{done}/{len(targets)} (누적 API 콜 {COUNTERS.total})")

    log(f"  [{label}] 레코드보유 {len(corps_with_records)} / 데이터없음 {len(corps_no_data)} "
        f"/ 오류 {len(corps_error)} / PIT폐기 {len(pit_dropped)}건")
    return ExecFetch(
        records_by_stock, corps_with_records, corps_no_data,
        corps_error, pit_dropped, max_rcept_all,
    )


# =============================================================================
#  축 A — 겸직 그래프
# =============================================================================


@dataclass
class CoexecGraph:
    """
    edges       : 무향 종목쌍 → 그 쌍을 잇는 인물키 집합
    person_span : 인물키 → 등재 종목 집합
    """
    edges: Dict[Tuple[str, str], Set[Tuple[str, str]]]
    person_span: Dict[Tuple[str, str], Set[str]]
    n_nodes: int
    n_records: int
    n_birth_missing: int
    n_person_keys_usable: int


def build_coexec_graph(records_by_stock: Dict[str, List[ExecRecord]]) -> CoexecGraph:
    """
    겸직 엣지 = 동일 인물(성명 + 출생년월)이 두 종목에 동시 임원 등재(§3.1).
    출생년월이 결측인 레코드는 인물키를 만들 수 없다. 동명이인 오결합을 막기 위해
    엣지 생성에서 제외하고, 그 수를 결측으로 기록한다(P0_FAIL_LOUD — 추정 금지).
    """
    person_span: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    n_records = 0
    n_birth_missing = 0
    for stock_code, recs in records_by_stock.items():
        for r in recs:
            n_records += 1
            if not r.birth_ym:
                n_birth_missing += 1
                continue
            person_span[(r.name, r.birth_ym)].add(stock_code)

    edges: Dict[Tuple[str, str], Set[Tuple[str, str]]] = defaultdict(set)
    for pkey, stocks in person_span.items():
        if len(stocks) < 2:
            continue
        ordered = sorted(stocks)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                edges[(ordered[i], ordered[j])].add(pkey)

    return CoexecGraph(
        edges=dict(edges),
        person_span=dict(person_span),
        n_nodes=len(records_by_stock),
        n_records=n_records,
        n_birth_missing=n_birth_missing,
        n_person_keys_usable=len(person_span),
    )


def edges_incident_to(graph_edges: Iterable[Tuple[str, str]], measure: Set[str]) -> Set[Tuple[str, str]]:
    """측정대상에 한쪽이라도 걸린 엣지(§3.1 — 상대 노드가 측정 대상 밖이어도 유지)."""
    return {e for e in graph_edges if e[0] in measure or e[1] in measure}


# =============================================================================
#  축 A 실행
# =============================================================================


def run_axis_a(limitations: List[str]) -> Tuple[List[AxisVerdict], Optional[str]]:
    """
    반환: (판정표, 중단사유)
    예산 초과·축 중단이 발생해도 **거기까지의 판정표는 반드시 반환한다**(§4.4-2).
    예외를 그대로 올리면 완료된 기준일의 측정 결과가 통째로 사라진다.
    """
    verdicts: List[AxisVerdict] = []
    stop_reason: Optional[str] = None
    pre = preflight_axis_a()
    if not pre.ok:
        for label, as_of, _y, _r in AXIS_A_BASES:
            v = AxisVerdict(
                axis="A", as_of=as_of.isoformat(), status="BLOCKED_PREREQ",
                blocked_reason=pre.summary(), blocked_cause_class=pre.cause_class,
            )
            v.extra["preflight_blockers"] = [{"cause_class": c, "detail": d} for c, d in pre.blockers]
            v.known_limitations.append(
                "사전점검 단계에서 차단되어 어떤 게이트도 측정되지 않았다. "
                "STOP(측정 결과 미달)이 아니라 BLOCKED_PREREQ(측정 자체 불가)다(§11)."
            )
            verdicts.append(v)
        for c, d in pre.blockers:
            log(f"  축 A BLOCKED_PREREQ [{c}] {d}")
        return verdicts, None

    breaker = CircuitBreaker("A")
    try:
        by_stock, corp_names, by_norm = fetch_corp_codes(breaker)
    except Exception as exc:
        for label, as_of, _y, _r in AXIS_A_BASES:
            verdicts.append(AxisVerdict(
                axis="A", as_of=as_of.isoformat(), status="UNVERIFIED",
                blocked_reason=f"corpCode.xml 확보 실패: {type(exc).__name__}: {exc}",
            ))
        log(f"  ⚠ corpCode.xml 확보 실패 — 축 A 전체 UNVERIFIED: {exc}")
        return verdicts, None

    for label, as_of, bsns_year, reprt_code in AXIS_A_BASES:
        if stop_reason:
            verdicts.append(AxisVerdict(
                axis="A", as_of=as_of.isoformat(), status="UNVERIFIED",
                blocked_reason=f"선행 기준일에서 중단되어 착수하지 못했다: {stop_reason}",
            ))
            continue
        t0 = time.time()
        date_key = as_of.isoformat()
        # 캐시 히트/미스는 축 누적값이므로 기준일 몫만 빼서 기록한다(§8.4).
        hit0 = COUNTERS.cache_hit.get("A", 0)
        miss0 = COUNTERS.cache_miss.get("A", 0)
        v = AxisVerdict(axis="A", as_of=date_key, status="PENDING")
        deadline = statutory_deadline(bsns_year, reprt_code)
        v.extra.update({
            "base_label": label, "bsns_year": bsns_year, "reprt_code": reprt_code,
            "reprt_name": REPRT_SPEC[reprt_code][0],
            "statutory_deadline": deadline.isoformat(),
        })
        log("")
        rule(f"축 A — 기준일 {label} = {as_of} / {bsns_year} {REPRT_SPEC[reprt_code][0]} "
            f"(제출기한 {deadline})", "-")

        if deadline > as_of:
            v.status = "UNVERIFIED"
            v.blocked_reason = (
                f"기준일 {as_of} 시점에 {bsns_year} {REPRT_SPEC[reprt_code][0]} 의 "
                f"법정 제출기한({deadline})이 미도래 — 관측 불가(§3.2)."
            )
            verdicts.append(v)
            continue

        try:
            uni = fetch_universe(as_of, breaker)
            if label == "T_NOW":
                DIAG.check_node_count(len(uni.tickers))
                DIAG.raise_if_failed()

            # --- §3.3 corp_code 매핑 진단 -------------------------------------
            mapped = {t: by_stock[t] for t in uni.tickers if t in by_stock}
            missing = [t for t in uni.tickers if t not in by_stock]
            miss_rows: List[Dict[str, Any]] = []
            miss_counter: Counter = Counter()
            for t in missing:
                nm = corp_names.get(t)
                if nm is None:
                    try:
                        from pykrx import stock as _st
                        COUNTERS.aux_call("krx_ticker_name")
                        nm = _st.get_market_ticker_name(t)
                    except Exception:
                        nm = None
                in_corpcode = bool(nm) and normalize_corp_name(nm) in by_norm
                cls = classify_mapping_miss(t, nm, in_corpcode)
                miss_counter[cls] += 1
                miss_rows.append({
                    "as_of": date_key, "ticker": t, "name": nm or "",
                    "market_cap": uni.market_cap.get(t, 0),
                    "miss_class": cls, "name_found_in_corpcode": in_corpcode,
                })
            write_csv(REPORTS_DIR / "diag_corpcode_miss.csv", miss_rows)
            unknown = miss_counter.get("⑥원인불명", 0)
            log(f"  매핑 성공 {len(mapped)} / 실패 {len(missing)} → " +
                ", ".join(f"{k}:{miss_counter.get(k, 0)}" for k in MISS_CLASSES))
            v.extra["mapping"] = {
                "universe_total": len(uni.tickers),
                "mapped": len(mapped),
                "missing": len(missing),
                "miss_breakdown": {k: miss_counter.get(k, 0) for k in MISS_CLASSES},
            }
            if unknown > TH.corpcode_unknown_miss_max:
                v.status = "UNVERIFIED"
                v.blocked_reason = (
                    f"§3.3-4 — ⑥원인불명 매핑 실패가 {unknown}종목으로 임계 "
                    f"{TH.corpcode_unknown_miss_max}종목을 초과했다. 판정을 보류한다."
                )
                log(f"  ⚠ {v.blocked_reason}")
                verdicts.append(v)
                continue

            # --- 카나리 (P0_CANARY_FIRST) ------------------------------------
            measure_set = set(uni.measure_set)
            targets = sorted(mapped.items())
            canary = targets[: TH.canary_size]
            log(f"  카나리 {len(canary)}종목 선행 수집 (P0_CANARY_FIRST)")
            cf = fetch_executives(canary, bsns_year, reprt_code, as_of, date_key, breaker, "canary")
            if not cf.corps_with_records:
                v.status = "UNVERIFIED"
                v.blocked_reason = (
                    f"카나리 {len(canary)}종목에서 임원 레코드를 하나도 얻지 못했다. "
                    f"오류 표본: {list(cf.corps_error.items())[:3]}. 벌크 진입을 금지한다(P0_CANARY_FIRST)."
                )
                log(f"  ⚠ {v.blocked_reason}")
                verdicts.append(v)
                continue
            log(f"  카나리 통과 — {len(cf.corps_with_records)}/{len(canary)}종목 레코드 확보")
            mark_contract("P0_CANARY_FIRST", "PASS")   # 벌크 진입 전 카나리가 실제로 돌았다

            # --- 벌크 -----------------------------------------------------------
            ef = fetch_executives(targets, bsns_year, reprt_code, as_of, date_key, breaker, label)
            mark_contract("P0_PIT_STRICT", "PASS")     # 접수일자 기준 폐기가 실제로 적용되었다
            write_csv(REPORTS_DIR / "diag_pit_dropped.csv", ef.pit_dropped)
            pit_dist = Counter(r["rcept_dt"][:6] for r in ef.pit_dropped if r["rcept_dt"][:6])
            v.extra["pit_dropped"] = {
                "total": len(ef.pit_dropped),
                "by_month": dict(sorted(pit_dist.items())),
            }
            v.extra["max_rcept_dt"] = ef.max_rcept_dt

            # --- 그래프 (전 상장사) --------------------------------------------
            g = build_coexec_graph(ef.records_by_stock)
            inc = edges_incident_to(g.edges, measure_set)
            # 그래프는 전 상장사로 구성했고 측정은 하위 1,000종목으로 한정했다.
            mark_contract("P0_GRAPH_FULL_MEASURE_SUB", "PASS")
            internal = {e for e in inc if e[0] in measure_set and e[1] in measure_set}
            external = inc - internal
            linked_stocks = {s for e in inc for s in e if s in measure_set}
            log(f"  그래프: 노드(레코드보유) {g.n_nodes} / 인물키 {g.n_person_keys_usable} "
                f"/ 전체 엣지 {len(g.edges)}")
            log(f"  측정대상 걸친 엣지 {len(inc)} (내부 {len(internal)} / 외부 {len(external)}), "
                f"링크 걸린 하위1000 종목 {len(linked_stocks)}")

            # --- 게이트 ---------------------------------------------------------
            n_mapped = len(mapped)
            a1 = len(ef.corps_with_records) / n_mapped if n_mapped else 0.0
            a2 = g.n_birth_missing / g.n_records if g.n_records else 1.0
            denom = len(measure_set & set(mapped))
            a3 = len(linked_stocks) / denom if denom else 0.0
            a5 = len(inc)

            v.gates = [
                Gate("A-1", "임원 레코드 1건 이상 확보 비율 (매핑 성공 종목 기준)",
                     round(a1, 4), TH.A1_exec_record_coverage, a1 >= TH.A1_exec_record_coverage),
                Gate("A-2", "출생년월 결측률",
                     round(a2, 4), TH.A2_birth_ym_missing, a2 <= TH.A2_birth_ym_missing),
                Gate("A-3", "겸직 링크가 걸린 하위 1,000종목 비율 (전 상장사 그래프 기준)",
                     round(a3, 4), TH.A3_linked_share_bottom1000, a3 >= TH.A3_linked_share_bottom1000,
                     note=f"분모 = 측정대상 중 매핑 성공 {denom}종목"),
                Gate("A-4", "겸직 링크 수기 검증 정확도", "PENDING",
                     f"{TH.A4_manual_sample}건 CSV 수기 판정", None,
                     note="reports/manual_check_A_coexec_links.csv — 사람이 판정할 때까지 PENDING"),
                Gate("A-5", "총 겸직 링크 수 (하위 1,000종목에 하나 이상 걸린 엣지)",
                     a5, TH.A5_total_links, a5 >= TH.A5_total_links,
                     note=("임계 근처(600±50) — 판정표에 명시하며 임계를 조정하지 않는다(§3.4)"
                           if abs(a5 - TH.A5_total_links) <= 50 else "")),
            ]
            v.extra["graph"] = {
                "nodes_with_records": g.n_nodes,
                "person_keys_usable": g.n_person_keys_usable,
                "edges_total": len(g.edges),
                "edges_incident_measure": len(inc),
                "edges_internal": len(internal),
                "edges_external": len(external),
                "linked_measure_stocks": len(linked_stocks),
                "exec_records": g.n_records,
                "birth_ym_missing": g.n_birth_missing,
            }
            v.known_limitations += [
                "겸직 엣지는 (성명 + 출생년월) 동일성으로 판정한다. 출생년월 결측 레코드는 "
                "동명이인 오결합을 피하기 위해 엣지 생성에서 제외했으며 그 수를 A-2 로 보고한다.",
                "A-5 는 인물 다중 겸직을 합산하지 않고 '고유 종목쌍' 수로 센다(보수적 계수).",
                "제출기한은 12월 결산법인 기준으로 계산했다. 비12월 결산법인은 실제 기한이 다르다.",
            ]
            if label == "T_NOW":
                _write_manual_check_a(inc, g, corp_names, uni)

            v.status = finalize_status(v)

        except CallBudgetExceeded as exc:
            v.status = "UNVERIFIED"
            v.blocked_reason = f"호출 예산 중단(§4.4): {exc}"
            stop_reason = str(exc)
            log(f"  ⚠ {v.blocked_reason}")
        except ContractViolation:
            raise                       # 자가진단 실패는 삼키지 않는다(§1.3)
        except (AxisAborted, DartFatalStatus) as exc:
            v.status = "UNVERIFIED"
            v.blocked_reason = f"{type(exc).__name__}: {exc}"
            stop_reason = str(exc)
            log(f"  ⚠ 축 A 중단 [{label}]: {v.blocked_reason}")
        except Exception as exc:
            v.status = "UNVERIFIED"
            v.blocked_reason = f"{type(exc).__name__}: {exc}"
            log(f"  ⚠ 축 A 측정 실패 [{label}]: {v.blocked_reason}")
            log(traceback.format_exc())

        v.api_calls_this_date = COUNTERS.by_date.get(date_key, 0)
        v.cache_hit = COUNTERS.cache_hit.get("A", 0) - hit0
        v.cache_miss = COUNTERS.cache_miss.get("A", 0) - miss0
        v.runtime_sec = time.time() - t0
        verdicts.append(v)

    return verdicts, stop_reason


def _write_manual_check_a(
    inc: Set[Tuple[str, str]], g: CoexecGraph, corp_names: Dict[str, str], uni: Universe,
) -> None:
    """§9.3 — 겸직 링크 200건 수기 검증 CSV."""
    rows: List[Dict[str, Any]] = []
    # 링크 200건 = 200행. 한 쌍을 여러 인물이 잇더라도 행을 늘리지 않고 대표 1명 + 인원수로 적는다.
    for a, b in sorted(inc)[: TH.A4_manual_sample]:
        persons = sorted(g.edges.get((a, b), set()))
        pname, pbirth = persons[0] if persons else ("", "")
        rows.append({
            "stock_a": a, "name_a": corp_names.get(a, ""),
            "stock_b": b, "name_b": corp_names.get(b, ""),
            "person_name": pname, "birth_ym": pbirth,
            "n_linking_persons": len(persons),
            "other_persons": "; ".join(f"{n}({y})" for n, y in persons[1:4]),
            "cap_a": uni.market_cap.get(a, 0), "cap_b": uni.market_cap.get(b, 0),
            "dart_a": f"https://dart.fss.or.kr/dsab007/main.do?textCrpNm={corp_names.get(a, '')}",
            "verdict_TRUE_or_FALSE": "",     # 사람이 채운다
            "reviewer_note": "",
        })
    write_csv(REPORTS_DIR / "manual_check_A_coexec_links.csv", rows)
    log(f"  수기 검증 CSV {len(rows)}행(링크 {len(rows)}건) 저장 → "
        f"manual_check_A_coexec_links.csv (A-4 는 PENDING 유지)")


# =============================================================================
#  축 A-Δ — 분기별 엣지 생성/소멸
# =============================================================================


def run_axis_a_delta(limitations: List[str]) -> Tuple[AxisVerdict, Optional[str]]:
    """반환: (판정표, 중단사유). 중단해도 그때까지 구성된 스냅샷으로 전이를 계산해 보고한다."""
    t0 = time.time()
    hit0 = COUNTERS.cache_hit.get("A", 0)
    miss0 = COUNTERS.cache_miss.get("A", 0)
    v = AxisVerdict(axis="A-delta", as_of=AXIS_AD_SNAPSHOTS[-1][1].isoformat(), status="PENDING")
    v.extra["snapshots"] = [
        {"label": lb, "date": d.isoformat(), "bsns_year": y, "reprt_code": rc,
         "reprt_name": REPRT_SPEC[rc][0], "deadline": statutory_deadline(y, rc).isoformat()}
        for lb, d, y, rc in AXIS_AD_SNAPSHOTS
    ]

    pre = preflight_axis_a()
    if not pre.ok:
        v.status = "BLOCKED_PREREQ"
        v.blocked_reason = pre.summary()
        v.blocked_cause_class = pre.cause_class
        v.extra["preflight_blockers"] = [{"cause_class": c, "detail": d} for c, d in pre.blockers]
        v.known_limitations.append(
            "사전점검 단계에서 차단되어 스냅샷을 하나도 구성하지 못했다. STOP 이 아니라 BLOCKED_PREREQ 다."
        )
        v.runtime_sec = time.time() - t0
        for c, d in pre.blockers:
            log(f"  축 A-Δ BLOCKED_PREREQ [{c}] {d}")
        return v, None

    run_date = date.today()
    breaker = CircuitBreaker("A-delta")
    stop_reason: Optional[str] = None
    try:
        by_stock, corp_names, _ = fetch_corp_codes(breaker)
    except Exception as exc:
        v.status = "UNVERIFIED"
        v.blocked_reason = f"corpCode.xml 확보 실패: {type(exc).__name__}: {exc}"
        v.runtime_sec = time.time() - t0
        log(f"  ⚠ {v.blocked_reason}")
        return v, None

    snap_graphs: Dict[str, CoexecGraph] = {}
    snap_measure: Dict[str, Set[str]] = {}
    snap_status: Dict[str, str] = {}
    snap_max_rcept: Dict[str, Optional[str]] = {}

    try:
        for lb, sdate, byear, rcode in AXIS_AD_SNAPSHOTS:
            log("")
            deadline = statutory_deadline(byear, rcode)
            rule(f"축 A-Δ 스냅샷 {lb} = {sdate} / {byear} {REPRT_SPEC[rcode][0]} "
                 f"(제출기한 {deadline})", "-")

            # --- §4.3 제출기한 가드 (P0_SNAPSHOT_DEADLINE_GUARD) -------------
            # 벌크 수집 '전에' 기한을 확인한다는 것이 계약의 내용이므로, 여기서 확인 사실을 남긴다.
            mark_contract("P0_SNAPSHOT_DEADLINE_GUARD", "PASS")
            uni = fetch_universe(sdate, breaker)
            snap_measure[lb] = set(uni.measure_set)
            mapped = {t: by_stock[t] for t in uni.tickers if t in by_stock}
            targets = sorted(mapped.items())

            if deadline > run_date:
                log(f"  ⚠ 제출기한 {deadline} > 실행일 {run_date} — 선행 프로브 "
                    f"{TH.canary_size}종목만 던진다(§4.3).")
                probe = fetch_executives(
                    targets[: TH.canary_size], byear, rcode, run_date,
                    f"AD_{lb}", breaker, f"{lb}-probe",
                )
                if not probe.corps_with_records:
                    snap_status[lb] = "UNVERIFIED"
                    log(f"  {lb} UNVERIFIED — 접수 확인 0종목. 벌크 진입 없이 종료(§4.3).")
                    continue
                log(f"  {lb} 조기 접수 {len(probe.corps_with_records)}종목 확인 → 벌크 진행")

            ef = fetch_executives(targets, byear, rcode, run_date, f"AD_{lb}", breaker, lb)
            if not ef.corps_with_records:
                snap_status[lb] = "UNVERIFIED"
                log(f"  {lb} UNVERIFIED — 레코드 0건")
                continue
            snap_graphs[lb] = build_coexec_graph(ef.records_by_stock)
            snap_status[lb] = "OK"
            snap_max_rcept[lb] = ef.max_rcept_dt
            log(f"  {lb} 그래프 구성 완료 — 엣지 {len(snap_graphs[lb].edges)}, "
                f"최종접수일 {ef.max_rcept_dt}")

    except CallBudgetExceeded as exc:
        # 중단하되, 이미 구성된 스냅샷으로 전이 계산까지는 진행한다(§4.4-2).
        stop_reason = f"호출 예산 중단(§4.4): {exc}"
        log(f"  ⚠ {stop_reason}")
    except (AxisAborted, DartFatalStatus) as exc:
        stop_reason = f"{type(exc).__name__}: {exc}"
        log(f"  ⚠ 축 A-Δ 중단: {stop_reason}")
    except Exception as exc:
        stop_reason = f"{type(exc).__name__}: {exc}"
        log(f"  ⚠ 축 A-Δ 측정 실패: {stop_reason}")
        log(traceback.format_exc())

    if stop_reason:
        v.blocked_reason = stop_reason
        for lb, _d, _y, _r in AXIS_AD_SNAPSHOTS:
            snap_status.setdefault(lb, "UNVERIFIED")
    v.extra["snapshot_status"] = snap_status
    v.extra["snapshot_max_rcept_dt"] = snap_max_rcept

    # --- 전이 계산 -------------------------------------------------------------
    transitions: List[Dict[str, Any]] = []
    event_rows: List[Dict[str, Any]] = []
    born_shares: List[float] = []
    born_totals: List[int] = []

    for i in range(len(AXIS_AD_SNAPSHOTS) - 1):
        la = AXIS_AD_SNAPSHOTS[i][0]
        lb2 = AXIS_AD_SNAPSHOTS[i + 1][0]
        name = f"{la}→{lb2}"
        if snap_status.get(la) != "OK" or snap_status.get(lb2) != "OK":
            transitions.append({
                "transition": name, "status": "SKIPPED",
                "reason": "미성립 스냅샷이 낀 전이는 계산하지 않는다(§4.3). "
                          "빈 스냅샷을 쓰면 소멸이 전부 허위로 잡힌다.",
            })
            log(f"  전이 {name} SKIPPED — 스냅샷 미성립")
            continue

        ga, gb = snap_graphs[la], snap_graphs[lb2]
        # 구성 변화가 이벤트로 위장하지 않도록 두 스냅샷의 측정대상 교집합을 쓴다.
        measure = snap_measure[la] & snap_measure[lb2]
        ea = edges_incident_to(ga.edges, measure)
        eb = edges_incident_to(gb.edges, measure)
        born_edges = eb - ea
        died_edges = ea - eb

        born_by_stock: Counter = Counter()
        died_by_stock: Counter = Counter()
        for e in born_edges:
            for s in e:
                if s in measure:
                    born_by_stock[s] += 1
        for e in died_edges:
            for s in e:
                if s in measure:
                    died_by_stock[s] += 1

        n_born_ge1 = sum(1 for s in measure if born_by_stock[s] >= 1)
        share = n_born_ge1 / len(measure) if measure else 0.0
        born_shares.append(share)
        born_totals.append(len(born_edges))

        for s in sorted(measure):
            if born_by_stock[s] or died_by_stock[s]:
                event_rows.append({
                    "transition": name, "stock_code": s, "name": corp_names.get(s, ""),
                    "edge_born": born_by_stock[s], "edge_died": died_by_stock[s],
                })

        tr = {
            "transition": name, "status": "OK",
            "measure_intersection": len(measure),
            "edges_prev": len(ea), "edges_curr": len(eb),
            "edge_born_total": len(born_edges),      # 생성과 소멸을 절대 합산하지 않는다(§4.5)
            "edge_died_total": len(died_edges),
            "stocks_born_ge1": n_born_ge1,
            "born_ge1_share": round(share, 4),
            "max_rcept_dt_prev": snap_max_rcept.get(la),
            "max_rcept_dt_curr": snap_max_rcept.get(lb2),
        }
        transitions.append(tr)
        log(f"  전이 {name}: 교집합 {len(measure)}종목, born {len(born_edges)} / "
            f"died {len(died_edges)}, born≥1 비율 {share:.3f}, "
            f"최종접수일 {snap_max_rcept.get(la)}→{snap_max_rcept.get(lb2)}")

    write_csv(REPORTS_DIR / "diag_edge_events.csv", event_rows)
    v.extra["transitions"] = transitions

    n_ok_snapshots = sum(1 for s in snap_status.values() if s == "OK")
    if not born_shares:
        v.status = "UNVERIFIED"
        v.blocked_reason = (
            f"성립한 전이가 0개다. 스냅샷 성립 {n_ok_snapshots}/{TH.AD3_snapshots_required}. "
            "측정 실패이며 결과 미달(STOP)이 아니다(§11)."
        )
    else:
        srt = sorted(born_totals)
        m = len(srt)
        median_born = float(srt[m // 2]) if m % 2 else (srt[m // 2 - 1] + srt[m // 2]) / 2
        ad1 = sum(born_shares) / len(born_shares)
        v.gates = [
            Gate("AΔ-1", "분기당 edge_born ≥ 1 인 종목 비율 (전이 평균)",
                 round(ad1, 4), TH.AD1_born_ge1_share, ad1 >= TH.AD1_born_ge1_share),
            Gate("AΔ-2", "분기당 전체 edge_born 총건수 중앙값",
                 median_born, TH.AD2_born_total_median, median_born >= TH.AD2_born_total_median),
            Gate("AΔ-3", "4개 스냅샷 모두 그래프 구성 성공",
                 f"{n_ok_snapshots}/{TH.AD3_snapshots_required}", TH.AD3_snapshots_required,
                 n_ok_snapshots >= TH.AD3_snapshots_required),
        ]
        if ad1 < TH.AD1_born_ge1_share or median_born < TH.AD2_born_total_median:
            v.known_limitations.append(
                "AΔ-1 또는 AΔ-2 미달 — 분기 단위 차분이 성립하지 않는다. 연 단위 재설계 필요를 "
                "보고만 하며, 이번 단계에서 연 단위 측정을 즉흥 실행하지 않는다(§4.6)."
            )
        if stop_reason:
            # 중간 중단으로 스냅샷이 빠진 상태다. AΔ-3 미달은 '결과 미달'이 아니라 '측정 실패'다(§11).
            v.status = "UNVERIFIED"
            v.known_limitations.append(
                "실행이 중간에 중단되어 스냅샷이 불완전하다. 아래 게이트 수치는 성립한 전이에만 "
                "근거하며, 미달을 STOP 으로 읽어서는 안 된다."
            )
        else:
            v.status = v.resolve_status()

    v.known_limitations += [
        "엣지 소멸이 실제 퇴임인지 보고서 미기재인지 구분할 수 없다(§4.5). "
        "edge_died 는 '보고서상 사라짐'으로만 읽어야 한다.",
        "생성과 소멸은 절대 합산하지 않았다(§4.5).",
        "S3(2025/11011 사업보고서)는 제출기한이 2026-03-31로 분기보고서보다 지연이 3개월 길다. "
        "S2→S3, S3→S4 전이는 관측 지연이 비대칭이며 전이별 최종접수일을 각각 기록했다(§4.7).",
        "전이별 측정대상은 양 스냅샷 하위 1,000종목의 교집합이다. 유니버스 구성 변화가 "
        "엣지 생성/소멸로 위장하는 것을 막기 위한 선택이며, 교집합 크기를 함께 기록했다.",
    ]
    v.api_calls_this_date = sum(
        n for k, n in COUNTERS.by_date.items() if k.startswith("AD_")
    )
    v.cache_hit = COUNTERS.cache_hit.get("A", 0) - hit0
    v.cache_miss = COUNTERS.cache_miss.get("A", 0) - miss0
    v.runtime_sec = time.time() - t0
    return v, stop_reason


# =============================================================================
#  축 B — Google Patents (BigQuery)
# =============================================================================

BQ_TABLE = "patents-public-data.patents.publications"
BQ_RESEARCH_TABLE = "patents-public-data.google_patents_research.publications"


def _bq_int_date(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def build_assignee_query(as_of: date, years: int) -> str:
    """
    §5.2 SELECT * 금지, 파티션/필터 컬럼 필수.
    §5.3 관측가능성 필터는 publication_date, 측정 변수는 filing_date. 혼용 금지.
    """
    pub_hi = _bq_int_date(as_of)
    fil_lo = _bq_int_date(date(as_of.year - years, as_of.month, as_of.day))
    return f"""
-- 축 B: KR 출원인별 특허 집계 (관측가능성 = publication_date, 측정 = filing_date)
SELECT
  a.name                       AS assignee_name,
  COUNT(DISTINCT p.publication_number) AS n_publications,
  COUNT(DISTINCT p.family_id)          AS n_families,
  MIN(p.filing_date)                   AS filing_date_min,
  MAX(p.filing_date)                   AS filing_date_max,
  MAX(p.publication_date)              AS publication_date_max
FROM `{BQ_TABLE}` AS p,
UNNEST(p.assignee_harmonized) AS a
WHERE p.country_code = 'KR'
  AND p.publication_date > 0
  AND p.publication_date <= {pub_hi}      -- 룩어헤드 차단(§5.3)
  AND p.filing_date >= {fil_lo}           -- 측정 변수(§5.3)
  AND p.filing_date <= {pub_hi}
GROUP BY assignee_name
HAVING n_publications > 0
""".strip()


def build_citation_query(as_of: date, years: int) -> str:
    """B-3 피인용 결측률 측정용. cited_by 는 현재시점 기준이며 PIT 재구성이 아니다(한계 기록)."""
    pub_hi = _bq_int_date(as_of)
    fil_lo = _bq_int_date(date(as_of.year - years, as_of.month, as_of.day))
    return f"""
-- 축 B-3: 피인용(cited_by) 결측률
SELECT
  COUNT(*)                                            AS n_total,
  COUNTIF(r.publication_number IS NULL)               AS n_no_research_row,
  COUNTIF(r.publication_number IS NOT NULL
          AND ARRAY_LENGTH(r.cited_by) = 0)           AS n_zero_cited_by
FROM (
  SELECT p.publication_number
  FROM `{BQ_TABLE}` AS p
  WHERE p.country_code = 'KR'
    AND p.publication_date > 0
    AND p.publication_date <= {pub_hi}
    AND p.filing_date >= {fil_lo}
    AND p.filing_date <= {pub_hi}
) AS s
LEFT JOIN `{BQ_RESEARCH_TABLE}` AS r
  ON r.publication_number = s.publication_number
""".strip()


# 퍼지 매칭 정의를 코드로 고정한다. 임계를 낮춰 매칭률을 부풀리지 않는다(§5.5-3).
#   퍼지 = 접두 일치. (a) 출원인명이 종목명으로 시작하거나 (b) 종목명이 출원인명으로 시작.
# 임의 부분문자열 포함을 쓰면 '동방' 이 '동방전자'·'동방물산'·'극동방직' 에 모두 걸려
# 매칭률이 부풀려진다. 접두로 한정하고 최소 길이를 둔다.
MIN_FUZZY_LEN = 3


def match_universe_to_assignees(
    universe_names: Dict[str, str], by_norm: Dict[str, int], min_len: int = MIN_FUZZY_LEN,
) -> Dict[str, Any]:
    """§5.5 — 완전일치와 퍼지를 **분리**해서 센다. 합쳐서 보고하지 않는다."""
    sorted_keys = sorted(by_norm)

    def prefix_hit(key: str) -> bool:
        i = bisect.bisect_left(sorted_keys, key)                  # (a)
        if i < len(sorted_keys) and sorted_keys[i].startswith(key):
            return True
        for cut in range(len(key) - 1, min_len - 1, -1):          # (b)
            if key[:cut] in by_norm:
                return True
        return False

    exact = fuzzy = skipped = 0
    for _tkr, nm in universe_names.items():
        key = normalize_corp_name(nm)
        if not key:
            skipped += 1
            continue
        if key in by_norm:
            exact += 1
        elif len(key) >= min_len and prefix_hit(key):
            fuzzy += 1
    n = len(universe_names)
    return {
        "status": "OK", "universe": n, "name_unusable": skipped,
        "exact": exact, "fuzzy": fuzzy,
        "exact_rate": round(exact / n, 4) if n else 0.0,
        "any_rate": round((exact + fuzzy) / n, 4) if n else 0.0,
        "fuzzy_rule": f"접두 일치, 최소 길이 {min_len}",
    }


def run_axis_b(universe_names: Optional[Dict[str, str]], limitations: List[str]) -> AxisVerdict:
    t0 = time.time()
    v = AxisVerdict(axis="B", as_of=T_NOW.isoformat(), status="PENDING")
    pre, info = preflight_axis_b()
    v.extra["auth"] = info
    if not pre.ok:
        v.status = "BLOCKED_PREREQ"
        v.blocked_reason = pre.summary()
        v.blocked_cause_class = pre.cause_class
        v.extra["preflight_blockers"] = [{"cause_class": c, "detail": d} for c, d in pre.blockers]
        v.known_limitations.append(
            "인증/의존성 단계에서 차단되었다. §5.1에 따라 '경로 없음'·'키 형식 오류'·"
            "'프로젝트 미지정'·'권한 없음'·'결제 미설정'·'네트워크 차단'을 하나의 BLOCKED 로 "
            f"뭉치지 않고 각각 기록했다. 우선 해결 대상은 cause_class={pre.cause_class} 다."
        )
        v.runtime_sec = time.time() - t0
        for c, d in pre.blockers:
            log(f"  축 B BLOCKED_PREREQ [{c}] {d}")
        return v

    from google.cloud import bigquery
    from google.api_core import exceptions as gexc

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip() or info.get("GOOGLE_CLOUD_PROJECT")
    client = bigquery.Client(project=project)

    def dry_run(sql: str, tag: str) -> Optional[int]:
        """§5.2 — 모든 쿼리를 dry_run 으로 먼저 실행해 스캔 바이트를 로그에 출력한다."""
        cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        try:
            job = client.query(sql, job_config=cfg)
        except gexc.Forbidden as exc:
            msg = str(exc)
            cls = "AUTH_BILLING" if "billing" in msg.lower() else "AUTH_PERMISSION"
            raise RuntimeError(f"[{cls}] {msg[:500]}") from exc
        except Exception as exc:
            raise RuntimeError(f"[QUERY_ERROR] {type(exc).__name__}: {str(exc)[:500]}") from exc
        b = job.total_bytes_processed or 0
        log(f"  dry_run[{tag}] 스캔 예상 {b / 1024 ** 3:.2f} GB")
        return b

    canary_sql = f"""
-- 카나리: KR 표기 병존 확인 (로마자/한글). LIMIT 로 비용 통제.
SELECT a.name AS assignee_name, COUNT(*) AS n
FROM `{BQ_TABLE}` AS p, UNNEST(p.assignee_harmonized) AS a
WHERE p.country_code = 'KR'
  AND p.publication_date BETWEEN {_bq_int_date(date(T_NOW.year - 1, 1, 1))} AND {_bq_int_date(T_NOW)}
GROUP BY assignee_name
ORDER BY n DESC
LIMIT {TH.canary_size}
""".strip()

    try:
        # --- 카나리 (P0_CANARY_FIRST) -----------------------------------------
        b = dry_run(canary_sql, "canary")
        if b and b > TH.bq_max_scan_bytes:
            v.status = "UNVERIFIED"
            v.blocked_reason = (
                f"카나리 쿼리 스캔 예상 {b / 1024 ** 3:.1f}GB > 상한 "
                f"{TH.bq_max_scan_bytes / 1024 ** 3:.0f}GB — 실행 중단(§5.2)."
            )
            v.runtime_sec = time.time() - t0
            return v
        canary_rows = list(client.query(canary_sql).result())
        names = [r["assignee_name"] for r in canary_rows]
        has_hangul = any(re.search(r"[가-힣]", str(n) or "") for n in names)
        has_latin = any(re.search(r"[A-Za-z]", str(n) or "") for n in names)
        log(f"  카나리 출원인 상위 {len(names)}건 표본: {names[:5]}")
        log(f"  표기 병존 — 한글 {has_hangul} / 로마자 {has_latin}")
        v.extra["canary"] = {
            "sample": names[:10], "has_hangul": has_hangul, "has_latin": has_latin,
        }

        # --- 본 쿼리 ------------------------------------------------------------
        results: Dict[str, Dict[str, Any]] = {}
        for label, as_of in (("T_NOW", T_NOW), ("T_PAST", T_PAST)):
            sql = build_assignee_query(as_of, PATENT_WINDOW_YEARS)
            b = dry_run(sql, f"assignee_{label}")
            if b and b > TH.bq_max_scan_bytes:
                results[label] = {
                    "status": "ABORTED_COST",
                    "scan_bytes": b,
                    "reason": f"{b / 1024 ** 3:.1f}GB > 100GB 상한(§5.2)",
                }
                log(f"  ⚠ {label} 쿼리 중단 — {results[label]['reason']}")
                continue
            rows = list(client.query(sql).result())
            results[label] = {
                "status": "OK", "scan_bytes": b, "n_assignees": len(rows),
                "by_norm": {},
            }
            for r in rows:
                key = normalize_corp_name(str(r["assignee_name"]))
                if not key:
                    continue
                cur = results[label]["by_norm"].setdefault(key, 0)
                results[label]["by_norm"][key] = cur + int(r["n_publications"])
            log(f"  {label}: KR 출원인 {len(rows)}건 → 정규화 키 "
                f"{len(results[label]['by_norm'])}개")

        # --- 종목 매핑 (§5.5) ----------------------------------------------------
        if not universe_names:
            v.status = "UNVERIFIED"
            v.blocked_reason = (
                "유니버스 법인명을 얻지 못해 B-1/B-2/B-4 를 계산할 수 없다. "
                "축 A 의 corpCode 매핑이 선행되어야 하나, P0_INDEPENDENT_AXES 에 따라 "
                "축 A 의 '판정'에는 의존하지 않으며 명칭 사전만 공유한다."
            )
            v.runtime_sec = time.time() - t0
            return v

        def match(label: str) -> Dict[str, Any]:
            res = results.get(label, {})
            if res.get("status") != "OK":
                return {"status": res.get("status", "MISSING")}
            return match_universe_to_assignees(universe_names, res["by_norm"])

        m_now = match("T_NOW")
        m_past = match("T_PAST")
        v.extra["match"] = {"T_NOW": m_now, "T_PAST": m_past}

        # --- B-3 피인용 결측률 ---------------------------------------------------
        cite_sql = build_citation_query(T_NOW, PATENT_WINDOW_YEARS)
        b3_measured: Any = "UNVERIFIED"
        b3_pass: Optional[bool] = None
        try:
            b = dry_run(cite_sql, "citation")
            if b and b > TH.bq_max_scan_bytes:
                v.known_limitations.append(
                    f"B-3 피인용 쿼리 스캔 예상 {b / 1024 ** 3:.1f}GB 가 100GB 상한을 넘어 "
                    "실행하지 않았다(§5.2). B-3 은 UNVERIFIED 다."
                )
            else:
                row = list(client.query(cite_sql).result())[0]
                total = int(row["n_total"] or 0)
                missing = int(row["n_no_research_row"] or 0)
                b3_measured = round(missing / total, 4) if total else 1.0
                b3_pass = b3_measured <= TH.B3_citation_missing
                v.extra["citation"] = {
                    "n_total": total, "n_no_research_row": missing,
                    "n_zero_cited_by": int(row["n_zero_cited_by"] or 0),
                }
        except Exception as exc:
            v.known_limitations.append(f"B-3 피인용 측정 실패: {type(exc).__name__}: {str(exc)[:300]}")

        b1 = m_now.get("any_rate") if m_now.get("status") == "OK" else None
        b2 = None
        if m_now.get("status") == "OK" and (m_now["exact"] + m_now["fuzzy"]) > 0:
            b2 = round(m_now["exact"] / (m_now["exact"] + m_now["fuzzy"]), 4)
        b4 = m_past.get("any_rate") if m_past.get("status") == "OK" else None

        v.gates = [
            Gate("B-1", "최근 5년 KR 특허 1건 이상 보유 비율",
                 b1 if b1 is not None else "UNVERIFIED", TH.B1_patent_holder_share,
                 (b1 >= TH.B1_patent_holder_share) if b1 is not None else None),
            Gate("B-2", "출원인명 완전일치 매핑 성공률 (B-1 통과 종목 대상)",
                 b2 if b2 is not None else "UNVERIFIED", TH.B2_exact_match_rate,
                 (b2 >= TH.B2_exact_match_rate) if b2 is not None else None,
                 note="완전일치/퍼지 매칭률을 분리 보고한다(§5.5-3)"),
            Gate("B-3", "피인용 데이터 결측률", b3_measured, TH.B3_citation_missing, b3_pass),
            Gate("B-4", "T_PAST 시점에도 B-1 성립",
                 b4 if b4 is not None else "UNVERIFIED", TH.B4_patent_holder_share_past,
                 (b4 >= TH.B4_patent_holder_share_past) if b4 is not None else None),
        ]
        v.known_limitations += [
            f"특허 공개 지연 약 {PATENT_PUBLICATION_LAG_MONTHS}개월. 출원(filing_date) 후 "
            "공개(publication_date)까지의 지연을 판정표에 명시한다(§5.3/§7).",
            "관측가능성 필터는 publication_date, 측정 변수는 filing_date 로 분리했다. 혼용하지 않았다.",
            "cited_by 는 조회 시점 기준이며 as_of 시점으로 재구성한 값이 아니다. 이번 단계는 "
            "'가용성'만 측정하며, 전략 사용 시 PIT 재구성이 별도로 필요하다.",
            "청구항 수는 patents.publications 에 직접 컬럼이 없어 수집하지 않았다(결측으로 기록, 추정 금지).",
            "패밀리 규모는 조회 창(KR·기간 한정) 내 family_id 기준이므로 전세계 패밀리 규모의 하한이다.",
            "B-1/B-4 의 분모는 corpCode.xml 의 종목코드 보유 법인 전체(조회 시점 스냅샷)다. "
            "as_of 시점의 상장 유니버스와 정확히 일치하지 않으며, 그만큼 보유 비율은 하한이다.",
            "퍼지 매칭은 '접두 일치, 최소 길이 3'으로 고정했다. 임의 부분문자열 포함을 쓰면 "
            "매칭률이 부풀려지므로 채택하지 않았다. 완전일치와 퍼지는 분리 보고한다(§5.5-3).",
        ]
        v.status = finalize_status(v)

    except Exception as exc:
        msg = str(exc)
        v.status = "BLOCKED_PREREQ" if msg.startswith("[AUTH_") else "UNVERIFIED"
        v.blocked_cause_class = (
            msg.split("]")[0].lstrip("[") if msg.startswith("[") else "QUERY_ERROR"
        )
        v.blocked_reason = msg[:800]
        log(f"  ⚠ 축 B 중단 [{v.blocked_cause_class}]: {v.blocked_reason}")

    v.runtime_sec = time.time() - t0
    return v


# =============================================================================
#  축 C — 국민연금 사업장 (§6)
# =============================================================================

NPS_URL = f"https://{NPS_HOST}/B552015/NpsBplcInfoInqireService/getBassInfoSearch"


def _nps_call(params: Dict[str, Any], timeout: int = 20) -> Tuple[Optional[int], str, Optional[str]]:
    """반환: (http_status, body_text, error)"""
    if not _HAS_REQUESTS:
        return None, "", "requests 미설치"
    # Decoding 키를 코드가 인코딩한다(이중인코딩 방지).
    qs = urlencode({k: v for k, v in params.items() if k != "serviceKey"})
    url = f"{NPS_URL}?serviceKey={quote(DATA_GO_KR_KEY, safe='')}" + (f"&{qs}" if qs else "")
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code, resp.text, None
    except Exception as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


def _extract_tag(body: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", body, flags=re.S)
    if m:
        return m.group(1).strip()
    try:
        obj = json.loads(body)
    except Exception:
        return None

    def walk(o: Any) -> Optional[str]:
        if isinstance(o, dict):
            for k, val in o.items():
                if k.lower() == tag.lower():
                    return str(val)
                r = walk(val)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for it in o:
                r = walk(it)
                if r is not None:
                    return r
        return None

    return walk(obj)


def _extract_wkpl_names(body: str, limit: int = 3) -> List[str]:
    names = re.findall(r"<wkplNm>(.*?)</wkplNm>", body, flags=re.S)
    if names:
        return [n.strip() for n in names[:limit]]
    try:
        obj = json.loads(body)
    except Exception:
        return []
    out: List[str] = []

    def walk(o: Any) -> None:
        if len(out) >= limit:
            return
        if isinstance(o, dict):
            for k, val in o.items():
                if k == "wkplNm" and isinstance(val, str):
                    out.append(val.strip())
                else:
                    walk(val)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(obj)
    return out[:limit]


def run_axis_c(limitations: List[str]) -> AxisVerdict:
    t0 = time.time()
    v = AxisVerdict(axis="C", as_of=T_NOW.isoformat(), status="PENDING")

    log("")
    log("  ── 축 C 승인 상태 확인 안내 (§6.1) ────────────────────────────────")
    log("     공공데이터포털 마이페이지 > 데이터활용 > 활용신청 현황")
    log("     → '승인' 여부와 일일 트래픽 잔량을 확인한다.")
    log("     → 상태가 '신청' 이면 어떤 파라미터 조합으로도 실패한다.")
    log("  ────────────────────────────────────────────────────────────────")

    pre = preflight_axis_c()
    probes: List[Dict[str, Any]] = []

    # §6.1 프로브 4종. 순서대로, 성공하면 즉시 중단.
    probe_specs: List[Tuple[str, Dict[str, Any]]] = [
        ("1_dataCrtYm_202506", {"dataCrtYm": "202506", "numOfRows": 10, "pageNo": 1}),
        ("2_no_dataCrtYm", {"numOfRows": 10, "pageNo": 1}),
        ("3_minimal_params", {}),
        ("4_numOfRows1_pageNo1", {"numOfRows": 1, "pageNo": 1}),
    ]

    success_body: Optional[str] = None
    if not pre.ok:
        # 네트워크/키 자체가 막힌 경우에도 4개 시도를 전부 기록한다 — 사유를 원문 그대로 남긴다.
        for name, params in probe_specs:
            probes.append({
                "probe": name, "params": json.dumps(params, ensure_ascii=False),
                "http_status": "", "resultCode": "", "resultMsg": "",
                "error": "사전점검 차단으로 시도되지 않음 — " + pre.summary(),
                "cause_class": pre.cause_class,
                "body_head_400": "",
            })
        v.status = "BLOCKED_PREREQ"
        v.blocked_reason = pre.summary()
        v.blocked_cause_class = pre.cause_class
        v.extra["preflight_blockers"] = [{"cause_class": c, "detail": d} for c, d in pre.blockers]
        for c, d in pre.blockers:
            log(f"  축 C BLOCKED_PREREQ [{c}] {d}")
    else:
        for name, params in probe_specs:
            polite_sleep()
            COUNTERS.api_call("C")
            status, body, err = _nps_call(params)
            rc = _extract_tag(body, "resultCode") or _extract_tag(body, "returnReasonCode") or ""
            rm = _extract_tag(body, "resultMsg") or _extract_tag(body, "returnAuthMsg") or ""
            probes.append({
                "probe": name, "params": json.dumps(params, ensure_ascii=False),
                "http_status": status if status is not None else "",
                "resultCode": rc, "resultMsg": rm,
                "error": err or "", "cause_class": "",
                "body_head_400": (body or "")[:400].replace("\n", " "),
            })
            ok = (status == 200) and (rc in ("00", "0", "")) and ("<wkplNm>" in body or "wkplNm" in body)
            log(f"  프로브 {name}: HTTP={status} resultCode={rc!r} resultMsg={rm!r} "
                f"성공={ok}")
            if ok:
                success_body = body
                break   # 성공하면 즉시 중단(§6.1)

        if success_body is None:
            v.status = "UNVERIFIED"      # STOP 아님(§6.2)
            v.blocked_reason = (
                "§6.1 프로브 4개 시도 모두 실패. 사유는 diag_C_probes.csv 에 원문 그대로 기록했다. "
                "측정 실패이며 결과 미달(STOP)이 아니다."
            )
        else:
            samples = _extract_wkpl_names(success_body, 3)
            DIAG.check_c_samples(samples)
            DIAG.raise_if_failed()
            log(f"  축 C 첫 응답 wkplNm 표본 3건: {samples}")

            body = success_body
            has_bizno_full = bool(re.search(r"<bzowrRgstNo>\s*\d{10}\s*</bzowrRgstNo>", body))
            has_bizno_masked = bool(re.search(r"<bzowrRgstNo>[^<]*[*]", body))
            v.extra["probe_success_sample"] = samples
            v.extra["bizno_full_digits"] = has_bizno_full
            v.extra["bizno_masked"] = has_bizno_masked

            v.gates = [
                Gate("C-1", "사업자등록번호 전체 자릿수 제공 여부 (Y/N)",
                     "Y" if has_bizno_full else ("N(마스킹)" if has_bizno_masked else "N"),
                     "Y", has_bizno_full),
                Gate("C-2", "유니버스 종목 사업장 매칭 성공 비율",
                     "UNVERIFIED", TH.C2_workplace_match, None,
                     note="상호 기반 매칭. 낮게 나오는 것은 정상적인 결과이며 퍼지 임계를 낮추지 않는다(§6.3)."),
                Gate("C-3", "T_PAST 까지 월별 시계열 연속 존재",
                     "UNVERIFIED", "연속", None),
                Gate("C-4", "다사업장 법인 통합 가능 여부 (Y/N/부분)",
                     "UNVERIFIED", "Y/N/부분", None),
                Gate("C-5", f"매칭 {TH.C5_manual_sample}건 수기 검증",
                     "PENDING", f"{TH.C5_manual_sample}건 CSV", None,
                     note="reports/manual_check_C_workplace_match.csv"),
            ]
            v.status = finalize_status(v)

    write_csv(
        REPORTS_DIR / "diag_C_probes.csv", probes,
        fieldnames=["probe", "params", "http_status", "resultCode", "resultMsg",
                    "error", "cause_class", "body_head_400"],
    )
    v.extra["probes"] = probes
    v.known_limitations.append(
        "축 C 관측 지연: 해당 월 후 1~2개월 공표. 프로브 성공 시 실제 지연을 측정한다(§7)."
    )
    v.api_calls_this_date = COUNTERS.by_date.get("C", 0)
    v.runtime_sec = time.time() - t0
    return v


# =============================================================================
#  §9  —  산출물
# =============================================================================


def write_verdicts(verdicts: List[AxisVerdict], meta: Dict[str, Any]) -> None:
    if RUN_MODE != "LIVE":
        raise ContractViolation("run_mode 가 LIVE 가 아니면 판정표를 저장하지 않는다(§9.1).")

    payload = {
        "run_mode": RUN_MODE,
        "version": VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "verdicts": [v.to_dict() for v in verdicts],
    }
    (REPORTS_DIR / "phase0_verdict_v12.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows: List[Dict[str, Any]] = []
    for v in verdicts:
        if not v.gates:
            rows.append({
                "run_mode": RUN_MODE, "axis": v.axis, "as_of": v.as_of, "status": v.status,
                "gate_id": "", "criterion": "", "measured": "", "threshold": "", "pass": "",
                "blocked_cause_class": v.blocked_cause_class or "",
                "blocked_reason": v.blocked_reason or "",
                "api_calls_this_date": v.api_calls_this_date,
                "cache_hit": v.cache_hit, "cache_miss": v.cache_miss,
                "runtime_sec": round(v.runtime_sec, 1),
            })
            continue
        for g in v.gates:
            rows.append({
                "run_mode": RUN_MODE, "axis": v.axis, "as_of": v.as_of, "status": v.status,
                "gate_id": g.id, "criterion": g.criterion,
                "measured": g.measured, "threshold": g.threshold,
                "pass": {True: "PASS", False: "FAIL", None: "PENDING"}[g.passed],
                "blocked_cause_class": v.blocked_cause_class or "",
                "blocked_reason": v.blocked_reason or "",
                "api_calls_this_date": v.api_calls_this_date,
                "cache_hit": v.cache_hit, "cache_miss": v.cache_miss,
                "runtime_sec": round(v.runtime_sec, 1),
            })
    write_csv(
        REPORTS_DIR / "phase0_verdict_v12.csv", rows,
        fieldnames=["run_mode", "axis", "as_of", "status", "gate_id", "criterion",
                    "measured", "threshold", "pass", "blocked_cause_class",
                    "blocked_reason", "api_calls_this_date", "cache_hit",
                    "cache_miss", "runtime_sec"],
    )


def write_summary(verdicts: List[AxisVerdict], meta: Dict[str, Any]) -> None:
    """§9.4 — 축별 판정과 근거 수치만. 해석·전략 제안 금지."""
    L: List[str] = []
    L.append(f"# PHASE 0 판정 요약 {VERSION}")
    L.append("")
    L.append(f"- 실행 모드: {RUN_MODE}")
    L.append(f"- 전 상장사 노드 수: {DIAG.node_count if DIAG.node_count is not None else '미측정'}"
             f" ({DIAG.node_count_verdict})")
    L.append(f"- 축 C 첫 응답 wkplNm 표본 3건: {DIAG.c_wkpl_samples or '미획득'} ({DIAG.c_verdict})")
    L.append(f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}")
    L.append(f"- PROJECT_ROOT: `{PROJECT_ROOT}` (P0_RUNTIME_ROOT={CONTRACT_STATE['P0_RUNTIME_ROOT']})")
    L.append(f"- 총 API 호출: {COUNTERS.total} / 중단선 {TH.call_budget_hard_stop} "
             f"(80% 트립선 {COUNTERS.trip_at})")
    L.append(f"- 총 실행시간: {meta.get('runtime_sec', 0):.1f}s")
    L.append("")
    L.append("## 축별 판정")
    L.append("")
    L.append("| 축 | 기준일 | 상태 | 차단 유형 | 게이트 |")
    L.append("|---|---|---|---|---|")
    def gate_mark(g: Gate) -> str:
        return "PASS" if g.passed else ("FAIL" if g.passed is False else "PENDING")

    for v in verdicts:
        gs = " / ".join(f"{g.id}={gate_mark(g)}" for g in v.gates) or "—"
        L.append(f"| {v.axis} | {v.as_of} | {v.status} | {v.blocked_cause_class or '—'} | {gs} |")
    L.append("")

    for v in verdicts:
        L.append(f"### 축 {v.axis} — {v.as_of} — {v.status}")
        L.append("")
        blockers = v.extra.get("preflight_blockers") or []
        if blockers:
            L.append(f"차단 사유 {len(blockers)}건 (우선 해결: `{v.blocked_cause_class}`)")
            L.append("")
            for b in blockers:
                L.append(f"- `{b['cause_class']}` — {b['detail']}")
        elif v.blocked_reason:
            L.append(f"- 사유(`{v.blocked_cause_class or '—'}`): {v.blocked_reason}")
        if v.gates:
            L.append("")
            L.append("| 게이트 | 기준 | 측정값 | 임계 | 판정 |")
            L.append("|---|---|---|---|---|")
            for g in v.gates:
                L.append(f"| {g.id} | {g.criterion} | {g.measured} | {g.threshold} "
                         f"| {gate_mark(g)} |")
        if v.known_limitations:
            L.append("")
            L.append("**known_limitations**")
            for k in v.known_limitations:
                L.append(f"- {k}")
        L.append("")

    L.append("## 계약 상태")
    L.append("")
    L.append("`NOT_EXERCISED` = 이번 실행에서 해당 코드 경로가 돌지 않았다. PASS 가 아니다.")
    L.append("")
    L.append("| 계약 | 상태 | 내용 |")
    L.append("|---|---|---|")
    for k, desc in CONTRACTS.items():
        L.append(f"| `{k}` | {CONTRACT_STATE[k]} | {desc} |")
    L.append("")
    L.append("## 축별 관측 지연 (§7 — 기록만)")
    L.append("")
    L.append("| 축 | 실제 사건 → 관측 가능 |")
    L.append("|---|---|")
    L.append("| A | 분기보고서 45일 / 사업보고서 90일 |")
    L.append(f"| B | 출원 후 약 {PATENT_PUBLICATION_LAG_MONTHS}개월 (공개) |")
    L.append("| C | 해당 월 후 1~2개월 (공표) |")
    L.append("")
    (REPORTS_DIR / "phase0_summary_v12.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_resume_todo(verdicts: List[AxisVerdict], reason: str) -> None:
    """§4.4-3 — 중단 시 남은 작업 목록."""
    todo = {
        "reason": reason,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counters": COUNTERS.snapshot(),
        "remaining": [
            {"axis": v.axis, "as_of": v.as_of, "status": v.status,
             "blocked_reason": v.blocked_reason}
            for v in verdicts if v.status in ("UNVERIFIED", "PENDING", "BLOCKED_PREREQ")
        ],
        "note": "캐시는 (corp_code, bsns_year, reprt_code) 키로 보존된다. "
                "다음 실행은 캐시 히트로 0콜에서 이어받는다(§8.2).",
    }
    (REPORTS_DIR / "resume_todo.json").write_text(
        json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# =============================================================================
#  main
# =============================================================================


def main() -> int:
    _enforce_live_only()
    ensure_dirs()

    rule(f"PHASE 0 — 대체데이터 3축 수집 가능성 검증 {VERSION}")
    log(f"실행 모드: {RUN_MODE}")
    log(f"PROJECT_ROOT: {PROJECT_ROOT}")
    log(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")
    log(f"실행일: {date.today()}   T_NOW={T_NOW}   T_PAST={T_PAST}")
    log("")
    log("이 단계는 수집 가능성만 측정한다. 팩터·시그널·수익률 연산은 전면 금지다(P0_NO_STRATEGY).")

    # --- 계약 초기 상태 --------------------------------------------------------
    # (1) 구조적으로 보장되는 계약 — 코드 형태 자체가 근거다.
    mark_contract("P0_LIVE_ONLY", "PASS")            # SELFTEST=False + 합성 경로 부재
    mark_contract("P0_NO_STRATEGY", "PASS")          # 수익률/시그널/팩터 코드 부재
    mark_contract("P0_NO_THRESHOLD_EDIT", "PASS")    # frozen dataclass
    mark_contract("P0_RESUMABLE", "PASS")            # 캐시 키 (corp_code, bsns_year, reprt_code)
    mark_contract("P0_INDEPENDENT_AXES", "PASS")     # 축이 서로의 판정을 참조하지 않는다
    mark_contract("P0_FAIL_LOUD", "PASS")            # 보간·추정·대체값 코드 부재
    mark_contract("NO_KNOWN_DEAD_CALL", _scan_source_for_dead_call())
    mark_contract("P0_RUNTIME_ROOT", _ROOT_CONTRACT_STATE)

    # (2) 수집이 실제로 돌아야 확인되는 계약 — 돌기 전에는 PASS 로 적지 않는다.
    for _c in ("P0_PIT_STRICT", "P0_GRAPH_FULL_MEASURE_SUB",
               "P0_SNAPSHOT_DEADLINE_GUARD", "P0_CANARY_FIRST"):
        mark_contract(_c, "NOT_EXERCISED")
    if _ROOT_WARNING:
        log("")
        log(f"⚠ {_ROOT_WARNING}")

    # --- 사전점검 요약 ---------------------------------------------------------
    log("")
    rule("사전점검 (Preflight) — 원인을 구분해 보고한다", "-")
    log_key_status()
    log("")
    pre_a = preflight_axis_a()
    pre_b, _bi = preflight_axis_b()
    pre_c = preflight_axis_c()
    for nm, pr in (("축 A / A-Δ (OpenDART + KRX)", pre_a),
                   ("축 B (BigQuery)", pre_b),
                   ("축 C (공공데이터포털)", pre_c)):
        if pr.ok:
            log(f"  [OK   ] {nm}: {pr.detail}")
            continue
        log(f"  [BLOCK] {nm} — 차단 사유 {len(pr.blockers)}건 "
            f"(우선 해결: {pr.cause_class})")
        for c, d in pr.blockers:
            log(f"           · [{c}] {d}")

    limitations: List[str] = []
    verdicts: List[AxisVerdict] = []
    budget_stop_reason: Optional[str] = None
    universe_names: Optional[Dict[str, str]] = None

    # --- 축 A ------------------------------------------------------------------
    log("")
    rule("축 A — 겸직 그래프 밀도 (§3)")
    a_verdicts, a_stop = run_axis_a(limitations)
    verdicts += a_verdicts                      # 중단해도 여기까지의 판정표는 살린다(§4.4-2)
    if a_stop:
        budget_stop_reason = a_stop

    # 축 B 매핑용 법인명 사전(판정 의존 아님 — P0_INDEPENDENT_AXES)
    if pre_a.ok:
        try:
            _bs, _names, _bn = fetch_corp_codes(CircuitBreaker("A"))
            universe_names = _names
        except Exception as exc:
            log(f"  법인명 사전 확보 실패(축 B 매핑에 영향): {type(exc).__name__}: {exc}")

    # --- 축 A-Δ ----------------------------------------------------------------
    log("")
    rule("축 A-Δ — 분기별 엣지 생성/소멸 밀도 (§4)")
    if budget_stop_reason:
        verdicts.append(AxisVerdict(
            axis="A-delta", as_of=AXIS_AD_SNAPSHOTS[-1][1].isoformat(), status="UNVERIFIED",
            blocked_reason=f"선행 축에서 중단되어 착수하지 못했다: {budget_stop_reason}",
        ))
        log("  선행 중단으로 축 A-Δ 미착수 — resume_todo.json 으로 이어받는다(§4.4-3)")
    else:
        ad_verdict, ad_stop = run_axis_a_delta(limitations)
        verdicts.append(ad_verdict)
        if ad_stop:
            budget_stop_reason = ad_stop

    # --- 축 B ------------------------------------------------------------------
    log("")
    rule("축 B — Google Patents / BigQuery (§5)")
    verdicts.append(run_axis_b(universe_names, limitations))

    # --- 축 C ------------------------------------------------------------------
    log("")
    rule("축 C — 국민연금 사업장 (§6)")
    verdicts.append(run_axis_c(limitations))

    # --- §1.3 자가진단 블록 (최종) ---------------------------------------------
    log("")
    rule("§1.3 자가진단", "-")
    log(f"실행 모드: {RUN_MODE}")
    log(f"전 상장사 노드 수: {DIAG.node_count if DIAG.node_count is not None else '미측정(축 A 차단)'}"
        f"   → {DIAG.node_count_verdict}")
    log(f"축 C 첫 응답 wkplNm 표본 3건: {DIAG.c_wkpl_samples or '미획득(축 C 차단)'}"
        f"   → {DIAG.c_verdict}")
    DIAG.raise_if_failed()

    # --- 산출물 ----------------------------------------------------------------
    runtime = time.time() - _T0
    meta = {
        "runtime_sec": runtime,
        "counters": COUNTERS.snapshot(),
        "contracts": dict(CONTRACT_STATE),
        "self_diagnosis": {
            "node_count": DIAG.node_count,
            "node_count_verdict": DIAG.node_count_verdict,
            "c_wkpl_samples": DIAG.c_wkpl_samples,
            "c_verdict": DIAG.c_verdict,
        },
        "preflight": {
            key: {
                "ok": pr.ok, "primary_cause_class": pr.cause_class, "detail": pr.detail,
                "blockers": [{"cause_class": c, "detail": d} for c, d in pr.blockers],
            }
            for key, pr in (("axis_a", pre_a), ("axis_b", pre_b), ("axis_c", pre_c))
        },
        "scope_reductions": limitations,
        "budget_stop_reason": budget_stop_reason,
    }
    write_verdicts(verdicts, meta)
    write_summary(verdicts, meta)
    if budget_stop_reason or any(v.status in ("UNVERIFIED", "BLOCKED_PREREQ") for v in verdicts):
        write_resume_todo(verdicts, budget_stop_reason or "미완료 축 존재")

    log("")
    rule("최종 판정")
    for v in verdicts:
        log(f"  축 {v.axis:<8} {v.as_of}  →  {v.status}"
            + (f"  [{v.blocked_cause_class}]" if v.blocked_cause_class else ""))
    log("")
    log(f"산출물: {REPORTS_DIR}")
    for p in sorted(REPORTS_DIR.glob("*")):
        log(f"  - {p.name}  ({p.stat().st_size:,} bytes)")
    log("")
    log(f"총 실행시간 {runtime:.1f}s / 총 API 호출 {COUNTERS.total}")
    if runtime > TH.runtime_budget_sec:
        log(f"⚠ 실행시간 예산 {TH.runtime_budget_sec}s 초과 — §10 축소 순서를 적용할 것")

    flush_log()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ContractViolation as _exc:
        log("")
        log(f"❌ 계약 위반으로 중단: {_exc}")
        flush_log()
        sys.exit(2)
    except KeyboardInterrupt:
        log("사용자 중단")
        flush_log()
        sys.exit(130)
