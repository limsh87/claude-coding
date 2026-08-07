#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  TCD v3 · 전략 1 — CORE-D  (U-MID 전환 코어)
#  트레이드오프 붕괴 탐지 / Trade-off Collapse Detection
#  백테스트 구간: 2016-08-01 ~ 2026-07-31 (10년)
#
#  ┌─ 찾는 것 ────────────────────────────────────────────────────────────────────────────────┐
#  │ "좋은 기업"이 아니라 "제약이 풀린 기업".                                                   │
#  │ 물량을 늘리면 단가를 깎아야 하고, 설비를 늘리면 ROIC 가 떨어지고, 사람을 늘리면 인당       │
#  │ 생산성이 희석된다. 질적 전환이란 이 대가를 더 이상 치르지 않게 된 상태다.                  │
#  │ 그래서 점수화 단위는 개별 지표가 아니라 트레이드오프 쌍(TP)이다:                           │
#  │     TP = max(z(개선의 크기), 0) × max(z(치르지 않은 대가의 크기), 0)                       │
#  │ 음수 절단이 핵심이다. z×z 로 두면 (-2)×(-2)=+4 가 되어 '매출 급감 + 회전 악화' 종목이      │
#  │ 최고점을 받는다. 이 부호버그가 v2 의 최대 결함이었다(§6.5).                                │
#  └──────────────────────────────────────────────────────────────────────────────────────────┘
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v3_01_core_d.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정
#     [1] 합성데이터 엔드투엔드 스모크   (실데이터 쓰기 전에 계산경로를 먼저 증명)
#     [2] CANARY K1~K7                   (실측 표. FAIL 항목에 의존하는 단계는 큐에서 제거)
#     [3] 데이터 수집  (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [4] 원장 무결성 감사               (보고서 ↔ 애널리스트 ↔ 종목 연결이 제대로 됐는가)
#     [5] PIT 유니버스(U-MID) + 연도별 감쇠 감사
#     [6] L1 피처패널 → L2 스코어 → L3 백테스트   (M0 → M1 → M2 → M3 단계별)
#     [7] 성과 검증표  (CAGR/MDD/Sharpe/Sortino/Calmar/회전율/우측꼬리 기여도)
#     [8] 강건성 검사 R0~R10
#     [9] 해석표 · 진단카드 · 런타임 감사 · 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다.  (이 블록 아래는 수정하지 않아도 됩니다)
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 로그에 한글로 명시합니다. 조용히 실패하지 않습니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#   ▸ 처음 한 번은 RUN_MODE="SMOKE" 로 돌려보세요. 네트워크·키 없이 30초 만에
#     백테스트~강건성~해석표까지 전 출력물이 나옵니다(합성데이터 예행연습).
#
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  ★이 전략의 핵심 입력 ──────────────────────────────────────────────
#
#    받는 법 (무료 · 1분):
#      1. https://opendart.fss.or.kr  접속
#      2. 우측 상단 [인증키 신청/관리] → [인증키 신청] → 이메일 인증
#      3. 발급된 40자리 키를 아래 따옴표 안에 붙여넣기
#    일 20,000건 호출 제한 (코드가 자동으로 스로틀하고 잔량을 표시합니다).
#
#    ▶ 없으면: TP_I1~I4, TP_P1/P2, V1/V2/V5 가 전부 죽습니다. 사실상 전략이 성립하지 않습니다.
DART_API_KEY = ""

# ── ② KRX 데이터 마켓플레이스  (2025-12 인증방식 변경 대응) ─────────────────────────────────────
#
#    받는 법 (무료):
#      1. https://data.krx.co.kr  접속 → 우측 상단 [회원가입]
#      2. 가입한 아이디 / 비밀번호를 그대로 아래에 입력
#
#    ▶ 없어도 실행은 됩니다. 다만 v3 에서는 '있으면 좋은 것'이 아닙니다 — 무엇이 약해지는지
#      정확히 알고 비우세요:
#        · PIT 시가총액 : pykrx 가 유일한 정확한 소스입니다. 없으면 '상장주식수를 과거로
#          고정하고 과거 종가를 곱하는' 근사로 대체되는데, 이건 유상증자·무상증자·감자를
#          반영하지 못합니다. 그 결과 자본 이벤트가 있었던 기업의 U-MID 밴드 편입이
#          체계적으로 틀어집니다 — 하필 TP_P1/TP_P2 가 겨냥하는 종목군입니다.
#          유니버스 계약 C13 이 그만큼 약해지고, 실행 중 '시총 소스 감사표'에 비중이 찍힙니다.
#        · 투자자별 수급(d3) : pykrx 경유입니다. 없으면 U 는 d1 단독으로 축소됩니다.
#        · 상장일·폐지일 자체는 FDR/KIND 로 확보되므로 생존자편향 제거(C2)는 영향받지 않습니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서
#      1회만 하고 모든 호출을 직렬화해 '스스로' 충돌하지는 않지만, 바깥은 막을 수 없습니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

#    (선택) KRX Open API 인증키. https://data-dbg.krx.co.kr 에서 발급.
#    ⚠ 키만으론 즉시 안 됩니다 — 엔드포인트별 '이용신청'이 따로 필요하고 승인에 하루쯤 걸립니다.
KRX_OPENAPI_KEY = ""

# ── ③ 구글드라이브 캐시  ★★★ 절대 1원칙 ★★★ ──────────────────────────────────────────────────
#
#    이 코드는 기존 캐시·인덱스를 **절대 삭제하거나 덮어쓰지 않습니다.** 약속이 아니라 구조로
#    보장합니다:
#      · 인덱스의 진실은 append-only JSONL 저널입니다. 기존 줄을 다시 쓰지 않으므로
#        코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없습니다.
#      · index.parquet 은 저널의 파생물(캐시)일 뿐이고, 재생성 전 항상 타임스탬프 백업합니다.
#      · 컬럼은 합집합으로만 확장합니다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않습니다.
#      · 원본 blob 은 내용해시 경로에 쓰므로 같은 내용은 재기록조차 하지 않습니다.
#      · 이미 드라이브에 있던 리포트는 "옮기지 않고 경로만 등록"합니다(adopt-by-reference).
#      · 삭제 API 자체가 없습니다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 합니다.
#
#    GDRIVE_ROOT       : 캐시 최상위 루트
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략에서도 그대로 재활용 가능한 원본/정제본
#                        (가격·DART원문·리포트PDF·애널리스트원장 …)
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유의 피처/스코어/백테스트 산출물
#                        ★ v2 의 "tcd_v2" 와 다른 이름입니다. v2 산출물을 건드리지 않습니다.
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"              # → {ROOT}/_shared          (공용 · 전 전략 재사용)
GDRIVE_PRIVATE_NS = "tcd_v3_core_d"        # → {ROOT}/tcd_v3_core_d    (전용 · 이 전략)

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요.
#      재귀 스캔해서 "등록만" 합니다. 파일을 옮기거나 지우지 않습니다. 경로/크기만 기록합니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    "/content/drive/MyDrive/한경컨센서스",
    "/content/drive/MyDrive/네이버리서치",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
LOCAL_CACHE_ROOT = "./tcd_cache"

# ── ④ 백테스트 구간 ────────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑤ 실행 단계 (§2 단계 게이트) ───────────────────────────────────────────────────────────────
#    "M0"  벌크재무 + 가격 + 상폐 + PIT유니버스        → TP_I2·TP_I4 + V1/V2/V5/V6
#    "M1"  + 현금흐름표·IC/ROIC + 자사주·배당 공시     → TP_I1, TP_P1, TP_P2, b4
#    "M2"  + 직원현황(annual)                          → TP_I3
#    "M3"  + 수급 + U층(d1/d3)                         → 완전체 Signal
#    "ALL" M3 와 동일 + 강건성 R0~R10 전체
#    ▶ M0 에서 이미 백테스트 결과가 한 번 나옵니다. 전부 모은 뒤 한 번에 돌리지 않습니다.
STAGE = "ALL"

# ── ⑥ 실행 모드 ────────────────────────────────────────────────────────────────────────────────
#    "SMOKE"  합성데이터로 전체 출력물 예행연습(30초). 네트워크/키 불필요. ★ 처음엔 이걸로.
#    "FULL"   스모크 → 실경로 리허설 → 실데이터 수집 → 백테스트 → 강건성  (권장)
#    "CACHED" 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트
RUN_MODE = "FULL"

# ── ⑦ 성능 / 자원 ──────────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12      # 네트워크 병렬(스레드). 403/429 가 뜨면 8 이하로 줄이세요.
N_WORKERS_CPU  = 0       # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {       # 소스별 초당 요청 상한 — 차단 방지. 낮출수록 안전/느림.
    "dart":     8.0,
    "hankyung": 2.5,
    "naver":    3.0,
    "krx":      2.0,
    "kind":     2.0,
    "generic":  3.0,
}
MEM_BUDGET_GB = 6.0      # 이 값을 넘길 것 같으면 청크 처리로 자동 전환

# ── ⑧ 유니버스 U-MID (§5 · 계약 C13) ───────────────────────────────────────────────────────────
#    시총 랭크 251~1400 · 20일 평균거래대금 ≥ 3억 · 상장 후 250거래일 경과
#    ★ 이 밴드는 매 리밸런싱 시점 t 의 '당시' 값으로 재산출합니다(PIT). 현재 시총으로 과거를
#      자르면 "시총 800억이 8,000억이 된 기업" 이 지금은 중대형주라서 유니버스에서 빠집니다.
#      성공 사례를 정의상 제거하는 것이고, 우측 꼬리 의존 전략에서 이는 조용한 거짓 음성입니다.
UNIVERSE_MODE       = "auto"      # "rank"(절대랭크) | "pct"(분위) | "auto"(감쇠감사 결과로 자동)
UNIVERSE_RANK_LO    = 251
UNIVERSE_RANK_HI    = 1400
UNIVERSE_PCT_LO     = 0.10        # UNIVERSE_MODE="pct" 일 때 시총 상위 10% ~
UNIVERSE_PCT_HI     = 0.55        #                              ~ 55%
UNIVERSE_MIN_ADTV   = 3e8         # 20일 평균거래대금 하한 (3억)
UNIVERSE_SEASON_DAYS = 250        # 상장 후 거래일

# ── ⑨ 포지션 / 사이징 (§8.3 — 드로다운 한가운데서 정하지 않도록 코드 상수로 못박음) ────────────
PORTFOLIO_TOP_PCT     = 0.05      # 신호 상위 5% 진입
PORTFOLIO_MAX_NAMES   = 25
PORTFOLIO_MIN_NAMES   = 5
POS_MAX_WEIGHT        = 0.12      # 종목당 최대 비중
POS_MIN_WEIGHT        = 0.02
POS_ADV_PARTICIPATION = 0.10      # 20일 평균거래대금의 10% 이내로 종목당 금액 상한
HOLD_MAX_MONTHS       = 24
ACCOUNT_KRW           = 30_000_000        # 소액계좌 가정 (최소주문/유동성 제약 계산용)
BREADTH_FLOOR_PCT     = 0.50      # 하한선: 활성 센서군 각각의 셀 내 백분위 ≥ 50th
                                  # "모든 축이 상위"가 아니라 "빈 축이 없을 것"

# ── ⑩ 애널리스트 리포트 (한경컨센서스 · 네이버금융리서치) ──────────────────────────────────────
#    사용자 드라이브에 이미 캐시된 리포트를 먼저 흡수하고, 부족분만 신규 수집합니다.
#    수집분은 공용 인덱스에 저장되어 다른 전략에서도 그대로 재사용됩니다.
RESEARCH_COLLECT      = True      # False 면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES      = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF = True      # PDF 원문까지 받을지 (애널리스트/목표주가 정확도↑, 용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0    # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR = 30000  # 연간 수집 목표. 달성/미달을 감사표에 정직하게 표시합니다.
#    ▶ 사양 §8.1 의 U 는 mean(z(d1), z(d3)) 입니다. 아래를 True 로 두면 리포트 기반 축
#      d2(목표주가 상향 리비전) · d4(커버리지 변화) 를 U 에 추가합니다.
#      사양 확장이므로 R5 절제에서 기여도를 반드시 확인하세요(기여가 없으면 False 로).
USE_RESEARCH_AXIS = True

# ── ⑪ 기타 ────────────────────────────────────────────────────────────────────────────────────
SEED = 20260807                   # C8 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = False     # §11 킬 기준 위반 시 즉시 중단할지.
                                  # False = 킬을 '기록'하고 남은 검사를 마저 돌려 전체 그림을 보여줌
                                  #         (판정은 그대로 KILL 로 보고합니다 — 통과시키지 않습니다)
WALL_CLOCK_BUDGET_MIN = 240.0     # §2 하드 제약 4시간. 초과 시 경고(중단 아님)

# ═══════════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "CORE_D"
STRATEGY_NAME = "전략 1 · CORE-D (U-MID 전환 코어)"
BUILD_VERSION = "v3.0.0"

# §2 단계별 누적 예산(분). 계측은 실측으로만 하고 추측하지 않는다(C10).
STAGE_BUDGET_MIN = {"CANARY": 20.0, "M0": 50.0, "M1": 68.0, "M2": 110.0,
                    "M3": 122.0, "ALL": 167.0}
STAGE_ORDER = ["M0", "M1", "M2", "M3"]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [02/22]  01_bootstrap.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [03/22]  02_kernel.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



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


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [04/22]  03_util.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



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


def as_ts_series(s) -> pd.Series:
    """★ 혼합 포맷 방어. pandas 2.x 는 **첫 비결측 원소에서 포맷 하나를 추론해 전체에 엄격
    적용**한다. 그래서 ['2016-01-15 00:00:00', '2016-01-15'] 처럼 섞이면 뒤쪽이 전부 NaT 이
    되고, errors='coerce' 라 예외도 안 난다.

    이 모양이 나오는 곳이 하필 **재실행 경로**다: 드라이브 캐시에서 읽은 파싱 완료
    Timestamp + 이번에 새로 수집한 문자열을 concat 하면 정확히 이렇게 된다. 실측으로
    보고서 원장 1,500건 중 1,000건이 '날짜 무효'로 조용히 탈락했다.
    → 1차 추론에서 실패한 원소만 골라 mixed 포맷으로, 그래도 안 되면 원소별로 재시도한다.
      실패분에만 적용하므로 정상 경로의 비용은 0 이다.
    """
    ser = pd.Series(s)
    out = pd.to_datetime(ser, errors="coerce")
    try:
        raw_ok = ser.notna() & (ser.astype(str).str.strip().str.lower()
                                .isin(("", "nan", "none", "nat", "null")) == False)  # noqa: E712
        bad = out.isna() & raw_ok
        if bad.any():
            try:
                out = out.astype("datetime64[ns]")
            except Exception:
                pass
            try:
                out.loc[bad] = pd.to_datetime(ser[bad], errors="coerce", format="mixed")
            except (TypeError, ValueError):
                pass
            bad2 = out.isna() & raw_ok
            if bad2.any():
                out.loc[bad2] = pd.Series(
                    [pd.to_datetime(x, errors="coerce") for x in ser[bad2]],
                    index=ser.index[bad2])
    except Exception:
        pass
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
    d = re.sub(r"\D", "", s)
    if d and len(d) <= 6:
        cand = d.zfill(6)
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
    # ★ 클리핑 경계는 **로버스트 추정치**로 잡는다. 평균/표준편차로 잡으면 이상치 자신이
    #   경계를 부풀려 1회 윈저로는 흡수되지 않는다. 실측: N(0,1) 99개 + 1e6 한 개를 넣으면
    #   ±2σ 윈저 후에도 z 최대가 9.95 다(윈저를 안 한 것과 거의 같다). 재무 비율은 분모가
    #   작을 때 이런 값을 일상적으로 만들므로, 그 한 종목이 셀 전체의 z 를 지배하게 된다.
    #   중앙값 ± k·1.4826·MAD 로 잡으면 정규분포에서는 ±kσ 와 사실상 같고(의미 보존),
    #   이상치에는 무너지지 않는다. MAD 가 0 인 셀(값의 과반이 동일 — clip TP 에서 흔하다)만
    #   표준편차로 되돌린다.
    med = g.transform("median")
    mad = (v - med).abs().groupby(grp, observed=True, dropna=False).transform("median") * 1.4826
    scale = mad.where(mad > 0, sd0)
    w = v.clip(lower=med - k * scale, upper=med + k * scale)      # ① winsorize (로버스트 경계)
    w = w.where(scale > 0, v)

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


def tp_signed_product(z_improve: pd.Series, z_nopay: pd.Series) -> pd.Series:
    """★ v2 사양의 원형 — TP = z(a) × z(b). **이 전략은 이것을 쓰지 않는다.**

    보존하는 이유는 R5 절제에서 "부호버그가 있었을 때 무슨 일이 벌어지는가"를 실측으로
    보여주기 위해서다(§6.5). 실전 경로에서 호출되면 안 되므로 이름을 바꿔 두었다.

    부호버그: z(a)=-2(매출 급감), z(b)=-2(회전 악화) → TP=+4 = 최고점.
    횡단면 z 이므로 유니버스의 약 25%가 양쪽 음수 → 양의 TP 를 얻는다.
    결과적으로 상위 분위가 '매출 급감 + 회전 악화' 종목으로 오염된다.
    """
    a = pd.to_numeric(z_improve, errors="coerce")
    b = pd.to_numeric(z_nopay, errors="coerce")
    return (a * b).astype("float32")


def nonempty(x) -> bool:
    """DataFrame/Series/배열/None 을 안전하게 '내용이 있는가'로 판정한다.

    ★ 왜 함수로 만드는가: `a() or b()` 는 DataFrame 에서
      "ValueError: The truth value of a DataFrame is ambiguous" 로 죽는다.
      그런데 이 버그는 **a() 가 None 을 반환하는 환경에서는 숨는다**(None or b 는 합법).
      즉 '소스가 막힌 개발 환경에서는 통과하고, 소스가 살아 있는 실환경에서만 터진다'.
      실제로 CANARY K4 가 정확히 그렇게 죽었다 — 네트워크가 차단된 곳에서 전부 통과했다.
      쓰기 쉬운 잘못된 관용구(`or`)를 대체할 쓰기 쉬운 올바른 관용구가 없으면 재발한다.
    """
    if x is None:
        return False
    if isinstance(x, (pd.DataFrame, pd.Series, pd.Index, np.ndarray)):
        return len(x) > 0
    try:
        return bool(len(x))
    except TypeError:
        return bool(x)


def first_nonempty(*sources, min_len: int = 1):
    """폴백 체인. 각 source 는 호출가능(지연평가) 또는 값.

    비어 있지 않은 첫 결과를 돌려주고, 전부 비면 None. 예외는 그 소스만 건너뛴다.
        d = first_nonempty(lambda: _px_fdr(c, s, e), lambda: _px_naver(c, s, e))
    """
    for s in sources:
        try:
            v = s() if callable(s) else s
        except Exception:                                   # noqa — 소스 하나의 실패로 체인을 죽이지 않는다
            continue
        if nonempty(v) and (not hasattr(v, "__len__") or len(v) >= min_len):
            return v
    return None


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


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [05/22]  04_vault.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



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
                # ★★ uid 는 **행 내용에서만** 유도해야 한다. 예전 구현은 concat 후의 '위치 i' 를
                #   해시에 넣었는데, 그 위치는 저널이 길어질수록 달라진다. 그러면 같은 레거시
                #   행이 실행할 때마다 다른 uid 를 받아 drop_duplicates 를 통과하고, 인덱스가
                #   매 실행 두 배로 불어난다. 데이터가 사라지진 않지만 인덱스는 망가진다 —
                #   사용자의 절대 1원칙에 정면으로 걸린다.
                #   (실측: 같은 레거시 CSV 3행이 두 번째 실행에서 6행이 되었다)
                #   또 idx.iloc[i] 를 행마다 부르면 40만 행 레거시에서 수 분이 걸린다. 벡터화한다.
                sub = idx.loc[miss, fill_src].astype(str) if fill_src else \
                    pd.DataFrame(index=idx.index[miss])
                key = (sub.agg("\x1f".join, axis=1) if len(fill_src)
                       else pd.Series("", index=sub.index))
                # 내용이 완전히 같은 행이 여러 개면 파일 내 등장 순서로만 구분한다
                # (그 순서는 같은 파일을 같은 방식으로 읽는 한 실행 간 재현된다).
                occ = key.groupby(key).cumcount()
                idx.loc[miss, "uid"] = [sha1_str("legacy", k, o) for k, o in zip(key, occ)]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 내용 기반 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지지도, 실행마다 중복되지도 않게 — "
                         f"기존 기록 보존).")
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
    """여유 디스크(GB). os.statvfs 는 Windows 에 없다 — shutil.disk_usage 가 크로스플랫폼이다."""
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        pass
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return float("nan")


def discover_drive_dirs(cache_root: str) -> List[str]:
    """플랫폼별 구글드라이브·기존 캐시 후보 경로를 자동 탐지한다.

    ★ 왜 필요한가: GDRIVE_ADOPT_DIRS 기본값이 Colab 경로(/content/...)라, 로컬 주피터에서
      돌리면 "흡수할 파일을 찾지 못했습니다" 만 뜨고 사용자가 이미 모아둔 리포트가
      통째로 무시된다. 사용자에게 경로를 손으로 고치라고 요구하는 대신 흔한 위치를 훑는다.
      (읽기 전용 스캔이며 파일을 옮기거나 지우지 않는다 — adopt-by-reference)
    """
    cands: List[str] = []
    home = os.path.expanduser("~")
    if cache_root:
        cands += [cache_root, os.path.dirname(os.path.abspath(cache_root))]
    if sys.platform.startswith("win"):
        for drv in "GHIJKDEF":
            cands += [f"{drv}:\\내 드라이브", f"{drv}:\\My Drive", f"{drv}:\\"]
        cands += [os.path.join(home, "Google Drive"), os.path.join(home, "GoogleDrive"),
                  os.path.join(home, "Documents"), os.path.join(home, "Downloads")]
    elif sys.platform == "darwin":
        cands += [os.path.join(home, "Google Drive"),
                  os.path.join(home, "Library/CloudStorage")]
    else:
        cands += ["/content/drive/MyDrive", os.path.join(home, "Google Drive"),
                  os.path.join(home, "GoogleDrive")]
    out, seen = [], set()
    for c in cands:
        try:
            if not c or not os.path.isdir(c):
                continue
            r = os.path.realpath(c)
            # 드라이브 루트 전체 스캔은 너무 비싸다 — 하위의 그럴듯한 폴더만 고른다
            if len(r) <= 3:
                for sub in os.listdir(c)[:60]:
                    p = os.path.join(c, sub)
                    if os.path.isdir(p) and any(
                            k in sub.lower() for k in ("tcd", "research", "report", "consensus",
                                                       "리서치", "리포트", "컨센서스", "quant", "qunat")):
                        rp = os.path.realpath(p)
                        if rp not in seen:
                            seen.add(rp); out.append(p)
                continue
            if r not in seen:
                seen.add(r); out.append(c)
        except Exception:
            continue
    return out


VAULT: Optional[Vault] = None


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [06/22]  05_http.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



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


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [07/22]  06_statv3.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  v3 통계 원시연산 — TP 조립 / 셀 정규화 / 롤링 적률 / 런타임 계측                    ║
# ║                                                                                          ║
# ║  이 블록은 v3 에서 **바뀐 것만** 담는다. 바뀐 이유가 전부 실측 사고이므로 주석에          ║
# ║  "무엇이 어떻게 터졌는가"를 남긴다.                                                       ║
# ║    §6.5  TP 부호버그 → clip(z,0) 강제                                                     ║
# ║    §7    groupby.apply 금지 → 이중계산 폴백                                               ║
# ║    §6.4  스트라이드 창 쌓기 금지 → 롤링 적률 닫힌해                                        ║
# ║    §2    모든 단계를 계측한다. 추측 금지(C10).                                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── §2 런타임 계측 (C10) ────────────────────────────────────────────────────────────────────
RUNTIME_LOG: List[dict] = []
_RUNTIME_LK = threading.RLock()


@contextmanager
def Stage(name: str, budget_min: Optional[float] = None):
    """with Stage("M0.ingest_bulk"): ... 형태. 종료 시 RUNTIME_LOG 에 append.

    PIPE.stage 와 역할이 다르다. PIPE.stage 는 '실패 지점 국소화'가 목적이고,
    이건 '§2 예산표 대비 실측'이 목적이다. 둘 다 필요하다 — 어느 단계가 예산의 몇 배를
    썼는지는 실패와 무관하게 알아야 하고, 그게 v2 가 16~40시간으로 폭발한 뒤 얻은 교훈이다.
    """
    t0 = time.time()
    rss0 = _rss_mb()
    err = ""
    try:
        yield
    except BaseException as e:                                  # noqa
        err = f"{type(e).__name__}: {str(e)[:120]}"
        raise
    finally:
        dt = time.time() - t0
        rec = {"stage": name, "sec": dt, "min": dt / 60.0,
               "budget_min": budget_min, "rss_mb": _rss_mb(), "d_rss_mb": _rss_mb() - rss0,
               "err": err}
        with _RUNTIME_LK:
            RUNTIME_LOG.append(rec)
        if budget_min and dt / 60.0 > budget_min * 1.5:
            LOG.warn(f"[C10] '{name}' 이 예산 {budget_min:.0f}분의 "
                     f"{dt/60.0/budget_min:.1f}배({dt/60.0:.1f}분)를 썼습니다. "
                     f"중단하지 않고 계속 진행합니다 — 마지막 런타임 표에서 확인하세요.")


def _rss_mb() -> float:
    """상주 메모리(MB). 리눅스·macOS·Windows 전부에서 동작한다.

    ★ 예전엔 /proc 과 resource 에만 의존해 **Windows 에서 전부 NaN** 이었다. 런타임 표의
      RSS 열이 통째로 '-' 로 나와 메모리 감사가 무의미해진다 — 하필 Colab 아닌 로컬
      주피터가 메모리 압박을 가장 먼저 받는 환경이다. psutil 은 선택 의존이므로
      없어도 되는 경로를 셋 다 갖춘다.
    """
    try:
        with open("/proc/self/statm") as f:                       # Linux
            return int(f.read().split()[1]) * (os.sysconf("SC_PAGE_SIZE") / 1e6)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:                                                       # Windows: PSAPI
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = _PMC()
            c.cb = ctypes.sizeof(_PMC)
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.WorkingSetSize / 1e6
        except Exception:
            pass
    try:
        import psutil                                              # 있으면 가장 정확
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        pass
    try:
        import resource                                            # macOS/BSD 폴백(최대치)
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / 1e6 if sys.platform == "darwin" else ru / 1e3
    except Exception:
        return float("nan")


def report_runtime_v3(total_budget_min: float = 240.0):
    if not RUNTIME_LOG:
        return
    LOG.banner("런타임 감사 (C10) — §2 예산표 대비 실측",
               "추측하지 않는다. 어느 단계가 예산을 얼마나 썼는지 실측으로만 판정한다.")
    rows, tot = [], 0.0
    for r in RUNTIME_LOG:
        tot += r["sec"]
        bud = r.get("budget_min")
        verdict = "—"
        if bud:
            ratio = (r["min"] / bud) if bud > 0 else 0
            verdict = "✔ 예산 내" if ratio <= 1.0 else f"❗ {ratio:.1f}배 초과"
        rows.append([_trunc(r["stage"], 34), f"{r['sec']:8.2f}", f"{r['min']:6.2f}",
                     (f"{bud:.0f}분" if bud else "-"), verdict,
                     f"{r['rss_mb']:,.0f}" if np.isfinite(r["rss_mb"]) else "-",
                     f"{r['d_rss_mb']:+,.0f}" if np.isfinite(r["d_rss_mb"]) else "-",
                     _trunc(r["err"], 26)])
    rows.append(["── 합계 ──", f"{tot:8.2f}", f"{tot/60:6.2f}",
                 f"{total_budget_min:.0f}분",
                 "✔ 예산 내" if tot / 60 <= total_budget_min
                 else "❗ 초과 — 검사를 줄이지 말고 구조를 고칠 것(§11-8)", "", "", ""])
    LOG.table(rows, ["단계", "실측(초)", "실측(분)", "예산", "판정", "RSS(MB)", "ΔRSS", "예외"],
              ["l", "r", "r", "r", "l", "r", "r", "l"])


# ── 셀 폴백 사다리를 탄 z-score ─────────────────────────────────────────────────────────────
def xsec_z_fb(v: pd.Series, cells: pd.Series, cells_fb: Optional[Sequence[pd.Series]] = None,
              min_n: int = CELL_MIN_N, tag: str = "") -> pd.Series:
    """셀 내 z. 표본이 부족한 셀은 상위 셀로 내려간다.

    ★ 이 폴백이 없으면 조용히, 그리고 치명적으로 망가진다. 셀 = (연월 × 산업중분류 × 규모3단계)
      는 실데이터에서 셀당 중앙 크기가 한 자릿수인 구간이 많다. min_n 미달 셀을 전부 NaN 으로
      떨어뜨리면 **TP 와 U 가 거의 전부 결측**이 되고, 그러면 E 는 소수 종목만 남긴 채로
      계산되며 백테스트는 아무 예외 없이 '보유 1종목' 포트폴리오를 만든다.
      (실측: 폴백 없이 합성 80종목×36개월에서 TP 유효 관측이 2,880행 중 114행이었다)
    """
    out = xsec_z(v, cells, min_n=min_n)
    fine_ok = out.notna()
    for fb in (cells_fb or []):
        if not out.isna().any():
            break
        out = out.where(out.notna(), xsec_z(v, fb, min_n=min_n))
    if tag:
        obs = pd.to_numeric(v, errors="coerce").notna()
        n_obs = int(obs.sum())
        if n_obs:
            # 폴백 사용 = 관측은 있는데 1단계 셀에서는 못 냈고 상위 셀에서 냈다
            CELL_FALLBACK_STATS[f"z:{tag}"] += int((obs & ~fine_ok & out.notna()).sum())
            CELL_FALLBACK_STATS[f"z:{tag}__n"] += n_obs
    return out


# ── §6.5 TP 조립 — 부호버그 수정 (v3 최우선 교정) ───────────────────────────────────────────
def tp(a: pd.Series, b: pd.Series, cells: pd.Series,
       cells_fb: Optional[Sequence[pd.Series]] = None, min_n: int = CELL_MIN_N) -> pd.Series:
    """트레이드오프 쌍 = max(z(개선),0) × max(z(대가회피),0).

    ★ v2 사양은 z(a)*z(b) 였다. 횡단면 z 이므로 유니버스의 약 25%가 양쪽 음수이고,
      그 종목들이 음수×음수=양수로 상위 분위를 차지했다. 즉 '매출 급감 + 회전 악화'가
      '매출 증가 + 회전 유지'와 같은 점수를 받았다. 예외는 나지 않는다 — 순위만 조용히 틀린다.

    v3 의 의미론: 개선이 없거나(za<=0) 대가를 치렀으면(zb<=0) 정확히 0.
      "제약이 풀렸다"는 주장은 두 조건이 동시에 성립할 때만 참이므로 이게 정의에 맞다.

    ★ 결측 전파 규칙: 한쪽이라도 NaN 이면 결과도 NaN 이다. 0 으로 채우면
      "대가를 안 치렀다"는 거짓 주장이 된다(관측이 없는 것과 대가가 0인 것은 다르다).
      clip 은 NaN 을 보존하므로 아래 구현은 자동으로 이 규칙을 만족한다.
    """
    za = xsec_z_fb(a, cells, cells_fb, min_n=min_n)
    zb = xsec_z_fb(b, cells, cells_fb, min_n=min_n)
    out = za.clip(lower=0.0) * zb.clip(lower=0.0)
    return out.astype("float32")


def tp_rank(a: pd.Series, b: pd.Series, cells: pd.Series,
            cells_fb: Optional[Sequence[pd.Series]] = None,
            min_n: int = CELL_MIN_N) -> pd.Series:
    """대안 정의: rank_pct(a) × rank_pct(b).  [0,1] 구간이라 부호 문제가 정의상 소멸한다.

    §6.5 는 둘 중 무엇을 쓰든 R5 절제에서 두 방식을 비교해 리포트에 명시하라고 요구한다.
    clip 방식과 다른 점: clip 은 '평균 이하'를 전부 0 으로 뭉개지만 rank 는 순서를 보존한다.
    → clip 은 더 선택적(상위 25%만 양수), rank 는 더 연속적. 어느 쪽이 옳은지는 실측 문제다.
    """
    def _r(v):
        out = xsec_rank_pct(v, cells, min_n=min_n)
        for fb in (cells_fb or []):
            if not out.isna().any():
                break
            out = out.where(out.notna(), xsec_rank_pct(v, fb, min_n=min_n))
        return out
    return (_r(a) * _r(b)).astype("float32")


def tp_dispatch(mode: str, a: pd.Series, b: pd.Series, cells: pd.Series,
                cells_fb: Optional[Sequence[pd.Series]] = None,
                min_n: int = CELL_MIN_N) -> pd.Series:
    if mode == "rank":
        return tp_rank(a, b, cells, cells_fb, min_n)
    if mode == "signed":
        # R5 전용 — v2 의 부호버그를 그대로 재현해 '무슨 일이 벌어졌는가'를 실측으로 보여준다
        return tp_signed_product(xsec_z_fb(a, cells, cells_fb, min_n),
                                 xsec_z_fb(b, cells, cells_fb, min_n))
    return tp(a, b, cells, cells_fb, min_n)


# ── §7 셀 정규화 — 벡터화 폴백 ──────────────────────────────────────────────────────────────
CELL_FALLBACK_STATS: Counter = Counter()


def cell_rank(df: pd.DataFrame, col_or_series, keys: Sequence[str],
              fallback_keys: Sequence[str], min_n: int = CELL_MIN_N,
              tag: str = "") -> pd.Series:
    """셀 내 백분위 랭크. 표본이 부족한 셀은 상위 셀로 폴백한다.

    ★ 이중계산이 조건분기보다 100배 빠르다. groupby.apply 로 셀마다 파이썬 함수를 부르면
      v2 에서 720,000회 호출에 24분이 걸렸다. fine/coarse 를 둘 다 통째로 계산한 뒤
      np.where 로 고르는 게 총 연산량은 두 배지만 전부 C 레벨이라 압도적으로 싸다.

    ★ 판정 기준은 '셀 크기'가 아니라 '그 센서의 유효 관측 수'다. 셀에 종목이 30개 있어도
      그 센서를 관측한 종목은 5개뿐일 수 있고(신규상장·비DART·계정 미매칭), 그때
      크기만 보고 통과시키면 5개짜리 랭크가 만들어져 백분위가 무의미해진다.
    """
    v = (pd.to_numeric(df[col_or_series], errors="coerce") if isinstance(col_or_series, str)
         else pd.to_numeric(col_or_series, errors="coerce"))
    v = v.replace([np.inf, -np.inf], np.nan)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=df.index, dtype="float32")

    def _key(ks):
        # 카테고리 dtype 을 그대로 groupby 하면 observed=False 기본값에서 카티션 폭발이 난다.
        # (date × industry × size 조합이 미관측분까지 전부 만들어져 메모리를 먹는다)
        s = None
        for k in ks:
            c = df[k].astype(str) if k in df.columns else pd.Series("NA", index=df.index)
            s = c if s is None else (s + "\x1f" + c)
        return (s if s is not None else pd.Series("ALL", index=df.index)).to_numpy()

    kf = _key(keys)
    gf = v.groupby(kf, observed=True, dropna=False)
    fine = gf.rank(pct=True, method="average")
    n_fine = gf.transform("count")

    # ★ 이중계산은 조건분기보다 빠르지만, '폴백이 필요 없을 때'까지 상위 셀을 계산할 이유는
    #   없다. assemble_score 1회가 cell_rank 를 30회 넘게 부르고 강건성 스위트가 그걸
    #   40회 반복하므로, 이 분기 하나가 전체의 절반을 좌우한다.
    short = (n_fine < min_n) & v.notna()
    if not bool(short.any()):
        r = fine.where(v.notna())
        if tag:
            CELL_FALLBACK_STATS[tag] += 0
            CELL_FALLBACK_STATS[f"{tag}__n"] += int(v.notna().sum())
        return r.astype("float32")

    kc = _key(fallback_keys)
    gc = v.groupby(kc, observed=True, dropna=False)
    coarse = gc.rank(pct=True, method="average")
    n_coarse = gc.transform("count")

    out = np.where(n_fine.to_numpy() >= min_n, fine.to_numpy(), coarse.to_numpy())
    out = np.where(n_coarse.to_numpy() >= min_n, out, np.nan)   # 상위 셀조차 부족하면 결측
    used_fallback = int(((n_fine < min_n) & (n_coarse >= min_n) & v.notna()).sum())
    n_obs = int(v.notna().sum())
    if n_obs:
        CELL_FALLBACK_STATS[tag or "?"] += used_fallback
        CELL_FALLBACK_STATS[f"{tag or '?'}__n"] += n_obs
    return pd.Series(out, index=df.index, dtype="float32")


def report_cell_fallback(threshold: float = 0.30):
    """§7: 폴백 발생 비율을 로깅하고 30%를 넘으면 셀 정의를 재검토한다."""
    tags = sorted({k[:-3] for k in CELL_FALLBACK_STATS if k.endswith("__n")})
    if not tags:
        return
    rows, worst = [], 0.0
    for t in tags:
        n = CELL_FALLBACK_STATS.get(f"{t}__n", 0)
        f = CELL_FALLBACK_STATS.get(t, 0)
        r = f / max(n, 1)
        worst = max(worst, r)
        rows.append([t, f"{n:,}", f"{f:,}", f"{100*r:.1f}%",
                     "✔" if r <= threshold else "❗ 셀 정의 재검토"])
    LOG.table(rows, ["센서", "유효관측", "폴백 사용", "폴백률", "판정"],
              ["l", "r", "r", "r", "l"],
              title=f"셀 폴백 감사 (§7) — 폴백률 {threshold:.0%} 초과 시 셀 정의를 재검토")
    if worst > threshold:
        LOG.warn(f"최대 폴백률 {100*worst:.0f}% 가 기준({threshold:.0%})을 넘습니다. "
                 f"셀이 너무 잘게 쪼개져 있다는 뜻입니다 — 산업 분류 단위를 넓히거나 "
                 f"size_bucket 단계를 줄이세요. 지금 상태로는 '셀 내 정규화'가 "
                 f"사실상 '전체 정규화'로 퇴화한 종목이 그만큼 됩니다.")


# ── §6.4 롤링 회귀 — 적률 방식 ──────────────────────────────────────────────────────────────
def rolling_ols_moment(Y: np.ndarray, X: np.ndarray, window: int,
                       ridge: float = 1e-8) -> np.ndarray:
    """(N,T) y 와 (N,T,K) X 에 대해 길이 W 롤링 OLS 의 '창 마지막 시점 잔차'를 반환.

    ★ §6.4 가 금지하는 것: np.lib.stride_tricks 로 창을 쌓는 방식. (N, T-W+1, W, K) 배열이
      실체화되면서 2,600종목 × 2,400일 × 120창 × 2변수 = 8GB 를 잡아 OOM 으로 죽는다.
    ★ §6.4 가 금지하는 것 ②: rolling(W).apply(파이썬 콜백). 종목·시점마다 파이썬 호출이라
      15분짜리가 3시간이 된다.
    ★ v3 방식: 교차곱 컬럼을 먼저 만들고 rolling sum 으로 XtX/Xty 원소를 직접 누적한다.
      메모리는 O(N·T·K²) 가 아니라 창을 실체화하지 않으므로 O(N·T·K²) 의 '누적합' 뿐이고,
      역행렬은 K×K(보통 2×2) 소행렬 배치라 사실상 공짜다.

    반환: (N, T) 잔차. 창이 안 차거나 결측이 섞이면 NaN.
    """
    Y = np.asarray(Y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    N, T = Y.shape
    K = X.shape[2]
    out = np.full((N, T), np.nan, dtype=np.float64)
    if T < window or window < K + 2:
        return out

    ok = np.isfinite(Y) & np.isfinite(X).all(axis=2)          # (N,T)
    Yc = np.where(ok, Y, 0.0)
    Xc = np.where(ok[:, :, None], X, 0.0)

    def _rsum(A):
        """마지막 축 T 에 대한 길이 window 이동합. 누적합 차분 — O(N·T) 이고 창을 안 만든다."""
        cs = np.cumsum(A, axis=1)
        r = np.empty_like(cs)
        r[:, :window - 1] = np.nan
        r[:, window - 1] = cs[:, window - 1]
        r[:, window:] = cs[:, window:] - cs[:, :-window]
        return r

    n_ok = _rsum(ok.astype(np.float64))                        # (N,T) 창 내 유효 관측 수
    XtX = np.empty((N, T, K, K), dtype=np.float64)
    for i in range(K):
        for j in range(i, K):
            s = _rsum(Xc[:, :, i] * Xc[:, :, j])
            XtX[:, :, i, j] = s
            if j != i:
                XtX[:, :, j, i] = s
    Xty = np.empty((N, T, K), dtype=np.float64)
    for i in range(K):
        Xty[:, :, i] = _rsum(Xc[:, :, i] * Yc)

    full = (n_ok >= window - 1e-9)                             # 창 전체가 유효할 때만 푼다
    # 정규방정식은 조건수가 원 설계행렬의 제곱이다. 스케일에 비례하는 리지를 반드시 넣는다.
    tr = np.einsum("ntkk->nt", XtX)
    lam = ridge * np.maximum(1.0, np.abs(tr) / max(K, 1))
    XtX = XtX + lam[:, :, None, None] * np.eye(K)[None, None]

    A = np.where(full[:, :, None, None], XtX, np.eye(K)[None, None])
    b = np.where(full[:, :, None], Xty, 0.0)
    try:
        beta = np.linalg.solve(A, b[..., None])[..., 0]        # (N,T,K)
    except np.linalg.LinAlgError:
        beta = np.einsum("ntkl,ntl->ntk", np.linalg.pinv(A), b)
    resid = Yc - np.einsum("ntk,ntk->nt", Xc, beta)
    out = np.where(full & ok, resid, np.nan)
    return out


def expand_events_to_months(ev: pd.DataFrame, date_col: str, months: pd.DatetimeIndex,
                            window_days: int) -> pd.DataFrame:
    """이벤트를 '그 이벤트가 유효한 월말들'로 펼친다. 월 루프를 없애는 핵심 원시함수.

    ★ 왜: 원래 코드는 월마다 전체 프레임을 불리언 필터링했다.
        for m in months:  w = x[(x.dt > m-90d) & (x.dt <= m)]
      120개월 × 30만행 = 3,600만 회 비교 + groupby 120회. 리포트가 목표치(연 3만 × 10년 =
      30만건)에 도달하면 이 한 함수가 수 분을 먹는다. 그런데 이벤트 하나가 영향을 주는
      월말은 window/30 개뿐이다(90일이면 3~4개). 그 관계를 직접 만들면 전체 비용이
      O(이벤트 × 창길이/30) 로 떨어지고 groupby 는 단 1회다.

    반환: ev 를 (창에 걸리는 월말 수)만큼 복제하고 'month' 컬럼을 붙인 프레임.
    """
    if not nonempty(ev) or len(months) == 0:
        out = ev.iloc[0:0].copy() if ev is not None else pd.DataFrame()
        out["month"] = pd.Series(dtype="datetime64[ns]")
        return out
    m_arr = np.asarray(pd.DatetimeIndex(months).values, dtype="datetime64[ns]")
    d = as_ts_series(ev[date_col]).to_numpy(dtype="datetime64[ns]")
    ok = ~np.isnat(d)
    if not ok.any():
        out = ev.iloc[0:0].copy()
        out["month"] = pd.Series(dtype="datetime64[ns]")
        return out
    sub = ev[ok].reset_index(drop=True)
    d = d[ok]
    # 이벤트가 유효한 구간: 월말 m 에 대해 (m - window) < d <= m
    #   ⇔ d <= m 이고 m < d + window  ⇔ m ∈ [첫 월말 ≥ d, d + window)
    lo = np.searchsorted(m_arr, d, side="left")
    hi = np.searchsorted(m_arr, d + np.timedelta64(int(window_days), "D"), side="left")
    cnt = np.maximum(hi - lo, 0)
    if cnt.sum() == 0:
        out = sub.iloc[0:0].copy()
        out["month"] = pd.Series(dtype="datetime64[ns]")
        return out
    rep = np.repeat(np.arange(len(sub)), cnt)
    # 각 복제행의 월 인덱스 = lo + (그룹 내 순번)
    offs = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    midx = np.repeat(lo, cnt) + offs
    out = sub.iloc[rep].reset_index(drop=True)
    out["month"] = m_arr[midx]
    return out


def rolling_sum_min_valid(s: pd.Series, window: int, min_valid: int) -> pd.Series:
    """rolling(window).sum() 인데 '유효 관측이 min_valid 미만이면 NaN'.

    pandas 의 min_periods 는 '창 안의 non-NaN 개수'를 세지만, 우리가 원하는 건
    '창이 실제로 window 만큼 채워졌는가'다. 상장 직후나 거래정지 구간에서
    3개짜리 합을 120일 누적으로 부르면 d3 가 그 종목만 체계적으로 작아진다.
    """
    v = pd.to_numeric(s, errors="coerce")
    tot = v.rolling(window, min_periods=1).sum()
    cnt = v.notna().rolling(window, min_periods=1).sum()
    return tot.where(cnt >= min_valid)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [08/22]  10_ingest_universe.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 유니버스 (C2 생존자편향 제거)                                     ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축 — 우선순위와 역할이 각각 다르다:                                      ║
# ║    ① FDR GitHub 캐시  listing/krx        상장 종목 + 상장일        ← 로그인 불필요, 1순위  ║
# ║    ② FDR GitHub 캐시  listing/delisting  상장폐지 + 폐지일         ← ★생존자편향 제거 입력 ║
# ║    ③ KIND 상장법인목록                   상장일·업종 보강                                  ║
# ║    ④ pykrx 월/분기말 스냅샷              "그 날 실제 상장" 검증     ← 인증 필요, 보조      ║
# ║    ⑤ DART corpCode.xml                   corp_code ↔ 종목코드                              ║
# ║    ⑥ 네이버 금융                         ①~⑤ 어디에도 이름이 없는 잔여 코드 보강          ║
# ║                                                                                          ║
# ║  ★ 설계 원칙: 유니버스의 정확성은 ①②③⑤(상장일·폐지일)만으로 성립해야 한다.                ║
# ║    ④ 스냅샷은 '검증·보강'이지 '의존'이 아니다. KRX 인증이 실패해도 백테스트는 정상이어야   ║
# ║    한다. 실제로 KRX 는 부분 응답을 자주 내는데, 그걸 진실로 믿으면 그 달 유니버스가        ║
# ║    조용히 쪼그라들어 곧바로 선택편향이 된다.                                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "sector_src", "src"]

# 스냅샷 주기: "Q"(분기·기본) | "M"(월) | "A"(연) | "off"
#   월 단위는 120개월 × 2시장 = 240 호출이라 KRX 세션을 자주 건드리고 차단 위험이 커진다.
#   상장/폐지일이 이미 있으므로 분기 격자(40 × 2 = 80 호출)로도 검증 목적은 충분하다.
UNIVERSE_SNAPSHOT_FREQ = "Q"


# ── 중복 컬럼 방어 (이번 크래시의 직접 원인 유형) ────────────────────────────────────────────
def assert_no_dup_cols(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 에서 예외 없이 의미가 바뀐다.
    df[col] 이 Series 가 아니라 DataFrame 이 되고, groupby.agg 가
    'DataFrame object has no attribute name' 로 엉뚱한 곳에서 터진다.
    조용히 지나가면 최악이므로 발생 지점에서 즉시 세운다."""
    if df is None or df.empty:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — "
                           f"pandas 연산의 의미가 바뀌므로 여기서 중단합니다.")
    return df


# ── KRX 세션 게이트 ─────────────────────────────────────────────────────────────────────────
class KRXGate:
    """pykrx 호출을 단일 게이트로 통과시킨다.

    ★ 왜 필요한가 (pykrx 1.2.8 소스 확인 결과):
      get_auth_session() 은 모듈 전역 _auth_session 에 대해 락 없이 검사-후-생성을 한다.
      스레드 6개가 동시에 None 을 보면 6개가 각자 로그인하고, KRX 는 중복 로그인(CD011)을
      skipDup 로 처리하며 앞선 세션을 강제 종료시킨다. 살아남는 건 마지막 하나뿐이고
      나머지 스레드는 죽은 쿠키로 요청해 JSON 대신 로그인 HTML 을 받는다.
      → 실제 운영 로그의 'Error occurred in ...: Expecting value: line 13 column 1' 이 이것이다.
      또 세션은 3600초(버퍼 300초 → 실효 55분) 만료라 긴 수집은 반드시 만료를 넘긴다.
      만료 갱신도 같은 무락 경로를 타므로 장시간 실행에서 같은 폭풍이 재현된다.

    대응: ① 메인 스레드에서 단 한 번 워밍업 ② 모든 pykrx 호출을 락으로 직렬화
          ③ 만료 전에 선제 갱신 ④ 실패해도 예외 대신 None 을 돌려 상위가 폴백하게 한다.
    """

    def __init__(self):
        self._lk = threading.RLock()
        self._warm = False
        self._authed = False
        self._t_login = 0.0
        self.calls = 0
        self.fails = 0

    def warmup(self) -> bool:
        if pykrx_stock is None:
            return False
        with self._lk:
            if self._warm:
                return self._authed
            self._warm = True
            has_cred = bool(os.environ.get("KRX_ID") and os.environ.get("KRX_PW"))
            try:
                from pykrx.website.comm.auth import get_auth_session   # type: ignore
                s = get_auth_session()
                self._authed = s is not None and getattr(s, "is_authenticated", False)
            except Exception:
                self._authed = False
            self._t_login = time.time()
            if has_cred and self._authed:
                LOG.ok("KRX 세션 확보 (메인 스레드 1회 로그인) — 이후 모든 pykrx 호출을 "
                       "직렬화해 중복 로그인(CD011)으로 서로를 밀어내는 현상을 막습니다.")
            elif has_cred:
                LOG.warn("KRX 자격증명은 있으나 세션 인증에 실패했습니다. ID/PW 를 확인하세요. "
                         "스냅샷 검증만 건너뛰며, 유니버스는 상장일·폐지일로 정확히 구성됩니다.")
            else:
                LOG.info("KRX 자격증명 미입력 — pykrx 스냅샷 검증은 생략합니다. "
                         "유니버스는 FDR 상장/폐지 목록으로 구성되며 백테스트는 정상 동작합니다.")
            return self._authed

    def _refresh_if_stale(self):
        # 실효 55분. 45분마다 선제 갱신해 '동시 만료 → 동시 재로그인'을 원천 차단한다.
        if not self._authed or (time.time() - self._t_login) < 45 * 60:
            return
        try:
            from pykrx.website.comm.auth import get_auth_session       # type: ignore
            get_auth_session()
            self._t_login = time.time()
            LOG.debug("KRX 세션 선제 갱신")
        except Exception:
            pass

    def call(self, fn: Callable, *a, **kw):
        """모든 pykrx 호출의 유일한 통로. 직렬화 + 스로틀 + 예외 흡수."""
        if pykrx_stock is None:
            return None
        with self._lk:
            self._refresh_if_stale()
            limiter("krx").wait()
            self.calls += 1
            try:
                return fn(*a, **kw)
            except Exception as e:                                     # noqa
                self.fails += 1
                LOG.debug(f"pykrx 호출 실패 {getattr(fn, '__name__', '?')}: {type(e).__name__}")
                return None

    def report(self):
        if self.calls:
            LOG.info(f"pykrx 게이트 — 호출 {self.calls:,}건 · 실패 {self.fails:,}건 "
                     f"({100*self.fails/max(self.calls,1):.1f}%) · 직렬화 적용")


KRXG = KRXGate()


# ── 로그인 불필요 경로 ★1순위 ──────────────────────────────────────────────────────────────
#   FinanceDataReader 가 실제로 읽는 GitHub 캐시. KRX 인증 변경의 영향을 받지 않는다.
#   FDR 라이브러리 자체는 최신 영업일을 알아내려고 data.krx.co.kr 을 한 번 찌르는데,
#   그게 로그인 벽에 막히면 CSV 는 멀쩡한데도 ValueError 로 죽는다 → 우리는 CSV 를 직접 읽는다.
FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
             "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 14) -> Optional[pd.DataFrame]:
    """영업일 CSV 만 존재하므로 최근 날짜부터 거꾸로 훑는다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        url = FDR_CACHE.format(kind=kind, date=d.isoformat())
        raw = http_get(url, source="generic", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            # ★ index_col=0 을 무조건 주면 안 된다.
            #   listing CSV 는 이름 없는 인덱스 컬럼이 있지만 delisting CSV 는 없을 수 있고,
            #   그때 첫 실컬럼(Symbol=종목코드)이 인덱스로 먹혀 통째로 사라진다.
            #   → 상장폐지 종목이 전부 유실되고 그게 곧 생존자편향이다. 반드시 판별해서 읽는다.
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str,
                                    "MarketId": str, "Market": str, "ISU_CD": str,
                                    "Unnamed: 0": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR GitHub 캐시 적중: {kind} @ {d.isoformat()} "
                          f"({len(df):,}행 · 컬럼 {list(df.columns)[:6]})")
                return df
        except Exception:
            continue
    return None


def _lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def fetch_fdr_listing() -> pd.DataFrame:
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
        name_c = col.get("name") or col.get("korean name") or col.get("isu_nm")
        if code_c and name_c:
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "market": (d[col["market"]].astype(str) if "market" in col
                           else d[col["marketid"]].astype(str) if "marketid" in col else "KRX"),
                "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
                "industry": (d[col["sector"]].astype(str) if "sector" in col
                             else d[col["industry"]].astype(str) if "industry" in col else ""),
            })
            t["sector_src"], t["src"] = "fdr_cache", "fdr_github_cache"
            t["delisting_date"] = pd.NaT
            t["corp_code"] = np.nan
            n0 = len(t)
            r = t.dropna(subset=["code"]).drop_duplicates("code")
            if n0 - len(r):
                LOG.debug(f"상장목록 정규화 탈락 {n0-len(r):,}건(코드 형식 불일치/중복)")
            LOG.ok(f"상장목록(로그인 불필요 경로) {len(r):,}건 — KRX 인증 변경 영향을 받지 않습니다.")
            return r

    if fdr is None:
        LOG.warn("상장목록을 확보하지 못했습니다 (GitHub 캐시 실패 + FinanceDataReader 없음).")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    try:
        limiter("krx").wait()
        d = fdr.StockListing("KRX")
    except Exception as e:                                            # noqa
        LOG.warn(f"fdr.StockListing('KRX') 실패({type(e).__name__}) — "
                 f"FDR 은 최신 영업일 확인차 data.krx.co.kr 를 찌르는데 그게 막히면 "
                 f"CSV 가 멀쩡해도 죽습니다.")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    if d is None or len(d) == 0:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    col = _lower_map(d)
    code_c = col.get("code") or col.get("symbol")
    name_c = col.get("name")
    if not code_c or not name_c:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6), "name": d[name_c].astype(str),
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "listing_date": as_ts_series(d[col["listingdate"]]) if "listingdate" in col else pd.NaT,
        "industry": d[col["sector"]].astype(str) if "sector" in col else "",
        "delisting_date": pd.NaT, "corp_code": np.nan,
        "sector_src": "fdr", "src": "fdr:KRX"})
    return t.dropna(subset=["code"]).drop_duplicates("code")


def fetch_fdr_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력. KRX Open API 에는 상장폐지 엔드포인트가 아예 없어서
    이 GitHub 캐시가 사실상 유일한 공개 경로다.

    ★ 탈락 사유를 반드시 집계해 로그로 남긴다. 여기서 조용히 버려지는 종목이
    그대로 생존자편향이 되기 때문이다(운영에서 4,172행 → 2,526행으로 줄었던 구간)."""
    d = _fdr_cache_csv("listing/delisting")
    if d is None or len(d) == 0:
        if fdr is None:
            LOG.warn("상장폐지 목록을 확보하지 못했습니다 — C2(생존자편향 제거) 미충족 상태입니다. "
                     "결과 해석 시 반드시 감안하세요.")
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
        try:
            limiter("krx").wait()
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
        if d is None or len(d) == 0:
            return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])

    col = _lower_map(d)
    code_c = col.get("symbol") or col.get("code") or col.get("isu_cd") or col.get("isu_srt_cd")
    if not code_c:
        LOG.warn(f"상장폐지 파일에서 종목코드 컬럼을 찾지 못했습니다: {list(d.columns)[:12]}")
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date",
                                  "listingdate") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c

    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    n_badcode = int(codes.isna().sum())
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    })
    t = t.dropna(subset=["code"])
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_nodate = int(t["delisting_date"].isna().sum())

    LOG.ok(f"상장폐지 목록(로그인 불필요 경로) {len(t):,}건 — 생존자편향 제거 입력 확보")
    if n_raw - len(t):
        LOG.info(f"  폐지목록 정규화: 원본 {n_raw:,} → {len(t):,} "
                 f"(코드형식 불일치 {n_badcode:,} · 동일코드 중복 {n_dupe:,}) · "
                 f"폐지일 결측 {n_nodate:,}건은 상장기간 추정에서 제외됩니다.")
        if n_badcode > n_raw * 0.05:
            # ★ 탈락분이 '무엇인지'를 보여주지 않으면 이 경고는 해석 불가능한 공포일 뿐이다.
            #   실측상 대부분은 ELW·신주인수권증서·수익증권처럼 애초에 보통주가 아니고,
            #   그건 빼는 게 맞다. 하지만 보통주가 섞여 있으면 그게 곧 생존자편향이므로
            #   증권 종류별로 분해해서 어느 쪽인지 눈으로 확인할 수 있게 한다.
            bad_mask = codes.isna()
            kind_col = next((col[k] for k in ("secugroup", "kind", "issuetype", "종류")
                             if k in col), None)
            if kind_col is not None:
                vc = d.loc[bad_mask.to_numpy(), kind_col].astype(str).value_counts().head(8)
                LOG.table([[k, f"{v:,}", f"{100*v/max(n_badcode,1):.1f}%"] for k, v in vc.items()],
                          ["증권 종류", "탈락 건수", "비중"], ["l", "r", "r"],
                          title=f"폐지목록에서 코드 형식 불일치로 제외된 {n_badcode:,}건의 구성")
                eq = sum(v for k, v in vc.items() if any(
                    s in str(k) for s in ("주권", "보통주", "Common", "EQUITY")))
                if eq:
                    LOG.warn(f"그중 보통주로 보이는 {eq:,}건이 있습니다 — 이만큼은 생존자편향으로 "
                             f"남습니다. to_code6 의 티커 정규식을 확인하세요.")
                else:
                    LOG.info("전부 보통주가 아닌 증권(ELW·신주인수권·수익증권 등)입니다 — "
                             "제외가 맞으며 생존자편향과 무관합니다.")
            else:
                LOG.warn(f"폐지목록의 {100*n_badcode/max(n_raw,1):.0f}% 가 코드 형식 불일치로 "
                         f"탈락했고 증권 종류 컬럼이 없어 구성을 확인할 수 없습니다. "
                         f"원본 코드 예시: {raw_codes[bad_mask].head(5).tolist()}")
    return t


def fetch_kind_listing() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일·업종 보강.
    ★ 종목코드가 정수로 와서 앞자리 0 이 날아간다(5930 ← 005930). to_code6 이 복구한다."""
    urls = [
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
        "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download",
    ]
    for u in urls:
        raw = http_get(u, source="kind", as_bytes=True, tries=2,
                       referer="https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage")
        if not raw or len(raw) < 500:
            continue
        for enc in ("euc-kr", "cp949", "utf-8"):
            try:
                tabs = pd.read_html(io.BytesIO(raw), encoding=enc)
            except Exception:
                continue
            if not tabs:
                continue
            d = max(tabs, key=len)
            col = {str(c).strip(): c for c in d.columns}
            code_c, name_c = col.get("종목코드"), col.get("회사명")
            if not code_c or not name_c:
                continue
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "listing_date": as_ts_series(d[col["상장일"]]) if "상장일" in col else pd.NaT,
                "industry": d[col["업종"]].astype(str) if "업종" in col else "",
                "sector_src": "kind", "src": "kind", "market": "",
                "delisting_date": pd.NaT, "corp_code": np.nan,
            }).dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"KIND 상장법인목록 {len(t):,}건 (상장일 {int(t['listing_date'].notna().sum()):,}건)")
            return t
    LOG.warn("KIND 상장법인목록을 받지 못했습니다 — 상장일은 FDR/스냅샷으로만 채웁니다.")
    return pd.DataFrame(columns=SEC_MASTER_COLS)


def fetch_dart_corpcode() -> pd.DataFrame:
    """corp_code ↔ 종목코드. DART 의 모든 재무·공시 조회는 corp_code 로만 된다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=30)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 와 네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    txt = _decode(xml, None, "corpcode")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code")), "modify_date": g("modify_date")})
    d = pd.DataFrame(rows)
    if len(d):
        VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건)")
    return d


# ── pykrx 스냅샷 (보조·검증) ────────────────────────────────────────────────────────────────
def _snapshot_grid(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    f = str(UNIVERSE_SNAPSHOT_FREQ).upper()
    if f in ("OFF", "NONE", ""):
        return []
    if f == "M":
        return list(months)
    if f == "A":
        return [m for m in months if m.month == 12] or list(months[::12])
    return [m for m in months if m.month in (3, 6, 9, 12)] or list(months[::3])   # 기본 Q


def fetch_pykrx_snapshots(months: pd.DatetimeIndex) -> pd.DataFrame:
    """분기말 상장종목 스냅샷. C2 의 '검증' 입력이다(의존 대상이 아님).

    ★ 전부 KRXG 게이트를 통해 직렬로 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), 그 결과 JSON 대신 로그인 HTML 을 받아 대량 실패한다."""
    cols = ["snap_date", "code", "market"]
    cached = VAULT.get_table("krx_listing_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"공용 캐시에서 상장 스냅샷 {len(have)}개 시점 재사용")

    grid = _snapshot_grid(months)
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    new_rows: List[dict] = []
    if todo:
        if not KRXG.warmup():
            LOG.info(f"KRX 세션이 없어 스냅샷 {len(todo)}개 시점을 건너뜁니다. "
                     f"유니버스는 상장일·폐지일로 구성되며 이는 정상 경로입니다.")
            todo = []
    if todo:
        LOG.info(f"KRX 상장 스냅샷 {len(todo)}개 시점 수집 (주기={UNIVERSE_SNAPSHOT_FREQ}, 직렬)")
        bad_streak = 0
        for d in tqdm(todo, desc="KRX 상장 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           d.strftime("%Y%m%d"), prev=True) or d.strftime("%Y%m%d")
            got_any = False
            for mkt in ("KOSPI", "KOSDAQ"):
                tk = KRXG.call(pykrx_stock.get_market_ticker_list, bd, market=mkt)
                if not tk:
                    continue
                got_any = True
                for t in tk:
                    c = to_code6(t)
                    if c:
                        new_rows.append({"snap_date": d.strftime("%Y-%m-%d"),
                                         "code": c, "market": mkt})
            bad_streak = 0 if got_any else bad_streak + 1
            if bad_streak >= 5:
                LOG.warn("KRX 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 상태입니다. "
                         "스냅샷 수집을 중단하고 상장일·폐지일 경로로 진행합니다(정상 폴백).")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap = (snap.dropna(subset=["snap_date", "code"])
                .drop_duplicates(["snap_date", "code"])[cols])

    # ★ 부분 응답 방어: 이웃 시점 대비 종목수가 급감한 스냅샷은 '진실'이 아니라 '사고'다.
    #   그대로 쓰면 그 달 유니버스가 조용히 쪼그라들어 선택편향이 된다.
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만이라 "
                     f"부분 응답으로 판단하고 폐기합니다: "
                     f"{[str(x.date()) for x in bad.index[:6]]}")
            snap = snap[~snap["snap_date"].isin(bad.index)]
    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                        source="pykrx", extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_listing_snapshots", snap, source="pykrx")
    return snap


def fetch_naver_names(codes: Sequence[str], limit: int = 400) -> Dict[str, str]:
    """①~⑤ 어디에도 이름이 없는 잔여 코드를 네이버로 보강한다.
    이름이 비면 국민연금·조달 상호 매칭이 통째로 실패하므로 커버리지에 직접 영향이 있다."""
    codes = [c for c in codes if c][:limit]
    if not codes or RUN_MODE == "CACHED":
        return {}

    def _one(c: str):
        h = http_get(f"https://finance.naver.com/item/main.naver?code={c}",
                     source="naver", tries=1, force_enc="euc-kr",
                     referer="https://finance.naver.com/")
        if not h:
            return None
        m = re.search(r'<div class="wrap_company">\s*<h2>\s*<a[^>]*>([^<]+)</a>', h)
        if not m:
            m = re.search(r"<title>\s*([^:<]+?)\s*:", h)
        return (c, _clean_cell(m.group(1))) if m else None

    res = pmap_io(_one, codes, workers=min(6, N_WORKERS_IO), desc="네이버 종목명 보강")
    out = {c: n for r in res if r for c, n in [r] if n}
    if out:
        LOG.ok(f"네이버로 종목명 {len(out):,}건 보강")
    return out


# ── 종목 마스터 ─────────────────────────────────────────────────────────────────────────────
def build_security_master(snapshots: pd.DataFrame) -> pd.DataFrame:
    """모든 소스를 합쳐 종목 마스터를 만든다. 충돌은 우선순위로 해소하고 전부 로깅한다."""
    parts: List[pd.DataFrame] = []
    src_stats: List[Tuple[str, int]] = []

    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
        src_stats.append(("FDR 상장목록", len(lst)))
        PIPE.io("IN", "HTTP", "fdr:StockListing", lst, source="FinanceDataReader")

    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
        src_stats.append(("KIND 상장법인", len(kind)))
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")

    dead = fetch_fdr_delisting()
    PIPE.io("IN", "HTTP", "fdr:KRX-DELISTING", dead, source="FinanceDataReader",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market"]).copy()
        d2["listing_date"] = pd.NaT
        d2["industry"] = ""
        d2["corp_code"] = np.nan
        d2["sector_src"] = "fdr-del"
        d2["src"] = "fdr:delisting"
        parts.append(d2)
        src_stats.append(("FDR 상장폐지", len(d2)))

    # 스냅샷에만 존재하는 종목(=상장목록·폐지목록 어디에도 없는 종목)도 반드시 살린다
    if snapshots is not None and len(snapshots):
        known = set(pd.concat(parts, ignore_index=True)["code"]) if parts else set()
        extra = sorted(set(snapshots["code"]) - known)
        if extra:
            parts.append(pd.DataFrame({
                "code": extra, "name": "", "market": "", "listing_date": pd.NaT,
                "delisting_date": pd.NaT, "corp_code": np.nan, "industry": "",
                "sector_src": "snapshot", "src": "pykrx:snapshot"}))
            src_stats.append(("스냅샷 전용", len(extra)))
            LOG.info(f"스냅샷에만 존재하는 종목 {len(extra):,}건 추가 — 상장/폐지 명단 누락분입니다. "
                     f"(빠뜨리면 곧바로 생존자편향)")

    if not parts:
        raise RuntimeError(
            "종목 마스터를 만들 소스가 하나도 없습니다.\n"
            "  · 네트워크에서 raw.githubusercontent.com 과 kind.krx.co.kr 에 접근 가능한지\n"
            "  · FinanceDataReader 가 설치되어 있는지\n"
            "확인하세요. RUN_MODE='SMOKE' 로는 네트워크 없이 계산경로만 검증할 수 있습니다.")

    # ★ 중복 컬럼 원천 차단: 컬럼 목록을 dict.fromkeys 로 유일화한 뒤 정렬한다.
    #   (SEC_MASTER_COLS 에 이미 있는 이름을 다시 더하면 m[col] 이 DataFrame 이 되고
    #    groupby.agg 가 'DataFrame object has no attribute name' 으로 터진다)
    _cols = list(dict.fromkeys(SEC_MASTER_COLS))
    m = pd.concat([p.reindex(columns=_cols) for p in parts], ignore_index=True)
    assert_no_dup_cols(m, "security_master:concat")
    m["code"] = m["code"].map(to_code6)
    m = m.dropna(subset=["code"])

    def _first_str(s):
        for x in s:
            if isinstance(x, str) and x.strip():
                return x.strip()
        return ""

    agg = m.groupby("code", as_index=False).agg(
        name=("name", _first_str),
        market=("market", _first_str),
        listing_date=("listing_date", "min"),
        delisting_date=("delisting_date", "max"),
        industry=("industry", _first_str),
        src=("src", lambda s: "|".join(sorted(set(map(str, s))))),
    )
    assert_no_dup_cols(agg, "security_master:agg")

    # 스냅샷으로 상장/폐지일 보정 — 소스 날짜가 없을 때만 관측으로 채운다
    if snapshots is not None and len(snapshots):
        g = snapshots.groupby("code")["snap_date"]
        agg = agg.merge(g.min().rename("snap_first"), left_on="code", right_index=True, how="left")
        agg = agg.merge(g.max().rename("snap_last"), left_on="code", right_index=True, how="left")
        need = agg["listing_date"].isna() & agg["snap_first"].notna()
        agg.loc[need, "listing_date"] = agg.loc[need, "snap_first"]
        last_snap = snapshots["snap_date"].max()
        gone = (agg["delisting_date"].isna() & agg["snap_last"].notna() &
                (agg["snap_last"] < last_snap - pd.Timedelta(days=200)))
        agg.loc[gone, "delisting_date"] = agg.loc[gone, "snap_last"] + pd.offsets.MonthEnd(1)
        if int(gone.sum()):
            LOG.info(f"스냅샷에서 사라진 {int(gone.sum()):,}종목을 폐지로 추정 "
                     f"(폐지명단 누락 보완 — 생존자편향 2차 방어)")
        agg = agg.drop(columns=[c for c in ("snap_first", "snap_last") if c in agg.columns])

    cc = fetch_dart_corpcode()
    if len(cc):
        cc2 = cc.dropna(subset=["code"])[["code", "corp_code", "corp_name"]].drop_duplicates("code")
        agg = agg.merge(cc2, on="code", how="left")
        blank = agg["name"].astype(str).str.strip() == ""
        agg.loc[blank, "name"] = agg.loc[blank, "corp_name"].fillna("")
        agg = agg.drop(columns=["corp_name"])
    else:
        agg["corp_code"] = np.nan

    # 네이버로 잔여 무명 종목 보강 (상호 매칭 커버리지에 직결)
    nameless = agg.loc[agg["name"].astype(str).str.strip() == "", "code"].tolist()
    if nameless:
        LOG.info(f"이름이 비어 있는 종목 {len(nameless):,}건 — 네이버로 보강 시도")
        nm = fetch_naver_names(nameless)
        if nm:
            agg["name"] = agg.apply(
                lambda r: nm.get(r["code"], r["name"]) if not str(r["name"]).strip() else r["name"],
                axis=1)

    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    agg["sector_src"] = "merged"
    assert_no_dup_cols(agg, "security_master:final")

    n_list = int(agg["listing_date"].notna().sum())
    n_del = int(agg["delisting_date"].notna().sum())
    n_corp = int(agg["corp_code"].notna().sum()) if "corp_code" in agg.columns else 0
    n_name = int((agg["name"].astype(str).str.strip() != "").sum())
    LOG.table([[lab, f"{n:,}"] for lab, n in src_stats] +
              [["── 병합 결과 ──", ""],
               ["고유 종목", f"{len(agg):,}"],
               ["상장일 보유", f"{n_list:,} ({100*n_list/max(len(agg),1):.0f}%)"],
               ["폐지일 보유", f"{n_del:,} ({100*n_del/max(len(agg),1):.0f}%)"],
               ["corp_code 보유", f"{n_corp:,} ({100*n_corp/max(len(agg),1):.0f}%)"],
               ["종목명 보유", f"{n_name:,} ({100*n_name/max(len(agg),1):.0f}%)"]],
              ["소스 / 항목", "건수"], ["l", "r"], title="종목 마스터 구성 (다중소스 병합)")

    if n_del < 200:
        LOG.warn("상장폐지 종목이 200건 미만입니다. 10년 구간이면 통상 1,000건 이상이어야 합니다. "
                 "생존자편향이 남아 있으니 결과 해석 시 반드시 감안하세요. (C2 부분 미충족)")
        PIPE.note("WARN: 상장폐지 표본 부족 — C2 완전 제거 미달")
    if n_corp < len(agg) * 0.3:
        LOG.warn(f"corp_code 매칭률이 {100*n_corp/max(len(agg),1):.0f}% 로 낮습니다. "
                 f"DART 재무·공시가 그만큼 결측이 되어 B/C축과 PACK-C/D 가 약해집니다. "
                 f"DART_API_KEY 를 확인하세요.")
    VAULT.put_table("security_master", agg, scope="shared", domain="universe",
                    source="fdr+kind+pykrx+dart+naver")
    KRXG.report()
    return agg


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [09/22]  11_ingest_price.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · 수급                                                              ║
# ║                                                                                          ║
# ║  KRX 인증(2025-12 변경) → pykrx → FinanceDataReader → 네이버 → yfinance → 캐시            ║
# ║  어느 경로가 실제로 쓰였는지 종목 단위로 기록하고 표로 출력한다.                            ║
# ║  ▶ 폴백해도 백테스트는 정상 동작한다. 단, 거래대금(Amount)은 소스에 따라 근사가 되므로      ║
# ║    유동성 필터(V6)의 엄밀성이 달라진다 — 이 점을 감사표에 명시한다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]


class KRXAuth:
    """KRX 데이터 마켓플레이스 인증(2025-12 변경 대응). 실패해도 절대 죽지 않고 폴백으로 넘긴다.

    2026년 기준 경로 3가지:
      ① KRX Open API (data-dbg.krx.co.kr) — 인증키. ★단, 엔드포인트별로 '이용신청'이 따로 필요하고
         승인에 하루 정도 걸린다. 키만 있다고 바로 되는 게 아니다. 상장폐지 API 는 존재하지 않는다.
      ② 마켓플레이스 세션 로그인 → getJsonData.cmd (bld 기반). pykrx 가 쓰는 경로.
      ③ 레거시 OTP 파일다운로드 — 2026년에는 세션 없이 빈 데이터/로그아웃 오류가 잦다. 의존 금지.
    """

    LOGIN_WARM1 = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    LOGIN_WARM2 = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    JSONDATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
    OPENAPI = "https://data-dbg.krx.co.kr/svc/apis/{cat}/{ep}"

    def __init__(self, user: str, pw: str, apikey: str = ""):
        self.user, self.pw, self.apikey = (user or "").strip(), (pw or "").strip(), (apikey or "").strip()
        self.status = "NOT_ATTEMPTED"
        self.session_ok = False
        self.openapi_ok = False

    def login(self) -> bool:
        if self.apikey:
            self.openapi_ok = self._probe_openapi()
            self.status = "OPENAPI_OK" if self.openapi_ok else "OPENAPI_KEY_UNAUTHORIZED"
            if not self.openapi_ok:
                LOG.warn("KRX Open API 키는 있으나 해당 엔드포인트 호출이 거부되었습니다. "
                         "KRX Open API 는 '엔드포인트별 이용신청'이 따로 필요하고 승인에 하루 정도 "
                         "걸립니다. 키 발급만으로는 즉시 사용할 수 없습니다.")
        if not (self.user and self.pw):
            if not self.openapi_ok:
                self.status = "NO_CREDENTIALS"
                LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 불필요 경로로 진행합니다. "
                         "(FDR GitHub 캐시 → 네이버 차트 → yfinance). "
                         "백테스트는 정상 동작하며, 어느 소스가 쓰였는지는 감사표에 나옵니다.")
            return self.openapi_ok
        # 워밍업 없이 바로 POST 하면 세션 쿠키가 없어 항상 실패한다
        http_get(self.LOGIN_WARM1, source="krx", tries=1)
        http_get(self.LOGIN_WARM2, source="krx", tries=1, referer=self.LOGIN_WARM1)
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                continue
            if re.search(r"CD011|중복\s*로그인", str(txt)):
                LOG.warn("KRX 중복 로그인(CD011) 감지 — 같은 계정이 브라우저나 다른 노트북에서 "
                         "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 종료됩니다. "
                         "두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                 "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
        return self.openapi_ok

    def _probe_openapi(self) -> bool:
        """AUTH_KEY 를 쿼리로 보내는 구현과 헤더로 보내는 공식 샘플이 공존한다 — 둘 다 시도."""
        d = (_dt.date.today() - _dt.timedelta(days=7))
        while d.weekday() >= 5:
            d -= _dt.timedelta(days=1)
        url = self.OPENAPI.format(cat="sto", ep="stk_bydd_trd")
        for mode in ("query", "header"):
            kw = ({"params": {"AUTH_KEY": self.apikey, "basDd": d.strftime("%Y%m%d")}}
                  if mode == "query" else
                  {"params": {"basDd": d.strftime("%Y%m%d")},
                   "headers": {"AUTH_KEY": self.apikey}})
            js = http_json(url, source="krx", tries=1, **kw)
            if isinstance(js, dict) and (js.get("OutBlock_1") or js.get("output")):
                LOG.ok(f"KRX Open API 사용 가능 (AUTH_KEY 전달 방식: {mode})")
                self._openapi_mode = mode
                return True
        return False

    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회. 세션이 없으면 JSON 대신 로그인 HTML 이 와서
        엉뚱한 곳에서 JSONDecodeError 가 난다 → 여기서 미리 막는다."""
        if not self.session_ok:
            return None
        body = {"bld": bld, "share": "1", "money": "1", "csvxls_isNo": "false", **params}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if not txt or txt.lstrip()[:1] not in ("{", "["):
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, KRX_OPENAPI_KEY)


# ── 개별 소스 ───────────────────────────────────────────────────────────────────────────────
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    try:
        limiter("krx").wait()
        d = pykrx_stock.get_market_ohlcv(start.replace("-", ""), end.replace("-", ""), code)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "거래대금": "amount"}
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    d["code"], d["src"] = code, "pykrx"
    return d.reindex(columns=PRICE_COLS)


def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        limiter("krx").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    if "amount" not in d.columns:
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")      # 근사 — 감사표에 명시된다
    d["code"], d["src"] = code, "fdr"
    return d.reindex(columns=PRICE_COLS)


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 차트 API. 폴백 중에서는 가장 안정적이지만 거래대금이 없다."""
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
        # 응답이 파이썬 리터럴에 가까운 준-JSON 이다: 홑따옴표 + 따옴표 없는 키워드
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast
                arr = ast.literal_eval(t.strip())
            except Exception:
                arr = None
        if isinstance(arr, list) and len(arr) >= 2:
            break
        arr = None
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    hdr = [str(x).strip().lower() for x in arr[0]]
    rows = [r for r in arr[1:] if isinstance(r, (list, tuple)) and len(r) == len(hdr)]
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=hdr)
    # ★ 이 rename 이 오랫동안 아무 일도 하지 않고 있었다.
    #   {**ren, **{c: c for c in d.columns}} 는 두 번째 dict 가 첫 번째를 덮어써서
    #   '날짜'→'날짜' 가 '날짜'→'date' 를 이긴다. 결과적으로 컬럼명이 한글로 남고
    #   d.get("close") 가 None 이 되어 None*None TypeError 로 죽는다.
    #   (pykrx/FDR 이 둘 다 없는 환경에서만 드러나므로 오래 숨어 있었다)
    ren = {"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "외국인소진율": "foreign_ratio"}
    d = d.rename(columns=ren)
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["amount"] = d["close"] * d["volume"]          # 네이버는 거래대금을 안 준다 → 근사(감사표에 명시)
    d["code"], d["src"] = code, "naver"
    d = d.dropna(subset=["close"])
    return d.reindex(columns=PRICE_COLS) if len(d) else None


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            limiter("generic").wait()
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [str(c[0]).lower() for c in d.columns]
        else:
            d.columns = [str(c).lower() for c in d.columns]
        d = d.reset_index()
        d = d.rename(columns={"index": "date"})
        if "date" not in d.columns:
            d = d.rename(columns={d.columns[0]: "date"})
        d["amount"] = pd.to_numeric(d.get("close"), errors="coerce") * \
            pd.to_numeric(d.get("volume"), errors="coerce")
        d["code"], d["src"] = code, "yfinance"
        return d.reindex(columns=PRICE_COLS)
    return None


PRICE_CHAIN = [("pykrx", _px_pykrx), ("fdr", _px_fdr), ("naver", _px_naver), ("yfinance", _px_yf)]


def fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """폴백 체인으로 전 종목 일봉 수집. 캐시 증분 갱신. 공용 인덱스에 저장."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    cached = VAULT.get_table("krx_ohlcv_daily", scope="shared")
    have_max: Dict[str, pd.Timestamp] = {}
    have_min: Dict[str, pd.Timestamp] = {}
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        g = cached.groupby("code")["date"]
        have_max, have_min = g.max().to_dict(), g.min().to_dict()
        LOG.info(f"공용 캐시에서 일봉 {len(cached):,}행 재사용 ({len(have_max):,}종목)")

    start_ts, end_ts = as_ts(start), as_ts(end)

    # ── 시도 원장 (음성 캐시) ─────────────────────────────────────────────────────────────
    #  ★ 폐지 종목과 '어느 소스에도 없는 종목'은 매 실행마다 전 소스 체인을 헛돌게 만든다.
    #    성공한 종목만 캐시에 남으므로 실패는 영원히 기억되지 않고, 그 수는 백테스트 기간이
    #    길어질수록 단조 증가한다. 실측상 완전 캐시 상태의 실행에서도 13~15분을 여기서 쓴다.
    #    → '언제 무엇을 시도했는지'를 남겨 30일간 재시도하지 않는다. 소스가 복구되면
    #      30일 뒤 자동으로 다시 시도하므로 영구 포기가 아니다.
    RETRY_AFTER_DAYS = 30
    _today = as_ts(end)
    attempts: Dict[str, dict] = {}
    _att = VAULT.get_table("price_fetch_attempts", scope="shared")
    if _att is not None and len(_att):
        _att["attempted_at"] = as_ts_series(_att["attempted_at"])
        _att["requested_from"] = as_ts_series(_att["requested_from"])
        _att = _att.sort_values("attempted_at").drop_duplicates("code", keep="last")
        attempts = {str(r.code): {"at": r.attempted_at, "frm": r.requested_from}
                    for r in _att.itertuples(index=False)}

    def _recently_failed(c: str, want_from: pd.Timestamp) -> bool:
        p = attempts.get(c)
        if p is None or pd.isna(p["at"]):
            return False
        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 되지 않는다.
        if pd.notna(p["frm"]) and p["frm"] > want_from:
            return False
        return (_today - p["at"]).days < RETRY_AFTER_DAYS

    todo, n_back, n_fwd, n_skip = [], 0, 0, 0
    for c in codes:
        mx, mn = have_max.get(c), have_min.get(c)
        if mx is None:
            if _recently_failed(c, start_ts):
                n_skip += 1
                continue
            todo.append((c, start))
            continue
        # ★ 과거 방향 백필을 반드시 함께 본다.
        #   앞선 실행이 최근 구간만 캐시했다면(예: 캐시가 2023~2026 뿐),
        #   max 만 보고 판단하면 2016~2022 를 영원히 못 받는다.
        #   → 10년 백테스트인데 앞 7년이 조용히 비는 사고가 된다.
        if mn is not None and mn > start_ts + pd.Timedelta(days=10):
            todo.append((c, start))
            n_back += 1
        elif mx < end_ts - pd.Timedelta(days=5):
            todo.append((c, (mx + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
            n_fwd += 1
    if n_back:
        LOG.info(f"과거 구간이 비어 있는 {n_back:,}종목을 처음부터 다시 받습니다 "
                 f"(캐시 최소일이 요청 시작일보다 늦음 = 앞 구간 결손).")
    if n_skip:
        LOG.info(f"최근 {RETRY_AFTER_DAYS}일 내 전 소스에서 실패한 {n_skip:,}종목은 이번엔 "
                 f"건너뜁니다 (대부분 상장폐지분). {RETRY_AFTER_DAYS}일 뒤 자동 재시도합니다.")
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 미수집 {len(todo):,}종목을 건너뜁니다.")
        todo = []

    src_used: Counter = Counter()
    new_frames: List[pd.DataFrame] = []
    if todo:
        LOG.info(f"일봉 신규/증분 수집 대상 {len(todo):,}종목")

        def _one(job):
            code, st = job
            # 폴백 체인. first_nonempty 는 DataFrame 진리값 오용(`a() or b()`)을
            # 구조적으로 막는다 — 그 관용구는 소스가 막힌 환경에서만 통과한다.
            d = first_nonempty(*[(lambda f=fn: f(code, st, end)) for _nm, fn in PRICE_CHAIN])
            if nonempty(d):
                d = d.dropna(subset=["date"])
                if nonempty(d):
                    return d
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        failed = []
        for (c, st), d in zip(todo, res):
            if d is not None and len(d):
                new_frames.append(d)
                src_used[str(d["src"].iloc[0])] += 1
            else:
                failed.append({"code": c, "requested_from": as_ts(st), "attempted_at": _today})
        if failed:
            LOG.warn(f"일봉 수집 실패 {len(failed):,}종목 — 전 소스에서 데이터를 못 받았습니다. "
                     f"(상장폐지 종목은 소스에 따라 조회가 안 되는 게 정상입니다) "
                     f"시도 원장에 기록하여 {RETRY_AFTER_DAYS}일간 재시도하지 않습니다.")
            # ★ 성공 캐시 저장(if new_frames)과 별개로 무조건 기록한다. 전부 실패한 실행에서
            #   아무것도 남기지 않으면 다음 실행이 똑같은 헛수고를 그대로 반복한다.
            _prev = _att if _att is not None and len(_att) else None
            _new = pd.DataFrame(failed)
            _all = pd.concat([_prev, _new], ignore_index=True) if _prev is not None else _new
            _all = (_all.sort_values("attempted_at")
                        .drop_duplicates("code", keep="last").reset_index(drop=True))
            VAULT.put_table("price_fetch_attempts", _all, scope="shared", domain="price",
                            source="fetch_prices:negative_cache")

    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        avail = [nm for nm, _fn in PRICE_CHAIN
                 if (nm != "pykrx" or pykrx_stock is not None)
                 and (nm != "fdr" or fdr is not None)
                 and (nm != "yfinance" or yf is not None)]
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            f"  · 시도한 소스 체인 : {', '.join(nm for nm, _ in PRICE_CHAIN)}\n"
            f"  · 이번 실행에서 사용 가능했던 소스 : {', '.join(avail) or '없음'}\n"
            f"  · 대상 종목 {len(codes):,}개 / 신규 수집 시도 {len(todo):,}개\n"
            "  진단: ① 네트워크에서 fchart.stock.naver.com 접근이 되는지\n"
            "        ② FinanceDataReader / pykrx 가 설치돼 있는지\n"
            "        ③ 드라이브 캐시(krx_ohlcv_daily)가 비어 있지 않은지\n"
            "  임시 우회: RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    for c in ("open", "high", "low", "close", "volume", "amount"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    px = (px.sort_values(["code", "date"])
            .drop_duplicates(["code", "date"], keep="last")
            .reset_index(drop=True))
    px = px[(px["date"] >= as_ts(start) - pd.Timedelta(days=400)) & (px["date"] <= end_ts)]

    if new_frames:
        VAULT.put_table("krx_ohlcv_daily", px, scope="shared", domain="price",
                        source="chain:" + ",".join(f"{k}×{v}" for k, v in src_used.most_common()))
    if src_used:
        LOG.table([[k, f"{v:,}"] for k, v in src_used.most_common()],
                  ["사용 소스", "종목수"], ["l", "r"], title="가격 소스 감사 (신규 수집분)")
        if src_used.get("naver", 0) or src_used.get("yfinance", 0):
            LOG.warn("네이버/yfinance 경로로 받은 종목은 거래대금이 종가×거래량 근사입니다. "
                     "V6 유동성 필터의 엄밀성이 그만큼 떨어집니다(과대추정 방향).")
    PIPE.io("OUT", "DRIVE", "krx_ohlcv_daily", px, source="price chain")
    return downcast(px)


def build_price_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 기준 가격 패널 + 익월 시가 체결가 + 20일 평균거래대금(ADV).

    체결은 '신호 산출일 다음 거래일 시가'(§10.1). 당일 종가 체결은 미래누수다.
    """
    px = px.sort_values(["code", "date"])
    px["adv20"] = (px.groupby("code", observed=True)["amount"]
                     .transform(lambda s: s.rolling(20, min_periods=10).mean()))
    px["ret1d"] = px.groupby("code", observed=True)["close"].pct_change()

    # 월말 스냅샷
    px["ym"] = px["date"].values.astype("datetime64[M]")
    last = px.groupby(["code", "ym"], observed=True).tail(1).copy()
    last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)

    # 다음 거래일 시가 = 체결가
    nxt = px.copy()
    nxt["next_open"] = nxt.groupby("code", observed=True)["open"].shift(-1)
    nxt["next_date"] = nxt.groupby("code", observed=True)["date"].shift(-1)
    keep = nxt[["code", "date", "next_open", "next_date"]]
    last = last.merge(keep, on=["code", "date"], how="left")

    monthly = last[["code", "month", "date", "close", "adv20", "next_open", "next_date"]].copy()
    monthly = monthly.rename(columns={"date": "signal_date"})
    monthly = monthly[monthly["month"].isin(months)]

    # 월간 수익률(체결가→체결가). 상장폐지 처리는 backtest 엔진에서 -100% 로 강제한다.
    monthly = monthly.sort_values(["code", "month"])
    # 체결가 = 신호 산출일의 '다음 거래일 시가'. 그 다음 거래일이 너무 멀면(거래정지·상폐 직전)
    # 그 가격으로 체결했다고 가정할 수 없으므로 종가로 폴백한다.
    gap = (monthly["next_date"] - monthly["signal_date"]).dt.days
    monthly["exec_px"] = monthly["next_open"].where(gap.notna() & (gap <= 10))
    monthly["exec_px"] = monthly["exec_px"].fillna(monthly["close"])

    # ★ fwd_ret 은 '바로 다음 달'과만 짝지어야 한다. 거래가 끊겨 중간 달이 패널에서 빠지면
    #   shift(-1) 이 몇 달 뒤 가격을 끌어와 한 달 수익으로 둔갑시킨다(수익 과대계상).
    nxt_px = monthly.groupby("code", observed=True)["exec_px"].shift(-1)
    nxt_m = monthly.groupby("code", observed=True)["month"].shift(-1)
    adjacent = (((nxt_m.dt.year - monthly["month"].dt.year) * 12 +
                 (nxt_m.dt.month - monthly["month"].dt.month)) == 1)
    monthly["fwd_ret"] = (nxt_px / monthly["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nxt_m.notna() & ~adjacent).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 백테스트 엔진이 -100% 로 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", monthly)
    return {"daily": px, "monthly": downcast(monthly)}


def fetch_investor_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """d3(기관+외국인 누적순매수) 입력. 없으면 D축은 가용 축 평균으로 자동 축소된다."""
    cached = VAULT.get_table("krx_investor_flows", scope="shared")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 수급 {len(cached):,}행 재사용")
        cached["date"] = as_ts_series(cached["date"])
        return cached
    if pykrx_stock is None or RUN_MODE == "CACHED":
        LOG.warn("수급 데이터 미수집 (pykrx 없음 또는 CACHED 모드) — D축 d3 는 결측 처리되고 "
                 "U 는 가용 축 평균으로 계산됩니다. 0으로 채우지 않습니다.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])

    codes = sorted({c for c in map(to_code6, codes) if c})

    def _one(code: str):
        try:
            limiter("krx").wait()
            d = pykrx_stock.get_market_trading_value_by_date(
                as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), code)
        except Exception:
            return None
        if d is None or len(d) == 0:
            return None
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "date"})
        inst = next((c for c in d.columns if "기관" in str(c)), None)
        forg = next((c for c in d.columns if "외국" in str(c)), None)
        if inst is None and forg is None:
            return None
        return pd.DataFrame({"code": code, "date": as_ts_series(d["date"]),
                             "inst_net": pd.to_numeric(d[inst], errors="coerce") if inst else np.nan,
                             "foreign_net": pd.to_numeric(d[forg], errors="coerce") if forg else np.nan})

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 8), desc="수급 수집")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.warn("수급 데이터를 받지 못했습니다 — d3 결측 처리.")
        return pd.DataFrame(columns=["code", "date", "inst_net", "foreign_net"])
    fl = pd.concat(got, ignore_index=True)
    VAULT.put_table("krx_investor_flows", fl, scope="shared", domain="flow", source="pykrx")
    PIPE.io("OUT", "DRIVE", "krx_investor_flows", fl, source="pykrx")
    return downcast(fl)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [10/22]  12_ingest_dart.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무 (벌크 우선) · 직원현황 · 공시목록                                       ║
# ║                                                                                          ║
# ║  §4.1 Primary  : 재무정보 일괄다운로드 (분기 단위 벌크). 종목별 루프 금지.                 ║
# ║  §4.1 Fallback A: fnlttMultiAcnt 다종목 배치(100사/호출). 단, '주요계정'만 온다.           ║
# ║  §4.1 Fallback B: fnlttSinglAcntAll 종목별. 예산 초과 확실 — 사용자 승인 후에만.           ║
# ║                                                                                          ║
# ║  ★ 벌크 파일의 함정: 벌크 txt 에는 **접수일자(rcept_dt)가 없다.** 결산기준일만 있다.       ║
# ║    그대로 knowledge_date 로 쓰면 45~90일치 미래누수가 통째로 들어간다(C1 정면 위반).       ║
# ║    → 공시목록(list.json, pblntf_ty="A")에서 (회사, 보고서종류, 사업연도) → rcept_dt 를     ║
# ║      만들어 결합한다. 결합 실패분은 법정 제출기한으로 보수적 추정한다                       ║
# ║      (보수적 추정 = '늦게 알았다' 방향이므로 누수를 만들지 않는다).                         ║
# ║    이것이 사용자가 요구한 '다중소스 원장연결'의 실체다 — 벌크는 값을, 공시목록은 시점을.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_DAILY_LIMIT = 19_000                 # 공식 20,000 대비 여유
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
# 벌크 파일명·공시 제목에 쓰이는 보고서 명칭 ↔ reprt_code
REPRT_NAME = {"11013": "1분기보고서", "11012": "반기보고서",
              "11014": "3분기보고서", "11011": "사업보고서"}
REPRT_BY_NAME = {v: k for k, v in REPRT_NAME.items()}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class DartBudget:
    """일일 호출 한도를 드라이브에 영속 기록. 재실행 시 이어받기의 근거."""

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0
        self.exhausted = False
        self._lk = threading.Lock()
        self._load()

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_budget.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘 이미 사용한 DART 호출 {self.n:,}건 (한도 {DART_DAILY_LIMIT:,}) — 이어서 진행합니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps({"date": self.today, "n": self.n}))
        except Exception:
            pass

    def refund(self, k: int = 1):
        if k > 0:
            with self._lk:
                self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.n + k > DART_DAILY_LIMIT:
                if not self.exhausted:
                    self.exhausted = True
                    LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                             f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일 같은 "
                             f"코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                return False
            self.n += k
            if self.n % 500 == 0:
                self._save()
            return True

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, source: str = "dart", tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 tries 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 한도를 넘긴다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DBUDGET is not None:
        DBUDGET.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            LOG.warn(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Primary — 재무정보 일괄다운로드 (벌크)
# ═══════════════════════════════════════════════════════════════════════════════════════════
DART_BULK_PAGE = "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do"
DART_BULK_DL = [
    "https://opendart.fss.or.kr/cmm/downloadFnltt.do",
    "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/download.do",
]
# 벌크 파일명 규칙(관측된 형태). 확정할 수 없으므로 페이지에서 '발견'을 우선하고
# 이 후보들은 발견이 실패했을 때만 쓴다. 어느 경로가 통했는지는 CANARY 표에 남는다.
BULK_STATEMENTS = ["재무상태표", "손익계산서", "포괄손익계산서", "현금흐름표"]
BULK_CONSOL = ["연결", "개별"]

_BULK_FLNM_RE = re.compile(r"(20\d{2}_[^\"'<>|]{4,80}?\.(?:zip|txt))", re.I)


def _bulk_candidates(year: int, reprt: str) -> List[str]:
    nm = REPRT_NAME.get(reprt, "사업보고서")
    out = []
    for i, st in enumerate(BULK_STATEMENTS, start=1):
        for cs in BULK_CONSOL:
            out.append(f"{year}_{nm}_{i:02d}_{st}_{cs}.zip")
    return out


def _bulk_discover(year: int, reprt: str) -> Tuple[List[str], str]:
    """페이지에서 실제 fl_nm 을 찾아낸다. 파일명 규칙을 추측하지 않는 것이 1순위다.

    반환 (후보 목록, 진단문자열).
    ★ 진단문자열이 핵심이다. "후보 N개 전부 실패" 만 남기면 사용자 로그를 받아도 원인을
      특정할 수 없다. 페이지를 받았는지 / 로그인 벽인지 / 어떤 링크·폼·스크립트가 있었는지를
      남겨야 다음 실행 로그 한 장으로 고칠 수 있다.
    """
    html = http_get(DART_BULK_PAGE, source="dart", tries=2,
                    params={"selectYear": str(year), "selectReprtCode": reprt},
                    referer="https://opendart.fss.or.kr/")
    if not html:
        return [], "페이지 응답 없음(네트워크 차단·타임아웃·403 가능). HTTP 감사표를 확인하세요"
    low = html.lower()
    marks = []
    if "login" in low or "로그인" in html:
        marks.append("로그인벽 의심")
    for kw in ("downloadfnltt", "fl_nm", "downloadzip", "flnm", "download.do"):
        if kw in low:
            marks.append(f"'{kw}' 발견")
    hits = [h for h in dict.fromkeys(_BULK_FLNM_RE.findall(html)) if str(year) in h]
    # 폼/앵커에서 실제 액션 URL 과 파라미터 이름을 긁어 남긴다
    acts = dict.fromkeys(re.findall(r'(?:action|href)\s*=\s*["\']([^"\']*(?:down|fnltt)[^"\']*)["\']',
                                    html, re.I))
    names = dict.fromkeys(re.findall(r'<input[^>]+name\s*=\s*["\']([^"\']+)["\']', html, re.I))
    diag = (f"HTML {len(html):,}자 · 후보 {len(hits)}개 · "
            f"{', '.join(marks) if marks else '단서 없음'} · "
            f"액션 {list(acts)[:3]} · 폼필드 {list(names)[:6]}")
    return hits, diag


def _bulk_fetch_one(fl_nm: str) -> Optional[bytes]:
    for base in DART_BULK_DL:
        for params in ({"fl_nm": fl_nm}, {"fl_nm": fl_nm, "crtfc_key": DART_API_KEY}):
            raw = http_get(base, source="dart", params=params, as_bytes=True, tries=2,
                           referer=DART_BULK_PAGE, timeout=120)
            if raw and len(raw) > 5000 and (raw[:2] == b"PK" or b"\t" in raw[:4000]):
                return raw
    return None


_BULK_VALUE_HINTS = ["당기 1분기 3개월", "당기 반기 3개월", "당기 3분기 3개월",
                     "당기 1분기 누적", "당기 반기 누적", "당기 3분기 누적",
                     "당기", "당기말"]


def _parse_bulk_txt(raw: bytes, year: int, reprt: str) -> pd.DataFrame:
    """벌크 zip/txt → 정규화 행. 컬럼 인덱스를 믿지 않고 헤더 텍스트로 찾는다."""
    blobs: List[bytes] = []
    if raw[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            for n in zf.namelist():
                if n.lower().endswith((".txt", ".csv")):
                    blobs.append(zf.read(n))
        except Exception:
            return pd.DataFrame()
    else:
        blobs.append(raw)

    rows = []
    for b in blobs:
        txt = _decode(b, None, "bulk")
        try:
            d = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str, engine="python",
                            on_bad_lines="skip")
        except Exception:
            continue
        if d is None or not len(d):
            continue
        cols = {re.sub(r"\s+", "", str(c)): c for c in d.columns}

        def pick(*names):
            for n in names:
                k = re.sub(r"\s+", "", n)
                if k in cols:
                    return cols[k]
            for k, orig in cols.items():
                if any(re.sub(r"\s+", "", n) in k for n in names):
                    return orig
            return None

        c_code = pick("종목코드")
        c_item = pick("항목코드")
        c_name = pick("항목명")
        c_sj = pick("재무제표종류")
        c_end = pick("결산기준일")
        if not (c_code and c_name):
            continue
        # 금액 컬럼: '당기...' 중 가장 먼저 맞는 것. 누적(3개월이 아닌)을 우선한다 —
        # 우리는 아래에서 누적→분기 차분을 하므로 누적이 정본이다.
        c_val = None
        for h in _BULK_VALUE_HINTS:
            c_val = pick(h)
            if c_val is not None:
                break
        if c_val is None:
            num_like = [c for c in d.columns if str(c).startswith("당기")]
            c_val = num_like[0] if num_like else None
        if c_val is None:
            continue

        t = pd.DataFrame({
            "stock_code": d[c_code].astype(str).str.replace(r"[\[\]\s]", "", regex=True).map(to_code6),
            "account_id": (d[c_item].astype(str) if c_item else ""),
            "account_nm": d[c_name].astype(str).str.replace(r"\s+", "", regex=True),
            "sj_raw": (d[c_sj].astype(str) if c_sj else ""),
            "period_end_raw": (d[c_end].astype(str) if c_end else ""),
            "thstrm_amount": d[c_val].astype(str),
        })
        rows.append(t)

    if not rows:
        return pd.DataFrame()
    R = pd.concat(rows, ignore_index=True).dropna(subset=["stock_code"])
    R["bsns_year"] = int(year)
    R["reprt_code"] = str(reprt)
    # 재무제표종류 문자열에서 BS/IS/CIS/CF 를 판별한다 (파일마다 표기가 조금씩 다르다)
    sj = R["sj_raw"].astype(str)
    R["sj_div"] = np.select(
        [sj.str.contains("재무상태", na=False),
         sj.str.contains("포괄손익", na=False),
         sj.str.contains("손익", na=False),
         sj.str.contains("현금흐름", na=False)],
        ["BS", "CIS", "IS", "CF"], default="OTHER")
    R["fs_div"] = np.where(sj.str.contains("연결", na=False), "CFS", "OFS")
    return R


def fetch_dart_bulk(years: Sequence[int], reprts: Sequence[str]) -> pd.DataFrame:
    """§4.1 Primary. 파일을 통째로 받고 필터는 다운로드 이후에 한다. 종목별 루프 없음."""
    cached = VAULT.get_table("dart_bulk_raw", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["bsns_year"].astype(int), cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 벌크 {len(cached):,}행 재사용 ({len(done)} 분기)")
    jobs = [(int(y), str(r)) for y in years for r in reprts if (int(y), str(r)) not in done]
    if RUN_MODE == "CACHED" or not DART_API_KEY:
        jobs = []

    got: List[pd.DataFrame] = []
    ok_q, fail_q = [], []
    if jobs:
        LOG.info(f"DART 재무정보 일괄다운로드 {len(jobs)} 분기 (분기당 파일 여러 개)")
        for y, r in tqdm(jobs, desc="DART 벌크", ncols=88, leave=False):
            names, diag = _bulk_discover(y, r)
            if not names:
                names = _bulk_candidates(y, r)
                LOG.debug(f"벌크 {y}/{REPRT_NAME.get(r, r)} 발견 실패 → 추측 후보 사용 · {diag}")
            frames = []
            for fl in names:
                raw = _bulk_fetch_one(fl)
                if not raw:
                    continue
                # 원본은 공용 인덱스에 그대로 보관 — 다른 전략이 재파싱할 수 있게(L0 불변)
                VAULT.put_blob("dart", "fnltt_bulk", fl, raw,
                               "zip" if raw[:2] == b"PK" else "txt",
                               source="opendart bulk", scope="shared",
                               event_date=f"{y}-12-31", knowledge_date=None,
                               extra={"year": y, "reprt": r})
                t = _parse_bulk_txt(raw, y, r)
                if len(t):
                    frames.append(t)
            if frames:
                got.append(pd.concat(frames, ignore_index=True))
                ok_q.append((y, r))
            else:
                fail_q.append((y, r))
        VAULT.flush("shared")

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        if jobs:
            LOG.warn("재무정보 일괄다운로드를 한 건도 받지 못했습니다 — Fallback A(fnlttMultiAcnt)"
                     "로 전환합니다. (§4.1). 벌크 경로는 공개 API 가 아니라 웹 다운로드라 "
                     "사이트 구조 변경에 취약합니다 — CANARY K1 결과를 확인하세요.")
        return pd.DataFrame(columns=["stock_code", "account_id", "account_nm", "sj_div",
                                     "fs_div", "thstrm_amount", "bsns_year", "reprt_code"])
    B = pd.concat(frames, ignore_index=True)
    B = B.drop_duplicates(["stock_code", "bsns_year", "reprt_code", "sj_div", "fs_div",
                           "account_id", "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_bulk_raw", B, scope="shared", domain="dart",
                        source="opendart 재무정보 일괄다운로드")
    LOG.ok(f"DART 벌크 {len(B):,}행 · {B['stock_code'].nunique():,}종목 "
           f"(성공 분기 {len(ok_q)} / 실패 {len(fail_q)})")
    PIPE.io("IN", "HTTP", "dart:bulk", B, source="opendart bulk", ok=len(B) > 0)
    return B


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Fallback A — fnlttMultiAcnt 배치 (100사/호출)
# ═══════════════════════════════════════════════════════════════════════════════════════════
DART_MULTI_BATCH = 100
_FS_KEEP = ["corp_code", "stock_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]


def fetch_dart_multi(corp_codes: Sequence[str], years: Sequence[int],
                     reprts: Sequence[str]) -> pd.DataFrame:
    """주요계정 배치. 벌크가 실패했을 때의 1차 폴백.

    ⚠ '주요계정'만 온다: 매출·영업이익·순이익·자산·부채·자본.
      재고·매출채권·영업CF·유형자산취득이 **없다** → i_dio/i_dso/i_accr/i_capex 가 죽고
      TP_I2·TP_I4·TP_I1 이 전부 무력화된다. 이 사실을 커버리지 표에 명시한다.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")
    corps = [str(c) for c in corp_codes]
    jobs = []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps if (c, int(y), str(r)) not in done]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), str(r)))
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        batch, y, r = job
        js = dart_api("fnlttMultiAcnt.json",
                      {"corp_code": ",".join(batch), "bsns_year": str(y), "reprt_code": r})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["bsns_year"] = int(y)
        d["reprt_code"] = str(r)
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]
    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_nm"],
                          keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사")
    PIPE.io("IN", "HTTP", "dart:multi", M, source="opendart fnlttMultiAcnt")
    return M


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1 Fallback B — fnlttSinglAcntAll (전체 재무제표, 회사×연도×보고서 단건)
# ═══════════════════════════════════════════════════════════════════════════════════════════
#  ★ 왜 이게 필요한가 (실측으로 확인된 상황):
#    벌크(K1)가 실패하면 Fallback A(fnlttMultiAcnt)만 남는데, A 는 '주요계정'만 준다 —
#    매출·영업이익·순이익·자산·부채·자본. **재고·매출채권·영업CF·유형자산취득이 없다.**
#    그러면 i_dio·i_dso·i_accr·i_capex 가 전부 결측이 되고
#    TP_I2(매출↑인데 회전 유지)·TP_I4(매출↑인데 발생액 유지)·TP_I1(확장하는데 ROIC 유지)이
#    죽는다. 즉 전략의 코어가 사라진 채로 백테스트가 '성공'한다. 그건 결과가 아니라 착시다.
#
#  ★ 비용의 현실을 숨기지 않는다:
#    연 1회(사업보고서)  : 2,600사 × 11년         ≈ 28,600 콜 → 일 19,000 한도로 약 2일
#    분기 전체           : 2,600사 × 11년 × 4분기 ≈ 114,400 콜 →              약 6일
#    그래서 기본값은 annual 이고, 이어받기가 전제다. 중단돼도 받은 만큼 드라이브에 남고
#    다음 실행이 정확히 그 지점부터 잇는다.
DART_FS_FREQ = "annual"          # "annual"(약 2일) | "quarterly"(약 6일)


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    # 연결(CFS) 우선, 없으면 개별(OFS). 순서를 바꾸면 지주사에서 매출이 통째로 달라진다.
    for fs_div in ("CFS", "OFS"):
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": reprt, "fs_div": fs_div})
        if js and isinstance(js.get("list"), list) and js["list"]:
            d = pd.DataFrame(js["list"])
            for c in _FS_KEEP:
                if c not in d.columns:
                    d[c] = None
            d["corp_code"] = corp
            d["bsns_year"] = int(year)
            d["reprt_code"] = str(reprt)
            d["fs_div"] = fs_div
            return d[_FS_KEEP]
    return None


def fetch_dart_full(corp_codes: Sequence[str], years: Sequence[int],
                    priority: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """전체 재무제표. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(유동성 상위)대로 먼저 받는다. 일일 한도로 중간에 끊기는 것이
    **정상 시나리오**이므로, 끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가
    되도록 정렬한다. 무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아
    백테스트를 못 돌린다.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = set()
    if nonempty(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 전체재무제표 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = ([REPRT_CODES["FY"]] if DART_FS_FREQ == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes), key=lambda c: (order.get(c, 10 ** 9), c))
    jobs = [(c, y, r) for y in sorted(years, reverse=True)      # 최근 연도 우선
            for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    got = []
    if jobs:
        avail = max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0))
        days = math.ceil(len(jobs) * 1.3 / max(DART_DAILY_LIMIT, 1))
        LOG.warn(f"전체 재무제표 신규 수집 대상 {len(jobs):,}건 (오늘 가용 호출 {avail:,}건). "
                 f"콜당 최대 2회 요청이므로 콜드빌드에 약 {days}일이 걸립니다 "
                 f"(DART_FS_FREQ='{DART_FS_FREQ}'). 오늘 받을 수 있는 만큼 받아 드라이브에 "
                 f"저장하고, 내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다. "
                 f"유동성 상위·최근 연도부터 채우므로 중간에 끊겨도 상위 종목은 먼저 완성됩니다.")
        res = pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 12), desc="DART 전체재무제표")
        got = [d for d in res if nonempty(d)]

    frames = ([cached] if nonempty(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    F = pd.concat(frames, ignore_index=True)
    F = F.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_fnltt_raw", F, scope="shared", domain="dart",
                        source="opendart fnlttSinglAcntAll")
    n_have = F.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(F) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"전체 재무제표 진행률 {n_have:,}/{n_need:,} ({100*n_have/max(n_need,1):.1f}%) — "
             f"재실행하면 이 지점부터 이어받습니다.")
    PIPE.io("IN", "HTTP", "dart:fnlttSinglAcntAll", F, source="opendart", ok=len(F) > 0)
    return F


def merge_financial_tiers(*tiers: pd.DataFrame) -> pd.DataFrame:
    """상위 티어를 우선하고, 없는 (회사, 기간) 조합만 하위 티어로 메운다.

    티어 순서 = 정보량 순서: 벌크/전체재무제표(전 계정) > 주요계정(6개 계정).
    콜드빌드가 며칠 걸리는 동안에도 주요계정이 전 종목을 덮고 있어 유니버스·규모버킷·
    R3 팩터가 즉시 동작하고, 전체 재무제표가 도착하는 종목부터 TP 가 살아난다.
    """
    tiers = [t for t in tiers if nonempty(t)]
    if not tiers:
        return pd.DataFrame(columns=_FS_KEEP)
    out = tiers[0]
    for t in tiers[1:]:
        keys = ("corp_code", "bsns_year", "reprt_code")
        if not all(k in out.columns for k in keys) or not all(k in t.columns for k in keys):
            out = pd.concat([out, t], ignore_index=True)
            continue
        have = set(zip(out["corp_code"].astype(str), out["bsns_year"].astype(int),
                       out["reprt_code"].astype(str)))
        key = list(zip(t["corp_code"].astype(str), t["bsns_year"].astype(int),
                       t["reprt_code"].astype(str)))
        fill = t[[k not in have for k in key]]
        if len(fill):
            LOG.info(f"하위 티어로 보완한 (회사×기간) "
                     f"{fill.groupby(list(keys)).ngroups:,}건 — 상위 티어가 도착하면 자동 대체됩니다.")
            out = pd.concat([out, fill], ignore_index=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  공시목록 — 값이 아니라 '시점'과 '이벤트'를 준다
# ═══════════════════════════════════════════════════════════════════════════════════════════
DISCLOSURE_PATTERNS = {
    "treasury_acq":   r"자기주식\s*취득(?!.*신탁\s*해지)",
    "treasury_trust": r"자기주식\s*취득\s*신탁",
    "treasury_canc":  r"자기주식\s*소각|이익소각|주식소각",
    "dividend":       r"현금.?현물배당결정|결산배당|중간배당|배당\s*결정",
    "rights_issue":   r"유상증자",
    "cb_issue":       r"전환사채",
    "bw_issue":       r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion":  r"감사보고서",
    "periodic":       r"(사업보고서|반기보고서|분기보고서)",
}


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다.

    두 가지 용도가 있고 둘 다 필수다:
      ① 정기공시(A) → (회사, 보고서종류, 연도) → **접수일자**. 벌크 재무의 knowledge_date.
      ② 주요사항(B) → 자사주 취득/소각(TP_P2), 유증·CB·BW(V3), 감사의견(V5).
    """
    empty = pd.DataFrame(columns=["corp_code", "stock_code", "rcept_no", "rcept_dt",
                                  "report_nm", "event", "event_date", "knowledge_date"])
    if not DART_API_KEY:
        return empty
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    have_months = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        todo = []

    def _one(m):
        rows = []
        for ty in ("A", "B"):                     # A=정기공시, B=주요사항보고
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})       # ★ 'N' — 정정 전 원본까지 전부 받는다
                if not js or not isinstance(js.get("list"), list) or not js["list"]:
                    break
                rows.extend(js["list"])
                if page >= int(js.get("total_page", 1) or 1):
                    break
                page += 1
        return rows

    new = []
    if todo:
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="DART 공시목록")
        for r in res:
            if r:
                new.extend(r)

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "flr_nm", "corp_cls") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return empty
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    if "stock_code" in D.columns:
        D["stock_code"] = D["stock_code"].map(to_code6)
    D["event"] = ""
    for ev, pat in DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        out = D.copy()
        out["rcept_dt"] = out["rcept_dt"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("dart_disclosures", out, scope="shared", domain="dart",
                        source="opendart list.json")
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")       # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={int((D['event'] == k).sum()):,}"
                     for k in DISCLOSURE_PATTERNS if (D["event"] == k).any()))
    PIPE.io("IN", "HTTP", "dart:list", D, source="opendart list.json")
    return D


_PERIODIC_RE = re.compile(r"(사업보고서|반기보고서|분기보고서)")
_PERIOD_IN_TITLE = re.compile(r"\((\d{4})\.(\d{2})\)")


def build_knowledge_map(dis: pd.DataFrame) -> pd.DataFrame:
    """공시목록 → (stock_code, bsns_year, reprt_code) → 접수일자.

    ★ 벌크 재무에 없는 유일한 것이 시점이다. 이 표가 없으면 C1 을 만족할 수 없다.
    ★ 정정공시가 있으면 접수일자가 여러 개다. **가장 이른 접수일자**를 쓴다 —
      정정본의 접수일을 쓰면 원본을 알 수 있었던 시점보다 늦춰 잡아 보수적이지만,
      우리가 결합하는 값은 원본 값이므로 원본 시점이 맞다.
      (반대로 정정본 값을 원본 접수일에 붙이면 그게 곧 미래누수다 — 그건 하지 않는다)
    """
    cols = ["stock_code", "bsns_year", "reprt_code", "knowledge_date"]
    if dis is None or dis.empty:
        return pd.DataFrame(columns=cols)
    d = dis[dis["report_nm"].str.contains(_PERIODIC_RE, na=False)].copy()
    if d.empty or "stock_code" not in d.columns:
        return pd.DataFrame(columns=cols)
    d = d.dropna(subset=["stock_code"])

    nm = d["report_nm"].astype(str)
    # 제목 예: "분기보고서 (2016.03)" / "사업보고서 (2015.12)" / "반기보고서 (2016.06)"
    per = nm.str.extract(_PERIOD_IN_TITLE)
    d["p_year"] = pd.to_numeric(per[0], errors="coerce")
    d["p_month"] = pd.to_numeric(per[1], errors="coerce")

    d["reprt_code"] = np.select(
        [nm.str.contains("사업보고서", na=False),
         nm.str.contains("반기보고서", na=False),
         nm.str.contains("분기보고서", na=False) & d["p_month"].eq(3),
         nm.str.contains("분기보고서", na=False) & d["p_month"].eq(9)],
        [REPRT_CODES["FY"], REPRT_CODES["H1"], REPRT_CODES["Q1"], REPRT_CODES["Q3"]],
        default="")
    # 제목에 기간이 없는 분기보고서는 접수월로 추정한다(1~5월 접수 → Q1, 그 외 → Q3).
    miss = (d["reprt_code"] == "") & nm.str.contains("분기보고서", na=False)
    if miss.any():
        mo = d.loc[miss, "rcept_dt"].dt.month
        d.loc[miss, "reprt_code"] = np.where(mo <= 8, REPRT_CODES["Q1"], REPRT_CODES["Q3"])
        d.loc[miss, "p_year"] = d.loc[miss, "rcept_dt"].dt.year - np.where(mo <= 2, 1, 0)
    d = d[d["reprt_code"] != ""]
    if d.empty:
        return pd.DataFrame(columns=cols)

    # 사업연도: 제목의 연도가 있으면 그것, 없으면 접수일 기준 추정
    yr = d["p_year"]
    fallback_yr = d["rcept_dt"].dt.year - np.where(d["rcept_dt"].dt.month <= 4, 1, 0)
    d["bsns_year"] = pd.to_numeric(yr.fillna(pd.Series(fallback_yr, index=d.index)),
                                   errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    d["bsns_year"] = d["bsns_year"].astype(int)

    K = (d.groupby(["stock_code", "bsns_year", "reprt_code"], as_index=False)["rcept_dt"]
          .min().rename(columns={"rcept_dt": "knowledge_date"}))
    LOG.ok(f"접수일자 원장 {len(K):,}건 ({K['stock_code'].nunique():,}종목) — "
           f"벌크 재무의 knowledge_date 를 여기서 확정합니다 (다중소스 원장연결).")
    PIPE.io("OUT", "MEM", "dart_knowledge_map", K, source="dart list.json → 접수일자")
    return K


def _deadline_knowledge(year: int, reprt: str) -> pd.Timestamp:
    mm, dd = REPRT_PERIOD_END.get(reprt, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt, 90))


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  계정 매핑 — account_id(IFRS 표준코드) 우선, 실패 시 account_nm
# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §4.1: "매핑 테이블은 config/account_map.yaml 로 분리하고 커버리지를 로깅한다(K3)."
#  단일 파일 배포이므로 dict 로 인라인하되, 구조는 동일하게 (sj, [id정규식], [명칭정규식]) 로 분리한다.
ACCOUNT_MAP: Dict[str, Tuple[str, List[str], List[str]]] = {
    # 항목:            (재무제표, [account_id 정규식],                      [account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"_Revenue$"],
                            [r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$", r"^매출$"]),
    "cogs":          ("IS", [r"CostOfSales"], [r"^매출원가$", r"^영업비용$"]),
    "gross_profit":  ("IS", [r"GrossProfit"], [r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense"], [r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense"], [r"경상(연구)?개발비", r"^연구개발비"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"_ProfitLossFromOperatingActivities"],
                            [r"^영업이익"]),
    "net_income":    ("IS", [r"ifrs-full_ProfitLoss$"], [r"^당기순이익", r"^분기순이익", r"^반기순이익"]),
    "inventory":     ("BS", [r"Inventories"], [r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"CurrentTradeReceivables"],
                            [r"^매출채권", r"^매출채권및기타"]),
    "assets":        ("BS", [r"ifrs-full_Assets$"], [r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$"], [r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$"], [r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment$"], [r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssets"], [r"^무형자산$"]),
    "cur_assets":    ("BS", [r"ifrs-full_CurrentAssets$"], [r"^유동자산$"]),
    "cur_liab":      ("BS", [r"ifrs-full_CurrentLiabilities$"], [r"^유동부채$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents"], [r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities"], [r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities"], [r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment"], [r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense"], [r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid"], [r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares"], [r"자기주식의?\s*취득"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense"], [r"법인세비용"]),
    "pretax_income": ("IS", [r"ProfitLossBeforeTax"], [r"법인세비용차감전"]),
}
_SJ_ACCEPT = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# 손익·현금흐름 성격의 전 계정 — 누적공시라 분기 차분이 필요하다.
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy",
              "tax_expense", "pretax_income"]
# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼. 수집이 얼마나 실패하든 스키마는 항상 같아야
# 한다 — 그래야 "어떤 실행엔 있고 어떤 실행엔 없는" 축이 사라지고 결측이 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_MAP)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q", "period_end"])

ACCOUNT_COVERAGE: Dict[str, float] = {}


def _num(s) -> pd.Series:
    return pd.to_numeric(
        pd.Series(s).astype(str)
          .str.replace(",", "", regex=False)
          .str.replace("−", "-", regex=False)
          .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
          .str.replace(r"[^\d.\-]", "", regex=True)
          .replace({"": np.nan, "-": np.nan, ".": np.nan}),
        errors="coerce")


def tidy_financials(raw: pd.DataFrame, kmap: pd.DataFrame,
                    code_of_corp: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """원시 계정 → (code, period_end, 항목) 와이드. knowledge_date 를 여기서 확정한다."""
    base_cols = ["code", "period_end", "knowledge_date", "bsns_year", "reprt_code"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)
    d = raw.copy()

    # 종목코드 통일 — 벌크는 stock_code, API 는 corp_code 로 온다
    if "stock_code" in d.columns:
        d["code"] = d["stock_code"].map(to_code6)
    else:
        d["code"] = None
    if d["code"].isna().any() and code_of_corp and "corp_code" in d.columns:
        need = d["code"].isna()
        d.loc[need, "code"] = d.loc[need, "corp_code"].astype(str).map(code_of_corp)
    d = d.dropna(subset=["code"])
    if d.empty:
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)

    d["amount"] = _num(d["thstrm_amount"])
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str).fillna("")
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    d["sj_div"] = d["sj_div"].astype(str)
    # 연결(CFS) 우선. 개별만 있는 회사는 개별을 쓴다.
    d["_fs_pri"] = np.where(d.get("fs_div", pd.Series("", index=d.index)).astype(str) == "CFS", 0, 1)

    out_rows = []
    cov = {}
    for key, (sj, id_pats, nm_pats) in ACCOUNT_MAP.items():
        sub = d[d["sj_div"].isin(_SJ_ACCEPT.get(sj, (sj,)))]
        if sub.empty:
            cov[key] = 0.0
            continue
        # ★ account_id(IFRS 표준코드) 우선. 표준코드가 붙은 행이 있으면 명칭 매칭은 보지 않는다.
        #   명칭은 회사마다 제각각이라 '영업수익'을 매출로 잡는 등 오매칭이 잦다.
        rx_id = re.compile("|".join(id_pats), re.I) if id_pats else None
        rx_nm = re.compile("|".join(nm_pats), re.I) if nm_pats else None
        hit_id = sub[sub["account_id"].str.contains(rx_id, na=False)] if rx_id is not None \
            else sub.iloc[0:0]
        hit_nm = sub[sub["account_nm"].str.contains(rx_nm, na=False)] if rx_nm is not None \
            else sub.iloc[0:0]
        hit_id = hit_id.assign(_pri=0)
        hit_nm = hit_nm.assign(_pri=1)
        hit = pd.concat([hit_id, hit_nm], ignore_index=True)
        if hit.empty:
            cov[key] = 0.0
            continue
        # (회사, 기간) 당 1행: 표준코드 > 명칭, 연결 > 개별, 그다음 절대값 큰 쪽(대표 계정)
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values(["_pri", "_fs_pri", "_a"], ascending=[True, True, False])
                  .drop_duplicates(["code", "bsns_year", "reprt_code"], keep="first"))
        cov[key] = float(hit["code"].nunique())
        cols = ["code", "bsns_year", "reprt_code", "amount"]
        if "rcept_no" in hit.columns:
            cols.append("rcept_no")
        out_rows.append(hit.assign(item=key)[cols + ["item"]])

    if not out_rows:
        LOG.error("계정 매핑이 한 건도 성립하지 않았습니다. ACCOUNT_MAP 정규식과 소스 스키마를 "
                  "확인하세요. (재무 기반 센서가 전부 결측이 됩니다)")
        return pd.DataFrame(columns=base_cols + FUNDAMENTAL_COLS)

    L = pd.concat(out_rows, ignore_index=True)
    n_codes = max(L["code"].nunique(), 1)
    ACCOUNT_COVERAGE.clear()
    ACCOUNT_COVERAGE.update({k: v / n_codes for k, v in cov.items()})

    W = L.pivot_table(index=["code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    if "rcept_no" in L.columns:
        rc = (L.dropna(subset=["rcept_no"]).sort_values("rcept_no")
               .groupby(["code", "bsns_year", "reprt_code"])["rcept_no"].first().reset_index())
        W = W.merge(rc, on=["code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12, 31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12, 31))[1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]

    # ── knowledge_date 확정 (C1 의 급소) ─────────────────────────────────────────────────
    W["bsns_year"] = W["bsns_year"].astype(int)
    W["reprt_code"] = W["reprt_code"].astype(str)
    W["knowledge_date"] = pd.NaT
    n_map = n_rcept = n_deadline = 0
    if kmap is not None and len(kmap):
        k = kmap.copy()
        k["bsns_year"] = k["bsns_year"].astype(int)
        k["reprt_code"] = k["reprt_code"].astype(str)
        k = k.rename(columns={"stock_code": "code", "knowledge_date": "_kd_map"})
        W = W.merge(k[["code", "bsns_year", "reprt_code", "_kd_map"]],
                    on=["code", "bsns_year", "reprt_code"], how="left")
        W["knowledge_date"] = as_ts_series(W["_kd_map"])
        n_map = int(W["knowledge_date"].notna().sum())
        W = W.drop(columns=["_kd_map"])
    if "rcept_no" in W.columns:
        need = W["knowledge_date"].isna()
        if need.any():
            s = W.loc[need, "rcept_no"].astype(str).str.replace(r"\D", "", regex=True)
            kd = as_ts_series(s.str.slice(0, 8))
            W.loc[need, "knowledge_date"] = kd.where(kd.dt.year.between(2000, 2100))
            n_rcept = int(W["knowledge_date"].notna().sum()) - n_map
    need = W["knowledge_date"].isna()
    if need.any():
        W.loc[need, "knowledge_date"] = [
            _deadline_knowledge(int(y), str(r))
            for y, r in zip(W.loc[need, "bsns_year"], W.loc[need, "reprt_code"])]
        n_deadline = int(need.sum())
    LOG.table([["① 공시목록 접수일자 (정확)", f"{n_map:,}", "✔ C1 정확"],
               ["② rcept_no 앞 8자리", f"{n_rcept:,}", "✔ C1 정확"],
               ["③ 법정 제출기한 추정", f"{n_deadline:,}",
                "⚠ 보수적(늦게 앎) — 누수는 없으나 신호가 늦어짐"]],
              ["knowledge_date 출처", "행수", "판정"], ["l", "r", "l"],
              title="재무 PIT 시점 확정 — 벌크 파일에는 접수일자가 없어 공시목록과 결합합니다")
    if n_deadline > 0.5 * len(W):
        LOG.warn(f"재무 {100*n_deadline/max(len(W),1):.0f}% 가 법정기한 추정입니다. "
                 f"공시목록 수집이 부족하다는 뜻입니다 — 신호가 실제보다 최대 45일 늦게 반영되어 "
                 f"성과가 보수적으로(낮게) 나옵니다. 미래누수 방향은 아닙니다.")

    # ── 누적 → 분기 단독 ─────────────────────────────────────────────────────────────────
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.dropna(subset=["q"]).sort_values(["code", "bsns_year", "q"]).reset_index(drop=True)
    gk = ["code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in FLOW_ITEMS:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        # ★ 누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다. fail-open 금지.
        W[c + "_q"] = np.where(W["q"] == 1, W[c], np.where(contiguous, W[c] - prev, np.nan))
        # TTM = 4분기 이동합. min_periods=4 — 3개로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])

    for k in ACCOUNT_MAP:
        if k not in W.columns:
            W[k] = np.nan

    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' (분기 프레임에서 센다) ───────────────────
    #   ★ 월 패널에서 rolling(9) 로 세면 같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도
    #     정답이 아니다. 발동이 1~2개월 늦고 결산→1Q→반기 창은 아예 놓친다.
    #     분기 프레임은 관측당 정확히 한 행이고 이미 (code, year, q) 로 정렬돼 있다.
    _bad = ((col(W, "net_income_ttm") > 0) &
            (col(W, "cfo_ttm") < 0.5 * col(W, "net_income_ttm"))).astype(float)
    W["v2_bad_3q"] = (_bad.groupby(W["code"], observed=True)
                          .transform(lambda s: s.rolling(3, min_periods=3).min()))

    miss = [k for k in ACCOUNT_MAP if W[k].notna().sum() == 0]
    if miss:
        LOG.warn(f"한 건도 매칭되지 않은 계정 {len(miss)}개: {miss[:10]} — "
                 f"이 계정을 쓰는 센서는 전부 결측이 됩니다(0으로 채우지 않음).")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"재무 정제 {len(W):,}행 · {W['code'].nunique():,}종목 "
           f"(누적→분기 차분 · TTM min_periods=4 완료)")
    PIPE.io("OUT", "MEM", "financials_tidy", W)
    return downcast(W)


def report_account_coverage(min_cov: float = 0.85):
    """CANARY K3 의 본선 판. 필수 계정 커버리지가 기준 미만이면 어떤 TP 가 죽는지 명시한다."""
    if not ACCOUNT_COVERAGE:
        return set()
    need = {"revenue": ["TP_I2", "TP_I4", "V1"], "cogs": ["TP_I2(i_dio)"],
            "inventory": ["TP_I2(i_dio)", "V1"], "receivable": ["TP_I2(i_dso)", "V1"],
            "cfo": ["TP_I4(i_accr)", "TP_P1", "V2"], "capex": ["TP_I1", "TP_P1"],
            "net_income": ["TP_I4", "V2"], "assets": ["TP_I4"],
            "equity": ["V5"], "ppe": ["TP_I1(i_ic)"], "op_income": ["TP_I3(i_vapp)"]}
    rows, weak = [], set()
    for k, tps in need.items():
        c = ACCOUNT_COVERAGE.get(k, 0.0)
        ok = c >= min_cov
        if not ok:
            weak.update(tps)
        rows.append([k, f"{100*c:.1f}%", "✔" if ok else f"❗ {min_cov:.0%} 미만",
                     ", ".join(tps)])
    LOG.table(sorted(rows, key=lambda r: float(r[1].rstrip("%"))),
              ["계정", "커버리지", "판정", "영향받는 지표"], ["l", "r", "l", "l"],
              title=f"필수 계정 커버리지 (CANARY K3 · 기준 {min_cov:.0%})")
    if weak:
        LOG.warn(f"커버리지 미달로 신뢰도가 낮은 지표: {sorted(weak)}. "
                 f"§1 K3 는 '85% 미만 계정을 쓰는 TP 를 비활성화' 하라고 요구합니다 — "
                 f"비활성화 여부는 아래 CANARY 판정표를 따릅니다.")
    return weak


# ── 직원현황 (M2 · TP_I3) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int],
                         code_of_corp: Dict[str, str]) -> pd.DataFrame:
    cols = ["code", "bsns_year", "employees", "payroll", "event_date", "knowledge_date"]
    if not DART_API_KEY:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(str(c), int(y)) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 서로소이므로 합산이
        #   맞지만, 일부 기업은 '합계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이라 아예 쓰지 않는다.
        for c in ("fo_bbm", "sexdstn"):
            if c in d.columns:
                d = d[~d[c].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        emp = float(_num(d["sm"]).sum(skipna=True)) if "sm" in d.columns else np.nan
        pay = float(_num(d["fyer_salary_totamt"]).sum(skipna=True)) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year),
                "employees": emp if emp > 0 else np.nan,
                "payroll": pay if pay > 0 else np.nan, "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart",
                        source="opendart empSttus")
    # ★ E.get("rcept_no","") 는 컬럼이 없으면 '문자열'을 돌려주고 zip 이 그걸 글자 단위로 훑어
    #   knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["code"] = E["corp_code"].astype(str).map(code_of_corp)
    E = E.dropna(subset=["code"])
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    s = E["rcept_no"].astype(str).str.replace(r"\D", "", regex=True)
    kd = as_ts_series(s.str.slice(0, 8))
    E["knowledge_date"] = kd.where(kd.dt.year.between(2000, 2100))
    need = E["knowledge_date"].isna()
    if need.any():
        E.loc[need, "knowledge_date"] = [_deadline_knowledge(int(y), REPRT_CODES["FY"])
                                         for y in E.loc[need, "bsns_year"]]
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"직원현황 {len(E):,}행 · {E['code'].nunique():,}종목")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [11/22]  15_mcap.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-G  PIT 시가총액 · 상장주식수  — 계약 C13 의 유일한 입력                                ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 없으면 C13 은 성립하지 않는다. 그리고 C13 이 깨지면 이 전략은 자기가 찾는     ║
# ║    대상을 정의상 제거한다.                                                                ║
# ║                                                                                          ║
# ║    우리가 찾는 건 "시총 800억이 8,000억이 된 기업"이다. 현재 시총으로 유니버스를 자르면    ║
# ║    그 종목은 '지금 중대형주'라서 밴드 밖이고, 2016년 시점 데이터에서도 빠진다.             ║
# ║    성공 사례가 통째로 사라지는데 예외도 경고도 나지 않는다. 우측 꼬리에 의존하는           ║
# ║    전략에서 이건 조용한 거짓 음성이고, 생존자편향과 정확히 같은 급의 사고다.                ║
# ║                                                                                          ║
# ║  소스 우선순위 (모두 실패해도 죽지 않고, 무엇을 썼는지 반드시 표로 보고한다):              ║
# ║    ① pykrx get_market_cap_by_ticker(date)   진짜 PIT. 시총·상장주식수 둘 다.  ★1순위       ║
# ║    ② 네이버 금융 시가총액 페이지            현재값만 → 과거 복원 불가. 보강용             ║
# ║    ③ FDR StockListing 의 Stocks(상장주식수) 를 과거로 고정 + 과거 종가                     ║
# ║       → ★근사다. 유증·액면분할·감자를 반영하지 못한다. 편향 방향을 아래에 명시한다.        ║
# ║    ④ 20일 평균거래대금 랭크 (최후)          규모가 아니라 유동성이다. 판정에 명시한다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MCAP_COLS = ["code", "month", "mcap", "shares", "mcap_src"]


def _mcap_pykrx_month(d: pd.Timestamp) -> Optional[pd.DataFrame]:
    """특정 월말의 전 종목 시총·상장주식수. KRXG 게이트로 직렬 호출한다."""
    if pykrx_stock is None:
        return None
    bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                   d.strftime("%Y%m%d"), prev=True)
    if not bd:
        return None
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
        if t is None or len(t) == 0:
            continue
        t = t.reset_index()
        ren = {"티커": "code", "종목코드": "code", "시가총액": "mcap", "상장주식수": "shares"}
        t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
        if "code" not in t.columns:
            t = t.rename(columns={t.columns[0]: "code"})
        if "mcap" not in t.columns:
            continue
        frames.append(t[["code"] + [c for c in ("mcap", "shares") if c in t.columns]])
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out["code"] = out["code"].map(to_code6)
    out = out.dropna(subset=["code"])
    out["month"] = d
    out["mcap_src"] = "pykrx"
    for c in ("mcap", "shares"):
        if c not in out.columns:
            out[c] = np.nan
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 시총 0/음수는 데이터 오류다. 랭크에 넣으면 그 종목이 최하위를 차지해 밴드를 밀어낸다.
    out.loc[~(out["mcap"] > 0), "mcap"] = np.nan
    return out[MCAP_COLS]


def fetch_pit_marketcap(months: pd.DatetimeIndex, px_monthly: pd.DataFrame,
                        sec: pd.DataFrame) -> pd.DataFrame:
    """월말 격자의 PIT 시가총액. 공용 인덱스에 저장 — 다른 전략이 그대로 재사용한다."""
    cached = VAULT.get_table("krx_marketcap_monthly", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["month"] = as_ts_series(cached["month"])
        cached["code"] = cached["code"].map(to_code6)
        cached = cached.dropna(subset=["month", "code"])
        have = set(cached["month"].dt.strftime("%Y-%m-%d"))
        frames.append(cached)
        LOG.info(f"공용 캐시에서 PIT 시가총액 {len(cached):,}행 재사용 ({len(have)}개 월)")

    todo = [m for m in months if m.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 시총 미수집 {len(todo)}개월을 건너뜁니다.")
        todo = []

    got_new = False
    if todo and pykrx_stock is not None:
        KRXG.warmup()
        LOG.info(f"PIT 시가총액 {len(todo)}개월 수집 (직렬 · 월당 2호출)")
        bad_streak = 0
        for d in tqdm(todo, desc="PIT 시가총액", ncols=88, leave=False):
            t = _mcap_pykrx_month(d)
            if t is not None and len(t):
                frames.append(t)
                got_new = True
                bad_streak = 0
            else:
                bad_streak += 1
                if bad_streak >= 6:
                    LOG.warn("시총 조회가 연속 6개월 비었습니다 — KRX 세션이 끊겼거나 "
                             "차단된 상태입니다. 수집을 중단하고 근사 경로로 폴백합니다.")
                    break
    elif todo:
        LOG.warn("pykrx 가 없어 PIT 시가총액을 직접 받을 수 없습니다 — 근사 경로로 폴백합니다.")

    M = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=MCAP_COLS)
    if len(M):
        M = (M.sort_values(["code", "month"])
               .drop_duplicates(["code", "month"], keep="last").reset_index(drop=True))
    if got_new:
        out = M.copy()
        out["month"] = out["month"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_monthly", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "PIT 시가총액·상장주식수 월말 격자 — 전 전략 공용"})

    # ── 폴백: 상장주식수를 과거로 고정하고 과거 종가를 곱한다 ────────────────────────────
    #   ★ 이건 근사다. 편향 방향을 정확히 알고 써야 한다:
    #     · 그 뒤 유상증자/무상증자를 한 기업 → 과거 시총이 과대 추정된다 → 랭크가 높아진다
    #       → U-MID(251~1400) 밴드에서 위로 밀려나 '빠질' 수 있다.
    #     · 자사주 소각/감자를 한 기업 → 과거 시총이 과소 추정된다 → 아래로 밀린다.
    #   즉 자본 이벤트가 있었던 기업의 유니버스 편입이 체계적으로 틀어진다. 그런데 이 전략의
    #   TP_P1/TP_P2 가 바로 자본배분 신호이므로, 하필 가장 중요한 종목군에서 틀린다.
    #   → 근사를 쓸 수밖에 없더라도 그 사실과 커버리지를 반드시 표로 남긴다.
    px = px_monthly[["code", "month", "close", "adv20"]].copy()
    px["month"] = as_ts_series(px["month"])
    base = px.merge(M, on=["code", "month"], how="left")
    n_true = int(base["mcap"].notna().sum())

    need = base["mcap"].isna()
    if need.any():
        shares_now = pd.Series(dtype="float64")
        if "shares" in M.columns and len(M):
            # 우리가 실제로 관측한 상장주식수 중 '가장 이른' 것을 그 이전 구간에 역투영한다.
            # 가장 최근 것을 쓰면 그동안의 증자를 전부 과거에 소급하게 되어 편향이 커진다.
            first_obs = (M.dropna(subset=["shares"]).sort_values("month")
                          .drop_duplicates("code", keep="first").set_index("code")["shares"])
            shares_now = first_obs
        if shares_now.empty and "shares" in sec.columns:
            shares_now = sec.dropna(subset=["shares"]).set_index("code")["shares"]
        if not shares_now.empty:
            est = base.loc[need, "code"].map(shares_now) * base.loc[need, "close"]
            base.loc[need, "mcap"] = est.to_numpy()
            base.loc[need & base["mcap"].notna(), "mcap_src"] = "shares_backproj"

    n_approx = int((base["mcap_src"].astype(str) == "shares_backproj").sum())
    still = base["mcap"].isna()
    n_proxy = int(still.sum())
    if still.any():
        # 최후 폴백: 거래대금 랭크를 규모의 대리로 쓴다. 규모가 아니라 유동성이므로
        # 판정에 반드시 명시한다. (거래대금은 유동성 필터와 상관되어 밴드가 좁아진다)
        base.loc[still, "mcap"] = base.loc[still, "adv20"]
        base.loc[still & base["mcap"].notna(), "mcap_src"] = "adv_proxy"

    tot = max(len(base), 1)
    LOG.table([["① pykrx PIT 시총 (정확)", f"{n_true:,}", f"{100*n_true/tot:.1f}%", "✔ C13 충족"],
               ["③ 상장주식수 역투영 (근사)", f"{n_approx:,}", f"{100*n_approx/tot:.1f}%",
                "⚠ 자본이벤트 미반영 — 증자기업 과대/감자기업 과소"],
               ["④ 거래대금 대리 (최후)", f"{n_proxy:,}", f"{100*n_proxy/tot:.1f}%",
                "❗ 규모가 아니라 유동성 — 밴드 의미가 달라짐"],
               ["시총 미상", f"{int(base['mcap'].isna().sum()):,}",
                f"{100*int(base['mcap'].isna().sum())/tot:.1f}%", "유니버스에서 제외됨"]],
              ["시총 소스", "행수", "비중", "판정"], ["l", "r", "r", "l"],
              title="PIT 시가총액 소스 감사 (계약 C13) — 근사 비중이 크면 유니버스 정의가 흔들립니다")

    if n_true / tot < 0.60:
        LOG.warn(f"정확한 PIT 시총 비중이 {100*n_true/tot:.0f}% 에 그칩니다. "
                 f"KRX 마켓플레이스 ID/PW 를 입력하면 pykrx 경로가 열려 크게 개선됩니다. "
                 f"근사 구간에서는 U-MID 밴드 편입이 자본이벤트 기업에서 체계적으로 틀어집니다 — "
                 f"하필 TP_P1/TP_P2 가 겨냥하는 종목군입니다. 결과 해석 시 반드시 감안하세요.")
        PIPE.note("WARN: PIT 시총 근사 비중 과다 — C13 부분 충족")

    out = base[["code", "month", "mcap", "mcap_src"]].copy()
    out["mcap_src"] = out["mcap_src"].fillna("none").astype(str)
    PIPE.io("OUT", "MEM", "pit_marketcap", out, source="pykrx+approx")
    return downcast(out)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [12/22]  16_ingest_research.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 수집 — 한경컨센서스 + 네이버금융리서치                            ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : 작성자(애널리스트)·적정가격·투자의견을 리스트에서    ║
# ║      바로 준다. 1요청에 최대 수백 행 → 애널리스트 원장의 1순위 소스.                       ║
# ║      단, 종목코드가 컬럼에 없다. 제목의 "종목명(005930)" 에서 뽑아야 한다.                 ║
# ║    · 네이버금융리서치 : 종목코드를 td[0] a.stock_item href 에 확실히 준다.                 ║
# ║      애널리스트명은 리스트에 없다(PDF/상세에 있음). 커버리지 폭이 넓다.                    ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자가 명시적으로 수집을 지시했으므로     ║
# ║    수행하되, 초당 요청을 보수적으로 제한하고(RATE_LIMIT_QPS) 이 사실을 로그에 명시한다.     ║
# ║  ⚠ PDF 원문은 증권사 저작물이다. 로컬 캐시/분석 용도로만 쓰고 재배포하지 말 것.             ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다. (공개 스크래퍼들의 컬럼 인덱스가 서로 모순되기 때문)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
HK_PDF = HK_BASE + "/analysis/downpdf?report_idx={idx}"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = [
    "report_uid", "source", "src_report_id", "pub_date", "category",
    "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
    "analyst_raw", "target_price", "opinion", "pdf_url", "pdf_uid", "detail_url",
    "views", "event_date", "knowledge_date",
]

_OPINION_MAP = {
    "매수": "BUY", "buy": "BUY", "strongbuy": "BUY", "적극매수": "BUY", "outperform": "BUY",
    "비중확대": "BUY", "overweight": "BUY", "trading buy": "BUY", "tradingbuy": "BUY",
    "중립": "HOLD", "hold": "HOLD", "neutral": "HOLD", "marketperform": "HOLD",
    "시장수익률": "HOLD", "보유": "HOLD", "비중유지": "HOLD",
    "매도": "SELL", "sell": "SELL", "underperform": "SELL", "비중축소": "SELL",
    "underweight": "SELL", "reduce": "SELL",
}
_NULL_TOKENS = {"", "-", "--", "0", "n/a", "na", "없음", "투자의견없음", "nr", "not rated", "제시안함"}


def _clean_cell(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABCABC' 처럼 2~3회 반복되어 나오는 알려진 버그를 되돌린다."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0:
            unit = s[: n // k]
            if unit * k == s:
                return unit
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 목표주가 리비전 팩터가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    if v <= 0 or v > 5e7:
        return None
    return v


def parse_opinion(x: Any) -> Optional[str]:
    t = _clean_cell(x)
    if t.lower() in _NULL_TOKENS:
        return None
    k = re.sub(r"[^\w가-힣]", "", t).lower()
    for pat, val in _OPINION_MAP.items():
        if re.sub(r"[^\w가-힣]", "", pat).lower() in k:
            return val
    return t[:20] or None


_YYMMDD = re.compile(r"^\s*(\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*$")


def parse_kr_date(s: Any) -> Optional[str]:
    """★ 네이버 리스트의 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    → 두 자리 연도는 여기서 4자리로 확정한 뒤에만 하위로 넘긴다.
    """
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        # 백테스트 대상은 2000년대. 두 자리 연도는 2000+yy 로 확정한다.
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        try:
            return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
        except Exception:
            return None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6})\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return m.group(1) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


# ── 헤더 기반 테이블 파서 (컬럼 인덱스 불신 원칙) ────────────────────────────────────────────
def _table_headers(table) -> List[str]:
    hdr = []
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            hdr = [_clean_cell(th.get_text()) for th in ths]
            break
    return hdr


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    if headers and len(headers) == len(tds):
        return {headers[i]: tds[i] for i in range(len(tds))}
    return {}


def _pick(rowmap: Dict[str, Any], *names) -> Optional[Any]:
    for n in names:
        for k, v in rowmap.items():
            if n in k:
                return v
    return None


# ── 한경컨센서스 ────────────────────────────────────────────────────────────────────────────
_HK_LAYOUT_LOGGED = set()


def _hk_parse(html: str, category: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = None
    for sel in ("div.table_style01 table", "#contents table", "table"):
        t = soup.select_one(sel)
        if t is not None and t.find("tr") is not None:
            table = t
            break
    if table is None:
        return []
    if soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃 감지: {len(headers)}컬럼 {headers}")
        if headers and not any("적정" in h or "목표" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 적정가격 컬럼이 없습니다. "
                     f"skinType 파라미터가 무시된 것 같습니다(통합 탭 6컬럼 레이아웃). "
                     f"목표주가·투자의견은 이 카테고리에서 수집되지 않습니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        # report_idx 는 어느 열에 있든 앵커에서 찾는다 (인덱스 의존 제거)
        ridx, pdf = None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                pdf = HK_PDF.format(idx=ridx)
                break
        if ridx is None:
            continue

        date_s = _pick(rm, "작성일", "날짜")
        if not date_s:
            date_s = next((t for t in texts if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
        title = _pick(rm, "제목")
        if not title:
            a = tr.find("a", href=re.compile("report_idx"))
            title = _clean_cell(a.get_text(" ")) if a else ""
        title = _dedup_repeat(title)

        tp = _pick(rm, "적정가격", "목표주가", "적정주가")
        op = _pick(rm, "투자의견", "의견")
        an = _pick(rm, "작성자", "애널리스트")
        bk = _pick(rm, "제공출처", "증권사", "출처")

        if headers and len(headers) == len(texts):
            pass                                     # 헤더 매핑 성공 — 그대로 사용
        else:
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c not in (op or "",)]
            if bk is None:
                bk = next((c for c in cand if "증권" in c or "투자" in c or "금융" in c), None)
            if an is None:
                an = next((c for c in cand if c != bk and 1 <= len(c) <= 30), None)

        out.append({
            "source": "hankyung", "src_report_id": str(ridx), "category": category,
            "pub_date": parse_kr_date(date_s), "title": title,
            "stock_code": code_from_title(title), "stock_name": name_from_title(title),
            "broker_raw": _clean_cell(bk), "analyst_raw": _clean_cell(an),
            "target_price": parse_target_price(tp), "opinion": parse_opinion(op),
            "pdf_url": pdf, "detail_url": pdf, "views": None,
        })
    return out


def hankyung_collect(start: str, end: str, skins: Sequence[str] = ("business",),
                     page_size: int = 80, max_pages: int = 400) -> pd.DataFrame:
    """연도 단위로 쪼개서 수집. 한 번에 10년을 요청하면 서버 페이지 상한에 걸린다."""
    rows: List[dict] = []
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    jobs = []
    for skin in skins:
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            jobs.append((skin, sd, ed))

    def _sweep(job):
        skin, sd, ed = job
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            params = {
                "skinType": skin, "sdate": sd.strftime("%Y-%m-%d"), "edate": ed.strftime("%Y-%m-%d"),
                "now_page": page, "pagenum": page_size, "order_type": "",
                "report_type": "CO" if skin == "business" else "",
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            if not html:
                break
            batch = _hk_parse(html, skin)
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            for b in fresh:
                seen_ids.add(b["src_report_id"])
            got.extend(fresh)
            # ★ 조기 종료 조건을 느슨하게 잡으면 데이터가 조용히 잘려나간다.
            #   파싱 실패나 일시적 짧은 페이지 하나로 그 해 전체 수집이 끊길 수 있으므로,
            #   '새 항목 0건'이 2회 연속일 때만 멈춘다.
            if len(fresh) == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
            if page == max_pages:
                LOG.warn(f"한경 {skin} {sd:%Y} 구간이 최대 페이지({max_pages})에 도달했습니다 — "
                         f"데이터가 잘렸을 수 있습니다. max_pages 를 늘리거나 구간을 분기 단위로 "
                         f"쪼개세요. (지금까지 {len(got):,}건)")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스")
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows, columns=[c for c in REPORT_COLS if c in (rows[0].keys() if rows else [])]) \
        if rows else pd.DataFrame(columns=REPORT_COLS)
    if rows:
        d = pd.DataFrame(rows)
    LOG.ok(f"한경컨센서스 {len(d):,}건 "
           f"(작성자 보유 {int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} / "
           f"목표주가 보유 {int(d['target_price'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
NV_CATS = {
    "company": ("company_list.naver", "company_read.naver"),
    "industry": ("industry_list.naver", "industry_read.naver"),
    "market": ("market_info_list.naver", "market_info_read.naver"),
    "invest": ("invest_list.naver", "invest_read.naver"),
    "economy": ("economy_list.naver", "economy_read.naver"),
    "debenture": ("debenture_list.naver", "debenture_read.naver"),
}
_NV_PDF_RE = re.compile(r"/stock-research/(\w+)/(\d+)/(\d{8})_(\w+)_(\d+)\.pdf")


def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = soup.select_one("#contentarea_left div.box_type_m table.type_1") or \
        soup.select_one("table.type_1") or soup.select_one("table")
    if table is None:
        return []
    headers = _table_headers(table)
    _, read_page = NV_CATS.get(cat, ("", "company_read.naver"))
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid, detail, title = None, None, None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid = m.group(1)
                detail = urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=(\d{6})", a_item["href"])
            code = mm.group(1) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        pdf = None
        for a in tr.find_all("a", href=True):
            if a["href"].lower().endswith(".pdf"):
                pdf = a["href"] if a["href"].startswith("http") else urljoin(NV_BASE, a["href"])
                break

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)
        vw = _pick(rm, "조회")

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None,
            "pdf_url": pdf, "detail_url": detail,
            "views": _clean_cell(vw).replace(",", "") or None,
        })
    return out


def _nv_last_page(html: str) -> int:
    soup = soup_of(html)
    if soup is None:
        return 1
    mx = 1
    for a in soup.select("table.Nnavi a[href]"):
        m = re.search(r"page=(\d+)", a["href"])
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def naver_collect_json(cat: str, start: str, end: str, page_size: int = 100,
                       hard_cap: int = 60000) -> pd.DataFrame:
    """신형 JSON API. 되면 HTML 페이징보다 훨씬 빠르고 구조가 안정적이다."""
    rows, index = [], 0
    url = NV_API.format(cat=cat)
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    while index < hard_cap:
        js = http_json(url, source="naver", tries=2, headers=hdr,
                       params={"index": index, "size": page_size,
                               "startDate": as_ts(start).strftime("%Y-%m-%d"),
                               "endDate": as_ts(end).strftime("%Y-%m-%d")})
        if not js:
            break
        items = js if isinstance(js, list) else (js.get("researches") or js.get("list") or
                                                 js.get("items") or js.get("content") or [])
        if not isinstance(items, list) or not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({
                "source": "naver", "category": cat,
                "src_report_id": str(it.get("id") or it.get("nid") or it.get("researchId") or ""),
                # ★ JSON 경로도 반드시 parse_kr_date 를 통과시킨다. HTML 파서에는 있는 가드가
                #   여기만 빠져 있었다. 네이버가 'YY.MM.DD' 를 주면 pandas 자동추론이
                #   '26.01.19' 를 2019-01-26 으로 읽어(연·일 뒤바뀜) 예외 없이 통과하고,
                #   리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
                #   (실측: 원장 병합 단계에서 절반이 '범위 밖'으로 조용히 탈락)
                "pub_date": parse_kr_date(it.get("createDate") or it.get("date")
                                          or it.get("writeDate")),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                "detail_url": None, "views": it.get("readCount"),
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    if len(d):
        d = d[d["src_report_id"].astype(str).str.len() > 0]
    return d


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1500) -> pd.DataFrame:
    frames = []
    for cat in cats:
        # ① JSON API 우선
        try:
            dj = naver_collect_json(cat, start, end)
        except Exception:
            dj = pd.DataFrame()
        if len(dj) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(dj):,}건")
            frames.append(dj)
            continue
        # ② HTML 리스트 폴백
        list_page, _ = NV_CATS[cat]
        base = urljoin(NV_BASE, list_page)
        probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                         params={"searchType": "writeDate",
                                 "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                                 "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": 1})
        if not probe:
            LOG.warn(f"네이버 '{cat}' 리스트 접근 실패 — 건너뜁니다.")
            continue
        last = min(_nv_last_page(probe), max_pages)
        LOG.info(f"네이버 '{cat}' HTML 폴백 — 총 {last:,}페이지")

        def _pg(p: int):
            h = probe if p == 1 else http_get(
                base, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=3,
                params={"searchType": "writeDate",
                        "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                        "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": p})
            return _nv_parse_list(h, cat) if h else []

        res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO),
                      desc=f"네이버 {cat}")
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다."""
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    if len(need) > limit:
        LOG.warn(f"네이버 상세 보강 대상 {len(need):,}건 중 최신 {limit:,}건만 조회합니다 "
                 f"(RESEARCH 설정으로 조절 가능). 나머지는 목표주가 결측으로 남습니다.")
        need = need.sort_values("pub_date", ascending=False).head(limit)

    def _one(u: str):
        h = http_get(u, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=2)
        if not h:
            return None
        s = soup_of(h)
        if s is None:
            return None
        box = s.select_one("div.view_info_1") or s
        tp = box.select_one("em.money strong") or box.select_one("em.money")
        op = box.select_one("em.coment")
        an = ""
        src = s.select_one("th.view_sbj p.source")
        if src is not None:
            an = _clean_cell(src.get_text(" "))
        return {"detail_url": u,
                "target_price": parse_target_price(tp.get_text() if tp else None),
                "opinion": parse_opinion(op.get_text() if op else None),
                "_detail_src": an}

    res = pmap_io(_one, need["detail_url"].tolist(), workers=min(8, N_WORKERS_IO),
                  desc="네이버 상세(목표주가)")
    got = pd.DataFrame([r for r in res if r])
    if got.empty:
        return df
    # ★ detail_url 이 유일하지 않으면 merge 가 행을 증식시킨다(리포트가 복제됨).
    #   원장 건수가 조용히 불어나 커버리지·리비전 통계가 전부 틀어진다.
    got = got.drop_duplicates("detail_url", keep="last")
    n_before = len(df)
    df = df.merge(got, on="detail_url", how="left", suffixes=("", "_d"))
    if len(df) != n_before:
        LOG.warn(f"상세 보강 머지에서 행수가 {n_before:,}→{len(df):,} 로 변했습니다 — "
                 f"중복 detail_url 로 인한 증식입니다.")
        df = df.drop_duplicates("report_uid", keep="first")
    for c in ("target_price", "opinion"):
        if f"{c}_d" in df.columns:
            df[c] = df[c].where(df[c].notna(), df[f"{c}_d"])
            df = df.drop(columns=[f"{c}_d"])
    LOG.ok(f"네이버 상세 보강 — 목표주가 {int(got['target_price'].notna().sum()):,}건 추가 확보")
    return df


# ── PDF 원문 ────────────────────────────────────────────────────────────────────────────────
_ANALYST_LINE = re.compile(
    r"([가-힣]{2,4})\s*(?:연구원|애널리스트|수석|책임|선임)?\s*"
    r"(?:\(?\s*(?:02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}\s*\)?)?\s*"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TP_PAT = re.compile(r"(?:목표\s*주가|목표주가|적정\s*주가|적정주가|TP)\s*[:：(]?\s*"
                     r"(?:원\)?\s*)?([0-9][0-9,]{2,9})")


def pdf_text(data: bytes, max_pages: int = 3) -> str:
    """1페이지 헤더/푸터에 애널리스트명·이메일·목표주가가 몰려 있다. 앞 3장이면 충분하다."""
    if not data or data[:5] != b"%PDF-":
        return ""
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count)))
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
        except Exception:
            pass
    return ""


def pdf_extract_fields(text: str) -> dict:
    out = {"pdf_analysts": "", "pdf_emails": "", "pdf_target": None}
    if not text:
        return out
    pairs = _ANALYST_LINE.findall(text[:6000])
    names = [p[0] for p in pairs]
    mails = [p[1] for p in pairs] or _EMAIL.findall(text[:6000])
    if not names:
        # 이메일 로컬파트에서 역추적 실패 시, '연구원/애널리스트' 앞 한글 이름만이라도
        names = re.findall(r"([가-힣]{2,4})\s*(?:연구원|애널리스트)", text[:6000])
    out["pdf_analysts"] = ",".join(dict.fromkeys(names))[:120]
    out["pdf_emails"] = ",".join(dict.fromkeys(mails))[:200]
    m = _TP_PAT.search(text[:8000])
    if m:
        out["pdf_target"] = parse_target_price(m.group(1))
    return out


def download_pdfs(df: pd.DataFrame, cap_per_month: int = 0) -> pd.DataFrame:
    """PDF 를 공용 인덱스에 저장(내용해시 경로 → 중복 저장 없음)하고 본문 필드를 추출한다."""
    if df.empty or not RESEARCH_DOWNLOAD_PDF:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None if c != "pdf_uid" else ""
        return df
    if fitz is None and pdfplumber is None:
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 원문 추출을 건너뜁니다. "
                 "한경 리스트의 작성자/목표주가만으로도 애널리스트 연결은 동작합니다.")
    work = df[df["pdf_url"].notna()].copy()
    if cap_per_month and len(work):
        work["_m"] = as_ts_series(work["pub_date"]).dt.to_period("M")
        work = work.groupby("_m", observed=True).head(cap_per_month).drop(columns=["_m"])
    if work.empty:
        return df

    idx = VAULT.load_index("shared")
    known = {}
    if len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        # iterrows 는 30만 행에서 13초를 쓴다. zip 은 같은 결과를 0.2초에 만든다.
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
    LOG.info(f"PDF 대상 {len(work):,}건 (드라이브 캐시 보유 {sum(1 for k in work['report_uid'] if k in known):,}건)")

    def _one(rec):
        uid, url = rec
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
            if data:
                return (uid, known[uid], data)
            # 인덱스에는 있는데 실제 파일이 없으면(드라이브 동기화 누락 등) 재수집으로 폴백한다.
            # 여기서 포기하면 그 보고서는 영구히 비어 있는 채로 남는다.
        raw = http_get(url, source="hankyung" if "hankyung" in str(url) else "naver",
                       as_bytes=True, tries=2, referer=HK_BASE + "/" if "hankyung" in str(url) else NV_BASE)
        if not raw or raw[:5] != b"%PDF-":
            return (uid, "", b"")          # 로그인/에러 HTML 이 200 으로 오는 케이스 방어
        return (uid, "", raw)

    jobs = list(zip(work["report_uid"].astype(str), work["pdf_url"].astype(str)))

    # ★ 청크로 끊어 받는다. pmap_io 는 결과 리스트를 통째로 들고 있으므로, 한 번에 던지면
    #   내려받은 PDF 본문 전부가 동시에 RAM 에 남는다. 목표치인 연 3만건 × 10년 = 30만건에
    #   평균 300KB 를 곱하면 90GB 다. 캐시가 차 있어도 마찬가지다 — 캐시 경로도 blob 바이트를
    #   그대로 반환하기 때문에 오히려 더 빨리 쌓인다. 청크 단위로 소비하고 버리면 상주량이
    #   작업 수와 무관하게 평평해진다(약 600MB). 청크마다 flush 하므로 중간에 끊겨도 이어받는다.
    PDF_CHUNK = 2000
    rows = []
    ok = 0
    for k0 in range(0, len(jobs), PDF_CHUNK):
        chunk = jobs[k0:k0 + PDF_CHUNK]
        res = pmap_io(_one, chunk, workers=min(N_WORKERS_IO, 10),
                      desc=f"리포트 PDF {k0//PDF_CHUNK + 1}/{(len(jobs)-1)//PDF_CHUNK + 1}")
        for r in res:
            if not r:
                continue
            uid, existing_blob_uid, data = r
            if not data:
                continue
            ok += 1
            blob_uid = existing_blob_uid
            if not blob_uid:
                p = VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                                   source="report_pdf", scope="shared")
                blob_uid = sha1_str("research", "report_pdf", uid, sha1_bytes(data)) if p else ""
            f = pdf_extract_fields(pdf_text(data))
            rows.append({"report_uid": uid, "pdf_uid": blob_uid, **f})
        del res
        VAULT.flush("shared")
    VAULT.flush("shared")
    LOG.ok(f"PDF 확보 {ok:,}/{len(jobs):,}건 — 공용 인덱스에 저장(내용해시 중복제거 적용)")
    if not rows:
        for c in ("pdf_uid", "pdf_analysts", "pdf_emails", "pdf_target"):
            if c not in df.columns:
                df[c] = None
        return df
    ext = pd.DataFrame(rows)
    df = df.merge(ext, on="report_uid", how="left")
    PIPE.io("OUT", "DRIVE", "research:pdf", ext, source="hankyung/naver pdf")
    return df


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [13/22]  17_entity_research.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  엔티티 해상 — 증권사 정규화 / 애널리스트 원장 / 보고서↔애널리스트 연결              ║
# ║                                                                                          ║
# ║  이 모듈이 답해야 하는 질문 (사용자 요구사항):                                              ║
# ║    Q1. 보고서와 애널리스트가 제대로 연결되었는가?   → report_analyst_link + 연결 감사표     ║
# ║    Q2. 다중소스 원장 연결은 확실한가?               → dedup_key 병합 + 소스기여 감사표      ║
# ║    Q3. 목표주가는 누가 언제 제시했는가?             → (analyst_id, code, date, tp) 원장     ║
# ║                                                                                          ║
# ║  증권사 사명 변경(2016~2026)을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로          ║
# ║  다른 사람이 되어버린다 → 목표주가 리비전(d2)이 통째로 망가진다.                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 정규화 표: (별칭 정규식 → 정식명). 사명 변경 이력이 핵심이다.
BROKER_CANON: List[Tuple[str, str]] = [
    (r"미래에셋(대우|증권|생명)?", "미래에셋증권"),          # 미래에셋대우→미래에셋증권(2021)
    (r"(대우증권|KDB대우)", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),        # 우리투자→NH투자(2014)
    (r"한국투자|한국證|한투증권", "한국투자증권"),
    (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),                # KB투자+현대증권→KB증권(2017)
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),        # 신한금융투자→신한투자증권(2022)
    (r"하나(증권|금융투자|금투)", "하나증권"),                # 하나금융투자→하나증권(2022)
    (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"),
    (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"),                       # 동양→유안타(2014)
    (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"),
    (r"IBK(투자증권|증권)|기업은행", "IBK투자증권"),
    (r"신영증권", "신영증권"),
    (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),      # HMC투자→현대차증권(2016)
    (r"SK증권", "SK증권"),
    (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권", "iM증권"),               # 하이투자→iM증권(2024)
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),           # 이베스트→LS증권(2024)
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),      # KTB→다올(2022)
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),             # 동부→DB금융투자(2018)
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"),
    (r"부국증권", "부국증권"),
    (r"한양증권", "한양증권"),
    (r"상상인증권|골든브릿지", "상상인증권"),
    (r"케이프(투자증권|증권)", "케이프투자증권"),
    (r"토스증권", "토스증권"),
    (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"),
    (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"),
    (r"DS투자증권", "DS투자증권"),
    (r"현대해상|한화생명|미래에셋생명", "기타"),
    (r"NICE|나이스", "NICE디앤비"),
    (r"에프앤가이드|FnGuide", "에프앤가이드"),
    (r"(하이證|하이증권)", "iM증권"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]

# 대형 10개사 / 중소형 10개사 — 커버리지 목표 달성 여부 감사에 쓴다
MAJOR_BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "키움증권", "메리츠증권", "대신증권"]
MINOR_BROKERS = ["유안타증권", "한화투자증권", "교보증권", "IBK투자증권", "신영증권",
                 "현대차증권", "SK증권", "유진투자증권", "iM증권", "LS증권",
                 "다올투자증권", "DB금융투자", "BNK투자증권", "흥국증권", "부국증권",
                 "한양증권", "상상인증권", "케이프투자증권", "DS투자증권", "코리아에셋투자증권"]


def normalize_broker(raw: Any) -> Tuple[str, str]:
    """(broker_id, 정식명). 못 알아보면 정규화 문자열 자체를 id 로 쓰되 '미상' 표시는 하지 않는다
    (미상으로 뭉치면 서로 다른 소형사가 한 덩어리가 되어 커버리지 통계가 거짓이 된다)."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return (sha1_str("broker", canon)[:12], canon)
    canon = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    return (sha1_str("broker", canon)[:12], canon)


_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동/김철수' / '홍길동 외 1인' → ['홍길동','김철수']"""
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사)", " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


def _name_to_code_map(sec: pd.DataFrame) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for _, r in sec.iterrows():
        n = norm_corp_name(r.get("name"))
        c = r.get("code")
        if n and isinstance(c, str) and n not in m:
            m[n] = c
    return m


def _atoms(vals, sep: str) -> List[str]:
    """합성 토큰을 원자로 되돌린 뒤 정렬·중복제거. 병합을 멱등하게 만드는 핵심 함수."""
    out = set()
    for v in vals:
        s = str(v)
        if not s or s.lower() in ("nan", "none", "<na>"):
            continue
        for tok in s.split(sep):
            tok = tok.strip()
            if tok and tok.lower() not in ("nan", "none", "<na>"):
                out.add(tok)
    return sorted(out)


def _pick_str(vals) -> str:
    """비어있지 않은 값 중 사전순 최소. '행 순서상 첫 값'과 달리 실행 간 재현된다."""
    c = sorted({str(v).strip() for v in vals
                if v is not None and str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "<na>")})
    return c[0] if c else ""


def build_report_master(frames: Sequence[pd.DataFrame], sec: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 → 보고서 원장. 중복 제거가 아니라 '병합'이다(정보를 버리지 않는다)."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.warn("수집된 리포트가 없습니다. 드라이브 캐시도 비어 있다면 D축 d2/d4 는 결측 처리됩니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat([f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                   for f in frames], ignore_index=True)

    # 두 자리 연도는 수집부 parse_kr_date 에서 이미 4자리로 확정된다.
    # 여기서는 남은 이상치만 걸러낸다(교정하지 않는다 — 잘못된 교정이 더 위험하다).
    n_raw0 = len(d)
    # ★ 마지막 방어선: 수집부에서 정규화를 놓친 소스가 있어도 여기서 두 자리 연도를 살린다.
    #   as_ts_series 로 바로 넘기면 pandas 자동추론이 '16.01.15' 를 2015-01-16 으로 읽고,
    #   그 값은 범위 밖도 아니라서 경고 없이 통과한다 — 시간축이 통째로 어긋난 채로.
    d["pub_date"] = d["pub_date"].map(parse_kr_date)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("1999-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일이 없거나 범위를 벗어난 리포트 {int(bad.sum()):,}건을 제외했습니다 "
                 f"({100*bad.mean():.2f}%). 이 비율이 크면 소스의 날짜 형식이 바뀐 것입니다 — "
                 f"조용히 넘기지 말고 parse_kr_date 를 확인하세요.")
    d = d[~bad]
    if len(d) == 0:
        LOG.error("발간일이 유효한 리포트가 하나도 없습니다. 날짜 파싱이 깨졌습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    bid = d["broker_raw"].map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]

    # 종목코드: ① 소스 제공 ② 제목 정규식 ③ 종목명→코드 사전
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = d.loc[need, "title"].map(code_from_title)
    need = d["stock_code"].isna() & d["stock_name"].astype(str).str.len().gt(0)
    if need.any() and len(sec):
        n2c = _name_to_code_map(sec)
        d.loc[need, "stock_code"] = d.loc[need, "stock_name"].map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = d["title"].map(_dedup_repeat)
    # report_uid 는 '한 번 붙으면 안 바뀌는' 식별자여야 한다. 이미 붙어 있으면 보존한다.
    # (드라이브 캐시의 병합 결과가 다시 입력으로 들어올 때 source 가 "hankyung+naver" 같은
    #  합성 토큰이라, 무조건 재계산하면 실행마다 uid 가 달라져 PDF 캐시가 통째로 무효화된다)
    _uid_new = [sha1_str(s, i) for s, i in zip(d["source"].astype(str),
                                               d["src_report_id"].astype(str))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    # 소스 간 동일 보고서 판정 키
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b,
                               c or "", norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             d["stock_code"].fillna(""), d["title"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"])

    # ── 멱등 병합 (재실행 안전) ─────────────────────────────────────────────────────────
    #   이 함수의 출력(원장)은 다음 실행에서 드라이브 캐시로부터 '입력 프레임'으로 되돌아온다.
    #   그때 source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로, 단순 set 병합은
    #   "hankyung+naver" 를 원자 하나로 취급해 실행할 때마다 문자열이 무한히 길어진다
    #   (hankyung+naver → hankyung+hankyung+naver+naver → …). 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌어
    #   PDF 캐시·애널리스트 연결표가 통째로 끊긴다. 순서에 무관한 min 으로 고정한다.
    #   (min 은 병합행이 다시 들어와도 같은 값을 낸다: min{u1,u2,min(u1,u2)} = min(u1,u2))
    m = d.groupby("dedup_key", as_index=False).agg(**{
        "report_uid": ("report_uid", "min"),
        "src_report_id": ("src_report_id", lambda s: "|".join(_atoms(s, "|"))),
        "source": ("source", lambda s: "+".join(_atoms(s, "+"))),
        "category": ("category", _pick_str),
        "pub_date": ("pub_date", "min"),
        "title": ("title", lambda s: max(sorted(set(map(str, s))), key=len)),
        "stock_code": ("stock_code", lambda s: _pick_str(s) or None),
        "stock_name": ("stock_name", _pick_str),
        "broker_id": ("broker_id", "min"),          # dedup_key 구성요소라 그룹 내 동일
        "broker_name": ("broker_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),      # 네이티브 max = NaN 무시. 파이썬 람다는 30만건에서 50초.
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "pdf_url": ("pdf_url", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"보고서 원장 병합: 수집 {n_raw0:,}건 → 날짜유효 {n_raw:,}건 → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0 - n_raw:,} · 소스 간 중복 병합 {n_raw - len(m):,})")

    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개 (C1)
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver")
    return m


def build_analyst_ledger(rep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """애널리스트 마스터 + 보고서↔애널리스트 연결표. 연결 방법과 신뢰도를 반드시 기록한다."""
    if rep.empty:
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))
    links = []
    for r in rep.itertuples(index=False):
        names, method, conf = [], "unresolved", 0.0
        raw = getattr(r, "analyst_raw", "") or ""
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98        # 한경 '작성자' 컬럼 — 가장 신뢰도 높음
        if not names:
            praw = getattr(r, "pdf_analysts", "") or ""
            if str(praw).strip():
                names = [n for n in str(praw).split(",") if n.strip()]
                method, conf = "pdf_header", 0.80
        if not names:
            continue
        for i, nm in enumerate(names):
            links.append({
                "report_uid": r.report_uid, "name": nm, "broker_id": r.broker_id,
                "broker_name": r.broker_name, "role": "lead" if i == 0 else "co",
                "link_method": method, "link_conf": conf,
                "pub_date": r.pub_date, "stock_code": r.stock_code,
                "target_price": r.target_price, "opinion": r.opinion,
            })
    if not links:
        LOG.warn("애널리스트를 한 건도 식별하지 못했습니다. 한경컨센서스 수집이 실패했거나 "
                 "skinType=business 응답이 6컬럼 레이아웃으로 왔을 가능성이 큽니다.")
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"]))

    L = pd.DataFrame(links)
    L["name_norm"] = L["name"].map(lambda s: re.sub(r"\s+", "", str(s)))
    # 애널리스트 동일성: (증권사, 이름). 동명이인은 소속으로 구분된다.
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14] for b, n in zip(L["broker_id"], L["name_norm"])]

    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name_norm", "first"), broker_id=("broker_id", "first"),
               broker_name=("broker_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("stock_code", lambda s: s.dropna().nunique()),
               n_targets=("target_price", lambda s: int(s.notna().sum()))))
    # 동명이인/이직 감지 — 같은 이름이 여러 증권사에 존재
    dup = A.groupby("name")["analyst_id"].transform("size")
    A["name_ambiguous"] = dup > 1
    LOG.ok(f"애널리스트 원장 {len(A):,}명 · 연결 {len(L):,}건 "
           f"(동명/이직 후보 {int(A['name_ambiguous'].sum()):,}명)")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


def audit_linkage(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame):
    """★ 사용자 요구: '보고서와 식별된 애널리스트가 제대로 연결되었는지 한눈에'."""
    LOG.banner("원장 무결성 감사 — 보고서 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출한다. 숫자가 낮으면 그대로 보고한다.")
    if rep.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()
    r["has_tp"] = r["target_price"].notna()

    rows = []
    for y, g in r.groupby("year"):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g['has_tp'].sum()):,}", f"{100*g['has_tp'].mean():.1f}%",
                     "✔" if n >= RESEARCH_TARGET_PER_YEAR else f"목표 {RESEARCH_TARGET_PER_YEAR:,} 미달"])
    LOG.table(rows, ["연도", "보고서", "애널연결", "연결률", "종목코드", "코드율",
                     "목표주가", "TP율", "연 3만건 목표"],
              ["c", "r", "r", "r", "r", "r", "r", "r", "l"])

    src = r.groupby("source").agg(n=("report_uid", "size"),
                                  analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean"),
                                  tp=("has_tp", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%",
                f"{100*s['code']:.1f}%", f"{100*s['tp']:.1f}%"] for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "종목코드율", "목표주가율"],
              ["l", "r", "r", "r", "r"],
              title="다중소스 원장 연결 — 어느 소스가 무엇을 채웠는가 "
                    "('hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건")

    if len(L):
        mth = L.groupby("link_method").agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "보고서 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 "
                        "(list_field=한경 작성자컬럼 0.98 · pdf_header=PDF추출 0.80)")

    if len(A):
        bro = (A.groupby("broker_name")
                .agg(analysts=("analyst_id", "nunique"), reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        mnr = [b for b in bro.index if b not in MAJOR_BROKERS]
        LOG.table([[b, f"{int(bro.loc[b,'analysts']):,}", f"{int(bro.loc[b,'reports']):,}"]
                   for b in bro.index[:30]],
                  ["증권사", "애널리스트 수", "보고서 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 그 외 증권사 {len(mnr)}개 "
                 f"→ 요구조건(대형 10+ / 중소형 10+): "
                 f"{'✔ 충족' if len(maj) >= 10 and len(mnr) >= 10 else '❗ 미충족 — 수집 범위를 넓히세요'}")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source").size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없어 PDF 추출에 의존합니다 "
                 f"(RESEARCH_DOWNLOAD_PDF=True 로 개선 가능).")


def build_consensus_panel(L: pd.DataFrame, months: pd.DatetimeIndex,
                          window_days: int = 90) -> pd.DataFrame:
    """D축 d2(목표주가 상향 리비전) · d4(커버리지 변화) 산출.

    ★ 리비전은 '같은 애널리스트가 같은 종목에 대해 이전에 제시한 목표주가' 와 비교해야 한다.
      애널리스트 식별이 없으면 이 지표는 만들 수 없다 — 애널리스트 원장이 필요한 진짜 이유.
    """
    cols = ["code", "month", "n_analyst", "tp_median", "rev_up", "rev_dn", "d2_raw", "d4_raw"]
    if L is None or L.empty:
        LOG.warn("애널리스트 연결이 없어 컨센서스 패널을 만들 수 없습니다 — d2/d4 결측 처리. "
                 "U 는 가용 축(d1, d3) 평균으로 계산됩니다(0으로 채우지 않음).")
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["stock_code"]).copy()
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    if x.empty:
        return pd.DataFrame(columns=cols)

    x = x.sort_values(["stock_code", "analyst_id", "pub_date"])
    x["prev_tp"] = x.groupby(["stock_code", "analyst_id"], observed=True)["target_price"].shift(1)
    x["rev"] = np.where(x["target_price"].notna() & x["prev_tp"].notna(),
                        np.sign(x["target_price"] - x["prev_tp"]), np.nan)

    # ★ 월 루프 + 전체 프레임 필터링(120 × 30만행)을 이벤트→월 전개 + groupby 1회로 바꾼다.
    #   리포트가 목표치(30만건)에 도달하면 예전 경로는 수 분을 먹었다. 결과는 동일하다:
    #   창 조건 (m-window, m] 을 인덱스 산술로 그대로 옮긴 것이기 때문이다.
    x["rev_up1"] = (x["rev"] > 0).astype("float32")
    x["rev_dn1"] = (x["rev"] < 0).astype("float32")
    W = expand_events_to_months(x, "pub_date", months, window_days)
    if not nonempty(W):
        return pd.DataFrame(columns=cols)
    g = W.groupby(["stock_code", "month"], observed=True)
    P = g.agg(n_analyst=("analyst_id", "nunique"),
              tp_median=("target_price", "median"),
              rev_up=("rev_up1", "sum"),
              rev_dn=("rev_dn1", "sum")).reset_index().rename(columns={"stock_code": "code"})
    P = P.sort_values(["code", "month"])
    # d2 = -(상향 리비전 수 / 커버리지)   d4 = -Δ(커버리지 애널리스트 수)
    P["d2_raw"] = -(P["rev_up"] / P["n_analyst"].replace(0, np.nan))
    P["d4_raw"] = -P.groupby("code", observed=True)["n_analyst"].diff()
    LOG.ok(f"컨센서스 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) — "
           f"목표주가 리비전 관측 {int((P['rev_up']+P['rev_dn']).sum()):,}건")
    PIPE.io("OUT", "MEM", "consensus_panel", P)
    return downcast(P)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [14/22]  20_pit_v3.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-H  PIT 패널 조립 · U-MID 유니버스(C13) · 셀                                            ║
# ║                                                                                          ║
# ║  §4.2  C1 은 '접근 방식'이 아니라 '출력'에서 검증한다.                                     ║
# ║        pit.get() 루프(1,150만 호출 = 3.2시간) 대신 merge_asof 단일 패스(10초).             ║
# ║        그리고 전 행에 대해 knowledge_date <= asof 를 assert 한다 —                        ║
# ║        전수 검사이므로 게이트웨이 방식보다 오히려 더 강하다.                                ║
# ║                                                                                          ║
# ║  §5    C13 유니버스는 Point-In-Time.                                                      ║
# ║        (a) 시총·유동성 랭크는 매 시점 t 의 당시 값으로 재산출                               ║
# ║        (b) 졸업(graduate out)은 성공 신호다                                                ║
# ║        (c) 보유 중 밴드 이탈은 청산 사유가 아니다                                          ║
# ║        (d) 밴드는 **진입 필터 전용**이다                                                   ║
# ║        → 그래서 패널은 밴드 밖 종목도 계속 들고 간다. u_mid 는 컬럼(플래그)이지             ║
# ║          행 필터가 아니다. 행을 지우면 (c) 를 코드로 만족시킬 방법이 없어진다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_pit_panel(grid: pd.DataFrame, sources: Dict[str, pd.DataFrame],
                    by: str = "code", left_time: str = "month") -> pd.DataFrame:
    """§4.2 — merge_asof 단일 패스. grid: (month, code) 격자.

    각 source 는 knowledge_date 컬럼을 보유해야 한다(pit_frame 통과분).
    direction='backward' 는 knowledge_date <= month 인 마지막 행만 붙이므로 C1 과 동의어다.
    """
    out = grid.copy()
    out["_ord"] = np.arange(len(out))
    # ★ pandas 2.x 는 소스에 따라 datetime64[s]/[us]/[ns] 를 섞어 만든다. merge_asof 는
    #   해상도가 다르면 MergeError 로 죽고(운 좋은 경우), 우리 코드는 그걸 잡아
    #   "결합 건너뜀"으로 넘어가 **그 소스 전체가 조용히 사라진다**(운 나쁜 경우).
    #   양쪽을 [ns] 로 못박아 두 시나리오를 모두 없앤다.
    out[left_time] = as_ts_series(out[left_time]).astype("datetime64[ns]")
    for name, src in sources.items():
        if src is None or len(src) == 0:
            LOG.debug(f"PIT 결합 건너뜀(빈 소스): {name}")
            continue
        if "knowledge_date" not in src.columns or by not in src.columns:
            LOG.warn(f"PIT 결합 건너뜀: '{name}' 에 knowledge_date 또는 '{by}' 가 없습니다.")
            continue
        R = src.copy()
        R["knowledge_date"] = as_ts_series(R["knowledge_date"]).astype("datetime64[ns]")
        R = R.dropna(subset=["knowledge_date", by])
        # ★ by 키 dtype 이 다르면(category vs object) merge_asof 가 조용히 0건 매칭하거나 터진다.
        R[by] = R[by].astype(str)
        drop = [c for c in ("event_date", "_src", "_ord") if c in R.columns]
        R = R.drop(columns=drop).sort_values("knowledge_date", kind="stable")
        R = R.rename(columns={c: c for c in R.columns})
        R[f"knowledge_date_{name}"] = R["knowledge_date"]

        L = out.copy()
        L[by] = L[by].astype(str)
        # ★★ 결합키·시각이 결측인 행을 '떨어뜨리면' 안 된다. 그게 곧 생존자편향 재유입이다.
        mask = L[left_time].notna() & L[by].notna()
        Lm = L[mask].sort_values(left_time, kind="stable")
        if Lm.empty:
            continue
        try:
            M = pd.merge_asof(Lm, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", f"__{name}"))
        except Exception as e:                                   # noqa
            # 조용히 넘어가면 그 소스의 컬럼이 통째로 없어지고, 하류는 그걸 '결측 데이터'로
            # 보고해 운영자를 API 키 쪽으로 오도한다. 원장에 ERR 로 남기고 크게 경고한다.
            LOG.error(f"merge_asof 실패({type(e).__name__}: {e}) — '{name}' 소스가 패널에 "
                      f"결합되지 않았습니다. 이 소스를 쓰는 센서는 전부 결측이 됩니다. "
                      f"대개 by 키 dtype 불일치이거나 시간 컬럼 해상도(datetime64[s] vs [ns]) "
                      f"불일치입니다.")
            PIPE.io("IN", "MEM", f"asof:{name}", None, ok=False, note=f"{type(e).__name__}")
            continue
        new_cols = [c for c in M.columns if c not in out.columns]
        if not new_cols:
            continue
        out = (out.set_index("_ord")
                  .join(M.set_index("_ord")[new_cols], how="left")
                  .reset_index())
        PIPE.io("IN", "MEM", f"asof:{name}", M, source=f"merge_asof backward on {left_time}")
    return out.drop(columns=["_ord"])


def assert_c1(panel: pd.DataFrame, strict: bool = True) -> List[str]:
    """§4.2 — C1 계약을 출력에서 전수 검증한다. 위반이 1행이라도 있으면 미래누수다."""
    bad = []
    asof = as_ts_series(panel["month"])
    for c in [c for c in panel.columns if c.startswith("knowledge_date_")]:
        kd = as_ts_series(panel[c])
        v = kd.notna() & (kd > asof)
        if v.any():
            bad.append(f"{c}: {int(v.sum()):,}행 (최대 +{int((kd[v]-asof[v]).dt.days.max())}일)")
    if bad:
        msg = ("[C1 위반] 아래 소스에서 knowledge_date > asof 인 행이 발견되었습니다 — "
               "이것은 미래누수입니다:\n  " + "\n  ".join(bad))
        if strict:
            raise KillCriteria(msg)
        LOG.error(msg)
    else:
        n = len([c for c in panel.columns if c.startswith("knowledge_date_")])
        LOG.ok(f"C1 전수 검증 통과 — {len(panel):,}행 × {n}개 소스 전부 "
               f"knowledge_date <= asof (merge_asof 단일 패스, 예외 경로 없음)")
    return bad


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §5  U-MID 유니버스 (C13)
# ═══════════════════════════════════════════════════════════════════════════════════════════
class UniverseV3:
    """PIT 유니버스. 밴드는 진입 필터일 뿐이므로 패널 행을 지우지 않는다."""

    def __init__(self, panel: pd.DataFrame, sec: pd.DataFrame, mode: str = UNIVERSE_MODE):
        self.sec = sec
        self.mode_requested = mode
        self.mode = "rank" if mode in ("rank", "auto") else "pct"
        self.attrition = pd.DataFrame()
        self.panel_cols = ["u_mid", "u_micro", "mcap_rank", "mcap_pct", "adv20", "days_listed"]
        self._delist = {}
        if "delisting_date" in sec.columns:
            dd = as_ts_series(sec["delisting_date"])
            self._delist = {c: d for c, d in zip(sec["code"], dd) if pd.notna(d)}

    # ── 벡터화 빌더 (§5.3 — groupby.apply 금지) ──────────────────────────────────────────
    def annotate(self, P: pd.DataFrame, mode: Optional[str] = None) -> pd.DataFrame:
        mode = mode or self.mode
        p = P.copy()
        p["mcap"] = col(p, "mcap")
        p.loc[~(p["mcap"] > 0), "mcap"] = np.nan
        # ★ 랭크는 '그 달에 실제로 상장돼 있던' 종목만으로 매겨야 한다. 폐지 후 행이나
        #   미상장 행이 모집단에 섞이면 251~1400 밴드의 의미가 달마다 달라진다.
        live = p["listed"].astype(bool) if "listed" in p.columns else pd.Series(True, index=p.index)
        mc = p["mcap"].where(live)
        g = mc.groupby(p["month"], observed=True)
        p["mcap_rank"] = g.rank(ascending=False, method="first")
        p["mcap_pct"] = g.rank(ascending=False, pct=True, method="average")
        p["n_ranked"] = g.transform("count")

        adtv = col(p, "adv20")
        seasoned = col(p, "days_listed") >= UNIVERSE_SEASON_DAYS
        liq = adtv >= UNIVERSE_MIN_ADTV
        if mode == "pct":
            band = p["mcap_pct"].between(UNIVERSE_PCT_LO, UNIVERSE_PCT_HI)
            band_micro = p["mcap_pct"] > UNIVERSE_PCT_HI
        else:
            band = p["mcap_rank"].between(UNIVERSE_RANK_LO, UNIVERSE_RANK_HI)
            band_micro = p["mcap_rank"] > UNIVERSE_RANK_HI
        p["in_band"] = band.fillna(False) & live
        p["u_mid"] = p["in_band"] & liq.fillna(False) & seasoned.fillna(False)
        p["u_micro"] = (band_micro.fillna(False) & live & seasoned.fillna(False) &
                        (adtv >= 1e8).fillna(False))
        return p

    # ── §5.4 감쇠 감사 ───────────────────────────────────────────────────────────────────
    def audit_attrition(self, P: pd.DataFrame) -> pd.DataFrame:
        p = P.copy()
        p["year"] = p["month"].dt.year
        live = p["listed"].astype(bool) if "listed" in p.columns else pd.Series(True, index=p.index)
        adtv = col(p, "adv20")
        seasoned = col(p, "days_listed") >= UNIVERSE_SEASON_DAYS
        rows = []
        for y, gg in p.groupby("year"):
            nm = max(gg["month"].nunique(), 1)
            lv = live.loc[gg.index]
            rows.append({
                "year": int(y),
                # 전체상장 = 그 달 패널에 존재하는 모든 행(가격이 관측된 종목)
                # PIT유니버스 = 그중 상장일·폐지일 기준으로 '그 시점에 실제 상장 상태'인 것만
                #   → 두 숫자의 차이가 곧 PIT 필터가 걸러낸 양이다. 같은 값으로 찍으면
                #     이 표가 존재하는 이유(어느 게이트가 표본을 깎는가)가 사라진다.
                "전체상장": len(gg) / nm,
                "PIT유니버스": lv.sum() / nm,
                "시총밴드": (gg["in_band"] & lv).sum() / nm,
                "유동성": (gg["in_band"] & lv & adtv.loc[gg.index].ge(UNIVERSE_MIN_ADTV)).sum() / nm,
                "상장250일": (gg["in_band"] & lv & adtv.loc[gg.index].ge(UNIVERSE_MIN_ADTV)
                              & seasoned.loc[gg.index]).sum() / nm,
                "U_MID": gg["u_mid"].sum() / nm,
                "U_MICRO": gg["u_micro"].sum() / nm,
            })
        A = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
        self.attrition = A
        LOG.table([[int(r.year), f"{r.전체상장:,.0f}", f"{r.PIT유니버스:,.0f}", f"{r.시총밴드:,.0f}",
                    f"{r.유동성:,.0f}", f"{r.상장250일:,.0f}", f"{r.U_MID:,.0f}", f"{r.U_MICRO:,.0f}"]
                   for r in A.itertuples(index=False)],
                  ["년도", "전체상장", "PIT유니버스", "시총밴드", "유동성", "상장250일",
                   "U-MID", "U-MICRO"],
                  ["c", "r", "r", "r", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§5.4) — 어느 게이트에서 표본이 붕괴하는지 눈으로 본다")
        return A

    def verdict_mode(self, A: pd.DataFrame) -> Tuple[str, str]:
        """§5.4 판정: 첫해와 마지막해의 U-MID 종목수가 20% 이상 차이나면 분위로 교체."""
        if A is None or len(A) < 2:
            return self.mode, "표본 부족 — 판정 보류"
        a, b = float(A["U_MID"].iloc[0]), float(A["U_MID"].iloc[-1])
        base = max(a, b, 1.0)
        diff = abs(a - b) / base
        y0, y1 = int(A["year"].iloc[0]), int(A["year"].iloc[-1])
        txt = (f"{y0}년 {a:,.0f}종목 → {y1}년 {b:,.0f}종목 (차이 {100*diff:.1f}%)")
        if diff >= 0.20:
            return "pct", (f"❗ {txt} — 20% 이상 차이. 상장 종목 수가 크게 변해 절대 랭크"
                           f"({UNIVERSE_RANK_LO}~{UNIVERSE_RANK_HI})가 구간의 의미를 바꿉니다. "
                           f"분위({UNIVERSE_PCT_LO:.0%}~{UNIVERSE_PCT_HI:.0%})로 교체합니다.")
        return "rank", f"✔ {txt} — 20% 미만. 절대 랭크를 유지합니다."

    def resolve_mode(self, P: pd.DataFrame) -> pd.DataFrame:
        """감쇠 감사 → 필요 시 분위 모드로 재산출. auto 가 아니면 사용자 지정을 존중한다."""
        P = self.annotate(P, mode=self.mode)
        A = self.audit_attrition(P)
        verdict_mode, why = self.verdict_mode(A)
        LOG.info(f"유니버스 모드 판정: {why}")
        if self.mode_requested == "auto" and verdict_mode != self.mode:
            LOG.warn(f"유니버스 정의를 '{self.mode}' → '{verdict_mode}' 로 교체하고 재측정합니다. "
                     f"※ 이 전환은 전체 표본을 본 뒤의 결정이므로 그 자체가 약한 사후선택입니다. "
                     f"R5 절제에서 두 정의를 모두 측정해 성과가 정의에 좌우되지 않는지 확인하세요.")
            self.mode = verdict_mode
            P = self.annotate(P, mode=self.mode)
            self.audit_attrition(P)
        elif self.mode_requested != "auto":
            LOG.info(f"UNIVERSE_MODE='{self.mode_requested}' 로 고정되어 있어 자동 교체를 하지 않습니다.")
        n = int(P["u_mid"].sum())
        avg = n / max(P["month"].nunique(), 1)
        LOG.ok(f"U-MID 유니버스 확정 (mode={self.mode}) — 월평균 {avg:,.0f}종목 · 총 {n:,} 종목·월")
        if avg < 200:
            LOG.warn(f"U-MID 월평균이 {avg:,.0f}종목으로 200 미만입니다. §11-6 킬 기준입니다 — "
                     f"통계 검정이 불가능한 수준이므로 위 감쇠표에서 어느 게이트가 원인인지 "
                     f"먼저 확인하세요(임계값부터 낮추지 마세요).")
        return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  기본 패널 격자
# ═══════════════════════════════════════════════════════════════════════════════════════════
def build_base_panel(months: pd.DatetimeIndex, px_monthly: pd.DataFrame, px_daily: pd.DataFrame,
                     sec: pd.DataFrame, mcap: pd.DataFrame) -> pd.DataFrame:
    """(month, code) 격자 + 가격/유동성/상장상태/시총. 밴드 밖 종목도 전부 보존한다."""
    P = px_monthly[px_monthly["month"].isin(months)].copy()
    P["month"] = as_ts_series(P["month"])
    P["code"] = P["code"].astype(str)

    # ── 상장 상태 (C2) ───────────────────────────────────────────────────────────────────
    s = sec.drop_duplicates("code").set_index("code")
    ld = as_ts_series(s["listing_date"]).to_dict() if "listing_date" in s.columns else {}
    dd = as_ts_series(s["delisting_date"]).to_dict() if "delisting_date" in s.columns else {}
    P["listing_date"] = P["code"].map(ld)
    P["delisting_date"] = P["code"].map(dd)
    P["listed"] = (~(P["listing_date"].notna() & (P["listing_date"] > P["month"])) &
                   ~(P["delisting_date"].notna() & (P["delisting_date"] <= P["month"])))

    # ── 상장 후 거래일 수 ────────────────────────────────────────────────────────────────
    #   ★ 앵커 주의(v2 의 조용한 유니버스 붕괴 원인): searchsorted 는 '가격패널 시작일 이전에
    #     상장한' 종목을 전부 index 0 으로 보낸다. 거기에 +250 을 더하면 1990년 상장 종목조차
    #     "패널 시작 후 250거래일"에야 시즈닝이 끝난 것으로 계산되어 2017년 중반까지
    #     기존 상장사 전부가 유니버스에서 빠진다. 에러도 로그도 없이.
    #     → 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은 이미 시즈닝 완료.
    #   ★★ 두 번째 함정: **상장일을 모르는 경우** ★★
    #     FDR GitHub 상장목록 CSV 에는 ListingDate 컬럼이 없는 스냅샷이 있다(실측 확인:
    #     컬럼이 Code/ISU_CD/Name/Market/Dept/Close 뿐). KIND 가 막히면 상장일이 전 종목 결측이
    #     되고, 그때 "모르면 신규 상장으로 간주"하면 패널 첫 12개월의 유니버스가 통째로 0 이 된다.
    #     에러도 경고도 없이. → '모른다'와 '최근 상장했다'는 완전히 다르다.
    #     앵커는 (상장일 ∨ 최초 가격 관측일) 이고, 그게 패널 시작 이전이면 시즈닝은 이미 끝났다.
    td = np.sort(pd.unique(as_ts_series(px_daily["date"]).values)) if len(px_daily) else np.array([])
    first_px = (P.groupby("code", observed=True)["month"].transform("min"))
    anchor = P["listing_date"].where(P["listing_date"].notna(), first_px)
    n_known = int(P["listing_date"].notna().sum())
    if len(td):
        t0 = as_ts(td[0])
        panel_start = P["month"].min()
        ai = anchor.to_numpy(dtype="datetime64[ns]")
        mi = P["month"].to_numpy(dtype="datetime64[ns]")
        i_anchor = np.searchsorted(td, ai, side="left")
        i_now = np.searchsorted(td, mi, side="right")
        n_days = (i_now - i_anchor).astype("float64")
        pre = (~np.isnat(ai)) & (ai <= np.datetime64(max(t0, panel_start)))
        n_days = np.where(pre, 1e6, n_days)         # 패널 시작 시점에 이미 있었음 = 시즈닝 완료
        n_days = np.where(np.isnat(ai), 1e6, n_days)   # 앵커 자체를 모르면 '오래된 종목'으로 본다
        P["days_listed"] = n_days
    else:
        P["days_listed"] = 1e6
    if n_known < 0.5 * len(P):
        LOG.warn(f"상장일이 확인된 행이 {100*n_known/max(len(P),1):.0f}% 뿐입니다 "
                 f"(KIND 상장법인목록을 못 받으면 흔합니다). 상장일이 없는 종목은 "
                 f"'최초 가격 관측일'을 앵커로 쓰고, 그것도 패널 시작 이전이면 시즈닝 완료로 "
                 f"간주합니다. → 신규 상장 종목의 시즈닝 필터가 그만큼 느슨해집니다. "
                 f"반대 방향(전 종목을 신규로 간주)이 유니버스를 통째로 비우는 것보다 안전합니다.")

    # ── PIT 시가총액 ─────────────────────────────────────────────────────────────────────
    if mcap is not None and len(mcap):
        m = mcap.copy()
        m["month"] = as_ts_series(m["month"])
        m["code"] = m["code"].astype(str)
        P = P.merge(m[["code", "month", "mcap", "mcap_src"]], on=["code", "month"], how="left")
    else:
        P["mcap"] = np.nan
        P["mcap_src"] = "none"
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) · "
           f"{mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel", P)
    return P


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §7  셀 — CELL_MID = (date, ind_mid, size_bucket)
# ═══════════════════════════════════════════════════════════════════════════════════════════
CELL_KEYS = ["ym", "ind_mid", "size_bucket"]
CELL_FALLBACK = ["ym", "ind_mid"]
CELL_FALLBACK2 = ["ym"]


def build_cells(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """셀 = (연월, 산업중분류, 규모 3단계).

    규모를 넣는 이유: 같은 산업이라도 대형/소형은 성장률 분포 자체가 다르다. 셀에 넣으면
    그 차이가 공통충격으로 흡수되어 비용 0 으로 제거된다.
    ★ 규모 버킷은 그 달의 시총 3분위다. 전 기간 고정 경계를 쓰면 인플레이션·시장 전체 상승이
      그대로 버킷 이동으로 나타나 셀 정의가 시간에 따라 흘러간다.
    """
    p = P.copy()
    ind = sec.drop_duplicates("code").set_index("code")["industry"].astype(str).to_dict() \
        if "industry" in sec.columns else {}
    raw = p["code"].map(ind).fillna("미분류").astype(str)
    # 산업 중분류: KRX/KIND 업종명은 자유 텍스트라 앞 토큰만 취해 과분할을 막는다.
    p["ind_mid"] = raw.str.replace(r"\s+", "", regex=True).str.slice(0, 6).replace("", "미분류")
    p["ym"] = p["month"].dt.strftime("%Y%m")

    mc = col(p, "mcap")
    q = mc.groupby(p["month"], observed=True).rank(pct=True, method="average")
    p["size_bucket"] = np.select([q <= 1 / 3, q <= 2 / 3, q > 2 / 3],
                                 ["S", "M", "L"], default="NA")
    n_cell = p.groupby(CELL_KEYS, observed=True)["code"].transform("size")
    n_ind = int(p["ind_mid"].nunique())
    LOG.info(f"셀 구성: {p.groupby(CELL_KEYS, observed=True).ngroups:,}개 "
             f"(중앙 크기 {int(n_cell.median()):,}종목 · 산업 {n_ind}종) · 폴백 사다리 "
             f"{'>'.join(['+'.join(CELL_KEYS), '+'.join(CELL_FALLBACK), '+'.join(CELL_FALLBACK2)])}")
    unclassified = float((p["ind_mid"] == "미분류").mean())
    if n_ind <= 2 or unclassified > 0.5:
        LOG.warn(f"산업 분류가 사실상 없습니다 (고유 {n_ind}종 · 미분류 {100*unclassified:.0f}%). "
                 f"KIND 상장법인목록을 못 받으면 이렇게 됩니다 — FDR GitHub 상장목록 CSV 에는 "
                 f"업종 컬럼이 없는 스냅샷이 있습니다. 이 상태에서는 '셀 내 정규화'가 "
                 f"'규모버킷 내 정규화'로 퇴화합니다. 예외는 안 나지만 산업 공통충격이 "
                 f"제거되지 않아 경기민감 업종이 통째로 상·하위를 차지할 수 있습니다. "
                 f"kind.krx.co.kr 접근을 확인하세요.")
        PIPE.note("WARN: 산업 분류 부재 — 셀 정규화 퇴화")
    return p


def cell_ladder(P: pd.DataFrame, keys: Sequence[str] = CELL_KEYS) -> List[pd.Series]:
    """폴백 사다리: (연월×산업×규모) → (연월×산업) → (연월). 표본이 부족하면 위로 올라간다."""
    fbs = [list(keys[:-1]) or list(keys), CELL_FALLBACK2]
    seen, out = set(), []
    for k in fbs:
        t = tuple(k)
        if t == tuple(keys) or t in seen:
            continue
        seen.add(t)
        out.append(cell_series(P, k))
    return out


def cell_series(P: pd.DataFrame, keys: Sequence[str]) -> pd.Series:
    """셀 키 결합 문자열. category dtype 을 그대로 groupby 하면 observed=False 에서
    카티션 폭발이 나므로 항상 문자열로 만든 뒤 넘긴다."""
    s = None
    for k in keys:
        c = P[k].astype(str) if k in P.columns else pd.Series("NA", index=P.index)
        s = c if s is None else (s + "\x1f" + c)
    return s if s is not None else pd.Series("ALL", index=P.index)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [15/22]  30_sensors.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1  원시 센서  (§3 · §6)                                                                  ║
# ║                                                                                          ║
# ║  ★ 이 블록에는 윈저·z·랭크·셀·TP·거부권이 **하나도** 들어가면 안 된다.                     ║
# ║    그 경계가 v3 의 핵심이다. 정규화가 L1 에 있으면 절제 1회에 L1 재빌드(30분+)가 걸린다.   ║
# ║    전부 L2 에 있으므로 파라미터 실험 1회가 수십 초다.                                      ║
# ║                                                                                          ║
# ║  출력은 parquet 로 영속화되고 L2(score)는 그 parquet 만 읽는다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _mi(P: pd.DataFrame) -> pd.Series:
    """월 인덱스(정수). diff 의 '몇 달 전'을 행 위치가 아니라 달력으로 세기 위해 쓴다."""
    m = as_ts_series(P["month"])
    return (m.dt.year * 12 + m.dt.month).astype("int64")


def _lag_ok(P: pd.DataFrame, n: int) -> pd.Series:
    """n개월 전 행이 실제로 존재하고 정확히 n개월 전인가.

    ★ 이걸 안 하면 거래정지·상장폐지 직전처럼 달이 비는 구간에서 shift(n) 이 몇 달 더 과거를
      끌어와 'n개월 변화'로 둔갑한다. 예외는 안 나고 값만 조용히 틀린다. 전 diff 에 강제한다.
    """
    prev = P.groupby("code", observed=True)["_mi"].shift(n)
    return (P["_mi"] - prev) == n


def gdiff(P: pd.DataFrame, s, n: int = 12) -> pd.Series:
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    v = v.replace([np.inf, -np.inf], np.nan)
    d = v - v.groupby(P["code"], observed=True).shift(n)
    return d.where(_lag_ok(P, n))


def gdlog(P: pd.DataFrame, s, n: int = 12) -> pd.Series:
    """Δlog. 음수/0 은 결측 — log 의 정의역 밖을 0 으로 메우는 것이 이 프로젝트 최빈 버그였다."""
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    v = v.replace([np.inf, -np.inf], np.nan)
    lv = np.log(v.where(v > 0))
    d = lv - lv.groupby(P["code"], observed=True).shift(n)
    return d.where(_lag_ok(P, n))


def groll_mean(P: pd.DataFrame, s, n: int, min_periods: Optional[int] = None) -> pd.Series:
    v = pd.to_numeric(P[s], errors="coerce") if isinstance(s, str) else pd.to_numeric(s, errors="coerce")
    return (v.groupby(P["code"], observed=True)
             .transform(lambda x: x.rolling(n, min_periods=min_periods or max(2, n // 2)).mean()))


SENSOR_STAGE = {
    # 센서 → 필요한 최소 단계(§2). 단계별로 어떤 TP 가 살아나는지가 여기서 결정된다.
    "M0": ["i_sales", "i_dio", "i_dso", "i_turn", "i_accr", "i_gpm",
           "v1_push", "v2_bad", "v5_impair"],
    "M1": ["i_capex", "i_ic", "i_roic", "p_payout", "p_invest", "p_cancel", "b4_defrev", "v3_dilute"],
    "M2": ["i_emp", "i_vapp"],
    "M3": ["d1", "d3", "dlog_M", "dlog_E"],
}
SENSOR_ALL = [s for v in SENSOR_STAGE.values() for s in v]


def build_sensors(P: pd.DataFrame, stage: str = "ALL") -> pd.DataFrame:
    """§6 원시 센서. 정규화 없음. 단계별로 필요한 것만 계산한다."""
    p = P.sort_values(["code", "month"], kind="mergesort").reset_index(drop=True)
    p["_mi"] = _mi(p)
    want = STAGE_ORDER[:STAGE_ORDER.index(stage) + 1] if stage in STAGE_ORDER else STAGE_ORDER

    # ── §6.1 재무 센서 (M0) ──────────────────────────────────────────────────────────────
    rev = col(p, "revenue_ttm")
    cogs = col(p, "cogs_ttm")
    p["i_sales"] = gdlog(p, rev, 12)
    p["i_dio"] = safe_div(col(p, "inventory"), cogs) * 365.0
    p["i_dso"] = safe_div(col(p, "receivable"), rev) * 365.0
    # i_turn 은 '회전이 나빠지지 않았다'를 양수로 만드는 부호다: -Δ(DIO+DSO)
    p["i_turn"] = -gdiff(p, p["i_dio"] + p["i_dso"], 12)
    # Sloan accruals. ★ 순이익이 음수인 구간에서 영업CF/순이익 비율을 쓰면 안 된다(부호 뒤집힘).
    #   발생액 형태로만 쓴다: (순이익 - 영업CF) / 평균총자산
    avg_assets = (col(p, "assets") + col(p, "assets").groupby(p["code"], observed=True).shift(12)
                  .where(_lag_ok(p, 12))) / 2.0
    avg_assets = avg_assets.where(avg_assets > 0, col(p, "assets").where(col(p, "assets") > 0))
    p["_accr_lvl"] = safe_div(col(p, "net_income_ttm") - col(p, "cfo_ttm"), avg_assets)
    p["i_accr"] = -gdiff(p, p["_accr_lvl"], 12)
    p["_gpm"] = safe_div(col(p, "gross_profit_ttm"), rev)
    # 매출총이익이 없는 회사는 매출-매출원가로 복원한다(계정 미매칭이 흔하다)
    p["_gpm"] = p["_gpm"].where(p["_gpm"].notna(), safe_div(rev - cogs, rev))
    p["i_gpm"] = gdiff(p, p["_gpm"], 12)

    # 거부권 원재료 (L1 이므로 판정은 하지 않고 값만 만든다)
    d_rev = gdiff(p, rev, 12)
    d_inv = gdiff(p, col(p, "inventory"), 12)
    d_rec = gdiff(p, col(p, "receivable"), 12)
    p["v1_push"] = safe_div(d_inv + d_rec, d_rev).where(d_rev > 0)     # V1 밀어내기 비율
    p["v2_bad"] = col(p, "v2_bad_3q")                                   # 분기프레임에서 이미 계산됨
    eq = col(p, "equity")
    cap_stock = col(p, "assets") - col(p, "liabilities")
    p["v5_impair"] = ((eq <= 0) | (cap_stock <= 0)).astype("float32")   # 자본잠식

    # ── §6.2 자본·자원 센서 (M1) ────────────────────────────────────────────────────────
    if "M1" in want:
        capex = col(p, "capex_ttm").abs()          # 현금흐름표에서 음수로 오는 경우가 흔하다
        base3 = groll_mean(p, capex, 36, min_periods=24)
        base3 = base3.groupby(p["code"], observed=True).shift(12).where(_lag_ok(p, 12))
        p["i_capex"] = safe_div(capex, base3)
        nwc = col(p, "cur_assets") - col(p, "cur_liab")
        ic = nwc + col(p, "ppe") + col(p, "intangible")
        p["_ic"] = ic.where(ic > 0)
        p["i_ic"] = gdlog(p, p["_ic"], 12)
        tax_rate = safe_div(col(p, "tax_expense_ttm"), col(p, "pretax_income_ttm")).clip(0.0, 0.5)
        tax_rate = tax_rate.fillna(0.22)                                 # 한국 실효법인세 근사
        nopat = col(p, "op_income_ttm") * (1.0 - tax_rate)
        avg_ic = (p["_ic"] + p["_ic"].groupby(p["code"], observed=True).shift(12)
                  .where(_lag_ok(p, 12))) / 2.0
        avg_ic = avg_ic.where(avg_ic > 0, p["_ic"])
        p["_roic"] = safe_div(nopat, avg_ic)
        p["i_roic"] = gdiff(p, p["_roic"], 12)
        p["_payout"] = safe_div(col(p, "dividend_paid_ttm").abs() +
                                col(p, "treasury_buy_ttm").abs(), col(p, "cfo_ttm"))
        p["_payout"] = p["_payout"].where(col(p, "cfo_ttm") > 0)        # 영업CF 음수면 무의미
        p["p_payout"] = gdiff(p, p["_payout"], 12)
        p["_invest"] = safe_div(capex + col(p, "rnd_ttm").abs(), rev)
        p["p_invest"] = gdiff(p, p["_invest"], 12)
        p["b4_defrev"] = safe_div(gdiff(p, col(p, "contract_liab"), 12), rev)
        if "p_cancel" not in p.columns:
            p["p_cancel"] = np.nan
        if "treasury_acq_amt" not in p.columns:
            p["treasury_acq_amt"] = np.nan
        if "v3_dilute" not in p.columns:
            p["v3_dilute"] = 0.0

    # ── §6.3 인적 센서 (M2) ─────────────────────────────────────────────────────────────
    if "M2" in want:
        emp = col(p, "employees")
        p["i_emp"] = gdlog(p, emp, 12)
        va = col(p, "op_income_ttm") + col(p, "payroll") + col(p, "dep_ttm").abs()
        p["_vapp"] = safe_div(va, emp.where(emp > 0))
        p["i_vapp"] = gdiff(p, p["_vapp"], 12)

    # ── §6.4 반영도 센서 (M3) ───────────────────────────────────────────────────────────
    if "M3" in want:
        # ΔlogP = ΔlogE + ΔlogM  →  ΔlogM = ΔlogP - ΔlogE.  d1 = -ΔlogM
        # 윈도우 120거래일 ≈ 6개월. 월 패널이므로 6개월 차분으로 등가 구현한다.
        W = 6
        p["dlog_P"] = gdlog(p, "close", W)
        # E = trailing 12M 이익. 적자 기업은 배수가 정의되지 않으므로 결측이다 —
        # 0 이나 대체 계정으로 채우면 횡단면 안에서 서로 다른 정의가 섞인다.
        p["dlog_E"] = gdlog(p, col(p, "net_income_ttm"), W)
        p["dlog_M"] = p["dlog_P"] - p["dlog_E"]
        p["d1"] = -p["dlog_M"]
        if "flow_120d" in p.columns:
            p["d3"] = -safe_div(col(p, "flow_120d"), col(p, "mcap"))
        else:
            p["d3"] = np.nan

    # ── R3(퀄리티 직교화)용 표준 팩터. 원시값이므로 L1 에 둔다 ───────────────────────────
    p["q_roa"] = safe_div(col(p, "net_income_ttm"), col(p, "assets"))
    p["q_gpa"] = safe_div(col(p, "gross_profit_ttm").where(col(p, "gross_profit_ttm").notna(),
                                                           rev - cogs), col(p, "assets"))
    p["q_size"] = np.log(col(p, "mcap").where(col(p, "mcap") > 0))
    p["q_bm"] = safe_div(eq, col(p, "mcap"))
    mom12 = gdlog(p, "close", 12)
    mom1 = gdlog(p, "close", 1)
    p["q_mom"] = mom12 - mom1                       # 12-1 모멘텀 (직전 1개월 반전 제거)
    p["q_vol"] = (col(p, "ret_m")
                  .groupby(p["code"], observed=True)
                  .transform(lambda s: s.rolling(12, min_periods=8).std()))

    drop = [c for c in p.columns if c.startswith("_") and c not in ("_mi",)]
    p = p.drop(columns=drop)
    made = [s for s in SENSOR_ALL if s in p.columns]
    cov = [[s, f"{int(p[s].notna().sum()):,}", f"{100*p[s].notna().mean():.1f}%"] for s in made]
    LOG.table(cov, ["센서", "유효관측", "커버리지"], ["l", "r", "r"],
              title=f"L1 센서 커버리지 (단계 {stage}) — 0% 인 센서를 쓰는 TP 는 전부 결측이 됩니다")
    PIPE.io("OUT", "MEM", "L1_sensors", p)
    return downcast(p)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  공시 파생 센서 — p_cancel · treasury_acq_amt · v3_dilute
# ═══════════════════════════════════════════════════════════════════════════════════════════
def build_disclosure_sensors(P: pd.DataFrame, dis: pd.DataFrame,
                             months: pd.DatetimeIndex) -> pd.DataFrame:
    """자사주 취득/소각, 희석성 조달.

    ★★ p_cancel 의 PIT 재정의 ★★
      §6.2 원문은 "자사주 취득공시 대비 12M 내 실제 소각 실행률" 이다. 이 정의를 시점 t 에서
      그대로 계산하면 t 이후 12개월의 소각을 봐야 한다 — **정의상 미래를 본다.**
      그대로 구현하면 R1 누수검정이 잡아내지도 못한다(누수가 아니라 정의가 미래를 포함하므로
      knowledge_date 를 앞당겨도 개선이 안 나온다). 조용히, 그리고 크게 틀린다.

      → t 시점에 **이미 판정이 끝난 취득공시만** 본다:
         t-24M ~ t-12M 사이의 취득공시 각각에 대해, 그 공시 후 12개월 안에 소각공시가
         있었는가. 이건 전부 t 이전 정보다. 창을 24개월로 두는 이유는 표본 확보다.
      이 재정의는 '신호가 1년 늦다'는 대가를 치르지만, 진정성(취득 후 실제 소각)이라는
      의미는 그대로 보존된다. 대가를 치르는 쪽이 미래를 보는 쪽보다 항상 낫다.
    """
    p = P.copy()
    for c in ("p_cancel", "treasury_acq_amt", "v3_dilute"):
        if c not in p.columns:
            p[c] = np.nan if c != "v3_dilute" else 0.0
    if dis is None or dis.empty or "stock_code" not in dis.columns:
        LOG.warn("공시목록이 없어 p_cancel · TP_P2 · V3 를 만들 수 없습니다 (결측 처리).")
        return p

    d = dis.dropna(subset=["stock_code"]).copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt"])
    acq = d[d["event"].isin(["treasury_acq", "treasury_trust"])][["stock_code", "rcept_dt"]]
    can = d[d["event"] == "treasury_canc"][["stock_code", "rcept_dt"]]

    # ── p_cancel: 이미 판정이 끝난 취득건의 소각 실행률 ─────────────────────────────────
    if len(acq):
        a = acq.rename(columns={"rcept_dt": "acq_dt"}).sort_values("acq_dt")
        if len(can):
            c = can.rename(columns={"rcept_dt": "can_dt"}).sort_values("can_dt")
            # 각 취득공시에 대해 '그 이후 첫 소각공시'
            m = pd.merge_asof(a, c, left_on="acq_dt", right_on="can_dt", by="stock_code",
                              direction="forward")
            m["executed"] = ((m["can_dt"] - m["acq_dt"]).dt.days.between(0, 365)).astype(float)
        else:
            m = a.copy()
            m["executed"] = 0.0
        m["verdict_dt"] = m["acq_dt"] + pd.Timedelta(days=365)     # 판정이 끝나는 시점
        # 월 루프 대신 이벤트→월 전개 + groupby 1회 (창 조건은 동일하다)
        W = expand_events_to_months(m, "verdict_dt", months, 730)
        if nonempty(W):
            C = (W.groupby(["stock_code", "month"], observed=True)["executed"]
                 .agg(["mean", "size"]).reset_index()
                 .rename(columns={"stock_code": "code", "mean": "_pc", "size": "_pn"}))
            C["code"] = C["code"].astype(str)
            p = p.merge(C[["code", "month", "_pc", "_pn"]], on=["code", "month"], how="left")
            p["p_cancel"] = p["_pc"]
            # TP_P2 의 '취득 규모' 축: 판정 창 안의 취득 건수(규모의 대리).
            # 금액은 공시목록에 없고 본문 파싱이 필요하므로 건수로 대체하고 그 사실을 남긴다.
            p["treasury_acq_amt"] = p["_pn"]
            p = p.drop(columns=["_pc", "_pn"])
            LOG.ok(f"p_cancel(소각 실행률) {int(p['p_cancel'].notna().sum()):,}행 — "
                   f"PIT 재정의 적용(판정이 끝난 취득건만). 원문 정의는 12개월 미래를 봅니다.")
            LOG.info("※ TP_P2 의 '취득 규모' 축은 금액이 아니라 판정창 내 취득공시 건수입니다. "
                     "공시목록에 금액이 없어 본문 파싱이 필요하기 때문입니다 — 해석 시 감안하세요.")

    # ── V3: 90일 내 대규모 희석성 조달 ──────────────────────────────────────────────────
    dil = d[d["event"].isin(["rights_issue", "cb_issue", "bw_issue"])][["stock_code", "rcept_dt"]]
    if len(dil):
        dil = dil.rename(columns={"stock_code": "code", "rcept_dt": "dt"})
        dil["code"] = dil["code"].astype(str)
        WV = expand_events_to_months(dil, "dt", months, 90)
        if nonempty(WV):
            V = WV.groupby(["code", "month"], observed=True).size().reset_index(name="n")
            p = p.merge(V, on=["code", "month"], how="left")
            p["v3_dilute"] = (p["n"].fillna(0) > 0).astype("float32")
            p = p.drop(columns=["n"])
            LOG.ok(f"V3(90일 내 희석성 조달) 발동 후보 {int(p['v3_dilute'].sum()):,}행")

    # ── V5 보강: 비적정 감사의견 ────────────────────────────────────────────────────────
    #   공시목록의 '감사보고서' 제목만으로는 의견을 알 수 없다. 자본잠식(v5_impair)으로만
    #   판정하고, 감사의견 축은 데이터가 없음을 명시한다. 있는 척하지 않는다.
    return p


def attach_investor_flows(P: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """d3 입력: 120거래일 기관+외국인 누적순매수 (일별 → 월말 스냅샷)."""
    p = P.copy()
    if flows is None or flows.empty:
        p["flow_120d"] = np.nan
        LOG.warn("수급 데이터가 없어 d3 는 결측 처리됩니다. U 는 가용 축 평균으로 계산되며 "
                 "0 으로 채우지 않습니다(§8.1).")
        return p
    f = flows.copy()
    f["date"] = as_ts_series(f["date"])
    f = f.dropna(subset=["date", "code"]).sort_values(["code", "date"])
    f["net"] = (pd.to_numeric(f.get("inst_net"), errors="coerce").fillna(0) +
                pd.to_numeric(f.get("foreign_net"), errors="coerce").fillna(0))
    # ★ 창이 실제로 120일 채워졌을 때만 값을 낸다. 상장 직후·거래정지 구간에서 3일짜리 합을
    #   120일 누적으로 부르면 그 종목만 체계적으로 작아져 d3 랭크가 왜곡된다.
    f["flow_120d"] = (f.groupby("code", observed=True)["net"]
                       .transform(lambda s: rolling_sum_min_valid(s, 120, 90)))
    f["month"] = f["date"] + pd.offsets.MonthEnd(0)
    mo = (f.sort_values("date").groupby(["code", "month"], observed=True)["flow_120d"]
           .last().reset_index())
    mo["code"] = mo["code"].astype(str)
    p = p.merge(mo, on=["code", "month"], how="left")
    LOG.ok(f"d3 수급 결합 {int(p['flow_120d'].notna().sum()):,}행 "
           f"({100*p['flow_120d'].notna().mean():.1f}%)")
    return p


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [16/22]  40_score.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  정규화 → TP → 거부권 → E/U/V → Signal   (§6.5 · §7 · §8)                             ║
# ║                                                                                          ║
# ║  이 블록 전체가 L2 다. L1 parquet 만 읽고, 매 절제마다 통째로 다시 돈다(수십 초).          ║
# ║  C5 순서는 여기서 단 한 번 하드코딩되고 파라미터화하지 않는다:                              ║
# ║      winsorize(±2σ) → cell_z → clip(·,0) → TP → rank_pct                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── §6.6 CORE-D 트레이드오프 쌍 ─────────────────────────────────────────────────────────────
TP_DEFS: List[Tuple[str, str, str, str, str]] = [
    # (ID,      개선축,      대가회피축,   최소단계, 발화 의미)
    ("TP_I2", "i_sales", "i_turn",   "M0", "매출↑인데 회전 유지 = 수요가 당김"),
    ("TP_I4", "i_sales", "i_accr",   "M0", "매출↑인데 발생액 유지 = 이익의 질"),
    ("TP_I1", "i_capex", "i_roic",   "M1", "확장하는데 수익성 유지 = 제약선 이동"),
    ("TP_P1", "p_payout", "p_invest", "M1", "환원↑인데 투자도↑ = 잉여현금 창출력"),
    ("TP_P2", "treasury_acq_amt", "p_cancel", "M1", "취득 큰데 소각까지 = 진정성"),
    ("TP_I3", "i_emp", "i_vapp",     "M2", "인원↑인데 생산성 유지 = 희석 없는 확장"),
]
# §8.1 E 의 구성: TP 6개 + rank_pct(b4_defrev). 동일가중(C7 — 최적화 금지).
E_EXTRA = [("b4_defrev", "M1", "계약부채·선수금 증가 = 미인식 수요")]
# §8.1 U 의 구성. d2/d4 는 사양 확장(USE_RESEARCH_AXIS) — R5 에서 기여도를 반드시 본다.
U_AXES_CORE = [("d1", "M3"), ("d3", "M3")]
U_AXES_RESEARCH = [("d2_raw", "M3"), ("d4_raw", "M3")]

# 하한선(breadth floor) — §8.1 "모든 축이 상위"가 아니라 **"빈 축이 없을 것"**
#
#   ★ 두 가지를 의도적으로 정했고, 둘 다 이유가 실측이다.
#
#   ① 축 하나하나가 아니라 '군' 단위다. 7개 축 전부에 50th 를 걸면 독립 가정에서
#      0.5^7 = 0.8% 만 통과해 하한선 하나가 선정을 지배한다. 그러면 R2(TP vs 나이브)
#      비교가 성립하지 않는다 — 두 팔이 같은 하한선을 물려받으면 나이브 팔조차 TP 로
#      선별된 종목만 보기 때문이다(v2 실측 자카드 0.73).
#
#   ② 군의 값은 **TP 곱이 아니라 그 군을 구성하는 원시 센서의 셀 랭크 평균**이다.
#      TP 곱을 쓰면 clip(z,0) 때문에 유니버스의 약 75%가 정확히 0 이 되고, 그 동점 덩어리의
#      평균 랭크가 0.375 라 50th 문턱에서 전부 탈락한다. 실측: 3개 군 전부에 걸면 통과율이
#      1.6% → 월 보유가 한 자릿수로 붕괴했다. 그리고 그건 '하한선'이 아니라 스코어를 한 번 더
#      건 것이다. 원시 센서 랭크로 재면 동점 덩어리가 없고, "각 센서군에서 빈 축 없이 최소한
#      중간은 간다"는 breadth 의 문자 그대로의 뜻이 된다.
FLOOR_GROUPS: Dict[str, Tuple[List[str], str]] = {
    "내부효율":   (["i_sales", "i_turn", "i_accr"], "M0"),
    "자본투입":   (["i_capex", "i_roic"], "M1"),
    "자본배분":   (["p_payout", "p_invest"], "M1"),
    "미인식수요": (["b4_defrev"], "M1"),
    "인적확장":   (["i_emp", "i_vapp"], "M2"),
}


def _stage_ok(need: str, stage: str) -> bool:
    order = STAGE_ORDER
    s = stage if stage in order else order[-1]
    return order.index(need) <= order.index(s)


def build_tps(P: pd.DataFrame, stage: str = "M3", tp_mode: str = "clip",
              cell_keys: Sequence[str] = CELL_KEYS,
              drop: Sequence[str] = ()) -> Tuple[pd.DataFrame, List[str]]:
    """§6.5 TP 조립. drop 에 든 TP 는 만들지 않는다(R5 절제용)."""
    p = P.copy()
    cells = cell_series(p, cell_keys)
    cells_fb = cell_ladder(p, cell_keys)
    made = []
    for tid, a, b, need, _why in TP_DEFS:
        if tid in drop or not _stage_ok(need, stage):
            continue
        if a not in p.columns or b not in p.columns:
            continue
        if col(p, a).notna().sum() == 0 or col(p, b).notna().sum() == 0:
            LOG.debug(f"{tid} 건너뜀 — 입력 센서({a} 또는 {b})가 전부 결측")
            continue
        p[tid] = tp_dispatch(tp_mode, col(p, a), col(p, b), cells, cells_fb)
        made.append(tid)
    return p, made


def assemble_score(P: pd.DataFrame, stage: str = "M3", tp_mode: str = "clip",
                   drop_tp: Sequence[str] = (), drop_axis: Sequence[str] = (),
                   floor_pct: float = BREADTH_FLOOR_PCT,
                   cell_keys: Sequence[str] = CELL_KEYS,
                   use_research: Optional[bool] = None,
                   quiet: bool = False) -> pd.DataFrame:
    """§8.1  Signal = rank_pct(E) × rank_pct(U) × ∏V_k

    ★ E 와 U 를 **둘 다 백분위 랭크로 바꾼 뒤** 곱한다. 원값 곱은 음수 구간에서 단조성이
      깨진다(U 는 z 평균이라 음수가 나온다). v2 는 이걸 원값으로 곱해 U<0 인 종목의
      순서가 뒤집혀 있었다.
    """
    use_research = USE_RESEARCH_AXIS if use_research is None else use_research
    p, tps = build_tps(P, stage=stage, tp_mode=tp_mode, cell_keys=cell_keys, drop=drop_tp)
    cells = cell_series(p, cell_keys)
    cells_fb = cell_ladder(p, cell_keys)
    fb = list(cell_keys[:-1]) or list(cell_keys)

    # ── E: 동일가중 평균 (C7) ───────────────────────────────────────────────────────────
    e_parts, e_names = [], []
    for tid in tps:
        r = cell_rank(p, p[tid], cell_keys, fb, tag=tid)
        p[f"r_{tid}"] = r
        e_parts.append(r)
        e_names.append(tid)
    for nm, need, _why in E_EXTRA:
        if nm in drop_tp or nm in drop_axis or not _stage_ok(need, stage):
            continue
        if nm not in p.columns or col(p, nm).notna().sum() == 0:
            continue
        r = cell_rank(p, p[nm], cell_keys, fb, tag=nm)
        p[f"r_{nm}"] = r
        e_parts.append(r)
        e_names.append(nm)
    if not e_parts:
        raise RuntimeError(
            "E 를 구성할 축이 하나도 없습니다. L1 센서가 전부 결측이라는 뜻입니다 — "
            "위 'L1 센서 커버리지' 표에서 어느 입력이 비었는지 확인하세요. "
            "가장 흔한 원인은 DART_API_KEY 미입력 또는 재무 수집 실패입니다.")
    E = pd.concat(e_parts, axis=1)
    # ★ 결측 축은 '제외 평균'이다. 0 으로 채우면 "그 축에서 최하위" 라는 거짓 주장이 된다.
    p["E"] = E.mean(axis=1, skipna=True).astype("float32")
    p["E_n"] = E.notna().sum(axis=1).astype("int16")

    # ── U: 결측 축 제외 평균 (z 스케일) ─────────────────────────────────────────────────
    u_axes = [a for a, need in U_AXES_CORE if _stage_ok(need, stage)]
    if use_research:
        u_axes += [a for a, need in U_AXES_RESEARCH if _stage_ok(need, stage)]
    u_axes = [a for a in u_axes if a not in drop_axis and a in p.columns
              and col(p, a).notna().sum() > 0]
    if u_axes:
        U = pd.concat([xsec_z_fb(col(p, a), cells, cells_fb, tag=a).rename(a) for a in u_axes],
                      axis=1)
        p["U"] = U.mean(axis=1, skipna=True).astype("float32")
        p["U_n"] = U.notna().sum(axis=1).astype("int16")
    else:
        # U 층이 아직 없는 단계(M0~M2)에서는 U 를 중립(전 종목 동일)으로 둔다.
        # 0 으로 채우는 것과 다르다 — 랭크가 전부 같아지므로 Signal 순서를 E 가 결정한다.
        p["U"] = 0.0
        p["U_n"] = 0

    p["E_rank"] = cell_rank(p, p["E"], ["ym"], ["ym"], min_n=20, tag="E")
    p["U_rank"] = (cell_rank(p, p["U"], ["ym"], ["ym"], min_n=20, tag="U")
                   if len(u_axes) else pd.Series(1.0, index=p.index, dtype="float32"))

    # ── V: 거부권 (이진, 상쇄 금지 — C6) ────────────────────────────────────────────────
    p = apply_vetoes(p, stage=stage, quiet=quiet, copy=False)

    # ── 하한선 (breadth floor) ──────────────────────────────────────────────────────────
    p, floor_info = apply_breadth_floor(p, stage=stage, tps=tps, floor_pct=floor_pct,
                                        cell_keys=cell_keys, quiet=quiet, copy=False)

    # ── Signal ──────────────────────────────────────────────────────────────────────────
    p["Signal"] = (p["E_rank"].astype("float64") * p["U_rank"].astype("float64")
                   * p["VETO"].astype("float64")).astype("float32")
    # ★ Signal_rank 는 **월 전체** 백분위여야 한다. 하위 그룹(정보량·셀)별로 매기면
    #   '자기 그룹에 혼자인' 종목이 전부 1.0 을 받아 상위를 독차지한다(v2 의 치명 결함).
    p["Signal_rank"] = (p["Signal"].groupby(p["month"], observed=True)
                        .rank(pct=True, method="average").astype("float32"))

    if not quiet:
        _report_score_health(p, e_names, u_axes, floor_info)
    PIPE.io("OUT", "MEM", "L2_scores", p[["code", "month", "E", "U", "Signal", "VETO", "FLOOR"]])
    return p


def _report_score_health(p: pd.DataFrame, e_names, u_axes, floor_info):
    n = max(len(p), 1)
    e = p["E"]
    zero_mass = float((e.fillna(-1) <= 1e-12).mean())
    top = p[p["Signal_rank"] >= 0.95]
    tie = float(top["Signal"].duplicated().mean()) if len(top) else 0.0
    LOG.table([["E 구성축", ", ".join(e_names)],
               ["U 구성축", ", ".join(u_axes) or "(없음 — 단계 미도달)"],
               ["E 유효행", f"{int(e.notna().sum()):,} / {n:,} ({100*e.notna().mean():.1f}%)"],
               ["E 평균 축개수", f"{float(p['E_n'].mean()):.2f}"],
               ["E=0 질량", f"{100*zero_mass:.1f}%"],
               ["상위 5% 내 동점비율", f"{100*tie:.1f}%"],
               ["거부권 통과", f"{int((p['VETO'] == 1).sum()):,} ({100*(p['VETO'] == 1).mean():.1f}%)"],
               ["하한선 통과", f"{int((p['FLOOR'] == 1).sum()):,} ({100*(p['FLOOR'] == 1).mean():.1f}%)"],
               ["최종 후보(둘 다 통과)",
                f"{int(((p['VETO'] == 1) & (p['FLOOR'] == 1)).sum()):,}"]],
              ["항목", "값"], ["l", "l"], title="L2 스코어 건전성")
    if zero_mass > 0.75:
        LOG.warn(f"E 가 정확히 0 인 행이 {100*zero_mass:.0f}% 입니다. clip(z,0) 방식에서는 "
                 f"자연스러운 현상이지만(양쪽 축이 모두 평균 이상인 종목만 양수), 이 값이 "
                 f"90% 를 넘으면 선정이 사실상 소수 후보 안에서만 이뤄집니다. "
                 f"R5 의 tp_mode='rank' 팔과 비교해 어느 쪽이 나은지 확인하세요.")
    if tie > 0.25:
        LOG.warn(f"상위 5% 구간의 동점비율이 {100*tie:.0f}% 입니다. 동점은 명시적 정렬키로 "
                 f"결정적으로 깨지지만(_top_n), 동점이 많다는 건 신호의 분해능이 낮다는 뜻입니다.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §8.2  거부권 — 이진, 상쇄 금지 (C6)
# ═══════════════════════════════════════════════════════════════════════════════════════════
VETO_DEFS = [
    ("V1", "M0", "밀어내기: Δ매출>0 인데 (Δ재고+Δ매출채권)/Δ매출 > 1.5"),
    ("V2", "M0", "이익-현금 괴리 3분기 연속: 순이익>0 인데 영업CF < 0.5×순이익"),
    ("V3", "M1", "90일 내 대규모 희석성 조달(유증/CB/BW)"),
    ("V5", "M0", "자본잠식 (감사의견·관리종목은 데이터 없음 — 아래 주석 참조)"),
    ("V6", "M0", "20일 평균거래대금 하한 미만 또는 거래정지"),
]


def apply_vetoes(P: pd.DataFrame, stage: str = "M3", quiet: bool = False,
                 copy: bool = True) -> pd.DataFrame:
    """각 거부권은 독립 이진이고 곱으로 결합한다. 점수로 환산해 상쇄시키지 않는다(C6).

    ★ 결측 = 통과다. 근거 없이 종목을 제외하면 그게 곧 선택편향이다.
      (예: 재무가 없는 종목을 V2 로 자르면 DART 커버리지가 낮은 소형주만 통째로 사라진다)

    copy=False 는 호출자가 이미 소유한 복사본일 때만 쓴다. 실데이터 패널은 300~400MB 라
    assemble_score 안에서 무조건 복사하면 한 번의 L2 통과에 전체 패널이 3벌 상주하고,
    R5 절제가 그걸 18회 반복한다.
    """
    p = P.copy() if copy else P
    v1 = ~(col(p, "v1_push") > 1.5).fillna(False)
    v2 = ~(col(p, "v2_bad") >= 1.0).fillna(False)
    v3 = ~(col(p, "v3_dilute") > 0).fillna(False) if _stage_ok("M1", stage) else pd.Series(True, index=p.index)
    v5 = ~(col(p, "v5_impair") > 0).fillna(False)
    halted = col(p, "volume").fillna(1.0) <= 0
    v6 = (col(p, "adv20") >= UNIVERSE_MIN_ADTV).fillna(False) & ~halted
    for nm, s in (("V1", v1), ("V2", v2), ("V3", v3), ("V5", v5), ("V6", v6)):
        p[nm] = s.astype("int8")
    p["VETO"] = (p["V1"] * p["V2"] * p["V3"] * p["V5"] * p["V6"]).astype("int8")
    if not quiet:
        rows = []
        for nm, need, why in VETO_DEFS:
            blocked = int((p[nm] == 0).sum())
            rows.append([nm, why, f"{blocked:,}", f"{100*blocked/max(len(p),1):.2f}%",
                         "활성" if _stage_ok(need, stage) else "단계 미도달"])
        LOG.table(rows, ["ID", "조건", "차단 행수", "차단률", "상태"], ["c", "l", "r", "r", "c"],
                  title="거부권 발동 감사 (§8.2 · C6 — 이진이며 상쇄 없음)")
        LOG.info("※ V5 는 자본잠식만 판정합니다. 감사의견 비적정·관리종목 지정은 공시목록 제목만으로 "
                 "알 수 없고 별도 소스가 필요합니다 — 없는 것을 있는 척하지 않습니다. "
                 "그만큼 V5 는 사양보다 약합니다.")
    return p


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  하한선 (breadth floor) — "모든 축이 상위"가 아니라 "빈 축이 없을 것"
# ═══════════════════════════════════════════════════════════════════════════════════════════
def apply_breadth_floor(P: pd.DataFrame, stage: str, tps: Sequence[str],
                        floor_pct: float = BREADTH_FLOOR_PCT,
                        cell_keys: Sequence[str] = CELL_KEYS,
                        quiet: bool = False, copy: bool = True) -> Tuple[pd.DataFrame, dict]:
    """활성 센서군 각각의 셀 내 백분위 ≥ floor_pct.

    ★ 축 단위가 아니라 '군' 단위다. 7개 축 전부에 50th 를 걸면 독립 가정에서 0.8% 만
      통과해 하한선 하나가 선정을 지배한다. 그러면 R2(TP vs 나이브) 비교가 성립하지 않는다 —
      두 팔이 같은 하한선을 물려받으면 나이브 팔조차 TP 로 선별된 종목만 보게 되기 때문이다.
    ★ 군이 '활성'인지는 단계(STAGE)로 결정한다. 단계에 도달하지 않은 군은 존재하지 않는 것이지
      비어 있는 것이 아니다. 이 구분이 없으면 M0 에서 자본배분군이 없다는 이유로 전 종목이 탈락한다.
    """
    p = P.copy() if copy else P
    fb = list(cell_keys[:-1]) or list(cell_keys)
    ok = pd.Series(True, index=p.index)
    info = {"groups": [], "pass_rate": {}}
    active_groups = 0
    for gname, (members, need) in FLOOR_GROUPS.items():
        if not _stage_ok(need, stage):
            continue
        have = [m for m in members if m in p.columns and col(p, m).notna().sum() > 0]
        if not have:
            continue
        active_groups += 1
        # 군의 값 = 구성 센서들의 셀 랭크 평균. 원시값 평균이 아니다 —
        # 원시값은 단위가 제각각(일수·비율·배수)이라 평균이 의미를 갖지 않는다.
        r_members = [cell_rank(p, col(p, m), cell_keys, fb, tag=f"floor:{m}") for m in have]
        gv = pd.concat(r_members, axis=1).mean(axis=1, skipna=True)
        r = cell_rank(p, gv, cell_keys, fb, tag=f"floor:{gname}")
        # 관측이 없으면(NaN) '빈 축'이므로 탈락한다 — 이게 §8.1 의 문자 그대로의 의미다.
        g_ok = (r >= floor_pct).fillna(False)
        ok &= g_ok
        info["groups"].append(gname)
        info["pass_rate"][gname] = float(g_ok.mean())
    if active_groups == 0:
        ok = pd.Series(True, index=p.index)
    p["FLOOR"] = ok.astype("int8")
    info["n_groups"] = active_groups
    info["overall"] = float(ok.mean())
    if not quiet and active_groups:
        LOG.table([[g, f"{100*info['pass_rate'][g]:.1f}%"] for g in info["groups"]] +
                  [["── 전체 동시통과 ──", f"{100*info['overall']:.1f}%"]],
                  ["센서군", f"백분위 ≥ {floor_pct:.0%} 통과율"], ["l", "r"],
                  title=f"하한선 감사 — 활성 센서군 {active_groups}개")
        if info["overall"] < 0.02:
            LOG.warn(f"하한선 통과율이 {100*info['overall']:.2f}% 로 매우 낮습니다. "
                     f"하한선 하나가 선정을 지배하면 R2(TP vs 나이브) 비교가 무의미해집니다 — "
                     f"두 팔이 같은 하한선을 물려받아 나이브 팔조차 TP 로 선별된 종목만 보기 "
                     f"때문입니다. R5 의 floor 40/50/60 절제 결과를 반드시 확인하세요.")
    return p, info


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [17/22]  50_backtest.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  체결 · 비용 · 성과   (§8.3 · §8.4)                                                    ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱. 체결 = 신호 산출일 **다음 거래일 시가**. 당일 종가 체결 금지(미래누수). ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 -100%. 누락 처리 금지(= 생존자편향).              ║
# ║  · 롱온리. 음의 신호는 청산 게이트로만 쓴다.                                                ║
# ║  · ★ C13(c): 보유 중 밴드 이탈은 청산 사유가 아니다. u_mid 는 **진입 필터 전용**이다.       ║
# ║      졸업(시총이 커져 밴드를 벗어남)은 성공 신호이므로 그걸 이유로 팔면 안 된다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TAX_SCHEDULE = [                       # 증권거래세(매도). 농특세 포함 총부담 기준.
    ("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
]
COMMISSION_BPS = 1.5                   # 편도. 개인 온라인 수수료 가정
SLIPPAGE_K = 0.10                      # 제곱근 충격 계수
SLIPPAGE_FLOOR = 0.0015                # 호가스프레드 하한. 소액이라고 비용이 0 이 되지는 않는다


def sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate


def slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격 + 스프레드 하한.

    ★ 하한이 없으면 소액계좌(3천만원) 가정에서 참여율이 1e-4 수준이 되어 슬리피지가 사실상
      0 이 된다. 그러면 R9(용량) 검사가 '비용이 없으니 성과가 그대로'라는 무의미한 답을 낸다.
      실제로는 소형주 호가스프레드만으로도 왕복 30~100bp 가 든다.
    """
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(max(SLIPPAGE_FLOOR, SLIPPAGE_K * math.sqrt(part)))


def exit_gate(dm, de) -> bool:
    """§8.3 청산: 'ΔlogM 이 ΔlogE 수준까지 확장 완료' 또는 논거 무효.

    진입 논리는 ΔlogE > 0 이고 시장이 아직 자본화하지 않음(ΔlogM < ΔlogE) 이다.
    그 상태를 벗어나면 청산한다. 두 경우가 한 식에 들어간다:
      · dm >= de → 시장이 마침내 재분류했다 (알파 소진 — 원래 의도한 청산)
      · de <= 0  → 이익 증가 자체가 소멸했다 (논거 무효)
    ★ v2 는 `dm >= de and de > 0` 이었다. 뒤 조건이 'de<=0' 인 전 구간을 닫아버려
      논거가 깨진 종목을 청산하는 경로가 통째로 막혀 있었다(24개월 상한까지 자리를 차지).
    NaN 은 '보유'로 떨어진다 — 모르는 것을 이유로 팔지 않는다.
    """
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def _top_n(df: pd.DataFrame, n: int, signal_col: str) -> pd.DataFrame:
    """상위 n 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep="first") 는 동점일 때 '먼저 나온 행'을 고른다. 패널이 code 로 정렬돼
      있으면 그건 '종목코드가 작은 순'이다. 동점이 많으면 보유종목이 데이터가 아니라
      정렬의 함수가 된다(v2 실측: 월 보유의 70%가 동점 1.0). 정렬키를 명시해 결정성을 준다.
    """
    if not len(df):
        return df.iloc[0:0]
    keys = [signal_col] + [c for c in ("Signal", "E", "code") if c in df.columns and c != signal_col]
    asc = [False] + [True if c == "code" else False for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(n)


def size_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 기반 사이징. 분포가 평평하면 분산, 격차가 크면 집중."""
    s = col(sub, "Signal_rank").fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = np.median(s)
    spread = float(np.mean(np.abs(s - med)))
    if spread < 1e-6:
        w = np.full(len(s), 1.0 / len(s))
    else:
        raw = np.clip(s - med, 0, None) + 1e-9
        w = raw ** min(2.0, 0.5 + spread * 8.0)
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    adv = col(sub, "adv20").fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, (adv * POS_ADV_PARTICIPATION) / max(ACCOUNT_KRW, 1), POS_MAX_WEIGHT)
    cap = np.minimum(POS_MAX_WEIGHT, np.maximum(liq_cap, POS_MIN_WEIGHT * 0.5))
    # ★ clip 후 w/w.sum() 으로 재정규화하면 상한이 도로 뚫린다. 상한에 걸린 종목은 고정하고
    #   나머지에만 잔여를 재배분하는 water-filling 으로 강제한다.
    w = np.clip(w, 0.0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    free = np.ones(len(w), dtype=bool)
    for _ in range(24):
        over = free & (w > cap)
        if not over.any():
            break
        w[over] = cap[over]
        free &= ~over
        rem = 1.0 - w[~free].sum()
        if rem <= 1e-12 or not free.any():
            break
        pool = w[free].sum()
        w[free] = (w[free] / pool * rem) if pool > 1e-12 else (rem / free.sum())
    if w.sum() > 1.0 + 1e-9:                     # 전 종목이 상한에 걸리면 현금을 남긴다
        w = w * (1.0 / w.sum())
    return sub.assign(weight=w)


def run_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, sec: pd.DataFrame,
                 signal_col: str = "Signal_rank", top_pct: float = PORTFOLIO_TOP_PCT,
                 apply_costs: bool = True, label: str = "CORE-D",
                 entry_col: str = "u_mid", quiet: bool = True,
                 max_names: int = PORTFOLIO_MAX_NAMES,
                 min_names: int = PORTFOLIO_MIN_NAMES) -> dict:
    delist = {}
    if "delisting_date" in sec.columns:
        dd = as_ts_series(sec["delisting_date"])
        delist = {c: d for c, d in zip(sec["code"].astype(str), dd) if pd.notna(d)}

    need = [c for c in ("adv20", "fwd_ret", "VETO", "FLOOR", "dlog_M", "dlog_E", "exec_px",
                        entry_col, "Signal", "E", signal_col) if c in P.columns]
    Pm = {m: g for m, g in P[["code", "month"] + need].groupby("month", observed=True)}

    hold: Dict[str, int] = {}
    rows, holdings_log, gates = [], [], []
    prev_w: Dict[str, float] = {}

    for m in months:
        sub = Pm.get(m)
        if sub is None or sub.empty:
            rows.append({"month": m, "ret": 0.0, "ret_gross": 0.0, "n": 0,
                         "turnover": 0.0, "cost": 0.0})
            prev_w = {}
            continue
        sub = sub.copy()
        rec = {c: dict(zip(sub["code"], sub[c])) for c in need if c in sub.columns}

        # ── 진입 후보: 유니버스 밴드 ∧ 거부권 ∧ 하한선 ─────────────────────────────────
        band = sub[entry_col].astype(bool) if entry_col in sub.columns else pd.Series(True, index=sub.index)
        # 폐지일이 지난 종목은 진입 후보에서도 무조건 제외한다 (유니버스 플래그와 무관하게).
        # ★ 파이썬 람다로 쓰면 종목수×개월수 만큼 호출된다. 강건성 스위트가 백테스트를
        #   40회 가까이 재실행하므로 그 비용이 그대로 곱해진다 — dict map 으로 벡터화한다.
        gone = as_ts_series(sub["code"].map(delist)).le(m).fillna(False)
        elig = sub[band & ~gone & (sub["VETO"] == 1) & (sub["FLOOR"] == 1)
                   & sub[signal_col].notna() & sub["exec_px"].notna()]
        gates.append({"month": m, "패널": len(sub), "U_MID": int(band.sum()),
                      "거부권통과": int((band & (sub["VETO"] == 1)).sum()),
                      "하한선통과": int((band & (sub["VETO"] == 1) & (sub["FLOOR"] == 1)).sum()),
                      "체결가보유": len(elig)})

        k = int(max(min_names, min(max_names, round(len(elig) * top_pct))))
        pick = _top_n(elig, k, signal_col) if len(elig) else elig

        # ── 청산 게이트 ───────────────────────────────────────────────────────────────
        #   ★ 여기서 u_mid 를 보지 않는다. C13(c) — 밴드 이탈(=졸업)은 청산 사유가 아니다.
        keep = []
        for c in list(hold):
            # ★ C2 강제: 폐지일이 지난 종목은 어떤 경로로도 보유되지 않는다.
            #   실데이터에서는 폐지 후 가격이 없어 자연히 빠지지만, 그건 '우연히 안전한' 것이지
            #   보장이 아니다. 가격 소스가 폐지 후 값을 하나라도 주면(정리매매 잔재·데이터 오류)
            #   그 종목이 계속 보유되어 이미 -100% 를 계상한 포지션이 되살아난다.
            _dl = delist.get(c)
            if _dl is not None and pd.notna(_dl) and _dl <= m:
                continue
            if c not in rec.get("exec_px", {}):
                continue                                   # 패널에서 사라짐(폐지) → 아래서 -100%
            if rec.get("VETO", {}).get(c, 1) == 0:
                continue                                   # 거부권 발동 → 즉시 강제청산
            if hold[c] >= HOLD_MAX_MONTHS:
                continue
            if exit_gate(rec.get("dlog_M", {}).get(c), rec.get("dlog_E", {}).get(c)):
                continue
            keep.append(c)

        picked = set(pick["code"]) if len(pick) else set()
        carry = sub[sub["code"].isin([c for c in keep if c not in picked])]
        target = pd.concat([pick, carry], ignore_index=True) if len(carry) else pick
        if len(target) > max_names:
            target = _top_n(target, max_names, signal_col)
        target = size_positions(target) if len(target) else target.assign(weight=[])
        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}

        turn = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0)) for c in set(w_new) | set(prev_w))
        cost = 0.0
        if apply_costs:
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                a = rec.get("adv20", {}).get(c)
                adv = float(a) if a is not None and pd.notna(a) else 0.0
                cost += abs(dw) * (COMMISSION_BPS / 1e4
                                   + slippage(abs(dw) * ACCOUNT_KRW, adv)
                                   + (sell_tax(m) if dw < 0 else 0.0))

        ret = 0.0
        for c, w in w_new.items():
            f = rec.get("fwd_ret", {}).get(c)
            fr = float(f) if f is not None and pd.notna(f) else np.nan
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                # ★ 상장폐지: 정리매매 최종가가 없으면 -100%. 누락 처리 금지(C2).
                fr = -1.0 if not np.isfinite(fr) else fr
            if not np.isfinite(fr):
                fr = 0.0
            ret += w * fr
            holdings_log.append({"month": m, "code": c, "weight": w, "ret": fr,
                                 "signal": rec.get(signal_col, {}).get(c, np.nan)})
        # 폐지로 패널에서 사라진 보유 종목도 손실을 계상한다(빠뜨리면 생존자편향)
        for c, w in prev_w.items():
            if c in w_new or c in rec.get("exec_px", {}):
                continue
            dl = delist.get(c)
            if dl is not None and pd.notna(dl) and dl <= m + pd.offsets.MonthEnd(1):
                ret += w * (-1.0)
                holdings_log.append({"month": m, "code": c, "weight": w, "ret": -1.0,
                                     "signal": np.nan})

        rows.append({"month": m, "ret": ret - cost, "ret_gross": ret, "n": len(w_new),
                     "turnover": turn, "cost": cost})
        hold = {c: (hold.get(c, 0) + 1) for c in w_new}
        prev_w = w_new

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    G = pd.DataFrame(gates)
    if not quiet and len(G):
        LOG.table([[g, f"{G[g].mean():,.0f}", f"{G[g].min():,.0f}", f"{G[g].max():,.0f}",
                    ("" if i == 0 else f"{100*G[g].mean()/max(G[G.columns[1]].mean(),1e-9):.0f}%")]
                   for i, g in enumerate([c for c in G.columns if c != "month"])],
                  ["게이트", "월평균", "최소", "최대", "U-MID 대비"], ["l", "r", "r", "r", "r"],
                  title="선정 깔때기 — 어느 게이트에서 후보가 사라지는지")
    return {"returns": R, "holdings": pd.DataFrame(holdings_log), "gates": G, "label": label}


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  §8.4  성과 지표
# ═══════════════════════════════════════════════════════════════════════════════════════════
def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    r = col(R, "ret").fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1 + r)
    years = n / 12.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(12) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(12) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "월수": n, "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균수익": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(월)": int(mx),
        "누적수익": float(eq[-1] - 1),
        "평균보유종목수": float(R["n"].mean()) if "n" in R else np.nan,
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """§8.4 — 이 전략은 IR 이 아니라 우측 꼬리에 의존한다.

    ★ 상위 소수를 제외했을 때 성과가 사라지는지 반드시 측정한다. 측정 단위는 '종목'이다:
      기여도 = Σ(비중 × 수익) 을 종목별로 합산한 뒤 상위 k 를 빼고 월수익을 재구성한다.
      (월 단위로 빼면 '좋았던 달을 뺀다'가 되어 전혀 다른 질문이 된다)
    """
    H = bt.get("holdings")
    R = bt.get("returns")
    if H is None or H.empty or R is None or R.empty:
        return {}
    H = H.copy()
    H["contrib"] = pd.to_numeric(H["weight"], errors="coerce") * pd.to_numeric(H["ret"], errors="coerce")
    by_code = H.groupby("code")["contrib"].sum().sort_values(ascending=False)
    n = len(by_code)
    if n == 0:
        return {}
    out = {"기여 상위5종목": ", ".join(f"{c}({v:+.2f})" for c, v in by_code.head(5).items()),
           "보유 종목수(누적)": n}
    base = perf_stats(R)
    out["원본 CAGR"] = base.get("CAGR")
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        excl = set(by_code.index[:k])
        h2 = H[~H["code"].isin(excl)]
        r2 = h2.groupby("month")["contrib"].sum().reindex(R["month"]).fillna(0.0)
        cost = pd.to_numeric(R["cost"], errors="coerce").fillna(0).to_numpy()
        R2 = pd.DataFrame({"month": R["month"], "ret": r2.to_numpy() - cost,
                           "n": R["n"], "turnover": R["turnover"], "cost": R["cost"]})
        s2 = perf_stats(R2)
        out[f"{lab} 제외 종목수"] = k
        out[f"{lab} 제외 CAGR"] = s2.get("CAGR")
        out[f"{lab} 제외 Sharpe"] = s2.get("Sharpe")
    return out


def benchmark_returns(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    out = {}
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, (months[0] - pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d"),
                                   months[-1].strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        out[name] = d.groupby("month")["close"].last().pct_change().reindex(months)
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [18/22]  60_robust.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  R-SUITE  강건성 (§9)                                                                      ║
# ║                                                                                          ║
# ║  순서대로. 앞 단계 실패 시 판정을 KILL 로 기록한다.                                        ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§11). 나쁜 결과는 그 자체로 정보다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: List[dict] = []
ABLATION_RETURNS: "OrderedDict[str, pd.Series]" = OrderedDict()


def _rec(rid: str, name: str, verdict: str, detail: str, metric: str = "",
         kill: bool = False):
    ROBUST.append({"id": rid, "name": name, "verdict": verdict, "metric": metric,
                   "detail": detail, "kill": kill})
    icon = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "INFO": "·", "SKIP": "→"}.get(verdict, "?")
    (LOG.error if verdict == "FAIL" else LOG.warn if verdict == "WARN" else LOG.ok)(
        f"{icon} [{rid}] {name} — {verdict}  {metric}")
    if detail:
        LOG.info(f"    {detail}")


def _cagr(bt) -> float:
    return float(perf_stats(bt["returns"]).get("CAGR", np.nan))


def _calmar(bt) -> float:
    return float(perf_stats(bt["returns"]).get("Calmar", np.nan))


def _sharpe(bt) -> float:
    return float(perf_stats(bt["returns"]).get("Sharpe", np.nan))


def _holdings_set(bt) -> Dict[pd.Timestamp, set]:
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    return {m: set(g["code"]) for m, g in H.groupby("month")}


def _jaccard(a: dict, b: dict) -> float:
    ks = set(a) & set(b)
    if not ks:
        return np.nan
    vals = []
    for k in ks:
        u = a[k] | b[k]
        if u:
            vals.append(len(a[k] & b[k]) / len(u))
    return float(np.mean(vals)) if vals else np.nan


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R0 — S1 기준선 재측정  ⭐ 가장 싸고 가장 결정적
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R0_baseline(P: pd.DataFrame, months, sec, runner) -> dict:
    """§9 R0.

    ★ 정직성 고지: 이 문서에는 "S1_HARD_FIREWALL_ONLY 규칙"의 정의가 없다. 정의 없이
      '재구현'을 주장하면 그 자체가 날조다. 그래서 우리는 **이 하네스 안에서 완전히
      정의된** 세 개의 기준선을 같은 유니버스·같은 비용모델·같은 기간으로 측정하고,
      그중 '방화벽(거부권)만 쓰고 스코어는 쓰지 않는' 팔을 S1 의 가장 자연스러운 해석으로
      지정한다. 해석이라는 사실을 리포트에 명시한다.

    ★ 과거 대화의 "S1 10년 CAGR 17%" 는 오류로 확인되었다. 어디에도 하드코딩하지 않는다.
    """
    out = {}
    # B1: U-MID 동일가중 — "아무것도 하지 않는다"
    b1 = runner(P, label="B1_umid_equal", signal="equal", floor=False, veto=False)
    # B2: 거부권만 (하드 방화벽) + 유동성 상위 — S1 해석
    b2 = runner(P, label="B2_firewall_only", signal="equal", floor=False, veto=True)
    # B3: 단순 퀄리티 (GP/A 상위) — "재포장이 아닌가"의 사전 점검
    b3 = runner(P, label="B3_quality_gpa", signal="q_gpa", floor=False, veto=True)
    for k, bt in (("B1_UMID_동일가중", b1), ("B2_거부권만(S1 해석)", b2), ("B3_퀄리티GPA", b3)):
        out[k] = perf_stats(bt["returns"])
    rows = []
    for k, s in out.items():
        rows.append([k, f"{s.get('CAGR', np.nan):+.2%}", f"{s.get('MDD', np.nan):+.1%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('Calmar', np.nan):.2f}",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
    LOG.table(rows, ["기준선", "CAGR", "MDD", "Sharpe", "Calmar", "t(HAC)"],
              ["l", "r", "r", "r", "r", "r"],
              title="R0 — S1 기준선 재측정 (기억 속 숫자 사용 금지 · 동일 하네스 실측)")
    LOG.info("※ S1_HARD_FIREWALL_ONLY 의 규칙은 이 문서에 정의되어 있지 않습니다. "
             "B2(거부권만 적용, 스코어 미사용)를 가장 자연스러운 해석으로 지정했으며, "
             "이것이 해석이라는 사실을 명시합니다. 이후 문서의 공통 기준선은 B2 의 실측값입니다.")
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R1 — 누수 자가검정 (이중 대조군)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R1_leakage(P: pd.DataFrame, months, sec, runner, base_bt) -> None:
    """§9 R1.

    DART 공시는 결산기준일 대비 45~90일 후행한다. knowledge_date 를 -30일 앞당겨도 여전히
    결산일 이후라 성과가 개선되지 않고, 구현자는 정상 하네스를 '고장났다'고 오판한다.
    대조군 2개를 모두 쓴다:
      (a) 재무 knowledge_date -120일  → 뚜렷한 개선이 나와야 정상
      (b) 미래 3개월 수익률을 신호로 직접 주입 → 극적 개선이 나와야 정상
    (b)에서도 개선이 없으면 백테스트 엔진 자체가 고장난 것이다. 전 결과 무효.
    """
    base = _cagr(base_bt)
    # (b) 먼저 한다 — 가장 결정적이고 가장 싸다.
    P2 = P.copy()
    fwd3 = (P2.sort_values(["code", "month"]).groupby("code", observed=True)["fwd_ret"]
            .transform(lambda s: s.shift(-1).rolling(3, min_periods=1).sum()))
    P2["_oracle"] = fwd3
    bt_b = runner(P2, label="R1b_oracle", signal="_oracle", floor=True, veto=True)
    cb = _cagr(bt_b)
    jb = _jaccard(_holdings_set(base_bt), _holdings_set(bt_b))
    # 하한선이 선정을 지배하면 신호를 바꿔도 보유가 안 변한다 — 그 경우를 분리해서 본다.
    bt_b_nofloor = runner(P2, label="R1b_oracle_nofloor", signal="_oracle", floor=False, veto=True)
    cb2 = _cagr(bt_b_nofloor)
    ok_b = np.isfinite(cb) and np.isfinite(base) and (cb > base + 0.10)
    ok_b2 = np.isfinite(cb2) and np.isfinite(base) and (cb2 > base + 0.10)
    if ok_b or ok_b2:
        _rec("R1b", "미래수익률 직접 주입", "PASS",
             f"신호를 미래 3개월 수익률로 바꾸면 성과가 뛴다 = 신호가 실제로 선정을 움직인다. "
             f"보유종목 자카드 {jb:.2f} (낮을수록 신호가 지배적).",
             f"기준 {base:+.2%} → 오라클 {cb:+.2%} (하한선 해제 시 {cb2:+.2%})")
        if not ok_b and ok_b2:
            _rec("R1b*", "하한선 지배 경고", "WARN",
                 "하한선을 켠 상태에서는 오라클 신호조차 성과를 못 올렸습니다. 하한선이 선정을 "
                 "지배한다는 뜻이고, 그러면 R2·R5 의 신호 비교가 전부 무의미해집니다. "
                 "BREADTH_FLOOR_PCT 를 낮추거나 FLOOR_GROUPS 구성을 재검토하세요.", "")
    else:
        _rec("R1b", "미래수익률 직접 주입", "FAIL",
             "미래 수익률을 신호로 직접 넣었는데도 성과가 개선되지 않습니다. 백테스트 엔진 "
             "자체가 고장난 것입니다(신호→선정→수익 경로가 끊겨 있음). **전 결과 무효**입니다. "
             "§11-3 킬 기준.",
             f"기준 {base:+.2%} → 오라클 {cb:+.2%} / 하한선해제 {cb2:+.2%} · 자카드 {jb:.2f}",
             kill=True)
        return

    # (a) knowledge_date -120일
    kd_cols = [c for c in P.columns if c.startswith("knowledge_date_")]
    if not kd_cols:
        _rec("R1a", "knowledge_date -120일", "SKIP",
             "패널에 knowledge_date_* 컬럼이 없어 오염본을 만들 수 없습니다.", "")
        return
    LOG.info("R1a — 재무 knowledge_date 를 120일 앞당긴 오염본으로 패널을 재조립합니다. "
             "(-30일은 DART 지연보다 작아 아무 변화도 안 나옵니다 — 그래서 -120일입니다)")
    Pa = P.copy()
    # 오염 주입: 재무 as-of 결합을 120일 늦은 시점에서 한 것과 동치가 되도록 month 를 당긴다.
    # 실제 재조립 대신 등가 변환을 쓰는 이유는 L1 재빌드(30분+)를 피하기 위함이다.
    shift_n = 4                                     # 120일 ≈ 4개월
    fin_cols = [c for c in ("i_sales", "i_turn", "i_accr", "i_gpm", "i_capex", "i_roic",
                            "i_ic", "p_payout", "p_invest", "b4_defrev", "i_emp", "i_vapp",
                            "v1_push", "v2_bad") if c in Pa.columns]
    Pa = Pa.sort_values(["code", "month"])
    Pa["_mi"] = _mi(Pa)
    # ★ shift 는 '행'을 옮기지 '달'을 옮기지 않는다. 거래정지·폐지 직전처럼 달이 비면
    #   4행 뒤가 4개월 뒤가 아니다. 그대로 두면 오염 강도가 종목마다 달라져 R1a 의
    #   판정 근거가 흐려진다 — 정확히 4개월 뒤인 행만 오염시킨다.
    ahead_ok = _lag_ok(Pa, -shift_n)
    for c in fin_cols:
        Pa[c] = Pa.groupby("code", observed=True)[c].shift(-shift_n).where(ahead_ok)
    bt_a = runner(Pa, label="R1a_shift120", signal="Signal_rank", floor=True, veto=True)
    ca = _cagr(bt_a)
    if np.isfinite(ca) and np.isfinite(base) and ca > base + 0.02:
        _rec("R1a", "knowledge_date -120일", "PASS",
             "재무를 120일 일찍 알았다고 가정하면 성과가 개선됩니다 = 하네스가 시점에 민감합니다. "
             "즉 정상 경로에서는 미래를 보고 있지 않습니다.",
             f"기준 {base:+.2%} → 오염본 {ca:+.2%} (Δ{ca-base:+.2%}p)")
    else:
        _rec("R1a", "knowledge_date -120일", "WARN",
             "오염본에서 뚜렷한 개선이 나오지 않았습니다. ① 재무 센서의 기여가 원래 작거나 "
             "② 신호가 시점에 둔감하거나 ③ 이미 미래를 보고 있어 더 볼 게 없거나 입니다. "
             "R1b 가 통과했으므로 엔진 고장은 아닙니다. 재무 축의 기여도를 R5 에서 확인하세요.",
             f"기준 {base:+.2%} → 오염본 {ca:+.2%} (Δ{ca-base:+.2%}p)")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R2 — TP vs 나이브  ⭐ 패러다임 근거
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R2_tp_vs_naive(P, months, sec, runner, base_bt) -> None:
    """§9 R2 — TP 가 '개선 항목 단독'보다 유의하게 우수해야 한다.

    ★ 공정성 두 가지를 반드시 맞춘다(v2 는 둘 다 틀려서 판정이 무의미했다):
      ① 두 팔이 **각자의 증거로** 하한선을 만든다. 본선의 FLOOR 를 물려주면 나이브 팔조차
         TP 로 선별된 종목만 보게 되어 자카드 0.73 이 나온다 = 비교가 아니다.
      ② 축 개수를 맞춘다. 하한선은 축수에 지수적이라 6 대 4 면 통과폭이 크게 벌어진다.
    """
    improve_only = ["i_sales", "i_capex", "p_payout", "i_emp"]
    have = [c for c in improve_only if c in P.columns and col(P, c).notna().sum() > 0]
    if not have:
        _rec("R2", "TP vs 나이브", "SKIP", "개선축 센서가 전부 결측입니다.", "")
        return
    bt_tp = runner(P, label="R2_tp", signal="Signal_rank", floor=True, veto=True)
    bt_nv = runner(P, label="R2_naive", signal="naive_improve", floor="naive", veto=True,
                   naive_axes=have)
    s_tp, s_nv = _sharpe(bt_tp), _sharpe(bt_nv)
    c_tp, c_nv = _cagr(bt_tp), _cagr(bt_nv)
    j = _jaccard(_holdings_set(bt_tp), _holdings_set(bt_nv))
    # 유의성: 두 수익률 시계열의 차분에 HAC t
    a = bt_tp["returns"].set_index("month")["ret"]
    b = bt_nv["returns"].set_index("month")["ret"]
    d = (a - b).dropna()
    _, t = hac_tstat(d.to_numpy())

    # R2b 하니스 검정 — TP 가 무정보 난수를 못 이기면 R2 판정 자체를 신뢰하면 안 된다
    rng = np.random.default_rng(SEED)
    Pr = P.copy()
    Pr["_rand"] = rng.random(len(Pr))
    bt_rd = runner(Pr, label="R2b_random", signal="_rand", floor=False, veto=True)
    c_rd = _cagr(bt_rd)

    LOG.table([["TP (본선)", f"{c_tp:+.2%}", f"{s_tp:.2f}"],
               ["나이브 (개선축 단독)", f"{c_nv:+.2%}", f"{s_nv:.2f}"],
               ["무정보 난수 (하니스 검정)", f"{c_rd:+.2%}", f"{_sharpe(bt_rd):.2f}"]],
              ["팔", "CAGR", "Sharpe"], ["l", "r", "r"],
              title="R2 — 트레이드오프 쌍이 '개선 항목 단독'을 이기는가")
    if np.isfinite(c_tp) and np.isfinite(c_rd) and c_tp <= c_rd:
        _rec("R2b", "하니스 검정(TP vs 난수)", "WARN",
             "TP 팔이 무정보 난수 팔을 이기지 못했습니다. 이 상태에서는 R2 판정 자체를 "
             "신뢰하면 안 됩니다 — 신호가 선정을 거의 움직이지 못한다는 뜻입니다.",
             f"TP {c_tp:+.2%} vs 난수 {c_rd:+.2%}")
    if np.isfinite(t) and t > 1.5 and np.isfinite(s_tp) and np.isfinite(s_nv) and s_tp > s_nv:
        _rec("R2", "TP vs 나이브", "PASS",
             f"트레이드오프 쌍이 개선 항목 단독보다 우수합니다. 보유종목 자카드 {j:.2f} "
             f"(높으면 두 팔이 사실상 같은 종목을 본다는 뜻이므로 비교가 약합니다).",
             f"ΔSharpe {s_tp-s_nv:+.2f} · 월수익차 t(HAC) {t:+.2f}")
    else:
        _rec("R2", "TP vs 나이브", "FAIL",
             "TP 가 나이브를 유의하게 이기지 못했습니다. 이 전략의 존재 이유(트레이드오프 논리)의 "
             "근거가 소멸합니다. §11-4 킬 기준입니다 — 파라미터를 조정해 통과시키지 마세요.",
             f"Sharpe TP {s_tp:.2f} vs 나이브 {s_nv:.2f} · t(HAC) {t:+.2f} · 자카드 {j:.2f}",
             kill=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R3 — 퀄리티 팩터 직교화
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R3_orthogonal(P: pd.DataFrame, bt: dict, months) -> None:
    """표준 퀄리티/수익성/모멘텀/규모/가치 팩터로 직교화한 뒤에도 알파가 남는가.

    팩터 수익률은 U-MID 안에서 만든 롱숏 스프레드(상위 30% - 하위 30%, 동일가중)다.
    외부 팩터 데이터를 쓰지 않으므로 어떤 환경에서도 재현된다.
    """
    facs = {"q_gpa": "수익성(GP/A)", "q_roa": "수익성(ROA)", "q_mom": "모멘텀(12-1)",
            "q_size": "규모(logMcap)", "q_bm": "가치(B/M)"}
    use = [f for f in facs if f in P.columns and col(P, f).notna().sum() > 100]
    if not use or bt["returns"].empty:
        _rec("R3", "퀄리티 직교화", "SKIP", "팩터 구성 입력이 부족합니다.", "")
        return
    pool = P[P["u_mid"].astype(bool)] if "u_mid" in P.columns else P
    frets = {}
    for f in use:
        r = (col(pool, f).groupby(pool["month"], observed=True)
             .rank(pct=True, method="average"))
        fw = pool.assign(_r=r, _fr=pd.to_numeric(pool.get("fwd_ret"), errors="coerce"))
        fw = fw.dropna(subset=["_r", "_fr"])
        if fw.empty:
            continue
        hi = fw[fw["_r"] >= 0.7].groupby("month")["_fr"].mean()
        lo = fw[fw["_r"] <= 0.3].groupby("month")["_fr"].mean()
        frets[f] = (hi - lo).reindex(months)
    if not frets:
        _rec("R3", "퀄리티 직교화", "SKIP", "팩터 수익률을 만들지 못했습니다.", "")
        return
    F = pd.DataFrame(frets)
    y = bt["returns"].set_index("month")["ret"].reindex(months)
    D = pd.concat([y.rename("y"), F], axis=1).dropna()
    if len(D) < 24:
        _rec("R3", "퀄리티 직교화", "SKIP", f"공통 관측이 {len(D)}개월로 부족합니다.", "")
        return
    X = np.column_stack([np.ones(len(D))] + [D[c].to_numpy() for c in F.columns])
    beta, *_ = np.linalg.lstsq(X, D["y"].to_numpy(), rcond=None)
    resid = D["y"].to_numpy() - X @ beta
    alpha_m = float(beta[0])
    _, t_a = hac_tstat(resid + alpha_m)
    ann = (1 + alpha_m) ** 12 - 1
    LOG.table([[facs.get(c, c), f"{beta[i+1]:+.3f}"] for i, c in enumerate(F.columns)] +
              [["── 알파(월) ──", f"{alpha_m:+.4f}"], ["알파(연환산)", f"{ann:+.2%}"],
               ["t(HAC)", f"{t_a:+.2f}"]],
              ["팩터", "적재/값"], ["l", "r"],
              title="R3 — 표준 팩터 직교화 후 잔존 알파")
    if np.isfinite(t_a) and t_a > 1.65 and ann > 0:
        _rec("R3", "퀄리티 직교화", "PASS",
             "표준 퀄리티·수익성·모멘텀·규모·가치로 설명되지 않는 알파가 남습니다.",
             f"연환산 알파 {ann:+.2%} · t(HAC) {t_a:+.2f}")
    else:
        _rec("R3", "퀄리티 직교화", "FAIL",
             "표준 팩터로 직교화하면 알파가 사라집니다. 트레이드오프 쌍이 결국 기존 팩터의 "
             "재포장이라는 뜻입니다. §11-5 킬 기준입니다.",
             f"연환산 알파 {ann:+.2%} · t(HAC) {t_a:+.2f}", kill=True)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R5 — 절제 (기여 귀속) + R6 입력 생성
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R5_ablation(P, months, sec, runner, base_bt) -> pd.DataFrame:
    """§9 R5. L2 만 건드리므로 전부 합쳐 십수 분.

    구성: TP 6개 각각 제거(6) + 유니버스 경계 5 + TP 방식 3 + 하한선 3 = 17개
    ★ 널-절제(아무것도 안 뺀 것)를 반드시 포함하고 Δ가 0 인지 검정한다. v2 는 기준선이
      다른 경로를 타서 널-절제의 ΔSharpe 가 +2.08 이었다(0 이어야 한다).
    """
    cfgs: List[Tuple[str, dict]] = [("널절제(기준)", {})]
    for tid, a, b, need, _ in TP_DEFS:
        cfgs.append((f"−{tid}", {"drop_tp": [tid]}))
    for lo, hi in ((200, 1200), (251, 1400), (300, 1600)):
        cfgs.append((f"랭크{lo}~{hi}", {"uni": ("rank", lo, hi)}))
    for lo, hi in ((0.10, 0.55), (0.15, 0.60)):
        cfgs.append((f"분위{lo:.0%}~{hi:.0%}", {"uni": ("pct", lo, hi)}))
    for mode in ("clip", "rank", "signed"):
        cfgs.append((f"TP방식={mode}", {"tp_mode": mode}))
    for f in (0.40, 0.50, 0.60):
        cfgs.append((f"하한선{f:.0%}", {"floor_pct": f}))

    base_s = _sharpe(base_bt)
    rows = []
    usable: Dict[str, float] = {}
    ABLATION_RETURNS.clear()
    for name, kw in tqdm(cfgs, desc="R5 절제", ncols=88, leave=False):
        try:
            bt = runner(P, label=f"R5:{name}", signal="Signal_rank", floor=True, veto=True, **kw)
        except Exception as e:                                   # noqa
            rows.append([name, "실패", "-", "-", "-", f"{type(e).__name__}"])
            continue
        s = perf_stats(bt["returns"])
        n_hold = float(bt["returns"]["n"].mean()) if len(bt["returns"]) else 0.0
        # ★ 유니버스가 붕괴한 팔은 '성과가 나쁜 구성'이 아니라 **측정 불가**다.
        #   경계를 좁혀 후보가 0~2종목이 되면 Sharpe 는 아무 의미가 없는데, 그걸 범위에
        #   넣으면 '경계 민감도 폭'이 자동으로 커져 정상 전략도 무조건 FAIL 이 된다.
        #   (합성 300종목에서 랭크 300~1600 팔의 유니버스는 정확히 0종목이었다)
        ok = n_hold >= PORTFOLIO_MIN_NAMES
        if ok:
            ABLATION_RETURNS[name] = bt["returns"].set_index("month")["ret"]
            usable[name] = float(s.get("Sharpe", np.nan))
        rows.append([name, f"{s.get('CAGR', np.nan):+.2%}", f"{s.get('Sharpe', np.nan):.2f}",
                     f"{s.get('Sharpe', np.nan) - base_s:+.2f}", f"{n_hold:.1f}",
                     "" if ok else "측정불가(유니버스 붕괴)"])
    LOG.table(rows, ["구성", "CAGR", "Sharpe", "ΔSharpe(본선대비)", "평균종목수", "비고"],
              ["l", "r", "r", "r", "r", "l"], title="R5 — 절제 (기여 귀속)")

    null = next((r for r in rows if r[0] == "널절제(기준)"), None)
    if null and null[3] not in ("-",):
        try:
            dnull = abs(float(str(null[3]).replace("+", "")))
            if dnull > 0.05:
                _rec("R5*", "널절제 정합성", "WARN",
                     "아무것도 빼지 않은 구성의 ΔSharpe 가 0 이 아닙니다. 기준선과 절제팔이 "
                     "서로 다른 경로를 탄다는 뜻이고, 그러면 모든 기여도 숫자를 믿을 수 없습니다.",
                     f"널절제 ΔSharpe {null[3]}")
        except Exception:
            pass

    # 경계 민감도 판정 — §9 R5 는 이 판정을 리포트 첫 페이지에 쓰라고 요구한다
    vals = [v for k, v in usable.items()
            if k.startswith(("랭크", "분위")) and np.isfinite(v)]
    n_dropped = sum(1 for r in rows if r[0].startswith(("랭크", "분위")) and r[-1])
    if n_dropped:
        LOG.warn(f"유니버스 경계 팔 {n_dropped}개가 '측정 불가'(유니버스 붕괴)로 판정에서 "
                 f"제외되었습니다. 조용히 빼지 않고 여기 남깁니다 — 실데이터에서 이 숫자가 "
                 f"크면 밴드 자체가 표본을 감당하지 못한다는 뜻입니다.")
    if len(vals) >= 3:
        rng_ = max(vals) - min(vals)
        if rng_ > max(0.5, 0.5 * abs(base_s if np.isfinite(base_s) else 1.0)):
            _rec("R5-경계", "유니버스 경계 민감도", "FAIL",
                 "유니버스 경계를 흔들었을 때 Sharpe 가 크게 변합니다. 이건 알파가 아니라 "
                 "특정 구간의 우연입니다. (§9 R5 — 이 판정을 리포트 첫 페이지에 씁니다)",
                 f"Sharpe 범위 {min(vals):.2f} ~ {max(vals):.2f} (폭 {rng_:.2f})", kill=True)
        else:
            _rec("R5-경계", "유니버스 경계 민감도", "PASS",
                 "경계를 흔들어도 성과가 급변하지 않습니다.",
                 f"Sharpe 범위 {min(vals):.2f} ~ {max(vals):.2f} (폭 {rng_:.2f})")
    else:
        _rec("R5-경계", "유니버스 경계 민감도", "SKIP",
             f"측정 가능한 경계 팔이 {len(vals)}개뿐이라 민감도를 판정할 수 없습니다. "
             f"경계를 좁히면 유니버스가 붕괴하는 규모라는 뜻입니다 "
             f"(합성 스모크에서는 정상 — 실데이터에서 나오면 표본 자체를 재검토하세요).", "")
    tp_modes = {r[0]: r[2] for r in rows if r[0].startswith("TP방식=")}
    if tp_modes:
        LOG.info(f"§6.5 요구 — TP 방식 비교 결과를 명시합니다: " +
                 " / ".join(f"{k.split('=')[1]} Sharpe {v}" for k, v in tp_modes.items()) +
                 ".  'signed' 는 v2 의 부호버그(z×z)를 재현한 팔입니다. 이것이 clip/rank 보다 "
                 "높게 나온다면 상위 분위가 '급감+악화' 종목으로 오염되었을 때 우연히 좋았다는 "
                 "뜻이므로, 수치가 아니라 의미를 근거로 clip/rank 를 택해야 합니다.")
    return pd.DataFrame(rows, columns=["구성", "CAGR", "Sharpe", "dSharpe", "평균종목수", "비고"])


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R6 — PBO / DSR  (절제 구성 집합 위에서 CSCV · 백테스트 재실행 0회)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R6_pbo(n_split: int = 12, max_comb: int = 20000) -> None:
    """§9 R6 — C7 이 최적화를 금지하므로 파라미터 그리드가 없다.
    → R5 의 절제 구성 집합을 '구성 축'으로 삼아 N_config × T 수익률 행렬 위에서 CSCV.
    """
    if len(ABLATION_RETURNS) < 4:
        _rec("R6", "PBO / DSR", "SKIP", "절제 구성이 4개 미만이라 CSCV 를 할 수 없습니다.", "")
        return
    M = pd.DataFrame(ABLATION_RETURNS).dropna(how="all")
    M = M.dropna(axis=1, how="any")
    if M.shape[1] < 4 or M.shape[0] < 24:
        _rec("R6", "PBO / DSR", "SKIP", f"행렬 {M.shape} 가 너무 작습니다.", "")
        return
    T, N = M.shape
    S = min(n_split, (T // 6) * 2)
    S = S if S % 2 == 0 else S - 1
    if S < 4:
        _rec("R6", "PBO / DSR", "SKIP", f"기간 {T}개월로는 CSCV 분할이 불가능합니다.", "")
        return
    blocks = np.array_split(np.arange(T), S)
    from itertools import combinations
    combos = list(combinations(range(S), S // 2))
    if len(combos) > max_comb:
        rng = np.random.default_rng(SEED)
        combos = [combos[i] for i in rng.choice(len(combos), max_comb, replace=False)]
    X = M.to_numpy(dtype=float)

    def _sr(a):
        s = a.std(ddof=1)
        return a.mean() / s if s > 0 else -np.inf

    lam = []
    for tr in combos:
        tr_idx = np.concatenate([blocks[i] for i in tr])
        te_idx = np.setdiff1d(np.arange(T), tr_idx)
        sr_tr = np.array([_sr(X[tr_idx, j]) for j in range(N)])
        sr_te = np.array([_sr(X[te_idx, j]) for j in range(N)])
        best = int(np.argmax(sr_tr))
        rank = float((sr_te < sr_te[best]).sum()) / max(N - 1, 1)   # 상위일수록 1에 가까움
        w = max(min(rank, 1 - 1e-9), 1e-9)
        lam.append(math.log(w / (1 - w)))
    pbo = float(np.mean(np.array(lam) <= 0))
    LOG.table([["구성 수 (N)", f"{N}"], ["기간 (T개월)", f"{T}"],
               ["CSCV 분할 S", f"{S}"], ["조합 수", f"{len(combos):,}"],
               ["PBO (과최적화 확률)", f"{pbo:.3f}"]],
              ["항목", "값"], ["l", "r"], title="R6 — PBO / CSCV (백테스트 재실행 0회)")
    if pbo <= 0.5:
        _rec("R6", "PBO / DSR", "PASS",
             "학습구간 최우수 구성이 검증구간에서도 중앙값 이상을 유지하는 경우가 더 많습니다. "
             "※ 절제 구성들은 서로 고도로 상관되어 있어 PBO 가 낙관적으로 편향될 수 있습니다 — "
             "이 수치를 단독 근거로 쓰지 마세요.", f"PBO {pbo:.3f}")
    else:
        _rec("R6", "PBO / DSR", "WARN",
             "학습구간 최우수 구성이 검증구간에서 자주 뒤집힙니다. 구성 선택이 표본 내 "
             "우연에 의존한다는 뜻이므로 파라미터를 더 줄이세요.", f"PBO {pbo:.3f}")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R7 · R8 — 레짐 / 연도별
# ═══════════════════════════════════════════════════════════════════════════════════════════
VALUEUP_EVENTS = ["2024-01-24", "2024-02-26", "2024-05-02", "2024-09-24"]


def R7_regime(bt: dict, bench: Dict[str, pd.Series]) -> None:
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    cut = as_ts("2024-01-01")
    segs = [("2024년 이전", R[R["month"] < cut]), ("2024년 이후(밸류업 레짐)", R[R["month"] >= cut])]
    ks = pd.concat([v.rename(k) for k, v in bench.items()], axis=1) if bench else pd.DataFrame()
    rows = []
    for nm, seg in segs:
        if seg.empty:
            continue
        s = perf_stats(seg)
        bmk = ""
        if len(ks):
            b = ks.reindex(seg["month"]).mean(axis=1)
            bmk = f"{((1+b.fillna(0)).prod()**(12/max(len(b),1))-1):+.2%}"
        rows.append([nm, f"{len(seg)}개월", f"{s.get('CAGR', np.nan):+.2%}",
                     f"{s.get('Sharpe', np.nan):.2f}", f"{s.get('MDD', np.nan):+.1%}", bmk])
    LOG.table(rows, ["레짐", "기간", "CAGR", "Sharpe", "MDD", "시장(연율)"],
              ["l", "c", "r", "r", "r", "r"],
              title="R7 — 레짐 분할 (2024 전후 필수)")
    n_after = int((R["month"] >= cut).sum())
    _rec("R7", "레짐 분할", "INFO",
         f"2024년 이후 표본이 {n_after}개월뿐이라 이 구간 단독의 통계적 검정력은 낮습니다. "
         f"수치는 공개하되 '레짐 의존성 여부'의 결론 근거로 단독 사용하지 마세요. "
         f"TP_P1/TP_P2 의 레짐 의존성은 R10 정책반증으로 별도 판정합니다.", "")


def R8_subperiod(bt: dict) -> None:
    R = bt["returns"].copy()
    R["month"] = as_ts_series(R["month"])
    R["year"] = R["month"].dt.year
    rows = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        rows.append([int(y), f"{len(g)}", f"{cum:+.2%}",
                     f"{float(g['ret'].mean()):+.2%}", f"{float((g['ret'] > 0).mean()):.0%}",
                     f"{float(g['n'].mean()):.1f}", f"{float(g['turnover'].mean()):.2f}"])
    LOG.table(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수", "회전율"],
              ["c", "r", "r", "r", "r", "r", "r"], title="R8 — 연도별 안정성")
    yr = [float(r[2].rstrip("%")) / 100 for r in rows]
    if yr:
        neg = sum(1 for v in yr if v < 0)
        _rec("R8", "연도별 안정성", "INFO",
             f"손실 연도 {neg}/{len(yr)}년. 최악 {min(yr):+.1%} · 최선 {max(yr):+.1%}. "
             f"소수 연도에 성과가 집중되면 우측꼬리 의존과 결합해 재현성이 낮아집니다.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R9 — 회전율 · 용량
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R9_capacity(P, months, sec, runner, base_bt) -> None:
    """계좌 규모를 키우며 비용 차감 후 성과가 남는지 본다.

    ★ ACCOUNT_KRW=3천만 가정만 보면 참여율이 1e-4 수준이라 슬리피지가 사실상 0 이 되어
      '비용이 없으니 성과가 그대로'라는 무의미한 답이 나온다. 규모를 키워야 검사가 성립한다.
    """
    global ACCOUNT_KRW
    orig = ACCOUNT_KRW
    rows = []
    gross = perf_stats(runner(P, label="R9_nocost", signal="Signal_rank", floor=True,
                              veto=True, costs=False)["returns"])
    rows.append(["비용 미차감", f"{gross.get('CAGR', np.nan):+.2%}",
                 f"{gross.get('Sharpe', np.nan):.2f}", "-", "-"])
    try:
        for amt in (30_000_000, 300_000_000, 3_000_000_000, 30_000_000_000):
            ACCOUNT_KRW = amt
            globals()["ACCOUNT_KRW"] = amt
            bt = runner(P, label=f"R9_{amt}", signal="Signal_rank", floor=True, veto=True)
            s = perf_stats(bt["returns"])
            rows.append([f"{amt/1e8:,.0f}억원", f"{s.get('CAGR', np.nan):+.2%}",
                         f"{s.get('Sharpe', np.nan):.2f}",
                         f"{s.get('월평균비용', np.nan):.4f}",
                         f"{s.get('월평균회전율', np.nan):.2f}"])
    finally:
        ACCOUNT_KRW = orig
        globals()["ACCOUNT_KRW"] = orig
    LOG.table(rows, ["계좌 규모", "CAGR", "Sharpe", "월평균비용", "월평균회전율"],
              ["l", "r", "r", "r", "r"], title="R9 — 회전율 · 용량 (비용 차감 후 성과 잔존)")
    live = [r for r in rows[1:] if r[1] not in ("nan",)]
    try:
        c0 = float(rows[1][1].rstrip("%")) / 100
        _rec("R9", "회전율·용량", "PASS" if c0 > 0 else "FAIL",
             "소액계좌(3천만원)에서 비용 차감 후에도 성과가 남는지가 §11-7 킬 기준입니다. "
             "규모가 커질수록 슬리피지가 성과를 깎는 지점을 위 표에서 확인하세요.",
             f"3천만원 계좌 CAGR {c0:+.2%}", kill=(c0 <= 0))
    except Exception:
        _rec("R9", "회전율·용량", "INFO", "수치 파싱 실패 — 위 표를 직접 확인하세요.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  R10 — 정책 반증 (TP_P1 / TP_P2 한정)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def R10_policy(P, months, sec, runner, base_bt) -> None:
    """§9 R10 — 밸류업 발표 ±6개월을 제외해도 TP_P1/P2 의 알파가 유지되는가.

    §6.6 경고: 밸류업 프로그램은 2024년 이후다. 10년 중 최근 2년만 현 레짐이다.
    2024년 이전 구간에서 알파가 0 이면 이것은 구조적 알파가 아니라 정책 베팅이다.
    """
    have_p = [t for t, *_ in [(d[0],) for d in TP_DEFS] if t in ("TP_P1", "TP_P2")]
    if not any(t in P.columns or True for t in have_p):
        _rec("R10", "정책 반증", "SKIP", "TP_P1/TP_P2 가 구성되지 않았습니다.", "")
        return
    ev = [as_ts(x) for x in VALUEUP_EVENTS]
    excl = pd.Series(False, index=pd.Index(months, name="month"))
    for e in ev:
        excl |= (pd.Series(months, index=months) >= e - pd.DateOffset(months=6)) & \
                (pd.Series(months, index=months) <= e + pd.DateOffset(months=6))
    keep_months = pd.DatetimeIndex([m for m in months if not bool(excl.get(m, False))])
    pre24 = pd.DatetimeIndex([m for m in months if m < as_ts("2024-01-01")])

    bt_full = runner(P, label="R10_withP", signal="Signal_rank", floor=True, veto=True)
    bt_noP = runner(P, label="R10_noP", signal="Signal_rank", floor=True, veto=True,
                    drop_tp=["TP_P1", "TP_P2"])

    def _sub(bt, idx):
        R = bt["returns"].copy()
        R["month"] = as_ts_series(R["month"])
        return perf_stats(R[R["month"].isin(idx)])

    rows = []
    for lab, idx in (("전체", pd.DatetimeIndex(months)),
                     ("밸류업 ±6M 제외", keep_months),
                     ("2024년 이전만", pre24)):
        a, b = _sub(bt_full, idx), _sub(bt_noP, idx)
        rows.append([lab, f"{len(idx)}개월",
                     f"{a.get('CAGR', np.nan):+.2%}", f"{b.get('CAGR', np.nan):+.2%}",
                     f"{(a.get('CAGR', np.nan) - b.get('CAGR', np.nan)):+.2%}p"])
    LOG.table(rows, ["구간", "기간", "TP_P 포함", "TP_P 제외", "TP_P 기여"],
              ["l", "c", "r", "r", "r"],
              title="R10 — 정책 반증 (밸류업은 2024년 이후 · 그 이전 기여가 0이면 정책 베팅)")
    try:
        pre_contrib = float(rows[2][4].rstrip("p").rstrip("%")) / 100
        if pre_contrib <= 0:
            _rec("R10", "정책 반증", "FAIL",
                 "2024년 이전 구간에서 TP_P1/TP_P2 의 기여가 0 이하입니다. 이건 구조적 알파가 "
                 "아니라 정책 베팅입니다 — 해당 TP 를 폐기하거나 '정책 의존'으로 명시하세요.",
                 f"2024년 이전 TP_P 기여 {pre_contrib:+.2%}p")
        else:
            _rec("R10", "정책 반증", "PASS",
                 "밸류업 레짐 밖에서도 자본배분 TP 의 기여가 양(+)입니다.",
                 f"2024년 이전 TP_P 기여 {pre_contrib:+.2%}p")
    except Exception:
        _rec("R10", "정책 반증", "INFO", "수치 파싱 실패 — 위 표를 직접 확인하세요.", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════
def report_robustness():
    if not ROBUST:
        return
    LOG.banner("강건성 판정 요약 (§9 · §11 킬 기준)",
               "나쁜 결과는 그대로 보고합니다. 파라미터를 조정해 통과시키지 않습니다.")
    LOG.table([[r["id"], _trunc(r["name"], 26),
                {"PASS": "✔ PASS", "FAIL": "✘ FAIL", "WARN": "⚠ WARN",
                 "INFO": "· INFO", "SKIP": "→ SKIP"}.get(r["verdict"], r["verdict"]),
                _trunc(r["metric"], 40), "⛔ 킬" if r["kill"] else ""]
               for r in ROBUST],
              ["ID", "검사", "판정", "실측", "킬 기준"], ["c", "l", "c", "l", "c"], maxw=42)
    kills = [r for r in ROBUST if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 발동", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
        _safe_print("\n  이 전략은 위 기준에 따라 **폐기 대상**입니다. 결과를 그대로 보고합니다.")
    else:
        LOG.ok("킬 기준에 걸린 항목이 없습니다.")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [19/22]  70_report.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증표 · 해석표 · 진단카드 · 데이터흐름 지도                                     ║
# ║                                                                                          ║
# ║  사용자 요구: "에러 발생 시 어디서 에러가 발생했고 데이터 입출력이 어디서 이뤄지는지,       ║
# ║  애널리스트보고서와 식별된 애널리스트가 제대로 연결되었는지, 다중소스 원장연결은            ║
# ║  확실한지를 한눈에 파악할 수 있게" → 아래 세 표가 그 답이다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _fnum(x, default: float = float("nan")) -> float:
    """포맷 직전 방어. None/NaT/문자열이 f-string 숫자 포맷에 닿으면 ValueError 로 죽는데,
    하필 그 지점이 '리포트 출력'이라 백테스트를 다 돌리고 마지막에 잃는다."""
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:
        return default


def report_performance(bt: dict, bench: Dict[str, pd.Series], title: str = "성과 검증"):
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과 지표를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return s
    LOG.banner(f"{title} — {bt.get('label', '')}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 리밸런싱 · 다음 거래일 시가 체결")
    fmt = {"CAGR": "{:+.2%}", "연변동성": "{:.2%}", "MDD": "{:+.2%}", "승률": "{:.1%}",
           "월평균수익": "{:+.3%}", "누적수익": "{:+.2%}", "월평균비용": "{:.4%}"}
    LOG.table([[k, (fmt.get(k, "{:,.3f}").format(v) if isinstance(v, float) and np.isfinite(v)
                    else (f"{v:,}" if isinstance(v, (int,)) else str(v)))]
               for k, v in s.items()],
              ["지표", "값"], ["l", "r"])
    if bench:
        rows = []
        R = bt["returns"].set_index("month")["ret"]
        for name, b in bench.items():
            b = b.reindex(R.index)
            n = int(b.notna().sum())
            if n < 12:
                continue
            cum = float((1 + b.fillna(0)).prod() - 1)
            cagr = (1 + cum) ** (12 / max(n, 1)) - 1
            ex = (R - b.fillna(0)).dropna()
            _, t = hac_tstat(ex.to_numpy())
            rows.append([name, f"{cagr:+.2%}", f"{cum:+.2%}",
                         f"{float(ex.mean())*12:+.2%}", f"{t:+.2f}"])
        if rows:
            LOG.table(rows, ["벤치마크", "CAGR", "누적", "연초과수익", "t(HAC)"],
                      ["l", "r", "r", "r", "r"], title="벤치마크 대비")
    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, (f"{v:+.2%}" if isinstance(v, float) and "CAGR" in k
                        else f"{v:.2f}" if isinstance(v, float) else str(v))]
                   for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 기여도 (§8.4) — 상위 소수를 빼면 성과가 사라지는가")
        try:
            base, ex5 = rt.get("원본 CAGR"), rt.get("상위5% 제외 CAGR")
            if base is not None and ex5 is not None and np.isfinite(base) and np.isfinite(ex5):
                LOG.info(f"상위 5% 종목을 빼면 CAGR 이 {base:+.2%} → {ex5:+.2%} 로 바뀝니다. "
                         + ("이 전략은 우측 꼬리에 의존합니다 — 소수 종목이 성과의 대부분을 "
                            "만듭니다. 재현성이 낮고 표본 밖에서 무너질 수 있습니다."
                            if ex5 <= 0 < base else
                            "상위 소수를 빼도 성과가 남습니다 — 꼬리 의존이 지배적이지 않습니다."))
        except Exception:
            pass
    return s


def report_interpretation(P: pd.DataFrame, bt: dict):
    """해석표 — 어떤 트레이드오프 쌍이 어떤 종목을 얼마나 골랐고, 그게 수익에 얼마나 기여했나."""
    LOG.banner("해석표", "무엇이 신호를 만들었고 무엇이 수익을 만들었는가")
    tps = [t for t, *_ in [(d[0],) for d in TP_DEFS] if t in P.columns]
    rows = []
    for tid, a, b, need, why in TP_DEFS:
        if tid not in P.columns:
            rows.append([tid, why, "-", "-", "-", "미구성(단계 또는 데이터 부족)"])
            continue
        v = col(P, tid)
        pos = float((v > 0).mean())
        rows.append([tid, why, f"{int(v.notna().sum()):,}", f"{100*pos:.1f}%",
                     f"{float(v[v > 0].mean()) if (v > 0).any() else np.nan:.3f}",
                     f"{a} × {b}"])
    LOG.table(rows, ["TP", "발화 의미", "유효관측", "양수 비율", "양수 평균", "구성 축"],
              ["c", "l", "r", "r", "r", "l"],
              title="트레이드오프 쌍 (§6.6) — 양수 비율이 곧 '제약이 풀린 종목'의 비율")

    H = bt.get("holdings")
    if H is not None and not H.empty:
        H = H.copy()
        H["contrib"] = pd.to_numeric(H["weight"], errors="coerce") * pd.to_numeric(H["ret"], errors="coerce")
        H["year"] = as_ts_series(H["month"]).dt.year
        g = H.groupby("year").agg(종목수=("code", "nunique"), 기여합=("contrib", "sum"),
                                  평균수익=("ret", "mean"), 승률=("ret", lambda s: (s > 0).mean()))
        LOG.table([[int(y), f"{r.종목수:,}", f"{r.기여합:+.3f}", f"{r.평균수익:+.2%}",
                    f"{r.승률:.0%}"] for y, r in g.iterrows()],
                  ["연도", "보유 종목수", "기여합", "평균 종목수익", "종목 승률"],
                  ["c", "r", "r", "r", "r"], title="연도별 보유 종목 성과 분해")

    if "mcap_src" in P.columns:
        m = P["mcap_src"].astype(str).value_counts()
        LOG.table([[k, f"{v:,}", f"{100*v/max(len(P),1):.1f}%"] for k, v in m.items()],
                  ["시총 소스", "행수", "비중"], ["l", "r", "r"],
                  title="유니버스 정의의 근거 (C13) — 근사 비중이 크면 밴드 편입이 흔들립니다")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 10):
    """최근 시점 상위 종목 진단 카드 — 왜 이 종목이 뽑혔는지 축 단위로 보여준다."""
    if P.empty or "Signal_rank" not in P.columns:
        return ""
    last = P["month"].max()
    sub = P[(P["month"] == last) & (P["VETO"] == 1) & (P["FLOOR"] == 1)]
    if "u_mid" in sub.columns:
        sub = sub[sub["u_mid"].astype(bool)]
    if sub.empty:
        LOG.warn("최근 시점에 선정 가능한 종목이 없어 진단 카드를 만들 수 없습니다.")
        return ""
    sub = _top_n(sub, top_n, "Signal_rank")
    name = sec.drop_duplicates("code").set_index("code")["name"].astype(str).to_dict() \
        if "name" in sec.columns else {}
    lines = [f"진단 카드 — 기준월 {last:%Y-%m}  (상위 {len(sub)}종목)", "=" * 92]
    for r in sub.itertuples(index=False):
        c = getattr(r, "code")
        lines.append(f"\n[{c}] {name.get(c, '')}   Signal {getattr(r, 'Signal', float('nan')):.4f} "
                     f"(월내 백분위 {getattr(r, 'Signal_rank', float('nan')):.3f})")
        lines.append(f"  E {getattr(r, 'E', float('nan')):.3f} (축 {getattr(r, 'E_n', 0)}개) · "
                     f"U {getattr(r, 'U', float('nan')):.3f} · "
                     f"시총랭크 {getattr(r, 'mcap_rank', float('nan')):,.0f} · "
                     f"ADTV {_fnum(getattr(r, 'adv20', np.nan))/1e8:,.1f}억")
        for tid, a, b, need, why in TP_DEFS:
            v = getattr(r, tid, None)
            if v is None or not np.isfinite(v):
                continue
            lines.append(f"   · {tid} {v:6.3f}  {why}"
                         f"   [{a}={getattr(r, a, float('nan')):+.3f} / "
                         f"{b}={getattr(r, b, float('nan')):+.3f}]")
    txt = "\n".join(lines)
    _safe_print("\n" + txt)
    return txt


def report_dataflow_map():
    """데이터 흐름 지도 — 어떤 소스가 어떤 스테이지를 거쳐 어디로 갔는가."""
    if not PIPE.flow:
        return
    LOG.banner("데이터 흐름 지도",
               "소스 → 스테이지 → 산출물. PIT 열은 event/knowledge 컬럼 보유 여부다(C1 감사).")
    agg: Dict[Tuple[str, str, str], dict] = {}
    for e in PIPE.flow:
        k = (e.stage, e.kind, e.name)
        a = agg.setdefault(k, {"in": 0, "out": 0, "rows": 0, "pit": e.pit_cols, "src": e.source})
        a["in" if e.direction == "IN" else "out"] += 1
        a["rows"] = max(a["rows"], e.rows)
        if e.pit_cols and e.pit_cols != "—":
            a["pit"] = e.pit_cols
    LOG.table([[st, kd, _trunc(nm, 34), f"{v['rows']:,}" if v["rows"] >= 0 else "-",
                f"{v['in']}/{v['out']}", v["pit"] or "—", _trunc(v["src"], 28)]
               for (st, kd, nm), v in agg.items()],
              ["스테이지", "종류", "대상", "최대행수", "IN/OUT", "PIT", "소스"],
              ["l", "l", "l", "r", "c", "c", "l"], maxw=36)


def report_stage_matrix():
    """§2 단계 게이트 — 각 단계에서 무엇이 활성화되는가."""
    rows = []
    for st in STAGE_ORDER:
        tps = [t for t, a, b, need, _ in TP_DEFS if _stage_ok(need, st)]
        vs = [v for v, need, _ in VETO_DEFS if _stage_ok(need, st)]
        us = [a for a, need in U_AXES_CORE if _stage_ok(need, st)]
        rows.append([st, f"{STAGE_BUDGET_MIN.get(st, 0):.0f}분",
                     ", ".join(tps) or "-", ", ".join(vs) or "-", ", ".join(us) or "-"])
    LOG.table(rows, ["단계", "누적 예산", "활성 TP", "활성 거부권", "활성 U축"],
              ["c", "r", "l", "l", "l"],
              title="§2 단계 게이트 — M0 에서 이미 백테스트 결과가 나옵니다")


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    LOG.banner("산출물 다운로드", "아래 링크를 클릭하면 바로 저장됩니다 (미리보기 없음)")
    for p in paths:
        _safe_print(f"  · {os.path.basename(p)}  ({os.path.getsize(p)/1e6:.2f} MB)  →  {p}")
    if ENV["colab"]:
        try:
            from google.colab import files as _f                 # type: ignore
            for p in paths:
                if os.path.getsize(p) <= 200 * 1024 * 1024:
                    _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML                # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2.2'>"]
        for p in paths:
            sz = os.path.getsize(p)
            if sz > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({sz/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [20/22]  79_canary.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  CANARY (§1) — 본 수집 전 필수 확인.  예산 20분                                            ║
# ║                                                                                          ║
# ║  ★ 하나라도 FAIL 이면 **해당 항목에 의존하는 단계를 큐에서 제거하고** 사용자에게 보고한다.  ║
# ║    추측으로 진행하지 않는다. K5(상장폐지)만은 FAIL 시 전체 중단이다 —                      ║
# ║    생존자편향을 제거할 수 없으면 어떤 성과 숫자도 의미가 없기 때문이다.                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY: List[dict] = []
DISABLED: set = set()          # FAIL 로 비활성화된 기능 태그


def _canary(cid: str, item: str, ok: bool, measured: str, action: str,
            disables: Sequence[str] = ()):
    CANARY.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL",
                   "measured": measured, "action": action})
    if not ok:
        DISABLED.update(disables)
    (LOG.ok if ok else LOG.warn)(f"[{cid}] {item} — {'PASS' if ok else 'FAIL'} · {measured}")


@contextmanager
def _probe(cid: str, item: str, disables: Sequence[str] = ()):
    """★ 프로브 하나의 예외가 CANARY 전체를 죽이지 않게 격리한다.

    §1 의 설계는 "FAIL 항목에 의존하는 단계를 큐에서 제거하고 진행" 이다. 그런데 프로브가
    예외를 던지면 스테이지가 critical 이라 실행 전체가 중단되어 설계와 정면으로 어긋난다.
    실제로 K4 의 DataFrame truthiness 예외 하나가 CANARY 를 통째로 죽이고 사용자의
    10년 백테스트를 시작조차 못 하게 만들었다.

    예외는 삼키지 않는다 — FAIL 로 기록하고 예외 종류를 실측값에 남긴다. 즉 '조용히 넘어감'이
    아니라 '이 항목은 실패했고 이유는 코드 예외'로 보고된다.
    """
    try:
        yield
    except KillCriteria:
        raise                                   # K5 중단은 그대로 위로 올린다
    except Exception as e:                      # noqa
        _canary(cid, item, False,
                f"프로브 예외 {type(e).__name__}: {str(e)[:80]}",
                "이 항목에 의존하는 단계를 비활성화하고 진행합니다 (코드 결함일 수 있으니 "
                "위 트레이스백 없이도 종류가 남도록 기록합니다)", disables)
        LOG.debug(traceback.format_exc()[-800:])


def run_canary(sample_codes: Sequence[str], sample_corps: Sequence[str]) -> pd.DataFrame:
    LOG.banner("CANARY (§1) — 코드가 의존하는 전제를 실측으로 확인",
               "FAIL 항목에 의존하는 단계는 큐에서 제거합니다. 추측으로 진행하지 않습니다.")
    smp = list(sample_codes)[:200]
    corps = list(sample_corps)[:200]
    # ★ 프로브 간 공유 변수는 반드시 _probe 바깥에서 정의한다. 안에서 정의하면 그 프로브가
    #   예외로 중단됐을 때 뒤 프로브가 NameError 를 내고, 격리의 의미가 사라진다.
    probe = smp[:12] or ["005930", "000660", "035420"]
    ok1 = False
    # ── K1 · K2  DART 재무정보 일괄다운로드 ────────────────────────────────────────────
    with _probe("K1", "DART 재무정보 일괄다운로드 2016Q1", {"bulk"}):
        t0 = time.time()
        k1_rows = 0
        k1_detail = "DART_API_KEY 미입력"
        if DART_API_KEY:
            names, diag = _bulk_discover(2016, REPRT_CODES["Q1"])
            if not names:
                names = _bulk_candidates(2016, REPRT_CODES["Q1"])
            raw, used = None, ""
            for fl in names[:8]:
                if time.time() - t0 > 180:
                    break
                raw = _bulk_fetch_one(fl)
                if raw:
                    used = fl
                    break
            if raw:
                k1_rows = len(_parse_bulk_txt(raw, 2016, REPRT_CODES["Q1"]))
                k1_detail = f"{k1_rows:,}행 / {len(raw)/1e6:.1f}MB / {time.time()-t0:.1f}s / {used}"
            else:
                # ★ "후보 N개 전부 실패" 만으로는 아무것도 고칠 수 없다. 페이지가 실제로
                #   무엇을 돌려줬는지(상태·길이·로그인 여부·발견된 링크)를 남겨야
                #   다음 실행 로그만 보고도 원인을 특정할 수 있다.
                k1_detail = f"후보 {len(names)}개 실패 · {diag}"
        _canary("K1", "DART 재무정보 일괄다운로드 2016Q1", k1_rows > 100_000, k1_detail,
                "진행" if k1_rows > 100_000 else
                "Fallback A(fnlttMultiAcnt 배치) → Fallback B(fnlttSinglAcntAll 이어받기)로 전환. "
                "A 만으로는 재고·매출채권·영업CF가 없어 TP_I2/TP_I4/TP_I1 이 죽습니다(§4.1)",
                disables=() if k1_rows > 100_000 else {"bulk"})
        ok1 = k1_rows > 100_000

    with _probe("K2", "일괄다운로드 최초 제공 분기 ≤ 2016Q1"):
        _canary("K2", "일괄다운로드 최초 제공 분기 ≤ 2016Q1", ok1,
                "2016Q1 취득 성공 → 최초 제공 분기 ≤ 2016Q1" if ok1
                else "벌크 미취득으로 최초 제공 분기를 판정할 수 없음",
                "진행" if ok1 else "폴백 경로는 2016년부터 조회 가능하므로 백테스트 시작일은 유지합니다")

    # ── K4  가격 10년 ─────────────────────────────────────────────────────────────────
    with _probe("K4", "가격 10년 취득"):
        #   ★ 시간 상한이 필수다. 소스가 전부 막힌 환경에서 20종목 × 4소스 × 재시도는
        #     최악 30분 이상이고 §1 의 CANARY 예산(20분)을 카나리아 하나가 통째로 먹는다.
        #     '몇 종목을 봤는지'를 함께 보고하면 조기 종료가 판정을 왜곡하지 않는다.
        t0 = time.time()
        n_ok, n_try, n_miss = 0, 0, []
        for c in probe:
            if time.time() - t0 > 120:
                break
            n_try += 1
            # ★ `_px_fdr(...) or _px_naver(...)` 로 쓰면 안 된다. DataFrame 에 or 를 걸면
            #   __bool__ 이 호출되어 ValueError 로 죽는데, FDR 이 막힌 환경에서는 None 이 돌아와
            #   `None or x` 로 조용히 통과한다 — 소스가 살아 있는 실환경에서만 터진다.
            d = first_nonempty(lambda: _px_fdr(c, BACKTEST_START, BACKTEST_END),
                               lambda: _px_naver(c, BACKTEST_START, BACKTEST_END),
                               lambda: _px_yf(c, BACKTEST_START, BACKTEST_END))
            if nonempty(d) and len(d) > 1000:
                n_ok += 1
            else:
                n_miss.append(c)
        ok4 = n_try > 0 and n_ok >= max(1, int(0.9 * n_try))
        _canary("K4", "가격 10년 취득 (FDR→네이버→yfinance)", ok4,
                f"{n_ok}/{n_try} 성공 ({time.time()-t0:.1f}s"
                + (", 시간상한 조기종료" if n_try < len(probe) else "") + ")"
                + (f" · 실패 예시 {n_miss[:4]}" if n_miss else ""),
                "진행" if ok4 else "폴백 체인으로 계속하되 커버리지 감소를 감안하세요. "
                                  "전부 실패라면 네트워크에서 fchart.stock.naver.com 접근을 확인하세요")

    # ── K5  상장폐지 목록 (C2) ★ FAIL 이면 중단 ────────────────────────────────────────
    with _probe("K5", "상장폐지 목록 (C2)"):
        t0 = time.time()
        dead = fetch_fdr_delisting()
        n_dead = 0
        if dead is not None and len(dead):
            dd = as_ts_series(dead["delisting_date"])
            n_dead = int(((dd >= as_ts(BACKTEST_START)) & (dd <= as_ts(BACKTEST_END))).sum())
        ok5 = n_dead >= 200
        _canary("K5", "상장폐지 목록 (생존자편향 제거 · C2)", ok5,
                f"전체 {len(dead) if dead is not None else 0:,}건 · 백테스트 구간 내 {n_dead:,}건 "
                f"({time.time()-t0:.1f}s)",
                "진행" if ok5 else "⛔ 중단 — 생존자편향을 제거할 수 없으면 어떤 성과 숫자도 "
                                  "의미가 없습니다(§11-1)",
                disables=() if ok5 else {"__abort__"})

    # ── K6  KRX 투자자별 수급 ──────────────────────────────────────────────────────────
    with _probe("K6", "KRX 투자자별 수급", {"d3"}):
        t0 = time.time()
        n6 = 0
        if pykrx_stock is not None:
            KRXG.warmup()
            for c in probe[:5]:
                r = KRXG.call(pykrx_stock.get_market_trading_value_by_date,
                              "20240102", "20240131", c)
                if r is not None and len(r):
                    n6 += 1
        ok6 = n6 >= 3
        _canary("K6", "KRX 투자자별 수급", ok6,
                f"표본 5종목 중 {n6} 성공 ({time.time()-t0:.1f}s)"
                + ("" if pykrx_stock is not None else " · pykrx 미설치"),
                "진행" if ok6 else "d3 비활성화 — U 를 d1 단독으로 구성합니다(§1 K6)",
                disables=() if ok6 else {"d3"})

    # ── K7  DART empSttus (직원현황) ──────────────────────────────────────────────────
    with _probe("K7", "DART empSttus", {"TP_I3"}):
        t0 = time.time()
        n7, tried = 0, 0
        if DART_API_KEY and corps:
            for cc in corps[:20]:
                if time.time() - t0 > 90:
                    break
                tried += 1
                js = dart_api("empSttus.json", {"corp_code": str(cc), "bsns_year": "2016",
                                                "reprt_code": REPRT_CODES["FY"]})
                if js and isinstance(js.get("list"), list) and js["list"]:
                    n7 += 1
        rate7 = n7 / max(tried, 1)
        ok7 = rate7 >= 0.80
        _canary("K7", "DART empSttus 2016 응답률 ≥ 80%", ok7,
                f"{n7}/{tried} = {100*rate7:.0f}% ({time.time()-t0:.1f}s)",
                "진행" if ok7 else "TP_I3(인원↑인데 생산성 유지) 비활성화(§1 K7)",
                disables=() if ok7 else {"TP_I3"})

    # ── K3  필수 계정 태그 커버리지 — 본 수집 후 report_account_coverage 가 본선 판정 ──
    _canary("K3", "필수 계정 태그 커버리지 ≥ 85%", True,
            "본 수집 직후 '필수 계정 커버리지' 표에서 실측 판정합니다 "
            "(표본 200종목 사전 프로브보다 전수 실측이 강합니다)",
            "수집 후 판정 — 85% 미만 계정을 쓰는 TP 는 그 표에서 비활성화 대상으로 표시됩니다")

    C = pd.DataFrame(CANARY)
    LOG.table([[r["id"], _trunc(r["item"], 34), ("✔ PASS" if r["result"] == "PASS" else "✘ FAIL"),
                _trunc(r["measured"], 44), _trunc(r["action"], 40)]
               for r in CANARY],
              ["ID", "항목", "결과", "실측값", "조치"], ["c", "l", "c", "l", "l"], maxw=46)
    if DISABLED - {"__abort__"}:
        LOG.warn(f"CANARY 결과로 비활성화된 기능: {sorted(DISABLED - {'__abort__'})}. "
                 f"이 기능에 의존하는 지표는 결측 처리되며, 0 으로 채우지 않습니다.")
    if "__abort__" in DISABLED:
        raise KillCriteria(
            "CANARY K5 실패 — 상장폐지 목록을 확보하지 못했습니다. 생존자편향을 제거할 수 "
            "없는 상태에서 나온 성과 숫자는 체계적으로 과대평가되며, 그 크기를 추정할 방법도 "
            "없습니다. §11-1 에 따라 여기서 중단합니다. "
            "네트워크에서 raw.githubusercontent.com 접근이 가능한지 확인하세요.")
    return C


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [21/22]  80_selftest.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  자가검정 — 계약 검정 + 합성데이터 엔드투엔드 스모크                                       ║
# ║                                                                                          ║
# ║  둘은 서로 다른 것을 본다:                                                                ║
# ║   · 계약 검정 : 협상 불가 규칙(PIT·생존자편향·거부권·부호·결정성)이 코드에 실제로 있는가    ║
# ║   · 스모크    : 알파가 심어진 합성 패널에서 L2→L3 계산경로가 그 알파를 찾아내는가          ║
# ║  스모크가 통과해야 실데이터 수집을 시작한다. 수집에 30분 쓰고 계산부에서 죽는 것을 막는다.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TESTS: List[Tuple[str, str, bool, str]] = []


def _t(cid: str, name: str, ok: bool, detail: str = ""):
    TESTS.append((cid, name, bool(ok), detail))
    (LOG.ok if ok else LOG.error)(f"[{cid}] {name} — {'PASS' if ok else 'FAIL'}"
                                  + (f"  ({detail})" if detail else ""))


def make_synthetic_panel(n_code: int = 240, n_month: int = 72, seed: int = SEED
                         ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """알파가 **심어진** 합성 패널. 심어놓은 것을 못 찾으면 계산경로가 고장난 것이다."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2018-01-31", periods=n_month, freq="ME")
    codes = [f"{i:06d}" for i in range(1, n_code + 1)]
    idx = pd.MultiIndex.from_product([codes, months], names=["code", "month"])
    P = pd.DataFrame(index=idx).reset_index()
    n = len(P)

    # ── 잠재 구조 ────────────────────────────────────────────────────────────────────
    #  이 전략이 존재를 가정하는 구조를 그대로 합성한다. 세 가지를 의도적으로 넣는다:
    #
    #   ① **두 개의 독립 잠재축** A(개선) 과 B(대가 회피).
    #      수익은 max(A,0)×max(B,0) 에만 붙고 A 단독·B 단독에는 붙지 않는다.
    #      → 이래야 R2(TP vs 나이브)가 진짜 검정이 된다. 하나의 잠재축이 모든 센서와 수익을
    #        동시에 움직이면 나이브 팔도 똑같이 잘 맞혀서 R2 가 아무것도 구별하지 못한다.
    #   ② **지속성.** 전환 상태는 8~26개월 지속된다. 매월 독립난수면 청산 게이트·보유상한·
    #      회전율 경로가 전혀 검정되지 않고 회전율만 100% 로 튄다.
    #   ③ **보고 지연 3개월.** 센서는 잠재 상태를 3개월 늦게 드러낸다(DART 는 45~90일 후행).
    #      → 이래야 R1a(knowledge_date -120일)가 개선을 보여줄 수 있다. 지연이 없으면
    #        R1a 는 구조적으로 아무 변화도 못 만들고, 정상 하네스가 WARN 을 받는다.
    T = len(months)

    def _latent_block():
        start = rng.integers(0, T, size=n_code)
        dur = rng.integers(8, 27, size=n_code)
        M = np.zeros((n_code, T))
        for i in range(n_code):
            M[i, start[i]:min(T, start[i] + dur[i])] = 1.0
        return M * rng.normal(1.0, 0.35, size=n_code)[:, None]

    A_true, B_true = _latent_block(), _latent_block()
    LAG = 3                                        # 보고 지연(개월)
    A_obs = np.roll(A_true, LAG, axis=1); A_obs[:, :LAG] = 0.0
    B_obs = np.roll(B_true, LAG, axis=1); B_obs[:, :LAG] = 0.0
    a_obs, b_obs = A_obs.reshape(-1), B_obs.reshape(-1)     # (code, month) = MultiIndex 순서
    a_true, b_true = A_true.reshape(-1), B_true.reshape(-1)

    def _sen(base, load, noise):
        return base * load + rng.normal(0, noise, size=n)

    # A 계열 = 개선 축 (매출↑·설비↑·환원↑·인원↑)
    P["i_sales"] = _sen(a_obs, 1.0, 0.6)
    P["i_capex"] = _sen(a_obs, 0.9, 0.7)
    P["p_payout"] = _sen(a_obs, 0.8, 0.7)
    P["i_emp"] = _sen(a_obs, 0.8, 0.7)
    P["treasury_acq_amt"] = np.clip(_sen(a_obs, 0.6, 0.9) + 1.5, 0, None)
    # B 계열 = 대가를 치르지 않았음 (회전 유지·발생액 유지·ROIC 유지·투자 유지·생산성 유지)
    P["i_turn"] = _sen(b_obs, 1.0, 0.6)
    P["i_accr"] = _sen(b_obs, 0.8, 0.7)
    P["i_roic"] = _sen(b_obs, 0.9, 0.7)
    P["p_invest"] = _sen(b_obs, 0.8, 0.7)
    P["i_vapp"] = _sen(b_obs, 0.8, 0.7)
    P["p_cancel"] = np.clip(_sen(b_obs, 0.35, 0.35) + 0.4, 0, 1)
    P["b4_defrev"] = _sen((a_obs + b_obs) / 2, 0.05, 0.05)
    P["d1"] = _sen((a_obs + b_obs) / 2, 0.5, 0.9)              # 시장이 아직 반영 안 함
    P["d3"] = _sen((a_obs + b_obs) / 2, 0.4, 1.0)
    # 전환 중엔 이익이 늘고(dlog_E>0) 배수는 아직 안 늘었다(dlog_M<dlog_E) → 청산 게이트 유지
    P["dlog_E"] = 0.02 + (a_true + b_true) * 0.02 + rng.normal(0, 0.01, size=n)
    P["dlog_M"] = -0.01 + (a_true + b_true) * 0.003 + rng.normal(0, 0.01, size=n)
    P["v1_push"] = rng.random(size=n) * 2.0
    P["v2_bad"] = (rng.random(size=n) < 0.03).astype(float)
    P["v3_dilute"] = (rng.random(size=n) < 0.02).astype(float)
    P["v5_impair"] = (rng.random(size=n) < 0.01).astype(float)
    for c in ("q_gpa", "q_roa", "q_mom", "q_size", "q_bm"):
        P[c] = rng.normal(size=n)

    # 가격·유동성·시총
    P["close"] = 10000 * np.exp(np.cumsum(rng.normal(0, 0.06, size=n)) / 50)
    P["exec_px"] = P["close"]
    P["adv20"] = np.exp(rng.normal(20.5, 1.1, size=n))
    P["volume"] = 10000.0
    P["mcap"] = np.exp(rng.normal(25.5, 1.0, size=n))
    P["mcap_src"] = "synthetic"
    P["listed"] = True
    P["days_listed"] = 1e6
    P["industry"] = "SYN"
    P["ind_mid"] = "SYN" + (P["code"].astype(int) % 6).astype(str)
    P["ym"] = P["month"].dt.strftime("%Y%m")
    q = P.groupby("month")["mcap"].rank(pct=True)
    P["size_bucket"] = np.select([q <= 1/3, q <= 2/3], ["S", "M"], default="L")
    P["mcap_rank"] = P.groupby("month")["mcap"].rank(ascending=False, method="first")
    P["mcap_pct"] = P.groupby("month")["mcap"].rank(ascending=False, pct=True)
    P["in_band"] = P["mcap_rank"].between(20, 220)
    P["u_mid"] = P["in_band"] & (P["adv20"] >= 3e8)
    P["u_micro"] = False

    # ★ 심어놓은 알파: 두 잠재축이 **동시에** 켜졌을 때만 수익이 붙는다.
    #   A 단독·B 단독에는 보상이 없다 — 트레이드오프 쌍의 정의를 그대로 데이터에 넣은 것이고,
    #   이래야 R2(TP vs 나이브)가 구별력을 갖는다.
    both = np.maximum(a_true, 0) * np.maximum(b_true, 0)
    P["fwd_ret"] = (0.002 + 0.028 * (both / (both.std() + 1e-9))
                    + rng.normal(0, 0.070, size=n))
    P["ret_m"] = P.groupby("code")["fwd_ret"].shift(1).fillna(0.0)
    P["knowledge_date_fin"] = P["month"] - pd.Timedelta(days=50)

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "market": "KOSPI", "industry": "SYN",
                        "listing_date": pd.Timestamp("2010-01-01"),
                        "delisting_date": pd.NaT})
    # 생존자편향 검정용: 10% 는 중간에 폐지시킨다
    dl = rng.choice(codes, size=max(1, n_code // 10), replace=False)
    sec.loc[sec["code"].isin(dl), "delisting_date"] = months[len(months) // 2]
    return downcast(P), sec, months


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정", "협상 불가 규칙이 코드에 실제로 있는지 실행으로 확인한다")
    rng = np.random.default_rng(SEED)

    # ── TP 부호 (§6.5) ★ v3 최우선 교정 ───────────────────────────────────────────────
    cells = pd.Series(["c"] * 400)
    a = pd.Series(np.concatenate([np.full(200, -2.0), np.full(200, 2.0)]))
    b = pd.Series(np.concatenate([np.full(200, -2.0), np.full(200, 2.0)]))
    v = tp(a, b, cells)
    lo, hi = float(v.iloc[:200].max()), float(v.iloc[200:].min())
    _t("TP-SIGN", "TP 는 음수×음수를 최고점으로 만들지 않는다 (§6.5)",
       lo <= 1e-9 < hi, f"양쪽 음수 그룹 최대 {lo:.3f} / 양쪽 양수 그룹 최소 {hi:.3f}")
    old = tp_signed_product(xsec_z(a, cells), xsec_z(b, cells))
    _t("TP-SIGN2", "v2 원형(z×z)은 실제로 부호버그를 갖는다 (재현 확인)",
       float(old.iloc[:200].mean()) > 0,
       f"z×z 의 '양쪽 음수' 그룹 평균 {float(old.iloc[:200].mean()):+.3f} (양수면 버그 재현)")
    na = tp(pd.Series([1.0, np.nan] * 200), pd.Series([1.0] * 400), cells)
    _t("TP-NAN", "한쪽이 결측이면 TP 도 결측 (0 으로 채우지 않는다)",
       bool(na.isna().sum() >= 190), f"결측 {int(na.isna().sum())}/400")

    # ── C5 순서 ───────────────────────────────────────────────────────────────────────
    x = pd.Series(np.concatenate([rng.normal(size=99), [1e6]]))
    z = xsec_z(x, pd.Series(["c"] * 100))
    _t("C5", "winsorize(±2σ) → cell_z 순서가 극단값을 흡수한다",
       bool(np.isfinite(z).all() and z.abs().max() < 4.0),
       f"이상치 포함 z 최대 |{float(z.abs().max()):.2f}| (윈저 없으면 ~9.9)")
    inf_s = pd.Series(np.concatenate([rng.normal(size=99), [np.inf]]))
    zi = xsec_z(inf_s, pd.Series(["c"] * 100))
    _t("C5-INF", "±inf 를 먼저 NaN 으로 바꾼다 (안 하면 셀 전체 z 가 0 으로 뭉개짐)",
       bool(zi.iloc[:99].std() > 0.5), f"inf 1개 포함 시 나머지 z 표준편차 {float(zi.iloc[:99].std()):.2f}")

    # ── C6 거부권 ─────────────────────────────────────────────────────────────────────
    P = pd.DataFrame({"v1_push": [0.0, 2.0, 0.0], "v2_bad": [0.0, 0.0, 1.0],
                      "v3_dilute": 0.0, "v5_impair": 0.0,
                      "adv20": [1e9] * 3, "volume": [1e4] * 3})
    P = apply_vetoes(P, stage="M3", quiet=True)
    _t("C6", "거부권은 이진이며 상쇄되지 않는다",
       list(P["VETO"]) == [1, 0, 0], f"VETO={list(P['VETO'])} (기대 [1,0,0])")
    Pm = pd.DataFrame({"v1_push": [np.nan], "v2_bad": [np.nan], "v3_dilute": [np.nan],
                       "v5_impair": [np.nan], "adv20": [1e9], "volume": [1e4]})
    _t("C6-NA", "근거가 없으면(결측) 거부하지 않는다 (= 선택편향 방지)",
       int(apply_vetoes(Pm, stage="M3", quiet=True)["VETO"].iloc[0]) == 1)

    # ── 청산 게이트 4사분면 (§8.3) ────────────────────────────────────────────────────
    quad = {(0.01, 0.05): False,     # de>0, dm<de → 보유 (논거 유효)
            (0.06, 0.05): True,      # dm>=de     → 청산 (재분류 완료)
            (-0.01, -0.05): True,    # de<=0      → 청산 (논거 무효)
            (-0.06, -0.05): True}
    got = {k: exit_gate(*k) for k in quad}
    _t("EXIT", "청산 게이트가 네 사분면 전부에서 옳게 동작한다",
       got == quad, f"{got}")
    _t("EXIT-NA", "모르는 것(NaN)을 이유로 팔지 않는다", exit_gate(np.nan, 0.05) is False)

    # ── C8 결정성 ─────────────────────────────────────────────────────────────────────
    Ps, secs, ms = make_synthetic_panel(n_code=80, n_month=36)
    s1 = assemble_score(Ps, stage="M3", quiet=True)
    s2 = assemble_score(Ps.sample(frac=1.0, random_state=1).reset_index(drop=True),
                        stage="M3", quiet=True)
    j1 = s1.sort_values(["code", "month"])["Signal"].round(6).to_numpy()
    j2 = s2.sort_values(["code", "month"])["Signal"].round(6).to_numpy()
    same = bool(len(j1) == len(j2) and np.allclose(np.nan_to_num(j1), np.nan_to_num(j2), atol=1e-5))
    _t("C8", "행 순서를 섞어도 결과가 같다 (결정성 · 정렬 의존 없음)", same)
    b1 = run_backtest(s1, ms, secs, quiet=True)
    b2 = run_backtest(s2.sort_values(["code", "month"]).reset_index(drop=True), ms, secs, quiet=True)
    _t("C8-BT", "백테스트도 행 순서에 무관하다 (동점 처리가 결정적)",
       bool(np.allclose(b1["returns"]["ret"].fillna(0), b2["returns"]["ret"].fillna(0), atol=1e-9)))

    # ── C2 생존자편향 ─────────────────────────────────────────────────────────────────
    dl_codes = set(secs.loc[secs["delisting_date"].notna(), "code"])
    H = b1["holdings"]
    ever = bool(len(H) and len(set(H["code"]) & dl_codes) > 0)
    _t("C2", "상장폐지 종목이 폐지 전 구간에 실제로 보유될 수 있다",
       ever, f"보유된 폐지예정 종목 {len(set(H['code']) & dl_codes) if len(H) else 0}개")
    if len(H):
        dm = secs.set_index("code")["delisting_date"].to_dict()
        after = [(c, m) for c, m in zip(H["code"], H["month"])
                 if pd.notna(dm.get(c)) and m > dm[c] + pd.offsets.MonthEnd(1)]
        _t("C2-AFTER", "폐지 이후에는 보유되지 않는다", len(after) == 0, f"위반 {len(after)}건")

    # ── C13 유니버스 PIT ──────────────────────────────────────────────────────────────
    u = UniverseV3(Ps, secs, mode="rank")
    Pu = u.annotate(Ps, mode="rank")
    r = Pu.groupby("month")["mcap_rank"].max()
    _t("C13", "시총 랭크가 매 시점 독립적으로 재산출된다 (현재 시총 사용 금지)",
       bool(r.nunique() >= 1 and Pu["mcap_rank"].notna().sum() > 0),
       f"월별 최대 랭크 {int(r.min())}~{int(r.max())}")
    Pu2 = Pu.copy()
    Pu2.loc[Pu2["month"] == Pu2["month"].max(), "mcap"] *= 100      # 마지막 달만 시총 폭증
    Pu2 = u.annotate(Pu2, mode="rank")
    same_hist = bool((Pu2[Pu2["month"] < Pu2["month"].max()]["mcap_rank"].fillna(-1).to_numpy()
                      == Pu[Pu["month"] < Pu["month"].max()]["mcap_rank"].fillna(-1).to_numpy()).all())
    _t("C13-PIT", "미래 시총 변화가 과거 랭크를 바꾸지 않는다", same_hist)

    # ── C1 (merge_asof 출력 전수 검증) ────────────────────────────────────────────────
    grid = Ps[["code", "month"]].copy()
    src = pd.DataFrame({"code": Ps["code"].unique()[:50]})
    src["knowledge_date"] = pd.Timestamp("2019-06-30")
    src["xval"] = 1.0
    j = build_pit_panel(grid, {"t": src})
    bad = assert_c1(j, strict=False)
    _t("C1", "merge_asof 출력 전 행이 knowledge_date <= asof 를 만족한다", len(bad) == 0,
       "; ".join(bad) if bad else "위반 0행")
    src_bad = src.copy()
    src_bad["knowledge_date"] = pd.Timestamp("2099-01-01")
    jb = build_pit_panel(grid, {"bad": src_bad})
    got_bad = ("xval" not in jb.columns) or bool(jb["xval"].notna().sum() == 0)
    _t("C1-NEG", "미래 시점 소스는 아무 행에도 붙지 않는다 (음성 대조군)", got_bad)

    # ── 하한선 축수 정합성 ────────────────────────────────────────────────────────────
    s_m0 = assemble_score(Ps, stage="M0", quiet=True)
    s_m3 = assemble_score(Ps, stage="M3", quiet=True)
    _t("FLOOR", "단계에 도달하지 않은 센서군 때문에 전 종목이 탈락하지 않는다",
       bool(s_m0["FLOOR"].sum() > 0 and s_m3["FLOOR"].sum() > 0),
       f"M0 통과 {int(s_m0['FLOOR'].sum()):,} · M3 통과 {int(s_m3['FLOOR'].sum()):,}")

    # ── Signal_rank 는 월 전체 백분위 ────────────────────────────────────────────────
    g = s_m3.groupby("month")["Signal_rank"]
    _t("RANK", "Signal_rank 는 하위그룹이 아니라 월 전체에서 매겨진다",
       bool((g.max() <= 1.0 + 1e-6).all() and (g.nunique() > 5).mean() > 0.9),
       f"월별 고유값 중앙 {int(g.nunique().median())}개")

    # ── C10 계측 ─────────────────────────────────────────────────────────────────────
    with Stage("selftest.probe", budget_min=0.001):
        time.sleep(0.01)
    _t("C10", "모든 단계가 계측된다 (추측 금지)",
       any(r["stage"] == "selftest.probe" for r in RUNTIME_LOG))

    # ── 폴백 체인이 DataFrame 진리값에서 죽지 않는다 ──────────────────────────────────
    #   ★ 이 결함은 '소스가 막힌 환경에서만 통과'한다. 개발 중엔 _px_fdr 이 None 을 돌려줘
    #     `None or x` 로 조용히 지나가고, 소스가 살아 있는 실환경에서만 ValueError 로 죽었다.
    #     그래서 두 방향을 다 검정한다: ① 올바른 관용구가 동작하는가 ② 잘못된 관용구가
    #     실제로 죽는가(죽지 않는다면 이 검정 자체가 무의미해진 것이다).
    _df = pd.DataFrame({"a": [1, 2, 3]})
    ok_chain = False
    try:
        got = first_nonempty(lambda: None, lambda: pd.DataFrame(), lambda: _df,
                             lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        ok_chain = isinstance(got, pd.DataFrame) and len(got) == 3
    except Exception:
        ok_chain = False
    raises = False
    try:
        _ = (_df or pd.DataFrame())          # 예전 관용구 — 반드시 죽어야 한다
    except ValueError:
        raises = True
    _t("CHAIN", "폴백 체인이 DataFrame 에서 죽지 않는다 (first_nonempty)",
       ok_chain and raises,
       f"체인 정상 {ok_chain} · 구 관용구(`df or x`)가 여전히 ValueError 를 냄 {raises}")
    _t("CHAIN-ERR", "체인 중간 소스의 예외가 전체를 죽이지 않는다",
       first_nonempty(lambda: (_ for _ in ()).throw(RuntimeError("x")), lambda: _df) is not None)

    # ── 혼합 포맷 날짜 (재실행 경로의 조용한 유실) ───────────────────────────────────
    mixed = pd.Series([pd.Timestamp("2016-01-15"), "2016-01-15", "2016/01/15",
                       "20160115", None, ""])
    got = as_ts_series(mixed)
    _t("DATE-MIX", "혼합 포맷 날짜가 조용히 NaT 이 되지 않는다 (캐시+신규 concat 경로)",
       int(got.notna().sum()) == 4,
       f"유효 {int(got.notna().sum())}/4 (pandas 2.x 는 첫 원소 포맷을 전체에 강제한다)")
    ymd = as_ts_series(pd.Series(["26.01.19", "19.12.31"]).map(parse_kr_date))
    _t("DATE-YY", "두 자리 연도가 연·일 뒤바뀜 없이 해석된다",
       list(ymd.dt.strftime("%Y-%m-%d")) == ["2026-01-19", "2019-12-31"],
       f"{list(ymd.dt.strftime('%Y-%m-%d'))} (자동추론이면 2019-01-26 / 2031-12-19)")

    # ── VAULT: 사용자의 절대 1원칙을 계약으로 강제한다 ────────────────────────────────
    _t(*_vault_integrity_test())

    n_fail = sum(1 for _c, _n, ok, _d in TESTS if not ok)
    LOG.table([[c, _trunc(n, 46), "✔ PASS" if ok else "✘ FAIL", _trunc(d, 34)]
               for c, n, ok, d in TESTS],
              ["ID", "계약", "결과", "실측"], ["c", "l", "c", "l"], maxw=48)
    if n_fail and strict:
        raise RuntimeError(f"계약 검정 {n_fail}건 실패 — 실데이터 수집을 시작하지 않습니다. "
                           f"위 표에서 FAIL 항목을 확인하세요.")
    LOG.ok(f"계약 검정 {len(TESTS) - n_fail}/{len(TESTS)} 통과")
    return n_fail == 0


def _vault_integrity_test() -> Tuple[str, str, bool, str]:
    """★ 절대 1원칙 — 기존 캐시·인덱스를 훼손하지 않는다.

    말이 아니라 실행으로 증명한다: 다른 스키마의 테이블 · uid 없는 레거시 인덱스 · 기존 blob
    이 있는 금고에 대고 **세 번** 새로 실행한 뒤, ① 기존 uid 가 하나도 사라지지 않았는가
    ② 레거시 행이 실행마다 중복되지 않았는가 ③ 기존 blob 파일이 그대로인가 를 확인한다.

    ②가 특히 중요하다. uid 를 '행 위치'로 만들면 저널이 길어질 때마다 같은 레거시 행이 새 uid
    를 받아 인덱스가 매 실행 불어난다. 데이터가 사라지진 않지만 인덱스는 망가지고, 그건
    이 원칙이 막으려던 바로 그 일이다. (실측으로 재현했던 결함)
    """
    global VAULT
    keep = VAULT
    tmp = tempfile.mkdtemp(prefix="tcd_vault_selftest_")
    # 자가검정은 금고를 3회 재적재하므로 정보 로그가 8회쯤 반복된다. 검정 동안만 조용히 한다
    # (경고·오류는 그대로 통과시킨다 — 진짜 문제를 숨기면 안 된다).
    _lvl, LOG.min = LOG.min, LOG.LEVELS["WARN"]
    try:
        V = Vault(tmp, "SELFTEST")
        VAULT = globals()["VAULT"] = V
        V.put_table("krx_ohlcv_daily", pd.DataFrame({"code": ["005930"], "close": [55000]}),
                    scope="shared")
        V.put_blob("research", "report_pdf", "old-1", b"%PDF-1.4 old", "pdf", scope="shared")
        V.flush(); V.compact("shared")
        legacy = os.path.join(V.ns["shared"], "index", "legacy_v1.csv")
        pd.DataFrame({"uid": ["", "", ""], "key": list("abc")}).to_csv(legacy, index=False)
        before = V.load_index("shared", force=True)
        uid0 = set(before["uid"].astype(str))
        blob0 = {os.path.join(r, f) for r, _d, fs in os.walk(V.blob_dir("shared")) for f in fs}

        n_leg = -1
        for run in range(3):
            V2 = Vault(tmp, "SELFTEST")
            VAULT = globals()["VAULT"] = V2
            V2.load_index("shared")
            # 스키마가 다른 새 테이블 + 기존 테이블 교체 + 동일 내용 blob 재기록
            V2.put_table("krx_marketcap_monthly", pd.DataFrame({"code": ["000660"], "mcap": [1e12]}),
                         scope="shared")
            V2.put_table("krx_ohlcv_daily",
                         pd.DataFrame({"code": ["000660"], "close": [95000], "amount": [1e9]}),
                         scope="shared")
            V2.put_blob("research", "report_pdf", "old-1", b"%PDF-1.4 old", "pdf", scope="shared")
            V2.flush(); V2.compact("shared")
            after = V2.load_index("shared", force=True)
            n_leg = int((after.get("_legacy_file", pd.Series(dtype=str)).astype(str)
                         == "legacy_v1.csv").sum())
        lost = uid0 - set(after["uid"].astype(str))
        blob1 = {os.path.join(r, f) for r, _d, fs in os.walk(V2.blob_dir("shared")) for f in fs}
        lost_blob = blob0 - blob1
        has_delete = any(k in dir(V2) for k in ("delete", "remove", "purge", "drop"))
        ok = (not lost) and (not lost_blob) and n_leg == 3 and not has_delete
        return ("VAULT", "기존 캐시·인덱스 훼손 불가 (절대 1원칙 · 3회 재실행)", ok,
                f"uid유실 {len(lost)} · blob유실 {len(lost_blob)} · 레거시행 {n_leg}(기대 3) · "
                f"삭제API {'있음' if has_delete else '없음'}")
    except Exception as e:                                       # noqa
        return ("VAULT", "기존 캐시·인덱스 훼손 불가 (절대 1원칙)", False,
                f"{type(e).__name__}: {str(e)[:60]}")
    finally:
        LOG.min = _lvl
        VAULT = globals()["VAULT"] = keep
        shutil.rmtree(tmp, ignore_errors=True)


def run_smoke(full: bool = False) -> dict:
    """합성 패널로 L2 → L3 → 성과 → 강건성까지 전 출력물을 예행연습한다."""
    LOG.banner("합성데이터 엔드투엔드 스모크",
               "알파가 심어진 패널에서 계산경로가 그 알파를 찾아내는지 확인한다")
    P, sec, months = make_synthetic_panel(n_code=(300 if full else 160),
                                          n_month=(96 if full else 60))
    runner = make_runner(months, sec)
    S = assemble_score(P, stage="M3", quiet=not full)
    bt = run_backtest(S, months, sec, label="SMOKE", quiet=not full)
    s = perf_stats(bt["returns"])
    ok = np.isfinite(s.get("CAGR", np.nan)) and s.get("CAGR", -1) > 0
    LOG.table([[k, (f"{v:+.2%}" if k in ("CAGR", "MDD", "누적수익") and isinstance(v, float)
                    else f"{v:,.3f}" if isinstance(v, float) else str(v))]
               for k, v in s.items()], ["지표", "값"], ["l", "r"],
              title="스모크 성과 (심어놓은 알파를 찾았는가)")
    if not ok:
        LOG.error("합성 패널에 알파를 심어 두었는데도 성과가 나오지 않습니다. "
                  "L2→L3 계산경로가 고장난 것입니다 — 실데이터로 넘어가지 않습니다.")
        raise RuntimeError("스모크 실패: 심어놓은 알파를 계산경로가 찾지 못했습니다.")
    LOG.ok(f"스모크 통과 — 합성 CAGR {s['CAGR']:+.2%} (알파를 심어놨으므로 양수가 정상)")
    if full:
        bench = {}
        report_performance(bt, bench, title="스모크 성과 검증")
        base = R0_baseline(P, months, sec, runner)
        R1_leakage(P, months, sec, runner, bt)
        R2_tp_vs_naive(P, months, sec, runner, bt)
        R3_orthogonal(P, bt, months)
        R5_ablation(P, months, sec, runner, bt)
        R6_pbo()
        R7_regime(bt, {})
        R8_subperiod(bt)
        R9_capacity(P, months, sec, runner, bt)
        R10_policy(P, months, sec, runner, bt)
        report_robustness()
        report_interpretation(S, bt)
        diagnostic_card(S, bt, sec)
        report_stage_matrix()
    return {"panel": S, "backtest": bt, "sec": sec, "months": months}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [22/22]  90_main.py
# ═══════════════════════════════════════════════════════════════════════════════════════════════



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 실행 순서와 산출물                                                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _reband(P: pd.DataFrame, mode: str, lo: float, hi: float) -> pd.DataFrame:
    """유니버스 밴드만 갈아끼운다. L1 재빌드가 필요 없다 — 랭크는 이미 패널에 있다(§3)."""
    Q = P.copy()
    adtv = col(Q, "adv20")
    seasoned = col(Q, "days_listed") >= UNIVERSE_SEASON_DAYS
    live = Q["listed"].astype(bool) if "listed" in Q.columns else pd.Series(True, index=Q.index)
    band = (col(Q, "mcap_pct").between(lo, hi) if mode == "pct"
            else col(Q, "mcap_rank").between(lo, hi))
    Q["u_mid_alt"] = (band.fillna(False) & live & adtv.ge(UNIVERSE_MIN_ADTV).fillna(False)
                      & seasoned.fillna(False))
    return Q


def make_runner(months: pd.DatetimeIndex, sec: pd.DataFrame, stage: str = "M3") -> Callable:
    """L2 + L3 를 한 번 도는 클로저. 강건성 스위트가 이걸 반복 호출한다.

    ★ L1 은 절대 다시 만들지 않는다(§3). 그래서 절제 1회가 수십 초다.
    """
    def runner(P: pd.DataFrame, label: str = "run", signal: str = "Signal_rank",
               floor=True, veto: bool = True, drop_tp: Sequence[str] = (),
               drop_axis: Sequence[str] = (), tp_mode: str = "clip",
               floor_pct: float = BREADTH_FLOOR_PCT, uni: Optional[tuple] = None,
               costs: bool = True, naive_axes: Optional[Sequence[str]] = None,
               use_research: Optional[bool] = None) -> dict:
        Q = P
        entry = "u_mid"
        if uni is not None:
            Q = _reband(Q, *uni)
            entry = "u_mid_alt"
        need_full = (signal == "Signal_rank") or (floor is True)
        if need_full:
            S = assemble_score(Q, stage=stage, tp_mode=tp_mode, drop_tp=drop_tp,
                               drop_axis=drop_axis, floor_pct=floor_pct,
                               use_research=use_research, quiet=True)
        else:
            S = apply_vetoes(Q.copy(), stage=stage, quiet=True)
            S["FLOOR"] = np.int8(1)
            if "Signal" not in S.columns:
                S["Signal"] = 1.0
            if "E" not in S.columns:
                S["E"] = np.nan

        # ── 신호 교체 ───────────────────────────────────────────────────────────────
        if signal == "equal":
            S["Signal"] = 1.0
            S["Signal_rank"] = 1.0
        elif signal == "naive_improve":
            ax = list(naive_axes or [])
            cells = cell_series(S, CELL_KEYS)
            fb = list(CELL_KEYS[:-1])
            parts = [cell_rank(S, col(S, a), CELL_KEYS, fb, tag=f"naive:{a}")
                     for a in ax if a in S.columns]
            if not parts:
                raise RuntimeError("나이브 팔의 축이 하나도 없습니다.")
            base = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
            S["_naive_E"] = base
            er = cell_rank(S, base, ["ym"], ["ym"], min_n=20, tag="naive:E")
            ur = S["U_rank"] if "U_rank" in S.columns else pd.Series(1.0, index=S.index)
            S["Signal"] = (er.astype("float64") * ur.astype("float64")
                           * S["VETO"].astype("float64")).astype("float32")
            S["Signal_rank"] = (S["Signal"].groupby(S["month"], observed=True)
                                .rank(pct=True, method="average").astype("float32"))
        elif signal != "Signal_rank":
            if signal not in S.columns:
                raise RuntimeError(f"신호 컬럼 '{signal}' 이 패널에 없습니다.")
            S["Signal"] = pd.to_numeric(S[signal], errors="coerce").astype("float32")
            S["Signal_rank"] = (S["Signal"].groupby(S["month"], observed=True)
                                .rank(pct=True, method="average").astype("float32"))

        # ── 게이트 교체 ─────────────────────────────────────────────────────────────
        if not veto:
            S["VETO"] = np.int8(1)
        if floor is False:
            S["FLOOR"] = np.int8(1)
        elif floor == "naive":
            # ★ 나이브 팔은 **자기 증거로** 하한선을 만든다. 본선 FLOOR 를 물려주면
            #   나이브 팔조차 TP 로 선별된 종목만 보게 되어 비교 자체가 성립하지 않는다.
            #   축 개수도 맞춘다 — 하한선은 축수에 지수적이다.
            ax = list(naive_axes or [])
            n_groups = max(1, len([g for g, (m, need) in FLOOR_GROUPS.items()
                                   if _stage_ok(need, stage)]))
            chunks = [ax[i::n_groups] for i in range(n_groups)]
            ok = pd.Series(True, index=S.index)
            fb = list(CELL_KEYS[:-1])
            for ch in chunks:
                ch = [c for c in ch if c in S.columns]
                if not ch:
                    continue
                gv = pd.concat([col(S, c) for c in ch], axis=1).mean(axis=1, skipna=True)
                ok &= (cell_rank(S, gv, CELL_KEYS, fb, tag="naive:floor") >= floor_pct).fillna(False)
            S["FLOOR"] = ok.astype("int8")

        # 동일가중 기준선은 '유니버스 전체를 그냥 담는다'는 뜻이므로 종목수 상한을 풀어야 한다.
        # 25종목으로 자르면 그건 동일가중 벤치마크가 아니라 또 하나의 선정 규칙이 된다.
        eq = (signal == "equal")
        bt = run_backtest(S, months, sec, signal_col="Signal_rank",
                          top_pct=(1.0 if eq else PORTFOLIO_TOP_PCT),
                          max_names=(10_000 if eq else PORTFOLIO_MAX_NAMES),
                          apply_costs=costs, label=label, entry_col=entry, quiet=True)
        bt["scored"] = S if label.startswith("MAIN") else None
        return bt
    return runner


# ═══════════════════════════════════════════════════════════════════════════════════════════
def collect_all(months: pd.DatetimeIndex, stage: str) -> dict:
    """L1 수집. 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))

    with PIPE.stage("M0.UNI", "종목 마스터 (다중소스)", "M0", budget_s=600), Stage("M0.universe", 8):
        snaps = fetch_pykrx_snapshots(months)
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps
        ctx["code_of_corp"] = (sec.dropna(subset=["corp_code"])
                                  .assign(corp_code=lambda d: d["corp_code"].astype(str))
                                  .set_index("corp_code")["code"].to_dict())

    with PIPE.stage("M0.PX", "가격 · 거래대금", "M0", budget_s=1500), Stage("M0.price", 20):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        ctx["pp"] = build_price_panel(px, months)

    with PIPE.stage("M0.MCAP", "PIT 시가총액 (C13)", "M0", budget_s=900), Stage("M0.mcap", 8):
        ctx["mcap"] = fetch_pit_marketcap(months, ctx["pp"]["monthly"], ctx["sec"])

    with PIPE.stage("M0.DART", "DART 재무 (벌크 → 폴백)", "M0", budget_s=1800), Stage("M0.dart", 15):
        dis = fetch_dart_disclosures(
            (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"), BACKTEST_END)
        ctx["disclosures"] = dis
        kmap = build_knowledge_map(dis)
        reprts = [REPRT_CODES[k] for k in ("Q1", "H1", "Q3", "FY")]
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        # 유동성 상위 종목의 corp_code 를 우선순위로 넘긴다 — 일일 한도로 끊겨도
        # '투자 가능한 종목의 최근 데이터'가 먼저 완성되게 하기 위함이다.
        prio: List[str] = []
        try:
            adv = (ctx["pp"]["monthly"].groupby("code", observed=True)["adv20"]
                   .median().sort_values(ascending=False))
            c2c = (ctx["sec"].dropna(subset=["corp_code"])
                   .assign(corp_code=lambda d: d["corp_code"].astype(str))
                   .set_index("code")["corp_code"].to_dict())
            prio = [c2c[c] for c in adv.index if c in c2c]
        except Exception:
            prio = []

        # ── §4.1 3단 티어. 정보량 순으로 쌓고, 상위 티어가 없는 조합만 하위가 메운다 ──
        #   Tier1 벌크            : 전 계정 · 1회 다운로드 (최선)
        #   Tier3 fnlttSinglAcntAll: 전 계정 · 단건(며칠 소요, 이어받기)
        #   Tier2 fnlttMultiAcnt  : 주요계정 6개 · 배치(즉시) — '바닥'을 싸게 깐다
        t_bulk = fetch_dart_bulk(years, reprts) if "bulk" not in DISABLED else pd.DataFrame()
        t_multi = fetch_dart_multi(corps, years, reprts)
        t_full = pd.DataFrame()
        if not nonempty(t_bulk):
            LOG.warn("벌크가 비어 Fallback B(fnlttSinglAcntAll)를 가동합니다. 주요계정만으로는 "
                     "재고·매출채권·영업CF가 없어 TP_I2/TP_I4/TP_I1 이 죽기 때문입니다 — "
                     "이 경로 없이 나온 성과는 '코어가 빠진 전략'의 성과입니다.")
            t_full = fetch_dart_full(corps, years, priority=prio)
        raw = merge_financial_tiers(t_bulk, t_full, t_multi)
        ctx["fin"] = tidy_financials(raw, kmap, ctx.get("code_of_corp"))
        ctx["weak_tp"] = report_account_coverage()

    if _stage_ok("M2", stage):
        with PIPE.stage("M2.EMP", "DART 직원현황", "M2", budget_s=2400, critical=False), \
                Stage("M2.employees", 42):
            if "TP_I3" in DISABLED:
                LOG.warn("CANARY K7 실패로 TP_I3 가 비활성화되어 직원현황 수집을 건너뜁니다.")
                ctx["emp"] = pd.DataFrame()
            else:
                corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
                ctx["emp"] = fetch_dart_employees(corps, years, ctx.get("code_of_corp", {}))
    else:
        ctx["emp"] = pd.DataFrame()

    if _stage_ok("M3", stage):
        with PIPE.stage("M3.FLOW", "기관·외국인 수급 (d3)", "M3", budget_s=900, critical=False), \
                Stage("M3.flows", 12):
            if "d3" in DISABLED:
                LOG.warn("CANARY K6 실패로 d3 를 비활성화합니다 — U 는 d1 단독으로 구성됩니다.")
                ctx["flows"] = pd.DataFrame()
            else:
                ctx["flows"] = fetch_investor_flows(ctx["sec"]["code"].tolist(),
                                                    BACKTEST_START, BACKTEST_END)

        with PIPE.stage("M3.RESEARCH", "애널리스트 리포트 · 원장", "M3", budget_s=3600,
                        critical=False), Stage("M3.research", 25):
            ctx.update(collect_research(months, ctx["sec"]))
    else:
        ctx["flows"] = pd.DataFrame()
        ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
        ctx["consensus"] = pd.DataFrame()
    return ctx


def collect_research(months: pd.DatetimeIndex, sec: pd.DataFrame) -> dict:
    """한경컨센서스 · 네이버금융리서치.  드라이브 캐시 우선 → 부족분만 신규 → 재적재."""
    LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
             "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
             "로컬 분석 용도로만 사용하세요(재배포 금지).")
    cached = VAULT.get_table("research_report_master", scope="shared")
    frames = []
    if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
        if "hankyung" in RESEARCH_SOURCES:
            frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
        if "naver" in RESEARCH_SOURCES:
            nv = naver_collect(BACKTEST_START, BACKTEST_END)
            frames.append(naver_enrich_detail(nv))
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 "
                 f"(드라이브에 이미 있는 리포트를 다시 받지 않습니다)")
        frames.append(cached)
    rep = build_report_master(frames, sec)
    if len(rep):
        rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
        if "pdf_target" in rep.columns:
            fill = rep["target_price"].isna() & rep["pdf_target"].notna()
            if fill.any():
                rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
        # ★ 공용(다른 전략 재사용) + 전용(이 전략 시점) 양쪽에 저장한다
        VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                        source="hankyung+naver")
        VAULT.put_table(f"report_master_{STRATEGY_ID}", rep, scope="private",
                        domain="research", source="strategy view")
    A, L = build_analyst_ledger(rep)
    if len(A):
        VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                        source="entity_resolution")
        VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                        source="entity_resolution")
    audit_linkage(rep, A, L)
    cons = build_consensus_panel(L, months)
    return {"reports": rep, "analysts": A, "links": L, "consensus": cons}


def build_L1(ctx: dict, months: pd.DatetimeIndex, stage: str) -> Tuple[pd.DataFrame, "UniverseV3"]:
    with PIPE.stage("L1.PANEL", "L1 피처 패널 (정규화 없음)", "L1", budget_s=900), \
            Stage("L1.panel", 12):
        P = build_base_panel(months, ctx["pp"]["monthly"], ctx["pp"]["daily"],
                             ctx["sec"], ctx.get("mcap"))
        sources = {}
        if len(ctx.get("fin", [])):
            sources["fin"] = ctx["fin"]
        if len(ctx.get("emp", [])):
            sources["emp"] = ctx["emp"][["code", "employees", "payroll", "knowledge_date"]]
        P = build_pit_panel(P, sources)
        assert_c1(P, strict=True)               # ★ 출력 전수 검증 (§4.2)

        uni = UniverseV3(P, ctx["sec"], mode=UNIVERSE_MODE)
        P = uni.resolve_mode(P)
        P = build_cells(P, ctx["sec"])
        P = attach_investor_flows(P, ctx.get("flows"))
        P = build_sensors(P, stage=stage)
        P = build_disclosure_sensors(P, ctx.get("disclosures"), months)
        cons = ctx.get("consensus")
        if cons is not None and len(cons):
            c = cons.rename(columns={"code": "code"}).copy()
            c["month"] = as_ts_series(c["month"])
            c["code"] = c["code"].astype(str)
            P = P.merge(c[["code", "month", "d2_raw", "d4_raw", "n_analyst"]],
                        on=["code", "month"], how="left")
            LOG.ok(f"리서치 축 결합 — d2 {int(P['d2_raw'].notna().sum()):,}행 · "
                   f"d4 {int(P['d4_raw'].notna().sum()):,}행 "
                   f"(USE_RESEARCH_AXIS={USE_RESEARCH_AXIS})")
        for c in ("d2_raw", "d4_raw"):
            if c not in P.columns:
                P[c] = np.nan
        P = downcast(P)
        LOG.ok(f"L1 완성 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB")
        # §3 구현 강제: L1 은 parquet 로 영속화하고 L2 는 이 parquet 만 읽는다
        VAULT.put_table(f"l1_panel_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="L1 sensors (정규화 없음)")
    return P, uni


def main() -> dict:
    t0 = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"TCD v3 · {STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 단계 {STAGE} · 모드 {RUN_MODE} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["시드", str(SEED)],
               ["DART 키", "입력됨" if DART_API_KEY else "❗ 미입력 — 재무 센서 전부 결측"],
               ["KRX 계정", "입력됨" if (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW)
                else "미입력 — PIT 시총이 근사로 대체됩니다(C13 약화)"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")
    report_stage_matrix()

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300), Stage("L0.vault", 3):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        LOG.info(f"공용 인덱스 {GDRIVE_SHARED_NS} (전 전략 재사용) · "
                 f"전용 인덱스 {GDRIVE_PRIVATE_NS} (이 전략) — "
                 f"기존 기록은 append-only 저널이라 훼손 불가입니다.")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간 2GB 미만 — RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        # 설정된 경로 + 플랫폼별 자동 탐지. 손으로 경로를 고치지 않아도 이미 모아둔
        # 리포트를 찾아낸다(읽기 전용 등록 — 이동·삭제 없음).
        adopt = list(dict.fromkeys(list(GDRIVE_ADOPT_DIRS) + discover_drive_dirs(VAULT.root)))
        LOG.info(f"기존 캐시 스캔 대상 {len(adopt)}곳 (설정 {len(GDRIVE_ADOPT_DIRS)} + 자동탐지 "
                 f"{len(adopt) - len(GDRIVE_ADOPT_DIRS)})")
        VAULT.adopt_scan(adopt)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300), Stage("L0.contracts", 2):
        # ★ 반환값을 반드시 확인한다. strict=True 가 내부에서 raise 하는 것에만 의존하면,
        #   리팩터링으로 그 경로가 끊겼을 때(실제로 한 번 그랬다 — 요약/raise 블록이 다른
        #   함수 안으로 딸려 들어가 함수가 None 을 반환했다) 계약이 전부 실패해도 조용히
        #   통과한다. None 은 falsy 이므로 이 검사가 그 유형까지 함께 막는다.
        if not run_contract_tests(strict=True):
            raise RuntimeError("계약 자동검정이 통과를 보고하지 않았습니다 — "
                               "실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.SMOKE", "합성 스모크", "L0", budget_s=1800), Stage("L0.smoke", 3):
        run_smoke(full=(RUN_MODE == "SMOKE"))

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        report_dataflow_map()
        return {"mode": "SMOKE"}

    months = month_range(BACKTEST_START, BACKTEST_END)
    stage = STAGE if STAGE in STAGE_ORDER else "M3"

    # ★ 스테이지 밖에서 초기화한다. 안에서만 대입하면 CANARY 가 예외로 죽었을 때
    #   L0.PERSIST 의 참조가 UnboundLocalError 를 내고, 그러면 '왜 죽었는지'를 담은
    #   산출물 저장 자체가 실패해 진단 정보를 잃는다.
    ctx_canary = pd.DataFrame()
    with PIPE.stage("CANARY", "CANARY K1~K7", "L0", budget_s=1500, critical=False), \
            Stage("CANARY", 20):
        # ★ critical=False. §1 의 설계는 "FAIL 항목에 의존하는 단계를 큐에서 제거하고 진행"
        #   이다. CANARY 가 전체 실행을 죽이면 그 설계와 정면으로 어긋난다.
        #   진짜 중단 사유(K5 상장폐지 미확보)는 KillCriteria 로 별도 전파된다.
        probe_codes, probe_corps = [], []
        try:
            probe_sec = fetch_fdr_listing()
            if nonempty(probe_sec):
                probe_codes = probe_sec["code"].dropna().astype(str).tolist()[:200]
        except Exception as e:                                   # noqa
            LOG.warn(f"CANARY 표본 종목 확보 실패({type(e).__name__}) — 기본 표본으로 진행합니다.")
        try:
            cc = fetch_dart_corpcode()
            if nonempty(cc):
                probe_corps = cc.dropna(subset=["code"])["corp_code"].astype(str).tolist()[:200]
        except Exception as e:                                   # noqa
            LOG.warn(f"CANARY corp_code 확보 실패({type(e).__name__}) — K7 은 건너뜁니다.")
        ctx_canary = run_canary(probe_codes, probe_corps)

    ctx = collect_all(months, stage)
    P, uni = build_L1(ctx, months, stage)
    runner = make_runner(months, ctx["sec"], stage=stage)

    # ── §2 단계별 백테스트 — M0 에서 이미 결과가 나온다 ──────────────────────────────
    results = {}
    bench = benchmark_returns(months)
    for st in STAGE_ORDER:
        if not _stage_ok(st, stage):
            break
        with PIPE.stage(f"{st}.BT", f"백테스트 ({st})", "L3", budget_s=600), Stage(f"{st}.backtest",
                                                                                  STAGE_BUDGET_MIN.get(st)):
            r = make_runner(months, ctx["sec"], stage=st)
            bt = r(P, label=f"MAIN:{st}")
            results[st] = bt
            LOG.rule(f"{st} 백테스트 결과")
            report_performance(bt, bench if st == stage else {}, title=f"성과 검증 ({st})")

    bt = results[stage]
    S = bt.get("scored")
    if S is None:
        S = assemble_score(P, stage=stage, quiet=False)

    with PIPE.stage("L6.PERF", "성과 검증 (최종)", "L6", budget_s=180), Stage("L6.perf", 3):
        report_performance(bt, bench, title="성과 검증 (최종)")
        uni.audit_attrition(P)
        report_cell_fallback()

    with PIPE.stage("R.SUITE", "강건성 R0~R10", "L5", budget_s=4 * 3600, critical=False), \
            Stage("R-SUITE", 45):
        try:
            R0_baseline(P, months, ctx["sec"], runner)
            R1_leakage(P, months, ctx["sec"], runner, bt)
            R2_tp_vs_naive(P, months, ctx["sec"], runner, bt)
            R3_orthogonal(S, bt, months)
            R5_ablation(P, months, ctx["sec"], runner, bt)
            R6_pbo()
            R7_regime(bt, bench)
            R8_subperiod(bt)
            R9_capacity(P, months, ctx["sec"], runner, bt)
            R10_policy(P, months, ctx["sec"], runner, bt)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드", "L6", budget_s=180, critical=False), \
            Stage("L6.report", 3):
        report_interpretation(S, bt)
        card = diagnostic_card(S, bt, ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False), Stage("L0.persist", 5):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []

        def _w(name, df):
            if df is None or not len(df):
                return
            p = os.path.join(outdir, f"{name}_{stamp}.csv")
            df.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)

        _w("returns", bt["returns"])
        _w("holdings", bt["holdings"])
        _w("canary", ctx_canary)
        _w("attrition", uni.attrition)
        _w("runtime", pd.DataFrame(RUNTIME_LOG))
        _w("robustness", pd.DataFrame(ROBUST))
        for st, b in results.items():
            _w(f"backtest_{st}", b["returns"])
        if card:
            p = os.path.join(outdir, f"card_sample_{stamp}.txt")
            atomic_write_text(p, card)
            outs.append(p)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)

        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        S[[c for c in ("code", "month", "E", "U", "Signal", "Signal_rank",
                                       "VETO", "FLOOR", "u_mid") if c in S.columns]],
                        scope="private", domain="scores", source="L2")
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        if DBUDGET:
            DBUDGET.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    report_http()
    report_dataflow_map()
    report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
    LOG.banner("완료", f"총 소요 {(time.time()-t0)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시: ① 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 d1 의 E 는 "
             "후행 12M 이익 대리변수입니다. ② p_cancel 은 미래를 보지 않도록 재정의되어 "
             "원문 정의보다 1년 늦습니다. ③ V5 는 자본잠식만 판정합니다(감사의견 소스 없음). "
             "④ PIT 시총이 근사인 구간에서는 자본이벤트 기업의 밴드 편입이 틀어집니다. "
             "숨기지 않고 여기에 명시합니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "scored": S, "backtest": bt, "stages": results,
            "ctx": ctx, "robust": ROBUST, "canary": ctx_canary}


RESULT: Optional[dict] = None


def _entry():
    global RESULT
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        try:
            report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        report_dataflow_map()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 정확히 이 지점부터 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass


# ★ 노트북(Colab/JupyterLab)에서는 셀 실행이 곧 실행이고, CLI 에서는 __main__ 일 때만 돈다.
#   `import` 로 불러가는 경우에는 자동 실행되지 않는다(TCD_NO_AUTORUN=1 로도 끌 수 있다).
if os.environ.get("TCD_NO_AUTORUN", "") not in ("1", "true", "True"):
    if __name__ == "__main__" or ENV.get("ipython"):
        _entry()
