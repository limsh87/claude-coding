#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  U250 대체데이터 팩터 독립 검정  —  명세서 v1.0 구현체
#  u250-20260812-3219e74
#
#  게이트 적용 U250/U500 유니버스에 대해 4개 후보 팩터(F1~F4)의 "독립적" 유효성을 검정한다.
#  팩터를 결합하지 않는다. 4개를 각각 단독으로 얹어 베이스라인 대비 순수익 초과분만 측정한다.
#
#  ★ 이 파일은 사전등록(pre-registration) 명세의 실행체다.
#    임계값·기간·N값은 1차 결과를 본 뒤 수정할 수 없다(§8 금지사항).
#    코드가 그 규율을 강제한다 — SPEC 상수는 SpecLock 으로 잠기고, OOS 구간은
#    Step 7 이전에 접근하면 예외로 막힌다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   `python u250_factor_test_v1.py`  또는 Colab/JupyterLab 한 셀에 붙여넣고 실행.
#
#     Step 0  캐시 하베스트  ← ★구글드라이브·로컬 D:·깃허브 캐시를 먼저 전부 훑는다
#     Step 1  Phase 0 커버리지 진단 4종      → 통과 팩터 확정
#     Step 2  베이스라인 B1~B4 산출          → 허들 확정
#     Step 3~6 F1~F4 단독 백테스트 (IS)
#     Step 7  IS 통과 팩터만 OOS 개봉        → G4
#     Step 8  전체 시행수(120) 기준 DSR/PBO  → G5
#     Step 9  용량 시뮬레이션                → MASTER_SCORECARD.md
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다  (명세서 §0 코드 작성 규약 ①)
#
#   ▸ 키가 없으면 그 데이터원만 건너뛰고 "왜 건너뛰었는지"를 한글로 명시합니다.
#   ▸ ★캐시가 있으면 키 없이도 대부분 재현됩니다. 이 코드는 캐시를 최우선으로 씁니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI ─────────────────────────────────────────────────────────────────
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료. 일 20,000건 호출 제한. F1(자본거래)·F2(내부자)·F4(공급계약)의 원천입니다.
DART_API_KEY = ""

# ── ② 공공데이터포털 (F4 보조 — 나라장터 낙찰정보) ──────────────────────────────────────────
#    발급: https://www.data.go.kr → 로그인 → API 상세 → [활용신청]
#    ★ 반드시 "일반 인증키(Decoding)" 를 붙여넣으세요. Encoding 키(%2B,%3D)는 이중 인코딩 오류.
DATA_GO_KR_KEY = ""

# ── ③ KRX 데이터 마켓플레이스 (선택) ────────────────────────────────────────────────────────
#    비워도 됩니다. 가격·시총은 캐시와 공개 경로로 성립합니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""
KRX_OPENAPI_KEY    = ""

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   ★★★ 캐시 최우선 (CACHE-FIRST) — 이 절이 이 프로그램의 1원칙이다 ★★★
#
#   "거의 다 데이터가 수집되어 있으니 굳이 신규수집할 필요가 거의 없다."
#   그래서 이 코드는 신규 수집을 '기본'이 아니라 '예외'로 다룬다:
#
#     ① 아래 경로들을 전부 재귀 스캔해서 쓸 수 있는 캐시를 목록화한다 (CacheLake)
#     ② 역할(가격/시총/종목마스터/DART공시/재무…)별로 최적 소스를 고른다
#     ③ 커버리지 구멍이 남았을 때만, 그 구멍만큼만 네트워크를 친다
#     ④ COLLECT_POLICY="NEVER" 로 두면 네트워크를 아예 쓰지 않는다
#
#   ★ 기존 캐시는 절대 삭제·덮어쓰지 않는다. 읽고, 경로만 등록한다(adopt-by-reference).
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ④-1 산출물 루트 (명세서 §0 실행 환경 규약) ──────────────────────────────────────────────
BASE_DIR   = r"D:\quant\u250_factor_test"      # 전 산출물 루트
CACHE_DIR  = ""                                 # 비우면 {BASE_DIR}\cache
LOG_DIR    = ""                                 # 비우면 {BASE_DIR}\logs
OUTPUT_DIR = ""                                 # 비우면 {BASE_DIR}\outputs

# ── ④-2 캐시 탐색 경로 ──────────────────────────────────────────────────────────────────────
#    ▸ 존재하지 않는 경로는 조용히 건너뜁니다. 넉넉히 적어두세요.
#    ▸ 로컬 D: 드라이브 — 이전 프로젝트(KR_QUANT_SUITE_V1, W012 등)가 남긴 캐시를 여기서 줍습니다.
CACHE_SEARCH_DIRS = [
    r"D:\quant",                      # ★ 로컬 D 드라이브 퀀트 루트 (재귀 스캔)
    r"D:\quant\cache",
    r"D:\quant\data",
    r"D:\data",
    "./tcd_cache",                    # 이 저장소의 로컬 캐시 폴백
    "~/quant",
]
#    ▸ 구글드라이브 — Colab 이면 자동 마운트, 로컬 동기화 폴더면 그 경로를 그대로 씁니다.
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"          # 공용 인덱스 — 다른 전략이 모은 원본을 그대로 재활용
GDRIVE_PRIVATE_NS = "u250_factor"      # 전용 인덱스 — 이 검정의 산출물
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/quant",
    "/content/drive/MyDrive/quant_cache",
    "/content/drive/MyDrive/u250",
    r"G:\내 드라이브\tcd_cache",        # Windows 구글드라이브 동기화 기본 경로
    r"G:\My Drive\tcd_cache",
]
LOCAL_CACHE_ROOT = "./u250_cache"      # 드라이브가 없을 때의 폴백 루트

#    ▸ 깃허브 — 공개 raw 캐시. (owner/repo, branch, 하위경로) 를 적으면 파일목록을 받아 재활용.
GITHUB_CACHE_REPOS = [
    ("FinanceData/fdr_krx_data_cache", "master", "data"),   # 상장/폐지 목록 (로그인 불필요)
]
GITHUB_TOKEN = ""                      # 비공개 저장소를 쓸 때만. 없으면 공개 저장소만.

# ── ④-3 수집 정책 ───────────────────────────────────────────────────────────────────────────
#    "GAP_ONLY" : ★기본. 캐시로 못 채운 구멍만 신규 수집한다.
#    "NEVER"    : 네트워크 완전 차단. 캐시만으로 돌린다 (재현·오프라인 검증용).
#    "REFRESH"  : 캐시가 있어도 최신 구간만 갱신 (권장하지 않음 — 느립니다)
COLLECT_POLICY = "GAP_ONLY"
CACHE_SCAN_MAX_DEPTH = 6               # 재귀 스캔 최대 깊이 (너무 키우면 스캔이 느려집니다)
CACHE_SCAN_MAX_FILES = 400_000         # 안전 상한

# ── ⑤ 유니버스 (명세서 §1 — 동결. 수정 금지) ────────────────────────────────────────────────
#    기존 KR_QUANT_SUITE_V1.py 4380–4394행의 적격성 게이트를 그대로 사용한다.
#    ※ 그 파일이 이 실행 환경에 없으면 아래 상수로 재현하고, 원본이 있으면
#      GATE_SOURCE_FILE 을 지정해 실제 상수를 파싱·대조합니다(불일치는 로그에 기록).
GATE_SOURCE_FILE   = r"D:\quant\KR_QUANT_SUITE_V1.py"
GATE_MIN_AMOUNT    = 100_000_000       # 거래대금 ≥ 1억원
GATE_MIN_LIST_DAYS = 180               # 상장 ≥ 180일
UNIV_MAIN_N        = 250               # 주 유니버스: 시총 하위 250
UNIV_AUX_N         = 500               # 보조 유니버스: 시총 하위 500

#    리밸런싱 주기 — "기존 구현과 동일 주기 유지"(§1).
#    ▸ 선행 문서의 NW lag 규약 `ceil(보유세션 / 4.7063)` 은 '주' 단위 수익률 계열을 뜻하므로
#      기본값을 주간(금요일)으로 둔다. 월간 구현이었다면 "M" 으로 바꾸면 전 산출물이 따라간다.
#      어느 쪽이든 실행 로그와 run_log 에 명시되어 사후에 구분 가능하다.
REBAL_FREQ = "W-FRI"                   # "W-FRI"(주간) | "M"(월말)

#    패널 기간 — "기존 패널 전 구간". 비워두면 캐시가 실제로 덮는 전 구간을 자동 사용.
PANEL_START = ""                       # 예: "2016-08-01"
PANEL_END   = ""                       # 예: "2026-07-31"

# ── ⑥ 성능 / 자원 (§0 규약 ②: 기본 병렬화) ──────────────────────────────────────────────────
N_WORKERS_IO   = 16                    # I/O 바운드 → ThreadPoolExecutor
N_WORKERS_CPU  = 0                     # CPU 바운드 → ProcessPoolExecutor (0 = 코어수 자동)
MEM_BUDGET_GB  = 6.0
RATE_LIMIT_QPS = {"dart": 8.0, "datagokr": 5.0, "krx": 2.0, "naver": 3.0,
                  "generic": 3.0, "github": 5.0, "hankyung": 2.5, "kind": 2.0,
                  "customs": 3.0}

# ── ⑦ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 Step 0~9 전 산출물을 예행연습. 네트워크·키 불필요, 수십 초.
#              계산경로(커버리지→베이스라인→팩터→게이트→스코어카드)를 실데이터 전에 증명한다.
#    "FULL"  : 스모크 → 캐시 하베스트 → 부족분 수집 → 전체 검정  (기본)
#    "CACHED": 스모크 → 캐시만으로 전체 검정 (COLLECT_POLICY 를 NEVER 로 강제)
RUN_MODE = "FULL"

SEED    = 20260812                     # 결정성: 모든 난수는 이 시드에서 파생 (B4·플라시보 포함)
VERBOSE = True

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 사전등록된 명세 상수입니다 — 결과를 보고 바꾸지 마십시오(§8).
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "U250_FACTOR_TEST"
STRATEGY_NAME = "U250 대체데이터 팩터 독립 검정 v1.0"
BUILD_VERSION = "u250-20260812-3219e74"
SPEC_VERSION  = "1.0"
ACTIVE_PACKS  = ["F1", "F2", "F3", "F4"]


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

# ★ pykrx 1.2.8 의 get_auth_session() 은 모듈 전역 _auth_session 에 대해 '락 없는 검사-후-생성'
#   이다. 스레드 N 개가 동시에 None(또는 만료)을 보면 N 번 로그인하고, KRX 는 중복 로그인을
#   skipDup 으로 처리하며 앞선 세션을 강제 종료한다. 살아남는 건 1개, 나머지는 죽은 쿠키로
#   요청해 JSON 대신 로그인 HTML 을 받는다("Expecting value: line 13 column 1"). 만료(3600-300초
#   =55분) 갱신도 같은 무락 경로라, 공유 세션 하나에 대해 여러 스레드가 동시에 refresh() 를
#   돌리면 서로가 쓰고 있는 소켓을 close() 한다.
#   KRXGate(10_ingest_universe.py)는 자기 자신을 통해 들어오는 호출만 직렬화한다. 가격·수급
#   수집처럼 별도 스레드풀에서 pykrx 를 직접 부르는 호출까지 다 막으려면, 게이트가 아니라
#   라이브러리 경계에서 막아야 한다 — 호출 지점을 하나라도 놓치면 폭풍이 되살아나기 때문이다.
#   webio 는 함수를 '이름으로' import 했으므로(from ... import get_auth_session) auth 모듈만
#   패치하면 효과가 없다 — 두 바인딩을 모두 교체한다. 데이터 호출 자체는 계속 병렬로 둔다.
if pykrx_stock is not None:
    try:
        import pykrx.website.comm.auth as _kauth
        import pykrx.website.comm.webio as _kwebio

        _KRX_AUTH_LK = threading.RLock()
        _KRX_AUTH_FAIL = [0.0]          # 음성 캐시 — 틀린 자격증명 재시도 폭주 억제 (10분)
        _kx_orig_get_auth = _kauth.get_auth_session

        def _kx_get_auth_locked():
            with _KRX_AUTH_LK:
                if _KRX_AUTH_FAIL[0] and (time.time() - _KRX_AUTH_FAIL[0]) < 600:
                    return None
                try:
                    s = _kx_orig_get_auth()
                except Exception:
                    s = None
                if s is None and os.environ.get("KRX_ID") and os.environ.get("KRX_PW"):
                    _KRX_AUTH_FAIL[0] = time.time()
                else:
                    _KRX_AUTH_FAIL[0] = 0.0
                return s

        _kauth.get_auth_session = _kx_get_auth_locked
        _kwebio.get_auth_session = _kx_get_auth_locked
    except Exception:
        pass

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


_DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
_DATE_NULLS = ("", "nan", "nat", "none", "null", "-", "--")


def as_ts_series(s, where: str = "") -> pd.Series:
    """★ pandas 2.x 는 첫 비결측 원소 하나로 날짜 포맷을 추론하고, 그 포맷에 맞지 않는 값은
    errors="coerce" 때문에 예외도 경고도 없이 전부 NaT 가 된다 — 다수/소수 무관, 행 0 이 이긴다.
    폐지일처럼 소스가 섞일 수 있는 컬럼(FDR GitHub 캐시는 ISO, KRX 라이브 응답은 슬래시)에서
    이건 곧 생존자편향이다. 빠른 경로가 값을 죽였을 때만 포맷별로 재파싱하고, 복구/실패
    건수를 반드시 로그로 남긴다 — 01_bootstrap 의 warnings.filterwarnings("ignore") 때문에
    pandas 자체 경고도 안 뜨므로 여기서 못 잡으면 아무도 못 잡는다."""
    raw = pd.Series(s)
    out = pd.to_datetime(raw, errors="coerce")
    if len(raw) and raw.dtype == object and out.isna().any():
        txt = raw.astype(str).str.strip()
        miss = out.isna() & ~txt.str.lower().isin(_DATE_NULLS)
        n0 = int(miss.sum())
        if n0:
            out = out.copy()
            for f in ("mixed",) + _DATE_FMTS:
                # to_numpy() — 라벨 정렬을 쓰면 중복 인덱스에서 어긋난다
                out.loc[miss] = pd.to_datetime(raw[miss], errors="coerce", format=f).to_numpy()
                miss = miss & out.isna()
                if not miss.any():
                    break
            n1 = int(miss.sum())
            if n0 - n1:
                LOG.warn(f"[{where or 'as_ts_series'}] 날짜 {n0 - n1:,}/{len(raw):,}건이 첫 행과 "
                         f"형식이 달라 기본 추론에서 NaT 가 될 뻔했습니다 — 형식별 재파싱으로 "
                         f"복구했습니다. 소스의 날짜 형식이 섞여 있습니다.")
            if n1:
                LOG.warn(f"[{where or 'as_ts_series'}] 날짜 파싱 실패 {n1:,}/{len(raw):,}건 — "
                         f"예: {txt[miss].head(5).tolist()}")
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
    # ★ \D 를 지우고 zfill 하면 안 된다. 비(非)주권 단축코드가 '살아있는 다른 종목'으로
    #   둔갑한다. '008465W'(신주인수권증권) → '008465', '00846W' → '000846',
    #   'J00123' → '000123'. 상장폐지 피드(MDCSTAT23801)에는 신주인수권증권/증서·수익증권이
    #   대량으로 섞여 있는데, SecuGroup 필터가 없어 전부 들어온다. 그 권리행사기간
    #   만료일이 멀쩡히 상장돼 있는 회사의 delisting_date 로 집계되고
    #   (build_security_master 의 agg 는 delisting_date="max") 그 회사가 유니버스에서
    #   영구 제외된다 — 게다가 이 손실은 절단된 코드가 '유효해 보이므로' 어떤 카운터에도
    #   안 걸린다(오히려 겹치면 n_dupe 를 늘려 "중복"으로 오귀속된다).
    #   복구는 '앞자리 0 이 날아간 순수 정수 코드'(예: KIND 의 5930)에만 허용한다 —
    #   문자가 하나라도 섞여 있으면 그건 절단 대상이지 zero-padding 대상이 아니다.
    if s.isdigit() and len(s) < 6:
        cand = s.zfill(6)
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
# ║  사전등록 상수 (SPEC) + 동결 장치                                                          ║
# ║                                                                                          ║
# ║  명세서 §8 금지사항은 "그러지 않겠다"는 약속이 아니라 구조여야 한다.                        ║
# ║   · SPEC 은 SpecLock 으로 감싼다 → 실행 중 대입하면 즉시 예외                              ║
# ║   · 민감도 격자는 팩터당 4개로 상한이 걸려 있다 → 5개째를 등록하면 예외                     ║
# ║   · OOS 구간은 OOSSeal 이 잠그고, Step 7 에서만 열린다 → 조기 열람이 예외로 잡힌다          ║
# ║   · 문서 SHA256 을 run_log 에 남긴다 (선행 문서 규약)                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝


class SpecViolation(Exception):
    """사전등록 위반. 코드를 고치기 전에 명세 개정(버전 상향)을 먼저 하라는 뜻."""


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
                f"명세서 §8-3(1차 결과를 본 뒤 재조정 금지) 위반입니다. "
                f"정말 바꿔야 한다면 코드가 아니라 명세서 버전을 올리고 그 이력을 남기세요.")
        super().__setitem__(k, v)

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# ── §1 유니버스 ─────────────────────────────────────────────────────────────────────────────
SPEC_UNIV = SpecLock("UNIVERSE", dict(
    min_amount_krw=GATE_MIN_AMOUNT,      # 거래대금 ≥ 1억원
    min_listing_days=GATE_MIN_LIST_DAYS,  # 상장 ≥ 180일
    main_n=UNIV_MAIN_N,                   # 시총 하위 250 (주)
    aux_n=UNIV_AUX_N,                     # 시총 하위 500 (보조)
    weighting="EW",                       # 동일가중
))

# ── §4 공통 규약 ────────────────────────────────────────────────────────────────────────────
SPEC_N_VALUES   = (30, 50, 80)     # 랭킹형·이벤트형 N. 주 명세는 50
SPEC_N_PRIMARY  = 50
SPEC_UNCOV_MODES = ("neutral", "exclude")   # 미커버 처리 2방식 — 둘 다 산출
#   neutral : 선별 대상에서 빼지 않는다 — 랭킹형은 중앙값 점수, 필터형은 통과(유지)
#   exclude : 미커버 종목을 후보에서 제외한다
SPEC_PIT_LAG_BDAYS = 1                   # 공시 접수일 + 1영업일부터 사용 가능

# ── §3 Phase 0 통과 기준 ────────────────────────────────────────────────────────────────────
SPEC_COV = SpecLock("PHASE0", dict(pass_median=80, hold_median=40))

# ── §6.1 표본 분할 ──────────────────────────────────────────────────────────────────────────
SPEC_IS_FRACTION = 0.60           # 탐색구간(IS) = 앞 60%
SPEC_WF_TRAIN_M  = 36             # walk-forward 학습 36개월
SPEC_WF_TEST_M   = 12             # 검정 12개월, 12개월 롤

# ── §6.2 시행 횟수 (다중검정 통제) ──────────────────────────────────────────────────────────
#   4팩터 × (주명세 1 + 민감도 4) × N값 3개 × 미커버처리 2방식 = 120
#   ★ DSR 계산 시 팩터별이 아니라 반드시 이 전체값을 쓴다(§6.2).
SPEC_TRIALS_TOTAL = 4 * 5 * 3 * 2

# ── §6.3 판정 게이트 ────────────────────────────────────────────────────────────────────────
SPEC_GATE = SpecLock("GATES", dict(
    g1_random_pct=0.95,          # B4 무작위 분포 상위 5% 밖
    g2_excess_cagr=0.030,        # B2 대비 순수익 초과 CAGR ≥ +3.0%p (AUM 1억)
    g2_aum_krw=100_000_000,
    g3_drop_best_years=2,        # 최고 2개 연도 제외 후에도 초과수익 > 0
    g4_oos_ratio=0.50,           # OOS 초과수익 ≥ IS 의 50%
    g5_dsr_min=0.0, g5_pbo_max=0.5,
    g6_quintile_monotone=True,   # 랭킹형 한정
    g7_placebo_shift_bdays=-60,  # P1: 신호일 −60영업일 시프트
))
SPEC_B4_SIMS = 1000              # §2 B4: 무작위 N종목 1,000회 시뮬

# ── §5 비용 모형 ────────────────────────────────────────────────────────────────────────────
#   증권거래세: 연도별 실제 세율표. 하드코딩 금지 → 테이블로 관리하고 근거를 함께 남긴다.
#   (매도 시에만 부과. 코스피는 농특세 0.15% 포함 실효세율, 코스닥은 거래세만)
SPEC_TAX_TABLE = [
    # (시행 시작연도, KOSPI 매도 실효율, KOSDAQ 매도 실효율, 근거)
    (2016, 0.00300, 0.00300, "증권거래세법 — 유가증권 0.15%+농특세 0.15%, 코스닥 0.30%"),
    (2019, 0.00300, 0.00250, "2019.06 인하 — 유가증권 0.10%+농특세 0.15%, 코스닥 0.25%"),
    (2021, 0.00230, 0.00230, "2021.01 인하 — 유가증권 0.08%+농특세 0.15%, 코스닥 0.23%"),
    (2023, 0.00200, 0.00200, "2023.01 인하 — 유가증권 0.05%+농특세 0.15%, 코스닥 0.20%"),
    (2024, 0.00180, 0.00180, "2024.01 인하 — 유가증권 0.03%+농특세 0.15%, 코스닥 0.18%"),
    (2025, 0.00150, 0.00150, "2025.01 인하 — 유가증권 0.00%+농특세 0.15%, 코스닥 0.15%"),
]
SPEC_COST = SpecLock("COST", dict(
    commission_roundtrip=0.0003,     # 위탁수수료 왕복 0.03%
    spread_fallback_bp={             # 종목별 실측 미가용 시 시총분위별 보수 고정값(편도 bp)
        1: 90.0, 2: 70.0, 3: 55.0, 4: 40.0, 5: 30.0},
    spread_fallback_basis="마이크로캡 호가단위/가격 기반 보수 추정 — 실측 대체 시 로그에 명시",
    impact_coef=0.10,                # 시장충격 = coef × sqrt(주문금액 / ADV)
    slippage_bp=15.0,                # 체결가정: 리밸일 종가 대비 불리한 방향 고정 슬리피지
))
SPEC_AUM_LADDER = (10_000_000, 100_000_000, 300_000_000, 1_000_000_000)   # §5 용량 시뮬

# ── §4 팩터별 신호 상수 ─────────────────────────────────────────────────────────────────────
SPEC_F1 = SpecLock("F1", dict(
    horizon_m=12,                    # 제거 유효기간 12개월
    e1_private_only=True,            # E1: CB/BW 발행결정 — 사모 한정
    e4_refix_drop=-0.20,             # E4: 현재가 ≤ 최초 전환가 × (1−0.20)
))
SPEC_F2 = SpecLock("F2", dict(
    lookback_m=6,                    # 직전 6개월 순매수 > 0
    rank_var="net_buy_over_mktcap",  # 랭킹 변수: 순매수금액 / 시가총액
    reasons_include=("장내매수",),
    reasons_exclude=("주식매수선택권", "스톡옵션", "상속", "증여", "담보", "무상증자",
                     "주식배당", "장외매수", "신주인수권", "전환", "합병", "대여", "반환"),
))
SPEC_F3 = SpecLock("F3", dict(
    illiq_window_d=60,               # ILLIQ = mean(|r|/거래대금) over 60일
    delta_lag_d=120,                 # ΔILLIQ = log ILLIQ(t) − log ILLIQ(t−120일)
    redundancy_rho=0.50,             # |ρ| > 0.5 → F3 기각
))
SPEC_F4 = SpecLock("F4", dict(
    ratio_threshold=0.20,            # 계약금액 / 직전연도 매출액 ≥ 0.20
    horizon_m=12,                    # 신호 유효기간 12개월, 복수 계약 합산
    track_cancel=True,               # 정정·해지 추적 — 누락하면 명백한 미래참조
))

# ── §4 민감도 격자 (팩터당 총 4개. 초과 금지 — 등록기가 강제한다) ───────────────────────────
SENS_MAX_PER_FACTOR = 4


class SensitivityGrid:
    """민감도 축 등록기. 팩터당 4개를 넘기면 예외 — §8-2 를 구조로 막는다."""

    def __init__(self):
        self._g: Dict[str, List[dict]] = {}

    def add(self, factor: str, key: str, desc: str, **override):
        g = self._g.setdefault(factor, [])
        if any(x["key"] == key for x in g):
            return
        if len(g) >= SENS_MAX_PER_FACTOR:
            raise SpecViolation(
                f"[{factor}] 민감도 격자가 {SENS_MAX_PER_FACTOR}개를 넘었습니다 "
                f"(추가 시도: {key}). 명세서 §8-2 위반 — 격자를 늘리려면 명세를 개정하세요.")
        g.append(dict(key=key, desc=desc, override=override))

    def get(self, factor: str) -> List[dict]:
        return list(self._g.get(factor, []))

    def all_variants(self, factor: str) -> List[dict]:
        """주 명세(primary) 1개 + 민감도 4개 = 5개."""
        return [dict(key="primary", desc="주 명세", override={})] + self.get(factor)


SENS = SensitivityGrid()

# F1 — 유효기간 6/24개월(2) + E1 사모+공모 확대(1) + E4 임계 −30%(1)
SENS.add("F1", "horizon_6m",  "유효기간 6개월",            horizon_m=6)
SENS.add("F1", "horizon_24m", "유효기간 24개월",           horizon_m=24)
SENS.add("F1", "e1_all",      "E1 사모+공모 전체로 확대",  e1_private_only=False)
SENS.add("F1", "e4_m30",      "E4 임계 −30%",              e4_refix_drop=-0.30)
# F2 — 룩백 3/12개월(2) + 대표이사·최대주주 본인 한정(1) + 랭킹변수 ADV 기준(1)
SENS.add("F2", "lookback_3m",  "룩백 3개월",               lookback_m=3)
SENS.add("F2", "lookback_12m", "룩백 12개월",              lookback_m=12)
SENS.add("F2", "ceo_only",     "대표이사·최대주주 본인 한정", ceo_only=True)
SENS.add("F2", "rank_by_adv",  "랭킹변수 = 순매수금액/일평균거래대금",
         rank_var="net_buy_over_adv")
# F3 — 윈도 30d/120d(2) + 수준(level) 대조군(1, 반증용) + 거래대금 변화율 단순판(1)
SENS.add("F3", "win_30d",   "ILLIQ 윈도 30일",            illiq_window_d=30)
SENS.add("F3", "win_120d",  "ILLIQ 윈도 120일",           illiq_window_d=120)
SENS.add("F3", "level",     "수준(level) 기반 대조군 — 반증용", use_level=True)
SENS.add("F3", "amt_only",  "거래대금 변화율만(수익률 미포함)", amount_only=True)
# F4 — 임계 0.10/0.35(2) + 유효기간 6개월(1) + 계약상대 공공·대기업 한정(1)
SENS.add("F4", "thr_010",    "임계 0.10",                 ratio_threshold=0.10)
SENS.add("F4", "thr_035",    "임계 0.35",                 ratio_threshold=0.35)
SENS.add("F4", "horizon_6m", "유효기간 6개월",            horizon_m=6)
SENS.add("F4", "public_big", "계약상대 공공기관·대기업집단 한정", counterparty_major=True)

FACTOR_META = {
    "F1": dict(name="자본거래·지배구조 이벤트", kind="filter",  dirn="하방 제거",
               hyp="H1: 이벤트 발생 종목을 제거하면 순수익 CAGR 이 B2 를 유의하게 초과하고 "
                   "좌측 꼬리(하위 5% 종목수익, MDD)가 개선된다."),
    "F2": dict(name="내부자 순매수", kind="rank", dirn="상방",
               hyp="H2: 임원·주요주주의 자기자금 장내매수 종목은 이후 12개월 순수익이 "
                   "B2 및 B4 상위 5% 를 초과한다."),
    "F3": dict(name="유동성 개선(Investor Recognition)", kind="rank", dirn="상방",
               hyp="H3: Amihud 비유동성의 개선(변화율) 상위 종목은 이후 순수익이 B2 를 초과한다. "
                   "수준(level)이 아니라 변화율이 유효할 것."),
    "F4": dict(name="수주·공급계약", kind="event", dirn="상방",
               hyp="H4: 직전 매출액 대비 20% 이상 신규 공급계약 공시 종목은 이후 12개월 "
                   "순수익이 B2 및 B4 상위 5% 를 초과한다."),
}


# ── §6.1 OOS 봉인 ───────────────────────────────────────────────────────────────────────────
class OOSSeal:
    """봉인구간(뒤 40%)은 Step 7 이전에 열 수 없다.

    '보지 않겠다'는 의지가 아니라 잠금이어야 한다. IS 단계의 모든 수익률 조회는
    이 봉인을 통과하며, 열리기 전에 OOS 날짜를 요청하면 예외로 중단된다.
    """

    def __init__(self):
        self.boundary: Optional[pd.Timestamp] = None
        self.opened = False
        self.open_reason = ""
        self.blocked = 0

    def set_boundary(self, dates: Sequence) -> pd.Timestamp:
        d = pd.DatetimeIndex(sorted(pd.to_datetime(pd.Series(list(dates))).dropna().unique()))
        if len(d) == 0:
            raise SpecViolation("봉인 경계를 정할 리밸런싱 시점이 없습니다.")
        i = max(0, int(np.floor(len(d) * SPEC_IS_FRACTION)) - 1)
        self.boundary = d[i]
        LOG.info(f"표본 분할 — 탐색구간(IS) {d[0]:%Y-%m-%d} ~ {self.boundary:%Y-%m-%d} "
                 f"({i+1}/{len(d)} 시점, {SPEC_IS_FRACTION:.0%}) · "
                 f"봉인구간(OOS) {d[min(i+1, len(d)-1)]:%Y-%m-%d} ~ {d[-1]:%Y-%m-%d} → 🔒 잠금")
        return self.boundary

    def open(self, reason: str):
        self.opened = True
        self.open_reason = reason
        LOG.warn(f"🔓 OOS 봉인 해제 — {reason} (이 시점 이전의 조기 열람 시도: {self.blocked}건)")

    def mask(self, dates, want: str) -> "pd.Series":
        """want='IS'|'OOS'|'ALL'. 봉인 전 OOS/ALL 요청은 예외."""
        s = pd.to_datetime(pd.Series(list(dates)).reset_index(drop=True))
        if self.boundary is None:
            return pd.Series(True, index=s.index)
        if want == "IS":
            return s <= self.boundary
        if not self.opened:
            self.blocked += 1
            raise SpecViolation(
                f"봉인구간(OOS) 접근이 차단되었습니다 (요청: {want}). "
                f"명세서 §8-6(OOS 구간 조기 열람 금지) — Step 7 에서만 열립니다.")
        return pd.Series(True, index=s.index) if want == "ALL" else (s > self.boundary)


SEAL = OOSSeal()


def spec_sha256() -> str:
    """사전등록 상수 전체의 해시. run_log 에 남겨 사후 변조를 확인할 수 있게 한다."""
    payload = json.dumps({
        "spec_version": SPEC_VERSION,
        "univ": dict(SPEC_UNIV), "cov": dict(SPEC_COV), "gate": dict(SPEC_GATE),
        "cost": dict(SPEC_COST), "tax": SPEC_TAX_TABLE, "aum": list(SPEC_AUM_LADDER),
        "f1": dict(SPEC_F1), "f2": dict(SPEC_F2), "f3": dict(SPEC_F3), "f4": dict(SPEC_F4),
        "n_values": list(SPEC_N_VALUES), "trials": SPEC_TRIALS_TOTAL,
        "sens": {f: [x["key"] for x in SENS.get(f)] for f in FACTOR_META},
        "is_fraction": SPEC_IS_FRACTION, "b4_sims": SPEC_B4_SIMS, "seed": SEED,
    }, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

import gzip
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  ★ CacheLake — 캐시 최우선 데이터 계층                                                    ║
# ║                                                                                          ║
# ║  전제: "거의 다 수집되어 있다." 그러므로 이 계층의 임무는 수집이 아니라 발굴이다.           ║
# ║                                                                                          ║
# ║    ① 구글드라이브 공용 인덱스(_shared)  — 다른 전략이 모아둔 원본/정제본                   ║
# ║    ② 로컬 D: 드라이브 재귀 스캔          — 이전 프로젝트가 남긴 parquet/csv/sqlite         ║
# ║    ③ 깃허브 raw 캐시                     — FDR 상장/폐지 목록 등                          ║
# ║                                                                                          ║
# ║  스키마를 모르는 캐시를 어떻게 쓰는가 — 컬럼 지문(signature)으로 역할을 추정한다.           ║
# ║  프로젝트마다 컬럼명이 다르다(code/종목코드/Symbol/ticker …). 별칭표로 정규화하고,          ║
# ║  점수가 임계 이상인 파일만 채택한다. 애매하면 채택하지 않고 목록에만 남긴다 —              ║
# ║  잘못 채택한 캐시는 없는 캐시보다 나쁘다.                                                  ║
# ║                                                                                          ║
# ║  ★ 절대 원칙: 스캔은 읽기 전용이다. 옮기지도, 지우지도, 덮어쓰지도 않는다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DATA_EXT = (".parquet", ".pq", ".csv", ".csv.gz", ".tsv", ".feather", ".ftr",
            ".pkl", ".pickle", ".jsonl", ".json", ".db", ".sqlite", ".sqlite3", ".h5")

# 스캔에서 건너뛸 디렉터리 (시간 낭비 + 데이터가 있을 리 없는 곳)
SKIP_DIRS = {".git", ".ipynb_checkpoints", "__pycache__", "node_modules", ".venv", "venv",
             "site-packages", ".cache", "AppData", "Windows", "Program Files",
             "Program Files (x86)", "$RECYCLE.BIN", "System Volume Information",
             ".vscode", ".idea", "_backup", "blob"}

# ── 컬럼 별칭표 ─────────────────────────────────────────────────────────────────────────────
#   같은 뜻인데 프로젝트마다 다르게 쓴 이름들. 소문자·공백제거 후 비교한다.
ALIAS = {
    "code":        ["code", "종목코드", "단축코드", "symbol", "ticker", "stock_code", "isu_srt_cd",
                    "shortcode", "srtncd", "종목", "isu_cd", "stockcode", "scode"],
    "name":        ["name", "종목명", "회사명", "기업명", "corp_name", "isu_nm", "itemname",
                    "한글종목명", "stock_name", "korean name", "종목이름"],
    "date":        ["date", "일자", "기준일", "기준일자", "trd_dd", "dt", "basdt", "ymd",
                    "거래일", "date_", "std_dt", "base_date"],
    "open":        ["open", "시가", "opnprc", "tdd_opnprc"],
    "high":        ["high", "고가", "hgprc", "tdd_hgprc"],
    "low":         ["low", "저가", "lwprc", "tdd_lwprc"],
    "close":       ["close", "종가", "clsprc", "tdd_clsprc", "adj close", "adjclose", "price",
                    "수정종가", "종가_수정"],
    "volume":      ["volume", "거래량", "acc_trdvol", "trdvol", "vol"],
    "amount":      ["amount", "거래대금", "acc_trdval", "trdval", "value", "거래금액", "tradingvalue"],
    "market_cap":  ["market_cap", "시가총액", "mktcap", "marketcap", "mkt_cap", "cap", "시총",
                    "mktcap_krw", "market_capitalization"],
    "shares":      ["shares", "상장주식수", "listed_shares", "list_shrs", "발행주식수", "shrs"],
    "market":      ["market", "시장", "시장구분", "mkt", "mktid", "market_name", "mkt_tp_nm"],
    "listing_date":   ["listing_date", "상장일", "listingdate", "list_dt", "상장일자", "listed_date"],
    "delisting_date": ["delisting_date", "폐지일", "상장폐지일", "delistingdate", "delist_dt",
                       "상장폐지일자", "delisted_date"],
    "corp_code":   ["corp_code", "고유번호", "corpcode", "dart_code", "corp_cd"],
    "rcept_no":    ["rcept_no", "접수번호", "receptno", "rcp_no", "rceptno"],
    "rcept_dt":    ["rcept_dt", "접수일자", "공시일", "공시일자", "receptdt", "rcp_dt", "rceptdt"],
    "report_nm":   ["report_nm", "보고서명", "공시제목", "title", "reportnm", "rpt_nm", "제목"],
    "bsns_year":   ["bsns_year", "사업연도", "year", "회계연도", "fy"],
    "account_nm":  ["account_nm", "계정명", "계정과목", "accountnm", "account_name"],
    "amount_fs":   ["thstrm_amount", "당기금액", "당기", "amount_fs", "value_fs"],
    "revenue":     ["revenue", "매출액", "sales", "영업수익", "매출"],
    "equity":      ["equity", "자본총계", "total_equity", "자기자본", "자본"],
    "capital":     ["capital", "자본금", "paid_in_capital", "납입자본금"],
    "industry":    ["industry", "업종", "섹터", "sector", "업종명", "industry_name", "gics", "wics"],
    "reason":      ["reason", "취득처분사유", "사유", "변동사유", "취득방법", "reason_nm"],
    "insider_nm":  ["insider_nm", "보고자", "성명", "repror", "보고자명", "reporter"],
    "contract_amt": ["contract_amt", "계약금액", "contract_amount", "계약총액"],
    "ratio_sales": ["ratio_sales", "매출액대비", "매출액대비비율", "sales_ratio", "비율"],
}
_ALIAS_REV = {a.replace(" ", "").replace("_", "").lower(): k
              for k, v in ALIAS.items() for a in v}


def canon_col(c: Any) -> Optional[str]:
    return _ALIAS_REV.get(str(c).strip().replace(" ", "").replace("_", "").lower())


# ── 역할 지문 ───────────────────────────────────────────────────────────────────────────────
#   need : 전부 있어야 채택   nice : 있으면 가점   role 별 최소 점수로 오채택을 막는다
ROLE_SIG = {
    "price_daily":     dict(need=["code", "date", "close"],
                            nice=["amount", "volume", "open", "high", "low", "market_cap"], min_score=4),
    "mktcap_daily":    dict(need=["code", "date", "market_cap"], nice=["shares", "amount"], min_score=3),
    "sec_master":      dict(need=["code", "name"],
                            nice=["listing_date", "delisting_date", "market", "industry", "corp_code"],
                            min_score=3),
    "corp_map":        dict(need=["corp_code", "code"], nice=["name"], min_score=2),
    "dart_disclosure": dict(need=["rcept_no", "report_nm"], nice=["corp_code", "rcept_dt", "code"],
                            min_score=3),
    "dart_fin":        dict(need=["corp_code", "bsns_year", "account_nm"],
                            nice=["amount_fs", "rcept_no"], min_score=4),
    "dart_insider":    dict(need=["rcept_no", "reason"], nice=["code", "corp_code", "insider_nm"],
                            min_score=3),
    "dart_contract":   dict(need=["rcept_no", "contract_amt"], nice=["ratio_sales", "code", "corp_code"],
                            min_score=3),
    "financials":      dict(need=["code", "revenue"], nice=["equity", "capital", "date", "bsns_year"],
                            min_score=3),
}
# 파일명 힌트 — 컬럼 지문과 독립적인 2차 증거. 단독으로는 채택하지 않는다.
NAME_HINT = {
    "price_daily": ("ohlcv", "price", "시세", "주가", "daily"),
    "mktcap_daily": ("mktcap", "시가총액", "cap", "marketcap"),
    "sec_master": ("master", "listing", "종목", "krx_stock", "sec_master", "universe"),
    "corp_map": ("corpcode", "corp_code", "corpmap"),
    "dart_disclosure": ("disclosure", "공시", "list", "dart_list", "rcept"),
    "dart_fin": ("fnltt", "financial", "재무", "dart_fin"),
    "dart_insider": ("insider", "지분", "임원", "주요주주", "소유상황"),
    "dart_contract": ("contract", "공급계약", "수주", "단일판매"),
    "financials": ("fin", "재무", "financ"),
}


@dataclass
class LakeItem:
    path: str
    role: str
    score: float
    rows: int
    cols: List[str]
    fmt: str
    origin: str          # drive | local | github | vault
    sub: str = ""        # sqlite 테이블명 등
    mtime: float = 0.0


def _sniff_parquet(path: str) -> Optional[Tuple[List[str], int]]:
    """★ 데이터를 읽지 않는다. 푸터 메타데이터만 본다 — 수 GB 파일도 수 ms."""
    try:
        import pyarrow.parquet as pq
        f = pq.ParquetFile(path)
        return [str(c) for c in f.schema_arrow.names], int(f.metadata.num_rows)
    except Exception:
        try:
            d = pd.read_parquet(path)
            return [str(c) for c in d.columns], len(d)
        except Exception:
            return None


def _sniff_csv(path: str) -> Optional[Tuple[List[str], int]]:
    try:
        opener = gzip.open if path.endswith(".gz") else open
        sep = "\t" if path.endswith((".tsv", ".tsv.gz")) else ","
        with opener(path, "rt", encoding="utf-8-sig", errors="replace") as fh:
            head = fh.readline()
        if not head:
            return None
        cols = [c.strip().strip('"') for c in head.rstrip("\r\n").split(sep)]
        if len(cols) < 2:
            return None
        # 행수는 바이트/행길이 추정 (전체를 읽지 않는다)
        try:
            approx = max(1, int(os.path.getsize(path) / max(len(head), 1)) - 1)
        except Exception:
            approx = -1
        return cols, approx
    except Exception:
        return None


def _sniff_sqlite(path: str) -> List[Tuple[str, List[str], int]]:
    out = []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            tabs = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()]
            for t in tabs[:60]:
                try:
                    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
                    if len(cols) >= 2:
                        out.append((t, [str(c) for c in cols], -1))
                except Exception:
                    continue
        finally:
            con.close()
    except Exception:
        pass
    return out


def _score_role(cols: List[str], fname: str) -> Tuple[Optional[str], float]:
    canon = {c for c in (canon_col(x) for x in cols) if c}
    best, best_s = None, 0.0
    low = os.path.basename(fname).lower()
    for role, sig in ROLE_SIG.items():
        if not all(n in canon for n in sig["need"]):
            continue
        s = float(len(sig["need"])) + sum(1.0 for n in sig["nice"] if n in canon)
        if any(h in low for h in NAME_HINT.get(role, ())):
            s += 1.0
        if s >= sig["min_score"] and s > best_s:
            best, best_s = role, s
    return best, best_s


class CacheLake:
    """읽기 전용 캐시 발굴기. 채택한 파일만 실제로 로드한다."""

    def __init__(self):
        self.items: List[LakeItem] = []
        self.scanned = 0
        self.skipped_dirs = 0
        self.roots_used: List[Tuple[str, str]] = []
        self._loaded: Dict[str, pd.DataFrame] = {}
        self.rejected: List[Tuple[str, List[str]]] = []

    # ── 스캔 ────────────────────────────────────────────────────────────────────────────
    def _roots(self) -> List[Tuple[str, str]]:
        seen, out = set(), []
        # ① 볼트(구글드라이브 또는 로컬 폴백)의 table 디렉터리 — 가장 신뢰도가 높다
        for scope in ("shared", "private"):
            try:
                p = VAULT.table_dir(scope)
                if os.path.isdir(p) and p not in seen:
                    seen.add(p); out.append((p, "vault"))
            except Exception:
                pass
        # ② 구글드라이브 채택 폴더
        for p in GDRIVE_ADOPT_DIRS:
            p = os.path.expanduser(str(p))
            if os.path.isdir(p) and p not in seen:
                seen.add(p); out.append((p, "drive"))
        # ③ 로컬 (D: 포함)
        for p in CACHE_SEARCH_DIRS + [CACHE_DIR, BASE_DIR, LOCAL_CACHE_ROOT]:
            p = os.path.expanduser(str(p or ""))
            if p and os.path.isdir(p) and p not in seen:
                seen.add(p); out.append((p, "local"))
        return out

    def scan_local(self):
        roots = self._roots()
        self.roots_used = roots
        if not roots:
            LOG.warn("스캔할 캐시 경로가 하나도 없습니다 — CACHE_SEARCH_DIRS / GDRIVE_ADOPT_DIRS 를 "
                     "확인하세요. (경로가 없어도 실행은 되지만 전부 신규 수집이 됩니다)")
            return
        _names = [(os.path.basename(p.rstrip("/" + os.sep)) or p) + f"[{k}]" for p, k in roots]
        LOG.info(f"캐시 스캔 시작 — 루트 {len(roots)}개: " + ", ".join(_names))
        cands: List[Tuple[str, str]] = []
        for root, kind in roots:
            base_depth = root.rstrip("/\\").count(os.sep)
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.count(os.sep) - base_depth >= CACHE_SCAN_MAX_DEPTH:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                self.skipped_dirs += 1
                for fn in filenames:
                    if fn.lower().endswith(DATA_EXT) and not fn.startswith("."):
                        cands.append((os.path.join(dirpath, fn), kind))
                        if len(cands) >= CACHE_SCAN_MAX_FILES:
                            break
                if len(cands) >= CACHE_SCAN_MAX_FILES:
                    break
        # 같은 파일이 여러 루트로 잡히면 한 번만
        uniq: Dict[str, str] = {}
        for p, k in cands:
            rp = os.path.realpath(p)
            if rp not in uniq or k == "vault":
                uniq[rp] = k
        LOG.info(f"데이터 후보 파일 {len(uniq):,}개 발견 — 컬럼 지문으로 역할을 판별합니다 "
                 f"(파일 내용은 읽지 않고 스키마만 봅니다).")

        def _one(item):
            path, kind = item
            out: List[LakeItem] = []
            low = path.lower()
            try:
                mt = os.path.getmtime(path)
                if low.endswith((".db", ".sqlite", ".sqlite3")):
                    for t, cols, n in _sniff_sqlite(path):
                        role, s = _score_role(cols, f"{path}:{t}")
                        if role:
                            out.append(LakeItem(path, role, s, n, cols, "sqlite", kind, t, mt))
                    return out
                if low.endswith((".parquet", ".pq")):
                    sn = _sniff_parquet(path)
                elif low.endswith((".csv", ".csv.gz", ".tsv")):
                    sn = _sniff_csv(path)
                elif low.endswith((".feather", ".ftr")):
                    try:
                        import pyarrow.feather as fe
                        sn = ([str(c) for c in fe.read_table(path, columns=None).schema.names], -1)
                    except Exception:
                        sn = None
                elif low.endswith((".pkl", ".pickle")):
                    if os.path.getsize(path) > 600 * 1024 * 1024:
                        return out                       # 거대 pickle 은 안전하게 건너뛴다
                    try:
                        d = pd.read_pickle(path)
                        sn = ([str(c) for c in d.columns], len(d)) if isinstance(d, pd.DataFrame) else None
                    except Exception:
                        sn = None
                elif low.endswith(".jsonl"):
                    rows = read_jsonl(path)[:1]
                    sn = ([str(c) for c in rows[0].keys()], -1) if rows else None
                else:
                    return out
                if not sn:
                    return out
                cols, n = sn
                role, s = _score_role(cols, path)
                if role:
                    out.append(LakeItem(path, role, s, n, cols, os.path.splitext(low)[1].lstrip("."),
                                        kind, "", mt))
                else:
                    self.rejected.append((path, cols[:12]))
            except Exception:
                pass
            return out

        res = pmap_io(_one, list(uniq.items()), workers=min(N_WORKERS_IO, 12), desc="캐시 지문 판별")
        for lst in res:
            if lst:
                self.items.extend(lst)
        self.scanned = len(uniq)

    # ── 깃허브 ──────────────────────────────────────────────────────────────────────────
    def scan_github(self):
        if COLLECT_POLICY == "NEVER":
            LOG.info("COLLECT_POLICY=NEVER — 깃허브 캐시 조회를 건너뜁니다.")
            return
        for owner_repo, branch, sub in GITHUB_CACHE_REPOS:
            url = f"https://api.github.com/repos/{owner_repo}/git/trees/{branch}?recursive=1"
            hdr = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else None
            js = http_json(url, source="github", headers=hdr, tries=2, timeout=30)
            if not isinstance(js, dict) or "tree" not in js:
                LOG.warn(f"깃허브 캐시 목록 조회 실패: {owner_repo} — 이 소스는 건너뜁니다.")
                continue
            files = [t["path"] for t in js["tree"]
                     if t.get("type") == "blob" and str(t.get("path", "")).startswith(sub)
                     and str(t.get("path", "")).lower().endswith((".csv", ".parquet"))]
            LOG.ok(f"깃허브 {owner_repo}@{branch}/{sub} — 파일 {len(files):,}개 확인 "
                   f"(내려받지 않고 목록만 확보. 필요한 날짜만 그때 받습니다).")
            self._gh_files = getattr(self, "_gh_files", {})
            self._gh_files[owner_repo] = (branch, files)

    def harvest(self):
        with PIPE.stage("L0.LAKE", "캐시 하베스트 (드라이브·로컬D·깃허브)", "L0", budget_s=900):
            self.scan_local()
            self.scan_github()
            self.report()
            self.adopt_into_vault()

    # ── 보고 ────────────────────────────────────────────────────────────────────────────
    def report(self):
        if not self.items:
            LOG.warn("재활용 가능한 캐시를 찾지 못했습니다. 경로 설정을 확인하세요 — "
                     "이대로 진행하면 전부 신규 수집이라 매우 느립니다.")
            if self.rejected:
                LOG.info("판별 실패한 파일 예시 (컬럼이 지문과 맞지 않음):")
                for p, cols in self.rejected[:5]:
                    LOG.info(f"    {os.path.basename(p)} → {cols}")
            return
        agg: Dict[Tuple[str, str], List[int]] = {}
        for it in self.items:
            k = (it.role, it.origin)
            a = agg.setdefault(k, [0, 0])
            a[0] += 1
            a[1] += max(it.rows, 0)
        rows = [[role, origin, f"{n:,}", f"{r:,}" if r else "?"]
                for (role, origin), (n, r) in sorted(agg.items())]
        LOG.table(rows, ["역할", "출처", "파일수", "행수(추정)"], ["l", "l", "r", "r"],
                  title=f"★ 재활용 캐시 목록 — 후보 {self.scanned:,}개 중 {len(self.items):,}개 채택")

    def adopt_into_vault(self):
        """경로만 인덱스에 등록한다. 파일을 옮기거나 고치지 않는다(adopt-by-reference)."""
        n = 0
        for it in self.items:
            if it.origin == "vault":
                continue
            try:
                VAULT.adopt(it.path, domain="lake", subtype=it.role,
                                 key=f"{it.role}:{os.path.basename(it.path)}{(':'+it.sub) if it.sub else ''}",
                                 source=f"lake:{it.origin}", scope="shared")
                n += 1
            except Exception:
                continue
        if n:
            LOG.ok(f"외부 캐시 {n:,}건을 인덱스에 '경로만' 등록했습니다 — "
                   f"파일은 원위치 그대로이며 다음 실행에서도 즉시 재활용됩니다.")
        VAULT.flush()

    # ── 적재 ────────────────────────────────────────────────────────────────────────────
    def _read_item(self, it: LakeItem) -> Optional[pd.DataFrame]:
        try:
            if it.fmt == "sqlite":
                con = sqlite3.connect(f"file:{it.path}?mode=ro", uri=True)
                try:
                    d = pd.read_sql_query(f'SELECT * FROM "{it.sub}"', con)
                finally:
                    con.close()
            elif it.fmt in ("parquet", "pq"):
                d = read_parquet_safe(it.path)
            elif it.fmt in ("csv", "gz", "tsv"):
                d = pd.read_csv(it.path, encoding="utf-8-sig", low_memory=False,
                                sep="\t" if it.path.endswith(".tsv") else ",")
            elif it.fmt in ("feather", "ftr"):
                d = pd.read_feather(it.path)
            elif it.fmt in ("pkl", "pickle"):
                d = pd.read_pickle(it.path)
            elif it.fmt == "jsonl":
                d = pd.DataFrame(read_jsonl(it.path))
            else:
                return None
        except Exception as e:                                          # noqa
            LOG.debug(f"캐시 적재 실패 {os.path.basename(it.path)}: {type(e).__name__}")
            return None
        if d is None or not len(d):
            return None
        ren = {}
        for c in d.columns:
            k = canon_col(c)
            if k and k not in ren.values():
                ren[c] = k
        d = d.rename(columns=ren)
        d = d.loc[:, ~pd.Index(d.columns).duplicated()]
        d["_src"] = os.path.basename(it.path) + (f":{it.sub}" if it.sub else "")
        return d

    def load(self, role: str, required: Sequence[str] = ()) -> Optional[pd.DataFrame]:
        """역할별 최적 캐시를 합쳐서 반환. 큰 것·최신 것 우선, 중복은 뒤에 오는 것을 버린다."""
        if role in self._loaded:
            return self._loaded[role]
        cand = sorted([i for i in self.items if i.role == role],
                      key=lambda x: (-x.score, -max(x.rows, 0), -x.mtime))
        if not cand:
            return None
        frames, used = [], []
        for it in cand[:12]:                       # 상위 12개까지만 — 같은 데이터의 사본이 흔하다
            d = self._read_item(it)
            if d is None:
                continue
            if required and not all(c in d.columns for c in required):
                continue
            frames.append(d)
            used.append(f"{os.path.basename(it.path)}({len(d):,})")
            if sum(len(f) for f in frames) > 40_000_000:
                LOG.warn(f"[{role}] 적재량이 4천만행을 넘어 나머지 사본은 건너뜁니다.")
                break
        if not frames:
            return None
        allc: List[str] = []
        for f in frames:
            for c in f.columns:
                if c not in allc:
                    allc.append(c)
        d = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
        LOG.ok(f"[{role}] 캐시 재활용 {len(d):,}행 ← {', '.join(used[:5])}"
               f"{' 외 %d개' % (len(used)-5) if len(used) > 5 else ''}")
        PIPE.io("IN", "CACHE", f"lake:{role}", d, source=",".join(used[:3]))
        self._loaded[role] = d
        return d

    def has(self, role: str) -> bool:
        return any(i.role == role for i in self.items)


LAKE = CacheLake()

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  데이터 조립 — 캐시에서 꺼내 쓰고, 없는 것만 만든다                                        ║
# ║                                                                                          ║
# ║  순서가 곧 정책이다:  LAKE(캐시) → VAULT(드라이브 테이블) → 네트워크(구멍만)              ║
# ║  COLLECT_POLICY="NEVER" 면 세 번째 단계가 아예 실행되지 않는다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

RUNLOG: Dict[str, Any] = {}


def _net_allowed() -> bool:
    if RUN_MODE == "CACHED" or COLLECT_POLICY == "NEVER":
        return False
    return True


# ── SMOKE 합성데이터 ────────────────────────────────────────────────────────────────────────
def synth_dataset(n_codes: int = 900, years: int = 8) -> Dict[str, pd.DataFrame]:
    """실데이터 없이 Step 0~9 전 계산경로를 증명하기 위한 합성 패널.

    ★ 신호가 '있는' 데이터를 만들지 않는다. F2/F4 이벤트는 수익률과 독립으로 뿌린다.
      스모크에서 팩터가 통과하면 그건 하네스 버그지 알파가 아니다 —
      그래서 스모크의 기대 결과는 '전 팩터 G1~G7 미달' 이다.
    """
    rng = np.random.default_rng(SEED)
    end = pd.Timestamp("2026-07-31")
    dates = pd.bdate_range(end - pd.DateOffset(years=years), end)
    codes = [f"{i:06d}" for i in rng.choice(np.arange(1000, 999999), n_codes, replace=False)]
    codes = [c[:-1] + "0" for c in codes]
    codes = sorted(set(codes))
    n_codes = len(codes)

    drift = rng.normal(0.0002, 0.0004, n_codes)
    vol = rng.uniform(0.018, 0.055, n_codes)
    r = rng.standard_normal((len(dates), n_codes)) * vol + drift
    px = 1000.0 * np.exp(np.cumsum(r, axis=0)) * rng.uniform(0.5, 20, n_codes)
    shares = rng.lognormal(16.5, 1.1, n_codes)
    turn = np.exp(rng.normal(-5.6, 1.0, (len(dates), n_codes)))
    vol_sh = np.maximum(shares * turn, 1.0)

    D = pd.DataFrame({
        "code": np.tile(codes, len(dates)),
        "date": np.repeat(dates.values, n_codes),
        "close": px.ravel(), "open": (px * (1 + rng.normal(0, 0.004, px.shape))).ravel(),
        "high": (px * 1.01).ravel(), "low": (px * 0.99).ravel(),
        "volume": vol_sh.ravel(),
        "amount": (px * vol_sh).ravel(),
        "shares": np.tile(shares, len(dates)),
    })
    D["market_cap"] = D["close"] * D["shares"]

    lst = pd.to_datetime(rng.choice(pd.bdate_range("2005-01-01", "2024-01-01"), n_codes))
    dele = pd.Series(pd.NaT, index=range(n_codes))
    kill = rng.random(n_codes) < 0.11                      # 폐지 이력 ~11%
    dele[kill] = pd.to_datetime(rng.choice(pd.bdate_range(dates[0], dates[-1]), int(kill.sum())))
    names = []
    for i, c in enumerate(codes):
        t = rng.random()
        names.append(f"합성{i:03d}스팩" if t < 0.04 else
                     f"합성{i:03d}리츠" if t < 0.06 else f"합성{i:03d}")
    SEC = pd.DataFrame({"code": codes, "name": names,
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes, p=[0.25, 0.75]),
                        "listing_date": lst, "delisting_date": dele.values,
                        "corp_code": [f"{i:08d}" for i in range(n_codes)],
                        "industry": rng.choice([f"업종{i}" for i in range(18)], n_codes)})

    yrs = list(range(dates[0].year - 1, dates[-1].year + 1))
    FIN = pd.DataFrame([
        {"code": c, "bsns_year": y,
         "knowledge_date": pd.Timestamp(year=y + 1, month=3, day=25),
         "revenue": float(rng.lognormal(24, 1.3)),
         "equity": float(rng.lognormal(23.5, 1.4)) * (1 if rng.random() > 0.07 else -1),
         "capital": float(rng.lognormal(22.8, 1.0))}
        for c in codes for y in yrs])

    def _ev(rate, cols):
        k = max(1, int(n_codes * len(dates) / 250 * rate))
        idx = rng.integers(0, n_codes, k)
        dt = pd.to_datetime(rng.choice(dates, k))
        d = pd.DataFrame({"code": [codes[i] for i in idx], "rcept_dt": dt})
        for cname, fn in cols.items():
            d[cname] = fn(k, rng)
        return d

    CAP = _ev(0.09, {"event": lambda k, g: g.choice(["E1_CB", "E1_BW", "E2_3RD", "E3_OWNER"], k),
                     "is_private": lambda k, g: g.random(k) < 0.75,
                     "refix": lambda k, g: g.random(k) < 0.6,
                     "conv_price": lambda k, g: g.uniform(500, 20000, k)})
    INS = _ev(0.05, {"reason": lambda k, g: g.choice(["장내매수", "장내매도", "스톡옵션", "상속"], k,
                                                     p=[0.42, 0.33, 0.15, 0.10]),
                     "net_amount": lambda k, g: g.lognormal(18, 1.5, k),
                     "role": lambda k, g: g.choice(["대표이사", "등기임원", "최대주주", "특수관계인"], k)})
    INS["net_amount"] *= np.where(INS["reason"] == "장내매수", 1, -1)
    CON = _ev(0.04, {"contract_amt": lambda k, g: g.lognormal(23, 1.6, k),
                     "counterparty": lambda k, g: g.choice(["공공기관", "대기업집단", "일반"], k),
                     "is_cancel": lambda k, g: g.random(k) < 0.07})
    return {"price": D, "sec": SEC, "fin": FIN, "cap_events": CAP,
            "insider": INS, "contracts": CON}


# ── 로더 ────────────────────────────────────────────────────────────────────────────────────
def load_sec_master() -> pd.DataFrame:
    d = LAKE.load("sec_master")
    if d is None:
        d = VAULT.get_table("sec_master", scope="shared")
    if d is None and _net_allowed():
        d = fetch_sec_master_github()
    if d is None or not len(d):
        raise StageFailure(
            "종목마스터(상장일·폐지일)를 어디에서도 찾지 못했습니다. 상장일이 없으면 "
            "'상장 ≥ 180일' 게이트를, 폐지일이 없으면 생존자편향 제거를 할 수 없습니다.")
    d = d.copy()
    d["code"] = d["code"].map(to_code6)
    d = d.dropna(subset=["code"])
    for c in ("listing_date", "delisting_date"):
        d[c] = as_ts_series(d[c]) if c in d.columns else pd.NaT
    for c in ("name", "market", "industry", "corp_code"):
        if c not in d.columns:
            d[c] = ""
    #   같은 종목이 여러 캐시에 있으면 정보가 많은 행을 남긴다(폐지일이 있는 쪽 우선).
    d["_rich"] = d[["listing_date", "delisting_date"]].notna().sum(axis=1) + \
                 (d["name"].astype(str).str.len() > 0).astype(int)
    d = d.sort_values("_rich").drop_duplicates("code", keep="last").drop(columns=["_rich"])
    n_del = int(d["delisting_date"].notna().sum())
    LOG.ok(f"종목마스터 {len(d):,}종목 (폐지 이력 {n_del:,}종목 = {100*n_del/max(len(d),1):.1f}%) "
           f"— 폐지 종목이 0이면 생존자편향입니다.")
    if n_del == 0:
        LOG.warn("폐지 종목이 하나도 없습니다 — 생존자편향이 확실합니다. "
                 "폐지 목록을 담은 캐시를 찾거나 FDR delisting 을 수집하세요.")
    return d


def fetch_sec_master_github() -> Optional[pd.DataFrame]:
    """깃허브 FDR 캐시(로그인 불필요)에서 상장/폐지 목록만 받는다. 구멍 메우기 전용."""
    out = []
    today = _dt.date.today()
    for kind, dcol in (("listing/krx", None), ("listing/delisting", "DelistingDate")):
        got = None
        for i in range(20):
            day = today - _dt.timedelta(days=i)
            if day.weekday() >= 5:
                continue
            url = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                   f"refs/heads/master/data/{kind}/{day.isoformat()}.csv")
            raw = http_get(url, source="github", as_bytes=True, tries=1, timeout=25)
            if raw and len(raw) > 200 and not raw[:15].lstrip().startswith(b"404"):
                try:
                    got = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", dtype=str)
                    break
                except Exception:
                    continue
        if got is None:
            LOG.warn(f"깃허브 FDR 캐시 {kind} 를 받지 못했습니다.")
            continue
        ren = {c: canon_col(c) for c in got.columns if canon_col(c)}
        got = got.rename(columns=ren)
        if dcol and "delisting_date" not in got.columns:
            for c in got.columns:
                if "delist" in str(c).lower():
                    got = got.rename(columns={c: "delisting_date"})
                    break
        out.append(got)
    if not out:
        return None
    d = pd.concat(out, ignore_index=True)
    VAULT.put_table("sec_master", d, scope="shared", domain="universe", source="fdr_github_cache")
    return d


def load_price() -> pd.DataFrame:
    d = LAKE.load("price_daily", required=["code", "date", "close"])
    mc = LAKE.load("mktcap_daily")
    if d is None:
        d = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    if d is None:
        raise StageFailure(
            "일별 가격 캐시를 찾지 못했습니다. CACHE_SEARCH_DIRS 에 이전 프로젝트의 "
            "가격 parquet/csv 가 있는 폴더를 추가하세요. (신규 수집은 수 시간 걸립니다)")
    if mc is not None and ("market_cap" not in d.columns or d["market_cap"].isna().all()):
        keep = [c for c in ("code", "date", "market_cap", "shares") if c in mc.columns]
        mc = mc[keep].copy()
        mc["code"] = mc["code"].map(to_code6)
        mc["date"] = as_ts_series(mc["date"])
        d = d.merge(mc.drop_duplicates(["code", "date"]), on=["code", "date"], how="left")
        LOG.ok(f"별도 시총 캐시 {len(mc):,}행을 가격 패널에 결합했습니다.")
    return d


def load_financials() -> pd.DataFrame:
    """(code, knowledge_date, revenue, equity, capital) 롱패널. knowledge_date = 접수일자."""
    d = LAKE.load("financials")
    if d is not None and {"revenue"} <= set(d.columns):
        f = d.copy()
    else:
        raw = LAKE.load("dart_fin")
        if raw is None:
            raw = VAULT.get_table("dart_fnltt_raw", scope="shared")
        if raw is None:
            LOG.warn("재무 캐시를 찾지 못했습니다 — 자본잠식·재무결측 게이트가 무력화됩니다.")
            return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
        f = tidy_dart_accounts(raw)
    for c in ("revenue", "equity", "capital"):
        if c not in f.columns:
            f[c] = np.nan
        f[c] = pd.to_numeric(f[c], errors="coerce")
    if "knowledge_date" not in f.columns:
        if "rcept_no" in f.columns:
            f["knowledge_date"] = pd.to_datetime(
                f["rcept_no"].astype(str).str.replace(r"\D", "", regex=True).str[:8],
                format="%Y%m%d", errors="coerce")
        elif "bsns_year" in f.columns:
            #   접수일자를 모르면 법정 제출기한(사업보고서 90일)으로 보수 추정한다.
            f["knowledge_date"] = pd.to_datetime(
                pd.to_numeric(f["bsns_year"], errors="coerce").astype("Int64").astype(str) + "-12-31",
                errors="coerce") + pd.Timedelta(days=90)
            LOG.warn("재무 캐시에 접수일자가 없어 결산일+90일로 보수 추정했습니다 — "
                     "PIT 가 그만큼 느슨해집니다(미래참조 방향이 아니라 지연 방향).")
    if "code" not in f.columns:
        f = map_corp_to_code(f)
    f = f.dropna(subset=["code", "knowledge_date"])
    f = (f.sort_values(["code", "knowledge_date"])
           .drop_duplicates(["code", "knowledge_date"], keep="last"))
    LOG.ok(f"재무 패널 {len(f):,}행 · {f['code'].nunique():,}종목 "
           f"(자본총계 유효 {int(f['equity'].notna().sum()):,}행)")
    return f[["code", "knowledge_date", "revenue", "equity", "capital"]]


_ACCT_PAT = {
    "revenue": re.compile(r"^(매출액|수익\(매출액\)|영업수익|매출)$"),
    "equity":  re.compile(r"^(자본총계|자본\s*총계)$"),
    "capital": re.compile(r"^(자본금)$"),
}


def tidy_dart_accounts(raw: pd.DataFrame) -> pd.DataFrame:
    """DART 원시 계정 롱테이블 → 종목×기간 와이드. 접수일자를 여기서 확정한다."""
    d = raw.copy()
    if "account_nm" not in d.columns or "amount_fs" not in d.columns:
        return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    d["amount_fs"] = pd.to_numeric(
        d["amount_fs"].astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce")
    frames = []
    for item, pat in _ACCT_PAT.items():
        h = d[d["account_nm"].str.match(pat)]
        if not len(h):
            continue
        keys = [c for c in ("corp_code", "code", "bsns_year", "rcept_no") if c in h.columns]
        frames.append(h.groupby(keys, observed=True)["amount_fs"].max().rename(item).reset_index())
    if not frames:
        return pd.DataFrame(columns=["code", "knowledge_date", "revenue", "equity", "capital"])
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=[c for c in out.columns if c in f.columns and c in
                               ("corp_code", "code", "bsns_year", "rcept_no")], how="outer")
    return out


def map_corp_to_code(d: pd.DataFrame) -> pd.DataFrame:
    """corp_code → 종목코드. 매핑표가 없으면 그 사실을 남기고 빈 결과를 돌려준다."""
    if "corp_code" not in d.columns:
        d["code"] = np.nan
        return d
    m = LAKE.load("corp_map")
    if m is None:
        m = VAULT.get_table("dart_corp_map", scope="shared")
    if m is None or "code" not in getattr(m, "columns", []):
        LOG.warn("corp_code ↔ 종목코드 매핑표가 없어 DART 데이터를 종목에 붙이지 못했습니다.")
        d["code"] = np.nan
        return d
    m = m[["corp_code", "code"]].dropna().drop_duplicates("corp_code")
    m["code"] = m["code"].map(to_code6)
    d = d.copy()
    d["corp_code"] = d["corp_code"].astype(str).str.zfill(8)
    m["corp_code"] = m["corp_code"].astype(str).str.zfill(8)
    out = d.merge(m, on="corp_code", how="left")
    hit = 100 * out["code"].notna().mean()
    LOG.info(f"corp_code → 종목코드 매핑률 {hit:.1f}% ({int(out['code'].notna().sum()):,}행)")
    return out


def attach_pit_financials(snap: pd.DataFrame, fin: pd.DataFrame) -> pd.DataFrame:
    """PIT 결합 — 리밸 시점에 '이미 공시된' 최신 재무만 붙인다(merge_asof backward)."""
    if fin is None or not len(fin):
        return snap
    f = fin.copy()
    #   공시 접수일 + 1영업일부터 사용 가능 (§4 공통규약 PIT)
    f["usable_from"] = f["knowledge_date"] + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS)
    f = f.dropna(subset=["usable_from"]).sort_values("usable_from")
    s = snap.sort_values("rebal")
    out = pd.merge_asof(s, f[["code", "usable_from", "revenue", "equity", "capital"]],
                        left_on="rebal", right_on="usable_from", by="code", direction="backward")
    n = int(out["equity"].notna().sum())
    LOG.info(f"PIT 재무 결합 — {n:,}/{len(out):,} 셀에 접수일 기준 최신 재무가 붙었습니다 "
             f"({100*n/max(len(out),1):.1f}%).")
    return out

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  DART 원천 — F1(자본거래) · F2(내부자) · F4(공급계약)                                     ║
# ║                                                                                          ║
# ║  ★ 명세서 §0: "API 명칭은 참조용이다. 구현 전 실제 문서에서 엔드포인트·파라미터·응답       ║
# ║    스키마를 검증하고, 불일치 시 로그에 기록한 뒤 진행할 것. 추측으로 채우지 말 것."         ║
# ║                                                                                          ║
# ║  그래서 엔드포인트를 코드에 박아두고 믿지 않는다. 실행 시각에 실제로 한 번 찔러 보고        ║
# ║  ① 응답 status ② 실제 필드명을 기록한 뒤, 검증된 것만 쓴다. 검증 실패한 엔드포인트는       ║
# ║  '없는 데이터'로 취급되어 Phase 0 커버리지에서 자동으로 걸러진다(§6.4 조기 중단).          ║
# ║  없는 필드를 이름만 보고 추측해 채우는 경로는 만들지 않았다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"


class DartBudget:
    """일 20,000건 호출 한도. 캐시가 있으면 거의 쓸 일이 없지만, 한도를 넘기면
    그날의 남은 수집이 전부 실패하므로 파일로 관리하며 재실행에서 이어받는다."""

    LIMIT = 20000

    def __init__(self):
        self.path = os.path.join(CACHE_DIR or ".", "_dart_budget.json")
        self.day = _dt.date.today().isoformat()
        self.used = 0
        self._lk = threading.Lock()
        try:
            j = json.loads(open(self.path, encoding="utf-8").read())
            if j.get("day") == self.day:
                self.used = int(j.get("used", 0))
        except Exception:
            pass

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.used + k > self.LIMIT:
                return False
            self.used += k
            if self.used % 200 < k:
                self._save()
            return True

    def _save(self):
        try:
            atomic_write_text(self.path, json.dumps({"day": self.day, "used": self.used}))
        except Exception:
            pass

    def close(self):
        self._save()
        if self.used:
            LOG.info(f"DART 호출 {self.used:,}건 사용 (일 한도 {self.LIMIT:,}). "
                     f"남은 한도 {self.LIMIT - self.used:,}건.")


DARTB = DartBudget()


def dart_api(endpoint: str, params: dict, tries: int = 3) -> Optional[dict]:
    if not DART_API_KEY:
        return None
    if not _net_allowed():
        return None
    if not DARTB.take():
        LOG.warn("DART 일일 호출 한도 소진 — 남은 수집은 다음 실행에서 이어집니다(캐시는 유지).")
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries, timeout=30,
                   referer="https://opendart.fss.or.kr/")
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st == "020":
        LOG.warn("DART status=020 (일일 한도 초과). 수집을 중단합니다.")
        DARTB.used = DartBudget.LIMIT
    elif st in ("010", "011", "012"):
        LOG.warn(f"DART status={st} — 인증키가 등록되지 않았거나 사용할 수 없습니다. "
                 f"DART_API_KEY 를 확인하세요.")
    return js


# ── 엔드포인트 레지스트리 ───────────────────────────────────────────────────────────────────
#   name → (endpoint, 최소 파라미터, 기대 필드). 기대 필드는 '검증 대상'이지 전제가 아니다.
DART_ENDPOINTS = {
    "list":       ("list.json",       {"pblntf_ty": "B"},          ["rcept_no", "report_nm", "rcept_dt", "corp_code"]),
    "cb":         ("cvbdIsDecsn.json", {},                          ["rcept_no", "bd_tm", "cv_prc"]),
    "bw":         ("bdwtIsDecsn.json", {},                          ["rcept_no", "bd_tm", "ex_prc"]),
    "rights":     ("piicDecsn.json",   {},                          ["rcept_no", "ic_mthn", "nstk_ostk_cnt"]),
    "owner_chg":  ("hyslrChgSttus.json", {},                        ["rcept_no", "change_on", "mxmm_shldr_nm"]),
    "elestock":   ("elestock.json",    {},                          ["rcept_no", "repror", "isu_exctv_rgist_at", "sp_stock_lmp_cnt"]),
}
#   ※ '단일판매·공급계약체결'은 정형 엔드포인트가 확인되지 않았다. 공시검색(list)으로 목록을
#     잡고 공시원문(document.xml)을 파싱하는 경로를 쓴다 — 이 사실을 레지스트리에 명시한다.
DART_DOC_ONLY = {"contract": "단일판매·공급계약체결 (정형 API 미확인 → 원문 파싱 경로)"}

ENDPOINT_STATUS: Dict[str, dict] = {}


def verify_dart_endpoints(sample_corp: Optional[str] = None) -> None:
    """실행 시각에 실제로 찔러 보고 스키마를 기록한다. 추측 금지의 실행체."""
    if not DART_API_KEY or not _net_allowed():
        for k in DART_ENDPOINTS:
            ENDPOINT_STATUS[k] = dict(verified=False, reason="키 없음 또는 네트워크 비활성",
                                      fields=[])
        LOG.warn("DART 엔드포인트 검증을 건너뜁니다(키 없음/캐시 전용 모드). "
                 "F1·F2·F4 는 캐시에 있는 것만 씁니다.")
        return
    rows = []
    for name, (ep, extra, expect) in DART_ENDPOINTS.items():
        p = dict(extra)
        if name == "list":
            p.update({"bgn_de": (_dt.date.today() - _dt.timedelta(days=7)).strftime("%Y%m%d"),
                      "end_de": _dt.date.today().strftime("%Y%m%d"),
                      "page_count": "10"})
        else:
            p.update({"corp_code": sample_corp or "00126380",     # 검증용 1건
                      "bgn_de": "20200101", "end_de": "20241231"})
        js = dart_api(ep, p, tries=2)
        if js is None:
            ENDPOINT_STATUS[name] = dict(verified=False, reason="응답 없음", fields=[])
            rows.append([name, ep, "—", "응답 없음", "미검증"])
            continue
        st = str(js.get("status", "?"))
        lst = js.get("list") or []
        fields = sorted(lst[0].keys()) if isinstance(lst, list) and lst and isinstance(lst[0], dict) else []
        ok = st in ("000", "013")                 # 013 = 조회 데이터 없음 (엔드포인트 자체는 유효)
        missing = [f for f in expect if fields and f not in fields]
        ENDPOINT_STATUS[name] = dict(verified=ok, reason=f"status={st}", fields=fields,
                                     missing=missing)
        rows.append([name, ep, st, ", ".join(fields[:6]) or "(빈 응답)",
                     "검증" if ok and not missing else
                     ("필드 불일치: " + ",".join(missing)) if missing else "실패"])
    for k, why in DART_DOC_ONLY.items():
        ENDPOINT_STATUS[k] = dict(verified=False, reason=why, fields=[], doc_parse=True)
        rows.append([k, "(원문 파싱)", "—", why, "원문 경로"])
    LOG.table(rows, ["용도", "엔드포인트", "status", "실제 응답 필드", "판정"],
              ["l", "l", "c", "l", "l"], title="DART 엔드포인트 실측 검증 (§0 — 추측 금지)")
    RUNLOG["dart_endpoints"] = {k: {kk: vv for kk, vv in v.items() if kk != "fields"}
                                for k, v in ENDPOINT_STATUS.items()}


# ── 이벤트 적재 (캐시 최우선) ───────────────────────────────────────────────────────────────
def load_capital_events(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F1 원천: CB/BW 발행결정 · 제3자배정 유상증자 · 최대주주 변경."""
    d = LAKE.load("dart_disclosure")
    if d is None:
        d = VAULT.get_table("dart_disclosure_list", scope="shared")
    if d is None or not len(d):
        LOG.warn("공시목록 캐시가 없습니다 — F1 은 커버리지 0 으로 Phase 0 에서 보류됩니다. "
                 "(수집하려면 DART_API_KEY 를 넣고 COLLECT_POLICY 를 GAP_ONLY 로 두세요)")
        return pd.DataFrame(columns=["code", "rcept_dt", "event", "is_private", "refix", "conv_price"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    ev = pd.Series("", index=d.index)
    ev[nm.str.contains("전환사채권발행결정|전환사채발행결정", regex=True)] = "E1_CB"
    ev[nm.str.contains("신주인수권부사채권발행결정|신주인수권부사채발행결정", regex=True)] = "E1_BW"
    ev[nm.str.contains("유상증자결정|유상증자") & ~nm.str.contains("철회|정정")] = "E2_3RD"
    ev[nm.str.contains("최대주주변경|최대주주 변경", regex=True)] = "E3_OWNER"
    d["event"] = ev
    out = d[(d["event"] != "") & d["code"].notna() & d["rcept_dt"].notna()].copy()
    #   사모/공모 구분과 리픽싱·전환가는 제목만으로는 알 수 없다. 정형 API 가 검증됐으면 그걸로
    #   보강하고, 아니면 결측으로 남긴다 — 추측해서 채우지 않는다(E1 사모한정·E4 가 그만큼 축소).
    out["is_private"] = np.nan
    out["refix"] = np.nan
    out["conv_price"] = np.nan
    out = _enrich_capital_details(out)
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    LOG.ok(f"F1 자본거래 이벤트 {len(out):,}건 · {out['code'].nunique():,}종목 "
           f"({', '.join(f'{k}:{v:,}' for k, v in out['event'].value_counts().items())})")
    return out[["code", "rcept_dt", "event", "is_private", "refix", "conv_price"]]


def _rcept_to_ts(d: pd.DataFrame) -> pd.Series:
    if "rcept_dt" in d.columns:
        s = as_ts_series(d["rcept_dt"])
        if s.notna().any():
            return s
    if "rcept_no" in d.columns:
        return pd.to_datetime(d["rcept_no"].astype(str).str.replace(r"\D", "", regex=True).str[:8],
                              format="%Y%m%d", errors="coerce")
    return pd.Series(pd.NaT, index=d.index)


def _enrich_capital_details(ev: pd.DataFrame) -> pd.DataFrame:
    """정형 API 가 검증된 경우에만 사모여부·전환가·리픽싱을 채운다."""
    hits = [k for k in ("cb", "bw", "rights") if ENDPOINT_STATUS.get(k, {}).get("verified")]
    if not hits:
        LOG.warn("CB/BW/유상증자 정형 API 가 검증되지 않아 사모여부·리픽싱·전환가를 "
                 "채우지 못했습니다. E1 은 '사모 한정' 대신 전체로, E4 는 평가 불가로 처리하고 "
                 "그 사실을 판정문에 기록합니다.")
        RUNLOG["f1_degraded"] = "사모구분·리픽싱 미가용"
    return ev


def load_insider(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F2 원천: 임원·주요주주 특정증권등 소유상황보고서."""
    d = LAKE.load("dart_insider")
    if d is None:
        d = VAULT.get_table("dart_insider_holdings", scope="shared")
    if d is None or not len(d):
        LOG.warn("내부자 지분공시 캐시가 없습니다 — F2 는 Phase 0 에서 보류됩니다.")
        return pd.DataFrame(columns=["code", "rcept_dt", "reason", "net_amount", "role"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    if "reason" not in d.columns:
        d["reason"] = ""
    d["reason"] = d["reason"].astype(str)
    if "net_amount" not in d.columns:
        d["net_amount"] = _infer_net_amount(d)
    d["role"] = d.get("insider_nm", pd.Series("", index=d.index)).astype(str)
    out = d[d["code"].notna() & d["rcept_dt"].notna()].copy()
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    LOG.ok(f"F2 내부자 지분공시 {len(out):,}건 · {out['code'].nunique():,}종목")
    return out[["code", "rcept_dt", "reason", "net_amount", "role"]]


def _infer_net_amount(d: pd.DataFrame) -> pd.Series:
    """금액 컬럼이 없으면 (변동수량 × 단가)로 만든다. 둘 다 없으면 결측 — 0 으로 채우지 않는다."""
    qty = next((c for c in d.columns if re.search(r"(증감|변동).*수량|chg.*qty", str(c))), None)
    prc = next((c for c in d.columns if re.search(r"단가|취득.*가|unit.*prc", str(c))), None)
    if qty and prc:
        return (pd.to_numeric(d[qty], errors="coerce") * pd.to_numeric(d[prc], errors="coerce"))
    LOG.warn("내부자 거래금액을 만들 컬럼(변동수량·단가)이 없습니다 — "
             "F2 랭킹변수가 결측이 되어 커버리지가 떨어집니다. 0 으로 채우지 않습니다.")
    return pd.Series(np.nan, index=d.index)


def load_contracts(codes: Sequence[str], start, end) -> pd.DataFrame:
    """F4 원천: 단일판매·공급계약체결 (+ 정정·해지 추적)."""
    d = LAKE.load("dart_contract")
    if d is None:
        d = VAULT.get_table("dart_supply_contracts", scope="shared")
    if d is None or not len(d):
        # 공시목록에서 제목만으로 잡을 수 있는지 확인 — 금액이 없으면 임계 판정을 못 하므로
        # '관측은 되나 신호 산출 불가' 로 남긴다. 이 구분이 Phase 0 의 signal_rate 다.
        dl = LAKE.load("dart_disclosure")
        if dl is not None and "report_nm" in dl.columns:
            nm = dl["report_nm"].astype(str)
            hit = dl[nm.str.contains("단일판매|공급계약")].copy()
            if len(hit):
                LOG.warn(f"공급계약 공시 {len(hit):,}건을 제목으로는 찾았으나 계약금액·매출액대비 "
                         f"비율이 없습니다. 원문 파싱 없이는 임계 0.20 판정이 불가하므로 "
                         f"F4 는 '관측 O / 신호 X' 로 기록됩니다.")
                if "code" not in hit.columns:
                    hit = map_corp_to_code(hit)
                hit["code"] = hit["code"].map(to_code6)
                hit["rcept_dt"] = _rcept_to_ts(hit)
                hit["contract_amt"] = np.nan
                hit["ratio_sales"] = np.nan
                hit["counterparty"] = ""
                hit["is_cancel"] = hit["report_nm"].astype(str).str.contains("해지|철회|취소")
                return hit[["code", "rcept_dt", "contract_amt", "ratio_sales",
                            "counterparty", "is_cancel"]].dropna(subset=["code", "rcept_dt"])
        LOG.warn("공급계약 캐시가 없습니다 — F4 는 Phase 0 에서 보류됩니다.")
        return pd.DataFrame(columns=["code", "rcept_dt", "contract_amt", "ratio_sales",
                                     "counterparty", "is_cancel"])
    d = d.copy()
    if "code" not in d.columns:
        d = map_corp_to_code(d)
    d["code"] = d["code"].map(to_code6)
    d["rcept_dt"] = _rcept_to_ts(d)
    for c in ("contract_amt", "ratio_sales"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    if "is_cancel" not in d.columns:
        nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
        d["is_cancel"] = nm.str.contains("해지|철회|취소|계약해제")
    if "counterparty" not in d.columns:
        d["counterparty"] = ""
    out = d[d["code"].notna() & d["rcept_dt"].notna()]
    out = out[(out["rcept_dt"] >= as_ts(start)) & (out["rcept_dt"] <= as_ts(end))]
    n_cancel = int(out["is_cancel"].sum())
    LOG.ok(f"F4 공급계약 {len(out):,}건 · {out['code'].nunique():,}종목 "
           f"(해지·정정 {n_cancel:,}건 = {100*n_cancel/max(len(out),1):.1f}%) — "
           f"해지 추적을 끄면 미래참조가 됩니다(§4 F4).")
    RUNLOG["f4_cancel_rate"] = float(n_cancel / max(len(out), 1))
    return out[["code", "rcept_dt", "contract_amt", "ratio_sales", "counterparty", "is_cancel"]]

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §1 유니버스 — 동결. 수정 금지.                                                           ║
# ║                                                                                          ║
# ║  적격성 게이트: 거래대금 ≥ 1억원 · 보통주 · 비스팩/비리츠 · 상장 ≥ 180일 ·                 ║
# ║                비자본잠식 · 재무 비결측                                                   ║
# ║  유니버스     : 적격 통과 종목 중 시총 하위 250(주) / 하위 500(보조)                       ║
# ║  비중         : 동일가중(EW)                                                              ║
# ║                                                                                          ║
# ║  ★ 이 게이트는 탐색 대상이 아니다(명세서 §1 주의). 임계값을 건드리는 코드 경로가           ║
# ║    아예 없도록 SPEC_UNIV 에서만 읽는다.                                                    ║
# ║  ★ 원본 KR_QUANT_SUITE_V1.py 가 있으면 4380–4394행을 파싱해 상수를 대조하고,               ║
# ║    불일치는 조용히 넘기지 않고 표로 출력한다.                                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 스팩·리츠·기타 비적격 법적 형태 (상호에 남는다)
_EXCL_NAME_PAT = re.compile(
    r"(스팩|기업인수목적|제\d+호\s*기업인수|리츠|위탁관리부동산투자|자기관리부동산투자|"
    r"기업구조조정부동산투자|리얼티|투자회사|뮤추얼펀드|사모투자|선박투자|인프라투자)")
# 우선주 (보통주만 남긴다)
_PREF_NAME_PAT = re.compile(r"(\d?우[BC]?$|우선주$|\(전환\)$|우\(전환\)$|우\d*$)")


def gate_crosscheck() -> None:
    """원본 파일이 있으면 게이트 상수를 실제로 읽어 대조한다. 없으면 그 사실을 남긴다."""
    p = os.path.expanduser(GATE_SOURCE_FILE or "")
    if not p or not os.path.exists(p):
        LOG.info(f"게이트 원본({GATE_SOURCE_FILE}) 미발견 — 명세서 §1 표의 상수로 재현합니다: "
                 f"거래대금 ≥ {SPEC_UNIV['min_amount_krw']:,}원 · 상장 ≥ "
                 f"{SPEC_UNIV['min_listing_days']}일 · 하위 {SPEC_UNIV['main_n']}/{SPEC_UNIV['aux_n']}. "
                 f"원본을 이 경로에 두면 자동 대조합니다.")
        RUNLOG["gate_source"] = "spec_table"
        return
    try:
        src = open(p, encoding="utf-8", errors="replace").read().split("\n")
        seg = "\n".join(src[4379:4394])                      # 4380–4394행 (1-based)
        nums = [int(x.replace("_", "").replace(",", ""))
                for x in re.findall(r"\b\d[\d_,]{2,}\b", seg)]
        LOG.info(f"게이트 원본 4380–4394행을 읽었습니다 ({len(seg)}자). 발견 상수: {nums[:12]}")
        miss = []
        for label, want in (("거래대금 하한", SPEC_UNIV["min_amount_krw"]),
                            ("상장일수 하한", SPEC_UNIV["min_listing_days"]),
                            ("주 유니버스 N", SPEC_UNIV["main_n"]),
                            ("보조 유니버스 N", SPEC_UNIV["aux_n"])):
            if want not in nums:
                miss.append([label, f"{want:,}", "원본 구간에서 발견되지 않음"])
        if miss:
            LOG.table(miss, ["항목", "명세서 값", "대조 결과"], ["l", "r", "l"],
                      title="⚠ 게이트 상수 대조 — 불일치(추측으로 채우지 않고 명세서 값으로 진행)")
        else:
            LOG.ok("게이트 상수 4종이 원본과 일치합니다.")
        RUNLOG["gate_source"] = f"{p}#4380-4394"
        RUNLOG["gate_sha256"] = hashlib.sha256(seg.encode("utf-8")).hexdigest()[:16]
    except Exception as e:                                   # noqa
        LOG.warn(f"게이트 원본 파싱 실패({type(e).__name__}) — 명세서 값으로 진행합니다.")
        RUNLOG["gate_source"] = "spec_table(parse_failed)"


def rebalance_dates(panel_dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """리밸런싱 시점 = 거래일 격자에 스냅된 주기 말일. (§1 기존 구현과 동일 주기 유지)"""
    d = pd.DatetimeIndex(sorted(pd.unique(panel_dates)))
    if len(d) == 0:
        return d
    if REBAL_FREQ.upper().startswith("M"):
        key = d.to_period("M")
    else:
        key = d.to_period("W-FRI")
    s = pd.Series(d, index=key)
    out = pd.DatetimeIndex(s.groupby(level=0).last().values)
    LOG.info(f"리밸런싱 주기 = {REBAL_FREQ} → 시점 {len(out):,}개 "
             f"({out[0]:%Y-%m-%d} ~ {out[-1]:%Y-%m-%d}). "
             f"'기존 구현과 동일 주기 유지'(§1) 를 이 상수로 고정했습니다.")
    return out


def build_daily_panel(px: pd.DataFrame) -> pd.DataFrame:
    """일별 패널 정규화 — 수익률·ADV·ILLIQ 원재료를 여기서 한 번만 만든다."""
    need = ["code", "date", "close"]
    for c in need:
        if c not in px.columns:
            raise StageFailure(f"가격 패널에 '{c}' 컬럼이 없습니다. 캐시 지문 판별을 확인하세요.")
    d = px.copy()
    d["code"] = d["code"].map(to_code6)
    d["date"] = as_ts_series(d["date"])
    for c in ("open", "high", "low", "close", "volume", "amount", "market_cap", "shares"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["code", "date", "close"])
    d = d[d["close"] > 0]
    d = d.sort_values(["code", "date"]).drop_duplicates(["code", "date"], keep="last")

    if "amount" not in d.columns or d["amount"].isna().all():
        if "volume" in d.columns:
            d["amount"] = d["close"] * d["volume"]
            LOG.warn("거래대금 컬럼이 없어 종가×거래량으로 근사했습니다 — 게이트(1억원)가 "
                     "그만큼 느슨해집니다(과대추정 방향). 감사표에 명시됩니다.")
        else:
            raise StageFailure("거래대금도 거래량도 없습니다 — 유동성 게이트를 걸 수 없습니다.")
    if "market_cap" not in d.columns or d["market_cap"].isna().all():
        if "shares" in d.columns and d["shares"].notna().any():
            d["market_cap"] = d["close"] * d["shares"]
            LOG.info("시가총액을 종가×상장주식수로 산출했습니다.")
        else:
            raise StageFailure("시가총액도 상장주식수도 없습니다 — 시총 하위 250 을 정의할 수 없습니다.")

    g = d.groupby("code", observed=True)
    d["ret1d"] = g["close"].pct_change()
    #   게이트의 '거래대금'은 단일일 값이 아니라 20세션 중앙값을 쓴다.
    #   하루치로 재면 상한가 하루가 종목을 통과시켜 유니버스가 그날그날 요동친다.
    d["adv20"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=10).median())
    d["adv20_mean"] = g["amount"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    LOG.ok(f"일별 패널 {len(d):,}행 · 종목 {d['code'].nunique():,}개 · "
           f"{d['date'].min():%Y-%m-%d} ~ {d['date'].max():%Y-%m-%d}")
    PIPE.io("OUT", "MEM", "daily_panel", d)
    return downcast(d)


def _is_common(code: str, name: str) -> bool:
    """보통주 판별. 코드 끝자리(신형우선주는 K/L/M)와 상호를 함께 본다."""
    c, n = str(code), str(name or "")
    if not c or len(c) != 6:
        return False
    if c[-1] not in "0":                     # 우선주 5/7/9, 신형우선주 K·L·M
        return False
    return not bool(_PREF_NAME_PAT.search(n.strip()))


def build_eligibility(daily: pd.DataFrame, sec: pd.DataFrame, fin: pd.DataFrame,
                      rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """리밸런싱 시점 × 종목 적격성 패널. 게이트 6종을 각각 컬럼으로 남겨 감쇠를 감사한다."""
    snap = daily[daily["date"].isin(rebals)][
        ["code", "date", "close", "amount", "adv20", "adv20_mean", "market_cap"]].copy()
    snap = snap.rename(columns={"date": "rebal"})
    #   daily 는 메모리를 아끼려고 code 를 categorical 로 두지만, 이 스냅샷부터는
    #   merge_asof·map 이 dtype 일치를 요구하므로 문자열로 확정한다.
    snap["code"] = snap["code"].astype(str)
    if not len(snap):
        raise StageFailure("리밸런싱 시점에 해당하는 가격 스냅샷이 없습니다.")

    s = sec.drop_duplicates("code").set_index("code")
    #   downcast 로 code 가 categorical 이 되어 있으면 map 결과도 categorical 이 되고,
    #   그 뒤의 fillna("")·str.contains 가 조용히가 아니라 요란하게 터진다. 문자열로 못박는다.
    _codes = snap["code"].astype(str)
    snap["name"] = (_codes.map(s["name"]).astype(object).fillna("").astype(str)
                    if "name" in s.columns else "")
    for c in ("listing_date", "delisting_date"):
        snap[c] = (pd.to_datetime(_codes.map(s[c]).astype(object), errors="coerce")
                   if c in s.columns else pd.NaT)

    # ── 게이트 6종 ─────────────────────────────────────────────────────────────────────
    snap["g_amount"] = snap["adv20"] >= SPEC_UNIV["min_amount_krw"]
    snap["g_common"] = [_is_common(c, n) for c, n in zip(_codes, snap["name"])]
    snap["g_form"] = ~snap["name"].str.contains(_EXCL_NAME_PAT)
    age = (snap["rebal"] - snap["listing_date"]).dt.days
    #   상장일을 모르는 종목을 통과시키면 신규상장이 섞이고, 막으면 오래된 종목이 사라진다.
    #   후자가 선택편향으로 덜 위험하므로 '모르면 탈락'으로 두고 그 건수를 로그에 남긴다.
    snap["g_age"] = age.notna() & (age >= SPEC_UNIV["min_listing_days"])
    n_noage = int(age.isna().sum())

    # 자본잠식·재무결측 — PIT(공시 접수일 기준) 로 붙인다
    snap = attach_pit_financials(snap, fin)
    eq, cap = snap.get("equity"), snap.get("capital")
    if eq is None:
        snap["g_solvent"], snap["g_fin"] = True, False
        LOG.warn("재무(자본총계)를 붙이지 못해 자본잠식 게이트가 무력화됩니다 — "
                 "유니버스가 명세와 달라집니다. 캐시의 재무 테이블을 확인하세요.")
    else:
        impaired_full = eq <= 0
        impaired_part = (cap.notna() & (eq < cap)) if cap is not None else pd.Series(False, index=eq.index)
        snap["g_solvent"] = ~(impaired_full | impaired_part).fillna(False)
        snap["g_fin"] = eq.notna() & snap.get("revenue", pd.Series(np.nan, index=eq.index)).notna()
        RUNLOG["impair_full_only_delta"] = int((impaired_part & ~impaired_full).sum())
        LOG.info(f"자본잠식 = 자본총계 ≤ 0(완전) 또는 자본총계 < 자본금(부분). "
                 f"부분잠식만으로 탈락한 (종목×시점) {RUNLOG['impair_full_only_delta']:,}건 — "
                 f"완전잠식만 적용했다면 이만큼 더 남았을 것입니다(진단용, 대안 백테스트 아님).")

    gates = ["g_amount", "g_common", "g_form", "g_age", "g_solvent", "g_fin"]
    snap["eligible"] = snap[gates].all(axis=1)

    # ── 유니버스 감쇠 감사 ─────────────────────────────────────────────────────────────
    tot = len(snap)
    rows, alive = [], pd.Series(True, index=snap.index)
    for g, label in zip(gates, ["거래대금 ≥ 1억", "보통주", "비스팩/비리츠", "상장 ≥ 180일",
                                "비자본잠식", "재무 비결측"]):
        before = int(alive.sum())
        alive &= snap[g]
        rows.append([label, f"{before:,}", f"{int(alive.sum()):,}",
                     f"−{before - int(alive.sum()):,}",
                     f"{100*(before-int(alive.sum()))/max(before,1):.1f}%"])
    LOG.table(rows, ["게이트", "적용 전", "적용 후", "탈락", "탈락률"], ["l", "r", "r", "r", "r"],
              title=f"유니버스 감쇠 감사 — (종목×리밸) {tot:,}셀 중 적격 {int(snap['eligible'].sum()):,}셀")
    if n_noage:
        LOG.info(f"상장일 미상으로 탈락한 셀 {n_noage:,}건 (신규상장 혼입 방지를 위한 보수 처리).")
    PIPE.io("OUT", "MEM", "eligibility", snap)
    return snap


def build_universe(elig: pd.DataFrame) -> pd.DataFrame:
    """적격 종목 중 시총 하위 N. as-of 리밸런싱 시점마다 새로 뽑는다."""
    e = elig[elig["eligible"] & elig["market_cap"].notna() & (elig["market_cap"] > 0)].copy()
    e = e.sort_values(["rebal", "market_cap"])
    e["cap_rank"] = e.groupby("rebal", observed=True)["market_cap"].rank(method="first")
    e["u250"] = e["cap_rank"] <= SPEC_UNIV["main_n"]
    e["u500"] = e["cap_rank"] <= SPEC_UNIV["aux_n"]
    cnt = e.groupby("rebal")["u250"].sum()
    short = int((cnt < SPEC_UNIV["main_n"]).sum())
    LOG.ok(f"유니버스 구성 완료 — U250 리밸당 평균 {cnt.mean():.1f}종목 "
           f"(최소 {int(cnt.min())}, 최대 {int(cnt.max())})")
    if short:
        LOG.warn(f"적격 종목이 {SPEC_UNIV['main_n']}개에 못 미친 리밸 시점 {short:,}개 — "
                 f"그 시점은 있는 만큼만 담습니다(빈자리를 부적격으로 채우지 않습니다).")
    RUNLOG["u250_mean_count"] = float(cnt.mean())
    PIPE.io("OUT", "MEM", "universe", e)
    return e

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §5 비용 모형 + 백테스트 엔진                                                             ║
# ║                                                                                          ║
# ║  "순수익 없이는 어떤 판정도 하지 않는다."                                                  ║
# ║  그래서 총수익 경로는 B1 하나뿐이고, 나머지 전 산출물은 비용을 통과해야만 나온다.           ║
# ║                                                                                          ║
# ║  스프레드는 종목별 실측을 우선한다 — Corwin-Schultz(2012) 고저가 추정량을 일별 OHLC 로     ║
# ║  계산하고, 추정이 불가한 구간에만 시총분위별 보수 고정값으로 폴백한다.                      ║
# ║  (마이크로캡에서 스프레드를 상수로 두면 소형일수록 비용이 과소계상돼 결론이 뒤집힌다)       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def tax_rate(year: int, market: str) -> float:
    """연도별 증권거래세 실효율 (매도 시). 하드코딩이 아니라 테이블 조회다(§5)."""
    row = SPEC_TAX_TABLE[0]
    for r in SPEC_TAX_TABLE:
        if year >= r[0]:
            row = r
    return row[2] if str(market).upper().startswith("KOSDAQ") else row[1]


def corwin_schultz_spread(daily: pd.DataFrame) -> pd.DataFrame:
    """일별 고저가로 종목별 유효 스프레드(편도, 비율)를 추정한다.

    음수 추정치는 0 이 아니라 결측으로 둔다 — 0 으로 밀면 '비용 없는 종목'이 생기고
    그 종목이 정확히 마이크로캡이라 결론을 오염시킨다.
    """
    if not {"high", "low"} <= set(daily.columns):
        LOG.warn("고가·저가가 없어 Corwin-Schultz 스프레드 실측을 건너뜁니다 → "
                 "전 구간 시총분위 폴백값을 사용합니다(§5 '값과 근거를 로그에 명시').")
        return pd.DataFrame(columns=["code", "date", "spread_cs"])
    d = daily[["code", "date", "high", "low"]].copy()
    d["code"] = d["code"].astype(str)
    d = d[(d["high"] > 0) & (d["low"] > 0)].sort_values(["code", "date"])
    g = d.groupby("code", observed=True)
    h1, l1 = g["high"].shift(-1), g["low"].shift(-1)
    beta = np.log(d["high"] / d["low"]) ** 2 + np.log(h1 / l1) ** 2
    h2 = np.maximum(d["high"], h1)
    l2 = np.minimum(d["low"], l1)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    d["spread_cs"] = np.where(np.isfinite(s) & (s > 0) & (s < 0.25), s, np.nan)
    #   2일 추정치는 잡음이 크다 → 60세션 중앙값으로 눌러 쓴다(리밸 시점 조회용).
    d["spread_cs"] = d.groupby("code", observed=True)["spread_cs"].transform(
        lambda s: s.rolling(60, min_periods=20).median())
    out = d[["code", "date", "spread_cs"]].reset_index(drop=True)
    ok = int(out["spread_cs"].notna().sum())
    LOG.ok(f"Corwin-Schultz 스프레드 실측 {ok:,}셀 "
           f"(중앙값 편도 {100*out['spread_cs'].median():.3f}% ) — "
           f"결측 셀은 시총분위 폴백값을 씁니다.")
    return out


@dataclass
class CostModel:
    """§5 비용 모형. AUM 을 받아 종목별 왕복 비용률을 만든다."""
    spread_map: Optional[pd.DataFrame] = None      # (code, rebal) → 편도 스프레드
    market_map: Optional[pd.Series] = None         # code → KOSPI/KOSDAQ
    cap_quintile: Optional[pd.DataFrame] = None    # (code, rebal) → 1(소)~5(대)
    adv: Optional[pd.DataFrame] = None             # (code, rebal) → 20일 평균거래대금
    fallback_used: int = 0
    measured_used: int = 0

    def one_way(self, rebal: pd.Timestamp, codes: pd.Index, notional: np.ndarray) -> np.ndarray:
        """편도 비용률 (세금 제외). notional = 이 리밸에서 그 종목에 실제로 넣고 빼는 금액."""
        sp = self._spread(rebal, codes)
        adv = self._adv(rebal, codes)
        impact = SPEC_COST["impact_coef"] * np.sqrt(np.maximum(notional, 0.0) / np.maximum(adv, 1.0))
        return (sp / 2.0
                + SPEC_COST["commission_roundtrip"] / 2.0
                + SPEC_COST["slippage_bp"] / 1e4
                + impact)

    def sell_tax(self, rebal: pd.Timestamp, codes: pd.Index) -> np.ndarray:
        mk = (self.market_map.reindex(codes).fillna("KOSDAQ").to_numpy()
              if self.market_map is not None else np.array(["KOSDAQ"] * len(codes)))
        y = int(pd.Timestamp(rebal).year)
        return np.array([tax_rate(y, m) for m in mk])

    def _spread(self, rebal, codes) -> np.ndarray:
        base = np.full(len(codes), np.nan)
        if self.spread_map is not None:
            s = self.spread_map.get(rebal)
            if s is not None:
                base = s.reindex(codes).to_numpy(dtype=float)
        miss = ~np.isfinite(base)
        if miss.any():
            q = np.full(len(codes), 1)
            if self.cap_quintile is not None:
                qq = self.cap_quintile.get(rebal)
                if qq is not None:
                    q = qq.reindex(codes).fillna(1).astype(int).to_numpy()
            fb = np.array([SPEC_COST["spread_fallback_bp"].get(int(x), 90.0) / 1e4 for x in q])
            base = np.where(miss, fb, base)
            self.fallback_used += int(miss.sum())
        self.measured_used += int((~miss).sum())
        return base

    def _adv(self, rebal, codes) -> np.ndarray:
        if self.adv is None:
            return np.full(len(codes), 1e9)
        a = self.adv.get(rebal)
        if a is None:
            return np.full(len(codes), 1e9)
        return a.reindex(codes).fillna(1e7).to_numpy(dtype=float)

    def report(self):
        tot = self.measured_used + self.fallback_used
        if tot:
            LOG.info(f"스프레드 출처 — 실측(Corwin-Schultz) {100*self.measured_used/tot:.1f}% · "
                     f"시총분위 폴백 {100*self.fallback_used/tot:.1f}% "
                     f"(폴백 근거: {SPEC_COST['spread_fallback_basis']})")


@dataclass
class BTResult:
    name: str
    nav: pd.Series                # 순수익 NAV
    nav_gross: pd.Series
    ret: pd.Series                # 리밸 구간 순수익률
    ret_gross: pd.Series
    turnover: pd.Series
    cost: pd.Series
    n_holdings: pd.Series
    weights: Dict[pd.Timestamp, pd.Series] = field(default_factory=dict)

    def stats(self, periods_per_year: float) -> dict:
        r = self.ret.dropna()
        if not len(r):
            return dict(cagr=np.nan, vol=np.nan, mdd=np.nan, sharpe=np.nan,
                        turnover=np.nan, cost=np.nan, n=0)
        yrs = len(r) / periods_per_year
        cagr = (self.nav.iloc[-1]) ** (1 / max(yrs, 1e-9)) - 1 if self.nav.iloc[-1] > 0 else -1.0
        vol = r.std(ddof=1) * np.sqrt(periods_per_year)
        dd = self.nav / self.nav.cummax() - 1
        return dict(cagr=float(cagr), vol=float(vol), mdd=float(dd.min()),
                    sharpe=float(cagr / vol) if vol > 0 else np.nan,
                    turnover=float(self.turnover.mean() * periods_per_year),
                    cost=float(self.cost.sum()), n=int(len(r)),
                    final_nav=float(self.nav.iloc[-1]))

    def yearly(self) -> pd.Series:
        r = self.ret.dropna()
        if not len(r):
            return pd.Series(dtype=float)
        return r.groupby(r.index.year).apply(lambda x: float((1 + x).prod() - 1))


class Engine:
    """동일가중(EW) 리밸런싱 백테스터. 선택 함수만 갈아끼우면 B1~B4·F1~F4 가 전부 나온다."""

    def __init__(self, rebals: pd.DatetimeIndex, fwd: pd.DataFrame, cost: CostModel,
                 delist: Optional[pd.DataFrame] = None):
        self.rebals = rebals
        self.fwd = fwd                 # index=rebal, columns=code, 값=구간 총수익률
        self.cost = cost
        self.delist = delist           # index=rebal, columns=code, True=이 구간에 폐지
        self.ppy = 52.0 if not REBAL_FREQ.upper().startswith("M") else 12.0

    def run(self, select: Callable[[pd.Timestamp], Sequence[str]], name: str,
            aum0: float = 100_000_000, dynamic_aum: bool = False,
            keep_weights: bool = False) -> BTResult:
        nav, nav_g = 1.0, 1.0
        prev_w = pd.Series(dtype=float)
        navs, navs_g, rets, rets_g, tos, costs, ns = [], [], [], [], [], [], []
        wkeep: Dict[pd.Timestamp, pd.Series] = {}
        idx = []
        for t in self.rebals:
            if t not in self.fwd.index:
                continue
            sel = [c for c in select(t) if c]
            if not sel:
                #   빈 포트폴리오 = 현금. 0% 로 기록하되 그 사실이 보이도록 종목수 0 을 남긴다.
                idx.append(t); navs.append(nav); navs_g.append(nav_g)
                rets.append(0.0); rets_g.append(0.0); tos.append(0.0); costs.append(0.0); ns.append(0)
                prev_w = pd.Series(dtype=float)
                continue
            w = pd.Series(1.0 / len(sel), index=pd.Index(sel, name="code"))
            allc = prev_w.index.union(w.index)
            dw = (w.reindex(allc).fillna(0.0) - prev_w.reindex(allc).fillna(0.0))
            aum = (aum0 * nav) if dynamic_aum else aum0
            notional = np.abs(dw.to_numpy()) * aum
            ow = self.cost.one_way(t, allc, notional)
            tax = self.cost.sell_tax(t, allc)
            buy = np.maximum(dw.to_numpy(), 0.0)
            sell = np.maximum(-dw.to_numpy(), 0.0)
            c = float((buy * ow).sum() + (sell * (ow + tax)).sum())

            r = self.fwd.loc[t].reindex(w.index)
            if self.delist is not None and t in self.delist.index:
                dl = self.delist.loc[t].reindex(w.index).fillna(False).astype(bool)
                r = r.where(~dl, -1.0)                 # 정리매매가 없으면 −100% (누락 금지)
            #   수익률이 결측인 종목은 '그 구간 현금'이 아니라 '보유 불가'다.
            #   결측을 0 으로 채우면 폐지·거래정지가 무위험 자산이 된다 → 명시적으로 제외하고
            #   남은 종목으로 비중을 재정규화한다(그 사실은 n_holdings 로 드러난다).
            ok = r.notna()
            rp = float(r[ok].mean()) if ok.any() else 0.0
            nav_g *= (1 + rp)
            nav *= (1 + rp) * (1 - c)
            #   다음 리밸의 시작 비중 = 수익률로 드리프트된 비중
            drift = (w[ok] * (1 + r[ok]))
            prev_w = drift / drift.sum() if drift.sum() > 0 else pd.Series(dtype=float)
            idx.append(t); navs.append(nav); navs_g.append(nav_g)
            rets.append((1 + rp) * (1 - c) - 1); rets_g.append(rp)
            tos.append(float(np.abs(dw).sum() / 2.0)); costs.append(c); ns.append(int(ok.sum()))
            if keep_weights:
                wkeep[t] = w
        I = pd.DatetimeIndex(idx)
        return BTResult(name, pd.Series(navs, index=I), pd.Series(navs_g, index=I),
                        pd.Series(rets, index=I), pd.Series(rets_g, index=I),
                        pd.Series(tos, index=I), pd.Series(costs, index=I),
                        pd.Series(ns, index=I), wkeep)


def build_forward_returns(daily: pd.DataFrame, rebals: pd.DatetimeIndex,
                          sec: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """리밸 구간 수익률 행렬. 체결가 = 신호일 다음 거래일 시가(없으면 종가).

    ★ 폐지 구간은 −100%. 가격이 사라졌다고 수익률을 결측 처리하면 그게 생존자편향이다.
    """
    d = daily.sort_values(["code", "date"]).copy()
    g = d.groupby("code", observed=True)
    d["next_open"] = g["open"].shift(-1) if "open" in d.columns else np.nan
    d["next_date"] = g["date"].shift(-1)
    gap = (d["next_date"] - d["date"]).dt.days
    d["exec_px"] = d["next_open"].where(gap.notna() & (gap <= 10) & (d["next_open"] > 0))
    d["exec_px"] = d["exec_px"].fillna(d["close"])
    snap = d[d["date"].isin(rebals)][["code", "date", "exec_px"]].copy()
    snap["code"] = snap["code"].astype(str)
    M = snap.pivot_table(index="date", columns="code", values="exec_px", aggfunc="last")
    M.columns = M.columns.astype(str)
    M = M.reindex(rebals)
    FWD = M.shift(-1) / M - 1.0

    # 폐지 처리 — 폐지일이 구간 안에 들어오면 그 구간을 −100% 로 못박는다
    DEL = pd.DataFrame(False, index=FWD.index, columns=FWD.columns)
    if sec is not None and "delisting_date" in sec.columns:
        dl = sec.dropna(subset=["delisting_date"]).set_index("code")["delisting_date"]
        dl = dl[dl.index.isin(FWD.columns)]
        starts = FWD.index
        ends = list(FWD.index[1:]) + [FWD.index[-1] + pd.Timedelta(days=400)]
        for c, dt in dl.items():
            j = np.searchsorted(np.array(starts), np.datetime64(dt), side="right") - 1
            if 0 <= j < len(starts) and dt <= ends[j]:
                DEL.iloc[j, DEL.columns.get_loc(c)] = True
    #   마지막 시점은 전방 수익률이 없다. 남겨 두면 '수익 0% 인데 비용은 낸 구간'이 하나
    #   생겨 전 전략의 CAGR 이 똑같이 조금씩 깎인다. 아예 구간에서 뺀다.
    if len(FWD) and FWD.iloc[-1].isna().all():
        FWD, DEL = FWD.iloc[:-1], DEL.iloc[:-1]
    n_del = int(DEL.to_numpy().sum())
    LOG.ok(f"구간 수익률 행렬 {FWD.shape[0]:,}시점 × {FWD.shape[1]:,}종목 · "
           f"폐지로 −100% 처리된 (종목×구간) {n_del:,}건")
    if n_del == 0 and sec is not None and "delisting_date" in sec.columns:
        LOG.warn("폐지 처리 건수가 0입니다 — 폐지일이 패널 구간과 겹치지 않거나 매핑이 어긋난 "
                 "것일 수 있습니다. 생존자편향이 남아 있는지 확인하세요.")
    return FWD, DEL

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §3 Phase 0 — 커버리지 진단 (선행 필수, 게이트)                                           ║
# ║                                                                                          ║
# ║  팩터 백테스트 전에 반드시 먼저 실행한다. 커버리지가 미달이면 백테스트 없이 보류한다.       ║
# ║                                                                                          ║
# ║  ★ 이 절의 진짜 목적은 '데이터가 있냐'가 아니다. 커버 자체가 알파인 경우를 분리하는 것이다. ║
# ║    그래서 커버 종목만 담은 B_cov 를 따로 돌리고, 팩터 성과를 B2 와 B_cov 양쪽에 견준다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

@dataclass
class Coverage:
    factor: str
    cov_stock: float
    cov_stock_rebal: float
    cov_universe_rebal: pd.Series      # 리밸 시점별 U250 내 관측 종목수
    cov_trend: pd.Series               # 연도별 중앙값
    signal_rate: float
    median_cov: float
    verdict: str                       # PASS | PARTIAL | HOLD
    covered_codes: Dict[pd.Timestamp, set] = field(default_factory=dict)
    bias: Optional[pd.DataFrame] = None

    @property
    def proceed(self) -> bool:
        return self.verdict in ("PASS", "PARTIAL")


def coverage_diag(factor: str, obs: pd.DataFrame, sig: pd.DataFrame,
                  univ: pd.DataFrame, rebals: pd.DatetimeIndex,
                  all_codes: Sequence[str]) -> Coverage:
    """obs = (code, rebal) 관측 셀, sig = 그 중 실제 신호가 켜진 셀."""
    u = univ[univ["u250"]]
    u_by_t = {t: set(g["code"]) for t, g in u.groupby("rebal", observed=True)}
    obs_by_t = ({t: set(g["code"]) for t, g in obs.groupby("rebal", observed=True)}
                if len(obs) else {})
    cov_ts = pd.Series({t: len(u_by_t.get(t, set()) & obs_by_t.get(t, set())) for t in rebals},
                       dtype=float).sort_index()
    covered = {t: (u_by_t.get(t, set()) & obs_by_t.get(t, set())) for t in rebals}

    n_all = max(len(set(all_codes)), 1)
    cov_stock = len(set(obs["code"])) / n_all if len(obs) else 0.0
    cells = sum(len(v) for v in u_by_t.values())
    cov_cell = (cov_ts.sum() / cells) if cells else 0.0
    trend = cov_ts.groupby(cov_ts.index.year).median()
    srate = (len(sig) / max(len(obs), 1)) if len(obs) else 0.0
    med = float(cov_ts.median()) if len(cov_ts) else 0.0

    if med >= SPEC_COV["pass_median"]:
        verdict = "PASS"
    elif med >= SPEC_COV["hold_median"]:
        verdict = "PARTIAL"
    else:
        verdict = "HOLD"

    LOG.table(
        [["cov_stock", f"{cov_stock:.1%}", "전 기간 중 1회 이상 관측된 종목 비율"],
         ["cov_stock_rebal", f"{cov_cell:.1%}", "(종목×리밸) 셀 중 관측 비율 — U250 기준"],
         ["cov_universe_rebal 중앙값", f"{med:.0f}종목",
          f"기준: ≥{SPEC_COV['pass_median']} 정상 / {SPEC_COV['hold_median']}~"
          f"{SPEC_COV['pass_median']} 부분 / <{SPEC_COV['hold_median']} 보류"],
         ["signal_rate", f"{srate:.1%}", "관측된 것 중 실제로 신호가 발생한 셀 비율"],
         ["판정", verdict, {"PASS": "정상 진행", "PARTIAL": "부분 커버 팩터로 표기하고 진행",
                            "HOLD": "★백테스트 보류 (§6.4 조기 중단)"}[verdict]]],
        ["지표", "값", "정의 / 기준"], ["l", "r", "l"],
        title=f"[{factor}] Phase 0 커버리지 진단")
    if len(trend) > 1:
        LOG.table([[str(y), f"{v:.0f}"] for y, v in trend.items()],
                  ["연도", "U250 내 관측 종목수(중앙값)"], ["c", "r"],
                  title=f"[{factor}] cov_trend — 초기 연도 결측 급증 여부")
    return Coverage(factor, cov_stock, cov_cell, cov_ts, trend, srate, med, verdict, covered)


def coverage_bias(cov: Coverage, univ: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """커버 종목 vs 미커버 종목의 시총·거래대금·업종 분포 비교 (§3 추가 필수 진단)."""
    u = univ[univ["u250"]].copy()
    u["covered"] = [c in cov.covered_codes.get(t, set())
                    for t, c in zip(u["rebal"], u["code"])]
    if u["covered"].nunique() < 2:
        LOG.warn(f"[{cov.factor}] 커버/미커버 한쪽이 비어 선택편향 비교를 할 수 없습니다.")
        return pd.DataFrame()
    ind = sec.drop_duplicates("code").set_index("code").get("industry")
    u["industry"] = u["code"].map(ind) if ind is not None else ""
    rows = []
    for col, label in (("market_cap", "시가총액"), ("adv20", "20일 중앙 거래대금")):
        if col not in u.columns:
            continue
        a = u.loc[u["covered"], col].dropna()
        b = u.loc[~u["covered"], col].dropna()
        if not len(a) or not len(b):
            continue
        rows.append([label, f"{a.median():,.0f}", f"{b.median():,.0f}",
                     f"{a.median()/max(b.median(),1):.2f}x"])
    top = (u[u["covered"]]["industry"].value_counts(normalize=True).head(3))
    rows.append(["상위 업종(커버)", ", ".join(f"{k} {v:.0%}" for k, v in top.items()), "", ""])
    LOG.table(rows, ["항목", "커버 종목", "미커버 종목", "배수"], ["l", "r", "r", "r"],
              title=f"[{cov.factor}] 커버리지 선택편향 진단 — 커버 자체가 알파인가")
    out = u.groupby(["rebal", "covered"], observed=True).agg(
        n=("code", "size"), mktcap_med=("market_cap", "median"),
        adv_med=("adv20", "median")).reset_index()
    cov.bias = out
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §2 베이스라인 B1~B4                                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def run_baselines(eng: Engine, univ: pd.DataFrame, elig: pd.DataFrame,
                  window: str = "IS") -> Dict[str, BTResult]:
    u_by_t = {t: list(g["code"]) for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}
    e_by_t = {t: list(g["code"]) for t, g in elig[elig["eligible"]].groupby("rebal", observed=True)}
    reb = _window_rebals(eng.rebals, window)
    e2 = Engine(reb, eng.fwd, eng.cost, eng.delist)
    out = {}
    out["B1"] = e2.run(lambda t: u_by_t.get(t, []), "B1 U250 EW 총수익")
    out["B2"] = e2.run(lambda t: u_by_t.get(t, []), "B2 U250 EW 순수익")
    out["B3"] = e2.run(lambda t: e_by_t.get(t, []), "B3 적격 전종목 EW 순수익")
    #   B1 은 '총수익'이므로 NAV 를 총수익 계열로 바꿔 끼운다 (엔진은 둘 다 계산해 둔다)
    b1 = out["B1"]
    out["B1"] = BTResult(b1.name, b1.nav_gross, b1.nav_gross, b1.ret_gross, b1.ret_gross,
                         b1.turnover, pd.Series(0.0, index=b1.cost.index), b1.n_holdings)
    return out


def _window_rebals(rebals: pd.DatetimeIndex, window: str) -> pd.DatetimeIndex:
    m = SEAL.mask(rebals, window)
    return pd.DatetimeIndex(pd.Series(list(rebals))[m.to_numpy()].tolist())


def random_null(eng: Engine, univ: pd.DataFrame, n: int, sims: int = SPEC_B4_SIMS,
                window: str = "IS", aum: float = 100_000_000,
                match_turnover: Optional[float] = None) -> Dict[str, Any]:
    """B4 — U250 내 무작위 n종목 EW 를 sims 회. 팩터 선별력의 귀무분포.

    ★ 팩터로 뽑은 성과는 반드시 이 분포 안에서 위치를 본다. 절대 CAGR 은 판정에 쓰지 않는다.
    match_turnover 를 주면 '직전 보유를 그만큼 유지하는' 회전율 정합 귀무분포도 함께 만든다
    (무작위는 회전율이 100%에 가까워 비용 차가 스프레드에 섞이기 때문 — 보조 진단용).
    """
    reb = _window_rebals(eng.rebals, window)
    codes = list(eng.fwd.columns)
    cidx = {c: i for i, c in enumerate(codes)}
    u_by_t = {t: np.array([cidx[c] for c in g["code"] if c in cidx], dtype=np.int64)
              for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}
    rng = np.random.default_rng(SEED)
    W = np.zeros((sims, len(codes)), dtype=np.float32)
    nav = np.ones(sims, dtype=np.float64)
    navs = []
    used = 0
    for t in reb:
        if t not in eng.fwd.index:
            continue
        av = u_by_t.get(t)
        if av is None or len(av) == 0:
            continue
        r_all = eng.fwd.loc[t].to_numpy(dtype=np.float64)
        if eng.delist is not None and t in eng.delist.index:
            dl = eng.delist.loc[t].to_numpy(dtype=bool)
            r_all = np.where(dl, -1.0, r_all)
        av = av[np.isfinite(r_all[av])]
        if len(av) < n:
            continue
        # sims × n 무복원 추출 — 난수 정렬의 앞 n개
        rnd = rng.random((sims, len(av)))
        if match_turnover is not None and used > 0:
            #   회전율 정합 — 직전 보유 중 (1−회전율) 만큼은 유지하고 나머지만 새로 뽑는다.
            #   유지분과 신규분이 겹치지 않도록 각각의 난수 키에 벌점을 준다.
            keep = int(round(n * min(1.0, max(0.0, 1.0 - float(match_turnover)))))
            held = W[:, av] > 0
            fresh = np.where(held, 2.0, rnd)
            new_i = av[np.argpartition(fresh, max(n - keep, 1) - 1, axis=1)[:, :max(n - keep, 0)]]
            if keep > 0:
                keep_i = av[np.argpartition(np.where(held, rnd, 2.0), keep - 1, axis=1)[:, :keep]]
                pick = np.concatenate([keep_i, new_i], axis=1)
            else:
                pick = new_i
        else:
            pick = av[np.argpartition(rnd, n - 1, axis=1)[:, :n]]
        #   put_along_axis 로 '1 을 세팅'한 뒤 행 정규화한다. 중복 인덱스가 섞여도
        #   (회전율 정합 경로에서 발생 가능) 고유 종목에 대한 정확한 동일가중이 된다.
        Wn = np.zeros_like(W)
        np.put_along_axis(Wn, pick, np.float32(1.0), axis=1)
        _s = Wn.sum(axis=1, keepdims=True)
        Wn = np.divide(Wn, np.where(_s > 0, _s, 1.0), dtype=np.float32)
        dW = Wn - W
        notional = np.abs(dW).astype(np.float64) * aum
        ow = _cost_matrix(eng.cost, t, codes, notional)
        tax = eng.cost.sell_tax(t, pd.Index(codes))[None, :]
        buy = np.maximum(dW, 0.0).astype(np.float64)
        sell = np.maximum(-dW, 0.0).astype(np.float64)
        c = (buy * ow).sum(axis=1) + (sell * (ow + tax)).sum(axis=1)
        #   수익률은 '실제로 보유한 고유 종목의 동일가중 평균' = Wn·r 이다.
        #   pick 평균으로 계산하면 중복분이 두 번 세어진다.
        r = (Wn.astype(np.float64) * np.nan_to_num(r_all, nan=0.0)[None, :]).sum(axis=1)
        nav *= (1.0 + r) * (1.0 - c)
        drift = Wn * (1.0 + np.nan_to_num(r_all, nan=0.0)[None, :]).astype(np.float32)
        s = drift.sum(axis=1, keepdims=True)
        W = np.divide(drift, np.where(s > 0, s, 1.0), dtype=np.float32)
        navs.append(nav.copy())
        used += 1
    if not navs:
        return dict(n=n, sims=0, cagr=np.array([]), p95=np.nan, median=np.nan)
    ppy = eng.ppy
    yrs = used / ppy
    final = navs[-1]
    cagr = np.where(final > 0, np.power(np.maximum(final, 1e-12), 1.0 / max(yrs, 1e-9)) - 1, -1.0)
    LOG.ok(f"B4 무작위 귀무분포 (N={n}, {sims:,}회, {used}시점) — "
           f"CAGR 중앙 {np.median(cagr):.2%} · 상위5% 경계 {np.quantile(cagr, 0.95):.2%} · "
           f"상위1% {np.quantile(cagr, 0.99):.2%}"
           + ("  [회전율 정합]" if match_turnover is not None else ""))
    return dict(n=n, sims=sims, cagr=cagr, p95=float(np.quantile(cagr, 0.95)),
                median=float(np.median(cagr)), periods=used,
                matched=match_turnover is not None)


def _cost_matrix(cm: CostModel, t, codes: Sequence[str], notional: np.ndarray) -> np.ndarray:
    idx = pd.Index(codes)
    sp = cm._spread(t, idx)[None, :]
    adv = cm._adv(t, idx)[None, :]
    impact = SPEC_COST["impact_coef"] * np.sqrt(np.maximum(notional, 0.0) / np.maximum(adv, 1.0))
    return sp / 2.0 + SPEC_COST["commission_roundtrip"] / 2.0 + SPEC_COST["slippage_bp"] / 1e4 + impact

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §4 팩터 명세 F1~F4 — 각각 독립 실행. 결합 백테스트는 이 명세 범위 밖(§8-1).               ║
# ║                                                                                          ║
# ║  공통 규약                                                                                ║
# ║   · PIT   : 모든 신호는 공시 접수일 + 1영업일부터 사용 가능. 정정 전 원본을 쓴다.           ║
# ║   · 룩어헤드 금지 : 전 기간으로 학습한 정규화 파라미터를 쓰지 않는다.                      ║
# ║   · 미커버 : neutral(랭킹=중앙값 / 필터=통과) 와 exclude(후보에서 제외) 두 방식 모두 산출.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

@dataclass
class FactorSignal:
    factor: str
    variant: str
    obs: pd.DataFrame        # (code, rebal) — 소스가 값을 낼 수 있었던 셀
    sig: pd.DataFrame        # (code, rebal, score) — 실제로 신호가 켜진 셀
    kind: str                # filter | rank | event
    note: str = ""

    def selector(self, univ_by_t: Dict[pd.Timestamp, List[str]], n: Optional[int],
                 uncov: str) -> Callable[[pd.Timestamp], List[str]]:
        cov_by_t = {t: set(g["code"]) for t, g in self.obs.groupby("rebal", observed=True)} \
            if len(self.obs) else {}
        sig_by_t = {t: g for t, g in self.sig.groupby("rebal", observed=True)} if len(self.sig) else {}

        if self.kind == "filter":
            def sel(t):
                cand = list(univ_by_t.get(t, []))
                flagged = set(sig_by_t.get(t, pd.DataFrame(columns=["code"]))["code"])
                out = [c for c in cand if c not in flagged]
                if uncov == "exclude":
                    cov = cov_by_t.get(t, set())
                    out = [c for c in out if c in cov]
                return out
            return sel

        def sel(t):
            cand = list(univ_by_t.get(t, []))
            if not cand:
                return []
            s = sig_by_t.get(t)
            score = pd.Series(np.nan, index=pd.Index(cand, name="code"))
            if s is not None and len(s):
                v = s.set_index("code")["score"]
                score.update(v.reindex(score.index).dropna())
            cov = cov_by_t.get(t, set())
            if uncov == "exclude":
                score = score[[c in cov for c in score.index]]
            else:
                #   중립 = 중앙값 부여. 이 시점 횡단면 중앙값만 쓴다(전 기간 통계 금지).
                med = score.median()
                score = score.fillna(med if np.isfinite(med) else 0.0)
            score = score.dropna()
            if not len(score):
                return []
            if self.kind == "event":
                #   이벤트형: 신호 발생 종목만. N 이 주어지면 점수 상위 N 으로 자른다.
                fired = set(s["code"]) if (s is not None and len(s)) else set()
                score = score[[c in fired for c in score.index]]
                if not len(score):
                    return []
            k = min(int(n or len(score)), len(score))
            return list(score.sort_values(ascending=False).head(k).index)
        return sel


def _ensure_cols(d: pd.DataFrame, cols: Dict[str, Any]) -> pd.DataFrame:
    """원천마다 있는 컬럼이 다르다. 없는 것은 결측으로 세워 둔다 — 추측값으로 채우지 않는다."""
    d = d.copy()
    for c, v in cols.items():
        if c not in d.columns:
            d[c] = v
    return d


def _pit_usable(dt: pd.Series) -> pd.Series:
    """공시 접수일 + 1영업일 (§4 공통규약)."""
    return as_ts_series(dt) + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS)


def _source_span(ev: pd.DataFrame, col: str = "rcept_dt") -> Tuple[pd.Timestamp, pd.Timestamp]:
    if ev is None or not len(ev):
        return pd.NaT, pd.NaT
    s = as_ts_series(ev[col]).dropna()
    return (s.min(), s.max()) if len(s) else (pd.NaT, pd.NaT)


def _obs_cells(codes_seen: Sequence[str], rebals: pd.DatetimeIndex,
               span: Tuple[pd.Timestamp, pd.Timestamp],
               univ_by_t: Dict[pd.Timestamp, List[str]]) -> pd.DataFrame:
    """소스가 '값을 낼 수 있었던' 셀. 종목이 소스 원장에 있고, 시점이 소스 구간 안일 때."""
    lo, hi = span
    seen = set(codes_seen)
    rows = []
    for t in rebals:
        if pd.notna(lo) and (t < lo or t > hi + pd.Timedelta(days=400)):
            continue
        for c in univ_by_t.get(t, []):
            if c in seen:
                rows.append((c, t))
    return pd.DataFrame(rows, columns=["code", "rebal"])


# ── F1. 자본거래·지배구조 이벤트 (하방 제거, 필터형) ────────────────────────────────────────
def build_F1(ev: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t, daily: pd.DataFrame,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F1), **ov}
    if ev is None or not len(ev):
        return FactorSignal("F1", variant, pd.DataFrame(columns=["code", "rebal"]),
                            pd.DataFrame(columns=["code", "rebal", "score"]), "filter",
                            "원천 없음")
    e = _ensure_cols(ev, {"is_private": np.nan, "refix": np.nan, "conv_price": np.nan,
                          "event": ""})
    e["usable"] = _pit_usable(e["rcept_dt"])
    hz = pd.Timedelta(days=int(round(p["horizon_m"] * 30.44)))

    keep = pd.Series(False, index=e.index)
    is_cbbw = e["event"].isin(["E1_CB", "E1_BW"])
    if p["e1_private_only"]:
        #   사모 구분이 결측이면 '사모로 간주'하지 않는다 — 추측 금지. 대신 그 사실을 남긴다.
        keep |= is_cbbw & (e["is_private"] == True)                             # noqa: E712
        n_unknown = int((is_cbbw & e["is_private"].isna()).sum())
        if n_unknown:
            LOG.info(f"[F1/{variant}] 사모 여부 미상인 CB/BW {n_unknown:,}건은 E1 에서 제외했습니다 "
                     f"(추측으로 사모 처리하지 않음).")
    else:
        keep |= is_cbbw
    keep |= e["event"] == "E2_3RD"
    keep |= e["event"] == "E3_OWNER"
    E = e[keep].copy()

    # E4 — 리픽싱 + 현재가가 최초 전환가 대비 임계 이하 (희석 예약 상태)
    e4 = e[is_cbbw & (e["refix"] == True) & e["conv_price"].notna()].copy()      # noqa: E712
    rows = []
    _pv = daily[daily["date"].isin(rebals)][["code", "date", "close"]].copy()
    _pv["code"] = _pv["code"].astype(str)
    px = _pv.pivot_table(index="date", columns="code", values="close", aggfunc="last")
    px.columns = px.columns.astype(str)
    for _, r in e4.iterrows():
        c = r["code"]
        if c not in px.columns:
            continue
        win = px.index[(px.index >= r["usable"]) & (px.index <= r["usable"] + hz)]
        if not len(win):
            continue
        cur = px.loc[win, c]
        hit = cur[cur <= float(r["conv_price"]) * (1.0 + p["e4_refix_drop"])]
        for t in hit.index:
            rows.append((c, t))
    e4_cells = pd.DataFrame(rows, columns=["code", "rebal"]).drop_duplicates()

    # 유효기간 안의 셀로 전개
    out = []
    for t in rebals:
        w = E[(E["usable"] <= t) & (E["usable"] > t - hz)]
        for c in set(w["code"]):
            out.append((c, t))
    sig = pd.DataFrame(out, columns=["code", "rebal"]).drop_duplicates()
    if len(e4_cells):
        sig = pd.concat([sig, e4_cells], ignore_index=True).drop_duplicates()
    sig["score"] = 1.0
    obs = _obs_cells(set(ev["code"]), rebals, _source_span(ev), univ_by_t)
    return FactorSignal("F1", variant, obs, sig, "filter",
                        f"E4 셀 {len(e4_cells):,} · 유효기간 {p['horizon_m']}M")


# ── F2. 내부자 순매수 (상방, 랭킹형) ────────────────────────────────────────────────────────
def build_F2(ins: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t, univ: pd.DataFrame,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F2), **ov}
    empty = FactorSignal("F2", variant, pd.DataFrame(columns=["code", "rebal"]),
                         pd.DataFrame(columns=["code", "rebal", "score"]), "rank", "원천 없음")
    if ins is None or not len(ins):
        return empty
    d = _ensure_cols(ins, {"reason": "", "net_amount": np.nan, "role": ""})
    d["usable"] = _pit_usable(d["rcept_dt"])
    rs = d["reason"].astype(str)
    #   장내매수만 채택. 스톡옵션·상속·증여·담보·무상증자·장외 등은 명시적으로 제외한다.
    inc = rs.str.contains("|".join(map(re.escape, p["reasons_include"])))
    exc = rs.str.contains("|".join(map(re.escape, p["reasons_exclude"])))
    d = d[~exc]
    if ov.get("ceo_only"):
        d = d[d["role"].astype(str).str.contains("대표이사|최대주주")]
    #   순매수 = 장내매수 − 장내매도. 매도 건은 부호가 이미 음수로 들어온다.
    d["signed"] = pd.to_numeric(d["net_amount"], errors="coerce")
    d.loc[inc & (d["signed"] < 0), "signed"] = d.loc[inc & (d["signed"] < 0), "signed"].abs()
    d = d.dropna(subset=["signed", "usable", "code"])
    if not len(d):
        return empty

    lb = pd.Timedelta(days=int(round(p["lookback_m"] * 30.44)))
    denom_col = "market_cap" if p["rank_var"] == "net_buy_over_mktcap" else "adv20"
    den = univ.set_index(["rebal", "code"])[denom_col] if denom_col in univ.columns else None
    rows = []
    for t in rebals:
        w = d[(d["usable"] <= t) & (d["usable"] > t - lb)]
        if not len(w):
            continue
        net = w.groupby("code", observed=True)["signed"].sum()
        net = net[net > 0]
        if not len(net):
            continue
        if den is not None:
            try:
                dv = den.loc[t].reindex(net.index)
            except KeyError:
                dv = pd.Series(np.nan, index=net.index)
            sc = net / dv.replace(0, np.nan)
        else:
            sc = net
        sc = sc.replace([np.inf, -np.inf], np.nan).dropna()
        for c, v in sc.items():
            rows.append((c, t, float(v)))
    sig = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    obs = _obs_cells(set(ins["code"]), rebals, _source_span(ins), univ_by_t)
    return FactorSignal("F2", variant, obs, sig, "rank",
                        f"룩백 {p['lookback_m']}M · 랭킹변수 {p['rank_var']}")


# ── F3. 유동성 개선 (상방, 랭킹형) ──────────────────────────────────────────────────────────
def build_F3(daily: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t,
             variant: str, ov: dict) -> FactorSignal:
    p = {**dict(SPEC_F3), **ov}
    w = int(p["illiq_window_d"])
    lag = int(p["delta_lag_d"])
    d = daily.sort_values(["code", "date"]).copy()
    g = d.groupby("code", observed=True)
    if ov.get("amount_only"):
        base = g["amount"].transform(lambda s: s.rolling(w, min_periods=max(10, w // 3)).mean())
        d["ILLIQ"] = 1.0 / np.maximum(base, 1.0)          # 거래대금이 클수록 비유동성 낮음
    else:
        d["_x"] = np.abs(d["ret1d"]) / np.maximum(d["amount"], 1.0)
        d["ILLIQ"] = g["_x"].transform(lambda s: s.rolling(w, min_periods=max(10, w // 3)).mean())
    d["logI"] = np.log(np.maximum(d["ILLIQ"], 1e-30))
    d["dlogI"] = d["logI"] - g["logI"].shift(lag)
    d["score"] = d["logI"] if ov.get("use_level") else -d["dlogI"]
    if ov.get("use_level"):
        d["score"] = -d["logI"]                            # 수준: 비유동성이 낮을수록 높은 점수
    snap = d[d["date"].isin(rebals)][["code", "date", "score", "logI", "dlogI"]].copy()
    snap["code"] = snap["code"].astype(str)
    snap = snap.rename(columns={"date": "rebal"})
    sig = snap.dropna(subset=["score"])[["code", "rebal", "score"]]
    obs = snap.dropna(subset=["logI"])[["code", "rebal"]]
    return FactorSignal("F3", variant, obs, sig, "rank",
                        f"윈도 {w}d · 변화 lag {lag}d" + (" · 수준 대조군" if ov.get("use_level") else ""))


def f3_redundancy(daily: pd.DataFrame, sig: pd.DataFrame, rebals: pd.DatetimeIndex) -> dict:
    """§4 F3 중복성 검사 — 12개월 모멘텀·1개월 반전과의 상관. |ρ|>0.5 면 기각."""
    d = daily.sort_values(["code", "date"]).copy()
    d["code"] = d["code"].astype(str)
    px = d.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    px = px.reindex(pd.DatetimeIndex(sorted(set(px.index) | set(rebals)))).ffill().reindex(rebals)
    per = 12 if REBAL_FREQ.upper().startswith("M") else 52
    mom = px / px.shift(per) - 1.0
    rev = px / px.shift(max(1, per // 12)) - 1.0
    S = sig.pivot_table(index="rebal", columns="code", values="score", aggfunc="last")
    rhos_m, rhos_r = [], []
    for t in S.index:
        if t not in mom.index:
            continue
        a = S.loc[t].dropna()
        for src, box in ((mom, rhos_m), (rev, rhos_r)):
            b = src.loc[t].reindex(a.index).dropna()
            if len(b) >= 20:
                box.append(float(pd.Series(a.reindex(b.index)).corr(b, method="spearman")))
    out = dict(rho_mom=float(np.nanmean(rhos_m)) if rhos_m else np.nan,
               rho_rev=float(np.nanmean(rhos_r)) if rhos_r else np.nan)
    out["reject"] = bool(max(abs(out["rho_mom"] or 0), abs(out["rho_rev"] or 0))
                         > SPEC_F3["redundancy_rho"])
    LOG.table([["12개월 모멘텀", f"{out['rho_mom']:+.3f}"],
               ["1개월 반전", f"{out['rho_rev']:+.3f}"],
               ["기각 기준", f"|ρ| > {SPEC_F3['redundancy_rho']}"],
               ["판정", "★기각" if out["reject"] else "통과"]],
              ["대조 신호", "평균 Spearman ρ"], ["l", "r"],
              title="[F3] 중복성 검사 — EW 리밸런싱 자체가 반전 베팅이므로 필수")
    return out


# ── F4. 수주·공급계약 (상방, 이벤트형) ──────────────────────────────────────────────────────
def build_F4(con: pd.DataFrame, fin: pd.DataFrame, rebals: pd.DatetimeIndex, univ_by_t,
             variant: str, ov: dict, track_cancel: bool = True) -> FactorSignal:
    p = {**dict(SPEC_F4), **ov}
    empty = FactorSignal("F4", variant, pd.DataFrame(columns=["code", "rebal"]),
                         pd.DataFrame(columns=["code", "rebal", "score"]), "event", "원천 없음")
    if con is None or not len(con):
        return empty
    d = _ensure_cols(con, {"ratio_sales": np.nan, "contract_amt": np.nan,
                           "counterparty": "", "is_cancel": False})
    d["usable"] = _pit_usable(d["rcept_dt"])
    if ov.get("counterparty_major"):
        d = d[d["counterparty"].astype(str).str.contains("공공|국가|지자체|공사|공단|대기업|그룹")]
    #   비율은 공시에 이미 들어 있다(계약금액/직전 매출액). 없으면 재무로 직접 만든다.
    need = d["ratio_sales"].isna() & d["contract_amt"].notna()
    if need.any() and fin is not None and len(fin):
        f = fin.dropna(subset=["revenue"]).sort_values("knowledge_date")
        f = f.assign(usable_from=f["knowledge_date"] + pd.tseries.offsets.BDay(SPEC_PIT_LAG_BDAYS))
        tmp = pd.merge_asof(d[need].sort_values("usable"), f[["code", "usable_from", "revenue"]],
                            left_on="usable", right_on="usable_from", by="code", direction="backward")
        d.loc[need, "ratio_sales"] = (tmp["contract_amt"] / tmp["revenue"].replace(0, np.nan)).values
    d["ratio_sales"] = pd.to_numeric(d["ratio_sales"], errors="coerce")
    #   공시가 %로 들어오는 경우(예: 25.0 = 25%)를 스케일 감지로 교정한다.
    if d["ratio_sales"].dropna().median() > 3.0:
        LOG.info("[F4] 매출액대비 비율이 백분율(%)로 보입니다 — 100 으로 나눠 비율로 환산했습니다.")
        d["ratio_sales"] = d["ratio_sales"] / 100.0

    hz = pd.Timedelta(days=int(round(p["horizon_m"] * 30.44)))
    live = d[~d["is_cancel"].fillna(False)] if track_cancel else d
    cancels = d[d["is_cancel"].fillna(False)][["code", "usable"]] if track_cancel else \
        pd.DataFrame(columns=["code", "usable"])
    rows = []
    for t in rebals:
        w = live[(live["usable"] <= t) & (live["usable"] > t - hz)]
        if not len(w):
            continue
        if track_cancel and len(cancels):
            #   해지 공시 시점부터 신호 소멸 — 그 종목의 해당 구간 계약을 통째로 무효화한다.
            cc = cancels[(cancels["usable"] <= t) & (cancels["usable"] > t - hz)]["code"]
            w = w[~w["code"].isin(set(cc))]
        agg = w.groupby("code", observed=True)["ratio_sales"].sum()
        agg = agg[agg >= float(p["ratio_threshold"])]
        for c, v in agg.items():
            rows.append((c, t, float(v)))
    sig = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    obs = _obs_cells(set(con["code"]), rebals, _source_span(con), univ_by_t)
    return FactorSignal("F4", variant, obs, sig, "event",
                        f"임계 {p['ratio_threshold']:.2f} · 유효 {p['horizon_m']}M"
                        + ("" if track_cancel else " · ★해지 미처리(대조용)"))

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §6.3 판정 게이트 G1~G7 + §6.2 다중검정(DSR/PBO)                                          ║
# ║                                                                                          ║
# ║  전부 통과해야 '유효'다. 하나라도 실패하면 실패로 기록하고, 통과시키기 위해 명세를          ║
# ║  고치지 않는다(§7 MASTER_SCORECARD 필수 포함 사항).                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

from math import erf, sqrt as _sqrt


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / _sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """역정규 (Acklam 근사). scipy 의존을 피한다 — 이 코드는 어디서든 돌아야 한다."""
    p = min(max(float(p), 1e-12), 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = _sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = _sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe(ret: pd.Series, n_trials: int, ppy: float) -> dict:
    """Bailey & López de Prado (2014). 시행수는 반드시 §6.2 의 전체값(120)을 쓴다."""
    r = pd.Series(ret).dropna().to_numpy(dtype=float)
    T = len(r)
    if T < 12 or r.std(ddof=1) == 0:
        return dict(sr=np.nan, sr0=np.nan, dsr=np.nan, excess=np.nan, T=T)
    sr = float(r.mean() / r.std(ddof=1))                       # 주기 단위 SR
    g3 = float(pd.Series(r).skew())
    g4 = float(pd.Series(r).kurt() + 3.0)
    #   시행 N개 중 최대 SR 의 기대값 (귀무: 진짜 SR=0)
    euler = 0.5772156649
    e1 = _norm_ppf(1 - 1.0 / n_trials)
    e2 = _norm_ppf(1 - 1.0 / (n_trials * math.e))
    var_sr = 1.0 / _sqrt(max(T - 1, 1))                        # 귀무 하에서의 SR 표준편차 근사
    sr0 = var_sr * ((1 - euler) * e1 + euler * e2)
    denom = _sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    z = (sr - sr0) * _sqrt(max(T - 1, 1)) / denom
    return dict(sr=sr * _sqrt(ppy), sr0=sr0 * _sqrt(ppy), dsr=_norm_cdf(z),
                excess=float(sr - sr0), T=T)


def pbo_cscv(R: pd.DataFrame, n_blocks: int = 16) -> dict:
    """CSCV — 변형(variant) 들 사이에서 IS 최우수가 OOS 중앙 아래로 떨어질 확률.

    R: index=시점, columns=변형. 팩터 하나의 격자 전체(5×3×2=30)를 넣는다.
    """
    R = R.dropna(how="all").fillna(0.0)
    T, K = R.shape
    if K < 2 or T < n_blocks * 3:
        return dict(pbo=np.nan, n_comb=0, K=K, T=T)
    n_blocks = int(n_blocks) - (int(n_blocks) % 2)
    edges = np.array_split(np.arange(T), n_blocks)
    X = R.to_numpy(dtype=float)
    bs = np.array([X[e].sum(axis=0) for e in edges])            # (B, K)
    bq = np.array([(X[e] ** 2).sum(axis=0) for e in edges])
    bn = np.array([len(e) for e in edges], dtype=float)

    from itertools import combinations
    idx = list(range(n_blocks))
    combos = list(combinations(idx, n_blocks // 2))
    if len(combos) > 20000:
        rng = np.random.default_rng(SEED)
        combos = [combos[i] for i in rng.choice(len(combos), 20000, replace=False)]

    def _sharpe(sel):
        s, q, n = bs[list(sel)].sum(0), bq[list(sel)].sum(0), bn[list(sel)].sum()
        mu = s / n
        var = np.maximum(q / n - mu ** 2, 1e-18)
        return mu / np.sqrt(var)

    logits = []
    for cmb in combos:
        oos = tuple(i for i in idx if i not in cmb)
        s_is, s_oos = _sharpe(cmb), _sharpe(oos)
        best = int(np.argmax(s_is))
        rank = float((s_oos <= s_oos[best]).sum()) / K          # 상대 순위 (1=최고)
        w = min(max(rank, 1.0 / (K + 1)), 1 - 1.0 / (K + 1))
        logits.append(math.log(w / (1 - w)))
    lg = np.array(logits)
    return dict(pbo=float((lg <= 0).mean()), n_comb=len(combos), K=K, T=T,
                logit_median=float(np.median(lg)))


# ── 게이트 판정 ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    gate: str
    passed: Optional[bool]
    value: str
    criterion: str
    note: str = ""


def excess_cagr(res: BTResult, base: BTResult, ppy: float) -> float:
    return res.stats(ppy)["cagr"] - base.stats(ppy)["cagr"]


def yearly_excess(res: BTResult, base: BTResult) -> pd.Series:
    a, b = res.yearly(), base.yearly()
    return (a - b.reindex(a.index)).dropna()


def gate_G1(res: BTResult, null: dict, ppy: float) -> GateResult:
    if null is None or not len(null.get("cagr", [])):
        return GateResult("G1", None, "—", "B4 무작위 분포 상위 5% 밖", "귀무분포 없음")
    c = res.stats(ppy)["cagr"]
    pct = float((null["cagr"] < c).mean())
    return GateResult("G1", bool(c > null["p95"]), f"{c:.2%} (분위 {pct:.1%})",
                      f"> B4 p95 = {null['p95']:.2%}")


def gate_G2(res: BTResult, b2: BTResult, ppy: float) -> GateResult:
    x = excess_cagr(res, b2, ppy)
    return GateResult("G2", bool(x >= SPEC_GATE["g2_excess_cagr"]), f"{x:+.2%}p",
                      f"≥ +{SPEC_GATE['g2_excess_cagr']:.1%}p (AUM 1억)")


def gate_G3(res: BTResult, b2: BTResult) -> GateResult:
    ye = yearly_excess(res, b2)
    if not len(ye):
        return GateResult("G3", None, "—", "연도별 초과 중앙값>0 & 최고2년 제외 후 >0")
    med = float(ye.median())
    k = SPEC_GATE["g3_drop_best_years"]
    trimmed = ye.sort_values(ascending=False).iloc[k:] if len(ye) > k else pd.Series(dtype=float)
    tm = float(trimmed.mean()) if len(trimmed) else np.nan
    ok = bool(med > 0 and np.isfinite(tm) and tm > 0)
    return GateResult("G3", ok, f"중앙 {med:+.2%}p · 최고{k}년제외 평균 {tm:+.2%}p",
                      "중앙값>0 이고 최고 2년 제외 후에도 >0")


def gate_G4(is_x: float, oos_x: float) -> GateResult:
    if not np.isfinite(oos_x) or not np.isfinite(is_x):
        return GateResult("G4", None, "—", f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}",
                          "OOS 미개봉")
    if is_x <= 0:
        return GateResult("G4", False, f"IS {is_x:+.2%}p", "IS 초과수익이 없어 판정 불가 → 실패")
    return GateResult("G4", bool(oos_x >= is_x * SPEC_GATE["g4_oos_ratio"]),
                      f"IS {is_x:+.2%}p → OOS {oos_x:+.2%}p ({oos_x/is_x:.0%})",
                      f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}")


def gate_G5(dsr: dict, pbo: dict) -> GateResult:
    d, p = dsr.get("dsr", np.nan), pbo.get("pbo", np.nan)
    if not np.isfinite(d) or not np.isfinite(p):
        return GateResult("G5", None, "—", "DSR>0 · PBO<0.5", "표본 부족")
    ok = bool(d > SPEC_GATE["g5_dsr_min"] and p < SPEC_GATE["g5_pbo_max"])
    strict = bool(dsr.get("excess", -1) > 0 and p < SPEC_GATE["g5_pbo_max"])
    return GateResult("G5", ok, f"DSR {d:.3f} · PBO {p:.3f} · SR−SR₀ {dsr.get('excess', np.nan):+.4f}",
                      f"DSR > {SPEC_GATE['g5_dsr_min']} · PBO < {SPEC_GATE['g5_pbo_max']}",
                      f"엄격판정(SR>SR₀ 기준) = {'통과' if strict else '실패'}")


def gate_G6(quint: Dict[int, BTResult], kind: str, ppy: float) -> GateResult:
    if kind == "filter":
        return GateResult("G6", None, "—", "5분위 단조 감소 (랭킹형 한정)", "필터형 — 해당 없음")
    if not quint or len(quint) < 5:
        return GateResult("G6", None, "—", "5분위 단조 감소", "분위 구성 실패")
    c = [quint[q].stats(ppy)["cagr"] for q in sorted(quint, reverse=True)]   # Q5→Q1
    mono = all(c[i] >= c[i + 1] for i in range(len(c) - 1))
    return GateResult("G6", bool(mono), " → ".join(f"{x:.1%}" for x in c),
                      "상위→하위 단조 감소")


def gate_G7(p1: float, p2: float, p3: float, base_x: float) -> GateResult:
    """P1·P2 는 초과수익이 소멸해야 하고, P3 는 유지되어야 한다."""
    tol = max(0.3 * abs(base_x), 0.005)
    r1 = np.isfinite(p1) and abs(p1) < tol
    r2 = np.isfinite(p2) and abs(p2) < tol
    r3 = np.isfinite(p3) and p3 > 0
    ok = bool(r1 and r2 and r3)
    return GateResult("G7", ok,
                      f"P1 {p1:+.2%}p{'✓' if r1 else '✗'} · P2 {p2:+.2%}p{'✓' if r2 else '✗'} · "
                      f"P3 {p3:+.2%}p{'✓' if r3 else '✗'}",
                      f"P1·P2 소멸(|초과|<{tol:.2%}p) & P3 유지(>0)")


# ── 플라시보 생성기 ─────────────────────────────────────────────────────────────────────────
def placebo_shift(fs: FactorSignal, rebals: pd.DatetimeIndex) -> FactorSignal:
    """P1 — 신호 발생일을 −60영업일 시프트. 진짜 신호라면 초과수익이 사라져야 한다."""
    if not len(fs.sig):
        return fs
    s = fs.sig.copy()
    shifted = pd.to_datetime(s["rebal"]) + pd.tseries.offsets.BDay(SPEC_GATE["g7_placebo_shift_bdays"])
    grid = pd.DatetimeIndex(rebals)
    pos = grid.searchsorted(shifted.to_numpy(), side="left")
    pos = np.clip(pos, 0, len(grid) - 1)
    s["rebal"] = grid[pos]
    return FactorSignal(fs.factor, fs.variant + "|P1", fs.obs, s.drop_duplicates(["code", "rebal"]),
                        fs.kind, "P1 −60영업일 시프트")


def placebo_shuffle(fs: FactorSignal, univ_by_t: Dict[pd.Timestamp, List[str]]) -> FactorSignal:
    """P2 — 신호 라벨을 종목 간 무작위 셔플. 발생 빈도(시점별 신호 종목수)는 보존한다."""
    if not len(fs.sig):
        return fs
    rng = np.random.default_rng(SEED + 7)
    rows = []
    for t, g in fs.sig.groupby("rebal", observed=True):
        pool = list(univ_by_t.get(t, []))
        if not pool:
            continue
        k = min(len(g), len(pool))
        pick = rng.choice(len(pool), k, replace=False)
        sc = g["score"].to_numpy()[:k]
        for j, i in enumerate(pick):
            rows.append((pool[i], t, float(sc[j])))
    s = pd.DataFrame(rows, columns=["code", "rebal", "score"])
    return FactorSignal(fs.factor, fs.variant + "|P2", fs.obs, s, fs.kind, "P2 라벨 셔플")


def placebo_matched(fs: FactorSignal, univ: pd.DataFrame, sec: pd.DataFrame) -> FactorSignal:
    """P3 — 신호 종목과 시총·업종·거래대금이 매칭된 대조군. 이 대조군 대비로도 이겨야 한다."""
    if not len(fs.sig):
        return fs
    ind = sec.drop_duplicates("code").set_index("code").get("industry")
    U = univ[univ["u250"]][["rebal", "code", "market_cap", "adv20"]].copy()
    U["industry"] = U["code"].map(ind) if ind is not None else ""
    rng = np.random.default_rng(SEED + 13)
    rows = []
    for t, g in fs.sig.groupby("rebal", observed=True):
        pool = U[U["rebal"] == t]
        if not len(pool):
            continue
        tgt = pool[pool["code"].isin(set(g["code"]))]
        cand = pool[~pool["code"].isin(set(g["code"]))]
        if not len(tgt) or not len(cand):
            continue
        for _, r in tgt.iterrows():
            c2 = cand[cand["industry"] == r["industry"]] if r["industry"] else cand
            if not len(c2):
                c2 = cand
            #   시총·거래대금 로그거리 최소 종목을 짝지운다 (동률은 난수로)
            d = (np.log1p(c2["market_cap"]) - np.log1p(r["market_cap"])).abs() + \
                (np.log1p(c2["adv20"]) - np.log1p(r["adv20"])).abs()
            d = d + rng.random(len(d)) * 1e-6
            rows.append((c2.loc[d.idxmin(), "code"], t, 1.0))
    s = pd.DataFrame(rows, columns=["code", "rebal", "score"]).drop_duplicates(["code", "rebal"])
    return FactorSignal(fs.factor, fs.variant + "|P3", fs.obs, s, fs.kind, "P3 매칭 대조군")

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §7 산출물                                                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

FACTOR_DIR = {"F1": "F1_capital_events", "F2": "F2_insider",
              "F3": "F3_liquidity", "F4": "F4_contracts"}


def _out(*parts) -> str:
    p = os.path.join(OUTPUT_DIR, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def write_xlsx(path: str, sheets: Dict[str, pd.DataFrame]) -> str:
    """엑셀로 쓰되, 엔진이 없으면 조용히 실패하지 않고 CSV 로 떨어뜨리고 그 사실을 알린다."""
    sheets = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame(v))
              for k, v in sheets.items() if v is not None}
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            for name, df in sheets.items():
                (df if len(df) else pd.DataFrame({"(비어 있음)": []})).to_excel(
                    w, sheet_name=str(name)[:31], index=False)
        LOG.ok(f"산출물 저장 — {os.path.relpath(path, OUTPUT_DIR)} ({len(sheets)}시트)")
        return path
    except Exception as e:                                              # noqa
        base = os.path.splitext(path)[0]
        os.makedirs(base, exist_ok=True)
        for name, df in sheets.items():
            df.to_csv(os.path.join(base, f"{name}.csv"), index=False, encoding="utf-8-sig")
        LOG.warn(f"엑셀 저장 실패({type(e).__name__}) — CSV 로 저장했습니다: "
                 f"{os.path.relpath(base, OUTPUT_DIR)}/  (openpyxl 설치 시 xlsx 로 나옵니다)")
        return base


def write_md(path: str, text: str) -> str:
    atomic_write_text(path, text)
    LOG.ok(f"산출물 저장 — {os.path.relpath(path, OUTPUT_DIR)}")
    return path


def perf_row(name: str, r: BTResult, ppy: float, base: Optional[BTResult] = None) -> dict:
    s = r.stats(ppy)
    row = {"전략": name, "CAGR": s["cagr"], "연환산변동성": s["vol"], "MDD": s["mdd"],
           "Sharpe": s["sharpe"], "연회전율": s["turnover"], "누적실현거래비용": s["cost"],
           "구간수": s["n"], "평균보유종목": float(r.n_holdings.mean()) if len(r.n_holdings) else np.nan}
    if base is not None:
        row["초과CAGR(vs B2)"] = s["cagr"] - base.stats(ppy)["cagr"]
    return row


def yearly_table(results: Dict[str, BTResult]) -> pd.DataFrame:
    cols = {}
    for k, r in results.items():
        cols[k] = r.yearly()
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).reset_index().rename(columns={"index": "연도"})


def phase0_report(covs: Dict[str, Coverage], b_cov: Dict[str, BTResult],
                  ppy: float, b2: Optional[BTResult]) -> str:
    summ = pd.DataFrame([{
        "팩터": c.factor, "팩터명": FACTOR_META[c.factor]["name"],
        "cov_stock": c.cov_stock, "cov_stock_rebal": c.cov_stock_rebal,
        "cov_universe_rebal(중앙값)": c.median_cov, "signal_rate": c.signal_rate,
        "판정": c.verdict,
        "조치": {"PASS": "정상 진행", "PARTIAL": "부분 커버 팩터로 표기하고 진행 (미커버 중립)",
                 "HOLD": "백테스트 보류 — §6.4 조기 중단"}[c.verdict],
    } for c in covs.values()])
    sheets = {"요약": summ}
    for f, c in covs.items():
        sheets[f"{f}_cov_ts"] = c.cov_universe_rebal.rename("U250내_관측종목수").reset_index() \
            .rename(columns={"index": "rebal"})
        sheets[f"{f}_cov_trend"] = c.cov_trend.rename("중앙값").reset_index() \
            .rename(columns={"index": "연도"})
        if c.bias is not None and len(c.bias):
            sheets[f"{f}_bias"] = c.bias
    if b_cov:
        rows = [perf_row(f"B_cov[{f}] 커버종목만 EW 순수익", r, ppy, b2) for f, r in b_cov.items()]
        sheets["B_cov"] = pd.DataFrame(rows)
    return write_xlsx(_out("phase0_coverage_report.xlsx"), sheets)


def baseline_report(base: Dict[str, BTResult], nulls: Dict[int, dict], ppy: float) -> str:
    rows = [perf_row(r.name, r, ppy, base.get("B2")) for r in base.values()]
    nullrows = []
    for n, d in nulls.items():
        if not len(d.get("cagr", [])):
            continue
        c = d["cagr"]
        nullrows.append({"N": n, "시행": d["sims"], "중앙 CAGR": float(np.median(c)),
                         "p05": float(np.quantile(c, .05)), "p95": d["p95"],
                         "p99": float(np.quantile(c, .99)),
                         "회전율정합": d.get("matched", False)})
    return write_xlsx(_out("baseline_B1_B4.xlsx"),
                      {"성과요약": pd.DataFrame(rows),
                       "연도별수익률": yearly_table(base),
                       "B4_무작위분포": pd.DataFrame(nullrows)})


def gate_scorecard_md(factor: str, gates: List[GateResult], head: dict) -> str:
    L = [f"# {factor} 게이트 스코어카드 — {FACTOR_META[factor]['name']}", "",
         f"> {FACTOR_META[factor]['hyp']}", "",
         f"- 주 명세: N={SPEC_N_PRIMARY}, 미커버 처리=neutral, AUM {SPEC_GATE['g2_aum_krw']:,}원",
         f"- 사전등록 해시: `{spec_sha256()[:16]}` · 명세 v{SPEC_VERSION}", ""]
    for k, v in head.items():
        L.append(f"- {k}: {v}")
    L += ["", "| # | 게이트 | 판정 | 값 | 기준 | 비고 |", "|---|---|---|---|---|---|"]
    for g in gates:
        mark = "✅ 통과" if g.passed is True else ("❌ 실패" if g.passed is False else "— 판정불가")
        L.append(f"| {g.gate} | {_GATE_NAME[g.gate]} | {mark} | {g.value} | {g.criterion} | {g.note} |")
    npass = sum(1 for g in gates if g.passed is True)
    nfail = sum(1 for g in gates if g.passed is False)
    L += ["", f"**종합: {npass}통과 / {nfail}실패 / "
              f"{sum(1 for g in gates if g.passed is None)}판정불가**",
          "", "전부 통과해야 '유효'다(§6.3). 통과시키기 위해 명세를 수정하지 않는다(§8-3, §8-5)."]
    return "\n".join(L)


_GATE_NAME = {"G1": "무작위 대비", "G2": "순수익 초과", "G3": "연도 안정성", "G4": "OOS 일관성",
              "G5": "다중검정", "G6": "단조성", "G7": "플라시보"}


def master_scorecard(all_gates: Dict[str, List[GateResult]], excess: Dict[str, dict],
                     covs: Dict[str, Coverage], capacity: pd.DataFrame,
                     amendments: List[str]) -> str:
    L = ["# MASTER SCORECARD — U250 대체데이터 팩터 독립 검정", "",
         f"- 명세 v{SPEC_VERSION} · 사전등록 해시 `{spec_sha256()}`",
         f"- 실행 {_dt.datetime.now():%Y-%m-%d %H:%M} · 유니버스 U{SPEC_UNIV['main_n']} EW · "
         f"리밸 {REBAL_FREQ} · 시행수(다중검정) {SPEC_TRIALS_TOTAL}",
         f"- 캐시 재활용: {len(LAKE.items):,}개 파일 (스캔 {LAKE.scanned:,}개 중)", "",
         "## 1. 4팩터 × G1~G7 격자", "",
         "| 팩터 | 커버리지 | G1 무작위 | G2 초과 | G3 안정 | G4 OOS | G5 다중검정 | G6 단조 | G7 플라시보 | 유효 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    any_pass = False
    for f in ("F1", "F2", "F3", "F4"):
        gs = {g.gate: g for g in all_gates.get(f, [])}
        cells = []
        for k in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            g = gs.get(k)
            cells.append("—" if g is None or g.passed is None else ("✅" if g.passed else "❌"))
        valid = all(c == "✅" for c in cells if c != "—") and any(c == "✅" for c in cells)
        # G6 가 '해당 없음(필터형)'인 경우를 제외하고 전부 통과해야 유효
        req = [gs.get(k) for k in ("G1", "G2", "G3", "G4", "G5", "G7")]
        valid = all(g is not None and g.passed is True for g in req) and \
            (gs.get("G6") is None or gs["G6"].passed is not False)
        any_pass |= valid
        cv = covs.get(f)
        L.append(f"| {f} {FACTOR_META[f]['name']} | {cv.verdict if cv else '—'}"
                 f"({cv.median_cov:.0f}종목) | " + " | ".join(cells) +
                 f" | {'**유효**' if valid else '무효'} |")
    L += ["", "## 2. B2 대비 순수익 초과 CAGR", "",
          "| 팩터 | AUM 1억 (IS) | AUM 1억 (OOS) | 동적 AUM (IS) | B_cov 대비 (IS) |",
          "|---|---|---|---|---|"]
    for f in ("F1", "F2", "F3", "F4"):
        x = excess.get(f, {})
        def _f(k):
            v = x.get(k)
            return f"{v:+.2%}p" if isinstance(v, float) and np.isfinite(v) else "—"
        L.append(f"| {f} | {_f('is')} | {_f('oos')} | {_f('dyn')} | {_f('bcov')} |")

    L += ["", "## 3. 판정", ""]
    if any_pass:
        L.append("일부 팩터가 G1~G7 을 통과했다. 위 격자와 §7 팩터별 산출물을 함께 볼 것.")
    else:
        L += ["> ### ★ 전 팩터가 G1~G7 을 통과하지 못했다.",
              ">",
              "> 명세서 §7 의 요구대로 이 사실을 명시적으로 기록한다. "
              "통과 팩터를 만들기 위해 명세를 수정하지 않았다.",
              "> 민감도 격자는 팩터당 4개로 상한이 걸려 있고(코드가 강제), "
              "임계값·기간·N값은 1차 결과를 본 뒤 조정하지 않았다.", ""]
    if len(capacity):
        cols = [str(a) for a in SPEC_AUM_LADDER] + ["dynamic"]
        hdr = [f"{a/1e8:.0f}억" if a >= 1e8 else f"{a/1e7:.0f}천만" for a in SPEC_AUM_LADDER] + ["동적 AUM"]
        L += ["", "## 4. 용량 (AUM별 순수익 CAGR 감쇠)", "",
              "| 전략 | " + " | ".join(hdr) + " |",
              "|---|" + "---|" * len(hdr)]
        for _, r in capacity.iterrows():
            cells = []
            for c in cols:
                v = r.get(c, np.nan)
                cells.append(f"{v:.2%}" if isinstance(v, (int, float)) and np.isfinite(v) else "—")
            L.append(f"| {r['전략']} | " + " | ".join(cells) + " |")
    if amendments:
        L += ["", "## 5. 명세 개정 요청 (코드를 고치지 않고 기록만 한다 — §8)", ""]
        L += [f"{i+1}. {a}" for i, a in enumerate(amendments)]
    L += ["", "---", "", "### 실행 기록", "",
          "```", json.dumps(RUNLOG, ensure_ascii=False, indent=2, default=str)[:6000], "```"]
    return "\n".join(L)

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  §9 실행 순서 — Step 0 ~ Step 9                                                           ║
# ║  각 Step 완료 시 중간 산출물을 저장하고, 다음 Step 은 이전 결과를 보지 않은 상태에서        ║
# ║  명세대로만 실행한다.                                                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

AMENDMENTS: List[str] = []
FWD_GLOBAL: Optional[pd.DataFrame] = None


def _prep_dirs():
    global CACHE_DIR, LOG_DIR, OUTPUT_DIR
    base = os.path.expanduser(BASE_DIR)
    if not _can_write(base):
        base = os.path.abspath("./u250_factor_test")
        LOG.warn(f"BASE_DIR({BASE_DIR}) 에 쓸 수 없어 {base} 로 대체합니다 "
                 f"(윈도우 경로를 다른 OS 에서 실행한 경우 정상입니다).")
    CACHE_DIR = CACHE_DIR or os.path.join(base, "cache")
    LOG_DIR = LOG_DIR or os.path.join(base, "logs")
    OUTPUT_DIR = OUTPUT_DIR or os.path.join(base, "outputs")
    for p in (base, CACHE_DIR, LOG_DIR, OUTPUT_DIR):
        os.makedirs(p, exist_ok=True)
    LOG.info(f"산출물 루트 {base}")


def _can_write(p: str) -> bool:
    try:
        os.makedirs(p, exist_ok=True)
        t = os.path.join(p, ".wtest")
        open(t, "w").close()
        os.remove(t)
        return True
    except Exception:
        return False


def _load_all() -> dict:
    """캐시에서 전부 꺼낸다. 하나라도 없으면 그 사실을 남기고 SMOKE 합성으로 대체한다."""
    if RUN_MODE == "SMOKE":
        LOG.warn("RUN_MODE=SMOKE — 합성데이터로 계산경로만 증명합니다. "
                 "이 결과는 알파 판정이 아닙니다(신호를 수익률과 독립으로 뿌렸으므로 "
                 "전 팩터 G1~G7 미달이 정상입니다).")
        return synth_dataset()
    try:
        px = load_price()
        sec = load_sec_master()
        fin = load_financials()
    except StageFailure as e:
        LOG.error(str(e))
        LOG.warn("실데이터를 조립하지 못해 SMOKE 합성으로 전환합니다 — "
                 "산출물 구조는 동일하나 수치는 무의미합니다.")
        RUNLOG["fallback_to_synth"] = str(e)
        return synth_dataset()
    return {"price": px, "sec": sec, "fin": fin, "cap_events": None,
            "insider": None, "contracts": None}


def run_all():
    t0 = time.time()
    LOG.banner(STRATEGY_NAME, f"명세 v{SPEC_VERSION} · 사전등록 해시 {spec_sha256()[:16]} · "
                              f"빌드 {BUILD_VERSION}")
    RUNLOG.update(spec_sha256=spec_sha256(), spec_version=SPEC_VERSION, run_mode=RUN_MODE,
                  rebal_freq=REBAL_FREQ, collect_policy=COLLECT_POLICY, seed=SEED,
                  started=_dt.datetime.now().isoformat(timespec="seconds"))

    # ── Step 0. 캐시 하베스트 ─────────────────────────────────────────────────────────
    _prep_dirs()
    global VAULT
    VAULT = Vault(*_mount_drive())
    LOG.info(f"캐시 볼트 {VAULT.root} [{VAULT.mode}]")
    if RUN_MODE != "SMOKE":
        LAKE.harvest()
    gate_crosscheck()
    if RUN_MODE == "CACHED":
        globals()["COLLECT_POLICY"] = "NEVER"
    verify_dart_endpoints()

    D = _load_all()
    with PIPE.stage("L1.PANEL", "패널 조립", "L1", budget_s=900):
        daily = build_daily_panel(D["price"])
        if PANEL_START:
            daily = daily[daily["date"] >= as_ts(PANEL_START)]
        if PANEL_END:
            daily = daily[daily["date"] <= as_ts(PANEL_END)]
        sec, fin = D["sec"], D["fin"]
        rebals = rebalance_dates(pd.DatetimeIndex(daily["date"].unique()))
        SEAL.set_boundary(rebals)
        elig = build_eligibility(daily, sec, fin, rebals)
        univ = build_universe(elig)
        RUNLOG["panel"] = dict(codes=int(daily["code"].nunique()), rows=int(len(daily)),
                               start=str(daily["date"].min().date()),
                               end=str(daily["date"].max().date()),
                               rebals=int(len(rebals)))

    global FWD_GLOBAL
    with PIPE.stage("L2.COST", "비용 모형 · 수익률 행렬", "L2", budget_s=900):
        FWD, DEL = build_forward_returns(daily, rebals, sec)
        FWD_GLOBAL = FWD
        cs = corwin_schultz_spread(daily)
        spread_map = ({t: g.set_index("code")["spread_cs"]
                       for t, g in cs[cs["date"].isin(rebals)].groupby("date", observed=True)}
                      if len(cs) else {})
        adv_map = {t: g.set_index("code")["adv20_mean"]
                   for t, g in univ.groupby("rebal", observed=True)}
        qmap = {}
        for t, g in univ.groupby("rebal", observed=True):
            try:
                q = pd.qcut(g["market_cap"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
                qmap[t] = pd.Series(q.astype(int).values, index=g["code"].astype(str).values)
            except (ValueError, IndexError):
                #   종목이 5개 미만이면 분위를 못 나눈다 → 가장 보수적인 1분위로 둔다.
                qmap[t] = pd.Series(1, index=g["code"].astype(str).values)
        cost = CostModel(spread_map=spread_map,
                         market_map=sec.drop_duplicates("code").set_index("code").get("market"),
                         cap_quintile=qmap, adv=adv_map)
        eng = Engine(rebals, FWD, cost, DEL)
        ppy = eng.ppy
        univ_by_t = {t: list(g["code"]) for t, g in univ[univ["u250"]].groupby("rebal", observed=True)}

    # ── Step 1. Phase 0 커버리지 진단 ─────────────────────────────────────────────────
    with PIPE.stage("S1.PHASE0", "Phase 0 커버리지 진단 (게이트)", "L3", budget_s=1800):
        start, end = daily["date"].min(), daily["date"].max()
        codes = sorted(daily["code"].unique())
        src = {}
        src["F1"] = D["cap_events"] if D["cap_events"] is not None else load_capital_events(codes, start, end)
        src["F2"] = D["insider"] if D["insider"] is not None else load_insider(codes, start, end)
        src["F4"] = D["contracts"] if D["contracts"] is not None else load_contracts(codes, start, end)
        prim = {}
        prim["F1"] = build_F1(src["F1"], rebals, univ_by_t, daily, "primary", {})
        prim["F2"] = build_F2(src["F2"], rebals, univ_by_t, univ, "primary", {})
        prim["F3"] = build_F3(daily, rebals, univ_by_t, "primary", {})
        prim["F4"] = build_F4(src["F4"], fin, rebals, univ_by_t, "primary", {})
        covs, b_cov = {}, {}
        for f in ("F1", "F2", "F3", "F4"):
            c = coverage_diag(f, prim[f].obs, prim[f].sig, univ, rebals, codes)
            coverage_bias(c, univ, sec)
            covs[f] = c

    # ── Step 2. 베이스라인 B1~B4 ──────────────────────────────────────────────────────
    with PIPE.stage("S2.BASE", "베이스라인 B1~B4", "L3", budget_s=3600):
        base = run_baselines(eng, univ, elig, "IS")
        LOG.table([[k, f"{r.stats(ppy)['cagr']:.2%}", f"{r.stats(ppy)['mdd']:.1%}",
                    f"{r.stats(ppy)['vol']:.1%}", f"{r.stats(ppy)['turnover']:.1f}x",
                    f"{r.stats(ppy)['cost']:.3f}"] for k, r in base.items()],
                  ["베이스라인", "CAGR", "MDD", "변동성", "연회전율", "누적비용"],
                  ["l", "r", "r", "r", "r", "r"], title="§2 베이스라인 (IS 구간)")
        nulls = {n: random_null(eng, univ, n, SPEC_B4_SIMS, "IS") for n in SPEC_N_VALUES}
        # 커버 종목만 담은 B_cov — '커버되는 것 자체가 알파'인 경우를 분리한다(§3)
        for f, c in covs.items():
            if c.median_cov <= 0:
                continue
            b_cov[f] = Engine(_window_rebals(rebals, "IS"), FWD, cost, DEL).run(
                lambda t, cc=c: [x for x in univ_by_t.get(t, []) if x in cc.covered_codes.get(t, set())],
                f"B_cov[{f}]")
        baseline_report(base, nulls, ppy)
        phase0_report(covs, b_cov, ppy, base.get("B2"))

    # ── Step 3~6. 팩터별 단독 백테스트 (IS) ───────────────────────────────────────────
    FR: Dict[str, dict] = {}
    for f in ("F1", "F2", "F3", "F4"):
        with PIPE.stage(f"S{2+int(f[1])}.{f}", f"{f} 단독 백테스트 (IS)", "L3", budget_s=3600):
            FR[f] = run_factor(f, src, daily, fin, rebals, univ, univ_by_t, sec,
                               eng, base, nulls, covs[f], b_cov.get(f), ppy)

    # ── Step 7. OOS 개봉 ──────────────────────────────────────────────────────────────
    with PIPE.stage("S7.OOS", "IS 통과 팩터만 OOS 개봉 → G4", "L3", budget_s=3600):
        ok = [f for f, r in FR.items()
              if r.get("gates") and all(g.passed is not False
                                        for g in r["gates"] if g.gate in ("G1", "G2", "G3"))]
        LOG.info(f"IS 에서 G1·G2·G3 를 하나도 실패하지 않은 팩터: {ok or '없음'}")
        SEAL.open(f"Step 7 — IS 확정 후 개봉 (대상 {ok or '없음'})")
        base_oos = run_baselines(eng, univ, elig, "OOS")
        for f in ok:
            r = FR[f]
            e2 = Engine(_window_rebals(rebals, "OOS"), FWD, cost, DEL)
            res = e2.run(r["sel_primary"], f"{f} OOS")
            r["oos"] = res
            r["excess"]["oos"] = excess_cagr(res, base_oos["B2"], ppy)
            r["gates"].append(gate_G4(r["excess"]["is"], r["excess"]["oos"]))
        for f in FR:
            if f not in ok:
                FR[f]["gates"].append(GateResult(
                    "G4", None, "—", f"OOS ≥ IS × {SPEC_GATE['g4_oos_ratio']:.0%}",
                    "IS 미통과 — OOS 미개봉(§9 Step 7)"))

    # ── Step 8. 전체 시행수 기준 DSR / PBO ────────────────────────────────────────────
    with PIPE.stage("S8.MULTI", f"다중검정 — 시행수 {SPEC_TRIALS_TOTAL} 기준 DSR/PBO", "L3",
                    budget_s=1200):
        for f, r in FR.items():
            if r.get("primary") is None:
                r["gates"].append(GateResult("G5", None, "—", "DSR>0 · PBO<0.5", "백테스트 미실행"))
                continue
            d = deflated_sharpe(r["primary"].ret, SPEC_TRIALS_TOTAL, ppy)
            grid = pd.DataFrame({k: v.ret for k, v in r["grid"].items()}) if r.get("grid") else pd.DataFrame()
            p = pbo_cscv(grid) if len(grid.columns) >= 2 else dict(pbo=np.nan)
            r["dsr"], r["pbo"] = d, p
            r["gates"].append(gate_G5(d, p))
            LOG.info(f"[{f}] SR {d['sr']:.3f} · SR₀ {d['sr0']:.3f} · DSR {d['dsr']:.3f} · "
                     f"PBO {p.get('pbo', float('nan')):.3f} (격자 {p.get('K', 0)}개, "
                     f"조합 {p.get('n_comb', 0):,})")
        AMENDMENTS.append(
            "§2 의 B4 정의('U250 내 무작위 N종목 EW')는 매 리밸런싱마다 새로 뽑는지, "
            "뽑은 뒤 보유하는지를 명시하지 않는다. 코드는 문자 그대로 '매 리밸 새로 추출'로 "
            "구현했고 G1 판정도 그 분포로만 한다. 다만 그 경우 귀무 포트폴리오의 회전율이 "
            "100%에 가까워져 비용 차가 선별력과 섞이므로, 팩터의 실현 회전율에 맞춘 "
            "귀무분포를 '진단'으로 함께 산출해 G1 비고란에 남겼다(판정에는 쓰지 않음).")
        AMENDMENTS.append(
            f"§6.2 의 시행수 계산 120 = 4팩터×5×N3×2 는 F1(필터형)에 N 차원이 없다는 점을 "
            f"반영하지 않는다. 실제 격자는 F1 {len(FR['F1'].get('grid', {}))}개 + F2~F4 각 "
            f"{len(FR['F2'].get('grid', {}))}개 안팎이다. DSR 은 명세대로 120 을 그대로 썼다 "
            f"(실제보다 큰 시행수는 보수적 방향이므로 결론을 유리하게 만들지 않는다).")
        AMENDMENTS.append(
            "§6.3 G5 의 'DSR > 0' 은 DSR 을 확률로 정의하면 항상 참이라 사실상 비구속 조건이다. "
            "코드는 명세대로 'DSR > 0' 으로 판정하되, 실질 판정에 해당하는 SR > SR₀ 결과를 "
            "비고란에 함께 남겼다. 임계 변경은 명세 개정 사항이므로 코드에서 바꾸지 않았다.")

    # ── Step 9. 용량 시뮬레이션 ───────────────────────────────────────────────────────
    with PIPE.stage("S9.CAP", "용량 시뮬레이션 (AUM 사다리 + 동적 AUM)", "L3", budget_s=3600):
        cap_rows = []
        targets = [("B2 U250 EW", lambda t: univ_by_t.get(t, []))]
        targets += [(f"{f} 주명세", FR[f]["sel_primary"]) for f in FR if FR[f].get("sel_primary")]
        e_is = Engine(_window_rebals(rebals, "IS"), FWD, cost, DEL)
        for name, sel in targets:
            row = {"전략": name}
            for a in SPEC_AUM_LADDER:
                row[str(a)] = e_is.run(sel, name, aum0=a).stats(ppy)["cagr"]
            row["dynamic"] = e_is.run(sel, name, aum0=SPEC_GATE["g2_aum_krw"],
                                      dynamic_aum=True).stats(ppy)["cagr"]
            cap_rows.append(row)
            for f in FR:
                if FR[f].get("sel_primary") is sel:
                    FR[f]["excess"]["dyn"] = row["dynamic"] - cap_rows[0]["dynamic"]
        capacity = pd.DataFrame(cap_rows)
        write_xlsx(_out("capacity_curves.xlsx"), {"AUM별_CAGR": capacity})
        cost.report()

    # ── 산출물 ────────────────────────────────────────────────────────────────────────
    all_gates = {f: r["gates"] for f, r in FR.items()}
    excess = {f: r["excess"] for f, r in FR.items()}
    for f, r in FR.items():
        write_md(_out(FACTOR_DIR[f], f"{f}_gate_scorecard.md"),
                 gate_scorecard_md(f, r["gates"], r["head"]))
    write_md(_out("MASTER_SCORECARD.md"),
             master_scorecard(all_gates, excess, covs, capacity, AMENDMENTS))
    RUNLOG["elapsed_s"] = round(time.time() - t0, 1)
    atomic_write_text(os.path.join(LOG_DIR, f"run_log_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"),
                      json.dumps(RUNLOG, ensure_ascii=False, indent=2, default=str))
    VAULT.flush()
    DARTB.close()
    PIPE.report_stages()
    PIPE.report_flow()
    report_http()
    PIPE.report_runtime()
    VAULT.report()
    LOG.banner("완료", f"{OUTPUT_DIR} · {RUNLOG['elapsed_s']}초 · "
                       f"MASTER_SCORECARD.md 를 먼저 보세요")


def run_factor(f: str, src: dict, daily, fin, rebals, univ, univ_by_t, sec,
               eng: Engine, base: Dict[str, BTResult], nulls: dict, cov: Coverage,
               bcov: Optional[BTResult], ppy: float) -> dict:
    """팩터 하나를 명세대로 끝까지 — 격자 30종 + 게이트 + 필수 부가 산출."""
    meta = FACTOR_META[f]
    out = dict(gates=[], grid={}, excess={}, head={}, primary=None, sel_primary=None)
    if not cov.proceed:
        LOG.warn(f"[{f}] cov_universe_rebal 중앙값 {cov.median_cov:.0f} < "
                 f"{SPEC_COV['hold_median']} → §6.4 조기 중단. 백테스트를 실행하지 않습니다.")
        out["head"] = {"판정": f"HOLD — 커버리지 중앙값 {cov.median_cov:.0f}종목",
                       "사유": "팩터가 아니라 별도 소형 유니버스로 재정의해야 하므로 본 명세 범위 밖"}
        for g in ("G1", "G2", "G3", "G5", "G6", "G7"):
            out["gates"].append(GateResult(g, None, "—", "—", "Phase 0 보류로 미실행"))
        write_xlsx(_out(FACTOR_DIR[f], f"{f}_results.xlsx"),
                   {"보류": pd.DataFrame([{"팩터": f, "판정": "HOLD",
                                          "cov_universe_rebal_중앙값": cov.median_cov}])})
        return out

    e_is = Engine(_window_rebals(rebals, "IS"), FWD_GLOBAL, eng.cost, eng.delist)
    builders = {
        "F1": lambda v, ov: build_F1(src["F1"], rebals, univ_by_t, daily, v, ov),
        "F2": lambda v, ov: build_F2(src["F2"], rebals, univ_by_t, univ, v, ov),
        "F3": lambda v, ov: build_F3(daily, rebals, univ_by_t, v, ov),
        "F4": lambda v, ov: build_F4(src["F4"], fin, rebals, univ_by_t, v, ov),
    }[f]
    variants = SENS.all_variants(f)
    rows = []
    for var in variants:
        fs = builders(var["key"], var["override"])
        n_list = SPEC_N_VALUES if fs.kind != "filter" else (SPEC_N_PRIMARY,)
        for n in n_list:
            for uc in SPEC_UNCOV_MODES:
                sel = fs.selector(univ_by_t, None if fs.kind == "filter" else n, uc)
                key = f"{var['key']}|N{n}|{uc}"
                res = e_is.run(sel, f"{f} {key}")
                out["grid"][key] = res
                rows.append({**perf_row(key, res, ppy, base["B2"]),
                             "변형": var["desc"], "N": n, "미커버처리": uc,
                             "신호셀": int(len(fs.sig)), "비고": fs.note})
                if var["key"] == "primary" and n == SPEC_N_PRIMARY and uc == "neutral":
                    out["primary"], out["sel_primary"], out["fs_primary"] = res, sel, fs
    if out["primary"] is None:
        out["primary"] = list(out["grid"].values())[0]
        out["sel_primary"] = None
    LOG.table([[r["전략"], f"{r['CAGR']:.2%}", f"{r.get('초과CAGR(vs B2)', float('nan')):+.2%}p",
                f"{r['MDD']:.1%}", f"{r['연회전율']:.1f}x"] for r in rows[:12]],
              ["격자", "CAGR", "vs B2", "MDD", "회전율"], ["l", "r", "r", "r", "r"],
              title=f"[{f}] 민감도 격자 (상위 12행 / 총 {len(rows)}행)")

    prim, fsp = out["primary"], out.get("fs_primary")
    out["excess"]["is"] = excess_cagr(prim, base["B2"], ppy)
    if bcov is not None:
        out["excess"]["bcov"] = excess_cagr(prim, bcov, ppy)

    # ── 게이트 ────────────────────────────────────────────────────────────────────────
    null = nulls.get(SPEC_N_PRIMARY)
    g1 = gate_G1(prim, null, ppy)
    #   ★ 진단(게이트 아님): 무작위 귀무분포는 매 리밸 새로 뽑으므로 회전율이 100%에 가깝고,
    #     그 비용 차가 스프레드에 섞인다. 팩터의 실현 회전율에 맞춘 귀무분포를 함께 만들어
    #     "G1 통과가 선별력 때문인지 회전율 차이 때문인지"를 구분할 수 있게 남긴다.
    #     사전등록된 G1 판정 자체는 명세대로 literal B4 로만 한다(§8-3).
    tv = float(prim.turnover.mean()) if len(prim.turnover) else np.nan
    null_m = (random_null(eng, univ, SPEC_N_PRIMARY, sims=200, window="IS",
                          match_turnover=tv) if np.isfinite(tv) else None)
    if null_m is not None and len(null_m.get("cagr", [])):
        c = prim.stats(ppy)["cagr"]
        g1.note = (f"회전율 정합 귀무분포(진단, 200회, 회전율 {tv:.1%}/리밸) p95 = "
                   f"{null_m['p95']:.2%} → {'초과' if c > null_m['p95'] else '미달'}")
        out["null_matched"] = null_m
    out["gates"].append(g1)
    out["gates"].append(gate_G2(prim, base["B2"], ppy))
    out["gates"].append(gate_G3(prim, base["B2"]))
    quint = {}
    if fsp is not None and fsp.kind != "filter" and len(fsp.sig):
        quint = _quintiles(fsp, univ_by_t, e_is, f)
    out["gates"].append(gate_G6(quint, fsp.kind if fsp else "rank", ppy))
    p1 = p2 = p3 = np.nan
    if fsp is not None and len(fsp.sig):
        n_or_none = None if fsp.kind == "filter" else SPEC_N_PRIMARY
        r1 = e_is.run(placebo_shift(fsp, rebals).selector(univ_by_t, n_or_none, "neutral"), f"{f}|P1")
        r2 = e_is.run(placebo_shuffle(fsp, univ_by_t).selector(univ_by_t, n_or_none, "neutral"), f"{f}|P2")
        pm = placebo_matched(fsp, univ, sec)
        r3 = e_is.run(pm.selector(univ_by_t, n_or_none, "neutral"), f"{f}|P3")
        p1 = excess_cagr(r1, base["B2"], ppy)
        p2 = excess_cagr(r2, base["B2"], ppy)
        p3 = prim.stats(ppy)["cagr"] - r3.stats(ppy)["cagr"]
    out["gates"].append(gate_G7(p1, p2, p3, out["excess"]["is"]))
    out["head"] = {"커버리지 판정": f"{cov.verdict} (중앙 {cov.median_cov:.0f}종목)",
                   "주명세 CAGR": f"{prim.stats(ppy)['cagr']:.2%}",
                   "B2 대비 초과": f"{out['excess']['is']:+.2%}p",
                   "B_cov 대비 초과": (f"{out['excess']['bcov']:+.2%}p"
                                       if "bcov" in out["excess"] else "—"),
                   "격자 수": len(out["grid"])}

    if out.get("null_matched") is not None:
        nm = out["null_matched"]["cagr"]
        sheets_null = pd.DataFrame([{"귀무분포": "literal B4 (매 리밸 재추출)",
                                     "중앙 CAGR": float(np.median(null["cagr"])) if null and len(null["cagr"]) else np.nan,
                                     "p95": null["p95"] if null else np.nan},
                                    {"귀무분포": f"회전율 정합 (진단, {tv:.1%}/리밸)",
                                     "중앙 CAGR": float(np.median(nm)), "p95": float(np.quantile(nm, .95))}])
    else:
        sheets_null = None
    sheets = {"격자결과": pd.DataFrame(rows),
              "B4_귀무분포_비교": sheets_null,
              "연도별": yearly_table({"주명세": prim, "B2": base["B2"]}),
              "플라시보": pd.DataFrame([{"P1(−60영업일)": p1, "P2(라벨셔플)": p2,
                                       "P3(매칭대조군 대비)": p3}])}
    if quint:
        sheets["5분위"] = pd.DataFrame([perf_row(f"Q{q}", r, ppy, base["B2"])
                                       for q, r in sorted(quint.items(), reverse=True)])
    sheets.update(_factor_extras(f, src, fsp, univ, univ_by_t, sec, e_is, base, ppy, fin, rebals, daily))
    write_xlsx(_out(FACTOR_DIR[f], f"{f}_results.xlsx"), sheets)
    return out


def _quintiles(fs: FactorSignal, univ_by_t, e_is: Engine, f: str) -> Dict[int, BTResult]:
    """G6 단조성 — 신호 점수 5분위. 상위→하위 단조 감소해야 한다."""
    sig_by_t = {t: g for t, g in fs.sig.groupby("rebal", observed=True)}
    out = {}
    for q in range(1, 6):
        def sel(t, q=q):
            g = sig_by_t.get(t)
            if g is None or len(g) < 10:
                return []
            s = g.set_index("code")["score"].sort_values()
            cand = [c for c in s.index if c in set(univ_by_t.get(t, []))]
            if len(cand) < 10:
                return []
            s = s.reindex(cand).dropna()
            k = len(s)
            lo, hi = int((q - 1) * k / 5), int(q * k / 5)
            return list(s.index[lo:hi])
        out[q] = e_is.run(sel, f"{f} Q{q}")
    return out


def _factor_extras(f, src, fsp, univ, univ_by_t, sec, e_is, base, ppy, fin, rebals, daily) -> dict:
    """§4 팩터별 '필수 부가 산출'."""
    ex = {}
    if f == "F1" and fsp is not None:
        cnt = fsp.sig.groupby("rebal", observed=True)["code"].nunique() if len(fsp.sig) else pd.Series(dtype=int)
        ex["제거종목수_시계열"] = cnt.rename("제거종목수").reset_index()
        # 제거 종목의 실제 사후 수익률 — 음수가 아니면 가설이 틀린 것이다
        rr = []
        for t, g in (fsp.sig.groupby("rebal", observed=True) if len(fsp.sig) else []):
            if t not in FWD_GLOBAL.index:
                continue
            r = FWD_GLOBAL.loc[t].reindex(list(g["code"])).dropna()
            if len(r):
                rr.append({"rebal": t, "제거종목수": len(r), "평균수익": float(r.mean()),
                           "중앙수익": float(r.median()),
                           "U250평균": float(FWD_GLOBAL.loc[t].reindex(univ_by_t.get(t, [])).mean())})
        ex["제거종목_사후수익"] = pd.DataFrame(rr)
        if len(rr):
            m = float(np.nanmean([x["평균수익"] - x["U250평균"] for x in rr]))
            LOG.info(f"[F1] 제거 종목의 사후 초과수익 평균 {m:+.3%}/구간 — "
                     f"{'가설과 정합(음수)' if m < 0 else '★가설과 반대(양수) — H1 이 틀렸다는 증거'}")
            RUNLOG["f1_removed_excess"] = m
        # 폐지 종목 사전 포착률
        dl = sec.dropna(subset=["delisting_date"])[["code", "delisting_date"]]
        dl = dl[dl["code"].isin(set(univ["code"]))]
        hit = 0
        flag = {t: set(g["code"]) for t, g in fsp.sig.groupby("rebal", observed=True)} if len(fsp.sig) else {}
        for _, r in dl.iterrows():
            win = [t for t in rebals if r["delisting_date"] - pd.Timedelta(days=365) <= t <= r["delisting_date"]]
            if any(r["code"] in flag.get(t, set()) for t in win):
                hit += 1
        ex["폐지_사전포착률"] = pd.DataFrame([{"유니버스 내 폐지종목": len(dl), "F1 사전포착": hit,
                                            "포착률": hit / max(len(dl), 1)}])
        LOG.info(f"[F1] 폐지 {len(dl):,}종목 중 사전 포착 {hit:,}종목 "
                 f"({100*hit/max(len(dl),1):.1f}%)")
    if f == "F2" and src.get("F2") is not None and len(src["F2"]):
        d = src["F2"]
        rows = []
        for role in ("대표이사", "등기임원", "최대주주", "특수관계인"):
            sub = d[d["role"].astype(str).str.contains(role)]
            if not len(sub):
                continue
            fs2 = build_F2(sub, rebals, univ_by_t, univ, f"role:{role}", {})
            r = e_is.run(fs2.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), f"F2 {role}")
            rows.append({**perf_row(role, r, ppy, base["B2"]), "건수": len(sub)})
        ex["매수주체별_분해"] = pd.DataFrame(rows)
        LOG.info("[F2] 매수 주체별 분해는 후속 가설 생성용으로만 기록합니다 — "
                 "이 결과를 보고 주 명세를 바꾸지 않습니다(§4 F2).")
    if f == "F4" and src.get("F4") is not None and len(src["F4"]):
        d = src["F4"]
        n_c = int(d["is_cancel"].fillna(False).sum())
        rows = [{"공시건수": len(d), "해지·정정 건수": n_c, "해지율": n_c / max(len(d), 1)}]
        ex["해지_발생률"] = pd.DataFrame(rows)
        fs_no = build_F4(d, fin, rebals, univ_by_t, "no_cancel_tracking", {}, track_cancel=False)
        r_no = e_is.run(fs_no.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), "F4 해지미처리")
        base_c = e_is.run(fsp.selector(univ_by_t, SPEC_N_PRIMARY, "neutral"), "F4 해지처리") \
            if fsp is not None else None
        ex["해지처리_유무_비교"] = pd.DataFrame([
            perf_row("해지 처리(주명세)", base_c, ppy, base["B2"]) if base_c else {},
            perf_row("해지 미처리(미래참조)", r_no, ppy, base["B2"])])
        if base_c is not None:
            gap = r_no.stats(ppy)["cagr"] - base_c.stats(ppy)["cagr"]
            LOG.info(f"[F4] 해지 처리를 빼면 CAGR 이 {gap:+.2%}p 달라집니다 — "
                     f"이만큼이 미래참조로 생기는 가짜 수익입니다.")
            RUNLOG["f4_lookahead_gap"] = gap
    return ex


def main():
    try:
        run_all()
    except SpecViolation as e:
        LOG.error(f"사전등록 위반으로 중단합니다 — {e}")
        raise
    except KillCriteria as e:
        LOG.error(f"킬 기준 — {e}")
        raise


if __name__ == "__main__":
    main()
