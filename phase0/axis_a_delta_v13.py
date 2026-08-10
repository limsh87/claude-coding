#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 0 — 축 A-Δ 재측정 v1.3   (캐시 재사용 · 로컬 JupyterLab 전용 · LIVE 전용)          ║
# ║                                                                                          ║
# ║  이 실행의 유일한 질문:  분기마다 겸직 링크가 실제로 몇 개나 생기고 사라지는가?              ║
# ║                                                                                          ║
# ║  v1.2 에서 축 A 본체(A-1 커버리지 / A-2 식별자 / A-3 그래프 확대효과)는 이미 확인되었다.    ║
# ║  이 파일은 그것을 다시 재지 않는다. 룩어헤드로 무효가 된 A-Δ 만 고쳐서 다시 잰다.           ║
# ║                                                                                          ║
# ║  ── v1.2 결함 → v1.3 수정 ──────────────────────────────────────────────────────────────  ║
# ║   #1  as_of 에 실행일이 들어가 PIT 필터가 무력화됨 (S1 최종접수일 20260731, 폐기 0건)      ║
# ║       → as_of = 해당 보고서의 법정 제출기한. 스냅샷마다 폐기 건수를 강제 출력하고,          ║
# ║         필터 후 최종접수일 > as_of 이면 그 자리에서 예외를 던진다.        (§3.1)           ║
# ║   #2  분기말이 휴장일이면 시총이 전부 0 (S3 2025-12-31 → 시총>0 0종목)                     ║
# ║       → 시총>0 종목수로 거래일 여부를 실측하여 직전 거래일까지 되짚는다.  (§3.2)           ║
# ║   #3  측정대상 0종목인데 2,789종목 수집 강행 → 예산 낭비                                   ║
# ║       → 유니버스 4개를 전부 확정한 뒤에야 수집에 진입한다.               (§3.3)           ║
# ║   #4  corpCode.xml 파싱에 231초 → 파싱 '결과'를 캐시. 히트면 XML 을 열지 않는다. (§2.3)    ║
# ║   #5  캐시가 /content 에 있어 세션 종료 시 소멸 → 로컬 SSD 강제, 드라이브는 콜드백업. (§2)  ║
# ║                                                                                          ║
# ║  붙여넣기: JupyterLab 셀 하나에 그대로. 또는  python axis_a_delta_v13.py                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 0. 자격증명 · 실행 경로   ─ 여기만 채우면 된다
# ══════════════════════════════════════════════════════════════════════════════════════════
#
#  DART_API_KEY  ─ 금융감독원 전자공시 OpenDART 인증키 (40자 16진 문자열)
#     발급: https://opendart.fss.or.kr/  →  [인증키 신청/관리] → [인증키 신청]
#           이메일 인증 → 즉시 발급. 개인 무료. 일 20,000건 호출 한도.
#     확인: https://opendart.fss.or.kr/mng/apiUsageStatus.do  (당일 소진량)
#     ※ 이 실행이 쓰는 엔드포인트는 exctvSttus(임원 현황) 하나뿐이다.
#
DART_API_KEY = ""

#  KRX_ID / KRX_PW ─ KRX 정보데이터시스템 마켓플레이스 계정 (pykrx 인증 경로용)
#     발급: http://data.krx.co.kr/  →  우측 상단 [로그인] → [회원가입]
#           이메일 인증 후 즉시 사용. 무료.
#     비워도 된다 — 시총 조회는 비인증 경로로도 동작한다. 다만 2025-12 KRX 인증 정책
#     변경 이후 비인증 경로는 간헐적으로 429/HTML 을 돌려준다.
#     ★ 값을 넣든 안 넣든, pykrx 는 이 값들이 os.environ 에 들어간 '뒤에' import 된다.
#       (v1.2 의 KRX_ENV_TOO_LATE 경고 원인. §8 — 아래 _import_pykrx_after_env() 가 강제한다)
#
KRX_ID = ""
KRX_PW = ""

#  PROJECT_ROOT ─ 로컬 SSD 경로. /content 계열이면 예외를 던지고 즉시 중단한다.
#                 (P0_LOCAL_ROOT_ONLY — v1.2 의 WAIVED 허용은 철회되었다)
PROJECT_ROOT = "~/quant/phase0"

#  GDRIVE_BACKUP_DIR ─ 콜드 백업 전용 디렉터리. 작업은 언제나 로컬에서 한다.
#     Google Drive for desktop / rclone 등으로 마운트된 경로를 넣는다. 비우면 백업 생략.
#     예) "~/Google Drive/My Drive/quant_backup"   또는  "/mnt/gdrive/quant_backup"
GDRIVE_BACKUP_DIR = ""

#  예상 신규 API 호출이 5,000건을 넘으면 스크립트가 인벤토리만 출력하고 멈춘다 (P0_CACHE_FIRST).
#  보고를 읽고 진행하기로 했다면 이 값을 True 로 바꾸고 셀을 다시 실행한다.
CONFIRM_LARGE_COLLECTION = False

#  KONEX 포함 여부. 기본 False(=KOSPI+KOSDAQ).
#     근거: 명세 §6 P0_LIVE_ONLY 가 요구하는 '전 상장사 노드 수 2,700 내외' 및 §2.2 의
#     '필요 ~2,760건' 은 KONEX 제외 모수와 일치한다. ALL(=KONEX 포함)은 2,900종목대이며,
#     KONEX 는 시총이 극단적으로 작아 '시총 하위 1,000종목'을 통째로 점유해 측정 대상을
#     바꿔버린다. 이 선택은 판정표 methodology 에 기록된다.
INCLUDE_KONEX = False

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 1. 계약 (§6) — 이 실행이 스스로에게 거는 제약. 위반하면 조용히 넘어가지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
CONTRACTS = {
    "P0_LOCAL_ROOT_ONLY":      "/content 계열 감지 시 예외 발생 후 중단. WAIVED 허용하지 않는다",
    "P0_PIT_STRICT_DELTA":     "as_of 는 실행일이 아니다. 스냅샷별 PIT 폐기 건수를 반드시 출력",
    "P0_EMPTY_UNIVERSE_GUARD": "시총>0 종목 100 미만이면 수집 진입 금지",
    "P0_CACHE_FIRST":          "수집 전 캐시 인벤토리 출력. 예상 신규 호출 5,000건 초과 시 대기",
    "P0_NO_STRATEGY":          "팩터·시그널·수익률 연산 금지",
    "P0_GRAPH_FULL_MEASURE_SUB": "그래프는 전 상장사, 측정은 하위 1,000종목",
    "P0_FAIL_LOUD":            "결측은 결측으로. 보간·추정 금지",
    "P0_NO_THRESHOLD_EDIT":    "임계값 frozen. 실행 중 변경 금지",
    "P0_LIVE_ONLY":            "합성 데이터 경로 금지. 전 상장사 노드 수를 로그에 출력",
    "NO_KNOWN_DEAD_CALL":      "pykrx.get_index_portfolio_deposit_file('1028') 금지",
}

# ── 임계값 (frozen). P0_NO_THRESHOLD_EDIT — 실행 중 어떤 이유로도 바꾸지 않는다. ────────────
#    아래 해시는 이 세 값에서 파생된다. 값을 고치면 해시가 어긋나 실행이 중단된다.
GATE_THRESHOLDS = {"AD1_born_ratio_mean": 0.05, "AD2_born_total_median": 50, "A5_legacy": 600}
GATE_THRESHOLDS_SHA256 = "5377b9db1fab287d1417eec46f87c39e84a10db6b81f84bc64d087ffba3c0d35"

KNOWN_LIMITATIONS = [
    "AΔ-1=0.05, AΔ-2=50, A-5=600 은 경험적 근거 없이 설정된 임계값이다.",
    "게이트 미달은 '전략 불가'를 뜻하지 않는다. 실측값을 근거로 임계를 재설정하는 것은 "
    "다음 단계의 판단이며, 이번 실행에서는 임계를 변경하지 않았다(P0_NO_THRESHOLD_EDIT).",
    "관측시점 정렬(A)을 채택했다. 유니버스(시총 하위 1,000종목)는 스냅샷 기준일에, "
    "임원 데이터는 법정 제출기한(as_of)에 정렬된다 — 두 축의 기준일이 다르다. "
    "as_of 시점에는 기준일 대비 상장·폐지·시총순위 변동이 이미 발생했을 수 있다.",
    "정정공시로 rcept_dt 가 as_of 를 넘는 레코드는 '폐기'된다. DART API 는 최신 리비전만 "
    "돌려주므로 정정 이전의 원본 내용을 복원할 수 없다. 해당 기업은 그 스냅샷에서 "
    "임원 데이터 결측으로 남는다(보간하지 않음 — P0_FAIL_LOUD).",
    "인물 동일성은 (성명, 출생년월) 로만 판정한다. 동명이인이 같은 출생년월을 가지면 "
    "실재하지 않는 엣지가 생성된다. 진단표에 다수 종목 겸직자 상위 목록을 함께 출력한다.",
    "출생년월 결측 레코드는 엣지 생성에서 제외된다. 제외 건수를 스냅샷별로 기록한다.",
    "edge_born/edge_died 는 '교집합 종목에 한쪽 끝이라도 걸친 엣지'를 센다(§4.1 의 "
    "'상대 노드가 측정 대상 밖이어도 엣지 유지'). 상대 노드의 상장/폐지가 엣지 생성·소멸로 "
    "보일 수 있어, 양끝이 두 스냅샷 모두에 상장된 경우만 센 보조 수치를 함께 기록한다.",
]

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 2. 표준 라이브러리 (서드파티는 자격증명 주입 이후에만 import 한다)
# ══════════════════════════════════════════════════════════════════════════════════════════
import os
import re
import io
import sys
import json
import time
import errno
import random
import shutil
import hashlib
import zipfile
import tarfile
import datetime as _dt
import itertools
import threading
import subprocess
import importlib.util
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

RUN_STARTED = _dt.datetime.now()
SEED = 20260810
random.seed(SEED)


class ContractViolation(RuntimeError):
    """계약 위반. 이 예외는 절대 삼키지 않는다."""


class DiskFull(RuntimeError):
    """ENOSPC. 즉시 실패한다 — 포맷 재시도 금지 (§8)."""


class HardStop(RuntimeError):
    """예산 소진·서킷브레이커·인증 실패 등 계속할 수 없는 상태."""


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 3. 실행 경로 검사 (P0_LOCAL_ROOT_ONLY)
# ══════════════════════════════════════════════════════════════════════════════════════════
_FORBIDDEN_ROOT_PARTS = ("/content", "/gdrive", "/drive/mydrive")


def resolve_project_root(raw: str) -> Path:
    """/content 계열이면 예외를 던진다. v1.2 의 WAIVED 우회는 철회되었다."""
    root = Path(os.path.expanduser(str(raw or ""))).resolve()
    low = str(root).lower().replace("\\", "/")
    for bad in _FORBIDDEN_ROOT_PARTS:
        if low == bad or low.startswith(bad + "/"):
            raise ContractViolation(
                f"P0_LOCAL_ROOT_ONLY 위반: PROJECT_ROOT={root}\n"
                f"  '{bad}' 계열은 세션 종료와 함께 소멸한다. v1.2 에서 캐시를 통째로 잃은 원인이다.\n"
                f"  로컬 SSD 경로로 바꾸고 다시 실행할 것 (예: ~/quant/phase0).\n"
                f"  이 계약에는 WAIVED 가 없다.")
    if "google.colab" in sys.modules:
        raise ContractViolation(
            "P0_LOCAL_ROOT_ONLY 위반: Colab 런타임이 감지되었다. 로컬 JupyterLab 에서 실행할 것.")
    return root


# 아래 전역은 _bootstrap() 이 채운다. 모듈 import 만으로는 아무 부작용도 일어나지 않게 해서,
# 순수 로직(PIT 필터·인물키·엣지·전이)을 네트워크와 자격증명 없이 따로 검증할 수 있게 한다.
# JupyterLab 셀에 붙여넣으면 __name__ == "__main__" 이므로 평소처럼 전부 실행된다.
ROOT = DIR_CACHE_RAW = DIR_CACHE_META = DIR_STATE = DIR_REPORTS = None
pd = requests = stock = None

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 4. 로깅 — 화면과 run_log.txt 에 동시에 쓴다
# ══════════════════════════════════════════════════════════════════════════════════════════
_LOG_LK = threading.Lock()
_LOG_FH = None


def LOG(msg: str = "", tag: str = "") -> None:
    t = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}" if not tag else f"[{t}] {tag:<5} {msg}"
    with _LOG_LK:
        print(line, flush=True)
        if _LOG_FH is None:
            return
        try:
            _LOG_FH.write(line + "\n")
            _LOG_FH.flush()
        except OSError as e:
            if getattr(e, "errno", None) == errno.ENOSPC:
                raise DiskFull("run_log.txt 기록 중 ENOSPC") from e
            raise


def OK(m):
    LOG(m, "OK")


def WARN(m):
    LOG(m, "WARN")


def ERR(m):
    LOG(m, "ERR")


def RULE(title: str = "") -> None:
    LOG("─" * 88)
    if title:
        LOG(title)
        LOG("─" * 88)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 5. 안전한 파일 입출력 — ENOSPC 는 즉시 실패 (§8)
# ══════════════════════════════════════════════════════════════════════════════════════════
def _guard_enospc(e: BaseException, what: str):
    if isinstance(e, OSError) and getattr(e, "errno", None) == errno.ENOSPC:
        raise DiskFull(f"디스크 공간 없음(ENOSPC): {what} — 재시도하지 않는다. "
                       f"공간을 확보한 뒤 다시 실행할 것.") from e


def write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError as e:
        _guard_enospc(e, str(path))
        raise
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def read_json(path: Path):
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8", "replace"))
    except (OSError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 6. 의존성 → 자격증명 주입 → pykrx import   (이 순서를 코드가 강제한다, §8)
# ══════════════════════════════════════════════════════════════════════════════════════════
def _ensure_packages(pkgs) -> None:
    """find_spec 은 모듈을 '실행'하지 않는다 — pykrx 를 여기서 import 하면 안 되기 때문이다."""
    missing = [p for p in pkgs if importlib.util.find_spec(p.replace("-", "_")) is None]
    if not missing:
        return
    LOG(f"의존 패키지 설치: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=False)
    importlib.invalidate_caches()


PYKRX_IMPORT_ORDER = {"purged_stale_modules": 0, "env_injected_before_import": False}


def _import_pykrx_after_env():
    """KRX 자격증명을 os.environ 에 넣은 '뒤에' pykrx 를 import 한다.

    pykrx.webio 는 모듈 로드 시점에 KRX 세션을 만든다. 순서가 뒤집히면 비인증 세션이
    조용히 만들어지고, 이후 조회가 JSON 대신 로그인 HTML 을 받아 엉뚱한 곳에서 터진다.
    v1.2 의 KRX_ENV_TOO_LATE 가 정확히 이것이었다.
    셀을 같은 커널에서 다시 돌리면 pykrx 가 이미 sys.modules 에 있으므로, 주입 전에 비운다.
    """
    stale = [m for m in list(sys.modules) if m == "pykrx" or m.startswith("pykrx.")]
    for m in stale:
        del sys.modules[m]
    PYKRX_IMPORT_ORDER["purged_stale_modules"] = len(stale)

    if KRX_ID and KRX_PW:
        os.environ["KRX_ID"] = KRX_ID.strip()
        os.environ["KRX_PW"] = KRX_PW.strip()
    PYKRX_IMPORT_ORDER["env_injected_before_import"] = True

    if any(m == "pykrx" or m.startswith("pykrx.") for m in sys.modules):
        raise ContractViolation("pykrx 가 자격증명 주입 이전에 이미 로드되어 있다.")

    from pykrx import stock as _stock          # ← 주입 이후의 유일한 import 지점
    return _stock


_DEAD_CALL_NAME = "get_index_portfolio_deposit_file"


def _bootstrap():
    """경로 검사 → 디렉터리 → 로그 → 의존성 → 자격증명 주입 → pykrx import.

    이 순서가 곧 계약이다. 특히 마지막 두 단계는 뒤집히면 안 된다 (§8).
    """
    global ROOT, DIR_CACHE_RAW, DIR_CACHE_META, DIR_STATE, DIR_REPORTS
    global pd, requests, stock, _LOG_FH

    ROOT = resolve_project_root(PROJECT_ROOT)          # P0_LOCAL_ROOT_ONLY — 여기서 터진다
    DIR_CACHE_RAW = ROOT / "cache" / "raw" / "dart_exctv"
    DIR_CACHE_META = ROOT / "cache" / "meta"
    DIR_STATE = ROOT / "cache" / "state"
    DIR_REPORTS = ROOT / "reports"
    for d in (DIR_CACHE_RAW, DIR_CACHE_META, DIR_STATE, DIR_REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    _LOG_FH = open(DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")

    _ensure_packages(["pandas", "requests", "pykrx"])
    import pandas as _pd
    import requests as _rq
    pd, requests = _pd, _rq

    stock = _import_pykrx_after_env()                  # ← 자격증명 주입 '이후'의 유일한 지점

    # NO_KNOWN_DEAD_CALL: '쓰지 않는다'로 끝내지 않고, 호출되면 터지게 만든다.
    if hasattr(stock, _DEAD_CALL_NAME):
        def _dead_call(*a, **k):
            raise ContractViolation(
                f"NO_KNOWN_DEAD_CALL 위반: {_DEAD_CALL_NAME}{a!r} 는 사용이 금지된 호출이다.")
        setattr(stock, _DEAD_CALL_NAME, _dead_call)

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 7. 스냅샷 명세 (§3.1) — 관측시점 정렬(A) 채택
# ══════════════════════════════════════════════════════════════════════════════════════════
#   as_of = 해당 보고서의 법정 제출기한 = "그 정보를 알 수 있게 된 시점".
#   분기/반기보고서 45일, 사업보고서 90일. 아래 FROZEN 값과 계산값이 어긋나면 실행을 멈춘다.
ALIGNMENT = "A_OBSERVATION_TIME"
REPRT_NAME = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서",
              "11014": "3분기보고서"}
_DEADLINE_DAYS = {"11011": 90, "11012": 45, "11013": 45, "11014": 45}

SNAPSHOT_SPEC = [
    # id,   기준일(nominal), 결산기준일,     bsns_year, reprt_code, as_of(FROZEN), 필요건수(§2.2)
    ("S1", "2025-06-30", "2025-06-30", "2025", "11012", "2025-08-14", 2760),
    ("S2", "2025-09-30", "2025-09-30", "2025", "11014", "2025-11-14", 2765),
    ("S3", "2025-12-31", "2025-12-31", "2025", "11011", "2026-03-31", 2790),
    ("S4", "2026-03-31", "2026-03-31", "2026", "11013", "2026-05-15", 2763),
]

TRANSITIONS = [("S1", "S2"), ("S2", "S3"), ("S3", "S4")]
MEASURE_N = 1000            # 측정 대상 = 시총 하위 1,000종목
EMPTY_UNIVERSE_MIN = 100    # 시총>0 이 이보다 적으면 수집 진입 금지 (§3.3)
TRADING_DAY_LOOKBACK = 10   # 직전 거래일 탐색 최대 역행 일수 (§3.2)
HOMONYM_FLAG_K = 8          # 이 이상 종목에 겸직으로 잡히는 인물은 동명이인 의심으로 진단 출력
CALL_BUDGET_DAILY = 19000
CALL_BUDGET_STOP = 12000
N_WORKERS = 4
DELAY_RANGE = (0.3, 1.0)
CIRCUIT_FAIL_N = 10
CIRCUIT_SLEEP = 60
CIRCUIT_MAX_TRIPS = 3


def _legal_deadline(period_end: str, reprt_code: str) -> str:
    d = _dt.date.fromisoformat(period_end) + _dt.timedelta(days=_DEADLINE_DAYS[reprt_code])
    return d.isoformat()


def verify_snapshot_spec() -> None:
    """FROZEN as_of 가 법정기한 계산과 일치하는지, 그리고 실행일이 아닌지 확인한다."""
    today = _dt.date.today().isoformat()
    for sid, _nom, pend, _yy, rc, as_of, _need in SNAPSHOT_SPEC:
        calc = _legal_deadline(pend, rc)
        if calc != as_of:
            raise ContractViolation(
                f"P0_PIT_STRICT_DELTA: {sid} as_of 불일치 — FROZEN={as_of}, 법정기한계산={calc}")
        if as_of == today:
            raise ContractViolation(
                f"P0_PIT_STRICT_DELTA 위반: {sid} 의 as_of 가 실행일({today})과 같다. "
                f"v1.2 를 무효화한 바로 그 결함이다.")


def _sha256_thresholds() -> str:
    return hashlib.sha256(
        json.dumps(GATE_THRESHOLDS, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 8. 정규화 헬퍼
# ══════════════════════════════════════════════════════════════════════════════════════════
_NONDIGIT = re.compile(r"\D")
_PAREN = re.compile(r"[(（\[][^)）\]]*[)）\]]")
_WS = re.compile(r"[\s 　]+")
_BIRTH = re.compile(r"(\d{4})\s*[년.\-/]?\s*(\d{1,2})")


def to_code6(v) -> str:
    s = _NONDIGIT.sub("", str(v or ""))
    return s.zfill(6) if 0 < len(s) <= 6 else (s[-6:] if len(s) > 6 else "")


def norm_name(v) -> str:
    """'홍길동(洪吉童)' · '홍 길동' → '홍길동'. 괄호 병기와 공백만 제거한다(음차 추정 금지)."""
    s = _PAREN.sub("", str(v or ""))
    return _WS.sub("", s).strip()


def norm_birth_ym(v) -> str:
    """'1960년 03월' · '1960.03' · '1960-3' → '196003'. 복원 불가면 '' (엣지 생성 제외)."""
    s = str(v or "")
    m = _BIRTH.search(s)
    if not m:
        return ""
    yy, mm = int(m.group(1)), int(m.group(2))
    if not (1900 <= yy <= 2020 and 1 <= mm <= 12):
        return ""
    return f"{yy:04d}{mm:02d}"


def person_key(name, birth) -> str:
    n, b = norm_name(name), norm_birth_ym(birth)
    return f"{n}|{b}" if (n and b) else ""


def rcept_dt_of(rcept_no) -> str:
    """접수번호 앞 8자리 = 접수일자(YYYYMMDD). 형식이 깨졌으면 '' (추정하지 않는다)."""
    s = _NONDIGIT.sub("", str(rcept_no or ""))
    if len(s) < 8:
        return ""
    d = s[:8]
    try:
        _dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    except ValueError:
        return ""
    return d


def compact(iso_date: str) -> str:
    return iso_date.replace("-", "")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 9. 캐시 계층 (§2)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  키 = (corp_code, bsns_year, reprt_code)
#  경로 = cache/raw/dart_exctv/{corp_code}/{bsns_year}_{reprt_code}.json
#  ★ 캐시는 API '원본 응답'을 저장한다. PIT 필터는 읽은 '뒤에' 적용한다.
#    따라서 v1.2 에서 잘못된 as_of 로 수집된 캐시도 그대로 재사용 가능하다 — 필터만 다시 건다.
#    v1.2 캐시가 as_of 를 파일에 박아 두었더라도 그 필드는 읽지 않고 rcept_no 로 재필터링한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
_IGNORED_CACHE_FIELDS = ("as_of", "asof", "as_of_date", "pit_as_of", "filtered", "pit_filtered")


def cache_path(corp_code: str, year: str, reprt: str) -> Path:
    return DIR_CACHE_RAW / str(corp_code) / f"{year}_{reprt}.json"


def extract_dart_payload(obj):
    """원본 응답이든 v1.2 의 봉투(envelope)든 (status, list) 를 꺼낸다.

    v1.2 캐시는 {"as_of":..., "response":{...}} 처럼 감싸져 있을 수 있다. 그 as_of 는
    무시하고 원본 rcept_no 로 재필터링한다는 것이 §2.4 의 요구다.
    """
    if isinstance(obj, list):
        return "", obj
    if not isinstance(obj, dict):
        return "", []
    if isinstance(obj.get("list"), list):
        return str(obj.get("status", "")), obj["list"]
    for k in ("response", "raw", "data", "payload", "body", "json", "result"):
        v = obj.get(k)
        if isinstance(v, (dict, list)):
            st, lst = extract_dart_payload(v)
            if lst or st:
                return st, lst
    return str(obj.get("status", "")), []


def scan_cache_inventory():
    """(year, reprt) → set(corp_code). 파일 하나하나를 열지 않고 파일명만 읽는다."""
    inv = defaultdict(set)
    if not DIR_CACHE_RAW.exists():
        return inv
    try:
        with os.scandir(DIR_CACHE_RAW) as corps:
            for c in corps:
                if not c.is_dir():
                    continue
                try:
                    with os.scandir(c.path) as files:
                        for f in files:
                            n = f.name
                            if not n.endswith(".json") or "_" not in n:
                                continue
                            y, _, r = n[:-5].partition("_")
                            if y.isdigit() and r.isdigit():
                                inv[(y, r)].add(c.name)
                except OSError:
                    continue
    except OSError:
        pass
    return inv


# ── 드라이브 콜드 백업 ─────────────────────────────────────────────────────────────────────
BACKUP_NAME = "phase0_dart_exctv_cache.tar.gz"


def _drive_dir():
    if not str(GDRIVE_BACKUP_DIR or "").strip():
        return None
    return Path(os.path.expanduser(GDRIVE_BACKUP_DIR)).resolve()


def restore_from_drive() -> dict:
    """skip-if-exists. 로컬 파일은 어떤 경우에도 덮어쓰지 않는다 (§2.2)."""
    out = {"attempted": False, "archive": "", "restored": 0, "skipped_existing": 0,
           "rejected_members": 0, "error": ""}
    d = _drive_dir()
    if d is None:
        out["error"] = "GDRIVE_BACKUP_DIR 미설정"
        return out
    arc = d / BACKUP_NAME
    out["attempted"] = True
    out["archive"] = str(arc)
    if not arc.exists():
        out["error"] = "아카이브 없음"
        return out
    try:
        with tarfile.open(arc, "r:gz") as tf:
            for m in tf:
                if not m.isfile():                             # 심볼릭/하드링크·디렉터리 제외
                    continue
                # 경로 탈출은 '무해한 이름으로 고쳐서 받기'가 아니라 '거부'다.
                # (lstrip('./') 로 지우면 ../../../etc/evil 이 etc/evil 로 둔갑해 조용히 쓰인다)
                rel = os.path.normpath(m.name.replace("\\", "/"))
                if os.path.isabs(rel) or rel == "." or rel.startswith(".."):
                    out["rejected_members"] += 1
                    continue
                dest = ROOT / rel
                try:
                    dest.resolve().relative_to(ROOT.resolve())
                except ValueError:
                    out["rejected_members"] += 1
                    continue
                if dest.exists():
                    out["skipped_existing"] += 1
                    continue
                src = tf.extractfile(m)
                if src is None:
                    continue
                write_bytes(dest, src.read())
                out["restored"] += 1
    except DiskFull:
        raise
    except Exception as e:                                     # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def backup_to_drive() -> dict:
    """이전 아카이브는 .prev 로 보존한다 (§2.5)."""
    out = {"attempted": False, "archive": "", "ok": False, "bytes": 0, "error": ""}
    d = _drive_dir()
    if d is None:
        out["error"] = "GDRIVE_BACKUP_DIR 미설정 — 백업 생략"
        return out
    out["attempted"] = True
    arc = d / BACKUP_NAME
    out["archive"] = str(arc)
    tmp = d / (BACKUP_NAME + ".tmp")
    try:
        d.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tmp, "w:gz") as tf:
            if DIR_CACHE_RAW.exists():
                tf.add(DIR_CACHE_RAW, arcname="cache/raw/dart_exctv")
            if DIR_CACHE_META.exists():
                tf.add(DIR_CACHE_META, arcname="cache/meta")
        if arc.exists():
            os.replace(arc, d / (BACKUP_NAME + ".prev"))
        os.replace(tmp, arc)
        out["ok"] = True
        out["bytes"] = arc.stat().st_size
    except OSError as e:
        _guard_enospc(e, "드라이브 백업")
        out["error"] = f"{type(e).__name__}: {e}"
    except Exception as e:                                     # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 10. corpCode — 파싱 '결과'를 캐시한다 (§2.3, v1.2 는 매 실행 231초를 썼다)
# ══════════════════════════════════════════════════════════════════════════════════════════
_CORP_LIST_RE = re.compile(rb"<list>(.*?)</list>", re.S)


def _corpcode_xml() -> Path:
    return DIR_CACHE_META / "corpCode.zip"


def _corpcode_parsed() -> Path:
    return DIR_CACHE_META / "corpcode_parsed.csv"


def _dart_status_msg(code: str) -> str:
    return {
        "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
        "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
        "020": "요청 제한 초과(일 20,000건)", "021": "조회 가능한 회사 개수 초과",
        "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검",
        "900": "정의되지 않은 오류", "901": "사용자 계정의 개인정보보호 요청",
    }.get(str(code), "알 수 없음")


def load_corpcode() -> "pd.DataFrame":
    """종목코드를 가진 법인만 남긴 (corp_code, corp_name, code) 표."""
    if _corpcode_parsed().exists():
        try:
            df = pd.read_csv(_corpcode_parsed(), dtype=str).fillna("")
            if len(df) and {"corp_code", "code"} <= set(df.columns):
                OK(f"corpCode 파싱 결과 캐시 히트 — {len(df):,}건 (XML 을 열지 않았다)")
                return df
        except Exception as e:                                 # noqa: BLE001
            WARN(f"corpCode 파싱 캐시 손상({type(e).__name__}) — 다시 만든다")

    raw = None
    if _corpcode_xml().exists():
        raw = _corpcode_xml().read_bytes()
        LOG(f"corpCode.zip 로컬 캐시 사용 ({len(raw):,} bytes)")
    if not raw or raw[:2] != b"PK":
        LOG("corpCode.xml 신규 수신 …")
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": DART_API_KEY}, timeout=180,
                         headers={"User-Agent": "Mozilla/5.0"})
        raw = r.content
        if raw[:2] != b"PK":
            body = raw[:400].decode("utf-8", "ignore")
            m = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
            st = m.group(1) if m else "?"
            raise HardStop(f"corpCode 응답이 ZIP 이 아니다 (status={st}: {_dart_status_msg(st)}). "
                           f"DART_API_KEY 를 확인할 것.")
        write_bytes(_corpcode_xml(), raw)

    t0 = time.time()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")] or zf.namelist()
        xml = zf.read(names[0])

    # v1.2 는 전체를 유니코드로 디코드한 뒤 <list> 마다 태그별 정규식을 돌려 231초를 썼다.
    # 바이트 단위 1-pass 로 끝낸다 (수 초).
    def _tag(blk: bytes, tag: bytes) -> str:
        i = blk.find(b"<" + tag + b">")
        if i < 0:
            return ""
        i += len(tag) + 2
        j = blk.find(b"</" + tag + b">", i)
        return blk[i:j].decode("utf-8", "replace").strip() if j > 0 else ""

    rows = []
    for m in _CORP_LIST_RE.finditer(xml):
        blk = m.group(1)
        code = to_code6(_tag(blk, b"stock_code"))
        if not code:
            continue                                            # 비상장 법인은 버린다
        rows.append({"corp_code": _tag(blk, b"corp_code"),
                     "corp_name": _tag(blk, b"corp_name"),
                     "code": code,
                     "modify_date": _tag(blk, b"modify_date")})
    df = pd.DataFrame(rows, columns=["corp_code", "corp_name", "code", "modify_date"])
    df = df[df["corp_code"].str.len() == 8].drop_duplicates("corp_code")
    OK(f"corpCode 파싱 완료 — 종목코드 보유 {len(df):,}건 / 소요 {time.time() - t0:.1f}s")
    try:
        df.to_csv(_corpcode_parsed(), index=False, encoding="utf-8")
        LOG(f"파싱 결과 캐시 저장 → {_corpcode_parsed().name} (다음 실행부터 XML 미개봉)")
    except OSError as e:
        _guard_enospc(e, "corpcode_parsed.csv")
        WARN(f"파싱 결과 캐시 저장 실패: {e}")
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 11. 유니버스 — 거래일 스냅(§3.2) + 빈 유니버스 가드(§3.3)
# ══════════════════════════════════════════════════════════════════════════════════════════
def _mcap_frame(date_c: str):
    """pykrx 버전별 시그니처 차이를 흡수한다. alternative 는 쓰지 않는다 —
    휴장일을 자동으로 직전 거래일로 바꿔치기해 버리면 #2 결함이 다시 숨는다."""
    for fn, kw in (("get_market_cap_by_ticker", {"market": "ALL", "alternative": False}),
                   ("get_market_cap_by_ticker", {"market": "ALL"}),
                   ("get_market_cap_by_ticker", {}),
                   ("get_market_cap", {"market": "ALL"}),
                   ("get_market_cap", {})):
        f = getattr(stock, fn, None)
        if f is None:
            continue
        try:
            df = f(date_c, **kw)
        except TypeError:
            continue
        except Exception:                                       # noqa: BLE001
            continue
        if isinstance(df, pd.DataFrame) and len(df) and "시가총액" in df.columns:
            return df
    return None


def resolve_trading_day(nominal_iso: str):
    """분기말이 휴장일이면 직전 거래일로 이동. '시총>0 종목수'로 거래일을 실측한다."""
    d0 = _dt.date.fromisoformat(nominal_iso)
    trail = []
    for back in range(TRADING_DAY_LOOKBACK + 1):
        d = d0 - _dt.timedelta(days=back)
        df = _mcap_frame(compact(d.isoformat()))
        if df is None:
            trail.append((d.isoformat(), "조회실패"))
            continue
        n_pos = int((pd.to_numeric(df["시가총액"], errors="coerce").fillna(0) > 0).sum())
        trail.append((d.isoformat(), f"행 {len(df):,} / 시총>0 {n_pos:,}"))
        if n_pos >= EMPTY_UNIVERSE_MIN:
            return d.isoformat(), df, trail
    return None, None, trail


def build_universe(sid: str, nominal_iso: str):
    """반환: dict(효과일자, 시총표, 측정대상 코드집합, 전상장 코드집합, 상태)."""
    eff, df, trail = resolve_trading_day(nominal_iso)
    for day, note in trail:
        mark = "←사용" if day == eff else ""
        LOG(f"    거래일 탐색 {day}: {note} {mark}")
    if eff is None:
        WARN(f"  {sid} 빈 유니버스 — {nominal_iso} 부터 {TRADING_DAY_LOOKBACK}일 역행했으나 "
             f"시총>0 종목이 {EMPTY_UNIVERSE_MIN} 미만. P0_EMPTY_UNIVERSE_GUARD 발동: "
             f"임원현황 수집에 진입하지 않는다.")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": "", "status": "UNVERIFIED",
                "status_reason": "EMPTY_UNIVERSE", "listed": set(), "measure": set(),
                "mcap": None, "n_listed_all": 0, "n_konex": 0}
    if eff != nominal_iso:
        WARN(f"  {sid} 휴장일 스냅: {nominal_iso} → {eff} (직전 거래일)")

    date_c = compact(eff)
    cap = pd.to_numeric(df["시가총액"], errors="coerce").fillna(0)
    df = df.assign(_cap=cap.values)
    df.index = [to_code6(i) for i in df.index]
    df = df[~df.index.duplicated(keep="first")]     # .loc 이 행을 불려 내는 사고 방지
    all_pos = df[df["_cap"] > 0]

    konex = set()
    keep_markets = ["KOSPI", "KOSDAQ"] + (["KONEX"] if INCLUDE_KONEX else [])
    sel = set()
    for mk in ["KOSPI", "KOSDAQ", "KONEX"]:
        try:
            ts = {to_code6(t) for t in stock.get_market_ticker_list(date_c, market=mk)}
        except Exception as e:                                  # noqa: BLE001
            WARN(f"  {sid} {mk} 종목목록 조회 실패({type(e).__name__}) — 해당 시장 라벨 결측")
            ts = set()
        if mk == "KONEX":
            konex = ts
        if mk in keep_markets:
            sel |= ts

    listed = set(all_pos.index) & sel if sel else set(all_pos.index)
    if not sel:
        WARN(f"  {sid} 시장 라벨 전부 결측 — 시총>0 전체를 유니버스로 사용(KONEX 포함 가능)")
    if len(listed) < EMPTY_UNIVERSE_MIN:
        WARN(f"  {sid} 시장 필터 후 {len(listed)}종목 — P0_EMPTY_UNIVERSE_GUARD 발동")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "UNVERIFIED",
                "status_reason": "EMPTY_UNIVERSE_AFTER_MARKET_FILTER", "listed": set(),
                "measure": set(), "mcap": None, "n_listed_all": len(all_pos), "n_konex": len(konex)}

    sub = all_pos.loc[sorted(listed)].sort_values("_cap", ascending=True)
    measure = set(sub.index[:MEASURE_N])
    LOG(f"    전 상장사(시총>0, {'KONEX 포함' if INCLUDE_KONEX else 'KONEX 제외'}) "
        f"{len(listed):,}종목  |  ALL 기준 {len(all_pos):,} (KONEX {len(konex):,})")
    LOG(f"    측정대상 = 시총 하위 {len(measure):,}종목  "
        f"(최소 {sub['_cap'].iloc[0] / 1e8:,.0f}억 ~ 최대 {sub['_cap'].iloc[len(measure) - 1] / 1e8:,.0f}억)")
    return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "OK",
            "status_reason": "", "listed": listed, "measure": measure, "mcap": sub,
            "n_listed_all": len(all_pos), "n_konex": len(konex)}


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 12. DART 임원현황 수집 — 워커 4 / 랜덤지연 / 지수백오프 / 서킷브레이커 / 예산 (§8)
# ══════════════════════════════════════════════════════════════════════════════════════════
EXCTV_URL = "https://opendart.fss.or.kr/api/exctvSttus.json"
_BUDGET_FILE = f"call_budget_{RUN_STARTED:%Y%m%d}.json"      # 경로는 _bootstrap 이후에 만든다


class Collector:
    def __init__(self, api_key: str):
        self.key = api_key
        self.lk = threading.Lock()
        self.tls = threading.local()
        self.budget_state = DIR_STATE / _BUDGET_FILE
        st = read_json(self.budget_state) or {}
        self.calls_today = int(st.get("calls", 0))      # 같은 날 이전 실행분까지 누적
        self.calls_run = 0
        self.consec_fail = 0
        self.trips = 0
        self.pause_until = 0.0
        self.halt = ""
        self.stat = Counter()

    # ── 예산 ──────────────────────────────────────────────────────────────────────────
    def _reserve(self) -> bool:
        with self.lk:
            if self.halt:
                return False
            if self.calls_run >= CALL_BUDGET_STOP:
                self.halt = "BUDGET_STOP_RUN"
                return False
            if self.calls_today >= CALL_BUDGET_DAILY:
                self.halt = "BUDGET_STOP_DAILY"
                return False
            self.calls_run += 1
            self.calls_today += 1
            return True

    def persist_budget(self):
        write_json(self.budget_state,
                   {"date": f"{RUN_STARTED:%Y-%m-%d}", "calls": self.calls_today})

    # ── 서킷브레이커 ──────────────────────────────────────────────────────────────────
    def _await_pause(self):
        while True:
            with self.lk:
                if self.halt:
                    return
                rem = self.pause_until - time.time()
            if rem <= 0:
                return
            time.sleep(min(2.0, rem))

    def _on_ok(self):
        with self.lk:
            self.consec_fail = 0

    def _on_fail(self):
        with self.lk:
            self.consec_fail += 1
            if self.consec_fail >= CIRCUIT_FAIL_N:
                self.consec_fail = 0
                self.trips += 1
                if self.trips >= CIRCUIT_MAX_TRIPS:
                    self.halt = "CIRCUIT_BREAKER"
                else:
                    self.pause_until = time.time() + CIRCUIT_SLEEP
                    WARN(f"  서킷브레이커 {self.trips}/{CIRCUIT_MAX_TRIPS} — "
                         f"연속실패 {CIRCUIT_FAIL_N}회, {CIRCUIT_SLEEP}초 대기")

    def _session(self):
        s = getattr(self.tls, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) phase0-axisA-delta"})
            self.tls.s = s
        return s

    # ── 단건 수집 ─────────────────────────────────────────────────────────────────────
    def fetch(self, corp_code: str, year: str, reprt: str) -> str:
        """성공 시 캐시에 원본 응답을 저장하고 상태코드를 돌려준다."""
        path = cache_path(corp_code, year, reprt)
        for attempt in range(4):
            self._await_pause()
            if not self._reserve():
                return "HALT"
            time.sleep(random.uniform(*DELAY_RANGE))
            try:
                r = self._session().get(
                    EXCTV_URL, timeout=30,
                    params={"crtfc_key": self.key, "corp_code": corp_code,
                            "bsns_year": year, "reprt_code": reprt})
            except Exception:                                   # noqa: BLE001
                self._on_fail()
                self.stat["net_error"] += 1
                time.sleep(min(16, 2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
                continue
            if r.status_code >= 500 or r.status_code == 429:
                self._on_fail()
                self.stat[f"http_{r.status_code}"] += 1
                time.sleep(min(16, 2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
                continue
            try:
                js = r.json()
            except ValueError:
                self._on_fail()
                self.stat["not_json"] += 1
                time.sleep(min(16, 2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
                continue

            st = str(js.get("status", ""))
            if st in ("011", "012", "020", "021"):
                with self.lk:
                    self.halt = f"DART_{st}"
                ERR(f"  DART status={st} ({_dart_status_msg(st)}) — 계속할 수 없다")
                return st
            if st in ("800", "900"):
                self._on_fail()
                self.stat[f"dart_{st}"] += 1
                time.sleep(min(16, 2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
                continue

            self._on_ok()
            self.stat[f"dart_{st or '?'}"] += 1
            write_json(path, js)           # ← 원본 응답 그대로. PIT 필터는 읽을 때 건다.
            return st
        self.stat["exhausted"] += 1
        return "RETRY_EXHAUSTED"

    def run(self, jobs, label: str):
        """jobs = [(corp_code, year, reprt), ...]. 반환: (성공수, 남은 작업)"""
        done, remaining = 0, []
        if not jobs:
            return 0, []
        def _tally(job, status):
            nonlocal done
            if status in ("000", "013"):    # 013(데이터 없음)도 확정된 사실 — 캐시되고 재호출 안 함
                done += 1
            else:
                remaining.append(job)

        with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
            futs = {ex.submit(self.fetch, *j): j for j in jobs}
            seen = set()
            for i, fu in enumerate(as_completed(futs), 1):
                j = futs[fu]
                seen.add(j)
                try:
                    _tally(j, fu.result())
                except Exception as e:                          # noqa: BLE001
                    _tally(j, f"EXC_{type(e).__name__}")
                if i % 200 == 0 or i == len(jobs):
                    LOG(f"    {label}: {i:,}/{len(jobs):,} 완료 "
                        f"(성공 {done:,} / 누적호출 {self.calls_run:,})")
                if self.halt:
                    break
            # break 로 빠져나와도 with 블록은 남은 future 를 끝까지 기다린다. halt 상태에서는
            # _reserve() 가 즉시 False 를 돌려주므로 곧바로 끝난다. 그 결과를 버리면 성공한
            # 건이 resume_todo 에 다시 실려 재호출된다 — 여기서 반드시 회수한다.
        for fu, j in futs.items():
            if j in seen:
                continue
            try:
                _tally(j, fu.result(timeout=0))
            except Exception as e:                              # noqa: BLE001
                _tally(j, f"EXC_{type(e).__name__}")
        self.persist_budget()
        return done, remaining


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 13. PIT 필터 (§3.1) — 이번 수정의 핵심
# ══════════════════════════════════════════════════════════════════════════════════════════
def pit_filter(records, as_of_iso: str):
    """rcept_no 앞 8자리(접수일자) ≤ as_of 인 레코드만 남긴다.

    반환: (kept, dropped) — dropped 각 건에 폐기 사유를 붙인다.
      LOOKAHEAD    접수일자가 as_of 이후 (정정공시 등). 이것이 v1.2 를 무효화한 오염원이다.
      BAD_RCEPT    접수번호가 없거나 날짜로 읽히지 않음 → 추정하지 않고 버린다(P0_FAIL_LOUD)
    """
    cutoff = compact(as_of_iso)
    kept, dropped = [], []
    for rec in records:
        d = rcept_dt_of(rec.get("rcept_no"))
        if not d:
            dropped.append({**rec, "_drop_reason": "BAD_RCEPT", "_rcept_dt": ""})
        elif d > cutoff:
            dropped.append({**rec, "_drop_reason": "LOOKAHEAD", "_rcept_dt": d})
        else:
            kept.append({**rec, "_rcept_dt": d})
    return kept, dropped


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 14. 그래프 (§4.1)
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_graph(records, corp2code):
    """노드=종목코드, 엣지=(성명+출생년월) 동일인이 두 종목에 동시 임원 등재.

    출생년월 결측 레코드는 엣지 생성에서 제외한다. 측정대상 밖의 상대 노드도 유지한다.
    """
    per_person = defaultdict(set)
    n_no_birth = n_no_code = n_used = 0
    for rec in records:
        code = corp2code.get(str(rec.get("corp_code", "")).strip(), "")
        if not code:
            n_no_code += 1
            continue
        k = person_key(rec.get("nm"), rec.get("birth_ym"))
        if not k:
            n_no_birth += 1
            continue
        per_person[k].add(code)
        n_used += 1

    edges = set()
    multi = []
    for k, codes in per_person.items():
        if len(codes) < 2:
            continue
        multi.append((k, len(codes)))
        for a, b in itertools.combinations(sorted(codes), 2):
            edges.add((a, b))
    multi.sort(key=lambda t: -t[1])
    return {
        "edges": edges,
        "persons": len(per_person),
        "persons_multi": len(multi),
        "records_used": n_used,
        "records_no_birth": n_no_birth,
        "records_unmapped_corp": n_no_code,
        "homonym_suspects": [{"person": k, "n_codes": n} for k, n in multi if n >= HOMONYM_FLAG_K],
        "top_multi": [{"person": k, "n_codes": n} for k, n in multi[:15]],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 15. 전이 (§4.2) — born / died. 절대 합산하지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
def transition(prev: dict, nxt: dict):
    """교집합 = 두 스냅샷 모두에서 시총 하위 1,000 에 든 종목.

    엣지 귀속: 한쪽 끝이라도 교집합에 걸치면 그 전이의 엣지로 센다(§4.1).
    보조수치 both_listed_* 는 양끝이 두 스냅샷 모두에 상장돼 있던 엣지만 센다 —
    상대 노드의 상장/폐지가 엣지 생성·소멸로 위장하는 몫을 분리하기 위한 것이다.
    """
    I = prev["measure"] & nxt["measure"]
    Ep, En = prev["edges"], nxt["edges"]
    both = prev["listed"] & nxt["listed"]

    born_e = [e for e in (En - Ep) if e[0] in I or e[1] in I]
    died_e = [e for e in (Ep - En) if e[0] in I or e[1] in I]

    born_by, died_by = Counter(), Counter()
    for a, b in born_e:
        if a in I:
            born_by[a] += 1
        if b in I:
            born_by[b] += 1
    for a, b in died_e:
        if a in I:
            died_by[a] += 1
        if b in I:
            died_by[b] += 1

    n_born_stocks = sum(1 for s in I if born_by.get(s, 0) > 0)
    return {
        "from": prev["snapshot"], "to": nxt["snapshot"],
        "intersect": len(I),
        "measure_from": len(prev["measure"]), "measure_to": len(nxt["measure"]),
        "edges_from": len(Ep), "edges_to": len(En),
        "edge_born": len(born_e), "edge_died": len(died_e),
        "born_ratio": (n_born_stocks / len(I)) if I else 0.0,
        "stocks_with_born": n_born_stocks,
        "stocks_with_died": sum(1 for s in I if died_by.get(s, 0) > 0),
        "born_both_listed": sum(1 for e in born_e if e[0] in both and e[1] in both),
        "died_both_listed": sum(1 for e in died_e if e[0] in both and e[1] in both),
        "status": "OK",
        "_per_stock": [{"transition": f"{prev['snapshot']}->{nxt['snapshot']}", "code": s,
                        "edge_born": born_by.get(s, 0), "edge_died": died_by.get(s, 0)}
                       for s in sorted(I)],
    }


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 16. 메인
# ══════════════════════════════════════════════════════════════════════════════════════════
def main():
    _bootstrap()
    RULE("PHASE 0 — 축 A-Δ 재측정 v1.3   (LIVE / 로컬 JupyterLab)")
    LOG(f"PROJECT_ROOT : {ROOT}")
    LOG(f"실행 시각    : {RUN_STARTED:%Y-%m-%d %H:%M:%S}")
    LOG(f"정렬 방식    : {ALIGNMENT} — as_of = 법정 제출기한 (§3.1 (A) 채택)")
    LOG(f"유니버스     : {'KOSPI+KOSDAQ+KONEX' if INCLUDE_KONEX else 'KOSPI+KOSDAQ (KONEX 제외)'}")

    # ── 1. 계약 검사 ──────────────────────────────────────────────────────────────────
    RULE("1. 계약 검사")
    if _sha256_thresholds() != GATE_THRESHOLDS_SHA256:
        raise ContractViolation(
            f"P0_NO_THRESHOLD_EDIT 위반: 임계값이 변경되었다.\n"
            f"  현재값={GATE_THRESHOLDS}\n  현재해시={_sha256_thresholds()}\n"
            f"  고정해시={GATE_THRESHOLDS_SHA256}")
    verify_snapshot_spec()
    if not str(DART_API_KEY).strip():
        raise ContractViolation(
            "P0_LIVE_ONLY: DART_API_KEY 가 비어 있다. 합성 데이터 경로는 존재하지 않는다.\n"
            "  https://opendart.fss.or.kr/ 에서 인증키를 발급받아 상단 블록에 넣을 것.")
    for cid, desc in CONTRACTS.items():
        LOG(f"  ✓ {cid:<26} {desc}")
    LOG(f"  ✓ pykrx import 순서 강제 — 자격증명 주입 후 로드 "
        f"(재실행 시 정리한 stale 모듈 {PYKRX_IMPORT_ORDER['purged_stale_modules']}개)")

    # ── 2. 캐시 인벤토리 (P0_CACHE_FIRST) ────────────────────────────────────────────
    RULE("2. 캐시 인벤토리")
    inv_local = scan_cache_inventory()
    n_local = {k: len(v) for k, v in inv_local.items()}
    restore = restore_from_drive()
    if restore["attempted"]:
        if restore["error"]:
            WARN(f"  드라이브 복원 불가: {restore['error']}")
        else:
            OK(f"  드라이브 복원 {restore['restored']:,}건 "
               f"(로컬 기존 파일 {restore['skipped_existing']:,}건은 건드리지 않음)")
    else:
        LOG("  드라이브 백업 미설정 — 로컬 캐시만 사용")
    inv_after = scan_cache_inventory()
    corpcode_cached = _corpcode_parsed().exists()

    LOG("")
    LOG("캐시 인벤토리")
    est_new = 0
    inv_rows = []
    for sid, nom, _pe, yy, rc, as_of, need in SNAPSHOT_SPEC:
        have0 = n_local.get((yy, rc), 0)
        have1 = len(inv_after.get((yy, rc), set()))
        short = max(0, need - have1)
        est_new += short
        inv_rows.append({"snapshot": sid, "bsns_year": yy, "reprt_code": rc,
                         "report": REPRT_NAME[rc], "local_before": have0,
                         "restored_from_drive": have1 - have0, "local_after": have1,
                         "expected_need": need, "estimated_shortfall": short})
        LOG(f"  {yy}/{rc} ({sid} {REPRT_NAME[rc]:<6}) : 로컬 {have0:>5,}건 / "
            f"드라이브복원 {have1 - have0:>5,}건 / 필요 ~{need:,}건 → 부족 {short:>5,}건")
    LOG(f"  corpCode 파싱 결과            : {'있음' if corpcode_cached else '없음'}")
    LOG(f"  ── 예상 신규 API 호출: {est_new:,}건 / "
        f"예상 소요: {est_new * (sum(DELAY_RANGE) / 2) / N_WORKERS / 60:.0f}분")

    inventory = {"local_before": {f"{k[0]}/{k[1]}": v for k, v in n_local.items()},
                 "drive_restore": restore, "rows": inv_rows,
                 "corpcode_parse_cache": corpcode_cached,
                 "estimated_new_calls": est_new, "actual_new_calls": 0}
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    if est_new > 5000 and not CONFIRM_LARGE_COLLECTION:
        LOG("")
        WARN(f"P0_CACHE_FIRST: 예상 신규 호출 {est_new:,}건 > 5,000건.")
        WARN("다만 이 수치는 §2.2 의 '필요 ~2,760건' 어림값에서 뺀 것이라 실제와 다르다.")
        WARN("정확한 부족분은 유니버스를 확정해야 나온다. 그 과정은 pykrx 조회와 corpCode "
             "1건뿐이고, 임원현황 수집에는 진입하지 않는다.")
        WARN("→ 4b 까지 진행해 정확한 수를 뽑은 뒤, 거기서 다시 멈춰 확인을 받는다.")

    # ── 3. corpCode ──────────────────────────────────────────────────────────────────
    RULE("3. corpCode")
    cc = load_corpcode()
    corp2code = dict(zip(cc["corp_code"], cc["code"]))
    code2corp = {}
    for corp, code in zip(cc["corp_code"], cc["code"]):
        code2corp.setdefault(code, corp)
    LOG(f"  corp_code → 종목코드 매핑 {len(corp2code):,}건 / 종목코드 고유 {len(code2corp):,}건")

    # ── 4a. 유니버스 확정 (DART 호출 0건. 여기서 빈 유니버스를 먼저 걸러낸다) ─────────
    RULE("4a. 유니버스 확정 — 거래일 스냅 + 빈 유니버스 가드")
    universes = {}
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        LOG(f"  {sid} 기준일 {nom} / {yy}-{rc} {REPRT_NAME[rc]} / as_of {as_of}")
        universes[sid] = build_universe(sid, nom)

    live_ids = [s for s in universes if universes[s]["status"] == "OK"]
    if not live_ids:
        raise HardStop("모든 스냅샷이 빈 유니버스다. pykrx/KRX 접속 상태를 확인할 것.")

    # ── 4b. 정확한 부족분 계산 → 5,000건 게이트 → 수집 ───────────────────────────────
    RULE("4b. 수집 대상 확정")
    jobs_by_snap, all_jobs = {}, []
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        u = universes[sid]
        if u["status"] != "OK":
            jobs_by_snap[sid] = []
            LOG(f"  {sid}: 빈 유니버스 — 수집 진입 안 함 (P0_EMPTY_UNIVERSE_GUARD)")
            continue
        want = sorted({code2corp[c] for c in u["listed"] if c in code2corp})
        u["corp_wanted"] = want
        u["unmapped_codes"] = len(u["listed"]) - len(want)
        have = inv_after.get((yy, rc), set())
        todo = [(cp, yy, rc) for cp in want if cp not in have]
        jobs_by_snap[sid] = todo
        all_jobs += todo
        LOG(f"  {sid}: 전상장 {len(u['listed']):,}종목 → corp_code 매핑 {len(want):,}건 "
            f"(미매핑 {u['unmapped_codes']:,}) / 캐시보유 {len(want) - len(todo):,} / 신규 {len(todo):,}")

    LOG(f"  ── 실제 신규 호출 예정: {len(all_jobs):,}건 "
        f"(예상 소요 {len(all_jobs) * (sum(DELAY_RANGE) / 2) / N_WORKERS / 60:.0f}분) "
        f"— 임원현황 수집은 아직 시작하지 않았다")
    inventory["planned_new_calls"] = len(all_jobs)
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)
    if len(all_jobs) > 5000 and not CONFIRM_LARGE_COLLECTION:
        WARN(f"P0_CACHE_FIRST: 실제 신규 호출 {len(all_jobs):,}건 > 5,000건.")
        WARN("수집에 진입하지 않고 여기서 멈춘다. 위 내역을 확인한 뒤")
        WARN("  CONFIRM_LARGE_COLLECTION = True")
        WARN("로 바꾸고 셀을 다시 실행할 것. (이미 받은 캐시는 그대로 재사용된다)")
        return {"status": "AWAITING_USER_CONFIRMATION", "planned_calls": len(all_jobs),
                "cache_inventory": inventory}

    col = Collector(DART_API_KEY.strip())
    if col.calls_today:
        LOG(f"  오늘 이전 실행분 누적 호출 {col.calls_today:,}건 (일일한도 {CALL_BUDGET_DAILY:,})")
    if all_jobs:
        RULE("4c. 임원현황 수집")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            todo = jobs_by_snap[sid]
            if not todo or col.halt:
                continue
            LOG(f"  {sid} ({yy}/{rc}) 신규 {len(todo):,}건 수집")
            done, remain = col.run(todo, sid)
            universes[sid]["api_new"] = done
            if remain:
                jobs_by_snap[sid] = remain
        if col.halt:
            left = [list(j) for sid in jobs_by_snap for j in jobs_by_snap[sid]]
            write_json(DIR_REPORTS / "resume_todo.json",
                       {"halt": col.halt, "calls_run": col.calls_run,
                        "calls_today": col.calls_today, "remaining": left})
            WARN(f"수집 중단({col.halt}) — 남은 {len(left):,}건을 resume_todo.json 에 저장했다. "
                 f"수집된 분량으로 측정을 계속한다(결측은 결측으로 남는다).")
        LOG(f"  응답 분포: {dict(col.stat)}")
    else:
        OK("  신규 호출 0건 — 전량 캐시 히트")
    inventory["actual_new_calls"] = col.calls_run
    inventory["collector_stat"] = dict(col.stat)
    inventory["halt"] = col.halt
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    # ── 4d. 캐시 로드 → PIT 필터 → 그래프 ────────────────────────────────────────────
    RULE("4d. PIT 필터 + 그래프 구성")
    snap_out, pit_rows = [], []
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        u = universes[sid]
        rec = {"id": sid, "date": u["date"] or nom, "date_nominal": nom, "as_of": as_of,
               "report": f"{yy}/{rc}", "report_name": REPRT_NAME[rc],
               "nodes": len(u["listed"]), "nodes_with_exctv": 0, "edges": 0,
               "pit_dropped": 0, "pit_dropped_lookahead": 0, "pit_dropped_bad_rcept": 0,
               "pit_kept": 0, "last_rcept_dt": "", "first_rcept_dt": "",
               "cache_hit": 0, "api_new": int(u.get("api_new", 0)),
               "records_no_birth": 0, "status": u["status"],
               "status_reason": u.get("status_reason", "")}
        if u["status"] != "OK":
            WARN(f"  {sid}: {u.get('status_reason')} — 그래프 구성 생략")
            snap_out.append(rec)
            u["edges"] = set()
            continue

        raw_recs, hit, miss, bad_status = [], 0, 0, Counter()
        for cp in u["corp_wanted"]:
            p = cache_path(cp, yy, rc)
            if not p.exists():
                miss += 1
                continue
            obj = read_json(p)
            if obj is None:
                miss += 1
                continue
            hit += 1
            st, lst = extract_dart_payload(obj)
            if st and st not in ("000", "013"):
                bad_status[st] += 1
            for r0 in lst:
                if isinstance(r0, dict):
                    raw_recs.append({k: v for k, v in r0.items()
                                     if k not in _IGNORED_CACHE_FIELDS})

        kept, dropped = pit_filter(raw_recs, as_of)
        n_look = sum(1 for d in dropped if d["_drop_reason"] == "LOOKAHEAD")
        n_bad = len(dropped) - n_look
        rec.update({"pit_kept": len(kept), "pit_dropped": len(dropped),
                    "pit_dropped_lookahead": n_look, "pit_dropped_bad_rcept": n_bad})
        # 이 시점엔 이번에 새로 받은 파일도 디스크에 있다. cache_hit 은 '원래 갖고 있던 것'만
        # 세야 §2.2 의 인벤토리와 말이 맞는다.
        rec["files_read"] = hit
        rec["cache_hit"] = max(0, hit - rec["api_new"])
        rec["cache_miss"] = miss
        rec["records_raw"] = len(raw_recs)

        dts = sorted({r["_rcept_dt"] for r in kept if r["_rcept_dt"]})
        rec["first_rcept_dt"] = dts[0] if dts else ""
        rec["last_rcept_dt"] = dts[-1] if dts else ""

        LOG(f"  {sid} {yy}/{rc} as_of={as_of}")
        LOG(f"    읽은 파일 {hit:,}사 (기존 캐시 {rec['cache_hit']:,} / 이번 신규 "
            f"{rec['api_new']:,}) / 미보유 {miss:,}사 / 원본 레코드 {len(raw_recs):,}건")
        LOG(f"    PIT 폐기 {len(dropped):,}건 (룩어헤드 {n_look:,} / 접수번호불량 {n_bad:,}) "
            f"→ 잔존 {len(kept):,}건")
        LOG(f"    최종접수일 {rec['last_rcept_dt'] or '—'} (최초 {rec['first_rcept_dt'] or '—'})")
        if bad_status:
            LOG(f"    비정상 status 응답: {dict(bad_status)}")

        # ★ 이번 수정이 실제로 걸렸는지의 하드 검사 (§3.1)
        if rec["last_rcept_dt"] and rec["last_rcept_dt"] > compact(as_of):
            raise ContractViolation(
                f"P0_PIT_STRICT_DELTA 위반: {sid} 최종접수일 {rec['last_rcept_dt']} > "
                f"as_of {compact(as_of)}. 필터가 걸리지 않았다 — 즉시 중단한다.")
        if n_look == 0:
            WARN(f"    {sid} 룩어헤드 폐기 0건 — v1.2 오염의 신호였던 값이다. "
                 f"폐기 분포표(diag_pit_dropped_delta.csv)를 반드시 확인할 것.")

        for d in dropped:
            pit_rows.append({"snapshot": sid, "as_of": as_of, "report": f"{yy}/{rc}",
                             "reason": d["_drop_reason"],
                             "rcept_ym": (d["_rcept_dt"][:6] if d["_rcept_dt"] else ""),
                             "rcept_dt": d["_rcept_dt"], "corp_code": d.get("corp_code", ""),
                             "corp_name": d.get("corp_name", "")})

        g = build_graph(kept, corp2code)
        u["edges"] = g["edges"]
        rec.update({"edges": len(g["edges"]),
                    "nodes_with_exctv": len({corp2code.get(str(r.get("corp_code", "")).strip(), "")
                                             for r in kept} - {""}),
                    "records_no_birth": g["records_no_birth"],
                    "records_unmapped_corp": g["records_unmapped_corp"],
                    "persons": g["persons"], "persons_multi_company": g["persons_multi"],
                    "homonym_suspects": len(g["homonym_suspects"]),
                    "top_multi": g["top_multi"]})
        LOG(f"    노드 {len(u['listed']):,}종목(전 상장사) / 임원데이터 보유 "
            f"{rec['nodes_with_exctv']:,}종목 / 엣지 {len(g['edges']):,}")
        LOG(f"    인물 {g['persons']:,}명 (2종목 이상 겸직 {g['persons_multi']:,}명) / "
            f"출생년월 결측 제외 {g['records_no_birth']:,}건")
        if g["homonym_suspects"]:
            WARN(f"    {HOMONYM_FLAG_K}종목 이상 겸직으로 잡힌 인물 "
                 f"{len(g['homonym_suspects'])}명 — 동명이인 의심 (판정표 top_multi 참조)")
        snap_out.append(rec)

    # ── 5. 전이 ──────────────────────────────────────────────────────────────────────
    RULE("5. 전이 — edge_born / edge_died (합산하지 않는다)")
    trans_out, per_stock = [], []
    for a, b in TRANSITIONS:
        ua, ub = universes[a], universes[b]
        if ua["status"] != "OK" or ub["status"] != "OK":
            trans_out.append({"from": a, "to": b, "intersect": 0, "edge_born": None,
                              "edge_died": None, "born_ratio": None, "status": "UNVERIFIED",
                              "status_reason": f"{a}={ua['status']} / {b}={ub['status']}"})
            WARN(f"  {a}→{b}: 스냅샷 미확보 — UNVERIFIED")
            continue
        t = transition(ua, ub)
        per_stock += t.pop("_per_stock")
        trans_out.append(t)
        LOG(f"  {a}→{b}  교집합 {t['intersect']:,}종목 "
            f"(측정대상 {t['measure_from']:,}/{t['measure_to']:,})")
        LOG(f"         edge_born {t['edge_born']:,}  |  edge_died {t['edge_died']:,}  "
            f"|  born_ratio {t['born_ratio']:.4f} ({t['stocks_with_born']:,}종목)")
        LOG(f"         (양끝 모두 두 스냅샷 상장: born {t['born_both_listed']:,} / "
            f"died {t['died_both_listed']:,})")

    # ── 6. 게이트 ────────────────────────────────────────────────────────────────────
    RULE("6. 판정 게이트")
    ok_t = [t for t in trans_out if t.get("status") == "OK"]
    ratios = [t["born_ratio"] for t in ok_t]
    borns = [t["edge_born"] for t in ok_t]
    n_graph_ok = sum(1 for s in snap_out if s["status"] == "OK" and s["edges"] is not None
                     and s["nodes_with_exctv"] > 0)

    def _gate(gid, desc, value, thr, cmp_ok, unverified):
        st = "UNVERIFIED" if unverified else ("PASS" if cmp_ok else "FAIL")
        g = {"id": gid, "desc": desc, "value": value, "threshold": thr, "status": st}
        v = "—" if value is None else (f"{value:.4f}" if isinstance(value, float) else f"{value:,}")
        LOG(f"  {gid:<6} {desc:<44} 실측 {v:>10}  임계 {thr:<6} → {st}")
        return g

    m_ratio = (sum(ratios) / len(ratios)) if ratios else None
    m_born = _median(borns)
    gates = [
        _gate("AΔ-1", "분기당 edge_born≥1 종목 비율 (전이 평균)", m_ratio,
              GATE_THRESHOLDS["AD1_born_ratio_mean"],
              m_ratio is not None and m_ratio >= GATE_THRESHOLDS["AD1_born_ratio_mean"],
              len(ok_t) != len(TRANSITIONS)),
        _gate("AΔ-2", "분기당 전체 edge_born 총건수 중앙값", m_born,
              GATE_THRESHOLDS["AD2_born_total_median"],
              m_born is not None and m_born >= GATE_THRESHOLDS["AD2_born_total_median"],
              len(ok_t) != len(TRANSITIONS)),
        _gate("AΔ-3", "4개 스냅샷 모두 그래프 구성 성공", n_graph_ok, 4, n_graph_ok >= 4, False),
    ]

    # ── 7. 성공 조건 (§10) — 게이트 통과 여부와 무관하다 ──────────────────────────────
    RULE("7. 성공 조건 (§10)")
    live = [s for s in snap_out if s["status"] == "OK"]
    c1_each = [{"snapshot": s["id"], "pit_dropped": s["pit_dropped"],
                "lookahead": s["pit_dropped_lookahead"], "last_rcept_dt": s["last_rcept_dt"],
                "as_of": compact(s["as_of"]),
                "within_as_of": bool(s["last_rcept_dt"]) and s["last_rcept_dt"] <= compact(s["as_of"])}
               for s in snap_out]
    c1 = (len(live) == 4 and all(s["pit_dropped"] > 0 for s in live)
          and all(x["within_as_of"] for x in c1_each if x["snapshot"] in {s["id"] for s in live}))
    c2 = len(ok_t) == len(TRANSITIONS) and all(
        t["edge_born"] is not None and t["edge_died"] is not None for t in ok_t)
    # 폐기에는 '룩어헤드'와 '접수번호 불량' 두 종류가 있다. §10 이 요구하는 것은 전체 폐기지만,
    # 이번 수정이 겨눈 것은 룩어헤드다 — 그래서 따로 세워 둔다.
    c1_lookahead = len(live) == 4 and all(s["pit_dropped_lookahead"] > 0 for s in live)
    LOG(f"  ① 4개 스냅샷 PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : {'충족' if c1 else '미충족'}")
    LOG(f"     (그 중 룩어헤드 폐기가 4개 스냅샷 모두 ≠ 0 : {'예' if c1_lookahead else '아니오'})")
    for x in c1_each:
        LOG(f"       {x['snapshot']}: 폐기 {x['pit_dropped']:,}건 (룩어헤드 {x['lookahead']:,}) / "
            f"최종접수일 {x['last_rcept_dt'] or '—'} ≤ as_of {x['as_of']} → "
            f"{'OK' if x['within_as_of'] else 'NG'}")
    LOG(f"  ② 전이 3개의 edge_born / edge_died 산출              : {'충족' if c2 else '미충족'}")
    LOG(f"  ⇒ 이번 실행: {'성공' if (c1 and c2) else '미완'}  (수치의 크기는 성공 여부와 무관)")

    # ── 8. 백업 ──────────────────────────────────────────────────────────────────────
    RULE("8. 드라이브 콜드 백업")
    bk = backup_to_drive()
    if bk["ok"]:
        OK(f"  백업 완료 {bk['archive']} ({bk['bytes'] / 1e6:.1f} MB, 이전본은 .prev 로 보존)")
    else:
        WARN(f"  백업 실패/생략: {bk['error']}")

    # ── 9. 산출물 ────────────────────────────────────────────────────────────────────
    RULE("9. 산출물")
    verdict = {
        "run_mode": "LIVE",
        "spec_version": "v1.3",
        "generated_at": RUN_STARTED.isoformat(timespec="seconds"),
        "project_root": str(ROOT),
        "alignment": ALIGNMENT,
        "alignment_note": "(A) 관측시점 정렬 — as_of = 해당 보고서의 법정 제출기한",
        "methodology": {
            "universe": "KOSPI+KOSDAQ+KONEX" if INCLUDE_KONEX else "KOSPI+KOSDAQ (KONEX 제외)",
            "measure_n": MEASURE_N,
            "node": "종목코드 (해당 스냅샷 거래일의 시총>0 상장사 전체)",
            "edge": "(성명, 출생년월) 동일 인물이 두 종목에 동시 임원 등재",
            "edge_attribution": "교집합 종목에 한쪽 끝이라도 걸친 엣지",
            "birth_missing": "엣지 생성에서 제외 (보간하지 않음)",
            "empty_universe_min": EMPTY_UNIVERSE_MIN,
        },
        "contracts": [{"id": k, "desc": v, "status": "ENFORCED"} for k, v in CONTRACTS.items()],
        "thresholds": GATE_THRESHOLDS,
        "thresholds_sha256": _sha256_thresholds(),
        "snapshots": snap_out,
        "transitions": trans_out,
        "gates": gates,
        "success_conditions": {"pit_evidence": bool(c1), "lookahead_evidence": bool(c1_lookahead),
                               "delta_measured": bool(c2), "overall": bool(c1 and c2),
                               "detail": c1_each},
        "cache": inventory,
        "backup": bk,
        "skipped": [
            {"axis": "A(본체)", "status": "SKIPPED_BY_SCOPE",
             "note": "A-1/A-2/A-3 는 v1.2 에서 확인 완료 — 재측정하지 않는다 (§5)"},
            {"axis": "B(BigQuery)", "status": "SKIPPED_BY_SCOPE"},
            {"axis": "C(국민연금)", "status": "SKIPPED_BY_SCOPE"},
        ],
        "known_limitations": KNOWN_LIMITATIONS,
    }
    write_json(DIR_REPORTS / "phase0_verdict_v13.json", verdict)

    rows = []
    for s in snap_out:
        rows.append({"section": "snapshot", "key": s["id"], **{
            k: v for k, v in s.items() if k not in ("id", "top_multi")}})
    for t in trans_out:
        rows.append({"section": "transition", "key": f"{t['from']}->{t['to']}", **{
            k: v for k, v in t.items() if k not in ("from", "to")}})
    for g in gates:
        rows.append({"section": "gate", "key": g["id"], **{
            k: v for k, v in g.items() if k != "id"}})
    pd.DataFrame(rows).to_csv(DIR_REPORTS / "phase0_verdict_v13.csv",
                              index=False, encoding="utf-8-sig")
    pd.DataFrame(per_stock, columns=["transition", "code", "edge_born", "edge_died"]).to_csv(
        DIR_REPORTS / "diag_edge_events.csv", index=False, encoding="utf-8-sig")

    if pit_rows:
        pdf = pd.DataFrame(pit_rows)
        dist = (pdf.groupby(["snapshot", "as_of", "report", "reason", "rcept_ym"])
                .agg(n_records=("corp_code", "size"), n_corps=("corp_code", "nunique"),
                     min_rcept_dt=("rcept_dt", "min"), max_rcept_dt=("rcept_dt", "max"))
                .reset_index().sort_values(["snapshot", "reason", "rcept_ym"]))
    else:
        dist = pd.DataFrame(columns=["snapshot", "as_of", "report", "reason", "rcept_ym",
                                     "n_records", "n_corps", "min_rcept_dt", "max_rcept_dt"])
    dist.to_csv(DIR_REPORTS / "diag_pit_dropped_delta.csv", index=False, encoding="utf-8-sig")

    md = ["# PHASE 0 — 축 A-Δ 재측정 v1.3 요약", "",
          f"- 실행: {RUN_STARTED:%Y-%m-%d %H:%M}  ·  run_mode: LIVE  ·  PROJECT_ROOT: `{ROOT}`",
          f"- 정렬: {ALIGNMENT} (as_of = 법정 제출기한)",
          f"- 유니버스: {verdict['methodology']['universe']}  ·  측정대상: 시총 하위 {MEASURE_N}종목",
          "", "## 스냅샷", "",
          "| 스냅샷 | 기준일(명목→사용) | 보고서 | as_of | 노드 | 엣지 | PIT폐기(룩어헤드) | 최종접수일 | 캐시히트 | 신규호출 | 상태 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in snap_out:
        d = s["date_nominal"] if s["date_nominal"] == s["date"] else f"{s['date_nominal']}→{s['date']}"
        md.append(f"| {s['id']} | {d} | {s['report']} {s['report_name']} | {s['as_of']} | "
                  f"{s['nodes']:,} | {s['edges']:,} | {s['pit_dropped']:,} "
                  f"({s['pit_dropped_lookahead']:,}) | {s['last_rcept_dt'] or '—'} | "
                  f"{s['cache_hit']:,} | {s['api_new']:,} | {s['status']} |")
    md += ["", "## 전이", "",
           "| 전이 | 교집합 | edge_born | edge_died | born_ratio | 상태 |", "|---|---|---|---|---|---|"]
    for t in trans_out:
        br = "—" if t.get("born_ratio") is None else f"{t['born_ratio']:.4f}"
        md.append(f"| {t['from']}→{t['to']} | {t['intersect']:,} | "
                  f"{t['edge_born'] if t['edge_born'] is not None else '—'} | "
                  f"{t['edge_died'] if t['edge_died'] is not None else '—'} | {br} | "
                  f"{t.get('status')} |")
    md += ["", "## 게이트", "", "| ID | 내용 | 실측 | 임계 | 판정 |", "|---|---|---|---|---|"]
    for g in gates:
        v = "—" if g["value"] is None else (f"{g['value']:.4f}" if isinstance(g["value"], float)
                                            else f"{g['value']:,}")
        md.append(f"| {g['id']} | {g['desc']} | {v} | {g['threshold']} | {g['status']} |")
    md += ["", "## 성공 조건 (§10)", "",
           f"- ① PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : **{'충족' if c1 else '미충족'}**",
           f"- ② 전이 3개 edge_born/edge_died 산출 : **{'충족' if c2 else '미충족'}**", "",
           "## 범위 밖", "",
           "- 축 A 본체(A-1/A-2/A-3): v1.2 확인 완료 — 재측정 안 함",
           "- 축 B(BigQuery) / 축 C(국민연금): SKIPPED_BY_SCOPE", "",
           "## known_limitations", ""]
    md += [f"{i}. {s}" for i, s in enumerate(KNOWN_LIMITATIONS, 1)]
    write_text(DIR_REPORTS / "phase0_summary_v13.md", "\n".join(md) + "\n")

    for f in ("phase0_verdict_v13.json", "phase0_verdict_v13.csv", "phase0_summary_v13.md",
              "diag_edge_events.csv", "diag_pit_dropped_delta.csv", "cache_inventory.json",
              "run_log.txt"):
        p = DIR_REPORTS / f
        LOG(f"  {'✓' if p.exists() else '✗'} {p}")
    RULE("완료")
    return verdict


if __name__ == "__main__":
    try:
        VERDICT = main()
    except (ContractViolation, DiskFull, HardStop) as _e:
        ERR(f"{type(_e).__name__}: {_e}")
        raise
