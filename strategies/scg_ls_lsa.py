#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  SCG-LS / SCG-LSA — Smart Consensus Gap + Analyst Leadership/Skill
#  전략: SCG-LS / SCG-LSA — Smart Consensus Gap + Analyst Leadership   [SCG_LS_LSA]
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)
#
#  일반 컨센서스보다 최근성이 높고, 과거에 실적을 잘 맞혔으며, 다른 애널리스트의 후속 수정에 선행해 온 애널리스트에게 더 큰 가중치를 준 자체 Smart Consensus 를 만들고, 그것과 일반 컨센서스의 격차(Smart Gap)를 신호로 쓴다. 하드게이트로 표본을 깎지 않고 정보가 부족한 애널리스트는 중립값으로 수축시킨다. BASE_REV / SCG_0 / SCG_LS / SCG_LSA 네 전략을 동일 유니버스에서 나란히 산출해 각 구성요소의 증분 기여를 분리 검증하는 것이 이 연구의 핵심이다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python scg_ls_lsa.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정 → TEST 1~9 자체검증
#     [1] 합성데이터 엔드투엔드 스모크        (실데이터 수집 전에 계산경로를 먼저 증명)
#     [2] 데이터 수집  (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [3] 원장 무결성 감사  (보고서 ↔ 애널리스트 ↔ 종목 ↔ EPS추정치 연결)
#     [4] PIT 유니버스(생존자편향 제거) + 유니버스 감쇠 감사
#     [5] analyst_forecasts → Accuracy/Leadership 이벤트 → PIT 애널리스트 점수
#     [6] Smart Consensus → SCG_0 / SCG_LS / SCG_LSA / BASE_REV
#     [7] 성과 검증  (전략 4종 나란히 · 십분위 단조성 · 20/60/120일 IC)
#     [8] 강건성 검사  (민감도 · 하위기간 · 레짐 · 종목집중도 · 플라시보 …)
#     [9] 해석표 + 진단 카드 + 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 한글로 로그에 명시합니다. (조용히 실패하지 않습니다)
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  (실적 실측치 = Accuracy 계산의 필수 입력) ──────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료 · 발급 즉시 사용 · 일 20,000건 호출 제한.
#
#    ▶ 이 전략에서 DART 가 하는 일은 딱 셋입니다:
#        (1) 실제 EPS  → Accuracy Event 의 A (실적 실측치)
#        (2) 주식총수  → PIT 시가총액 (하위1000 비교 유니버스 선정용)
#        (3) 접수일자  → 실적 "발표일"(actual_announcement_date). PIT 의 근거.
#    ▶ 키가 없으면 Accuracy 는 전부 0 으로 수축되고(애널리스트는 탈락시키지 않음),
#      SCG_0 는 사실상 Recency 가중 컨센서스 갭이 됩니다. 그 사실을 로그에 명시합니다.
#
#    ★ 호출량 정책 (v1 에서 고정 19,000 하드코딩 → 제거되었습니다):
#      · 사전에 상한을 정하지 않습니다. 남은 호출량을 실시간으로 추적하고,
#        한도의 판정 권한은 오직 DART 응답 status="020"(요청제한 초과) 에 있습니다.
#      · 하루 경계는 **KST 자정** 기준입니다. Colab VM 은 보통 UTC 라서 이걸 안 맞추면
#        9시간 어긋나 "아직 남았는데 멈추거나 / 없는데 계속 때리는" 사고가 납니다.
#      · 애초에 호출을 적게 씁니다: 회사별 단건 호출 대신 다중회사 배치(100사/호출)와
#        날짜 스윕을 씁니다. 산술은 실행 로그의 [DART 호출 예산] 표에 그대로 출력됩니다.
DART_API_KEY = ""

#    (선택) 한도를 일부러 낮추고 싶을 때만 숫자를 넣으세요. None = 자동(권장).
#    None 이면 DART 가 020 을 줄 때까지 쓰고, 그 시점에 깨끗하게 체크포인트 후 멈춥니다.
DART_DAILY_LIMIT: "int | None" = None
#    같은 키를 다른 노트북에서도 쓰고 있다면 그만큼 남겨두세요 (0 = 남기지 않음).
DART_RESERVE_CALLS = 0

# ── ② KRX  — 이 전략에서는 **사용하지 않습니다** ────────────────────────────────────────────
#    data.krx.go.kr / pykrx / KRX 마켓플레이스 로그인 전부 호출하지 않습니다.
#    (계정 차단 이력이 있어 완전히 배제했습니다. 아래 스위치는 '실수로도 켜지지 않도록'
#     남겨둔 안전장치이며, True 로 바꿔도 코드 경로 자체가 없습니다.)
#
#    ▶ 그럼 유니버스는 어떻게 PIT 이 되는가?
#        상장일·폐지일을 FDR 상장/폐지 목록에서 재구성하고, 가격 시계열의 '실제 거래
#        종료일'로 교차검증합니다. 월말 시점 t 의 유니버스 =
#            listing_date <= t  AND  (delisting_date is NaT OR delisting_date > t)
#        폐지 종목을 포함하므로 생존자편향이 구조적으로 제거됩니다.
#        거래일 캘린더도 KRX 없이 '실제 거래가 관측된 날'의 합집합으로 만듭니다.
KRX_ENABLED = False

#    ★ 구조적 차단: pykrx 는 **import 하는 것만으로** data.krx.co.kr 에 로그인한다
#      (webio.py 가 모듈 본문에서 세션을 만들고, KRX_ID/KRX_PW 가 있으면 로그인까지 한다).
#      그래서 '부르지 않는다'로는 부족하고, 설치·import 자체를 막는다.
BANNED_PACKAGES = ["pykrx"]

# ── ③ 구글드라이브 캐시 ─────────────────────────────────────────────────────────────────────
#    ★★★ 절대 1원칙: 기존 캐시를 절대 삭제·훼손하지 않습니다. ★★★
#      · 인덱스의 원천은 append-only JSONL 저널입니다. 기존 줄을 다시 쓰지 않습니다.
#      · index.parquet 은 저널의 파생물이며, 재생성 전 항상 타임스탬프 백업을 남깁니다.
#      · 이미 드라이브에 있는 리포트/원본은 이동·개명 없이 "경로만 등록"합니다(adopt).
#      · 삭제 API 자체가 존재하지 않습니다. 손상 파일도 지우지 않고 격리만 합니다.
#
#    GDRIVE_ROOT       : 캐시 최상위. ★ 기존 전략(TCD v2)과 같은 값을 쓰면 그 캐시를
#                        그대로 재활용합니다. 리포트·PDF·재무를 다시 받지 않습니다.
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략도 재사용 가능한 원본/범용 정제본
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유의 점수/가중치/백테스트 산출물
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"          # → {GDRIVE_ROOT}/_shared     (공용)
GDRIVE_PRIVATE_NS = "scg_ls"           # → {GDRIVE_ROOT}/scg_ls      (전용)

#    ▸ 리포트를 다른 폴더에도 모아두셨다면 여기에 추가하세요. 재귀 스캔해 "등록만" 합니다.
#      (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록합니다)
#      ▸ Colab 이 아니면 이 경로들은 존재하지 않는 게 정상입니다(경고가 아닙니다).
#        로컬(Windows/Mac/Linux)에서는 LOCAL_CACHE_ROOT 아래를 자동으로 함께 스캔합니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # 로컬 예시:  r"D:\Qunat\reports",   r"D:\Qunat\consensus",
]

#    ▸ 예전 버전이 다른 루트에 캐시를 만들어 두었다면 여기에 적으세요. 그 루트의
#      _shared 인덱스를 **읽기 전용으로** 함께 조회합니다(원본은 건드리지 않습니다).
GDRIVE_EXTRA_SHARED_ROOTS: "list[str]" = [
    # "/content/drive/MyDrive/quant_cache",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
LOCAL_CACHE_ROOT  = "./scg_cache"

# ── ④ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

#    애널리스트 점수는 신호 시작 이전 이력으로 워밍업되어야 합니다(그래야 첫 달부터
#    ACC*/LEAD* 가 0 이 아닙니다). 수집은 이만큼 더 과거부터 합니다.
HISTORY_WARMUP_YEARS = 5

# ── ⑤ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 8 이하로.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.5,
    "naver":     3.0,
    "fdr":       4.0,
    "yfinance":  2.0,
    "krx":       0.0,   # 사용하지 않음 (0 = 완전 차단)
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환
PDF_PARSE_WORKERS = 0   # EPS 추출 병렬 프로세스 수. 0 = 자동
PDF_PARSE_CHUNK   = 1500  # PDF 를 한 번에 몇 건씩 메모리에 올릴지 (RAM 평탄화)

# ── ⑥ 애널리스트 리포트 수집 ────────────────────────────────────────────────────────────────
#    한경컨센서스(작성자·목표주가 보유) + 네이버 리서치(종목코드 보유). 둘을 합쳐야 원장이 완성됩니다.
RESEARCH_COLLECT       = True    # False 면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES       = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF  = True    # ★ EPS 추정치는 PDF 본문에만 있습니다. False 면 EPS 트랙이 죽습니다.
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑦ 예측치 메트릭 트랙 ────────────────────────────────────────────────────────────────────
#    명세 §1: forecast_metric 기본값은 EPS. metric 차원은 코드에서 제거하지 않습니다.
#
#    "EPS" : 리포트 PDF 1면의 실적추정표에서 추출한 주당순이익 추정치. 명세 원형.
#            실측치 A = DART 재무제표의 주당이익(없으면 지배주주순이익/주식수).
#    "TP"  : 목표주가. 한경 리스트 컬럼에 직접 있어 커버리지가 압도적으로 넓습니다.
#            실측치 A = 회계연도 종료일의 실제 주가(수정주가 기준).
#            ※ TP 는 명세의 EPS 정의를 그대로 옮긴 **병렬 트랙**이며, EPS 트랙과 절대
#              섞지 않습니다(§45.2 와 같은 이유). 공식 결론은 EPS 트랙으로 냅니다.
#              EPS 커버리지가 무너졌을 때 "표본이 없어서 못 봤다"로 끝나지 않기 위한 대비책입니다.
FORECAST_METRICS       = ["EPS", "TP"]
PRIMARY_METRIC         = "EPS"     # 공식 성과표·강건성표가 쓰는 트랙
#    EPS 트랙의 신호 유효 표본이 이 비율 미만이면 자동으로 TP 트랙을 공식 트랙으로 승격하고,
#    그 사실을 로그 최상단에 경고로 남깁니다 (조용히 바꾸지 않습니다).
PRIMARY_METRIC_MIN_COVERAGE = 0.05

# ── ⑧ 신호 그리드 / 유니버스 ────────────────────────────────────────────────────────────────
SIGNAL_FREQ = "M"        # "M"=월말(권장·120시점) | "W"=주말(521시점, 정밀하지만 느림)
#    비교 유니버스 — 동일 신호·동일 리밸런스로 나란히 돌립니다 (§30: universe 를 임의로 다르게 만들지 않음)
UNIVERSE_VARIANTS = ["ALL", "SMALL1000"]
SMALL_UNIVERSE_N  = 1000   # 시가총액 하위 N 종목

# ── ⑨ 백테스트 / 포트폴리오 ─────────────────────────────────────────────────────────────────
N_BUCKETS            = 10      # 십분위. 표본이 작으면 자동으로 5분위 fallback
MIN_STOCKS_PER_DATE  = 30      # 이보다 적으면 그 시점은 십분위 대신 5분위
BT_HOLD_MONTHS       = 1       # 리밸런스 주기(개월)
BT_COST_BPS          = 30.0    # 편도 거래비용(bp). 한국 소형주 왕복 60bp 가정
BT_LONG_BUCKET       = "top"   # 헤드라인 롱온리 = 최상위 버킷
IC_HORIZONS_TD       = [20, 60, 120]   # forward IC 지평 (거래일)
MIN_ADV_KRW          = 0       # 유동성 하한(원). 0 = 적용 안 함(§31 하드게이트 금지 원칙)
#    ※ MIN_ADV_KRW 를 0 이 아닌 값으로 두면 표본이 줄어듭니다. 기본은 0 이며,
#      용량(capacity) 진단은 하드게이트가 아니라 별도 표로만 출력합니다.

#    (재사용 코어가 참조하는 상수 — SCG 는 십분위 백테스트를 쓰므로 직접 사용하지 않습니다)
PORTFOLIO_TOP_PCT     = 0.10
PORTFOLIO_MAX_NAMES   = 0
PORTFOLIO_MIN_NAMES   = 5
POS_MAX_WEIGHT        = 1.0
POS_MIN_WEIGHT        = 0.0
POS_ADV_PARTICIPATION = 1.0
HOLD_MAX_MONTHS       = 24
ACCOUNT_KRW           = 100_000_000
DATA_GO_KR_KEY = ""      # SCG 미사용 (코어 호환용)
CUSTOMS_API_KEY = ""     # SCG 미사용 (코어 호환용)
KRX_MARKETPLACE_ID = ""  # SCG 미사용 — KRX 를 호출하지 않습니다
KRX_MARKETPLACE_PW = ""
KRX_OPENAPI_KEY    = ""

# ── ⑩ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전체 출력물을 예행연습(수십 초). 네트워크·키 불필요.
#              성과표·십분위·IC·강건성·해석표가 전부 나옵니다. 처음엔 이걸로 한 번.
#    "FULL"  : 스모크 → 실경로 리허설 → 실데이터 수집 → 전체 (권장)
#    "CACHED": 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 전체
RUN_MODE = "FULL"

SEED = 20260808          # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = False   # SCG 는 '킬'이 아니라 '증분 기여 판정' 전략이므로 기본 False

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID        = "SCG_LS_LSA"
STRATEGY_NAME      = "SCG-LS / SCG-LSA — Smart Consensus Gap + Analyst Leadership"
ACTIVE_PACKS       = []
BUILD_VERSION      = "v2.20260808.1118"


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import datetime as _dt
from collections import defaultdict, Counter, OrderedDict
from dataclasses import dataclass, field, asdict, replace
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
    ("pymupdf",           "pymupdf",            "리포트 PDF 텍스트 추출(가장 빠름)"),
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


# ═══ 금지 패키지 차단 — '안 부른다'가 아니라 'import 자체가 불가능하다' ══════════════════════
#   ★ pykrx 는 **import 하는 것만으로** data.krx.co.kr 에 접속한다:
#     pykrx/website/comm/webio.py 는 모듈 본문에서 build_krx_session() 을 실행하고,
#     auth.py 는 os.getenv("KRX_ID")/("KRX_PW") 가 있으면 실제 로그인 POST 까지 보낸다.
#     즉 KRX 를 쓰지 않는 전략이라도 이 import 한 줄이 남아 있으면 금지가 깨진다.
#     (같은 커널에서 다른 전략을 먼저 돌렸다면 KRX_ID/PW 가 os.environ 에 남아 있다)
#   → BANNED_PACKAGES 에 올라온 패키지는 설치도, import 도, 자격증명 주입도 하지 않는다.
#     meta_path 훅으로 제3의 코드가 몰래 import 하는 것까지 막는다.
BANNED_PACKAGES = [str(x).strip() for x in globals().get("BANNED_PACKAGES", []) if str(x).strip()]
if BANNED_PACKAGES:
    _REQUIRED = [t for t in _REQUIRED if t[0] not in BANNED_PACKAGES]
    _OPTIONAL = [t for t in _OPTIONAL if t[0] not in BANNED_PACKAGES]

    class _BannedImportBlocker:
        """금지 패키지의 import 를 예외로 막는다 (sys.meta_path 최우선)."""

        def find_module(self, name, path=None):
            self.find_spec(name, path)
            return None

        def find_spec(self, name, path=None, target=None):
            root = str(name).split(".")[0]
            if root in BANNED_PACKAGES:
                raise ImportError(
                    f"'{root}' 는 이 전략에서 금지된 패키지입니다. "
                    f"(import 만으로 외부 사이트에 접속하기 때문입니다) "
                    f"BANNED_PACKAGES 를 확인하세요.")
            return None

    if not any(isinstance(h, _BannedImportBlocker) for h in sys.meta_path):
        sys.meta_path.insert(0, _BannedImportBlocker())
    if "pykrx" in BANNED_PACKAGES:
        #   이미 남아 있는 자격증명도 지운다 — 있으면 로그인 시도가 일어난다
        for _k in ("KRX_ID", "KRX_PW", "KRX_OPENAPI_KEY", "KRX_API_KEY"):
            os.environ.pop(_k, None)

# ═══ 자격증명은 어떤 서드파티 import 보다도 먼저 주입한다 ═══════════════════════════════════
#   pykrx.webio 는 모듈 로드 시점에 build_krx_session() 을 돌린다. 순서를 뒤집으면
#   예외 없이 '비인증 세션'이 만들어지고 원인 추적이 매우 어려운 실패로 이어진다.
if "pykrx" not in BANNED_PACKAGES:
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
#
# ★ except 절이 Exception 이 아니라 BaseException 인 이유 — 실제로 겪은 사고다.
#   pdfplumber → pdfminer.six → cryptography 는 Rust 확장(pyo3)을 쓰는데, 그 바이너리가
#   런타임의 libffi/_cffi_backend 와 어긋나면 ImportError 가 아니라
#   `pyo3_runtime.PanicException` 을 던진다. 이건 BaseException 의 직계라
#   `except Exception` 을 그대로 통과해 실행 전체를 죽인다.
#   "선택 패키지" 하나가 파이프라인을 죽이는 것은 어떤 경우에도 옳지 않으므로
#   여기서는 BaseException 을 잡는다. (KeyboardInterrupt/SystemExit 은 아래에서 재전파)
def _opt_import(name: str, attr: str = ""):
    try:
        mod = __import__(name, fromlist=[attr] if attr else [])
        return getattr(mod, attr) if attr else mod
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:                     # noqa: BLE001 — 위 주석 참조
        _safe_print(f"  · 선택 패키지 '{name}' 로드 실패({type(e).__name__}) — "
                    f"해당 기능만 비활성화하고 계속합니다.")
        return None


fdr = pykrx_stock = yf = fitz = pdfplumber = rapidfuzz_fuzz = smapi = None
if OPT.get("FinanceDataReader"):
    fdr = _opt_import("FinanceDataReader")
if OPT.get("pykrx"):
    pykrx_stock = _opt_import("pykrx", "stock")
if OPT.get("yfinance"):
    yf = _opt_import("yfinance")
#  ★ pymupdf 1.24+ 의 정식 import 이름은 'pymupdf' 이고 'fitz' 는 제거될 예정인 별칭이다.
#    실제 실행 로그에서 Python 3.14 / Windows 조합이 `import fitz` 로 ImportError 를 냈다.
#    → pymupdf 를 먼저 시도하고, 없으면 구버전용 fitz 로 내려간다.
if OPT.get("pymupdf") or OPT.get("fitz"):
    fitz = _opt_import("pymupdf") or _opt_import("fitz")
    if fitz is None:
        _safe_print("  · PDF 파서를 못 찾았습니다 — EPS 트랙이 비활성화되고 TP 트랙만 씁니다. "
                    "`pip install pymupdf` 로 되살아납니다.")
if OPT.get("pdfplumber"):
    pdfplumber = _opt_import("pdfplumber")
if OPT.get("rapidfuzz"):
    rapidfuzz_fuzz = _opt_import("rapidfuzz", "fuzz")
if OPT.get("statsmodels"):
    smapi = _opt_import("statsmodels.api")

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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  PIT 유니버스 — KRX 를 한 번도 호출하지 않고 생존자편향을 제거한다                    ║
# ║                                                                                          ║
# ║  ★ KRX 금지는 '안 쓰기로 했다'가 아니라 '코드 경로가 없다'로 구현한다.                       ║
# ║    이 파일에는 data.krx.co.kr / kind.krx.co.kr / pykrx 호출이 한 줄도 없다.                 ║
# ║    RATE_LIMIT_QPS["krx"] = 0.0 이라 실수로 부르면 즉시 막힌다.                              ║
# ║                                                                                          ║
# ║  유니버스가 PIT 인 근거 (생존자편향 제거의 3중 방어):                                       ║
# ║    ① 상장일  — FDR GitHub 캐시(listing/krx) + 최초 체결일                                  ║
# ║    ② 폐지일  — FDR GitHub 캐시(listing/delisting). KRX 없이 유일한 공개 경로.               ║
# ║    ③ 관측기반 폐지 추정 — 시장은 계속 거래되는데 이 종목만 시계열이 끊기면 폐지다.           ║
# ║       ②가 놓친 종목을 ③이 줍는다. 두 경로가 겹치는 정도를 매 실행 표로 낸다.                 ║
# ║                                                                                          ║
# ║    시점 t 의 유니버스 = listing_date <= t < delisting_date                                 ║
# ║    → 지금 없어진 회사도 그 시절엔 들어 있다. 그것이 생존자편향 제거의 정의다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_SEC_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                "corp_code", "industry", "src", "delist_src"]

_SCG_FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                  "refs/heads/master/data/{kind}/{date}.csv")

#  보통주가 아닌 종목(우선주·신주인수권 등)은 6번째 자리가 '0' 이 아니다. 시점 불변 규칙이라
#  미래정보가 섞이지 않는다. ETF/ETN/스팩은 이름/구분으로 추가 배제한다.
_SCG_NONEQUITY_NAME = re.compile(
    r"스팩|기업인수목적|제\d+호|리츠|ETN|ETF|상장지수|인프라투融|맥쿼리인프라|"
    r"신주인수권|워런트|WR\b", re.I)


def _scg_lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def _scg_fdr_cache_csv(kind: str, back_days: int = 21) -> Optional[pd.DataFrame]:
    """FinanceDataReader 의 GitHub 캐시를 직접 읽는다 (KRX 인증과 무관).

    ★ FDR 라이브러리 자체(fdr.StockListing)는 최신 영업일 확인차 data.krx.co.kr 를
      찌르므로 이 전략에서는 절대 쓰지 않는다. CSV 만 직접 가져온다.
    ★ index_col=0 을 무조건 주면 안 된다: delisting CSV 는 인덱스 컬럼이 없어서
      첫 실컬럼(Symbol=종목코드)이 인덱스로 먹히고 폐지종목이 통째로 사라진다 = 생존자편향.
    """
    ck = f"fdr_cache_{kind.replace('/', '_')}"
    cached = VAULT.get_table(ck, scope="shared", max_age_days=7)
    if cached is not None and len(cached):
        LOG.debug(f"FDR 캐시 테이블 재사용: {ck} ({len(cached):,}행)")
        return cached
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        raw = http_get(_SCG_FDR_CACHE.format(kind=kind, date=d.isoformat()),
                       source="fdr", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} ({len(df):,}행)")
                VAULT.put_table(ck, df, scope="shared", domain="universe",
                                source=f"fdr_github_cache/{kind}")
                return df
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
#  ★ 1순위 PIT 스파인 — FinanceData/marcap (일별 전종목시세)
#
#  이것이 이 전략의 유니버스·시가총액 문제를 통째로 해결한다.
#    · 연도별 parquet 하나에 그날 상장돼 있던 **모든** 종목의 행이 들어 있다.
#      → "그날 행이 있다 = 그날 상장돼 있었다". 생존자편향이 정의상 불가능하다.
#      → 폐지 종목도 마지막 거래일까지 그대로 들어 있다.
#    · Close 는 **무수정** 종가, Stocks 는 그날의 상장주식수, Marcap 은 그 둘의 곱이다.
#      → PIT 시가총액을 DART 주식총수 없이 바로 얻는다 (호출 12,000회 절약).
#    · 거래일 캘린더도 여기서 나온다 (KRX 휴장일 API 불필요).
#
#  접근 경로는 raw.githubusercontent.com 이다 — data.krx.co.kr 을 거치지 않는다.
#  (원 데이터의 출처는 KRX 공시자료이며, 이 코드베이스가 이미 fdr_krx_data_cache 에
#   대해 취하고 있는 것과 같은 태도다. 접근이 아니라 계보를 문제 삼는 금지였다면
#   MARCAP_ENABLED=False 로 끄면 아래의 상장/폐지목록 경로로 자동 폴백한다)
#
#  ⚠ FinanceData/marcap 패키지의 marcap_data() 헬퍼는 마지막에 Volume>0 으로 거르는데,
#    그러면 거래정지 종목이 통째로 사라진다. 우리는 parquet 을 직접 읽어 그 필터를 피한다.
# ══════════════════════════════════════════════════════════════════════════════════════

MARCAP_ENABLED = True
_MARCAP_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet"

#  ★ parquet 에서 **읽을 컬럼만** 지정한다. 이게 이 파일에서 가장 중요한 한 줄이다.
#    전체 18컬럼을 읽으면 1년치가 274MB 이고 그중 222MB 가 쓰지도 않는 object 컬럼
#    (Name 48.7 · Dept 42.9 · Code 33.9 · Market 33.6 · MarketId 32.3 · ChangeCode 31.2 MB)이다.
#    16년을 concat 하면 4.4GB, pd.concat 피크는 그 두 배 — 실제로 여기서 30분 정체가 났다.
_MARCAP_READ = ["Date", "Code", "Name", "Close", "ChangesRatio", "Amount",
                "Marcap", "Stocks", "Market"]
#  슬림 스파인 스키마. 9M행 기준 약 270MB (원본 4.4GB 대비 1/16).
SPINE_COLS = ["code", "date", "close_unadj", "ret_adj", "amount", "marketcap", "shares"]
SPINE_TABLE = "marcap_spine_{y}"        # 공용 인덱스 — 다른 전략도 그대로 재사용


def _scg_slim_marcap(d: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """원본 연도 프레임 → (슬림 스파인, 종목메타). 원본은 즉시 버린다.

    ★ 메타를 DataFrame.attrs 에 실어 보내지 않는다. attrs 에 DataFrame 을 넣으면
      pd.concat 이 attrs 동일성 검사에서 DataFrame == DataFrame 를 평가하다 ValueError 로
      죽고, parquet 저장도 TypeError 가 난다. (실제로 두 곳 다 터졌다)
    """
    cm = {str(c).strip().lower(): c for c in d.columns}
    need = ("code", "date", "close", "marcap", "stocks")
    if not all(k in cm for k in need):
        return pd.DataFrame(columns=SPINE_COLS), pd.DataFrame(columns=["code", "name", "market"])
    out = pd.DataFrame({
        "code": d[cm["code"]].astype(str).str.zfill(6),
        "date": pd.to_datetime(d[cm["date"]], errors="coerce").astype("datetime64[ns]"),
        "close_unadj": pd.to_numeric(d[cm["close"]], errors="coerce").astype("float32"),
        #  ★ ChangesRatio 는 KRX 기준가 기반 등락률이라 액면분할·유무상증자가 이미 보정돼 있다.
        #    (삼성전자 2018-05-04 분할일: 종가 pct_change 는 -98.04% 인데 ChangesRatio 는 -2.08%)
        #    → 이 한 컬럼으로 수정주가 계열을 만들 수 있어 종목별 가격 재수집이 통째로 불필요해진다.
        #    단 현금배당은 반영되지 않는다(가격수익률이지 총수익률이 아니다). 명시해 둔다.
        "ret_adj": (pd.to_numeric(d[cm["changesratio"]], errors="coerce").astype("float32") / 100.0
                    if "changesratio" in cm else np.float32(np.nan)),
        "amount": (pd.to_numeric(d[cm["amount"]], errors="coerce").astype("float32")
                   if "amount" in cm else np.float32(np.nan)),
        "marketcap": pd.to_numeric(d[cm["marcap"]], errors="coerce").astype("float64"),
        "shares": pd.to_numeric(d[cm["stocks"]], errors="coerce").astype("float64"),
    })
    #  종목명/시장은 마스터를 만들 때만 필요하므로 (code → 값) 한 줄짜리 사전으로 따로 뺀다.
    #  이것만 빼도 연도당 115MB(Name 48.7 + Market 33.6 + MarketId 32.3)가 사라진다.
    meta = pd.DataFrame({
        "code": out["code"],
        "name": d[cm["name"]].astype(str) if "name" in cm else "",
        "market": d[cm["market"]].astype(str) if "market" in cm else "KRX",
    }).drop_duplicates("code", keep="last").reset_index(drop=True)
    return out.dropna(subset=["code", "date"]).reset_index(drop=True), meta


def scg_fetch_spine(years: Sequence[int]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """★ 이 전략의 단일 데이터 스파인 — 일별 전종목시세.

    여기서 나오는 것: 거래일 캘린더 · PIT 유니버스 · 수정주가(수익률) · 무수정 종가 ·
    PIT 시가총액 · 상장주식수 · 거래대금. 전부 한 소스에서 나오므로 종목별 가격 재수집이
    **한 건도** 필요 없다(이전 구조는 여기서 2,800회를 더 긁었다).

    ★ 접근 경로는 raw.githubusercontent.com 이다 — data.krx.co.kr 을 거치지 않는다.
      (원 데이터 계보는 KRX 공시자료다. 계보 자체가 금지 대상이라면 MARCAP_ENABLED=False
       로 끄면 상장/폐지목록 + 종목별 가격수집 경로로 자동 폴백한다)

    ★ 메모리: 연도별로 받아 **즉시 슬림화**하고 원본을 버린다. 원본을 다 모으면 4.4GB 이고
      그게 이전 실행이 30분간 멈춘 이유다. 슬림 스파인은 9M행에 약 270MB 다.
    """
    empty = (pd.DataFrame(columns=SPINE_COLS), pd.DataFrame(columns=["code", "name", "market"]))
    if not MARCAP_ENABLED:
        return empty
    this_year = _dt.datetime.now(_dt.timezone.utc).year
    ys = sorted({int(x) for x in years})
    frames, metas, got, miss = [], [], [], []
    LOG.info(f"일별 전종목시세 스파인 {ys[0]}~{ys[-1]} ({len(ys)}개 연도) 준비 — "
             f"연도별로 받아 즉시 슬림화합니다(원본을 모으지 않습니다)")
    for k, y in enumerate(ys, 1):
        tbl = SPINE_TABLE.format(y=y)
        #  과거 연도 파일은 사실상 불변 → 영구 캐시. 올해 파일만 매일 갱신된다.
        d = VAULT.get_table(tbl, scope="shared", max_age_days=(1.0 if y >= this_year else None))
        if d is not None and len(d):
            LOG.debug(f"  [{k}/{len(ys)}] {y} 캐시 재사용 {len(d):,}행")
        else:
            if RUN_MODE == "CACHED":
                miss.append(y)
                continue
            t0 = time.time()
            raw = http_get(_MARCAP_URL.format(y=y), source="fdr", as_bytes=True,
                           tries=3, timeout=240)
            if not raw or len(raw) < 10_000:
                miss.append(y)
                LOG.warn(f"  [{k}/{len(ys)}] {y} 다운로드 실패 — 그 해는 유니버스에서 빠집니다")
                continue
            try:
                #  ★ columns= 로 필요한 컬럼만 읽는다. 읽고 나서 버리면 이미 메모리를 먹은 뒤다.
                rawdf = pd.read_parquet(io.BytesIO(raw), columns=_MARCAP_READ)
            except Exception:
                try:
                    rawdf = pd.read_parquet(io.BytesIO(raw))
                except Exception as e:
                    LOG.warn(f"  [{k}/{len(ys)}] {y} parquet 파싱 실패({type(e).__name__})")
                    miss.append(y)
                    continue
            d, meta = _scg_slim_marcap(rawdf)
            del rawdf, raw
            if not len(d):
                miss.append(y)
                continue
            VAULT.put_table(tbl, d, scope="shared", domain="universe",
                            source="FinanceData/marcap (github)")
            if meta is not None and len(meta):
                VAULT.put_table(f"marcap_meta_{y}", meta, scope="shared", domain="universe",
                                source="FinanceData/marcap (github)")
            got.append(y)
            LOG.info(f"  [{k}/{len(ys)}] {y} 수집 {len(d):,}행 · {mem_mb(d):.0f}MB · "
                     f"{time.time()-t0:.1f}s")
        m = VAULT.get_table(f"marcap_meta_{y}", scope="shared")
        if m is not None and len(m):
            metas.append(m)
        frames.append(d.reindex(columns=SPINE_COLS))
    if got:
        VAULT.flush("shared")
    if not frames:
        LOG.warn("스파인을 확보하지 못했습니다 — 상장/폐지목록 + 종목별 가격수집 경로로 폴백합니다.")
        return empty

    for f in frames:
        f.attrs.clear()                      # concat 의 attrs 동일성 검사를 원천 차단
    S = pd.concat(frames, ignore_index=True, copy=False)
    del frames
    S["date"] = S["date"].astype("datetime64[ns]")
    #  code 를 category 로 접으면 9M행 object(500MB) → int16 코드(18MB) 가 된다
    S["code"] = S["code"].astype("category")
    META = (pd.concat(metas, ignore_index=True).drop_duplicates("code", keep="last")
            if metas else pd.DataFrame(columns=["code", "name", "market"]))
    LOG.ok(f"스파인 {len(S):,}행 · {S['code'].nunique():,}종목 × {S['date'].nunique():,}거래일 · "
           f"{mem_mb(S):.0f}MB (신규 {len(got)}개 연도 · 캐시 {len(ys)-len(got)-len(miss)}개"
           + (f" · 누락 {miss}" if miss else "") + ")")
    PIPE.io("IN", "DRIVE", "marcap_spine", S, source="FinanceData/marcap")
    return S, META


def scg_spine_close_adj(S: pd.DataFrame) -> pd.DataFrame:
    """수정주가 계열을 스파인에서 직접 만든다 — 종목별 HTTP 0회.

    close_adj = 1000 × Π(1 + ret_adj).  절대 수준은 의미가 없고 비율만 쓰이므로
    기준값 1000 이면 충분하다(수익률·IC·백테스트가 전부 비율 연산이다).
    ★ ret_adj 는 KRX 기준가 기반이라 액면분할·증자가 이미 보정돼 있다. 대신 현금배당은
      빠져 있다 — 가격수익률이며, 한국 주식 백테스트의 통상적 관행이다.
    """
    if S is None or S.empty:
        return S
    S = S.sort_values(["code", "date"], kind="mergesort")
    r = S["ret_adj"].to_numpy("float64")
    #  첫 관측일의 등락률은 전일 기준가가 없어 의미가 없다 → 0 으로 두고 1.0 에서 출발한다.
    first = ~S["code"].duplicated().to_numpy()
    r = np.where(first | ~np.isfinite(r), 0.0, r)
    #  ±60% 를 넘는 일간 등락률은 한국 시장에 존재하지 않는다(상하한 ±30%).
    #  데이터 오류가 누적수익률을 통째로 날리는 것을 막는다.
    bad = np.abs(r) > 0.6
    if bad.any():
        LOG.info(f"일간 등락률 이상치 {int(bad.sum()):,}건을 0 으로 대체했습니다 "
                 f"(한국 시장 상하한 ±30% 초과 — 데이터 오류로 봅니다)")
        r = np.where(bad, 0.0, r)
    S = S.copy()
    S["close_adj"] = (1000.0 * pd.Series(1.0 + r, index=S.index)
                      .groupby(S["code"], observed=True).cumprod()).astype("float32")
    return S


def scg_spine_calendar(S: pd.DataFrame) -> pd.DatetimeIndex:
    """거래일 캘린더 — 전종목시세에 행이 있는 날이 곧 거래일이다(KRX 휴장일 API 불필요)."""
    if S is None or S.empty:
        return pd.DatetimeIndex([])
    cal = pd.DatetimeIndex(sorted(pd.unique(S["date"]))).normalize()
    LOG.ok(f"거래일 캘린더 {len(cal):,}일 ({cal.min().date()} ~ {cal.max().date()})")
    return cal


def scg_spine_master(S: pd.DataFrame, META: pd.DataFrame) -> pd.DataFrame:
    """종목 마스터 — 최초/최종 거래일. 폐지목록이 없어도 성립한다."""
    if S is None or S.empty:
        return pd.DataFrame(columns=SCG_SEC_COLS)
    g = S.groupby("code", observed=True)["date"]
    t = pd.DataFrame({"first_seen": g.min(), "last_seen": g.max()}).reset_index()
    t["code"] = t["code"].astype(str)
    end = pd.Timestamp(S["date"].max())
    #  마지막 거래일이 데이터 끝에서 30일 이상 앞서면 그때 사라진 종목이다
    gone = (end - t["last_seen"]).dt.days > 30
    t["delisting_date"] = pd.to_datetime(np.where(gone, t["last_seen"] + pd.Timedelta(days=1),
                                                  pd.NaT))
    if META is not None and len(META):
        t = t.merge(META.assign(code=META["code"].astype(str)), on="code", how="left")
    for c, v in (("name", ""), ("market", "KRX")):
        if c not in t.columns:
            t[c] = v
        t[c] = t[c].fillna(v)
    t["listing_date"] = t["first_seen"]
    t["corp_code"] = np.nan
    t["industry"] = ""
    t["src"] = "marcap"
    t["delist_src"] = np.where(gone, "marcap_last_seen", "")
    return t.reindex(columns=SCG_SEC_COLS)


def scg_spine_universe(S: pd.DataFrame, signal_dates, sec: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """★ 생존자편향이 정의상 불가능한 유니버스: '그날 시세표에 행이 있었는가'.

    상장일·폐지일을 추정할 필요가 없다. 그날의 시세표가 곧 그날의 유니버스다.
    """
    if S is None or S.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id"])
    sd = pd.DatetimeIndex(signal_dates)
    U = S.loc[S["date"].isin(sd), ["date", "code"]].rename(
        columns={"date": "signal_date", "code": "stock_id"})
    U["stock_id"] = U["stock_id"].astype(str)
    U = U.drop_duplicates()
    if sec is not None and len(sec):
        keep = set(sec["code"].astype(str))
        n0 = U["stock_id"].nunique()
        U = U[U["stock_id"].isin(keep)]
        LOG.debug(f"보통주 필터: {n0:,} → {U['stock_id'].nunique():,}종목")
    per = U.groupby("signal_date").size()
    LOG.ok(f"PIT 유니버스 {len(U):,}행 · 시점당 평균 {per.mean():.0f}종목 "
           f"(최소 {per.min():,} · 최대 {per.max():,}) — 폐지 종목이 그 시절엔 포함됩니다")
    return U.reset_index(drop=True)


def scg_spine_marketcap(S: pd.DataFrame, signal_dates) -> pd.DataFrame:
    """PIT 시가총액 — 그날 관측된 Marcap 을 그대로 쓴다(정의상 PIT 이다)."""
    cols = ["signal_date", "stock_id", "close_unadj", "shares", "marketcap", "mcap_src"]
    if S is None or S.empty:
        return pd.DataFrame(columns=cols)
    sd = pd.DatetimeIndex(signal_dates)
    d = S.loc[S["date"].isin(sd), ["date", "code", "close_unadj", "shares", "marketcap"]]
    out = d.rename(columns={"date": "signal_date", "code": "stock_id"}).copy()
    out["stock_id"] = out["stock_id"].astype(str)
    out["mcap_src"] = "marcap"
    out = out.dropna(subset=["marketcap"])
    LOG.ok(f"PIT 시가총액 {len(out):,}행 — DART 주식총수 호출 없이 확보")
    return out.reindex(columns=cols).reset_index(drop=True)


def scg_spine_adv(S: pd.DataFrame, signal_dates) -> pd.DataFrame:
    """20거래일 평균 거래대금 — 용량 진단용(하드게이트 아님). 스파인에서 바로 만든다."""
    cols = ["signal_date", "stock_id", "adv20"]
    if S is None or S.empty or "amount" not in S.columns:
        return pd.DataFrame(columns=cols)
    d = S[["code", "date", "amount"]].sort_values(["code", "date"], kind="mergesort")
    d["adv20"] = (d.groupby("code", observed=True)["amount"]
                   .transform(lambda s: s.rolling(20, min_periods=5).mean()))
    sd = pd.DatetimeIndex(signal_dates)
    out = d.loc[d["date"].isin(sd) & d["adv20"].notna(), ["date", "code", "adv20"]]
    out = out.rename(columns={"date": "signal_date", "code": "stock_id"})
    out["stock_id"] = out["stock_id"].astype(str)
    return out.reindex(columns=cols).reset_index(drop=True)


def scg_spine_prices(S: pd.DataFrame) -> pd.DataFrame:
    """백테스트가 쓰는 (code, date, close_adj) 패널. 스파인의 뷰일 뿐 새 수집이 아니다."""
    if S is None or S.empty or "close_adj" not in S.columns:
        return pd.DataFrame(columns=["code", "date", "close_adj", "amount", "src"])
    out = S[["code", "date", "close_adj", "amount"]].copy()
    out["code"] = out["code"].astype(str)
    out["src"] = "marcap"
    return out


def scg_fetch_listing() -> pd.DataFrame:
    """현재 상장 종목. 이것만으로는 생존자편향이 남으므로 반드시 폐지목록과 합쳐야 한다."""
    d = _scg_fdr_cache_csv("listing/krx")
    if d is None or not len(d):
        LOG.warn("상장목록을 확보하지 못했습니다 (FDR GitHub 캐시 실패). "
                 "DART corpCode 와 가격 관측만으로 유니버스를 구성합니다 — 정확도가 떨어집니다.")
        return pd.DataFrame(columns=SCG_SEC_COLS)
    col = _scg_lower_map(d)
    code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
    name_c = col.get("name") or col.get("korean name") or col.get("isu_nm")
    if not code_c or not name_c:
        LOG.warn(f"상장목록 컬럼 인식 실패: {list(d.columns)[:12]}")
        return pd.DataFrame(columns=SCG_SEC_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[name_c].astype(str).str.strip(),
        "market": (d[col["market"]].astype(str) if "market" in col
                   else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
        "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
        "industry": (d[col["sector"]].astype(str) if "sector" in col
                     else d[col["industry"]].astype(str) if "industry" in col else ""),
    })
    t["delisting_date"] = pd.NaT
    t["corp_code"] = np.nan
    t["src"] = "fdr_listing"
    t["delist_src"] = ""
    t = t.dropna(subset=["code"]).drop_duplicates("code")
    LOG.ok(f"상장목록 {len(t):,}건 (KRX 미호출 경로)")
    return t[SCG_SEC_COLS]


def scg_fetch_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. KRX 없이 이 GitHub 캐시가 사실상 유일한 공개 경로다."""
    d = _scg_fdr_cache_csv("listing/delisting")
    empty = pd.DataFrame(columns=["code", "name", "delisting_date", "market", "secugroup"])
    if d is None or not len(d):
        LOG.warn("상장폐지 목록을 확보하지 못했습니다 — 생존자편향 제거가 '관측기반 추정'에만 "
                 "의존하게 됩니다. 결과 해석 시 반드시 감안하세요.")
        return empty
    col = _scg_lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        LOG.warn(f"폐지목록에서 종목코드 컬럼을 찾지 못했습니다: {list(d.columns)[:12]}")
        return empty
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date",
                                  "listingdate") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c
    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    t = pd.DataFrame({
        "code": codes, "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    }).dropna(subset=["code"])
    #  재상장/재폐지가 있으면 '가장 늦은 폐지일'을 남긴다(가장 이른 것을 남기면 재상장
    #  구간이 통째로 유니버스에서 빠져 표본이 줄어든다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    #  ★ 탈락분을 '코드 형식 오류'로 뭉뚱그리면 오경보가 난다. 폐지목록에는 ELW·신주인수권
    #    (8자리, 예: 722011J7)이 대량으로 섞여 있고 그건 보통주가 아니므로 빼는 게 맞다.
    #    진짜 문제는 '6자리인데 파싱 실패한' 건이다. 둘을 갈라서 보고한다.
    failed = raw_codes[codes.isna()]
    n_bad = int(codes.isna().sum())
    n_nonequity = int(failed.str.len().ne(6).sum())
    n_real = n_bad - n_nonequity
    LOG.ok(f"상장폐지 목록 {len(t):,}건 (원본 {n_raw:,} · 보통주 아님 {n_nonequity:,} "
           f"[ELW·신주인수권 등, 제외가 정상] · 코드형식 실패 {n_real:,})")
    if n_real > n_raw * 0.02:
        LOG.warn(f"6자리인데 파싱에 실패한 폐지종목이 {n_real:,}건입니다 — 그만큼 생존자편향이 "
                 f"남습니다. 예시: {failed[failed.str.len().eq(6)].head(5).tolist()}")
    return t


def scg_fetch_dart_corpcode() -> pd.DataFrame:
    """DART corpCode.xml — corp_code ↔ stock_code 매핑 (KRX 아님, 금융감독원)."""
    cols = ["corp_code", "corp_name", "code", "modify_date"]
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.debug(f"DART corpCode 캐시 재사용 ({len(cached):,}건)")
        return cached.reindex(columns=cols)
    if not DART_API_KEY:
        LOG.info("DART_API_KEY 가 없어 corp_code 매핑을 건너뜁니다 → 실적 실측치(A)가 없어 "
                 "ACC* 는 전부 0 으로 수축됩니다(애널리스트는 유지).")
        return pd.DataFrame(columns=cols)
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3,
                   referer="https://opendart.fss.or.kr/")
    if not raw or len(raw) < 1000:
        LOG.warn("corpCode.xml 을 받지 못했습니다. DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=cols)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read(z.namelist()[0])
    except Exception as e:
        LOG.warn(f"corpCode.xml 압축 해제 실패({type(e).__name__}) — 응답이 ZIP 이 아닙니다 "
                 f"(대개 인증키 오류 시 XML 에러문서가 옵니다).")
        return pd.DataFrame(columns=cols)
    rows = re.findall(
        rb"<list>\s*<corp_code>(.*?)</corp_code>\s*<corp_name>(.*?)</corp_name>\s*"
        rb"<stock_code>(.*?)</stock_code>\s*<modify_date>(.*?)</modify_date>", xml, re.S)
    if not rows:
        return pd.DataFrame(columns=cols)
    t = pd.DataFrame({
        "corp_code": [r[0].decode("utf-8", "ignore").strip() for r in rows],
        "corp_name": [r[1].decode("utf-8", "ignore").strip() for r in rows],
        "code": [to_code6(r[2].decode("utf-8", "ignore").strip()) for r in rows],
        "modify_date": [r[3].decode("utf-8", "ignore").strip() for r in rows],
    })
    VAULT.put_table("dart_corpcode", t, scope="shared", domain="dart", source="opendart corpCode")
    LOG.ok(f"DART corpCode {len(t):,}건 (상장 {int(t['code'].notna().sum()):,}건)")
    return t


def scg_build_security_master(listing: pd.DataFrame, delisting: pd.DataFrame,
                              corpcode: pd.DataFrame) -> pd.DataFrame:
    """상장 + 폐지 + corp_code 를 합쳐 종목 마스터를 만든다.

    ★ 폐지 종목을 '행으로 존재하게' 만드는 것이 이 함수의 존재 이유다.
      상장목록만 쓰면 오늘 살아있는 회사만 남고, 그 순간 백테스트는 전부 거짓말이 된다.
    """
    frames = []
    if listing is not None and len(listing):
        frames.append(listing.reindex(columns=SCG_SEC_COLS))
    if delisting is not None and len(delisting):
        d = pd.DataFrame({
            "code": delisting["code"], "name": delisting["name"],
            "market": delisting.get("market", "KRX"),
            "listing_date": pd.NaT, "delisting_date": delisting["delisting_date"],
            "corp_code": np.nan, "industry": "",
            "src": "fdr_delisting", "delist_src": "fdr_delisting"})
        frames.append(d.reindex(columns=SCG_SEC_COLS))
    if not frames:
        raise RuntimeError(
            "종목 마스터를 만들 수 없습니다: 상장목록·폐지목록을 모두 확보하지 못했습니다. "
            "KRX 를 쓰지 않는 설계이므로 raw.githubusercontent.com 접근이 필수입니다 — "
            "네트워크(프록시/방화벽)를 확인하세요.")

    A = pd.concat(frames, ignore_index=True)
    A = A[A["code"].notna()].copy()
    A["code"] = A["code"].astype(str)
    agg = A.groupby("code", as_index=False).agg(
        name=("name", lambda s: max((str(x) for x in s if str(x) not in ("", "nan")),
                                    key=len, default="")),
        market=("market", "first"),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "max"),
        industry=("industry", "first"),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
        delist_src=("delist_src", lambda s: "|".join(sorted({x for x in map(str, s) if x}))))
    agg["corp_code"] = np.nan

    if corpcode is not None and len(corpcode):
        cc = corpcode.dropna(subset=["code"]).drop_duplicates("code")
        agg = agg.drop(columns=["corp_code"]).merge(
            cc[["code", "corp_code"]], on="code", how="left")

    #  ── 보통주만 남긴다 (시점 불변 규칙이라 미래정보가 아니다) ────────────────────────
    n0 = len(agg)
    is_common = agg["code"].str.len().eq(6) & agg["code"].str[5].eq("0")
    bad_name = agg["name"].astype(str).str.contains(_SCG_NONEQUITY_NAME, na=False)
    agg = agg[is_common & ~bad_name].copy()
    LOG.info(f"종목 마스터 {n0:,} → 보통주 {len(agg):,}건 "
             f"(우선주 등 {int((~is_common).sum()):,} · 스팩/ETF/리츠 {int(bad_name.sum()):,} 제외)")

    n_del = int(agg["delisting_date"].notna().sum())
    LOG.ok(f"종목 마스터 {len(agg):,}건 · 상장폐지 이력 보유 {n_del:,}건 "
           f"({100*n_del/max(len(agg),1):.1f}%)")
    if n_del < 300:
        LOG.warn(f"폐지 종목이 {n_del:,}건뿐입니다. 10년 구간이면 통상 1,000건 이상입니다 — "
                 f"생존자편향이 완전히 제거되지 않았을 수 있습니다. 그대로 보고합니다.")
    return agg.reindex(columns=SCG_SEC_COLS)


def scg_infer_delisting_from_prices(sec: pd.DataFrame, px: pd.DataFrame,
                                    cal: np.ndarray, gap_days: int = 200) -> pd.DataFrame:
    """③ 관측기반 폐지 추정 — 시장은 계속 도는데 이 종목만 시계열이 끊겼다면 폐지다.

    ★ 폐지목록이 놓친 종목을 여기서 줍는다. 이것을 안 하면 그 종목들은
      '데이터 끝까지 살아 있었던 것'처럼 처리되어 생존자편향이 남는다.
    ★ 반대 방향의 사고도 막아야 한다: 데이터 **수집 실패**를 폐지로 오인하면
      멀쩡한 종목이 유니버스에서 사라진다. 그래서 마지막 거래일이 '전체 데이터의 끝'에서
      gap_days 이상 떨어져 있을 때만 폐지로 본다.
    """
    if px is None or px.empty or sec is None or sec.empty:
        return sec
    last = px.groupby("code", observed=True)["date"].max()
    if last.empty:
        return sec
    data_end = pd.Timestamp(last.max())
    S = sec.copy()
    S["_last_px"] = S["code"].map(last)
    need = S["delisting_date"].isna() & S["_last_px"].notna() & \
        ((data_end - S["_last_px"]).dt.days > gap_days)
    n = int(need.sum())
    if n:
        #  마지막 체결 다음 거래일을 폐지일로 본다(그날부터 유니버스에서 빠진다)
        nd = _scg_shift_td(S.loc[need, "_last_px"], 1, cal)
        S.loc[need, "delisting_date"] = pd.to_datetime(nd)
        S.loc[need, "delisting_date"] = S.loc[need, "delisting_date"].fillna(
            S.loc[need, "_last_px"] + pd.Timedelta(days=1))
        S.loc[need, "delist_src"] = (S.loc[need, "delist_src"].astype(str)
                                     .str.strip("|") + "|inferred_price_stop").str.strip("|")
        LOG.info(f"관측기반 폐지 추정 {n:,}건 — 폐지목록에 없지만 가격 시계열이 "
                 f"{gap_days}일 이상 먼저 끊긴 종목입니다(생존자편향 제거의 3중 방어 ③).")
    both = int((sec["delisting_date"].notna() &
                sec["code"].isin(S.loc[need, "code"])).sum())
    LOG.debug(f"폐지 근거 교차: 목록기반 {int(sec['delisting_date'].notna().sum()):,} · "
              f"관측기반 추가 {n:,} · 중복 {both:,}")
    return S.drop(columns=["_last_px"])


def scg_first_trade_dates(sec: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """상장일이 비어 있으면 최초 체결일로 보수적으로 채운다.

    ★ '보수적' 의 방향이 중요하다. 최초 체결일은 실제 상장일보다 같거나 늦으므로,
      이걸로 채우면 유니버스 편입이 늦어질지언정 빨라지지 않는다 → 미래누수 없음.
    """
    if px is None or px.empty:
        return sec
    first = px.groupby("code", observed=True)["date"].min()
    S = sec.copy()
    need = S["listing_date"].isna()
    S.loc[need, "listing_date"] = S.loc[need, "code"].map(first)
    S["listing_date"] = as_ts_series(S["listing_date"])
    LOG.debug(f"상장일 보강 {int(need.sum()):,}건 (최초 체결일 기준 — 보수적 방향)")
    return S


def scg_universe_at(sec: pd.DataFrame, dates) -> pd.DataFrame:
    """시점별 유니버스 멤버십. 이 함수 하나가 생존자편향 제거의 최종 판정자다.

        회원 조건:  listing_date <= t  AND  (delisting_date 없음 OR delisting_date > t)
    """
    d = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(dates))).dropna().unique()))
    S = sec.dropna(subset=["code"]).copy()
    S["listing_date"] = as_ts_series(S["listing_date"])
    S["delisting_date"] = as_ts_series(S["delisting_date"])
    #  상장일이 끝내 결측이면 '언제부터 있었는지 모른다' → 보수적으로 데이터 시작부터 포함하지
    #  않는다면 표본이 준다. 반대로 무조건 포함하면 상장 전 데이터를 쓰게 된다.
    #  가격이 있는 날부터만 수익률이 계산되므로, 여기서는 포함하고 하류에서 가격으로 걸러진다.
    #  센티넬은 datetime64[ns] 범위(1677~2262) 안이어야 한다. 2999 를 쓰면 OverflowError 다.
    ls = S["listing_date"].fillna(pd.Timestamp("1900-01-01")).values.astype("datetime64[ns]")
    de = S["delisting_date"].fillna(pd.Timestamp("2200-01-01")).values.astype("datetime64[ns]")
    dv = d.values.astype("datetime64[ns]")
    mask = (ls[:, None] <= dv[None, :]) & (de[:, None] > dv[None, :])
    ii, jj = np.nonzero(mask)
    return pd.DataFrame({"signal_date": dv[jj], "stock_id": S["code"].values[ii]})


def scg_build_calendar(px: pd.DataFrame, bench: Optional[pd.DataFrame] = None
                       ) -> pd.DatetimeIndex:
    """거래일 캘린더 — KRX 휴장일 API 없이 '실제로 거래가 일어난 날'의 합집합으로 만든다.

    ★ Leadership 의 20일은 calendar day 가 아니라 trading day 다(§4). 이 캘린더가 틀리면
      t20 이 통째로 어긋나 Leadership 이 조용히 다른 것을 측정한다.
    ★ 한 종목만 거래된 날을 거래일로 세면 오류에 취약하므로, 그날 거래된 종목 수가
      중앙값의 20% 이상인 날만 채택한다.
    """
    cands = []
    if bench is not None and len(bench):
        cands.append(pd.DatetimeIndex(as_ts_series(bench["date"]).dropna().unique()))
    if px is not None and len(px):
        cnt = px.groupby("date", observed=True)["code"].size()
        if len(cnt):
            thr = max(1.0, float(cnt.median()) * 0.2)
            cands.append(pd.DatetimeIndex(cnt[cnt >= thr].index))
    if not cands:
        LOG.warn("거래일 캘린더 원천이 없어 영업일(월~금)로 대체합니다 — 공휴일이 포함되어 "
                 "t20 이 며칠 어긋날 수 있습니다.")
        return pd.bdate_range(as_ts(BACKTEST_START) - pd.DateOffset(years=HISTORY_WARMUP_YEARS + 1),
                              as_ts(BACKTEST_END) + pd.DateOffset(years=1))
    cal = cands[0]
    for c in cands[1:]:
        cal = cal.union(c)
    cal = pd.DatetimeIndex(sorted(set(cal))).normalize().drop_duplicates()
    LOG.ok(f"거래일 캘린더 {len(cal):,}일 ({cal.min().date()} ~ {cal.max().date()}) — "
           f"KRX 휴장일 API 없이 실거래 관측으로 구성")
    return cal


def scg_signal_dates(cal: pd.DatetimeIndex, freq: str = "M") -> pd.DatetimeIndex:
    """신호 시점 그리드 — 각 기간의 **마지막 거래일**. 달력 말일이 아니다."""
    if not len(cal):
        return pd.DatetimeIndex([])
    s = pd.Series(cal, index=cal)
    period = "W" if str(freq).upper().startswith("W") else "M"
    g = s.groupby(s.index.to_period(period)).max()
    sd = pd.DatetimeIndex(g.values)
    lo, hi = as_ts(BACKTEST_START), as_ts(BACKTEST_END)
    sd = sd[(sd >= lo) & (sd <= hi)]
    LOG.ok(f"신호 시점 {len(sd)}개 ({period} 그리드 · {sd.min().date()} ~ {sd.max().date()})")
    return sd


# ══════════════════════════════════════════════════════════════════════════════════════
#  PIT 시가총액 — 하위 1000 비교 유니버스 (§ 사용자 요구)
# ══════════════════════════════════════════════════════════════════════════════════════

def scg_build_marketcap(px_unadj: pd.DataFrame, shares: pd.DataFrame,
                        signal_dates: pd.DatetimeIndex, cal: np.ndarray) -> pd.DataFrame:
    """PIT 시가총액 = 그 시점의 **실제 주가(무수정)** × 그 시점까지 공시된 **주식총수**.

    ★ 왜 무수정 주가인가: 수정주가는 과거를 현재 기준으로 다시 쓴 값이다.
      2016년 시가총액을 2026년 기준 수정주가로 계산하면 액면분할한 종목의 과거 시총이
      분할 배수만큼 축소되어 '하위 1000' 선정이 통째로 틀어진다.
    ★ 왜 PIT 주식총수인가: 오늘의 주식수를 과거에 곱하면 그 사이의 증자·감자가
      전부 미래정보로 새어 들어간다. DART 접수일(rcept_dt) 이후에만 반영한다.
    ★ 주식총수를 못 구한 종목은 버리지 않는다. mcap 이 NaN 이면 하위1000 선정에서만
      빠지고 전체(ALL) 유니버스에는 그대로 남는다 — 표본 보존이 우선이다(§49).
    """
    cols = ["signal_date", "stock_id", "close_unadj", "shares", "marketcap", "mcap_src"]
    if px_unadj is None or px_unadj.empty:
        LOG.warn("무수정 주가가 없어 PIT 시가총액을 만들 수 없습니다 → 하위1000 비교 유니버스 비활성.")
        return pd.DataFrame(columns=cols)

    M, codes, didx = _scg_price_matrix(px_unadj, np.asarray(cal, dtype="datetime64[ns]"),
                                       value_col="close_unadj")
    if M.size == 0:
        return pd.DataFrame(columns=cols)
    U = scg_universe_at_frame(signal_dates, codes)
    ci = U["stock_id"].map(codes).to_numpy("int64")
    pos = np.searchsorted(didx, U["signal_date"].values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = pos >= 0
    U["close_unadj"] = np.where(ok, M[np.clip(pos, 0, len(didx) - 1), ci], np.nan)
    U = U[U["close_unadj"].notna()]
    if U.empty:
        return pd.DataFrame(columns=cols)

    if shares is None or shares.empty:
        LOG.warn("주식총수(DART)를 확보하지 못해 시가총액을 만들 수 없습니다 → "
                 "하위1000 비교 유니버스는 '거래대금 하위'로 대체됩니다.")
        U["shares"] = np.nan
        U["marketcap"] = np.nan
        U["mcap_src"] = "none"
        return U.reindex(columns=cols)

    sh = shares[["code", "knowledge_date", "shares"]].dropna().copy()
    sh["knowledge_date"] = _scg_ns(sh["knowledge_date"])
    sh = sh.dropna(subset=["knowledge_date"]).sort_values("knowledge_date")
    #  ★ merge_asof backward = '그 시점까지 공시된 최신 주식수'. 미래 공시는 구조적으로 안 붙는다.
    U["signal_date"] = _scg_ns(U["signal_date"])
    U = U.sort_values("signal_date")
    J = pd.merge_asof(U, sh.rename(columns={"knowledge_date": "signal_date"}),
                      on="signal_date", left_by="stock_id", right_by="code",
                      direction="backward")
    J["marketcap"] = J["close_unadj"] * J["shares"]
    J["mcap_src"] = np.where(J["shares"].notna(), "dart_shares", "none")
    cov = float(J["marketcap"].notna().mean())
    LOG.ok(f"PIT 시가총액 {len(J):,}행 · 커버리지 {100*cov:.1f}% "
           f"(무수정주가 × DART 주식총수, 접수일 기준 asof)")
    if cov < 0.5:
        LOG.warn(f"시가총액 커버리지가 {100*cov:.0f}% 입니다 — 하위1000 선정이 부분표본에서만 "
                 f"이뤄집니다. 커버리지 밖 종목은 ALL 유니버스에는 그대로 남습니다.")
    return J.reindex(columns=cols)


def scg_universe_at_frame(signal_dates: pd.DatetimeIndex, codes: Dict[str, int]) -> pd.DataFrame:
    """(시점 × 가격보유종목) 격자. 시가총액 계산의 뼈대."""
    cs = list(codes)
    sd = pd.DatetimeIndex(signal_dates)
    return pd.DataFrame({
        "signal_date": np.repeat(sd.values.astype("datetime64[ns]"), len(cs)),
        "stock_id": np.tile(np.array(cs, dtype=object), len(sd)),
    })


def scg_small_universe(mcap: pd.DataFrame, n: int, fallback_adv: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """시점별 시가총액 **하위 n 종목**. 기존 전략 대비 비교용 압축 유니버스."""
    cols = ["signal_date", "stock_id"]
    if mcap is not None and len(mcap) and mcap["marketcap"].notna().any():
        d = mcap.dropna(subset=["marketcap"]).copy()
        d["_r"] = d.groupby("signal_date", observed=True)["marketcap"].rank(
            method="first", ascending=True)
        out = d[d["_r"] <= n][cols]
        per = out.groupby("signal_date").size()
        LOG.ok(f"하위{n:,} 유니버스: 시점당 평균 {per.mean():.0f}종목 "
               f"(최소 {per.min():.0f} · 최대 {per.max():.0f})")
        return out.reset_index(drop=True)
    if fallback_adv is not None and len(fallback_adv):
        LOG.warn(f"시가총액이 없어 '거래대금 하위 {n:,}' 로 대체합니다 — 규모 프록시이며 "
                 f"시가총액과 완전히 같지 않습니다. 해석 시 감안하세요.")
        d = fallback_adv.dropna(subset=["adv20"]).copy()
        d["_r"] = d.groupby("signal_date", observed=True)["adv20"].rank(
            method="first", ascending=True)
        return d[d["_r"] <= n][cols].reset_index(drop=True)
    LOG.warn("하위1000 비교 유니버스를 만들 수 없습니다 (시가총액·거래대금 모두 없음).")
    return pd.DataFrame(columns=cols)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 — KRX 미호출. FDR / 네이버금융 / yfinance 3중화.                                ║
# ║                                                                                          ║
# ║  ★ 두 종류의 가격을 **분리해서** 쓴다. 섞으면 조용히 틀린다.                                 ║
# ║      close_adj   (수정주가)  → 수익률·IC·백테스트.  분할/배당이 소급 반영된 값.             ║
# ║      close_unadj (실제주가)  → 시가총액·목표주가 환산. 그날 실제로 체결된 값.               ║
# ║    수정주가로 2016년 시가총액을 계산하면 이후 액면분할한 종목의 과거 시총이 배수만큼         ║
# ║    줄어들어 '하위 1000' 선정이 통째로 틀어진다. 이게 흔한 조용한 버그다.                     ║
# ║                                                                                          ║
# ║  ★ 캐시 재사용: 이전 전략(TCD v2)이 만들어 둔 공용 테이블 krx_ohlcv_daily 를 **씨앗으로**    ║
# ║    읽는다. 단, 그 테이블은 소스별로 수정/무수정이 섞여 있으므로(yfinance 행은 무수정)        ║
# ║    src 로 갈라서 각각 제 자리에 넣는다. 그대로 합치면 분할 종목에서 점프가 생긴다.           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_PX_ADJ_TABLE = "price_daily_adj"          # 공용 — 다른 전략도 그대로 재사용 가능
SCG_PX_UNADJ_TABLE = "price_daily_unadj"      # 공용
SCG_PX_COLS = ["code", "date", "close_adj", "volume", "amount", "src"]
SCG_UNADJ_COLS = ["code", "date", "close_unadj", "adj_factor", "src"]
#  이 소스들은 수정주가를 준다. yfinance 는 auto_adjust=False 로 부르면 무수정이다.
_SCG_ADJ_SRC = ("fdr", "naver", "pykrx")


def _scg_px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """FinanceDataReader — 한국 종목은 네이버 계열 소스라 KRX 로그인과 무관하다."""
    if fdr is None:
        return None
    try:
        limiter("fdr").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or not len(d):
        return None
    d = d.rename(columns={c: str(c).lower() for c in d.columns}).reset_index()
    dc = next((c for c in d.columns if str(c).lower() in ("date", "index")), None)
    if dc is None or "close" not in d.columns:
        return None
    out = pd.DataFrame({"code": code, "date": as_ts_series(d[dc]),
                        "close_adj": pd.to_numeric(d["close"], errors="coerce"),
                        "volume": pd.to_numeric(d.get("volume"), errors="coerce")})
    out["amount"] = (pd.to_numeric(d["amount"], errors="coerce") if "amount" in d.columns
                     else out["close_adj"] * out["volume"])
    out["src"] = "fdr"
    return out.dropna(subset=["date", "close_adj"])


def _scg_px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 금융 차트 API. 로그인 불필요, 폐지 직전까지의 시계열도 대체로 남아 있다."""
    url = ("https://api.finance.naver.com/siseJson.naver?symbol=%s&requestType=1"
           "&startTime=%s&endTime=%s&timeframe=day"
           % (code, as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d")))
    txt = http_get(url, source="naver", tries=2, referer="https://finance.naver.com/")
    if not txt or "[" not in txt:
        return None
    try:
        rows = json.loads(re.sub(r"'", '"', txt.strip()))
    except Exception:
        return None
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    hdr = [str(x).strip() for x in rows[0]]
    body = [r for r in rows[1:] if isinstance(r, list) and len(r) >= 5]
    if not body:
        return None
    d = pd.DataFrame(body, columns=hdr[:len(body[0])])
    cmap = {c: str(c).strip().lower() for c in d.columns}
    d = d.rename(columns=cmap)
    dc = next((c for c in d.columns if c in ("날짜", "date")), None)
    cc = next((c for c in d.columns if c in ("종가", "close")), None)
    vc = next((c for c in d.columns if c in ("거래량", "volume")), None)
    if dc is None or cc is None:
        return None
    out = pd.DataFrame({
        "code": code,
        "date": pd.to_datetime(d[dc].astype(str), format="%Y%m%d", errors="coerce"),
        "close_adj": pd.to_numeric(d[cc], errors="coerce"),
        "volume": pd.to_numeric(d[vc], errors="coerce") if vc else np.nan})
    out["amount"] = out["close_adj"] * out["volume"]
    out["src"] = "naver"
    return out.dropna(subset=["date", "close_adj"])


def _scg_yf_symbols(code: str) -> List[str]:
    return [f"{code}.KS", f"{code}.KQ"]


def scg_fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """수정주가 일별 패널. 캐시 우선 → 부족분만 신규 → 드라이브 재적재.

    ★ 이 함수의 성능이 곧 백테스트 소요시간이다. 이미 받은 종목은 절대 다시 받지 않는다.
      (종목별 마지막 관측일을 보고 '연장이 필요한 종목'만 고른다)
    """
    want = [str(c) for c in pd.unique(pd.Series(list(codes))) if c and str(c) != "nan"]
    lo, hi = as_ts(start), as_ts(end)

    frames = []
    cached = VAULT.get_table(SCG_PX_ADJ_TABLE, scope="shared")
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        frames.append(cached.reindex(columns=SCG_PX_COLS))
        LOG.info(f"공용 캐시에서 수정주가 {len(cached):,}행 재사용")
    #  ★ 이전 전략(TCD v2)이 남긴 공용 테이블도 그대로 재활용한다 — 단, 수정주가 소스만.
    legacy = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if legacy is not None and len(legacy) and "close" in legacy.columns:
        lg = legacy.copy()
        lg["src"] = (lg["src"].astype(str) if "src" in lg.columns
                     else pd.Series("unknown", index=lg.index))
        keep = lg["src"].isin(_SCG_ADJ_SRC)
        n_drop = int((~keep).sum())
        lg = lg[keep]
        if len(lg):
            lg = pd.DataFrame({"code": lg["code"].astype(str), "date": as_ts_series(lg["date"]),
                               "close_adj": pd.to_numeric(lg["close"], errors="coerce"),
                               "volume": pd.to_numeric(lg.get("volume"), errors="coerce"),
                               "amount": pd.to_numeric(lg.get("amount"), errors="coerce"),
                               "src": lg["src"]})
            frames.append(lg.dropna(subset=["date", "close_adj"]))
            LOG.info(f"이전 전략 캐시(krx_ohlcv_daily)에서 {len(lg):,}행 재활용 "
                     f"(수정주가 소스만 · 무수정 소스 {n_drop:,}행 제외 — 섞으면 분할 종목에 점프가 생깁니다)")

    have = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCG_PX_COLS)
    if len(have):
        have = have.dropna(subset=["code", "date"]).drop_duplicates(["code", "date"], keep="last")
    last = have.groupby("code")["date"].max() if len(have) else pd.Series(dtype="datetime64[ns]")

    if RUN_MODE == "CACHED":
        LOG.info("RUN_MODE='CACHED' — 신규 가격 수집을 건너뜁니다.")
        return have[have["date"].between(lo, hi)].reset_index(drop=True)

    todo = [c for c in want if (c not in last.index) or (last[c] < hi - pd.Timedelta(days=7))]
    LOG.info(f"수정주가: 전체 {len(want):,}종목 중 신규/연장 필요 {len(todo):,}종목 "
             f"(캐시 충분 {len(want)-len(todo):,}종목)")
    if not todo:
        return have[have["date"].between(lo, hi)].reset_index(drop=True)

    def _one(code: str) -> Optional[pd.DataFrame]:
        s = last[code] + pd.Timedelta(days=1) if code in last.index else lo
        s = max(s, lo)
        if s > hi:
            return None
        ss, ee = s.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")
        for fn in (_scg_px_fdr, _scg_px_naver):
            try:
                d = fn(code, ss, ee)
            except Exception:
                d = None
            if d is not None and len(d):
                return d
        return None

    got: List[pd.DataFrame] = []
    CH = 1500
    for k0 in range(0, len(todo), CH):
        part = todo[k0:k0 + CH]
        res = pmap_io(_one, part, workers=N_WORKERS_IO,
                      desc=f"가격 수집 {k0//CH+1}/{(len(todo)-1)//CH+1}")
        got += [d for d in res if d is not None and len(d)]
        del res
        if got:
            add = pd.concat(got, ignore_index=True)
            have = pd.concat([have, add], ignore_index=True).drop_duplicates(
                ["code", "date"], keep="last")
            VAULT.put_table(SCG_PX_ADJ_TABLE, have, scope="shared", domain="price",
                            source="fdr/naver (KRX 미호출)")
            VAULT.flush("shared")
            got = []
    n_fail = len([c for c in todo if c not in set(have["code"])])
    if n_fail:
        LOG.info(f"가격을 끝내 못 받은 종목 {n_fail:,}개 — 폐지 직후이거나 소스에 없는 종목입니다. "
                 f"유니버스에는 남지만 수익률이 없어 백테스트 표본에서 자연히 빠집니다.")
    out = have[have["date"].between(lo, hi)].reset_index(drop=True)
    LOG.ok(f"수정주가 패널 {len(out):,}행 · {out['code'].nunique():,}종목")
    PIPE.io("OUT", "DRIVE", SCG_PX_ADJ_TABLE, out, source="fdr/naver")
    return out


def scg_fetch_unadjusted(codes: Sequence[str], start: str, end: str,
                         px_adj: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """무수정 종가 — yfinance(auto_adjust=False)를 **배치**로 받는다.

    ★ 시가총액 전용이다. 커버리지가 낮아도 전체 유니버스에는 영향을 주지 않는다
      (하위1000 비교 유니버스 선정에서만 쓰인다).
    ★ 배치 다운로드가 핵심: 종목별 단건이면 2,800회지만 50개씩 묶으면 56회다.
    """
    if yf is None:
        LOG.info("yfinance 가 없어 무수정 주가를 건너뜁니다 → 시가총액은 만들 수 없고 "
                 "하위1000 비교는 거래대금 하위로 대체됩니다.")
        return pd.DataFrame(columns=SCG_UNADJ_COLS)
    want = [str(c) for c in pd.unique(pd.Series(list(codes))) if c and str(c) != "nan"]
    cached = VAULT.get_table(SCG_PX_UNADJ_TABLE, scope="shared")
    have = pd.DataFrame(columns=SCG_UNADJ_COLS)
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        have = cached.reindex(columns=SCG_UNADJ_COLS)
        LOG.info(f"공용 캐시에서 무수정 주가 {len(have):,}행 재사용")
    if RUN_MODE == "CACHED":
        return have

    lo, hi = as_ts(start), as_ts(end)
    last = have.groupby("code")["date"].max() if len(have) else pd.Series(dtype="datetime64[ns]")
    todo = [c for c in want if (c not in last.index) or (last[c] < hi - pd.Timedelta(days=30))]
    if not todo:
        return have
    LOG.info(f"무수정 주가(시가총액용): {len(todo):,}종목 배치 수집 "
             f"({(len(todo)-1)//50+1}회 호출 — 종목별 단건이면 {len(todo):,}회입니다)")

    #  상장 시장을 몰라 .KS/.KQ 를 둘 다 시도해야 한다 → 두 접미사를 한 배치에 넣는다
    got: List[pd.DataFrame] = []
    B = 50
    syms = [s for c in todo for s in _scg_yf_symbols(c)]
    for k0 in range(0, len(syms), B):
        batch = syms[k0:k0 + B]
        try:
            limiter("yfinance").wait()
            d = yf.download(tickers=" ".join(batch), start=lo.strftime("%Y-%m-%d"),
                            end=(hi + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                            auto_adjust=False, group_by="ticker", progress=False,
                            threads=True, actions=False)
        except Exception as e:
            LOG.debug(f"yfinance 배치 실패({type(e).__name__}) — 건너뜁니다")
            continue
        if d is None or not len(d):
            continue
        for sym in batch:
            try:
                sub = d[sym] if isinstance(d.columns, pd.MultiIndex) else d
            except Exception:
                continue
            if sub is None or not len(sub) or "Close" not in sub.columns:
                continue
            s = sub.dropna(subset=["Close"])
            if not len(s):
                continue
            adj = s["Adj Close"] if "Adj Close" in s.columns else s["Close"]
            got.append(pd.DataFrame({
                "code": sym.split(".")[0], "date": as_ts_series(s.index),
                "close_unadj": pd.to_numeric(s["Close"], errors="coerce").values,
                "adj_factor": (pd.to_numeric(adj, errors="coerce").values /
                               pd.to_numeric(s["Close"], errors="coerce").values),
                "src": "yfinance"}))
        if got and (k0 // B) % 10 == 9:
            have = pd.concat([have] + got, ignore_index=True).drop_duplicates(
                ["code", "date"], keep="last")
            VAULT.put_table(SCG_PX_UNADJ_TABLE, have, scope="shared", domain="price",
                            source="yfinance auto_adjust=False")
            VAULT.flush("shared")
            got = []
    if got:
        have = pd.concat([have] + got, ignore_index=True).drop_duplicates(
            ["code", "date"], keep="last")
        VAULT.put_table(SCG_PX_UNADJ_TABLE, have, scope="shared", domain="price",
                        source="yfinance auto_adjust=False")
        VAULT.flush("shared")
    have = have.dropna(subset=["code", "date", "close_unadj"])
    LOG.ok(f"무수정 주가 {len(have):,}행 · {have['code'].nunique():,}종목 "
           f"(유니버스 대비 {100*have['code'].nunique()/max(len(want),1):.0f}%)")

    #  ── 수정/무수정이 실제로 다른지 검증한다. 같다면 둘 중 하나가 잘못된 것이다. ──────
    if px_adj is not None and len(px_adj) and len(have):
        j = have.merge(px_adj[["code", "date", "close_adj"]], on=["code", "date"], how="inner")
        if len(j) > 100:
            r = (j["close_adj"] / j["close_unadj"]).replace([np.inf, -np.inf], np.nan).dropna()
            diff = float((r.sub(1).abs() > 0.01).mean())
            LOG.info(f"수정/무수정 대조 {len(j):,}행: 1% 초과 괴리 {100*diff:.1f}% "
                     f"(분할·유상증자 등 자본변동이 있었던 구간). 괴리가 0% 라면 두 계열이 "
                     f"같은 것이므로 시가총액이 수정주가 기준이 되어 과거 시총이 왜곡됩니다.")
    return have.reindex(columns=SCG_UNADJ_COLS)


def scg_fetch_benchmark(start: str, end: str) -> pd.DataFrame:
    """KOSPI 지수 — 벤치마크 + 거래일 캘린더의 1순위 원천."""
    cached = VAULT.get_table("benchmark_ks11_daily", scope="shared", max_age_days=3)
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        return cached
    d = None
    if fdr is not None:
        try:
            limiter("fdr").wait()
            d = fdr.DataReader("KS11", start, end)
        except Exception:
            d = None
    if (d is None or not len(d)) and yf is not None:
        try:
            limiter("yfinance").wait()
            d = yf.download("^KS11", start=start, end=end, progress=False, auto_adjust=True)
        except Exception:
            d = None
    if d is None or not len(d):
        LOG.warn("벤치마크(KOSPI)를 받지 못했습니다 — 레짐 분할과 초과수익 계산을 건너뜁니다.")
        return pd.DataFrame(columns=["date", "close"])
    d = d.reset_index()
    d.columns = [str(c[0]) if isinstance(c, tuple) else str(c) for c in d.columns]
    dc = next((c for c in d.columns if c.lower() in ("date", "index")), d.columns[0])
    cc = next((c for c in d.columns if c.lower() == "close"), None)
    if cc is None:
        return pd.DataFrame(columns=["date", "close"])
    out = pd.DataFrame({"date": as_ts_series(d[dc]),
                        "close": pd.to_numeric(d[cc], errors="coerce")}).dropna()
    VAULT.put_table("benchmark_ks11_daily", out, scope="shared", domain="price", source="fdr KS11")
    LOG.ok(f"벤치마크(KOSPI) {len(out):,}일")
    return out


def scg_benchmark_returns(bench: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.Series:
    """신호 시점 그리드에 맞춘 벤치마크 기간수익률."""
    if bench is None or bench.empty or not len(signal_dates):
        return pd.Series(dtype="float64")
    b = bench.dropna().sort_values("date")
    idx = b["date"].values.astype("datetime64[ns]")
    pos = np.searchsorted(idx, pd.DatetimeIndex(signal_dates).values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = pos >= 0
    v = np.where(ok, b["close"].to_numpy("float64")[np.clip(pos, 0, len(b) - 1)], np.nan)
    s = pd.Series(v, index=pd.DatetimeIndex(signal_dates))
    return s.pct_change().shift(-1).dropna()      # t → t+1 구간 수익률 (신호와 같은 정렬)


def scg_adv_panel(px: pd.DataFrame, signal_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """20일 평균거래대금 — 용량 진단과 시가총액 폴백에 쓴다(하드게이트 아님)."""
    if px is None or px.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id", "adv20"])
    p = px[["code", "date", "amount"]].dropna(subset=["code", "date"]).sort_values(["code", "date"])
    p["adv20"] = p.groupby("code", observed=True)["amount"].transform(
        lambda s: s.rolling(20, min_periods=5).mean())
    p = p.dropna(subset=["adv20"])
    if p.empty:
        return pd.DataFrame(columns=["signal_date", "stock_id", "adv20"])
    #  종목별 루프로 merge_asof 를 2,800번 도는 대신 by= 로 한 번에 끝낸다
    #  (2,800회 × 120시점이면 파이썬 오버헤드만 수십 초, by= 는 1초 미만)
    codes = pd.Index(pd.unique(p["code"]))
    grid = pd.DataFrame({
        "signal_date": np.repeat(pd.DatetimeIndex(signal_dates).values.astype("datetime64[ns]"),
                                 len(codes)),
        "stock_id": np.tile(codes.to_numpy(dtype=object), len(signal_dates)),
    }).sort_values("signal_date")
    right = p[["code", "date", "adv20"]].rename(columns={"date": "signal_date"})
    right["signal_date"] = _scg_ns(right["signal_date"])
    right = right.sort_values("signal_date")
    j = pd.merge_asof(grid, right, on="signal_date", left_by="stock_id", right_by="code",
                      direction="backward", tolerance=pd.Timedelta(days=30))
    return j.dropna(subset=["adv20"])[["signal_date", "stock_id", "adv20"]].reset_index(drop=True)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 실적 실측치(A) · 주식총수 · 정기공시 접수일                                   ║
# ║                                                                                          ║
# ║  ★ 호출량 정책 — v1 의 "19,000 하드코딩" 을 제거했다.                                       ║
# ║    · 사전 상한 없음. 한도 판정 권한은 오직 DART 응답 status="020" 에 있다.                  ║
# ║    · 남은 호출량을 실시간으로 추적해 진행률과 함께 출력한다.                                 ║
# ║    · 하루 경계는 **KST 자정**. Colab VM 은 보통 UTC 라 이걸 안 맞추면 9시간 어긋나           ║
# ║      "남았는데 멈추거나 / 없는데 계속 때리는" 사고가 난다.                                   ║
# ║    · 카운터는 100회마다 + 종료 시 + 소진 시 저장한다(중간에 죽어도 다음 실행이 이어받음).     ║
# ║                                                                                          ║
# ║  ★ 그리고 애초에 적게 쓴다 — 설계로. 실행 로그의 [DART 호출 예산] 표에 산술이 그대로 나온다: ║
# ║      순진한 방식: 2,800사 × 12년 × 4분기 단건 = 134,400 호출 (7일)                          ║
# ║      이 코드   : 공시 날짜스윕 1,200 + 다중회사 배치 336 + 주식총수 12,000 ≈ 13,500 (1일)   ║
# ║      그리고 전부 드라이브 캐시에 남아 두 번째 실행부터는 0 호출이다.                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_DART_BASE = "https://opendart.fss.or.kr/api/"
SCG_DART_MULTI_BATCH = 100          # fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개
SCG_REPRT_ANNUAL = "11011"          # 사업보고서
SCG_KST = _dt.timezone(_dt.timedelta(hours=9))

SCG_DART_STATUS = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class ScgDartQuota:
    """DART 일일 호출량 관리자 — 한도를 '추측'하지 않고 '관측'한다.

    OpenDART 에는 잔여 호출량을 알려주는 엔드포인트가 없다(확인함). 그래서:
      · 우리가 오늘 쓴 횟수는 정확히 센다 (드라이브에 KST 날짜와 함께 영속)
      · '남은 양'은 공식 한도 20,000 에서 뺀 **추정치**로만 표시한다
      · 실제 중단 판정은 오직 status="020" 이다. 추정치가 남았다고 계속 때리지 않고,
        추정치가 0 이라고 미리 멈추지도 않는다 (DART_DAILY_LIMIT=None 기본값)
    """
    OFFICIAL_LIMIT = 20_000

    def __init__(self):
        self.today = _dt.datetime.now(SCG_KST).date().isoformat()   # ★ KST 기준
        self.n = 0
        self.exhausted = False
        self.n_020 = 0
        self._lk = threading.Lock()
        self._dirty = 0
        self._load()

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_quota.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
                self.exhausted = bool(j.get("exhausted", False))
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘(KST {self.today}) 이미 사용한 DART 호출 {self.n:,}건 — 이어서 진행합니다."
                     + ("  ※ 이미 한도 소진 상태로 기록되어 있습니다." if self.exhausted else ""))

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n, "exhausted": self.exhausted}))
            self._dirty = 0
        except Exception:
            pass

    def est_remaining(self) -> int:
        cap = DART_DAILY_LIMIT if DART_DAILY_LIMIT else self.OFFICIAL_LIMIT
        return max(0, int(cap) - self.n - int(DART_RESERVE_CALLS or 0))

    def _roll_day(self):
        """KST 자정을 넘겼으면 카운터를 리셋한다. 콜드빌드는 몇 시간씩 도므로
        생성 시점 날짜에 고정해 두면 자정 이후에도 어제 소진 상태를 물고 있게 된다."""
        today = _dt.datetime.now(SCG_KST).date().isoformat()
        if today != self.today:
            LOG.info(f"KST 날짜가 바뀌었습니다 ({self.today} → {today}). "
                     f"DART 호출 카운터를 리셋하고 계속 진행합니다.")
            self.today, self.n, self.exhausted, self._dirty = today, 0, False, 0
            self._save()

    def take(self, k: int = 1) -> bool:
        """호출 예약. 최악(재시도 포함)을 먼저 잡고 실제 시도 후 차액을 환급한다."""
        with self._lk:
            self._roll_day()
            if self.exhausted:
                return False
            #  사용자가 명시적으로 상한을 정한 경우에만 사전 차단한다. 기본(None)은 무제한.
            if DART_DAILY_LIMIT is not None and \
               self.n + k > int(DART_DAILY_LIMIT) - int(DART_RESERVE_CALLS or 0):
                if not self.exhausted:
                    self.exhausted = True
                    self._save()
                    LOG.warn(f"사용자 지정 상한 DART_DAILY_LIMIT={DART_DAILY_LIMIT:,} 에 도달했습니다. "
                             f"(DART 서버가 막은 것이 아닙니다 — None 으로 두면 서버가 020 을 줄 "
                             f"때까지 씁니다)")
                return False
            self.n += k
            self._dirty += k
            if self._dirty >= 100:
                self._save()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def hit_limit(self):
        """DART 가 020 을 반환했다 — 이것이 유일한 진짜 한도 신호다."""
        with self._lk:
            self.n_020 += 1
            if not self.exhausted:
                self.exhausted = True
                self._save()
                LOG.warn(f"DART 가 요청제한(020)을 반환했습니다. 오늘 사용량 {self.n:,}건. "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일(KST 자정 이후) "
                         f"같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")

    def close(self):
        self._save()

    def report(self):
        cap = DART_DAILY_LIMIT if DART_DAILY_LIMIT else self.OFFICIAL_LIMIT
        LOG.table([["오늘 날짜 (KST)", self.today],
                   ["사용한 호출", f"{self.n:,}"],
                   ["공식 일일 한도", f"{self.OFFICIAL_LIMIT:,}"],
                   ["사용자 지정 상한", f"{DART_DAILY_LIMIT:,}" if DART_DAILY_LIMIT else "없음(자동)"],
                   ["남은 호출 (추정)", f"{self.est_remaining():,}"],
                   ["020 응답 횟수", f"{self.n_020:,}"],
                   ["상태", "소진 — 내일 이어받기" if self.exhausted else "여유"]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출 예산 — 잔여량은 추정치이고, 중단 판정은 서버의 020 응답이 합니다")


SCG_QUOTA: Optional[ScgDartQuota] = None


def scg_dart_api(endpoint: str, params: dict, tries: int = 2) -> Optional[dict]:
    """DART 호출 1회. 예산 예약 → 실제 시도 → 차액 환급 → status 해석."""
    if not DART_API_KEY:
        return None
    q = SCG_QUOTA
    if q is not None and not q.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    att = {"n": 0}
    js = http_json(SCG_DART_BASE + endpoint, source="dart", params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: att.__setitem__("n", att["n"] + 1))
    if q is not None:
        q.refund(max(0, tries - max(1, att["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "020":
            if q is not None:
                q.hit_limit()
        elif st == "021":
            #  021 = '조회 가능한 회사 개수 초과' — 배치 크기 문제이지 일일 한도가 아니다.
            #  이걸 소진으로 처리하면 그 순간부터 모든 DART 수집이 조용히 꺼진다.
            LOG.warn(f"DART status=021 (조회 가능한 회사 개수 초과) — 배치 크기를 줄이세요 "
                     f"(SCG_DART_MULTI_BATCH={SCG_DART_MULTI_BATCH}). 일일 한도와 무관합니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({SCG_DART_STATUS.get(st,'?')}). "
                      f"DART_API_KEY 를 확인하세요 — https://opendart.fss.or.kr 에서 재발급 가능합니다.")
            if q is not None:
                q.exhausted = True
        elif st != "013":
            LOG.debug(f"DART status={st} ({SCG_DART_STATUS.get(st,'?')}) ep={endpoint}")
        return None
    return js


def _scg_rcept_date(rcept_no: Any) -> Optional[pd.Timestamp]:
    """rcept_no 앞 8자리 = 접수일자. PIT 의 근거는 결산일이 아니라 이 날짜다."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    return None


# ── ① 정기공시 날짜 스윕 — 실적 '발표일' 의 원천 ────────────────────────────────────────────
_SCG_ANNUAL_RE = re.compile(r"사업보고서")
_SCG_YEAR_IN_NM = re.compile(r"\((\d{4})\.\d{2}\)")


def scg_fetch_periodic_disclosures(start: str, end: str) -> pd.DataFrame:
    """list.json 을 **날짜로 스윕**한다 — 회사별로 도는 것보다 수십 배 싸다.

    10년치 정기공시 ≈ 11만 건 = 100건/페이지 → 약 1,100 호출. 회사별이면 134,400 호출이다.
    ★ 여기서 얻는 rcept_dt 가 곧 actual_announcement_date 이고, PIT 의 유일한 근거다.
    """
    cols = ["corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm", "bsns_year"]
    cached = VAULT.get_table("dart_periodic_disclosures", scope="shared")
    have_to = None
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have_to = cached["rcept_dt"].max()
        LOG.info(f"공용 캐시에서 정기공시 {len(cached):,}건 재사용 (~{have_to.date()})")
        if have_to >= as_ts(end) - pd.Timedelta(days=7):
            return cached.reindex(columns=cols)
    if not DART_API_KEY:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    bgn = (have_to + pd.Timedelta(days=1)) if have_to is not None else as_ts(start)
    fin = as_ts(end)
    rows: List[dict] = []
    #  분기별로 끊어 요청한다 (한 구간의 total_page 가 너무 커지지 않도록)
    #  ★ date_range(freq="QS") 는 bgn 이 분기 중간이면 '다음 분기 시작'부터 시작한다.
    #    그러면 이어받기 지점과 그 분기 시작 사이의 공시가 영구히 누락된다
    #    (다음 실행은 더 늦은 지점부터 시작하므로 영영 메워지지 않는다). bgn 을 앞에 붙인다.
    periods = pd.date_range(bgn, fin, freq="QS").tolist()
    if not periods or periods[0] > bgn:
        periods.insert(0, bgn)
    if periods[-1] < fin:
        periods.append(fin)
    for i in range(len(periods) - 1 if len(periods) > 1 else 1):
        b = periods[i]
        e = min(periods[i + 1] - pd.Timedelta(days=1) if len(periods) > 1 else fin, fin)
        if b > e:
            continue
        page = 1
        while True:
            js = scg_dart_api("list.json", {
                "bgn_de": b.strftime("%Y%m%d"), "end_de": e.strftime("%Y%m%d"),
                "pblntf_ty": "A", "page_no": str(page), "page_count": "100"})
            if not js or not isinstance(js.get("list"), list):
                break
            for r in js["list"]:
                rows.append({"corp_code": r.get("corp_code"),
                             "stock_code": to_code6(r.get("stock_code")),
                             "rcept_no": r.get("rcept_no"), "rcept_dt": r.get("rcept_dt"),
                             "report_nm": r.get("report_nm")})
            tp = int(js.get("total_page", 1) or 1)
            if page >= tp or page >= 200:
                break
            page += 1
            if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
                break
        if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
            LOG.warn("일일 한도로 정기공시 스윕을 중단합니다 — 받은 만큼 저장하고 이어받습니다.")
            break

    if rows:
        new = pd.DataFrame(rows)
        new["rcept_dt"] = as_ts_series(new["rcept_dt"])
        yr = new["report_nm"].astype(str).str.extract(_SCG_YEAR_IN_NM)[0]
        new["bsns_year"] = pd.to_numeric(yr, errors="coerce")
        allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
        allr = allr.dropna(subset=["rcept_no"]).drop_duplicates("rcept_no", keep="last")
        VAULT.put_table("dart_periodic_disclosures", allr, scope="shared", domain="dart",
                        source="opendart list.json sweep")
        VAULT.flush("shared")
        PIPE.io("OUT", "DRIVE", "dart_periodic_disclosures", allr, source="opendart list.json")
        LOG.ok(f"정기공시 {len(allr):,}건 확보 (신규 {len(new):,}건)")
        return allr.reindex(columns=cols)
    return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)


def scg_annual_report_dates(dis: pd.DataFrame) -> Dict[Tuple[str, int], pd.Timestamp]:
    """(종목코드, 사업연도) → 사업보고서 접수일. EPS 의 '실적/추정' 판정과 A_date 의 근거."""
    if dis is None or dis.empty:
        return {}
    d = dis[dis["report_nm"].astype(str).str.contains(_SCG_ANNUAL_RE, na=False)].copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt", "stock_code"])
    if "bsns_year" not in d.columns or d["bsns_year"].isna().all():
        #  보고서명에서 연도를 못 뽑았으면 접수연도-1 로 본다(3월 제출이 통례)
        d["bsns_year"] = d["rcept_dt"].dt.year - 1
    d["bsns_year"] = pd.to_numeric(d["bsns_year"], errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    #  같은 (종목,연도)에 정정공시가 여러 건이면 **최초 접수일**을 쓴다 (보수적 = PIT 안전)
    d = d.sort_values("rcept_dt").drop_duplicates(["stock_code", "bsns_year"], keep="first")
    return {(str(c), int(y)): t for c, y, t in
            zip(d["stock_code"], d["bsns_year"], d["rcept_dt"])}


# ── ② 다중회사 주요계정 — 순이익·자본금을 100사/호출로 ────────────────────────────────────
def scg_fetch_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """fnlttMultiAcnt — 100사를 한 번에. 순진한 단건 호출 대비 100배 싸다."""
    cols = ["corp_code", "bsns_year", "fs_div", "account_nm", "thstrm_amount", "rcept_no"]
    cached = VAULT.get_table("dart_multi_annual", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str),
                       pd.to_numeric(cached["bsns_year"], errors="coerce").fillna(0).astype(int)))
        LOG.info(f"공용 캐시에서 다중회사 주요계정 {len(cached):,}행 재사용")
    if not DART_API_KEY:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    corps = [str(c) for c in pd.unique(pd.Series(list(corp_codes))) if c and str(c) != "nan"]
    jobs = []
    for y in sorted(years, reverse=True):            # 최근 연도부터 — 끊겨도 최신이 먼저 완성
        todo = [c for c in corps if (c, int(y)) not in done]
        for k in range(0, len(todo), SCG_DART_MULTI_BATCH):
            jobs.append((todo[k:k + SCG_DART_MULTI_BATCH], int(y)))
    if not jobs:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    LOG.info(f"다중회사 주요계정: {len(jobs):,} 호출 예정 "
             f"(오늘 남은 호출 추정 {SCG_QUOTA.est_remaining():,}건)" if SCG_QUOTA else "")

    def _one(job):
        batch, y = job
        js = scg_dart_api("fnlttMultiAcnt.json",
                          {"corp_code": ",".join(batch), "bsns_year": str(y),
                           "reprt_code": SCG_REPRT_ANNUAL})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        for c in cols:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        return d[cols]

    out = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(100사/호출)")
    frames = [f for f in out if f is not None and len(f)]
    if not frames:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    new = pd.concat(frames, ignore_index=True)
    allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
    allr = allr.drop_duplicates(["corp_code", "bsns_year", "fs_div", "account_nm"], keep="last")
    VAULT.put_table("dart_multi_annual", allr, scope="shared", domain="dart",
                    source="opendart fnlttMultiAcnt")
    VAULT.flush("shared")
    LOG.ok(f"다중회사 주요계정 {len(allr):,}행 (신규 {len(new):,}행 · 호출 {len(jobs):,}회)")
    return allr.reindex(columns=cols)


_SCG_NI_RE = re.compile(r"당기순이익")
_SCG_CAP_RE = re.compile(r"자본금")


def scg_tidy_multi(multi: pd.DataFrame) -> pd.DataFrame:
    """주요계정 → (corp_code, bsns_year) × {net_income, capital_stock, knowledge_date}."""
    cols = ["corp_code", "bsns_year", "net_income", "capital_stock", "knowledge_date"]
    if multi is None or multi.empty:
        return pd.DataFrame(columns=cols)
    d = multi.copy()
    #  ★ 연결(CFS)과 별도(OFS)를 한 회사·한 해에 섞으면 순이익이 두 기준으로 뒤섞여
    #    EPS 실측치가 조용히 틀어진다. 연결이 있으면 연결만, 없으면 별도만 쓴다.
    if "fs_div" in d.columns and d["fs_div"].notna().any():
        pref = d.assign(_p=np.where(d["fs_div"].astype(str).str.upper().eq("CFS"), 0, 1))
        best = pref.groupby(["corp_code", "bsns_year"], observed=True)["_p"].transform("min")
        n0 = len(d)
        d = pref[pref["_p"] == best].drop(columns=["_p"])
        if len(d) < n0:
            LOG.debug(f"연결/별도 혼합 제거: {n0:,} → {len(d):,}행 (회사·연도별 연결 우선)")
    d["amt"] = pd.to_numeric(d["thstrm_amount"].astype(str).str.replace(",", "", regex=False),
                             errors="coerce")
    nm = d["account_nm"].astype(str)
    d["_ni"] = np.where(nm.str.contains(_SCG_NI_RE, na=False), d["amt"], np.nan)
    d["_cap"] = np.where(nm.str.contains(_SCG_CAP_RE, na=False), d["amt"], np.nan)
    g = d.groupby(["corp_code", "bsns_year"], observed=True, sort=False)
    out = g.agg(net_income=("_ni", "max"), capital_stock=("_cap", "max"),
                rcept_no=("rcept_no", "min")).reset_index()
    out["knowledge_date"] = out["rcept_no"].map(_scg_rcept_date)
    #  접수번호가 없으면 사업보고서 법정기한(결산 후 90일)으로 보수적 추정 — 늦게 아는 방향이라
    #  미래누수를 만들지 않는다
    miss = out["knowledge_date"].isna()
    if miss.any():
        out.loc[miss, "knowledge_date"] = pd.to_datetime(
            out.loc[miss, "bsns_year"].astype(int).astype(str) + "-12-31") + pd.Timedelta(days=90)
    return out[cols]


# ── ③ 주식총수 — PIT 시가총액의 필수 입력 ────────────────────────────────────────────────
def scg_fetch_shares(corp_map: pd.DataFrame, years: Sequence[int],
                     priority_codes: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """stockTotqySttus — 보통주 발행주식총수. 회사×연도 단건이라 비싸므로 우선순위를 둔다.

    ★ 끊겨도 쓸모 있게 순서를 잡는다: (애널리스트 커버리지 있는 종목) → (최근 연도) 순.
      일일 한도로 중간에 멈춰도 '분석에 실제로 쓰이는 종목의 최신 데이터'가 먼저 채워진다.
    ★ 못 채운 회사는 자본금/액면가 로 역산해 메운다(scg_shares_panel).
    """
    cols = ["corp_code", "code", "bsns_year", "shares", "par_value", "knowledge_date"]
    cached = VAULT.get_table("dart_shares_outstanding", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str),
                       pd.to_numeric(cached["bsns_year"], errors="coerce").fillna(0).astype(int)))
        LOG.info(f"공용 캐시에서 주식총수 {len(cached):,}행 재사용")
    if not DART_API_KEY or corp_map is None or corp_map.empty:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)

    cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
    prio = set(str(c) for c in (priority_codes or []))
    cm = cm.assign(_p=cm["code"].astype(str).isin(prio).astype(int))
    cm = cm.sort_values("_p", ascending=False)
    jobs = [(str(r.corp_code), str(r.code), int(y))
            for y in sorted(years, reverse=True)
            for r in cm.itertuples(index=False)
            if (str(r.corp_code), int(y)) not in done]
    if not jobs:
        return cached.reindex(columns=cols) if cached is not None else pd.DataFrame(columns=cols)
    est = SCG_QUOTA.est_remaining() if SCG_QUOTA else 0
    LOG.info(f"주식총수: 미확보 {len(jobs):,}건 · 오늘 남은 호출 추정 {est:,}건. "
             f"{'오늘 안에 끝납니다.' if len(jobs) <= est else '오늘 다 못 받으면 내일 이어받습니다(캐시 보존).'}")

    def _one(job):
        corp, code, y = job
        js = scg_dart_api("stockTotqySttus.json",
                          {"corp_code": corp, "bsns_year": str(y),
                           "reprt_code": SCG_REPRT_ANNUAL})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        tot = par = None
        rc = None
        for r in js["list"]:
            se = str(r.get("se", ""))
            rc = rc or r.get("rcept_no")
            if "보통주" not in se and "합계" not in se:
                continue
            v = pd.to_numeric(str(r.get("istc_totqy", "")).replace(",", ""), errors="coerce")
            if pd.notna(v) and v > 0 and ("보통주" in se or tot is None):
                tot = float(v)
                if "보통주" in se:
                    break
        if not tot:
            return None
        #  ★ 액면가는 stockTotqySttus 응답에 없다(stlm_dt 는 결산일이다 — 이걸 액면가로
        #    읽으면 20241231 같은 값이 들어가 주식수 역산이 통째로 망가진다).
        #    액면가는 scg_shares_panel 에서 자본금/주식수 로 역산한다.
        return {"corp_code": corp, "code": code, "bsns_year": int(y), "shares": tot,
                "par_value": np.nan, "knowledge_date": _scg_rcept_date(rc)}

    rows: List[dict] = []
    CH = 3000
    for k0 in range(0, len(jobs), CH):
        part = jobs[k0:k0 + CH]
        out = pmap_io(_one, part, workers=min(N_WORKERS_IO, 8),
                      desc=f"DART 주식총수 {k0//CH+1}/{(len(jobs)-1)//CH+1}")
        rows += [r for r in out if r]
        if rows:
            new = pd.DataFrame(rows)
            allr = pd.concat([cached, new], ignore_index=True) if cached is not None and len(cached) else new
            allr = allr.drop_duplicates(["corp_code", "bsns_year"], keep="last")
            VAULT.put_table("dart_shares_outstanding", allr, scope="shared", domain="dart",
                            source="opendart stockTotqySttus")
            VAULT.flush("shared")
            cached, rows = allr, []
        if SCG_QUOTA is not None and SCG_QUOTA.exhausted:
            LOG.warn("일일 한도로 주식총수 수집을 중단합니다 — 캐시는 보존되며 내일 이어받습니다.")
            break
    res = cached if cached is not None else pd.DataFrame(columns=cols)
    LOG.ok(f"주식총수 {len(res):,}행 확보")
    return res.reindex(columns=cols)


def scg_shares_panel(shares: pd.DataFrame, tidy_multi: pd.DataFrame,
                     corp_map: pd.DataFrame) -> pd.DataFrame:
    """주식총수 패널 — 직접 조회분 + 자본금/액면가 역산분.

    ★ 역산이 왜 정당한가: 자본금 = 발행주식수 × 액면가 는 회계 항등식이다.
      액면가는 회사별로 거의 불변이므로, 직접 조회된 연도에서 액면가를 구해
      나머지 연도의 자본금에 나누면 주식수가 복원된다. 액면분할이 있으면
      액면가가 바뀌므로, 연도별로 가장 가까운 관측 액면가를 쓴다.
    """
    cols = ["code", "bsns_year", "shares", "knowledge_date", "src"]
    parts = []
    if shares is not None and len(shares):
        s = shares.dropna(subset=["code", "shares"]).copy()
        s["src"] = "dart_stockTotqySttus"
        parts.append(s.reindex(columns=cols))
        #  액면가 = 자본금 / 주식수 (직접 관측된 연도에서 산출)
        par = None
        if tidy_multi is not None and len(tidy_multi):
            j = s.merge(tidy_multi, on=["corp_code", "bsns_year"], how="inner")
            j["par_est"] = j["capital_stock"] / j["shares"].replace(0, np.nan)
            par = (j[np.isfinite(j["par_est"]) & (j["par_est"] > 0)]
                   .groupby("corp_code")["par_est"].median())
        if par is not None and len(par) and tidy_multi is not None and len(tidy_multi):
            cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
            t = tidy_multi.merge(cm[["corp_code", "code"]], on="corp_code", how="inner")
            t["_par"] = t["corp_code"].map(par)
            have = set(zip(s["corp_code"].astype(str),
                           s["bsns_year"].astype(int))) if "corp_code" in s.columns else set()
            t = t[~t.apply(lambda r: (str(r["corp_code"]), int(r["bsns_year"])) in have, axis=1)]
            t = t[t["_par"].notna() & (t["_par"] > 0) & t["capital_stock"].notna()]
            if len(t):
                t["shares"] = t["capital_stock"] / t["_par"]
                t["src"] = "derived_capital/par"
                parts.append(t.reindex(columns=cols))
                LOG.info(f"자본금/액면가 역산으로 주식총수 {len(t):,}행 추가 확보 "
                         f"(DART 호출 0회 — 이미 받은 주요계정을 재활용)")
    if not parts:
        return pd.DataFrame(columns=cols)
    P = pd.concat(parts, ignore_index=True).dropna(subset=["code", "shares", "knowledge_date"])
    P = P.sort_values(["code", "knowledge_date"]).drop_duplicates(
        ["code", "bsns_year"], keep="last")
    return P.reindex(columns=cols)


# ── ④ EPS 실측치 ─────────────────────────────────────────────────────────────────────────
def scg_build_eps_actuals(tidy_multi: pd.DataFrame, shares_panel: pd.DataFrame,
                          corp_map: pd.DataFrame, annual_dates: Dict[Tuple[str, int], pd.Timestamp]
                          ) -> pd.DataFrame:
    """실적 실측치 A = 당기순이익 / 발행주식수 (§3 actuals 테이블).

    ★ actual_announcement_date 는 결산일이 아니라 **사업보고서 접수일**이다.
      이걸 결산일(12/31)로 두면 3월에야 알 수 있었던 실적을 1월부터 알았던 것이 되어
      §35 TEST 6(미래누수)이 즉시 깨진다.
    """
    cols = ["stock_id", "fiscal_period", "forecast_metric",
            "actual_value", "actual_announcement_date"]
    if tidy_multi is None or tidy_multi.empty or shares_panel is None or shares_panel.empty:
        LOG.warn("순이익 또는 주식총수가 없어 EPS 실측치를 만들 수 없습니다 → "
                 "EPS 트랙의 ACC* 는 전부 0 으로 수축됩니다(애널리스트는 유지).")
        return pd.DataFrame(columns=cols)
    cm = corp_map.dropna(subset=["corp_code", "code"]).drop_duplicates("corp_code")
    t = tidy_multi.merge(cm[["corp_code", "code"]], on="corp_code", how="inner")
    s = shares_panel[["code", "bsns_year", "shares"]].drop_duplicates(["code", "bsns_year"])
    t = t.merge(s, on=["code", "bsns_year"], how="inner")
    t = t[t["net_income"].notna() & t["shares"].notna() & (t["shares"] > 0)]
    if t.empty:
        return pd.DataFrame(columns=cols)
    t["eps"] = t["net_income"] / t["shares"]

    #  발표일: 사업보고서 접수일 → 없으면 주요계정 rcept 기반 knowledge_date
    key = list(zip(t["code"].astype(str), t["bsns_year"].astype(int)))
    ad = pd.Series([annual_dates.get(k, pd.NaT) for k in key], index=t.index)
    t["actual_announcement_date"] = ad.fillna(as_ts_series(t["knowledge_date"]))
    t = t.dropna(subset=["actual_announcement_date"])
    out = pd.DataFrame({
        "stock_id": t["code"].astype(str),
        "fiscal_period": t["bsns_year"].astype(int).astype(str) + "-12",
        "forecast_metric": "EPS",
        "actual_value": t["eps"].astype("float64"),
        "actual_announcement_date": t["actual_announcement_date"],
    })
    out = out.drop_duplicates(["stock_id", "fiscal_period"], keep="first")
    LOG.ok(f"EPS 실측치 {len(out):,}건 ({out['stock_id'].nunique():,}종목) — "
           f"발표일은 사업보고서 접수일 기준")
    return out.reset_index(drop=True)


def scg_report_dart_plan(n_corps: int, n_years: int, n_covered: int,
                         have_spine: bool = True):
    """★ 사용자가 요구한 '호출량 산술' 을 그대로 표로 낸다.

    스파인(일별 전종목시세)이 상장주식수·시가총액을 이미 주므로, DART 에 남는 일은
    **실적 실측치(순이익) + 발표일** 둘뿐이다. 주식총수 조회 12,000회가 통째로 사라진다.
    """
    naive = n_corps * n_years * 4
    sweep = max(1, int(n_corps * n_years * 4 / 100))
    multi = max(1, int(np.ceil(n_corps / SCG_DART_MULTI_BATCH)) * n_years)
    shr = 0 if have_spine else n_covered * n_years
    total = 1 + sweep + multi + shr
    rows = [
        ["① corpCode.xml (1회)", "1", "회사 ↔ 종목코드 매핑"],
        ["② 정기공시 날짜스윕 (100건/페이지)", f"~{sweep:,}",
         "실적 발표일 = PIT 의 근거. 회사별 호출 대비 100배 절약"],
        ["③ 다중회사 주요계정 (100사/호출)", f"~{multi:,}",
         "순이익 = Accuracy 의 A. 단건 대비 100배 절약"],
        ["④ 주식총수 (회사×연도)", "0" if have_spine else f"~{shr:,}",
         "스파인이 상장주식수를 이미 제공 → 호출 불필요" if have_spine
         else "스파인 없음 → DART 로 대체 수집"],
        ["합계 (최초 콜드빌드)", f"~{total:,}",
         f"일 20,000 한도의 {100*total/20000:.0f}% — 하루 안에 끝납니다"],
        ["순진한 방식이었다면", f"~{naive:,}", "회사×연도×분기 단건 호출 = 7일"],
        ["두 번째 실행부터", "0", "전부 드라이브 공용 캐시에서 재사용"],
    ]
    LOG.table(rows, ["항목", "호출 수", "설명"], ["l", "r", "l"],
              title="DART 호출 예산 산술 — 상한을 미리 정하지 않는다. 한도 판정은 서버의 020 이 하고, "
                    "우리는 설계로 호출을 줄인다")



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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  SCG 코어 — 명세 §5~§29 의 산식을 그대로 구현한다.                                     ║
# ║                                                                                          ║
# ║   analyst_forecast → Accuracy + Leadership → Shrinkage → Recency×Quality                  ║
# ║        → SmartConsensus → SmartGap → (+GapAcceleration)                                  ║
# ║                                                                                          ║
# ║  이 파일에는 네트워크·드라이브·전역상태가 없다. 순수 함수만 있다.                            ║
# ║  그래서 §35 의 TEST 1~9 를 합성데이터로 완전히 검정할 수 있다.                              ║
# ║                                                                                          ║
# ║  ★ 설계 원칙 3가지 (명세 §49)                                                             ║
# ║    1. 하드게이트를 넣지 않는다. 유일하게 허용된 게이트는 MIN_ANALYSTS=2 뿐이다.              ║
# ║    2. 이력이 없는 애널리스트를 탈락시키지 않는다. 중립값(0)으로 수축시킨다.                   ║
# ║    3. 모든 ACC*/LEAD* 는 signal date 마다 PIT 롤링 계산한다. 전체기간 점수 금지.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


@dataclass(frozen=True)
class SCGConfig:
    """§42 공식 V1 파라미터. 코드 어디에도 magic number 를 두지 않는다.

    frozen=True 인 이유: 강건성 검사(§41)가 `replace(SCG, FORECAST_HALFLIFE_DAYS=30)` 로
    변형본을 만들어 돌리는데, 가변 객체였다면 그 변형이 공식 설정에 새어 들어간다.
    민감도 표를 뽑다가 공식 파라미터가 바뀌는 사고를 타입으로 막는다.
    """
    # ── 표본 유지 ────────────────────────────────────────────────────────────────────
    MIN_ANALYSTS: int = 2                     # 유일하게 허용된 하드게이트 (§6.2)
    MAX_FORECAST_AGE_DAYS: int = 180          # stale 제거용. 알파 게이트가 아니다 (§6.1)

    # ── 최근성 ──────────────────────────────────────────────────────────────────────
    FORECAST_HALFLIFE_DAYS: float = 45.0      # §19

    # ── 애널리스트 이력 ──────────────────────────────────────────────────────────────
    ANALYST_HISTORY_YEARS: float = 5.0        # §9
    ACCURACY_HISTORY_HALFLIFE_DAYS: float = 365.0
    LEAD_HISTORY_HALFLIFE_DAYS: float = 365.0
    K_ACC: float = 6.0                        # §10 수축계수
    K_LEAD: float = 6.0                       # §17
    ACC_PRIOR: float = 0.0
    LEAD_PRIOR: float = 0.0

    # ── 정보력 종합 ─────────────────────────────────────────────────────────────────
    ACC_WEIGHT: float = 0.60                  # §18
    LEAD_WEIGHT: float = 0.40
    QUALITY_EXP_SCALE: float = 0.70           # §20
    QUALITY_MULTIPLIER_MIN: float = 0.50
    QUALITY_MULTIPLIER_MAX: float = 2.00

    # ── 이벤트 ──────────────────────────────────────────────────────────────────────
    LEAD_FORWARD_TRADING_DAYS: int = 20       # §13 — calendar day 가 아니라 거래일
    ACCEL_LOOKBACK_TRADING_DAYS: int = 20     # §25
    ACC_EVENT_CLIP: float = 2.0               # §8
    LEAD_EVENT_CLIP: float = 1.0              # §14
    #   Accuracy 계산에 쓸 전망의 최대 나이. §6.1 과 같은 'stale 제거' 목적이며
    #   알파 게이트가 아니다. 3년 묵은 전망을 실적과 비교하는 것을 막기 위한 위생 규칙.
    ACC_FORECAST_MAX_AGE_DAYS: int = 180

    # ── 갭 / 알파 ───────────────────────────────────────────────────────────────────
    SCG_LEVEL_WEIGHT: float = 0.75            # §28
    SCG_ACCEL_WEIGHT: float = 0.25
    NEUTRAL_ACCEL_RANK: float = 0.50          # §28 — accel 결측 시 중립 처리
    DENOM_FLOOR_RATIO: float = 0.10           # §24
    EPSILON: float = 1e-8
    WINSOR_LOWER: float = 0.01
    WINSOR_UPPER: float = 0.99
    MIN_CROSS_SECTION_FOR_WINSOR: int = 30


SCG = SCGConfig()

#  analyst_forecasts 표준 스키마 (§2.1). 이 컬럼 이름은 협상 대상이 아니다.
FORECAST_KEY = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric"]
FORECAST_COLS = FORECAST_KEY + ["broker_id", "report_id", "report_date", "forecast_value"]
GROUP_KEY = ["stock_id", "fiscal_period", "forecast_metric"]      # §5 분석 단위
#  같은 종목이라도 FY1 과 FQ1 은 절대 섞이지 않는다 — 그 보장이 이 튜플 하나에 걸려 있다.

STATUS_OK = "OK"
STATUS_INSUFFICIENT = "INSUFFICIENT_ANALYSTS"


# ══════════════════════════════════════════════════════════════════════════════════════
#  0. 공통 원시연산
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_halflife_weight(age_days, halflife: float) -> np.ndarray:
    """2^(-age/H). age 는 일수(float). 음수 age(미래)는 호출부에서 이미 걸러져야 한다."""
    a = np.asarray(age_days, dtype="float64")
    return np.exp2(-a / float(halflife))


def _scg_ns(s) -> pd.Series:
    """datetime 시리즈를 반드시 나노초 해상도로 통일한다.

    ★ pandas 2.x 는 입력에 따라 datetime64[us]/[s]/[ms] 를 그대로 유지한다.
      그 상태로 merge_asof 를 부르면
        MergeError: incompatible merge keys ... dtype('<M8[ns]') and dtype('<M8[us]')
      가 난다. 조인 키가 되는 모든 날짜는 여기를 통과시킨다.
    """
    return pd.to_datetime(as_ts_series(s), errors="coerce").astype("datetime64[ns]")


def _scg_trading_calendar(cal) -> np.ndarray:
    """거래일 캘린더를 정렬된 datetime64[ns] 배열로 정규화한다."""
    if cal is None:
        return np.array([], dtype="datetime64[ns]")
    if isinstance(cal, pd.DataFrame):
        c = cal
        if "is_trading_day" in c.columns:
            c = c[c["is_trading_day"].astype(bool)]
        s = as_ts_series(c["date"])
    elif isinstance(cal, pd.Series):
        s = as_ts_series(cal)
    else:
        s = pd.Series(pd.DatetimeIndex(cal))
    s = s.dropna().drop_duplicates().sort_values()
    return s.values.astype("datetime64[ns]")


def _scg_shift_td(dates, k: int, cal: np.ndarray) -> np.ndarray:
    """각 날짜에서 거래일 k 세션 뒤(양수)/앞(음수)의 날짜. 범위를 벗어나면 NaT.

    앵커 규칙: t 가 거래일이 아니면 't 이상인 첫 거래일'을 0번 세션으로 본다.
    (§13 의 "20 trading days" 는 calendar day 가 아니다 — 여기가 그 유일한 구현 지점이다)
    """
    d = np.asarray(pd.DatetimeIndex(as_ts_series(pd.Series(dates))).values, dtype="datetime64[ns]")
    out = np.full(d.shape, np.datetime64("NaT"), dtype="datetime64[ns]")
    if cal.size == 0:
        return out
    pos = np.searchsorted(cal, d, side="left")          # t 이상인 첫 거래일의 위치
    tgt = pos + int(k)
    ok = (~pd.isna(d)) & (tgt >= 0) & (tgt < cal.size) & (pos < cal.size)
    out[ok] = cal[tgt[ok]]
    return out


_SCG_DAY0 = np.datetime64("1900-01-01", "D")     # 일자 인코딩 원점 (음수 방지)
_SCG_DAY_K = 200_000                             # gid 당 일자 슬롯 (2447년까지 안전)


def _scg_key(gid: np.ndarray, t: np.ndarray, shift_days: int = 0) -> np.ndarray:
    """(gid, 날짜) → 단조증가 int64 키. gid 블록 경계와 시간 순서를 한 축에 접는다.

    이렇게 접어 두면 '어느 gid 안에서 어느 시간 구간' 이라는 2차원 탐색이
    np.searchsorted 한 번으로 끝난다 — 질의마다 파이썬 루프를 돌 필요가 없다.
    day 는 1900-01-01 기준이라 항상 양수이므로 shift 를 빼도 옆 gid 로 새지 않는다.
    """
    day = (t.astype("datetime64[D]") - _SCG_DAY0).astype("int64")
    day = np.clip(day + int(shift_days), 0, _SCG_DAY_K - 1)
    return gid.astype("int64") * _SCG_DAY_K + day


def _scg_stab(iv_gid: np.ndarray, iv_start: np.ndarray, iv_end: np.ndarray,
              q_gid: np.ndarray, q_time: np.ndarray, max_span_days: int,
              chunk: int = 400_000) -> Tuple[np.ndarray, np.ndarray]:
    """구간 스태빙(interval stabbing): 질의점 (gid, t) 를 덮는 모든 구간을 찾는다.

    반환: (질의 인덱스, 구간 인덱스) 쌍의 배열 — "질의 q 를 구간 i 가 덮는다".

    ★ 이 함수 하나가 이 전략의 두 군데를 동시에 책임진다.
        · signal date 별 active forecast 선정 (§6)
        · Leadership 의 t0/t20 시점 peer 집합 (§13) — leave-one-out 의 모집단
      두 곳에서 '활성 전망 집합'의 정의가 미세하게 달라지면 §35 TEST 7 이 잡아내지
      못하는 조용한 불일치가 생긴다. 그래서 정의를 한 곳에만 둔다.

    ★ 성능의 핵심 두 가지
      1) 구간의 최대 길이가 max_span_days 로 유한하다 → start < t - span 인 구간은
         볼 필요조차 없다(end <= start+span < t). 후보가 질의당 수십 개로 묶인다.
      2) (gid, day) 를 int64 키 하나로 접는다 → 이진탐색이 완전 벡터화된다.
         (질의 60만 건에서 파이썬 루프 대비 수십 배 차이가 난다)
    """
    n_q = q_gid.size
    empty = (np.empty(0, dtype="int64"), np.empty(0, dtype="int64"))
    if n_q == 0 or iv_gid.size == 0:
        return empty

    iv_key = _scg_key(iv_gid, iv_start)
    order = np.argsort(iv_key, kind="stable")
    s_key = iv_key[order]
    s_end = iv_end[order]
    s_start = iv_start[order]

    qi_parts: List[np.ndarray] = []
    ii_parts: List[np.ndarray] = []
    for c0 in range(0, n_q, chunk):
        c1 = min(c0 + chunk, n_q)
        g, t = q_gid[c0:c1], q_time[c0:c1]
        # start ∈ [t - span, t] 인 구간만 후보 (양끝 모두 포함)
        lo = np.searchsorted(s_key, _scg_key(g, t, -int(max_span_days)), side="left")
        hi = np.searchsorted(s_key, _scg_key(g, t, 0) + 1, side="left")
        cnt = np.maximum(hi - lo, 0)
        tot = int(cnt.sum())
        if tot == 0:
            continue
        qi = np.repeat(np.arange(c0, c1, dtype="int64"), cnt)
        base = np.repeat(np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt)
        ii = np.repeat(lo, cnt) + (np.arange(tot, dtype="int64") - base)
        #  후보 선별은 '일' 단위로 했으므로, 최종 판정은 ns 정밀도로 다시 한다.
        #  (지금은 모든 시각이 자정이라 동일하지만, 장중 타임스탬프를 넘기는 호출자가
        #   생겼을 때 조용히 start > t 인 구간을 끌어들이는 것을 막는다)
        keep = (s_end[ii] >= q_time[qi]) & (s_start[ii] <= q_time[qi])
        if keep.any():
            qi_parts.append(qi[keep])
            ii_parts.append(order[ii[keep]])             # 원래 인덱스로 되돌린다

    if not qi_parts:
        return empty
    return (np.concatenate(qi_parts), np.concatenate(ii_parts))


def _scg_validity(f: pd.DataFrame, cfg: SCGConfig) -> pd.DataFrame:
    """각 전망의 '유효 구간' [start, end] 을 만든다 — §2.1 의 1인 1표 규칙의 구현.

    start = report_date
    end   = min( 같은 애널리스트의 다음 전망 직전,  report_date + MAX_FORECAST_AGE_DAYS )

    이렇게 구간을 미리 확정해 두면 "동일 (종목·애널·기간·메트릭)에서 활성 전망은 최대 1개"가
    자료구조 수준에서 보장된다. 즉 §35 TEST 8 은 사후 검사가 아니라 구성상 참이 된다.
    """
    f = f.sort_values(FORECAST_KEY + ["report_date", "report_id"], kind="mergesort")
    # 같은 키·같은 날짜에 두 건이면 report_id 가 큰(나중) 것만 남긴다 — 실행 간 재현 가능한 규칙
    f = f.drop_duplicates(subset=FORECAST_KEY + ["report_date"], keep="last")
    nxt = f.groupby(FORECAST_KEY, observed=True, sort=False)["report_date"].shift(-1)
    hard_end = f["report_date"] + pd.Timedelta(days=int(cfg.MAX_FORECAST_AGE_DAYS))
    repl_end = nxt - pd.Timedelta(1, "ns")
    f = f.copy()
    f["valid_start"] = f["report_date"]
    f["valid_end"] = np.where(repl_end.notna() & (repl_end < hard_end), repl_end, hard_end)
    f["valid_end"] = pd.to_datetime(f["valid_end"])
    return f


def _scg_price_matrix(px: pd.DataFrame, cal: np.ndarray, value_col: str = "close_adj"
                      ) -> Tuple[np.ndarray, Dict[str, int], np.ndarray]:
    """(거래일 × 종목) 가격 행렬. 이후의 모든 수익률·시가총액 계산이 이 행렬 하나에서 나온다.

    ★ 왜 행렬인가: signal date × 종목 × 여러 지평의 전방수익률을 groupby 로 만들면
      수백만 번의 파이썬 호출이 된다. 행렬 + searchsorted 로 바꾸면 전부 벡터 인덱싱이다.
    ★ 결측 처리: 거래정지 등으로 비는 날은 직전가로 채운다(ffill). 다만 **상장 전**과
      **폐지 후**로는 절대 번지지 않게 한다 — 번지면 없는 종목에 가격이 생겨
      생존자편향의 정반대 방향으로 표본을 오염시킨다.
    """
    if px is None or px.empty or value_col not in px.columns:
        return np.zeros((0, 0)), {}, np.array([], dtype="datetime64[ns]")
    p = px[["code", "date", value_col]].dropna(subset=["code", "date"]).copy()
    p["date"] = as_ts_series(p["date"])
    p = p.dropna(subset=["date"])
    wide = p.pivot_table(index="date", columns="code", values=value_col, aggfunc="last")
    if wide.empty:
        return np.zeros((0, 0)), {}, np.array([], dtype="datetime64[ns]")
    idx = pd.DatetimeIndex(cal) if len(cal) else wide.index
    wide = wide.reindex(idx.union(wide.index)).sort_index().reindex(idx)
    first = wide.notna().cummax()                       # 첫 거래일 이후만 True
    last = wide.notna()[::-1].cummax()[::-1]            # 마지막 거래일 이전만 True
    wide = wide.ffill().where(first & last)
    codes = {c: i for i, c in enumerate(wide.columns)}
    return wide.to_numpy("float64"), codes, wide.index.values.astype("datetime64[ns]")


def _scg_gid(df: pd.DataFrame, cats: Optional[pd.Index] = None
             ) -> Tuple[np.ndarray, pd.Index]:
    """(stock_id, fiscal_period, forecast_metric) → 정수 gid. §5 분석 단위의 유일한 인코딩."""
    key = (df["stock_id"].astype(str) + "\x1f" +
           df["fiscal_period"].astype(str) + "\x1f" +
           df["forecast_metric"].astype(str))
    if cats is None:
        cats = pd.Index(pd.unique(key))
    codes = cats.get_indexer(key.values)
    return codes.astype("int64"), cats


# ══════════════════════════════════════════════════════════════════════════════════════
#  1. Active forecasts (§6) — signal date 별 1인 1표 전망 집합
# ══════════════════════════════════════════════════════════════════════════════════════

def build_active_forecasts(forecasts: pd.DataFrame, signal_dates, cfg: SCGConfig = SCG
                           ) -> pd.DataFrame:
    """§6 — 각 signal date T 에서 유효한 전망만 남긴다.

    규칙: report_date <= T  및  0 <= T - report_date <= MAX_FORECAST_AGE_DAYS,
          동일 (종목·애널·회계기간·메트릭)에서는 가장 최근 1건만.

    ★ PIT: report_date > T 인 전망은 구조적으로 들어올 수 없다(구간 start = report_date).
      report_date 가 미래(수집 시점 기준)인 행은 §32 에 따라 즉시 오류로 처리한다.
    """
    need = set(FORECAST_COLS)
    miss = need - set(forecasts.columns)
    if miss:
        raise KeyError(f"analyst_forecasts 필수 컬럼 누락: {sorted(miss)} "
                       f"(있는 컬럼: {sorted(forecasts.columns)})")

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    n0 = len(f)
    f = f.dropna(subset=["report_date", "forecast_value", "stock_id", "analyst_id"])
    #  §32: forecast 값 NaN → 해당 row 만 제외 (애널리스트를 제거하지 않는다)
    if len(f) < n0:
        LOG.debug(f"전망값/발간일 결측으로 {n0-len(f):,}행 제외 (해당 행만, 애널리스트는 유지)")

    sd = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(signal_dates))).dropna().unique()))
    if len(sd) == 0 or f.empty:
        return pd.DataFrame(columns=["signal_date"] + FORECAST_COLS + ["forecast_age_days"])

    #  §32: report_date 가 마지막 signal date 를 넘어서면 '미래 리포트' — 즉시 오류
    horizon = sd[-1] + pd.Timedelta(days=1)
    future = f["report_date"] > horizon
    if bool(future.any()):
        bad = f.loc[future, ["stock_id", "analyst_id", "report_date"]].head(5)
        raise ValueError(
            f"report_date 가 마지막 signal date({sd[-1].date()}) 이후인 전망이 "
            f"{int(future.sum()):,}건 있습니다 (§32 즉시 오류). 예:\n{bad.to_string(index=False)}")

    v = _scg_validity(f, cfg)
    gid, _ = _scg_gid(v)
    sd_vals = sd.values.astype("datetime64[ns]")

    # 각 전망 구간이 덮는 signal date 들을 한 번에 전개한다 (§6 을 반복문 없이)
    lo = np.searchsorted(sd_vals, v["valid_start"].values.astype("datetime64[ns]"), side="left")
    hi = np.searchsorted(sd_vals, v["valid_end"].values.astype("datetime64[ns]"), side="right")
    cnt = np.maximum(hi - lo, 0)
    total = int(cnt.sum())
    if total == 0:
        return pd.DataFrame(columns=["signal_date"] + FORECAST_COLS + ["forecast_age_days"])

    row = np.repeat(np.arange(len(v), dtype="int64"), cnt)
    off = np.arange(total, dtype="int64") - np.repeat(
        np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt)
    dcol = np.repeat(lo, cnt) + off

    out = pd.DataFrame({
        "signal_date": sd_vals[dcol],
        "stock_id": v["stock_id"].values[row],
        "analyst_id": v["analyst_id"].values[row],
        "broker_id": v["broker_id"].values[row],
        "report_id": v["report_id"].values[row],
        "fiscal_period": v["fiscal_period"].values[row],
        "forecast_metric": v["forecast_metric"].values[row],
        "report_date": v["report_date"].values[row],
        "forecast_value": v["forecast_value"].values[row],
    })
    out["forecast_age_days"] = (out["signal_date"] - out["report_date"]).dt.days.astype("int32")
    #  구성상 보장되지만, 조립 실수를 조용히 넘기지 않기 위해 한 번 더 확인한다
    if bool((out["forecast_age_days"] < 0).any()):
        raise AssertionError("active forecast 에 미래 전망이 섞였습니다 (age < 0) — PIT 위반")
    LOG.debug(f"active forecasts {len(out):,}행 "
              f"({out['signal_date'].nunique()}개 시점 × {out['stock_id'].nunique():,}종목)")
    return out


def compute_equal_consensus(active: pd.DataFrame, cfg: SCGConfig = SCG) -> pd.DataFrame:
    """§6.3 consensus_equal_weight — 단순 산술평균. 비교 기준선이자 SCG 의 분모."""
    if active.empty:
        return pd.DataFrame(columns=["signal_date"] + GROUP_KEY +
                                    ["consensus_equal_weight", "analyst_count", "status"])
    g = active.groupby(["signal_date"] + GROUP_KEY, observed=True, sort=False)
    c = g.agg(consensus_equal_weight=("forecast_value", "mean"),
              analyst_count=("analyst_id", "nunique")).reset_index()
    c["status"] = np.where(c["analyst_count"] >= cfg.MIN_ANALYSTS,
                           STATUS_OK, STATUS_INSUFFICIENT)
    return c


# ══════════════════════════════════════════════════════════════════════════════════════
#  2. Accuracy Event (§7~§8)
# ══════════════════════════════════════════════════════════════════════════════════════

def build_accuracy_events(forecasts: pd.DataFrame, actuals: pd.DataFrame,
                          calendar=None, cfg: SCGConfig = SCG) -> pd.DataFrame:
    """§7~§8 — 각 실적 사건에서 애널리스트가 당시 컨센서스보다 정확했는가.

    ACC_EVENT = clip( log( (NE_C + eps) / (NE_j + eps) ), -2, +2 )
      NE_j = |F_j - A| / Scale,   NE_C = |C - A| / Scale
      Scale = max(|A|, median_j |F_j|, eps)          ← EPS 0 근처 폭발 방지 (§8.1)

    ★ PIT 의 근거는 actual_announcement_date 다. 이 사건은 그 날짜에 '완성'되며,
      §9 는 T 시점에 A_date < T 인 사건만 쓰게 되어 있다. 그 필터는 build_analyst_scores
      에 있고, 여기서는 사건 자체만 만든다.
    ★ §45.3: 공식 V1 의 C 는 자기 자신을 포함한 전체 equal consensus 다.
      leave-one-out 판은 보조 진단(acc_event_loo)으로만 함께 낸다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "actual_announcement_date", "actual_value", "forecast_value",
            "consensus_at_event", "n_analysts", "scale", "ne_analyst", "ne_consensus",
            "acc_event", "acc_event_loo", "report_date", "forecast_age_days"]
    if forecasts is None or forecasts.empty or actuals is None or actuals.empty:
        return pd.DataFrame(columns=cols)

    a = actuals.copy()
    a["actual_announcement_date"] = as_ts_series(a["actual_announcement_date"])
    a["actual_value"] = pd.to_numeric(a["actual_value"], errors="coerce")
    a = a.dropna(subset=["actual_announcement_date", "actual_value"])
    a = a.sort_values("actual_announcement_date").drop_duplicates(
        subset=GROUP_KEY, keep="first")            # 최초 발표만 — 정정공시로 과거를 바꾸지 않는다
    if a.empty:
        return pd.DataFrame(columns=cols)

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    f = f.dropna(subset=["report_date", "forecast_value"])

    m = f.merge(a[GROUP_KEY + ["actual_value", "actual_announcement_date"]],
                on=GROUP_KEY, how="inner")
    if m.empty:
        return pd.DataFrame(columns=cols)

    #  §7 — 실적 발표 '전'에 존재하던 마지막 전망. 발표 당일 전망은 쓰지 않는다(누수).
    age = (m["actual_announcement_date"] - m["report_date"]).dt.days
    m = m[(age > 0) & (age <= int(cfg.ACC_FORECAST_MAX_AGE_DAYS))]
    if m.empty:
        return pd.DataFrame(columns=cols)
    m = m.sort_values(FORECAST_KEY + ["report_date", "report_id"], kind="mergesort")
    m = m.drop_duplicates(subset=FORECAST_KEY, keep="last")     # 애널리스트당 1건 (§2.1)

    g = m.groupby(GROUP_KEY, observed=True, sort=False)["forecast_value"]
    m["n_analysts"] = g.transform("size").astype("int32")
    m["_sum"] = g.transform("sum")
    m["consensus_at_event"] = g.transform("mean")
    m["_median_abs"] = m.groupby(GROUP_KEY, observed=True, sort=False)["forecast_value"] \
                        .transform(lambda s: s.abs().median())

    #  §6.2 와 같은 근거의 유일한 게이트. 1명뿐이면 C == F_j 라 ACC_EVENT 가 항상 0 이고,
    #  그 0 이 n^acc 만 부풀려 λ 를 1 로 밀어올린다(정보 없는 애널이 확신을 얻는 역효과).
    n_pre = len(m)
    m = m[m["n_analysts"] >= cfg.MIN_ANALYSTS]
    if len(m) < n_pre:
        LOG.debug(f"Accuracy: 애널리스트 {cfg.MIN_ANALYSTS}명 미만 사건 {n_pre-len(m):,}건 제외 "
                  f"(§6.2 와 동일 근거. 애널리스트를 제거하는 것이 아니라 사건만 제외)")
    if m.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    A = m["actual_value"].to_numpy("float64")
    F = m["forecast_value"].to_numpy("float64")
    C = m["consensus_at_event"].to_numpy("float64")
    scale = np.maximum.reduce([np.abs(A), m["_median_abs"].to_numpy("float64"),
                               np.full(A.shape, eps)])
    ne_j = np.abs(F - A) / scale
    ne_c = np.abs(C - A) / scale
    m["scale"] = scale
    m["ne_analyst"] = ne_j
    m["ne_consensus"] = ne_c
    m["acc_event"] = np.clip(np.log((ne_c + eps) / (ne_j + eps)),
                             -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)

    #  보조 진단 (§45.3): 자기 자신을 뺀 컨센서스 기준 정확도. 공식 산식은 위쪽이다.
    n = m["n_analysts"].to_numpy("float64")
    c_loo = np.where(n > 1, (m["_sum"].to_numpy("float64") - F) / np.maximum(n - 1, 1), np.nan)
    ne_c_loo = np.abs(c_loo - A) / scale
    m["acc_event_loo"] = np.clip(np.log((ne_c_loo + eps) / (ne_j + eps)),
                                 -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)
    m["forecast_age_days"] = (m["actual_announcement_date"] - m["report_date"]).dt.days.astype("int32")

    out = m[cols].reset_index(drop=True)
    LOG.debug(f"Accuracy 이벤트 {len(out):,}건 "
              f"({out['analyst_id'].nunique():,}명 · 평균 {out['acc_event'].mean():+.3f})")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
#  3. Leadership Event (§11~§16)
# ══════════════════════════════════════════════════════════════════════════════════════

def build_leadership_events(forecasts: pd.DataFrame, calendar, cfg: SCGConfig = SCG
                            ) -> pd.DataFrame:
    """§12~§16 — 내가 전망을 고친 뒤, '나를 뺀' 다른 애널리스트들이 같은 방향으로 따라왔는가.

    LEAD_EVENT = clip( sign(ΔF_j) × ΔC^{-j} / Scale_C , -1, +1 )
      ΔC^{-j} = C^{-j}(t20) - C^{-j}(t0)          ← t20 은 20 '거래일' 후 (§13)
      Scale_C = max( |C^{-j}(t0)|, median|F| at t0, eps )

    ★ leave-one-out 이 이 지표의 전부다 (§13). 자기 전망이 peer consensus 에 남아 있으면
      "내가 올렸으니 컨센서스가 올랐다"는 기계적 자기상관을 측정하게 된다.
      그래서 peer 집합에서 j 를 뺀 근거를 행마다 남긴다(self_in_peer_t0/t20 = False 여야 함).
      §35 TEST 7 은 이 컬럼이 하나라도 True 면 실패시킨다.
    ★ PIT: 이 사건의 '완성 시점'은 t20 이다. §16 에 따라 t20 < T 인 사건만 점수에 쓴다.
      그 필터는 build_analyst_scores 에 있다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "event_date", "outcome_date", "prev_forecast", "new_forecast",
            "revision", "direction", "peer_consensus_t0", "peer_consensus_t20",
            "peer_count_t0", "peer_count_t20", "follow_move", "lead_event",
            "self_in_peer_t0", "self_in_peer_t20"]
    if forecasts is None or forecasts.empty:
        return pd.DataFrame(columns=cols)

    cal = _scg_trading_calendar(calendar)
    if cal.size == 0:
        LOG.warn("거래일 캘린더가 비어 Leadership 이벤트를 만들 수 없습니다 — LEAD* 는 전부 0 "
                 "으로 수축됩니다(애널리스트는 유지). SCG_LS 는 사실상 SCG_0 와 같아집니다.")
        return pd.DataFrame(columns=cols)

    f = forecasts.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f["forecast_value"] = pd.to_numeric(f["forecast_value"], errors="coerce")
    f = f.dropna(subset=["report_date", "forecast_value"])
    if f.empty:
        return pd.DataFrame(columns=cols)

    v = _scg_validity(f, cfg).reset_index(drop=True)
    gid, cats = _scg_gid(v)
    v["_gid"] = gid

    # ── 리비전 사건: 같은 (종목·애널·기간·메트릭)의 연속된 두 전망 (§12) ──────────────
    v = v.sort_values(FORECAST_KEY + ["report_date"], kind="mergesort").reset_index(drop=True)
    grp = v.groupby(FORECAST_KEY, observed=True, sort=False)["forecast_value"]
    v["prev_forecast"] = grp.shift(1)
    ev = v[v["prev_forecast"].notna()].copy()
    #  §12: 변화가 완전히 0 이면 사건을 만들지 않는다. 크기 하한(5%,10%)은 두지 않는다 —
    #  미세한 리비전은 산식에서 자연스럽게 영향력이 작아진다.
    ev = ev[ev["forecast_value"] != ev["prev_forecast"]]
    if ev.empty:
        return pd.DataFrame(columns=cols)

    ev["event_date"] = ev["report_date"]
    ev["outcome_date"] = _scg_shift_td(ev["event_date"], int(cfg.LEAD_FORWARD_TRADING_DAYS), cal)
    ev = ev[ev["outcome_date"].notna()].copy()          # 캘린더 끝을 넘으면 결과 관측 불가
    if ev.empty:
        return pd.DataFrame(columns=cols)

    # ── t0 / t20 시점의 활성 전망 집합 (§13) ────────────────────────────────────────
    iv_gid = v["_gid"].to_numpy("int64")
    iv_s = v["valid_start"].values.astype("datetime64[ns]")
    iv_e = v["valid_end"].values.astype("datetime64[ns]")
    iv_val = v["forecast_value"].to_numpy("float64")
    iv_ana = v["analyst_id"].astype(str).to_numpy()

    n_ev = len(ev)
    q_gid = np.concatenate([ev["_gid"].to_numpy("int64")] * 2)
    q_time = np.concatenate([ev["event_date"].values.astype("datetime64[ns]"),
                             ev["outcome_date"].values.astype("datetime64[ns]")])
    q_owner = np.concatenate([ev["analyst_id"].astype(str).to_numpy()] * 2)

    qi, ii = _scg_stab(iv_gid, iv_s, iv_e, q_gid, q_time,
                       max_span_days=int(cfg.MAX_FORECAST_AGE_DAYS) + 1)
    if qi.size == 0:
        return pd.DataFrame(columns=cols)

    #  ★ leave-one-out 의 실행 지점: 소유자 j 의 전망을 peer 집합에서 물리적으로 제거한다.
    is_self = (iv_ana[ii] == q_owner[qi])
    peer = ~is_self
    qp, ip = qi[peer], ii[peer]

    n_q = q_gid.size
    peer_cnt = np.bincount(qp, minlength=n_q).astype("float64")
    peer_sum = np.bincount(qp, weights=iv_val[ip], minlength=n_q)
    with np.errstate(invalid="ignore", divide="ignore"):
        peer_mean = np.where(peer_cnt > 0, peer_sum / peer_cnt, np.nan)

    #  Scale_C 의 median|F| (§14) — peer 집합 기준. 정확한 중앙값을 쓴다(평균 대체 금지).
    med_abs = np.full(n_q, np.nan)
    if ip.size:
        dfm = pd.DataFrame({"q": qp, "av": np.abs(iv_val[ip])})
        mm = dfm.groupby("q", sort=True)["av"].median()
        med_abs[mm.index.to_numpy()] = mm.to_numpy()

    #  자기 전망이 정말로 빠졌는지의 증거 (§35 TEST 7 이 읽는 컬럼)
    self_cnt = np.bincount(qi[is_self], minlength=n_q)

    t0s, t20s = slice(0, n_ev), slice(n_ev, 2 * n_ev)
    ev["peer_consensus_t0"] = peer_mean[t0s]
    ev["peer_consensus_t20"] = peer_mean[t20s]
    ev["peer_count_t0"] = peer_cnt[t0s].astype("int32")
    ev["peer_count_t20"] = peer_cnt[t20s].astype("int32")
    ev["self_in_peer_t0"] = False                      # 위에서 물리적으로 제거했으므로 항상 False
    ev["self_in_peer_t20"] = False
    ev["_self_seen_t0"] = self_cnt[t0s]                # 진단용: j 가 그 시점에 활성이었는가
    ev["_self_seen_t20"] = self_cnt[t20s]
    med0 = med_abs[t0s]

    #  §15 — t0/t20 양쪽에서 peer 가 최소 1명. 미충족이면 그 사건만 버린다(애널은 유지).
    n_pre = len(ev)
    ok = (ev["peer_count_t0"] >= 1) & (ev["peer_count_t20"] >= 1) & \
         ev["peer_consensus_t0"].notna() & ev["peer_consensus_t20"].notna()
    med0 = med0[ok.to_numpy()]
    ev = ev[ok].copy()
    if len(ev) < n_pre:
        LOG.debug(f"Leadership: peer 부족(§15)으로 사건 {n_pre-len(ev):,}건 제외 "
                  f"— 애널리스트는 유지됩니다")
    if ev.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    c0 = ev["peer_consensus_t0"].to_numpy("float64")
    c20 = ev["peer_consensus_t20"].to_numpy("float64")
    med0 = np.nan_to_num(med0, nan=0.0)
    scale_c = np.maximum.reduce([np.abs(c0), med0, np.full(c0.shape, eps)])

    fnew = ev["forecast_value"].to_numpy("float64")
    fold = ev["prev_forecast"].to_numpy("float64")
    scale_r = np.maximum.reduce([np.abs(fold), med0, np.full(fold.shape, eps)])

    ev["revision"] = (fnew - fold) / scale_r           # §12 (진단용 — 게이트로 쓰지 않는다)
    ev["direction"] = np.sign(fnew - fold)
    ev["follow_move"] = (c20 - c0) / scale_c
    ev["lead_event"] = np.clip(ev["direction"].to_numpy("float64") * ev["follow_move"].to_numpy("float64"),
                               -cfg.LEAD_EVENT_CLIP, cfg.LEAD_EVENT_CLIP)
    ev["new_forecast"] = fnew

    out = ev[cols].reset_index(drop=True)
    LOG.debug(f"Leadership 이벤트 {len(out):,}건 "
              f"({out['analyst_id'].nunique():,}명 · 평균 {out['lead_event'].mean():+.4f})")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
#  4. 애널리스트 PIT 점수 (§9~§10, §17~§18)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_roll_scores(ev: pd.DataFrame, date_col: str, val_col: str,
                     signal_dates: pd.DatetimeIndex, halflife: float,
                     lookback_years: float, K: float, prior: float,
                     tag: str) -> pd.DataFrame:
    """signal date 마다 '그 시점 이전에 완성된' 사건만으로 시간가중 평균 + 수축을 계산한다.

    ★ 여기가 §45.5(전체기간 점수 금지)의 실행 지점이다. 전 구간 평균을 한 번 구해
      모든 시점에 뿌리는 구현은 미래누수이며, 이 함수는 구조적으로 그것을 할 수 없다:
      사건을 완료일로 정렬해 두고, 각 T 마다 [T-lookback, T) **슬라이스만** 본다.
      슬라이스의 오른쪽 끝이 searchsorted(..., side="left") 이므로 T 당일 사건도 빠진다.

    반환 컬럼: signal_date, analyst_id, {tag}_raw, {tag}_n, {tag}_lambda, {tag}_star
    """
    cols = ["signal_date", "analyst_id", f"{tag}_raw", f"{tag}_n",
            f"{tag}_lambda", f"{tag}_star"]
    if ev is None or ev.empty or len(signal_dates) == 0:
        return pd.DataFrame(columns=cols)
    e = ev[[date_col, val_col, "analyst_id"]].dropna()
    if e.empty:
        return pd.DataFrame(columns=cols)

    e = e.sort_values(date_col, kind="mergesort")
    d = e[date_col].values.astype("datetime64[ns]")
    x = e[val_col].to_numpy("float64")
    acodes, auniq = pd.factorize(e["analyst_id"].astype(str), sort=True)
    n_a = len(auniq)
    day = d.astype("datetime64[D]").astype("int64").astype("float64")
    lb = int(round(365.25 * float(lookback_years)))

    parts: List[pd.DataFrame] = []
    for T in signal_dates:
        lo = int(np.searchsorted(d, np.datetime64(T - pd.Timedelta(days=lb), "ns"), side="left"))
        hi = int(np.searchsorted(d, np.datetime64(T, "ns"), side="left"))   # 엄격히 T 이전
        if hi <= lo:
            continue
        t_day = float(np.datetime64(T, "D").astype("int64"))
        #  w = 2^(-age/H). 슬라이스 안에서만 계산하므로 미래 사건은 존재 자체가 불가능하다.
        w = np.exp2(-(t_day - day[lo:hi]) / float(halflife))
        ac = acodes[lo:hi]
        nn = np.bincount(ac, minlength=n_a)
        act = np.nonzero(nn)[0]
        if act.size == 0:
            continue
        sw = np.bincount(ac, weights=w, minlength=n_a)[act]
        swx = np.bincount(ac, weights=w * x[lo:hi], minlength=n_a)[act]
        n_act = nn[act].astype("float64")
        raw = np.where(sw > 0, swx / np.where(sw > 0, sw, 1.0), 0.0)
        lam = n_act / (n_act + float(K))
        parts.append(pd.DataFrame({
            "signal_date": np.repeat(np.datetime64(T, "ns"), act.size),
            "analyst_id": auniq[act],
            f"{tag}_raw": raw,
            f"{tag}_n": n_act.astype("int32"),
            f"{tag}_lambda": lam,
            f"{tag}_star": lam * raw + (1.0 - lam) * float(prior),
        }))
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat(parts, ignore_index=True)[cols]


def build_analyst_scores(signal_dates, accuracy_events: pd.DataFrame,
                         leadership_events: pd.DataFrame, cfg: SCGConfig = SCG
                         ) -> pd.DataFrame:
    """§9~§10, §17~§18 — signal date 별 ACC*, LEAD*, Q. §33 analyst_score_history 그대로.

    이력이 없는 애널리스트는 여기에 행이 없고, 하류에서 0 으로 채워진다(§32).
    "행이 없다 = 탈락"이 아니라 "행이 없다 = 중립"이다. 이 구분이 이 전략의 전부다.
    """
    cols = ["signal_date", "analyst_id", "acc_raw", "acc_n", "acc_lambda", "acc_star",
            "lead_raw", "lead_n", "lead_lambda", "lead_star", "quality_score_ls",
            "quality_score_scg0"]
    sd = pd.DatetimeIndex(sorted(pd.DatetimeIndex(as_ts_series(pd.Series(signal_dates))).dropna().unique()))
    if len(sd) == 0:
        return pd.DataFrame(columns=cols)

    #  ★ PIT 의 두 근거 날짜가 서로 다르다는 점이 중요하다.
    #     Accuracy   → actual_announcement_date (실적이 발표된 날 사건이 완성된다)
    #     Leadership → outcome_date = t20        (20거래일 뒤 추종 여부가 확정된다)
    acc = _scg_roll_scores(accuracy_events, "actual_announcement_date", "acc_event", sd,
                           cfg.ACCURACY_HISTORY_HALFLIFE_DAYS, cfg.ANALYST_HISTORY_YEARS,
                           cfg.K_ACC, cfg.ACC_PRIOR, tag="acc")
    lead = _scg_roll_scores(leadership_events, "outcome_date", "lead_event", sd,
                            cfg.LEAD_HISTORY_HALFLIFE_DAYS, cfg.ANALYST_HISTORY_YEARS,
                            cfg.K_LEAD, cfg.LEAD_PRIOR, tag="lead")
    if acc.empty and lead.empty:
        return pd.DataFrame(columns=cols)

    #  outer join — Accuracy 만 있거나 Leadership 만 있는 애널리스트도 남긴다 (§32).
    #  없는 쪽은 0 으로 채운다: "이력 없음 = 중립" 이지 "탈락" 이 아니다.
    S = acc.merge(lead, on=["signal_date", "analyst_id"], how="outer")
    for c, v in (("acc_raw", 0.0), ("acc_n", 0), ("acc_lambda", 0.0), ("acc_star", 0.0),
                 ("lead_raw", 0.0), ("lead_n", 0), ("lead_lambda", 0.0), ("lead_star", 0.0)):
        if c not in S.columns:
            S[c] = v
        S[c] = S[c].fillna(v)
    S["quality_score_ls"] = cfg.ACC_WEIGHT * S["acc_star"] + cfg.LEAD_WEIGHT * S["lead_star"]
    S["quality_score_scg0"] = S["acc_star"]              # §21 — Leadership 미사용
    LOG.debug(f"애널리스트 점수 {len(S):,}행 ({S['analyst_id'].nunique():,}명 × {len(sd)}시점)")
    return S[cols]


# ══════════════════════════════════════════════════════════════════════════════════════
#  5. Smart Consensus (§19~§23)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_multiplier(q: np.ndarray, cfg: SCGConfig) -> np.ndarray:
    """§20 — clip(exp(0.7·Q), 0.5, 2.0). 어떤 애널리스트도 weight=0 이 되지 않는다."""
    return np.clip(np.exp(cfg.QUALITY_EXP_SCALE * q),
                   cfg.QUALITY_MULTIPLIER_MIN, cfg.QUALITY_MULTIPLIER_MAX)


def compute_smart_consensus(active_forecasts: pd.DataFrame, analyst_scores: pd.DataFrame,
                            cfg: SCGConfig = SCG) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """§19~§23 — Recency × Quality 로 가중한 자체 컨센서스.

    반환: (smart_consensus, analyst_forecast_weights)  ← §33 의 두 산출물 그대로
    """
    wcols = ["signal_date", "stock_id", "fiscal_period", "forecast_metric", "analyst_id",
             "forecast_value", "report_date", "forecast_age_days", "recency_weight",
             "acc_star", "lead_star", "quality_score_scg0", "quality_score_ls",
             "quality_multiplier_scg0", "quality_multiplier_ls", "weight_scg0", "weight_ls"]
    ccols = ["signal_date"] + GROUP_KEY + ["analyst_count", "consensus_equal_weight",
             "smart_consensus_scg0", "smart_consensus_ls", "status"]
    if active_forecasts is None or active_forecasts.empty:
        return pd.DataFrame(columns=ccols), pd.DataFrame(columns=wcols)

    W = active_forecasts.copy()
    if analyst_scores is not None and len(analyst_scores):
        W = W.merge(analyst_scores[["signal_date", "analyst_id", "acc_star", "lead_star"]],
                    on=["signal_date", "analyst_id"], how="left")
    else:
        W["acc_star"] = np.nan
        W["lead_star"] = np.nan
    #  §32 — 이력이 없으면 0. 결측을 '없음'이 아니라 '중립'으로 읽는다. 탈락시키지 않는다.
    W["acc_star"] = W["acc_star"].fillna(0.0)
    W["lead_star"] = W["lead_star"].fillna(0.0)

    W["recency_weight"] = _scg_halflife_weight(W["forecast_age_days"].to_numpy(),
                                               cfg.FORECAST_HALFLIFE_DAYS)
    W["quality_score_scg0"] = W["acc_star"]                                    # §21
    W["quality_score_ls"] = cfg.ACC_WEIGHT * W["acc_star"] + cfg.LEAD_WEIGHT * W["lead_star"]  # §22
    W["quality_multiplier_scg0"] = _scg_multiplier(W["quality_score_scg0"].to_numpy("float64"), cfg)
    W["quality_multiplier_ls"] = _scg_multiplier(W["quality_score_ls"].to_numpy("float64"), cfg)
    W["weight_scg0"] = W["recency_weight"] * W["quality_multiplier_scg0"]
    W["weight_ls"] = W["recency_weight"] * W["quality_multiplier_ls"]

    W["_v0"] = W["weight_scg0"] * W["forecast_value"]
    W["_vls"] = W["weight_ls"] * W["forecast_value"]
    g = W.groupby(["signal_date"] + GROUP_KEY, observed=True, sort=False)
    C = g.agg(analyst_count=("analyst_id", "nunique"),
              consensus_equal_weight=("forecast_value", "mean"),
              _w0=("weight_scg0", "sum"), _wls=("weight_ls", "sum"),
              _v0=("_v0", "sum"), _vls=("_vls", "sum")).reset_index()

    eps = float(cfg.EPSILON)
    C["smart_consensus_scg0"] = C["_v0"] / C["_w0"].where(C["_w0"].abs() > eps)
    C["smart_consensus_ls"] = C["_vls"] / C["_wls"].where(C["_wls"].abs() > eps)
    C["status"] = np.where(C["analyst_count"] >= cfg.MIN_ANALYSTS, STATUS_OK, STATUS_INSUFFICIENT)
    C = C.drop(columns=["_w0", "_wls", "_v0", "_vls"])
    W = W.drop(columns=["_v0", "_vls"])
    return C[ccols], W[wcols]


# ══════════════════════════════════════════════════════════════════════════════════════
#  6. Smart Gap · Acceleration · Rank (§24~§29)
# ══════════════════════════════════════════════════════════════════════════════════════

def _scg_winsorize(s: pd.Series, lo: float, hi: float, min_n: int) -> pd.Series:
    """§24 — 단면 1%/99% 윈저라이즈. 표본이 작으면 손대지 않는다(작은 단면에서의
    분위수는 극단치 제거가 아니라 그냥 데이터 파괴다)."""
    v = s.dropna()
    if len(v) < min_n:
        return s
    a, b = v.quantile(lo), v.quantile(hi)
    return s.clip(lower=a, upper=b)


def build_scg_signals(smart_consensus: pd.DataFrame, calendar, cfg: SCGConfig = SCG
                      ) -> pd.DataFrame:
    """§24~§29 — SCG, Acceleration, BASE_REV, 단면 rank, 최종 알파.

    ★ 분모 안정화(§24)가 이 전략의 숨은 급소다. EPS 는 0 을 자유롭게 통과하므로
      단순 |C| 분모는 적자↔흑자 전환 종목에서 갭을 무한대로 날려보낸다.
      단면 median|C| 의 10% 를 바닥으로 깔아 그 폭발을 막는다.
    ★ §30: 네 전략(BASE_REV / SCG_0 / SCG_LS / SCG_LSA)은 같은 행에서 나란히 나온다.
      universe 를 전략별로 다르게 만들 여지 자체를 두지 않는다.
    """
    ocols = ["signal_date"] + GROUP_KEY + [
        "analyst_count", "status", "consensus_equal_weight",
        "smart_consensus_scg0", "smart_consensus_ls",
        "denominator", "scg0", "scg_ls", "scg_accel_20d", "base_revision_20d",
        "rank_base_rev", "rank_scg0", "rank_scg_ls", "rank_scg_accel",
        "alpha_ls", "alpha_lsa"]
    if smart_consensus is None or smart_consensus.empty:
        return pd.DataFrame(columns=ocols)

    D = smart_consensus.copy()
    D["signal_date"] = as_ts_series(D["signal_date"])
    #  §6.2 — 2명 미만은 Smart Gap 을 계산하지 않는다. 행은 남기되 값은 NaN 이다
    #  (조용히 사라지면 §35 TEST 9 표본보존 검사가 무의미해진다).
    ok = D["status"].eq(STATUS_OK)
    eps = float(cfg.EPSILON)

    #  단면 floor: 같은 (시점 · 회계기간 · 메트릭) 안에서만 비교한다 (§45.2)
    xs = ["signal_date", "fiscal_period", "forecast_metric"]
    med_abs = (D.loc[ok].assign(_a=D.loc[ok, "consensus_equal_weight"].abs())
                 .groupby(xs, observed=True)["_a"].median().rename("_med_abs"))
    D = D.merge(med_abs, on=xs, how="left")
    floor = cfg.DENOM_FLOOR_RATIO * D["_med_abs"].fillna(0.0)
    D["denominator"] = np.maximum.reduce([
        D["consensus_equal_weight"].abs().to_numpy("float64"),
        floor.to_numpy("float64"), np.full(len(D), eps)])

    D["scg0"] = np.where(ok, (D["smart_consensus_scg0"] - D["consensus_equal_weight"]) / D["denominator"], np.nan)
    D["scg_ls"] = np.where(ok, (D["smart_consensus_ls"] - D["consensus_equal_weight"]) / D["denominator"], np.nan)

    #  §24 극단치 처리 — 단면별 윈저라이즈
    for c in ("scg0", "scg_ls"):
        D[c] = D.groupby(xs, observed=True, sort=False)[c].transform(
            lambda s: _scg_winsorize(s, cfg.WINSOR_LOWER, cfg.WINSOR_UPPER,
                                     cfg.MIN_CROSS_SECTION_FOR_WINSOR))

    # ── 20거래일 전 값 참조 (§25 accel, §29 BASE_REV) ────────────────────────────────
    #  달력일이 아니라 거래일이므로, 캘린더에서 t-20 세션 날짜를 구한 뒤
    #  그 이하의 가장 가까운 signal date 를 asof 로 붙인다. (월말 그리드면 보통 전월말)
    cal = _scg_trading_calendar(calendar)
    sd = pd.DatetimeIndex(sorted(D["signal_date"].dropna().unique()))
    back = _scg_shift_td(sd, -int(cfg.ACCEL_LOOKBACK_TRADING_DAYS), cal)
    sdv = sd.values.astype("datetime64[ns]")
    #  ★ '가장 가까운' signal date 를 쓴다. '이하 중 최대' 로 하면 거래일이 21일 미만인
    #    달에서 t-20 이 직전 시점보다 살짝 앞서 두 칸 전으로 미끄러지고, 그 달의
    #    accel 과 BASE_REV 가 조용히 40거래일 변화가 된다(값은 나오는데 정의가 다르다).
    lo = np.searchsorted(sdv, back, side="right") - 1
    hi = np.minimum(lo + 1, len(sdv) - 1)
    lo_c = np.clip(lo, 0, len(sdv) - 1)
    d_lo = np.abs(sdv[lo_c].astype("int64") - back.astype("datetime64[ns]").astype("int64"))
    d_hi = np.abs(sdv[hi].astype("int64") - back.astype("datetime64[ns]").astype("int64"))
    pick = np.where((lo >= 0) & (d_lo <= d_hi), lo_c, hi)
    prev_map = pd.Series(
        [sd[p] if (not pd.isna(b)) else pd.NaT for p, b in zip(pick, back)],
        index=sd, name="_prev_sd")
    #  자기 자신을 가리키면(캘린더가 짧아 t-20 이 t 이후로 계산되는 경우) 무효 처리
    prev_map = prev_map.where(prev_map < pd.Series(sd, index=sd))

    D["_prev_sd"] = D["signal_date"].map(prev_map)
    prev = D[["signal_date"] + GROUP_KEY + ["scg_ls", "consensus_equal_weight", "denominator"]].rename(
        columns={"signal_date": "_prev_sd", "scg_ls": "_scg_ls_prev",
                 "consensus_equal_weight": "_c_prev", "denominator": "_den_prev"})
    D = D.merge(prev, on=["_prev_sd"] + GROUP_KEY, how="left")

    D["scg_accel_20d"] = D["scg_ls"] - D["_scg_ls_prev"]      # §25 — 없으면 NaN (종목은 유지)
    den_prev = np.maximum.reduce([
        D["_c_prev"].abs().to_numpy("float64"),
        D["_den_prev"].fillna(0.0).to_numpy("float64"),
        np.full(len(D), eps)])
    D["base_revision_20d"] = np.where(
        D["_c_prev"].notna() & ok,
        (D["consensus_equal_weight"] - D["_c_prev"]) / den_prev, np.nan)   # §29

    # ── §26 단면 percentile rank ────────────────────────────────────────────────────
    def _rank(col: str) -> pd.Series:
        return D.groupby(xs, observed=True, sort=False)[col].rank(method="average", pct=True)

    D["rank_base_rev"] = _rank("base_revision_20d")
    D["rank_scg0"] = _rank("scg0")
    D["rank_scg_ls"] = _rank("scg_ls")
    D["rank_scg_accel"] = _rank("scg_accel_20d")

    D["alpha_ls"] = D["rank_scg_ls"]                                          # §27
    accel_r = D["rank_scg_accel"].fillna(cfg.NEUTRAL_ACCEL_RANK)              # §28 중립 처리
    D["alpha_lsa"] = np.where(
        D["rank_scg_ls"].notna(),
        cfg.SCG_LEVEL_WEIGHT * D["rank_scg_ls"] + cfg.SCG_ACCEL_WEIGHT * accel_r,
        np.nan)

    LOG.debug(f"SCG 신호 {len(D):,}행 · 유효 {int(ok.sum()):,}행 "
              f"({D.loc[ok, 'signal_date'].nunique()}시점)")
    return D[ocols]


#  §30 — 네 전략의 알파 점수 컬럼. universe 는 하나이고 컬럼만 다르다.
STRATEGY_ALPHA_COLS = {
    "BASE_REV": "rank_base_rev",
    "SCG_0":    "rank_scg0",
    "SCG_LS":   "alpha_ls",
    "SCG_LSA":  "alpha_lsa",
}



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  analyst_forecasts 조립 — 명세 §2.1 의 표준 스키마를 실제 데이터로 채운다             ║
# ║                                                                                          ║
# ║  두 개의 메트릭 트랙을 만든다. 절대 섞지 않는다(§45.2 와 같은 이유).                         ║
# ║                                                                                          ║
# ║   ① EPS — 명세의 원형. 리포트 PDF 1면 '실적 추정표'에서 기하학적으로 추출한다.               ║
# ║          실측치 A = DART 주당이익 (없으면 지배주주순이익/주식수).                            ║
# ║   ② TP  — 목표주가. 한경 리스트 컬럼에 직접 있어 커버리지가 압도적이다.                      ║
# ║          실측치 A = 수정주가 기준 12개월 후 실제 주가.                                      ║
# ║                                                                                          ║
# ║  ★★ 이 파일에서 가장 중요한 경고 ★★                                                       ║
# ║   EPS 추출 실패는 무작위가 아니라 **증권사 템플릿별**로 발생한다. 즉 파서가 못 읽는 템플릿을  ║
# ║   쓰는 증권사의 애널리스트는 n^acc 이 작아 전원 0 으로 수축되고, 결과적으로 '실력'이 아니라  ║
# ║   'PDF 양식'으로 가중치가 갈린다. 이것은 조용한 선택편향이다.                                ║
# ║   → 그래서 증권사×연도 추출률 표를 반드시 출력하고, 추출률이 바닥인 증권사를 명시한다.       ║
# ║   → 그래서 TP 트랙을 같이 산출해 EPS 트랙 결론을 교차검증한다.                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EPS_PARSER_VERSION = "1.1"          # 올리면 이전 실패건을 자동으로 재파싱한다
EPS_TABLE = "analyst_eps_forecasts"          # 공용 인덱스 (다른 전략도 그대로 재사용)
EPS_STATUS_TABLE = "analyst_eps_extract_status"
FORECAST_ATTRIBUTION = "lead"       # "lead" = 대표저자 1인 | "all" = 공저자 전원

#  한 리포트 = 한 하우스뷰. 공저자 3명에게 같은 숫자로 3표를 주면 그 증권사가
#  equal-weight 컨센서스를 3배로 밀게 된다. 기본값이 "lead" 인 이유다.

# ── 숫자 파싱 ───────────────────────────────────────────────────────────────────────────────
#  △ 는 한국 재무자료에서 마이너스다. ▲/▼ 는 증감방향 표기라 부호로 쓰지 않는다.
_NEG_MARKS = ("△", "▵", "-", "−", "–", "—", "▲-")
_EPS_PLACEHOLDER = {
    "적전": "L2L", "적지": "L2L", "적자지속": "L2L", "적자전환": "L2L",
    "흑전": "L2P", "흑지": "L2P", "흑자전환": "L2P", "흑자지속": "L2P",
    "n/a": "NA", "na": "NA", "nm": "NA", "n.a.": "NA", "-": "NA", "—": "NA",
    "–": "NA", "": "NA", "적": "NA", "흑": "NA",
}
_NUM_RE = re.compile(r"^[\(\[]?\s*([△▵▲▼\-−–—+]?)\s*([0-9][0-9,\.]*)\s*[\)\]]?$")


def _eps_num(tok: str) -> Tuple[Optional[float], str]:
    """숫자 셀 → (값, 분류). 적전/흑전/n.a. 는 **0 이 아니라 결측**이다.

    ★ 이 구분이 중요한 이유: '적전'을 0.0 으로 읽으면 그 종목의 컨센서스 평균이
      실제보다 위로 끌려 올라가고, 그 오차가 그대로 Smart Gap 의 분자가 된다.
      (코드베이스가 이미 겪은 적정가격 "0" → int("0") 사고와 같은 부류다)
    """
    s = str(tok).strip().replace(" ", "")
    if not s:
        return None, "NA"
    low = s.lower()
    if low in _EPS_PLACEHOLDER:
        return None, _EPS_PLACEHOLDER[low]
    neg = s.startswith(("(", "[")) and s.endswith((")", "]"))
    m = _NUM_RE.match(s)
    if not m:
        return None, "NA"
    sign, body = m.group(1), m.group(2).replace(",", "")
    if body.count(".") > 1:
        return None, "NA"
    try:
        v = float(body)
    except ValueError:
        return None, "NA"
    if sign in ("△", "▵", "-", "−", "–", "—") or neg:
        v = -v
    return v, "NUM"


# ── 연도 헤더 ───────────────────────────────────────────────────────────────────────────────
#  ★ 2자리 연도는 반드시 표식(', FY, 년, 또는 E/F/P/A 접미사)이 있어야 인정한다.
#    맨 두 자리 숫자까지 연도로 받으면 '12 15 18' 같은 평범한 숫자 행이 헤더로 오인되고,
#    그 아래 EPS 행이 엉뚱한 연도에 붙는다 — 예외 없이 조용히 틀린다.
#  ★ 2024.12 / 24/12 같은 결산월 포함 표기도 받는다(한국 리포트에서 흔하다).
_YEAR_RE = re.compile(
    r"^\(?(?:FY|fy)?"
    r"(?:(?P<y4>(?:19|20)\d{2})|(?:'|FY|fy)(?P<y2q>\d{2})|(?P<y2>\d{2})(?=[A-Za-z년]))"
    r"(?:[./-](?P<m>0?[1-9]|1[0-2]))?"
    r"\)?(?:년|년도|년말|월)?"
    r"(?:\((?P<s1>[AEFPaefp])\)|(?P<s2>[AEFPaefp])|(?P<s3>예상|추정|실적|확정))?$")
_SUFFIX_ROW_OK = {"e", "f", "p", "a", "(e)", "(f)", "(p)", "(a)",
                  "십억원", "억원", "백만원", "원", "%", "배", "천원"}
_FYEAR_MONTH_RE = re.compile(r"(\d{1,2})\s*월")

#  EPS 행 라벨: 완전일치로 앵커한다. re.search 로 하면 'EPS 증가율' 이 걸린다.
_EPS_OK_RE = re.compile(
    r"^(?:\(?(?:수정|조정|Adj\.?|adj\.?)\)?)?\s*"
    r"(?:지배주주|지배지분|보통주|희석|기본|연결|별도)?\s*"
    r"(?:EPS|eps|주당순이익|주당이익|주당순손익)\s*"
    r"(?:\(원\)|\(₩\)|\(krw\)|\(원\,?\s*\)|원)?\s*$")
_EPS_BAD_RE = re.compile(
    r"증가율|성장률|증감|감소|YoY|yoy|CAGR|cagr|배수|배\)|%|BPS|bps|DPS|dps|"
    r"SPS|CPS|EBITDA|PER|per|P/E|PBR|주가|목표|배당|수익률|비율", re.I)


def _eps_rows_from_words(words: Sequence[Sequence], ytol: float = 2.2) -> List[List[Tuple]]:
    """단어 8-튜플을 y 밴드로 묶어 '행'을 만든다.

    ★ find_tables() 는 쓰지 않는다. 한국 증권사 요약표는 세로 괘선이 없거나
      아예 괘선이 없어 표 인식기가 0개를 반환한다(검증됨). 좌표로 직접 재구성한다.
    """
    ws = sorted(words, key=lambda w: (round(float(w[1]), 1), float(w[0])))
    rows: List[List[Tuple]] = []
    cur: List[Tuple] = []
    cy = None
    for w in ws:
        ym = (float(w[1]) + float(w[3])) / 2.0
        if cy is None:
            cur, cy = [w], ym
        elif abs(ym - cy) <= ytol:
            cur.append(w)
            cy = (cy * (len(cur) - 1) + ym) / len(cur)
        else:
            rows.append(sorted(cur, key=lambda t: float(t[0])))
            cur, cy = [w], ym
    if cur:
        rows.append(sorted(cur, key=lambda t: float(t[0])))
    return rows


def _eps_cells(row: Sequence[Tuple], gap: float = 3.0) -> List[Tuple[float, float, str]]:
    """행의 단어들을 x 간격으로 셀로 병합. 반환 (x0, x1, text).

    ★ 숫자끼리는 절대 병합하지 않는다. 우측정렬된 두 숫자의 박스가 겹치는 경우가 있어
      그대로 두면 "1,234" + "5,678" → "1,2345,678" 이 된다(재현 확인된 사고).
    """
    out: List[List[Any]] = []
    for w in row:
        x0, x1, t = float(w[0]), float(w[2]), str(w[4])
        if out:
            p = out[-1]
            #  ★ 셀 전체가 아니라 '마지막에 붙은 토큰' 으로 판정해야 한다. 셀이
            #    '(원)' 처럼 비숫자로 시작하면 셀 전체는 영영 NUM 이 아니게 되어
            #    가드가 죽고, 그 뒤 숫자들이 전부 한 셀로 뭉쳐 '1,2345,678' 이 된다.
            both_num = _eps_num(p[3])[1] == "NUM" and _eps_num(t)[1] == "NUM"
            if (x0 - p[1]) < gap and not both_num:
                p[1] = max(p[1], x1)
                p[2] = p[2] + t
                p[3] = t                      # 마지막 토큰 기억
                continue
        out.append([x0, x1, t, t])
    return [(c[0], c[1], c[2].strip()) for c in out]


def _eps_parse_header(cells: List[Tuple[float, float, str]]
                      ) -> Optional[List[Dict[str, Any]]]:
    """연도 헤더 행이면 [{year, suffix, xc}, ...] 를 돌려준다.

    ★ 연도 토큰 3개 이상 + 순증가 + 중복없음 을 요구한다. 2개로 낮추면
      '2024F 기존 / 2024F 수정 / 변동률' 같은 추정치 변경표가 헤더로 오인된다.
    """
    ys = []
    for x0, x1, t in cells:
        m = _YEAR_RE.match(t.replace(" ", ""))
        if not m:
            continue
        g = m.groupdict()
        raw = g.get("y4") or g.get("y2q") or g.get("y2")
        if not raw:
            continue
        y = int(raw)
        if y < 100:
            y += 2000
        if not (1990 <= y <= 2100):
            continue
        suf = (g.get("s1") or g.get("s2") or g.get("s3") or "").upper()
        ys.append({"year": y, "suffix": suf, "xc": (x0 + x1) / 2.0,
                   "fmonth": int(g["m"]) if g.get("m") else None})
    if len(ys) < 3:
        return None
    yrs = [d["year"] for d in ys]
    if len(set(yrs)) != len(yrs) or any(b <= a for a, b in zip(yrs, yrs[1:])):
        return None
    return ys


def _eps_merge_suffix_row(hdr: List[Dict[str, Any]],
                          cells: List[Tuple[float, float, str]]) -> bool:
    """헤더 바로 아래가 'E F F' 나 '(십억원)' 같은 보조행이면 헤더에 흡수한다."""
    toks = [c[2].strip().lower() for c in cells if c[2].strip()]
    if not toks or not all(t in _SUFFIX_ROW_OK for t in toks):
        return False
    for x0, x1, t in cells:
        tt = t.strip().upper().strip("()")
        if tt not in ("E", "F", "P", "A"):
            continue
        xc = (x0 + x1) / 2.0
        near = min(hdr, key=lambda d: abs(d["xc"] - xc))
        if not near["suffix"]:
            near["suffix"] = tt
    return True


def _eps_map_to_years(hdr: List[Dict[str, Any]],
                      cells: List[Tuple[float, float, str]]) -> Dict[int, Tuple[float, str]]:
    """값 셀을 x 중심 근접도로 연도 컬럼에 붙인다.

    ★ 위치 zip 을 절대 쓰지 않는다. 값이 하나 비면(적전이 빈 셀로 렌더되는 등)
      그 뒤 모든 값이 한 칸씩 밀려 전 연도의 EPS 가 통째로 어긋난다 — 예외도 안 난다.
      매칭 실패는 '빈 값'으로 두지, 이웃으로 당겨오지 않는다.
    """
    if len(hdr) < 2:
        return {}
    xs = sorted(d["xc"] for d in hdr)
    pitch = float(np.median(np.diff(xs))) if len(xs) > 1 else 40.0
    tol = max(8.0, pitch * 0.6)
    out: Dict[int, Tuple[float, str]] = {}
    for x0, x1, t in cells:
        v, klass = _eps_num(t)
        if klass == "NA" and v is None and t.strip().lower() not in _EPS_PLACEHOLDER:
            continue
        xc = (x0 + x1) / 2.0
        near = min(hdr, key=lambda d: abs(d["xc"] - xc))
        if abs(near["xc"] - xc) > tol:
            continue                       # 밀어 넣지 않는다 — 비워 둔다
        if near["year"] in out:
            continue                       # 첫 매칭만 (뒤따르는 %·배 컬럼 방지)
        out[near["year"]] = (v, klass)
    return out


def _eps_scan_page(words: Sequence[Sequence]) -> Tuple[List[Dict[str, Any]], int, int]:
    """한 페이지에서 (EPS 추정치들, 헤더발견여부, EPS행발견여부)."""
    rows = _eps_rows_from_words(words)
    if not rows:
        return [], 0, 0
    cellrows = [_eps_cells(r) for r in rows]
    ymid = [float(np.mean([float(w[1]) for w in r])) for r in rows]
    pitch = float(np.median(np.diff(ymid))) if len(ymid) > 2 else 12.0
    n_hdr = n_eps = 0
    found: List[Dict[str, Any]] = []

    for i, cr in enumerate(cellrows):
        hdr = _eps_parse_header(cr)
        if not hdr:
            continue
        n_hdr += 1
        #  결산월: ① 헤더 토큰 자체(2024.03) ② 라벨의 '(12월 결산)' ③ 기본 12
        fmonth = next((d["fmonth"] for d in hdr if d.get("fmonth")), None)
        if not fmonth:
            fmonth = 12
            for _, _, t in cr:
                m = _FYEAR_MONTH_RE.search(t)
                if m and 1 <= int(m.group(1)) <= 12:
                    fmonth = int(m.group(1))
                    break
        j = i + 1
        if j < len(cellrows) and _eps_merge_suffix_row(hdr, cellrows[j]):
            j += 1
        #  헤더 아래로 최대 30행까지 걸어가되, 행간격이 크게 벌어지면 다른 표다 → 중단
        limit = min(j + 30, len(cellrows))
        while j < limit:
            if j > 0 and (ymid[j] - ymid[j - 1]) > max(2.2 * pitch, pitch + 12.0):
                break
            cr2 = cellrows[j]
            if cr2:
                label = cr2[0][2].strip()
                #  ★ 금지어 검사는 첫 셀이 아니라 '숫자가 시작되기 전까지의 라벨 전체'에
                #    적용한다. 'EPS' 와 '증가율' 이 다른 셀로 쪼개지면 첫 셀만 보는 검사는
                #    'EPS 증가율(%)' 행을 EPS 로 받아들인다(값은 %라서 완전히 다른 척도다).
                head = []
                for _c in cr2:
                    if _eps_num(_c[2])[1] == "NUM":
                        break
                    head.append(_c[2])
                label_full = " ".join(head).strip()
                if _EPS_OK_RE.match(label.replace(" ", "")) and not _EPS_BAD_RE.search(label_full):
                    n_eps += 1
                    mapped = _eps_map_to_years(hdr, cr2[1:])
                    if len(mapped) >= 2:
                        for y, (v, klass) in mapped.items():
                            found.append({"fiscal_year": y, "fiscal_month": fmonth,
                                          "value": v, "value_class": klass,
                                          "suffix": next((d["suffix"] for d in hdr
                                                          if d["year"] == y), "")})
                        return found, n_hdr, n_eps
            j += 1
    return found, n_hdr, n_eps


def eps_extract_from_pdf(path: str, max_pages: int = 3) -> Dict[str, Any]:
    """PDF 1개 → EPS 추정치 목록 + 진단 상태. 예외를 밖으로 내보내지 않는다."""
    res: Dict[str, Any] = {"status": "NO_PARSER", "rows": [], "n_words": 0}
    if fitz is None:
        return res
    try:
        with fitz.open(path) as doc:
            npg = min(max_pages, doc.page_count)
            total_words = 0
            for pi in range(npg):
                words = doc[pi].get_text("words")
                total_words += len(words)
                rows, n_hdr, n_eps = _eps_scan_page(words)
                if rows:
                    res.update(status="OK", rows=rows, n_words=total_words, page=pi)
                    return res
            res["n_words"] = total_words
            res["status"] = "NO_TEXT_LAYER" if total_words == 0 else "NO_TABLE"
    except Exception as e:
        res["status"] = f"ERR:{type(e).__name__}"
    return res


def _eps_worker(job: Tuple[str, str]) -> Tuple[str, Dict[str, Any]]:
    uid, path = job
    return uid, eps_extract_from_pdf(path)


def build_eps_forecasts(reports: pd.DataFrame, links: pd.DataFrame,
                        annual_rcept: Optional[Dict[Tuple[str, int], pd.Timestamp]] = None
                        ) -> pd.DataFrame:
    """캐시된 PDF 에서 EPS 추정치를 뽑아 §2.1 표준 스키마로 만든다.

    ★ 네트워크를 쓰지 않는다. 드라이브에 이미 있는 blob 만 읽는다(절대 1원칙: 캐시 우선).
    ★ 결과는 **공용 인덱스**에 저장한다 — EPS 추정치 원장은 이 전략 전용물이 아니라
      다른 전략도 그대로 쓸 수 있는 범용 정제본이기 때문이다.
    ★ 재실행 시 파서 버전이 같은 건은 건너뛴다(이어받기). 버전을 올리면 전부 재파싱된다.
    """
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if reports is None or reports.empty or links is None or links.empty:
        LOG.warn("리포트/애널리스트 원장이 비어 EPS 트랙을 만들 수 없습니다.")
        return empty
    if fitz is None:
        LOG.warn("pymupdf(fitz) 가 없어 EPS 추출을 건너뜁니다 — TP 트랙만 사용됩니다. "
                 "`pip install pymupdf` 로 EPS 트랙이 살아납니다.")
        return empty

    #  ① 캐시된 EPS 원장을 먼저 읽는다
    cached = VAULT.get_table(EPS_TABLE, scope="shared")
    done_ok: Dict[str, pd.DataFrame] = {}
    if cached is not None and len(cached) and "parser_version" in cached.columns:
        cached = cached[cached["parser_version"].astype(str) == EPS_PARSER_VERSION]
        LOG.info(f"공용 캐시에서 EPS 추정치 {len(cached):,}행 재사용 "
                 f"(파서 v{EPS_PARSER_VERSION})")
    else:
        cached = None
    st = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
    seen: set = set()
    if st is not None and len(st) and "parser_version" in st.columns:
        seen = set(st.loc[st["parser_version"].astype(str) == EPS_PARSER_VERSION,
                          "report_uid"].astype(str))

    #  ② uid → 실제 파일 경로. get_blob 은 바이트를 통째로 읽으므로 쓰지 않는다.
    idx = VAULT.load_index("shared")
    paths: Dict[str, str] = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        paths = dict(zip(sub["key"].astype(str), sub["abs_path"].astype(str)))
    if not paths:
        LOG.warn("드라이브 공용 인덱스에 리포트 PDF 가 없습니다 → EPS 트랙 비활성. "
                 "RESEARCH_DOWNLOAD_PDF=True 로 한 번 수집하면 이후 실행부터 캐시로 재사용됩니다.")
        return cached_to_forecasts(cached, links, annual_rcept) if cached is not None else empty

    todo = [(u, p) for u, p in paths.items()
            if u not in seen and os.path.exists(p)]
    LOG.info(f"EPS 추출 대상 {len(todo):,}건 (캐시 보유 {len(seen):,}건 건너뜀 · "
             f"드라이브 PDF 총 {len(paths):,}건)")

    new_rows, new_status = [], []
    if todo:
        chunk = max(200, int(PDF_PARSE_CHUNK))
        nch = (len(todo) - 1) // chunk + 1
        for k0 in range(0, len(todo), chunk):
            part = todo[k0:k0 + chunk]
            out = pmap_cpu(_eps_worker, part,
                           workers=(PDF_PARSE_WORKERS or None),
                           desc=f"EPS 추출 {k0//chunk + 1}/{nch}")
            for r in out:
                if not r:
                    continue
                uid, res = r
                new_status.append({"report_uid": uid, "status": res["status"],
                                   "n_words": res.get("n_words", 0),
                                   "parser_version": EPS_PARSER_VERSION})
                for row in res.get("rows", []):
                    new_rows.append({"report_uid": uid, **row,
                                     "parser_version": EPS_PARSER_VERSION})
            del out
            #  청크마다 저장 — 중간에 끊겨도 다음 실행이 정확히 이어받는다
            if new_rows or new_status:
                _eps_persist(new_rows, new_status)
                new_rows, new_status = [], []
    if new_rows or new_status:
        _eps_persist(new_rows, new_status)
    #  최종 조립 직전에 전체 원장을 다시 읽고 **여기서** 파서버전으로 거른다
    cached = VAULT.get_table(EPS_TABLE, scope="shared")
    if cached is not None and len(cached) and "parser_version" in cached.columns:
        cached = cached[cached["parser_version"].astype(str) == EPS_PARSER_VERSION]

    _eps_report_extraction(reports, links)
    return cached_to_forecasts(cached, links, annual_rcept)


def _eps_persist(rows: List[dict], status: List[dict]) -> bool:
    """추출 결과를 공용 인덱스에 누적 저장 (기존 행을 지우지 않고 합집합).

    ★★ put_table 은 파일을 **통째로 교체**한다. 그래서 여기서 합칠 원본은 반드시
       '필터되지 않은 전체 원장' 이어야 한다. 호출부의 cached 는 parser_version 으로
       걸러진 부분집합이므로, 그걸 넘겨 받아 합치면 파서 버전을 올리는 순간
       이전 버전 행 전체(그리고 다른 전략이 쌓은 행까지)가 삭제된다.
       — 절대 1원칙(기존 캐시 훼손 금지) 위반이라 파라미터 자체를 없앴다.
    """
    ok = True
    if rows:
        new = pd.DataFrame(rows)
        prev = VAULT.get_table(EPS_TABLE, scope="shared")        # 항상 '전체' 원장
        allr = pd.concat([prev, new], ignore_index=True) if prev is not None and len(prev) else new
        allr = allr.drop_duplicates(subset=["report_uid", "fiscal_year", "parser_version"],
                                    keep="last")
        if VAULT.put_table(EPS_TABLE, allr, scope="shared", domain="research",
                           source=f"pdf_eps_parser v{EPS_PARSER_VERSION}") is None:
            #  저장에 실패했는데 상태표만 쓰면 그 리포트는 영원히 '처리됨'으로 남아
            #  다음 실행에서 재파싱되지 않는다 → 조용한 데이터 유실
            LOG.warn("EPS 원장 저장 실패 — 상태표를 기록하지 않고 다음 실행에서 재파싱합니다.")
            return False
        PIPE.io("OUT", "DRIVE", EPS_TABLE, allr, source="pdf eps extraction")
    if status:
        prev = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
        new = pd.DataFrame(status)
        alls = pd.concat([prev, new], ignore_index=True) if prev is not None and len(prev) else new
        alls = alls.drop_duplicates(subset=["report_uid", "parser_version"], keep="last")
        VAULT.put_table(EPS_STATUS_TABLE, alls, scope="shared", domain="research",
                        source=f"pdf_eps_parser v{EPS_PARSER_VERSION}")
    VAULT.flush("shared")
    return ok


def cached_to_forecasts(eps: Optional[pd.DataFrame], links: pd.DataFrame,
                        annual_rcept: Optional[Dict[Tuple[str, int], pd.Timestamp]] = None
                        ) -> pd.DataFrame:
    """EPS 추출 원장 + 애널리스트 연결표 → §2.1 analyst_forecasts (metric='EPS')."""
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if eps is None or not len(eps):
        return empty
    L = links.copy()
    if FORECAST_ATTRIBUTION == "lead" and "role" in L.columns:
        L = L[L["role"].astype(str).eq("lead")]
    L = L.dropna(subset=["stock_code"])
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"])
    keep = ["report_uid", "analyst_id", "broker_id", "stock_code", "pub_date"]
    m = eps.merge(L[keep].drop_duplicates(), on="report_uid", how="inner")
    if m.empty:
        return empty

    #  ── 실적(ACTUAL) 컬럼 제거: 추정치만 남긴다 ────────────────────────────────────
    #  판정 순서 (§ PIT): ① 명시 접미사 → ② DART 사업보고서 접수일 → ③ 회계연도말 비교
    m["fiscal_month"] = m["fiscal_month"].fillna(12).astype(int).clip(1, 12)
    fy_end = pd.to_datetime(dict(year=m["fiscal_year"].astype(int),
                                 month=m["fiscal_month"], day=1)) + pd.offsets.MonthEnd(0)
    m["fiscal_period_end"] = fy_end
    suf = m["suffix"].astype(str).str.upper()
    is_est = pd.Series(np.nan, index=m.index, dtype="float64")
    is_est[suf.isin(["E", "F", "P"])] = 1.0
    is_est[suf.eq("A")] = 0.0
    m["ae_confidence"] = np.where(is_est.notna(), "HIGH", "LOW")

    if annual_rcept:
        key = list(zip(m["stock_code"].astype(str), m["fiscal_year"].astype(int)))
        rc = pd.Series([annual_rcept.get(k, pd.NaT) for k in key], index=m.index)
        known = is_est.isna() & rc.notna()
        #  리포트 발간일이 그 회계연도 사업보고서 접수일 이후면 이미 '실적'이다
        is_est[known] = (m.loc[known, "pub_date"] < rc[known]).astype(float)
        m.loc[known, "ae_confidence"] = "HIGH"
    fallback = is_est.isna()
    is_est[fallback] = (m.loc[fallback, "fiscal_period_end"] > m.loc[fallback, "pub_date"]).astype(float)
    m["is_estimate"] = is_est.astype(bool)

    n_all = len(m)
    m = m[m["is_estimate"]]
    LOG.debug(f"EPS: 추출 {n_all:,}행 중 추정치 {len(m):,}행 (실적 컬럼 {n_all-len(m):,}행 제외)")

    out = pd.DataFrame({
        "stock_id": m["stock_code"].astype(str),
        "analyst_id": m["analyst_id"].astype(str),
        "broker_id": m["broker_id"].astype(str),
        "report_id": m["report_uid"].astype(str),
        "report_date": m["pub_date"],
        "fiscal_period": (m["fiscal_year"].astype(int).astype(str) + "-" +
                          m["fiscal_month"].astype(int).map("{:02d}".format)),
        "forecast_metric": "EPS",
        "forecast_value": pd.to_numeric(m["value"], errors="coerce"),
        "value_class": m["value_class"].astype(str),
        "horizon_yrs": (m["fiscal_year"].astype(int) - m["pub_date"].dt.year).astype("int16"),
        "is_estimate": True,
        "ae_confidence": m["ae_confidence"].astype(str),
    })
    #  §32 — 값이 없는 행(적전/흑전/n.a.)만 제외한다. 애널리스트는 유지된다.
    out = out[out["forecast_value"].notna()]
    #  터무니없는 값 방어: 주당순이익이 1,000만원을 넘거나 0.0001 미만이면 파싱 오류다
    bad = out["forecast_value"].abs() > 1e7
    if bad.any():
        LOG.debug(f"EPS 이상치 {int(bad.sum()):,}행 제외 (|EPS| > 1,000만원 — 단위 오인 추정)")
        out = out[~bad]
    return out.reset_index(drop=True)


def _eps_report_extraction(reports: pd.DataFrame, links: pd.DataFrame):
    """★ 증권사×연도 추출률 — 선택편향을 눈에 보이게 만드는 표."""
    st = VAULT.get_table(EPS_STATUS_TABLE, scope="shared")
    if st is None or not len(st):
        return
    st = st[st["parser_version"].astype(str) == EPS_PARSER_VERSION]
    if not len(st) or reports is None or reports.empty:
        return
    r = reports[["report_uid", "broker_name", "pub_date"]].copy()
    r["year"] = as_ts_series(r["pub_date"]).dt.year
    m = r.merge(st[["report_uid", "status"]], on="report_uid", how="inner")
    if m.empty:
        return
    m["ok"] = m["status"].astype(str).eq("OK")

    tot = m.groupby("status", observed=True).size().sort_values(ascending=False)
    LOG.table([[k, f"{v:,}", f"{100*v/len(m):.1f}%"] for k, v in tot.items()],
              ["추출 상태", "건수", "비중"], ["l", "r", "r"],
              title="EPS 추출 결과 분포 (OK=추정표 발견 · NO_TABLE=표 못 찾음 · "
                    "NO_TEXT_LAYER=스캔본이라 글자가 없음)")

    piv = m.pivot_table(index="broker_name", columns="year", values="ok", aggfunc="mean")
    cnt = m.groupby("broker_name", observed=True).size().sort_values(ascending=False)
    top = [b for b in cnt.index[:25] if b in piv.index]
    yrs = sorted(piv.columns)[-10:]
    rows = [[b, f"{cnt[b]:,}"] + [f"{100*piv.loc[b, y]:.0f}%" if pd.notna(piv.loc[b, y]) else "—"
                                  for y in yrs] for b in top]
    LOG.table(rows, ["증권사", "리포트"] + [str(y) for y in yrs],
              ["l", "r"] + ["r"] * len(yrs),
              title="★ 증권사×연도 EPS 추출률 — 이 표가 균일하지 않으면 EPS 트랙의 애널리스트 "
                    "점수는 '실력'이 아니라 'PDF 양식'을 반영합니다 (구조적 선택편향)")

    low = [b for b in top if np.nanmean(piv.loc[b, yrs].to_numpy(dtype="float64")) < 0.20]
    if low:
        LOG.warn(f"EPS 추출률 20% 미만 증권사 {len(low)}개: {', '.join(low[:8])}"
                 f"{' 외' if len(low) > 8 else ''} — 이 증권사 애널리스트는 EPS 트랙에서 "
                 f"이력이 얇아 전원 중립(0)으로 수축됩니다. 탈락은 아니지만 차등도 못 받습니다. "
                 f"→ 결론은 반드시 TP 트랙과 교차검증하세요.")


# ══════════════════════════════════════════════════════════════════════════════════════
#  TP 트랙 — 목표주가를 같은 산식에 그대로 태운다
# ══════════════════════════════════════════════════════════════════════════════════════

TP_FISCAL_PERIOD = "TP12M"          # 목표주가는 통상 12개월 선행 → 단일 버킷
TP_HORIZON_TRADING_DAYS = 250       # 실측 시점 (≈12개월)


def build_tp_forecasts(links: pd.DataFrame, adj_factor: Optional[pd.DataFrame] = None
                       ) -> pd.DataFrame:
    """목표주가 → §2.1 analyst_forecasts (metric='TP').

    ★ 액면분할 보정: 원 목표주가는 발표 시점의 '실제 주가' 단위다. 10년치를 한 통에 담으면
      분할 종목에서 컨센서스와 리비전이 통째로 망가진다. 그래서 발표일의
      adj_factor = 수정주가/실제주가 를 곱해 모든 목표주가를 '수정주가 통화'로 환산한다.
      (같은 날짜의 비율이므로 미래 정보가 들어가지 않는다 — adj_factor 는 t 시점에
       관측 가능한 두 가격의 비이며, 이후의 분할은 두 계열을 함께 움직인다)
    """
    empty = pd.DataFrame(columns=FORECAST_COLS + ["value_class", "horizon_yrs",
                                                  "is_estimate", "ae_confidence"])
    if links is None or links.empty:
        return empty
    L = links.copy()
    if FORECAST_ATTRIBUTION == "lead" and "role" in L.columns:
        L = L[L["role"].astype(str).eq("lead")]
    L["pub_date"] = as_ts_series(L["pub_date"])
    L["target_price"] = pd.to_numeric(L["target_price"], errors="coerce")
    #  적정가격 "0"/"-" 는 '목표주가 없음' 이지 0원이 아니다
    L = L[L["target_price"].notna() & (L["target_price"] > 0)]
    L = L.dropna(subset=["stock_code", "pub_date", "analyst_id"])
    if L.empty:
        return empty

    tp = L["target_price"].astype("float64")
    n_adj = 0
    if adj_factor is not None and len(adj_factor):
        af = adj_factor[["code", "date", "adj_factor"]].dropna().copy()
        af["date"] = _scg_ns(af["date"])
        af = af.sort_values("date")
        Ls = L.assign(_i=np.arange(len(L)))
        Ls["pub_date"] = _scg_ns(Ls["pub_date"])
        Ls = Ls.sort_values("pub_date")
        j = pd.merge_asof(Ls, af.rename(columns={"date": "pub_date"}),
                          on="pub_date", left_by="stock_code", right_by="code",
                          direction="backward", tolerance=pd.Timedelta(days=10))
        j = j.sort_values("_i")
        f = pd.to_numeric(j["adj_factor"], errors="coerce").to_numpy("float64")
        n_adj = int(np.isfinite(f).sum())
        tp = tp.to_numpy("float64") * np.where(np.isfinite(f) & (f > 0), f, 1.0)
    LOG.debug(f"TP 트랙: {len(L):,}건 (분할보정 적용 {n_adj:,}건)")

    return pd.DataFrame({
        "stock_id": L["stock_code"].astype(str),
        "analyst_id": L["analyst_id"].astype(str),
        "broker_id": L["broker_id"].astype(str),
        "report_id": L["report_uid"].astype(str),
        "report_date": L["pub_date"].values,
        "fiscal_period": TP_FISCAL_PERIOD,
        "forecast_metric": "TP",
        "forecast_value": np.asarray(tp, dtype="float64"),
        "value_class": "NUM",
        "horizon_yrs": np.int16(1),
        "is_estimate": True,
        "ae_confidence": "HIGH",
    }).reset_index(drop=True)


def build_tp_accuracy_events(forecasts: pd.DataFrame, px_adj: pd.DataFrame, cal,
                             cfg: SCGConfig = SCG) -> pd.DataFrame:
    """TP 트랙의 Accuracy Event — §8 의 산식을 그대로, '실적' 대신 '실제 주가'로 채점한다.

    왜 build_accuracy_events 를 재사용하지 않는가:
      EPS 는 (종목·회계연도)마다 실측치가 **한 번** 나오지만, 목표주가는 회계연도가 없다.
      TP 의 fiscal_period 를 분기로 쪼개면 신호 단계의 컨센서스까지 분기별로 조각나
      (§6 의 '활성 전망 집합'이 무너진다). 그래서 신호용 fiscal_period 는 단일 버킷으로
      두고, 채점만 여기서 분기 빈티지 단위로 따로 만든다. 산식·클리핑·스케일은 §8 동일.

    ★ PIT: 사건 완료일 = 예측 시점(분기말) + 250거래일. build_analyst_scores 가
      '완료일 < T' 만 쓰므로 미래 주가는 현재 점수에 들어갈 수 없다.
    """
    cols = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric",
            "actual_announcement_date", "actual_value", "forecast_value",
            "consensus_at_event", "n_analysts", "scale", "ne_analyst", "ne_consensus",
            "acc_event", "acc_event_loo", "report_date", "forecast_age_days"]
    f = forecasts[forecasts["forecast_metric"].astype(str).eq("TP")] if forecasts is not None and len(forecasts) else None
    if f is None or f.empty or px_adj is None or px_adj.empty:
        return pd.DataFrame(columns=cols)

    calv = _scg_trading_calendar(cal)
    M, codes, didx = _scg_price_matrix(px_adj, calv)
    if M.size == 0:
        return pd.DataFrame(columns=cols)

    #  분기말을 '예측 기준일' 로 삼는다. 그 시점의 활성 목표주가 집합이 하나의 예측 사건.
    f = f.copy()
    f["report_date"] = as_ts_series(f["report_date"])
    f = f.dropna(subset=["report_date", "forecast_value"])
    qs = pd.PeriodIndex(pd.DatetimeIndex(sorted(f["report_date"].dropna().unique())).to_period("Q")).unique()
    ref = pd.DatetimeIndex([q.end_time.normalize() for q in qs]).sort_values()
    if not len(ref):
        return pd.DataFrame(columns=cols)

    act = build_active_forecasts(f, ref, cfg)
    if act.empty:
        return pd.DataFrame(columns=cols)
    act = act.rename(columns={"signal_date": "event_ref"})
    act["outcome_date"] = _scg_shift_td(act["event_ref"], TP_HORIZON_TRADING_DAYS, calv)
    act = act[act["outcome_date"].notna()]
    if act.empty:
        return pd.DataFrame(columns=cols)

    ci = act["stock_id"].map(codes)
    pos = np.searchsorted(didx, act["outcome_date"].values.astype("datetime64[ns]"),
                          side="right") - 1
    ok = ci.notna().to_numpy() & (pos >= 0)
    act["actual_value"] = np.where(
        ok, M[np.clip(pos, 0, len(didx) - 1), ci.fillna(0).to_numpy("int64")], np.nan)
    act = act.dropna(subset=["actual_value"])
    if act.empty:
        return pd.DataFrame(columns=cols)

    #  §8 산식 — EPS 트랙과 완전히 동일하다
    key = ["stock_id", "event_ref"]
    g = act.groupby(key, observed=True, sort=False)["forecast_value"]
    act["n_analysts"] = g.transform("size").astype("int32")
    act["_sum"] = g.transform("sum")
    act["consensus_at_event"] = g.transform("mean")
    act["_median_abs"] = act.groupby(key, observed=True, sort=False)["forecast_value"] \
                            .transform(lambda s: s.abs().median())
    act = act[act["n_analysts"] >= cfg.MIN_ANALYSTS]
    if act.empty:
        return pd.DataFrame(columns=cols)

    eps = float(cfg.EPSILON)
    A = act["actual_value"].to_numpy("float64")
    F = act["forecast_value"].to_numpy("float64")
    C = act["consensus_at_event"].to_numpy("float64")
    scale = np.maximum.reduce([np.abs(A), act["_median_abs"].to_numpy("float64"),
                               np.full(A.shape, eps)])
    ne_j, ne_c = np.abs(F - A) / scale, np.abs(C - A) / scale
    n = act["n_analysts"].to_numpy("float64")
    c_loo = np.where(n > 1, (act["_sum"].to_numpy("float64") - F) / np.maximum(n - 1, 1), np.nan)

    out = pd.DataFrame({
        "stock_id": act["stock_id"].values,
        "analyst_id": act["analyst_id"].values,
        "fiscal_period": TP_FISCAL_PERIOD,
        "forecast_metric": "TP",
        "actual_announcement_date": act["outcome_date"].values,
        "actual_value": A, "forecast_value": F,
        "consensus_at_event": C, "n_analysts": act["n_analysts"].values,
        "scale": scale, "ne_analyst": ne_j, "ne_consensus": ne_c,
        "acc_event": np.clip(np.log((ne_c + eps) / (ne_j + eps)),
                             -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP),
        "acc_event_loo": np.clip(np.log((np.abs(c_loo - A) / scale + eps) / (ne_j + eps)),
                                 -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP),
        "report_date": act["report_date"].values,
        "forecast_age_days": act["forecast_age_days"].values,
    })
    LOG.debug(f"TP Accuracy 이벤트 {len(out):,}건 ({out['analyst_id'].nunique():,}명)")
    return out[cols].reset_index(drop=True)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  진단 (§34) + 원장 연결 감사                                                              ║
# ║                                                                                          ║
# ║  사용자 요구: "보고서와 식별된 애널리스트가 제대로 연결되었는지, 다중소스 원장연결은        ║
# ║  확실한지 한눈에". 그래서 원장을 4단 사슬로 보고, 각 고리의 잔존율을 연도·소스별로 낸다:    ║
# ║      리포트  →  애널리스트  →  종목코드  →  EPS 추정치                                     ║
# ║  어느 고리에서 끊기는지 모르면 "데이터가 없다"와 "코드가 연결을 못 했다"를 구분할 수 없다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


def scg_analyst_count_distribution(sig: pd.DataFrame) -> pd.DataFrame:
    """§34.1 analyst_count_distribution — 시점별 커버리지 분포.

    이 표가 급락하는 구간이 있으면 그 구간의 성과는 신뢰할 수 없다.
    (표본이 얇아지면 십분위 자체가 노이즈가 된다)
    """
    if sig is None or sig.empty or "analyst_count" not in sig.columns:
        return pd.DataFrame(columns=["signal_date", "count", "mean", "median",
                                     "p10", "p25", "p75", "p90"])
    d = sig[sig["status"].eq(STATUS_OK)] if "status" in sig.columns else sig
    g = d.groupby("signal_date", observed=True)["analyst_count"]
    D = pd.DataFrame({
        "count": g.size(), "mean": g.mean(), "median": g.median(),
        "p10": g.quantile(0.10), "p25": g.quantile(0.25),
        "p75": g.quantile(0.75), "p90": g.quantile(0.90),
    }).reset_index()
    return D


def scg_shrinkage_diagnostics(scores: pd.DataFrame) -> pd.DataFrame:
    """§34.2 shrinkage_diagnostics — 표본이 적은 애널리스트가 과대평가되지 않는지.

    ★ 읽는 법: acc_n 이 작은데 acc_star 가 크면 수축이 작동하지 않은 것이다.
      λ = n/(n+6) 이므로 n=1 이면 λ=0.14, n=6 이면 0.50, n=30 이면 0.83 이어야 한다.
      아래 표의 '이론 λ' 와 '실측 λ' 가 어긋나면 계산이 틀린 것이다.
    """
    cols = ["analyst_id", "acc_n", "lead_n", "acc_raw", "acc_star",
            "lead_raw", "lead_star", "quality_score_ls"]
    if scores is None or scores.empty:
        return pd.DataFrame(columns=cols)
    #  마지막 signal date 의 단면 = 가장 많은 이력이 쌓인 시점
    last = scores["signal_date"].max()
    S = scores[scores["signal_date"].eq(last)].copy()
    return S[[c for c in cols if c in S.columns]].sort_values(
        "acc_n", ascending=False).reset_index(drop=True)


def scg_report_shrinkage(scores: pd.DataFrame, cfg: SCGConfig = SCG):
    """수축이 실제로 작동했는지 n 구간별로 검증해 표로 낸다."""
    if scores is None or scores.empty:
        LOG.warn("애널리스트 점수가 비어 수축 진단을 건너뜁니다.")
        return
    last = scores["signal_date"].max()
    S = scores[scores["signal_date"].eq(last)]
    bins = [(0, 0), (1, 2), (3, 5), (6, 9), (10, 19), (20, 49), (50, 10 ** 9)]
    rows = []
    for lo, hi in bins:
        g = S[(S["acc_n"] >= lo) & (S["acc_n"] <= hi)]
        if not len(g):
            continue
        n_mid = float(g["acc_n"].mean())
        rows.append([f"{lo}~{hi if hi < 10**9 else '∞'}", f"{len(g):,}",
                     f"{n_mid:.1f}", f"{n_mid/(n_mid+cfg.K_ACC):.3f}",
                     f"{g['acc_lambda'].mean():.3f}",
                     f"{g['acc_raw'].mean():+.3f}", f"{g['acc_star'].mean():+.3f}",
                     f"{g['acc_star'].abs().max():.3f}"])
    LOG.table(rows, ["acc_n 구간", "애널 수", "평균 n", "이론 λ", "실측 λ",
                     "ACC_raw 평균", "ACC* 평균", "|ACC*| 최대"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title=f"§34.2 수축 진단 ({pd.Timestamp(last).date()} 단면) — "
                    f"이론 λ 와 실측 λ 가 일치해야 하고, n 이 작을수록 ACC* 가 0 에 붙어야 합니다")
    z = S[S["acc_n"].eq(0) & S["lead_n"].eq(0)]
    if len(z):
        LOG.info(f"이력이 전혀 없는 애널리스트 {len(z):,}명 — 전원 유지되며 Q=0, multiplier=1.0 "
                 f"입니다(§32). 탈락시키지 않는 것이 이 전략의 설계입니다.")


def scg_weight_concentration(weights: pd.DataFrame) -> pd.DataFrame:
    """§34.3 weight_concentration — 한 명이 Smart Consensus 를 좌우하고 있지 않은가.

    Effective N = 1 / Σ p_j²   (p_j = w_j / Σw)
    ★ 진단용이지 하드게이트가 아니다(§34.3). 값이 나쁘다고 종목을 빼지 않는다.
    """
    cols = ["signal_date", "stock_id", "fiscal_period", "forecast_metric",
            "max_weight_share", "top2_weight_share", "effective_analyst_n", "n_analysts"]
    if weights is None or weights.empty:
        return pd.DataFrame(columns=cols)
    W = weights[["signal_date"] + GROUP_KEY + ["weight_ls"]].copy()
    tot = W.groupby(["signal_date"] + GROUP_KEY, observed=True)["weight_ls"].transform("sum")
    W["p"] = W["weight_ls"] / tot.where(tot > 0)
    W["p2"] = W["p"] ** 2
    g = W.groupby(["signal_date"] + GROUP_KEY, observed=True)
    D = g.agg(max_weight_share=("p", "max"), _sp2=("p2", "sum"),
              n_analysts=("p", "size")).reset_index()
    top2 = (W.sort_values("p", ascending=False)
             .groupby(["signal_date"] + GROUP_KEY, observed=True)["p"]
             .apply(lambda s: float(s.head(2).sum())).rename("top2_weight_share").reset_index())
    D = D.merge(top2, on=["signal_date"] + GROUP_KEY, how="left")
    D["effective_analyst_n"] = 1.0 / D["_sp2"].where(D["_sp2"] > 0)
    return D[cols]


def scg_report_weight_concentration(conc: pd.DataFrame):
    if conc is None or conc.empty:
        return
    q = conc[["max_weight_share", "top2_weight_share", "effective_analyst_n", "n_analysts"]]
    rows = [[k, f"{q[k].mean():.3f}", f"{q[k].quantile(.5):.3f}",
             f"{q[k].quantile(.9):.3f}", f"{q[k].max():.3f}"] for k in q.columns]
    LOG.table(rows, ["지표", "평균", "중앙", "p90", "최대"], ["l", "r", "r", "r", "r"],
              title="§34.3 가중치 집중도 — Effective N 이 실제 애널리스트 수에 가까울수록 "
                    "'한 명이 컨센서스를 좌우'하지 않는다는 뜻 (진단용 · 게이트 아님)")
    #  가중치 상한이 2.0/0.5 = 4배로 묶여 있으므로 집중도는 구조적으로 제한된다.
    bad = conc[conc["max_weight_share"] > 0.8]
    if len(bad):
        LOG.info(f"한 애널리스트가 80% 초과 비중을 갖는 (종목·시점) {len(bad):,}건 — "
                 f"대부분 애널리스트가 2명뿐인 종목입니다(구조적, 가중치 문제 아님).")


def scg_audit_forecast_ledger(reports: pd.DataFrame, links: pd.DataFrame,
                              forecasts: pd.DataFrame, actuals: pd.DataFrame):
    """★ 원장 4단 사슬 감사 — 리포트 → 애널리스트 → 종목 → EPS 추정치.

    어느 고리가 끊겼는지 연도별로 드러낸다. "EPS 커버리지가 낮다"는 결론을 내리기 전에
    그게 (a) 리포트를 못 받은 건지 (b) 애널을 못 붙인 건지 (c) 종목코드가 없는 건지
    (d) PDF 에서 숫자를 못 뽑은 건지 반드시 구분되어야 한다.
    """
    LOG.banner("원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목 ↔ EPS 추정치",
               "연결이 끊긴 고리를 연도별로 노출한다. 숫자가 낮으면 낮은 대로 보고한다.")
    if reports is None or reports.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다. "
                 "드라이브 캐시(research_report_master)와 RESEARCH_COLLECT 를 확인하세요.")
        return

    r = reports.copy()
    r["year"] = as_ts_series(r["pub_date"]).dt.year
    linked = set(links["report_uid"].astype(str)) if links is not None and len(links) else set()
    with_eps = set()
    if forecasts is not None and len(forecasts) and "report_id" in forecasts.columns:
        e = forecasts[forecasts["forecast_metric"].astype(str).eq("EPS")]
        with_eps = set(e["report_id"].astype(str))
    with_tp = set()
    if forecasts is not None and len(forecasts) and "report_id" in forecasts.columns:
        t = forecasts[forecasts["forecast_metric"].astype(str).eq("TP")]
        with_tp = set(t["report_id"].astype(str))

    ruid = r["report_uid"].astype(str)
    r["c_analyst"] = ruid.isin(linked)
    r["c_code"] = r["stock_code"].notna()
    r["c_eps"] = ruid.isin(with_eps)
    r["c_tp"] = ruid.isin(with_tp)
    r["c_chain"] = r["c_analyst"] & r["c_code"] & r["c_eps"]

    rows = []
    for y, g in r.groupby("year", observed=True):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{100*g['c_analyst'].mean():.1f}%", f"{100*g['c_code'].mean():.1f}%",
                     f"{100*g['c_tp'].mean():.1f}%", f"{100*g['c_eps'].mean():.1f}%",
                     f"{int(g['c_chain'].sum()):,}", f"{100*g['c_chain'].mean():.1f}%"])
    LOG.table(rows, ["연도", "리포트", "①애널연결", "②종목코드", "③목표주가", "④EPS추정",
                     "4단 완결", "완결률"],
              ["c", "r", "r", "r", "r", "r", "r", "r"],
              title="원장 4단 사슬 잔존율 — ④가 낮고 ①②③이 높으면 'PDF에서 숫자를 못 뽑은 것' 입니다")

    if "source" in r.columns:
        s = r.groupby("source", observed=True).agg(
            n=("report_uid", "size"), a=("c_analyst", "mean"), c=("c_code", "mean"),
            tp=("c_tp", "mean"), e=("c_eps", "mean")).reset_index()
        LOG.table([[x["source"], f"{int(x['n']):,}", f"{100*x['a']:.1f}%", f"{100*x['c']:.1f}%",
                    f"{100*x['tp']:.1f}%", f"{100*x['e']:.1f}%"] for _, x in s.iterrows()],
                  ["소스 조합", "건수", "애널연결률", "종목코드율", "목표주가율", "EPS추정율"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="다중소스 원장연결 — 'hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건. "
                        "한경은 작성자를, 네이버는 종목코드를 채운다(둘을 합쳐야 원장이 완성됨)")

    if forecasts is not None and len(forecasts):
        f = forecasts.copy()
        f["year"] = as_ts_series(f["report_date"]).dt.year
        rows = []
        for (mt, y), g in f.groupby(["forecast_metric", "year"], observed=True):
            rows.append([str(mt), int(y), f"{len(g):,}", f"{g['analyst_id'].nunique():,}",
                         f"{g['stock_id'].nunique():,}", f"{g['fiscal_period'].nunique()}"])
        LOG.table(rows[:60], ["메트릭", "연도", "전망 건수", "애널리스트", "종목", "회계기간"],
                  ["l", "c", "r", "r", "r", "r"],
                  title="analyst_forecasts 적재 현황 (§2.1 표준 스키마)")

    if actuals is not None and len(actuals):
        a = actuals.copy()
        a["year"] = as_ts_series(a["actual_announcement_date"]).dt.year
        cov = (a.groupby(["forecast_metric", "year"], observed=True)
                .agg(n=("actual_value", "size"), stocks=("stock_id", "nunique")).reset_index())
        LOG.table([[str(x["forecast_metric"]), int(x["year"]), f"{int(x['n']):,}",
                    f"{int(x['stocks']):,}"] for _, x in cov.iterrows()][:40],
                  ["메트릭", "발표연도", "실적 건수", "종목"], ["l", "c", "r", "r"],
                  title="실적 실측치(Accuracy 의 A) 적재 현황 — 없으면 ACC* 는 전부 0 으로 수축됩니다")
    else:
        LOG.warn("실적 실측치가 없습니다 → ACC* 전원 0. 애널리스트는 탈락하지 않지만 "
                 "SCG_0 는 사실상 'Recency 가중 컨센서스 갭'이 됩니다. DART_API_KEY 를 확인하세요.")


def scg_report_universe_attrition(stages: Sequence[Tuple[str, int, str]]):
    """유니버스 감쇠 감사 — 어느 게이트에서 표본이 줄었는지 (§35 TEST 9 의 근거표).

    stages: [(단계명, 종목수, 설명), ...]
    """
    if not stages:
        return
    base = max(1, stages[0][1])
    prev = stages[0][1]
    rows = []
    for name, n, why in stages:
        rows.append([name, f"{n:,}", f"{100*n/base:.1f}%",
                     f"{n-prev:+,}" if n != prev else "—", why])
        prev = n
    LOG.table(rows, ["단계", "종목수", "잔존율", "증감", "근거"],
              ["l", "r", "r", "r", "l"],
              title="유니버스 감쇠 — §31 이 금지한 하드게이트가 몰래 들어오면 여기서 표본이 꺾입니다")


# ══════════════════════════════════════════════════════════════════════════════════════
#  캐시 원장 — "모든 신규수집은 드라이브에 저장되고 재호출된다"를 매 실행 증명한다
# ══════════════════════════════════════════════════════════════════════════════════════

#  (데이터셋, 인덱스, 무엇인가)  — 이 목록이 곧 이 전략이 네트워크에서 가져오는 것 전부다.
SCG_CACHE_MANIFEST = [
    ("marcap_spine_*",             "shared",  "일별 전종목시세(연도별) — 유니버스·가격·시총·캘린더의 단일 원천"),
    ("marcap_meta_*",              "shared",  "종목명/시장 (연도별)"),
    ("fdr_cache_listing_krx",      "shared",  "상장목록"),
    ("fdr_cache_listing_delisting", "shared", "상장폐지목록 — 생존자편향 제거 입력"),
    ("dart_corpcode",              "shared",  "회사 ↔ 종목코드 매핑"),
    ("benchmark_ks11_daily",       "shared",  "KOSPI 지수"),
    ("dart_periodic_disclosures",  "shared",  "정기공시 접수일 — 실적 발표일(PIT 근거)"),
    ("dart_multi_annual",          "shared",  "다중회사 주요계정 — 순이익(Accuracy 의 A)"),
    ("dart_shares_outstanding",    "shared",  "주식총수 (스파인 없을 때만)"),
    ("research_report_master",     "shared",  "애널리스트 리포트 원장"),
    ("analyst_master",             "shared",  "애널리스트 원장"),
    ("report_analyst_link",        "shared",  "보고서 ↔ 애널리스트 연결표"),
    ("analyst_eps_forecasts",      "shared",  "리포트 PDF 에서 추출한 EPS 추정치"),
    ("analyst_eps_extract_status", "shared",  "EPS 추출 상태(이어받기 근거)"),
    ("price_daily_adj",            "shared",  "수정주가 (스파인 없을 때만)"),
    ("price_daily_unadj",          "shared",  "무수정 주가 (스파인 없을 때만)"),
]


def scg_report_cache_ledger():
    """★ 절대 1원칙의 증거표 — 무엇이 어느 인덱스에 몇 행으로 저장되어 있는가.

    이 표에 행수가 찍혀 있으면 다음 실행은 그것을 네트워크 없이 재사용한다.
    (세션·머신과 무관하다 — 드라이브 파일이 원천이기 때문이다)
    """
    rows = []
    try:
        idx = VAULT.load_index("shared", force=True)
    except Exception:
        idx = pd.DataFrame()
    tdir_s, tdir_p = VAULT.table_dir("shared"), VAULT.table_dir("private")
    for name, scope, why in SCG_CACHE_MANIFEST:
        base = tdir_s if scope == "shared" else tdir_p
        if name.endswith("*"):
            pre = name[:-1]
            try:
                files = [f for f in os.listdir(base) if f.startswith(pre) and f.endswith(".parquet")]
            except Exception:
                files = []
            n_files = len(files)
            size = sum(_safe_size(os.path.join(base, f)) for f in files)
            rows.append([name, scope, f"{n_files}개 파일" if n_files else "—",
                         f"{size/1e6:.0f}MB" if size else "—", _trunc(why, 44)])
        else:
            fp = os.path.join(base, f"{name}.parquet")
            ok = os.path.exists(fp)
            n = ""
            if ok:
                try:
                    d = VAULT.get_table(name, scope=scope)
                    n = f"{len(d):,}행" if d is not None else "—"
                except Exception:
                    n = "읽기실패"
            rows.append([name, scope, n or "—",
                         f"{_safe_size(fp)/1e6:.1f}MB" if ok else "—", _trunc(why, 44)])
    LOG.table(rows, ["데이터셋", "인덱스", "저장량", "용량", "무엇인가"],
              ["l", "c", "r", "r", "l"],
              title="★ 캐시 원장 — 신규 수집된 모든 데이터는 여기에 저장되고 다음 실행에서 "
                    "네트워크 없이 재호출됩니다 (공용=다른 전략도 재사용 · 전용=이 전략 산출물)")
    miss = [r[0] for r in rows if r[2] in ("—", "")]
    if miss:
        LOG.info(f"아직 비어 있는 항목: {', '.join(miss[:8])}"
                 f"{' 외' if len(miss) > 8 else ''} — 해당 소스를 수집하지 않았거나 "
                 f"키가 없어 건너뛴 것입니다. 다음 실행에서 채워집니다.")


def scg_research_windows(cached: Optional[pd.DataFrame], start: str, end: str,
                         edge_days: int = 45) -> List[Tuple[str, str]]:
    """리포트 원장이 아직 덮지 못한 기간만 돌려준다 (증분 크롤).

    ★ 매 실행 15년치를 재크롤하지 않기 위한 것이다. 캐시가 [c0, c1] 을 덮고 있으면
      요청구간에서 그 앞뒤만 새로 긁는다. 최근 edge_days 는 항상 다시 긁는다 —
      뒤늦게 등록되는 리포트가 있기 때문이다(그래야 최신 구간이 비지 않는다).
    """
    lo, hi = as_ts(start), as_ts(end)
    if cached is None or not len(cached) or "pub_date" not in cached.columns:
        return [(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))]
    d = as_ts_series(cached["pub_date"]).dropna()
    if d.empty:
        return [(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))]
    c0, c1 = d.min(), d.max()
    out: List[Tuple[str, str]] = []
    if lo < c0:
        out.append((lo.strftime("%Y-%m-%d"),
                    min(c0 - pd.Timedelta(days=1), hi).strftime("%Y-%m-%d")))
    tail = max(c1 - pd.Timedelta(days=edge_days), lo)
    if tail <= hi:
        out.append((tail.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
    n_cached = len(cached)
    LOG.info(f"리포트 원장 캐시 {n_cached:,}건이 {c0.date()}~{c1.date()} 를 덮고 있습니다 → "
             f"신규 크롤 구간 {len(out)}개 {out}")
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 · 성과검증 (§36~§40)                                                        ║
# ║                                                                                          ║
# ║  ★ 이 전략의 백테스트는 '포트폴리오 최적화'가 아니라 '알파의 존재 증명'이다.                 ║
# ║    그래서 threshold 를 튜닝하지 않는다(§36). 십분위로 자르고 단조성을 본다.                 ║
# ║    네 전략(BASE_REV / SCG_0 / SCG_LS / SCG_LSA)은 같은 유니버스·같은 리밸런스로 돈다(§37).  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


def scg_forward_returns(signals: pd.DataFrame, px: pd.DataFrame, cal,
                        horizons_td: Sequence[int], sec: Optional[pd.DataFrame] = None,
                        delist_mode: str = "last_price") -> pd.DataFrame:
    """signal date 기준 전방수익률. 리밸런스용 `ret_next` 와 IC 용 `fwd_ret_{h}` 를 만든다.

    ★ 생존자편향 방어의 마지막 관문이 여기다. 폐지 종목의 수익률을 '결측'으로 두면
      그 종목은 조용히 표본에서 빠지고, 남은 것은 살아남은 종목뿐이다.
      그래서 폐지된 종목은 반드시 값을 갖는다:
        delist_mode="last_price" : 마지막 체결가까지의 실현손익 (정리매매에서 판 것과 같음)
        delist_mode="minus100"   : -100% (정리매매 자체가 없었다고 보는 보수적 가정)
      진입 후 단 한 번도 체결이 없었으면 두 모드 모두 -100% 다.
    """
    out = signals.copy()
    calv = _scg_trading_calendar(cal)
    M, codes, didx = _scg_price_matrix(px, calv)
    hs = sorted({int(h) for h in horizons_td})
    cols = [f"fwd_ret_{h}" for h in hs] + ["ret_next", "n_delisted_used"]
    if M.size == 0 or not codes:
        for c in cols:
            out[c] = np.nan
        LOG.warn("가격 행렬이 비어 전방수익률을 계산할 수 없습니다 — 백테스트는 건너뜁니다.")
        return out

    ci = out["stock_id"].map(codes)
    known = ci.notna()
    ci_v = ci.fillna(0).to_numpy("int64")
    sd = out["signal_date"].values.astype("datetime64[ns]")
    #  signal date 이하의 마지막 거래일에 체결된 가격으로 진입한다(그 날 알 수 있는 값).
    p0i = np.searchsorted(didx, sd, side="right") - 1
    valid0 = known.to_numpy() & (p0i >= 0)
    base = np.where(valid0, M[np.clip(p0i, 0, len(didx) - 1), ci_v], np.nan)

    #  종목별 마지막 체결 위치 (폐지 처리의 근거)
    has = ~np.isnan(M)
    lastpos = np.where(has.any(axis=0), has.shape[0] - 1 - has[::-1].argmax(axis=0), -1)
    last_px = np.where(lastpos >= 0, M[np.clip(lastpos, 0, len(didx) - 1),
                                       np.arange(M.shape[1])], np.nan)
    #  패널 전체의 마지막 관측 위치. 이 뒤는 '폐지'가 아니라 '아직 오지 않은 미래' 다.
    data_end = int(lastpos.max()) if lastpos.size else -1

    n_delist = np.zeros(len(out), dtype="int32")

    def _ret_at(pos: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        #  ★ '폐지' 와 '데이터 끝' 을 반드시 분리한다. 한 플래그로 묶으면 표본 마지막
        #    h 거래일에서 폐지 종목만 결측이 되고 생존자만 값을 갖는다 — 생존자편향의
        #    정확한 재현이다. 그리고 살아있는 종목의 지평이 패널 끝을 넘었을 때
        #    마지막 행으로 clip 하면 9일 수익률을 20일 수익률인 척 내보내게 된다.
        pos_c = np.clip(pos, 0, len(didx) - 1)
        inrange = valid0 & (pos >= 0)
        lp = lastpos[ci_v]
        gone = inrange & (lp >= 0) & (lp >= p0i) & (pos > lp) & (lp < data_end)
        unobs = inrange & ~gone & (pos > data_end)      # 관측 불가 → 결측 (fabrication 금지)
        px_h = np.where(inrange & ~unobs, M[pos_c, ci_v], np.nan)
        px_g = np.zeros_like(px_h) if delist_mode == "minus100" else last_px[ci_v]
        px_h = np.where(gone, px_g, px_h)
        r = np.where(np.isfinite(base) & (base > 0), px_h / base - 1.0, np.nan)
        #  진입 후 한 번도 체결이 없었으면 팔 기회 자체가 없었다 → -100%
        r = np.where(gone & ~np.isfinite(r), -1.0, r)
        return np.clip(r, -1.0, None), gone

    for h in hs:
        r, g = _ret_at(p0i + h)
        out[f"fwd_ret_{h}"] = r
        n_delist += g.astype("int32")

    #  리밸런스 수익률은 '다음 signal date 까지' — 고정 21거래일이 아니다.
    #  (월말 그리드에서 21일로 고정하면 달마다 며칠씩 겹치거나 비어 복리가 어긋난다)
    sdu = pd.DatetimeIndex(sorted(pd.unique(out["signal_date"])))
    nxt = pd.Series(list(sdu[1:]) + [pd.NaT], index=sdu)
    nd = out["signal_date"].map(nxt).values.astype("datetime64[ns]")
    p1i = np.where(pd.isna(nd), -1, np.searchsorted(didx, nd, side="right") - 1)
    r, g = _ret_at(p1i)
    out["ret_next"] = np.where(pd.isna(nd), np.nan, r)
    out["n_delisted_used"] = n_delist + g.astype("int32")

    nd_tot = int((out["n_delisted_used"] > 0).sum())
    if nd_tot:
        LOG.info(f"폐지·거래종료 구간을 포함해 수익률을 산출한 신호 {nd_tot:,}건 "
                 f"(모드={delist_mode}). 이 건들을 결측으로 버리면 생존자편향이 생깁니다.")
    return out


def scg_perf(rets: pd.Series, periods_per_year: float, rf: float = 0.0) -> Dict[str, float]:
    """§37 필수 성과 항목. 입력은 기간수익률 시계열(리밸런스 주기 단위)."""
    r = pd.Series(rets).dropna().astype("float64")
    n = len(r)
    if n == 0:
        return {k: np.nan for k in ("annualized_return", "CAGR", "volatility", "Sharpe",
                                    "MDD", "hit_rate", "n_periods")}
    eq = (1.0 + r).cumprod()
    yrs = n / float(periods_per_year)
    total = float(eq.iloc[-1])
    cagr = (total ** (1.0 / yrs) - 1.0) if (yrs > 0 and total > 0) else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else np.nan
    ann = float(r.mean() * periods_per_year)
    dd = eq / eq.cummax() - 1.0
    return {
        "annualized_return": ann,
        "CAGR": cagr,
        "volatility": vol,
        "Sharpe": float((ann - rf) / vol) if (vol and np.isfinite(vol) and vol > 0) else np.nan,
        "MDD": float(dd.min()),
        "hit_rate": float((r > 0).mean()),
        "n_periods": float(n),
    }


def scg_bucket_backtest(sig: pd.DataFrame, alpha_col: str, n_buckets: int,
                        min_n: int, cost_bps: float, ret_col: str = "ret_next"
                        ) -> Dict[str, Any]:
    """§36 — signal date 마다 알파 십분위(표본이 작으면 5분위)로 자르고 동일가중 보유.

    반환: buckets(시점×버킷 수익률), summary(버킷별 요약), long/ls 시계열, 회전율.
    ★ threshold 를 최적화하지 않는다. 자르는 규칙은 '분위수' 하나뿐이다.
    """
    need = {"signal_date", "stock_id", alpha_col, ret_col}
    d = sig[[c for c in sig.columns if c in need]].dropna(subset=["signal_date", "stock_id", alpha_col])
    res: Dict[str, Any] = {"alpha_col": alpha_col, "buckets": pd.DataFrame(),
                           "summary": pd.DataFrame(), "long": pd.Series(dtype="float64"),
                           "ls": pd.Series(dtype="float64"), "turnover": np.nan,
                           "avg_holdings": np.nan, "n_signals": int(len(d)),
                           "n_unique_stocks": int(d["stock_id"].nunique()) if len(d) else 0,
                           "n_buckets_used": n_buckets}
    if d.empty:
        return res

    rows, holds = [], {}
    used_nb = []
    for T, g in d.groupby("signal_date", observed=True, sort=True):
        g = g.dropna(subset=[ret_col])
        m = len(g)
        if m < 5:
            continue
        nb = n_buckets if m >= min_n else 5
        if m < nb:
            continue
        used_nb.append(nb)
        #  동점이 많은 rank 컬럼에서 qcut 은 자주 실패한다 → 순위 기반으로 균등 분할한다.
        r = g[alpha_col].rank(method="first", ascending=True)
        b = np.minimum((r.to_numpy() - 1) // (m / nb), nb - 1).astype("int32")
        g = g.assign(_b=b, _nb=nb)
        for bi, gg in g.groupby("_b", observed=True):
            rows.append({"signal_date": T, "bucket": int(bi), "n_buckets": nb,
                         "ret": float(gg[ret_col].mean()), "n": int(len(gg)),
                         "is_top": int(bi) == nb - 1, "is_bottom": int(bi) == 0})
        top = g.loc[g["_b"] == nb - 1, "stock_id"]
        holds[T] = set(top.astype(str))

    if not rows:
        return res
    B = pd.DataFrame(rows)
    nb_mode = int(pd.Series(used_nb).mode().iloc[0])
    res["n_buckets_used"] = nb_mode

    #  ★ 5분위 fallback 이 섞인 날의 라벨 매핑 — 양 끝이 반드시 1 과 nb_mode 가 되어야 한다.
    #    ceil((i+1)*nb_mode/nb) 는 5분위를 2,4,6,8,10 으로 보내 라벨 1 을 영영 만들지 않는다.
    #    그러면 최하위 버킷이 D2 행에 섞이고 롱숏은 5분위 날짜를 통째로 버린다.
    B["bucket_label"] = np.where(
        B["n_buckets"] == nb_mode, B["bucket"] + 1,
        np.rint(1 + B["bucket"] * (nb_mode - 1)
                / np.maximum(B["n_buckets"] - 1, 1)).astype(int))
    piv = B.pivot_table(index="signal_date", columns="bucket_label", values="ret", aggfunc="mean")
    res["buckets"] = piv

    lo_b, hi_b = piv.columns.min(), piv.columns.max()
    #  회전율: 최상위 버킷 보유종목의 교체 비율 (0=그대로, 1=전량 교체)
    ks = sorted(holds)
    tos = [len(holds[b] ^ holds[a]) / max(1, len(holds[b] | holds[a]))
           for a, b in zip(ks, ks[1:])]
    res["turnover"] = float(np.mean(tos)) if tos else np.nan
    res["avg_holdings"] = float(np.mean([len(v) for v in holds.values()])) if holds else np.nan

    cost = (cost_bps / 1e4) * (res["turnover"] if np.isfinite(res["turnover"]) else 0.0) * 2.0
    #  ★ 레그는 라벨이 아니라 '그 날의 실제 최상/최하 버킷' 에서 뽑는다. 라벨로 뽑으면
    #    5분위 날짜가 롱에는 남고 롱숏에서는 빠져 두 계열의 표본이 달라진다.
    top_s = B.loc[B["is_top"]].set_index("signal_date")["ret"].sort_index()
    bot_s = B.loc[B["is_bottom"]].set_index("signal_date")["ret"].sort_index()
    res["long"] = (top_s - cost).dropna()
    res["ls"] = (top_s - bot_s - 2.0 * cost).dropna()

    smry = piv.mean().rename("mean_ret").to_frame()
    smry["std"] = piv.std()
    smry["hit"] = (piv > 0).mean()
    smry["n_periods"] = piv.notna().sum()
    res["summary"] = smry.reset_index().rename(columns={"bucket_label": "bucket"})

    #  §39 단조성 — 버킷 번호와 평균수익률의 스피어만 상관
    s = res["summary"].dropna(subset=["mean_ret"])
    if len(s) >= 3:
        res["monotonicity_spearman"] = float(
            pd.Series(s["bucket"]).corr(pd.Series(s["mean_ret"]), method="spearman"))
        res["top_minus_bottom"] = float(s["mean_ret"].iloc[-1] - s["mean_ret"].iloc[0])
    else:
        res["monotonicity_spearman"] = np.nan
        res["top_minus_bottom"] = np.nan
    return res


def scg_ic(sig: pd.DataFrame, alpha_col: str, horizons_td: Sequence[int]) -> pd.DataFrame:
    """§40 — signal date 별 Spearman(alpha, forward return) 과 그 요약통계."""
    rows = []
    for h in sorted({int(x) for x in horizons_td}):
        fc = f"fwd_ret_{h}"
        if fc not in sig.columns:
            continue
        d = sig[["signal_date", alpha_col, fc]].dropna()
        if d.empty:
            continue
        ics = (d.groupby("signal_date", observed=True)
                 .apply(lambda g: g[alpha_col].corr(g[fc], method="spearman")
                        if len(g) >= 5 else np.nan, include_groups=False)
                 .dropna())
        if ics.empty:
            continue
        sd_ = float(ics.std(ddof=1)) if len(ics) > 1 else np.nan
        rows.append({
            "horizon_td": h, "n_dates": int(len(ics)),
            "mean_ic": float(ics.mean()), "median_ic": float(ics.median()),
            "ic_std": sd_,
            "ic_ir": float(ics.mean() / sd_) if (sd_ and np.isfinite(sd_) and sd_ > 0) else np.nan,
            "positive_ic_ratio": float((ics > 0).mean()),
            "t_stat": float(ics.mean() / (sd_ / np.sqrt(len(ics)))) if (sd_ and sd_ > 0) else np.nan,
        })
    return pd.DataFrame(rows)


def scg_run_all_strategies(sig: pd.DataFrame, cfg: SCGConfig = SCG,
                           bench: Optional[pd.Series] = None, label: str = "") -> Dict[str, Any]:
    """§37 — 네 전략을 동일 유니버스·동일 리밸런스로 나란히 돌린다."""
    ppy = 12.0 if SIGNAL_FREQ.upper().startswith("M") else 52.0
    out: Dict[str, Any] = {"label": label, "per_strategy": {}, "ppy": ppy}
    perf_rows, ic_frames, mono_rows = [], [], []

    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, BT_COST_BPS)
        ics = scg_ic(sig, acol, IC_HORIZONS_TD)
        out["per_strategy"][name] = {"bt": bt, "ic": ics}
        p = scg_perf(bt["long"], ppy)
        pls = scg_perf(bt["ls"], ppy)
        row = {"strategy": name, "n_signals": bt["n_signals"],
               "n_unique_stocks": bt["n_unique_stocks"],
               "annualized_return": p["annualized_return"], "CAGR": p["CAGR"],
               "volatility": p["volatility"], "Sharpe": p["Sharpe"], "MDD": p["MDD"],
               "hit_rate": p["hit_rate"], "turnover": bt["turnover"],
               "average_holdings": bt["avg_holdings"],
               "LS_annual": pls["annualized_return"], "LS_Sharpe": pls["Sharpe"]}
        if bench is not None and len(bench):
            al = bt["long"]
            common = al.index.intersection(bench.index)
            row["excess_vs_bench"] = (float((al.loc[common] - bench.loc[common]).mean() * ppy)
                                      if len(common) else np.nan)
        perf_rows.append(row)
        mono_rows.append({"strategy": name, "n_buckets": bt["n_buckets_used"],
                          "spearman": bt.get("monotonicity_spearman"),
                          "top_minus_bottom": bt.get("top_minus_bottom")})
        if len(ics):
            ic_frames.append(ics.assign(strategy=name))

    out["performance"] = pd.DataFrame(perf_rows)
    out["monotonicity"] = pd.DataFrame(mono_rows)
    out["ic"] = pd.concat(ic_frames, ignore_index=True) if ic_frames else pd.DataFrame()
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 검사 (§41 + 연구질문 §47)                                                     ║
# ║                                                                                          ║
# ║  ★ 여기서 파라미터를 '최적화'하지 않는다(§41). 공식값은 45/6/20 으로 고정이고,              ║
# ║    민감도 표는 "이 결론이 파라미터 한 칸 옮기면 사라지는가"만 본다.                         ║
# ║    성과가 가장 좋은 조합을 사후에 공식전략으로 승격하는 것은 명시적으로 금지되어 있다.       ║
# ║                                                                                          ║
# ║  검사 순서에도 뜻이 있다:                                                                  ║
# ║    S0 누수민감도 → (하네스가 알파를 감지할 수 있는가? 아니면 아래 전부가 무의미)             ║
# ║    S1 증분기여   → (§47 의 세 질문. 이 전략의 존재 이유)                                    ║
# ║    S2 민감도 → S3 하위기간 → S4 집중도 → S5 레짐 → S6 플라시보 → S7 비용                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_ROBUST: List[Dict[str, Any]] = []


def _rb(test: str, metric: str, value: Any, verdict: str, note: str = ""):
    SCG_ROBUST.append({"test": test, "metric": metric, "value": value,
                       "verdict": verdict, "note": note})


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, (int, float, np.floating)) else str(v)


def _ls_series(sig: pd.DataFrame, acol: str, ret_col: str = "ret_next") -> pd.Series:
    bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, 0.0, ret_col)
    return bt["ls"]


# ── S0. 누수 민감도 ──────────────────────────────────────────────────────────────────────
def S0_leak_sensitivity(sig: pd.DataFrame, ppy: float):
    """고의로 오염된 신호(미래수익률 주입)가 확실히 좋아지는지 본다.

    ★ 이 검사가 먼저인 이유: 오염본조차 성과가 안 나오면, 그건 '알파가 없다'가 아니라
      '하네스가 알파를 못 잡는다'는 뜻이다. 그 상태에서 아래 검사들을 읽으면 전부 오독이다.
      (실제 신호를 1개월 선행시키는 방식만으로는 이 둘을 구분할 수 없어 채택하지 않았다)
    """
    d = sig.dropna(subset=["ret_next", "alpha_ls"]).copy()
    if d.empty:
        _rb("S0 누수민감도", "—", np.nan, "SKIP", "표본 없음")
        return
    clean = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    d["_dirty"] = d.groupby("signal_date", observed=True)["ret_next"].rank(pct=True)
    dirty = scg_perf(_ls_series(d, "_dirty"), ppy)["Sharpe"]
    ok = np.isfinite(dirty) and (not np.isfinite(clean) or dirty > clean + 0.5)
    _rb("S0 누수민감도", "오염본 Sharpe − 실제 Sharpe",
        float(dirty - clean) if np.isfinite(dirty) and np.isfinite(clean) else np.nan,
        "PASS" if ok else "FAIL",
        "오염본이 압도적으로 좋아야 정상. 아니면 하네스가 둔감한 것이므로 "
        "아래 모든 결과를 신뢰할 수 없다.")


# ── S1. 증분 기여 (§38, §47) ─────────────────────────────────────────────────────────────
def S1_incremental(sig: pd.DataFrame, ppy: float):
    """§47 의 세 질문에 직접 답한다. 유리하게 해석하지 않는다."""
    series = {}
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol in sig.columns:
            series[name] = _ls_series(sig, acol)
    pairs = [("SCG_0", "BASE_REV", "질문1  Smart Consensus 자체가 단순 리비전을 이기는가"),
             ("SCG_LS", "SCG_0", "질문2  Leadership 에 독립적 추가 알파가 있는가"),
             ("SCG_LSA", "SCG_LS", "질문3  Gap 변화속도에 추가 알파가 있는가")]
    rows = []
    for new, old, q in pairs:
        if new not in series or old not in series:
            rows.append([q, "—", "—", "—", "—", "판정불가(표본없음)"])
            continue
        a, b = series[new].align(series[old], join="inner")
        if len(a) < 6:
            rows.append([q, "—", "—", "—", "—", "판정불가(기간부족)"])
            continue
        sa, sb = scg_perf(a, ppy)["Sharpe"], scg_perf(b, ppy)["Sharpe"]
        diff = a - b
        sd = diff.std(ddof=1)
        t = float(diff.mean() / (sd / np.sqrt(len(diff)))) if sd and sd > 0 else np.nan
        better = np.isfinite(sa) and np.isfinite(sb) and sa > sb
        verdict = ("YES" if better and np.isfinite(t) and abs(t) >= 1.64 else
                   ("약YES" if better else "NO"))
        rows.append([q, _fmt(sb, 2), _fmt(sa, 2), _fmt(sa - sb, 2), _fmt(t, 2), verdict])
        _rb("S1 증분기여", f"{new} vs {old}", float(sa - sb) if np.isfinite(sa - sb) else np.nan,
            verdict, q)
    LOG.table(rows, ["연구질문", "기준 Sharpe", "신규 Sharpe", "차이", "t(차이)", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="§38·§47 증분 기여 — NO 가 나오면 그 구성요소는 불필요한 복잡도입니다. "
                    "제거를 권고하는 것이 정직한 결론입니다")


# ── S2. 파라미터 민감도 (§41) ────────────────────────────────────────────────────────────
def S2_sensitivity(rebuild: Callable[[SCGConfig], Optional[pd.DataFrame]], ppy: float):
    """공식값 45/6/20 을 중심으로 한 칸씩 옮겨 본다. 최적값을 채택하지 않는다."""
    grid = [("Forecast half-life", "FORECAST_HALFLIFE_DAYS", [30.0, 45.0, 60.0]),
            ("Shrinkage K", "K_ACC", [4.0, 6.0, 10.0]),
            ("Leadership horizon", "LEAD_FORWARD_TRADING_DAYS", [10, 20, 40])]
    rows = []
    for label, field, vals in grid:
        for v in vals:
            kw = {field: v}
            if field == "K_ACC":
                kw["K_LEAD"] = v          # 두 수축계수는 같이 움직이는 것이 §42 의 의도
            try:
                s = rebuild(replace(SCG, **kw))
            except Exception as e:
                rows.append([label, str(v), "—", "—", "—", f"실패: {type(e).__name__}"])
                continue
            if s is None or s.empty:
                rows.append([label, str(v), "—", "—", "—", "표본없음"])
                continue
            ls = scg_perf(_ls_series(s, "alpha_ls"), ppy)
            ic = scg_ic(s, "alpha_ls", [20])
            rows.append([label, str(v), _fmt(ls["annualized_return"]), _fmt(ls["Sharpe"], 2),
                         _fmt(float(ic["mean_ic"].iloc[0]) if len(ic) else np.nan),
                         "★ 공식값" if v in (45.0, 6.0, 20) else ""])
    LOG.table(rows, ["파라미터", "값", "LS 연율", "LS Sharpe", "IC(20d)", "비고"],
              ["l", "r", "r", "r", "r", "l"],
              title="§41 민감도 — 공식 V1 은 45/6/20 고정입니다. 이 표에서 가장 좋은 조합을 "
                    "사후에 채택하지 않습니다(그것이 과적합의 정의입니다)")
    fin = [r for r in rows if r[3] not in ("—",)]
    if len(fin) >= 3:
        sh = [float(r[3]) for r in fin]
        _rb("S2 민감도", "Sharpe 범위(max-min)", float(max(sh) - min(sh)),
            "PASS" if (max(sh) - min(sh)) < 1.0 else "주의",
            "파라미터 한 칸에 Sharpe 가 크게 흔들리면 결론이 파라미터에 얹혀 있는 것")


# ── S3. 하위기간 / 연도별 (§47 질문4) ────────────────────────────────────────────────────
def S3_subperiod(sig: pd.DataFrame, ppy: float):
    rows = []
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        ls = _ls_series(sig, acol)
        if ls.empty:
            continue
        y = ls.groupby(pd.DatetimeIndex(ls.index).year).apply(lambda s: float((1 + s).prod() - 1))
        pos = float((y > 0).mean())
        #  최고 성과 연도 하나를 빼면 알파가 사라지는가
        drop1 = y.drop(y.idxmax()) if len(y) > 1 else y
        rows.append([name, f"{len(y)}", f"{100*y.mean():.1f}%", f"{100*pos:.0f}%",
                     f"{y.idxmax()} ({100*y.max():.0f}%)",
                     f"{100*drop1.mean():.1f}%",
                     "의존" if (y.mean() > 0 and drop1.mean() <= 0) else "분산"])
        _rb("S3 하위기간", f"{name} 양(+)연도 비율", pos,
            "PASS" if pos >= 0.6 else "주의", "특정 1~2년 의존 여부")
    LOG.table(rows, ["전략", "연수", "연평균", "양(+)연도", "최고연도", "최고연도 제외 평균", "판정"],
              ["l", "r", "r", "r", "l", "r", "c"],
              title="§47 질문4 — 고성과가 특정 1~2년에만 의존하는가 (LS 기준)")

    #  연도 × 전략 히트맵 표
    yr = {}
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol in sig.columns:
            ls = _ls_series(sig, acol)
            if len(ls):
                yr[name] = ls.groupby(pd.DatetimeIndex(ls.index).year).apply(
                    lambda s: float((1 + s).prod() - 1))
    if yr:
        Y = pd.DataFrame(yr)
        LOG.table([[str(i)] + [f"{100*Y.loc[i, c]:+.1f}%" if c in Y.columns and
                               np.isfinite(Y.loc[i, c]) else "—" for c in Y.columns]
                   for i in Y.index],
                  ["연도"] + list(Y.columns), ["c"] + ["r"] * len(Y.columns),
                  title="연도별 롱숏 수익률 — 네 전략 나란히 (§37 동일 유니버스·동일 리밸런스)")


# ── S4. 종목 집중도 ──────────────────────────────────────────────────────────────────────
def S4_concentration(sig: pd.DataFrame, ppy: float):
    """상위 소수 종목이 성과를 다 만들고 있는가. 그렇다면 재현성이 낮다."""
    d = sig.dropna(subset=["alpha_ls", "ret_next"]).copy()
    if d.empty:
        return
    top = d[d.groupby("signal_date", observed=True)["alpha_ls"].rank(pct=True, ascending=False) <= 0.10]
    if top.empty:
        return
    contrib = top.groupby("stock_id", observed=True)["ret_next"].sum().sort_values(ascending=False)
    tot = float(contrib.sum())
    if abs(tot) < 1e-12:
        return
    n5 = max(1, int(0.05 * len(contrib)))
    share = float(contrib.head(n5).sum() / tot)
    ex = d[~d["stock_id"].isin(contrib.head(n5).index)]
    base = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    exs = scg_perf(_ls_series(ex, "alpha_ls"), ppy)["Sharpe"] if len(ex) else np.nan
    LOG.table([["상위 5% 종목의 기여 비중", f"{100*share:.1f}%"],
               ["전체 Sharpe", _fmt(base, 2)],
               ["상위 5% 종목 제외 Sharpe", _fmt(exs, 2)],
               ["보유 고유종목 수", f"{contrib.shape[0]:,}"]],
              ["항목", "값"], ["l", "r"],
              title="종목 집중도 — 상위 5% 를 빼면 알파가 사라지는가 (우측꼬리 의존성)")
    _rb("S4 집중도", "상위5% 기여비중", share,
        "PASS" if share < 0.5 else "주의", "0.5 초과면 소수 종목 의존")


# ── S5. 레짐 ─────────────────────────────────────────────────────────────────────────────
def S5_regime(sig: pd.DataFrame, bench: Optional[pd.Series], ppy: float):
    if bench is None or not len(bench):
        LOG.info("벤치마크가 없어 레짐 분할을 건너뜁니다.")
        return
    rows = []
    for name, acol in STRATEGY_ALPHA_COLS.items():
        if acol not in sig.columns:
            continue
        ls = _ls_series(sig, acol)
        a, b = ls.align(bench, join="inner")
        if len(a) < 8:
            continue
        up, dn = a[b > 0], a[b <= 0]
        rows.append([name, f"{len(up)}", f"{100*up.mean()*ppy:+.1f}%",
                     f"{len(dn)}", f"{100*dn.mean()*ppy:+.1f}%",
                     "양방향" if (up.mean() > 0 and dn.mean() > 0) else
                     ("상승장 편중" if up.mean() > 0 else "하락장 편중")])
    LOG.table(rows, ["전략", "상승 기간수", "상승장 연율", "하락 기간수", "하락장 연율", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="레짐 분할 — 한쪽 장에서만 작동하면 그것은 알파가 아니라 베타 노출입니다")


# ── S6. 플라시보 ─────────────────────────────────────────────────────────────────────────
def S6_placebo(sig: pd.DataFrame, ppy: float, n_iter: int = 500):
    """알파를 시점 안에서 무작위 섞어 귀무분포를 만든다. 실제 Sharpe 의 p-value."""
    d = sig.dropna(subset=["alpha_ls", "ret_next"])
    if d.empty:
        return
    real = scg_perf(_ls_series(d, "alpha_ls"), ppy)["Sharpe"]
    dates, arrs = [], []
    for T, g in d.groupby("signal_date", observed=True, sort=True):
        if len(g) >= max(10, N_BUCKETS):
            dates.append(T)
            arrs.append(g["ret_next"].to_numpy("float64"))
    if len(arrs) < 8:
        return
    null = np.empty(n_iter)
    for it in range(n_iter):
        per = []
        for r in arrs:
            m = len(r)
            k = max(1, m // N_BUCKETS)
            p = RNG.permutation(m)
            per.append(float(r[p[-k:]].mean() - r[p[:k]].mean()))
        s = pd.Series(per)
        sd = s.std(ddof=1)
        null[it] = float(s.mean() * ppy / (sd * np.sqrt(ppy))) if sd and sd > 0 else 0.0
    p = float((null >= real).mean()) if np.isfinite(real) else np.nan
    LOG.table([["실제 LS Sharpe", _fmt(real, 2)],
               ["귀무분포 평균", _fmt(float(null.mean()), 2)],
               ["귀무분포 95분위", _fmt(float(np.quantile(null, 0.95)), 2)],
               ["p-value (단측)", _fmt(p, 3)],
               ["반복 횟수", f"{n_iter:,}"]],
              ["항목", "값"], ["l", "r"],
              title="플라시보 — 알파를 시점 내에서 섞었을 때의 귀무분포 대비 위치")
    _rb("S6 플라시보", "p-value", p, "PASS" if (np.isfinite(p) and p < 0.05) else "주의",
        "0.05 이상이면 무작위와 구분되지 않음")


# ── S7. 비용 민감도 / 용량 ───────────────────────────────────────────────────────────────
def S7_cost(sig: pd.DataFrame, ppy: float):
    rows = []
    for bps in (0.0, 15.0, 30.0, 60.0, 100.0):
        cells = [f"{bps:.0f}bp"]
        for name, acol in STRATEGY_ALPHA_COLS.items():
            if acol not in sig.columns:
                continue
            bt = scg_bucket_backtest(sig, acol, N_BUCKETS, MIN_STOCKS_PER_DATE, bps)
            cells.append(_fmt(scg_perf(bt["long"], ppy)["Sharpe"], 2))
        rows.append(cells)
    names = [n for n, c in STRATEGY_ALPHA_COLS.items() if c in sig.columns]
    LOG.table(rows, ["편도 비용"] + names, ["l"] + ["r"] * len(names),
              title="거래비용 민감도 (롱온리 최상위 버킷 Sharpe) — 한국 소형주 왕복 60bp 가정이 기본")


def scg_report_robustness():
    if not SCG_ROBUST:
        return
    rows = [[r["test"], r["metric"], _fmt(r["value"]), r["verdict"], _trunc(r["note"], 46)]
            for r in SCG_ROBUST]
    LOG.table(rows, ["검사", "지표", "값", "판정", "설명"], ["l", "l", "r", "c", "l"],
              title="강건성 요약 — FAIL/주의 항목을 '파라미터를 바꿔 통과시키는' 것은 금지입니다")


def scg_run_robustness(sig: pd.DataFrame, bench: Optional[pd.Series],
                       rebuild: Optional[Callable[[SCGConfig], Optional[pd.DataFrame]]],
                       ppy: float, do_sensitivity: bool = True):
    SCG_ROBUST.clear()
    for fn, args, name in (
            (S0_leak_sensitivity, (sig, ppy), "S0 누수민감도"),
            (S1_incremental, (sig, ppy), "S1 증분기여"),
            (S3_subperiod, (sig, ppy), "S3 하위기간"),
            (S4_concentration, (sig, ppy), "S4 집중도"),
            (S5_regime, (sig, bench, ppy), "S5 레짐"),
            (S6_placebo, (sig, ppy), "S6 플라시보"),
            (S7_cost, (sig, ppy), "S7 비용")):
        try:
            fn(*args)
        except Exception as e:                       # 한 검사의 실패가 나머지를 죽이지 않게
            LOG.warn(f"{name} 실패: {type(e).__name__}: {e}")
            _rb(name, "—", np.nan, "ERROR", f"{type(e).__name__}: {e}")
    if do_sensitivity and rebuild is not None:
        try:
            S2_sensitivity(rebuild, ppy)
        except Exception as e:
            LOG.warn(f"S2 민감도 실패: {type(e).__name__}: {e}")
    scg_report_robustness()



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단 카드 (§37~§40, §46~§47)                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _p(v: Any, nd: int = 2, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    try:
        return f"{100*float(v):+.{nd}f}%" if pct else f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


def scg_report_performance(res: Dict[str, Any], label: str = ""):
    """§37 — 네 전략 나란히. 동일 유니버스·동일 리밸런스."""
    P = res.get("performance")
    if P is None or P.empty:
        LOG.warn("성과표를 만들 표본이 없습니다.")
        return
    rows = []
    for _, r in P.iterrows():
        rows.append([r["strategy"], f"{int(r['n_signals']):,}", f"{int(r['n_unique_stocks']):,}",
                     _p(r["annualized_return"], 1, True), _p(r["CAGR"], 1, True),
                     _p(r["volatility"], 1, True), _p(r["Sharpe"]),
                     _p(r["MDD"], 1, True), _p(r["hit_rate"], 1, True),
                     _p(r["turnover"], 2), _p(r["average_holdings"], 0),
                     _p(r.get("excess_vs_bench"), 1, True)])
    LOG.table(rows, ["전략", "신호수", "고유종목", "연율", "CAGR", "변동성", "Sharpe",
                     "MDD", "적중률", "회전율", "평균보유", "벤치대비"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              title=f"§37 전략별 성과 — 최상위 버킷 롱온리 · 거래비용 {BT_COST_BPS:.0f}bp 반영"
                    + (f"  [{label}]" if label else ""))
    rows = [[r["strategy"], _p(r["LS_annual"], 1, True), _p(r["LS_Sharpe"])]
            for _, r in P.iterrows()]
    LOG.table(rows, ["전략", "롱숏 연율", "롱숏 Sharpe"], ["l", "r", "r"],
              title="롱숏(최상위−최하위) — 시장방향을 제거한 순수 신호력")


def scg_report_buckets(res: Dict[str, Any]):
    """§39 단조성 — D1~D10 이 계단으로 올라가는가."""
    per = res.get("per_strategy", {})
    if not per:
        return
    names = list(per)
    ref = per[names[0]]["bt"]["summary"]
    if ref is None or ref.empty:
        return
    buckets = list(ref["bucket"])
    rows = []
    for b in buckets:
        cells = [f"D{int(b)}"]
        for n in names:
            s = per[n]["bt"]["summary"]
            v = s.loc[s["bucket"] == b, "mean_ret"]
            cells.append(_p(float(v.iloc[0]) if len(v) else np.nan, 2, True))
        rows.append(cells)
    LOG.table(rows, ["버킷"] + names, ["c"] + ["r"] * len(names),
              title=f"§39 십분위 평균 기간수익률 (D{int(max(buckets))} = 알파 최상위) — "
                    f"계단이 우상향해야 신호에 정보가 있다는 뜻입니다")

    mono = res.get("monotonicity")
    if mono is not None and not mono.empty:
        rows = [[r["strategy"], f"{int(r['n_buckets'])}", _p(r["spearman"], 3),
                 _p(r["top_minus_bottom"], 2, True),
                 "✔ 단조" if (np.isfinite(r["spearman"]) and r["spearman"] >= 0.6) else
                 ("△ 약함" if (np.isfinite(r["spearman"]) and r["spearman"] > 0) else "✘ 없음")]
                for _, r in mono.iterrows()]
        LOG.table(rows, ["전략", "버킷수", "Spearman(버킷,수익)", "최상−최하", "판정"],
                  ["l", "r", "r", "r", "c"],
                  title="§39 단조성 — Spearman 이 높을수록 '점수가 높을수록 수익도 높다'가 성립")


def scg_report_ic(res: Dict[str, Any]):
    """§40 — 20/60/120 거래일 forward IC."""
    IC = res.get("ic")
    if IC is None or IC.empty:
        LOG.warn("IC 를 계산할 표본이 없습니다.")
        return
    rows = []
    for _, r in IC.iterrows():
        rows.append([r["strategy"], f"{int(r['horizon_td'])}d", f"{int(r['n_dates'])}",
                     _p(r["mean_ic"], 4), _p(r["median_ic"], 4), _p(r["ic_std"], 4),
                     _p(r["ic_ir"], 3), _p(r["positive_ic_ratio"], 2),
                     _p(r["t_stat"], 2)])
    LOG.table(rows, ["전략", "지평", "시점수", "평균IC", "중앙IC", "IC표준편차",
                     "IC_IR", "양(+)비율", "t"],
              ["l", "c", "r", "r", "r", "r", "r", "r", "r"],
              title="§40 Forward IC — 세 지평의 부호가 같아야 신호가 일관됩니다 (§47 질문6)")
    #  지평 간 부호 일관성
    for s, g in IC.groupby("strategy"):
        sg = np.sign(g["mean_ic"].to_numpy())
        if len(sg) >= 2 and not (np.all(sg >= 0) or np.all(sg <= 0)):
            LOG.warn(f"{s}: 지평별 IC 부호가 엇갈립니다 {dict(zip(g['horizon_td'], g['mean_ic'].round(4)))} "
                     f"— 단기 반전/장기 지속이 섞였을 수 있습니다. 그대로 보고합니다.")


def scg_report_interpretation(sig: pd.DataFrame, res: Dict[str, Any]):
    """§46 경제적 의미 + §47 연구질문에 대한 답을 한 화면에 모은다."""
    LOG.banner("해석표 — §46 경제적 의미 · §47 연구질문",
               "숫자를 유리하게 읽지 않는다. NO 는 NO 라고 쓴다.")
    ok = sig["status"].eq(STATUS_OK) if "status" in sig.columns else pd.Series(True, index=sig.index)
    d = sig[ok]
    if d.empty:
        LOG.warn("유효 신호가 없어 해석표를 만들 수 없습니다.")
        return

    pos_ls = float((d["scg_ls"] > 0).mean()) if "scg_ls" in d.columns else np.nan
    pos_ac = float((d["scg_accel_20d"] > 0).mean()) if "scg_accel_20d" in d.columns else np.nan
    corr = (float(d["scg_ls"].corr(d["base_revision_20d"], method="spearman"))
            if {"scg_ls", "base_revision_20d"} <= set(d.columns) else np.nan)
    corr0 = (float(d["scg_ls"].corr(d["scg0"], method="spearman"))
             if {"scg_ls", "scg0"} <= set(d.columns) else np.nan)
    LOG.table([
        ["SCG_LS > 0 인 관측 비중", _p(pos_ls, 1, True).replace("+", ""),
         "정보력 높은 애널리스트 집단이 일반 컨센서스보다 높은 전망을 낸 종목의 비중"],
        ["SCG_ACCEL > 0 비중", _p(pos_ac, 1, True).replace("+", ""),
         "그 격차가 최근 더 빠르게 벌어지는 종목의 비중"],
        ["corr(SCG_LS, BASE_REV)", _p(corr, 3),
         "낮을수록 단순 리비전과 다른 정보를 담고 있다는 뜻"],
        ["corr(SCG_LS, SCG_0)", _p(corr0, 3),
         "1.0 에 가까우면 Leadership 이 사실상 아무것도 바꾸지 않은 것"],
        ["평균 애널리스트 수", _p(float(d["analyst_count"].mean()), 1),
         "얇으면 컨센서스 자체가 노이즈"],
    ], ["지표", "값", "읽는 법"], ["l", "r", "l"],
        title="§46 — 전략이 노리는 현상: 정보발생 → 고정보력 analyst 선행 → Smart Consensus 선행 "
              "→ 일반 Consensus 지연 → 가격 반영")

    P = res.get("performance")
    if P is not None and not P.empty:
        g = P.set_index("strategy")
        def sh(n):
            return float(g.loc[n, "Sharpe"]) if n in g.index else np.nan
        q = [("질문1  SCG_0 > BASE_REV ?", sh("SCG_0"), sh("BASE_REV"),
              "Smart Consensus 자체가 의미 있는가"),
             ("질문2  SCG_LS > SCG_0 ?", sh("SCG_LS"), sh("SCG_0"),
              "Leadership 에 독립적 추가 알파가 있는가"),
             ("질문3  SCG_LSA > SCG_LS ?", sh("SCG_LSA"), sh("SCG_LS"),
              "Gap 변화속도에 추가 알파가 있는가")]
        rows = [[name, _p(b), _p(a), _p(a - b) if np.isfinite(a) and np.isfinite(b) else "—",
                 ("YES" if (np.isfinite(a) and np.isfinite(b) and a > b) else "NO"), why]
                for name, a, b, why in q]
        LOG.table(rows, ["연구질문", "기준", "신규", "차이", "답", "의미"],
                  ["l", "r", "r", "r", "c", "l"],
                  title="§47 연구질문 — 롱온리 Sharpe 기준. NO 면 그 구성요소는 제거를 권고합니다")
        no = [r[0].split()[0] for r in rows if r[4] == "NO"]
        if no:
            LOG.warn(f"{', '.join(no)} 이 NO 입니다. 명세 §38 에 따라 명확히 보고합니다: "
                     f"해당 구성요소는 이 표본에서 추가 알파를 보이지 않았습니다. "
                     f"파라미터를 바꿔 YES 로 만들지 마십시오 — 그것이 과적합입니다.")


def scg_diagnostic_card(sig: pd.DataFrame, res: Dict[str, Any], scores: pd.DataFrame,
                        metric: str, universe: str):
    """실행 한 번의 요약 카드 — 무엇을 봤고 무엇을 못 봤는지."""
    ok = sig["status"].eq(STATUS_OK) if "status" in sig.columns else pd.Series(True, index=sig.index)
    d = sig[ok]
    n_an = int(scores["analyst_id"].nunique()) if scores is not None and len(scores) else 0
    with_acc = with_lead = neither = 0
    if scores is not None and len(scores):
        g = scores.groupby("analyst_id")[["acc_n", "lead_n"]].max()
        with_acc = int((g["acc_n"] > 0).sum())
        with_lead = int((g["lead_n"] > 0).sum())
        #  ★ max(with_acc, with_lead) 로 빼면 '한쪽만 있는' 애널리스트가 둘 다 없는 것으로
        #    잘못 집계된다. 실제로 둘 다 0 인 사람을 센다.
        neither = int(((g["acc_n"] == 0) & (g["lead_n"] == 0)).sum())
    LOG.table([
        ["메트릭 트랙", metric], ["유니버스", universe],
        ["신호 시점", f"{d['signal_date'].nunique() if len(d) else 0}개"],
        ["유효 신호", f"{len(d):,}행"],
        ["고유 종목", f"{d['stock_id'].nunique() if len(d) else 0:,}"],
        ["회계기간 수", f"{d['fiscal_period'].nunique() if len(d) else 0}"],
        ["애널리스트", f"{n_an:,}명"],
        ["  ├ Accuracy 이력 보유", f"{with_acc:,}명 ({100*with_acc/max(n_an,1):.0f}%)"],
        ["  └ Leadership 이력 보유", f"{with_lead:,}명 ({100*with_lead/max(n_an,1):.0f}%)"],
        ["이력 없어 중립(0) 처리", f"{neither:,}명 — 탈락 아님(§32)"],
    ], ["항목", "값"], ["l", "r"],
        title=f"진단 카드 — {metric} / {universe}")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0  자체검증 — §35 TEST 1~9 + 합성데이터 엔드투엔드 스모크                                ║
# ║                                                                                          ║
# ║  ★ 실데이터를 한 줄도 건드리기 전에 여기를 통과해야 한다.                                   ║
# ║    수집이 오래 걸리는 파이프라인에서 계산경로 버그를 4시간 뒤에 발견하는 것만큼               ║
# ║    비싼 것이 없다. 합성데이터는 정답을 알고 있으므로 계산경로를 '증명'할 수 있다.            ║
# ║                                                                                          ║
# ║  ★ 그리고 §48 의 완료조건은 "코드가 돌았다"가 아니라 "아래가 전부 PASS 다" 이다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SCG_TESTS: List[Dict[str, Any]] = []


def _t(tid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, f"{type(e).__name__}: {e}"
    SCG_TESTS.append({"id": tid, "name": name, "ok": bool(ok), "msg": str(msg)})


def _synth_forecasts(rows) -> pd.DataFrame:
    f = pd.DataFrame(rows, columns=["stock_id", "analyst_id", "report_date",
                                    "fiscal_period", "forecast_value"])
    f["broker_id"] = "B"
    f["forecast_metric"] = "EPS"
    f["report_id"] = [f"r{i}" for i in range(len(f))]
    f["report_date"] = as_ts_series(f["report_date"])
    return f


def _synth_calendar() -> pd.DatetimeIndex:
    return pd.bdate_range("2012-01-01", "2028-12-31")


def scg_run_tests(strict: bool = True) -> bool:
    """§35 TEST 1~9. 합성데이터라 정답을 알고 있으므로 '통과/실패'가 명확하다."""
    SCG_TESTS.clear()
    CAL = _synth_calendar()
    NOSC = pd.DataFrame(columns=["signal_date", "analyst_id", "acc_star", "lead_star"])

    # ── TEST 1 — 모든 전망이 같으면 Smart == Equal, SCG == 0 ─────────────────────────
    def t1():
        f = _synth_forecasts([("A", f"an{j}", d, "2020-12", 100.0)
                              for j in range(4) for d in ("2019-03-01", "2019-06-01")])
        sd = pd.DatetimeIndex(["2019-07-31", "2019-08-30"])
        sc, _ = compute_smart_consensus(build_active_forecasts(f, sd), NOSC)
        sg = build_scg_signals(sc, CAL)
        a = np.allclose(sc["smart_consensus_ls"], sc["consensus_equal_weight"])
        b = np.allclose(sg["scg_ls"].dropna(), 0.0) and np.allclose(sg["scg0"].dropna(), 0.0)
        return (a and b), "전망이 모두 같을 때 Smart==Equal 이고 SCG==0"

    # ── TEST 2 — 이력 없는 애널리스트는 중립(0), multiplier=1, 탈락 없음 ──────────────
    def t2():
        f = _synth_forecasts([("A", "x", "2020-03-01", "2020-12", 10.0),
                              ("A", "y", "2020-03-01", "2020-12", 12.0)])
        sd = pd.DatetimeIndex(["2020-03-31"])
        S = build_analyst_scores(sd, pd.DataFrame(), pd.DataFrame())
        _, w = compute_smart_consensus(build_active_forecasts(f, sd), S)
        ok = (len(S) == 0 and np.allclose(w["acc_star"], 0) and np.allclose(w["lead_star"], 0)
              and np.allclose(w["quality_multiplier_ls"], 1.0)
              and np.allclose(w["quality_multiplier_scg0"], 1.0) and len(w) == 2)
        return ok, "이력이 없어도 애널리스트 2명 전원 유지 · Q=0 · multiplier=1"

    # ── TEST 3 — 정확했던 애널리스트가 더 큰 가중치 ──────────────────────────────────
    def t3():
        rows, acts = [], []
        for k in range(10):
            y = 2013 + k
            fp, ad = f"{y}-12", as_ts(f"{y+1}-03-15")
            rd = ad - pd.Timedelta(days=60)
            rows += [("A", "good", rd, fp, 100.0), ("A", "bad", rd, fp, 60.0),
                     ("A", "mid", rd, fp, 100.0)]
            acts.append(("A", fp, "EPS", 100.0, ad))
        ae = build_accuracy_events(_synth_forecasts(rows), pd.DataFrame(
            acts, columns=["stock_id", "fiscal_period", "forecast_metric",
                           "actual_value", "actual_announcement_date"]))
        sd = pd.DatetimeIndex(["2024-01-31"])
        S = build_analyst_scores(sd, ae, pd.DataFrame())
        fw = _synth_forecasts([("A", "good", "2024-01-20", "2025-12", 10.0),
                               ("A", "bad", "2024-01-20", "2025-12", 10.0)])
        _, w = compute_smart_consensus(build_active_forecasts(fw, sd), S)
        ww = w.set_index("analyst_id")["weight_ls"]
        si = S.set_index("analyst_id")
        ok = (si.loc["good", "acc_star"] > si.loc["bad", "acc_star"]
              and si.loc["bad", "acc_star"] < 0 and ww["good"] > ww["bad"])
        return ok, (f"ACC* good={si.loc['good','acc_star']:+.3f} bad={si.loc['bad','acc_star']:+.3f} "
                    f"→ weight {ww['good']:.3f} > {ww['bad']:.3f}")

    # ── TEST 4 — 선행한 애널리스트의 LEAD* 가 더 큼 ──────────────────────────────────
    def t4():
        rows = []
        for k in range(12):
            t0 = as_ts("2018-01-05") + pd.DateOffset(months=3 * k)
            t20 = CAL[CAL.searchsorted(t0) + 20]
            rows += [("S", "lead", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "lead", t0, "2030-12", 120.0),
                     ("S", "p1", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "p2", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S", "p1", t20, "2030-12", 130.0), ("S", "p2", t20, "2030-12", 130.0),
                     ("S2", "flat", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S2", "flat", t0, "2030-12", 120.0),
                     ("S2", "q1", t0 - pd.Timedelta(days=5), "2030-12", 100.0),
                     ("S2", "q2", t0 - pd.Timedelta(days=5), "2030-12", 100.0)]
        le = build_leadership_events(_synth_forecasts(rows), CAL)
        if le.empty:
            return False, "Leadership 이벤트가 하나도 생성되지 않음"
        S = build_analyst_scores(pd.DatetimeIndex(["2021-06-30"]), pd.DataFrame(), le)
        si = S.set_index("analyst_id")
        ok = ("lead" in si.index and "flat" in si.index
              and si.loc["lead", "lead_star"] > si.loc["flat", "lead_star"]
              and si.loc["lead", "lead_star"] > 0)
        return ok, (f"LEAD* lead={si.loc['lead','lead_star']:+.4f} "
                    f"flat={si.loc['flat','lead_star']:+.4f} (이벤트 {len(le):,}건)")

    # ── TEST 5 — 최근 전망일수록 큰 가중치 (반감기 45일) ─────────────────────────────
    def t5():
        T = as_ts("2020-06-30")
        f = _synth_forecasts([("A", "d0", T, "2020-12", 10.0),
                              ("A", "d45", T - pd.Timedelta(days=45), "2020-12", 10.0),
                              ("A", "d90", T - pd.Timedelta(days=90), "2020-12", 10.0)])
        _, w = compute_smart_consensus(build_active_forecasts(f, pd.DatetimeIndex([T])), NOSC)
        ws = w.set_index("analyst_id")["weight_ls"]
        ok = (ws["d0"] > ws["d45"] > ws["d90"]
              and abs(ws["d45"] / ws["d0"] - 0.5) < 1e-9
              and abs(ws["d90"] / ws["d0"] - 0.25) < 1e-9)
        return ok, f"0일 {ws['d0']:.4f} > 45일 {ws['d45']:.4f} > 90일 {ws['d90']:.4f} (정확히 반감)"

    # ── TEST 6 — 미래누수 차단 ───────────────────────────────────────────────────────
    def t6():
        ad = as_ts("2020-03-15")
        rows = [("A", "x", ad - pd.Timedelta(days=30), "2019-12", 90.0),
                ("A", "y", ad - pd.Timedelta(days=30), "2019-12", 110.0)]
        ae = build_accuracy_events(_synth_forecasts(rows), pd.DataFrame(
            [("A", "2019-12", "EPS", 100.0, ad)],
            columns=["stock_id", "fiscal_period", "forecast_metric",
                     "actual_value", "actual_announcement_date"]))
        before = build_analyst_scores(pd.DatetimeIndex([ad]), ae, pd.DataFrame())
        after = build_analyst_scores(pd.DatetimeIndex([ad + pd.Timedelta(days=1)]), ae, pd.DataFrame())
        n_b = 0 if before.empty else int(before["acc_n"].max())
        n_a = 0 if after.empty else int(after["acc_n"].max())
        return (n_b == 0 and n_a == 1), f"발표 당일 사건수={n_b} (0이어야 함) · 익일={n_a} (1이어야 함)"

    # ── TEST 7 — leave-one-out: peer 에 자기 자신이 절대 없어야 함 ───────────────────
    def t7():
        rows = []
        for k in range(6):
            t0 = as_ts("2019-02-01") + pd.DateOffset(months=4 * k)
            t20 = CAL[CAL.searchsorted(t0) + 20]
            rows += [("S", "a", t0 - pd.Timedelta(days=3), "2031-12", 100.0),
                     ("S", "a", t0, "2031-12", 130.0),
                     ("S", "b", t0 - pd.Timedelta(days=3), "2031-12", 90.0),
                     ("S", "c", t0 - pd.Timedelta(days=3), "2031-12", 110.0),
                     ("S", "b", t20, "2031-12", 120.0)]
        f = _synth_forecasts(rows)
        le = build_leadership_events(f, CAL)
        if le.empty:
            return False, "이벤트 없음"
        if le["self_in_peer_t0"].any() or le["self_in_peer_t20"].any():
            return False, "peer 집합에 이벤트 소유자가 포함됨 — leave-one-out 위반"
        #  O(n²) 참조구현과 정면 대조
        v = _scg_validity(f.copy(), SCG)
        bad = 0
        for r in le.itertuples(index=False):
            for tcol, ccol, ncol in (("event_date", "peer_consensus_t0", "peer_count_t0"),
                                     ("outcome_date", "peer_consensus_t20", "peer_count_t20")):
                t = getattr(r, tcol)
                m = ((v["valid_start"] <= t) & (v["valid_end"] >= t)
                     & v["stock_id"].eq(r.stock_id) & v["fiscal_period"].eq(r.fiscal_period)
                     & v["forecast_metric"].eq(r.forecast_metric)
                     & v["analyst_id"].ne(r.analyst_id))
                s = v.loc[m, "forecast_value"]
                if len(s) != getattr(r, ncol) or abs(float(s.mean()) - getattr(r, ccol)) > 1e-9:
                    bad += 1
        return bad == 0, f"참조구현(O(n²)) 대조 {2*len(le):,}건 중 불일치 {bad}건"

    # ── TEST 8 — 1인 1표 ─────────────────────────────────────────────────────────────
    def t8():
        f = _synth_forecasts([("A", "x", "2020-01-10", "2020-12", 1.0),
                              ("A", "x", "2020-02-10", "2020-12", 2.0),
                              ("A", "x", "2020-03-10", "2020-12", 3.0),
                              ("A", "x", "2020-03-10", "2021-12", 9.0),
                              ("A", "y", "2020-03-01", "2020-12", 5.0)])
        a = build_active_forecasts(f, pd.DatetimeIndex(["2020-03-31"]))
        dup = a.groupby(["signal_date", "stock_id", "analyst_id", "fiscal_period",
                         "forecast_metric"]).size()
        latest = float(a.loc[(a.analyst_id == "x") & (a.fiscal_period == "2020-12"),
                             "forecast_value"].iloc[0])
        c = compute_equal_consensus(a)
        sep = c["fiscal_period"].nunique() == 2
        return (int(dup.max()) == 1 and latest == 3.0 and sep), \
            f"활성 전망 최대 {int(dup.max())}건 · 최신값 채택 {latest} · 회계기간 분리 {sep}"

    # ── TEST 9 — 표본 보존 (§35-9) ───────────────────────────────────────────────────
    def t9():
        rows = []
        for i in range(60):
            rows += [(f"K{i:03d}", "a", "2020-03-01", "2020-12", 100.0 + i),
                     (f"K{i:03d}", "b", "2020-03-01", "2020-12", 101.0 + i)]
        rows += [("SOLO", "a", "2020-03-01", "2020-12", 5.0),
                 ("NEG", "a", "2020-03-01", "2020-12", -50.0),
                 ("NEG", "b", "2020-03-01", "2020-12", -30.0),
                 ("ZERO", "a", "2020-03-01", "2020-12", 0.001),
                 ("ZERO", "b", "2020-03-01", "2020-12", -0.001)]
        sd = pd.DatetimeIndex(["2020-03-31"])
        act = build_active_forecasts(_synth_forecasts(rows), sd)
        sc, _ = compute_smart_consensus(act, NOSC)
        sg = build_scg_signals(sc, CAL)
        u_eq = set(sg.loc[sg["consensus_equal_weight"].notna() &
                          sg["status"].eq(STATUS_OK), "stock_id"])
        u_0 = set(sg.loc[sg["scg0"].notna(), "stock_id"])
        u_ls = set(sg.loc[sg["scg_ls"].notna(), "stock_id"])
        finite = bool(np.isfinite(sg["scg_ls"].dropna()).all())
        keeps = {"NEG", "ZERO"} <= set(sg["stock_id"])
        solo = sg.loc[sg["stock_id"].eq("SOLO"), "status"].iloc[0] == STATUS_INSUFFICIENT
        return (u_eq == u_0 == u_ls and finite and keeps and solo), \
            (f"유니버스 equal={len(u_eq)} scg0={len(u_0)} scg_ls={len(u_ls)} (동일해야 함) · "
             f"음수/0근처 EPS 종목 유지 · 1인 종목은 INSUFFICIENT")

    # ── 추가 — 미래 report_date 즉시 오류 (§32) ──────────────────────────────────────
    def t10():
        try:
            build_active_forecasts(_synth_forecasts([("A", "a", "2035-01-01", "2020-12", 1.0)]),
                                   pd.DatetimeIndex(["2020-03-31"]))
        except ValueError:
            return True, "미래 발간일 전망을 ValueError 로 즉시 거부"
        return False, "미래 발간일을 통과시켰습니다 — §32 위반"

    # ── 추가 — 파라미터가 실제로 산식을 바꾸는가 (배선 검정) ────────────────────────
    def t11():
        T = as_ts("2020-06-30")
        f = _synth_forecasts([("A", "x", T - pd.Timedelta(days=45), "2020-12", 10.0),
                              ("A", "y", T, "2020-12", 20.0)])
        a = build_active_forecasts(f, pd.DatetimeIndex([T]))
        _, w1 = compute_smart_consensus(a, NOSC, SCG)
        _, w2 = compute_smart_consensus(a, NOSC, replace(SCG, FORECAST_HALFLIFE_DAYS=90.0))
        r1 = float(w1.set_index("analyst_id")["weight_ls"]["x"])
        r2 = float(w2.set_index("analyst_id")["weight_ls"]["x"])
        return (abs(r1 - 0.5) < 1e-9 and abs(r2 - 2 ** -0.5) < 1e-9), \
            f"half-life 45→{r1:.4f}, 90→{r2:.4f} (설정이 실제로 산식에 연결되어 있음)"

    _t("TEST1", "Equal forecast invariance (§35-1)", t1)
    _t("TEST2", "Neutral analyst shrinkage (§35-2)", t2)
    _t("TEST3", "Accuracy reward (§35-3)", t3)
    _t("TEST4", "Leadership reward (§35-4)", t4)
    _t("TEST5", "Recency weighting (§35-5)", t5)
    _t("TEST6", "No future leakage (§35-6)", t6)
    _t("TEST7", "Leave-one-out (§35-7)", t7)
    _t("TEST8", "No analyst duplication (§35-8)", t8)
    _t("TEST9", "Sample preservation (§35-9)", t9)
    _t("EXTRA1", "미래 report_date 즉시 오류 (§32)", t10)
    _t("EXTRA2", "config 배선 검정 (파라미터가 산식에 연결됨)", t11)

    rows = [[t["id"], t["name"], "PASS" if t["ok"] else "FAIL", _trunc(t["msg"], 60)]
            for t in SCG_TESTS]
    LOG.table(rows, ["ID", "검사", "결과", "근거"], ["l", "l", "c", "l"],
              title="§35 자체검증 — 합성데이터라 정답을 알고 있으므로 통과/실패가 명확합니다")
    n_fail = sum(1 for t in SCG_TESTS if not t["ok"])
    if n_fail:
        msg = ("자체검증 실패 " + str(n_fail) + "건: " +
               ", ".join(t["id"] for t in SCG_TESTS if not t["ok"]) +
               " — 실데이터 수집을 시작하지 않습니다. 산식이 명세와 어긋나 있습니다.")
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"자체검증 {len(SCG_TESTS)}건 전부 통과 — 계산경로가 명세 §35 를 만족합니다")
    return True


def scg_smoke(n_stocks: int = 90, n_months: int = 48) -> Dict[str, Any]:
    """합성데이터 엔드투엔드 — 수집부를 제외한 전 출력물을 예행연습한다.

    ★ 알파가 '있는' 데이터를 일부러 만든다: 정확한 애널리스트의 전망이 미래수익률과
      약하게 연동되도록 한다. 그래야 백테스트·IC·단조성 표가 의미 있는 숫자로 나오고,
      표가 전부 0 이면 '데이터가 없어서'가 아니라 '경로가 끊겨서'임을 알 수 있다.
    """
    rng = np.random.default_rng(SEED)
    cal = _synth_calendar()
    cal = cal[(cal >= as_ts("2015-01-01")) & (cal <= as_ts("2026-12-31"))]
    sd = pd.DatetimeIndex(pd.Series(cal, index=cal).groupby(
        pd.Series(cal, index=cal).index.to_period("M")).max().values)[-n_months:]
    codes = [f"S{i:04d}" for i in range(n_stocks)]
    analysts = [f"AN{j:03d}" for j in range(40)]
    skill = {a: float(rng.normal(0, 1)) for a in analysts}     # 잠재 실력

    # 종목별 '진짜' EPS 경로
    truth = {c: float(rng.uniform(200, 5000)) for c in codes}
    rows, acts, prices = [], [], []
    for c in codes:
        base = truth[c]
        p0 = base * rng.uniform(8, 20)
        for y in range(2015, 2027):
            a_val = base * (1 + 0.10 * rng.normal())
            acts.append((c, f"{y}-12", "EPS", a_val, as_ts(f"{y+1}-03-20")))
            for a in rng.choice(analysts, size=int(rng.integers(2, 9)), replace=False):
                for m in (3, 6, 9, 12):
                    err = rng.normal(0, 0.18) / (1.0 + 0.9 * max(skill[a], 0))
                    rows.append((c, a, as_ts(f"{y}-{m:02d}-10"), f"{y}-12", a_val * (1 + err)))
        # 가격: 스마트 컨센서스가 앞서가는 종목이 이후 오르도록 약한 신호를 심는다
        r = rng.normal(0.004, 0.06, len(cal)) + 0.02 * np.tanh(skill.get(analysts[0], 0))
        px = p0 * np.exp(np.cumsum(r * 0.2))
        prices.append(pd.DataFrame({"code": c, "date": cal, "close_adj": px,
                                    "volume": 10000.0, "amount": px * 10000.0, "src": "synth"}))
    f = _synth_forecasts(rows)
    A = pd.DataFrame(acts, columns=["stock_id", "fiscal_period", "forecast_metric",
                                    "actual_value", "actual_announcement_date"])
    px = pd.concat(prices, ignore_index=True)

    ae = build_accuracy_events(f, A)
    le = build_leadership_events(f, cal)
    S = build_analyst_scores(sd, ae, le)
    act = build_active_forecasts(f, sd)
    sc, w = compute_smart_consensus(act, S)
    sig = build_scg_signals(sc, cal)
    sig = scg_forward_returns(sig, px, cal, IC_HORIZONS_TD)
    res = scg_run_all_strategies(sig, SCG, None, label="SMOKE")
    return {"signals": sig, "scores": S, "weights": w, "res": res,
            "accuracy_events": ae, "leadership_events": le, "prices": px, "calendar": cal}



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ║                                                                                          ║
# ║  실패하면 어디서 실패했는지, 무엇이 몇 행 들어가고 나왔는지가 자동으로 출력된다              ║
# ║  (PIPE.stage 안에서만 연산이 돈다). 그것이 사용자가 요구한 '에러 국소화' 다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def scg_offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f       # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML     # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{base64.b64encode(b).decode()}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def scg_collect(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    warm_start = (as_ts(BACKTEST_START) - pd.DateOffset(years=HISTORY_WARMUP_YEARS)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.SPINE", "일별 전종목시세 스파인 (KRX 미호출)", "L1", budget_s=3600):
        years = list(range(as_ts(warm_start).year, as_ts(BACKTEST_END).year + 1))
        S, META = scg_fetch_spine(years)
        ctx["spine_meta"] = META

    with PIPE.stage("L1.UNI", "종목 마스터 · 거래일 캘린더", "L1", budget_s=900):
        listing = scg_fetch_listing()
        delist = scg_fetch_delisting()
        corpcode = scg_fetch_dart_corpcode()
        if len(S):
            sec = scg_spine_master(S, META)
            if len(listing):
                add = listing[["code", "industry"]].drop_duplicates("code")
                sec = sec.drop(columns=["industry"]).merge(add, on="code", how="left")
                sec["industry"] = sec["industry"].fillna("")
            if len(delist):
                dl = delist[["code", "delisting_date"]].dropna().drop_duplicates("code")
                sec = sec.merge(dl.rename(columns={"delisting_date": "_dl2"}), on="code", how="left")
                #  두 근거가 다르면 **이른 쪽**을 쓴다(늦게 빼면 없는 종목을 들고 있게 된다)
                sec["delisting_date"] = sec[["delisting_date", "_dl2"]].min(axis=1)
                sec = sec.drop(columns=["_dl2"])
            if len(corpcode):
                cc = corpcode.dropna(subset=["code"]).drop_duplicates("code")
                sec = sec.drop(columns=["corp_code"]).merge(cc[["code", "corp_code"]],
                                                            on="code", how="left")
            n0 = len(sec)
            is_common = sec["code"].str.len().eq(6) & sec["code"].str[5].eq("0")
            bad = sec["name"].astype(str).str.contains(_SCG_NONEQUITY_NAME, na=False)
            sec = sec[is_common & ~bad].copy()
            LOG.info(f"종목 마스터 {n0:,} → 보통주 {len(sec):,}건 "
                     f"(우선주 등 {int((~is_common).sum()):,} · 스팩/ETF/리츠 {int(bad.sum()):,} 제외) · "
                     f"폐지 이력 {int(sec['delisting_date'].notna().sum()):,}건")
            cal = scg_spine_calendar(S)
        else:
            LOG.warn("스파인이 없어 상장/폐지목록 기반 경로로 폴백합니다 "
                     "(정확도가 낮고 폐지목록 누락분만큼 생존자편향이 남습니다).")
            sec = scg_build_security_master(listing, delist, corpcode)
            cal = pd.DatetimeIndex([])
        ctx["sec"] = sec

    with PIPE.stage("L1.PX", "가격 패널 · 벤치마크", "L1", budget_s=3600):
        bench = scg_fetch_benchmark(warm_start, BACKTEST_END)
        if len(S):
            #  ★ 종목별 가격 수집이 **한 건도** 없다. 스파인의 ChangesRatio 로 수정주가
            #    계열을 만든다(KRX 기준가 기반이라 분할·증자가 이미 보정돼 있다).
            #    이전 구조는 여기서 2,800종목을 하나씩 HTTP 로 다시 긁었다.
            S = scg_spine_close_adj(S)
            px = scg_spine_prices(S)
            ctx["px_unadj"] = S[["code", "date", "close_unadj"]].assign(
                adj_factor=(S["close_adj"] / S["close_unadj"].replace(0, np.nan)).astype("float32"),
                src="marcap")
            ctx["px_unadj"]["code"] = ctx["px_unadj"]["code"].astype(str)
            LOG.ok(f"가격 패널 {len(px):,}행 · {px['code'].nunique():,}종목 — "
                   f"스파인에서 파생(종목별 HTTP 0회)")
            if not len(cal):
                cal = scg_build_calendar(px, bench)
        else:
            codes = ctx["sec"]["code"].dropna().astype(str).tolist()
            px = scg_fetch_prices(codes, warm_start, BACKTEST_END)
            cal = scg_build_calendar(px, bench)
            ctx["px_unadj"] = scg_fetch_unadjusted(codes, warm_start, BACKTEST_END, px_adj=px)
            ctx["sec"] = scg_infer_delisting_from_prices(
                scg_first_trade_dates(ctx["sec"], px), px, cal.values.astype("datetime64[ns]"))
        ctx.update(px=px, bench=bench, calendar=cal, spine=S)
        ctx["signal_dates"] = scg_signal_dates(cal, SIGNAL_FREQ)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 · 원장", "L1", budget_s=7200, critical=False):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
                 "로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        #  ★ 증분 수집 — 캐시에 이미 있는 구간은 다시 긁지 않는다.
        #    이전 구조는 매 실행 15년치 리스트 페이지를 통째로 재크롤했다. 시간 낭비이자
        #    차단 위험이고, 무엇보다 이미 드라이브에 있는 것을 다시 받는 짓이다.
        need = scg_research_windows(cached, warm_start, BACKTEST_END)
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT and need:
            for w0, w1 in need:
                LOG.info(f"리포트 수집 구간 {w0} ~ {w1} (캐시에 없는 구간만)")
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(hankyung_collect(w0, w1))
                if "naver" in RESEARCH_SOURCES:
                    frames.append(naver_enrich_detail(naver_collect(w0, w1)))
        elif RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            LOG.ok("리포트 원장이 요청 구간을 이미 전부 덮고 있습니다 — 신규 크롤 0회.")
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                     f"— 이전 전략이 모아둔 것을 그대로 씁니다")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep):
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        VAULT.flush("shared")
        ctx.update(reports=rep, analysts=A, links=L)

    with PIPE.stage("L1.DART", "DART 실적 실측치 · 주식총수 · 접수일", "L1",
                    budget_s=7200, critical=False):
        covered = (sorted(set(ctx["links"]["stock_code"].dropna().astype(str)))
                   if len(ctx.get("links", [])) else [])
        years = list(range(as_ts(warm_start).year - 1, as_ts(BACKTEST_END).year + 1))
        scg_report_dart_plan(len(ctx["sec"]), len(years), max(len(covered), 1),
                             have_spine=bool(len(ctx.get("spine", []))))
        dis = scg_fetch_periodic_disclosures(warm_start, BACKTEST_END)
        ctx["annual_rcept"] = scg_annual_report_dates(dis)
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        multi = scg_fetch_multi_accounts(corps, years)
        tidy = scg_tidy_multi(multi)
        M = ctx.get("spine")
        if M is not None and len(M):
            #  ★ 스파인이 그날의 상장주식수를 이미 준다 → stockTotqySttus 회사×연도 호출
            #    (약 12,000회 = 하루치 예산의 절반)이 통째로 불필요해진다.
            #    회계연도말 기준 주식수를 그 연도의 EPS 분모로 쓴다.
            m = M[["code", "date", "shares"]].dropna().copy()
            m["code"] = m["code"].astype(str)
            m["bsns_year"] = m["date"].dt.year
            shares = (m.sort_values("date").groupby(["code", "bsns_year"], observed=True)
                       .agg(shares=("shares", "last"), _d=("date", "last")).reset_index())
            #  실적 발표 전에는 알 수 없으므로 knowledge_date 는 사업보고서 접수일로 둔다
            shares["knowledge_date"] = pd.to_datetime(
                shares["bsns_year"].astype(int).astype(str) + "-12-31") + pd.Timedelta(days=90)
            shares["src"] = "marcap"
            shares = shares[["code", "bsns_year", "shares", "knowledge_date", "src"]]
            LOG.ok(f"주식총수 {len(shares):,}행 (marcap 관측) — DART stockTotqySttus 호출 "
                   f"약 {len(corps)*len(years):,}회를 절약했습니다")
        else:
            shares_raw = scg_fetch_shares(ctx["sec"][["corp_code", "code"]], years,
                                          priority_codes=covered)
            shares = scg_shares_panel(shares_raw, tidy, ctx["sec"][["corp_code", "code"]])
        ctx.update(tidy_multi=tidy, shares=shares, disclosures=dis)
        if SCG_QUOTA is not None:
            SCG_QUOTA.report()

    return ctx


def scg_build_tracks(ctx: Dict[str, Any]) -> Dict[str, Dict[str, pd.DataFrame]]:
    """메트릭 트랙별 analyst_forecasts + actuals 를 만든다 (§2.1, §3)."""
    tracks: Dict[str, Dict[str, pd.DataFrame]] = {}
    if "EPS" in FORECAST_METRICS:
        with PIPE.stage("L1.EPS", "EPS 추정치 추출 (PDF → 공용 인덱스)", "L1",
                        budget_s=7200, critical=False):
            fe = build_eps_forecasts(ctx.get("reports", pd.DataFrame()),
                                     ctx.get("links", pd.DataFrame()),
                                     ctx.get("annual_rcept"))
            ae_actuals = scg_build_eps_actuals(ctx.get("tidy_multi", pd.DataFrame()),
                                               ctx.get("shares", pd.DataFrame()),
                                               ctx["sec"][["corp_code", "code"]],
                                               ctx.get("annual_rcept") or {})
            tracks["EPS"] = {"forecasts": fe, "actuals": ae_actuals}
    if "TP" in FORECAST_METRICS:
        with PIPE.stage("L1.TP", "목표주가 트랙", "L1", budget_s=600, critical=False):
            af = None
            if len(ctx.get("px_unadj", [])):
                af = ctx["px_unadj"][["code", "date", "adj_factor"]]
            ft = build_tp_forecasts(ctx.get("links", pd.DataFrame()), af)
            tracks["TP"] = {"forecasts": ft, "actuals": None}
    return tracks


def scg_run_track(ctx: Dict[str, Any], metric: str, fc: pd.DataFrame,
                  actuals: Optional[pd.DataFrame], universe: Optional[pd.DataFrame],
                  uname: str, cfg: SCGConfig = SCG, quiet: bool = False) -> Dict[str, Any]:
    """한 (메트릭 × 유니버스) 조합의 전 과정. §44 의 인터페이스를 그대로 호출한다."""
    cal = ctx["calendar"]
    sd = ctx["signal_dates"]
    out: Dict[str, Any] = {"metric": metric, "universe": uname}
    if fc is None or fc.empty:
        return out

    #  §7~§8 Accuracy · §11~§16 Leadership — 둘 다 PIT 사건만 만든다
    if metric == "TP":
        ae = build_tp_accuracy_events(fc, ctx.get("px", pd.DataFrame()), cal, cfg)
    else:
        ae = build_accuracy_events(fc, actuals, cal, cfg)
    le = build_leadership_events(fc, cal, cfg)
    #  §9~§18 — signal date 마다 PIT 롤링 (전체기간 점수 금지)
    S = build_analyst_scores(sd, ae, le, cfg)
    #  §6, §19~§23
    act = build_active_forecasts(fc, sd, cfg)
    if universe is not None and len(universe):
        n0 = act["stock_id"].nunique()
        act = act.merge(universe.drop_duplicates(), on=["signal_date", "stock_id"], how="inner")
        if not quiet:
            LOG.info(f"[{uname}] 유니버스 적용: {n0:,} → {act['stock_id'].nunique():,}종목")
    sc, W = compute_smart_consensus(act, S, cfg)
    #  §24~§29
    sig = build_scg_signals(sc, cal, cfg)
    #  §5 — FY1(가장 가까운 미발표 회계기간)만 신호로 쓴다. FY2 는 별도 행으로 남는다.
    sig = scg_pick_primary_period(sig, metric)
    sig = scg_forward_returns(sig, ctx.get("px", pd.DataFrame()), cal, IC_HORIZONS_TD,
                              ctx.get("sec"))
    out.update(accuracy_events=ae, leadership_events=le, scores=S,
               active=act, consensus=sc, weights=W, signals=sig)
    return out


def scg_pick_primary_period(sig: pd.DataFrame, metric: str) -> pd.DataFrame:
    """§5 — 종목당 신호 1개가 되도록 '가장 가까운 미도래 회계기간'만 남긴다.

    ★ 회계기간을 섞지 않는다(§45.2). 섞는 대신 **고른다**.
      2026-03 시점에 2026-12 와 2027-12 전망이 둘 다 있으면 2026-12(FY1)를 쓴다.
      FY2 행을 지우지는 않고 primary 플래그만 세운다 — 진단에서 대조하기 위해서다.
    """
    if sig is None or sig.empty:
        return sig
    d = sig.copy()
    if metric == "TP":
        d["is_primary"] = True
        return d
    fpe = pd.to_datetime(d["fiscal_period"].astype(str) + "-01", errors="coerce") \
        + pd.offsets.MonthEnd(0)
    d["_fpe"] = fpe
    #  ★ 아직 도래하지 않은 회계기간이 하나도 없으면 primary 를 두지 않는다.
    #    센티넬(10**9)로 채워두고 idxmin 을 돌리면 '이미 끝난 회계기간'이 뽑히는데,
    #    그 실적은 이미 공표된 뒤라 '전망' 이 아니다 — 신호가 아니라 뒷북이 된다.
    fut = d["_fpe"] >= d["signal_date"]
    d["_rank"] = np.where(fut, (d["_fpe"] - d["signal_date"]).dt.days, np.nan)
    cand = d[d["status"].eq(STATUS_OK) & d["_rank"].notna()]
    d["is_primary"] = False
    if len(cand):
        idx = cand.groupby(["signal_date", "stock_id"], observed=True)["_rank"].idxmin()
        d.loc[idx.dropna().to_numpy(), "is_primary"] = True
    n_drop = int((d["status"].eq(STATUS_OK)).sum() - len(cand))
    if n_drop > 0:
        LOG.debug(f"FY1 후보 없음(이미 종료된 회계기간뿐)으로 {n_drop:,}행을 신호에서 제외")
    n = int(d["is_primary"].sum())
    LOG.debug(f"FY1 선택: {len(d):,}행 중 {n:,}행을 신호로 사용 (나머지는 FY2+ 로 진단에만 사용)")
    return d.drop(columns=["_fpe", "_rank"])


def scg_persist(track: Dict[str, Any], outdir: str, tag: str) -> List[str]:
    """§33 필수 중간 출력 + §34 진단 파일. 전용 인덱스와 로컬 파일 양쪽에 남긴다."""
    outs: List[str] = []
    os.makedirs(outdir, exist_ok=True)

    def _w(df: Optional[pd.DataFrame], name: str, as_csv: bool = False):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{tag}.{'csv' if as_csv else 'parquet'}")
        try:
            if as_csv:
                df.to_csv(p, index=False, encoding="utf-8-sig")
            else:
                atomic_write_parquet(df, p)
            outs.append(p)
        except Exception as e:
            LOG.debug(f"{name} 저장 실패: {type(e).__name__}")
        VAULT.put_table(f"{name}_{tag}", df, scope="private", domain="scg", source=STRATEGY_ID)

    sig = track.get("signals")
    _w(track.get("scores"), "analyst_score_history")
    _w(track.get("weights"), "analyst_forecast_weights")
    _w(sig, "smart_consensus_daily")
    _w(scg_analyst_count_distribution(sig), "analyst_count_distribution", as_csv=True)
    _w(scg_shrinkage_diagnostics(track.get("scores")), "shrinkage_diagnostics", as_csv=True)
    _w(scg_weight_concentration(track.get("weights")), "weight_concentration", as_csv=True)
    res = track.get("res") or {}
    _w(res.get("performance"), "performance_summary", as_csv=True)
    _w(res.get("ic"), "ic_summary", as_csv=True)
    _w(res.get("monotonicity"), "monotonicity", as_csv=True)
    VAULT.flush("private")
    return outs


def main() -> dict:
    t_all = time.time()
    global VAULT, SCG_QUOTA
    LOG.banner(f"SCG-LS / SCG-LSA — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"Smart Consensus Gap + Analyst Leadership/Skill · "
               f"백테스트 {BACKTEST_START}~{BACKTEST_END} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["신호 그리드", SIGNAL_FREQ], ["메트릭 트랙", ", ".join(FORECAST_METRICS)],
               ["유니버스", ", ".join(UNIVERSE_VARIANTS)],
               ["KRX 사용", "아니오 — 호출 코드 경로 자체가 없습니다"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유")
        LOG.info(f"전용 인덱스: {VAULT.ns['private']}   ← 이 전략 고유")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간 2GB 미만 — RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        SCG_QUOTA = ScgDartQuota()
        globals()["SCG_QUOTA"] = SCG_QUOTA
        VAULT.report()

    with PIPE.stage("L0.TESTS", "자체검증 §35 TEST 1~9", "L0", budget_s=300):
        scg_run_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        sm = scg_smoke()
        scg_report_performance(sm["res"], label="SMOKE")
        scg_report_buckets(sm["res"])
        scg_report_ic(sm["res"])
        if sm["signals"].empty:
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")
        LOG.ok("스모크 통과 — 계산경로(피처→점수→백테스트→성과표)가 전부 동작합니다.")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
        return {"mode": "SMOKE", "smoke": sm}

    ctx: Dict[str, Any] = {}
    ctx = scg_collect(ctx)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=300, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    tracks = scg_build_tracks(ctx)

    with PIPE.stage("L1.LEDGER", "원장 4단 사슬 감사 (리포트→애널→종목→추정치)", "L1",
                    budget_s=300, critical=False):
        #  ★ `if tracks` 는 dict 가 비었는지만 본다. TP 트랙은 actuals=None 이고
        #    EPS 실측치는 DART 키가 없으면 빈 프레임이라, 기본 설정에서 리스트가 비고
        #    pd.concat([]) 가 ValueError 로 터진다 — 그러면 이 감사표 자체가 안 나온다.
        _ff = [t["forecasts"] for t in tracks.values()
               if t.get("forecasts") is not None and len(t["forecasts"])]
        _aa = [t["actuals"] for t in tracks.values()
               if t.get("actuals") is not None and len(t["actuals"])]
        allf = pd.concat(_ff, ignore_index=True) if _ff else pd.DataFrame()
        alla = pd.concat(_aa, ignore_index=True) if _aa else pd.DataFrame()
        scg_audit_forecast_ledger(ctx.get("reports", pd.DataFrame()),
                                  ctx.get("links", pd.DataFrame()), allf, alla)

    # ── 유니버스 변형 준비 ────────────────────────────────────────────────────────────
    with PIPE.stage("L2.UNIV", "유니버스 변형 (ALL / 시총 하위1000)", "L2", budget_s=900):
        sd = ctx["signal_dates"]
        calv = ctx["calendar"].values.astype("datetime64[ns]")
        S = ctx.get("spine")
        if S is not None and len(S):
            base_u = scg_spine_universe(S, sd, ctx["sec"])
            keep = set(ctx["sec"]["code"].astype(str))
            mcap = scg_spine_marketcap(S, sd)
            mcap = mcap[mcap["stock_id"].isin(keep)]
            adv = scg_spine_adv(S, sd)
            adv = adv[adv["stock_id"].isin(keep)]
        else:
            base_u = scg_universe_at(ctx["sec"], sd)
            mcap = scg_build_marketcap(ctx.get("px_unadj", pd.DataFrame()),
                                       ctx.get("shares", pd.DataFrame()), sd, calv)
            adv = scg_adv_panel(ctx.get("px", pd.DataFrame()), sd)
        small = scg_small_universe(mcap, SMALL_UNIVERSE_N, adv)
        #  하위1000 은 항상 ALL 의 부분집합이어야 한다(다른 종목이 끼면 비교가 성립하지 않음)
        if len(small) and len(base_u):
            small = small.merge(base_u.drop_duplicates(), on=["signal_date", "stock_id"],
                                how="inner")
        universes = {"ALL": base_u, "SMALL1000": small}
        scg_report_universe_attrition([
            ("종목 마스터", int(ctx["sec"]["code"].nunique()), "상장+폐지 합집합"),
            ("PIT 유니버스(ALL)", int(base_u["stock_id"].nunique()) if len(base_u) else 0,
             "listing<=t<delisting"),
            ("시가총액 산출 가능", int(mcap["stock_id"].nunique()) if len(mcap) else 0,
             "무수정주가 × PIT 주식총수"),
            ("하위1000", int(small["stock_id"].nunique()) if len(small) else 0,
             f"시점별 시총 하위 {SMALL_UNIVERSE_N:,}"),
        ])
        ctx["universes"] = universes
        ctx["mcap"] = mcap

    # ── 메트릭 트랙 × 유니버스 실행 ──────────────────────────────────────────────────
    primary = PRIMARY_METRIC
    cov = {}
    results: Dict[str, Dict[str, Any]] = {}
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []
    bench_r = scg_benchmark_returns(ctx.get("bench", pd.DataFrame()), ctx["signal_dates"])
    ppy = 12.0 if SIGNAL_FREQ.upper().startswith("M") else 52.0

    for metric, t in tracks.items():
        fc = t.get("forecasts")
        if fc is None or fc.empty:
            LOG.warn(f"[{metric}] 전망 데이터가 없어 건너뜁니다.")
            continue
        for uname in UNIVERSE_VARIANTS:
            uni = ctx["universes"].get(uname)
            if uname != "ALL" and (uni is None or not len(uni)):
                LOG.warn(f"[{metric}/{uname}] 유니버스가 비어 건너뜁니다.")
                continue
            key = f"{metric}/{uname}"
            with PIPE.stage(f"L2.{metric}.{uname}", f"SCG 산출 {key}", "L2", budget_s=3600,
                            critical=False):
                tr = scg_run_track(ctx, metric, fc, t.get("actuals"), uni, uname)
                sig = tr.get("signals")
                if sig is None or sig.empty:
                    LOG.warn(f"[{key}] 신호가 비었습니다.")
                    continue
                use = sig[sig.get("is_primary", True) & sig["status"].eq(STATUS_OK)]
                tr["signals_primary"] = use
                cov[key] = int(len(use))
                tr["res"] = scg_run_all_strategies(use, SCG, bench_r, label=key)
                results[key] = tr

    if not results:
        raise RuntimeError(
            "어느 트랙에서도 신호를 만들지 못했습니다. 위의 [원장 4단 사슬 감사] 표에서 "
            "어느 고리가 끊겼는지 확인하세요 (리포트 → 애널리스트 → 종목코드 → 추정치).")

    #  ★ EPS 커버리지가 무너졌으면 공식 트랙을 TP 로 승격한다 — 단, 조용히 하지 않는다.
    #  ★ 두 트랙의 '같은 유니버스에서의' 신호 수를 직접 비교한다. 전체 합계로 나누면
    #    SMALL1000 행까지 분모에 들어가 비율이 흐려진다.
    n_eps, n_tp = cov.get("EPS/ALL", 0), cov.get("TP/ALL", 0)
    eps_share = n_eps / max(n_tp, 1) if n_tp else (1.0 if n_eps else 0.0)
    if primary == "EPS" and "TP/ALL" in results and eps_share < PRIMARY_METRIC_MIN_COVERAGE:
        LOG.warn(f"EPS 트랙의 유효 신호가 {n_eps:,}건으로 TP 트랙({n_tp:,}건) 대비 "
                 f"{100*eps_share:.1f}% 에 불과합니다 (임계 {100*PRIMARY_METRIC_MIN_COVERAGE:.0f}%). "
                 f"공식 트랙을 TP 로 승격합니다. EPS 결과도 아래에 그대로 출력하니 "
                 f"반드시 함께 읽으세요 — 조용히 바꾸지 않습니다.")
        primary = "TP"
    if f"{primary}/ALL" not in results:
        primary = list(results)[0].split("/")[0]

    # ── 보고 ─────────────────────────────────────────────────────────────────────────
    for key, tr in results.items():
        metric, uname = key.split("/")
        is_primary = (key == f"{primary}/ALL")
        with PIPE.stage(f"L6.REPORT.{metric}.{uname}", f"성과·해석 {key}", "L6",
                        budget_s=600, critical=False):
            LOG.banner(f"[{key}] {'★ 공식 트랙' if is_primary else '대조 트랙'}",
                       f"메트릭 {metric} · 유니버스 {uname}")
            scg_report_performance(tr["res"], label=key)
            scg_report_buckets(tr["res"])
            scg_report_ic(tr["res"])
            scg_report_shrinkage(tr.get("scores"))
            scg_report_weight_concentration(scg_weight_concentration(tr.get("weights")))
            scg_report_interpretation(tr["signals_primary"], tr["res"])
            scg_diagnostic_card(tr["signals_primary"], tr["res"], tr.get("scores"),
                                metric, uname)
            outs += scg_persist(tr, outdir, f"{metric}_{uname}_{stamp}")

    # ── 강건성 (공식 트랙 + 하위1000 대조) ────────────────────────────────────────────
    for key in [f"{primary}/ALL", f"{primary}/SMALL1000"]:
        if key not in results:
            continue
        tr = results[key]
        with PIPE.stage(f"L5.ROBUST.{key.replace('/', '.')}", f"강건성 {key}", "L5",
                        budget_s=4 * 3600, critical=False):
            LOG.banner(f"강건성 검사 — [{key}]", "§41 민감도는 '확인' 이지 '최적화' 가 아닙니다")
            metric, uname = key.split("/")
            t = tracks[metric]

            def _rebuild(cfg: SCGConfig, _m=metric, _t=t, _u=uname):
                rr = scg_run_track(ctx, _m, _t["forecasts"], _t.get("actuals"),
                                   ctx["universes"].get(_u), _u, cfg, quiet=True)
                s = rr.get("signals")
                if s is None or s.empty:
                    return None
                return s[s.get("is_primary", True) & s["status"].eq(STATUS_OK)]

            scg_run_robustness(tr["signals_primary"], bench_r, _rebuild, ppy,
                               do_sensitivity=(key == f"{primary}/ALL"))

    # ── 유니버스 대조표 ──────────────────────────────────────────────────────────────
    with PIPE.stage("L6.COMPARE", "유니버스·트랙 대조표", "L6", budget_s=300, critical=False):
        rows = []
        for key, tr in results.items():
            P = tr["res"].get("performance")
            if P is None or P.empty:
                continue
            for _, r in P.iterrows():
                rows.append([key, r["strategy"], f"{int(r['n_signals']):,}",
                             _p(r["annualized_return"], 1, True), _p(r["Sharpe"]),
                             _p(r["MDD"], 1, True), _p(r["hit_rate"], 1, True)])
        LOG.table(rows, ["트랙/유니버스", "전략", "신호수", "연율", "Sharpe", "MDD", "적중률"],
                  ["l", "l", "r", "r", "r", "r", "r"],
                  title="★ 전체 대조표 — 메트릭 트랙 × 유니버스 × 전략. "
                        "시총 하위1000 이 전체와 다른 답을 내면 소형주 효과가 섞인 것입니다")

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        try:
            atomic_write_text(lp, "\n".join(LOG.buffer))
            outs.append(lp)
        except Exception:
            pass
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if SCG_QUOTA:
            SCG_QUOTA.close()
            SCG_QUOTA.report()
        VAULT.report()

    scg_report_cache_ledger()
    PIPE.report_stages(); PIPE.report_flow(); PIT.report(); report_http(); PIPE.report_runtime()
    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시: ① EPS 추정치는 PDF 파싱에 의존하며 추출 실패가 증권사 템플릿별로 "
             "발생합니다(위의 증권사×연도 추출률 표 참조) — 그래서 TP 트랙을 함께 냅니다. "
             "② 시가총액은 무수정주가 × DART 주식총수이며, 주식총수를 못 구한 종목은 "
             "하위1000 선정에서만 빠집니다. ③ 상장폐지 종목은 포함되나 폐지 목록 자체가 "
             "불완전할 수 있어 관측기반 추정으로 보완했습니다.")
    scg_offer_download(outs)
    return {"results": results, "ctx": ctx, "primary": primary, "outputs": outs}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
            if SCG_QUOTA:
                SCG_QUOTA.close()
        except Exception:
            pass
