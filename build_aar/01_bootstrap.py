
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트 / pandas 2·3 양립                    ║
# ║  입력: 없음        출력: 전역 ENV, OPT, 임포트된 모듈                                     ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import itertools
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
_ASCII_FALLBACK = str.maketrans({
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "═": "=", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "─": "-", "│": "|",
    "┼": "+", "┬": "+", "┴": "+", "├": "+", "┤": "+", "▼": "v", "▲": "^",
    "✔": "OK", "✘": "X", "⚠": "!", "★": "*", "▶": ">", "▷": ">",
    "⬇": "v", "…": "...", "·": ".", "×": "x", "σ": "sigma", "θ": "theta", "λ": "lambda",
    "Δ": "d", "≥": ">=", "≤": "<=", "≈": "~", "①": "(1)", "②": "(2)",
    "③": "(3)", "④": "(4)", "⑤": "(5)", "⑥": "(6)", "⑦": "(7)",
    "⑧": "(8)", "⑨": "(9)", "⑩": "(10)", "⑪": "(11)", "⑫": "(12)",
    "⭐": "*", "⛔": "STOP", "∏": "prod", "Σ": "sum", "√": "sqrt", "ρ": "rho", "→": "->",
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
_REQUIRED = [
    ("numpy",     "numpy",              "모든 수치연산"),
    ("pandas",    "pandas",             "모든 패널 처리"),
    ("pyarrow",   "pyarrow",            "parquet 캐시 · 샤드 가격저장소"),
    ("scipy",     "scipy",              "통계검정 / 회귀 / 희소행렬"),
    ("requests",  "requests",           "모든 HTTP 수집"),
    ("bs4",       "beautifulsoup4",     "리서치 리스트 파싱"),
    ("lxml",      "lxml",               "HTML/XML 고속 파서"),
    ("tqdm",      "tqdm",               "진행률 표시"),
]
_OPTIONAL = [
    ("FinanceDataReader", "finance-datareader", "가격/상장목록 1순위 (로그인 불필요)"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("statsmodels",       "statsmodels",        "HAC(Newey-West) · 패널 회귀 보조"),
    ("rapidfuzz",         "rapidfuzz",          "애널리스트/종목명 유사도 매칭(고속)"),
    ("html5lib",          "html5lib",           "깨진 HTML 복구 파싱"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출(선택 — 식별률 보강용)"),
]


def _pip_install(pkgs: List[str], quiet: bool = True) -> Tuple[bool, str]:
    if not pkgs:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if quiet:
        cmd.append("-q")
    cmd += pkgs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        return r.returncode == 0, (r.stderr or r.stdout)[-2000:]
    except Exception as e:                                    # noqa
        return False, f"{type(e).__name__}: {e}"


def _ensure_deps() -> Dict[str, bool]:
    import importlib
    missing_req, missing_opt = [], []
    for mod, pkg, _why in _REQUIRED:
        if importlib.util.find_spec(mod) is None:
            missing_req.append(pkg)
    for mod, pkg, _why in _OPTIONAL:
        if importlib.util.find_spec(mod) is None:
            missing_opt.append(pkg)

    if missing_req:
        _safe_print(f"[부트스트랩] 필수 패키지 설치 중: {', '.join(missing_req)}  (1~3분 소요)")
        ok, err = _pip_install(missing_req)
        if not ok:
            _safe_print("\n" + "=" * 88)
            _safe_print("❌ 필수 패키지 설치 실패. 아래 명령을 직접 실행한 뒤 다시 돌려주세요.")
            _safe_print(f"   pip install {' '.join(missing_req)}")
            _safe_print("-" * 88)
            _safe_print(err)
            _safe_print("=" * 88)
            raise SystemExit(1)
        importlib.invalidate_caches()

    if missing_opt:
        _safe_print(f"[부트스트랩] 선택 패키지 설치 중: {', '.join(missing_opt)}")
        _pip_install(missing_opt)          # 실패해도 계속 — 각 기능에서 개별적으로 degrade
        importlib.invalidate_caches()

    # find_spec 은 모듈을 실행하지 않으므로 부작용이 없다. 실제 import 는 아래 통제된 블록에서만.
    return {mod: (importlib.util.find_spec(mod) is not None) for mod, _pkg, _why in _OPTIONAL}


# ★ KRX 자격증명은 KRX_ENABLED 일 때만 주입한다.
#   pykrx 는 import 시점에 KRX 로그인을 수행하므로, 차단된 계정 정보를 환경변수에 넣어두면
#   설치돼 있기만 해도 로그인 시도가 발생해 차단이 더 굳어진다. 이 전략은 KRX 에 의존하지
#   않으므로 아예 건드리지 않는 것이 옳다.
if KRX_ENABLED and KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW
else:
    for _k in ("KRX_ID", "KRX_PW"):
        os.environ.pop(_k, None)

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
np.seterr(all="ignore")

# ── pandas 2.x / 3.x 양립 계층 ──────────────────────────────────────────────────────────────
#   pandas 3.0 은 문자열 기본 dtype 이 object 가 아니라 str 이다. 그래서
#   `df[c].dtype == object` 로 문자열 컬럼을 찾던 관용구가 **예외 없이 조용히 0개를 반환**한다.
#   (dtype.kind 는 여전히 "O" 라 kind 로 보면 양쪽에서 동작한다)
#   또 Copy-on-Write 가 강제되어 `df[mask]["c"] = v` 같은 연쇄 대입이 **경고 없이 무시**된다.
#   이 두 가지가 pandas 3 에서 가장 흔한 무증상 버그이므로 여기서 한 번에 봉인한다.
PANDAS_MAJOR = int(str(pd.__version__).split(".")[0])
NUMPY_MAJOR = int(str(np.__version__).split(".")[0])


def is_texty(s) -> bool:
    """문자열/객체 컬럼인가. pandas 2(object) 와 3(str) 양쪽에서 동일하게 동작한다."""
    try:
        dt = s.dtype if hasattr(s, "dtype") else s
        if getattr(dt, "kind", "") == "O":
            return True
        return bool(pd.api.types.is_string_dtype(dt))
    except Exception:
        return False


def text_cols(df: "pd.DataFrame") -> List[str]:
    return [c for c in df.columns if is_texty(df[c])]


def as_str_series(s) -> "pd.Series":
    """결측을 빈 문자열로 만든 문자열 Series. astype(str) 은 pandas 3 에서 NaN 을
    문자열로 바꾸지 않고 남기므로(dtype=str 의 결측 표현), 비교·해시 전에 반드시 통과시킨다."""
    return pd.Series(s).astype("object").where(pd.notna(pd.Series(s)), "").astype(str)


try:
    pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
except Exception:
    pass
try:                       # pandas 2 에서 CoW 를 미리 켜 3.x 와 동작을 일치시킨다
    if PANDAS_MAJOR < 3:
        pd.set_option("mode.copy_on_write", True)
except Exception:
    pass

# 결정성: 모든 난수는 이 시드에서 파생된다.
random.seed(SEED)
np.random.seed(SEED % (2 ** 32 - 1))
RNG = np.random.default_rng(SEED)

# 선택 모듈 핸들
fdr = yf = smapi = rapidfuzz_fuzz = fitz = None
if OPT.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr           # type: ignore
    except Exception:
        fdr = None
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
    except Exception:
        yf = None
if OPT.get("statsmodels"):
    try:
        import statsmodels.api as smapi           # type: ignore
    except Exception:
        smapi = None
if OPT.get("rapidfuzz"):
    try:
        from rapidfuzz import fuzz as rapidfuzz_fuzz   # type: ignore
    except Exception:
        rapidfuzz_fuzz = None
if OPT.get("fitz"):
    try:
        import fitz                               # type: ignore  (pymupdf)
    except Exception:
        fitz = None

# ── 병렬 전략 결정 ──────────────────────────────────────────────────────────────────────────
#   노트북에서 ProcessPoolExecutor 는 "__main__ 에 정의된 함수를 피클할 수 없음" 으로 자주 죽는다.
#   fork 를 쓸 수 있는 리눅스(=Colab)에서는 안전하고, spawn 플랫폼(win/mac)에서는 스레드로 폴백.
import multiprocessing as _mp
try:
    _MP_METHODS = set(_mp.get_all_start_methods())
except Exception:
    _MP_METHODS = {"spawn"}
CAN_FORK = ("fork" in _MP_METHODS) and (ENV["platform"] == "Linux")
N_CPU = N_WORKERS_CPU if N_WORKERS_CPU and N_WORKERS_CPU > 0 else max(1, (os.cpu_count() or 2) - 1)
