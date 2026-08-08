
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import xml.etree.ElementTree as _ET
import socket as _socket
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
