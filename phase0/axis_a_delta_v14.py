#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 0 — 축 A-Δ 재측정 v1.4   (로컬 JupyterLab 전용 · LIVE 전용 · 단일 셀)               ║
# ║                                                                                          ║
# ║  이 실행의 유일한 질문:  분기마다 겸직 링크가 실제로 몇 개나 생기고 사라지는가?              ║
# ║  전이 3개(S1→S2, S2→S3, S3→S4)의 edge_born / edge_died 가 나오면 목적 달성이다.            ║
# ║                                                                                          ║
# ║  ── v1.3 이 실패한 진짜 이유 (v1.3 명령서의 진단은 틀렸다) ──────────────────────────────  ║
# ║   KRX 는 2025-12-27 부로 정보데이터시스템을 회원제 "KRX Data Marketplace" 로 개편했다.      ║
# ║   pykrx 1.2.8 은 `from pykrx import stock` 하는 순간 website/comm/webio.py 12행에서        ║
# ║   build_krx_session() 을 실행하고, 그 안의 login_krx() 가 응답을 try/except 없이            ║
# ║   resp.json() 으로 파싱한다. 개편 후 로그인 응답이 JSON 이 아니게 되면서                    ║
# ║     JSONDecodeError: Expecting value: line 13 column 1 (char 25)                          ║
# ║   가 **import 시점에** 터진다. 자격증명이 없어서가 아니라, 자격증명을 넣고 시도한 로그인      ║
# ║   자체가 KRX 쪽 변경으로 실패한 것이다. v1.3 은 이 실패를 흡수하고 '무자격 재시도'로 넘어가  ║
# ║   문제를 감췄다. (KRX ID/PW 와 KRX Open API 인증키는 완전히 별개다 — 이번 실행은 Open API   ║
# ║   승인을 기다리지 않는다.)                                                                 ║
# ║                                                                                          ║
# ║  ── v1.4 가 하는 일 ────────────────────────────────────────────────────────────────────  ║
# ║   §2  시장 데이터 3단 사다리:  Plan A(pykrx 최신화) → Plan B(마켓플레이스 세션 직접 구성)   ║
# ║        → Plan C(DART 주식총수 × FDR 종가로 시총 재구성). 하나 성공하면 나머지는 건너뛴다.   ║
# ║        각 단계의 성패와 **사유 원문**을 reports/diag_market_source.json 에 남긴다.          ║
# ║   §3  DART 연결 단일 카나리 → 예외 유형 분류 → reports/diag_dart_preflight.json.           ║
# ║        '코드로 해결 불가'면 벌크 수집에 진입하지 않고 캐시분으로만 할 수 있는 것을 한다.     ║
# ║   §8  워커 2 · 요청간 0.3~1.0초 랜덤 · 타임아웃 30초 · 지수백오프 2/4/8 · 콜당 재시도 3회.  ║
# ║        서킷브레이커는 '재시도를 모두 소진한 콜이 연속 10건'일 때만 발동한다(v1.3 은 단발     ║
# ║        실패 31건으로 즉사했다). KRX 계열 호출은 단일 스레드 + 요청 간 1초 이상.             ║
# ║                                                                                          ║
# ║  붙여넣기: JupyterLab 셀 하나에 그대로. 또는  python axis_a_delta_v14.py                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 0. 인증정보 · 실행 경로   ─ 여기만 채우면 된다
# ══════════════════════════════════════════════════════════════════════════════════════════
#
#  ┌─ DART_API_KEY ─ 금융감독원 전자공시 OpenDART 인증키 (40자 16진 문자열). ★필수★
#  │   발급 URL : https://opendart.fss.or.kr/
#  │   절차     : [인증키 신청/관리] → [인증키 신청] → 이메일 인증 → 즉시 발급(무료).
#  │              별도 이용승인 절차 없음. 발급 즉시 전 엔드포인트 사용 가능.
#  │   한도     : 일 20,000건. 당일 소진량 확인은 로그인 후
#  │              https://opendart.fss.or.kr/mng/apiUsageStatus.do  (API 로는 조회 불가)
#  │   이 실행이 쓰는 엔드포인트 : exctvSttus(임원현황) · stockTotqySttus(주식총수, Plan C 전용)
#  │                              · corpCode(고유번호 zip, 1회)
#  └───────────────────────────────────────────────────────────────────────────────────────
DART_API_KEY = ""

#  ┌─ KRX_ID / KRX_PW ─ KRX Data Marketplace 회원 계정. ★Plan A·B 에 필요★
#  │   발급 URL : https://data.krx.co.kr/   (2025-12-27 개편 후 회원제)
#  │   절차     : 우측 상단 [로그인] → [회원가입] → 이메일 인증. **무료 · 이용신청 불필요**.
#  │              가입 즉시 사용 가능하다. KRX Open API 인증키와는 완전히 별개의 물건이며,
#  │              이번 실행은 Open API 승인을 기다리지 않는다(v1.3 명령서의 혼동 지점).
#  │   주의     : 비밀번호 정기변경 요구(로그인 응답 _error_code=CD010)에 걸려 있으면 로그인이
#  │              실패한다. 그 경우 위 사이트에서 비밀번호를 한 번 바꾸면 풀린다.
#  │   비워 두면 : Plan A 는 무자격 경로로만, Plan B 는 로그인 없이 세션만으로 시도한다.
#  │              둘 다 실패하면 Plan C(KRX 무의존 재구성)로 내려간다 — 측정은 계속된다.
#  └───────────────────────────────────────────────────────────────────────────────────────
KRX_ID = ""
KRX_PW = ""

#  PROJECT_ROOT ─ 로컬 SSD 경로. /content 계열이면 예외를 던지고 즉시 중단한다.
#                 (P0_LOCAL_ROOT_ONLY — WAIVED 허용 없음)
#                 Windows 예)  r"C:\Users\user\quant\phase0"
PROJECT_ROOT = r"C:\Users\user\quant\phase0"

#  GDRIVE_ROOT ─ 마운트된 구글드라이브 경로(선택). 비우면 로컬 전용으로 동작한다.
#     예) r"G:\My Drive\quant_cache"  ·  "~/Google Drive/My Drive/quant_cache"
GDRIVE_ROOT = ""

#  예상 신규 API 호출이 5,000건을 넘으면 스크립트가 인벤토리만 출력하고 멈춘다 (P0_CACHE_FIRST).
#  보고를 읽고 진행하기로 했다면 True 로 바꾸고 셀을 다시 실행한다.
CONFIRM_LARGE_COLLECTION = False

#  KONEX 포함 여부. 기본 False(=KOSPI+KOSDAQ). 판정표 methodology 에 기록된다.
INCLUDE_KONEX = False

#  동시 요청 워커 수. v1.3 의 4에서 2로 하향(§3.3) — 로컬 네트워크가 콜랩보다 불안정하다는 전제.
#  KRX 계열 호출은 이 값과 무관하게 항상 단일 스레드다(§8).
N_WORKERS = 2

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 1. 계약 — 이 실행이 스스로에게 거는 제약. 위반하면 조용히 넘어가지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
CONTRACTS = {
    "P0_MARKET_SOURCE_LADDER": "§2 의 Plan A→B→C 를 순서대로 시도. 각 단계 성패와 사유를 기록. "
                               "3단 실패 시 임원현황 수집 진입 금지",
    "P0_NO_URL_GUESSING":      "엔드포인트·파라미터를 추측으로 만들지 않는다. 응답 원문 덤프 또는 "
                               "설치된 라이브러리 소스에서 확인한 뒤 구현한다",
    "P0_DART_PREFLIGHT":       "단일 카나리로 연결을 확인하고 예외 유형을 분류하기 전에는 벌크 "
                               "수집에 진입하지 않는다",
    "P0_NO_VERIFY_FALSE":      "SSL 검증 비활성화 금지. 인증서 문제는 CA 번들 지정으로 해결한다",
    "P0_LOCAL_ROOT_ONLY":      "/content 계열 감지 시 예외 발생 후 중단. WAIVED 허용하지 않는다",
    "P0_PIT_STRICT_DELTA":     "as_of 는 실행일이 아니다. 스냅샷별 PIT 폐기 건수 필수 출력. 0건이면 중단",
    "P0_EMPTY_UNIVERSE_GUARD": "시총>0 종목 100 미만이면 수집 진입 금지",
    "P0_CACHE_FIRST":          "수집 전 인벤토리 출력. 예상 신규 호출 5,000건 초과 시 대기",
    "P0_NO_STRATEGY":          "팩터·시그널·수익률·백테스트 연산 금지",
    "P0_GRAPH_FULL_MEASURE_SUB": "그래프는 전 상장사, 측정은 하위 1,000종목",
    "P0_FAIL_LOUD":            "결측은 결측으로. 보간·추정 금지",
    "P0_NO_THRESHOLD_EDIT":    "임계값 frozen. 실행 중 변경 금지",
    "P0_LIVE_ONLY":            "합성 데이터 경로 금지. 전 상장사 노드 수 로그 출력",
    "NO_KNOWN_DEAD_CALL":      "pykrx.get_index_portfolio_deposit_file('1028') 금지",
}

# ── 임계값 (frozen). P0_NO_THRESHOLD_EDIT — 실행 중 어떤 이유로도 바꾸지 않는다. ────────────
#    아래 해시는 이 세 값에서 파생된다. 값을 고치면 해시가 어긋나 실행이 중단된다.
#    v1.3 과 동일한 값·동일한 해시다(임계 변경 없음).
GATE_THRESHOLDS = {"AD1_born_ratio_mean": 0.05, "AD2_born_total_median": 50, "A5_legacy": 600}
GATE_THRESHOLDS_SHA256 = "5377b9db1fab287d1417eec46f87c39e84a10db6b81f84bc64d087ffba3c0d35"

KNOWN_LIMITATIONS = [
    "AΔ-1=0.05, AΔ-2=50, A-5=600 은 경험적 근거 없이 설정된 임계값이다. 게이트 미달을 "
    "'전략 불가'로 읽어서는 안 된다. 실행 중 임계 변경은 금지되어 있다(P0_NO_THRESHOLD_EDIT).",
    "관측시점 정렬(A)을 채택했다. 유니버스(시총 하위 1,000종목)는 스냅샷 기준일에, 임원 "
    "데이터는 법정 제출기한(as_of)에 정렬된다 — 두 축의 기준일이 다르다.",
    "정정공시로 rcept_dt 가 as_of 를 넘는 레코드는 폐기된다. DART API 는 최신 리비전만 "
    "돌려주므로 정정 이전의 원본 내용을 복원할 수 없다. 해당 기업은 그 스냅샷에서 임원 "
    "데이터 결측으로 남는다(보간하지 않음 — P0_FAIL_LOUD).",
    "인물 동일성은 (성명, 출생년월) 로만 판정한다. 동명이인이 같은 출생년월을 가지면 "
    "실재하지 않는 엣지가 생성된다. 다수 종목 겸직자 상위 목록을 진단표에 함께 출력한다.",
    "출생년월 결측 레코드는 엣지 생성에서 제외된다. 제외 건수를 스냅샷별로 기록한다.",
    "edge_born/edge_died 는 '교집합 종목에 한쪽 끝이라도 걸친 엣지'를 센다. 상대 노드의 "
    "상장/폐지가 엣지 생성·소멸로 보일 수 있어, 양끝이 두 스냅샷 모두에 상장된 경우만 센 "
    "보조 수치(born_both_listed / died_both_listed)를 함께 기록한다.",
    "Plan C 가 채택된 경우: 시가총액은 KRX 공식 시총이 아니라 '발행주식총수 × 종가' "
    "재구성값이다. 절대 수준은 부정확할 수 있다. 이번 용도는 시총 하위 1,000종목이라는 "
    "순위 컷이므로 순위 보존성만 있으면 목적을 달성하지만, 이 수치를 다른 목적에 "
    "재사용해서는 안 된다.",
    "Plan C 의 종가는 FinanceDataReader 가 제공하는 수정주가다. 액면분할·병합 구간에서는 "
    "'현재 시점 발행주식총수 × 수정종가'가 당시 실제 시가총액과 어긋날 수 있다.",
    "Plan C 의 시장구분(KOSPI/KOSDAQ/KONEX)은 DART 응답의 corp_cls 를 쓴다. corp_cls 는 "
    "응답 시점의 분류이지 스냅샷 시점의 분류가 아니다 — 시장이전(코스닥→코스피)이 있었던 "
    "종목은 과거 스냅샷에서도 현재 시장으로 라벨링된다.",
    "일일 호출한도로 중단되면 resume_todo.json 을 남기고 다음 실행이 정확히 이어받는다. "
    "부분 수집 상태에서 만든 그래프는 '해당 스냅샷의 임원 데이터가 불완전하다'는 뜻이며, "
    "스냅샷별 cache_miss 건수로 그 사실이 판정표에 남는다.",
    "요청 범위에 '스몰캡 백테스트 비교'는 포함되지 않는다. 이 파일의 측정 대상 자체가 이미 "
    "시총 하위 1,000종목이고, 백테스트·수익률 연산은 P0_NO_STRATEGY 로 범위 밖이다.",
]

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 2. 표준 라이브러리 (서드파티는 자격증명 주입 이후에만 import 한다)
# ══════════════════════════════════════════════════════════════════════════════════════════
import os
import re
import io
import ast
import sys
import json
import time
import errno
import random
import hashlib
import zipfile
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
SPEC_VERSION = "v1.4"


class ContractViolation(RuntimeError):
    """계약 위반. 이 예외는 절대 삼키지 않는다."""


class DiskFull(RuntimeError):
    """로컬 ENOSPC. 즉시 실패한다 — 포맷 재시도 금지."""


class HardStop(RuntimeError):
    """예산 소진·서킷브레이커·인증 실패 등 계속할 수 없는 상태."""


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 3. 실행 경로 검사 (P0_LOCAL_ROOT_ONLY)
# ══════════════════════════════════════════════════════════════════════════════════════════
_FORBIDDEN_ROOT_PARTS = ("/content", "/gdrive", "/drive/mydrive")


def resolve_project_root(raw: str) -> Path:
    """/content 계열이면 예외를 던진다. WAIVED 우회는 없다."""
    root = Path(os.path.expanduser(str(raw or ""))).resolve()
    low = str(root).lower().replace("\\", "/")
    for bad in _FORBIDDEN_ROOT_PARTS:
        if low == bad or low.startswith(bad + "/"):
            raise ContractViolation(
                f"P0_LOCAL_ROOT_ONLY 위반: PROJECT_ROOT={root}\n"
                f"  '{bad}' 계열은 세션 종료와 함께 소멸한다.\n"
                f"  로컬 SSD 경로로 바꾸고 다시 실행할 것 (예: C:\\Users\\user\\quant\\phase0).\n"
                f"  이 계약에는 WAIVED 가 없다.")
    if "google.colab" in sys.modules:
        raise ContractViolation(
            "P0_LOCAL_ROOT_ONLY 위반: Colab 런타임이 감지되었다. 로컬 JupyterLab 에서 실행할 것.")
    return root


# 아래 전역은 _bootstrap() 이 채운다. 모듈 import 만으로는 아무 부작용도 일어나지 않게 해서,
# 순수 로직(PIT 필터·인물키·엣지·전이)을 네트워크와 자격증명 없이 따로 검증할 수 있게 한다.
ROOT = DIR_CACHE_RAW = DIR_CACHE_META = DIR_STATE = DIR_REPORTS = None
DIR_CACHE_MARKET = DIR_CACHE_PX = DIR_CACHE_SHARES = None
pd = requests = stock = fdr = None
PYKRX_AVAILABLE = False
PYKRX_DIAGNOSTIC = ""
FDR_AVAILABLE = False
PARQUET_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 4. 로깅 — 화면과 run_log.txt 에 동시에 쓴다
# ══════════════════════════════════════════════════════════════════════════════════════════
_LOG_LK = threading.Lock()
_LOG_FH = None


def _force_utf8_stdout() -> str:
    """Windows 콘솔 기본 인코딩(cp949)에서 로그가 통째로 죽는 것을 막는다.

    이 파일이 쓰는 문자 중 cp949 로 인코딩이 **불가능**한 것들이 있다:
      '—'(EM DASH) '✓' '✗' '═' '║' '╔' '╗' '╚' '╝'
    JupyterLab 은 stdout 이 UTF-8 이라 무사하지만, `python axis_a_delta_v14.py` 를
    cmd/PowerShell 에서 돌리면 첫 출력 줄에서 UnicodeEncodeError 로 즉사한다.
    """
    try:
        enc = (sys.stdout.encoding or "").lower()
    except Exception:                                        # noqa: BLE001
        enc = ""
    if enc.replace("-", "") in ("utf8", "utf8mb4"):
        return enc or "utf-8"
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Python 3.7+
        return "utf-8(reconfigured)"
    except Exception:                                        # noqa: BLE001
        return enc or "unknown"     # 실패해도 LOG() 가 줄 단위로 방어한다(아래)


def LOG(msg: str = "", tag: str = "") -> None:
    t = _dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}" if not tag else f"[{t}] {tag:<5} {msg}"
    with _LOG_LK:
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            # 콘솔이 못 그리는 글자는 '?' 로 바꿔서라도 출력한다. 화면이 조금 깨지는 것과
            # 실행이 죽는 것은 완전히 다른 문제다 — run_log.txt 에는 항상 원본이 남는다.
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(line.encode(enc, "replace").decode(enc, "replace"), flush=True)
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
    LOG("─" * 90)
    if title:
        LOG(title)
        LOG("─" * 90)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 5. 안전한 파일 입출력 — 로컬 ENOSPC 는 즉시 실패 (포맷 재시도 금지)
# ══════════════════════════════════════════════════════════════════════════════════════════
def _guard_enospc(e: BaseException, what: str):
    if isinstance(e, OSError) and getattr(e, "errno", None) == errno.ENOSPC:
        raise DiskFull(f"디스크 공간 없음(ENOSPC): {what} — 재시도하지 않는다. "
                       f"공간을 확보한 뒤 다시 실행할 것.") from e


def _replace_with_retry(tmp: Path, path: Path, tries: int = 6) -> None:
    """POSIX 의 rename(2) 은 대상이 열려 있어도 성공하지만 Windows 는 다르다.

    MoveFileEx 는 tmp 나 목적지에 다른 프로세스의 핸들이 하나라도 남아 있으면
    PermissionError(WinError 5) 또는 OSError(WinError 32) 를 던진다. 방금 닫힌 .json 을
    실시간 검사하는 Windows Defender, 폴더를 훑는 드라이브 동기화 클라이언트가 대표적인
    원인이고 둘 다 수백 ms 안에 손을 뗀다. 여기서 포기하면 이미 API 호출을 써서 받아 온
    응답을 그냥 버리는 셈이다. ENOSPC 는 기다려도 안 풀리므로 즉시 올려보낸다.
    """
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except OSError as e:
            if getattr(e, "errno", None) == errno.ENOSPC:
                raise
            transient = isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32)
            if not transient or i == tries - 1:
                raise
            time.sleep(0.08 * (2 ** i) * random.uniform(0.8, 1.2))


def write_bytes(path: Path, data: bytes) -> None:
    # 스레드마다 다른 tmp 이름을 쓴다 — 같은 경로를 두 워커가 동시에 쓰면 서로의 tmp 를
    # 지워 버리는 사고가 난다(finally 의 unlink 가 남의 파일을 지우는 형태로).
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}_{threading.get_ident()}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass                                   # 일부 FUSE 드라이브 마운트는 fsync 미지원
        _replace_with_retry(tmp, path)
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


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def append_jsonl(path: Path, rows) -> None:
    """append-only. 기존 줄은 절대 다시 쓰지 않는다."""
    if not rows:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except OSError as e:
        _guard_enospc(e, str(path))
        raise


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 6. 정규화 헬퍼
# ══════════════════════════════════════════════════════════════════════════════════════════
_PAREN = re.compile(r"[(（\[][^)）\]]*[)）\]]")
_WS = re.compile(r"[\s 　]+")
_BIRTH = re.compile(r"(\d{4})\s*[년.\-/]?\s*(\d{1,2})")

# 2024-01-01 종목코드 개편으로 영숫자 코드가 도입되었다: 앞 4자리 숫자 + 5번째(0-9,A-Z 중
# I/O/U 제외) + 6번째(0,K,L,M,N). 단순히 숫자만 남기면 이런 신형 티커가 조용히 망가진다
# (예: '09701K' → 숫자만 남기면 '09701' → zfill 로 '009701', 완전히 다른 종목이 된다).
_TICKER_RE = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])$")
_NONDIGIT = re.compile(r"\D")


def to_code6(v) -> str:
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드. 실패하면 ''."""
    if v is None:
        return ""
    try:
        if isinstance(v, float) and not (v == v):          # NaN
            return ""
    except Exception:                                       # noqa: BLE001
        pass
    s = re.sub(r"\s", "", str(v).strip().upper()).split(".")[0]
    if len(s) == 7 and s[0] in "AQ" and _TICKER_RE.match(s[1:]):
        s = s[1:]
    if _TICKER_RE.match(s):
        return s
    d = _NONDIGIT.sub("", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
        return cand if _TICKER_RE.match(cand) else ""
    return ""


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


def _to_int(v):
    """'1,234,567' · '1234567' · 1234567 → int. 실패하면 None (0으로 추정하지 않는다)."""
    s = re.sub(r"[,\s]", "", str(v if v is not None else "")).strip()
    if not s or s in ("-", "--"):
        return None
    neg = s.startswith("-")
    s = _NONDIGIT.sub("", s)
    if not s:
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return -n if neg else n


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def spearman(xs, ys):
    """스피어만 순위상관. scipy 없이 '순위로 바꾼 뒤 피어슨'으로 계산한다(정의상 동일).

    동점은 평균순위로 처리한다 — 시가총액에 동점이 거의 없더라도 정의를 지키는 쪽이 옳다.
    """
    n = len(xs)
    if n != len(ys) or n < 3:
        return None

    def _rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _rank(list(xs)), _rank(list(ys))
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 7. 부트스트랩 — 자격증명 env 주입 → pykrx 방탄 import (순서를 코드가 강제한다)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  pykrx 1.2.8 은 `from pykrx import stock` 하는 순간 website/comm/webio.py 12행에서
#  build_krx_session() 을 실행한다. 그 함수는 os.getenv("KRX_ID")/("KRX_PW") 를 **기본
#  인자값으로** 읽는다 — 즉 import 시점에 환경변수가 이미 있어야 로그인을 시도하고, 없으면
#  로그인 자체를 건너뛴다. 그래서 자격증명 주입은 **반드시 최초 import 보다 먼저** 일어나야
#  한다(v1.3 에서 KRX_ENV_TOO_LATE 경고가 났던 지점).
#
#  그리고 login_krx() 는 resp.json() 을 try/except 없이 호출하므로, KRX 가 JSON 이 아닌
#  응답(로그인 페이지·차단·점검 안내)을 주면 JSONDecodeError 가 import 문에서 그대로 터진다.
#  이걸 코드로 막는 유일한 방법은 import 자체를 넓은 except 로 감싸는 것뿐이다 — 특정 예외
#  타입으로 좁혀 잡으면 다음 버전에서 예외 종류가 바뀌는 순간 다시 뚫린다.
# ══════════════════════════════════════════════════════════════════════════════════════════
PYKRX_IMPORT_LOG = {
    "env_injected_before_import": False,
    "purged_stale_modules": 0,
    "env_too_late": False,
    "attempts": [],
}


def _ensure_packages(pkgs) -> None:
    """find_spec 은 모듈을 '실행'하지 않는다 — pykrx 를 여기서 import 하면 안 되기 때문이다."""
    missing = [p for p in pkgs if importlib.util.find_spec(p.replace("-", "_")) is None]
    if not missing:
        return
    LOG(f"의존 패키지 설치: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=False)
    importlib.invalidate_caches()


def _purge_pykrx_modules() -> int:
    stale = [m for m in list(sys.modules) if m == "pykrx" or m.startswith("pykrx.")]
    for m in stale:
        del sys.modules[m]
    return len(stale)


def inject_krx_env() -> None:
    """KRX 자격증명을 os.environ 에 넣는다. pykrx 를 처음 import 하기 '전에' 불려야 한다.

    이미 pykrx 가 로드돼 있으면(셀 재실행·다른 코드가 먼저 import 한 경우) 그 인스턴스는
    옛 환경으로 로그인 세션을 만들어 둔 상태다 — sys.modules 에서 걷어내고 표시를 남긴다.
    """
    already = [m for m in sys.modules if m == "pykrx" or m.startswith("pykrx.")]
    PYKRX_IMPORT_LOG["env_too_late"] = bool(already)
    PYKRX_IMPORT_LOG["purged_stale_modules"] = _purge_pykrx_modules()
    if str(KRX_ID or "").strip() and str(KRX_PW or "").strip():
        os.environ["KRX_ID"] = KRX_ID.strip()
        os.environ["KRX_PW"] = KRX_PW.strip()
    else:
        os.environ.pop("KRX_ID", None)
        os.environ.pop("KRX_PW", None)
    PYKRX_IMPORT_LOG["env_injected_before_import"] = True


def _try_import_pykrx(with_creds: bool):
    """단일 시도. 성공하면 (stock모듈, ''), 실패하면 (None, 예외 전문). 절대 예외를 던지지 않는다."""
    _purge_pykrx_modules()
    importlib.invalidate_caches()
    if with_creds and str(KRX_ID or "").strip() and str(KRX_PW or "").strip():
        os.environ["KRX_ID"] = KRX_ID.strip()
        os.environ["KRX_PW"] = KRX_PW.strip()
    else:
        os.environ.pop("KRX_ID", None)
        os.environ.pop("KRX_PW", None)
    buf = io.StringIO()
    try:
        import contextlib as _ctx
        with _ctx.redirect_stdout(buf):
            from pykrx import stock as _stock   # ← 여기서 실제 로그인 네트워크 I/O 가 돈다
        return _stock, "", buf.getvalue()
    except BaseException as e:                       # noqa: BLE001 — 의도적으로 전부 잡는다
        _purge_pykrx_modules()
        return None, f"{type(e).__module__}.{type(e).__qualname__}: {e}", buf.getvalue()


def import_pykrx_guarded():
    """자격증명 포함 → 실패 시 무자격, 두 경로 모두 예외 전문을 로그에 남긴다.

    v1.3 은 자격증명 포함 시도의 실패를 흡수하고 조용히 무자격 재시도로 넘어가면서 문제를
    감췄다. 여기서는 두 시도의 결과를 모두 기록하고, 무자격으로 로드됐다면 '로그인은 실패한
    상태'라는 사실을 명시한다 — pykrx 의 Get/Post 는 세션이 없으면 익명 requests.Session
    으로 폴백하므로 조회가 될 수도, 안 될 수도 있다. 그 판정은 카나리가 한다.
    """
    global PYKRX_AVAILABLE, PYKRX_DIAGNOSTIC
    has_creds = bool(str(KRX_ID or "").strip() and str(KRX_PW or "").strip())

    st1, err1, out1 = _try_import_pykrx(with_creds=True)
    PYKRX_IMPORT_LOG["attempts"].append(
        {"with_creds": has_creds, "ok": st1 is not None, "error": err1,
         "pykrx_stdout": out1.strip()[:600]})
    if out1.strip():
        for ln in out1.strip().splitlines()[:6]:
            LOG(f"    [pykrx] {ln}")
    if st1 is not None:
        PYKRX_AVAILABLE = True
        PYKRX_DIAGNOSTIC = ""
        return st1

    ERR(f"pykrx import 실패({'자격증명 포함' if has_creds else '무자격'}): {err1}")
    ERR("  이것은 이 스크립트의 결함이 아니라 pykrx 1.2.8 의 결함이다 — login_krx() 가 "
        "resp.json() 을 try/except 없이 호출한다(website/comm/auth.py).")

    st2, err2, out2 = _try_import_pykrx(with_creds=False)
    PYKRX_IMPORT_LOG["attempts"].append(
        {"with_creds": False, "ok": st2 is not None, "error": err2,
         "pykrx_stdout": out2.strip()[:600]})
    if st2 is not None:
        PYKRX_AVAILABLE = True
        PYKRX_DIAGNOSTIC = f"무자격으로만 로드됨(로그인 실패). 자격증명포함 시도: {err1}"
        WARN("  무자격 재시도로 pykrx 는 로드됐다. 다만 KRX 로그인은 실패한 상태이므로 "
             "조회가 실제로 되는지는 카나리가 판정한다(v1.3 은 여기서 판정 없이 진행했다).")
        return st2

    PYKRX_AVAILABLE = False
    PYKRX_DIAGNOSTIC = f"자격증명포함: {err1} / 무자격: {err2}"
    ERR(f"pykrx 를 어떤 방식으로도 로드하지 못했다: {PYKRX_DIAGNOSTIC}")
    return None


def pykrx_call(fn_name: str, *a, **kw):
    """모든 pykrx 호출의 유일한 통로. 절대 예외를 밖으로 내보내지 않는다.

    pykrx 는 import 이후에도 세션 만료 시 재로그인을 시도하며 같은 종류의 무방비 JSON
    파싱을 또 탄다 — import 가 살아남았다고 이후 호출이 안전하다는 보장이 없다.
    stdout 에 직접 뿌리는 'Error occurred in ...' 스팸도 여기서 가로챈다.
    """
    if not PYKRX_AVAILABLE or stock is None:
        return None
    fn = getattr(stock, fn_name, None)
    if fn is None:
        return None
    import contextlib as _ctx
    buf = io.StringIO()
    try:
        with _ctx.redirect_stdout(buf):
            return fn(*a, **kw)
    except BaseException as e:                          # noqa: BLE001
        WARN(f"    pykrx.{fn_name} 호출 실패({type(e).__name__}: {str(e)[:120]})")
        return None


_DEAD_CALL_NAME = "get_index_portfolio_deposit_file"


def _arm_dead_call_guard(mod) -> bool:
    """NO_KNOWN_DEAD_CALL: '쓰지 않는다'로 끝내지 않고, 호출되면 터지게 만든다."""
    if mod is None or not hasattr(mod, _DEAD_CALL_NAME):
        return False

    def _dead_call(*a, **k):
        raise ContractViolation(
            f"NO_KNOWN_DEAD_CALL 위반: {_DEAD_CALL_NAME}{a!r} 는 사용이 금지된 호출이다.")

    setattr(mod, _DEAD_CALL_NAME, _dead_call)
    return True


def _try_import_fdr():
    """FinanceDataReader — Plan C 의 종가 소스. 없으면 Plan C 를 쓸 수 없다."""
    global FDR_AVAILABLE
    try:
        import FinanceDataReader as _fdr
        FDR_AVAILABLE = True
        return _fdr
    except Exception as e:                               # noqa: BLE001
        FDR_AVAILABLE = False
        WARN(f"  FinanceDataReader import 실패({type(e).__name__}: {e}) — Plan C 는 쓸 수 없다")
        return None


def _check_parquet() -> bool:
    global PARQUET_AVAILABLE
    PARQUET_AVAILABLE = importlib.util.find_spec("pyarrow") is not None or \
        importlib.util.find_spec("fastparquet") is not None
    return PARQUET_AVAILABLE


# ── P0_NO_VERIFY_FALSE 자기검사 ─────────────────────────────────────────────────────────────
#   '쓰지 않았다'는 선언 대신, 자기 소스를 읽어 실제로 없는지 확인한다. 셀 붙여넣기 실행처럼
#   __file__ 이 없는 경우에는 검사 자체가 불가능하므로 그 사실을 그대로 표기한다(가장한 PASS 금지).
_VERIFY_OFF_PATTERN = re.compile(r"verify\s*=\s*(?:False|0)\b")


def assert_no_verify_false() -> str:
    try:
        src = Path(__file__).read_text(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        return "UNCHECKABLE(소스 파일 접근 불가 — 셀 붙여넣기 실행)"
    bad = []
    for i, line in enumerate(src.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _VERIFY_OFF_PATTERN.search(line):
            bad.append(f"{i}: {s[:90]}")
    if bad:
        raise ContractViolation(
            "P0_NO_VERIFY_FALSE 위반: SSL 검증을 끄는 코드가 있다.\n  " + "\n  ".join(bad) +
            "\n  인증서 문제는 REQUESTS_CA_BUNDLE 에 회사 루트 인증서를 지정해 해결할 것.")
    return "ENFORCED(소스 자기검사 통과)"


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 8. 엔드포인트 출처 레지스트리 (P0_NO_URL_GUESSING)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  이 실행이 때리는 모든 URL 은 여기에 '어디서 확인했는가'와 함께 등록된 것만 쓴다.
#  provenance 종류:
#    LIBRARY_SOURCE  설치된 pykrx 소스에서 ast 로 읽어냄 (파일:줄번호까지 기록)
#    OFFICIAL_DOC    OpenDART 공식 문서 + v1.2/v1.3 실사용으로 검증된 엔드포인트
#    RESPONSE_DUMP   응답 원문을 떠서 눈으로 확인한 뒤 등록
#  추측으로 만든 URL 은 등록할 수 없다 — register 시 provenance 가 비면 예외가 난다.
# ══════════════════════════════════════════════════════════════════════════════════════════
ENDPOINT_REGISTRY: dict = {}
_ENDPOINT_LK = threading.Lock()


def register_endpoint(key: str, url: str, provenance: str, detail: str = "") -> str:
    if not url or not provenance:
        raise ContractViolation(
            f"P0_NO_URL_GUESSING 위반: '{key}' 를 출처 없이 등록하려 했다 "
            f"(url={url!r}, provenance={provenance!r}).")
    with _ENDPOINT_LK:
        ENDPOINT_REGISTRY[key] = {"url": url, "provenance": provenance, "detail": detail}
    return url


def endpoint(key: str) -> str:
    with _ENDPOINT_LK:
        e = ENDPOINT_REGISTRY.get(key)
    if not e:
        raise ContractViolation(
            f"P0_NO_URL_GUESSING 위반: 등록되지 않은 엔드포인트 '{key}' 를 호출하려 했다.")
    return e["url"]


# DART 엔드포인트 — OpenDART 공식 문서에 명시된 고정 URL 이고 v1.2(12,165콜)/v1.3 에서
# 실제로 응답을 받아 본 것들이다. 추측이 아니다.
DART_BASE = "https://opendart.fss.or.kr/api"
register_endpoint("dart_exctv", f"{DART_BASE}/exctvSttus.json", "OFFICIAL_DOC",
                  "OpenDART DS002 임원현황. v1.2 에서 12,165콜 정상 처리 실적")
register_endpoint("dart_stock_totqy", f"{DART_BASE}/stockTotqySttus.json", "OFFICIAL_DOC",
                  "OpenDART DS002 주식의총수 현황. Plan C 의 발행주식총수 소스")
register_endpoint("dart_corpcode", f"{DART_BASE}/corpCode.xml", "OFFICIAL_DOC",
                  "OpenDART 고유번호 전체 ZIP. v1.2/v1.3 에서 3,981건 파싱 실적")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 9. 레이트 리미터 — DART 는 0.3~1.0초 랜덤, KRX 계열은 단일 스레드 + 1초 이상 (§8)
# ══════════════════════════════════════════════════════════════════════════════════════════
class RandomDelay:
    """요청 간 0.3~1.0초 랜덤 지연. v1.3 의 적응형 가속은 쓰지 않는다 —
    로컬 네트워크가 불안정하다는 전제에서는 '빨라지는 것'이 위험이지 이득이 아니다."""

    def __init__(self, lo: float = 0.3, hi: float = 1.0):
        self.lo, self.hi = lo, hi

    def wait(self) -> None:
        time.sleep(random.uniform(self.lo, self.hi))

    @property
    def cur(self) -> float:
        return (self.lo + self.hi) / 2.0


class SerialGate:
    """KRX 계열 전용. 단일 스레드 + 요청 간 최소 간격을 구조로 강제한다.

    KRX 는 과도한 접속을 차단 사유로 명시한 전례가 있다. '동시성 금지'를 주석으로 적어 두는
    대신 락으로 직렬화한다 — 다른 코드가 스레드풀에서 불러도 동시에 두 요청이 나갈 수 없다.
    """

    def __init__(self, min_interval: float = 1.0):
        self.min_interval = min_interval
        self.lk = threading.Lock()
        self.last = 0.0
        self.calls = 0

    def __enter__(self):
        self.lk.acquire()
        gap = time.time() - self.last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self.calls += 1
        return self

    def __exit__(self, *exc):
        self.last = time.time()
        self.lk.release()
        return False


KRX_GATE = SerialGate(1.0)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 10. 캐시 — 로컬 1차, 드라이브는 보조. skip-if-exists.
# ══════════════════════════════════════════════════════════════════════════════════════════
#    cache/raw/dart_exctv/{corp_code}/{year}_{reprt}.json   임원현황 원본 응답
#    cache/raw/dart_shares/{corp_code}/{year}_{reprt}.json  주식총수 원본 응답 (Plan C)
#    cache/raw/px/{ticker}/{year}.parquet                   일별 종가 (Plan C, 명령서 §2.3-3)
#    cache/market/krx_market_{YYYYMMDD}.csv                 KRX 실측 전종목 시총 (Plan A/B)
#    cache/market/planc_mcap_{YYYYMMDD}.csv                 Plan C 재구성 시총
#    cache/meta/{dart_corpcode.csv, corpCode.zip}
#    cache/state/call_budget_YYYYMMDD.json
#  ★ 캐시는 API 원본 응답을 저장한다. PIT 필터는 읽은 뒤에 적용한다 —
#    그래서 as_of 가 달라져도 기존 캐시는 전부 재사용 가능하다(§4.2).
# ══════════════════════════════════════════════════════════════════════════════════════════
GDRIVE_SHARED_NS = "_shared"


def _drive_root():
    if not str(GDRIVE_ROOT or "").strip():
        return None
    return Path(os.path.expanduser(GDRIVE_ROOT)).resolve()


def drive_shared(*parts):
    d = _drive_root()
    if d is None:
        return None
    p = d / GDRIVE_SHARED_NS
    for part in parts:
        p = p / part
    return p


def cache_path(corp_code: str, year: str, reprt: str) -> Path:
    return DIR_CACHE_RAW / str(corp_code) / f"{year}_{reprt}.json"


def shares_path(corp_code: str, year: str, reprt: str) -> Path:
    return DIR_CACHE_SHARES / str(corp_code) / f"{year}_{reprt}.json"


def px_path(ticker: str, year: int) -> Path:
    ext = "parquet" if PARQUET_AVAILABLE else "csv"
    return DIR_CACHE_PX / str(ticker) / f"{year}.{ext}"


def _drive_blob_path(kind: str, corp_code: str, year: str, reprt: str):
    return drive_shared("blob", "dart", kind, str(corp_code), f"{year}_{reprt}.json")


def _safe_copy(src: Path, dst: Path) -> bool:
    """로컬 목적지가 이미 있으면 손대지 않는다. 원격(드라이브) 오류는 경고만 하고 계속한다."""
    if dst.exists():
        return False
    try:
        data = src.read_bytes()
    except OSError:
        return False
    try:
        write_bytes(dst, data)
        return True
    except DiskFull:
        raise
    except OSError as e:
        WARN(f"    드라이브 동기화 실패({type(e).__name__}): {dst}")
        return False


def restore_blobs_from_drive(kind: str, keys) -> int:
    """로컬에 없는 것만 드라이브에서 당겨온다(skip-if-exists)."""
    if _drive_root() is None:
        return 0
    local_fn = cache_path if kind == "exctv" else shares_path
    n = 0
    for cp, yy, rc in keys:
        local = local_fn(cp, yy, rc)
        if local.exists():
            continue
        remote = _drive_blob_path(kind, cp, yy, rc)
        if remote is None or not remote.exists():
            continue
        if _safe_copy(remote, local):
            n += 1
    return n


def sync_blobs_to_drive(kind: str, keys) -> dict:
    """로컬에 있는 파일을 드라이브에 증분 동기화한다. 스냅샷 수집이 끝날 때마다 부른다 —
    실행이 중간에 죽어도 그때까지 받은 건 안전하다."""
    out = {"attempted": False, "synced": 0, "already_there": 0, "local_missing": 0, "error": ""}
    if _drive_root() is None:
        return out
    out["attempted"] = True
    local_fn = cache_path if kind == "exctv" else shares_path
    for cp, yy, rc in keys:
        local = local_fn(cp, yy, rc)
        if not local.exists():
            out["local_missing"] += 1
            continue
        remote = _drive_blob_path(kind, cp, yy, rc)
        if remote is None:
            continue
        if remote.exists():
            out["already_there"] += 1
            continue
        try:
            write_bytes(remote, local.read_bytes())
            out["synced"] += 1
        except DiskFull:
            raise
        except OSError as e:
            out["error"] = f"{type(e).__name__}: {e}"
            WARN(f"    드라이브 동기화 중단({out['error']}) — 로컬 캐시는 안전하다.")
            break
    return out


def restore_shared_table(name: str, local_path: Path) -> bool:
    if local_path.exists():
        return False
    remote = drive_shared("table", f"{name}.csv")
    if remote is None or not remote.exists():
        return False
    return _safe_copy(remote, local_path)


def publish_shared_table(name: str, local_path: Path) -> bool:
    remote = drive_shared("table", f"{name}.csv")
    if remote is None or not local_path.exists():
        return False
    try:
        write_bytes(remote, local_path.read_bytes())
        return True
    except DiskFull:
        raise
    except OSError as e:
        WARN(f"    {name} 공용 인덱스 게시 실패: {e}")
        return False


def journal_append(rows) -> None:
    append_jsonl(DIR_CACHE_META / "journal_officer.jsonl", rows)
    rj = drive_shared("index", "journal.jsonl")
    if rj is not None:
        try:
            append_jsonl(rj, rows)
        except DiskFull:
            raise
        except OSError as e:
            WARN(f"    드라이브 저널 append 실패(로컬 저널은 정상): {e}")


def scan_blob_inventory(root: Path):
    """(year, reprt) → set(corp_code). 파일 하나하나를 열지 않고 파일명만 읽는다."""
    inv = defaultdict(set)
    if root is None or not root.exists():
        return inv
    try:
        with os.scandir(root) as corps:
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


def count_px_cached() -> int:
    if DIR_CACHE_PX is None or not DIR_CACHE_PX.exists():
        return 0
    try:
        return sum(1 for d in os.scandir(DIR_CACHE_PX) if d.is_dir())
    except OSError:
        return 0


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 11. 스냅샷 명세 — 관측시점 정렬(A) 채택 (FROZEN, 변경 금지)
# ══════════════════════════════════════════════════════════════════════════════════════════
ALIGNMENT = "A_OBSERVATION_TIME"
REPRT_NAME = {"11011": "사업", "11012": "반기", "11013": "1분기", "11014": "3분기"}
_DEADLINE_DAYS = {"11011": 90, "11012": 45, "11013": 45, "11014": 45}

SNAPSHOT_SPEC = [
    # id,   기준일(nominal), 결산기준일,     bsns_year, reprt_code, as_of(FROZEN), 필요건수
    ("S1", "2025-06-30", "2025-06-30", "2025", "11012", "2025-08-14", 2760),
    ("S2", "2025-09-30", "2025-09-30", "2025", "11014", "2025-11-14", 2765),
    ("S3", "2025-12-31", "2025-12-31", "2025", "11011", "2026-03-31", 2790),
    ("S4", "2026-03-31", "2026-03-31", "2026", "11013", "2026-05-15", 2763),
]

TRANSITIONS = [("S1", "S2"), ("S2", "S3"), ("S3", "S4")]
MEASURE_N = 1000            # 측정 대상 = 시총 하위 1,000종목
EMPTY_UNIVERSE_MIN = 100    # 시총>0 이 이보다 적으면 수집 진입 금지
TRADING_DAY_LOOKBACK = 10   # 직전 거래일 탐색 최대 역행 일수
HOMONYM_FLAG_K = 8          # 이 이상 종목에 겸직으로 잡히는 인물은 동명이인 의심으로 진단 출력
LARGE_COLLECTION_GATE = 5000

# ── 호출 예산 (§4.3) ────────────────────────────────────────────────────────────────────────
#   일일 한도 19,500(DART 실한도 20,000 대비 안전마진). 누적 12,000 도달 시 중단하고
#   resume_todo.json 을 저장한다 — 명령서 §4.3 의 명시 지시다.
#   ※ 한 가지 짚어 둔다: 4개 스냅샷 콜드 수집의 실 필요량은 ~11,078건이라 12,000 과의 여유가
#     ~900건뿐이다. 재시도가 섞이면 정상적인 콜드런도 12,000 에서 한 번 멎을 수 있다.
#     그 경우는 '실패'가 아니라 '중단'이며, resume_todo.json 을 두고 다음 실행이 정확히
#     이어받는다(캐시는 전부 재사용된다). 임계는 명령서대로 두고, 이 사실만 기록해 둔다.
CALL_BUDGET_DAILY = 19500
CALL_BUDGET_STOP_CUMULATIVE = 12000
CIRCUIT_FAIL_N = 10          # '재시도를 모두 소진한 콜'이 연속 이만큼이면 서킷 발동
CIRCUIT_SLEEP = 60
CIRCUIT_MAX_TRIPS = 3
HTTP_TIMEOUT = 30
MAX_RETRY_PER_CALL = 3       # 최초 1회 + 재시도 3회 = 최대 4 시도
BACKOFF_SECONDS = (2, 4, 8)


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
                f"P0_PIT_STRICT_DELTA 위반: {sid} 의 as_of 가 실행일({today})과 같다.")


def _sha256_thresholds() -> str:
    return hashlib.sha256(
        json.dumps(GATE_THRESHOLDS, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _dart_status_msg(code: str) -> str:
    return {
        "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
        "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
        "020": "요청 제한 초과(일 20,000건)", "021": "조회 가능한 회사 개수 초과",
        "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검",
        "900": "정의되지 않은 오류", "901": "사용자 계정의 개인정보보호 요청",
    }.get(str(code), "알 수 없음")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 12. DART HTTP 계층 + 연결 진단 (§3)   ─ P0_DART_PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════════════════════
#  v1.3 은 로컬 Windows 에서 31콜이 전부 net_error 로 죽고 서킷브레이커에 걸렸다. 같은 코드가
#  v1.2(Colab)에서는 12,165콜을 정상 처리했다. 벌크에 들어가기 전에 '무엇이 막고 있는가'를
#  단일 카나리 1콜로 확정한다. 예외 타입을 뭉뚱그려 net_error 로 세면 원인을 영영 모른다.
# ══════════════════════════════════════════════════════════════════════════════════════════
#  분류표(§3.2). requests 의 예외 계층은 ProxyError·SSLError·ConnectTimeout 이 전부
#  ConnectionError 의 하위 클래스라, 반드시 '구체적인 것부터' 훑어야 한다. MRO 전체의
#  클래스 이름을 모아 순서대로 매칭한다.
_DART_EXC_RULES = [
    (("SSLCertVerificationError", "CertificateError", "SSLError"),
     "사내망 SSL 인터셉트(중간자 인증서)",
     "회사 루트 인증서를 REQUESTS_CA_BUNDLE 환경변수에 지정할 것. "
     "예) os.environ['REQUESTS_CA_BUNDLE'] = r'C:\\certs\\corp_root.pem'  "
     "— SSL 검증을 끄는 우회는 이 실행에서 금지되어 있다(P0_NO_VERIFY_FALSE).",
     True),
    (("ProxyError", "ProxySchemeUnknown", "InvalidProxyURL"),
     "프록시 미설정 또는 프록시 설정 오류",
     "HTTP_PROXY / HTTPS_PROXY 환경변수를 사내 프록시로 설정할 것. "
     "예) os.environ['HTTPS_PROXY'] = 'http://proxy.corp:8080'",
     True),
    (("ReadTimeout", "ConnectTimeout", "Timeout"),
     "타임아웃 과소 또는 회선 지연",
     f"타임아웃을 {HTTP_TIMEOUT}초로 상향한 상태다. 그래도 계속되면 회선/프록시 지연을 확인할 것.",
     True),
    (("NameResolutionError", "gaierror"),
     "DNS 해석 실패 — opendart.fss.or.kr 을 못 찾는다",
     "망 문제다. 코드로 해결할 수 없다 — DNS/방화벽 담당자에게 확인할 것.",
     False),
    (("NewConnectionError", "ConnectionRefusedError", "ConnectionResetError", "ConnectionError"),
     "연결 거부/차단 — 방화벽이 막고 있을 가능성이 높다",
     "망 문제다. 코드로 해결할 수 없다 — 방화벽에서 opendart.fss.or.kr:443 허용을 요청할 것.",
     False),
]


def classify_dart_exception(exc: BaseException):
    """반환 (분류, 조치, code_fixable). 예외 계층 전체를 보고 구체적인 규칙부터 맞춘다."""
    names = {c.__name__ for c in type(exc).__mro__}
    for keys, cause, action, fixable in _DART_EXC_RULES:
        if names & set(keys):
            return cause, action, fixable
    return (f"미분류 예외({type(exc).__name__})",
            "예외 전문을 그대로 보고할 것 — 분류표에 없는 유형이다.", False)


def dart_request(key: str, params: dict, timeout: int = HTTP_TIMEOUT, session=None) -> dict:
    """DART 단일 요청. 예외를 삼키지 않고 '무엇이 어떻게 실패했는지'를 구조로 돌려준다.

    반환 dict:
      ok            bool          — 응답을 받았고 파싱까지 됐는가
      exc_type      str           — 예외 전체 이름 (requests.exceptions.SSLError 형태)
      exc_message   str           — 예외 메시지 전문
      http_status   int|None
      body_head     str           — 응답 본문 앞 500자
      json          dict|None
      elapsed       float
    """
    out = {"ok": False, "exc_type": "", "exc_message": "", "http_status": None,
           "body_head": "", "json": None, "elapsed": 0.0}
    s = session if session is not None else requests
    t0 = time.time()
    try:
        r = s.get(endpoint(key), params=params, timeout=timeout,
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                         "phase0-axisA-delta/1.4"})
    except BaseException as e:                              # noqa: BLE001
        out["elapsed"] = time.time() - t0
        out["exc_type"] = f"{type(e).__module__}.{type(e).__qualname__}"
        out["exc_message"] = str(e)
        return out
    out["elapsed"] = time.time() - t0
    out["http_status"] = r.status_code
    try:
        out["body_head"] = r.text[:500]
    except Exception:                                        # noqa: BLE001
        out["body_head"] = "(본문 디코딩 실패)"
    try:
        out["json"] = r.json()
        out["ok"] = True
    except ValueError as e:
        out["exc_type"] = f"{type(e).__module__}.{type(e).__qualname__}"
        out["exc_message"] = f"응답이 JSON 이 아니다: {e}"
    return out


DART_PREFLIGHT = {"done": False, "ok": False, "code_fixable": True, "classification": "",
                  "action": "", "detail": {}}
# 카나리 대상: 삼성전자(00126380) × S1 보고서(2025/11012). 명령서 §3.1 이 예시로 든 corp_code 다.
# 필요한 조회이기도 해서(S1 유니버스에 삼성전자가 없더라도 캐시는 남는다) 응답이 정상이면
# 그대로 캐시에 저장해 호출 1건을 낭비하지 않는다.
PREFLIGHT_CORP = "00126380"
PREFLIGHT_YEAR = "2025"
PREFLIGHT_REPRT = "11012"


def run_dart_preflight() -> dict:
    """단일 카나리 1콜 → 예외 유형 분류. 벌크 수집 전 반드시 통과해야 한다(P0_DART_PREFLIGHT).

    멱등이다 — 여러 곳에서 불려도 실제 호출은 한 번뿐이다. Plan C 는 DART 를 쓰므로
    Plan C 카나리보다 먼저 이 진단이 돌아야 실패 원인을 옳게 귀속할 수 있다.
    """
    if DART_PREFLIGHT["done"]:
        return DART_PREFLIGHT
    DART_PREFLIGHT["done"] = True

    RULE("§3. DART 연결 진단 — 단일 카나리 1콜 (벌크 진입 전 필수)")
    LOG(f"  대상: exctvSttus.json  corp_code={PREFLIGHT_CORP} "
        f"bsns_year={PREFLIGHT_YEAR} reprt_code={PREFLIGHT_REPRT}  timeout={HTTP_TIMEOUT}s")

    res = dart_request("dart_exctv",
                       {"crtfc_key": DART_API_KEY.strip(), "corp_code": PREFLIGHT_CORP,
                        "bsns_year": PREFLIGHT_YEAR, "reprt_code": PREFLIGHT_REPRT})

    det = {"endpoint": endpoint("dart_exctv"), "corp_code": PREFLIGHT_CORP,
           "bsns_year": PREFLIGHT_YEAR, "reprt_code": PREFLIGHT_REPRT,
           "elapsed_sec": round(res["elapsed"], 3),
           "exception_type": res["exc_type"] or None,
           "exception_message": res["exc_message"] or None,
           "http_status": res["http_status"],
           "response_body_head_500": res["body_head"],
           "timeout_sec": HTTP_TIMEOUT,
           "retry_policy": f"콜당 최대 {MAX_RETRY_PER_CALL}회 재시도 / 백오프 "
                           f"{'/'.join(str(x) for x in BACKOFF_SECONDS)}초",
           "circuit_rule": f"재시도를 모두 소진한 콜이 연속 {CIRCUIT_FAIL_N}건이면 발동",
           "workers": N_WORKERS}

    LOG(f"  예외 타입     : {res['exc_type'] or '(없음 — 응답 도달)'}")
    if res["exc_message"]:
        for ln in str(res["exc_message"]).splitlines()[:6]:
            LOG(f"  예외 메시지   : {ln}")
    LOG(f"  HTTP 상태코드 : {res['http_status'] if res['http_status'] is not None else '(응답 없음)'}")
    if res["body_head"]:
        LOG(f"  응답 본문 앞 500자: {res['body_head'][:500]!r}")

    if res["ok"]:
        st = str((res["json"] or {}).get("status", ""))
        det["dart_status"] = st
        det["dart_message"] = _dart_status_msg(st)
        if st in ("000", "013"):
            DART_PREFLIGHT.update({"ok": True, "code_fixable": True,
                                   "classification": "정상 (HTTP 200 + 정상 JSON)",
                                   "action": "그대로 진행"})
            OK(f"  DART status={st} ({_dart_status_msg(st)}) — 연결 정상. 벌크 진입 가능.")
            if st == "000":
                try:
                    write_json(cache_path(PREFLIGHT_CORP, PREFLIGHT_YEAR, PREFLIGHT_REPRT),
                               res["json"])
                    LOG("  카나리 응답을 캐시에 저장했다 — 호출 1건을 낭비하지 않는다.")
                except (OSError, DiskFull):
                    pass
        else:
            fixable = st not in ("010", "011", "012")
            DART_PREFLIGHT.update({
                "ok": False, "code_fixable": fixable,
                "classification": f"DART 인증/권한 응답 status={st} ({_dart_status_msg(st)})",
                "action": ("인증키를 다시 확인할 것 — https://opendart.fss.or.kr/ "
                           "[인증키 신청/관리]" if not fixable else
                           "일시적 응답이다. 재시도 정책이 처리한다.")})
            ERR(f"  DART status={st} ({_dart_status_msg(st)}) — {DART_PREFLIGHT['action']}")
    elif res["exc_type"]:
        # 예외 객체를 다시 만들 수 없으므로 이름으로 분류한다 — dart_request 가 MRO 이름을
        # 잃지 않도록 예외 전체 이름을 남겨 두었다.
        fake_names = res["exc_type"].split(".")[-1]
        cause, action, fixable = _classify_by_name(fake_names, res["exc_message"])
        DART_PREFLIGHT.update({"ok": False, "code_fixable": fixable,
                               "classification": cause, "action": action})
        ERR(f"  분류: {cause}")
        ERR(f"  조치: {action}")
    else:
        DART_PREFLIGHT.update({"ok": False, "code_fixable": True,
                               "classification": f"HTTP {res['http_status']} 응답(JSON 아님)",
                               "action": "본문 앞 500자를 확인할 것 — 차단 페이지/점검 안내일 수 있다."})
        ERR(f"  분류: {DART_PREFLIGHT['classification']}")

    det["classification"] = DART_PREFLIGHT["classification"]
    det["action"] = DART_PREFLIGHT["action"]
    det["code_fixable"] = DART_PREFLIGHT["code_fixable"]
    DART_PREFLIGHT["detail"] = det
    write_json(DIR_REPORTS / "diag_dart_preflight.json", det)
    LOG(f"  → diag_dart_preflight.json 저장")
    if not DART_PREFLIGHT["ok"] and not DART_PREFLIGHT["code_fixable"]:
        ERR("  §3.4: '코드로 해결 불가'로 분류되었다 — 임원현황 수집에 진입하지 않는다. "
            "이미 캐시된 분량으로 할 수 있는 것만 하고 종료한다.")
    return DART_PREFLIGHT


def _classify_by_name(exc_name: str, message: str):
    """예외 '이름'만으로 분류한다. dart_request 는 예외 객체를 넘기지 않기 때문이다.

    메시지 본문에도 원인 단서가 실려 오는 경우가 많아(예: ConnectionError 안에 감싸인
    'CERTIFICATE_VERIFY_FAILED') 이름과 메시지를 함께 본다.
    """
    def _r(i):
        return _DART_EXC_RULES[i][1], _DART_EXC_RULES[i][2], _DART_EXC_RULES[i][3]

    # 1) 구체적인 규칙의 이름이 정확히 맞으면 그것으로 확정한다.
    #    마지막 규칙(ConnectionError 계열)은 가장 일반적이라 여기서 제외한다 — 그것부터
    #    맞춰 버리면 'ConnectionError 로 감싸인 인증서 오류'가 방화벽으로 오분류된다.
    for i, (keys, cause, action, fixable) in enumerate(_DART_EXC_RULES[:-1]):
        if exc_name in keys:
            return cause, action, fixable
    # 2) 이름이 일반적일 때는 메시지 본문의 증거를 본다. urllib3/requests 는 실제 원인을
    #    바깥 예외 이름이 아니라 메시지에 담아 오는 경우가 흔하다.
    low = f"{exc_name} {message}".lower()
    if "certificate" in low or "ssl" in low:
        return _r(0)
    if "proxy" in low:
        return _r(1)
    if "timed out" in low or "timeout" in low:
        return _r(2)
    if "name or service not known" in low or "getaddrinfo" in low \
            or "nodename nor servname" in low or "name resolution" in low:
        return _r(3)
    # 3) 그래도 남으면 일반 규칙(연결 거부/차단)을 적용한다.
    if exc_name in _DART_EXC_RULES[-1][0]:
        return _r(len(_DART_EXC_RULES) - 1)
    for i, (keys, _c, _a, _f) in enumerate(_DART_EXC_RULES):
        if any(k.lower() in low for k in keys):
            return _r(i)
    return (f"미분류 예외({exc_name})",
            "예외 전문을 그대로 보고할 것 — 분류표에 없는 유형이다.", False)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 13. corpCode — 파싱 결과 캐시 (XML 재파싱 금지, §4.2)
# ══════════════════════════════════════════════════════════════════════════════════════════
_CORP_LIST_RE = re.compile(rb"<list>(.*?)</list>", re.S)


def _corpcode_xml() -> Path:
    return DIR_CACHE_META / "corpCode.zip"


def _corpcode_parsed() -> Path:
    return DIR_CACHE_META / "dart_corpcode.csv"


def load_corpcode():
    """종목코드를 가진 법인만 남긴 (corp_code, corp_name, code) 표.

    탐색 순서: 로컬 파싱캐시 → 드라이브 공용 인덱스 → 신규 수신.
    v1.2 에서 XML 재파싱에 231초를 쓴 뒤로, 파싱 '결과'를 캐시한다.
    """
    if restore_shared_table("dart_corpcode", _corpcode_parsed()):
        OK("  드라이브 공용 인덱스에서 dart_corpcode 복원")

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
        try:
            r = requests.get(endpoint("dart_corpcode"),
                             params={"crtfc_key": DART_API_KEY.strip()}, timeout=180,
                             headers={"User-Agent": "Mozilla/5.0"})
            raw = r.content
        except BaseException as e:                              # noqa: BLE001
            cause, action, _f = _classify_by_name(type(e).__name__, str(e))
            raise HardStop(f"corpCode 수신 실패 ({type(e).__module__}.{type(e).__qualname__}: {e})\n"
                           f"  분류: {cause}\n  조치: {action}") from e
        if raw[:2] != b"PK":
            body = raw[:400].decode("utf-8", "ignore")
            m = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
            st = m.group(1) if m else "?"
            raise HardStop(f"corpCode 응답이 ZIP 이 아니다 (status={st}: {_dart_status_msg(st)}). "
                           f"DART_API_KEY 를 확인할 것. 응답 앞부분: {body[:200]!r}")
        write_bytes(_corpcode_xml(), raw)

    t0 = time.time()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")] or zf.namelist()
        xml = zf.read(names[0])

    # 바이트 단위 1-pass 파싱(수 초) — 전체를 유니코드로 디코드한 뒤 태그별 정규식을 돌리면
    # 3,981개 <list> 블록에서 수 분이 걸린다.
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
        if publish_shared_table("dart_corpcode", _corpcode_parsed()):
            LOG("  공용 인덱스에 dart_corpcode 게시 — 다른 전략에서도 재사용 가능")
    except DiskFull:
        raise
    except OSError as e:
        WARN(f"파싱 결과 캐시 저장 실패: {e}")
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 14. 시장 스냅샷 공통 — "날짜 하나 → 전종목 (코드·시총·시장구분)"
# ══════════════════════════════════════════════════════════════════════════════════════════
#  어떤 Plan 이 이기든 산출물의 모양은 같다: index=종목코드, columns=[cap, mkt].
#  종목별 개별 요청은 구조적으로 금지한다 — 2,700회를 도는 순간 그게 병목이자 차단 사유다.
#  (Plan C 만 예외적으로 종목별 조회가 불가피한데, 그래서 전부 영구 캐시한다.)
# ══════════════════════════════════════════════════════════════════════════════════════════
_MKT_NORM = {
    "STK": "STK", "KSQ": "KSQ", "KNX": "KNX",
    "KOSPI": "STK", "KOSDAQ": "KSQ", "KOSDAQ GLOBAL": "KSQ", "KONEX": "KNX",
    "유가증권": "STK", "코스닥": "KSQ", "코스닥글로벌": "KSQ", "코넥스": "KNX",
    "유가증권시장": "STK", "코스닥시장": "KSQ", "코넥스시장": "KNX",
    # DART corp_cls (Plan C 의 시장구분 소스): Y=유가증권 K=코스닥 N=코넥스 E=기타
    "Y": "STK", "K": "KSQ", "N": "KNX",
}


def _norm_market(v) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip().upper()
    if s in _MKT_NORM:
        return _MKT_NORM[s]
    s2 = s.replace(" ", "")
    for k, val in _MKT_NORM.items():
        if k.replace(" ", "").upper() == s2:
            return val
    if "KOSDAQ" in s or "코스닥" in s:
        return "KSQ"
    if "KONEX" in s or "코넥스" in s:
        return "KNX"
    if "KOSPI" in s or "유가증권" in s:
        return "STK"
    return ""


def _num(series):
    """'1,234' · '1234' · 1234 → 숫자. 실패는 NaN(추정하지 않는다)."""
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")


def _mk_snapshot(codes, caps, mkts):
    """provider 공통 산출물: index=종목코드, columns=[cap, mkt]. 유효행이 부족하면 None."""
    df = pd.DataFrame({"cap": list(caps), "mkt": [_norm_market(m) for m in mkts]},
                      index=[to_code6(c) for c in codes])
    df = df[df.index != ""]
    df = df[~df.index.duplicated(keep="first")]
    df["cap"] = pd.to_numeric(df["cap"], errors="coerce").fillna(0)
    df = df[df["cap"] > 0]
    return df if len(df) >= EMPTY_UNIVERSE_MIN else None


def _snap_read_csv(p: Path):
    try:
        df = pd.read_csv(p, dtype={"code": str})
    except Exception:                                        # noqa: BLE001
        return None
    if not {"code", "cap"} <= set(df.columns):
        return None
    # ★ .to_numpy() 가 반드시 있어야 한다. Series 를 그대로 넘기면서 index= 를 함께 주면
    #   pandas 는 '값 정렬'이 아니라 '라벨 재색인'을 한다 — Series 의 라벨은 0,1,2… 인데
    #   새 index 는 종목코드라 하나도 안 맞아서 전 값이 NaN 이 된다. 그러면 cap>0 필터에
    #   전부 걸려 캐시가 항상 비어 보이고, 매 실행이 조용히 네트워크를 다시 탄다.
    out = pd.DataFrame(
        {"cap": pd.to_numeric(df["cap"], errors="coerce").fillna(0).to_numpy(),
         "mkt": (df["mkt"].fillna("").astype(str).to_numpy()
                 if "mkt" in df.columns else [""] * len(df))},
        index=[to_code6(c) for c in df["code"]])
    out = out[(out.index != "") & (out["cap"] > 0)]
    out = out[~out.index.duplicated(keep="first")]
    return out if len(out) >= EMPTY_UNIVERSE_MIN else None


def _snap_write_csv(df, p: Path):
    body = pd.DataFrame({"code": df.index, "cap": df["cap"].astype("int64"), "mkt": df["mkt"]})
    write_text(p, body.to_csv(index=False))


def _krx_snap_path(date_iso: str) -> Path:
    """Plan A/B 가 만든 KRX 실측 스냅샷. v1.3 및 이 저장소의 다른 전략과 같은 파일명이다."""
    return DIR_CACHE_MARKET / f"krx_market_{compact(date_iso)}.csv"


def _planc_snap_path(date_iso: str) -> Path:
    """Plan C 재구성 스냅샷. KRX 실측과 절대 같은 파일에 섞지 않는다 —
    나중에 어느 쪽이 실측이었는지 구분할 수 없게 되는 것이 가장 위험하다."""
    return DIR_CACHE_MARKET / f"planc_mcap_{compact(date_iso)}.csv"


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 15. 시장 데이터 소스 — 3단 사다리 (P0_MARKET_SOURCE_LADDER)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  §2.1 Plan A  pykrx 최신화 → 카나리 get_market_cap_by_ticker("20250630", market="ALL")
#  §2.2 Plan B  응답 원문 덤프 → 설치된 pykrx 소스 판독 → 세션 직접 구성 → 카나리
#  §2.3 Plan C  DART 주식총수 × FDR 종가로 시총 재구성 → 카나리 10종목 → S4 실측과 순위상관
#  하나가 성공하면 나머지는 건너뛴다. 3단 모두 실패하면 임원현황 수집에 진입하지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
MARKET_SOURCE = {"plan": "", "name": "", "detail": ""}
LADDER_DIAG = {"spec": "v1.4 §2", "canary_date": "2025-06-30", "plans": [], "selected": "",
               "endpoint_provenance": {}, "conclusion": ""}
CANARY_DATE = "2025-06-30"          # 명령서 §2.1-4 가 지정한 카나리 날짜
CANARY_MIN_ROWS = 100               # 100종목 이상 반환되면 성공


def _plan_record(plan: str, title: str) -> dict:
    rec = {"plan": plan, "title": title, "attempted": True, "ok": False,
           "reason": "", "steps": [], "started_at": _dt.datetime.now().isoformat(timespec="seconds")}
    LADDER_DIAG["plans"].append(rec)
    return rec


def _step(rec: dict, name: str, ok: bool, note: str = "", **extra) -> None:
    rec["steps"].append({"step": name, "ok": bool(ok), "note": str(note)[:2000], **extra})
    LOG(f"    [{rec['plan']}] {name}: {'OK' if ok else 'NG'}{(' — ' + str(note)[:220]) if note else ''}")


# ── Plan A: pykrx 최신화 ───────────────────────────────────────────────────────────────────
def _pip_version(pkg: str) -> str:
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "show", pkg],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:                                   # noqa: BLE001
        return f"(pip show 실패: {type(e).__name__})"
    for ln in (r.stdout or "").splitlines():
        if ln.lower().startswith("version:"):
            return ln.split(":", 1)[1].strip()
    return "(미설치)"


def plan_a_pykrx() -> bool:
    """§2.1 — pykrx 를 최신으로 올린 뒤, 자격증명 주입 이후에 import 하고 카나리를 친다."""
    global stock
    rec = _plan_record("A", "pykrx 최신화")

    before = _pip_version("pykrx")
    _step(rec, "pip show pykrx (업그레이드 전)", True, before)
    rec["version_before"] = before

    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "-q", "pykrx"],
                           capture_output=True, text=True, timeout=600)
        up_note = (r.stdout or "").strip()[-400:] or (r.stderr or "").strip()[-400:] or "(출력 없음)"
        _step(rec, "pip install --upgrade pykrx", r.returncode == 0, up_note, returncode=r.returncode)
    except Exception as e:                                   # noqa: BLE001
        _step(rec, "pip install --upgrade pykrx", False, f"{type(e).__name__}: {e}")
    importlib.invalidate_caches()

    after = _pip_version("pykrx")
    _step(rec, "pip show pykrx (업그레이드 후)", True, after)
    rec["version_after"] = after
    rec["upgraded"] = (before != after)
    if before == after:
        LOG(f"    [A] 버전 변화 없음({after}) — 이미 최신이다. 최신판이 KRX 개편에 대응했는지는 "
            f"카나리가 판정한다.")

    # 커널 재시작 대신: 자격증명을 env 에 넣은 '뒤' sys.modules 에서 pykrx 를 걷어내고 새로
    # import 한다. importlib.invalidate_caches() 로 방금 설치된 파일이 보이게 만든 상태다.
    inject_krx_env()
    rec["env_injected_before_import"] = PYKRX_IMPORT_LOG["env_injected_before_import"]
    rec["env_too_late_detected"] = PYKRX_IMPORT_LOG["env_too_late"]
    if PYKRX_IMPORT_LOG["env_too_late"]:
        LOG("    [A] 이미 로드돼 있던 pykrx 를 걷어내고 자격증명 주입 후 다시 import 한다 "
            "(v1.3 의 KRX_ENV_TOO_LATE 재발 방지)")

    mod = import_pykrx_guarded()
    stock = mod
    _step(rec, "pykrx import", mod is not None,
          PYKRX_DIAGNOSTIC or ("성공" if mod is not None else "실패"),
          attempts=PYKRX_IMPORT_LOG["attempts"])
    rec["import_attempts"] = PYKRX_IMPORT_LOG["attempts"]
    if mod is None:
        rec["reason"] = f"pykrx import 실패: {PYKRX_DIAGNOSTIC}"
        return False

    rec["dead_call_guard_armed"] = _arm_dead_call_guard(mod)

    df = pykrx_call("get_market_cap_by_ticker", compact(CANARY_DATE), market="ALL")
    n = 0
    if df is not None:
        try:
            n = int(len(df))
        except Exception:                                    # noqa: BLE001
            n = 0
    rec["canary_rows"] = n
    if n >= CANARY_MIN_ROWS:
        _step(rec, f"카나리 get_market_cap_by_ticker({compact(CANARY_DATE)}, market='ALL')",
              True, f"{n:,}종목 반환")
        rec["ok"] = True
        return True
    _step(rec, f"카나리 get_market_cap_by_ticker({compact(CANARY_DATE)}, market='ALL')",
          False, f"{n}종목 반환 (기준 {CANARY_MIN_ROWS} 미만)")
    rec["reason"] = (f"import 는 됐으나 카나리가 {n}종목만 반환했다 — 로그인 없이는 조회가 안 "
                     f"되는 상태로 보인다. pykrx 진단: {PYKRX_DIAGNOSTIC or '(없음)'}")
    return False


def snap_plan_a(date_iso: str):
    """Plan A 가 이긴 경우의 날짜별 스냅샷: 시총 + 시장구분을 한 번에 받는다."""
    df = pykrx_call("get_market_cap_by_ticker", compact(date_iso), market="ALL")
    if df is None or not len(df) or "시가총액" not in getattr(df, "columns", []):
        return None, "빈 응답(휴장일 또는 세션 문제)"
    lab = {}
    for mk, tag in (("KOSPI", "STK"), ("KOSDAQ", "KSQ"), ("KONEX", "KNX")):
        for t in (pykrx_call("get_market_ticker_list", compact(date_iso), market=mk) or []):
            lab[to_code6(t)] = tag
    mkts = [lab.get(to_code6(i), "") for i in df.index]
    snap = _mk_snapshot(df.index, _num(df["시가총액"]), mkts)
    return (snap, f"{len(snap):,}종목") if snap is not None else (None, "시총>0 부족(휴장일 추정)")


# ── Plan B: 마켓플레이스 세션 직접 구성 ─────────────────────────────────────────────────────
#  P0_NO_URL_GUESSING — 여기서 쓰는 URL·파라미터·성공코드는 전부 **설치된 pykrx 소스를 ast 로
#  읽어서** 얻는다. 하드코딩된 추측 URL 은 하나도 없다. 소스에서 못 읽으면 Plan B 는 그
#  사실을 사유로 남기고 실패한다 — 짐작으로 만들어 KRX 를 두들기지 않는다.
def _pykrx_pkg_dir():
    try:
        spec = importlib.util.find_spec("pykrx")             # 모듈을 '실행'하지 않는다
    except Exception:                                        # noqa: BLE001
        return None
    if spec is None:
        return None
    locs = list(getattr(spec, "submodule_search_locations", None) or [])
    return Path(locs[0]) if locs else None


def _parse_py(path: Path):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(src), src
    except Exception:                                        # noqa: BLE001
        return None, ""


def _find_node(tree, kinds, name):
    for n in ast.walk(tree):
        if isinstance(n, kinds) and getattr(n, "name", None) == name:
            return n
    return None


def _module_str_consts(tree) -> dict:
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = n.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out[n.targets[0].id] = (v.value, n.lineno)
            elif isinstance(v, ast.JoinedStr):
                continue
            else:
                # USER_AGENT = ("..." "...") 같은 암묵적 연결은 Constant 로 접히지 않을 수 있다
                try:
                    val = ast.literal_eval(v)
                    if isinstance(val, str):
                        out[n.targets[0].id] = (val, n.lineno)
                except Exception:                            # noqa: BLE001
                    pass
    return out


def _returned_str_const(fn):
    if fn is None:
        return None, None
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            return n.value.value, n.lineno
    return None, None


def _method_of(cls, name):
    if cls is None:
        return None
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def discover_pykrx_endpoints() -> dict:
    """설치된 pykrx 소스에서 로그인·조회 경로를 읽어낸다. 추측 금지(P0_NO_URL_GUESSING)."""
    d = {"pkg_dir": "", "missing": [], "provenance": {}}
    pkg = _pykrx_pkg_dir()
    if pkg is None:
        d["missing"].append("pykrx 패키지를 찾을 수 없다(미설치)")
        return d
    d["pkg_dir"] = str(pkg)

    def prov(field, path: Path, lineno):
        d["provenance"][field] = f"{path}:{lineno}"

    # ── (1) 로그인: website/comm/auth.py ────────────────────────────────────────────────
    auth_p = pkg / "website" / "comm" / "auth.py"
    tree, _src = _parse_py(auth_p)
    if tree is None:
        d["missing"].append(f"auth.py 를 읽지 못했다: {auth_p}")
    else:
        consts = _module_str_consts(tree)
        # 이름을 고정하지 않는다 — 'https://...' 문자열 중 로그인 흐름에 쓰이는 것을 함수에서 찾는다.
        warm = _find_node(tree, (ast.FunctionDef,), "warmup_krx_session")
        login = _find_node(tree, (ast.FunctionDef,), "login_krx")
        if login is None:
            d["missing"].append("auth.py 에 login_krx 가 없다")
        else:
            # 로그인 POST 대상 URL: session.post(<NAME>, data=payload, ...)
            for n in ast.walk(login):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr == "post" and n.args:
                    tgt = n.args[0]
                    if isinstance(tgt, ast.Name) and tgt.id in consts:
                        d["login_url"] = consts[tgt.id][0]
                        prov("login_url", auth_p, consts[tgt.id][1])
                    elif isinstance(tgt, ast.Constant) and isinstance(tgt.value, str):
                        d["login_url"] = tgt.value
                        prov("login_url", auth_p, n.lineno)
                    break
            # payload 딕셔너리 + 어느 키가 ID/PW 인가 (함수 인자 이름과 대조)
            argnames = [a.arg for a in login.args.args]
            id_arg = argnames[0] if len(argnames) > 0 else ""
            pw_arg = argnames[1] if len(argnames) > 1 else ""
            for n in ast.walk(login):
                if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                        and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Dict):
                    keys, id_key, pw_key = [], "", ""
                    for k, v in zip(n.value.keys, n.value.values):
                        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                            continue
                        keys.append(k.value)
                        if isinstance(v, ast.Name):
                            if v.id == id_arg:
                                id_key = k.value
                            elif v.id == pw_arg:
                                pw_key = k.value
                    if id_key and pw_key:
                        d["login_payload_keys"] = keys
                        d["login_id_key"] = id_key
                        d["login_pw_key"] = pw_key
                        prov("login_payload", auth_p, n.lineno)
                        break
            # 성공 코드 + 그 코드를 담은 변수 이름 (return error_code == "CD001")
            ok_var = ""
            for n in ast.walk(login):
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Compare) \
                        and n.value.comparators and isinstance(n.value.comparators[0], ast.Constant):
                    cv = n.value.comparators[0].value
                    if isinstance(cv, str):
                        d["login_success_code"] = cv
                        if isinstance(n.value.left, ast.Name):
                            ok_var = n.value.left.id
                        prov("login_success_code", auth_p, n.lineno)
                        break
            # 오류코드 키: 그 변수에 대입된 <응답>.get("<키>") 를 찾는다.
            # 키 이름에 'error' 가 들어간다는 가정은 쓰지 않는다 — pykrx 가 이름을 바꾸면
            # 조용히 못 찾게 되고, 그 순간 로그인 성패 판정이 무너지기 때문이다.
            def _get_key(call):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
                        and call.func.attr == "get" and call.args \
                        and isinstance(call.args[0], ast.Constant) \
                        and isinstance(call.args[0].value, str):
                    return call.args[0].value
                return None

            if ok_var:
                for n in ast.walk(login):
                    if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                            and isinstance(n.targets[0], ast.Name) and n.targets[0].id == ok_var:
                        k = _get_key(n.value)
                        if k:
                            d["error_code_key"] = k
                            prov("error_code_key", auth_p, n.lineno)
                            break
            if "error_code_key" not in d:
                for n in ast.walk(login):
                    k = _get_key(n)
                    if k and "error" in k.lower():
                        d["error_code_key"] = k
                        prov("error_code_key", auth_p, n.lineno)
                        break
            # 중복로그인 재전송 규칙: 'if error_code == "CD011": payload["skipDup"] = "Y"'
            # 트리거 코드까지 읽어야 아무 오류코드에나 재전송하는 일이 없다.
            for n in ast.walk(login):
                if not isinstance(n, ast.If) or not isinstance(n.test, ast.Compare):
                    continue
                comps = n.test.comparators
                if not comps or not isinstance(comps[0], ast.Constant) \
                        or not isinstance(comps[0].value, str):
                    continue
                for b in ast.walk(n):
                    if isinstance(b, ast.Assign) and len(b.targets) == 1 \
                            and isinstance(b.targets[0], ast.Subscript) \
                            and isinstance(b.targets[0].slice, ast.Constant) \
                            and isinstance(b.value, ast.Constant):
                        d["dup_login_param"] = (b.targets[0].slice.value, b.value.value)
                        d["dup_login_trigger"] = comps[0].value
                        prov("dup_login_param", auth_p, b.lineno)
                        break
                if "dup_login_param" in d:
                    break
        if warm is not None:
            urls = []
            for n in ast.walk(warm):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr == "get" and n.args:
                    t = n.args[0]
                    if isinstance(t, ast.Name) and t.id in consts:
                        urls.append(consts[t.id][0])
                    elif isinstance(t, ast.Constant) and isinstance(t.value, str):
                        urls.append(t.value)
            if urls:
                d["warmup_urls"] = urls
                prov("warmup_urls", auth_p, warm.lineno)
        for nm, (val, ln) in consts.items():
            if "AGENT" in nm.upper() and "Mozilla" in val:
                d["user_agent"] = val
                prov("user_agent", auth_p, ln)

    for need, label in (("login_url", "로그인 POST URL"), ("login_payload_keys", "로그인 payload"),
                        ("login_success_code", "로그인 성공코드")):
        if need not in d:
            d["missing"].append(f"auth.py 에서 {label} 를 읽지 못했다")

    # ── (2) 조회 URL: website/krx/krxio.py 의 KrxWebIo.url ─────────────────────────────
    krxio_p = pkg / "website" / "krx" / "krxio.py"
    tree2, _ = _parse_py(krxio_p)
    if tree2 is None:
        d["missing"].append(f"krxio.py 를 읽지 못했다: {krxio_p}")
    else:
        cls = _find_node(tree2, (ast.ClassDef,), "KrxWebIo")
        url, ln = _returned_str_const(_method_of(cls, "url"))
        if url:
            d["data_url"] = url
            prov("data_url", krxio_p, ln)
        else:
            d["missing"].append("krxio.py 의 KrxWebIo.url 을 읽지 못했다")

    # ── (3) 기본 헤더: website/comm/webio.py 의 Post.__init__ ──────────────────────────
    webio_p = pkg / "website" / "comm" / "webio.py"
    tree3, _ = _parse_py(webio_p)
    if tree3 is not None:
        cls = _find_node(tree3, (ast.ClassDef,), "Post")
        init = _method_of(cls, "__init__")
        if init is not None:
            for n in ast.walk(init):
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
                    try:
                        hd = ast.literal_eval(n.value)
                    except Exception:                        # noqa: BLE001
                        continue
                    if isinstance(hd, dict) and any("agent" in str(k).lower() for k in hd):
                        d["data_headers"] = {str(k): str(v) for k, v in hd.items()}
                        prov("data_headers", webio_p, n.lineno)
                        break

    # ── (4) 전종목시세 bld · 파라미터 · 응답 키: website/krx/market/core.py ────────────
    core_p = pkg / "website" / "krx" / "market" / "core.py"
    tree4, _ = _parse_py(core_p)
    if tree4 is None:
        d["missing"].append(f"market/core.py 를 읽지 못했다: {core_p}")
    else:
        cls = _find_node(tree4, (ast.ClassDef,), "전종목시세")
        if cls is None:
            d["missing"].append("market/core.py 에 전종목시세 클래스가 없다")
        else:
            bld, ln = _returned_str_const(_method_of(cls, "bld"))
            if bld:
                d["bld_all_quotes"] = bld
                prov("bld_all_quotes", core_p, ln)
            else:
                d["missing"].append("전종목시세.bld 를 읽지 못했다")
            fetch = _method_of(cls, "fetch")
            if fetch is not None:
                fargs = [a.arg for a in fetch.args.args if a.arg != "self"]
                if len(fargs) >= 2:
                    d["param_date"], d["param_market"] = fargs[0], fargs[1]
                    prov("fetch_params", core_p, fetch.lineno)
                for n in ast.walk(fetch):
                    if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) \
                            and isinstance(n.slice, ast.Constant) \
                            and isinstance(n.slice.value, str):
                        d["result_key"] = n.slice.value
                        prov("result_key", core_p, n.lineno)
                        break
            if "param_date" not in d or "param_market" not in d:
                d["missing"].append("전종목시세.fetch 의 파라미터 이름을 읽지 못했다")
            if "result_key" not in d:
                d["missing"].append("전종목시세.fetch 의 응답 키를 읽지 못했다")

    # ── (5) market 코드 매핑: website/krx/market/wrap.py 의 get_market_cap_by_ticker ───
    wrap_p = pkg / "website" / "krx" / "market" / "wrap.py"
    tree5, _ = _parse_py(wrap_p)
    if tree5 is not None:
        fn = _find_node(tree5, (ast.FunctionDef,), "get_market_cap_by_ticker")
        if fn is not None:
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
                    try:
                        mp = ast.literal_eval(n.value)
                    except Exception:                        # noqa: BLE001
                        continue
                    if isinstance(mp, dict) and "ALL" in mp:
                        d["market_all_value"] = str(mp["ALL"])
                        prov("market_all_value", wrap_p, n.lineno)
                        break
    d.setdefault("market_all_value", "")
    if not d["market_all_value"]:
        d["missing"].append("전체시장 코드값(mktId=ALL 상당)을 소스에서 읽지 못했다")
    return d


class KrxMarketplaceSession:
    """pykrx 소스에서 읽어낸 경로로 직접 세션을 구성한다. 단일 스레드 + 요청 간 1초(§2.2-4)."""

    def __init__(self, disc: dict):
        self.d = disc
        self.s = None
        self.logged_in = False
        self.login_detail = {}

    def _new_session(self):
        s = requests.Session()
        ua = self.d.get("user_agent") or (self.d.get("data_headers") or {}).get("User-Agent", "")
        if ua:
            s.headers.update({"User-Agent": ua})
        return s

    def warmup(self) -> list:
        self.s = self._new_session()
        out = []
        urls = self.d.get("warmup_urls") or []
        for i, u in enumerate(urls):
            hd = {"Referer": urls[0]} if i else {}
            try:
                with KRX_GATE:
                    r = self.s.get(u, headers=hd, timeout=HTTP_TIMEOUT)
                out.append({"url": u, "status": r.status_code, "len": len(r.content)})
            except BaseException as e:                       # noqa: BLE001
                out.append({"url": u, "error": f"{type(e).__name__}: {e}"})
        return out

    def dump_login_response(self, dump_path: Path) -> dict:
        """§2.2-1 — 깨지는 응답의 원문을 먼저 뜬다. 로그인 페이지인지 차단인지 점검 공지인지
        눈으로 확인할 수 있어야 한다. 저장 후 파일 경로를 진단물에 남긴다."""
        info = {"warmup": [], "login": {}, "dump_file": str(dump_path)}
        if self.s is None:
            info["warmup"] = self.warmup()
        payload = {k: "" for k in (self.d.get("login_payload_keys") or [])}
        payload[self.d.get("login_id_key", "mbrId")] = str(KRX_ID or "").strip()
        payload[self.d.get("login_pw_key", "pw")] = str(KRX_PW or "").strip()
        hd = {"Referer": (self.d.get("warmup_urls") or [""])[0]}
        lines = [f"# KRX 로그인 응답 원문 덤프  ({_dt.datetime.now():%Y-%m-%d %H:%M:%S})",
                 f"# 이 URL 은 설치된 pykrx 소스에서 읽어낸 것이다(추측 아님):",
                 f"#   {self.d.get('provenance', {}).get('login_url', '(출처 미상)')}",
                 f"# 자격증명: {'설정됨(ID=' + str(KRX_ID)[:3] + '***)' if KRX_ID else '미설정 — 빈 값으로 전송'}",
                 ""]
        for w in info["warmup"]:
            lines.append(f"[warmup] {w}")
        lines.append("")
        try:
            with KRX_GATE:
                r = self.s.post(self.d["login_url"], data=payload, headers=hd, timeout=HTTP_TIMEOUT)
            body = r.text
            info["login"] = {"status": r.status_code,
                             "headers": {k: v for k, v in r.headers.items()},
                             "body_head_2000": body[:2000],
                             "is_json": body.lstrip()[:1] in ("{", "[")}
            lines += [f"[login POST] {self.d['login_url']}",
                      f"status_code : {r.status_code}",
                      "headers     :",
                      json.dumps(dict(r.headers), ensure_ascii=False, indent=2),
                      "",
                      "text[:2000] :",
                      body[:2000]]
        except BaseException as e:                           # noqa: BLE001
            info["login"] = {"error": f"{type(e).__module__}.{type(e).__qualname__}: {e}"}
            lines += [f"[login POST] {self.d.get('login_url')}",
                      f"예외: {type(e).__module__}.{type(e).__qualname__}: {e}"]
        try:
            write_text(dump_path, "\n".join(lines) + "\n")
        except (OSError, DiskFull):
            pass
        return info

    def login(self) -> dict:
        """소스에서 읽은 절차 그대로: warmup → POST → 성공코드 확인 → (중복로그인이면 재전송)."""
        out = {"attempted": True, "ok": False, "error_code": "", "note": ""}
        if not (str(KRX_ID or "").strip() and str(KRX_PW or "").strip()):
            out.update({"attempted": False, "note": "KRX_ID/KRX_PW 미설정 — 로그인 시도 생략"})
            return out
        if self.s is None:
            self.warmup()
        payload = {k: "" for k in (self.d.get("login_payload_keys") or [])}
        payload[self.d["login_id_key"]] = KRX_ID.strip()
        payload[self.d["login_pw_key"]] = KRX_PW.strip()
        hd = {"Referer": (self.d.get("warmup_urls") or [""])[0]}
        ekey = self.d.get("error_code_key", "_error_code")
        okcode = self.d.get("login_success_code", "CD001")
        dup = self.d.get("dup_login_param")
        for attempt in range(2):
            try:
                with KRX_GATE:
                    r = self.s.post(self.d["login_url"], data=payload, headers=hd,
                                    timeout=HTTP_TIMEOUT)
            except BaseException as e:                       # noqa: BLE001
                out["note"] = f"{type(e).__module__}.{type(e).__qualname__}: {e}"
                return out
            txt = (r.text or "").lstrip()
            if txt[:1] not in ("{", "["):
                out["note"] = (f"로그인 응답이 JSON 이 아니다 (http{r.status_code}) — "
                               f"이것이 pykrx import 를 죽인 바로 그 응답이다. "
                               f"앞부분: {txt[:200]!r}")
                return out
            try:
                js = r.json()
            except ValueError as e:
                out["note"] = f"JSON 파싱 실패: {e} / 앞부분 {txt[:200]!r}"
                return out
            code = str(js.get(ekey, ""))
            out["error_code"] = code
            if code == okcode:
                out["ok"] = True
                self.logged_in = True
                out["note"] = f"{ekey}={code} (성공)"
                return out
            if dup and attempt == 0 and code and code == self.d.get("dup_login_trigger"):
                # 소스가 알려 준 재전송 규칙(중복 로그인)을 그 트리거 코드일 때만 따른다.
                payload[dup[0]] = dup[1]
                out["note"] = f"{ekey}={code} → {dup[0]}={dup[1]} 로 재전송"
                continue
            out["note"] = (f"{ekey}={code} / 메시지 "
                           f"{str(js.get('_error_message') or js.get('message') or '')[:200]!r}")
            return out
        return out

    def all_quotes(self, date_iso: str):
        """전종목 시세(시가총액 포함). 반환 (rows|None, note)."""
        body = {"bld": self.d["bld_all_quotes"],
                self.d["param_date"]: compact(date_iso),
                self.d["param_market"]: self.d["market_all_value"]}
        hd = dict(self.d.get("data_headers") or {})
        if self.s is None:
            self.warmup()
        try:
            with KRX_GATE:
                r = self.s.post(self.d["data_url"], data=body, headers=hd, timeout=HTTP_TIMEOUT)
        except BaseException as e:                           # noqa: BLE001
            return None, f"{type(e).__module__}.{type(e).__qualname__}: {e}"
        txt = (r.text or "").lstrip()
        if r.status_code != 200:
            return None, f"http{r.status_code} / 앞부분 {txt[:160]!r}"
        if txt[:1] not in ("{", "["):
            return None, f"JSON 이 아닌 응답(로그인/차단 페이지 추정): {txt[:200]!r}"
        try:
            js = r.json()
        except ValueError as e:
            return None, f"JSON 파싱 실패: {e}"
        rows = js.get(self.d.get("result_key", "OutBlock_1"))
        if not isinstance(rows, list):
            for v in js.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    rows = v
                    break
        if not isinstance(rows, list) or not rows:
            return None, f"행 배열 없음(keys={list(js)[:6]})"
        return rows, f"{len(rows):,}행"


KRX_SESSION = None
_MDC_CODE_KEYS = ("ISU_SRT_CD", "ISU_CD", "종목코드", "단축코드")
_MDC_CAP_KEYS = ("MKTCAP", "시가총액")
_MDC_MKT_KEYS = ("MKT_ID", "MKT_NM", "MKT_TP_NM", "시장구분")


def _rows_to_snapshot(rows):
    df = pd.DataFrame(rows)
    code_c = next((c for c in _MDC_CODE_KEYS if c in df.columns), None)
    cap_c = next((c for c in _MDC_CAP_KEYS if c in df.columns), None)
    mkt_c = next((c for c in _MDC_MKT_KEYS if c in df.columns), None)
    if not code_c or not cap_c:
        return None, f"스키마 불일치({list(df.columns)[:8]})"
    snap = _mk_snapshot(df[code_c], _num(df[cap_c]), df[mkt_c] if mkt_c else [""] * len(df))
    return (snap, f"{len(snap):,}종목") if snap is not None else (None, "시총>0 부족(휴장일 추정)")


def plan_b_marketplace() -> bool:
    """§2.2 — 소스 판독 → 응답 원문 덤프 → 세션 로그인 → 카나리."""
    global KRX_SESSION
    rec = _plan_record("B", "마켓플레이스 세션 직접 구성")

    # (2) 먼저 소스를 읽는다. §2.2 는 덤프를 1번으로 적었지만, '어느 URL 을 때릴지'를 알아야
    #     덤프를 뜰 수 있다 — 추측으로 URL 을 만들지 않기 위한 순서다(P0_NO_URL_GUESSING).
    disc = discover_pykrx_endpoints()
    rec["discovery"] = {k: v for k, v in disc.items() if k != "provenance"}
    rec["discovery_provenance"] = disc.get("provenance", {})
    LADDER_DIAG["endpoint_provenance"].update(
        {f"pykrx:{k}": v for k, v in disc.get("provenance", {}).items()})
    _step(rec, "설치된 pykrx 소스 판독(ast)", not disc["missing"],
          f"pkg={disc.get('pkg_dir') or '(없음)'} / 미확인 {len(disc['missing'])}건"
          + (f": {disc['missing'][:3]}" if disc["missing"] else ""))
    for f in ("login_url", "data_url", "bld_all_quotes"):
        if f in disc:
            LOG(f"      · {f} = {disc[f]}   ← {disc['provenance'].get(f, '?')}")

    need = ("login_url", "data_url", "bld_all_quotes", "param_date", "param_market",
            "market_all_value")
    lack = [f for f in need if not disc.get(f)]
    if lack:
        rec["reason"] = (f"설치된 pykrx 소스에서 필수 항목을 읽지 못했다: {lack}. "
                         f"추측으로 엔드포인트를 만들지 않는다(P0_NO_URL_GUESSING). "
                         f"세부: {disc['missing']}")
        _step(rec, "필수 항목 확보", False, rec["reason"])
        return False

    register_endpoint("krx_login", disc["login_url"], "LIBRARY_SOURCE",
                      disc["provenance"].get("login_url", ""))
    register_endpoint("krx_data", disc["data_url"], "LIBRARY_SOURCE",
                      disc["provenance"].get("data_url", ""))

    sess = KrxMarketplaceSession(disc)

    # (1) 깨지는 응답의 원문 덤프 — 로그인 페이지인지 차단인지 점검 공지인지 눈으로 본다.
    dump_path = DIR_REPORTS / "diag_krx_login_response.txt"
    dump = sess.dump_login_response(dump_path)
    rec["login_response_dump"] = dump
    li = dump.get("login", {})
    _step(rec, "로그인 응답 원문 덤프",
          bool(li.get("status")),
          (f"http{li.get('status')} / JSON={li.get('is_json')} / "
           f"앞부분 {str(li.get('body_head_2000', ''))[:200]!r}") if li.get("status")
          else li.get("error", "실패"),
          dump_file=str(dump_path))

    # (3) 로그인 → 세션 쿠키
    lg = sess.login()
    rec["login"] = lg
    _step(rec, "세션 로그인", lg["ok"], lg.get("note", ""))

    # (4) 카나리 — 로그인 세션으로. 실패하면 비로그인 세션으로도 한 번 더 본다.
    #     (pykrx 의 Get/Post 는 세션이 없으면 익명 requests.Session 으로 폴백한다 —
    #      즉 '로그인 없이도 되는가'는 소스가 실제로 취하는 경로이지 우리의 추측이 아니다.)
    rows, note = sess.all_quotes(CANARY_DATE)
    rec["canary_logged_in"] = {"ok": rows is not None, "note": note}
    _step(rec, f"카나리 전종목시세({CANARY_DATE}) [로그인 세션]", rows is not None, note)
    if rows is None:
        sess2 = KrxMarketplaceSession(disc)
        sess2.warmup()
        rows, note = sess2.all_quotes(CANARY_DATE)
        rec["canary_anonymous"] = {"ok": rows is not None, "note": note}
        _step(rec, f"카나리 전종목시세({CANARY_DATE}) [비로그인 세션]", rows is not None, note)
        if rows is not None:
            sess = sess2
    if rows is None:
        rec["reason"] = f"전종목시세 조회 실패: {note}"
        return False

    snap, snote = _rows_to_snapshot(rows)
    rec["canary_rows"] = 0 if snap is None else int(len(snap))
    if snap is None or len(snap) < CANARY_MIN_ROWS:
        _step(rec, "카나리 파싱", False, snote)
        rec["reason"] = f"응답은 왔으나 시총>0 종목이 {CANARY_MIN_ROWS} 미만이다: {snote}"
        return False
    _step(rec, "카나리 파싱", True, snote)
    KRX_SESSION = sess
    rec["ok"] = True
    rec["logged_in"] = sess.logged_in
    return True


def snap_plan_b(date_iso: str):
    if KRX_SESSION is None:
        return None, "세션 없음"
    rows, note = KRX_SESSION.all_quotes(date_iso)
    if rows is None:
        return None, note
    return _rows_to_snapshot(rows)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 16. DART 수집기 — 워커 2 / 재시도 3 / 지수백오프 2·4·8 / 서킷 / 예산 (§3.3 · §4.3)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  v1.3 의 서킷브레이커는 '연속 실패 10회'라서, 단발 net_error 31건만으로 즉사했다.
#  v1.4 는 '재시도(최대 3회)를 모두 소진한 콜이 연속 10건'일 때만 발동한다 — 재시도로
#  회복되는 잡음은 서킷을 건드리지 못한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
class Collector:
    """exctvSttus(임원현황) 와 stockTotqySttus(주식총수) 를 같은 규율로 수집한다."""

    KINDS = {
        "exctv":  ("dart_exctv", "임원현황"),
        "shares": ("dart_stock_totqy", "주식총수"),
    }

    def __init__(self, api_key: str):
        self.key = api_key
        self.lk = threading.Lock()
        self.tls = threading.local()
        self.budget_state = DIR_STATE / f"call_budget_{RUN_STARTED:%Y%m%d}.json"
        st = read_json(self.budget_state) or {}
        self.calls_today = int(st.get("calls", 0))      # 같은 날 이전 실행분까지 누적
        self.calls_run = 0
        self.consec_exhausted = 0
        self.trips = 0
        self.pause_until = 0.0
        self.halt = ""
        self.stat = Counter()
        self.delay = RandomDelay(0.3, 1.0)
        self._journal_buf = []
        self._journal_lk = threading.Lock()

    @staticmethod
    def path_for(kind: str, corp_code: str, year: str, reprt: str) -> Path:
        return (cache_path if kind == "exctv" else shares_path)(corp_code, year, reprt)

    # ── 예산 ───────────────────────────────────────────────────────────────────────────
    def _reserve(self) -> bool:
        with self.lk:
            if self.halt:
                return False
            if self.calls_today >= CALL_BUDGET_DAILY:
                self.halt = "BUDGET_STOP_DAILY"
                return False
            if self.calls_today >= CALL_BUDGET_STOP_CUMULATIVE:
                self.halt = "BUDGET_STOP_CUMULATIVE"
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

    def _on_call_ok(self):
        with self.lk:
            self.consec_exhausted = 0

    def _on_call_exhausted(self):
        with self.lk:
            self.consec_exhausted += 1
            if self.consec_exhausted >= CIRCUIT_FAIL_N:
                self.consec_exhausted = 0
                self.trips += 1
                if self.trips >= CIRCUIT_MAX_TRIPS:
                    self.halt = "CIRCUIT_BREAKER"
                else:
                    self.pause_until = time.time() + CIRCUIT_SLEEP
                    WARN(f"  서킷브레이커 {self.trips}/{CIRCUIT_MAX_TRIPS} — "
                         f"재시도를 모두 소진한 콜이 연속 {CIRCUIT_FAIL_N}건, "
                         f"{CIRCUIT_SLEEP}초 대기")

    def _session(self):
        s = getattr(self.tls, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                            "phase0-axisA-delta/1.4"})
            self.tls.s = s
        return s

    def flush_journal(self):
        with self._journal_lk:
            rows, self._journal_buf = self._journal_buf, []
        if rows:
            journal_append(rows)

    # ── 단건 수집 ─────────────────────────────────────────────────────────────────────
    def fetch(self, kind: str, corp_code: str, year: str, reprt: str) -> str:
        """성공 시 캐시에 원본 응답을 저장하고 DART status 를 돌려준다.

        최초 1회 + 재시도 MAX_RETRY_PER_CALL(3)회. 백오프 2/4/8초. 전부 소진하면
        RETRY_EXHAUSTED — 이 값만 서킷 카운터를 올린다.
        """
        ep_key = self.KINDS[kind][0]
        path = self.path_for(kind, corp_code, year, reprt)
        last = ""
        for attempt in range(MAX_RETRY_PER_CALL + 1):
            self._await_pause()
            if not self._reserve():
                return "HALT"
            self.delay.wait()
            res = dart_request(ep_key,
                               {"crtfc_key": self.key, "corp_code": corp_code,
                                "bsns_year": year, "reprt_code": reprt},
                               session=self._session())
            hs = res.get("http_status")
            if hs is not None and (hs >= 500 or hs == 429):
                # 5xx/429 는 본문이 JSON 이든 아니든 재시도 대상이다.
                last = f"http{hs}"
                self.stat[last] += 1
                if attempt < MAX_RETRY_PER_CALL:
                    time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                               * random.uniform(0.8, 1.2))
                continue
            if not res["ok"]:
                last = res["exc_type"] or f"http{hs}"
                self.stat[f"err_{last.split('.')[-1]}"] += 1
                if attempt < MAX_RETRY_PER_CALL:
                    time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                               * random.uniform(0.8, 1.2))
                continue

            js = res["json"] or {}
            st = str(js.get("status", ""))
            if st in ("011", "012", "020", "021"):
                # ★ 020(요청 제한 초과)은 우리 자체 카운터보다 권위 있는 실시간 신호다.
                with self.lk:
                    self.halt = f"DART_{st}"
                ERR(f"  DART status={st} ({_dart_status_msg(st)}) — 계속할 수 없다")
                return st
            if st in ("800", "900"):
                last = f"dart_{st}"
                self.stat[last] += 1
                if attempt < MAX_RETRY_PER_CALL:
                    time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                               * random.uniform(0.8, 1.2))
                continue

            self._on_call_ok()
            self.stat[f"dart_{st or '?'}"] += 1
            data = json.dumps(js, ensure_ascii=False).encode("utf-8")
            write_json(path, js)           # ← 원본 응답 그대로. PIT 필터는 읽을 때 건다.
            with self._journal_lk:
                self._journal_buf.append({
                    "kind": kind, "corp_code": corp_code, "bsns_year": year,
                    "reprt_code": reprt, "status": st, "sha1": sha1_bytes(data),
                    "bytes": len(data),
                    "collected_at": _dt.datetime.now().isoformat(timespec="seconds")})
            return st
        self.stat["retry_exhausted"] += 1
        self._on_call_exhausted()
        return "RETRY_EXHAUSTED"

    def run(self, kind: str, jobs, label: str):
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

        futs = {}
        with ThreadPoolExecutor(max_workers=max(1, min(8, N_WORKERS))) as ex:
            futs = {ex.submit(self.fetch, kind, *j): j for j in jobs}
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
                        f"(성공 {done:,} / 이번 실행 누적호출 {self.calls_run:,} / "
                        f"오늘 누적 {self.calls_today:,})")
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
        self.flush_journal()
        return done, remaining


def extract_dart_payload(obj):
    """원본 응답이든 구버전 봉투(envelope)든 (status, list) 를 꺼낸다."""
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 17. Plan C — DART 주식총수 × FDR 종가로 시가총액 재구성 (§2.3)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  시가총액 = 발행주식총수 × 종가.  KRX 에 전혀 의존하지 않는 경로다.
#
#  ★ 발행주식총수 필드 선택이 이 Plan 의 정확도를 결정한다. DART '주식의 총수 현황'은
#    비슷한 이름의 필드를 여러 개 준다:
#      istc_totqy              발행주식의 총수          ← 우리가 원하는 값
#      isu_stock_totqy         발행할 주식의 총수(수권주식수)  ← 실제 발행량이 아니다. 절대 금지
#      now_to_isu_stock_totqy  현재까지 발행한 주식의 총수(누적) ← 감소분이 안 빠져 있다. 금지
#      distb_stock_co          유통주식수(= 발행 - 자기주식)
#      tesstk_co               자기주식수
#    그래서 후보를 '이름이 비슷하니 아무거나'로 두지 않는다. 1순위는 istc_totqy 뿐이고,
#    그것이 응답에 아예 없을 때만 distb_stock_co 로 내려가되 그 사실을 크게 경고하고 기록한다.
#
#  ★ 자기주식 차감 여부(§2.3-2): **차감하지 않는다.**
#    KRX 공식 시가총액이 '상장주식수 × 종가'로 자기주식을 포함하기 때문이다. 이 실행의
#    목적은 KRX 실측 순위와의 정합이므로 KRX 정의를 따르는 쪽이 순위 보존성이 높다.
#    참고용으로 자기주식수 합계도 함께 기록해 두어, 나중에 차감본을 만들고 싶으면 만들 수 있다.
# ══════════════════════════════════════════════════════════════════════════════════════════
PLANC_SHARES_FIELD_PRIMARY = "istc_totqy"
PLANC_SHARES_FIELD_FALLBACK = "distb_stock_co"
PLANC_TREASURY_FIELD = "tesstk_co"
PLANC_DEDUCT_TREASURY = False
#  ★ Plan C 채택 시 4개 스냅샷 전부를 Plan C 로 만든다(True). S4 에 KRX 실측 캐시가 남아
#    있어도 유니버스 구성에는 쓰지 않는다 — 스냅샷마다 시총 소스가 다르면 그 차이 자체가
#    S3→S4 전이에서 가짜 신호로 보이기 때문이다. 실측 캐시는 교차검증 기준값으로만 쓴다.
#    False 로 두면 실측 캐시가 있는 날짜는 실측을 우선한다(절대 수준은 정확해지지만
#    스냅샷 간 비교 가능성이 깨진다). 선택값은 판정표 methodology 에 기록된다.
PLANC_UNIFORM_SNAPSHOTS = True
PLANC_CANARY_MIN_OK = 6          # 카나리 10종목 중 이만큼은 정상 파싱돼야 Plan C 를 신뢰한다
PLANC_XVAL_MIN_SPEARMAN = 0.95   # §2.3 — 이 미만이면 판정표에 '신뢰할 수 없음'을 명시한다
PLANC_PRICE_STALE_MAX_DAYS = 10  # 스냅샷일에 체결이 없으면 이 일수 내 직전 종가까지만 인정
PX_NODATA_TTL_DAYS = 3           # '종가 없음' 표시의 유효기간 (영구 결측으로 굳지 않게)

# 카나리 10종목 — 대형주로 고정한다(공시 누락 가능성이 가장 낮은 표본).
PLANC_CANARY_TICKERS = ["005930", "000660", "035420", "005380", "051910",
                        "068270", "006400", "000270", "012330", "105560"]

PLANC = {"available": False, "reason": "", "shares_field": "", "se_values_seen": [],
         "canary": [], "cross_validation": {}, "coverage": {}, "price": {}}


def _norm_se(v) -> str:
    return re.sub(r"[\s()（）]", "", str(v or ""))


def _is_common_share_row(se: str) -> bool:
    """보통주 행만 쓴다(§2.3-2). '합계'는 우선주가 섞여 있으므로 반드시 제외한다."""
    s = _norm_se(se)
    if not s:
        return False
    if "우선" in s:
        return False
    if s in ("합계", "계", "총계") or s.endswith("합계"):
        return False
    return "보통" in s


def parse_shares_payload(obj):
    """반환 dict(shares, treasury, corp_cls, se_values, field_used, note). 실패는 shares=None."""
    st, rows = extract_dart_payload(obj)
    out = {"status": st, "shares": None, "treasury": None, "corp_cls": "",
           "se_values": [], "field_used": "", "note": ""}
    if not rows:
        out["note"] = f"행 없음(status={st})"
        return out
    common = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out["se_values"].append(str(r.get("se", "")))
        if not out["corp_cls"]:
            out["corp_cls"] = str(r.get("corp_cls", "") or "")
        if _is_common_share_row(r.get("se")):
            common.append(r)
    if not common:
        out["note"] = f"보통주 행 없음 (se={sorted(set(out['se_values']))[:6]})"
        return out
    for field in (PLANC_SHARES_FIELD_PRIMARY, PLANC_SHARES_FIELD_FALLBACK):
        vals = [_to_int(r.get(field)) for r in common]
        vals = [v for v in vals if v is not None and v > 0]
        if vals:
            out["shares"] = sum(vals)         # 종류가 여러 줄로 쪼개져 오면 합친다
            out["field_used"] = field
            break
    if out["shares"] is None:
        out["note"] = (f"발행주식총수 필드를 찾지 못했다 "
                       f"(찾은 키: {sorted(common[0].keys())[:12]})")
        return out
    tre = [_to_int(r.get(PLANC_TREASURY_FIELD)) for r in common]
    tre = [v for v in tre if v is not None and v >= 0]
    out["treasury"] = sum(tre) if tre else None
    return out


# ── 종가 캐시 (§2.3-3: cache/raw/px/{ticker}/{year}.parquet) ───────────────────────────────
class PriceStore:
    """FDR 개별 종목 시계열을 연 단위로 영구 캐시한다. 재실행은 네트워크를 타지 않는다."""

    def __init__(self, years, fetch_start: str, fetch_end: str):
        self.years = sorted(set(int(y) for y in years))
        self.fetch_start = fetch_start
        self.fetch_end = fetch_end
        self.mem = {}
        self.keep = None
        self.lk = threading.Lock()
        self.delay = RandomDelay(0.3, 1.0)
        self.stat = Counter()

    # -- 저수준 IO ------------------------------------------------------------------
    def _meta_path(self, ticker: str, year: int) -> Path:
        return DIR_CACHE_PX / str(ticker) / f"{year}.meta.json"

    def _read_year(self, ticker: str, year: int):
        p = px_path(ticker, year)
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
        except Exception:                                    # noqa: BLE001
            return None
        if not {"date", "close"} <= set(df.columns):
            return None
        return {str(d): float(c) for d, c in zip(df["date"], df["close"])
                if c == c and float(c) > 0}

    def _write_year(self, ticker: str, year: int, series: dict):
        p = px_path(ticker, year)
        df = pd.DataFrame({"date": list(series.keys()), "close": list(series.values())})
        df = df.sort_values("date")
        try:
            if p.suffix == ".parquet":
                p.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(p, index=False)
            else:
                write_text(p, df.to_csv(index=False))
            write_json(self._meta_path(ticker, year),
                       {"rows": len(df), "min_date": (df["date"].iloc[0] if len(df) else ""),
                        "max_date": (df["date"].iloc[-1] if len(df) else ""),
                        "fetched_at": _dt.datetime.now().isoformat(timespec="seconds"),
                        "fetch_range": [self.fetch_start, self.fetch_end]})
        except DiskFull:
            raise
        except Exception as e:                               # noqa: BLE001
            WARN(f"    종가 캐시 저장 실패 {ticker}/{year}: {type(e).__name__}: {e}")

    def _nodata_path(self, ticker: str) -> Path:
        return DIR_CACHE_PX / str(ticker) / "nodata.json"

    def _nodata_fresh(self, ticker: str) -> bool:
        """'이 종목은 종가를 못 받았다'를 유효기간 있게 기억한다.

        corpCode 에는 이미 상장폐지된 종목이 많아 FDR 에 시계열이 아예 없다. 그대로 두면
        재실행마다 그 수백~천 종목을 다시 두들긴다. 그렇다고 영구 캐시하면 일시적 장애가
        영원한 결측으로 굳는다 — 그래서 PX_NODATA_TTL_DAYS 가 지나면 다시 시도한다.
        """
        m = read_json(self._nodata_path(ticker))
        if not m:
            return False
        try:
            t = _dt.datetime.fromisoformat(str(m.get("at", "")))
        except ValueError:
            return False
        return (_dt.datetime.now() - t).days < PX_NODATA_TTL_DAYS

    def _mark_nodata(self, ticker: str, note: str) -> None:
        try:
            write_json(self._nodata_path(ticker),
                       {"at": _dt.datetime.now().isoformat(timespec="seconds"),
                        "note": str(note)[:200], "ttl_days": PX_NODATA_TTL_DAYS})
        except (OSError, DiskFull):
            pass

    def _covered(self, ticker: str, needed_dates) -> bool:
        """필요한 날짜가 '이미 받아 둔 구간' 안에 들어오는가.

        메타의 fetch_range 가 권위다 — 그 구간 안이라면 해당 날짜에 값이 없다는 것도
        '그 종목은 그 날 체결이 없었다'는 확정된 사실이다(다시 받아도 결과가 같다).
        구간 밖이면 캐시가 그 날짜를 아직 안 덮은 것이므로 다시 받는다.
        """
        for d in needed_dates:
            m = read_json(self._meta_path(ticker, int(str(d)[:4])))
            if not m:
                return False
            fr = m.get("fetch_range") or ["", ""]
            if not (str(fr[0]) <= str(d) <= str(fr[1])):
                return False
        return True

    def set_keep_window(self, nominal_dates, back_days: int):
        """메모리에 들고 있을 날짜를 스냅샷 주변으로 좁힌다 — 4,000종목 × 2년치를 전부
        메모리에 올릴 이유가 없다. 디스크 캐시는 온전한 연 단위로 남는다."""
        keep = set()
        for nom in nominal_dates:
            d0 = _dt.date.fromisoformat(str(nom))
            for b in range(back_days + 1):
                keep.add((d0 - _dt.timedelta(days=b)).isoformat())
        self.keep = keep

    # -- 네트워크 ------------------------------------------------------------------
    def _fetch(self, ticker: str):
        if fdr is None:
            return None, "FDR 미설치"
        self.delay.wait()
        try:
            df = fdr.DataReader(ticker, self.fetch_start, self.fetch_end)
        except BaseException as e:                           # noqa: BLE001
            return None, f"{type(e).__name__}: {str(e)[:120]}"
        if df is None or not len(df):
            return None, "빈 응답"
        col = next((c for c in ("Close", "close", "종가") if c in df.columns), None)
        if col is None:
            return None, f"종가 컬럼 없음({list(df.columns)[:6]})"
        try:
            idx = pd.to_datetime(df.index)
            out = {}
            for d, v in zip(idx, df[col]):
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv > 0:
                    out[d.strftime("%Y-%m-%d")] = fv
        except Exception as e:                               # noqa: BLE001
            return None, f"파싱 실패: {type(e).__name__}: {e}"
        return (out, f"{len(out):,}일") if out else (None, "유효 종가 없음")

    def ensure(self, tickers, needed_dates, label: str = "종가"):
        """캐시에 없는 종목만 받는다(skip-if-exists). 반환 (신규수신, 실패)."""
        todo, skipped = [], 0
        for t in tickers:
            if self._covered(t, needed_dates):
                continue
            if self._nodata_fresh(t):
                skipped += 1
                continue
            todo.append(t)
        LOG(f"  {label}: 대상 {len(tickers):,}종목 / 캐시 히트 "
            f"{len(tickers) - len(todo) - skipped:,} / 종가없음(최근 확인, 재시도 생략) "
            f"{skipped:,} / 신규 수신 {len(todo):,}")
        self.stat["skipped_nodata"] = skipped
        if not todo:
            return 0, 0
        got = fail = 0
        lk = threading.Lock()

        def _one(t):
            nonlocal got, fail
            series, note = self._fetch(t)
            if series is None:
                self._mark_nodata(t, note)
                with lk:
                    fail += 1
                    self.stat[f"fail_{note.split(':')[0][:30]}"] += 1
                return
            by_year = defaultdict(dict)
            for d, v in series.items():
                by_year[int(d[:4])][d] = v
            for y in self.years:
                self._write_year(t, y, by_year.get(y, {}))
            try:
                self._nodata_path(t).unlink(missing_ok=True)
            except OSError:
                pass
            with lk:
                got += 1

        with ThreadPoolExecutor(max_workers=max(1, min(4, N_WORKERS))) as ex:
            futs = {ex.submit(_one, t): t for t in todo}
            for i, fu in enumerate(as_completed(futs), 1):
                try:
                    fu.result()
                except Exception as e:                       # noqa: BLE001
                    with lk:
                        fail += 1
                        self.stat[f"exc_{type(e).__name__}"] += 1
                if i % 250 == 0 or i == len(todo):
                    LOG(f"    {label} 수신 {i:,}/{len(todo):,} (성공 {got:,} / 실패 {fail:,})")
        return got, fail

    # -- 조회 ---------------------------------------------------------------------
    def load(self, ticker: str) -> dict:
        with self.lk:
            if ticker in self.mem:
                return self.mem[ticker]
        merged = {}
        for y in self.years:
            s = self._read_year(ticker, y)
            if not s:
                continue
            if self.keep is not None:
                s = {d: v for d, v in s.items() if d in self.keep}
            merged.update(s)
        with self.lk:
            self.mem[ticker] = merged
        return merged

    def close_asof(self, ticker: str, date_iso: str):
        """그 날짜의 종가. 체결이 없으면 PLANC_PRICE_STALE_MAX_DAYS 내 직전 종가.
        반환 (close|None, 사용한 날짜, 경과일). 추정·보간은 하지 않는다."""
        s = self.load(ticker)
        if not s:
            return None, "", -1
        if date_iso in s:
            return s[date_iso], date_iso, 0
        d0 = _dt.date.fromisoformat(date_iso)
        for back in range(1, PLANC_PRICE_STALE_MAX_DAYS + 1):
            d = (d0 - _dt.timedelta(days=back)).isoformat()
            if d in s:
                return s[d], d, back
        return None, "", -1

    def trading_day_count(self, tickers, date_iso: str) -> int:
        n = 0
        for t in tickers:
            s = self.load(t)
            if s and date_iso in s:
                n += 1
        return n


PRICE_STORE = None


def plan_c_reconstruct(cc_df, code2corp) -> bool:
    """§2.3 카나리 — DART 주식총수 API 가 실제로 존재하고 응답하는지 10종목으로 먼저 확인한다.

    Plan C 는 DART 를 쓰므로, 여기 오기 전에 §3 의 DART 연결 진단이 반드시 끝나 있어야
    실패 원인을 옳게 귀속할 수 있다(P0_DART_PREFLIGHT).
    """
    global PRICE_STORE
    rec = _plan_record("C", "KRX 없이 시총 자체 계산 (DART 주식총수 × FDR 종가)")

    pre = run_dart_preflight()
    _step(rec, "DART 연결 진단(§3) 선행", pre["ok"],
          f"{pre['classification']} / code_fixable={pre['code_fixable']}")
    if not pre["ok"] and not pre["code_fixable"]:
        rec["reason"] = (f"DART 연결이 코드로 해결 불가로 분류되었다 — Plan C 는 DART 에 "
                         f"의존하므로 성립할 수 없다. 분류: {pre['classification']}")
        return False

    if fdr is None:
        rec["reason"] = "FinanceDataReader 를 import 하지 못했다 — 종가 소스가 없다."
        _step(rec, "FinanceDataReader", False, rec["reason"])
        return False
    _step(rec, "FinanceDataReader", True, "사용 가능")
    if not PARQUET_AVAILABLE:
        WARN("    [C] parquet 엔진(pyarrow/fastparquet)이 없어 종가 캐시를 CSV 로 저장한다 "
             "— 명령서가 지정한 경로 형식과 확장자만 다르고 동작은 같다.")

    # ── 카나리 1: DART 주식총수 10종목 ──────────────────────────────────────────────
    col = get_collector()
    cyy, crc = SNAPSHOT_SPEC[0][3], SNAPSHOT_SPEC[0][4]      # S1 보고서로 확인한다
    canary = []
    se_seen, fields_used = set(), Counter()
    for t in PLANC_CANARY_TICKERS:
        cp = code2corp.get(t, "")
        if not cp:
            canary.append({"ticker": t, "ok": False, "note": "corpCode 에 없음"})
            continue
        p = shares_path(cp, cyy, crc)
        obj = read_json(p) if p.exists() else None
        cached = obj is not None
        if obj is None:
            st = col.fetch("shares", cp, cyy, crc)
            if st in ("HALT", "RETRY_EXHAUSTED") or col.halt:
                canary.append({"ticker": t, "ok": False, "note": f"수집 실패({st})"})
                continue
            obj = read_json(p)
        parsed = parse_shares_payload(obj) if obj is not None else {"shares": None,
                                                                   "note": "응답 없음"}
        se_seen.update(parsed.get("se_values") or [])
        if parsed.get("field_used"):
            fields_used[parsed["field_used"]] += 1
        canary.append({"ticker": t, "corp_code": cp, "cached": cached,
                       "ok": parsed.get("shares") is not None,
                       "shares": parsed.get("shares"), "treasury": parsed.get("treasury"),
                       "corp_cls": parsed.get("corp_cls"), "field_used": parsed.get("field_used"),
                       "status": parsed.get("status"), "note": parsed.get("note")})
    n_ok = sum(1 for c in canary if c.get("ok"))
    PLANC["canary"] = canary
    PLANC["se_values_seen"] = sorted(se_seen)
    rec["canary_shares"] = {"n_ok": n_ok, "n_total": len(PLANC_CANARY_TICKERS),
                            "detail": canary, "se_values_seen": sorted(se_seen),
                            "fields_used": dict(fields_used)}
    _step(rec, f"카나리 DART 주식총수 {len(PLANC_CANARY_TICKERS)}종목 ({cyy}/{crc})",
          n_ok >= PLANC_CANARY_MIN_OK,
          f"정상 파싱 {n_ok}/{len(PLANC_CANARY_TICKERS)} / 사용 필드 {dict(fields_used)} / "
          f"se 값 {sorted(se_seen)[:8]}")
    col.persist_budget()
    col.flush_journal()
    if n_ok < PLANC_CANARY_MIN_OK:
        rec["reason"] = (f"DART 주식총수 카나리 실패 — {len(PLANC_CANARY_TICKERS)}종목 중 "
                         f"{n_ok}종목만 발행주식총수를 얻었다(기준 {PLANC_CANARY_MIN_OK}). "
                         f"세부: {[c.get('note') for c in canary if not c.get('ok')][:5]}")
        return False
    field = fields_used.most_common(1)[0][0] if fields_used else PLANC_SHARES_FIELD_PRIMARY
    PLANC["shares_field"] = field
    if field != PLANC_SHARES_FIELD_PRIMARY:
        WARN(f"    [C] 발행주식총수를 1순위 필드({PLANC_SHARES_FIELD_PRIMARY})가 아니라 "
             f"'{field}' 에서 읽었다. 이 값의 정의를 판정표에서 반드시 확인할 것.")

    # ── 카나리 2: FDR 종가 ─────────────────────────────────────────────────────────
    years = sorted({int(s[1][:4]) for s in SNAPSHOT_SPEC})
    fetch_start = f"{min(years)}-01-01"
    fetch_end = min(f"{max(years)}-12-31", _dt.date.today().isoformat())
    PRICE_STORE = PriceStore(years, fetch_start, fetch_end)
    nominal_dates = [s[1] for s in SNAPSHOT_SPEC]
    PRICE_STORE.set_keep_window(nominal_dates,
                                TRADING_DAY_LOOKBACK + PLANC_PRICE_STALE_MAX_DAYS)
    got, fail = PRICE_STORE.ensure(PLANC_CANARY_TICKERS, nominal_dates, "카나리 종가")
    px_ok = 0
    px_detail = []
    for t in PLANC_CANARY_TICKERS:
        c, used, back = PRICE_STORE.close_asof(t, CANARY_DATE)
        px_detail.append({"ticker": t, "close": c, "date_used": used, "days_back": back})
        if c:
            px_ok += 1
    rec["canary_price"] = {"n_ok": px_ok, "n_total": len(PLANC_CANARY_TICKERS),
                           "date": CANARY_DATE, "detail": px_detail,
                           "fetch_range": [fetch_start, fetch_end],
                           "cache_dir": str(DIR_CACHE_PX)}
    _step(rec, f"카나리 FDR 종가 {CANARY_DATE}", px_ok >= PLANC_CANARY_MIN_OK,
          f"{px_ok}/{len(PLANC_CANARY_TICKERS)}종목 종가 확보 (신규수신 {got} / 실패 {fail})")
    if px_ok < PLANC_CANARY_MIN_OK:
        rec["reason"] = (f"FDR 종가 카나리 실패 — {CANARY_DATE} 기준 "
                         f"{px_ok}/{len(PLANC_CANARY_TICKERS)}종목만 종가를 얻었다.")
        return False

    PLANC["available"] = True
    rec["ok"] = True
    rec["shares_field"] = field
    rec["treasury_deducted"] = PLANC_DEDUCT_TREASURY
    rec["treasury_note"] = ("자기주식 차감하지 않음 — KRX 공식 시가총액이 '상장주식수 × 종가'로 "
                            "자기주식을 포함하기 때문. 자기주식수 합계는 별도 기록.")
    return True


# ── Plan C 벌크: 종가 → 거래일 판정 → 발행주식총수 → 시총 재구성 ───────────────────────────
def planc_build_snapshots(cc_df, code2corp, col: "Collector"):
    """반환 dict(status, snapshots{sid: (eff_date, df)}, diag). DART 호출 예산 게이트를 포함한다."""
    tickers = sorted({c for c in cc_df["code"] if c})
    nominal = [s[1] for s in SNAPSHOT_SPEC]
    diag = {"tickers": len(tickers), "nominal_dates": nominal}

    # (1) 예산 사전 보고 — 실제 수신 전에 규모를 먼저 알린다 (P0_CACHE_FIRST)
    px_todo = [t for t in tickers if not PRICE_STORE._covered(t, nominal)]
    sh_inv = scan_blob_inventory(DIR_CACHE_SHARES)
    sh_need = 0
    for _sid, _nom, _pe, yy, rc, _as, _need in SNAPSHOT_SPEC:
        have = sh_inv.get((yy, rc), set())
        sh_need += sum(1 for t in tickers if code2corp.get(t) and code2corp[t] not in have)
    est_total = len(px_todo) + sh_need
    diag.update({"price_new_fetch": len(px_todo), "shares_new_calls_upper_bound": sh_need,
                 "estimated_total_new_calls": est_total})
    LOG(f"  Plan C 예상 신규 호출 — FDR 종가 {len(px_todo):,}종목 + DART 주식총수 "
        f"최대 {sh_need:,}건 = {est_total:,}건")
    LOG(f"    (주식총수는 4개 스냅샷 × 종목 이므로 콜드런에서는 임원현황(~11,078건)보다 크다. "
        f"일일한도 때문에 여러 날에 걸쳐 완주하게 된다 — 캐시는 전부 이어받는다.)")
    if est_total > LARGE_COLLECTION_GATE and not CONFIRM_LARGE_COLLECTION:
        WARN(f"P0_CACHE_FIRST: Plan C 예상 신규 호출 {est_total:,}건 > {LARGE_COLLECTION_GATE:,}건.")
        WARN("수집에 진입하지 않고 여기서 멈춘다. 위 내역을 확인한 뒤")
        WARN("  CONFIRM_LARGE_COLLECTION = True")
        WARN("로 바꾸고 셀을 다시 실행할 것. (이미 받은 캐시는 그대로 재사용된다)")
        return {"status": "AWAITING_USER_CONFIRMATION", "snapshots": {}, "diag": diag}

    # (2) 종가 수신 — DART 예산과 무관한 무료 경로다. 전부 영구 캐시한다.
    got, fail = PRICE_STORE.ensure(tickers, nominal, "종가(Plan C)")
    diag.update({"price_fetched": got, "price_failed": fail,
                 "price_stat": dict(PRICE_STORE.stat)})
    PLANC["price"] = {"fetched": got, "failed": fail, "cached_tickers": count_px_cached()}

    # (3) 거래일 판정 — 달력이 아니라 '그 날 실제 체결이 있었는가'로 정한다.
    eff_of, day_trail = {}, {}
    for sid, nom, _pe, _yy, _rc, _as, _need in SNAPSHOT_SPEC:
        d0 = _dt.date.fromisoformat(nom)
        trail = []
        eff = None
        for back in range(TRADING_DAY_LOOKBACK + 1):
            d = (d0 - _dt.timedelta(days=back)).isoformat()
            n = PRICE_STORE.trading_day_count(tickers, d)
            trail.append((d, n))
            if n >= EMPTY_UNIVERSE_MIN:
                eff = d
                break
        eff_of[sid] = eff
        day_trail[sid] = trail
        for d, n in trail:
            LOG(f"    {sid} 거래일 탐색 {d}: 체결 {n:,}종목 {'←사용' if d == eff else ''}")
    diag["effective_dates"] = eff_of
    diag["trading_day_trail"] = {k: [{"date": d, "n": n} for d, n in v]
                                 for k, v in day_trail.items()}

    # (4) 그 날 종가가 있는 종목만 주식총수를 조회한다 — 값을 못 쓸 종목에 호출을 낭비하지 않는다.
    jobs, want_by_sid = [], {}
    for sid, _nom, _pe, yy, rc, _as, _need in SNAPSHOT_SPEC:
        eff = eff_of.get(sid)
        if not eff:
            want_by_sid[sid] = []
            continue
        want = []
        for t in tickers:
            c, _u, _b = PRICE_STORE.close_asof(t, eff)
            if c and code2corp.get(t):
                want.append(t)
        want_by_sid[sid] = want
        have = scan_blob_inventory(DIR_CACHE_SHARES).get((yy, rc), set())
        todo = [(code2corp[t], yy, rc) for t in want if code2corp[t] not in have]
        restored = restore_blobs_from_drive("shares", todo)
        if restored:
            have = scan_blob_inventory(DIR_CACHE_SHARES).get((yy, rc), set())
            todo = [(code2corp[t], yy, rc) for t in want if code2corp[t] not in have]
        jobs += todo
        LOG(f"    {sid} ({yy}/{rc}): 종가보유 {len(want):,}종목 / 주식총수 신규 필요 {len(todo):,}건"
            + (f" / 드라이브복원 {restored:,}" if restored else ""))
    diag["shares_jobs"] = len(jobs)

    if jobs:
        LOG(f"  주식총수 수집 시작 — {len(jobs):,}건 "
            f"(오늘 누적 {col.calls_today:,} / 중단임계 {CALL_BUDGET_STOP_CUMULATIVE:,})")
        done, remain = col.run("shares", jobs, "주식총수")
        diag["shares_collected"] = done
        diag["shares_remaining"] = len(remain)
        if col.halt:
            WARN(f"  주식총수 수집 중단({col.halt}) — 남은 {len(remain):,}건. "
                 f"확보된 분량으로 계속하되, 시총 결측 종목은 유니버스에서 빠진다(결측은 결측으로).")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            sync_blobs_to_drive("shares", [(code2corp[t], yy, rc)
                                           for t in want_by_sid.get(sid, []) if code2corp.get(t)])

    # (5) 시총 재구성
    out, cov = {}, {}
    for sid, nom, _pe, yy, rc, _as, _need in SNAPSHOT_SPEC:
        eff = eff_of.get(sid)
        if not eff:
            out[sid] = (None, None)
            cov[sid] = {"reason": "거래일을 찾지 못했다(종가 결측)"}
            continue
        codes, caps, mkts = [], [], []
        n_no_shares = n_no_price = n_stale = 0
        stale_max = 0
        treasury_sum = 0
        for t in want_by_sid.get(sid, []):
            cp = code2corp.get(t, "")
            p = shares_path(cp, yy, rc)
            if not p.exists():
                n_no_shares += 1
                continue
            parsed = parse_shares_payload(read_json(p))
            sh = parsed.get("shares")
            if not sh or sh <= 0:
                n_no_shares += 1
                continue
            close, used, back = PRICE_STORE.close_asof(t, eff)
            if not close:
                n_no_price += 1
                continue
            if back > 0:
                n_stale += 1
                stale_max = max(stale_max, back)
            if PLANC_DEDUCT_TREASURY and parsed.get("treasury"):
                sh = max(0, sh - int(parsed["treasury"]))
            treasury_sum += int(parsed.get("treasury") or 0)
            codes.append(t)
            caps.append(float(sh) * float(close))
            mkts.append(parsed.get("corp_cls") or "")
        snap = _mk_snapshot(codes, caps, mkts) if codes else None
        cov[sid] = {"eff_date": eff, "candidates": len(want_by_sid.get(sid, [])),
                    "computed": 0 if snap is None else int(len(snap)),
                    "no_shares": n_no_shares, "no_price": n_no_price,
                    "stale_price_used": n_stale, "stale_price_max_days": stale_max,
                    "treasury_shares_total": treasury_sum,
                    "treasury_deducted": PLANC_DEDUCT_TREASURY}
        if snap is not None:
            try:
                _snap_write_csv(snap, _planc_snap_path(eff))
            except DiskFull:
                raise
            except OSError:
                pass
        out[sid] = (eff, snap)
        LOG(f"    {sid} 재구성 완료 — {0 if snap is None else len(snap):,}종목 "
            f"(주식총수 결측 {n_no_shares:,} / 종가 결측 {n_no_price:,} / "
            f"직전종가 사용 {n_stale:,}, 최대 {stale_max}일)")
    PLANC["coverage"] = cov
    diag["coverage"] = cov
    return {"status": "OK", "snapshots": out, "diag": diag}


def planc_cross_validate(planc_snaps) -> dict:
    """§2.3 필수 — Plan C 순위 vs S4 실측 순위의 스피어만 상관. 0.95 미만이면 판정표에 명시."""
    res = {"performed": False, "reason": "", "spearman": None,
           "threshold": PLANC_XVAL_MIN_SPEARMAN, "trustworthy": None}
    eff, snap = planc_snaps.get("S4", (None, None))
    if snap is None:
        res["reason"] = "Plan C 가 S4 스냅샷을 만들지 못했다"
        return res
    ref_path = None
    for cand in [eff, SNAPSHOT_SPEC[3][1]]:
        if cand and _krx_snap_path(cand).exists():
            ref_path = _krx_snap_path(cand)
            res["reference_date"] = cand
            break
    if ref_path is None:
        res["reason"] = (f"비교 기준이 될 KRX 실측 스냅샷(local_cache 의 "
                         f"krx_market_{compact(eff or SNAPSHOT_SPEC[3][1])}.csv)이 없다 — "
                         f"교차검증을 수행하지 못했다.")
        return res
    ref = _snap_read_csv(ref_path)
    if ref is None:
        res["reason"] = f"기준 스냅샷을 읽지 못했다: {ref_path}"
        return res
    common = sorted(set(snap.index) & set(ref.index))
    res.update({"reference_file": str(ref_path), "n_planc": int(len(snap)),
                "n_reference": int(len(ref)), "n_common": len(common)})
    if len(common) < 200:
        res["reason"] = f"공통 종목이 {len(common)}개뿐이라 순위상관이 의미 없다"
        return res
    rho = spearman([float(snap.loc[c, "cap"]) for c in common],
                   [float(ref.loc[c, "cap"]) for c in common])
    res["performed"] = True
    res["spearman"] = None if rho is None else round(float(rho), 6)

    # 이번 용도는 '시총 하위 1,000 컷'이므로, 그 컷 자체가 얼마나 재현되는지도 함께 본다.
    pl_bottom = set(snap.loc[common].sort_values("cap").index[:MEASURE_N])
    rf_bottom = set(ref.loc[common].sort_values("cap").index[:MEASURE_N])
    inter = len(pl_bottom & rf_bottom)
    res["bottom_n"] = MEASURE_N
    res["bottom_overlap"] = inter
    res["bottom_overlap_ratio"] = round(inter / max(1, min(len(pl_bottom), len(rf_bottom))), 4)
    res["trustworthy"] = bool(rho is not None and rho >= PLANC_XVAL_MIN_SPEARMAN)
    LOG(f"  Plan C 교차검증: 공통 {len(common):,}종목 / 스피어만 "
        f"{'—' if rho is None else f'{rho:.4f}'} (기준 {PLANC_XVAL_MIN_SPEARMAN}) / "
        f"하위{MEASURE_N} 집합 일치 {inter:,}종목({res['bottom_overlap_ratio']:.1%})")
    if not res["trustworthy"]:
        WARN(f"  ★ 스피어만 상관이 {PLANC_XVAL_MIN_SPEARMAN} 미만이다 — Plan C 시총을 "
             f"신뢰할 수 없다. 이 사실을 판정표에 명시한다(수치는 그대로 산출한다).")
    return res


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 18. 사다리 오케스트레이션 + 스냅샷 조회
# ══════════════════════════════════════════════════════════════════════════════════════════
_SNAP_MEM: dict = {}
_SNAP_LK = threading.Lock()


def run_market_ladder(cc_df, code2corp) -> str:
    """§2 — Plan A → B → C 를 순서대로. 하나 성공하면 나머지는 건너뛴다. 반환: 'A'|'B'|'C'|''."""
    RULE("§2. 시장 데이터 소스 확보 — 3단 사다리 (P0_MARKET_SOURCE_LADDER)")

    LOG("  [Plan A] pykrx 최신화")
    if plan_a_pykrx():
        MARKET_SOURCE.update({"plan": "A", "name": "pykrx",
                              "detail": f"pykrx {LADDER_DIAG['plans'][-1].get('version_after')}"})
        OK("  → Plan A 성공. Plan B·C 는 건너뛴다.")
        LADDER_DIAG["selected"] = "A"
        return "A"
    WARN(f"  → Plan A 실패: {LADDER_DIAG['plans'][-1].get('reason')}")

    LOG("  [Plan B] 마켓플레이스 세션 직접 구성")
    if plan_b_marketplace():
        MARKET_SOURCE.update({"plan": "B", "name": "krx_marketplace_session",
                              "detail": ("로그인 세션" if LADDER_DIAG["plans"][-1].get("logged_in")
                                         else "비로그인 세션")})
        OK("  → Plan B 성공. Plan C 는 건너뛴다.")
        LADDER_DIAG["selected"] = "B"
        return "B"
    WARN(f"  → Plan B 실패: {LADDER_DIAG['plans'][-1].get('reason')}")

    LOG("  [Plan C] KRX 없이 시총 자체 계산 (DART 주식총수 × FDR 종가)")
    if plan_c_reconstruct(cc_df, code2corp):
        MARKET_SOURCE.update({"plan": "C", "name": "planc_reconstructed",
                              "detail": f"발행주식총수 필드={PLANC['shares_field']}, "
                                        f"자기주식 차감={PLANC_DEDUCT_TREASURY}"})
        OK("  → Plan C 성공(카나리 통과). 시총은 재구성값이며 절대 수준은 부정확할 수 있다.")
        LADDER_DIAG["selected"] = "C"
        return "C"
    WARN(f"  → Plan C 실패: {LADDER_DIAG['plans'][-1].get('reason')}")

    LADDER_DIAG["selected"] = ""
    LADDER_DIAG["conclusion"] = ("3단 모두 실패 — 시가총액을 얻을 수 없다. 4개 스냅샷 전부 "
                                 "UNVERIFIED(NO_MARKET_SOURCE) 로 처리하고, 임원현황 수집에 "
                                 "진입하지 않는다(§2.4).")
    ERR("  ★ Plan A·B·C 모두 실패했다 — §2.4 에 따라 임원현황 수집에 진입하지 않는다.")
    return ""


def get_market_snapshot(date_iso: str):
    """그 날짜의 전종목 (코드·시총·시장구분). 반환 (df|None, source, trail).

    탐색: 실행내 메모 → 로컬 캐시(선택된 Plan 의 파일) → 라이브 조회(Plan A/B 만).
    Plan C 는 planc_build_snapshots 가 미리 캐시를 채워 두므로 여기서 네트워크를 타지 않는다.

    ★ '그 날 데이터 없음'은 디스크에 캐시하지 않는다. 오늘의 휴장/빈 응답이 내일은 실데이터일
      수 있기 때문이다(소스 장애와 진짜 휴장을 응답만 보고 구분할 수 없다). 그 대가로
      휴장인 명목일자(예: 2025-12-31)는 재실행 때마다 1회씩 다시 확인한다 — 스냅샷당
      최대 1회, KRX 게이트가 1초 간격을 강제하므로 비용은 초 단위다. 확정된 거래일은
      캐시에서 나오므로 네트워크를 타지 않는다.
    """
    with _SNAP_LK:
        if date_iso in _SNAP_MEM:
            df, src = _SNAP_MEM[date_iso]
            return df, src, ["memo"]

    plan = MARKET_SOURCE.get("plan", "")
    trail = []
    if plan == "C":
        # 균일 모드에서는 실측 캐시를 쳐다보지 않는다. 스냅샷별로 소스가 섞이면 그 차이가
        # 전이의 born/died 로 위장하기 때문이다.
        cands = ([(_planc_snap_path(date_iso), "local_cache_planc")]
                 if PLANC_UNIFORM_SNAPSHOTS else
                 [(_krx_snap_path(date_iso), "local_cache_krx"),
                  (_planc_snap_path(date_iso), "local_cache_planc")])
    else:
        cands = [(_krx_snap_path(date_iso), "local_cache")]
    lp = cands[-1][0]
    for cand, src_name in cands:
        if not cand.exists():
            continue
        df = _snap_read_csv(cand)
        if df is not None:
            with _SNAP_LK:
                _SNAP_MEM[date_iso] = (df, src_name)
            return df, src_name, [f"로컬캐시({cand.name})"]
        trail.append(f"로컬캐시 손상({cand.name})")

    if plan == "A":
        df, note = snap_plan_a(date_iso)
    elif plan == "B":
        df, note = snap_plan_b(date_iso)
    else:
        df, note = None, ("Plan C 재구성 캐시 없음" if plan == "C" else "시장 소스 없음")
    trail.append(f"plan{plan or '-'}={note}")
    if df is not None:
        try:
            _snap_write_csv(df, lp)
        except DiskFull:
            raise
        except OSError:
            pass
        with _SNAP_LK:
            _SNAP_MEM[date_iso] = (df, MARKET_SOURCE.get("name") or f"plan_{plan}")
        return df, _SNAP_MEM[date_iso][1], trail

    with _SNAP_LK:
        _SNAP_MEM[date_iso] = (None, "")
    return None, "", trail


def resolve_market_day(nominal_iso: str):
    """분기말이 휴장일이면 직전 거래일로 역행한다. 거래일 판정은 달력이 아니라
    '그 날 시총>0 종목이 실제로 존재하는가'로 한다."""
    d0 = _dt.date.fromisoformat(nominal_iso)
    trail = []
    for back in range(TRADING_DAY_LOOKBACK + 1):
        d = (d0 - _dt.timedelta(days=back)).isoformat()
        snap, src, why = get_market_snapshot(d)
        if snap is not None:
            trail.append((d, f"{len(snap):,}종목 [{src}]"))
            return d, snap, src, trail
        trail.append((d, " · ".join(why) if why else "없음"))
    return None, None, "", trail


def build_universe(sid: str, nominal_iso: str):
    """반환 dict(효과일자, 시총표, 측정대상 코드집합, 전상장 코드집합, 상태, 소스 진단)."""
    eff, snap, src, trail = resolve_market_day(nominal_iso)
    for day, note in trail:
        mark = "←사용" if day == eff else ""
        LOG(f"    거래일 탐색 {day}: {note} {mark}")
    if eff is None:
        WARN(f"  {sid} 빈 유니버스 — {nominal_iso} 부터 {TRADING_DAY_LOOKBACK}일 역행했으나 "
             f"시총>0 종목 {EMPTY_UNIVERSE_MIN}개 이상을 얻지 못했다. "
             f"P0_EMPTY_UNIVERSE_GUARD 발동: 임원현황 수집에 진입하지 않는다.")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": "", "status": "UNVERIFIED",
                "status_reason": ("NO_MARKET_SOURCE" if not MARKET_SOURCE.get("plan")
                                  else "EMPTY_UNIVERSE"),
                "listed": set(), "measure": set(), "mcap": None, "n_listed_all": 0,
                "n_konex": 0, "mcap_source": "", "universe_source": ""}
    if eff != nominal_iso:
        WARN(f"  {sid} 휴장일 스냅: {nominal_iso} → {eff} (직전 거래일)")

    konex = set(snap.index[snap["mkt"] == "KNX"])
    n_unlabeled = int((snap["mkt"] == "").sum())
    if INCLUDE_KONEX or n_unlabeled == len(snap):
        listed = set(snap.index)
        if n_unlabeled == len(snap) and not INCLUDE_KONEX:
            WARN(f"  {sid} 시장구분 라벨이 전혀 없는 소스({src}) — KONEX 필터를 적용하지 못했다. "
                 f"측정 대상(시총 하위 {MEASURE_N})에 KONEX 가 섞일 수 있다(판정표에 기록).")
    else:
        listed = set(snap.index[snap["mkt"] != "KNX"])

    if len(listed) < EMPTY_UNIVERSE_MIN:
        WARN(f"  {sid} 시장 필터 후 {len(listed)}종목 — P0_EMPTY_UNIVERSE_GUARD 발동")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "UNVERIFIED",
                "status_reason": "EMPTY_UNIVERSE_AFTER_MARKET_FILTER", "listed": set(),
                "measure": set(), "mcap": None, "n_listed_all": len(snap), "n_konex": len(konex),
                "mcap_source": src, "universe_source": src}

    sub = snap.loc[sorted(listed)].sort_values("cap", ascending=True)
    measure = set(sub.index[:MEASURE_N])
    lo = sub["cap"].iloc[0] / 1e8
    hi = sub["cap"].iloc[min(len(measure), len(sub)) - 1] / 1e8
    LOG(f"    전 상장사(시총>0, {'KONEX 포함' if INCLUDE_KONEX else 'KONEX 제외'}) "
        f"{len(listed):,}종목  |  소스 전체 {len(snap):,} (KONEX {len(konex):,} / "
        f"시장라벨없음 {n_unlabeled:,})  |  소스={src}")
    LOG(f"    측정대상 = 시총 하위 {len(measure):,}종목  (최소 {lo:,.0f}억 ~ 최대 {hi:,.0f}억)")
    return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "OK",
            "status_reason": "", "listed": listed, "measure": measure, "mcap": sub,
            "n_listed_all": len(snap), "n_konex": len(konex), "n_unlabeled_market": n_unlabeled,
            "mcap_source": src, "universe_source": src}


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 19. PIT 필터 — 이번 실행 전체의 핵심 (v1.2 를 무효화했던 결함의 수정)
# ══════════════════════════════════════════════════════════════════════════════════════════
_IGNORED_CACHE_FIELDS = ("as_of", "asof", "as_of_date", "pit_as_of", "filtered", "pit_filtered")


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
#  ▣ 20. 그래프
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
#  ▣ 21. 전이 — born / died. 절대 합산하지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
def transition(prev: dict, nxt: dict):
    """교집합 = 두 스냅샷 모두에서 시총 하위 1,000 에 든 종목.

    엣지 귀속: 한쪽 끝이라도 교집합에 걸치면 그 전이의 엣지로 센다.
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 22. 부트스트랩
# ══════════════════════════════════════════════════════════════════════════════════════════
def _bootstrap():
    """경로 검사 → 디렉터리 → 로그 → 의존성 → pandas/requests/FDR import.

    pykrx 는 여기서 import 하지 않는다 — §2.1 Plan A 가 '자격증명 env 주입 이후'에만
    import 하도록 순서를 잡고 있기 때문이다(§8). 죽는 건 PROJECT_ROOT 검사와
    DART_API_KEY 부재뿐이다.
    """
    global ROOT, DIR_CACHE_RAW, DIR_CACHE_META, DIR_STATE, DIR_REPORTS
    global DIR_CACHE_MARKET, DIR_CACHE_PX, DIR_CACHE_SHARES
    global pd, requests, fdr, _LOG_FH

    # 경로 검사보다 먼저 — 그 예외 메시지 자체가 '—' 같은 cp949 불가 문자를 담고 있어서,
    # 인코딩을 먼저 손보지 않으면 진짜 원인 대신 UnicodeEncodeError 가 보인다.
    enc = _force_utf8_stdout()

    ROOT = resolve_project_root(PROJECT_ROOT)          # P0_LOCAL_ROOT_ONLY — 여기서 터진다
    DIR_CACHE_RAW = ROOT / "cache" / "raw" / "dart_exctv"
    DIR_CACHE_SHARES = ROOT / "cache" / "raw" / "dart_shares"
    DIR_CACHE_PX = ROOT / "cache" / "raw" / "px"
    DIR_CACHE_META = ROOT / "cache" / "meta"
    DIR_STATE = ROOT / "cache" / "state"
    DIR_REPORTS = ROOT / "reports"
    DIR_CACHE_MARKET = ROOT / "cache" / "market"
    for d in (DIR_CACHE_RAW, DIR_CACHE_SHARES, DIR_CACHE_PX, DIR_CACHE_META, DIR_STATE,
              DIR_REPORTS, DIR_CACHE_MARKET):
        d.mkdir(parents=True, exist_ok=True)
    _LOG_FH = open(DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")
    if "reconfigured" in enc or "utf8" not in enc.replace("-", ""):
        LOG(f"콘솔 인코딩: {enc}  (Windows cp949 등에서 로그가 죽지 않도록 UTF-8 로 맞춤)")

    _ensure_packages(["pandas", "requests", "FinanceDataReader", "pyarrow"])
    import pandas as _pd
    import requests as _rq
    pd, requests = _pd, _rq
    fdr = _try_import_fdr()
    _check_parquet()


COLLECTOR = None


def get_collector() -> "Collector":
    """DART 호출 예산·서킷 상태를 실행 전체에서 하나로 공유한다 —
    Plan C 카나리 / 주식총수 / 임원현황이 각자 카운터를 갖게 두면 예산이 이중으로 샌다."""
    global COLLECTOR
    if COLLECTOR is None:
        COLLECTOR = Collector(DART_API_KEY.strip())
    return COLLECTOR


def _est_minutes(calls: int) -> float:
    """요청 간 0.3~1.0초 랜덤(평균 0.65) / 워커 N / 왕복 오버헤드 ~0.15초 가정."""
    per = 0.65 / max(1, N_WORKERS) + 0.15
    return calls * per / 60.0


def _write_ladder_diag():
    LADDER_DIAG["endpoint_registry"] = {k: v for k, v in ENDPOINT_REGISTRY.items()}
    LADDER_DIAG["market_source"] = dict(MARKET_SOURCE)
    if MARKET_SOURCE.get("plan") == "C":
        LADDER_DIAG["plan_c"] = {k: v for k, v in PLANC.items() if k != "canary"}
        LADDER_DIAG["plan_c"]["canary"] = PLANC.get("canary", [])
    write_json(DIR_REPORTS / "diag_market_source.json", LADDER_DIAG)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 23. 메인
# ══════════════════════════════════════════════════════════════════════════════════════════
def main():
    _bootstrap()
    RULE(f"PHASE 0 — 축 A-Δ 재측정 {SPEC_VERSION}   (LIVE / 로컬 JupyterLab)")
    LOG(f"PROJECT_ROOT : {ROOT}")
    LOG(f"GDRIVE_ROOT  : {GDRIVE_ROOT or '(미설정 — 로컬 전용)'}")
    LOG(f"실행 시각    : {RUN_STARTED:%Y-%m-%d %H:%M:%S}")
    LOG(f"정렬 방식    : {ALIGNMENT} — as_of = 법정 제출기한")
    LOG(f"유니버스     : {'KOSPI+KOSDAQ+KONEX' if INCLUDE_KONEX else 'KOSPI+KOSDAQ (KONEX 제외)'}")
    LOG(f"동시성       : 워커 {N_WORKERS} / 요청간 0.3~1.0초 / 타임아웃 {HTTP_TIMEOUT}초 / "
        f"콜당 재시도 {MAX_RETRY_PER_CALL}회 / KRX 계열은 단일 스레드 + 1초 간격")

    # ── 1. 계약 검사 ─────────────────────────────────────────────────────────────────
    RULE("1. 계약 검사")
    if _sha256_thresholds() != GATE_THRESHOLDS_SHA256:
        raise ContractViolation(
            f"P0_NO_THRESHOLD_EDIT 위반: 임계값이 변경되었다.\n"
            f"  현재값={GATE_THRESHOLDS}\n  현재해시={_sha256_thresholds()}\n"
            f"  고정해시={GATE_THRESHOLDS_SHA256}")
    verify_snapshot_spec()
    vf = assert_no_verify_false()
    if not str(DART_API_KEY).strip():
        raise ContractViolation(
            "P0_LIVE_ONLY: DART_API_KEY 가 비어 있다. 합성 데이터 경로는 존재하지 않는다.\n"
            "  https://opendart.fss.or.kr/ 에서 인증키를 발급받아 상단 블록에 넣을 것.")
    for cid, desc in CONTRACTS.items():
        LOG(f"  ✓ {cid:<26} {desc}")
    LOG(f"  · P0_NO_VERIFY_FALSE 자기검사: {vf}")
    LOG(f"  · DART_API_KEY: 설정됨 (끝 4자리 …{DART_API_KEY.strip()[-4:]})")
    LOG(f"  · KRX_ID/PW  : {'설정됨 (ID=' + str(KRX_ID)[:3] + '***)' if (KRX_ID and KRX_PW) else '미설정'}")
    LOG(f"  · FinanceDataReader {'사용가능' if FDR_AVAILABLE else '미설치'} / "
        f"parquet 엔진 {'있음' if PARQUET_AVAILABLE else '없음(CSV 로 대체 저장)'}")

    # ── 2. 캐시 인벤토리 (§4.1 — 가장 먼저 출력) ──────────────────────────────────────
    RULE("2. 캐시 인벤토리 (P0_CACHE_FIRST)")
    n_local = {k: len(v) for k, v in scan_blob_inventory(DIR_CACHE_RAW).items()}
    n_shares = {k: len(v) for k, v in scan_blob_inventory(DIR_CACHE_SHARES).items()}
    est_calls = 0
    LOG("")
    LOG("캐시 인벤토리")
    for sid, _nom, _pe, yy, rc, _as, need in SNAPSHOT_SPEC:
        have = n_local.get((yy, rc), 0)
        short = max(0, need - have)
        est_calls += short
        LOG(f"  {yy}/{rc} ({sid} {REPRT_NAME[rc]:<3}) : 로컬 {have:>5,}건 / 필요 ~{need:,}건 "
            f"→ 부족 {short:>5,}건")
    corpcode_cached = _corpcode_parsed().exists()
    n_px = count_px_cached()
    LOG(f"  corpCode 파싱 결과     : {'있음' if corpcode_cached else '없음'}")
    LOG(f"  종가 캐시(Plan C용)    : {n_px:,}종목")
    _sh_txt = " / ".join(f"{k[0]}/{k[1]}={v:,}" for k, v in sorted(n_shares.items())) or "없음"
    LOG(f"  주식총수 캐시(Plan C용) : {_sh_txt}")
    LOG(f"  ── 예상 신규 API 호출: {est_calls:,}건 / 예상 소요: {_est_minutes(est_calls):.0f}분")
    LOG("     (임원현황 기준이다. Plan C 가 채택되면 주식총수·종가 수집이 §2.3 단계에서 "
        "따로 계산·보고된다.)")
    if sum(n_local.values()) == 0:
        LOG("  ※ 임원 캐시가 0건인 이유: 이전 실행이 임원현황 수집에 도달하기 전에 끝났기 "
            "때문이다. 수집을 한 번이라도 통과하면 응답 1건당 파일 1개로 즉시 저장되고, "
            "중간에 끊어도 그때까지 받은 분량은 그대로 남는다.")

    inventory = {"local_exctv_before": {f"{k[0]}/{k[1]}": v for k, v in n_local.items()},
                 "local_shares_before": {f"{k[0]}/{k[1]}": v for k, v in n_shares.items()},
                 "corpcode_parse_cache": corpcode_cached, "px_cached_tickers": n_px,
                 "estimated_new_calls_exctv": est_calls,
                 "estimated_minutes_exctv": round(_est_minutes(est_calls), 1),
                 "planned_new_calls": 0, "actual_new_calls": 0}
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    # ── 3. corpCode ──────────────────────────────────────────────────────────────────
    RULE("3. corpCode")
    cc = load_corpcode()
    corp2code = dict(zip(cc["corp_code"], cc["code"]))
    code2corp = {}
    for corp, code in zip(cc["corp_code"], cc["code"]):
        code2corp.setdefault(code, corp)
    LOG(f"  corp_code → 종목코드 매핑 {len(corp2code):,}건 / 종목코드 고유 {len(code2corp):,}건")

    # ── 4. 시장 데이터 소스 3단 사다리 (§2) ───────────────────────────────────────────
    plan = run_market_ladder(cc, code2corp)
    _write_ladder_diag()
    LOG(f"  → diag_market_source.json 저장 (선택된 Plan: {plan or '없음'})")

    # ── 5. DART 연결 진단 (§3) — 아직 안 돌았으면 여기서 돈다(멱등) ────────────────────
    run_dart_preflight()
    skip_collection = not DART_PREFLIGHT["ok"] and not DART_PREFLIGHT["code_fixable"]
    if skip_collection:
        WARN("  §3.4 발동: 임원현황 수집에 진입하지 않고, 캐시된 분량으로만 측정한다.")

    # ── 6. Plan C 벌크 재구성 (선택된 경우에만) ───────────────────────────────────────
    planc_snaps, xval = {}, {}
    if plan == "C":
        RULE("6. Plan C — 시가총액 재구성 (발행주식총수 × 종가)")
        if skip_collection:
            WARN("  DART 연결이 코드로 해결 불가 상태라 주식총수 수집을 할 수 없다 — "
                 "이미 캐시된 주식총수만으로 재구성한다.")
        built = planc_build_snapshots(cc, code2corp, get_collector())
        if built["status"] == "AWAITING_USER_CONFIRMATION":
            inventory["planc"] = built["diag"]
            write_json(DIR_REPORTS / "cache_inventory.json", inventory)
            LADDER_DIAG["conclusion"] = ("Plan C 채택. 예상 신규 호출이 5,000건을 넘어 "
                                         "P0_CACHE_FIRST 로 수집 전 대기 중.")
            _write_ladder_diag()
            return {"status": "AWAITING_USER_CONFIRMATION",
                    "planned_calls": built["diag"].get("estimated_total_new_calls"),
                    "stage": "PLAN_C_BULK", "cache_inventory": inventory}
        planc_snaps = built["snapshots"]
        inventory["planc"] = built["diag"]
        # 재구성 결과를 스냅샷 메모에 심는다 — 이후 build_universe 는 네트워크를 타지 않는다.
        for sid, (eff, snap) in planc_snaps.items():
            if eff and snap is not None:
                with _SNAP_LK:
                    _SNAP_MEM[eff] = (snap, "planc_reconstructed")
        xval = planc_cross_validate(planc_snaps)
        PLANC["cross_validation"] = xval
        _write_ladder_diag()
        if PLANC_UNIFORM_SNAPSHOTS:
            LOG("  ※ Plan C 채택 시 4개 스냅샷 전부를 Plan C 로 만든다. S4 에 KRX 실측 캐시가 "
                "있어도 유니버스 구성에는 쓰지 않는다 — 스냅샷마다 시총 소스가 다르면 그 "
                "차이 자체가 S3→S4 전이에서 가짜 신호로 보이기 때문이다. 실측 캐시는 위 "
                "교차검증의 기준값으로만 쓴다.")

    # ── 7. 유니버스 확정 ──────────────────────────────────────────────────────────────
    RULE("7. 유니버스 확정 — 거래일 스냅 + 빈 유니버스 가드")
    universes = {}
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        LOG(f"  {sid} 기준일 {nom} / {yy}-{rc} {REPRT_NAME[rc]} / as_of {as_of}")
        universes[sid] = build_universe(sid, nom)

    live_ids = [s for s in universes if universes[s]["status"] == "OK"]
    if not live_ids:
        ERR("  모든 스냅샷이 UNVERIFIED 다 — 임원현황 수집에 진입하지 않는다(§2.4).")

    # ── 8. 임원현황 수집 대상 확정 → 게이트 → 수집 ───────────────────────────────────
    RULE("8. 임원현황 수집 대상 확정")
    col = get_collector()
    jobs_by_snap, all_jobs, drive_restored = {}, [], 0
    inv_after = scan_blob_inventory(DIR_CACHE_RAW)
    for sid, _nom, _pe, yy, rc, _as, _need in SNAPSHOT_SPEC:
        u = universes[sid]
        if u["status"] != "OK":
            jobs_by_snap[sid] = []
            LOG(f"  {sid}: {u.get('status_reason')} — 수집 진입 안 함")
            continue
        want = sorted({code2corp[c] for c in u["listed"] if c in code2corp})
        u["corp_wanted"] = want
        u["unmapped_codes"] = len(u["listed"]) - len(want)
        have = inv_after.get((yy, rc), set())
        missing_local = [(cp, yy, rc) for cp in want if cp not in have]
        restored = restore_blobs_from_drive("exctv", missing_local)
        drive_restored += restored
        if restored:
            have = inv_after[(yy, rc)] = have | {cp for cp, _y, _r in missing_local
                                                 if cache_path(cp, yy, rc).exists()}
        todo = [(cp, yy, rc) for cp in want if cp not in have]
        jobs_by_snap[sid] = todo
        all_jobs += todo
        LOG(f"  {sid}: 전상장 {len(u['listed']):,}종목 → corp_code 매핑 {len(want):,}건 "
            f"(미매핑 {u['unmapped_codes']:,}) / 캐시보유 {len(want) - len(missing_local):,} / "
            f"드라이브복원 {restored:,} / 신규필요 {len(todo):,}")

    inventory["drive_restored"] = drive_restored
    inventory["planned_new_calls"] = len(all_jobs)
    LOG(f"  ── 실제 신규 API 호출 예정: {len(all_jobs):,}건 / 예상 소요 "
        f"{_est_minutes(len(all_jobs)):.0f}분 — 아직 수집을 시작하지 않았다")
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    if skip_collection and all_jobs:
        WARN(f"  DART 연결 진단이 '코드로 해결 불가'로 끝났다 — 신규 {len(all_jobs):,}건을 "
             f"수집하지 않는다(§3.4). 캐시된 분량으로만 계속한다.")
        all_jobs = []
        jobs_by_snap = {k: [] for k in jobs_by_snap}
    elif col.halt:
        # Plan C 주식총수 단계에서 이미 예산/서킷으로 멎은 상태다. 여기서 '5,000건 초과라
        # 대기'를 안내하면 사용자가 원인을 잘못 짚는다 — 중단 사유를 그대로 이어서 남긴다.
        WARN(f"  이미 중단 상태({col.halt})다 — 임원현황 수집에 진입하지 않고 "
             f"resume_todo.json 에 남은 작업을 기록한다.")
        all_jobs = []
    elif len(all_jobs) > LARGE_COLLECTION_GATE and not CONFIRM_LARGE_COLLECTION:
        WARN(f"P0_CACHE_FIRST: 실제 신규 호출 {len(all_jobs):,}건 > {LARGE_COLLECTION_GATE:,}건.")
        WARN("수집에 진입하지 않고 여기서 멈춘다. 위 내역을 확인한 뒤")
        WARN("  CONFIRM_LARGE_COLLECTION = True")
        WARN("로 바꾸고 셀을 다시 실행할 것. (이미 받은 캐시는 그대로 재사용된다)")
        return {"status": "AWAITING_USER_CONFIRMATION", "planned_calls": len(all_jobs),
                "stage": "EXCTV", "cache_inventory": inventory}

    if all_jobs:
        RULE("8b. 임원현황 수집")
        LOG(f"  오늘 이전 실행분 누적 {col.calls_today:,}건 + 이번 예정 {len(all_jobs):,}건 "
            f"(중단임계 {CALL_BUDGET_STOP_CUMULATIVE:,} / 일일한도 {CALL_BUDGET_DAILY:,})")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            todo = jobs_by_snap[sid]
            if not todo or col.halt:
                continue
            LOG(f"  {sid} ({yy}/{rc}) 신규 {len(todo):,}건 수집")
            done, remain = col.run("exctv", todo, sid)
            universes[sid]["api_new"] = done
            jobs_by_snap[sid] = remain
        LOG(f"  응답 분포: {dict(col.stat)}")
        _after = scan_blob_inventory(DIR_CACHE_RAW)
        OK(f"  저장 확인: 임원 캐시 총 {sum(len(v) for v in _after.values()):,}건이 디스크에 "
           f"있다 → 다음 실행은 이만큼 건너뛴다")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            got = len(_after.get((yy, rc), set()))
            if got:
                LOG(f"    {sid} {yy}/{rc}: {got:,}건 저장됨")
    elif live_ids:
        OK("  신규 호출 0건 — 전량 캐시 히트")

    if col.halt:
        left = [list(j) for sid in jobs_by_snap for j in jobs_by_snap[sid]]
        write_json(DIR_REPORTS / "resume_todo.json",
                   {"halt": col.halt, "calls_run": col.calls_run,
                    "calls_today": col.calls_today,
                    "stop_threshold": CALL_BUDGET_STOP_CUMULATIVE,
                    "daily_limit": CALL_BUDGET_DAILY,
                    "note": "다음 실행이 캐시를 전부 재사용하고 여기부터 이어받는다. "
                            "남은 목록은 참고용이며, 실제 재개 대상은 다음 실행이 캐시를 "
                            "다시 스캔해 정확히 계산한다.",
                    "remaining_exctv": left,
                    "remaining_shares": inventory.get("planc", {}).get("shares_remaining", 0),
                    "remaining": left})
        WARN(f"수집 중단({col.halt}) — 남은 {len(left):,}건을 resume_todo.json 에 저장했다. "
             f"수집된 분량으로 측정을 계속한다(결측은 결측으로 남는다).")

    if GDRIVE_ROOT:
        RULE("8c. 드라이브 증분 동기화")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            u = universes[sid]
            if u["status"] != "OK" or not u.get("corp_wanted"):
                continue
            sync = sync_blobs_to_drive("exctv", [(cp, yy, rc) for cp in u["corp_wanted"]])
            if sync["attempted"]:
                LOG(f"  {sid}: 신규 {sync['synced']:,} / 이미있음 {sync['already_there']:,}" +
                    (f" / 오류 {sync['error']}" if sync["error"] else ""))

    inventory["actual_new_calls"] = col.calls_run
    inventory["collector_stat"] = dict(col.stat)
    inventory["halt"] = col.halt
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    # ── 9. PIT 필터 + 그래프 ─────────────────────────────────────────────────────────
    RULE("9. PIT 필터 + 그래프 구성")
    snap_out, pit_rows = [], []
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        u = universes[sid]
        rec = {"id": sid, "date": u["date"] or nom, "date_nominal": nom, "as_of": as_of,
               "report": f"{yy}/{rc}", "report_name": REPRT_NAME[rc],
               "nodes": len(u["listed"]), "nodes_with_exctv": 0, "edges": 0,
               "pit_dropped": 0, "pit_dropped_lookahead": 0, "pit_dropped_bad_rcept": 0,
               "pit_kept": 0, "last_rcept_dt": "", "first_rcept_dt": "",
               "cache_hit": 0, "cache_miss": 0, "api_new": int(u.get("api_new", 0)),
               "records_no_birth": 0, "status": u["status"],
               "status_reason": u.get("status_reason", ""),
               "mcap_source": u.get("mcap_source", ""),
               "universe_source": u.get("universe_source", ""),
               "n_listed_all": int(u.get("n_listed_all", 0)),
               "n_konex": int(u.get("n_konex", 0)),
               "n_unlabeled_market": int(u.get("n_unlabeled_market", 0))}
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
                    "pit_dropped_lookahead": n_look, "pit_dropped_bad_rcept": n_bad,
                    "files_read": hit, "cache_hit": max(0, hit - rec["api_new"]),
                    "cache_miss": miss, "records_raw": len(raw_recs)})

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

        # ★ PIT 필터가 실제로 걸렸는지의 하드 검사
        if rec["last_rcept_dt"] and rec["last_rcept_dt"] > compact(as_of):
            raise ContractViolation(
                f"P0_PIT_STRICT_DELTA 위반: {sid} 최종접수일 {rec['last_rcept_dt']} > "
                f"as_of {compact(as_of)}. 필터가 걸리지 않았다 — 즉시 중단한다.")
        if n_look == 0 and len(raw_recs) > 0:
            WARN(f"    ★ {sid} 룩어헤드 폐기 0건 — 명령서 §5.1 은 이 경우 '필터가 안 걸린 "
                 f"것이므로 즉시 중단하고 보고'하라고 한다. diag_pit_dropped_delta.csv 를 "
                 f"반드시 확인할 것(성공조건 ①이 미충족으로 기록된다).")

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

    # ── 10. 전이 ─────────────────────────────────────────────────────────────────────
    RULE("10. 전이 — edge_born / edge_died (합산하지 않는다)")
    trans_out, per_stock = [], []
    for a, b in TRANSITIONS:
        ua, ub = universes[a], universes[b]
        if ua["status"] != "OK" or ub["status"] != "OK" or not isinstance(ua.get("edges"), set) \
                or not isinstance(ub.get("edges"), set):
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

    # ── 11. 게이트 ───────────────────────────────────────────────────────────────────
    RULE("11. 판정 게이트")
    ok_t = [t for t in trans_out if t.get("status") == "OK"]
    ratios = [t["born_ratio"] for t in ok_t]
    borns = [t["edge_born"] for t in ok_t]
    n_graph_ok = sum(1 for s in snap_out if s["status"] == "OK" and s["nodes_with_exctv"] > 0)

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

    # ── 12. 성공 조건 — 게이트 통과 여부와 무관하다 (§10) ────────────────────────────
    RULE("12. 성공 조건")
    live = [s for s in snap_out if s["status"] == "OK"]
    c1_each = [{"snapshot": s["id"], "pit_dropped": s["pit_dropped"],
                "lookahead": s["pit_dropped_lookahead"], "last_rcept_dt": s["last_rcept_dt"],
                "as_of": compact(s["as_of"]),
                "within_as_of": bool(s["last_rcept_dt"]) and s["last_rcept_dt"] <= compact(s["as_of"])}
               for s in snap_out]
    live_ids_set = {s["id"] for s in live}
    c1 = (len(live) == 4 and all(s["pit_dropped"] > 0 for s in live)
          and all(x["within_as_of"] for x in c1_each if x["snapshot"] in live_ids_set))
    c2 = len(ok_t) == len(TRANSITIONS) and all(
        t["edge_born"] is not None and t["edge_died"] is not None for t in ok_t)
    c1_lookahead = len(live) == 4 and all(s["pit_dropped_lookahead"] > 0 for s in live)
    LOG(f"  ① 4개 스냅샷 PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : {'충족' if c1 else '미충족'}")
    LOG(f"     (그 중 룩어헤드 폐기가 4개 스냅샷 모두 ≠ 0 : {'예' if c1_lookahead else '아니오'})")
    for x in c1_each:
        LOG(f"       {x['snapshot']}: 폐기 {x['pit_dropped']:,}건 (룩어헤드 {x['lookahead']:,}) / "
            f"최종접수일 {x['last_rcept_dt'] or '—'} ≤ as_of {x['as_of']} → "
            f"{'OK' if x['within_as_of'] else 'NG'}")
    LOG(f"  ② 전이 3개의 edge_born / edge_died 산출              : {'충족' if c2 else '미충족'}")
    LOG(f"  ⇒ 이번 실행: {'성공' if (c1 and c2) else '미완'}  (수치의 크기는 성공 여부와 무관)")

    # ── 13. 산출물 ───────────────────────────────────────────────────────────────────
    RULE("13. 산출물")
    LADDER_DIAG["conclusion"] = LADDER_DIAG.get("conclusion") or (
        f"Plan {plan} 채택 — {MARKET_SOURCE.get('name')} ({MARKET_SOURCE.get('detail')})"
        if plan else "3단 모두 실패")
    _write_ladder_diag()

    verdict = {
        "run_mode": "LIVE",
        "spec_version": SPEC_VERSION,
        "generated_at": RUN_STARTED.isoformat(timespec="seconds"),
        "project_root": str(ROOT),
        "gdrive_root": GDRIVE_ROOT or "",
        "alignment": ALIGNMENT,
        "alignment_note": "(A) 관측시점 정렬 — as_of = 해당 보고서의 법정 제출기한",
        "market_source_ladder": LADDER_DIAG,
        "dart_preflight": DART_PREFLIGHT.get("detail", {}),
        "plan_c": (PLANC if plan == "C" else {"used": False}),
        "data_sources": {
            "selected_plan": plan or "NONE",
            "market_source": dict(MARKET_SOURCE),
            "pykrx_available": PYKRX_AVAILABLE, "pykrx_diagnostic": PYKRX_DIAGNOSTIC,
            "pykrx_import_log": PYKRX_IMPORT_LOG,
            "fdr_available": FDR_AVAILABLE, "parquet_available": PARQUET_AVAILABLE,
            "krx_credentials_set": bool(KRX_ID and KRX_PW),
        },
        "methodology": {
            "universe": "KOSPI+KOSDAQ+KONEX" if INCLUDE_KONEX else "KOSPI+KOSDAQ (KONEX 제외)",
            "measure_n": MEASURE_N,
            "node": "종목코드 (해당 스냅샷 거래일의 시총>0 상장사 전체)",
            "edge": "(성명, 출생년월) 동일 인물이 두 종목에 동시 임원 등재",
            "edge_attribution": "교집합 종목에 한쪽 끝이라도 걸친 엣지",
            "birth_missing": "엣지 생성에서 제외 (보간하지 않음)",
            "empty_universe_min": EMPTY_UNIVERSE_MIN,
            "mcap_source": MARKET_SOURCE.get("name") or "NONE",
            "mcap_ladder": "Plan A(pykrx) → Plan B(마켓플레이스 세션) → Plan C(DART 주식총수 × FDR 종가)",
            "planc_uniform_snapshots": PLANC_UNIFORM_SNAPSHOTS if plan == "C" else None,
            "workers": N_WORKERS, "timeout_sec": HTTP_TIMEOUT,
            "retry_per_call": MAX_RETRY_PER_CALL,
            "circuit_rule": f"재시도를 모두 소진한 콜이 연속 {CIRCUIT_FAIL_N}건",
            "budget": {"daily_limit": CALL_BUDGET_DAILY,
                       "cumulative_stop": CALL_BUDGET_STOP_CUMULATIVE},
        },
        "contracts": [{"id": k, "desc": v, "status": "ENFORCED"} for k, v in CONTRACTS.items()],
        "contract_no_verify_false_selfcheck": vf,
        "thresholds": GATE_THRESHOLDS,
        "thresholds_sha256": _sha256_thresholds(),
        "snapshots": snap_out,
        "transitions": trans_out,
        "gates": gates,
        "success_conditions": {"pit_evidence": bool(c1), "lookahead_evidence": bool(c1_lookahead),
                               "delta_measured": bool(c2), "overall": bool(c1 and c2),
                               "detail": c1_each},
        "cache": inventory,
        "skipped": [
            {"axis": "A(본체)", "status": "SKIPPED_BY_SCOPE",
             "note": "A-1/A-2/A-3 는 이전 실행에서 확인 완료 — 재측정하지 않는다"},
            {"axis": "B(BigQuery)", "status": "SKIPPED_BY_SCOPE"},
            {"axis": "C(국민연금)", "status": "SKIPPED_BY_SCOPE"},
            {"axis": "KRX Open API", "status": "SKIPPED_BY_SCOPE",
             "note": "§1.2 — Open API 인증키는 ID/PW 와 별개이고 이번 실행은 승인을 기다리지 않는다"},
        ],
        "known_limitations": KNOWN_LIMITATIONS + (
            [f"Plan C 교차검증: 스피어만 {xval.get('spearman')} "
             f"(기준 {PLANC_XVAL_MIN_SPEARMAN}) — "
             f"{'신뢰 가능' if xval.get('trustworthy') else '기준 미달이거나 검증 불가. ' + str(xval.get('reason') or '')}"]
            if plan == "C" else []),
    }
    write_json(DIR_REPORTS / f"phase0_verdict_{SPEC_VERSION.replace('.', '')}.json", verdict)

    rows = []
    for s in snap_out:
        rows.append({"section": "snapshot", "key": s["id"],
                     **{k: v for k, v in s.items() if k not in ("id", "top_multi")}})
    for t in trans_out:
        rows.append({"section": "transition", "key": f"{t['from']}->{t['to']}",
                     **{k: v for k, v in t.items() if k not in ("from", "to")}})
    for g in gates:
        rows.append({"section": "gate", "key": g["id"],
                     **{k: v for k, v in g.items() if k != "id"}})
    pd.DataFrame(rows).to_csv(DIR_REPORTS / f"phase0_verdict_{SPEC_VERSION.replace('.', '')}.csv",
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

    _write_summary_md(verdict, snap_out, trans_out, gates, c1, c2, plan, xval)

    for f in (f"phase0_verdict_{SPEC_VERSION.replace('.', '')}.json",
              f"phase0_verdict_{SPEC_VERSION.replace('.', '')}.csv",
              f"phase0_summary_{SPEC_VERSION.replace('.', '')}.md",
              "diag_market_source.json", "diag_dart_preflight.json", "diag_edge_events.csv",
              "diag_pit_dropped_delta.csv", "cache_inventory.json", "run_log.txt"):
        p = DIR_REPORTS / f
        LOG(f"  {'✓' if p.exists() else '✗'} {p}")
    rt = DIR_REPORTS / "resume_todo.json"
    LOG(f"  {'✓' if rt.exists() else '·'} {rt}  ({'중단 있음' if col.halt else '중단 없음'})")
    RULE("완료")
    return verdict


def _write_summary_md(verdict, snap_out, trans_out, gates, c1, c2, plan, xval):
    """판정과 근거 수치만. 해석·전략 제안은 쓰지 않는다(§9)."""
    v = SPEC_VERSION.replace(".", "")
    md = [f"# PHASE 0 — 축 A-Δ 재측정 {SPEC_VERSION} 요약", "",
          f"- 실행: {RUN_STARTED:%Y-%m-%d %H:%M}  ·  run_mode: LIVE  ·  PROJECT_ROOT: `{ROOT}`",
          f"- 정렬: {ALIGNMENT} (as_of = 법정 제출기한)",
          f"- 유니버스: {verdict['methodology']['universe']}  ·  측정대상: 시총 하위 {MEASURE_N}종목",
          f"- 시장 데이터 소스: **Plan {plan or '없음'}** "
          f"({MARKET_SOURCE.get('name') or 'NONE'} / {MARKET_SOURCE.get('detail') or '—'})",
          f"- DART 연결 진단: {DART_PREFLIGHT.get('classification') or '(미실행)'} "
          f"→ {'정상' if DART_PREFLIGHT.get('ok') else ('코드로 해결 가능' if DART_PREFLIGHT.get('code_fixable') else '코드로 해결 불가')}",
          "", "## 시장 데이터 3단 사다리 (§2)", "",
          "| Plan | 내용 | 결과 | 사유 |", "|---|---|---|---|"]
    for p in LADDER_DIAG["plans"]:
        md.append(f"| {p['plan']} | {p['title']} | {'성공' if p['ok'] else '실패'} | "
                  f"{(p.get('reason') or '—').replace('|', '/')[:220]} |")
    if not LADDER_DIAG["plans"]:
        md.append("| — | (사다리를 실행하지 않았다) | — | — |")
    if plan == "C" and xval:
        md += ["", "### Plan C 교차검증 (S4 실측 대비)", "",
               f"- 스피어만 순위상관: **{xval.get('spearman')}** (기준 {PLANC_XVAL_MIN_SPEARMAN})",
               f"- 공통 종목: {xval.get('n_common', '—')}  ·  하위{MEASURE_N} 집합 일치: "
               f"{xval.get('bottom_overlap', '—')} ({xval.get('bottom_overlap_ratio', '—')})",
               f"- 판정: {'신뢰 가능' if xval.get('trustworthy') else '**신뢰할 수 없음**'} "
               f"{('— ' + str(xval.get('reason'))) if xval.get('reason') else ''}"]
    md += ["", "## 스냅샷", "",
           "| 스냅샷 | 기준일(명목→사용) | 보고서 | as_of | 노드 | 엣지 | PIT폐기(룩어헤드) | "
           "최종접수일 | 캐시히트 | 미보유 | 신규호출 | 시총소스 | 상태 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in snap_out:
        d = s["date_nominal"] if s["date_nominal"] == s["date"] else f"{s['date_nominal']}→{s['date']}"
        md.append(f"| {s['id']} | {d} | {s['report']} {s['report_name']} | {s['as_of']} | "
                  f"{s['nodes']:,} | {s['edges']:,} | {s['pit_dropped']:,} "
                  f"({s['pit_dropped_lookahead']:,}) | {s['last_rcept_dt'] or '—'} | "
                  f"{s['cache_hit']:,} | {s.get('cache_miss', 0):,} | {s['api_new']:,} | "
                  f"{s.get('mcap_source') or '—'} | {s['status']} |")
    md += ["", "## 전이 (이 실행의 유일한 질문)", "",
           "| 전이 | 교집합 | edge_born | edge_died | born_ratio | 양끝상장 born/died | 상태 |",
           "|---|---|---|---|---|---|---|"]
    for t in trans_out:
        br = "—" if t.get("born_ratio") is None else f"{t['born_ratio']:.4f}"
        md.append(f"| {t['from']}→{t['to']} | {t['intersect']:,} | "
                  f"{t['edge_born'] if t['edge_born'] is not None else '—'} | "
                  f"{t['edge_died'] if t['edge_died'] is not None else '—'} | {br} | "
                  f"{t.get('born_both_listed', '—')}/{t.get('died_both_listed', '—')} | "
                  f"{t.get('status')} |")
    md += ["", "## 게이트", "", "| ID | 내용 | 실측 | 임계 | 판정 |", "|---|---|---|---|---|"]
    for g in gates:
        val = "—" if g["value"] is None else (f"{g['value']:.4f}" if isinstance(g["value"], float)
                                              else f"{g['value']:,}")
        md.append(f"| {g['id']} | {g['desc']} | {val} | {g['threshold']} | {g['status']} |")
    md += ["", "## 성공 조건 (§10 — 게이트 통과 여부와 무관)", "",
           f"- ① PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : **{'충족' if c1 else '미충족'}**",
           f"- ② 전이 3개 edge_born/edge_died 산출 : **{'충족' if c2 else '미충족'}**", "",
           "## 범위 밖", "",
           "- 축 A 본체(A-1/A-2/A-3): 이전 실행 확인 완료 — 재측정 안 함",
           "- 축 B(BigQuery) / 축 C(국민연금): SKIPPED_BY_SCOPE",
           "- KRX Open API 승인 대기: §1.2 에 따라 이번 실행 범위 밖",
           "", "## known_limitations", ""]
    md += [f"{i}. {s}" for i, s in enumerate(verdict["known_limitations"], 1)]
    write_text(DIR_REPORTS / f"phase0_summary_{v}.md", "\n".join(md) + "\n")


if __name__ == "__main__":
    try:
        VERDICT = main()
    except (ContractViolation, DiskFull, HardStop) as _e:
        ERR(f"{type(_e).__name__}: {_e}")
        raise
