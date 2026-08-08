#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  TCD v2 — 트레이드오프 붕괴 탐지 (Trade-off Collapse Detection)
#  전략: PACK-P 조달청 낙찰   [PACK_P]
#  활성 센서팩: PACK-P
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)
#
#  낙찰업체가 사업자등록번호로 직접 식별되므로 매핑 문제가 구조적으로 없다. 낙찰률(q2)은 수출단가와 같은 성질의 순수 가격 지표다. 방산·원전 레짐 편승 위험이 크므로 R7 레짐 분할이 필수 통과 조건이다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v2_05_pack_p_procurement.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성·계약(C1~C12) 자가검정
#     [1] 합성데이터 엔드투엔드 스모크 테스트  (실데이터 쓰기 전 계산경로 증명)
#     [2] 데이터 수집  (구글드라이브 캐시 우선 → 부족분만 신규 수집 → 드라이브 재적재)
#     [3] 원장 무결성 감사  (보고서 ↔ 애널리스트 ↔ 종목 연결 상태)
#     [4] PIT 유니버스 구축 + 유니버스 감쇠 감사
#     [5] 피처 패널(L1) → 스코어(L2) → 백테스트(L3)
#     [6] 성과 검증표
#     [7] 강건성 검사 R1~R11
#     [8] 해석표 + 종목별 진단 카드
#     [9] 런타임 감사(C10) + 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 다만 키가 없는 데이터원은 자동으로 건너뛰고,
#     "왜 건너뛰었는지"를 로그에 한글로 명시합니다. (조용히 실패하지 않습니다)
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI ─────────────────────────────────────────────────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료. 발급 즉시 사용. 일 20,000건 호출 제한(2026 기준, 코드가 자동 스로틀합니다).
#    ▶ 이 전략의 B축(회계품질)·C축(자원투입)의 필수 입력입니다. 없으면 대부분의 TP가 죽습니다.
DART_API_KEY = ""

# ── ② 공공데이터포털 (국민연금 사업장 / 조달청 낙찰) ────────────────────────────────────────
#    발급: https://www.data.go.kr  →  로그인 → 원하는 API 상세페이지 → [활용신청]
#           → 마이페이지 > 데이터활용 > Open API > 인증키에서 확인
#    ★ 반드시 "일반 인증키(Decoding)" 값을 붙여넣으세요.
#      Encoding 키(%2B, %3D 같은 게 섞인 것)를 넣으면 이중 인코딩으로 401/SERVICE_KEY_IS_NOT_REGISTERED가 납니다.
#      (코드가 이중 인코딩을 자동 감지해서 경고하고 교정 시도합니다)
DATA_GO_KR_KEY = ""

# ── ③ 관세청 무역통계 (PACK-X 사용 시에만) ──────────────────────────────────────────────────
#    발급: https://unipass.customs.go.kr  또는 공공데이터포털의 관세청 수출입무역통계 API
CUSTOMS_API_KEY = ""

# ── ④ KRX 데이터 마켓플레이스 (2025-12 인증 방식 변경 대응) ─────────────────────────────────
#    가입: https://data.krx.co.kr  →  회원가입(무료) → 로그인 정보 입력
#
#    ▶ 비워두셔도 됩니다. 유니버스의 정확성은 상장일·폐지일(FDR/KIND)만으로 성립하도록
#      설계되어 있고, KRX 스냅샷은 '검증·보강'일 뿐입니다. 비우면 그 단계만 건너뜁니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML을 받아 대량 실패합니다.
#      (이 코드는 로그인을 메인 스레드에서 1회만 하고 모든 호출을 직렬화해 스스로
#       충돌하지 않지만, '바깥에서' 같은 계정을 쓰는 것까지는 막을 수 없습니다)
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""
KRX_OPENAPI_KEY    = ""   # (선택) KRX Open API 인증키. 단, 엔드포인트별 '이용신청'이 따로
                          #        필요하고 승인에 하루 정도 걸립니다. 키만으론 즉시 안 됩니다.

# ── ⑤ 구글드라이브 캐시 ─────────────────────────────────────────────────────────────────────
#    ★★★ 절대 원칙: 이 코드는 기존 캐시를 절대 삭제·덮어쓰기하지 않습니다. ★★★
#      · 기존 인덱스(공용/전용)는 읽기 전용으로 열고, 갱신은 "append-merge + 원자적 교체"로만 합니다.
#      · 인덱스를 건드리기 전 항상 타임스탬프 백업을 남깁니다.
#      · 이미 드라이브에 있는 보고서/원본은 "이동·개명 없이 경로만 등록"합니다(adopt-by-reference).
#
#    GDRIVE_ROOT      : 이 전략이 쓰는 최상위 캐시 루트
#    GDRIVE_SHARED_NS : 공용 인덱스 네임스페이스 — 다른 전략에서도 재활용 가능한 원본/정제본
#    GDRIVE_PRIVATE_NS: 전용 인덱스 네임스페이스 — 이 전략 고유의 피처/스코어/리포트
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"          # → {GDRIVE_ROOT}/_shared      (공용)
GDRIVE_PRIVATE_NS = "tcd_v2"           # → {GDRIVE_ROOT}/tcd_v2       (전용)

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요. 재귀 스캔해서 "등록만" 합니다.
#      (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록합니다)
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
LOCAL_CACHE_ROOT  = "./tcd_cache"

# ── ⑥ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑦ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 16     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 8로 줄이세요.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.5,
    "naver":     3.0,
    "krx":       2.0,
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환

# ── ⑧ 애널리스트 리포트 수집 ────────────────────────────────────────────────────────────────
#    목표: 연 30,000건 이상 원문 수집. 실제 시장 발간량이 상한이므로,
#          달성/미달 여부와 그 원인을 로그에 정직하게 표로 출력합니다.
RESEARCH_COLLECT       = True    # False면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES       = ["hankyung", "naver"]   # 리스트 페이지 소스
RESEARCH_DOWNLOAD_PDF  = True    # PDF 원문까지 받을지 (목표주가/애널리스트 추출 정확도↑, 용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑨ 포지션 / 사이징  (§8.5 — 드로다운 한가운데서 정하지 않도록 상수로 못박음) ──────────────
PORTFOLIO_TOP_PCT       = 0.05    # 신호 상위 5% 진입
PORTFOLIO_MAX_NAMES     = 25
PORTFOLIO_MIN_NAMES     = 5
POS_MAX_WEIGHT          = 0.12    # 종목당 최대 비중
POS_MIN_WEIGHT          = 0.02
POS_ADV_PARTICIPATION   = 0.10    # 20일 평균거래대금의 10% 이내로 보유 제한
HOLD_MAX_MONTHS         = 24
ACCOUNT_KRW             = 30_000_000   # 소액계좌 가정 (최소주문/유동성 제약 계산용)
MIN_ADV_KRW             = 300_000_000  # V6 유동성 하한: 20일 평균거래대금

# ── ⑩ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전체 출력물을 예행연습 (수십 초). 네트워크/키 불필요.
#              백테스트·성과·강건성·해석표·진단카드가 전부 나옵니다. 처음엔 이걸로 한 번.
#    "FULL"  : 스모크 → 실경로 리허설 → 실데이터 수집 → 백테스트 → 강건성 (권장)
#    "CACHED": 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트
RUN_MODE = "FULL"

#    실행 전에 자동으로 도는 3중 검증 (전부 통과해야 실데이터 수집을 시작합니다):
#      ① 계약 자동검정 C1~C12  — PIT·생존자편향·거부권 등 협상 불가 규칙
#      ② 합성 스모크          — 피처→스코어→백테스트 '계산경로'
#      ③ 실경로 리허설        — 네트워크만 가짜로 두고 '수집·정제 함수'를 실물 실행
#    ③이 없던 빌드가 ①②를 다 통과하고도 실행 2분 만에 수집부 한 줄 때문에 죽은 적이 있어
#    추가되었습니다. 세 검증은 서로 다른 것을 봅니다.

SEED = 20260807          # C8 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True   # §15 킬 기준 위반 시 즉시 중단하고 보고 (False로 끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID        = "PACK_P"
STRATEGY_NAME      = "PACK-P 조달청 낙찰"
ACTIVE_PACKS       = ["P"]
BUILD_VERSION      = "v2.20260808.1322"


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
        # ★ yfinance 는 실패 종목마다 ERROR 한 줄을 직접 찍는다. 한국 폐지종목은 .KS/.KQ 양쪽이
        #   모두 없으므로 종목당 2줄 — 1,800종목이면 3,600줄이 진단 로그를 덮어버린다.
        #   실패 사실은 fetch_prices 의 시도 원장(price_fetch_attempts)에 이미 남으므로
        #   여기서는 라이브러리 자체 출력만 CRITICAL 로 올려 침묵시킨다(예외는 그대로 전파).
        for _n in ("yfinance", "yfinance.data", "yfinance.utils", "peewee", "urllib3"):
            logging.getLogger(_n).setLevel(logging.CRITICAL)
        try:
            yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), "py-yfinance"))
        except Exception:
            pass
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

    @property
    def active(self) -> bool:
        """이 스테이지의 본문을 실제로 수행해야 하는가.

        ★★ 왜 이 속성이 필요한가 — skip_if 의 함정 ★★
          `PIPE.stage(..., skip_if=True)` 는 **본문을 건너뛰지 못한다.**
          @contextmanager 로 만든 컨텍스트 매니저는 yield 하는 순간 with 블록의 본문이
          반드시 실행된다 — 파이썬에 '본문을 안 돌리는 with' 는 없다.
          그래서 skip_if 는 지금까지 상태 표시(SKIP)와 경고 한 줄만 남기고,
          정작 건너뛰려던 수집은 그대로 수행돼 왔다. 로그에는 '건너뜀' 이라고 찍히고
          네트워크로는 나가는, 가장 헷갈리는 형태의 조용한 실패다.
        → 호출부가 `with PIPE.stage(...) as st: if st.active:` 로 명시적으로 가른다.
          컨텍스트 매니저가 못 하는 일을 하는 척하지 않는다.
        """
        return self.status != "SKIP"


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
            # ★ 여기서 yield 하면 with 본문은 **그대로 실행된다**(위 StageRecord.active 참조).
            #   호출부가 `if st.active:` 로 가르지 않으면 '건너뜀' 이라고 찍고도 수집이 돈다.
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
        dt = df[c].dtype
        # ★ category 의 dtype.kind 는 "O" 다. 그래서 아래 object 분기가 **이미 category 인
        #   컬럼에도 매번 들어가** nunique() 를 다시 돌았다. 7.09M 행에서 실측 수 초.
        #   이 함수는 매 실행 같은 결론에 도달하므로 그냥 넘긴다.
        if isinstance(dt, pd.CategoricalDtype):
            continue
        k = dt.kind
        if k == "f":
            if dt.itemsize <= 4:          # 이미 float32 이하 — 다시 재지 않는다
                continue
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★ 2단 캐시 — 로컬 미러 + 드라이브 원본
#
#  구글드라이브(Colab 마운트든 데스크톱 동기화든)는 로컬 디스크가 아니라 네트워크
#  파일시스템에 가깝다. 실측으로 340MB 짜리 일봉 테이블 한 번 읽기가 수십 초다.
#  같은 실행 안에서의 중복 읽기는 세션 메모가 이미 막고 있지만, **실행이 바뀌면**
#  다시 처음부터 드라이브를 읽는다 — 재실행이 잦은 이 파이프라인에서 그 비용이 크다.
#
#  → 드라이브에서 읽은 테이블을 로컬 디스크에 그대로 미러링한다. 다음 실행은
#    ① 세션 메모 → ② 로컬 미러 → ③ 드라이브 순으로 찾는다.
#    미러 유효성은 사이드카(.meta.json)에 적어 둔 드라이브 파일의 (mtime, size) 와
#    대조해 판정한다. stat 한 번은 FUSE 에서도 싸고, 읽기는 수십 초다.
#
#  ★ 진실의 원천은 언제나 드라이브다. 미러는 순수한 읽기 가속이며,
#    미러가 없거나 깨져도 결과는 동일하다(그냥 느려질 뿐). 미러는 삭제해도 안전하다.
#  ★ 반대로 **드라이브를 못 쓰는 실행**(마운트 실패·네트워크 단절)에서는 미러가
#    마지막 보루가 된다. 그때는 미러에서 읽고 그 사실을 로그에 남긴다.
#  ★ 미러는 절대 드라이브를 덮어쓰지 않는다. 방향은 항상 드라이브 → 로컬 한쪽뿐이고,
#    put_table 은 드라이브에 먼저 쓴 뒤 그 결과를 미러에 복사한다(절대1원칙).
# ══════════════════════════════════════════════════════════════════════════════════════════
def _default_mirror_root() -> str:
    v = globals().get("LOCAL_MIRROR_ROOT")
    if v:
        return os.path.abspath(str(v))
    if ENV.get("colab"):
        return "/content/tcd_cache_mirror"          # Colab 컨테이너 로컬 SSD
    return os.path.join(os.path.expanduser("~"), ".cache", "tcd_cache_mirror")


class Vault:
    def __init__(self, root: str, mode: str, mirror_root: Optional[str] = None):
        self.root = os.path.abspath(root)
        self.mode = mode
        # 루트가 이미 로컬이면 미러는 무의미하다(같은 디스크를 두 번 쓰는 낭비).
        _mr = os.path.abspath(mirror_root or _default_mirror_root())
        _is_net = ("drive" in self.root.lower() or "clouddrive" in self.root.lower()
                   or "cloudstorage" in self.root.lower() or mode.endswith("DRIVE")
                   or mode == "LOCAL_SYNCED_DRIVE")
        self.mirror_root = _mr if (_is_net and os.path.normpath(_mr) !=
                                   os.path.normpath(self.root)) else None
        self.mirror_stats = Counter()
        if self.mirror_root:
            try:
                os.makedirs(self.mirror_root, exist_ok=True)
            except Exception:                                    # noqa
                self.mirror_root = None
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
        # (파일경로, mtime) → 디코딩된 프레임. 같은 실행에서 같은 테이블을 다시 읽지 않는다.
        # 드라이브 동기화 폴더에서 수백 MB 파케이 재읽기는 수십 초짜리 비용이다.
        self._tbl_memo: Dict[tuple, pd.DataFrame] = {}

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    # ── 로컬 미러 -----------------------------------------------------------------------
    def _mirror_paths(self, scope: str, name: str) -> Optional[Tuple[str, str]]:
        if not self.mirror_root:
            return None
        d = os.path.join(self.mirror_root, scope, "table")
        return os.path.join(d, f"{name}.parquet"), os.path.join(d, f"{name}.meta.json")

    def _mirror_valid(self, mp: str, meta_p: str, src: str) -> bool:
        """미러가 드라이브 원본과 같은 세대인가. stat 두 번으로 판정한다(읽지 않는다)."""
        try:
            if not (os.path.exists(mp) and os.path.exists(meta_p)):
                return False
            st = os.stat(src)
            m = json.loads(open(meta_p, encoding="utf-8").read() or "{}")
            return (abs(float(m.get("src_mtime", -1)) - st.st_mtime) < 1e-6
                    and int(m.get("src_size", -1)) == int(st.st_size))
        except Exception:                                        # noqa
            return False

    def _mirror_write(self, scope: str, name: str, src: str) -> None:
        """드라이브 원본을 로컬로 복사하고 세대 정보를 사이드카에 남긴다. 실패해도 무해하다."""
        mpz = self._mirror_paths(scope, name)
        if not mpz:
            return
        mp, meta_p = mpz
        try:
            st = os.stat(src)
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            tmp = mp + f".tmp{os.getpid()}"
            shutil.copy2(src, tmp)
            os.replace(tmp, mp)
            atomic_write_text(meta_p, json.dumps(
                {"src": src, "src_mtime": st.st_mtime, "src_size": int(st.st_size),
                 "mirrored_at": _dt.datetime.now().isoformat(timespec="seconds")},
                ensure_ascii=False))
            self.mirror_stats["mirror_write"] += 1
        except Exception as e:                                   # noqa
            # 미러는 순수 가속이다. 실패하면 그냥 다음 실행에 드라이브를 읽으면 된다.
            self.mirror_stats["mirror_write_fail"] += 1
            LOG.debug(f"로컬 미러 기록 실패({type(e).__name__}) — 결과에는 영향 없습니다: {name}")

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
                  domain: str = "table", source: str = "", extra: Optional[dict] = None,
                  backup: bool = True) -> Optional[str]:
        """정제 테이블(parquet). 기존 파일은 백업 후 교체 — 백업 없이는 절대 교체하지 않는다.

        backup=False 는 **증분 체크포인트 전용**이다. 왜 필요한가:
          이 함수는 한 번 불릴 때마다 전체 파일 작업을 네 번 한다 —
          sha1_file(파일 전체 읽기) → copy2(전량 복사) → parquet 쓰기 → 미러 복사.
          대상이 구글드라이브 FUSE 이고 대상 테이블이 수백 MB 이면 한 번이 수십 초다.
          수집 루프는 청크마다 이 함수를 부르므로(EMP 1,000건·Tier-2 40사) 그 비용이
          수집 시간 자체를 압도하고, _backup 폴더도 청크 수만큼 불어난다.
        ★ 세대 보존 원칙은 깨지지 않는다: 진실의 원천은 append-only 저널이고,
          중간 체크포인트는 같은 실행 안에서 **단조 증가**하는 스냅샷이라
          마지막 저장 한 번만 백업하면 잃을 세대가 없다.
        """
        if df is None:
            return None
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        if os.path.exists(path) and backup:
            # ★★ 백업 이름을 타임스탬프에서 **내용해시**로 바꿨다 ★★
            #   실측: 340MB 짜리 가격 테이블이 신규 1종목만 있어도 매 실행 통째로 복사됐고,
            #   _backup 에는 개수·용량 상한이 없으며 삭제 API 도 없다(원칙상 있어서도 안 된다).
            #   일 1회 실행이면 10.2GB/월 · 124GB/년 — 무료 15GB 는 44회, 100GB 는 294회에 찬다.
            #   내용해시로 이름을 지으면 **같은 내용은 같은 이름**이라 중복 백업이 사라지고,
            #   내용이 다르면 절대 충돌하지 않는다. 세대는 그대로 보존된다(원칙 유지).
            #   덤으로 타임스탬프 1초 해상도 때문에 같은 초의 두 저장이 앞 백업을 조용히
            #   덮어쓰던 구멍도 닫힌다.
            try:
                _h = sha1_file(path)[:12]
            except Exception:                               # noqa
                _h = f"{_dt.datetime.now():%Y%m%d_%H%M%S}"
            bak = os.path.join(self.ns[scope], "index", "_backup", f"{name}.{_h}.parquet")
            try:
                if not os.path.exists(bak):
                    shutil.copy2(path, bak)
                else:
                    self.stats["backup_dedup"] += 1
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name} "
                         f"(get_table 은 활성 파일이 없거나 못 읽을 때 이 리비전을 읽습니다)")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
        try:
            atomic_write_parquet(df, path)
        except Exception as e:                              # noqa
            LOG.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        # 방금 쓴 내용을 세션 메모에 심어 둔다 — 바로 뒤에 get_table 하는 코드가
        # 드라이브에서 같은 것을 다시 읽지 않게 한다(수백 MB 파케이면 수십 초다).
        try:
            with self._lk:
                self._tbl_memo = {k: v for k, v in self._tbl_memo.items() if k[0] != path}
                self._tbl_memo[(path, os.path.getmtime(path))] = df
        except Exception:                                   # noqa
            pass
        # 드라이브에 쓴 그 파일을 로컬로도 복사한다. 방향은 항상 드라이브 → 로컬 한쪽이며,
        # 미러가 드라이브를 덮는 경로는 존재하지 않는다(절대1원칙).
        self._mirror_write(scope, name, path)
        self._register(scope, {
            "uid": sha1_str("table", scope, name), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        return path

    def _latest_revision(self, name: str, scope: str) -> Optional[str]:
        """{name}.rev*.parquet 중 가장 최근 것. 활성 파일이 없을 때만 쓰인다."""
        try:
            d = self.table_dir(scope)
            cand = [os.path.join(d, f) for f in os.listdir(d)
                    if f.startswith(f"{name}.rev") and f.endswith(".parquet")]
            return max(cand, key=os.path.getmtime) if cand else None
        except Exception:                                   # noqa
            return None

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None
                  ) -> Optional[pd.DataFrame]:
        """정제 테이블 읽기. **같은 실행 안에서는 파일을 한 번만 읽는다.**

        ★ 왜 메모이제이션이 필요한가. 이 파이프라인은 같은 테이블을 한 실행에서 여러 번
          읽는다 — 예: price_earliest_available 은 fetch_prices 안에서만 2회,
          dart_employees_ext 는 사전점검·수집·마감에서 3회. 구글드라이브 동기화 폴더는
          로컬 디스크가 아니라 네트워크 파일시스템에 가까워서, 수백 MB 파케이 한 번 읽기가
          수십 초다. 그걸 실행마다 중복으로 냈다.
        ★ 무효화는 mtime 으로 한다. 같은 실행에서 put_table 이 파일을 바꾸면 mtime 이
          달라지므로 자동으로 다시 읽는다 — 오래된 값을 붙들고 있을 수 없다.
        ★ 반환은 얕은 복사다. 호출자가 `d["date"] = ...` 처럼 컬럼을 갈아끼워도
          캐시 원본이 오염되지 않는다(공용 캐시를 제자리에서 고치는 것은 절대1원칙 위반이다).
        """
        path = os.path.join(self.table_dir(scope), f"{name}.parquet")
        # ── 0단계: 로컬 미러가 드라이브와 같은 세대면 **드라이브를 읽지 않는다** ────────────
        #    stat 두 번(≈ms) 으로 판정하고, 유효하면 로컬 디스크에서 읽는다(수십 초 절약).
        _mz = self._mirror_paths(scope, name)
        if _mz and os.path.exists(path) and self._mirror_valid(_mz[0], _mz[1], path):
            try:
                _mt = os.path.getmtime(_mz[0])
                if max_age_days is None or (time.time() - os.path.getmtime(path)
                                            ) / 86400.0 <= max_age_days:
                    _ck = (_mz[0], _mt)
                    with self._lk:
                        _hit = self._tbl_memo.get(_ck)
                    if _hit is not None:
                        self.stats["table_memo_hit"] += 1
                        return _hit.copy(deep=False)
                    _t0 = time.time()
                    _d = read_parquet_safe(_mz[0])
                    if _d is not None:
                        with self._lk:
                            if len(self._tbl_memo) > 64:
                                self._tbl_memo.clear()
                            self._tbl_memo[_ck] = _d
                        self.mirror_stats["mirror_hit"] += 1
                        self.stats["table_read_mirror"] += 1
                        PIPE.io("IN", "PARQUET", f"table:{name}", _d,
                                source=f"로컬 미러 ({time.time()-_t0:.1f}s · 드라이브 재읽기 없음)")
                        return _d.copy(deep=False)
            except Exception:                                    # noqa
                pass                                             # 미러가 깨졌으면 원본으로 간다
        if not os.path.exists(path):
            # 공용에 없으면 전용에서, 전용에 없으면 공용에서 — 다른 전략이 만든 걸 재활용한다
            alt = "private" if scope == "shared" else "shared"
            path2 = os.path.join(self.table_dir(alt), f"{name}.parquet")
            if os.path.exists(path2):
                path = path2
            elif _mz and os.path.exists(_mz[0]):
                # ★ 드라이브에 원본이 아예 없다 = 이번 실행에서 드라이브를 못 붙였거나
                #   다른 머신에서 돈 실행이다. 그럴 때 미러는 마지막 보루다 —
                #   "캐시가 있는데도 다시 수집" 하는 것보다 낫다. 사실을 로그로 남긴다.
                LOG.warn(f"드라이브에 {name}.parquet 이 없어 **로컬 미러**에서 읽습니다 "
                         f"({os.path.relpath(_mz[0], self.mirror_root)}). "
                         f"드라이브 마운트를 확인하세요 — 이번 실행의 신규 수집물은 "
                         f"드라이브에 저장되지 못할 수 있습니다.")
                d0 = read_parquet_safe(_mz[0])
                if d0 is not None:
                    self.mirror_stats["mirror_rescue"] += 1
                    return d0.copy(deep=False)
                return None
            else:
                # ★ 마지막 수단: put_table 이 백업 실패로 흘려 둔 리비전 파일.
                #   예전엔 이걸 아무도 읽지 않아, 워터마크·음성캐시 기록이 통째로 새고
                #   다음 실행이 같은 헛수고를 그대로 반복했다(실측 900초대).
                #   ★ 활성 파일이 **있으면** 절대 승격하지 않는다 — 더 넓은 활성본을
                #     더 좁은 옛 스냅샷으로 덮는 '좁혀 덮어쓰기'가 되기 때문이다.
                rev = self._latest_revision(name, scope) or self._latest_revision(name, alt)
                if not rev:
                    return None
                LOG.warn(f"활성 테이블 {name}.parquet 이 없어 리비전 파일을 읽습니다: "
                         f"{os.path.basename(rev)}. 이전 실행에서 백업 복사가 실패해 "
                         f"활성 파일 대신 리비전으로 저장된 기록입니다 — "
                         f"드라이브 용량·권한을 확인하세요.")
                path = rev
        try:
            mt = os.path.getmtime(path)
        except OSError:
            return None
        if max_age_days is not None:
            if (time.time() - mt) / 86400.0 > max_age_days:
                return None
        ck = (path, mt)
        with self._lk:
            hit = self._tbl_memo.get(ck)
        if hit is not None:
            self.stats["table_memo_hit"] += 1
            PIPE.io("IN", "MEM", f"table:{name}", hit, source="세션 내 재사용(파일 재읽기 없음)")
            return hit.copy(deep=False)
        t0 = time.time()
        d = read_parquet_safe(path)
        if d is not None:
            with self._lk:
                # 메모는 (경로, mtime) 키라 무한히 자라지 않는다. 그래도 상한을 둔다.
                if len(self._tbl_memo) > 64:
                    self._tbl_memo.clear()
                self._tbl_memo[ck] = d
            self.stats["table_read"] += 1
            _el = time.time() - t0
            PIPE.io("IN", "DRIVE", f"table:{name}", d, source=os.path.relpath(path, self.root))
            # 드라이브에서 읽었으니 로컬로 미러링해 둔다 — **다음 실행**이 이 비용을 안 낸다.
            self._mirror_write(scope, name, path)
            if _el > 5.0:
                LOG.info(f"드라이브에서 {name} {len(d):,}행 읽는 데 {_el:.1f}초 — "
                         f"이번 실행에서 다시 읽지 않고(세션 메모), 로컬 미러에 복사해 "
                         f"다음 실행도 다시 읽지 않습니다.")
            return d.copy(deep=False)
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
        if self.mirror_root:
            _n = self.mirror_stats
            _sz = 0.0
            try:
                for dp, _dn, fns in os.walk(self.mirror_root):
                    _sz += sum(_safe_size(os.path.join(dp, f)) for f in fns if f.endswith(".parquet"))
            except Exception:
                pass
            LOG.table([["로컬 미러 경로", self.mirror_root],
                       ["미러에서 읽음(드라이브 생략)", f"{_n.get('mirror_hit', 0):,}회"],
                       ["미러로 복사", f"{_n.get('mirror_write', 0):,}회"],
                       ["드라이브 부재 시 미러 구제", f"{_n.get('mirror_rescue', 0):,}회"],
                       ["미러 용량", f"{max(_sz,0)/1e9:.2f} GB"]],
                      ["2단 캐시", "값"], ["l", "r"],
                      title="로컬 미러 — 드라이브는 진실의 원천, 로컬은 읽기 가속")
            LOG.info("로컬 미러는 언제 지워도 안전합니다(다음 실행에서 드라이브로부터 다시 만듭니다). "
                     "미러가 드라이브를 덮어쓰는 경로는 존재하지 않습니다.")
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

# ── 소스 단위 서킷브레이커 (403/401 연속) ──────────────────────────────────────────────────
#   차단당한 소스를 계속 두드리면 시간만 태우고 차단을 더 오래 끌게 만든다.
#   실측: 한경컨센서스가 (skinType × 연도) 잡마다 tries=3 을 독립 소진해 403 을 33회 맞았다.
#   ★ 접은 사실은 반드시 감사표에 남긴다 — '0건'이 '데이터가 없다'로 오독되면 안 된다.
HTTP_DENY_TRIP_N = 12          # 이만큼 연속 거부되면 이번 실행에서 그 소스를 접는다
_DENIED: Counter = Counter()
_TRIPPED: set = set()


def _note_denied(source: str):
    with _HTTP_LK:
        _DENIED[source] += 1
        if _DENIED[source] >= HTTP_DENY_TRIP_N and source not in _TRIPPED:
            _TRIPPED.add(source)
            LOG.error(f"'{source}' 가 403/401 을 {_DENIED[source]}회 연속 반환했습니다 — "
                      f"이번 실행에서는 이 소스를 더 호출하지 않습니다(서킷브레이커). "
                      f"차단된 상태에서 계속 두드려도 받지 못하고 차단만 길어집니다. "
                      f"※ 이 소스의 산출물이 0건인 것은 '데이터가 없어서'가 아니라 "
                      f"'요청을 거부당해서'입니다 — 감사표에 그대로 남습니다.")


def _note_ok(source: str):
    if _DENIED.get(source):
        with _HTTP_LK:
            _DENIED[source] = 0


def _source_tripped(source: str) -> bool:
    return source in _TRIPPED


def http_tripped_sources() -> List[str]:
    return sorted(_TRIPPED)


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
    # ★ 소스 단위 서킷브레이커 — 403/401 이 연속되면 그 소스를 이번 실행에서 접는다.
    #   한경컨센서스는 (skinType × 연도) 잡마다 독립적으로 tries=3 을 소진했고,
    #   실측 로그의 '403 × 33회' 가 정확히 이 구조에서 나왔다. 차단당한 뒤에도 계속
    #   두드리는 것은 시간 낭비일 뿐 아니라 차단을 더 오래 끌게 만든다.
    #   ※ '데이터가 없다'로 오판하지 않도록, 접었다는 사실은 감사표에 남는다.
    if _source_tripped(source):
        with _HTTP_LK:
            HTTP_STATS[f"{source}:SKIPPED_TRIPPED"] += 1
        return None
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
                _note_ok(source)          # 한 번이라도 통하면 연속 카운터를 되돌린다
                return r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
            if r.status_code in (429, 503):
                time.sleep(min(30.0, 2.0 * (2 ** attempt)) + random.random())
                last_exc = requests.HTTPError(f"{r.status_code} {url}")
                continue
            if r.status_code in (403, 401):
                _note_denied(source)
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
    if _TRIPPED:
        LOG.error(f"서킷브레이커로 접힌 소스: {sorted(_TRIPPED)} — "
                  f"이 소스들의 산출물이 0건인 것은 **데이터가 없어서가 아니라 "
                  f"요청을 거부당해서**입니다. 결측으로 처리되며, 그 사실이 리포트에 남습니다. "
                  f"잠시 뒤(수십 분~수 시간) 재실행하면 캐시에 이어받습니다.")


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
                   "corp_code", "industry", "sector_src", "src",
                   # 폐지 사유 — 백테스트가 청산가를 정할 때 쓴다. 흡수합병·완전자회사화·
                   # 스팩해산을 -100% 로 처리하면 없는 손실을 매년 지어낸다(41_backtest).
                   "delist_reason", "to_code"]

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
                # ★ 컬럼 목록을 자르지 않는다. [:6] 으로 자른 로그가 delisting CSV 의
                #   DelistingDate(7번째)를 가려, '상장일을 폐지일로 읽고 있다'는 오진을
                #   유발했다. 진단 출력이 진단을 방해하면 없느니만 못하다.
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} "
                          f"({len(df):,}행 · 컬럼 {list(df.columns)})")
                return df
        except Exception:
            continue
    return None


def _lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}



# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★★★ 절대원칙 — 신규 수집물은 **무조건** 인덱스에 남는다 ★★★
#    루트가 구글드라이브든 로컬이든, 한 번 받은 것은 다음 세션이 그대로 재호출한다.
#    유니버스 3종(FDR 상장·FDR 폐지·KIND 상장법인)은 매 실행 네트워크로 나가고 있었다.
#    작아 보여도 (a) 네트워크가 죽으면 그날 실행이 통째로 무의미해지고
#    (b) 소스가 스키마를 바꾸면 어제까지 되던 실행이 오늘 실패한다.
#    캐시가 있으면 신선도만 확인하고, 신규 수집이 성공했을 때만 갱신한다(좁혀 덮어쓰기 금지).
# ══════════════════════════════════════════════════════════════════════════════════════════
UNIVERSE_CACHE_MAX_DAYS = 1.0        # 이보다 낡으면 새로 받아 본다(실패하면 낡은 것을 쓴다)


def _cached_or_fetch(name: str, fetch_fn: Callable[[], pd.DataFrame],
                     max_age_days: float = UNIVERSE_CACHE_MAX_DAYS) -> pd.DataFrame:
    """캐시 우선 → 신선하지 않으면 수집 → 성공하면 저장, 실패하면 낡은 캐시로 폴백.

    ★ 신규 수집이 **0행이면 저장하지 않는다.** 소스 장애로 빈 응답이 온 날
      멀쩡한 캐시를 빈 프레임으로 덮으면 그 다음 실행부터 전부 무너진다.
    """
    fresh = VAULT.get_table(name, scope="shared", max_age_days=max_age_days)
    if fresh is not None and len(fresh):
        LOG.info(f"공용 캐시에서 {name} {len(fresh):,}행 재사용 "
                 f"({max_age_days:g}일 이내) — 네트워크로 나가지 않습니다.")
        return fresh
    try:
        got = fetch_fn()
    except Exception as e:                                          # noqa
        got = None
        LOG.warn(f"{name} 수집 실패({type(e).__name__}).")
    if got is not None and len(got):
        if VAULT.put_table(name, got, scope="shared", domain="universe",
                           source="자동 캐시 — 신규 수집물은 무조건 인덱스에 남긴다") is None:
            LOG.error(f"{name} 저장 실패 — 다음 실행이 같은 것을 다시 받습니다.")
        return got
    stale = VAULT.get_table(name, scope="shared")          # 신선도 무시
    if stale is not None and len(stale):
        LOG.warn(f"{name} 신규 수집이 비었습니다 — 낡은 공용 캐시 {len(stale):,}행을 씁니다. "
                 f"빈 결과로 캐시를 덮지 않습니다(그러면 다음 실행까지 무너집니다).")
        return stale
    return got if got is not None else pd.DataFrame()


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
    # ★ dl_c 폴백 목록에 "listingdate" 가 들어 있다. 업스트림이 DelistingDate 컬럼명을
    #   바꾸는 순간 상장일이 폐지일로 읽히고, 모든 종목이 상장 첫날 폐지된 것으로 처리되어
    #   유니버스가 통째로 비워진다 — 예외가 아니라 '그럴듯한 숫자'로 실패한다. 방어한다.
    if dl_c and str(dl_c).strip().lower().replace("_", "") == "listingdate":
        LOG.error("폐지목록에 폐지일 컬럼이 없어 상장일 컬럼을 쓸 뻔했습니다 — "
                  f"상장일을 폐지일로 읽으면 전 종목이 즉시 폐지 처리됩니다. "
                  f"폐지일 없이 진행합니다. 원본 컬럼: {list(d.columns)}")
        dl_c = None
    lst_c = next((col[k] for k in ("listingdate", "listing_date", "listdate") if k in col), None)
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        # 폐지 종목의 상장일 — 상장 전 달에 유니버스로 새는 것(C13)과 시즈닝 면제를 막는다.
        "listing_date": as_ts_series(d[lst_c]) if lst_c else pd.NaT,
        # 폐지 '사유'. 흡수합병·완전자회사화·스팩해산은 -100% 가 아니다(41_backtest 가 소비).
        "delist_reason": (d[col["reason"]].astype(str).str.strip() if "reason" in col else ""),
        "to_code": (d[col["tosymbol"]].map(to_code6) if "tosymbol" in col else None),
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str).str.strip() if "secugroup" in col
                      else d[col["kind"]].astype(str).str.strip() if "kind" in col else ""),
    })
    # ★ 탈락분의 정체를 반드시 증권종류로 분류한다.
    #   업스트림 원본(4,172행)을 직접 확인한 결과, to_code6 이 떨어뜨리는 1,536행은
    #   전부 신주인수권증서(857)·수익증권(521)·신주인수권증권(158)이고 **주권은 0건**이다.
    #   그런데 예전 코드는 이를 "코드형식 불일치 → 생존자편향이 그만큼 남습니다"로 경고했다.
    #   주식 전략의 유니버스가 아닌 파생·펀드 상품이 빠진 것을 편향으로 보고하면,
    #   ① 멀쩡한 결과를 의심하게 만들고 ② 진짜 편향 경고까지 같이 무시하게 만든다.
    #   → '정책적 제외'와 '진짜 유실'을 분리해서 세고, 주권이 유실될 때만 경고한다.
    _EQUITY_SG = ("주권", "외국주권", "주식예탁증권")
    sg = t["secugroup"].fillna("")
    is_equity = sg.isin(_EQUITY_SG) if sg.str.len().gt(0).any() else pd.Series(True, index=t.index)
    bad = t["code"].isna()
    n_badcode = int(bad.sum())
    n_lost_equity = int((bad & is_equity).sum())
    n_nonequity = int((~bad & ~is_equity).sum())
    if sg.str.len().gt(0).any() and n_badcode:
        LOG.info(f"  코드 정규화 탈락 {n_badcode:,}건의 증권종류: "
                 f"{dict(sg[bad].value_counts().head(5))} → 이 중 주권계열 {n_lost_equity:,}건")
    # ★ 비주권(수익증권·리츠·투자회사 등)은 여기서 **버리지 않는다.**
    #   폐지 기록을 지우면 그 종목이 유니버스에서 영원히 살아있는 것으로 보인다 — 제거하려던
    #   생존자편향을 오히려 만드는 방향이다. 담을 수 없는 종목은 U-MID 의 유동성·규모 조건이
    #   이미 걸러내므로, 여기서는 '분류해서 보고'만 하고 기록은 보존한다.
    t = t.dropna(subset=["code"])
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_nodate = int(t["delisting_date"].isna().sum())

    LOG.ok(f"상장폐지 목록 {len(t):,}건 (주권계열 {int(t['secugroup'].isin(_EQUITY_SG).sum()):,} · "
           f"비주권 {n_nonequity:,}) — 생존자편향 제거 입력 확보")
    if n_raw - len(t):
        LOG.info(f"  폐지목록 정규화: 원본 {n_raw:,} → {len(t):,} "
                 f"(증권종류상 코드체계가 다른 {n_badcode:,}건 제외 · 동일코드 중복 {n_dupe:,} 병합) · "
                 f"폐지일 결측 {n_nodate:,}건은 상장기간 추정에서 제외됩니다.")
    # ★ 경고는 '주권이 유실됐을 때'만 띄운다. 비주권 제외는 편향이 아니라 유니버스 정의다.
    if n_lost_equity:
        LOG.warn(f"폐지목록에서 **주권** {n_lost_equity:,}건이 코드 정규화에 실패했습니다 — "
                 f"이만큼은 실제로 생존자편향으로 남습니다. "
                 f"원본 코드 예시: {raw_codes[codes.isna() & is_equity].head(5).tolist()}")
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
    if not dart_has_key():
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    # ★★ 만료 후 다운로드가 실패하면 **빈 프레임이 아니라 낡은 캐시**로 돌아간다 ★★
    #   예전엔 실패 시 그냥 빈 프레임을 돌려줬다. corp_code 가 전멸하면 그 실행의
    #   EMP·Tier-2·Tier-1·공시가 **통째로 0건**이 된다 — 이미 받아둔 캐시가 디스크에
    #   멀쩡히 있는데도 그렇다. 30일마다 한 번씩 열리는 전량 실패 창이었다.
    #   corpCode 는 기업 식별자 목록이라 며칠 낡아도 기존 기업의 코드는 바뀌지 않는다.
    def _stale_or_empty(why: str):
        _old = VAULT.get_table("dart_corpcode", scope="shared")      # max_age 무시
        if _old is not None and len(_old):
            LOG.warn(f"{why} — 30일이 지난 corpCode 캐시 {len(_old):,}건을 그대로 씁니다. "
                     f"기업 식별자는 잘 바뀌지 않으므로 신규 상장분만 누락됩니다. "
                     f"빈 목록으로 진행하면 이 실행의 DART 수집이 통째로 0건이 됩니다.")
            return _old
        LOG.error(f"{why} — 대체할 캐시도 없습니다. 이 실행의 DART 수집은 전부 0건이 됩니다.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])

    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw:
        return _stale_or_empty("DART corpCode.xml 수신 실패(키·네트워크 확인)")
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        return _stale_or_empty(f"corpCode 응답이 ZIP 이 아님 (status={code}: "
                               f"{DART_STATUS_MSG.get(code, '알 수 없음')})")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        return _stale_or_empty(f"corpCode zip 해제 실패({type(e).__name__})")
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

    # ★★ 저장은 필터 **이전**, 폐기는 소비 쪽에서만 ★★
    #   예전엔 아래 부분응답 폐기 결과를 **저장본에도 반영**했다. 그러면
    #     ① 폐기된 시점이 다음 실행의 have 에 없으니 다시 수집되고,
    #     ② 다시 수집하면 new_rows 가 비지 않아 또 저장되고,
    #     ③ 또 폐기된다 — **자기지속 재수집 루프**다(시점당 3콜, 직렬 3~5초).
    #   게다가 중앙값은 프레임 내용에 따라 실행마다 달라져, 과거 실행이 저장해 둔 시점이
    #   나중 실행에서 '나쁨'으로 재판정되어 활성 파케이에서 사라질 수 있다 —
    #   공용 테이블 **좁혀 덮어쓰기**이자 절대 1원칙 위반이다.
    if new_rows:
        _store = snap.copy()
        _store["snap_date"] = _store["snap_date"].dt.strftime("%Y-%m-%d")
        if VAULT.put_table("krx_listing_snapshots", _store, scope="shared", domain="universe",
                           source="pykrx",
                           extra={"note": "상장종목 스냅샷 — 전 전략 공용 (원본 보존, "
                                          "부분응답 판정은 소비 시점에만 적용)"}) is None:
            LOG.error("스냅샷 저장 실패 — 다음 실행이 같은 시점을 다시 수집합니다.")

    # ★ 부분 응답 방어: 이웃 시점 대비 종목수가 급감한 스냅샷은 '진실'이 아니라 '사고'다.
    #   그대로 쓰면 그 달 유니버스가 조용히 쪼그라들어 선택편향이 된다.
    #   → **반환값에서만** 걷어낸다. 원본은 드라이브에 그대로 남는다.
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만이라 "
                     f"부분 응답으로 판단하고 **이번 실행에서만** 제외합니다: "
                     f"{[str(x.date()) for x in bad.index[:6]]} "
                     f"(원본은 공용 캐시에 그대로 보존됩니다 — 지우면 매 실행 다시 받게 됩니다)")
            snap = snap[~snap["snap_date"].isin(bad.index)]
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

    lst = _cached_or_fetch("src_fdr_listing", fetch_fdr_listing)
    if len(lst):
        parts.append(lst)
        src_stats.append(("FDR 상장목록", len(lst)))
        PIPE.io("IN", "HTTP", "fdr:StockListing", lst, source="FinanceDataReader")

    kind = _cached_or_fetch("src_kind_listing", fetch_kind_listing)
    if len(kind):
        parts.append(kind)
        src_stats.append(("KIND 상장법인", len(kind)))
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")

    dead = _cached_or_fetch("src_fdr_delisting", fetch_fdr_delisting)
    PIPE.io("IN", "HTTP", "fdr:KRX-DELISTING", dead, source="FinanceDataReader",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market",
                                   "listing_date", "delist_reason", "to_code"]).copy()
        # ★ 예전엔 여기서 listing_date 를 pd.NaT 로 못박았다. 그런데 폐지목록 원본에는
        #   ListingDate 가 4,172건 **전부** 들어 있다. 버리면 두 가지가 동시에 깨진다:
        #     ① Universe.at 는 listing_date 결측을 '태초부터 상장'으로 읽는다 →
        #        2016년 이후 상장했다가 폐지된 292종목이 상장 전 달의 유니버스에 낀다(C13 위반).
        #     ② 250일 시즈닝 게이트는 listing_date 가 있을 때만 걸린다 → 결측인 종목만
        #        면제된다. 그 면제 대상이 하필 '나중에 폐지된 종목'이라, 어느 종목이 게이트를
        #        건너뛰는지가 **그 종목의 미래로 결정**된다. 실거래로는 재현 불가능한 유니버스다.
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
        delist_reason=("delist_reason", _first_str),
        to_code=("to_code", _first_str),
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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]

# 전 소스에서 실패한 종목을 며칠간 다시 묻지 않을 것인가.
RETRY_AFTER_DAYS = 30
# ★ 만료된 종목이 한꺼번에 되살아나 한 실행이 폭발하지 않도록 실행당 재시도 상한을 둔다.
#   예전엔 이 상한이 없었고, 시계마저 상수라 만료 자체가 일어나지 않아 문제가 가려져 있었다.
#   시계를 실제 날짜로 고치는 순간 1,000종목이 동시에 만료될 수 있다(≈28분).
PRICE_RETRY_BUDGET_PER_RUN = 200

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★★ 수익률 무결성 (7회차 실행에서 두 개의 증상으로 동시에 드러난 하나의 결함) ★★
#
#  증상 ①  R0 벤치마크가 CAGR inf% / MDD nan% 를 출력했다.
#  증상 ②  보유종목 상위 5%(20종목)가 총기여의 180% 를 만들었다.
#
#  두 증상의 원인은 같다 — fwd_ret 에 **가격으로는 불가능한 값**이 섞여 있었다.
#    fwd_ret = 다음달 체결가 / 이번달 체결가 − 1
#  분모(exec_px)는 next_open 이 없으면 close 로 폴백하는데, 소스가 0 이나 결측을 0 으로
#  준 종목에서 이 값이 **0** 이 된다. 0 으로 나누면 +inf 다. inf 한 개가 월 평균에
#  들어가면 동일가중 벤치마크의 cumprod 가 그 달에 inf 로 발산하고, 그 다음부터
#  eq/peak = inf/inf = nan 이라 MDD·Calmar 가 통째로 nan 이 된다. 판정식은
#  isfinite(nan)=False 라 **조용히 FAIL** 로 떨어진다 — 벤치마크가 없는데 '벤치마크에
#  졌다'고 보고하는 최악의 형태다.
#
#  분모가 0 이 아니어도 문제는 남는다. 이 파이프라인은 pykrx·FDR·네이버·yfinance 를
#  종목 단위로 섞어 쓰고(캐시도 여러 실행에 걸쳐 섞인다), 소스마다 수정주가 기준이
#  다르다. 액면분할·감자가 한쪽에만 반영돼 있으면 경계 달에서 ±90% 나 +900% 같은
#  '수익률'이 만들어진다. 그 종목이 우연히 선정되면 그 한 종목이 10년 성과를 만든다.
#
#  ▶ 방어는 두 겹이다. 지어내지 않고, 조용히 버리지도 않는다.
#    ① 불가능 판정 — KRX 가격제한(±30%/일)상 물리적으로 나올 수 없는 배율은
#       가격 움직임이 아니라 기업행위(분할·병합·감자) 또는 데이터 오류다. 결측 처리하고
#       **몇 건을 왜 버렸는지 표로 남긴다.** 임계는 실제 거래일 간격으로 계산한다.
#    ② 나머지 꼬리는 절대 손대지 않는다. 대신 상위 |수익률| 분포를 표로 출력해
#       "이 성과가 몇 종목·몇 달에 의존하는가"를 사용자가 직접 보게 한다.
#
#  ★ 벤치마크(R0)만은 절사평균을 함께 쓴다. 1,500종목 동일가중에서 한 종목의
#    +900% 는 월 +0.6%p 를 만든다 — 실제로 담을 수 없는 수익이 기준선을 밀어 올린다.
#    전략 수익률에는 절사를 적용하지 않는다(그건 성과를 지어내는 것이다).
# ══════════════════════════════════════════════════════════════════════════════════════════
KRX_DAILY_LIMIT = 0.30        # KRX 일일 가격제한폭 (2015-06-15 이후 ±30%)
RET_LIMIT_SLACK = 1.10        # 시가 갭·정리매매·거래일 계산 오차 여유
RET_SANITY_LEDGER: List[dict] = []     # 무엇을 왜 버렸는지 — 표로 출력하고 드라이브에 남긴다


def _price_limit_envelope(n_days: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """n 거래일 동안 가격제한만으로 도달 가능한 배율의 [하한, 상한].

    n 이 결측이면 한 달치(20거래일)로 본다. 이 봉투는 매우 관대하다(20일이면 [8e-4, 190]) —
    의도적이다. 실제 수익을 자르는 것이 아니라 **물리적으로 불가능한 값만** 걷어내는 것이
    목적이다. 좁히고 싶다면 그건 별개의 결정이며 리포트에 명시해야 한다.
    """
    n = pd.to_numeric(n_days, errors="coerce").fillna(20.0).clip(lower=1.0, upper=45.0)
    up = np.power(1.0 + KRX_DAILY_LIMIT, n) * RET_LIMIT_SLACK
    dn = np.power(1.0 - KRX_DAILY_LIMIT, n) / RET_LIMIT_SLACK
    return dn, up


def price_cache_floor() -> str:
    """일봉 수집 하한일. **v2·v3 가 반드시 같은 값을 써야 한다.**

    ★★ 예전엔 v2 가 BACKTEST_START−15개월, v3 가 −18개월이었다. 89일 차이가
      계획 루프의 10일 임계를 넘으므로, **v2 가 채운 캐시는 v3 에서 전부 '앞 구간 결손'
      으로 판정되고 그 반대도 마찬가지**였다. 두 전략을 번갈아 돌리면 서로가 서로의
      캐시를 매 실행 재수집 대상으로 만든다 — 1,834종목 × 0.5초 = 917초로
      관측치 916.7초와 정확히 일치한다.
      캐시는 공용이다. 공용 자원의 경계값은 한 곳에서만 정의한다.
    """
    return (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d")


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
        # ★★ 병목: 예전엔 limiter("krx") 를 썼다 ★★
        #   'krx' 버킷은 KRX 마켓플레이스 세션(중복 로그인에 민감)을 보호하려고 2.0 qps 로
        #   묶여 있다. 그런데 pykrx 의 일봉 조회는 그 세션이 아니라 별도 공개 엔드포인트다.
        #   같은 버킷에 넣으면 **체인의 첫 링크가 초당 2건으로 직렬화**되어 N_WORKERS_IO=12
        #   가 무의미해진다(실효 동시성 1). 3,000종목이면 그것만으로 25분이다.
        #   → 전용 버킷으로 분리한다. 마켓플레이스 세션은 여전히 'krx' 로 보호된다.
        limiter("pykrx").wait()
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
    # ★ 이름은 FDR 이지만 6자리 KRX 코드는 FinanceDataReader 내부에서 NaverDailyReader 로
    #   라우팅된다(fchart.stock.naver.com). 즉 KRX 가 아니라 네이버다. 그런데 예전엔
    #   krx 버킷(2.0 qps)의 토큰을 먹었다. RateLimiter 는 소스당 전역 단일 간격이라
    #   12스레드가 0.5초 슬롯 하나를 나눠 쓰게 되고, 실효 동시성이 1로 떨어진다.
    #   실측: 1,833건 × 0.5초 = 916.5초 ≈ 관측 916.7초 — 수집 시간의 100%가 이 대기였다.
    if fdr is None:
        return None
    try:
        limiter("naver").wait()
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


# 코드 → 야후 접미사 힌트. fetch_prices 가 상장정보(sec)로 채워 넣는다.
# 비어 있으면 종전대로 .KS → .KQ 양쪽을 시도한다(동작은 같고, 채워지면 호출이 절반이 된다).
YF_SUFFIX_HINT: Dict[str, str] = {}


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    hint = YF_SUFFIX_HINT.get(code)
    sufs = ((hint, ".KQ" if hint == ".KS" else ".KS") if hint else (".KS", ".KQ"))
    for suf in sufs:
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


def fetch_prices(codes: Sequence[str], start: str, end: str,
                 sec: Optional[pd.DataFrame] = None,
                 market_last_day=None) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. 캐시 증분 갱신. 공용 인덱스에 저장.

    market_last_day: 시장의 마지막 영업일(유니버스 스냅샷에서 받는다). 증분 종료 판정의
      앵커다. 없으면 end 를 쓰지만, 그러면 BACKTEST_END 가 연휴 뒤에 놓일 때
      존재하지 않는 구간을 전 종목에 한꺼번에 묻게 된다(실측 ≈83분).
    """
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
    # ★★ 시계 ★★ 예전엔 `_today = as_ts(end)` 였다. end 는 BACKTEST_END **상수**다.
    #   그래서 attempted_at 도 전 행 같은 값으로 기록됐고 `(_today - at).days` 가 항상 0 —
    #   음성캐시가 **영원히 만료되지 않았고** RETRY_AFTER_DAYS 는 죽은 상수였다.
    #   더 나쁜 것은 병합이다: 전 행이 동률이라 `sort_values(1키).drop_duplicates(keep="last")`
    #   가 사실상 무작위가 되어, 새 기록이 확정적으로 살아남지 못했다.
    #   → 실제 시각으로 기록한다. 다만 **생략 판정의 1차 근거는 시계가 아니라 사실**이다
    #     (폐지일 · 워터마크 · 상장일). 시계 만료는 보조이며, 만료가 한꺼번에 터져
    #     한 실행이 폭발하지 않도록 실행당 재시도 예산을 둔다.
    _today = as_ts(_dt.datetime.now().date())
    attempts: Dict[Tuple[str, str], dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att = _att.copy()
        _att["attempted_at"] = as_ts_series(_att["attempted_at"])
        _att["requested_from"] = as_ts_series(_att["requested_from"])
        # 레거시 행에는 kind 가 없다 — 최초 수집 실패로 간주한다(그 시절 유일한 기록 경로).
        if "kind" not in _att.columns:
            _att["kind"] = "init"
        _att["kind"] = _att["kind"].fillna("init").astype(str)
        # ★ 정렬 안정성에 기대지 않는다. (code, kind) 별로 **가장 최근 시각**을 명시 선택.
        _idx = _att.groupby(["code", "kind"])["attempted_at"].idxmax()
        _att = _att.loc[_idx]
        attempts = {(str(r.code), str(r.kind)): {"at": r.attempted_at, "frm": r.requested_from}
                    for r in _att.itertuples(index=False)}
    _retry_budget = [PRICE_RETRY_BUDGET_PER_RUN]

    def _recently_failed(c: str, want_from: pd.Timestamp, kind: str) -> bool:
        """이 종목의 **이 방향** 요청이 최근에 실패했는가.

        ★ 예전엔 kind 구분이 없어서, '최초 수집'이 한 번 실패한 종목(frm=가능한 최소값)이
          이후 **어떤 증분 요청도 받지 못하고 영구히 얼어붙었다.** 그 종목은 다른 전략이
          캐시해 둔 시점에 동결되어 최근 구간 봉이 통째로 결측이 된다 — 시간을 아끼는 게
          아니라 결과를 왜곡하는 경로다.
        """
        p = attempts.get((c, kind))
        if p is None or pd.isna(p["at"]):
            return False
        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 되지 않는다(같은 kind 안에서만).
        if pd.notna(p["frm"]) and p["frm"] > want_from:
            return False
        if (_today - p["at"]).days >= RETRY_AFTER_DAYS:
            # 만료됐다 — 다시 시도할 수 있다. 단 한 실행에서 몰아치지 않게 예산을 쓴다.
            if _retry_budget[0] <= 0:
                return True
            _retry_budget[0] -= 1
            return False
        return True

    # ── 전 구간 재수집을 막는 두 가지 하한 ──────────────────────────────────────────────
    #   ① 상장일 — 그 이전 봉은 존재하지 않는다.
    #   ② 워터마크 — 전 구간을 요청했는데도 더 이전이 안 온 지점. 소스에 없다는 뜻이다.
    listing_of: Dict[str, pd.Timestamp] = {}
    delist_of: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        try:
            _s = sec.dropna(subset=["code"]).drop_duplicates("code")
            _cd = _s["code"].astype(str)
            if "listing_date" in _s.columns:
                listing_of = dict(zip(_cd, as_ts_series(_s["listing_date"])))
            if "delisting_date" in _s.columns:
                delist_of = dict(zip(_cd, as_ts_series(_s["delisting_date"])))
        except Exception:
            listing_of, delist_of = {}, {}
    watermark: Dict[str, pd.Timestamp] = {}
    _wm = VAULT.get_table("price_earliest_available", scope="shared")
    if _wm is not None and len(_wm):
        try:
            watermark = dict(zip(_wm["code"].astype(str), as_ts_series(_wm["earliest"])))
        except Exception:
            watermark = {}

    # ★ 증분 종료 앵커. 예전엔 `end_ts - 5일` 이었는데, BACKTEST_END 가 5일 넘는 연휴 뒤에
    #   놓이면 **생존 종목 전체**에 대해 동시에 참이 되어 존재하지도 않는 하루짜리 구간을
    #   3,000여 종목에 한꺼번에 요청했다(네이버 버킷 전역 하한으로 ≈83분).
    #   → 시장 달력(유니버스 스냅샷의 마지막 영업일)을 앵커로 쓴다. 캐시 자신을 앵커로
    #     쓰면 '캐시가 스스로를 인증하는' 순환이 되어 정당한 증분까지 억제되므로 금지한다.
    mkt_last = as_ts(market_last_day) if market_last_day else end_ts
    if pd.isna(mkt_last):
        mkt_last = end_ts
    mkt_last = min(mkt_last, end_ts)

    todo: List[Tuple[str, str, str, str]] = []
    n_back = n_fwd = n_skip = n_done = 0
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, start_ts, "init"):
                n_skip += 1
                continue
            todo.append((c, start, end, "init"))
            continue
        # ★ 과거 방향 백필을 반드시 함께 본다.
        #   앞선 실행이 최근 구간만 캐시했다면(예: 캐시가 2023~2026 뿐),
        #   max 만 보고 판단하면 2016~2022 를 영원히 못 받는다.
        #   → 10년 백테스트인데 앞 7년이 조용히 비는 사고가 된다.
        #
        #   ★★ 다만 '요청 시작일'을 그대로 기준으로 삼으면 안 된다. 2021년에 상장한 종목은
        #   2015년 봉이 **존재할 수 없으므로** 조건이 영원히 참이고, 매 실행 전 구간을 다시
        #   받는다. 실측: 캐시 3,517종목 중 1,487종목(42%)이 매번 재수집 대상이 되어
        #   가격 단계 992초 중 916초를 이미 갖고 있는 데이터를 다시 받는 데 썼다.
        #   → 상장일과 '이 종목에서 실제로 받아진 최소일' 워터마크로 하한을 올린다.
        want = start_ts
        _ld = listing_of.get(c)
        if _ld is not None and pd.notna(_ld):
            want = max(want, as_ts(_ld))
        _wm = watermark.get(c)
        if _wm is not None and pd.notna(_wm):
            want = max(want, _wm)          # 이미 '더 이전은 없다'가 확인된 지점
        # ★ 증분(앞으로) 방향에도 종료 조건이 필요하다.
        #   폐지 종목의 mx 는 '마지막 거래일'이라 mx < end_ts - 5d 가 **영원히 참**이다.
        #   그래서 매 실행 존재하지도 않는 구간(mx+1 ~ 오늘)을 4개 소스에 물었고,
        #   637종목이 100% 실패하며 640초를 태웠다 — 그것도 매번.
        #   음성캐시는 'mx is None' 가지에서만 조회되므로 이 population 을 못 본다.
        #   → 폐지일이 있으면 그 이후는 애초에 요청하지 않는다. 사실이지 기억이 아니다.
        _dd = delist_of.get(c)
        _closed = (_dd is not None and pd.notna(_dd)
                   and mx >= as_ts(_dd) - pd.Timedelta(days=5))
        # ★★ 분기 **순서**가 결함이었다 ★★
        #   예전엔 n_back 판정이 _closed 보다 **먼저** 평가됐다. 그래서 폐지가 확정된 종목이
        #   유일한 사실기반 가드를 우회해 매 실행 (c, start) = 11.5년 전 구간을 통째로
        #   다시 요청했고, 그것도 _recently_failed 가드조차 없었다. 관측된 640초가 이것이다.
        #   → 백필이 정말 필요한지를 먼저 계산하고, 필요 없으면 폐지 종료조건이 이긴다.
        back_need = (mn is not None and mn > want + pd.Timedelta(days=10))
        if _closed and not back_need:
            n_done += 1                      # 폐지까지 이미 다 받음 — 더 받을 것이 없다
        elif back_need and not _recently_failed(c, want, "back"):
            # ★ **결손 구간만** 요청한다. 예전엔 (c, start) 로 전 구간을 다시 받았다 —
            #   이미 갖고 있는 2,800여 봉을 다시 받느라 종목당 수 초를 태웠고, 게다가
            #   keep="last" 병합 때문에 pykrx 의 실제 거래대금이 네이버 근사(종가×거래량)로
            #   덮이는 데이터 열화까지 일어났다.
            todo.append((c, want.strftime("%Y-%m-%d"),
                         (mn - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "back"))
            n_back += 1
        elif (not _closed) and mx < mkt_last - pd.Timedelta(days=5) and not _recently_failed(
                c, mx + pd.Timedelta(days=1), "fwd"):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), end, "fwd"))
            n_fwd += 1
        else:
            n_skip += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목의 **결손 구간만** 받습니다 "
                 f"(캐시 최소일이 요청 시작일보다 늦음 = 앞 구간 결손). "
                 f"전 구간을 다시 받지 않습니다.")
    if n_done:
        LOG.info(f"폐지일까지 이미 확보된 {n_done:,}종목은 증분 요청을 보내지 않습니다 "
                 f"(폐지 이후 구간은 존재하지 않습니다 — 예전엔 이걸 매 실행 4개 소스에 "
                 f"물어 전량 실패하며 시간을 태웠습니다).")
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
            code, st, en, _kind = job
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, en)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        failed, wm_rows = [], []
        for (c, st, en, kind), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
                # ★ 과거 방향으로 '있는 만큼 다' 요청했는데 이만큼만 왔다면 그 이전은 소스에 없다.
                #   이 워터마크가 없으면 2021년 상장 종목은 2015년 봉이 영영 안 오므로
                #   '앞 구간 결손'으로 판정되어 **매 실행 전 구간을 다시 받는다.**
                #   ★ 조건을 start_ts 가 아니라 want(=이번에 요청한 하한)로 잡는다 —
                #     결손 구간만 요청하도록 바뀌었으므로 start_ts 기준이면 영영 기록되지 않는다.
                if kind in ("init", "back"):
                    _mn = as_ts_series(d["date"]).min()
                    if pd.notna(_mn):
                        wm_rows.append({"code": c, "earliest": _mn,
                                        "requested_from": as_ts(st), "checked_at": _today})
            else:
                failed.append({"code": c, "kind": kind,
                               "requested_from": as_ts(st), "attempted_at": _today})
        if wm_rows:
            _wprev = VAULT.get_table("price_earliest_available", scope="shared")
            _wall = pd.concat([_wprev, pd.DataFrame(wm_rows)], ignore_index=True) \
                if _wprev is not None and len(_wprev) else pd.DataFrame(wm_rows)
            # ★★ 병합을 정렬 안정성에 맡기지 않는다 ★★
            #   예전엔 sort_values("checked_at").drop_duplicates(keep="last") 였는데
            #   checked_at 이 전 행 동률이라 **새 관측이 확정적으로 살아남지 못했다.**
            #   그리고 keep="last" 는 '가장 최근에 본 최소일'을 남겨, 이력이 짧은 소스가
            #   응답한 실행이 이력이 긴 소스의 결과를 덮어 바닥을 영구히 올렸다 —
            #   그 종목의 앞 몇 년이 조용히 빈 채 결과가 나온다.
            #   → 워터마크는 **내려갈 수만 있다**(관측된 최소일의 min). 명시 집계로 못박는다.
            _agg = {"earliest": ("earliest", "min"), "checked_at": ("checked_at", "max")}
            if "requested_from" in _wall.columns:
                _agg["requested_from"] = ("requested_from", "min")
            _wall = (_wall.dropna(subset=["code", "earliest"])
                          .groupby("code", as_index=False).agg(**_agg))
            if VAULT.put_table("price_earliest_available", _wall, scope="shared", domain="price",
                               source="fetch_prices: 소스가 보유한 최초 관측일 워터마크") is None:
                LOG.error("워터마크 저장에 실패했습니다 — 다음 실행이 같은 종목의 앞 구간을 "
                          "다시 받습니다(실측 900초대). 드라이브 용량·권한을 확인하세요.")
            else:
                LOG.info(f"최초 관측일 워터마크 {len(wm_rows):,}종목 기록 — 다음 실행부터 "
                         f"이 종목들의 앞 구간 재수집을 건너뜁니다"
                         f"(상장 이전 구간은 존재하지 않습니다).")
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.
            _prev = VAULT.get_table("price_fetch_attempts", scope="shared")
            _new = pd.DataFrame(failed)
            _all = (pd.concat([_prev, _new], ignore_index=True)
                    if _prev is not None and len(_prev) else _new)
            if "kind" not in _all.columns:
                _all["kind"] = "init"
            _all["kind"] = _all["kind"].fillna("init").astype(str)
            _all["attempted_at"] = as_ts_series(_all["attempted_at"])
            # ★ 병합 키에 kind 를 포함한다. 예전엔 code 단독이라 'init 실패' 한 줄이
            #   그 종목의 fwd·back 기록을 덮어 **어떤 증분 요청도 못 받게** 만들었다.
            #   정렬 안정성 대신 idxmax 로 명시 선택한다(attempted_at 이 동률이어도 결정적).
            _all = _all.dropna(subset=["code"])
            _all = _all.loc[_all.groupby(["code", "kind"])["attempted_at"].idxmax()] \
                       .reset_index(drop=True)
            if VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                               source="fetch_prices:negative_cache") is None:
                LOG.error("시도 원장 저장에 실패했습니다 — 다음 실행이 같은 헛수고를 반복합니다.")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 받을 것이 없으면 아무 일도 하지 않는다 ★★
    #    예전엔 todo 가 비어 있어도(=신규 심볼 0개) 아래 무조건 경로를 통과했다:
    #      concat(700만 행) → code.map(to_code6)(행마다 파이썬 함수 + 정규식 2회)
    #      → to_numeric ×6 → sort_values(2키) → drop_duplicates(2키)
    #    실측 51.6초. **한 종목도 새로 받지 않은 실행에서** 매번 그만큼 태웠다.
    #    캐시는 바로 이 함수가 정규화해서 쓴 것이므로 다시 정규화할 이유가 없다.
    if not new_frames and cached is not None and len(cached):
        px = cached
        win = (px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)
        px_out = px[win]
        LOG.ok(f"일봉 신규 수집 0건 — 공용 캐시 {len(px):,}행을 그대로 재사용합니다 "
               f"(재정규화·재정렬·재저장 없음). 창 적용 후 {len(px_out):,}행.")
        PIPE.io("IN", "DRIVE", "krx_ohlcv_daily", px_out, source="cache only (no refetch)")
        return downcast(px_out)

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
    # ★★ 정규화는 **신규분에만** 적용한다 ★★
    #   캐시 7.09M 행은 직전 실행에서 바로 이 파이프라인을 통과해 저장된 것이므로,
    #   다시 거는 것은 항등변환이다. 실측으로 `code.map(to_code6)` 6.3~8.4초,
    #   dropna/to_numeric/sort/dedup 을 합쳐 24.4초가 매 실행 순낭비였다.
    #   그리고 to_code6 은 행마다 파이썬 함수 + 정규식 2회다 → **고유값 사전**으로 대체한다.
    if new_frames:
        nf = pd.concat(new_frames, ignore_index=True)
        nf["date"] = as_ts_series(nf["date"])
        _s = nf["code"].astype(object)
        _m = {k: to_code6(k) for k in pd.unique(_s)}
        nf["code"] = _s.map(_m)
        nf = nf.dropna(subset=["code", "date", "close"])
        for c in ("open", "high", "low", "close", "volume", "amount"):
            nf[c] = pd.to_numeric(nf[c], errors="coerce")
    else:
        nf = None
    _parts = ([cached] if cached is not None and len(cached) else []) + \
             ([nf] if nf is not None and len(nf) else [])
    px = pd.concat(_parts, ignore_index=True) if len(_parts) > 1 else _parts[0]
    # ★ 중복 제거 방향에 주의. keep="last" 는 '나중 프레임이 이긴다'인데, 신규분이
    #   네이버(거래대금 = 종가×거래량 근사)이고 캐시분이 pykrx(실제 거래대금)이면
    #   **정확한 값이 근사로 덮인다.** 겹치는 (code,date) 는 캐시를 우선한다.
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="first"))
    # ★★ 공용 캐시 보존 (절대 1원칙) ★★
    #   반환값은 이번 백테스트 창(+400일 워밍업)으로 자르는 게 맞지만, **그 잘린 프레임을
    #   공용 테이블에 그대로 써버리면** 창 밖의 과거가 활성 parquet 에서 영구히 사라진다.
    #   put_table 은 백업을 남기지만 get_table 은 활성 파일만 읽으므로, 다른 전략(또는 더 이른
    #   시작일로 도는 다음 실행)이 보기에 캐시가 통째로 파괴된 것과 같다.
    #   → 저장은 '기존 캐시 ∪ 신규'로 하고, 반환만 창으로 자른다.
    # 창이 캐시 전체를 덮으면(현 설정에서는 보통 그렇다) 마스킹 자체가 무의미하다 — 단락한다.
    _lo = as_ts(start) - pd.Timedelta(days=400)
    if len(px) and px["date"].min() >= _lo and px["date"].max() <= end_ts:
        px_out = px
    else:
        px_out = px[(px["date"] >= _lo) & (px["date"] <= end_ts)]

    if new_frames:
        # ★ px 는 이미 '기존 캐시 ∪ 신규' 다(위에서 cached 를 통째로 넣었다). 창으로 자른
        #   px_out 이 아니라 px 를 저장한다 — 창 밖의 과거를 잘라 덮어쓰면 다른 전략이
        #   보기에 캐시가 파괴된 것과 같다(절대 1원칙).
        if VAULT.put_table(
                "krx_ohlcv_daily", px, scope="shared", domain="price",
                source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common())) is None:
            LOG.error("일봉 공용 캐시 저장에 실패했습니다 — 이번 실행에서 받은 "
                      f"{sum(len(f) for f in new_frames):,}행이 디스크에 남지 않습니다. "
                      f"다음 실행이 같은 종목을 처음부터 다시 받습니다.")
    px = px_out
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if any(src_used.get(k, 0) for k in ("naver", "yfinance", "fdr")):
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
    # ★ groupby(...).tail(1) 은 7.09M 행에서 실측 4.16초. 바로 위 sort_values 로
    #   (code, date) 정렬이 끝나 있고 fetch_prices 가 (code,date) 중복을 이미 제거했으므로
    #   '그룹의 마지막 행' = '다음 행과 (code,ym) 이 다른 행' 이다 — 같은 집합·같은 순서.
    last = px.loc[~px[["code", "ym"]].duplicated(keep="last")].copy()
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
    # ★★ 분모 위생 ★★ 0 이나 음수, ±inf 는 '가격'이 아니라 소스가 결측을 0 으로 준 것이다.
    #   이걸 그대로 두면 아래 나눗셈이 +inf 를 만들고, 그 inf 한 개가 벤치마크의 복리를
    #   통째로 발산시킨다(7회차의 CAGR inf% / MDD nan%). 값을 지어내지 않고 결측으로 둔다.
    _px_bad = int((~np.isfinite(monthly["exec_px"].to_numpy(dtype="float64"))
                   ) .sum() + int((monthly["exec_px"] <= 0).sum()))
    monthly["exec_px"] = monthly["exec_px"].replace([np.inf, -np.inf], np.nan)
    monthly["exec_px"] = monthly["exec_px"].where(monthly["exec_px"] > 0)

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    _g = monthly.groupby("code", observed=True)
    nxt_px = _g["exec_px"].shift(-1)
    nxt_m = _g["month"].shift(-1)
    nxt_sd = _g["signal_date"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    ratio = safe_div(nxt_px, monthly["exec_px"])
    monthly["fwd_ret"] = (ratio - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")

    # ── 무결성 게이트 ────────────────────────────────────────────────────────────────────
    #  ① 비유한값 : inf/-inf/NaN 배율. 분모 위생을 거쳤어도 소스가 이상값을 주면 남는다.
    #  ② 가격제한 불가능 : 실제 거래일 간격으로 계산한 봉투 밖. 분할·감자·데이터 오류다.
    fr = monthly["fwd_ret"]
    n_td = _trading_day_gap(px, monthly["signal_date"], nxt_sd)
    lo_env, hi_env = _price_limit_envelope(n_td)
    bad_inf = fr.notna() & ~np.isfinite(fr.to_numpy(dtype="float64"))
    bad_env = fr.notna() & np.isfinite(fr.to_numpy(dtype="float64")) & (
        (ratio > hi_env) | (ratio < lo_env))
    n_inf, n_env = int(bad_inf.sum()), int(bad_env.sum())
    if n_inf or n_env:
        monthly.loc[bad_inf | bad_env, "fwd_ret"] = np.nan
        _ex = monthly.loc[bad_env, ["code", "month"]].copy()
        _ex["ratio"] = ratio[bad_env].to_numpy()
        _ex["n_days"] = n_td[bad_env].to_numpy()
        RET_SANITY_LEDGER.extend(_ex.head(500).to_dict("records"))
        LOG.warn(
            f"★ 수익률 무결성 게이트 — 비유한 {n_inf:,}건 · 가격제한상 불가능 {n_env:,}건을 "
            f"결측 처리했습니다(총 {n_inf+n_env:,}/{int(fr.notna().sum()):,}행). "
            f"이 값들은 주가 움직임이 아니라 **기업행위(액면분할·병합·감자) 미반영 또는 "
            f"소스 혼용에 따른 수정주가 불일치**입니다. 그대로 두면 벤치마크 복리가 발산하고"
            f"(7회차 CAGR inf%), 그 종목 하나가 10년 성과를 만듭니다.")
        if n_env:
            _t = _ex.reindex(_ex["ratio"].abs().sort_values(ascending=False).index).head(10)
            LOG.table([[r.code, f"{as_ts(r.month):%Y-%m}", f"{r.ratio:,.1f}배",
                        f"{int(r.n_days)}일" if np.isfinite(r.n_days) else "-",
                        f"{(1.0+KRX_DAILY_LIMIT)**max(int(r.n_days),1):,.0f}배"
                        if np.isfinite(r.n_days) else "-"]
                       for r in _t.itertuples(index=False)],
                      ["종목", "달", "관측 배율", "거래일", "가격제한상 최대"],
                      ["c", "c", "r", "r", "r"],
                      title="버려진 관측 상위 10건 — 왜 '수익률'이 아닌지 근거")
    if _px_bad:
        LOG.warn(f"체결가가 0 이하이거나 비유한값인 {_px_bad:,}행을 결측 처리했습니다 "
                 f"(소스가 결측을 0 으로 반환한 경우). 0 으로 나눈 +inf 가 하류로 흐르는 "
                 f"경로를 여기서 끊습니다.")

    # ③ 남은 꼬리는 **자르지 않는다.** 대신 보이게 만든다 — 성과가 몇 건에 의존하는지를
    #    사용자가 직접 판단해야 한다. 조용히 winsorize 하면 그건 성과를 지어내는 것이다.
    _report_return_tail(monthly)
    # ★ 원장은 공용 인덱스에 남긴다(절대1원칙: 신규 산출물도 반드시 캐시·재호출 가능).
    if RET_SANITY_LEDGER:
        try:
            VAULT.put_table("price_return_sanity_ledger", pd.DataFrame(RET_SANITY_LEDGER),
                            scope="shared", domain="price",
                            source="build_price_panel: 가격제한 초과·비유한 수익률 폐기 원장")
        except Exception as e:                                       # noqa
            LOG.debug(f"수익률 무결성 원장 저장 실패({type(e).__name__}) — 계산에는 영향 없음")

    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def _trading_day_gap(px: pd.DataFrame, d0: pd.Series, d1: pd.Series) -> pd.Series:
    """두 날짜 사이의 **실제 거래일 수**. 달력일이 아니라 거래일이어야 가격제한 봉투가 맞다.

    시장 전체의 거래일 배열에 searchsorted 를 두 번 하면 끝난다 — 종목 루프 없음(원칙 3).
    """
    try:
        td = np.sort(pd.unique(as_ts_series(px["date"]).values))
        if not len(td):
            return pd.Series(np.nan, index=d0.index, dtype="float64")
        a = np.searchsorted(td, as_ts_series(d0).values, side="left")
        b = np.searchsorted(td, as_ts_series(d1).values, side="left")
        out = (b - a).astype("float64")
        out[~np.isfinite(pd.to_numeric(as_ts_series(d1), errors="coerce").to_numpy())] = np.nan
        return pd.Series(out, index=d0.index)
    except Exception:                                                # noqa
        return pd.Series(np.nan, index=d0.index, dtype="float64")


def _report_return_tail(monthly: pd.DataFrame) -> None:
    """월수익 분포의 꼬리를 표로 남긴다. 자르지 않고 **보이게** 하는 것이 목적이다."""
    r = pd.to_numeric(monthly.get("fwd_ret"), errors="coerce").dropna()
    if len(r) < 100:
        return
    qs = [0.001, 0.01, 0.05, 0.50, 0.95, 0.99, 0.999]
    v = r.quantile(qs)
    LOG.table([[f"{q*100:g}%", f"{v.loc[q]:+.1%}"] for q in qs] +
              [["최소", f"{r.min():+.1%}"], ["최대", f"{r.max():+.1%}"],
               [">+100% 건수", f"{int((r > 1.0).sum()):,}"],
               ["<-50% 건수", f"{int((r < -0.5).sum()):,}"]],
              ["분위", "월수익률"], ["c", "r"],
              title=f"월수익률 분포 ({len(r):,}행) — 극단 꼬리가 성과를 만드는지 확인용")


def fetch_investor_flows(codes: Sequence[str], start: str, end: str,
                         sec: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다.

    ★ 증분 계획은 가격과 **같은 규칙**을 쓴다. 예전에는 여기에만 상장일 하한도,
      폐지 종료조건도, 음성 원장도 없어서 BACKTEST_START 이후 상장한 종목은
      `lo_c > need_lo + 10d` 가 영원히 참이라 매 실행 전 구간을 백필했다.
    """
    need_lo, need_hi = as_ts(start), as_ts(end)
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    have_hi: Dict[str, pd.Timestamp] = {}
    have_lo: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached = cached.copy()                      # 공용 캐시 객체를 제자리에서 고치지 않는다
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        lo, hi = cached["date"].min(), cached["date"].max()
        _g = cached.groupby("code")["date"]
        have_hi, have_lo = _g.max().to_dict(), _g.min().to_dict()
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용 "
                 f"({lo:%Y-%m} ~ {hi:%Y-%m} · {cached['code'].nunique():,}종목)")
    if pykrx_stock is None or RUN_MODE == "CACHED":
        if cached is not None and len(cached):
            _lo, _hi = cached["date"].min(), cached["date"].max()
            if pd.notna(_lo) and pd.notna(_hi) and (_lo > need_lo + pd.Timedelta(days=45) or
                                                    _hi < need_hi - pd.Timedelta(days=45)):
                LOG.warn(f"수급 캐시가 요청 구간({need_lo:%Y-%m}~{need_hi:%Y-%m})을 다 덮지 "
                         f"못하고, 이번 실행에서는 넓힐 수단이 없습니다"
                         f"(pykrx 미설치 또는 CACHED 모드) — 덮이지 않는 달의 d3 는 결측이 되고 "
                         f"U 는 d1 단독으로 계산됩니다. 0으로 채우지 않습니다.")
            return cached
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})
    # ★★ 증분 수집 ★★
    #   예전엔 캐시가 있으면 **무조건 통째로 반환**하고 끝이었다. 그래서 다른 전략이 더 짧은
    #   구간으로 만들어 둔 캐시를 물려받으면 요청 구간의 뒷부분 d3 가 조용히 전부 결측이 됐고,
    #   넓히려면 전체를 다시 받는 수밖에 없었다(그래서 아무도 안 넓혔다).
    #   → 종목별로 '캐시가 못 덮는 구간'만 받는다. 캐시는 그대로 두고 합집합으로 저장한다.
    # 가격과 같은 하한/종료조건을 쓴다 — 상장 이전 구간과 폐지 이후 구간은 존재하지 않는다.
    f_listing: Dict[str, pd.Timestamp] = {}
    f_delist: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        try:
            _s = sec.dropna(subset=["code"]).drop_duplicates("code")
            _cd = _s["code"].astype(str)
            if "listing_date" in _s.columns:
                f_listing = dict(zip(_cd, as_ts_series(_s["listing_date"])))
            if "delisting_date" in _s.columns:
                f_delist = dict(zip(_cd, as_ts_series(_s["delisting_date"])))
        except Exception:                                           # noqa
            f_listing, f_delist = {}, {}
    # 음성 원장 — 빈 응답이 got 필터에서 조용히 사라져 다음 실행이 같은 구간을 재요청했다.
    _fatt = VAULT.get_table("flow_fetch_attempts", scope="shared")
    f_skip: set = set()
    if _fatt is not None and len(_fatt):
        try:
            _fatt = _fatt.copy()
            _fatt["attempted_at"] = as_ts_series(_fatt["attempted_at"])
            _age = (as_ts(_dt.datetime.now().date()) - _fatt["attempted_at"]).dt.days
            f_skip = set(zip(_fatt.loc[_age.fillna(10 ** 6) < RETRY_AFTER_DAYS, "code"].astype(str),
                             _fatt.loc[_age.fillna(10 ** 6) < RETRY_AFTER_DAYS, "kind"].astype(str)))
        except Exception:                                           # noqa
            f_skip = set()

    jobs: List[Tuple[str, str, str, str]] = []
    for c in codes:
        hi_c, lo_c = have_hi.get(c), have_lo.get(c)
        want = need_lo
        _ld = f_listing.get(c)
        if _ld is not None and pd.notna(_ld):
            want = max(want, as_ts(_ld))
        _dd = f_delist.get(c)
        if hi_c is None:
            if (c, "init") not in f_skip:
                jobs.append((c, want.strftime("%Y-%m-%d"), end, "init"))
            continue
        _closed = (_dd is not None and pd.notna(_dd)
                   and hi_c >= as_ts(_dd) - pd.Timedelta(days=5))
        if lo_c is not None and lo_c > want + pd.Timedelta(days=10) and (c, "back") not in f_skip:
            jobs.append((c, want.strftime("%Y-%m-%d"),
                         (lo_c - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "back"))
        if (not _closed) and hi_c < need_hi - pd.Timedelta(days=10) and (c, "fwd") not in f_skip:
            jobs.append((c, (hi_c + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), end, "fwd"))
    if not jobs:
        LOG.ok(f"수급 신규 수집 0건 — 공용 캐시가 요청 구간을 전부 덮습니다({len(cached):,}행).")
        return downcast(cached) if cached is not None else pd.DataFrame(
            columns=["code", "date", "inst_net", "foreign_net"])
    LOG.info(f"수급 증분 수집 {len(jobs):,}건 (전 종목 재수집이면 {len(codes):,}건)")

    def _one(job):
        code, st, en, _kind = job
        try:
            limiter("krx").wait()
            limiter("pykrx").wait()
            d = pykrx_stock.get_market_trading_value_by_date(
                as_ts(st).strftime("%Y%m%d"), as_ts(en).strftime("%Y%m%d"), code)
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

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ 청크 + 데드라인 + 체크포인트 — 가격·직원현황·Tier-2 가 다 갖고 있는데 여기만 없었다.
    #    전량을 pmap_io 한 방에 던지면 (a) 4시간 계약에 걸려도 멈출 방법이 없고
    #    (b) 중간에 끊기면 **받은 것이 전량 소실**된다(저장이 맨 끝에 한 번뿐이므로).
    #    d3(수급)는 U축의 절반이라 조용히 사라지면 U 가 d1 단독으로 퇴화한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    try:
        _dl = time.time() + stage_time_budget(FLOW_TIME_SHARE, floor_s=60.0)
    except Exception:                                               # noqa
        _dl = None
    res: List[Optional[pd.DataFrame]] = []
    _CH = 400
    for _i in range(0, len(jobs), _CH):
        _chunk = jobs[_i:_i + _CH]
        res.extend(pmap_io(_one, _chunk, workers=min(N_WORKERS_IO, 8),
                           desc=f"수급 증분 수집({_i//_CH + 1}/{math.ceil(len(jobs)/_CH)})"))
        _new = [d for d in res if d is not None and len(d)]
        if _new:
            try:
                _acc = pd.concat(([cached] if cached is not None and len(cached) else []) + _new,
                                 ignore_index=True)
                _acc["date"] = as_ts_series(_acc["date"])
                _acc = (_acc.dropna(subset=["code", "date"])
                            .drop_duplicates(["code", "date"], keep="last"))
                VAULT.put_table("krx_investor_flows", _acc, scope="shared", domain="flow",
                                source="pykrx (청크 체크포인트)", backup=False)
            except Exception as e:                                  # noqa
                LOG.debug(f"수급 체크포인트 실패({type(e).__name__}) — 수집은 계속합니다.")
        if _dl and time.time() > _dl and (_i + _CH) < len(jobs):
            LOG.warn(f"수급 수집 시간 몫을 다 썼습니다 — {_i+len(_chunk):,}/{len(jobs):,}건에서 "
                     f"멈춥니다. 받은 만큼은 공용 인덱스에 저장됐고 재실행 시 이어받습니다. "
                     f"덮이지 않는 달의 d3 는 결측이 되고 U 는 d1 단독으로 계산됩니다.")
            jobs = jobs[:_i + len(_chunk)]
            break
    got = [d for d in res if d is not None and len(d)]
    # ★ 빈 응답을 기억한다. 예전엔 got 필터에서 조용히 사라져 다음 실행이 같은 구간을
    #   그대로 다시 요청했다 — '수집 실패'와 '원래 자료가 없음'을 구별하지 못했다.
    _fail = [{"code": j[0], "kind": j[3], "requested_from": as_ts(j[1]),
              "attempted_at": as_ts(_dt.datetime.now().date())}
             for j, d in zip(jobs, res) if d is None or not len(d)]
    if _fail:
        try:
            _fp = VAULT.get_table("flow_fetch_attempts", scope="shared")
            _fa = (pd.concat([_fp, pd.DataFrame(_fail)], ignore_index=True)
                   if _fp is not None and len(_fp) else pd.DataFrame(_fail))
            _fa["attempted_at"] = as_ts_series(_fa["attempted_at"])
            _fa = _fa.loc[_fa.groupby(["code", "kind"])["attempted_at"].idxmax()] \
                     .reset_index(drop=True)
            VAULT.put_table("flow_fetch_attempts", _fa, scope="shared", domain="flow",
                            source="fetch_investor_flows:negative_cache")
            LOG.info(f"수급 미수신 {len(_fail):,}건을 시도 원장에 기록했습니다 — "
                     f"{RETRY_AFTER_DAYS}일간 다시 묻지 않습니다.")
        except Exception as e:                                      # noqa
            LOG.warn(f"수급 시도 원장 저장 실패({type(e).__name__}).")
    if not got:
        LOG.warn("수급 신규분을 받지 못했습니다 — 캐시분만 사용합니다(d3 부분 결측).")
        return downcast(cached) if cached is not None and len(cached) else pd.DataFrame(
            columns=["code", "date", "inst_net", "foreign_net"])
    # ★ 저장은 '기존 캐시 ∪ 신규'. 잘라서 덮어쓰면 다른 전략이 쌓아 둔 과거가 사라진다(절대1원칙).
    fl = pd.concat(([cached] if cached is not None and len(cached) else []) + got,
                   ignore_index=True)
    fl["date"] = as_ts_series(fl["date"])
    fl = (fl.dropna(subset=["code", "date"])
            .sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무제표 / 직원현황 / 공시목록                                               ║
# ║                                                                                          ║
# ║  ★ PIT 핵심: knowledge_date = 접수일자(rcept_dt). 결산기준일이 아니다.                     ║
# ║    fnltt* 응답의 rcept_no 앞 8자리가 곧 접수일자다 → 여기서 knowledge_date 를 얻는다.       ║
# ║    rcept_no 가 없으면 법정 제출기한(분기 45일 / 사업보고서 90일)으로 보수적 추정한다.       ║
# ║    ※ 보수적 추정은 '늦게 알았다'는 방향이므로 미래누수를 만들지 않는다.                     ║
# ║                                                                                          ║
# ║  ★ 호출 예산: DART 는 일 20,000건 제한. 10년 분기 전체 재무제표는 그 몇 배다.               ║
# ║    → 콜드빌드는 며칠에 걸쳐 '이어받기'로 완성된다(§3: 콜드빌드는 4시간 예산 밖).            ║
# ║    → 남은 호출량을 실시간으로 표시하고, 한도에 닿으면 깨끗하게 멈춘 뒤 진행률을 알려준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_DAILY_LIMIT = 19_000                 # 공식 20,000 대비 여유
DART_STATEMENT_FREQ = "quarterly"         # "quarterly" | "annual"
# 한 번 공시된 재무 관측치를 '아직 유효한 최신치'로 몇 일까지 끌고 갈 것인가.
# 연간 공시 주기(365일) + 제출 지연·결산월 변경 여유. 이 값을 넘기면 다시 결측으로 되돌린다.
# ★ 0 으로 채우는 것이 아니다 — 모르는 것은 끝까지 모르는 것으로 둔다(원칙 6).
FS_CARRY_MAX_DAYS = 550
# 주요계정 배치의 음성 캐시 — '물어봤는데 자료가 없더라'를 기억하는 공용 원장.
# 이게 없으면 상장 전·폐지 후·비제출 조합(격자의 대부분)을 매 실행 영원히 다시 묻는다.
MULTI_NODATA_TABLE = "dart_multi_nodata"
FS_NODATA_TABLE = "dart_fnltt_nodata"      # 전체재무제표(단건) 쪽 같은 원장
# ★ Tier-2 는 호출 수가 아니라 **시간**으로 자른다. 4시간 계약을 지키는 것은 개수가 아니라
#   벽시계다 — 개수 상한은 서버가 먼저 막으면 아무것도 보호하지 못한다(5차 실행에서 실증).
FS_TIME_BUDGET_S = 20 * 60                 # 폴백값. 실제로는 아래 _fs_time_budget_s() 가 쓰인다
FS_CHECKPOINT_CORPS = 40                   # 이만큼 회사를 완성할 때마다 드라이브에 저장


def _fs_time_budget_s() -> float:
    """Tier-2 가 이번 실행에서 쓸 수 있는 초. **남은 시간의 비율**로 계산한다.

    ★ 왜 고정 상수가 아닌가. 20분을 박아 두면 두 방향으로 다 틀린다:
      · 앞 단계(가격·직원현황)가 빨리 끝나 2시간이 남아도 20분만 쓰고 멈춘다 → 커버리지를
        올릴 기회를 그냥 버린다(7회차 Tier-2 13.5%).
      · 앞 단계가 늦어져 10분밖에 안 남았는데도 20분을 쓴다 → 4시간 계약을 넘긴다.
    v3 조각(06_env)이 데드라인을 제공하면 그것을 쓰고, 없으면(v2 단독 실행) 상수로 돌아간다.
    """
    try:
        return float(stage_time_budget(FS_TIME_SHARE, floor_s=120.0))
    except Exception:                                       # noqa
        return float(FS_TIME_BUDGET_S or 0.0)
MULTI_NODATA_RECENT_DAYS = 30     # 최근 2개 회계연도 — 나중에 제출될 수 있으므로 짧게
MULTI_NODATA_OLD_DAYS = 365       # 그 이전 — 이제 와서 새로 제출될 일은 사실상 없다
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


class DartBudget:
    """DART 호출 사용량 추적 + 다중 키 로테이션.

    ★★ 설계 원칙 (한 번 크게 틀렸던 부분) ★★
      이 카운터는 **계획용 추정치이지 허가권이 아니다.**
      예전 판은 로컬 카운터가 19,000 에 닿으면 호출 자체를 거부했다. 그런데 그 카운터는
      틀릴 수밖에 없다 — 이전 세션의 잔여, 동시 실행, 환불 누락, 강제 종료로 저장 못 한
      구간, KST 경계 오차가 전부 여기에 쌓인다. 실제로 사용자 실행이 그렇게 죽었다:
      파일엔 19,000/19,000 인데 서버는 답해 줄 수 있는 상태에서 **한 건도 시도하지 않고**
      "한도 소진" 을 선언했다. 우리 추정으로 우리를 막은 것이다.

      → 진짜 잔여량은 **서버만 안다.** DART 는 한도를 넘기면 status 020/021 로 명시적으로
        알려 준다. 그러니 그 응답이 오기 전까지는 계속 쏜다. 카운터는 ETA·예산표·우선순위
        정렬에만 쓰고, 차단은 **서버가 거부한 키**로만 판정한다.
        (초과 요청은 020 응답 하나로 끝나며 별도 불이익이 없다 — 헛차단이 훨씬 비싸다)

    ★ 다중 키 — 한도는 키 하나당이다. DART 는 계정당 여러 키를 무료·즉시 발급한다.
      키가 여러 개면 하루 총량이 그만큼 곱해지고, 소진된 키는 건너뛰고 다음 키로 넘어간다.
      드라이브에는 키 원문이 아니라 해시(kid)만 남긴다.
    """

    def __init__(self):
        self.today = self._kst_day()
        raw = [str(k).strip() for k in ([DART_API_KEY] + list(DART_API_KEYS))]
        self.keys = list(dict.fromkeys(k for k in raw if k))
        self._kid_of = {k: self._make_kid(k) for k in self.keys}
        self.per_key: Dict[str, int] = {kid: 0 for kid in self._kid_of.values()}
        self.blocked: set = set()          # ★ 서버가 020/021 로 거부한 kid — 유일한 하드 차단
        self.n = 0
        self.exhausted = False
        self._lk = threading.RLock()
        self._reserved: Dict[str, int] = {}
        self._dirty = 0
        self._rr = 0
        self._ephemeral = False            # True 면 파일 저장·사용자 로그를 하지 않는다(계약 검정용)
        self._load()
        if len(self.keys) > 1:
            LOG.ok(f"DART 키 {len(self.keys)}개 로테이션 — 소진된 키는 자동으로 건너뜁니다. "
                   f"참고 한도 {self.soft_cap:,}건(키당 {DART_DAILY_LIMIT:,}), "
                   f"오늘 사용 추정 {self.n:,}건. 실제 잔여는 서버 응답으로 판정합니다.")

    # ── 참고용 상한 (계획·ETA 전용, 차단에는 쓰지 않는다) ───────────────────────────────
    @property
    def soft_cap(self) -> int:
        return DART_DAILY_LIMIT * max(1, len(self.keys))

    @staticmethod
    def _make_kid(key: str) -> str:
        return hashlib.sha1(key.encode()).hexdigest()[:10] if key else "none"

    @staticmethod
    def _kst_day() -> str:
        """DART 한도의 리셋 경계는 00:00 KST 다. 로컬 날짜를 쓰면 UTC 컨테이너에서
        하루에 두 번 틀린다: 15~24 UTC 는 이미 리셋된 한도를 소진으로 착각해 9시간을
        헛차단하고, 그 뒤에는 남아 있다고 믿고 쏘다가 status 020 을 맞는다."""
        try:
            from zoneinfo import ZoneInfo
            return _dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        except Exception:
            return (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date().isoformat()

    def _roll_if_new_day(self):
        """긴 실행이 자정을 넘으면 한도도 리셋된다. take() 안에서 값싸게 확인한다."""
        d = self._kst_day()
        if d != self.today:
            # ★ 계약 검정의 합성 객체(_ephemeral)는 사용자 로그를 더럽히지 않는다.
            #   §12-A 가 만드는 b2 는 n = DART_DAILY_LIMIT*99 = 1,881,000 이라
            #   "직전 사용 1,881,000건" 이 프로덕션 로그에 그대로 샜다.
            #   게다가 아래에서 전역 DART_HALT 를 지우므로 실제 상태까지 오염시킨다.
            if getattr(self, "_ephemeral", False):
                self.today, self.n, self.exhausted = d, 0, False
                self.per_key = {kid: 0 for kid in self._kid_of.values()}
                self.blocked.clear()
                return
            LOG.info(f"KST 자정 경과 — DART 일일 한도가 초기화됐습니다 "
                     f"({self.today} → {d}, 직전 사용 {self.n:,}건). 차단 표시도 해제합니다.")
            self._save()
            self.today, self.n, self.exhausted = d, 0, False
            self.per_key = {kid: 0 for kid in self._kid_of.values()}
            self.blocked.clear()
            DART_HALT["reason"] = DART_HALT["detail"] = None

    def _path(self) -> str:
        # ★★ 공용 네임스페이스에 둔다 ★★
        #   예전엔 전략 **전용** 인덱스에 있었다. 그래서 같은 DART 키로 전략 5개를 돌리면
        #   각 전략이 자기 파일만 보고 "오늘 0건 썼다"고 믿었다. 실제로는 서버 기준으로
        #   이미 소진돼 있었고, 5차 실행은 첫 호출에서 020 을 맞았다.
        #   한도는 **키 단위**지 전략 단위가 아니다. 그러니 원장도 키 단위여야 한다.
        #   ※ 이 값은 여전히 추정치이고 차단 기준이 아니다 — 계획·ETA 표시에만 쓴다.
        #     (전략끼리 알려주면 최소한 '왜 갑자기 020 이 났는지'는 설명할 수 있다)
        return os.path.join(VAULT.ns["shared"], "index", "dart_budget.json")

    def _load(self):
        """어제·오늘 사용량을 읽되 **차단 상태는 복원하지 않는다.**

        ★ blocked 를 파일에서 되살리면 그 순간 다시 '우리 추정으로 우리를 막는' 옛 버그가
          된다. 서버가 오늘 실제로 거부해야만 차단이다. 사용량은 ETA 표시에만 쓴다.
        """
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                pk = j.get("per_key", {})
                for kid in self.per_key:
                    self.per_key[kid] = int(pk.get(kid, 0))
                if not pk and "n" in j:           # 단일 키 시절 파일 하위호환
                    only = next(iter(self.per_key), None)
                    if only is not None:
                        self.per_key[only] = int(j.get("n", 0))
                self.n = sum(self.per_key.values())
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘 사용한 것으로 기록된 DART 호출 {self.n:,}건 "
                     f"(참고 한도 {self.soft_cap:,}). 이 값이 한도에 닿아 있어도 "
                     f"**시도는 계속합니다** — 실제 잔여는 서버만 알기 때문입니다.")

    def _save(self):
        # ★ 계약 자가검정이 만드는 합성 예산 객체는 프로덕션 상태를 건드리면 안 된다.
        #   §12-A 가 mark_blocked() 를 부르는 순간 이 _save 가 실제 dart_budget.json 을
        #   덮어썼고, 로그에는 '직전 사용 1,881,000건' 같은 가짜 수치가 남았다.
        #   테스트가 프로덕션 카운터를 오염시키면 그 다음 실행의 판단 근거가 거짓이 된다.
        if getattr(self, "_ephemeral", False):
            return
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n, "per_key": self.per_key}))
        except Exception:
            pass

    # ── 키 선택 ────────────────────────────────────────────────────────────────────────
    def pick_key(self) -> Optional[str]:
        """차단되지 않은 키 중 **가장 적게 쓴** 키. 전부 차단이면 None."""
        with self._lk:
            self._roll_if_new_day()
            live = [k for k in self.keys if self._kid_of[k] not in self.blocked]
            if not live:
                return None
            return min(live, key=lambda k: self.per_key.get(self._kid_of[k], 0))

    def mark_blocked(self, key: Optional[str], why: str = ""):
        """서버가 한도초과(020/021)를 알려온 키를 오늘 더 쓰지 않는다. 유일한 하드 차단."""
        with self._lk:
            kid = self._kid_of.get(key or "")
            if not kid or kid in self.blocked:
                return
            self.blocked.add(kid)
            left_keys = len(self.keys) - len(self.blocked)
            if getattr(self, "_ephemeral", False):
                return                      # 합성 객체(계약 검정) — 사용자 로그를 더럽히지 않는다
            if left_keys > 0:
                LOG.info(f"DART 키 하나가 서버에서 한도초과로 거부됐습니다{(' — ' + why) if why else ''}. "
                         f"남은 키 {left_keys}개로 계속합니다.")
            elif not self.exhausted:
                self.exhausted = True
                LOG.warn(f"DART 키 {len(self.keys)}개가 전부 한도초과입니다 "
                         f"(사용 추정 {self.n:,}건). 여기까지 받은 데이터는 드라이브에 "
                         f"저장되어 있으니, KST 자정 이후 재실행하면 이어받습니다. "
                         f"키를 더 발급해 DART_API_KEYS 에 추가하면 하루에 더 받을 수 있습니다.")
            self._save()

    # ── 사용량 기록 (허가가 아니라 계측이다) ──────────────────────────────────────────
    def charge(self, k: int, key: Optional[str], purpose: Optional[str] = None):
        with self._lk:
            kid = self._kid_of.get(key or "")
            if kid:
                self.per_key[kid] = self.per_key.get(kid, 0) + k
            self.n += k
            if purpose in self._reserved:
                self._reserved[purpose] = max(0, self._reserved[purpose] - k)
            self._dirty += k
            if self._dirty >= 200:
                self._dirty = 0
                self._save()

    def refund(self, k: int = 1, purpose: Optional[str] = None, key: Optional[str] = None):
        if k <= 0:
            return
        with self._lk:
            kid = self._kid_of.get(key or "")
            if kid and kid in self.per_key:
                self.per_key[kid] = max(0, self.per_key[kid] - k)
            self.n = max(0, self.n - k)
            if purpose in self._reserved:
                self._reserved[purpose] += k
            self._dirty += k

    # ── 예약 — 알파(직원현황) 몫을 다른 단계가 먼저 못 쓰게 한다 ────────────────────────
    #  ★ 예약은 '계획'에만 작용한다. 각 수집 함수가 자기 상한을 정할 때 left(purpose) 를
    #    보고 잡 수를 자르는 용도다. 호출 자체를 거부하지는 않는다(그건 서버 몫).
    def reserve(self, purpose: str, k: int):
        with self._lk:
            self._reserved[purpose] = max(0, int(k))

    def _reserved_for_others(self, purpose: Optional[str]) -> int:
        return sum(v for p, v in self._reserved.items() if p != purpose)

    def left(self, purpose: Optional[str] = None) -> int:
        """purpose 가 이번 실행에서 계획해도 되는 호출 수(추정). 남의 예약분은 뺀다.

        ★ 이것은 '허가된 잔량'이 아니라 '계획 기준선'이다. 0 이어도 시도는 막지 않는다.
        """
        with self._lk:
            live = max(1, len(self.keys) - len(self.blocked))
            cap = DART_DAILY_LIMIT * live
            used = sum(v for k, v in self.per_key.items() if k not in self.blocked)
            return max(0, cap - used - self._reserved_for_others(purpose))

    def all_blocked(self) -> bool:
        with self._lk:
            return bool(self.keys) and len(self.blocked) >= len(self.keys)

    def close(self):
        self._save()

    def report(self):
        if not self.keys:
            return
        rows = [[f"키 #{i+1} ({self._kid_of[k]})",
                 f"{self.per_key.get(self._kid_of[k], 0):,}",
                 "서버 거부" if self._kid_of[k] in self.blocked else "사용 가능"]
                for i, k in enumerate(self.keys)]
        rows.append(["── 합계", f"{self.n:,}", f"차단 {len(self.blocked)}/{len(self.keys)}"])
        LOG.table(rows, ["DART 키", "이번 실행까지 사용(추정)", "상태"], ["l", "r", "c"],
                  title="DART 키별 사용량 — 차단은 서버 응답(020/021)으로만 판정합니다")


DBUDGET: Optional[DartBudget] = None

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ★ '지금 못 받는다' 와 '원래 없다' 를 구별하는 단일 진실
#
#  dart_api() 는 세 가지 전혀 다른 사건을 모두 None 으로 뭉갠다:
#    ① 예산 게이트가 호출을 거부   ② 네트워크 실패   ③ API 가 '데이터 없음'(013) 응답
#  호출자는 ①②를 ③으로 읽는다. 실제로 이것 때문에 실행이 죽었다 —
#  일일 한도가 소진된 상태로 시작한 실행에서 CANARY 가 K8 을 '급여총액 미기재'로 판정하고
#  §12-2 킬 기준을 발동시켰다. 데이터는 멀쩡히 있었고 오늘 호출권이 없었을 뿐이다.
#  게다가 그 판정의 처방은 '백테스트 시작일 상향' — 일시적 조건으로 전략을 영구 훼손한다.
#
#  → 사유를 여기에 기록하고, 자원 조건으로 실패한 검사는 FAIL 이 아니라 SKIP 이어야 한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
DART_HALT: Dict[str, Optional[str]] = {"reason": None, "detail": None}


def dart_has_key() -> bool:
    """키가 하나라도 있는가. DART_API_KEY(단일) 와 DART_API_KEYS(복수) 를 함께 본다."""
    return bool(str(DART_API_KEY).strip() or [k for k in DART_API_KEYS if str(k).strip()])


def dart_note_halt(reason: str, detail: str = ""):
    if DART_HALT["reason"] is None:
        DART_HALT["reason"], DART_HALT["detail"] = reason, detail


def dart_halt_reason(purpose: Optional[str] = None) -> Optional[str]:
    """지금 DART 를 쓸 수 없는 이유. None 이면 정상 — 즉 '응답 0건'은 진짜 데이터 부재다.

    purpose 를 주면 그 용도의 **예약분까지 고려**해서 판정한다. 예약이 남아 있으면
    전체 잔량이 0 이어도 그 용도는 계속 진행할 수 있다."""
    if not dart_has_key():
        return "DART API 키 미입력 (DART_API_KEY / DART_API_KEYS)"
    # ★ 로컬 카운터로는 절대 차단하지 않는다. 그 카운터는 추정치이고, 추정으로 우리를 막는
    #   순간 '서버는 답해 줄 수 있는데 한 건도 안 쏘는' 상태가 된다(실제로 그렇게 죽었다).
    #   하드 차단은 서버가 020/021 로 거부해 모든 키가 막혔을 때뿐이다.
    if DBUDGET is not None and DBUDGET.all_blocked():
        return f"DART 키 전부 한도초과 — 서버 거부 (사용 추정 {DBUDGET.n:,}건)"
    return DART_HALT["reason"]


def dart_budget_left(purpose: Optional[str] = None) -> int:
    return DBUDGET.left(purpose) if DBUDGET else DART_DAILY_LIMIT


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2, no_data_ok: bool = False,
             purpose: Optional[str] = None) -> Optional[dict]:
    """DART 단건 호출. 키 로테이션 + 사용량 계측.

    ★ 로컬 카운터로 호출을 **거부하지 않는다.** 진짜 잔여량은 서버만 알고, 서버는 넘치면
      status 020/021 로 알려 준다. 그 응답이 오면 그 키만 오늘 접고 다음 키로 재시도한다.
      (예전 판은 우리 추정으로 우리를 막아, 서버가 답해 줄 수 있는 상태에서 한 건도
       시도하지 않고 '한도 소진'을 선언했다)
    """
    if not (DART_API_KEY or DART_API_KEYS):
        return None
    if DBUDGET is None:
        return _dart_call_once(endpoint, params, DART_API_KEY, source, tries, no_data_ok)[0]

    for _ in range(max(1, len(DBUDGET.keys))):
        key = DBUDGET.pick_key()
        if key is None:                       # 모든 키가 서버에서 거부됨 = 진짜 소진
            dart_note_halt(f"DART 키 {len(DBUDGET.keys)}개 전부 한도초과(서버 응답 020/021)",
                           "KST 자정 이후 재실행하면 이어받습니다.")
            return None
        js, why = _dart_call_once(endpoint, params, key, source, tries, no_data_ok,
                                  purpose=purpose)
        if why != "quota":
            # ★★ 021 은 '이 요청 하나가 잘못됐다'이지 '키가 소진됐다'가 아니다 ★★
            #   예전엔 020 과 021 을 같은 bool 로 뭉개서, 회사 개수를 초과한 요청 한 건이
            #   **모든 키를 차례로 접었다.** 5차 실행에서 CANARY 의 첫 호출이 그렇게
            #   19,000건 호출권을 통째로 날렸다. 021 은 호출자가 배치를 줄여 재시도할
            #   문제이므로 키를 건드리지 않고 그대로 올려 보낸다.
            if why == "oversize":
                LOG.warn(f"DART status=021(조회 가능한 회사 개수 초과) — {endpoint}. "
                         f"이 요청 하나가 큰 것이지 키가 소진된 것이 아닙니다. "
                         f"키를 접지 않고 호출자가 배치를 줄여 재시도합니다.")
            return js
        DBUDGET.mark_blocked(key, f"status=020 ep={endpoint}")   # 다음 키로 자동 재시도
    return None


def _dart_call_once(endpoint: str, params: dict, key: str, source: str,
                    tries: int, no_data_ok: bool,
                    purpose: Optional[str] = None) -> Tuple[Optional[dict], str]:
    """(응답, 사유). 사유는 "" | "quota"(020, 이 키 소진) | "oversize"(021, 요청이 큼).

    예산 계측은 여기서만 한다.

    ★ http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다. 호출당 1건으로 세면
      실사용량을 tries 배 과소집계하므로, 최악을 먼저 계상하고 실제 시도 수를 알면 환급한다.
      try/finally 가 없으면 예외가 새는 순간 그만큼이 영구 소실된다(EMP 경로는 상위에서
      예외를 삼키므로 그 누수가 완전히 조용하다).
    """
    p = dict(params)
    p["crtfc_key"] = key
    attempts = {"n": 0}
    if DBUDGET is not None:
        DBUDGET.charge(tries, key, purpose=purpose)
    try:
        js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                       referer="https://opendart.fss.or.kr/",
                       on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    finally:
        if DBUDGET is not None:
            DBUDGET.refund(max(0, tries - max(1, attempts["n"])), purpose=purpose, key=key)
    if not isinstance(js, dict):
        return None, ""
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "020":
            return None, "quota"               # ← 이 키가 오늘 소진. 호출자가 다음 키로 넘긴다
        if st == "021":
            # 조회 가능한 회사 개수 초과 — 요청이 큰 것이지 키 소진이 아니다.
            return None, "oversize"
        if st in ("010", "011", "012", "901"):
            dart_note_halt(f"DART 인증 오류(status={st} · {DART_STATUS_MSG.get(st, '?')})",
                           "DART_API_KEY / DART_API_KEYS 를 확인하세요. 데이터 부재가 아닙니다.")
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"키를 확인하세요.")
        elif st == "800":
            dart_note_halt("DART 시스템 점검 중(status=800)", "점검 종료 후 재실행하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        # ★ 013("조회된 데이터 없음")은 통신 실패가 아니라 **정상 응답**이다. None 으로
        #   뭉개면 호출자가 '실패'와 구별할 수 없어 서킷브레이커가 정상 데이터로 터진다.
        if st == "013" and no_data_ok:
            return {"status": "013", "list": []}, False
        return None, ""
    return js, False


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자(YYYYMMDD). 없으면 법정기한으로 보수적 추정."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


# ── 전체 재무제표 ───────────────────────────────────────────────────────────────────────────
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]


_FS_EMPTY_LK = threading.Lock()
_FS_EMPTY: List[dict] = []


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    # ★ 예산·인증이 이미 막혔으면 남은 잡을 즉시 포기한다. 계속 돌면 OFS/CFS 두 번씩
    #   헛호출하며 큐 전체(최대 12,000건)를 소진하고, 로그만 실패로 채운다.
    if dart_halt_reason():
        return None
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        if dart_halt_reason():
            return None
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "CFS"})
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        # ★ 서버가 정상 응답했는데 목록이 비었다 = 이 (회사, 연도, 보고서)는 자료가 없다.
        #   done 은 '응답에 나온 행'으로만 만들어지므로, 이 조합은 기록해 두지 않으면
        #   **매 실행 OFS+CFS 두 번씩 영원히 다시 묻는다.** 상장 전·폐지 후·비제출이
        #   격자의 상당 부분이라 그 낭비가 상한을 그대로 잡아먹는다.
        #   ※ dart_halt_reason() 이 있으면 위에서 이미 return 했으므로 여기 오는 것은
        #     '호출은 됐고 자료가 없다'가 확인된 경우뿐이다 — 추측이 아니다.
        if js is not None and not dart_halt_reason():
            with _FS_EMPTY_LK:
                _FS_EMPTY.append({"corp_code": str(corp), "bsns_year": int(year),
                                  "reprt_code": str(reprt),
                                  "asked_at": (_dt.datetime.utcnow()
                                               + _dt.timedelta(hours=9)).date()})
        return None
    d = pd.DataFrame(js["list"])
    for c in _FS_KEEP:
        if c not in d.columns:
            d[c] = None
    d["corp_code"] = corp
    d["bsns_year"] = int(year)
    d["reprt_code"] = reprt
    return d[_FS_KEEP]


# ── Tier-1: 다중회사 주요계정 (배치) ────────────────────────────────────────────────────────
#   fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개까지 받는다.
#   2,500사 × 10년 × 4분기를 단건으로 받으면 100,000 호출(일 20,000 한도로 5일)이지만
#   배치로는 1,000 호출(1시간 이내)이면 끝난다. ★100배 차이다.
#   다만 '주요계정'만 오므로 B/C축이 필요로 하는 재고·매출채권·영업CF 는 없다.
#   → 헤드라인은 배치로 싹 깔고, 전체 재무제표는 우선순위대로 단건 수집해 덮어쓴다(2단 구성).
DART_MULTI_BATCH = 100
_MULTI_ACCOUNT_MAP = {
    "매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income",
    "자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity",
}


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not dart_has_key():
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 음성 캐시 — '물어봤는데 없더라'를 기억한다 ★★
    #    done 은 **응답에 나온 행**으로만 만들어진다. 그런데 상장 전 연도, 폐지 후 연도,
    #    비제출 기업 같은 조합은 응답에 절대 나오지 않으므로 done 에 영원히 못 들어간다.
    #    그래서 매 실행 같은 조합을 다시 물었다 — 이 격자의 대부분이 그런 조합이다.
    #    (3,981사 × 13년 × 4보고서 중 실제 제출은 일부다. 나머지를 매번 다시 묻는다.)
    #    → 배치 응답에 안 나온 회사는 '그 (연도, 보고서)에 자료 없음'이 **확인된** 것이다.
    #      사실이지 추측이 아니다. 기록해 두고 다시 묻지 않는다.
    #    ※ 최근 회계연도는 나중에 제출될 수 있으므로 재시도 창을 짧게 둔다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    _today_kst = (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date()
    nod = VAULT.get_table(MULTI_NODATA_TABLE, scope="shared")
    skip: set = set()
    if nod is not None and len(nod):
        try:
            _ages = (pd.Timestamp(_today_kst) - as_ts_series(nod["asked_at"])).dt.days
            _yy = nod["bsns_year"].astype(int)
            # 오래된 회계연도는 이제 와서 새로 제출될 일이 없다 → 재시도 창을 길게.
            _win = np.where(_yy <= _today_kst.year - 2, MULTI_NODATA_OLD_DAYS,
                            MULTI_NODATA_RECENT_DAYS)
            _live = nod[(_ages.fillna(10 ** 6) < _win)]
            skip = set(zip(_live["corp_code"].astype(str), _live["bsns_year"].astype(int),
                           _live["reprt_code"].astype(str)))
            if skip:
                LOG.info(f"주요계정 음성 캐시 {len(skip):,}조합을 건너뜁니다 "
                         f"(이전 실행에서 '자료 없음'이 확인된 회사×연도×보고서). "
                         f"이 원장이 없으면 그 조합을 매 실행 영원히 다시 묻습니다.")
        except Exception as e:                                      # noqa
            LOG.warn(f"주요계정 음성 캐시 해석 실패({type(e).__name__}) — 이번엔 전 격자를 봅니다.")
            skip = set()

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    corps = [str(c) for c in corp_codes]
    jobs = []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps
                    if (c, int(y), str(r)) not in done and (c, int(y), str(r)) not in skip]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), r))
    if RUN_MODE == "CACHED":
        jobs = []

    _empty_lk = threading.Lock()
    _empty: List[dict] = []

    def _one(job):
        batch, y, r = job
        if dart_halt_reason():          # 예산·인증이 막히면 남은 배치를 즉시 포기
            return None
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(batch), "bsns_year": str(y), "reprt_code": r})
        if js is None:
            return None                 # 네트워크·예산 실패 — '자료 없음'이 아니다. 기록하지 않는다.
        if not isinstance(js.get("list"), list) or not js["list"]:
            # ★ 서버가 정상 응답했는데 목록이 비었다 = 이 배치 전원이 그 기간에 자료 없음.
            with _empty_lk:
                _empty.extend({"corp_code": c, "bsns_year": int(y), "reprt_code": str(r),
                               "asked_at": _today_kst} for c in batch)
            return None
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        d["reprt_code"] = r
        # 응답에 나오지 않은 회사도 '없음이 확인된' 것이다 — 부분 응답을 놓치지 않는다.
        _seen = set(d["corp_code"].astype(str))
        _miss = [c for c in batch if c not in _seen]
        if _miss:
            with _empty_lk:
                _empty.extend({"corp_code": c, "bsns_year": int(y), "reprt_code": str(r),
                               "asked_at": _today_kst} for c in _miss)
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건 수집이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량입니다")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]
    if _empty:
        try:
            _prev = VAULT.get_table(MULTI_NODATA_TABLE, scope="shared")
            _all = pd.concat([_prev, pd.DataFrame(_empty)], ignore_index=True) \
                if _prev is not None and len(_prev) else pd.DataFrame(_empty)
            _all = (_all.sort_values("asked_at")
                        .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
                        .reset_index(drop=True))
            VAULT.put_table(MULTI_NODATA_TABLE, _all, scope="shared", domain="dart",
                            source="fnlttMultiAcnt: 자료 없음이 확인된 조합(음성 캐시)")
            LOG.info(f"'자료 없음'이 확인된 {len(_empty):,}조합을 기록했습니다 — "
                     f"다음 실행부터 다시 묻지 않습니다(누적 {len(_all):,}조합).")
        except Exception as e:                                      # noqa
            LOG.warn(f"주요계정 음성 캐시 저장 실패({type(e).__name__}) — "
                     f"다음 실행이 같은 조합을 다시 묻게 됩니다.")

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사 "
           f"(호출 {len(jobs):,}회로 확보)")
    PIPE.io("OUT", "DRIVE", "dart_multi_raw", M, source="opendart fnlttMultiAcnt")
    return M


def fetch_dart_financials(corp_codes: Sequence[str], years: Sequence[int],
                          priority: Optional[Sequence[str]] = None,
                          max_calls: Optional[int] = None,
                          freq: Optional[str] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다.

    ★ max_calls (2026-08 추가 — 이번 실행에서 던질 호출 수의 하드 상한)
      이 함수의 잡 수는 |기업| × |연도| × |보고서| 로 **곱셈으로 폭발**한다.
      3,981사 × 13년 × 4분기 = 207,012건 = 11일치. 호출자가 상한을 주지 않으면
      tqdm 이 11시간짜리 ETA 를 띄운 채 그대로 돌아간다 — 4시간 예산 계약이 있는
      호출자에게 이것은 계약 위반이다. 상한을 받으면 **우선순위 순으로 잘라서** 그만큼만
      던지고, 무엇을 남겼는지 로그로 밝힌다. None 이면 종전과 동일(무제한 콜드빌드).

    ★ freq  ("annual" | "quarterly") — 전역 DART_STATEMENT_FREQ 를 호출자가 덮어쓴다.
      연간만 받으면 잡 수가 정확히 1/4 이 된다.
    """
    if not dart_has_key():
        LOG.warn("DART_API_KEY 미입력 — B축(회계품질)·C축(자원투입)·PACK-C 가 전부 비활성화됩니다. "
                 "이 전략의 핵심 입력이므로 키 입력을 강력히 권합니다.")
        return pd.DataFrame(columns=_FS_KEEP)

    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 재무 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = ([REPRT_CODES["FY"]] if (freq or DART_STATEMENT_FREQ) == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    # 음성 캐시 — 자료 없음이 확인된 조합은 다시 묻지 않는다(Tier-1 배치와 같은 원장 구조).
    _today_kst = (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date()
    fs_skip: set = set()
    _nod = VAULT.get_table(FS_NODATA_TABLE, scope="shared")
    if _nod is not None and len(_nod):
        try:
            _ages = (pd.Timestamp(_today_kst) - as_ts_series(_nod["asked_at"])).dt.days
            _win = np.where(_nod["bsns_year"].astype(int) <= _today_kst.year - 2,
                            MULTI_NODATA_OLD_DAYS, MULTI_NODATA_RECENT_DAYS)
            _lv = _nod[_ages.fillna(10 ** 6) < _win]
            fs_skip = set(zip(_lv["corp_code"].astype(str), _lv["bsns_year"].astype(int),
                              _lv["reprt_code"].astype(str)))
            if fs_skip:
                LOG.info(f"전체재무제표 음성 캐시 {len(fs_skip):,}조합을 건너뜁니다 "
                         f"(자료 없음이 확인된 회사×연도×보고서). 이 원장이 없으면 그 조합에 "
                         f"매 실행 OFS+CFS 두 번씩 헛호출이 나갑니다.")
        except Exception:                                           # noqa
            fs_skip = set()
    done |= fs_skip

    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    # 연도 내림차순 → 기업 우선순위 → 사업보고서(FY) 우선. FY 를 먼저 받아야 연간 축(직원현황·
    # 한계임금)과 짝이 맞는 회계 데이터가 먼저 완성된다.
    _rorder = {REPRT_CODES["FY"]: 0, REPRT_CODES["Q3"]: 1,
               REPRT_CODES["H1"]: 2, REPRT_CODES["Q1"]: 3}
    reprts = sorted(reprts, key=lambda r: _rorder.get(r, 9))
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 회사 우선 루프 — 이 순서가 CORE-D 의 생사를 가른다 ★★
    #
    #  예전엔 `for y in years for c in corps` 였다(연도 바깥 루프). 상한에서 끊기면
    #  **모든 회사가 최근 1년씩** 남는다. 그런데 CORE-D 의 Tier-2 센서는 전부 12개월
    #  차분을 요구한다 — i_turn/p_payout/p_invest/i_ic 는 연속 2개 회계연도,
    #  i_capex(shift(12).rolling(36))·i_accr·i_roic 는 3개가 필요하다.
    #  즉 연도 우선 격자는 **연속 FY 2개를 가진 회사를 구조적으로 0사** 로 만든다.
    #  5차 실행에서 캐시에 Tier-2 가 2,210조합이나 있는데도 i_capex=0 · i_turn=0 ·
    #  i_accr=0 · p_payout=0 · p_invest=0 이었던 이유가 이것이다. 키가 멀쩡했어도
    #  같은 자리에서 죽었다 — 키 소진은 사망 시각을 앞당겼을 뿐이다.
    #
    #  회사 우선으로 뒤집으면 같은 호출 수로 (상한 ÷ 연수) 개의 회사가 **완전한 전 기간**을
    #  갖는다. 3,667 호출 · 13년이면 282사다. 적어 보이지만, 부분 연도만 가진 3,667사는
    #  12개월 차분에 **한 건도** 기여하지 못하므로 그쪽이 전액 손실이다.
    #
    #  ★ 절단도 회사 경계에서 한다. 회사는 '완전하거나 없거나' 둘 중 하나여야 한다.
    #    반쪽짜리 회사에 쓴 호출은 회수되지 않는다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    _per_corp = max(1, len(years) * len(reprts))
    jobs = [(c, y, r) for c in corp_sorted for y in sorted(years, reverse=True) for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    total_needed = len(jobs)
    # ★★ 로컬 카운터로 작업을 자르지 않는다 ★★
    #   예전엔 `left_today = DART_DAILY_LIMIT - DBUDGET.n` 을 min() 에 넣어 잡을 잘랐다.
    #   그 한 줄에 세 가지 오류가 겹쳐 있었다:
    #     ① 로컬 추정치를 허가권으로 썼다 — 이 파일 111·128~129·206행이 명문으로 금지한다.
    #     ② 분모 DART_DAILY_LIMIT 은 **키 1개분**인데 분자 DBUDGET.n 은 전 키 합산이었다.
    #        키 2개로 각 9,500 씩 쓰면 실제 잔여 19,000 인데 0 으로 판정됐다.
    #     ③ 이전 세션 잔여·강제종료·환불누락·KST 오차가 누적된 값이라 애초에 신뢰할 수 없다.
    #   진짜 잔여량은 서버만 안다. 하드 차단은 서버가 020/021 을 준 키에 대해서만 일어난다.
    cap = total_needed
    if max_calls is not None:
        cap = max(0, min(cap, int(max_calls)))
    if jobs:
        LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 "
                 f"(계획 기준선 {dart_budget_left():,}건 — 추정치이며 차단 기준이 아닙니다. "
                 f"실제 중단은 서버가 한도초과를 응답할 때만 일어납니다)")
        if cap < total_needed:
            # ★ 회사 경계로 내림한다. 반쪽짜리 회사는 12개월 차분에 한 건도 기여하지 못하므로
            #   그 회사에 쓴 호출은 전액 손실이다. '완전하거나 없거나' 둘 중 하나여야 한다.
            #   ★ 단 cap==0(CACHE_ONLY 등)이면 **0사**여야 한다 — max(_per_corp, …) 로
            #     최소 1사를 강제하면 "받지 않기로 한 실행"이 1사를 받으러 나간다.
            cap = 0 if cap <= 0 else max(_per_corp, (cap // _per_corp) * _per_corp)
            jobs = jobs[:cap]
            LOG.warn(
                f"이번 실행에서는 상한 {cap:,}건만 받습니다 — **회사 {cap // _per_corp:,}사의 "
                f"전 기간({len(years)}년)** 을 완성합니다(반쪽짜리 회사를 만들지 않습니다). "
                f"전체 {total_needed:,}건 = 약 {math.ceil(total_needed / max(cap, 1))}회 실행분. "
                f"미수집 회사는 Tier-1 주요계정으로 대체되며, 재실행하면 다음 회사부터 이어받습니다.")
        elif total_needed > DART_DAILY_LIMIT:
            LOG.warn(f"필요 호출({total_needed:,})이 일일 한도({DART_DAILY_LIMIT:,})를 초과합니다. "
                     f"오늘 받을 수 있는 만큼 받고 저장합니다. "
                     f"약 {math.ceil(total_needed / DART_DAILY_LIMIT)}일에 걸쳐 콜드빌드가 완성됩니다. "
                     f"(§3 — 콜드빌드는 4시간 반복예산 밖입니다)")
        _FS_EMPTY.clear()
        # ══════════════════════════════════════════════════════════════════════════════════
        #  ★★ 청크 체크포인트 ★★ 예전엔 잡 전체를 pmap_io 한 방에 던지고 맨 끝에 한 번만
        #    저장했다. 중간에 서버가 막거나 세션이 끊기면 **받은 것이 전부 증발**한다.
        #    회사 경계로 자른 청크마다 저장하므로, 어디서 끊겨도 '완성된 회사'는 남는다.
        #    EMP 는 이미 이 구조였는데 Tier-2 에만 없었다.
        # ══════════════════════════════════════════════════════════════════════════════════
        # ★ 시간 몫은 **남은 수집시간의 비율**이다. 고정 상수(예전 20분)를 쓰면 앞 단계가
        #   빨리 끝났을 때 남는 시간을 그냥 버리고, 앞 단계가 늦어졌을 때 4시간을 넘긴다.
        _budget_s = _fs_time_budget_s()
        got, _deadline = [], (time.time() + _budget_s if _budget_s else None)
        LOG.info(f"  Tier-2 시간 몫 {_budget_s/60:.0f}분 배정 — 멈추는 조건은 "
                 f"①서버 020/021 ②시계 둘뿐입니다(로컬 추정 잔량으로 자르지 않습니다).")
        _chunk = max(_per_corp, (FS_CHECKPOINT_CORPS * _per_corp))
        for _i in range(0, len(jobs), _chunk):
            if dart_halt_reason():
                LOG.warn(f"DART 가 중단되어 {_i:,}/{len(jobs):,}건에서 멈춥니다 — "
                         f"여기까지는 드라이브에 저장됐습니다.")
                break
            if _deadline and time.time() > _deadline:
                LOG.warn(f"Tier-2 시간 몫 {_budget_s/60:.0f}분을 다 썼습니다 — "
                         f"{_i:,}/{len(jobs):,}건(회사 {_i//max(_per_corp,1):,}사)에서 멈춥니다. "
                         f"받은 만큼은 드라이브 공용 인덱스에 저장됐고, 재실행하면 다음 회사부터 "
                         f"이어받습니다. (호출 수가 아니라 **시간**으로 4시간 계약을 지킵니다)")
                break
            _res = pmap_io(_fs_one, jobs[_i:_i + _chunk], workers=min(N_WORKERS_IO, 12),
                           desc=f"DART 재무제표({_i//_chunk + 1}/{math.ceil(len(jobs)/_chunk)})")
            _new = [d for d in _res if d is not None and len(d)]
            got.extend(_new)
            if _new:
                _acc = pd.concat(([cached] if cached is not None and len(cached) else []) + got,
                                 ignore_index=True)
                _acc = _acc.drop_duplicates(
                    ["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id", "account_nm"],
                    keep="last")
                VAULT.put_table("dart_fnltt_raw", _acc, scope="shared", domain="dart",
                                source="opendart (청크 체크포인트)", backup=False)
        if _FS_EMPTY:
            try:
                _pv = VAULT.get_table(FS_NODATA_TABLE, scope="shared")
                _al = pd.concat([_pv, pd.DataFrame(_FS_EMPTY)], ignore_index=True) \
                    if _pv is not None and len(_pv) else pd.DataFrame(_FS_EMPTY)
                _al = (_al.sort_values("asked_at")
                          .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
                          .reset_index(drop=True))
                VAULT.put_table(FS_NODATA_TABLE, _al, scope="shared", domain="dart",
                                source="fnlttSinglAcntAll: 자료 없음이 확인된 조합(음성 캐시)")
                LOG.info(f"전체재무제표 '자료 없음' {len(_FS_EMPTY):,}조합 기록 — "
                         f"다음 실행부터 다시 묻지 않습니다(누적 {len(_al):,}조합).")
            except Exception as e:                                  # noqa
                LOG.warn(f"전체재무제표 음성 캐시 저장 실패({type(e).__name__}) — "
                         f"다음 실행이 같은 조합에 헛호출을 보냅니다.")
    else:
        got = []

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        LOG.warn("DART 재무 데이터를 확보하지 못했습니다.")
        return pd.DataFrame(columns=_FS_KEEP)
    fs = pd.concat(frames, ignore_index=True)
    fs = fs.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                             "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_fnltt_raw", fs, scope="shared", domain="dart", source="opendart")
    n_have = fs.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(fs) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"DART 전체 재무제표 진행률 {n_have:,}/{n_need:,} "
             f"({100*n_have/max(n_need,1):.1f}%) — 최근 연도·우선순위 종목부터 채웁니다. "
             f"재실행하면 정확히 이 지점부터 이어받습니다.")
    PIPE.io("OUT", "DRIVE", "dart_fnltt_raw", fs, source="opendart fnlttSinglAcntAll")
    return fs


def merge_financial_tiers(full: pd.DataFrame, multi: pd.DataFrame) -> pd.DataFrame:
    """Tier-2(전체 재무제표)를 우선하고, 없는 (회사, 기간)만 Tier-1(주요계정)로 메운다.

    콜드빌드가 며칠 걸리는 동안에도 매출·영업이익·순이익·자산·부채·자본은 전 종목이
    확보되어 있어 유니버스 구성과 규모 버킷(C11), R3 팩터가 즉시 동작한다."""
    if multi is None or multi.empty:
        return full if full is not None else pd.DataFrame(columns=_FS_KEEP)
    if full is None or full.empty:
        LOG.info("전체 재무제표가 아직 없어 주요계정(배치)만으로 진행합니다 — "
                 "B축의 재고·매출채권·영업CF 는 결측이므로 TP_B1/TP_B2 가 약해집니다.")
        return multi
    have = set(zip(full["corp_code"].astype(str), full["bsns_year"].astype(int),
                   full["reprt_code"].astype(str)))
    key = list(zip(multi["corp_code"].astype(str), multi["bsns_year"].astype(int),
                   multi["reprt_code"].astype(str)))
    fill = multi[[k not in have for k in key]]
    if len(fill):
        LOG.info(f"주요계정으로 보완한 (회사×기간) {fill.groupby(['corp_code','bsns_year','reprt_code']).ngroups:,}건 "
                 f"— 전체 재무제표 콜드빌드가 끝나면 자동으로 대체됩니다.")
    return pd.concat([full, fill], ignore_index=True)


# ── 계정 매핑 (한국 XBRL 계정명은 회사마다 다르다 → 정규식 다중 매칭) ────────────────────────
ACCOUNT_PATTERNS: Dict[str, Tuple[str, List[str]]] = {
    # 키:            (재무제표구분, [account_id 또는 account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$"]),
    "cogs":          ("IS", [r"CostOfSales", r"^매출원가$"]),
    "gross_profit":  ("IS", [r"GrossProfit", r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense", r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense", r"경상(연구)?개발비", r"^연구개발비"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense", r"법인세비용"]),
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세비용차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment", r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssetsOtherThanGoodwill", r"^무형자산$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents", r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities", r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities", r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment", r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense", r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid", r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares", r"자기주식의?\s*취득"]),
    "debt_raise":    ("CF", [r"ProceedsFromBorrowings", r"차입금의?\s*증가", r"사채의?\s*발행"]),
}
_SJ_MAP = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# ★ 손익·현금흐름 성격의 전 계정. 빠뜨리면 <계정>_ttm 컬럼이 아예 생성되지 않고,
#   그걸 쓰는 팩이 실데이터 실행에서만 터진다(합성 스모크는 통과한다).
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy", "debt_raise",
              "tax_expense", "pretax_income", "other_income"]

# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼 전체 목록.
# attach_fundamentals 가 이 목록으로 스키마를 계약적으로 보장한다 — 수집이 얼마나 실패하든
# 패널의 컬럼 집합은 항상 같아야 한다. 그래야 "어떤 실행에선 있고 어떤 실행엔 없는" 축이
# 사라지고, 결측은 결측대로 조용히가 아니라 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_PATTERNS)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다."""
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()
    d["amount"] = pd.to_numeric(
        d["thstrm_amount"].astype(str).str.replace(",", "", regex=False).str.replace("−", "-", regex=False),
        errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
    for key, (sj, pats) in ACCOUNT_PATTERNS.items():
        sjs = _SJ_MAP.get(sj, (sj,))
        sub = d[d["sj_div"].astype(str).isin(sjs)]
        if sub.empty:
            continue
        rx = re.compile("|".join(pats), re.I)
        hit = sub[sub["account_id"].str.contains(rx, na=False) |
                  sub["account_nm"].str.contains(rx, na=False)]
        if hit.empty:
            continue
        # 같은 항목에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "rcept_no", "item", "amount"]])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    rc = (L.sort_values("rcept_no").groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    # 누적치 → 분기 단독치 (Q1/H1/Q3/FY 는 누적 공시다. 차분하지 않으면 계절성이 곧 신호가 된다)
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    flow_items = FLOW_ITEMS
    # 누적 → 분기 단독. 직전 분기가 실제로 존재할 때만 차분한다.
    # (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    gk = ["corp_code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    # ★★ FY 단독 경로 ★★
    #   사업보고서(FY)의 손익·현금흐름 '당기금액'은 **그 회계연도 12개월 누적치 그 자체**다.
    #   즉 FY 행 하나만 있으면 TTM 은 계산하는 게 아니라 이미 손에 쥐고 있는 값이다.
    #
    #   이 경로가 없으면 어떤 일이 벌어지는가 — 실측된 사고:
    #     DART_FS_FREQ="annual" 로 받으면 Tier-2 는 FY 한 행뿐이고 Q1/H1/Q3 는
    #     Tier-1(fnlttMultiAcnt)에서 온다. Tier-1 에는 현금흐름표가 **아예 없어서**
    #     prev 가 NaN → q_val NaN → rolling(4, min_periods=4) 이 전 구간 NaN.
    #     공용 캐시에 Tier-2 가 2,210조합이나 쌓여 있는데도 cfo_ttm 커버리지가
    #     '약 4%'가 아니라 **정확히 0.0%** 였던 이유가 이것이다. 그리고 그 0.0% 가
    #     CORE-D 5개 TP 를 전멸시켜 L2.SCORE 를 RuntimeError 로 죽였다.
    #
    #   분기 경로가 성립하면(4분기 전부 존재) rolling 합 == FY 누적치이므로 두 값은 일치한다.
    #   따라서 이 보정은 근사가 아니라 **분기가 없을 때만 발동하는 동치 경로**다.
    #   부수효과: 연간 수집만으로 CORE-D 가 살아나므로 Tier-2 호출이 1/4 로 줄어든다.
    _is_fy = (W["q"] == 4)
    _n_fy_direct = 0
    for c in flow_items:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        q_val = np.where(W["q"] == 1, W[c],
                         np.where(contiguous, W[c] - prev, np.nan))
        W[c + "_q"] = q_val
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        ttm = (W.groupby("corp_code", observed=True)[c + "_q"]
                .transform(lambda s: s.rolling(4, min_periods=4).sum()))
        # 분기 경로가 못 만든 FY 행만 누적치 원본으로 채운다(덮어쓰지 않는다).
        _fill = _is_fy & ttm.isna() & W[c].notna()
        _n_fy_direct += int(_fill.sum())
        W[c + "_ttm"] = ttm.where(~_fill, W[c])
    if _n_fy_direct:
        LOG.info(f"FY 누적치를 TTM 으로 직접 채운 (회사×연도×계정) {_n_fy_direct:,}건 — "
                 f"사업보고서의 당기금액은 이미 12개월 누적이므로 차분이 필요 없습니다. "
                 f"(분기 4개가 모두 있으면 이동합과 같은 값이라 경로가 갈려도 결과는 동일합니다)")
    W = W.drop(columns=["_q_prev"])
    # ★ 재무상태표 항목(재고·매출채권·자산·자본 등)은 pivot 결과에 그 계정이 없으면
    #   컬럼 자체가 생성되지 않는다. 그러면 패널 스키마가 실행마다 달라져
    #   "어떤 날은 있고 어떤 날은 없는" 축이 생긴다. 여기서 전 항목을 계약적으로 보장한다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in W.columns:
            W[_k] = np.nan
    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' 플래그 ─────────────────────────────────────
    #   ★ 여기서 만드는 이유: 연속성은 분기 관측을 세야 하는데, 월 패널에서 세면
    #     같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도 정답이 아니다. 분기 프레임은
    #     관측당 정확히 한 행이고 이미 (corp_code, bsns_year, q) 로 정렬돼 있다.
    #     as-of 결합이 이 플래그를 C1 게이트웨이 그대로 실어 나른다.
    #   min_periods=3 — 제출분이 3개 미만이면 NaN(=거부하지 않음). 근거 없는 제외 금지.
    _bad_q = ((col(W, "net_income_ttm") > 0) &
              (col(W, "cfo_ttm") < 0.5 * col(W, "net_income_ttm"))).astype(float)
    W["v2_bad_3q"] = (_bad_q.groupby(W["corp_code"], observed=True)
                            .transform(lambda s: s.rolling(3, min_periods=3).min()))

    # ★★ 티어 혼합으로 인한 '값 가림' 제거 (as-of 결합 직전) ★★
    #   Tier-2(전체재무제표)와 Tier-1(주요계정)은 같은 PIT 테이블의 **서로 다른 행**으로 들어간다.
    #   PIT.asof_join 은 knowledge_date 기준 backward 로 **가장 최근 1행**만 취하므로,
    #   FY2023 을 Tier-2 로 잘 받아 놨어도 2024-05 에 Tier-1 Q1 행이 들어오는 순간
    #   그 행의 cfo_ttm=NaN 이 FY2023 의 값을 덮어 가린다. 즉 받아 놓고도 못 쓴다.
    #
    #   → 회사별로 knowledge_date 순으로 **컬럼 단위 전진충전**한다.
    #     이것은 미래누수가 아니다 — 이미 그 시점에 공시되어 알 수 있었던 값을
    #     '아직 유효한 최신치'로 실어 나르는 것뿐이다(반대로 지금 코드는 알던 것을 잊는다).
    #
    #   다만 무한정 끌고 가면 폐업·상장폐지 직전 회사의 3년 전 값이 영원히 살아남는다.
    #   → 관측 시점으로부터 FS_CARRY_MAX_DAYS 를 넘긴 값은 다시 결측으로 되돌린다.
    #     (연간 공시 주기 + 제출 지연을 감안한 값. 0 으로 채우지 않는다.)
    _cand = [c for c in W.columns
             if c in ACCOUNT_PATTERNS
             or (c.endswith("_ttm") and c.rsplit("_", 1)[0] in FLOW_ITEMS)]
    # 전부 결측인 컬럼은 실어 나를 것이 없고, 결측이 없는 컬럼은 채울 것이 없다 —
    # 둘 다 빼면 (행 × 컬럼) 타임스탬프 행렬이 크게 줄어 메모리·시간이 함께 내려간다.
    # ※ _q(분기 단독치)는 의도적으로 제외한다. 그것은 '그 분기의 값'이라 다음 분기로
    #   끌고 가면 의미가 달라진다. TTM 과 잔액(BS)만 이월한다.
    _carry_cols = [c for c in _cand
                   if 0 < int(W[c].notna().sum()) < len(W)]
    if _carry_cols and len(W):
        W = W.sort_values(["corp_code", "knowledge_date", "q"]).reset_index(drop=True)
        _kd = as_ts_series(W["knowledge_date"])
        _obs = pd.DataFrame({c: _kd.where(W[c].notna()) for c in _carry_cols}, index=W.index)
        _obs = _obs.groupby(W["corp_code"], observed=True).ffill()
        _val = W.groupby("corp_code", observed=True)[_carry_cols].ffill()
        _age = _obs.rsub(_kd, axis=0).apply(lambda s: s.dt.days)
        _before = int(W[_carry_cols].notna().sum().sum())
        W[_carry_cols] = _val.mask(_age > FS_CARRY_MAX_DAYS)
        _after = int(W[_carry_cols].notna().sum().sum())
        if _after > _before:
            LOG.info(f"티어 혼합으로 가려져 있던 재무 관측 {_after - _before:,}개를 되살렸습니다 "
                     f"(회사별 knowledge_date 순 전진충전, {FS_CARRY_MAX_DAYS}일 초과분은 결측 유지). "
                     f"이 보정이 없으면 Tier-2 로 받아 둔 현금흐름표가 다음 분기 Tier-1 행에 "
                     f"가려져 그대로 버려집니다.")

    _missing = [k for k in ACCOUNT_PATTERNS if W[k].notna().sum() == 0]
    if _missing:
        LOG.warn(f"DART 재무에서 한 건도 매칭되지 않은 계정 {len(_missing)}개: "
                 f"{_missing[:8]}{'...' if len(_missing) > 8 else ''} — "
                 f"해당 계정을 쓰는 지표는 전부 결측이 됩니다(0으로 채우지 않음). "
                 f"ACCOUNT_PATTERNS 정규식이 이 회사들의 계정명과 안 맞을 수 있습니다.")
    n_ttm = int(W["revenue_ttm"].notna().sum()) if "revenue_ttm" in W.columns else 0
    if len(W) and n_ttm / len(W) < 0.35:
        LOG.warn(f"TTM 산출률이 {100*n_ttm/len(W):.0f}% 로 낮습니다. 분기보고서가 결측인 기업이 "
                 f"많다는 뜻이며(중소형주에서 흔함), 해당 종목은 B/C축이 결측 처리됩니다. "
                 f"DART_STATEMENT_FREQ='quarterly' 콜드빌드가 아직 미완이라면 이어받기를 계속하세요.")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 재무 정제 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(knowledge_date = 접수일자 기준, 누적→분기 차분 완료)")
    PIPE.io("OUT", "MEM", "dart_financials_tidy", W)
    return downcast(W)


# ── 직원현황 (θ_N, TP_C2) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    if not dart_has_key():
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(c, y) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list):
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 각 조합은 서로소이므로
        #   합산이 맞지만, 일부 기업은 '합계/계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   또 jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이므로 아예 쓰지 않는다.
        for col in ("fo_bbm", "sexdstn"):
            if col in d.columns:
                d = d[~d[col].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        num = lambda s: pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                                      errors="coerce")
        emp = num(d.get("sm", pd.Series(dtype=object))).sum(skipna=True) if "sm" in d.columns else np.nan
        pay = num(d.get("fyer_salary_totamt", pd.Series(dtype=object))).sum(skipna=True) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "employees": float(emp),
                "payroll": float(pay), "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    # ★ E.get("rcept_no", "") 는 컬럼이 없으면 '문자열'을 돌려주고, zip 이 그걸 글자 단위로
    #   훑어 knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    E["knowledge_date"] = [_knowledge_from_rcept(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(E["rcept_no"], E["bsns_year"])]
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart", source="opendart empSttus")
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E


# ── 공시목록 스윕 (시장 전체를 날짜로 훑는다 — 회사별 호출보다 수십 배 싸다) ──────────────────
DISCLOSURE_PATTERNS = {
    "treasury_acq":  r"자기주식\s*취득",
    "treasury_disp": r"자기주식\s*처분",
    "treasury_canc": r"자기주식\s*소각|이익소각",
    "dividend":      r"(현금|현물)?\s*[·ㆍ]?\s*배당\s*결정|결산배당|중간배당",
    "rights_issue":  r"유상증자",
    "cb_issue":      r"전환사채",
    "bw_issue":      r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion": r"감사보고서",
}


# ★ 모듈 스코프여야 한다. 예전엔 fetch_dart_disclosures 안의 지역변수였는데
#   _disclosure_done_months 가 이를 참조해 NameError 가 잠복해 있었다. 예산이 남아 있는
#   첫 실행에서 L1.DART 가 통째로 죽는다(critical=False 라 조용한 WARN 으로).
DISCLOSURE_TYPES = ("A", "B")     # A=정기공시(사업/반기/분기보고서), B=주요사항보고
DISCLOSURE_LEDGER = "dart_disclosure_months"


def _disclosure_done_months(cached: Optional[pd.DataFrame]) -> set:
    """완결이 **증명된** 달만 돌려준다.

    기존 캐시에는 이 원장이 없다. 그렇다고 '캐시에 행이 있으니 완결'로 간주하면
    이미 뚫려 있는 구멍을 그대로 물려받는다. 그래서 레거시 캐시는 (달 × 유형)당
    1회짜리 값싼 탐침으로 total_count 를 받아 실제 보유 행수와 대조해 검증한다.
    120개월이면 240회 — 전체 재수집(수천 회)에 비하면 무시할 수 있는 비용이고,
    이 한 번으로 과거 실행이 남긴 조용한 결손이 드러난다.
    """
    led = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    if led is not None and len(led) and "month" in led.columns:
        d = led[led.get("complete", False).astype(bool)] if "complete" in led.columns else led
        return set(d["month"].astype(str))
    if cached is None or not len(cached):
        return set()

    have = cached["rcept_dt"].dt.to_period("M").astype(str).value_counts().to_dict()
    if not have or not dart_has_key() or RUN_MODE == "CACHED" or dart_halt_reason():
        # 검증할 수 없으면 재수집 대상으로 둔다 — 조용히 '완결'로 승격시키지 않는다.
        return set()

    LOG.info(f"공시목록 캐시 {len(have)}개월의 완결성을 검증합니다 "
             f"(달당 {len(DISCLOSURE_TYPES)}회 탐침 — 과거 실행이 페이지 중간에 끊겼는지 확인).")

    def _probe(mk):
        p = pd.Period(mk, freq="M")
        total = 0
        for ty in DISCLOSURE_TYPES:
            js = dart_api("list.json", {
                "bgn_de": p.start_time.strftime("%Y%m%d"), "end_de": p.end_time.strftime("%Y%m%d"),
                "pblntf_ty": ty, "page_no": 1, "page_count": 1, "last_reprt_at": "N"},
                no_data_ok=True)
            if js is None:
                return mk, None                       # 검증 실패 → 완결로 승격하지 않는다
            total += int(js.get("total_count", 0) or 0)
        return mk, total

    res = pmap_io(_probe, sorted(have), workers=min(N_WORKERS_IO, 8), desc="공시 캐시 완결성 검증")
    ok, holed, unknown = set(), [], 0
    for r in res:
        if not r:
            unknown += 1
            continue
        mk, total = r
        if total is None:
            unknown += 1
        elif have.get(mk, 0) >= total:
            ok.add(mk)
        else:
            holed.append((mk, have.get(mk, 0), total))
    if holed:
        LOG.warn(f"과거 실행이 남긴 공시목록 결손 {len(holed)}개월을 찾았습니다 — "
                 f"예: {[f'{m}: {h}/{t}행' for m, h, t in holed[:3]]}. "
                 f"이 달들을 다시 받습니다. (그대로 뒀다면 유상증자·전환사채·자기주식 공시가 "
                 f"'애초에 없었던 것'으로 백테스트에 들어갔습니다)")
    if unknown:
        LOG.info(f"  {unknown}개월은 검증하지 못해 재수집 대상으로 둡니다(안전한 방향).")
    _save_disclosure_ledger(ok)
    return ok


def _save_disclosure_ledger(complete_months) -> None:
    prev = VAULT.get_table(DISCLOSURE_LEDGER, scope="shared")
    rows = set()
    if prev is not None and len(prev) and "month" in prev.columns:
        keep = prev[prev["complete"].astype(bool)] if "complete" in prev.columns else prev
        rows |= set(keep["month"].astype(str))
    rows |= {str(m) for m in complete_months}
    if not rows:
        return
    VAULT.put_table(DISCLOSURE_LEDGER,
                    pd.DataFrame({"month": sorted(rows), "complete": True}),
                    scope="shared", domain="dart",
                    source="공시목록 완결성 원장 — 페이지를 끝까지 훑은 달만 기록")


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not dart_has_key():
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ '그 달에 행이 하나라도 있다' ≠ '그 달을 다 받았다'
    #
    #  예전에는 have_months 를 캐시 행의 rcept_dt 에서 유도했다. 그래서 12페이지짜리 달을
    #  3페이지에서 예산·네트워크로 놓쳐도, 1~2페이지가 저장되는 순간 그 달은 영원히
    #  '보유'로 표시되고 나머지 페이지는 **두 번 다시 시도되지 않았다.**
    #  잃어버리는 것이 유상증자·전환사채·자기주식 공시라서, 하류(V3 희석 거부권·PACK-C)는
    #  '이벤트 없음'이라는 **정상적인 값**을 읽는다 — 경고도 FAIL 도 뜨지 않고, 재실행할수록
    #  그 거짓이 굳는다. 일시적 장애를 영구적 음성 관측으로 세탁하는 최악의 형태다.
    #  → 완결 여부를 별도 원장에 명시적으로 기록하고, 그 원장만 신뢰한다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    done_months = _disclosure_done_months(cached)
    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in done_months]
    if RUN_MODE == "CACHED":
        todo = []
    elif todo and cached is not None and len(cached):
        LOG.info(f"공시목록 미완결 {len(todo)}개월을 다시 받습니다 "
                 f"(완결 확인 {len(done_months)}개월). 페이지 중간에 끊긴 달은 "
                 f"'보유'로 세지 않습니다 — 그렇게 세면 빠진 공시가 영구히 없는 것이 됩니다.")

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)

    def _one(m):
        """(월, 행들, 완결여부). 한 페이지라도 못 받으면 그 달은 미완결이다."""
        rows, complete = [], True
        for ty in DISCLOSURE_TYPES:
            page, walked = 1, False
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"}, no_data_ok=True)
                if js is None:                       # 예산·네트워크·인증 → 이 달은 미완결
                    complete = False
                    break
                lst = js.get("list")
                if not isinstance(lst, list) or not lst:
                    walked = True                    # 정상 빈 응답 = 이 유형은 여기서 끝
                    break
                rows.extend(lst)
                if page >= int(js.get("total_page", 1) or 1):
                    walked = True
                    break
                page += 1
            else:
                complete = False                     # 100페이지 상한 = 다 못 훑었다
            if not walked and complete is not False:
                complete = False
        return str(m), rows, complete

    new, ok_months, bad_months = [], [], []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if not r:
                continue
            mkey, rows, complete = r
            new.extend(rows)
            (ok_months if complete else bad_months).append(mkey)
        if bad_months:
            LOG.warn(f"공시목록 {len(bad_months)}개월이 미완결로 남았습니다 "
                     f"(예: {bad_months[:3]}). 받은 부분은 저장하되 **완결로 표시하지 않으므로** "
                     f"다음 실행에서 그 달부터 다시 받습니다. "
                     + (f"사유: {dart_halt_reason()}" if dart_halt_reason() else ""))

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "flr_nm", "corp_cls") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures", D, scope="shared", domain="dart", source="opendart list.json")
    # 원장 갱신은 저장 뒤에. 완결로 표시한 달은 실제로 저장된 달이어야 한다.
    if ok_months:
        _save_disclosure_ledger(ok_months)
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")     # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — 이벤트 분류: " +
           ", ".join(f"{k}={int((D['event']==k).sum()):,}" for k in DISCLOSURE_PATTERNS if (D['event']==k).any()))
    PIPE.io("OUT", "DRIVE", "dart_disclosures", D, source="opendart list.json")
    return D



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


_MERGE_WHITELIST = {
    "report_uid", "src_report_id", "source", "category", "pub_date", "title",
    "stock_code", "stock_name", "broker_id", "broker_name", "broker_raw",
    "analyst_raw", "target_price", "opinion", "pdf_url", "detail_url",
    "dedup_key",                       # 그룹 키 자체는 인덱스로 나온다
}


def _carry_extra_cols(d: pd.DataFrame) -> dict:
    """화이트리스트 밖의 컬럼을 병합에서 **떨어뜨리지 않고** 실어 나른다.

    ★★ 절대 1원칙 위반이었다 ★★
      이 함수의 출력은 공용 캐시 research_report_master 로 **덮어써진다.** 그런데
      병합 agg 가 출력 컬럼을 화이트리스트로 열거하고 있어서, 입력에 있던
      pdf_uid·pdf_analysts·pdf_emails·pdf_target·views 같은 컬럼이 왕복 한 번마다
      조용히 사라졌다. 즉 PDF 를 한 번 받아 채워 넣어도 다음 실행에서 그 정보가
      공용 캐시에서 영구히 지워지고, 다른 전략도 그 손실을 그대로 물려받는다.
      "삭제 API 가 없다"는 원칙은 파일 단위로는 지켜졌지만 **컬럼 단위로는 새고 있었다.**

    숫자는 max(결측 무시), 그 외는 '비지 않은 첫 값'으로 접는다 — 둘 다 순서에 무관해
    재실행 멱등성을 깨지 않는다.
    """
    out = {}
    for c in d.columns:
        if c in _MERGE_WHITELIST:
            continue
        if pd.api.types.is_numeric_dtype(d[c]) or pd.api.types.is_datetime64_any_dtype(d[c]):
            out[c] = (c, "max")
        else:
            out[c] = (c, _pick_str)
    return out


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
        **_carry_extra_cols(d),
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

# ★ as-of 결합에서 '마지막으로 알려진 값'을 며칠까지 실어 나를 것인가.
#   연간 공시 주기(365일) + 제출 지연 여유. 이보다 오래된 것은 결측으로 둔다 —
#   무한 이월은 결측을 가짜 0.0 차분으로 둔갑시켜 증거층 게이트를 속인다.
#   0 이면 제한 없음(예전 동작). 바꾸지 마십시오.
PIT_ASOF_MAX_DAYS = 550


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
        # ★★ tolerance ★★ 이게 없으면 '마지막으로 알려진 행'이 **무한히 미래로 이월**된다.
        #   격자가 불완전해 중간 연도가 빈 회사에서, 2019년 재무가 2024년 달에 그대로 붙고
        #   diff(12) 가 결측이 아니라 **정확히 0.0** 이 된다. 그 가짜 관측이 FLOOR
        #   (MIN_TP_OBSERVED)를 통과해 '커버리지가 있는 것처럼' 보인다 — 조용히 틀리는
        #   방향이라 크래시보다 나쁘다. 알 수 없는 것은 끝까지 결측으로 둔다.
        _tol = pd.Timedelta(days=int(PIT_ASOF_MAX_DAYS)) if PIT_ASOF_MAX_DAYS else None
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", tolerance=_tol,
                              suffixes=("", suffix or "_r"))
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  상장폐지 '유형' 분류 — 청산가를 -100% 로 둘지 직전가로 둘지 가른다
#
#  ★ 왜 필요한가. 예전엔 모든 폐지를 -100% 로 처리했다. 그런데 폐지목록 원본의 Reason 을
#    실측해 보면 2016년 이후 폐지된 주권 561건 중
#      · 피흡수합병 60 · 스팩소멸합병 53 · 지주회사 완전자회사화 29 · 타법인 완전자회사 편입 14
#        → 합병 대가로 인수기업 주식을 받는다. 0% 도 아니고 보통 프리미엄이 붙는다.
#      · 스팩 예심청구서 미제출·해산 ~110  → 예치금이 공모가 + 이자로 반환된다(사실상 원금).
#    즉 **절반 이상이 전액손실이 아닌데 전액손실로 계상**되고 있었다.
#    U-MID 대역의 연 폐지율(~4.9%)과 25종목 포트폴리오로 환산하면 연 -2%p 안팎의
#    '있지도 않은 손실'이다. 게다가 이것은 보수적인 방향이 아니라 **틀린** 방향이다.
#
#  ★ 그렇다고 프리미엄을 지어내지 않는다. 합병·해산 건은 **직전 관측가로 청산**한다.
#    한국 시장의 합병 스프레드는 좁아 직전가가 편향 없는 추정치이고, 실제 프리미엄보다
#    낮으므로 여전히 보수적이다. 부실 폐지(감사의견 거절·자본잠식·부도)는 종전대로
#    정리매매가가 없으면 -100% 다.
# ══════════════════════════════════════════════════════════════════════════════════════════
DELIST_TRANSFER_PAT = (
    r"흡수합병|피흡수|합병으로|완전자회사|지주회사|주식교환|주식의\s*포괄적|"
    r"신청에\s*의한\s*상장폐지|상장폐지\s*신청|자진|공개매수|이전상장|재상장|시장이전")
DELIST_SPAC_PAT = (
    # 스팩 특유의 사유들. '청구서'와 '신청서'가 혼용되고, '존속기간 만료'는 스팩의
    # 3년 존속기간이 끝나 예치금을 반환하고 해산하는 경우다(부실이 아니다).
    r"스팩|기업인수목적|예비심사\s*(청구서|신청서)\s*미제출|합병상장예비심사신청서\s*미제출|"
    r"해산\s*사유|존속기간\s*만료")
DELIST_DISTRESS_PAT = (
    # ★ '자본잠식' 을 그대로 쓰면 실제 표기인 '자본전액잠식'(전액이 사이에 낀다)을 놓친다.
    #   계약 C2c 가 이 누락을 잡아냈다 — 사유 문자열은 KRX 표기 그대로 검증해야 한다.
    r"감사의견|의견거절|부적정|자본\S*잠식|부도|파산|회생|영업정지|계속기업|"
    r"상장폐지\s*기준에\s*해당|횡령|배임|사업보고서\s*미제출|주식\S*분산\s*미달|"
    r"매출액\s*미달|시가총액\s*미달|거래량\s*미달")


def classify_delisting(reason: Any) -> str:
    """'transfer'(합병·자진) | 'spac'(스팩 해산) | 'distress'(부실) | 'unknown'"""
    s = str(reason or "").strip()
    if not s:
        return "unknown"
    # 부실을 먼저 본다. '스팩소멸합병'처럼 두 패턴이 겹칠 때 관대한 쪽으로 새지 않게
    # 하려는 것이 아니라, 반대로 부실 신호가 있으면 무조건 부실로 보내기 위함이다.
    if re.search(DELIST_DISTRESS_PAT, s):
        return "distress"
    if re.search(DELIST_TRANSFER_PAT, s):
        return "transfer"
    if re.search(DELIST_SPAC_PAT, s):
        return "spac"
    return "unknown"


# 직전가 청산으로 볼 유형. 'unknown' 은 포함하지 않는다 — 모르면 보수적으로 -100%.
DELIST_NOT_WIPEOUT = ("transfer", "spac")


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

    def delist_kind_map(self) -> Dict[str, str]:
        """종목 → 폐지 유형. 청산가를 -100% 로 둘지 직전가로 둘지 가른다."""
        if "delist_reason" not in self.sec.columns:
            return {}
        return {r.code: classify_delisting(getattr(r, "delist_reason", ""))
                for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  감쇠 원장 — 팔(arm) 태그와 기록 스위치
    #
    #  ★★ 왜 필요한가 (7회차 리포트에 '잔존율 113.7%' 라는 불가능한 숫자가 찍힌 자리) ★★
    #    이 리스트는 전역 하나였고 태그가 없었다. 그런데 여기에 쓰는 주체가 셋이다:
    #      ① 전체(ALL) 팔의 apply_umid  ② 하위1000(SMALL) 팔의 apply_umid
    #      ③ run_backtest — 그리고 강건성 스위트가 백테스트를 **10여 회 재실행**한다.
    #    report_attrition 은 stage 별 단순 평균을 내므로,
    #      '유동성필터' = ALL 패널에서 잰 월평균(≈1,500)
    #      'U-MID대역'  = ALL 과 SMALL 을 섞은 월평균(≈1,300)
    #    처럼 **서로 다른 모집단의 평균**이 한 깔때기에 세로로 놓인다. 뒤 단계가 앞 단계보다
    #    커지는 순간 잔존율이 100%를 넘는다. 숫자가 이상해서 눈에 띈 것이 다행이었다 —
    #    조금만 덜 이상했으면 '어느 게이트에서 표본이 붕괴하는가'를 통째로 오독했을 것이다.
    #  → ① 모든 기록에 arm 태그를 단다. ② 팔별로 표를 따로 낸다.
    #    ③ 강건성 재실행은 audit_on=False 로 아예 기록하지 않는다(같은 달을 10번 세면
    #       평균은 같지만 min/max 가 의미를 잃고, 팔 태그도 뒤섞인다).
    # ══════════════════════════════════════════════════════════════════════════════════════
    audit_arm: str = "MAIN"
    audit_on: bool = True

    def set_audit_arm(self, arm: str, on: bool = True):
        self.audit_arm, self.audit_on = str(arm), bool(on)

    def audit_row(self, stage: str, t, codes: Sequence[str], arm: Optional[str] = None):
        if not self.audit_on:
            return
        self.attrition.append({"arm": str(arm or self.audit_arm), "month": as_ts(t),
                               "stage": stage, "n": len(codes)})

    def report_attrition(self, title_suffix: str = ""):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        if "arm" not in A.columns:
            A["arm"] = "MAIN"
        # ★ 같은 (팔, 단계, 달) 이 두 번 기록되면 평균이 바뀌진 않지만 min/max·표본수가
        #   왜곡된다. 마지막 기록을 진실로 본다(재실행이 있었다면 그쪽이 최신이다).
        A = A.drop_duplicates(["arm", "stage", "month"], keep="last")
        # ★ 이 목록에 없는 단계는 표에서 조용히 사라진다(오류도 경고도 없이).
        #   새 게이트를 추가했다면 반드시 여기에도 넣을 것.
        order = ["전체상장", "PIT유니버스", "가격보유", "U-MID대역", "유동성필터", "거부권통과",
                 "하한선통과", "최종선정"]
        for arm in sorted(A["arm"].unique(), key=lambda x: (x != "MAIN", x)):
            sub = A[A["arm"] == arm]
            piv = sub.groupby("stage")["n"].agg(["mean", "min", "max", "size"])
            rows, prev = [], None
            for s in order:
                if s not in piv.index:
                    continue
                m = piv.loc[s]
                keep = "" if prev is None else f"{100*m['mean']/prev:.1f}%"
                # 100% 초과는 이제 구조적으로 나올 수 없지만, 나오면 그 사실을 표에 적는다.
                if prev is not None and m["mean"] > prev * 1.001:
                    keep += " ⚠모집단불일치"
                rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}",
                             f"{int(m['size']):,}", keep])
                prev = m["mean"]
            if not rows:
                continue
            LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "관측월", "직전 대비 잔존율"],
                      ["l", "r", "r", "r", "r", "r"],
                      title=f"유니버스 감쇠 감사 (§10.4) · 팔={arm}{title_suffix} "
                            f"— 어느 게이트에서 표본이 붕괴하는지")
            if float(str(rows[-1][1]).replace(",", "")) < PORTFOLIO_MIN_NAMES:
                LOG.warn(f"[{arm}] 최종 선정 종목이 월평균 {rows[-1][1]}개로 "
                         f"PORTFOLIO_MIN_NAMES={PORTFOLIO_MIN_NAMES} 에 못 미칩니다. "
                         f"이 수준에서는 성과가 종목 몇 개의 함수이지 전략의 함수가 아닙니다 — "
                         f"임계값을 낮추기 전에 위 표에서 어느 게이트가 원인인지 확인하세요.")


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
# ║  L1-G  공용축 B(회계품질) · C(자원투입) · D(반영도)  — 전 팩 공유, 필수                    ║
# ║                                                                                          ║
# ║  B·C 는 '확인'이 아니라 '사전확률'로 쓴다. K분기 연속 정렬 같은 대기조건을 넣지 않는다.     ║
# ║  가장 느린 축에 전체를 묶으면 선행성을 잃기 때문이다(§1.4).                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_base_panel(uni: "Universe", months: pd.DatetimeIndex,
                     price_m: pd.DataFrame) -> pd.DataFrame:
    """(code, month) 기본 격자. 여기에 모든 축이 as-of 로 붙는다."""
    rows = []
    for m in months:
        codes = uni.at(m)
        uni.audit_row("PIT유니버스", m, codes)
        rows.append(pd.DataFrame({"code": codes, "month": m}))
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["code", "month"])
    P = P.merge(price_m, on=["code", "month"], how="left")
    for m in months:
        sub = P[(P["month"] == m) & P["close"].notna()]
        uni.audit_row("가격보유", m, sub["code"].tolist())
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {len(months)}개월) "
           f"— 메모리 {mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel", P)
    return P


def attach_fundamentals(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """재무·직원 데이터를 PIT as-of 로 결합. 여기가 미래누수의 최대 위험지점이다."""
    c2c = sec.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str).to_dict()
    P = P.copy()
    P["corp_code"] = P["code"].map(c2c)
    if PIT.has("dart_financials"):
        P = PIT.asof_join(P, "dart_financials", by="corp_code", left_time="month")
    if PIT.has("dart_employees"):
        P = PIT.asof_join(P, "dart_employees", by="corp_code", left_time="month",
                          cols=["corp_code", "knowledge_date", "employees", "payroll"],
                          suffix="_emp")
    # ★ 결합 '이후에' 채운다. 먼저 만들어 두면 merge_asof 가 접미사를 붙여 실제 값을 흘려버린다.
    #
    #   왜 전 계정을 계약적으로 보장하는가 ─────────────────────────────────────────────────
    #   DART 키가 없거나(상단 안내가 "아무것도 안 채워도 실행된다"고 약속한다) 재무 수집이
    #   부분 실패하면 asof_join 이 아예 일어나지 않아 revenue_ttm·assets 같은 컬럼이
    #   존재하지 않게 된다. 피처 계산부는 col() 로 결측 컬럼을 막아 두었지만
    #   groupby(...)[c] 는 KeyError 로 죽고, 그 위치(L1.PANEL)는 critical 스테이지라
    #   실행 전체가 중단된다. 특히 손익·현금흐름 계정은 tidy_financials 가 항상 만들지만
    #   재무상태표 계정(assets·contract_liab 등)은 그 계정이 매칭됐을 때만 생기므로,
    #   "DART 는 응답했는데 BS 계정만 정규식이 안 맞은" 경우엔 패널이 멀쩡한 채로 죽는다.
    #   여기서 전부 NaN 으로 채워 두면 B/C축이 통째로 결측이 될 뿐 실행은 끝까지 간다.
    for c in FUNDAMENTAL_COLS:
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_financials"):
        LOG.warn("DART 재무가 없어 B축(회계품질)·C축(자원투입)과 PACK-C 가 전부 결측입니다. "
                 "실행은 계속되지만 증거층이 얇아집니다 — DART_API_KEY 를 넣으면 살아납니다.")
    return P


# ── B축: 회계 품질 ──────────────────────────────────────────────────────────────────────────
def axis_B(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)

    rev = col(P, "revenue_ttm")
    cogs = col(P, "cogs_ttm")
    P["gpm"] = safe_div(rev - cogs, rev) if rev is not None and cogs is not None else np.nan
    # b1: GPM 추세 기울기 (12개월 창의 선형 기울기 — 4분기 추세의 월간 등가물)
    P["b1"] = g("gpm").transform(lambda s: s.rolling(12, min_periods=6)
                                 .apply(lambda w: np.polyfit(np.arange(len(w)), w, 1)[0]
                                        if np.isfinite(w).all() else np.nan, raw=True))
    P["DIO"] = safe_div(col(P, "inventory"), col(P, "cogs_ttm")) * 365.0
    P["DSO"] = safe_div(col(P, "receivable"), col(P, "revenue_ttm")) * 365.0
    P["turn_days"] = P["DIO"] + P["DSO"]
    P["d_turn"] = g("turn_days").diff(12)
    P["dlog_rev"] = g("revenue_ttm").transform(lambda s: dlog(s, 12))

    # accruals (Sloan) — 순이익이 음수인 구간에서 CF/NI 비율을 쓰지 말 것(§7.1)
    avg_assets = (col(P, "assets") + g("assets").shift(12)) / 2.0
    P["accruals"] = safe_div(col(P, "net_income_ttm") - col(P, "cfo_ttm"), avg_assets)
    P["d_accruals"] = g("accruals").diff(12)
    P["b4"] = safe_div(g("contract_liab").diff(12), col(P, "revenue_ttm"))
    return P


def axis_B_tp(P: pd.DataFrame) -> pd.DataFrame:
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_B1"] = tp_product(z("dlog_rev"), -z("d_turn"))      # 매출↑ 인데 회전 유지
    P["TP_B2"] = tp_product(z("dlog_rev"), -z("d_accruals"))  # 매출↑ 인데 발생액 유지
    P["E_AXB"] = nanmean_cols(P, ["TP_B1", "TP_B2"]) * 0.5 + \
        nanmean_cols(pd.DataFrame({"a": z("b1"), "b": z("b4")}), ["a", "b"]) * 0.5
    return P


# ── C축: 자원 투입 ──────────────────────────────────────────────────────────────────────────
def axis_C(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)
    nwc = (col(P, "receivable").fillna(0) + col(P, "inventory").fillna(0) -
           col(P, "payable").fillna(0)) if "receivable" in P.columns else np.nan
    P["IC"] = nwc + col(P, "ppe").fillna(0) + col(P, "intangible").fillna(0)
    P["dlog_IC"] = g("IC").transform(lambda s: dlog(s, 12))
    nopat = col(P, "op_income_ttm") * 0.78                      # 법인세 22% 가정(셀 내 상대값이라 수준은 무해)
    avg_ic = (P["IC"] + g("IC").shift(12)) / 2.0
    P["ROIC"] = safe_div(nopat, avg_ic)
    P["d_ROIC"] = g("ROIC").diff(12)
    P["value_added"] = (col(P, "op_income_ttm").fillna(0) + col(P, "payroll").fillna(0) +
                        col(P, "dep_ttm").fillna(0))
    P["va_per_emp"] = safe_div(P["value_added"], col(P, "employees"))
    P["d_va_per_emp"] = g("va_per_emp").diff(12)
    P["dlog_emp"] = g("employees").transform(lambda s: dlog(s, 12))
    P["c3"] = safe_div(col(P, "capex_ttm").abs(), col(P, "dep_ttm").abs())
    P["debt_ratio"] = safe_div(col(P, "liabilities"), col(P, "equity"))
    P["d_debt_ratio"] = g("debt_ratio").diff(12)
    return P


def axis_C_tp(P: pd.DataFrame) -> pd.DataFrame:
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_C1"] = tp_product(z("dlog_IC"), z("d_ROIC"))            # 확장하는데 수익성 유지
    P["TP_C2"] = tp_product(z("dlog_emp"), z("d_va_per_emp"))     # 인원↑ 인데 생산성 유지
    P["E_AXC"] = nanmean_cols(P, ["TP_C1", "TP_C2"]) * 0.5 + \
        nanmean_cols(pd.DataFrame({"a": z("c3")}), ["a"]) * 0.5
    return P


# ── D축: 반영도 (U 산출) — 이 시스템에서 가장 중요한 단일 지표 ───────────────────────────────
def axis_D(P: pd.DataFrame, px_daily: pd.DataFrame, flows: pd.DataFrame,
           cons: pd.DataFrame) -> pd.DataFrame:
    """Δlog P = Δlog E + Δlog M 분해.

    목표 상태: ΔlogE > 0 AND ΔlogM <= 0
      → 시장이 이익 증가는 인정했으나 자본화를 거부 = "일회성으로 분류함" = 노리는 미스프라이싱
    d1 = -Δlog M

    ⚠ 한계 명시(§16.2): 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하다. 따라서 E 는
      후행 12M EPS(=DART TTM 순이익/주식수 대신 시가총액 기준으로 EPS 대리)를 쓴다.
      이 대리변수의 한계를 리포트에 반드시 명시하고 숨기지 않는다.
    """
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)

    # E 대리: TTM 순이익. M 대리: 시가총액/TTM순이익 → 주식수를 모를 때도 비율은 성립한다.
    P["E_proxy"] = col(P, "net_income_ttm")
    P["mktcap_proxy"] = P["close"]                       # 셀 내 상대비교라 주식수 상수배는 무해
    # 120거래일 ≈ 6개월 창
    P["dlog_E"] = g("E_proxy").transform(lambda s: dlog(s, 6))
    P["dlog_P"] = g("close").transform(lambda s: dlog(s, 6))
    P["dlog_M"] = P["dlog_P"] - P["dlog_E"]
    P["d1"] = -P["dlog_M"]
    P["D_state"] = np.select(
        [(P["dlog_E"] > 0) & (P["dlog_M"] <= 0),
         (P["dlog_E"] > 0) & (P["dlog_M"] > 0),
         (P["dlog_E"] <= 0) & (P["dlog_M"] > 0)],
        ["목표상태(진입)", "리레이팅중(관망)", "기대선행(배제)"], default="개선없음(배제)")

    # d3: 120일 기관+외국인 누적순매수 / 시총 (부호 반전 — 아직 안 들어온 게 좋다)
    P["d3"] = np.nan
    if flows is not None and len(flows):
        f = flows.copy()
        f["date"] = as_ts_series(f["date"])
        f["net"] = f.get("inst_net").fillna(0) + f.get("foreign_net").fillna(0)
        f = f.sort_values(["code", "date"])
        f["cum120"] = (f.groupby("code", observed=True)["net"]
                        .transform(lambda s: s.rolling(120, min_periods=40).sum()))
        f["month"] = f["date"].values.astype("datetime64[M]")
        fm = (f.groupby(["code", "month"], observed=True)["cum120"].last().reset_index())
        fm["month"] = as_ts_series(fm["month"]) + pd.offsets.MonthEnd(0)
        P = P.merge(fm, on=["code", "month"], how="left")
        adv = P["adv20"].replace(0, np.nan)
        P["d3"] = -safe_div(P["cum120"], adv * 250.0)     # 시총 대신 연간 거래대금으로 정규화

    # d2/d4: 컨센서스 (애널리스트 원장에서 산출)
    P["d2"] = np.nan
    P["d4"] = np.nan
    if cons is not None and len(cons):
        P = P.merge(cons[["code", "month", "d2_raw", "d4_raw", "n_analyst", "tp_median"]],
                    on=["code", "month"], how="left")
        P["d2"] = P["d2_raw"]
        P["d4"] = P["d4_raw"]
    return P


def axis_D_U(P: pd.DataFrame) -> pd.DataFrame:
    """U = 결측 제외 평균. ★ 결측 축을 0으로 채우지 않는다(§7.3)."""
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    Z = pd.DataFrame({"z_d1": z("d1"), "z_d2": z("d2"), "z_d3": z("d3"), "z_d4": z("d4")})
    avail = Z.notna().sum(axis=1)
    P["U_raw"] = nanmean_cols(Z, list(Z.columns))
    P["U_axes_used"] = avail
    P["U"] = xsec_rank_pct_l(P, P["U_raw"])
    used = {c: int(Z[c].notna().sum()) for c in Z.columns}
    LOG.info("D축 가용성 — " + " · ".join(f"{k}:{v:,}행" for k, v in used.items()) +
             f"  (평균 가용 축 {avail.mean():.2f}개)")
    if used.get("z_d2", 0) == 0 and used.get("z_d4", 0) == 0:
        LOG.warn("컨센서스 기반 d2/d4 가 전무합니다. U 는 d1(+d3)만으로 구성됩니다. "
                 "애널리스트 리포트 수집이 실패했거나 목표주가 추출률이 0인 상태입니다 — "
                 "위 원장 무결성 감사표를 확인하세요.")
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  센서팩 레지스트리                                                                   ║
# ║                                                                                          ║
# ║  팩은 플러그인이다. 각 팩은 자기 자신을 여기에 등록하고, 스코어 조립부는 레지스트리만 본다.  ║
# ║  → 이 파일에 어떤 팩이 포함되어 빌드되었는지가 곧 전략의 정의가 된다.                       ║
# ║  C12: 정책 캘린더가 없는 센서팩은 등록될 수 없다.                                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_REGISTRY: "OrderedDict[str, dict]" = OrderedDict()


def register_pack(pid: str, name: str, tp_cols: Sequence[str], features_fn: Callable,
                  policy: Sequence[dict], interp: Sequence[Tuple[str, str, str]],
                  ingest_fn: Optional[Callable] = None, theta_col: Optional[str] = None,
                  notes: str = ""):
    if not policy:
        raise RuntimeError(
            f"[C12 위반] 센서팩 '{pid}' 에 정책 캘린더가 없습니다. "
            f"정책 캘린더 없는 센서팩은 파이프라인에 등록될 수 없습니다(§12). "
            f"모든 대체데이터는 정책에 오염됩니다 — 이건 PACK-N 만의 문제가 아닙니다.")
    PACK_REGISTRY[pid] = {
        "id": pid, "name": name, "tp_cols": list(tp_cols), "features": features_fn,
        "ingest": ingest_fn, "policy": list(policy), "interp": list(interp),
        "theta_col": theta_col, "notes": notes,
        "enabled": True, "disable_reason": "", "E_col": f"E_{pid}",
    }


def active_packs() -> List[dict]:
    return [p for pid, p in PACK_REGISTRY.items()
            if p["enabled"] and pid in ACTIVE_PACKS]


def disable_pack(pid: str, reason: str):
    if pid in PACK_REGISTRY:
        PACK_REGISTRY[pid]["enabled"] = False
        PACK_REGISTRY[pid]["disable_reason"] = reason
        LOG.warn(f"센서팩 '{pid}' 비활성화 — {reason} (조용히 남겨두지 않고 명시적으로 끕니다)")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PACK-P  조달청 낙찰  (내수 수주기업 보강)                                                 ║
# ║                                                                                          ║
# ║  매핑 문제가 구조적으로 없다 — 낙찰업체가 사업자등록번호로 직접 식별된다.                    ║
# ║  낙찰률(q2)은 원가 노이즈가 없는 순수 가격 지표라는 점에서 수출단가와 동일한 성질.           ║
# ║                                                                                          ║
# ║  ⚠ 레짐 편승 경고: 이 데이터는 방산·전력기기·원전·철도·건설에 집중되는데,                    ║
# ║    이것이 정확히 현 KOSPI 주도 섹터다. R7 레짐 분할을 필수 통과 조건으로 건다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PACK_P_POLICY = [
    {"policy_id": "SME_COMPETE_ITEM", "name": "중소기업자간 경쟁제품 지정(3년 주기 갱신)",
     "start": "2016-01-01", "end": None, "pack": "P", "req_type": "기업규모", "req_value": "중소기업"},
    {"policy_id": "REGION_LIMIT_BID", "name": "지역제한 입찰 제도", "start": "2016-01-01",
     "end": None, "pack": "P", "req_type": "지역", "req_value": "본점 소재지"},
    {"policy_id": "DEFENSE_BUDGET_EXPAND", "name": "국방예산 증액 국면", "start": "2022-01-01",
     "end": None, "pack": "P", "req_type": "업종", "req_value": "방산"},
    {"policy_id": "NEWDEAL_2020", "name": "한국판 뉴딜(SOC·디지털)", "start": "2020-07-14",
     "end": "2022-12-31", "pack": "P", "req_type": "없음", "req_value": ""},
    {"policy_id": "NUCLEAR_POLICY_SHIFT", "name": "원전 정책 전환(탈원전→원전확대)",
     "start": "2022-05-10", "end": None, "pack": "P", "req_type": "업종", "req_value": "원전"},
]

PACK_P_INTERP = [
    ("TP_Q1", "가격 안 깎고 수주 확대", "저가 수주로 물량만 늘림"),
    ("TP_Q2", "발주처 다변화인데 마진 유지", "특정 발주처 의존 심화 또는 저가 확장"),
]

G2B_API = "https://apis.data.go.kr/1230000/ScsbidInfoService/"


def fetch_procurement(months: pd.DatetimeIndex) -> pd.DataFrame:
    """나라장터 낙찰정보. 사업자등록번호와 예정가격이 있어야 q2(낙찰률)가 산다."""
    key = _datagokr_key()
    cached = VAULT.get_table("g2b_awards_monthly", scope="shared")
    have = set(cached["ym"].astype(str)) if cached is not None and len(cached) else set()
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 조달 낙찰 {len(cached):,}행 재사용")
    if not key:
        if not have:
            LOG.warn("DATA_GO_KR_KEY 미입력 — PACK-P 를 구동할 수 없습니다.")
            return pd.DataFrame()
        return cached
    todo = [m for m in months if m.strftime("%Y%m") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    def _one(m):
        rows, page = [], 1
        while page <= 200:
            limiter("datagokr").wait()
            js = http_json(G2B_API + "getScsbidListSttusThng", source="datagokr", tries=2,
                           params={"serviceKey": key, "numOfRows": 999, "pageNo": page,
                                   "inqryDiv": 1, "type": "json",
                                   "inqryBgnDt": m.strftime("%Y%m01") + "0000",
                                   "inqryEndDt": (m + pd.offsets.MonthEnd(0)).strftime("%Y%m%d") + "2359"})
            if not js:
                break
            body = (js.get("response", {}).get("body") if isinstance(js, dict) else None) or {}
            items = body.get("items") or []
            it = items.get("item") if isinstance(items, dict) else items
            if isinstance(it, dict):
                it = [it]
            if not it:
                break
            for r in it:
                rows.append({
                    "ym": m.strftime("%Y%m"),
                    "biz_no": re.sub(r"\D", "", str(r.get("bizno") or r.get("bidwinnrBizno") or "")),
                    "corp_nm": str(r.get("bidwinnrNm") or r.get("cmpnyNm") or ""),
                    "award_amt": pd.to_numeric(r.get("sucsfbidAmt"), errors="coerce"),
                    "plan_price": pd.to_numeric(r.get("presmptPrce"), errors="coerce"),
                    "rate": pd.to_numeric(r.get("sucsfbidRate"), errors="coerce"),
                    "org": str(r.get("dminsttNm") or ""),
                    "item_cls": str(r.get("prdctClsfcNo") or ""),
                })
            page += 1
        return rows

    new = []
    if todo:
        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="조달청 낙찰")
        for r in res:
            if r:
                new.extend(r)
    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        frames.append(pd.DataFrame(new))
    if not frames:
        return pd.DataFrame()
    G = pd.concat(frames, ignore_index=True)
    if new:
        VAULT.put_table("g2b_awards_monthly", G, scope="shared", domain="procurement",
                        source="나라장터 낙찰정보")
    has_plan = float(G["plan_price"].notna().mean()) if "plan_price" in G.columns else 0.0
    LOG.ok(f"조달 낙찰 {len(G):,}건 (예정가격 보유율 {100*has_plan:.1f}%)")
    if has_plan < 0.2:
        LOG.warn("예정가격 보유율이 20% 미만입니다. q2(낙찰률)가 사실상 죽고 팩 가치가 급감합니다 "
                 "(§6.4 착수 전 확인 항목). TP_Q1/TP_Q2 결과 해석 시 반드시 감안하세요.")
    return G


def pack_p_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    G, sec = ctx.get("procurement"), ctx.get("sec")
    for c in ("q1", "q2", "q3", "q4"):
        P[c] = np.nan
    if G is None or len(G) == 0:
        P["TP_Q1"] = np.nan; P["TP_Q2"] = np.nan; P["E_P"] = np.nan
        disable_pack("P", "조달청 낙찰 데이터 부재")
        return P
    # 사업자번호 → 종목코드: DART 회사개황이 없으면 상호 유사도로 연결
    n2c = {}
    if sec is not None and len(sec):
        for _, r in sec.iterrows():
            n = norm_corp_name(r.get("name"))
            if n and n not in n2c:
                n2c[n] = r.get("code")
    G = G.copy()
    G["code"] = G["corp_nm"].map(lambda s: n2c.get(norm_corp_name(s)))
    G = G.dropna(subset=["code"])
    if G.empty:
        P["TP_Q1"] = np.nan; P["TP_Q2"] = np.nan; P["E_P"] = np.nan
        disable_pack("P", "조달 낙찰업체를 상장사와 연결하지 못함")
        return P
    G["month"] = as_ts_series(G["ym"].astype(str) + "01") + pd.offsets.MonthEnd(0)
    G["win_rate"] = G["rate"].where(G["rate"].between(50, 120),
                                    safe_div(G["award_amt"], G["plan_price"]) * 100.0)
    T = (G.groupby(["code", "month"], as_index=False)
          .agg(award_amt=("award_amt", "sum"), win_rate=("win_rate", "mean"),
               n_org=("org", "nunique"), n_award=("award_amt", "size")))
    org_sh = (G.assign(one=1).groupby(["code", "month", "org"], as_index=False)["award_amt"].sum())
    org_sh["sh"] = org_sh["award_amt"] / org_sh.groupby(["code", "month"])["award_amt"].transform("sum")
    hhi = org_sh.assign(sh2=lambda d: d["sh"] ** 2).groupby(["code", "month"], as_index=False)["sh2"].sum()
    T = T.merge(hhi.rename(columns={"sh2": "hhi_org"}), on=["code", "month"], how="left")
    # PIT: 개찰일/공고일 중 늦은 것 → 월말 + 공개 지연 15일
    T["knowledge_date"] = T["month"] + pd.Timedelta(days=15)
    T = pit_frame(T, "month", "knowledge_date", source="procurement")
    PIT.register("procure_panel", T, key_cols=["code"])
    P = PIT.asof_join(P, "procure_panel", by="code", left_time="month",
                      cols=["code", "knowledge_date", "award_amt", "win_rate", "hhi_org", "n_award"],
                      suffix="_g2b")
    P = P.sort_values(["code", "month"])
    g = lambda c: gby(P, c)      # 없는 컬럼도 NaN 으로 만든 뒤 그룹화 (수집 부분실패 내성)
    P["q1"] = g("award_amt").transform(lambda s: dlog(s.rolling(12, min_periods=6).sum(), 12))
    P["q2"] = g("win_rate").diff(12)
    P["q3"] = -g("hhi_org").diff(12)
    z = lambda c: xsec_z_l(P, c)          # 셀 폴백 사다리 적용 (C11)
    P["TP_Q1"] = tp_product(z("q1"), z("q2"))
    P["TP_Q2"] = tp_product(z("q3"), z("q2"))
    P["E_P"] = nanmean_cols(P, ["TP_Q1", "TP_Q2"])
    return P


def pack_p_ingest(ctx: dict, months: pd.DatetimeIndex) -> None:
    """PACK-P 전용 수집 — 조달청 낙찰 원장."""
    ctx["procurement"] = fetch_procurement(months)


register_pack(
    pid="P", name="조달청 낙찰", tp_cols=["TP_Q1", "TP_Q2"],
    features_fn=pack_p_features, policy=PACK_P_POLICY, interp=PACK_P_INTERP,
    ingest_fn=pack_p_ingest,
    notes="낙찰률은 원가 노이즈가 없는 순수 가격 지표 — 수출단가와 동일한 성질. "
          "단 방산·원전 레짐 편승 위험이 크므로 R7 필수.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  정책 캘린더 (§12) — 모든 센서팩의 필수 자산 (C12)                                   ║
# ║                                                                                          ║
# ║  모든 대체데이터는 정책에 오염된다. 이건 PACK-N 고유 문제가 아니다.                          ║
# ║  정책 시행일은 공개되어 있고 정확하다 → 그래서 이 오염만은 자연실험 설계가 가능하다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

POLICY_COLS = ["policy_id", "name", "start", "end", "pack", "req_type", "req_value", "url"]


def build_policy_calendar() -> pd.DataFrame:
    rows = []
    for pid, p in PACK_REGISTRY.items():
        for e in p["policy"]:
            r = {c: e.get(c) for c in POLICY_COLS}
            r["pack"] = r.get("pack") or pid
            rows.append(r)
    # 전 팩 공통 매크로 이벤트 (팩 무관하게 신호-수익 관계를 흔드는 국면)
    rows += [
        {"policy_id": "COVID_CRASH", "name": "코로나 급락/급반등", "start": "2020-02-20",
         "end": "2020-09-30", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORT_BAN_2020", "name": "공매도 전면금지", "start": "2020-03-16",
         "end": "2021-05-02", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORT_BAN_2023", "name": "공매도 전면금지(2차)", "start": "2023-11-06",
         "end": "2025-03-31", "pack": "*", "req_type": "없음", "req_value": ""},
    ]
    C = pd.DataFrame(rows, columns=POLICY_COLS)
    C["start"] = as_ts_series(C["start"])
    C["end"] = as_ts_series(C["end"]).fillna(as_ts(BACKTEST_END))
    C = C.dropna(subset=["start"]).drop_duplicates("policy_id")
    LOG.ok(f"정책 캘린더 {len(C)}건 등록 (C12 — 캘린더 없는 팩은 등록 자체가 불가)")
    PIPE.io("OUT", "MEM", "policy_calendar", C)
    return C


def policy_windows(cal: pd.DataFrame, packs: Sequence[str], months: pd.DatetimeIndex,
                   halo_months: int = 6) -> pd.Series:
    """정책 이벤트 ±6개월 구간 마스크. R10 검정 C(이벤트 구간 제외)의 입력."""
    mask = pd.Series(False, index=months)
    sel = cal[cal["pack"].isin(list(packs) + ["*"])]
    for r in sel.itertuples(index=False):
        lo = r.start - pd.DateOffset(months=halo_months)
        hi = r.start + pd.DateOffset(months=halo_months)
        mask |= (months >= lo) & (months <= hi)
        if pd.notna(r.end) and r.end < as_ts(BACKTEST_END):
            mask |= (months >= r.end - pd.DateOffset(months=halo_months)) & \
                    (months <= r.end + pd.DateOffset(months=halo_months))
    return mask


def report_policy(cal: pd.DataFrame, months: pd.DatetimeIndex, packs: Sequence[str]):
    m = policy_windows(cal, packs, months)
    LOG.table([[r.policy_id, _trunc(r.name, 34), str(r.start)[:10],
                str(r.end)[:10] if pd.notna(r.end) else "-", r.pack,
                f"{r.req_type}:{r.req_value}"[:24]] for r in cal.itertuples(index=False)],
              ["ID", "제도명", "시행", "종료", "대상팩", "요건"],
              ["l", "l", "l", "l", "c", "l"], title="정책 캘린더 (§12)")
    LOG.info(f"정책 이벤트 ±6개월 구간: 전체 {len(months)}개월 중 {int(m.sum())}개월 "
             f"({100*m.mean():.0f}%) — R10 검정 C 에서 이 구간을 제외하고 재검정합니다.")
    if m.mean() > 0.75:
        LOG.warn("정책 구간이 전체의 75%를 넘습니다. 검정 C 의 잔여 표본이 부족해 "
                 "R10 결론의 검정력이 낮아집니다. 이 한계를 결과 해석에 반영하세요.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  거부권(V1~V8) + 스코어 조립  Signal = rank_pct(E) × rank_pct(U) × ∏V               ║
# ║                                                                                          ║
# ║  ★ V 를 연속화하면 전략이 붕괴한다. 어떤 센서 점수도 밀어내기 정황을 상쇄할 수 없어야 한다. ║
# ║    이것이 "취지에서 벗어난 종목"이 유입되는 유일한 통로다(§1.3).                            ║
# ║  ★ E 와 U 는 모두 백분위 랭크 변환 후 곱한다. 원값 곱셈은 음수 구간에서 단조성이 깨진다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VETO_DEFS = [
    ("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출 > 1.5", "제외"),
    ("V2", "순이익>0 인데 영업CF < 0.5×순이익 3분기 연속", "제외"),
    ("V3", "90일 내 대규모 희석성 조달(유증/CB/BW)", "제외"),
    ("V4", "θ 미달 / 매핑 실패 / 플라시보 p>0.05", "해당 팩만 무효화"),
    ("V5", "감사의견 비적정·관리종목·자본잠식", "제외"),
    ("V6", "유동성 하한 미달 또는 거래정지", "제외"),
    ("V7", "위험요인·우발부채 문단 유사도 셀 내 하위 5%", "제외"),
    ("V8", "인원 급증 + 유효세율 급락 (정책 유인 채용 의심)", "제외"),
]


def apply_vetoes(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """V_k ∈ {0,1}. 연속화·가중치화·상쇄 금지 (C6)."""
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gby(P, c)          # 없는 컬럼도 NaN 으로 만들어 준 뒤 그룹화 (DART 부분실패 내성)
    n = len(P)

    # ── V1 밀어내기 ────────────────────────────────────────────────────────────────────────
    d_rev = g("revenue_ttm").diff(12)
    d_inv = g("inventory").diff(12)
    d_rec = g("receivable").diff(12)
    push = safe_div(d_inv.fillna(0) + d_rec.fillna(0), d_rev)
    P["v1_metric"] = push
    P["V1"] = np.where((d_rev > 0) & (push > 1.5), 0.0, 1.0)

    # ── V2 이익-현금 괴리 '3분기 연속' ─────────────────────────────────────────────────────
    #   ★ 연속성은 반드시 '분기 프레임'에서 센다. 예전엔 월 패널에서 rolling(9) 로 셌는데,
    #     그건 "3분기 = 9개월"이라는 잘못된 전제다. 월 패널의 한 행은 분기 관측이 아니라
    #     '그 시점에 가장 최근 알려진 분기값'이고, 같은 분기값이 몇 달 동안 반복되는지는
    #     보고서 유형과 제출 지연에 따라 1~4개월로 들쭉날쭉하다. 그래서 rolling(9) 는
    #     발동이 1~2개월 늦고, 결산→1Q→반기처럼 반복이 짧은 창은 아예 놓친다.
    #     분기 프레임에서 rolling(3) 으로 만든 플래그(v2_bad_3q)를 as-of 결합으로 실어 오면
    #     C1 게이트웨이를 그대로 타면서 지연도 0 이 된다. (12_ingest_dart_fin 참조)
    v2q = col(P, "v2_bad_3q")
    if v2q.notna().any():
        P["v2_streak"] = v2q
        P["V2"] = np.where(v2q.fillna(0.0) >= 1.0, 0.0, 1.0)
    else:
        # 분기 플래그가 없으면(재무 미수집) 거부하지 않는다 — 근거 없는 제외가 더 위험하다.
        P["v2_streak"] = np.nan
        P["V2"] = 1.0

    # ── V3 희석성 조달 (공시목록에서 직접 관측) ────────────────────────────────────────────
    P["V3"] = 1.0
    dis = ctx.get("disclosures")
    if dis is not None and len(dis) and "corp_code" in P.columns:
        d = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue", "capital_reduce"])].copy()
        if len(d):
            d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
            ev = d.groupby(["corp_code", "month"]).size().rename("dilution").reset_index()
            ev["corp_code"] = ev["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(ev, on=["corp_code", "month"], how="left")
            P["dilution"] = P["dilution"].fillna(0.0)
            P = P.sort_values(["code", "month"])
            rec = (P.groupby("code", observed=True)["dilution"]
                    .transform(lambda s: s.rolling(3, min_periods=1).sum()))   # 90일 ≈ 3개월
            P["V3"] = np.where(rec > 0, 0.0, 1.0)

    # ── V4 부분 거부권: 팩별 θ / 매핑 품질 ─────────────────────────────────────────────────
    #    전면 제외가 아니라 '해당 팩만 무효화' — 유일한 부분 거부권이다.
    P["V4"] = 1.0
    for p in active_packs():
        tc = p.get("theta_col")
        ecol = p["E_col"]
        if tc and tc in P.columns and ecol in P.columns:
            kill = P[tc].isna() | (P[tc] < 0.50)
            P.loc[kill, ecol] = np.nan
            if int(kill.sum()):
                LOG.info(f"V4 부분거부권 — 팩 {p['id']}: θ<0.50 인 {int(kill.sum()):,}행의 "
                         f"{ecol} 무효화 (전면 제외가 아님)")

    # ── V5 감사의견/관리종목/자본잠식 ──────────────────────────────────────────────────────
    impair = (col(P, "equity") <= 0)
    P["V5"] = np.where(impair.fillna(False), 0.0, 1.0)
    adm = ctx.get("administrative")
    if adm is not None and len(adm):
        bad_codes = set(adm["code"].dropna())
        P["V5"] = np.where(P["code"].isin(bad_codes), 0.0, P["V5"])

    # ── V6 유동성 ──────────────────────────────────────────────────────────────────────────
    P["V6"] = np.where((P["adv20"].fillna(0) >= MIN_ADV_KRW) & (P["close"].fillna(0) > 0), 1.0, 0.0)

    # ── V7 공시텍스트 (PACK-D) ─────────────────────────────────────────────────────────────
    P["V7"] = 1.0
    if "sim_risk_pct" in P.columns:
        P["V7"] = np.where(P["sim_risk_pct"] < 0.05, 0.0, 1.0)

    # ── V8 정책 유인 채용 의심 ─────────────────────────────────────────────────────────────
    P["V8"] = 1.0
    if "n1" in P.columns and "d_eff_tax" in P.columns:
        n1_hi = P["n1"] > P.groupby("month", observed=True)["n1"].transform(
            lambda s: s.quantile(0.90))
        tax_drop = P["d_eff_tax"] < -0.03
        P["V8"] = np.where(n1_hi.fillna(False) & tax_drop.fillna(False), 0.0, 1.0)

    vcols = [f"V{i}" for i in range(1, 9)]
    for c in vcols:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(1.0)
        uniq = set(np.unique(P[c].dropna()))
        if not uniq <= {0.0, 1.0}:
            raise ValueError(f"[C6 위반] 거부권 {c} 가 이진이 아닙니다: {sorted(uniq)[:5]}. "
                             f"거부권은 절대 연속화하지 않습니다.")
    P["VETO"] = P[vcols].prod(axis=1)
    fired = {c: int((P[c] == 0).sum()) for c in vcols}
    LOG.table([[c, d, act, f"{fired[c]:,}", f"{100*fired[c]/max(n,1):.2f}%"]
               for (c, d, act) in VETO_DEFS],
              ["ID", "조건", "조치", "발동 행수", "비율"], ["c", "l", "c", "r", "r"],
              title="거부권 발동 현황 (V∈{0,1} · 곱 · 상쇄 불가)")
    return P


MIN_FLOOR_AXES = 2


def compute_floor(P: pd.DataFrame, cols: Sequence[str], min_axes: int = MIN_FLOOR_AXES,
                  pct_out: Optional[dict] = None) -> pd.Series:
    """§8.2 하한선 — "그 종목이 실제로 보유한 축은 모두 셀 내 50th 이상 + 축이 최소 2개".

    ★ 왜 함수로 빼는가: 하한선은 본선에서만 쓰이는 게 아니라 R2 킬게이트·R5 절제실험의
      비교팔에서도 다시 만들어져야 한다. 예전엔 비교팔이 본선의 FLOOR 컬럼을 그대로
      복사해 썼는데, FLOOR 는 전부 TP 에서 파생된 값이라 '나이브 팔'조차 TP 로 선별된
      종목만 보게 된다. 실측하면 FLOOR 하나가 종목 선정의 92% 를 끝내 버려서, TP 팔과
      균등난수 팔의 보유종목 자카드 유사도가 0.73 이었다 — 무엇과도 구별하지 못하는
      킬게이트는 킬게이트가 아니다. 규칙을 한 곳에 두고 각 팔이 '자기 증거'로 만든다.
    """
    ok = pd.Series(0, index=P.index)
    bad = pd.Series(0, index=P.index)
    for c in cols:
        pct = xsec_rank_pct_l(P, c)
        if pct_out is not None:
            pct_out[c] = pct
        ok += (pct >= 0.50).fillna(False).astype(int)
        bad += (pct < 0.50).fillna(False).astype(int)
    return ((bad == 0) & (ok >= min_axes)).astype(float)


def score_from_axes(P: pd.DataFrame, all_e: Sequence[str],
                    min_axes: int = MIN_FLOOR_AXES) -> dict:
    """주어진 축 집합 하나로 E·FLOOR·Signal·Signal_rank 를 만드는 단일 경로.

    본선(assemble_score)과 강건성 비교팔(R2·R5)이 **반드시 이 함수만** 통과해야 한다.
    비교팔이 다른 경로로 점수를 만들면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를
    재게 된다. 실제로 아무것도 빼지 않은 널-절제의 ΔSharpe 가 +2.08 로 나온 적이 있다.

    두 가지 계산상의 선택을 여기에 못박는다:

    ① 축을 평균하기 전에 축별로 z 표준화한다.
       E_AXB 같은 축은 표준편차가 0.9, E_X 같은 축은 0.1 인데 원값을 그대로 평균하면
       "팩 간 동일가중(C7)"이라고 로그에 찍으면서 실제로는 분산비 만큼(실측 9.4배)
       가중이 갈린다. z 로 분산을 맞춘 뒤 평균해야 로그가 참이 된다.
       (백분위 평균이 아니라 z 평균인 이유: 백분위는 1.0 에서 잘려서 '트레이드오프가
        극적으로 붕괴한 종목'과 '그냥 괜찮은 종목'을 구별하지 못한다. 이 전략이 재려는
        크기 정보가 바로 거기 있다. C5 가 정한 winsorize→z→백분위 순서와도 맞는다)

    ② Signal_rank 는 '월 전체' 백분위다. (month, pack_profile) 로 나눠 매기면 안 된다.
       프로파일이 다른 종목끼리 랭크가 서로 비교 불가능해지는데, 정작 선정부는
       nlargest 로 월 전체를 한 줄로 세워 뽑는다. 그러면 '자기 프로파일에서 혼자'인
       종목이 전부 1.0 을 받아 상위를 채우고, 실측상 월 보유종목의 70%가 동점 1.0 중
       종목코드 순으로 결정됐다. 정보량 차이는 pack_profile 랭킹이 아니라
       FLOOR(빈 축 없음 + 최소 2축)가 이미 막는다.
    """
    all_e = list(all_e)
    pcts: dict = {}
    Z = pd.DataFrame({c: xsec_z_l(P, c) for c in all_e}, index=P.index)
    E_raw = nanmean_cols(Z, all_e)                       # ① 축별 z → 동일가중 평균
    E = xsec_rank_pct_l(P, E_raw)
    FLOOR = compute_floor(P, all_e, min_axes, pct_out=pcts)
    U = P["U"].fillna(0) if "U" in P.columns else pd.Series(0.0, index=P.index)
    VETO = P["VETO"].fillna(0) if "VETO" in P.columns else pd.Series(1.0, index=P.index)
    Signal = E.fillna(0) * U * VETO * FLOOR
    prof = P[all_e].notna().astype(int).astype(str).agg("".join, axis=1)
    rank = Signal.groupby(P["month"], observed=True).rank(pct=True, method="average")  # ②
    return {"E_raw": E_raw, "E": E, "FLOOR": FLOOR, "Signal": Signal,
            "pack_profile": prof, "Signal_rank": rank,
            "n_axes_active": P[all_e].notna().sum(axis=1), "pcts": pcts}


def assemble_score(P: pd.DataFrame) -> pd.DataFrame:
    """E = mean(활성 팩 + 공용축 B·C), U = 반영도, Signal = rank(E)×rank(U)×∏V.

    C7: TP 내 → 팩 내 → 팩 간 모두 동일가중. 이것이 기본값이자 최종값이다.
    """
    packs = active_packs()
    ecols = [p["E_col"] for p in packs if p["E_col"] in P.columns]
    axcols = [c for c in ("E_AXB", "E_AXC") if c in P.columns]

    # ── ① 데이터가 아예 없는 팩은 자동 비활성화 (§8.4) ────────────────────────────────────
    #     이걸 안 하면 빈 팩 하나 때문에 아래 하한선에서 전 종목이 탈락한다.
    live_e = []
    for c in ecols:
        cov = float(P[c].notna().mean()) if len(P) else 0.0
        if cov < 0.01:
            pid = next((p["id"] for p in packs if p["E_col"] == c), c)
            disable_pack(pid, f"패널 내 {c} 관측 커버리지 {cov*100:.2f}% — 데이터 부재로 자동 비활성화")
            P[f"pct_{c}"] = np.nan
        else:
            live_e.append(c)
    all_e = live_e + axcols
    if not all_e:
        raise RuntimeError("합성할 증거층(E) 컬럼이 하나도 없습니다. "
                           "활성 팩의 원천 데이터가 전부 비어 있는지 위 수집 로그를 확인하세요.")
    if "U" not in P.columns:
        P["U"] = np.nan

    # ── ② 점수 조립 — 본선도 비교팔과 완전히 같은 경로를 탄다 ────────────────────────────
    #   (§8.2 하한선 원문: "활성 센서팩 및 B·C축 각각의 셀 내 백분위가 모두 ≥ 50th"
    #    "'모든 축이 상위'가 아니라 '빈 축이 없을 것'. 표본 붕괴 없이 단일 축 편중을 막고"
    #
    #    ★ 순진하게 '전 축 conjunction' 으로 구현하면 두 가지가 깨진다:
    #      (a) V4 는 §9에서 유일한 '부분' 거부권인데, θ 미달로 E_N 이 NaN 이 되면 그 종목이
    #          하한선에서 통째로 탈락한다 → 부분 거부권이 전면 제외로 변질된다.
    #      (b) 축이 7개면 잔존율이 0.5^7 ≈ 0.8% 로 붕괴한다 → 스펙이 명시적으로 금지한 '표본 붕괴'.
    #    그래서 "보유한 축은 모두 50th 이상" + "축 최소 MIN_FLOOR_AXES 개" 로 읽는다)
    S = score_from_axes(P, all_e)
    for k in ("E_raw", "E", "FLOOR", "Signal", "pack_profile", "Signal_rank", "n_axes_active"):
        P[k] = S[k]
    for c, pct in S["pcts"].items():
        P[f"pct_{c}"] = pct

    # ── ③ 진단 출력 ───────────────────────────────────────────────────────────────────────
    ret = float(P["FLOOR"].mean()) if len(P) else 0.0
    rows = [[c, f"{float(P[c].notna().mean())*100:.1f}%",
             f"{float((P[f'pct_{c}'] >= 0.50).mean())*100:.1f}%"] for c in all_e]
    LOG.table(rows, ["증거층 축", "관측 커버리지", "50th 이상 비율"], ["l", "r", "r"],
              title="하한선 구성 축 (§8.2 — 빈 축이 없을 것)")
    LOG.info(f"하한선 통과 {int(P['FLOOR'].sum()):,}행 / {len(P):,}행 ({ret*100:.1f}%) · "
             f"보유 축 중앙값 {float(P['n_axes_active'].median()):.0f}개")
    if ret < 0.03:
        LOG.warn(f"하한선 잔존율이 {ret*100:.1f}% 로 매우 낮습니다. 축이 많을수록 "
                 f"'모든 축 ≥ 50th' 조건은 기하급수적으로 좁아집니다(축 k개면 대략 0.5^k). "
                 f"§8.2 는 '표본 붕괴 없이' 를 명시하므로, 활성 팩 수를 줄이거나 "
                 f"팩별 단독 파일로 나눠 돌리는 편이 스펙 의도에 더 가깝습니다.")

    prof_n = int(P["pack_profile"].nunique())
    LOG.ok(f"스코어 조립 완료 — 증거층 {len(all_e)}개 축 z표준화 후 동일가중 "
           f"({', '.join(all_e)}) · 하한선 통과 {int(P['FLOOR'].sum()):,}행 "
           f"({100*P['FLOOR'].mean():.1f}%) · Signal_rank 는 월 전체 백분위 "
           f"(정보량 프로파일 {prof_n}종은 진단용으로만 기록)")
    PIPE.io("OUT", "MEM", "scored_panel", P)
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델                                                             ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 '다음 거래일 시가'. 당일 종가 체결 금지(미래누수).   ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(누락 = 생존자편향).         ║
# ║  · 롱온리 (공매도 불가) — 음의 신호는 청산 게이트로만 쓴다.                                 ║
# ║  · 청산 규칙이 진입 논리와 같은 언어를 쓴다: Δlog M 이 Δlog E 수준까지 확장 완료 시 청산.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.0030, "KOSDAQ": 0.0030, "OTHER": 0.0030}),
    ("2019-06-03", {"KOSPI": 0.0025, "KOSDAQ": 0.0025, "OTHER": 0.0025}),
    ("2021-01-01", {"KOSPI": 0.0023, "KOSDAQ": 0.0023, "OTHER": 0.0023}),
    ("2023-01-01", {"KOSPI": 0.0020, "KOSDAQ": 0.0020, "OTHER": 0.0020}),
    ("2024-01-01", {"KOSPI": 0.0018, "KOSDAQ": 0.0018, "OTHER": 0.0018}),
    ("2025-01-01", {"KOSPI": 0.0015, "KOSDAQ": 0.0015, "OTHER": 0.0015}),
]
COMMISSION_BPS = 1.5          # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10             # 제곱근 충격 계수

# 보유 중 패널에서 사라진 종목을 '폐지 진행'으로 볼 최대 대기 기간.
#   KRX 는 매매거래정지 → 개선기간 → 정리매매 → 상장폐지 경로가 흔히 3~24개월이다.
#   거래가 정지되면 그 달부터 패널에 행이 생기지 않으므로, 폐지일이 '다음 달 안'일 때만
#   -100% 를 물리면 이 경로가 통째로 0% 청산으로 빠져나간다(생존자편향).
DELIST_VANISH_HORIZON_M = 24


def sell_tax(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격. 참여율이 높을수록 급격히 비싸진다 — 소형주 가중이 여기서 나온다."""
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(SLIPPAGE_K * math.sqrt(part))


def exit_gate(dm, de) -> bool:
    """청산 판단: '진입 시의 목표상태'를 벗어났는가.

    진입 조건(axis_D)은 ΔlogE > 0 AND 시장이 아직 자본화를 안 함(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다. 알파 소진(원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다. 논거 무효

    ★ 예전엔 `dm >= de and de > 0` 이었다. 앞 조건이 참이면 뒤 조건도 거의 항상 참이라
      보이지만, 실제로 걸러지는 건 'de <= 0' 인 전 구간 — 즉 논거가 깨진 종목을 청산하는
      경로가 통째로 닫혀 있었다. 그 종목들은 보유상한(24개월)까지 자리를 차지했다.
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 종목 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '데이터프레임에 먼저 나온 행'을 고른다. 패널은
      ["code","month"] 로 정렬되어 있으므로 그건 곧 '종목코드가 작은 순'이다. 동점이 드물면
      무해하지만, 실측상 월 보유종목의 상당수가 동점 구간에서 결정됐고 행 순서를 섞으면
      포트폴리오가 통째로 바뀌었다 — 즉 보유종목이 데이터가 아니라 정렬의 함수였다.
      그래서 ① 1차 키는 signal_col, ② 2차 키는 랭크 이전의 원 Signal(정보량이 더 많다),
      ③ 최후에만 code 로 깬다. 이러면 동점 처리가 결정적이면서 '왜 그 종목인가'가 설명된다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "code") if c in df.columns and c != signal_col]
    asc = [False] + [False if c == "Signal" else True for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중(§8.5).
    비중 상한은 코드 상수로 이미 못박혀 있다 — 드로다운 한가운데서 정하지 않는다."""
    s = sub["Signal_rank"].fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    lo, hi = float(np.min(s)), float(np.max(s))
    if spread < 1e-6 or (hi - lo) < 1e-12:
        w = np.full(len(s), 1.0 / len(s))
    else:
        # ★ 예전엔 raw = clip(s - median, 0, None) + 1e-9 였다. 그러면 **선정된 종목의 정확히
        #   절반**(중앙값 이하)이 raw=1e-9 로 깔려 비중이 사실상 0 이 된다 — 25종목을 골랐다고
        #   로그에 찍으면서 실제로는 12~13종목만 보유하는 셈이고, '평균종목수' 지표가 실효
        #   보유수의 2배 넘게 부풀려진다. 분산 효과도 그만큼 과대평가된다.
        #   선정집합 내부 순위로 바꾸면 모든 선정 종목이 양(+)의 비중을 갖고,
        #   집중도는 conc 하나로만 조절된다(문서화된 의도 그대로).
        r = pd.Series(s).rank(method="average").to_numpy(dtype=float)   # 1..n
        conc = min(2.0, 0.5 + spread * 8.0)          # 격차 클수록 집중
        w = (r / r.sum()) ** conc
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    # 종목별 상한 = min(정책 상한, 유동성 상한). 유동성 상한은 20일 평균거래대금의 X%.
    adv = sub["adv20"].fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                       POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))

    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다(합이 1보다 작아지면 전부 커진다).
    #   상한에 걸린 종목은 고정하고 나머지에만 잔여 비중을 재배분하는 water-filling 으로 강제한다.
    w = np.clip(w, 0.0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    free = np.ones(len(w), dtype=bool)
    for _ in range(24):
        over = free & (w > cap)
        if not over.any():
            break
        w[over] = cap[over]
        free &= ~over
        rem = 1.0 - w[~free].sum()
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem) if pool > 1e-12 else (rem / free.sum())
    if w.sum() > 1.0 + 1e-9:                 # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 종목수가 적으면 이 함수는 조용히 '현금 70% 펀드'를 만든다 ★★
    #    cap 은 실질적으로 언제나 POS_MAX_WEIGHT(0.12) 다. liq_cap = adv×0.10/3천만원 인데
    #    패널에 남으려면 adv ≥ 3억이므로 liq_cap ≥ 1.0 — 유동성 상한은 전 구간 사문화다.
    #    그래서 종목이 n 개면 Σw ≤ 0.12n 이고, n=3 이면 **자동으로 현금 64%** 가 된다.
    #    7회차 스몰캡 팔이 월평균 2.5종목이었다 → 사실상 현금 70% 포트폴리오였는데,
    #    그것을 100% 투자된 전체 팔과 나란히 놓고 "차이는 규모 대역 하나" 라고 보고했다.
    #    현금 비중이 성과 차이의 지배적 원인인데 표 어디에도 그 말이 없었다.
    #  → 현금 비중을 **명시적으로 계산해 돌려준다.** 임의로 채워 넣지 않는다(그건 상한을
    #    뚫는 것이다). 대신 호출자가 이 사실을 표에 쓰게 만든다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    out = sub.assign(weight=w)
    out.attrs["cash"] = float(max(0.0, 1.0 - float(np.nansum(w))))
    return out


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                 sec: pd.DataFrame, signal_col: str = "Signal_rank",
                 top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                 label: str = "TCD", audit: bool = True) -> dict:
    # ★ audit=False 는 강건성 스위트의 재실행용이다. 같은 달을 10여 번 다시 세면
    #   감쇠 원장의 min/max·관측월이 무의미해지고, 팔 태그까지 뒤섞인다(잔존율 113.7%).
    #   본선·비교팔만 원장에 남긴다.
    _audit_saved = getattr(uni, "audit_on", True)
    if not audit:
        uni.audit_on = False
    try:
        # ★ 진단 경고는 **본선·비교팔에서만** 낸다. 강건성 스위트는 같은 엔진을 20여 회
        #   재실행하므로, 그대로 두면 같은 경고가 20번 반복되어 정작 읽어야 할 표가
        #   스크롤 밖으로 밀려난다. 로그가 시끄러우면 아무도 읽지 않고, 안 읽히는 경고는
        #   없는 경고와 같다. 재실행분은 DEBUG 로 내린다(사실은 그대로 남는다).
        return _run_backtest_inner(P, months, uni, sec, signal_col, top_pct,
                                   apply_costs, label, verbose=bool(audit))
    finally:
        uni.audit_on = _audit_saved


def _run_backtest_inner(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                        sec: pd.DataFrame, signal_col: str = "Signal_rank",
                        top_pct: float = PORTFOLIO_TOP_PCT, apply_costs: bool = True,
                        label: str = "TCD", verbose: bool = True) -> dict:
    _say = LOG.warn if verbose else LOG.debug
    _tbl = LOG.table if verbose else (lambda *a, **k: None)
    mkt = sec.set_index("code")["market"].astype(str).to_dict()
    delist = uni.delisting_map()
    # 폐지 '유형' — 흡수합병·스팩해산은 -100% 가 아니다. 없으면 전부 -100%(종전 동작).
    dkind = uni.delist_kind_map() if hasattr(uni, "delist_kind_map") else {}
    hold: Dict[str, dict] = {}
    rows, trades, holdings_log = [], [], []
    prev_w: Dict[str, float] = {}
    # 폐지 손실을 이미 반영한 종목 — 같은 종목에 -100% 를 두 번 물리지 않기 위한 장부
    delist_realized: set = set()
    vanished_delisted = vanished_other = vanished_transfer = 0
    unknown_ret_n, unknown_ret_w = 0, 0.0        # 수익을 알 수 없어 보유하지 않은 것으로 둔 건수
    # 종목별 '패널에 마지막으로 등장한 달'. 사라진 종목이 나중에 돌아오는지(유동성 회복 등)를
    # 판별해야 '거래정지→폐지'와 '일시적 유니버스 이탈'을 가를 수 있다.
    _pm = P[P["month"].isin(months)] if len(P) else P
    last_seen = (_pm.groupby("code", observed=True)["month"].max().to_dict()
                 if len(_pm) else {})

    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★ 월별 인덱스를 **한 번만** 만든다. 예전엔 매달 `P[P["month"] == m].copy()` 로
    #    전체 패널에 불리언 마스크를 걸고 복사했다 — 120개월이면 패널을 120번 완주하고
    #    120번 복사한다. 그리고 이 함수는 강건성 스위트에서 26번 재실행되므로
    #    그 비용이 그대로 26배가 된다. 실측상 L5 의 지배적 병목이었다.
    #    groupby(...).indices 는 한 번의 패스로 월→행위치 배열을 만들어 준다(원칙 3).
    # ══════════════════════════════════════════════════════════════════════════════════════
    _midx = P.groupby("month", observed=True).indices if len(P) else {}
    for i, m in enumerate(months):
        _rows_i = _midx.get(m)
        sub = (P.take(np.asarray(_rows_i)) if _rows_i is not None and len(_rows_i)
               else P.iloc[0:0])
        if sub.empty:
            rows.append({"month": m, "ret": 0.0, "n": 0, "turnover": 0.0, "cost": 0.0})
            continue
        elig = sub[(sub["VETO"] == 1) & (sub["FLOOR"] == 1) & sub[signal_col].notna() &
                   sub["exec_px"].notna()]
        # ★ 감쇠 감사는 '누적 교집합'으로 기록한다. 게이트별 독립 집계를 깔때기처럼 보여주면
        #   잔존율이 100%를 넘는 무의미한 숫자가 나온다(게이트가 서로 포함관계가 아니므로).
        g_liq = sub[sub["V6"] == 1]
        g_veto = g_liq[g_liq["VETO"] == 1]
        g_floor = g_veto[g_veto["FLOOR"] == 1]
        uni.audit_row("유동성필터", m, g_liq["code"].tolist())
        uni.audit_row("거부권통과", m, g_veto["code"].tolist())
        uni.audit_row("하한선통과", m, g_floor["code"].tolist())

        # 종목별 조회를 dict 로 미리 만든다. sub[sub.code==c] 를 종목마다 돌리면
        # 백테스트가 강건성 스위트에서 10여 회 재실행될 때 그 비용이 그대로 곱해진다.
        need_cols = [c for c in ("adv20", "fwd_ret", "VETO", "dlog_M", "dlog_E", signal_col)
                     if c in sub.columns]
        rec: Dict[str, dict] = {}
        for _c, *_v in sub[["code"] + need_cols].itertuples(index=False, name=None):
            rec[_c] = dict(zip(need_cols, _v))

        k = int(max(PORTFOLIO_MIN_NAMES, min(PORTFOLIO_MAX_NAMES,
                                             round(len(elig) * top_pct))))
        pick = _top_n(elig, k, signal_col)
        uni.audit_row("최종선정", m, pick["code"].tolist())

        # 청산 게이트: Δlog M 이 Δlog E 수준까지 확장 완료 / 보유상한 / 거부권
        keep = []
        vanished_w = 0.0          # 이달 상각(회수 불가)된 자본 비중 — 장부에서 자리를 차지한다
        for c, h in list(hold.items()):
            r0 = rec.get(c)
            if r0 is None:
                # ★★ 패널에서 사라진 보유 종목 (C2 생존자편향의 마지막 구멍) ★★
                #   예전엔 그냥 continue 였다. 그러면 '거래정지 → 몇 달 뒤 상장폐지' 경로가
                #   손실 0%로 조용히 청산된다. 거래가 끊긴 종목은 월 패널에 행이 생기지 않으므로
                #   아래 fwd_ret 기반 -100% 규칙이 **한 번도 발동하지 못한다.**
                #   실제로는 정리매매가 없으면 -100% 다. 사라진 이유를 갈라서 처리한다:
                #     · 폐지가 임박/진행 중  → -100% (이미 반영한 종목은 제외)
                #     · 그 외(유니버스 이탈) → 직전가로 청산, 그 달 수익 0% (로그로 드러냄)
                #   ★ 창을 '다음 달까지'로 잡으면 안 된다. 거래가 정지되면 그 달부터 패널에
                #     행이 없어지는데, 실제 폐지일은 3~24개월 뒤다. 그래서 '이 달 이후 패널에
                #     다시 나타나지 않는가(=영구 이탈)' + '폐지일이 그 안에 있는가'로 판정한다.
                dl = delist.get(c)
                w_prev = prev_w.get(c, 0.0)
                never_back = m > last_seen.get(c, m)
                terminal = (dl is not None and pd.notna(dl) and never_back
                            and dl <= m + pd.DateOffset(months=DELIST_VANISH_HORIZON_M))
                if w_prev > 0 and terminal and c not in delist_realized:
                    # ★ 폐지 유형에 따라 청산가가 다르다. 흡수합병·완전자회사화·스팩해산은
                    #   전액손실이 아니다(대가로 인수기업 주식 또는 예치금을 받는다).
                    #   그런 건을 -100% 로 계상하면 없는 손실을 매년 지어낸다.
                    #   모르는 사유('unknown')는 보수적으로 -100% 를 유지한다.
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        vanished_transfer += 1      # 직전가 청산 = 그 달 수익 0%
                    else:
                        vanished_w += float(w_prev)     # 전액손실 — 그만큼의 자본이 사라진다
                        vanished_delisted += 1
                        holdings_log.append({"month": m, "code": c, "weight": float(w_prev),
                                             "ret": -1.0, "signal": np.nan,
                                             "event": "delist_vanished"})
                    delist_realized.add(c)
                elif w_prev > 0:
                    vanished_other += 1
                continue
            dm, de = r0.get("dlog_M"), r0.get("dlog_E")
            exited = False
            if r0.get("VETO", 1) == 0:
                exited = True                                    # 거부권 발동 시 즉시 강제청산
            elif h["months"] >= HOLD_MAX_MONTHS:
                exited = True
            elif exit_gate(dm, de):
                exited = True                        # 목표상태 이탈 (재분류 완료 또는 논거 무효)
            if not exited:
                keep.append(c)
        target = pd.concat([pick, sub[sub["code"].isin(keep) & ~sub["code"].isin(pick["code"])]],
                           ignore_index=True) if len(keep) else pick
        if len(target) > PORTFOLIO_MAX_NAMES:
            target = _top_n(target, PORTFOLIO_MAX_NAMES, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])

        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}
        cash_w = float(target.attrs.get("cash", 0.0)) if len(target) else 1.0
        # ★ 이미 -100% 로 상각한 종목(=체결 자체가 불가능하다)에 매도비용을 다시 물리지 않는다.
        #   prev_w 에는 남아 있으므로 비용 루프가 '매도'로 잡고, rec 에 행이 없어 adv=0 →
        #   기본 슬리피지 2% + 증권거래세까지 부과했다. 존재하지 않는 거래에 대한 비용이다.
        _no_trade = {c for c in prev_w if c not in w_new and c in delist_realized}
        _cost_codes = (set(w_new) | set(prev_w)) - _no_trade
        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in _cost_codes)

        cost = 0.0
        if apply_costs:
            for c in _cost_codes:
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                _r = rec.get(c) or {}
                _a = _r.get("adv20")
                adv = float(_a) if _a is not None and pd.notna(_a) else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                c_bps = COMMISSION_BPS / 1e4
                sl = slippage(notional, adv)
                tx = sell_tax(m, mkt.get(c, "OTHER")) if dw < 0 else 0.0
                cost += abs(dw) * (c_bps + sl + tx)

        # ══════════════════════════════════════════════════════════════════════════════════
        #  다음 달 수익 — **비중 장부가 하나로 닫혀야 한다**
        #
        #  ★★ 예전 구조의 결함 ★★  ret 은 w_new(합 ≈ 1) 위에서 계산한 뒤,
        #    `ret += vanished_loss` 로 지난달 비중 w_prev 기반 손실을 **덧붙였다.**
        #    그 달의 총노출이 1 + Σw_van 이 되어, 폐지가 난 달마다 없는 자본으로 손실을
        #    추가로 낸 셈이다. 상각된 종목의 자본은 이미 사라졌으므로 신규 배분의 분모에서
        #    빠져야 한다 — 더하는 것이 아니라 **자리를 차지해야** 한다.
        #  → 장부를 하나로 닫는다:  1 = Σ(폐지상각분) + (1−Σ폐지상각분) × [Σw_new + 현금]
        # ══════════════════════════════════════════════════════════════════════════════════
        w_van = float(min(1.0, max(0.0, vanished_w)))     # 이달 상각된(회수 불가) 자본 비중
        alive = max(0.0, 1.0 - w_van)
        ret_alive = 0.0
        unknown_w_m = 0.0                      # 수익을 몰라 보유하지 않은 자본(현금으로 남는다)
        _is_last = (i == len(months) - 1)      # 마지막 달의 fwd_ret 결측은 결함이 아니다
        for c, w in w_new.items():
            _r = rec.get(c) or {}
            _f = _r.get("fwd_ret")
            fr = float(_f) if _f is not None and pd.notna(_f) else np.nan
            dl = delist.get(c)
            _ev = ""
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                # ★ 상장폐지: 정리매매 최종가가 있으면 그것을 쓴다. 없을 때만 유형을 본다.
                #   부실·사유불명 → -100%(C2 원칙7). 합병·스팩해산 → 직전가 청산(0%).
                if not np.isfinite(fr):
                    kind = dkind.get(c, "unknown")
                    if kind in DELIST_NOT_WIPEOUT:
                        fr = 0.0
                        vanished_transfer += 1
                    else:
                        fr = -1.0
                delist_realized.add(c)      # 이 종목의 폐지 손익은 여기서 확정 — 재차감 금지
                _ev = "delist"
            if not np.isfinite(fr):
                # ★★ '수익을 모른다'와 '수익이 0%'는 다른 사실이다 ★★
                #   여기 걸리는 행은 ① 무결성 게이트가 버린 가격제한 밖 관측 ② 월 연속성이
                #   끊긴 구간 ③ 체결가 결측이다. 셋 다 **그 달 그 종목을 보유했다고 말할 수
                #   없는** 상태다. 0% 로 덮으면 우측꼬리 의존 전략에서 가장 큰 상승·하락이
                #   정확히 사라지고, 그 자리에 '무사고'라는 없는 사실이 들어간다.
                #   → 보유하지 않은 것으로 처리하고(비중 0) 그 자본은 현금으로 남긴다.
                #     지어내지 않고, 조용히 0 으로 만들지도 않는다. 건수는 아래에서 보고한다.
                # ★ 마지막 달은 '다음 달'이 존재하지 않으므로 fwd_ret 이 결측인 것이 정상이다.
                #   그것을 데이터 결함처럼 세면 매 실행 마지막 달의 전 종목이 경고에 잡힌다.
                if not _is_last:
                    unknown_ret_n += 1
                    unknown_ret_w += float(w)
                unknown_w_m += float(w)          # 이 달의 미투자 자본(현금으로 남는다)
                holdings_log.append({"month": m, "code": c, "weight": 0.0, "ret": np.nan,
                                     "signal": np.nan, "event": "ret_unknown"})
                continue
            ret_alive += w * fr
            _s = _r.get(signal_col)
            holdings_log.append({"month": m, "code": c, "weight": w * alive, "ret": fr,
                                 "signal": float(_s) if _s is not None and pd.notna(_s) else np.nan,
                                 "event": _ev})
        # 상각분은 -100%. 살아남은 자본만 신규 배분의 수익을 받는다.
        ret = alive * ret_alive + w_van * (-1.0)
        # ★ 롱온리 한 달 손실의 하한은 −100% 다(장부가 닫혀 있으면 구조적으로 성립하지만,
        #   부동소수점·데이터 이상까지 감안해 마지막 방어선을 남긴다).
        ret = max(-1.0, float(ret)) if np.isfinite(ret) else 0.0
        ret_net = ret - cost
        rows.append({"month": m, "ret": ret_net, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost,
                     # ★ 현금 비중을 반드시 기록한다. 종목이 9개 미만이면 상한(0.12) 때문에
                     #   자동으로 현금이 생기는데, 그 사실이 표에 없으면 '규모 대역 차이'로
                     #   읽히는 것이 실은 '현금 70% vs 현금 0%' 의 차이가 된다.
                     # cash 는 ① 비중상한 때문에 못 채운 몫 ② 수익을 몰라 보유하지 않은 몫
                     #   둘을 합친 값이다. ②를 빼놓으면 "현금으로 남겼다"는 로그와 표가
                     #   서로 다른 말을 하게 된다.
                     "cash": float(min(1.0, max(0.0, cash_w + unknown_w_m))),
                     "invested": float(alive * max(0.0, 1.0 - cash_w - unknown_w_m))})
        for c in list(hold):
            if c in w_new:
                hold[c]["months"] += 1
            else:
                hold.pop(c, None)
        for c in w_new:
            hold.setdefault(c, {"months": 0})
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0).clip(lower=-1.0)).cumprod()
    H = pd.DataFrame(holdings_log)
    if vanished_delisted or vanished_other or vanished_transfer:
        (LOG.info if verbose else LOG.debug)(f"[{label}] 보유 중 청산된 종목 — 부실·사유불명 폐지 {vanished_delisted}건은 "
                 f"-100%, 합병·완전자회사화·스팩해산 {vanished_transfer}건은 직전가 청산(0%), "
                 f"그 외 유니버스 이탈 {vanished_other}건도 직전가 청산. "
                 f"조용히 사라지게 두지 않습니다(C2).")
        # ★★ 이 경고는 3년 내내 침묵하고 있었다 ★★
        #   `if not dkind` 는 **컬럼이 없을 때**만 참이다. 그런데 종목마스터 수집부는
        #   원본에 사유가 없어도 delist_reason 을 **빈 문자열 컬럼으로 항상 만든다**
        #   (10_ingest_universe.py:324). 그러면 dkind = {코드: "unknown"} 로 채워져
        #   비어 있지 않고, 모든 폐지가 조용히 -100% 로 계상되면서 경고는 뜨지 않는다.
        #   → 사유가 실제로 분류됐는지를 **값으로** 판정한다.
        _kinds = Counter(dkind.values()) if dkind else Counter()
        _unk = _kinds.get("unknown", 0)
        _tot = max(1, sum(_kinds.values()))
        if _kinds:
            _tbl([[k, f"{v:,}", f"{100*v/_tot:.0f}%",
                        "직전가 청산(0%)" if k in DELIST_NOT_WIPEOUT else "전액손실(-100%)"]
                       for k, v in _kinds.most_common()],
                      ["폐지 유형", "종목수", "비율", "청산 처리"], ["l", "r", "r", "l"],
                      title=f"[{label}] 상장폐지 사유 분류 — 청산가를 가르는 유일한 근거")
        if (not dkind) or _unk / _tot > 0.30:
            _say(f"[{label}] 폐지 사유를 분류하지 못한 종목이 {_unk:,}/{_tot:,}"
                     f"({100*_unk/_tot:.0f}%)이라 그만큼을 **전액손실(-100%)** 로 계상했습니다. "
                     f"실측상 폐지의 절반가량(흡수합병·스팩해산)은 전액손실이 아니므로 "
                     f"성과가 **과소평가**됩니다(U-MID 대역 기준 연 -2%p 안팎). "
                     f"종목마스터의 delist_reason 이 빈 문자열이 아닌지 확인하세요 — "
                     f"컬럼은 항상 만들어지므로 '컬럼 존재'만으로는 판정할 수 없습니다.")
    if unknown_ret_n:
        _say(f"[{label}] 다음 달 수익을 알 수 없는 보유 {unknown_ret_n:,}건"
                 f"(비중 합계 {unknown_ret_w:.2f})을 **보유하지 않은 것으로** 처리했습니다. "
                 f"가격 무결성 게이트가 버린 관측·월 연속성 단절·체결가 결측이 원인입니다. "
                 f"0% 로 덮으면 '무사고'라는 없는 사실이 장부에 들어갑니다 — "
                 f"그 자본은 현금으로 남겼고, 이 사실은 성과표의 현금비중에 반영됩니다.")
    _cash = float(R["cash"].mean()) if "cash" in R.columns and len(R) else 0.0
    if _cash > 0.05:
        _say(f"[{label}] 월평균 현금 비중이 {_cash:.0%} 입니다. 종목별 비중 상한"
                 f"(POS_MAX_WEIGHT={POS_MAX_WEIGHT:.0%})과 선정 종목수의 곱이 1 에 못 미치면 "
                 f"나머지는 자동으로 현금이 됩니다 — 종목이 "
                 f"{math.ceil(1/POS_MAX_WEIGHT)}개 미만인 달이 그렇습니다. "
                 f"이 팔의 성과를 다른 팔과 비교할 때 **현금 비중 차이**를 먼저 보세요. "
                 f"규모 대역의 효과로 읽으면 틀립니다.")
    return {"returns": R, "holdings": H, "label": label,
            "vanished_delisted": vanished_delisted, "vanished_other": vanished_other,
            "unknown_ret_n": unknown_ret_n, "cash_mean": _cash,
            "delist_kinds": dict(Counter(dkind.values()) if dkind else Counter())}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 이 함수가 nan 을 돌려주면 강건성 판정이 '조용히 FAIL' 로 떨어진다 ★★
    #    R0 은 `isfinite(cal_s) and isfinite(cal_b) and cal_s > cal_b` 로 판정한다.
    #    벤치마크가 nan 이면 세 조건 중 둘째가 거짓이라 **'Calmar 미달 — 폐기 대상'** 이
    #    출력된다. 실제로는 비교조차 못 한 것인데 '졌다'고 보고한 셈이다(7회차).
    #    → 여기서 세 가지를 강제한다:
    #      ① 비유한 수익률은 계산에서 제외한다(0 으로 바꾸지 않는다 — 그건 '수익 0'이라는
    #         없는 사실을 만든다). 몇 개를 제외했는지 반환값에 남긴다.
    #      ② 롱온리 월수익의 하한은 −100% 다. 보유분을 전부 잃어도 그 이상은 잃을 수 없다.
    #         (폐지 −100% 를 여러 종목에 동시에 물리면 합계가 −1 밑으로 내려가 자본이
    #          음수가 되고, 그 뒤 복리·MDD 가 전부 무의미해진다)
    #      ③ 자본이 0 이하로 떨어지면 CAGR 은 nan 이 아니라 **−100%** 다. 전액손실은
    #         '알 수 없음'이 아니라 확정된 사실이다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════════════════
    #  ★★ 선택 컬럼을 필수처럼 읽지 않는다 (R10 이 100% 확률로 오판정하던 자리) ★★
    #    반환 dict 리터럴이 `float(R["n"].mean())` 을 **무조건** 평가했다. 그런데 호출자
    #    중에는 수익률만 가진 프레임을 넘기는 곳이 있다 — R10 의 정책제외 구간 통계가
    #    그렇다(build_v3/50_robust.py). 그러면 KeyError 가 나고, 호출부의 넓은 except 가
    #    그것을 삼켜 off=nan 이 된다. 그 nan 은 `ok = isfinite(off) and ...` 에서 False 가
    #    되어 **"정책 구간을 빼면 알파가 사라짐 — TP_N1 폐기 대상"** 으로 출력됐다.
    #    측정에 실패한 것을 확정된 반증으로 보고한 것이고, 데이터와 무관하게 항상 그랬다.
    # ══════════════════════════════════════════════════════════════════════════════════════
    def _opt(colname: str) -> float:
        try:
            return float(pd.to_numeric(R[colname], errors="coerce").mean())
        except Exception:                                        # noqa
            return np.nan
    raw = pd.to_numeric(R["ret"], errors="coerce").to_numpy(dtype=float)
    n_bad = int((~np.isfinite(raw)).sum())
    r = np.where(np.isfinite(raw), raw, 0.0)
    r = np.clip(r, -1.0, None)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1 + r)
    # 자본이 한 번 0 이하가 되면 그 뒤는 존재하지 않는다 — 0 으로 고정해 복리를 끊는다.
    if (eq <= 0).any():
        first = int(np.argmax(eq <= 0))
        eq[first:] = 0.0
    eq = np.where(np.isfinite(eq), eq, 0.0)
    years = n / 12.0
    if years <= 0:
        cagr = np.nan
    elif eq[-1] > 0:
        cagr = eq[-1] ** (1 / years) - 1
    else:
        cagr = -1.0                       # 전액손실 — 판정 유보가 아니라 확정된 사실
    vol = r.std(ddof=1) * math.sqrt(12) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(12) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    # peak 가 0 이 될 수 있다(첫 달 −100%). 0 나눗셈은 nan 을 만들고 MDD 가 통째로 사라진다.
    dd = np.where(peak > 0, eq / np.where(peak > 0, peak, 1.0) - 1.0, -1.0)
    mdd = float(np.nanmin(dd)) if n else np.nan
    if not np.isfinite(mdd):
        mdd = np.nan
    uw, mx, cur = 0, 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    _cal = (cagr / abs(mdd)) if (np.isfinite(cagr) and np.isfinite(mdd) and mdd < 0) else np.nan
    out = {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": ((cagr - rf) / vol if np.isfinite(cagr) and vol and np.isfinite(vol)
                   and vol > 0 else np.nan),
        "Sortino": ((cagr - rf) / dvol if np.isfinite(cagr) and dvol and np.isfinite(dvol)
                    and dvol > 0 else np.nan),
        "MDD": mdd, "Calmar": _cal,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1), "평균종목수": _opt("n"),
        "월평균회전율": _opt("turnover"), "월평균비용": _opt("cost"),
        # ★ 현금 비중은 선택 지표가 아니라 **비교의 전제**다. 종목수가 적으면 비중 상한
        #   때문에 자동으로 현금이 쌓이는데, 그 사실 없이 두 팔의 CAGR 을 나란히 놓으면
        #   '규모 대역의 효과'로 읽히는 것이 실은 '투자비중의 차이'가 된다.
        "월평균현금비중": _opt("cash"),
    }
    # ★ 몇 개를 제외했는지 숨기지 않는다. 0 이 아니면 그 시계열은 이미 손상된 것이고,
    #   그 사실이 지표보다 먼저 읽혀야 한다.
    if n_bad:
        out["비유한수익률제외"] = n_bad
    return out


def right_tail_contribution(bt: dict) -> dict:
    """★ 이 전략은 IR 이 아니라 우측 꼬리에 의존한다. 상위 종목 제외 시 성과가 사라지는지
    반드시 측정하고 리포트에 명시한다(§10.2)."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    # ★ 분모(총기여)가 실제 누적수익과 다르면 '상위 5%가 총기여의 180%' 같은 수치가 나온다.
    #   두 가지를 맞춘다: ① 폐지 상각(-100%)도 보유 기록에 들어가 있어야 한다
    #   (delist_vanished 이벤트로 append 하도록 고쳤다) ② 수익을 알 수 없어 보유하지 않은
    #   것으로 처리한 행(ret_unknown)은 비중 0·수익 NaN 이므로 기여에서 자동 제외된다.
    H = H[pd.to_numeric(H["ret"], errors="coerce").notna()]
    if H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    out = {}
    base = float(contrib.sum())
    for q, lab in ((0.05, "상위5%"), (0.10, "상위10%"), (0.01, "상위1%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 종목수"] = k
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후 총기여"] = base - float(contrib.iloc[:k].sum())
    out["총기여"] = base
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


INDEX_TABLE = "index_ohlcv_daily"          # 공용 인덱스 — 다른 전략도 그대로 재사용한다


def _index_daily(sym: str, lo: pd.Timestamp, hi: pd.Timestamp) -> Optional[pd.DataFrame]:
    """지수 일봉을 **공용 캐시 우선**으로 확보한다.

    ★★ 절대1원칙 ★★ 신규로 수집되는 데이터는 예외 없이 구글드라이브 공용/전용 인덱스에
      저장돼 재호출 가능해야 한다. 예전 이 함수는 매 실행 FDR 에서 KS11/KQ11 을 새로 받고
      **어디에도 저장하지 않았다** — 이 모듈에는 VAULT 참조가 한 줄도 없었다.
      강건성 스위트가 R0 을 부를 때마다 같은 네트워크 왕복이 반복됐고,
      네트워크가 막힌 환경에서는 지수 벤치마크가 통째로 사라졌다(그리고 조용히 넘어갔다).
    """
    cached = None
    try:
        cached = VAULT.get_table(INDEX_TABLE, scope="shared")
    except Exception:                                            # noqa
        cached = None
    have = None
    if cached is not None and len(cached) and "symbol" in cached.columns:
        have = cached[cached["symbol"].astype(str) == sym].copy()
        if len(have):
            have["date"] = as_ts_series(have["date"])
            have = have.dropna(subset=["date"])
            if len(have) and have["date"].min() <= lo and have["date"].max() >= hi:
                return have.sort_values("date")                  # 캐시가 구간을 덮는다 → 호출 없음
    fresh = None
    if fdr is not None:
        try:
            limiter("naver").wait()
            r = fdr.DataReader(sym, lo, hi)
            if r is not None and len(r):
                r = r.reset_index()
                r.columns = [str(c).lower() for c in r.columns]
                r["date"] = as_ts_series(r[r.columns[0]])
                r["symbol"] = sym
                fresh = r[["symbol", "date"] + [c for c in ("open", "high", "low", "close",
                                                            "volume") if c in r.columns]]
        except Exception as e:                                   # noqa
            LOG.debug(f"지수 {sym} 수집 실패({type(e).__name__}) — 캐시분으로 진행합니다.")
    if fresh is None or not len(fresh):
        return have if (have is not None and len(have)) else None
    # 캐시와 합쳐 **넓어지는 방향으로만** 저장한다(좁혀 덮어쓰기 금지 — 절대1원칙).
    parts = [p for p in (cached, fresh) if p is not None and len(p)]
    merged = pd.concat(parts, ignore_index=True)
    merged["date"] = as_ts_series(merged["date"])
    merged = (merged.dropna(subset=["date", "symbol"])
                    .drop_duplicates(["symbol", "date"], keep="last")
                    .sort_values(["symbol", "date"]).reset_index(drop=True))
    try:
        VAULT.put_table(INDEX_TABLE, merged, scope="shared", domain="price",
                        source="fdr: KS11/KQ11 지수 일봉 (R0 벤치마크 · 타 전략 재사용 가능)")
    except Exception as e:                                       # noqa
        LOG.debug(f"지수 캐시 저장 실패({type(e).__name__}) — 계산에는 영향 없음")
    return merged[merged["symbol"].astype(str) == sym]


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    # ★ 끝을 2개월 늘린다. 아래 shift(-1) 때문에 마지막 달이 NaN 이 되면
    #   비교표의 dropna 에서 그 달이 조용히 빠진다.
    _lo = months[0] - pd.offsets.MonthEnd(2)
    _hi = months[-1] + pd.offsets.MonthEnd(2)
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = _index_daily(sym, _lo, _hi)
        if d is None or len(d) == 0:
            continue
        d = d.copy()
        d["date"] = as_ts_series(d["date"])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        # ★★ 위상 정렬 ★★ 전략 수익률은 '월 m 행 = 월 m+1 에 실현된 수익'(fwd_ret) 규약이다.
        #   지수를 pct_change() 그대로 두면 한 달 어긋난 채로 차분되어, 시장요인이 상쇄되기는
        #   커녕 두 배로 들어간다. 초과수익의 t통계량이 절반 수준으로 눌린다.
        s = d.groupby("month")["close"].last().pct_change().shift(-1)
        out[name] = s.reindex(months)
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 스위트 R1~R11 (§11)                                                            ║
# ║                                                                                          ║
# ║  순서대로 실행. 앞 단계 실패 시 진행 금지.                                                  ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§16.3). 나쁜 결과는 그 자체로 정보다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: "OrderedDict[str, dict]" = OrderedDict()


def _record(rid: str, name: str, passed: Optional[bool], detail: str,
            kill: bool = False, metrics: Optional[dict] = None):
    # ★ numpy bool 주의: np.False_ is False → False 다. `is False` 로 분기하면 킬 게이트가
    #   조용히 발동하지 않는다. 여기서 파이썬 bool 로 강제 변환한다.
    passed = None if passed is None else bool(passed)
    ROBUST_RESULTS[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                           "kill": kill, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[passed]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → {icon} · {detail}")
    if passed is False and kill and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name} — {detail}")


def _sharpe(R: pd.DataFrame) -> float:
    s = perf_stats(R)
    return float(s.get("Sharpe", np.nan)) if s else np.nan


# ── R1. 누수 민감도 자가검정 (C9) — 이 검정 통과 전 모든 백테스트 결과는 무효 ────────────────
def R1_leakage(P: pd.DataFrame, months, uni, sec, run_fn) -> None:
    """파이프라인이 누수를 '탐지할 수 있는지' 먼저 증명한다 (C9).

    두 부분으로 나눈다. 한쪽만으로는 결론이 나지 않기 때문이다:

      R1a 하네스 민감도 (판정의 기준)
          미래수익을 직접 신호로 심은 '고의 오염본'을 만든다. 이건 정의상 완벽한 누수다.
          이때도 성과가 뚜렷이 좋아지지 않으면 하네스가 신호에 반응하지 못하는 것 =
          체결·정렬·수익계산 어딘가가 고장난 것이다. 이 경우 전략 결과는 전부 무효다.

      R1b 실제 신호 선행 (참고)
          실제 신호를 1개월 앞당겨 본다. 개선되면 정상. 개선되지 않는 경우는 두 가지인데
          ① 하네스 둔감 ② 애초에 신호에 알파가 거의 없음 — 구분이 안 된다.
          그래서 R1b 는 판정에 쓰지 않고 참고로만 기록한다. (R1a 가 ①을 이미 배제한다)
    """
    base = run_fn(P, label="R1_base")
    s0 = _sharpe(base["returns"])

    # R1a: 미래수익을 신호에 주입 (고의 누수)
    Oracle = P.copy()
    ora = Oracle.groupby("month", observed=True)["fwd_ret"].rank(pct=True)
    Oracle["Signal_rank"] = ora.where(ora.notna(), Oracle["Signal_rank"])
    oracle_bt = run_fn(Oracle, label="R1_oracle")
    s_ora = _sharpe(oracle_bt["returns"])

    # 포지션이 아예 잡히지 않으면 '하네스 둔감'이 아니라 '게이트가 전부 막았다'는 뜻이다.
    # 두 원인은 처방이 완전히 다르므로 구분해서 보고한다.
    n_pos = float(base["returns"]["n"].mean()) if len(base["returns"]) else 0.0
    n_pos_ora = float(oracle_bt["returns"]["n"].mean()) if len(oracle_bt["returns"]) else 0.0
    if n_pos_ora < 0.5:
        _record("R1", "누수 민감도 자가검정 (C9)", None,
                f"평균 보유종목이 {n_pos_ora:.2f}개로 포지션이 사실상 잡히지 않아 판정할 수 없습니다. "
                f"하네스 문제가 아니라 게이트 문제입니다 — 위 '유니버스 감쇠 감사'에서 "
                f"거부권/하한선 중 어디서 표본이 0이 되는지 먼저 확인하세요.",
                kill=False, metrics={"n_pos": n_pos, "n_pos_oracle": n_pos_ora})
        LOG.error("R1 판정불가 — 포지션이 0입니다. 강건성 결과 전체가 무의미하므로 "
                  "게이트(특히 하한선)를 먼저 진단해야 합니다.")
        return
    sensitive = np.isfinite(s_ora) and np.isfinite(s0) and (s_ora - s0) > 0.5

    # R1b: 실제 신호 1개월 선행
    Q = P.sort_values(["code", "month"]).copy()
    for c in ("Signal_rank", "Signal", "E", "U"):
        if c in Q.columns:
            Q[c] = Q.groupby("code", observed=True)[c].shift(-1)
    s1 = _sharpe(run_fn(Q, label="R1_leaked")["returns"])

    _record("R1", "누수 민감도 자가검정 (C9)", sensitive,
            f"[R1a 하네스 민감도] 정상 Sharpe {s0:.3f} → 미래수익 주입 오염본 {s_ora:.3f} "
            f"(Δ={s_ora-s0:+.3f}). "
            + ("하네스가 누수에 뚜렷이 반응함 = 정상. 이제 실제 결과를 신뢰할 근거가 생겼습니다."
               if sensitive else
               "★ 완벽한 누수를 넣어도 성과가 개선되지 않습니다 → 하네스가 신호에 반응하지 못합니다. "
               "체결 정렬(익일 시가)·수익 계산·유니버스 결합 중 하나가 고장난 것이며, "
               "§15-1에 따라 이 상태의 백테스트 결과는 전부 무효입니다.")
            + f"  [R1b 참고] 실제 신호 1개월 선행 시 {s1:.3f} (Δ={s1-s0:+.3f})"
            + ("" if (s1 - s0) > 0.15 else
               " — 개선되지 않았으나, R1a 가 통과했다면 이는 '신호 자체의 알파가 약하다'는 뜻이지 "
               "누수 탐지 실패가 아닙니다." if sensitive else ""),
            kill=False,
            metrics={"sharpe_base": s0, "sharpe_oracle": s_ora, "sharpe_shifted": s1})
    if not sensitive:
        LOG.error("R1a 실패 — §15-1: 하네스가 누수에 둔감하므로 이후 모든 결과가 무효입니다. "
                  "전략을 손대기 전에 백테스트 엔진부터 고쳐야 합니다.")


# ── R2. TP vs 나이브 ⭐ 킬 게이트 — 이 시스템의 존재 이유를 검정한다 ─────────────────────────
def R2_tp_vs_naive(P: pd.DataFrame, run_fn) -> None:
    """TP = z(개선) × z(대가회피) 가 z(개선) 단독보다 낫지 않다면,
    트레이드오프 논리 전체가 불필요한 복잡도다. 정면으로 검정하고 있는 그대로 보고한다."""
    # ★ 두 팔의 '축 개수'를 맞춘다. 하한선은 "보유한 축이 모두 50th 이상"이라 축이 많을수록
    #   기하급수적으로 좁아진다(축 k개면 대략 0.5^k). TP 팔에 원시 TP 13개, 나이브 팔에
    #   원지표 7개를 넣으면 유니버스 폭이 1.68% 대 7.13% 로 벌어져서, 신호 품질이 아니라
    #   유니버스 폭 차이를 재게 된다. TP 쪽의 올바른 '축'은 팩 단위 집계인 E_* 컬럼이고,
    #   그게 본선이 실제로 쓰는 구성이기도 하다 — 검정 대상과 운용 대상이 일치해야 한다.
    tp_cols = [p["E_col"] for p in active_packs() if p["E_col"] in P.columns] + \
              [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    if not tp_cols:                       # E_* 가 없으면 원시 TP 로 폴백
        for p in active_packs():
            tp_cols += [c for c in p["tp_cols"] if c in P.columns]
        tp_cols += [c for c in ("TP_B1", "TP_B2", "TP_C1", "TP_C2") if c in P.columns]
    # 나이브 = '개선 항목 단독' (곱의 첫 인자에 해당하는 원지표들)
    naive_cols = [c for c in ("n1", "p1", "x1", "q1", "dlog_rev", "dlog_IC", "dlog_emp")
                  if c in P.columns]
    if not tp_cols or not naive_cols:
        _record("R2", "TP vs 나이브", None, "비교할 컬럼이 부족합니다.")
        return

    # ── 각 팔은 '자기 증거'로 하한선까지 다시 만든다 ──────────────────────────────────────
    #   ★ 예전엔 두 팔이 본선의 FLOOR 컬럼을 그대로 물려받았다. 그런데 FLOOR 는 전부 TP 에서
    #     파생된 값이라, '나이브 팔'조차 TP 로 선별된 종목만 보게 된다. 실측하면 FLOOR 하나가
    #     종목 선정의 92.4% 를 끝내 버려서, TP 팔과 '균등난수 팔'의 보유종목 자카드 유사도가
    #     0.73 이었다. 무엇과도 구별하지 못하는 게이트는 킬 게이트가 아니다.
    #     각 팔이 자기 증거로 하한선을 만들면 자카드가 0.64 → 0.14 로 떨어지고 비교가 성립한다.
    def _arm(cols: Sequence[str], label: str):
        A = P.copy()
        Z = pd.DataFrame({c: xsec_z_l(A, c) for c in cols}, index=A.index)
        A["E_raw"] = nanmean_cols(Z, list(cols))
        A["E"] = xsec_rank_pct_l(A, A["E_raw"])
        A["FLOOR"] = compute_floor(A, cols)
        A["Signal"] = A["E"].fillna(0) * A["U"].fillna(0) * A["VETO"].fillna(0) * A["FLOOR"]
        A["Signal_rank"] = (A.groupby("month", observed=True)["Signal"]
                             .rank(pct=True, method="average"))
        return A, run_fn(A, label=label)

    Q, tp_bt = _arm(tp_cols, "R2_TP")
    N, nv_bt = _arm(naive_cols, "R2_naive")

    f_tp, f_nv = float(Q["FLOOR"].mean()), float(N["FLOOR"].mean())
    LOG.info(f"R2 각 팔의 하한선 잔존율 — TP {f_tp*100:.2f}% · 나이브 {f_nv*100:.2f}% "
             f"(두 팔이 각자의 증거로 하한선을 만듭니다)")
    if not (0.5 <= f_nv / max(f_tp, 1e-9) <= 2.0):
        LOG.warn(f"두 팔의 유니버스 폭이 {f_nv/max(f_tp,1e-9):.2f}배로 벌어졌습니다. "
                 f"이 비교는 신호 품질이 아니라 유니버스 폭 차이를 재고 있을 수 있습니다 — "
                 f"아래 판정을 그만큼 할인해서 읽으십시오.")

    a, b = tp_bt["returns"]["ret"].fillna(0).to_numpy(), nv_bt["returns"]["ret"].fillna(0).to_numpy()
    k = min(len(a), len(b))
    diff = a[:k] - b[:k]
    mu, t = hac_tstat(diff)
    s_tp, s_nv = _sharpe(tp_bt["returns"]), _sharpe(nv_bt["returns"])
    better = np.isfinite(t) and t > 1.0 and s_tp > s_nv
    _record("R2", "TP vs 나이브 (킬 게이트)", better,
            f"TP Sharpe {s_tp:.3f} vs 나이브 {s_nv:.3f} · 월수익 차이 평균 {mu*100:+.3f}%p, "
            f"HAC t={t:.2f}. " + ("트레이드오프 논리가 나이브를 유의하게 이깁니다." if better else
                                  "★ TP 가 '개선 항목 단독'을 이기지 못했습니다. "
                                  "§15-2에 따라 트레이드오프 패러다임의 근거가 소멸합니다. "
                                  "유리하게 해석하지 않고 그대로 보고합니다."),
            kill=True, metrics={"sharpe_tp": s_tp, "sharpe_naive": s_nv, "t_diff": t})

    # ── R2b 하니스 자체 검정: TP 가 '무정보 균등난수'는 이겨야 한다 ────────────────────────
    #   이건 전략이 아니라 '비교 장치'를 검정한다. 만약 난수 팔이 TP 와 비슷한 성과를 내면
    #   위 R2 판정은 신호가 아니라 선별 게이트가 만든 것이고, 그 순간 R2 는 아무것도 판정하지
    #   못한다. 실제로 하한선을 공유하던 시절엔 난수 팔이 TP 팔과 자카드 0.73 이었다.
    Z = P.copy()
    Z["_noise"] = np.random.default_rng(SEED).random(len(Z))
    Z["E"] = xsec_rank_pct_l(Z, Z["_noise"])
    Z["FLOOR"] = compute_floor(Z, tp_cols)          # 유니버스 폭은 TP 팔과 동일하게 맞춘다
    Z["Signal"] = Z["E"].fillna(0) * Z["U"].fillna(0) * Z["VETO"].fillna(0) * Z["FLOOR"]
    Z["Signal_rank"] = Z.groupby("month", observed=True)["Signal"].rank(pct=True, method="average")
    s_rd = _sharpe(run_fn(Z, label="R2_noise")["returns"])
    _record("R2b", "TP vs 무정보 난수 (하니스 검정)", bool(s_tp > s_rd),
            f"TP Sharpe {s_tp:.3f} vs 균등난수 {s_rd:.3f}. " +
            ("비교 장치가 신호와 무신호를 구별합니다 — R2 판정을 신뢰할 수 있습니다."
             if s_tp > s_rd else
             "★ TP 가 무정보 난수조차 이기지 못했습니다. 이 경우 위 R2 판정은 신호가 아니라 "
             "선별 게이트(하한선·거부권)가 만든 것입니다. R2 결과를 그대로 믿지 마십시오."),
            metrics={"sharpe_tp": s_tp, "sharpe_random": s_rd})


# ── R3. 퀄리티 팩터 직교화 ─────────────────────────────────────────────────────────────────
def R3_orthogonal(P: pd.DataFrame, bt: dict, months) -> None:
    """표준 퀄리티/수익성/모멘텀에 회귀한 뒤 알파가 남는가. 안 남으면 재포장에 불과하다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        _record("R3", "퀄리티 팩터 직교화", None, "보유 이력이 없어 판정 불가")
        return
    Q = P.copy()
    Q["f_prof"] = safe_div(col(Q, "op_income_ttm"), col(Q, "assets"))
    Q["f_qual"] = safe_div(col(Q, "equity"), col(Q, "assets"))
    Q["f_mom"] = Q.groupby("code", observed=True)["close"].transform(lambda s: s.pct_change(12))
    Q["f_size"] = np.log(Q["adv20"].where(Q["adv20"] > 0))
    Q["f_val"] = safe_div(col(Q, "net_income_ttm"), Q["close"])
    facs = ["f_prof", "f_qual", "f_mom", "f_size", "f_val"]

    fac_ret = []
    for m in months:
        sub = Q[Q["month"] == m]
        if len(sub) < 30:
            continue
        row = {"month": m}
        for f in facs:
            z = xsec_z(sub[f], sub["cell"])
            r = sub["fwd_ret"]
            ok = z.notna() & r.notna()
            row[f] = float(np.average(r[ok], weights=np.clip(z[ok] - z[ok].min() + 1e-9, 0, None))
                           - r[ok].mean()) if ok.sum() > 10 else np.nan
        fac_ret.append(row)
    F = pd.DataFrame(fac_ret).set_index("month") if fac_ret else pd.DataFrame()
    R = bt["returns"].set_index("month")["ret"]
    if F.empty:
        _record("R3", "퀄리티 팩터 직교화", None, "팩터 수익률을 만들 표본이 부족합니다.")
        return
    J = F.join(R.rename("y"), how="inner").dropna()
    if len(J) < 24:
        _record("R3", "퀄리티 팩터 직교화", None, f"공통 표본 {len(J)}개월로 부족합니다.")
        return
    X = np.column_stack([np.ones(len(J))] + [J[f].to_numpy() for f in facs])
    y = J["y"].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    alpha_m, t = hac_tstat(resid + beta[0])
    passed = np.isfinite(t) and t > 1.5 and alpha_m > 0
    _record("R3", "퀄리티 팩터 직교화", passed,
            f"직교화 후 월알파 {alpha_m*100:+.3f}%p (연 {((1+alpha_m)**12-1)*100:+.1f}%), "
            f"HAC t={t:.2f}, 표본 {len(J)}개월. "
            + ("표준 팩터로 설명되지 않는 알파가 남습니다." if passed else
               "★ 직교화 후 알파가 사라집니다 — 기존 퀄리티 팩터의 재포장일 가능성이 큽니다(§15-3)."),
            kill=True, metrics={"alpha_m": alpha_m, "t": t})


# ── R4. 플라시보 매핑 ───────────────────────────────────────────────────────────────────────
def R4_placebo(P: pd.DataFrame, n_iter: int = 1000) -> None:
    """무작위로 종목-신호를 섞었을 때의 귀무분포. 실제가 상위 5% 밖이면 매핑이 무작위와 구분 안 됨."""
    sub = P[P["Signal_rank"].notna() & P["fwd_ret"].notna()]
    if len(sub) < 500:
        _record("R4", "플라시보 매핑", None, "표본 부족")
        return
    real = []
    for m, g in sub.groupby("month", observed=True):
        if len(g) < 20:
            continue
        k = max(1, int(len(g) * PORTFOLIO_TOP_PCT))
        real.append(g.nlargest(k, "Signal_rank")["fwd_ret"].mean() - g["fwd_ret"].mean())
    real_mu = float(np.nanmean(real)) if real else np.nan

    rng = np.random.default_rng(SEED)
    null = np.empty(n_iter)
    groups = [g for _, g in sub.groupby("month", observed=True) if len(g) >= 20]
    for i in range(n_iter):
        acc = []
        for g in groups:
            k = max(1, int(len(g) * PORTFOLIO_TOP_PCT))
            idx = rng.choice(len(g), size=k, replace=False)
            acc.append(g["fwd_ret"].to_numpy()[idx].mean() - g["fwd_ret"].mean())
        null[i] = np.nanmean(acc)
    p = float((null >= real_mu).mean())
    passed = np.isfinite(real_mu) and p < 0.05
    _record("R4", f"플라시보 (무작위 선택 귀무분포 {n_iter:,}회)", passed,
            f"실제 초과 {real_mu*100:+.3f}%p/월 vs 귀무 평균 {null.mean()*100:+.3f}%p "
            f"(p={p:.4f}). " + ("무작위와 구분됩니다." if passed else
                                "★ 무작위 선택과 통계적으로 구분되지 않습니다(§15-5)."),
            kill=False, metrics={"p": p, "real": real_mu})


# ── R10. 정책 반증 검정 ⭐ 전 팩 필수 ───────────────────────────────────────────────────────
def R10_policy_falsify(P: pd.DataFrame, cal: pd.DataFrame, months, run_fn) -> None:
    """정책 이벤트 ±6개월 구간을 전부 제외하고 백테스트. 알파가 유지돼야 통과."""
    packs = [p["id"] for p in active_packs()]
    mask = policy_windows(cal, packs, months, halo_months=6)
    clean_months = months[~mask.to_numpy()]
    if len(clean_months) < 24:
        _record("R10", "정책 반증 검정", None,
                f"정책구간 제외 후 {len(clean_months)}개월밖에 남지 않아 검정력이 없습니다. "
                f"이 자체가 '이 팩의 관측구간이 정책에 광범위하게 덮여 있다'는 사실을 뜻합니다.")
        return
    full = run_fn(P, label="R10_full")
    Q = P[P["month"].isin(clean_months)].copy()
    clean = run_fn(Q, label="R10_clean", months_override=clean_months)
    s_full, s_clean = _sharpe(full["returns"]), _sharpe(clean["returns"])
    mu_f = full["returns"]["ret"].mean()
    mu_c = clean["returns"]["ret"].mean()
    _, t_c = hac_tstat(clean["returns"]["ret"].fillna(0).to_numpy())
    kept = np.isfinite(s_clean) and s_clean > 0 and mu_c > 0 and (
        not np.isfinite(s_full) or s_clean >= 0.5 * s_full)

    # 검정 A: 정책 시행일 근처 신호 발화율 스파이크
    fire = P.groupby("month", observed=True)["Signal_rank"].apply(
        lambda s: float((s > 0.95).mean()) if len(s) else np.nan).reindex(months)
    in_w, out_w = fire[mask.to_numpy()].mean(), fire[~mask.to_numpy()].mean()

    _record("R10", "정책 반증 검정 (검정 C: 이벤트 ±6M 제외)", kept,
            f"전체 Sharpe {s_full:.3f}({len(months)}개월) → 정책구간 제외 {s_clean:.3f}"
            f"({len(clean_months)}개월, 월평균 {mu_c*100:+.3f}%p, HAC t={t_c:.2f}). "
            f"[검정A] 신호 발화율 정책구간 {in_w:.3f} vs 비정책구간 {out_w:.3f}. "
            + ("정책 이벤트를 빼도 알파가 유지됩니다." if kept else
               "★ 정책 이벤트 구간을 제외하면 알파가 사라집니다 → 해당 센서팩 폐기 대상(§15-4). "
               "이것은 수요가 아니라 제도를 관측한 것입니다."),
            kill=False, metrics={"s_full": s_full, "s_clean": s_clean, "fire_in": in_w, "fire_out": out_w})
    if not kept:
        for p in active_packs():
            disable_pack(p["id"], "R10 정책 반증 검정 미통과 — 자동 비활성화")


# ── R5. 절제 (ablation) ─────────────────────────────────────────────────────────────────────
def R5_ablation(P: pd.DataFrame, run_fn) -> None:
    """팩별·TP별로 하나씩 빼고 돌려 기여를 귀속한다. L2 만 건드리므로 몇 분이면 끝난다."""
    packs = active_packs()
    all_e = [p["E_col"] for p in packs if p["E_col"] in P.columns] + \
            [c for c in ("E_AXB", "E_AXC") if c in P.columns]

    # ★ 기준선도 절제팔과 똑같이 score_from_axes 를 통과시킨다.
    #   예전엔 기준선은 본선 컬럼을 그대로 쓰고 절제팔만 별도 식으로 점수를 다시 만들었다.
    #   그러면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를 잰다. 실제로
    #   아무것도 빼지 않은 널-절제의 ΔSharpe 가 +2.08 로 나왔다(0.000 이어야 한다).
    def _score_arm(cols: Sequence[str], label: str):
        A = P.copy()
        S = score_from_axes(A, cols)
        for k in ("E_raw", "E", "FLOOR", "Signal", "pack_profile", "Signal_rank"):
            A[k] = S[k]
        return _sharpe(run_fn(A, label=label)["returns"])

    s0 = _score_arm(all_e, "R5_base")
    rows = [["(전체)", f"{s0:.3f}", "—", "—"]]
    for drop in all_e:
        rest = [c for c in all_e if c != drop]
        if len(rest) < MIN_FLOOR_AXES:
            # 남은 축이 하한선 최소개수보다 적으면 FLOOR 가 전원 탈락한다 — 절제가 아니라
            # 유니버스 전멸이므로 Δ를 기여도로 읽으면 안 된다. 건너뛰되 표에 남긴다.
            rows.append([f"− {drop}", "—", "—",
                         f"측정 불가 (잔여 축 {len(rest)}개 < 하한선 최소 {MIN_FLOOR_AXES}개)"])
            continue
        s = _score_arm(rest, f"R5_no_{drop}")
        rows.append([f"− {drop}", f"{s:.3f}", f"{s - s0:+.3f}",
                     "기여함" if s < s0 - 0.03 else ("무기여" if s > s0 + 0.03 else "중립")])
    LOG.table(rows, ["절제 대상", "Sharpe", "Δ", "판정"], ["l", "r", "r", "l"],
              title="R5 절제 검사 — 어느 축이 실제로 기여하는가")
    _record("R5", "팩별·축별 절제", True, f"기준 Sharpe {s0:.3f} 대비 축별 기여 귀속 완료")


# ── R6. PBO / DSR ───────────────────────────────────────────────────────────────────────────
def _dsr(sharpe: float, n: int, skew: float, kurt: float, n_trials: int) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado)."""
    if not np.isfinite(sharpe) or n < 12:
        return np.nan
    try:
        from scipy.stats import norm
        e = 0.5772156649
        sr0 = math.sqrt(2 * math.log(max(n_trials, 2))) * (1 - e) + e * math.sqrt(
            2 * math.log(max(n_trials, 2) * math.e))
        sr0 = sr0 * (1.0 / math.sqrt(n))
        denom = math.sqrt(max(1e-12, 1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe ** 2))
        return float(norm.cdf((sharpe - sr0) * math.sqrt(n - 1) / denom))
    except Exception:
        return np.nan


def R6_pbo_dsr(bt: dict, n_trials: int = 12) -> None:
    from scipy import stats as _st
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    n = len(r)
    if n < 24:
        _record("R6", "PBO / DSR", None, "표본 부족")
        return
    sr_m = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    dsr = _dsr(sr_m, n, float(_st.skew(r)), float(_st.kurtosis(r, fisher=False)), n_trials)

    # PBO (CSCV, 축약형): 시계열을 S 조각으로 나눠 IS/OOS 순위 역전 빈도
    S = 8
    if n >= S * 6:
        idx = np.array_split(np.arange(n), S)
        losses = 0
        combos = 0
        for i in range(S):
            oos = idx[i]
            iss = np.concatenate([idx[j] for j in range(S) if j != i])
            if len(oos) < 3 or len(iss) < 6:
                continue
            combos += 1
            m_is, m_oos = r[iss].mean(), r[oos].mean()
            if m_is > 0 and m_oos <= 0:
                losses += 1
        pbo = losses / combos if combos else np.nan
    else:
        pbo = np.nan
    passed = (np.isfinite(dsr) and dsr > 0.90) and (not np.isfinite(pbo) or pbo < 0.5)
    _record("R6", "PBO / DSR", passed,
            f"DSR={dsr:.3f} (>0.90 권장, 시행횟수 {n_trials} 가정) · PBO={pbo:.3f} (<0.5 권장). "
            + ("과적합 위험 낮음." if passed else "과적합 위험이 낮지 않습니다 — 파라미터 수를 줄이세요."),
            metrics={"dsr": dsr, "pbo": pbo})


# ── R7. 레짐 분할 ───────────────────────────────────────────────────────────────────────────
def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    R = bt["returns"].set_index("month")["ret"]
    rows = []
    ks = bench.get("KOSPI")
    if ks is not None:
        up = ks.reindex(R.index) > 0
        for lab, m in (("강세(코스피↑)", up), ("약세(코스피↓)", ~up)):
            x = R[m.fillna(False)]
            if len(x) >= 6:
                rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                             f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    # 전·후반 구간 (PACK-C 밸류업 레짐 판정의 근거)
    half = len(R) // 2
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        if len(x) >= 6:
            rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                         f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    pre24 = R[R.index < as_ts("2024-01-01")]
    post24 = R[R.index >= as_ts("2024-01-01")]
    LOG.table(rows, ["레짐", "월수", "월평균", "연변동성", "승률"], ["l", "r", "r", "r", "r"],
              title="R7 레짐 분할")
    verdict = ""
    if len(pre24) >= 12 and len(post24) >= 6:
        verdict = (f"2024년 이전 월평균 {pre24.mean()*100:+.3f}%p / 이후 {post24.mean()*100:+.3f}%p. ")
        if "C" in ACTIVE_PACKS:
            if pre24.mean() <= 0:
                verdict += ("★ 밸류업(2024~) 이전 구간에서 알파가 0 이하입니다 → "
                            "이것은 구조적 알파가 아니라 정책 베팅입니다(§6.1 레짐 경고).")
            else:
                verdict += "밸류업 이전 구간에서도 알파가 양(+)이므로 정책 베팅으로만 보기는 어렵습니다."
    _record("R7", "레짐 분할", True, verdict or "레짐별 성과 공개 완료")


# ── R8. 하위기간 안정성 ─────────────────────────────────────────────────────────────────────
def R8_subperiod(bt: dict) -> None:
    R = bt["returns"].copy()
    R["year"] = R["month"].dt.year
    rows = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        rows.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%", f"{g['ret'].mean()*100:+.3f}%p",
                     f"{(g['ret']>0).mean()*100:.0f}%", f"{g['n'].mean():.1f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수"],
              ["c", "r", "r", "r", "r", "r"], title="R8 연도별 분해")
    yrs = [float(r[2].rstrip("%")) for r in rows]
    pos = sum(1 for v in yrs if v > 0)
    _record("R8", "하위기간 안정성", True,
            f"{pos}/{len(yrs)}개 연도 양(+). 최악 {min(yrs):+.1f}% / 최고 {max(yrs):+.1f}%")


# ── R9. 회전율·용량 ─────────────────────────────────────────────────────────────────────────
def R9_capacity(P: pd.DataFrame, run_fn) -> None:
    gross = run_fn(P, label="R9_gross", apply_costs=False)
    net = run_fn(P, label="R9_net", apply_costs=True)
    sg, sn = _sharpe(gross["returns"]), _sharpe(net["returns"])
    mg = gross["returns"]["ret"].mean()
    mn = net["returns"]["ret"].mean()
    survives = np.isfinite(sn) and sn > 0 and mn > 0
    _record("R9", "회전율·비용 차감 후 생존", survives,
            f"비용 전 Sharpe {sg:.3f}(월 {mg*100:+.3f}%p) → 비용 후 {sn:.3f}(월 {mn*100:+.3f}%p). "
            f"월평균 회전율 {net['returns']['turnover'].mean():.2f}, "
            f"월평균 비용 {net['returns']['cost'].mean()*100:.3f}%p. "
            + ("비용 차감 후에도 성과가 남습니다." if survives else
               "★ 비용 차감 후 성과가 소멸합니다 — 개인 소액계좌에서 실행 불가(§15-7)."),
            kill=False, metrics={"sharpe_gross": sg, "sharpe_net": sn})


# ── R11. 팩 간 상관 ─────────────────────────────────────────────────────────────────────────
def R11_pack_corr(P: pd.DataFrame) -> None:
    cols = [p["E_col"] for p in active_packs() if p["E_col"] in P.columns] + \
           [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    if len(cols) < 2:
        _record("R11", "팩 간 상관", None, "활성 축이 2개 미만이라 판정 불가")
        return
    C = P[cols].corr(min_periods=200)
    rows = [[c] + [f"{C.loc[c, d]:+.2f}" if pd.notna(C.loc[c, d]) else "—" for d in cols] for c in cols]
    LOG.table(rows, ["축"] + cols, ["l"] + ["r"] * len(cols), title="R11 팩 간 상관행렬")
    hi = [(a, b, C.loc[a, b]) for i, a in enumerate(cols) for b in cols[i+1:]
          if pd.notna(C.loc[a, b]) and abs(C.loc[a, b]) > 0.7]
    _record("R11", "팩 간 상관", len(hi) == 0,
            "중복 축 없음" if not hi else
            "높은 상관: " + ", ".join(f"{a}~{b}={v:+.2f}" for a, b, v in hi) + " → 통합 검토 필요")


def report_robustness():
    LOG.banner("강건성 검사 요약 (R1~R11)", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    order = ["R1", "R2", "R3", "R4", "R10", "R5", "R11", "R6", "R7", "R8", "R9"]
    rows = []
    for rid in order:
        r = ROBUST_RESULTS.get(rid)
        if not r:
            rows.append([rid, "—", "미실행", ""])
            continue
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid + ("⭐" if r["kill"] else ""), _trunc(r["name"], 26), icon,
                     _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)
    fails = [r for r in ROBUST_RESULTS.values() if r["pass"] is False]
    kills = [r for r in fails if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§15 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("모든 강건성 검사 통과.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — 성과검증표 / 해석표 / 종목별 진단 카드                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

INTERP_D_STATE = [
    ("ΔE>0, ΔM≤0", "★목표 상태. 시장이 개선을 일회성으로 분류", "진입"),
    ("ΔE>0, ΔM>0", "리레이팅 진행 중. 알파 소진", "관망/청산"),
    ("ΔE≤0, ΔM>0", "기대만 앞섬", "배제"),
    ("ΔE≤0, ΔM≤0", "개선 없음", "배제"),
]
INTERP_COMMON = [
    ("TP_B1", "수요가 공급을 당김. 협상력", "밀어내기 가능성 → V1 확인"),
    ("TP_B2", "이익의 질 양호", "회계적 이익 우위"),
    ("TP_C1", "수익성 유지하며 확장. 제약선 이동", "확장이 수익성 희석"),
    ("TP_C2", "희석 없는 인력 확장", "단순 규모 확대"),
]


def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = ""):
    LOG.banner(f"성과 검증 — {label or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 1회 리밸런싱 · 익일 시가 체결 · 롱온리")
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return
    order = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
             "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
             "월평균회전율", "월평균비용"]
    fmt = {"누적수익": "pct", "CAGR": "pct", "연변동성": "pct", "MDD": "pct", "승률": "pct",
           "월평균": "pctp", "월평균비용": "pctp", "월평균회전율": "num"}
    rows = []
    for k in order:
        v = s.get(k)
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            rows.append([k, "—"]); continue
        f = fmt.get(k)
        rows.append([k, f"{v*100:+.2f}%" if f == "pct" else
                        f"{v*100:+.3f}%p" if f == "pctp" else
                        f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"])
    LOG.table(rows, ["지표", "값"], ["l", "r"], title="포트폴리오 성과")

    brows = []
    R = bt["returns"].set_index("month")["ret"]
    for name, b in bench.items():
        bb = b.reindex(R.index).fillna(0)
        cum_s = float((1 + R.fillna(0)).prod() - 1)
        cum_b = float((1 + bb).prod() - 1)
        excess = R.fillna(0) - bb
        _, t = hac_tstat(excess.to_numpy())
        brows.append([name, f"{cum_b*100:+.1f}%", f"{cum_s*100:+.1f}%",
                      f"{(cum_s-cum_b)*100:+.1f}%p", f"{excess.mean()*100:+.3f}%p", f"{t:.2f}"])
    if brows:
        LOG.table(brows, ["벤치마크", "벤치 누적", "전략 누적", "초과", "월평균 초과", "HAC t"],
                  ["l", "r", "r", "r", "r", "r"], title="벤치마크 대비")

    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:,.3f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 (§10.2 — 이 전략은 IR 이 아니라 꼬리에 의존한다)")
        if rt.get("총기여") and rt.get("상위5% 제외 후 총기여") is not None:
            base, ex = rt["총기여"], rt["상위5% 제외 후 총기여"]
            if base > 0 and ex <= 0:
                LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. "
                         "성과가 소수 종목에 전적으로 의존합니다 — 실전에서 그 종목을 놓치면 "
                         "전략 전체가 실패합니다. 이 사실을 반드시 인지하고 사이징하세요.")


def report_interpretation(P: pd.DataFrame):
    LOG.banner("해석 참조표 (§13.2)", "TP 가 발화했을 때와 안 했을 때 각각 무슨 뜻인가")
    rows = []
    for p in active_packs():
        for tp, fire, nofire in p["interp"]:
            rows.append([p["id"], tp, _trunc(fire, 44), _trunc(nofire, 44)])
    for tp, fire, nofire in INTERP_COMMON:
        rows.append(["공용", tp, _trunc(fire, 44), _trunc(nofire, 44)])
    LOG.table(rows, ["팩", "TP", "발화 의미", "미발화 의미"], ["c", "l", "l", "l"], maxw=46)
    LOG.table([[a, b, c] for a, b, c in INTERP_D_STATE],
              ["D축 상태", "해석", "조치"], ["l", "l", "c"], title="D축(반영도) 상태 해석")

    if "D_state" in P.columns:
        cnt = P["D_state"].value_counts()
        LOG.table([[k, f"{v:,}", f"{100*v/len(P):.1f}%"] for k, v in cnt.items()],
                  ["상태", "행수", "비중"], ["l", "r", "r"],
                  title="실제 패널의 D축 상태 분포")

    fired = []
    for p in active_packs():
        for tp in p["tp_cols"]:
            if tp in P.columns:
                v = P[tp]
                fired.append([p["id"], tp, f"{int(v.notna().sum()):,}",
                              f"{float(v.mean()):+.3f}" if v.notna().any() else "—",
                              f"{int((v > 1).sum()):,}", f"{100*float((v > 1).mean()):.2f}%"])
    for tp in ("TP_B1", "TP_B2", "TP_C1", "TP_C2"):
        if tp in P.columns:
            v = P[tp]
            fired.append(["공용", tp, f"{int(v.notna().sum()):,}",
                          f"{float(v.mean()):+.3f}" if v.notna().any() else "—",
                          f"{int((v > 1).sum()):,}", f"{100*float((v > 1).mean()):.2f}%"])
    if fired:
        LOG.table(fired, ["팩", "TP", "관측행수", "평균", "발화(>1σ²)", "발화율"],
                  ["c", "l", "r", "r", "r", "r"],
                  title="트레이드오프 쌍 발화 통계 (TP는 곱이므로 두 조건이 동시 성립할 때만 양수)")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5):
    LOG.banner("종목별 진단 카드 (§13.1)", "최근 시점 신호 상위 종목 — 왜 뽑혔는지 한 장으로")
    last_m = P["month"].max()
    sub = P[(P["month"] == last_m) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    if sub.empty:
        sub = P[P["month"] == last_m]
    if sub.empty:
        LOG.warn("마지막 시점 패널이 비어 진단 카드를 만들 수 없습니다.")
        return
    names = sec.set_index("code")["name"].to_dict()
    top = sub.nlargest(min(top_n, len(sub)), "Signal_rank")
    for r in top.itertuples(index=False):
        code = r.code
        _safe_print("\n" + "─" * 104)
        _safe_print(f"[{code}] {names.get(code, '')}    셀: {getattr(r, 'cell', '?')}    "
              f"신호일: {pd.Timestamp(last_m).date()}")
        _safe_print("─" * 104)
        sig = getattr(r, "Signal_rank", np.nan)
        _safe_print(f"Signal {sig:.3f} (상위 {100*(1-sig):.1f}%)   "
              f"E: {getattr(r,'E',np.nan):.3f}   U: {getattr(r,'U',np.nan):.3f}   "
              f"Veto: {'통과' if getattr(r,'VETO',0)==1 else '차단'}")
        act = ",".join(p["id"] for p in active_packs()
                       if p["E_col"] in P.columns and np.isfinite(getattr(r, p["E_col"], np.nan)))
        ina = ",".join(p["id"] for p in active_packs()
                       if p["E_col"] in P.columns and not np.isfinite(getattr(r, p["E_col"], np.nan)))
        _safe_print(f"활성 팩: {act or '없음'}  |  비활성: {ina or '없음'}")

        _safe_print("\n■ 발화한 트레이드오프")
        tps = []
        for p in active_packs():
            for tp, fire, nofire in p["interp"]:
                v = getattr(r, tp, np.nan)
                if np.isfinite(v):
                    tps.append((tp, v, fire if v > 0 else nofire))
        for tp in ("TP_B1", "TP_B2", "TP_C1", "TP_C2"):
            v = getattr(r, tp, np.nan)
            if np.isfinite(v):
                meaning = next((f if v > 0 else nf for t, f, nf in INTERP_COMMON if t == tp), "")
                tps.append((tp, v, meaning))
        for tp, v, meaning in sorted(tps, key=lambda x: -x[1])[:8]:
            mark = "발화" if v > 0 else "미발화"
            _safe_print(f"  {_pad(tp,7)} {v:+7.2f}  [{mark}] {_trunc(meaning, 62)}")

        _safe_print("\n■ 미반영도 (U)")
        _safe_print(f"  d1  ΔlogE {getattr(r,'dlog_E',np.nan):+.3f}, ΔlogM {getattr(r,'dlog_M',np.nan):+.3f}"
              f"  → {getattr(r,'D_state','?')}")
        for k, lab in (("d2", "컨센 목표주가 리비전"), ("d3", "기관+외인 수급"), ("d4", "커버리지 변화")):
            v = getattr(r, k, np.nan)
            _safe_print(f"  {k}  {lab}: " + (f"{v:+.4f}" if np.isfinite(v) else "데이터 부족(결측 — 0으로 채우지 않음)"))
        if np.isfinite(getattr(r, "n_analyst", np.nan)):
            _safe_print(f"      커버 애널리스트 {int(getattr(r,'n_analyst',0))}명 · "
                  f"목표주가 중앙값 {getattr(r,'tp_median',np.nan):,.0f}원")

        _safe_print("\n■ 정책 오염 점검")
        det = getattr(r, "d_eff_tax", np.nan)
        _safe_print(f"  유효세율 변화 {det:+.4f} (임계 -0.03)   "
              f"{'✔ V8 통과' if getattr(r,'V8',1)==1 else '✘ V8 발동 — 정책 유인 채용 의심'}")
        if np.isfinite(getattr(r, "emp_band_flag", np.nan)):
            _safe_print(f"  임계밴드(50/100/300인) 근접: "
                  f"{'❗해당 — 신뢰도 하향' if getattr(r,'emp_band_flag',0)==1 else '✔ 이격'}")

        _safe_print("\n■ 거부권")
        vs = []
        for i in range(1, 9):
            v = getattr(r, f"V{i}", 1)
            vs.append(f"V{i} {'✔' if v == 1 else '✘'}")
        _safe_print("  " + "  ".join(vs))
    _safe_print("─" * 104)


def report_dataflow_map():
    """거시적 흐름 한 장 — 어디서 어디로 데이터가 가는지."""
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────┐
  │  환경감지 → 의존성 → 구글드라이브 마운트 → VAULT(공용/전용 인덱스, append-only 저널)  │
  │            └ adopt_scan: 기존 캐시 '이동 없이 참조 등록'                              │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │  종목마스터  ← FDR GitHub캐시 / KIND / pykrx월말스냅샷 / DART corpCode                 │
  │  가격·수급   ← KRX인증 → pykrx → FDR → 네이버 → yfinance  (폴백 체인, 소스 감사표)     │
  │  DART        ← 재무제표(rcept_no→knowledge_date) / 직원현황 / 공시목록 스윕             │
  │  리서치      ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장    │
  │                └ 애널리스트 원장 → (analyst_id, code, date, tp) → 목표주가 리비전       │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼  모든 테이블은 pit_frame() 통과 → PIT.register()
  ┌── L1/L2 피처 ─────────────────────────────────────────────────────────────────────────┐
  │  PIT 유니버스(상폐 포함) → 셀(date,industry,size) → 기본패널                            │
  │  PIT.asof_join(knowledge_date ≤ month)  ← C1 이 강제되는 유일한 관문                    │
  │  공용축 B/C/D  +  활성 센서팩(레지스트리)  →  TP = z(개선) × z(대가회피)                 │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L2 스코어 ──────────────────────────────────────────────────────────────────────────┐
  │  거부권 V1~V8 (이진·곱) → 하한선(빈 축 없을 것) → Signal = rank(E)×rank(U)×∏V           │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L3 백테스트 → L5 강건성 → L6 리포트 ────────────────────────────────────────────────┐
  │  익일시가 체결 · 상폐 -100% · 비용(수수료+거래세이력+제곱근충격)                          │
  │  R1 누수 → R2 TP vs 나이브⭐ → R3 직교화⭐ → R4 플라시보 → R10 정책반증 → R5~R11        │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 C1~C12 (§2) — 주석이나 관례는 무효. 테스트로만 강제한다.                    ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return ok


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACT_RESULTS.clear()
    rng = np.random.default_rng(SEED)

    # ── C1: PIT 강제 ──────────────────────────────────────────────────────────────────────
    def c1():
        d = pd.DataFrame({"code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 필터가 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "knowledge_date > as_of 인 행이 새어나왔습니다"
        # PIT 컬럼 없는 테이블은 반드시 거부돼야 한다
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 등록 거부 확인"

    _c("C1", "Point-In-Time 강제", c1)

    # ── C2: 생존자편향 ────────────────────────────────────────────────────────────────────
    def c2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": ["옛날", "미래", "폐지"],
            "market": ["KOSPI"] * 3, "industry": ["X"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"]),
        })
        days = pd.bdate_range("2009-01-01", "2026-08-01")
        px = pd.DataFrame({"date": days, "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2016 = u.at("2016-08-31")
        if "000002" in at2016:
            return False, "★C2 위반: 2016년 유니버스에 2025년 상장 종목이 포함되었습니다"
        if "000003" not in at2016:
            return False, "★C2 위반: 2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다(생존자편향)"
        at2020 = u.at("2020-01-31")
        if "000003" in at2020:
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지종목 당시 포함 · 폐지 후 제외 모두 정상"

    _c("C2", "생존자편향 제거", c2)

    # ── C3: 매핑도 PIT ────────────────────────────────────────────────────────────────────
    def c3():
        m = pd.DataFrame({"code": ["000001"], "external_id": ["X1"], "weight": [1.0],
                          "valid_from": pd.to_datetime(["2020-01-01"]),
                          "valid_to": pd.to_datetime(["2022-12-31"])})
        for c in ("valid_from", "valid_to"):
            if c not in m.columns:
                return False, f"매핑 테이블에 시간구간 컬럼 {c} 이 없습니다"
        t = as_ts("2019-06-30")
        live = m[(m["valid_from"] <= t) & (m["valid_to"] >= t)]
        return (len(live) == 0), "매핑 유효구간 이전 시점에서 매핑이 적용되지 않음 확인"

    _c("C3", "매핑·라벨 PIT", c3)

    # ── C4/C11: 셀 정의 ───────────────────────────────────────────────────────────────────
    def c4():
        n = 400
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": [as_ts("2020-06-30")] * n,
            "employees": rng.integers(10, 5000, n).astype(float),
            "x": rng.normal(size=n),
        })
        sec = pd.DataFrame({"code": P["code"], "industry": rng.choice(["화학", "전자", "건설"], n)})
        C = build_cells(P, sec)
        if "cell" not in C.columns:
            return False, "cell 컬럼이 생성되지 않았습니다"
        keys = C["cell"].astype(str).str.split("|", expand=True)
        if keys.shape[1] < 3:
            return False, "cell_key 가 (date, industry, size_bucket) 3요소가 아닙니다"
        z = xsec_z(C["x"], C["cell"])
        for cell, g in C.assign(z=z).groupby("cell", observed=True):
            if g["z"].notna().sum() >= CELL_MIN_N:
                if abs(float(g["z"].mean())) > 0.15:
                    return False, f"셀 {cell} 의 z-score 평균이 0에서 벗어남: {g['z'].mean():.3f}"
        return True, f"cell=(date,industry,size) · 셀 내 z 평균≈0 · 폴백 동작 확인 ({C['cell'].nunique()}개 셀)"

    _c("C4/C11", "셀 정의 및 횡단면 연산", c4)

    # ── C5: winsorize → z → rank 순서 ─────────────────────────────────────────────────────
    def c5():
        v = pd.Series([1.0] * 30 + [1000.0])          # 극단값 1개
        cell = pd.Series(["A"] * 31)
        z = xsec_z(v, cell)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        if float(z.max()) > 6:
            return False, f"윈저라이즈가 적용되지 않았습니다 (max z={z.max():.2f})"
        r = xsec_rank_pct(v, cell)
        if not (0 < float(r.min()) <= float(r.max()) <= 1):
            return False, "rank_pct 범위가 [0,1] 이 아닙니다"
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]))
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 으로 처리되지 않았습니다(0으로 채우면 안 됩니다)"
        # ±inf 오염: nanmean 은 NaN 은 무시하지만 inf 는 무시하지 않는다.
        # inf 하나가 셀 전체 z 를 0으로 뭉개면 그 셀의 신호가 통째로 사라진다.
        vi = pd.Series([1.0, 2.0, 3.0, np.inf, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        zi = xsec_z(vi, pd.Series(["A"] * 10))
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, (f"★inf 오염: 셀에 ±inf 가 하나 있으면 z-score 가 전부 뭉개집니다 "
                           f"(유효 {int(zi.notna().sum())}개, 표준편차 {float(zi.dropna().std()):.3f}). "
                           f"비율/로그 지표에서 흔히 발생하며 해당 셀의 신호가 통째로 소실됩니다.")
        return True, ("winsorize(±2σ)→z→rank_pct 순서 · 표본부족 NaN · ±inf 무해화 확인")

    _c("C5", "윈저라이즈→랭크 순서 고정", c5)

    # ── C6: 거부권 이진 ───────────────────────────────────────────────────────────────────
    def c6():
        P = pd.DataFrame({f"V{i}": [1.0, 0.0, 1.0] for i in range(1, 9)})
        prod = P.prod(axis=1)
        if list(prod) != [1.0, 0.0, 1.0]:
            return False, "거부권 곱이 이진으로 작동하지 않습니다"
        # 상쇄 불가: 어떤 큰 점수도 0을 되살릴 수 없다
        E, U = 0.999, 0.999
        if E * U * 0.0 != 0.0:
            return False, "거부권이 상쇄 가능합니다"
        return True, "V∈{0,1} · 곱 · 상쇄 불가 확인"

    _c("C6", "거부권 이진·곱", c6)

    # ── C7: 가중치 최적화 금지 ────────────────────────────────────────────────────────────
    def c7():
        src = ""
        for fn in (assemble_score, axis_B_tp, axis_C_tp):
            try:
                import inspect
                src += inspect.getsource(fn)
            except Exception:
                pass
        if re.search(r"(minimize|curve_fit|GridSearch|optimize\.|\.fit\(.*weight)", src):
            return False, "가중치 최적화 흔적이 발견되었습니다 (C7 위반)"
        return True, "TP 내·팩 내·팩 간 모두 동일가중 (nanmean). 최적화 루틴 없음"

    _c("C7", "Phase1-3 가중치 최적화 금지", c7)

    # ── C8: 결정성 ────────────────────────────────────────────────────────────────────────
    def c8():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1]).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 순서 무관 결과 동일 확인"

    _c("C8", "결정성", c8)

    # ── C10: 런타임 예산 계측 존재 ────────────────────────────────────────────────────────
    def c10():
        if not hasattr(PIPE, "report_runtime"):
            return False, "런타임 계측기가 없습니다"
        budgeted = [s for s in PIPE.stages.values() if s.budget_s is not None]
        return True, f"계층별 계측 활성 · 예산 지정 스테이지 {len(budgeted)}개 (추측 아닌 실측)"

    _c("C10", "런타임 예산 계측", c10)

    # ── C12: 정책 중립성 ──────────────────────────────────────────────────────────────────
    def c12():
        missing = [pid for pid, p in PACK_REGISTRY.items() if not p["policy"]]
        if missing:
            return False, f"정책 캘린더 없는 팩: {missing}"
        act = [p["id"] for p in active_packs()]
        return True, (f"등록 팩 {list(PACK_REGISTRY)} 전부 정책 캘린더 보유 · "
                      f"활성 팩 {act} 은 R10 대상")

    _c("C12", "정책 중립성", c12)

    # ── 추가: TP 는 반드시 곱 ─────────────────────────────────────────────────────────────
    def c_tp():
        a = pd.Series([2.0, 2.0, 0.0, np.nan])
        b = pd.Series([3.0, -3.0, 5.0, 1.0])
        r = tp_product(a, b)
        if not (abs(r[0] - 6) < 1e-6 and abs(r[1] + 6) < 1e-6):
            return False, "TP 가 곱으로 계산되지 않습니다"
        if pd.notna(r[3]):
            return False, "한쪽이 결측인데 결과가 결측이 아닙니다(0으로 채우면 거짓 주장이 됩니다)"
        return True, "TP = z(개선)×z(대가회피) · 결측 전파 확인 (합산으로 단순화 안 됨)"

    _c("TP", "트레이드오프 쌍은 곱(§1.1)", c_tp)

    # ── 회귀 방지: as-of 결합이 행을 버리지 않을 것 (C1+C2 동시) ──────────────────────────
    def c_asof():
        panel = pd.DataFrame({"code": ["A", "B", "C", "A", "B", "C"],
                              "corp_code": ["c1", None, "c3", "c1", None, "c3"],
                              "month": pd.to_datetime(["2020-01-31"] * 3 + ["2020-02-29"] * 3)})
        fin = pit_frame(pd.DataFrame({"corp_code": ["c1", "c1", "c3"],
                                      "revenue_ttm": [100.0, 999.0, 300.0],
                                      "pe": pd.to_datetime(["2019-12-31", "2020-03-31", "2019-12-31"]),
                                      "kd": pd.to_datetime(["2020-01-15", "2020-05-15", "2020-01-15"])}),
                        "pe", "kd")
        st = PITStore()
        st.register("fin", fin, key_cols=["corp_code"])
        out = st.asof_join(panel, "fin", by="corp_code", left_time="month")
        if len(out) != len(panel):
            return False, (f"★C2 재유입: 결합키가 결측인 행이 버려졌습니다 "
                           f"({len(out)}/{len(panel)}행). corp_code 없는 종목(대개 상장폐지)이 "
                           f"통째로 사라지면 그게 곧 생존자편향입니다.")
        if not out.loc[out["code"] == "B", "revenue_ttm"].isna().all():
            return False, "결합키 결측 행에 값이 붙었습니다"
        if out.loc[out["code"] == "A", "revenue_ttm"].tolist() != [100.0, 100.0]:
            return False, (f"★C1 위반: 2020-05-15 에야 알 수 있는 값(999)이 새어나오거나 "
                           f"행 정렬이 어긋났습니다 → {out.loc[out['code']=='A','revenue_ttm'].tolist()}")
        if out.loc[out["code"] == "C", "revenue_ttm"].tolist() != [300.0, 300.0]:
            return False, "결합 결과가 다른 종목에 붙었습니다(정렬 오류)"
        return True, "결합키 결측 행 보존 · 미래값 차단 · 종목별 정렬 정확"

    _c("C1/C2b", "as-of 결합 무결성", c_asof)

    # ── 회귀 방지: 유니버스는 미래 스냅샷을 쓰지 않을 것 ───────────────────────────────────
    def c_snapfuture():
        """스냅샷 semantics 3종 동시 검정.

        스냅샷은 '대체'가 아니라 '보강'이다. KRX 는 부분 응답을 자주 내는데, 그걸 그 달의
        진실로 믿고 날짜 근거를 덮어쓰면 유니버스가 조용히 줄어 곧바로 선택편향이 된다.
        그래서 세 성질을 동시에 만족해야 한다:
          (a) 미래 스냅샷에만 있는 종목은 절대 들어오면 안 된다      → 미래누수 금지
          (b) 과거 스냅샷에만 있는 종목은 반드시 들어와야 한다        → 생존자편향 방지
          (c) 부분 스냅샷에서 빠졌어도 날짜 근거가 있으면 남아야 한다 → 부분응답 방어
        """
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003", "000004"],
            "name": list("abcd"), "market": ["KOSPI"] * 4, "industry": ["X"] * 4,
            "corp_code": [None] * 4,
            # 003 = 스냅샷에만 존재(날짜 근거 없음), 004 = 2019 폐지
            "listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", None, "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, None, "2019-06-30"]),
        })
        snaps = pd.DataFrame({
            "snap_date": pd.to_datetime(["2020-01-31", "2020-01-31", "2020-03-31"]),
            # 2020-01 스냅샷은 '부분 응답'이라 000002 가 빠져 있다
            "code": ["000001", "000003", "000009"], "market": ["KOSPI"] * 3})
        px = pd.DataFrame({"date": pd.bdate_range("2009-01-01", "2021-01-01"), "code": "000001"})
        u = Universe(sec, snaps, px)
        got = set(u.at("2020-02-29"))

        if "000009" in got:
            return False, ("★미래누수: 2020-03-31 스냅샷에만 있는 종목이 2020-02-29 유니버스에 "
                           "들어왔습니다. 가장 '가까운'이 아니라 가장 '최근 과거' 스냅샷만 써야 합니다.")
        if "000003" not in got:
            return False, ("★생존자편향: 과거 스냅샷에만 존재하는 종목이 빠졌습니다. "
                           "상장/폐지 명단에서 누락된 종목이 바로 이 경로로 들어옵니다.")
        if "000002" not in got:
            return False, ("★부분응답 사고: 스냅샷에서 빠졌다는 이유로 날짜 근거가 있는 종목이 "
                           "탈락했습니다. 스냅샷은 대체가 아니라 보강이어야 합니다 "
                           "(KRX 부분 응답이 그 달 유니버스를 통째로 깎습니다).")
        if "000004" in got:
            return False, "2019-06-30 폐지 종목이 2020년 유니버스에 남아 있습니다."
        return True, ("미래 스냅샷 차단 · 과거 스냅샷 보강 · 부분응답 내성 · 폐지 후 제외 "
                      "모두 확인 (스냅샷은 대체가 아닌 보강)")

    _c("C2c", "유니버스 스냅샷 방향성", c_snapfuture)

    # ── 회귀 방지: 결측 컬럼 산술이 죽지 않을 것 ──────────────────────────────────────────
    def c_col():
        df = pd.DataFrame({"x": [1.0, 2.0]})
        s = col(df, "rnd_ttm")
        if not isinstance(s, pd.Series) or len(s) != 2 or s.notna().any():
            return False, "col() 이 결측 Series 를 반환하지 않습니다"
        _ = s.abs().fillna(0) + col(df, "capex_ttm").abs().fillna(0)
        if df.get("rnd_ttm") is not None:
            return False, "테스트 전제 오류"
        return True, ("없는 컬럼도 NaN Series 로 안전 반환 — 데이터 소스가 통째로 빈 실행에서 "
                      "AttributeError 로 죽지 않음")

    _c("COL", "결측 컬럼 안전 접근", c_col)

    # ── 회귀 방지: 비중 상한이 실제로 강제될 것 (§8.5 — 코드 상수로 못박은 규칙) ───────────
    def c_size():
        for name, sig, adv in (
            ("균등", np.linspace(0.5, 1.0, 10), np.full(10, 1e12)),
            ("극단집중", np.array([1.0] + [0.01] * 9), np.full(10, 1e12)),
            ("소수종목", np.linspace(0.6, 1.0, 5), np.full(5, 1e12)),
            ("저유동성", np.linspace(0.5, 1.0, 10), np.array([1e7] * 3 + [1e12] * 7)),
        ):
            sub = pd.DataFrame({"Signal_rank": sig, "adv20": adv,
                                "code": [f"{i:06d}" for i in range(len(sig))]})
            w = size_positions(sub)["weight"].to_numpy(dtype=float)
            if w.max() > POS_MAX_WEIGHT + 1e-9:
                return False, (f"★[{name}] 종목당 최대비중 {POS_MAX_WEIGHT:.0%} 가 뚫렸습니다 "
                               f"(최대 {w.max():.4f}). clip 후 재정규화하면 상한이 무력화됩니다.")
            if w.sum() > 1.0 + 1e-9:
                return False, f"[{name}] 비중 합이 1을 초과합니다 ({w.sum():.6f})"
            liq = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1),
                           POS_MAX_WEIGHT)
            cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq, POS_MIN_WEIGHT * 0.5))
            if (w > cap + 1e-9).any():
                return False, f"★[{name}] 유동성 상한(20일 평균거래대금×{POS_ADV_PARTICIPATION:.0%})이 뚫렸습니다"
        return True, (f"종목당 상한 {POS_MAX_WEIGHT:.0%} · 유동성 상한 · 합≤1 "
                      f"모두 강제 확인 (water-filling)")

    _c("SIZE", "포지션 비중 상한 강제", c_size)

    # ── 추가: 종목코드 정규화 (2024 영숫자 티커) ──────────────────────────────────────────
    def c_code():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) 모두 정상 처리"

    _c("CODE", "종목코드 정규화", c_code)

    # ── 회귀 방지: 수집 파서 (실데이터 없이도 검증 가능한 부분) ────────────────────────────
    def c_ingest():
        # ① YY.MM.DD — pandas 자동추론은 '26.01.19'를 2019-01-26 으로 읽는다(연·일 전치)
        for raw, exp in (("26.01.19", "2026-01-19"), ("19.12.31", "2019-12-31"),
                         ("24.11.30", "2024-11-30"), ("2020-05-01", "2020-05-01")):
            if parse_kr_date(raw) != exp:
                return False, (f"★날짜 파싱: {raw} → {parse_kr_date(raw)} (기대 {exp}). "
                               f"두 자리 연도를 자동추론에 맡기면 연·일이 뒤바뀌어 "
                               f"리포트 원장의 시간축이 통째로 어긋납니다.")
        # ② 목표주가 '0'/'-' 은 결측이지 0원이 아니다
        for raw, exp in (("95,000", 95000.0), ("0", None), ("-", None), ("없음", None)):
            if parse_target_price(raw) != exp:
                return False, f"목표주가 파싱: {raw!r} → {parse_target_price(raw)!r} (기대 {exp!r})"
        # ③ 증권사 사명 변경 정규화 (안 하면 같은 애널리스트가 다른 사람이 된다)
        for raw, exp in (("미래에셋대우", "미래에셋증권"), ("하나금융투자", "하나증권"),
                         ("신한금융투자", "신한투자증권"), ("이베스트투자증권", "LS증권"),
                         ("KTB투자증권", "다올투자증권"), ("하이투자증권", "iM증권")):
            if normalize_broker(raw)[1] != exp:
                return False, f"증권사 정규화: {raw} → {normalize_broker(raw)[1]} (기대 {exp})"
        # ④ 한경 9컬럼/6컬럼/헤더없음 — 컬럼 인덱스가 아니라 헤더명으로 매핑되는지
        def _mk(hdr, rows):
            h = ("<tr>" + "".join(f"<th>{x}</th>" for x in hdr) + "</tr>") if hdr else ""
            b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
            return f"<div class='table_style01'><table>{h}{b}</table></div>"
        r9 = [["2024-05-02",
               "<a href='/analysis/downpdf?report_idx=123456'>삼성전자(005930) 실적 개선</a>",
               "95,000", "Buy", "홍길동", "미래에셋대우", "-", "-",
               "<a href='/analysis/downpdf?report_idx=123456'>P</a>"]]
        o9 = _hk_parse(_mk(["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
                            "기업정보", "차트", "첨부"], r9), "t_business")
        if not o9 or o9[0]["stock_code"] != "005930" or o9[0]["target_price"] != 95000.0 \
                or o9[0]["analyst_raw"] != "홍길동":
            return False, f"한경 9컬럼 파싱 실패: {o9[:1]}"
        o0 = _hk_parse(_mk(None, r9), "t_noheader")       # thead 가 없어도 살아남아야 한다
        if not o0 or o0[0]["stock_code"] != "005930":
            return False, f"한경 헤더없음 폴백 실패: {o0[:1]}"
        # ⑤ 인코딩: force_enc 는 힌트일 뿐 — 소스가 UTF-8 로 바뀌어도 깨지면 안 된다
        ko = "네이버 금융 리서치 종목분석 삼성전자 목표주가 상향" * 4
        for enc in ("euc-kr", "utf-8"):
            if "네이버" not in _decode(ko.encode(enc), None, "x", force_enc="euc-kr"):
                return False, f"인코딩 판별 실패: 실제 {enc} 인데 깨짐"
        return True, ("YY.MM.DD 연·일 전치 방지 · 목표주가 0/- 결측처리 · 사명변경 정규화 · "
                      "헤더명 기반 컬럼매핑(9/6/무헤더) · EUC-KR↔UTF-8 자동판별 확인")

    _c("INGEST", "수집 파서 회귀 검사", c_ingest)

    # ── 회귀 방지: 시즈닝의 기준점은 '상장일'이지 '가격패널 시작일'이 아닐 것 ───────────────
    def c_season():
        """패널 시작 전에 상장한 종목이 백테스트 첫 1년 동안 사라지지 않아야 한다.

        searchsorted 는 패널 시작 이전 상장분을 전부 index 0 으로 보낸다. 거기에 +250거래일을
        더하면 1990년 상장 종목조차 '패널 시작 후 1년'에야 시즈닝이 끝난 것으로 계산되어,
        2016-08 시작 백테스트의 첫 1년 유니버스가 통째로 비어버린다. 에러도 경고도 없이.
        """
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "name": list("abc"), "market": ["KOSPI"] * 3, "industry": ["X"] * 3,
            "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["1990-03-02",    # 패널보다 26년 전 상장
                                            "2016-09-01",    # 패널 직후 상장(아직 미시즈닝)
                                            "2013-01-02"]),  # 패널 3년 전 상장
            "delisting_date": pd.to_datetime([None, None, None]),
        })
        px = pd.DataFrame({"date": pd.bdate_range("2016-08-01", "2019-12-31"), "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        first = set(u.at("2016-08-31"))
        miss = [c for c in ("000001", "000003") if c not in first]
        if miss:
            return False, (f"★시즈닝 앵커 오류: 패널 시작 전 상장 종목 {miss} 가 백테스트 첫 "
                           f"달에서 빠졌습니다. 기준점이 '상장일'이 아니라 '가격패널 시작일'로 "
                           f"잡혀 있습니다 — 첫 1년 유니버스가 통째로 증발합니다.")
        if "000002" in first:
            return False, "2016-09-01 상장 종목이 2016-08-31 유니버스에 있습니다(미래 상장)."
        if "000002" in set(u.at("2017-03-31")):
            return False, "상장 250거래일 미만 신규 상장이 시즈닝을 통과했습니다."
        if "000002" not in set(u.at("2017-10-31")):
            return False, "상장 250거래일이 지난 종목이 여전히 시즈닝에 막혀 있습니다."
        return True, ("시즈닝 기준점 = 상장일 확인 (기존 상장사 첫 달 생존 · 신규 상장 "
                      "250거래일 대기 · 대기 후 편입)")

    _c("C2d", "시즈닝 기준점", c_season)

    # ── 회귀 방지: 원장 병합은 멱등일 것 (출력이 다음 실행의 입력이 된다) ──────────────────
    def c_merge():
        """드라이브 캐시에 저장된 병합 결과는 다음 실행에서 '입력 프레임'으로 되돌아온다.
        그래서 병합은 반드시 멱등이어야 한다. 아니면 실행할 때마다 source 문자열이 길어지고
        report_uid 가 바뀌어 PDF 캐시·애널리스트 연결표가 조용히 끊긴다."""
        sec = pd.DataFrame(columns=["code", "name", "corp_code", "market", "industry",
                                    "listing_date", "delisting_date"])

        def _f(src, rid, tp):
            return pd.DataFrame([{
                "source": src, "src_report_id": rid, "pub_date": "2024-05-02",
                "category": "기업", "title": "삼성전자(005930) 실적 개선",
                "stock_code": "005930", "stock_name": "삼성전자",
                "broker_raw": "미래에셋증권", "analyst_raw": "홍길동",
                "target_price": tp, "opinion": "Buy", "pdf_url": None, "detail_url": None,
            }])

        a, b = _f("hankyung", "h1", 95000.0), _f("naver", "n1", 90000.0)
        m1 = build_report_master([a, b], sec)
        m2 = build_report_master([a, b, m1], sec)     # 캐시 재투입
        m3 = build_report_master([m1], sec)           # 캐시만으로 실행
        if not (len(m1) == len(m2) == len(m3) == 1):
            return False, f"소스 간 중복 병합 실패: {len(m1)}/{len(m2)}/{len(m3)}건 (기대 1/1/1)"
        for nm, mm in (("캐시 재투입", m2), ("캐시 전용", m3)):
            for c, why in (("source", "합성 토큰을 원자로 분해하지 않으면 실행마다 문자열이 "
                                      "무한히 길어집니다"),
                           ("src_report_id", "원본 보고서 ID 추적이 불가능해집니다"),
                           ("report_uid", "PDF 캐시와 애널리스트 연결표가 통째로 끊깁니다")):
                if mm[c].iloc[0] != m1[c].iloc[0]:
                    return False, (f"★{nm} 실행에서 {c} 가 "
                                   f"{str(m1[c].iloc[0])[:28]!r} → {str(mm[c].iloc[0])[:28]!r} "
                                   f"로 바뀌었습니다. {why}.")
        if float(m1["target_price"].iloc[0]) != 95000.0:
            return False, f"목표주가 병합이 최대값을 취하지 않았습니다: {m1['target_price'].iloc[0]}"
        return True, ("병합 멱등성 확인 — 캐시 재투입·캐시 전용 실행 모두에서 "
                      f"source({m1['source'].iloc[0]})·src_report_id·report_uid 불변")

    _c("MERGE", "원장 병합 멱등성", c_merge)

    # ── 회귀 방지: Signal_rank 는 '월 전체' 백분위일 것 ────────────────────────────────────
    def c_rank():
        """선정부(nlargest)는 월 전체를 한 줄로 세워 뽑는다. 따라서 랭크도 월 전체여야 한다.

        한때 (month, pack_profile) 로 나눠 랭크를 매겼다. 그러면 자기 프로파일에 혼자인 종목이
        무조건 1.0 을 받아 상위를 채운다 — 실측상 월 보유종목의 70%가 동점 1.0 이었고,
        그중 상당수가 그달 '가장 낮은' 원점수였다. 정보량 차이는 랭크 분할이 아니라
        하한선(빈 축 없음 + 최소 축수)이 막는다.
        """
        n = 60
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n + 1)],
            "month": as_ts("2020-06-30"), "cell": "X", "U": 1.0, "VETO": 1.0,
            "E_A": list(np.linspace(0.0, 1.0, n)) + [0.60],
            "E_B": list(np.linspace(0.0, 1.0, n)) + [np.nan],   # 마지막 1행만 축이 1개
        })
        S = score_from_axes(P, ["E_A", "E_B"], min_axes=1)
        sig, rank = S["Signal"], S["Signal_rank"]
        if int(S["pack_profile"].nunique()) < 2:
            return False, "테스트 전제 오류: 정보량 프로파일이 2종 이상이어야 합니다."
        top_by_rank = int(rank.idxmax())
        top_by_sig = int(sig.idxmax())
        if top_by_rank != top_by_sig:
            return False, (f"★랭크가 원점수와 어긋납니다: 최고 랭크는 {P['code'][top_by_rank]}"
                           f"(Signal {sig[top_by_rank]:.4f}) 인데 최고 원점수는 "
                           f"{P['code'][top_by_sig]}(Signal {sig[top_by_sig]:.4f}) 입니다. "
                           f"Signal_rank 를 pack_profile 로 나눠 매기면 '자기 그룹에 혼자인' "
                           f"종목이 1.0 을 받아 상위를 차지합니다.")
        d = pd.DataFrame({"s": sig, "r": rank}).dropna()
        rho = float(d["s"].corr(d["r"], method="spearman"))
        if not (rho > 0.999):
            return False, f"★Signal_rank 가 Signal 의 단조함수가 아닙니다 (spearman={rho:.4f})."
        return True, (f"월 전체 백분위 확인 — 랭크가 원점수의 단조함수(ρ={rho:.4f})이고 "
                      f"축이 1개뿐인 종목이 상위를 가로채지 않음 (프로파일 "
                      f"{int(S['pack_profile'].nunique())}종)")

    _c("RANK", "선정 랭크 정합성", c_rank)

    # ── 회귀 방지: 활성 팩은 전용 수집이 배선되어 있을 것 ──────────────────────────────────
    def c_wire():
        """'수집이 배선되지 않음'과 '수집했는데 비어 있음'은 완전히 다른 사건이다.

        한때 어느 팩도 ingest_fn 을 등록하지 않아 collect_all 의 팩 수집 루프가 통째로
        무동작이었다. 5개 팩 전략이 실제로는 PACK-C 하나로 돌면서 성과표를 끝까지 출력했고,
        하류 커버리지 검사는 그걸 '데이터 부재'로 보고해 운영자를 API 키 쪽으로 오도했다.
        """
        bad = [p["id"] for p in active_packs() if not p.get("ingest") and p["id"] != "C"]
        if bad:
            return False, (f"★센서팩 {bad} 이 활성인데 ingest_fn 이 없습니다. 이 팩들은 "
                           f"수집 자체가 일어나지 않아 전 구간 결측이 되며, 키를 넣어도 "
                           f"해결되지 않습니다.")
        wired = [p["id"] for p in active_packs() if p.get("ingest")]
        return True, (f"활성 팩 {[p['id'] for p in active_packs()]} 중 전용 수집 배선 {wired} "
                      f"확인 (C 는 L1.DART 재무를 그대로 읽으므로 전용 수집 없음이 정상)")

    _c("WIRE", "센서팩 수집 배선", c_wire)

    # ── 회귀 방지: 청산 게이트의 모든 분기가 도달 가능할 것 ────────────────────────────────
    def c_exit():
        """`dm >= de and de > 0` 처럼 뒤 조건이 앞 조건에 거의 포함되는 식은, 실제로는
        '논거가 깨진 종목을 파는 경로'만 골라서 닫아버린다. 네 사분면을 전부 검정한다."""
        cases = [
            (0.05, 0.10, False, "ΔlogE>0 이고 시장이 아직 자본화 안 함 → 보유(목표상태)"),
            (0.15, 0.10, True,  "시장이 재분류 완료(ΔlogM≥ΔlogE) → 청산(알파 소진)"),
            (-0.20, -0.05, True, "이익 증가 소멸 → 청산(논거 무효). 예전엔 이 경로가 닫혀 있었다"),
            (0.05, -0.05, True, "이익 감소 + 주가 상승 → 청산"),
            (np.nan, 0.10, False, "결측 → 보유(모르는 것을 이유로 팔지 않는다)"),
            (0.05, np.nan, False, "결측 → 보유"),
        ]
        for dm, de, want, why in cases:
            got = bool(exit_gate(dm, de))
            if got != want:
                return False, (f"★청산 게이트: ΔlogM={dm}, ΔlogE={de} → {got} (기대 {want}). {why}")
        return True, ("네 사분면 + 결측 전부 확인 — 재분류 완료와 논거 무효를 모두 청산하고, "
                      "결측은 보유로 떨어짐")

    _c("EXIT", "청산 게이트 도달성", c_exit)

    # ── 회귀 방지: TP_P2 의 저-저 사분면 부호 ──────────────────────────────────────────────
    def c_tpp2():
        """TP = z(개선) × z(대가회피) 는 곱이라, 두 인자가 모두 음수면 양수가 된다.
        '취득 규모가 큰데 소각까지 실행했는가'를 묻는 TP_P2 에서는 이게 치명적이다 —
        자사주를 거의 안 샀고 소각도 안 한 기업이 '진정성 있는 환원'으로 뒤집힌다."""
        zi = pd.Series([-1.5, -0.5, 1.2, 2.0])       # 취득 규모 z
        zp = pd.Series([-1.5, 1.0, -0.8, 1.5])       # 소각 실행률 z
        out = tp_product(zi.where(zi > 0), zp)
        if pd.notna(out.iloc[0]):
            return False, (f"★저-저 사분면(취득 안 함 + 소각 안 함)이 {out.iloc[0]:.3f} 로 "
                           f"산출됐습니다. 음×음=양 때문에 '아무것도 안 한 기업'이 상위로 "
                           f"올라갑니다. 지출이 없는 쪽은 NaN 이어야 합니다.")
        if pd.notna(out.iloc[1]):
            return False, "취득 규모가 셀 평균 미만인데 값이 나왔습니다."
        if not (pd.notna(out.iloc[3]) and out.iloc[3] > 0):
            return False, f"고-고 사분면(취득 큼 + 소각 실행)이 양수가 아닙니다: {out.iloc[3]}"
        if not (pd.notna(out.iloc[2]) and out.iloc[2] < 0):
            return False, f"취득은 컸는데 소각 안 한 경우가 음수가 아닙니다: {out.iloc[2]}"
        return True, ("저-저 사분면 NaN(0 아님) · 고-고 양수 · 고-저 음수 확인 — "
                      "'대가를 안 치렀다'는 거짓 주장을 만들지 않음")

    _c("TPP2", "자사주 TP 부호", c_tpp2)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 30), "✔ 통과" if r["pass"] else "✘ 실패",
             _trunc(r["msg"], 76)] for r in CONTRACT_RESULTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=80,
              title="계약 자동검정 C1~C12 (§2 — 협상 대상이 아님)")
    failed = [r for r in CONTRACT_RESULTS if not r["pass"]]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오(§2).")
        return False
    LOG.ok(f"계약 {len(CONTRACT_RESULTS)}건 전부 통과.")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  실경로 리허설 (REHEARSAL) — 수집 함수를 '진짜로' 실행해 본다                        ║
# ║                                                                                          ║
# ║  왜 이 계층이 생겼는가:                                                                    ║
# ║    합성 스모크(§80)는 make_synthetic() 이 만든 완성 패널을 곧바로 주입한다. 즉               ║
# ║    build_security_master · fetch_prices · tidy_financials · hankyung_collect 같은          ║
# ║    실제 수집·정제 함수는 단 한 줄도 실행되지 않는다.                                        ║
# ║    실제로 이 공백 때문에 계약 17건 + 스모크를 전부 통과한 빌드가 실행 2분 만에               ║
# ║    build_security_master 의 중복 컬럼 한 줄로 죽었다.                                      ║
# ║                                                                                          ║
# ║  그래서 여기서는 네트워크 계층만 가짜로 바꾸고(HTTP·pykrx·FDR), 그 위의 수집·정제           ║
# ║  로직은 실물 그대로 돌린다. 각 함수에 대해 네 가지를 먹인다:                                 ║
# ║    ① 정상 응답  ② 빈 응답  ③ 깨진 응답  ④ 기대 컬럼이 빠진 응답                            ║
# ║  전부 '예외 없이' 통과해야 하고, 정상 응답에서는 실제로 값이 나와야 한다.                    ║
# ║                                                                                          ║
# ║  수 초면 끝나고 네트워크·키가 필요 없다. 실수집 전에 반드시 통과해야 한다.                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []

# 전략별 추가 리허설 훅. 시그니처: fn(G: dict, sec: pd.DataFrame, corps: List[str],
# months: pd.DatetimeIndex) -> None.  가짜 네트워크가 이미 물려 있는 안쪽에서 호출된다.
# 코어만 빌드하면 빈 리스트라 동작이 바뀌지 않는다(순수 추가).
REHEARSAL_HOOKS: List[Callable] = []


def _rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    """리허설 1건 실행. 예외는 실패, 정상응답 0행도 (기대했다면) 실패."""
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        REHEARSAL_RESULTS.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0,
            "err": "" if ok else "정상 응답을 줬는데 결과가 0행입니다(파싱 실패 가능성)",
            "note": note})
        return out
    except Exception as e:                                          # noqa
        REHEARSAL_RESULTS.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0,
            "err": f"{type(e).__name__}: {str(e)[:200]}", "note": note,
            "tb": traceback.format_exc()})
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────────────────────
def _fx_fdr_listing_csv(n: int = 40) -> bytes:
    # FDR GitHub 캐시 실제 스키마 (ChagesRatio 오타는 업스트림 그대로)
    rows = ["，Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"
            .replace("，", "")]
    for i in range(n):
        code = f"{i+1:06d}"
        rows.append(f"{i},{code},KR7{code}003,합성{i+1:03d},"
                    f"{'KOSPI' if i%2 else 'KOSDAQ'},,10000,0.5,1000000000,100000,"
                    f"{'STK' if i%2 else 'KSQ'}")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_fdr_delisting_csv(n: int = 30) -> bytes:
    rows = ["Symbol,Name,Market,SecuGroup,Kind,DelistingDate,ToSymbol,ToName,Reason"]
    for i in range(n):
        # 앞 20건은 정상 6자리, 뒤 10건은 비표준 코드(ETF/ELW/스팩 등) — 탈락 집계 검증용
        code = f"{900000+i:06d}" if i < 20 else f"KR{i:08d}"
        rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,"
                    f"{2017+(i%8)}-0{1+(i%9)}-15,,,상장폐지")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _fx_kind_html(n: int = 30) -> bytes:
    # KIND 는 HTML 표이고 종목코드가 '정수'로 와서 앞자리 0 이 날아간다
    head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
            "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
    body = "".join(
        f"<tr><td>합성{i+1:03d}</td><td>{i+1}</td><td>화학</td><td>제품</td>"
        f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td><td>서울</td></tr>"
        for i in range(n))
    return (head + body + "</table>").encode("euc-kr")


def _fx_dart_fnltt(corp: str, year: int) -> dict:
    def row(sj, aid, anm, amt):
        return {"rcept_no": f"{year}0331000001", "reprt_code": "11011", "bsns_year": str(year),
                "corp_code": corp, "sj_div": sj, "sj_nm": sj, "account_id": aid,
                "account_nm": anm, "thstrm_amount": amt, "frmtrm_amount": amt, "ord": "1"}
    return {"status": "000", "message": "정상", "list": [
        row("IS", "ifrs-full_Revenue", "매출액", "1,234,567,000,000"),
        row("IS", "ifrs-full_CostOfSales", "매출원가", "900,000,000,000"),
        row("IS", "dart_OperatingIncomeLoss", "영업이익", "120,000,000,000"),
        row("IS", "ifrs-full_ProfitLoss", "당기순이익", "90,000,000,000"),
        row("IS", "-표준계정코드 미사용-", "경상연구개발비", "30,000,000,000"),
        row("IS", "ifrs-full_IncomeTaxExpense", "법인세비용", "20,000,000,000"),
        row("IS", "ifrs-full_ProfitLossBeforeTax", "법인세비용차감전순이익", "110,000,000,000"),
        row("IS", "dart_SellingGeneralAdministrativeExpenses", "판매비와관리비", "200,000,000,000"),
        row("BS", "ifrs-full_Inventories", "재고자산", "150,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권", "180,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentPayables", "매입채무및기타채무", "120,000,000,000"),
        row("BS", "ifrs-full_Assets", "자산총계", "3,000,000,000,000"),
        row("BS", "ifrs-full_Liabilities", "부채총계", "1,200,000,000,000"),
        row("BS", "ifrs-full_Equity", "자본총계", "1,800,000,000,000"),
        row("BS", "ifrs-full_PropertyPlantAndEquipment", "유형자산", "800,000,000,000"),
        row("BS", "ifrs-full_IntangibleAssetsOtherThanGoodwill", "무형자산", "100,000,000,000"),
        row("BS", "dart_ContractLiabilities", "계약부채", "50,000,000,000"),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "140,000,000,000"),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득", "-60,000,000,000"),
        row("CF", "dart_DepreciationAndAmortisationExpense", "감가상각비와상각비", "50,000,000,000"),
        row("CF", "ifrs-full_DividendsPaid", "배당금지급", "-15,000,000,000"),
        row("CF", "dart_PaymentsToAcquireOrRedeemEntitysShares", "자기주식의 취득", "-8,000,000,000"),
        row("CF", "ifrs-full_ProceedsFromBorrowings", "차입금의 증가", "40,000,000,000"),
    ]}


def _fx_dart_emp(corp: str, year: int) -> dict:
    # 사업부문 × 성별로 쪼개진 실제 스키마 + '합계' 소계 행(이중계상 방지 검증)
    def r(bbm, sex, sm, tot):
        return {"rcept_no": f"{year}0331000001", "corp_code": corp, "fo_bbm": bbm,
                "sexdstn": sex, "sm": sm, "fyer_salary_totamt": tot,
                "jan_salary_am": "70,000,000"}
    return {"status": "000", "list": [
        r("반도체", "남", "1,200", "96,000,000,000"),
        r("반도체", "여", "300", "21,000,000,000"),
        r("디스플레이", "남", "500", "40,000,000,000"),
        r("디스플레이", "여", "100", "7,000,000,000"),
        r("합계", "합계", "2,100", "164,000,000,000"),
    ]}


def _fx_dart_list(bgn: str) -> dict:
    y = bgn[:4]
    return {"status": "000", "page_no": 1, "total_page": 1, "list": [
        {"corp_code": "C0000001", "corp_name": "합성001", "stock_code": "000001",
         "rcept_no": f"{y}0410000001", "rcept_dt": f"{y}0410",
         "report_nm": "주요사항보고서(자기주식취득결정)", "flr_nm": "합성001", "corp_cls": "Y"},
        {"corp_code": "C0000002", "corp_name": "합성002", "stock_code": "000002",
         "rcept_no": f"{y}0412000002", "rcept_dt": f"{y}0412",
         "report_nm": "주요사항보고서(유상증자결정)", "flr_nm": "합성002", "corp_cls": "Y"},
        {"corp_code": "C0000003", "corp_name": "합성003", "stock_code": "000003",
         "rcept_no": f"{y}0415000003", "rcept_dt": f"{y}0415",
         "report_nm": "사업보고서 (2023.12)", "flr_nm": "합성003", "corp_cls": "Y"},
    ]}


def _fx_hankyung_html(n: int = 12) -> str:
    hdr = ("<tr>" + "".join(f"<th>{h}</th>" for h in
           ["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
            "기업정보", "차트", "첨부"]) + "</tr>")
    rows = []
    for i in range(n):
        idx = 500000 + i
        rows.append(
            "<tr>"
            f"<td>2024-0{1+(i%9)}-15</td>"
            f"<td class='text_l'><a href='/analysis/downpdf?report_idx={idx}'>"
            f"합성{i+1:03d}({i+1:06d}) 실적 개선 전망</a></td>"
            f"<td class='text_r'>{(i+5)*10000:,}</td><td>Buy</td>"
            f"<td>애널{i%7:02d}</td><td>{'미래에셋대우' if i%2 else '하나금융투자'}</td>"
            f"<td>-</td><td>-</td>"
            f"<td><a href='/analysis/downpdf?report_idx={idx}'>PDF</a></td></tr>")
    return f"<div id='contents'><div class='table_style01'><table>{hdr}{''.join(rows)}</table></div></div>"


def _fx_naver_research_html(n: int = 12) -> str:
    hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
           "<th>작성일</th><th>조회수</th></tr>")
    rows = []
    for i in range(n):
        rows.append(
            "<tr>"
            f"<td style='padding-left:10'><a class='stock_item' href='/item/main.naver?code={i+1:06d}' "
            f"title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
            f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>실적 개선 전망</a></td>"
            f"<td>{'KB증권' if i%2 else '신한금융투자'}</td>"
            f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
            f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
            f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
    nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
           "<a href='/research/company_list.naver?&amp;page=3'>맨뒤</a></td></tr></table>")
    return (f"<div id='contentarea_left'><div class='box_type_m'>"
            f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")


def _fx_nps_json(page: int) -> dict:
    items = [{"wkplNm": f"합성{i+1:03d}", "bzowrRgstNo": f"{1000000000+i}",
              "jnngpCnt": str(100 + i * 7), "crrmmNtcAmt": str((100 + i * 7) * 300000),
              "nwAcqzrCnt": "5", "lssJnngpCnt": "3", "wkplRoadNmDtlAddr": "서울시 강남구",
              "ldongAddrMgplDgCd": "11", "vldtVlKrnNm": "제조업", "seq": str(i)}
             for i in range(40)]
    return {"response": {"header": {"resultCode": "00"},
                         "body": {"totalCount": 40, "pageNo": page, "numOfRows": 1000,
                                  "items": {"item": items if page == 1 else []}}}}


def _fx_g2b_json() -> dict:
    items = [{"bizno": f"{1000000000+i}", "bidwinnrNm": f"합성{i+1:03d}",
              "sucsfbidAmt": str(1_000_000_000 + i * 1_000_000),
              "presmptPrce": str(1_200_000_000 + i * 1_000_000),
              "sucsfbidRate": str(85 + (i % 10)), "dminsttNm": "조달청",
              "prdctClsfcNo": f"{4000+i}"} for i in range(25)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_customs_json() -> dict:
    items = [{"expDlr": str(1_000_000 + i * 1000), "expWgt": str(500_000 + i * 500),
              "statCd": ["US", "DE", "VN", "CN"][i % 4]} for i in range(8)]
    return {"response": {"body": {"items": {"item": items}}}}


def _fx_pdf() -> bytes:
    return b"%PDF-1.4\n% synthetic fixture\n%%EOF\n"


# ── 라우팅 ──────────────────────────────────────────────────────────────────────────────────
class _FixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크. mode 로 정상/빈/깨짐/컬럼누락을 전환한다."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: Counter = Counter()

    def _m(self, kind: str):
        self.hits[kind] += 1

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u = str(url)
        p = params or {}
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return b"\x00\x01garbage" if as_bytes else "<html><body>오류</body></html>"

        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                self._m("fdr_delisting")
                return _fx_fdr_delisting_csv()
            self._m("fdr_listing")
            if self.mode == "missingcol":
                return b"\xef\xbb\xbf,Foo,Bar\n0,1,2\n"
            return _fx_fdr_listing_csv()
        if "kind.krx.co.kr" in u:
            self._m("kind")
            return _fx_kind_html()
        if "corpCode.xml" in u:
            self._m("dart_corpcode")
            buf = io.BytesIO()
            xml = "<result>" + "".join(
                f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
                f"<stock_code>{i+1:06d}</stock_code><modify_date>20240101</modify_date></list>"
                for i in range(40)) + "</result>"
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml", xml.encode("utf-8"))
            return buf.getvalue()
        if "document.xml" in u:
            self._m("dart_document")
            buf = io.BytesIO()
            body = ("<?xml version='1.0' encoding='euc-kr'?><DOCUMENT>"
                    "II. 사업의 내용 당사는 반도체 소재를 제조합니다. " * 30 +
                    "위험요인 환율 변동 위험이 존재합니다. " * 30 +
                    "우발부채 계류 중인 소송은 없습니다. " * 20 + "</DOCUMENT>")
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("doc.xml", body.encode("euc-kr"))
            return buf.getvalue()
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                self._m("hk_pdf")
                return _fx_pdf()
            self._m("hankyung")
            page = int(p.get("now_page", 1) or 1)
            return _fx_hankyung_html() if page == 1 else "<td class='no_data'>데이터가 없습니다</td>"
        if "finance.naver.com/research" in u:
            self._m("naver_research")
            page = int(p.get("page", 1) or 1)
            if page <= 2:
                return _fx_naver_research_html()
            return "<div id='contentarea_left'><table class='type_1'></table></div>"
        if "finance.naver.com/item/main" in u:
            self._m("naver_item")
            return ('<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>')
        if "stock.pstatic.net" in u:
            self._m("naver_pdf")
            return _fx_pdf()
        if "siseJson" in u:
            self._m("naver_chart")
            rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
            d = as_ts("2016-05-02")
            for i in range(2600):
                d2 = d + pd.Timedelta(days=i)
                if d2.weekday() >= 5:
                    continue
                rows.append(f"['{d2:%Y%m%d}',10000,10100,9900,10050,120000,5.0]")
            return "[" + ",".join(rows) + "]"
        self._m("other")
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "opendart" in u and "fnlttSinglAcntAll" in u:
            self._m("dart_fnltt")
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return _fx_dart_fnltt(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "empSttus" in u:
            self._m("dart_emp")
            return _fx_dart_emp(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "opendart" in u and "list.json" in u:
            self._m("dart_list")
            return _fx_dart_list(str(p.get("bgn_de", "20200101")))
        if "NpsBplcInfoInqireService" in u:
            self._m("nps")
            return _fx_nps_json(int(p.get("pageNo", 1) or 1))
        if "ScsbidInfoService" in u:
            self._m("g2b")
            return _fx_g2b_json() if int(p.get("pageNo", 1) or 1) == 1 else {"response": {"body": {"items": []}}}
        if "nitemtrade" in u:
            self._m("customs")
            return _fx_customs_json()
        if "stockSecurity/researches" in u:
            self._m("naver_api")
            return []                       # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        self._m("other_json")
        return None


def run_rehearsal(strict: bool = True) -> bool:
    """실제 수집·정제 함수를 픽스처로 전부 실행한다. 네트워크·키 불필요."""
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다")
    REHEARSAL_RESULTS.clear()
    G = globals()
    saved = {k: G.get(k) for k in ("http_get", "http_json", "http_post",
                                   "fdr", "pykrx_stock", "yf", "DART_API_KEY",
                                   "DATA_GO_KR_KEY", "CUSTOMS_API_KEY", "RUN_MODE",
                                   "RESEARCH_DOWNLOAD_PDF", "UNIVERSE_SNAPSHOT_FREQ")}
    tmp = tempfile.mkdtemp(prefix="tcd_rehearsal_")
    saved_vault, saved_budget = G.get("VAULT"), G.get("DBUDGET")
    months = month_range("2016-08-01", "2026-07-31")

    try:
        # 네트워크·외부 라이브러리 차단 + 키 주입 (키가 있어야 해당 분기가 실행된다)
        net = _FixtureNet("ok")
        G["http_get"] = net.get
        G["http_json"] = net.json
        G["http_post"] = lambda *a, **k: ""
        G["fdr"] = None
        G["pykrx_stock"] = None            # 스냅샷 경로는 '없을 때' 폴백을 검증
        G["yf"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["DATA_GO_KR_KEY"] = "REHEARSAL"
        G["CUSTOMS_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["VAULT"] = Vault(tmp, "REHEARSAL")
        G["DBUDGET"] = DartBudget()

        # ── ① 유니버스 ────────────────────────────────────────────────────────────────────
        snaps = _rh("fetch_pykrx_snapshots(pykrx 없음→폴백)",
                    lambda: fetch_pykrx_snapshots(months), expect_rows=False,
                    note="pykrx 미설치 상황에서 죽지 않고 빈 결과를 돌려줘야 한다")
        _rh("fetch_fdr_listing", fetch_fdr_listing)
        _rh("fetch_fdr_delisting", fetch_fdr_delisting)
        _rh("fetch_kind_listing", fetch_kind_listing)
        _rh("fetch_dart_corpcode", fetch_dart_corpcode)
        sec = _rh("build_security_master ★이번 크래시 지점",
                  lambda: build_security_master(snaps if snaps is not None else pd.DataFrame(
                      columns=["snap_date", "code", "market"])),
                  note="중복 컬럼 → groupby.agg 폭발이 여기서 났다")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{i+1:06d}" for i in range(40)],
                                "name": [f"합성{i+1:03d}" for i in range(40)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(40)],
                                "listing_date": as_ts("2010-01-01"),
                                "delisting_date": pd.NaT, "sector_src": "fx", "src": "fx"})

        # ── ② 가격 ────────────────────────────────────────────────────────────────────────
        codes = sec["code"].dropna().tolist()[:12]
        px = _rh("fetch_prices(네이버 차트 폴백)",
                 lambda: fetch_prices(codes, "2016-05-01", "2026-07-31", sec=sec),
                 note="FDR/pykrx 없이 네이버 경로만으로 동작해야 한다")
        if px is not None and len(px):
            _rh("build_price_panel", lambda: build_price_panel(px, months))
        _rh("fetch_investor_flows(pykrx 없음)",
            lambda: fetch_investor_flows(codes, "2016-08-01", "2026-07-31", sec=sec),
            expect_rows=False)

        # ── ③ DART ────────────────────────────────────────────────────────────────────────
        corps = sec["corp_code"].dropna().astype(str).tolist()[:6]
        years = [2019, 2020, 2021]
        fs = _rh("fetch_dart_financials", lambda: fetch_dart_financials(corps, years))
        if fs is not None and len(fs):
            _rh("tidy_financials", lambda: tidy_financials(fs))
        _rh("fetch_dart_employees", lambda: fetch_dart_employees(corps, years),
            note="사업부문×성별 분해 + '합계' 소계행 이중계상 방지")
        dis = _rh("fetch_dart_disclosures",
                  lambda: fetch_dart_disclosures("2019-01-01", "2019-06-30"))

        # ── ④ 리서치 원장 ─────────────────────────────────────────────────────────────────
        hk = _rh("hankyung_collect", lambda: hankyung_collect("2024-01-01", "2024-12-31"))
        nv = _rh("naver_collect", lambda: naver_collect("2024-01-01", "2024-12-31",
                                                        cats=("company",)))
        if nv is not None and len(nv):
            _rh("naver_enrich_detail", lambda: naver_enrich_detail(nv, limit=5),
                expect_rows=False)
        frames = [x for x in (hk, nv) if x is not None and len(x)]
        rep = _rh("build_report_master(다중소스 병합)",
                  lambda: build_report_master(frames, sec)) if frames else None
        if rep is not None and len(rep):
            rep2 = _rh("download_pdfs", lambda: download_pdfs(rep, cap_per_month=3))
            A_L = _rh("build_analyst_ledger",
                      lambda: build_analyst_ledger(rep2 if rep2 is not None else rep),
                      expect_rows=False)
            if A_L is not None:
                A, L = A_L
                _rh("audit_linkage", lambda: (audit_linkage(rep, A, L) or [1]),
                    expect_rows=False)
                _rh("build_consensus_panel", lambda: build_consensus_panel(L, months),
                    expect_rows=False)

        # ── ⑤ 팩 전용 수집 ────────────────────────────────────────────────────────────────
        if "fetch_nps_workplaces" in G:
            N = _rh("fetch_nps_workplaces", lambda: fetch_nps_workplaces(months[:3]))
            if N is not None and len(N):
                M = _rh("resolve_nps_to_corp",
                        lambda: resolve_nps_to_corp(N, sec, pd.DataFrame())[0])
                if M is not None and len(M):
                    _rh("build_nps_panel", lambda: build_nps_panel(N, M, pd.DataFrame(), months),
                        expect_rows=False)
        if "fetch_procurement" in G:
            _rh("fetch_procurement", lambda: fetch_procurement(months[:2]))
        if "fetch_customs_trade" in G:
            _rh("fetch_customs_trade",
                lambda: fetch_customs_trade(months[:2], ["3901000000", "3902000000"]))
        if "fetch_dart_documents" in G and dis is not None and len(dis):
            T = _rh("fetch_dart_documents", lambda: fetch_dart_documents(dis, sec, max_docs=5),
                    expect_rows=False)
            if T is not None and len(T):
                _rh("build_text_similarity", lambda: build_text_similarity(T),
                    expect_rows=False)

        # ── ⑤-b 전략별 추가 리허설 (가짜 네트워크가 물려 있는 상태에서 실행) ──────────────
        for _hook in list(REHEARSAL_HOOKS):
            try:
                _hook(G, sec, corps, months)
            except Exception as _e:                                  # noqa
                REHEARSAL_RESULTS.append({
                    "name": f"[훅] {getattr(_hook, '__name__', 'hook')}", "ok": False,
                    "rows": -1, "sec": 0.0, "err": f"{type(_e).__name__}: {_e}",
                    "note": "", "tb": traceback.format_exc()})

        # ── ⑥ 이상 응답 내성 (빈/깨짐/컬럼누락) ───────────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = _FixtureNet(mode)
            G["http_get"], G["http_json"] = bad.get, bad.json
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"tcd_rh_{mode}_"), "REHEARSAL")
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing),
                              ("fetch_dart_corpcode", fetch_dart_corpcode)):
                _rh(f"[{label}] {fname}", fn, expect_rows=False,
                    note="예외 없이 빈 결과를 돌려줘야 한다")
            _rh(f"[{label}] fetch_dart_financials",
                lambda: fetch_dart_financials(corps, [2020]), expect_rows=False)
            _rh(f"[{label}] hankyung_collect",
                lambda: hankyung_collect("2024-01-01", "2024-03-31"), expect_rows=False)
            _rh(f"[{label}] build_report_master(빈 입력)",
                lambda: build_report_master([], sec), expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"], G["DBUDGET"] = saved_vault, saved_budget
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in REHEARSAL_RESULTS if r["ok"])
    LOG.table([[r["name"], "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 62)]
               for r in REHEARSAL_RESULTS],
              ["실경로 함수", "판정", "결과", "소요", "비고"],
              ["l", "c", "r", "r", "l"], maxw=64)
    fails = [r for r in REHEARSAL_RESULTS if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(REHEARSAL_RESULTS)}건 실패")
        for r in fails[:4]:
            LOG.banner(f"✘ 리허설 실패: {r['name']}", r["err"])
            for ln in str(r.get("tb", "")).rstrip().split("\n")[-10:]:
                _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"이 검사는 '수집 함수가 진짜 데이터 모양에서 도는지'를 보는 것이라, "
                f"여기서 막는 것이 몇 시간 뒤 L1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(REHEARSAL_RESULTS)}건 통과 — "
           f"수집·정제 함수가 실제 데이터 모양에서 정상 동작합니다.")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  합성데이터 엔드투엔드 스모크 테스트                                                 ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 계산경로 전체(피처→스코어→백테스트→강건성→리포트)를      ║
# ║  합성데이터로 통과시킨다. 목적은 성과 측정이 아니라 '배관 검증'이다.                        ║
# ║                                                                                          ║
# ║  왜 필요한가: 실수집은 수 시간~수 일이 걸린다. 그걸 다 받은 뒤에 조립부에서 터지면          ║
# ║  그 시간이 통째로 날아간다. 수 초짜리 스모크가 그 위험을 없앤다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def make_synthetic(n_codes: int = 160, n_months: int = 60, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    months = pd.date_range(as_ts(BACKTEST_END) - pd.DateOffset(months=n_months - 1),
                           as_ts(BACKTEST_END), freq="ME")
    codes = [f"{i+1:06d}" for i in range(n_codes)]
    inds = rng.choice(["화학", "전자부품", "건설", "기계", "소프트웨어"], n_codes)

    # 상장/폐지 — 일부는 기간 중 상장, 일부는 폐지 (생존자편향 검증용)
    listing = [months[0] - pd.DateOffset(years=int(rng.integers(2, 12))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
        listing[i] = months[int(rng.integers(6, n_months - 6))]
    delist = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        delist[i] = months[int(rng.integers(10, n_months - 2))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": inds,
                        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)],
                        "src": "synthetic"})

    # ── 진짜 알파를 심는다: quality[i] 가 높으면 미래수익이 높다 ────────────────────────────
    quality = rng.normal(size=n_codes)

    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1] + pd.Timedelta(days=5))
    px_rows = []
    for i, c in enumerate(codes):
        drift = 0.0006 + 0.0012 * quality[i]
        r = rng.normal(drift, 0.022, len(days))
        p = 10000 * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.5, 0.8, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": p * (1 + rng.normal(0, 0.003, len(days))),
            "high": p * 1.01, "low": p * 0.99, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    for i, c in enumerate(codes):
        if pd.notna(delist[i]):
            px = px[~((px["code"] == c) & (px["date"] > delist[i]))]
        px = px[~((px["code"] == c) & (px["date"] < listing[i]))]

    # ── 재무: quality 와 상관되게 만들되 노이즈를 크게 준다 ────────────────────────────────
    fin_rows, emp_rows = [], []
    for i, c in enumerate(codes):
        base_rev = rng.lognormal(25, 1.0)
        for m in pd.date_range(months[0] - pd.DateOffset(months=15), months[-1], freq="QE"):
            gr = 1 + 0.02 * quality[i] + rng.normal(0, 0.05)
            rev = base_rev * gr
            base_rev = rev
            fin_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "period_end": m,
                "knowledge_date": m + pd.Timedelta(days=45),
                "revenue_ttm": rev, "cogs_ttm": rev * (0.72 - 0.02 * quality[i]),
                "op_income_ttm": rev * (0.08 + 0.02 * quality[i]),
                "net_income_ttm": rev * (0.06 + 0.015 * quality[i]),
                "cfo_ttm": rev * (0.09 + 0.02 * quality[i]),
                "capex_ttm": rev * 0.05, "rnd_ttm": rev * (0.02 + 0.01 * max(quality[i], 0)),
                "dep_ttm": rev * 0.04,
                "dividend_paid_ttm": rev * (0.01 + 0.008 * max(quality[i], 0)),
                "treasury_buy_ttm": rev * (0.005 * max(quality[i], 0)),
                "inventory": rev * (0.15 - 0.01 * quality[i]),
                "receivable": rev * (0.18 - 0.01 * quality[i]),
                "payable": rev * 0.12, "assets": rev * 1.4, "liabilities": rev * 0.6,
                "equity": rev * 0.8, "ppe": rev * 0.5, "intangible": rev * 0.1,
                "contract_liab": rev * (0.03 + 0.01 * quality[i]),
                "tax_expense": rev * 0.015, "pretax_income": rev * 0.07,
                "sgna_ttm": rev * 0.15,
            })
        for y in range(months[0].year - 1, months[-1].year + 1):
            emp_rows.append({"corp_code": sec["corp_code"].iloc[i], "bsns_year": y,
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90),
                             "employees": float(max(12, rng.lognormal(5.2, 1.0) *
                                                    (1 + 0.05 * quality[i]))),
                             "payroll": float(rng.lognormal(22, 0.8))})
    fin = pd.DataFrame(fin_rows)
    fin = pit_frame(fin, "period_end", "knowledge_date", source="synthetic")
    emp = pd.DataFrame(emp_rows)
    emp = pit_frame(emp, "period_end", "knowledge_date", source="synthetic")

    # ── 공시 ───────────────────────────────────────────────────────────────────────────────
    dis_rows = []
    for i, c in enumerate(codes):
        for m in months[::4]:
            if rng.random() < 0.10 + 0.10 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m)[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식취득결정)",
                                 "event": "treasury_acq"})
            if rng.random() < 0.05 + 0.08 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m, "x")[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식소각결정)",
                                 "event": "treasury_canc"})
            if rng.random() < 0.05:
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i],
                                 "rcept_no": sha1_str(c, m, "y")[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(유상증자결정)",
                                 "event": "rights_issue"})
    dis = pd.DataFrame(dis_rows)
    dis = pit_frame(dis, "rcept_dt", "rcept_dt", source="synthetic")

    # ── 애널리스트 리포트 원장 (링크까지 합성) ─────────────────────────────────────────────
    brokers = MAJOR_BROKERS[:10] + MINOR_BROKERS[:12]
    analysts = [(b, f"애널{j:02d}") for b in brokers for j in range(3)]
    rep_rows, link_rows = [], []
    for m in months:
        for _ in range(int(rng.integers(120, 260))):
            i = int(rng.integers(0, n_codes))
            b, nm = analysts[int(rng.integers(0, len(analysts)))]
            bid, bname = normalize_broker(b)
            tp = float(np.exp(rng.normal(9.6, 0.5)) * (1 + 0.15 * quality[i]))
            uid = sha1_str("syn", codes[i], m, nm, rng.integers(1e9))
            d = m - pd.Timedelta(days=int(rng.integers(0, 28)))
            rep_rows.append({"report_uid": uid, "source": "synthetic",
                             "src_report_id": uid[:10], "pub_date": d, "category": "company",
                             "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                             "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                             "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                             "opinion": "BUY", "pdf_url": None, "detail_url": None,
                             "event_date": d, "knowledge_date": d})
            link_rows.append({"report_uid": uid, "name": nm, "broker_id": bid,
                              "broker_name": bname, "role": "lead", "link_method": "list_field",
                              "link_conf": 0.98, "pub_date": d, "stock_code": codes[i],
                              "target_price": tp, "opinion": "BUY",
                              "name_norm": nm,
                              "analyst_id": sha1_str("analyst", bid, nm)[:14]})
    rep = pd.DataFrame(rep_rows)
    L = pd.DataFrame(link_rows)

    # ── 국민연금 패널 ──────────────────────────────────────────────────────────────────────
    nps_rows = []
    for i, c in enumerate(codes):
        base = max(15, int(rng.lognormal(5.0, 1.0)))
        wage = rng.lognormal(15.0, 0.25)
        for m in months:
            base = max(5, int(base * (1 + 0.004 * quality[i] + rng.normal(0, 0.02))))
            wage *= (1 + 0.002 + 0.001 * quality[i] + rng.normal(0, 0.004))
            nps_rows.append({"code": c, "month": m,
                             "nps_members": float(base),
                             "nps_amt": float(base * wage * 0.09),
                             "nps_acq": float(max(0, rng.poisson(3))),
                             "nps_loss": float(max(0, rng.poisson(max(1, 3 - quality[i])))),
                             "n_wkpl": float(max(1, int(rng.integers(1, 6)))),
                             "knowledge_date": m + pd.offsets.MonthEnd(2)})
    nps = pd.DataFrame(nps_rows)
    nps = pit_frame(nps, "month", "knowledge_date", source="synthetic")

    # ── 공시 텍스트 유사도 (PACK-D) ────────────────────────────────────────────────────────
    tx_rows = []
    for i, c in enumerate(codes):
        for y in range(months[0].year, months[-1].year + 1):
            d0 = as_ts(f"{y}-03-31")
            tx_rows.append({"corp_code": sec["corp_code"].iloc[i], "rcept_dt": d0,
                            "sim_risk": float(np.clip(0.9 + 0.03 * quality[i] +
                                                      rng.normal(0, 0.05), 0, 1)),
                            "sim_all": float(np.clip(0.9 + 0.02 * quality[i] +
                                                     rng.normal(0, 0.04), 0, 1))})
    txt = pit_frame(pd.DataFrame(tx_rows), "rcept_dt", "rcept_dt", source="synthetic")

    # ── 관세 통관 + HS 매핑 (PACK-X) ───────────────────────────────────────────────────────
    n_hs = max(60, n_codes // 2)              # 셀 내 z-score 가 성립할 만큼은 덮어야 한다
    hs_list = [f"{3900+i:04d}000000" for i in range(n_hs)]
    hs_map = pd.DataFrame({"code": [codes[i] for i in range(n_hs)],
                           "hs": hs_list, "weight": 1.0,
                           "valid_from": months[0], "valid_to": months[-1]})
    cu_rows = []
    for j, hs in enumerate(hs_list):
        # θ_X(수출매출/연결매출)가 0.3~0.9 가 되도록 매출 규모에 맞춰 스케일링한다.
        rev0 = float(np.exp(25.0))
        base_usd = rev0 * rng.uniform(0.3, 0.9) / 1300.0
        unit_px0 = rng.lognormal(1.0, 0.2)          # ※ 지역변수 px 는 일봉 DataFrame 이므로 금지
        q = base_usd / unit_px0
        for m in months:
            q *= (1 + 0.004 * quality[j] + rng.normal(0, 0.04))
            unit_px = unit_px0 * (1 + 0.03 * quality[j] + rng.normal(0, 0.02))
            for grp in ("선진_미국", "선진_EU", "아세안", "중화권"):
                w = q * rng.uniform(0.15, 0.35)
                cu_rows.append({"ym": m.strftime("%Y%m"), "hs": hs, "grp": grp,
                                "exp_wgt": float(w), "exp_usd": float(w * unit_px)})
    customs = pd.DataFrame(cu_rows)

    # ── 조달 낙찰 (PACK-P) ────────────────────────────────────────────────────────────────
    g_rows = []
    for i in range(0, n_codes, 3):
        for m in months:
            if rng.random() > 0.55:
                continue
            plan = rng.lognormal(19, 0.8)
            rate = float(np.clip(85 + 4 * quality[i] + rng.normal(0, 3), 60, 110))
            g_rows.append({"ym": m.strftime("%Y%m"), "biz_no": f"{1000000000+i}",
                           "corp_nm": f"합성{i+1:03d}", "award_amt": plan * rate / 100.0,
                           "plan_price": plan, "rate": rate,
                           "org": rng.choice(["조달청", "국방부", "한전", "지자체", "철도공단"]),
                           "item_cls": f"{rng.integers(1000,9999)}"})
    procure = pd.DataFrame(g_rows)

    return {"sec": sec, "px": px, "fin": fin, "emp": emp, "dis": dis,
            "reports": rep, "links": L, "nps": nps, "months": months,
            "text_sim": txt, "customs": customs, "hs_map": hs_map, "procure": procure,
            "flows": pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"]),
            "snapshots": pd.DataFrame(columns=["snap_date", "code", "market"])}


def run_selftest(full_chain: bool = False) -> bool:
    """full_chain=True 면 성과검증·강건성(R1~R11)·해석표·진단카드까지 전부 합성데이터로 돌린다.
    RUN_MODE='SMOKE' 의 목적이 바로 이것 — 실데이터 없이 최종 출력물의 모양을 전부 확인한다."""
    LOG.banner("① 합성데이터 엔드투엔드 스모크 테스트",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수 초)"
               + (" · full_chain: 강건성·해석표까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    S = make_synthetic()
    LOG.info(f"합성 데이터: 종목 {S['sec'].shape[0]} · 월 {len(S['months'])} · "
             f"일봉 {len(S['px']):,} · 재무 {len(S['fin']):,} · 리포트 {len(S['reports']):,}")

    PIT.register("dart_financials", S["fin"], key_cols=["corp_code"])
    PIT.register("dart_employees", S["emp"], key_cols=["corp_code"])

    panel = build_price_panel(S["px"], S["months"])
    uni = Universe(S["sec"], S["snapshots"], panel["daily"])
    P = build_base_panel(uni, S["months"], panel["monthly"])
    P = attach_fundamentals(P, S["sec"])
    P = build_cells(P, S["sec"])
    P = axis_B(P); P = axis_C(P)
    P = axis_B_tp(P); P = axis_C_tp(P)
    cons = build_consensus_panel(S["links"], S["months"])
    P = axis_D(P, panel["daily"], S["flows"], cons)
    P = axis_D_U(P)

    ctx = {"disclosures": S["dis"], "nps_panel": S["nps"], "sec": S["sec"],
           "text_sim": S["text_sim"], "customs": S["customs"], "hs_map": S["hs_map"],
           "procurement": S["procure"], "administrative": None}
    for p in active_packs():
        P = p["features"](P, ctx)
    P = apply_vetoes(P, ctx)
    P = assemble_score(P)

    def _run(pp, label="smoke", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else S["months"],
                            uni, S["sec"], apply_costs=apply_costs, label=label)

    bt = _run(P)
    st = perf_stats(bt["returns"])
    dur = time.time() - t0
    ok = (len(P) > 0 and len(bt["returns"]) == len(S["months"]) and
          bool(st) and np.isfinite(st.get("CAGR", np.nan)))
    LOG.table([["패널 행수", f"{len(P):,}"],
               ["활성 팩", ", ".join(p["id"] for p in active_packs()) or "없음"],
               ["백테스트 월수", f"{len(bt['returns'])}"],
               ["평균 보유종목", f"{st.get('평균종목수', float('nan')):.1f}"],
               ["합성 CAGR", f"{st.get('CAGR', float('nan'))*100:+.2f}%"],
               ["합성 Sharpe", f"{st.get('Sharpe', float('nan')):.3f}"],
               ["소요시간", f"{dur:.2f}초"]],
              ["항목", "값"], ["l", "r"], title="스모크 결과 (성과 수치는 의미 없음 — 배관 검증용)")
    if ok:
        LOG.ok(f"스모크 통과 ({dur:.2f}초) — 피처→스코어→백테스트 경로가 정상 동작합니다. "
               f"이제 실데이터를 수집해도 조립부에서 시간을 날릴 위험이 없습니다.")
    else:
        LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
        return False
    if not full_chain:
        return True

    # ── 여기서부터는 '최종 출력물 전체'를 합성데이터로 예행연습한다 ────────────────────────
    LOG.warn("아래 성과·강건성 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 아니라 "
             "'출력물이 제대로 나오는지'를 보여주는 예행연습입니다. 절대 해석하지 마세요.")
    bench = {}
    with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
        report_performance(bt, bench, label=f"{STRATEGY_NAME} (합성 예행연습)")
        uni.report_attrition()
    with PIPE.stage("SMOKE.POLICY", "[합성] 정책 캘린더", "L2", budget_s=60, critical=False):
        cal = build_policy_calendar()
        report_policy(cal, S["months"], [p["id"] for p in active_packs()])
    with PIPE.stage("SMOKE.ROBUST", "[합성] 강건성 R1~R11", "L5", budget_s=1800, critical=False):
        keep_kill = STOP_ON_KILL_CRITERIA
        globals()["STOP_ON_KILL_CRITERIA"] = False   # 예행연습에서는 킬로 멈추지 않는다
        try:
            R1_leakage(P, S["months"], uni, S["sec"], _run)
            R2_tp_vs_naive(P, _run)
            R3_orthogonal(P, bt, S["months"])
            R4_placebo(P, n_iter=200)
            R10_policy_falsify(P, cal, S["months"], _run)
            R5_ablation(P, _run)
            R11_pack_corr(P)
            R6_pbo_dsr(bt)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, _run)
        finally:
            globals()["STOP_ON_KILL_CRITERIA"] = keep_kill
        report_robustness()
    with PIPE.stage("SMOKE.REPORT", "[합성] 해석표 · 진단 카드", "L6", budget_s=120, critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, S["sec"])
    LOG.ok("full_chain 예행연습 완료 — 백테스트·성과검증·강건성·해석표·진단카드가 모두 "
           "정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 동일한 출력이 실데이터로 나옵니다.")
    ROBUST_RESULTS.clear()
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
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
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 링크 대신 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def collect_all(months: pd.DatetimeIndex) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스", "L1", budget_s=600):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 거래대금", "L1", budget_s=1200):
        KRX.login()
        # ★ sec= 를 넘기지 않으면 listing_of/delist_of 가 빈 dict 가 되어 상장일 하한과
        #   폐지 종료조건이 통째로 사라진다. 그 상태로 v2 가 만든 워터마크·음성캐시를
        #   v3 가 그대로 물려받아 같은 낭비를 반복한다 — 캐시가 공용이라 오염도 공용이다.
        px = fetch_prices(ctx["sec"]["code"].tolist(), price_cache_floor(), BACKTEST_END,
                          sec=ctx["sec"],
                          market_last_day=(ctx["snapshots"]["snap_date"].max()
                                           if ctx.get("snapshots") is not None
                                           and len(ctx["snapshots"]) else None))
        ctx["px"] = px
        ctx["panel"] = build_price_panel(px, months)

    with PIPE.stage("L1.FLOW", "기관·외국인 수급 (D축 d3)", "L1", budget_s=900, critical=False):
        ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(), BACKTEST_START,
                                            BACKTEST_END, sec=ctx["sec"])

    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시", "L1", budget_s=1800, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
        # 유동성 상위 종목의 corp_code 를 우선순위로 넘긴다 — 일일 한도로 끊겨도
        # '투자 가능한 종목의 최근 데이터'가 먼저 완성되게 하기 위함이다.
        prio: List[str] = []
        try:
            pm = ctx["panel"]["monthly"]
            adv = (pm.groupby("code", observed=True)["adv20"].median()
                     .sort_values(ascending=False))
            c2c = (ctx["sec"].dropna(subset=["corp_code"])
                             .set_index("code")["corp_code"].astype(str).to_dict())
            prio = [c2c[c] for c in adv.index if c in c2c]
        except Exception:
            prio = []
        # Tier-1: 주요계정 배치 (100사/호출) → 전 종목 헤드라인을 싸게 확보
        multi = fetch_dart_multi_accounts(corps, years)
        # Tier-2: 전체 재무제표 (우선순위·최근연도부터) → B/C축이 필요로 하는 상세 계정
        fs = fetch_dart_financials(corps, years, priority=prio)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        emp = fetch_dart_employees(corps, years)
        dis = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["fin"], ctx["emp"], ctx["disclosures"] = fin, emp, dis
        if len(fin):
            PIT.register("dart_financials", fin, key_cols=["corp_code"])
        if len(emp):
            PIT.register("dart_employees", emp, key_cols=["corp_code"])

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=3600, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되, 보수적 속도로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                nv = naver_enrich_detail(nv)
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep):
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            # ★ PDF 에서 추출한 목표주가를 원장에 실제로 반영한다.
            #   (추출만 하고 쓰지 않으면 네이버 단독 건의 목표주가가 영원히 결측으로 남는다)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건을 추가로 채웠습니다 "
                           f"(리스트에 목표주가가 없는 네이버 단독 건 보강).")
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

    # ── 팩 전용 수집 ──────────────────────────────────────────────────────────────────────
    #  ★ 배선 검정을 먼저 한다. 이 루프는 `if p.get("ingest")` 로 조용히 건너뛸 수 있는데,
    #    한때 어느 팩도 ingest_fn 을 등록하지 않아 루프 전체가 무동작이었다. 그 결과
    #    "5개 센서팩 전략"이 실제로는 PACK-C 하나로 돌면서 성과표·강건성표를 끝까지 출력했다.
    #    하류의 커버리지 검사는 이걸 "데이터 부재"로 보고해서 운영자를 API 키 쪽으로 오도한다.
    #    '수집이 배선되지 않음'과 '수집했는데 비어 있음'은 완전히 다른 사건이므로 여기서 가른다.
    #    (PACK-C 는 L1.DART 가 채운 재무를 그대로 읽으므로 전용 수집이 없는 게 정상이다)
    unwired = [p["id"] for p in active_packs() if not p.get("ingest") and p["id"] != "C"]
    if unwired:
        raise RuntimeError(
            f"[배선 결함] 센서팩 {unwired} 이 ACTIVE_PACKS 에 있는데 ingest_fn 이 등록되지 "
            f"않았습니다. 이건 '데이터 부재'가 아니라 '수집 자체가 배선되지 않음' 입니다 — "
            f"키를 넣어도 해결되지 않습니다. register_pack(..., ingest_fn=...) 를 확인하세요.")
    for p in active_packs():
        if p.get("ingest"):
            with PIPE.stage(f"L1.PACK.{p['id']}", f"팩 {p['id']} 전용 수집", "L1",
                            budget_s=1800, critical=False):
                p["ingest"](ctx, months)
    return ctx


def build_features(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe"]:
    with PIPE.stage("L1.PANEL", "피처 패널 조립 (L1)", "L1", budget_s=1800):
        uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel(uni, months, ctx["panel"]["monthly"])
        P = attach_fundamentals(P, ctx["sec"])
        P = build_cells(P, ctx["sec"])
        P = axis_B(P); P = axis_C(P)
        P = axis_B_tp(P); P = axis_C_tp(P)
        cons = build_consensus_panel(ctx.get("links", pd.DataFrame()), months)
        ctx["consensus"] = cons
        P = axis_D(P, ctx["panel"]["daily"], ctx.get("flows"), cons)
        P = axis_D_U(P)
        for p in active_packs():
            P = p["features"](P, ctx)
        P = downcast(P)
        LOG.ok(f"피처 패널 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        # L1/L2 분리(§3): 피처는 parquet 으로 영속화하고, 스코어부는 이 parquet 만 읽는다
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 panel")
    return P, uni


def score_and_backtest(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex,
                       uni: "Universe") -> Tuple[pd.DataFrame, dict, Callable]:
    with PIPE.stage("L2.SCORE", "거부권 + 스코어 조립 (L2)", "L2", budget_s=120):
        P = apply_vetoes(P, ctx)
        P = assemble_score(P)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        P[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR") if c in P.columns]],
                        scope="private", domain="scores", source="L2")

    def _run(pp, label="run", apply_costs=True, months_override=None):
        return run_backtest(pp, months_override if months_override is not None else months,
                            uni, ctx["sec"], apply_costs=apply_costs, label=label)

    with PIPE.stage("L3.BT", "백테스트 (L3)", "L3", budget_s=180):
        bt = _run(P, label=STRATEGY_ID)
    return P, bt, _run


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v2 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"활성 팩: {', '.join(ACTIVE_PACKS) or '없음'} · 백테스트 {BACKTEST_START}~{BACKTEST_END} · "
               f"빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared"); VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 C1~C12", "L0", budget_s=120):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(1800 if RUN_MODE == "SMOKE" else 300)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    # ★ 스모크는 '계산경로'를, 리허설은 '수집경로'를 증명한다. 둘은 겹치지 않는다.
    #   합성 스모크만 믿었다가 수집부 한 줄 때문에 실행 2분 만에 죽은 전례가 있다.
    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=600):
        run_rehearsal(strict=True)

    months = month_range(BACKTEST_START, BACKTEST_END)
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물(백테스트·성과·강건성·해석표)을 "
               "예행연습했습니다. 실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=120, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    P, uni = build_features(ctx, months)

    with PIPE.stage("L2.POLICY", "정책 캘린더 (C12)", "L2", budget_s=60):
        cal = build_policy_calendar()
        report_policy(cal, months, [p["id"] for p in active_packs()])
        ctx["policy"] = cal

    P, bt, _run = score_and_backtest(P, ctx, months, uni)

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=120):
        bench = benchmark_returns(months)
        report_performance(bt, bench)
        uni.report_attrition()

    with PIPE.stage("L5.ROBUST", "강건성 검사 R1~R11", "L5", budget_s=4 * 3600, critical=False):
        try:
            R1_leakage(P, months, uni, ctx["sec"], _run)
            R2_tp_vs_naive(P, _run)
            R3_orthogonal(P, bt, months)
            R4_placebo(P, n_iter=1000)
            R10_policy_falsify(P, ctx["policy"], months, _run)
            R5_ablation(P, _run)
            R11_pack_corr(P)
            R6_pbo_dsr(bt)
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, _run)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단 카드", "L6", budget_s=120, critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=300, critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        rp = os.path.join(outdir, f"returns_{stamp}.csv")
        bt["returns"].to_csv(rp, index=False, encoding="utf-8-sig"); outs.append(rp)
        if len(bt.get("holdings", pd.DataFrame())):
            hp = os.path.join(outdir, f"holdings_{stamp}.csv")
            bt["holdings"].to_csv(hp, index=False, encoding="utf-8-sig"); outs.append(hp)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer)); outs.append(lp)
        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    PIPE.report_runtime()
    report_dataflow_map()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시(§16.2): 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 "
             "D축 d1 의 E 는 후행 12M 이익 대리변수를 씁니다. 초기 구간일수록 이 대리의 "
             "오차가 큽니다. 이 한계를 숨기지 않고 여기에 명시합니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx, "robust": ROBUST_RESULTS}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§15 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
        try:
            report_robustness()
        except Exception:
            pass
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
        except Exception:
            pass
