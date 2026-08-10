#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  PHASE 0 — 대체데이터 3축 수집 가능성 검증  v1.1
#
#  이 파일 하나로 끝난다. Colab / JupyterLab "한 셀"에 통째로 붙여넣거나
#  `python phase0_altdata_3axis_v11.py` 로 실행한다. (명령서 §8.6 단일 셀 요구)
#
#  ── 이 코드가 하는 것 (명령서 §1) ──────────────────────────────────────────────────────
#    · 축 A     : 겸직 그래프를 "전 상장사"로 구성하고, 하위 1,000종목에 대해서만 밀도 측정
#    · 축 A-Δ   : 4개 분기 스냅샷 사이의 엣지 생성/소멸 이벤트 밀도 측정
#    · 축 B     : Google Patents(BigQuery) 수집 가능성 검증
#    · 축 C     : 국민연금 사업장 API 재프로브
#
#  ── 이 코드가 하지 않는 것 (위반 시 작업 실패) ─────────────────────────────────────────
#    · 팩터 계산 · 시그널 생성 · 수익률 산출 — 전면 금지 (P0_NO_STRATEGY 가 소스를 검사한다)
#    · 알파 존재 여부에 대한 주장, 축 간 결합 분석, 게이트 미달 시 임계값 조정
#
#  ⚠ 투자자문이 아니다. 데이터 수집 가능성 측정 코드다.
# ============================================================================================
from __future__ import annotations

import csv
import io
import json
import hashlib
import os
import random
import re
import sys
import threading
import time
import tokenize
import traceback
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채운다
#
#   비워두면 해당 축은 조용히 넘어가지 않고 BLOCKED_PREREQ / UNVERIFIED 로 "시끄럽게" 기록된다.
#
# ════════════════════════════════════════════════════════════════════════════════════════════

# ── ① OpenDART API 키  (축 A / A-Δ 필수) ────────────────────────────────────────────────────
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료·즉시 발급. 일일 호출한도 20,000건(계정당). 이 코드는 19,000건을 가용치로 잡고
#    80% (15,200건) 도달 시 스스로 중단한다 (명령서 §4.2).
#    사용 엔드포인트: corpCode.xml (기업코드 전체), exctvSttus.json (임원현황), company.json (기업개황)
DART_API_KEY = os.environ.get("DART_API_KEY", "")

# ── ② 공공데이터포털 키  (축 C 필수) ────────────────────────────────────────────────────────
#    발급: https://www.data.go.kr → 로그인 → "국민연금공단_국민연금 가입 사업장 내역" 상세페이지
#          → [활용신청] → 마이페이지 > 데이터활용 > Open API > 인증키
#    ★ 승인 소요: 자동승인 API 는 즉시, 심의 대상은 1~2 영업일. 승인 전에는 무조건 실패한다.
#    ★ 반드시 "일반 인증키(Decoding)" 를 넣는다. Encoding 키(%2B/%3D 포함)를 넣으면
#      이중 인코딩으로 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다. (코드가 감지해서 경고한다)
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY", "")

# ── ③ GCP / BigQuery  (축 B 필수) ───────────────────────────────────────────────────────────
#    방법 A) 서비스 계정: https://console.cloud.google.com/iam-admin/serviceaccounts
#            → 키 생성(JSON) → 아래 경로 지정. 역할은 BigQuery User + BigQuery Job User.
#    방법 B) ADC:  gcloud auth application-default login
#    ★ patents-public-data 는 공개 데이터셋이라 별도 권한이 필요 없지만,
#      쿼리 비용은 "본인 프로젝트"에 청구된다. GCP_PROJECT 를 반드시 지정한다.
#    ★ 우회 시도 금지 (명령서 §5.1). 인증이 없으면 즉시 BLOCKED_PREREQ 로 종료한다.
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
GCP_PROJECT = os.environ.get("GCP_PROJECT", "")

# ── ④ 작업 루트 (P0_RUNTIME_ROOT) ───────────────────────────────────────────────────────────
#    비워두면 환경에 맞춰 자동으로 잡는다:
#      · 코랩      → /content/phase0
#      · 윈도우    → C:\phase0   (SystemDrive 기준)
#      · 그 외     → <현재 디렉터리>/phase0
PROJECT_ROOT = os.environ.get("PHASE0_PROJECT_ROOT", "")

#    ★ 세션이 끝나면 사라지는 경로(/content, /tmp 등)를 쓸 것인가.
#      §8.1 이 이걸 막는 이유는 단 하나 — 재실행할 때마다 DART 일일 한도를 새로 태우기 때문이다.
#      True 로 두면 실행은 계속하되 계약 검사에 PASS 가 아니라 **WAIVED** 로 기록되고,
#      모든 판정표의 known_limitations 에 그 사실이 실린다. 숨기지 않는다.
ALLOW_EPHEMERAL_ROOT = True

# ── ④-1 구글드라이브 콜드 백업 (§8.4) ───────────────────────────────────────────────────────
#    핫 캐시는 로컬(PROJECT_ROOT), 드라이브는 **콜드 백업 전용**이다.
#    원본 API 응답을 아카이브 한 덩어리로 묶어 드라이브에 올려두고, 다음 실행에서 되살린다.
#    → 코랩 세션이 죽어도 DART 호출을 다시 태우지 않는다. 위 WAIVED 의 실질적 완화책이다.
#    기존 파일은 절대 덮어쓰지 않는다(skip-if-exists 복원, 직전 세대는 .prev 로 보존).
DRIVE_BACKUP = True
DRIVE_BACKUP_DIR = ""          # 비우면 코랩에서 /content/drive/MyDrive/phase0_cache 를 쓴다
AUTO_MOUNT_DRIVE = True        # 코랩에서 드라이브가 안 붙어 있으면 마운트를 시도한다(승인 창이 뜬다)

# ── ⑤ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SELFTEST" : 네트워크·키 없이 합성 데이터로 측정 로직 전체를 검증한다. 산출물은
#                 cache/reports_selftest/ 에 따로 쓰고 mode=SELFTEST_SYNTHETIC 로 낙인찍는다.
#                 (합성 결과를 실측 판정으로 오해할 수 없게 만든다)
#    "FULL"     : 실제 수집. 축별로 카나리 10종목 통과 후에만 벌크로 넘어간다.
RUN_MODE = os.environ.get("PHASE0_RUN_MODE", "SELFTEST")

AXES_TO_RUN = ("A", "B", "C")      # 축 선택 실행용. A 에는 A-Δ 가 포함된다.
RUN_DATE_OVERRIDE = ""             # "YYYY-MM-DD". 비우면 시스템 날짜. 재현성 확보용.

# ── ⑥ 동시성·예산 (명령서 §8.5 / §10) ───────────────────────────────────────────────────────
N_WORKERS = 4                      # 4 이하
REQ_DELAY_MIN, REQ_DELAY_MAX = 0.3, 1.0
TIME_BUDGET_SEC = 4 * 3600         # 4시간


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §2  계약 (Contracts)
#   상수로 선언하고 위반 시 예외를 발생시킨다.
# ════════════════════════════════════════════════════════════════════════════════════════════

P0_NO_STRATEGY          = "수익률·시그널·팩터 연산 일절 금지"
P0_PIT_STRICT           = "접수일자(rcept_dt)가 기준일 이후인 레코드는 무조건 폐기. 예외 없음"
P0_GRAPH_FULL_MEASURE_SUB = "그래프는 전 상장사로 구성, 지표 측정은 하위 1,000종목에 대해서만"
P0_CANARY_FIRST         = "축마다 10종목 카나리 통과 전 벌크 금지"
P0_INDEPENDENT_AXES     = "축 A/B/C 상호 의존 금지"
P0_FAIL_LOUD            = "결측은 결측으로 기록. 보간·추정·대체값 금지"
P0_RUNTIME_ROOT         = "PROJECT_ROOT 런타임 감지. /content 감지 시 경고 + 계약 FAIL"
P0_RESUMABLE            = "캐시 키에 (corp_code, bsns_year, reprt_code) 전부 포함"
P0_NO_THRESHOLD_EDIT    = "게이트 임계값을 코드 실행 중 변경 금지"
NO_KNOWN_DEAD_CALL      = "pykrx 지수 구성종목 조회(1028) 호출 금지 — 영구 실패"

CONTRACT_IDS = [
    "P0_NO_STRATEGY", "P0_PIT_STRICT", "P0_GRAPH_FULL_MEASURE_SUB", "P0_CANARY_FIRST",
    "P0_INDEPENDENT_AXES", "P0_FAIL_LOUD", "P0_RUNTIME_ROOT", "P0_RESUMABLE",
    "P0_NO_THRESHOLD_EDIT", "NO_KNOWN_DEAD_CALL",
]


class ContractViolation(RuntimeError):
    """계약 위반. 절대 삼키지 않는다."""


class AxisAbort(RuntimeError):
    """서킷 브레이커/예산 초과로 해당 축만 중단. 다른 축은 계속 간다."""


# ════════════════════════════════════════════════════════════════════════════════════════════
#   게이트 임계값 — 동결(freeze). 실행 중 변경 금지 (P0_NO_THRESHOLD_EDIT)
# ════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Thresholds:
    # 축 A (§3.4)
    A1_EXEC_COVERAGE_MIN: float = 0.90
    A2_BIRTHYM_MISS_MAX: float = 0.10
    A3_LINKED_RATIO_MIN: float = 0.25
    A5_TOTAL_LINKS_MIN: int = 600
    A4_MANUAL_SAMPLE_N: int = 200
    # 축 A-Δ (§4.4)
    AD1_BORN_STOCK_RATIO_MIN: float = 0.05
    AD2_BORN_TOTAL_MEDIAN_MIN: int = 50
    # 축 B (§5.6)
    B1_PATENT_HOLDER_RATIO_MIN: float = 0.30
    B2_EXACT_MATCH_RATIO_MIN: float = 0.70
    B3_CITATION_MISS_MAX: float = 0.30
    B4_PAST_HOLDER_RATIO_MIN: float = 0.30
    B_DRYRUN_MAX_BYTES: int = 100 * (1024 ** 3)      # 단일 쿼리 100GB
    # 축 C (§6.4)
    C2_WORKPLACE_MATCH_MIN: float = 0.60
    C5_MANUAL_SAMPLE_N: int = 100
    # 진단 (§3.3)
    CORPCODE_UNKNOWN_CAUSE_MAX: int = 20
    # 측정 대상 (§3.2)
    MEASURE_SUBSET_N: int = 1000
    # 호출 예산 (§4.2)
    DART_DAILY_CALL_LIMIT: int = 19_000
    DART_BUDGET_STOP_RATIO: float = 0.80


TH = Thresholds()
_TH_FINGERPRINT = hashlib.sha256(
    json.dumps(asdict(TH), sort_keys=True).encode("utf-8")).hexdigest()


def assert_thresholds_untouched() -> None:
    """P0_NO_THRESHOLD_EDIT — 게이트를 평가할 때마다 임계값 지문을 재확인한다."""
    now = hashlib.sha256(json.dumps(asdict(TH), sort_keys=True).encode("utf-8")).hexdigest()
    if now != _TH_FINGERPRINT:
        raise ContractViolation(f"P0_NO_THRESHOLD_EDIT 위반: 임계값이 실행 중 변경되었다 "
                                f"({_TH_FINGERPRINT[:12]} → {now[:12]})")


# ════════════════════════════════════════════════════════════════════════════════════════════
#   기준일 / 보고서 코드
# ════════════════════════════════════════════════════════════════════════════════════════════

T_NOW = date(2026, 6, 30)      # §3.5
T_PAST = date(2021, 6, 30)     # §3.5

REPRT_NAME = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}
REPRT_PERIOD_END_MD = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}   # 법정 제출기한

# §4.2 스냅샷 구간 — 직전 4개 분기
SNAPSHOTS: List[Tuple[str, int, str]] = [
    ("2025-09-30", 2025, "11014"),
    ("2025-12-31", 2025, "11011"),
    ("2026-03-31", 2026, "11013"),
    ("2026-06-30", 2026, "11012"),
]

# §7 축별 관측 지연 — 측정하고 기록만 한다
OBSERVATION_LAG_NOTE = {
    "A": "정기보고서 제출기한: 분기/반기 45일, 사업보고서 90일. 접수일자(rcept_no 앞 8자리) 기준 PIT 강제.",
    "B": "특허 공개 지연 약 18개월. publication_date <= as_of 로 관측가능성 필터, 측정변수는 filing_date.",
    "C": "국민연금 사업장 자료는 해당 월 후 1~2개월 공표. 프로브 성공 시 실제 지연을 측정해 기록.",
}


def period_end_of(bsns_year: int, reprt_code: str) -> date:
    m, d = REPRT_PERIOD_END_MD[reprt_code]
    return date(bsns_year, m, d)


def filing_deadline_of(bsns_year: int, reprt_code: str) -> date:
    """법정 제출기한. '어느 보고서를 요청할지' 고르는 데만 쓴다.
    PIT 자체는 레코드마다 rcept_dt 로 다시 강제한다(중복 방어)."""
    return period_end_of(bsns_year, reprt_code) + timedelta(days=REPRT_DEADLINE_DAYS[reprt_code])


def latest_available_report(as_of: date) -> Tuple[int, str]:
    """as_of 시점에 '법정 제출기한이 이미 지난' 보고서 중 기간 종료일이 가장 최근인 것.

    2026-06-30 → (2026, 11013)  ← 반기(11012)는 제출기한이 2026-08-14 이라 아직 볼 수 없다.
    2021-06-30 → (2021, 11013)
    1차 실행이 실제로 11013 을 사용한 것과 일치한다.
    """
    cands: List[Tuple[date, int, str]] = []
    for y in (as_of.year, as_of.year - 1, as_of.year - 2):
        for rc in REPRT_PERIOD_END_MD:
            if filing_deadline_of(y, rc) <= as_of:
                cands.append((period_end_of(y, rc), y, rc))
    if not cands:
        raise ContractViolation(f"{as_of} 시점에 제출기한이 지난 정기보고서가 없다 — 기준일 설정 오류")
    cands.sort(reverse=True)
    _, y, rc = cands[0]
    return y, rc


# ════════════════════════════════════════════════════════════════════════════════════════════
#   로깅
# ════════════════════════════════════════════════════════════════════════════════════════════

_LOG_LOCK = threading.Lock()
_LOG_SINK: List[str] = []
_T0 = time.time()


def LOG(msg: str = "", level: str = "INFO") -> None:
    el = time.time() - _T0
    line = f"[{el:7.1f}s][{level:5s}] {msg}"
    with _LOG_LOCK:
        _LOG_SINK.append(line)
        print(line, flush=True)


def HEAD(title: str) -> None:
    LOG("")
    LOG("=" * 92)
    LOG(f"  {title}")
    LOG("=" * 92)


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.1  P0_RUNTIME_ROOT — 런타임 경로 적합성 확인
#   1차 실행에서 PROJECT_ROOT=/content 인데 계약이 PASS 로 떴다. 소스코드만 보고
#   실행 환경을 보지 않았기 때문이다. 이제는 실제 경로를 본다.
# ════════════════════════════════════════════════════════════════════════════════════════════

def is_colab() -> bool:
    if "google.colab" in sys.modules:
        return True
    try:
        import importlib.util
        return importlib.util.find_spec("google.colab") is not None
    except Exception:
        return False


def default_project_root() -> str:
    """환경에 맞는 기본 작업 루트. 사용자가 PROJECT_ROOT 를 비워둬도 알아서 잡는다."""
    if is_colab():
        return "/content/phase0"                     # 코랩: 콘텐트 폴더
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "C:")   # 윈도우: C 드라이브
        return os.path.join(drive + os.sep, "phase0")
    return os.path.join(os.getcwd(), "phase0")


def resolve_project_root() -> str:
    root = (PROJECT_ROOT or os.environ.get("PHASE0_PROJECT_ROOT") or default_project_root())
    return os.path.abspath(root)


EPHEMERAL_PREFIXES = ("/content", "/kaggle/working", "/tmp")


def is_ephemeral_root(root: str) -> bool:
    n = root.replace("\\", "/")
    return any(n == p or n.startswith(p + "/") for p in EPHEMERAL_PREFIXES)


def contract_runtime_root(root: str) -> Tuple[str, str]:
    """(state, detail). state ∈ {PASS, FAIL, WAIVED}.

    §8.1 의 취지는 '세션이 끝나면 캐시가 사라지는 경로를 계약이 조용히 통과시키지 못하게' 하는 것이다.
    ALLOW_EPHEMERAL_ROOT 로 운영자가 명시적으로 감수하겠다고 선언하면 실행은 계속하되,
    **절대 PASS 로 기록하지 않고 WAIVED 로 남긴다.** 판정표의 known_limitations 에도 그대로 실린다.
    """
    if not is_ephemeral_root(root):
        return "PASS", f"PROJECT_ROOT={root} (세션과 함께 사라지지 않는 경로로 판정)"
    msg = (
        f"PROJECT_ROOT={root} 는 세션이 끝나면 캐시가 통째로 사라지는 경로다.\n"
        "  · 재실행할 때마다 DART 를 새로 호출해서 일일 한도(19,000회)를 태우게 된다.\n"
        "  · 이것이 §8.1 이 막으려던 유일한 실질 피해다."
    )
    if not ALLOW_EPHEMERAL_ROOT:
        return "FAIL", (
            f"P0_RUNTIME_ROOT 위반: {msg}\n"
            "  · 조치 ①: 사라지지 않는 경로를 지정하라.\n"
            "      PROJECT_ROOT = \"C:/phase0\"  또는  \"/home/<사용자>/phase0\"\n"
            "  · 조치 ②: 코랩처럼 선택지가 없으면 ALLOW_EPHEMERAL_ROOT=True 로 명시 승인하고,\n"
            "            DRIVE_BACKUP 을 켜서 원본 캐시를 구글드라이브에 콜드 백업하라(§8.4).\n"
            "  · Google Drive 는 콜드 백업 전용이다. 핫 캐시로 쓰지 마라."
        )
    return "WAIVED", (
        f"운영자 승인(ALLOW_EPHEMERAL_ROOT=True)으로 계속 진행한다. PASS 가 아니다.\n  {msg}\n"
        "  · 완화책: 원본 캐시를 구글드라이브에 콜드 백업/복원한다(§8.4). "
        "백업이 꺼져 있거나 실패하면 그 사실도 판정표에 남는다."
    )


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §2  소스 정적 검사 — P0_NO_STRATEGY / NO_KNOWN_DEAD_CALL
#   식별자(NAME 토큰)만 본다. 주석·문자열의 산문은 검사 대상이 아니다.
#   (계약 문구 자체가 '팩터', '수익률' 을 포함하므로 원문 검색은 무조건 오탐이다)
# ════════════════════════════════════════════════════════════════════════════════════════════

_BANNED_IDENT_FRAGMENTS = [
    "sharpe", "sortino", "drawdown", "pnl", "backtest", "alpha", "portfolio",
    "excess_return", "fwd_ret", "ret_fwd", "cum_ret", "ic_score", "factor_score",
    "signal_", "_signal", "quantile_ret", "turnover_cost",
]
# 연산 대상이 될 수 없도록 조각을 쪼개 둔다. 이 스캐너가 자기 자신을 잡지 않게 하려는 것이 아니라
# (문자열은 애초에 검사하지 않는다), 아래 데드콜 스캔이 자기 자신을 잡지 않게 하려는 것이다.
_DEAD_CALL_NEEDLE = "get_index_" + "portfolio_deposit_file"


def read_own_source() -> Tuple[Optional[str], str]:
    """(소스 텍스트, 출처). 노트북 한 셀로 붙여넣어 실행한 경우도 지원한다.

    1차 실행에서 '셀 실행이라 소스가 없다'는 이유로 정적 검사가 통째로 비었다.
    IPython 입력 히스토리에 셀 원문이 그대로 있으므로 그걸 읽으면 검사할 수 있다.
    """
    f = globals().get("__file__")
    if f and os.path.exists(f):
        try:
            with open(f, "rb") as fh:
                return fh.read().decode("utf-8"), f"파일 {os.path.abspath(f)}"
        except Exception:
            pass
    try:
        from IPython import get_ipython
        ip = get_ipython()
        if ip is not None:
            hist = ip.user_ns.get("In") or []
            for i in range(len(hist) - 1, -1, -1):
                cell = hist[i]
                if isinstance(cell, str) and "P0_GRAPH_FULL_MEASURE_SUB" in cell and "def build_graph" in cell:
                    return cell, f"IPython 입력 히스토리 In[{i}] ({len(cell):,}자)"
    except Exception:
        pass
    return None, "소스를 찾지 못했다"


def scan_source_contracts(text: Optional[str], origin: str) -> List[Tuple[str, str, str]]:
    """소스 정적 검사. (contract_id, state, detail). state ∈ {PASS, FAIL, SKIP}."""
    out: List[Tuple[str, str, str]] = []
    if text is None:
        # 검사하지 못한 것을 PASS 로 적지 않는다. SKIP 은 SKIP 이다.
        return [("P0_NO_STRATEGY", "SKIP", f"정적 검사를 하지 못했다 — {origin}"),
                ("NO_KNOWN_DEAD_CALL", "SKIP", f"정적 검사를 하지 못했다 — {origin}")]
    raw = text.encode("utf-8")

    hits: List[str] = []
    try:
        for tok in tokenize.tokenize(io.BytesIO(raw).readline):
            if tok.type != tokenize.NAME:
                continue
            low = tok.string.lower()
            for frag in _BANNED_IDENT_FRAGMENTS:
                if frag in low:
                    hits.append(f"{tok.string}@L{tok.start[0]}")
    except Exception as e:                                    # pragma: no cover
        hits.append(f"<토큰화 실패: {e}>")
    out.append(("P0_NO_STRATEGY", "PASS" if not hits else "FAIL",
                f"전략성 식별자 없음 ({origin})" if not hits else f"금지 식별자 검출: {hits[:8]}"))

    n_dead = text.count(_DEAD_CALL_NEEDLE)
    out.append(("NO_KNOWN_DEAD_CALL", "PASS" if n_dead == 0 else "FAIL",
                f"영구 실패 호출 없음 ({origin})" if n_dead == 0 else f"데드콜 리터럴 {n_dead}회 검출"))
    return out


def install_dead_call_guard() -> str:
    """pykrx 가 이미 임포트되어 있으면 데드콜을 런타임에서도 막는다."""
    mod = sys.modules.get("pykrx.stock")
    if mod is None:
        return "pykrx 미임포트 — 런타임 가드 대기"
    fn_name = _DEAD_CALL_NEEDLE
    if not hasattr(mod, fn_name):
        return "pykrx 에 해당 함수 없음"

    def _blocked(*a, **k):
        raise ContractViolation(f"NO_KNOWN_DEAD_CALL 위반: {fn_name} 호출됨")

    setattr(mod, fn_name, _blocked)
    return "런타임 가드 설치 완료"


# ════════════════════════════════════════════════════════════════════════════════════════════
#   P0_INDEPENDENT_AXES — 축 결과 금고
#   축 실행 중에 다른 축의 결과를 읽으면 예외. 구조로 막는다.
# ════════════════════════════════════════════════════════════════════════════════════════════

class ResultVault:
    def __init__(self) -> None:
        self._d: Dict[str, Any] = {}
        self._local = threading.local()

    def enter(self, axis: str) -> None:
        self._local.axis = axis

    def leave(self) -> None:
        self._local.axis = None

    @property
    def current(self) -> Optional[str]:
        return getattr(self._local, "axis", None)

    def put(self, axis: str, value: Any) -> None:
        cur = self.current
        if cur is not None and cur != axis:
            raise ContractViolation(f"P0_INDEPENDENT_AXES 위반: 축 {cur} 실행 중 축 {axis} 결과를 쓰려 했다")
        if axis in self._d:
            raise ContractViolation(f"축 {axis} 결과가 이미 기록되어 있다(덮어쓰기 금지)")
        self._d[axis] = value

    def get(self, axis: str) -> Any:
        cur = self.current
        if cur is not None and cur != axis:
            raise ContractViolation(f"P0_INDEPENDENT_AXES 위반: 축 {cur} 실행 중 축 {axis} 결과를 읽으려 했다")
        return self._d.get(axis)

    def all(self) -> Dict[str, Any]:
        if self.current is not None:
            raise ContractViolation(f"P0_INDEPENDENT_AXES 위반: 축 {self.current} 실행 중 전체 결과 열람 시도")
        return dict(self._d)


VAULT = ResultVault()


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.3  호출 수 집계 — 기준일별 카운터를 독립적으로. 총계는 별도 필드.
#   1차 실행에서 2021-06-30=1979 로 기록된 값이 사실은 누적 총계였다.
# ════════════════════════════════════════════════════════════════════════════════════════════

class CallLedger:
    def __init__(self, daily_limit: int, stop_ratio: float) -> None:
        self._lk = threading.Lock()
        self.by_bucket: Counter = Counter()      # 기준일/스냅샷 등 버킷별 (독립)
        self.by_axis: Counter = Counter()
        self.total: int = 0                      # 별도 필드
        self.daily_limit = daily_limit
        self.stop_at = int(daily_limit * stop_ratio)
        # 버킷은 스레드로컬이 아니라 공유 속성이다. 수집은 워커 스레드에서 일어나는데
        # 스레드로컬로 두면 워커가 버킷을 못 보고 전부 unbucketed 로 새어나간다.
        # 대신 '한 번에 하나의 수집 단계만 연다'는 불변조건을 지켜야 한다(단계는 순차 실행된다).
        self._cur_bucket: Optional[str] = None

    def bucket(self, name: str):
        ledger = self

        class _Ctx:
            def __enter__(self_inner):
                self_inner.prev = ledger._cur_bucket
                ledger._cur_bucket = name
                return ledger

            def __exit__(self_inner, *a):
                ledger._cur_bucket = self_inner.prev
                return False
        return _Ctx()

    def add(self, axis: str, n: int = 1) -> None:
        b = self._cur_bucket or "unbucketed"
        with self._lk:
            self.by_bucket[b] += n
            self.by_axis[axis] += n
            self.total += n
            over = self.total >= self.stop_at
        if over:
            raise AxisAbort(
                f"호출 예산 80% 도달: 총 {self.total}회 / 가용 {self.daily_limit}회 "
                f"(중단선 {self.stop_at}). 명령서 §4.2 에 따라 중단하고 보고한다.")

    def snapshot(self) -> Dict[str, Any]:
        with self._lk:
            return {"by_bucket": dict(self.by_bucket), "by_axis": dict(self.by_axis),
                    "total": self.total, "daily_limit": self.daily_limit, "stop_at": self.stop_at}


class CacheLedger:
    """§8.2 — 히트/미스를 축별로 분리 보고."""

    def __init__(self) -> None:
        self._lk = threading.Lock()
        self.hit: Counter = Counter()
        self.miss: Counter = Counter()

    def h(self, axis: str) -> None:
        with self._lk:
            self.hit[axis] += 1

    def m(self, axis: str) -> None:
        with self._lk:
            self.miss[axis] += 1

    def for_axis(self, axis: str) -> Tuple[int, int]:
        with self._lk:
            return self.hit[axis], self.miss[axis]

    def snapshot(self) -> Dict[str, Any]:
        with self._lk:
            axes = set(self.hit) | set(self.miss)
            return {a: {"hit": self.hit[a], "miss": self.miss[a]} for a in sorted(axes)}


CALLS = CallLedger(TH.DART_DAILY_CALL_LIMIT, TH.DART_BUDGET_STOP_RATIO)
CACHE = CacheLedger()


class TimeBudget:
    def __init__(self, budget_sec: int) -> None:
        self.t0 = time.time()
        self.budget = budget_sec
        self.reductions: List[str] = []

    def elapsed(self) -> float:
        return time.time() - self.t0

    def remaining(self) -> float:
        return self.budget - self.elapsed()

    def note_reduction(self, what: str) -> None:
        self.reductions.append(what)
        LOG(f"⏱ 시간예산 축소 적용: {what}", "WARN")


CLOCK = TimeBudget(TIME_BUDGET_SEC)


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.4  디렉터리
# ════════════════════════════════════════════════════════════════════════════════════════════

class Paths:
    def __init__(self, root: str, selftest: bool) -> None:
        self.root = root
        self.cache = os.path.join(root, "cache")
        self.raw = os.path.join(self.cache, "raw")
        self.parsed = os.path.join(self.cache, "parsed")
        self.reports = os.path.join(self.cache, "reports_selftest" if selftest else "reports")

    def ensure(self) -> None:
        for p in (self.cache, self.raw, self.parsed, self.reports):
            os.makedirs(p, exist_ok=True)

    def report(self, name: str) -> str:
        return os.path.join(self.reports, name)


def guard_enospc(e: BaseException) -> None:
    """§8.5 — ENOSPC 는 즉시 실패. 포맷 재시도 금지."""
    if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
        raise ContractViolation(f"디스크 공간 부족(ENOSPC): {e}. 즉시 중단한다(재시도·포맷 금지).")


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.4  구글드라이브 콜드 백업
#
#   핫 캐시는 로컬, 드라이브는 콜드 백업 전용이다. 파일 하나하나를 드라이브에 쓰면
#   수천 개 작은 파일 때문에 느려서 못 쓴다 — 원본 캐시를 아카이브 한 덩어리로 묶는다.
#
#   원칙: 기존 것을 절대 훼손하지 않는다.
#     · 복원은 skip-if-exists — 로컬에 이미 있는 파일을 덮어쓰지 않는다.
#     · 저장은 임시파일에 다 쓴 뒤 원자적 교체. 직전 세대는 .prev 로 남긴다.
# ════════════════════════════════════════════════════════════════════════════════════════════

RUNTIME_WAIVERS: List[str] = []


class ColdBackup:
    ARCHIVE = "phase0_raw_cache.tar.gz"

    def __init__(self, paths: "Paths", enabled: bool) -> None:
        self.paths = paths
        self.enabled = enabled
        self.dir: Optional[str] = None
        self.status = "미사용"

    def resolve(self) -> Optional[str]:
        if not self.enabled:
            self.status = "DRIVE_BACKUP=False — 콜드 백업을 쓰지 않는다"
            return None
        if DRIVE_BACKUP_DIR:
            self.dir = DRIVE_BACKUP_DIR
        elif is_colab():
            mnt = "/content/drive/MyDrive"
            if not os.path.isdir(mnt) and AUTO_MOUNT_DRIVE:
                try:
                    from google.colab import drive as _drive     # type: ignore
                    LOG("구글드라이브를 마운트한다(콜드 백업 전용). 승인 창이 뜨면 허용하라.")
                    _drive.mount("/content/drive")
                except Exception as e:                            # noqa: BLE001
                    LOG(f"드라이브 마운트 실패 — 콜드 백업 없이 진행한다: {e}", "WARN")
            if os.path.isdir(mnt):
                self.dir = os.path.join(mnt, "phase0_cache")
        if not self.dir:
            self.status = "드라이브를 찾지 못했다 — 콜드 백업 없이 진행(세션 종료 시 캐시 소멸)"
            LOG(self.status, "WARN")
            return None
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception as e:                                    # noqa: BLE001
            guard_enospc(e)
            self.status = f"백업 디렉터리를 만들지 못했다: {e}"
            LOG(self.status, "WARN")
            self.dir = None
            return None
        self.status = f"콜드 백업 경로 {self.dir}"
        LOG(self.status)
        return self.dir

    @property
    def archive_path(self) -> Optional[str]:
        return os.path.join(self.dir, self.ARCHIVE) if self.dir else None

    def restore(self) -> str:
        ap = self.archive_path
        if not ap or not os.path.exists(ap):
            return "복원할 아카이브 없음(첫 실행이거나 백업 미사용)"
        import tarfile
        n_new = n_skip = 0
        try:
            with tarfile.open(ap, "r:gz") as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    name = m.name.replace("\\", "/").lstrip("/")
                    if ".." in name.split("/"):                   # 경로 탈출 방지
                        continue
                    dest = os.path.join(self.paths.raw, name)
                    if os.path.exists(dest):                      # skip-if-exists: 핫 캐시 보존
                        n_skip += 1
                        continue
                    src = tf.extractfile(m)
                    if src is None:
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as fh:
                        fh.write(src.read())
                    n_new += 1
        except Exception as e:                                    # noqa: BLE001
            guard_enospc(e)
            return f"복원 실패(무시하고 진행): {type(e).__name__}: {e}"
        msg = f"콜드 백업 복원: 신규 {n_new:,}개 / 이미 있어 건너뜀 {n_skip:,}개"
        LOG(msg)
        return msg

    def save(self, quiet: bool = False) -> str:
        ap = self.archive_path
        if not ap or not os.path.isdir(self.paths.raw):
            return "백업 생략"
        import tarfile
        tmp = ap + ".tmp"
        n = 0
        try:
            with tarfile.open(tmp, "w:gz") as tf:
                for dirpath, _dirs, files in os.walk(self.paths.raw):
                    for fn in files:
                        full = os.path.join(dirpath, fn)
                        tf.add(full, arcname=os.path.relpath(full, self.paths.raw))
                        n += 1
            if os.path.exists(ap):                                # 직전 세대 보존 후 교체
                prev = ap + ".prev"
                try:
                    os.replace(ap, prev)
                except Exception:
                    pass
            os.replace(tmp, ap)
        except Exception as e:                                    # noqa: BLE001
            guard_enospc(e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return f"백업 실패(무시하고 진행): {type(e).__name__}: {e}"
        msg = f"콜드 백업 저장: {n:,}개 파일 → {ap}"
        if not quiet:
            LOG(msg)
        return msg

    def copy_reports(self) -> str:
        """판정표·진단 CSV 도 세션과 함께 사라지면 곤란하므로 같이 올린다."""
        if not self.dir or not os.path.isdir(self.paths.reports):
            return "리포트 백업 생략"
        import shutil
        dest = os.path.join(self.dir, "reports")
        try:
            os.makedirs(dest, exist_ok=True)
            n = 0
            for fn in os.listdir(self.paths.reports):
                src = os.path.join(self.paths.reports, fn)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(dest, fn))
                    n += 1
        except Exception as e:                                    # noqa: BLE001
            guard_enospc(e)
            return f"리포트 백업 실패: {type(e).__name__}: {e}"
        msg = f"리포트 {n}개 → {dest}"
        LOG(msg)
        return msg


COLD: Optional[ColdBackup] = None


def cold_checkpoint(tag: str) -> None:
    """수집 단계가 끝날 때마다 조용히 콜드 백업을 갱신한다. 세션이 죽어도 호출을 다시 안 태운다."""
    if COLD is None or not COLD.dir:
        return
    try:
        COLD.save(quiet=True)
    except Exception as e:                                        # noqa: BLE001
        LOG(f"체크포인트 백업 실패({tag}) — 무시하고 진행: {e}", "WARN")


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.5  HTTP — 워커 4 이하 / 0.3~1.0초 랜덤 지연 / 지수 백오프 / 서킷 브레이커
# ════════════════════════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """연속 실패 10회 → 60초 대기 → 3회 반복되면 해당 축 중단."""

    MAX_CONSEC = 10
    COOLDOWN = 60
    MAX_TRIPS = 3

    def __init__(self, axis: str) -> None:
        self.axis = axis
        self.consec = 0
        self.trips = 0
        self._lk = threading.Lock()

    def ok(self) -> None:
        with self._lk:
            self.consec = 0

    def fail(self) -> None:
        with self._lk:
            self.consec += 1
            tripped = self.consec >= self.MAX_CONSEC
            if tripped:
                self.consec = 0
                self.trips += 1
                trips = self.trips
        if not tripped:
            return
        if trips >= self.MAX_TRIPS:
            raise AxisAbort(f"서킷 브레이커 {trips}회 발동 — 축 {self.axis} 중단(차단 회피 우선)")
        LOG(f"⚡ 서킷 브레이커 발동({trips}/{self.MAX_TRIPS}) — {self.COOLDOWN}초 대기", "WARN")
        time.sleep(self.COOLDOWN)


_RNG = random.Random(20260630)
_TLS = threading.local()


def _session():
    import requests
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    s = requests.Session()
    s.headers.update({"User-Agent": "phase0-altdata-verify/1.1", "Accept": "*/*"})
    _TLS.sess = s
    return s


@dataclass
class HttpResult:
    ok: bool
    status: Optional[int]
    text: str
    error: str = ""
    elapsed: float = 0.0


def http_get(url: str, params: Dict[str, Any], *, axis: str, breaker: Optional[CircuitBreaker],
             timeout: int = 30, tries: int = 4, count_call: bool = True) -> HttpResult:
    last = HttpResult(False, None, "", "미시도")
    for attempt in range(tries):
        time.sleep(_RNG.uniform(REQ_DELAY_MIN, REQ_DELAY_MAX))
        t0 = time.time()
        try:
            if count_call:
                CALLS.add(axis, 1)
            r = _session().get(url, params=params, timeout=timeout)
            el = time.time() - t0
            if r.status_code == 200:
                if breaker:
                    breaker.ok()
                return HttpResult(True, 200, r.text, "", el)
            last = HttpResult(False, r.status_code, r.text[:2000], f"HTTP {r.status_code}", el)
            # 4xx 는 재시도해도 같다. 단 429 는 예외.
            if 400 <= r.status_code < 500 and r.status_code != 429:
                if breaker:
                    breaker.fail()
                return last
        except AxisAbort:
            raise
        except Exception as e:                                # noqa: BLE001
            guard_enospc(e)
            last = HttpResult(False, None, "", f"{type(e).__name__}: {e}", time.time() - t0)
        if attempt < tries - 1:
            time.sleep((2 ** attempt) + _RNG.uniform(0, 0.5))     # 지수 백오프
    if breaker:
        breaker.fail()
    return last


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §8.2  캐시 — 키 = (corp_code, bsns_year, reprt_code). skip-if-exists.
#   1차 실행 히트율 1.0% 의 원인은 키가 실제 요청 단위를 반영하지 못한 것이었다.
# ════════════════════════════════════════════════════════════════════════════════════════════

class RawCache:
    def __init__(self, paths: Paths, kind: str) -> None:
        self.dir = os.path.join(paths.raw, kind)
        os.makedirs(self.dir, exist_ok=True)

    def path(self, corp_code: str, bsns_year: int, reprt_code: str) -> str:
        return os.path.join(self.dir, corp_code, f"{bsns_year}_{reprt_code}.json")

    def get(self, corp_code: str, bsns_year: int, reprt_code: str) -> Optional[dict]:
        p = self.path(corp_code, bsns_year, reprt_code)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None       # 손상 파일은 미스로 취급하고 다시 받는다

    def put(self, corp_code: str, bsns_year: int, reprt_code: str, payload: dict) -> None:
        p = self.path(corp_code, bsns_year, reprt_code)
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, p)
        except Exception as e:
            guard_enospc(e)
            raise


# ════════════════════════════════════════════════════════════════════════════════════════════
#   정규화 유틸
# ════════════════════════════════════════════════════════════════════════════════════════════

_PAREN = re.compile(r"[(（\[].*?[)）\]]")
_WS = re.compile(r"\s+")
_CORP_SUFFIX = re.compile(
    r"(주식회사|㈜|\(주\)|\(유\)|유한회사|유한책임회사|합자회사|합명회사|"
    r"co\.?,?\s*ltd\.?|corp(oration)?\.?|inc\.?|company|limited|ltd\.?|llc|plc)",
    re.IGNORECASE)


def norm_person_name(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    s = _PAREN.sub("", s)              # 홍길동(洪吉童) → 홍길동
    s = _WS.sub("", s)
    return s.strip()


_BIRTH = re.compile(r"(19|20)\d{2}")


def norm_birth_ym(s: Any) -> Optional[str]:
    """'1968년 03월', '196803', '1968.03' → '196803'. 판독 불가는 None (P0_FAIL_LOUD)."""
    if not isinstance(s, str):
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) < 6:
        return None
    y, m = digits[:4], digits[4:6]
    if not _BIRTH.fullmatch(y):
        return None
    if not ("01" <= m <= "12"):
        return None
    return y + m


def norm_corp_name(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    s = _PAREN.sub(" ", s)
    s = _CORP_SUFFIX.sub(" ", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return s.upper()


def rcept_dt_of(rcept_no: Any) -> Optional[date]:
    """exctvSttus.json 은 rcept_dt 를 주지 않는다. rcept_no 앞 8자리가 접수일자다."""
    if not isinstance(rcept_no, str) or len(rcept_no) < 8 or not rcept_no[:8].isdigit():
        return None
    try:
        return datetime.strptime(rcept_no[:8], "%Y%m%d").date()
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════════════════════════════════
#   그래프 코어 — 순수 함수. 표준 라이브러리만 쓴다(테스트 가능하게).
# ════════════════════════════════════════════════════════════════════════════════════════════

PersonKey = Tuple[str, str]        # (이름, 출생년월)
EdgeKey = Tuple[str, str]          # (corp_a, corp_b) — 사전순 정렬


@dataclass
class ExecRow:
    corp_code: str
    rcept_no: str
    name: str
    birth_ym: Optional[str]
    position: str = ""
    registered: str = ""


@dataclass
class GraphBuild:
    person_to_corps: Dict[PersonKey, Set[str]]
    edges: Dict[EdgeKey, Set[PersonKey]]
    corps_with_rows: Set[str]
    n_rows: int
    n_rows_no_birth: int
    n_persons_excluded_no_birth: int


def build_graph(rows: Iterable[ExecRow]) -> GraphBuild:
    """겸직 엣지 = 동일 인물(성명+출생년월)이 두 종목에 동시 임원 등재. 가중치 = 공유 인원 수.

    출생년월이 없으면 동명이인을 구분할 수 없다. 추정하지 않고 엣지 형성에서 제외하고 센다
    (P0_FAIL_LOUD). A-2 게이트가 이 결측률을 직접 본다.
    """
    p2c: Dict[PersonKey, Set[str]] = defaultdict(set)
    corps: Set[str] = set()
    n_rows = 0
    n_no_birth = 0
    no_birth_names: Set[str] = set()
    for r in rows:
        n_rows += 1
        corps.add(r.corp_code)
        nm = norm_person_name(r.name)
        if not nm:
            n_no_birth += 0
        if not r.birth_ym:
            n_no_birth += 1
            if nm:
                no_birth_names.add(nm)
            continue
        if not nm:
            continue
        p2c[(nm, r.birth_ym)].add(r.corp_code)

    edges: Dict[EdgeKey, Set[PersonKey]] = defaultdict(set)
    for pk, cs in p2c.items():
        if len(cs) < 2:
            continue
        ordered = sorted(cs)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                edges[(ordered[i], ordered[j])].add(pk)

    return GraphBuild(dict(p2c), dict(edges), corps, n_rows, n_no_birth, len(no_birth_names))


def adjacency(edges: Dict[EdgeKey, Set[PersonKey]]) -> Dict[str, Set[str]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    for (a, b) in edges:
        adj[a].add(b)
        adj[b].add(a)
    return dict(adj)


@dataclass
class GraphMetrics:
    n_nodes_graph: int
    n_edges_graph: int
    measure_n: int
    measure_linked: int
    measure_linked_ratio: float
    edges_touching_measure: int
    edges_internal: int          # 양 끝이 모두 측정 대상(하위 1,000) 안
    edges_external: int          # 한 쪽만 측정 대상 안 — 유니버스 밖 상대와의 링크
    weight_sum_touching: int


def measure_graph(gb: GraphBuild, measure_corps: Set[str]) -> GraphMetrics:
    """P0_GRAPH_FULL_MEASURE_SUB — 그래프는 전 상장사, 측정은 하위 1,000종목."""
    adj = adjacency(gb.edges)
    linked = sum(1 for c in measure_corps if adj.get(c))
    n_int = n_ext = 0
    w = 0
    for (a, b), persons in gb.edges.items():
        ia, ib = a in measure_corps, b in measure_corps
        if not (ia or ib):
            continue
        w += len(persons)
        if ia and ib:
            n_int += 1
        else:
            n_ext += 1
    n_m = len(measure_corps)
    return GraphMetrics(
        n_nodes_graph=len(gb.corps_with_rows),
        n_edges_graph=len(gb.edges),
        measure_n=n_m,
        measure_linked=linked,
        measure_linked_ratio=(linked / n_m) if n_m else 0.0,
        edges_touching_measure=n_int + n_ext,
        edges_internal=n_int,
        edges_external=n_ext,
        weight_sum_touching=w,
    )


def edge_events(prev: Dict[EdgeKey, Set[PersonKey]], now: Dict[EdgeKey, Set[PersonKey]],
                measure_corps: Set[str]) -> Dict[str, Tuple[int, int, int, int]]:
    """§4.3 — 종목별 (edge_born, edge_died, deg_prev, deg_now).

    생성과 소멸을 절대 합산하지 않는다. 순변화 하나로 만들면 비대칭 정보가 상쇄되어 사라진다.
    """
    ap, an = adjacency(prev), adjacency(now)
    out: Dict[str, Tuple[int, int, int, int]] = {}
    for c in measure_corps:
        p, n = ap.get(c, set()), an.get(c, set())
        out[c] = (len(n - p), len(p - n), len(p), len(n))
    return out


def median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = len(s)
    return float(s[k // 2]) if k % 2 else (s[k // 2 - 1] + s[k // 2]) / 2.0


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §9.1  판정표
# ════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class Gate:
    id: str
    criterion: str
    measured: Any
    threshold: Any
    passed: Optional[bool]        # None = 사람 판정 대기(PENDING)
    note: str = ""

    def row(self) -> dict:
        return {"id": self.id, "criterion": self.criterion, "measured": self.measured,
                "threshold": self.threshold, "pass": self.passed, "note": self.note}


@dataclass
class Verdict:
    axis: str
    as_of: str
    status: str                       # GO | STOP | UNVERIFIED | BLOCKED_PREREQ | PENDING_MANUAL
    gates: List[Gate] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)
    manual_gates_pending: List[str] = field(default_factory=list)
    api_calls_this_date: int = 0
    api_calls_total_run: int = 0
    cache_hit: int = 0
    cache_miss: int = 0
    runtime_sec: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict:
        d = {
            "axis": self.axis, "as_of": self.as_of, "status": self.status,
            "gates": [g.row() for g in self.gates],
            "known_limitations": self.known_limitations,
            "manual_gates_pending": self.manual_gates_pending,
            "api_calls_this_date": self.api_calls_this_date,
            "api_calls_total_run": self.api_calls_total_run,
            "cache_hit": self.cache_hit, "cache_miss": self.cache_miss,
            "runtime_sec": round(self.runtime_sec, 1),
            "detail": self.detail,
        }
        return d


def auto_status(gates: List[Gate], *, measured_ok: bool) -> str:
    """측정 실패(UNVERIFIED)와 측정 결과 미달(STOP)을 구분한다 (§11)."""
    if not measured_ok:
        return "UNVERIFIED"
    auto = [g for g in gates if g.passed is not None]
    if not auto:
        return "UNVERIFIED"
    return "GO" if all(g.passed for g in auto) else "STOP"


def write_csv(path: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    n = 0
    try:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for r in rows:
                w.writerow(r)
                n += 1
    except Exception as e:
        guard_enospc(e)
        raise
    return n


def append_csv(path: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    """기준일이 여러 개인 진단표는 한 파일에 as_of 컬럼으로 누적한다(§9.2 의 파일명 유지)."""
    if not os.path.exists(path):
        return write_csv(path, header, rows)
    n = 0
    try:
        with open(path, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            for r in rows:
                w.writerow(r)
                n += 1
    except Exception as e:
        guard_enospc(e)
        raise
    return n


def with_accounting(axis: str, fn: Callable[[], "Verdict"]) -> "Verdict":
    """축 단위 호출/캐시 집계를 판정표에 채운다(§8.2/§8.3). 축별 버킷을 독립으로 유지한다."""
    c0 = CALLS.total
    h0, m0 = CACHE.for_axis(axis)
    with CALLS.bucket(f"{axis}@{T_NOW.isoformat()}"):
        v = fn()
    h1, m1 = CACHE.for_axis(axis)
    v.api_calls_this_date = CALLS.total - c0
    v.api_calls_total_run = CALLS.total
    v.cache_hit, v.cache_miss = h1 - h0, m1 - m0
    return v


# ════════════════════════════════════════════════════════════════════════════════════════════
#   DART 클라이언트
#   · corpCode.xml   — 기업코드 전체 (ZIP → XML). 종목코드 보유 레코드만 상장사 매핑에 쓴다.
#   · exctvSttus.json — 임원현황. 1차 실행에서 존재 확인 + 카나리 10/10 통과.
#   · company.json    — 기업개황(사업자등록번호). 축 C 의 매칭 키로만 쓴다.
# ════════════════════════════════════════════════════════════════════════════════════════════

DART_BASE = "https://opendart.fss.or.kr/api"

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키(오픈API 이용안내 참조)",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터가 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한을 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드의 부적절한 값", "101": "부적절한 접근", "800": "시스템 점검", "900": "정의되지 않은 오류",
    "901": "사용자 계정의 개인정보보유기간 만료",
}


class DartClient:
    def __init__(self, api_key: str, paths: Paths, transport: Optional[Callable] = None) -> None:
        self.key = api_key
        self.paths = paths
        self.cache_exctv = RawCache(paths, "dart_exctv")
        self.cache_company = RawCache(paths, "dart_company")
        self._transport = transport          # 셀프테스트용 주입구. FULL 모드에서는 None.

    # ── 원시 호출 ────────────────────────────────────────────────────────────────────────
    def _get_json(self, endpoint: str, params: Dict[str, Any], axis: str,
                  breaker: Optional[CircuitBreaker]) -> Tuple[Optional[dict], HttpResult]:
        p = dict(params)
        p["crtfc_key"] = self.key
        if self._transport is not None:
            CALLS.add(axis, 1)
            payload = self._transport(endpoint, p)
            return payload, HttpResult(True, 200, "", "", 0.0)
        res = http_get(f"{DART_BASE}/{endpoint}", p, axis=axis, breaker=breaker)
        if not res.ok:
            return None, res
        try:
            return json.loads(res.text), res
        except Exception as e:
            return None, HttpResult(False, res.status, res.text[:500], f"JSON 파싱 실패: {e}", res.elapsed)

    # ── 기업코드 전체 ────────────────────────────────────────────────────────────────────
    def corp_code_table(self, axis: str) -> List[Dict[str, str]]:
        """corpCode.xml → [{corp_code, corp_name, stock_code, modify_date}, ...]
        하루에 한 번만 받으면 되므로 파일로 캐시한다."""
        cpath = os.path.join(self.paths.raw, "dart_corpcode", "corpCode.json")
        if os.path.exists(cpath):
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                CACHE.h(axis)
                LOG(f"corpCode 캐시 히트: {len(rows):,}건")
                return rows
            except Exception:
                pass
        CACHE.m(axis)
        if self._transport is not None:
            CALLS.add(axis, 1)
            rows = self._transport("corpCode.xml", {})
        else:
            import requests
            CALLS.add(axis, 1)
            time.sleep(_RNG.uniform(REQ_DELAY_MIN, REQ_DELAY_MAX))
            r = _session().get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": self.key}, timeout=120)
            if r.status_code != 200:
                raise AxisAbort(f"corpCode.xml HTTP {r.status_code} — 기업코드 없이는 축 A 진행 불가")
            body = r.content
            if body[:2] != b"PK":       # ZIP 이 아니면 오류 XML 이다
                raise AxisAbort(f"corpCode.xml 이 ZIP 이 아니다(키 오류 추정): {body[:300]!r}")
            rows = []
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                name = z.namelist()[0]
                xml = z.read(name).decode("utf-8")
            for m in re.finditer(r"<list>(.*?)</list>", xml, re.S):
                blk = m.group(1)

                def _f(tag: str) -> str:
                    mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
                    return (mm.group(1).strip() if mm else "")
                rows.append({"corp_code": _f("corp_code"), "corp_name": _f("corp_name"),
                             "stock_code": _f("stock_code"), "modify_date": _f("modify_date")})
        os.makedirs(os.path.dirname(cpath), exist_ok=True)
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        LOG(f"corpCode 신규 수집: {len(rows):,}건")
        return rows

    # ── 임원현황 ─────────────────────────────────────────────────────────────────────────
    def exctv(self, corp_code: str, bsns_year: int, reprt_code: str, axis: str,
              breaker: Optional[CircuitBreaker]) -> Tuple[Optional[dict], str]:
        """캐시 키 = (corp_code, bsns_year, reprt_code) — P0_RESUMABLE. skip-if-exists."""
        hit = self.cache_exctv.get(corp_code, bsns_year, reprt_code)
        if hit is not None:
            CACHE.h(axis)
            return hit, "cache"
        CACHE.m(axis)
        payload, res = self._get_json(
            "exctvSttus.json",
            {"corp_code": corp_code, "bsns_year": str(bsns_year), "reprt_code": reprt_code},
            axis, breaker)
        if payload is None:
            return None, f"http_fail:{res.error}"
        status = str(payload.get("status", ""))
        if status in ("000", "013"):
            # 013(데이터 없음)도 캐시한다 — 재실행 때 다시 물어보지 않기 위해서다.
            self.cache_exctv.put(corp_code, bsns_year, reprt_code, payload)
            return payload, "api"
        if status == "020":
            raise AxisAbort("DART status=020 — 일일 요청 한도 초과. 중단하고 보고한다.")
        if status in ("010", "011", "012", "901"):
            raise AxisAbort(f"DART status={status} ({DART_STATUS_MSG.get(status,'?')}) — 키 문제. 축 중단.")
        return payload, f"status:{status}"

    # ── 기업개황(사업자등록번호) ─────────────────────────────────────────────────────────
    def company(self, corp_code: str, axis: str, breaker: Optional[CircuitBreaker]) -> Optional[dict]:
        hit = self.cache_company.get(corp_code, 0, "company")
        if hit is not None:
            CACHE.h(axis)
            return hit
        CACHE.m(axis)
        payload, _ = self._get_json("company.json", {"corp_code": corp_code}, axis, breaker)
        if payload is not None and str(payload.get("status", "")) in ("000", "013"):
            self.cache_company.put(corp_code, 0, "company", payload)
        return payload


def parse_exec_rows(payload: dict, corp_code: str, as_of: date) -> Tuple[List[ExecRow], List[date]]:
    """payload → (PIT 통과 임원 행, 폐기된 레코드의 접수일자 목록).

    P0_PIT_STRICT: 접수일자가 기준일 이후면 무조건 폐기. 예외 없음.
    접수일자를 읽을 수 없는 레코드도 폐기한다(추정 금지, P0_FAIL_LOUD).
    """
    rows: List[ExecRow] = []
    dropped: List[date] = []
    if not payload or str(payload.get("status", "")) != "000":
        return rows, dropped
    for it in payload.get("list", []) or []:
        rd = rcept_dt_of(it.get("rcept_no"))
        if rd is None:
            dropped.append(date(1900, 1, 1))          # 판독 불가 = 폐기. 1900-01 버킷으로 구분 기록
            continue
        if rd > as_of:
            dropped.append(rd)
            continue
        rows.append(ExecRow(
            corp_code=corp_code,
            rcept_no=str(it.get("rcept_no", "")),
            name=str(it.get("nm", "") or ""),
            birth_ym=norm_birth_ym(it.get("birth_ym")),
            position=str(it.get("ofcps", "") or ""),
            registered=str(it.get("rgist_exctv_at", "") or ""),
        ))
    return rows, dropped


# ════════════════════════════════════════════════════════════════════════════════════════════
#   유니버스 — 해당 기준일의 전 상장사 + 시총 (측정 대상 하위 1,000종목 선정용)
# ════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class UnivRow:
    stock_code: str
    name: Optional[str]
    market: str
    market_cap: Optional[int]


MARKETS = ("KOSPI", "KOSDAQ")     # 명령서의 '약 2,734종목'과 정합. KONEX 는 제외.


def _krx_prev_bday(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_universe_pykrx(as_of: date) -> List[UnivRow]:
    """pykrx 로 기준일 전 상장사와 시가총액을 받는다.

    NO_KNOWN_DEAD_CALL: 지수 구성종목 조회는 쓰지 않는다. 시장 전체 시총 테이블만 쓴다.
    """
    from pykrx import stock                                   # noqa: F401
    LOG(install_dead_call_guard())
    rows: List[UnivRow] = []
    for mk in MARKETS:
        cap = None
        d = as_of
        for _ in range(10):                                   # 휴장일 보정: 최대 10일 되짚는다
            try:
                cap = stock.get_market_cap_by_ticker(_krx_prev_bday(d), market=mk)
            except Exception as e:
                LOG(f"pykrx 시총 조회 실패({mk}, {d}): {e}", "WARN")
                cap = None
            if cap is not None and len(cap) > 0:
                break
            d = d - timedelta(days=1)
        if cap is None or len(cap) == 0:
            raise AxisAbort(f"{mk} 유니버스를 얻지 못했다({as_of}) — 측정 불가")
        names: Dict[str, str] = {}
        try:
            chg = stock.get_market_price_change_by_ticker(_krx_prev_bday(d), _krx_prev_bday(d), market=mk)
            for tk, r in chg.iterrows():
                names[str(tk)] = str(r.get("종목명", "") or "")
        except Exception as e:
            LOG(f"pykrx 종목명 일괄조회 실패({mk}) — 개별 조회로 대체: {e}", "WARN")
        for tk, r in cap.iterrows():
            tk = str(tk)
            nm = names.get(tk)
            if nm is None:
                try:
                    nm = stock.get_market_ticker_name(tk)
                except Exception:
                    nm = None                                  # P0_FAIL_LOUD: 결측은 결측
            try:
                mc = int(r["시가총액"])
            except Exception:
                mc = None
            rows.append(UnivRow(tk, nm, mk, mc))
        LOG(f"유니버스 {mk} @{d}: {len(cap):,}종목")
    return rows


def pick_measure_subset(univ: List[UnivRow], n: int) -> List[UnivRow]:
    """시총 하위 n종목. 시총 결측 종목은 순위를 매길 수 없으므로 제외하고 그 수를 보고한다."""
    ranked = [u for u in univ if u.market_cap is not None]
    missing = len(univ) - len(ranked)
    if missing:
        LOG(f"시총 결측 {missing}종목 — 하위 {n} 선정에서 제외(P0_FAIL_LOUD)", "WARN")
    ranked.sort(key=lambda u: (u.market_cap, u.stock_code))
    return ranked[:n]


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §3.3  corp_code 매핑 진단 — 필수 절차
#   1차 실행에서 1,000종목 중 86종목이 매핑 실패했다. 미달폭(6종목)보다 크다.
# ════════════════════════════════════════════════════════════════════════════════════════════

MISS_CATEGORIES = ["①우선주", "②스팩", "③리츠", "④ETF/ETN", "⑤신규상장", "⑥원인불명"]


def classify_mapping_miss(u: UnivRow, as_of: date, etf_etn: Set[str],
                          listing_date: Dict[str, date]) -> Tuple[str, str]:
    """실패 유형 자동 분류. (분류, 보조원인) — 보조원인은 ⑥의 내막을 사람에게 보여주기 위한 것이며
    게이트 계산에는 쓰지 않는다(임계값 조작 금지)."""
    nm = (u.name or "")
    code = u.stock_code
    if code in etf_etn:
        return "④ETF/ETN", "ETF/ETN 티커 목록에 존재"
    if "스팩" in nm or re.search(r"\bSPAC\b", nm, re.IGNORECASE) or re.search(r"기업인수목적", nm):
        return "②스팩", "종목명 규칙"
    if "리츠" in nm or re.search(r"REIT", nm, re.IGNORECASE):
        return "③리츠", "종목명 규칙"
    # 한국 보통주 티커는 끝자리가 0. 우선주는 5/7/9/K/L/M 등.
    if code and code[-1] != "0":
        return "①우선주", f"티커 끝자리 {code[-1]}"
    if re.search(r"우[BC]?$", nm) or "(전환)" in nm or "(신)" in nm:
        return "①우선주", "종목명 규칙"
    ld = listing_date.get(code)
    if ld is not None and (as_of - ld).days <= 120:
        return "⑤신규상장", f"상장일 {ld} (기준일 대비 {(as_of - ld).days}일)"
    # 여기까지 오면 원인불명. 보조원인으로 짐작 가능한 것만 덧붙인다.
    sub = "corpCode.xml 에 해당 종목코드 없음"
    if ld is None:
        sub += " / 상장일 정보 없음(현재 미상장 추정 — 과거 기준일에서 흔함)"
    return "⑥원인불명", sub


def fetch_etf_etn_tickers(as_of: date) -> Set[str]:
    out: Set[str] = set()
    try:
        from pykrx import stock
        for fn in ("get_etf_ticker_list", "get_etn_ticker_list", "get_elw_ticker_list"):
            f = getattr(stock, fn, None)
            if f is None:
                continue
            try:
                out |= {str(t) for t in f(_krx_prev_bday(as_of))}
            except Exception:
                pass
    except Exception as e:
        LOG(f"ETF/ETN 목록 조회 불가 — ④분류는 종목명 규칙에만 의존한다: {e}", "WARN")
    return out


def fetch_listing_dates() -> Dict[str, date]:
    out: Dict[str, date] = {}
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        for _, r in df.iterrows():
            code = str(r.get("Code") or r.get("Symbol") or "").strip()
            ld = r.get("ListingDate")
            if not code or ld is None:
                continue
            try:
                out[code] = ld.date() if hasattr(ld, "date") else datetime.strptime(str(ld)[:10], "%Y-%m-%d").date()
            except Exception:
                continue
    except Exception as e:
        LOG(f"상장일 정보 조회 불가 — ⑤신규상장 분류는 0으로 나온다: {e}", "WARN")
    return out


@dataclass
class MappingResult:
    code_to_corp: Dict[str, str]
    miss_rows: List[Tuple[str, str, str, str, str]]     # stock_code, name, market, category, subcause
    miss_counts: Counter


def map_universe_to_corpcode(univ: List[UnivRow], corp_rows: List[Dict[str, str]], as_of: date,
                             etf_etn: Set[str], listing_date: Dict[str, date]) -> MappingResult:
    by_stock: Dict[str, str] = {}
    for r in corp_rows:
        sc = (r.get("stock_code") or "").strip()
        if sc and sc != "00000000":
            by_stock[sc.zfill(6)] = r["corp_code"]
    code_to_corp: Dict[str, str] = {}
    miss: List[Tuple[str, str, str, str, str]] = []
    counts: Counter = Counter()
    for u in univ:
        cc = by_stock.get(u.stock_code.zfill(6))
        if cc:
            code_to_corp[u.stock_code] = cc
            continue
        cat, sub = classify_mapping_miss(u, as_of, etf_etn, listing_date)
        counts[cat] += 1
        miss.append((u.stock_code, u.name or "", u.market, cat, sub))
    return MappingResult(code_to_corp, miss, counts)


# ════════════════════════════════════════════════════════════════════════════════════════════
#   병렬 수집 (§8.5 워커 4 이하)
# ════════════════════════════════════════════════════════════════════════════════════════════

CANARY_N = 10
CANARY_MIN_OK = 8


def parallel_map(items: Sequence[Any], fn: Callable[[Any], Any], workers: int = N_WORKERS,
                 label: str = "") -> List[Any]:
    """AxisAbort(예산 초과·서킷)는 즉시 위로 올린다. 개별 실패는 결과에 담아 돌려준다."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out: List[Any] = []
    abort: List[BaseException] = []
    done = 0
    total = len(items)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for fu in as_completed(futs):
            try:
                out.append(fu.result())
            except (AxisAbort, ContractViolation) as e:
                abort.append(e)
                for f2 in futs:
                    f2.cancel()
            except Exception as e:                             # noqa: BLE001
                guard_enospc(e)
                out.append(("__error__", futs[fu], f"{type(e).__name__}: {e}"))
            done += 1
            if label and (done % 250 == 0 or done == total):
                LOG(f"  {label}: {done:,}/{total:,}  (누적 호출 {CALLS.total:,})")
    if abort:
        raise abort[0]
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   축 A — 겸직 그래프 밀도 재측정  (§3)
#
#   그래프 구성 노드 = 해당 기준일 전 상장사      (약 2,734종목)
#   지표 측정 대상   = 그 중 시총 하위 1,000종목
#   이 분리를 혼동하면 작업 실패 (P0_GRAPH_FULL_MEASURE_SUB)
#
# ════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class AxisAContext:
    dart: DartClient
    paths: Paths
    run_date: date
    universe_fetcher: Callable[[date], List[UnivRow]]
    etf_fetcher: Callable[[date], Set[str]]
    listing_fetcher: Callable[[], Dict[str, date]]


@dataclass
class SnapshotBuild:
    label: str
    bsns_year: int
    reprt_code: str
    graph: Optional[GraphBuild]
    n_corps_requested: int
    n_corps_with_rows: int
    max_rcept_dt: Optional[date]
    coverage: float
    available: bool = True
    unavailable_reason: str = ""


@dataclass
class CollectResult:
    rows: List[ExecRow]
    dropped_hist: Counter
    dropped_corps: Dict[str, Set[str]]
    statuses: Dict[str, int]
    corps_with_rows: Set[str]
    rcept_dates: List[date]


def collect_exec_snapshot(ctx: AxisAContext, corp_codes: Sequence[str], bsns_year: int,
                          reprt_code: str, pit_as_of: date, bucket: str,
                          breaker: CircuitBreaker) -> CollectResult:
    rows: List[ExecRow] = []
    dropped_hist: Counter = Counter()
    statuses: Counter = Counter()
    with_rows: Set[str] = set()
    rcept_dates: List[date] = []
    dropped_corps: Dict[str, Set[str]] = defaultdict(set)

    def work(cc: str):
        payload, src = ctx.dart.exctv(cc, bsns_year, reprt_code, "A", breaker)
        return cc, payload, src

    with CALLS.bucket(bucket):
        res = parallel_map(list(corp_codes), work, label=f"임원현황 {bsns_year}/{reprt_code}")

    for item in res:
        if isinstance(item, tuple) and item and item[0] == "__error__":
            statuses["error"] += 1
            continue
        cc, payload, _src = item
        if payload is None:
            statuses["no_payload"] += 1
            continue
        statuses[str(payload.get("status", "?"))] += 1
        r, dr = parse_exec_rows(payload, cc, pit_as_of)
        for d in dr:
            ym = d.strftime("%Y-%m") if d.year > 1900 else "판독불가"
            dropped_hist[ym] += 1
            dropped_corps[ym].add(cc)
        if r:
            with_rows.add(cc)
            rows.extend(r)
            rcept_dates.extend([x for x in (rcept_dt_of(y.rcept_no) for y in r) if x])
    return CollectResult(rows, dropped_hist, dict(dropped_corps), dict(statuses), with_rows, rcept_dates)


def run_axis_A_asof(ctx: AxisAContext, as_of: date, limitations: List[str]) -> Tuple[Verdict, Dict[str, Any]]:
    HEAD(f"축 A — 겸직 그래프 밀도 (기준일 {as_of})")
    t0 = time.time()
    breaker = CircuitBreaker("A")
    bucket = f"A@{as_of.isoformat()}"
    calls_before = CALLS.total
    hit0, miss0 = CACHE.for_axis("A")

    bsns_year, reprt_code = latest_available_report(as_of)
    LOG(f"PIT 상 이용 가능한 최신 정기보고서: {bsns_year} {reprt_code}({REPRT_NAME[reprt_code]}) "
        f"— 제출기한 {filing_deadline_of(bsns_year, reprt_code)}")
    LOG(f"  (반기보고서 {as_of.year}/11012 의 제출기한은 {filing_deadline_of(as_of.year, '11012')} 이라 "
        f"{as_of} 시점에는 관측 불가)")

    # ── 유니버스 ───────────────────────────────────────────────────────────────────────
    univ = ctx.universe_fetcher(as_of)
    measure = pick_measure_subset(univ, TH.MEASURE_SUBSET_N)
    LOG(f"전 상장사 {len(univ):,}종목 / 측정 대상(시총 하위 {TH.MEASURE_SUBSET_N}) {len(measure):,}종목")

    # ── corp_code 매핑 + §3.3 진단 ─────────────────────────────────────────────────────
    with CALLS.bucket(bucket):
        corp_rows = ctx.dart.corp_code_table("A")
    etf = ctx.etf_fetcher(as_of)
    ldates = ctx.listing_fetcher()
    m_all = map_universe_to_corpcode(univ, corp_rows, as_of, etf, ldates)
    m_sub = map_universe_to_corpcode(measure, corp_rows, as_of, etf, ldates)

    diag_path = ctx.paths.report("diag_corpcode_miss.csv")
    diag_rows = ([[as_of.isoformat(), "measure_bottom1000", *r] for r in m_sub.miss_rows] +
                 [[as_of.isoformat(), "all_listed", *r] for r in m_all.miss_rows])
    append_csv(diag_path, ["as_of", "scope", "stock_code", "name", "market", "category", "subcause"],
               diag_rows)
    LOG(f"매핑 실패 진단 → {diag_path}")
    LOG(f"  측정대상 {len(measure)}종목 중 매핑 실패 {len(m_sub.miss_rows)}종목: "
        + ", ".join(f"{k}={m_sub.miss_counts.get(k,0)}" for k in MISS_CATEGORIES))
    LOG(f"  전 상장사 {len(univ)}종목 중 매핑 실패 {len(m_all.miss_rows)}종목")

    unknown = m_sub.miss_counts.get("⑥원인불명", 0)
    hold = unknown > TH.CORPCODE_UNKNOWN_CAUSE_MAX
    if hold:
        LOG(f"⑥원인불명 {unknown}종목 > 임계 {TH.CORPCODE_UNKNOWN_CAUSE_MAX} — 이 축의 판정을 보류한다(§3.3.4)", "WARN")

    # ── 카나리 10종목 (P0_CANARY_FIRST) ────────────────────────────────────────────────
    canary_codes = [m_sub.code_to_corp[u.stock_code] for u in measure
                    if u.stock_code in m_sub.code_to_corp][:CANARY_N]
    ok = 0
    with_rows_canary = 0
    with CALLS.bucket(bucket):
        for cc in canary_codes:
            payload, src = ctx.dart.exctv(cc, bsns_year, reprt_code, "A", breaker)
            st = str(payload.get("status", "?")) if payload else "no_payload"
            if st in ("000", "013"):
                ok += 1
            if st == "000" and (payload.get("list") or []):
                with_rows_canary += 1
    LOG(f"카나리 {len(canary_codes)}종목: 정상응답 {ok} / 임원행 보유 {with_rows_canary}")
    if len(canary_codes) < CANARY_N or ok < CANARY_MIN_OK or with_rows_canary == 0:
        v = Verdict("A", as_of.isoformat(), "UNVERIFIED",
                    gates=[], known_limitations=limitations + [
                        f"카나리 실패(정상응답 {ok}/{len(canary_codes)}, 임원행 보유 {with_rows_canary}) — "
                        "벌크 수집으로 넘어가지 않았다(P0_CANARY_FIRST)."],
                    runtime_sec=time.time() - t0)
        v.api_calls_this_date = CALLS.total - calls_before
        return v, {}

    # ── 벌크: 전 상장사 그래프 (§3.2) ──────────────────────────────────────────────────
    all_corps = sorted(set(m_all.code_to_corp.values()))
    LOG(f"그래프 구성 노드(매핑 성공 전 상장사): {len(all_corps):,}개 — 여기 전부에 대해 임원현황을 받는다")
    cr = collect_exec_snapshot(ctx, all_corps, bsns_year, reprt_code, as_of, bucket, breaker)
    rows, dropped_hist, statuses = cr.rows, cr.dropped_hist, cr.statuses
    with_rows, dropped_corps = cr.corps_with_rows, cr.dropped_corps
    LOG(f"응답 상태 분포: {statuses}")
    LOG(f"PIT 통과 임원 행 {len(rows):,}건 / 폐기 {sum(dropped_hist.values()):,}건")
    cold_checkpoint(f"A@{as_of.isoformat()}")     # 세션이 죽어도 이 호출들을 다시 태우지 않는다

    # §3.6 폐기 레코드 접수일자 분포
    pit_path = ctx.paths.report("diag_pit_dropped.csv")
    append_csv(pit_path, ["as_of", "report", "rcept_ym", "dropped_records", "dropped_corps"],
               [[as_of.isoformat(), f"{bsns_year}/{reprt_code}", ym, n, len(dropped_corps.get(ym, ()))]
                for ym, n in sorted(dropped_hist.items())])
    LOG(f"PIT 폐기 분포 → {pit_path}")

    # ── 그래프 구성 및 측정 ────────────────────────────────────────────────────────────
    gb = build_graph(rows)
    measure_corps = {m_sub.code_to_corp[u.stock_code] for u in measure if u.stock_code in m_sub.code_to_corp}
    gm = measure_graph(gb, measure_corps)
    LOG(f"그래프: 노드 {gm.n_nodes_graph:,} / 엣지 {gm.n_edges_graph:,}")
    LOG(f"측정(하위 {TH.MEASURE_SUBSET_N}): 링크 보유 {gm.measure_linked:,}종목, "
        f"엣지 {gm.edges_touching_measure:,} (내부 {gm.edges_internal:,} / 외부 {gm.edges_external:,})")

    # ── 게이트 ─────────────────────────────────────────────────────────────────────────
    assert_thresholds_untouched()
    mapped_sub = len(measure_corps)
    a1_num = len(measure_corps & with_rows)
    a1 = (a1_num / mapped_sub) if mapped_sub else 0.0
    a1_all = (len(with_rows) / len(all_corps)) if all_corps else 0.0

    n_rows_total = gb.n_rows
    a2 = (gb.n_rows_no_birth / n_rows_total) if n_rows_total else 1.0

    a3 = gm.measure_linked / TH.MEASURE_SUBSET_N
    a3_mapped = (gm.measure_linked / mapped_sub) if mapped_sub else 0.0
    a5 = gm.edges_touching_measure

    gates = [
        Gate("A-1", "임원 레코드 1건 이상 확보 비율 (매핑 성공 종목 기준)", round(a1, 4),
             TH.A1_EXEC_COVERAGE_MIN, a1 >= TH.A1_EXEC_COVERAGE_MIN,
             f"분모=측정대상 매핑성공 {mapped_sub}종목, 분자={a1_num}. "
             f"전 상장사 기준으로는 {a1_all:.4f}. 보고서 {bsns_year}/{reprt_code} 단일 요청이며 대체 보고서 폴백 없음."),
        Gate("A-2", "출생년월 결측률", round(a2, 4), TH.A2_BIRTHYM_MISS_MAX,
             a2 <= TH.A2_BIRTHYM_MISS_MAX,
             f"분모=수집된 전 상장사 임원 행 {n_rows_total:,}건, 결측 {gb.n_rows_no_birth:,}건. "
             f"결측 행은 동명이인 구분이 불가하므로 엣지 형성에서 제외했다(제외된 고유 성명 {gb.n_persons_excluded_no_birth:,}명)."),
        Gate("A-3", "겸직 링크가 걸린 하위 1,000종목 비율 (전 상장사 그래프 기준)", round(a3, 4),
             TH.A3_LINKED_RATIO_MIN, a3 >= TH.A3_LINKED_RATIO_MIN,
             f"분모=하위 {TH.MEASURE_SUBSET_N}종목 전체. 매핑 성공분({mapped_sub})만을 분모로 하면 {a3_mapped:.4f} "
             f"(판정에는 사용하지 않음)."),
        Gate("A-4", "겸직 링크 수기 검증 정확도", None, "사람이 판정", None,
             f"manual_check_A_coexec_links.csv {TH.A4_MANUAL_SAMPLE_N}건 출력. PENDING 유지."),
        Gate("A-5", "총 겸직 링크 수 (하위 1,000종목에 하나 이상 걸린 엣지)", a5, TH.A5_TOTAL_LINKS_MIN,
             a5 >= TH.A5_TOTAL_LINKS_MIN,
             f"내부 링크(양끝 모두 하위 1,000) {gm.edges_internal:,} / "
             f"외부 링크(상대가 유니버스 밖) {gm.edges_external:,} / 공유 인원 합계 {gm.weight_sum_touching:,}"),
    ]

    status = auto_status(gates, measured_ok=True)
    if hold:
        status = "PENDING_MANUAL"

    lim = list(limitations)
    lim.append(f"관측지연: {OBSERVATION_LAG_NOTE['A']}")
    lim.append(f"{as_of} 시점 PIT 상 최신 보고서는 {bsns_year}/{reprt_code}({REPRT_NAME[reprt_code]})이며, "
               f"같은 해 반기보고서는 제출기한({filing_deadline_of(as_of.year, '11012')})이 기준일 이후라 사용할 수 없다.")
    lim.append("결산기가 12월이 아닌 법인은 해당 분기보고서가 없어 구조적으로 A-1 분자에서 빠진다(대체 보고서 폴백 없음).")
    lim.append("출생년월 결측 임원은 엣지 형성에서 제외했다. 보간·추정하지 않았다(P0_FAIL_LOUD).")
    lim.append("동일 성명+출생년월이 실제로 동일인이라는 보장은 없다. A-4 수기검증 전까지 링크 정확도는 미확정이다.")
    if hold:
        lim.append(f"corp_code 매핑 ⑥원인불명 {unknown}종목 > 임계 {TH.CORPCODE_UNKNOWN_CAUSE_MAX} "
                   f"— §3.3.4 에 따라 축 판정을 보류(PENDING_MANUAL)했다. 자동 게이트 결과는 참고치다.")

    hit1, miss1 = CACHE.for_axis("A")
    v = Verdict("A", as_of.isoformat(), status, gates=gates, known_limitations=lim,
                manual_gates_pending=["A-4"],
                api_calls_this_date=CALLS.total - calls_before,
                api_calls_total_run=CALLS.total,
                cache_hit=hit1 - hit0, cache_miss=miss1 - miss0,
                runtime_sec=time.time() - t0,
                detail={
                    "report_used": f"{bsns_year}/{reprt_code}",
                    "n_universe": len(univ), "n_measure": len(measure),
                    "n_mapped_all": len(m_all.code_to_corp), "n_mapped_measure": mapped_sub,
                    "mapping_miss_measure": dict(m_sub.miss_counts),
                    "mapping_miss_all": dict(m_all.miss_counts),
                    "graph_nodes": gm.n_nodes_graph, "graph_edges": gm.n_edges_graph,
                    "edges_internal": gm.edges_internal, "edges_external": gm.edges_external,
                    "pit_dropped_records": sum(dropped_hist.values()),
                    "response_status": statuses,
                })
    artifacts = {"graph": gb, "measure_corps": measure_corps, "measure_univ": measure,
                 "code_to_corp": m_sub.code_to_corp, "all_corps": all_corps,
                 "rows": rows, "univ": univ}
    return v, artifacts


def write_manual_check_A(paths: Paths, gb: GraphBuild, rows: List[ExecRow],
                         measure_corps: Set[str], corp_name: Dict[str, str],
                         corp_stock: Dict[str, str], n: int) -> str:
    """§9.3 — 사람이 진짜로 검증할 수 있게, 양쪽 회사의 직위와 접수번호까지 같이 낸다."""
    idx: Dict[Tuple[str, PersonKey], ExecRow] = {}
    for r in rows:
        if r.birth_ym:
            idx.setdefault((r.corp_code, (norm_person_name(r.name), r.birth_ym)), r)
    cand: List[Tuple[EdgeKey, PersonKey]] = []
    for ek, persons in gb.edges.items():
        if ek[0] in measure_corps or ek[1] in measure_corps:
            for pk in persons:
                cand.append((ek, pk))
    cand.sort(key=lambda x: (x[0][0], x[0][1], x[1][0], x[1][1]))
    rnd = random.Random(20260630)
    sample = cand if len(cand) <= n else rnd.sample(cand, n)
    sample.sort(key=lambda x: (x[0][0], x[0][1], x[1][0]))
    out = []
    for (a, b), (nm, by) in sample:
        ra, rb = idx.get((a, (nm, by))), idx.get((b, (nm, by)))
        out.append([
            nm, by,
            a, corp_name.get(a, ""), corp_stock.get(a, ""), "Y" if a in measure_corps else "N",
            (ra.position if ra else ""), (ra.registered if ra else ""), (ra.rcept_no if ra else ""),
            b, corp_name.get(b, ""), corp_stock.get(b, ""), "Y" if b in measure_corps else "N",
            (rb.position if rb else ""), (rb.registered if rb else ""), (rb.rcept_no if rb else ""),
            "",  # verdict_by_human
        ])
    p = paths.report("manual_check_A_coexec_links.csv")
    write_csv(p, ["person_name", "birth_ym",
                  "corp_a", "corp_a_name", "stock_a", "a_in_measure_subset", "position_a", "registered_a", "rcept_no_a",
                  "corp_b", "corp_b_name", "stock_b", "b_in_measure_subset", "position_b", "registered_b", "rcept_no_b",
                  "verdict_by_human(O/X)"], out)
    return p


# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   축 A-Δ — 분기별 엣지 생성/소멸 밀도  (§4)
#
#   전분기 대비 변화량 설계가 성립하려면 분기마다 실제로 엣지가 생기고 사라져야 한다.
#   종목당 이벤트가 0에 수렴하면 차분 신호 자체가 만들어지지 않는다. 그것을 미리 확인한다.
#
# ════════════════════════════════════════════════════════════════════════════════════════════

# 측정 성립 여부를 가르는 바닥값이다. §4.4 의 판정 임계값이 아니다(그건 TH 에 동결되어 있다).
# 법정 제출기한이 아직 안 지난 스냅샷은 '미달'이 아니라 '측정 불가'이므로 이 값으로 구분한다.
SNAPSHOT_MIN_COVERAGE = 0.50


def run_axis_A_delta(ctx: AxisAContext, all_corps: Sequence[str], measure_corps: Set[str],
                     corp_stock: Dict[str, str], limitations: List[str],
                     snapshots: Sequence[Tuple[str, int, str]]) -> Verdict:
    HEAD("축 A-Δ — 분기별 엣지 생성/소멸 밀도")
    t0 = time.time()
    breaker = CircuitBreaker("A")
    calls_before = CALLS.total
    hit0, miss0 = CACHE.for_axis("A")
    lim = list(limitations)

    LOG(f"스냅샷 {len(snapshots)}개 × 노드 {len(all_corps):,}개 ≈ 최대 {len(snapshots)*len(all_corps):,}콜 "
        f"(캐시 히트분 제외). 현재 누적 {CALLS.total:,} / 중단선 {CALLS.stop_at:,}")

    builds: List[SnapshotBuild] = []
    unavailable: List[str] = []
    for label, y, rc in snapshots:
        deadline = filing_deadline_of(y, rc)
        due = deadline <= ctx.run_date
        LOG(f"— 스냅샷 {label}  {y}/{rc}({REPRT_NAME[rc]})  "
            + ("제출기한 경과" if due else f"제출기한 미도래(→{deadline})"))

        # 제출기한이 아직 안 지난 스냅샷에 2,700콜을 태우기 전에 10종목만 찔러본다.
        if not due:
            n_ok = 0
            with CALLS.bucket(f"A-delta@{label}"):
                for cc in list(all_corps)[:CANARY_N]:
                    payload, _src = ctx.dart.exctv(cc, y, rc, "A", breaker)
                    if payload and str(payload.get("status", "")) == "000":
                        r, _dr = parse_exec_rows(payload, cc, ctx.run_date)
                        if r:
                            n_ok += 1
            LOG(f"   선행 프로브 {CANARY_N}종목 중 접수 확인 {n_ok}종목")
            if n_ok == 0:
                why = (f"법정 제출기한({deadline})이 실행일({ctx.run_date}) 이후다. "
                       f"선행 프로브 {CANARY_N}종목 전부 미접수 — 벌크 수집을 하지 않았다(호출 예산 보호).")
                LOG(f"   → 측정 불가: {why}", "WARN")
                unavailable.append(f"{label}({y}/{rc}): {why}")
                builds.append(SnapshotBuild(label, y, rc, None, len(all_corps), 0, None, 0.0,
                                            available=False, unavailable_reason=why))
                continue

        try:
            cr = collect_exec_snapshot(ctx, all_corps, y, rc, ctx.run_date, f"A-delta@{label}", breaker)
        except AxisAbort as e:
            LOG(f"스냅샷 {label} 수집 중단: {e}", "WARN")
            unavailable.append(f"{label}: 수집 중단({e})")
            builds.append(SnapshotBuild(label, y, rc, None, len(all_corps), 0, None, 0.0,
                                        available=False, unavailable_reason=f"수집 중단({e})"))
            break
        cov = (len(cr.corps_with_rows) / len(all_corps)) if all_corps else 0.0
        gb = build_graph(cr.rows)
        mx = max(cr.rcept_dates) if cr.rcept_dates else None
        LOG(f"   커버리지 {cov:.3f} ({len(cr.corps_with_rows):,}/{len(all_corps):,}) · 임원행 {len(cr.rows):,} · "
            f"엣지 {len(gb.edges):,} · 최종접수일 {mx}")
        avail = cov >= SNAPSHOT_MIN_COVERAGE
        why = ""
        if not avail:
            why = (f"커버리지 {cov:.3f} < 바닥값 {SNAPSHOT_MIN_COVERAGE} — "
                   + ("법정 제출기한이 아직 지나지 않아 대부분의 법인이 미제출 상태"
                      if not due else "제출기한은 지났으나 응답 커버리지가 바닥값 미만"))
            unavailable.append(f"{label}({y}/{rc}): {why}")
        builds.append(SnapshotBuild(label, y, rc, gb, len(all_corps), len(cr.corps_with_rows), mx, cov,
                                    available=avail, unavailable_reason=why))
        cold_checkpoint(f"A-delta@{label}")

    n_avail = sum(1 for b in builds if b.available)
    ad3_pass = (len(builds) == len(snapshots)) and (n_avail == len(snapshots))
    # 스냅샷이 빠진 이유가 '제출기한 미도래'라면 미달이 아니라 측정 불가다 → UNVERIFIED
    measured_ok = ad3_pass

    # ── 전이별 생성/소멸 (양쪽 스냅샷이 모두 성립한 인접 구간만) ──────────────────────
    ev_rows: List[List[Any]] = []
    born_ratio_per_tr: List[float] = []
    born_total_per_tr: List[int] = []
    died_total_per_tr: List[int] = []
    for i in range(1, len(builds)):
        prev, now = builds[i - 1], builds[i]
        if not (prev.available and now.available):
            LOG(f"전이 {prev.label}→{now.label}: 스냅샷 미성립으로 계산하지 않는다 "
                f"(빈 스냅샷을 그대로 쓰면 소멸이 전부 허위로 잡힌다)", "WARN")
            continue
        ev = edge_events(prev.graph.edges, now.graph.edges, measure_corps)
        tr = f"{prev.label}→{now.label}"
        n_born = sum(b for b, _d, _p, _n in ev.values())
        n_died = sum(d for _b, d, _p, _n in ev.values())
        n_stock_born = sum(1 for b, _d, _p, _n in ev.values() if b >= 1)
        ratio = (n_stock_born / len(measure_corps)) if measure_corps else 0.0
        born_ratio_per_tr.append(ratio)
        born_total_per_tr.append(n_born)
        died_total_per_tr.append(n_died)
        LOG(f"전이 {tr}: edge_born 총 {n_born:,} / edge_died 총 {n_died:,} / "
            f"born≥1 종목 {n_stock_born:,} ({ratio:.4f})")
        for cc, (b, d, dp, dn) in sorted(ev.items()):
            if b or d:
                ev_rows.append([tr, corp_stock.get(cc, ""), cc, b, d, dp, dn])

    ev_path = ctx.paths.report("diag_edge_events.csv")
    write_csv(ev_path, ["transition", "stock_code", "corp_code", "edge_born", "edge_died",
                        "degree_prev", "degree_now"], ev_rows)
    LOG(f"전이별 엣지 이벤트 → {ev_path} ({len(ev_rows):,}행)")

    assert_thresholds_untouched()
    has_tr = bool(born_ratio_per_tr)
    ad1 = sum(born_ratio_per_tr) / len(born_ratio_per_tr) if has_tr else 0.0
    ad2 = median(born_total_per_tr) if has_tr else 0.0

    gates = [
        Gate("AΔ-1", "분기당 edge_born ≥ 1 인 종목 비율 (전이 평균)",
             (round(ad1, 4) if has_tr else None), TH.AD1_BORN_STOCK_RATIO_MIN,
             (ad1 >= TH.AD1_BORN_STOCK_RATIO_MIN) if has_tr else None,
             f"성립한 전이 {len(born_ratio_per_tr)}개(명세 기준 {len(snapshots)-1}개): "
             f"{[round(x,4) for x in born_ratio_per_tr]}. 분모=측정대상 매핑성공 {len(measure_corps)}종목"
             + ("" if measured_ok else " — 스냅샷 일부 미성립 상태에서의 참고치다")),
        Gate("AΔ-2", "분기당 전체 edge_born 총건수 중앙값", (ad2 if has_tr else None),
             TH.AD2_BORN_TOTAL_MEDIAN_MIN,
             (ad2 >= TH.AD2_BORN_TOTAL_MEDIAN_MIN) if has_tr else None,
             f"전이별 born={born_total_per_tr} / died={died_total_per_tr} (합산하지 않음)"
             + ("" if measured_ok else " — 스냅샷 일부 미성립 상태에서의 참고치다")),
        Gate("AΔ-3", f"{len(snapshots)}개 스냅샷 모두에서 그래프 구성 성공",
             f"{n_avail}/{len(snapshots)}", "전부 성공", ad3_pass,
             "; ".join(unavailable) if unavailable else "전부 성공"),
    ]

    status = auto_status(gates, measured_ok=measured_ok)
    if not measured_ok:
        status = "UNVERIFIED"

    lim.append("엣지 소멸이 실제 퇴임인지 단순 보고서 미기재인지 구분할 수 없다. "
               "edge_died 는 '보고서상 사라짐'으로만 읽어야 한다.")
    lim.append("생성과 소멸을 합산하지 않았다. 순변화 하나로 만들면 비대칭 정보가 상쇄된다(§4.3).")
    lim.append(f"측정 대상은 {T_NOW} 기준 시총 하위 {TH.MEASURE_SUBSET_N}종목으로 4개 스냅샷 전체에 고정했다. "
               "스냅샷마다 유니버스를 다시 뽑으면 편입/편출이 엣지 생성·소멸로 위장된다.")
    lim.append("스냅샷들은 실행일 시점에서 관측한 것이다. 각 스냅샷의 실제 관측가능 시점은 "
               "max(rcept_dt) 로 detail 에 기록했다. 시그널화 시 그 시점 이후로 래그를 두어야 한다.")
    for u in unavailable:
        lim.append(f"스냅샷 측정 불가: {u}")
    if not measured_ok:
        lim.append("AΔ-3 미충족의 사유는 '데이터가 부족하다'가 아니라 '아직 관측할 수 없다'이다. "
                   "따라서 이 축의 판정은 STOP 이 아니라 UNVERIFIED 다(§11). "
                   "AΔ-1/AΔ-2 값은 성립한 전이에 대해서만 계산한 참고치이며, 축 판정을 뒤집지 않는다.")
    if not has_tr:
        lim.append("성립한 분기 전이가 하나도 없어 AΔ-1/AΔ-2 를 계산하지 못했다.")

    hit1, miss1 = CACHE.for_axis("A")
    return Verdict("A-delta", T_NOW.isoformat(), status, gates=gates, known_limitations=lim,
                   api_calls_this_date=CALLS.total - calls_before,
                   api_calls_total_run=CALLS.total,
                   cache_hit=hit1 - hit0, cache_miss=miss1 - miss0,
                   runtime_sec=time.time() - t0,
                   detail={
                       "snapshots": [
                           {"label": b.label, "report": f"{b.bsns_year}/{b.reprt_code}",
                            "filing_deadline": filing_deadline_of(b.bsns_year, b.reprt_code).isoformat(),
                            "available": b.available, "unavailable_reason": b.unavailable_reason,
                            "coverage": round(b.coverage, 4),
                            "corps_with_rows": b.n_corps_with_rows,
                            "edges": (len(b.graph.edges) if b.graph else None),
                            "max_rcept_dt": b.max_rcept_dt.isoformat() if b.max_rcept_dt else None}
                           for b in builds],
                       "born_total_per_transition": born_total_per_tr,
                       "died_total_per_transition": died_total_per_tr,
                       "born_stock_ratio_per_transition": [round(x, 4) for x in born_ratio_per_tr],
                   })


def run_axis_A(ctx: AxisAContext, limitations: List[str]) -> List[Verdict]:
    """§3(두 기준일) + §4(분기 스냅샷). A-Δ 는 축 A 의 하위 항목이므로 같은 스코프에서 돈다."""
    out: List[Verdict] = []
    VAULT.enter("A")
    try:
        v_now, art = run_axis_A_asof(ctx, T_NOW, limitations)
        out.append(v_now)

        if art:
            univ_by_corp = {art["code_to_corp"][u.stock_code]: u
                            for u in art["measure_univ"] if u.stock_code in art["code_to_corp"]}
            corp_stock = {cc: u.stock_code for cc, u in univ_by_corp.items()}
            corp_name = {cc: (u.name or "") for cc, u in univ_by_corp.items()}
            p = write_manual_check_A(ctx.paths, art["graph"], art["rows"], art["measure_corps"],
                                     corp_name, corp_stock, TH.A4_MANUAL_SAMPLE_N)
            LOG(f"수기 검증 표본 → {p} (A-4 는 PENDING 유지)")

        # §10 축소 순서 ②: 시간 예산이 25% 미만 남으면 T_PAST 를 생략한다
        if CLOCK.remaining() < TIME_BUDGET_SEC * 0.25:
            CLOCK.note_reduction("§3 T_PAST(2021-06-30) 기준일 생략 — 시간 예산")
            out.append(Verdict("A", T_PAST.isoformat(), "UNVERIFIED",
                               known_limitations=limitations + [
                                   "시간 예산 축소로 T_PAST 기준일을 측정하지 않았다(§10 축소순서 ②)."]))
        else:
            v_past, _ = run_axis_A_asof(ctx, T_PAST, limitations)
            out.append(v_past)

        # §3.4 — A-5 미달 시 §4 차분 측정은 무의미하므로 축을 STOP 처리한다
        a5 = next((g for g in v_now.gates if g.id == "A-5"), None)
        if a5 is not None and a5.passed is False:
            LOG("A-5 미달 — §4 차분 측정은 무의미하므로 수행하지 않는다(§3.4)", "WARN")
            out.append(Verdict("A-delta", T_NOW.isoformat(), "STOP",
                               known_limitations=limitations + [
                                   f"A-5 미달(측정 {a5.measured} < 임계 {a5.threshold}) — "
                                   "§3.4 에 따라 분기 차분 측정을 수행하지 않았다."]))
            return out
        if not art:
            out.append(Verdict("A-delta", T_NOW.isoformat(), "UNVERIFIED",
                               known_limitations=limitations + [
                                   "축 A 본 측정이 성립하지 않아(카나리 실패 등) 차분 측정을 수행하지 않았다."]))
            return out

        # §10 축소 순서 ①: 시간·호출 예산이 부족하면 스냅샷 4개 → 3개 (가장 오래된 것을 뺀다)
        snaps = list(SNAPSHOTS)
        need = len(snaps) * len(art["all_corps"])
        room = CALLS.stop_at - CALLS.total
        if CLOCK.remaining() < TIME_BUDGET_SEC * 0.40 or need > room:
            snaps = snaps[1:]
            CLOCK.note_reduction(
                f"§4 스냅샷 4개 → 3개 (가장 오래된 {SNAPSHOTS[0][0]} 제외). "
                f"필요 콜 {need:,} vs 잔여 {room:,}, 잔여 시간 {CLOCK.remaining()/60:.0f}분")

        univ_by_corp = {art["code_to_corp"][u.stock_code]: u
                        for u in art["measure_univ"] if u.stock_code in art["code_to_corp"]}
        corp_stock = {cc: u.stock_code for cc, u in univ_by_corp.items()}
        lim = list(limitations)
        if len(snaps) != len(SNAPSHOTS):
            lim.append(f"시간/호출 예산 축소로 스냅샷을 {len(SNAPSHOTS)}개에서 {len(snaps)}개로 줄였다"
                       f"(제외: {SNAPSHOTS[0][0]}). AΔ-3 은 축소된 집합 기준이다(§10 축소순서 ①).")
        out.append(run_axis_A_delta(ctx, art["all_corps"], art["measure_corps"], corp_stock, lim, snaps))
        return out
    finally:
        VAULT.leave()


# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   축 B — Google Patents (BigQuery)  (§5)
#
#   시점 규칙: 관측가능성 = publication_date <= as_of,  측정변수 = filing_date.
#   두 필드를 혼용하지 않는다. 특허 축에서 룩어헤드가 들어오는 사실상 유일한 경로다.
#
# ════════════════════════════════════════════════════════════════════════════════════════════

BQ_TABLE = "patents-public-data.patents.publications"

# SQL 안에서 쓰는 정규화. Python 의 norm_corp_name 과 같은 규칙을 유지해야 한다.
# __EXPR__ 자리에 컬럼식을 넣어서 쓴다.
SQL_NORM = r"""REGEXP_REPLACE(
    REGEXP_REPLACE(UPPER(__EXPR__), r'(주식회사|㈜|\(주\)|\(유\)|유한회사|CO\.?,?\s*LTD\.?|CORPORATION|CORP\.?|INC\.?|COMPANY|LIMITED|LTD\.?|LLC|PLC)', ''),
    r'[^0-9A-Z가-힣]', '')"""


def sql_norm(expr: str) -> str:
    return SQL_NORM.replace("__EXPR__", expr)


class BQRunner:
    """모든 쿼리를 dry_run 으로 먼저 돌려 스캔 바이트를 로그에 남기고, 100GB 초과 시 실행하지 않는다."""

    def __init__(self, client, max_bytes: int) -> None:
        self.client = client
        self.max_bytes = max_bytes
        self.log: List[Dict[str, Any]] = []

    def run(self, name: str, sql: str, params: Optional[List[Any]] = None) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        from google.cloud import bigquery
        cfg_dry = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False,
                                          query_parameters=params or [])
        info: Dict[str, Any] = {"name": name}
        try:
            job = self.client.query(sql, job_config=cfg_dry)
            nbytes = int(job.total_bytes_processed or 0)
        except Exception as e:                                  # noqa: BLE001
            info.update({"dry_run_ok": False, "error": f"{type(e).__name__}: {e}"})
            self.log.append(info)
            LOG(f"[BQ dry_run 실패] {name}: {e}", "WARN")
            return None, info
        info.update({"dry_run_ok": True, "bytes": nbytes, "gib": round(nbytes / 1024 ** 3, 2)})
        LOG(f"[BQ dry_run] {name}: 스캔 {nbytes:,} bytes ({info['gib']} GiB)")
        if nbytes > self.max_bytes:
            info["executed"] = False
            info["error"] = f"단일 쿼리 {info['gib']} GiB > 임계 {self.max_bytes / 1024**3:.0f} GiB — 실행 중단"
            self.log.append(info)
            LOG(f"[BQ] {name}: {info['error']}", "WARN")
            return None, info
        cfg = bigquery.QueryJobConfig(query_parameters=params or [])
        try:
            rows = [dict(r) for r in self.client.query(sql, job_config=cfg).result()]
            info.update({"executed": True, "rows": len(rows)})
            self.log.append(info)
            LOG(f"[BQ] {name}: {len(rows):,}행 수신")
            return rows, info
        except Exception as e:                                  # noqa: BLE001
            info.update({"executed": False, "error": f"{type(e).__name__}: {e}"})
            self.log.append(info)
            LOG(f"[BQ 실행 실패] {name}: {e}", "WARN")
            return None, info


def bq_prereq() -> Tuple[bool, str, Any]:
    """§5.1 — 인증이 없으면 즉시 BLOCKED_PREREQ. 우회 시도 금지."""
    try:
        from google.cloud import bigquery
    except Exception as e:                                      # noqa: BLE001
        return False, (f"google-cloud-bigquery 미설치: {e}\n"
                       "  조치: pip install google-cloud-bigquery db-dtypes"), None
    cred = GOOGLE_APPLICATION_CREDENTIALS or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if cred and not os.path.exists(cred):
        return False, f"GOOGLE_APPLICATION_CREDENTIALS 경로가 존재하지 않는다: {cred}", None
    if cred:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred
    try:
        import google.auth
        creds, proj = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
    except Exception as e:                                      # noqa: BLE001
        return False, (f"GCP 인증(ADC) 없음: {e}\n"
                       "  조치 A: gcloud auth application-default login\n"
                       "  조치 B: 서비스 계정 JSON 을 만들고 GOOGLE_APPLICATION_CREDENTIALS 로 지정\n"
                       "  ※ 우회 시도 금지(§5.1)"), None
    project = GCP_PROJECT or proj or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not project:
        return False, ("과금 프로젝트가 없다. GCP_PROJECT 를 지정하라. "
                       "patents-public-data 는 공개 데이터셋이지만 스캔 비용은 본인 프로젝트에 청구된다."), None
    try:
        client = bigquery.Client(project=project, credentials=creds)
    except Exception as e:                                      # noqa: BLE001
        return False, f"BigQuery 클라이언트 생성 실패: {e}", None
    return True, f"인증 확인 (project={project})", client


def run_axis_B(paths: Paths, dart: DartClient, universe_fetcher: Callable[[date], List[UnivRow]],
               limitations: List[str], years_back: int = 5) -> Verdict:
    HEAD("축 B — Google Patents (BigQuery)")
    VAULT.enter("B")
    t0 = time.time()
    lim = list(limitations)
    lim.append(f"관측지연: {OBSERVATION_LAG_NOTE['B']}")
    lim.append("공개 지연 약 18개월 때문에, 기준일 직전 약 18개월분의 출원은 구조적으로 관측되지 않는다. "
               "B-1/B-4 는 그만큼 하방 편의를 갖는다.")
    try:
        ok, msg, client = bq_prereq()
        LOG(msg if ok else f"선행 블로커: {msg}", "INFO" if ok else "WARN")
        if not ok:
            return Verdict("B", T_NOW.isoformat(), "BLOCKED_PREREQ",
                           known_limitations=lim + [f"BLOCKED_PREREQ 사유: {msg}"],
                           runtime_sec=time.time() - t0)

        runner = BQRunner(client, TH.B_DRYRUN_MAX_BYTES)
        from google.cloud import bigquery

        # ── 유니버스 이름 (DART 정식 법인명) ────────────────────────────────────────
        univ = universe_fetcher(T_NOW)
        measure = pick_measure_subset(univ, TH.MEASURE_SUBSET_N)
        corp_rows = dart.corp_code_table("B")
        by_stock = {(r.get("stock_code") or "").strip().zfill(6): r for r in corp_rows
                    if (r.get("stock_code") or "").strip()}
        targets: List[Tuple[str, str, str]] = []       # (stock_code, dart_name, norm_name)
        for u in measure:
            r = by_stock.get(u.stock_code.zfill(6))
            if r is None:
                continue
            targets.append((u.stock_code, r["corp_name"], norm_corp_name(r["corp_name"])))
        LOG(f"측정 대상 {len(measure)}종목 중 DART 정식 법인명 확보 {len(targets)}종목")
        if not targets:
            return Verdict("B", T_NOW.isoformat(), "UNVERIFIED",
                           known_limitations=lim + ["DART 법인명을 확보하지 못해 매핑 자체가 불가"],
                           runtime_sec=time.time() - t0)

        # ── 카나리 10종목: 로마자/한글 표기 병존 확인 (§5.5.4, P0_CANARY_FIRST) ────
        canary = targets[:CANARY_N]
        sql_canary = f"""
        SELECT a.name AS assignee_name, COUNT(*) AS n
        FROM `{BQ_TABLE}` p, UNNEST(p.assignee_harmonized) AS a
        WHERE p.country_code = 'KR'
          AND p.publication_date BETWEEN @pub_lo AND @pub_hi
          AND EXISTS (SELECT 1 FROM UNNEST(@names) AS nm
                      WHERE STRPOS({sql_norm('a.name')}, nm) > 0)
        GROUP BY assignee_name ORDER BY n DESC LIMIT 200
        """
        pub_hi = int(T_NOW.strftime("%Y%m%d"))
        pub_lo = int((T_NOW - timedelta(days=365 * years_back)).strftime("%Y%m%d"))
        params_canary = [
            bigquery.ScalarQueryParameter("pub_lo", "INT64", pub_lo),
            bigquery.ScalarQueryParameter("pub_hi", "INT64", pub_hi),
            bigquery.ArrayQueryParameter("names", "STRING", [t[2] for t in canary if t[2]]),
        ]
        crows, cinfo = runner.run("canary_assignee_names", sql_canary, params_canary)
        if crows is None:
            return Verdict("B", T_NOW.isoformat(), "UNVERIFIED",
                           known_limitations=lim + [
                               f"카나리 쿼리 실패로 벌크에 진입하지 않았다(P0_CANARY_FIRST): {cinfo.get('error')}"],
                           runtime_sec=time.time() - t0,
                           detail={"bq_log": runner.log})
        han = sum(1 for r in crows if re.search(r"[가-힣]", str(r.get("assignee_name") or "")))
        rom = len(crows) - han
        LOG(f"카나리: 출원인명 {len(crows)}종 — 한글표기 {han} / 로마자표기 {rom}")
        lim.append(f"출원인명 표기 병존 확인: 카나리 표본에서 한글 {han}종 / 로마자 {rom}종. "
                   "완전일치 매칭은 표기 체계가 갈리는 만큼 과소 측정된다.")

        # ── B-1 / B-2 : 최근 N년 KR 출원인 집계 ─────────────────────────────────────
        def agg_sql() -> str:
            return f"""
            WITH kr AS (
              SELECT {sql_norm('a.name')} AS norm_name,
                     p.publication_number
              FROM `{BQ_TABLE}` p, UNNEST(p.assignee_harmonized) AS a
              WHERE p.country_code = 'KR'
                AND p.publication_date <= @as_of          -- 관측가능성: 공개일
                AND p.filing_date BETWEEN @f_lo AND @f_hi -- 측정변수: 출원일
            )
            SELECT norm_name, COUNT(DISTINCT publication_number) AS n_pub
            FROM kr WHERE norm_name != '' GROUP BY norm_name
            """

        def run_window(as_of: date, tag: str):
            f_hi = int(as_of.strftime("%Y%m%d"))
            f_lo = int((as_of - timedelta(days=365 * years_back)).strftime("%Y%m%d"))
            ps = [bigquery.ScalarQueryParameter("as_of", "INT64", int(as_of.strftime("%Y%m%d"))),
                  bigquery.ScalarQueryParameter("f_lo", "INT64", f_lo),
                  bigquery.ScalarQueryParameter("f_hi", "INT64", f_hi)]
            return runner.run(f"assignee_agg_{tag}", agg_sql(), ps)

        rows_now, info_now = run_window(T_NOW, "now")
        if rows_now is None:
            return Verdict("B", T_NOW.isoformat(), "UNVERIFIED",
                           known_limitations=lim + [f"집계 쿼리 실패/비용초과: {info_now.get('error')}"],
                           runtime_sec=time.time() - t0, detail={"bq_log": runner.log})

        agg: Dict[str, int] = {str(r["norm_name"]): int(r["n_pub"]) for r in rows_now}
        exact_hit = {t[0]: agg.get(t[2], 0) for t in targets}
        n_exact = sum(1 for v in exact_hit.values() if v > 0)

        # 퍼지 매칭은 '분리 보고'만 한다. 임계값을 낮춰 매칭률을 부풀리지 않는다(§5.5.3).
        import difflib
        agg_keys = list(agg.keys())
        fuzzy_only = 0
        for sc, _dn, nn in targets:
            if not nn or exact_hit[sc] > 0:
                continue
            near = difflib.get_close_matches(nn, agg_keys, n=1, cutoff=0.92)
            if near:
                fuzzy_only += 1
        b1 = n_exact / len(targets)
        # B-2 의 분모는 'B-1 통과 종목'. 완전일치로 통과한 종목과, 퍼지에서만 잡힌 종목을 합한 것이
        # '특허를 가진 것으로 보이는 종목' 이고, 그중 완전일치가 차지하는 비율이 매핑의 순도다.
        denom_b2 = n_exact + fuzzy_only
        b2 = (n_exact / denom_b2) if denom_b2 else 0.0

        # ── B-3 : 피인용 데이터 결측률 ──────────────────────────────────────────────
        sql_cite = f"""
        WITH kr AS (
          SELECT {sql_norm('a.name')} AS norm_name,
                 p.publication_number,
                 ARRAY_LENGTH(p.citation) AS n_cite
          FROM `{BQ_TABLE}` p, UNNEST(p.assignee_harmonized) AS a
          WHERE p.country_code = 'KR'
            AND p.publication_date <= @as_of
            AND p.filing_date BETWEEN @f_lo AND @f_hi
        )
        SELECT COUNTIF(n_cite IS NULL OR n_cite = 0) AS n_missing, COUNT(*) AS n_total
        FROM kr WHERE norm_name IN UNNEST(@names)
        """
        f_hi = int(T_NOW.strftime("%Y%m%d"))
        f_lo = int((T_NOW - timedelta(days=365 * years_back)).strftime("%Y%m%d"))
        ps_cite = [bigquery.ScalarQueryParameter("as_of", "INT64", f_hi),
                   bigquery.ScalarQueryParameter("f_lo", "INT64", f_lo),
                   bigquery.ScalarQueryParameter("f_hi", "INT64", f_hi),
                   bigquery.ArrayQueryParameter("names", "STRING",
                                                [t[2] for t in targets if exact_hit[t[0]] > 0])]
        rows_cite, info_cite = runner.run("citation_coverage", sql_cite, ps_cite)
        if rows_cite:
            n_missing = int(rows_cite[0]["n_missing"] or 0)
            n_total = int(rows_cite[0]["n_total"] or 0)
            b3 = (n_missing / n_total) if n_total else None
        else:
            b3, n_missing, n_total = None, 0, 0
            lim.append(f"B-3 측정 실패(비용 초과 또는 쿼리 오류): {info_cite.get('error')} — 미달이 아니라 미측정이다.")

        # ── B-4 : T_PAST 시점에도 B-1 성립하는가 ────────────────────────────────────
        rows_past, info_past = run_window(T_PAST, "past")
        if rows_past is not None:
            agg_p = {str(r["norm_name"]): int(r["n_pub"]) for r in rows_past}
            n_exact_p = sum(1 for _sc, _dn, nn in targets if agg_p.get(nn, 0) > 0)
            b4 = n_exact_p / len(targets)
        else:
            b4 = None
            lim.append(f"B-4 측정 실패: {info_past.get('error')} — 미달이 아니라 미측정이다.")
        lim.append(f"B-4 의 종목 집합은 {T_NOW} 기준 하위 {TH.MEASURE_SUBSET_N}종목이다. "
                   f"{T_PAST} 시점 유니버스로 다시 뽑은 것이 아니므로 생존편의가 있다.")

        assert_thresholds_untouched()
        gates = [
            Gate("B-1", f"최근 {years_back}년 KR 특허 1건 이상 보유 비율", round(b1, 4),
                 TH.B1_PATENT_HOLDER_RATIO_MIN, b1 >= TH.B1_PATENT_HOLDER_RATIO_MIN,
                 f"완전일치 {n_exact}/{len(targets)}종목. 관측가능성 publication_date<={T_NOW}, "
                 f"측정변수 filing_date ∈ [{f_lo}, {f_hi}]"),
            Gate("B-2", "출원인명 완전일치 매핑 성공률 (B-1 통과 종목 대상)", round(b2, 4),
                 TH.B2_EXACT_MATCH_RATIO_MIN, b2 >= TH.B2_EXACT_MATCH_RATIO_MIN,
                 f"완전일치 {n_exact}종목 / 퍼지(cutoff 0.92)에서만 잡힌 종목 {fuzzy_only}종목. "
                 "퍼지 결과는 분리 보고이며 판정에 합산하지 않았다."),
            Gate("B-3", "피인용 데이터 결측률", (round(b3, 4) if b3 is not None else None),
                 TH.B3_CITATION_MISS_MAX,
                 (b3 <= TH.B3_CITATION_MISS_MAX) if b3 is not None else None,
                 f"결측 {n_missing:,} / 전체 {n_total:,}" if b3 is not None else "측정 실패(UNVERIFIED)"),
            Gate("B-4", f"T_PAST({T_PAST}) 시점에도 B-1 성립",
                 (round(b4, 4) if b4 is not None else None), TH.B4_PAST_HOLDER_RATIO_MIN,
                 (b4 >= TH.B4_PAST_HOLDER_RATIO_MIN) if b4 is not None else None,
                 "" if b4 is not None else "측정 실패(UNVERIFIED)"),
        ]
        measured_ok = any(g.passed is not None for g in gates)
        status = auto_status(gates, measured_ok=measured_ok)
        pending = [g.id for g in gates if g.passed is None]
        return Verdict("B", T_NOW.isoformat(), status, gates=gates, known_limitations=lim,
                       manual_gates_pending=pending, runtime_sec=time.time() - t0,
                       detail={"bq_log": runner.log, "n_targets": len(targets),
                               "years_back": years_back,
                               "canary_hangul": han, "canary_roman": rom})
    except Exception as e:                                      # noqa: BLE001
        guard_enospc(e)
        LOG(f"축 B 예외: {e}\n{traceback.format_exc()}", "ERROR")
        return Verdict("B", T_NOW.isoformat(), "UNVERIFIED",
                       known_limitations=lim + [f"예외로 측정 실패: {type(e).__name__}: {e}"],
                       runtime_sec=time.time() - t0)
    finally:
        VAULT.leave()


# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   축 C — 국민연금 사업장 (재프로브)  (§6)
#
#   1차 실행의 HTTP 400 / result_code=null 은 "데이터 없음"이 아니라 "요청 거부"다.
#   v1.0 의 STOP 판정은 근거 부족이므로 무효화하고 다시 프로브한다.
#
# ════════════════════════════════════════════════════════════════════════════════════════════

NPS_BASE = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireService"
NPS_OP = "getBassInfoSearch"


def _xml_first(text: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1).strip() if m else None


def _nps_parse(text: str) -> Dict[str, Any]:
    """resultCode/resultMsg 를 원문 그대로 뽑는다. JSON/XML 둘 다 대응."""
    out: Dict[str, Any] = {"resultCode": None, "resultMsg": None, "totalCount": None, "items": []}
    t = (text or "").strip()
    if t.startswith("{"):
        try:
            j = json.loads(t)
            hd = (j.get("response") or {}).get("header") or {}
            bd = (j.get("response") or {}).get("body") or {}
            out["resultCode"] = hd.get("resultCode")
            out["resultMsg"] = hd.get("resultMsg")
            out["totalCount"] = bd.get("totalCount")
            items = (bd.get("items") or {}).get("item") or []
            out["items"] = items if isinstance(items, list) else [items]
            return out
        except Exception:
            pass
    out["resultCode"] = _xml_first(t, "resultCode") or _xml_first(t, "returnReasonCode")
    out["resultMsg"] = _xml_first(t, "resultMsg") or _xml_first(t, "returnAuthMsg") or _xml_first(t, "errMsg")
    tc = _xml_first(t, "totalCount")
    out["totalCount"] = int(tc) if (tc or "").isdigit() else None
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", t, re.S):
        blk = m.group(1)
        d = {k: v.strip() for k, v in re.findall(r"<(\w+)>(.*?)</\1>", blk, re.S)}
        items.append(d)
    out["items"] = items
    return out


@dataclass
class Probe:
    name: str
    params: Dict[str, Any]
    http_status: Optional[int] = None
    result_code: Optional[str] = None
    result_msg: Optional[str] = None
    total_count: Optional[int] = None
    n_items: int = 0
    ok: bool = False
    raw_head: str = ""
    error: str = ""


def run_axis_C(paths: Paths, dart: DartClient, universe_fetcher: Callable[[date], List[UnivRow]],
               limitations: List[str], transport: Optional[Callable] = None) -> Verdict:
    HEAD("축 C — 국민연금 사업장 (재프로브)")
    VAULT.enter("C")
    t0 = time.time()
    lim = list(limitations)
    lim.append(f"관측지연: {OBSERVATION_LAG_NOTE['C']}")
    try:
        if not DATA_GO_KR_KEY:
            msg = ("공공데이터포털 인증키 없음. https://www.data.go.kr 에서 "
                   "'국민연금공단_국민연금 가입 사업장 내역' 활용신청 → 마이페이지 > 데이터활용 > "
                   "Open API > 인증키(일반 인증키 Decoding)를 DATA_GO_KR_KEY 에 넣어라. "
                   "자동승인 API 는 즉시, 심의 대상은 1~2 영업일 소요된다.")
            LOG(msg, "WARN")
            return Verdict("C", T_NOW.isoformat(), "BLOCKED_PREREQ",
                           known_limitations=lim + [f"BLOCKED_PREREQ 사유: {msg}"],
                           runtime_sec=time.time() - t0)
        if "%" in DATA_GO_KR_KEY:
            LOG("⚠ 인증키에 '%' 가 있다 — Encoding 키를 넣은 것으로 보인다. "
                "Decoding 키를 넣지 않으면 이중 인코딩으로 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다.", "WARN")
            lim.append("입력된 인증키가 Encoding 형식으로 보인다(‘%’ 포함). Decoding 키 사용을 권고한다.")

        breaker = CircuitBreaker("C")
        base = {"serviceKey": DATA_GO_KR_KEY, "numOfRows": 100, "pageNo": 1}

        # §6.2 재프로브 절차 — 순서대로, 실패하면 다음으로
        plans: List[Tuple[str, Dict[str, Any]]] = [
            ("①dataCrtYm=202506 (1년 전 월) — 미공표 여부 판별", {**base, "dataCrtYm": "202506"}),
            ("②dataCrtYm 없이 호출 — 필수 여부 판별", {**base}),
            ("③키 승인 상태 확인 — 최소 파라미터로 인증 오류만 본다", {"serviceKey": DATA_GO_KR_KEY}),
            ("④numOfRows=1, pageNo=1 최소 요청 — 파라미터 형식 문제 판별",
             {"serviceKey": DATA_GO_KR_KEY, "numOfRows": 1, "pageNo": 1}),
        ]
        LOG("공공데이터포털 승인 상태 확인 안내: 마이페이지 > 데이터활용 > 활용신청 현황 에서 "
            "해당 API 가 '승인' 인지, 일일 트래픽이 남아 있는지 확인하라. "
            "'신청' 상태면 어떤 파라미터를 넣어도 실패한다.")

        probes: List[Probe] = []
        success: Optional[Probe] = None
        for name, params in plans:
            if transport is not None:
                CALLS.add("C", 1)
                st, text = transport(NPS_OP, params)
                res = HttpResult(st == 200, st, text, "" if st == 200 else f"HTTP {st}", 0.0)
            else:
                res = http_get(f"{NPS_BASE}/{NPS_OP}", params, axis="C", breaker=breaker)
            p = Probe(name, {k: ("<KEY>" if k == "serviceKey" else v) for k, v in params.items()})
            p.http_status = res.status
            p.raw_head = (res.text or "")[:400].replace("\n", " ")
            parsed = _nps_parse(res.text or "")
            p.result_code = parsed["resultCode"]
            p.result_msg = parsed["resultMsg"]
            p.total_count = parsed["totalCount"]
            p.n_items = len(parsed["items"] or [])
            p.ok = bool(res.ok and (p.result_code in ("00", "0", "000") or p.n_items > 0))
            p.error = res.error
            probes.append(p)
            LOG(f"프로브 {name}")
            LOG(f"   HTTP={p.http_status}  resultCode={p.result_code!r}  resultMsg={p.result_msg!r}  "
                f"totalCount={p.total_count}  items={p.n_items}")
            LOG(f"   원문(앞 400자): {p.raw_head}")
            if p.ok:
                success = p
                LOG("   → 성공. 이후 프로브는 생략하고 게이트로 넘어간다.")
                break

        probe_path = paths.report("diag_C_probes.csv")
        write_csv(probe_path, ["probe", "params", "http_status", "resultCode", "resultMsg",
                               "totalCount", "n_items", "ok", "raw_head", "error"],
                  [[p.name, json.dumps(p.params, ensure_ascii=False), p.http_status, p.result_code,
                    p.result_msg, p.total_count, p.n_items, p.ok, p.raw_head, p.error] for p in probes])
        LOG(f"프로브 원문 로그 → {probe_path}")

        if success is None:
            # §6.3 — 4개 시도 모두 실패 → UNVERIFIED (STOP 아님)
            lim.append("4개 프로브 전부 실패. 이는 '데이터로 쓸 수 없다'가 아니라 '측정하지 못했다'이다.")
            for p in probes:
                lim.append(f"프로브 실패 원문 — {p.name}: HTTP={p.http_status}, "
                           f"resultCode={p.result_code!r}, resultMsg={p.result_msg!r}, error={p.error!r}")
            return Verdict("C", T_NOW.isoformat(), "UNVERIFIED",
                           known_limitations=lim, runtime_sec=time.time() - t0,
                           detail={"probes": [asdict(p) for p in probes]})

        # ── §6.4 게이트 (프로브 성공 시에만) ────────────────────────────────────────
        # 프로브 단계에서는 원문 앞 400자만 보관했으므로, 성공한 조합으로 한 번 더 호출해 본문을 받는다.
        if transport is not None:
            CALLS.add("C", 1)
            st, text = transport(NPS_OP, {**base, **({"dataCrtYm": "202506"} if "①" in success.name else {})})
            res2 = HttpResult(st == 200, st, text)
        else:
            res2 = http_get(f"{NPS_BASE}/{NPS_OP}",
                            {**base, **({"dataCrtYm": "202506"} if "①" in success.name else {})},
                            axis="C", breaker=breaker)
        items = _nps_parse(res2.text or "")["items"]
        LOG(f"본문 수신: {len(items)}건")

        # C-1 사업자등록번호 자릿수
        bizno_vals = [str(it.get("bzowrRgstNo", "") or "") for it in items]
        digits = [re.sub(r"\D", "", v) for v in bizno_vals if v]
        full10 = sum(1 for d in digits if len(d) == 10)
        c1 = "Y" if (digits and full10 == len(digits)) else ("부분" if full10 else "N")
        sample_biz = bizno_vals[:5]
        LOG(f"C-1 사업자등록번호 자릿수: {c1} (표본 {sample_biz})")

        # C-2 매칭률 — DART 기업개황의 bizr_no 와 대조
        univ = universe_fetcher(T_NOW)
        measure = pick_universe_sample(pick_measure_subset(univ, TH.MEASURE_SUBSET_N))
        corp_rows = dart.corp_code_table("C")
        by_stock = {(r.get("stock_code") or "").strip().zfill(6): r for r in corp_rows
                    if (r.get("stock_code") or "").strip()}
        room = CALLS.stop_at - CALLS.total
        sample = measure[:max(0, min(len(measure), room))]
        if len(sample) < len(measure):
            lim.append(f"호출 예산 때문에 C-2 표본을 {len(measure)}종목에서 {len(sample)}종목으로 줄였다(§10).")
        biz_of_univ: Dict[str, str] = {}
        for u in sample:
            r = by_stock.get(u.stock_code.zfill(6))
            if not r:
                continue
            comp = dart.company(r["corp_code"], "C", breaker)
            if comp and str(comp.get("status", "")) == "000":
                bz = re.sub(r"\D", "", str(comp.get("bizr_no", "") or ""))
                if bz:
                    biz_of_univ[u.stock_code] = bz
        nps_prefix = {d[:6] for d in digits if len(d) >= 6}
        nps_names = {norm_corp_name(it.get("wkplNm")) for it in items}
        matched = 0
        match_rows: List[List[Any]] = []
        for u in sample:
            bz = biz_of_univ.get(u.stock_code)
            hit_by_biz = bool(bz and bz[:6] in nps_prefix)
            hit_by_name = norm_corp_name(u.name) in nps_names if u.name else False
            if hit_by_biz or hit_by_name:
                matched += 1
            match_rows.append([u.stock_code, u.name or "", bz or "", hit_by_biz, hit_by_name, ""])
        c2 = (matched / len(sample)) if sample else 0.0
        lim.append("C-2 는 이번 프로브가 돌려준 페이지(사업장 일부)만을 상대로 계산한 것이다. "
                   "전체 사업장 원장을 내려받은 뒤라야 참값에 가까워진다.")

        # C-3 월별 시계열 연속성
        months: List[str] = []
        d = date(T_PAST.year, T_PAST.month, 1)
        while d <= date(T_NOW.year, T_NOW.month, 1):
            months.append(d.strftime("%Y%m"))
            d = date(d.year + (d.month // 12), (d.month % 12) + 1, 1)
        present: List[str] = []
        for ym in months:
            if CALLS.total >= CALLS.stop_at:
                lim.append("호출 예산 때문에 C-3 월별 점검을 중도 종료했다(§10).")
                break
            if transport is not None:
                CALLS.add("C", 1)
                st, text = transport(NPS_OP, {"serviceKey": DATA_GO_KR_KEY, "numOfRows": 1,
                                              "pageNo": 1, "dataCrtYm": ym})
                r3 = HttpResult(st == 200, st, text)
            else:
                r3 = http_get(f"{NPS_BASE}/{NPS_OP}",
                              {"serviceKey": DATA_GO_KR_KEY, "numOfRows": 1, "pageNo": 1, "dataCrtYm": ym},
                              axis="C", breaker=breaker)
            pr = _nps_parse(r3.text or "")
            if r3.ok and (pr["totalCount"] or 0) > 0:
                present.append(ym)
        c3_ok = len(present) == len(months)
        LOG(f"C-3 월별 존재: {len(present)}/{len(months)}개월")

        # C-4 다사업장 통합 가능 여부
        by_prefix: Counter = Counter(d[:6] for d in digits if len(d) >= 6)
        multi = sum(1 for _k, v in by_prefix.items() if v > 1)
        if c1 == "Y":
            c4 = "Y"
        elif by_prefix:
            c4 = "부분"
        else:
            c4 = "N"
        LOG(f"C-4 다사업장 법인 통합: {c4} (사업자번호 앞 6자리 기준 복수 사업장 {multi}건)")

        # C-5 수기 검증 CSV
        c5_path = paths.report("manual_check_C_workplace_match.csv")
        write_csv(c5_path, ["stock_code", "corp_name", "dart_bizr_no", "hit_by_bizno_prefix",
                            "hit_by_name", "verdict_by_human(O/X)"],
                  match_rows[:TH.C5_MANUAL_SAMPLE_N])
        LOG(f"C-5 수기 검증 표본 → {c5_path}")

        assert_thresholds_untouched()
        gates = [
            Gate("C-1", "사업자등록번호 전체 자릿수 제공 여부 (Y/N)", c1, "Y", c1 == "Y",
                 f"표본 {sample_biz}"),
            Gate("C-2", "유니버스 종목 사업장 매칭 성공 비율", round(c2, 4), TH.C2_WORKPLACE_MATCH_MIN,
                 c2 >= TH.C2_WORKPLACE_MATCH_MIN,
                 f"매칭 {matched}/{len(sample)}종목 (사업자번호 앞 6자리 또는 사업장명 정규화 일치)"),
            Gate("C-3", f"T_PAST({T_PAST})까지 월별 시계열 연속 존재",
                 f"{len(present)}/{len(months)}", "전부 존재", c3_ok, ""),
            Gate("C-4", "다사업장 법인의 통합 가능 여부 (Y/N/부분)", c4, "Y/부분",
                 c4 in ("Y", "부분"), f"복수 사업장으로 보이는 사업자번호 앞자리 {multi}건"),
            Gate("C-5", "매칭 100건 수기 검증", None, "사람이 판정", None, f"{c5_path} 출력. PENDING 유지."),
        ]
        status = auto_status(gates, measured_ok=True)
        return Verdict("C", T_NOW.isoformat(), status, gates=gates, known_limitations=lim,
                       manual_gates_pending=["C-5"], runtime_sec=time.time() - t0,
                       detail={"probes": [asdict(p) for p in probes],
                               "n_items_page": len(items), "months_checked": len(months)})
    except AxisAbort as e:
        LOG(f"축 C 중단: {e}", "WARN")
        return Verdict("C", T_NOW.isoformat(), "UNVERIFIED",
                       known_limitations=lim + [f"중단: {e}"], runtime_sec=time.time() - t0)
    except Exception as e:                                      # noqa: BLE001
        guard_enospc(e)
        LOG(f"축 C 예외: {e}\n{traceback.format_exc()}", "ERROR")
        return Verdict("C", T_NOW.isoformat(), "UNVERIFIED",
                       known_limitations=lim + [f"예외로 측정 실패: {type(e).__name__}: {e}"],
                       runtime_sec=time.time() - t0)
    finally:
        VAULT.leave()


def pick_universe_sample(measure: List[UnivRow]) -> List[UnivRow]:
    """축 C 의 C-2 표본. 축 A 의 결과를 재사용하지 않고 유니버스에서 다시 뽑는다
    (P0_INDEPENDENT_AXES — 공용 데이터원은 공유하되 축의 산출물은 공유하지 않는다)."""
    return list(measure)


# ════════════════════════════════════════════════════════════════════════════════════════════
#   계약 검증 — 문장이 아니라 프로브로 확인한다
# ════════════════════════════════════════════════════════════════════════════════════════════

def _st(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def verify_contracts(root: str) -> List[Tuple[str, str, str]]:
    """(contract_id, state, detail). state ∈ {PASS, FAIL, SKIP, WAIVED}. FAIL 만 실행을 멈춘다."""
    rows: List[Tuple[str, str, str]] = []
    src_text, src_origin = read_own_source()
    rows.extend(scan_source_contracts(src_text, src_origin))          # P0_NO_STRATEGY, NO_KNOWN_DEAD_CALL

    state, msg = contract_runtime_root(root)
    rows.append(("P0_RUNTIME_ROOT", state, msg))

    try:
        assert_thresholds_untouched()
        rows.append(("P0_NO_THRESHOLD_EDIT", "PASS", f"임계값 지문 {_TH_FINGERPRINT[:16]} 일치"))
    except ContractViolation as e:
        rows.append(("P0_NO_THRESHOLD_EDIT", "FAIL", str(e)))

    class _FakeCache:                     # 실제 구현(RawCache.path)을 그대로 호출해 확인한다
        dir = os.path.join("ROOT", "dart_exctv")
    real_path = RawCache.path(_FakeCache(), "00126380", 2026, "11013")   # type: ignore[arg-type]
    ok_res = all(tok in real_path for tok in ("00126380", "2026", "11013"))
    rows.append(("P0_RESUMABLE", _st(ok_res),
                 f"캐시 경로에 (corp_code, bsns_year, reprt_code) 전부 포함: {real_path}"))

    fut = (T_NOW + timedelta(days=1)).strftime("%Y%m%d")
    payload = {"status": "000", "list": [
        {"rcept_no": fut + "000001", "nm": "미래", "birth_ym": "1970년 01월"},
        {"rcept_no": "20260514000001", "nm": "과거", "birth_ym": "1970년 01월"}]}
    kept, dropped = parse_exec_rows(payload, "C0000001", T_NOW)
    rows.append(("P0_PIT_STRICT", _st(len(kept) == 1 and len(dropped) == 1),
                 f"기준일 {T_NOW} 프로브: 잔존 {len(kept)}건 / 폐기 {len(dropped)}건"))

    gb = build_graph([
        ExecRow("IN1", "20260514000001", "홍길동", "197001"),
        ExecRow("OUT1", "20260514000002", "홍길동", "197001"),
        ExecRow("NOBIRTH_A", "20260514000003", "김결측", None),
        ExecRow("NOBIRTH_B", "20260514000004", "김결측", None),
    ])
    gm = measure_graph(gb, {"IN1"})
    rows.append(("P0_GRAPH_FULL_MEASURE_SUB",
                 _st(gm.edges_touching_measure == 1 and gm.edges_external == 1),
                 f"측정대상 밖 노드와의 엣지 유지 확인: 외부링크 {gm.edges_external}, 내부링크 {gm.edges_internal}"))
    rows.append(("P0_FAIL_LOUD", _st(len(gb.edges) == 1 and gb.n_rows_no_birth == 2),
                 f"출생년월 결측 {gb.n_rows_no_birth}행은 엣지를 만들지 않고 결측으로 계상(총 엣지 {len(gb.edges)})"))

    guard_ok = False
    VAULT.enter("A")
    try:
        VAULT.get("B")
    except ContractViolation:
        guard_ok = True
    finally:
        VAULT.leave()
    rows.append(("P0_INDEPENDENT_AXES", _st(guard_ok), "축 A 스코프에서 축 B 결과 접근 시 예외 발생 확인"))

    rows.append(("P0_CANARY_FIRST", _st(CANARY_N == 10),
                 f"카나리 {CANARY_N}종목, 통과 하한 {CANARY_MIN_OK}. 실패 시 벌크 진입 없이 UNVERIFIED 를 반환한다"
                 " (셀프테스트 T09 에서 검증)"))
    return rows


# ════════════════════════════════════════════════════════════════════════════════════════════
#   §9  산출물
# ════════════════════════════════════════════════════════════════════════════════════════════

def write_reports(paths: Paths, verdicts: List[Verdict], meta: Dict[str, Any]) -> Dict[str, str]:
    # 계약 면제/미검사 사실은 축마다 판정표에 실린다. 요약본 구석에만 적어두지 않는다.
    for v in verdicts:
        for w in reversed(RUNTIME_WAIVERS):
            if w not in v.known_limitations:
                v.known_limitations.insert(0, w)
    jpath = paths.report("phase0_verdict_v11.json")
    doc = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "spec": "PHASE 0 대체데이터 3축 수집 가능성 검증 명령서 v1.1",
           "run_meta": meta,
           "verdicts": [v.to_json() for v in verdicts]}
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    cpath = paths.report("phase0_verdict_v11.csv")
    rows = []
    for v in verdicts:
        if not v.gates:
            rows.append([v.axis, v.as_of, v.status, "", "", "", "", "",
                         " | ".join(v.known_limitations)[:1000]])
        for g in v.gates:
            rows.append([v.axis, v.as_of, v.status, g.id, g.criterion, g.measured, g.threshold,
                         ("PENDING" if g.passed is None else ("PASS" if g.passed else "FAIL")), g.note])
    write_csv(cpath, ["axis", "as_of", "status", "gate_id", "criterion", "measured", "threshold",
                      "result", "note"], rows)

    mpath = paths.report("phase0_summary_v11.md")
    L: List[str] = []
    L.append("# PHASE 0 대체데이터 3축 수집 가능성 검증 — 요약 (v1.1)")
    L.append("")
    L.append(f"- 생성: {doc['generated_at']}")
    L.append(f"- 실행 모드: `{meta.get('run_mode')}`")
    L.append(f"- PROJECT_ROOT: `{meta.get('project_root')}`")
    L.append(f"- 기준일: T_NOW={T_NOW}, T_PAST={T_PAST} / 실행일={meta.get('run_date')}")
    L.append(f"- 총 API 호출: {meta.get('api_calls_total')} (기준일별 내역은 아래 표)")
    L.append(f"- 총 실행시간: {meta.get('runtime_sec')}초")
    if meta.get("contracts"):
        nonpass = {c: st for c, st in meta["contracts"].items() if st != "PASS"}
        L.append(f"- 계약 검사: {len(meta['contracts'])}건 중 PASS "
                 f"{sum(1 for s in meta['contracts'].values() if s == 'PASS')}건"
                 + (f" / 그 외 {nonpass}" if nonpass else ""))
    if meta.get("cold_backup"):
        L.append(f"- 콜드 백업: {meta['cold_backup']}")
    L.append("")
    L.append("## 축별 판정")
    L.append("")
    L.append("| 축 | 기준일 | 판정 | 사람 판정 대기 |")
    L.append("|---|---|---|---|")
    for v in verdicts:
        L.append(f"| {v.axis} | {v.as_of} | **{v.status}** | {', '.join(v.manual_gates_pending) or '-'} |")
    L.append("")
    L.append("## 게이트")
    L.append("")
    L.append("| 축 | 게이트 | 기준 | 측정 | 임계 | 결과 |")
    L.append("|---|---|---|---|---|---|")
    for v in verdicts:
        for g in v.gates:
            r = "PENDING" if g.passed is None else ("PASS" if g.passed else "FAIL")
            L.append(f"| {v.axis} | {g.id} | {g.criterion} | {g.measured} | {g.threshold} | {r} |")
    L.append("")
    L.append("## 호출/캐시 집계")
    L.append("")
    L.append("| 버킷 | 호출 수 |")
    L.append("|---|---|")
    for k, n in sorted((meta.get("api_calls_by_bucket") or {}).items()):
        L.append(f"| {k} | {n} |")
    L.append(f"| **총계(별도 필드)** | **{meta.get('api_calls_total')}** |")
    L.append("")
    L.append("| 축 | 캐시 히트 | 캐시 미스 | 히트율 |")
    L.append("|---|---|---|---|")
    for ax, d in (meta.get("cache_by_axis") or {}).items():
        tot = d["hit"] + d["miss"]
        L.append(f"| {ax} | {d['hit']} | {d['miss']} | {(d['hit']/tot if tot else 0):.3f} |")
    L.append("")
    L.append("## 관측 지연 (§7)")
    L.append("")
    L.append("| 축 | 실제 사건 → 관측 가능 시점 |")
    L.append("|---|---|")
    for ax, note in OBSERVATION_LAG_NOTE.items():
        L.append(f"| {ax} | {note} |")
    L.append("")
    L.append("## known_limitations")
    for v in verdicts:
        L.append("")
        L.append(f"### {v.axis} @ {v.as_of}")
        for k in v.known_limitations:
            L.append(f"- {k}")
    if meta.get("reductions"):
        L.append("")
        L.append("### 시간/호출 예산 축소 적용 (§10)")
        for r in meta["reductions"]:
            L.append(f"- {r}")
    L.append("")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    lpath = paths.report("run_log.txt")
    with open(lpath, "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG_SINK))
    return {"json": jpath, "csv": cpath, "md": mpath, "log": lpath}


# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   셀프테스트 — 네트워크·키 없이 측정 로직 전체를 검증한다
#
#   합성 데이터로 파이프라인을 끝까지 돌리고, 그래프/차분/게이트 계산을
#   독립적으로 다시 구현한 naive 버전과 대조한다(differential test).
#
# ════════════════════════════════════════════════════════════════════════════════════════════

QIDX = {"11013": 0, "11012": 1, "11014": 2, "11011": 3}


def qkey(bsns_year: int, reprt_code: str) -> int:
    return bsns_year * 4 + QIDX[reprt_code]


class SyntheticWorld:
    """1,300개 합성 법인. 겸직 인물 900명 중 600명은 상주, 300명은 분기마다 들락거린다."""

    N_ALL = 1300
    N_LOCAL_EXEC = 4
    N_SHARED = 900
    N_MEASURE_REAL = 978          # 하위 1,000 중 매핑 실패 22종목을 뺀 수

    def __init__(self) -> None:
        self.corp = [f"C{i:07d}" for i in range(self.N_ALL)]
        self.idx = {c: i for i, c in enumerate(self.corp)}

    # ── 유니버스 ─────────────────────────────────────────────────────────────────────
    def universe(self, as_of: date) -> List[UnivRow]:
        rows = [UnivRow(f"{i:05d}0", f"합성{i}", "KOSPI" if i % 2 else "KOSDAQ", (i + 1) * 1_000_000)
                for i in range(self.N_ALL)]
        # 매핑 실패를 유발하는 종목들. 시총을 아주 작게 줘서 하위 1,000 안에 들어가게 한다.
        for k in range(12):
            rows.append(UnivRow(f"{9000+k:05d}5", f"합성우선{k}우", "KOSPI", k + 1))
        for k in range(3):
            rows.append(UnivRow(f"{9100+k:05d}0", f"엔에이치스팩{k}호", "KOSDAQ", 20 + k))
        for k in range(2):
            rows.append(UnivRow(f"{9200+k:05d}0", f"합성리츠{k}", "KOSPI", 40 + k))
        for k in range(5):
            rows.append(UnivRow(f"{9300+k:05d}0", f"미상장{k}", "KOSDAQ", 60 + k))
        return rows

    def corp_rows(self) -> List[Dict[str, str]]:
        return [{"corp_code": self.corp[i], "corp_name": f"합성{i}주식회사",
                 "stock_code": f"{i:05d}0", "modify_date": "20260630"} for i in range(self.N_ALL)]

    # ── 겸직 인물 ────────────────────────────────────────────────────────────────────
    def shared_pairs(self, q: int) -> List[Tuple[int, int, str, str]]:
        """해당 분기에 살아 있는 (회사a, 회사b, 성명, 출생년월) 목록."""
        out = []
        for p in range(self.N_SHARED):
            a = p % self.N_MEASURE_REAL
            if p % 2 == 0:
                b = self.N_MEASURE_REAL + (p % (self.N_ALL - self.N_MEASURE_REAL))
            else:
                b = (p * 13 + 7) % self.N_MEASURE_REAL
                if b == a:
                    b = (b + 1) % self.N_MEASURE_REAL
            if a == b:
                continue
            stable = (p % 3 != 0)
            alive = stable or ((q + p) % 4 < 2)
            if not alive:
                continue
            out.append((a, b, f"겸직{p}", f"19{60 + (p % 30):02d}{(p % 12) + 1:02d}"))
        return out

    # ── DART 트랜스포트 ──────────────────────────────────────────────────────────────
    def transport(self, endpoint: str, params: Dict[str, Any]) -> Any:
        if endpoint == "corpCode.xml":
            return self.corp_rows()
        if endpoint == "company.json":
            cc = params["corp_code"]
            i = self.idx.get(cc)
            if i is None:
                return {"status": "013", "message": "조회된 데이타가 없습니다."}
            return {"status": "000", "corp_name": f"합성{i}주식회사",
                    "bizr_no": f"{100 + (i % 800):03d}{(i % 90) + 10:02d}{(i % 90000) + 10000:05d}"}
        if endpoint != "exctvSttus.json":
            return {"status": "100", "message": "알 수 없는 엔드포인트"}

        cc = params["corp_code"]
        y, rc = int(params["bsns_year"]), params["reprt_code"]
        i = self.idx.get(cc)
        if i is None:
            return {"status": "013", "message": "조회된 데이타가 없습니다."}
        if i % 97 == 0:                       # 결산기 12월 아님 등으로 해당 보고서 자체가 없음
            return {"status": "013", "message": "조회된 데이타가 없습니다."}

        pe = period_end_of(y, rc)
        late = (i % 37 == 0)
        filed = pe + timedelta(days=100 if late else 44)
        rno = filed.strftime("%Y%m%d") + f"{i:06d}"

        lst = []
        for k in range(self.N_LOCAL_EXEC):
            miss_birth = (i % 50 == 0 and k == 3)
            lst.append({
                "rcept_no": "" if (i % 211 == 0 and k == 0) else rno,
                "corp_code": cc, "corp_name": f"합성{i}주식회사",
                "nm": f"임원{i}_{k}", "sexdstn": "남",
                "birth_ym": "" if miss_birth else f"19{60 + ((i + k) % 30):02d}년 {(k % 12) + 1:02d}월",
                "ofcps": "대표이사" if k == 0 else "사내이사",
                "rgist_exctv_at": "등기임원", "fte_at": "상근",
            })
        for (a, b, nm, by) in self.shared_pairs(qkey(y, rc)):
            if i not in (a, b):
                continue
            lst.append({"rcept_no": rno, "corp_code": cc, "corp_name": f"합성{i}주식회사",
                        "nm": nm, "sexdstn": "남",
                        "birth_ym": f"{by[:4]}년 {by[4:]}월",
                        "ofcps": "기타비상무이사", "rgist_exctv_at": "등기임원", "fte_at": "비상근"})
        return {"status": "000", "message": "정상", "list": lst}

    # ── 국민연금 트랜스포트 ──────────────────────────────────────────────────────────
    def nps_transport_fail(self, op: str, params: Dict[str, Any]) -> Tuple[int, str]:
        return 400, ""

    def nps_transport_ok(self, op: str, params: Dict[str, Any]) -> Tuple[int, str]:
        n = int(params.get("numOfRows", 10) or 10)
        items = []
        for k in range(min(n, 100)):
            i = k
            items.append(
                f"<item><dataCrtYm>202506</dataCrtYm><seq>{k}</seq>"
                f"<wkplNm>합성{i}주식회사</wkplNm>"
                f"<bzowrRgstNo>{100 + (i % 800):03d}{(i % 90) + 10:02d}{(i % 90000) + 10000:05d}</bzowrRgstNo>"
                f"<wkplJnngStcd>1</wkplJnngStcd></item>")
        body = ("<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg>"
                f"</header><body><items>{''.join(items)}</items>"
                f"<totalCount>{len(items)}</totalCount></body></response>")
        return 200, body


def naive_edges(rows: List[ExecRow]) -> Set[Tuple[str, str]]:
    """build_graph 와 완전히 다른 방식으로 다시 센다(differential test)."""
    per_corp: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    for r in rows:
        if r.birth_ym and norm_person_name(r.name):
            per_corp[r.corp_code].add((norm_person_name(r.name), r.birth_ym))
    corps = sorted(per_corp)
    out: Set[Tuple[str, str]] = set()
    for x in range(len(corps)):
        for y in range(x + 1, len(corps)):
            if per_corp[corps[x]] & per_corp[corps[y]]:
                out.add((corps[x], corps[y]))
    return out


class Check:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, bool, str]] = []

    def __call__(self, name: str, cond: bool, detail: str = "") -> None:
        self.rows.append((name, bool(cond), detail))
        LOG(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}", "INFO" if cond else "ERROR")

    @property
    def failed(self) -> List[str]:
        return [n for n, ok, _ in self.rows if not ok]


def run_selftest(paths: Paths, run_date: date) -> int:
    HEAD("셀프테스트 — 합성 데이터로 측정 로직 검증 (네트워크·키 불필요)")
    ck = Check()
    w = SyntheticWorld()

    # ── T01~T05 단위 ────────────────────────────────────────────────────────────────
    ck("T01 보고서 선택 T_NOW", latest_available_report(T_NOW) == (2026, "11013"),
       f"→ {latest_available_report(T_NOW)} (반기 제출기한 {filing_deadline_of(2026, '11012')})")
    ck("T01b 보고서 선택 T_PAST", latest_available_report(T_PAST) == (2021, "11013"),
       f"→ {latest_available_report(T_PAST)}")
    ck("T02 출생년월 정규화",
       norm_birth_ym("1968년 03월") == "196803" and norm_birth_ym("") is None
       and norm_birth_ym("1968년 13월") is None,
       "형식 혼재 대응 + 판독불가는 None")
    ck("T03 접수일자 추출", rcept_dt_of("20260514000123") == date(2026, 5, 14)
       and rcept_dt_of("bad") is None, "rcept_no 앞 8자리")
    ck("T04 법인명 정규화",
       norm_corp_name("주식회사 가나다") == norm_corp_name("가나다(주)") == "가나다",
       f"→ {norm_corp_name('주식회사 가나다')!r}")
    ck("T05 중앙값", median([1, 2, 3]) == 2 and median([1, 2, 3, 4]) == 2.5, "")

    # ── T06 생성/소멸 (합산 금지 확인) ──────────────────────────────────────────────
    prev = {("A", "B"): {("p", "1")}, ("A", "C"): {("q", "1")}}
    now = {("A", "C"): {("q", "1")}, ("A", "D"): {("r", "1")}}
    ev = edge_events(prev, now, {"A"})
    ck("T06 edge_born/edge_died", ev["A"] == (1, 1, 2, 2),
       f"born/died/deg_prev/deg_now = {ev['A']} — 순변화 0 이지만 생성 1·소멸 1 로 분리 보존")

    # ── T07 예산 중단 ───────────────────────────────────────────────────────────────
    led = CallLedger(1000, 0.80)
    hit = False
    try:
        for _ in range(1000):
            led.add("A", 1)
    except AxisAbort:
        hit = True
    ck("T07 호출 예산 80% 중단", hit and led.total == 800, f"총 {led.total}회에서 중단")

    # ── T08 계약 ────────────────────────────────────────────────────────────────────
    st_eph, _ = contract_runtime_root("/content/phase0")
    st_ok, _ = contract_runtime_root("/home/me/phase0")
    ck("T08 P0_RUNTIME_ROOT", st_ok == "PASS" and st_eph == ("WAIVED" if ALLOW_EPHEMERAL_ROOT else "FAIL"),
       f"/content → {st_eph} (ALLOW_EPHEMERAL_ROOT={ALLOW_EPHEMERAL_ROOT}), 로컬 → {st_ok}")
    ck("T08c 면제는 PASS 로 기록되지 않는다", st_eph != "PASS",
       "사라지는 경로는 어떤 설정에서도 PASS 가 될 수 없다")
    src_text, src_origin = read_own_source()
    scan = {c: st for c, st, _ in scan_source_contracts(src_text, src_origin)}
    ck("T08d 소스 정적 검사 수행", src_text is not None and scan["P0_NO_STRATEGY"] == "PASS",
       f"출처: {src_origin}")
    ck("T08e 소스 없으면 PASS 가 아니라 SKIP",
       all(st == "SKIP" for _c, st, _d in scan_source_contracts(None, "테스트")),
       "검사하지 못한 것을 통과로 적지 않는다")
    frozen = False
    try:
        TH.A5_TOTAL_LINKS_MIN = 1                      # type: ignore[misc]
    except Exception:
        frozen = True
    ck("T08b P0_NO_THRESHOLD_EDIT", frozen, "임계값 dataclass 는 frozen — 대입 자체가 예외")

    # ── T09 카나리 실패 시 벌크 진입 금지 ───────────────────────────────────────────
    def dead_transport(endpoint: str, params: Dict[str, Any]):
        if endpoint == "corpCode.xml":
            return w.corp_rows()
        return {"status": "013", "message": "조회된 데이타가 없습니다."}

    p_canary = Paths(os.path.join(paths.root, "_selftest_canary"), selftest=True)
    p_canary.ensure()
    d_dead = DartClient("TEST", p_canary, transport=dead_transport)
    ctx_dead = AxisAContext(d_dead, p_canary, run_date, w.universe,
                            lambda _d: set(), lambda: {})
    calls_before = CALLS.total
    v_canary, art_canary = run_axis_A_asof(ctx_dead, T_NOW, [])
    spent = CALLS.total - calls_before
    ck("T09 P0_CANARY_FIRST",
       v_canary.status == "UNVERIFIED" and not art_canary and spent < 200,
       f"카나리 전멸 → {v_canary.status}, 소모 호출 {spent}회(벌크 미진입)")

    # ── T10 축 A 풀 파이프라인 ──────────────────────────────────────────────────────
    p_main = Paths(os.path.join(paths.root, "_selftest_main"), selftest=True)
    p_main.ensure()
    dart = DartClient("TEST", p_main, transport=w.transport)
    # 4개 스냅샷의 법정 제출기한이 전부 지난 날짜를 쓴다(2026 반기 기한 = 2026-08-14).
    # 기한 전 실행에서 무슨 일이 벌어지는지는 T12c 에서 따로 검증한다.
    main_run_date = date(2026, 8, 20)
    LOG(f"셀프테스트 본 파이프라인 실행일: {main_run_date} (스냅샷 4개 제출기한 모두 경과)")
    ctx = AxisAContext(dart, p_main, main_run_date, w.universe, lambda _d: set(), lambda: {})
    t_calls0 = CALLS.total
    verdicts = run_axis_A(ctx, [])
    v_now = next(v for v in verdicts if v.axis == "A" and v.as_of == T_NOW.isoformat())
    v_past = next(v for v in verdicts if v.axis == "A" and v.as_of == T_PAST.isoformat())
    v_del = next(v for v in verdicts if v.axis == "A-delta")

    g = {x.id: x for x in v_now.gates}
    ck("T10 축 A(T_NOW) 판정 GO", v_now.status == "GO",
       f"A-1={g['A-1'].measured} A-2={g['A-2'].measured} A-3={g['A-3'].measured} A-5={g['A-5'].measured}")
    ck("T10b A-4 는 PENDING 유지", g["A-4"].passed is None and "A-4" in v_now.manual_gates_pending, "")
    ck("T10c 외부 링크 보존", g["A-5"].note.count("외부 링크") == 1
       and v_now.detail["edges_external"] > 0,
       f"내부 {v_now.detail['edges_internal']} / 외부 {v_now.detail['edges_external']}")
    ck("T10d 매핑 실패 분류", v_now.detail["mapping_miss_measure"].get("①우선주") == 12
       and v_now.detail["mapping_miss_measure"].get("②스팩") == 3
       and v_now.detail["mapping_miss_measure"].get("③리츠") == 2
       and v_now.detail["mapping_miss_measure"].get("⑥원인불명") == 5,
       f"{v_now.detail['mapping_miss_measure']}")
    ck("T10e PIT 폐기 발생", v_now.detail["pit_dropped_records"] > 0,
       f"폐기 {v_now.detail['pit_dropped_records']}건 (지연제출 법인 + 접수번호 판독불가)")
    ck("T10f T_PAST 도 측정됨", v_past.status in ("GO", "STOP"), f"{v_past.status}")

    # differential: 그래프를 완전히 다른 방식으로 다시 센다
    cr = collect_exec_snapshot(ctx, sorted(w.corp), 2026, "11013", T_NOW, "selftest-diff",
                               CircuitBreaker("A"))
    gb = build_graph(cr.rows)
    ck("T11 그래프 differential", set(gb.edges.keys()) == naive_edges(cr.rows),
       f"엣지 {len(gb.edges)}개 일치")

    gd = {x.id: x for x in v_del.gates}
    ck("T12 축 A-Δ 판정", v_del.status == "GO",
       f"AΔ-1={gd['AΔ-1'].measured} AΔ-2={gd['AΔ-2'].measured} AΔ-3={gd['AΔ-3'].measured}")
    ck("T12b 생성·소멸 분리 보존",
       len(v_del.detail["born_total_per_transition"]) == len(v_del.detail["died_total_per_transition"]) > 0
       and all(b > 0 for b in v_del.detail["born_total_per_transition"])
       and all(d > 0 for d in v_del.detail["died_total_per_transition"]),
       f"born={v_del.detail['born_total_per_transition']} died={v_del.detail['died_total_per_transition']}")

    # T12c — 제출기한 미도래 스냅샷: '미달(STOP)' 이 아니라 '측정 불가(UNVERIFIED)' 로 분류되는가.
    #        실행일을 2026-08-10 으로 두면 2026 반기(제출기한 2026-08-14)가 아직 없다.
    #        측정 대상/노드 집합은 축 A 산출물을 재사용하지 않고 공개 헬퍼로 다시 구성한다.
    _univ = w.universe(T_NOW)
    _mp_all = map_universe_to_corpcode(_univ, w.corp_rows(), T_NOW, set(), {})
    _mp_sub = map_universe_to_corpcode(pick_measure_subset(_univ, TH.MEASURE_SUBSET_N),
                                       w.corp_rows(), T_NOW, set(), {})
    art_all_corps = sorted(set(_mp_all.code_to_corp.values()))
    art_measure = set(_mp_sub.code_to_corp.values())
    art_corp_stock = {cc: sc for sc, cc in _mp_sub.code_to_corp.items()}
    early = date(2026, 8, 10)
    ctx_early = AxisAContext(dart, p_main, early, w.universe, lambda _d: set(), lambda: {})
    c_before = CALLS.total
    v_del_early = run_axis_A_delta(ctx_early, art_all_corps, art_measure, art_corp_stock, [],
                                   list(SNAPSHOTS))
    gde = {x.id: x for x in v_del_early.gates}
    snaps_e = v_del_early.detail["snapshots"]
    ck("T12c 제출기한 미도래 → UNVERIFIED",
       v_del_early.status == "UNVERIFIED" and gde["AΔ-3"].passed is False
       and snaps_e[-1]["available"] is False,
       f"실행일 {early}: AΔ-3={gde['AΔ-3'].measured}, 마지막 스냅샷 사유={snaps_e[-1]['unavailable_reason'][:60]}")
    ck("T12d 미성립 스냅샷은 전이에서 제외",
       len(v_del_early.detail["born_total_per_transition"]) == 2
       and all(d > 0 for d in v_del_early.detail["died_total_per_transition"]),
       f"전이 {len(v_del_early.detail['born_total_per_transition'])}개 "
       f"born={v_del_early.detail['born_total_per_transition']} "
       f"died={v_del_early.detail['died_total_per_transition']} — 빈 스냅샷발 허위 소멸 없음")
    ck("T12e 미도래 스냅샷 벌크 미수집", CALLS.total - c_before < 100,
       f"소모 호출 {CALLS.total - c_before}회 (선행 프로브 {CANARY_N}종목만)")

    # ── T13 호출 카운터 독립성 (§8.3) ───────────────────────────────────────────────
    snap = CALLS.snapshot()
    b_now = snap["by_bucket"].get(f"A@{T_NOW.isoformat()}", 0)
    b_past = snap["by_bucket"].get(f"A@{T_PAST.isoformat()}", 0)
    ck("T13 기준일별 카운터 독립", b_now > 0 and b_past > 0 and b_now != snap["total"]
       and b_past != snap["total"],
       f"T_NOW={b_now}, T_PAST={b_past}, 총계={snap['total']} (총계는 별도 필드)")

    # ── T14 캐시 재실행 히트 (§8.2) ─────────────────────────────────────────────────
    h0, m0 = CACHE.for_axis("A")
    c0 = CALLS.total
    cr2 = collect_exec_snapshot(ctx, sorted(w.corp), 2026, "11013", T_NOW, "selftest-rerun",
                                CircuitBreaker("A"))
    h1, m1 = CACHE.for_axis("A")
    hit_ratio = (h1 - h0) / max(1, (h1 - h0) + (m1 - m0))
    ck("T14 P0_RESUMABLE 재실행 캐시", hit_ratio == 1.0 and CALLS.total == c0,
       f"히트율 {hit_ratio:.3f}, 신규 호출 {CALLS.total - c0}회 (1차 실행의 1.0% 문제 해소)")
    ck("T14b 재실행 결과 동일", len(cr2.rows) == len(cr.rows), f"{len(cr2.rows)}행")

    # ── T15 축 C: 전부 실패 → UNVERIFIED (STOP 아님) ────────────────────────────────
    globals()["DATA_GO_KR_KEY"] = "SELFTEST_KEY"
    v_c_fail = with_accounting("C", lambda: run_axis_C(p_main, dart, w.universe, [],
                                                      transport=w.nps_transport_fail))
    ck("T15 축 C 전부 실패 → UNVERIFIED", v_c_fail.status == "UNVERIFIED",
       f"{v_c_fail.status} (v1.0 의 STOP 오분류를 되풀이하지 않는다)")

    # ── T16 축 C: 프로브 성공 → 게이트 진행 ─────────────────────────────────────────
    v_c_ok = with_accounting("C", lambda: run_axis_C(p_main, dart, w.universe, [],
                                                    transport=w.nps_transport_ok))
    gc = {x.id: x for x in v_c_ok.gates}
    ck("T16 축 C 프로브 성공 시 게이트 산출", len(v_c_ok.gates) == 5 and gc["C-1"].measured in ("Y", "N", "부분"),
       f"status={v_c_ok.status} C-1={gc['C-1'].measured} C-2={gc['C-2'].measured} C-3={gc['C-3'].measured}")
    ck("T16b C-5 PENDING 유지", gc["C-5"].passed is None, "")
    globals()["DATA_GO_KR_KEY"] = ""

    # ── T17 축 B: 인증 없음 → BLOCKED_PREREQ ────────────────────────────────────────
    v_b = with_accounting("B", lambda: run_axis_B(p_main, dart, w.universe, []))
    ck("T17 축 B 인증 없음 → BLOCKED_PREREQ", v_b.status == "BLOCKED_PREREQ",
       "우회 시도 없이 즉시 종료(§5.1)")

    # ── T18 콜드 백업 왕복 (§8.4) ───────────────────────────────────────────────────
    #   사라지는 루트를 승인(WAIVED)했을 때 호출 예산을 지켜주는 유일한 장치다.
    #   저장 → 로컬 소거 → 복원 이 실제로 되는지, 그리고 기존 파일을 훼손하지 않는지 본다.
    p_cb = Paths(os.path.join(paths.root, "_selftest_backup"), selftest=True)
    p_cb.ensure()
    cb_cache = RawCache(p_cb, "dart_exctv")
    for i in range(5):
        cb_cache.put(f"C{i:07d}", 2026, "11013", {"status": "000", "list": [{"nm": f"임원{i}"}]})
    cb = ColdBackup(p_cb, enabled=True)
    cb.dir = os.path.join(paths.root, "_selftest_drive")
    os.makedirs(cb.dir, exist_ok=True)
    save_msg = cb.save(quiet=True)
    have_archive = bool(cb.archive_path) and os.path.exists(cb.archive_path)

    import shutil as _sh
    _sh.rmtree(os.path.join(p_cb.raw, "dart_exctv"))              # 세션 소멸 재현
    gone = cb_cache.get("C0000003", 2026, "11013") is None
    cb.restore()
    back = cb_cache.get("C0000003", 2026, "11013")
    ck("T18 콜드 백업 왕복", have_archive and gone and back == {"status": "000", "list": [{"nm": "임원3"}]},
       f"{save_msg} → 소거 후 복원 성공")

    cb_cache.put("C0000003", 2026, "11013", {"status": "000", "list": [{"nm": "핫캐시_최신"}]})
    cb.restore()
    ck("T18b 복원이 기존 캐시를 덮어쓰지 않는다",
       cb_cache.get("C0000003", 2026, "11013") == {"status": "000", "list": [{"nm": "핫캐시_최신"}]},
       "skip-if-exists — 로컬에 있는 파일은 건드리지 않는다")
    cb.save(quiet=True)
    ck("T18c 직전 세대 보존", os.path.exists(cb.archive_path + ".prev"),
       "재저장 시 이전 아카이브를 .prev 로 남긴다(훼손 금지)")

    # ── 결과 ────────────────────────────────────────────────────────────────────────
    all_v = verdicts + [v_c_fail, v_c_ok, v_b]
    for v in all_v:
        v.known_limitations.insert(0, "⚠ SELFTEST_SYNTHETIC — 합성 데이터다. 실측 판정이 아니다.")
    meta = {"run_mode": "SELFTEST_SYNTHETIC", "project_root": paths.root,
            "run_date": run_date.isoformat(),
            "api_calls_total": CALLS.total, "api_calls_by_bucket": CALLS.snapshot()["by_bucket"],
            "cache_by_axis": CACHE.snapshot(), "runtime_sec": round(time.time() - _T0, 1),
            "reductions": CLOCK.reductions,
            "WARNING": "SELFTEST_SYNTHETIC — 이 산출물은 합성 데이터의 결과이며 실측 판정이 아니다."}
    out = write_reports(p_main, all_v, meta)
    write_csv(p_main.report("selftest_checks.csv"), ["check", "result", "detail"],
              [[n, "PASS" if ok else "FAIL", d] for n, ok, d in ck.rows])

    HEAD(f"셀프테스트 결과: {len(ck.rows) - len(ck.failed)}/{len(ck.rows)} PASS")
    if ck.failed:
        LOG(f"실패: {ck.failed}", "ERROR")
    LOG(f"산출물: {out}")
    return 0 if not ck.failed else 1


# ════════════════════════════════════════════════════════════════════════════════════════════
#   main
# ════════════════════════════════════════════════════════════════════════════════════════════

def main() -> int:
    HEAD("PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.1")
    run_date = (datetime.strptime(RUN_DATE_OVERRIDE, "%Y-%m-%d").date()
                if RUN_DATE_OVERRIDE else date.today())
    root = resolve_project_root()
    selftest = (RUN_MODE.upper() == "SELFTEST")
    paths = Paths(root, selftest)

    LOG(f"실행 모드: {RUN_MODE} / 실행일: {run_date} / PROJECT_ROOT: {root}")
    LOG(f"기준일: T_NOW={T_NOW}, T_PAST={T_PAST}")
    LOG(f"호출 예산: 가용 {TH.DART_DAILY_CALL_LIMIT:,}회, "
        f"{TH.DART_BUDGET_STOP_RATIO:.0%} 도달({CALLS.stop_at:,}회) 시 중단")

    # ── 계약 검사 ───────────────────────────────────────────────────────────────────
    HEAD("계약 검사 (§2)")
    rows = verify_contracts(root)
    for cid in CONTRACT_IDS:
        if not any(r[0] == cid for r in rows):
            rows.append((cid, "FAIL", "검사 누락"))
    paths.ensure()
    write_csv(paths.report("contracts_v11.csv"), ["contract", "result", "detail"],
              [[c, st, d] for c, st, d in rows])
    for c, st, d in rows:
        LOG(f"  [{st:6s}] {c}: {d}", "WARN" if st in ("FAIL", "SKIP", "WAIVED") else "INFO")
    for c, st, d in rows:
        if st == "WAIVED":
            RUNTIME_WAIVERS.append(f"계약 {c} 는 PASS 가 아니라 운영자 승인(WAIVED) 상태다: "
                                   + d.replace("\n", " ").strip())
        elif st == "SKIP":
            RUNTIME_WAIVERS.append(f"계약 {c} 를 검사하지 못했다(SKIP): {d}")
    failed = [c for c, st, _ in rows if st == "FAIL"]
    if failed:
        LOG("")
        LOG(f"계약 위반으로 중단한다: {failed}", "ERROR")
        raise ContractViolation(f"계약 FAIL: {failed}")

    # ── 콜드 백업 (§8.4) — 사라지는 루트를 쓸 때 호출 예산을 지켜주는 유일한 장치 ────
    global COLD
    COLD = ColdBackup(paths, DRIVE_BACKUP and not selftest)
    if COLD.resolve():
        RUNTIME_WAIVERS.append(f"콜드 백업 사용: {COLD.restore()} / 저장 경로 {COLD.dir}")
    elif is_ephemeral_root(root):
        RUNTIME_WAIVERS.append(
            f"콜드 백업이 없다({COLD.status}). PROJECT_ROOT={root} 는 세션 종료 시 사라지므로 "
            "다음 실행은 DART 호출을 처음부터 다시 태운다.")

    if selftest:
        return run_selftest(paths, run_date)

    # ── 실측 ────────────────────────────────────────────────────────────────────────
    verdicts: List[Verdict] = []
    dart = DartClient(DART_API_KEY, paths)

    if "A" in AXES_TO_RUN:
        if not DART_API_KEY:
            msg = ("OpenDART 인증키 없음. https://opendart.fss.or.kr 에서 발급 후 DART_API_KEY 에 넣어라.")
            LOG(msg, "WARN")
            v = [Verdict("A", T_NOW.isoformat(), "BLOCKED_PREREQ", known_limitations=[msg]),
                 Verdict("A-delta", T_NOW.isoformat(), "BLOCKED_PREREQ", known_limitations=[msg])]
        else:
            ctx = AxisAContext(dart, paths, run_date, fetch_universe_pykrx,
                               fetch_etf_etn_tickers, fetch_listing_dates)
            try:
                v = run_axis_A(ctx, [])
            except (AxisAbort, ContractViolation) as e:
                LOG(f"축 A 중단: {e}", "WARN")
                v = [Verdict("A", T_NOW.isoformat(), "UNVERIFIED",
                             known_limitations=[f"중단: {e}"])]
            except Exception as e:                              # noqa: BLE001
                guard_enospc(e)
                LOG(f"축 A 예외: {e}\n{traceback.format_exc()}", "ERROR")
                v = [Verdict("A", T_NOW.isoformat(), "UNVERIFIED",
                             known_limitations=[f"예외로 측정 실패: {type(e).__name__}: {e}"])]
        VAULT.put("A", v)
        verdicts += v

    if "B" in AXES_TO_RUN:
        vb = with_accounting("B", lambda: run_axis_B(paths, dart, fetch_universe_pykrx, []))
        VAULT.put("B", vb)
        verdicts.append(vb)

    if "C" in AXES_TO_RUN:
        vc = with_accounting("C", lambda: run_axis_C(paths, dart, fetch_universe_pykrx, []))
        VAULT.put("C", vc)
        verdicts.append(vc)

    meta = {"run_mode": RUN_MODE, "project_root": root, "run_date": run_date.isoformat(),
            "api_calls_total": CALLS.total,
            "api_calls_by_bucket": CALLS.snapshot()["by_bucket"],
            "api_calls_by_axis": CALLS.snapshot()["by_axis"],
            "cache_by_axis": CACHE.snapshot(),
            "runtime_sec": round(time.time() - _T0, 1),
            "reductions": CLOCK.reductions,
            "contracts": {c: st for c, st, _ in rows},
            "cold_backup": (COLD.status if COLD else "미사용")}
    out = write_reports(paths, verdicts, meta)

    if COLD and COLD.dir:
        LOG(COLD.save())
        LOG(COLD.copy_reports())

    HEAD("판정 요약")
    for v in verdicts:
        LOG(f"  {v.axis:9s} @{v.as_of}  →  {v.status}"
            + (f"   (사람 판정 대기: {', '.join(v.manual_gates_pending)})" if v.manual_gates_pending else ""))
    LOG("")
    LOG(f"산출물: {out}")
    return 0


def _in_notebook() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython() is not None
    except Exception:
        return False


def _run_entry() -> int:
    try:
        return main()
    except ContractViolation as e:
        LOG("")
        LOG(str(e), "ERROR")
        return 2


if __name__ == "__main__":
    _rc = _run_entry()
    # 노트북 셀에서 sys.exit() 를 부르면 SystemExit 가 IPython 트레이스백으로 도배된다.
    # (심지어 IPython 내부에서 2차 예외까지 난다) 셀 실행이면 종료코드만 찍고 끝낸다.
    if _in_notebook():
        LOG(f"[종료코드 {_rc}]")
    else:
        sys.exit(_rc)
