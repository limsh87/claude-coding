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
#     [S8] 백테스트+성과검증(4전략 × 전체/시총하위1000 × 트랙별 전체 출력)
#     [S9] 트랙 비교 — 빠른판(TP12M) vs 정밀판(EPS·PDF)
#     [S10] 강건성 검사(민감도/서브기간/집중도/플라시보/지연)
#     [S11] 해석표 · 드라이브 저장(공용/전용 인덱스) · 다운로드 링크
#
#   ▣ 이중 트랙 (FORECAST_METRIC_MODE="BOTH", 기본값)
#     · 빠른판(TP12M) — 리스트 페이지의 '적정가격'만 쓴다. **PDF 원문이 필요 없어** 수 분에
#       10년치 4전략 백테스트가 완주한다. PDF 수집이 막혀도 결과가 항상 나온다.
#     · 정밀판(EPS)  — PDF 원문에서 EPS 추정치를 파싱한다(명세 §1 기본). 느리고 비싸다.
#     · 두 트랙은 **같은 가격행렬·같은 유니버스·같은 파라미터**를 공유한다. 트랙을 늘려도
#       시장데이터 조회는 1건도 늘지 않는다. 차이는 '예측 대상 지표' 하나뿐이므로
#       S9 비교표가 곧 "PDF 파싱이 성과로 회수되는가"의 답이 된다.
#
#   ▣ 전수수집을 목표로, 그러나 시간 안에 (§31·§36 기준 신뢰도 판정 동반)
#     · PDF 파싱은 **순수 CPU 작업**이라 스레드로는 GIL 이 코어를 못 쓴다(실측 24건/분).
#       확보(네트워크·스레드)와 파싱(CPU·프로세스)을 분리하고, 추출기는 이 장비에서
#       **실측해서** 빠른 것을 고른다(pymupdf → pypdf → pdfplumber).
#     · 단계 예산은 '남은 수집예산 − 백테스트 유보(30분)' 전부를 쓴다. 고정 60분은
#       4시간 중 3시간을 놀려 전수까지 필요한 실행 횟수를 늘릴 뿐이었다.
#     · 같은 예산이면 **(종목,월)에 2인 이상이 되는 칸부터** 받는다(§31) — 다운로드
#       1건당 쓸 수 있는 신호가 최대가 되고, 중간에 멈춰도 표본이 쓸모 있게 남는다.
#     · 종결 원장으로 재개가 보장되어 재실행할수록 100% 로 수렴한다. 매 실행마다
#       '지금 결과를 믿어도 되는가'를 커버리지 표로 판정해 출력한다.
#
#   ▣ 윈도우·주피터에서만 터지는 것들 (리눅스에선 절대 재현되지 않는다)
#     · 경로 포함 판정을 `realpath().startswith()` 로 하면 윈도우에서 오탐한다
#       (대소문자 · 8.3 단축명 · 확장길이 접두 · 아직 없는 경로). 절대1원칙의 방어선이
#       정상 쓰기를 막아 실행이 통째로 멈췄다 → normcase+commonpath 로 판정(계약 C-경로).
#     · 파싱 프로세스 풀이 `BrokenProcessPool` 로 죽었다. spawn 자식은 기동 직후
#       **부모의 __main__ 을 다시 실행**하는데 주피터의 __main__ 은 디스크에 없다.
#       __file__ 을 잠시 치우고 워커를 전부 미리 띄운 뒤 복구한다(__spec__ 은 None 으로 —
#       지우면 multiprocessing 이 AttributeError 를 낸다).
#
#   ▣ 막힌 소스에 시간을 쓰지 않는다 (회로차단 · 사전점검 · 진행표시)
#     · 소스별 회로차단기: 연속 실패가 쌓이면 그 소스를 끊고, 이후 요청은 대기 0초로 통과.
#     · PDF 단계는 시작 전에 호스트를 실측(최대 3건)하고, 막혔으면 계획에서 제외한다.
#     · 한경컨센서스는 실행 시점에 경로 후보를 두드려 보고 살아 있는 것을 자동 선택한다.
#       홈조차 403이면 경로 문제가 아니라 **발신 IP 차단**이 확정되므로 더 두드리지 않고,
#       차단 사실을 캐시에 남겨 쿨다운(기본 3시간) 동안은 아예 접근하지 않는다
#       (재시도가 차단 기간을 늘린다). 그동안 캐시+네이버로 백테스트는 그대로 진행된다.
#
#   ▣ 캐시 절대 1원칙
#     · 기존 구글드라이브 캐시(어느 전략이 만든 것이든)는 **읽기 전용**으로만 탐색·재활용.
#     · 신규 수집분은 전부 이 전략의 쓰기 루트에 저장하고 공용/전용 인덱스(append-only
#       JSONL 저널)에 등재. 기존 인덱스 파일에는 **쓰기 자체를 하지 않으므로** 훼손이
#       구조적으로 불가능합니다. (실행 후 실측 검증까지 수행 — S2 계약 C-보존)
#
#   ▣ 반복 오류의 행동패턴 감사 — 왜 같은 종류의 사고가 계속 났는가
#     지금까지 사용자 환경에서 터진 사고를 원인별로 묶으면 딱 두 갈래였다.
#       (A) **한 번도 실행해 본 적 없는 경로를 배포** — URL 자리표시자 불일치(KeyError),
#           존재하지 않는 파일 확장자(.csv.gz→404), 내 컨테이너에서 검증 불가능한 검사를
#           차단 게이트로 넣은 것, 그리고 이번의 'PDF 계획표에서 멈춤'.
#       (B) **외부 의존을 무경계로 신뢰** — KRX 재로그인 무한루프, pykrx 단일 의존 붕괴,
#           PDF 단계가 4시간 예산 전부 소모, 네이티브 확장 예외(PanicException)로 전체 사망.
#     공통 뿌리는 하나다: *검증되지 않은 가정을 검증된 사실처럼 다뤘다*.
#     구조적 대응(이 파일에 내장):
#       ① S2 자체계약 — 계산 규칙을 실행으로 증명. 실패하면 실데이터를 만지지 않는다.
#       ② S2b 실경로 리허설 — 네트워크만 픽스처로 바꾸고 수집 함수를 **실물 실행**.
#          이 환경에서 확인 불가능한 항목은 반드시 ⓘ(비차단)로 표시 — 내 검사가 남의
#          실행을 막는 사고를 두 번 내지 않기 위해서다.
#       ③ S3 합성 스모크 — 심어둔 알파를 실제로 복원하는지 확인(플라시보·지연 검사 포함).
#       ④ 확인할 수 없는 것은 **코드가 스스로 진단하고 강등**한다 — 추측해서 하드코딩하지
#          않는다(한경 경로 자동탐색, 호스트 사전점검, 회로차단, 진행표시).
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
RESEARCH_PDF_CAP_MONTH = 0        # (구) 월별 상한 — 아래 두 값이 실제 제어를 담당합니다
#    ▸ PDF 추출은 예전에 파이프라인 전체를 삼켰습니다(대상 5만건 → 4시간 소진).
#      이제 '단계 예산'과 '한 실행당 신규 상한'으로 못박고, 종결 원장에 진행분을
#      기록해 **다음 실행이 이어받습니다**. 여러 번 돌리면 자연히 100%로 수렴합니다.
#    ▸ **전수수집을 목표로 하되 시간은 지킨다**: 0 이면 '남은 수집예산 − 백테스트 유보분'
#      을 이 단계에 전부 씁니다. 60 같은 고정값은 4시간 예산 중 1시간만 쓰고 3시간을
#      놀리게 만들어, 전수까지 필요한 실행 횟수를 쓸데없이 늘렸습니다.
PDF_STAGE_BUDGET_MIN   = 0        # 0 = 자동(권장) · 양수면 그 분(minutes)으로 고정
BACKTEST_RESERVE_MIN   = 30       # 백테스트·강건성·저장에 남겨 둘 시간(분)
PDF_MAX_NEW_PER_RUN    = 0        # 0 = 무제한(시간예산이 실제 통제자입니다)
                                  #   이미 로컬에 있는 PDF 는 이 상한과 무관합니다
PDF_PROGRESS_EVERY     = 25       # 이만큼 처리할 때마다 진행 한 줄. '멈춘 것처럼 보임' 방지
#    ▸ PDF 파싱은 **순수 CPU 작업**이라 스레드로는 GIL 때문에 코어를 못 씁니다(실측 24건/분).
#      확보(네트워크)와 파싱(CPU)을 분리해 파싱만 프로세스로 내보냅니다.
PDF_PARSE_PROCESSES    = True    # False 면 스레드로만(디버깅용). 자동으로 폴백도 합니다
PDF_PARSE_WORKERS      = 0       # 0 = 자동(코어수-2, 최대 12)
SOURCE_CIRCUIT_FAILS   = 8        # ★ 한 소스에서 연속 실패가 이만큼 쌓이면 그 소스를 즉시 차단.
                                  #   403 으로 막힌 사이트에 단계 예산을 통째로 헌납하는 사고를
                                  #   막는다(멈춘 것처럼 보이던 진짜 원인). 성공하면 즉시 복구.

# ── ⑤-2 주지표(예측 대상) 선택 ─────────────────────────────────────────────────────────────
#    "TP12M" = 목표주가 12개월. 리스트 페이지의 '적정가격'만으로 계산 → **PDF 불필요, 빠름**
#    "EPS"   = PDF 원문에서 추출한 EPS 추정치. 명세 §1 기본이지만 PDF 파싱이 필요 → 느림
#    "BOTH"  = 두 트랙을 한 번에 돌리고 **나란히 비교표**까지 출력 (권장·기본값)
#    "AUTO"  = 커버리지를 보고 한쪽만 자동 선택 (구버전 동작)
FORECAST_METRIC_MODE   = "BOTH"   # "BOTH" | "AUTO" | "EPS" | "TP12M"
#    ▸ 빠른 버전만 원하면 아래 한 줄을 True 로. PDF 단계를 통째로 건너뜁니다(수 분 내 완주).
QUICK_TP12M_ONLY       = False

# ── ⑥ 성능/자원 ─────────────────────────────────────────────────────────────────────────────
COLLECT_HOURS_BUDGET = 4.0        # ★ 수집 시간예산(시간). 초과하면 수집을 그 자리에서 멈추고
                                  #   지금까지 모은 데이터만으로 '중간 백테스트 결과'를 출력한다.
                                  #   (수집은 전부 증분 캐시라 재실행하면 멈춘 곳부터 이어받는다)
N_IO_THREADS   = 12               # 네트워크 병렬(스레드). 차단이 의심되면 6으로.
#    소스별 초당 요청 상한(차단 방지) — **전역** 상한이라 스레드를 늘려도 이 값을 못 넘습니다.
#    PDF 는 검색질의가 아니라 정적 파일이라 목록 조회보다 여유롭게 둡니다. 서버가 429/503 로
#    속도를 낮추라고 하면 즉시 절반으로 줄고, 성공이 이어지면 천천히 되돌립니다.
#    ★ 한경은 이미 이 PC 의 IP 를 차단했습니다(본문: "Access Denied: Your IP is blocked").
#      다시 차단당하지 않는 것이 최우선이라, 같은 사이트를 오래 수집해 본 다른 전략의
#      실측 정중값(초당 0.8회·동시 2)을 그대로 채택합니다. 빠르게 긁어서 다시 막히면
#      복구에 며칠이 걸리고, 그동안 신규 수집이 통째로 불가능해집니다.
QPS = {"krx": 1.5, "dart": 8.0, "hankyung": 0.8, "naver": 1.5, "kind": 2.0,
       "fdr": 4.0, "yahoo": 3.0, "generic": 3.0,
       "hankyung_pdf": 1.2, "naver_pdf": 4.0}
HANKYUNG_COOLDOWN_MIN  = 180     # IP 차단 감지 후 이 시간 동안은 아예 두드리지 않습니다
MEM_SOFT_GB    = 6.0              # 이 수준을 넘보면 청크 처리로 전환
COST_BPS_ONEWAY = 15.0            # 십분위 성과의 왕복비용 가정(수수료+세금+슬리피지, 편도 bp)

# ── ⑦ 비교전략 · 기타 ───────────────────────────────────────────────────────────────────────
COMPARE_BOTTOM_N = 1000           # 시총 하위 1000 종목 비교 유니버스
SEED = 20260809                   # 모든 난수의 단일 시드(결정성 계약 C-결정 검증 대상)
VERBOSE = True

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝 — 아래부터는 수정할 필요가 없습니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

if QUICK_TP12M_ONLY:              # 빠른 버전 스위치 — PDF 단계를 아예 걸지 않는다
    FORECAST_METRIC_MODE = "TP12M"
    RESEARCH_DOWNLOAD_PDF = False

SCG_BUILD = "scg_v1.20260809c"
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
         ("pypdf", "pypdf", "PDF 텍스트 추출 2순위(순수 파이썬 — 새 파이썬에서도 설치됨)"),
         ("pdfplumber", "pdfplumber", "PDF 텍스트 추출 3순위(가장 느림)")]


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
        # ★ 한 번에 몰아서 설치하면 **하나가 실패할 때 나머지도 전부 안 깔린다**.
        #   사용자 로그에서 yfinance 와 pymupdf 가 동시에 없던 것이 정확히 이 모양이었고,
        #   그 탓에 PDF 파싱이 몇 배 느린 2순위 라이브러리로만 돌았다. 하나씩 설치한다.
        for _m, _p in want:
            _pip([_p])
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
# ★ PDF 라이브러리는 네이티브 확장에 의존해서, 설치가 깨지면 평범한 Exception 이 아니라
#   인터프리터 수준 패닉(BaseException)을 던진다. except Exception 으로는 못 잡아
#   런 전체가 죽는다. 실제로 그렇게 죽었다 — 그래서 BaseException 까지 잡는 통로로 보낸다.
_fitz = _opt_import("pymupdf", lambda: __import__("fitz"))
_pdfplumber = _opt_import("pdfplumber", lambda: __import__("pdfplumber"))
_pypdf = _opt_import("pypdf", lambda: __import__("pypdf"))

# PDF 파서(pdfminer)는 폰트 메타가 조금만 이상해도 경고를 줄줄이 찍는다.
# 내용 추출에는 영향이 없고 stderr 만 채우므로 조용히 시킨다.
import logging as _logging
for _nm in ("pdfminer", "pdfminer.pdfinterp", "pdfminer.pdffont", "pdfminer.pdfpage",
            "pdfminer.converter", "pdfplumber", "fitz", "PIL"):
    try:
        _logging.getLogger(_nm).setLevel(_logging.ERROR)
    except Exception:
        pass

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
    # ★ 스레드 식별자까지 넣는다 — 같은 프로세스의 두 스레드가 같은 표를
    #   동시에 저장하면 임시파일이 겹쳐 윈도우에서 os.replace 가 깨진다.
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}.parquet"
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
    """소스별 초당 요청 상한 — 차단 방지의 1차 방어선.

    ★ 이 상한은 **전역 게이트**다. 스레드를 6개 띄워도 초당 처리량은 QPS 를 못 넘는다.
      그래서 '병렬 12'라는 표시만 믿으면 실제 소요를 크게 잘못 예측한다(PDF 6,000건이
      2건/초면 50분이다). 계획 표에 예상 소요를 함께 찍는 이유다.
      429/503(=서버가 속도를 낮추라고 말한 것)이 오면 즉시 절반으로 낮추고,
      성공이 이어지면 원래 값까지 천천히 되돌린다.
    """
    def __init__(self):
        self._lk = threading.Lock()
        self._next: Dict[str, float] = {}
        self._factor: Dict[str, float] = {}

    def qps(self, source: str) -> float:
        base = float(QPS.get(source, QPS["generic"]))
        return max(0.1, base * self._factor.get(source, 1.0))

    def wait(self, source: str):
        gap = 1.0 / self.qps(source)
        with self._lk:
            now = time.time()
            t = max(self._next.get(source, 0.0), now)
            self._next[source] = t + gap
        if t > now:
            time.sleep(t - now)

    def slow_down(self, source: str):
        with self._lk:
            f = self._factor.get(source, 1.0) * 0.5
            self._factor[source] = max(0.1, f)
        CON.warn(f"[{source}] 서버가 속도 제한을 알렸습니다 — 요청 속도를 "
                 f"{self.qps(source):.1f}건/초로 낮춥니다")

    def speed_ok(self, source: str):
        f = self._factor.get(source, 1.0)
        if f < 1.0:
            with self._lk:
                self._factor[source] = min(1.0, f * 1.15)


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
            except (RuleBreak, HaltRun):
                # ★ 계약 위반과 중단 지시는 '부분 실패'가 아니다. 이걸 삼켰더니
                #   리허설 로그에 'RuleBreak 2건'만 남고 원인이 사라졌다 — 재전파한다.
                raise
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
        self.write_root = os.path.abspath(
            os.path.expanduser(droot or "./scg_cache"))
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

    @staticmethod
    def _norm_forms(p: str) -> List[str]:
        """경로 비교용 정규형 — **realpath 와 abspath 두 형태를 모두** 돌려준다.

        ★ 여기가 실행을 통째로 막았다. 윈도우에서 `realpath(...).startswith(...)` 는
          네 가지 이유로 조용히 어긋난다:
            ⓐ 대소문자 (윈도우 파일시스템은 대소문자를 구분하지 않는다)
            ⓑ 8.3 단축명 — TEMP 가 단축명이면 realpath 가 긴 이름으로 바꿔 놓는다.
            ⓒ 확장길이 접두 — _getfinalpathname 이 붙여 돌려줄 때가 있다.
            ⓓ 존재하지 않는 경로 — realpath 는 '존재하는 접두까지'만 해석한다.
               쓰기 **직전**의 검사라 대상 파일은 아직 없다. 부모와 자식이 서로
               다른 지점까지만 해석되면 접두 비교가 깨진다.
          그래서 한 형태에만 기대지 않고 두 형태를 모두 만들어 비교한다.
        """
        out: List[str] = []
        for f in (os.path.abspath, os.path.realpath):
            try:
                q = str(f(p))
            except Exception:
                continue
            if q.startswith("\\\\?\\"):
                q = q[4:]
            out.append(os.path.normcase(os.path.normpath(q)))
        return list(dict.fromkeys(out)) or [os.path.normcase(os.path.normpath(str(p)))]

    @staticmethod
    def _inside(child: str, parent: str) -> bool:
        """child 가 parent **안**인가.

        ★ 문자열 startswith 는 형제 디렉터리를 안으로 오판한다
          ('scg_cache2' 가 'scg_cache' 로 시작한다). commonpath 로 판정한다.
        """
        for c in Depot._norm_forms(child):
            for q in Depot._norm_forms(parent):
                try:
                    if c == q or os.path.commonpath([c, q]) == q:
                        return True
                except ValueError:          # 드라이브가 다르면 commonpath 가 예외
                    continue
        return False

    def _guard_write(self, path: str):
        # ★ 순서가 의미를 만든다: 읽기전용 루트는 **한 형태라도 안이면 거부**(보수),
        #   쓰기 루트는 **한 형태라도 안이면 허용**(오탐 제거). 절대1원칙은 앞의
        #   검사로 지켜지고, 뒤의 검사는 정상 쓰기를 막지 않는 역할만 한다.
        for ro in self.read_roots:
            if self._inside(path, ro):
                raise RuleBreak(f"[절대1원칙] 읽기전용 캐시 루트에 쓰기 시도: {path}")
        if not self._inside(path, self.write_root):
            raise RuleBreak(f"[절대1원칙] 쓰기 루트 밖 기록 시도: {path} "
                            f"(쓰기 루트: {self.write_root})")

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
                    CON.debug(f"캐시 {name}(내 쓰기루트) 스키마가 예전 버전 — "
                              f"건너뛰고 다른 루트를 계속 찾습니다"
                              f"(기존 파일은 그대로 둡니다).")
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
            ok_w = False
            for attempt in range(2):                      # 윈도우 파일잠금 등 일시적 실패 재시도
                try:
                    write_atomic_bytes(path, data)
                    ok_w = True
                    break
                except Exception as e:
                    err = e
                    time.sleep(0.2)
            if not ok_w and os.path.exists(path):
                # ★ 같은 내용(=같은 sha)을 다른 스레드가 방금 썼다. 윈도우에서 이때
                #   os.replace 가 PermissionError 를 내는데, 파일은 멀쩡히 있다.
                #   이걸 실패로 세면 멀쩡한 PDF 를 버리게 된다.
                ok_w = True
                self.stats["blob동시쓰기회피"] += 1
            if not ok_w:
                self.stats[f"blob저장실패:{type(err).__name__}"] += 1
                if self.stats[f"blob저장실패:{type(err).__name__}"] <= 3:
                    CON.warn(f"blob 저장 실패({type(err).__name__}) — 추출은 계속합니다"
                             f"(원문 보관만 건너뜁니다): {str(key)[:16]}")
                return None
        else:
            self.stats["blob중복회피"] += 1
        uid = h1("blob", domain, key, sha)
        bm = getattr(self, "_blobmap", None)
        if bm is not None and domain in bm:
            bm[domain][str(key)] = path            # 사전을 최신으로 유지
        self._register(scope, dict(uid=uid, domain=domain, key=str(key),
                                   path=os.path.relpath(path, self.write_root),
                                   fmt=ext, bytes=len(data), sha1=sha, source=source))
        return uid

    def _blob_map(self, domain: str) -> Dict[str, str]:
        """도메인별 key→경로 사전을 **한 번만** 만든다.
        ★ 항목마다 인덱스 DataFrame 을 필터링하면 6,000건 처리에서만 6천만 번의
          문자열 변환이 일어난다 — 조용히 몇 분을 먹는 병목이라 사전으로 바꾼다."""
        cache = getattr(self, "_blobmap", None)
        if cache is None:
            cache = self._blobmap = {}
        if domain in cache:
            return cache[domain]
        out: Dict[str, str] = {}
        idx = self.index_frame("공용")
        if len(idx):
            m = idx[idx["domain"] == domain]
            for k, pth, ab in zip(m["key"].astype(str), m["path"].astype(str),
                                  (m["abs_path"].astype(str) if "abs_path" in m.columns
                                   else [""] * len(m))):
                if k not in out:
                    out[k] = os.path.join(self.write_root, pth) if pth else str(ab)
        cache[domain] = out
        return out

    def blob_path(self, domain: str, key: str) -> Optional[str]:
        """★ 바이트가 아니라 **경로**를 돌려준다. 파싱을 별도 프로세스로 보낼 때
        수백 KB 를 프로세스 간에 실어 보내는 대신 경로 한 줄만 넘기기 위해서다."""
        p = self._blob_map(domain).get(str(key))
        if p and os.path.exists(p):
            return p
        p = self._adopted.get((domain, str(key)))
        return p if (p and os.path.exists(p)) else None

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
# ★ 세션은 스레드로컬이다. 워밍업(홈 방문)으로 받은 쿠키가 메인 스레드에만 남으면
#   정작 다운로드를 수행하는 워커 스레드는 쿠키 없이 요청해 403 을 맞는다.
#   그래서 쿠키는 전역 씨앗에 모아두고 새 세션마다 심어 준다.
_COOKIE_SEED: Dict[str, str] = {}
_COOKIE_LK = threading.Lock()


def cookie_seed_update(sess: requests.Session):
    with _COOKIE_LK:
        try:
            _COOKIE_SEED.update({c.name: c.value for c in sess.cookies})
        except Exception:
            pass


class SourceCircuit:
    """소스별 회로차단기 — '막힌 곳에 시간을 쓰지 않는다'는 단 하나의 목적.

    ★ 이것이 없어서 사고가 났다. 한경컨센서스가 403 을 돌려주는 상태에서 PDF
      6,000건을 그대로 시도했고, 건당 (스로틀 0.5s × 2회 + 403 대기 1.5s+3.0s)
      ≈ 5초씩 소모하며 60분 예산을 전부 태웠다. 화면에는 아무 줄도 찍히지
      않으니 사용자에게는 '멈춤'으로 보인다. 연속 실패가 쌓이면 즉시 끊고,
      이후 요청은 네트워크도 대기도 없이 곧바로 None 을 돌려준다.
      성공이 한 번이라도 나오면 카운터는 0으로 복구된다(일시적 장애와 구분).
    """

    def __init__(self, limit: int = 8, quiet: bool = False):
        self.limit = int(limit)
        self.quiet = bool(quiet)
        self._streak: Counter = Counter()
        self.opened: "OrderedDict[str, str]" = OrderedDict()
        self._lk = threading.Lock()

    def blocked(self, source: str) -> bool:
        return source in self.opened

    def _mute(self, source: str) -> bool:
        return self.quiet or str(source).startswith("__")

    def ok(self, source: str):
        with self._lk:
            if self._streak.get(source):
                self._streak[source] = 0
            if source in self.opened:            # 되살아났다 — 차단 해제
                self.opened.pop(source, None)
                if not self._mute(source):
                    CON.ok(f"[{source}] 응답이 돌아왔습니다 — 차단을 해제합니다")

    def fail(self, source: str, why: str) -> bool:
        with self._lk:
            self._streak[source] += 1
            n = self._streak[source]
            if n >= self.limit and source not in self.opened:
                self.opened[source] = f"{why} (연속 {n}회)"
                if not self._mute(source):
                    CON.warn(f"[{source}] 연속 실패 {n}회 — 이 소스를 차단합니다({why}). "
                             f"남은 요청은 즉시 건너뛰고 다른 소스/캐시로 진행합니다.")
                return True
        return False

    def open_now(self, source: str, why: str):
        with self._lk:
            if source not in self.opened:
                self.opened[source] = why
        if not self._mute(source):
            CON.warn(f"[{source}] 사전 점검 실패 — 차단하고 진행합니다({why})")

    def table(self):
        self.opened = OrderedDict((k, v) for k, v in self.opened.items()
                                  if not str(k).startswith("__"))
        if not self.opened:
            return
        CON.grid([[k, v] for k, v in self.opened.items()], ["차단된 소스", "사유"],
                 ["l", "l"], title="회로차단 현황 (해당 소스는 캐시로만 진행했습니다)")


CIRCUIT = SourceCircuit(SOURCE_CIRCUIT_FAILS)


def _sess() -> requests.Session:
    s = getattr(_TL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9",
                          "Accept": "*/*", "Connection": "keep-alive"})
        with _COOKIE_LK:
            for k, v in _COOKIE_SEED.items():
                try:
                    s.cookies.set(k, v)
                except Exception:
                    pass
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
    if CIRCUIT.blocked(source):
        # ★ 차단된 소스는 대기도 하지 않는다 — 여기가 '멈춘 것처럼 보이던' 지점이다.
        HTTP_TALLY[f"{source}:SKIP"] += 1
        return None
    hd = dict(headers or {})
    if referer:
        hd["Referer"] = referer
    last = ""
    counted = False          # 이 URL 의 실패를 회로차단 카운터에 이미 반영했는가
    for k in range(tries):
        THROTTLE.wait(source)
        if on_attempt:
            on_attempt()
        try:
            r = _sess().get(url, params=params, headers=hd, timeout=timeout)
            HTTP_TALLY[f"{source}:{r.status_code}"] += 1
            if r.status_code == 200:
                CIRCUIT.ok(source)
                THROTTLE.speed_ok(source)
                return r.content if as_bytes else decode_kr(r.content, r.encoding)
            last = f"HTTP {r.status_code}"
            if r.status_code in (429, 503):
                THROTTLE.slow_down(source)
                time.sleep(min(30.0, 2.0 * (2 ** k)) + random.random())
            elif r.status_code in (404, 410):
                # 그 문서 하나가 없는 것이지 사이트가 막힌 게 아니다.
                # ★ 이걸 회로차단에 넣으면 오래된 리포트 몇 건 때문에 멀쩡한 소스가
                #   통째로 끊긴다 — 개별 자원 부재는 카운터에 넣지 않고 즉시 포기한다.
                break
            elif r.status_code in (401, 403):
                # 권한 거부는 같은 요청을 되풀이해도 바뀌지 않는다. 재시도로
                # 시간을 태우는 대신 한 번만 짧게 물러서고 끝낸다.
                counted = True
                if CIRCUIT.fail(source, last) or k >= min(1, tries - 1):
                    break
                time.sleep(0.4)
                continue
        except Exception as e:
            last = type(e).__name__
            HTTP_TALLY[f"{source}:EXC"] += 1
            counted = True
            if CIRCUIT.fail(source, last):
                break
            time.sleep(min(10.0, 1.6 ** k) + random.random() * 0.3)
    else:
        if not counted:      # 같은 실패를 두 번 세면 멀쩡한 소스가 일찍 끊긴다
            CIRCUIT.fail(source, last or "재시도 소진")
    HTTP_TALLY[f"{source}:FAIL"] += 1
    CON.debug(f"수신 실패[{source}] {last}: {url[:90]}")
    return None


_PROBE_SESS: List[requests.Session] = []


def _probe_get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
               timeout: float = 20.0) -> Tuple[int, bytes, Optional[str], int]:
    """진단 전용 GET — 스로틀·회로차단·재시도를 **전부 우회**한다.

    ★ 진단은 '지금 이 순간 서버가 무엇을 돌려주는가'를 있는 그대로 봐야 한다.
      `fetch` 를 쓰면 재시도가 결과를 뭉개고, 진단이 회로차단을 건드려 서로를 오염시킨다.
      반환에 상태코드와 **원문 바이트**를 그대로 실어 보내는 이유도 같다 —
      403 의 본문을 봐야 '사이트 WAF' 와 '사내 프록시' 를 구분할 수 있다.
      (리허설은 이 함수 하나만 바꿔치기해 실제 네트워크 없이 배선을 검증한다.)
    """
    if not _PROBE_SESS:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA, **_HK_BROWSER_HEADERS})
        _PROBE_SESS.append(s)
    s = _PROBE_SESS[0]
    r = s.get(url, params=params, headers=headers or {}, timeout=timeout)
    cookie_seed_update(s)
    return r.status_code, r.content, r.encoding, len(s.cookies)


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


FDR_CACHE_LISTING_FROM = "2026-03-08"   # 이 저장소의 listing 계열 최초 존재일(실측)


def fdr_cache_csv(kind: str, back_days: int = 21,
                  asof: Optional[pd.Timestamp] = None) -> Optional[pd.DataFrame]:
    """영업일 CSV만 존재하므로 기준일부터 거꾸로 훑는다. 인증 불필요."""
    base = (asof or pd.Timestamp.today()).normalize()
    # ★ 이 저장소의 listing 계열은 2026-03-08 부터만 존재한다. 그 이전 날짜로 물으면
    #   404 만 6번 찍히고(로그 오염) 시간도 버린다 — 애초에 시도하지 않는다.
    if str(kind).startswith("listing/krx") and base < ts(FDR_CACHE_LISTING_FROM):
        CON.debug(f"FDR 캐시 {kind}: {base:%Y-%m-%d} 은 저장소 시작일"
                  f"({FDR_CACHE_LISTING_FROM}) 이전 — 조회 생략")
        return None
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
_HK_HOME = "https://consensus.hankyung.com/"
# ★ 한경컨센서스는 라우트를 바꾼 이력이 있고(구 `/apps.analysis/analysis.list` →
#   신 `/analysis/list`), 앞단 WAF 가 '브라우저처럼 보이지 않는' 요청에 403 을 준다.
#   어느 쪽이 살아 있는지는 **실행 환경마다 다르다**(사내망/해외IP/데이터센터IP).
#   그래서 하드코딩하지 않고 실행 시점에 후보를 차례로 두드려 보고 고른다.
_HK_CANDIDATES = [
    ("신 라우트(https)", "https://consensus.hankyung.com/analysis/list",
     "https://consensus.hankyung.com/analysis/downpdf?report_idx={rid}"),
    ("구 라우트(https)", "https://consensus.hankyung.com/apps.analysis/analysis.list",
     "https://consensus.hankyung.com/apps.analysis/analysis.downpdf?report_idx={rid}"),
    ("구 라우트(http)", "http://consensus.hankyung.com/apps.analysis/analysis.list",
     "http://consensus.hankyung.com/apps.analysis/analysis.downpdf?report_idx={rid}"),
]
HK: Dict[str, Any] = {"name": _HK_CANDIDATES[0][0], "list": _HK_CANDIDATES[0][1],
                      "pdf": _HK_CANDIDATES[0][2], "probed": False, "alive": False}
_HK_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
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
    # ★ 첫 테이블을 그냥 집으면 상단 검색폼/배너 표를 잡는다. 오래 수집해 본 다른
    #   전략은 '작성일 + (제공출처|작성자)' 헤더로 표를 식별한다 — 그 규칙을 따른다.
    table = None
    for t in sp.find_all("table"):
        head = " ".join(th.get_text(strip=True) for th in t.find_all("th"))
        if "작성일" in head and ("제공출처" in head or "작성자" in head):
            table = t
            break
    table = table or sp.select_one("div.table_style01 table") or sp.find("table")
    if table is None:
        return []
    # 결과없음 페이지는 colspan 안내행 하나뿐이다 — 레이아웃 변경으로 오판하지 않는다
    body_txt = table.get_text(" ", strip=True)
    if "없습니다" in body_txt or "결과가 없" in body_txt:
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
        pdf = HK["pdf"].format(rid=rid) if rid else ""
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


def _hk_params(sdate: str, edate: str, page: int, n: int = 80) -> dict:
    # ★ report_type / search_report_type — 사이트가 이름을 바꾼 이력이 있어 둘 다 싣는다.
    #   서버는 모르는 파라미터를 무시하므로 부작용이 없고, 한 번의 요청으로 양쪽을 만족한다.
    return {"skinType": "business", "search_text": "", "pagenum": str(n),
            "sdate": sdate, "edate": edate, "now_page": str(page),
            "report_type": "CO", "search_report_type": "CO", "order_type": ""}


def _hk_block_state(save: Optional[dict] = None) -> Optional[dict]:
    """한경 차단 상태를 공용 인덱스에 영속화(다음 실행이 이어받는다)."""
    if DEPOT is None:
        return None
    fp = os.path.join(DEPOT.ns["공용"], "index", "hankyung_block.json")
    if save is not None:
        try:
            write_atomic_text(fp, json.dumps(save, ensure_ascii=False))
        except Exception:
            pass
        return save
    try:
        return json.loads(open(fp, encoding="utf-8").read())
    except Exception:
        return None


def hk_probe() -> bool:
    """한경컨센서스 진단 — '왜 수집이 안 되는가'를 추측하지 않고 **실측**해서 표로 보여준다.

    ★ 사용자 로그의 `수신 실패[hankyung] HTTP 403` 은 그 자체로는 원인이 아니다.
      403 을 만들 수 있는 원인은 최소 네 가지이고, 각각 처방이 다르다:
        ⓐ 라우트가 바뀌어 옛 경로가 죽음        → 후보 경로를 순회하면 해결
        ⓑ WAF 가 비브라우저 요청을 거부         → 브라우저 헤더 + 홈 워밍업 쿠키
        ⓒ 발신 IP 자체를 차단(데이터센터/해외)   → 어떤 헤더로도 안 됨. 캐시로 진행
        ⓓ 회사/기관 방화벽·프록시가 가로챔       → 본문에 안내문이 담겨 있어 구분 가능
      그래서 후보별 상태코드와 **본문 앞부분**까지 찍는다. 본문을 봐야 ⓒ와 ⓓ가 갈린다.
      진단은 `fetch` 를 쓰지 않는다(회로차단·스로틀에 영향을 주고받지 않기 위해).
    """
    if HK["probed"]:
        return bool(HK["alive"])
    HK["probed"] = True
    # ★ 차단 상태를 캐시에 남겨 둔다. 차단된 IP 를 매 실행 다시 두드리는 것은
    #   시간 낭비일 뿐 아니라 **차단 기간을 연장시키는 행동**이다.
    st = _hk_block_state()
    if st and st.get("until", 0) > time.time():
        left = (st["until"] - time.time()) / 60.0
        CON.warn(f"한경컨센서스: 직전 실행에서 IP 차단이 확인되어 쿨다운 중입니다 "
                 f"(약 {left:.0f}분 남음 · 사유: {str(st.get('why'))[:60]}). "
                 f"이번 실행은 두드리지 않고 캐시+네이버로 진행합니다 — "
                 f"차단을 더 길게 만들지 않기 위해서입니다.")
        CIRCUIT.open_now("hankyung", f"쿨다운 {left:.0f}분 남음")
        return False
    ed = _dt.date.today()
    sd = ed - _dt.timedelta(days=20)
    rows, winner = [], None

    warm, home_ok = "-", False
    try:                                    # ⓑ 대비: 홈을 먼저 열어 세션 쿠키를 받는다
        sc, hb, _e, nck = _probe_get(_HK_HOME, timeout=15)
        warm = f"HTTP {sc} · 쿠키 {nck}개"
        home_ok = (sc == 200)
        if not home_ok:
            # ★ 홈조차 막혔다면 목록 경로를 세 번 더 두드릴 이유가 없다.
            #   경로 문제가 아니라 **발신 IP 문제**임이 이 한 번으로 확정된다.
            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                                              decode_kr(hb, _e)[:400])).strip()[:70]
            rows.append(["홈(추가 시도 생략)", f"HTTP {sc}", f"{len(hb):,}B", "-",
                         body or "-"])
    except Exception as e:
        warm = f"실패({type(e).__name__})"

    for name, lurl, purl in (_HK_CANDIDATES if home_ok else []):
        try:
            sc, content, enc, _ = _probe_get(
                lurl, params=_hk_params(sd.isoformat(), ed.isoformat(), 1, 20),
                headers={"Referer": _HK_HOME}, timeout=20)
            text = decode_kr(content, enc)
            nrow = len(_hk_parse_page(text)) if sc == 200 else 0
            hint = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text[:4000])).strip()[:70]
            rows.append([name, f"HTTP {sc}", f"{len(content):,}B", f"{nrow}행",
                         hint or "-"])
            if sc == 200 and nrow > 0 and winner is None:
                winner = (name, lurl, purl)
        except Exception as e:
            rows.append([name, f"예외 {type(e).__name__}", "-", "-", str(e)[:70]])

    if winner:
        HK.update(name=winner[0], list=winner[1], pdf=winner[2], alive=True)
    CON.grid(rows + [["세션 워밍업(홈 방문)", warm, "-", "-",
                      "쿠키를 전역 씨앗에 심어 모든 워커 스레드가 공유합니다"]],
             ["후보 경로", "응답", "본문크기", "파싱행수", "본문/사유 앞부분"],
             ["l", "l", "r", "r", "l"],
             title="한경컨센서스 접속 진단 (실측 · 추측 아님)")
    if winner:
        CON.ok(f"한경컨센서스 사용 경로: {winner[0]} — {winner[1]}")
    else:
        why = next((r[4] for r in rows if r[4] and r[4] != "-"), "403/차단")
        _hk_block_state(save=dict(until=time.time() + HANKYUNG_COOLDOWN_MIN * 60,
                                  why=why, at=_now_iso()))
        CIRCUIT.open_now("hankyung",
                         "모든 후보 경로가 403/차단 — 발신 IP 또는 WAF 정책으로 판단")
        CON.warn("한경컨센서스 신규 수집을 건너뜁니다. 원인은 위 표의 본문에서 확인하세요. "
                 "▸ '허용되지 않은 접근/Forbidden' 계열이면 사이트 WAF 차단(해외·데이터센터 "
                 "IP 또는 자동화 탐지)이고, 회사 프록시 안내문이면 사내 방화벽입니다. "
                 "▸ 어느 쪽이든 **기존 드라이브 캐시 + 네이버리서치로 백테스트는 그대로 "
                 "진행됩니다** — 이 단계에서 멈추지 않습니다.")
    return bool(HK["alive"])


def _hk_collect_month(y: int, m: int) -> List[dict]:
    if not HK["alive"] or CIRCUIT.blocked("hankyung"):
        return []
    sdate, edate = f"{y}-{m:02d}-01", f"{y}-{m:02d}-{pd.Timestamp(y, m, 1).days_in_month:02d}"
    out, page, empty_streak = [], 1, 0
    while page <= 120 and empty_streak < 2:
        if CIRCUIT.blocked("hankyung"):
            break
        html = fetch(HK["list"], source="hankyung", referer=_HK_HOME,
                     headers=_HK_BROWSER_HEADERS,
                     params=_hk_params(sdate, edate, page))
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
        hk_probe()                       # ★ 먼저 진단하고 시작한다 — 막힌 곳을 두드리지 않는다
        months = pd.period_range(ts(start), ts(end), freq="M")
        cur = pd.Timestamp.today().to_period("M")
        todo = [p for p in months if (str(p) not in done_m) or (p >= cur - 1)]
        CON.say(f"리포트 신규 수집 대상: {len(todo)}개월 "
                f"(robots 제한 소스 — 사용자 지시에 따라 보수 속도로 수집) · "
                f"한경 {'사용' if HK['alive'] else '건너뜀'} · 네이버 사용")

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
_ENGINE = ""          # bench_pdf_engines 가 채운다(워커 모듈에는 리터럴로 박힌다)


def _pdf_text(data: bytes, max_pages: int = 3) -> str:
    """실측으로 고른 추출기를 먼저, 실패하면 나머지를 차례로."""
    for eng in dict.fromkeys([_ENGINE, "pymupdf", "pypdf", "pdfplumber"]):
        if not eng:
            continue
        try:
            t = _pdf_text_with(eng, data, max_pages)
        except Exception:
            continue
        if t and t.strip():
            return t
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


def h1_trail(*parts) -> str:
    """구분자를 **각 조각 뒤에 붙이는** 해시 — 다른 전략(TCD v2 계열)의 report_uid 규칙.

    ★ 이게 매칭률 2.4%(10,244건 중 249건)의 진짜 원인이었다. 내 h1 은 조각들을
      \x1e 로 **사이에** 이어 붙이는데, 저쪽은 \x1f 를 **마지막 조각 뒤에도** 붙인다.
      규칙이 한 글자 다르면 해시는 영원히 안 맞는다. 그래서 이미 디스크에 있는
      PDF 1만 건을 매 실행 다시 받고 있었다. 두 규칙을 모두 후보로 넣는다.
    """
    h = hashlib.sha1()
    for x in parts:
        h.update(str(x).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def _pdf_alias_from_master(roots: List[str]) -> Dict[str, str]:
    """다른 전략의 보고서 마스터에서 '(source,rid) → report_uid' 를 **읽어 온다**.

    ★ 해시 규칙을 재현하는 것보다 확실하다 — 저쪽이 직접 적어 둔 대응표를 쓰는 것이니
      규칙이 또 바뀌어도 안 깨진다. (research_report_master.parquet 계열)
    """
    out: Dict[str, str] = {}
    pats = ("research_report_master", "report_master", "reports_master")
    seen, t_lim = 0, time.time() + 60          # 대형 캐시에서 이 탐색이 병목이 되지 않게
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if time.time() > t_lim:
                break
            for fn in files:
                if not fn.endswith(".parquet") or not any(t in fn for t in pats):
                    continue
                try:
                    df = pd.read_parquet(os.path.join(dirpath, fn))
                except Exception:
                    continue
                cols = {str(c).lower(): c for c in df.columns}
                cu = cols.get("report_uid")
                cs, cr = cols.get("source"), cols.get("src_report_id") or cols.get("rid")
                if not (cu and cr):
                    continue
                seen += 1
                for u, sr, rr in zip(df[cu].astype(str),
                                     df[cs].astype(str) if cs else ["" ] * len(df),
                                     df[cr].astype(str)):
                    if not u or u == "nan":
                        continue
                    for b in [t for t in re.split(r"[+|,]", rr) if t]:
                        out.setdefault(b, u)
                        for a in [t for t in re.split(r"[+|,]", sr) if t]:
                            out.setdefault(f"{a}\x00{b}", u)
    if out:
        CON.ok(f"타 전략 보고서 마스터 {seen}개에서 '(소스,보고서번호) → 저장키' "
               f"대응 {len(out):,}건을 읽었습니다 — 해시 규칙 추측 없이 직접 대조합니다")
    return out


def _pdf_key_index() -> Dict[str, str]:
    """기존 캐시(내 것 + 다른 전략 것)의 '보고서키 → PDF 실제경로' 지도.

    ★ 이전 버전은 파일명(=내용해시)만 보고 참조등록해서, 정작 report_uid 로 찾을 때
      항상 미스가 났다. 그래서 이미 디스크에 있는 PDF 1만여 건을 매번 다시 받았다.
      해법은 인덱스 저널을 읽는 것이다 — 거기에 key(report_uid) → path 가 들어 있다.
    """
    idx: Dict[str, str] = {}
    # ★ 매칭률이 1%(10,119건 중 124건)에 그쳤던 이유: 저널의 key 는 그것을 저장한
    #   빌드/전략의 report_uid 해시라, 소스가 병합된 원장(예: 'hankyung+naver')에서
    #   다시 계산한 해시와 절대 같아지지 않는다. 그런데 같은 저널에는 **원본 URL**이
    #   source 로 남아 있고, 거기에는 보고서 번호가 그대로 들어 있다.
    #   → URL 질의문자열에서 번호를 뽑아 별칭 키로 심는다(원장의 rid 와 바로 맞는다).
    #   파일명은 내용해시라 숫자를 뽑으면 오매칭 위험이 있어 **쓰지 않는다**.
    #   한 번호가 서로 다른 파일 두 개를 가리키면 모호하므로 아예 버린다 —
    #   엉뚱한 PDF 에서 EPS 를 뽑는 것보다 못 찾는 편이 낫다.
    alias: Dict[str, set] = defaultdict(set)
    id_re = re.compile(r"(?:report_idx|report_id|nid|idx|no|seq)=(\d{3,})",
                       re.IGNORECASE)
    roots = [DEPOT.write_root] + list(DEPOT.read_roots)
    seen_files = 0
    t_walk = time.time()
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if time.time() - t_walk > 90:        # 대형 캐시에서 이 탐색이 병목이 되지 않게
                CON.warn("PDF 인덱스 탐색 90초 상한 도달 — 찾은 만큼만 재사용합니다")
                break
            for fn in files:
                if fn not in ("index.jsonl", "journal.jsonl", "common_index.jsonl",
                              "private_index.jsonl"):
                    continue
                seen_files += 1
                for rec in jsonl_read(os.path.join(dirpath, fn)):
                    if str(rec.get("fmt", "")).lower().lstrip(".") != "pdf":
                        continue
                    key = str(rec.get("key") or "").strip()
                    if not key:
                        continue
                    # ★ abs_path 는 **저장한 그 PC** 기준으로 박혀 있다(콜랩이면
                    #   /content/drive/... 이라 이 PC 엔 없다). 그래서 존재를 확인해
                    #   고르고, 없으면 캐시루트+상대경로로 되돌린다.
                    cands = []
                    rel = rec.get("path")
                    if rel:
                        rel = str(rel)
                        cands.append(rel if os.path.isabs(rel) else os.path.join(
                            os.path.dirname(os.path.dirname(dirpath)), rel))
                    if rec.get("abs_path"):
                        cands.append(str(rec["abs_path"]))
                    p = next((c for c in cands if os.path.exists(c)),
                             cands[0] if cands else "")
                    if not p:
                        continue
                    idx.setdefault(key, p)
                    for fld in ("source", "url", "src_url"):
                        for mm in id_re.finditer(str(rec.get(fld) or "")):
                            alias[mm.group(1)].add(p)
            if len(idx) > 400_000:
                break
    n_key = len(idx)
    n_alias = 0
    for rid, paths in alias.items():
        if len(paths) == 1 and rid not in idx:
            idx[rid] = next(iter(paths))
            n_alias += 1
    ambig = sum(1 for v in alias.values() if len(v) > 1)
    if idx:
        CON.ok(f"기존 인덱스에서 PDF {len(idx):,}건의 '보고서키 → 경로' 지도를 복원했습니다 "
               f"(저널 {seen_files}개 · 저장키 {n_key:,} + URL 번호 별칭 {n_alias:,}"
               + (f" · 모호해서 버림 {ambig:,}" if ambig else "")
               + ") — 이미 받은 PDF 는 다시 받지 않습니다")
    return idx


def _priority_by_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """같은 예산이면 **성과검증에 실제로 쓰이는 칸**부터 채운다.

    ★ SCG 는 (종목, 신호월)에 애널리스트가 **2명 이상**이라야 컨센서스가 성립한다(§31).
      1명뿐인 칸을 100건 받아 봐야 신호는 0개다. 그래서 같은 (종목,월)에 보고서가
      여러 건 있는 것부터 받는다 — 다운로드 1건당 '쓸 수 있는 신호'가 최대가 된다.
      전수수집이 끝나면 결과는 어차피 같고, 중간에 멈춰도 표본이 쓸모 있게 남는다.
    """
    if df is None or df.empty or "stock_code" not in df.columns:
        return df
    d = df.copy()
    d["_m"] = ts_col(d["date"]).dt.to_period("M").astype(str)
    grp = d.groupby(["stock_code", "_m"], observed=True)["rid"].transform("size")
    d["_cell"] = grp.fillna(1)
    # 칸 밀도 내림차순 → 같은 밀도면 날짜순(결정적)
    d = d.sort_values(["_cell", "date"], ascending=[False, True], kind="stable")
    return d.drop(columns=["_m", "_cell"], errors="ignore")


def _balanced_by_year(df: pd.DataFrame, cap: int, date_col: str = "date") -> pd.DataFrame:
    """연도별 균형 샘플 — 예산이 모자라도 10년이 고르게 채워지게 한다.

    ★ 앞에서부터 자르면 2016~2017 만 채워진 채 10년 백테스트를 하게 된다.
      연도마다 균등 간격으로 뽑고 라운드로빈으로 섞어, 어느 시점에 중단되든
      표본이 기간 전체에 퍼져 있도록 만든다(결정적 — 시드 불필요).
    """
    if df.empty or cap <= 0:
        return df.iloc[0:0]
    if len(df) <= cap:
        return _priority_by_coverage(df)
    w = df.copy()
    w["_y"] = ts_col(w[date_col]).dt.year.fillna(0).astype(int)
    years = [y for y in sorted(w["_y"].unique()) if y > 0]
    if not years:
        return w.sort_values(date_col, kind="stable").head(cap).drop(columns=["_y"])
    per = max(1, math.ceil(cap / len(years)))
    parts = []
    for y in years:
        g = _priority_by_coverage(w[w["_y"] == y])
        if g is None or not len(g):
            continue
        if len(g) > per:
            g = g.iloc[:per]          # 이미 '쓸모 순'으로 정렬돼 있다
        parts.append(g.reset_index(drop=True))
    out, i = [], 0
    while sum(len(p) for p in parts) > 0 and len(out) < cap:      # 라운드로빈 인터리브
        p = parts[i % len(parts)]
        if len(p):
            out.append(p.iloc[[0]])
            parts[i % len(parts)] = p.iloc[1:]
        i += 1
        if i > cap * 4 + len(parts) * 2:
            break
    res = pd.concat(out, ignore_index=True) if out else w.head(cap)
    return res.head(cap).drop(columns=["_y"], errors="ignore")


# PDF 처리 결과의 '종결' 상태 — 이 상태는 파서 버전이 같은 한 다시 시도하지 않는다.
# (일시적 실패는 여기 없다: 다음 실행에서 자연히 재시도된다)
PDF_TERMINAL = frozenset({"EPS_OK", "NO_EPS_TABLE", "NO_TEXT_LAYER", "NOT_PDF", "NO_URL"})
PDF_PARSER_VERSION = "SCG_EPS_V2"


PDF_CHUNK = 40          # 체크포인트 단위. 500이면 첫 줄까지 몇 분 — 그게 '멈춤'으로 보였다


def _pdf_stage_minutes() -> float:
    """이 단계에 줄 시간(분). 자동이면 **남은 수집예산에서 백테스트 몫만 떼고 전부**.

    ★ 고정 60분은 4시간 예산 중 1시간만 쓰고 3시간을 놀렸다. 전수(53,658건)까지
      필요한 실행 횟수가 그만큼 늘어난다. 시간을 남기는 게 목적이 아니라,
      '백테스트가 반드시 돌 시간'만 지키는 게 목적이다.
    """
    if PDF_STAGE_BUDGET_MIN > 0:
        return float(PDF_STAGE_BUDGET_MIN)
    left = DEADLINE.remaining_s() / 60.0
    return float(max(5.0, left - BACKTEST_RESERVE_MIN))


PDF_CHECKPOINT_SEC = 120        # 체크포인트 간격(초). 청크마다 저장하면 O(n²) 가 된다


def _pdf_checkpoint(done: Dict[str, dict], status_rows: List[dict]):
    """진행분 영속화 — 중단돼도 여기까지는 남고, 다음 실행이 이어받는다."""
    try:
        DEPOT.table_save("scg_pdf_extract", pd.DataFrame(list(done.values())),
                         scope="공용", domain="research", source="pdf_parse")
        DEPOT.table_save("scg_pdf_status",
                         pd.DataFrame(status_rows).drop_duplicates("ruid", keep="last"),
                         scope="공용", domain="research", source="pdf_status")
    except Exception as e:
        CON.warn(f"PDF 진행분 저장 실패({type(e).__name__}) — 추출은 계속합니다")


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return b""


def _eta_report(done_n: int, total: int, t0: float, stage_end: float):
    """★ 계획표의 ETA 는 네트워크 속도만 보고 계산해서 20배 틀렸다(13분 → 실측 260분).
    파싱이 병목이면 네트워크 산수는 의미가 없다. 그래서 **실측 속도로 다시 계산**해
    한 번 더 알려준다 — 사용자가 '이 실행에서 어디까지 가는지' 알 수 있게."""
    done_n = min(done_n, total)
    el = time.time() - t0
    if done_n < 40 or el < 20:
        return
    rate = done_n / el                                   # 건/초 (실측)
    left_budget = max(0.0, stage_end - time.time())
    reach = min(total, done_n + int(rate * left_budget))
    if getattr(_eta_report, "_last", -1) == reach:
        return
    _eta_report._last = reach                            # type: ignore[attr-defined]
    CON.say(f"  ↳ 실측 {rate*60:.0f}건/분 → 이번 예산 안에 약 {reach:,}/{total:,}건 "
            f"({reach/max(total,1)*100:.0f}%) 처리 예상 · 전체 완주엔 "
            f"{total/max(rate,1e-9)/3600:.1f}시간 필요")


def _pdf_src(url) -> str:
    """★ 목록 조회와 **다른 소스명**을 쓴다. PDF 는 정적 파일이라 속도 상한이 다르고,
    목록이 막혔다고 PDF 까지 못 받는 것도 아니다(그 반대도 마찬가지). 회로차단도 따로 돈다."""
    u = str(url or "")
    return ("hankyung_pdf" if "hankyung" in u else
            ("naver_pdf" if "naver" in u else "generic"))


_PDF_URL_REWRITE: List[Tuple[str, str]] = []
_HK_PDF_ROUTES = ("/analysis/downpdf", "/apps.analysis/analysis.downpdf")


def pdf_url_fix(u) -> str:
    """캐시에 남은 옛 경로를 살아 있는 경로로 바꿔 준다.

    ★ 드라이브 캐시의 원장 5만여 건은 **예전 빌드가 만든 URL**을 그대로 갖고 있다.
      사이트가 라우트를 바꾸면 그 URL 은 전부 죽는데, 원장을 다시 만들 수는 없다
      (수집을 처음부터 다시 하라는 뜻이 된다). 그래서 다운로드 직전에 치환한다.
    """
    s = str(u or "")
    for a, b in _PDF_URL_REWRITE:
        if a in s:
            s = s.replace(a, b)
    return s


def _pdf_alt_urls(u: str) -> List[Tuple[str, str, str]]:
    """같은 문서를 가리키는 다른 경로 후보 — (옛조각, 새조각, 치환된 URL)."""
    out: List[Tuple[str, str, str]] = []
    for a in _HK_PDF_ROUTES:
        if a in u:
            for b in _HK_PDF_ROUTES:
                if b != a:
                    out.append((a, b, u.replace(a, b)))
    return out


def _pdf_preflight(work_net: Optional[pd.DataFrame]) -> Dict[str, bool]:
    """호스트별로 최대 3건만 실제로 받아 보고 '살아 있는지'를 판정한다.

    ★ 개별 문서가 지워져 404 인 경우와 호스트 자체가 막힌 경우를 구분해야 한다.
      그래서 1건이 아니라 3건까지 본다(3건 연속 실패면 개별 사정이 아니다).
      여기서 3~6초를 쓰는 대신 뒤에서 60분을 아낀다.
      전부 실패하면 포기하기 전에 **다른 라우트**로 한 번 더 확인한다 —
      캐시에 남은 옛 URL 때문에 멀쩡한 소스를 죽은 것으로 오판하지 않기 위해서다.
    """
    out: Dict[str, bool] = {}
    if work_net is None or not len(work_net):
        return out
    for src, g in work_net.groupby(work_net["pdf_url"].map(_pdf_src)):
        src = str(src)
        if CIRCUIT.blocked(src):
            out[src] = False
            continue
        ref = _HK_HOME if src.startswith("hankyung") else None
        sample = [str(x) for x in g["pdf_url"].head(3)]
        ok = False
        for u in sample:
            b = fetch(pdf_url_fix(u), source=src, as_bytes=True, tries=1, timeout=20,
                      referer=ref)
            if b and b[:5].startswith(b"%PDF"):
                ok = True
                break
        if not ok:                                  # 라우트 교차 재확인
            for u in sample:
                for a, bb, alt in _pdf_alt_urls(u):
                    d = fetch(alt, source=src, as_bytes=True, tries=1, timeout=20,
                              referer=ref)
                    if d and d[:5].startswith(b"%PDF"):
                        if (a, bb) not in _PDF_URL_REWRITE:
                            _PDF_URL_REWRITE.append((a, bb))
                        CON.ok(f"PDF 경로 치환 발견: '{a}' → '{bb}' — 캐시에 남은 옛 "
                               f"URL 을 살아 있는 경로로 바꿔 내려받습니다")
                        ok = True
                        break
                if ok:
                    break
        out[src] = ok
        if not ok:
            CIRCUIT.open_now(src, "PDF 사전점검 3건 연속 실패(대체 경로 포함)")
    return out


def _pdf_extract_one(data: bytes, year: int) -> Tuple[str, dict]:
    """단일 PDF → (상태, 추출결과). 상태는 재개 원장에 그대로 쓰인다."""
    if not data or not data[:5].startswith(b"%PDF"):
        return "NOT_PDF", {}
    text = _pdf_text(data)
    if not text or len(text.strip()) < 40:
        return "NO_TEXT_LAYER", {}
    eps = _eps_from_text(text, int(year))
    an = ",".join(dict.fromkeys(_ANALYST_TOK.findall(text[:2500])))[:80]
    payload = dict(pdf_analysts=an, eps_json=json.dumps(eps, ensure_ascii=False))
    return ("EPS_OK" if eps else "NO_EPS_TABLE"), payload


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║ PDF 파싱 가속 — 진짜 병목은 네트워크가 아니라 **CPU + GIL** 이었다                        ║
# ║                                                                                          ║
# ║  ★ 실측(사용자 로그): 병렬 6 으로 돌렸는데 24건/분. 6,249건에 260분, 전체 53,658건이면    ║
# ║    37시간이다. 원인을 분해하면 두 겹이다:                                                 ║
# ║      ⓐ `pmap` 은 **스레드**다. PDF 파싱은 순수 CPU 작업이라 GIL 이 직렬화한다.            ║
# ║         16코어 장비에서 사실상 1코어만 쓰고 있었다.                                       ║
# ║      ⓑ pdfplumber 는 문자 단위 레이아웃 객체를 전부 만든다 — 우리는 'EPS' 한 줄만          ║
# ║         찾으면 되는데 가장 비싼 방식으로 읽고 있었다. pymupdf 는 py3.14 휠이 없어 ImportError. ║
# ║  그래서 ① 추출기를 실측해서 빠른 것을 고르고 ② 파싱을 **프로세스 풀**로 내보낸다.          ║
# ║  프로세스 풀은 Jupyter(Windows spawn)에서 잘 깨지므로, 워커 모듈을 런타임에 파일로 써서    ║
# ║  import 가능하게 만들고 **자가시험 후 실패하면 스레드로 조용히 되돌아간다**.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
_PDF_ENGINE: Dict[str, Any] = {"name": "", "rate": 0.0, "measured": False, "table": []}
_PDF_POOL: Dict[str, Any] = {"ex": None, "mode": "", "checked": False,
                             "fn": None, "why": ""}


def _pdf_worker_source() -> str:
    """워커 모듈 소스를 **현재 함수들의 실제 소스에서** 생성한다.
    ★ 손으로 복제하면 본체와 워커가 서서히 갈라진다(그 자체가 다음 사고다).
      inspect 로 뽑아 쓰면 파서 로직의 단일 원천이 유지된다."""
    import inspect
    parts = ["# 자동 생성 — SCG PDF 파싱 워커 (수정 금지: 본체에서 재생성됨)",
             "import re, io, os, json",
             # ★ 본체 함수는 타입 주석을 쓴다(Dict/List/Tuple/Optional). 이걸 빼먹어
             #   워커 import 가 NameError 로 죽었고, 자가시험이 그걸 잡아 스레드로
             #   되돌아갔다 — 안전망은 동작했지만 병렬화 이득은 0이었다.
             "from typing import Any, Callable, Dict, List, Optional, "
             "Sequence, Tuple"]
    for mod, alias in (("fitz", "_fitz"), ("pdfplumber", "_pdfplumber"),
                       ("pypdf", "_pypdf")):
        parts.append(f"try:\n    import {mod} as {alias}\nexcept BaseException:\n"
                     f"    {alias} = None")
    parts.append(f"_ENGINE = {json.dumps(_PDF_ENGINE.get('name') or '')}")
    for name in ("_NUM_TOK", "_ANALYST_TOK", "_YEAR_HDR", "_EPS_LINE"):
        parts.append(f"{name} = re.compile({globals()[name].pattern!r}, "
                     f"{globals()[name].flags})")
    for fn in (_pdf_text_with, _pdf_text, _eps_from_text, _pdf_extract_one):
        parts.append(inspect.getsource(fn))
    parts.append(
        "def work(job):\n"
        "    path, year = job\n"
        "    try:\n"
        "        with open(path, 'rb') as f:\n"
        "            data = f.read()\n"
        "    except Exception:\n"
        "        return ('READ_FAIL', {})\n"
        "    return _pdf_extract_one(data, year)\n")
    parts.append("def selftest():\n    return 'ok'\n")
    # ★ 워커를 '실제로 여러 개' 띄워 보기 위한 함수. 풀은 게을러서 작업이 밀려야
    #   프로세스를 늘리는데, 우리는 __main__ 을 중화해 둔 **지금** 전부 띄워야 한다.
    parts.append("import time as _t, os as _o\n"
                 "def spin(_x=0):\n    _t.sleep(0.25)\n    return _o.getpid()\n")
    return "\n\n".join(parts)


_MAIN_SHIELD: Dict[str, Any] = {}


def _pdf_pool_close():
    """풀을 정리하고 상태를 초기화한다(유휴 워커가 남지 않게)."""
    ex = _PDF_POOL.get("ex")
    if ex is not None:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
    _PDF_POOL.update(ex=None, fn=None, checked=False)


def _pdf_main_shield(on: bool):
    """spawn 자식이 부모 __main__ 을 재실행하지 않도록 잠시 가린다(복구 보장)."""
    mm = sys.modules.get("__main__")
    if mm is None:
        return
    if on:
        # ★ __file__ 은 **지운다**(있으면 자식이 그 파일을 다시 실행한다).
        #   __spec__ 은 **None 으로 둔다** — multiprocessing 이 이 속성을 무조건
        #   읽으므로 지워 버리면 AttributeError 로 풀 생성 자체가 실패한다.
        #   (실제로 지웠다가 이 오류를 냈다. 둘의 취급이 다르다.)
        if hasattr(mm, "__file__"):
            _MAIN_SHIELD["__file__"] = mm.__file__
            try:
                del mm.__file__
            except Exception:
                _MAIN_SHIELD.pop("__file__", None)
        _MAIN_SHIELD["__spec__"] = getattr(mm, "__spec__", None)
        try:
            mm.__spec__ = None
        except Exception:
            _MAIN_SHIELD.pop("__spec__", None)
    else:
        for a, v in list(_MAIN_SHIELD.items()):
            try:
                setattr(mm, a, v)
            except Exception:
                pass
        _MAIN_SHIELD.clear()


def _pdf_pool(workers: int):
    """프로세스 풀을 만들되 **반드시 자가시험을 통과한 것만** 돌려준다.
    실패하면 None → 호출부가 스레드로 진행한다(느릴 뿐, 멈추지 않는다).

    ★ 사용자 환경(Windows + JupyterLab + py3.14)에서 `BrokenProcessPool` 로 죽어
      지난 라운드의 병렬화 이득이 통째로 0이 됐다. 원인은 spawn 방식의 구조다:
        · 윈도우는 fork 가 없어 자식이 **새 인터프리터로 시작**한다.
        · 자식은 부모가 넘긴 함수를 pickle 로 복원하는데, 그 함수가 `__main__` 에
          정의돼 있으면 `__main__` 을 import 하려 한다. Jupyter 커널에는 import
          가능한 `__main__` 파일이 없다 → 자식이 즉시 죽고 BrokenProcessPool.
        · `initializer` 로 sys.path 를 심으려 해도, 그 initializer 자체를 복원하려면
          이미 경로가 필요하다 — 순환이라 해결이 안 된다.
      그래서 ① 넘기는 함수는 **생성된 워커 모듈의 top-level 함수**만 쓰고,
      ② 자식이 그 모듈을 찾도록 **PYTHONPATH 환경변수**로 경로를 물려준다
      (spawn 자식은 부모 환경을 상속하고, 인터프리터가 기동하며 sys.path 에 넣는다).
    """
    if _PDF_POOL["checked"]:
        return _PDF_POOL["ex"]
    _PDF_POOL["checked"] = True
    ex = None
    if workers < 2:
        _PDF_POOL["mode"] = "스레드(워커 부족)"
        return None
    try:
        import multiprocessing as _mp
        from concurrent.futures import ProcessPoolExecutor
        d = os.path.join(tempfile.gettempdir(), f"scg_pdfw_{os.getpid()}")
        os.makedirs(d, exist_ok=True)
        write_atomic_text(os.path.join(d, "scg_pdf_worker.py"), _pdf_worker_source())
        if d not in sys.path:
            sys.path.insert(0, d)
        # ★ 자식이 워커 모듈을 import 할 수 있도록 경로를 환경변수로 물려준다.
        pp = os.environ.get("PYTHONPATH", "")
        if d not in pp.split(os.pathsep):
            os.environ["PYTHONPATH"] = (d + os.pathsep + pp) if pp else d
        import importlib
        w = importlib.import_module("scg_pdf_worker")
        importlib.reload(w)
        try:
            ctx = _mp.get_context("spawn")     # 모든 OS 에서 동일하게 동작시킨다
        except Exception:
            ctx = None
        # ★★ 여기가 BrokenProcessPool 의 진짜 원인이다.
        #    spawn 자식은 기동 직후 **부모의 __main__ 을 다시 실행**한다
        #    (multiprocessing.spawn._fixup_main_from_path). 그런데 Jupyter 의
        #    __main__ 은 디스크에 없는 가짜 경로라 자식이 즉시 죽는다
        #    → "A process in the process pool was terminated abruptly".
        #    __main__ 의 __file__/__spec__ 을 잠시 치우면 자식은 main 재실행을
        #    아예 건너뛰고, PYTHONPATH 로 워커 모듈만 import 한다(기동도 훨씬 빠르다).
        #    치운 상태에서 워커를 **전부 미리 띄워** 두고 원상복구한다 —
        #    나중에 게으르게 늘어나는 워커가 같은 함정에 빠지지 않게.
        _pdf_main_shield(True)
        try:
            ex = (ProcessPoolExecutor(max_workers=workers, mp_context=ctx)
                  if ctx is not None else ProcessPoolExecutor(max_workers=workers))
            # 넘기는 것은 모듈의 top-level 함수다 — 'scg_pdf_worker.selftest' 로
            # pickle 되고, 자식은 PYTHONPATH 덕에 그 모듈을 찾는다.
            if ex.submit(w.selftest).result(timeout=120) != "ok":
                raise RuntimeError("자가시험 응답 불일치")
            pids = set(ex.map(w.spin, range(workers * 2)))
        finally:
            _pdf_main_shield(False)
        _PDF_POOL["ex"] = ex
        _PDF_POOL["mode"] = f"프로세스×{workers}(실기동 {len(pids)})"
        _PDF_POOL["fn"] = w.work
        return ex
    except BaseException as e:
        why = f"{type(e).__name__}: {str(e)[:60]}"
        _PDF_POOL["mode"] = f"스레드(프로세스풀 불가 · {why})"
        _PDF_POOL["why"] = why
        try:
            if ex is not None:
                ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        return None


def bench_pdf_engines(samples: List[bytes]) -> str:
    """가용 추출기를 **실측**해서 가장 빠른 것을 고른다.

    ★ 어느 라이브러리가 빠른지 내가 이 환경에서 확인할 수 없다(여기엔 PDF 라이브러리가
      하나도 없다). 그러니 추측해서 하드코딩하는 대신 사용자 장비에서 재보고 고른다.
      같은 이유로 결과를 표로 찍는다 — 왜 그걸 골랐는지 보이게.
    """
    if _PDF_ENGINE["measured"]:
        return str(_PDF_ENGINE["name"])
    _PDF_ENGINE["measured"] = True
    cand = [(n, m) for n, m in (("pymupdf", _fitz), ("pypdf", _pypdf),
                                ("pdfplumber", _pdfplumber)) if m is not None]
    use = [s for s in samples if s and s[:5].startswith(b"%PDF")][:4]
    rows, best, best_rate = [], "", 0.0
    for name, _m in cand:
        if not use:
            rows.append([name, "가용", "-", "-"])
            continue
        t0, chars, okn = time.time(), 0, 0
        for s in use:
            try:
                t = _pdf_text_with(name, s)
            except Exception:
                t = ""
            chars += len(t or "")
            okn += 1 if (t and len(t.strip()) >= 40) else 0
        el = max(time.time() - t0, 1e-6)
        rate = len(use) / el
        rows.append([name, "가용", f"{rate:.1f}건/초", f"{okn}/{len(use)}건 성공"])
        if okn and rate > best_rate:
            best, best_rate = name, rate
    for name in ("pymupdf", "pypdf", "pdfplumber"):
        if not any(r[0] == name for r in rows):
            rows.append([name, "없음", "-",
                         "pip install " + ("pymupdf" if name == "pymupdf" else name)])
    _PDF_ENGINE.update(name=best, rate=best_rate, table=rows)
    return best


def _pdf_text_with(engine: str, data: bytes, max_pages: int = 3) -> str:
    """추출기 하나를 지정해서 텍스트만 뽑는다(벤치·워커 공용)."""
    if not data or not data[:5].startswith(b"%PDF"):
        return ""
    if engine == "pymupdf" and _fitz is not None:
        doc = _fitz.open(stream=data, filetype="pdf")
        try:
            return "\n".join(doc[i].get_text()
                             for i in range(min(max_pages, doc.page_count)))
        finally:
            doc.close()
    if engine == "pypdf" and _pypdf is not None:
        rd = _pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((rd.pages[i].extract_text() or "")
                         for i in range(min(max_pages, len(rd.pages))))
    if engine == "pdfplumber" and _pdfplumber is not None:
        with _pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages[:max_pages])
    return ""


def enrich_with_pdf(rep: pd.DataFrame) -> pd.DataFrame:
    """PDF 에서 (a) 작성자(네이버 건 보강) (b) EPS 추정치를 추출해 원장에 붙인다.

    ★ 이 단계는 예전에 파이프라인 전체를 삼켰다(대상 53,658건 → 4시간 예산 소진).
      세 가지로 바로잡는다:
        ① **단계 예산** — 이 단계가 쓸 수 있는 시간을 따로 못박는다.
        ② **종결 원장** — EPS 표가 없는 PDF 등은 '종결'로 기록해 다시 열지 않는다.
           이게 없으면 매 실행이 같은 파일을 다시 파싱해 영원히 수렴하지 않는다.
        ③ **연도 균형 + 재개** — 상한만큼만 하되 10년에 고르게 퍼뜨리고,
           다음 실행이 남은 것을 이어받는다.
    """
    rep = rep.copy()
    rep["ruid"] = pd.Series([h1(s, r) for s, r in zip(rep["source"], rep["rid"])],
                            index=rep.index, dtype="object")

    ex = DEPOT.table_load("scg_pdf_extract", need_cols=["ruid"])
    done: Dict[str, dict] = {}
    if ex is not None and len(ex):
        for r in ex.to_dict("records"):
            done[str(r.get("ruid"))] = r
        CON.say(f"PDF 추출 캐시 재사용 {len(done):,}건")

    st = DEPOT.table_load("scg_pdf_status", need_cols=["ruid", "status"])
    settled: set = set()
    if st is not None and len(st):
        if "parser_version" not in st.columns:
            st["parser_version"] = PDF_PARSER_VERSION
        m = (st["parser_version"].astype(str) == PDF_PARSER_VERSION) & \
            st["status"].astype(str).isin(PDF_TERMINAL)
        settled = set(st.loc[m, "ruid"].astype(str))
        CON.say(f"PDF 종결 원장 {len(settled):,}건 — 같은 파서 버전에서는 다시 열지 않습니다")
    status_rows: List[dict] = [] if st is None else st.to_dict("records")

    has_url = rep["pdf_url"].astype(str).str.startswith("http")
    need = rep[has_url & ~rep["ruid"].isin(settled) & ~rep["ruid"].isin(done.keys())]

    if not (RESEARCH_DOWNLOAD_PDF and RUN_MODE != "CACHED") or not len(need):
        return _attach_pdf_columns(rep, done)

    keymap = _pdf_key_index()                       # 이미 가진 PDF 재사용

    def _alt_keys(src: str, rid: str) -> List[str]:
        """★ 캐시에서 온 원장은 소스가 병합돼 있다(예: 'hankyung+naver', rid='12|34').
        그 상태의 해시는 원래 저장 시점의 report_uid 와 다르므로 그냥 조회하면
        영구 미스가 난다(실제로 이미 받은 PDF 1만여 건을 매번 다시 받았다).
        그래서 분해한 조합까지 후보로 넣어 맞춰 본다."""
        out = [h1(src, rid), h1_trail(src, rid), str(rid)]
        toks_s = [t for t in re.split(r"[+|,]", str(src)) if t]
        toks_r = [t for t in re.split(r"[+|,]", str(rid)) if t]
        pair_uids = []
        for a in toks_s:
            for b in toks_r:
                out.append(h1(a, b))
                out.append(h1_trail(a, b))        # 다른 전략의 규칙(구분자·후행)
                out.append(b)
                pair_uids.append(h1_trail(a, b))
                u = master_map.get(f"{a}\x00{b}") or master_map.get(b)
                if u:
                    out.append(u)                 # 저쪽이 직접 적어 둔 저장키
        if pair_uids:
            out.append(min(pair_uids))            # 병합행은 min(uid) 로 저장된다
        return list(dict.fromkeys(out))

    master_map = _pdf_alias_from_master([DEPOT.write_root] + list(DEPOT.read_roots))
    alt_map: Dict[str, str] = {}
    for _rid, _src, _u in zip(need["rid"], need["source"], need["ruid"]):
        for k in _alt_keys(_src, _rid):
            p_hit = keymap.get(str(k))
            if p_hit:
                alt_map[str(_u)] = p_hit
                break
    if alt_map:
        keymap.update(alt_map)
        CON.ok(f"보고서키 정규화로 기존 PDF {len(alt_map):,}건을 추가로 매칭했습니다 "
               f"(병합 원장의 source/rid 분해 대조)")
    local_hit = need["ruid"].map(lambda k: keymap.get(str(k)) is not None)

    cap = PDF_MAX_NEW_PER_RUN if PDF_MAX_NEW_PER_RUN > 0 else len(need)
    # 로컬에 이미 있는 건 네트워크 상한과 무관하게 전부 처리한다(공짜다)
    work_local = need[local_hit.to_numpy()]
    work_net = _balanced_by_year(need[~local_hit.to_numpy()], cap)
    # ★ 다운로드가 필요한 건은 **먼저 호스트가 살아 있는지 1건씩 실측**하고 시작한다.
    #   막힌 호스트를 6,000번 두드리는 게 '멈춘 것처럼 보이던' 진짜 원인이었다.
    alive = _pdf_preflight(work_net)
    if work_net is not None and len(work_net):
        keep = work_net["pdf_url"].map(lambda u: alive.get(_pdf_src(u), True))
        dropped = int((~keep).sum())
        if dropped:
            CON.warn(f"PDF 신규 다운로드 {dropped:,}건은 호스트가 막혀 있어 계획에서 뺐습니다 "
                     f"(시도해도 전부 실패하며 시간만 소모합니다). "
                     f"차단 해제 후 재실행하면 그대로 이어받습니다.")
        work_net = work_net[keep.to_numpy()]
    work = pd.concat([work_local, work_net], ignore_index=True)   # 로컬 먼저 → 즉시 성과
    stage_min = _pdf_stage_minutes()
    stage_end = time.time() + stage_min * 60
    # ★ 예상 소요를 **먼저** 보여준다. 속도 상한은 전역이라 스레드 수와 무관하고,
    #   이 산수를 안 보여준 탓에 사용자는 '멈췄다'고 볼 수밖에 없었다.
    qps_eff = sum(THROTTLE.qps(s) for s, v in alive.items() if v) or 1.0
    eta_min = len(work_net) / qps_eff / 60.0 + len(work_local) / 600.0
    reach = min(len(work), int((len(work_local) + qps_eff * stage_min * 60)))
    CON.grid([["기존 파일 재사용", f"{len(work_local):,}건", "네트워크 0회 — 먼저 처리합니다"],
              ["신규 다운로드", f"{len(work_net):,}건",
               f"연도 균형 샘플 (전체 대상 {len(need):,}건 중)"],
              ["호스트 사전점검", ", ".join(f"{k}={'OK' if v else '차단'}"
                                            for k, v in alive.items()) or "대상 없음",
               "1건씩 실측 후 결정 (막힌 곳에는 시간을 쓰지 않습니다)"],
              ["속도 상한", f"{qps_eff:.1f}건/초",
               "전역 상한 — 스레드를 늘려도 이 값을 못 넘습니다(차단 방지)"],
              ["예상 소요", f"{eta_min:.0f}분",
               f"이번 예산({stage_min:.0f}분) 안에 약 {reach:,}건 처리 예상"],
              ["단계 예산", f"{stage_min:.0f}분"
                            + ("(자동)" if PDF_STAGE_BUDGET_MIN <= 0 else ""),
               f"남은 수집예산 − 백테스트 유보 {BACKTEST_RESERVE_MIN}분"
               if PDF_STAGE_BUDGET_MIN <= 0 else "고정값"]],
             ["PDF 처리 계획", "규모", "비고"], ["l", "r", "l"],
             title="PDF 추출 계획 (재개 가능 · 종결 원장 기반)")
    if _fitz is None and _pdfplumber is not None:
        CON.warn("PDF 파서가 2순위(pdfplumber)뿐입니다 — 1순위(pymupdf)보다 몇 배 느립니다. "
                 "`pip install pymupdf` 후 재실행하면 같은 예산으로 훨씬 많이 처리합니다.")
    if len(need) > len(work):
        CON.say(f"남는 {len(need) - len(work):,}건은 다음 실행이 이어받습니다 — "
                f"전체를 채우려면 이 속도로 약 "
                f"{len(need)/max(qps_eff,0.1)/3600:.1f}시간(누적)이 필요합니다. "
                f"그동안에도 빠른판(TP12M) 백테스트는 매 실행마다 완결됩니다.")

    lock = threading.Lock()
    counter = {"n": 0, "new": 0, "hit": 0, "net": 0, "fail": 0}
    t0 = time.time()
    ck = {"t": time.time()}

    def _tick(total: int, phase: str = ""):
        """★ 진행 한 줄을 **처리 도중에도** 찍는다. 예전에는 500건 청크가 끝나야
          첫 줄이 나와서, 실제로는 돌고 있는데도 화면이 몇 분간 멈춰 보였다."""
        c = (counter["n"] if phase == "파싱" else
             counter["hit"] + counter["net"] + counter["fail"])
        if c % PDF_PROGRESS_EVERY or not c:
            return
        el = max(time.time() - t0, 1e-9)
        CON.say(f"  PDF[{phase or '진행'}] {c:,}/{total:,} · EPS추출 "
                f"{counter['new']:,} · 기존파일 {counter['hit']:,} · 신규 "
                f"{counter['net']:,} · 실패 {counter['fail']:,} · "
                f"{c/el*60:.0f}건/분 · 잔여예산 "
                f"{max(0, stage_end - time.time())/60:.0f}분")

    def _acquire(row):
        """[1단계] **확보만** 한다 — 로컬 재사용 또는 다운로드. IO 라 스레드가 맞다.
        반환: (ruid, 로컬경로 or None, 연도, 상태or None)"""
        ruid, url, y, total = row
        if time.time() > stage_end or DEADLINE.over("PDF 확보"):
            return None
        p = keymap.get(str(ruid))
        if p and os.path.exists(p):
            with lock:
                counter["hit"] += 1
                _tick(total, "확보")
            return (ruid, p, y, None)
        p = DEPOT.blob_path("research_pdf", ruid)
        if p and os.path.exists(p):
            with lock:
                counter["hit"] += 1
                _tick(total, "확보")
            return (ruid, p, y, None)
        src = _pdf_src(url)
        if CIRCUIT.blocked(src):                        # 즉시 반환 — 대기 0초
            with lock:
                counter["fail"] += 1
                _tick(total, "확보")
            return (ruid, None, y, "DOWNLOAD_FAIL")
        data = fetch(pdf_url_fix(url), source=src, as_bytes=True, tries=2,
                     referer=_HK_HOME if src.startswith("hankyung") else None)
        if not (data and data[:5].startswith(b"%PDF")):
            with lock:
                counter["fail"] += 1
                _tick(total, "확보")
            return (ruid, None, y, "DOWNLOAD_FAIL")     # 비종결 — 다음 실행에서 재시도
        DEPOT.blob_save("research_pdf", ruid, data, "pdf", source=str(url))
        np_ = DEPOT.blob_path("research_pdf", ruid)
        with lock:
            counter["net"] += 1
            _tick(total, "확보")
        return (ruid, np_ if (np_ and os.path.exists(np_)) else None, y,
                None if np_ else "DOWNLOAD_FAIL")

    n_jobs = len(work)
    jobs = list(zip(work["ruid"], work["pdf_url"],
                    ts_col(work["date"]).dt.year.fillna(2020).astype(int),
                    [n_jobs] * n_jobs))
    if not n_jobs:
        CON.say("PDF 처리 대상이 없습니다 — 이 단계를 건너뜁니다")
        return _attach_pdf_columns(rep, done)

    # ── 추출기 실측 → 파싱 병렬화 방식 결정 ──────────────────────────────────
    #  ★ 여기가 이번 개편의 핵심이다. 이전 빌드는 다운로드와 파싱을 한 스레드풀에
    #    섞어 돌렸다. 파싱은 순수 CPU 라 GIL 이 직렬화하므로 16코어에서 24건/분이
    #    나왔다(6,249건에 260분). 확보(IO)와 파싱(CPU)을 분리하고 파싱을 프로세스로
    #    내보내면 코어 수만큼 실제로 병렬이 된다.
    # ★ 추출기 실측은 **파일이 실제로 손에 들어온 뒤**에 한다.
    #   이전 빌드는 '이미 로컬에 있는 파일'만 표본으로 삼았는데, 신규 다운로드만
    #   있는 실행에서는 표본이 0개라 벤치가 통째로 건너뛰어졌다("선택: 없음").
    #   그러면 실측이 아니라 고정 순서로 돌아가 이 개선의 의미가 사라진다.
    n_par = PDF_PARSE_WORKERS or max(2, min(12, (RIG["cpu"] or 4) - 2))
    pool = _pdf_pool(n_par) if PDF_PARSE_PROCESSES else None
    CON.say(f"PDF 처리를 시작합니다 — {n_jobs:,}건 · 확보(IO) 스레드 "
            f"{min(6, N_IO_THREADS)} · 파싱(CPU) {_PDF_POOL['mode'] or f'스레드×{n_par}'}"
            f" · {PDF_PROGRESS_EVERY}건마다 진행 표시 · 체크포인트 {PDF_CHUNK}건")

    def _parse_batch(items: List[tuple]) -> List[tuple]:
        """[2단계] 파싱 — CPU 바운드. 프로세스 풀이 살아 있으면 그쪽으로."""
        nonlocal pool
        if not items:
            return []
        pj = [(pth, int(y)) for _r, pth, y, _st in items]
        if not _PDF_ENGINE["measured"]:            # 첫 배치의 실물 파일로 실측
            smp = []
            for q, _y in pj[:4]:
                b = _read_bytes(q)
                if b:
                    smp.append(b)
            eng = bench_pdf_engines(smp)
            globals()["_ENGINE"] = eng
            if _PDF_ENGINE["table"]:
                CON.grid(_PDF_ENGINE["table"], ["추출기", "설치", "실측 속도", "비고"],
                         ["l", "l", "r", "l"],
                         title=f"PDF 텍스트 추출기 실측 — 선택: {eng or '없음'} "
                               f"(추측 아님 · 이 장비에서 잰 값)")
            if pool is not None and eng:
                # 워커 모듈에 박아 둔 엔진 이름을 실측 결과로 갱신해 다시 띄운다
                _PDF_POOL.update(checked=False, ex=None, fn=None)
                try:
                    pool.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                pool = _pdf_pool(n_par)
        if pool is not None:
            try:
                res = list(pool.map(_PDF_POOL["fn"], pj, chunksize=4))
            except BaseException as e:
                CON.warn(f"프로세스 파싱 실패({type(e).__name__}) — 스레드로 계속합니다")
                _PDF_POOL["ex"], _PDF_POOL["mode"] = None, "스레드(프로세스 중단)"
                pool = None          # ★ 다음 배치가 죽은 풀을 다시 두드리지 않게
                res = pmap(lambda a: _pdf_extract_one(_read_bytes(a[0]), a[1]), pj,
                           workers=n_par)
        else:
            res = pmap(lambda a: _pdf_extract_one(_read_bytes(a[0]), a[1]), pj,
                       workers=n_par)
        out = []
        for (ruid, _p, _y, _s), r in zip(items, res):
            status, payload = r if r else ("READ_FAIL", {})
            if payload:
                payload = dict(payload)
                payload["ruid"] = ruid
            with lock:
                counter["n"] += 1
                if status == "EPS_OK":
                    counter["new"] += 1
                _tick(n_jobs, "파싱")
            out.append((ruid, status, payload or None))
        return out

    for i in range(0, len(jobs), PDF_CHUNK):
        if time.time() > stage_end or DEADLINE.over("PDF 추출"):
            CON.warn(f"PDF 단계 예산 소진 — {i:,}/{len(jobs):,}건에서 중단합니다. "
                     f"종결 원장에 진행분이 기록되어 다음 실행이 이어받습니다.")
            _pdf_checkpoint(done, status_rows)
            break
        got = [g for g in pmap(_acquire, jobs[i:i + PDF_CHUNK],
                               workers=min(6, N_IO_THREADS)) if g]
        for ruid, _p, _y, st in got:                     # 확보 실패는 여기서 기록
            if st:
                status_rows.append(dict(ruid=ruid, status=st,
                                        parser_version=PDF_PARSER_VERSION,
                                        updated_at=_now_iso()))
        for it in _parse_batch([g for g in got if g[1]]):
            ruid, status, payload = it
            status_rows.append(dict(ruid=ruid, status=status,
                                    parser_version=PDF_PARSER_VERSION,
                                    updated_at=_now_iso()))
            if payload:
                done[ruid] = payload
        # ★ 체크포인트는 **시간 기준**이다(청크마다가 아니라).
        #   상한을 풀어 53,000건을 한 실행에서 돌리면 40건마다 저장 = 1,341회이고,
        #   매번 5만 행짜리 표를 통째로 다시 쓰므로 O(n²) 가 된다 — 조용히 수 GB 를
        #   쓰며 수집보다 저장이 더 오래 걸리는 상태가 된다.
        if (time.time() - ck["t"] > PDF_CHECKPOINT_SEC
                or i + PDF_CHUNK >= len(jobs)):
            ck["t"] = time.time()
            _pdf_checkpoint(done, status_rows)
        _eta_report(i + PDF_CHUNK, n_jobs, t0, stage_end)
        # 남은 작업이 전부 차단된 호스트라면 더 돌 이유가 없다
        rest = [j for j in jobs[i + PDF_CHUNK:] if not keymap.get(str(j[0]))]
        if rest and all(CIRCUIT.blocked(_pdf_src(j[1])) for j in rest):
            CON.warn(f"남은 {len(rest):,}건은 모두 차단된 호스트 대상이라 중단합니다 "
                     f"(무의미한 재시도로 예산을 태우지 않습니다).")
            _pdf_checkpoint(done, status_rows)
            break
    _pdf_pool_close()
    CON.ok(f"PDF 단계 종료 — 파싱 {counter['n']:,} · EPS 확보 {counter['new']:,} · "
           f"기존파일 {counter['hit']:,} · 신규다운로드 {counter['net']:,} · "
           f"수신실패 {counter['fail']:,} · 누적 추출 {len(done):,}건 · "
           f"{(time.time()-t0)/60:.1f}분")
    return _attach_pdf_columns(rep, done)


def _attach_pdf_columns(rep: pd.DataFrame, done: Dict[str, dict]) -> pd.DataFrame:
    ex = (pd.DataFrame(list(done.values())) if done else
          pd.DataFrame(columns=["ruid", "pdf_analysts", "eps_json"]))
    for c in ("ruid", "pdf_analysts", "eps_json"):
        if c not in ex.columns:
            ex[c] = pd.Series(dtype="object")
    ex = ex[["ruid", "pdf_analysts", "eps_json"]].drop_duplicates("ruid", keep="last")
    ex["ruid"] = ex["ruid"].astype("object")
    rep = rep.merge(ex, on="ruid", how="left")
    fill = (rep["analyst"].astype(str).str.strip() == "") & rep["pdf_analysts"].notna()
    rep.loc[fill, "analyst"] = rep.loc[fill, "pdf_analysts"]
    if fill.any():
        CON.ok(f"PDF 본문에서 작성자 {int(fill.sum()):,}건 보강"
               f"(네이버 리스트에는 작성자가 없습니다)")
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
    METRIC_COV.clear()
    METRIC_COV.update({r[0]: dict(cov=int(r[1]), rows=int(r[2])) for r in stats})
    if FORECAST_METRIC_MODE in ("EPS", "TP12M"):
        return FORECAST_METRIC_MODE, tab
    eps_cov = tab.loc[tab["metric"] == "EPS", "월중앙_2인이상_종목수"].iloc[0]
    tp_cov = tab.loc[tab["metric"] == "TP12M", "월중앙_2인이상_종목수"].iloc[0]
    met = "EPS" if (eps_cov >= 40 and eps_cov >= 0.30 * max(tp_cov, 1)) else "TP12M"
    CON.ok(f"주지표 자동선택: {met} "
           f"(EPS 커버리지 {eps_cov} vs TP12M {tp_cov} — 기준: EPS≥40 이고 TP의 30% 이상. "
           f"명세 §1 기본은 EPS, TP12M 은 커버리지 부족 시의 검증 경로)")
    return met, tab


METRIC_COV: Dict[str, dict] = {}
TRACK_LABEL = {"TP12M": "빠른판(TP12M·목표주가 · PDF 불필요)",
               "EPS": "정밀판(EPS · PDF 원문 파싱)"}


def coverage_verdict(fc_all: pd.DataFrame, rep: pd.DataFrame,
                     months: Sequence) -> bool:
    """**지금 이 결과를 믿어도 되는가**를 수치로 판정한다.

    ★ 사용자 요구의 핵심: "가능하면 전수수집으로 신뢰할만한 결과를, 그렇다고 무한정
      길게 끌지는 말고." 그 둘을 잇는 다리가 이 표다. 커버리지가 판정선을 넘으면
      '이번 결과는 신뢰 가능', 못 넘으면 '몇 번 더 돌리면 되는지'를 같이 알려준다.
      기준은 자의적 미학이 아니라 명세에서 나온다 —
        · §31 MIN_ANALYSTS=2 : 컨센서스가 성립하는 최소 단위
        · §36 십분위          : 월 60종목 이상이라야 십분위, 그 아래는 오분위
        · §40 IC             : 월 표본이 얇으면 IC 의 표준오차가 결론을 못 낸다
    """
    rows, ok_all = [], True
    n_month = max(len(months), 1)
    for met in ("EPS", "TP12M"):
        f = fc_all[fc_all["forecast_metric"] == met]
        if not len(f):
            rows.append([met, "0", "0", "0%", "✘ 표본 없음"])
            ok_all = False if met == "EPS" else ok_all
            continue
        g = (f.assign(m=f["report_date"].dt.to_period("M"))
              .groupby(["m", "stock_id"], observed=True)["analyst_id"].nunique())
        per_m = g[g >= 2].groupby("m").size()
        med = int(per_m.median()) if len(per_m) else 0
        cov_m = min(1.0, len(per_m) / n_month)
        verdict = ("✔ 십분위 가능(신뢰)" if med >= 60 else
                   "△ 오분위 수준(참고)" if med >= 20 else "✘ 표본 부족")
        rows.append([met, f"{len(f):,}", f"{med}", f"{cov_m*100:.0f}%", verdict])
    # PDF 진척 — 전수까지 얼마나 남았는가
    st = DEPOT.table_load("scg_pdf_status", need_cols=["ruid", "status"])
    n_tot = int(len(rep)) if rep is not None else 0
    n_done = int(st["status"].astype(str).isin(PDF_TERMINAL).sum()) if (
        st is not None and len(st)) else 0
    if not n_done:          # 상태원장이 없는 캐시(타 전략 산출물)면 추출물 수로 센다
        ex0 = DEPOT.table_load("scg_pdf_extract", need_cols=["ruid"])
        n_done = int(len(ex0)) if ex0 is not None else 0
    pct = n_done / max(n_tot, 1) * 100
    rate = float(THROTTLE.qps("naver_pdf"))
    left_h = max(0, n_tot - n_done) / max(rate, 0.1) / 3600
    pct = min(100.0, pct)          # 추출물이 원장보다 많을 수 있다(과거 수집분 포함)
    CON.grid(rows + [["PDF 원문", f"{min(n_done, n_tot):,}/{n_tot:,}", "-", f"{pct:.0f}%",
                      ("✔ 전수 완료" if pct >= 99 else
                       f"진행 중 — 남은 {n_tot-n_done:,}건에 약 {left_h:.1f}시간 "
                       f"(재실행 {math.ceil(left_h/max(COLLECT_HOURS_BUDGET,0.1)):d}회)")]],
             ["지표", "예측행수", "월중앙 2인이상 종목", "월 커버리지", "판정"],
             ["l", "r", "r", "r", "l"],
             title="신뢰도 판정 — 지금 결과를 믿어도 되는가 (§31 2인 · §36 십분위 60종목)")
    if pct < 99:
        CON.say("전수수집은 종결원장으로 **이어받기**가 보장됩니다 — 같은 파일을 다시 "
                "실행하면 남은 것부터 채우고, 이미 종결된 건은 다시 열지 않습니다. "
                "그동안에도 매 실행이 완결된 백테스트를 산출합니다.")
    return ok_all


def plan_tracks(fc_all: pd.DataFrame) -> Tuple[str, List[str], pd.DataFrame]:
    """어떤 지표로 몇 개의 트랙을 돌릴지 결정한다.

    ★ 사용자 요구: "PDF 직접 파싱이 어렵다면 목표주가 버전으로 빠르게 백테스트하고,
      빠른 버전과 PDF 파싱 버전을 서로 비교해봐."
      → BOTH 모드에서는 **빠른 쪽(TP12M)을 먼저** 돌린다. PDF 트랙이 커버리지 부족으로
        비어도 최소 한 벌의 완결된 결과가 이미 나와 있게 하기 위해서다.
    """
    primary, tab = choose_metric(fc_all)
    if FORECAST_METRIC_MODE != "BOTH":
        return primary, [primary], tab
    order = [m for m in ("TP12M", "EPS") if METRIC_COV.get(m, {}).get("rows", 0) > 0]
    thin = [m for m in order if METRIC_COV[m]["cov"] < 5]
    for m in thin:
        CON.warn(f"[{m}] 트랙 커버리지가 너무 얕습니다"
                 f"(월중앙 2인이상 종목 {METRIC_COV[m]['cov']}개) — 이 트랙은 건너뜁니다")
    order = [m for m in order if m not in thin] or [primary]
    if primary not in order:
        primary = order[0]
    CON.ok("이중 트랙 실행: " + " → ".join(f"{m}({TRACK_LABEL[m]})" for m in order)
           + f" · 주 트랙 {primary}")
    return primary, order, tab


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
    if not len(fc):
        out = fc.copy()
        out["report_date"] = pd.Series(dtype="datetime64[ns]")
        out["valid_until"] = pd.Series(dtype="datetime64[ns]")
        return out
    """각 전망의 활성 구간 [발표일, 다음 전망일 또는 +180일). 같은 키의 새 전망이 옛 것을
    대체하므로 (stock,analyst,fp,metric,T) 활성표는 최대 1개 — TEST 8 이 구조로 보장된다."""
    fc = fc.sort_values(FC_KEY + ["report_date"], kind="mergesort").reset_index(drop=True)
    nxt = fc.groupby(FC_KEY, observed=True, sort=False)["report_date"].shift(-1)
    exp = fc["report_date"] + pd.Timedelta(int(cfg.MAX_FORECAST_AGE_DAYS) + 1, "D")
    fc["valid_until"] = np.minimum(nxt.fillna(pd.Timestamp("2262-01-01")).to_numpy(),
                                   exp.to_numpy())
    return fc


def active_at(fcv: pd.DataFrame, T: pd.Timestamp) -> pd.DataFrame:
    cols = (FC_KEY + ["broker_id", "report_id", "report_date", "forecast_value"]
            if "broker_id" in fcv.columns else
            FC_KEY + ["report_id", "report_date", "forecast_value"])
    if not len(fcv):
        # ★ 빈 프레임은 dtype 이 object 라 아래의 날짜 뺄셈·.dt 가 죽는다.
        #   '입력이 없다'는 정상 상태이므로, 모양과 dtype 을 갖춘 빈 결과를 돌려준다.
        out = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
        out["report_date"] = pd.Series(dtype="datetime64[ns]")
        out["forecast_value"] = pd.Series(dtype="float64")
        out.insert(0, "signal_date", pd.Series(dtype="datetime64[ns]"))
        out["forecast_age_days"] = pd.Series(dtype="int64")
        return out
    t = np.datetime64(pd.Timestamp(T).normalize())
    rd = fcv["report_date"].to_numpy("datetime64[ns]")
    vu = fcv["valid_until"].to_numpy("datetime64[ns]")
    sub = fcv.loc[(rd <= t) & (t < vu), cols].copy()
    sub.insert(0, "signal_date", pd.Timestamp(T).normalize())
    sub["forecast_age_days"] = (ts_col(sub["signal_date"])
                                - ts_col(sub["report_date"])).dt.days
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
        d["primary"] = d["fiscal_period"].astype(str) == "12M"
        if len(d) and not d["primary"].any():
            # ★ 조용한 0행 방지. 다른 전략이 만든 캐시는 TP 행의 fiscal_period 라벨이
            #   '12M' 이 아닐 수 있다(예: 'TP', '12개월', 연도표기). 라벨 하나 때문에
            #   트랙 전체가 빈 결과로 나오면 원인을 찾는 데만 한나절이 든다.
            lab = ", ".join(map(str, d["fiscal_period"].astype(str).unique()[:4]))
            CON.warn(f"TP12M 대표기간 라벨이 '12M' 이 아닙니다(관측: {lab}) — "
                     f"종목·시점당 1행을 대표로 승격해 트랙을 살립니다")
            idx = (d.sort_values("fiscal_period")
                   .groupby(["signal_date", "stock_id"], observed=True, sort=False)
                   .head(1).index)
            d.loc[idx, "primary"] = True
        return d
    ann: Dict[Tuple[str, str], pd.Timestamp] = {}
    if actuals is not None and len(actuals):
        for r in actuals.itertuples(index=False):
            ann[(r.stock_id, r.fiscal_period)] = r.actual_announcement_date
    year = d["fiscal_period"].astype(str).str.extract(r"(20\d{2})", expand=False)
    d["_fy"] = pd.to_numeric(year, errors="coerce")
    d = d[d["_fy"].notna()]
    if not len(d):                      # 빈 프레임의 object dtype 에 .dt 를 쓰면 죽는다
        return d.assign(primary=False)
    d["signal_date"] = ts_col(d["signal_date"])
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
    if not len(cons):                   # 하류(rank_alphas)가 요구하는 컬럼을 갖춰 돌려준다
        return cons.assign(**{c: np.nan for c in
                              ("scg0", "scg_ls", "scg_accel_20d", "base_revision_20d")})
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
    # ★ rows 가 비면 '컬럼조차 없는' 프레임이 되어, empty=False 를 믿는 하류가
    #   KeyError('ls') 로 죽는다. 모양을 계약으로 고정한다.
    R = pd.DataFrame(rows, columns=["month", "top", "bot", "ls", "top_net",
                                    "n_xs", "n_top", "turnover", "cost"])
    if not len(R):
        return {"strategy": strat, "empty": True,
                "note": "유효 수익률이 있는 신호일이 없습니다"}
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


def run_suite(sig: pd.DataFrame, panel: pd.DataFrame, label: str) -> Dict[str, dict]:
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
# ║ [S7~S9] 트랙 — 지표 하나를 '사건→점수→신호→백테스트'까지 완주시키는 단위                   ║
# ║  ★ 같은 가격행렬·같은 패널·같은 유니버스를 공유한다. 트랙을 늘려도 시장데이터 호출은        ║
# ║    단 한 번도 늘지 않는다(사용자 지시: 쓸데없이 가격조회를 반복하지 말 것).                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def build_track(metric: str, fc: pd.DataFrame, fcv: pd.DataFrame, actuals: pd.DataFrame,
                cal: "TradingCal", sig_months: List, cfg: "SCGParams",
                PMX: "PriceMatrix") -> dict:
    """지표 하나에 대한 SCG 엔진 전체(§7~§29)."""
    t0 = time.time()
    tp_act = (tp_actuals_from_prices(fc, PMX, cal) if metric == "TP12M" else
              pd.DataFrame(columns=["report_id", "matured_at", "actual_price"]))
    acc_ev = (acc_events_eps(fc, actuals, cfg) if metric == "EPS"
              else acc_events_tp(fc, tp_act, cfg))
    led_ev = lead_events(fcv, cal, cfg, metric)
    CON.say(f"[{metric}] 사건 테이블: 정확도 {len(acc_ev):,} · 리더십 {len(led_ev):,}")
    FLOW.io("출", "메모리", f"정확도사건_{metric}", acc_ev)
    FLOW.io("출", "메모리", f"리더십사건_{metric}", led_ev)
    scores = analyst_scores(sig_months, acc_ev, led_ev, cfg)
    cons, W = smart_consensus(fcv, scores, sig_months, cfg, metric)
    cons = pick_primary_fp(cons, actuals, metric)
    sig = rank_alphas(scg_signals(cons, sig_months, cal, cfg), cfg)
    ENG = dict(cfg=cfg, fcv=fcv, acc_ev=acc_ev, lead_ev=led_ev, metric=metric,
               signal_dates=sig_months, cal=cal, actuals=actuals, sig=sig)
    return dict(metric=metric, label=TRACK_LABEL.get(metric, metric), ENG=ENG, sig=sig,
                scores=scores, W=W, cons=cons, acc_ev=acc_ev, lead_ev=led_ev,
                tp_act=tp_act, build_sec=time.time() - t0)


def eval_track(trk: dict, panel: pd.DataFrame, uni_df: pd.DataFrame,
               bench: Optional[Dict[str, pd.Series]], mtab: Optional[pd.DataFrame],
               cfg: "SCGParams", full_report: bool = True, report: bool = True) -> dict:
    """트랙 하나를 전체 유니버스 + 시총하위N 두 유니버스에서 백테스트한다."""
    met, lbl = trk["metric"], trk["label"]
    sigp = trk["sig"][trk["sig"]["primary"]].merge(uni_df, on=["signal_date", "stock_id"],
                                                   how="left")
    sig_full = sigp[sigp["in_uni"].fillna(False).astype(bool)]
    n_months = max(sig_full["signal_date"].nunique(), 1) if len(sig_full) else 1
    CON.say(f"[{met}] 신호×유니버스 교집합: {len(sig_full):,}행 "
            f"(월평균 {len(sig_full)/n_months:.0f}종목)")
    suites_full = run_suite(sig_full, panel, f"{lbl} · 전체 유니버스")
    if report:
        report_all(suites_full, bench, sig_full, trk["scores"], trk["W"], trk["cons"],
                   f"{lbl} · 전체 유니버스", mtab if full_report else None, cfg)

    suites_small, sig_small = {}, pd.DataFrame()
    uu = uni_df.dropna(subset=["mktcap"])
    if len(uu) and len(sig_full):
        sm = (uu.sort_values("mktcap").groupby("signal_date", observed=True, sort=False)
                .head(COMPARE_BOTTOM_N)[["signal_date", "stock_id"]].copy())
        sm["in_small"] = True
        sigs = sig_full.merge(sm, on=["signal_date", "stock_id"], how="left")
        sig_small = alphas_in_universe(sigs, sigs["in_small"].fillna(False).astype(bool), cfg)
        CON.say(f"[{met}] 시총하위{COMPARE_BOTTOM_N} 유니버스 신호: {len(sig_small):,}행")
        suites_small = run_suite(sig_small, panel, f"{lbl} · 시총하위{COMPARE_BOTTOM_N}")
        if report:
            report_all(suites_small, bench, sig_small, trk["scores"], trk["W"],
                       trk["cons"], f"{lbl} · 시총 하위{COMPARE_BOTTOM_N} 비교전략",
                       None, cfg)
    elif not len(sig_full):
        CON.warn(f"[{met}] 이 트랙의 신호가 0행이라 시총하위{COMPARE_BOTTOM_N} 비교를 "
                 f"건너뜁니다 — 위 '신호×유니버스' 줄과 예측 커버리지를 확인하세요")
    else:
        CON.warn(f"[{met}] 단면 시가총액이 없어 시총하위{COMPARE_BOTTOM_N} 비교를 건너뜁니다")
    trk.update(sig_full=sig_full, suites_full=suites_full,
               suites_small=suites_small, sig_small=sig_small)
    return trk


def _track_row(trk: dict, suites_key: str, strat: str,
               bench: Optional[Dict[str, pd.Series]]) -> List[str]:
    bt = (trk.get(suites_key) or {}).get(strat, {})
    if not bt or bt.get("empty", True):
        return ["-"] * 7
    ps = perf_summary(bt, (bench or {}).get("KOSPI"), leg="ls")
    rho, _ = monotonicity(bt)
    ic = (bt.get("ic") or {}).get(20, {})
    return [f"{ps.get('n_signals', 0):,}",
            f"{ps.get('n_unique_stocks', 0):,}",
            _fmt(ps.get("annualized_return")),
            _fmt(ps.get("Sharpe"), "{:+.2f}"),
            _fmt(ps.get("MDD")),
            _fmt(ic.get("mean_ic"), "{:+.3f}"),
            _fmt(rho, "{:+.2f}")]


def track_compare(tracks: "OrderedDict[str, dict]",
                  bench: Optional[Dict[str, pd.Series]], primary: str):
    """★ 사용자 요구의 핵심 산출물 — '빠른 판(TP12M)' vs 'PDF 파싱 판(EPS)' 정면 비교.

    PDF 원문 파싱은 비싸다(수만 건 다운로드·수 시간). 그 비용이 **성과로 회수되는가**를
    수치로 보여주지 않으면 계속 태울지 말지 판단할 근거가 없다. 그래서 같은 가격·같은
    유니버스·같은 파라미터 위에서 두 트랙을 나란히 놓는다. 차이의 원인은 오직 '무엇을
    예측 대상으로 삼았는가' 하나뿐이다.
    """
    if len(tracks) < 2:
        return
    CON.head("트랙 비교 — 빠른판(목표주가) vs 정밀판(PDF·EPS)",
             "같은 가격·같은 유니버스·같은 파라미터 · 차이는 '예측 대상 지표' 하나뿐입니다")
    heads = ["트랙", "유니버스", "전략", "신호행", "종목수", "L/S 연율", "Sharpe",
             "MDD", "IC20", "단조성ρ"]
    rows = []
    for met, trk in tracks.items():
        tag = f"{met}{' ★주' if met == primary else ''}"
        for ukey, uname in (("suites_full", "전체"),
                            ("suites_small", f"하위{COMPARE_BOTTOM_N}")):
            if not trk.get(ukey):
                continue
            for st in STRATS:
                rows.append([tag, uname, st] + _track_row(trk, ukey, st, bench))
        rows.append(["", "", "", "", "", "", "", "", "", ""])
    CON.grid(rows, heads, ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r"],
             title=f"4전략 × 2유니버스 × {len(tracks)}트랙 동시 비교 (§30 동일표본 정렬 적용)")

    cost = []
    for met, trk in tracks.items():
        cv = METRIC_COV.get(met, {})
        cost.append([met, TRACK_LABEL.get(met, met), f"{cv.get('rows', 0):,}행",
                     f"{cv.get('cov', 0)}개",
                     "불필요" if met == "TP12M" else "필요(다운로드+파싱)",
                     f"{trk.get('build_sec', 0):.0f}초"])
    CON.grid(cost, ["지표", "트랙", "예측행수", "월중앙 2인이상 종목", "PDF 원문",
                    "엔진 소요"], ["l", "l", "r", "r", "l", "r"],
             title="트랙별 조달 비용 — 'PDF를 계속 태울 가치가 있는가'의 판단 근거")

    if "TP12M" in tracks and "EPS" in tracks:
        def _ann(m):
            bt = (tracks[m].get("suites_full") or {}).get("SCG_LS", {})
            if not bt or bt.get("empty", True):
                return np.nan
            return perf_summary(bt, None, leg="ls").get("annualized_return", np.nan)
        a_tp, a_eps = _ann("TP12M"), _ann("EPS")
        n_tp = METRIC_COV.get("TP12M", {}).get("cov", 0)
        n_eps = METRIC_COV.get("EPS", {}).get("cov", 0)
        if np.isfinite(a_tp) and np.isfinite(a_eps):
            gap = a_eps - a_tp
            CON.ok(f"판정: SCG_LS 연율 기준 EPS {a_eps*100:+.1f}% vs TP12M {a_tp*100:+.1f}% "
                   f"(차이 {gap*100:+.1f}%p). 커버리지는 EPS {n_eps} vs TP12M {n_tp}종목/월. "
                   + ("PDF 파싱이 성과로 회수됩니다 — 계속 채우십시오."
                      if gap > 0.02 and n_eps >= 0.5 * max(n_tp, 1) else
                      "현 커버리지에서 PDF 파싱의 성과 이득이 확인되지 않습니다 — "
                      "빠른판(TP12M)으로 운용하고 PDF는 배경에서 천천히 채우십시오."))
        else:
            CON.warn("판정 보류 — 한쪽 트랙의 백테스트가 비어 비교할 수 없습니다 "
                     "(위 표에서 어느 쪽이 비었는지 확인하세요)")


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

    def c_track():
        """★ 트랙이 '조용히 0행'으로 끝나지 않는가.
        TP12M 트랙이 스모크에서 통째로 비었던 원인이 정확히 이것이었다:
        대표 회계기간 라벨이 '12M' 이 아니면 primary 가 전부 False 가 되고,
        그 뒤 모든 표가 '-' 로 찍히는데 어디서 비었는지는 아무 데도 안 나온다."""
        base = pd.DataFrame({"signal_date": [ts("2021-06-30")] * 2,
                             "stock_id": ["005930", "000660"],
                             "fiscal_period": ["12M", "12M"],
                             "forecast_metric": "TP12M", "smart": [1.0, 2.0]})
        n_ok = int(pick_primary_fp(base, pd.DataFrame(), "TP12M")["primary"].sum())
        odd = base.assign(fiscal_period=["12개월", "TP"])
        n_odd = int(pick_primary_fp(odd, pd.DataFrame(), "TP12M")["primary"].sum())
        eps = pd.DataFrame({"signal_date": [ts("2021-06-30")] * 2,
                            "stock_id": ["005930"] * 2,
                            "fiscal_period": ["2021FY", "2022FY"],
                            "forecast_metric": "EPS", "smart": [1.0, 2.0]})
        n_eps = int(pick_primary_fp(eps, pd.DataFrame(), "EPS")["primary"].sum())
        ok = (n_ok == 2 and n_odd == 2 and n_eps == 1)
        return ok, f"TP정상 {n_ok}/2 · TP라벨이상 {n_odd}/2 · EPS 대표 {n_eps}/1"
    _ct("C-트랙", "대표기간 승격(트랙 공백 방지)", c_track)

    def c_path():
        """★ 경로 포함 판정 — 실행을 통째로 막았던 자리다.

        윈도우 사용자 환경에서 `realpath(...).startswith(...)` 가 오탐해
        '쓰기 루트 밖 기록 시도'로 리허설이 죽었다. 순수 로직이라 어떤 OS 에서도
        같은 답이 나와야 하고, 절대1원칙의 최후 방어선이므로 계약으로 못박는다.
        """
        base = os.path.abspath(os.path.join(tempfile.gettempdir(), "scg_ct"))
        ins = os.path.join(base, "shared", "blob", "research_pdf", "01", "x.pdf")
        cases = [
            (ins, base, True, "존재하지 않는 하위 경로도 '안'으로 봐야 한다"),
            (base, base, True, "자기 자신은 안이다"),
            (base + "2", base, False, "형제 디렉터리를 안으로 오판하면 안 된다"),
            (os.path.join(base, ".", "shared", "..", "shared", "a.txt"), base, True,
             "정규화 전 형태도 같은 답이어야 한다"),
            (os.path.abspath(os.sep + "elsewhere" + os.sep + "x"), base, False,
             "완전히 다른 경로는 밖이다"),
        ]
        bad = [w for c, q, want, w in cases if Depot._inside(c, q) is not want]
        if not bad and os.name != "nt":       # 대소문자 무시 판정(윈도우 규칙) 확인
            up = base.upper()
            if os.path.normcase("A") == os.path.normcase("a") and                     not Depot._inside(ins, up):
                bad.append("대소문자 차이를 흡수하지 못한다")
        return (not bad), (f"{len(cases)}개 경우 통과" if not bad
                           else "실패: " + "; ".join(bad)[:60])
    _ct("C-경로", "경로 포함 판정(절대1원칙 방어선)", c_path)
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


def _fx_real_pdf(lines: Sequence[str]) -> bytes:
    """xref 까지 갖춘 '진짜' 최소 PDF — 픽스처가 실제 파서를 태우게 하려면 필요하다.
    (바이트만 %PDF 로 시작하는 가짜를 쓰면 파서 경로가 검증되지 않는다)"""
    objs = [b"<</Type/Catalog/Pages 2 0 R>>",
            b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>"]
    body = ["BT /F1 11 Tf 40 740 Td 14 TL"]
    for ln in lines:
        esc = str(ln).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        body.append(f"({esc}) Tj T*")
    body.append("ET")
    stream = "\n".join(body).encode("latin-1", "replace")
    objs.append(b"<</Length " + str(len(stream)).encode() + b">>stream\n"
                + stream + b"\nendstream")
    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj".encode() + o + b"endobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    for off in offs:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer<</Size {len(objs)+1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


_FX_PDF_LINES = ["            2026    2027", "EPS       1,000   1,200",
                 "Kim Analyst  02-000-0000"]


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
            return _fx_real_pdf(_FX_PDF_LINES)
        if "consensus.hankyung" in u:
            return _fx_hankyung_html()
        if "finance.naver.com/research" in u:
            return _fx_naver_html()
        if u.lower().endswith(".pdf"):
            return _fx_real_pdf(_FX_PDF_LINES)
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


def _rh(name: str, fn: Callable, expect_rows: bool = True, blocking: bool = True):
    """리허설 항목 1건.

    ★ blocking=False 는 '환경에 따라 달라지는 검사'를 뜻한다(선택 라이브러리 유무,
      원격지 응답 형태 등). 이런 검사는 결과를 보여주되 **실행을 막지 않는다**.

      이 구분이 없어서 사고가 났다: 내가 만든 합성 PDF 가 pdfminer 로 파싱되는지를
      확인할 방법이 없는 환경에서 그 검사를 '차단 게이트'로 넣어 배포했고, 정작
      사용자 환경에서 그 검사가 실패해 백테스트 자체가 시작조차 못 했다.
      배선(wiring) 검사만 차단해야 한다 — 그건 어디서 돌려도 결과가 같기 때문이다.
    """
    t0 = time.time()
    try:
        v = fn()
        n = len(v) if hasattr(v, "__len__") else (1 if v is not None else 0)
        ok = (n > 0) if expect_rows else True
        REHEARSAL.append(dict(name=name, ok=ok, rows=n, sec=time.time() - t0,
                              blocking=blocking, err="" if ok else "행 0개"))
        return v
    except Exception as e:
        REHEARSAL.append(dict(name=name, ok=False, rows=-1, sec=time.time() - t0,
                              blocking=blocking,
                              err=f"{type(e).__name__}: {e}"[:110],
                              tb=traceback.format_exc(limit=6)))
        return None


def _rehearsal_depot(tmp: str) -> "Depot":
    """실제 캐시를 절대 건드리지 않는 임시 금고."""
    dep = Depot.__new__(Depot)
    dep.write_root = os.path.abspath(tmp)
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
            "DEPOT", "RESEARCH_DOWNLOAD_PDF", "RESEARCH_COLLECT", "_probe_get")
    saved_robust = list(ROBUST.items())
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

        def _probe_fx(url, params=None, headers=None, timeout=20.0):
            """진단 전송을 픽스처로 바꿔치기 — 실제 네트워크 없이 배선만 검증한다."""
            if "apps.analysis" in str(url):        # 구 라우트는 죽은 것으로 가정
                return 403, b"<html><body>Forbidden</body></html>", "utf-8", 0
            if str(url).rstrip("/") == _HK_HOME.rstrip("/"):
                return 200, b"<html>home</html>", "utf-8", 2
            return 200, _fx_hankyung_html().encode("utf-8"), "utf-8", 2
        G["_probe_get"] = _probe_fx
        HK.update(probed=False, alive=False, name=_HK_CANDIDATES[0][0],
                  list=_HK_CANDIDATES[0][1], pdf=_HK_CANDIDATES[0][2])
        dep = _rehearsal_depot(tmp)
        G["DEPOT"] = dep

        # ── 회로차단기 — '막힌 소스에 시간을 쓰지 않는다'는 배선 자체를 증명한다 ──
        #  ★ 차단(blocking) 검사다. 순수 로직이라 어떤 환경에서도 동일하게 판정된다.
        #    이게 없어서 403 사이트에 60분 예산을 통째로 헌납하고 화면은 멈춰 보였다.
        def _circuit_wiring():
            cb = SourceCircuit(limit=3, quiet=True)
            assert not cb.blocked("x")
            for _ in range(2):
                cb.fail("x", "HTTP 403")
            assert not cb.blocked("x"), "한도 전에 차단되면 정상 소스가 끊긴다"
            cb.fail("x", "HTTP 403")
            assert cb.blocked("x"), "한도 도달 시 차단되어야 한다"
            cb.ok("x")
            assert not cb.blocked("x"), "성공하면 즉시 복구되어야 한다"
            cb.fail("y", "EXC"); cb.ok("y")          # 연속이 끊기면 카운터 초기화
            for _ in range(2):
                cb.fail("y", "EXC")
            assert not cb.blocked("y"), "성공으로 끊긴 연속은 누적되면 안 된다"
            return 1
        _rh("회로차단기 배선(연속실패→차단→복구)", _circuit_wiring)

        def _fetch_skip_is_instant():
            """차단된 소스는 대기 없이 즉시 None — 이 즉시성이 핵심이다."""
            G_fetch = saved["fetch"]                  # 픽스처가 아닌 진짜 fetch
            CIRCUIT.open_now("__rh__", "리허설")
            t0 = time.time()
            r = G_fetch("https://example.invalid/x", source="__rh__", tries=3)
            el = time.time() - t0
            CIRCUIT.opened.pop("__rh__", None)
            assert r is None and el < 0.5, f"차단 소스가 {el:.2f}s 를 소모했다"
            return 1
        _rh("차단 소스는 즉시 건너뜀(대기 0초)", _fetch_skip_is_instant)

        def _pdf_route_rewrite():
            """캐시에 남은 옛 PDF 경로를 살아 있는 경로로 치환하는 배선."""
            _PDF_URL_REWRITE.clear()
            u = "https://consensus.hankyung.com/analysis/downpdf?report_idx=7"
            assert pdf_url_fix(u) == u, "치환 규칙이 없으면 원문 그대로여야 한다"
            alts = _pdf_alt_urls(u)
            assert alts and "apps.analysis/analysis.downpdf" in alts[0][2]
            _PDF_URL_REWRITE.append((alts[0][0], alts[0][1]))
            assert "apps.analysis/analysis.downpdf" in pdf_url_fix(u)
            assert pdf_url_fix("https://finance.naver.com/x.pdf").endswith("x.pdf")
            _PDF_URL_REWRITE.clear()
            return 1
        _rh("PDF 경로 치환(구/신 라우트 교차)", _pdf_route_rewrite)

        def _pdf_alias_index():
            """저장키가 안 맞아도 URL 의 보고서번호로 기존 PDF 를 찾아내는가.
            ★ 매칭률 1%(10,119건 중 124건)의 원인을 겨눈 검사다. 동시에 '한 번호가
              서로 다른 파일을 가리키면 버린다'는 안전장치도 함께 확인한다 —
              엉뚱한 PDF 에서 EPS 를 뽑는 것이 못 찾는 것보다 훨씬 나쁘다."""
            base = "https://consensus.hankyung.com/analysis/downpdf?report_idx="
            dep.blob_save("research_pdf", "KEY_A", b"%PDF-1.4 alpha\n", "pdf",
                          source=base + "770001")
            dep.blob_save("research_pdf", "KEY_B", b"%PDF-1.4 bravo\n", "pdf",
                          source=base + "770002")
            dep.blob_save("research_pdf", "KEY_C", b"%PDF-1.4 charlie\n", "pdf",
                          source=base + "770002")          # 같은 번호, 다른 파일 → 모호
            km = _pdf_key_index()
            assert "770001" in km, "URL 번호 별칭이 심어지지 않았다"
            assert "770002" not in km, "모호한 번호는 버려야 한다(오매칭 방지)"
            assert km["770001"].endswith(".pdf") and os.path.exists(km["770001"])
            return 1
        _rh("PDF 별칭 색인(URL 번호 → 파일)", _pdf_alias_index)

        def _worker_module_compiles():
            """파싱 워커 모듈이 **문법·이름 모두 성립**하는가 — 순수 로직이라 차단검사다.
            ★ 실제로 여기서 걸렸다: 본체 함수의 타입주석(Dict/List)을 워커 헤더에
              import 하지 않아 워커가 NameError 로 죽었고, 프로세스 병렬이 조용히
              스레드로 되돌아가 병렬화 이득이 0이 됐다. 컴파일만으로 잡힌다."""
            src = _pdf_worker_source()
            ns: Dict[str, Any] = {}
            exec(compile(src, "<scg_pdf_worker>", "exec"), ns)
            assert callable(ns.get("work")) and ns.get("selftest")() == "ok"
            assert ns["_pdf_extract_one"](b"not a pdf", 2020)[0] == "NOT_PDF"
            return 1
        _rh("PDF 파싱 워커 모듈 생성·컴파일", _worker_module_compiles)

        def _tcd_key_rule():
            """다른 전략(TCD v2)의 저장키 규칙을 정확히 재현하는가."""
            want = hashlib.sha1(b"hankyung\x1f12345\x1f").hexdigest()
            assert h1_trail("hankyung", "12345") == want, "구분자/후행 규칙 불일치"
            assert h1("hankyung", "12345") != want, "두 규칙은 달라야 정상이다"
            return 1
        _rh("타 전략 저장키 규칙 재현(PDF 재사용)", _tcd_key_rule)
        def _pool_probe():
            """★ 리허설이 띄운 워커를 그대로 두면 유휴 프로세스가 실행 내내 남는다.
            띄워 보고 **반드시 정리**한다. 사유는 표에 남겨 조치할 수 있게 한다."""
            ok = _pdf_pool(2) is not None
            _pdf_pool_close()
            if not ok and _PDF_POOL.get("why"):
                CON.debug(f"프로세스 풀 사용 불가 사유: {_PDF_POOL['why']}")
            return ok or None
        _rh("ⓘ PDF 파싱 프로세스 풀 기동", _pool_probe,
            expect_rows=False, blocking=False)
        _rh("ⓘ 한경 접속 진단(경로 자동선택)", lambda: (hk_probe(), HK["alive"])[1],
            expect_rows=False, blocking=False)

        _rh("무인증 캐시(listing)", lambda: fdr_cache_csv("listing/krx", back_days=3))
        _rh("무인증 캐시: 저장소 시작일 이전은 조회하지 않음",
            lambda: (fdr_cache_csv("listing/krx", back_days=3,
                                   asof=ts("2019-06-03")) is None) or None,
            expect_rows=True)
        _rh("무인증 캐시(delisting)", lambda: fdr_cache_csv("listing/delisting", back_days=3))
        _rh("단면: 벌크 marcap", lambda: bulk_marcap_year(2020))
        _rh("단면: 일단위 캐시",
            lambda: _xsec_fdrcache(ts(FDR_CACHE_LISTING_FROM) + pd.Timedelta(30, "D")))
        _rh("ⓘ 단면: pykrx", lambda: _xsec_pykrx(ts("2020-01-08")),
            expect_rows=False, blocking=False)
        # ★ 리허설이 **실제 KRX 로그인**을 하면 본 실행의 세션을 빼앗는다.
        #   KRX 는 중복 로그인 시 기존 세션을 끊기 때문에, 리허설 직후 본 실행이
        #   '세션무효'를 맞는다(로그에서 실제로 그렇게 나타났다). 배선만 확인한다.
        _rh("ⓘ 단면: KRX 마켓플레이스(로그인 없이 배선만)",
            lambda: KrxMarketplace("", "").xsec(ts("2020-01-08")),
            expect_rows=False, blocking=False)
        _rh("ⓘ 구간수익률: pykrx",
            lambda: _period_return_krx(ts("2020-01-02"), ts("2020-01-08")),
            expect_rows=False, blocking=False)
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
        _rh("ⓘ 벤치마크", lambda: collect_benchmark(hub, month_ends("2020-01-01",
                                                                  "2020-03-31")),
            expect_rows=False, blocking=False)

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
        # ⓘ 아래는 '환경 의존' 검사다 — PDF 라이브러리 종류/버전에 따라 결과가 달라지므로
        #   정보로만 남기고 실행을 막지 않는다. PDF 는 보강 경로이지 전제조건이 아니다.
        _rh("ⓘ PDF 텍스트 추출(라이브러리 의존)",
            lambda: (_pdf_text(_fx_real_pdf(_FX_PDF_LINES))
                     if (_fitz is not None or _pdfplumber is not None) else "라이브러리없음"),
            expect_rows=True, blocking=False)
        _rh("EPS 파서(본문→연도별 추정치)",
            lambda: _eps_from_text("            2020    2021\n"
                                   "EPS       1,000   1,200\n", 2020))
        _rh("DART corpCode",
            lambda: _dart_corpmap(pd.DataFrame({"code": ["005930"]})))
        _rh("DART 접수일", lambda: _dart_filing_dates("2021-01-01", "2021-03-31"))
        _rh("DART 실적 EPS",
            lambda: collect_actual_eps(
                pd.DataFrame({"code": ["005930"], "name": ["테스트"]}),
                hub.slice(hub.all_dates()), "2020-01-01", "2021-12-31"),
            expect_rows=False)

        # ── 퇴화경로(degenerate) 리허설 ────────────────────────────────────────────
        #  ★ 감사에서 확인된 결함 4건이 모두 '빈 결과 분기가 다른 모양의 프레임을
        #    반환한다'는 한 가지 뿌리였다. 정상경로만 태우면 절대 안 잡힌다.
        #    그래서 '수집은 됐는데 내용이 비었다'는 상태를 일부러 만들어 S7~S10 을 태운다.
        cfgz = SCGParams()
        empty_fc = pd.DataFrame(columns=FC_KEY + ["broker_id", "report_id",
                                                  "report_date", "forecast_value"])
        mz = list(month_ends("2020-01-01", "2020-03-31"))
        calz = TradingCal(pd.bdate_range("2019-06-01", "2020-12-31"))
        consz = _rh("퇴화: 빈 컨센서스",
                    lambda: smart_consensus(with_validity(empty_fc, cfgz), pd.DataFrame(),
                                            mz, cfgz, "EPS")[0], expect_rows=False)
        prim = _rh("퇴화: 대표 회계기간 선정",
                   lambda: pick_primary_fp(consz, pd.DataFrame(), "EPS"),
                   expect_rows=False)
        sigz = _rh("퇴화: 신호 산출",
                   lambda: scg_signals(prim, mz, calz, cfgz), expect_rows=False)
        alz = _rh("퇴화: 알파 랭크",
                  lambda: rank_alphas(sigz, cfgz), expect_rows=False)
        # 전 종목 수익률이 전부 결측인 패널(수집이 끊긴 최악의 중간결과 상태)
        panz = pd.DataFrame({"code": ["005930", "000660"] * len(mz),
                             "month": np.repeat(mz, 2), "close": 1000.0,
                             "mktcap": 1e9, "value": 1e8, "fwd_1m": np.nan,
                             "fwd_20td": np.nan, "fwd_60td": np.nan, "fwd_120td": np.nan})
        sig_nz = pd.DataFrame({"signal_date": np.repeat(mz, 2),
                               "stock_id": ["005930", "000660"] * len(mz),
                               "primary": True})
        for c in ALPHA_COL.values():
            sig_nz[c] = 0.5
        for c in ("base_revision_20d", "scg0", "scg_ls", "scg_accel_20d"):
            sig_nz[c] = 0.0
        stz = _rh("퇴화: 백테스트(전 수익률 결측)",
                  lambda: run_suite(sig_nz, panz, "퇴화"), expect_rows=False)
        if stz:
            _rh("퇴화: 성과요약", lambda: perf_summary(stz["SCG_LS"]) or {1: 1},
                expect_rows=False)
            _rh("퇴화: 보고표", lambda: (report_all(stz, None, sig_nz, pd.DataFrame(),
                                                  pd.DataFrame(), consz, "퇴화", None,
                                                  cfgz), 1)[1])
            _rh("퇴화: 강건성(서브기간·집중도)",
                lambda: (R_subperiod(stz), R_concentration(stz), 1)[2])
            _rh("퇴화: 비용 스트레스", lambda: (R_cost_stress(sig_nz, panz), 1)[1])
        _rh("퇴화: 단조성", lambda: (monotonicity({"empty": True}), 1)[1])
    finally:
        for k, v in saved.items():
            G[k] = v
        # ★ 리허설이 픽스처로 정한 한경 경로를 실행분으로 흘려보내면 안 된다 — 초기화.
        HK.update(probed=False, alive=False, name=_HK_CANDIDATES[0][0],
                  list=_HK_CANDIDATES[0][1], pdf=_HK_CANDIDATES[0][2])
        CIRCUIT.opened.clear()
        CIRCUIT._streak.clear()
        _PDF_URL_REWRITE.clear()
        _PDF_POOL.update(ex=None, mode="", checked=False, fn=None, why="")
        _PDF_ENGINE.update(measured=False, name="", table=[])
        ROBUST.clear()                 # 리허설이 남긴 강건성 결과는 실행분과 섞지 않는다
        ROBUST.update(dict(saved_robust))
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [r for r in REHEARSAL if not r["ok"] and r.get("blocking", True)]
    soft = [r for r in REHEARSAL if not r["ok"] and not r.get("blocking", True)]
    CON.grid([[r["name"], ("통과" if r["ok"] else
                           ("실패" if r.get("blocking", True) else "정보(비차단)")),
               f"{r['rows']:,}" if r["rows"] >= 0 else "-",
               f"{r['sec']:.2f}s", r["err"][:46]] for r in REHEARSAL],
             ["수집·정제 함수", "판정", "행수", "소요", "오류"],
             ["l", "l", "r", "r", "l"],
             title="실경로 리허설 (네트워크만 가짜 · 함수는 실물 실행 · ⓘ=환경의존/비차단)")
    if soft:
        CON.say("ⓘ 비차단 항목 " + ", ".join(r["name"] for r in soft[:6])
                + " 은 이 환경에서 결과가 없었습니다 — 해당 소스를 쓰지 않을 뿐,"
                  " 백테스트는 정상 진행됩니다.")
    for r in bad[:4]:
        if r.get("tb"):
            CON.err(f"[{r['name']}] {r['err']}")
            for ln in r["tb"].strip().splitlines()[-6:]:
                CON.say("  " + ln)
    if bad and strict:
        raise RuleBreak(
            f"실경로 리허설 {len(bad)}건 실패 — 수집부 '배선'이 깨져 있습니다(환경 문제가 "
            f"아니라 코드 문제입니다). 이대로 실데이터를 돌리면 같은 자리에서 죽습니다: "
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
    base_map: Dict[str, float] = {}
    cover_map: Dict[str, Any] = {}
    # ── ① 진실값(mis)·커버리지를 먼저 확정한다 ──
    #    ★ 목표주가(TP12M)는 '보고서 시점 주가'에 정박해야 실제와 같은 모양이 된다.
    #      그러려면 가격이 예측보다 먼저 있어야 한다 — 그래서 순서를 이렇게 나눈다.
    for sid in stocks:
        base_map[sid] = float(rng.uniform(500, 5000))
        cover_map[sid] = rng.choice(n_analysts, size=int(rng.integers(4, 8)),
                                    replace=False)
        for y in fy_years:
            mis_map[(sid, y)] = float(np.clip(rng.normal(0.0, 0.30), -0.8, 0.8))
            act_rows.append(dict(stock_id=sid, fiscal_period=f"{y}FY",
                                 forecast_metric="EPS",
                                 actual_value=base_map[sid] * (1 + mis_map[(sid, y)]),
                                 actual_announcement_date=ts(f"{y+1}-03-20")))
    # ── ② 가격을 '날짜 단면' 형태로 ── 실경로와 동일한 자료형이어야 스모크가 의미를 갖는다
    px_rows, px_ser = [], {}
    for j, sid in enumerate(stocks):
        p = 10000.0 * float(rng_px.uniform(0.5, 3))
        arr = []
        for d in days:
            mis = mis_map.get((sid, d.year), 0.0)
            # 심어둔 알파의 세기. 이건 전략 파라미터가 아니라 **시험용 신호 세기**다.
            # 약하면 플라시보(R4)·지연(R5) 검사가 잡음에 묻혀 스모크가 증명력을 잃는다.
            pull = 0.0045 * mis                    # 갭과 같은 앵커 → 신호가 수익을 예측
            p *= math.exp(rng_px.normal(0.0002, 0.010) + pull)
            arr.append(p)
        sh = np.full(len(days), 1e6)
        arr = np.array(arr, float)
        if j == 0:                                  # 액면분할 1건 심기(보정 경로 검증)
            k = len(days) // 2
            arr[k:] /= 5.0
            sh[k:] *= 5.0
        px_ser[sid] = pd.Series(arr, index=days)
        px_rows.append(pd.DataFrame({"date": days, "code": sid, "close": arr,
                                     "volume": 1e5, "value": arr * 1e5,
                                     "mktcap": arr * sh, "shares": sh,
                                     "market": "KOSPI"}))
    # ── ③ 예측 — 같은 정보(est)를 EPS 와 TP12M 두 형태로 동시에 낸다 ──
    #    현실의 리포트가 바로 이렇다: 본문 표에 EPS 추정치, 표지에 목표주가.
    #    두 트랙 비교가 의미를 가지려면 스모크에서도 두 지표가 함께 있어야 한다.
    for sid in stocks:
        base = base_map[sid]
        for y in fy_years:
            mis = mis_map[(sid, y)]
            for a_i in cover_map[sid]:
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
                    p_now = float(px_ser[sid].asof(d0))
                    if np.isfinite(p_now):
                        r = fc_rows[-1].copy()
                        r["forecast_metric"] = "TP12M"
                        r["fiscal_period"] = "12M"      # 실경로(build_forecasts)와 동일
                        r["forecast_value"] = max(100.0, p_now * (1 + 0.5 * (est / base - 1)
                                                                 + 0.05))
                        fc_rows.append(r)
    fc = pd.DataFrame(fc_rows)
    actuals = pd.DataFrame(act_rows)
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
    panel, pmx = build_month_panel(S["have_dates"], S["xsec"], S["sec"], months, S["cal"])
    # (스모크는 ReturnHub 없이 단면 파생 경로를 태운다 — 폴백이 살아 있는지 검증)
    uni_df = universe_frame(panel, S["sec"])

    # ★ 스모크가 **이중 트랙 전 경로**를 그대로 태운다. 실행부에서 처음 도는 코드가
    #   하나도 없어야 한다 — 사용자 환경에서만 터지는 사고를 이 자리에서 끝낸다.
    _, track_metrics, mtab = plan_tracks(fc)
    TR: "OrderedDict[str, dict]" = OrderedDict()
    for m in track_metrics:
        TR[m] = build_track(m, fc, fcv, S["actuals"], S["cal"], months, cfg, pmx)
    if "EPS" not in TR:                    # 합성세계의 정답 트랙은 EPS 다
        TR["EPS"] = build_track("EPS", fc, fcv, S["actuals"], S["cal"], months, cfg, pmx)
    CON.debug(f"합성 분할보정 {pmx.n_adjusted}건 · 트랙 {list(TR)}")
    sc, W, cons = TR["EPS"]["scores"], TR["EPS"]["W"], TR["EPS"]["cons"]
    sig, ae, le = TR["EPS"]["sig"], TR["EPS"]["acc_ev"], TR["EPS"]["lead_ev"]
    if not len(ae) or not len(le):
        CON.err("합성 사건 생성 실패")
        return False
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
        for m, trk in TR.items():          # 트랙 평가 + 비교표까지 실물 실행
            eval_track(trk, panel, uni_df, None, mtab if m == "EPS" else None, cfg,
                       full_report=(m == "EPS"))
        track_compare(TR, None, "EPS")
        R_sensitivity(TR["EPS"]["ENG"], panel)
        R_subperiod(suites)
        R_concentration(suites)
        R_placebo(sig[sig["primary"]], panel, n_iter=60)
        R_lag(sig[sig["primary"]], panel)
        robustness_verdict()
        ROBUST.clear()
    else:
        # 빠른 스모크에서도 비교 경로를 실물로 태운다 — 표만 조용히(보고블록 생략).
        for m, trk in TR.items():
            eval_track(trk, panel, uni_df, None, None, cfg, full_report=False,
                       report=False)
        track_compare(TR, None, "EPS")
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
        coverage_verdict(fc_all, rep_raw, months)
        metric, track_metrics, mtab = plan_tracks(fc_all)
        cfg = SCGParams()
        fc = validate_forecasts(fc_all, asof=ts(BACKTEST_END) + pd.Timedelta(7, "D"))
        fcv = with_validity(fc, cfg)
        sig_months = [m for m in months if m >= fc["report_date"].min()]
        # 가격 행렬을 여기서 한 번만 만들고, 이후 백테스트·IC·목표가 만기·**모든 트랙**이
        # 전부 재사용한다 — 트랙을 늘려도 시장데이터 조회는 1회도 늘지 않는다.
        panel, PMX = build_month_panel(HUB.all_dates(), xsec, sec, sig_months, cal,
                                       rethub=RET, anchors=anchor_of)
        uni_df = universe_frame(panel, sec)

    TRACKS: "OrderedDict[str, dict]" = OrderedDict()
    with FLOW.part("S7", "SCG 엔진(사건→PIT점수→스마트컨센서스→신호)", budget_s=3600):
        for _m in track_metrics:
            TRACKS[_m] = build_track(_m, fc, fcv, actuals, cal, sig_months, cfg, PMX)
        if metric not in TRACKS:            # 방어: 주 트랙이 비면 만들어진 것 중 첫째로
            metric = next(iter(TRACKS))
        ENG = TRACKS[metric]["ENG"]
        sig, scores, W, cons = (TRACKS[metric]["sig"], TRACKS[metric]["scores"],
                                TRACKS[metric]["W"], TRACKS[metric]["cons"])

    with FLOW.part("S8", f"백테스트 — 전체 PIT 유니버스 + 시총하위{COMPARE_BOTTOM_N} "
                         f"(트랙 {len(TRACKS)}개)", budget_s=3600):
        # PIT 유니버스 = 그 달 단면에 실재한 보통주. 상장/폐지 목록 정확도에 의존하지 않는다.
        for _m, _trk in TRACKS.items():
            eval_track(_trk, panel, uni_df, bench, mtab if _m == metric else None,
                       cfg, full_report=(_m == metric))
        sig_full = TRACKS[metric]["sig_full"]
        suites_full = TRACKS[metric]["suites_full"]
        suites_small = TRACKS[metric]["suites_small"]

    with FLOW.part("S9", "트랙 비교 — 빠른판(TP12M) vs 정밀판(EPS·PDF)", budget_s=600,
                   critical=False, skip=len(TRACKS) < 2,
                   why="단일 트랙 (FORECAST_METRIC_MODE≠BOTH 또는 한쪽 커버리지 부족)"):
        track_compare(TRACKS, bench, metric)

    with FLOW.part("S10", "강건성 검사(주 트랙)", budget_s=3600 * 2, critical=False):
        R_sensitivity(ENG, panel)
        R_subperiod(suites_full)
        R_concentration(suites_full)
        R_placebo(sig_full, panel)
        R_lag(sig_full, panel)
        R_cost_stress(sig_full, panel,
                      nq=suites_full.get("SCG_LS", {}).get("nq"))
        if suites_small:
            R_subperiod(suites_small)
            R_concentration(suites_small)
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
        for _m, _trk in TRACKS.items():          # 트랙별 · 유니버스별 수익률 전부 저장
            allbt = {**(_trk.get("suites_full") or {}),
                     **{f"small_{k}": v for k, v in (_trk.get("suites_small") or {}).items()}}
            for st, bt in allbt.items():
                if isinstance(bt, dict) and not bt.get("empty", True):
                    p = os.path.join(outdir, f"returns_{_m}_{st}_{stamp}.csv")
                    bt["returns"].to_csv(p, index=False, encoding="utf-8-sig")
                    outs.append(p)
        logp = os.path.join(outdir, f"log_{stamp}.txt")
        write_atomic_text(logp, "\n".join(CON.buffer))
        outs.append(logp)
        DEPOT.snapshot_indexes()
        QUOTA.report()
        http_report()
        CIRCUIT.table()
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
            "scores": scores, "metric": metric, "tracks": TRACKS,
            "partial": DEADLINE.tripped}


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
