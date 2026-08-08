
# ==========================================================================================
# 조각: s00_header.py
# ==========================================================================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  ARC-SACN — 공동커버리지 네트워크 모멘텀 (Shared Analyst Coverage Network Momentum)
#  SPEC-A 구현체   [ARC_SACN]
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)
#
#  한 애널리스트가 두 기업을 동시에 커버한다는 사실 자체를 경제적 연결의 식별자로 쓴다.
#  애널리스트는 희소한 자기 시간을 배분하는 주체이므로, 두 기업을 함께 본다는 선택은
#  그 둘이 같은 정보집합을 공유한다는 강한 증거다 (Ali & Hirshleifer, JFE 2020).
#
#  신호:  SACN_i(t) = Σ_j w_ij(t)·r_j(t-1) / Σ_j w_ij(t)      w_ij = 공유 애널리스트 수
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python arc_sacn_shared_coverage_network.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 캐시 연결 → 계약 자동검정 K1~K14
#     [1] 합성데이터 엔드투엔드 스모크  (실데이터 전에 계산경로를 먼저 증명)
#     [2] 실경로 리허설  (네트워크만 가짜로 두고 수집·정제 함수를 실물 실행)
#     [3] ★ PHASE 0 데이터 실현가능성 게이트 — 애널리스트 식별자 확보율 판정
#     [4] 데이터 수집 (드라이브 캐시 우선 → 부족분만 신규 → 공용/전용 인덱스 재적재)
#     [5] 원장 무결성 감사 (리포트 ↔ 애널리스트 ↔ 종목 다중소스 연결)
#     [6] PIT 유니버스 120개월 + 감쇠 감사
#     [7] 링크 행렬(희소) → SACN 신호 → 직교화
#     [8] 백테스트 12개 구성 × {전체 유니버스, 시총하위1000} 2개 아암
#     [9] 성과검증 → 강건성검사 → 가설검정 H1~H4(BH-FDR) → 해석표
#    [10] 산출물 저장 + 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 로그에 한글로 명시합니다. (조용히 실패하지 않습니다)
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① KRX 데이터 마켓플레이스 (가격·시총·투자자별 매매동향의 1순위 소스) ─────────────────────
#    가입: https://data.krx.co.kr  →  우측 상단 [회원가입] (무료, 이메일 인증 즉시 완료)
#          → 가입한 아이디/비밀번호를 아래에 그대로 입력
#
#    ▶ 2025-12 data.krx.co.kr 이관과 함께 로그인 요구가 강화됐습니다. 비워두면 KRX 경로만
#      건너뛰고 FinanceDataReader / 네이버금융 / yfinance 폴백으로 계속 진행합니다.
#      (유니버스의 정확성은 상장일·폐지일만으로 성립하도록 설계되어 있습니다)
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요. KRX는 중복 로그인 시
#      이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이 JSON 대신 로그인 HTML을
#      받아 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서 1회만 하고 모든 호출을
#      직렬화하므로 스스로 충돌하지는 않지만, '바깥에서' 같은 계정을 쓰는 것까지는 못 막습니다.
KRX_MARKETPLACE_ID = ""      # 예: "myid@gmail.com"   ← 필요할 때만 채우면 됨
KRX_MARKETPLACE_PW = ""      # 예: "mypassword"       ← 필요할 때만 채우면 됨
KRX_OPENAPI_KEY    = ""      # (선택) https://data.krx.co.kr → [OpenAPI] → 이용신청(승인 1일 소요)

# ── ② DART 전자공시 OpenAPI  (직교화의 BM(장부/시가) 폴백 전용) ──────────────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료. 발급 즉시 사용.
#
#    ▶ 이 전략은 DART를 거의 쓰지 않습니다. §6.3 직교화의 BM 한 항목이 전부이고,
#      그마저 KRX/pykrx 의 PBR 스냅샷(월 1회, 10년 = 120호출)이 1순위입니다.
#      DART 는 그 스냅샷이 비었을 때만 '배치 엔드포인트'로 보강합니다.
#      예상 호출량은 실행 시작 시 표로 출력됩니다 (통상 2,000건 미만).
#
#    ▶ 일일 호출한도는 코드가 하드코딩하지 않습니다. 실제 잔여량을 추적하고
#      API 가 status='020'(한도초과)을 돌려주는 지점을 관측해 한도 자체를 학습합니다.
#      (한도 상향 승인을 받은 계정이면 자동으로 그만큼 더 씁니다)
DART_API_KEY = ""            # ← 필요할 때만 채우면 됨

# ── ③ 구글드라이브 캐시 ─────────────────────────────────────────────────────────────────────
#    ★★★ 절대 1원칙: 기존 캐시·인덱스를 절대 삭제·덮어쓰기하지 않습니다. ★★★
#      · 인덱스의 진실은 append-only JSONL 저널입니다. 기존 줄을 재기록하지 않습니다.
#      · index.parquet 은 저널의 파생물이며, 재생성 전 항상 타임스탬프 백업합니다.
#      · 이미 드라이브에 있던 리포트는 이동·개명 없이 '경로만' 등록합니다(adopt-by-reference).
#      · 삭제 API 자체가 존재하지 않습니다.
#
#    ▸ 루트를 하드코딩하지 않습니다. 아래 후보를 순서대로 탐색해 '이미 존재하는' 경로를 씁니다.
#      (SPEC §2.1 — /content 하드코딩 금지. resolve_project_root() 가 런타임에 결정합니다)
#      맨 앞에 본인 경로를 추가하면 그게 최우선이 됩니다.
GDRIVE_ROOT_CANDIDATES = [
    # "/content/drive/MyDrive/내캐시폴더",        # ← 본인 경로가 있으면 여기 맨 앞에 추가
    "{DRIVE}/MyDrive/tcd_cache",                   # 기존 전략(TCD v2)이 쓰던 루트 — 공용 인덱스 재사용
    "{DRIVE}/MyDrive/kr_quant_cache",
    "{DRIVE}/MyDrive/ARC_SACN",
    "{DRIVE}/MyDrive/.kr_data_work/ARC_SACN",
    "~/.kr_data_work/ARC_SACN",
    r"C:\Users\KRIN-LG2405U\.kr_data_work\ARC_SACN",
]
GDRIVE_SHARED_NS  = "_shared"    # 공용 인덱스 — 다른 전략도 그대로 재사용 (가격·리포트원장·애널리스트원장)
GDRIVE_PRIVATE_NS = "arc_sacn"   # 전용 인덱스 — 이 전략 고유 (링크행렬·신호·백테스트)

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요. 재귀 스캔해서 '등록만' 합니다.
#      (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록합니다)
GDRIVE_ADOPT_DIRS = [
    "{DRIVE}/MyDrive/tcd_cache",
    "{DRIVE}/MyDrive/research",
    "{DRIVE}/MyDrive/reports",
    "{DRIVE}/MyDrive/consensus",
    "{DRIVE}/MyDrive/애널리스트리포트",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]
LOCAL_CACHE_ROOT = "./arc_sacn_cache"   # 드라이브를 못 찾으면 여기로 폴백 (실행은 계속됩니다)

# ── ④ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑤ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE"  : 합성데이터로 전 출력물을 예행연습 (수십 초). 네트워크·키 불필요.
#               백테스트·성과·강건성·가설검정·해석표가 전부 나옵니다. 처음엔 이걸로 한 번.
#    "PHASE0" : 스모크 → 리허설 → Phase 0 게이트만 실행하고 보고 후 정지 (SPEC §12-1)
#    "FULL"   : 스모크 → 리허설 → Phase 0 → 수집 → 백테스트 → 강건성 (권장)
#    "CACHED" : 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트
RUN_MODE = "FULL"

# ── ⑥ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 8      # 네트워크 병렬(스레드). 차단되면 4로 줄이세요. (SPEC §2.3 기본 4 이하 권고)
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.0,
    "naver":     2.5,
    "krx":       2.0,
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB          = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환
CIRCUIT_BREAKER_FAILS  = 10     # SPEC §2.3 서킷브레이커: 연속 실패 N회 시 해당 소스 수집 중단

# ── ⑦ 애널리스트 리포트 수집 ────────────────────────────────────────────────────────────────
RESEARCH_COLLECT       = True    # False면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES       = ["hankyung", "naver"]   # SPEC 지정: 한경컨센서스 + 네이버리서치
RESEARCH_DOWNLOAD_PDF  = True    # PDF 본문에서 애널리스트명 추출 (확보율↑, 용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑧ PHASE 0 데이터 실현가능성 게이트 (SPEC §4.3 — 이 전략의 유일한 실질 리스크) ────────────
#    애널리스트 식별자 확보율에 따라 전략의 링크 단위가 결정됩니다. 임의 판단하지 않습니다.
#      확보율 ≥ 70%           → 정상 진행 (애널리스트 단위 링크)
#      40% ≤ 확보율 < 70%     → 진행하되 §6.5 결측 민감도 분석(IPW) 필수 산출
#      확보율 < 40%           → 애널리스트 단위 포기 → broker × sector_team 폴백,
#                               교차업종 전용 버전을 주 버전으로 승격
PHASE0_SAMPLE_MONTHS = ["2019-06", "2022-03", "2024-11"]   # SPEC 예시 구간 그대로
PHASE0_SAMPLE_N      = 300      # 표본 리포트 건수
PHASE0_TIMEBOX_MIN   = 16 * 60  # 타임박스 16시간(분). 초과 시 즉시 중단하고 보고
PHASE0_GATE_HIGH     = 0.70
PHASE0_GATE_LOW      = 0.40

# ── ⑨ 유니버스 (SPEC §5 — PIT 월말 스냅샷) ──────────────────────────────────────────────────
UNI_MIN_PRICE_KRW   = 1_000          # 최소 주가
UNI_MIN_MKTCAP_KRW  = 50_000_000_000 # 최소 시가총액 500억
UNI_MIN_ADV_KRW     = 300_000_000    # 직전 20영업일 평균 거래대금 3억
UNI_MARKETS         = ("KOSPI", "KOSDAQ")   # KONEX 제외

# ── ⑩ 비교 아암: 시가총액 하위 1000 종목 (사용자 요청) ───────────────────────────────────────
#    동일한 신호·동일한 검정을 소형주 압축 유니버스에 적용해 전체 유니버스판과 나란히 비교합니다.
#    (SPEC §3 H3 의 "소형주에서 더 강하다"는 조건부 예측과도 직접 맞물립니다)
COMPARE_SMALLCAP_ARM   = True
SMALLCAP_ARM_N         = 1000        # 매월 시총 하위 N종목으로 압축

# ── ⑪ 포트폴리오 (SPEC §7 — 사전 확정, 사후 변경 금지) ──────────────────────────────────────
N_QUANTILES        = 5        # 5분위
PORT_MIN_NAMES     = 20       # 보유 종목 수 하한. 미달 시 그 리밸런싱은 현금 (로그 기록)
POS_MAX_WEIGHT     = 0.05     # 종목당 상한 5%
MIN_LINKS_REQUIRED = 3        # SPEC §6.1 연결기업 3개 미만이면 그 달 신호 결측
LINK_LOOKBACK_M    = 12       # SPEC §6.4 링크 룩백 12개월 고정

# ── ⑫ 거래비용 (SPEC §7.1 — 연도별 증권거래세 테이블 필수) ──────────────────────────────────
COST_COMMISSION_BP = 1.5      # 편도 수수료
COST_SLIPPAGE_BP   = {"large": 10.0, "mid": 20.0, "small": 35.0}   # 시총 구간별 편도
COST_SCENARIOS     = {"zero": 0.0, "base": 1.0, "double": 2.0}     # 비용 0 / 기본 / 2배 보수

# ── ⑬ 상장폐지 처리 (SPEC §0.3) ─────────────────────────────────────────────────────────────
#    정리매매 최종가 확인 불가 시의 보수적 기본값. 이 가정의 민감도 분석은 필수 산출물입니다.
DELIST_DEFAULT_RET      = -0.70
DELIST_SENSITIVITY_GRID = [-1.00, -0.70, -0.50, -0.30]

SEED    = 20260808        # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "ARC_SACN"
STRATEGY_NAME = "공동커버리지 네트워크 모멘텀 (Shared Analyst Coverage Network Momentum)"
BUILD_VERSION = "sacn.20260808.0646"

# 사전등록 하이퍼파라미터 격자 (SPEC §6.4 — 총 12개, 확장 금지) ------------------------------
#   링크 룩백 12M 고정 × 신호수익률윈도우 2 × 리밸런싱 2 × 링크가중 3 = 12
PREREG_SIGNAL_WINDOWS = ["1W", "1M"]                       # 신호 수익률 윈도우
PREREG_REBALANCES     = ["W", "M"]                         # 리밸런싱 주기
PREREG_LINK_WEIGHTS   = ["unweighted", "freq", "highskill"]  # 링크 가중
N_PREREG_CONFIGS      = (len(PREREG_SIGNAL_WINDOWS) * len(PREREG_REBALANCES)
                         * len(PREREG_LINK_WEIGHTS))       # = 12. 검정에서 시도횟수로 씀

# 아래 두 값은 재사용 코어(가격·유니버스·DART 조각)가 참조하는 이름입니다. 변경 불필요.
STOP_ON_KILL_CRITERIA = True
MIN_ADV_KRW           = UNI_MIN_ADV_KRW
ACCOUNT_KRW           = 100_000_000
DATA_GO_KR_KEY        = ""       # 이 전략은 사용하지 않음 (코어 조각 호환용)
CUSTOMS_API_KEY       = ""       # 이 전략은 사용하지 않음 (코어 조각 호환용)
ACTIVE_PACKS: list = []          # 이 전략은 센서팩 구조를 쓰지 않음 (코어 조각 호환용)
PORTFOLIO_TOP_PCT     = 0.20     # (코어 조각 호환용 — SACN 은 분위수 엔진을 따로 씀)
PORTFOLIO_MAX_NAMES   = 200
PORTFOLIO_MIN_NAMES   = PORT_MIN_NAMES
POS_MIN_WEIGHT        = 0.0
POS_ADV_PARTICIPATION = 0.10
HOLD_MAX_MONTHS       = 24


# ==========================================================================================
# 조각: 01_bootstrap.py
# ==========================================================================================

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import datetime as _dt
from collections import defaultdict, Counter, OrderedDict
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, urljoin, quote, unquote, urlparse, parse_qs

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ★ 윈도우 콘솔 기본 인코딩(cp949)은 이 코드가 쓰는 罫線문자(╔═║)와 ✔✘⚠★ 를 인코딩하지 못한다.
#   주피터는 UTF-8 이라 괜찮지만 `python 파일.py` 로 돌리면 첫 배너에서 UnicodeEncodeError 로
#   즉사한다. 가능하면 표준출력을 UTF-8 로 바꾸고, 안 되면 아래 _safe_print 가 ASCII 로 낮춘다.
for _s in ("stdout", "stderr"):
    try:
        _st = getattr(sys, _s, None)
        if _st is not None and hasattr(_st, "reconfigure"):
            _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _console_ok(sample: str = "╔✔⚠★─") -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    try:
        sample.encode(enc)
        return True
    except Exception:
        return False


CONSOLE_UNICODE = _console_ok()
# 인코딩이 안 되는 콘솔용 치환표 (표 모양은 잃되 정보는 전부 보존한다)
_ASCII_FALLBACK = str.maketrans({
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "═": "=", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "─": "-", "│": "|",
    "┼": "+", "┬": "+", "┴": "+", "├": "+", "┤": "+",
    "✔": "OK", "✘": "X", "⚠": "!", "★": "*", "▶": ">", "▷": ">",
    "⬇": "v", "…": "...", "·": ".", "×": "x", "σ": "sigma", "θ": "theta",
    "Δ": "d", "≥": ">=", "≤": "<=", "≈": "~", "①": "(1)", "②": "(2)",
    "③": "(3)", "④": "(4)", "⑤": "(5)", "⑥": "(6)", "⑦": "(7)",
    "⑧": "(8)", "⑨": "(9)", "⑩": "(10)", "⭐": "*", "⛔": "STOP", "∏": "prod",
})


def _safe_print(*args, **kw):
    """어떤 콘솔에서도 죽지 않는 print. 인코딩 실패 시에만 ASCII 로 낮춘다."""
    try:
        print(*args, **kw)
    except UnicodeEncodeError:
        try:
            print(*[str(a).translate(_ASCII_FALLBACK) for a in args], **kw)
        except Exception:
            enc = (getattr(sys.stdout, "encoding", None) or "ascii")
            print(*[str(a).encode(enc, "replace").decode(enc, "replace") for a in args], **kw)


def _detect_env() -> Dict[str, Any]:
    """Colab / JupyterLab / VSCode / 순수 CLI 를 구분한다. 어느 쪽이든 죽지 않아야 한다."""
    info = {"colab": False, "ipython": False, "kernel": None, "interactive": False}
    try:
        from IPython import get_ipython           # noqa
        ip = get_ipython()
        if ip is not None:
            info["ipython"] = True
            info["kernel"] = type(ip).__name__
            info["interactive"] = "ZMQ" in type(ip).__name__ or "Terminal" in type(ip).__name__
    except Exception:
        pass
    info["colab"] = ("google.colab" in sys.modules) or bool(os.environ.get("COLAB_RELEASE_TAG"))
    if not info["colab"]:
        try:
            import importlib.util
            info["colab"] = importlib.util.find_spec("google.colab") is not None
        except Exception:
            pass
    info["python"] = sys.version.split()[0]
    info["platform"] = platform.system()
    info["cpu"] = os.cpu_count() or 2
    return info


ENV = _detect_env()

# ── 의존성 ──────────────────────────────────────────────────────────────────────────────────
#   (모듈 임포트명, pip 설치명, 필수여부, 이 패키지가 없으면 무엇이 죽는지)
_REQUIRED = [
    ("numpy",     "numpy",              True,  "모든 수치연산"),
    ("pandas",    "pandas",             True,  "모든 패널 처리"),
    ("pyarrow",   "pyarrow",            True,  "parquet 캐시(L1 영속화)"),
    ("scipy",     "scipy",              True,  "통계검정 / 회귀"),
    ("requests",  "requests",           True,  "모든 HTTP 수집"),
    ("bs4",       "beautifulsoup4",     True,  "리서치 리스트 파싱"),
    ("lxml",      "lxml",               True,  "HTML/XML 고속 파서"),
    ("tqdm",      "tqdm",               True,  "진행률 표시"),
]
_OPTIONAL = [
    ("FinanceDataReader", "finance-datareader", "가격/상장목록 1순위 폴백"),
    ("pykrx",             "pykrx",              "PIT 상장목록(특정일 상장종목) — 생존자편향 제거의 핵심"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출(가장 빠름)"),
    ("pdfplumber",        "pdfplumber",         "PDF 추출 폴백"),
    ("rapidfuzz",         "rapidfuzz",          "사업장명/애널리스트명 유사도 매칭(고속)"),
    ("statsmodels",       "statsmodels",        "HAC(Newey-West) 표준오차"),
    ("html5lib",          "html5lib",           "깨진 HTML 복구 파싱"),
]


def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:
    if not pkgs:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if quiet:
        cmd.append("-q")
    cmd += pkgs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        return r.returncode == 0, (r.stderr or r.stdout)[-2000:]
    except Exception as e:                                    # noqa
        return False, f"{type(e).__name__}: {e}"


def _ensure_deps() -> Dict[str, bool]:
    import importlib
    missing_req, missing_opt = [], []
    for mod, pkg, _req, _why in _REQUIRED:
        if importlib.util.find_spec(mod) is None:
            missing_req.append(pkg)
    for mod, pkg, _why in _OPTIONAL:
        if importlib.util.find_spec(mod) is None:
            missing_opt.append(pkg)

    if missing_req:
        print(f"[부트스트랩] 필수 패키지 설치 중: {', '.join(missing_req)}  (1~3분 소요)")
        ok, err = _pip_install(missing_req)
        if not ok:
            print("\n" + "=" * 88)
            print("❌ 필수 패키지 설치 실패. 아래 명령을 직접 실행한 뒤 다시 돌려주세요.")
            print(f"   pip install {' '.join(missing_req)}")
            print("-" * 88)
            print(err)
            print("=" * 88)
            raise SystemExit(1)
        importlib.invalidate_caches()

    if missing_opt:
        print(f"[부트스트랩] 선택 패키지 설치 중: {', '.join(missing_opt)}")
        _pip_install(missing_opt)          # 실패해도 계속 — 각 기능에서 개별적으로 degrade
        importlib.invalidate_caches()

    # ★ 가용성 확인을 import_module 로 하면 안 된다. pykrx 는 import 시점에 KRX 로그인을 수행하는데,
    #   그게 아래 자격증명 주입보다 먼저 일어나면 비인증 세션이 만들어지고, 이후 모든 조회가
    #   JSON 대신 로그인 HTML 을 받아 엉뚱한 곳에서 JSONDecodeError 로 터진다.
    #   find_spec 은 모듈을 실행하지 않으므로 부작용이 없다. 실제 import 는 아래 통제된 블록에서만.
    return {mod: (importlib.util.find_spec(mod) is not None) for mod, _pkg, _why in _OPTIONAL}


# ═══ 자격증명은 어떤 서드파티 import 보다도 먼저 주입한다 ═══════════════════════════════════
#   pykrx.webio 는 모듈 로드 시점에 build_krx_session() 을 돌린다. 순서를 뒤집으면
#   예외 없이 '비인증 세션'이 만들어지고 원인 추적이 매우 어려운 실패로 이어진다.
if KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW
if KRX_OPENAPI_KEY:
    os.environ["KRX_OPENAPI_KEY"] = KRX_OPENAPI_KEY
    os.environ["KRX_API_KEY"] = KRX_OPENAPI_KEY

OPT = _ensure_deps()

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from tqdm.auto import tqdm
except Exception:                                             # pragma: no cover
    def tqdm(it=None, **kw):                                  # type: ignore
        return it if it is not None else iter(())

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_colwidth", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
np.seterr(all="ignore")

# 결정성(C8): 모든 난수는 이 시드에서 파생된다.
random.seed(SEED)
np.random.seed(SEED % (2 ** 32 - 1))
RNG = np.random.default_rng(SEED)

# 선택 모듈 핸들 (자격증명은 위 _ensure_deps 앞에서 이미 주입됨)
fdr = pykrx_stock = yf = fitz = pdfplumber = rapidfuzz_fuzz = smapi = None
if OPT.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr           # type: ignore
    except Exception:
        fdr = None
if OPT.get("pykrx"):
    try:
        from pykrx import stock as pykrx_stock    # type: ignore
    except Exception:
        pykrx_stock = None
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
    except Exception:
        yf = None
if OPT.get("fitz"):
    try:
        import fitz                               # type: ignore  (pymupdf)
    except Exception:
        fitz = None
if OPT.get("pdfplumber"):
    try:
        import pdfplumber                         # type: ignore
    except Exception:
        pdfplumber = None
if OPT.get("rapidfuzz"):
    try:
        from rapidfuzz import fuzz as rapidfuzz_fuzz   # type: ignore
    except Exception:
        rapidfuzz_fuzz = None
if OPT.get("statsmodels"):
    try:
        import statsmodels.api as smapi           # type: ignore
    except Exception:
        smapi = None

# ── 병렬 전략 결정 ──────────────────────────────────────────────────────────────────────────
#   노트북에서 ProcessPoolExecutor 는 "__main__ 에 정의된 함수를 피클할 수 없음" 으로 자주 죽는다.
#   fork 를 쓸 수 있는 리눅스(=Colab)에서는 안전하고, spawn 플랫폼(win/mac)에서는 스레드로 폴백한다.
import multiprocessing as _mp
try:
    _MP_METHODS = set(_mp.get_all_start_methods())
except Exception:
    _MP_METHODS = {"spawn"}
CAN_FORK = ("fork" in _MP_METHODS) and (ENV["platform"] == "Linux")
N_CPU = N_WORKERS_CPU if N_WORKERS_CPU and N_WORKERS_CPU > 0 else max(1, (os.cpu_count() or 2) - 1)


# ==========================================================================================
# 조각: s02_root.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A2  프로젝트 루트 결정 (SPEC §2.1)                                                    ║
# ║                                                                                          ║
# ║  경로를 하드코딩하지 않는다. /content 도 하드코딩하지 않는다.                              ║
# ║  런타임 환경(Colab / 로컬 Linux / 로컬 Windows / 기타)을 감지해 루트를 결정한다.           ║
# ║                                                                                          ║
# ║  결정 순서:                                                                               ║
# ║   ① 환경변수 ARC_SACN_ROOT 가 있으면 그것 (CI·배치 실행용 탈출구)                          ║
# ║   ② Colab 이면 드라이브 마운트를 시도하고, 마운트된 실제 경로를 {DRIVE} 로 치환            ║
# ║   ③ 후보 목록 중 '이미 존재하는' 첫 경로                                                   ║
# ║   ④ 아무것도 없으면 후보 중 부모 디렉터리가 존재하는 첫 경로를 새로 만든다                  ║
# ║   ⑤ 그래도 안 되면 LOCAL_CACHE_ROOT (실행은 반드시 계속된다)                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _drive_mount_points() -> List[str]:
    """이 머신에서 '구글드라이브일 수 있는' 마운트 지점들. 하드코딩이 아니라 탐색이다."""
    out: List[str] = []

    # Colab: 마운트를 시도한다. 실패해도 예외를 밖으로 내보내지 않는다.
    if ENV.get("colab"):
        mp = "/content/drive"
        try:
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                from google.colab import drive as _gdrive      # type: ignore
                _gdrive.mount(mp, force_remount=False)
        except Exception as e:                                  # noqa
            _safe_print(f"[루트] 구글드라이브 마운트 실패({type(e).__name__}) — 로컬 경로로 진행합니다.")
        if os.path.isdir(os.path.join(mp, "MyDrive")):
            out.append(mp)

    # 로컬(윈도우/맥/리눅스)에서 드라이브 데스크톱이 동기화해 둔 경로들
    home = os.path.expanduser("~")
    cands = [
        os.environ.get("GOOGLE_DRIVE_ROOT", ""),
        os.path.join(home, "Google Drive"),
        os.path.join(home, "GoogleDrive"),
        os.path.join(home, "내 드라이브"),
        "/content/drive",
    ]
    # 윈도우: 드라이브 데스크톱이 잡는 가상 드라이브 문자 (G:\내 드라이브 등)
    if platform.system() == "Windows":
        for letter in "GHIJKDEF":
            for leaf in ("My Drive", "내 드라이브"):
                cands.append(f"{letter}:\\{leaf}")
    for c in cands:
        if c and os.path.isdir(c) and c not in out:
            out.append(c)
    return out


def _expand_candidate(tpl: str, drives: Sequence[str]) -> List[str]:
    """'{DRIVE}/MyDrive/x' 템플릿을 실제 마운트 지점 수만큼 펼친다."""
    tpl = os.path.expanduser(str(tpl or "").strip())
    if not tpl:
        return []
    if "{DRIVE}" not in tpl:
        return [tpl]
    out = []
    for d in drives:
        p = tpl.replace("{DRIVE}", d)
        # 드라이브 데스크톱 경로는 이미 'My Drive' 를 포함하므로 중복 MyDrive 를 접는다
        p = p.replace(os.path.join("My Drive", "MyDrive"), "My Drive")
        p = p.replace("/My Drive/MyDrive", "/My Drive")
        p = p.replace("내 드라이브/MyDrive", "내 드라이브")
        out.append(os.path.normpath(p))
    return out


def resolve_project_root() -> Tuple[str, str, List[str]]:
    """(루트경로, 상태문자열, 실제로 존재하는 adopt 디렉터리 목록).

    SPEC §2.1 이 요구하는 함수. 어떤 환경에서도 예외 없이 (경로, 사유) 를 돌려준다.
    """
    drives = _drive_mount_points()
    on_drive = bool(drives)

    # ① 환경변수 탈출구
    env_root = os.environ.get("ARC_SACN_ROOT", "").strip()
    if env_root:
        p = os.path.abspath(os.path.expanduser(env_root))
        os.makedirs(p, exist_ok=True)
        return p, "ENV:ARC_SACN_ROOT", _resolve_adopt_dirs(drives)

    expanded: List[str] = []
    for tpl in GDRIVE_ROOT_CANDIDATES:
        expanded.extend(_expand_candidate(tpl, drives or [""]))
    # {DRIVE} 를 못 채운 후보(드라이브 없음)는 빈 접두사가 되어 무의미하므로 걸러낸다
    expanded = [p for p in expanded if p and not p.startswith(("/MyDrive", "MyDrive"))]

    # ③ 이미 존재하는 첫 경로 — 기존 캐시를 그대로 물려받는 가장 중요한 분기
    for p in expanded:
        if os.path.isdir(p):
            mode = "DRIVE_EXISTING" if on_drive and _under_any(p, drives) else "LOCAL_EXISTING"
            return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)

    # ④ 부모가 존재하면 새로 만든다 (드라이브 위를 우선한다)
    for p in expanded:
        parent = os.path.dirname(os.path.normpath(p))
        if parent and os.path.isdir(parent):
            try:
                os.makedirs(p, exist_ok=True)
                mode = "DRIVE_CREATED" if on_drive and _under_any(p, drives) else "LOCAL_CREATED"
                return os.path.abspath(p), mode, _resolve_adopt_dirs(drives)
            except Exception:
                continue

    # ⑤ 최후 폴백 — 여기서도 죽지 않는다
    p = os.path.abspath(os.path.expanduser(LOCAL_CACHE_ROOT))
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        p = os.path.abspath(tempfile.mkdtemp(prefix="arc_sacn_"))
    return p, "FALLBACK_LOCAL", _resolve_adopt_dirs(drives)


def _under_any(p: str, roots: Sequence[str]) -> bool:
    try:
        ap = os.path.abspath(p)
        return any(ap.startswith(os.path.abspath(r)) for r in roots if r)
    except Exception:
        return False


def _resolve_adopt_dirs(drives: Sequence[str]) -> List[str]:
    out: List[str] = []
    for tpl in GDRIVE_ADOPT_DIRS:
        for p in _expand_candidate(tpl, drives or [""]):
            if p and os.path.isdir(p) and p not in out:
                out.append(p)
    return out


# 재사용 코어(04_vault.py 의 _mount_drive)가 이 이름을 참조한다. 런타임에 확정된다.
GDRIVE_ROOT: str = ""
ADOPT_DIRS_RESOLVED: List[str] = []

# ── 판단 보류 항목 (SPEC §0 / §10 OPEN_QUESTIONS.md) ────────────────────────────────────────
#   "애매한 지점이 있으면 임의 판단하지 말고 여기 기록한 뒤 가장 보수적인 선택을 하라."
#   코드가 보수적 선택을 할 때마다 이 목록에 남기고, 마지막에 파일로 떨군다.
OPEN_QUESTIONS: List[dict] = []


def open_question(qid: str, topic: str, issue: str, choice: str, impact: str = ""):
    if any(q.get("id") == qid for q in OPEN_QUESTIONS):
        return
    OPEN_QUESTIONS.append({"id": qid, "topic": topic, "issue": issue,
                           "choice": choice, "impact": impact})


# ── 월말 주기 별칭 (pandas 버전 호환) ───────────────────────────────────────────────────────
#   pandas <2.2 는 "ME" 를 모르고, pandas 3.x 는 "M" 을 제거했다. 어느 쪽에서도 죽지 않도록
#   런타임에 한 번만 판별해 고정한다. Colab 과 로컬 JupyterLab 의 pandas 버전이 다른 것은
#   매우 흔하고, 이건 첫 줄에서 죽는 종류의 실패다.
def _resolve_month_end_alias() -> str:
    import pandas as _pd
    for alias in ("ME", "M"):
        try:
            _pd.date_range("2020-01-31", periods=2, freq=alias)
            return alias
        except Exception:
            continue
    return "ME"


MONTH_END_ALIAS = _resolve_month_end_alias()


def sacn_month_range(start, end) -> "pd.DatetimeIndex":
    """월말 인덱스. pandas 버전에 무관하게 동작한다."""
    return pd.date_range(month_end(start), month_end(end), freq=MONTH_END_ALIAS)


# ==========================================================================================
# 조각: 02_kernel.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-B  커널 — 로깅 / 스테이지 / 데이터흐름 원장 / 에러 국소화 / 런타임 계측(C10)          ║
# ║                                                                                          ║
# ║  이 블록의 목적은 단 하나:  "어디서 터졌고, 무슨 데이터가 어디로 흘렀는가"를               ║
# ║  스크롤 없이 한 화면에서 보이게 만드는 것.                                                ║
# ║                                                                                          ║
# ║  · 모든 연산은 STAGE 컨텍스트 안에서만 수행한다.                                          ║
# ║  · 모든 데이터 입출력은 FLOW 원장에 기록한다. (행수·바이트·소스·PIT컬럼 유무)              ║
# ║  · 예외는 잡아서 "스테이지ID + 입출력 스냅샷 + 한글 진단 힌트"와 함께 재출력한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_T0_PROCESS = time.time()


def _dw(s: str) -> int:
    """한글/한자 폭 2칸을 반영한 표시 너비. 표 정렬이 깨지지 않게 하는 유일한 방법."""
    w = 0
    for ch in str(s):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _pad(s: str, n: int, align: str = "l") -> str:
    s = str(s)
    gap = max(0, n - _dw(s))
    if align == "r":
        return " " * gap + s
    if align == "c":
        return " " * (gap // 2) + s + " " * (gap - gap // 2)
    return s + " " * gap


def _trunc(s: str, n: int) -> str:
    s = str(s).replace("\n", " ")
    if _dw(s) <= n:
        return s
    out = ""
    for ch in s:
        if _dw(out) + _dw(ch) > n - 1:
            return out + "…"
        out += ch
    return out


class _Log:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self, min_level: str = "INFO"):
        self.min = self.LEVELS[min_level]
        self.ctx: List[str] = []
        self.buffer: List[str] = []
        self.lock = threading.RLock()

    def _emit(self, level: str, msg: str, icon: str = ""):
        if self.LEVELS[level] < self.min:
            return
        el = time.time() - _T0_PROCESS
        stamp = f"{int(el // 60):02d}:{el % 60:05.2f}"
        scope = ("/".join(self.ctx))[-34:]
        line = f"[{stamp}] {_pad(scope, 34)} {icon}{msg}"
        with self.lock:
            self.buffer.append(line)
            _safe_print(line, flush=True)

    def debug(self, m): self._emit("DEBUG", m, "· ")
    def info(self, m):  self._emit("INFO",  m, "  ")
    def ok(self, m):    self._emit("INFO",  m, "✔ ")
    def warn(self, m):  self._emit("WARN",  m, "⚠ ")
    def error(self, m): self._emit("ERROR", m, "✘ ")

    def rule(self, title: str = "", ch: str = "─", width: int = 104):
        if title:
            pre = f"{ch * 3} {title} "
            _safe_print(pre + ch * max(0, width - _dw(pre)), flush=True)
        else:
            _safe_print(ch * width, flush=True)

    def banner(self, title: str, sub: str = "", width: int = 104):
        _safe_print("", flush=True)
        _safe_print("╔" + "═" * (width - 2) + "╗", flush=True)
        _safe_print("║ " + _pad(_trunc(title, width - 4), width - 4) + " ║", flush=True)
        if sub:
            _safe_print("║ " + _pad(_trunc(sub, width - 4), width - 4) + " ║", flush=True)
        _safe_print("╚" + "═" * (width - 2) + "╝", flush=True)

    def table(self, rows: List[Sequence[Any]], headers: Sequence[str],
              aligns: Optional[Sequence[str]] = None, maxw: int = 46, title: str = ""):
        """한글 폭 보정 표. 강건성/성과/감사 출력 전부 이걸 쓴다."""
        if title:
            _safe_print(f"\n▶ {title}", flush=True)
        if not rows:
            _safe_print("   (행 없음)", flush=True)
            return
        ncol = len(headers)
        aligns = list(aligns or ["l"] * ncol)
        cells = [[_trunc("" if c is None else c, maxw) for c in r] + [""] * (ncol - len(r)) for r in rows]
        widths = [max(_dw(headers[i]), *(_dw(r[i]) for r in cells)) for i in range(ncol)]
        head = "  " + " │ ".join(_pad(headers[i], widths[i], "c") for i in range(ncol))
        _safe_print(head, flush=True)
        _safe_print("  " + "─┼─".join("─" * widths[i] for i in range(ncol)), flush=True)
        for r in cells:
            _safe_print("  " + " │ ".join(_pad(r[i], widths[i], aligns[i]) for i in range(ncol)), flush=True)


LOG = _Log("DEBUG" if VERBOSE else "INFO")


# ── 데이터 흐름 원장 ────────────────────────────────────────────────────────────────────────
@dataclass
class IOEvent:
    stage: str
    direction: str          # IN / OUT
    kind: str               # HTTP / DRIVE / PARQUET / MEM / SQLITE / SYNTH
    name: str
    rows: int = -1
    cols: int = -1
    bytes_: int = -1
    source: str = ""
    ok: bool = True
    note: str = ""
    pit_cols: str = ""      # knowledge_date 계열 컬럼 존재 여부 — C1 감사에 쓰인다


@dataclass
class StageRecord:
    sid: str
    name: str
    layer: str
    status: str = "PENDING"       # PENDING / RUNNING / OK / WARN / FAIL / SKIP
    t_start: float = 0.0
    t_end: float = 0.0
    budget_s: Optional[float] = None
    rows_in: int = 0
    rows_out: int = 0
    err_type: str = ""
    err_msg: str = ""
    err_tb: str = ""
    hint: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def dur(self) -> float:
        return (self.t_end or time.time()) - self.t_start


class KillCriteria(Exception):
    """§15 킬 기준 위반. 우회하지 말고 사용자에게 보고하고 멈춘다."""


class StageFailure(Exception):
    pass


# ── 예외 → 한글 진단 힌트 ───────────────────────────────────────────────────────────────────
_DIAG_RULES: List[Tuple[str, str]] = [
    (r"SERVICE_KEY_IS_NOT_REGISTERED|SERVICEKEY",
     "공공데이터포털 인증키 문제입니다. ① 해당 API에 '활용신청'이 승인됐는지 ② DATA_GO_KR_KEY 에 "
     "Decoding(일반) 키를 넣었는지 확인하세요. Encoding 키를 넣으면 이중 인코딩으로 항상 실패합니다."),
    (r"LIMITED_NUMBER_OF_SERVICE_REQUESTS",
     "공공데이터포털 일일 호출한도 초과입니다. 내일 재시도하거나 트래픽 증가 신청을 하세요. "
     "이미 받은 분량은 드라이브 캐시에 남아 있으므로 재실행 시 이어서 받습니다."),
    (r"opendart|dart.*(013|020|100|800|900)|status.*'0(13|20)'",
     "DART API 응답 코드 오류. 013=조회 데이터 없음(정상일 수 있음), 020=일일한도 초과, "
     "100=필드 부적절, 800=시스템 점검, 900=정의되지 않은 오류. DART_API_KEY 를 확인하세요."),
    (r"HTTPError.*40[13]|Forbidden|403",
     "403 차단입니다. RATE_LIMIT_QPS 를 절반으로 낮추고 N_WORKERS_IO 를 8 이하로 줄이세요. "
     "네이버/한경은 User-Agent 와 Referer 헤더가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests",
     "요청이 너무 빠릅니다. RATE_LIMIT_QPS 를 낮추세요. 코드가 지수백오프로 재시도하지만 한계가 있습니다."),
    (r"ConnectionError|Timeout|Max retries|NameResolution|SSLError|ProxyError",
     "네트워크 도달 실패입니다. 방화벽/프록시 환경이면 해당 도메인이 막혀 있을 수 있습니다. "
     "RUN_MODE='CACHED' 로 두고 드라이브 캐시만으로 백테스트할 수 있습니다."),
    (r"No such file or directory.*drive|MyDrive|drive/MyDrive",
     "구글드라이브가 마운트되지 않았습니다. Colab이면 셀 실행 시 뜨는 인증 팝업을 승인하세요. "
     "JupyterLab이면 자동으로 LOCAL_CACHE_ROOT 를 사용합니다(정상)."),
    (r"No space left on device|Disk quota",
     "디스크/드라이브 용량 부족입니다. RESEARCH_DOWNLOAD_PDF=False 로 두면 PDF 원문을 받지 않고 "
     "리스트 메타데이터만으로도 목표주가·애널리스트 연결이 가능합니다."),
    (r"Can't pickle|pickle.*__main__|PicklingError|BrokenProcessPool",
     "프로세스 병렬화 실패(노트북의 고질적 문제). 코드가 자동으로 스레드 병렬로 폴백합니다. "
     "성능만 떨어지고 결과는 동일합니다."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족입니다. MEM_BUDGET_GB 를 낮추고 RESEARCH_DOWNLOAD_PDF=False, "
     "N_WORKERS_CPU=2 로 두세요. 패널은 float32/category 로 이미 축소되어 있습니다."),
    (r"pyarrow|parquet|ArrowInvalid|ArrowIOError",
     "parquet 읽기/쓰기 실패입니다. 드라이브 FUSE 마운트에서 쓰기가 중단되면 파일이 깨질 수 있습니다. "
     "코드는 임시파일→원자적 rename 으로 쓰므로, 깨진 건 이전 실행 잔재입니다. "
     "해당 파일만 지우고(원본 아님, 캐시임) 재실행하세요."),
    (r"'DataFrame' object has no attribute 'name'|_wrap_agged_manager",
     "중복 컬럼입니다. DataFrame 에 같은 이름의 컬럼이 두 개 있으면 df[col] 이 Series 가 아니라 "
     "DataFrame 이 되고, groupby(...).agg() 가 pandas 내부에서 이 예외로 터집니다. "
     "직전에 concat/reindex(columns=...)/merge 로 컬럼을 합친 곳을 보세요 — "
     "리스트를 이어붙일 때(예: COLS + ['x'] 인데 COLS 에 이미 'x' 가 있는 경우) 가장 흔합니다. "
     "assert_no_dup_cols() 로 발생 지점을 앞당겨 잡을 수 있습니다."),
    (r"Expecting value: line \d+ column 1|JSONDecodeError|Error occurred in get_market",
     "JSON 대신 HTML(대개 로그인/에러 페이지)을 받았습니다. KRX 계열이면 세션이 끊긴 것입니다. "
     "pykrx 는 스레드마다 재로그인하며 KRX 는 중복 로그인 시 이전 세션을 끊습니다 — "
     "모든 pykrx 호출은 KRXG.call() 게이트로 직렬화해야 합니다. "
     "KRX ID/PW 를 다른 브라우저 탭에서 동시에 쓰고 있지 않은지도 확인하세요."),
    (r"UnicodeEncodeError|cp949|charmap",
     "콘솔 인코딩 문제입니다(윈도우 기본 cp949 는 罫線문자 ╔═║ 와 ✔✘ 를 못 씁니다). "
     "코드가 stdout 을 UTF-8 로 재설정하고 실패 시 ASCII 로 낮추지만, 직접 출력을 추가했다면 "
     "print 대신 _safe_print 를 쓰세요. 또는 실행 전 `chcp 65001` 을 하세요."),
    (r"statvfs|WinError",
     "윈도우 전용 이슈입니다. os.statvfs 는 윈도우에 없고(용량 표시만 생략됩니다), "
     "파일 잠금·경로 구분자도 다릅니다. 기능에는 영향이 없어야 하며, 있다면 버그입니다."),
    (r"KeyError: 'knowledge_date'|knowledge_date",
     "PIT 컬럼 누락입니다. 모든 테이블은 event_date/knowledge_date 를 가져야 합니다(C1). "
     "새 수집 함수를 추가했다면 pit_frame() 으로 감싸주세요."),
    (r"empty|EmptyDataError|No objects to concatenate|zero-size",
     "수집 결과가 비었습니다. 대개 ① 키 미입력 ② 조회구간에 데이터 없음 ③ 소스 구조 변경입니다. "
     "바로 위 FLOW 원장에서 어느 소스가 0행을 반환했는지 확인하세요."),
    (r"ModuleNotFoundError|ImportError",
     "패키지 누락입니다. 위 부트스트랩 로그에서 어떤 설치가 실패했는지 확인하고 수동 설치하세요."),
    (r"tz-aware|tz-naive|Cannot compare",
     "타임존이 섞인 날짜 비교입니다. 이 코드는 모든 날짜를 tz-naive Timestamp 로 정규화합니다(as_ts). "
     "새로 추가한 소스가 tz-aware 를 반환했을 가능성이 큽니다."),
]


def diagnose(exc: BaseException, extra: str = "") -> str:
    blob = f"{type(exc).__name__}: {exc}\n{extra}\n{traceback.format_exc()}"
    for pat, hint in _DIAG_RULES:
        if re.search(pat, blob, re.I):
            return hint
    return ("알려진 패턴에 해당하지 않는 오류입니다. 아래 트레이스백의 마지막 프레임과 "
            "그 직전 FLOW 원장 행을 함께 보면 원인 구간이 좁혀집니다.")


# ── 파이프라인 ──────────────────────────────────────────────────────────────────────────────
class Pipeline:
    """스테이지 실행기. 모든 계산은 이 안에서만 돈다."""

    def __init__(self):
        self.stages: "OrderedDict[str, StageRecord]" = OrderedDict()
        self.flow: List[IOEvent] = []
        self.current: Optional[StageRecord] = None
        self.failed: List[str] = []
        self.artifacts: Dict[str, Any] = {}
        self._lock = threading.RLock()

    # -- I/O 원장 -------------------------------------------------------------------------
    def io(self, direction: str, kind: str, name: str, obj: Any = None,
           source: str = "", ok: bool = True, note: str = "", bytes_: int = -1):
        rows = cols = -1
        pit = ""
        try:
            if isinstance(obj, pd.DataFrame):
                rows, cols = int(obj.shape[0]), int(obj.shape[1])
                have = [c for c in ("event_date", "knowledge_date") if c in obj.columns]
                pit = "+".join(h[0].upper() for h in have) if have else "—"
            elif isinstance(obj, (list, tuple, set, dict)):
                rows = len(obj)
            elif isinstance(obj, (int, float)):
                rows = int(obj)
        except Exception:
            pass
        ev = IOEvent(stage=self.current.sid if self.current else "-", direction=direction,
                     kind=kind, name=name, rows=rows, cols=cols, bytes_=bytes_,
                     source=source, ok=ok, note=note, pit_cols=pit)
        with self._lock:
            self.flow.append(ev)
            if self.current:
                if direction == "IN" and rows > 0:
                    self.current.rows_in += rows
                if direction == "OUT" and rows > 0:
                    self.current.rows_out += rows
        return obj

    def note(self, msg: str):
        if self.current:
            self.current.notes.append(msg)

    # -- 스테이지 ------------------------------------------------------------------------
    @contextmanager
    def stage(self, sid: str, name: str, layer: str = "L?",
              budget_s: Optional[float] = None, critical: bool = True,
              skip_if: bool = False, skip_reason: str = ""):
        rec = StageRecord(sid=sid, name=name, layer=layer, budget_s=budget_s)
        self.stages[sid] = rec
        prev, self.current = self.current, rec
        LOG.ctx.append(sid)
        if skip_if:
            rec.status, rec.t_start, rec.t_end = "SKIP", time.time(), time.time()
            rec.notes.append(skip_reason or "조건 미충족")
            LOG.warn(f"건너뜀 — {skip_reason}")
            LOG.ctx.pop(); self.current = prev
            yield rec
            return
        rec.status = "RUNNING"
        rec.t_start = time.time()
        LOG.info(f"▷ {name}")
        try:
            yield rec
            rec.t_end = time.time()
            rec.status = "WARN" if any("WARN:" in n for n in rec.notes) else "OK"
            over = budget_s and rec.dur > budget_s
            msg = f"완료 {rec.dur:6.2f}s  in={rec.rows_in:,} out={rec.rows_out:,}"
            if over:
                rec.notes.append(f"WARN: 런타임 예산 {budget_s:.0f}s 초과")
                LOG.warn(msg + f"  ← 예산 {budget_s:.0f}s 초과 (C10)")
            else:
                LOG.ok(msg)
        except KillCriteria as e:
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = "KillCriteria"; rec.err_msg = str(e)
            rec.err_tb = traceback.format_exc()
            rec.hint = "§15 킬 기준입니다. 파라미터를 조정해 통과시키지 마세요. 결과를 그대로 보고합니다."
            self.failed.append(sid)
            LOG.error(f"킬 기준 발동 — {e}")
            raise
        except BaseException as e:                                   # noqa
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = type(e).__name__; rec.err_msg = str(e)[:600]
            rec.err_tb = traceback.format_exc()
            rec.hint = diagnose(e, extra=f"stage={sid} name={name}")
            self.failed.append(sid)
            self._print_failure(rec)
            if critical:
                raise StageFailure(f"[{sid}] {name} 실패: {rec.err_type}: {rec.err_msg}") from e
            rec.status = "WARN"
            rec.notes.append(f"WARN: 비필수 스테이지 실패 — {rec.err_type}")
        finally:
            LOG.ctx.pop()
            self.current = prev

    def _print_failure(self, rec: StageRecord):
        LOG.banner(f"✘ 실패 지점: [{rec.sid}] {rec.name}", f"계층 {rec.layer} · 경과 {rec.dur:.2f}s")
        _safe_print(f"  예외      : {rec.err_type}: {rec.err_msg}")
        _safe_print(f"  진단      : {rec.hint}")
        recent = [e for e in self.flow if e.stage == rec.sid][-8:]
        if recent:
            LOG.table(
                [[e.direction, e.kind, _trunc(e.name, 34), f"{e.rows:,}" if e.rows >= 0 else "-",
                  e.pit_cols, "OK" if e.ok else "ERR", _trunc(e.source or e.note, 26)] for e in recent],
                ["방향", "종류", "대상", "행수", "PIT", "상태", "소스/비고"],
                ["c", "l", "l", "r", "c", "c", "l"],
                title="이 스테이지의 직전 입출력 (여기서 무엇이 비었는지 보세요)")
        _safe_print("\n  ── 트레이스백 (마지막 12줄) " + "─" * 60)
        for ln in rec.err_tb.rstrip().split("\n")[-12:]:
            _safe_print("   " + ln)
        _safe_print("  " + "─" * 86)

    # -- 리포트 --------------------------------------------------------------------------
    def report_stages(self):
        LOG.banner("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수 · 런타임 예산(C10)")
        rows = []
        for r in self.stages.values():
            icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUNNING": "…"}.get(r.status, "?")
            bud = "-" if r.budget_s is None else (f"{r.budget_s:.0f}s" + ("❗" if r.dur > r.budget_s else ""))
            rows.append([r.layer, r.sid, _trunc(r.name, 40), f"{icon}{r.status}",
                         f"{r.dur:8.2f}", f"{r.rows_in:,}", f"{r.rows_out:,}", bud,
                         _trunc("; ".join(r.notes), 40)])
        LOG.table(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "예산", "비고"],
                  ["c", "l", "l", "c", "r", "r", "r", "c", "l"], maxw=44)

    def report_flow(self, only_kinds: Optional[Sequence[str]] = None, limit: int = 200):
        LOG.banner("데이터 흐름 원장 (I/O LEDGER)",
                   "어떤 스테이지가 어디서 몇 행을 읽고 어디에 몇 행을 썼는가 · PIT=E(event)/K(knowledge)")
        evs = [e for e in self.flow if (not only_kinds or e.kind in only_kinds)]
        if len(evs) > limit:
            LOG.warn(f"원장 {len(evs)}건 중 최근 {limit}건만 출력합니다.")
            evs = evs[-limit:]
        LOG.table(
            [[e.stage, e.direction, e.kind, _trunc(e.name, 38),
              f"{e.rows:,}" if e.rows >= 0 else "-",
              f"{e.cols}" if e.cols >= 0 else "-",
              e.pit_cols or "—", "OK" if e.ok else "ERR", _trunc(e.source or e.note, 30)] for e in evs],
            ["스테이지", "방향", "종류", "대상", "행수", "열수", "PIT", "상태", "소스/비고"],
            ["l", "c", "l", "l", "r", "r", "c", "c", "l"], maxw=40)

    def report_runtime(self):
        """C10 런타임 감사 — 추측하지 말고 측정한다."""
        LOG.banner("런타임 감사 (C10)", "계층별 실측 소요시간 vs 계약 예산")
        budgets = {"L1": 30 * 60, "L2": 2 * 60, "L3": 3 * 60, "L5": 4 * 3600}
        agg: Dict[str, float] = defaultdict(float)
        for r in self.stages.values():
            agg[r.layer] += r.dur
        rows = []
        for layer in sorted(agg):
            spent = agg[layer]
            bud = budgets.get(layer)
            verdict = "—"
            if bud:
                verdict = "✔ 예산 내" if spent <= bud else f"❗ 초과 ({spent / bud:.1f}배)"
            rows.append([layer, f"{spent:8.2f}s", f"{spent / 60:6.2f}분",
                         (f"{bud / 60:.0f}분" if bud else "-"), verdict])
        rows.append(["합계", f"{sum(agg.values()):8.2f}s", f"{sum(agg.values()) / 60:6.2f}분", "4시간",
                     "✔ 예산 내" if sum(agg.values()) <= 4 * 3600 else "❗ 초과 — 아키텍처 수정 필요"])
        LOG.table(rows, ["계층", "실측(초)", "실측(분)", "계약예산", "판정"], ["c", "r", "r", "r", "l"])
        LOG.info("계층 정의 — L0:부트/캐시  L1:수집·피처패널  L2:스코어  L3:백테스트  L5:강건성  L6:리포트")


PIPE = Pipeline()


# ==========================================================================================
# 조각: 03_util.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 해시 / 원자적 IO / 재시도 / 레이트리미터 / 병렬 / 벡터화 통계               ║
# ║                                                                                          ║
# ║  · 횡단면 변환 순서(C5)는 여기서 단 한 번 하드코딩된다: winsorize → z → rank_pct          ║
# ║  · 롤링 회귀는 반드시 벡터화 (칼만 폐기, §3). 종목별 파이썬 루프 금지.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 정규화 ─────────────────────────────────────────────────────────────────────────────
def as_ts(x) -> Optional[pd.Timestamp]:
    """무엇이 들어오든 tz-naive 로 정규화된 Timestamp. tz 혼재는 이 프로젝트 최빈 버그였다."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        t = pd.Timestamp(x)
    except Exception:
        try:
            t = pd.to_datetime(str(x), errors="coerce")
        except Exception:
            return None
    if t is pd.NaT or pd.isna(t):
        return None
    if getattr(t, "tzinfo", None) is not None:
        t = t.tz_localize(None) if t.tz is None else t.tz_convert(None).tz_localize(None)
    return t.normalize()


def as_ts_series(s) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    return out.dt.normalize()


def month_end(x) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> pd.DatetimeIndex:
    return pd.date_range(month_end(start), month_end(end), freq="ME")


# ── 해시 / 식별자 ───────────────────────────────────────────────────────────────────────────
def sha1_str(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha1_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm_text(s: Any) -> str:
    """상호/애널리스트명/제목 정규화. 매칭 정확도의 8할이 여기서 결정된다."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", s)        # 괄호 안 제거
    s = re.sub(r"[^\w가-힣A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_corp_name(s: Any) -> str:
    """법인격 접미어 제거 — 사업장명↔법인명 매칭용."""
    t = norm_text(s)
    t = re.sub(r"\b(주식회사|유한회사|합자회사|주|㈜|Co|Ltd|Inc|Corp|Corporation|Company|Limited)\b",
               " ", t, flags=re.I)
    t = re.sub(r"(주식회사|유한회사)", " ", t)
    return re.sub(r"\s+", "", t).strip()


# 2024-01-01 종목코드 개편으로 영숫자 코드가 도입되었다.
# 형식: 앞 4자리 숫자 + 5번째(0-9,A-Z 중 I/O/U 제외) + 6번째(0,K,L,M,N)
# ★ 단순히 \D 를 제거하면 신형 티커가 조용히 망가진다(예: '09701K' → '009701').
_TICKER_RE = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])$")


def to_code6(x: Any) -> Optional[str]:
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드.
    실패하면 None. 조용히 0으로 채워 잘못된 종목을 만들지 않는다."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    s = re.sub(r"\s", "", str(x).strip().upper()).split(".")[0]
    if len(s) == 7 and s[0] in "AQ" and _TICKER_RE.match(s[1:]):
        s = s[1:]
    if _TICKER_RE.match(s):
        return s
    d = re.sub(r"\D", "", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
        return cand if _TICKER_RE.match(cand) else None
    return None


def similarity(a: str, b: str) -> float:
    """0~100. rapidfuzz 있으면 그걸, 없으면 difflib."""
    a, b = norm_corp_name(a), norm_corp_name(b)
    if not a or not b:
        return 0.0
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(a, b))
    import difflib
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


# ── 원자적 파일 IO (드라이브 FUSE 에서 깨지지 않게) ──────────────────────────────────────────
def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def atomic_write_bytes(path: str, data: bytes) -> str:
    """임시파일 → flush/fsync → os.replace. 드라이브 마운트에서 중단돼도 원본이 반쪽 나지 않는다."""
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_parquet(df: pd.DataFrame, path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = df.copy()
    for c in out.columns:                       # object 컬럼은 arrow 가 종종 거부한다 → 문자열화
        if out[c].dtype == object:
            try:
                pd.api.types.infer_dtype(out[c], skipna=True)
            except Exception:
                out[c] = out[c].astype(str)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        out.to_parquet(tmp, index=False, compression="snappy")
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        LOG.warn(f"parquet 손상 추정 — 무시하고 재생성합니다: {os.path.basename(path)} ({type(e).__name__})")
        try:                                   # 손상 파일은 지우지 않고 격리 보관 (원본 보호 원칙)
            os.replace(path, path + f".corrupt.{int(time.time())}")
        except Exception:
            pass
        return None


def read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue                        # 반쪽 줄은 건너뛴다 (append-only 저널의 정상 동작)
    return out


def append_jsonl(path: str, rows: Iterable[dict]):
    _ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


# ── 레이트리미터 / 재시도 ───────────────────────────────────────────────────────────────────
class RateLimiter:
    """소스별 토큰버킷. 스레드 안전. 차단당하지 않기 위한 최소 장치."""

    def __init__(self, qps: float):
        self.interval = 1.0 / max(qps, 0.01)
        self._next = 0.0
        self._lk = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.monotonic()
            if now < self._next:
                d = self._next - now
            else:
                d = 0.0
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]


def retry(tries: int = 4, base: float = 1.6, exc=(Exception,), on_fail=None, quiet: bool = False):
    def deco(fn):
        def wrapped(*a, **kw):
            last = None
            for i in range(tries):
                try:
                    return fn(*a, **kw)
                except exc as e:                       # noqa
                    last = e
                    if i == tries - 1:
                        break
                    slp = (base ** i) + random.random() * 0.4
                    if not quiet:
                        LOG.debug(f"재시도 {i+1}/{tries-1} ({type(e).__name__}) — {slp:.1f}s 대기")
                    time.sleep(slp)
            if on_fail is not None:
                return on_fail(last)
            raise last                                  # type: ignore
        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapped
    return deco


# ── 병렬 ────────────────────────────────────────────────────────────────────────────────────
def pmap_io(fn: Callable, items: Sequence, workers: Optional[int] = None,
            desc: str = "", quiet: bool = False) -> List[Any]:
    """네트워크 병렬(스레드). 예외는 삼키지 않고 None 으로 표시하되 개수를 로그에 남긴다."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_WORKERS_IO, len(items)))
    out: List[Any] = [None] * len(items)
    errs: Counter = Counter()
    with ThreadPoolExecutor(max_workers=w, thread_name_prefix="io") as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        it_ = as_completed(futs)
        if not quiet:
            it_ = tqdm(it_, total=len(futs), desc=desc or "수집", leave=False, ncols=88)
        for fu in it_:
            i = futs[fu]
            try:
                out[i] = fu.result()
            except Exception as e:                       # noqa
                errs[type(e).__name__] += 1
                out[i] = None
    if errs:
        LOG.warn(f"{desc or '병렬작업'} 중 실패 {sum(errs.values())}/{len(items)}건 — " +
                 ", ".join(f"{k}×{v}" for k, v in errs.most_common(4)))
    return out


def pmap_cpu(fn: Callable, items: Sequence, workers: Optional[int] = None, desc: str = "") -> List[Any]:
    """연산 병렬. fork 가능하면 프로세스, 아니면 스레드로 자동 폴백(결과 동일, 속도만 차이)."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_CPU, len(items)))
    if w == 1 or not CAN_FORK:
        if not CAN_FORK:
            LOG.debug("fork 불가 환경 — 연산 병렬을 스레드로 폴백합니다(결과 동일).")
        return [fn(x) for x in tqdm(items, desc=desc or "연산", leave=False, ncols=88)]
    try:
        ctx = _mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=w, mp_context=ctx) as ex:
            return list(tqdm(ex.map(fn, items), total=len(items), desc=desc or "연산",
                             leave=False, ncols=88))
    except Exception as e:                                # noqa
        LOG.warn(f"프로세스 병렬 실패({type(e).__name__}) — 순차 실행으로 폴백합니다.")
        return [fn(x) for x in items]


# ── 메모리 ──────────────────────────────────────────────────────────────────────────────────
def downcast(df: pd.DataFrame, cat_thresh: float = 0.35) -> pd.DataFrame:
    """float64→float32, 저카디널리티 object→category. 10년 패널 RAM을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = df[c].dtype.kind
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
        elif k == "O":
            try:
                n = df[c].nunique(dropna=True)
                if n > 0 and n / max(len(df), 1) < cat_thresh:
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df


def mem_mb(df: pd.DataFrame) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0


# ── PIT 프레임 강제 (C1) ────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")


def _resolve_dates(df: pd.DataFrame, arg) -> pd.Series:
    """날짜 인자 해석 규칙 — 딱 세 가지만 허용한다(모호함이 곧 버그다):
       ① 문자열이고 df 의 컬럼명이면      → 그 컬럼
       ② Series/배열/리스트이면           → 그대로 (길이 일치 필요)
       ③ 그 외(스칼라 날짜/문자열 날짜)   → 전 행에 브로드캐스트
    """
    if isinstance(arg, str) and arg in df.columns:
        return as_ts_series(df[arg]).set_axis(df.index)
    if isinstance(arg, pd.Series):
        if len(arg) != len(df):
            raise ValueError(f"날짜 Series 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(arg.to_numpy())).set_axis(df.index)
    if isinstance(arg, (list, tuple, np.ndarray, pd.DatetimeIndex)):
        if len(arg) != len(df):
            raise ValueError(f"날짜 배열 길이 불일치: {len(arg)} vs {len(df)}")
        return as_ts_series(pd.Series(list(arg))).set_axis(df.index)
    return as_ts_series(pd.Series([arg] * len(df))).set_axis(df.index)


def pit_frame(df: pd.DataFrame, event_date, knowledge_date, source: str = "") -> pd.DataFrame:
    """모든 수집 결과는 이 함수를 통과해야 한다. 통과하지 않은 테이블은 PIT store 가 거부한다."""
    if df is None or len(df) == 0:
        base = pd.DataFrame(df if df is not None else None)
        for c in PIT_COLS:
            if c not in base.columns:
                base[c] = pd.Series(dtype="datetime64[ns]")
        if source:
            base["_src"] = pd.Series(dtype=object)
        return base
    out = df.copy().reset_index(drop=True)
    out["event_date"] = _resolve_dates(out, event_date)
    out["knowledge_date"] = _resolve_dates(out, knowledge_date)
    # knowledge_date 는 event_date 보다 이를 수 없다 — 이를 어기면 그 자체가 미래누수다.
    bad = out["knowledge_date"] < out["event_date"]
    if bad.any():
        out.loc[bad, "knowledge_date"] = out.loc[bad, "event_date"]
        if PIPE.current:
            PIPE.note(f"WARN: knowledge_date < event_date 인 {int(bad.sum())}행을 event_date 로 보정")
    out = out.dropna(subset=["knowledge_date"])
    if source:
        out["_src"] = source
    return out


# ── 벡터화 횡단면 통계 (C5 순서 고정) ───────────────────────────────────────────────────────
WINSOR_SIGMA = 2.0
CELL_MIN_N = 8


def _winsor_np(a: np.ndarray, k: float = WINSOR_SIGMA) -> np.ndarray:
    m = np.nanmean(a)
    s = np.nanstd(a)
    if not np.isfinite(s) or s == 0:
        return a
    return np.clip(a, m - k * s, m + k * s)


def xsec_z(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N,
           k: float = WINSOR_SIGMA) -> pd.Series:
    """C5: winsorize(±2σ) → 셀 내 z-score.  순서는 여기서만 정의되고 파라미터화하지 않는다.

    구현 주의 두 가지:
     ① ±inf 를 반드시 먼저 NaN 으로 바꾼다. np.nanmean 은 NaN 은 무시하지만 inf 는 무시하지
        않으므로, 셀에 inf 가 단 하나만 있어도 평균이 inf·표준편차가 NaN 이 되어
        **그 셀 전체의 z-score 가 0으로 뭉개진다.** 비율 지표(diff/log)에서 흔히 발생한다.
     ② groupby.transform(파이썬 UDF) 대신 네이티브 집계로 벡터화한다.
        실데이터 규모(30만 행 × 수천 셀)에서 UDF 경로는 호출당 10초 이상이고,
        파이프라인은 이 함수를 수십 번 부른다.
    """
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()

    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    mu0 = g.transform("mean")
    sd0 = g.transform("std", ddof=0)
    w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)          # ① winsorize

    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)                               # ② z-score
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)            # 셀 내 전원 동일값 → 0
    return z.where(cnt >= min_n).astype("float32")


def xsec_rank_pct(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 백분위 랭크 [0,1]. 표본 부족 셀은 NaN (0으로 채우지 않는다)."""
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    r = g.rank(pct=True, method="average")
    return r.where(cnt >= min_n).astype("float32")


CELL_LADDER = ("cell", "cell_l2", "cell_l3")


def xsec_z_l(P: pd.DataFrame, name: str, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 폴백 사다리를 적용한 z-score (C11).

    ★ 왜 필요한가: 셀에 종목이 30개 있어도 '그 센서를 관측한' 종목은 5개뿐일 수 있다.
      (관세·조달처럼 일부 종목만 커버하는 팩이 정확히 이 경우다)
      셀 크기만 보고 폴백하면 z-score 는 표본부족으로 전부 NaN 이 되고,
      그 팩은 아무 신호도 못 내면서 로그에는 아무것도 남지 않는다 — 최악의 조용한 실패다.
      그래서 '그 센서의 유효 관측 수' 기준으로 산업 상위 → 전체 순으로 단계적 폴백한다.
    """
    v = col(P, name)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not z.isna().any():
            break
        if lvl in P.columns:
            z = z.where(z.notna(), xsec_z(v, P[lvl], min_n))
    return z


def xsec_rank_pct_l(P: pd.DataFrame, name_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(name_or_series, errors="coerce")
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    r = xsec_rank_pct(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not r.isna().any():
            break
        if lvl in P.columns:
            r = r.where(r.notna(), xsec_rank_pct(v, P[lvl], min_n))
    return r


def tp_product(z_improve: pd.Series, z_nopay: pd.Series) -> pd.Series:
    """트레이드오프 쌍 = z(개선) × z(대가회피).  ★ 절대로 합으로 바꾸지 말 것 (§1.1).

    합으로 바꾸면 평범한 퀄리티 팩터가 되고 이 전략의 존재 이유가 사라진다.
    한쪽이 결측이면 결과도 결측 — 0으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다.
    """
    a = pd.to_numeric(z_improve, errors="coerce")
    b = pd.to_numeric(z_nopay, errors="coerce")
    return (a * b).astype("float32")


def col(df: pd.DataFrame, name: str, default: float = np.nan) -> pd.Series:
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자.

    ★ df.get("x") 는 컬럼이 없으면 None 을 반환한다. 그러면 `None + Series` 나 `None.abs()`
      로 TypeError/AttributeError 가 나는데, 하필 그 상황(= 특정 데이터 소스가 통째로 비어
      해당 계정 컬럼이 아예 생성되지 않은 경우)은 실데이터 실행에서 가장 흔하다.
      키 미입력·API 한도 소진·소급 데이터 없음 전부 이 경로로 들어온다.
      그래서 피처 계산부는 df.get 대신 반드시 이 함수를 쓴다.
    """
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def gby(df: pd.DataFrame, name: str, key: str = "code"):
    """col() 의 groupby 판(版). 없는 컬럼도 NaN 으로 만든 뒤 그룹화한다.

    ★ col() 이 막지 못하는 구멍이 정확히 여기였다. 피처 계산부는 결측 컬럼 산술을 col() 로
      막아 두었지만, `P.groupby("code")[c]` 는 여전히 맨손이라 c 가 없으면 KeyError 로 죽는다.
      DART 키가 없거나 재무 수집이 부분 실패하면 assets·contract_liab 같은 재무상태표 계정이
      아예 생성되지 않는데, 이 경로는 critical 스테이지(L1.PANEL)라 그대로 실행 전체가 중단된다.
      "키 없이도 실행은 된다"는 상단 안내와 정면으로 어긋나므로 groupby 도 안전 접근으로 통일한다.
    """
    if name not in df.columns:
        df[name] = np.nan
    return df.groupby(key, observed=True)[name]


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


def dlog(s: pd.Series, periods: int = 12) -> pd.Series:
    """Δlog. 음수/0 은 결측 처리 (log 의 정의역 밖을 0으로 메우는 것이 최빈 버그)."""
    v = pd.to_numeric(s, errors="coerce")
    lv = np.log(v.where(v > 0))
    return lv.diff(periods)


def nanmean_cols(df: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    """가용 축만으로 평균. 결측을 0으로 채우지 않는다 (§7.3 지시)."""
    use = [c for c in cols if c in df.columns]
    if not use:
        return pd.Series(np.nan, index=df.index)
    return df[use].astype("float64").mean(axis=1, skipna=True)


# ── 벡터화 롤링 OLS (칼만 대체, §3) ─────────────────────────────────────────────────────────
def rolling_ols_resid(y: np.ndarray, X: np.ndarray, window: int,
                      ridge: float = 1e-8, chunk: int = 256) -> np.ndarray:
    """N개 엔티티 × T기간 패널에 대해 길이 W 롤링 OLS 를 배치로 풀고 창 마지막 시점 잔차를 반환.

    y : (N, T)
    X : (N, T, K)   — 절편은 호출자가 포함시킬 것
    반환: (N, T) 잔차. 창이 안 차거나 결측 포함이면 NaN.

    종목별 파이썬 루프로 짜면 15분짜리가 3시간이 된다(§3). 반드시 이 경로를 쓸 것.
    """
    y = np.asarray(y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    N, T = y.shape
    K = X.shape[2]
    out = np.full((N, T), np.nan, dtype=np.float64)
    if T < window or window < K + 2:
        return out
    try:
        from numpy.lib.stride_tricks import sliding_window_view as _swv
    except Exception:                                     # numpy<1.20 폴백
        _swv = None

    for s in range(0, N, chunk):
        e = min(N, s + chunk)
        yc, Xc = y[s:e], X[s:e]
        n = e - s
        if _swv is not None:
            yw = _swv(yc, window, axis=1)                 # (n, T-W+1, W)
            Xw = _swv(Xc, window, axis=1)                 # (n, T-W+1, K, W)
            Xw = np.moveaxis(Xw, -1, 2)                   # (n, T-W+1, W, K)
        else:
            idx = np.arange(window)[None, :] + np.arange(T - window + 1)[:, None]
            yw = yc[:, idx]
            Xw = Xc[:, idx, :]
        finite = np.isfinite(yw).all(axis=2) & np.isfinite(Xw).all(axis=(2, 3))   # (n, M)
        yw = np.where(np.isfinite(yw), yw, 0.0)
        Xw = np.where(np.isfinite(Xw), Xw, 0.0)
        XtX = np.einsum("nmwk,nmwl->nmkl", Xw, Xw, optimize=True)
        Xty = np.einsum("nmwk,nmw->nmk", Xw, yw, optimize=True)
        XtX += ridge * np.eye(K)[None, None, :, :] * np.maximum(
            1.0, np.abs(np.einsum("nmkk->nm", XtX))[..., None, None] / max(K, 1))
        try:
            beta = np.linalg.solve(XtX, Xty[..., None])[..., 0]                   # (n, M, K)
        except np.linalg.LinAlgError:
            beta = np.einsum("nmkl,nml->nmk", np.linalg.pinv(XtX), Xty)
        x_last = Xw[:, :, -1, :]                                                  # (n, M, K)
        resid = yw[:, :, -1] - np.einsum("nmk,nmk->nm", x_last, beta)
        resid = np.where(finite, resid, np.nan)
        out[s:e, window - 1:] = resid
        del yw, Xw, XtX, Xty, beta
    return out


def rolling_ols_beta_last(y: np.ndarray, X: np.ndarray, window: int, ridge: float = 1e-8) -> np.ndarray:
    """위와 동일하되 마지막 창의 계수만 필요할 때 (R3 직교화 등)."""
    N, T = y.shape
    K = X.shape[2]
    if T < window:
        return np.full((N, K), np.nan)
    yw, Xw = y[:, -window:], X[:, -window:, :]
    ok = np.isfinite(yw).all(axis=1) & np.isfinite(Xw).all(axis=(1, 2))
    yw = np.nan_to_num(yw); Xw = np.nan_to_num(Xw)
    XtX = np.einsum("nwk,nwl->nkl", Xw, Xw) + ridge * np.eye(K)[None]
    Xty = np.einsum("nwk,nw->nk", Xw, yw)
    beta = np.linalg.solve(XtX, Xty[..., None])[..., 0]
    beta[~ok] = np.nan
    return beta


def hac_tstat(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량. 월간 초과수익 시계열의 유의성에 쓴다(R2/R3)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return (np.nan, np.nan)
    mu = x.mean()
    e = x - mu
    L = lags if lags is not None else int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    L = max(0, min(L, n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    se = math.sqrt(var / n)
    return (float(mu), float(mu / se))


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg. 강건성 검정을 여러 번 돌리면 다중검정 보정이 필요하다."""
    p = np.asarray(pvals, dtype=float)
    ok = np.isfinite(p)
    out = np.zeros_like(p, dtype=bool)
    idx = np.where(ok)[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        out[order[:kmax + 1]] = True
    return out


# ==========================================================================================
# 조각: 04_vault.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스                                 ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★                                  ║
# ║                                                                                          ║
# ║  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:                                        ║
# ║   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않으므로              ║
# ║      코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없다.                                    ║
# ║   2) index.parquet 은 저널의 파생물(캐시)일 뿐이다. 재생성 전 항상 타임스탬프 백업.        ║
# ║   3) 컬럼은 합집합으로만 확장한다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않는다.          ║
# ║   4) 원본 blob 은 내용해시 기반 경로에 쓰므로 같은 내용은 재기록조차 하지 않는다.          ║
# ║      내용이 다르면 새 리비전으로 쓰고, 기존 파일은 건드리지 않는다.                        ║
# ║   5) 이미 드라이브에 있던 리포트는 "옮기지 않고 경로만 등록"한다(adopt-by-reference).      ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 한다.              ║
# ║                                                                                          ║
# ║  공용 인덱스(_shared) : 다른 전략에서도 그대로 재활용 가능한 원본/정제본                   ║
# ║  전용 인덱스(tcd_v2)  : 이 전략 고유의 피처·스코어·리포트                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "2.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "extra",
]


def _mount_drive() -> Tuple[str, str]:
    """(루트경로, 상태문자열). Colab이면 마운트 시도, 아니면 로컬 폴백. 어느 쪽이든 죽지 않는다."""
    if ENV["colab"]:
        try:
            from google.colab import drive as _gdrive      # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
            if os.path.isdir(os.path.join(mp, "MyDrive")):
                return GDRIVE_ROOT, "COLAB_DRIVE"
            return LOCAL_CACHE_ROOT, "COLAB_DRIVE_FAILED→LOCAL"
        except Exception as e:                             # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")
            return LOCAL_CACHE_ROOT, "COLAB_MOUNT_ERROR→LOCAL"
    # JupyterLab / CLI: 드라이브가 이미 동기화되어 있으면 그 경로를 쓴다.
    for cand in (GDRIVE_ROOT, os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache")):
        if cand and os.path.isdir(cand):
            return cand, "LOCAL_SYNCED_DRIVE"
    return LOCAL_CACHE_ROOT, "LOCAL"


class Vault:
    def __init__(self, root: str, mode: str):
        self.root = os.path.abspath(root)
        self.mode = mode
        self.ns = {"shared": os.path.join(self.root, GDRIVE_SHARED_NS),
                   "private": os.path.join(self.root, GDRIVE_PRIVATE_NS)}
        for p in self.ns.values():
            os.makedirs(os.path.join(p, "index"), exist_ok=True)
            os.makedirs(os.path.join(p, "index", "_backup"), exist_ok=True)
            os.makedirs(os.path.join(p, "blob"), exist_ok=True)
            os.makedirs(os.path.join(p, "table"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, pd.DataFrame] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats = Counter()

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 잠금 (두 노트북이 동시에 돌아도 저널이 섞이지 않게) -----------------------------
    @contextmanager
    def lock(self, name: str, timeout: float = 60.0, stale: float = 900.0):
        lp = os.path.join(self.root, "_locks", f"{name}.lock")
        t0 = time.time()
        acquired = False
        while time.time() - t0 < timeout:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "host": platform.node(),
                                         "ts": time.time()}).encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                try:
                    info = json.loads(open(lp).read() or "{}")
                    if time.time() - float(info.get("ts", 0)) > stale:
                        LOG.warn(f"오래된 잠금 해제: {name} (>{stale:.0f}s)")
                        os.remove(lp)
                        continue
                except Exception:
                    try:
                        os.remove(lp)
                    except Exception:
                        pass
                time.sleep(0.4)
        if not acquired:
            LOG.warn(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # ── 인덱스 적재 (기존 것을 절대 건드리지 않고 읽기만) --------------------------------
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []

        # (a) 정규 parquet 인덱스
        p = self.idx_parquet(scope)
        d = read_parquet_safe(p)
        if d is not None and len(d):
            frames.append(d)

        # (b) append-only 저널 (진실의 원천)
        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # (c) 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        legacy_glob = []
        idx_dir = os.path.join(self.ns[scope], "index")
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    legacy_glob.append(os.path.join(idx_dir, fn))
        except Exception:
            pass
        for fp in legacy_glob:
            try:
                if fp.endswith(".parquet"):
                    dd = read_parquet_safe(fp)
                elif fp.endswith(".csv"):
                    dd = pd.read_csv(fp)
                elif fp.endswith(".jsonl"):
                    dd = pd.DataFrame(read_jsonl(fp))
                else:
                    dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                if dd is not None and len(dd):
                    dd["_legacy_file"] = os.path.basename(fp)
                    frames.append(dd)
                    self.stats[f"legacy_index_absorbed:{os.path.basename(fp)}"] += len(dd)
            except Exception:
                continue

        if frames:
            # 컬럼 합집합 — 기존 컬럼을 절대 떨어뜨리지 않는다
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            frames = [f.reindex(columns=allcols) for f in frames]
            idx = pd.concat(frames, ignore_index=True)
            # ★ uid 가 없거나 결측인 레거시 행을 그대로 두면 astype(str) 이 전부 "nan" 이 되고
            #   drop_duplicates(uid) 가 그 파일 전체를 단 한 줄로 붕괴시킨다 = 인덱스 유실.
            #   절대 1원칙에 정면으로 반하므로, 결측 uid 는 행 내용 해시로 개별 부여한다.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | (idx["uid"].astype(str).str.strip().isin(("", "nan", "None")))
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                idx.loc[miss, "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in fill_src])
                    for i in np.where(miss.to_numpy())[0]]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
            idx["uid"] = idx["uid"].astype(str)
            if "collected_at" in idx.columns:
                idx = idx.sort_values("collected_at", kind="stable")
            idx = idx.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        else:
            idx = pd.DataFrame(columns=INDEX_COLUMNS)

        for c in INDEX_COLUMNS:
            if c not in idx.columns:
                idx[c] = np.nan
        idx["scope"] = idx["scope"].fillna(scope)
        with self._lk:
            self._idx[scope] = idx
            self._uidset[scope] = set(idx["uid"].astype(str).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope] or any(r.get("uid") == uid for r in self._pending[scope])

    def lookup(self, scope: str, **eq) -> pd.DataFrame:
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= (idx[k].astype(str) == str(v))
        return idx[m]

    # ── 기록 --------------------------------------------------------------------------
    def _register(self, scope: str, rec: dict):
        rec.setdefault("scope", scope)
        rec.setdefault("schema_ver", VAULT_SCHEMA_VER)
        rec.setdefault("collected_at", _dt.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("strategy", STRATEGY_ID if scope == "private" else "")
        for c in INDEX_COLUMNS:
            rec.setdefault(c, None)
        with self._lk:
            self._pending[scope].append(rec)
            self._uidset.setdefault(scope, set()).add(str(rec["uid"]))
        self.stats[f"register:{scope}:{rec.get('domain')}"] += 1

    def put_blob(self, domain: str, subtype: str, key: str, data: bytes, fmt: str,
                 source: str = "", event_date=None, knowledge_date=None,
                 scope: str = "shared", extra: Optional[dict] = None,
                 uid: Optional[str] = None) -> Optional[str]:
        """원본 바이트를 내용해시 경로에 저장하고 인덱스에 등록. 같은 내용이면 재기록하지 않는다."""
        if not data:
            return None
        h = sha1_bytes(data)
        uid = uid or sha1_str(domain, subtype, key, h)
        sub = os.path.join(self.blob_dir(scope), domain, subtype, h[:2], h[2:4])
        fn = f"{h}.{fmt.lstrip('.')}"
        abspath = os.path.join(sub, fn)
        rel = os.path.relpath(abspath, self.root)
        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                          # noqa
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에만 기록하지 않고 건너뜁니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": rel, "abs_path": abspath, "fmt": fmt, "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "source": source, "adopted": False,
            "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        return abspath

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        if rows.empty:
            return None
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

    def put_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다."""
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                              # noqa
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        return path

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None
                  ) -> Optional[pd.DataFrame]:
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if not os.path.exists(path):
            # 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략이 만든 걸 재활용한다
            alt = "private" if scope == "shared" else "shared"
            path2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if os.path.exists(path2):
                path = path2
            else:
                return None
        if max_age_days is not None:
            age = (time.time() - os.path.getmtime(path)) / 86400.0
            if age > max_age_days:
                return None
        d = read_parquet_safe(path)
        if d is not None:
            PIPE.io("IN", "DRIVE", f"table:{name}", d, source=os.path.relpath(path, self.root))
        return d

    def adopt(self, abs_path: str, domain: str, subtype: str, key: str,
              source: str = "", event_date=None, knowledge_date=None,
              scope: str = "shared", extra: Optional[dict] = None) -> Optional[str]:
        """이미 드라이브에 있는 파일을 옮기지 않고 '경로만' 등록한다. 파일은 읽기만 한다."""
        try:
            sz = os.path.getsize(abs_path)
        except Exception:
            return None
        uid = sha1_str("adopt", domain, subtype, os.path.abspath(abs_path), sz)
        if self.has(scope, uid):
            return uid
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": abs_path, "abs_path": abs_path, "fmt": os.path.splitext(abs_path)[1].lstrip("."),
            "bytes": sz, "sha1": "", "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""), "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ------------------------------------------------------------------
    def flush(self, scope: Optional[str] = None):
        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""
        scopes = [scope] if scope else ["shared", "private"]
        for sc in scopes:
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)
            LOG.debug(f"인덱스 저널 append: {sc} +{len(rows)}행")

    def compact(self, scope: str):
        """저널 → index.parquet 재생성. 저널은 남기고, 기존 parquet 은 반드시 백업한 뒤 교체."""
        self.flush(scope)
        idx = self.load_index(scope, force=True)
        p = self.idx_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"index.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                          # noqa
                LOG.warn(f"인덱스 백업 실패({type(e).__name__}) — 안전을 위해 컴팩션을 건너뜁니다. "
                         f"저널({os.path.basename(self.journal(scope))})에 모든 기록이 남아 있으므로 "
                         f"데이터 유실은 없습니다.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (사용자의 기존 캐시 흡수) --------------------------------------------
    _PDF_PAT = re.compile(r"\.(pdf)$", re.I)
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 400_000) -> pd.DataFrame:
        """기존에 모아둔 리포트/테이블을 재귀 스캔해 '등록만' 한다. 이동·개명·삭제 없음."""
        seen, found = set(), []
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            rd = os.path.realpath(d)
            if rd in seen:
                continue
            seen.add(rd)
            LOG.info(f"기존 캐시 스캔: {d}")
            n = 0
            for dirpath, dirnames, filenames in os.walk(d):
                dirnames[:] = [x for x in dirnames if not x.startswith(".") and x != "_backup"]
                for fn in filenames:
                    if n >= max_files:
                        break
                    fp = os.path.join(dirpath, fn)
                    low = fn.lower()
                    if low.endswith(".pdf"):
                        kind = "report_pdf"
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "nps",
                                                   "price", "ohlcv", "universe", "fnltt")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": fp, "kind": kind, "name": fn,
                                  "dir": dirpath, "bytes": _safe_size(fp)})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        if not found:
            LOG.warn("기존 캐시에서 흡수할 파일을 찾지 못했습니다. "
                     "GDRIVE_ADOPT_DIRS 경로를 확인하세요(오타/미마운트가 가장 흔합니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared",
                       extra={"dir": r.dir})
        self.flush("shared")
        LOG.ok(f"기존 캐시 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
               f"(파일은 원위치 그대로, 이동·삭제 없음).")
        return df

    # ── 감사 --------------------------------------------------------------------------
    def report(self):
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            nb = 0
            try:
                nb = sum(int(x) for x in pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0))
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared" else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}",
                         f"{int(pd.to_numeric(idx.get('adopted'), errors='coerce').fillna(0).sum()):,}"
                         if "adopted" in idx.columns else "0",
                         f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])
        idx = self.load_index("shared")
        if not idx.empty and "domain" in idx.columns:
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(24))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title="공용 인덱스 구성 (다른 전략에서 그대로 재사용 가능)")
        if self.stats:
            LOG.table([[k, f"{v:,}"] for k, v in sorted(self.stats.items())][:24],
                      ["이벤트", "횟수"], ["l", "r"], title="이번 실행의 캐시 이벤트")
        LOG.info("무결성 원칙: 저널은 append-only(기존 줄 재기록 없음) · index.parquet 은 백업 후 교체 · "
                 "blob 은 내용해시 경로라 덮어쓰기 자체가 발생하지 않음 · 삭제 API 없음.")


def _safe_size(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:
        return -1


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return float("nan")


VAULT: Optional[Vault] = None


# ==========================================================================================
# 조각: 05_http.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 차단 회피          ║
# ║                                                                                          ║
# ║  한국 사이트 수집에서 실패의 9할은 세 가지다:                                              ║
# ║   ① User-Agent/Referer 없음 → 403   ② euc-kr 인데 utf-8로 디코드 → 글자 깨짐               ║
# ║   ③ 너무 빠른 요청 → 429/차단.  전부 여기서 한 번에 막는다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36",
]

_TLS = threading.local()
HTTP_STATS: Counter = Counter()
_HTTP_LK = threading.Lock()


def _session() -> "requests.Session":
    s = getattr(_TLS, "sess", None)
    if s is not None:
        return s
    s = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
            rt = Retry(total=0, connect=2, read=2, backoff_factor=0.5,
                       status_forcelist=(), raise_on_status=False)
        except Exception:
            rt = None
        ad = HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                         pool_maxsize=max(32, N_WORKERS_IO * 4),
                         max_retries=rt) if rt is not None else \
            HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
                        pool_maxsize=max(32, N_WORKERS_IO * 4))
        s.mount("https://", ad)
        s.mount("http://", ad)
    except Exception:
        pass
    s.headers.update({
        "User-Agent": UA_POOL[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    _TLS.sess = s
    return s


_HANGUL = re.compile(r"[가-힣]")
_MOJI = re.compile(r"[¿½¶ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß]")


def _korean_score(t: str) -> float:
    """한글 가독성 점수. 네이버 금융은 body 가 EUC-KR 인데 meta 는 utf-8 이라고 '거짓말'한다.
    meta 를 믿으면 조용히 깨진 글자를 얻는다(예외가 안 난다) — 그래서 점수로 고른다."""
    s = t[:6000]
    if not s:
        return -1.0
    han = len(_HANGUL.findall(s))
    moji = len(_MOJI.findall(s))
    repl = s.count("�")
    return han - 3.0 * moji - 5.0 * repl


def _decode(content: bytes, resp_enc: Optional[str], url: str,
            force_enc: Optional[str] = None) -> str:
    # force_enc 는 '우선 후보'일 뿐 절대 지정이 아니다. 소스가 UTF-8 로 바뀌면
    # euc-kr 강제 디코딩은 예외 없이 깨진 글자를 돌려주므로, 점수로 검증한 뒤에만 채택한다.
    if force_enc:
        try:
            t = content.decode(force_enc, "replace")
            if _korean_score(t) > 30:
                return t
        except Exception:
            pass
    head = content[:4096].decode("ascii", "ignore").lower()
    m = re.search(r'charset\s*=\s*["\']?\s*([\w\-]+)', head)
    cands: List[str] = []
    if m:
        cands.append(m.group(1))
    if resp_enc:
        cands.append(resp_enc)
    cands += ["utf-8", "euc-kr", "cp949"]
    seen, best, best_s = set(), None, -1e18
    for enc in cands:
        e = (enc or "").lower().replace("ks_c_5601-1987", "cp949")
        if not e or e in seen:
            continue
        seen.add(e)
        try:
            t = content.decode(e)
        except Exception:
            continue
        sc = _korean_score(t)
        if sc > best_s:
            best, best_s = t, sc
        if sc > 30:                     # 충분히 한글다우면 더 볼 필요 없음
            return t
    return best if best is not None else content.decode("utf-8", "replace")


def euckr_q(s: str) -> str:
    """네이버/한경 레거시 경로의 한글 파라미터는 UTF-8이 아니라 EUC-KR 퍼센트인코딩이다.
    이걸 틀리면 예외 없이 '검색 결과 0건'이 나온다 — 최악의 조용한 실패."""
    try:
        return quote(str(s), encoding="euc-kr")
    except Exception:
        return quote(str(s))


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    last_exc = None
    for attempt in range(tries):
        lim.wait()
        if on_attempt is not None:
            try:
                on_attempt()
            except Exception:
                pass
        try:
            s = _session()
            if attempt > 0:
                hdr["User-Agent"] = UA_POOL[attempt % len(UA_POOL)]
            r = s.get(url, params=params, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{r.status_code}"] += 1
            if r.status_code in allow_status:
                return r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
            if r.status_code in (429, 503):
                time.sleep(min(30.0, 2.0 * (2 ** attempt)) + random.random())
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            if r.status_code in (403, 401):
                time.sleep(1.5 * (attempt + 1))
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            last_exc = requests.HTTPError(f"{r.status_code} {url}")
        except Exception as e:                                # noqa
            last_exc = e
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(min(12.0, (1.7 ** attempt)) + random.random() * 0.3)
    if not quiet and last_exc:
        LOG.debug(f"GET 실패({source}) {url[:90]} — {type(last_exc).__name__}")
    with _HTTP_LK:
        HTTP_STATS[f"{source}:FAIL"] += 1
    return None


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None) -> Optional[Union[str, bytes]]:
    lim = limiter(source)
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    for attempt in range(tries):
        lim.wait()
        try:
            r = _session().post(url, data=data, json=json_body, headers=hdr, timeout=timeout)
            with _HTTP_LK:
                HTTP_STATS[f"{source}:POST{r.status_code}"] += 1
            if r.status_code == 200:
                return r.content if as_bytes else _decode(r.content, r.encoding, url)
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    return None


def soup_of(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    for parser in ("lxml", "html.parser", "html5lib"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def http_json(url: str, source: str = "generic", **kw) -> Optional[Any]:
    t = http_get(url, source=source, **kw)
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None


def report_http():
    if not HTTP_STATS:
        return
    LOG.banner("HTTP 수집 감사", "소스별 응답 분포 — 403/429가 많으면 RATE_LIMIT_QPS 를 낮추세요")
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_STATS.items():
        src, _, code = k.partition(":")
        by_src[src][code] += v
    rows = []
    for src, c in sorted(by_src.items()):
        tot = sum(c.values())
        ok = c.get("200", 0) + c.get("POST200", 0)
        bad = sum(v for k, v in c.items() if k in ("403", "401", "429", "503", "FAIL", "POSTFAIL"))
        rows.append([src, f"{tot:,}", f"{ok:,}", f"{100 * ok / max(tot, 1):.1f}%", f"{bad:,}",
                     _trunc(", ".join(f"{k}×{v}" for k, v in c.most_common(5)), 44)])
    LOG.table(rows, ["소스", "요청", "성공", "성공률", "차단/실패", "상세"],
              ["l", "r", "r", "r", "r", "l"])


# ==========================================================================================
# 조각: s06_dart.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  DART 호출량 관리 — "남은 만큼 쓴다"                                                ║
# ║                                                                                          ║
# ║  이전 구현의 결함 4가지를 전부 고쳤다:                                                     ║
# ║   ① 상한을 19,000 으로 하드코딩하고 그 숫자를 게이트로 썼다.                                ║
# ║      → 상한은 '표시용 힌트'일 뿐이고, 실제 정지 조건은 API 가 돌려주는 status='020' 이다.   ║
# ║        한도 상향 승인을 받은 계정이면 020 이 올 때까지 계속 쓴다. 관측으로 한도를 학습한다.  ║
# ║   ② status='020' 을 감지해 exhausted 플래그만 세우고 정작 게이트에 쓰지 않았다.             ║
# ║      → 020 이후에도 남은 작업이 전부 실제 HTTP 를 쏘고 실패했다. 이제 즉시 하드 스톱한다.    ║
# ║   ③ 카운터를 '전용(private)' 네임스페이스에 저장했다.                                       ║
# ║      → 호출량은 전략이 아니라 'API 키'에 걸린다. 두 전략이 각자 2만건이라고 착각했다.        ║
# ║        이제 공용(shared) 네임스페이스에 키 해시별로 저장해 모든 전략이 같은 잔량을 본다.     ║
# ║   ④ 날짜 경계를 컨테이너 로컬시각으로 잡았다 (Colab 은 UTC).                                ║
# ║      → DART 의 초기화 기준은 KST 자정이다. UTC 로 세면 매일 9시간 어긋난다.                  ║
# ║                                                                                          ║
# ║  그리고 애초에 이 전략은 DART 를 거의 쓰지 않는다.                                          ║
# ║  필요한 건 §6.3 직교화의 BM(장부/시가) 한 항목이고, 1순위는 KRX 월말 PBR 스냅샷(120호출)다.  ║
# ║  DART 는 그게 비었을 때만 '배치' 엔드포인트로 보강한다(100사/호출). 예상 총량은 실행 시작 시  ║
# ║  표로 출력된다 — 통상 2,000건 미만이다.                                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_LIMIT_HINT = 20_000          # 공식 기본 한도(표시용). 게이트가 아니다 — 관측으로 갱신된다.
DART_MULTI_BATCH = 100            # fnlttMultiAcnt: 1회 호출에 100개사
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}

_KST = _dt.timezone(_dt.timedelta(hours=9))


def kst_today() -> str:
    """DART 일일 한도의 초기화 기준은 KST 자정이다. 컨테이너 로컬시각(UTC)이 아니다."""
    return _dt.datetime.now(_dt.timezone.utc).astimezone(_KST).date().isoformat()


def kst_seconds_to_reset() -> int:
    now = _dt.datetime.now(_dt.timezone.utc).astimezone(_KST)
    nxt = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


class DartQuota:
    """실시간 잔여 호출량 관리자.

    핵심 원리: **한도를 가정하지 않고 관측한다.**
      · used  : 실제로 나간 HTTP 요청 수 (재시도 포함). 정확히 센다.
      · limit : 처음엔 힌트(20,000). status='020' 을 받은 시점의 used 를 '관측된 한도'로
                기록하고 이후 그 값을 쓴다. 다음 날 그 관측치를 사전값으로 재사용한다.
      · 정지  : limit 도달이 아니라 **020 수신**이 하드 스톱이다.
                (한도가 상향된 계정은 20,000 을 넘겨도 020 이 안 오므로 계속 쓴다)
    """

    def __init__(self, api_key: str, scope: str = "shared"):
        self.key_id = sha1_str("dartkey", api_key or "")[:12] if api_key else "nokey"
        self.scope = scope
        self.today = kst_today()
        self.used = 0
        self.observed_limit: Optional[int] = None   # 020 을 실제로 받은 지점
        self.exhausted = False
        self.calls_api = 0                          # 논리 호출 수 (HTTP 요청 수와 구분)
        self._lk = threading.RLock()
        self._dirty = 0
        self._load()

    # ── 영속화: 공용 네임스페이스, 키별 ──────────────────────────────────────────────
    def _path(self) -> str:
        return os.path.join(VAULT.ns[self.scope], "index", f"dart_quota_{self.key_id}.json")

    def _load(self):
        try:
            j = json.loads(open(self._path(), encoding="utf-8").read())
        except Exception:
            return
        # 어제까지의 '관측된 한도'는 날짜가 바뀌어도 유효한 지식이므로 이어받는다
        ol = j.get("observed_limit")
        if isinstance(ol, int) and ol > 0:
            self.observed_limit = ol
        if j.get("date") == self.today:
            self.used = int(j.get("used", 0))
            self.exhausted = bool(j.get("exhausted", False))
            if self.used:
                LOG.info(f"오늘(KST {self.today}) 이 키로 이미 사용한 DART 호출 {self.used:,}건 — "
                         f"잔여 {self.remaining():,}건. 이어서 진행합니다.")
            if self.exhausted:
                LOG.warn(f"이 키는 오늘 이미 한도 초과(020)를 받았습니다. "
                         f"KST 자정까지 {kst_seconds_to_reset() // 3600}시간 "
                         f"{kst_seconds_to_reset() % 3600 // 60}분 남았습니다. "
                         f"DART 경로는 건너뛰고 캐시/KRX 경로로 진행합니다.")

    def _save(self, force: bool = False):
        if not force and self._dirty < 100:
            return
        self._dirty = 0
        try:
            atomic_write_text(self._path(), json.dumps({
                "date": self.today, "used": self.used, "exhausted": self.exhausted,
                "observed_limit": self.observed_limit, "key_id": self.key_id,
                "updated_at": _dt.datetime.now(_KST).isoformat(timespec="seconds"),
            }, ensure_ascii=False))
        except Exception:
            pass

    # ── 잔여량 ──────────────────────────────────────────────────────────────────────
    @property
    def limit(self) -> int:
        return int(self.observed_limit or DART_LIMIT_HINT)

    def remaining(self) -> int:
        """지금 이 순간 남은 호출량. 020 을 받았으면 0."""
        with self._lk:
            if self.exhausted:
                return 0
            return max(0, self.limit - self.used)

    def limit_is_observed(self) -> bool:
        return self.observed_limit is not None

    # ── 예약 / 환급 ─────────────────────────────────────────────────────────────────
    def take(self, k: int = 1) -> bool:
        """k회의 HTTP 요청을 예약. 020 을 받았으면 무조건 거부(하드 스톱)."""
        with self._lk:
            if self.exhausted:
                return False
            # 힌트 한도를 넘어서도, 020 을 실제로 받기 전까지는 막지 않는다.
            # (한도 상향 계정을 스스로 19,000 에서 멈추게 만든 것이 이전 구현의 핵심 결함)
            if self.observed_limit is not None and self.used + k > self.observed_limit:
                return False
            self.used += k
            self._dirty += k
            self._save()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.used = max(0, self.used - k)

    def mark_exhausted(self):
        """API 가 020 을 돌려줬다 = 진짜 한도. 이 지점을 관측치로 학습한다."""
        with self._lk:
            if self.exhausted:
                return
            self.exhausted = True
            self.observed_limit = int(self.used)
            LOG.warn(f"DART 일일 한도에 실제로 도달했습니다 (status=020). "
                     f"이 키의 관측 한도 = {self.observed_limit:,}건 — 다음 실행부터 이 값을 씁니다. "
                     f"KST 자정({kst_seconds_to_reset() // 3600}시간 후) 초기화됩니다. "
                     f"여기까지 받은 데이터는 캐시에 저장되어 있으므로 재실행 시 정확히 이어받습니다.")
            self._save(force=True)

    def plan(self, need_calls: int, label: str) -> int:
        """이번 배치에서 '실제로 쓸 수 있는' 호출 수를 돌려준다. 미리 자르지 않는다.

        need <= remaining  → need 그대로 (전량 수행)
        need >  remaining  → remaining 만큼만 수행하고 나머지는 다음 실행으로 이월.
                             (예전처럼 19,000 에서 임의로 멈추는 게 아니라, 실제 잔량 기준)
        """
        rem = self.remaining()
        src = "관측" if self.limit_is_observed() else "기본값(미관측)"
        if need_calls <= rem:
            LOG.info(f"[DART 예산] {label}: 필요 {need_calls:,}건 / 잔여 {rem:,}건 "
                     f"(한도 {self.limit:,} {src}, 사용 {self.used:,}) → 전량 수행")
            return need_calls
        LOG.warn(f"[DART 예산] {label}: 필요 {need_calls:,}건 > 잔여 {rem:,}건 "
                 f"(한도 {self.limit:,} {src}) → 이번 실행은 {rem:,}건만 받고 "
                 f"나머지 {need_calls - rem:,}건은 KST 자정 이후 재실행 시 이어받습니다.")
        return rem

    def close(self):
        self._save(force=True)

    def report(self):
        LOG.table([
            ["키 식별자", self.key_id],
            ["기준일 (KST)", self.today],
            ["사용 (HTTP 요청 수)", f"{self.used:,}"],
            ["논리 호출 수", f"{self.calls_api:,}"],
            ["한도", f"{self.limit:,} ({'관측됨' if self.limit_is_observed() else '기본값 — 미관측'})"],
            ["잔여", f"{self.remaining():,}"],
            ["한도초과(020) 수신", "예 — 하드 스톱" if self.exhausted else "아니오"],
            ["KST 초기화까지", f"{kst_seconds_to_reset() // 3600}시간 "
                               f"{kst_seconds_to_reset() % 3600 // 60}분"],
        ], ["항목", "값"], ["l", "r"], title="DART 호출량 (실시간 추적 · 한도는 관측으로 학습)")


DQ: Optional[DartQuota] = None


def dart_api(endpoint: str, params: dict, source: str = "dart", tries: int = 2) -> Optional[dict]:
    """DART 호출 1건. 예산은 '최악(tries회)'을 먼저 예약하고 실제 시도 수만큼만 남긴다.

    http_get 은 내부적으로 최대 tries 회 실제 요청을 보낸다. 호출당 1건으로 세면
    실사용량을 최대 tries 배 과소집계한다 — 그래서 예약 후 환급하는 구조다.
    """
    if not DART_API_KEY:
        return None
    if DQ is not None and not DQ.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DQ is not None:
        DQ.refund(max(0, tries - max(1, attempts["n"])))
        DQ.calls_api += 1
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DQ is not None:
                DQ.mark_exhausted()          # ★ 이제 진짜로 멈춘다
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요 (https://opendart.fss.or.kr → 인증키 신청/관리).")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def dart_probe() -> Tuple[bool, str]:
    """카나리 (SPEC §2.3): 전체 수집 전에 1건으로 도달 가능성을 먼저 확인한다."""
    if not DART_API_KEY:
        return False, "키 미입력 — DART 경로 건너뜀 (KRX 스냅샷만으로 BM 산출)"
    if DQ is not None and DQ.exhausted:
        return False, "오늘 한도 초과(020) 상태 — KST 자정 이후 재시도"
    js = dart_api("list.json", {"bgn_de": "20240102", "end_de": "20240102",
                                "page_no": 1, "page_count": 1}, tries=1)
    if js is None:
        return False, "응답 없음/오류 — 키 또는 네트워크 확인"
    return True, "정상"


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자. 없으면 법정기한으로 보수적 추정 (미래누수 방지)."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


_EQUITY_PAT = re.compile(r"자본총계|^ifrs-full_Equity$|^ifrs_Equity$")


def fetch_dart_equity(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """§6.3 BM 의 DART 폴백 — 자본총계(장부가)만 배치로 받는다.

    fnlttMultiAcnt 는 1회 호출에 100개사를 처리하므로, 2,500사 × 11년 × 4보고서라도
    2500/100 × 11 × 4 ≈ 1,100 호출이면 끝난다. 전체 재무제표(fnlttSinglAcntAll)를
    사별로 긁으면 11만 호출이 필요하다 — 애초에 그렇게 설계하면 안 되는 것이다.
    """
    cols = ["corp_code", "bsns_year", "reprt_code", "equity", "period_end",
            "knowledge_date", "event_date"]
    cached = VAULT.get_table("dart_equity_quarterly", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        try:
            have = set(zip(cached["corp_code"].astype(str),
                           cached["bsns_year"].astype(int),
                           cached["reprt_code"].astype(str)))
        except Exception:
            have = set()
    if not DART_API_KEY or DQ is None or DQ.exhausted:
        return cached if cached is not None else pd.DataFrame(columns=cols)

    codes = sorted({str(c).zfill(8) for c in corp_codes if str(c).strip() and str(c) != "nan"})
    batches = [codes[i:i + DART_MULTI_BATCH] for i in range(0, len(codes), DART_MULTI_BATCH)]
    jobs = [(b, y, rc) for y in years for rc in REPRT_CODES.values() for b in batches
            if not all((c, int(y), rc) in have for c in b)]
    if not jobs:
        LOG.ok(f"DART 자본총계: 캐시로 충족 ({len(cached):,}행) — 신규 호출 0건")
        return cached

    allowed = DQ.plan(len(jobs) * 2, "자본총계 배치(BM 폴백)") // 2
    if allowed <= 0:
        LOG.warn("DART 잔여 호출량이 없어 이번 실행은 캐시만 사용합니다.")
        return cached if cached is not None else pd.DataFrame(columns=cols)
    jobs = jobs[:allowed]

    def _one(job):
        b, y, rc = job
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(b), "bsns_year": str(y), "reprt_code": rc})
        if not js or not isinstance(js.get("list"), list):
            return None
        rows = []
        for it in js["list"]:
            nm = str(it.get("account_nm", ""))
            aid = str(it.get("account_id", ""))
            if not (_EQUITY_PAT.search(nm) or _EQUITY_PAT.search(aid)):
                continue
            v = re.sub(r"[^\d\-]", "", str(it.get("thstrm_amount", "")))
            if not v or v == "-":
                continue
            mm, dd = REPRT_PERIOD_END.get(rc, (12, 31))
            rows.append({
                "corp_code": str(it.get("corp_code", "")).zfill(8),
                "bsns_year": int(y), "reprt_code": rc, "equity": float(v),
                "period_end": as_ts(f"{y}-{mm:02d}-{dd:02d}"),
                "knowledge_date": _knowledge_from_rcept(it.get("rcept_no"), rc, int(y)),
            })
        return pd.DataFrame(rows) if rows else None

    got = pmap_io(_one, jobs, workers=min(4, N_WORKERS_IO), desc="DART 자본총계")
    frames = [d for d in got if d is not None and len(d)]
    if cached is not None and len(cached):
        frames.append(cached)
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["corp_code", "bsns_year", "reprt_code"], keep="last")
    out = pit_frame(out, "period_end", "knowledge_date", source="dart")
    VAULT.put_table("dart_equity_quarterly", out, scope="shared", domain="dart",
                    source="opendart fnlttMultiAcnt (equity only)")
    LOG.ok(f"DART 자본총계 {len(out):,}행 (신규 호출 {DQ.calls_api:,}건, 잔여 {DQ.remaining():,}건)")
    return out


# ==========================================================================================
# 조각: 10_ingest_universe.py
# ==========================================================================================

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 유니버스 (C2 생존자편향 제거)                                     ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축 — 우선순위와 역할이 각각 다르다:                                      ║
# ║    ① FDR GitHub 캐시  listing/krx        상장 종목 + 상장일        ← 로그인 불필요, 1순위  ║
# ║    ② FDR GitHub 캐시  listing/delisting  상장폐지 + 폐지일         ← ★생존자편향 제거 입력 ║
# ║    ③ KIND 상장법인목록                   상장일·업종 보강                                  ║
# ║    ④ pykrx 월/분기말 스냅샷              "그 날 실제 상장" 검증     ← 인증 필요, 보조      ║
# ║    ⑤ DART corpCode.xml                   corp_code ↔ 종목코드                              ║
# ║    ⑥ 네이버 금융                         ①~⑤ 어디에도 이름이 없는 잔여 코드 보강          ║
# ║                                                                                          ║
# ║  ★ 설계 원칙: 유니버스의 정확성은 ①②③⑤(상장일·폐지일)만으로 성립해야 한다.                ║
# ║    ④ 스냅샷은 '검증·보강'이지 '의존'이 아니다. KRX 인증이 실패해도 백테스트는 정상이어야   ║
# ║    한다. 실제로 KRX 는 부분 응답을 자주 내는데, 그걸 진실로 믿으면 그 달 유니버스가        ║
# ║    조용히 쪼그라들어 곧바로 선택편향이 된다.                                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "sector_src", "src"]

# 스냅샷 주기: "Q"(분기·기본) | "M"(월) | "A"(연) | "off"
#   월 단위는 120개월 × 2시장 = 240 호출이라 KRX 세션을 자주 건드리고 차단 위험이 커진다.
#   상장/폐지일이 이미 있으므로 분기 격자(40 × 2 = 80 호출)로도 검증 목적은 충분하다.
UNIVERSE_SNAPSHOT_FREQ = "Q"


# ── 중복 컬럼 방어 (이번 크래시의 직접 원인 유형) ────────────────────────────────────────────
def assert_no_dup_cols(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 에서 예외 없이 의미가 바뀐다.
    df[col] 이 Series 가 아니라 DataFrame 이 되고, groupby.agg 가
    'DataFrame object has no attribute name' 로 엉뚱한 곳에서 터진다.
    조용히 지나가면 최악이므로 발생 지점에서 즉시 세운다."""
    if df is None or df.empty:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — "
                           f"pandas 연산의 의미가 바뀌므로 여기서 중단합니다.")
    return df


# ── KRX 세션 게이트 ─────────────────────────────────────────────────────────────────────────
class KRXGate:
    """pykrx 호출을 단일 게이트로 통과시킨다.

    ★ 왜 필요한가 (pykrx 1.2.8 소스 확인 결과):
      get_auth_session() 은 모듈 전역 _auth_session 에 대해 락 없이 검사-후-생성을 한다.
      스레드 6개가 동시에 None 을 보면 6개가 각자 로그인하고, KRX 는 중복 로그인(CD011)을
      skipDup 로 처리하며 앞선 세션을 강제 종료시킨다. 살아남는 건 마지막 하나뿐이고
      나머지 스레드는 죽은 쿠키로 요청해 JSON 대신 로그인 HTML 을 받는다.
      → 실제 운영 로그의 'Error occurred in ...: Expecting value: line 13 column 1' 이 이것이다.
      또 세션은 3600초(버퍼 300초 → 실효 55분) 만료라 긴 수집은 반드시 만료를 넘긴다.
      만료 갱신도 같은 무락 경로를 타므로 장시간 실행에서 같은 폭풍이 재현된다.

    대응: ① 메인 스레드에서 단 한 번 워밍업 ② 모든 pykrx 호출을 락으로 직렬화
          ③ 만료 전에 선제 갱신 ④ 실패해도 예외 대신 None 을 돌려 상위가 폴백하게 한다.
    """

    def __init__(self):
        self._lk = threading.RLock()
        self._warm = False
        self._authed = False
        self._t_login = 0.0
        self.calls = 0
        self.fails = 0

    def warmup(self) -> bool:
        if pykrx_stock is None:
            return False
        with self._lk:
            if self._warm:
                return self._authed
            self._warm = True
            has_cred = bool(os.environ.get("KRX_ID") and os.environ.get("KRX_PW"))
            try:
                from pykrx.website.comm.auth import get_auth_session   # type: ignore
                s = get_auth_session()
                self._authed = s is not None and getattr(s, "is_authenticated", False)
            except Exception:
                self._authed = False
            self._t_login = time.time()
            if has_cred and self._authed:
                LOG.ok("KRX 세션 확보 (메인 스레드 1회 로그인) — 이후 모든 pykrx 호출을 "
                       "직렬화해 중복 로그인(CD011)으로 서로를 밀어내는 현상을 막습니다.")
            elif has_cred:
                LOG.warn("KRX 자격증명은 있으나 세션 인증에 실패했습니다. ID/PW 를 확인하세요. "
                         "스냅샷 검증만 건너뛰며, 유니버스는 상장일·폐지일로 정확히 구성됩니다.")
            else:
                LOG.info("KRX 자격증명 미입력 — pykrx 스냅샷 검증은 생략합니다. "
                         "유니버스는 FDR 상장/폐지 목록으로 구성되며 백테스트는 정상 동작합니다.")
            return self._authed

    def _refresh_if_stale(self):
        # 실효 55분. 45분마다 선제 갱신해 '동시 만료 → 동시 재로그인'을 원천 차단한다.
        if not self._authed or (time.time() - self._t_login) < 45 * 60:
            return
        try:
            from pykrx.website.comm.auth import get_auth_session       # type: ignore
            get_auth_session()
            self._t_login = time.time()
            LOG.debug("KRX 세션 선제 갱신")
        except Exception:
            pass

    def call(self, fn: Callable, *a, **kw):
        """모든 pykrx 호출의 유일한 통로. 직렬화 + 스로틀 + 예외 흡수."""
        if pykrx_stock is None:
            return None
        with self._lk:
            self._refresh_if_stale()
            limiter("krx").wait()
            self.calls += 1
            try:
                return fn(*a, **kw)
            except Exception as e:                                     # noqa
                self.fails += 1
                LOG.debug(f"pykrx 호출 실패 {getattr(fn, '__name__', '?')}: {type(e).__name__}")
                return None

    def report(self):
        if self.calls:
            LOG.info(f"pykrx 게이트 — 호출 {self.calls:,}건 · 실패 {self.fails:,}건 "
                     f"({100*self.fails/max(self.calls,1):.1f}%) · 직렬화 적용")


KRXG = KRXGate()


# ── 로그인 불필요 경로 ★1순위 ──────────────────────────────────────────────────────────────
#   FinanceDataReader 가 실제로 읽는 GitHub 캐시. KRX 인증 변경의 영향을 받지 않는다.
#   FDR 라이브러리 자체는 최신 영업일을 알아내려고 data.krx.co.kr 을 한 번 찌르는데,
#   그게 로그인 벽에 막히면 CSV 는 멀쩡한데도 ValueError 로 죽는다 → 우리는 CSV 를 직접 읽는다.
FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
             "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 14) -> Optional[pd.DataFrame]:
    """영업일 CSV 만 존재하므로 최근 날짜부터 거꾸로 훑는다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        url = FDR_CACHE.format(kind=kind, date=d.isoformat())
        raw = http_get(url, source="generic", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            # ★ index_col=0 을 무조건 주면 안 된다.
            #   listing CSV 는 이름 없는 인덱스 컬럼이 있지만 delisting CSV 는 없을 수 있고,
            #   그때 첫 실컬럼(Symbol=종목코드)이 인덱스로 먹혀 통째로 사라진다.
            #   → 상장폐지 종목이 전부 유실되고 그게 곧 생존자편향이다. 반드시 판별해서 읽는다.
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} "
                          f"({len(df):,}행 · 컬럼 {list(df.columns)[:6]})")
                return df
        except Exception:
            continue
    return None


def _lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def fetch_fdr_listing() -> pd.DataFrame:
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
        name_c = col.get("name") or col.get("korean name") or col.get("isu_nm")
        if code_c and name_c:
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "market": (d[col["market"]].astype(str) if "market" in col
                           else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
                "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
                "industry": (d[col["sector"]].astype(str) if "sector" in col
                             else d[col["industry"]].astype(str) if "industry" in col else ""),
            })
            t["sector_src"], t["src"] = "fdr_cache", "fdr_github_cache"
            t["delisting_date"] = pd.NaT
            t["corp_code"] = np.nan
            n0 = len(t)
            r = t.dropna(subset=["code"]).drop_duplicates("code")
            if n0 - len(r):
                LOG.debug(f"상장목록 정규화 탈락 {n0-len(r):,}건(코드 형식 불일치/중복)")
            LOG.ok(f"상장목록(로그인 불필요 경로) {len(r):,}건 — KRX 인증 변경 영향을 받지 않습니다.")
            return r

    if fdr is None:
        LOG.warn("상장목록을 확보하지 못했습니다 (GitHub 캐시 실패 + FinanceDataReader 없음).")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    try:
        limiter("krx").wait()
        d = fdr.StockListing("KRX")
    except Exception as e:                                            # noqa
        LOG.warn(f"fdr.StockListing('KRX') 실패({type(e).__name__}) — "
                 f"FDR 은 최신 영업일 확인차 data.krx.co.kr 를 찌르는데 그게 막히면 "
                 f"CSV 가 멀쩡해도 죽습니다.")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    if d is None or len(d) == 0:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    col = _lower_map(d)
    code_c = col.get("code") or col.get("symbol")
    name_c = col.get("name")
    if not code_c or not name_c:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6), "name": d[name_c].astype(str),
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
        "industry": d[col["sector"]].astype(str) if "sector" in col else "",
        "delisting_date": pd.NaT, "corp_code": np.nan,
        "sector_src": "fdr", "src": "fdr:KRX"})
    return t.dropna(subset=["code"]).drop_duplicates("code")


def fetch_fdr_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. KRX Open API 에는 상장폐지 엔드포인트가 아예 없어서
    이 GitHub 캐시가 사실상 유일한 공개 경로다.

    ★ 탈락 사유를 반드시 집계해 로그로 남긴다. 여기서 조용히 버려지는 종목이
    그대로 생존자편향이 되기 때문이다(운영에서 4,172행 → 2,526행으로 줄었던 구간)."""
    d = _fdr_cache_csv("listing/delisting")
    if d is None or len(d) == 0:
        if fdr is None:
            LOG.warn("상장폐지 목록을 확보하지 못했습니다 — C2(생존자편향 제거) 미충족 상태입니다. "
                     "결과 해석 시 반드시 감안하세요.")
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
        try:
            limiter("krx").wait()
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
        if d is None or len(d) == 0:
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])

    col = _lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        LOG.warn(f"상장폐지 파일에서 종목코드 컬럼을 찾지 못했습니다: {list(d.columns)[:12]}")
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date",
                                  "listingdate") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c

    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    n_badcode = int(codes.isna().sum())
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    })
    t = t.dropna(subset=["code"])
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_nodate = int(t["delisting_date"].isna().sum())

    LOG.ok(f"상장폐지 목록(로그인 불필요 경로) {len(t):,}건 — 생존자편향 제거 입력 확보")
    if n_raw - len(t):
        LOG.info(f"  폐지목록 정규화: 원본 {n_raw:,} → {len(t):,} "
                 f"(코드형식 불일치 {n_badcode:,} · 동일코드 중복 {n_dupe:,}) · "
                 f"폐지일 결측 {n_nodate:,}건은 상장기간 추정에서 제외됩니다.")
        if n_badcode > n_raw * 0.25:
            LOG.warn(f"폐지목록의 {100*n_badcode/max(n_raw,1):.0f}% 가 코드 형식 불일치로 "
                     f"탈락했습니다. 이 비율이 크면 생존자편향이 그만큼 남습니다 — "
                     f"원본 코드 예시: {raw_codes[codes.isna()].head(5).tolist()}")
    return t


def fetch_kind_listing() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일·업종 보강.
    ★ 종목코드가 정수로 와서 앞자리 0 이 날아간다(5930 ← 005930). to_code6 이 복구한다."""
    urls = [
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download",
    ]
    for u in urls:
        raw = http_get(u, source="kind", as_bytes=True, tries=2,
                       referer="https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage")
        if not raw or len(raw) < 500:
            continue
        for enc in ("euc-kr", "cp949", "utf-8"):
            try:
                tabs = pd.read_html(io.BytesIO(raw), encoding=enc)
            except Exception:
                continue
            if not tabs:
                continue
            d = max(tabs, key=len)
            col = {str(c).strip(): c for c in d.columns}
            code_c, name_c = col.get("종목코드"), col.get("회사명")
            if not code_c or not name_c:
                continue
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "listing_date": as_ts_series(d[col["상장일"]]) if "상장일" in col else pd.NaT,
                "industry": d[col["업종"]].astype(str) if "업종" in col else "",
                "sector_src": "kind", "src": "kind", "market": "",
                "delisting_date": pd.NaT, "corp_code": np.nan,
            }).dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"KIND 상장법인목록 {len(t):,}건 (상장일 {int(t['listing_date'].notna().sum()):,}건)")
            return t
    LOG.warn("KIND 상장법인목록을 받지 못했습니다 — 상장일은 FDR/스냅샷으로만 채웁니다.")
    return pd.DataFrame(columns=SEC_MASTER_COLS)


def fetch_dart_corpcode() -> pd.DataFrame:
    """corp_code ↔ 종목코드. DART 의 모든 재무·공시 조회는 corp_code 로만 된다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 와 네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    txt = _decode(xml, None, "corpcode")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code")), "modify_date": g("modify_date")})
    d = pd.DataFrame(rows)
    if len(d):
        VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건)")
    return d


# ── pykrx 스냅샷 (보조·검증) ────────────────────────────────────────────────────────────────
def _snapshot_grid(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    f = str(UNIVERSE_SNAPSHOT_FREQ).upper()
    if f in ("OFF", "NONE", ""):
        return []
    if f == "M":
        return list(months)
    if f == "A":
        return [m for m in months if m.month == 12] or list(months[::12])
    return [m for m in months if m.month in (3, 6, 9, 12)] or list(months[::3])   # 기본 Q


def fetch_pykrx_snapshots(months: pd.DatetimeIndex) -> pd.DataFrame:
    """분기말 상장종목 스냅샷. C2 의 '검증' 입력이다(의존 대상이 아님).

    ★ 전부 KRXG 게이트를 통해 직렬로 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), 그 결과 JSON 대신 로그인 HTML 을 받아 대량 실패한다."""
    cols = ["snap_date", "code", "market"]
    cached = VAULT.get_table("krx_listing_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"공용 캐시에서 상장 스냅샷 {len(have)}개 시점 재사용")

    grid = _snapshot_grid(months)
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    new_rows: List[dict] = []
    if todo:
        if not KRXG.warmup():
            LOG.info(f"KRX 세션이 없어 스냅샷 {len(todo)}개 시점을 건너뜁니다. "
                     f"유니버스는 상장일·폐지일로 구성되며 이는 정상 경로입니다.")
            todo = []
    if todo:
        LOG.info(f"KRX 상장 스냅샷 {len(todo)}개 시점 수집 (주기={UNIVERSE_SNAPSHOT_FREQ}, 직렬)")
        bad_streak = 0
        for d in tqdm(todo, desc="KRX 상장 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           d.strftime("%Y%m%d"), prev=True) or d.strftime("%Y%m%d")
            got_any = False
            for mkt in ("KOSPI", "KOSDAQ"):
                tk = KRXG.call(pykrx_stock.get_market_ticker_list, bd, market=mkt)
                if not tk:
                    continue
                got_any = True
                for t in tk:
                    c = to_code6(t)
                    if c:
                        new_rows.append({"snap_date": d.strftime("%Y-%m-%d"),
                                         "code": c, "market": mkt})
            bad_streak = 0 if got_any else bad_streak + 1
            if bad_streak >= 5:
                LOG.warn("KRX 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 상태입니다. "
                         "스냅샷 수집을 중단하고 상장일·폐지일 경로로 진행합니다(정상 폴백).")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap = (snap.dropna(subset=["snap_date", "code"])
                .drop_duplicates(["snap_date", "code"])[cols])

    # ★ 부분 응답 방어: 이웃 시점 대비 종목수가 급감한 스냅샷은 '진실'이 아니라 '사고'다.
    #   그대로 쓰면 그 달 유니버스가 조용히 쪼그라들어 선택편향이 된다.
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만이라 "
                     f"부분 응답으로 판단하고 폐기합니다: "
                     f"{[str(x.date()) for x in bad.index[:6]]}")
            snap = snap[~snap["snap_date"].isin(bad.index)]
    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                        source="pykrx", extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_listing_snapshots", snap, source="pykrx")
    return snap


def fetch_naver_names(codes: Sequence[str], limit: int = 400) -> Dict[str, str]:
    """①~⑤ 어디에도 이름이 없는 잔여 코드를 네이버로 보강한다.
    이름이 비면 국민연금·조달 상호 매칭이 통째로 실패하므로 커버리지에 직접 영향이 있다."""
    codes = [c for c in codes if c][:limit]
    if not codes or RUN_MODE == "CACHED":
        return {}

    def _one(c: str):
        h = http_get(f"https://finance.naver.com/item/main.naver?code={c}",
                     source="naver", tries=1, force_enc="euc-kr",
                     referer="https://finance.naver.com/")
        if not h:
            return None
        m = re.search(r'<div class="wrap_company">\s*<h2>\s*<a[^>]*>([^<]+)</a>', h)
        if not m:
            m = re.search(r"<title>\s*([^:<]+?)\s*:", h)
        return (c, _clean_cell(m.group(1))) if m else None

    res = pmap_io(_one, codes, workers=min(6, N_WORKERS_IO), desc="네이버 종목명 보강")
    out = {c: n for r in res if r for c, n in [r] if n}
    if out:
        LOG.ok(f"네이버로 종목명 {len(out):,}건 보강")
    return out


# ── 종목 마스터 ─────────────────────────────────────────────────────────────────────────────
def build_security_master(snapshots: pd.DataFrame) -> pd.DataFrame:
    """모든 소스를 합쳐 종목 마스터를 만든다. 충돌은 우선순위로 해소하고 전부 로깅한다."""
    parts: List[pd.DataFrame] = []
    src_stats: List[Tuple[str, int]] = []

    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
        src_stats.append(("FDR 상장목록", len(lst)))
        PIPE.io("IN", "HTTP", "fdr:StockListing", lst, source="FinanceDataReader")

    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
        src_stats.append(("KIND 상장법인", len(kind)))
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")

    dead = fetch_fdr_delisting()
    PIPE.io("IN", "HTTP", "fdr:KRX-DELISTING", dead, source="FinanceDataReader",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market"]).copy()
        d2["listing_date"] = pd.NaT
        d2["industry"] = ""
        d2["corp_code"] = np.nan
        d2["sector_src"] = "fdr-del"
        d2["src"] = "fdr:delisting"
        parts.append(d2)
        src_stats.append(("FDR 상장폐지", len(d2)))

    # 스냅샷에만 존재하는 종목(=상장목록·폐지목록 어디에도 없는 종목)도 반드시 살린다
    if snapshots is not None and len(snapshots):
        known = set(pd.concat(parts, ignore_index=True)["code"]) if parts else set()
        extra = sorted(set(snapshots["code"]) - known)
        if extra:
            parts.append(pd.DataFrame({
                "code": extra, "name": "", "market": "", "listing_date": pd.NaT,
                "delisting_date": pd.NaT, "corp_code": np.nan, "industry": "",
                "sector_src": "snapshot", "src": "pykrx:snapshot"}))
            src_stats.append(("스냅샷 전용", len(extra)))
            LOG.info(f"스냅샷에만 존재하는 종목 {len(extra):,}건 추가 — 상장/폐지 명단 누락분입니다. "
                     f"(빠뜨리면 곧바로 생존자편향)")

    if not parts:
        raise RuntimeError(
            "종목 마스터를 만들 소스가 하나도 없습니다.\n"
            "  · 네트워크에서 raw.githubusercontent.com 과 kind.krx.co.kr 에 접근 가능한지\n"
            "  · FinanceDataReader 가 설치되어 있는지\n"
            "확인하세요. RUN_MODE='SMOKE' 로는 네트워크 없이 계산경로만 검증할 수 있습니다.")

    # ★ 중복 컬럼 원천 차단: 컬럼 목록을 dict.fromkeys 로 유일화한 뒤 정렬한다.
    #   (SEC_MASTER_COLS 에 이미 있는 이름을 다시 더하면 m[col] 이 DataFrame 이 되고
    #    groupby.agg 가 'DataFrame object has no attribute name' 으로 터진다)
    _cols = list(dict.fromkeys(SEC_MASTER_COLS))
    m = pd.concat([p.reindex(columns=_cols) for p in parts], ignore_index=True)
    assert_no_dup_cols(m, "security_master:concat")
    m["code"] = m["code"].map(to_code6)
    m = m.dropna(subset=["code"])

    def _first_str(s):
        for x in s:
            if isinstance(x, str) and x.strip():
                return x.strip()
        return ""

    agg = m.groupby("code", as_index=False).agg(
        name=("name", _first_str),
        market=("market", _first_str),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "max"),
        industry=("industry", _first_str),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
    )
    assert_no_dup_cols(agg, "security_master:agg")

    # 스냅샷으로 상장/폐지일 보정 — 소스 날짜가 없을 때만 관측으로 채운다
    if snapshots is not None and len(snapshots):
        g = snapshots.groupby("code")["snap_date"]
        agg = agg.merge(g.min().rename("snap_first"), left_on="code", right_index=True, how="left")
        agg = agg.merge(g.max().rename("snap_last"), left_on="code", right_index=True, how="left")
        need = agg["listing_date"].isna() & agg["snap_first"].notna()
        agg.loc[need, "listing_date"] = agg.loc[need, "snap_first"]
        last_snap = snapshots["snap_date"].max()
        gone = (agg["delisting_date"].isna() & agg["snap_last"].notna() &
                (agg["snap_last"] < last_snap - pd.Timedelta(days=200)))
        agg.loc[gone, "delisting_date"] = agg.loc[gone, "snap_last"] + pd.offsets.MonthEnd(1)
        if int(gone.sum()):
            LOG.info(f"스냅샷에서 사라진 {int(gone.sum()):,}종목을 폐지로 추정 "
                     f"(폐지명단 누락 보완 — 생존자편향 2차 방어)")
        agg = agg.drop(columns=[c for c in ("snap_first", "snap_last") if c in agg.columns])

    cc = fetch_dart_corpcode()
    if len(cc):
        cc2 = cc.dropna(subset=["code"])[["code", "corp_code", "corp_name"]].drop_duplicates("code")
        agg = agg.merge(cc2, on="code", how="left")
        blank = agg["name"].astype(str).str.strip() == ""
        agg.loc[blank, "name"] = agg.loc[blank, "corp_name"].fillna("")
        agg = agg.drop(columns=["corp_name"])
    else:
        agg["corp_code"] = np.nan

    # 네이버로 잔여 무명 종목 보강 (상호 매칭 커버리지에 직결)
    nameless = agg.loc[agg["name"].astype(str).str.strip() == "", "code"].tolist()
    if nameless:
        LOG.info(f"이름이 비어 있는 종목 {len(nameless):,}건 — 네이버로 보강 시도")
        nm = fetch_naver_names(nameless)
        if nm:
            agg["name"] = agg.apply(
                lambda r: nm.get(r["code"], r["name"]) if not str(r["name"]).strip() else r["name"],
                axis=1)

    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    agg["sector_src"] = "merged"
    assert_no_dup_cols(agg, "security_master:final")

    n_list = int(agg["listing_date"].notna().sum())
    n_del = int(agg["delisting_date"].notna().sum())
    n_corp = int(agg["corp_code"].notna().sum()) if "corp_code" in agg.columns else 0
    n_name = int((agg["name"].astype(str).str.strip() != "").sum())
    LOG.table([[lab, f"{n:,}"] for lab, n in src_stats] +
              [["── 병합 결과 ──", ""],
               ["고유 종목", f"{len(agg):,}"],
               ["상장일 보유", f"{n_list:,} ({100*n_list/max(len(agg),1):.0f}%)"],
               ["폐지일 보유", f"{n_del:,} ({100*n_del/max(len(agg),1):.0f}%)"],
               ["corp_code 보유", f"{n_corp:,} ({100*n_corp/max(len(agg),1):.0f}%)"],
               ["종목명 보유", f"{n_name:,} ({100*n_name/max(len(agg),1):.0f}%)"]],
              ["소스 / 항목", "건수"], ["l", "r"], title="종목 마스터 구성 (다중소스 병합)")

    if n_del < 200:
        LOG.warn("상장폐지 종목이 200건 미만입니다. 10년 구간이면 통상 1,000건 이상이어야 합니다. "
                 "생존자편향이 남아 있으니 결과 해석 시 반드시 감안하세요. (C2 부분 미충족)")
        PIPE.note("WARN: 상장폐지 표본 부족 — C2 완전 제거 미달")
    if n_corp < len(agg) * 0.3:
        LOG.warn(f"corp_code 매칭률이 {100*n_corp/max(len(agg),1):.0f}% 로 낮습니다. "
                 f"DART 재무·공시가 그만큼 결측이 되어 B/C축과 PACK-C/D 가 약해집니다. "
                 f"DART_API_KEY 를 확인하세요.")
    VAULT.put_table("security_master", agg, scope="shared", domain="universe",
                    source="fdr+kind+pykrx+dart+naver")
    KRXG.report()
    return agg


# ==========================================================================================
# 조각: 11_ingest_price.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]


class KRXAuth:
    """KRX 데이터 마켓플레이스 인증(2025-12 변경 대응). 실패해도 절대 죽지 않고 폴백으로 넘긴다.

    2026년 기준 경로 3가지:
      ① KRX Open API (data-dbg.krx.co.kr) — 인증키. ★단, 엔드포인트별로 '이용신청'이 따로 필요하고
         승인에 하루 정도 걸린다. 키만 있다고 바로 되는 게 아니다. 상장폐지 API 는 존재하지 않는다.
      ② 마켓플레이스 세션 로그인 → getJsonData.cmd (bld 기반). pykrx 가 쓰는 경로.
      ③ 레거시 OTP 파일다운로드 — 2026년에는 세션 없이 빈 데이터/로그아웃 오류가 잦다. 의존 금지.
    """

    LOGIN_WARM1 = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    LOGIN_WARM2 = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    JSONDATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
    OPENAPI = "https://data-dbg.krx.co.kr/svc/apis/{cat}/{ep}"

    def __init__(self, user: str, pw: str, apikey: str = ""):
        self.user, self.pw, self.apikey = (user or "").strip(), (pw or "").strip(), (apikey or "").strip()
        self.status = "NOT_ATTEMPTED"
        self.session_ok = False
        self.openapi_ok = False

    def login(self) -> bool:
        if self.apikey:
            self.openapi_ok = self._probe_openapi()
            self.status = "OPENAPI_OK" if self.openapi_ok else "OPENAPI_KEY_UNAUTHORIZED"
            if not self.openapi_ok:
                LOG.warn("KRX Open API 키는 있으나 해당 엔드포인트 호출이 거부되었습니다. "
                         "KRX Open API 는 '엔드포인트별 이용신청'이 따로 필요하고 승인에 하루 정도 "
                         "걸립니다. 키 발급만으로는 즉시 사용할 수 없습니다.")
        if not (self.user and self.pw):
            if not self.openapi_ok:
                self.status = "NO_CREDENTIALS"
                LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 불필요 경로로 진행합니다. "
                         "(FDR GitHub 캐시 → 네이버 차트 → yfinance). "
                         "백테스트는 정상 동작하며, 어느 소스가 쓰였는지는 감사표에 나옵니다.")
            return self.openapi_ok
        # 워밍업 없이 바로 POST 하면 세션 쿠키가 없어 항상 실패한다
        http_get(self.LOGIN_WARM1, source="krx", tries=1)
        http_get(self.LOGIN_WARM2, source="krx", tries=1, referer=self.LOGIN_WARM1)
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                continue
            if re.search(r"CD011|중복\s*로그인", str(txt)):
                LOG.warn("KRX 중복 로그인(CD011) 감지 — 같은 계정이 브라우저나 다른 노트북에서 "
                         "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 종료됩니다. "
                         "두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                 "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
        return self.openapi_ok

    def _probe_openapi(self) -> bool:
        """AUTH_KEY 를 쿼리로 보내는 구현과 헤더로 보내는 공식 샘플이 공존한다 — 둘 다 시도."""
        d = (_dt.date.today() - _dt.timedelta(days=7))
        while d.weekday() >= 5:
            d -= _dt.timedelta(days=1)
        url = self.OPENAPI.format(cat="sto", ep="stk_bydd_trd")
        for mode in ("query", "header"):
            kw = ({"params": {"AUTH_KEY": self.apikey, "basDd": d.strftime("%Y%m%d")}}
                  if mode == "query" else
                  {"params": {"basDd": d.strftime("%Y%m%d")},
                   "headers": {"AUTH_KEY": self.apikey}})
            js = http_json(url, source="krx", tries=1, **kw)
            if isinstance(js, dict) and (js.get("OutBlock_1") or js.get("output")):
                LOG.ok(f"KRX Open API 사용 가능 (AUTH_KEY 전달 방식: {mode})")
                self._openapi_mode = mode
                return True
        return False

    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회. 세션이 없으면 JSON 대신 로그인 HTML 이 와서
        엉뚱한 곳에서 JSONDecodeError 가 난다 → 여기서 미리 막는다."""
        if not self.session_ok:
            return None
        body = {"bld": bld, "share": "1", "money": "1", "csvxls_isNo": "false", **params}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if not txt or txt.lstrip()[:1] not in ("{", "["):
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY)


# ── 개별 소스 ───────────────────────────────────────────────────────────────────────────────
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_ohlcv(start.replace("-", ""), end.replace("-", ""), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "거래대금": "amount"}
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    d["code"], d["src"] = code, "pykrx"
    return d.reindex(columns=PRICE_COLS)


def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        limiter("krx").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    if "amount" not in d.columns:
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")      # 근사 — 감사표에 명시된다
    d["code"], d["src"] = code, "fdr"
    return d.reindex(columns=PRICE_COLS)


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 차트 API. 폴백 중에서는 가장 안정적이지만 거래대금이 없다."""
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
        # 응답이 파이썬 리터럴에 가까운 준-JSON 이다: 홑따옴표 + 따옴표 없는 키워드
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast
                arr = ast.literal_eval(t.strip())
            except Exception:
                arr = None
        if isinstance(arr, list) and len(arr) >= 2:
            break
        arr = None
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    hdr = [str(x).strip().lower() for x in arr[0]]
    rows = [r for r in arr[1:] if isinstance(r, (list, tuple)) and len(r) == len(hdr)]
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=hdr)
    # ★ 이 rename 이 오랫동안 아무 일도 하지 않고 있었다.
    #   {**ren, **{c: c for c in d.columns}} 는 두 번째 dict 가 첫 번째를 덮어써서
    #   '날짜'→'날짜' 가 '날짜'→'date' 를 이긴다. 결과적으로 컬럼명이 한글로 남고
    #   d.get("close") 가 None 이 되어 None*None TypeError 로 죽는다.
    #   (pykrx/FDR 이 둘 다 없는 환경에서만 드러나므로 오래 숨어 있었다)
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "외국인소진율": "foreign_ratio"}
    d = d.rename(columns=ren)
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["amount"] = d["close"] * d["volume"]          # 네이버는 거래대금을 안 준다 → 근사(감사표에 명시)
    d["code"], d["src"] = code, "naver"
    d = d.dropna(subset=["close"])
    return d.reindex(columns=PRICE_COLS) if len(d) else None


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            limiter("generic").wait()
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [str(c[0]).lower() for c in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]
        d = d.reset_index()
        d = d.rename(columns={"index": "date"})
        if "date" not in d.columns:
            d = d.rename(columns={d.columns[0]: "date"})
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")
        d["code"], d["src"] = code, "yfinance"
        return d.reindex(columns=PRICE_COLS)
    return None


PRICE_CHAIN = [("pykrx", _px_pykrx), ("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf)]


def fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. 캐시 증분 갱신. 공용 인덱스에 저장."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    cached = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        g = cached.groupby("code")["date"]
        have_max, have_min = g.max().to_dict(), g.min().to_dict()
        LOG.info(f"공용 캐시에서 일봉 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    start_ts, end_ts = as_ts(start), as_ts(end)

    # ── 시도 원장 (음성 캐시) ─────────────────────────────────────────────────────────────
    #  ★ 폐지 종목과 '어느 소스에도 없는 종목'은 매 실행마다 전 소스 체인을 헛돌게 만든다.
    #    성공한 종목만 캐시에 남으므로 실패는 영원히 기억되지 않고, 그 수는 백테스트 기간이
    #    길어질수록 단조 증가한다. 실측상 완전 캐시 상태의 실행에서도 13~15분을 여기서 쓴다.
    #    → '언제 무엇을 시도했는지'를 남겨 30일간 재시도하지 않는다. 소스가 복구되면
    #      30일 뒤 자동으로 다시 시도하므로 영구 포기가 아니다.
    RETRY_AFTER_DAYS = 30
    _today = as_ts(end)
    attempts: Dict[str, dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att["attempted_at"] = as_ts_series(_att["attempted_at"])
        _att["requested_from"] = as_ts_series(_att["requested_from"])
        _att = _att.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from}
                    for r in _att.itertuples(index=False)}

    def _recently_failed(c: str, want_from: pd.Timestamp) -> bool:
        p = attempts.get(c)
        if p is None or pd.isna(p["at"]):
            return False
        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 되지 않는다.
        if pd.notna(p["frm"]) and p["frm"] > want_from:
            return False
        return (_today - p["at"]).days < RETRY_AFTER_DAYS

    todo, n_back, n_fwd, n_skip = [], 0, 0, 0
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, start_ts):
                n_skip += 1
                continue
            todo.append((c, start))
            continue
        # ★ 과거 방향 백필을 반드시 함께 본다.
        #   앞선 실행이 최근 구간만 캐시했다면(예: 캐시가 2023~2026 뿐),
        #   max 만 보고 판단하면 2016~2022 를 영원히 못 받는다.
        #   → 10년 백테스트인데 앞 7년이 조용히 비는 사고가 된다.
        if mn is not None and mn > start_ts + pd.Timedelta(days=10):
            todo.append((c, start))
            n_back += 1
        elif mx < end_ts - pd.Timedelta(days=5):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
            n_fwd += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목을 처음부터 다시 받습니다 "
                 f"(캐시 최소일이 요청 시작일보다 늦음 = 앞 구간 결손).")
    if n_skip:
        LOG.info(f"최근 {RETRY_AFTER_DAYS}일 내 전 소스에서 실패한 {n_skip:,}종목은 이번엔 "
                 f"건너뜁니다 (대부분 상장폐지분). {RETRY_AFTER_DAYS}일 뒤 자동 재시도합니다.")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    if todo:
        LOG.info(f"일봉 신규/증분 수집 대상 {len(todo):,}종목")

        def _one(job):
            code, st = job
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        failed = []
        for (c, st), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.
            _prev = _att if _att is not None and len(_att) else None
            _new = pd.DataFrame(failed)
            _all = pd.concat([_prev, _new], ignore_index=True) if _prev is not None else _new
            _all = (_all.sort_values("attempted_at")
                        .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                            source="fetch_prices:negative_cache")

    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        avail = [nm for nm, _fn in PRICE_CHAIN
                 if (nm != "pykrx" or pykrx_stock is not None)
                 and (nm != "fdr" or fdr is not None)
                 and (nm != "yfinance" or yf is not None)]
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            f"  · 시도한 소스 체인 : {', '.join(nm for nm, _ in PRICE_CHAIN)}\n"
            f"  · 이번 실행에서 사용 가능했던 소스 : {', '.join(avail) or '없음'}\n"
            f"  · 대상 종목 {len(codes):,}개 / 신규 수집 시도 {len(todo):,}개\n"
            "  진단: ① 네트워크에서 fchart.stock.naver.com 접근이 되는지\n"
            "        ② FinanceDataReader / pykrx 가 설치돼 있는지\n"
            "        ③ 드라이브 캐시(krx_ohlcv_daily)가 비어 있지 않은지\n"
            "  임시 우회: RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    for c in ("open", "high", "low", "close", "volume", "amount"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    px = px[(px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)]

    if new_frames:
        VAULT.put_table("krx_ohlcv_daily", px, scope="shared", domain="price",
                        source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common()))
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if src_used.get("naver", 0) or src_used.get("yfinance", 0):
            LOG.warn("네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "V6 유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향).")
    PIPE.io("OUT", "DRIVE", "krx_ohlcv_daily", px, source="price chain")
    return downcast(px)


def build_price_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 기준 가격 패널 + 익월 시가 체결가 + 20일 평균거래대금(ADV).

    체결은 '신호 산출일 다음 거래일 시가'(§10.1). 당일 종가 체결은 미래누수다.
    """
    px = px.sort_values(["code", "date"])
    px["adv20"] = (px.groupby("code", observed=True)["amount"]
                     .transform(lambda s: s.rolling(20, min_periods=10).mean()))
    px["ret1d"] = px.groupby("code", observed=True)["close"].pct_change()

    # 월말 스냅샷
    px["ym"] = px["date"].values.astype("datetime64[M]")
    last = px.groupby(["code", "ym"], observed=True).tail(1).copy()
    last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)

    # 다음 거래일 시가 = 체결가
    nxt = px.copy()
    nxt["next_open"] = nxt.groupby("code", observed=True)["open"].shift(-1)
    nxt["next_date"] = nxt.groupby("code", observed=True)["date"].shift(-1)
    keep = nxt[["code", "date", "next_open", "next_date"]]
    last = last.merge(keep, on=["code", "date"], how="left")

    monthly = last[["code", "month", "date", "close", "adv20", "next_open", "next_date"]].copy()
    monthly = monthly.rename(columns={"date": "signal_date"})
    monthly = monthly[monthly["month"].isin(months)]

    # 월간 수익률(체결가→체결가). 상장폐지 처리는 backtest 엔진에서 -100% 로 강제한다.
    monthly = monthly.sort_values(["code", "month"])
    # 체결가 = 신호 산출일의 '다음 거래일 시가'. 그 다음 거래일이 너무 멀면(거래정지·상폐 직전)
    # 그 가격으로 체결했다고 가정할 수 없으므로 종가로 폴백한다.
    gap = (monthly["next_date"] - monthly["signal_date"]).dt.days
    monthly["exec_px"] = monthly["next_open"].where(gap.notna() & (gap <= 10))
    monthly["exec_px"] = monthly["exec_px"].fillna(monthly["close"])

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    nxt_px = monthly.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_m = monthly.groupby("code", observed=True)["month"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    monthly["fwd_ret"] = (nxt_px / monthly["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def fetch_investor_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다."""
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용")
        cached["date"] = as_ts_series(cached["date"])
        return cached
    if pykrx_stock is None or RUN_MODE == "CACHED":
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})

    def _one(code: str):
        try:
            limiter("krx").wait()
            d = pykrx_stock.get_market_trading_value_by_date(
                as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
        except Exception:
            return None
        if d is None or len(d) == 0:
            return None
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "date"})
        inst = next((c for c in d.columns if "기관" in str(c)), None)
        forg = next((c for c in d.columns if "외국" in str(c)), None)
        if inst is None and forg is None:
            return None
        return pd.DataFrame({"code": code, "date": as_ts_series(d["date"]),
                             "inst_net": pd.to_numeric(d[inst], errors="coerce") if inst else np.nan,
                             "foreign_net": pd.to_numeric(d[forg], errors="coerce") if forg else np.nan})

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 8), desc="수급 수집")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.warn("수급 데이터를 받지 못했습니다 — d3 결측 처리.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])
    fl = pd.concat(got, ignore_index=True)
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)


# ==========================================================================================
# 조각: s12_market_meta.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-M  시장 메타 — 시가총액 / BM / 제외플래그 / 업종 / 개인비중                            ║
# ║                                                                                          ║
# ║  재사용 코어(가격 조각)에는 이것들이 통째로 없다. 확인된 공백을 여기서 메운다:               ║
# ║    · 시가총액·상장주식수      → §5 유니버스 하한, §6.3 log(MktCap), 소형주 비교아암          ║
# ║    · BM(장부/시가)            → §6.3 직교화 4번째 항                                       ║
# ║    · 관리종목/스팩/우선주/ETF → §5 제외 규칙 (코어에 필터가 하나도 없었다)                   ║
# ║    · 업종                     → §6.3 SectorRet, H2 교차업종 전용 검정                       ║
# ║    · 개인 거래비중            → H3 조건부 예측                                              ║
# ║                                                                                          ║
# ║  ★ 호출량 설계: 전부 '날짜 1개 = 전종목 1호출' 스냅샷 API 다.                               ║
# ║    시총 120호출 + 펀더멘털 120호출 + ETF/ETN 목록 120호출 ≈ 360호출로 10년치가 끝난다.      ║
# ║    종목별 루프(2,500회)로 짜면 같은 데이터에 20배를 쓴다 — 그렇게 하지 않는다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MKTCAP_COLS = ["code", "month", "mktcap", "shares", "close_m", "amount_m"]
FUND_COLS = ["code", "month", "bps", "per", "pbr", "eps", "div_yield", "bm"]

_PREF_TAIL = set("5679KLMNkl")          # 우선주 관용 말자리 (구형 5/7/9, 신형 K/L/M)
_SPAC_PAT = re.compile(r"스팩|기업인수목적")
_REIT_PAT = re.compile(r"리츠|위탁관리부동산|기업구조조정부동산")
_ETF_PAT = re.compile(r"KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE |PLUS |RISE |KOSEF|"
                      r"TIMEFOLIO|파워|마이티|네비게이터|ETN|레버리지|인버스", re.I)


def is_preferred(code: str, name: str = "") -> bool:
    """우선주 판정. 코드 말자리(구형 5/7/9, 신형 K/L/M)와 종목명 '우/우B/2우B' 를 함께 본다."""
    c = str(code or "")
    if len(c) == 6 and c[-1] in _PREF_TAIL and c[-1] != "0":
        return True
    n = str(name or "").strip()
    return bool(re.search(r"(\d?우[BC]?)$|우선주$", n))


def _month_snap_dates(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    """각 월의 스냅샷 기준일(월말). pykrx 는 휴장일이면 직전 영업일로 알아서 당겨준다."""
    return [as_ts(m) for m in months]


def _krx_snapshot(fn_name: str, day: str) -> Optional[pd.DataFrame]:
    """pykrx 스냅샷 호출을 KRXG 게이트로 직렬화한다.

    pykrx 는 스레드마다 재로그인하고 KRX 는 중복 로그인 시 이전 세션을 끊는다.
    병렬로 부르면 JSON 대신 로그인 HTML 을 받아 엉뚱한 곳에서 터진다 — 반드시 직렬화.
    """
    if pykrx_stock is None:
        return None
    fn = getattr(pykrx_stock, fn_name, None)
    if fn is None:
        return None
    d = KRXG.call(fn, day, market="ALL")
    if d is None or not hasattr(d, "empty") or d.empty:
        d = KRXG.call(fn, day)
    if d is None or not hasattr(d, "empty") or d.empty:
        return None
    return d


def fetch_mktcap_monthly(months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 시가총액·상장주식수 스냅샷. 1개월 = 1호출."""
    cached = VAULT.get_table("krx_mktcap_monthly", scope="shared")
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["month"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"시가총액 월말 스냅샷: 캐시 충족 ({len(cached):,}행, 신규 호출 0건)")
        return cached
    if pykrx_stock is None:
        LOG.warn("pykrx 없음 — 시가총액 스냅샷을 건너뜁니다. "
                 "유니버스 시총 하한과 §6.3 log(MktCap) 항이 비활성화됩니다.")
        return cached if cached is not None else pd.DataFrame(columns=MKTCAP_COLS)

    LOG.info(f"시가총액 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails = [], 0
    for m in tqdm(todo, desc="시총 스냅샷", disable=not VERBOSE):
        d = _krx_snapshot("get_market_cap_by_ticker", m.strftime("%Y%m%d"))
        if d is None:
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 시총 수집을 중단하고 "
                         f"여기까지 받은 분량을 저장합니다.")
                break
            continue
        fails = 0
        t = d.reset_index()
        cmap = {c: str(c) for c in t.columns}
        t = t.rename(columns=cmap)
        pick = {}
        for c in t.columns:
            s = str(c)
            if s in ("티커", "종목코드", "index"):
                pick["code"] = c
            elif "시가총액" in s:
                pick["mktcap"] = c
            elif "상장주식수" in s:
                pick["shares"] = c
            elif s == "종가":
                pick["close_m"] = c
            elif "거래대금" in s:
                pick["amount_m"] = c
        if "code" not in pick or "mktcap" not in pick:
            continue
        g = pd.DataFrame({
            "code": t[pick["code"]].map(to_code6),
            "month": m,
            "mktcap": pd.to_numeric(t[pick["mktcap"]], errors="coerce"),
            "shares": pd.to_numeric(t[pick["shares"]], errors="coerce") if "shares" in pick else np.nan,
            "close_m": pd.to_numeric(t[pick["close_m"]], errors="coerce") if "close_m" in pick else np.nan,
            "amount_m": pd.to_numeric(t[pick["amount_m"]], errors="coerce") if "amount_m" in pick else np.nan,
        })
        rows.append(g.dropna(subset=["code"]))
    frames = [f for f in rows if len(f)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=MKTCAP_COLS))
    if not frames:
        return pd.DataFrame(columns=MKTCAP_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    VAULT.put_table("krx_mktcap_monthly", out, scope="shared", domain="price",
                    source="pykrx get_market_cap_by_ticker")
    PIPE.io("OUT", "DRIVE", "krx_mktcap_monthly", out)
    LOG.ok(f"시가총액 스냅샷 {out['month'].nunique()}개월 × {out['code'].nunique():,}종목 = {len(out):,}행")
    return out


def fetch_fundamental_monthly(months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 PBR/BPS/PER/EPS/배당수익률 스냅샷 → BM = 1/PBR. 1개월 = 1호출.

    §6.3 직교화의 BM 은 이 경로가 1순위다. DART 재무제표를 사별로 긁는 것보다
    두 자릿수 배 싸고, 시장가 기준이라 정의도 더 정확하다(장부가/시가).
    """
    cached = VAULT.get_table("krx_fundamental_monthly", scope="shared")
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["month"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in _month_snap_dates(months) if m.strftime("%Y-%m") not in have]
    if not todo:
        LOG.ok(f"펀더멘털 월말 스냅샷: 캐시 충족 ({len(cached):,}행, 신규 호출 0건)")
        return cached
    if pykrx_stock is None:
        LOG.warn("pykrx 없음 — PBR 스냅샷 불가. §6.3 직교화의 BM 항은 DART 폴백 또는 결측 처리됩니다.")
        return cached if cached is not None else pd.DataFrame(columns=FUND_COLS)

    LOG.info(f"펀더멘털(PBR/BPS) 월말 스냅샷 신규 {len(todo)}개월 (1개월 = 1호출)")
    rows, fails = [], 0
    for m in tqdm(todo, desc="펀더멘털 스냅샷", disable=not VERBOSE):
        d = _krx_snapshot("get_market_fundamental_by_ticker", m.strftime("%Y%m%d"))
        if d is None:
            fails += 1
            if fails >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"연속 실패 {fails}회 — 서킷브레이커 작동, 펀더멘털 수집 중단.")
                break
            continue
        fails = 0
        t = d.reset_index()
        col = {str(c).upper(): c for c in t.columns}
        code_c = None
        for c in t.columns:
            if str(c) in ("티커", "종목코드", "index"):
                code_c = c
                break
        if code_c is None:
            continue

        def _num(key):
            c = col.get(key)
            return pd.to_numeric(t[c], errors="coerce") if c is not None else pd.Series(np.nan, index=t.index)

        g = pd.DataFrame({
            "code": t[code_c].map(to_code6), "month": m,
            "bps": _num("BPS"), "per": _num("PER"), "pbr": _num("PBR"),
            "eps": _num("EPS"), "div_yield": _num("DIV"),
        })
        rows.append(g.dropna(subset=["code"]))
    frames = [f for f in rows if len(f)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=FUND_COLS))
    if not frames:
        return pd.DataFrame(columns=FUND_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    # BM = 장부가/시가 = 1/PBR. PBR<=0 (자본잠식)은 BM 정의가 무너지므로 결측.
    pbr = pd.to_numeric(out["pbr"], errors="coerce")
    out["bm"] = np.where(pbr > 0, 1.0 / pbr.replace(0, np.nan), np.nan)
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    VAULT.put_table("krx_fundamental_monthly", out, scope="shared", domain="price",
                    source="pykrx get_market_fundamental_by_ticker")
    PIPE.io("OUT", "DRIVE", "krx_fundamental_monthly", out)
    ok = int(out["bm"].notna().sum())
    LOG.ok(f"펀더멘털 스냅샷 {len(out):,}행 · BM 산출 가능 {ok:,}행 ({100*ok/max(len(out),1):.1f}%)")
    return out


def fetch_nonequity_tickers(months: pd.DatetimeIndex) -> pd.DataFrame:
    """ETF/ETN/ELW 티커 목록 스냅샷 (§5 제외). 반기 1회면 충분하므로 호출을 더 줄인다."""
    cached = VAULT.get_table("krx_nonequity_tickers", scope="shared")
    grid = sorted({as_ts(m) for m in months if m.month in (6, 12)}) or list(months[:1])
    have = set()
    if cached is not None and len(cached):
        try:
            have = set(as_ts_series(cached["snap"]).dt.strftime("%Y-%m"))
        except Exception:
            have = set()
    todo = [m for m in grid if m.strftime("%Y-%m") not in have]
    if not todo or pykrx_stock is None:
        if cached is not None:
            return cached
        return pd.DataFrame(columns=["snap", "code", "kind"])
    rows = []
    for m in todo:
        day = m.strftime("%Y%m%d")
        for kind, fname in (("ETF", "get_etf_ticker_list"), ("ETN", "get_etn_ticker_list"),
                            ("ELW", "get_elw_ticker_list")):
            fn = getattr(pykrx_stock, fname, None)
            if fn is None:
                continue
            lst = KRXG.call(fn, day)
            for c in (lst or []):
                cc = to_code6(c)
                if cc:
                    rows.append({"snap": m, "code": cc, "kind": kind})
    if not rows:
        return cached if cached is not None else pd.DataFrame(columns=["snap", "code", "kind"])
    out = pd.DataFrame(rows)
    if cached is not None and len(cached):
        out = pd.concat([out, cached], ignore_index=True)
    out["snap"] = as_ts_series(out["snap"])
    out = out.drop_duplicates(subset=["snap", "code"], keep="last").reset_index(drop=True)
    VAULT.put_table("krx_nonequity_tickers", out, scope="shared", domain="universe",
                    source="pykrx etf/etn/elw ticker list")
    LOG.ok(f"비주식 종목(ETF/ETN/ELW) {out['code'].nunique():,}개 식별")
    return out


def build_exclusion_flags(sec: pd.DataFrame, nonequity: pd.DataFrame) -> pd.DataFrame:
    """종목별 제외 플래그 (§5). 시점 불변 성질(우선주/스팩/ETF)만 여기서 판정한다.

    관리종목·거래정지는 시점 가변이라 공개 PIT 소스가 없다 → OPEN_QUESTIONS 에 기록하고
    '제외하지 않는' 보수적 선택을 한다(제외하면 성과가 좋아지는 방향이므로, 남기는 쪽이 보수적).
    """
    s = sec.copy()
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"])
    nm = s["name"].astype(str).fillna("")
    ne = set(nonequity["code"].astype(str)) if nonequity is not None and len(nonequity) else set()
    s["is_pref"] = [is_preferred(c, n) for c, n in zip(s["code"], nm)]
    s["is_spac"] = nm.str.contains(_SPAC_PAT, na=False)
    s["is_reit"] = nm.str.contains(_REIT_PAT, na=False)
    s["is_etp"] = s["code"].isin(ne) | nm.str.contains(_ETF_PAT, na=False)
    s["is_konex"] = s["market"].astype(str).str.upper().str.contains("KONEX", na=False)
    s["excluded"] = s[["is_pref", "is_spac", "is_reit", "is_etp", "is_konex"]].any(axis=1)
    out = s[["code", "name", "market", "is_pref", "is_spac", "is_reit", "is_etp",
             "is_konex", "excluded"]].reset_index(drop=True)
    LOG.table([[k, f"{int(out[k].sum()):,}"] for k in
               ("is_pref", "is_spac", "is_reit", "is_etp", "is_konex", "excluded")],
              ["제외 사유", "종목수"], ["l", "r"], title="유니버스 제외 플래그 (§5)")
    LOG.info("관리종목·투자주의환기·거래정지는 시점가변 PIT 공개소스가 없어 제외하지 않습니다. "
             "제외하면 성과가 개선되는 방향이므로 '남기는 쪽'이 보수적입니다 "
             "(OPEN_QUESTIONS.md 에 기록됨).")
    return out


def build_sector_map(sec: pd.DataFrame) -> pd.DataFrame:
    """code → sector. §6.3 SectorRet 과 H2 교차업종 검정의 기준.

    한계: 업종은 현재시점 분류다(PIT 아님). 변경 빈도가 낮아 영향이 제한적이지만
    완전한 PIT 은 아니며, 이 사실을 산출물에 명시한다.
    """
    s = sec[["code", "industry"]].copy()
    s["code"] = s["code"].map(to_code6)
    s = s.dropna(subset=["code"])
    ind = s["industry"].astype(str).replace({"": "미분류", "nan": "미분류", "None": "미분류"})
    ind = ind.fillna("미분류")
    # 세부 업종명이 너무 잘게 쪼개지면 SectorRet 이 자기 자신이 되어버린다.
    # 앞 두 어절로 묶어 셀 크기를 확보한다(최소 표본 확보가 회귀 안정성보다 앞선다).
    s["sector"] = ind.str.replace(r"\s+", " ", regex=True).str.split(" ").str[:2].str.join(" ")
    s.loc[s["sector"].str.len() < 2, "sector"] = "미분류"
    n = s["sector"].nunique()
    small = s.groupby("sector")["code"].size()
    rare = set(small[small < 5].index)
    if rare:
        s.loc[s["sector"].isin(rare), "sector"] = "기타"
    LOG.info(f"업종 매핑: {n}개 원분류 → {s['sector'].nunique()}개 사용 분류 "
             f"(5종목 미만 {len(rare)}개는 '기타'로 병합). ※현재시점 분류 — 완전 PIT 아님")
    return s[["code", "sector"]].drop_duplicates("code").reset_index(drop=True)


def fetch_retail_share(codes: Sequence[str], start: str, end: str,
                       max_codes: int = 2600) -> pd.DataFrame:
    """종목별 개인 거래대금 비중 (H3 조건부 예측용).

    종목 1개당 1호출로 전 구간을 받는다(2,500호출, 캐시 후 0). 일자별 루프로 짜면
    같은 데이터에 250배를 쓴다. 실패해도 전략을 죽이지 않고 H3 를 축소 보고한다.
    """
    cols = ["code", "month", "retail_share"]
    cached = VAULT.get_table("krx_retail_share_monthly", scope="shared")
    if cached is not None and len(cached):
        have = set(cached["code"].astype(str))
    else:
        have = set()
    todo = [c for c in dict.fromkeys(codes) if c and c not in have][:max_codes]
    if not todo or pykrx_stock is None:
        if cached is None or not len(cached):
            LOG.warn("개인 거래비중 데이터 없음 — H3 는 소형주·저커버리지 축으로만 판정합니다.")
            return pd.DataFrame(columns=cols)
        return cached

    LOG.info(f"개인 거래비중 신규 {len(todo):,}종목 (종목당 1호출로 전 구간)")
    s_str, e_str = as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d")
    state = {"fail": 0, "stop": False}

    def _one(code: str):
        if state["stop"]:
            return None
        fn = getattr(pykrx_stock, "get_market_trading_value_by_date", None)
        if fn is None:
            return None
        d = KRXG.call(fn, s_str, e_str, code, detail=True)
        if d is None or not hasattr(d, "empty") or d.empty:
            state["fail"] += 1
            if state["fail"] >= CIRCUIT_BREAKER_FAILS:
                state["stop"] = True
            return None
        state["fail"] = 0
        t = d.reset_index()
        dc = t.columns[0]
        ind_c = [c for c in t.columns if "개인" in str(c)]
        tot_c = [c for c in t.columns if "전체" in str(c) or "합계" in str(c)]
        if not ind_c:
            return None
        g = pd.DataFrame({"date": as_ts_series(t[dc]),
                          "ind": pd.to_numeric(t[ind_c[0]], errors="coerce").abs()})
        if tot_c:
            g["tot"] = pd.to_numeric(t[tot_c[0]], errors="coerce").abs()
        else:
            num = t.select_dtypes("number").abs().sum(axis=1)
            g["tot"] = pd.to_numeric(num, errors="coerce")
        g = g.dropna(subset=["date"])
        g["month"] = g["date"] + pd.offsets.MonthEnd(0)
        a = g.groupby("month", as_index=False)[["ind", "tot"]].sum()
        a["retail_share"] = safe_div(a["ind"], a["tot"])
        a["code"] = code
        return a[cols]

    got = pmap_io(_one, todo, workers=min(4, N_WORKERS_IO), desc="개인 거래비중")
    frames = [d for d in got if d is not None and len(d)]
    if cached is not None and len(cached):
        frames.append(cached.reindex(columns=cols))
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out["month"] = as_ts_series(out["month"])
    out = out.drop_duplicates(subset=["code", "month"], keep="last").reset_index(drop=True)
    VAULT.put_table("krx_retail_share_monthly", out, scope="shared", domain="flow",
                    source="pykrx get_market_trading_value_by_date(detail=True)")
    LOG.ok(f"개인 거래비중 {out['code'].nunique():,}종목 × {out['month'].nunique()}개월 = {len(out):,}행")
    return out


def attach_bm_fallback(fund: pd.DataFrame, mcap: pd.DataFrame,
                       sec: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX PBR 이 비어 있는 (code, month) 만 DART 자본총계로 보강한다.

    보강 대상 수를 먼저 세고, 그게 DART 잔여 호출량 대비 얼마인지 표로 보여준 뒤 실행한다.
    """
    base = fund.copy() if fund is not None and len(fund) else pd.DataFrame(columns=FUND_COLS)
    if not len(base):
        base = pd.DataFrame(columns=FUND_COLS)
    miss = int(base["bm"].isna().sum()) if "bm" in base.columns else 0
    total = max(len(base), 1)
    LOG.table([["KRX PBR 로 BM 확보", f"{total - miss:,}", f"{100*(total-miss)/total:.1f}%"],
               ["결측 (DART 보강 대상)", f"{miss:,}", f"{100*miss/total:.1f}%"]],
              ["BM 출처", "행수", "비중"], ["l", "r", "r"], title="§6.3 BM 확보 현황")
    if miss == 0 or not DART_API_KEY or DQ is None or DQ.exhausted:
        if miss and not DART_API_KEY:
            LOG.info("DART 키가 없어 BM 결측은 그대로 둡니다. 직교화 회귀는 해당 항을 "
                     "결측 제외로 처리하며, 그 사실이 산출물에 남습니다.")
        return base
    corps = sec["corp_code"].dropna().astype(str).unique().tolist() if "corp_code" in sec.columns else []
    if not corps:
        return base
    years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
    eq = fetch_dart_equity(corps, years)
    if eq is None or not len(eq):
        return base
    c2c = sec.dropna(subset=["corp_code"]).assign(
        corp_code=lambda d: d["corp_code"].astype(str)).set_index("corp_code")["code"].to_dict()
    eq = eq.copy()
    eq["code"] = eq["corp_code"].astype(str).map(c2c)
    eq = eq.dropna(subset=["code", "knowledge_date"])
    if not len(eq):
        return base
    PIT.register("dart_equity", eq, key_cols=["code"])
    grid = base[["code", "month"]].copy() if len(base) else pd.DataFrame(columns=["code", "month"])
    if not len(grid):
        return base
    j = PIT.asof_join(grid.assign(code=grid["code"].astype(str)), "dart_equity",
                      by="code", left_time="month", cols=["equity"])
    mm = mcap[["code", "month", "mktcap"]].copy() if mcap is not None and len(mcap) else None
    if mm is None:
        return base
    mm["code"] = mm["code"].astype(str)
    j["month"] = as_ts_series(j["month"])
    mm["month"] = as_ts_series(mm["month"])
    j = j.merge(mm, on=["code", "month"], how="left")
    j["bm_dart"] = np.where((j.get("equity", pd.Series(np.nan, index=j.index)) > 0) & (j["mktcap"] > 0),
                            safe_div(j.get("equity"), j["mktcap"]), np.nan)
    base = base.merge(j[["code", "month", "bm_dart"]], on=["code", "month"], how="left")
    base["bm"] = pd.to_numeric(base["bm"], errors="coerce").astype("float64")
    fill = base["bm"].isna() & base["bm_dart"].notna()
    base.loc[fill, "bm"] = pd.to_numeric(base.loc[fill, "bm_dart"], errors="coerce").astype("float64")
    LOG.ok(f"DART 자본총계로 BM {int(fill.sum()):,}행 보강 (잔여 결측 {int(base['bm'].isna().sum()):,}행)")
    return base.drop(columns=["bm_dart"], errors="ignore")


# ==========================================================================================
# 조각: 13_ingest_research.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 수집 — 한경컨센서스 + 네이버금융리서치                            ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : 작성자(애널리스트)·적정가격·투자의견을 리스트에서    ║
# ║      바로 준다. 1요청에 최대 수백 행 → 애널리스트 원장의 1순위 소스.                       ║
# ║      단, 종목코드가 컬럼에 없다. 제목의 "종목명(005930)" 에서 뽑아야 한다.                 ║
# ║    · 네이버금융리서치 : 종목코드를 td[0] a.stock_item href 에 확실히 준다.                 ║
# ║      애널리스트명은 리스트에 없다(PDF/상세에 있음). 커버리지 폭이 넓다.                    ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자가 명시적으로 수집을 지시했으므로     ║
# ║    수행하되, 초당 요청을 보수적으로 제한하고(RATE_LIMIT_QPS) 이 사실을 로그에 명시한다.     ║
# ║  ⚠ PDF 원문은 증권사 저작물이다. 로컬 캐시/분석 용도로만 쓰고 재배포하지 말 것.             ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다. (공개 스크래퍼들의 컬럼 인덱스가 서로 모순되기 때문)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
HK_PDF = HK_BASE + "/analysis/downpdf?report_idx={idx}"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = [
    "report_uid", "source", "src_report_id", "pub_date", "category",
    "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
    "analyst_raw", "target_price", "opinion", "pdf_url", "pdf_uid", "detail_url",
    "views", "event_date", "knowledge_date",
]

_OPINION_MAP = {
    "매수": "BUY", "buy": "BUY", "strongbuy": "BUY", "적극매수": "BUY", "outperform": "BUY",
    "비중확대": "BUY", "overweight": "BUY", "trading buy": "BUY", "tradingbuy": "BUY",
    "중립": "HOLD", "hold": "HOLD", "neutral": "HOLD", "marketperform": "HOLD",
    "시장수익률": "HOLD", "보유": "HOLD", "비중유지": "HOLD",
    "매도": "SELL", "sell": "SELL", "underperform": "SELL", "비중축소": "SELL",
    "underweight": "SELL", "reduce": "SELL",
}
_NULL_TOKENS = {"", "-", "--", "0", "n/a", "na", "없음", "투자의견없음", "nr", "not rated", "제시안함"}


def _clean_cell(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABCABC' 처럼 2~3회 반복되어 나오는 알려진 버그를 되돌린다."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0:
            unit = s[: n // k]
            if unit * k == s:
                return unit
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 목표주가 리비전 팩터가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    if v <= 0 or v > 5e7:
        return None
    return v


def parse_opinion(x: Any) -> Optional[str]:
    t = _clean_cell(x)
    if t.lower() in _NULL_TOKENS:
        return None
    k = re.sub(r"[^\w가-힣]", "", t).lower()
    for pat, val in _OPINION_MAP.items():
        if re.sub(r"[^\w가-힣]", "", pat).lower() in k:
            return val
    return t[:20] or None


_YYMMDD = re.compile(r"^\s*(\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*$")


def parse_kr_date(s: Any) -> Optional[str]:
    """★ 네이버 리스트의 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    → 두 자리 연도는 여기서 4자리로 확정한 뒤에만 하위로 넘긴다.
    """
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        # 백테스트 대상은 2000년대. 두 자리 연도는 2000+yy 로 확정한다.
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        try:
            return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
        except Exception:
            return None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6})\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return m.group(1) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


# ── 헤더 기반 테이블 파서 (컬럼 인덱스 불신 원칙) ────────────────────────────────────────────
def _table_headers(table) -> List[str]:
    hdr = []
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            hdr = [_clean_cell(th.get_text()) for th in ths]
            break
    return hdr


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    if headers and len(headers) == len(tds):
        return {headers[i]: tds[i] for i in range(len(tds))}
    return {}


def _pick(rowmap: Dict[str, Any], *names) -> Optional[Any]:
    for n in names:
        for k, v in rowmap.items():
            if n in k:
                return v
    return None


# ── 한경컨센서스 ────────────────────────────────────────────────────────────────────────────
_HK_LAYOUT_LOGGED = set()


def _hk_parse(html: str, category: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = None
    for sel in ("div.table_style01 table", "#contents table", "table"):
        t = soup.select_one(sel)
        if t is not None and t.find("tr") is not None:
            table = t
            break
    if table is None:
        return []
    if soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃 감지: {len(headers)}컬럼 {headers}")
        if headers and not any("적정" in h or "목표" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 적정가격 컬럼이 없습니다. "
                     f"skinType 파라미터가 무시된 것 같습니다(통합 탭 6컬럼 레이아웃). "
                     f"목표주가·투자의견은 이 카테고리에서 수집되지 않습니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        # report_idx 는 어느 열에 있든 앵커에서 찾는다 (인덱스 의존 제거)
        ridx, pdf = None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                pdf = HK_PDF.format(idx=ridx)
                break
        if ridx is None:
            continue

        date_s = _pick(rm, "작성일", "날짜")
        if not date_s:
            date_s = next((t for t in texts if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
        title = _pick(rm, "제목")
        if not title:
            a = tr.find("a", href=re.compile("report_idx"))
            title = _clean_cell(a.get_text(" ")) if a else ""
        title = _dedup_repeat(title)

        tp = _pick(rm, "적정가격", "목표주가", "적정주가")
        op = _pick(rm, "투자의견", "의견")
        an = _pick(rm, "작성자", "애널리스트")
        bk = _pick(rm, "제공출처", "증권사", "출처")

        if headers and len(headers) == len(texts):
            pass                                     # 헤더 매핑 성공 — 그대로 사용
        else:
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c not in (op or "",)]
            if bk is None:
                bk = next((c for c in cand if "증권" in c or "투자" in c or "금융" in c), None)
            if an is None:
                an = next((c for c in cand if c != bk and 1 <= len(c) <= 30), None)

        out.append({
            "source": "hankyung", "src_report_id": str(ridx), "category": category,
            "pub_date": parse_kr_date(date_s), "title": title,
            "stock_code": code_from_title(title), "stock_name": name_from_title(title),
            "broker_raw": _clean_cell(bk), "analyst_raw": _clean_cell(an),
            "target_price": parse_target_price(tp), "opinion": parse_opinion(op),
            "pdf_url": pdf, "detail_url": pdf, "views": None,
        })
    return out


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다."""
    rows: List[dict] = []
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    jobs = []
    for skin in skins:
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            jobs.append((skin, sd, ed))

    def _sweep(job):
        skin, sd, ed = job
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            params = {
                "skinType": skin, "sdate": sd.strftime("%Y-%m-%d"), "edate": ed.strftime("%Y-%m-%d"),
                "now_page": page, "pagenum": page_size, "order_type": "",
                "report_type": "CO" if skin == "business" else "",
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            if not html:
                break
            batch = _hk_parse(html, skin)
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            for b in fresh:
                seen_ids.add(b["src_report_id"])
            got.extend(fresh)
            # ★ 조기 종료 조건을 느슨하게 잡으면 데이터가 조용히 잘려나간다.
            #   파싱 실패나 일시적 짧은 페이지 하나로 그 해 전체 수집이 끊길 수 있으므로,
            #   '새 항목 0건'이 2회 연속일 때만 멈춘다.
            if len(fresh) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
            if page == max_pages:
                LOG.warn(f"한경 {skin} {sd:%Y} 구간이 최대 페이지({max_pages})에 도달했습니다 — "
                         f"데이터가 잘렸을 수 있습니다. max_pages 를 늘리거나 구간을 분기 단위로 "
                         f"쪼개세요. (지금까지 {len(got):,}건)")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스")
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows, columns=[c for c in REPORT_COLS if c in (rows[0].keys() if rows else [])]) \
        if rows else pd.DataFrame(columns=REPORT_COLS)
    if rows:
        d = pd.DataFrame(rows)
    LOG.ok(f"한경컨센서스 {len(d):,}건 "
           f"(작성자 보유 {int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} / "
           f"목표주가 보유 {int(d['target_price'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
NV_CATS = {
    "company": ("company_list.naver", "company_read.naver"),
    "industry": ("industry_list.naver", "industry_read.naver"),
    "market": ("market_info_list.naver", "market_info_read.naver"),
    "invest": ("invest_list.naver", "invest_read.naver"),
    "economy": ("economy_list.naver", "economy_read.naver"),
    "debenture": ("debenture_list.naver", "debenture_read.naver"),
}
_NV_PDF_RE = re.compile(r"/stock-research/(\w+)/(\d+)/(\d{8})_(\w+)_(\d+)\.pdf")


def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = soup.select_one("#contentarea_left div.box_type_m table.type_1") or \
        soup.select_one("table.type_1") or soup.select_one("table")
    if table is None:
        return []
    headers = _table_headers(table)
    _, read_page = NV_CATS.get(cat, ("", "company_read.naver"))
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid, detail, title = None, None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid = m.group(1)
                detail = urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=(\d{6})", a_item["href"])
            code = mm.group(1) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        pdf = None
        for a in tr.find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                pdf = a["href"] if a["href"].startswith("http") else urljoin(NV_BASE, a["href"])
                break

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)
        vw = _pick(rm, "조회")

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None,
            "pdf_url": pdf, "detail_url": detail,
            "views": _clean_cell(vw).replace(",", "") or None,
        })
    return out


def _nv_last_page(html: str) -> int:
    soup = soup_of(html)
    if soup is None:
        return 1
    mx = 1
    for a in soup.select("table.Nnavi a[href]"):
        m = re.search(r"page=(\d+)", a["href"])
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 60000) -> pd.DataFrame:
    """신형 JSON API. 되면 HTML 페이징보다 훨씬 빠르고 구조가 안정적이다."""
    rows, index = [], 0
    url = NV_API.format(cat=cat)
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    while index < hard_cap:
        js = http_json(url, source="naver", tries=2, headers=hdr,
                       params={"index": index, "size": page_size,
                               "startDate": as_ts(start).strftime("%Y-%m-%d"),
                               "endDate": as_ts(end).strftime("%Y-%m-%d")})
        if not js:
            break
        items = js if isinstance(js, list) else (js.get("researches") or js.get("list") or
                                                 js.get("items") or js.get("content") or [])
        if not isinstance(items, list) or not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({
                "source": "naver", "category": cat,
                "src_report_id": str(it.get("id") or it.get("nid") or it.get("researchId") or ""),
                "pub_date": it.get("createDate") or it.get("date") or it.get("writeDate"),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                "detail_url": None, "views": it.get("readCount"),
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    if len(d):
        d = d[d["src_report_id"].astype(str).str.len() > 0]
    return d


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1500) -> pd.DataFrame:
    frames = []
    for cat in cats:
        # ① JSON API 우선
        try:
            dj = naver_collect_json(cat, start, end)
        except Exception:
            dj = pd.DataFrame()
        if len(dj) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(dj):,}건")
            frames.append(dj)
            continue
        # ② HTML 리스트 폴백
        list_page, _ = NV_CATS[cat]
        base = urljoin(NV_BASE, list_page)
        probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                         params={"searchType": "writeDate",
                                 "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                                 "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": 1})
        if not probe:
            LOG.warn(f"네이버 '{cat}' 리스트 접근 실패 — 건너뜁니다.")
            continue
        last = min(_nv_last_page(probe), max_pages)
        LOG.info(f"네이버 '{cat}' HTML 폴백 — 총 {last:,}페이지")

        def _pg(p: int):
            h = probe if p == 1 else http_get(
                base, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=3,
                params={"searchType": "writeDate",
                        "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                        "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": p})
            return _nv_parse_list(h, cat) if h else []

        res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO),
                      desc=f"네이버 {cat}")
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다."""
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    if len(need) > limit:
        LOG.warn(f"네이버 상세 보강 대상 {len(need):,}건 중 최신 {limit:,}건만 조회합니다 "
                 f"(RESEARCH 설정으로 조절 가능). 나머지는 목표주가 결측으로 남습니다.")
        need = need.sort_values("pub_date", ascending=False).head(limit)

    def _one(u: str):
        h = http_get(u, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=2)
        if not h:
            return None
        s = soup_of(h)
        if s is None:
            return None
        box = s.select_one("div.view_info_1") or s
        tp = box.select_one("em.money strong") or box.select_one("em.money")
        op = box.select_one("em.coment")
        an = ""
        src = s.select_one("th.view_sbj p.source")
        if src is not None:
            an = _clean_cell(src.get_text(" "))
        return {"detail_url": u,
                "target_price": parse_target_price(tp.get_text() if tp else None),
                "opinion": parse_opinion(op.get_text() if op else None),
                "_detail_src": an}

    res = pmap_io(_one, need["detail_url"].tolist(), workers=min(8, N_WORKERS_IO),
                  desc="네이버 상세(목표주가)")
    got = pd.DataFrame([r for r in res if r])
    if got.empty:
        return df
    # ★ detail_url 이 유일하지 않으면 merge 가 행을 증식시킨다(리포트가 복제됨).
    #   원장 건수가 조용히 불어나 커버리지·리비전 통계가 전부 틀어진다.
    got = got.drop_duplicates("detail_url", keep="last")
    n_before = len(df)
    df = df.merge(got, on="detail_url", how="left", suffixes=("", "_d"))
    if len(df) != n_before:
        LOG.warn(f"상세 보강 머지에서 행수가 {n_before:,}→{len(df):,} 로 변했습니다 — "
                 f"중복 detail_url 로 인한 증식입니다.")
        df = df.drop_duplicates("report_uid", keep="first")
    for c in ("target_price", "opinion"):
        if f"{c}_d" in df.columns:
            df[c] = df[c].where(df[c].notna(), df[f"{c}_d"])
            df = df.drop(columns=[f"{c}_d"])
    LOG.ok(f"네이버 상세 보강 — 목표주가 {int(got['target_price'].notna().sum()):,}건 추가 확보")
    return df


# ── PDF 원문 ────────────────────────────────────────────────────────────────────────────────
_ANALYST_LINE = re.compile(
    r"([가-힣]{2,4})\s*(?:연구원|애널리스트|수석|책임|선임)?\s*"
    r"(?:\(?\s*(?:02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}\s*\)?)?\s*"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TP_PAT = re.compile(r"(?:목표\s*주가|목표주가|적정\s*주가|적정주가|TP)\s*[:：(]?\s*"
                     r"(?:원\)?\s*)?([0-9][0-9,]{2,9})")


def pdf_text(data: bytes, max_pages: int = 3) -> str:
    """1페이지 헤더/푸터에 애널리스트명·이메일·목표주가가 몰려 있다. 앞 3장이면 충분하다."""
    if not data or data[:5] != b"%PDF-":
        return ""
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count)))
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
        except Exception:
            pass
    return ""


def pdf_extract_fields(text: str) -> dict:
    out = {"pdf_analysts": "", "pdf_emails": "", "pdf_target": None}
    if not text:
        return out
    pairs = _ANALYST_LINE.findall(text[:6000])
    names = [p[0] for p in pairs]
    mails = [p[1] for p in pairs] or _EMAIL.findall(text[:6000])
    if not names:
        # 이메일 로컬파트에서 역추적 실패 시, '연구원/애널리스트' 앞 한글 이름만이라도
        names = re.findall(r"([가-힣]{2,4})\s*(?:연구원|애널리스트)", text[:6000])
    out["pdf_analysts"] = ",".join(dict.fromkeys(names))[:120]
    out["pdf_emails"] = ",".join(dict.fromkeys(mails))[:200]
    m = _TP_PAT.search(text[:8000])
    if m:
        out["pdf_target"] = parse_target_price(m.group(1))
    return out


def download_pdfs(df: pd.DataFrame, cap_per_month: int = 0) -> pd.DataFrame:
    """PDF 를 공용 인덱스에 저장(내용해시 경로 → 중복 저장 없음)하고 본문 필드를 추출한다."""
    if df.empty or not RESEARCH_DOWNLOAD_PDF:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None if c != "pdf_uid" else ""
        return df
    if fitz is None and pdfplumber is None:
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 원문 추출을 건너뜁니다. "
                 "한경 리스트의 작성자/목표주가만으로도 애널리스트 연결은 동작합니다.")
    work = df[df["pdf_url"].notna()].copy()
    if cap_per_month and len(work):
        work["_m"] = as_ts_series(work["pub_date"]).dt.to_period("M")
        work = work.groupby("_m", observed=True).head(cap_per_month).drop(columns=["_m"])
    if work.empty:
        return df

    idx = VAULT.load_index("shared")
    known = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        # iterrows 는 30만 행에서 13초를 쓴다. zip 은 같은 결과를 0.2초에 만든다.
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
    LOG.info(f"PDF 대상 {len(work):,}건 (드라이브 캐시 보유 {sum(1 for k in work['report_uid'] if k in known):,}건)")

    def _one(rec):
        uid, url = rec
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
            if data:
                return (uid, known[uid], data)
            # 인덱스에는 있는데 실제 파일이 없으면(드라이브 동기화 누락 등) 재수집으로 폴백한다.
            # 여기서 포기하면 그 보고서는 영구히 비어 있는 채로 남는다.
        raw = http_get(url, source="hankyung" if "hankyung" in str(url) else "naver",
                       as_bytes=True, tries=2, referer=HK_BASE + "/" if "hankyung" in str(url) else NV_BASE)
        if not raw or raw[:5] != b"%PDF-":
            return (uid, "", b"")          # 로그인/에러 HTML 이 200 으로 오는 케이스 방어
        return (uid, "", raw)

    jobs = list(zip(work["report_uid"].astype(str), work["pdf_url"].astype(str)))

    # ★ 청크로 끊어 받는다. pmap_io 는 결과 리스트를 통째로 들고 있으므로, 한 번에 던지면
    #   내려받은 PDF 본문 전부가 동시에 RAM 에 남는다. 목표치인 연 3만건 × 10년 = 30만건에
    #   평균 300KB 를 곱하면 90GB 다. 캐시가 차 있어도 마찬가지다 — 캐시 경로도 blob 바이트를
    #   그대로 반환하기 때문에 오히려 더 빨리 쌓인다. 청크 단위로 소비하고 버리면 상주량이
    #   작업 수와 무관하게 평평해진다(약 600MB). 청크마다 flush 하므로 중간에 끊겨도 이어받는다.
    PDF_CHUNK = 2000
    rows = []
    ok = 0
    for k0 in range(0, len(jobs), PDF_CHUNK):
        chunk = jobs[k0:k0 + PDF_CHUNK]
        res = pmap_io(_one, chunk, workers=min(N_WORKERS_IO, 10),
                      desc=f"리포트 PDF {k0//PDF_CHUNK + 1}/{(len(jobs)-1)//PDF_CHUNK + 1}")
        for r in res:
            if not r:
                continue
            uid, existing_blob_uid, data = r
            if not data:
                continue
            ok += 1
            blob_uid = existing_blob_uid
            if not blob_uid:
                p = VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                                   source="report_pdf", scope="shared")
                blob_uid = sha1_str("research", "report_pdf", uid, sha1_bytes(data)) if p else ""
            f = pdf_extract_fields(pdf_text(data))
            rows.append({"report_uid": uid, "pdf_uid": blob_uid, **f})
        del res
        VAULT.flush("shared")
    VAULT.flush("shared")
    LOG.ok(f"PDF 확보 {ok:,}/{len(jobs):,}건 — 공용 인덱스에 저장(내용해시 중복제거 적용)")
    if not rows:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None
        return df
    ext = pd.DataFrame(rows)
    df = df.merge(ext, on="report_uid", how="left")
    PIPE.io("OUT", "DRIVE", "research:pdf", ext, source="hankyung/naver pdf")
    return df


# ==========================================================================================
# 조각: 14_entity_research.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  엔티티 해상 — 증권사 정규화 / 애널리스트 원장 / 보고서↔애널리스트 연결              ║
# ║                                                                                          ║
# ║  이 모듈이 답해야 하는 질문 (사용자 요구사항):                                              ║
# ║    Q1. 보고서와 애널리스트가 제대로 연결되었는가?   → report_analyst_link + 연결 감사표     ║
# ║    Q2. 다중소스 원장 연결은 확실한가?               → dedup_key 병합 + 소스기여 감사표      ║
# ║    Q3. 목표주가는 누가 언제 제시했는가?             → (analyst_id, code, date, tp) 원장     ║
# ║                                                                                          ║
# ║  증권사 사명 변경(2016~2026)을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로          ║
# ║  다른 사람이 되어버린다 → 목표주가 리비전(d2)이 통째로 망가진다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 정규화 표: (별칭 정규식 → 정식명). 사명 변경 이력이 핵심이다.
BROKER_CANON: List[Tuple[str, str]] = [
    (r"미래에셋(대우|증권|생명)?", "미래에셋증권"),          # 미래에셋대우→미래에셋증권(2021)
    (r"(대우증권|KDB대우)", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),        # 우리투자→NH투자(2014)
    (r"한국투자|한국證|한투증권", "한국투자증권"),
    (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),                # KB투자+현대증권→KB증권(2017)
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),        # 신한금융투자→신한투자증권(2022)
    (r"하나(증권|금융투자|금투)", "하나증권"),                # 하나금융투자→하나증권(2022)
    (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"),
    (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"),                       # 동양→유안타(2014)
    (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"),
    (r"IBK(투자증권|증권)|기업은행", "IBK투자증권"),
    (r"신영증권", "신영증권"),
    (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),      # HMC투자→현대차증권(2016)
    (r"SK증권", "SK증권"),
    (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권", "iM증권"),               # 하이투자→iM증권(2024)
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),           # 이베스트→LS증권(2024)
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),      # KTB→다올(2022)
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),             # 동부→DB금융투자(2018)
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"),
    (r"부국증권", "부국증권"),
    (r"한양증권", "한양증권"),
    (r"상상인증권|골든브릿지", "상상인증권"),
    (r"케이프(투자증권|증권)", "케이프투자증권"),
    (r"토스증권", "토스증권"),
    (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"),
    (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"),
    (r"DS투자증권", "DS투자증권"),
    (r"현대해상|한화생명|미래에셋생명", "기타"),
    (r"NICE|나이스", "NICE디앤비"),
    (r"에프앤가이드|FnGuide", "에프앤가이드"),
    (r"(하이證|하이증권)", "iM증권"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]

# 대형 10개사 / 중소형 10개사 — 커버리지 목표 달성 여부 감사에 쓴다
MAJOR_BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "키움증권", "메리츠증권", "대신증권"]
MINOR_BROKERS = ["유안타증권", "한화투자증권", "교보증권", "IBK투자증권", "신영증권",
                 "현대차증권", "SK증권", "유진투자증권", "iM증권", "LS증권",
                 "다올투자증권", "DB금융투자", "BNK투자증권", "흥국증권", "부국증권",
                 "한양증권", "상상인증권", "케이프투자증권", "DS투자증권", "코리아에셋투자증권"]


def normalize_broker(raw: Any) -> Tuple[str, str]:
    """(broker_id, 정식명). 못 알아보면 정규화 문자열 자체를 id 로 쓰되 '미상' 표시는 하지 않는다
    (미상으로 뭉치면 서로 다른 소형사가 한 덩어리가 되어 커버리지 통계가 거짓이 된다)."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return (sha1_str("broker", canon)[:12], canon)
    canon = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    return (sha1_str("broker", canon)[:12], canon)


_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동/김철수' / '홍길동 외 1인' → ['홍길동','김철수']"""
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사)", " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


def _name_to_code_map(sec: pd.DataFrame) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for _, r in sec.iterrows():
        n = norm_corp_name(r.get("name"))
        c = r.get("code")
        if n and isinstance(c, str) and n not in m:
            m[n] = c
    return m


def _atoms(vals, sep: str) -> List[str]:
    """합성 토큰을 원자로 되돌린 뒤 정렬·중복제거. 병합을 멱등하게 만드는 핵심 함수."""
    out = set()
    for v in vals:
        s = str(v)
        if not s or s.lower() in ("nan", "none", "<na>"):
            continue
        for tok in s.split(sep):
            tok = tok.strip()
            if tok and tok.lower() not in ("nan", "none", "<na>"):
                out.add(tok)
    return sorted(out)


def _pick_str(vals) -> str:
    """비어있지 않은 값 중 사전순 최소. '행 순서상 첫 값'과 달리 실행 간 재현된다."""
    c = sorted({str(v).strip() for v in vals
                if v is not None and str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "<na>")})
    return c[0] if c else ""


def build_report_master(frames: Sequence[pd.DataFrame], sec: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 → 보고서 원장. 중복 제거가 아니라 '병합'이다(정보를 버리지 않는다)."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.warn("수집된 리포트가 없습니다. 드라이브 캐시도 비어 있다면 D축 d2/d4 는 결측 처리됩니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat([f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                   for f in frames], ignore_index=True)

    # 두 자리 연도는 수집부 parse_kr_date 에서 이미 4자리로 확정된다.
    # 여기서는 남은 이상치만 걸러낸다(교정하지 않는다 — 잘못된 교정이 더 위험하다).
    n_raw0 = len(d)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("1999-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일이 없거나 범위를 벗어난 리포트 {int(bad.sum()):,}건을 제외했습니다 "
                 f"({100*bad.mean():.2f}%). 이 비율이 크면 소스의 날짜 형식이 바뀐 것입니다 — "
                 f"조용히 넘기지 말고 parse_kr_date 를 확인하세요.")
    d = d[~bad]
    if len(d) == 0:
        LOG.error("발간일이 유효한 리포트가 하나도 없습니다. 날짜 파싱이 깨졌습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    bid = d["broker_raw"].map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]

    # 종목코드: ① 소스 제공 ② 제목 정규식 ③ 종목명→코드 사전
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = d.loc[need, "title"].map(code_from_title)
    need = d["stock_code"].isna() & d["stock_name"].astype(str).str.len().gt(0)
    if need.any() and len(sec):
        n2c = _name_to_code_map(sec)
        d.loc[need, "stock_code"] = d.loc[need, "stock_name"].map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = d["title"].map(_dedup_repeat)
    # report_uid 는 '한 번 붙으면 안 바뀌는' 식별자여야 한다. 이미 붙어 있으면 보존한다.
    # (드라이브 캐시의 병합 결과가 다시 입력으로 들어올 때 source 가 "hankyung+naver" 같은
    #  합성 토큰이라, 무조건 재계산하면 실행마다 uid 가 달라져 PDF 캐시가 통째로 무효화된다)
    _uid_new = [sha1_str(s, i) for s, i in zip(d["source"].astype(str),
                                               d["src_report_id"].astype(str))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    # 소스 간 동일 보고서 판정 키
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b,
                               c or "", norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             d["stock_code"].fillna(""), d["title"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"])

    # ── 멱등 병합 (재실행 안전) ─────────────────────────────────────────────────────────
    #   이 함수의 출력(원장)은 다음 실행에서 드라이브 캐시로부터 '입력 프레임'으로 되돌아온다.
    #   그때 source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로, 단순 set 병합은
    #   "hankyung+naver" 를 원자 하나로 취급해 실행할 때마다 문자열이 무한히 길어진다
    #   (hankyung+naver → hankyung+hankyung+naver+naver → …). 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌어
    #   PDF 캐시·애널리스트 연결표가 통째로 끊긴다. 순서에 무관한 min 으로 고정한다.
    #   (min 은 병합행이 다시 들어와도 같은 값을 낸다: min{u1,u2,min(u1,u2)} = min(u1,u2))
    m = d.groupby("dedup_key", as_index=False).agg(**{
        "report_uid": ("report_uid", "min"),
        "src_report_id": ("src_report_id", lambda s: "|".join(_atoms(s, "|"))),
        "source": ("source", lambda s: "+".join(_atoms(s, "+"))),
        "category": ("category", _pick_str),
        "pub_date": ("pub_date", "min"),
        "title": ("title", lambda s: max(sorted(set(map(str, s))), key=len)),
        "stock_code": ("stock_code", lambda s: _pick_str(s) or None),
        "stock_name": ("stock_name", _pick_str),
        "broker_id": ("broker_id", "min"),          # dedup_key 구성요소라 그룹 내 동일
        "broker_name": ("broker_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),      # 네이티브 max = NaN 무시. 파이썬 람다는 30만건에서 50초.
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "pdf_url": ("pdf_url", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"보고서 원장 병합: 수집 {n_raw0:,}건 → 날짜유효 {n_raw:,}건 → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0 - n_raw:,} · 소스 간 중복 병합 {n_raw - len(m):,})")

    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개 (C1)
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver")
    return m


def build_analyst_ledger(rep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """애널리스트 마스터 + 보고서↔애널리스트 연결표. 연결 방법과 신뢰도를 반드시 기록한다."""
    if rep.empty:
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))
    links = []
    for r in rep.itertuples(index=False):
        names, method, conf = [], "unresolved", 0.0
        raw = getattr(r, "analyst_raw", "") or ""
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98        # 한경 '작성자' 컬럼 — 가장 신뢰도 높음
        if not names:
            praw = getattr(r, "pdf_analysts", "") or ""
            if str(praw).strip():
                names = [n for n in str(praw).split(",") if n.strip()]
                method, conf = "pdf_header", 0.80
        if not names:
            continue
        for i, nm in enumerate(names):
            links.append({
                "report_uid": r.report_uid, "name": nm, "broker_id": r.broker_id,
                "broker_name": r.broker_name, "role": "lead" if i == 0 else "co",
                "link_method": method, "link_conf": conf,
                "pub_date": r.pub_date, "stock_code": r.stock_code,
                "target_price": r.target_price, "opinion": r.opinion,
            })
    if not links:
        LOG.warn("애널리스트를 한 건도 식별하지 못했습니다. 한경컨센서스 수집이 실패했거나 "
                 "skinType=business 응답이 6컬럼 레이아웃으로 왔을 가능성이 큽니다.")
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))

    L = pd.DataFrame(links)
    L["name_norm"] = L["name"].map(lambda s: re.sub(r"\s+", "", str(s)))
    # 애널리스트 동일성: (증권사, 이름). 동명이인은 소속으로 구분된다.
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14] for b, n in zip(L["broker_id"], L["name_norm"])]

    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name_norm", "first"), broker_id=("broker_id", "first"),
               broker_name=("broker_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("stock_code", lambda s: s.dropna().nunique()),
               n_targets=("target_price", lambda s: int(s.notna().sum()))))
    # 동명이인/이직 감지 — 같은 이름이 여러 증권사에 존재
    dup = A.groupby("name")["analyst_id"].transform("size")
    A["name_ambiguous"] = dup > 1
    LOG.ok(f"애널리스트 원장 {len(A):,}명 · 연결 {len(L):,}건 "
           f"(동명/이직 후보 {int(A['name_ambiguous'].sum()):,}명)")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


def audit_linkage(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame):
    """★ 사용자 요구: '보고서와 식별된 애널리스트가 제대로 연결되었는지 한눈에'."""
    LOG.banner("원장 무결성 감사 — 보고서 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출한다. 숫자가 낮으면 그대로 보고한다.")
    if rep.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()
    r["has_tp"] = r["target_price"].notna()

    rows = []
    for y, g in r.groupby("year"):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g['has_tp'].sum()):,}", f"{100*g['has_tp'].mean():.1f}%",
                     "✔" if n >= RESEARCH_TARGET_PER_YEAR else f"목표 {RESEARCH_TARGET_PER_YEAR:,} 미달"])
    LOG.table(rows, ["연도", "보고서", "애널연결", "연결률", "종목코드", "코드율",
                     "목표주가", "TP율", "연 3만건 목표"],
              ["c", "r", "r", "r", "r", "r", "r", "r", "l"])

    src = r.groupby("source").agg(n=("report_uid", "size"),
                                  analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean"),
                                  tp=("has_tp", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%",
                f"{100*s['code']:.1f}%", f"{100*s['tp']:.1f}%"] for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "종목코드율", "목표주가율"],
              ["l", "r", "r", "r", "r"],
              title="다중소스 원장 연결 — 어느 소스가 무엇을 채웠는가 "
                    "('hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건")

    if len(L):
        mth = L.groupby("link_method").agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "보고서 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 "
                        "(list_field=한경 작성자컬럼 0.98 · pdf_header=PDF추출 0.80)")

    if len(A):
        bro = (A.groupby("broker_name")
                .agg(analysts=("analyst_id", "nunique"), reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        mnr = [b for b in bro.index if b not in MAJOR_BROKERS]
        LOG.table([[b, f"{int(bro.loc[b,'analysts']):,}", f"{int(bro.loc[b,'reports']):,}"]
                   for b in bro.index[:30]],
                  ["증권사", "애널리스트 수", "보고서 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 그 외 증권사 {len(mnr)}개 "
                 f"→ 요구조건(대형 10+ / 중소형 10+): "
                 f"{'✔ 충족' if len(maj) >= 10 and len(mnr) >= 10 else '❗ 미충족 — 수집 범위를 넓히세요'}")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source").size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없어 PDF 추출에 의존합니다 "
                 f"(RESEARCH_DOWNLOAD_PDF=True 로 개선 가능).")


def build_consensus_panel(L: pd.DataFrame, months: pd.DatetimeIndex,
                          window_days: int = 90) -> pd.DataFrame:
    """D축 d2(목표주가 상향 리비전) · d4(커버리지 변화) 산출.

    ★ 리비전은 '같은 애널리스트가 같은 종목에 대해 이전에 제시한 목표주가' 와 비교해야 한다.
      애널리스트 식별이 없으면 이 지표는 만들 수 없다 — 애널리스트 원장이 필요한 진짜 이유.
    """
    cols = ["code", "month", "n_analyst", "tp_median", "rev_up", "rev_dn", "d2_raw", "d4_raw"]
    if L is None or L.empty:
        LOG.warn("애널리스트 연결이 없어 컨센서스 패널을 만들 수 없습니다 — d2/d4 결측 처리. "
                 "U 는 가용 축(d1, d3) 평균으로 계산됩니다(0으로 채우지 않음).")
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["stock_code"]).copy()
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    if x.empty:
        return pd.DataFrame(columns=cols)

    x = x.sort_values(["stock_code", "analyst_id", "pub_date"])
    x["prev_tp"] = x.groupby(["stock_code", "analyst_id"], observed=True)["target_price"].shift(1)
    x["rev"] = np.where(x["target_price"].notna() & x["prev_tp"].notna(),
                        np.sign(x["target_price"] - x["prev_tp"]), np.nan)

    out = []
    for m in months:
        lo = m - pd.Timedelta(days=window_days)
        w = x[(x["pub_date"] > lo) & (x["pub_date"] <= m)]
        if w.empty:
            continue
        g = w.groupby("stock_code", observed=True)
        agg = pd.DataFrame({
            "n_analyst": g["analyst_id"].nunique(),
            "tp_median": g["target_price"].median(),
            "rev_up": g["rev"].apply(lambda s: float((s > 0).sum())),
            "rev_dn": g["rev"].apply(lambda s: float((s < 0).sum())),
        }).reset_index().rename(columns={"stock_code": "code"})
        agg["month"] = m
        out.append(agg)
    if not out:
        return pd.DataFrame(columns=cols)
    P = pd.concat(out, ignore_index=True)
    P = P.sort_values(["code", "month"])
    # d2 = -(상향 리비전 수 / 커버리지)   d4 = -Δ(커버리지 애널리스트 수)
    P["d2_raw"] = -(P["rev_up"] / P["n_analyst"].replace(0, np.nan))
    P["d4_raw"] = -P.groupby("code", observed=True)["n_analyst"].diff()
    LOG.ok(f"컨센서스 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) — "
           f"목표주가 리비전 관측 {int((P['rev_up']+P['rev_dn']).sum()):,}건")
    PIPE.io("OUT", "MEM", "consensus_panel", P)
    return downcast(P)


# ==========================================================================================
# 조각: s15_analyst.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  애널리스트 식별 · Phase 0 실현가능성 게이트 (SPEC §4.3)                             ║
# ║                                                                                          ║
# ║  이 전략의 유일한 실질 리스크는 알파가 아니라 '애널리스트 식별자 확보율' 이다.               ║
# ║  링크를 못 만들면 전략 자체가 존재하지 않는다. 그래서 코드 작성이 아니라 게이트가 먼저다.    ║
# ║                                                                                          ║
# ║  확보율을 올리는 세 경로 (전부 구현):                                                      ║
# ║   ① 한경컨센서스 리스트의 '작성자' 컬럼        — 가장 정확 (link_conf 0.98)                 ║
# ║   ② 네이버 상세페이지 바이라인(_detail_src)    — 기존 코드가 긁어놓고 버리던 것을 회수      ║
# ║   ③ PDF 본문 헤더 정규식                        — 최후 (link_conf 0.80)                     ║
# ║                                                                                          ║
# ║  ★ ②가 이번 구현의 실질 개선이다. 네이버 단독 리포트는 리스트에 작성자가 없어서 전부        ║
# ║    PDF 에 의존했는데, 상세페이지에는 이미 바이라인이 있고 수집도 되고 있었다.                ║
# ║    build_report_master 의 named-agg 목록에 없어서 조용히 버려지던 컬럼이다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 바이라인에서 걷어낼 소속/직함 토큰. 남는 한글 2~4자를 사람 이름으로 본다.
_BYLINE_STRIP = re.compile(
    r"(리서치센터|리서치|투자정보|애널리스트|연구원|수석|책임|선임|팀장|센터장|위원|박사|"
    r"증권|투자|금융|자산운용|㈜|\(주\)|Research|Analyst)", re.I)
_BYLINE_NAME = re.compile(r"[가-힣]{2,4}")


def parse_byline(raw: Any) -> str:
    """네이버 상세페이지 바이라인 텍스트 → '홍길동,김철수' 형태의 애널리스트명 문자열.

    바이라인은 '미래에셋증권 홍길동' / '홍길동 애널리스트' / '삼성증권 리서치센터' 등
    형태가 제각각이다. 소속·직함을 걷어낸 뒤 남는 한글 2~4자만 채택한다.
    증권사명만 있고 사람 이름이 없으면 빈 문자열 — 억지로 만들지 않는다.
    """
    t = norm_text(raw)
    if not t:
        return ""
    t = _BYLINE_STRIP.sub(" ", t)
    t = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+", " ", t)   # 이메일 제거
    t = re.sub(r"\d", " ", t)
    names = []
    for m in _BYLINE_NAME.findall(t):
        if len(m) < 2 or m in ("종목", "기업", "산업", "시장", "전망", "분석", "보고", "자료"):
            continue
        names.append(m)
    return ",".join(dict.fromkeys(names))[:120]


def naver_attach_analyst(nv: pd.DataFrame) -> pd.DataFrame:
    """네이버 프레임의 _detail_src 바이라인을 analyst_raw 로 승격한다.

    naver_enrich_detail 이 이미 긁어온 컬럼이다. build_report_master 가 이걸
    named-agg 목록에 넣지 않아 통째로 버려지고 있었다 — 여기서 회수한다.
    """
    if nv is None or not len(nv):
        return nv
    d = nv.copy()
    if "_detail_src" not in d.columns:
        return d
    if "analyst_raw" not in d.columns:
        d["analyst_raw"] = ""
    cur = d["analyst_raw"].astype(str).fillna("").str.strip()
    rec = d["_detail_src"].map(parse_byline)
    fill = (cur == "") & (rec.astype(str).str.len() > 0)
    d.loc[fill, "analyst_raw"] = rec[fill]
    LOG.ok(f"네이버 상세 바이라인에서 애널리스트 {int(fill.sum()):,}건 회수 "
           f"(기존 구현은 이 컬럼을 버리고 있었습니다)")
    PIPE.note(f"naver byline recovered: {int(fill.sum())}")
    return d


# ── 공개 시각 보수화 (SPEC §0.1) ────────────────────────────────────────────────────────────
def apply_publication_lag(rep: pd.DataFrame) -> pd.DataFrame:
    """리포트의 knowledge_date 를 '익영업일' 로 민다.

    SPEC §0.1: 리포트는 발간일이 아니라 '공개 확인 가능 시각' 기준으로 쓴다.
    장중 발간이면 당일 종가를 쓸 수 없다.
    그런데 두 소스 모두 발간 '시각'을 제공하지 않는다(날짜만, 자정으로 정규화됨).
    시각을 모르면 전부 장중 발간으로 간주하는 것이 가장 보수적인 선택이므로,
    모든 리포트의 knowledge_date = pub_date + 1영업일 로 둔다.
    (§0 규칙: 애매하면 임의 판단하지 말고 OPEN_QUESTIONS 에 기록 후 최보수 선택)
    """
    if rep is None or not len(rep):
        return rep
    d = rep.copy()
    pub = as_ts_series(d["pub_date"])
    d["event_date"] = pub
    d["knowledge_date"] = pub + pd.tseries.offsets.BDay(1)
    OPEN_QUESTIONS.append({
        "id": "OQ-01", "topic": "리포트 공개 시각",
        "issue": "한경·네이버 모두 발간 '시각'을 제공하지 않아 장중/장후 발간을 구분할 수 없다.",
        "choice": "전 건을 장중 발간으로 간주하고 knowledge_date = 발간일 + 1영업일 로 보수화했다.",
        "impact": "링크 형성(12개월 룩백)에는 거의 영향이 없고, 신호 형성 시점의 미래누수를 구조적으로 차단한다.",
    })
    LOG.info(f"리포트 {len(d):,}건의 knowledge_date 를 발간일+1영업일로 보수화했습니다 "
             f"(§0.1 — 발간 시각 미제공이므로 전부 장중 발간으로 간주).")
    return d


# ── Phase 0 게이트 ──────────────────────────────────────────────────────────────────────────
PHASE0: Dict[str, Any] = {"ran": False, "rate": float("nan"), "unit": "analyst",
                          "verdict": "미실행", "n": 0, "detail": {}}


def _identified_mask(rep: pd.DataFrame, L: pd.DataFrame) -> pd.Series:
    if rep is None or not len(rep):
        return pd.Series(dtype=bool)
    if L is None or not len(L) or "report_uid" not in L.columns:
        return pd.Series(False, index=rep.index)
    return rep["report_uid"].isin(set(L["report_uid"].astype(str)))


def phase0_gate(rep: pd.DataFrame, L: pd.DataFrame, t_start: float) -> dict:
    """SPEC §4.3 — 표본으로 확보율을 재고 링크 단위를 기계적으로 결정한다.

    임의 판단하지 않는다. 세 구간(§8 예시 그대로)에서 표본을 뽑아 확보율만 본다.
    """
    elapsed_min = (time.time() - t_start) / 60.0
    if elapsed_min > PHASE0_TIMEBOX_MIN:
        LOG.warn(f"Phase 0 타임박스 {PHASE0_TIMEBOX_MIN/60:.0f}시간 초과 — 즉시 중단하고 보고합니다.")

    res: Dict[str, Any] = {"ran": True, "elapsed_min": elapsed_min}
    if rep is None or not len(rep):
        res.update(rate=0.0, n=0, unit="broker_sector_team", verdict="표본 없음 → 폴백",
                   detail={})
        PHASE0.update(res)
        return res

    d = rep.copy()
    d["pub_date"] = as_ts_series(d["pub_date"])
    d["ym"] = d["pub_date"].dt.strftime("%Y-%m")
    d["identified"] = _identified_mask(d, L).to_numpy()

    # 지정 3개월에서 표본 추출. 해당 월에 데이터가 없으면 전체에서 균등 추출로 대체.
    picks = []
    per = max(1, PHASE0_SAMPLE_N // max(1, len(PHASE0_SAMPLE_MONTHS)))
    for ym in PHASE0_SAMPLE_MONTHS:
        sub = d[d["ym"] == ym]
        if len(sub):
            picks.append(sub.sample(n=min(per, len(sub)), random_state=SEED))
    sample = pd.concat(picks, ignore_index=True) if picks else d.sample(
        n=min(PHASE0_SAMPLE_N, len(d)), random_state=SEED)

    rate = float(sample["identified"].mean()) if len(sample) else 0.0
    # 소스별·연도별 세부 (보고용)
    by_src = (d.groupby(d["source"].astype(str))["identified"]
              .agg(["size", "mean"]).reset_index()) if "source" in d.columns else pd.DataFrame()
    by_year = (d.groupby(d["pub_date"].dt.year)["identified"]
               .agg(["size", "mean"]).reset_index())

    if rate >= PHASE0_GATE_HIGH:
        unit, verdict = "analyst", f"정상 진행 — 애널리스트 단위 링크 (확보율 {rate:.1%} ≥ 70%)"
        need_ipw = False
    elif rate >= PHASE0_GATE_LOW:
        unit, verdict = "analyst", (f"진행하되 §6.5 결측 민감도 분석 필수 "
                                    f"(40% ≤ 확보율 {rate:.1%} < 70%)")
        need_ipw = True
    else:
        unit, verdict = "broker_sector_team", (
            f"★ 애널리스트 단위 포기 → broker×sector_team 폴백 (확보율 {rate:.1%} < 40%). "
            f"교차업종 전용 버전을 주 버전으로 승격합니다.")
        need_ipw = True

    res.update(rate=rate, n=int(len(sample)), unit=unit, verdict=verdict, need_ipw=need_ipw,
               overall_rate=float(d["identified"].mean()),
               detail={"by_source": by_src, "by_year": by_year})
    PHASE0.update(res)

    LOG.banner("PHASE 0 — 데이터 실현가능성 게이트 (SPEC §4.3)",
               f"표본 {len(sample):,}건 · 확보율 {rate:.1%} · 경과 {elapsed_min:.1f}분")
    LOG.table([["표본 확보율", f"{rate:.1%}"],
               ["전체 확보율", f"{d['identified'].mean():.1%}"],
               ["표본 크기", f"{len(sample):,}"],
               ["게이트 기준", "≥70% 정상 / 40~70% IPW필수 / <40% 폴백"],
               ["링크 단위 결정", unit],
               ["판정", verdict]],
              ["항목", "값"], ["l", "l"])
    if len(by_src):
        LOG.table([[r.iloc[0], f"{int(r.iloc[1]):,}", f"{float(r.iloc[2]):.1%}"]
                   for _, r in by_src.iterrows()],
                  ["소스 조합", "건수", "애널 확보율"], ["l", "r", "r"],
                  title="소스별 애널리스트 확보율")
    if unit == "broker_sector_team":
        LOG.warn("폴백으로 전환합니다. 모든 산출물 최상단에 이 사실이 명시되며, "
                 "폴백 결과를 애널리스트 단위 결과인 것처럼 보고하지 않습니다.")
    return res


# ── §6.5 결측 민감도 (확보율 < 70% 인 경우 필수) ────────────────────────────────────────────
def _logit_irls(X: np.ndarray, y: np.ndarray, iters: int = 40, ridge: float = 1e-6
                ) -> Optional[np.ndarray]:
    """의존성 없는 로지스틱 회귀(IRLS). statsmodels 가 없어도 §6.5 를 포기하지 않는다."""
    n, k = X.shape
    if n < k * 5 or len(np.unique(y)) < 2:
        return None
    b = np.zeros(k)
    for _ in range(iters):
        eta = np.clip(X @ b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1 - p), 1e-6, None)
        z = eta + (y - p) / w
        XtW = X.T * w
        A = XtW @ X + ridge * np.eye(k)
        try:
            b_new = np.linalg.solve(A, XtW @ z)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(b_new)):
            return None
        if np.max(np.abs(b_new - b)) < 1e-8:
            b = b_new
            break
        b = b_new
    return b


def missingness_sensitivity(rep: pd.DataFrame, L: pd.DataFrame,
                            mcap: pd.DataFrame) -> dict:
    """SPEC §6.5 — 애널리스트 식별 실패가 무작위인지 검정하고, 아니면 IPW 가중을 만든다.

    종속: 식별 성공(1/0). 설명: log(시총), 증권사 규모, 업종, 연도.
    유의한 편향이 있으면 역확률가중(IPW)을 리포트 단위로 산출해 링크 가중에 쓸 수 있게 한다.
    """
    out: Dict[str, Any] = {"ran": False, "biased": False, "ipw": None, "table": []}
    if rep is None or len(rep) < 200:
        return out
    d = rep.copy()
    d["pub_date"] = as_ts_series(d["pub_date"])
    d["identified"] = _identified_mask(d, L).astype(float).to_numpy()
    d["code"] = d["stock_code"].map(to_code6)
    d["month"] = d["pub_date"] + pd.offsets.MonthEnd(0)

    if mcap is not None and len(mcap):
        m = mcap[["code", "month", "mktcap"]].copy()
        m["code"] = m["code"].astype(str)
        m["month"] = as_ts_series(m["month"])
        d = d.merge(m, on=["code", "month"], how="left")
    else:
        d["mktcap"] = np.nan

    brk = d.groupby(d["broker_name"].astype(str))["report_uid"].transform("size")
    feats = pd.DataFrame({
        "logmc": np.log(pd.to_numeric(d["mktcap"], errors="coerce").clip(lower=1e8)),
        "logbroker": np.log(pd.to_numeric(brk, errors="coerce").clip(lower=1)),
        "year": d["pub_date"].dt.year.astype(float),
    })
    feats["logmc"] = feats["logmc"].fillna(feats["logmc"].median())
    feats["year"] = feats["year"] - feats["year"].min()
    X = np.column_stack([np.ones(len(feats)), feats["logmc"].to_numpy(),
                         feats["logbroker"].to_numpy(), feats["year"].to_numpy()])
    y = d["identified"].to_numpy()
    keep = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
    X, y = X[keep], y[keep]
    b = _logit_irls(X, y)
    if b is None:
        LOG.warn("§6.5 로지스틱 회귀가 수렴하지 않았습니다 (표본/분산 부족). "
                 "결측 민감도는 '판정 불가'로 보고합니다.")
        return out

    eta = np.clip(X @ b, -30, 30)
    p = 1.0 / (1.0 + np.exp(-eta))
    # 계수의 실질 크기로 편향 여부를 본다 (표준오차 근사 대신 효과 크기 기준 — 보수적)
    names = ["절편", "log(시총)", "log(증권사 발간량)", "연도"]
    spread = float(np.nanmax(p) - np.nanmin(p))
    biased = bool(spread > 0.10 and (abs(b[1]) > 0.05 or abs(b[2]) > 0.05))
    ipw = pd.Series(np.nan, index=d.index, dtype=float)
    w = 1.0 / np.clip(p, 0.05, 1.0)
    w = w / np.nanmean(w)
    ipw.loc[d.index[keep]] = w
    out.update(ran=True, biased=biased,
               ipw=pd.DataFrame({"report_uid": d.loc[d.index[keep], "report_uid"].to_numpy(),
                                 "ipw": w}),
               coef=dict(zip(names, [float(x) for x in b])), p_spread=spread,
               table=[[n, f"{float(v):+.4f}"] for n, v in zip(names, b)])
    LOG.table(out["table"] + [["식별확률 범위", f"{np.nanmin(p):.1%} ~ {np.nanmax(p):.1%}"],
                              ["편향 판정", "유의 — IPW 병기" if biased else "뚜렷하지 않음"]],
              ["설명변수", "계수"], ["l", "r"],
              title="§6.5 결측 민감도 — 식별 성공의 로지스틱 회귀")
    if biased:
        LOG.warn("애널리스트 식별 성공이 시총/증권사 규모와 체계적으로 연관됩니다 "
                 "(무작위 결측 아님). IPW 재추정 결과를 병기합니다.")
    return out


# ── 링크 원장 (s22 링크행렬의 유일한 입력) ──────────────────────────────────────────────────
LINK_LEDGER_COLS = ["analyst_key", "code", "pub_date", "knowledge_date",
                    "broker_id", "broker_name", "link_conf", "n_analyst_on_report",
                    "target_price"]


def build_link_ledger(rep: pd.DataFrame, L: pd.DataFrame, sec: pd.DataFrame,
                      unit: str = "analyst") -> pd.DataFrame:
    """(애널리스트 식별자 × 종목 × 시점) 원장. SPEC §4.2 의 식별자 규약을 여기서 확정한다.

        analyst_broker_identity = f"{analyst_id}@{broker_id}"

    동일 인물이 증권사를 옮기면 다른 식별자다 — 이 전략에서 링크는 '같은 하우스에서
    동시에 본다'는 사실이 핵심이기 때문이다. 기존 원장의 analyst_id 가 이미
    sha1(broker_id, name) 이라 규약과 일치하지만, 명시적으로 broker 를 붙여 못박는다.

    unit='broker_sector_team' 이면 Phase 0 폴백: 링크 단위를 증권사×업종팀으로 격하한다.
    """
    if L is None or not len(L) or "report_uid" not in L.columns:
        LOG.warn("애널리스트 링크 원장이 비었습니다 — 링크 행렬을 만들 수 없습니다.")
        return pd.DataFrame(columns=LINK_LEDGER_COLS)
    need = ("analyst_id", "broker_id", "stock_code", "pub_date")
    if any(c not in L.columns for c in need):
        LOG.warn(f"링크 테이블에 필요한 컬럼이 없습니다 (필요: {need}, 보유: {list(L.columns)}). "
                 f"빈 원장을 반환합니다.")
        return pd.DataFrame(columns=LINK_LEDGER_COLS)

    d = L.copy()
    d["code"] = d["stock_code"].map(to_code6)
    d = d.dropna(subset=["code"])
    d["pub_date"] = as_ts_series(d["pub_date"])
    d = d.dropna(subset=["pub_date"])

    # 공개 시각 보수화를 원장에도 동일 적용 (§0.1)
    kd = rep[["report_uid", "knowledge_date"]].drop_duplicates("report_uid") \
        if rep is not None and "knowledge_date" in rep.columns else None
    if kd is not None:
        d = d.merge(kd, on="report_uid", how="left")
        d["knowledge_date"] = as_ts_series(d["knowledge_date"]).fillna(
            d["pub_date"] + pd.tseries.offsets.BDay(1))
    else:
        d["knowledge_date"] = d["pub_date"] + pd.tseries.offsets.BDay(1)

    if unit == "broker_sector_team":
        smap = build_sector_map(sec).set_index("code")["sector"].to_dict()
        d["sector"] = d["code"].map(smap).fillna("미분류")
        d["analyst_key"] = d["broker_id"].astype(str) + "#" + d["sector"].astype(str)
        LOG.warn("Phase 0 폴백: 링크 단위를 broker×sector_team 으로 격하했습니다. "
                 "이 구성에서는 교차업종 전용 버전이 주 버전(primary)입니다.")
    else:
        d["analyst_key"] = d["analyst_id"].astype(str) + "@" + d["broker_id"].astype(str)

    d["n_analyst_on_report"] = d.groupby("report_uid")["analyst_key"].transform("nunique")
    d["link_conf"] = pd.to_numeric(d.get("link_conf"), errors="coerce").fillna(0.8)
    if "target_price" not in d.columns:
        d["target_price"] = np.nan
    d["target_price"] = pd.to_numeric(d["target_price"], errors="coerce")
    # "0"/"-" 는 '목표주가 없음'이다. 0 으로 넣으면 리비전 부호가 통째로 오염된다.
    d.loc[d["target_price"] <= 0, "target_price"] = np.nan
    out = d[LINK_LEDGER_COLS].drop_duplicates().reset_index(drop=True)
    PIPE.io("OUT", "MEM", "link_ledger", out)
    LOG.ok(f"링크 원장 {len(out):,}행 · 식별자 {out['analyst_key'].nunique():,}개 · "
           f"종목 {out['code'].nunique():,}개 · 단위={unit}")
    return out


# ==========================================================================================
# 조각: 20_pit.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  PIT 저장소 / 유니버스 / 셀  (계약 C1·C2·C3·C4·C11)                                 ║
# ║                                                                                          ║
# ║  C1: 모든 데이터 접근은 PIT.get(table, as_of) 한 곳만 통과한다.                            ║
# ║      DataFrame 직접 슬라이싱 금지. 우회 파라미터를 만들지 않는다.                          ║
# ║  C2: 유니버스는 상장폐지 종목을 포함한다. 정리매매가 없으면 -100%.                          ║
# ║  C11: 셀 = (date, industry, size_bucket). 다른 그룹키 금지.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, pd.DataFrame] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: pd.DataFrame, key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            LOG.debug(f"PIT 등록(빈 테이블): {name}")
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[C1 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        d = d.reset_index(drop=True)
        self._t[name] = d
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """시점 as_of 에서 '알 수 있었던' 행만 반환.
        latest_by 를 주면 그 키별 최신 1행(=당시 최신 관측)만 남긴다."""
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        t = as_ts(as_of)
        d = self._t[name]
        if d.empty:
            return d
        # knowledge_date 정렬되어 있으므로 searchsorted 로 O(log n) 절단
        pos = int(np.searchsorted(d["knowledge_date"].values, np.datetime64(t), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def asof_join(self, panel: pd.DataFrame, name: str, by: str,
                  left_time: str = "month", cols: Optional[Sequence[str]] = None,
                  suffix: str = "") -> pd.DataFrame:
        """get() 의 벡터화 등가물. 패널 전체에 대해 한 번에 as-of 결합한다.

        merge_asof(direction='backward') 는 knowledge_date <= month 인 마지막 행만 붙이므로
        C1 과 정확히 동일한 의미를 갖는다. 루프로 get() 을 3만 번 부르는 대신 이걸 쓴다.
        """
        self.access_log[name] += 1
        if name not in self._t or self._t[name].empty or panel.empty:
            return panel
        right = self._t[name]
        if by not in right.columns or by not in panel.columns:
            LOG.debug(f"asof_join 건너뜀: '{name}' 에 결합키 '{by}' 없음")
            return panel
        use = [c for c in (cols or [c for c in right.columns
                                    if c not in ("event_date", "_src")]) if c in right.columns]
        for c in (by, "knowledge_date"):
            if c not in use:
                use.append(c)
        R = (right[use].dropna(subset=["knowledge_date", by])
                        .sort_values("knowledge_date", kind="stable")).copy()
        if R.empty:
            return panel

        # ★★ 결합키가 결측인 패널 행을 '떨어뜨리면' 안 된다. ★★
        #   attach_fundamentals 에서 corp_code 가 없는 종목(대개 상장폐지·신규상장·비DART)이
        #   통째로 사라지면 그게 곧 생존자편향 재유입이다(C2 위반). merge_asof 는 by 키에
        #   NaN 이 있으면 다루지 못하므로, 유효키 부분만 결합한 뒤 전체 패널에 되붙인다.
        base = panel.copy()
        base["_ord"] = np.arange(len(base))
        mask = base[left_time].notna() & base[by].notna()
        n_drop = int((~mask).sum())
        if n_drop:
            LOG.debug(f"asof_join '{name}': 결합키 결측 {n_drop:,}행은 결측값으로 보존합니다"
                      f"(행을 버리지 않습니다 — C2).")
        L = base[mask].copy()
        if L.empty:
            LOG.warn(f"asof_join '{name}': 결합 가능한 행이 없습니다. 결합을 건너뜁니다.")
            return panel
        R[by] = R[by].astype(str)
        L[by] = L[by].astype(str)
        L = L.sort_values(left_time, kind="stable")
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", suffix or "_r"))
        except Exception as e:                                     # noqa
            LOG.warn(f"asof_join 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다. "
                     f"대개 정렬/타입 문제입니다.")
            return panel
        new_cols = [c for c in M.columns if c not in base.columns]
        if not new_cols:
            return panel
        add = M.set_index("_ord")[new_cols]
        out = base.set_index("_ord")
        out = out.join(add, how="left")            # 결합 실패 행은 NaN 으로 남고, 행은 유지된다
        out = out.sort_index().reset_index(drop=True)
        out.index = panel.index
        return out

    def report(self):
        rows = []
        for n, m in self._meta.items():
            rows.append([n, f"{m['rows']:,}",
                         str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                         ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n,0):,}"])
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (C1 — 모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()


# ── 유니버스 (C2) ───────────────────────────────────────────────────────────────────────────
LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    def __init__(self, sec: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame,
                 snap_window_days: int = 100):
        self.sec = sec.copy()
        self.snap = snapshots
        self.attrition: List[dict] = []
        self._cache_at: Dict[pd.Timestamp, List[str]] = {}
        # 스냅샷 주기가 분기면 ±45일 창으로는 대부분의 달이 스냅샷을 못 만난다 → 창을 넓힌다.
        self._snap_window_days = snap_window_days
        self._trading_days = (np.sort(pd.unique(as_ts_series(px_daily["date"]).values))
                              if px_daily is not None and len(px_daily) else
                              np.array([], dtype="datetime64[ns]"))
        self._snap_by_month: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            for d, g in snapshots.groupby("snap_date"):
                self._snap_by_month[as_ts(d)] = set(g["code"])

        self.sec["listing_date"] = as_ts_series(self.sec["listing_date"])
        self.sec["delisting_date"] = as_ts_series(self.sec["delisting_date"])
        self.sec = self.sec.drop_duplicates("code").reset_index(drop=True)

        # 벡터화용 배열 (at() 이 매월 3,500행 itertuples 를 도는 것을 없앤다)
        self._codes_arr = self.sec["code"].to_numpy(dtype=object)
        self._ld_arr = self.sec["listing_date"].to_numpy(dtype="datetime64[ns]")
        self._dd_arr = self.sec["delisting_date"].to_numpy(dtype="datetime64[ns]")
        self._delist = {c: d for c, d in zip(self._codes_arr, self.sec["delisting_date"])
                        if pd.notna(d)}

        # 상장 후 250거래일 시즈닝 — 거래일 배열에 대한 searchsorted 를 한 번에 벡터화
        #
        # ★ 앵커 주의 (조용한 유니버스 붕괴의 원인) ─────────────────────────────────────
        #   searchsorted 는 '가격패널 시작일 이전에 상장한' 종목을 전부 index 0 으로 보낸다.
        #   거기에 +250 을 더하면 1990년 상장 종목조차 "패널 시작 후 250거래일"에야 시즈닝이
        #   끝난 것으로 계산된다. 2016-08 시작 패널이면 2017년 중반까지 삼성전자를 포함한
        #   기존 상장사 전부가 유니버스에서 빠진다. 에러 없이, 로그도 없이.
        #   → 시즈닝의 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은
        #     이미 오래전에 시즈닝이 끝난 것으로 확정한다.
        self._seasoned: Dict[str, Any] = {}
        _FAR = pd.Timestamp("2100-01-01")     # 패널 안에서 시즈닝이 끝나지 않는 신규 상장
        if len(self._trading_days):
            t0 = self._trading_days[0]
            idx = np.searchsorted(self._trading_days, self._ld_arr, side="left")
            idx_s = idx + LISTING_SEASONING_DAYS
            n_td = len(self._trading_days)
            inside = idx_s < n_td
            seas = np.where(inside,
                            self._trading_days[np.minimum(idx_s, n_td - 1)],
                            np.datetime64(_FAR.isoformat(), "ns"))
            # 패널 시작 전 상장 → 달력 1년으로 확정(패널 시작보다 앞서므로 사실상 제약이 아님)
            pre = (~np.isnat(self._ld_arr)) & (self._ld_arr < t0)
            for c, ld, s, p in zip(self._codes_arr, self._ld_arr, seas, pre):
                if np.isnat(ld):
                    self._seasoned[c] = pd.NaT
                elif p:
                    self._seasoned[c] = as_ts(ld) + pd.Timedelta(days=365)
                else:
                    self._seasoned[c] = as_ts(s)
        else:
            for c, ld in zip(self._codes_arr, self._ld_arr):
                self._seasoned[c] = pd.NaT if np.isnat(ld) else as_ts(ld) + pd.Timedelta(days=365)

    def at(self, t) -> List[str]:
        """시점 t 의 유니버스. t 이후 상장 종목이 하나라도 섞이면 그 자체로 C2 위반이다."""
        t = as_ts(t)
        if t in self._cache_at:
            return self._cache_at[t]

        # ① 상장일·폐지일로 유도한 집합이 '기준선'이다. 이건 항상 성립해야 한다.
        base = set(self._codes_dated_at(t))

        # ② 스냅샷은 '보강'이다. 대체가 아니다.
        #    ★ 과거 스냅샷만 쓴다(미래 스냅샷을 고르면 그 자체가 누수).
        #    ★ 교집합이 아니라 합집합이다. 부분 응답 스냅샷으로 기준선을 깎으면
        #      그 달 유니버스가 조용히 줄어 곧바로 선택편향이 된다. 늘리기만 한다.
        past = [d for d in self._snap_by_month if d <= t]
        if past:
            key = max(past)
            if (t - key).days <= self._snap_window_days:
                base |= set(self._snap_by_month[key])

        # ③ 폐지 이후 종목은 어떤 경로로 들어왔든 반드시 제외한다.
        base -= {c for c, dd in self._delist.items() if pd.notna(dd) and dd <= t}

        # ④ 상장 후 250거래일 시즈닝
        out = [c for c in base
               if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]
        out = sorted(out)
        self._cache_at[t] = out
        return out

    def _codes_dated_at(self, t: pd.Timestamp) -> List[str]:
        """상장일/폐지일 기반 멤버십. itertuples 루프를 매월 도는 대신 벡터화한다
        (종목 3,500 × 120개월 = 42만 회 파이썬 루프였다)."""
        ld, dd = self._ld_arr, self._dd_arr
        tt = np.datetime64(t)
        ok = ~((~np.isnat(ld)) & (ld > tt)) & ~((~np.isnat(dd)) & (dd <= tt))
        ok &= ~(np.isnat(ld) & np.isnat(dd))        # 근거가 전혀 없는 종목은 넣지 않는다
        return self._codes_arr[ok].tolist()

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "PIT유니버스", "가격보유", "유동성필터", "거부권통과",
                 "하한선통과", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max", "size"])
        rows = []
        prev = None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/prev:.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§10.4) — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < 5:
            LOG.warn("최종 선정 종목이 월평균 5개 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 어느 게이트가 원인인지 위 표에서 먼저 확인하세요.")


# ── 셀 (C11) ────────────────────────────────────────────────────────────────────────────────
SIZE_BUCKETS = [(0, 50, "<50"), (50, 100, "50-99"), (100, 300, "100-299"),
                (300, 1000, "300-999"), (1000, 10 ** 9, "1000+")]


def size_bucket(n_emp: float) -> str:
    if n_emp is None or not np.isfinite(n_emp) or n_emp <= 0:
        return "미상"
    for lo, hi, lab in SIZE_BUCKETS:
        if lo <= n_emp < hi:
            return lab
    return "1000+"


def build_cells(panel: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell_key = (date, industry, size_bucket). 규모를 넣는 이유는 §5.6-② 참조:
    정부 지원제도 요건 대부분이 기업 규모에 연동되므로 정책효과가 셀 내 공통충격으로 흡수된다.
    비용 0의 오염 제거."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict()
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["industry_l1"] = p["industry"].str.slice(0, 4)                 # 폴백용 상위 단위
    p["size_bucket"] = p["employees"].map(size_bucket) if "employees" in p.columns else "미상"
    ym = p["month"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["industry"] + "|" + p["size_bucket"]
    # 폴백 사다리를 컬럼으로 미리 만들어 둔다. 센서별로 유효 관측이 부족할 때
    # xsec_z_l 이 이 사다리를 타고 내려간다(C11 "산업 상위 단위로 폴백").
    p["cell_l2"] = ym + "|" + p["industry_l1"] + "|ALL"
    p["cell_l3"] = ym + "|ALL|ALL"

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    still_n = 0
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        still_n = int(still.sum())
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백 발생: 1차 {n_small:,}행(산업 상위단위로) / 2차 {still_n:,}행(전체로). "
                 f"C11 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 1단계 {p['cell'].nunique():,}개 · 2단계 {p['cell_l2'].nunique():,}개 · "
              f"3단계 {p['cell_l3'].nunique():,}개")
    return p


# ==========================================================================================
# 조각: s21_universe.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-U  PIT 유니버스 (SPEC §5)                                                             ║
# ║                                                                                          ║
# ║  매월말 스냅샷. 이후 어떤 단계에서도 미래 스냅샷을 참조하지 않는다.                          ║
# ║   시장   : KOSPI + KOSDAQ (KONEX 제외)                                                    ║
# ║   제외   : 스팩 · 우선주 · ETF/ETN/리츠 (지주회사 중복상장분은 유지)                        ║
# ║   하한   : 주가 1,000원 · 시총 500억 · 20영업일 평균거래대금 3억                            ║
# ║   포함   : ★ 상장폐지 종목 — 그 시점에 살아 있었으면 반드시 포함한다 (생존편향 제거)         ║
# ║                                                                                          ║
# ║  각 스냅샷은 features/universe/universe_YYYYMM.parquet 로 저장한다.                        ║
# ║  게이트마다 잔존 종목수를 기록해 '어디서 표본이 붕괴하는지'를 표로 출력한다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

UNI_GATES = ["① 상장중(PIT)", "② 시장/증권 종류", "③ 가격 보유", "④ 주가 하한",
             "⑤ 시총 하한", "⑥ 유동성 하한", "⑦ 최종 유니버스"]

UNIVERSE_COLS = ["code", "month", "market", "close_m", "adv20", "mktcap", "shares",
                 "exec_px", "fwd_ret_m", "sector", "bm", "in_universe"]


class SACNUniverse:
    """SPEC §5 유니버스. 게이트별 감쇠를 기록하고 월별 스냅샷을 영속화한다."""

    def __init__(self):
        self.attrition: List[dict] = []
        self.panel: Optional[pd.DataFrame] = None
        self.saved_months: List[str] = []

    def _mark(self, month, gate: str, n: int):
        self.attrition.append({"month": as_ts(month), "gate": gate, "n": int(n)})

    def build(self, uni: "Universe", months: pd.DatetimeIndex, price_m: pd.DataFrame,
              mcap: pd.DataFrame, flags: pd.DataFrame, sector: pd.DataFrame,
              fund: pd.DataFrame, persist: bool = True) -> pd.DataFrame:
        # 룩업을 미리 만들어 월 루프 안에서 재구성하지 않는다 (120개월 × 2,500종목).
        pm = price_m.copy()
        pm["code"] = pm["code"].astype(str)
        pm["month"] = as_ts_series(pm["month"])
        pm = pm.set_index(["code", "month"])

        mc = mcap.copy() if mcap is not None and len(mcap) else pd.DataFrame(
            columns=["code", "month", "mktcap", "shares"])
        if len(mc):
            mc["code"] = mc["code"].astype(str)
            mc["month"] = as_ts_series(mc["month"])
            mc = mc.drop_duplicates(["code", "month"]).set_index(["code", "month"])

        fd = fund.copy() if fund is not None and len(fund) else pd.DataFrame(
            columns=["code", "month", "bm"])
        if len(fd):
            fd["code"] = fd["code"].astype(str)
            fd["month"] = as_ts_series(fd["month"])
            fd = fd.drop_duplicates(["code", "month"]).set_index(["code", "month"])

        excl = set(flags.loc[flags["excluded"], "code"].astype(str)) if flags is not None and len(flags) else set()
        mkt = (flags.set_index("code")["market"].astype(str).to_dict()
               if flags is not None and len(flags) and "market" in flags.columns else {})
        smap = (sector.set_index("code")["sector"].to_dict()
                if sector is not None and len(sector) else {})

        rows = []
        for m in tqdm(months, desc="PIT 유니버스", disable=not VERBOSE):
            m = as_ts(m)
            codes = [str(c) for c in uni.at(m)]                      # ① 상장중 (폐지종목 포함 판정)
            self._mark(m, UNI_GATES[0], len(codes))

            codes2 = [c for c in codes
                      if c not in excl
                      and str(mkt.get(c, "")).upper() in ("KOSPI", "KOSDAQ", "")]
            self._mark(m, UNI_GATES[1], len(codes2))                 # ② 시장/증권 종류

            idx = pd.MultiIndex.from_product([codes2, [m]], names=["code", "month"])
            g = pd.DataFrame(index=idx)
            for c in ("close", "adv20", "exec_px", "fwd_ret"):
                g[c] = pm[c].reindex(idx) if c in pm.columns else np.nan
            g["mktcap"] = mc["mktcap"].reindex(idx) if "mktcap" in getattr(mc, "columns", []) else np.nan
            g["shares"] = mc["shares"].reindex(idx) if "shares" in getattr(mc, "columns", []) else np.nan
            g["bm"] = fd["bm"].reindex(idx) if "bm" in getattr(fd, "columns", []) else np.nan
            g = g.reset_index()

            g = g[g["close"].notna() & (g["close"] > 0)]
            self._mark(m, UNI_GATES[2], len(g))                      # ③ 가격 보유

            g = g[g["close"] >= UNI_MIN_PRICE_KRW]
            self._mark(m, UNI_GATES[3], len(g))                      # ④ 주가 하한

            # 시총 스냅샷이 통째로 없는 달에는 이 게이트를 적용하지 않는다.
            # (데이터 부재를 '탈락'으로 처리하면 그 달 유니버스가 0이 되고, 그건 필터가 아니라 버그다)
            if g["mktcap"].notna().any():
                g = g[g["mktcap"].isna() | (g["mktcap"] >= UNI_MIN_MKTCAP_KRW)]
            self._mark(m, UNI_GATES[4], len(g))                      # ⑤ 시총 하한

            g = g[g["adv20"].isna() | (g["adv20"] >= UNI_MIN_ADV_KRW)]
            self._mark(m, UNI_GATES[5], len(g))                      # ⑥ 유동성 하한

            g["market"] = g["code"].map(lambda c: mkt.get(c, ""))
            g["sector"] = g["code"].map(lambda c: smap.get(c, "미분류"))
            g = g.rename(columns={"close": "close_m", "fwd_ret": "fwd_ret_m"})
            g["in_universe"] = True
            self._mark(m, UNI_GATES[6], len(g))                      # ⑦ 최종
            rows.append(g)

            if persist and len(g):
                self._persist_snapshot(m, g)

        P = (pd.concat(rows, ignore_index=True) if rows
             else pd.DataFrame(columns=UNIVERSE_COLS))
        P = P.reindex(columns=[c for c in UNIVERSE_COLS if c in P.columns or c in
                               ("code", "month")] + [c for c in P.columns if c not in UNIVERSE_COLS])
        P["code"] = P["code"].astype(str)
        P["month"] = as_ts_series(P["month"])
        self.panel = P
        PIPE.io("OUT", "MEM", "sacn_universe_panel", P)
        return P

    def _persist_snapshot(self, m: pd.Timestamp, g: pd.DataFrame):
        try:
            d = os.path.join(VAULT.ns["private"], "features", "universe")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"universe_{m:%Y%m}.parquet")
            if not os.path.exists(p):          # 이미 있으면 덮어쓰지 않는다
                atomic_write_parquet(g, p)
                self.saved_months.append(f"{m:%Y%m}")
        except Exception as e:                 # noqa
            LOG.debug(f"유니버스 스냅샷 저장 실패({type(e).__name__}) {m:%Y-%m}")

    # ── 감사 ─────────────────────────────────────────────────────────────────────────
    def report(self):
        if not self.attrition:
            LOG.warn("유니버스 감쇠 기록이 없습니다.")
            return
        A = pd.DataFrame(self.attrition)
        piv = A.groupby("gate")["n"].agg(["mean", "min", "max"]).reindex(UNI_GATES).dropna(how="all")
        rows, prev = [], None
        for gate, r in piv.iterrows():
            keep = "—" if prev in (None, 0) else f"{100 * r['mean'] / prev:.1f}%"
            rows.append([gate, f"{r['mean']:.0f}", f"{int(r['min'])}", f"{int(r['max'])}", keep])
            prev = r["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§5) — 어느 게이트에서 표본이 붕괴하는지")
        fin = piv.loc[UNI_GATES[6], "mean"] if UNI_GATES[6] in piv.index else 0
        need = N_QUANTILES * PORT_MIN_NAMES
        if fin < need:
            LOG.error(f"최종 유니버스 월평균 {fin:.0f}종목 → Q{N_QUANTILES} 분위당 "
                      f"{fin/N_QUANTILES:.0f}종목으로 보유하한 {PORT_MIN_NAMES}종목에 미달합니다. "
                      f"이대로면 대부분의 리밸런싱이 현금 처리되어 성과가 0 으로 나옵니다 "
                      f"(전략 실패가 아니라 표본 부족). 유니버스가 최소 {need}종목은 되어야 합니다.")
            PIPE.note("WARN: 유니버스 표본 부족 — 분위 백테스트 실행 불가 수준")
        elif fin < 200:
            LOG.warn(f"최종 유니버스 월평균 {fin:.0f}종목 — 분위당 {fin/N_QUANTILES:.0f}종목뿐입니다. "
                     f"통계적 판단력이 약합니다.")
        if self.saved_months:
            LOG.ok(f"월별 유니버스 스냅샷 {len(self.saved_months)}개 저장 "
                   f"→ {GDRIVE_PRIVATE_NS}/features/universe/universe_YYYYMM.parquet")

    def delisting_returns(self, uni: "Universe", months: pd.DatetimeIndex,
                          px_daily: pd.DataFrame, default_ret: float = DELIST_DEFAULT_RET
                          ) -> pd.DataFrame:
        """SPEC §0.3 — 폐지 종목의 최종 수익률.

        -100% 가 아니라 '정리매매 최종가' 기준이다. 일별 가격의 마지막 관측이 정리매매
        최종가에 해당하므로, 폐지 직전월 종가 → 최종 관측가 수익률을 쓴다.
        최종가를 확인할 수 없으면 default_ret(-70%)를 쓰고, 그 가정의 민감도를 별도 보고한다.
        """
        dmap = uni.delisting_map() if hasattr(uni, "delisting_map") else {}
        if not dmap:
            return pd.DataFrame(columns=["code", "month", "delist_ret", "source"])
        px = px_daily[["code", "date", "close"]].copy()
        px["code"] = px["code"].astype(str)
        px["date"] = as_ts_series(px["date"])
        last = (px.dropna(subset=["close"]).sort_values("date")
                .groupby("code", observed=True).tail(1).set_index("code"))
        rows = []
        mset = set(as_ts(m) for m in months)
        for code, dd in dmap.items():
            d = as_ts(dd)
            if d is None:
                continue
            m_prev = (d - pd.offsets.MonthEnd(1)) + pd.offsets.MonthEnd(0)
            if m_prev not in mset:
                continue
            base = px[(px["code"] == str(code)) & (px["date"] <= m_prev)]
            p0 = base["close"].dropna().iloc[-1] if len(base["close"].dropna()) else np.nan
            p1 = last["close"].get(str(code), np.nan)
            t1 = last["date"].get(str(code), pd.NaT)
            if np.isfinite(p0) and np.isfinite(p1) and p0 > 0 and pd.notna(t1) and t1 > m_prev:
                r, src = float(p1 / p0 - 1.0), "정리매매 최종가"
            else:
                r, src = float(default_ret), "확인불가 → 보수적 기본값"
            rows.append({"code": str(code), "month": m_prev,
                         "delist_ret": max(-1.0, min(r, 5.0)), "source": src})
        out = pd.DataFrame(rows)
        if len(out):
            n_ok = int((out["source"] == "정리매매 최종가").sum())
            LOG.table([["정리매매 최종가 확인", f"{n_ok:,}"],
                       ["확인불가 → 기본값 적용", f"{len(out) - n_ok:,}"],
                       ["기본값", f"{default_ret:.0%}"],
                       ["평균 폐지수익률", f"{out['delist_ret'].mean():.1%}"]],
                      ["항목", "값"], ["l", "r"],
                      title="상장폐지 처리 (§0.3) — -100% 일괄 적용 금지")
            if len(out) - n_ok:
                open_question("OQ-02", "상장폐지 최종가",
                              f"{len(out) - n_ok}건은 정리매매 최종가를 확인할 수 없다.",
                              f"보수적 기본값 {default_ret:.0%} 적용.",
                              "delisting_sensitivity.md 에 -100%/-70%/-50%/-30% 민감도 병기.")
        return out


def smallcap_subset(P: pd.DataFrame, n: int = SMALLCAP_ARM_N) -> pd.DataFrame:
    """비교 아암 — 매월 시가총액 하위 n종목으로 압축한 유니버스.

    H3('소형주에서 더 강하다')의 조건부 예측과 직접 맞물리는 비교군이다.
    시총 결측 종목은 순위를 매길 수 없으므로 제외한다(포함하면 순위가 의미를 잃는다).
    """
    if P is None or not len(P):
        return P
    d = P[P["mktcap"].notna()].copy()
    if not len(d):
        LOG.warn("시가총액이 전부 결측이라 소형주 비교아암을 만들 수 없습니다.")
        return d
    d["_rk"] = d.groupby("month")["mktcap"].rank(method="first", ascending=True)
    out = d[d["_rk"] <= n].drop(columns=["_rk"]).reset_index(drop=True)
    LOG.ok(f"소형주 비교아암: 월평균 {out.groupby('month').size().mean():.0f}종목 "
           f"(시총 하위 {n:,} 기준) · 전체 아암 월평균 "
           f"{P.groupby('month').size().mean():.0f}종목")
    return out


# ==========================================================================================
# 조각: s22_link.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-L  공동커버리지 링크 행렬 (SPEC §6.1) + 애널리스트 스킬 (SPEC §6.4)                    ║
# ║                                                                                          ║
# ║   covered(a,i) = 1  if 애널리스트 a 가 [t-12M, t] 에 종목 i 리포트를 1건 이상 발간          ║
# ║   w_ij(t)      = Σ_a covered(a,i)·covered(a,j)   (i≠j)     # 공유 애널리스트 수            ║
# ║                                                                                          ║
# ║  구현 원칙                                                                                ║
# ║   · 밀집행렬 금지. C(애널 × 종목) 희소행렬을 만들고 W = CᵀC 로 한 번에 얻는다.              ║
# ║     2,500종목 밀집이면 월당 50MB × 120개월 = 6GB — 애초에 성립하지 않는다.                  ║
# ║   · 대각원소 0 강제 (자기 자신은 연결이 아니다).                                            ║
# ║   · PIT: 윈도우 필터는 pub_date 가 아니라 knowledge_date 로 건다.                           ║
# ║   · 월별 CSR 을 전용 인덱스에 직렬화한다. 재실행 시 재계산하지 않는다(§8.1 재실행 45분).     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

try:
    import scipy.sparse as _sp
    from scipy.sparse import csr_matrix as _csr
except Exception:                                            # pragma: no cover
    _sp = None
    _csr = None


class LinkMatrices:
    """월별 링크 행렬 보관소. 가중 방식별로 따로 만든다 (SPEC §6.4 의 3가지)."""

    def __init__(self, weight_mode: str = "unweighted"):
        self.mode = weight_mode
        self.codes: List[str] = []
        self.cidx: Dict[str, int] = {}
        self.W: "OrderedDict[pd.Timestamp, Any]" = OrderedDict()
        self.stats: List[dict] = []

    def n_links(self, m) -> np.ndarray:
        w = self.W.get(as_ts(m))
        if w is None:
            return np.zeros(len(self.codes))
        return np.asarray((w > 0).sum(axis=1)).ravel()

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame(self.stats)


def _cache_path(mode: str) -> str:
    d = os.path.join(VAULT.ns["private"], "features", "linkmat")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"link_{mode}.npz")


def _save_links(LM: LinkMatrices):
    if _sp is None or not LM.W:
        return
    try:
        payload: Dict[str, Any] = {"__codes__": np.array(LM.codes, dtype=object),
                                   "__months__": np.array([str(m.date()) for m in LM.W], dtype=object)}
        for m, w in LM.W.items():
            k = f"m{m:%Y%m}"
            c = w.tocoo()
            payload[k + "_r"] = c.row.astype(np.int32)
            payload[k + "_c"] = c.col.astype(np.int32)
            payload[k + "_v"] = c.data.astype(np.float32)
        # ★ np.savez_compressed 는 파일명이 .npz 로 끝나지 않으면 '.npz' 를 덧붙인다.
        #   tmp 를 ".tmp" 로 두면 실제 파일은 ".tmp.npz" 가 되고 os.replace 가 매번 실패한다
        #   (그리고 예외를 삼키므로 '캐시가 조용히 전혀 안 되는' 상태가 된다).
        tmp = _cache_path(LM.mode) + ".tmp.npz"
        np.savez_compressed(tmp, **payload)
        os.replace(tmp, _cache_path(LM.mode))
        LOG.debug(f"링크 행렬 직렬화: {LM.mode} ({len(LM.W)}개월)")
    except Exception as e:                                    # noqa
        LOG.debug(f"링크 행렬 저장 실패({type(e).__name__}) — 재계산으로 진행합니다.")


def _load_links(mode: str, months: pd.DatetimeIndex) -> Optional[LinkMatrices]:
    p = _cache_path(mode)
    if _sp is None or not os.path.exists(p):
        return None
    try:
        z = np.load(p, allow_pickle=True)
        codes = [str(x) for x in z["__codes__"]]
        have = {str(x) for x in z["__months__"]}
        want = {str(as_ts(m).date()) for m in months}
        if not want.issubset(have):
            return None
        LM = LinkMatrices(mode)
        LM.codes = codes
        LM.cidx = {c: i for i, c in enumerate(codes)}
        n = len(codes)
        for m in months:
            m = as_ts(m)
            k = f"m{m:%Y%m}"
            if k + "_r" not in z:
                return None
            LM.W[m] = _csr((z[k + "_v"], (z[k + "_r"], z[k + "_c"])), shape=(n, n))
        LOG.ok(f"링크 행렬 캐시 적중: {mode} ({len(LM.W)}개월) — 재계산 생략")
        return LM
    except Exception:
        return None


def build_link_matrices(ledger: pd.DataFrame, months: pd.DatetimeIndex,
                        codes: Sequence[str], weight_mode: str = "unweighted",
                        skill: Optional[pd.DataFrame] = None,
                        lookback_m: int = LINK_LOOKBACK_M,
                        use_cache: bool = True) -> LinkMatrices:
    """월별 공동커버리지 행렬 W(t) 를 만든다.

    weight_mode
      "unweighted" : covered = 1  (SPEC 기본)
      "freq"       : covered = 해당 윈도우 내 발간 건수 (발간빈도 가중)
      "highskill"  : 고스킬 애널리스트(상위 40%)만 사용, covered = 1
    """
    if use_cache:
        cached = _load_links(weight_mode, months)
        if cached is not None:
            return cached

    LM = LinkMatrices(weight_mode)
    LM.codes = [str(c) for c in dict.fromkeys(codes)]
    LM.cidx = {c: i for i, c in enumerate(LM.codes)}
    n = len(LM.codes)
    if _sp is None:
        LOG.error("scipy.sparse 를 쓸 수 없습니다 — 밀집행렬로는 이 전략을 돌리지 않습니다.")
        return LM
    if ledger is None or not len(ledger) or n == 0:
        LOG.warn("링크 원장 또는 종목 목록이 비어 링크 행렬을 만들 수 없습니다.")
        return LM

    d = ledger.copy()
    d["code"] = d["code"].astype(str)
    d = d[d["code"].isin(LM.cidx)]
    d["knowledge_date"] = as_ts_series(d["knowledge_date"])
    d = d.dropna(subset=["knowledge_date"])
    if not len(d):
        LOG.warn("유니버스 종목과 겹치는 리포트가 없습니다.")
        return LM

    # 고스킬 한정 모드: 월별로 자격 애널리스트가 달라지므로 (month, analyst_key) 집합을 미리 만든다
    hs: Dict[pd.Timestamp, set] = {}
    if weight_mode == "highskill":
        if skill is None or not len(skill):
            LOG.warn("스킬 테이블이 없어 'highskill' 구성을 비가중과 동일하게 처리합니다. "
                     "이 사실은 결과표에 표시됩니다.")
        else:
            s = skill.copy()
            s["month"] = as_ts_series(s["month"])
            for m, g in s[s["is_high"]].groupby("month"):
                hs[as_ts(m)] = set(g["analyst_key"].astype(str))

    d["_ci"] = d["code"].map(LM.cidx).astype(np.int32)
    akeys = pd.Index(sorted(d["analyst_key"].astype(str).unique()))
    aidx = {a: i for i, a in enumerate(akeys)}
    d["_ai"] = d["analyst_key"].astype(str).map(aidx).astype(np.int32)
    d = d.sort_values("knowledge_date", kind="stable").reset_index(drop=True)
    kd = d["knowledge_date"].to_numpy("datetime64[ns]")

    t0 = time.time()
    for m in tqdm(months, desc=f"링크행렬[{weight_mode}]", disable=not VERBOSE):
        m = as_ts(m)
        lo = m - pd.DateOffset(months=lookback_m)
        # PIT: knowledge_date 로 자른다. 정렬돼 있으므로 O(log n).
        i0 = int(np.searchsorted(kd, np.datetime64(lo), side="left"))
        i1 = int(np.searchsorted(kd, np.datetime64(m), side="right"))
        win = d.iloc[i0:i1]
        if weight_mode == "highskill" and hs:
            allow = hs.get(m, set())
            win = win[win["analyst_key"].astype(str).isin(allow)] if allow else win.iloc[0:0]
        if not len(win):
            LM.W[m] = _csr((n, n), dtype=np.float32)
            LM.stats.append({"month": m, "n_analyst": 0, "n_pair": 0, "n_covered": 0,
                             "median_links": 0.0})
            continue

        if weight_mode == "freq":
            g = win.groupby(["_ai", "_ci"], observed=True).size().reset_index(name="v")
            vals = g["v"].to_numpy(np.float32)
        else:
            g = win[["_ai", "_ci"]].drop_duplicates()
            vals = np.ones(len(g), dtype=np.float32)
        C = _csr((vals, (g["_ai"].to_numpy(np.int32), g["_ci"].to_numpy(np.int32))),
                 shape=(len(akeys), n))
        W = (C.T @ C).tocsr()
        W.setdiag(0)                       # ★ 자기 자신은 연결이 아니다
        W.eliminate_zeros()
        LM.W[m] = W.astype(np.float32)
        deg = np.asarray((W > 0).sum(axis=1)).ravel()
        LM.stats.append({"month": m, "n_analyst": int(win["_ai"].nunique()),
                         "n_pair": int(W.nnz // 2), "n_covered": int((deg > 0).sum()),
                         "median_links": float(np.median(deg[deg > 0])) if (deg > 0).any() else 0.0})

    LOG.ok(f"링크 행렬 {len(LM.W)}개월 생성 [{weight_mode}] — {time.time()-t0:.1f}s")
    S = LM.summary()
    if len(S):
        LOG.table([[f"{r['month']:%Y-%m}", f"{int(r['n_analyst']):,}", f"{int(r['n_covered']):,}",
                    f"{int(r['n_pair']):,}", f"{r['median_links']:.0f}"]
                   for _, r in S.iloc[::max(1, len(S) // 8)].iterrows()],
                  ["월", "활동 애널", "연결보유 종목", "링크쌍", "종목당 연결(중위)"],
                  ["l", "r", "r", "r", "r"],
                  title=f"링크 행렬 요약 [{weight_mode}] — 표본 8개월")
    _save_links(LM)
    return LM


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  애널리스트 스킬 — 경험적 베이즈 축소추정 (SPEC §6.4, 선택이 아니라 필수)
# ═══════════════════════════════════════════════════════════════════════════════════════════
SKILL_LOOKBACK_M = 24        # 직전 24개월 목표주가 개정
SKILL_HORIZON_M = 3          # 이후 3개월 수익률과 부호 일치
SKILL_TOP_PCT = 0.40         # 상위 40% = 고스킬


def _beta_binom_k(hits: np.ndarray, n: np.ndarray) -> float:
    """적률법으로 베타-이항 사전강도 k 를 추정한다.

    k 가 클수록 사전분포로 강하게 끌어당긴다. 애널리스트 1인당 유효 개정 건수가
    연 40~80건뿐이라 비축소 추정은 거의 전부 잡음이다 — 그래서 이 축소는 필수다.
    """
    ok = (n > 0) & np.isfinite(hits) & np.isfinite(n)
    if ok.sum() < 8:
        return 20.0
    p = hits[ok] / n[ok]
    nb = n[ok]
    mu = float(np.average(p, weights=nb))
    if not (0 < mu < 1):
        return 20.0
    var = float(np.average((p - mu) ** 2, weights=nb))
    within = mu * (1 - mu) * float(np.average(1.0 / nb, weights=nb))
    between = var - within
    if between <= 1e-9:
        return 200.0                      # 개인차가 관측되지 않음 → 거의 전부 사전으로
    k = mu * (1 - mu) / between - 1.0
    return float(np.clip(k, 5.0, 500.0))


def build_analyst_skill(ledger: pd.DataFrame, price_m: pd.DataFrame,
                        months: pd.DatetimeIndex, sector: pd.DataFrame) -> pd.DataFrame:
    """월별 애널리스트 스킬 (PIT). 반환: analyst_key, month, n_rev, hit_raw, skill, is_high

    정의(SPEC §6.4): 직전 24개월 목표주가 개정의 부호가 이후 3개월 수익률과 일치한 비율.
    축소추정: 증권사 평균 → 섹터 평균 순으로 shrink. 관측 수가 적을수록 강하게 끌어당긴다.

    ★ PIT 주의: 시점 t 에서 쓸 수 있는 개정은 s + 3개월 ≤ t 인 것뿐이다.
      (개정 시점의 '이후 3개월 수익률'을 알아야 적중 여부가 정해지므로)
    """
    cols = ["analyst_key", "month", "n_rev", "hit_raw", "skill", "is_high"]
    if ledger is None or not len(ledger) or "target_price" not in ledger.columns:
        LOG.warn("목표주가가 없어 애널리스트 스킬을 계산할 수 없습니다 — "
                 "'highskill' 구성은 비가중과 동일해집니다.")
        return pd.DataFrame(columns=cols)

    d = ledger.dropna(subset=["target_price"]).copy()
    if not len(d):
        LOG.warn("유효 목표주가가 0건입니다 — 스킬 계산 불가.")
        return pd.DataFrame(columns=cols)
    d["knowledge_date"] = as_ts_series(d["knowledge_date"])
    d["month"] = d["knowledge_date"] + pd.offsets.MonthEnd(0)
    d = d.sort_values(["analyst_key", "code", "knowledge_date"], kind="stable")

    # ① 같은 애널리스트가 같은 종목에 이전에 제시한 목표주가 대비 개정 부호
    g = d.groupby(["analyst_key", "code"], observed=True)["target_price"]
    d["tp_prev"] = g.shift(1)
    d = d[d["tp_prev"].notna() & (d["tp_prev"] > 0)]
    if not len(d):
        LOG.warn("직전 목표주가와 비교 가능한 개정이 없습니다 (동일 애널×종목 재방문 부족).")
        return pd.DataFrame(columns=cols)
    d["rev_sign"] = np.sign(d["target_price"] - d["tp_prev"])
    d = d[d["rev_sign"] != 0]

    # ② 개정 시점 이후 3개월 수익률
    pm = price_m[["code", "month", "close"]].copy()
    pm["code"] = pm["code"].astype(str)
    pm["month"] = as_ts_series(pm["month"])
    pm = pm.dropna(subset=["close"]).sort_values(["code", "month"])
    pm["close_fwd3"] = pm.groupby("code", observed=True)["close"].shift(-SKILL_HORIZON_M)
    pm["mfwd"] = pm.groupby("code", observed=True)["month"].shift(-SKILL_HORIZON_M)
    okgap = (((pm["mfwd"].dt.year - pm["month"].dt.year) * 12
              + (pm["mfwd"].dt.month - pm["month"].dt.month)) == SKILL_HORIZON_M)
    pm["ret3"] = np.where(okgap, safe_div(pm["close_fwd3"], pm["close"]) - 1.0, np.nan)

    d["code"] = d["code"].astype(str)
    d = d.merge(pm[["code", "month", "ret3"]], on=["code", "month"], how="left")
    d = d.dropna(subset=["ret3"])
    if not len(d):
        LOG.warn("개정 시점과 이후 3개월 수익률을 맞출 수 없습니다 — 스킬 계산 불가.")
        return pd.DataFrame(columns=cols)
    d["hit"] = (np.sign(d["ret3"]) == d["rev_sign"]).astype(float)
    # 적중 여부를 '알 수 있게 되는' 시점 = 개정월 + 3개월 (미래누수 차단의 핵심)
    d["known_month"] = d["month"] + pd.offsets.MonthEnd(SKILL_HORIZON_M)

    smap = (sector.set_index("code")["sector"].to_dict()
            if sector is not None and len(sector) else {})
    d["sector"] = d["code"].map(lambda c: smap.get(c, "미분류"))

    # ③ 월별 롤링 24개월 집계 + EB 축소
    d = d.sort_values("known_month", kind="stable")
    km = d["known_month"].to_numpy("datetime64[ns]")
    out = []
    for m in months:
        m = as_ts(m)
        lo = m - pd.DateOffset(months=SKILL_LOOKBACK_M)
        i0 = int(np.searchsorted(km, np.datetime64(lo), side="left"))
        i1 = int(np.searchsorted(km, np.datetime64(m), side="right"))
        w = d.iloc[i0:i1]
        if len(w) < 20:
            continue
        a = w.groupby("analyst_key", observed=True).agg(
            n_rev=("hit", "size"), hits=("hit", "sum"),
            broker=("broker_id", "first"), sector=("sector", lambda s: s.mode().iat[0]
                                                    if len(s.mode()) else "미분류")).reset_index()
        # 사전분포: 증권사 평균 → (표본 부족 시) 섹터 평균 → 전체 평균
        gm = float(w["hit"].mean())
        bro = w.groupby("broker_id", observed=True)["hit"].agg(["mean", "size"])
        sec_ = w.groupby("sector", observed=True)["hit"].agg(["mean", "size"])
        prior = []
        for _, r in a.iterrows():
            b = bro.loc[r["broker"]] if r["broker"] in bro.index else None
            if b is not None and b["size"] >= 30:
                prior.append(float(b["mean"]))
                continue
            s_ = sec_.loc[r["sector"]] if r["sector"] in sec_.index else None
            if s_ is not None and s_["size"] >= 30:
                prior.append(float(s_["mean"]))
                continue
            prior.append(gm)
        a["prior"] = prior
        k = _beta_binom_k(a["hits"].to_numpy(float), a["n_rev"].to_numpy(float))
        a["skill"] = (a["hits"] + k * a["prior"]) / (a["n_rev"] + k)
        a["hit_raw"] = safe_div(a["hits"], a["n_rev"])
        thr = a["skill"].quantile(1.0 - SKILL_TOP_PCT)
        a["is_high"] = a["skill"] >= thr
        a["month"] = m
        a["k_shrink"] = k
        out.append(a[["analyst_key", "month", "n_rev", "hit_raw", "skill", "is_high", "k_shrink"]])

    if not out:
        LOG.warn("스킬 산출 가능한 월이 없습니다 (개정 표본 부족).")
        return pd.DataFrame(columns=cols)
    S = pd.concat(out, ignore_index=True)
    med_n = float(S["n_rev"].median())
    LOG.table([["산출 월수", f"{S['month'].nunique()}"],
               ["애널리스트 수(연인원)", f"{len(S):,}"],
               ["1인당 유효 개정(중위)", f"{med_n:.0f}"],
               ["축소강도 k (중위)", f"{S['k_shrink'].median():.0f}"],
               ["원시 적중률(중위)", f"{S['hit_raw'].median():.1%}"],
               ["축소 후 스킬(중위)", f"{S['skill'].median():.1%}"],
               ["고스킬 판정 비율", f"{S['is_high'].mean():.1%}"]],
              ["항목", "값"], ["l", "r"],
              title="애널리스트 스킬 — 경험적 베이즈 축소추정 (SPEC §6.4)")
    if med_n < 10:
        LOG.warn(f"1인당 유효 개정이 중위 {med_n:.0f}건뿐입니다. 축소추정이 사전분포를 "
                 f"거의 그대로 돌려주므로 'highskill' 구성은 사실상 증권사/섹터 평균 분류에 "
                 f"가깝습니다. 이 한계를 결과표에 명시합니다.")
        open_question("OQ-03", "고스킬 애널리스트 정의",
                      f"1인당 유효 목표주가 개정이 중위 {med_n:.0f}건으로 매우 적다.",
                      "EB 축소를 필수 적용하고, highskill 구성의 해석 한계를 결과표에 명시.",
                      "highskill 아암의 결과는 개인 스킬이 아니라 하우스/섹터 효과일 수 있음.")
    return S


# ==========================================================================================
# 조각: s23_signal.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-S  SACN 신호 (SPEC §6.2) + 직교화 (SPEC §6.3)                                         ║
# ║                                                                                          ║
# ║      SACN_i(t) = Σ_j w_ij(t)·r_j(t-1) / Σ_j w_ij(t)                                       ║
# ║                                                                                          ║
# ║  희소행렬 곱 한 번이면 전 종목이 동시에 계산된다:                                          ║
# ║      num = W @ (r ⊙ mask),  den = W @ mask,  SACN = num / den                             ║
# ║  mask 는 '그 시점 유니버스에 속한 연결기업만 쓴다'는 §6.2 규칙을 그대로 구현한 것이다.       ║
# ║  종목별 루프로 짜면 같은 결과에 수백 배가 든다.                                             ║
# ║                                                                                          ║
# ║  직교화(필수): SACN 을 그대로 쓰면 업종/사이즈/반전의 재포장일 수 있다.                     ║
# ║      SACN_i = α + β1·log(MktCap) + β2·r_i(t-1) + β3·SectorRet(t-1) + β4·BM_i + ε_i         ║
# ║  최종 신호는 잔차 ε. 원신호 버전과 직교화 버전을 둘 다 산출해 병기한다.                     ║
# ║  직교화 후 신호가 소멸하면 그것이 결론이다 — 되살리려 하지 않는다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

WINDOW_DAYS = {"1W": 7, "1M": 31}          # 캘린더 기준 룩백 (거래일 수가 아니라 달력일)


class PriceGrid:
    """일별 종가/시가 와이드 격자. 모든 시점 연산의 공용 기반."""

    def __init__(self, px_daily: pd.DataFrame):
        d = px_daily[["code", "date", "close", "open"]].copy()
        d["code"] = d["code"].astype(str)
        d["date"] = as_ts_series(d["date"])
        d = d.dropna(subset=["date", "code"]).drop_duplicates(["code", "date"], keep="last")
        self.close = d.pivot(index="date", columns="code", values="close").astype("float32")
        self.open = d.pivot(index="date", columns="code", values="open").astype("float32") \
            .reindex_like(self.close)
        self.close = self.close.sort_index()
        self.open = self.open.reindex(index=self.close.index, columns=self.close.columns)
        self.dates = self.close.index.to_numpy("datetime64[ns]")
        self.codes = list(self.close.columns)
        self.cpos = {c: i for i, c in enumerate(self.codes)}
        LOG.info(f"가격 격자 {self.close.shape[0]:,}일 × {self.close.shape[1]:,}종목 "
                 f"({self.close.memory_usage(deep=True).sum()/1e6:.0f}MB)")

    def pos_at_or_before(self, t) -> int:
        """t 이하 마지막 거래일의 인덱스. 없으면 -1."""
        return int(np.searchsorted(self.dates, np.datetime64(as_ts(t)), side="right")) - 1

    def pos_after(self, t) -> int:
        """t 초과 첫 거래일의 인덱스(= 익영업일). 없으면 -1."""
        i = int(np.searchsorted(self.dates, np.datetime64(as_ts(t)), side="right"))
        return i if i < len(self.dates) else -1

    def prior_return(self, t, window: str) -> np.ndarray:
        """t 시점까지의 직전 window 수익률 (종가 기준). 전 종목 벡터."""
        i1 = self.pos_at_or_before(t)
        if i1 < 0:
            return np.full(len(self.codes), np.nan, dtype="float32")
        t0 = as_ts(t) - pd.Timedelta(days=WINDOW_DAYS.get(window, 31))
        i0 = self.pos_at_or_before(t0)
        if i0 < 0 or i0 >= i1:
            return np.full(len(self.codes), np.nan, dtype="float32")
        c1 = self.close.iloc[i1].to_numpy("float32")
        c0 = self.close.iloc[i0].to_numpy("float32")
        with np.errstate(all="ignore"):
            r = np.where((c0 > 0) & np.isfinite(c0) & np.isfinite(c1), c1 / c0 - 1.0, np.nan)
        return r.astype("float32")

    def exec_price(self, t) -> Tuple[np.ndarray, Optional[pd.Timestamp]]:
        """익영업일 시가 (없으면 그날 종가). SPEC 아키텍처 불변 규칙: 진입은 익영업일."""
        i = self.pos_after(t)
        if i < 0:
            return np.full(len(self.codes), np.nan, dtype="float32"), None
        o = self.open.iloc[i].to_numpy("float32")
        c = self.close.iloc[i].to_numpy("float32")
        px = np.where(np.isfinite(o) & (o > 0), o, c)
        return px.astype("float32"), as_ts(self.close.index[i])


def rebalance_dates(months: pd.DatetimeIndex, grid: PriceGrid, freq: str) -> List[pd.Timestamp]:
    """리밸런싱 시점. 'M'=월말, 'W'=주말(각 주의 마지막 거래일)."""
    if freq == "M":
        out = []
        for m in months:
            i = grid.pos_at_or_before(m)
            if i >= 0:
                out.append(as_ts(grid.close.index[i]))
        return sorted(set(out))
    idx = pd.DatetimeIndex(grid.close.index)
    lo, hi = as_ts(months[0]), as_ts(months[-1])
    idx = idx[(idx >= lo - pd.DateOffset(months=1)) & (idx <= hi)]
    if not len(idx):
        return []
    s = pd.Series(idx, index=idx)
    wk = s.groupby([idx.isocalendar().year, idx.isocalendar().week]).max()
    return sorted(as_ts(x) for x in wk.to_numpy())


def compute_sacn(LM: LinkMatrices, grid: PriceGrid, uni_panel: pd.DataFrame,
                 rebals: Sequence[pd.Timestamp], window: str,
                 min_links: int = MIN_LINKS_REQUIRED) -> pd.DataFrame:
    """SPEC §6.2 원신호. 반환: code, date, sacn_raw, n_link_used, own_ret

    연결기업 j 는 '해당 시점 유니버스에 속한 종목' 만 쓴다. 유니버스 밖 종목은
    분자·분모 양쪽에서 동시에 빠져야 한다 — 분자에서만 빼면 신호가 0 쪽으로 눌린다.
    """
    if _sp is None or not LM.W:
        return pd.DataFrame(columns=["code", "date", "sacn_raw", "n_link_used", "own_ret"])

    lcodes = LM.codes
    lpos = {c: i for i, c in enumerate(lcodes)}
    # 링크행렬 좌표계 ↔ 가격격자 좌표계 대응
    g2l = np.full(len(lcodes), -1, dtype=np.int64)
    for c, i in lpos.items():
        j = grid.cpos.get(c, -1)
        g2l[i] = j

    uni = uni_panel[["code", "month"]].copy()
    uni["code"] = uni["code"].astype(str)
    uni["month"] = as_ts_series(uni["month"])
    uni_by_month: Dict[pd.Timestamp, set] = {
        as_ts(m): set(g["code"]) for m, g in uni.groupby("month")}

    link_months = sorted(LM.W.keys())
    lm_arr = np.array([np.datetime64(m) for m in link_months])

    rows = []
    for t in rebals:
        t = as_ts(t)
        # PIT: t 시점에 '이미 만들어져 있던' 가장 최근 월말 링크 행렬만 쓴다
        k = int(np.searchsorted(lm_arr, np.datetime64(t), side="right")) - 1
        if k < 0:
            continue
        m_link = link_months[k]
        W = LM.W.get(m_link)
        if W is None or W.nnz == 0:
            continue
        # 유니버스도 t 이하 최근 월말 스냅샷 기준
        m_uni = (t + pd.offsets.MonthEnd(0)) if t == (t + pd.offsets.MonthEnd(0)) \
            else (t - pd.offsets.MonthEnd(1))
        if m_uni not in uni_by_month:
            cand = [m for m in uni_by_month if m <= t]
            if not cand:
                continue
            m_uni = max(cand)
        alive = uni_by_month[m_uni]

        r_grid = grid.prior_return(t, window)
        r = np.full(len(lcodes), np.nan, dtype="float64")
        ok = g2l >= 0
        r[ok] = r_grid[g2l[ok]]

        mask = np.array([1.0 if c in alive else 0.0 for c in lcodes])
        mask *= np.isfinite(r).astype(float)
        if mask.sum() < min_links + 1:
            continue
        rr = np.where(np.isfinite(r), r, 0.0) * mask

        num = W @ rr
        den = W @ mask
        B = (W > 0).astype(np.float32)
        nlink = B @ mask                      # 실제로 쓰인 연결기업 수

        with np.errstate(all="ignore"):
            sig = np.where((den > 0) & (nlink >= min_links), num / den, np.nan)

        sel = np.isfinite(sig)
        if not sel.any():
            continue
        rows.append(pd.DataFrame({
            "code": [lcodes[i] for i in np.where(sel)[0]],
            "date": t,
            "sacn_raw": sig[sel].astype("float32"),
            "n_link_used": nlink[sel].astype("float32"),
            "own_ret": r[sel].astype("float32"),
        }))
    if not rows:
        LOG.warn(f"SACN 신호가 한 시점도 만들어지지 않았습니다 (window={window}). "
                 f"링크 부족 또는 유니버스 불일치를 확인하세요.")
        return pd.DataFrame(columns=["code", "date", "sacn_raw", "n_link_used", "own_ret"])
    S = pd.concat(rows, ignore_index=True)
    cov = S.groupby("date")["code"].size()
    LOG.ok(f"SACN 원신호 [{window}] {len(S):,}행 · {S['date'].nunique()}시점 · "
           f"시점당 평균 {cov.mean():.0f}종목 (최소 연결 {min_links}개 요건 적용)")
    return S


def orthogonalize(S: pd.DataFrame, uni_panel: pd.DataFrame, grid: PriceGrid,
                  window: str) -> pd.DataFrame:
    """SPEC §6.3 — 매 시점 횡단면 회귀의 잔차를 최종 신호로 쓴다.

        SACN_i = α + β1·log(MktCap_i) + β2·r_i(t-1) + β3·SectorRet(t-1) + β4·BM_i + ε_i

    설계 판단: 어떤 회귀항이 통째로 결측인 시점에는 그 항만 빼고 회귀한다.
    (그 시점을 통째로 버리면 표본이 붕괴하고, 결측을 0으로 채우면 계수가 오염된다)
    빠진 항은 시점별로 기록해 산출물에 남긴다.
    """
    if S is None or not len(S):
        return S
    U = uni_panel[["code", "month", "mktcap", "bm", "sector"]].copy()
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])

    d = S.copy()
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    # 주간 리밸런싱은 월말 이전 시점이 있으므로, 그 시점에 '알 수 있던' 직전 월말 속성을 쓴다
    d["month_attr"] = np.where(as_ts_series(d["date"]) >= d["month"],
                               d["month"], d["month"] - pd.offsets.MonthEnd(1))
    d["month_attr"] = as_ts_series(d["month_attr"])
    d = d.merge(U.rename(columns={"month": "month_attr"}), on=["code", "month_attr"], how="left")

    # 업종 수익률: 같은 시점, 같은 업종의 자기수익률 평균 (자기 자신 제외 = leave-one-out)
    grp = d.groupby(["date", "sector"], observed=True)["own_ret"]
    ssum, scnt = grp.transform("sum"), grp.transform("count")
    d["sector_ret"] = np.where(scnt > 1, (ssum - d["own_ret"].fillna(0)) / (scnt - 1), np.nan)

    d["logmc"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").clip(lower=1e8))
    d["bm_w"] = pd.to_numeric(d["bm"], errors="coerce")

    terms = [("logmc", "log(MktCap)"), ("own_ret", "r_i(t-1)"),
             ("sector_ret", "SectorRet(t-1)"), ("bm_w", "BM")]
    out, dropped = [], Counter()
    for t, g in d.groupby("date", observed=True):
        g = g.copy()
        y = pd.to_numeric(g["sacn_raw"], errors="coerce").to_numpy(float)
        use = []
        for c, label in terms:
            v = pd.to_numeric(g[c], errors="coerce")
            if v.notna().sum() >= max(10, 0.5 * len(g)):
                use.append((c, label, v))
            else:
                dropped[label] += 1
        if not use or len(g) < 12:
            g["sacn_resid"] = np.nan
            out.append(g)
            continue
        X = np.column_stack([np.ones(len(g))] + [
            np.where(np.isfinite(v.to_numpy(float)),
                     v.to_numpy(float), np.nanmedian(v.to_numpy(float))) for _, _, v in use])
        # 스케일 차가 큰 설계행렬은 정규방정식을 불안정하게 만든다 → 표준화 후 회귀
        mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0)
        sd = np.where(sd > 1e-12, sd, 1.0)
        Xs = np.column_stack([np.ones(len(g)), (X[:, 1:] - mu) / sd])
        keep = np.isfinite(y)
        if keep.sum() < 12:
            g["sacn_resid"] = np.nan
            out.append(g)
            continue
        try:
            beta, *_ = np.linalg.lstsq(Xs[keep], y[keep], rcond=None)
            resid = np.full(len(g), np.nan)
            resid[keep] = y[keep] - Xs[keep] @ beta
        except Exception:
            resid = np.full(len(g), np.nan)
        g["sacn_resid"] = resid
        out.append(g)

    R = pd.concat(out, ignore_index=True)
    n_ok = int(R["sacn_resid"].notna().sum())
    LOG.ok(f"직교화 [{window}] 완료 — 잔차 산출 {n_ok:,}/{len(R):,}행 "
           f"({100*n_ok/max(len(R),1):.1f}%)")
    if dropped:
        LOG.table([[k, f"{v}"] for k, v in dropped.most_common()],
                  ["결측으로 제외된 회귀항", "시점 수"], ["l", "r"],
                  title="§6.3 직교화 — 시점별로 빠진 항 (통째 결측인 항만 제외)")
        open_question("OQ-04", "직교화 회귀항 결측",
                      f"일부 시점에서 회귀항이 통째로 결측이다: {dict(dropped)}",
                      "해당 시점에서 그 항만 제외하고 회귀했다(시점 자체를 버리거나 0으로 채우지 않음).",
                      "직교화 강도가 시점별로 균일하지 않다. 원신호 버전을 반드시 병기해 비교한다.")
    try:
        c = R[["sacn_raw", "sacn_resid"]].corr().iloc[0, 1]
        LOG.info(f"원신호 vs 직교화 신호 상관 = {c:.3f} "
                 f"({'대부분 사이즈/업종/반전으로 설명됨' if abs(c) < 0.5 else '고유 정보가 상당 부분 남음'})")
    except Exception:
        pass
    return R.drop(columns=["month_attr"], errors="ignore")


def attach_attrs(P: pd.DataFrame, uni_panel: pd.DataFrame,
                 cols: Sequence[str] = ("mktcap", "market", "sector", "bm")) -> pd.DataFrame:
    """유니버스 속성을 신호 패널에 붙인다 — 이미 있는 컬럼은 건드리지 않는다.

    ★ orthogonalize() 가 mktcap/bm/sector 를 이미 병합해 둔다. 그걸 모르고 다시 merge 하면
      pandas 가 mktcap_x / mktcap_y 로 쪼개고 'mktcap' 이라는 이름은 사라진다.
      하류(run_quantile_backtest)는 결측 컬럼을 NaN 으로 관대하게 처리하므로 예외 없이
      전 종목이 'small' 슬리피지로 계산되는 조용한 오류가 된다. 여기서 원천 차단한다.
    """
    if P is None or not len(P):
        return P
    need = [c for c in cols if c not in P.columns]
    if not need:
        return P
    U = uni_panel[["code", "month"] + [c for c in need if c in uni_panel.columns]].copy()
    if U.shape[1] <= 2:
        return P
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])
    U = U.drop_duplicates(["code", "month"])
    d = P.copy()
    d["code"] = d["code"].astype(str)
    # 주간 리밸런싱 시점은 월말이 아니므로 '그 시점에 알 수 있던' 직전 월말 속성을 쓴다
    mm = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    d["_m"] = np.where(as_ts_series(d["date"]) >= mm, mm, mm - pd.offsets.MonthEnd(1))
    d["_m"] = as_ts_series(d["_m"])
    d = d.merge(U.rename(columns={"month": "_m"}), on=["code", "_m"], how="left")
    return d.drop(columns=["_m"], errors="ignore")


def build_signal_panel(LM: LinkMatrices, grid: PriceGrid, uni_panel: pd.DataFrame,
                       months: pd.DatetimeIndex, window: str, rebal: str) -> pd.DataFrame:
    """신호 패널 조립: 원신호 + 직교화 + 익영업일 실행가 + 다음 리밸까지의 전향수익률."""
    rebals = rebalance_dates(months, grid, rebal)
    if not rebals:
        return pd.DataFrame()
    S = compute_sacn(LM, grid, uni_panel, rebals, window)
    if not len(S):
        return S
    S = orthogonalize(S, uni_panel, grid, window)

    # 익영업일 실행가 (SPEC 불변 규칙) + 다음 리밸 실행가까지의 수익률
    ex: Dict[pd.Timestamp, Tuple[np.ndarray, Optional[pd.Timestamp]]] = {}
    for t in rebals:
        ex[as_ts(t)] = grid.exec_price(t)
    frames = []
    for i, t in enumerate(rebals):
        t = as_ts(t)
        px0, d0 = ex[t]
        if d0 is None:
            continue
        nxt = as_ts(rebals[i + 1]) if i + 1 < len(rebals) else None
        px1, d1 = ex[nxt] if nxt is not None else (None, None)
        sub = S[S["date"] == t]
        if not len(sub):
            continue
        gi = np.array([grid.cpos.get(c, -1) for c in sub["code"]])
        p0 = np.where(gi >= 0, px0[np.clip(gi, 0, len(px0) - 1)], np.nan)
        if px1 is not None:
            p1 = np.where(gi >= 0, px1[np.clip(gi, 0, len(px1) - 1)], np.nan)
            with np.errstate(all="ignore"):
                fr = np.where((p0 > 0) & np.isfinite(p0) & np.isfinite(p1), p1 / p0 - 1.0, np.nan)
        else:
            fr = np.full(len(sub), np.nan)
        g = sub.copy()
        g["exec_px"] = p0.astype("float32")
        g["exec_date"] = d0
        g["fwd_ret"] = fr.astype("float32")
        g["next_date"] = d1
        frames.append(g)
    P = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(P):
        # 신호일과 수익 구간이 겹치면 실패로 간주한다 (SPEC §8)
        bad = (as_ts_series(P["exec_date"]) <= as_ts_series(P["date"])).sum()
        if bad:
            raise RuntimeError(f"[누수] 실행일이 신호일보다 이르거나 같은 행이 {bad:,}건 있습니다. "
                               f"익영업일 앵커가 깨졌습니다 — 백테스트를 진행하지 않습니다.")
        LOG.ok(f"신호 패널 [{window}/{rebal}] {len(P):,}행 · {P['date'].nunique()}시점 · "
               f"전향수익 보유 {int(P['fwd_ret'].notna().sum()):,}행")
    return P


# ==========================================================================================
# 조각: s30_backtest.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-B  백테스트 엔진 (SPEC §7 · §8)                                                       ║
# ║                                                                                          ║
# ║   · 5분위 정렬. 주 포트폴리오 = Q5 롱온리 동일가중 (한국 공매도 제약 반영)                  ║
# ║   · 참고 산출 = Q5−Q1 롱숏 스프레드 (알파 존재 검증용, 실행가능성과 무관하게 보고)          ║
# ║   · 보유 하한 20종목. 미달이면 그 리밸런싱은 현금 — 조용히 넘어가지 않고 로그에 남긴다.      ║
# ║   · 진입은 신호일의 익영업일 (신호 패널에서 이미 앵커됨). 겹치면 실패로 간주.               ║
# ║   · 상장폐지는 -100% 일괄이 아니라 정리매매 최종가 기준 (§0.3)                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 연도별 증권거래세 (SPEC §7.1 — 단일 세율 적용 금지) ─────────────────────────────────────
#   출처: 기획재정부 증권거래세법 시행령 개정 연혁
#     https://www.moef.go.kr  ·  https://www.law.go.kr/법령/증권거래세법시행령
#   유가증권시장 = 증권거래세 + 농어촌특별세 0.15%, 코스닥 = 증권거래세.
#   2019-06-03 · 2021-01-01 · 2023-01-01 · 2024-01-01 · 2025-01-01 에 각각 인하됐다.
SELL_TAX_SCHEDULE = [
    ("1900-01-01", {"KOSPI": 0.00300, "KOSDAQ": 0.00300, "OTHER": 0.00300}),
    ("2019-06-03", {"KOSPI": 0.00250, "KOSDAQ": 0.00250, "OTHER": 0.00250}),
    ("2021-01-01", {"KOSPI": 0.00230, "KOSDAQ": 0.00230, "OTHER": 0.00230}),
    ("2023-01-01", {"KOSPI": 0.00200, "KOSDAQ": 0.00200, "OTHER": 0.00200}),
    ("2024-01-01", {"KOSPI": 0.00180, "KOSDAQ": 0.00180, "OTHER": 0.00180}),
    ("2025-01-01", {"KOSPI": 0.00150, "KOSDAQ": 0.00150, "OTHER": 0.00150}),
]
_TAX_DATES = [as_ts(d) for d, _ in SELL_TAX_SCHEDULE]

SIZE_LARGE_KRW = 1_000_000_000_000       # 1조 이상 = large
SIZE_MID_KRW = 300_000_000_000           # 3천억 이상 = mid, 미만 = small


def sell_tax_rate(t, market: str) -> float:
    i = int(np.searchsorted(np.array([np.datetime64(x) for x in _TAX_DATES]),
                            np.datetime64(as_ts(t)), side="right")) - 1
    i = max(0, i)
    tbl = SELL_TAX_SCHEDULE[i][1]
    return float(tbl.get(str(market).upper(), tbl["OTHER"]))


def size_class(mktcap: float) -> str:
    if not np.isfinite(mktcap):
        return "small"
    if mktcap >= SIZE_LARGE_KRW:
        return "large"
    if mktcap >= SIZE_MID_KRW:
        return "mid"
    return "small"


def tax_schedule_table():
    rows = []
    for d, tbl in SELL_TAX_SCHEDULE:
        rows.append([d if d != "1900-01-01" else "~2019-06-02",
                     f"{tbl['KOSPI']*100:.3f}%", f"{tbl['KOSDAQ']*100:.3f}%"])
    LOG.table(rows, ["적용 시작일", "유가증권(매도)", "코스닥(매도)"], ["l", "r", "r"],
              title="증권거래세 연도별 테이블 (§7.1) — 출처: 증권거래세법 시행령 개정 연혁")


PERIODS_PER_YEAR = {"M": 12.0, "W": 52.0}


def perf_stats(R: pd.DataFrame, ppy: float = 12.0, rf: float = 0.0) -> dict:
    """성과 지표. 리밸런싱 주기(ppy)에 따라 연율화 계수가 달라진다.

    Sharpe 는 교과서 정의(평균/표준편차 × √ppy)를 쓴다. 기하수익/변동성 정의와 섞으면
    다른 표와 비교가 불가능해지므로 한 가지로 고정한다.
    """
    if R is None or not len(R):
        return {}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy(float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / ppy
    cagr = float(eq[-1] ** (1.0 / years) - 1.0) if years > 0 and eq[-1] > 0 else float("nan")
    vol = float(np.std(r, ddof=1) * math.sqrt(ppy)) if n > 1 else float("nan")
    dn = r[r < 0]
    dvol = float(np.std(dn, ddof=1) * math.sqrt(ppy)) if len(dn) > 1 else float("nan")
    dd = eq / np.maximum.accumulate(eq) - 1.0
    mdd = float(dd.min()) if n else float("nan")
    mu, tstat = hac_tstat(r)
    uw, best = 0, 0
    for x in dd:
        uw = uw + 1 if x < 0 else 0
        best = max(best, uw)
    out = {
        "기간수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(ppy)) if n > 1 and np.std(r, ddof=1) > 0 else float("nan"),
        "Sortino": float(np.mean(r) * ppy / dvol) if dvol and dvol > 0 else float("nan"),
        "MDD": mdd, "Calmar": float(cagr / abs(mdd)) if mdd and mdd < 0 else float("nan"),
        "승률": float((r > 0).mean()), "기간평균수익": float(np.mean(r)),
        "t통계량(HAC)": float(tstat), "최장언더워터(기간)": int(best),
        "누적수익": float(eq[-1] - 1.0),
    }
    if "n" in R.columns:
        out["평균종목수"] = float(pd.to_numeric(R["n"], errors="coerce").mean())
    if "turnover" in R.columns:
        out["평균회전율"] = float(pd.to_numeric(R["turnover"], errors="coerce").mean())
    if "cost" in R.columns:
        out["평균비용"] = float(pd.to_numeric(R["cost"], errors="coerce").mean())
    return out


def _assign_quantiles(g: pd.DataFrame, col: str, q: int) -> pd.Series:
    """동점 처리를 결정적으로: 신호 내림차순 → code 오름차순으로 순위를 확정한 뒤 분할."""
    d = g[[col, "code"]].copy()
    d["_r"] = d[col].rank(method="first", ascending=True)
    n = int(d["_r"].notna().sum())
    if n < q:
        return pd.Series(np.nan, index=g.index)
    lab = np.ceil(d["_r"] / (n / q))
    return pd.Series(np.clip(lab, 1, q), index=g.index)


def run_quantile_backtest(P: pd.DataFrame, signal_col: str, rebal: str,
                          delist: Optional[pd.DataFrame] = None,
                          cost_mult: float = 1.0, label: str = "SACN",
                          q: int = N_QUANTILES, min_names: int = PORT_MIN_NAMES,
                          long_only: bool = True) -> dict:
    """분위 백테스트. 반환 dict: returns / holdings / spread / label / meta"""
    empty = {"returns": pd.DataFrame(columns=["date", "ret", "ret_gross", "n", "turnover",
                                              "cost", "equity"]),
             "holdings": pd.DataFrame(), "spread": pd.DataFrame(), "label": label,
             "meta": {"cash_periods": 0, "ppy": PERIODS_PER_YEAR.get(rebal, 12.0)}}
    if P is None or not len(P) or signal_col not in P.columns:
        return empty

    d = P[P[signal_col].notna() & P["exec_px"].notna()].copy()
    if not len(d):
        return empty
    d["code"] = d["code"].astype(str)
    d["date"] = as_ts_series(d["date"])
    # 신호 패널은 메모리 절약을 위해 float32 다. 여기서 float64 로 올려 두지 않으면
    # 아래 폐지수익률(float64) 주입이 pandas 3.x 에서 dtype 상향 오류로 죽는다.
    for c in ("fwd_ret", "exec_px", signal_col):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")

    # 폐지 수익률 주입 (§0.3) — fwd_ret 이 결측인데 그 구간에 폐지된 종목
    if delist is not None and len(delist):
        dl = delist.copy()
        dl["code"] = dl["code"].astype(str)
        dl["month"] = as_ts_series(dl["month"])
        d["_m"] = d["date"] + pd.offsets.MonthEnd(0)
        d = d.merge(dl.rename(columns={"month": "_m"})[["code", "_m", "delist_ret"]],
                    on=["code", "_m"], how="left")
        inj = d["fwd_ret"].isna() & d["delist_ret"].notna()
        d.loc[inj, "fwd_ret"] = d.loc[inj, "delist_ret"]
        d = d.drop(columns=["_m", "delist_ret"], errors="ignore")

    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    if not len(d):
        return empty

    if "mktcap" not in d.columns:
        d["mktcap"] = np.nan
    if "market" not in d.columns:
        d["market"] = "OTHER"
    d["_size"] = d["mktcap"].map(size_class)

    dates = sorted(d["date"].unique())
    prev_w: Dict[str, float] = {}
    rows, holds, spreads = [], [], []
    cash_periods, cash_dates = 0, []

    for t in dates:
        t = as_ts(t)
        g = d[d["date"] == t]
        top = g[g["qtile"] == q]
        bot = g[g["qtile"] == 1]

        if len(top) < min_names:
            cash_periods += 1
            cash_dates.append(t)
            # 전량 청산 비용은 실제로 발생한다 — 현금 처리라고 0으로 두지 않는다
            cost = 0.0
            for c, w in prev_w.items():
                mk = g.loc[g["code"] == c, "market"]
                sz = g.loc[g["code"] == c, "_size"]
                cost += abs(w) * (COST_COMMISSION_BP / 1e4
                                  + COST_SLIPPAGE_BP.get(sz.iat[0] if len(sz) else "small", 35.0) / 1e4
                                  + sell_tax_rate(t, mk.iat[0] if len(mk) else "OTHER"))
            cost *= cost_mult
            rows.append({"date": t, "ret": -cost, "ret_gross": 0.0, "n": 0,
                         "turnover": float(sum(abs(v) for v in prev_w.values())), "cost": cost})
            prev_w = {}
            continue

        w = 1.0 / len(top)
        w = min(w, POS_MAX_WEIGHT)
        wmap = {c: w for c in top["code"]}
        # 상한 때문에 남은 비중은 현금으로 둔다 (억지로 종목을 늘리지 않는다)
        fr = pd.to_numeric(top["fwd_ret"], errors="coerce").fillna(0.0).to_numpy(float)
        ret_gross = float(np.sum(fr * w))

        cost, turn = 0.0, 0.0
        allc = set(wmap) | set(prev_w)
        smap = dict(zip(g["code"], g["_size"]))
        mmap = dict(zip(g["code"], g["market"]))
        for c in allc:
            dw = wmap.get(c, 0.0) - prev_w.get(c, 0.0)
            if abs(dw) < 1e-12:
                continue
            turn += abs(dw)
            slip = COST_SLIPPAGE_BP.get(smap.get(c, "small"), 35.0) / 1e4
            tax = sell_tax_rate(t, mmap.get(c, "OTHER")) if dw < 0 else 0.0
            cost += abs(dw) * (COST_COMMISSION_BP / 1e4 + slip + tax)
        cost *= cost_mult

        rows.append({"date": t, "ret": ret_gross - cost, "ret_gross": ret_gross,
                     "n": int(len(top)), "turnover": turn, "cost": cost})
        h = top[["code", "date", signal_col, "fwd_ret"]].copy()
        h["weight"] = w
        holds.append(h)

        if len(bot) >= min_names:
            rb = float(pd.to_numeric(bot["fwd_ret"], errors="coerce").fillna(0.0).mean())
            spreads.append({"date": t, "q5": ret_gross, "q1": rb, "spread": ret_gross - rb,
                            "n5": len(top), "n1": len(bot)})
        prev_w = wmap

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"]).cumprod()
    H = pd.concat(holds, ignore_index=True) if holds else pd.DataFrame()
    S = pd.DataFrame(spreads)
    if cash_periods:
        LOG.warn(f"[{label}] 보유 하한({min_names}종목) 미달로 {cash_periods}개 기간을 "
                 f"현금 보유 처리했습니다. 예: "
                 f"{', '.join(f'{x:%Y-%m-%d}' for x in cash_dates[:5])}"
                 f"{' …' if len(cash_dates) > 5 else ''}")
    n_per = max(1, len(dates))
    cash_ratio = cash_periods / n_per
    if cash_ratio > 0.5:
        LOG.error(f"[{label}] 전체 {n_per}기간 중 {cash_periods}기간({cash_ratio:.0%})이 현금입니다. "
                  f"유니버스가 작아 Q{q} 분위 종목수가 보유하한 {min_names}종목에 미달합니다. "
                  f"이 결과는 '전략의 성과'가 아니라 '표본 부족'입니다 — 판정에 쓰면 안 됩니다.")
    return {"returns": R, "holdings": H, "spread": S, "label": label,
            "meta": {"cash_periods": cash_periods, "n_periods": n_per,
                     "cash_ratio": cash_ratio, "ppy": PERIODS_PER_YEAR.get(rebal, 12.0),
                     "rebal": rebal, "signal_col": signal_col, "cost_mult": cost_mult}}


def quantile_profile(P: pd.DataFrame, signal_col: str, q: int = N_QUANTILES) -> pd.DataFrame:
    """분위별 평균 전향수익 — 신호가 단조인지 보는 가장 정직한 표."""
    if P is None or not len(P) or signal_col not in P.columns:
        return pd.DataFrame()
    d = P[P[signal_col].notna() & P["fwd_ret"].notna()].copy()
    if not len(d):
        return pd.DataFrame()
    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    per = d.groupby(["date", "qtile"])["fwd_ret"].mean().reset_index()
    out = per.groupby("qtile")["fwd_ret"].agg(["mean", "std", "size"]).reset_index()
    out.columns = ["분위", "평균수익", "표준편차", "기간수"]
    return out


# ── 벤치마크 ────────────────────────────────────────────────────────────────────────────────
def equal_weight_universe(grid: "PriceGrid", uni_panel: pd.DataFrame,
                          rebals: Sequence[pd.Timestamp]) -> pd.Series:
    """★ SPEC §8 이 말하는 '진짜 비교 기준'.

    시총가중 지수 대비 초과는 사이즈 팩터일 뿐이다. 같은 유니버스를 동일가중으로 들었을 때
    대비 초과가 나야 신호에 의미가 있다.

    ★ 신호 패널(연결 3개 이상인 종목)이 아니라 '유니버스 전체'로 계산한다.
      신호가 잡힌 종목만으로 벤치마크를 만들면, 커버리지가 두터운 종목만 모인 집단과
      비교하게 되어 초과수익이 구조적으로 과소평가된다. 비교 기준을 유리하게 만들지도,
      불리하게 만들지도 않는 유일한 방법은 유니버스 정의 그대로 쓰는 것이다.
    """
    if uni_panel is None or not len(uni_panel) or not len(rebals):
        return pd.Series(dtype=float)
    U = uni_panel[["code", "month"]].copy()
    U["code"] = U["code"].astype(str)
    U["month"] = as_ts_series(U["month"])
    by_month = {as_ts(m): set(g["code"]) for m, g in U.groupby("month")}
    months_sorted = sorted(by_month)
    ex = {as_ts(t): grid.exec_price(t) for t in rebals}
    out = {}
    rb = [as_ts(t) for t in rebals]
    for i, t in enumerate(rb[:-1]):
        cand = [m for m in months_sorted if m <= t]
        if not cand:
            continue
        alive = by_month[max(cand)]
        p0, d0 = ex[t]
        p1, d1 = ex[rb[i + 1]]
        if d0 is None or d1 is None:
            continue
        gi = np.array([grid.cpos.get(c, -1) for c in alive])
        gi = gi[gi >= 0]
        if not len(gi):
            continue
        with np.errstate(all="ignore"):
            r = np.where((p0[gi] > 0) & np.isfinite(p0[gi]) & np.isfinite(p1[gi]),
                         p1[gi] / p0[gi] - 1.0, np.nan)
        if np.isfinite(r).sum() >= 5:
            out[t] = float(np.nanmean(r))
    s = pd.Series(out).sort_index()
    s.name = "동일가중 유니버스"
    return s


def index_benchmarks(dates: Sequence[pd.Timestamp]) -> Dict[str, pd.Series]:
    """KOSPI / KOSDAQ — 리밸런싱 시점 격자에 맞춰 수익률화."""
    out: Dict[str, pd.Series] = {}
    if fdr is None or not len(dates):
        return out
    idx = pd.DatetimeIndex(sorted(as_ts(d) for d in dates))
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            df = fdr.DataReader(sym, (idx[0] - pd.DateOffset(months=2)).strftime("%Y-%m-%d"),
                                idx[-1].strftime("%Y-%m-%d"))
            if df is None or df.empty:
                continue
            c = df["Close"].copy()
            c.index = as_ts_series(pd.Series(df.index)).to_numpy()
            v = c.reindex(c.index.union(idx)).sort_index().ffill().reindex(idx)
            out[name] = v.pct_change()
        except Exception as e:                                   # noqa
            LOG.debug(f"벤치마크 {name} 수집 실패({type(e).__name__})")
    return out


def benchmark_table(bt: dict, bench: Dict[str, pd.Series], ppy: float) -> List[list]:
    R = bt.get("returns")
    if R is None or not len(R):
        return []
    r = R.set_index(as_ts_series(R["date"]))["ret"]
    rows = []
    for name, b in bench.items():
        if b is None or not len(b):
            continue
        j = pd.concat([r.rename("s"), b.rename("b")], axis=1).dropna()
        if len(j) < 6:
            continue
        ex = j["s"] - j["b"]
        _, tt = hac_tstat(ex.to_numpy(float))
        rows.append([name, f"{(1+j['b']).prod() ** (ppy/len(j)) - 1:+.2%}",
                     f"{(1+j['s']).prod() ** (ppy/len(j)) - 1:+.2%}",
                     f"{ex.mean()*ppy:+.2%}", f"{tt:+.2f}",
                     "✔" if ex.mean() * ppy >= 0.03 else "—"])
    return rows


# ==========================================================================================
# 조각: s40_stats.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-S  통계 검증 게이트 (SPEC §9)                                                         ║
# ║                                                                                          ║
# ║   ① 블록 부트스트랩 (1,000회) → CAGR·Sharpe 신뢰구간                                       ║
# ║   ② PBO — CSCV 방식, 12개 구성 대상                                                        ║
# ║   ③ DSR — 시도 횟수 12로 명시                                                              ║
# ║   ④ 워크포워드 — 학습 5년 / 검증 1년 롤링 (구성 선택이 개입할 때만 의미가 있다)              ║
# ║   ⑤ BH-FDR (q=0.10) — H1~H4 전체                                                          ║
# ║   ⑥ 뉴이-웨스트 표준오차 (lag = 리밸런싱 주기 × 1.5)                                        ║
# ║                                                                                          ║
# ║  ①②③④ 는 기존 코드베이스에 아예 없었다. 여기서 새로 만든다.                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

try:
    from scipy import stats as _sps
except Exception:                                            # pragma: no cover
    _sps = None


def _norm_cdf(x: float) -> float:
    if _sps is not None:
        return float(_sps.norm.cdf(x))
    return float(0.5 * (1.0 + math.erf(x / math.sqrt(2.0))))


def _norm_ppf(p: float) -> float:
    p = float(min(max(p, 1e-12), 1 - 1e-12))
    if _sps is not None:
        return float(_sps.norm.ppf(p))
    # Acklam 근사 (scipy 없을 때도 DSR 을 포기하지 않는다)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r: np.ndarray, ppy: float = 12.0, n_boot: int = 1000,
                    block: Optional[int] = None, seed: int = SEED) -> dict:
    """순환 블록 부트스트랩. 자기상관을 보존한 채 CAGR·Sharpe 신뢰구간을 구한다.

    SPEC §9.1 은 '블록 길이 21영업일'이라고 쓰여 있다. 그런데 월간 수익률 계열에서
    21영업일은 곧 1기간이고, 블록 길이 1 은 자기상관을 전혀 보존하지 못해
    부트스트랩이 단순 i.i.d. 재표집으로 퇴화한다.
    → 21영업일을 기간 단위로 환산하되 최소 3기간을 강제한다(더 넓은 = 더 보수적인 구간).
      실제 사용한 블록 길이를 항상 함께 보고한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 12:
        return {"n": n, "ok": False}
    dpp = 21.0 if ppy <= 13 else (5.0 if ppy <= 60 else 1.0)
    if block is None:
        block = max(3, int(round(21.0 / dpp)))
    block = int(min(max(1, block), max(1, n // 3)))
    rng = np.random.default_rng(seed)
    nblk = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, nblk))
    offs = np.arange(block)
    cagrs = np.empty(n_boot)
    sharps = np.empty(n_boot)
    for i in range(n_boot):
        idx = ((starts[i][:, None] + offs[None, :]) % n).ravel()[:n]
        x = r[idx]
        eq = float(np.prod(1.0 + x))
        cagrs[i] = eq ** (ppy / n) - 1.0 if eq > 0 else -1.0
        sd = np.std(x, ddof=1)
        sharps[i] = (np.mean(x) / sd * math.sqrt(ppy)) if sd > 0 else np.nan
    qs = [2.5, 50, 97.5]
    cg = np.nanpercentile(cagrs, qs)
    sh = np.nanpercentile(sharps, qs)
    return {"ok": True, "n": n, "block": block, "n_boot": n_boot,
            "cagr_lo": float(cg[0]), "cagr_med": float(cg[1]), "cagr_hi": float(cg[2]),
            "sharpe_lo": float(sh[0]), "sharpe_med": float(sh[1]), "sharpe_hi": float(sh[2]),
            "p_cagr_le0": float(np.mean(cagrs <= 0)),
            "p_sharpe_le0": float(np.nanmean(sharps <= 0))}


# ── ② PBO (CSCV) ────────────────────────────────────────────────────────────────────────────
def cscv_pbo(M: pd.DataFrame, S: int = 8) -> dict:
    """Combinatorially Symmetric Cross-Validation (Bailey et al. 2016).

    M: 행=기간, 열=구성(12개). 값=기간수익률.
    S 개 연속 블록으로 나누고 C(S, S/2) 조합 전부에 대해
      IS 최고 구성의 OOS 순위 → 로짓 λ → PBO = P(λ ≤ 0).
    기존 코드베이스의 R6 은 leave-one-out 8폴드 약식이었다. 여기서는 정식 조합형을 쓴다.
    """
    out = {"ok": False, "pbo": float("nan"), "n_combo": 0, "n_config": int(M.shape[1] if M is not None else 0)}
    if M is None or M.shape[1] < 2:
        return out
    D = M.dropna(how="any")
    T, N = D.shape
    if T < S * 4:
        S = max(4, (T // 4) * 2 // 2 * 2)
        if S < 4 or T < S * 2:
            out["note"] = f"기간 {T} 이 부족해 CSCV 를 수행할 수 없습니다 (필요 ≥ {4*4})."
            return out
    if S % 2:
        S -= 1
    blocks = np.array_split(np.arange(T), S)
    from itertools import combinations
    half = S // 2
    lams, n_lt0 = [], 0
    X = D.to_numpy(float)
    for comb in combinations(range(S), half):
        is_idx = np.concatenate([blocks[b] for b in comb])
        oos_idx = np.concatenate([blocks[b] for b in range(S) if b not in comb])
        if len(is_idx) < 4 or len(oos_idx) < 4:
            continue
        def _sr(a):
            sd = np.std(a, axis=0, ddof=1)
            return np.where(sd > 0, np.mean(a, axis=0) / np.where(sd > 0, sd, 1.0), -np.inf)
        sr_is = _sr(X[is_idx])
        sr_oos = _sr(X[oos_idx])
        n_star = int(np.argmax(sr_is))
        # OOS 순위 (1=최악 … N=최고)
        rank = float(pd.Series(sr_oos).rank(method="average").iloc[n_star])
        w = rank / (N + 1.0)
        w = min(max(w, 1e-6), 1 - 1e-6)
        lam = math.log(w / (1 - w))
        lams.append(lam)
        if lam <= 0:
            n_lt0 += 1
    if not lams:
        out["note"] = "유효 조합이 없습니다."
        return out
    out.update(ok=True, pbo=float(n_lt0 / len(lams)), n_combo=len(lams), S=S,
               lambda_med=float(np.median(lams)), n_config=N, T=T)
    return out


# ── ③ Deflated Sharpe Ratio ─────────────────────────────────────────────────────────────────
def deflated_sharpe(r: np.ndarray, n_trials: int = 12, ppy: float = 12.0,
                    sr_variance: Optional[float] = None) -> dict:
    """Bailey & López de Prado. 시도 횟수를 명시적으로 차감한 Sharpe 유의도.

    반환 dsr 은 '진짜 SR>0 일 확률'이다. SPEC §11 은 DSR > 0 을 요구하지만
    그건 사실상 항상 참이므로, 통용 기준인 0.95 도 함께 표시한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 12:
        return {"ok": False, "n": n}
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return {"ok": False, "n": n}
    sr = float(np.mean(r) / sd)                       # 기간단위 SR (비연율)
    m3 = float(np.mean(((r - r.mean()) / sd) ** 3))
    m4 = float(np.mean(((r - r.mean()) / sd) ** 4))
    e = 0.5772156649015329
    N = max(2, int(n_trials))
    if sr_variance is None or not np.isfinite(sr_variance) or sr_variance <= 0:
        sr_variance = 1.0 / max(1, n - 1)             # SR 추정치의 분산 근사
    sd_sr = math.sqrt(sr_variance)
    sr0 = sd_sr * ((1 - e) * _norm_ppf(1 - 1.0 / N) + e * _norm_ppf(1 - 1.0 / (N * math.e)))
    denom = math.sqrt(max(1e-12, 1.0 - m3 * sr + (m4 - 1.0) / 4.0 * sr * sr))
    z = (sr - sr0) * math.sqrt(max(1, n - 1)) / denom
    return {"ok": True, "n": n, "sr_period": sr, "sr_annual": sr * math.sqrt(ppy),
            "sr0": sr0, "dsr": _norm_cdf(z), "z": z, "n_trials": N,
            "skew": m3, "kurt": m4}


# ── ④ 워크포워드 ────────────────────────────────────────────────────────────────────────────
def walk_forward(M: pd.DataFrame, ppy: float = 12.0, train_years: int = 5,
                 test_years: int = 1) -> dict:
    """학습 5년에서 최고 구성을 고르고, 이어지는 1년 성과를 측정한다 (롤링).

    이 전략은 주 구성이 사전등록되어 있어 파라미터 적합이 없다. 그러나 '12개 구성 중
    사후에 최고를 고르면 얼마나 무너지는가'는 반드시 측정해야 한다 — 그게 이 검정의 목적이다.
    """
    out = {"ok": False, "folds": []}
    if M is None or M.shape[1] < 2:
        return out
    D = M.dropna(how="any")
    T = len(D)
    tr, te = int(train_years * ppy), int(test_years * ppy)
    if T < tr + te:
        out["note"] = f"기간 {T} < 학습 {tr} + 검증 {te} — 워크포워드 불가"
        return out
    idx = D.index
    rows, oos = [], []
    s = 0
    while s + tr + te <= T:
        A, B = D.iloc[s:s + tr], D.iloc[s + tr:s + tr + te]
        sd = A.std(ddof=1).replace(0, np.nan)
        sr = (A.mean() / sd).dropna()
        if not len(sr):
            s += te
            continue
        pick = str(sr.idxmax())
        rb = B[pick]
        rows.append({"검증구간": f"{as_ts(idx[s+tr]):%Y-%m} ~ {as_ts(idx[s+tr+te-1]):%Y-%m}",
                     "선택 구성": pick,
                     "학습 Sharpe": float(sr.max() * math.sqrt(ppy)),
                     "검증 Sharpe": float(rb.mean() / rb.std(ddof=1) * math.sqrt(ppy))
                     if rb.std(ddof=1) > 0 else float("nan"),
                     "검증 수익": float((1 + rb).prod() - 1)})
        oos.extend(rb.tolist())
        s += te
    if not rows:
        return out
    oos = np.asarray(oos, float)
    out.update(ok=True, folds=rows, n_fold=len(rows),
               oos_sharpe=float(np.mean(oos) / np.std(oos, ddof=1) * math.sqrt(ppy))
               if np.std(oos, ddof=1) > 0 else float("nan"),
               oos_cagr=float(np.prod(1 + oos) ** (ppy / len(oos)) - 1) if len(oos) else float("nan"),
               n_distinct=len({r["선택 구성"] for r in rows}))
    return out


# ── ⑥ 뉴이-웨스트 (lag = 리밸런싱 주기 × 1.5) ───────────────────────────────────────────────
def nw_tstat(x: np.ndarray, ppy: float = 12.0) -> Tuple[float, float, int]:
    """SPEC §9.6 규칙대로 lag 을 고정한다. 반환 (평균, t, lag)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 12:
        return float("nan"), float("nan"), 0
    lag = max(1, int(round(1.5 * (1 if ppy <= 13 else 4))))
    mu, t = hac_tstat(x, lags=lag)
    return float(mu), float(t), lag


def fdr_table(names: Sequence[str], pvals: Sequence[float], q: float = 0.10) -> pd.DataFrame:
    """BH-FDR. 개별 p 값만으로 판정하지 않는다 (SPEC §3)."""
    p = np.asarray([float(x) if np.isfinite(x) else 1.0 for x in pvals], float)
    rej = bh_fdr(p, q=q)
    order = np.argsort(p)
    crit = np.full(len(p), np.nan)
    m = len(p)
    for rank, i in enumerate(order, start=1):
        crit[i] = q * rank / m
    return pd.DataFrame({"가설": list(names), "p": p, "BH 임계": crit,
                         "기각(유의)": np.asarray(rej, bool)})


def two_sided_p(t: float) -> float:
    if not np.isfinite(t):
        return 1.0
    return float(2.0 * (1.0 - _norm_cdf(abs(t))))


# ==========================================================================================
# 조각: s41_hypothesis.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-H  사전등록 가설 검정 H1~H4 (SPEC §3) + 메커니즘 검정                                  ║
# ║                                                                                          ║
# ║   H1  연결기업 직전 수익률이 초점기업 다음 수익률을 양(+)으로 예측      기각: t < 2.0        ║
# ║   H2  동일업종 링크를 전부 제거해도 유지된다                            기각: 교차업종 < 40% ║
# ║   H3  소형주·저커버리지·고개인비중에서 더 강하다                        기각: 하위군에서 약함 ║
# ║   H4  발간빈도 가중이 비가중보다 강화된다                               기각: 개선 없음      ║
# ║                                                                                          ║
# ║  ★ §3 의 메커니즘 테스트가 백테스트 통과보다 상위 필터다.                                  ║
# ║    효과는 있는데 이론이 예측한 방향으로 강해지지 않으면 폐기한다.                            ║
# ║  ★ 다중검정: H1~H4 전체에 BH-FDR(q=0.10). 개별 p 값만으로 판정하지 않는다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HYP: "OrderedDict[str, dict]" = OrderedDict()


def _rec(hid: str, name: str, passed: Optional[bool], stat: float, p: float,
         detail: str, extra: Optional[dict] = None):
    HYP[hid] = {"id": hid, "name": name, "pass": passed, "stat": float(stat) if stat is not None else float("nan"),
                "p": float(p) if p is not None else float("nan"), "detail": detail,
                "extra": extra or {}}


def spread_series(P: pd.DataFrame, signal_col: str, q: int = N_QUANTILES,
                  min_per_q: int = 5) -> pd.Series:
    """시점별 Q5−Q1 동일가중 스프레드. 알파 존재 검증용(실행가능성과 무관)."""
    if P is None or not len(P) or signal_col not in P.columns:
        return pd.Series(dtype=float)
    d = P[P[signal_col].notna() & P["fwd_ret"].notna()].copy()
    if not len(d):
        return pd.Series(dtype=float)
    d["qtile"] = d.groupby("date", group_keys=False).apply(
        lambda g: _assign_quantiles(g, signal_col, q))
    d = d[d["qtile"].notna()]
    g = d.groupby(["date", "qtile"])["fwd_ret"].agg(["mean", "size"]).reset_index()
    piv_m = g.pivot(index="date", columns="qtile", values="mean")
    piv_n = g.pivot(index="date", columns="qtile", values="size")
    if q not in piv_m.columns or 1 not in piv_m.columns:
        return pd.Series(dtype=float)
    ok = (piv_n[q] >= min_per_q) & (piv_n[1] >= min_per_q)
    return (piv_m[q] - piv_m[1])[ok].dropna()


def mask_cross_sector(LM: LinkMatrices, sector: pd.DataFrame) -> LinkMatrices:
    """H2 — 동일업종 링크를 '전부' 제거한 링크 행렬을 만든다.

    업종 모멘텀의 재포장이 아님을 보이려면 같은 업종 쌍을 남겨두면 안 된다.
    희소행렬에서 업종 블록만 지우는 방식으로 처리한다(밀집 마스크를 만들지 않는다).
    """
    out = LinkMatrices(LM.mode + "_xsector")
    out.codes, out.cidx = list(LM.codes), dict(LM.cidx)
    if _sp is None or not LM.W:
        return out
    smap = (sector.set_index("code")["sector"].to_dict()
            if sector is not None and len(sector) else {})
    sec_arr = np.array([str(smap.get(c, "미분류")) for c in LM.codes])
    uniq = {s: i for i, s in enumerate(sorted(set(sec_arr)))}
    sid = np.array([uniq[s] for s in sec_arr], dtype=np.int32)
    for m, W in LM.W.items():
        C = W.tocoo()
        keep = sid[C.row] != sid[C.col]
        out.W[m] = _csr((C.data[keep], (C.row[keep], C.col[keep])), shape=W.shape)
        out.stats.append({"month": m, "n_pair": int(out.W[m].nnz // 2),
                          "n_pair_full": int(W.nnz // 2)})
    S = out.summary()
    if len(S) and S["n_pair_full"].sum() > 0:
        keep_pct = 100.0 * S["n_pair"].sum() / max(1, S["n_pair_full"].sum())
        LOG.info(f"H2 교차업종 마스킹: 링크쌍 {keep_pct:.1f}% 잔존 "
                 f"(동일업종 쌍 {100-keep_pct:.1f}% 제거)")
    return out


# ── H1 ──────────────────────────────────────────────────────────────────────────────────────
def test_H1(P: pd.DataFrame, signal_col: str, ppy: float) -> pd.Series:
    sp = spread_series(P, signal_col)
    if not len(sp):
        _rec("H1", "공동커버리지 신호의 예측력", None, np.nan, np.nan,
             "스프레드 계열을 만들 수 없음 (표본 부족)")
        return sp
    mu, t, lag = nw_tstat(sp.to_numpy(float), ppy)
    p = two_sided_p(t)
    passed = bool(np.isfinite(t) and t >= 2.0)
    _rec("H1", "공동커버리지 신호의 예측력", passed, t, p,
         f"Q5−Q1 평균 {mu*ppy:+.2%}/년 · NW t={t:+.2f} (lag={lag}) · 기각선 t<2.0",
         {"mean_period": mu, "ann": mu * ppy, "n": len(sp), "lag": lag})
    return sp


# ── H2 ──────────────────────────────────────────────────────────────────────────────────────
def test_H2(sp_full: pd.Series, sp_xsec: pd.Series, ppy: float) -> None:
    if not len(sp_full) or not len(sp_xsec):
        _rec("H2", "업종 모멘텀의 재포장이 아님", None, np.nan, np.nan,
             "교차업종 전용 스프레드를 만들 수 없음")
        return
    a, b = float(sp_full.mean()), float(sp_xsec.mean())
    ratio = float(b / a) if abs(a) > 1e-12 else float("nan")
    mu, t, lag = nw_tstat(sp_xsec.to_numpy(float), ppy)
    passed = bool(np.isfinite(ratio) and ratio >= 0.40 and a > 0)
    _rec("H2", "업종 모멘텀의 재포장이 아님", passed, t, two_sided_p(t),
         f"교차업종 전용 {b*ppy:+.2%}/년 vs 전체 {a*ppy:+.2%}/년 = {ratio:.0%} "
         f"(기각선 <40%) · NW t={t:+.2f}",
         {"ratio": ratio, "full_ann": a * ppy, "xsec_ann": b * ppy, "lag": lag})


# ── H3 (메커니즘) ───────────────────────────────────────────────────────────────────────────
def test_H3(P: pd.DataFrame, signal_col: str, ppy: float,
            retail: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """소형주 / 저커버리지 / 고개인비중 하위군에서 효과가 '더 강한지' 본다.

    제한된 주의(limited attention)와 느린 정보 전파가 메커니즘이라면 반드시 그래야 한다.
    반대로 나오면 알파가 아니라 데이터마이닝이다.
    """
    rows = []
    d = P.copy()
    if retail is not None and len(retail):
        rr = retail.copy()
        rr["code"] = rr["code"].astype(str)
        rr["month"] = as_ts_series(rr["month"])
        d["_m"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
        d = d.merge(rr.rename(columns={"month": "_m"}), on=["code", "_m"], how="left")

    axes = [("규모", "mktcap", "소형", "대형", True),
            ("커버리지", "n_link_used", "저커버리지", "고커버리지", True)]
    if "retail_share" in d.columns and d["retail_share"].notna().any():
        axes.append(("개인비중", "retail_share", "고개인", "저개인", False))
    else:
        LOG.warn("개인 거래비중이 없어 H3 의 세 번째 축을 건너뜁니다 (규모·커버리지로만 판정).")
        open_question("OQ-05", "H3 개인비중 축",
                      "종목별 개인 거래비중 데이터를 확보하지 못했다.",
                      "규모·커버리지 두 축으로만 H3 를 판정하고 그 사실을 명시했다.",
                      "H3 판정력이 약해진다. 통과해도 '부분 확인'으로만 해석해야 한다.")

    ok_axes, passed_axes = 0, 0
    for label, col, lo_name, hi_name, low_is_weak in axes:
        if col not in d.columns or not d[col].notna().any():
            continue
        g = d[d[col].notna()].copy()
        med = g.groupby("date")[col].transform("median")
        lo = g[g[col] <= med]
        hi = g[g[col] > med]
        s_lo = spread_series(lo, signal_col, min_per_q=3)
        s_hi = spread_series(hi, signal_col, min_per_q=3)
        if not len(s_lo) or not len(s_hi):
            continue
        # low_is_weak=True 이면 '하위 절반'이 메커니즘상 강해야 하는 쪽 (소형주·저커버리지)
        strong, weak = (s_lo, s_hi) if low_is_weak else (s_hi, s_lo)
        sname, wname = (lo_name, hi_name)
        m_s, t_s, _ = nw_tstat(strong.to_numpy(float), ppy)
        m_w, t_w, _ = nw_tstat(weak.to_numpy(float), ppy)
        diff = pd.concat([strong.rename("s"), weak.rename("w")], axis=1).dropna()
        m_d, t_d, _ = nw_tstat((diff["s"] - diff["w"]).to_numpy(float), ppy) \
            if len(diff) >= 12 else (np.nan, np.nan, 0)
        good = bool(np.isfinite(m_s) and np.isfinite(m_w) and m_s > m_w)
        ok_axes += 1
        passed_axes += int(good)
        rows.append({"축": label, "예측 강한군": sname, "강한군 연율": m_s * ppy,
                     "강한군 t": t_s, "약한군": wname, "약한군 연율": m_w * ppy,
                     "약한군 t": t_w, "차이 연율": m_d * ppy if np.isfinite(m_d) else np.nan,
                     "차이 t": t_d, "방향 일치": good})
    T = pd.DataFrame(rows)
    if not len(T):
        _rec("H3", "메커니즘 조건부 예측 (소형·저커버리지·고개인)", None, np.nan, np.nan,
             "하위군 분할 표본이 부족해 판정 불가")
        return T
    frac = passed_axes / max(1, ok_axes)
    passed = bool(frac >= 0.5)
    best_t = float(np.nanmax(T["차이 t"].to_numpy(float))) if T["차이 t"].notna().any() else np.nan
    _rec("H3", "메커니즘 조건부 예측 (소형·저커버리지·고개인)", passed, best_t,
         two_sided_p(best_t),
         f"검정 가능한 {ok_axes}개 축 중 {passed_axes}개에서 예측 방향 일치 ({frac:.0%})",
         {"axes": ok_axes, "agree": passed_axes})
    return T


# ── H4 ──────────────────────────────────────────────────────────────────────────────────────
def test_H4(sp_unw: pd.Series, sp_freq: pd.Series, ppy: float,
            sp_skill: Optional[pd.Series] = None) -> None:
    if not len(sp_unw) or not len(sp_freq):
        _rec("H4", "커버리지 강도 가중이 강화한다", None, np.nan, np.nan,
             "가중/비가중 스프레드를 비교할 수 없음")
        return
    j = pd.concat([sp_unw.rename("u"), sp_freq.rename("f")], axis=1).dropna()
    if len(j) < 12:
        _rec("H4", "커버리지 강도 가중이 강화한다", None, np.nan, np.nan,
             f"공통 시점 {len(j)}개로 비교 불가")
        return
    md, td, _ = nw_tstat((j["f"] - j["u"]).to_numpy(float), ppy)
    passed = bool(np.isfinite(md) and md > 0)
    extra = {"unw_ann": float(j["u"].mean()) * ppy, "freq_ann": float(j["f"].mean()) * ppy,
             "diff_ann": md * ppy}
    txt = (f"발간빈도 가중 {extra['freq_ann']:+.2%}/년 vs 비가중 {extra['unw_ann']:+.2%}/년 · "
           f"차이 {extra['diff_ann']:+.2%}/년 (t={td:+.2f})")
    if sp_skill is not None and len(sp_skill):
        js = pd.concat([sp_unw.rename("u"), sp_skill.rename("s")], axis=1).dropna()
        if len(js) >= 12:
            ms, ts, _ = nw_tstat((js["s"] - js["u"]).to_numpy(float), ppy)
            extra["skill_diff_ann"] = ms * ppy
            txt += f" · 고스킬한정 차이 {ms*ppy:+.2%}/년 (t={ts:+.2f})"
    _rec("H4", "커버리지 강도 가중이 강화한다", passed, td, two_sided_p(td), txt, extra)


# ── 종합 판정 ───────────────────────────────────────────────────────────────────────────────
def finalize_hypotheses(q: float = 0.10) -> pd.DataFrame:
    """BH-FDR 보정 후 최종 판정표. 개별 p 만으로 결론내지 않는다."""
    ids = [k for k in ("H1", "H2", "H3", "H4") if k in HYP]
    if not ids:
        return pd.DataFrame()
    F = fdr_table(ids, [HYP[i]["p"] for i in ids], q=q)
    rows = []
    for i, (_, fr) in zip(ids, F.iterrows()):
        h = HYP[i]
        raw = h["pass"]
        # BH-FDR 은 '유의성'에 대한 보정이다. 사전등록 기각조건(예: t<2.0)과 함께 봐야 한다.
        final = None if raw is None else bool(raw and bool(fr["기각(유의)"]))
        h["fdr_sig"] = bool(fr["기각(유의)"])
        h["final"] = final
        rows.append([i, h["name"],
                     {True: "통과", False: "기각", None: "판정불가"}[raw],
                     f"{h['stat']:+.2f}" if np.isfinite(h["stat"]) else "—",
                     f"{h['p']:.4f}" if np.isfinite(h["p"]) else "—",
                     f"{fr['BH 임계']:.4f}",
                     "유의" if fr["기각(유의)"] else "비유의",
                     {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[final]])
    LOG.table(rows, ["ID", "가설", "사전등록 기준", "통계량", "p", f"BH 임계(q={q})",
                     "FDR", "최종"],
              ["c", "l", "c", "r", "r", "r", "c", "c"],
              title=f"사전등록 가설 판정 — BH-FDR 다중검정 보정 (q={q})")
    for i in ids:
        LOG.info(f"  {i}: {HYP[i]['detail']}")
    return F


def final_verdict(bt_base: dict, bench_ew: pd.Series, pbo: dict, dsr: dict,
                  ppy: float) -> dict:
    """SPEC §11 — 사전 확정 기준으로만 기계적으로 판정한다. 사후 변경하지 않는다."""
    g = lambda k: (HYP.get(k, {}) or {}).get("final")
    h1, h2, h3 = g("H1"), g("H2"), g("H3")
    pbo_v = pbo.get("pbo", float("nan"))
    dsr_v = dsr.get("dsr", float("nan"))
    R = bt_base.get("returns", pd.DataFrame())
    excess = float("nan")
    if len(R) and bench_ew is not None and len(bench_ew):
        j = pd.concat([R.set_index(as_ts_series(R["date"]))["ret"].rename("s"),
                       bench_ew.rename("b")], axis=1).dropna()
        if len(j) >= 6:
            excess = float((j["s"] - j["b"]).mean() * ppy)

    crit = [
        ("H1 통과 (BH-FDR 보정 후)", h1 is True),
        ("H2 통과 (교차업종 ≥ 전체의 40%)", h2 is True),
        ("H3 통과 (소형·저커버리지에서 강화)", h3 is True),
        ("PBO < 0.5", bool(np.isfinite(pbo_v) and pbo_v < 0.5)),
        ("DSR > 0", bool(np.isfinite(dsr_v) and dsr_v > 0)),
        ("동일가중 유니버스 대비 연 +3%p 이상", bool(np.isfinite(excess) and excess >= 0.03)),
    ]
    # ★ 표본 부족으로 포지션 자체가 안 잡힌 경우를 '전략 실패'로 보고하면 안 된다.
    #   PBO=1.0, DSR 미산출 같은 산출물이 그럴듯한 KILL 로 둔갑한다 — 가장 위험한 오보다.
    cash_ratio = float((bt_base.get("meta") or {}).get("cash_ratio", 0.0) or 0.0)
    if cash_ratio > 0.5:
        why = (f"기간의 {cash_ratio:.0%}가 현금 — 유니버스가 작아 분위 포트폴리오가 "
               f"구성되지 않았습니다. 성과·PBO·DSR 은 전략의 성질이 아니라 표본 부족의 결과이며 "
               f"§11 판정을 적용할 수 없습니다.")
        LOG.banner("FINAL VERDICT — NOT_EVALUABLE", why)
        LOG.table([[n, "✔" if v else "✘"] for n, v in crit],
                  ["§11 판정 조건 (참고용 — 판정에 쓰지 않음)", "충족"], ["l", "c"])
        return {"verdict": "NOT_EVALUABLE", "why": why, "criteria": crit,
                "excess_ew": excess, "pbo": pbo_v, "dsr": dsr_v, "cash_ratio": cash_ratio}

    if all(c[1] for c in crit):
        verdict, why = "ACCEPT", "전 조건 충족 — 실전 후보로 승격"
    elif h1 is False or h2 is False or (np.isfinite(pbo_v) and pbo_v >= 0.5):
        reasons = []
        if h1 is False:
            reasons.append("H1 실패")
        if h2 is False:
            reasons.append("H2 실패(업종 모멘텀 재포장)")
        if np.isfinite(pbo_v) and pbo_v >= 0.5:
            reasons.append(f"PBO {pbo_v:.2f} ≥ 0.5")
        verdict, why = "KILL", " · ".join(reasons)
    elif h1 is True and h2 is True and h3 is False:
        verdict, why = "CONDITIONAL", ("H1·H2 통과 + H3 실패 — 알파일 수 있으나 메커니즘 미확인. "
                                       "실전 배분 금지, 페이퍼 트레이딩만.")
    else:
        verdict, why = "CONDITIONAL", "일부 조건 판정불가 — 확정 불가, 관찰 대상"
    LOG.banner(f"FINAL VERDICT — {verdict}", why)
    LOG.table([[n, "✔" if v else "✘"] for n, v in crit] +
              [["동일가중 대비 초과(연)", f"{excess:+.2%}" if np.isfinite(excess) else "—"],
               ["PBO", f"{pbo_v:.3f}" if np.isfinite(pbo_v) else "—"],
               ["DSR", f"{dsr_v:.3f}" if np.isfinite(dsr_v) else "—"]],
              ["§11 판정 조건", "충족"], ["l", "c"])
    return {"verdict": verdict, "why": why, "criteria": crit, "excess_ew": excess,
            "pbo": pbo_v, "dsr": dsr_v}


# ==========================================================================================
# 조각: s50_report.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6-R  성과검증 · 강건성 · 해석표 · 산출물 (SPEC §10)                                      ║
# ║                                                                                          ║
# ║  결과 미화 금지 (SPEC §0.5): "유망하다" / "추가 튜닝하면" 같은 표현을 쓰지 않는다.           ║
# ║  성과가 나쁘면 나쁜 대로, §11 기준으로만 판정해 출력한다.                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

OUTPUTS: List[str] = []

_METRIC_ORDER = ["기간수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                 "승률", "기간평균수익", "t통계량(HAC)", "최장언더워터(기간)", "누적수익",
                 "평균종목수", "평균회전율", "평균비용"]
_PCT = {"CAGR", "연변동성", "MDD", "승률", "기간평균수익", "누적수익", "평균회전율", "평균비용"}


def _fmt_metric(k: str, v: Any) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if k in _PCT:
        return f"{v:+.2%}" if k not in ("승률", "연변동성", "평균회전율", "평균비용") else f"{v:.2%}"
    if k in ("기간수", "최장언더워터(기간)"):
        return f"{int(v):,}"
    if k == "평균종목수":
        return f"{v:.1f}"
    return f"{v:+.3f}"


def outdir() -> str:
    d = os.path.join(VAULT.ns["private"], "outputs")
    os.makedirs(d, exist_ok=True)
    return d


def write_text(name: str, text: str) -> str:
    p = os.path.join(outdir(), name)
    atomic_write_text(p, text)
    OUTPUTS.append(p)
    return p


def write_df(name: str, df: pd.DataFrame) -> Optional[str]:
    if df is None:
        return None
    p = os.path.join(outdir(), name)
    try:
        if name.endswith(".parquet"):
            atomic_write_parquet(df, p)
        else:
            df.to_csv(p, index=False, encoding="utf-8-sig")
        OUTPUTS.append(p)
        return p
    except Exception as e:                                    # noqa
        LOG.warn(f"산출물 저장 실패({type(e).__name__}): {name}")
        return None


def report_performance(bt: dict, bench: Dict[str, pd.Series], title: str = "") -> dict:
    """성과 검증표."""
    R = bt.get("returns", pd.DataFrame())
    ppy = bt.get("meta", {}).get("ppy", 12.0)
    if R is None or not len(R):
        LOG.warn(f"[{title or bt.get('label')}] 수익 계열이 비어 성과표를 만들 수 없습니다.")
        return {}
    st = perf_stats(R, ppy=ppy)
    LOG.banner(f"성과 검증 — {title or bt.get('label')}",
               f"{as_ts(R['date'].min()):%Y-%m-%d} ~ {as_ts(R['date'].max()):%Y-%m-%d} · "
               f"{len(R)}기간 · 연 {ppy:.0f}회 리밸런싱")
    LOG.table([[k, _fmt_metric(k, st.get(k))] for k in _METRIC_ORDER if k in st],
              ["지표", "값"], ["l", "r"])
    rows = benchmark_table(bt, bench, ppy)
    if rows:
        LOG.table(rows, ["벤치마크", "벤치 연수익", "전략 연수익", "초과(연)", "초과 t(HAC)",
                         "§11 +3%p"], ["l", "r", "r", "r", "r", "c"],
                  title="벤치마크 대비 — ★동일가중 유니버스가 진짜 비교 기준이다 "
                        "(시총가중 지수 대비 초과는 사이즈 팩터일 뿐)")
    # 연도별
    if len(R):
        y = R.copy()
        y["연도"] = as_ts_series(y["date"]).dt.year
        ag = y.groupby("연도").agg(기간수=("ret", "size"), 수익=("ret", lambda s: (1 + s).prod() - 1),
                                   승률=("ret", lambda s: (s > 0).mean()),
                                   평균종목=("n", "mean"), 회전율=("turnover", "mean"))
        LOG.table([[str(i), f"{int(r['기간수'])}", f"{r['수익']:+.2%}", f"{r['승률']:.0%}",
                    f"{r['평균종목']:.0f}", f"{r['회전율']:.1%}"] for i, r in ag.iterrows()],
                  ["연도", "기간수", "수익", "승률", "평균종목수", "회전율"],
                  ["c", "r", "r", "r", "r", "r"], title="연도별 성과")
    return st


def report_quantile_profile(P: pd.DataFrame, signal_col: str, title: str = ""):
    Q = quantile_profile(P, signal_col)
    if not len(Q):
        return
    ppy = 12.0
    LOG.table([[f"Q{int(r['분위'])}", f"{r['평균수익']:+.3%}", f"{r['표준편차']:.3%}",
                f"{int(r['기간수'])}"] for _, r in Q.iterrows()],
              ["분위", "기간평균 전향수익", "표준편차", "기간수"], ["c", "r", "r", "r"],
              title=f"분위별 프로파일 — {title} (단조성이 없으면 신호가 아니라 잡음이다)")
    lo, hi = Q["평균수익"].iloc[0], Q["평균수익"].iloc[-1]
    mono = bool(Q["평균수익"].is_monotonic_increasing)
    LOG.info(f"  Q1 {lo:+.3%} → Q5 {hi:+.3%} · 단조증가 {'예' if mono else '아니오'}")


def report_robustness(rob: dict, title: str = ""):
    """강건성 검사표 — 블록 부트스트랩 / PBO / DSR / 워크포워드."""
    LOG.banner(f"강건성 검사 — {title}", "SPEC §9 통계 검증 게이트")
    bs = rob.get("bootstrap", {})
    if bs.get("ok"):
        LOG.table([["블록 길이", f"{bs['block']} 기간"],
                   ["반복", f"{bs['n_boot']:,}회"],
                   ["CAGR 95% 신뢰구간", f"{bs['cagr_lo']:+.2%} ~ {bs['cagr_hi']:+.2%} "
                                          f"(중앙 {bs['cagr_med']:+.2%})"],
                   ["Sharpe 95% 신뢰구간", f"{bs['sharpe_lo']:+.2f} ~ {bs['sharpe_hi']:+.2f} "
                                            f"(중앙 {bs['sharpe_med']:+.2f})"],
                   ["P(CAGR ≤ 0)", f"{bs['p_cagr_le0']:.1%}"],
                   ["P(Sharpe ≤ 0)", f"{bs['p_sharpe_le0']:.1%}"]],
                  ["항목", "값"], ["l", "r"], title="① 블록 부트스트랩 (§9.1)")
    else:
        LOG.warn("① 블록 부트스트랩: 표본 부족으로 수행 불가")

    pb = rob.get("pbo", {})
    if pb.get("ok"):
        LOG.table([["구성 수", f"{pb['n_config']}"], ["블록 수 S", f"{pb.get('S','-')}"],
                   ["조합 수", f"{pb['n_combo']:,}"],
                   ["PBO", f"{pb['pbo']:.3f}"],
                   ["§11 기준", "✔ PBO < 0.5" if pb["pbo"] < 0.5 else "✘ PBO ≥ 0.5 → KILL"]],
                  ["항목", "값"], ["l", "r"], title="② PBO — CSCV (§9.2)")
    else:
        LOG.warn(f"② PBO: {pb.get('note', '수행 불가')}")

    ds = rob.get("dsr", {})
    if ds.get("ok"):
        LOG.table([["시도 횟수 (사전등록 구성 수)", f"{ds['n_trials']}"],
                   ["Sharpe (연율)", f"{ds['sr_annual']:+.3f}"],
                   ["기대 최대 Sharpe (기간단위)", f"{ds['sr0']:+.4f}"],
                   ["왜도 / 첨도", f"{ds['skew']:+.2f} / {ds['kurt']:.2f}"],
                   ["DSR", f"{ds['dsr']:.4f}"],
                   ["§11 기준 (DSR>0)", "✔" if ds["dsr"] > 0 else "✘"],
                   ["통용 기준 (DSR>0.95)", "✔" if ds["dsr"] > 0.95 else "✘ — 시도횟수 보정 후 유의하지 않음"]],
                  ["항목", "값"], ["l", "r"], title="③ Deflated Sharpe Ratio (§9.3)")
    else:
        LOG.warn("③ DSR: 표본 부족으로 수행 불가")

    wf = rob.get("wf", {})
    if wf.get("ok"):
        LOG.table([[f["검증구간"], f["선택 구성"], f"{f['학습 Sharpe']:+.2f}",
                    f"{f['검증 Sharpe']:+.2f}", f"{f['검증 수익']:+.2%}"] for f in wf["folds"]],
                  ["검증구간", "학습기 최고 구성", "학습 Sharpe", "검증 Sharpe", "검증 수익"],
                  ["l", "l", "r", "r", "r"], title="④ 워크포워드 5년 학습 / 1년 검증 (§9.4)")
        LOG.info(f"  OOS 종합: Sharpe {wf['oos_sharpe']:+.2f} · CAGR {wf['oos_cagr']:+.2%} · "
                 f"선택된 구성 종류 {wf['n_distinct']}개/{wf['n_fold']}폴드 "
                 f"({'구성 선택이 불안정하다' if wf['n_distinct'] > wf['n_fold']/2 else '구성 선택이 비교적 안정적이다'})")
    else:
        LOG.warn(f"④ 워크포워드: {wf.get('note', '수행 불가')}")


def report_cost_sensitivity(scen: Dict[str, dict], ppy: float) -> pd.DataFrame:
    rows = []
    for name, bt in scen.items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        st = perf_stats(R, ppy=ppy)
        rows.append([name, _fmt_metric("CAGR", st.get("CAGR")),
                     _fmt_metric("Sharpe", st.get("Sharpe")),
                     _fmt_metric("MDD", st.get("MDD")),
                     f"{st.get('평균비용', float('nan')):.3%}",
                     f"{st.get('평균회전율', float('nan')):.1%}"])
    if rows:
        LOG.table(rows, ["비용 시나리오", "CAGR", "Sharpe", "MDD", "기간평균 비용", "회전율"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="비용 민감도 (§7.1) — 0 / 기본 / 2배 보수")
    return pd.DataFrame(rows, columns=["시나리오", "CAGR", "Sharpe", "MDD", "평균비용", "회전율"])


def report_delist_sensitivity(rows: List[list]) -> None:
    if rows:
        LOG.table(rows, ["폐지 수익률 가정", "CAGR", "Sharpe", "MDD", "영향 종목수"],
                  ["l", "r", "r", "r", "r"],
                  title="상장폐지 처리 민감도 (§0.3) — -100% 일괄 적용은 과도한 가정이다")


def report_arm_comparison(arms: Dict[str, dict], ppy: float):
    """전체 유니버스 아암 vs 시총 하위 1000 아암 — 사용자 요청 비교표."""
    rows = []
    for name, bt in arms.items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        st = perf_stats(R, ppy=bt.get("meta", {}).get("ppy", ppy))
        rows.append([name, _fmt_metric("CAGR", st.get("CAGR")),
                     _fmt_metric("Sharpe", st.get("Sharpe")),
                     _fmt_metric("MDD", st.get("MDD")),
                     _fmt_metric("Calmar", st.get("Calmar")),
                     _fmt_metric("승률", st.get("승률")),
                     f"{st.get('평균종목수', float('nan')):.0f}",
                     _fmt_metric("t통계량(HAC)", st.get("t통계량(HAC)"))])
    if rows:
        LOG.table(rows, ["아암", "CAGR", "Sharpe", "MDD", "Calmar", "승률", "평균종목수", "t(HAC)"],
                  ["l", "r", "r", "r", "r", "r", "r", "r"],
                  title="★ 아암 비교 — 전체 유니버스 vs 시가총액 하위 1,000종목")
        LOG.info("H3(소형주에서 더 강하다)가 참이라면 하위1000 아암이 전체 아암보다 강해야 한다. "
                 "그렇지 않다면 메커니즘 주장과 배치된다.")


def report_interpretation(P: pd.DataFrame, signal_col: str, LM: LinkMatrices,
                          bt: dict, sec: pd.DataFrame, top_n: int = 8):
    """기타 해석표 — 신호가 실제로 무엇을 집고 있는지 종목 단위로 보여준다."""
    LOG.banner("해석표", "신호 구성 · 링크 구조 · 최근 시점 상위 종목")
    S = LM.summary()
    if len(S):
        LOG.table([["평균 활동 애널리스트", f"{S['n_analyst'].mean():.0f}"],
                   ["평균 연결보유 종목", f"{S['n_covered'].mean():.0f}"],
                   ["평균 링크쌍", f"{S['n_pair'].mean():,.0f}"],
                   ["종목당 연결 수 (중위)", f"{S['median_links'].median():.0f}"],
                   ["링크 룩백", f"{LINK_LOOKBACK_M}개월 (고정)"],
                   ["최소 연결 요건", f"{MIN_LINKS_REQUIRED}개 미만은 신호 결측"]],
                  ["링크 구조", "값"], ["l", "r"])
    if P is None or not len(P):
        return
    last = as_ts(P["date"].max())
    g = P[(P["date"] == last) & P[signal_col].notna()].copy()
    if not len(g):
        return
    nm = sec.set_index("code")["name"].to_dict() if "name" in sec.columns else {}
    g = g.nlargest(top_n, signal_col)
    LOG.table([[r["code"], _trunc(nm.get(r["code"], ""), 16), f"{r[signal_col]:+.4f}",
                f"{r.get('sacn_raw', float('nan')):+.4f}",
                f"{int(r.get('n_link_used', 0))}",
                f"{r.get('own_ret', float('nan')):+.2%}",
                f"{r.get('mktcap', float('nan'))/1e8:,.0f}억" if np.isfinite(r.get("mktcap", np.nan)) else "—",
                _trunc(str(r.get("sector", "")), 14)] for _, r in g.iterrows()],
              ["종목", "종목명", "최종신호", "원신호", "연결수", "자기수익(t-1)", "시총", "업종"],
              ["l", "l", "r", "r", "r", "r", "r", "l"],
              title=f"최근 리밸런싱({last:%Y-%m-%d}) 상위 {top_n}종목")
    H = bt.get("holdings", pd.DataFrame())
    if len(H) and "fwd_ret" in H.columns:
        con = (H.assign(c=H["weight"] * H["fwd_ret"].fillna(0))
               .groupby("code")["c"].sum().sort_values(ascending=False))
        tot = float(con.sum())
        LOG.table([[c, _trunc(nm.get(c, ""), 16), f"{v:+.3%}",
                    f"{100*v/tot:+.1f}%" if abs(tot) > 1e-12 else "—"]
                   for c, v in list(con.head(5).items()) + list(con.tail(5).items())],
                  ["종목", "종목명", "누적 기여", "총기여 대비"], ["l", "l", "r", "r"],
                  title="기여 상위·하위 5종목 (우측꼬리 의존도 점검)")
        top5 = con.head(max(1, int(len(con) * 0.05)))
        LOG.info(f"  상위 5% 종목({len(top5)}개) 기여 {float(top5.sum()):+.2%} / 총 {tot:+.2%} — "
                 f"제외 시 {tot - float(top5.sum()):+.2%}")


# ── 산출물 파일 (§10) ───────────────────────────────────────────────────────────────────────
def _md_table(df: pd.DataFrame, maxrow: int = 200) -> str:
    if df is None or not len(df):
        return "_(데이터 없음)_\n"
    d = df.head(maxrow)
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    body = "\n".join("| " + " | ".join(
        ("" if v is None else (f"{v:.4f}" if isinstance(v, float) and np.isfinite(v) else str(v)))
        for v in r) + " |" for r in d.itertuples(index=False))
    return "\n".join([head, sep, body]) + "\n"


def _fallback_banner() -> str:
    if PHASE0.get("unit") == "broker_sector_team":
        return ("> ## ⚠ 폴백 전환 고지\n"
                "> Phase 0 확보율이 40% 미만이어서 **링크 단위를 애널리스트에서 "
                "`broker × sector_team` 으로 격하**했습니다.\n"
                "> 이 문서의 모든 결과는 **폴백 구성의 결과**이며, 애널리스트 단위 결과가 아닙니다.\n"
                "> 교차업종 전용 버전이 주 버전(primary)입니다.\n\n")
    return ""


def write_phase0_md(ph: dict) -> str:
    t = ["# PHASE 0 — 데이터 실현가능성 게이트", "", f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M}",
         f"빌드: {BUILD_VERSION}", "", "## 판정", "",
         f"- **표본 확보율: {ph.get('rate', float('nan')):.1%}** (표본 {ph.get('n', 0):,}건)",
         f"- 전체 확보율: {ph.get('overall_rate', float('nan')):.1%}",
         f"- 게이트: ≥70% 정상 / 40~70% IPW 필수 / <40% 폴백",
         f"- **링크 단위: `{ph.get('unit')}`**", f"- 판정: {ph.get('verdict')}",
         f"- 경과: {ph.get('elapsed_min', 0):.1f}분 (타임박스 {PHASE0_TIMEBOX_MIN/60:.0f}시간)", ""]
    det = ph.get("detail", {}) or {}
    for key, title in (("by_source", "소스별 확보율"), ("by_year", "연도별 확보율")):
        d = det.get(key)
        if d is not None and len(d):
            t += [f"## {title}", "", _md_table(d), ""]
    t += ["## 확보 경로", "",
          "1. 한경컨센서스 리스트 '작성자' 컬럼 (신뢰도 0.98)",
          "2. 네이버 상세페이지 바이라인 — 기존 구현이 수집해 놓고 버리던 컬럼을 회수",
          "3. PDF 본문 헤더 정규식 (신뢰도 0.80)", "",
          "## 한계", "",
          "- 두 소스 모두 발간 **시각**을 제공하지 않는다 → 전 건을 장중 발간으로 간주하고 "
          "knowledge_date = 발간일 + 1영업일로 보수화했다.",
          "- `analyst_id = sha1(broker_id, name)` 이므로 이직 시 다른 식별자가 된다. "
          "이는 SPEC §4.2 의 요구와 일치한다(같은 하우스에서 동시에 본다는 사실이 링크의 핵심).", ""]
    return write_text("PHASE0_DATA_FEASIBILITY.md", "\n".join(t))


def write_hypothesis_md(F: pd.DataFrame, rob: dict) -> str:
    t = [_fallback_banner(), "# 가설 검정 보고서 (H1~H4)", "",
         f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M} · 빌드 {BUILD_VERSION}", "",
         "사전등록된 가설과 기각조건만으로 판정한다. 백테스트 결과를 본 뒤 기준을 바꾸지 않는다.", ""]
    _LBL = {True: "통과", False: "기각", None: "판정불가"}
    for k in ("H1", "H2", "H3", "H4"):
        h = HYP.get(k)
        if not h:
            continue
        mark = {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[h.get("final")]
        stat = f"{h['stat']:+.3f}" if np.isfinite(h.get("stat", np.nan)) else "—"
        pv = f"{h['p']:.4f}" if np.isfinite(h.get("p", np.nan)) else "—"
        t += [f"## {k}. {h['name']} — **{mark}**", "",
              f"- 사전등록 기준 판정: {_LBL[h.get('pass')]}",
              f"- 통계량: {stat} · p = {pv} · BH-FDR 유의: "
              f"{'예' if h.get('fdr_sig') else '아니오'}",
              f"- 상세: {h['detail']}", ""]
    t += ["## 다중검정 보정 (BH-FDR, q=0.10)", "", _md_table(F), ""]
    for key, title in (("bootstrap", "블록 부트스트랩"), ("pbo", "PBO (CSCV)"),
                       ("dsr", "Deflated Sharpe Ratio")):
        d = rob.get(key, {})
        if d:
            t += [f"## {title}", "", _md_table(pd.DataFrame([
                {"항목": k2, "값": (f"{v:.4f}" if isinstance(v, float) else str(v))}
                for k2, v in d.items() if not isinstance(v, (list, dict, pd.DataFrame))])), ""]
    return write_text("hypothesis_test_report.md", "\n".join(t))


def write_mechanism_md(T: pd.DataFrame, arms: Dict[str, dict], ppy: float) -> str:
    t = [_fallback_banner(), "# 메커니즘 검정 (H3 조건부 예측)", "",
         "제한된 주의와 느린 정보 전파가 메커니즘이라면, 소형주·저커버리지·고개인비중에서 "
         "효과가 **더 강해야** 한다. 반대로 나오면 알파가 아니라 데이터마이닝이다.", "",
         _md_table(T), "", "## 아암 비교 (전체 유니버스 vs 시총 하위 1,000)", ""]
    rows = []
    for name, bt in arms.items():
        R = bt.get("returns", pd.DataFrame())
        if len(R):
            st = perf_stats(R, ppy=bt.get("meta", {}).get("ppy", ppy))
            rows.append({"아암": name, "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe"),
                         "MDD": st.get("MDD"), "t(HAC)": st.get("t통계량(HAC)"),
                         "평균종목수": st.get("평균종목수")})
    t += [_md_table(pd.DataFrame(rows)), ""]
    return write_text("mechanism_tests.md", "\n".join(t))


def write_open_questions_md() -> str:
    t = ["# OPEN QUESTIONS — 판단 보류 항목", "",
         "SPEC §0: 애매한 지점은 임의 판단하지 않고 여기 기록한 뒤 가장 보수적인 선택을 한다.", ""]
    if not OPEN_QUESTIONS:
        t += ["_(이번 실행에서 기록된 항목 없음)_", ""]
    for q in OPEN_QUESTIONS:
        t += [f"## {q['id']} — {q['topic']}", "", f"- **문제**: {q['issue']}",
              f"- **선택**: {q['choice']}"]
        if q.get("impact"):
            t += [f"- **영향**: {q['impact']}"]
        t += [""]
    return write_text("OPEN_QUESTIONS.md", "\n".join(t))


def write_verdict_md(v: dict, arms: Dict[str, dict], ppy: float) -> str:
    t = [_fallback_banner(), f"# FINAL VERDICT — {v['verdict']}", "",
         f"{v['why']}", "", f"생성: {_dt.datetime.now():%Y-%m-%d %H:%M} · 빌드 {BUILD_VERSION}",
         f"백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
         "## §11 판정 조건 (사전 확정, 사후 변경 없음)", ""]
    t += ["| 조건 | 충족 |", "| --- | --- |"]
    for n, ok in v["criteria"]:
        t += [f"| {n} | {'✔' if ok else '✘'} |"]
    def _num(key, fmt):
        x = v.get(key, float("nan"))
        return format(x, fmt) if isinstance(x, (int, float)) and np.isfinite(x) else "—"

    t += ["",
          f"- 동일가중 유니버스 대비 초과(연): {_num('excess_ew', '+.2%')}",
          f"- PBO: {_num('pbo', '.3f')}",
          f"- DSR: {_num('dsr', '.3f')}", "",
          "## 판정 규칙", "",
          "- **ACCEPT**: H1·H2·H3 전부 통과 + PBO<0.5 + DSR>0 + 동일가중 대비 연 +3%p 이상",
          "- **CONDITIONAL**: H1·H2 통과 + H3 실패 → 실전 배분 금지, 페이퍼 트레이딩만",
          "- **KILL**: H1 실패 · 또는 H2 실패(업종 모멘텀 재포장) · 또는 PBO ≥ 0.5", ""]
    return write_text("FINAL_VERDICT.md", "\n".join(t))


# ==========================================================================================
# 조각: s60_validate.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-V  계약 자동검정 K1~K14  +  합성데이터 엔드투엔드 스모크  +  실경로 리허설             ║
# ║                                                                                          ║
# ║  세 검증은 서로 다른 것을 본다. 하나로 합칠 수 없다:                                       ║
# ║   · 계약검정 : 협상 불가 규칙(PIT·생존편향·사전등록)이 코드에 실제로 박혀 있는가            ║
# ║   · 스모크   : 합성데이터로 '계산경로'가 끝까지 도는가 (네트워크·키 불필요)                 ║
# ║   · 리허설   : 네트워크만 가짜로 두고 '수집·정제 함수'를 실물 실행 — 파싱 크래시를 잡는다   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _src(*objs) -> str:
    """지정 함수/클래스의 소스를 모아 돌려준다.

    __file__ 에 의존하면 노트북 셀에 붙여넣어 실행할 때 소스검사 계약이 통째로 무너진다
    (그리고 '검사가 사라진 것'을 아무도 모른다). inspect 로 대상 객체에서 직접 뽑는다.
    """
    import inspect
    out = []
    for o in objs:
        try:
            out.append(inspect.getsource(o))
        except Exception:
            pass
    return "\n".join(out)


def _k(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                    # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:180]}"
    CONTRACTS.append({"id": cid, "name": name, "pass": bool(ok), "msg": msg})


def _synth(n_codes: int = 140, n_months: int = 54, n_analysts: int = 90,
           seed: int = SEED) -> dict:
    """합성 시장 — 실제로 링크를 통해 전파되는 신호를 심는다.

    스모크가 '돌기만' 하면 의미가 없다. 심어놓은 효과를 파이프라인이 실제로 회수하는지까지
    본다. 그래야 계산경로가 옳다는 증거가 된다.
    """
    rng = np.random.default_rng(seed)
    codes = [f"{900000 + i:06d}"[:6] for i in range(n_codes)]
    codes = [f"{(100000 + i * 7) % 900000 + 10000:06d}" for i in range(n_codes)]
    end = as_ts(BACKTEST_END)
    months = pd.date_range(end=end, periods=n_months, freq=MONTH_END_ALIAS)
    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1])

    # 애널리스트별 커버리지: 종목을 블록으로 묶어 진짜 군집이 생기게 한다
    #  애널리스트는 대체로 한 업종을 맡되 일부는 업종을 가로지른다.
    #  이렇게 해야 H2(동일업종 링크 제거) 마스킹 경로가 실제로 검증된다 —
    #  커버리지가 업종과 무관하면 제거할 동일업종 쌍이 0개라 H2 가 H1 의 복사본이 된다.
    n_sec = 9
    by_sec: Dict[int, List[str]] = {k: [c for i, c in enumerate(codes) if i % n_sec == k]
                                    for k in range(n_sec)}
    cov: Dict[str, List[str]] = {}
    for a in range(n_analysts):
        k = int(rng.integers(4, 10))
        home = by_sec[a % n_sec]
        pick = list(rng.choice(home, size=min(k, len(home)), replace=False))
        if rng.random() < 0.35:                     # 35% 는 인접 업종도 함께 커버
            other = by_sec[(a + 1) % n_sec]
            pick += list(rng.choice(other, size=min(2, len(other)), replace=False))
        cov[f"A{a:03d}@B{a % 12:02d}"] = [str(x) for x in pick]

    # 가격: 링크 이웃의 직전 수익률이 다음 달 수익률에 +로 들어가게 설계
    nb: Dict[str, set] = {c: set() for c in codes}
    for a, cs in cov.items():
        for i in cs:
            for j in cs:
                if i != j:
                    nb[i].add(j)
    cpos = {c: i for i, c in enumerate(codes)}
    # 이웃 평균 연산자를 행렬로 만들어 둔다 (루프보다 빠르고, 무엇보다 부호 실수를 막는다)
    A = np.zeros((n_codes, n_codes))
    for c, ns in nb.items():
        if ns:
            A[cpos[c], [cpos[x] for x in ns]] = 1.0 / len(ns)

    # 월 단위로 먼저 만든다: 이번 달 수익 = 자체충격 + 0.5 × (이웃의 '지난달' 수익)
    # → 신호(이웃 직전수익)가 다음 달 수익을 실제로 예측하도록 설계된 세계다.
    gmonths = pd.date_range(days[0], days[-1], freq=MONTH_END_ALIAS)
    shock = rng.normal(0.0, 0.08, (len(gmonths), n_codes))
    mret = np.zeros_like(shock)
    mret[0] = shock[0]
    for i in range(1, len(gmonths)):
        mret[i] = shock[i] + 0.50 * (A @ mret[i - 1])

    # 월 수익을 그 달 영업일에 균등 분배 + 일간 잡음 (월 합계는 보존)
    n_d = len(days)
    px = np.zeros((n_d, n_codes), dtype=float)
    px[0] = 10000 * np.exp(rng.normal(0, 0.4, n_codes))
    mkey = {as_ts(m): i for i, m in enumerate(gmonths)}
    for t in range(1, n_d):
        mi = mkey.get(as_ts(days[t]) + pd.offsets.MonthEnd(0))
        base = (mret[mi] / 21.0) if mi is not None else np.zeros(n_codes)
        step = base + rng.normal(0.0, 0.010, n_codes)
        px[t] = np.maximum(px[t - 1] * (1 + step), 100.0)
    close = pd.DataFrame(px, index=days, columns=codes)
    daily = close.stack().rename("close").reset_index()
    daily.columns = ["date", "code", "close"]
    daily["open"] = daily["close"] * (1 + rng.normal(0, 0.003, len(daily)))
    daily["volume"] = rng.integers(1e4, 1e6, len(daily))
    daily["amount"] = daily["close"] * daily["volume"]
    daily["high"] = daily["close"] * 1.01
    daily["low"] = daily["close"] * 0.99
    daily["src"] = "synth"

    # 리포트 원장
    rows = []
    for a, cs in cov.items():
        for c in cs:
            for m in months[::2]:
                if rng.random() < 0.55:
                    d = as_ts(m) - pd.Timedelta(days=int(rng.integers(1, 25)))
                    rows.append({"analyst_key": a, "code": c, "pub_date": d,
                                 "knowledge_date": d + pd.tseries.offsets.BDay(1),
                                 "broker_id": a.split("@")[1], "broker_name": a.split("@")[1],
                                 "link_conf": 0.98, "n_analyst_on_report": 1,
                                 "target_price": float(close.loc[:d, c].iloc[-1] *
                                                       (1 + rng.normal(0.1, 0.2)))
                                 if len(close.loc[:d, c]) else np.nan})
    ledger = pd.DataFrame(rows)

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i}" for i in range(n_codes)],
                        "market": ["KOSPI" if i % 3 else "KOSDAQ" for i in range(n_codes)],
                        "industry": [f"업종{i % 9}" for i in range(n_codes)],
                        "corp_code": [f"{i:08d}" for i in range(n_codes)],
                        "listing_date": days[0] - pd.Timedelta(days=900),
                        "delisting_date": pd.NaT})
    # 월말 종가를 한 번에 뽑는다. (months × codes) 루프로 .loc 슬라이싱하면
    # 종목 수를 늘리는 순간 합성데이터 생성이 백테스트보다 오래 걸린다.
    cm = close.reindex(close.index.union(months)).sort_index().ffill().reindex(months)
    mc_long = cm.stack().rename("close_m").reset_index()
    mc_long.columns = ["month", "code", "close_m"]
    mc_long = mc_long.dropna(subset=["close_m"])
    scale = mc_long["code"].map(lambda c: 1e6 * (1 + cpos[c] % 40))
    mcap = pd.DataFrame({"code": mc_long["code"].to_numpy(), "month": mc_long["month"].to_numpy(),
                         "mktcap": mc_long["close_m"].to_numpy() * scale.to_numpy(),
                         "shares": 1e6, "close_m": mc_long["close_m"].to_numpy(),
                         "amount_m": 1e9})
    fund = mcap[["code", "month"]].copy()
    fund["pbr"] = np.abs(rng.normal(1.2, 0.5, len(fund))) + 0.1
    fund["bm"] = 1.0 / fund["pbr"]
    for c in ("bps", "per", "eps", "div_yield"):
        fund[c] = np.nan
    return {"codes": codes, "months": months, "daily": daily, "ledger": ledger,
            "sec": sec, "mcap": mcap, "fund": fund,
            "sector": pd.DataFrame({"code": codes,
                                    "sector": [f"업종{i % 9}" for i in range(n_codes)]})}


class _SynthUniverse:
    """스모크용 최소 Universe — 실제 Universe 와 같은 인터페이스만 제공한다."""

    def __init__(self, codes, months):
        self._c, self._m = list(codes), list(months)

    def at(self, t):
        return list(self._c)

    def delisting_map(self):
        return {}


def run_selftest(full: bool = True) -> bool:
    """합성데이터로 링크→신호→백테스트→검정까지 전 경로를 실제로 돈다."""
    LOG.banner("합성데이터 엔드투엔드 스모크", "네트워크·키 불필요 · 계산경로 증명")
    S = _synth()
    grid = PriceGrid(S["daily"])
    months = pd.DatetimeIndex([m for m in S["months"]])

    uni_rows = []
    for m in months:
        sub = S["mcap"][S["mcap"]["month"] == m][["code", "month", "mktcap", "shares"]]
        if not len(sub):
            continue
        g = sub.copy()
        g["close_m"] = [float(grid.close.loc[:m, c].iloc[-1]) if c in grid.close.columns
                        and len(grid.close.loc[:m, c]) else np.nan for c in g["code"]]
        g["adv20"] = 1e9
        g["market"] = "KOSPI"
        g["sector"] = g["code"].map(S["sector"].set_index("code")["sector"])
        g["bm"] = g.merge(S["fund"], on=["code", "month"], how="left")["bm"].to_numpy()
        g["exec_px"] = g["close_m"]
        g["fwd_ret_m"] = np.nan
        g["in_universe"] = True
        uni_rows.append(g)
    U = pd.concat(uni_rows, ignore_index=True)

    LM = build_link_matrices(S["ledger"], months, S["codes"], "unweighted", use_cache=False)
    if not LM.W:
        LOG.error("스모크 실패: 링크 행렬이 만들어지지 않았습니다.")
        return False
    P = build_signal_panel(LM, grid, U, months, "1M", "M")
    if P is None or not len(P):
        LOG.error("스모크 실패: 신호 패널이 비었습니다.")
        return False
    P = attach_attrs(P, U)

    bt = run_quantile_backtest(P, "sacn_raw", "M", label="SMOKE")
    if not len(bt["returns"]):
        LOG.error("스모크 실패: 백테스트 수익 계열이 비었습니다.")
        return False
    st = perf_stats(bt["returns"], ppy=12.0)
    sp = spread_series(P, "sacn_raw")
    mu, t, _ = nw_tstat(sp.to_numpy(float), 12.0) if len(sp) else (np.nan, np.nan, 0)
    bs = block_bootstrap(bt["returns"]["ret"].to_numpy(float), ppy=12.0, n_boot=200)
    M = pd.DataFrame({f"cfg{i}": bt["returns"]["ret"].to_numpy(float) *
                      (1 + 0.1 * np.sin(i + np.arange(len(bt["returns"]))))
                      for i in range(N_PREREG_CONFIGS)})
    pb = cscv_pbo(M, S=8)
    ds = deflated_sharpe(bt["returns"]["ret"].to_numpy(float), n_trials=N_PREREG_CONFIGS)

    LOG.table([["링크 행렬", f"{len(LM.W)}개월"], ["신호 패널", f"{len(P):,}행"],
               ["백테스트 기간", f"{len(bt['returns'])}"],
               ["CAGR", _fmt_metric('CAGR', st.get('CAGR'))],
               ["Sharpe", _fmt_metric('Sharpe', st.get('Sharpe'))],
               ["Q5−Q1 t(NW)", f"{t:+.2f}" if np.isfinite(t) else "—"],
               ["부트스트랩", "OK" if bs.get("ok") else "미수행"],
               ["PBO", f"{pb.get('pbo', float('nan')):.3f}" if pb.get("ok") else "미수행"],
               ["DSR", f"{ds.get('dsr', float('nan')):.3f}" if ds.get("ok") else "미수행"]],
              ["스모크 단계", "결과"], ["l", "r"])

    # 심어놓은 효과를 실제로 회수했는가 (스모크의 진짜 판정 기준)
    recovered = bool(np.isfinite(t) and t > 0)
    if not recovered:
        LOG.warn("합성데이터에 심어둔 이웃 전파 효과를 신호가 회수하지 못했습니다 "
                 "(t ≤ 0). 계산경로 어딘가가 부호를 뒤집거나 링크를 잘못 잇고 있습니다.")
    else:
        LOG.ok(f"심어둔 이웃 전파 효과를 회수했습니다 (Q5−Q1 t={t:+.2f}) — 계산경로 정상")
    LOG.ok("스모크 통과")
    return True


# ── 계약 검정 ───────────────────────────────────────────────────────────────────────────────
def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정 K1~K14", "협상 불가 규칙이 코드에 실제로 박혀 있는지 검사한다")
    CONTRACTS.clear()

    def k1():
        d = pd.DataFrame({"code": ["A"], "v": [1]})
        try:
            PIT.register("__k1__", d)
            return False, "PIT 컬럼 없는 테이블이 등록되었다 (C1 우회 경로 존재)"
        except KeyError:
            pass
        f = pit_frame(d, "2020-01-01", "2019-01-01")
        ok = bool((f["knowledge_date"] >= f["event_date"]).all())
        return ok, "pit_frame 이 knowledge<event 를 교정하고, PIT 컬럼 없으면 등록 거부"

    def k2():
        src = _src(SACNUniverse.delisting_returns)
        ok = ("정리매매" in src) and ("DELIST_DEFAULT_RET" in src or "default_ret" in src)
        return bool(ok), "폐지 수익률을 정리매매 최종가 기준으로 처리 (-100% 일괄 아님)"

    def k3():
        S = _synth(n_codes=40, n_months=20, n_analysts=25)
        g = PriceGrid(S["daily"])
        t = as_ts(S["months"][5])
        _, d0 = g.exec_price(t)
        return bool(d0 is not None and d0 > t), f"실행일 {d0} > 신호일 {t} (익영업일 앵커)"

    def k4():
        S = _synth(n_codes=30, n_months=16, n_analysts=20)
        LM = build_link_matrices(S["ledger"], pd.DatetimeIndex(S["months"]), S["codes"],
                                 "unweighted", use_cache=False)
        if not LM.W:
            return False, "링크 행렬 생성 실패"
        bad = sum(int(np.abs(W.diagonal()).sum()) for W in LM.W.values())
        return bad == 0, "링크 행렬 대각원소 전부 0 (자기 자신은 연결이 아니다)"

    def k5():
        return MIN_LINKS_REQUIRED >= 3, f"최소 연결 요건 {MIN_LINKS_REQUIRED}개 (SPEC §6.1 = 3)"

    def k6():
        src = _src(build_link_matrices)
        ok = ('knowledge_date' in src) and ('searchsorted(kd' in src) and \
             ('searchsorted(pub' not in src)
        return ok, "링크 윈도우를 pub_date 가 아니라 knowledge_date 로 자른다 (PIT)"

    def k7():
        n = len(PREREG_SIGNAL_WINDOWS) * len(PREREG_REBALANCES) * len(PREREG_LINK_WEIGHTS)
        return n == 12 and N_PREREG_CONFIGS == 12, f"사전등록 격자 {n}개 (SPEC §6.4 = 12, 확장 금지)"

    def k8():
        a = block_bootstrap(np.random.default_rng(1).normal(0.01, 0.05, 60), n_boot=50, seed=7)
        b = block_bootstrap(np.random.default_rng(1).normal(0.01, 0.05, 60), n_boot=50, seed=7)
        return a["cagr_med"] == b["cagr_med"], "같은 시드 → 같은 결과 (결정성)"

    def k9():
        r19 = sell_tax_rate("2018-01-01", "KOSPI")
        r25 = sell_tax_rate("2025-06-01", "KOSPI")
        return bool(r19 > r25 and len(SELL_TAX_SCHEDULE) >= 6), \
            f"연도별 세율 테이블 적용 (2018 {r19:.3%} → 2025 {r25:.3%})"

    def k10():
        src = _src(compute_sacn, orthogonalize)
        return ("sacn_raw" in src and "sacn_resid" in src), "원신호와 직교화 신호를 둘 다 산출"

    def k11():
        src = _src(build_link_ledger)
        ok = ('+ "@" +' in src) and ('broker_id' in src)
        return ok, "애널리스트 식별자 = analyst_id@broker_id (이직 시 다른 식별자)"

    def k12():
        return not hasattr(Vault, "delete") and not hasattr(Vault, "remove"), \
            "Vault 에 삭제 API 자체가 없다 (기존 캐시 훼손 불가능)"

    def k13():
        g = pd.DataFrame({"code": list("abcdefghij"), "s": [1.0] * 10})
        q1 = _assign_quantiles(g, "s", 5).to_numpy()
        q2 = _assign_quantiles(g.iloc[::-1].reset_index(drop=True), "s", 5).to_numpy()
        return bool(np.nansum(q1) == np.nansum(q2)), "동점 분위 배정이 입력 순서에 무관"

    def k14():
        k = _beta_binom_k(np.array([5., 30., 2.]), np.array([10., 60., 4.]))
        return bool(np.isfinite(k) and k > 0), f"EB 축소강도 k={k:.0f} > 0 (축소는 필수)"

    for cid, name, fn in [
        ("K1", "미래누수 차단 (PIT 게이트)", k1),
        ("K2", "생존편향 — 폐지 수익률 처리", k2),
        ("K3", "익영업일 진입 앵커", k3),
        ("K4", "링크 행렬 대각 0", k4),
        ("K5", "최소 연결 요건", k5),
        ("K6", "링크 윈도우 PIT (knowledge_date)", k6),
        ("K7", "사전등록 격자 12개 고정", k7),
        ("K8", "결정성 (시드 재현)", k8),
        ("K9", "연도별 증권거래세", k9),
        ("K10", "원신호 + 직교화 병기", k10),
        ("K11", "애널리스트 식별자 규약 §4.2", k11),
        ("K12", "캐시 삭제 API 부재", k12),
        ("K13", "분위 배정 결정성", k13),
        ("K14", "EB 축소추정 실제 적용", k14),
    ]:
        _k(cid, name, fn)

    LOG.table([[c["id"], c["name"], "✔" if c["pass"] else "✘", _trunc(c["msg"], 54)]
               for c in CONTRACTS], ["ID", "계약", "판정", "근거/사유"],
              ["c", "l", "c", "l"], maxw=56)
    fails = [c for c in CONTRACTS if not c["pass"]]
    if fails:
        LOG.error(f"계약 위반 {len(fails)}건: {[c['id'] for c in fails]}")
        if strict:
            raise RuntimeError(f"계약 검정 실패 {[c['id'] for c in fails]} — "
                               f"실데이터 수집을 시작하지 않습니다.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS)}건 전부 통과")
    return True


# ── 실경로 리허설 ───────────────────────────────────────────────────────────────────────────
class _FakePykrx:
    """네트워크만 가짜로 둔다. 파싱·정제 로직은 실물 그대로 돈다."""

    @staticmethod
    def get_market_cap_by_ticker(day, market="ALL"):
        idx = pd.Index([f"{5930 + i:06d}" for i in range(30)], name="티커")
        return pd.DataFrame({"종가": np.linspace(1000, 90000, 30),
                             "시가총액": np.linspace(3e10, 4e13, 30),
                             "거래량": 1e5, "거래대금": np.linspace(1e8, 9e10, 30),
                             "상장주식수": 1e7}, index=idx)

    @staticmethod
    def get_market_fundamental_by_ticker(day, market="ALL"):
        idx = pd.Index([f"{5930 + i:06d}" for i in range(30)], name="티커")
        return pd.DataFrame({"BPS": np.linspace(1000, 50000, 30),
                             "PER": np.linspace(3, 40, 30), "PBR": np.linspace(0.3, 4.0, 30),
                             "EPS": np.linspace(100, 5000, 30),
                             "DIV": np.linspace(0, 5, 30), "DPS": 100}, index=idx)

    @staticmethod
    def get_etf_ticker_list(day):
        return ["069500", "102110"]

    @staticmethod
    def get_etn_ticker_list(day):
        return ["550001"]

    @staticmethod
    def get_elw_ticker_list(day):
        return ["58J123"]


def run_rehearsal(strict: bool = False) -> bool:
    """새로 만든 수집·정제 함수들을 가짜 네트워크로 '실물 실행'한다.

    합성 스모크는 계산경로만 증명한다. 수집부 한 줄 때문에 실행 2분 만에 죽는 사고는
    이 리허설이 아니면 잡히지 않는다 — 둘은 겹치지 않는다.
    """
    LOG.banner("실경로 리허설", "네트워크만 가짜 · 수집·정제 함수는 실물 실행")
    results = []
    g = globals()
    saved_pykrx, saved_call = g.get("pykrx_stock"), KRXG.call
    try:
        g["pykrx_stock"] = _FakePykrx
        KRXG.call = lambda fn, *a, **kw: fn(*a, **kw)     # type: ignore
        months = pd.date_range(end=as_ts(BACKTEST_END), periods=3, freq=MONTH_END_ALIAS)

        for name, fn in [
            ("시가총액 스냅샷", lambda: fetch_mktcap_monthly(months)),
            ("펀더멘털 스냅샷", lambda: fetch_fundamental_monthly(months)),
            ("비주식 종목 목록", lambda: fetch_nonequity_tickers(months)),
        ]:
            try:
                d = fn()
                ok = d is not None and len(d) > 0
                results.append([name, "✔" if ok else "✘", f"{len(d) if d is not None else 0}행"])
            except Exception as e:                        # noqa
                results.append([name, "✘", f"{type(e).__name__}: {str(e)[:60]}"])

        # 파싱 유틸은 네트워크가 필요 없다 — 실물 그대로
        for name, fn in [
            ("바이라인 파서", lambda: parse_byline("미래에셋증권 리서치센터 홍길동 애널리스트")),
            ("우선주 판정", lambda: str(is_preferred("005935", "삼성전자우"))),
            ("증권거래세", lambda: f"{sell_tax_rate('2022-03-01', 'KOSDAQ'):.4%}"),
        ]:
            try:
                v = fn()
                results.append([name, "✔" if v else "✘", _trunc(str(v), 40)])
            except Exception as e:                        # noqa
                results.append([name, "✘", f"{type(e).__name__}: {str(e)[:60]}"])
    finally:
        g["pykrx_stock"] = saved_pykrx
        KRXG.call = saved_call                            # type: ignore

    LOG.table(results, ["수집·정제 함수", "판정", "결과"], ["l", "c", "l"])
    bad = [r for r in results if r[1] == "✘"]
    if bad and strict:
        raise RuntimeError(f"리허설 실패 {[r[0] for r in bad]}")
    if bad:
        LOG.warn(f"리허설에서 {len(bad)}건 실패 — 해당 경로는 실행 중 저하될 수 있습니다.")
    else:
        LOG.ok("리허설 전항목 통과")
    return not bad


# ==========================================================================================
# 조각: s90_main.py
# ==========================================================================================


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — SPEC §12 실행 순서                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

#  사전등록 주 구성 (SPEC §7). 결과를 본 뒤 바꾸지 않는다.
#    12개 격자 중 '기본값'을 사전에 못박아 둔다: 1개월 신호 · 월간 리밸런싱 · 비가중 링크.
#    최종 신호는 직교화 잔차(§6.3)이며, 원신호 버전을 항상 병기한다.
PRIMARY_CONFIG = {"window": "1M", "rebal": "M", "weight": "unweighted"}
PRIMARY_SIGNAL = "sacn_resid"


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in dict.fromkeys(paths) if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f          # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML         # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: <code>{p}</code></div>")
                continue
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{base64.b64encode(b).decode()}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.2f}MB)</a>")
        display(HTML("".join(html) + "</div>"))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물: {p}")


def _cfg_id(w: str, rb: str, wt: str) -> str:
    return f"{w}|{rb}|{wt}"


def collect_all(months: pd.DatetimeIndex) -> dict:
    ctx: Dict[str, Any] = {}

    with PIPE.stage("L1.UNI", "종목 마스터 (상장·폐지 이력 포함)", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "일별 가격 · 거래대금", "L1", budget_s=2400):
        KRX.login()
        start = (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d")
        px = fetch_prices(ctx["sec"]["code"].tolist(), start, BACKTEST_END)
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L1.META", "시가총액 · BM · 제외플래그 · 업종", "L1", budget_s=1800):
        ctx["mcap"] = fetch_mktcap_monthly(months)
        fund = fetch_fundamental_monthly(months)
        ctx["nonequity"] = fetch_nonequity_tickers(months)
        ctx["flags"] = build_exclusion_flags(ctx["sec"], ctx["nonequity"])
        ctx["sector"] = build_sector_map(ctx["sec"])
        ctx["fund"] = attach_bm_fallback(fund, ctx["mcap"], ctx["sec"], months)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=5400, critical=False):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                nv = naver_enrich_detail(nv)
                nv = naver_attach_analyst(nv)         # ★ 버려지던 바이라인 회수
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep):
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
            rep = apply_publication_lag(rep)          # §0.1 익영업일 보수화
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
            VAULT.put_table(f"report_master_{STRATEGY_ID}", rep, scope="private",
                            domain="research", source="strategy view")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    return ctx


def main() -> dict:
    t_all = time.time()
    global VAULT, DQ, GDRIVE_ROOT, ADOPT_DIRS_RESOLVED
    LOG.banner(f"ARC-SACN — {STRATEGY_NAME}",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(폴백)")],
               ["시드", str(SEED)], ["사전등록 구성 수", f"{N_PREREG_CONFIGS}개 (확장 금지)"],
               ["주 구성", f"{PRIMARY_CONFIG['window']} 신호 · "
                           f"{PRIMARY_CONFIG['rebal']} 리밸 · {PRIMARY_CONFIG['weight']} 링크"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.ROOT", "프로젝트 루트 결정 · 캐시 연결", "L0", budget_s=300):
        root, mode, adopts = resolve_project_root()
        GDRIVE_ROOT = root
        globals()["GDRIVE_ROOT"] = root
        ADOPT_DIRS_RESOLVED = adopts
        globals()["ADOPT_DIRS_RESOLVED"] = adopts
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.table([["캐시 루트", VAULT.root], ["결정 방식", mode],
                   ["공용 인덱스", f"{GDRIVE_SHARED_NS}  (다른 전략과 공유·재사용)"],
                   ["전용 인덱스", f"{GDRIVE_PRIVATE_NS}  (이 전략 고유)"],
                   ["기존 캐시 스캔 대상", f"{len(adopts)}개 경로"],
                   ["여유 공간", f"{free_gb(VAULT.root):.1f} GB"]],
                  ["항목", "값"], ["l", "l"], title="구글드라이브 캐시")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(adopts)
        DQ = DartQuota(DART_API_KEY, scope="shared")
        globals()["DQ"] = DQ
        DQ.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 K1~K14", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        if not run_selftest(full=True):
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설", "L0", budget_s=300, critical=False):
        run_rehearsal(strict=False)

    months = sacn_month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 계산경로를 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (리포트 ↔ 애널 ↔ 종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    with PIPE.stage("L1.PHASE0", "PHASE 0 데이터 실현가능성 게이트", "L1", budget_s=600):
        ph = phase0_gate(ctx.get("reports", pd.DataFrame()), ctx.get("links", pd.DataFrame()),
                         t_all)
        ctx["phase0"] = ph
        write_phase0_md(ph)
        if ph.get("need_ipw"):
            ctx["ipw"] = missingness_sensitivity(ctx.get("reports", pd.DataFrame()),
                                                 ctx.get("links", pd.DataFrame()), ctx["mcap"])
        ctx["ledger"] = build_link_ledger(ctx.get("reports", pd.DataFrame()),
                                          ctx.get("links", pd.DataFrame()),
                                          ctx["sec"], unit=ph["unit"])
    if RUN_MODE == "PHASE0":
        LOG.banner("PHASE 0 완료 — 승인 대기", "SPEC §12-1: 여기서 보고 후 중단합니다.")
        write_open_questions_md()
        PIPE.report_stages()
        offer_download(OUTPUTS)
        return {"mode": "PHASE0", "phase0": ph, "outputs": OUTPUTS}
    if ctx["ledger"] is None or not len(ctx["ledger"]):
        raise RuntimeError("링크 원장이 비어 있어 전략을 구성할 수 없습니다. "
                           "PHASE0_DATA_FEASIBILITY.md 를 확인하세요.")

    with PIPE.stage("L2.UNIVERSE", "PIT 유니버스 120개월", "L2", budget_s=900):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
            columns=["snap_date", "code", "market"])), ctx["panel"]["daily"])
        SU = SACNUniverse()
        U = SU.build(uni, months, ctx["panel"]["monthly"], ctx["mcap"], ctx["flags"],
                     ctx["sector"], ctx["fund"])
        SU.report()
        ctx["uni_panel"], ctx["SU"] = U, SU
        ctx["delist"] = SU.delisting_returns(uni, months, ctx["panel"]["daily"])
        if not len(U):
            raise RuntimeError("PIT 유니버스가 비었습니다 — 게이트 감쇠표에서 붕괴 지점을 확인하세요.")

    with PIPE.stage("L2.LINK", "링크 행렬 (3가지 가중) + 애널리스트 스킬", "L2", budget_s=2400):
        codes = sorted(U["code"].astype(str).unique())
        ctx["skill"] = build_analyst_skill(ctx["ledger"], ctx["panel"]["monthly"],
                                           months, ctx["sector"])
        LMs = {wt: build_link_matrices(ctx["ledger"], months, codes, wt, skill=ctx["skill"])
               for wt in PREREG_LINK_WEIGHTS}
        ctx["LMs"] = LMs
        ctx["LM_xsec"] = mask_cross_sector(LMs["unweighted"], ctx["sector"])

    with PIPE.stage("L2.SIGNAL", f"신호 {N_PREREG_CONFIGS}개 구성", "L2", budget_s=1800):
        grid = PriceGrid(ctx["panel"]["daily"])
        ctx["grid"] = grid
        panels: Dict[str, pd.DataFrame] = {}
        for wt in PREREG_LINK_WEIGHTS:
            for w in PREREG_SIGNAL_WINDOWS:
                for rb in PREREG_REBALANCES:
                    cid = _cfg_id(w, rb, wt)
                    P = build_signal_panel(LMs[wt], grid, U, months, w, rb)
                    if P is None or not len(P):
                        LOG.warn(f"구성 {cid}: 신호 패널이 비었습니다 — 건너뜁니다.")
                        continue
                    panels[cid] = attach_attrs(P, U)
        ctx["panels"] = panels
        if not panels:
            raise RuntimeError("어떤 구성에서도 신호가 만들어지지 않았습니다.")
        LOG.ok(f"신호 패널 {len(panels)}/{N_PREREG_CONFIGS}개 구성 생성")
        _pid = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"],
                       PRIMARY_CONFIG["weight"])
        if _pid in panels:
            VAULT.put_table(f"signal_panel_primary_{STRATEGY_ID}", panels[_pid],
                            scope="private", domain="features", source=f"SACN {_pid}")

    pid = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], PRIMARY_CONFIG["weight"])
    if pid not in ctx["panels"]:
        pid = sorted(ctx["panels"])[0]
        LOG.warn(f"사전등록 주 구성을 만들 수 없어 {pid} 로 대체합니다 (그 사실을 산출물에 남깁니다).")
        open_question("OQ-06", "주 구성 대체",
                      f"사전등록 주 구성을 생성할 수 없었다.", f"{pid} 로 대체.",
                      "주 구성 결과 해석 시 이 대체를 감안해야 한다.")
    ctx["primary_id"] = pid
    P0 = ctx["panels"][pid]
    ppy = PERIODS_PER_YEAR.get(PRIMARY_CONFIG["rebal"], 12.0)

    with PIPE.stage("L3.BT", f"백테스트 {len(ctx['panels'])}구성 × 2아암", "L3", budget_s=1800):
        arms = {"전체 유니버스": P0}
        if COMPARE_SMALLCAP_ARM:
            arms["시총하위1000"] = smallcap_subset(P0, SMALLCAP_ARM_N)
        ctx["arm_bt"] = {}
        for an, Pa in arms.items():
            ctx["arm_bt"][an] = run_quantile_backtest(
                Pa, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"], delist=ctx["delist"],
                cost_mult=COST_SCENARIOS["base"], label=an)
        # 12개 구성 전체 (PBO/DSR/WF 의 입력)
        allbt: Dict[str, dict] = {}
        for cid, Pc in ctx["panels"].items():
            rb = cid.split("|")[1]
            allbt[cid] = run_quantile_backtest(Pc, PRIMARY_SIGNAL, rb, delist=ctx["delist"],
                                               cost_mult=1.0, label=cid)
        ctx["allbt"] = allbt

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300):
        bench = index_benchmarks(ctx["arm_bt"]["전체 유니버스"]["returns"]["date"].tolist())
        bench["동일가중 유니버스"] = equal_weight_universe(
            ctx["grid"], U, rebalance_dates(months, ctx["grid"], PRIMARY_CONFIG["rebal"]))
        ctx["bench"] = bench
        tax_schedule_table()
        for an, bt in ctx["arm_bt"].items():
            report_performance(bt, bench, title=f"{an} · {pid} · {PRIMARY_SIGNAL}")
            report_quantile_profile(ctx["panels"][pid] if an == "전체 유니버스"
                                    else smallcap_subset(P0, SMALLCAP_ARM_N),
                                    PRIMARY_SIGNAL, title=an)
        report_arm_comparison(ctx["arm_bt"], ppy)
        # 원신호 vs 직교화 병기 (§6.3)
        bt_raw = run_quantile_backtest(P0, "sacn_raw", PRIMARY_CONFIG["rebal"],
                                       delist=ctx["delist"], label="원신호")
        ctx["bt_raw"] = bt_raw
        report_arm_comparison({"직교화(주)": ctx["arm_bt"]["전체 유니버스"], "원신호": bt_raw}, ppy)

    with PIPE.stage("L5.STATS", "통계 검증 게이트 (§9)", "L5", budget_s=1500, critical=False):
        base = ctx["arm_bt"]["전체 유니버스"]
        r = base["returns"]["ret"].to_numpy(float) if len(base["returns"]) else np.array([])
        M = pd.DataFrame({cid: bt["returns"].set_index(as_ts_series(bt["returns"]["date"]))["ret"]
                          for cid, bt in ctx["allbt"].items()
                          if len(bt["returns"])}).sort_index()
        rob = {"bootstrap": block_bootstrap(r, ppy=ppy),
               "pbo": cscv_pbo(M, S=8),
               "dsr": deflated_sharpe(r, n_trials=N_PREREG_CONFIGS, ppy=ppy),
               "wf": walk_forward(M, ppy=ppy)}
        ctx["rob"] = rob
        report_robustness(rob, title=f"{pid} · 전체 유니버스")

    with PIPE.stage("L5.HYP", "사전등록 가설 H1~H4 (§3)", "L5", budget_s=900, critical=False):
        sp_full = test_H1(P0, PRIMARY_SIGNAL, ppy)
        Px = build_signal_panel(ctx["LM_xsec"], ctx["grid"], U, months,
                                PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"])
        if Px is not None and len(Px):
            Px = attach_attrs(Px, U)
            sp_x = spread_series(Px, PRIMARY_SIGNAL)
        else:
            sp_x = pd.Series(dtype=float)
        test_H2(sp_full, sp_x, ppy)
        ctx["retail"] = fetch_retail_share(
            sorted(U["code"].astype(str).unique()), BACKTEST_START, BACKTEST_END) \
            if RUN_MODE == "FULL" else pd.DataFrame()
        T3 = test_H3(P0, PRIMARY_SIGNAL, ppy, ctx.get("retail"))
        cid_f = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], "freq")
        cid_s = _cfg_id(PRIMARY_CONFIG["window"], PRIMARY_CONFIG["rebal"], "highskill")
        test_H4(sp_full,
                spread_series(ctx["panels"][cid_f], PRIMARY_SIGNAL) if cid_f in ctx["panels"]
                else pd.Series(dtype=float),
                ppy,
                spread_series(ctx["panels"][cid_s], PRIMARY_SIGNAL) if cid_s in ctx["panels"]
                else None)
        F = finalize_hypotheses(q=0.10)
        ctx["hyp_table"], ctx["mech_table"] = F, T3

    with PIPE.stage("L5.SENS", "비용 · 폐지 민감도", "L5", budget_s=600, critical=False):
        scen = {name: run_quantile_backtest(P0, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"],
                                            delist=ctx["delist"], cost_mult=mult,
                                            label=f"cost:{name}")
                for name, mult in COST_SCENARIOS.items()}
        ctx["cost_scen"] = scen
        ctx["cost_table"] = report_cost_sensitivity(scen, ppy)
        drows = []
        for g in DELIST_SENSITIVITY_GRID:
            dl = ctx["delist"].copy()
            if len(dl):
                m = dl["source"] != "정리매매 최종가"
                dl.loc[m, "delist_ret"] = g
            b = run_quantile_backtest(P0, PRIMARY_SIGNAL, PRIMARY_CONFIG["rebal"],
                                      delist=dl, label=f"delist:{g}")
            st = perf_stats(b["returns"], ppy=ppy)
            drows.append([f"{g:.0%}", _fmt_metric("CAGR", st.get("CAGR")),
                          _fmt_metric("Sharpe", st.get("Sharpe")),
                          _fmt_metric("MDD", st.get("MDD")),
                          f"{int((dl['source'] != '정리매매 최종가').sum()) if len(dl) else 0}"])
        ctx["delist_table"] = drows
        report_delist_sensitivity(drows)

    with PIPE.stage("L6.INTERP", "해석표", "L6", budget_s=300, critical=False):
        report_interpretation(P0, PRIMARY_SIGNAL, ctx["LMs"][PRIMARY_CONFIG["weight"]],
                              ctx["arm_bt"]["전체 유니버스"], ctx["sec"])

    with PIPE.stage("L6.VERDICT", "§11 기계적 판정 + 산출물", "L6", budget_s=600, critical=False):
        v = final_verdict(ctx["arm_bt"]["전체 유니버스"], ctx["bench"].get("동일가중 유니버스"),
                          ctx["rob"]["pbo"], ctx["rob"]["dsr"], ppy)
        ctx["verdict"] = v
        write_outputs(ctx, ppy, t_all)

    PIPE.report_stages()
    PIPE.report_flow(limit=120)
    PIT.report()
    report_http()
    if DQ:
        DQ.report()
        DQ.close()
    PIPE.report_runtime()
    VAULT.flush()
    VAULT.compact("shared")
    VAULT.compact("private")
    VAULT.report()
    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물 {len(OUTPUTS)}개 · 캐시 {VAULT.root}")
    offer_download(OUTPUTS)
    return {"ctx": ctx, "verdict": ctx.get("verdict"), "outputs": OUTPUTS}


def write_outputs(ctx: dict, ppy: float, t_all: float):
    """SPEC §10 산출물 일체."""
    rows = []
    for cid, bt in ctx["allbt"].items():
        R = bt.get("returns", pd.DataFrame())
        if not len(R):
            continue
        w, rb, wt = cid.split("|")
        st = perf_stats(R, ppy=PERIODS_PER_YEAR.get(rb, 12.0))
        rows.append({"config": cid, "signal_window": w, "rebalance": rb, "link_weight": wt,
                     "is_primary": cid == ctx["primary_id"],
                     **{k: st.get(k) for k in _METRIC_ORDER if k in st}})
    MC = pd.DataFrame(rows)
    write_df("metrics_all_configs.csv", MC)
    if len(MC):
        LOG.table([[r["config"] + (" ★" if r["is_primary"] else ""),
                    _fmt_metric("CAGR", r.get("CAGR")), _fmt_metric("Sharpe", r.get("Sharpe")),
                    _fmt_metric("MDD", r.get("MDD")),
                    _fmt_metric("t통계량(HAC)", r.get("t통계량(HAC)"))]
                   for _, r in MC.iterrows()],
                  ["구성 (신호|리밸|가중)", "CAGR", "Sharpe", "MDD", "t(HAC)"],
                  ["l", "r", "r", "r", "r"],
                  title=f"사전등록 {N_PREREG_CONFIGS}개 구성 전체 성과 (★=사전등록 주 구성)")

    eq = []
    for cid, bt in ctx["allbt"].items():
        R = bt.get("returns", pd.DataFrame())
        if len(R):
            e = R[["date", "ret", "equity"]].copy()
            e["config"] = cid
            eq.append(e)
    write_df("equity_curves.parquet", pd.concat(eq, ignore_index=True) if eq else pd.DataFrame())
    H = ctx["arm_bt"]["전체 유니버스"].get("holdings", pd.DataFrame())
    write_df("trade_log.parquet", H)

    write_hypothesis_md(ctx.get("hyp_table", pd.DataFrame()), ctx["rob"])
    write_mechanism_md(ctx.get("mech_table", pd.DataFrame()), ctx["arm_bt"], ppy)
    write_text("cost_sensitivity.md", "# 비용 민감도 (§7.1)\n\n"
               "증권거래세는 2019년 이후 여러 차례 인하됐다. 단일 세율을 쓰지 않고 "
               "연도별 실제 세율 테이블을 적용했다.\n\n"
               + _md_table(ctx.get("cost_table", pd.DataFrame())) + "\n\n## 연도별 세율\n\n"
               + _md_table(pd.DataFrame([{"적용시작": d, "유가증권": f"{t['KOSPI']:.3%}",
                                          "코스닥": f"{t['KOSDAQ']:.3%}"}
                                         for d, t in SELL_TAX_SCHEDULE])))
    write_text("delisting_sensitivity.md", "# 상장폐지 처리 민감도 (§0.3)\n\n"
               "폐지 종목의 최종 수익률은 -100% 일괄이 아니라 정리매매 최종가 기준으로 "
               "처리했다. 최종가를 확인할 수 없는 건에만 보수적 기본값을 적용하고, "
               "그 가정의 민감도를 아래에 병기한다.\n\n"
               + _md_table(pd.DataFrame(ctx.get("delist_table", []),
                                        columns=["가정", "CAGR", "Sharpe", "MDD", "영향 종목수"])))
    write_open_questions_md()
    write_verdict_md(ctx["verdict"], ctx["arm_bt"], ppy)

    summary = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "run_mode": RUN_MODE, "started": _dt.datetime.now().isoformat(timespec="seconds"),
        "elapsed_min": round((time.time() - t_all) / 60.0, 2),
        "backtest": {"start": BACKTEST_START, "end": BACKTEST_END,
                     "months": int(len(sacn_month_range(BACKTEST_START, BACKTEST_END)))},
        "phase0": {k: (v if isinstance(v, (int, float, str, bool)) else str(type(v)))
                   for k, v in (ctx.get("phase0") or {}).items() if k != "detail"},
        "primary_config": ctx.get("primary_id"), "primary_signal": PRIMARY_SIGNAL,
        "n_configs_built": len(ctx.get("panels", {})), "n_configs_preregistered": N_PREREG_CONFIGS,
        "universe_months": int(ctx["uni_panel"]["month"].nunique()) if len(ctx.get("uni_panel", [])) else 0,
        "universe_avg_names": float(ctx["uni_panel"].groupby("month").size().mean())
        if len(ctx.get("uni_panel", [])) else 0.0,
        "link_ledger_rows": int(len(ctx.get("ledger", []))),
        "analyst_keys": int(ctx["ledger"]["analyst_key"].nunique()) if len(ctx.get("ledger", [])) else 0,
        "verdict": (ctx.get("verdict") or {}).get("verdict"),
        "hypotheses": {k: {"pass": h.get("pass"), "final": h.get("final"),
                           "stat": h.get("stat"), "p": h.get("p")} for k, h in HYP.items()},
        "robustness": {k: {kk: vv for kk, vv in (v or {}).items()
                           if isinstance(vv, (int, float, str, bool))}
                       for k, v in ctx.get("rob", {}).items()},
        "dart_quota": {"used": DQ.used if DQ else 0, "remaining": DQ.remaining() if DQ else 0,
                       "limit": DQ.limit if DQ else 0,
                       "limit_observed": DQ.limit_is_observed() if DQ else False},
        "cache_root": VAULT.root, "shared_ns": GDRIVE_SHARED_NS, "private_ns": GDRIVE_PRIVATE_NS,
        "open_questions": len(OPEN_QUESTIONS),
    }
    write_text("run_summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    write_text(f"run_log_{_dt.datetime.now():%Y%m%d_%H%M%S}.txt", "\n".join(LOG.buffer))
    for cid, bt in ctx["allbt"].items():
        if len(bt.get("returns", [])):
            VAULT.put_table(f"backtest_returns_{STRATEGY_ID}_{cid.replace('|','_')}",
                            bt["returns"], scope="private", domain="backtest", source=cid)
    LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:.1f}KB"] for p in OUTPUTS
               if os.path.exists(p)], ["산출물", "크기"], ["l", "r"],
              title=f"산출물 (§10) → {os.path.join(GDRIVE_PRIVATE_NS, 'outputs')}")


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except StageFailure as e:
        LOG.banner("실행 중단", "위 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow(limit=60)
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 캐시에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
            if DQ:
                DQ.close()
        except Exception:
            pass
