#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 0 — 축 A-Δ 재측정 v1.3   (엔지니어링 개정판 · 로컬 JupyterLab 전용 · LIVE 전용)      ║
# ║                                                                                          ║
# ║  이 실행의 유일한 질문:  분기마다 겸직 링크가 실제로 몇 개나 생기고 사라지는가?              ║
# ║  측정 로직(PIT 필터·그래프·전이) 자체는 검증이 끝난 상태로, 이번 개정에서 건드리지 않았다.   ║
# ║                                                                                          ║
# ║  ── 이번 개정의 계기 ────────────────────────────────────────────────────────────────────  ║
# ║   실사용 중 pykrx import 자체가 JSONDecodeError 로 죽는 크래시가 발생했다:                  ║
# ║     pykrx/website/comm/webio.py:12  _session = build_krx_session()  ← 모듈 로드 시점       ║
# ║     → login_krx() 가 KRX 로그인 응답을 resp.json() 으로 파싱하는데 try/except 가 없다.      ║
# ║     KRX 가 JSON 대신 에러 페이지를 주면 import pykrx 자체가 예외를 던지며 전체가 멎는다.     ║
# ║     (이 실패 시그니처는 build/10_ingest_universe.py 의 KRXGate 주석에 이미 기록돼 있던       ║
# ║      바로 그 pykrx 1.2.8 결함이다 — "Expecting value: line 13 column 1")                   ║
# ║                                                                                          ║
# ║  ── 이번 개정 내용 (근본 수정 + 확장) ───────────────────────────────────────────────────  ║
# ║   ① pykrx import 를 방탄화 — 어떤 예외든 흡수하고, 실패하면 무자격 재시도 후 그래도         ║
# ║      실패하면 PYKRX_AVAILABLE=False 로 전환해 폴백 경로로 계속 진행한다(§4). 이후 모든       ║
# ║      stock.* 호출도 pykrx_call() 래퍼를 거쳐 절대 예외를 밖으로 흘리지 않는다.               ║
# ║   ② 시가총액 1순위 소스로 KRX Open API 추가 — pykrx 가 완전히 죽어도 시총 조회가 가능하다    ║
# ║      (§5). 상장종목 목록은 pykrx 실패 시 DART corpCode + FDR + KIND 다중소스 병합으로        ║
# ║      생존자편향 없이 폴백한다(§7).                                                          ║
# ║   ③ 캐시를 tar.gz 일괄 백업에서 공용/전용 인덱스 이중탐색(로컬→드라이브) 구조로 교체.        ║
# ║      dart_corpcode·security_master 는 이 저장소의 다른 전략(build/10_ingest_universe.py)    ║
# ║      과 동일한 공용 테이블명으로 저장해 캐시를 상호 재활용한다(§9). 신규 수집 원본은          ║
# ║      스냅샷 단위로 즉시 드라이브에 증분 동기화한다(§11.4) — 실행 종료를 기다리지 않는다.     ║
# ║   ④ 호출예산 재설계 — 이전 판의 '중도정지 12,000'은 실제 필요량(~11,078건)보다 여유가        ║
# ║      너무 적어 정상적인 콜드런도 중도에 멎을 수 있었다. 그 임의 임계를 없애고 '일일 실한도    ║
# ║      기준 사전 계산'으로 대체했다. 실시간 소진 신호는 DART status=020 응답이 권위를 가진다   ║
# ║      (§11).                                                                              ║
# ║   ⑤ 적응형 지연 — 고정 슬립을 성공 스트릭엔 가속·실패엔 즉시 감속하는 방식으로 교체(§8).     ║
# ║      동일 (소스,날짜) 재조회는 실행 내 메모이제이션으로 제거한다.                            ║
# ║                                                                                          ║
# ║  붙여넣기: JupyterLab 셀 하나에 그대로. 또는  python axis_a_delta_v13.py                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 0. 자격증명 · 실행 경로   ─ 여기만 채우면 된다
# ══════════════════════════════════════════════════════════════════════════════════════════
#
#  DART_API_KEY  ─ 금융감독원 전자공시 OpenDART 인증키 (40자 16진 문자열). 필수.
#     발급: https://opendart.fss.or.kr/  →  [인증키 신청/관리] → [인증키 신청]
#           이메일 인증 → 즉시 발급. 개인 무료. 일 20,000건 호출 한도.
#     확인: https://opendart.fss.or.kr/mng/apiUsageStatus.do  (당일 소진량 — 로그인 필요,
#           API 로는 실시간 잔여량을 조회할 방법이 없다. 이 스크립트는 그래서 스스로 호출
#           수를 세고, DART 가 020(제한초과)을 돌려주면 그 응답을 최종 권위로 취급한다.)
#     ※ 이 실행이 쓰는 DART 엔드포인트는 exctvSttus(임원 현황) 하나뿐이다.
#
DART_API_KEY = ""

#  KRX_ID / KRX_PW ─ KRX 정보데이터시스템 마켓플레이스 계정 (pykrx 인증 경로용). 선택.
#     발급: http://data.krx.co.kr/  →  우측 상단 [로그인] → [회원가입]
#           이메일 인증 후 즉시 사용. 무료.
#     비워도 된다 — 시총 조회는 비인증 pykrx 경로 또는 KRX Open API로도 동작한다.
#     ★ 값을 넣든 안 넣든, pykrx 는 이 값들이 os.environ 에 들어간 '뒤에' import 된다(§4).
#     ★ pykrx 1.2.8 은 import 시점에 실제로 로그인을 시도하고 실패를 흡수하지 않는 결함이
#       있다 — 이 스크립트는 그 실패를 붙잡아 무자격 재시도 후에도 안 되면 폴백 경로로
#       넘어간다. KRX_ID/PW 가 틀렸다고 스크립트 전체가 죽지 않는다.
#
KRX_ID = ""
KRX_PW = ""

#  KRX_OPENAPI_KEY ─ KRX 정보데이터시스템 Open API 인증키. 선택이지만 강력 추천.
#     발급: https://data.krx.co.kr/  →  [Open API] 메뉴 → 키 발급
#     ★ 함정: 키 발급만으로 바로 쓸 수 없다. '주식 일별매매정보'(sto/stk_bydd_trd) 같은
#       엔드포인트별로 별도 이용신청이 필요하고 승인에 하루 정도 걸린다. 이 스크립트는
#       시작 시 1회 프로브를 날려 실제 사용 가능 여부를 판정하고, 안 되면 조용히 pykrx로만
#       진행한다(둘 다 있으면 이 소스가 1순위 — pykrx 의 스크래핑보다 공식 API 라 더 안정적).
#
KRX_OPENAPI_KEY = ""

#  PROJECT_ROOT ─ 로컬 SSD 경로. /content 계열이면 예외를 던지고 즉시 중단한다.
#                 (P0_LOCAL_ROOT_ONLY — WAIVED 허용 없음)
PROJECT_ROOT = "~/quant/phase0"

#  GDRIVE_ROOT ─ 구글드라이브 마운트 경로. 공용/전용 인덱스가 이 아래에 산다.
#     Google Drive for desktop / rclone 등으로 마운트된 경로를 넣는다. 비우면 드라이브
#     동기화 없이 로컬 전용으로 동작한다(측정 자체는 정상 진행).
#     예) "~/Google Drive/My Drive/quant_cache"   또는  "/mnt/gdrive/quant_cache"
#     ★ 이 저장소의 build/00_header.py 가 쓰는 것과 같은 레이아웃이다({root}/_shared/...).
#       같은 GDRIVE_ROOT 를 다른 전략(tcd_v2_*)에도 쓰면 dart_corpcode·security_master
#       캐시가 즉시 상호 재활용된다(§9).
GDRIVE_ROOT = ""

#  예상 신규 API 호출이 5,000건을 넘으면 스크립트가 인벤토리만 출력하고 멈춘다 (P0_CACHE_FIRST).
#  보고를 읽고 진행하기로 했다면 이 값을 True 로 바꾸고 셀을 다시 실행한다.
CONFIRM_LARGE_COLLECTION = False

#  KONEX 포함 여부. 기본 False(=KOSPI+KOSDAQ).
#     근거: '전 상장사 노드 수 2,700 내외' 및 '스냅샷당 필요 ~2,760건' 은 KONEX 제외
#     모수와 일치한다. KONEX 포함시 시총이 극단적으로 작은 종목이 '시총 하위 1,000종목'을
#     통째로 점유해 측정 대상 자체가 바뀐다. 이 선택은 판정표 methodology 에 기록된다.
INCLUDE_KONEX = False

#  동시 요청 워커 수. I/O(네트워크 대기)가 병목이라 스레드로 충분하다 — DART/KRX 호출은
#  전부 HTTP 왕복이 대부분의 시간을 차지하고 GIL 이 병목이 되는 CPU 연산이 아니므로
#  멀티프로세싱은 도움이 안 되고(프로세스 간 예산·서킷브레이커 상태 공유만 복잡해진다),
#  오히려 동시성이 과하면 차단(429)만 늘어난다. 4~8 사이를 권장. 상한 8.
N_WORKERS = 4

# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 1. 계약 — 이 실행이 스스로에게 거는 제약. 위반하면 조용히 넘어가지 않는다.
# ══════════════════════════════════════════════════════════════════════════════════════════
CONTRACTS = {
    "P0_LOCAL_ROOT_ONLY":      "/content 계열 감지 시 예외 발생 후 중단. WAIVED 허용하지 않는다",
    "P0_PIT_STRICT_DELTA":     "as_of 는 실행일이 아니다. 스냅샷별 PIT 폐기 건수를 반드시 출력",
    "P0_EMPTY_UNIVERSE_GUARD": "시총>0 종목 100 미만이면 수집 진입 금지",
    "P0_CACHE_FIRST":          "수집 전 캐시 인벤토리 출력. 예상 신규 호출 5,000건 초과 시 대기",
    "P0_NO_STRATEGY":          "팩터·시그널·수익률·백테스트 연산 금지",
    "P0_GRAPH_FULL_MEASURE_SUB": "그래프는 전 상장사, 측정은 하위 1,000종목",
    "P0_FAIL_LOUD":            "결측은 결측으로. 보간·추정 금지",
    "P0_NO_THRESHOLD_EDIT":    "임계값 frozen. 실행 중 변경 금지",
    "P0_LIVE_ONLY":            "합성 데이터 경로 금지. 전 상장사 노드 수를 로그에 출력",
    "NO_KNOWN_DEAD_CALL":      "pykrx.get_index_portfolio_deposit_file('1028') 금지",
    "P0_DEFENSIVE_PYKRX":      "pykrx import·호출은 어떤 예외에도 프로세스를 죽이지 않는다",
    "P0_MULTI_SOURCE_UNIVERSE": "상장목록은 pykrx 단일 의존이 아니라 DART/FDR/KIND 다중소스 병합",
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
    "edge_born/edge_died 는 '교집합 종목에 한쪽 끝이라도 걸친 엣지'를 센다("
    "'상대 노드가 측정 대상 밖이어도 엣지 유지'). 상대 노드의 상장/폐지가 엣지 생성·소멸로 "
    "보일 수 있어, 양끝이 두 스냅샷 모두에 상장된 경우만 센 보조 수치를 함께 기록한다.",
    "시가총액은 pykrx/KRX Open API 로만 얻는다. FDR·네이버·yfinance 는 과거 특정일의 "
    "시가총액(발행주식수×종가)을 신뢰성 있게 제공하지 않아 이 두 소스가 모두 실패하면 "
    "해당 스냅샷은 UNVERIFIED 로 남는다 — 다른 소스로 시총을 추정하지 않는다(P0_FAIL_LOUD).",
    "상장목록 폴백(FDR+KIND+DART corpCode 병합)에서 상장일을 확정할 수 없었지만 DART "
    "corpCode 에 존재하는 종목은 '상장일 미상으로 포함'되며 그 건수를 로그에 남긴다 — "
    "제외도 추정도 아닌, 있는 그대로의 불확실성 표기다.",
    "요청 범위에는 '시총 하위 1,000종목 대상 스몰캡 버전과의 백테스트 비교'가 포함되어 "
    "있었으나 구현하지 않았다. 이 파일의 측정 대상 자체가 이미 시총 하위 1,000종목이고, "
    "백테스트·수익률 연산은 P0_NO_STRATEGY 로 이 실행 범위 밖에 명시적으로 못박혀 있다 — "
    "축 A 본체가 확인된 뒤 팩터·시그널을 절대 연산하지 않는다는 원 설계와 정면으로 "
    "충돌하기 때문이다. 필요하면 별도 전략 파일(strategies/tcd_v2_*.py 계열)로 만드는 "
    "것이 맞다.",
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
pd = requests = stock = fdr = None
PYKRX_AVAILABLE = False
PYKRX_DIAGNOSTIC = ""
FDR_AVAILABLE = False
KRX_OPENAPI_OK = False
KRX_OPENAPI_MODE = ""

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
#  ▣ 5. 안전한 파일 입출력 — 로컬 ENOSPC 는 즉시 실패
# ══════════════════════════════════════════════════════════════════════════════════════════
def _guard_enospc(e: BaseException, what: str):
    if isinstance(e, OSError) and getattr(e, "errno", None) == errno.ENOSPC:
        raise DiskFull(f"디스크 공간 없음(ENOSPC): {what} — 재시도하지 않는다. "
                       f"공간을 확보한 뒤 다시 실행할 것.") from e


def write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass                                   # 일부 FUSE 드라이브 마운트는 fsync 미지원
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


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def append_jsonl(path: Path, rows) -> None:
    """append-only. 기존 줄은 절대 다시 쓰지 않는다 — 저널의 진실성은 이 함수 하나에 달려 있다."""
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


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue                            # 중단된 append(반쪽 줄)는 건너뛴다
    except OSError:
        pass
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 6. 의존성 → 자격증명 주입 → pykrx 방탄 import
# ══════════════════════════════════════════════════════════════════════════════════════════
#  pykrx 1.2.8 은 `from pykrx import stock` 하는 순간 website/comm/webio.py 모듈 최상단에서
#  build_krx_session() 을 실행한다. 이 함수는 KRX 로그인 엔드포인트에 POST 하고 resp.json()
#  을 try/except 없이 호출한다 — KRX 가 로그인 실패·차단·점검 페이지(HTML)를 돌려주면
#  JSONDecodeError 가 *import 시점에* 그대로 터진다. 즉 "pykrx 를 import 만 해도 죽을 수
#  있다"는 게 실제 동작이다. 이걸 코드로 방어하는 유일한 방법은 import 자체를 넓은
#  except 로 감싸는 것뿐이다 — 어떤 특정 예외 타입을 예상해서 좁혀 잡으면 다음 pykrx
#  버전에서 예외 종류가 바뀌는 순간 다시 뚫린다.
# ══════════════════════════════════════════════════════════════════════════════════════════
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


def _try_import_pykrx(with_creds: bool):
    """단일 시도. 성공하면 (stock모듈, ''), 실패하면 (None, 진단문자열). 절대 예외를 던지지 않는다."""
    _purge_pykrx_modules()
    if with_creds and KRX_ID and KRX_PW:
        os.environ["KRX_ID"] = KRX_ID.strip()
        os.environ["KRX_PW"] = KRX_PW.strip()
    else:
        os.environ.pop("KRX_ID", None)
        os.environ.pop("KRX_PW", None)
    try:
        from pykrx import stock as _stock            # ← 여기서 실제 로그인 네트워크 I/O 가 돈다
        return _stock, ""
    except BaseException as e:                         # noqa: BLE001 — 의도적으로 전부 잡는다
        _purge_pykrx_modules()
        return None, f"{type(e).__name__}: {e}"


PYKRX_IMPORT_ORDER = {"purged_stale_modules": 0, "env_injected_before_import": False,
                      "attempts": []}


def _import_pykrx_after_env():
    """KRX 자격증명을 os.environ 에 넣은 '뒤에' pykrx 를 import 한다 — 실패해도 죽지 않는다.

    1차: 자격증명 포함 시도. 실패하면(위 이유로 흔히 실패한다) 자격증명을 비우고 2차 시도
    — 비인증 경로는 로그인 자체를 안 하므로 자격증명이 틀렸어도 이쪽은 보통 산다.
    둘 다 실패하면 PYKRX_AVAILABLE=False 로 남기고 폴백 소스(KRX Open API·FDR·KIND)로
    계속 진행한다. pykrx 없이 실행 자체가 죽는 일은 없다.
    """
    global PYKRX_AVAILABLE, PYKRX_DIAGNOSTIC
    stock1, err1 = _try_import_pykrx(with_creds=True)
    PYKRX_IMPORT_ORDER["attempts"].append({"with_creds": True, "ok": stock1 is not None, "err": err1})
    if stock1 is not None:
        PYKRX_AVAILABLE = True
        return stock1
    if KRX_ID and KRX_PW:
        WARN(f"pykrx import 실패(자격증명 포함): {err1}")
        WARN("  pykrx 1.2.8 은 import 시점에 KRX 로그인을 하고 실패를 흡수하지 않는 알려진 "
             "결함이 있다(이 실패는 스크립트 결함이 아니라 pykrx 자체의 결함이다). "
             "무자격 상태로 재시도한다.")
    stock2, err2 = _try_import_pykrx(with_creds=False)
    PYKRX_IMPORT_ORDER["attempts"].append({"with_creds": False, "ok": stock2 is not None, "err": err2})
    if stock2 is not None:
        PYKRX_AVAILABLE = True
        if KRX_ID and KRX_PW:
            WARN("  무자격 재시도로 pykrx 는 로드됐다. 다만 KRX 로그인 자체는 실패했으므로 "
                 "인증이 필요한 pykrx 조회는 여전히 못 쓴다 — 시총·종목목록은 비인증 경로로도 된다.")
        return stock2
    PYKRX_AVAILABLE = False
    PYKRX_DIAGNOSTIC = f"자격증명포함: {err1} / 무자격: {err2}"
    ERR(f"pykrx 를 어떤 방식으로도 로드하지 못했다: {PYKRX_DIAGNOSTIC}")
    ERR("  P0_DEFENSIVE_PYKRX: 이 실행은 여기서 죽지 않는다. KRX Open API 와 FDR/KIND "
        "폴백만으로 계속된다. 그 경로마저 전부 막히면 해당 스냅샷만 UNVERIFIED 로 남는다.")
    return None


def pykrx_call(fn_name: str, *a, **kw):
    """모든 pykrx 호출의 유일한 통로. 절대 예외를 밖으로 내보내지 않는다(P0_DEFENSIVE_PYKRX).

    pykrx 는 import 이후에도 세션 만료 시 재로그인을 시도하며 같은 종류의 무방비 JSON 파싱을
    또 탄다 — import 가 살아남았다고 이후 호출이 전부 안전하다는 보장이 없다. 그래서 개별
    호출도 전부 이 래퍼를 거친다.
    """
    if not PYKRX_AVAILABLE or stock is None:
        return None
    fn = getattr(stock, fn_name, None)
    if fn is None:
        return None
    try:
        return fn(*a, **kw)
    except BaseException as e:                          # noqa: BLE001
        WARN(f"    pykrx.{fn_name} 호출 실패({type(e).__name__}: {e}) — 폴백 소스로 넘어간다")
        return None


_DEAD_CALL_NAME = "get_index_portfolio_deposit_file"


def _try_import_fdr():
    """FinanceDataReader — 상장목록 폴백용. 있으면 쓰고 없으면 조용히 생략한다(선택 의존성)."""
    global FDR_AVAILABLE
    try:
        import FinanceDataReader as _fdr
        FDR_AVAILABLE = True
        return _fdr
    except Exception:                                    # noqa: BLE001
        FDR_AVAILABLE = False
        return None


def _bootstrap():
    """경로 검사 → 디렉터리 → 로그 → 의존성 → 자격증명 주입 → pykrx/FDR import → 전처리 요약.

    pykrx·FDR 은 둘 다 실패해도 여기서 죽지 않는다. 죽는 건 PROJECT_ROOT 검사와
    DART_API_KEY 부재뿐이다 — 이 둘은 이 실행의 존재 이유(로컬 캐시, LIVE 데이터)와 직결된다.
    """
    global ROOT, DIR_CACHE_RAW, DIR_CACHE_META, DIR_STATE, DIR_REPORTS
    global pd, requests, stock, fdr, _LOG_FH

    ROOT = resolve_project_root(PROJECT_ROOT)          # P0_LOCAL_ROOT_ONLY — 여기서 터진다
    DIR_CACHE_RAW = ROOT / "cache" / "raw" / "dart_exctv"
    DIR_CACHE_META = ROOT / "cache" / "meta"
    DIR_STATE = ROOT / "cache" / "state"
    DIR_REPORTS = ROOT / "reports"
    for d in (DIR_CACHE_RAW, DIR_CACHE_META, DIR_STATE, DIR_REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    _LOG_FH = open(DIR_REPORTS / "run_log.txt", "a", encoding="utf-8")

    _ensure_packages(["pandas", "requests", "pykrx", "FinanceDataReader"])
    import pandas as _pd
    import requests as _rq
    pd, requests = _pd, _rq

    stock = _import_pykrx_after_env()                  # ← 자격증명 주입 '이후'의 유일한 지점. 안 죽는다.
    fdr = _try_import_fdr()

    if stock is not None and hasattr(stock, _DEAD_CALL_NAME):
        # NO_KNOWN_DEAD_CALL: '쓰지 않는다'로 끝내지 않고, 호출되면 터지게 만든다.
        def _dead_call(*a, **k):
            raise ContractViolation(
                f"NO_KNOWN_DEAD_CALL 위반: {_DEAD_CALL_NAME}{a!r} 는 사용이 금지된 호출이다.")
        setattr(stock, _DEAD_CALL_NAME, _dead_call)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 7. KRX Open API — 시가총액 1순위 소스 (pykrx 가 죽어도 살아 있다)
# ══════════════════════════════════════════════════════════════════════════════════════════
KRX_OPENAPI_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"


def probe_krx_openapi() -> bool:
    """실제 호출로 사용 가능 여부를 1회 확인한다. 엔드포인트별 이용신청이 안 돼 있으면
    키가 유효해도 거부된다 — 그래서 '키가 있다'와 '쓸 수 있다'를 코드로 직접 구분해야 한다."""
    global KRX_OPENAPI_OK, KRX_OPENAPI_MODE
    if not str(KRX_OPENAPI_KEY or "").strip() or requests is None:
        return False
    d = _dt.date.today() - _dt.timedelta(days=7)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    for mode in ("query", "header"):
        try:
            if mode == "query":
                r = requests.get(KRX_OPENAPI_URL, timeout=15,
                                 params={"AUTH_KEY": KRX_OPENAPI_KEY, "basDd": d.strftime("%Y%m%d")})
            else:
                r = requests.get(KRX_OPENAPI_URL, timeout=15,
                                 params={"basDd": d.strftime("%Y%m%d")},
                                 headers={"AUTH_KEY": KRX_OPENAPI_KEY})
            js = r.json()
        except Exception:                                # noqa: BLE001
            continue
        if isinstance(js, dict) and (js.get("OutBlock_1") or js.get("output")):
            KRX_OPENAPI_OK, KRX_OPENAPI_MODE = True, mode
            return True
    KRX_OPENAPI_OK = False
    return False


def _mcap_frame_openapi(date_c: str):
    """KRX Open API 벌크 조회(그 날짜 전종목 1콜). 실패하면 None — 예외를 던지지 않는다."""
    if not KRX_OPENAPI_OK or requests is None:
        return None
    kw = ({"params": {"AUTH_KEY": KRX_OPENAPI_KEY, "basDd": date_c}} if KRX_OPENAPI_MODE == "query"
          else {"params": {"basDd": date_c}, "headers": {"AUTH_KEY": KRX_OPENAPI_KEY}})
    try:
        r = requests.get(KRX_OPENAPI_URL, timeout=20, **kw)
        js = r.json()
    except Exception:                                    # noqa: BLE001
        return None
    rows = js.get("OutBlock_1") or js.get("output") or []
    if not rows:
        return None
    df = pd.DataFrame(rows)
    code_c = next((c for c in ("ISU_SRT_CD", "ISU_CD", "srtnCd") if c in df.columns), None)
    cap_c = next((c for c in ("MKTCAP", "mktCap") if c in df.columns), None)
    if not code_c or not cap_c:
        return None
    out = pd.DataFrame({"시가총액": pd.to_numeric(
        df[cap_c].astype(str).str.replace(",", "", regex=False), errors="coerce")})
    out.index = [to_code6(x) for x in df[code_c]]
    return out if len(out) and (out["시가총액"] > 0).sum() > 0 else None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 8. 적응형 지연 — 성공 스트릭엔 가속, 실패엔 즉시 감속 (차단 회피 최우선)
# ══════════════════════════════════════════════════════════════════════════════════════════
class AdaptiveDelay:
    def __init__(self, lo: float = 0.12, hi: float = 1.2, start: float = 0.4,
                 speedup_every: int = 25, speedup_factor: float = 0.92,
                 backoff_factor: float = 1.8):
        self.lo, self.hi = lo, hi
        self.cur = start
        self.streak = 0
        self.speedup_every = speedup_every
        self.speedup_factor = speedup_factor
        self.backoff_factor = backoff_factor
        self.lk = threading.Lock()

    def wait(self) -> None:
        with self.lk:
            d = self.cur
        time.sleep(max(0.0, d * random.uniform(0.85, 1.15)))

    def on_success(self) -> None:
        with self.lk:
            self.streak += 1
            if self.streak >= self.speedup_every:
                self.cur = max(self.lo, self.cur * self.speedup_factor)
                self.streak = 0

    def on_failure(self) -> None:
        with self.lk:
            self.streak = 0
            self.cur = min(self.hi, self.cur * self.backoff_factor)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 9. 정규화 헬퍼
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 10. 공용/전용 인덱스 — 로컬+드라이브 이중탐색, 다른 전략과 캐시 상호 재활용
# ══════════════════════════════════════════════════════════════════════════════════════════
#  레이아웃은 이 저장소의 build/00_header.py 가 쓰는 것과 동일하다:
#    {GDRIVE_ROOT}/_shared/table/{dart_corpcode, security_master}.csv   ← 공용, 다른 전략과 공유
#    {GDRIVE_ROOT}/_shared/blob/dart/exctv/{corp}/{year}_{reprt}.json   ← 공용, 임원 원본
#    {GDRIVE_ROOT}/_shared/index/journal.jsonl                          ← append-only 저널
#    {GDRIVE_ROOT}/phase0_axis_a_delta/                                 ← 전용(이 스크립트 고유)
#  로컬은 항상 1차 저장소다. 드라이브는 "복원 시 로컬에 없으면만 당겨오고, 신규 수집분은
#  스냅샷 완료마다 즉시 올린다" — 실행 종료를 기다리는 일괄 백업이 아니다.
# ══════════════════════════════════════════════════════════════════════════════════════════
GDRIVE_SHARED_NS = "_shared"
GDRIVE_PRIVATE_NS = "phase0_axis_a_delta"


def _drive_root():
    if not str(GDRIVE_ROOT or "").strip():
        return None
    return Path(os.path.expanduser(GDRIVE_ROOT)).resolve()


def drive_shared(*parts) -> "Path | None":
    d = _drive_root()
    if d is None:
        return None
    p = d / GDRIVE_SHARED_NS
    for part in parts:
        p = p / part
    return p


def _safe_copy(src: Path, dst: Path) -> bool:
    """로컬 목적지가 이미 있으면 손대지 않는다. 원격(드라이브) ENOSPC 는 경고만 하고 계속한다."""
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


# ── 임원 원본 blob: 이중탐색 ────────────────────────────────────────────────────────────────
def cache_path(corp_code: str, year: str, reprt: str) -> Path:
    return DIR_CACHE_RAW / str(corp_code) / f"{year}_{reprt}.json"


def _drive_blob_path(corp_code: str, year: str, reprt: str):
    return drive_shared("blob", "dart", "exctv", str(corp_code), f"{year}_{reprt}.json")


def restore_officer_blobs_from_drive(keys) -> int:
    """keys=[(corp_code,year,reprt),...] 중 로컬에 없는 것만 드라이브에서 당겨온다(skip-if-exists).
    tar.gz 통째 복원과 달리, 필요한 키만 골라 찾으므로 캐시가 커도 빠르다."""
    d = _drive_root()
    if d is None:
        return 0
    n = 0
    for cp, yy, rc in keys:
        local = cache_path(cp, yy, rc)
        if local.exists():
            continue
        remote = _drive_blob_path(cp, yy, rc)
        if remote is None or not remote.exists():
            continue
        try:
            if _safe_copy(remote, local):
                n += 1
        except DiskFull:
            raise
    return n


def sync_officer_blobs_to_drive(keys) -> dict:
    """이미 로컬에 있는(방금 받았든 예전부터 있었든) 파일을 드라이브에 증분 동기화한다.
    스냅샷 수집이 끝날 때마다 호출한다 — 실행이 중간에 죽어도 그때까지 받은 건 안전하다."""
    out = {"attempted": False, "synced": 0, "already_there": 0, "local_missing": 0, "error": ""}
    d = _drive_root()
    if d is None:
        return out
    out["attempted"] = True
    for cp, yy, rc in keys:
        local = cache_path(cp, yy, rc)
        if not local.exists():
            out["local_missing"] += 1
            continue
        remote = _drive_blob_path(cp, yy, rc)
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


# ── 공용 테이블(dart_corpcode / security_master): 이중탐색, CSV(항상)+parquet(있으면 상호운용) ─
def restore_shared_table(name: str, local_path: Path) -> bool:
    if local_path.exists():
        return False
    for ext, reader in ((".csv", None), (".parquet", "parquet")):
        remote = drive_shared("table", f"{name}{ext}")
        if remote is None or not remote.exists():
            continue
        if reader is None:
            return _safe_copy(remote, local_path)
        # 다른 전략이 parquet 로 저장했을 수 있다(build/04_vault.py 관례) — 있으면 읽어서
        # 우리 형식(csv)으로 옮겨 담는다. pyarrow 가 없으면 조용히 건너뛴다(선택적 상호운용).
        try:
            df = pd.read_parquet(remote)
        except Exception:                                    # noqa: BLE001
            continue
        try:
            write_text(local_path, df.to_csv(index=False))
            OK(f"    공용 인덱스에서 {name} 재사용(parquet, 다른 전략이 수집한 데이터) "
               f"{len(df):,}행")
            return True
        except DiskFull:
            raise
        except OSError:
            continue
    return False


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


# ── 저널(append-only, 공용) ─────────────────────────────────────────────────────────────────
def journal_path_local() -> Path:
    return DIR_CACHE_META / "journal_officer.jsonl"


def journal_append(rows) -> None:
    append_jsonl(journal_path_local(), rows)
    rj = drive_shared("index", "journal.jsonl")
    if rj is not None:
        try:
            append_jsonl(rj, rows)
        except DiskFull:
            raise
        except OSError as e:
            WARN(f"    드라이브 저널 append 실패(로컬 저널은 정상): {e}")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 11. corpCode — 파싱 결과 캐시 + 공용 인덱스 상호운용
# ══════════════════════════════════════════════════════════════════════════════════════════
_CORP_LIST_RE = re.compile(rb"<list>(.*?)</list>", re.S)


def _corpcode_xml() -> Path:
    return DIR_CACHE_META / "corpCode.zip"


def _corpcode_parsed() -> Path:
    return DIR_CACHE_META / "dart_corpcode.csv"


def _dart_status_msg(code: str) -> str:
    return {
        "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
        "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
        "020": "요청 제한 초과(일 20,000건)", "021": "조회 가능한 회사 개수 초과",
        "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검",
        "900": "정의되지 않은 오류", "901": "사용자 계정의 개인정보보호 요청",
    }.get(str(code), "알 수 없음")


def load_corpcode() -> "pd.DataFrame":
    """종목코드를 가진 법인만 남긴 (corp_code, corp_name, code) 표.

    탐색 순서: 로컬 파싱캐시 → 공용 드라이브 인덱스(다른 전략이 이미 받아둔 것) → 신규 수신.
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
#  ▣ 12. 다중소스 상장 유니버스 폴백 (P0_MULTI_SOURCE_UNIVERSE)
# ══════════════════════════════════════════════════════════════════════════════════════════
#  1순위는 언제나 pykrx.get_market_ticker_list(그 날짜) — 정확한 시점 스냅샷이다.
#  pykrx 가 죽었을 때만(§6) 이 다중소스 병합으로 대체한다: FDR 상장/폐지 목록(로그인 불필요,
#  GitHub 캐시 우선) + KIND 상장법인목록 + DART corpCode. 상장일 ≤ 스냅샷일 < 폐지일 로
#  그 시점에 존재했던 종목만 남긴다 — 생존자편향 없는 point-in-time 필터다.
#  시가총액은 이 소스들로 얻을 수 없다(과거 특정일의 시총을 신뢰성 있게 주는 곳이 없다) —
#  그래서 이건 '어느 종목이 존재했는가'의 폴백일 뿐, 시총 폴백은 §7 의 KRX Open API 뿐이다.
# ══════════════════════════════════════════════════════════════════════════════════════════
_LISTING_COLS = ["code", "listing_date", "delisting_date", "market"]
FDR_GITHUB_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                    "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 14):
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        url = FDR_GITHUB_CACHE.format(kind=kind, date=d.isoformat())
        try:
            r = requests.get(url, timeout=20)
        except Exception:                                       # noqa: BLE001
            continue
        if r.status_code != 200 or len(r.content) < 200:
            continue
        try:
            df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
        except Exception:                                        # noqa: BLE001
            continue
        if len(df.columns) and str(df.columns[0]).strip().lower() in (
                "", "unnamed: 0", "unnamed:0", "index"):
            df = df.drop(columns=[df.columns[0]])
        if len(df):
            return df
    return None


def _lower_map(d) -> dict:
    return {str(c).strip().lower(): c for c in d.columns}


def fetch_fdr_listing():
    """로그인 불필요 경로 1순위(FDR 이 실제 읽는 GitHub 캐시). 실패하면 fdr.StockListing 폴백."""
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
        if code_c:
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "market": (d[col["market"]].astype(str) if "market" in col
                          else d[col["marketid"]].astype(str) if "marketid" in col else ""),
                "listing_date": pd.to_datetime(d[col["listingdate"]], errors="coerce")
                                if "listingdate" in col else pd.NaT,
            })
            t["delisting_date"] = pd.NaT
            return t[t["code"] != ""].drop_duplicates("code").reindex(columns=_LISTING_COLS)
    if fdr is None:
        return pd.DataFrame(columns=_LISTING_COLS)
    try:
        d = fdr.StockListing("KRX")
    except Exception:                                            # noqa: BLE001
        return pd.DataFrame(columns=_LISTING_COLS)
    if d is None or not len(d):
        return pd.DataFrame(columns=_LISTING_COLS)
    col = _lower_map(d)
    code_c = col.get("code") or col.get("symbol")
    if not code_c:
        return pd.DataFrame(columns=_LISTING_COLS)
    t = pd.DataFrame({"code": d[code_c].map(to_code6),
                      "market": d[col["market"]].astype(str) if "market" in col else "",
                      "listing_date": pd.to_datetime(d[col["listingdate"]], errors="coerce")
                                      if "listingdate" in col else pd.NaT})
    t["delisting_date"] = pd.NaT
    return t[t["code"] != ""].drop_duplicates("code").reindex(columns=_LISTING_COLS)


def fetch_fdr_delisting():
    """생존자편향 제거 입력. KRX Open API 에는 상장폐지 엔드포인트가 아예 없어 이 경로가
    사실상 유일한 공개 소스다."""
    d = _fdr_cache_csv("listing/delisting")
    if d is None or not len(d):
        if fdr is None:
            return pd.DataFrame(columns=["code", "delisting_date"])
        try:
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:                                        # noqa: BLE001
            d = None
        if d is None or not len(d):
            return pd.DataFrame(columns=["code", "delisting_date"])
    col = _lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        return pd.DataFrame(columns=["code", "delisting_date"])
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date")
                if k in col), None)
    t = pd.DataFrame({"code": d[code_c].astype(str).map(to_code6),
                      "delisting_date": pd.to_datetime(d[dl_c], errors="coerce") if dl_c else pd.NaT})
    t = t[t["code"] != ""]
    return t.sort_values("delisting_date").drop_duplicates("code", keep="last")


def fetch_kind_listing():
    """KIND 상장법인목록 — 상장일 보강. 종목코드가 정수로 와서 앞자리 0 이 날아가므로
    to_code6 로 복구한다."""
    urls = ["https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
            "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"]
    for u in urls:
        try:
            r = requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        except Exception:                                        # noqa: BLE001
            continue
        if r.status_code != 200 or len(r.content) < 500:
            continue
        for enc in ("euc-kr", "cp949", "utf-8"):
            try:
                tabs = pd.read_html(io.BytesIO(r.content), encoding=enc)
            except Exception:                                     # noqa: BLE001
                continue
            if not tabs:
                continue
            d = max(tabs, key=len)
            col = {str(c).strip(): c for c in d.columns}
            code_c = col.get("종목코드")
            if not code_c:
                continue
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "listing_date": pd.to_datetime(d[col["상장일"]], errors="coerce")
                                if "상장일" in col else pd.NaT,
                "market": "",
            })
            t["delisting_date"] = pd.NaT
            return t[t["code"] != ""].drop_duplicates("code").reindex(columns=_LISTING_COLS)
    return pd.DataFrame(columns=_LISTING_COLS)


def build_security_master() -> "pd.DataFrame":
    """FDR+KIND+DART corpCode 병합. 캐시(로컬→드라이브 공용 인덱스)를 먼저 본다 — 이미
    다른 전략(build/10_ingest_universe.py 계열)이 훨씬 풍부한 버전을 만들어 뒀을 수 있다."""
    local = DIR_CACHE_META / "security_master.csv"
    if restore_shared_table("security_master", local):
        OK("  드라이브 공용 인덱스에서 security_master 재사용 (다른 전략이 이미 수집한 데이터)")
    if local.exists():
        age_days = (time.time() - local.stat().st_mtime) / 86400.0
        if age_days <= 7:
            try:
                df = pd.read_csv(local, dtype={"code": str})
                for c in ("listing_date", "delisting_date"):
                    df[c] = pd.to_datetime(df[c], errors="coerce")
                if len(df):
                    OK(f"  security_master 로컬 캐시 히트 {len(df):,}건 "
                       f"({age_days:.1f}일 전 수집, 7일 이내라 재사용)")
                    return df
            except Exception:                                     # noqa: BLE001
                pass

    LOG("  security_master 신규 수집 (FDR + KIND + DART corpCode 병합) — pykrx 폴백 전용, "
        "정상 경로에서는 호출되지 않는다")
    parts = []
    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
    dead = fetch_fdr_delisting()
    if len(dead):
        d2 = dead.copy()
        d2["listing_date"] = pd.NaT
        d2["market"] = ""
        parts.append(d2.reindex(columns=_LISTING_COLS))

    cc = load_corpcode()
    corp_only_codes = set()
    if len(cc):
        known = set(pd.concat(parts, ignore_index=True)["code"]) if parts else set()
        corp_only_codes = set(cc["code"]) - known - {""}
        if corp_only_codes:
            parts.append(pd.DataFrame({"code": sorted(corp_only_codes), "listing_date": pd.NaT,
                                       "delisting_date": pd.NaT, "market": ""}))

    if not parts:
        WARN("  security_master 병합 소스가 하나도 없다 — 상장목록 폴백을 쓸 수 없다. "
             "네트워크에서 raw.githubusercontent.com / kind.krx.co.kr 접근을 확인할 것.")
        return pd.DataFrame(columns=_LISTING_COLS)

    m = pd.concat(parts, ignore_index=True)
    m = m[m["code"] != ""]
    agg = m.groupby("code", as_index=False).agg(
        listing_date=("listing_date", "min"), delisting_date=("delisting_date", "max"),
        market=("market", lambda s: next((x for x in s if str(x).strip()), "")))

    n_nolist = int(agg["listing_date"].isna().sum())
    LOG(f"  security_master 병합 완료 — 고유종목 {len(agg):,}건 / "
        f"상장일 보유 {len(agg) - n_nolist:,}건 / 상장일 미상(DART corpCode 존재로만 포함) "
        f"{len(corp_only_codes):,}건")
    if n_nolist > len(agg) * 0.5:
        WARN(f"  상장일 미상 비율이 {100 * n_nolist / max(len(agg), 1):.0f}% 로 높다 — "
             f"이 폴백으로 만든 유니버스는 점검 없이 신뢰하지 말 것.")
    try:
        agg.to_csv(local, index=False, encoding="utf-8")
        if publish_shared_table("security_master", local):
            LOG("  공용 인덱스에 security_master 게시 — 다른 전략에서도 재사용 가능")
    except DiskFull:
        raise
    except OSError:
        pass
    return agg


def point_in_time_listed(master: "pd.DataFrame", snap_date_iso: str) -> set:
    """listing_date ≤ snap_date < delisting_date (또는 미상) 인 종목 집합."""
    if master is None or not len(master):
        return set()
    snap = pd.Timestamp(snap_date_iso)
    ok_listed = master["listing_date"].isna() | (master["listing_date"] <= snap)
    ok_alive = master["delisting_date"].isna() | (master["delisting_date"] > snap)
    return set(master.loc[ok_listed & ok_alive, "code"])


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 13. 스냅샷 명세 — 관측시점 정렬(A) 채택 (FROZEN, 변경 금지)
# ══════════════════════════════════════════════════════════════════════════════════════════
ALIGNMENT = "A_OBSERVATION_TIME"
REPRT_NAME = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서",
              "11014": "3분기보고서"}
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

# ── 호출예산: '실 필요량 대비 사전 계산'으로 판단한다 ────────────────────────────────────────
#   4개 스냅샷 콜드 수집의 실 필요량은 ~11,078건(2760+2765+2790+2763). 예전 판은 여기에
#   '중도정지 12,000'이라는 별도의 낮은 임계를 더 얹어서, 재시도가 조금만 섞여도(정상적인
#   운영 잡음이다) 실 필요량보다 낮은 그 임계에 먼저 걸려 정상적인 콜드런조차 중도에 멎을
#   수 있었다. 그 임의 임계는 없앴다. 이제 유일한 하드 한도는 DART 실제 일일한도 아래
#   안전마진을 둔 CALL_BUDGET_DAILY 뿐이고, 실시간 소진의 최종 권위는 DART 가 돌려주는
#   status=020 자체다(자체 카운터가 낙관적이어도 이 신호가 이긴다).
CALL_BUDGET_DAILY = 19500
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
                f"P0_PIT_STRICT_DELTA 위반: {sid} 의 as_of 가 실행일({today})과 같다.")


def _sha256_thresholds() -> str:
    return hashlib.sha256(
        json.dumps(GATE_THRESHOLDS, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 14. 유니버스 — 거래일 스냅 + 빈 유니버스 가드 + 시총/티커 다중소스 폴백
# ══════════════════════════════════════════════════════════════════════════════════════════
_MCAP_CACHE: dict = {}          # date_c -> (df|None, source) — 실행 내 메모이제이션, 재조회 제거


def _mcap_frame_pykrx(date_c: str):
    for fn, kw in (("get_market_cap_by_ticker", {"market": "ALL", "alternative": False}),
                   ("get_market_cap_by_ticker", {"market": "ALL"}),
                   ("get_market_cap_by_ticker", {}),
                   ("get_market_cap", {"market": "ALL"})):
        df = pykrx_call(fn, date_c, **kw)
        if isinstance(df, pd.DataFrame) and len(df) and "시가총액" in df.columns:
            return df
    return None


def _mcap_frame(date_c: str):
    """시총 조회 1콜 = 그 날 전종목. KRX Open API(공식) 1순위, pykrx(스크래핑) 2순위.
    같은 날짜는 실행 중 한 번만 실제로 조회한다(메모이제이션) — v1.2/재시도로 인한
    중복 시총조회를 원천 제거한다."""
    if date_c in _MCAP_CACHE:
        return _MCAP_CACHE[date_c][0]
    df, src = None, ""
    if KRX_OPENAPI_OK:
        df = _mcap_frame_openapi(date_c)
        if df is not None:
            src = "krx_openapi"
    if df is None and PYKRX_AVAILABLE:
        df = _mcap_frame_pykrx(date_c)
        if df is not None:
            src = "pykrx"
    _MCAP_CACHE[date_c] = (df, src)
    return df


def _mcap_source(date_c: str) -> str:
    return _MCAP_CACHE.get(date_c, (None, ""))[1]


def resolve_trading_day(nominal_iso: str):
    """분기말이 휴장일이면 직전 거래일로 이동. '시총>0 종목수'로 거래일을 실측한다."""
    d0 = _dt.date.fromisoformat(nominal_iso)
    trail = []
    for back in range(TRADING_DAY_LOOKBACK + 1):
        d = d0 - _dt.timedelta(days=back)
        date_c = compact(d.isoformat())
        df = _mcap_frame(date_c)
        if df is None:
            trail.append((d.isoformat(), "조회실패(전 소스)"))
            continue
        n_pos = int((pd.to_numeric(df["시가총액"], errors="coerce").fillna(0) > 0).sum())
        trail.append((d.isoformat(), f"행 {len(df):,} / 시총>0 {n_pos:,} [{_mcap_source(date_c)}]"))
        if n_pos >= EMPTY_UNIVERSE_MIN:
            return d.isoformat(), df, trail
    return None, None, trail


_SECURITY_MASTER_CACHE = None


def _security_master_lazy():
    global _SECURITY_MASTER_CACHE
    if _SECURITY_MASTER_CACHE is None:
        _SECURITY_MASTER_CACHE = build_security_master()
    return _SECURITY_MASTER_CACHE


def _resolve_listed_set(date_c: str, snap_date_iso: str):
    """티커 목록 1순위=pykrx(그 날짜 정확), 실패 시 다중소스 상장/폐지 병합의 point-in-time 필터.
    반환: (listed_by_market: {market: set(code)}, source: str)"""
    by_mkt, any_ok = {}, False
    for mk in ("KOSPI", "KOSDAQ", "KONEX"):
        ts = pykrx_call("get_market_ticker_list", date_c, market=mk)
        if ts:
            by_mkt[mk] = {to_code6(t) for t in ts}
            any_ok = True
    if any_ok:
        return by_mkt, "pykrx"

    WARN("    pykrx 티커목록 사용 불가 — 다중소스 상장유니버스 폴백(FDR+KIND+DART)으로 대체")
    master = _security_master_lazy()
    codes = point_in_time_listed(master, snap_date_iso)
    if not codes:
        return {}, "none"
    # 폴백에는 시장 라벨이 부실하므로(KIND/FDR 캐시가 시장을 늘 주지 않는다) 전부 하나의
    # 가상 마켓으로 묶는다 — INCLUDE_KONEX 필터는 이 경로에서는 걸 수 없다는 뜻이고,
    # 그 사실을 로그로 명시한다.
    LOG(f"    폴백 유니버스 {len(codes):,}종목 — 시장 라벨(KOSPI/KOSDAQ/KONEX) 구분 불가 "
        f"(KONEX 필터 미적용, methodology 에 기록됨)")
    return {"_FALLBACK_ALL": codes}, "fallback_multi_source"


def build_universe(sid: str, nominal_iso: str):
    """반환: dict(효과일자, 시총표, 측정대상 코드집합, 전상장 코드집합, 상태, 소스 진단)."""
    eff, df, trail = resolve_trading_day(nominal_iso)
    for day, note in trail:
        mark = "←사용" if day == eff else ""
        LOG(f"    거래일 탐색 {day}: {note} {mark}")
    if eff is None:
        WARN(f"  {sid} 빈 유니버스 — {nominal_iso} 부터 {TRADING_DAY_LOOKBACK}일 역행했으나 "
             f"시총>0 종목이 {EMPTY_UNIVERSE_MIN} 미만(KRX Open API·pykrx 모두 실패 포함). "
             f"P0_EMPTY_UNIVERSE_GUARD 발동: 임원현황 수집에 진입하지 않는다.")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": "", "status": "UNVERIFIED",
                "status_reason": "EMPTY_UNIVERSE", "listed": set(), "measure": set(),
                "mcap": None, "n_listed_all": 0, "n_konex": 0, "mcap_source": "", "universe_source": ""}
    if eff != nominal_iso:
        WARN(f"  {sid} 휴장일 스냅: {nominal_iso} → {eff} (직전 거래일)")

    date_c = compact(eff)
    mcap_src = _mcap_source(date_c)
    cap = pd.to_numeric(df["시가총액"], errors="coerce").fillna(0)
    df = df.assign(_cap=cap.values)
    df.index = [to_code6(i) for i in df.index]
    df = df[~df.index.duplicated(keep="first")]     # .loc 이 행을 불려 내는 사고 방지
    all_pos = df[df["_cap"] > 0]

    by_mkt, universe_src = _resolve_listed_set(date_c, eff)
    konex = by_mkt.get("KONEX", set())
    if "_FALLBACK_ALL" in by_mkt:
        sel = by_mkt["_FALLBACK_ALL"]
    else:
        keep_markets = ["KOSPI", "KOSDAQ"] + (["KONEX"] if INCLUDE_KONEX else [])
        sel = set().union(*(by_mkt.get(mk, set()) for mk in keep_markets)) if by_mkt else set()

    listed = set(all_pos.index) & sel if sel else set(all_pos.index)
    if not sel:
        WARN(f"  {sid} 시장/유니버스 라벨 전부 결측 — 시총>0 전체를 유니버스로 사용")
    if len(listed) < EMPTY_UNIVERSE_MIN:
        WARN(f"  {sid} 시장 필터 후 {len(listed)}종목 — P0_EMPTY_UNIVERSE_GUARD 발동")
        return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "UNVERIFIED",
                "status_reason": "EMPTY_UNIVERSE_AFTER_MARKET_FILTER", "listed": set(),
                "measure": set(), "mcap": None, "n_listed_all": len(all_pos), "n_konex": len(konex),
                "mcap_source": mcap_src, "universe_source": universe_src}

    sub = all_pos.loc[sorted(listed)].sort_values("_cap", ascending=True)
    measure = set(sub.index[:MEASURE_N])
    LOG(f"    전 상장사(시총>0, {'KONEX 포함' if INCLUDE_KONEX else 'KONEX 제외'}) "
        f"{len(listed):,}종목  |  ALL 기준 {len(all_pos):,} (KONEX {len(konex):,})  "
        f"|  시총소스={mcap_src}  유니버스소스={universe_src}")
    LOG(f"    측정대상 = 시총 하위 {len(measure):,}종목  "
        f"(최소 {sub['_cap'].iloc[0] / 1e8:,.0f}억 ~ 최대 {sub['_cap'].iloc[len(measure) - 1] / 1e8:,.0f}억)")
    return {"snapshot": sid, "date_nominal": nominal_iso, "date": eff, "status": "OK",
            "status_reason": "", "listed": listed, "measure": measure, "mcap": sub,
            "n_listed_all": len(all_pos), "n_konex": len(konex),
            "mcap_source": mcap_src, "universe_source": universe_src}


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 15. DART 임원현황 수집 — 워커 스레드풀 / 적응형지연 / 지수백오프 / 서킷브레이커 / 예산
# ══════════════════════════════════════════════════════════════════════════════════════════
EXCTV_URL = "https://opendart.fss.or.kr/api/exctvSttus.json"
_BUDGET_FILE = f"call_budget_{RUN_STARTED:%Y%m%d}.json"      # 경로는 _bootstrap 이후에 만든다


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


_IGNORED_CACHE_FIELDS = ("as_of", "asof", "as_of_date", "pit_as_of", "filtered", "pit_filtered")


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
        self.delay = AdaptiveDelay()
        self._journal_buf = []
        self._journal_lk = threading.Lock()

    # ── 예산: 유일한 하드 한도는 DART 실 일일한도(안전마진 포함) ────────────────────────
    def _reserve(self) -> bool:
        with self.lk:
            if self.halt:
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
        self.delay.on_success()

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
        self.delay.on_failure()

    def _session(self):
        s = getattr(self.tls, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) phase0-axisA-delta"})
            self.tls.s = s
        return s

    def flush_journal(self):
        with self._journal_lk:
            rows, self._journal_buf = self._journal_buf, []
        if rows:
            journal_append(rows)

    # ── 단건 수집 ─────────────────────────────────────────────────────────────────────
    def fetch(self, corp_code: str, year: str, reprt: str) -> str:
        """성공 시 캐시에 원본 응답을 저장하고 상태코드를 돌려준다."""
        path = cache_path(corp_code, year, reprt)
        for attempt in range(4):
            self._await_pause()
            if not self._reserve():
                return "HALT"
            self.delay.wait()
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
                # ★ 020(요청 제한 초과) 은 우리 자체 카운터보다 권위 있는 실시간 신호다.
                #   자체 카운터가 뭐라 하든 DART 가 소진을 알려주면 그 자리에서 멈춘다.
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
            data = json.dumps(js, ensure_ascii=False).encode("utf-8")
            write_json(path, js)           # ← 원본 응답 그대로. PIT 필터는 읽을 때 건다.
            with self._journal_lk:
                self._journal_buf.append({
                    "corp_code": corp_code, "bsns_year": year, "reprt_code": reprt,
                    "status": st, "sha1": sha1_bytes(data), "bytes": len(data),
                    "collected_at": _dt.datetime.now().isoformat(timespec="seconds")})
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
                        f"(성공 {done:,} / 누적호출 {self.calls_run:,} / "
                        f"지연 {self.delay.cur:.2f}s)")
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 16. PIT 필터 — 이번 실행 전체의 핵심 (v1.2 를 무효화했던 결함의 수정)
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
#  ▣ 17. 그래프
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_graph(records, corp2code):
    """노드=종목코드, 엣지=(성명+출생년월) 동일인이 두 종목에 동시 임원 등재.

    출생년월 결측 레코드는 엣지 생성에서 제외한다. 측정대상 밖의 상대 노드도 유지한다.
    이 루프는 스냅샷당 레코드 수만 건(최악 4~5만) 규모라 파이썬 반복의 오버헤드는
    네트워크 I/O(스냅샷당 최대 수천 콜, 초 단위)에 비해 무시할 수준이다 — 여기를
    벡터화해도 병목은 옮겨가지 않는다.
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
#  ▣ 18. 전이 — born / died. 절대 합산하지 않는다.
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


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


# ══════════════════════════════════════════════════════════════════════════════════════════
#  ▣ 19. 메인
# ══════════════════════════════════════════════════════════════════════════════════════════
def main():
    _bootstrap()
    RULE("PHASE 0 — 축 A-Δ 재측정 v1.3   (LIVE / 로컬 JupyterLab)")
    LOG(f"PROJECT_ROOT : {ROOT}")
    LOG(f"GDRIVE_ROOT  : {GDRIVE_ROOT or '(미설정 — 로컬 전용)'}")
    LOG(f"실행 시각    : {RUN_STARTED:%Y-%m-%d %H:%M:%S}")
    LOG(f"정렬 방식    : {ALIGNMENT} — as_of = 법정 제출기한")
    LOG(f"유니버스     : {'KOSPI+KOSDAQ+KONEX' if INCLUDE_KONEX else 'KOSPI+KOSDAQ (KONEX 제외)'}")

    # ── 1. 계약 검사 + 소스 가용성 사전점검 ──────────────────────────────────────────
    RULE("1. 계약 검사 · 데이터소스 사전점검")
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
        LOG(f"  ✓ {cid:<28} {desc}")

    krx_oa = probe_krx_openapi() if KRX_OPENAPI_KEY else False
    LOG("")
    LOG("데이터소스 가용성")
    LOG(f"  DART_API_KEY      : 설정됨 (끝 4자리 …{DART_API_KEY.strip()[-4:]})")
    LOG(f"  pykrx             : {'사용가능' if PYKRX_AVAILABLE else f'사용불가 — {PYKRX_DIAGNOSTIC}'}")
    LOG(f"  KRX Open API      : {'사용가능(mode=' + KRX_OPENAPI_MODE + ')' if krx_oa else ('키 있으나 엔드포인트 미승인/오류' if KRX_OPENAPI_KEY else '키 미설정')}")
    LOG(f"  FinanceDataReader : {'사용가능' if FDR_AVAILABLE else '미설치(선택 의존성 — 상장목록 폴백 일부 축소)'}")
    LOG(f"  KRX ID/PW(마켓플레이스) : {'설정됨' if (KRX_ID and KRX_PW) else '미설정 — pykrx 비인증 경로로 진행'}")
    if not PYKRX_AVAILABLE and not krx_oa:
        WARN("  pykrx 와 KRX Open API 가 둘 다 사용 불가하다 — 이 실행은 시가총액을 전혀 "
             "얻을 수 없으므로 모든 스냅샷이 UNVERIFIED 로 끝날 가능성이 높다. "
             "KRX_OPENAPI_KEY 발급을 강력 권장한다(§0).")

    # ── 2. 캐시 인벤토리 (P0_CACHE_FIRST) ────────────────────────────────────────────
    RULE("2. 캐시 인벤토리 (로컬 → 드라이브 공용 인덱스 순으로 탐색)")
    n_local = {k: len(v) for k, v in scan_cache_inventory().items()}

    LOG("")
    LOG("캐시 인벤토리 (로컬 보유분 — 부족분은 4b 에서 드라이브까지 마저 확인한다)")
    for sid, nom, _pe, yy, rc, as_of, need in SNAPSHOT_SPEC:
        have0 = n_local.get((yy, rc), 0)
        LOG(f"  {yy}/{rc} ({sid} {REPRT_NAME[rc]:<6}) : 로컬 {have0:>5,}건 / 필요 ~{need:,}건")
    corpcode_cached = _corpcode_parsed().exists()
    LOG(f"  corpCode 파싱 결과 : {'있음' if corpcode_cached else '없음(드라이브 공용 인덱스 확인 예정)'}")

    inventory = {"local_before": {f"{k[0]}/{k[1]}": v for k, v in n_local.items()},
                 "corpcode_parse_cache": corpcode_cached, "estimated_new_calls": 0,
                 "actual_new_calls": 0}
    write_json(DIR_REPORTS / "cache_inventory.json", inventory)

    # ── 3. corpCode ──────────────────────────────────────────────────────────────────
    RULE("3. corpCode")
    cc = load_corpcode()
    corp2code = dict(zip(cc["corp_code"], cc["code"]))
    code2corp = {}
    for corp, code in zip(cc["corp_code"], cc["code"]):
        code2corp.setdefault(code, corp)
    LOG(f"  corp_code → 종목코드 매핑 {len(corp2code):,}건 / 종목코드 고유 {len(code2corp):,}건")

    # ── 4a. 유니버스 확정 (DART 임원 호출 0건. 여기서 빈 유니버스를 먼저 걸러낸다) ────
    RULE("4a. 유니버스 확정 — 거래일 스냅 + 빈 유니버스 가드 + 다중소스 폴백")
    universes = {}
    for sid, nom, _pe, yy, rc, as_of, _need in SNAPSHOT_SPEC:
        LOG(f"  {sid} 기준일 {nom} / {yy}-{rc} {REPRT_NAME[rc]} / as_of {as_of}")
        universes[sid] = build_universe(sid, nom)

    live_ids = [s for s in universes if universes[s]["status"] == "OK"]
    if not live_ids:
        raise HardStop("모든 스냅샷이 빈 유니버스다. pykrx/KRX Open API 접속 상태를 확인할 것.")

    # ── 4b. 정확한 부족분 계산(로컬+드라이브) → 5,000건 게이트 → 수집 ────────────────
    RULE("4b. 수집 대상 확정 (드라이브 공용 인덱스에서 먼저 당겨온다)")
    inv_after = scan_cache_inventory()
    jobs_by_snap, all_jobs, drive_restored_total = {}, [], 0
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
        missing_local = [(cp, yy, rc) for cp in want if cp not in have]
        restored = restore_officer_blobs_from_drive(missing_local)
        drive_restored_total += restored
        if restored:
            have = inv_after[(yy, rc)] = have | {cp for cp, _, _ in missing_local
                                                 if cache_path(cp, yy, rc).exists()}
        todo = [(cp, yy, rc) for cp in want if cp not in have]
        jobs_by_snap[sid] = todo
        all_jobs += todo
        LOG(f"  {sid}: 전상장 {len(u['listed']):,}종목 → corp_code 매핑 {len(want):,}건 "
            f"(미매핑 {u['unmapped_codes']:,}) / 로컬캐시 {len(want) - len(missing_local):,} / "
            f"드라이브복원 {restored:,} / 신규필요 {len(todo):,}")

    LOG(f"  ── 드라이브에서 복원한 기존 캐시: {drive_restored_total:,}건")
    LOG(f"  ── 실제 신규 API 호출 예정: {len(all_jobs):,}건 — 임원현황 수집은 아직 시작하지 않았다")
    inventory["drive_restored"] = drive_restored_total
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
    projected_today = col.calls_today + len(all_jobs)
    LOG(f"  오늘 이전 실행분 누적 호출 {col.calls_today:,}건 + 이번 예정 {len(all_jobs):,}건 "
        f"= {projected_today:,}건 (일일한도 {CALL_BUDGET_DAILY:,})")
    if projected_today > CALL_BUDGET_DAILY:
        WARN(f"  예정 호출을 전부 채우면 일일한도를 {projected_today - CALL_BUDGET_DAILY:,}건 "
             f"초과한다 — 도중에 DART_020 으로 자동 정지되고 나머지는 resume_todo.json 에 "
             f"저장된다(중단이지 실패가 아니다). 여러 날에 걸쳐 나눠 완주하면 된다.")

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
        OK("  신규 호출 0건 — 전량 캐시 히트(로컬+드라이브)")

    # ── 4c-보조. 드라이브 증분 동기화 — 이번 실행에서 새로 받았든, 예전부터 로컬에만
    #   있었든 상관없이 스냅샷당 한 번씩 돌린다. 신규 호출이 없던 스냅샷(전량 캐시 히트)의
    #   로컬 전용 캐시도 이 기회에 함께 올라간다 — 그렇지 않으면 "GDRIVE_ROOT 를 나중에
    #   켠 경우" 기존 로컬 캐시가 영영 드라이브에 오르지 않는다.
    if GDRIVE_ROOT:
        RULE("4c-보조. 드라이브 증분 동기화")
        for sid, _n, _p, yy, rc, _a, _need in SNAPSHOT_SPEC:
            u = universes[sid]
            if u["status"] != "OK" or not u.get("corp_wanted"):
                continue
            sync = sync_officer_blobs_to_drive([(cp, yy, rc) for cp in u["corp_wanted"]])
            if sync["attempted"]:
                LOG(f"  {sid}: 신규 {sync['synced']:,} / 이미있음 {sync['already_there']:,}" +
                    (f" / 오류 {sync['error']}" if sync["error"] else ""))
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
               "status_reason": u.get("status_reason", ""),
               "mcap_source": u.get("mcap_source", ""), "universe_source": u.get("universe_source", "")}
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
        # 세야 인벤토리와 말이 맞는다.
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

        # ★ 이번 수정이 실제로 걸렸는지의 하드 검사
        if rec["last_rcept_dt"] and rec["last_rcept_dt"] > compact(as_of):
            raise ContractViolation(
                f"P0_PIT_STRICT_DELTA 위반: {sid} 최종접수일 {rec['last_rcept_dt']} > "
                f"as_of {compact(as_of)}. 필터가 걸리지 않았다 — 즉시 중단한다.")
        if n_look == 0:
            WARN(f"    {sid} 룩어헤드 폐기 0건 — 이전 오염의 신호였던 값이다. "
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

    # ── 7. 성공 조건 — 게이트 통과 여부와 무관하다 ───────────────────────────────────
    RULE("7. 성공 조건")
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
    c1_lookahead = len(live) == 4 and all(s["pit_dropped_lookahead"] > 0 for s in live)
    LOG(f"  ① 4개 스냅샷 PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : {'충족' if c1 else '미충족'}")
    LOG(f"     (그 중 룩어헤드 폐기가 4개 스냅샷 모두 ≠ 0 : {'예' if c1_lookahead else '아니오'})")
    for x in c1_each:
        LOG(f"       {x['snapshot']}: 폐기 {x['pit_dropped']:,}건 (룩어헤드 {x['lookahead']:,}) / "
            f"최종접수일 {x['last_rcept_dt'] or '—'} ≤ as_of {x['as_of']} → "
            f"{'OK' if x['within_as_of'] else 'NG'}")
    LOG(f"  ② 전이 3개의 edge_born / edge_died 산출              : {'충족' if c2 else '미충족'}")
    LOG(f"  ⇒ 이번 실행: {'성공' if (c1 and c2) else '미완'}  (수치의 크기는 성공 여부와 무관)")

    # ── 8. 산출물 ────────────────────────────────────────────────────────────────────
    RULE("8. 산출물")
    verdict = {
        "run_mode": "LIVE",
        "spec_version": "v1.3",
        "generated_at": RUN_STARTED.isoformat(timespec="seconds"),
        "project_root": str(ROOT),
        "gdrive_root": GDRIVE_ROOT or "",
        "alignment": ALIGNMENT,
        "alignment_note": "(A) 관측시점 정렬 — as_of = 해당 보고서의 법정 제출기한",
        "data_sources": {
            "pykrx_available": PYKRX_AVAILABLE, "pykrx_diagnostic": PYKRX_DIAGNOSTIC,
            "krx_openapi_available": KRX_OPENAPI_OK, "fdr_available": FDR_AVAILABLE,
            "pykrx_import_attempts": PYKRX_IMPORT_ORDER["attempts"],
        },
        "methodology": {
            "universe": "KOSPI+KOSDAQ+KONEX" if INCLUDE_KONEX else "KOSPI+KOSDAQ (KONEX 제외)",
            "measure_n": MEASURE_N,
            "node": "종목코드 (해당 스냅샷 거래일의 시총>0 상장사 전체)",
            "edge": "(성명, 출생년월) 동일 인물이 두 종목에 동시 임원 등재",
            "edge_attribution": "교집합 종목에 한쪽 끝이라도 걸친 엣지",
            "birth_missing": "엣지 생성에서 제외 (보간하지 않음)",
            "empty_universe_min": EMPTY_UNIVERSE_MIN,
            "mcap_source_priority": "krx_openapi > pykrx (그 외 소스는 과거 시총을 신뢰성 "
                                    "있게 제공하지 않아 쓰지 않음)",
            "universe_source_priority": "pykrx(정확한 시점) > FDR+KIND+DART corpCode 병합"
                                        "(생존자편향 방지 point-in-time 필터, 시장 라벨 없음)",
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
        "skipped": [
            {"axis": "A(본체)", "status": "SKIPPED_BY_SCOPE",
             "note": "A-1/A-2/A-3 는 이전 실행에서 확인 완료 — 재측정하지 않는다"},
            {"axis": "B(BigQuery)", "status": "SKIPPED_BY_SCOPE"},
            {"axis": "C(국민연금)", "status": "SKIPPED_BY_SCOPE"},
            {"axis": "스몰캡 백테스트 비교", "status": "SKIPPED_BY_SCOPE",
             "note": "P0_NO_STRATEGY 와 충돌 — KNOWN_LIMITATIONS 참조"},
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
          f"- 데이터소스: pykrx={'가능' if PYKRX_AVAILABLE else '불가'} · "
          f"KRX Open API={'가능' if KRX_OPENAPI_OK else '불가'} · "
          f"FDR={'설치됨' if FDR_AVAILABLE else '미설치'}",
          "", "## 스냅샷", "",
          "| 스냅샷 | 기준일(명목→사용) | 보고서 | as_of | 노드 | 엣지 | PIT폐기(룩어헤드) | "
          "최종접수일 | 캐시히트 | 신규호출 | 시총소스 | 유니버스소스 | 상태 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in snap_out:
        d = s["date_nominal"] if s["date_nominal"] == s["date"] else f"{s['date_nominal']}→{s['date']}"
        md.append(f"| {s['id']} | {d} | {s['report']} {s['report_name']} | {s['as_of']} | "
                  f"{s['nodes']:,} | {s['edges']:,} | {s['pit_dropped']:,} "
                  f"({s['pit_dropped_lookahead']:,}) | {s['last_rcept_dt'] or '—'} | "
                  f"{s['cache_hit']:,} | {s['api_new']:,} | {s.get('mcap_source') or '—'} | "
                  f"{s.get('universe_source') or '—'} | {s['status']} |")
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
    md += ["", "## 성공 조건", "",
           f"- ① PIT 폐기 ≠ 0 이고 최종접수일 ≤ as_of : **{'충족' if c1 else '미충족'}**",
           f"- ② 전이 3개 edge_born/edge_died 산출 : **{'충족' if c2 else '미충족'}**", "",
           "## 범위 밖", "",
           "- 축 A 본체(A-1/A-2/A-3): 이전 실행 확인 완료 — 재측정 안 함",
           "- 축 B(BigQuery) / 축 C(국민연금): SKIPPED_BY_SCOPE",
           "- 시총 하위 1,000 스몰캡 버전 백테스트 비교: SKIPPED_BY_SCOPE "
           "(P0_NO_STRATEGY 와 충돌 — known_limitations 참조)", "",
           "## known_limitations", ""]
    md += [f"{i}. {s}" for i, s in enumerate(KNOWN_LIMITATIONS, 1)]
    write_text(DIR_REPORTS / "phase0_summary_v13.md", "\n".join(md) + "\n")

    for f in ("phase0_verdict_v13.json", "phase0_verdict_v13.csv", "phase0_summary_v13.md",
              "diag_edge_events.csv", "diag_pit_dropped_delta.csv", "cache_inventory.json",
              "run_log.txt"):
        p = DIR_REPORTS / f
        LOG(f"  {'✓' if p.exists() else '✗'} {p}")
    if GDRIVE_ROOT:
        LOG(f"  드라이브 공용 인덱스: {drive_shared()}")
    RULE("완료")
    return verdict


if __name__ == "__main__":
    try:
        VERDICT = main()
    except (ContractViolation, DiskFull, HardStop) as _e:
        ERR(f"{type(_e).__name__}: {_e}")
        raise
