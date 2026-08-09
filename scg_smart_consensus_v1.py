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
QPS = {"krx": 2.0, "dart": 8.0, "hankyung": 2.0, "naver": 2.5, "kind": 2.0,
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

try:
    import scipy.stats as _scistats
except Exception:
    _scistats = None
try:
    import FinanceDataReader as fdr
except Exception:
    fdr = None
try:
    from pykrx import stock as pykrx_stock
except Exception:
    pykrx_stock = None
try:
    import yfinance as yf
except Exception:
    yf = None
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
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    if _scistats is not None:
        return float(_scistats.spearmanr(a[m], b[m]).statistic)
    ra = pd.Series(a[m]).rank().to_numpy()
    rb = pd.Series(b[m]).rank().to_numpy()
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
             os.path.join(home, "GoogleDrive"), "G:/My Drive", "G:/내 드라이브"]
    for c in cands:
        if os.path.isdir(c):
            return os.path.join(c, os.path.basename(GDRIVE_WRITE_ROOT)), "데스크톱동기화"
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
# ║ [S4-a] KRX 마켓플레이스 세션 + 시가총액 스냅샷                                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
class KrxSession:
    LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    HOME = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    DATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    def __init__(self, user: str, pw: str):
        self.user, self.pw = user, pw
        self.state = "미시도"
        self._t_login = 0.0
        self._lk = threading.RLock()

    def login(self) -> bool:
        with self._lk:
            if not self.user:
                self.state = "자격증명없음"
                CON.say("KRX 마켓플레이스 ID 미입력 — 시총 스냅샷은 pykrx/FDR 폴백으로 진행합니다.")
                return False
            fetch(self.HOME, source="krx")                      # 쿠키 웜업(없으면 POST 거절)
            fetch(self.LOGIN_PAGE, source="krx")
            body = {"mbrId": self.user, "pw": self.pw, "telNo": "", "mbrNm": "",
                    "certType": "", "di": ""}
            for extra in ({}, {"skipDup": "Y"}):                # 중복로그인(CD011)이면 기존 세션 정리
                THROTTLE.wait("krx")
                try:
                    r = _sess().post(self.LOGIN_POST, data={**body, **extra},
                                     headers={"Referer": self.LOGIN_PAGE}, timeout=20)
                    txt = r.text[:800]
                except Exception as e:
                    self.state = f"접속실패:{type(e).__name__}"
                    return False
                if re.search(r"CD011|중복\s*로그인", txt):
                    continue
                if not re.search(r"실패|불일치|오류|password|fail", txt, re.I):
                    self.state, self._t_login = "로그인성공", time.time()
                    CON.ok("KRX 마켓플레이스 로그인 성공")
                    return True
            self.state = "로그인실패"
            CON.warn("KRX 로그인 실패 — ID/PW 확인. 시총 스냅샷은 폴백 소스로 진행합니다.")
            return False

    def _fresh(self):
        if self.state == "로그인성공" and time.time() - self._t_login > 45 * 60:
            CON.debug("KRX 세션 45분 경과 — 선제 재로그인")
            self.login()

    def jsondata(self, bld: str, **params) -> Optional[dict]:
        if self.state != "로그인성공":
            return None
        self._fresh()
        THROTTLE.wait("krx")
        QUOTA.spend("krx")
        try:
            r = _sess().post(self.DATA, data={"bld": bld, **params},
                             headers={"Referer": self.HOME}, timeout=25)
            t = r.text.lstrip()
            if not t.startswith("{"):                # 로그인 HTML → 세션 만료
                CON.debug("KRX JSON 대신 HTML 수신 — 재로그인 후 1회 재시도")
                if self.login():
                    r = _sess().post(self.DATA, data={"bld": bld, **params},
                                     headers={"Referer": self.HOME}, timeout=25)
                    t = r.text.lstrip()
            return json.loads(t) if t.startswith("{") else None
        except Exception:
            return None

    def mktcap_snapshot(self, day: pd.Timestamp) -> Optional[pd.DataFrame]:
        js = self.jsondata("dbms/MDC/STAT/standard/MDCSTAT01501",
                           mktId="ALL", trdDd=f"{day:%Y%m%d}",
                           share="1", money="1", csvxls_isNo="false")
        rows = (js or {}).get("OutBlock_1") or []
        if not rows:
            return None
        rec = []
        for r in rows:
            c = code6(r.get("ISU_SRT_CD"))
            if not c:
                continue
            def _num(x):
                try:
                    return float(str(x).replace(",", ""))
                except Exception:
                    return np.nan
            rec.append((c, str(r.get("ISU_ABBRV", "")), str(r.get("MKT_NM", "")),
                        _num(r.get("TDD_CLSPRC")), _num(r.get("MKTCAP")),
                        _num(r.get("LIST_SHRS"))))
        return pd.DataFrame(rec, columns=["code", "name", "market", "close", "mktcap", "shares"])


KRXS = KrxSession(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW)


def _pykrx_call(fn: Callable, *a, **k):
    """pykrx 호출 직렬화 + 스로틀 — KRX 는 병렬 요청에 세션을 끊는다."""
    with _PYKRX_LOCK:
        THROTTLE.wait("krx")
        QUOTA.spend("krx")
        try:
            return fn(*a, **k)
        except Exception as e:
            CON.debug(f"pykrx 실패({type(e).__name__}): {getattr(fn, '__name__', fn)}")
            return None


_PYKRX_LOCK = threading.RLock()


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-b] PIT 유니버스 — 상장/상폐 이력 + 월별 시총 스냅샷 (생존자편향 제거의 뼈대)            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _fdr_listing() -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        d = fdr.StockListing("KRX")
    except Exception:
        return None
    if d is None or not len(d):
        return None
    lc = {str(c).lower(): c for c in d.columns}
    out = pd.DataFrame({
        "code": d[lc.get("code", lc.get("symbol", list(d.columns)[0]))].map(code6),
        "name": d[lc["name"]].astype(str) if "name" in lc else "",
        "market": d[lc["market"]].astype(str) if "market" in lc else "",
        "list_date": ts_col(d[lc["listingdate"]]) if "listingdate" in lc else pd.NaT,
    })
    return out.dropna(subset=["code"])


def _fdr_delisting() -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        d = fdr.StockListing("KRX-DELISTING")
    except Exception:
        return None
    if d is None or not len(d):
        return None
    lc = {str(c).lower(): c for c in d.columns}
    code_c = lc.get("symbol", lc.get("code"))
    del_c = lc.get("delistingdate", lc.get("delistdate"))
    if not code_c or not del_c:
        return None
    out = pd.DataFrame({"code": d[code_c].map(code6),
                        "name": d[lc["name"]].astype(str) if "name" in lc else "",
                        "delist_date": ts_col(d[del_c])})
    out = out.dropna(subset=["code", "delist_date"])
    return out.sort_values("delist_date").drop_duplicates("code", keep="last")


def _kind_listing() -> Optional[pd.DataFrame]:
    """KIND 상장법인목록 — FDR 불능 시 폴백."""
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    raw = fetch(url, source="kind", params={"method": "download", "searchType": "13"},
                as_bytes=True)
    if not raw:
        return None
    try:
        tables = pd.read_html(io.BytesIO(raw), encoding="euc-kr")
    except Exception:
        try:
            tables = pd.read_html(io.BytesIO(raw), encoding="cp949")
        except Exception:
            return None
    if not tables:
        return None
    d = tables[0]
    cols = {str(c): c for c in d.columns}
    cc = next((cols[c] for c in cols if "종목코드" in c), None)
    nc = next((cols[c] for c in cols if "회사명" in c), None)
    dc = next((cols[c] for c in cols if "상장일" in c), None)
    if cc is None:
        return None
    return pd.DataFrame({"code": d[cc].map(code6), "name": d[nc].astype(str) if nc else "",
                         "market": "", "list_date": ts_col(d[dc]) if dc else pd.NaT}
                        ).dropna(subset=["code"])


_SPECIAL_NAME = re.compile(r"스팩|SPAC|ETN|ETF|리츠|REIT|인프라|우$|우B$|\d호(?![가-힣])", re.I)


def _is_common_stock(code: str, name: str) -> bool:
    """보통주만 남긴다 — 우선주(코드 끝자리 0 아님)·스팩·ETF/ETN·리츠 제외.
    (컨센서스 전략의 대상은 보통주다. 제외 규칙은 여기 한 곳에만 둔다)"""
    if not code:
        return False
    if re.fullmatch(r"\d{6}", code) and not code.endswith("0"):
        return False
    if _SPECIAL_NAME.search(str(name) or ""):
        return False
    return True


def collect_universe(months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """반환 sec: code·name·market·list_date·delist_date / mcap: month·code·mktcap·shares·close"""
    sec = DEPOT.table_load("scg_security_master",
                           foreign_patterns=["security_master"],
                           need_cols=["code", "name"])
    if sec is not None:
        sec = sec.rename(columns={"listing_date": "list_date",
                                  "delisting_date": "delist_date"})
        for c in ("list_date", "delist_date"):
            sec[c] = ts_col(sec[c]) if c in sec.columns else pd.NaT
        sec["code"] = sec["code"].map(code6)
        sec = sec.dropna(subset=["code"])
        # ★ 캐시된 마스터에 상폐 이력이 없으면 그대로 쓰는 순간 생존자편향이다.
        #   신선한 상폐 목록을 덧입히고, 그래도 없으면 크게 경고한다.
        if int(sec["delist_date"].notna().sum()) < 200:
            dl = _fdr_delisting() if RUN_MODE != "CACHED" else None
            if dl is not None and len(dl):
                dmap = dl.set_index("code")["delist_date"].to_dict()
                sec["delist_date"] = sec["delist_date"].fillna(
                    sec["code"].map(dmap))
                CON.ok(f"캐시 마스터에 상폐 이력 보강: {int(sec['delist_date'].notna().sum()):,}건")
            else:
                CON.warn("캐시된 종목마스터에 상폐 이력이 거의 없습니다(<200) — "
                         "생존자편향 위험. 온라인 재실행으로 보강을 권장합니다.")
    else:
        lst = _fdr_listing()
        if lst is None or len(lst) < 500:
            lst = _kind_listing()
        if lst is None or not len(lst):
            raise HaltRun("상장목록을 어느 소스에서도 얻지 못했습니다(FDR/KIND) — 네트워크 확인")
        dl = _fdr_delisting()
        FLOW.io("입", "HTTP", "상장목록", lst, src="FDR/KIND")
        FLOW.io("입", "HTTP", "상폐목록", dl, src="FDR")
        sec = lst.copy()
        if dl is not None and len(dl):
            sec = sec.merge(dl[["code", "delist_date"]], on="code", how="outer")
            nm = dl.set_index("code")["name"].to_dict()
            sec["name"] = sec["name"].fillna(sec["code"].map(nm))
        else:
            sec["delist_date"] = pd.NaT
            CON.warn("상폐목록 없음 — 생존자편향 제거가 불완전합니다(스냅샷 유니온으로 보강)")
        sec["name"] = sec["name"].fillna("")
        sec["market"] = sec.get("market", pd.Series("", index=sec.index)).fillna("")
        n_del = int(sec["delist_date"].notna().sum())
        CON.say(f"종목마스터 {len(sec):,}개 (상폐이력 {n_del:,}건 포함)")
        if n_del < 200:
            CON.warn("상폐 이력이 200건 미만 — 상폐 데이터 소스를 확인하세요(생존자편향 위험)")
        DEPOT.table_save("scg_security_master", sec, scope="공용", domain="universe",
                         source="FDR+KIND")
    # ★ 이전상장(예: 코스닥→코스피)은 '상폐'가 아니다. 상폐일이 (재)상장일 근처이거나
    #   그보다 앞서면 이전으로 간주하고 상폐 기록을 무효화한다 — 이걸 안 하면
    #   멀쩡히 거래되는 대형주가 이전일 이후 유니버스에서 조용히 사라진다.
    xfer = (sec["delist_date"].notna() & sec["list_date"].notna()
            & (sec["delist_date"] <= sec["list_date"] + pd.Timedelta(days=30)))
    if xfer.any():
        CON.say(f"이전상장으로 판정된 상폐기록 {int(xfer.sum()):,}건 무효화(시장이동≠상폐)")
        sec.loc[xfer, "delist_date"] = pd.NaT
    sec = sec[[_is_common_stock(c, n) for c, n in zip(sec["code"], sec["name"])]]
    sec = sec.drop_duplicates("code").reset_index(drop=True)

    # ── 월별 시총 스냅샷 (KRX 마켓플레이스 → pykrx 폴백) — 비교전략(하위1000)의 기준 ──────
    mcap = DEPOT.table_load("scg_mcap_monthly",
                            foreign_patterns=["mktcap", "marketcap", "mcap_month"],
                            need_cols=["month", "code", "mktcap", "shares"])
    have_m = set()
    if mcap is not None and len(mcap):
        mcap["month"] = ts_col(mcap["month"])
        have_m = set(mcap["month"].unique())
    todo = [m for m in months if m not in have_m]
    if todo and RUN_MODE != "CACHED":
        CON.say(f"시총 스냅샷 수집: {len(todo)}개월 (캐시 {len(have_m)}개월 재사용)")
        krx_ok = KRXS.login() if KRXS.state == "미시도" else (KRXS.state == "로그인성공")
        frames = [] if mcap is None else [mcap]
        for m in todo:
            if DEADLINE.over("시총 스냅샷"):
                break
            snap = None
            day = m
            if krx_ok:
                for back in range(6):                       # 월말 휴장 대비 최근 거래일 탐색
                    snap = KRXS.mktcap_snapshot(day - pd.Timedelta(days=back))
                    if snap is not None and len(snap) > 100:
                        break
            if (snap is None or not len(snap)) and pykrx_stock is not None:
                d8 = None
                try:
                    d8 = _pykrx_call(pykrx_stock.get_nearest_business_day_in_a_week,
                                     f"{m:%Y%m%d}")
                except Exception:
                    d8 = f"{m:%Y%m%d}"
                cap = _pykrx_call(pykrx_stock.get_market_cap_by_ticker, d8 or f"{m:%Y%m%d}",
                                  market="ALL")
                if cap is not None and len(cap):
                    cap = cap.reset_index()
                    lc = {str(c): c for c in cap.columns}
                    snap = pd.DataFrame({
                        "code": cap[lc.get("티커", list(cap.columns)[0])].map(code6),
                        "name": "", "market": "",
                        "close": pd.to_numeric(cap[lc["종가"]], errors="coerce")
                        if "종가" in lc else np.nan,
                        "mktcap": pd.to_numeric(cap[lc["시가총액"]], errors="coerce")
                        if "시가총액" in lc else np.nan,
                        "shares": pd.to_numeric(cap[lc["상장주식수"]], errors="coerce")
                        if "상장주식수" in lc else np.nan})
            if snap is None or not len(snap):
                CON.warn(f"{m:%Y-%m} 시총 스냅샷 실패 — 해당 월은 직전 스냅샷으로 대체됩니다")
                continue
            snap = snap.dropna(subset=["code"])
            snap.insert(0, "month", m)
            frames.append(snap[["month", "code", "mktcap", "shares", "close"]])
            FLOW.io("입", "HTTP", f"시총스냅샷:{m:%Y-%m}", snap,
                    src="KRX마켓플레이스" if krx_ok else "pykrx")
        mcap = pd.concat(frames, ignore_index=True) if frames else mcap
        if mcap is not None and len(mcap):
            mcap = mcap.drop_duplicates(["month", "code"], keep="last")
            DEPOT.table_save("scg_mcap_monthly", mcap, scope="공용", domain="universe",
                             source="krx_marketplace+pykrx")
    if mcap is None:
        mcap = pd.DataFrame(columns=["month", "code", "mktcap", "shares", "close"])
    mcap["month"] = ts_col(mcap["month"])
    return {"sec": sec, "mcap": mcap}


UNIVERSE_SEASONING_DAYS = 0   # 명세 §31(추가 하드게이트 금지) 준수: 기본 0.
                              # IPO 직후 왜곡을 배제한 별도 실험을 원할 때만 250 등으로.


def universe_at(T: pd.Timestamp, sec: pd.DataFrame, mcap: pd.DataFrame) -> pd.Index:
    """시점 T의 PIT 유니버스: T에 상장돼 있고 아직 상폐 전인 보통주.
    시총 스냅샷이 있는 달은 그 달 스냅샷과 유니온(스냅샷 결손이 종목을 죽이지 않게)."""
    ld = sec["list_date"]
    dd = sec["delist_date"]
    ok = ((ld.isna() | (ld + pd.Timedelta(days=UNIVERSE_SEASONING_DAYS) <= T))
          & (dd.isna() | (dd > T)))
    base = set(sec.loc[ok, "code"])
    snap = mcap[mcap["month"] == (T + pd.offsets.MonthEnd(0))]
    if len(snap):
        # 스냅샷과 교차 검증: 스냅샷에 있는데 base 에 없으면(마스터 누락) 추가하되 상폐자는 제외
        extra = set(snap["code"]) - base
        dmap = sec.set_index("code")["delist_date"].to_dict()
        for c in extra:
            d = dmap.get(c, pd.NaT)
            if (pd.isna(d) or d > T) and _is_common_stock(c, ""):
                base.add(c)
    return pd.Index(sorted(base))


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [S4-c] 가격 수집 — pykrx→FDR→네이버→야후 4중 폴백, 종목 단위 단일소스 원칙                 ║
# ║        (소스를 섞어 이어붙이면 수정주가 기준이 달라 가짜 수익률이 생긴다)                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _px_pykrx(code: str, s: str, e: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    d = _pykrx_call(pykrx_stock.get_market_ohlcv, s.replace("-", ""), e.replace("-", ""),
                    code, adjusted=True)
    if d is None or not len(d):
        return None
    d = d.reset_index()
    lc = {str(c): c for c in d.columns}
    dtc = next((lc[c] for c in lc if "날짜" in c or "date" in c.lower()), d.columns[0])
    out = pd.DataFrame({"date": ts_col(d[dtc]),
                        "close": pd.to_numeric(d[lc.get("종가", "종가")], errors="coerce")
                        if "종가" in lc else np.nan,
                        "volume": pd.to_numeric(d.get(lc.get("거래량"), np.nan), errors="coerce")})
    return out.dropna(subset=["date", "close"])


def _px_fdr(code: str, s: str, e: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        d = fdr.DataReader(code, s, e)
    except Exception:
        return None
    if d is None or not len(d):
        return None
    d = d.reset_index()
    lc = {str(c).lower(): c for c in d.columns}
    return pd.DataFrame({"date": ts_col(d[lc.get("date", d.columns[0])]),
                         "close": pd.to_numeric(d[lc["close"]], errors="coerce"),
                         "volume": pd.to_numeric(d.get(lc.get("volume"), np.nan),
                                                 errors="coerce")}).dropna(subset=["date", "close"])


def _px_naver(code: str, s: str, e: str) -> Optional[pd.DataFrame]:
    n_days = max(30, (ts(e) - ts(s)).days + 10)
    t = fetch("https://fchart.stock.naver.com/siseJson.naver", source="naver",
              params={"symbol": code, "requestType": "1", "count": str(n_days),
                      "startTime": s.replace("-", ""), "endTime": e.replace("-", ""),
                      "timeframe": "day"})
    if not t:
        return None
    rows = re.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*(\d+)', t)
    if not rows:
        return None
    out = pd.DataFrame(rows, columns=["d", "o", "h", "l", "c", "v"])
    return pd.DataFrame({"date": ts_col(out["d"]),
                         "close": pd.to_numeric(out["c"], errors="coerce"),
                         "volume": pd.to_numeric(out["v"], errors="coerce")}
                        ).dropna(subset=["date", "close"])


def _px_yahoo(code: str, s: str, e: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            THROTTLE.wait("yahoo")
            d = yf.download(code + suf, start=s, end=e, auto_adjust=True,
                            progress=False, threads=False)
        except Exception:
            d = None
        if d is not None and len(d):
            d = d.reset_index()
            cols = {str(c[0]) if isinstance(c, tuple) else str(c): c for c in d.columns}
            return pd.DataFrame({"date": ts_col(d[cols.get("Date", d.columns[0])]),
                                 "close": pd.to_numeric(d[cols["Close"]].squeeze(),
                                                        errors="coerce"),
                                 "volume": pd.to_numeric(d[cols.get("Volume")].squeeze(),
                                                         errors="coerce")
                                 if "Volume" in cols else np.nan}
                                ).dropna(subset=["date", "close"])
    return None


_PX_CHAIN = [("pykrx", _px_pykrx), ("fdr", _px_fdr), ("naver", _px_naver), ("yahoo", _px_yahoo)]


def collect_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """일별 수정종가 패널 code·date·close·volume·src. 캐시 우선 + 부족 종목만 신규."""
    cached = DEPOT.table_load("scg_px_daily",
                              foreign_patterns=["ohlcv_daily", "px_daily", "price_daily"],
                              need_cols=["code", "date", "close"])
    frames: List[pd.DataFrame] = []
    have: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached["code"] = cached["code"].map(code6)
        cached["date"] = ts_col(cached["date"])
        cached = cached.dropna(subset=["code", "date", "close"])
        if "src" not in cached.columns:
            cached["src"] = "cache"
        cached = cached[cached["date"] >= ts(start) - pd.Timedelta(days=7)]
        frames.append(cached[["code", "date", "close", "volume", "src"]]
                      if "volume" in cached.columns else
                      cached.assign(volume=np.nan)[["code", "date", "close", "volume", "src"]])
        g = cached.groupby("code")["date"]
        have = {c: (mn, mx) for c, mn, mx in zip(g.min().index, g.min(), g.max())}
        CON.say(f"가격 캐시 재사용: {cached['code'].nunique():,}종목 {len(cached):,}행")
    end_t = ts(end)
    todo = []
    for c in codes:
        rng = have.get(c)
        if rng is None:
            todo.append((c, start, end))
        elif rng[1] < end_t - pd.Timedelta(days=9) or rng[0] > ts(start) + pd.Timedelta(days=35):
            # ★ 꼬리만 이어붙이면 (a) 소스가 섞이고 (b) 그 사이 액면분할/배당으로
            #   수정주가 기준이 달라져 이음새에 가짜 수익률이 생긴다. 갱신이 필요한
            #   종목은 전 구간을 한 소스에서 다시 받아 통째로 교체한다(종목당 1콜).
            #   앞머리가 비어 있는 캐시(뒤 구간만 있는 외부 캐시)도 같은 경로로 채운다.
            todo.append((c, start, end))
    if RUN_MODE == "CACHED":
        todo = []
    if todo:
        CON.say(f"가격 신규 수집 {len(todo):,}종목/구간 (폴백사슬 pykrx→FDR→네이버→야후)")

        def _one(job):
            if DEADLINE.over("가격 수집"):
                return None
            c, s, e = job
            for src, fn in _PX_CHAIN:
                try:
                    d = fn(c, s, e)
                except Exception:      # 한 소스의 어댑터 예외가 나머지 폴백을 막으면 안 된다
                    d = None
                if d is not None and len(d) >= 2:
                    d.insert(0, "code", c)
                    d["src"] = src
                    return d
            return None

        got = pmap(_one, todo, label="가격수집")
        got = [g for g in got if g is not None]
        if got:
            frames.append(pd.concat(got, ignore_index=True))
        CON.say(f"가격 신규 수집 완료: {len(got):,}/{len(todo):,}종목")
    if not frames:
        raise HaltRun("가격 데이터가 전혀 없습니다 — 네트워크/캐시를 확인하세요")
    px = pd.concat(frames, ignore_index=True)
    px = (px.dropna(subset=["code", "date", "close"])
            .sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last").reset_index(drop=True))
    px = px[px["close"] > 0]
    if todo:
        DEPOT.table_save("scg_px_daily", px, scope="공용", domain="price",
                         source="pykrx+fdr+naver+yahoo")
    return shrink(px)


def _resample_me(s: pd.Series) -> pd.Series:
    try:
        return s.resample("ME").last()
    except ValueError:                     # pandas < 2.2
        return s.resample("M").last()


def collect_benchmark(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    for nm, sym, ysym in (("KOSPI", "KS11", "^KS11"), ("KOSDAQ", "KQ11", "^KQ11")):
        ser = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, months[0] - pd.offsets.MonthEnd(2), months[-1])
                if d is not None and len(d):
                    d = d.reset_index()
                    lc = {str(c).lower(): c for c in d.columns}
                    dd = pd.DataFrame({"date": ts_col(d[lc.get("date", d.columns[0])]),
                                       "close": pd.to_numeric(d[lc["close"]], errors="coerce")})
                    m = _resample_me(dd.set_index("date")["close"])
                    ser = m.pct_change().reindex(months)
            except Exception:
                ser = None
        if ser is None and yf is not None:
            try:
                d = yf.download(ysym, start=str(months[0].date() - _dt.timedelta(days=70)),
                                end=str(months[-1].date()), auto_adjust=True, progress=False)
                if d is not None and len(d):
                    m = _resample_me(d["Close"].squeeze())
                    m.index = pd.DatetimeIndex(m.index).normalize()
                    ser = m.pct_change().reindex(months)
            except Exception:
                ser = None
        if ser is not None:
            out[nm] = ser
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
    rep = rep[(rep["date"] >= ts(start) - pd.Timedelta(days=400))
              & (rep["date"] <= ts(end) + pd.Timedelta(days=7))]
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


def collect_actual_eps(sec: pd.DataFrame, mcap: pd.DataFrame,
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
        shares_map, first_shares = {}, {}
        if len(mcap) and "shares" in mcap.columns:
            for (mth, c), sh in (mcap.sort_values("month")
                                 .set_index(["month", "code"])["shares"].items()):
                shares_map[(mth.year, c)] = sh
                first_shares.setdefault(c, sh)   # 창 이전 회계연도의 폴백(최초 스냅샷)
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


def tp_actuals_from_prices(fc: pd.DataFrame, px_close: pd.DataFrame,
                           cal: "TradingCal") -> pd.DataFrame:
    """TP12M 정확도 사건용 실측치: 각 보고서의 '12개월 뒤 실제 주가'.
    (EPS 실적발표일에 해당하는 것이 '만기일' — 만기가 지난 사건만 정확도에 쓰인다)"""
    if not len(fc):
        return pd.DataFrame(columns=["report_id", "matured_at", "actual_price"])
    tp = fc[fc["forecast_metric"] == "TP12M"]
    if not len(tp):
        return pd.DataFrame(columns=["report_id", "matured_at", "actual_price"])
    px = px_close
    out = []
    for sid, g in tp.groupby("stock_id", observed=True):
        s = px.get(sid)
        if s is None:
            continue
        dates, vals = s
        for rid, rd in zip(g["report_id"], g["report_date"]):
            mat = cal.shift(rd, 252)
            if mat is None:
                continue
            i = int(np.searchsorted(dates, np.datetime64(mat), side="right")) - 1
            if i < 0 or (mat - pd.Timestamp(dates[i])).days > 15:
                continue
            out.append((rid, mat, float(vals[i])))
    return pd.DataFrame(out, columns=["report_id", "matured_at", "actual_price"])


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
    exp = fc["report_date"] + pd.Timedelta(days=int(cfg.MAX_FORECAST_AGE_DAYS) + 1)
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
def build_price_book(px: pd.DataFrame) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """code → (일자배열, 종가배열). 이후 모든 조회는 이 북에서 O(log n)."""
    book = {}
    for c, g in px.groupby("code", observed=True, sort=False):
        g = g.sort_values("date")
        book[str(c)] = (g["date"].to_numpy("datetime64[ns]"),
                        g["close"].to_numpy(float))
    return book


def _px_asof(book, code: str, day, max_gap_days: int = 12) -> float:
    s = book.get(str(code))
    if s is None:
        return np.nan
    d, v = s
    i = int(np.searchsorted(d, np.datetime64(pd.Timestamp(day)), side="right")) - 1
    if i < 0:
        return np.nan
    if (pd.Timestamp(day) - pd.Timestamp(d[i])).days > max_gap_days:
        return np.nan
    return float(v[i])


def build_month_panel(book: Dict, sec: pd.DataFrame, months, cal: "TradingCal"
                      ) -> pd.DataFrame:
    """월별 code 패널: close · fwd_1m(다음달) · fwd_20/60/120td(거래일 지평, IC용).
    상장폐지 처리(생존자편향 금지): 다음달 내 상폐 & 가격 없음 → -100%. 누락 처리 금지."""
    delist = sec.set_index("code")["delist_date"].to_dict()
    months = list(pd.DatetimeIndex(months))
    rows = []
    for code, (d, v) in book.items():
        dd = delist.get(code, pd.NaT)
        last_px_day = pd.Timestamp(d[-1])
        for i, m in enumerate(months):
            c0 = _px_asof(book, code, m)
            if not np.isfinite(c0):
                continue
            # ★ 정지→상폐 경로: 마지막 체결 후 가격이 다시는 나오지 않고 상폐가 예정돼
            #   있으면, '마지막 체결이 속한 달'에 전손(-100%)을 기록한다. 이 손실을
            #   어느 달에도 안 적으면 하위분위 수익률이 조용히 과대평가된다(생존자편향).
            #   단, 상폐일이 '이력 끝 근처'일 때만 — 수집이 중간에 잘린 이력(시간예산
            #   부분수집 등)에 가짜 전손을 찍으면 중간결과 모드가 왜곡된다.
            dying = (pd.notna(dd) and dd > m
                     and (last_px_day - pd.Timestamp(m)).days <= 45
                     and dd <= last_px_day + pd.Timedelta(days=45))
            nxt = months[i + 1] if i + 1 < len(months) else None
            fwd1 = np.nan
            if nxt is not None:
                c1 = _px_asof(book, code, nxt)
                if np.isfinite(c1):
                    fwd1 = c1 / c0 - 1.0
                elif dying or (pd.notna(dd) and m < dd <= nxt + pd.Timedelta(days=5)):
                    fwd1 = -1.0                    # 정리매매 최종가 없으면 전손 처리(보수적)
            r = {"code": code, "month": m, "close": c0, "fwd_1m": fwd1}
            for h in (20, 60, 120):
                th = cal.shift(m, h)
                ch = _px_asof(book, code, th) if th is not None else np.nan
                if np.isfinite(ch):
                    r[f"fwd_{h}td"] = ch / c0 - 1.0
                else:
                    # IC 지평에도 같은 규칙 — 생존자만으로 IC 를 재지 않는다
                    r[f"fwd_{h}td"] = -1.0 if dying else np.nan
            rows.append(r)
    P = pd.DataFrame(rows)
    CON.say(f"월간 수익률 패널 {len(P):,}행 · 종목 {P['code'].nunique():,} · "
            f"메모리 {mem_mb(P):.0f}MB")
    return shrink(P)


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
    """4전략을 동일 유니버스·동일 시점·동일 분위수에서 나란히(§30·§37)."""
    common = sig.merge(panel[["code", "month"]],
                       left_on=["stock_id", "signal_date"],
                       right_on=["code", "month"], how="inner")
    xs = common.groupby("signal_date")["stock_id"].size()
    nq_common = 10 if (len(xs) and xs.median() >= 60) else 5
    out = {}
    for s in STRATS:
        out[s] = bucket_backtest(sig, panel, s, nq_override=nq_common)
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


def R_cost_stress(sig: pd.DataFrame, panel: pd.DataFrame):
    rows = []
    for bps in (0.0, 25.0, 50.0):
        bt = bucket_backtest(sig, panel, "SCG_LS", cost_bps=bps)
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
            m0 = ts("2020-01-15") + pd.Timedelta(days=60 * k)
            # 추종 지연 10일(≈7거래일) — 20거래일 관측창 '안'이어야 리더십이 관측된다.
            # 리더의 다음 수정(+60일)은 추종자 창 밖이라 역방향 오염이 없다.
            rows += [_fc_row("S", "leader", f"{m0:%Y-%m-%d}", "2021FY", 100.0 + 10 * k),
                     _fc_row("S", "follower", f"{(m0 + pd.Timedelta(days=10)):%Y-%m-%d}",
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
    _ct("C-보존", "기존 캐시 쓰기 차단", c_depot)
    _ct("C-결정", "결정성(시드)", c_det)
    bad = [c for c in CONTRACTS if not c["ok"]]
    CON.grid([[c["id"], c["name"], "통과" if c["ok"] else "실패", c["msg"]]
              for c in CONTRACTS], ["ID", "계약", "판정", "근거"], ["l", "l", "l", "l"],
             title="자체계약 검증 결과")
    if bad and strict:
        raise RuleBreak(f"자체계약 {len(bad)}건 실패 — 실데이터로 진행하지 않습니다: "
                        + ", ".join(c["id"] for c in bad))
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
                        days=72 * q + int(rng.integers(0, 10)) + lead_shift)
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
    px_rows = []
    for sid in stocks:
        p = 10000.0 * float(rng_px.uniform(0.5, 3))
        arr = []
        for d in days:
            mis = mis_map.get((sid, d.year), 0.0)
            pull = 0.0022 * mis                    # 갭과 같은 앵커 → 신호가 수익을 예측
            p *= math.exp(rng_px.normal(0.0002, 0.010) + pull)
            arr.append(p)
        px_rows.append(pd.DataFrame({"code": sid, "date": days, "close": arr,
                                     "volume": 1e5, "src": "synth"}))
    px = pd.concat(px_rows, ignore_index=True)
    sec = pd.DataFrame({"code": stocks, "name": [f"합성{i}" for i in range(n_stocks)],
                        "market": "KOSPI", "list_date": ts("2010-01-01"),
                        "delist_date": pd.NaT})
    # 일부 종목 중도상폐 심기(생존자편향 경로 검증)
    sec.loc[sec.index[-3:], "delist_date"] = ts("2022-06-15")
    mcap_rows = []
    months = month_ends(days[0], days[-1])
    for m in months:
        for i, sid in enumerate(stocks):
            mcap_rows.append(dict(month=m, code=sid, mktcap=1e10 * (i + 1),
                                  shares=1e6, close=np.nan))
    return dict(fc=fc, actuals=actuals, px=px, sec=sec,
                mcap=pd.DataFrame(mcap_rows), cal=cal, months=months)


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
    sig = sig.rename(columns={"stock_id": "stock_id"})
    book = build_price_book(S["px"])
    panel = build_month_panel(book, S["sec"], months, S["cal"])
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


def coverage_table(fc: pd.DataFrame, R: pd.DataFrame, px: pd.DataFrame,
                   actuals: pd.DataFrame):
    rows = [["보고서 원장", f"{len(R):,}건",
             f"{R['date'].min():%Y-%m}~{R['date'].max():%Y-%m}" if len(R) else "-"],
            ["예측 테이블", f"{len(fc):,}행",
             f"{fc['report_date'].min():%Y-%m}~{fc['report_date'].max():%Y-%m}"
             if len(fc) else "-"],
            ["가격 패널", f"{px['code'].nunique():,}종목",
             f"{px['date'].min():%Y-%m}~{px['date'].max():%Y-%m}" if len(px) else "-"],
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
              ["선택 패키지", ", ".join(k for k, v in HAVE.items() if v) or "없음"],
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

    with FLOW.part("S4a", "PIT 유니버스 + 월별 시총", budget_s=3600):
        U = collect_universe(months)
        sec, mcap = U["sec"], U["mcap"]
        FLOW.io("출", "메모리", "종목마스터", sec)

    with FLOW.part("S4b", "가격 수집(수정주가·상폐 포함)", budget_s=3600 * 2):
        codes = sec["code"].tolist()
        px = collect_prices(codes, (ts(BACKTEST_START) - pd.DateOffset(months=15)
                                    ).strftime("%Y-%m-%d"), BACKTEST_END)
        cal = TradingCal(px["date"].unique())
        bench = collect_benchmark(months)

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
        actuals = collect_actual_eps(sec, mcap, BACKTEST_START, BACKTEST_END)

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
        fc = validate_forecasts(fc_all, asof=ts(BACKTEST_END) + pd.Timedelta(days=7))
        fcv = with_validity(fc, cfg)
        book = build_price_book(px)
        tp_act = tp_actuals_from_prices(fc, book, cal) if metric == "TP12M" else \
            pd.DataFrame(columns=["report_id", "matured_at", "actual_price"])

    with FLOW.part("S7", "SCG 엔진(사건→PIT점수→스마트컨센서스→신호)", budget_s=3600):
        sig_months = [m for m in months if m >= fc["report_date"].min()]
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
        panel = build_month_panel(book, sec, sig_months, cal)
        uni_members = []
        for T in sig_months:
            uni_members.append(pd.DataFrame({"signal_date": T,
                                             "stock_id": universe_at(T, sec, mcap)}))
        uni_df = pd.concat(uni_members, ignore_index=True)
        uni_df["in_uni"] = True
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
        small_members = []
        if len(mcap):
            mc = mcap.dropna(subset=["mktcap"]).sort_values("month")
            for T in sig_months:
                snap = mc[mc["month"] <= T]
                if not len(snap):
                    continue
                last_m = snap["month"].max()
                s = snap[snap["month"] == last_m].nsmallest(COMPARE_BOTTOM_N, "mktcap")
                small_members.append(pd.DataFrame({"signal_date": T,
                                                   "stock_id": s["code"].map(code6)}))
        if small_members:
            sm = pd.concat(small_members, ignore_index=True)
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
            suites_small = {}
            CON.warn("시총 스냅샷이 없어 비교전략을 건너뜁니다 — KRX 로그인/pykrx 를 확인하세요")

    with FLOW.part("S10", "강건성 검사(전체 유니버스)", budget_s=3600 * 2, critical=False):
        R_sensitivity(ENG, panel)
        R_subperiod(suites_full)
        R_concentration(suites_full)
        R_placebo(sig_full, panel)
        R_lag(sig_full, panel)
        R_cost_stress(sig_full, panel)
        robustness_verdict()

    with FLOW.part("S11", "해석표 · 저장(공용/전용 인덱스) · 다운로드", budget_s=900,
                   critical=False):
        interpretation_tables(metric)
        coverage_table(fc, R, px, actuals)
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
