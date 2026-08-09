#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   SCG — Smart Consensus Gap 백테스트 (BASE_REV · SCG_0 · SCG_LS · SCG_LSA)
#   구간: 2016-08 ~ 2026-07 (10년) · 한국 상장 전종목 PIT 유니버스
#
#   ▣ 이 파일 하나로 완결됩니다.
#     Colab / JupyterLab 어느 쪽이든 "한 셀"에 전체를 붙여넣고 실행하거나
#     `python scg_smart_consensus_v1.py` 로 실행하면 동일하게 동작합니다.
#
#   ▣ 실행 순서 (각 단계는 실패 지점·데이터 입출력이 원장에 기록됩니다)
#     [S0] 환경 준비(의존성/드라이브)     [S1] 캐시 금고 연결(로컬+드라이브 다중루트 탐색)
#     [S2] 자체계약 검증(TEST1~9 등)      [S3] 합성데이터 전체경로 스모크
#     [S4] 데이터 수집(유니버스→가격→리포트→실적) — 캐시 우선, 부족분만 신규
#     [S5] 보고서↔애널리스트↔종목 원장 연결 감사
#     [S6] 예측 테이블 구축(EPS/목표가)   [S7] SCG 엔진(정확도·리더십·스마트컨센서스)
#     [S8] 백테스트+성과검증(4전략)       [S9] 시총 하위1000 비교전략(별도 전체 출력)
#     [S10] 강건성 검사(민감도/서브기간/집중도/플라시보/지연)
#     [S11] 해석표 · 드라이브 저장(공용/전용 인덱스) · 다운로드 링크
#
#   ▣ 캐시 절대 1원칙
#     · 기존 구글드라이브 캐시(어느 전략이 만든 것이든)는 **읽기 전용**으로만 탐색·재활용.
#     · 신규 수집분은 전부 이 전략의 쓰기 루트에 저장하고 공용/전용 인덱스(append-only
#       JSONL 저널)에 등재. 기존 인덱스 파일에는 **쓰기 자체를 하지 않으므로** 훼손이
#       구조적으로 불가능합니다. (실행 후 실측 검증까지 수행 — S2 계약 C-보존)
#
#   ⚠ 연구·검증용 코드입니다. 투자자문이 아닙니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [입력부]  여기만 채우면 됩니다 — 전부 비워도 실행됩니다(없는 소스는 건너뛰고 사유 출력)   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── ① KRX 정보데이터시스템(마켓플레이스) 로그인 ─────────────────────────────────────────────
#    어디서 얻나: https://data.krx.co.kr → 우측 상단 [회원가입](무료) → 아이디/비밀번호.
#    2025-12 인증정책 변경 후 KRX 시세·시총 조회에 로그인 세션이 필요합니다.
#    ⚠ 같은 계정을 브라우저에서 동시에 로그인해 두지 마세요 — KRX는 중복로그인(CD011) 시
#      기존 세션을 끊어 수집이 로그인 HTML 을 받게 됩니다(코드가 감지해 재로그인합니다).
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

# ── ② DART OpenAPI 인증키 (실적 EPS·발표일 = 정확도 점수의 원천) ────────────────────────────
#    어디서 얻나: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → 즉시 무료 발급.
#    일일 한도(공식 20,000건)는 **고정 예산으로 미리 깎지 않고** 실제 사용량을 실시간
#    카운트하며, 서버가 한도초과(status 020/021)를 알리는 순간 그 소스만 우아하게 멈추고
#    받은 만큼 저장합니다. 오늘 쓴 호출수는 드라이브에 기록되어 재실행 시 이어집니다.
DART_API_KEY = ""

# ── ③ 구글드라이브 캐시 경로 ────────────────────────────────────────────────────────────────
#    쓰기 루트(신규 저장 전용) — 이 안에 공용(shared)/전용(scg_v1) 인덱스가 만들어집니다.
GDRIVE_WRITE_ROOT = "/content/drive/MyDrive/scg_cache"
#    읽기 루트(기존 캐시 재활용, 읽기전용) — 자동 탐색 + 아래 수동 추가. 절대 쓰지 않습니다.
GDRIVE_READ_ROOTS_EXTRA = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/MIRAE_QUANT_CACHE_V1",
    "/content/drive/MyDrive/QuantCache",
    "/content/drive/MyDrive/quant_cache",
    "/content/drive/MyDrive/quant",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
]
#    로컬 캐시 탐색(있으면 드라이브보다 먼저 조회해 시간 절약; 없으면 무시) — D드라이브 포함.
LOCAL_CACHE_DIRS = [
    "D:/quant_cache", "D:/scg_cache", "D:/tcd_cache", "D:/캐시",
    "./scg_cache", "~/scg_cache", "~/quant_cache",
]
#    JupyterLab(로컬)에서 구글드라이브 데스크톱 동기화 폴더가 있으면 자동 인식합니다.
#    자동 인식이 실패하면 여기에 직접 적어주세요. (예: "G:/내 드라이브/scg_cache")
GDRIVE_DESKTOP_OVERRIDE = ""

# ── ④ 백테스트 구간 · 실행 모드 ─────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"
#    "SMOKE"  = 합성데이터로 전 출력물 예행연습(네트워크·키 불필요, 수 분). 처음엔 이걸로.
#    "FULL"   = 스모크 → 실데이터 수집 → 백테스트 → 강건성 → 해석표 (기본값)
#    "CACHED" = 신규 수집 없이 캐시만으로 재현(오프라인)
RUN_MODE = "FULL"

# ── ⑤ 애널리스트 리포트 수집 ────────────────────────────────────────────────────────────────
#    한경컨센서스·네이버리서치 리스트를 수집하고, PDF 원문에서 EPS 추정치·목표주가를
#    추출합니다. 드라이브에 이미 캐시된 원장·PDF는 재수집하지 않고 그대로 씁니다.
RESEARCH_COLLECT       = True
RESEARCH_DOWNLOAD_PDF  = True     # PDF 원문 수집(EPS 추출 정확도↑, 용량·시간↑)
RESEARCH_PDF_CAP_MONTH = 0        # 월별 PDF 다운로드 상한. 0 = 무제한, 테스트 시 50 권장
FORECAST_METRIC_MODE   = "AUTO"   # "AUTO" | "EPS" | "TP12M"
#    AUTO: EPS 추정치 커버리지가 충분하면 EPS(명세 §1 기본), 부족하면 목표주가 12M(TP12M)
#          를 주 지표로 쓰고 두 경우 모두 커버리지 근거를 표로 출력합니다.

# ── ⑥ 성능/자원 ─────────────────────────────────────────────────────────────────────────────
COLLECT_HOURS_BUDGET = 4.0        # ★ 수집 시간예산(시간). 초과하면 수집을 그 자리에서 멈추고
                                  #   지금까지 모은 데이터만으로 '중간 백테스트 결과'를 출력한다.
                                  #   (수집은 전부 증분 캐시라 재실행하면 멈춘 곳부터 이어받는다)
N_IO_THREADS   = 12               # 네트워크 병렬(스레드). 차단이 의심되면 6으로.
QPS = {"krx": 1.5, "dart": 8.0, "hankyung": 2.0, "naver": 2.5, "kind": 2.0,
       "fdr": 4.0, "yahoo": 3.0, "generic": 3.0}   # 소스별 초당 요청 상한(차단 방지)
MEM_SOFT_GB    = 6.0              # 이 수준을 넘보면 청크 처리로 전환
COST_BPS_ONEWAY = 15.0            # 십분위 성과의 왕복비용 가정(수수료+세금+슬리피지, 편도 bp)

# ── ⑦ 비교전략 · 기타 ───────────────────────────────────────────────────────────────────────
COMPARE_BOTTOM_N = 1000           # 시총 하위 1000 종목 비교 유니버스
SEED = 20260809                   # 모든 난수의 단일 시드(결정성 계약 C-결정 검증 대상)
VERBOSE = True

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝 — 아래부터는 수정할 필요가 없습니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

SCG_BUILD = "scg_v1.20260809"
STRATEGY_TAG = "scg_v1"           # 전용 인덱스 네임스페이스 이름


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-a] 표준 라이브러리 · 콘솔 안전장치                                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, io, re, json, math, time, gc, glob, shutil, hashlib, random, platform
import datetime as _dt
import threading, tempfile, traceback, unicodedata, subprocess, importlib, importlib.util
from collections import Counter, OrderedDict, defaultdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")           # Windows cp949 콘솔 깨짐 방지
    except Exception:
        pass


def _println(*a, **k):
    """print 가 콘솔 인코딩 문제로 죽어도 실행은 계속되게 하는 최후의 안전판."""
    try:
        print(*a, **k)
    except UnicodeEncodeError:
        try:
            print(*(str(x).encode("utf-8", "replace").decode("ascii", "replace")
                    for x in a), **k)
        except Exception:
            pass


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-b] 실행환경 감지 (Colab / JupyterLab / CLI)                                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _find_spec_safe(name: str):
    try:
        return importlib.util.find_spec(name)
    except Exception:          # 부모 패키지 자체가 없으면 find_spec 이 예외를 던진다
        return None


def _detect_rig() -> Dict[str, Any]:
    colab = ("google.colab" in sys.modules or os.environ.get("COLAB_RELEASE_TAG")
             or _find_spec_safe("google.colab") is not None)
    ipy = False
    try:
        from IPython import get_ipython        # type: ignore
        ipy = get_ipython() is not None
    except Exception:
        ipy = False
    return {
        "colab": bool(colab), "ipython": bool(ipy),
        "python": platform.python_version(), "os": platform.system(),
        "cpu": os.cpu_count() or 2, "windows": platform.system() == "Windows",
    }


RIG = _detect_rig()


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-c] 의존성 — 필수는 자동 설치, 선택은 없으면 대체경로                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_NEED = [("numpy", "numpy"), ("pandas", "pandas"), ("pyarrow", "pyarrow"),
         ("requests", "requests"), ("bs4", "beautifulsoup4"), ("lxml", "lxml")]
_NICE = [("scipy", "scipy", "스피어만 IC 정밀계산(없으면 자체 구현 사용)"),
         ("FinanceDataReader", "finance-datareader", "상장/상폐 목록·지수·가격 폴백"),
         ("pykrx", "pykrx", "KRX 시세·시총 스냅샷(1순위 가격/시총 소스)"),
         ("yfinance", "yfinance", "가격 최후 폴백"),
         ("fitz", "pymupdf", "PDF 텍스트 추출(EPS 추정치) 1순위"),
         ("pdfplumber", "pdfplumber", "PDF 텍스트 추출 2순위")]


def _pip(pkgs: List[str]) -> bool:
    if os.environ.get("SCG_NO_PIP"):
        return False
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs],
                           capture_output=True, text=True, timeout=1500)
        return r.returncode == 0
    except Exception:
        return False


def _boot_deps() -> Dict[str, bool]:
    missing = [p for m, p in _NEED if _find_spec_safe(m.split(".")[0]) is None]
    if missing:
        _println(f"[S0] 필수 패키지 설치: {missing}")
        if not _pip(missing):
            still = [p for m, p in _NEED if _find_spec_safe(m.split(".")[0]) is None]
            if still:
                _println("─" * 80)
                _println("필수 패키지가 없어 진행할 수 없습니다. 아래를 실행한 뒤 다시 시작하세요:")
                _println(f"    pip install {' '.join(still)}")
                _println("─" * 80)
                raise SystemExit(1)
    have: Dict[str, bool] = {}
    want = [(m, p) for m, p, _w in _NICE if _find_spec_safe(m.split(".")[0]) is None]
    if want and not os.environ.get("SCG_NO_PIP"):
        _pip([p for _m, p in want])
    for m, p, why in _NICE:
        have[m] = _find_spec_safe(m.split(".")[0]) is not None
        if not have[m]:
            _println(f"[S0] 선택 패키지 없음: {p} — {why}. 대체 경로로 계속합니다.")
    return have


# ★ pykrx 는 import 시점에 KRX 세션을 만들므로, 자격증명을 '먼저' 환경변수로 심는다.
#   (import 후에 넣으면 이미 익명 세션이 만들어져 2025-12 이후 조회가 막힌다)
if KRX_MARKETPLACE_ID:
    os.environ.setdefault("KRX_ID", KRX_MARKETPLACE_ID)
    os.environ.setdefault("KRX_PW", KRX_MARKETPLACE_PW)

HAVE = _boot_deps()

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ★ 선택 패키지는 '설치되어 있음'과 '실제로 import 됨'이 다르다.
#   pykrx 는 import 시점에 KRX 로그인을 시도하므로, 그 안에서 예외가 나면 설치돼 있어도
#   import 자체가 실패한다. 예전 버전은 이 실패를 조용히 None 으로 삼켜서, 수집이
#   "네트워크를 한 번도 부르지 않고" 0행을 반환했다 — 로그만 보면 원인을 알 수 없었다.
#   그래서 실패 사유를 문자열로 남기고 환경표에 그대로 출력한다.
IMPORT_ERR: Dict[str, str] = {}


def _opt_import(label: str, fn: Callable):
    try:
        return fn()
    except BaseException as e:                 # SystemExit 까지 포함해 잡는다
        IMPORT_ERR[label] = f"{type(e).__name__}: {e}"[:160]
        return None


_scistats = _opt_import("scipy", lambda: __import__("scipy.stats", fromlist=["stats"]))
fdr = _opt_import("FinanceDataReader", lambda: __import__("FinanceDataReader"))
pykrx_stock = _opt_import("pykrx", lambda: __import__("pykrx.stock", fromlist=["stock"]))
yf = _opt_import("yfinance", lambda: __import__("yfinance"))
try:
    import fitz as _fitz                      # pymupdf
except Exception:
    _fitz = None
try:
    import pdfplumber as _pdfplumber
except Exception:
    _pdfplumber = None

random.seed(SEED)
np.random.seed(SEED % (2**32 - 1))
RNG = np.random.default_rng(SEED)
try:
    pd.set_option("mode.copy_on_write", True)
except Exception:
    pass                                     # 구버전 pandas 호환


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-d] 콘솔 로거 — 한글 폭 계산 표 출력(해석표가 어긋나지 않게)                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _vw(s: str) -> int:
    """동아시아 전각문자를 폭 2로 계산 — 이걸 안 하면 한글 표가 전부 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(s))


def _fit(s: str, w: int, align: str = "l") -> str:
    s = str(s)
    while _vw(s) > w and len(s) > 1:
        s = s[:-1]
    pad = w - _vw(s)
    return (" " * pad + s) if align == "r" else (s + " " * pad) if align == "l" \
        else (" " * (pad // 2) + s + " " * (pad - pad // 2))


class _Console:
    def __init__(self):
        self.buffer: List[str] = []
        self.t0 = time.time()
        self.scope: List[str] = []

    def _emit(self, icon: str, msg: str):
        ts = time.time() - self.t0
        sc = ("·".join(self.scope) + " ") if self.scope else ""
        line = f"[{int(ts//60):02d}:{ts % 60:05.2f}] {icon} {sc}{msg}"
        self.buffer.append(line)
        _println(line)

    def say(self, m):   self._emit("│", m)
    def ok(self, m):    self._emit("✔", m)
    def warn(self, m):  self._emit("⚠", m)
    def err(self, m):   self._emit("✘", m)

    def debug(self, m):
        if VERBOSE:
            self._emit("·", m)

    def line(self, title: str = "", width: int = 100):
        t = f"─ {title} " if title else ""
        self._emit("", t + "─" * max(4, width - _vw(t)))

    def head(self, title: str, sub: str = "", width: int = 100):
        self._emit("", "╔" + "═" * (width - 2) + "╗")
        self._emit("", "║ " + _fit(title, width - 4) + " ║")
        if sub:
            self._emit("", "║ " + _fit(sub, width - 4) + " ║")
        self._emit("", "╚" + "═" * (width - 2) + "╝")

    def grid(self, rows: Sequence[Sequence[Any]], cols: Sequence[str],
             align: Optional[Sequence[str]] = None, title: str = "", maxw: int = 44):
        if title:
            self.line(title)
        if not rows:
            self.say("(빈 표)")
            return
        rows = [[("" if v is None else v) for v in r] for r in rows]
        align = list(align or ["l"] * len(cols))
        ws = [min(maxw, max(_vw(c), *(_vw(r[i]) for r in rows))) for i, c in enumerate(cols)]
        self._emit("", "  " + "  ".join(_fit(c, ws[i], "c") for i, c in enumerate(cols)))
        self._emit("", "  " + "  ".join("─" * w for w in ws))
        for r in rows:
            self._emit("", "  " + "  ".join(
                _fit(r[i], ws[i], align[i] if i < len(align) else "l")
                for i in range(len(cols))))

    @contextmanager
    def inside(self, tag: str):
        self.scope.append(tag)
        try:
            yield
        finally:
            self.scope.pop()


CON = _Console()


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-e] 실행 원장(Orchestra) — 어느 단계에서 무엇이 들어오고 나갔는지 · 실패 지점 즉시 특정  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
class HaltRun(Exception):
    """치명 단계 실패 — 원인 요약과 함께 전체 실행을 멈춘다."""


class RuleBreak(Exception):
    """자체계약(TEST/C-*) 위반 — 파라미터를 바꿔 통과시키지 말 것."""


_DIAG = [
    (r"status.*?020|요청.*한도|OVER_QUOTA", "DART 일일 호출한도 소진 — 받은 만큼 저장했습니다. 내일 같은 키로 재실행하면 이어받습니다."),
    (r"CD011|중복\s*로그인", "KRX 중복로그인으로 세션이 끊겼습니다 — 브라우저의 data.krx.co.kr 로그아웃 후 재실행하세요."),
    (r"010|011|등록되지 않은 키|INVALID.*KEY", "API 키가 잘못되었습니다 — 입력부의 키를 발급 사이트에서 다시 확인하세요."),
    (r"429|Too Many|Rate", "요청 속도 제한에 걸렸습니다 — QPS 설정을 낮추고 재실행하세요(캐시부터 이어받습니다)."),
    (r"403|Forbidden", "원격지가 접근을 거부했습니다 — 잠시 후 재시도하거나 해당 소스를 끄세요."),
    (r"MyDrive|drive.*mount|No such file.*content", "구글드라이브가 마운트되지 않았습니다 — Colab이면 팝업 승인, 로컬이면 GDRIVE_DESKTOP_OVERRIDE 를 지정하세요."),
    (r"No space|디스크|ENOSPC", "저장공간 부족 — RESEARCH_DOWNLOAD_PDF=False 로 낮추거나 공간을 비우세요."),
    (r"MemoryError|Unable to allocate", "메모리 부족 — N_IO_THREADS 를 줄이고 재실행하세요(청크 처리로 이어받습니다)."),
    (r"JSONDecode|Expecting value", "JSON 대신 HTML(로그인/차단 페이지)을 받았습니다 — 자격증명/차단 여부를 확인하세요."),
    (r"ConnectionError|Timeout|NameResolution", "네트워크 오류 — 연결 확인 후 재실행하면 캐시에서 이어받습니다."),
]


def _diagnose(e: BaseException) -> str:
    s = f"{type(e).__name__}: {e}"
    for pat, hint in _DIAG:
        if re.search(pat, s, re.I):
            return hint
    return "아래 트레이스백 마지막 줄과 단계 원장을 보면 위치가 특정됩니다."


class Orchestra:
    """단계 실행기 + 데이터 입출력 원장. '거시 흐름'과 '미시 입출력'을 한 표에서 본다."""

    def __init__(self):
        self.parts: "OrderedDict[str, dict]" = OrderedDict()
        self.io_log: List[dict] = []
        self.cur: Optional[str] = None

    @contextmanager
    def part(self, pid: str, title: str, critical: bool = True,
             budget_s: Optional[float] = None, skip: bool = False, why: str = ""):
        rec = dict(id=pid, title=title, status="진행", t0=time.time(), t1=None,
                   critical=critical, budget_s=budget_s, err="", hint="", note="")
        self.parts[pid] = rec
        if skip:
            rec.update(status="건너뜀", note=why, t1=time.time())
            CON.warn(f"[{pid}] {title} — 건너뜀: {why}")
            # contextmanager 구조상 with 본문 자체를 생략할 수는 없다 — 본문 함수들이
            # 내부 플래그로 무동작하도록 짜여 있고, 여기서는 예외만 흡수해 원장에 남긴다.
            try:
                yield
            except Exception as e:
                rec.update(status="경고", err=f"{type(e).__name__}: {e}")
                CON.warn(f"[{pid}] 건너뜀 단계 내부 예외 무시: {type(e).__name__}: {e}")
            return
        prev, self.cur = self.cur, pid
        CON.line(f"[{pid}] {title}")
        try:
            with CON.inside(pid):
                yield
            rec.update(status="완료", t1=time.time())
            dur = rec["t1"] - rec["t0"]
            if budget_s and dur > budget_s:
                rec["note"] = f"예산 {budget_s:.0f}s 초과({dur:.0f}s)"
            CON.ok(f"[{pid}] {title} — {dur:.1f}s")
        except (HaltRun, RuleBreak, KeyboardInterrupt):
            rec.update(status="실패", t1=time.time(),
                       err=traceback.format_exc(limit=6).strip().splitlines()[-1])
            raise
        except Exception as e:
            rec.update(status="실패", t1=time.time(),
                       err=f"{type(e).__name__}: {e}", hint=_diagnose(e))
            self._crash_detail(pid, e)
            if critical:
                raise HaltRun(f"[{pid}] {title} 실패 — {rec['err']}") from e
            rec["status"] = "경고"
            CON.warn(f"[{pid}] 비치명 단계 실패 — 파이프라인은 계속합니다: {rec['err']}")
        finally:
            self.cur = prev

    def io(self, way: str, medium: str, name: str, obj=None, src: str = "", note: str = ""):
        """way='입'|'출', medium='HTTP'|'드라이브'|'로컬'|'메모리'|'합성'. obj 는 그대로 돌려준다."""
        rows = cols = -1
        try:
            if isinstance(obj, pd.DataFrame):
                rows, cols = len(obj), obj.shape[1]
            elif isinstance(obj, (list, tuple, dict)):
                rows = len(obj)
            elif isinstance(obj, (bytes, bytearray)):
                rows = len(obj)
        except Exception:
            pass
        self.io_log.append(dict(part=self.cur or "-", way=way, medium=medium, name=name,
                                rows=rows, cols=cols, src=src, note=note, ts=_now_iso()))
        return obj

    def _crash_detail(self, pid: str, e: BaseException):
        CON.err(f"[{pid}] 실패 지점 상세 ↓")
        CON.say(f"  예외: {type(e).__name__}: {e}")
        CON.say(f"  진단: {_diagnose(e)}")
        recent = [r for r in self.io_log if r["part"] == pid][-6:]
        for r in recent:
            CON.say(f"  최근 I/O: [{r['way']}·{r['medium']}] {r['name']} "
                    f"rows={r['rows']} src={r['src']}")
        for ln in traceback.format_exc(limit=10).strip().splitlines()[-8:]:
            CON.say("  " + ln)

    def parts_table(self):
        rows = []
        for r in self.parts.values():
            dur = (r["t1"] or time.time()) - r["t0"]
            icon = {"완료": "✔", "실패": "✘", "경고": "⚠", "건너뜀": "…", "진행": "▶"}[r["status"]]
            rows.append([r["id"], r["title"], icon + r["status"], f"{dur:7.1f}s",
                         r.get("err", "")[:56] or r.get("note", "")])
        CON.grid(rows, ["단계", "이름", "상태", "소요", "비고/오류"],
                 ["l", "l", "l", "r", "l"], title="실행 단계 원장(거시 흐름)")

    def io_table(self, limit: int = 200):
        rows = [[r["part"], r["way"], r["medium"], r["name"], f"{r['rows']:,}" if r["rows"] >= 0 else "-",
                 r["src"][:38], r["note"][:24]] for r in self.io_log[-limit:]]
        CON.grid(rows, ["단계", "입출", "매체", "데이터", "행수", "출처", "비고"],
                 ["l", "c", "l", "l", "r", "l", "l"],
                 title=f"데이터 입출력 원장(미시 흐름, 최근 {min(limit, len(self.io_log))}건)")


FLOW = Orchestra()


def dataflow_map():
    CON.line("데이터 흐름 지도 (모듈 ↔ 입출력)")
    for ln in [
        "  [S4a 유니버스] pykrx/KRX마켓·FDR·KIND ─→ 종목마스터+월별시총 ─→ (공용인덱스 저장)",
        "  [S4b 가격]     pykrx→FDR→네이버→야후 폴백 ─→ 일별 수정주가 패널 ─→ (공용)",
        "  [S4c 리포트]   한경컨센서스+네이버리서치 ─→ 보고서 원장+PDF blob ─→ (공용)",
        "  [S4d 실적]     DART EPS+접수일(PIT) / 네이버 폴백 ─→ actuals ─→ (공용)",
        "  [S5 원장감사]  보고서↔애널리스트↔종목 연결률 · 다중소스 병합 무결성",
        "  [S6 예측]      원장+PDF ─→ analyst_forecasts(EPS/TP12M) · actuals 정합",
        "  [S7 엔진]      정확도·리더십 사건 ─→ PIT 점수 ─→ 스마트컨센서스 ─→ 신호 4종",
        "  [S8~S9 백테스트] 십분위·IC·성과 — 전체 vs 시총하위1000 (전용인덱스 저장)",
        "  [S10 강건성]   민감도(45/6/20±)·서브기간·집중도·플라시보·신호지연",
        "  [S11 해석표]   성과검증표·IC표·단조성·감사표·다운로드 링크",
    ]:
        CON.say(ln)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-f] 공용 유틸 — 날짜 · 해시 · 원자적 쓰기 · 병렬 · 스로틀 · 메모리                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def ts(x) -> Optional[pd.Timestamp]:
    """무엇이 오든 tz 없는 자정 Timestamp 로. 실패는 None (예외로 파이프라인을 죽이지 않는다)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    try:
        t = pd.Timestamp(x)
        if t.tzinfo is not None:
            t = t.tz_localize(None)
        return t.normalize()
    except Exception:
        return None


def ts_col(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    try:
        out = out.dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    return out.dt.normalize()


def month_ends(a, b) -> pd.DatetimeIndex:
    try:
        return pd.date_range(ts(a), ts(b), freq="ME")
    except ValueError:                       # pandas < 2.2 는 "M"
        return pd.date_range(ts(a), ts(b), freq="M")


def _resample_me(s: pd.Series) -> pd.Series:
    try:
        return s.resample("ME").last()
    except ValueError:                       # pandas < 2.2
        return s.resample("M").last()


def h1(*parts) -> str:
    return hashlib.sha1("\x1e".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def h1b(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def code6(x) -> Optional[str]:
    """한국 종목코드 정규화. 숫자 5~6자리는 6자리로, 신형 영숫자 코드(뒤 K 등)는 그대로."""
    if x is None:
        return None
    s = str(x).strip().upper()
    s = re.sub(r"\.(KS|KQ)$", "", s)
    if re.fullmatch(r"\d{1,6}", s):
        return s.zfill(6)
    if re.fullmatch(r"\d{5}[0-9A-Z]", s):
        return s
    m = re.search(r"\((\d{6})\)", s)
    return m.group(1) if m else None


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = re.sub(r"\(주\)|주식회사|㈜|\s+", "", s)
    return re.sub(r"(CO\.?,?\s*LTD\.?|INC\.?|CORP\.?)$", "", s, flags=re.I).strip()


def _mkdirs(p: str):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)


def write_atomic_bytes(path: str, data: bytes):
    _mkdirs(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)          # 같은 볼륨 내 원자적 교체 — 반쯤 쓰인 파일이 남지 않는다


def write_atomic_text(path: str, text: str):
    write_atomic_bytes(path, text.encode("utf-8"))


def write_atomic_parquet(df: pd.DataFrame, path: str):
    _mkdirs(path)
    tmp = f"{path}.tmp.{os.getpid()}.parquet"
    try:
        df.to_parquet(tmp, compression="zstd", index=False)
    except Exception:
        df.to_parquet(tmp, compression="snappy", index=False)
    os.replace(tmp, path)


def read_parquet_soft(path: str) -> Optional[pd.DataFrame]:
    """깨진 parquet 는 조용히 None — 원본은 절대 지우지 않고 그대로 둔다(읽기전용 원칙)."""
    if not path or not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        CON.warn(f"parquet 판독 실패({type(e).__name__}): {os.path.basename(path)} — 건너뜀")
        return None


def jsonl_read(path: str) -> List[dict]:
    out = []
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue      # 손상 줄은 건너뛰되 나머지는 살린다
    except Exception:
        pass
    return out


def jsonl_append(path: str, rows: Iterable[dict]):
    _mkdirs(path)
    with open(path, "a", encoding="utf-8") as f:      # append-only — 기존 줄은 절대 재기록 없음
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


class Throttle:
    """소스별 초당 요청 상한 — 차단 방지의 1차 방어선."""
    def __init__(self):
        self._lk = threading.Lock()
        self._next: Dict[str, float] = {}

    def wait(self, source: str):
        qps = float(QPS.get(source, QPS["generic"]))
        gap = 1.0 / max(qps, 0.1)
        with self._lk:
            now = time.time()
            t = max(self._next.get(source, 0.0), now)
            self._next[source] = t + gap
        if t > now:
            time.sleep(t - now)


THROTTLE = Throttle()


def pmap(fn: Callable, items: Sequence, workers: Optional[int] = None,
         label: str = "") -> List:
    """IO 병렬 map(스레드) — 순서 보존, 개별 실패는 None + 집계 로그."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or N_IO_THREADS, len(items)))
    out: List[Any] = [None] * len(items)
    errs: Counter = Counter()
    with ThreadPoolExecutor(max_workers=w) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        done = 0
        for fu in as_completed(futs):
            i = futs[fu]
            try:
                out[i] = fu.result()
            except Exception as e:
                errs[type(e).__name__] += 1
            done += 1
            if label and done % max(1, len(items) // 10) == 0:
                CON.debug(f"{label}: {done}/{len(items)}")
    if errs:
        CON.warn(f"{label or 'pmap'} 부분 실패 {sum(errs.values())}건: {dict(errs)}")
    return out


def shrink(df: pd.DataFrame) -> pd.DataFrame:
    """램 절약 — float64→float32, 저카디널리티 문자열→category."""
    for c in df.columns:
        d = df[c].dtype
        if d == np.float64:
            df[c] = df[c].astype(np.float32)
        elif d == object:
            try:
                nun = df[c].nunique(dropna=True)
                if 0 < nun < max(64, len(df) // 3):
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df


def mem_mb(df: pd.DataFrame) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return float("nan")


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    av, bv = a[m], b[m]
    # 상수 입력이면 상관계수가 정의되지 않는다 — 경고를 흘리지 말고 NaN 으로 명시한다
    if np.all(av == av[0]) or np.all(bv == bv[0]):
        return float("nan")
    if _scistats is not None:
        return float(_scistats.spearmanr(av, bv).statistic)
    ra = pd.Series(av).rank().to_numpy()
    rb = pd.Series(bv).rank().to_numpy()
    ra -= ra.mean(); rb -= rb.mean()
    den = math.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / den) if den > 0 else float("nan")


def nw_tstat(x: np.ndarray) -> Tuple[float, float]:
    """Newey-West(HAC) 평균 t통계 — 월간 수익률 자기상관 보정."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return (float(np.mean(x)) if n else float("nan"), float("nan"))
    mu = float(x.mean())
    e = x - mu
    L = max(1, int(math.floor(4 * (n / 100.0) ** (2 / 9))))
    s = float((e * e).mean())
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1)
        s += 2.0 * w * float((e[l:] * e[:-l]).mean())
    se = math.sqrt(max(s, 1e-18) / n)
    return mu, mu / se if se > 0 else float("nan")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S1] 캐시 금고(Depot)                                                                     ║
# ║                                                                                          ║
# ║  절대 1원칙의 구조적 보장:                                                                 ║
# ║   · 읽기 루트(기존 캐시)는 목록·판독만 한다. 쓰기 함수에 읽기 루트 경로가 들어오면          ║
# ║     예외를 던진다(가드레일).                                                              ║
# ║   · 쓰기 루트의 인덱스는 append-only JSONL 저널이 원천. 스냅샷 parquet 은 파생물이며       ║
# ║     교체 전 반드시 타임스탬프 백업.                                                       ║
# ║   · blob 은 내용해시 경로 — 같은 내용은 재기록조차 없음. 삭제 API 없음.                    ║
# ║   · 실행 전 기존 인덱스들의 (경로,크기) 지문을 떠 두고, 종료 시 축소·소실이 없는지          ║
# ║     실측 검증한다(C-보존 계약).                                                           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_IDX_COLS = ["uid", "scope", "domain", "key", "path", "fmt", "bytes", "sha1",
             "event_date", "source", "strategy", "note", "saved_at"]


def _gdrive_mount() -> Tuple[Optional[str], str]:
    """(드라이브 상 쓰기루트, 상태). Colab 마운트 → 데스크톱 동기화 → 실패 시 None."""
    if RIG["colab"]:
        try:
            from google.colab import drive as _gd        # type: ignore
            if not os.path.isdir("/content/drive/MyDrive"):
                _gd.mount("/content/drive", force_remount=False)
            if os.path.isdir("/content/drive/MyDrive"):
                return GDRIVE_WRITE_ROOT, "콜랩드라이브"
        except Exception as e:
            CON.warn(f"드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백")
        return None, "마운트실패"
    if GDRIVE_DESKTOP_OVERRIDE:
        return GDRIVE_DESKTOP_OVERRIDE, "수동지정"
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Google Drive", "My Drive"),
             os.path.join(home, "Google Drive", "내 드라이브"),
             os.path.join(home, "GoogleDrive")]
    if RIG["windows"]:
        # Google Drive for Desktop 은 보통 G: 로 붙지만 문자가 바뀔 수 있다 — 전 드라이브를 훑는다.
        for letter in "GHIJKLMNOPQRSTUVWXYZDEF":
            for leaf in ("내 드라이브", "My Drive"):
                cands.append(f"{letter}:\\{leaf}")
    else:
        cands += ["/Volumes/GoogleDrive/My Drive",
                  os.path.join(home, "Library", "CloudStorage")]
    for c in cands:
        try:
            if os.path.isdir(c):
                root = os.path.join(c, os.path.basename(GDRIVE_WRITE_ROOT))
                CON.say(f"구글드라이브 자동 인식: {c}")
                return root, "데스크톱동기화"
        except Exception:
            continue
    # 사용자가 GDRIVE_WRITE_ROOT 에 로컬 경로를 직접 넣은 경우 그대로 존중한다.
    # (콜랩 전용 경로 /content/... 는 로컬에서 의미가 없으므로 제외)
    if GDRIVE_WRITE_ROOT and not GDRIVE_WRITE_ROOT.startswith("/content/"):
        try:
            os.makedirs(GDRIVE_WRITE_ROOT, exist_ok=True)
            return GDRIVE_WRITE_ROOT, "지정경로(로컬)"
        except Exception:
            pass
    return None, "드라이브없음"


class Depot:
    def __init__(self):
        droot, self.drive_mode = _gdrive_mount()
        # 쓰기 루트: 드라이브가 있으면 드라이브, 없으면 로컬(경고와 함께)
        self.write_root = os.path.abspath(droot or os.path.expanduser("./scg_cache"))
        self.on_drive = droot is not None
        self.ns = {"공용": os.path.join(self.write_root, "shared"),
                   "전용": os.path.join(self.write_root, STRATEGY_TAG)}
        for p in self.ns.values():
            for sub in ("index", "index/_backup", "table", "blob", "report"):
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        # 읽기 루트(기존 캐시): 존재하는 것만, 쓰기 루트와 중복 제거 — 전부 읽기전용
        self.read_roots = self._discover_read_roots()
        self._idx_cache: Dict[str, pd.DataFrame] = {}
        self._lk = threading.RLock()
        self.stats: Counter = Counter()
        self._adopted: Dict[Tuple[str, str], str] = {}
        self._scan_roots_once()          # 기존 루트 1회 스캔: parquet·PDF·인덱스지문 동시 수집

    # ── 읽기 루트 탐색 ─────────────────────────────────────────────────────────────────
    def _discover_read_roots(self) -> List[str]:
        cands: List[str] = []
        base_drive = None
        if self.on_drive:
            base_drive = os.path.dirname(self.write_root)          # .../MyDrive
        for c in GDRIVE_READ_ROOTS_EXTRA:
            cands.append(c)
            if base_drive and c.startswith("/content/drive/MyDrive/"):
                cands.append(os.path.join(base_drive, c.split("/content/drive/MyDrive/")[1]))
        if base_drive and os.path.isdir(base_drive):
            try:                                    # MyDrive 1단계에서 cache/quant 류 자동 발견
                for fn in os.listdir(base_drive):
                    if re.search(r"cache|quant|캐시", fn, re.I):
                        cands.append(os.path.join(base_drive, fn))
            except Exception:
                pass
        for c in LOCAL_CACHE_DIRS:
            cands.append(os.path.expanduser(c))
        out, seen = [], set()
        wr = os.path.realpath(self.write_root)
        for c in cands:
            try:
                if not c or not os.path.isdir(c):
                    continue
                r = os.path.realpath(c)
                if r == wr or r in seen:
                    continue
                seen.add(r)
                out.append(r)
            except Exception:
                continue
        return out

    def _guard_write(self, path: str):
        rp = os.path.realpath(path)
        for ro in self.read_roots:
            if rp.startswith(ro + os.sep) or rp == ro:
                raise RuleBreak(f"[절대1원칙] 읽기전용 캐시 루트에 쓰기 시도: {path}")
        if not rp.startswith(os.path.realpath(self.write_root)):
            raise RuleBreak(f"[절대1원칙] 쓰기 루트 밖 기록 시도: {path}")

    def _scan_roots_once(self):
        """기존 캐시 루트를 '한 번만' 걷는다 — 대형 blob 트리를 테이블 조회 때마다
        재귀하면 드라이브 FUSE 에서 조회당 수 분이 날아간다. 여기서
        ① 재활용 후보 parquet ② 기존 PDF(참조등록용) ③ 인덱스 파일 지문(훼손 실측용)을
        동시에 수집한다. 스캔은 읽기(listdir/stat)만 한다."""
        self._foreign_parquets: List[Tuple[str, str]] = []
        self._foreign_fingerprint: Dict[str, int] = {}
        self._foreign_pdfs: Dict[str, str] = {}
        idx_names = ("index.jsonl", "common_index.jsonl", "private_index.jsonl",
                     "public_index.json", "private_index.json", "index.parquet",
                     "journal.jsonl", "snapshot.parquet")
        for root in self.read_roots:
            n_dirs, t0 = 0, time.time()
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                n_dirs += 1
                # 드라이브 FUSE 는 디렉터리 나열이 초 단위다 — 개수와 '시간' 양쪽으로 상한
                if n_dirs > 25000 or time.time() - t0 > 150:
                    CON.warn(f"기존 캐시 스캔 상한 도달({root}, {n_dirs:,}dir "
                             f"{time.time()-t0:.0f}s) — 일부만 인덱싱했습니다")
                    break
                for fn in files:
                    fl = fn.lower()
                    p = os.path.join(dirpath, fn)
                    if fl.endswith(".parquet"):
                        self._foreign_parquets.append((fl, p))
                    if fn in idx_names:
                        try:
                            self._foreign_fingerprint[p] = os.path.getsize(p)
                        except Exception:
                            pass
                    if fl.endswith(".pdf") and len(self._foreign_pdfs) < 400_000:
                        self._foreign_pdfs.setdefault(os.path.splitext(fn)[0], p)
        if self.read_roots:
            CON.say(f"기존 캐시 스캔: parquet {len(self._foreign_parquets):,} · "
                    f"PDF {len(self._foreign_pdfs):,} · 인덱스 지문 "
                    f"{len(self._foreign_fingerprint):,} (전부 읽기전용)")

    def verify_foreign_untouched(self) -> Tuple[bool, str]:
        bad = []
        for p, sz in self._foreign_fingerprint.items():
            try:
                now = os.path.getsize(p) if os.path.exists(p) else -1
            except Exception:
                continue
            if now < sz:              # append 로 커지는 건 정상, 줄거나 사라지면 훼손
                bad.append(f"{p} {sz}→{now}")
        if bad:
            return False, " / ".join(bad[:3])
        return True, f"기존 인덱스 {len(self._foreign_fingerprint)}개 모두 무손상(감소·소실 0건)"

    # ── 인덱스(저널) ───────────────────────────────────────────────────────────────────
    def _journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "journal.jsonl")

    def _register(self, scope: str, rec: dict):
        rec = {**{c: None for c in _IDX_COLS}, **rec}
        rec["scope"] = scope
        rec["strategy"] = STRATEGY_TAG if scope == "전용" else ""
        rec["saved_at"] = _now_iso()
        with self._lk:
            jsonl_append(self._journal(scope), [rec])
            self._idx_cache.pop(scope, None)
        self.stats[f"등재:{scope}"] += 1

    def index_frame(self, scope: str) -> pd.DataFrame:
        with self._lk:
            if scope in self._idx_cache:
                return self._idx_cache[scope]
        rows = jsonl_read(self._journal(scope))
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_IDX_COLS)
        for c in _IDX_COLS:
            if c not in df.columns:
                df[c] = None
        if len(df):
            df = df.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        with self._lk:
            self._idx_cache[scope] = df
        return df

    def snapshot_indexes(self):
        """저널 → 사람이 보기 쉬운 스냅샷 parquet. 기존 스냅샷은 백업 후 교체."""
        for scope in ("공용", "전용"):
            df = self.index_frame(scope)
            snap = os.path.join(self.ns[scope], "index", "snapshot.parquet")
            if os.path.exists(snap):
                bak = os.path.join(self.ns[scope], "index", "_backup",
                                   f"snapshot.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
                try:
                    shutil.copy2(snap, bak)
                except Exception:
                    CON.warn(f"스냅샷 백업 실패 — 안전을 위해 {scope} 스냅샷 교체를 건너뜁니다"
                             " (저널이 원천이므로 유실 없음)")
                    continue
            try:
                write_atomic_parquet(df.astype(str), snap)
            except Exception as e:
                CON.warn(f"스냅샷 기록 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음")

    # ── 테이블 ─────────────────────────────────────────────────────────────────────────
    def table_save(self, name: str, df: pd.DataFrame, scope: str = "공용",
                   domain: str = "table", source: str = "", note: str = "") -> Optional[str]:
        if df is None:
            return None
        path = os.path.join(self.ns[scope], "table", f"{name}.parquet")
        self._guard_write(path)
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception:
                path = os.path.join(self.ns[scope], "table",
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
                CON.warn(f"기존 {name} 백업 실패 — 덮어쓰지 않고 리비전 파일로 저장")
        try:
            write_atomic_parquet(df, path)
        except Exception as e:
            CON.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._register(scope, dict(uid=h1("table", scope, name), domain=domain, key=name,
                                   path=os.path.relpath(path, self.write_root), fmt="parquet",
                                   bytes=os.path.getsize(path), source=source,
                                   note=note or f"rows={len(df)}"))
        FLOW.io("출", "드라이브" if self.on_drive else "로컬", f"표:{name}", df,
                src=f"{scope}인덱스")
        return path

    def table_load(self, name: str, scope: str = "공용",
                   foreign_patterns: Optional[List[str]] = None,
                   need_cols: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        """쓰기 루트(내 것) → 반대 스코프 → 기존 읽기 루트 순으로 탐색(시간 절약).
        foreign_patterns: 기존 캐시에서 찾아볼 파일명 패턴(소문자 부분일치)."""
        for sc in ([scope, "전용" if scope == "공용" else "공용"]):
            p = os.path.join(self.ns[sc], "table", f"{name}.parquet")
            d = read_parquet_soft(p)
            if d is not None and len(d):
                if need_cols and not set(need_cols).issubset(d.columns):
                    CON.warn(f"캐시 {name} 의 스키마가 예전 버전입니다(필요 컬럼 누락) — "
                             f"무시하고 새로 만듭니다(기존 파일은 그대로 둡니다).")
                    continue
                FLOW.io("입", "드라이브" if self.on_drive else "로컬", f"표:{name}", d, src=f"쓰기루트/{sc}")
                self.stats["캐시적중:쓰기루트"] += 1
                return d
        pats = [name.lower()] + [p.lower() for p in (foreign_patterns or [])]
        for fl, path in self._foreign_parquets:
            if "_backup" in path:
                continue
            if any(pt in fl for pt in pats):
                d = read_parquet_soft(path)
                if d is None or not len(d):
                    continue
                if need_cols and not set(need_cols).issubset(d.columns):
                    continue
                CON.ok(f"기존 캐시 재활용: {name} ← {path} ({len(d):,}행) — 읽기전용")
                FLOW.io("입", "기존캐시", f"표:{name}", d, src=os.path.dirname(path))
                self.stats["캐시적중:기존루트"] += 1
                return d
        return None

    # ── blob (PDF 등 원본) ─────────────────────────────────────────────────────────────
    def blob_save(self, domain: str, key: str, data: bytes, ext: str,
                  source: str = "", scope: str = "공용") -> Optional[str]:
        if not data:
            return None
        sha = h1b(data)
        path = os.path.join(self.ns[scope], "blob", domain, sha[:2], f"{sha}.{ext.lstrip('.')}")
        self._guard_write(path)
        if not os.path.exists(path):                      # 존재하면 절대 다시 쓰지 않는다
            try:
                write_atomic_bytes(path, data)
            except Exception as e:
                CON.warn(f"blob 저장 실패({type(e).__name__}): {key}")
                return None
        else:
            self.stats["blob중복회피"] += 1
        uid = h1("blob", domain, key, sha)
        self._register(scope, dict(uid=uid, domain=domain, key=str(key),
                                   path=os.path.relpath(path, self.write_root),
                                   fmt=ext, bytes=len(data), sha1=sha, source=source))
        return uid

    def blob_bytes(self, domain: str, key: str) -> Optional[bytes]:
        idx = self.index_frame("공용")
        if len(idx):
            m = idx[(idx["domain"] == domain) & (idx["key"].astype(str) == str(key))]
            for _, r in m.iterrows():
                p = os.path.join(self.write_root, str(r["path"]))
                if os.path.exists(p):
                    try:
                        return open(p, "rb").read()
                    except Exception:
                        pass
        p = self._adopted.get((domain, str(key)))
        if p and os.path.exists(p):
            try:
                return open(p, "rb").read()
            except Exception:
                pass
        return None

    # ── 기존 PDF 등 참조 등록(adopt) — 이동/개명/삭제 없이 경로만 기억 ────────────────────
    def scan_adopt_pdfs(self, cap: int = 400_000):
        for key, p in self._foreign_pdfs.items():          # 1회 스캔 결과 재사용
            self._adopted.setdefault(("research_pdf", key), p)
        n_dirs, t0 = 0, time.time()
        for dirpath, dirs, files in os.walk(self.write_root):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            n_dirs += 1
            if n_dirs > 25000 or len(self._adopted) >= cap or time.time() - t0 > 150:
                break
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    self._adopted.setdefault(("research_pdf", os.path.splitext(fn)[0]),
                                             os.path.join(dirpath, fn))
        CON.say(f"기존 PDF 참조등록 {len(self._adopted):,}건 "
                f"(이동·개명·삭제 없음, 경로만 기억)")
        self.stats["PDF참조등록"] = len(self._adopted)

    def audit_table(self):
        rows = []
        for sc in ("공용", "전용"):
            idx = self.index_frame(sc)
            nb = pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum() if len(idx) else 0
            rows.append([f"{sc} ({os.path.basename(self.ns[sc])})", f"{len(idx):,}",
                         f"{nb/1e9:.2f} GB", os.path.relpath(self._journal(sc), self.write_root)])
        CON.grid(rows, ["인덱스", "등재 항목", "용량", "저널(append-only)"],
                 ["l", "r", "r", "l"], title="캐시 금고 감사")
        CON.grid([[r, "읽기전용"] for r in self.read_roots] or [["(없음)", ""]],
                 ["기존 캐시 루트(재활용)", "권한"], ["l", "l"])
        if self.stats:
            CON.grid([[k, f"{v:,}"] for k, v in sorted(self.stats.items())],
                     ["캐시 이벤트", "횟수"], ["l", "r"])
        okk, msg = self.verify_foreign_untouched()
        (CON.ok if okk else CON.err)(f"절대1원칙 실측: {msg}")
        if not okk:
            raise RuleBreak("기존 인덱스 훼손이 감지되었습니다 — 즉시 중단")


DEPOT: Optional[Depot] = None


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-g] HTTP 계층 — 세션 재사용 · 스로틀 · 재시도 · 한국어 인코딩 자동판별                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TL = threading.local()
HTTP_TALLY: Counter = Counter()


def _sess() -> requests.Session:
    s = getattr(_TL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9",
                          "Accept": "*/*", "Connection": "keep-alive"})
        try:
            from requests.adapters import HTTPAdapter
            ad = HTTPAdapter(pool_connections=max(8, N_IO_THREADS),
                             pool_maxsize=max(16, N_IO_THREADS * 2))
            s.mount("http://", ad); s.mount("https://", ad)
        except Exception:
            pass
        _TL.s = s
    return s


_HANGUL_RE = re.compile(r"[가-힣]")


def _readable_kr(t: str) -> float:
    head = t[:5000]
    return len(_HANGUL_RE.findall(head)) - 4.0 * head.count("\ufffd")


def decode_kr(content: bytes, declared: Optional[str]) -> str:
    """네이버 등은 본문이 EUC-KR 인데 헤더는 utf-8 이라 주장한다 — 실제 가독성으로 판별."""
    best, best_s = "", -1e9
    for enc in [declared, "utf-8", "euc-kr", "cp949"]:
        if not enc:
            continue
        try:
            t = content.decode(enc, errors="replace")
        except Exception:
            continue
        sc = _readable_kr(t)
        if sc > best_s:
            best, best_s = t, sc
        if sc > 40:
            break
    return best


def fetch(url: str, source: str = "generic", params: Optional[dict] = None,
          as_bytes: bool = False, tries: int = 3, timeout: float = 25.0,
          headers: Optional[dict] = None, referer: Optional[str] = None,
          on_attempt: Optional[Callable[[], None]] = None) -> Optional[Any]:
    hd = dict(headers or {})
    if referer:
        hd["Referer"] = referer
    last = ""
    for k in range(tries):
        THROTTLE.wait(source)
        if on_attempt:
            on_attempt()
        try:
            r = _sess().get(url, params=params, headers=hd, timeout=timeout)
            HTTP_TALLY[f"{source}:{r.status_code}"] += 1
            if r.status_code == 200:
                return r.content if as_bytes else decode_kr(r.content, r.encoding)
            if r.status_code in (429, 503):
                time.sleep(min(30.0, 2.0 * (2 ** k)) + random.random())
            elif r.status_code in (401, 403):
                time.sleep(1.5 * (k + 1))
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = type(e).__name__
            HTTP_TALLY[f"{source}:EXC"] += 1
            time.sleep(min(10.0, 1.6 ** k) + random.random() * 0.3)
    HTTP_TALLY[f"{source}:FAIL"] += 1
    CON.debug(f"수신 실패[{source}] {last}: {url[:90]}")
    return None


def fetch_json(url: str, source: str = "generic", **kw) -> Optional[Any]:
    t = fetch(url, source=source, **kw)
    if t is None:
        return None
    if isinstance(t, (bytes, bytearray)):
        t = t.decode("utf-8", "replace")
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


def soup(html: str) -> Optional[BeautifulSoup]:
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def http_report():
    per: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_TALLY.items():
        src, code = k.split(":", 1)
        per[src][code] += v
    rows = []
    for src, c in sorted(per.items()):
        tot = sum(c.values()); ok = c.get("200", 0)
        bad = tot - ok
        rows.append([src, f"{tot:,}", f"{ok:,}", f"{(ok/tot*100 if tot else 0):.0f}%",
                     f"{bad:,}", ", ".join(f"{k}×{v}" for k, v in c.items() if k != "200")[:40]])
    if rows:
        CON.grid(rows, ["소스", "요청", "성공", "성공률", "실패", "상세"],
                 ["l", "r", "r", "r", "r", "l"], title="HTTP 사용량")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S0-h] 실시간 쿼터 매니저 — 고정예산이 아니라 '실사용량 + 서버 신호'로 운전한다             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
class Quota:
    """소스별 일일 사용량을 드라이브에 영속화. 서버의 한도초과 신호가 유일한 진짜 상한이다.
    (사용자 지시: 19,000 같은 고정치를 미리 깎지 말고 남은 호출량을 실시간으로 체크할 것)"""

    OFFICIAL = {"dart": 20000}          # 공지된 참고치 — 표시용. 정지는 서버 신호로만 한다.

    def __init__(self):
        self.used: Counter = Counter()
        self.dead: Dict[str, str] = {}
        self._lk = threading.Lock()
        self._loaded = False

    def _path(self) -> Optional[str]:
        if DEPOT is None:
            return None
        return os.path.join(DEPOT.ns["공용"], "index",
                            f"quota_{_dt.date.today():%Y%m%d}.json")

    def load(self):
        p = self._path()
        if p and os.path.exists(p):
            try:
                d = json.loads(open(p, encoding="utf-8").read())
                self.used.update({k: int(v) for k, v in d.get("used", {}).items()})
                CON.say(f"오늘 기존 사용량 이어받음: "
                        + ", ".join(f"{k}={v:,}" for k, v in self.used.items()))
            except Exception:
                pass
        self._loaded = True

    def _save(self):
        p = self._path()
        if p:
            try:
                write_atomic_text(p, json.dumps({"used": dict(self.used)}))
            except Exception:
                pass

    def spend(self, source: str, n: int = 1) -> bool:
        with self._lk:
            if source in self.dead:
                return False
            self.used[source] += n
            if self.used[source] % 300 == 0:
                self._save()
                lim = self.OFFICIAL.get(source)
                if lim:
                    CON.debug(f"{source} 호출 사용량 {self.used[source]:,} / 공지한도 {lim:,} "
                              f"(잔여추정 {max(0, lim - self.used[source]):,})")
        return True

    def kill(self, source: str, reason: str):
        with self._lk:
            if source not in self.dead:
                self.dead[source] = reason
                self._save()
                CON.warn(f"[{source}] 서버 한도 신호 감지 — 이 소스만 정지하고 받은 만큼 저장합니다. "
                         f"사유: {reason}. 내일 재실행하면 이어받습니다.")

    def alive(self, source: str) -> bool:
        return source not in self.dead

    def report(self):
        rows = []
        for src in sorted(set(list(self.used) + list(self.dead))):
            lim = self.OFFICIAL.get(src)
            rows.append([src, f"{self.used.get(src, 0):,}",
                         f"{lim:,}" if lim else "-",
                         f"{max(0, lim - self.used.get(src, 0)):,}" if lim else "-",
                         self.dead.get(src, "정상")])
        if rows:
            CON.grid(rows, ["소스", "오늘 사용", "공지한도", "잔여(추정)", "상태"],
                     ["l", "r", "r", "r", "l"], title="API 호출 쿼터(실시간)")
        self._save()


QUOTA = Quota()


class CollectDeadline:
    """수집 시간예산 — 초과 순간 모든 수집 루프가 스스로 멈추고, 파이프라인은
    '그때까지 모인 데이터'로 중간 백테스트 결과를 낸다. (백테스트 자체는 금방이다)"""

    def __init__(self, hours: float):
        self.budget_s = float(hours) * 3600.0
        self.t0: Optional[float] = None
        self.tripped = False
        self._warned = False

    def start(self):
        self.t0 = time.time()
        CON.say(f"수집 시간예산 시작: {self.budget_s/3600:.1f}시간 "
                f"(초과 시 그 시점까지의 데이터로 중간 결과를 냅니다)")

    def remaining_s(self) -> float:
        if self.t0 is None:
            return self.budget_s
        return self.budget_s - (time.time() - self.t0)

    def over(self, where: str = "") -> bool:
        if self.t0 is None:
            return False
        if self.remaining_s() <= 0:
            self.tripped = True
            if not self._warned:
                self._warned = True
                CON.warn(f"⏰ 수집 시간예산({self.budget_s/3600:.1f}h) 소진 — 이후 신규 수집을 "
                         f"멈추고 지금까지 수집분으로 중간 백테스트를 진행합니다"
                         + (f" (지점: {where})" if where else ""))
            return True
        return False


DEADLINE = CollectDeadline(COLLECT_HOURS_BUDGET)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-a] 시장 데이터 허브 — '날짜 단면(cross-section)' 수집                                   ║
# ║                                                                                          ║
# ║  ★ 이 설계가 이 파일에서 가장 중요한 성능/정확성 결정이다.                                  ║
# ║                                                                                          ║
# ║  월 리밸런싱 백테스트에 실제로 필요한 것은 '전 종목의 전체 일별 시계열'이 아니라             ║
# ║  '몇 개 날짜의 전 종목 단면'뿐이다:                                                        ║
# ║      · 신호일(월말) 120개  · 각 신호일의 +20/+60/+120 거래일(IC 지평)                      ║
# ║    → 중복 제거 후 약 400~500개 날짜.                                                      ║
# ║                                                                                          ║
# ║  pykrx 의 get_market_cap(date, market="ALL") 은 한 번의 호출로 그 날짜의                   ║
# ║  전 종목 [종가·시가총액·상장주식수·거래량·거래대금] 을 반환한다.                            ║
# ║      종목별 시계열 방식: 5,400종목 × 1콜 = 5,400콜  (수 시간)                              ║
# ║      날짜 단면 방식:      480날짜 × 1콜 =   480콜  (수 분)     ← 10배 이상 절감            ║
# ║                                                                                          ║
# ║  부수효과가 더 중요하다:                                                                  ║
# ║   · 생존자편향이 구조적으로 사라진다 — 스냅샷에는 '그 날 실제로 상장돼 거래된 종목'만        ║
# ║     들어 있다. 상장/폐지 목록의 정확도에 의존하지 않는다(목록은 교차검증용으로만 쓴다).      ║
# ║   · 시가총액이 매 신호일에 실측으로 존재한다 → 시총 하위 1000 비교전략이 정확해진다.        ║
# ║   · 상장주식수가 함께 오므로 액면분할/무상증자를 탐지해 수익률을 보정할 수 있다.             ║
# ║                                                                                          ║
# ║  캐시: 날짜 단면은 전략과 무관한 원본이므로 **공용 인덱스**에 적재한다.                     ║
# ║        다른 전략이 같은 날짜를 다시 받을 필요가 없다(연 단위 파티션 parquet).               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
XSEC_COLS = ["date", "code", "name", "close", "volume", "value", "mktcap",
             "shares", "market"]
XSEC_TABLE = "xsec_daily_krx"          # 공용 인덱스 테이블 접두어 (연 단위 파티션)
XSEC_WORKERS = 2                       # KRX 는 계정 단위로 차단한다 — 병렬을 낮게 유지
RET_TABLE = "krx_period_return"        # 구간 수익률(수정주가·상폐 포함) 공용 캐시


class _PykrxGate:
    """pykrx 호출의 유일한 통로 — 명시 로그인 1회 + 직렬화 + 스로틀 + 실패 계수.

    ★ 다른 파이프라인에서 검증된 방식을 그대로 가져왔다. pykrx 는 import 시점에
      로그인을 시도하는데, 그때 실패하면 이후 모든 호출이 조용히 빈 결과를 준다.
      여기서 get_auth_session() 으로 세션을 '명시적으로' 잡고 결과를 보고한다.
      또한 모든 호출을 직렬화해 중복로그인(CD011)으로 서로를 밀어내는 것을 막는다.
    """

    def __init__(self):
        self._lk = threading.RLock()
        self.authed = False
        self.warm = False
        self.calls = 0
        self.fails = 0
        self.note = ""
        self._t = 0.0

    def warmup(self) -> bool:
        if pykrx_stock is None:
            self.note = IMPORT_ERR.get("pykrx", "import 실패")
            return False
        with self._lk:
            if self.warm:
                return self.authed
            self.warm = True
            has_cred = bool(os.environ.get("KRX_ID") and os.environ.get("KRX_PW"))
            try:
                from pykrx.website.comm.auth import get_auth_session   # type: ignore
                s = get_auth_session()
                self.authed = s is not None and bool(getattr(s, "is_authenticated", True))
                self.note = "세션 확보" if self.authed else "세션 인증 실패"
            except ImportError:
                self.authed = True          # 구버전 pykrx = 로그인 개념 자체가 없음
                self.note = "구버전(로그인 불필요)"
            except Exception as e:
                self.authed = False
                self.note = f"{type(e).__name__}: {e}"[:60]
            self._t = time.time()
            if has_cred and self.authed:
                CON.ok("KRX 세션 확보 — pykrx 호출을 직렬화해 중복로그인(CD011) 충돌을 막습니다")
            elif has_cred:
                CON.warn(f"KRX 자격증명은 있으나 세션 인증 실패({self.note}) — "
                         f"pykrx 경로는 건너뛰고 무인증 벌크 소스로 진행합니다")
            else:
                CON.say("KRX 자격증명 미입력 — 무인증 벌크 소스로 진행합니다(정확도 동일)")
            return self.authed

    def call(self, fn: Callable, *a, **k):
        if pykrx_stock is None:
            return None
        with self._lk:
            if self.authed and time.time() - self._t > 45 * 60:
                try:
                    from pykrx.website.comm.auth import get_auth_session   # type: ignore
                    get_auth_session()
                    self._t = time.time()
                except Exception:
                    pass
            THROTTLE.wait("krx")
            QUOTA.spend("krx")
            self.calls += 1
            try:
                return fn(*a, **k)
            except Exception as e:
                self.fails += 1
                if self.fails <= 3:      # 처음 몇 건은 사유를 보여 준다(조용한 실패 방지)
                    CON.debug(f"pykrx 실패({type(e).__name__}: {e})"[:150])
                return None


PYKRX = _PykrxGate()


def _pykrx_call(fn: Callable, *a, **k):
    return PYKRX.call(fn, *a, **k)


class KrxMarketplace:
    """KRX 정보데이터시스템(data.krx.co.kr) 세션 — **보강용 2순위 소스**.

    ★ 회로차단기(circuit breaker)가 이 클래스의 핵심이다.
      이전 버전은 '로그인 성공' 판정이 느슨해 거짓 성공을 반환했고, 데이터 요청이
      로그인 HTML 을 받을 때마다 재로그인 → 재시도 → 재실패를 월마다 6회씩 반복해
      24분을 실패에만 썼다. 이제 연속 실패가 임계에 닿으면 **이 소스를 영구 비활성화**하고
      즉시 pykrx 로 넘긴다. 되지 않는 것을 계속 두드리지 않는다.
    """
    HOME = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201"
    LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    DATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    MAX_FAILS = 3                       # 연속 실패 임계 — 넘으면 영구 비활성

    def __init__(self, user: str, pw: str):
        self.user, self.pw = user or "", pw or ""
        self.state = "미시도"
        self.fails = 0
        self.disabled = not bool(user)
        self.reason = "ID 미입력" if not user else ""
        self._lk = threading.RLock()
        self._t_login = 0.0

    def login(self) -> bool:
        with self._lk:
            if self.disabled:
                return False
            fetch(self.HOME, source="krx")               # 쿠키 웜업(없으면 POST 거절)
            fetch(self.LOGIN_PAGE, source="krx")
            body = {"mbrId": self.user, "pw": self.pw, "telNo": "", "mbrNm": "",
                    "certType": "", "di": ""}
            for extra in ({}, {"skipDup": "Y"}):        # 중복로그인(CD011) 시 기존 세션 정리
                THROTTLE.wait("krx")
                try:
                    r = _sess().post(self.LOGIN_POST, data={**body, **extra},
                                     headers={"Referer": self.LOGIN_PAGE,
                                              "X-Requested-With": "XMLHttpRequest"},
                                     timeout=20)
                    txt = (r.text or "")[:1200]
                except Exception as e:
                    self.state = f"접속실패:{type(e).__name__}"
                    return False
                if re.search(r"CD011|중복\s*로그인", txt):
                    continue
                # ★ 성공을 '실패 문자열의 부재'로 판정하지 않는다 — 그 느슨함이 거짓 성공의
                #   원인이었다. 로그인 폼이 그대로 돌아왔는지를 적극적으로 확인한다.
                looks_like_form = bool(re.search(r"login\.jsp|mbrId|비밀번호|아이디를", txt))
                looks_bad = bool(re.search(r"실패|불일치|오류|error|fail|잠금|탈퇴", txt, re.I))
                if not looks_like_form and not looks_bad:
                    self.state, self._t_login = "로그인성공", time.time()
                    CON.ok("KRX 정보데이터시스템 로그인 성공")
                    return True
            self.state = "로그인실패"
            return False

    def _kill(self, why: str):
        if not self.disabled:
            self.disabled = True
            self.reason = why
            CON.warn(f"KRX 정보데이터시스템 보강을 중단합니다 — {why}. "
                     f"시세·시총은 pykrx 단면 수집으로 계속 진행합니다(정확도 동일). "
                     f"ID/PW 를 다시 확인하거나, 브라우저에서 data.krx.co.kr 로그아웃 후 "
                     f"재실행하면 이 소스가 다시 쓰입니다.")

    def jsondata(self, bld: str, **params) -> Optional[dict]:
        if self.disabled:
            return None
        if self.state != "로그인성공":
            if not self.login():
                self.fails += 1
                if self.fails >= self.MAX_FAILS:
                    self._kill(f"로그인 {self.fails}회 연속 실패")
                return None
        if time.time() - self._t_login > 45 * 60:       # 세션 만료 선제 갱신
            self.login()
        THROTTLE.wait("krx")
        QUOTA.spend("krx")
        try:
            r = _sess().post(self.DATA, data={"bld": bld, **params},
                             headers={"Referer": self.HOME,
                                      "X-Requested-With": "XMLHttpRequest"}, timeout=25)
            txt = (r.text or "").lstrip()
        except Exception:
            txt = ""
        if txt.startswith("{"):
            self.fails = 0
            try:
                return json.loads(txt)
            except Exception:
                return None
        # JSON 이 아니면(로그인 HTML/차단 페이지) 실패로 계수 — 재시도 루프를 만들지 않는다
        self.fails += 1
        self.state = "세션무효"
        if self.fails >= self.MAX_FAILS:
            self._kill(f"JSON 대신 HTML 응답 {self.fails}회 연속")
        return None

    def xsec(self, day: pd.Timestamp) -> Optional[pd.DataFrame]:
        js = self.jsondata("dbms/MDC/STAT/standard/MDCSTAT01501",
                           mktId="ALL", trdDd=f"{day:%Y%m%d}", share="1", money="1",
                           csvxls_isNo="false")
        rows = (js or {}).get("OutBlock_1") or []
        if not rows:
            return None

        def _n(x):
            try:
                return float(str(x).replace(",", ""))
            except Exception:
                return np.nan

        rec = []
        for r in rows:
            c = code6(r.get("ISU_SRT_CD"))
            if not c:
                continue
            rec.append((c, _n(r.get("TDD_CLSPRC")), _n(r.get("ACC_TRDVOL")),
                        _n(r.get("ACC_TRDVAL")), _n(r.get("MKTCAP")),
                        _n(r.get("LIST_SHRS")), str(r.get("MKT_NM", ""))))
        if not rec:
            return None
        d = pd.DataFrame(rec, columns=["code", "close", "volume", "value",
                                       "mktcap", "shares", "market"])
        d.insert(0, "date", pd.Timestamp(day).normalize())
        return d


KRXM = KrxMarketplace(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW)


def _xsec_pykrx(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """1순위: pykrx 전종목 단면. get_market_cap 한 번에 종가·시총·주식수·거래대금이 온다."""
    if pykrx_stock is None:
        return None
    d8 = f"{day:%Y%m%d}"
    cap = None
    for fname in ("get_market_cap", "get_market_cap_by_ticker"):   # 버전별 이름 차이 흡수
        fn = getattr(pykrx_stock, fname, None)
        if fn is None:
            continue
        cap = _pykrx_call(fn, d8, market="ALL")
        if cap is not None and len(cap):
            break
        cap = None
    if cap is None or not len(cap):
        return None
    cap = cap.reset_index()
    lc = {str(c): c for c in cap.columns}
    tick = lc.get("티커") or lc.get("ticker") or cap.columns[0]
    out = pd.DataFrame({"code": cap[tick].map(code6)})

    def _col(*names):
        for n in names:
            if n in lc:
                return pd.to_numeric(cap[lc[n]], errors="coerce")
        return pd.Series(np.nan, index=cap.index)

    out["close"] = _col("종가")
    out["volume"] = _col("거래량")
    out["value"] = _col("거래대금")
    out["mktcap"] = _col("시가총액")
    out["shares"] = _col("상장주식수")
    out["market"] = ""
    out = out.dropna(subset=["code"])
    out = out[(out["mktcap"] > 0) | (out["close"] > 0)]
    if not len(out):
        return None
    out.insert(0, "date", pd.Timestamp(day).normalize())
    return out


def _xsec_fdr(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """3순위: FDR 상장목록의 시총 스냅샷(당일에 한함). 과거 날짜는 지원하지 않으므로
    '오늘' 근처에서만 의미가 있다 — 최근월 결손을 메우는 용도."""
    if fdr is None or (pd.Timestamp.today().normalize() - pd.Timestamp(day)).days > 5:
        return None
    try:
        d = fdr.StockListing("KRX")
    except Exception:
        return None
    if d is None or not len(d):
        return None
    lc = {str(c).lower(): c for c in d.columns}
    if "marcap" not in lc and "close" not in lc:
        return None
    out = pd.DataFrame({
        "code": d[lc.get("code", lc.get("symbol", d.columns[0]))].map(code6),
        "close": pd.to_numeric(d[lc["close"]], errors="coerce") if "close" in lc else np.nan,
        "volume": pd.to_numeric(d[lc["volume"]], errors="coerce") if "volume" in lc else np.nan,
        "value": np.nan,
        "mktcap": pd.to_numeric(d[lc["marcap"]], errors="coerce") if "marcap" in lc else np.nan,
        "shares": pd.to_numeric(d[lc["stocks"]], errors="coerce") if "stocks" in lc else np.nan,
        "market": d[lc["market"]].astype(str) if "market" in lc else "",
    }).dropna(subset=["code"])
    if not len(out):
        return None
    out.insert(0, "date", pd.Timestamp(day).normalize())
    return out


# ── 무인증 벌크 소스 ────────────────────────────────────────────────────────────────────────
#  ★ pykrx 는 import 시점에 KRX 로그인을 하므로 그것이 막히면 통째로 죽는다. 그때 대안이
#    없으면 파이프라인 전체가 0행으로 멈춘다(실제로 그렇게 멈췄다). 그래서 **인증도
#    라이브러리도 필요 없는 HTTP 벌크 소스**를 1순위에 둔다.
#    marcap 은 연 단위 CSV 한 개에 그 해 전 종목·전 거래일의
#    [종가·거래량·거래대금·시가총액·상장주식수]가 들어 있다 → 10년치가 파일 10개.
#    실측 확인(2026-08): 형식은 parquet, 브랜치는 master 만 유효(csv/csv.gz/main 은 404).
#    1995~2026 전 연도 존재 · 연 18MB · 상장폐지 종목이 '거래되던 날짜에' 그대로 포함
#    (= 생존자편향 없음) · Marcap == Close×Stocks 정확 일치 · 분할일에 Stocks 재계산.
MARCAP_URLS = [
    "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet",
    "https://media.githubusercontent.com/media/FinanceData/marcap/master/data/marcap-{y}.parquet",
]
#  FDR 이 실제로 읽는 GitHub 캐시를 **라이브러리를 거치지 않고 직접** 읽는다.
#  (fdr.StockListing 은 최신영업일을 알아내려 data.krx.co.kr 을 찌르는데, 로그인 벽에
#   막히면 CSV 는 멀쩡한데도 통째로 실패한다. 다른 파이프라인에서 검증된 우회 경로다.)
FDR_CACHE_URL = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                 "refs/heads/{br}/data/{kind}/{date}.csv")


def fdr_cache_csv(kind: str, back_days: int = 21,
                  asof: Optional[pd.Timestamp] = None) -> Optional[pd.DataFrame]:
    """영업일 CSV만 존재하므로 기준일부터 거꾸로 훑는다. 인증 불필요."""
    base = (asof or pd.Timestamp.today()).normalize()
    for i in range(back_days):
        d = base - pd.Timedelta(i, "D")
        if d.weekday() >= 5:
            continue
        for br in ("master", "main"):
            raw = fetch(FDR_CACHE_URL.format(br=br, kind=kind, date=f"{d:%Y-%m-%d}"),
                        source="generic", as_bytes=True, tries=1, timeout=30)
            if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
                continue
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", low_memory=False,
                                 dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                        "MarketId": str, "Market": str, "ISU_CD": str,
                                        "Unnamed: 0": str})
            except Exception:
                continue
            # ★ index_col=0 을 무조건 주면 안 된다. listing 은 이름없는 인덱스가 있지만
            #   delisting 은 없을 수 있어, 그때 첫 실컬럼(Symbol)이 인덱스로 먹혀
            #   상장폐지 종목이 통째로 사라진다 — 그게 곧 생존자편향이다.
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                CON.debug(f"FDR GitHub 캐시 적중: {kind} @ {d:%Y-%m-%d} ({len(df):,}행)")
                return df
    return None


def _norm_xsec_frame(d: pd.DataFrame) -> Optional[pd.DataFrame]:
    """어느 소스에서 왔든 XSEC_COLS 스키마로 정규화한다(컬럼명 표기 차이 흡수)."""
    if d is None or not len(d):
        return None
    lc = {str(c).strip().lower(): c for c in d.columns}

    def pick(*names, numeric=True):
        for n in names:
            if n in lc:
                v = d[lc[n]]
                return pd.to_numeric(v, errors="coerce") if numeric else v.astype(str)
        return pd.Series(np.nan if numeric else "", index=d.index)

    code_c = lc.get("code") or lc.get("symbol") or lc.get("종목코드") or lc.get("티커")
    if code_c is None:
        return None
    out = pd.DataFrame({"code": d[code_c].map(code6)})
    out["close"] = pick("close", "종가")
    out["volume"] = pick("volume", "거래량")
    out["value"] = pick("amount", "거래대금", "value")
    out["mktcap"] = pick("marcap", "시가총액", "mktcap", "marketcap")
    out["shares"] = pick("stocks", "상장주식수", "shares", "listedshares")
    out["market"] = pick("market", "시장구분", numeric=False)
    out["name"] = pick("name", "종목명", "회사명", numeric=False)   # PIT 종목명(그 날짜 기준)
    date_c = lc.get("date") or lc.get("날짜")
    out.insert(0, "date", ts_col(d[date_c]) if date_c else pd.NaT)
    out = out.dropna(subset=["code"])
    out = out[(out["close"] > 0) | (out["mktcap"] > 0)]
    return out if len(out) else None


def bulk_marcap_year(year: int) -> Optional[pd.DataFrame]:
    """연 단위 벌크 다운로드 — 그 해 전 거래일 × 전 종목 단면을 한 번에."""
    for tmpl in MARCAP_URLS:
        raw = fetch(tmpl.format(y=year), source="generic", as_bytes=True, tries=2,
                    timeout=240)
        if not raw or len(raw) < 5000:
            continue
        try:
            if raw[:4] == b"PAR1":
                d = pd.read_parquet(io.BytesIO(raw))
            else:
                if raw[:2] == b"\x1f\x8b":
                    import gzip
                    raw = gzip.decompress(raw)
                d = pd.read_csv(io.BytesIO(raw), low_memory=False)
        except Exception as e:
            CON.debug(f"marcap {year} 파싱 실패({type(e).__name__})")
            continue
        out = _norm_xsec_frame(d)
        if out is not None and out["date"].notna().any():
            CON.ok(f"벌크 단면 확보: {year}년 {len(out):,}행 · "
                   f"거래일 {out['date'].nunique():,}일 · 종목 {out['code'].nunique():,} "
                   f"(무인증 1회 다운로드)")
            return out
    return None


def _xsec_fdrcache(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """일 단위 무인증 캐시 CSV(FDR 공개 캐시) — 벌크가 못 덮는 최근분 보완.

    ★ 이 캐시는 최근 몇 달치만 존재한다(과거 날짜는 404). 그래서 벌크(marcap)가
      1순위이고 이건 '최근분 보완'용이다. 파일은 UTF-8 BOM + 무명 인덱스 컬럼.
    """
    d = fdr_cache_csv("listing/krx", back_days=5, asof=pd.Timestamp(day))
    if d is None:
        return None
    out = _norm_xsec_frame(d)
    if out is None:
        return None
    out["date"] = pd.Timestamp(day).normalize()     # 이 캐시엔 날짜 컬럼이 없다(파일명이 날짜)
    return out


_XSEC_CHAIN = [("무인증캐시", _xsec_fdrcache), ("pykrx", _xsec_pykrx),
               ("krx마켓플레이스", lambda d: KRXM.xsec(d)), ("fdr", _xsec_fdr)]


def _period_return_krx(d0: pd.Timestamp, d1: pd.Timestamp) -> Optional[pd.DataFrame]:
    """구간 [d0, d1] 의 전종목 **수정주가 등락률** — KRX 서버가 직접 계산해 준다.

    ★ 이것이 수익률의 1순위 소스인 이유:
      · 액면분할·무상증자가 서버측에서 이미 반영된다(내 휴리스틱 보정이 필요 없다).
      · 구간 중 상장폐지된 종목이 등락률 -100% 로 **포함되어** 돌아온다.
        → 생존자편향이 데이터 소스 단계에서 제거된다. 이보다 나은 보장은 없다.
    호출 1회로 전 종목이 오므로, 종목별 조회는 어떤 경우에도 하지 않는다.
    """
    if pykrx_stock is None:
        return None
    fn = getattr(pykrx_stock, "get_market_price_change", None) or \
        getattr(pykrx_stock, "get_market_price_change_by_ticker", None)
    if fn is None:
        return None
    d = _pykrx_call(fn, f"{d0:%Y%m%d}", f"{d1:%Y%m%d}", market="ALL", adjusted=True)
    if d is None or not len(d):
        return None
    d = d.reset_index()
    lc = {str(c): c for c in d.columns}
    tick = lc.get("티커") or d.columns[0]
    rc = lc.get("등락률")
    if rc is None:
        return None
    out = pd.DataFrame({"code": d[tick].map(code6),
                        "ret": pd.to_numeric(d[rc], errors="coerce") / 100.0})
    # ★ dropna 이후에 마스크를 만든다 — 원본 길이로 만든 마스크를 쓰면 길이 불일치로
    #   예외가 나고, 그 예외가 pmap 에 먹혀 이 구간이 영영 캐시되지 않는다.
    out = out.dropna(subset=["code"])
    if "시가" in lc and len(out):
        base = pd.to_numeric(d.loc[out.index, lc["시가"]], errors="coerce").to_numpy()
        out.loc[~np.isfinite(base) | (base <= 0), "ret"] = np.nan
    return out[np.isfinite(out["ret"])] if len(out) else None


class ReturnHub:
    """구간 수익률 캐시 — (시작일, 종료일) 쌍당 1회만 받고 공용 인덱스에 적재한다."""

    def __init__(self, depot: "Depot"):
        self.depot = depot
        self.df: Optional[pd.DataFrame] = None
        self.have: set = set()
        self.dirty = False

    def load(self):
        if self.df is not None:
            return
        d = self.depot.table_load(RET_TABLE, need_cols=["from_date", "to_date", "code", "ret"])
        if d is not None and len(d):
            d["from_date"] = ts_col(d["from_date"])
            d["to_date"] = ts_col(d["to_date"])
            d["code"] = d["code"].astype(str).str.zfill(6)
            # 같은 (구간, 종목)이 두 번 들어오면 하류의 reindex 가 깨진다 — 여기서 정규화
            d = d.drop_duplicates(["from_date", "to_date", "code"], keep="last")
            self.df = d
            self.have = set(zip(d["from_date"], d["to_date"]))
        else:
            self.df = pd.DataFrame(columns=["from_date", "to_date", "code", "ret"])

    def ensure(self, pairs: Sequence[Tuple[pd.Timestamp, pd.Timestamp]]):
        self.load()
        pairs = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in pairs
                 if a is not None and b is not None and a < b]
        todo = [p for p in dict.fromkeys(pairs) if p not in self.have]
        if todo and RUN_MODE == "CACHED":
            CON.warn(f"CACHED 모드 — 미보유 구간수익률 {len(todo)}건은 단면 파생값으로 대체")
            return
        if not todo:
            return
        CON.say(f"구간 수익률(수정주가·상폐포함) 수집: 신규 {len(todo)}구간 "
                f"/ 캐시 {len(pairs)-len(todo)}구간 — 구간당 1콜, 전 종목 동시")

        def _one(p):
            if DEADLINE.over("구간 수익률"):
                return None
            d = _period_return_krx(p[0], p[1])
            if d is None or not len(d):
                return None
            d["from_date"], d["to_date"] = p[0], p[1]
            return d

        CHUNK = 40
        for i in range(0, len(todo), CHUNK):
            if DEADLINE.over("구간 수익률"):
                break
            got = [g for g in pmap(_one, todo[i:i + CHUNK], workers=XSEC_WORKERS)
                   if g is not None]
            if not got and i == 0:
                CON.warn("구간 수익률 소스가 응답하지 않습니다 — 단면 파생 수익률로 "
                         "진행합니다(분할 보정이 휴리스틱이 됩니다).")
                break
            if got:
                self.df = pd.concat([self.df] + got, ignore_index=True).drop_duplicates(
                    ["from_date", "to_date", "code"], keep="last")
                self.have |= {(g["from_date"].iloc[0], g["to_date"].iloc[0]) for g in got}
                self.dirty = True
                self.flush()
            CON.say(f"  구간 {min(i+CHUNK, len(todo))}/{len(todo)}")

    def flush(self):
        if self.dirty and self.df is not None and len(self.df):
            self.depot.table_save(RET_TABLE, self.df, scope="공용", domain="market",
                                  source="pykrx_price_change(adjusted)",
                                  note="구간 수정주가 등락률 · 상폐 -100% 포함")
            self.dirty = False

    def get(self, d0, d1) -> Optional[pd.Series]:
        if self.df is None or not len(self.df):
            return None
        m = self.df[(self.df["from_date"] == pd.Timestamp(d0))
                    & (self.df["to_date"] == pd.Timestamp(d1))]
        if not len(m):
            return None
        return m.drop_duplicates("code", keep="last").set_index("code")["ret"]


class MarketHub:
    """날짜 단면 시장데이터 허브 — 캐시(로컬/드라이브) 우선, 부족한 날짜만 신규 수집."""

    def __init__(self, depot: "Depot"):
        self.depot = depot
        self.frames: Dict[int, pd.DataFrame] = {}       # 연도 → 단면 프레임
        self.loaded_years: set = set()
        self.have_dates: set = set()
        self.new_years: set = set()
        self._bulk_tried: set = set()
        self._lk = threading.RLock()

    # ── 캐시 ───────────────────────────────────────────────────────────────────────────
    def _load_year(self, y: int):
        if y in self.loaded_years:
            return
        self.loaded_years.add(y)
        d = self.depot.table_load(f"{XSEC_TABLE}_{y}",
                                  foreign_patterns=[f"xsec_daily_krx_{y}", f"krx_xsec_{y}"],
                                  need_cols=["date", "code", "close"])
        if d is not None and len(d):
            d["date"] = ts_col(d["date"])
            d["code"] = d["code"].astype(str).str.zfill(6)
            for c in XSEC_COLS:
                if c not in d.columns:
                    d[c] = np.nan
            self.frames[y] = d[XSEC_COLS]
            self.have_dates |= set(d["date"].unique())

    def _save_year(self, y: int):
        if y in self.frames and len(self.frames[y]):
            self.depot.table_save(f"{XSEC_TABLE}_{y}", self.frames[y], scope="공용",
                                  domain="market", source="pykrx+krx+fdr",
                                  note="date-cross-section (공용: 어느 전략이든 재사용)")

    def flush(self):
        for y in sorted(self.new_years):
            self._save_year(y)
        self.new_years.clear()

    # ── 거래일 캘린더 (1콜) ────────────────────────────────────────────────────────────
    def calendar(self, start, end) -> pd.DatetimeIndex:
        cached = self.depot.table_load("krx_trading_calendar",
                                       foreign_patterns=["trading_calendar", "krx_calendar"],
                                       need_cols=["date"])
        days: Optional[pd.DatetimeIndex] = None
        if cached is not None and len(cached) > 500:
            days = pd.DatetimeIndex(ts_col(cached["date"]).dropna().unique())
        need_lo, need_hi = ts(start), ts(end)
        if days is None or days.min() > need_lo + pd.Timedelta(10, "D") or \
                days.max() < min(need_hi, pd.Timestamp.today().normalize()) - pd.Timedelta(10, "D"):
            got = None
            if pykrx_stock is not None:
                idx = _pykrx_call(pykrx_stock.get_index_ohlcv,
                                  f"{need_lo:%Y%m%d}", f"{need_hi:%Y%m%d}", "1001")
                if idx is not None and len(idx):
                    got = pd.DatetimeIndex(pd.to_datetime(idx.index)).normalize()
            if got is None and fdr is not None:
                try:
                    d = fdr.DataReader("KS11", need_lo, need_hi)
                    if d is not None and len(d):
                        got = pd.DatetimeIndex(pd.to_datetime(d.index)).normalize()
                except Exception:
                    got = None
            if got is not None and len(got) > 100:
                days = got if days is None else pd.DatetimeIndex(
                    sorted(set(days) | set(got)))
                self.depot.table_save("krx_trading_calendar",
                                      pd.DataFrame({"date": days}), scope="공용",
                                      domain="market", source="krx_index_1001")
        if days is None or len(days) < 100:
            CON.warn("거래일 캘린더를 지수에서 얻지 못해 영업일(주말 제외) 근사로 대체합니다 "
                     "— 공휴일이 포함되어 지평 계산이 며칠 어긋날 수 있습니다.")
            days = pd.bdate_range(need_lo, need_hi)
        days = days[(days >= need_lo - pd.Timedelta(400, "D")) & (days <= need_hi)]
        return pd.DatetimeIndex(sorted(set(days)))

    # ── 단면 수집 ──────────────────────────────────────────────────────────────────────
    def _bulk_fill(self, missing: Sequence[pd.Timestamp]) -> int:
        """부족한 날짜를 연 단위 벌크로 한 번에 메운다 — 연당 1회 다운로드.
        날짜별로 두드리는 것보다 압도적으로 빠르고 차단 위험도 없다(무인증 정적 파일)."""
        years = sorted({pd.Timestamp(d).year for d in missing})
        filled = 0
        for y in years:
            if DEADLINE.over("벌크 단면"):
                break
            if y in self._bulk_tried:
                continue
            self._bulk_tried.add(y)
            d = bulk_marcap_year(y)
            if d is None or not len(d):
                CON.debug(f"벌크 단면 {y}년 미확보 — 날짜별 소스로 넘어갑니다")
                continue
            self._absorb([d])
            self.flush()
            filled += 1
        return filled

    def ensure(self, dates: Sequence[pd.Timestamp]) -> "pd.DataFrame":
        """요청 날짜들의 전종목 단면을 보장한다. 캐시에 있는 날짜는 절대 다시 받지 않는다."""
        want = sorted({pd.Timestamp(d).normalize() for d in dates})
        for y in sorted({d.year for d in want}):
            self._load_year(y)
        todo = [d for d in want if d not in self.have_dates]
        if todo and RUN_MODE != "CACHED":
            if self._bulk_fill(todo):
                todo = [d for d in want if d not in self.have_dates]
                CON.say(f"벌크 적재 후 잔여 미보유 {len(todo)}일")
        if todo and RUN_MODE == "CACHED":
            CON.warn(f"CACHED 모드 — 미보유 단면 {len(todo)}일은 건너뜁니다")
            todo = []
        if todo:
            CON.say(f"전종목 단면 수집: 신규 {len(todo)}일 / 요청 {len(want)}일 "
                    f"(캐시 재사용 {len(want)-len(todo)}일) — 날짜당 1콜")
            got_n, src_tally = 0, Counter()
            batch: List[pd.DataFrame] = []
            t0 = time.time()

            def _one(day):
                if DEADLINE.over("전종목 단면 수집"):
                    return None
                for src, fn in _XSEC_CHAIN:
                    try:
                        d = fn(day)
                    except Exception:
                        d = None
                    if d is not None and len(d) > 100:      # 부분응답(사고)은 채택하지 않는다
                        d["src"] = src
                        return d
                return None

            CHUNK = 60
            for i in range(0, len(todo), CHUNK):
                if DEADLINE.over("전종목 단면 수집"):
                    break
                part = pmap(_one, todo[i:i + CHUNK], workers=XSEC_WORKERS)
                for d in part:
                    if d is None or not len(d):
                        continue
                    src_tally[d["src"].iloc[0]] += 1
                    batch.append(d.drop(columns=["src"]))
                    got_n += 1
                if batch:                                   # 청크마다 적재+저장(중단 내성)
                    self._absorb(batch)
                    batch = []
                    self.flush()
                done = min(i + CHUNK, len(todo))
                el = time.time() - t0
                if got_n == 0 and done >= min(20, len(todo)):
                    # ★ 초반부터 단 한 건도 못 받으면 남은 수백 일을 계속 두드리지 않는다.
                    #   되지 않는 이유가 소스에 있는 것이므로, 즉시 멈추고 원인을 보고한다.
                    CON.warn(f"단면 {done}일 연속 실패 — 남은 {len(todo)-done}일 시도를 "
                             f"중단합니다(원인은 아래 소스 진단표 참조)")
                    break
                if el > 3:
                    rate = done / el
                    CON.say(f"  단면 {done}/{len(todo)}일 · 성공 {got_n} "
                            f"({rate*60:.0f}일/분, 잔여 {(len(todo)-done)/max(rate,1e-9)/60:.1f}분)")
            if src_tally:
                CON.grid([[k, f"{v:,}"] for k, v in src_tally.items()],
                         ["단면 소스", "성공 일수"], ["l", "r"])
            miss = [d for d in todo if d not in self.have_dates]
            if miss:
                CON.warn(f"단면 미수집 {len(miss)}일 — 해당 신호일은 직전 영업일 단면으로 "
                         f"대체되거나 제외됩니다(예: {miss[0]:%Y-%m-%d})")
        return self.slice(want)

    def _absorb(self, frames: List[pd.DataFrame]):
        with self._lk:
            for d in frames:
                y = int(d["date"].iloc[0].year)
                for c in XSEC_COLS:
                    if c not in d.columns:
                        d[c] = np.nan
                cur = self.frames.get(y)
                d = d[XSEC_COLS]
                self.frames[y] = d if cur is None else pd.concat([cur, d], ignore_index=True)
                self.frames[y] = self.frames[y].drop_duplicates(["date", "code"], keep="last")
                self.have_dates |= set(d["date"].unique())
                self.new_years.add(y)

    # ── 분할 보정 (일별 데이터로 계산해야 정확하다) ─────────────────────────────────────
    def compute_adjusted(self):
        """전 캐시 일별 단면에서 액면분할·무상증자를 탐지해 연속 총수익 가격을 만든다.

        ★ 인접 '거래일' 사이에서 판정하므로 오탐이 거의 없다. 월 간격으로 판정하면
          그 사이 주가 변동이 섞여 유상증자를 분할로 오인하거나 진짜 분할을 놓친다.
          판정: 상장주식수가 5% 넘게 변했는데 주가가 그 역수만큼 움직여 시가총액이
          연속인 경우 = 자본 유입 없는 주식수 변경 = 분할/무상증자.
        """
        if not self.frames:
            return
        allf = pd.concat([f[["date", "code", "close", "shares"]] for f in self.frames.values()
                          if len(f)], ignore_index=True)
        allf = allf.drop_duplicates(["date", "code"], keep="last")
        allf = allf.sort_values(["code", "date"], kind="mergesort")
        g = allf.groupby("code", observed=True, sort=False)
        p_sh = g["shares"].shift()
        p_px = g["close"].shift()
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = allf["shares"].to_numpy(float) / p_sh.to_numpy(float)
            pr = allf["close"].to_numpy(float) / p_px.to_numpy(float)
        split = (np.isfinite(ratio) & np.isfinite(pr) & (np.abs(ratio - 1.0) > 0.05)
                 & (np.abs(pr * ratio - 1.0) < 0.15))
        allf["_f"] = np.where(split, ratio, 1.0)
        allf["_g"] = allf.groupby("code", observed=True, sort=False)["_f"].cumprod()
        allf["adj_close"] = allf["close"].to_numpy(float) * allf["_g"].to_numpy(float)
        n_split = int(split.sum())
        if n_split:
            CON.say(f"액면분할·무상증자 {n_split:,}건 탐지 — 일별 인접 거래일 기준으로 "
                    f"보정해 연속 총수익 가격을 만들었습니다")
        key = allf.set_index(["date", "code"])["adj_close"]
        for y, f in self.frames.items():
            idx = pd.MultiIndex.from_arrays([f["date"], f["code"]])
            f["adj_close"] = key.reindex(idx).to_numpy(float)
            self.frames[y] = f

    def slice(self, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
        want = {pd.Timestamp(d).normalize() for d in dates}
        cols = XSEC_COLS + ["adj_close"]
        parts = [f.reindex(columns=[c for c in cols if c in f.columns])[
                     f["date"].isin(want).to_numpy()]
                 for f in self.frames.values() if len(f)]
        parts = [p for p in parts if len(p)]
        if not parts:
            return pd.DataFrame(columns=XSEC_COLS)
        out = pd.concat(parts, ignore_index=True)
        return out.drop_duplicates(["date", "code"], keep="last")

    def all_dates(self) -> List[pd.Timestamp]:
        return sorted(self.have_dates)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-b] PIT 유니버스 · 종목마스터 — 단면이 곧 유니버스다                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_SPECIAL_NAME = re.compile(r"스팩|SPAC|ETN|ETF|리츠|REIT|인프라|우$|우B$|\d+호(?![가-힣])", re.I)


def _is_common_stock(code: str, name: str) -> bool:
    """보통주만 남긴다 — 우선주(6자리 숫자코드 끝자리≠0)·스팩·ETF/ETN·리츠 제외.
    제외 규칙은 이 함수 한 곳에만 둔다(여기저기 흩어지면 유니버스가 조용히 달라진다)."""
    if not code:
        return False
    if re.fullmatch(r"\d{6}", code) and not code.endswith("0"):
        return False
    if _SPECIAL_NAME.search(str(name) or ""):
        return False
    return True


def _fdr_listing() -> Optional[pd.DataFrame]:
    d = fdr_cache_csv("listing/krx")          # 1순위: 무인증 GitHub 캐시 직접 읽기
    if (d is None or not len(d)) and fdr is not None:
        try:
            d = fdr.StockListing("KRX")       # 2순위: 라이브러리(내부에서 KRX 를 찌른다)
        except Exception:
            d = None
    if d is None or not len(d):
        return None
    lc = {str(c).lower(): c for c in d.columns}
    code_c = lc.get("code") or lc.get("symbol")
    if code_c is None:
        return None
    out = pd.DataFrame({"code": d[code_c].map(code6)})
    out["name"] = d[lc["name"]].astype(str) if "name" in lc else ""
    out["market"] = d[lc["market"]].astype(str) if "market" in lc else ""
    out["list_date"] = ts_col(d[lc["listingdate"]]) if "listingdate" in lc else pd.NaT
    return out.dropna(subset=["code"])


def _fdr_delisting() -> Optional[pd.DataFrame]:
    d = fdr_cache_csv("listing/delisting")    # 1순위: 무인증 GitHub 캐시(생존자편향의 핵심)
    if (d is None or not len(d)) and fdr is not None:
        try:
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
    if d is None or not len(d):
        return None
    lc = {str(c).lower(): c for c in d.columns}
    code_c = lc.get("symbol") or lc.get("code")
    del_c = lc.get("delistingdate") or lc.get("delistdate")
    if code_c is None or del_c is None:
        return None
    out = pd.DataFrame({"code": d[code_c].map(code6),
                        "name": d[lc["name"]].astype(str) if "name" in lc else "",
                        "delist_date": ts_col(d[del_c])})
    out = out.dropna(subset=["code", "delist_date"])
    return out.sort_values("delist_date").drop_duplicates("code", keep="last")


def _kind_listing() -> Optional[pd.DataFrame]:
    """KIND 상장법인목록 — 종목명 보강용(폴백)."""
    raw = fetch("https://kind.krx.co.kr/corpgeneral/corpList.do", source="kind",
                params={"method": "download", "searchType": "13"}, as_bytes=True)
    if not raw:
        return None
    for enc in ("euc-kr", "cp949", "utf-8"):
        try:
            tables = pd.read_html(io.BytesIO(raw), encoding=enc)
            break
        except Exception:
            tables = None
    if not tables:
        return None
    d = tables[0]
    cols = {str(c): c for c in d.columns}
    cc = next((cols[c] for c in cols if "종목코드" in c), None)
    nc = next((cols[c] for c in cols if "회사명" in c), None)
    dc = next((cols[c] for c in cols if "상장일" in c), None)
    if cc is None:
        return None
    return pd.DataFrame({"code": d[cc].map(code6),
                         "name": d[nc].astype(str) if nc else "",
                         "market": "",
                         "list_date": ts_col(d[dc]) if dc else pd.NaT}
                        ).dropna(subset=["code"])


def probe_market_sources(cal: "TradingCal") -> pd.DataFrame:
    """수집 전에 각 소스를 '실제로 한 번' 호출해 살아있는지 확인하고 표로 보여준다.

    ★ 이 단계가 없어서, pykrx import 가 실패했는데도 코드가 조용히 0행을 만들며
      수백 일을 헛돌았다. 무엇이 되고 무엇이 안 되는지 먼저 못박고 시작한다.
    """
    probe_day = pd.Timestamp(cal.days[max(0, len(cal.days) - 260)])   # 1년쯤 전 거래일
    rows = []
    ok_any = False
    PYKRX.warmup()
    # 1) 벌크(무인증)
    y = int(probe_day.year)
    t0 = time.time()
    b = bulk_marcap_year(y) if RUN_MODE != "CACHED" else None
    rows.append(["벌크 연단위(무인증)", f"marcap {y}",
                 "정상" if b is not None else "불가",
                 f"{len(b):,}행" if b is not None else "-", f"{time.time()-t0:.1f}s"])
    ok_any |= b is not None
    if b is not None:
        MARKET_PROBE_BULK.append(b)
    # 2) 일단위 무인증 캐시
    t0 = time.time()
    c = _xsec_fdrcache(probe_day) if RUN_MODE != "CACHED" else None
    rows.append(["일단위 캐시(무인증)", f"{probe_day:%Y-%m-%d}",
                 "정상" if c is not None else "불가",
                 f"{len(c):,}행" if c is not None else "-", f"{time.time()-t0:.1f}s"])
    ok_any |= c is not None
    # 3) pykrx
    if pykrx_stock is None:
        rows.append(["pykrx", "import 실패",
                     "불가", IMPORT_ERR.get("pykrx", "사유 미상")[:44], "-"])
    else:
        t0 = time.time()
        p = _xsec_pykrx(probe_day) if RUN_MODE != "CACHED" else None
        rows.append(["pykrx 단면", f"{probe_day:%Y-%m-%d}",
                     "정상" if p is not None else "불가",
                     (f"{len(p):,}행" if p is not None else PYKRX.note[:44]),
                     f"{time.time()-t0:.1f}s"])
        ok_any |= p is not None
    # 4) KRX 마켓플레이스
    rows.append(["KRX 정보데이터시스템", KRXM.state,
                 "비활성" if KRXM.disabled else "대기", KRXM.reason[:40] or "-", "-"])
    # 5) FDR / 기타
    rows.append(["FinanceDataReader", "import",
                 "정상" if fdr is not None else "불가",
                 IMPORT_ERR.get("FinanceDataReader", "")[:40] or "-", "-"])
    CON.grid(rows, ["소스", "대상", "판정", "비고", "소요"], ["l", "l", "l", "l", "r"],
             title="시장데이터 소스 자가진단 (되는 것만 씁니다)")
    if not ok_any and RUN_MODE != "CACHED":
        raise HaltRun(
            "시장데이터 소스가 하나도 응답하지 않습니다. 확인 순서: "
            "① 인터넷/프록시(사내망이면 raw.githubusercontent.com 차단 여부) "
            "② pykrx import 오류 메시지(위 표) — KRX 로그인 실패가 원인이면 "
            "KRX_MARKETPLACE_ID/PW 를 확인하거나 비워두고 재실행 "
            "③ RUN_MODE='CACHED' 로 기존 캐시만으로 재현")
    return pd.DataFrame(rows, columns=["source", "target", "verdict", "note", "sec"])


MARKET_PROBE_BULK: List[pd.DataFrame] = []


def build_security_master(xsec: pd.DataFrame) -> pd.DataFrame:
    """종목마스터 = 단면에서 관측된 실체 + 이름/시장/상장·폐지일 보강(다중소스 교차검증).

    유니버스 membership 자체는 단면이 정한다(그 날 거래된 종목). 상장/폐지 목록은
    ① 이름·시장 보강 ② 사라진 종목이 '폐지'인지 '결손'인지 판별 — 두 용도로만 쓴다.
    """
    if not len(xsec):
        raise HaltRun("단면 데이터가 비어 있습니다 — 시장 데이터 수집을 확인하세요")
    g = xsec.groupby("code", observed=True)["date"]
    sec = pd.DataFrame({"code": g.min().index, "first_seen": g.min().to_numpy(),
                        "last_seen": g.max().to_numpy()})
    # ★ 단면에 종목명이 있으면 그것이 가장 정확하다(그 시점에 실제로 쓰이던 이름).
    if "name" in xsec.columns:
        nm_x = (xsec.loc[xsec["name"].astype(str).str.strip() != "",
                         ["date", "code", "name"]]
                .sort_values("date").drop_duplicates("code", keep="last")[["code", "name"]])
        if len(nm_x):
            sec = sec.merge(nm_x, on="code", how="left")
    names = DEPOT.table_load("krx_security_names",
                             foreign_patterns=["security_master", "krx_names"],
                             need_cols=["code", "name"])
    frames = []
    if names is not None and len(names):
        n = names.copy()
        n["code"] = n["code"].map(code6)
        frames.append(n[["code", "name"] + ([c for c in ("market", "list_date") if c in n.columns])])
    if RUN_MODE != "CACHED":
        for fn in (_fdr_listing, _kind_listing):
            try:
                d = fn()
            except Exception:
                d = None
            if d is not None and len(d):
                frames.append(d)
    if frames:
        nm = pd.concat(frames, ignore_index=True).dropna(subset=["code"])
        nm = nm[nm["name"].astype(str).str.strip() != ""]
        nm = nm.drop_duplicates("code", keep="first").rename(columns={"name": "name_ext"})
        sec = sec.merge(nm, on="code", how="left")
        if "name" in sec.columns:      # 단면 이름을 우선하고 빈 곳만 외부 목록으로 채움
            sec["name"] = sec["name"].fillna("").astype(str)
            blank = sec["name"].str.strip() == ""
            sec.loc[blank, "name"] = sec.loc[blank, "name_ext"]
        else:
            sec["name"] = sec["name_ext"]
        sec = sec.drop(columns=[c for c in ("name_ext",) if c in sec.columns])
        DEPOT.table_save("krx_security_names", nm, scope="공용", domain="universe",
                         source="fdr+kind", note="종목명/시장/상장일 (공용 재사용)")
    for c in ("name", "market"):
        if c not in sec.columns:
            sec[c] = ""
        sec[c] = sec[c].fillna("").astype(str)
    if "list_date" not in sec.columns:
        sec["list_date"] = pd.NaT
    sec["list_date"] = ts_col(sec["list_date"])

    # 시장 구분 보강: 단면의 market 값(있으면) → 이름 소스 → 미상
    mk = (xsec[xsec["market"].astype(str) != ""]
          .drop_duplicates("code", keep="last")[["code", "market"]]
          .rename(columns={"market": "market_x"}))
    sec = sec.merge(mk, on="code", how="left")
    sec["market"] = np.where(sec["market"].astype(str) != "", sec["market"],
                             sec["market_x"].fillna(""))
    sec = sec.drop(columns=["market_x"])

    # 폐지일: FDR 목록 + '마지막 관측 이후 재등장 없음'의 교차검증
    dl = _fdr_delisting() if RUN_MODE != "CACHED" else None
    if dl is None:
        dl = DEPOT.table_load("krx_delisting", need_cols=["code", "delist_date"])
    else:
        DEPOT.table_save("krx_delisting", dl, scope="공용", domain="universe", source="fdr")
    sec["delist_date"] = pd.NaT
    if dl is not None and len(dl):
        dmap = dl.set_index("code")["delist_date"].to_dict()
        sec["delist_date"] = ts_col(sec["code"].map(dmap))
        # 이전상장(코스닥→코스피)은 폐지가 아니다 — 폐지일 이후에도 단면에 계속 보이면 무효화
        bogus = sec["delist_date"].notna() & (sec["last_seen"] > sec["delist_date"] + pd.Timedelta(10, "D"))
        if bogus.any():
            CON.say(f"이전상장·재상장으로 판정된 폐지기록 {int(bogus.sum()):,}건 무효화 "
                    f"(폐지일 이후에도 단면에 계속 관측됨)")
            sec.loc[bogus, "delist_date"] = pd.NaT
    # 단면 기준 사망 추정: 데이터 끝보다 충분히 앞서 사라졌는데 폐지기록이 없는 종목
    data_end = xsec["date"].max()
    vanished = (sec["delist_date"].isna() &
                (sec["last_seen"] < data_end - pd.Timedelta(35, "D")))
    if vanished.any():
        sec.loc[vanished, "delist_date"] = sec.loc[vanished, "last_seen"] + pd.Timedelta(1, "D")
        CON.say(f"단면에서 사라진 뒤 재등장 없는 종목 {int(vanished.sum()):,}건을 "
                f"폐지로 간주(생존자편향 방지 — 마지막 관측 다음날로 기록)")
    named = float((sec["name"].astype(str).str.strip() != "").mean()) if len(sec) else 0.0
    if named < 0.90:
        CON.warn(f"종목명 확보율 {named*100:.0f}% — 이름이 없으면 스팩·리츠·ETN 을 코드만으로는 "
                 f"거를 수 없어 소형주 유니버스가 오염됩니다(비교전략에 특히 치명적). "
                 f"FDR/KIND 접근을 확인하세요.")
    sec["is_common"] = [_is_common_stock(c, n) for c, n in zip(sec["code"], sec["name"])]
    CON.say(f"종목마스터 {len(sec):,}개 (보통주 {int(sec['is_common'].sum()):,} · "
            f"폐지이력 {int(sec['delist_date'].notna().sum()):,})")
    if int(sec["delist_date"].notna().sum()) < 100:
        CON.warn("폐지 이력이 100건 미만입니다 — 생존자편향 위험. FDR 상폐목록 접근을 확인하세요.")
    return sec


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-c] 월간 수익률 패널 — 단면에서 벡터화로 조립 (파이썬 루프 없음)                          ║
# ║                                                                                          ║
# ║  · 액면분할/무상증자 보정: 상장주식수 비율과 주가의 역방향 동시변동을 탐지해 보정한다.       ║
# ║    (유상증자처럼 '실제로 희석된' 경우는 보정하지 않는다 — 그건 진짜 손실이다)               ║
# ║  · 상장폐지: 단면에서 사라지고 폐지일이 확인되면 그 구간 수익률 -100%. 누락 금지.           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
SPLIT_MIN_RATIO = 1.35        # 주식수 비율이 이보다 크게(또는 역수보다 작게) 변할 때만 후보
SPLIT_PRICE_TOL = 0.10        # 보정 후 가격변화가 이 범위 안이면 분할/무상증자로 판정
SPLIT_MCAP_TOL = 0.15         # 시총 연속성 — 유상증자(자본 유입)를 분할로 오인하지 않게


def _pivot(xsec: pd.DataFrame, col: str, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    d = xsec[xsec["date"].isin(set(dates))]
    if not len(d):
        return pd.DataFrame(index=pd.Index([], name="code"))
    p = d.pivot_table(index="code", columns="date", values=col, aggfunc="last")
    return p.reindex(columns=pd.DatetimeIndex(sorted(set(dates))))


def _adjust_factor(shares: pd.DataFrame, close: pd.DataFrame,
                   mcap: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """열(날짜) 간 분할계수 f: 다음 시점 가격에 곱하면 분할 전후가 연속이 되는 값.

    판정은 세 조건을 '동시에' 만족할 때만: ① 주식수가 크게 변했고 ② 가격이 그 역수만큼
    움직였고 ③ 시가총액이 연속이다. ③이 핵심이다 — 유상증자는 자본이 유입되어 시총이
    뛰므로 걸러진다. 열 간격이 한 달이라 ②만으로는 오탐/누락이 모두 커진다.
    """
    sh = shares.to_numpy(float)
    px = close.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = sh[:, 1:] / sh[:, :-1]
        pr = px[:, 1:] / px[:, :-1]
    cand = np.isfinite(ratio) & ((ratio >= SPLIT_MIN_RATIO) | (ratio <= 1 / SPLIT_MIN_RATIO))
    ok = cand & np.isfinite(pr) & (np.abs(pr * ratio - 1.0) < SPLIT_PRICE_TOL)
    if mcap is not None:
        mc = mcap.to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            mr = mc[:, 1:] / mc[:, :-1]
        # 시총비가 '가격비×주식수비'와 일치하고 1 근처여야 순수 분할이다
        ok &= np.isfinite(mr) & (np.abs(mr - 1.0) < SPLIT_MCAP_TOL)
    f = np.ones_like(ratio)
    f[ok] = ratio[ok]
    return pd.DataFrame(f, index=close.index, columns=close.columns[1:])


class PriceMatrix:
    """단면 → (종목 × 날짜) 행렬. 분할·무상증자 보정을 한 번만 계산해 재사용한다.

    adj[code, date] 의 두 시점 비율이 곧 총수익률이다. 백테스트 수익률, IC 지평,
    목표주가 만기 조회가 모두 이 하나의 행렬을 쓴다 — 가격 조회를 반복하지 않는다.
    """

    def __init__(self, xsec: pd.DataFrame, dates: Sequence[pd.Timestamp]):
        dates = sorted({pd.Timestamp(d).normalize() for d in dates if d is not None})
        self.close = _pivot(xsec, "close", dates)
        if self.close.empty:
            raise HaltRun("단면에서 가격 행렬을 만들지 못했습니다 — 시장 데이터 수집 확인")
        # ★ pivot_table 은 전부 NaN 인 행을 통째로 떨어뜨린다. 행 인덱스를 close 에 맞춰
        #   재정렬하지 않으면 mktcap 이 '한 칸 밀려 다른 종목에 붙는' 사고가 난다
        #   (시총 하위1000 선정이 조용히 엉뚱한 종목을 고르게 된다).
        def _al(col):
            return _pivot(xsec, col, dates).reindex(index=self.close.index,
                                                    columns=self.close.columns)

        self.shares = _al("shares")
        self.mcap = _al("mktcap")
        self.value = _al("value")
        if "adj_close" in xsec.columns and xsec["adj_close"].notna().any():
            # 일별 데이터로 이미 보정된 연속가격이 있으면 그것을 쓴다(가장 정확)
            self.adj = _al("adj_close")
            self.cum = (self.adj.to_numpy(float) /
                        np.where(self.close.to_numpy(float) == 0, np.nan,
                                 self.close.to_numpy(float)))
            self.n_adjusted = int(np.nansum(np.abs(self.cum - 1.0) > 1e-9))
            self.cols = np.array(self.close.columns.values, dtype="datetime64[ns]")
            self.row_of = {c: i for i, c in enumerate(self.close.index)}
            self._adj_np = self.adj.to_numpy(float)
            self.daily_adjusted = True     # 일별 인접 거래일 기준 보정 = 추정이 아님
            return
        self.daily_adjusted = False
        fac = _adjust_factor(self.shares, self.close, self.mcap)
        self.n_adjusted = int((fac.to_numpy() != 1.0).sum())
        if self.n_adjusted:
            CON.say(f"액면분할·무상증자 보정 {self.n_adjusted:,}건 "
                    f"(상장주식수 비율 × 역방향 가격변동 동시 탐지)")
        self.cum = np.cumprod(np.hstack([np.ones((len(fac), 1)), fac.to_numpy()]), axis=1)
        self.adj = pd.DataFrame(self.close.to_numpy() * self.cum, index=self.close.index,
                                columns=self.close.columns)
        self.cols = np.array(self.close.columns.values, dtype="datetime64[ns]")
        self.row_of = {c: i for i, c in enumerate(self.close.index)}
        self._adj_np = self.adj.to_numpy(float)


def build_month_panel(have_dates: Sequence[pd.Timestamp], xsec: pd.DataFrame,
                      sec: pd.DataFrame, months: Sequence[pd.Timestamp],
                      cal: "TradingCal", pm: Optional["PriceMatrix"] = None,
                      rethub: Optional["ReturnHub"] = None,
                      anchors: Optional[Dict[Any, pd.Timestamp]] = None
                      ) -> Tuple[pd.DataFrame, "PriceMatrix"]:
    """월간 패널: code·month·close·mktcap·value·fwd_1m·fwd_20/60/120td.

    수익률 우선순위:
      1순위 ReturnHub — KRX 서버측 수정주가 등락률(분할 반영 + 상폐 -100% 포함)
      2순위 단면 파생 — 상장주식수 비율로 분할을 탐지해 보정(1순위 실패 구간의 폴백)
    반환 (패널, PriceMatrix) — 행렬은 목표주가 만기 조회 등에서 재사용된다."""
    months = list(pd.DatetimeIndex(months))
    have = np.array(sorted({pd.Timestamp(d).normalize() for d in have_dates}),
                    dtype="datetime64[ns]")
    if not len(have):
        raise HaltRun("보유 단면이 없습니다 — 시장 데이터 수집을 확인하세요")

    have_set2 = {pd.Timestamp(d) for d in have}

    def _resolve(t, tol: int = 10) -> Optional[pd.Timestamp]:
        if t is None:
            return None
        i = int(np.searchsorted(have, np.datetime64(pd.Timestamp(t)), side="right")) - 1
        if i < 0:
            return None
        got = pd.Timestamp(have[i])
        return got if (pd.Timestamp(t) - got).days <= tol else None

    # ★ 앵커가 주어지면 그대로 쓴다. 구간 수익률 캐시는 앵커 날짜로 키가 잡혀 있으므로
    #   여기서 다른 날짜로 해석하면 그 달 전체가 캐시 미스가 되고, 신호도 월말이 아닌
    #   날짜의 가격으로 평가된다.
    if anchors:
        snap_of = {m: (anchors.get(m) if anchors.get(m) in have_set2 else None)
                   for m in months}
    else:
        snap_of = {m: _resolve(m, tol=10) for m in months}
    use_months = [m for m in months if snap_of[m] is not None]
    if not use_months:
        raise HaltRun("신호일에 대응하는 단면이 하나도 없습니다")
    md = [snap_of[m] for m in use_months]
    # ★ 지평 날짜는 '실제 거래일'을 그대로 쓴다. ReturnHub 가 그 구간의 수익률을 직접
    #   주기 때문에 그 날짜의 단면을 받을 필요가 없다(호출량 급감). 단면이 마침 있으면
    #   폴백 계산에도 쓰이고, 없으면 그 지평만 결측이 된다.
    horiz = {h: [cal.shift(d0, h) for d0 in md] for h in (20, 60, 120)}
    nxt = [md[i + 1] if i + 1 < len(md) else None for i in range(len(md))]

    have_set = have_set2
    all_dates = sorted({d for d in md if d is not None}
                       | {d for v in horiz.values() for d in v
                          if d is not None and pd.Timestamp(d) in have_set}
                       | {d for d in nxt if d is not None})
    if pm is None:
        pm = PriceMatrix(xsec, all_dates)
    close, adj, mcap, value = pm.close, pm.adj, pm.mcap, pm.value

    dl = (sec.drop_duplicates("code").set_index("code")["delist_date"]
          .reindex(close.index))
    dl_np = dl.to_numpy("datetime64[ns]")
    dl_ok = dl.notna().to_numpy()
    rows = []
    nan_col = np.full(len(close.index), np.nan)
    src_tally = Counter()

    nan_ret = np.full(len(close.index), np.nan)

    def _dead_between(d_from, d_to):
        """구간 (d_from, d_to] 안에서 실제로 폐지된 종목만 True.
        ★ 상한을 두지 않으면 2025년에 폐지될 종목이 2018년 어느 달에도 전손으로 찍힌다."""
        return (dl_ok & (dl_np > np.datetime64(pd.Timestamp(d_from)))
                & (dl_np <= np.datetime64(pd.Timestamp(d_to) + pd.Timedelta(35, "D"))))

    def _ret(d_from, d_to, c0_np, alive0):
        """1순위 서버 수정주가, 2순위 단면 파생. 어느 쪽이든 '그 구간에 폐지된' 종목만 -100%."""
        if d_to is None:
            src_tally["미산출"] += 1
            return nan_ret.copy(), "없음"
        n_alive = int(alive0.sum())
        if rethub is not None:
            s = rethub.get(d_from, d_to)
            # ★ 부분응답을 성공으로 받으면 단면 대부분이 결측이 되고, 그 결측이 다시
            #   전손 판정으로 흘러간다. 살아있는 종목의 절반 이상을 덮을 때만 채택한다.
            if s is not None and len(s) >= max(30, 0.5 * n_alive):
                r = s.reindex(close.index).to_numpy(float)
                miss = alive0 & ~np.isfinite(r)
                r = np.where(miss & _dead_between(d_from, d_to), -1.0, r)
                src_tally["서버수정주가"] += 1
                return r, "서버"
        # 폴백: 그 날짜 단면이 실제로 존재할 때만 계산한다. 빈 열로 계산하면
        # 전 종목이 '사라진 것'으로 보여 대량 오검출이 난다.
        if d_to not in adj.columns:
            src_tally["미산출"] += 1
            return nan_ret.copy(), "없음"
        ch = adj[d_to].to_numpy()
        if not np.isfinite(ch).any():
            src_tally["미산출"] += 1
            return nan_ret.copy(), "없음"
        r = ch / c0_np - 1.0
        gone = alive0 & ~np.isfinite(ch)
        src_tally["단면파생"] += 1
        return np.where(gone & _dead_between(d_from, d_to), -1.0, r), "단면"
    for i, m in enumerate(use_months):
        d0 = md[i]
        c0 = adj[d0]
        base = pd.DataFrame({"code": close.index, "month": m,
                             "close": close[d0].to_numpy(),
                             "mktcap": (mcap[d0].to_numpy() if d0 in mcap.columns
                                        else nan_col),
                             "value": (value[d0].to_numpy() if d0 in value.columns
                                       else nan_col)})
        c0_np = c0.to_numpy()
        alive0 = np.isfinite(c0_np)
        base["fwd_1m"] = _ret(d0, nxt[i], c0_np, alive0)[0]
        for h in (20, 60, 120):
            base[f"fwd_{h}td"] = _ret(d0, horiz[h][i], c0_np, alive0)[0]
        rows.append(base[alive0])
    P = pd.concat(rows, ignore_index=True)
    P = P[np.isfinite(P["close"]) & (P["close"] > 0)]
    if src_tally:
        CON.say("수익률 출처: " + " · ".join(f"{k} {v:,}구간" for k, v in src_tally.items())
                + " (서버 수정주가가 분할·상폐를 이미 반영합니다)")
        tot = sum(src_tally.values())
        derived = src_tally.get("단면파생", 0)
        precise = pm is not None and getattr(pm, "daily_adjusted", False)
        if tot and derived / tot > 0.30 and not precise and RUN_MODE != "SMOKE":
            CON.warn(f"구간의 {derived/tot*100:.0f}%가 월 간격 추정 보정입니다 — 분할 판정이 "
                     f"휴리스틱이라 정확도가 떨어집니다. 벌크 일별 데이터를 확보하면 "
                     f"자동으로 정확한 보정으로 대체됩니다.")
    # 잔여 생존자편향 점검: 살아 있었는데 다음 달 수익률이 결측인 종목 비율
    nan_ratio = float(P["fwd_1m"].isna().mean()) if len(P) else 0.0
    if nan_ratio > 0.10:
        CON.warn(f"fwd_1m 결측 비율 {nan_ratio*100:.0f}% — 사라진 종목이 손실로 기록되지 "
                 f"않고 표본에서 빠지면 하위분위 수익률이 과대평가됩니다. "
                 f"상폐 목록(krx_delisting) 수집 상태를 확인하세요.")
    CON.say(f"월간 패널 {len(P):,}행 · 종목 {P['code'].nunique():,} · 월 {len(use_months)} · "
            f"{mem_mb(P):.0f}MB")
    return shrink(P), pm


def universe_frame(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """PIT 유니버스 = 그 달 단면에 실재한 보통주. (상장/폐지 목록에 의존하지 않는다)"""
    common = set(sec.loc[sec["is_common"], "code"])
    U = P.loc[P["code"].isin(common), ["code", "month", "mktcap"]].copy()
    U = U.rename(columns={"code": "stock_id", "month": "signal_date"})
    U["in_uni"] = True
    return U


def collect_benchmark(hub: "MarketHub", months: Sequence[pd.Timestamp]
                      ) -> Dict[str, pd.Series]:
    """벤치마크 월간 수익률 — 지수 시계열 1콜씩."""
    out: Dict[str, pd.Series] = {}
    midx = pd.DatetimeIndex(months)
    lo, hi = midx.min() - pd.Timedelta(70, "D"), midx.max()
    cached = DEPOT.table_load("krx_index_monthly", need_cols=["name", "date", "close"])
    frames = [cached] if cached is not None and len(cached) else []
    fresh = []
    if RUN_MODE != "CACHED":
        for name, kcode, fsym in (("KOSPI", "1001", "KS11"), ("KOSDAQ", "2001", "KQ11")):
            s = None
            if pykrx_stock is not None:
                d = _pykrx_call(pykrx_stock.get_index_ohlcv, f"{lo:%Y%m%d}", f"{hi:%Y%m%d}",
                                kcode)
                if d is not None and len(d):
                    col = "종가" if "종가" in d.columns else d.columns[-1]
                    s = pd.Series(pd.to_numeric(d[col], errors="coerce").to_numpy(),
                                  index=pd.DatetimeIndex(d.index).normalize())
            if s is None and fdr is not None:
                try:
                    d = fdr.DataReader(fsym, lo, hi)
                    if d is not None and len(d):
                        s = pd.Series(pd.to_numeric(d["Close"], errors="coerce").to_numpy(),
                                      index=pd.DatetimeIndex(d.index).normalize())
                except Exception:
                    s = None
            if s is not None and len(s):
                fresh.append(pd.DataFrame({"name": name, "date": s.index,
                                           "close": s.to_numpy()}))
    if fresh:
        frames.extend(fresh)
    if not frames:
        CON.warn("벤치마크 지수를 얻지 못했습니다 — 초과수익 열은 비어 있게 됩니다")
        return out
    B = pd.concat(frames, ignore_index=True)
    B["date"] = ts_col(B["date"])
    B = B.dropna(subset=["date", "close"]).drop_duplicates(["name", "date"], keep="last")
    if fresh:
        DEPOT.table_save("krx_index_monthly", B, scope="공용", domain="market",
                         source="pykrx+fdr")
    for name, g in B.groupby("name"):
        s = g.set_index("date")["close"].sort_index()
        m = _resample_me(s)
        # ★ shift(-1): 패널의 fwd_1m 은 'T 이후 한 달'의 수익이다. 지수 수익도 같은 구간으로
        #   맞춰야 초과수익이 한 달 어긋나지 않는다.
        out[str(name)] = m.pct_change().shift(-1).reindex(midx)
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-d] 애널리스트 리포트 수집 — 한경컨센서스 + 네이버리서치 (다중소스 원장)                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_HK_LIST = "https://consensus.hankyung.com/analysis/list"
_NV_LIST = "https://finance.naver.com/research/company_list.naver"

_TITLE_CODE = re.compile(r"\((\d{6})\)")
_NULLISH = {"", "-", "0", "N/A", "없음", "nan", "None"}


def _tp_parse(x) -> Optional[float]:
    s = re.sub(r"[,\s원]", "", str(x or ""))
    if s in _NULLISH:
        return None
    try:
        v = float(s)
    except Exception:
        return None
    return v if 100 <= v <= 5e7 else None       # 0/'-' 는 '목표가 없음'이다. 0원을 넣으면 오염.


def _date_kr(x) -> Optional[pd.Timestamp]:
    """명시적 날짜 패턴만 인정한다 — 자유 추론에 맡기면 조회수 '1234' 가
    1234년으로, 'YY.MM.DD' 가 연/일 반전으로 조용히 오염된다."""
    s = str(x or "").strip()
    m = re.fullmatch(r"(\d{2})[./-](\d{2})[./-](\d{2})\.?", s)
    if m:
        return ts(f"20{m.group(1)}-{m.group(2)}-{m.group(3)}")
    m = re.fullmatch(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})\.?", s)
    if m:
        return ts(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    return None


def _hk_parse_page(html: str) -> List[dict]:
    sp = soup(html)
    if sp is None:
        return []
    table = sp.select_one("div.table_style01 table") or sp.find("table")
    if table is None:
        return []
    heads = [th.get_text(strip=True) for th in table.select("thead th")] or \
            [th.get_text(strip=True) for th in table.find_all("th")]

    def _col(*keys):
        for i, hh in enumerate(heads):
            if any(k in hh for k in keys):
                return i
        return None

    i_dt, i_ti = _col("작성일", "날짜"), _col("제목")
    i_tp, i_op = _col("적정가격", "목표주가", "적정주가"), _col("투자의견", "의견")
    i_an, i_br = _col("작성자", "애널리스트"), _col("제공출처", "증권사", "출처")
    rows = []
    for tr in table.select("tbody tr") or table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        def _cell(i):
            return tds[i].get_text(" ", strip=True) if i is not None and i < len(tds) else ""
        title = _cell(i_ti) or (tds[1].get_text(" ", strip=True) if len(tds) > 1 else "")
        rid = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)|downpdf\?[^\"']*?(\d{5,})", a["href"])
            if m:
                rid = m.group(1) or m.group(2)
                break
        pdf = f"https://consensus.hankyung.com/analysis/downpdf?report_idx={rid}" if rid else ""
        d = _date_kr(_cell(i_dt))
        mcode = _TITLE_CODE.search(title)
        rows.append(dict(source="hankyung", rid=str(rid or h1("hk", title, str(d))[:12]),
                         date=d, title=title,
                         stock_code=mcode.group(1) if mcode else None,
                         stock_name=title.split("(")[0].strip()[:40] if mcode else "",
                         broker=_cell(i_br), analyst=_cell(i_an),
                         target_price=_tp_parse(_cell(i_tp)), opinion=_cell(i_op),
                         pdf_url=pdf))
    return rows


def _hk_collect_month(y: int, m: int) -> List[dict]:
    sdate, edate = f"{y}-{m:02d}-01", f"{y}-{m:02d}-{pd.Timestamp(y, m, 1).days_in_month:02d}"
    out, page, empty_streak = [], 1, 0
    while page <= 120 and empty_streak < 2:
        html = fetch(_HK_LIST, source="hankyung",
                     params={"skinType": "business", "search_text": "", "pagenum": "80",
                             "sdate": sdate, "edate": edate, "now_page": str(page),
                             "report_type": "CO"})
        rows = _hk_parse_page(html) if html else []
        if not rows:
            empty_streak += 1
        else:
            empty_streak = 0
            out.extend(rows)
            if len(rows) < 20:
                break
        page += 1
    return out


def _nv_parse_page(html: str) -> List[dict]:
    sp = soup(html)
    if sp is None:
        return []
    table = sp.select_one("table.type_1")
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        a_item = tr.select_one("a.stock_item")
        code = None
        if a_item is not None:
            m = re.search(r"code=(\d{6})", a_item.get("href", ""))
            code = m.group(1) if m else None
        a_det = next((a for a in tr.find_all("a", href=True)
                      if "company_read" in a["href"]), None)
        nid = None
        if a_det is not None:
            m = re.search(r"nid=(\d+)", a_det["href"])
            nid = m.group(1) if m else None
        pdf = next((a["href"] for a in tr.find_all("a", href=True)
                    if a["href"].lower().endswith(".pdf")), "")
        txts = [td.get_text(" ", strip=True) for td in tds]
        date = next((v for v in (_date_kr(t) for t in txts[::-1]) if v is not None), None)
        title = a_det.get_text(" ", strip=True) if a_det is not None else txts[1][:80]
        broker = txts[2] if len(txts) > 2 else ""
        rows.append(dict(source="naver", rid=str(nid or h1("nv", title, str(date))[:12]),
                         date=date, title=title, stock_code=code,
                         stock_name=(a_item.get_text(strip=True) if a_item else ""),
                         broker=broker, analyst="", target_price=None, opinion="",
                         pdf_url=pdf if str(pdf).startswith("http") else "",
                         detail_url=(f"https://finance.naver.com/research/company_read.naver"
                                     f"?nid={nid}" if nid else "")))
    return rows


def _nv_collect_month(y: int, m: int) -> List[dict]:
    sdate = f"{y}-{m:02d}-01"
    edate = f"{y}-{m:02d}-{pd.Timestamp(y, m, 1).days_in_month:02d}"
    out, page = [], 1
    while page <= 200:
        html = fetch(_NV_LIST, source="naver",
                     params={"searchType": "writeDate", "writeFromDate": sdate,
                             "writeToDate": edate, "page": str(page)})
        rows = _nv_parse_page(html) if html else []
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 25:
            break
        page += 1
    return out


def collect_research(start: str, end: str) -> pd.DataFrame:
    """월 단위 증분 수집 + 캐시 병합. 반환: 원시 보고서 행(중복 미제거 — 병합은 원장 단계서)."""
    cached = DEPOT.table_load("scg_reports_raw",
                              foreign_patterns=["report_master", "research_report"],
                              need_cols=None)
    frames: List[pd.DataFrame] = []
    done_m: set = set()
    if cached is not None and len(cached):
        cached = _adapt_foreign_reports(cached)
        if cached is not None and len(cached):
            frames.append(cached)
            done_m = set(cached["date"].dropna().dt.to_period("M").astype(str))
            CON.say(f"보고서 캐시 재사용 {len(cached):,}건 ({len(done_m)}개월분)")
    if RESEARCH_COLLECT and RUN_MODE != "CACHED":
        months = pd.period_range(ts(start), ts(end), freq="M")
        cur = pd.Timestamp.today().to_period("M")
        todo = [p for p in months if (str(p) not in done_m) or (p >= cur - 1)]
        CON.say(f"리포트 신규 수집 대상: {len(todo)}개월 "
                f"(robots 제한 소스 — 사용자 지시에 따라 보수 속도로 수집)")

        def _one(p):
            if DEADLINE.over("리포트 수집"):
                return None
            rows = _hk_collect_month(p.year, p.month) + _nv_collect_month(p.year, p.month)
            return pd.DataFrame(rows) if rows else None

        got = pmap(_one, todo, workers=min(4, N_IO_THREADS), label="리포트수집")
        got = [g for g in got if g is not None and len(g)]
        if got:
            newdf = pd.concat(got, ignore_index=True)
            newdf["date"] = ts_col(newdf["date"])
            frames.append(newdf)
            FLOW.io("입", "HTTP", "리포트신규", newdf, src="한경+네이버")
    if not frames:
        return pd.DataFrame(columns=["source", "rid", "date", "title", "stock_code",
                                     "stock_name", "broker", "analyst", "target_price",
                                     "opinion", "pdf_url", "detail_url"])
    rep = pd.concat(frames, ignore_index=True)
    rep["date"] = ts_col(rep["date"])
    rep = rep.dropna(subset=["date"])
    rep = rep[(rep["date"] >= ts(start) - pd.Timedelta(400, "D"))
              & (rep["date"] <= ts(end) + pd.Timedelta(7, "D"))]
    rep = rep.drop_duplicates(subset=["source", "rid"], keep="last").reset_index(drop=True)
    DEPOT.table_save("scg_reports_raw", rep, scope="공용", domain="research",
                     source="hankyung+naver+cache")
    return rep


def _adapt_foreign_reports(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """다른 전략이 만든 보고서 원장(컬럼명이 다른)을 이 코드의 표준 스키마로 변환."""
    if df is None or not len(df):
        return None
    df = df.reset_index(drop=True)      # 외부 캐시의 중복 인덱스가 reindex 를 깨뜨린다
    m = {str(c).lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in m:
                return df[m[n]]
        return pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame({
        "source": pick("source").fillna("cache").astype(str),
        "rid": pick("rid", "src_report_id", "report_uid", "report_id").astype(str),
        "date": ts_col(pick("date", "pub_date", "report_date", "event_date")),
        "title": pick("title", "report_title").astype(str),
        "stock_code": pick("stock_code", "code").map(code6),
        "stock_name": pick("stock_name", "name").astype(str),
        "broker": pick("broker", "broker_name", "broker_raw").astype(str),
        "analyst": pick("analyst", "analyst_raw", "analyst_name", "pdf_analysts").astype(str),
        "target_price": pd.to_numeric(pick("target_price", "pdf_target"), errors="coerce"),
        "opinion": pick("opinion", "rating").astype(str),
        "pdf_url": pick("pdf_url").astype(str),
        "detail_url": pick("detail_url").astype(str),
    })
    out = out.dropna(subset=["date"])
    # rid 가 없는 외부 원장은 그대로 두면 drop_duplicates(source,rid) 가 전체를
    # 소스당 1행으로 붕괴시킨다 — 행 내용으로 rid 를 합성해 이력을 보존한다.
    bad_rid = out["rid"].isin(("None", "nan", "", "NaT")) | out["rid"].isna()
    if bad_rid.any():
        out.loc[bad_rid, "rid"] = [
            h1(s, str(d), t[:60], b) for s, d, t, b in
            zip(out.loc[bad_rid, "source"], out.loc[bad_rid, "date"],
                out.loc[bad_rid, "title"], out.loc[bad_rid, "broker"])]
    return out if len(out) else None


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-e] PDF 원문 — 다운로드(blob) + EPS 추정치·작성자 추출                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _pdf_text(data: bytes, max_pages: int = 3) -> str:
    if not data or not data[:5].startswith(b"%PDF"):
        return ""
    if _fitz is not None:
        try:
            doc = _fitz.open(stream=data, filetype="pdf")
            t = "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count)))
            doc.close()
            return t
        except Exception:
            pass
    if _pdfplumber is not None:
        try:
            with _pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((pg.extract_text() or "")
                                 for pg in pdf.pages[:max_pages])
        except Exception:
            pass
    return ""


_EPS_LINE = re.compile(r"EPS[^\n]{0,120}", re.I)
_YEAR_HDR = re.compile(r"(20\d{2})\s*(?:\.?12)?\s*[EFP]?")
_NUM_TOK = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?")
_ANALYST_TOK = re.compile(r"([가-힣]{2,4})\s*(?:연구원|애널리스트|수석|책임|선임)?\s*"
                          r"(?:☎|Tel|T\.|\d{2,3}[-.)\s]\d{3,4})", re.I)


def _eps_from_text(text: str, report_year: int) -> Dict[str, float]:
    """리포트 본문 추정치 테이블에서 'EPS' 행을 찾아 {회계연도: 값} 으로.
    연도 헤더가 같은 줄 위쪽에 있는 경우가 대부분이라 근처 줄에서 연도열을 맞춘다."""
    out: Dict[str, float] = {}
    if not text:
        return out
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not re.search(r"\bEPS\b", ln, re.I):
            continue
        nums = [float(t.replace(",", "")) for t in _NUM_TOK.findall(ln.split("EPS")[-1])]
        nums = [v for v in nums if abs(v) < 5e6]
        if len(nums) < 2:
            continue
        years: List[int] = []
        for back in range(1, 7):                      # 위쪽 몇 줄에서 연도 헤더 찾기
            if i - back < 0:
                break
            ys = [int(y) for y in _YEAR_HDR.findall(lines[i - back])
                  if 2010 <= int(y) <= 2035]
            if len(ys) >= 2:
                years = ys
                break
        if not years:
            years = list(range(report_year - 1, report_year - 1 + len(nums)))
        for y, v in zip(years, nums):
            if report_year - 2 <= y <= report_year + 3:
                out[f"{y}FY"] = v
        if out:
            break
    return out


def enrich_with_pdf(rep: pd.DataFrame) -> pd.DataFrame:
    """PDF 에서 (a) 작성자(네이버 건 보강) (b) EPS 추정치를 추출해 원장에 붙인다.
    추출 결과는 표로 캐시되어 재실행 시 파싱을 건너뛴다."""
    cache = DEPOT.table_load("scg_pdf_extract", need_cols=["ruid"])
    done: Dict[str, dict] = {}
    if cache is not None and len(cache):
        for _, r in cache.iterrows():
            done[str(r["ruid"])] = r.to_dict()
        CON.say(f"PDF 추출 캐시 재사용 {len(done):,}건")
    rep = rep.copy()
    rep["ruid"] = [h1(s, r) for s, r in zip(rep["source"], rep["rid"])]
    need = rep[(rep["pdf_url"].astype(str).str.startswith("http"))
               & (~rep["ruid"].isin(done.keys()))]
    if RESEARCH_DOWNLOAD_PDF and RUN_MODE != "CACHED" and len(need):
        cap = RESEARCH_PDF_CAP_MONTH
        if cap and cap > 0:
            need = (need.assign(_m=need["date"].dt.to_period("M"))
                    .groupby("_m", group_keys=False).head(cap))
        CON.say(f"PDF 신규 수집·추출 대상 {len(need):,}건")

        def _one(row):
            if DEADLINE.over("PDF 추출"):
                return None
            ruid, url, y = row
            data = DEPOT.blob_bytes("research_pdf", ruid)
            if data is None:
                data = fetch(url, source="hankyung" if "hankyung" in url else "naver",
                             as_bytes=True)
                if data and data[:5].startswith(b"%PDF"):
                    DEPOT.blob_save("research_pdf", ruid, data, "pdf", source=url)
                else:
                    data = None
            if data is None:
                return (ruid, None)
            text = _pdf_text(data)
            eps = _eps_from_text(text, int(y))
            an = ",".join(dict.fromkeys(_ANALYST_TOK.findall(text[:2500])))[:80]
            return (ruid, dict(ruid=ruid, pdf_analysts=an,
                               eps_json=json.dumps(eps, ensure_ascii=False)))

        jobs = list(zip(need["ruid"], need["pdf_url"], need["date"].dt.year))
        got = pmap(_one, jobs, workers=min(6, N_IO_THREADS), label="PDF추출")
        n_new = 0
        for it in got:
            if it and it[1]:
                done[it[0]] = it[1]
                n_new += 1
        CON.say(f"PDF 추출 신규 {n_new:,}건 (누적 {len(done):,})")
        if n_new:
            DEPOT.table_save("scg_pdf_extract", pd.DataFrame(list(done.values())),
                             scope="공용", domain="research", source="pdf_parse")
    ex = pd.DataFrame(list(done.values())) if done else \
        pd.DataFrame(columns=["ruid", "pdf_analysts", "eps_json"])
    rep = rep.merge(ex, on="ruid", how="left")
    fill = (rep["analyst"].astype(str).str.strip() == "") & rep["pdf_analysts"].notna()
    rep.loc[fill, "analyst"] = rep.loc[fill, "pdf_analysts"]
    if fill.any():
        CON.ok(f"PDF 본문에서 작성자 {int(fill.sum()):,}건 보강(네이버 리스트에는 작성자가 없음)")
    return rep


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-f] 실적(EPS)·발표일 — DART 1순위(PIT 정확), 네이버금융 폴백(보수적 지연)               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_DART = "https://opendart.fss.or.kr/api/"


def _dart_json(ep: str, **params) -> Optional[dict]:
    if not DART_API_KEY or not QUOTA.alive("dart"):
        return None
    js = fetch_json(_DART + ep, source="dart",
                    params={"crtfc_key": DART_API_KEY, **params},
                    on_attempt=lambda: QUOTA.spend("dart"))
    st = str((js or {}).get("status", ""))
    if st in ("020", "021"):
        QUOTA.kill("dart", f"status {st} (일일 한도)")
        return None
    if st in ("010", "011", "012", "901"):
        CON.err(f"DART 인증 오류 status {st} — 키를 확인하세요")
        QUOTA.kill("dart", f"status {st} (인증)")
        return None
    return js if st == "000" else None


def _dart_corpmap(sec: pd.DataFrame) -> pd.DataFrame:
    cm = DEPOT.table_load("scg_dart_corpmap", foreign_patterns=["corpcode", "corp_map"],
                          need_cols=["corp_code", "code"])
    if cm is not None and len(cm):
        cm["code"] = cm["code"].map(code6)
        return cm.dropna(subset=["code"])
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "code"])
    raw = fetch(_DART + "corpCode.xml", source="dart", as_bytes=True,
                params={"crtfc_key": DART_API_KEY},
                on_attempt=lambda: QUOTA.spend("dart"))
    if not raw or not raw[:2] == b"PK":
        CON.warn("DART corpCode 수신 실패 — 실적은 네이버 폴백으로 진행")
        return pd.DataFrame(columns=["corp_code", "code"])
    import zipfile
    from xml.etree import ElementTree
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        xml = z.read(z.namelist()[0]).decode("utf-8", "replace")
        root = ElementTree.fromstring(xml)
        rows = [(el.findtext("corp_code"), code6(el.findtext("stock_code")))
                for el in root.iter("list")]
        cm = pd.DataFrame(rows, columns=["corp_code", "code"]).dropna()
        DEPOT.table_save("scg_dart_corpmap", cm, scope="공용", domain="dart", source="opendart")
        return cm
    except Exception as e:
        CON.warn(f"corpCode 해석 실패({type(e).__name__})")
        return pd.DataFrame(columns=["corp_code", "code"])


def _dart_filing_dates(start: str, end: str) -> pd.DataFrame:
    """정기공시(사업/반기/분기보고서) 접수일 — knowledge date 의 원천. 월 단위 증분 캐시."""
    cached = DEPOT.table_load("scg_dart_filings", need_cols=["stock_code", "rcept_dt"])
    have = set()
    if cached is not None and len(cached):
        cached["rcept_dt"] = ts_col(cached["rcept_dt"])
        have = set(cached["rcept_dt"].dt.to_period("M").astype(str))
    rows_new: List[dict] = []
    if DART_API_KEY and RUN_MODE != "CACHED":
        for p in pd.period_range(ts(start), ts(end), freq="M"):
            if str(p) in have and p < pd.Timestamp.today().to_period("M") - 1:
                continue
            if DEADLINE.over("DART 접수일 수집"):
                break
            page, month_rows, month_complete = 1, [], False
            while QUOTA.alive("dart") and not DEADLINE.over("DART 접수일 수집"):
                js = _dart_json("list.json", bgn_de=f"{p.start_time:%Y%m%d}",
                                end_de=f"{p.end_time:%Y%m%d}", pblntf_ty="A",
                                page_no=str(page), page_count="100")
                lst = (js or {}).get("list") or []
                for it in lst:
                    nm = str(it.get("report_nm", ""))
                    if not re.search(r"사업보고서|반기보고서|분기보고서", nm):
                        continue
                    month_rows.append(dict(stock_code=code6(it.get("stock_code")),
                                           corp_code=it.get("corp_code"),
                                           report_nm=nm, rcept_dt=ts(it.get("rcept_dt"))))
                if len(lst) < 100 or page >= int((js or {}).get("total_page", 1)):
                    month_complete = True
                    break
                page += 1
            # ★ 한도/시간예산으로 달 중간에 끊겼으면 그 달의 부분 페이지는 버린다 —
            #   부분 행이 캐시에 남으면 다음 실행이 그 달을 '완료'로 오인해 영영 안 채운다.
            if month_complete:
                rows_new.extend(month_rows)
    fr = [f for f in (cached, pd.DataFrame(rows_new) if rows_new else None)
          if f is not None and len(f)]
    if not fr:
        return pd.DataFrame(columns=["stock_code", "corp_code", "report_nm", "rcept_dt"])
    out = pd.concat(fr, ignore_index=True).dropna(subset=["rcept_dt"])
    out = out.drop_duplicates(["stock_code", "report_nm", "rcept_dt"])
    if rows_new:
        DEPOT.table_save("scg_dart_filings", out, scope="공용", domain="dart", source="opendart")
    return out


def _naver_annual_eps(code: str) -> Optional[pd.DataFrame]:
    """네이버금융 기업 요약표의 연간 EPS (DART 키 없을 때의 폴백). 발표일은 보수적 지연."""
    html = fetch(f"https://finance.naver.com/item/main.naver?code={code}", source="naver")
    if not html:
        return None
    sp = soup(html)
    if sp is None:
        return None
    try:
        tables = pd.read_html(io.StringIO(str(sp)), match="주요재무정보")
    except Exception:
        return None
    if not tables:
        return None
    t = tables[0]
    try:
        t.columns = [" ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)
                     for c in t.columns]
        first = t.columns[0]
        eps_row = t[t[first].astype(str).str.contains("EPS", na=False)]
        if not len(eps_row):
            return None
        rows = []
        for cname in t.columns[1:]:
            m = re.search(r"(20\d{2})\.12", str(cname))
            if not m or "(E)" in str(cname):
                continue
            v = pd.to_numeric(str(eps_row.iloc[0][cname]).replace(",", ""), errors="coerce")
            if pd.notna(v):
                y = int(m.group(1))
                rows.append(dict(stock_id=code, fiscal_period=f"{y}FY",
                                 forecast_metric="EPS", actual_value=float(v),
                                 actual_announcement_date=ts(f"{y+1}-03-31")))
        return pd.DataFrame(rows) if rows else None
    except Exception:
        return None


def collect_actual_eps(sec: pd.DataFrame, xsec: pd.DataFrame,
                       start: str, end: str) -> pd.DataFrame:
    """actuals: stock_id·fiscal_period(YYYYFY)·EPS·발표일.
    DART: 연결우선 당기순이익 ÷ FY말 상장주식수, 발표일 = 사업보고서 접수일(PIT 정확).
    폴백: 네이버 요약표 EPS + 보수적 발표일(FY말+90일)."""
    cached = DEPOT.table_load("scg_actual_eps",
                              need_cols=["stock_id", "fiscal_period", "actual_value",
                                         "actual_announcement_date"])
    if cached is not None and len(cached) > 500 and RUN_MODE == "CACHED":
        cached["actual_announcement_date"] = ts_col(cached["actual_announcement_date"])
        return cached
    y0, y1 = ts(start).year - 2, ts(end).year
    out_frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        cached["actual_announcement_date"] = ts_col(cached["actual_announcement_date"])
        out_frames.append(cached)
    have_keys = set()
    if out_frames:
        have_keys = set(zip(out_frames[0]["stock_id"], out_frames[0]["fiscal_period"]))

    cm = _dart_corpmap(sec)
    if len(cm) and QUOTA.alive("dart") and RUN_MODE != "CACHED":
        code2corp = cm.set_index("code")["corp_code"].to_dict()
        codes = [c for c in sec["code"] if c in code2corp]
        # 상장주식수는 단면에 이미 들어 있다 — 별도 조회 없이 (연도, 종목) 로 접는다.
        shares_map, first_shares = {}, {}
        if len(xsec) and "shares" in xsec.columns:
            sh = xsec.loc[xsec["shares"].notna() & (xsec["shares"] > 0),
                          ["date", "code", "shares"]].sort_values("date")
            sh["y"] = sh["date"].dt.year
            last_of_year = sh.drop_duplicates(["y", "code"], keep="last")
            shares_map = dict(zip(zip(last_of_year["y"], last_of_year["code"]),
                                  last_of_year["shares"]))
            first_of_code = sh.drop_duplicates("code", keep="first")
            first_shares = dict(zip(first_of_code["code"], first_of_code["shares"]))
        ni_rows: List[dict] = []
        corps = [code2corp[c] for c in codes]
        B = 100
        years = [y for y in range(y0, y1 + 1)]
        jobs = [(y, corps[i:i + B], codes[i:i + B]) for y in years
                for i in range(0, len(corps), B)]
        CON.say(f"DART 당기순이익 배치 수집: {len(jobs)}회 예정(연도 {y0}~{y1}, 100사/회)")
        for y, cbatch, kbatch in jobs:
            if not QUOTA.alive("dart"):
                CON.warn("DART 한도 신호로 잔여 배치를 중단 — 받은 만큼으로 진행합니다")
                break
            if DEADLINE.over("DART 실적 수집"):
                break
            js = _dart_json("fnlttMultiAcnt.json", corp_code=",".join(cbatch),
                            bsns_year=str(y), reprt_code="11011")
            for it in (js or {}).get("list") or []:
                if "당기순이익" not in str(it.get("account_nm", "")):
                    continue
                c = code6(it.get("stock_code"))
                try:
                    amt = float(str(it.get("thstrm_amount", "")).replace(",", ""))
                except Exception:
                    continue
                ni_rows.append(dict(code=c, year=y, ni=amt,
                                    fs=str(it.get("fs_div", "")),
                                    rcept=str(it.get("rcept_no", ""))[:8]))
        if ni_rows:
            ni = pd.DataFrame(ni_rows).dropna(subset=["code"])
            ni["fs_rank"] = (ni["fs"] == "CFS").astype(int)      # 연결(CFS) 우선
            ni = (ni.sort_values(["code", "year", "fs_rank"])
                    .drop_duplicates(["code", "year"], keep="last"))
            filings = _dart_filing_dates(start, end)
            ann_map = {}
            if len(filings):
                fy_fil = filings[filings["report_nm"].str.contains("사업보고서", na=False)]
                fy_fil = fy_fil.assign(y=fy_fil["report_nm"].str.extract(
                    r"\((\d{4})\.12\)")[0].astype(float))
                for _, r in fy_fil.dropna(subset=["stock_code", "y"]).iterrows():
                    ann_map[(r["stock_code"], int(r["y"]))] = r["rcept_dt"]
            rows = []
            n_no_shares = 0
            for _, r in ni.iterrows():
                y = int(r["year"])
                ann = ann_map.get((r["code"], y))
                if ann is None:
                    ann = ts(r["rcept"]) or ts(f"{y+1}-03-31")   # 접수번호 앞 8자리 = 접수일
                sh = (shares_map.get((y, r["code"])) or shares_map.get((y + 1, r["code"]))
                      or first_shares.get(r["code"]))            # 백테스트 창 이전 FY 폴백
                if not sh or not np.isfinite(sh) or sh <= 0:
                    n_no_shares += 1
                    continue
                rows.append(dict(stock_id=r["code"], fiscal_period=f"{y}FY",
                                 forecast_metric="EPS", actual_value=float(r["ni"]) / float(sh),
                                 actual_announcement_date=ann))
            new = pd.DataFrame(rows)
            new = new[~new.apply(lambda r: (r["stock_id"], r["fiscal_period"]) in have_keys,
                                 axis=1)] if have_keys and len(new) else new
            if n_no_shares:
                CON.say(f"주식수 스냅샷 부재로 제외된 실적 {n_no_shares:,}건 "
                        f"(초기 연도 커버리지 한계 — 표에 정직하게 남깁니다)")
            if len(new):
                out_frames.append(new)
                CON.ok(f"DART 실적 EPS {len(new):,}건 (발표일=사업보고서 접수일)")
    elif not DART_API_KEY:
        if out_frames and len(out_frames[0]) > 500:
            CON.say("DART 키 없음 — 캐시된 실적을 그대로 사용합니다(재수집 생략)")
        else:
            CON.warn("DART 키 없음 — EPS 실적은 네이버 요약표 폴백(발표일 보수적 FY말+90일). "
                     "정확도 점수의 시차 정밀도가 낮아집니다.")

            def _one_eps(c):
                if DEADLINE.over("네이버 실적"):
                    return None
                return _naver_annual_eps(c)

            got = pmap(_one_eps, list(sec["code"])[:1500],
                       workers=min(6, N_IO_THREADS), label="네이버실적")
            got = [g for g in got if g is not None]
            if got:
                out_frames.append(pd.concat(got, ignore_index=True))
    if not out_frames:
        return pd.DataFrame(columns=["stock_id", "fiscal_period", "forecast_metric",
                                     "actual_value", "actual_announcement_date"])
    out = (pd.concat(out_frames, ignore_index=True)
             .drop_duplicates(["stock_id", "fiscal_period", "forecast_metric"], keep="last"))
    DEPOT.table_save("scg_actual_eps", out, scope="공용", domain="fundamental",
                     source="dart+naver")
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S5] 보고서 ↔ 애널리스트 ↔ 종목 원장 — 엔터티 해소와 연결 감사                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_BROKER_ALIASES = [
    (r"미래에셋대우|미래에셋증권|미래에셋", "미래에셋증권"),
    (r"우리투자|NH투자|NH농협증권", "NH투자증권"),
    (r"현대증권|KB투자|KB증권", "KB증권"),
    (r"신한금융투자|신한투자|신한증권", "신한투자증권"),
    (r"하나금융투자|하나대투|하나증권", "하나증권"),
    (r"동양증권|유안타", "유안타증권"),
    (r"HMC투자|현대차증권|현대차투자", "현대차증권"),
    (r"하이투자|iM증권|DGB", "iM증권"),
    (r"이베스트|LS증권|이트레이드", "LS증권"),
    (r"KTB투자|다올투자|다올", "다올투자증권"),
    (r"동부증권|DB금융투자|DB증권", "DB증권"),
    (r"메리츠종금|메리츠증권|메리츠", "메리츠증권"),
    (r"삼성증권", "삼성증권"), (r"한국투자|한투", "한국투자증권"),
    (r"키움", "키움증권"), (r"대신", "대신증권"), (r"유진투자|유진증권", "유진투자증권"),
    (r"한화투자|한화증권", "한화투자증권"), (r"교보", "교보증권"), (r"IBK", "IBK투자증권"),
    (r"SK증권", "SK증권"), (r"카카오페이", "카카오페이증권"), (r"토스", "토스증권"),
    (r"신영", "신영증권"), (r"흥국", "흥국증권"), (r"상상인", "상상인증권"),
    (r"BNK", "BNK투자증권"), (r"케이프", "케이프투자증권"), (r"리딩", "리딩투자증권"),
    (r"NH선물|나무", "NH투자증권"), (r"골드만|Goldman", "골드만삭스"),
    # ★ JP모간을 모건스탠리보다 먼저 — 순서를 바꾸면 '모간' 패턴이 JP모간을 삼켜
    #   두 회사 동명 애널리스트가 한 실체로 병합된다(§45.1 위반)
    (r"JP모간|JP모건|JPMorgan|J\.P\.", "JP모간"),
    (r"모간스탠리|모건스탠리|Morgan\s*Stanley|모간|모건", "모건스탠리"),
    (r"UBS", "UBS"), (r"CLSA", "CLSA"), (r"노무라|Nomura", "노무라"),
]
_BROKER_RE = [(re.compile(p), c) for p, c in _BROKER_ALIASES]


def broker_canon(raw: str) -> Tuple[str, str]:
    """(broker_id, 표준명). 증권사 개명 이력(합병 포함)을 하나의 실체로 묶는다.
    이걸 안 하면 '미래에셋대우 김OO'과 '미래에셋증권 김OO'이 남남이 되어 이력이 끊긴다."""
    s = unicodedata.normalize("NFKC", str(raw or "")).strip()
    s = re.sub(r"리서치센터$|리서치$|투자증권$|증권$", "", s) or s
    for pat, canon in _BROKER_RE:
        if pat.search(str(raw or "")) or pat.search(s):
            return h1("brk", canon)[:12], canon
    canon = s if s else "미상출처"
    return h1("brk", canon)[:12], canon


_AN_SPLIT = re.compile(r"[,/·∙•|;]| 외 | 및 |\s{2,}")
_AN_TITLE = re.compile(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|파트장|RA)\b")


def split_analysts(raw: str) -> List[str]:
    out, seen = [], set()
    for tok in _AN_SPLIT.split(str(raw or "")):
        t = _AN_TITLE.sub("", re.sub(r"\([^)]*\)|외\s*\d+인?", "", tok)).strip()
        t = re.sub(r"\s+", "", t)
        if 2 <= len(t) <= 12 and re.fullmatch(r"[가-힣A-Za-z.\-]+", t) and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_ledger(rep: pd.DataFrame, sec: pd.DataFrame
                 ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """반환 (reports_master, analyst_master, link).

    · 다중소스 중복(같은 날·같은 증권사·같은 종목·유사 제목)은 1건으로 병합 — 병합키와
      병합 통계를 감사표에 남긴다.
    · analyst_id = (표준 증권사, 이름) 해시 — 이름만으로 다른 증권사 사람을 합치지 않는다
      (동명이인 위험, 명세 §45.1). 이직 시 새 id 가 되는 한계는 감사표에 명시.
    """
    rep = rep.copy()
    if "ruid" not in rep.columns:
        rep["ruid"] = [h1(s, r) for s, r in zip(rep["source"], rep["rid"])]
    # NaN 문자열화 사고 방지 — float NaN 이 'nan' 이름의 유령 애널리스트가 되지 않게
    for c in ("analyst", "title", "opinion", "broker", "stock_name", "pdf_url"):
        if c in rep.columns:
            rep[c] = rep[c].fillna("").astype(str).replace({"nan": "", "None": ""})
    bk = rep["broker"].map(broker_canon)
    rep["broker_id"] = [b[0] for b in bk]
    rep["broker_name"] = [b[1] for b in bk]
    # 종목코드 해소: 소스 제공 → 제목의 (6자리) → 종목명 사전
    n2c = {norm_name(n): c for c, n in zip(sec["code"], sec["name"]) if n}
    need = rep["stock_code"].isna() | (rep["stock_code"].astype(str) == "None")
    rep.loc[need, "stock_code"] = rep.loc[need, "title"].astype(str).str.extract(
        _TITLE_CODE, expand=False)
    need = rep["stock_code"].isna()
    rep.loc[need, "stock_code"] = rep.loc[need, "stock_name"].map(
        lambda s: n2c.get(norm_name(s)))
    rep["stock_code"] = rep["stock_code"].map(code6)

    rep["dedup_key"] = [h1(f"{d:%Y%m%d}" if pd.notna(d) else "", b, c or "",
                           norm_name(t)[:40])
                        for d, b, c, t in zip(rep["date"], rep["broker_id"],
                                              rep["stock_code"], rep["title"])]
    n_before = len(rep)
    agg = {"ruid": "min", "source": lambda s: "+".join(sorted(set(sum(
              (str(x).split("+") for x in s), [])))),
           "date": "first", "title": lambda s: max(s, key=lambda x: len(str(x))),
           "stock_code": "first", "stock_name": "first",
           "broker_id": "first", "broker_name": "first",
           "analyst": lambda s: max(s.fillna("").astype(str), key=len),
           "target_price": "max", "opinion": "first", "pdf_url": "first",
           "eps_json": lambda s: max((str(x) for x in s
                                      if pd.notna(x) and str(x) not in
                                      ("", "{}", "None", "nan")), key=len, default=None)}
    keep_cols = [c for c in agg if c in rep.columns]
    R = (rep.sort_values("date").groupby("dedup_key", as_index=False)
            .agg({c: agg[c] for c in keep_cols}))
    R["_merged_n"] = rep.groupby("dedup_key").size().reindex(R["dedup_key"]).to_numpy()
    CON.say(f"보고서 원장: 원시 {n_before:,} → 병합 후 {len(R):,} "
            f"(다중소스 중복 {n_before - len(R):,}건 병합)")

    links: List[dict] = []
    for r in R.itertuples(index=False):
        names = split_analysts(getattr(r, "analyst", ""))
        for i, nm in enumerate(names):
            links.append(dict(ruid=r.ruid, stock_code=r.stock_code, date=r.date,
                              broker_id=r.broker_id, broker_name=r.broker_name,
                              name=nm, role="주저자" if i == 0 else "공저자",
                              analyst_id=h1("an", r.broker_id, nm)[:14],
                              target_price=r.target_price,
                              link_src="리스트" if getattr(r, "analyst", "") else "PDF"))
    L = pd.DataFrame(links) if links else pd.DataFrame(
        columns=["ruid", "stock_code", "date", "broker_id", "broker_name", "name",
                 "role", "analyst_id", "target_price", "link_src"])
    if len(L):
        A = (L.groupby("analyst_id").agg(
                name=("name", "first"), broker_name=("broker_name", "first"),
                broker_id=("broker_id", "first"),
                first_seen=("date", "min"), last_seen=("date", "max"),
                n_reports=("ruid", "nunique"), n_stocks=("stock_code", "nunique"))
             .reset_index())
        dup = A.groupby("name")["analyst_id"].transform("size")
        A["name_ambiguous"] = dup > 1
    else:
        A = pd.DataFrame(columns=["analyst_id", "name", "broker_name", "broker_id",
                                  "first_seen", "last_seen", "n_reports", "n_stocks",
                                  "name_ambiguous"])
    return R, A, L


def audit_ledger(R: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame):
    """'보고서와 식별된 애널리스트가 제대로 연결되었는지, 다중소스 원장 연결은 확실한지'를
    한눈에 보는 감사표."""
    if not len(R):
        CON.warn("보고서 원장이 비었습니다 — 리포트 수집/캐시를 확인하세요")
        return
    R = R.copy()
    R["y"] = R["date"].dt.year
    linked = set(L["ruid"]) if len(L) else set()
    rows = []
    for y, g in R.groupby("y"):
        n = len(g)
        nl = int(g["ruid"].isin(linked).sum())
        nc = int(g["stock_code"].notna().sum())
        ntp = int(g["target_price"].notna().sum())
        neps = int(g["eps_json"].map(lambda s: bool(s) and s not in ("{}", "null", "None")
                                     ).sum()) if "eps_json" in g.columns else 0
        rows.append([int(y), f"{n:,}", f"{nl:,}", f"{nl/n*100:.0f}%",
                     f"{nc/n*100:.0f}%", f"{ntp/n*100:.0f}%", f"{neps:,}"])
    CON.grid(rows, ["연도", "보고서", "애널연결", "연결률", "종목코드율", "목표가율",
                    "EPS추출"],
             ["r"] * 7, title="원장 연결 감사 ① — 연도별 (보고서↔애널리스트↔종목)")
    src_rows = [[s, f"{n:,}"] for s, n in R["source"].value_counts().items()]
    CON.grid(src_rows, ["소스(병합 후)", "건수"], ["l", "r"],
             title="원장 연결 감사 ② — 다중소스 병합 상태 ('한경+네이버' = 양쪽에서 수집되어 1건으로 병합)")
    if len(A):
        amb = int(A["name_ambiguous"].sum())
        CON.grid([[f"{len(A):,}", f"{A['n_reports'].median():.0f}",
                   f"{amb:,}", f"{L['link_src'].eq('PDF').mean()*100 if len(L) else 0:.0f}%"]],
                 ["식별 애널리스트", "인당 보고서(중앙값)", "동명이인(타사)", "PDF연결 비중"],
                 ["r"] * 4, title="원장 연결 감사 ③ — 애널리스트 실체")
        CON.say("한계 명시: analyst_id 는 (증권사,이름) 단위 — 이직 시 새 실체가 됩니다. "
                "이름만으로 타사 동일인을 합치지 않는 것은 명세 §45.1의 의도적 선택입니다.")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S6] 예측 테이블 — analyst_forecasts(EPS·TP12M) · actuals · 주지표 자동선택               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
FC_KEY = ["stock_id", "analyst_id", "fiscal_period", "forecast_metric"]
CS_KEY = ["stock_id", "fiscal_period", "forecast_metric"]


def build_forecasts(R: pd.DataFrame, L: pd.DataFrame) -> pd.DataFrame:
    """보고서 원장 → 표준 예측 테이블
    stock_id·analyst_id·broker_id·report_id·report_date·fiscal_period·forecast_metric·forecast_value
    · EPS: PDF 추출 {연도FY: 값}
    · TP12M: 목표주가(12개월 목표 관행) — fiscal_period='12M'
    한 보고서에 공저자가 있으면 주저자에게 귀속(표결권 1표 원칙 §2.1)."""
    if not len(R) or not len(L):
        return pd.DataFrame(columns=FC_KEY + ["broker_id", "report_id", "report_date",
                                              "forecast_value"])
    lead = L[L["role"] == "주저자"].drop_duplicates("ruid")
    # broker_id 는 원장(R)에 이미 있으므로 링크에서는 analyst_id 만 가져온다
    # (양쪽에서 겹쳐 오면 _x/_y 로 갈라져 하류가 조용히 깨진다)
    base = R.merge(lead[["ruid", "analyst_id"]], on="ruid", how="inner")
    rows: List[dict] = []
    for r in base.itertuples(index=False):
        if pd.isna(r.date) or pd.isna(r.stock_code) or r.stock_code is None:
            continue
        tp = getattr(r, "target_price", None)
        if tp is not None and pd.notna(tp):
            rows.append(dict(stock_id=r.stock_code, analyst_id=r.analyst_id,
                             broker_id=r.broker_id, report_id=r.ruid,
                             report_date=r.date, fiscal_period="12M",
                             forecast_metric="TP12M", forecast_value=float(tp)))
        ej = getattr(r, "eps_json", None)
        if ej and str(ej) not in ("{}", "null", "None", "nan"):
            try:
                d = json.loads(ej)
            except Exception:
                d = {}
            for fp, v in d.items():
                try:
                    v = float(v)
                except Exception:
                    continue
                if np.isfinite(v):
                    rows.append(dict(stock_id=r.stock_code, analyst_id=r.analyst_id,
                                     broker_id=r.broker_id, report_id=r.ruid,
                                     report_date=r.date, fiscal_period=str(fp),
                                     forecast_metric="EPS", forecast_value=v))
    fc = pd.DataFrame(rows)
    if len(fc):
        fc = (fc.sort_values("report_date")
                .drop_duplicates(FC_KEY + ["report_date"], keep="last")
                .reset_index(drop=True))
    CON.say(f"예측 테이블: {len(fc):,}행 "
            f"(EPS {int((fc['forecast_metric']=='EPS').sum()) if len(fc) else 0:,} / "
            f"TP12M {int((fc['forecast_metric']=='TP12M').sum()) if len(fc) else 0:,})")
    return fc


def tp_actuals_from_prices(fc: pd.DataFrame, pm: "PriceMatrix",
                           cal: "TradingCal") -> pd.DataFrame:
    """TP12M 정확도 사건용 실측치: 각 보고서의 '12개월 뒤 실제 주가'.
    (EPS 의 실적발표일에 해당하는 것이 목표주가의 '만기일' — 만기가 지난 사건만 쓴다)

    ★ 가격은 이미 만들어 둔 PriceMatrix 에서 벡터로 뽑는다. 종목별 재조회를 하지 않는다.
    단면은 월말 중심이므로 만기 허용오차를 25일까지 둔다(12개월 목표가의 성격상 무해)."""
    cols = ["report_id", "matured_at", "actual_price"]
    if not len(fc):
        return pd.DataFrame(columns=cols)
    tp = fc[fc["forecast_metric"] == "TP12M"]
    if not len(tp) or pm is None:
        return pd.DataFrame(columns=cols)
    mat_map = {d: cal.shift(d, 252) for d in tp["report_date"].unique()}
    mat = tp["report_date"].map(mat_map)
    ok = mat.notna()
    tp = tp[ok.to_numpy()]
    mat = mat[ok.to_numpy()]
    if not len(tp):
        return pd.DataFrame(columns=cols)
    ri = pd.Index(tp["stock_id"].astype(str)).map(pm.row_of)
    ci = np.searchsorted(pm.cols, mat.to_numpy("datetime64[ns]"), side="right") - 1
    # 발행일이 속한 열 — 목표주가는 '그 시점의 주가 단위'로 제시되므로 만기 가격을
    # 발행 시점 단위로 되돌려 비교해야 한다(분할이 끼면 5배 어긋나 정확도가 0이 된다).
    ci0 = np.searchsorted(pm.cols, tp["report_date"].to_numpy("datetime64[ns]"),
                          side="right") - 1
    row = np.asarray(ri, dtype=float)
    good = np.isfinite(row) & (ci >= 0) & (ci0 >= 0)
    if not good.any():
        return pd.DataFrame(columns=cols)
    ri_i = row[good].astype(int)
    ci_i = ci[good]
    ci0_i = ci0[good]
    gap = (mat.to_numpy("datetime64[ns]")[good] - pm.cols[ci_i]).astype("timedelta64[D]")
    within = gap.astype(int) <= 25
    r_i, c_i, c0_i = ri_i[within], ci_i[within], ci0_i[within]
    px = pm.adj.to_numpy(float)[r_i, c_i] / pm.cum[r_i, c0_i]
    out = pd.DataFrame({"report_id": tp["report_id"].to_numpy()[good][within],
                        "matured_at": pd.DatetimeIndex(pm.cols[c_i]),
                        "actual_price": px})
    return out[np.isfinite(out["actual_price"])].reset_index(drop=True)


def choose_metric(fc: pd.DataFrame) -> Tuple[str, pd.DataFrame]:
    """주지표 자동선택(AUTO): '월별로 애널리스트 2명 이상이 붙는 종목 수'가 판단 기준.
    EPS 커버리지가 실전 최소선을 넘으면 명세 기본(EPS), 아니면 TP12M."""
    stats = []
    for met in ("EPS", "TP12M"):
        f = fc[fc["forecast_metric"] == met]
        if not len(f):
            stats.append([met, 0, 0])
            continue
        f = f.assign(m=f["report_date"].dt.to_period("M"))
        g = (f.groupby(["m", "stock_id"], observed=True)["analyst_id"].nunique()
             .reset_index())
        per_m = g[g["analyst_id"] >= 2].groupby("m")["stock_id"].nunique()
        stats.append([met, int(per_m.median()) if len(per_m) else 0, int(len(f))])
    tab = pd.DataFrame(stats, columns=["metric", "월중앙_2인이상_종목수", "예측행수"])
    CON.grid(tab.values.tolist(), list(tab.columns), ["l", "r", "r"],
             title="주지표 선택 근거 (FORECAST_METRIC_MODE="
                   f"{FORECAST_METRIC_MODE})")
    if FORECAST_METRIC_MODE in ("EPS", "TP12M"):
        return FORECAST_METRIC_MODE, tab
    eps_cov = tab.loc[tab["metric"] == "EPS", "월중앙_2인이상_종목수"].iloc[0]
    tp_cov = tab.loc[tab["metric"] == "TP12M", "월중앙_2인이상_종목수"].iloc[0]
    met = "EPS" if (eps_cov >= 40 and eps_cov >= 0.30 * max(tp_cov, 1)) else "TP12M"
    CON.ok(f"주지표 자동선택: {met} "
           f"(EPS 커버리지 {eps_cov} vs TP12M {tp_cov} — 기준: EPS≥40 이고 TP의 30% 이상. "
           f"명세 §1 기본은 EPS, TP12M 은 커버리지 부족 시의 검증 경로)")
    return met, tab


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S7] SCG 엔진 — 명세서 산식의 축자 구현                                                    ║
# ║  하드게이트 금지(§31) · 수축으로 중립화(§10,17) · PIT 롤링(§45.5) · t20<T(§16)             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
class SCGParams:
    """공식 V1 파라미터(§42) — 단일 출처. 민감도는 variant() 사본으로만 돌린다.
    '가장 좋았던 조합을 사후 채택'하는 것은 §41이 금지한다: 공식값은 45/6/20 고정."""
    V1 = dict(
        MIN_ANALYSTS=2, MAX_FORECAST_AGE_DAYS=180,
        FORECAST_HALFLIFE_DAYS=45.0,
        ACCURACY_HISTORY_HALFLIFE_DAYS=365.0, LEAD_HISTORY_HALFLIFE_DAYS=365.0,
        K_ACC=6.0, K_LEAD=6.0, ACC_WEIGHT=0.60, LEAD_WEIGHT=0.40,
        QUALITY_EXP_SCALE=0.70, QUALITY_MULTIPLIER_MIN=0.50, QUALITY_MULTIPLIER_MAX=2.00,
        LEAD_FORWARD_TRADING_DAYS=20, ACCEL_LOOKBACK_TRADING_DAYS=20,
        SCG_LEVEL_WEIGHT=0.75, SCG_ACCEL_WEIGHT=0.25,
        DENOM_FLOOR_RATIO=0.10, EPSILON=1e-8,
        WINSOR_LOWER=0.01, WINSOR_UPPER=0.99, MIN_CROSS_SECTION_FOR_WINSOR=30,
        ACC_EVENT_CLIP=2.0, LEAD_EVENT_CLIP=1.0,
    )

    def __init__(self, **over):
        bad = set(over) - set(self.V1)
        if bad:
            raise ValueError(f"SCGParams 알 수 없는 키: {sorted(bad)}")
        for k, v in self.V1.items():
            setattr(self, k, over.get(k, v))

    def variant(self, **over) -> "SCGParams":
        cur = {k: getattr(self, k) for k in self.V1}
        cur.update(over)
        return SCGParams(**cur)

    def tag(self) -> str:
        return (f"HL{self.FORECAST_HALFLIFE_DAYS:g}/K{self.K_ACC:g}"
                f"/LD{self.LEAD_FORWARD_TRADING_DAYS}")


STRATS = ["BASE_REV", "SCG_0", "SCG_LS", "SCG_LSA"]      # §30 — 반드시 4종 독립 산출


class TradingCal:
    """거래일 캘린더(§4) — 20일은 달력일이 아니라 거래일이다."""

    def __init__(self, dates):
        d = pd.DatetimeIndex(pd.to_datetime(list(dates))).normalize().unique().sort_values()
        if len(d) < 30:
            raise HaltRun(f"거래일 캘린더가 {len(d)}일 — 가격 수집이 부족합니다")
        self.days = d
        self._v = d.values.astype("datetime64[D]").astype(np.int64)

    def pos(self, t) -> int:
        return int(np.searchsorted(self._v,
                                   np.datetime64(pd.Timestamp(t).normalize(), "D")
                                   .astype(np.int64), side="right")) - 1

    def shift(self, t, n: int) -> Optional[pd.Timestamp]:
        p = self.pos(t)
        if p < 0:
            return None
        q = p + n
        if q < 0 or q >= len(self.days):
            return None
        return self.days[q]


def xs_winsor(v: np.ndarray, lo: float, hi: float, min_n: int) -> np.ndarray:
    x = np.asarray(v, float)
    m = np.isfinite(x)
    if m.sum() < min_n:                      # 표본이 작으면 손대지 않는다(§24)
        return x
    ql, qh = np.nanquantile(x[m], [lo, hi])
    return np.clip(x, ql, qh)


def validate_forecasts(fc: pd.DataFrame, asof=None) -> pd.DataFrame:
    need = FC_KEY + ["report_date", "forecast_value"]
    miss = [c for c in need if c not in fc.columns]
    if miss:
        raise RuleBreak(f"예측 테이블 필수 컬럼 누락: {miss} (§2.1)")
    fc = fc.copy()
    fc["report_date"] = ts_col(fc["report_date"])
    fc["forecast_value"] = pd.to_numeric(fc["forecast_value"], errors="coerce")
    n0 = len(fc)
    fc = fc.dropna(subset=["forecast_value", "report_date", "stock_id", "analyst_id"])
    if n0 - len(fc):
        CON.say(f"NaN 예측 {n0-len(fc):,}행 제외 — 해당 행만 제외, 실체는 유지(§32)")
    if asof is not None:
        fut = fc["report_date"] > ts(asof)
        if fut.any():
            raise RuleBreak(f"[PIT] 기준시점 이후 report_date {int(fut.sum())}건 — 즉시 오류(§32)")
    return (fc.sort_values("report_date", kind="stable")
              .drop_duplicates(FC_KEY + ["report_date"], keep="last")
              .reset_index(drop=True))


def with_validity(fc: pd.DataFrame, cfg: SCGParams) -> pd.DataFrame:
    """각 전망의 활성 구간 [발표일, 다음 전망일 또는 +180일). 같은 키의 새 전망이 옛 것을
    대체하므로 (stock,analyst,fp,metric,T) 활성표는 최대 1개 — TEST 8 이 구조로 보장된다."""
    fc = fc.sort_values(FC_KEY + ["report_date"], kind="mergesort").reset_index(drop=True)
    nxt = fc.groupby(FC_KEY, observed=True, sort=False)["report_date"].shift(-1)
    exp = fc["report_date"] + pd.Timedelta(int(cfg.MAX_FORECAST_AGE_DAYS) + 1, "D")
    fc["valid_until"] = np.minimum(nxt.fillna(pd.Timestamp("2262-01-01")).to_numpy(),
                                   exp.to_numpy())
    return fc


def active_at(fcv: pd.DataFrame, T: pd.Timestamp) -> pd.DataFrame:
    t = np.datetime64(pd.Timestamp(T).normalize())
    rd = fcv["report_date"].to_numpy("datetime64[ns]")
    vu = fcv["valid_until"].to_numpy("datetime64[ns]")
    sub = fcv.loc[(rd <= t) & (t < vu),
                  FC_KEY + ["broker_id", "report_id", "report_date", "forecast_value"]
                  if "broker_id" in fcv.columns else
                  FC_KEY + ["report_id", "report_date", "forecast_value"]].copy()
    sub.insert(0, "signal_date", pd.Timestamp(T).normalize())
    sub["forecast_age_days"] = (sub["signal_date"] - sub["report_date"]).dt.days
    return sub


# ── Accuracy 사건 (§7~8) ────────────────────────────────────────────────────────────────────
def acc_events_eps(fc: pd.DataFrame, actuals: pd.DataFrame, cfg: SCGParams) -> pd.DataFrame:
    cols = ["analyst_id", "stock_id", "fiscal_period", "forecast_metric",
            "completion_date", "acc_event", "n_forecasters"]
    f = fc[fc["forecast_metric"] == "EPS"]
    a = actuals[actuals["forecast_metric"] == "EPS"] if len(actuals) else actuals
    if not len(f) or a is None or not len(a):
        return pd.DataFrame(columns=cols)
    m = f.merge(a[["stock_id", "fiscal_period", "forecast_metric", "actual_value",
                   "actual_announcement_date"]], on=CS_KEY, how="inner")
    age = (m["actual_announcement_date"] - m["report_date"]).dt.days
    m = m[(age > 0) & (age <= cfg.MAX_FORECAST_AGE_DAYS)]      # 발표 '전' 최신 + stale 제외
    if not len(m):
        return pd.DataFrame(columns=cols)
    m = (m.sort_values("report_date", kind="stable")
          .drop_duplicates(FC_KEY, keep="last"))               # 애널리스트당 1표(§2.1)
    return _acc_from_snapshot(m, cfg, cols)


def _acc_from_snapshot(m: pd.DataFrame, cfg: SCGParams, cols: List[str]) -> pd.DataFrame:
    g = m.groupby(CS_KEY + ["actual_announcement_date"], observed=True, sort=False)
    m = m.assign(_C=g["forecast_value"].transform("mean"),
                 _MAF=g["forecast_value"].transform(
                     lambda s: float(np.median(np.abs(s)))),
                 _N=g["forecast_value"].transform("size"))
    # n=1 이면 C≡F_j 라 산식이 자연히 0 사건을 낳는다 — §10 의 λ=n/(n+K) 는 이 관측도
    # 세므로, 억지로 걸러 n 을 줄이지 않는다(명세 산술 그대로).
    if not len(m):
        return pd.DataFrame(columns=cols)
    eps = cfg.EPSILON
    A = m["actual_value"].to_numpy(float)
    Fj = m["forecast_value"].to_numpy(float)
    C = m["_C"].to_numpy(float)
    scale = np.maximum.reduce([np.abs(A), m["_MAF"].to_numpy(float),
                               np.full(len(m), eps)])          # §8.1 안정화
    ev = np.log((np.abs(C - A) / scale + eps) / (np.abs(Fj - A) / scale + eps))
    ev = np.clip(ev, -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)  # §8 극단치 억제
    out = m[["analyst_id", "stock_id", "fiscal_period", "forecast_metric"]].copy()
    out["completion_date"] = m["actual_announcement_date"].to_numpy()
    out["acc_event"] = ev
    out["n_forecasters"] = m["_N"].to_numpy()
    return out.reset_index(drop=True)


def acc_events_tp(fc: pd.DataFrame, tp_act: pd.DataFrame, cfg: SCGParams) -> pd.DataFrame:
    """TP12M 정확도: 만기(발행+252거래일)가 지난 목표가만, '당시 동료 컨센서스 대비'
    실제 주가를 누가 더 잘 맞혔는지. EPS 산식(§8)과 동일 구조 — 만기일이 완결일."""
    cols = ["analyst_id", "stock_id", "fiscal_period", "forecast_metric",
            "completion_date", "acc_event", "n_forecasters"]
    f = fc[fc["forecast_metric"] == "TP12M"]
    if not len(f) or tp_act is None or not len(tp_act):
        return pd.DataFrame(columns=cols)
    m = f.merge(tp_act, on="report_id", how="inner")
    if not len(m):
        return pd.DataFrame(columns=cols)
    # '같은 만기 무렵'의 동료 = 같은 종목에서 ±45일 내 발행된 목표가들 → 발행월 버킷으로 근사
    m = m.assign(_bucket=m["report_date"].dt.to_period("M").astype(str))
    g = m.groupby(["stock_id", "_bucket"], observed=True, sort=False)
    m = m.assign(_C=g["forecast_value"].transform("mean"),
                 _MAF=g["forecast_value"].transform(lambda s: float(np.median(np.abs(s)))),
                 _N=g["forecast_value"].transform("size"),
                 actual_value=m["actual_price"],
                 actual_announcement_date=m["matured_at"])
    # EPS 쪽과 같은 이유로 n=1 사건도 유지(값은 자연히 0) — §10 관측수 산술 보존
    if not len(m):
        return pd.DataFrame(columns=cols)
    eps = cfg.EPSILON
    A = m["actual_value"].to_numpy(float)
    Fj = m["forecast_value"].to_numpy(float)
    C = m["_C"].to_numpy(float)
    scale = np.maximum.reduce([np.abs(A), m["_MAF"].to_numpy(float),
                               np.full(len(m), eps)])
    ev = np.clip(np.log((np.abs(C - A) / scale + eps) / (np.abs(Fj - A) / scale + eps)),
                 -cfg.ACC_EVENT_CLIP, cfg.ACC_EVENT_CLIP)
    out = m[["analyst_id", "stock_id", "fiscal_period", "forecast_metric"]].copy()
    out["completion_date"] = m["actual_announcement_date"].to_numpy()
    out["acc_event"] = ev
    out["n_forecasters"] = m["_N"].to_numpy()
    return out.reset_index(drop=True)


# ── Leadership 사건 (§11~16) ────────────────────────────────────────────────────────────────
def lead_events(fc: pd.DataFrame, cal: TradingCal, cfg: SCGParams,
                metric: str) -> pd.DataFrame:
    """수정 후 20거래일간 leave-one-out 동료 컨센서스가 같은 방향으로 움직였는가.
    · 자기 자신은 t0/t20 양쪽에서 반드시 제외(§13, TEST 7)
    · peer 없으면 그 사건만 미생성(§15) · t20 이 캘린더 밖이면 미완결로 미생성
    · revision=0 은 사건이 아니다(§12). 크기 하드게이트는 두지 않는다."""
    cols = ["analyst_id", "stock_id", "fiscal_period", "forecast_metric",
            "event_date", "completion_date", "lead_event", "rev_magnitude"]
    f = fc[fc["forecast_metric"] == metric]
    if not len(f):
        return pd.DataFrame(columns=cols)
    eps = cfg.EPSILON
    H = int(cfg.LEAD_FORWARD_TRADING_DAYS)
    max_age_ns = np.timedelta64(int(cfg.MAX_FORECAST_AGE_DAYS), "D")
    f = f.sort_values(CS_KEY + ["analyst_id", "report_date"], kind="mergesort")
    rows: List[tuple] = []
    for key, grp in f.groupby(CS_KEY, observed=True, sort=False):
        aids = grp["analyst_id"].unique()
        if len(aids) < 2:
            continue
        per: Dict[Any, Tuple[np.ndarray, np.ndarray]] = {}
        for aid, ga in grp.groupby("analyst_id", observed=True, sort=False):
            per[aid] = (ga["report_date"].to_numpy("datetime64[ns]"),
                        ga["forecast_value"].to_numpy(float))

        def peer_consensus(excl, q):
            vals = []
            for a2, (d2, v2) in per.items():
                if a2 == excl:
                    continue
                i = int(np.searchsorted(d2, q, side="right")) - 1
                if i >= 0 and (q - d2[i]) <= max_age_ns:
                    vals.append(v2[i])
            return vals

        for aid, (d1, v1) in per.items():
            for k in range(1, len(d1)):
                f_old, f_new = v1[k - 1], v1[k]
                if not (np.isfinite(f_old) and np.isfinite(f_new)) or f_new == f_old:
                    continue
                t0 = pd.Timestamp(d1[k])
                t20 = cal.shift(t0, H)
                if t20 is None:
                    continue
                p0 = peer_consensus(aid, d1[k])
                p20 = peer_consensus(aid, np.datetime64(t20))
                if not p0 or not p20:
                    continue
                c0, c20 = float(np.mean(p0)), float(np.mean(p20))
                maf = float(np.median(np.abs(np.array(p0 + [f_old, f_new]))))
                scale_c = max(abs(c0), maf, eps)                       # §14
                lead = float(np.clip(np.sign(f_new - f_old) * (c20 - c0) / scale_c,
                                     -cfg.LEAD_EVENT_CLIP, cfg.LEAD_EVENT_CLIP))
                rev = (f_new - f_old) / max(abs(f_old), maf, eps)      # §12 (진단용 기록)
                rows.append((aid, *key, t0, t20, lead, rev))
    out = pd.DataFrame(rows, columns=cols)
    if len(out):
        out["event_date"] = ts_col(out["event_date"])
        out["completion_date"] = ts_col(out["completion_date"])
    return out


# ── PIT 롤링 점수 (§9~10, §17~18) ───────────────────────────────────────────────────────────
_DAY_NS = 86_400_000_000_000
_T_ORIGIN = pd.Timestamp("2010-01-01").value


def _daynum(x) -> np.ndarray:
    a = pd.to_datetime(pd.Series(list(x))).to_numpy("datetime64[ns]").astype(np.int64)
    return (a - _T_ORIGIN) / _DAY_NS


class DecayBook:
    """사건(완결일,값) → 임의 T 의 반감기 가중평균을 O(log n) 조회.
    w=2^{t/H} 누적합으로 분해 — 비율에서 2^{-T/H} 가 소거되어 수치도 안전하다."""

    def __init__(self, ev: pd.DataFrame, col: str, halflife: float):
        self.by: Dict[Any, tuple] = {}
        if ev is None or not len(ev):
            return
        ev = ev.sort_values("completion_date", kind="mergesort")
        for aid, g in ev.groupby("analyst_id", observed=True, sort=False):
            t = _daynum(g["completion_date"])
            w = np.power(2.0, t / float(halflife))
            v = g[col].to_numpy(float)
            self.by[aid] = (t, np.cumsum(w * v), np.cumsum(w))

    def at(self, aid, T_day: float) -> Tuple[float, int]:
        rec = self.by.get(aid)
        if rec is None:
            return np.nan, 0
        t, cn, cd = rec
        i = int(np.searchsorted(t, T_day, side="left"))    # 완결일 < T 만(§16, §3)
        if i <= 0:
            return np.nan, 0
        return (cn[i - 1] / cd[i - 1] if cd[i - 1] > 0 else np.nan), i


def analyst_scores(signal_dates, acc_ev: pd.DataFrame, led_ev: pd.DataFrame,
                   cfg: SCGParams) -> pd.DataFrame:
    """analyst_score_history (§33.1). 모든 signal date 에서 PIT 롤링 — 전체기간 선계산 금지."""
    A = DecayBook(acc_ev, "acc_event", cfg.ACCURACY_HISTORY_HALFLIFE_DAYS)
    Ld = DecayBook(led_ev, "lead_event", cfg.LEAD_HISTORY_HALFLIFE_DAYS)
    aids = sorted(set(A.by) | set(Ld.by))
    rows = []
    for T in signal_dates:
        Td = float(_daynum([T])[0])
        for aid in aids:
            ar, an = A.at(aid, Td)
            lr, ln = Ld.at(aid, Td)
            al = an / (an + cfg.K_ACC) if an else 0.0          # §10 수축
            ll = ln / (ln + cfg.K_LEAD) if ln else 0.0         # §17
            a_star = al * ar if an else 0.0                    # prior=0
            l_star = ll * lr if ln else 0.0
            rows.append((pd.Timestamp(T), aid, ar if an else np.nan, an, al, a_star,
                         lr if ln else np.nan, ln, ll, l_star,
                         cfg.ACC_WEIGHT * a_star + cfg.LEAD_WEIGHT * l_star))   # §18
    return pd.DataFrame(rows, columns=[
        "signal_date", "analyst_id", "acc_raw", "acc_n", "acc_lambda", "acc_star",
        "lead_raw", "lead_n", "lead_lambda", "lead_star", "quality_score_ls"])


# ── Smart Consensus (§19~23) ───────────────────────────────────────────────────────────────
def smart_consensus(fcv: pd.DataFrame, scores: pd.DataFrame, signal_dates,
                    cfg: SCGParams, metric: str,
                    keep_weights: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """signal date 마다: 활성전망 → RECENCY×품질승수 가중 → SC⁰/SC^LS.
    반환 (consensus rows, analyst_forecast_weights §33.2)."""
    sc_map: Dict[pd.Timestamp, pd.DataFrame] = {}
    if len(scores):
        for T, g in scores.groupby("signal_date", observed=True):
            sc_map[pd.Timestamp(T)] = g.set_index("analyst_id")[
                ["acc_star", "lead_star", "quality_score_ls"]]
    cons_parts, w_parts = [], []
    fm = fcv[fcv["forecast_metric"] == metric]
    lo, hi = cfg.QUALITY_MULTIPLIER_MIN, cfg.QUALITY_MULTIPLIER_MAX
    for T in signal_dates:
        act = active_at(fm, T)
        if not len(act):
            continue
        sc = sc_map.get(pd.Timestamp(T))
        if sc is not None:
            act = act.join(sc, on="analyst_id")
        for c in ("acc_star", "lead_star", "quality_score_ls"):
            if c not in act.columns:
                act[c] = 0.0
            act[c] = act[c].fillna(0.0)          # 이력 없음 = 중립(§32, TEST 2)
        act["recency_weight"] = np.power(
            2.0, -act["forecast_age_days"].to_numpy(float) / cfg.FORECAST_HALFLIFE_DAYS)
        act["quality_multiplier_scg0"] = np.clip(
            np.exp(cfg.QUALITY_EXP_SCALE * act["acc_star"]), lo, hi)          # §21
        act["quality_multiplier_ls"] = np.clip(
            np.exp(cfg.QUALITY_EXP_SCALE * act["quality_score_ls"]), lo, hi)  # §20,22
        act["weight_scg0"] = act["recency_weight"] * act["quality_multiplier_scg0"]
        act["weight_ls"] = act["recency_weight"] * act["quality_multiplier_ls"]
        act["_wf0"] = act["weight_scg0"] * act["forecast_value"]
        act["_wfl"] = act["weight_ls"] * act["forecast_value"]
        g = act.groupby(CS_KEY, observed=True, sort=False)
        agg = g.agg(analyst_count=("analyst_id", "size"),
                    consensus_equal_weight=("forecast_value", "mean"),
                    _w0=("weight_scg0", "sum"), _wl=("weight_ls", "sum"),
                    _f0=("_wf0", "sum"), _fl=("_wfl", "sum")).reset_index()
        agg.insert(0, "signal_date", pd.Timestamp(T))
        agg["smart_consensus_scg0"] = agg["_f0"] / agg["_w0"].where(agg["_w0"] > 0)
        agg["smart_consensus_ls"] = agg["_fl"] / agg["_wl"].where(agg["_wl"] > 0)
        insuff = agg["analyst_count"] < cfg.MIN_ANALYSTS
        agg["status"] = np.where(insuff, "INSUFFICIENT_ANALYSTS", "OK")   # §6.2 — 제거 아님
        agg.loc[insuff, ["smart_consensus_scg0", "smart_consensus_ls"]] = np.nan
        cons_parts.append(agg.drop(columns=["_w0", "_wl", "_f0", "_fl"]))
        if keep_weights:
            keep = ["signal_date"] + CS_KEY + ["analyst_id", "forecast_value",
                    "report_date", "forecast_age_days", "recency_weight",
                    "acc_star", "lead_star", "quality_score_ls",
                    "quality_multiplier_scg0", "quality_multiplier_ls",
                    "weight_scg0", "weight_ls"]
            w_parts.append(act[[c for c in keep if c in act.columns]])
    if not cons_parts:
        return (pd.DataFrame(columns=["signal_date"] + CS_KEY + [
            "analyst_count", "consensus_equal_weight", "smart_consensus_scg0",
            "smart_consensus_ls", "status"]), pd.DataFrame())
    cons = pd.concat(cons_parts, ignore_index=True)
    W = pd.concat(w_parts, ignore_index=True) if w_parts else pd.DataFrame()
    return cons, W


def pick_primary_fp(cons: pd.DataFrame, actuals: pd.DataFrame, metric: str) -> pd.DataFrame:
    """종목당 대표 fiscal_period 선정 — FY1(그 해, 미발표) 우선. FQ/FY 혼합 금지(§5).
    TP12M 은 단일 '12M' 이라 그대로 대표가 된다."""
    d = cons.copy()
    d["primary"] = False
    if metric == "TP12M":
        d["primary"] = d["fiscal_period"] == "12M"
        return d
    ann: Dict[Tuple[str, str], pd.Timestamp] = {}
    if actuals is not None and len(actuals):
        for r in actuals.itertuples(index=False):
            ann[(r.stock_id, r.fiscal_period)] = r.actual_announcement_date
    year = d["fiscal_period"].astype(str).str.extract(r"(20\d{2})", expand=False)
    d["_fy"] = pd.to_numeric(year, errors="coerce")
    d = d[d["_fy"].notna()]
    T_year = d["signal_date"].dt.year

    def _rank(row_fy, row_T_year, T_sig, key):
        a = ann.get(key)
        # PIT: '그 시점 T 에 이미 발표되었는가'만 본다 — 최종 DB 에 발표기록이 있다는
        # 사실 자체를 쓰면 §0.1(수정된 최종 DB 소급 간주 금지) 위반이다.
        unannounced = (a is None) or pd.isna(a) or (a >= T_sig)
        # FY1 = signal 연도, 다음해, 그 다음해, 전년(미발표시) 순
        offset = row_fy - row_T_year
        base = {0: 0, 1: 1, 2: 2, -1: 3}.get(int(offset), 9)
        return base + (0 if unannounced else 0.5)

    d["_rank"] = [_rank(fy, ty, tsg, (s, fp)) for fy, ty, tsg, s, fp in
                  zip(d["_fy"], T_year, d["signal_date"], d["stock_id"],
                      d["fiscal_period"])]
    idx = (d.sort_values(["_rank"])
           .groupby(["signal_date", "stock_id"], observed=True, sort=False)
           .head(1).index)
    d.loc[idx, "primary"] = True
    return d.drop(columns=["_fy", "_rank"])


# ── SCG · Accel · BASE_REV (§24~29) ────────────────────────────────────────────────────────
def _lookback_pairs(signal_dates, cal: TradingCal, n_td: int) -> Dict:
    sd = sorted(pd.DatetimeIndex(signal_dates))
    pos = [cal.pos(t) for t in sd]
    out = {}
    for i, t in enumerate(sd):
        out[t] = None
        for j in range(i - 1, -1, -1):
            if pos[i] - pos[j] >= n_td:
                out[t] = sd[j]
                break
    return out


def scg_signals(cons: pd.DataFrame, signal_dates, cal: TradingCal,
                cfg: SCGParams) -> pd.DataFrame:
    if not len(cons):
        return cons
    eps = cfg.EPSILON
    d = cons.copy()
    ok = d["status"] == "OK"
    med = (d[ok].groupby(["signal_date", "forecast_metric"], observed=True)
           ["consensus_equal_weight"]
           .transform(lambda s: float(np.median(np.abs(s)))))
    d["_mad"] = np.nan
    d.loc[ok, "_mad"] = med
    denom = np.maximum.reduce([d["consensus_equal_weight"].abs().to_numpy(float),
                               (cfg.DENOM_FLOOR_RATIO * d["_mad"]).fillna(0).to_numpy(float),
                               np.full(len(d), eps)])                       # §24
    d["scg0"] = (d["smart_consensus_scg0"] - d["consensus_equal_weight"]) / denom
    d["scg_ls"] = (d["smart_consensus_ls"] - d["consensus_equal_weight"]) / denom
    d.loc[~ok, ["scg0", "scg_ls"]] = np.nan
    for c in ("scg0", "scg_ls"):
        d[c] = (d.groupby(["signal_date", "forecast_metric"], observed=True)[c]
                .transform(lambda s: xs_winsor(s.to_numpy(float), cfg.WINSOR_LOWER,
                                               cfg.WINSOR_UPPER,
                                               cfg.MIN_CROSS_SECTION_FOR_WINSOR)))
    lb = _lookback_pairs(signal_dates, cal, int(cfg.ACCEL_LOOKBACK_TRADING_DAYS))
    prev = d["signal_date"].map(lb)
    snap = d.set_index(["signal_date"] + CS_KEY)
    key_prev = pd.MultiIndex.from_arrays([prev, d["stock_id"], d["fiscal_period"],
                                          d["forecast_metric"]])
    p_scg = snap["scg_ls"].reindex(key_prev).to_numpy(float)
    p_c = snap["consensus_equal_weight"].reindex(key_prev).to_numpy(float)
    d["scg_accel_20d"] = d["scg_ls"].to_numpy(float) - p_scg                # §25
    bden = np.maximum.reduce([np.abs(p_c),
                              (cfg.DENOM_FLOOR_RATIO * d["_mad"]).fillna(0).to_numpy(float),
                              np.full(len(d), eps)])
    d["base_revision_20d"] = (d["consensus_equal_weight"].to_numpy(float) - p_c) / bden  # §29
    d.loc[~ok, "base_revision_20d"] = np.nan
    d.loc[prev.isna().to_numpy(), ["scg_accel_20d", "base_revision_20d"]] = np.nan
    return d.drop(columns=["_mad"])


def rank_alphas(sig: pd.DataFrame, cfg: SCGParams) -> pd.DataFrame:
    """§26~28. 대표행(primary)의 단면 percentile rank → 4전략 알파.
    accel 결측 = rank 0.5 중립(§28) — 종목을 버리지 않는다(§25)."""
    d = sig.copy()
    p = d["primary"] if "primary" in d.columns else pd.Series(True, index=d.index)
    grp = d[p].groupby("signal_date", observed=True)
    for src, dst in (("base_revision_20d", "rank_base_rev"), ("scg0", "rank_scg0"),
                     ("scg_ls", "rank_scg_ls"), ("scg_accel_20d", "rank_scg_accel")):
        d.loc[p, dst] = grp[src].rank(method="average", pct=True)           # §26
    d["alpha_base_rev"] = d.get("rank_base_rev")
    d["alpha_scg0"] = d.get("rank_scg0")
    d["alpha_ls"] = d.get("rank_scg_ls")                                    # §27
    d["alpha_lsa"] = (cfg.SCG_LEVEL_WEIGHT * d["rank_scg_ls"]
                      + cfg.SCG_ACCEL_WEIGHT * d["rank_scg_accel"].fillna(0.50))  # §28
    d.loc[d["rank_scg_ls"].isna(), "alpha_lsa"] = np.nan
    return d


ALPHA_COL = {"BASE_REV": "alpha_base_rev", "SCG_0": "alpha_scg0",
             "SCG_LS": "alpha_ls", "SCG_LSA": "alpha_lsa"}
RAW_COL = {"BASE_REV": "base_revision_20d", "SCG_0": "scg0",
           "SCG_LS": "scg_ls", "SCG_LSA": None}     # LSA 는 rank 합성이라 raw 가 없다


# ── 진단(§34) ──────────────────────────────────────────────────────────────────────────────
def diag_analyst_counts(cons: pd.DataFrame) -> pd.DataFrame:
    if not len(cons):
        return pd.DataFrame()
    g = cons[cons["status"] == "OK"].groupby("signal_date")["analyst_count"]
    return (g.agg(count="size", mean="mean", median="median",
                  p10=lambda s: s.quantile(.1), p25=lambda s: s.quantile(.25),
                  p75=lambda s: s.quantile(.75), p90=lambda s: s.quantile(.9))
            .reset_index())


def diag_shrinkage(scores: pd.DataFrame) -> pd.DataFrame:
    if not len(scores):
        return pd.DataFrame()
    return (scores.sort_values("signal_date").groupby("analyst_id").tail(1)
            [["analyst_id", "acc_n", "lead_n", "acc_raw", "acc_star",
              "lead_raw", "lead_star"]].reset_index(drop=True))


def diag_weight_conc(W: pd.DataFrame) -> pd.DataFrame:
    if not len(W):
        return pd.DataFrame()
    d = W.assign(_w=W["weight_ls"].astype(float))
    g = d.groupby(["signal_date"] + CS_KEY, observed=True)["_w"]
    tot = g.transform("sum")
    p = d["_w"] / tot.where(tot > 0)
    d = d.assign(_p=p, _p2=p * p)
    g2 = d.groupby(["signal_date"] + CS_KEY, observed=True)
    out = g2.agg(max_weight_share=("_p", "max"), sum_p2=("_p2", "sum")).reset_index()
    top2 = (d.sort_values("_p", ascending=False)
            .groupby(["signal_date"] + CS_KEY, observed=True)["_p"]
            .apply(lambda s: float(s.head(2).sum())).reset_index(name="top2_weight_share"))
    out = out.merge(top2, on=["signal_date"] + CS_KEY, how="left")
    out["effective_analyst_n"] = 1.0 / out["sum_p2"].where(out["sum_p2"] > 0)
    return out.drop(columns=["sum_p2"])


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S8] 백테스트 — 십분위(부족 시 오분위) · 4전략 side-by-side · IC · 단조성                  ║
# ║  임계값 최적화 금지(§36): bucket 은 rank 등분이며 전략 간 유니버스는 동일(§30).            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def alphas_in_universe(sig: pd.DataFrame, members: pd.Series, cfg: SCGParams
                       ) -> pd.DataFrame:
    """평가 유니버스(예: 시총 하위1000) 안에서 raw 신호를 '재랭크'해 알파를 만든다.
    전체 유니버스 rank 를 그대로 부분집합에 쓰면 십분위가 비어 공정 비교가 깨진다."""
    d = sig[members].copy()
    grp = d.groupby("signal_date", observed=True)
    for src, dst in (("base_revision_20d", "alpha_base_rev"), ("scg0", "alpha_scg0"),
                     ("scg_ls", "alpha_ls")):
        d[dst] = grp[src].rank(method="average", pct=True)
    r_ac = grp["scg_accel_20d"].rank(method="average", pct=True)
    d["alpha_lsa"] = (cfg.SCG_LEVEL_WEIGHT * d["alpha_ls"]
                      + cfg.SCG_ACCEL_WEIGHT * r_ac.fillna(0.50))
    d.loc[d["alpha_ls"].isna(), "alpha_lsa"] = np.nan
    return d


def bucket_backtest(sig: pd.DataFrame, panel: pd.DataFrame, strat: str,
                    cost_bps: float = COST_BPS_ONEWAY,
                    nq_override: Optional[int] = None) -> dict:
    """단일 전략의 십분위 백테스트. 반환: returns(월별)·decile_mean·ic·holdings·nq"""
    a_col = ALPHA_COL[strat]
    d = sig.dropna(subset=[a_col]).merge(
        panel, left_on=["stock_id", "signal_date"], right_on=["code", "month"],
        how="inner")
    if not len(d):
        return {"strategy": strat, "empty": True}
    xs_n = d.groupby("signal_date")["stock_id"].size()
    # 표본 작으면 오분위 자동 폴백(§36). 4전략 비교표에서는 run_suite 가 공통 단면으로
    # nq 를 한 번만 정해 넘긴다 — 전략마다 분위수가 달라지면 §37 비교가 어긋난다.
    nq = int(nq_override) if nq_override else (10 if xs_n.median() >= 60 else 5)
    d["bucket"] = (d.groupby("signal_date")[a_col]
                   .transform(lambda s: np.ceil(s.rank(method="first", pct=True) * nq)
                              .clip(1, nq)))
    rows, hold_prev, hold_log = [], set(), []
    for T, g in d.groupby("signal_date", observed=True, sort=True):
        g_ok = g[np.isfinite(g["fwd_1m"])]
        if not len(g_ok):
            continue
        top = g_ok[g_ok["bucket"] == nq]
        bot = g_ok[g_ok["bucket"] == 1]
        top_codes = set(top["stock_id"])
        turn = (len(top_codes - hold_prev) + len(hold_prev - top_codes)) \
            / max(1, len(top_codes) + len(hold_prev)) if (top_codes or hold_prev) else 0.0
        cost = turn * 2 * cost_bps / 1e4             # 편도×양방향 근사
        r_top = float(top["fwd_1m"].mean()) if len(top) else np.nan
        r_bot = float(bot["fwd_1m"].mean()) if len(bot) else np.nan
        rows.append(dict(month=T, top=r_top, bot=r_bot,
                         ls=(r_top - r_bot) if np.isfinite(r_top) and np.isfinite(r_bot)
                         else np.nan,
                         top_net=(r_top - cost) if np.isfinite(r_top) else np.nan,
                         n_xs=len(g_ok), n_top=len(top), turnover=turn, cost=cost))
        for _, r in top.iterrows():
            hold_log.append(dict(month=T, code=r["stock_id"], ret=r["fwd_1m"]))
        hold_prev = top_codes
    R = pd.DataFrame(rows)
    dec = (d[np.isfinite(d["fwd_1m"])].groupby("bucket")["fwd_1m"]
           .agg(["mean", "count"]).reset_index()
           .rename(columns={"mean": "mean_fwd_1m", "count": "n"}))
    ics = {}
    for h in (20, 60, 120):
        col = f"fwd_{h}td"
        dd = d.dropna(subset=[col])
        per = pd.Series({T: spearman(g[a_col].to_numpy(float), g[col].to_numpy(float))
                         for T, g in dd.groupby("signal_date", observed=True)})
        per = per.dropna()
        ics[h] = dict(mean_ic=float(per.mean()) if len(per) else np.nan,
                      median_ic=float(per.median()) if len(per) else np.nan,
                      ic_std=float(per.std(ddof=1)) if len(per) > 2 else np.nan,
                      ic_ir=float(per.mean() / per.std(ddof=1))
                      if len(per) > 2 and per.std(ddof=1) > 0 else np.nan,
                      positive_ic_ratio=float((per > 0).mean()) if len(per) else np.nan,
                      n_dates=int(len(per)))
    return {"strategy": strat, "empty": False, "returns": R, "decile": dec, "nq": nq,
            "ic": ics, "holdings": pd.DataFrame(hold_log),
            "n_signals": int(len(d)), "n_unique_stocks": int(d["stock_id"].nunique())}


def perf_summary(bt: dict, bench: Optional[pd.Series] = None, leg: str = "ls") -> dict:
    """§37 필수 성과 항목. leg='ls'(D10-D1) 또는 'top_net'(상위십분위, 비용 차감)."""
    if bt.get("empty"):
        return {}
    R = bt["returns"].dropna(subset=[leg])
    r = R[leg].to_numpy(float)
    n = len(r)
    if n < 6:
        return {}
    eq = np.cumprod(1 + r)
    yrs = n / 12.0
    cagr = eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 else np.nan
    vol = float(np.std(r, ddof=1) * math.sqrt(12)) if n > 2 else np.nan
    peak = np.maximum.accumulate(eq)
    mdd = float((eq / peak - 1).min())
    mu, t = nw_tstat(r)
    out = dict(strategy=bt["strategy"], months=n,
               n_signals=bt["n_signals"], n_unique_stocks=bt["n_unique_stocks"],
               annualized_return=float(mu * 12), CAGR=float(cagr), volatility=vol,
               Sharpe=float(cagr / vol) if vol and np.isfinite(vol) and vol > 0 else np.nan,
               MDD=mdd, hit_rate=float((r > 0).mean()),
               turnover=float(R["turnover"].mean()),
               average_holdings=float(R["n_top"].mean()), t_HAC=float(t),
               cum_return=float(eq[-1] - 1))
    if bench is not None and len(bench):
        b = bench.reindex(R["month"]).to_numpy(float)
        m = np.isfinite(b)
        if m.sum() > 6:
            ex = r[m] - b[m]
            out["excess_vs_bench_ann"] = float(np.nanmean(ex) * 12)
    return out


def monotonicity(bt: dict) -> Tuple[float, bool]:
    """§39 — D1..D10 평균수익의 단조성. (스피어만, D_top>D_bottom)"""
    if bt.get("empty") or not len(bt["decile"]):
        return np.nan, False
    dec = bt["decile"].sort_values("bucket")
    rho = spearman(dec["bucket"].to_numpy(float), dec["mean_fwd_1m"].to_numpy(float))
    top_gt = bool(dec["mean_fwd_1m"].iloc[-1] > dec["mean_fwd_1m"].iloc[0])
    return rho, top_gt


def run_suite(sig: pd.DataFrame, panel: pd.DataFrame, label: str,
              bench: Optional[pd.Series] = None) -> Dict[str, dict]:
    """4전략을 동일 표본·동일 시점·동일 분위수에서 나란히(§30·§37).

    ★ 네 알파 중 하나라도 결측인 행은 전부 제외한다. BASE_REV 는 t-20 컨센서스가
      없으면 결측이라 첫 달과 신규 커버 종목에서 표본이 작아지는데, 그 상태로
      나란히 놓으면 §47 질문1(SCG_0 vs BASE_REV)이 서로 다른 표본의 비교가 된다.
      제외된 양은 로그에 남긴다 — 조용히 줄이지 않는다.
    """
    acols = [ALPHA_COL[s] for s in STRATS if ALPHA_COL[s] in sig.columns]
    n0 = len(sig)
    common_sig = sig.dropna(subset=acols) if acols else sig
    if n0 and len(common_sig) < n0:
        CON.say(f"[{label}] 4전략 공통표본 정렬: {n0:,} → {len(common_sig):,}행 "
                f"(어느 한 전략이라도 알파가 없는 행 제외 — §30 동일 유니버스 보장)")
    merged = common_sig.merge(panel[["code", "month"]], left_on=["stock_id", "signal_date"],
                              right_on=["code", "month"], how="inner")
    xs = merged.groupby("signal_date")["stock_id"].size()
    nq_common = 10 if (len(xs) and xs.median() >= 60) else 5
    out = {}
    for s in STRATS:
        out[s] = bucket_backtest(common_sig, panel, s, nq_override=nq_common)
        out[s]["label"] = label
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S10] 강건성 — 민감도(§41) · 서브기간 · 집중도 · 플라시보 · 신호지연                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
ROBUST: "OrderedDict[str, dict]" = OrderedDict()


def _rb(rid: str, name: str, verdict: Optional[bool], detail: str):
    ROBUST[rid] = dict(id=rid, name=name, ok=verdict, detail=detail)
    icon = "✔" if verdict else ("✘" if verdict is False else "·")
    CON.say(f"{icon} [{rid}] {name} — {detail}")


def rebuild_signals(ENG: dict, cfg: SCGParams) -> pd.DataFrame:
    """파라미터 변형으로 점수→컨센서스→신호를 재계산(민감도 전용 경로).
    리더십 지평이 바뀌면 사건 자체를 다시 만든다."""
    led = ENG["lead_ev"]
    if int(cfg.LEAD_FORWARD_TRADING_DAYS) != int(ENG["cfg"].LEAD_FORWARD_TRADING_DAYS):
        led = lead_events(ENG["fcv"], ENG["cal"], cfg, ENG["metric"])
    sc = analyst_scores(ENG["signal_dates"], ENG["acc_ev"], led, cfg)
    cons, _ = smart_consensus(ENG["fcv"], sc, ENG["signal_dates"], cfg, ENG["metric"],
                              keep_weights=False)
    cons = pick_primary_fp(cons, ENG["actuals"], ENG["metric"])
    sig = scg_signals(cons, ENG["signal_dates"], ENG["cal"], cfg)
    return rank_alphas(sig, cfg)


def R_sensitivity(ENG: dict, panel: pd.DataFrame):
    """§41 — 최적화가 아니라 민감도 '확인'. 공식값은 45/6/20 고정, 표만 출력."""
    base_cfg: SCGParams = ENG["cfg"]
    variants = [("공식 V1", base_cfg)]
    for hl in (30.0, 60.0):
        variants.append((f"halflife={hl:g}", base_cfg.variant(FORECAST_HALFLIFE_DAYS=hl)))
    for K in (4.0, 10.0):
        variants.append((f"K={K:g}", base_cfg.variant(K_ACC=K, K_LEAD=K)))
    for ld in (10, 40):
        variants.append((f"lead={ld}td", base_cfg.variant(LEAD_FORWARD_TRADING_DAYS=ld)))
    rows = []
    for name, cfg in variants:
        try:
            sig = ENG["sig"] if name == "공식 V1" else rebuild_signals(ENG, cfg)
            for st in ("SCG_LS", "SCG_LSA"):
                bt = bucket_backtest(sig[sig.get("primary", True)], panel, st)
                if bt.get("empty"):
                    rows.append([name, st, "-", "-", "-"])
                    continue
                ls = bt["returns"]["ls"].dropna()
                rows.append([name, st,
                             f"{ls.mean()*12*100:+.1f}%",
                             f"{bt['ic'][20]['mean_ic']:+.3f}",
                             f"{bt['ic'][20]['ic_ir']:+.2f}"])
        except Exception as e:
            rows.append([name, "-", f"실패:{type(e).__name__}", "-", "-"])
    CON.grid(rows, ["변형", "전략", "L/S 연환산", "IC20 평균", "IC20 IR"],
             ["l", "l", "r", "r", "r"],
             title="강건성 R1 — 파라미터 민감도 (공식 V1=45/6/20 고정 · 사후 채택 금지 §41)")
    _rb("R1", "파라미터 민감도", None, f"{len(variants)}개 변형 표 출력(판정 없음 — 확인 목적)")


def R_subperiod(suites: Dict[str, dict]):
    rows = []
    for st, bt in suites.items():
        if bt.get("empty"):
            continue
        R = bt["returns"].dropna(subset=["ls"]).copy()
        R["y"] = pd.DatetimeIndex(R["month"]).year
        for y, g in R.groupby("y"):
            rows.append([st, int(y), f"{g['ls'].mean()*12*100:+.1f}%",
                         f"{(g['ls'] > 0).mean()*100:.0f}%", len(g)])
    CON.grid(rows, ["전략", "연도", "L/S 연환산", "월승률", "개월"],
             ["l", "r", "r", "r", "r"], title="강건성 R2 — 연도별 서브기간 (특정 1~2년 의존 점검 §47-질문4)")
    ok = None
    ls_by_year = defaultdict(list)
    for r in rows:
        if r[0] == "SCG_LS":
            ls_by_year[r[1]] = r[2]
    _rb("R2", "서브기간 분해", None, f"{len(ls_by_year)}개 연도 출력")


def R_concentration(suites: Dict[str, dict]):
    rows = []
    for st, bt in suites.items():
        if bt.get("empty") or not len(bt.get("holdings", [])):
            continue
        H = bt["holdings"].dropna(subset=["ret"])
        contrib = H.groupby("code")["ret"].sum().sort_values(ascending=False)
        tot = float(contrib.sum())
        k5 = max(1, int(len(contrib) * 0.05))
        top5_share = float(contrib.head(k5).sum())
        flip = (tot - top5_share) <= 0 < tot
        rows.append([st, len(contrib), f"{tot:+.2f}", f"{top5_share:+.2f}",
                     f"{tot - top5_share:+.2f}", "⚠소수의존" if flip else "분산"])
    CON.grid(rows, ["전략", "보유종목수(누적)", "총기여", "상위5%기여", "상위5%제외 후",
                    "판정"], ["l", "r", "r", "r", "r", "l"],
             title="강건성 R3 — 종목 집중도 (몇 종목이 성과를 다 만들었는가 §47-질문4)")
    _rb("R3", "종목 집중도", None, "상위 5% 종목 제외 후 기여 표 출력")


def R_placebo(sig: pd.DataFrame, panel: pd.DataFrame, n_iter: int = 200):
    """알파를 월내 무작위 재배열 → L/S 스프레드 귀무분포 대비 실제값 위치."""
    st = "SCG_LS"
    d = sig.dropna(subset=[ALPHA_COL[st]]).merge(
        panel, left_on=["stock_id", "signal_date"], right_on=["code", "month"],
        how="inner").dropna(subset=["fwd_1m"])
    if len(d) < 500:
        _rb("R4", "플라시보(무작위 재배열)", None, "표본 부족으로 생략")
        return
    a = d[ALPHA_COL[st]].to_numpy(float)
    f = d["fwd_1m"].to_numpy(float)
    gidx = d.groupby("signal_date", observed=True).indices
    def _spread(alpha):
        s = 0.0; n = 0
        for _, ix in gidx.items():
            av, fv = alpha[ix], f[ix]
            if len(ix) < 10:
                continue
            q_hi, q_lo = np.nanquantile(av, [0.9, 0.1])
            hi, lo = fv[av >= q_hi], fv[av <= q_lo]
            if len(hi) and len(lo):
                s += float(np.nanmean(hi) - np.nanmean(lo)); n += 1
        return s / max(n, 1)
    real = _spread(a)
    null = []
    rng = np.random.default_rng(SEED)
    for _ in range(n_iter):
        ap = a.copy()
        for _, ix in gidx.items():
            ap[ix] = rng.permutation(ap[ix])
        null.append(_spread(ap))
    null = np.array(null)
    p = float((null >= real).mean()) if np.isfinite(real) else np.nan
    _rb("R4", "플라시보(무작위 재배열)", bool(p < 0.10) if np.isfinite(p) else None,
        f"실제 스프레드 {real*100:+.2f}%/월 · 귀무 p={p:.3f} (n={n_iter})")


def R_lag(sig: pd.DataFrame, panel: pd.DataFrame):
    """신호를 한 달 늦게 써도 성과가 남는지 + '미래 신호'가 더 좋아지면 누수 의심."""
    st = "SCG_LS"
    d = sig.dropna(subset=[ALPHA_COL[st]])[["signal_date", "stock_id", ALPHA_COL[st]]]
    sd = sorted(d["signal_date"].unique())
    nxt = {a: b for a, b in zip(sd[:-1], sd[1:])}
    lag = d.copy()
    lag["signal_date"] = lag["signal_date"].map(nxt)      # T 의 신호를 T+1 에 사용
    lag = lag.dropna(subset=["signal_date"])
    out = {}
    for name, dd in (("동시(기본)", d), ("1개월 지연", lag)):
        m = dd.merge(panel, left_on=["stock_id", "signal_date"],
                     right_on=["code", "month"], how="inner").dropna(subset=["fwd_1m"])
        per = []
        for _, g in m.groupby("signal_date", observed=True):
            if len(g) < 10:
                continue
            q_hi, q_lo = g[ALPHA_COL[st]].quantile([0.9, 0.1])
            per.append(float(g[g[ALPHA_COL[st]] >= q_hi]["fwd_1m"].mean()
                             - g[g[ALPHA_COL[st]] <= q_lo]["fwd_1m"].mean()))
        out[name] = float(np.nanmean(per)) if per else np.nan
    base, lagged = out.get("동시(기본)", np.nan), out.get("1개월 지연", np.nan)
    verdict = None
    detail = f"기본 {base*100:+.2f}%/월 vs 지연 {lagged*100:+.2f}%/월"
    if np.isfinite(base) and np.isfinite(lagged):
        verdict = bool(lagged < base * 1.5)     # 지연이 크게 '더 좋으면' 시점정렬 의심
        detail += " — 지연 신호가 유의하게 우월하면 시점 정렬(누수)을 의심해야 합니다"
    _rb("R5", "신호 지연 검사(누수 반증)", verdict, detail)


def R_cost_stress(sig: pd.DataFrame, panel: pd.DataFrame, nq: Optional[int] = None):
    rows = []
    for bps in (0.0, 25.0, 50.0):
        bt = bucket_backtest(sig, panel, "SCG_LS", cost_bps=bps, nq_override=nq)
        if bt.get("empty"):
            continue
        ps = perf_summary(bt, leg="top_net")
        rows.append([f"{bps:.0f}bp", f"{ps.get('CAGR', np.nan)*100:+.1f}%",
                     f"{ps.get('Sharpe', np.nan):.2f}"])
    CON.grid(rows, ["편도비용", "상위십분위 CAGR", "Sharpe"], ["r", "r", "r"],
             title="강건성 R6 — 거래비용 스트레스(상위 십분위, 비용 차감)")
    _rb("R6", "비용 스트레스", None, "0/25/50bp 표 출력")


def robustness_verdict():
    rows = [[r["id"], r["name"],
             {"True": "통과", "False": "실패", "None": "정보"}[str(r["ok"])],
             r["detail"][:64]] for r in ROBUST.values()]
    CON.grid(rows, ["검사", "이름", "판정", "세부"], ["l", "l", "l", "l"],
             title="강건성 종합")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S2] 자체계약 — 명세 §35 TEST 1~9 + 구조 계약. 실패하면 실데이터 수집을 시작하지 않는다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
CONTRACTS: List[dict] = []


def _ct(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACTS.append(dict(id=cid, name=name, ok=bool(ok), msg=str(msg)[:80]))
    (CON.ok if ok else CON.err)(f"[{cid}] {name} — {msg}")


def _mini_cal() -> TradingCal:
    return TradingCal(pd.bdate_range("2020-01-01", "2023-12-31"))


def _fc_row(sid, aid, d, fp, v, met="EPS"):
    return dict(stock_id=sid, analyst_id=aid, broker_id="b", report_id=h1(sid, aid, d),
                report_date=ts(d), fiscal_period=fp, forecast_metric=met,
                forecast_value=float(v))


def run_contracts(strict: bool = True) -> bool:
    cfg = SCGParams()
    cal = _mini_cal()
    T = ts("2021-06-30")
    sdates = [T]

    def t1():   # 모든 전망 동일 → smart == equal, scg == 0
        fc = validate_forecasts(pd.DataFrame(
            [_fc_row("A", f"a{i}", "2021-06-01", "2021FY", 100.0) for i in range(3)]))
        cons, _ = smart_consensus(with_validity(fc, cfg), pd.DataFrame(), sdates, cfg, "EPS")
        cons["primary"] = True
        sig = scg_signals(cons, sdates, cal, cfg)
        r = sig.iloc[0]
        same = abs(r["smart_consensus_ls"] - r["consensus_equal_weight"]) < 1e-9
        return same and abs(r["scg_ls"]) < 1e-9, f"scg_ls={r['scg_ls']:.2e}"

    def t2():   # 이력 없는 애널리스트 = 중립 (star 0, multiplier 1)
        fc = validate_forecasts(pd.DataFrame(
            [_fc_row("A", "novice", "2021-06-01", "2021FY", 100.0),
             _fc_row("A", "other", "2021-06-01", "2021FY", 120.0)]))
        _, W = smart_consensus(with_validity(fc, cfg), pd.DataFrame(), sdates, cfg, "EPS")
        w = W[W["analyst_id"] == "novice"].iloc[0]
        return (abs(w["acc_star"]) < 1e-12 and abs(w["lead_star"]) < 1e-12
                and abs(w["quality_multiplier_ls"] - 1.0) < 1e-9), \
            f"mult={w['quality_multiplier_ls']:.3f}"

    def t3():   # 반복적으로 더 정확했던 A 의 weight > B
        rows, acts = [], []
        for k in range(6):
            y = 2016 + k
            # 발표 60여 일 전의 '마지막 전망' — 180일 신선도 한도 안이어야 사건이 된다
            rows += [_fc_row("A", "good", f"{y+1}-01-15", f"{y}FY", 100.0),
                     _fc_row("A", "bad", f"{y+1}-01-15", f"{y}FY", 140.0)]
            acts.append(dict(stock_id="A", fiscal_period=f"{y}FY", forecast_metric="EPS",
                             actual_value=101.0, actual_announcement_date=ts(f"{y+1}-03-20")))
        fc = validate_forecasts(pd.DataFrame(rows))
        ae = acc_events_eps(fc, pd.DataFrame(acts), cfg)
        sc = analyst_scores([ts("2022-06-30")], ae, pd.DataFrame(), cfg)
        fc2 = validate_forecasts(pd.DataFrame(
            [_fc_row("A", "good", "2022-06-01", "2022FY", 100.0),
             _fc_row("A", "bad", "2022-06-01", "2022FY", 120.0)]))
        _, W = smart_consensus(with_validity(fc2, cfg), sc, [ts("2022-06-30")], cfg, "EPS")
        wg = float(W[W["analyst_id"] == "good"]["weight_ls"].iloc[0])
        wb = float(W[W["analyst_id"] == "bad"]["weight_ls"].iloc[0])
        return wg > wb, f"w(good)={wg:.3f} > w(bad)={wb:.3f}"

    def t4():   # 동일 정확도, A 수정 후 동료가 따라옴 → lead_A > lead_B, weight_A > weight_B
        rows = []
        for k in range(5):
            m0 = ts("2020-01-15") + pd.Timedelta(60 * k, "D")
            # 추종 지연 10일(≈7거래일) — 20거래일 관측창 '안'이어야 리더십이 관측된다.
            # 리더의 다음 수정(+60일)은 추종자 창 밖이라 역방향 오염이 없다.
            rows += [_fc_row("S", "leader", f"{m0:%Y-%m-%d}", "2021FY", 100.0 + 10 * k),
                     _fc_row("S", "follower", f"{(m0 + pd.Timedelta(10, 'D')):%Y-%m-%d}",
                             "2021FY", 100.0 + 10 * k)]
        fc = validate_forecasts(pd.DataFrame(rows))
        le = lead_events(fc, cal, cfg, "EPS")
        sc = analyst_scores([ts("2021-06-30")], pd.DataFrame(), le, cfg)
        la = float(sc[sc["analyst_id"] == "leader"]["lead_star"].iloc[0])
        lb = float(sc[sc["analyst_id"] == "follower"]["lead_star"].iloc[0])
        ma = min(2.0, max(0.5, math.exp(0.7 * 0.4 * la)))
        mb = min(2.0, max(0.5, math.exp(0.7 * 0.4 * lb)))
        return la > lb and la > 0 and ma > mb, \
            f"lead*(leader)={la:.3f} > {lb:.3f} · mult {ma:.3f}>{mb:.3f}"

    def t5():   # 최근성: 오늘 > 45일 전 > 90일 전
        fc = validate_forecasts(pd.DataFrame(
            [_fc_row("A", "a1", "2021-06-30", "2021FY", 100.0),
             _fc_row("A", "a2", "2021-05-16", "2021FY", 100.0),
             _fc_row("A", "a3", "2021-04-01", "2021FY", 100.0)]))
        _, W = smart_consensus(with_validity(fc, cfg), pd.DataFrame(), sdates, cfg, "EPS")
        w = W.set_index("analyst_id")["weight_ls"]
        return w["a1"] > w["a2"] > w["a3"], \
            f"{w['a1']:.3f} > {w['a2']:.3f} > {w['a3']:.3f}"

    def t6():   # 미래 누수: T 이후 완결 사건이 T 점수에 들어가면 안 된다 + 미래 report 즉사
        ae = pd.DataFrame([dict(analyst_id="x", stock_id="A", fiscal_period="2021FY",
                                forecast_metric="EPS", completion_date=ts("2021-07-05"),
                                acc_event=2.0, n_forecasters=3)])
        sc = analyst_scores([T], ae, pd.DataFrame(), cfg)
        leak_free = abs(float(sc["acc_star"].iloc[0])) < 1e-12 and int(sc["acc_n"].iloc[0]) == 0
        try:
            validate_forecasts(pd.DataFrame([_fc_row("A", "a", "2021-07-02", "2021FY", 1.0)]),
                               asof=T)
            future_caught = False
        except RuleBreak:
            future_caught = True
        return leak_free and future_caught, "T 이후 사건 0건 반영 · 미래 report 즉시 오류"

    def t7():   # leave-one-out: 동료가 안 움직였으면 자기 상향만으로 lead>0 이 되면 안 된다
        rows = [_fc_row("S", "self", "2020-02-01", "2021FY", 100.0),
                _fc_row("S", "self", "2020-03-02", "2021FY", 200.0),
                _fc_row("S", "peer", "2020-01-15", "2021FY", 100.0)]
        le = lead_events(validate_forecasts(pd.DataFrame(rows)), cal, cfg, "EPS")
        if not len(le):
            return False, "사건 미생성"
        ev = float(le["lead_event"].iloc[0])
        return abs(ev) < 1e-9, f"lead_event={ev:.4f} (자기상관 제거 확인)"

    def t8():   # 같은 키의 활성 전망은 최대 1개
        fc = validate_forecasts(pd.DataFrame(
            [_fc_row("A", "a", "2021-05-01", "2021FY", 90.0),
             _fc_row("A", "a", "2021-06-10", "2021FY", 110.0),
             _fc_row("A", "b", "2021-06-10", "2021FY", 100.0)]))
        act = active_at(with_validity(fc, cfg), T)
        n = act.groupby(FC_KEY).size().max()
        v = float(act[act["analyst_id"] == "a"]["forecast_value"].iloc[0])
        return n == 1 and v == 110.0, f"활성 전망 키당 {n}개, 최신값 {v:.0f}"

    def t9():   # 표본 보존: quality 조건이 유니버스를 줄이면 안 된다
        rows = [_fc_row("A", "a", "2021-06-01", "2021FY", 100.0),
                _fc_row("A", "b", "2021-06-01", "2021FY", 120.0),
                _fc_row("B", "c", "2021-06-01", "2021FY", 50.0),
                _fc_row("B", "d", "2021-06-01", "2021FY", 70.0),
                _fc_row("C", "e", "2021-06-01", "2021FY", 10.0)]   # C 는 1명 → INSUFFICIENT
        cons, _ = smart_consensus(with_validity(validate_forecasts(pd.DataFrame(rows)),
                                                cfg), pd.DataFrame(), sdates, cfg, "EPS")
        okset = set(cons[cons["status"] == "OK"]["stock_id"])
        s0 = set(cons[cons["smart_consensus_scg0"].notna()]["stock_id"])
        sl = set(cons[cons["smart_consensus_ls"].notna()]["stock_id"])
        return okset == s0 == sl == {"A", "B"}, f"eligible={sorted(okset)} 3전략 동일"

    def c_depot():   # 절대1원칙 가드레일: 읽기 루트에 쓰기 시도 → 즉시 차단
        if DEPOT is None or not DEPOT.read_roots:
            return True, "읽기 루트 없음(신규 환경) — 가드레일은 활성"
        try:
            DEPOT._guard_write(os.path.join(DEPOT.read_roots[0], "x.parquet"))
            return False, "차단 실패"
        except RuleBreak:
            return True, "기존 캐시 쓰기 차단 확인"

    def c_det():   # 결정성: 같은 시드 → 같은 난수
        a = np.random.default_rng(SEED).normal(size=5)
        b = np.random.default_rng(SEED).normal(size=5)
        return bool(np.allclose(a, b)), "동일 시드 동일 난수"

    _ct("TEST1", "동일 전망 불변성(§35.1)", t1)
    _ct("TEST2", "중립 애널리스트(§35.2)", t2)
    _ct("TEST3", "정확도 보상(§35.3)", t3)
    _ct("TEST4", "리더십 보상(§35.4)", t4)
    _ct("TEST5", "최근성 가중(§35.5)", t5)
    _ct("TEST6", "미래누수 금지(§35.6)", t6)
    _ct("TEST7", "leave-one-out(§35.7)", t7)
    _ct("TEST8", "중복 전망 금지(§35.8)", t8)
    _ct("TEST9", "표본 보존(§35.9)", t9)
    def c_url():   # URL 템플릿 ↔ 호출부 인자 이름 일치 (런타임 KeyError 원천 차단)
        checks = [(MARCAP_URLS[0], {"y": 2020}), (FDR_CACHE_URL,
                                                  {"br": "master", "kind": "listing/krx",
                                                   "date": "2026-08-07"})]
        for tmpl, kw in checks:
            need = set(re.findall(r"\{(\w+)[^}]*\}", tmpl))
            if need != set(kw):
                return False, f"템플릿 자리표시자 {sorted(need)} ≠ 호출 인자 {sorted(kw)}"
            tmpl.format(**kw)
        return True, f"URL 템플릿 {len(checks)}종 자리표시자 일치"

    _ct("C-보존", "기존 캐시 쓰기 차단", c_depot)
    _ct("C-결정", "결정성(시드)", c_det)
    _ct("C-URL", "URL 템플릿 배선", c_url)
    bad = [c for c in CONTRACTS if not c["ok"]]
    CON.grid([[c["id"], c["name"], "통과" if c["ok"] else "실패", c["msg"]]
              for c in CONTRACTS], ["ID", "계약", "판정", "근거"], ["l", "l", "l", "l"],
             title="자체계약 검증 결과")
    if bad and strict:
        raise RuleBreak(f"자체계약 {len(bad)}건 실패 — 실데이터로 진행하지 않습니다: "
                        + ", ".join(c["id"] for c in bad))
    return not bad


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S2b] 실경로 리허설 — 네트워크만 가짜, 수집 함수는 '실물'로 실행한다                        ║
# ║                                                                                          ║
# ║  ★ 이 계층이 없어서 같은 유형의 사고가 반복됐다:                                           ║
# ║    수집부를 고쳐도 SMOKE(합성)·CACHED(캐시)는 그 코드를 한 줄도 타지 않으므로              ║
# ║    사용자의 실행이 곧 '첫 실행'이 되고, URL 자리표시자 이름 하나가 틀린 것 같은            ║
# ║    사소한 배선 오류가 몇 분 뒤 KeyError 로 터졌다. py_compile 로는 절대 안 잡힌다.         ║
# ║                                                                                          ║
# ║  그래서 fetch/fetch_json 만 픽스처로 바꿔치고 수집·정제 함수를 전부 호출해 본다.            ║
# ║  통과 못 하면 실데이터 수집을 시작하지 않는다.                                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
REHEARSAL: List[dict] = []


def _fx_marcap_parquet() -> bytes:
    # 월말(신호일)과 +120거래일 지평이 모두 들어가도록 넉넉히 잡는다
    days = pd.bdate_range("2019-11-01", "2020-06-30")
    rows = []
    for c in ("005930", "000660", "900110"):
        for i, d in enumerate(days):
            rows.append(dict(Date=d, Code=c, Name=f"테스트{c}", Close=1000 + i * 10,
                             Open=1000, High=1010, Low=990, Volume=1e5, Amount=1e8,
                             Marcap=(1000 + i * 10) * 1e6, Stocks=1e6,
                             Market="KOSPI", MarketId="STK", Dept="", ChangeCode="0",
                             Changes=0.0, ChangesRatio=0.0, Rank=1))
    buf = io.BytesIO()
    pd.DataFrame(rows).to_parquet(buf, index=False)
    return buf.getvalue()


def _fx_fdrcache_csv() -> bytes:
    hdr = (",Code,ISU_CD,Name,Market,Dept,Close,ChangeCode,Changes,ChagesRatio,"
           "Open,High,Low,Volume,Amount,Marcap,Stocks,MarketId\n")
    body = "".join(f"{i},{c},KR7{c}003,테스트{c},KOSPI,,1000,0,0,0.0,1000,1010,990,"
                   f"100000,100000000,1000000000,1000000,STK\n"
                   for i, c in enumerate(("005930", "000660")))
    return ("﻿" + hdr + body).encode("utf-8")


def _fx_delisting_csv() -> bytes:
    hdr = (",Symbol,Name,Market,SecuGroup,Kind,ListingDate,DelistingDate,Reason,"
           "ArrantEnforceDate,ArrantEndDate,Industry,ParValue,ListingShares,"
           "ToSymbol,ToName\n")
    body = ("0,900110,폐지테스트,KOSPI,주권,,2010-01-01,2021-06-16,감사의견,,,,"
            "5000,1000000,,\n")
    return ("﻿" + hdr + body).encode("utf-8")


def _fx_hankyung_html() -> str:
    rows = "".join(
        f"<tr><td>26.03.1{i}</td><td><a href='/analysis/downpdf?report_idx={900+i}'>"
        f"테스트기업(00593{i}) 목표가 상향</a></td><td>12,000</td><td>매수</td>"
        f"<td>김애널</td><td>테스트증권</td></tr>" for i in range(1, 4))
    return ("<div class='table_style01'><table><thead><tr><th>작성일</th><th>제목</th>"
            "<th>적정가격</th><th>투자의견</th><th>작성자</th><th>제공출처</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


def _fx_naver_html() -> str:
    rows = "".join(
        f"<tr><td><a class='stock_item' href='/item/main.naver?code=00593{i}'>테스트{i}</a>"
        f"</td><td><a href='/research/company_read.naver?nid={700+i}'>실적 리뷰</a></td>"
        f"<td>테스트증권</td><td><a href='http://x/y.pdf'>pdf</a></td>"
        f"<td>26.03.1{i}</td><td>123</td></tr>" for i in range(1, 4))
    return f"<div class='box_type_m'><table class='type_1'>{rows}</table></div>"


class _FixtureNet:
    """네트워크만 가짜. 어떤 URL이 오든 그럴듯한 응답을 돌려준다."""

    def __init__(self):
        self.hits: Counter = Counter()

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        self.hits[source] += 1
        u = str(url)
        if "marcap" in u:
            return _fx_marcap_parquet()
        if "fdr_krx_data_cache" in u:
            raw = _fx_delisting_csv() if "delisting" in u else _fx_fdrcache_csv()
            return raw if as_bytes else raw.decode("utf-8")
        if "consensus.hankyung" in u and "downpdf" in u:
            return ("%PDF-1.4\nEPS\n2020 2021\n1,000 1,200\n"
                    "김애널 연구원 02-000-0000").encode("utf-8")
        if "consensus.hankyung" in u:
            return _fx_hankyung_html()
        if "finance.naver.com/research" in u:
            return _fx_naver_html()
        if u.lower().endswith(".pdf"):
            return b"%PDF-1.4\nEPS\n2020 2021\n1,000 1,200\n"
        if "corpCode" in u:
            import zipfile
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml",
                           "<result><list><corp_code>00126380</corp_code>"
                           "<corp_name>테스트</corp_name>"
                           "<stock_code>005930</stock_code></list></result>")
            return buf.getvalue()
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        self.hits[source] += 1
        u = str(url)
        if "list.json" in u:
            return {"status": "000", "total_page": 1,
                    "list": [{"corp_code": "00126380", "stock_code": "005930",
                              "report_nm": "사업보고서 (2020.12)",
                              "rcept_dt": "20210315"}]}
        if "fnlttMultiAcnt" in u:
            return {"status": "000",
                    "list": [{"stock_code": "005930", "account_nm": "당기순이익",
                              "thstrm_amount": "1,000,000,000", "fs_div": "CFS",
                              "rcept_no": "20210315000123"}]}
        return {"status": "000", "list": []}


def _rh(name: str, fn: Callable, expect_rows: bool = True):
    t0 = time.time()
    try:
        v = fn()
        n = len(v) if hasattr(v, "__len__") else (1 if v is not None else 0)
        ok = (n > 0) if expect_rows else True
        REHEARSAL.append(dict(name=name, ok=ok, rows=n, sec=time.time() - t0,
                              err="" if ok else "행 0개"))
        return v
    except Exception as e:
        REHEARSAL.append(dict(name=name, ok=False, rows=-1, sec=time.time() - t0,
                              err=f"{type(e).__name__}: {e}"[:110],
                              tb=traceback.format_exc(limit=6)))
        return None


def _rehearsal_depot(tmp: str) -> "Depot":
    """실제 캐시를 절대 건드리지 않는 임시 금고."""
    dep = Depot.__new__(Depot)
    dep.write_root = tmp
    dep.on_drive = False
    dep.drive_mode = "리허설"
    dep.ns = {"공용": os.path.join(tmp, "shared"), "전용": os.path.join(tmp, "scg_v1")}
    for p in dep.ns.values():
        for sub in ("index", "index/_backup", "table", "blob", "report"):
            os.makedirs(os.path.join(p, sub), exist_ok=True)
    dep.read_roots = []
    dep._idx_cache = {}
    dep._lk = threading.RLock()
    dep.stats = Counter()
    dep._adopted = {}
    dep._foreign_parquets = []
    dep._foreign_fingerprint = {}
    dep._foreign_pdfs = {}
    return dep


def run_rehearsal(strict: bool = True) -> bool:
    """수집·정제 함수를 픽스처 네트워크로 실물 실행한다(라이브러리 없는 최악 조건)."""
    G = globals()
    keys = ("fetch", "fetch_json", "fdr", "pykrx_stock", "DART_API_KEY", "RUN_MODE",
            "DEPOT", "RESEARCH_DOWNLOAD_PDF", "RESEARCH_COLLECT")
    saved = {k: G.get(k) for k in keys}
    net = _FixtureNet()
    tmp = tempfile.mkdtemp(prefix="scg_rehearsal_")
    try:
        G["fetch"], G["fetch_json"] = net.get, net.json
        G["fdr"] = None                    # 선택 라이브러리가 전부 없어도 통과해야 한다
        G["pykrx_stock"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["RESEARCH_COLLECT"] = True
        dep = _rehearsal_depot(tmp)
        G["DEPOT"] = dep

        _rh("무인증 캐시(listing)", lambda: fdr_cache_csv("listing/krx", back_days=3))
        _rh("무인증 캐시(delisting)", lambda: fdr_cache_csv("listing/delisting", back_days=3))
        _rh("단면: 벌크 marcap", lambda: bulk_marcap_year(2020))
        _rh("단면: 일단위 캐시", lambda: _xsec_fdrcache(ts("2020-01-08")))
        _rh("단면: pykrx", lambda: _xsec_pykrx(ts("2020-01-08")), expect_rows=False)
        _rh("단면: KRX 마켓플레이스", lambda: KRXM.xsec(ts("2020-01-08")), expect_rows=False)
        _rh("구간수익률: pykrx",
            lambda: _period_return_krx(ts("2020-01-02"), ts("2020-01-08")),
            expect_rows=False)
        _rh("종목목록", lambda: _fdr_listing())
        _rh("상폐목록", lambda: _fdr_delisting())

        hub = MarketHub(dep)
        _rh("거래일 캘린더", lambda: hub.calendar("2020-01-01", "2020-01-13"))
        xs = _rh("허브 단면 적재",
                 lambda: hub.ensure(list(pd.bdate_range("2019-12-02", periods=6))))
        _rh("허브 분할보정", lambda: (hub.compute_adjusted(), 1)[1])
        sec = _rh("종목마스터 조립",
                  lambda: build_security_master(hub.slice(hub.all_dates())))
        if sec is not None and len(sec) and xs is not None and len(xs):
            cal = TradingCal(pd.bdate_range("2019-06-01", "2020-06-30"))
            months = list(month_ends("2019-12-01", "2020-02-29"))
            pr = _rh("월간 패널 조립",
                     lambda: build_month_panel(hub.all_dates(),
                                               hub.slice(hub.all_dates()), sec,
                                               months, cal)[0], expect_rows=False)
            if pr is not None and len(pr):
                _rh("유니버스 프레임", lambda: universe_frame(pr, sec), expect_rows=False)
        _rh("벤치마크",
            lambda: collect_benchmark(hub, month_ends("2020-01-01", "2020-03-31")),
            expect_rows=False)

        rep = _rh("리포트 수집(한경+네이버)",
                  lambda: collect_research("2026-03-01", "2026-03-31"))
        if rep is not None and len(rep):
            rep2 = _rh("PDF 추출·작성자 보강", lambda: enrich_with_pdf(rep))
            if rep2 is not None and len(rep2):
                secx = (sec if sec is not None and len(sec)
                        else pd.DataFrame({"code": ["005931"], "name": ["테스트"]}))
                R, A, L = build_ledger(rep2, secx)
                _rh("원장 구축", lambda: R)
                _rh("원장 감사", lambda: (audit_ledger(R, A, L), 1)[1])
                fc = _rh("예측 테이블", lambda: build_forecasts(R, L), expect_rows=False)
                if fc is not None and len(fc):
                    _rh("주지표 선택", lambda: choose_metric(fc)[0])
                    _rh("예측 검증", lambda: validate_forecasts(fc))
        _rh("DART corpCode",
            lambda: _dart_corpmap(pd.DataFrame({"code": ["005930"]})))
        _rh("DART 접수일", lambda: _dart_filing_dates("2021-01-01", "2021-03-31"))
        _rh("DART 실적 EPS",
            lambda: collect_actual_eps(
                pd.DataFrame({"code": ["005930"], "name": ["테스트"]}),
                hub.slice(hub.all_dates()), "2020-01-01", "2021-12-31"),
            expect_rows=False)
    finally:
        for k, v in saved.items():
            G[k] = v
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [r for r in REHEARSAL if not r["ok"]]
    CON.grid([[r["name"], "통과" if r["ok"] else "실패",
               f"{r['rows']:,}" if r["rows"] >= 0 else "-",
               f"{r['sec']:.2f}s", r["err"][:46]] for r in REHEARSAL],
             ["수집·정제 함수", "판정", "행수", "소요", "오류"],
             ["l", "l", "r", "r", "l"],
             title="실경로 리허설 (네트워크만 가짜 · 함수는 실물 실행)")
    for r in bad[:4]:
        if r.get("tb"):
            CON.err(f"[{r['name']}] {r['err']}")
            for ln in r["tb"].strip().splitlines()[-6:]:
                CON.say("  " + ln)
    if bad and strict:
        raise RuleBreak(
            f"실경로 리허설 {len(bad)}건 실패 — 수집부 배선이 깨져 있습니다. "
            f"이대로 실데이터를 돌리면 몇 분 뒤 같은 자리에서 죽습니다: "
            + ", ".join(r["name"] for r in bad))
    return not bad



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S3] 합성데이터 스모크 — 실데이터 전에 '계산 전 경로'를 끝까지 태워본다                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def synth_world(n_stocks: int = 60, n_analysts: int = 28, years: int = 4) -> dict:
    """알파가 '실제로 존재'하는 합성세계.
    · 각 종목의 올해 진실 EPS(tv)는 기준치(base) 대비 mis = (tv-base)/base 만큼 괴리.
    · 실력 있는 애널리스트는 tv 로 빨리 수렴, 대중은 느리게 → SCG 갭 ∝ mis.
    · 주가 드리프트도 같은 앵커 mis 에 비례 → 갭이 미래수익을 예측해야 정상.
    · 리더는 25일(≈18거래일, 20거래일 창 안) 먼저 움직인다 → 리더십 사건 관측 가능."""
    rng = np.random.default_rng(SEED)          # 예측/실적용
    rng_px = np.random.default_rng(SEED + 7)   # 가격용 — 같은 스트림 공유 금지
    days = pd.bdate_range("2019-01-02", periods=int(252 * years))
    cal = TradingCal(days)
    stocks = [f"{100000 + i * 10:06d}" for i in range(n_stocks)]
    analysts = [f"AN{i:02d}" for i in range(n_analysts)]
    skill = rng.uniform(0, 1, n_analysts)               # 심어둔 실력(정확도)
    is_leader = rng.uniform(0, 1, n_analysts) < 0.30    # 심어둔 선행성
    mis_map: Dict[Tuple[str, int], float] = {}
    fc_rows, act_rows = [], []
    fy_years = sorted({d.year for d in days})
    for s_i, sid in enumerate(stocks):
        base = rng.uniform(500, 5000)
        cover = rng.choice(n_analysts, size=int(rng.integers(4, 8)), replace=False)
        for y in fy_years:
            mis = float(np.clip(rng.normal(0.0, 0.30), -0.8, 0.8))
            tv = base * (1 + mis)
            mis_map[(sid, y)] = mis
            act_rows.append(dict(stock_id=sid, fiscal_period=f"{y}FY",
                                 forecast_metric="EPS", actual_value=tv,
                                 actual_announcement_date=ts(f"{y+1}-03-20")))
            for a_i in cover:
                aid = analysts[a_i]
                lead_shift = -25 if is_leader[a_i] else 0
                for q in range(5):        # 분기 4회 + 4Q 프리뷰(11월) — 발표 전 180일 안쪽
                    d0 = ts(f"{y}-01-20") + pd.Timedelta(
                        int(72 * q + rng.integers(0, 10) + lead_shift), "D")
                    if d0 > days[-1] or d0 < days[0]:
                        continue
                    conv = (q + 1) / 5.0                       # 대중의 수렴 속도
                    if is_leader[a_i] or skill[a_i] > 0.6:     # 정보력 집단은 선수렴
                        conv = min(1.0, conv + 0.45)
                    noise = rng.normal(0, 0.18 * (1.05 - skill[a_i]))
                    est = base * (1 + mis * conv + noise)
                    fc_rows.append(_fc_row(sid, aid, f"{d0:%Y-%m-%d}", f"{y}FY", est))
    fc = pd.DataFrame(fc_rows)
    actuals = pd.DataFrame(act_rows)
    # 가격을 '날짜 단면' 형태로 만든다 — 실경로와 동일한 자료형이어야 스모크가 의미를 갖는다
    px_rows = []
    for j, sid in enumerate(stocks):
        p = 10000.0 * float(rng_px.uniform(0.5, 3))
        arr = []
        for d in days:
            mis = mis_map.get((sid, d.year), 0.0)
            pull = 0.0022 * mis                    # 갭과 같은 앵커 → 신호가 수익을 예측
            p *= math.exp(rng_px.normal(0.0002, 0.010) + pull)
            arr.append(p)
        sh = np.full(len(days), 1e6)
        arr = np.array(arr, float)
        if j == 0:                                  # 액면분할 1건 심기(보정 경로 검증)
            k = len(days) // 2
            arr[k:] /= 5.0
            sh[k:] *= 5.0
        px_rows.append(pd.DataFrame({"date": days, "code": sid, "close": arr,
                                     "volume": 1e5, "value": arr * 1e5,
                                     "mktcap": arr * sh, "shares": sh,
                                     "market": "KOSPI"}))
    xsec = pd.concat(px_rows, ignore_index=True)
    months = month_ends(days[0], days[-1])
    # 일부 종목 중도상폐 심기(생존자편향 경로 검증) — 단면에서도 사라지게 한다
    dead_codes = stocks[-3:]
    dead_at = ts("2022-06-15")
    xsec = xsec[~(xsec["code"].isin(dead_codes) & (xsec["date"] > dead_at))]
    sec = pd.DataFrame({"code": stocks, "name": [f"합성{i}" for i in range(n_stocks)],
                        "market": "KOSPI", "list_date": ts("2010-01-01"),
                        "delist_date": pd.NaT,
                        "first_seen": days[0], "last_seen": days[-1], "is_common": True})
    sec.loc[sec["code"].isin(dead_codes), "delist_date"] = dead_at
    sec.loc[sec["code"].isin(dead_codes), "last_seen"] = dead_at
    return dict(fc=fc, actuals=actuals, xsec=xsec, sec=sec, cal=cal, months=months,
                have_dates=sorted(set(days)))


def run_smoke(full: bool) -> bool:
    S = synth_world()
    cfg = SCGParams()
    months = [m for m in S["months"]][6:-2]
    fc = validate_forecasts(S["fc"])
    fcv = with_validity(fc, cfg)
    FLOW.io("입", "합성", "forecasts", fc, src="synth_world")
    ae = acc_events_eps(fc, S["actuals"], cfg)
    le = lead_events(fc, S["cal"], cfg, "EPS")
    CON.say(f"합성 사건: 정확도 {len(ae):,} · 리더십 {len(le):,}")
    if not len(ae) or not len(le):
        CON.err("합성 사건 생성 실패")
        return False
    sc = analyst_scores(months, ae, le, cfg)
    cons, W = smart_consensus(fcv, sc, months, cfg, "EPS")
    cons = pick_primary_fp(cons, S["actuals"], "EPS")
    sig = rank_alphas(scg_signals(cons, months, S["cal"], cfg), cfg)
    panel, pmx = build_month_panel(S["have_dates"], S["xsec"], S["sec"], months, S["cal"])
    # (스모크는 ReturnHub 없이 단면 파생 경로를 태운다 — 폴백이 살아 있는지 검증)
    tp_act = tp_actuals_from_prices(fc.assign(forecast_metric="TP12M").head(50), pmx,
                                    S["cal"])          # TP 경로도 스모크에서 한 번 태운다
    CON.debug(f"합성 TP 만기 실측 {len(tp_act):,}건 · 분할보정 {pmx.n_adjusted}건")
    suites = run_suite(sig[sig["primary"]], panel, "합성")
    bt = suites["SCG_LS"]
    if bt.get("empty"):
        CON.err("합성 백테스트 결과 없음")
        return False
    rho, top_ok = monotonicity(bt)
    ic20 = bt["ic"][20]["mean_ic"]
    ok = bool(top_ok and np.isfinite(ic20) and ic20 > 0)
    CON.say(f"합성 검증: D상위>D하위={top_ok} · 단조성 ρ={rho:+.2f} · IC20={ic20:+.3f}")
    if full:
        report_all(suites, None, sig, sc, W, cons, "합성(스모크)", None, cfg)
        R_sensitivity(dict(cfg=cfg, fcv=fcv, acc_ev=ae, lead_ev=le, metric="EPS",
                           signal_dates=months, cal=S["cal"], actuals=S["actuals"],
                           sig=sig), panel)
        R_subperiod(suites)
        R_concentration(suites)
        R_placebo(sig[sig["primary"]], panel, n_iter=60)
        R_lag(sig[sig["primary"]], panel)
        robustness_verdict()
        ROBUST.clear()
    if ok:
        CON.ok("전체 스모크 통과 — 계산 경로가 심어둔 알파를 복원했습니다")
    else:
        CON.err("스모크 실패 — 실데이터 수집을 시작하지 않습니다")
    return ok


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S11] 보고부 — 성과검증표 · IC · 단조성 · 증분기여 · 진단 · 해석                           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _fmt(v, p="{:+.2%}"):
    try:
        if v is None or not np.isfinite(float(v)):
            return "-"
        return p.format(float(v))
    except Exception:
        return "-"


def report_all(suites: Dict[str, dict], bench: Optional[Dict[str, pd.Series]],
               sig: pd.DataFrame, scores: pd.DataFrame, W: pd.DataFrame,
               cons: pd.DataFrame, label: str, mtab: Optional[pd.DataFrame],
               cfg: SCGParams):
    part_note = " ⚠중간결과(수집 시간예산 소진 — 부분 데이터)" if DEADLINE.tripped else ""
    CON.head(f"성과 검증 — {label}{part_note}",
             f"metric 파라미터: {cfg.tag()} · 비용 {COST_BPS_ONEWAY:.0f}bp 편도(상위분위 net)")
    kospi = (bench or {}).get("KOSPI") if bench else None
    rows = []
    for st in STRATS:
        bt = suites.get(st, {})
        if bt.get("empty", True):
            rows.append([st] + ["-"] * 10)
            continue
        ps_ls = perf_summary(bt, kospi, leg="ls")
        ps_tp = perf_summary(bt, kospi, leg="top_net")
        rows.append([st, f"{ps_ls.get('n_signals', 0):,}",
                     f"{ps_ls.get('n_unique_stocks', 0):,}",
                     _fmt(ps_ls.get("annualized_return")), _fmt(ps_ls.get("CAGR")),
                     _fmt(ps_ls.get("volatility")),
                     _fmt(ps_ls.get("Sharpe"), "{:+.2f}"), _fmt(ps_ls.get("MDD")),
                     _fmt(ps_ls.get("hit_rate"), "{:.0%}"),
                     _fmt(ps_ls.get("turnover"), "{:.0%}"),
                     _fmt(ps_ls.get("average_holdings"), "{:.0f}")])
        rows.append(["  └ 상위분위(비용차감)", "", "",
                     _fmt(ps_tp.get("annualized_return")), _fmt(ps_tp.get("CAGR")),
                     _fmt(ps_tp.get("volatility")),
                     _fmt(ps_tp.get("Sharpe"), "{:+.2f}"), _fmt(ps_tp.get("MDD")),
                     _fmt(ps_tp.get("hit_rate"), "{:.0%}"), "",
                     _fmt(ps_tp.get("excess_vs_bench_ann"))])
    CON.grid(rows, ["전략(L/S=상위-하위)", "n_signals", "n_stocks", "연환산", "CAGR",
                    "변동성", "Sharpe", "MDD", "월승률", "회전율", "평균종목/벤치초과"],
             ["l"] + ["r"] * 10, title=f"§37 전략별 성과 — {label}")

    ic_rows = []
    for st in STRATS:
        bt = suites.get(st, {})
        if bt.get("empty", True):
            continue
        for h in (20, 60, 120):
            ic = bt["ic"][h]
            ic_rows.append([st, f"{h}일", _fmt(ic["mean_ic"], "{:+.4f}"),
                            _fmt(ic["median_ic"], "{:+.4f}"),
                            _fmt(ic["ic_std"], "{:.4f}"), _fmt(ic["ic_ir"], "{:+.2f}"),
                            _fmt(ic["positive_ic_ratio"], "{:.0%}"), ic["n_dates"]])
    CON.grid(ic_rows, ["전략", "지평", "mean_ic", "median_ic", "ic_std", "ic_ir",
                       "IC>0 비율", "표본"],
             ["l", "r", "r", "r", "r", "r", "r", "r"],
             title=f"§40 IC 검증 (20/60/120 거래일) — {label}")

    mono_rows = []
    for st in STRATS:
        bt = suites.get(st, {})
        if bt.get("empty", True):
            continue
        rho, top_ok = monotonicity(bt)
        dec = bt["decile"].sort_values("bucket")
        dec_str = " ".join(f"{v*100:+.1f}" for v in dec["mean_fwd_1m"])
        mono_rows.append([st, f"{bt['nq']}분위", dec_str,
                          _fmt(rho, "{:+.2f}"), "예" if top_ok else "아니오"])
    CON.grid(mono_rows, ["전략", "분위수", "분위별 평균수익(%/월, 하위→상위)",
                         "Spearman", "상위>하위"],
             ["l", "l", "l", "r", "l"], title=f"§39 단조성 검증 — {label}")

    def _mean_ls(st):
        bt = suites.get(st, {})
        if bt.get("empty", True):
            return np.nan
        return float(bt["returns"]["ls"].dropna().mean()) * 12

    def _ic20(st):
        bt = suites.get(st, {})
        return bt["ic"][20]["mean_ic"] if not bt.get("empty", True) else np.nan

    inc = []
    for q, a, b in (("질문1 SCG_0 > BASE_REV ?", "SCG_0", "BASE_REV"),
                    ("질문2 SCG_LS > SCG_0 ?", "SCG_LS", "SCG_0"),
                    ("질문3 SCG_LSA > SCG_LS ?", "SCG_LSA", "SCG_LS")):
        la, lb = _mean_ls(a), _mean_ls(b)
        ia, ib = _ic20(a), _ic20(b)
        verdict = "YES" if (np.isfinite(la) and np.isfinite(lb) and la > lb
                            and np.isfinite(ia) and np.isfinite(ib) and ia > ib) else \
            ("혼재" if (np.isfinite(la) and np.isfinite(lb) and (la > lb) != (ia > ib))
             else "NO")
        inc.append([q, f"{_fmt(la)} vs {_fmt(lb)}",
                    f"{_fmt(ia, '{:+.4f}')} vs {_fmt(ib, '{:+.4f}')}", verdict])
    CON.grid(inc, ["§47 핵심 연구질문", "L/S 연환산 (좌>우?)", "IC20 (좌>우?)", "판정"],
             ["l", "r", "r", "c"], title=f"§38 증분 기여 검증 — {label}")

    if mtab is not None:
        pass  # 주지표 선택 근거표는 S6 에서 이미 출력
    if len(cons):
        dc = diag_analyst_counts(cons)
        if len(dc):
            t = dc.tail(1).iloc[0]
            CON.grid([[f"{int(t['count']):,}", f"{t['mean']:.1f}", f"{t['median']:.0f}",
                       f"{t['p10']:.0f}/{t['p25']:.0f}/{t['p75']:.0f}/{t['p90']:.0f}"]],
                     ["커버 종목수(최근월)", "평균 애널리스트", "중앙값", "p10/25/75/90"],
                     ["r"] * 4, title="§34.1 애널리스트 커버리지 분포(최근 signal date)")
    if len(scores):
        sh = diag_shrinkage(scores)
        if len(sh):
            top = sh.reindex(sh["acc_star"].abs().sort_values(ascending=False).index).head(8)
            CON.grid([[r["analyst_id"][:10], int(r["acc_n"]), int(r["lead_n"]),
                       _fmt(r["acc_raw"], "{:+.3f}"), _fmt(r["acc_star"], "{:+.3f}"),
                       _fmt(r["lead_raw"], "{:+.3f}"), _fmt(r["lead_star"], "{:+.3f}")]
                      for _, r in top.iterrows()],
                     ["analyst", "acc_n", "lead_n", "acc_raw", "acc★", "lead_raw", "lead★"],
                     ["l"] + ["r"] * 6,
                     title="§34.2 수축 진단 — 표본 적은 애널리스트가 과대평가되지 않는가"
                           " (★ = 수축 후)")
    if len(W):
        wc = diag_weight_conc(W)
        if len(wc):
            CON.grid([[_fmt(wc["max_weight_share"].mean(), "{:.0%}"),
                       _fmt(wc["top2_weight_share"].mean(), "{:.0%}"),
                       f"{wc['effective_analyst_n'].mean():.2f}"]],
                     ["최대가중 평균", "상위2 평균", "유효 애널리스트 수(평균)"],
                     ["r"] * 3, title="§34.3 가중 집중도(진단용 — 게이트 아님)")


def interpretation_tables(metric: str):
    CON.grid([
        ["SCG_LS > 0", "최근성 높고, 실적을 상대적으로 잘 맞혔고, 남들이 따라오게 만든 "
                       "애널리스트들이 컨센서스보다 높은 전망을 냄", "정보 선반영 매수 후보(§46)"],
        ["SCG_LS < 0", "고정보력 집단이 컨센서스보다 낮은 전망", "지연 하향 위험"],
        ["SCG_ACCEL > 0", "고정보력-일반 격차가 최근 더 벌어짐", "정보 확산 초기 국면"],
        ["BASE_REV", "일반 컨센서스의 20거래일 변화(비교 벤치마크)", "SCG 추가알파의 기준선"],
        ["INSUFFICIENT_ANALYSTS", "활성 애널리스트 2명 미만 — 신호 미산출(제거 아님)", "표본 보존 §6.2"],
    ], ["신호", "경제적 의미", "해석/행동"], ["l", "l", "l"],
        title=f"기타 해석표 — 신호의 의미 (주지표: {metric})")
    CON.grid([
        ["정확도 사건", "실적발표 직전 스냅샷에서 '당시 컨센서스 대비' 로그 상대오차(§8)"],
        ["리더십 사건", "수정 후 20거래일, 자신 제외 동료 컨센서스의 동방향 추종(§14)"],
        ["수축", "사건 n 이 적으면 λ=n/(n+6) 로 중립(0)으로 끌어당김(§10·§17)"],
        ["가중치", "W = 2^(-경과일/45) × clip(e^(0.7·Q), 0.5, 2.0) (§19~22)"],
        ["PIT", "모든 점수는 signal date 이전 완결 사건만 사용, t20<T (§16)"],
    ], ["구성요소", "정의"], ["l", "l"], title="산식 요약(감사용)")


def coverage_table(fc: pd.DataFrame, R: pd.DataFrame, xsec: pd.DataFrame,
                   actuals: pd.DataFrame):
    rows = [["보고서 원장", f"{len(R):,}건",
             f"{R['date'].min():%Y-%m}~{R['date'].max():%Y-%m}" if len(R) else "-"],
            ["예측 테이블", f"{len(fc):,}행",
             f"{fc['report_date'].min():%Y-%m}~{fc['report_date'].max():%Y-%m}"
             if len(fc) else "-"],
            ["전종목 단면", f"{xsec['code'].nunique():,}종목 / "
                            f"{xsec['date'].nunique():,}일",
             f"{xsec['date'].min():%Y-%m}~{xsec['date'].max():%Y-%m}"
             if len(xsec) else "-"],
            ["실적(actual)", f"{len(actuals):,}건", ""],
            ["수집 상태", "중간결과(시간예산 소진 — 재실행 시 이어받음)"
             if DEADLINE.tripped else "정상 완료", ""]]
    CON.grid(rows, ["데이터", "규모", "범위"], ["l", "r", "l"],
             title="데이터 커버리지(결과 신뢰 범위의 근거)")


def offer_downloads(paths: List[str]):
    """미리보기 없이 '클릭=저장' 링크만. Colab 은 즉시 다운로드, Jupyter 는 data 링크."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if RIG["colab"]:
        try:
            from google.colab import files as _f      # type: ignore
            for p in paths:
                _println(f"⬇ 다운로드: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML     # type: ignore
        import base64
        html = ["<div style='font-family:sans-serif'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 대용량: <code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;"
                        f"text-decoration:none'>⬇ {os.path.basename(p)} "
                        f"({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _println(f"⬇ 산출물 경로: {p}")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ 오케스트레이터 — 전체 실행                                                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def run_all() -> dict:
    global DEPOT
    t_all = time.time()
    CON.head(f"SCG Smart Consensus Gap 백테스트  [{SCG_BUILD}]",
             f"{BACKTEST_START} ~ {BACKTEST_END} · 모드 {RUN_MODE} · 4전략 "
             f"{'/'.join(STRATS)} · 비교 시총하위{COMPARE_BOTTOM_N}")
    CON.grid([["환경", "Colab" if RIG["colab"] else ("Jupyter" if RIG["ipython"] else "CLI")],
              ["파이썬/OS", f"{RIG['python']} / {RIG['os']} {RIG['cpu']}코어"],
              ["사용 가능 패키지",
               ", ".join(n for n, m in (("scipy", _scistats), ("FinanceDataReader", fdr),
                                        ("pykrx", pykrx_stock), ("yfinance", yf),
                                        ("pymupdf", _fitz), ("pdfplumber", _pdfplumber))
                         if m is not None) or "없음"],
              ["import 실패", "; ".join(f"{k}({v.split(':')[0]})"
                                        for k, v in IMPORT_ERR.items()) or "없음"],
              ["수집 시간예산", f"{COLLECT_HOURS_BUDGET:.1f}시간 (초과 시 중간결과 산출)"],
              ["KRX 마켓플레이스", "ID 입력됨" if KRX_MARKETPLACE_ID else "미입력(폴백 사용)"],
              ["DART 키", "입력됨" if DART_API_KEY else "미입력(네이버 실적 폴백)"]],
             ["항목", "값"], ["l", "l"], title="실행 환경")

    with FLOW.part("S1", "캐시 금고 연결(로컬 D드라이브+구글드라이브 다중루트)", budget_s=300):
        DEPOT = Depot()
        globals()["DEPOT"] = DEPOT
        CON.say(f"쓰기 루트: {DEPOT.write_root} ({DEPOT.drive_mode})")
        if not DEPOT.on_drive and RUN_MODE != "SMOKE":
            CON.warn("구글드라이브 미연결 — 산출물이 로컬에만 저장됩니다. "
                     "절대1원칙(드라이브 저장)을 위해 드라이브 연결을 권장합니다.")
        CON.say(f"읽기 루트(기존 캐시, 읽기전용) {len(DEPOT.read_roots)}개: "
                + (", ".join(DEPOT.read_roots[:4]) + ("…" if len(DEPOT.read_roots) > 4 else "")
                   if DEPOT.read_roots else "없음"))
        QUOTA.load()
        DEPOT.scan_adopt_pdfs()

    with FLOW.part("S2", "자체계약 검증(TEST1~9 + 구조계약)", budget_s=240):
        run_contracts(strict=True)

    # ★ 계약(S2)은 '계산 규칙'을, 리허설(S2b)은 '수집 배선'을 증명한다. 둘은 겹치지 않는다.
    #   S2b 가 없던 빌드가 S2·S3 를 다 통과하고도 실행 2분 만에 수집부 한 줄 때문에 죽었다.
    with FLOW.part("S2b", "실경로 리허설(수집 함수 실물 실행)", budget_s=300):
        run_rehearsal(strict=True)

    with FLOW.part("S3", "합성데이터 전체경로 스모크", budget_s=1800):
        if not run_smoke(full=(RUN_MODE == "SMOKE")):
            raise HaltRun("스모크 실패 — 계산 경로 결함. 실데이터 수집을 시작하지 않습니다.")
    if RUN_MODE == "SMOKE":
        FLOW.parts_table()
        DEPOT.audit_table()
        CON.head("SMOKE 완료", "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요")
        return {"mode": "SMOKE"}

    months = month_ends(BACKTEST_START, BACKTEST_END)
    DEADLINE.start()

    with FLOW.part("S4a", "거래일 캘린더 + 필요 호출 산출", budget_s=900):
        HUB = MarketHub(DEPOT)
        RET = ReturnHub(DEPOT)
        cal_days = HUB.calendar((ts(BACKTEST_START) - pd.DateOffset(months=15)
                                 ).strftime("%Y-%m-%d"), BACKTEST_END)
        cal = TradingCal(cal_days)
        # ★ 필요한 호출만 정확히 계산한다 — 종목별 시계열은 단 한 번도 받지 않는다.
        #   ① 신호일(월말) 단면 : 유니버스·시총·주식수·가격    → 월당 1콜
        #   ② 구간 수익률       : 신호일→(익월/20/60/120td)   → 월당 4콜, 전 종목 동시
        snap_dates, ret_pairs = [], []
        anchors, anchor_of = [], {}
        for m in months:
            p = cal.pos(m)
            if p < 0:
                continue
            d0 = pd.Timestamp(cal.days[p])
            anchors.append(d0)
            anchor_of[pd.Timestamp(m)] = d0     # 월 → 앵커(구간수익률 캐시 키와 일치)
            snap_dates.append(d0)
        for i, d0 in enumerate(anchors):
            if i + 1 < len(anchors):
                ret_pairs.append((d0, anchors[i + 1]))
            for h in (20, 60, 120):
                dh = cal.shift(d0, h)
                if dh is not None:
                    ret_pairs.append((d0, pd.Timestamp(dh)))
        snap_dates = sorted(set(snap_dates))
        ret_pairs = list(dict.fromkeys(ret_pairs))
        probe_market_sources(cal)
        if MARKET_PROBE_BULK:          # 진단에서 받은 벌크는 버리지 않고 그대로 적재
            HUB._load_year(int(MARKET_PROBE_BULK[0]["date"].iloc[0].year))
            HUB._absorb(MARKET_PROBE_BULK)
            HUB._bulk_tried.add(int(MARKET_PROBE_BULK[0]["date"].iloc[0].year))
            HUB.flush()
        CON.grid([["신호일 단면", f"{len(snap_dates):,}콜", "전 종목 가격·시총·주식수"],
                  ["구간 수익률", f"{len(ret_pairs):,}콜",
                   "전 종목 수정주가 등락률(상폐 -100% 포함)"],
                  ["종목별 시계열", "0콜", "쓰지 않음 — 이전 설계의 병목이었습니다"]],
                 ["호출 종류", "예상 호출", "무엇을 받는가"], ["l", "r", "l"],
                 title="시장 데이터 호출 계획 (캐시 적중분은 실제로 호출되지 않습니다)")
        FLOW.io("출", "메모리", "호출계획", snap_dates + ret_pairs)

    with FLOW.part("S4b", "전종목 단면 + 구간 수익률 수집", budget_s=3600 * 2):
        # 벌크가 일별 전체를 주므로, 필요한 날짜만 뽑지 말고 지평 날짜까지 함께 확보한다
        # (이미 받은 데이터 안에 있으므로 추가 호출이 0이다).
        want_dates = sorted(set(snap_dates) | {pd.Timestamp(b) for _, b in ret_pairs})
        HUB.ensure(want_dates)
        HUB.compute_adjusted()          # 일별 인접 거래일로 분할보정(가장 정확)
        xsec = HUB.slice(want_dates)
        HUB.flush()
        have_adj = ("adj_close" in xsec.columns and xsec["adj_close"].notna().mean() > 0.9)
        if have_adj:
            CON.ok("일별 분할보정 가격을 확보했습니다 — 구간 수익률 API 호출 "
                   f"{len(ret_pairs)}건을 생략합니다(같은 값을 이미 갖고 있으므로 "
                   f"불필요한 반복 조회를 하지 않습니다).")
        else:
            RET.ensure(ret_pairs)
            RET.flush()
            cov = len(RET.have & set(ret_pairs)) / max(len(ret_pairs), 1)
            CON.say(f"구간 수익률 커버리지 {cov*100:.0f}%")
        FLOW.io("출", "메모리", "전종목단면", xsec)
        sec = build_security_master(xsec)
        FLOW.io("출", "메모리", "종목마스터", sec)
        bench = collect_benchmark(HUB, months)

    with FLOW.part("S4c", "애널리스트 리포트 수집(한경+네이버)", budget_s=3600 * 2,
                   skip=not RESEARCH_COLLECT and RUN_MODE != "CACHED",
                   why="RESEARCH_COLLECT=False"):
        rep_raw = collect_research(BACKTEST_START, BACKTEST_END)
        rep_raw = enrich_with_pdf(rep_raw)

    # 비치명 단계가 실패해도 하류가 NameError 로 죽지 않도록 먼저 빈 값으로 바인딩
    actuals = pd.DataFrame(columns=["stock_id", "fiscal_period", "forecast_metric",
                                    "actual_value", "actual_announcement_date"])
    with FLOW.part("S4d", "실적 EPS·발표일(DART→네이버 폴백)", budget_s=3600,
                   critical=False):
        actuals = collect_actual_eps(sec, xsec, BACKTEST_START, BACKTEST_END)

    with FLOW.part("S5", "원장 구축 + 연결 감사", budget_s=600):
        R, A, L = build_ledger(rep_raw, sec)
        audit_ledger(R, A, L)
        DEPOT.table_save("scg_report_ledger", R, scope="공용", domain="research",
                         source="entity_resolution")
        DEPOT.table_save("scg_analyst_ledger", A, scope="공용", domain="research",
                         source="entity_resolution")
        DEPOT.table_save("scg_report_analyst_link", L, scope="공용", domain="research",
                         source="entity_resolution")

    with FLOW.part("S6", "예측 테이블(EPS/TP12M) + 주지표 선택", budget_s=900):
        fc_all = build_forecasts(R, L)
        if not len(fc_all):
            raise HaltRun("예측 테이블이 비었습니다 — 리포트 수집/PDF 추출을 확인하세요. "
                          "(RUN_MODE='SMOKE' 로 계산 경로는 검증 가능합니다)")
        fc_all = fc_all[fc_all["stock_id"].isin(set(sec["code"]))]
        if not len(fc_all):
            raise HaltRun("예측 테이블과 종목마스터의 교집합이 비었습니다 — "
                          "종목코드 형식(6자리)과 마스터 수집을 확인하세요.")
        DEPOT.table_save("scg_analyst_forecasts", fc_all, scope="공용", domain="research",
                         source="ledger+pdf")
        metric, mtab = choose_metric(fc_all)
        cfg = SCGParams()
        fc = validate_forecasts(fc_all, asof=ts(BACKTEST_END) + pd.Timedelta(7, "D"))
        fcv = with_validity(fc, cfg)
        sig_months = [m for m in months if m >= fc["report_date"].min()]
        # 가격 행렬을 여기서 한 번만 만들고, 이후 백테스트·IC·목표가 만기가 전부 재사용한다
        panel, PMX = build_month_panel(HUB.all_dates(), xsec, sec, sig_months, cal,
                                       rethub=RET, anchors=anchor_of)
        tp_act = tp_actuals_from_prices(fc, PMX, cal) if metric == "TP12M" else \
            pd.DataFrame(columns=["report_id", "matured_at", "actual_price"])

    with FLOW.part("S7", "SCG 엔진(사건→PIT점수→스마트컨센서스→신호)", budget_s=3600):
        if metric == "EPS":
            acc_ev = acc_events_eps(fc, actuals, cfg)
        else:
            acc_ev = acc_events_tp(fc, tp_act, cfg)
        led_ev = lead_events(fcv, cal, cfg, metric)
        CON.say(f"사건 테이블: 정확도 {len(acc_ev):,} · 리더십 {len(led_ev):,}")
        FLOW.io("출", "메모리", "정확도사건", acc_ev)
        FLOW.io("출", "메모리", "리더십사건", led_ev)
        scores = analyst_scores(sig_months, acc_ev, led_ev, cfg)
        cons, W = smart_consensus(fcv, scores, sig_months, cfg, metric)
        cons = pick_primary_fp(cons, actuals, metric)
        sig = rank_alphas(scg_signals(cons, sig_months, cal, cfg), cfg)
        ENG = dict(cfg=cfg, fcv=fcv, acc_ev=acc_ev, lead_ev=led_ev, metric=metric,
                   signal_dates=sig_months, cal=cal, actuals=actuals, sig=sig)

    with FLOW.part("S8", "백테스트 — 전체 PIT 유니버스", budget_s=1800):
        # PIT 유니버스 = 그 달 단면에 실재한 보통주. 상장/폐지 목록 정확도에 의존하지 않는다.
        uni_df = universe_frame(panel, sec)
        sigp = sig[sig["primary"]].merge(uni_df, on=["signal_date", "stock_id"], how="left")
        sig_full = sigp[sigp["in_uni"].fillna(False)]
        CON.say(f"신호×유니버스 교집합: {len(sig_full):,}행 "
                f"(월평균 {len(sig_full)/max(len(sig_months),1):.0f}종목)")
        suites_full = run_suite(sig_full, panel, "전체 유니버스", bench)
        report_all(suites_full, bench, sig_full, scores, W, cons,
                   "전체 유니버스", mtab, cfg)

    suites_small: Dict[str, dict] = {}
    with FLOW.part("S9", f"비교전략 — 시총 하위{COMPARE_BOTTOM_N}", budget_s=1200,
                   critical=False):
        # 시총은 각 신호일 단면에 실측으로 들어 있다 — 그 달의 유니버스 안에서 하위 N.
        uu = uni_df.dropna(subset=["mktcap"])
        sm = None
        if len(uu):
            sm = (uu.sort_values("mktcap")
                    .groupby("signal_date", observed=True, sort=False)
                    .head(COMPARE_BOTTOM_N)[["signal_date", "stock_id"]].copy())
        if sm is not None and len(sm):
            sm["in_small"] = True
            sigs = sig_full.merge(sm, on=["signal_date", "stock_id"], how="left")
            mask = sigs["in_small"].fillna(False)
            sig_small = alphas_in_universe(sigs, mask, cfg)
            CON.say(f"하위{COMPARE_BOTTOM_N} 유니버스 신호: {len(sig_small):,}행")
            suites_small = run_suite(sig_small, panel, f"시총하위{COMPARE_BOTTOM_N}", bench)
            report_all(suites_small, bench, sig_small, scores, W, cons,
                       f"시총 하위{COMPARE_BOTTOM_N} 비교전략", None, cfg)
            R_subperiod(suites_small)
            R_concentration(suites_small)
        else:
            CON.warn("단면에 시가총액이 없어 비교전략을 건너뜁니다 — pykrx 수집을 확인하세요")

    with FLOW.part("S10", "강건성 검사(전체 유니버스)", budget_s=3600 * 2, critical=False):
        R_sensitivity(ENG, panel)
        R_subperiod(suites_full)
        R_concentration(suites_full)
        R_placebo(sig_full, panel)
        R_lag(sig_full, panel)
        R_cost_stress(sig_full, panel,
                      nq=suites_full.get("SCG_LS", {}).get("nq"))
        robustness_verdict()

    with FLOW.part("S11", "해석표 · 저장(공용/전용 인덱스) · 다운로드", budget_s=900,
                   critical=False):
        interpretation_tables(metric)
        coverage_table(fc, R, xsec, actuals)
        outdir = os.path.join(DEPOT.ns["전용"], "report")
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        # §33 필수 산출물 — 전용 인덱스
        DEPOT.table_save("analyst_score_history", scores, scope="전용", domain="scores")
        DEPOT.table_save("analyst_forecast_weights", shrink(W), scope="전용", domain="scores")
        DEPOT.table_save("smart_consensus_daily", shrink(sig), scope="전용", domain="signals")
        for nm, df in (("analyst_count_distribution", diag_analyst_counts(cons)),
                       ("shrinkage_diagnostics", diag_shrinkage(scores)),
                       ("weight_concentration", diag_weight_conc(W))):
            p = os.path.join(outdir, f"{nm}_{stamp}.csv")
            if len(df):
                df.to_csv(p, index=False, encoding="utf-8-sig")
                outs.append(p)
        for st, bt in {**suites_full, **{f"small_{k}": v for k, v in
                                         (suites_small or {}).items()}}.items():
            if isinstance(bt, dict) and not bt.get("empty", True):
                p = os.path.join(outdir, f"returns_{st}_{stamp}.csv")
                bt["returns"].to_csv(p, index=False, encoding="utf-8-sig")
                outs.append(p)
        logp = os.path.join(outdir, f"log_{stamp}.txt")
        write_atomic_text(logp, "\n".join(CON.buffer))
        outs.append(logp)
        DEPOT.snapshot_indexes()
        QUOTA.report()
        http_report()
        DEPOT.audit_table()
        FLOW.parts_table()
        FLOW.io_table()
        dataflow_map()
        offer_downloads(outs)

    CON.head("완료" + (" — 중간결과(부분 데이터)" if DEADLINE.tripped else ""),
             f"총 {(time.time()-t_all)/60:.1f}분 · 산출물은 구글드라이브 "
             f"공용/전용 인덱스에 저장되었습니다"
             + (" · 재실행하면 수집을 이어받아 완전한 결과를 만듭니다"
                if DEADLINE.tripped else ""))
    return {"suites_full": suites_full, "suites_small": suites_small, "sig": sig,
            "scores": scores, "metric": metric, "partial": DEADLINE.tripped}


if __name__ == "__main__" or RIG["ipython"]:
    try:
        RESULT = run_all()
    except RuleBreak as e:
        CON.head("⛔ 계약 위반으로 중단", "파라미터를 조정해 통과시키지 마십시오")
        _println(f"  {e}")
        FLOW.parts_table()
    except HaltRun as e:
        CON.head("실행 중단", "위 '실패 지점 상세'와 단계 원장에서 원인을 확인하세요")
        _println(f"  {e}")
        FLOW.parts_table()
        FLOW.io_table()
    except KeyboardInterrupt:
        CON.warn("사용자 중단 — 지금까지 수집분은 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다")
        FLOW.parts_table()
