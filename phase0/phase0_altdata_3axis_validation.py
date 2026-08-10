# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 0 — 대체데이터 3축 수집 가능성 검증  v1.0                                              ║
# ║                                                                                              ║
# ║  이 코드가 하는 일: 시가총액 하위 1,000종목 유니버스에 대해 아래 3축이 기계적으로 수집         ║
# ║  가능한지, 커버리지와 과거 깊이가 얼마인지를 '숫자로' 확인하고 판정표를 만든다.                ║
# ║      축 A — DART 임원현황            (겸직 네트워크의 원재료)                                  ║
# ║      축 B — Google Patents BigQuery  (기업 단위 특허 지표의 원재료)                            ║
# ║      축 C — 국민연금 사업장 가입자   (월간 고용 flow 의 원재료)                                ║
# ║                                                                                              ║
# ║  이 코드가 하지 않는 일 (계약으로 강제한다):                                                   ║
# ║      팩터 계산 · 시그널 생성 · 포트폴리오 구성 · 수익률 산출 — 전면 금지                       ║
# ║      알파 존재 여부에 대한 주장 · 3축의 결합/교차 분석 · 실패 축의 즉흥 우회                   ║
# ║                                                                                              ║
# ║  실행 방법                                                                                     ║
# ║      JupyterLab: 이 셀 하나를 그대로 실행 (셀을 쪼개지 말 것)                                  ║
# ║      터미널   : python phase0_altdata_3axis_validation.py                                     ║
# ║                                                                                              ║
# ║  산출물 (<PROJECT_ROOT>/cache/reports/)                                                       ║
# ║      phase0_verdict.json / phase0_verdict.csv                                                 ║
# ║      manual_check_A_coexec_links.csv (200건) / manual_check_C_workplace_match.csv (100건)      ║
# ║      phase0_summary.md / phase0_run_log.txt                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

from __future__ import annotations

import ast
import csv
import io
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import zipfile
import datetime as _dt
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ═════════════════════════════════════════════════════════════════════════════════════════════
#  0. 인증정보 — 여기만 채우면 된다
#     환경변수가 있으면 환경변수가 우선한다. 없으면 아래 문자열에 직접 붙여넣어도 된다.
# ═════════════════════════════════════════════════════════════════════════════════════════════

# ── OpenDART API 키 (축 A 필수 / 축 C 의 사업자등록번호 대조에 보조 사용) ─────────────────────
#   발급처 : https://opendart.fss.or.kr/
#   절차   : ① 우측 상단 [인증키 신청/관리] → [인증키 신청]
#            ② 이름·이메일·계정 입력 후 신청 → 이메일 인증 링크 클릭
#            ③ 인증 즉시 40자리 API Key 발급 (승인 대기 없음, 당일 사용 가능)
#   한도   : 일 20,000건. 초과 시 응답 status=020 으로 조용히 실패하므로 예산을 미리 계산한다.
DART_API_KEY = os.environ.get("DART_API_KEY", "") or ""

# ── 공공데이터포털 API 키 (축 C 필수) ─────────────────────────────────────────────────────────
#   발급처 : https://www.data.go.kr/
#   절차   : ① 회원가입·로그인
#            ② 검색창에 "국민연금 가입 사업장 내역" → 오픈API 탭의 해당 항목 진입
#            ③ [활용신청] 클릭 → 활용목적 기재 → 신청
#               · 자동승인 데이터셋이면 즉시 발급
#               · 담당자 승인 데이터셋이면 1~2 영업일 소요 (마이페이지에서 상태 확인)
#            ④ [마이페이지] → [오픈API] → [인증키 발급현황] 에서 키 복사
#   ★ 반드시 "일반 인증키(Decoding)" 를 복사할 것. Encoding 키(%2B, %3D 포함)를 그대로 넣으면
#     requests 가 다시 인코딩해 이중 인코딩이 되고 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다.
#     (아래 코드는 이 실수를 자동 감지해 교정하고 경고를 남긴다.)
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY", "") or ""

# ── Google Cloud BigQuery (축 B 필수) ─────────────────────────────────────────────────────────
#   전제   : GCP 프로젝트 + 결제 계정 연결이 되어 있어야 한다 (월 1TB 쿼리 무료 티어).
#            결제 정보가 없으면 patents-public-data 조회 자체가 거부된다 → 축 B 는 BLOCKED_PREREQ.
#   절차   : ① https://console.cloud.google.com/ 에서 프로젝트 생성
#            ② [결제] 메뉴에서 결제 계정 연결 (무료 티어 내에서는 청구되지 않음)
#            ③ [API 및 서비스] → "BigQuery API" 사용 설정
#            ④ [IAM 및 관리자] → [서비스 계정] → 계정 생성 →
#               역할 "BigQuery 작업 관리자(BigQuery Job User)" + "BigQuery 데이터 편집자" 부여
#            ⑤ 키 → [키 추가] → JSON → 내려받은 파일 경로를
#               GOOGLE_APPLICATION_CREDENTIALS 환경변수에 지정
#            ⑥ 로컬 개발이라면 `gcloud auth application-default login` 으로도 대체 가능
#   비용   : 이 코드는 모든 쿼리를 dry_run 으로 먼저 재고, 100GB 초과 쿼리는 실행하지 않는다.
BQ_PROJECT_ID = (os.environ.get("BQ_PROJECT_ID", "")
                 or os.environ.get("GOOGLE_CLOUD_PROJECT", "") or "")
# 물질화(중간 테이블) 를 저장할 데이터셋. 없으면 코드가 생성을 시도한다.
BQ_DEST_DATASET = os.environ.get("BQ_DEST_DATASET", "") or "phase0_altdata"
# patents-public-data 는 US 멀티리전에 있다. 데이터셋 위치가 다르면 조인이 실패한다.
BQ_LOCATION = os.environ.get("BQ_LOCATION", "") or "US"

# ═════════════════════════════════════════════════════════════════════════════════════════════
#  1. 실행 설정
# ═════════════════════════════════════════════════════════════════════════════════════════════

T_NOW = "2026-06-30"          # 최근 커버리지 기준일
T_PAST = "2021-06-30"         # 백필 깊이 기준일
AS_OF_LIST = [T_NOW, T_PAST]

UNIVERSE_SIZE = 1000          # 시가총액 하위 N 종목
CANARY_N = 10                 # 축별 카나리 종목 수
MANUAL_SAMPLE_A = 200         # 축 A 수기검증 샘플 수
MANUAL_SAMPLE_C = 100         # 축 C 수기검증 샘플 수
RANDOM_SEED = 20260630

N_WORKERS = 4                 # ThreadPoolExecutor 최대 워커 (명령서 §3.6: 4 이하)
DELAY_MIN, DELAY_MAX = 0.3, 1.0     # 요청 간 랜덤 지연(초)
CB_FAIL_STREAK = 10           # 서킷 브레이커: 연속 실패 임계
CB_COOLDOWN_SEC = 60          # 서킷 브레이커: 대기 시간
CB_MAX_TRIPS = 3              # 서킷 브레이커: 이 횟수만큼 작동하면 해당 축 중단

DART_DAILY_LIMIT = 19_000     # 공식 20,000 대비 여유
BQ_MAX_SCAN_BYTES = 100 * (1024 ** 3)      # 단일 쿼리 스캔 상한 100GB (명령서 §4.3)

TIME_BUDGET_SEC = 4 * 3600    # 전체 실행 예산 (명령서 §8)
PATENT_LOOKBACK_YEARS = 5     # 축 B 관측 창. 예산 초과 시 3년으로 축소(기록 남김)

ALLOW_PIP_INSTALL = True      # 누락 패키지 자동 설치 허용
FUZZY_THRESHOLD = 0.90        # 퍼지 매칭 임계. ★ 매칭률을 부풀리려고 낮추지 말 것 (§4.5.4)

# 특허 공개 지연: 출원 후 18개월. filing_date 와 publication_date 를 혼용하면 룩어헤드다. (§4.7)
PATENT_PUBLICATION_LAG_MONTHS = 18

# ═════════════════════════════════════════════════════════════════════════════════════════════
#  2. 계약 (Contracts) — 선언만 하지 않는다. 자기 소스를 AST 로 읽어 위반을 실행 전에 잡는다.
# ═════════════════════════════════════════════════════════════════════════════════════════════

CONTRACTS = {
    "P0_NO_STRATEGY":     "수익률·시그널·팩터 관련 연산을 일절 수행하지 않는다",
    "P0_PIT_UNIVERSE":    "유니버스는 각 기준일 시점의 상장 종목. 현재 종목을 과거에 소급하지 않는다",
    "P0_CANARY_FIRST":    "각 축마다 10종목 카나리를 통과하기 전에는 전체 실행을 시작하지 않는다",
    "P0_INDEPENDENT_AXES": "축 A/B/C 는 서로의 결과에 의존하지 않는다",
    "P0_FAIL_LOUD":       "데이터가 없으면 '없음'으로 기록한다. 추정·보간·대체값 채우기 금지",
    "P0_NO_HARDCODED_PATH": "특정 환경 전용 경로 금지. 런타임 자동 감지",
    "P0_RESUMABLE":       "중단 후 재실행 시 이미 수집된 항목은 건너뛴다",
}

# ── P0_NO_STRATEGY: 아래 단어가 '식별자 조각'으로 등장하면 전략 코드로 간주하고 즉시 중단 ──────
#    (문자열·주석은 검사 대상이 아니다. 정의된 이름·인자·대입 대상만 본다.)
_BANNED_NAME_SEGMENTS = {
    "alpha", "sharpe", "sortino", "calmar", "pnl", "cagr", "mdd", "drawdown",
    "backtest", "portfolio", "rebalance", "turnover", "signal", "signals",
    "factor", "factors", "zscore", "ic", "rankic", "ret", "rets", "retn",
    "returns", "excess", "benchmark", "longshort", "quantile", "decile",
    "weight", "weights", "position", "positions", "holding", "holdings",
    "strategy", "strat", "pnls", "sortino", "beta", "hedge",
}
# ── P0_FAIL_LOUD: 결측을 조용히 메우는 호출 금지 ─────────────────────────────────────────────
_BANNED_ATTR_CALLS = {"fillna", "interpolate", "ffill", "bfill", "backfill", "pad"}
# ── §2.3 알려진 함정: 영구 실패하는 호출은 아예 코드에 존재해서는 안 된다 ──────────────────────
_FORBIDDEN_CALLS = {"get_index_portfolio_deposit_file"}
# ── P0_NO_HARDCODED_PATH: 아래로 시작하는 절대경로 리터럴 금지 ────────────────────────────────
#    ★ 금지 리터럴을 소스에 그대로 적으면 이 검사가 자기 자신을 잡는다. 런타임 조립으로 만든다.
_BANNED_PATH_PREFIXES = tuple(
    "/" + s for s in ("content", "Users", "home", "mnt", "gdrive", "workspace", "data", "media")
) + tuple(c + ":" + chr(92) for c in ("C", "D", "E")) \
  + tuple("~" + "/" + s for s in ("Desktop", "Downloads", "Documents"))
# ── P0_INDEPENDENT_AXES: 축 함수 본문에서 참조하면 안 되는 전역 ────────────────────────────────
_AXIS_FORBIDDEN_GLOBALS = {"VERDICTS", "AXIS_OUTPUT", "AXIS_A_OUT", "AXIS_B_OUT", "AXIS_C_OUT"}
_AXIS_ENTRYPOINTS = ("run_axis_a", "run_axis_b", "run_axis_c")
# ── §4.3 전 컬럼 조회 금지. 금지 대상 문자열을 메시지에 그대로 쓰면 검사가 자기 메시지를
#    잡으므로, 사람이 읽을 라벨은 런타임에 조립한다.
_SQL_STAR = "SELECT" + " " + chr(42)


class ContractViolation(RuntimeError):
    """계약 위반. 우회 파라미터를 의도적으로 만들지 않았다."""


def _read_self_source() -> Tuple[Optional[str], str]:
    """자기 소스를 확보한다. 파일 실행이면 __file__, 노트북이면 현재 셀 원문."""
    try:
        with open(__file__, encoding="utf-8") as fh:       # noqa: F821 - 노트북에선 NameError
            return fh.read(), "__file__"
    except NameError:
        pass
    except OSError:
        pass
    try:
        cells = get_ipython().user_ns.get("In")            # noqa: F821 - IPython 전용
        if cells:
            return cells[-1], "ipython_cell"
    except Exception:
        pass
    return None, "unavailable"


def _iter_defined_names(tree: ast.AST) -> Iterable[Tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node.lineno
            for a in (list(node.args.posonlyargs) + list(node.args.args)
                      + list(node.args.kwonlyargs)):
                yield a.arg, node.lineno
        elif isinstance(node, ast.ClassDef):
            yield node.name, node.lineno
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.id, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno


def verify_contracts(src: Optional[str], origin: str) -> Dict[str, Any]:
    """소스 자기검사. 통과하지 못하면 데이터 수집을 시작하지 않는다."""
    out: Dict[str, Any] = {"source_origin": origin, "checks": {}, "violations": []}
    if not src:
        out["checks"]["source_scan"] = "SKIPPED"
        out["violations"].append(
            "자기 소스를 읽지 못해 P0_NO_STRATEGY / P0_FAIL_LOUD / P0_NO_HARDCODED_PATH "
            "정적 검사를 수행하지 못했습니다 (조용히 넘어가지 않고 여기 기록합니다)."
        )
        return out
    tree = ast.parse(src)

    bad_names = []
    for name, lineno in _iter_defined_names(tree):
        segs = {s for s in str(name).lower().split("_") if s}
        hit = segs & _BANNED_NAME_SEGMENTS
        if hit:
            bad_names.append(f"L{lineno}: {name} ({','.join(sorted(hit))})")
    out["checks"]["P0_NO_STRATEGY"] = "PASS" if not bad_names else "FAIL"
    out["violations"] += [f"P0_NO_STRATEGY 위반 — {b}" for b in bad_names]

    bad_calls, forbidden = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        nm = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if nm in _BANNED_ATTR_CALLS:
            bad_calls.append(f"L{node.lineno}: .{nm}()")
        if nm in _FORBIDDEN_CALLS:
            forbidden.append(f"L{node.lineno}: {nm}()")
    out["checks"]["P0_FAIL_LOUD"] = "PASS" if not bad_calls else "FAIL"
    out["violations"] += [f"P0_FAIL_LOUD 위반 — {b}" for b in bad_calls]
    out["checks"]["NO_KNOWN_DEAD_CALL"] = "PASS" if not forbidden else "FAIL"
    out["violations"] += [f"§2.3 영구 실패 호출 — {b}" for b in forbidden]

    bad_paths = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if any(v.startswith(p) for p in _BANNED_PATH_PREFIXES) and len(v) > 3:
                bad_paths.append(f"L{node.lineno}: {v[:60]}")
    out["checks"]["P0_NO_HARDCODED_PATH"] = "PASS" if not bad_paths else "FAIL"
    out["violations"] += [f"P0_NO_HARDCODED_PATH 위반 — {b}" for b in bad_paths]

    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _AXIS_ENTRYPOINTS:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in _AXIS_FORBIDDEN_GLOBALS:
                    leaks.append(f"L{sub.lineno}: {node.name} → {sub.id}")
    out["checks"]["P0_INDEPENDENT_AXES"] = "PASS" if not leaks else "FAIL"
    out["violations"] += [f"P0_INDEPENDENT_AXES 위반 — {b}" for b in leaks]

    # f-string SQL 은 JoinedStr 로 쪼개지므로 조각 하나하나까지 본다.
    star = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and re.search(r"SELECT\s+\*", node.value, re.I):
            star.append(f"L{node.lineno}: {node.value[:60]}")
    out["checks"]["BQ_NO_SELECT_STAR"] = "PASS" if not star else "FAIL"
    out["violations"] += [f"§4.3 {_SQL_STAR} 금지 위반 — {b}" for b in star]

    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  3. 실행 환경 — PROJECT_ROOT 자동 감지, 캐시 디렉터리, 의존성
# ═════════════════════════════════════════════════════════════════════════════════════════════

def detect_project_root() -> str:
    """스크립트/노트북 위치를 기준으로 자동 감지. 특정 환경 전용 경로를 쓰지 않는다."""
    env = os.environ.get("PHASE0_PROJECT_ROOT", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    try:
        base = os.path.dirname(os.path.abspath(__file__))   # noqa: F821
    except NameError:
        base = os.getcwd()
    cur = base
    for _ in range(6):                      # 저장소 루트를 위로 훑는다
        if any(os.path.isdir(os.path.join(cur, m)) for m in (".git",)) or \
           any(os.path.isfile(os.path.join(cur, m)) for m in ("pyproject.toml", "README.md")):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return base


PROJECT_ROOT = detect_project_root()
CACHE_ROOT = os.path.join(PROJECT_ROOT, "cache")
DIR_RAW = os.path.join(CACHE_ROOT, "raw")          # 원본 응답 (불변)
DIR_PARSED = os.path.join(CACHE_ROOT, "parsed")    # 축 × 기준일 단위 파일
DIR_REPORTS = os.path.join(CACHE_ROOT, "reports")  # 판정표·수기검증·로그
for _d in (DIR_RAW, DIR_PARSED, DIR_REPORTS):
    os.makedirs(_d, exist_ok=True)

MIN_FREE_BYTES = 200 * 1024 * 1024


def assert_disk_space(path: str = CACHE_ROOT) -> None:
    """ENOSPC 는 즉시 실패시킨다. 포맷을 바꿔 재시도하지 않는다. (§6.3)"""
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        return
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"디스크 여유 공간 부족: {free/1e6:.0f}MB "
                           f"(최소 {MIN_FREE_BYTES/1e6:.0f}MB 필요). 즉시 중단합니다.")


# ── 로깅 ──────────────────────────────────────────────────────────────────────────────────────
_LOG_PATH = os.path.join(DIR_REPORTS, "phase0_run_log.txt")
_LOG_LOCK = threading.Lock()
T0 = time.time()


class Log:
    @staticmethod
    def _emit(tag: str, msg: str) -> None:
        line = f"[{time.time()-T0:7.1f}s][{tag}] {msg}"
        with _LOG_LOCK:
            print(line, flush=True)
            try:
                with open(_LOG_PATH, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass

    @staticmethod
    def info(m: str) -> None: Log._emit("INFO", m)

    @staticmethod
    def ok(m: str) -> None: Log._emit(" OK ", m)

    @staticmethod
    def warn(m: str) -> None: Log._emit("WARN", m)

    @staticmethod
    def error(m: str) -> None: Log._emit("ERR ", m)

    @staticmethod
    def head(m: str) -> None:
        bar = "─" * max(0, 88 - len(m))
        Log._emit("STEP", f"{m} {bar}")


def ensure_packages(pkgs: Sequence[Tuple[str, str]]) -> Dict[str, bool]:
    """(import 이름, pip 이름) 목록. 설치 실패는 실패로 기록하고 계속 간다."""
    st: Dict[str, bool] = {}
    for imp, pip_name in pkgs:
        try:
            __import__(imp)
            st[imp] = True
            continue
        except Exception:
            pass
        if not ALLOW_PIP_INSTALL:
            st[imp] = False
            continue
        Log.info(f"의존성 설치 시도: {pip_name}")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", pip_name],
                           check=True, timeout=900)
            __import__(imp)
            st[imp] = True
        except Exception as e:                                            # noqa: BLE001
            Log.warn(f"{pip_name} 설치/임포트 실패({type(e).__name__}) — 관련 기능은 비활성화됩니다.")
            st[imp] = False
    return st


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  4. HTTP 계층 — 보수적 동시성, 지수 백오프, 서킷 브레이커
# ═════════════════════════════════════════════════════════════════════════════════════════════

_RNG = random.Random(RANDOM_SEED)
_RNG_LOCK = threading.Lock()

HTTP_STAT: Dict[str, Counter] = defaultdict(Counter)
CACHE_STAT = Counter()


def _jitter() -> float:
    with _RNG_LOCK:
        return _RNG.uniform(DELAY_MIN, DELAY_MAX)


class CircuitBreaker:
    """연속 실패 10회 → 60초 대기 후 재개. 3회 반복되면 해당 축을 중단한다. (§3.6)"""

    def __init__(self, name: str):
        self.name = name
        self.streak = 0
        self.trips = 0
        self.dead = False
        self._lk = threading.Lock()

    def success(self) -> None:
        with self._lk:
            self.streak = 0

    def failure(self) -> None:
        with self._lk:
            self.streak += 1
            if self.streak < CB_FAIL_STREAK:
                return
            self.streak = 0
            self.trips += 1
            if self.trips >= CB_MAX_TRIPS:
                self.dead = True
                Log.error(f"[{self.name}] 서킷 브레이커 {self.trips}회 작동 — 이 축의 수집을 중단합니다.")
                return
        Log.warn(f"[{self.name}] 연속 실패 {CB_FAIL_STREAK}회 — {CB_COOLDOWN_SEC}초 대기 후 재개 "
                 f"(작동 {self.trips}/{CB_MAX_TRIPS})")
        time.sleep(CB_COOLDOWN_SEC)


BREAKERS: Dict[str, CircuitBreaker] = {}


def breaker(name: str) -> CircuitBreaker:
    if name not in BREAKERS:
        BREAKERS[name] = CircuitBreaker(name)
    return BREAKERS[name]


_SESSION_LOCAL = threading.local()


def _session():
    import requests
    s = getattr(_SESSION_LOCAL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            "Accept": "*/*",
        })
        _SESSION_LOCAL.s = s
    return s


def http_get(url: str, source: str, params: Optional[dict] = None,
             tries: int = 3, timeout: int = 30,
             referer: Optional[str] = None) -> Optional[bytes]:
    """지수 백오프 + 랜덤 지연. 실패는 None 으로 돌려주고 사유를 집계한다."""
    cb = breaker(source)
    if cb.dead:
        return None
    headers = {"Referer": referer} if referer else {}
    delay = 1.0
    for attempt in range(1, tries + 1):
        time.sleep(_jitter())
        HTTP_STAT[source]["req"] += 1
        try:
            r = _session().get(url, params=params, timeout=timeout, headers=headers)
            if r.status_code == 200:
                HTTP_STAT[source]["ok"] += 1
                cb.success()
                return r.content
            HTTP_STAT[source][f"http_{r.status_code}"] += 1
            if r.status_code in (400, 401, 403, 404):
                cb.failure()
                return None
        except Exception as e:                                            # noqa: BLE001
            HTTP_STAT[source][type(e).__name__] += 1
        if attempt < tries:
            time.sleep(delay)
            delay *= 2
    cb.failure()
    return None


def http_json(url: str, source: str, params: Optional[dict] = None,
              tries: int = 3, timeout: int = 30,
              referer: Optional[str] = None) -> Optional[Any]:
    raw = http_get(url, source, params=params, tries=tries, timeout=timeout, referer=referer)
    if raw is None:
        return None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError:
            HTTP_STAT[source]["not_json"] += 1
            return None
    HTTP_STAT[source]["decode_fail"] += 1
    return None


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  5. 캐시 계층 — skip-if-exists (P0_RESUMABLE). 원본은 raw/, 정제본은 parsed/ 에 둔다.
#
#  핫 캐시는 로컬 디스크만 쓴다. Google Drive 는 이 단계에서 연결하지 않는다 —
#  파일 수천 개를 만드는 워크로드에서 Drive 를 핫 캐시로 쓰면 I/O 가 병목이 되고,
#  마운트 실패가 '데이터 없음'으로 오독될 여지가 생긴다. 백업이 필요하면 실행이 끝난 뒤
#  cache/ 디렉터리를 통째로 복사하면 된다(콜드 백업).
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _safe_key(key: str) -> str:
    return re.sub(r"[^0-9A-Za-z._\-]", "_", key)[:180]


def atomic_write_text(path: str, text: str) -> None:
    assert_disk_space(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def atomic_write_bytes(path: str, blob: bytes) -> None:
    assert_disk_space(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, path)


def cache_json(namespace: str, key: str, producer: Callable[[], Any],
               subdir: str = DIR_RAW,
               cacheable: Optional[Callable[[Any], bool]] = None) -> Any:
    """이미 있으면 네트워크를 건드리지 않는다. 없으면 만들어 저장한다.

    ★ 무엇을 캐시에 굳히느냐가 P0_RESUMABLE 의 전부다.
      '데이터가 없다'(사실) 는 굳혀도 되지만, '인증 실패·일일한도 초과·통신 오류'(상태)
      를 굳히면 다음 실행이 영원히 같은 실패를 재생하며 '없음'으로 보고한다.
      그래서 무엇이 캐시 가능한지는 호출부가 명시한다."""
    ok = cacheable or (lambda x: x is not None)
    d = os.path.join(subdir, _safe_key(namespace))
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, _safe_key(key) + ".json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                CACHE_STAT["hit"] += 1
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            os.replace(p, p + ".corrupt")      # 지우지 않고 격리만 한다
    CACHE_STAT["miss"] += 1
    val = producer()
    if val is not None and ok(val):
        atomic_write_text(p, json.dumps(val, ensure_ascii=False))
    return val


def cache_bytes(namespace: str, key: str, producer: Callable[[], Optional[bytes]]) -> Optional[bytes]:
    d = os.path.join(DIR_RAW, _safe_key(namespace))
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, _safe_key(key) + ".bin")
    if os.path.exists(p):
        CACHE_STAT["hit"] += 1
        with open(p, "rb") as fh:
            return fh.read()
    CACHE_STAT["miss"] += 1
    val = producer()
    if val:
        atomic_write_bytes(p, val)
    return val


def parsed_path(axis: str, as_of: str, name: str) -> str:
    """축 × 기준일 단위 파일. 단일 대용량 파일을 만들지 않는다. (§6.2)"""
    d = os.path.join(DIR_PARSED, f"axis_{axis}", as_of)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, _safe_key(name))


def pmap(fn: Callable, items: Sequence, desc: str, workers: int = N_WORKERS) -> List[Any]:
    """보수적 동시성. 진행률을 종목 단위로 찍는다."""
    out: List[Any] = [None] * len(items)
    if not items:
        return out
    done = 0
    step = max(1, len(items) // 20)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, N_WORKERS))) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                out[i] = f.result()
            except Exception as e:                                        # noqa: BLE001
                Log.warn(f"{desc} 항목 실패 [{i}] {type(e).__name__}: {e}")
                out[i] = None
            done += 1
            if done % step == 0 or done == len(items):
                Log.info(f"{desc} {done:,}/{len(items):,} ({100*done/len(items):.0f}%)")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  6. 공용 유틸 — 법인명 정규화, 유사도, 날짜
# ═════════════════════════════════════════════════════════════════════════════════════════════

_CORP_SUFFIX_PAT = re.compile(
    r"(주식회사|㈜|\(주\)|\（주\）|유한회사|유한책임회사|합자회사|합명회사|재단법인|사단법인|"
    r"주식회사$|co\.?,?\s*ltd\.?|co\.?\s*limited|corporation|corp\.?|incorporated|inc\.?|"
    r"ltd\.?|llc|plc|company|group|holdings?|kabushiki\s*kaisha)",
    re.I)
_PAREN_PAT = re.compile(r"[\(\（][^\)\）]*[\)\）]")
_NONWORD_PAT = re.compile(r"[^0-9A-Za-z가-힣]")


def norm_corp_name(s: Any) -> str:
    """주식회사/㈜/Co.,Ltd 등 제거 후 공백·대소문자·기호 정규화. (§4.5.3)"""
    if s is None:
        return ""
    t = str(s).strip()
    if not t:
        return ""
    t = _PAREN_PAT.sub(" ", t)
    t = _CORP_SUFFIX_PAT.sub(" ", t)
    t = _NONWORD_PAT.sub("", t)
    return t.lower()


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def prefix_bucket(names: Sequence[str], k: int = 2) -> Dict[str, List[int]]:
    """앞 k글자로 후보를 미리 묶는다. 이게 없으면 1,000 × 수십만 비교로 폭발한다."""
    b: Dict[str, List[int]] = defaultdict(list)
    for i, s in enumerate(names):
        if s and len(s) >= k:
            b[s[:k]].append(i)
    return b


def fuzzy_best(query: str, names: Sequence[str], bucket: Dict[str, List[int]],
               threshold: float = FUZZY_THRESHOLD) -> Tuple[Optional[int], float]:
    """앞 2글자 버킷 + 길이비 사전필터 후에만 SequenceMatcher 를 돌린다.
    ★ threshold 는 호출부에서 낮추지 않는다 (§4.5.4 매칭률 부풀리기 금지)."""
    if not query or len(query) < 2:
        return None, 0.0
    best, bsim = None, 0.0
    lo, hi = len(query) * threshold, len(query) / max(threshold, 0.01)
    for i in bucket.get(query[:2], []):
        cand = names[i]
        if not (lo <= len(cand) <= hi):        # 길이가 이만큼 다르면 임계를 넘을 수 없다
            continue
        s = similarity(query, cand)
        if s > bsim:
            best, bsim = i, s
    return (best, bsim) if (best is not None and bsim >= threshold) else (None, bsim)


def has_hangul(s: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(s or "")))


def to_code6(x: Any) -> Optional[str]:
    s = re.sub(r"\D", "", str(x or ""))
    return s.zfill(6) if s else None


def ymd_int(d: str) -> int:
    return int(str(d).replace("-", "")[:8])


def as_date(s: str) -> _dt.date:
    return _dt.date(*[int(x) for x in str(s)[:10].split("-")])


def shift_years(d: str, years: int) -> str:
    dd = as_date(d)
    try:
        return dd.replace(year=dd.year + years).isoformat()
    except ValueError:                       # 2/29
        return dd.replace(year=dd.year + years, day=28).isoformat()


def elapsed() -> float:
    return time.time() - T0


def budget_left() -> float:
    return TIME_BUDGET_SEC - elapsed()


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  7. 판정표 자료구조
# ═════════════════════════════════════════════════════════════════════════════════════════════

class Gate:
    def __init__(self, gid: str, criterion: str, measured: Any,
                 threshold: Any, passed: Optional[bool], note: str = ""):
        self.gid, self.criterion = gid, criterion
        self.measured, self.threshold, self.passed, self.note = measured, threshold, passed, note

    def to_dict(self) -> dict:
        return {"id": self.gid, "criterion": self.criterion, "measured": self.measured,
                "threshold": self.threshold, "pass": self.passed, "note": self.note}


class AxisVerdict:
    def __init__(self, axis: str, as_of: str):
        self.axis, self.as_of = axis, as_of
        self.gates: List[Gate] = []
        self.limits: List[str] = []
        self.api_calls = 0
        self.t_start = time.time()
        self.forced_status: Optional[str] = None
        self.extra: Dict[str, Any] = {}

    def gate(self, *a, **kw) -> None:
        self.gates.append(Gate(*a, **kw))

    def limit(self, msg: str) -> None:
        if msg not in self.limits:
            self.limits.append(msg)

    @property
    def status(self) -> str:
        if self.forced_status:
            return self.forced_status
        measurable = [g for g in self.gates if g.passed is not None]
        if any(g.passed is False for g in measurable):
            return "STOP"
        if any(g.passed is None for g in self.gates):
            return "PENDING_MANUAL"
        return "GO" if measurable else "STOP"

    def to_dict(self) -> dict:
        return {
            "axis": self.axis,
            "as_of": self.as_of,
            "status": self.status,
            "gates": [g.to_dict() for g in self.gates],
            "known_limitations": list(self.limits),
            "api_calls_used": int(self.api_calls),
            "runtime_sec": round(time.time() - self.t_start, 1),
            "detail": self.extra,
        }


def _rate(num: int, den: int) -> Optional[float]:
    """분모가 0이면 None. 0으로 나누어 0.0 을 만들어 놓고 '측정했다'고 하지 않는다."""
    return round(num / den, 4) if den else None


def _ge(measured: Optional[float], thr: float) -> Optional[bool]:
    return None if measured is None else bool(measured >= thr)


def _le(measured: Optional[float], thr: float) -> Optional[bool]:
    return None if measured is None else bool(measured <= thr)


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  8. 유니버스 — PIT. 각 기준일 시점의 상장 종목으로 구성한다. (§2, P0_PIT_UNIVERSE)
#
#  ★ 알려진 함정 (§2.3)
#    · pykrx 의 지수 구성종목 예탁 파일 조회(1028)는 영구 실패한다. 여기서는 아예 쓰지 않고,
#      그런 호출이 소스에 있으면 계약 자기검사(NO_KNOWN_DEAD_CALL)가 실행을 막는다.
#    · 2025년 KRX 로그인 요구사항 변경으로 pykrx 인증이 실패할 수 있다 →
#      FinanceDataReader 단독 경로로 폴백하고, 그때 생기는 생존편향·시총 소급적용을
#      판정표에 그대로 적는다.
# ═════════════════════════════════════════════════════════════════════════════════════════════

UNIV_COLS = ["code", "name", "market", "marcap", "marcap_rank",
             "is_preferred", "is_spac", "is_reit", "is_etf_etn", "is_admin", "src"]


def _flag_preferred(code: str, name: str) -> bool:
    nm = str(name or "")
    if re.search(r"(우|우B|우C|1우|2우B|\(전환\))\s*$", nm):
        return True
    c = to_code6(code) or ""
    return bool(len(c) == 6 and c[-1] != "0")


def _flag_spac(name: str) -> bool:
    return bool(re.search(r"(스팩|기업인수목적)", str(name or "")))


def _flag_reit(name: str) -> bool:
    return bool(re.search(r"(리츠|위탁관리부동산투자|자기관리부동산투자)", str(name or "")))


def _flag_etf_etn(name: str) -> bool:
    return bool(re.search(r"(ETF|ETN|KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE )",
                          str(name or ""), re.I))


def _pykrx_universe(as_of: str) -> Tuple[Optional[Any], List[str]]:
    """진짜 PIT 경로. 그 날짜에 상장되어 있던 종목과 그 날짜의 시가총액을 그대로 받는다.
    상장폐지 종목이 자연히 포함되므로 생존편향이 없다."""
    notes: List[str] = []
    try:
        import pandas as pd
        from pykrx import stock as _krx
    except Exception as e:                                                # noqa: BLE001
        return None, [f"pykrx 임포트 실패({type(e).__name__}) — FinanceDataReader 단독 경로로 폴백"]
    d = str(as_of).replace("-", "")
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        got = None
        for attempt in range(3):
            try:
                t = _krx.get_market_cap_by_ticker(d, market=mkt)
                if t is not None and len(t):
                    got = t
                    break
            except Exception as e:                                        # noqa: BLE001
                notes.append(f"pykrx {mkt} {d} 시도{attempt+1} 실패: {type(e).__name__}")
            time.sleep(1.5 * (attempt + 1))
        if got is None:
            return None, notes + [
                "pykrx 로 과거 시가총액을 받지 못했습니다 "
                "(2025년 KRX 로그인 요구사항 변경 가능성). FinanceDataReader 단독 경로로 폴백합니다."]
        t = got.reset_index()
        code_col = "티커" if "티커" in t.columns else t.columns[0]
        cap_col = "시가총액" if "시가총액" in t.columns else None
        if cap_col is None:
            return None, notes + ["pykrx 응답에 시가총액 컬럼이 없습니다 — 폴백합니다."]
        # ★ 종목명은 여기서 채우지 않는다. get_market_ticker_name 은 종목당 1회 네트워크
        #   호출이라 2,800종목 × 2시점이면 그것만으로 수십 분이 날아간다.
        #   하위 1,000종목을 고른 뒤 필요한 것만 채운다.
        frames.append(pd.DataFrame({
            "code": [to_code6(c) for c in t[code_col].astype(str)],
            "name": "",
            "market": mkt,
            "marcap": pd.to_numeric(t[cap_col], errors="coerce"),
            "src": "pykrx",
        }))
    u = pd.concat(frames, ignore_index=True)
    notes.append("PIT 경로: pykrx 시점별 시가총액 — 해당일 상장 종목만 포함(생존편향 없음)")
    return u, notes


def _fill_names(sel: Any, notes: List[str], cap: int = 400) -> Any:
    """선택된 종목의 이름만 채운다. ① FDR 현재 상장목록 매핑 ② 나머지는 pykrx 개별 조회.
    이름을 못 채운 종목은 빈 문자열로 남긴다(임의의 대체명을 만들지 않는다 — P0_FAIL_LOUD)."""
    need = sel["name"].astype(str).str.len() == 0
    if not bool(need.any()):
        return sel
    name_map: Dict[str, str] = {}
    try:
        import FinanceDataReader as fdr
        for mkt in ("KOSPI", "KOSDAQ"):
            t = fdr.StockListing(mkt)
            if t is None or not len(t):
                continue
            ccol = "Code" if "Code" in t.columns else ("Symbol" if "Symbol" in t.columns else None)
            if ccol is None or "Name" not in t.columns:
                continue
            for c, n in zip(t[ccol].astype(str), t["Name"].astype(str)):
                cc6 = to_code6(c)
                if cc6:
                    name_map[cc6] = n
    except Exception as e:                                                # noqa: BLE001
        notes.append(f"FDR 종목명 매핑 실패({type(e).__name__}) — pykrx 개별 조회에만 의존합니다.")
    sel = sel.copy()
    sel["name"] = [name_map.get(c, n) for c, n in zip(sel["code"], sel["name"].astype(str))]

    still = [c for c, n in zip(sel["code"], sel["name"].astype(str)) if not n]
    if still:
        try:
            from pykrx import stock as _krx
            for c in still[:cap]:
                try:
                    name_map[c] = _krx.get_market_ticker_name(c) or ""
                except Exception:                                         # noqa: BLE001
                    pass
                time.sleep(0.05)
        except Exception as e:                                            # noqa: BLE001
            notes.append(f"pykrx 종목명 조회 불가({type(e).__name__}).")
        sel["name"] = [name_map.get(c, n) for c, n in zip(sel["code"], sel["name"].astype(str))]
        blank = int((sel["name"].astype(str).str.len() == 0).sum())
        if blank:
            notes.append(f"종목명을 확보하지 못한 종목 {blank:,}개 — 빈 값으로 남깁니다 "
                         f"(상호 기반 매칭에서 이 종목들은 자동 불일치가 됩니다).")
    return sel


def _fdr_universe(as_of: str) -> Tuple[Optional[Any], List[str]]:
    """폴백 경로. FinanceDataReader 는 '현재' 상장목록과 '현재' 시가총액만 준다.
    → 과거 기준일에 쓰면 (a) 생존편향 (b) 시총 소급적용 두 결함이 동시에 생긴다. 숨기지 않는다."""
    notes: List[str] = []
    try:
        import pandas as pd
        import FinanceDataReader as fdr
    except Exception as e:                                                # noqa: BLE001
        return None, [f"FinanceDataReader 임포트 실패({type(e).__name__})"]
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        try:
            t = fdr.StockListing(mkt)
        except Exception as e:                                            # noqa: BLE001
            notes.append(f"FDR StockListing({mkt}) 실패: {type(e).__name__}")
            continue
        if t is None or not len(t):
            continue
        code_col = next((c for c in ("Code", "Symbol") if c in t.columns), None)
        cap_col = next((c for c in ("Marcap", "MarketCap") if c in t.columns), None)
        if code_col is None:
            notes.append(f"FDR {mkt} 응답에 종목코드 컬럼이 없습니다 (컬럼: {list(t.columns)[:12]})")
            continue
        if cap_col is None:
            notes.append(f"FDR {mkt} 응답에 Marcap 컬럼이 없습니다 (컬럼: {list(t.columns)[:12]}) — "
                         f"시가총액 없이는 하위 1,000종목을 정의할 수 없습니다.")
            continue
        frames.append(pd.DataFrame({
            "code": [to_code6(c) for c in t[code_col].astype(str)],
            "name": t["Name"].astype(str) if "Name" in t.columns else "",
            "market": mkt,
            "marcap": pd.to_numeric(t[cap_col], errors="coerce"),
            "src": "fdr",
        }))
    if not frames:
        return None, notes + ["FinanceDataReader 로도 상장목록을 받지 못했습니다."]
    u = pd.concat(frames, ignore_index=True)
    today = _dt.date.today().isoformat()
    if as_of < today:
        notes.append(
            f"생존편향 있음: {as_of} 유니버스를 현재({today}) 상장목록으로 구성했습니다. "
            f"당시 상장되어 있다가 이후 상장폐지된 종목이 누락됩니다.")
        notes.append(
            f"시가총액 소급적용: {as_of} 순위를 현재 시가총액으로 매겼습니다 "
            f"(P0_PIT_UNIVERSE 미충족 — pykrx 경로 실패로 인한 폴백).")
    return u, notes


def _fdr_delisted_at(as_of: str) -> Tuple[int, List[str]]:
    """폴백 경로에서 '얼마나 누락되는가'만이라도 숫자로 남긴다."""
    notes: List[str] = []
    try:
        import pandas as pd
        import FinanceDataReader as fdr
        t = fdr.StockListing("KRX-DELISTING")
    except Exception as e:                                                # noqa: BLE001
        return -1, [f"상장폐지 목록 확보 실패({type(e).__name__}) — 누락 규모를 측정하지 못했습니다."]
    if t is None or not len(t):
        return -1, ["상장폐지 목록이 비어 있습니다 — 누락 규모를 측정하지 못했습니다."]
    dcol = next((c for c in t.columns if "delist" in str(c).lower()), None)
    lcol = next((c for c in t.columns if "listingdate" in str(c).lower().replace("_", "")), None)
    if dcol is None:
        return -1, [f"상장폐지일 컬럼을 찾지 못했습니다 (컬럼: {list(t.columns)[:12]})"]
    dd = pd.to_datetime(t[dcol], errors="coerce")
    cond = dd > pd.Timestamp(as_of)
    if lcol is not None:
        ll = pd.to_datetime(t[lcol], errors="coerce")
        cond = cond & (ll <= pd.Timestamp(as_of))
    n = int(cond.sum())
    notes.append(f"{as_of} 시점 상장 중이었다가 이후 상장폐지된 종목 {n:,}건이 "
                 f"현재 상장목록 기반 유니버스에서 누락됩니다.")
    return n, notes


def build_universe(as_of: str) -> Tuple[Any, Dict[str, Any]]:
    """하위 UNIVERSE_SIZE 종목. 플래그는 표시만 하고 제외하지 않는다. (§2.1.4)"""
    import pandas as pd
    meta: Dict[str, Any] = {"as_of": as_of, "notes": [], "pit_ok": False}
    cache_p = parsed_path("universe", as_of, "universe.csv")
    meta_p = parsed_path("universe", as_of, "universe_meta.json")
    if os.path.exists(cache_p) and os.path.exists(meta_p):
        CACHE_STAT["hit"] += 1
        u = pd.read_csv(cache_p, dtype={"code": str})
        with open(meta_p, encoding="utf-8") as fh:
            meta = json.load(fh)
        Log.info(f"유니버스 캐시 재사용 {as_of}: {len(u):,}종목")
        return u, meta

    u, notes = _pykrx_universe(as_of)
    if u is not None and len(u):
        meta["pit_ok"] = True
        meta["source"] = "pykrx"
    else:
        for n in notes:
            Log.warn(n)
        u2, notes2 = _fdr_universe(as_of)
        notes = notes + notes2
        if u2 is None or not len(u2):
            raise RuntimeError("유니버스를 어느 경로로도 구성하지 못했습니다. 네트워크를 확인하세요.")
        u = u2
        meta["source"] = "fdr"
        n_miss, dn = _fdr_delisted_at(as_of)
        notes += dn
        meta["delisted_missing_count"] = n_miss
    meta["notes"] = notes

    u = u.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    u = u[pd.to_numeric(u["marcap"], errors="coerce").notna()].copy()
    u["marcap"] = pd.to_numeric(u["marcap"], errors="coerce")
    u = u.sort_values("marcap", ascending=False).reset_index(drop=True)
    meta["listed_total"] = int(len(u))
    u["marcap_rank"] = range(1, len(u) + 1)
    sel = u.tail(UNIVERSE_SIZE).copy().reset_index(drop=True)
    sel = _fill_names(sel, meta["notes"])

    sel["is_preferred"] = [bool(_flag_preferred(c, n)) for c, n in zip(sel["code"], sel["name"])]
    sel["is_spac"] = [bool(_flag_spac(n)) for n in sel["name"]]
    sel["is_reit"] = [bool(_flag_reit(n)) for n in sel["name"]]
    sel["is_etf_etn"] = [bool(_flag_etf_etn(n)) for n in sel["name"]]
    sel["is_admin"] = None            # 관리종목 상태의 시점별 이력은 확보 경로가 없다 → 미측정
    meta["notes"].append(
        "관리종목 플래그: 시점별 지정 이력을 제공하는 소스를 찾지 못해 측정하지 않았습니다(None).")
    meta["notes"].append(
        "우선주/스팩/리츠/ETF·ETN 플래그는 종목코드 말자리·종목명 규칙 기반 휴리스틱입니다.")
    meta["excluded_if_filtered"] = int(
        (sel["is_preferred"] | sel["is_spac"] | sel["is_reit"] | sel["is_etf_etn"]).sum())
    meta["n_selected"] = int(len(sel))
    meta["marcap_rank_range"] = [int(sel["marcap_rank"].min()), int(sel["marcap_rank"].max())]

    sel = sel[[c for c in UNIV_COLS if c in sel.columns]]
    sel.to_csv(cache_p, index=False)
    atomic_write_text(meta_p, json.dumps(meta, ensure_ascii=False, indent=2))
    Log.ok(f"유니버스 {as_of}: 상장 {meta['listed_total']:,}종목 중 하위 {len(sel):,} "
           f"(순위 {meta['marcap_rank_range'][0]}~{meta['marcap_rank_range'][1]}, "
           f"플래그 해당 {meta['excluded_if_filtered']:,})")
    return sel, meta


def canary_pick(univ: Any, salt: str) -> List[Tuple[str, str]]:
    """축별로 서로 다른 10종목을 뽑되, 재실행 시 같은 종목이 나오도록 시드를 고정한다."""
    rnd = random.Random(f"{RANDOM_SEED}:{salt}")
    rows = list(zip(univ["code"].astype(str).tolist(), univ["name"].astype(str).tolist()))
    return rnd.sample(rows, min(CANARY_N, len(rows)))


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  9. 공용 리소스 — DART corpCode (축 A/B/C 가 각자 쓰는 '입력'이지 서로의 '결과'가 아니다)
#     P0_INDEPENDENT_AXES 는 축이 다른 축의 산출물에 의존하지 않는다는 뜻이다.
#     공통 원자료를 공유하는 것은 의존이 아니므로 여기서 한 번만 받는다.
# ═════════════════════════════════════════════════════════════════════════════════════════════

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}

DART_CALLS = Counter()
_DART_LOCK = threading.Lock()


def dart_call(endpoint: str, params: dict, tries: int = 2) -> Tuple[Optional[dict], str]:
    """(응답, status) 를 함께 돌려준다. status 를 삼키면 '없음'과 '실패'를 구분할 수 없다."""
    if not DART_API_KEY:
        return None, "NOKEY"
    with _DART_LOCK:
        if DART_CALLS["n"] >= DART_DAILY_LIMIT:
            return None, "020"
        DART_CALLS["n"] += 1
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/")
    if not isinstance(js, dict):
        return None, "NORESP"
    st = str(js.get("status", ""))
    if st != "000":
        return None, st or "NOSTATUS"
    return js, "000"


def fetch_dart_corpcode() -> Tuple[Any, Dict[str, Any]]:
    """corp_code ↔ 종목코드 매핑. DART 의 모든 조회는 corp_code 로만 된다. (§3.4)"""
    import pandas as pd
    info: Dict[str, Any] = {"ok": False, "n_rows": 0, "n_listed": 0, "reason": ""}
    if not DART_API_KEY:
        info["reason"] = "DART_API_KEY 미입력"
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"]), info

    def _dl() -> Optional[bytes]:
        with _DART_LOCK:
            DART_CALLS["n"] += 1
        return http_get(DART_BASE + "corpCode.xml", source="dart",
                        params={"crtfc_key": DART_API_KEY}, tries=3, timeout=120,
                        referer="https://opendart.fss.or.kr/")

    raw = cache_bytes("dart_corpcode", "corpCode_zip", _dl)
    if not raw:
        info["reason"] = "corpCode.xml 수신 실패"
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"]), info
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        m = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        st = m.group(1) if m else "?"
        info["reason"] = f"ZIP 이 아닌 응답 (status={st}: {DART_STATUS_MSG.get(st, '알 수 없음')})"
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"]), info
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist())
    except Exception as e:                                                # noqa: BLE001
        info["reason"] = f"zip 해제 실패({type(e).__name__})"
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"]), info
    txt = xml.decode("utf-8", "ignore")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag: str) -> str:
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return mm.group(1).strip() if mm else ""
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code"))})
    cc = pd.DataFrame(rows)
    info["ok"] = bool(len(cc))
    info["n_rows"] = int(len(cc))
    info["n_listed"] = int(cc["code"].notna().sum()) if len(cc) else 0
    Log.ok(f"DART corpCode {info['n_rows']:,}건 (종목코드 보유 {info['n_listed']:,}건)")
    return cc, info


def map_universe_to_corp(univ: Any, corpcode: Any) -> Tuple[Any, Dict[str, Any]]:
    if corpcode is None or not len(corpcode):
        u = univ.copy()
        u["corp_code"] = None
        u["corp_name"] = None
        return u, {"mapped": 0, "total": int(len(u)), "fail_rate": 1.0}
    cc = corpcode.dropna(subset=["code"]).drop_duplicates("code", keep="first")
    u = univ.merge(cc[["code", "corp_code", "corp_name"]], on="code", how="left")
    n_ok = int(u["corp_code"].notna().sum())
    return u, {"mapped": n_ok, "total": int(len(u)),
               "fail_rate": round(1 - n_ok / max(1, len(u)), 4)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  10. 축 A — DART 임원현황
# ═════════════════════════════════════════════════════════════════════════════════════════════

# 정기보고서 코드와 법정 제출기한. PIT 선택에 쓴다.
REPRT = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}

# 임원현황 전용 API 후보. 선행 확인(§3.2)에서 라이브 프로브로 존재 여부를 확정한다.
# ★ '보수현황' 류 엔드포인트를 후보에 넣지 않는다. 응답이 오더라도 임원현황이 아니므로
#   존재 확인이 거짓 양성이 된다. 후보는 임원현황 자체를 가리키는 이름만 둔다.
EXEC_ENDPOINT_CANDIDATES = ["exctvSttus.json"]
# 대조군 — DS002 그룹(정기보고서 주요정보) 자체가 살아 있는지 확인. 직원현황.
CONTROL_ENDPOINT = "empSttus.json"
# 프로브용 corp_code (삼성전자 / SK하이닉스). 유니버스 종목이 아니라 'API 존재 확인'에만 쓴다.
PROBE_CORP_CODES = ["00126380", "00164779"]
# 응답이 실제로 임원현황인지 확인하는 필수 필드
EXEC_SIGNATURE_FIELDS = {"nm", "birth_ym", "ofcps"}

EXEC_FIELDS = ["nm", "sexdstn", "birth_ym", "ofcps", "rgist_exctv_at", "fte_at",
               "chrg_job", "main_career", "mxmm_shrholdr_relate", "hffc_pd", "tenure_end_on"]


def _reprt_deadline(year: int, code: str) -> _dt.date:
    m, d = REPRT_PERIOD_END[code]
    return _dt.date(year, m, d) + _dt.timedelta(days=REPRT_DEADLINE_DAYS[code])


def reprt_candidates(as_of: str) -> List[Tuple[int, str]]:
    """as_of 시점에 이미 제출되었어야 하는 정기보고서를 최신 결산기준 순으로. (P0_PIT_UNIVERSE)"""
    d = as_date(as_of)
    out: List[Tuple[_dt.date, int, str]] = []
    for y in range(d.year - 2, d.year + 1):
        for code in ("11013", "11011", "11014", "11012"):
            if _reprt_deadline(y, code) <= d:
                m, dd = REPRT_PERIOD_END[code]
                out.append((_dt.date(y, m, dd), y, code))
    out.sort(key=lambda t: t[0], reverse=True)
    return [(y, c) for _, y, c in out][:3]        # 최신 3개까지만 시도 (호출 예산)


def axis_a_precheck() -> Dict[str, Any]:
    """§3.2 선행 확인. 문서 조회는 차단될 수 있으므로 라이브 프로브를 판정 근거로 삼는다.
    ★ status 000 만으로 만족하지 않는다. 응답 필드가 실제 임원현황인지까지 확인해야
      '전용 API 가 있다'고 말할 수 있다."""
    res: Dict[str, Any] = {"documented": None, "probe": {}, "dedicated_api": False,
                           "endpoint": None, "fields_confirmed": False,
                           "control_alive": None, "sample_fields": []}

    # ① 개발가이드 DS002 목록 (best-effort — 접근 차단/개편 시 실패해도 계속 간다)
    raw = http_get("https://opendart.fss.or.kr/guide/main.do", source="dart_guide",
                   params={"apiGrpCd": "DS002"}, tries=2, timeout=20)
    if raw:
        html = raw.decode("utf-8", "ignore")
        ids = sorted(set(re.findall(r"apiId=([A-Za-z0-9]+)", html)))
        titles = sorted({t.strip() for t in re.findall(r">\s*([^<>]{2,30}?현황)\s*<", html)})
        res["documented"] = {"api_ids": ids[:60], "titles_found": titles[:60],
                             "mentions_exec_status": ("임원현황" in html or "임원 현황" in html)}
    else:
        res["documented"] = {"error": "개발가이드 페이지를 받지 못했습니다(차단/개편 가능). "
                                      "라이브 프로브 결과로 판정합니다."}

    # ② 라이브 프로브 — status 000(데이터 있음) / 013(데이터 없음) 이면 엔드포인트는 존재한다.
    probe_year = _dt.date.today().year - 1
    for ep in EXEC_ENDPOINT_CANDIDATES:
        for corp in PROBE_CORP_CODES:
            js, st = dart_call(ep, {"corp_code": corp, "bsns_year": str(probe_year),
                                    "reprt_code": "11011"})
            res["probe"][f"{ep}@{corp}"] = st
            if st not in ("000", "013"):
                continue
            if not res["dedicated_api"]:
                res["dedicated_api"] = True
                res["endpoint"] = ep
            if st == "000" and isinstance(js, dict):
                lst = js.get("list") or []
                if lst:
                    keys = sorted(lst[0].keys())
                    res["sample_fields"] = keys
                    res["fields_confirmed"] = EXEC_SIGNATURE_FIELDS.issubset(set(keys))
            if res["fields_confirmed"]:
                break
        if res["fields_confirmed"]:
            break
    if res["dedicated_api"] and not res["fields_confirmed"]:
        res["note"] = ("엔드포인트는 응답했으나 임원 필드(nm/birth_ym/ofcps)를 확인하지 "
                       "못했습니다. 프로브 종목에 데이터가 없었을 수 있습니다.")
    _, cst = dart_call(CONTROL_ENDPOINT, {"corp_code": PROBE_CORP_CODES[0],
                                          "bsns_year": str(probe_year), "reprt_code": "11011"})
    res["control_alive"] = cst in ("000", "013")
    res["control_status"] = cst
    return res


def _fetch_exec_one(endpoint: str, corp_code: str, as_of: str,
                    cands: Sequence[Tuple[int, str]]) -> Dict[str, Any]:
    """한 종목의 임원현황. PIT: 접수일자(rcept_no 앞 8자리) > as_of 인 레코드는 버린다."""
    cut = ymd_int(as_of)
    out: Dict[str, Any] = {"corp_code": corp_code, "rows": [], "status": "EMPTY",
                           "used": None, "dropped_future": 0, "tried": []}
    for year, code in cands:
        key = f"{corp_code}_{year}_{code}"
        payload = cache_json(
            f"axis_a/{as_of}", key,
            lambda y=year, c=code: _dart_exec_raw(endpoint, corp_code, y, c),
            cacheable=lambda x: isinstance(x, dict) and x.get("_status") in ("000", "013"))
        out["tried"].append(f"{year}/{code}")
        if not payload:
            continue
        st = payload.get("_status", "")
        if st in ("010", "011", "012", "901"):
            out["status"] = "AUTH"
            return out
        if st == "020":
            out["status"] = "LIMIT"
            return out
        rows = payload.get("list") or []
        keep = []
        for r in rows:
            rc = str(r.get("rcept_no", ""))[:8]
            if rc and rc.isdigit() and int(rc) > cut:
                out["dropped_future"] += 1
                continue
            keep.append({k: r.get(k) for k in EXEC_FIELDS + ["rcept_no", "corp_name"]})
        if keep:
            out["rows"] = keep
            out["status"] = "OK"
            out["used"] = f"{year}/{code}"
            return out
    return out


def _dart_exec_raw(endpoint: str, corp_code: str, year: int, code: str) -> Optional[dict]:
    """항상 _status 를 붙여 돌려준다. 무엇을 캐시할지는 cache_json 의 cacheable 이 정한다.
    (013=데이터 없음 은 사실이므로 캐시 가능, 인증실패·한도초과는 캐시 금지.)"""
    js, st = dart_call(endpoint, {"corp_code": corp_code, "bsns_year": str(year),
                                  "reprt_code": code})
    if js is None:
        return {"_status": st, "list": []}
    js["_status"] = st
    return js


# ★ 대안 순서 주의: (0?[1-9]|1[0-2]) 로 쓰면 "1970년 12월" 의 12 에서 1 만 먹혀 1월이 된다.
_BIRTH_YM_PAT = re.compile(r"(19\d{2}|20\d{2})\D{0,4}(1[0-2]|0?[1-9])?(?!\d)")
_BIRTH_YY_PAT = re.compile(r"^(\d{2})\D(1[0-2]|0?[1-9])$")


def parse_birth(v: Any) -> Optional[str]:
    """'1970년 03월' / '1970.03' / '70.03' 등. 파싱 실패는 결측으로 센다 (보정하지 않는다).
    월이 없으면 'YYYY-00' 으로 남긴다 — 없는 월을 만들어 넣지 않는다 (P0_FAIL_LOUD)."""
    s = str(v or "").strip()
    if not s or s in ("-", "미기재", "해당사항없음", "비공개"):
        return None
    m = _BIRTH_YM_PAT.search(s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) else f"{m.group(1)}-00"
    m2 = _BIRTH_YY_PAT.match(s)
    if m2:
        yy = int(m2.group(1))
        y = 1900 + yy if yy > 30 else 2000 + yy
        return f"{y}-{int(m2.group(2)):02d}"
    return None


def norm_person(nm: Any) -> str:
    return re.sub(r"[\s\.\(\)\[\]]", "", str(nm or "")).strip()


def run_axis_a(univ: Any, as_of: str, precheck: Dict[str, Any],
               corp_map_info: Dict[str, Any]) -> Tuple[AxisVerdict, Any]:
    """축 A. 다른 축의 산출물을 참조하지 않는다 (P0_INDEPENDENT_AXES)."""
    import pandas as pd
    v = AxisVerdict("A", as_of)
    v.extra["precheck"] = precheck
    v.extra["corp_code_mapping"] = corp_map_info
    n_univ = int(len(univ))

    if not DART_API_KEY:
        v.forced_status = "BLOCKED_PREREQ"
        v.limit("DART_API_KEY 미입력 — 축 A 를 실행할 수 없습니다.")
        return v, pd.DataFrame()

    if not precheck.get("dedicated_api"):
        # §3.2: 전용 API 가 없으면 원문 파싱 난이도만 평가하고 '조건부 실패'로 둔다.
        v.forced_status = "STOP"
        v.limit("조건부 실패: 임원현황 전용 API 를 확인하지 못했습니다 "
                f"(프로브 결과 {precheck.get('probe')}).")
        v.limit("사업보고서 원문 파싱 경로 난이도 평가: 원문은 XBRL 이 아닌 서식 HTML/한글문서이며 "
                "'임원 현황' 표의 컬럼 구성·병합셀·주석이 회사·연도마다 달라 범용 파서가 필요하다. "
                "명령서 §3.2 에 따라 이번 단계에서는 파싱 파이프라인을 구축하지 않는다.")
        v.gate("A-1", "임원현황 데이터 확보율", None, 0.90, None,
               "전용 API 미확인으로 미측정")
        return v, pd.DataFrame()

    endpoint = precheck["endpoint"]
    cands = reprt_candidates(as_of)
    v.extra["reprt_candidates"] = [f"{y}/{c}" for y, c in cands]

    have_corp = univ.dropna(subset=["corp_code"]) if "corp_code" in univ.columns else univ.iloc[0:0]
    v.extra["universe_with_corp_code"] = int(len(have_corp))
    if not len(have_corp):
        v.forced_status = "STOP"
        v.limit("유니버스 종목 중 corp_code 매핑에 성공한 종목이 없습니다.")
        return v, pd.DataFrame()

    est = len(have_corp) * len(cands) + CANARY_N * len(cands)
    Log.info(f"[축 A/{as_of}] 호출 예산 추정 최대 {est:,}건 "
             f"(일일 한도 {DART_DAILY_LIMIT:,}, 현재까지 사용 {DART_CALLS['n']:,}건)")
    v.extra["call_budget_estimate"] = est

    # ── 카나리 (P0_CANARY_FIRST) ──────────────────────────────────────────────────────────
    canary = canary_pick(have_corp, "A")
    ccodes = have_corp.set_index("code")["corp_code"].to_dict()
    cres = pmap(lambda t: _fetch_exec_one(endpoint, str(ccodes.get(t[0])), as_of, cands),
                canary, f"[축 A/{as_of}] 카나리")
    cres = [r for r in cres if r]
    n_ok = sum(1 for r in cres if r["status"] == "OK")
    auth_bad = any(r["status"] == "AUTH" for r in cres)
    v.extra["canary"] = {"n": len(canary), "n_with_rows": n_ok,
                         "codes": [c for c, _ in canary],
                         "auth_error": bool(auth_bad)}
    if auth_bad or n_ok == 0:
        v.forced_status = "STOP"
        v.limit(f"카나리 실패: 10종목 중 임원 레코드 확보 {n_ok}건"
                + (", 인증 오류 발생" if auth_bad else "")
                + " — 벌크 실행을 시작하지 않았습니다 (P0_CANARY_FIRST).")
        v.gate("A-1", "임원현황 데이터 확보율", None, 0.90, None, "카나리 실패로 미측정")
        v.api_calls = DART_CALLS["n"]
        return v, pd.DataFrame()
    Log.ok(f"[축 A/{as_of}] 카나리 통과 ({n_ok}/{len(canary)} 종목에서 레코드 확보)")

    # ── 벌크 ──────────────────────────────────────────────────────────────────────────────
    items = list(zip(have_corp["code"].astype(str), have_corp["corp_code"].astype(str)))
    results = pmap(lambda t: _fetch_exec_one(endpoint, t[1], as_of, cands), items,
                   f"[축 A/{as_of}] 임원현황")

    recs: List[dict] = []
    n_cov, n_limit, n_dropped = 0, 0, 0
    used_counter: Counter = Counter()
    for (code, corp), r in zip(items, results):
        if not r:
            continue
        n_dropped += r.get("dropped_future", 0)
        if r["status"] == "LIMIT":
            n_limit += 1
        if r["status"] != "OK":
            continue
        n_cov += 1
        used_counter[r.get("used") or "?"] += 1
        for row in r["rows"]:
            recs.append({"code": code, "corp_code": corp,
                         "corp_name": row.get("corp_name"),
                         "person": norm_person(row.get("nm")),
                         "birth_ym": parse_birth(row.get("birth_ym")),
                         "birth_raw": row.get("birth_ym"),
                         "ofcps": row.get("ofcps"),
                         "rgist_exctv_at": row.get("rgist_exctv_at"),
                         "fte_at": row.get("fte_at"),
                         "chrg_job": row.get("chrg_job"),
                         "hffc_pd": row.get("hffc_pd"),
                         "tenure_end_on": row.get("tenure_end_on"),
                         "rcept_no": row.get("rcept_no")})
    E = pd.DataFrame(recs)
    v.extra["reprt_used_distribution"] = dict(used_counter)
    v.extra["records"] = int(len(E))
    v.extra["pit_dropped_future_records"] = int(n_dropped)
    if n_dropped:
        Log.info(f"[축 A/{as_of}] 접수일자가 기준일보다 늦어 버린 레코드 {n_dropped:,}건 (PIT 강제)")
    if n_limit:
        v.limit(f"DART 일일 호출 한도 도달로 {n_limit:,}종목을 조회하지 못했습니다. "
                f"다음 날 재실행하면 캐시에서 이어받습니다.")

    if len(E):
        E.to_csv(parsed_path("A", as_of, "exec_records.csv"), index=False)

    # ── 게이트 ─────────────────────────────────────────────────────────────────────────────
    a1 = _rate(n_cov, n_univ)
    v.gate("A-1", "유니버스 종목 중 해당 시점 임원 레코드 1건 이상 반환 비율",
           a1, 0.90, _ge(a1, 0.90),
           f"{n_cov:,}/{n_univ:,} (corp_code 매핑 성공 {len(have_corp):,} 기준으로는 "
           f"{_rate(n_cov, len(have_corp))})")

    if len(E):
        n_birth_missing = int(E["birth_ym"].isna().sum())
        a2 = _rate(n_birth_missing, len(E))
        n_month_missing = int(E["birth_ym"].astype(str).str.endswith("-00").sum())
    else:
        a2, n_birth_missing, n_month_missing = None, 0, 0
    v.gate("A-2", "출생년월 결측률 (전체 임원 레코드 기준)", a2, 0.10, _le(a2, 0.10),
           f"결측 {n_birth_missing:,}건 / 전체 {len(E):,}건, "
           f"연도만 있고 월이 없는 레코드 {n_month_missing:,}건")

    # ★ '링크'는 (인물, 종목A, 종목B) 쌍이다. 인물 단위로 세면 한 인물이 만든 수십 개의
    #   쌍이 1건으로 뭉개져 A-4 의 '무작위 200건'이 실제로는 200쌍이 아니게 된다.
    MAX_PAIRS_PER_PERSON = 50
    links = pd.DataFrame()
    n_linked_codes, n_capped, n_multi = 0, 0, 0
    if len(E):
        E2 = E.dropna(subset=["birth_ym"]).copy()
        E2 = E2[E2["person"].astype(str).str.len() >= 2]
        E2["pkey"] = E2["person"].astype(str) + "|" + E2["birth_ym"].astype(str)
        by_person: Dict[str, Dict[str, dict]] = defaultdict(dict)
        for r in E2.to_dict("records"):
            # 한 종목에 같은 인물이 여러 직위로 등장할 수 있다 → 종목당 첫 레코드만
            by_person[r["pkey"]].setdefault(str(r["code"]), r)
        pair_rows: List[dict] = []
        linked_codes: set = set()
        for pkey, per_code in by_person.items():
            codes = sorted(per_code)
            if len(codes) < 2:
                continue
            n_multi += 1
            linked_codes.update(codes)
            pairs = list(itertools.combinations(codes, 2))
            if len(pairs) > MAX_PAIRS_PER_PERSON:
                n_capped += len(pairs) - MAX_PAIRS_PER_PERSON
                pairs = pairs[:MAX_PAIRS_PER_PERSON]
            for ca, cb in pairs:
                a, b = per_code[ca], per_code[cb]
                pair_rows.append({
                    "pkey": pkey, "person": a.get("person"), "birth_ym": a.get("birth_ym"),
                    "code_a": ca, "corp_name_a": a.get("corp_name"), "ofcps_a": a.get("ofcps"),
                    "rgist_a": a.get("rgist_exctv_at"), "rcept_no_a": a.get("rcept_no"),
                    "code_b": cb, "corp_name_b": b.get("corp_name"), "ofcps_b": b.get("ofcps"),
                    "rgist_b": b.get("rgist_exctv_at"), "rcept_no_b": b.get("rcept_no"),
                })
        links = pd.DataFrame(pair_rows)
        n_linked_codes = len(linked_codes)
        a3 = _rate(n_linked_codes, n_univ)
        v.extra["coexec_persons"] = n_multi
        v.extra["coexec_links"] = int(len(links))
        v.extra["coexec_pairs_capped"] = n_capped
    else:
        a3 = None
    if n_capped:
        v.limit(f"겸직 쌍 상한 적용: 한 인물이 {MAX_PAIRS_PER_PERSON}개를 넘는 쌍을 만든 경우 "
                f"초과분 {n_capped:,}쌍을 CSV 에서 잘랐습니다 (A-3 비율 계산에는 영향 없음).")
    v.gate("A-3", "(성명+출생년월) 이 2개 이상 종목에 등장하는 인물이 걸린 종목 비율",
           a3, 0.10, _ge(a3, 0.10),
           f"겸직 인물 {n_multi:,}명, 겸직 링크(종목쌍) {len(links):,}건, "
           f"링크된 종목 {n_linked_codes:,}개")

    # A-4 — 수기 검증용 CSV 만 만들고 판정은 사람이 한다.
    n_sample = 0
    if len(links):
        rnd = random.Random(f"{RANDOM_SEED}:A4:{as_of}")
        idx = list(range(len(links)))
        pick = idx if len(idx) <= MANUAL_SAMPLE_A else rnd.sample(idx, MANUAL_SAMPLE_A)
        smp = links.iloc[sorted(pick)].copy()
        smp["as_of"] = as_of
        smp["verdict_by_human"] = ""
        smp["human_note"] = ""
        out_p = os.path.join(DIR_REPORTS, "manual_check_A_coexec_links.csv")
        header = not os.path.exists(out_p)
        smp.to_csv(out_p, mode="a", index=False, header=header, encoding="utf-8-sig")
        n_sample = int(len(pick))
    v.gate("A-4", "겸직 링크 수기 검증 정확도 (사람이 판정)", None, 0.90, None,
           f"검출된 링크 {len(links):,}건 중 {n_sample:,}건을 "
           f"manual_check_A_coexec_links.csv 로 출력했습니다. 자동 판정하지 않습니다.")

    v.api_calls = DART_CALLS["n"]
    v.limit(f"임원현황은 정기보고서 시점 스냅샷입니다. 사용된 보고서 분포: {dict(used_counter)}")
    v.limit("동명이인 위험: (성명+출생년월) 조합은 고유 식별자가 아닙니다. "
            "A-4 수기 검증이 필요한 이유입니다.")
    return v, links


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  11. 축 B — Google Patents (BigQuery)
# ═════════════════════════════════════════════════════════════════════════════════════════════

BQ_PUBS = "`patents-public-data.patents.publications`"
BQ_GPR = "`patents-public-data.google_patents_research.publications`"


def _sql_guard(sql: str) -> None:
    if re.search(r"SELECT\s+\*", sql, re.I):
        raise ContractViolation(f"§4.3 위반: {_SQL_STAR} 금지 — 필요한 컬럼만 명시할 것")


class BQ:
    """모든 쿼리는 dry_run 으로 먼저 재고, 상한을 넘으면 실행하지 않는다. (§4.3)"""

    def __init__(self):
        from google.cloud import bigquery
        self.bigquery = bigquery
        self.client = bigquery.Client(project=BQ_PROJECT_ID or None, location=BQ_LOCATION)
        self.project = self.client.project
        self.estimates: List[dict] = []

    def dry(self, sql: str, label: str) -> int:
        _sql_guard(sql)
        cfg = self.bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = self.client.query(sql, job_config=cfg)
        n = int(job.total_bytes_processed or 0)
        self.estimates.append({"label": label, "bytes": n, "gb": round(n / 1024 ** 3, 2)})
        Log.info(f"[축 B] dry_run {label}: {n/1024**3:,.2f} GB 스캔 예상 "
                 f"(상한 {BQ_MAX_SCAN_BYTES/1024**3:.0f} GB)")
        return n

    def run(self, sql: str, label: str, dest: Optional[str] = None) -> Tuple[Optional[Any], int]:
        n = self.dry(sql, label)
        if n > BQ_MAX_SCAN_BYTES:
            Log.error(f"[축 B] {label} 스캔량 {n/1024**3:,.1f}GB 가 상한을 초과 — 실행하지 않습니다.")
            return None, n
        kw: Dict[str, Any] = {"maximum_bytes_billed": BQ_MAX_SCAN_BYTES}
        if dest:
            kw.update({"destination": self.bigquery.TableReference.from_string(dest),
                       "write_disposition": "WRITE_TRUNCATE"})
        cfg = self.bigquery.QueryJobConfig(**kw)
        job = self.client.query(sql, job_config=cfg)
        res = job.result()
        return (None if dest else res.to_dataframe()), n


def axis_b_prereq() -> Dict[str, Any]:
    """§4.2 선행 블로커. 준비되지 않았으면 즉시 BLOCKED_PREREQ. 우회하지 않는다."""
    info: Dict[str, Any] = {"library": False, "credentials": False, "project": bool(BQ_PROJECT_ID),
                            "billing_ok": None, "reason": ""}
    try:
        import google.cloud.bigquery  # noqa: F401
        info["library"] = True
    except Exception as e:                                                # noqa: BLE001
        info["reason"] = f"google-cloud-bigquery 임포트 실패({type(e).__name__})"
        return info
    cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    adc = os.path.expanduser(os.path.join("~", ".config", "gcloud",
                                          "application_default_credentials.json"))
    info["credentials"] = bool(cred and os.path.exists(cred)) or os.path.exists(adc)
    if not info["credentials"]:
        info["reason"] = ("GCP 인증정보를 찾지 못했습니다 "
                          "(GOOGLE_APPLICATION_CREDENTIALS 또는 gcloud ADC).")
        return info
    if not BQ_PROJECT_ID:
        info["reason"] = "BQ_PROJECT_ID(=GOOGLE_CLOUD_PROJECT) 가 비어 있습니다."
        return info
    try:
        from google.cloud import bigquery
        c = bigquery.Client(project=BQ_PROJECT_ID, location=BQ_LOCATION)
        cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        c.query(f"SELECT COUNT(1) AS n FROM {BQ_PUBS} WHERE country_code='KR'",
                job_config=cfg)
        info["billing_ok"] = True
    except Exception as e:                                                # noqa: BLE001
        info["billing_ok"] = False
        info["reason"] = (f"BigQuery 접근 실패({type(e).__name__}): {str(e)[:200]} — "
                          f"결제 계정 연결 및 BigQuery API 사용 설정을 확인하세요.")
    return info


def _bq_ensure_dataset(bq: "BQ") -> Optional[str]:
    ds_id = f"{bq.project}.{BQ_DEST_DATASET}"
    try:
        bq.client.get_dataset(ds_id)
        return ds_id
    except Exception:                                                     # noqa: BLE001
        pass
    try:
        d = bq.bigquery.Dataset(ds_id)
        d.location = BQ_LOCATION
        bq.client.create_dataset(d, exists_ok=True)
        Log.ok(f"[축 B] 데이터셋 생성 {ds_id} ({BQ_LOCATION})")
        return ds_id
    except Exception as e:                                                # noqa: BLE001
        Log.warn(f"[축 B] 데이터셋 생성 실패({type(e).__name__}) — 물질화 없이 진행합니다.")
        return None


def _bq_materialize_kr(bq: "BQ", ds_id: str, pub_lo: int, pub_hi: int) -> Optional[str]:
    """KR 공개특허 최소 컬럼만 사용자 데이터셋에 물질화. 이후 쿼리는 이 작은 테이블에서 돈다.
    ★ WHERE 로는 스캔량이 줄지 않는다(파티션 아님). 컬럼 선택만이 비용을 통제한다."""
    tbl = f"{ds_id}.kr_pubs"
    try:
        t = bq.client.get_table(tbl)
        if t.num_rows:
            Log.info(f"[축 B] 물질화 테이블 재사용 {tbl} ({t.num_rows:,}행)")
            CACHE_STAT["hit"] += 1
            return tbl
    except Exception:                                                     # noqa: BLE001
        pass
    CACHE_STAT["miss"] += 1
    sql = f"""
        SELECT
          publication_number,
          family_id,
          publication_date,
          filing_date,
          ARRAY(SELECT a.name FROM UNNEST(assignee_harmonized) AS a) AS assignee_h,
          assignee AS assignee_raw
        FROM {BQ_PUBS}
        WHERE country_code = 'KR'
          AND publication_date BETWEEN {pub_lo} AND {pub_hi}
    """
    _, n = bq.run(sql, "KR 공개특허 물질화", dest=tbl)
    if n > BQ_MAX_SCAN_BYTES:
        return None
    try:
        t = bq.client.get_table(tbl)
        Log.ok(f"[축 B] 물질화 완료 {tbl} ({t.num_rows:,}행)")
    except Exception:                                                     # noqa: BLE001
        pass
    return tbl


def _bq_forward_citations(bq: "BQ", ds_id: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """피인용(forward citation). 후보 경로를 dry_run 으로 재고 상한 안쪽 것만 실행한다.
    ★ 0회 인용과 '데이터 없음' 을 구분할 수 있어야 결측률을 말할 수 있다.
      gpr.cited_by 는 공보마다 행이 있으므로 ARRAY_LENGTH=0 이 '0회'로 구분된다.
      publications.citation 역집계는 0회가 아예 행으로 나오지 않아 구분이 불가능하다."""
    tbl = f"{ds_id}.kr_fwd_cit"
    meta: Dict[str, Any] = {"route": None, "distinguishes_zero": None, "estimates": []}
    try:
        t = bq.client.get_table(tbl)
        if t.num_rows:
            Log.info(f"[축 B] 피인용 테이블 재사용 {tbl} ({t.num_rows:,}행)")
            CACHE_STAT["hit"] += 1
            meta["route"] = "cached"
            meta["distinguishes_zero"] = True
            return tbl, meta
    except Exception:                                                     # noqa: BLE001
        pass
    CACHE_STAT["miss"] += 1

    routes = [
        ("gpr.cited_by", True, f"""
            SELECT r.publication_number AS publication_number,
                   ARRAY_LENGTH(r.cited_by) AS n_forward_citation
            FROM {BQ_GPR} AS r
            WHERE r.publication_number LIKE 'KR-%'
        """),
        ("publications.citation 역집계", False, f"""
            SELECT c.publication_number AS publication_number,
                   COUNT(1) AS n_forward_citation
            FROM {BQ_PUBS} AS p, UNNEST(p.citation) AS c
            WHERE c.publication_number LIKE 'KR-%'
            GROUP BY 1
        """),
    ]
    for label, zero_ok, sql in routes:
        try:
            n = bq.dry(sql, f"피인용 경로 · {label}")
        except Exception as e:                                            # noqa: BLE001
            meta["estimates"].append({"route": label, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        meta["estimates"].append({"route": label, "gb": round(n / 1024 ** 3, 2)})
        if n <= BQ_MAX_SCAN_BYTES:
            _, _n = bq.run(sql, f"피인용 수집 · {label}", dest=tbl)
            meta["route"] = label
            meta["distinguishes_zero"] = zero_ok
            return tbl, meta
    Log.error("[축 B] 피인용 경로가 모두 100GB 상한을 초과 — 실행하지 않고 미측정으로 기록합니다.")
    return None, meta


def run_axis_b(univ: Any, as_of: str, prereq: Dict[str, Any],
               corpcode: Any) -> Tuple[AxisVerdict, Any]:
    """축 B. 다른 축의 산출물을 참조하지 않는다 (P0_INDEPENDENT_AXES)."""
    import pandas as pd
    v = AxisVerdict("B", as_of)
    v.extra["prereq"] = prereq
    v.limit(f"특허는 출원 후 약 {PATENT_PUBLICATION_LAG_MONTHS}개월 뒤 공개된다. "
            f"publication_date 기준 관측 가능한 최신 데이터는 실제 출원 활동보다 약 1.5년 뒤처진다.")
    v.limit("filing_date(출원일)와 publication_date(공개일)를 혼용하지 않았다. "
            "관측 가능성 필터는 publication_date <= as_of, 측정 변수는 filing_date 이다.")

    if not (prereq.get("library") and prereq.get("credentials")
            and prereq.get("project") and prereq.get("billing_ok")):
        v.forced_status = "BLOCKED_PREREQ"
        v.limit(f"선행 블로커: {prereq.get('reason') or 'GCP 계정/결제 미준비'}")
        v.gate("B-1", "최근 5년 KR 특허 1건 이상 보유 비율", None, 0.30, None, "선행 블로커로 미측정")
        return v, pd.DataFrame()

    try:
        bq = BQ()
    except Exception as e:                                                # noqa: BLE001
        v.forced_status = "BLOCKED_PREREQ"
        v.limit(f"BigQuery 클라이언트 생성 실패({type(e).__name__}): {str(e)[:160]}")
        return v, pd.DataFrame()

    ds_id = _bq_ensure_dataset(bq)
    if not ds_id:
        v.forced_status = "BLOCKED_PREREQ"
        v.limit("BigQuery 데이터셋을 만들 수 없어 물질화 경로를 쓸 수 없습니다 "
                "(BigQuery 데이터 편집자 역할 필요).")
        return v, pd.DataFrame()

    lookback = PATENT_LOOKBACK_YEARS
    if budget_left() < 0.4 * TIME_BUDGET_SEC and lookback > 3:
        lookback = 3
        v.limit(f"실행 시간 예산 축소 적용(§8): 축 B 관측 창 {PATENT_LOOKBACK_YEARS}년 → 3년")
    v.extra["lookback_years"] = lookback

    pub_lo = ymd_int(shift_years(min(AS_OF_LIST), -(lookback + 2)))
    pub_hi = ymd_int(max(AS_OF_LIST))
    tbl = _bq_materialize_kr(bq, ds_id, pub_lo, pub_hi)
    if not tbl:
        v.forced_status = "STOP"
        v.limit("KR 공개특허 물질화 쿼리가 100GB 상한을 초과했습니다 — 중단하고 보고합니다.")
        v.extra["dry_run_estimates"] = bq.estimates
        return v, pd.DataFrame()

    cut = ymd_int(as_of)
    file_lo = ymd_int(shift_years(as_of, -lookback))

    # ── 출원인명 집계 (작은 테이블 위에서 도는 저비용 쿼리) ────────────────────────────────
    agg_sql = f"""
        SELECT name AS assignee_name,
               COUNT(DISTINCT publication_number) AS n_publication,
               COUNT(DISTINCT family_id) AS n_family,
               MIN(filing_date) AS first_filing_date,
               MAX(filing_date) AS last_filing_date
        FROM `{tbl}`, UNNEST(assignee_h) AS name
        WHERE publication_date <= {cut}
          AND filing_date BETWEEN {file_lo} AND {cut}
        GROUP BY 1
    """
    A, _ = bq.run(agg_sql, f"출원인 집계 {as_of}")
    if A is None or not len(A):
        v.forced_status = "STOP"
        v.limit("출원인 집계 결과가 비어 있습니다.")
        v.extra["dry_run_estimates"] = bq.estimates
        return v, pd.DataFrame()
    A["nm"] = [norm_corp_name(x) for x in A["assignee_name"]]
    v.extra["distinct_assignees"] = int(A["assignee_name"].nunique())

    # ── §4.5.2 로마자/한글 표기 병존 조사 ─────────────────────────────────────────────────
    lang_sql = f"""
        SELECT
          COUNTIF(EXISTS(SELECT 1 FROM UNNEST(assignee_h) AS n
                         WHERE REGEXP_CONTAINS(n, r'[가-힣]'))) AS n_h_hangul,
          COUNTIF(EXISTS(SELECT 1 FROM UNNEST(assignee_raw) AS n
                         WHERE REGEXP_CONTAINS(n, r'[가-힣]'))) AS n_raw_hangul,
          COUNT(1) AS n_total
        FROM `{tbl}`
        WHERE publication_date <= {cut}
    """
    L, _ = bq.run(lang_sql, f"출원인 표기 언어 분포 {as_of}")
    if L is not None and len(L):
        row = L.iloc[0].to_dict()
        v.extra["assignee_script"] = {
            "harmonized_hangul_rate": _rate(int(row["n_h_hangul"]), int(row["n_total"])),
            "raw_hangul_rate": _rate(int(row["n_raw_hangul"]), int(row["n_total"])),
            "n_total": int(row["n_total"]),
        }
        Log.info(f"[축 B/{as_of}] 출원인 표기 — harmonized 한글 포함 "
                 f"{v.extra['assignee_script']['harmonized_hangul_rate']}, "
                 f"raw 한글 포함 {v.extra['assignee_script']['raw_hangul_rate']}")

    # ── 매칭 키: DART 정식 법인명 우선, 없으면 KRX 종목명 (근거를 기록한다) ─────────────────
    U = univ.copy()
    if corpcode is not None and len(corpcode):
        cc = corpcode.dropna(subset=["code"]).drop_duplicates("code", keep="first")
        U = U.merge(cc[["code", "corp_name"]], on="code", how="left", suffixes=("", "_dart"))
        key_src = ["dart_corp_name" if isinstance(x, str) and x else "krx_name"
                   for x in U.get("corp_name", pd.Series([None] * len(U)))]
        U["match_name"] = [x if isinstance(x, str) and x else y
                           for x, y in zip(U.get("corp_name", pd.Series([None] * len(U))),
                                           U["name"])]
    else:
        key_src = ["krx_name"] * len(U)
        U["match_name"] = U["name"]
        v.limit("DART corpCode 를 쓰지 못해 매칭 키를 KRX 종목명으로 대체했습니다 "
                "(정식 법인명 대비 매칭률이 낮아질 수 있습니다).")
    U["nm"] = [norm_corp_name(x) for x in U["match_name"]]
    v.extra["match_key_source"] = dict(Counter(key_src))

    # ── 카나리 10종목 (P0_CANARY_FIRST) ───────────────────────────────────────────────────
    canary = canary_pick(U, "B")
    cset = {to_code6(c) for c, _ in canary}
    cU = U[U["code"].isin(cset)]
    cx = cU.merge(A[["nm", "n_publication"]], on="nm", how="left")
    n_can_hit = int(cx["n_publication"].notna().sum())
    v.extra["canary"] = {"n": int(len(cU)), "n_exact_hit": n_can_hit,
                         "codes": sorted(cset)}
    Log.info(f"[축 B/{as_of}] 카나리 {len(cU)}종목 중 완전일치 {n_can_hit}건")
    if not len(cU):
        v.forced_status = "STOP"
        v.limit("카나리 종목을 구성하지 못했습니다 — 벌크를 시작하지 않았습니다.")
        return v, pd.DataFrame()

    # ── 완전일치 ──────────────────────────────────────────────────────────────────────────
    Aex = A.sort_values("n_publication", ascending=False).drop_duplicates("nm", keep="first")
    M = U.merge(Aex, on="nm", how="left")
    M["match_method"] = ["exact" if pd.notna(x) else "" for x in M["n_publication"]]

    # ── 퍼지 (별도 플래그. 임계값을 낮춰 매칭률을 부풀리지 않는다) ───────────────────────────
    cand_nm = Aex["nm"].tolist()
    bucket = prefix_bucket(cand_nm)
    fz_name, fz_sim, fz_pub, fz_fam = [], [], [], []
    for nmv, meth in zip(M["nm"], M["match_method"]):
        if meth == "exact" or not nmv or len(nmv) < 2:
            fz_name.append(None); fz_sim.append(None); fz_pub.append(None); fz_fam.append(None)
            continue
        best, bsim = fuzzy_best(nmv, cand_nm, bucket)
        if best is not None:
            r = Aex.iloc[best]
            fz_name.append(r["assignee_name"]); fz_sim.append(round(bsim, 4))
            fz_pub.append(int(r["n_publication"])); fz_fam.append(int(r["n_family"]))
        else:
            fz_name.append(None); fz_sim.append(None); fz_pub.append(None); fz_fam.append(None)
    M["fuzzy_assignee"] = fz_name
    M["fuzzy_sim"] = fz_sim
    M["fuzzy_n_publication"] = fz_pub
    M["fuzzy_n_family"] = fz_fam

    n_univ = int(len(U))
    n_exact = int((M["match_method"] == "exact").sum())
    n_fuzzy = int(M["fuzzy_assignee"].notna().sum())
    b1_exact = _rate(n_exact, n_univ)
    b1_any = _rate(n_exact + n_fuzzy, n_univ)
    v.gate("B-1", f"유니버스 종목 중 최근 {lookback}년 KR 특허 출원(filing) 1건 이상 보유 비율 "
                  f"[완전일치 기준]",
           b1_exact, 0.30, _ge(b1_exact, 0.30),
           f"완전일치 {n_exact:,}종목, 퍼지(≥{FUZZY_THRESHOLD}) 추가 {n_fuzzy:,}종목 "
           f"→ 합산 {b1_any}. 게이트 판정은 완전일치만 사용.")
    v.gate("B-2", "출원인명 완전일치 매핑 성공률 (B-1 통과 종목 대상)",
           _rate(n_exact, n_exact + n_fuzzy) if (n_exact + n_fuzzy) else None, 0.70,
           _ge(_rate(n_exact, n_exact + n_fuzzy) if (n_exact + n_fuzzy) else None, 0.70),
           f"완전일치 {n_exact:,} / (완전일치+퍼지) {n_exact + n_fuzzy:,}")

    # ── B-3 피인용 결측률 ─────────────────────────────────────────────────────────────────
    cit_tbl, cit_meta = _bq_forward_citations(bq, ds_id)
    v.extra["forward_citation"] = cit_meta
    b3 = None
    b3_note = "피인용 경로가 100GB 상한을 넘어 미측정 (추정치는 detail.forward_citation 참조)"
    if cit_tbl:
        # ★ USING 절로 합친 컬럼은 한쪽 별칭으로 다시 참조할 수 없다 → ON 으로 조인한다.
        cit_sql = f"""
            SELECT
              COUNT(1) AS n_pub,
              COUNTIF(c.publication_number IS NULL) AS n_absent
            FROM `{tbl}` AS p
            LEFT JOIN `{cit_tbl}` AS c
              ON p.publication_number = c.publication_number
            WHERE p.publication_date <= {cut}
              AND p.filing_date BETWEEN {file_lo} AND {cut}
        """
        C, _ = bq.run(cit_sql, f"피인용 결측 측정 {as_of}")
        if C is not None and len(C):
            r = C.iloc[0]
            b3 = _rate(int(r["n_absent"]), int(r["n_pub"]))
            b3_note = (f"결측(피인용 원장에 공보 자체가 없음) {int(r['n_absent']):,} / "
                       f"{int(r['n_pub']):,}. 경로={cit_meta.get('route')}, "
                       f"0회인용과 결측 구분 가능={cit_meta.get('distinguishes_zero')}")
            if cit_meta.get("distinguishes_zero") is False:
                v.limit("피인용 경로가 역집계라 '피인용 0회'와 '데이터 없음'을 구분할 수 없습니다. "
                        "B-3 수치는 상한값으로 읽어야 합니다.")
    v.gate("B-3", "피인용 데이터 결측률", b3, 0.30, _le(b3, 0.30), b3_note)

    # B-4 는 두 기준일을 모두 돈 뒤 상위에서 비교한다. 여기서는 B-1 수치를 남긴다.
    v.extra["b1_exact_rate"] = b1_exact
    v.extra["b1_any_rate"] = b1_any
    v.extra["dry_run_estimates"] = bq.estimates

    # 청구항 수 — KR 공보는 전문(claims_localized)이 없다. '가능한 경우'의 실제 답을 측정한다.
    claims_sql = f"""
        SELECT COUNTIF(ARRAY_LENGTH(claims_localized) > 0) AS n_with_claims,
               COUNT(1) AS n_total
        FROM {BQ_PUBS}
        WHERE country_code = 'KR'
    """
    try:
        n_est = bq.dry(claims_sql, "KR 청구항 보유율")
        if n_est <= BQ_MAX_SCAN_BYTES:
            CL, _ = bq.run(claims_sql, "KR 청구항 보유율")
            if CL is not None and len(CL):
                v.extra["kr_claims_availability"] = {
                    "n_with_claims": int(CL.iloc[0]["n_with_claims"]),
                    "n_total": int(CL.iloc[0]["n_total"]),
                    "rate": _rate(int(CL.iloc[0]["n_with_claims"]), int(CL.iloc[0]["n_total"]))}
        else:
            v.limit(f"청구항 수: claims_localized 스캔 추정 {n_est/1024**3:,.0f}GB 로 상한 초과 → "
                    f"측정하지 않았습니다(§4.4 '가능한 경우'에 해당하지 않음).")
    except Exception as e:                                                # noqa: BLE001
        v.limit(f"청구항 보유율 측정 실패({type(e).__name__}).")

    keep = ["code", "name", "match_name", "nm", "assignee_name", "n_publication", "n_family",
            "first_filing_date", "last_filing_date", "match_method",
            "fuzzy_assignee", "fuzzy_sim", "fuzzy_n_publication", "fuzzy_n_family"]
    M[[c for c in keep if c in M.columns]].to_csv(
        parsed_path("B", as_of, "assignee_match.csv"), index=False)
    return v, M


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  12. 축 C — 국민연금 사업장 가입자
# ═════════════════════════════════════════════════════════════════════════════════════════════

NPS_API = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireService/"
NPS_OPS = {
    "basic": "getBassInfoSearch",        # 사업장 기본정보 (월 스냅샷)
    "detail": "getDetailInfoSearch",     # 사업장 상세정보
    "period": "getPdAcctoSttusInfoSearch",  # 기간별(월별) 현황
}
NPS_FIELD_MAP = {
    "wkplNm": "wkpl_name", "bzowrRgstNo": "biz_no", "jnngpCnt": "n_member",
    "crrmmNtcAmt": "notice_amt", "nwAcqzrCnt": "n_acquire", "lssJnngpCnt": "n_loss",
    "wkplRoadNmDtlAddr": "addr", "ldongAddrMgplDgCd": "sido_cd",
    "ldongAddrMgplSggCd": "sgg_cd", "vldtVlKrnNm": "industry",
    "dataCrtYm": "ym", "seq": "seq", "wkplJnngStcd": "join_status",
    "wkplStylDvcd": "wkpl_style", "adptDt": "adopt_date", "scsnDt": "secede_date",
}


_DGK_CACHE: Dict[str, str] = {}


def datagokr_key() -> str:
    """Decoding/Encoding 키 혼동은 공공데이터포털 실패의 1위 원인이다. 자동 감지해 교정한다.
    (페이지마다 호출되므로 경고는 한 번만 낸다.)"""
    if "v" in _DGK_CACHE:
        return _DGK_CACHE["v"]
    from urllib.parse import unquote
    k = (DATA_GO_KR_KEY or "").strip()
    if k and re.search(r"%[0-9A-Fa-f]{2}", k):
        Log.warn("DATA_GO_KR_KEY 가 Encoding 키로 보입니다(%XX 포함). "
                 "이중 인코딩을 막기 위해 디코딩해서 사용합니다. "
                 "가능하면 포털에서 '일반 인증키(Decoding)' 를 복사해 넣으세요.")
        k = unquote(k)
    _DGK_CACHE["v"] = k
    return k


def _nps_page(op: str, params: dict) -> Optional[dict]:
    key = datagokr_key()
    if not key:
        return None
    p = dict(params)
    p.update({"serviceKey": key, "resultType": "json"})
    js = http_json(NPS_API + op, source="datagokr", params=p, tries=3, timeout=40)
    if not isinstance(js, dict):
        return None
    return js


def _nps_ok(js: Any) -> bool:
    """정상 응답만 캐시에 굳힌다. 인증오류·트래픽초과 응답을 굳히면 재실행이 그대로 재생한다."""
    if not isinstance(js, dict):
        return False
    head = (js.get("response", {}) or {}).get("header", {}) or {}
    return str(head.get("resultCode", "")).strip() in ("00", "0")


def _nps_items(js: Optional[dict]) -> Tuple[List[dict], int]:
    if not isinstance(js, dict):
        return [], 0
    body = (js.get("response", {}) or {}).get("body", {}) or {}
    items = body.get("items") or {}
    it = items.get("item") if isinstance(items, dict) else items
    if isinstance(it, dict):
        it = [it]
    if not isinstance(it, list):
        it = []
    try:
        tot = int(body.get("totalCount") or 0)
    except (TypeError, ValueError):
        tot = 0
    return it, tot


def _nps_probe(label: str, op: str, params: dict, info: Dict[str, Any]) -> List[dict]:
    js = _nps_page(op, params)
    items, tot = _nps_items(js)
    head = (js.get("response", {}) or {}).get("header", {}) if isinstance(js, dict) else {}
    info["ops"][label] = {"op": op, "params": {k: v for k, v in params.items()
                                               if k not in ("serviceKey",)},
                          "n_items": len(items), "total_count": tot,
                          "result_code": head.get("resultCode"),
                          "result_msg": str(head.get("resultMsg"))[:120],
                          "fields": sorted(items[0].keys()) if items else []}
    return items


def axis_c_source_check() -> Dict[str, Any]:
    """§5.2 실제 제공 형태를 먼저 확인한다.

    ★ 상세·기간별 오퍼레이션은 seq(사업장 일련번호)가 필수다. seq 없이 찔러 보면 어떤 API든
      실패하므로 '기능 없음'이라는 잘못된 결론이 나온다. 기본정보에서 실제 seq 를 먼저 얻어
      그 seq 로 찔러야 이 프로브가 의미를 갖는다."""
    info: Dict[str, Any] = {"ops": {}, "usable": False, "note": "", "probe_seq": None}
    if not datagokr_key():
        info["note"] = "DATA_GO_KR_KEY 미입력"
        return info
    last_month = _dt.date.today().replace(day=1) - _dt.timedelta(days=1)
    ym = last_month.strftime("%Y%m")

    items = _nps_probe("basic", NPS_OPS["basic"],
                       {"pageNo": 1, "numOfRows": 3, "dataCrtYm": ym}, info)
    if items:
        info["usable"] = True
    seq = None
    for r in items:
        if str(r.get("seq") or "").strip():
            seq = str(r["seq"]).strip()
            break
    info["probe_seq"] = seq

    if seq:
        for label in ("detail", "period"):
            _nps_probe(label, NPS_OPS[label], {"seq": seq, "pageNo": 1, "numOfRows": 10}, info)
    else:
        for label in ("detail", "period"):
            info["ops"][label] = {"op": NPS_OPS[label], "n_items": 0,
                                  "result_msg": "기본정보에서 seq 를 얻지 못해 프로브하지 못함"}

    # 월별 파라미터가 실제로 먹는지 — 과거 월을 요청했을 때 응답의 dataCrtYm 이 그 월인가.
    past_ym = T_PAST[:7].replace("-", "")
    ia = _nps_probe("historic_month", NPS_OPS["basic"],
                    {"pageNo": 1, "numOfRows": 3, "dataCrtYm": past_ym}, info)
    got = [str(r.get("dataCrtYm") or "") for r in ia]
    info["historic_month_probe"] = {
        "ym_requested": past_ym, "n_items": len(ia), "ym_returned": sorted(set(got)),
        "honors_month_param": bool(got) and all(g == past_ym for g in got),
    }
    return info


def _nps_fetch_month(ym: str, max_pages: int = 2000) -> Tuple[List[dict], Dict[str, Any]]:
    """한 달치 전국 사업장 스냅샷. skip-if-exists 로 페이지 단위 재개가 된다.

    ★ 반드시 확인해야 할 것: dataCrtYm 파라미터가 실제로 먹는가.
      이 파라미터를 무시하고 늘 최신월을 돌려주는 API 라면, 과거 월을 요청했다고 믿고
      최신 데이터를 과거에 붙이는 것이 되어 그대로 룩어헤드가 된다.
      요청한 ym 과 응답의 dataCrtYm 이 일치하는 비율을 측정해 함께 돌려준다."""
    rows: List[dict] = []
    page, truncated = 1, False
    n_ym_match, n_ym_seen, total_count = 0, 0, 0
    cb = breaker("datagokr")
    while page <= max_pages and not cb.dead:
        payload = cache_json(f"axis_c/nps_{ym}", f"page_{page:05d}",
                             lambda p=page: _nps_page(NPS_OPS["basic"],
                                                      {"pageNo": p, "numOfRows": 1000,
                                                       "dataCrtYm": ym}),
                             cacheable=_nps_ok)
        items, tot = _nps_items(payload)
        total_count = tot or total_count
        if not items:
            break
        for r in items:
            got_ym = str(r.get("dataCrtYm") or "").strip()
            if got_ym:
                n_ym_seen += 1
                n_ym_match += int(got_ym == ym)
            rec = {NPS_FIELD_MAP[k]: r.get(k) for k in NPS_FIELD_MAP if k in r}
            rec["ym_requested"] = ym
            rec["ym"] = got_ym or None      # 응답이 준 값을 그대로 둔다 (덮어쓰지 않는다)
            rows.append(rec)
        if tot and page * 1000 >= tot:
            break
        page += 1
        if budget_left() < 600:
            Log.warn(f"[축 C] 시간 예산 부족 — {ym} 수집을 {page}페이지에서 중단합니다.")
            truncated = True
            break
    meta = {"ym_requested": ym, "pages": page, "rows": len(rows),
            "total_count_reported": total_count, "truncated": truncated,
            "ym_match_rate": _rate(n_ym_match, n_ym_seen),
            "ym_field_present": bool(n_ym_seen)}
    return rows, meta


def _dart_company_bizno(corp_code: str) -> Optional[dict]:
    js, st = dart_call("company.json", {"corp_code": corp_code})
    if js is None:
        return {"_status": st} if st in ("013",) else None
    return {"_status": st, "bizr_no": js.get("bizr_no"), "jurir_no": js.get("jurir_no"),
            "corp_name": js.get("corp_name"), "adres": js.get("adres")}


def run_axis_c(univ: Any, as_of: str, src_info: Dict[str, Any],
               corpcode: Any) -> Tuple[AxisVerdict, Any]:
    """축 C. 다른 축의 산출물을 참조하지 않는다 (P0_INDEPENDENT_AXES)."""
    import pandas as pd
    v = AxisVerdict("C", as_of)
    v.extra["source_check"] = src_info
    n_univ = int(len(univ))

    if not datagokr_key():
        v.forced_status = "BLOCKED_PREREQ"
        v.limit("DATA_GO_KR_KEY 미입력 — 축 C 를 실행할 수 없습니다.")
        v.gate("C-2", "유니버스 종목 중 사업장 매칭 성공 비율", None, 0.60, None, "선행 블로커로 미측정")
        return v, pd.DataFrame()
    if not src_info.get("usable"):
        v.forced_status = "STOP"
        v.limit(f"국민연금 사업장 API 가 응답하지 않습니다: "
                f"{json.dumps(src_info.get('ops'), ensure_ascii=False)[:400]} "
                f"{src_info.get('note') or ''}")
        v.gate("C-2", "유니버스 종목 중 사업장 매칭 성공 비율", None, 0.60, None, "API 응답 없음")
        return v, pd.DataFrame()
    hm = src_info.get("historic_month_probe") or {}
    if hm.get("n_items") and not hm.get("honors_month_param"):
        v.limit(f"dataCrtYm 파라미터 검증: {hm.get('ym_requested')} 을 요청했는데 응답은 "
                f"{hm.get('ym_returned')} 이었습니다. 과거 월 스냅샷이 제공되지 않는 것으로 "
                f"보이며, 이 경우 과거 시점 매칭·시계열은 시점 정합성이 없습니다.")

    ym = as_of[:7].replace("-", "")
    Log.head(f"[축 C/{as_of}] 사업장 스냅샷 {ym} 수집")
    rows, snap_meta = _nps_fetch_month(ym)
    v.extra["snapshot"] = snap_meta
    if not rows:
        v.forced_status = "STOP"
        v.limit(f"{ym} 사업장 스냅샷을 받지 못했습니다 (과거 월 미제공 가능): {snap_meta}")
        v.gate("C-2", "유니버스 종목 중 사업장 매칭 성공 비율", None, 0.60, None,
               "해당 월 스냅샷 없음")
        return v, pd.DataFrame()
    mr = snap_meta.get("ym_match_rate")
    if snap_meta.get("ym_field_present") and mr is not None and mr < 0.99:
        v.limit(f"요청 월({ym})과 응답 dataCrtYm 의 일치율이 {mr} 입니다. "
                f"dataCrtYm 파라미터가 무시되고 최신월이 반환되고 있다면 과거 시점 측정값은 "
                f"그 시점의 값이 아니며 P0_PIT_UNIVERSE 를 충족하지 않습니다.")
    if not snap_meta.get("ym_field_present"):
        v.limit(f"응답에 dataCrtYm 필드가 없어 반환된 데이터가 요청 월({ym})의 것인지 "
                f"확인할 수 없습니다.")
    if snap_meta.get("truncated"):
        v.limit(f"시간 예산으로 {ym} 스냅샷 수집을 {snap_meta.get('pages')}페이지에서 중단했습니다 "
                f"(총 {snap_meta.get('total_count_reported'):,}건 중 일부만 수집). "
                f"C-2 매칭률은 하한값으로 읽어야 합니다.")
    W = pd.DataFrame(rows)
    for c in ("n_member", "notice_amt", "n_acquire", "n_loss"):
        if c in W.columns:
            W[c] = pd.to_numeric(W[c], errors="coerce")
    v.extra["workplace_rows"] = int(len(W))
    W.to_csv(parsed_path("C", as_of, f"nps_workplaces_{ym}.csv"), index=False)

    # ── C-1 사업자등록번호 자릿수 ──────────────────────────────────────────────────────────
    digits = [len(re.sub(r"\D", "", str(x or ""))) for x in W.get("biz_no", pd.Series(dtype=str))]
    dist = Counter(d for d in digits if d)
    modal = dist.most_common(1)[0][0] if dist else 0
    full = _rate(sum(c for d, c in dist.items() if d == 10), sum(dist.values())) if dist else None
    c1_pass = bool(full is not None and full >= 0.95)
    v.gate("C-1", "사업자등록번호 전체 자릿수(10자리) 제공 여부", "Y" if c1_pass else "N", "Y", c1_pass,
           f"자릿수 분포 {dict(sorted(dist.items()))}, 최빈 {modal}자리, 10자리 비율 {full}")
    if not c1_pass:
        v.limit(f"사업자등록번호가 {modal}자리로만 공개됩니다 → 사업자번호 직결 매칭이 불가능하고 "
                f"상호명 매칭에 의존해야 하므로 매칭 난이도와 오매칭 위험이 급상승합니다.")

    # ── 매칭 키 준비: DART 기업개황의 사업자등록번호(10자리) + 정식 법인명 ──────────────────
    U = univ.copy()
    if corpcode is not None and len(corpcode):
        cc = corpcode.dropna(subset=["code"]).drop_duplicates("code", keep="first")
        U = U.merge(cc[["code", "corp_code", "corp_name"]], on="code", how="left")
    if "corp_code" not in U.columns:
        U["corp_code"] = None
        U["corp_name"] = None
    U["match_name"] = [x if isinstance(x, str) and x else y
                       for x, y in zip(U["corp_name"], U["name"])]
    U["nm"] = [norm_corp_name(x) for x in U["match_name"]]

    bizno_map: Dict[str, str] = {}
    if DART_API_KEY:
        targets = [c for c in U["corp_code"].tolist() if isinstance(c, str) and c]
        Log.info(f"[축 C/{as_of}] DART 기업개황으로 사업자등록번호 확보 시도 {len(targets):,}건")
        got = pmap(lambda cc_: cache_json("axis_c/company", str(cc_),
                                          lambda c=cc_: _dart_company_bizno(str(c))),
                   targets, f"[축 C/{as_of}] 기업개황")
        for cc_, g in zip(targets, got):
            if isinstance(g, dict) and g.get("bizr_no"):
                bizno_map[cc_] = re.sub(r"\D", "", str(g["bizr_no"]))
        v.extra["dart_bizno_coverage"] = _rate(len(bizno_map), max(1, len(targets)))
    else:
        v.limit("DART_API_KEY 가 없어 사업자등록번호 대조 없이 상호명만으로 매칭했습니다.")

    # ── 카나리 (P0_CANARY_FIRST) ──────────────────────────────────────────────────────────
    W["nm"] = [norm_corp_name(x) for x in W.get("wkpl_name", pd.Series([""] * len(W)))]
    W["biz6"] = [re.sub(r"\D", "", str(x or ""))[:6] for x in W.get("biz_no", pd.Series([""] * len(W)))]
    wk_by_nm: Dict[str, List[int]] = defaultdict(list)
    for i, nmv in enumerate(W["nm"].tolist()):
        if nmv and len(nmv) >= 2:
            wk_by_nm[nmv].append(i)
    wk_by_biz6: Dict[str, List[int]] = defaultdict(list)
    for i, b in enumerate(W["biz6"].tolist()):
        if b and len(b) == 6:
            wk_by_biz6[b].append(i)
    wk_names = sorted(wk_by_nm.keys())
    wk_bucket = prefix_bucket(wk_names)

    canary = canary_pick(U, "C")
    cset = {to_code6(c) for c, _ in canary}
    cU = U[U["code"].isin(cset)]
    n_can_hit = sum(1 for nmv in cU["nm"] if nmv in wk_by_nm)
    v.extra["canary"] = {"n": int(len(cU)), "n_name_hit": int(n_can_hit), "codes": sorted(cset)}
    Log.info(f"[축 C/{as_of}] 카나리 {len(cU)}종목 중 상호 완전일치 {n_can_hit}건")
    if n_can_hit == 0:
        v.forced_status = "STOP"
        v.limit("카나리 실패: 10종목 중 사업장 상호 완전일치 0건 — 벌크 매칭을 진행하지 않았습니다.")
        v.gate("C-2", "유니버스 종목 중 사업장 매칭 성공 비율", None, 0.60, None, "카나리 실패")
        v.api_calls = sum(HTTP_STAT["datagokr"].values())
        return v, pd.DataFrame()

    # ── C-2 매칭 ──────────────────────────────────────────────────────────────────────────
    match_rows: List[dict] = []
    for _, r in U.iterrows():
        nmv, code = r["nm"], r["code"]
        biz10 = bizno_map.get(r.get("corp_code") or "", "")
        idxs, method = [], ""
        if biz10 and len(biz10) == 10 and wk_by_biz6:
            idxs = wk_by_biz6.get(biz10[:6], [])
            if idxs:
                method = "bizno6"
        if not idxs and nmv:
            idxs = wk_by_nm.get(nmv, [])
            if idxs:
                method = "exact_name"
        if not idxs and nmv and len(nmv) >= 3:
            bi, _bsim = fuzzy_best(nmv, wk_names, wk_bucket)
            if bi is not None:
                idxs, method = wk_by_nm[wk_names[bi]], "fuzzy_name"
        if not idxs:
            match_rows.append({"code": code, "name": r["name"], "match_name": r["match_name"],
                               "match_method": "", "n_workplace": 0, "n_member_sum": None,
                               "wkpl_names": "", "biz6_set": "", "seq_list": ""})
            continue
        sub = W.iloc[idxs]
        match_rows.append({
            "code": code, "name": r["name"], "match_name": r["match_name"],
            "match_method": method,
            "n_workplace": int(len(sub)),
            "n_member_sum": (int(sub["n_member"].sum()) if "n_member" in sub.columns
                             and sub["n_member"].notna().any() else None),
            "wkpl_names": " | ".join(str(x) for x in sub.get("wkpl_name", [])[:5]),
            "biz6_set": ",".join(sorted({str(x) for x in sub.get("biz6", []) if x})),
            "seq_list": ",".join(str(x) for x in sub.get("seq", [])[:20]),
        })
    MC = pd.DataFrame(match_rows)
    n_matched = int((MC["match_method"] != "").sum())
    n_exact_like = int(MC["match_method"].isin(["bizno6", "exact_name"]).sum())
    c2 = _rate(n_matched, n_univ)
    v.gate("C-2", "유니버스 종목 중 사업장 매칭 성공 비율", c2, 0.60, _ge(c2, 0.60),
           f"완전일치성 매칭(사업자번호6/상호완전일치) {n_exact_like:,}, "
           f"퍼지(≥{FUZZY_THRESHOLD}) 포함 {n_matched:,} / {n_univ:,}. "
           f"방법별 분포 {dict(Counter(MC['match_method']))}")
    MC.to_csv(parsed_path("C", as_of, "workplace_match.csv"), index=False)

    # ── C-3 월별 연속성 ───────────────────────────────────────────────────────────────────
    c3_pass, c3_note, c3_measured = None, "", None
    seqs: List[Tuple[str, str]] = []
    reach_past = 0
    period_ok = bool((src_info.get("ops", {}).get("period", {}) or {}).get("n_items"))
    if not period_ok:
        c3_note = ("기간별 현황 오퍼레이션이 응답하지 않아 월별 시계열 연속성을 측정하지 못했습니다: "
                   f"{src_info.get('ops', {}).get('period')}")
        v.limit(c3_note)
    else:
        for _, r in MC[MC["match_method"] != ""].head(200).iterrows():
            s = str(r["seq_list"]).split(",")[0]
            if s and s != "nan":
                seqs.append((str(r["code"]), s))
        Log.info(f"[축 C/{as_of}] 월별 연속성 표본 {len(seqs):,}개 사업장 조회")
        res = pmap(lambda t: cache_json("axis_c/period", f"{t[1]}",
                                        lambda s=t[1]: _nps_page(NPS_OPS["period"],
                                                                 {"seq": s, "pageNo": 1,
                                                                  "numOfRows": 200}),
                                        cacheable=_nps_ok),
                   seqs, f"[축 C/{as_of}] 기간별 현황")
        months_per: List[int] = []
        target = int(T_PAST[:7].replace("-", ""))
        for js in res:
            items, _ = _nps_items(js)
            yms = sorted({int(str(i.get("dataCrtYm") or 0)) for i in items
                          if str(i.get("dataCrtYm") or "").isdigit()})
            yms = [y for y in yms if y]
            months_per.append(len(yms))
            if yms and min(yms) <= target:
                reach_past += 1
        c3_measured = _rate(reach_past, len(seqs))
        c3_pass = _ge(c3_measured, 0.60)
        med = sorted(months_per)[len(months_per) // 2] if months_per else 0
        c3_note = (f"표본 {len(seqs):,}개 사업장 중 {T_PAST[:7]} 이전까지 월별 기록이 닿는 사업장 "
                   f"{reach_past:,}개 ({c3_measured}). 표본 월 수 중앙값 {med}개월")
        v.extra["c3_months_median"] = med
        v.extra["c3_probe_n"] = len(seqs)
    v.gate("C-3", f"매칭 성공 종목의 월별 시계열이 {T_PAST} 시점까지 연속 존재",
           c3_measured, 0.60, c3_pass, c3_note)

    # ── C-4 다사업장 통합 가능 여부 ────────────────────────────────────────────────────────
    multi = MC[MC["n_workplace"] >= 2]
    n_multi_wkpl = int(len(multi))
    same_biz6 = int(sum(1 for s in multi["biz6_set"] if s and "," not in s))
    if n_multi_wkpl == 0:
        c4 = "N"
        c4_note = "매칭된 종목 중 복수 사업장을 가진 사례가 없어 통합 가능 여부를 판정할 수 없습니다."
    else:
        share = same_biz6 / n_multi_wkpl
        c4 = "Y" if share >= 0.90 else ("부분" if share >= 0.50 else "N")
        c4_note = (f"복수 사업장 종목 {n_multi_wkpl:,}개 중 사업장들의 사업자번호 앞 6자리가 "
                   f"동일한 경우 {same_biz6:,}개 ({share:.2%}). "
                   f"6자리는 마스킹된 값이므로 동일해도 동일 법인임을 보장하지 않습니다.")
    v.gate("C-4", "다사업장 법인의 사업장 통합 가능 여부 (Y/N/부분)", c4, "Y",
           True if c4 == "Y" else (None if c4 == "부분" else False), c4_note)
    if c4 != "Y":
        v.limit("다사업장 통합: 마스킹된 사업자번호로는 본사·공장·지점을 한 법인으로 확정 결합할 수 "
                "없습니다. 상호 접두 규칙에 의존하면 오결합이 발생합니다.")

    # ── C-5 수기 검증 샘플 ────────────────────────────────────────────────────────────────
    hit = MC[MC["match_method"] != ""]
    n_sample = 0
    if len(hit):
        rnd = random.Random(RANDOM_SEED)
        idx = list(range(len(hit)))
        pick = idx if len(idx) <= MANUAL_SAMPLE_C else rnd.sample(idx, MANUAL_SAMPLE_C)
        smp = hit.iloc[sorted(pick)].copy()
        smp["as_of"] = as_of
        smp["verdict_by_human"] = ""
        smp["human_note"] = ""
        out_p = os.path.join(DIR_REPORTS, "manual_check_C_workplace_match.csv")
        header = not os.path.exists(out_p)
        smp.to_csv(out_p, mode="a", index=False, header=header, encoding="utf-8-sig")
        n_sample = int(len(pick))
    v.gate("C-5", "사업장 매칭 수기 검증 정확도 (사람이 판정)", None, 0.90, None,
           f"샘플 {n_sample:,}건을 manual_check_C_workplace_match.csv 로 출력했습니다. "
           f"자동 판정하지 않습니다.")

    v.limit("동명 법인 위험: 비상장사와 상장사가 동일·유사 상호를 갖는 경우 상호 매칭은 "
            "오매칭을 만듭니다. C-5 수기 검증이 필요한 이유입니다.")
    v.api_calls = sum(HTTP_STAT["datagokr"].values())
    return v, MC


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  13. 판정표 · 요약 리포트
# ═════════════════════════════════════════════════════════════════════════════════════════════

STATUS_ORDER = {"GO": 0, "PENDING_MANUAL": 1, "STOP": 2, "BLOCKED_PREREQ": 3}

# §8 실행 시간 예산 축소 1단계: T_PAST 를 포기하고 T_NOW 커버리지만 확인한다.
# 축소를 적용했다면 반드시 판정표의 known_limitations 에 남긴다.
SKIP_PAST_RESERVE_SEC = 900


def skipped_verdict(axis: str, as_of: str, run_meta: Dict[str, Any]) -> AxisVerdict:
    v = AxisVerdict(axis, as_of)
    v.forced_status = "STOP"
    msg = (f"실행 시간 예산 축소(§8 1단계) 적용: 남은 예산이 {budget_left():.0f}초여서 "
           f"{as_of}({'T_PAST' if as_of == T_PAST else as_of}) 시점 수집을 생략했습니다. "
           f"이 축의 과거 깊이는 측정되지 않았습니다.")
    v.limit(msg)
    if msg not in run_meta.setdefault("reductions", []):
        run_meta["reductions"].append(msg)
    Log.warn(f"[축 {axis}/{as_of}] {msg}")
    return v


def should_run(as_of: str) -> bool:
    return as_of == T_NOW or budget_left() > SKIP_PAST_RESERVE_SEC


def worse(a: str, b: str) -> str:
    return a if STATUS_ORDER.get(a, 9) >= STATUS_ORDER.get(b, 9) else b


def write_verdict(verdicts: List[AxisVerdict], run_meta: Dict[str, Any]) -> None:
    payload = {
        "phase": "PHASE_0_ALTDATA_3AXIS_VALIDATION",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "contracts": CONTRACTS,
        "run": run_meta,
        "axes": [v.to_dict() for v in verdicts],
        "axis_overall": {},
    }
    by_axis: Dict[str, List[AxisVerdict]] = defaultdict(list)
    for v in verdicts:
        by_axis[v.axis].append(v)
    for ax, vs in by_axis.items():
        st = "GO"
        for v in vs:
            st = worse(st, v.status)
        payload["axis_overall"][ax] = {
            "status": st,
            "rule": "두 기준일 중 나쁜 쪽 기준 (§2.2)",
            "by_as_of": {v.as_of: v.status for v in vs},
        }
    atomic_write_text(os.path.join(DIR_REPORTS, "phase0_verdict.json"),
                      json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    csv_p = os.path.join(DIR_REPORTS, "phase0_verdict.csv")
    with open(csv_p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["axis", "as_of", "axis_status", "gate_id", "criterion",
                    "measured", "threshold", "pass", "note", "api_calls_used", "runtime_sec"])
        for v in verdicts:
            d = v.to_dict()
            if not d["gates"]:
                w.writerow([v.axis, v.as_of, d["status"], "", "", "", "", "", "",
                            d["api_calls_used"], d["runtime_sec"]])
            for g in d["gates"]:
                w.writerow([v.axis, v.as_of, d["status"], g["id"], g["criterion"],
                            g["measured"], g["threshold"], g["pass"], g["note"],
                            d["api_calls_used"], d["runtime_sec"]])
    Log.ok(f"판정표 저장: {csv_p}")


def write_summary(verdicts: List[AxisVerdict], run_meta: Dict[str, Any]) -> None:
    """사실과 숫자만 기록한다. 해석이나 전략 제안을 쓰지 않는다. (§7.3)"""
    L: List[str] = []
    L.append("# PHASE 0 — 대체데이터 3축 수집 가능성 검증 결과")
    L.append("")
    L.append(f"- 생성 시각: {_dt.datetime.now().isoformat(timespec='seconds')}")
    L.append(f"- 총 실행 시간: {run_meta.get('runtime_sec')}초")
    L.append(f"- 기준일: {T_NOW} (T_NOW), {T_PAST} (T_PAST)")
    L.append(f"- 유니버스: 시가총액 하위 {UNIVERSE_SIZE}종목")
    L.append(f"- 캐시 히트/미스: {run_meta.get('cache_hit')}/{run_meta.get('cache_miss')}")
    L.append("")
    L.append("## 유니버스")
    L.append("")
    L.append("| 기준일 | 소스 | 상장 총수 | 선택 | 순위 구간 | 플래그 해당 | PIT |")
    L.append("|---|---|---|---|---|---|---|")
    for a, m in (run_meta.get("universe") or {}).items():
        rng = m.get("marcap_rank_range") or ["", ""]
        L.append(f"| {a} | {m.get('source')} | {m.get('listed_total')} | {m.get('n_selected')} | "
                 f"{rng[0]}~{rng[1]} | {m.get('excluded_if_filtered')} | "
                 f"{'Y' if m.get('pit_ok') else 'N'} |")
    L.append("")
    for a, m in (run_meta.get("universe") or {}).items():
        for n in m.get("notes", []):
            L.append(f"- ({a}) {n}")
    L.append("")

    by_axis: Dict[str, List[AxisVerdict]] = defaultdict(list)
    for v in verdicts:
        by_axis[v.axis].append(v)
    names = {"A": "축 A — DART 임원현황", "B": "축 B — Google Patents (BigQuery)",
             "C": "축 C — 국민연금 사업장 가입자"}
    for ax in ("A", "B", "C"):
        vs = by_axis.get(ax) or []
        st = "GO"
        for v in vs:
            st = worse(st, v.status)
        L.append(f"## {names[ax]} — 판정 **{st}**")
        L.append("")
        L.append("두 기준일 중 나쁜 쪽 기준. 기준일별: "
                 + ", ".join(f"{v.as_of}={v.status}" for v in vs))
        L.append("")
        L.append("| 기준일 | 게이트 | 기준 | 측정값 | 임계 | 통과 | 비고 |")
        L.append("|---|---|---|---|---|---|---|")
        for v in vs:
            for g in v.gates:
                p = {True: "PASS", False: "FAIL", None: "PENDING/미측정"}[g.passed]
                note = str(g.note).replace("|", "/").replace("\n", " ")
                L.append(f"| {v.as_of} | {g.gid} | {g.criterion} | {g.measured} | "
                         f"{g.threshold} | {p} | {note} |")
        L.append("")
        lims = []
        for v in vs:
            for x in v.limits:
                if x not in lims:
                    lims.append(x)
        if lims:
            L.append("알려진 한계:")
            L.append("")
            for x in lims:
                L.append(f"- {x}")
            L.append("")
        L.append("API 호출 수: " + ", ".join(f"{v.as_of}={v.api_calls}" for v in vs))
        L.append("")
    red = run_meta.get("reductions") or []
    L.append("## 적용된 범위 축소 (§8)")
    L.append("")
    if red:
        for x in red:
            L.append(f"- {x}")
    else:
        L.append("- 없음")
    L.append("")
    L.append("## 수기 검증 대기")
    L.append("")
    L.append("- `manual_check_A_coexec_links.csv` — 겸직 링크 (게이트 A-4). 사람이 판정한다.")
    L.append("- `manual_check_C_workplace_match.csv` — 사업장 매칭 (게이트 C-5). 사람이 판정한다.")
    L.append("")
    L.append("## 계약 자기검사")
    L.append("")
    for k, val in (run_meta.get("contract_check", {}).get("checks") or {}).items():
        L.append(f"- {k}: {val}")
    for x in (run_meta.get("contract_check", {}).get("violations") or []):
        L.append(f"- ⚠ {x}")
    atomic_write_text(os.path.join(DIR_REPORTS, "phase0_summary.md"), "\n".join(L) + "\n")
    Log.ok(f"요약 리포트 저장: {os.path.join(DIR_REPORTS, 'phase0_summary.md')}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
#  14. 메인
# ═════════════════════════════════════════════════════════════════════════════════════════════

def main() -> int:
    Log.head("PHASE 0 — 대체데이터 3축 수집 가능성 검증 v1.0")
    Log.info(f"PROJECT_ROOT = {PROJECT_ROOT}")
    Log.info(f"캐시 = {CACHE_ROOT}")
    assert_disk_space()

    src, origin = _read_self_source()
    cc = verify_contracts(src, origin)
    for k, val in cc["checks"].items():
        (Log.ok if val == "PASS" else Log.warn)(f"계약 {k}: {val}")
    if any(val == "FAIL" for val in cc["checks"].values()):
        for x in cc["violations"]:
            Log.error(x)
        raise ContractViolation("계약 자기검사 실패 — 데이터 수집을 시작하지 않습니다.")
    for x in cc["violations"]:
        Log.warn(x)

    Log.head("의존성 확인")
    deps = ensure_packages([
        ("requests", "requests"), ("pandas", "pandas"), ("numpy", "numpy"),
        ("FinanceDataReader", "finance-datareader"), ("pykrx", "pykrx"),
        ("google.cloud.bigquery", "google-cloud-bigquery"),
        ("pyarrow", "pyarrow"), ("db_dtypes", "db-dtypes"),
    ])
    Log.info("의존성 상태: " + ", ".join(f"{k}={'OK' if val else 'MISSING'}"
                                     for k, val in deps.items()))
    if not deps.get("pandas") or not deps.get("requests"):
        raise RuntimeError("pandas / requests 없이는 진행할 수 없습니다.")

    run_meta: Dict[str, Any] = {"contract_check": cc, "project_root": PROJECT_ROOT,
                                "deps": deps, "universe": {}, "reductions": []}

    # ── 유니버스 ──────────────────────────────────────────────────────────────────────────
    Log.head("유니버스 구성 (PIT)")
    universes: Dict[str, Any] = {}
    for a in AS_OF_LIST:
        u, m = build_universe(a)
        universes[a] = u
        run_meta["universe"][a] = m
        for n in m.get("notes", []):
            Log.warn(f"[{a}] {n}")

    # ── 공용 리소스 ───────────────────────────────────────────────────────────────────────
    Log.head("DART corpCode 매핑 (축 A/B/C 의 공통 입력)")
    corpcode, cc_info = fetch_dart_corpcode()
    run_meta["corpcode"] = cc_info

    verdicts: List[AxisVerdict] = []

    # ── 축 A ─────────────────────────────────────────────────────────────────────────────
    Log.head("축 A — DART 임원현황: 선행 확인 (§3.2)")
    try:
        pre_a = axis_a_precheck()
        Log.info(f"[축 A] 전용 API 존재 = {pre_a.get('dedicated_api')} "
                 f"(엔드포인트 {pre_a.get('endpoint')}), 프로브 {pre_a.get('probe')}")
    except Exception as e:                                                # noqa: BLE001
        pre_a = {"dedicated_api": False, "error": f"{type(e).__name__}: {e}"}
        Log.error(f"[축 A] 선행 확인 실패: {e}")
    for a in AS_OF_LIST:
        if not should_run(a):
            verdicts.append(skipped_verdict("A", a, run_meta))
            continue
        Log.head(f"축 A — {a}")
        try:
            u2, mi = map_universe_to_corp(universes[a], corpcode)
            v, _links = run_axis_a(u2, a, pre_a, mi)
        except Exception as e:                                            # noqa: BLE001
            v = AxisVerdict("A", a)
            v.forced_status = "STOP"
            v.limit(f"축 A 실행 중 예외: {type(e).__name__}: {e}")
            Log.error(f"[축 A/{a}] {traceback.format_exc(limit=6)}")
        verdicts.append(v)
        Log.info(f"[축 A/{a}] 판정 {v.status}")

    # ── 축 B ─────────────────────────────────────────────────────────────────────────────
    Log.head("축 B — Google Patents: 선행 블로커 확인 (§4.2)")
    try:
        pre_b = axis_b_prereq()
        Log.info(f"[축 B] 선행 확인: {pre_b}")
    except Exception as e:                                                # noqa: BLE001
        pre_b = {"library": False, "reason": f"{type(e).__name__}: {e}"}
    b_vs: List[AxisVerdict] = []
    for a in AS_OF_LIST:
        if not should_run(a):
            sv = skipped_verdict("B", a, run_meta)
            b_vs.append(sv)
            verdicts.append(sv)
            continue
        Log.head(f"축 B — {a}")
        try:
            v, _m = run_axis_b(universes[a], a, pre_b, corpcode)
        except Exception as e:                                            # noqa: BLE001
            v = AxisVerdict("B", a)
            v.forced_status = "STOP"
            v.limit(f"축 B 실행 중 예외: {type(e).__name__}: {e}")
            Log.error(f"[축 B/{a}] {traceback.format_exc(limit=6)}")
        b_vs.append(v)
        verdicts.append(v)
        Log.info(f"[축 B/{a}] 판정 {v.status}")
    # B-4 — T_PAST 시점에도 B-1 이 성립하는지 (백필 깊이)
    past = next((x for x in b_vs if x.as_of == T_PAST), None)
    now = next((x for x in b_vs if x.as_of == T_NOW), None)
    if past is not None:
        r_past = past.extra.get("b1_exact_rate")
        past.gate("B-4", f"{T_PAST} 시점에도 B-1 성립 (백필 깊이)", r_past, 0.30,
                  _ge(r_past, 0.30),
                  f"{T_NOW} 시점 B-1={now.extra.get('b1_exact_rate') if now else None}")

    # ── 축 C ─────────────────────────────────────────────────────────────────────────────
    Log.head("축 C — 국민연금 사업장: 제공 형태 확인 (§5.2)")
    try:
        pre_c = axis_c_source_check()
        Log.info("[축 C] 오퍼레이션 프로브: "
                 + json.dumps(pre_c.get("ops", {}), ensure_ascii=False)[:400])
    except Exception as e:                                                # noqa: BLE001
        pre_c = {"usable": False, "note": f"{type(e).__name__}: {e}"}
    for a in AS_OF_LIST:
        if not should_run(a):
            verdicts.append(skipped_verdict("C", a, run_meta))
            continue
        Log.head(f"축 C — {a}")
        try:
            v, _mc = run_axis_c(universes[a], a, pre_c, corpcode)
        except Exception as e:                                            # noqa: BLE001
            v = AxisVerdict("C", a)
            v.forced_status = "STOP"
            v.limit(f"축 C 실행 중 예외: {type(e).__name__}: {e}")
            Log.error(f"[축 C/{a}] {traceback.format_exc(limit=6)}")
        verdicts.append(v)
        Log.info(f"[축 C/{a}] 판정 {v.status}")

    # ── 산출 ─────────────────────────────────────────────────────────────────────────────
    Log.head("판정표 · 요약 리포트")
    if elapsed() > TIME_BUDGET_SEC:
        for v in verdicts:
            v.limit(f"실행 시간이 예산({TIME_BUDGET_SEC}초)을 초과했습니다 "
                    f"(실제 {elapsed():.0f}초).")
    run_meta.update({
        "runtime_sec": round(elapsed(), 1),
        "cache_hit": int(CACHE_STAT["hit"]),
        "cache_miss": int(CACHE_STAT["miss"]),
        "cache_hit_rate": round(CACHE_STAT["hit"] / max(1, CACHE_STAT["hit"] + CACHE_STAT["miss"]), 4),
        "http": {k: dict(v_) for k, v_ in HTTP_STAT.items()},
        "dart_calls": int(DART_CALLS["n"]),
    })
    write_verdict(verdicts, run_meta)
    write_summary(verdicts, run_meta)

    Log.head("최종 요약")
    by_axis: Dict[str, List[AxisVerdict]] = defaultdict(list)
    for v in verdicts:
        by_axis[v.axis].append(v)
    for ax in ("A", "B", "C"):
        vs = by_axis.get(ax) or []
        st = "GO"
        for v in vs:
            st = worse(st, v.status)
        detail = ", ".join(f"{v.as_of}:{v.status}" for v in vs)
        Log.info(f"축 {ax}: {st}   ({detail})")
    Log.info(f"총 소요 {elapsed():.0f}초 · DART 호출 {DART_CALLS['n']:,}건 · "
             f"캐시 히트율 {run_meta['cache_hit_rate']:.1%}")
    for k, v_ in HTTP_STAT.items():
        Log.info(f"HTTP[{k}] " + " ".join(f"{a}={b}" for a, b in sorted(v_.items())))
    Log.ok(f"산출물 디렉터리: {DIR_REPORTS}")
    return 0


def _in_notebook() -> bool:
    try:
        return get_ipython().__class__.__name__ in (          # noqa: F821
            "ZMQInteractiveShell", "TerminalInteractiveShell")
    except NameError:
        return False


if __name__ == "__main__":
    # ★ 이 파일과 노트북 셀은 한 글자도 다르지 않다. 노트북에서는 sys.exit 가 SystemExit
    #   트레이스백으로 보이므로, 노트북일 때만 종료코드를 삼킨다.
    _exit_code = main()
    if not _in_notebook():
        sys.exit(_exit_code)
