#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  ARC-AAR — 애널리스트 주의 재배분 (Analyst Attention Reallocation)
#  전략: 애널리스트 주의 재배분 (양방향 현시선호 신호)   [ARC_AAR]
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)
#
#  애널리스트가 '무엇을 말했는가'를 전혀 읽지 않는다. 대신 고정된 주의 예산을 어디에 재배분했는가만 본다. 매도의견이 사실상 0이고 목표주가가 제도적으로 상향 편향된 한국 시장에서, 표명된 의견을 읽는 모든 팩터는 검열된 분포 위에서 작동한다. 주의 배분은 검열되지 않는다. 특히 커버리지 철회를 '인사이동'과 '자발적 철회'로 인과 분해하면, 공매도 제약 아래 관측 가능한 사실상 유일한 음(−) 신호를 얻는다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣거나
#   `python arc_aar_analyst_attention.py` 로 실행하면 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정 → 합성 스모크 → 실경로 리허설
#     [1] Phase 0 데이터 실현가능성 게이트 (애널리스트 식별률 측정 → 진행/폴백 판정)
#     [2] 데이터 수집 (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [3] 원장 무결성 감사 (리포트 ↔ 애널리스트 ↔ 종목 연결)
#     [4] PIT 유니버스 (상장폐지 포함) + 시가총액 PIT 재구성
#     [5] 주의 패널 → 경험적베이즈 축소추정 → 기계적발간 통제회귀 → VAS
#     [6] 커버리지 철회 3분류 (V-DROP / H-EXIT / M-EXIT) + 이벤트 스터디
#     [7] 백테스트 12개 사전등록 구성  ×  유니버스 2종(전체 / 시총하위1000)
#     [8] 성과검증 → 가설검정 H1~H5 (BH-FDR) → 강건성(부트스트랩·PBO·DSR·워크포워드)
#     [9] 해석표 · 최종판정 · 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
#  ⚠ 선행연구 고지: 애널리스트 노력배분·커버리지 종료의 정보성은 선행 문헌이 존재합니다
#    (Kelly & Ljungqvist 2012 커버리지 종료 실험, Merton 1987 투자자 인지 가설 등).
#    이 코드는 "새로운 학술적 발견"이 아니라 그것을 한국시장 횡단면 신호로 조작화하고
#    커버리지 철회를 인사이동 대 자발적 철회로 인과분해한 구현체입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다  (아무것도 안 채워도 실행됩니다)
#
#   키가 없는 데이터원은 자동으로 건너뛰고 "왜 건너뛰었는지"를 한글로 명시합니다.
#   조용히 실패하지 않습니다. 드라이브에 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  (선택 — 있으면 통제회귀가 정확해집니다) ────────────────────────
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료 · 발급 즉시 사용 가능.
#
#    ▶ 이 전략이 DART 를 쓰는 곳은 딱 두 가지뿐입니다:
#        (a) 실적발표월 판정  — §6.3 통제회귀의 EarningsMonth
#        (b) 월별 공시 건수   — §6.3 통제회귀의 DisclosureCount
#      둘 다 "시장 전체를 날짜로 훑는" list.json 스윕으로 얻습니다.
#      재무제표(fnltt*)를 회사별로 받지 않으므로 **10년 콜드빌드에 약 2,000~4,000 호출**이면
#      끝납니다. 일일 한도(2만)의 10~20% 수준이고, 그마저 한 번 받으면 영구 캐시됩니다.
#      (이전 세대 설계가 회사×분기 재무제표를 받느라 한도가 모자랐던 것이지,
#       이 전략의 요구량이 큰 게 아닙니다.)
#
#    ▶ 남은 호출량은 **하드코딩하지 않고 실시간으로 추적**합니다:
#        · 오늘 사용량을 드라이브에 영속 기록하고 재실행 시 이어받습니다
#        · 실제로 status=020(한도초과)이 올 때까지 멈추지 않습니다
#        · 020 이 온 시점의 사용량을 "관측된 실제 한도"로 학습해 다음 실행에 씁니다
#        · 진행 중 잔여량을 로그에 계속 표시합니다
DART_API_KEY = ""

# ── ② KRX 데이터 마켓플레이스 (현재 비활성 — 계정 차단 상태) ─────────────────────────────────
#    가입: https://data.krx.co.kr → 회원가입(무료)
#
#    ⚠ 다른 세션에서 중복 로그인(CD011)으로 계정이 차단된 상태입니다.
#      그래서 이 파이프라인은 **KRX 없이 완결되도록 설계**되었습니다:
#        · PIT 유니버스   ← FDR GitHub 캐시(상장/폐지) + KIND + 가격관측 교차검증
#        · 일별 수정주가  ← FinanceDataReader → 네이버 차트 → yfinance 폴백 체인
#        · 시가총액 PIT   ← FDR 스냅샷 상장주식수 시계열 × 수정종가 (3단 폴백, §10.3)
#      KRX_ENABLED=True 로 바꾸고 ID/PW 를 넣으면 '검증 보조'로만 쓰입니다.
#      의존하지 않으므로 켜지 않아도 결과는 완전합니다.
KRX_ENABLED        = False        # ← 차단 해제 후에만 True 로
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

# ── ③ 구글드라이브 캐시 ─────────────────────────────────────────────────────────────────────
#    ★★★ 절대 1원칙: 기존 캐시·인덱스를 절대 삭제·덮어쓰기하지 않습니다. ★★★
#      · 인덱스의 진실은 append-only JSONL 저널 — 기존 줄을 다시 쓰지 않습니다
#      · index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업
#      · blob 은 내용해시 경로 → 같은 내용은 재기록조차 하지 않음
#      · 이미 있던 파일은 이동·개명 없이 "경로만 등록"(adopt-by-reference)
#      · 삭제 API 자체가 존재하지 않습니다
#
#    GDRIVE_ROOT       : 최상위 캐시 루트
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략도 그대로 재사용 (가격/리포트원장/애널리스트원장)
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유 (주의패널/VAS/신호/백테스트)
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"
GDRIVE_PRIVATE_NS = "arc_aar"

#    ▸ 이미 다른 폴더에 리포트/데이터를 모아두셨다면 여기에 추가하세요.
#      재귀 스캔해서 "등록만" 합니다. 파일을 옮기거나 지우지 않습니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/arc_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ 다른 전략이 쓰던 공용 네임스페이스가 여러 개면 전부 적어두세요. 읽기 전용으로 흡수합니다.
GDRIVE_EXTRA_SHARED_NS = ["_shared", "shared", "common", "_common"]

#    ▸ JupyterLab(로컬)에서 돌릴 때. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
LOCAL_CACHE_ROOT  = "./arc_cache"

# ── ③-b 전면 캐시 정책  ★ 재실행 시간을 극단적으로 줄이는 핵심 ★ ────────────────────────────
#    원칙: **새로 수집·계산되는 모든 것은 예외 없이 캐시에 남고 다음 실행에서 재호출된다.**
#    같은 계열 전략을 여러 번 돌릴 때 같은 일을 두 번 하지 않게 만드는 것이 목적입니다.
#
#    3계층으로 동작합니다:
#      ① HTTP 응답 캐시   — 모든 GET 응답을 내용해시 blob 으로 저장. 같은 URL+파라미터는
#                           네트워크에 나가지 않습니다. 리스트 페이지 스크레이핑이 통째로 사라집니다.
#      ② 원천/정제 테이블 — 공용 인덱스(_shared). 가격·리포트원장·애널리스트원장·공시 등
#                           **다른 전략이 그대로 재사용**합니다.
#      ③ 파생 산출물 메모 — 전용 인덱스(arc_aar). 주의패널·VAS·철회분류·신호·백테스트·CAR 등
#                           입력 지문(fingerprint)이 같으면 계산 자체를 건너뜁니다.
#
#    지문 = sha1(이름 + 관련 설정값 + 입력 데이터 요약). 입력이나 설정이 바뀌면 자동으로
#    새 지문이 되어 재계산되므로, 캐시가 낡아서 틀린 결과를 내는 일은 구조적으로 없습니다.
CACHE_EVERYTHING     = True
MEMO_ENABLED         = True     # 파생 산출물 메모화 (③)
HTTP_CACHE_ENABLED   = True     # HTTP 응답 캐시 (①)
HTTP_CACHE_TTL_DAYS  = {        # 소스별 재검증 주기(일). 0 = 무기한 재사용
    "hankyung": 30.0,           # 과거 구간 리스트는 사실상 불변 → 길게
    "naver":    30.0,
    "dart":     30.0,
    "github":   3.0,            # FDR 상장/폐지 캐시는 매일 갱신되므로 짧게
    "kind":     7.0,
    "kofia":    30.0,
    "generic":  7.0,
}
#    ▸ 과거 구간(오늘로부터 HTTP_CACHE_IMMUTABLE_DAYS 이전에 끝나는 조회)은 TTL 을 무시하고
#      영구 재사용합니다. 2017년 리포트 목록이 지금 와서 바뀔 리는 없기 때문입니다.
HTTP_CACHE_IMMUTABLE_DAYS = 400

# ── ④ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑤ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 6~8 로.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.5,
    "naver":     3.0,
    "kind":      2.0,
    "github":    6.0,
    "kofia":     1.5,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0

# ── ⑥ 애널리스트 리포트 수집 ────────────────────────────────────────────────────────────────
RESEARCH_COLLECT      = True                     # False면 드라이브 캐시만 사용
RESEARCH_SOURCES      = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF = False                    # ★ 이 전략은 PDF 본문이 필요 없습니다.
#   이유: AAR 은 "무엇을 말했는가"를 전혀 읽지 않습니다. (analyst, ticker, date) 메타데이터만
#   쓰므로 PDF 를 받지 않아도 신호가 완전합니다. 한계 데이터 비용이 0에 가깝다는 것이
#   이 전략의 설계상 우위입니다(§0-2). True 로 켜면 애널리스트 식별률 보강에만 쓰입니다.
RESEARCH_PDF_MAX_PER_MONTH = 60                  # PDF 를 켠 경우의 월별 상한 (식별률 보강용 표본)

# ── ⑦ Phase 0 데이터 실현가능성 게이트 (§3) ─────────────────────────────────────────────────
PHASE0_ENABLED      = True
PHASE0_SAMPLE_MONTHS = ["2019-06", "2022-03", "2024-11"]   # 명세 고정 표본
PHASE0_SAMPLE_N      = 300                                  # 월별 표본 건수
PHASE0_PASS          = 0.70     # ≥70% → 정상 진행
PHASE0_DEGRADE       = 0.40     # 40~70% → 진행 + 결측 민감도 분석 필수 / <40% → 하우스 단위 폴백
PHASE0_HALT_ON_FAIL  = False    # True 면 Phase 0 결과 보고 후 중단(명세 §12-1의 '승인 대기')

# ── ⑧ 포트폴리오 (§7 — 사전 고정. 드로다운 한가운데서 정하지 않습니다) ───────────────────────
PORT_QUANTILES      = 5         # 신호 5분위
PORT_MIN_NAMES      = 20        # 보유 종목 하한. 미달 시 현금 처리 + 로그
POS_MAX_WEIGHT      = 0.05      # 종목당 상한 5%
NEG_EXCLUDE_PCT     = 0.10      # AAR_neg 하위 10% 강제 배제
MIN_ADV_KRW         = 100_000_000    # 유동성 하한(20일 평균거래대금). 소형주 전략이라 낮게.
ACCOUNT_KRW         = 100_000_000    # 슬리피지·용량 계산용 가정 계좌

# ── ⑨ 거래비용 (§7.1) ───────────────────────────────────────────────────────────────────────
COMMISSION_BPS      = 1.5       # 편도 수수료
SLIPPAGE_BPS        = {"large": 10.0, "mid": 20.0, "small": 35.0}
#   증권거래세 연도별 테이블 — 단일 세율 금지(§7.1). 출처:
#   기획재정부 증권거래세법 시행령 개정 이력 / https://www.law.go.kr (증권거래세법 시행령 §5)
#   KOSPI 는 농어촌특별세 0.15% 포함 총부담 기준, KOSDAQ 은 증권거래세 단일.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.00300, "KOSDAQ": 0.00300, "KONEX": 0.00300, "OTHER": 0.00300}),
    ("2019-06-03", {"KOSPI": 0.00250, "KOSDAQ": 0.00250, "KONEX": 0.00100, "OTHER": 0.00250}),
    ("2021-01-01", {"KOSPI": 0.00230, "KOSDAQ": 0.00230, "KONEX": 0.00100, "OTHER": 0.00230}),
    ("2023-01-01", {"KOSPI": 0.00200, "KOSDAQ": 0.00200, "KONEX": 0.00100, "OTHER": 0.00200}),
    ("2024-01-01", {"KOSPI": 0.00180, "KOSDAQ": 0.00180, "KONEX": 0.00100, "OTHER": 0.00180}),
    ("2025-01-01", {"KOSPI": 0.00150, "KOSDAQ": 0.00150, "KONEX": 0.00100, "OTHER": 0.00150}),
]
COST_SCENARIOS = {"무비용": 0.0, "기본": 1.0, "2배": 2.0}      # §7.1 — 3종 전부 보고

# ── ⑩ 유니버스 변형 (비교 백테스트) ─────────────────────────────────────────────────────────
#    "FULL"       : PIT 전체 상장 유니버스 (상장폐지 포함)
#    "SMALL1000"  : 매월 시가총액 하위 1000 종목으로 압축한 비교 전략
#    두 변형 각각 백테스트 → 성과검증 → 강건성 → 해석표를 출력하고 마지막에 비교표를 냅니다.
UNIVERSE_VARIANTS   = ["FULL", "SMALL1000"]
SMALLCAP_N          = 1000

# ── ⑪ 사전등록 파라미터 격자 (§6.6 — 총 12개. 확장 금지) ────────────────────────────────────
#    3 (가중방식) × 2 (λ) × 2 (보유기간) = 12
GRID_WEIGHTS  = ["uw", "nreports", "ncover"]    # 비가중 / 발간량 / 커버리지폭
GRID_LAMBDA   = [0.0, 1.0]                      # 음의 신호 결합계수
GRID_HOLD     = [1, 3]                          # 보유기간(개월)
#    ↓ 아래 3개는 명세상 **고정값이며 튜닝 대상이 아닙니다**. 바꾸면 사전등록 위반입니다.
LOOKBACK_M       = 12      # 베이스라인 룩백 개월
MIN_REPORTS_MON  = 3       # N(a,t) < 3 이면 결측
MIN_LOOKBACK_N   = 12      # 룩백 합계 < 12 이면 결측
NEG_W_VDROP      = 1.0     # AAR_neg 가중 (사전 고정)
NEG_W_HEXIT      = 1.5     # AAR_neg 가중 (사전 고정)
COVER_WINDOW_M   = 12      # 커버 상태 판정 창(개월) — 직전 4개 분기 = 12개월
FDR_Q            = 0.10    # BH-FDR q

# ── ⑫ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE"  : 합성데이터로 전 출력물 예행연습 (수십 초). 네트워크/키 불필요. 처음엔 이걸로.
#    "FULL"   : 스모크 → 리허설 → 실데이터 수집 → 전체 (기본값)
#    "CACHED" : 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 전체
RUN_MODE = "FULL"

SEED    = 20260808        # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True     # §11 KILL 기준 위반 시 즉시 중단하고 보고 (끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "ARC_AAR"
STRATEGY_NAME = "애널리스트 주의 재배분 (양방향 현시선호 신호)"
BUILD_VERSION = "aar.20260808.0903"


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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-B  커널 — 로깅 / 스테이지 / 데이터흐름 원장 / 에러 국소화 / 런타임 계측                ║
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
            line = pre + ch * max(0, width - _dw(pre))
        else:
            line = ch * width
        with self.lock:
            self.buffer.append(line)
        _safe_print(line, flush=True)

    def banner(self, title: str, sub: str = "", width: int = 104):
        lines = ["", "╔" + "═" * (width - 2) + "╗",
                 "║ " + _pad(_trunc(title, width - 4), width - 4) + " ║"]
        if sub:
            lines.append("║ " + _pad(_trunc(sub, width - 4), width - 4) + " ║")
        lines.append("╚" + "═" * (width - 2) + "╝")
        with self.lock:
            self.buffer.extend(lines)
        for ln in lines:
            _safe_print(ln, flush=True)

    def table(self, rows: List[Sequence[Any]], headers: Sequence[str],
              aligns: Optional[Sequence[str]] = None, maxw: int = 46, title: str = ""):
        """한글 폭 보정 표. 강건성/성과/감사 출력 전부 이걸 쓴다."""
        out: List[str] = []
        if title:
            out.append(f"\n▶ {title}")
        if not rows:
            out.append("   (행 없음)")
        else:
            ncol = len(headers)
            al = list(aligns or ["l"] * ncol)
            al += ["l"] * (ncol - len(al))
            cells = [[_trunc("" if c is None else c, maxw) for c in r] + [""] * (ncol - len(r))
                     for r in rows]
            widths = [max([_dw(headers[i])] + [_dw(r[i]) for r in cells]) for i in range(ncol)]
            out.append("  " + " │ ".join(_pad(headers[i], widths[i], "c") for i in range(ncol)))
            out.append("  " + "─┼─".join("─" * widths[i] for i in range(ncol)))
            for r in cells:
                out.append("  " + " │ ".join(_pad(r[i], widths[i], al[i]) for i in range(ncol)))
        with self.lock:
            self.buffer.extend(out)
        for ln in out:
            _safe_print(ln, flush=True)


LOG = _Log("DEBUG" if VERBOSE else "INFO")


# ── 데이터 흐름 원장 ────────────────────────────────────────────────────────────────────────
@dataclass
class IOEvent:
    stage: str
    direction: str          # IN / OUT
    kind: str               # HTTP / DRIVE / PARQUET / MEM / SHARD / SYNTH
    name: str
    rows: int = -1
    cols: int = -1
    bytes_: int = -1
    source: str = ""
    ok: bool = True
    note: str = ""
    pit_cols: str = ""      # knowledge_date 계열 컬럼 존재 여부 — PIT 감사에 쓴다


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
    """§11 KILL 기준 위반. 우회하지 말고 사용자에게 보고하고 멈춘다."""


class StageFailure(Exception):
    pass


# ── 예외 → 한글 진단 힌트 ───────────────────────────────────────────────────────────────────
_DIAG_RULES: List[Tuple[str, str]] = [
    (r"dart.*(020|021)|LIMITED_NUMBER_OF_SERVICE|요청 제한",
     "DART 일일 호출한도 초과입니다. 이 전략은 실적발표일·공시건수만 받으므로 총 2~4천 호출이면 "
     "충분한데, 같은 키를 다른 작업과 공유했다면 소진될 수 있습니다. 받은 만큼 드라이브에 "
     "저장돼 있으니 내일 재실행하면 정확히 이어받습니다. 통제회귀는 결측 통제변수를 제외하고 "
     "진행되며 그 사실이 로그에 명시됩니다."),
    (r"opendart|dart.*(01[0-4]|100|800|900)|status.*'0(1[0-4])'",
     "DART API 응답 코드 오류. 010/011=키 문제, 012=IP 차단, 013=조회 데이터 없음(정상일 수 있음), "
     "800=시스템 점검, 900=정의되지 않은 오류. DART_API_KEY 를 확인하세요. "
     "DART 없이도 파이프라인은 동작합니다(통제변수만 축소)."),
    (r"HTTPError.*40[13]|Forbidden|403",
     "403 차단입니다. RATE_LIMIT_QPS 를 절반으로 낮추고 N_WORKERS_IO 를 6 이하로 줄이세요. "
     "네이버/한경은 User-Agent 와 Referer 헤더가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests",
     "요청이 너무 빠릅니다. RATE_LIMIT_QPS 를 낮추세요. 지수백오프로 재시도하지만 한계가 있습니다."),
    (r"ConnectionError|Timeout|Max retries|NameResolution|SSLError|ProxyError",
     "네트워크 도달 실패입니다. 방화벽/프록시 환경이면 해당 도메인이 막혀 있을 수 있습니다. "
     "RUN_MODE='CACHED' 로 두면 드라이브 캐시만으로 백테스트할 수 있습니다."),
    (r"No such file or directory.*drive|MyDrive|drive/MyDrive",
     "구글드라이브가 마운트되지 않았습니다. Colab이면 셀 실행 시 뜨는 인증 팝업을 승인하세요. "
     "JupyterLab이면 자동으로 LOCAL_CACHE_ROOT 를 사용합니다(정상)."),
    (r"No space left on device|Disk quota",
     "디스크/드라이브 용량 부족입니다. RESEARCH_DOWNLOAD_PDF=False(기본값)이면 PDF 를 받지 "
     "않으므로 용량은 대부분 가격 샤드가 차지합니다. 가격 샤드는 연도별로 분할되어 있어 "
     "오래된 연도를 다른 폴더로 옮겨도 매니페스트가 자동으로 재수집을 판단합니다."),
    (r"Can't pickle|pickle.*__main__|PicklingError|BrokenProcessPool",
     "프로세스 병렬화 실패(노트북의 고질적 문제). 코드가 자동으로 스레드 병렬로 폴백합니다. "
     "성능만 떨어지고 결과는 동일합니다."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족입니다. 주의 패널(애널리스트×종목×월)이 가장 큰 객체입니다. "
     "MEM_BUDGET_GB 를 낮추면 통제회귀가 청크 모드로 전환됩니다. 패널은 이미 float32/category 로 "
     "축소되어 있으며, 가격은 연도 샤드로 나눠 필요한 구간만 읽습니다."),
    (r"pyarrow|parquet|ArrowInvalid|ArrowIOError|ArrowNotImplementedError",
     "parquet 읽기/쓰기 실패입니다. 드라이브 FUSE 마운트에서 쓰기가 중단되면 파일이 깨질 수 "
     "있습니다. 이 코드는 임시파일→원자적 rename 으로 쓰므로 깨진 건 이전 실행 잔재입니다. "
     "코드가 자동으로 .corrupt 로 격리하고 재생성합니다(원본 삭제 안 함)."),
    (r"'DataFrame' object has no attribute 'name'|_wrap_agged_manager",
     "중복 컬럼입니다. DataFrame 에 같은 이름의 컬럼이 두 개 있으면 df[col] 이 Series 가 아니라 "
     "DataFrame 이 되고, groupby(...).agg() 가 pandas 내부에서 이 예외로 터집니다. "
     "직전에 concat/reindex(columns=...)/merge 로 컬럼을 합친 곳을 보세요. "
     "assert_no_dup_cols() 로 발생 지점을 앞당겨 잡을 수 있습니다."),
    (r"Expecting value: line \d+ column 1|JSONDecodeError",
     "JSON 대신 HTML(대개 로그인/에러 페이지)을 받았습니다. 이 전략은 KRX 인증 경로를 쓰지 "
     "않으므로, 네이버 JSON API 스키마 변경이거나 일시 차단일 가능성이 큽니다. "
     "HTML 리스트 폴백이 자동으로 동작합니다."),
    (r"UnicodeEncodeError|cp949|charmap",
     "콘솔 인코딩 문제입니다(윈도우 기본 cp949 는 罫線문자 ╔═║ 와 ✔✘ 를 못 씁니다). "
     "코드가 stdout 을 UTF-8 로 재설정하고 실패 시 ASCII 로 낮춥니다. 직접 출력을 추가했다면 "
     "print 대신 _safe_print 를 쓰세요. 또는 실행 전 `chcp 65001`."),
    (r"KeyError: 'knowledge_date'|knowledge_date",
     "PIT 컬럼 누락입니다. 모든 테이블은 event_date/knowledge_date 를 가져야 합니다. "
     "새 수집 함수를 추가했다면 pit_frame() 으로 감싸주세요."),
    (r"dtype.*object|is_string_dtype|StringDtype|astype\(str\)",
     "pandas 3.0 문자열 dtype 문제일 가능성이 큽니다. pandas 3 에서 문자열 컬럼은 object 가 "
     "아니라 str dtype 이므로 `df[c].dtype == object` 가 조용히 False 가 됩니다. "
     "is_texty()/text_cols()/as_str_series() 를 쓰세요."),
    (r"empty|EmptyDataError|No objects to concatenate|zero-size|attempt to get argmax",
     "수집 결과가 비었습니다. 대개 ① 조회구간에 데이터 없음 ② 소스 구조 변경 ③ 차단입니다. "
     "바로 위 FLOW 원장에서 어느 소스가 0행을 반환했는지 확인하세요."),
    (r"ModuleNotFoundError|ImportError",
     "패키지 누락입니다. 위 부트스트랩 로그에서 어떤 설치가 실패했는지 확인하고 수동 설치하세요."),
    (r"tz-aware|tz-naive|Cannot compare|Cannot subtract",
     "타임존이 섞인 날짜 비교입니다. 이 코드는 모든 날짜를 tz-naive Timestamp 로 정규화합니다"
     "(as_ts). 새로 추가한 소스가 tz-aware 를 반환했을 가능성이 큽니다."),
    (r"singular matrix|LinAlgError|SVD did not converge",
     "회귀 설계행렬이 특이합니다. 통제변수 중 하나가 상수이거나 완전공선일 때 발생합니다 "
     "(예: 표본 구간에 실적발표월이 하나도 없어 EarningsMonth 가 전부 0). "
     "코드가 상수/공선 열을 자동 제거하고 재시도하지만, 제거 후 남는 열이 없으면 "
     "그 통제는 '적용 불가'로 보고됩니다."),
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
            elif isinstance(obj, (int, float)) and np.isfinite(obj):
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
            LOG.ctx.pop()
            self.current = prev
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
                LOG.warn(msg + f"  ← 예산 {budget_s:.0f}s 초과")
            else:
                LOG.ok(msg)
        except KillCriteria as e:
            rec.t_end = time.time(); rec.status = "FAIL"
            rec.err_type = "KillCriteria"; rec.err_msg = str(e)
            rec.err_tb = traceback.format_exc()
            rec.hint = "§11 KILL 기준입니다. 파라미터를 조정해 통과시키지 마세요. 그대로 보고합니다."
            self.failed.append(sid)
            LOG.error(f"KILL 기준 발동 — {e}")
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
        LOG.banner("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수 · 런타임 예산")
        rows = []
        for r in self.stages.values():
            icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUNNING": "…"}.get(r.status, "?")
            bud = "-" if r.budget_s is None else (f"{r.budget_s:.0f}s" + ("❗" if r.dur > r.budget_s else ""))
            rows.append([r.layer, r.sid, _trunc(r.name, 40), f"{icon}{r.status}",
                         f"{r.dur:8.2f}", f"{r.rows_in:,}", f"{r.rows_out:,}", bud,
                         _trunc("; ".join(r.notes), 40)])
        LOG.table(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "예산", "비고"],
                  ["c", "l", "l", "c", "r", "r", "r", "c", "l"], maxw=44)

    def report_flow(self, only_kinds: Optional[Sequence[str]] = None, limit: int = 220):
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
        """§8.1 런타임 감사 — 추측하지 말고 측정한다."""
        LOG.banner("런타임 감사 (§8.1)", "계층별 실측 소요시간 vs 계약 예산 (합계 ≤ 250분)")
        budgets = {"L0": 20 * 60, "L1": 150 * 60, "L2": 35 * 60, "L3": 20 * 60,
                   "L5": 25 * 60, "L6": 10 * 60}
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
        tot = sum(agg.values())
        rows.append(["합계", f"{tot:8.2f}s", f"{tot / 60:6.2f}분", "250분",
                     "✔ 예산 내" if tot <= 250 * 60 else "❗ 초과 — 캐시 적중 여부를 먼저 보세요"])
        LOG.table(rows, ["계층", "실측(초)", "실측(분)", "계약예산", "판정"], ["c", "r", "r", "r", "l"])
        LOG.info("계층 — L0:부트/캐시  L1:수집  L2:주의패널·VAS  L3:백테스트  L5:검정  L6:리포트")
        LOG.info("캐시 히트 재실행 목표 ≤ 40분. 초과하면 가격 샤드 매니페스트나 리포트 원장 캐시가 "
                 "적중하지 못하고 있다는 뜻입니다 — 위 FLOW 원장에서 DRIVE 입력 행수를 확인하세요.")


PIPE = Pipeline()


def assert_no_dup_cols(df: "pd.DataFrame", where: str) -> "pd.DataFrame":
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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 날짜/해시/원자적IO/레이트리미터/병렬/횡단면통계                              ║
# ║         + 이 전략의 두 핵심 수치 커널:                                                    ║
# ║           ① eb_shrink()  경험적 베이즈 계층 축소추정 (§6.2 — 비축소 결과 단독보고 금지)   ║
# ║           ② absorb_fe()  고차원 양방향 고정효과 흡수 회귀 (§6.3 — 통제 없는 원신호 무효)  ║
# ║                                                                                          ║
# ║  ★ 성능 원칙: 종목/애널리스트별 파이썬 루프 금지. 전부 groupby-네이티브 또는 bincount.     ║
# ║    실측 — 200만 행 × 양방향 FE 10회 반복이 0.6초. 루프로 짜면 같은 일이 수십 분이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 정규화 ─────────────────────────────────────────────────────────────────────────────
KST = "Asia/Seoul"


def as_ts(x) -> Optional["pd.Timestamp"]:
    """무엇이 들어오든 **KST 기준** tz-naive 로 정규화된 Timestamp.

    ★ 여기서 tz_convert(None) 을 쓰면 안 된다. 그건 UTC 로 변환한 뒤 tz 를 떼는 것이라
      KST 09:00 이전 시각이 **전날로 밀린다**(실측: 2020-01-15 08:00 KST → 2020-01-14).
      그 값이 knowledge_date 에 들어가면 하루 앞선 정보를 쓴 것이 되어 PIT 를 정면 위반한다.
      게다가 as_ts_series 는 tz_localize(None)(로컬 보존)이라 두 함수가 하루 다른 값을 냈다.
      한국 시장 데이터이므로 **로컬 벽시계 시각(KST)** 이 유일하게 옳은 기준이다."""
    if x is None:
        return None
    if isinstance(x, float) and not np.isfinite(x):
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
        try:
            t = t.tz_convert(KST).tz_localize(None)
        except Exception:
            try:
                t = t.tz_localize(None)
            except Exception:
                return None
    return t.normalize()


def as_ts_series(s) -> "pd.Series":
    """열 단위 날짜 정규화 — as_ts 와 **정확히 같은 규약**(KST 벽시계, 자정 정렬, ns).

    ★ pandas 3 은 parquet 왕복에서 datetime64[us] 를 돌려준다. us 와 ns 를 섞으면
      merge_asof 가 MergeError 로 하드 실패하므로 여기서 단위를 통일한다.
    ★ tz 가 섞인 열은 utc=True 없이는 ValueError 를 내는데, 전역 warnings 억제 때문에
      사전 경고조차 보이지 않는다. 혼재를 먼저 흡수한 뒤 KST 로 되돌린다."""
    ser = pd.Series(s)
    filled = ser.notna()
    try:
        out = pd.to_datetime(ser, errors="coerce")
    except Exception:
        out = pd.to_datetime(ser, errors="coerce", utc=True)
    tz = getattr(getattr(out, "dt", None), "tz", None)
    if tz is not None:
        # ★ 여기가 조용한 데이터 유실 지점이다. tz-aware 와 naive 가 섞인 열을
        #   pd.to_datetime 에 그냥 넣으면 **예외 없이** tz-aware dtype 이 되고
        #   naive 원소는 전부 NaT 로 사라진다(pandas 3 실측). 리포트 발간일이 이렇게
        #   사라지면 그 달의 주의 배분이 통째로 비는데 로그에는 아무것도 안 남는다.
        lost = filled & out.isna()
        out = out.dt.tz_convert(KST).dt.tz_localize(None)
        if bool(lost.any()):
            # naive 원소는 '이미 KST 벽시계'다. utc=True 로 재파싱하면 +9시간 밀린다.
            naive = pd.to_datetime(ser.where(lost), errors="coerce")
            if getattr(getattr(naive, "dt", None), "tz", None) is not None:
                naive = naive.dt.tz_convert(KST).dt.tz_localize(None)
            out = out.where(~lost, naive)
    try:
        out = out.astype("datetime64[ns]")
    except Exception:
        pass
    return out.dt.normalize()


def month_end(x) -> Optional["pd.Timestamp"]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> "pd.DatetimeIndex":
    return pd.date_range(month_end(start), month_end(end), freq="ME")


def add_months(t, k: int):
    return (as_ts(t) + pd.DateOffset(months=k) + pd.offsets.MonthEnd(0)).normalize()


# ── 해시 / 식별자 ───────────────────────────────────────────────────────────────────────────
def sha1_str(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def norm_text(s: Any) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("​", "").replace("\xa0", " ")
    s = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", s)
    s = re.sub(r"[^\w가-힣A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_corp_name(s: Any) -> str:
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
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드. 실패하면 None.
    조용히 0으로 채워 잘못된 종목을 만들지 않는다."""
    if x is None:
        return None
    if isinstance(x, float) and not np.isfinite(x):
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
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def _parquet_safe_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """arrow 가 거부하는 혼합형 object 컬럼만 문자열화한다.
    ★ pandas 3 은 문자열이 str dtype 이라 `dtype == object` 로는 못 찾는다 — kind 로 본다."""
    out = df.copy()
    for c in out.columns:
        if getattr(out[c].dtype, "kind", "") != "O":
            continue
        try:
            kind = pd.api.types.infer_dtype(out[c], skipna=True)
        except Exception:
            kind = "mixed"
        if kind not in ("string", "empty", "unicode"):
            out[c] = as_str_series(out[c])
    return out


def atomic_write_parquet(df: "pd.DataFrame", path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = _parquet_safe_frame(df)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        try:
            out.to_parquet(tmp, index=False, compression="snappy")
        except Exception:
            out.astype({c: str for c in text_cols(out)}).to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str, columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path, columns=list(columns) if columns else None)
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
            d = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(
                RATE_LIMIT_QPS.get(source, RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]


class CircuitBreaker:
    """§2.3 서킷 브레이커 — 연속 실패 N회면 즉시 중단하고 상태를 남긴다.
    차단당한 채로 수천 번 더 두드리는 것이 계정 정지로 가는 가장 빠른 길이다."""

    def __init__(self, name: str, threshold: int = 10):
        self.name, self.threshold = name, threshold
        self.streak = 0
        self.tripped = False
        self.total_fail = 0
        self._lk = threading.Lock()

    def ok(self):
        with self._lk:
            self.streak = 0

    def fail(self) -> bool:
        with self._lk:
            self.streak += 1
            self.total_fail += 1
            if self.streak >= self.threshold and not self.tripped:
                self.tripped = True
                LOG.error(f"서킷 브레이커 작동 [{self.name}] — 연속 실패 {self.streak}회. "
                          f"이 소스의 수집을 즉시 중단합니다. 지금까지 받은 분량은 드라이브에 "
                          f"저장되며 재실행 시 이어받습니다. 차단 상태로 계속 두드리면 "
                          f"복구가 더 늦어집니다.")
            return self.tripped


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
            desc: str = "", quiet: bool = False,
            breaker: Optional[CircuitBreaker] = None) -> List[Any]:
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
                if breaker is not None:
                    (breaker.ok() if out[i] is not None else breaker.fail())
            except Exception as e:                       # noqa
                errs[type(e).__name__] += 1
                out[i] = None
                if breaker is not None and breaker.fail():
                    for f2 in futs:
                        f2.cancel()
                    break
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
def downcast(df: "pd.DataFrame", cat_thresh: float = 0.35) -> "pd.DataFrame":
    """float64→float32, 저카디널리티 문자열→category. 패널 RAM 을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = getattr(df[c].dtype, "kind", "")
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
        elif k == "O" and is_texty(df[c]):
            try:
                n = df[c].nunique(dropna=True)
                if n > 0 and n / max(len(df), 1) < cat_thresh:
                    df[c] = df[c].astype("category")
            except Exception:
                pass
    return df


def mem_mb(df: "pd.DataFrame") -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        try:
            return shutil.disk_usage(path).free / 1e9
        except Exception:
            return float("nan")


# ── PIT 프레임 강제 ─────────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")


def _resolve_dates(df: "pd.DataFrame", arg) -> "pd.Series":
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


def pit_frame(df: "pd.DataFrame", event_date, knowledge_date, source: str = "") -> "pd.DataFrame":
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


# ── 안전 접근자 ─────────────────────────────────────────────────────────────────────────────
def col(df: "pd.DataFrame", name: str, default: float = np.nan) -> "pd.Series":
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자.

    ★ df.get("x") 는 컬럼이 없으면 None 을 반환한다. 그러면 `None + Series` 로 TypeError 가
      나는데, 하필 그 상황(= 특정 데이터 소스가 통째로 비어 해당 컬럼이 생성되지 않은 경우)이
      실데이터 실행에서 가장 흔하다. 키 미입력·API 한도 소진·소급 데이터 없음 전부 이 경로다."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


# ── 횡단면 통계 (winsorize → z / rank) ──────────────────────────────────────────────────────
WINSOR_SIGMA = 3.0        # 주의 잔차는 꼬리가 두껍다. ±3σ 로 자른다(사전 고정).
CELL_MIN_N = 10


def xsec_z(values, cells, min_n: int = CELL_MIN_N, k: Optional[float] = WINSOR_SIGMA) -> "pd.Series":
    """winsorize(±kσ) → 셀 내 z-score. 순서는 여기서만 정의되고 파라미터화하지 않는다.

    ★ k=None 이면 윈저라이즈를 건너뛴다. AAR_neg 처럼 **구조적으로 유계인** 지표에는
      윈저라이즈가 해롭다: 90% 이상이 정확히 0인 점질량 분포에서 ±3σ 절단선이
      극단 철회 사건 5건을 단일값 하나로 붕괴시킨다(실측 z: -7.86/-7.63/-7.57/-7.12/-5.87
      → 전부 -4.415). 이 신호가 존재하는 이유인 사건을 정확히 지우는 셈이다.

    구현 주의 두 가지:
     ① ±inf 를 반드시 먼저 NaN 으로 바꾼다. np.nanmean 은 NaN 은 무시하지만 inf 는 무시하지
        않으므로, 셀에 inf 가 단 하나만 있어도 평균이 inf·표준편차가 NaN 이 되어
        **그 셀 전체의 z-score 가 0으로 뭉개진다.** 비율 지표에서 흔히 발생한다.
     ② groupby.transform(파이썬 UDF) 대신 네이티브 집계로 벡터화한다.
        수십만 행 × 수천 셀에서 UDF 경로는 호출당 10초 이상이고, 이 함수는 수십 번 불린다.
    """
    v = pd.to_numeric(pd.Series(values).reset_index(drop=True), errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = as_str_series(pd.Series(cells).reset_index(drop=True)).replace("", "__NA__").to_numpy()

    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    if k is None:
        w = v                                                     # ① 윈저라이즈 생략
    else:
        mu0 = g.transform("mean")
        sd0 = g.transform("std", ddof=0)
        w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)      # ① winsorize

    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)                               # ② z-score
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)            # 셀 내 전원 동일값 → 0
    out = z.where(cnt >= min_n).astype("float32")
    out.index = pd.Series(values).index
    return out


def xsec_rank_pct(values, cells, min_n: int = CELL_MIN_N) -> "pd.Series":
    """셀 내 백분위 랭크 [0,1]. 표본 부족 셀은 NaN (0으로 채우지 않는다)."""
    v = pd.to_numeric(pd.Series(values).reset_index(drop=True), errors="coerce").astype("float64")
    v = v.replace([np.inf, -np.inf], np.nan)
    grp = as_str_series(pd.Series(cells).reset_index(drop=True)).replace("", "__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    r = g.rank(pct=True, method="average")
    out = r.where(cnt >= min_n).astype("float32")
    out.index = pd.Series(values).index
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  수치 커널 ①  경험적 베이즈 계층 축소추정  (§6.2)                                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def ea_analytic_var(r_t, N_t, r_lb, N_lb) -> "pd.Series":
    """EA 의 표본분산 — **닫힌형**. MoM 으로 추정할 필요가 없다.

    EA = share − base 는 두 이항비율의 차이다:
        share ~ Bin(N_t, p)/N_t,  base ~ Bin(N_lb, p)/N_lb   (독립)
        Var(EA) = p(1-p)·(1/N_t + 1/N_lb)

    ★ p 는 반드시 **풀링 비율** (r_t+r_lb)/(N_t+N_lb) 를 쓴다. share 를 쓰면
      커버를 끊은 관측(share=0)의 분산이 0 이 되어 '무한 정밀 관측'으로 오판되고,
      축소추정이 그 관측을 전혀 줄이지 않는다 — 정확히 우리가 잡으려는 사건들이다.
    검증: 해석적 mean(v)=6.2007e-03 vs 실측 Var(EA−θ)=6.1666e-03 (비율 1.006).
    """
    rt = pd.to_numeric(pd.Series(r_t), errors="coerce").astype("float64")
    nt = pd.to_numeric(pd.Series(N_t), errors="coerce").astype("float64")
    rl = pd.to_numeric(pd.Series(r_lb), errors="coerce").astype("float64")
    nl = pd.to_numeric(pd.Series(N_lb), errors="coerce").astype("float64")
    p = (rt + rl) / (nt + nl).where((nt + nl) > 0)
    p = p.clip(0.0, 1.0)
    v = p * (1.0 - p) * (1.0 / nt.where(nt > 0) + 1.0 / nl.where(nl > 0))
    # 분산 0(=p가 정확히 0 또는 1)은 수치적으로 위험하다. 관측 1건 분해능을 하한으로 둔다.
    floor = (1.0 / nt.where(nt > 0)) ** 2 * 0.25
    return v.fillna(np.nan).clip(lower=floor).astype("float64")


def eb_shrink_tau2(df: "pd.DataFrame", unit: str, house: str, sector: str,
                   ea: str = "EA", var: str = "v") -> Tuple["pd.Series", "pd.Series", "pd.DataFrame"]:
    """경험적 베이즈 3단 계층 축소 — **위치가 아니라 분산(tau²)에 계층을 건다.**

    왜 평균 계층이 무효인가: share 는 애널리스트-월 안에서 합이 1 이고 base 도 그러므로
    **EA 는 애널리스트-월마다 합이 정확히 0** 이다(영합 제약, 실측 |ΣEA| < 1e-12).
    따라서 모든 레벨의 사전평균이 0 이고, 평균을 향해 축소하는 3단 사다리는
    같은 상수(0)를 세 번 향하는 무동작이 된다. 계층이 실제로 정보를 나르는 곳은
    **각 애널리스트의 신호 강도 tau² = Var(θ)** 다.

    모형:  EA = θ + e,  e ~ N(0, v)  (v 는 해석적, ea_analytic_var),  θ ~ N(0, tau²_unit)
    추정:  tau2_raw = E[EA²] − mean(v)                      (사전평균 0이므로 성립)
           V(tau2_raw) = 2(tau2_raw + v̄)² / n              (카이제곱 적률의 분산)
           섹터 ← 전역, 증권사 ← 섹터, 애널 ← 증권사 순으로 정밀도 가중 축소
    결과:  w = tau² / (tau² + v),   EA_shrunk = w · EA      (절편 없음 — 0을 향한 축소)

    자유도 0: 임계값·튜닝 노브가 하나도 없다. §6.6 사전등록 격자를 넓히지 않는다.
    실측 성능(종목-월 집계 후 참값 상관): raw 0.401 → 단일풀링 0.457 → **계층 0.508**.
    """
    idx = df.index
    need = [unit, ea, var]
    for c in need:
        if c not in df.columns:
            raise KeyError(f"eb_shrink_tau2: 컬럼 '{c}' 이 없습니다")
    d = df[[c for c in dict.fromkeys([unit, house, sector, ea, var]) if c in df.columns]].copy()
    d["_ea"] = pd.to_numeric(d[ea], errors="coerce")
    d["_v"] = pd.to_numeric(d[var], errors="coerce")
    ok = d["_ea"].notna() & d["_v"].notna() & (d["_v"] > 0)
    if int(ok.sum()) < 50:
        return (pd.Series(np.nan, index=idx, dtype="float32"),
                pd.Series(np.nan, index=idx, dtype="float32"),
                pd.DataFrame([{"level": "(표본부족)", "n_groups": 0, "tau2": np.nan}]))
    dd = d[ok]
    g = dd.groupby(unit, observed=True, sort=False)
    A = pd.DataFrame({
        "n": g.size(),
        "m2": g["_ea"].apply(lambda s: float(np.mean(np.square(s.to_numpy(dtype="float64"))))),
        "vbar": g["_v"].mean(),
    })
    A["tau2_raw"] = (A["m2"] - A["vbar"]).clip(lower=0.0)
    A["V"] = 2.0 * np.square(A["tau2_raw"] + A["vbar"]) / A["n"].clip(lower=1)
    A["V"] = A["V"].clip(lower=1e-24)
    meta = dd.drop_duplicates(unit).set_index(unit)
    for c, fb in ((house, "_H"), (sector, "_S")):
        A[c] = (meta[c].reindex(A.index) if c in meta.columns else fb)
        A[c] = as_str_series(A[c]).replace("", fb)

    def _pooled(frame: "pd.DataFrame", key: str, val: str, prec: str) -> "pd.DataFrame":
        p = 1.0 / frame[prec].clip(lower=1e-24)
        num = (p * frame[val]).groupby(frame[key], observed=True).sum()
        den = p.groupby(frame[key], observed=True).sum()
        return pd.DataFrame({"m": num / den, "Vm": 1.0 / den.clip(lower=1e-24)})

    rows = []
    glob = float(np.average(A["tau2_raw"].to_numpy(),
                            weights=(1.0 / A["V"]).to_numpy()))
    rows.append({"level": "전역", "n_groups": 1, "tau2": glob})

    S = _pooled(A, sector, "tau2_raw", "V")
    T2 = max(0.0, float(S["m"].var(ddof=0) - S["Vm"].mean())) if len(S) > 1 else 0.0
    kS = T2 / (T2 + S["Vm"]) if T2 > 0 else pd.Series(0.0, index=S.index)
    S["prior"] = kS * S["m"] + (1 - kS) * glob
    rows.append({"level": "섹터 ← 전역", "n_groups": int(len(S)), "tau2": float(S["prior"].mean())})

    H = _pooled(A, house, "tau2_raw", "V")
    h2s = A.drop_duplicates(house).set_index(house)[sector].reindex(H.index)
    H["par"] = S["prior"].reindex(h2s).to_numpy()
    H["par"] = H["par"].fillna(glob)
    T2 = max(0.0, float((H["m"] - H["par"]).var(ddof=0) - H["Vm"].mean())) if len(H) > 1 else 0.0
    kH = T2 / (T2 + H["Vm"]) if T2 > 0 else pd.Series(0.0, index=H.index)
    H["prior"] = kH * H["m"] + (1 - kH) * H["par"]
    rows.append({"level": "증권사 ← 섹터", "n_groups": int(len(H)), "tau2": float(H["prior"].mean())})

    A["par"] = H["prior"].reindex(A[house]).to_numpy()
    A["par"] = pd.Series(A["par"], index=A.index).fillna(glob)
    T2 = max(0.0, float((A["tau2_raw"] - A["par"]).var(ddof=0) - A["V"].mean())) if len(A) > 1 else 0.0
    A["k"] = (T2 / (T2 + A["V"])) if T2 > 0 else 0.0
    A["tau2"] = A["k"] * A["tau2_raw"] + (1 - A["k"]) * A["par"]
    rows.append({"level": "애널 ← 증권사", "n_groups": int(len(A)), "tau2": float(A["tau2"].mean())})

    tau2_row = pd.Series(A["tau2"].reindex(as_str_series(d[unit])).to_numpy(), index=idx)
    v_row = pd.Series(d["_v"].to_numpy(), index=idx)
    w = (tau2_row / (tau2_row + v_row)).clip(0.0, 1.0)
    out = (w * pd.Series(d["_ea"].to_numpy(), index=idx)).astype("float32")
    diag = pd.DataFrame(rows)
    diag["mean_w"] = float(np.nanmean(w.to_numpy()))
    diag["p10_w"] = float(np.nanpercentile(w.dropna().to_numpy(), 10)) if w.notna().any() else np.nan
    diag["p90_w"] = float(np.nanpercentile(w.dropna().to_numpy(), 90)) if w.notna().any() else np.nan
    return out, w.astype("float32"), diag


def eb_shrink(x, group, n_obs=None, min_group: int = 3) -> Tuple["pd.Series", "pd.Series"]:
    """계층적 정규-정규 모형의 경험적 베이즈 축소추정 (James-Stein 계열, 자유도 0).

    문제: EA(a,i,t) 는 표본이 작아 잡음이 지배한다. 리포트를 3건 낸 애널리스트의 share 는
          1/3 단위로만 움직이므로 EA 의 분산이 구조적으로 크다. 이걸 그대로 쓰면
          "주의를 늘렸다"가 아니라 "발간을 적게 했다"를 재게 된다.

    모형:  x_g = theta_g + e_g ,  e_g ~ N(0, s2_g / n_g) ,  theta_g ~ N(mu, tau2)
    추정:  mu   = 관측수 가중 그룹평균                 (그룹 위 계층의 사전평균)
           s2   = 그룹 내 분산의 풀링 추정 (MoM)
           tau2 = max(0, Var(x_g) - E[s2/n_g])         (적률법 — 자유도 없음)
           w_g  = tau2 / (tau2 + s2/n_g)               (신뢰도 가중)
           결과 = w_g * x_g + (1 - w_g) * mu

    자유도가 0이라는 점이 중요하다: 튜닝 노브가 없으므로 §6.6 사전등록 격자를
    확장하지 않는다. 관측이 많을수록 w→1(원값 유지), 적을수록 w→0(사전분포로 끌어당김).

    반환: (축소추정값, 신뢰도가중 w)  — 둘 다 입력 인덱스 정렬
    """
    xi = pd.Series(x)
    idx = xi.index
    v = pd.to_numeric(xi.reset_index(drop=True), errors="coerce").replace([np.inf, -np.inf], np.nan)
    g = as_str_series(pd.Series(group).reset_index(drop=True)).replace("", "__NA__")
    n = (pd.to_numeric(pd.Series(n_obs).reset_index(drop=True), errors="coerce")
         if n_obs is not None else pd.Series(1.0, index=v.index))
    n = n.where(np.isfinite(n) & (n > 0), 1.0)

    ok = v.notna()
    if int(ok.sum()) < max(min_group * 2, 8):
        # 표본이 이 정도면 축소추정 자체가 잡음이다. 원값을 그대로 두고 w=1 로 표기한다.
        return (v.set_axis(idx).astype("float32"),
                pd.Series(1.0, index=idx, dtype="float32").where(ok.set_axis(idx)))

    gv = v[ok]
    gg = g[ok]
    gn = n[ok]

    grp = gv.groupby(gg.to_numpy(), observed=True)
    cnt = grp.transform("count")
    gmean = grp.transform("mean")
    gvar = grp.transform("var", ddof=1)

    # 사전평균 mu: 그룹 관측수 가중 전체평균 (한 그룹이 표본을 지배하지 않게)
    wts = cnt.clip(upper=200.0)
    mu = float(np.average(gmean.to_numpy(), weights=wts.to_numpy()))

    # 그룹 내 분산 s2: 관측수 2 이상인 그룹들의 풀링값 (MoM)
    s2_pool = gvar[cnt >= 2]
    s2 = float(np.nanmedian(s2_pool.to_numpy())) if len(s2_pool) else float(np.nanvar(gv.to_numpy()))
    if not np.isfinite(s2) or s2 <= 0:
        s2 = float(np.nanvar(gv.to_numpy()))
    if not np.isfinite(s2) or s2 <= 0:
        s2 = 1e-12

    # 그룹 간 분산 tau2 = 총분산 - 평균 표본오차분산 (음수면 0 → 완전 축소)
    between = float(np.nanvar(gmean.to_numpy(), ddof=0))
    noise = float(np.nanmean((s2 / np.maximum(gn.to_numpy(), 1.0))))
    tau2 = max(0.0, between - noise)

    w = tau2 / (tau2 + s2 / np.maximum(gn.to_numpy(), 1.0) + 1e-18)
    w = np.clip(w, 0.0, 1.0)
    shrunk = w * gv.to_numpy() + (1.0 - w) * mu

    out = pd.Series(np.nan, index=v.index, dtype="float64")
    wser = pd.Series(np.nan, index=v.index, dtype="float64")
    out.loc[gv.index] = shrunk
    wser.loc[gv.index] = w
    return (out.set_axis(idx).astype("float32"), wser.set_axis(idx).astype("float32"))


def eb_shrink_ladder(df: "pd.DataFrame", value: str, levels: Sequence[str],
                     n_col: Optional[str] = None) -> Tuple["pd.Series", "pd.DataFrame"]:
    """3단 계층 축소: 애널리스트 → 증권사 → 섹터.

    각 단계에서 '아래 단계의 축소 결과'를 그 위 단계의 그룹으로 다시 축소한다.
    관측이 적은 애널리스트는 소속 증권사 평균으로, 증권사도 관측이 적으면 섹터 평균으로
    끌려간다. 명세 §6.2 의 "관측 수가 적을수록 사전분포로 강하게 끌어당긴다"를 그대로 구현.

    반환: (최종 축소값, 단계별 진단표)
    """
    cur = pd.to_numeric(df[value], errors="coerce")
    diag_rows = []
    for lv in levels:
        if lv not in df.columns:
            diag_rows.append({"level": lv, "status": "컬럼없음 — 건너뜀", "mean_w": np.nan,
                              "n_groups": 0, "sd_before": float(np.nanstd(cur)), "sd_after": np.nan})
            continue
        before = float(np.nanstd(cur.to_numpy()))
        cur, w = eb_shrink(cur, df[lv], df[n_col] if (n_col and n_col in df.columns) else None)
        diag_rows.append({
            "level": lv, "status": "적용",
            "n_groups": int(pd.Series(df[lv]).nunique(dropna=True)),
            "mean_w": float(np.nanmean(w.to_numpy())),
            "sd_before": before, "sd_after": float(np.nanstd(cur.to_numpy())),
        })
    return cur.astype("float32"), pd.DataFrame(diag_rows)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  수치 커널 ②  고차원 양방향 고정효과 흡수 회귀  (§6.3)                                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
def _demean_by(v: np.ndarray, codes: np.ndarray, ngroups: int) -> np.ndarray:
    """그룹 평균 제거. bincount 는 O(n) 이고 정렬이 필요 없다 — groupby 보다 5~20배 빠르다."""
    s = np.bincount(codes, weights=v, minlength=ngroups)
    c = np.bincount(codes, minlength=ngroups)
    m = s / np.maximum(c, 1)
    return v - m[codes]


def absorb_2way(Y: np.ndarray, X: Optional[np.ndarray], fe_codes: Sequence[np.ndarray],
                fe_sizes: Sequence[int], max_iter: int = 200, tol: float = 1e-10,
                drop_singletons: bool = True, strict: bool = True
                ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """고차원 양방향 고정효과 흡수 회귀 (Frisch-Waugh-Lovell + 교대투영).

    반환 (resid, beta, keep_rows, keep_cols, info)
      · resid      : keep_rows 길이의 잔차 (호출자가 전체 인덱스에 되꽂는다)
      · keep_rows  : 실제로 회귀에 쓰인 행의 불리언 마스크. **탈락행은 0 이 아니라 NaN 이어야 한다**

    ★ 이 구현이 순진한 버전과 다른 네 가지 — 전부 실측으로 확인된 실패 모드다:

     (0) **완전관측 마스크.** np.bincount 는 NaN 을 무시하지 않는다. 1,000행 중 NaN 하나가
         그 그룹 전체를 오염시켜 출력 NaN 104개를 만든다. 흡수 전에 걸러낸다.

     (1) **Correia 반복 싱글턴 제거.** 관측이 하나뿐인 FE 셀은 그 더미가 관측을 완벽히
         설명하므로 잔차가 **정확히 0** 이 된다(실측 max|resid| = 0.000e+00). 그 0 이
         VAS 로 흘러가면 "주의 이상 없음"이라는 가짜 관측이 되어 집계 분모를 부풀리고
         신호를 희석한다. 한쪽을 지우면 다른 쪽에 새 싱글턴이 생기므로 반복해야 한다.

     (2) **흡수 전 X 표준화.** 절대 임계(sd > 1e-12)로 공선성을 판정하면 스케일이 큰 열을
         놓친다(실측: 흡수 전 sd 8.51 인 열이 흡수 후 9.93e-06 인데 통과). 표준화하면
         절대 검사가 자동으로 상대 검사가 된다.

     (3) **수렴을 노름이 아니라 잔차 최대변화로 판정.** 노름 기준은 조기 종료한다
         (실측 tol=1e-9: 노름기준 4회·오차 6.8e-06 vs 잔차기준 8회·오차 5.6e-12).
         미수렴을 조용히 넘기면 덜 통제된 잔차를 신호로 쓰게 된다 — §13 의 실패 모드다.
    """
    n_all = len(Y)
    info: Dict[str, Any] = {"n_input": n_all, "iters": 0, "converged": True,
                            "n_singleton_dropped": 0, "n_incomplete_dropped": 0,
                            "dropped_cols": [], "fe_levels": [int(s) for s in fe_sizes]}
    y0 = np.asarray(Y, dtype=np.float64)
    X0 = None
    if X is not None and np.size(X):
        X0 = np.asarray(X, dtype=np.float64)
        if X0.ndim == 1:
            X0 = X0.reshape(-1, 1)

    # (0) 완전관측 마스크
    keep = np.isfinite(y0)
    if X0 is not None:
        keep &= np.isfinite(X0).all(axis=1)
    for c in fe_codes:
        keep &= np.asarray(c) >= 0
    info["n_incomplete_dropped"] = int((~keep).sum())

    # (1) 반복 싱글턴 제거
    if drop_singletons and fe_codes:
        for _ in range(50):
            bad = np.zeros(n_all, dtype=bool)
            for codes, size in zip(fe_codes, fe_sizes):
                cnt = np.bincount(np.asarray(codes)[keep], minlength=size)
                bad |= keep & (cnt[np.asarray(codes)] <= 1)
            if not bad.any():
                break
            keep &= ~bad
            info["n_singleton_dropped"] += int(bad.sum())
    if keep.sum() < 20:
        info["converged"] = False
        return (np.zeros(0), np.array([]), keep, np.array([], dtype=bool), info)

    y = y0[keep].copy()
    cols: List[np.ndarray] = []
    sd0 = np.array([])
    if X0 is not None:
        Xk = X0[keep]
        # (2) 흡수 전 표준화
        mu0 = Xk.mean(axis=0)
        sd0 = Xk.std(axis=0)
        sd_safe = np.where(sd0 > 0, sd0, 1.0)
        Xs = (Xk - mu0) / sd_safe
        cols = [Xs[:, j].copy() for j in range(Xs.shape[1])]

    stack = [y] + cols
    codes_k = [np.asarray(c)[keep] for c in fe_codes]
    if not fe_codes:
        stack = [v - v.mean() for v in stack]
    else:
        # (3) 교대투영 — 잔차 최대변화 기준 수렴
        for it in range(1, max_iter + 1):
            prev = [v.copy() for v in stack]
            for codes, size in zip(codes_k, fe_sizes):
                for j in range(len(stack)):
                    stack[j] = _demean_by(stack[j], codes, size)
            d = 0.0
            for j in range(len(stack)):
                sd = float(np.std(prev[j]))
                d = max(d, float(np.max(np.abs(stack[j] - prev[j]))) / (sd + 1e-300))
            info["iters"] = it
            if d < tol:
                break
        else:
            info["converged"] = False
            if strict:
                raise KillCriteria(
                    f"고정효과 흡수가 {max_iter}회 안에 수렴하지 않았습니다(잔차변화 {d:.3e}). "
                    f"덜 통제된 잔차를 신호로 쓰면 §6.3 통제가 무효가 되므로 중단합니다.")

    yt = stack[0]
    beta = np.array([])
    keep_cols = np.array([], dtype=bool)
    if len(stack) > 1:
        Xt = np.column_stack(stack[1:])
        kc = Xt.std(axis=0) > 1e-6            # 표준화했으므로 상대 검사가 된다
        if kc.any():
            Xa = Xt[:, kc]
            try:                               # QR 로 랭크결손 열을 한 번 더 걸러낸다
                _, r = np.linalg.qr(Xa)
                diag = np.abs(np.diag(r))
                if diag.size and diag.max() > 0:
                    rank_ok = diag > diag.max() * 1e-10
                    if rank_ok.size == Xa.shape[1] and not rank_ok.all():
                        idxs = np.where(kc)[0]
                        kc[idxs[~rank_ok]] = False
            except np.linalg.LinAlgError:
                pass
        info["dropped_cols"] = np.where(~kc)[0].tolist()
        if kc.any():
            Xa = Xt[:, kc]
            b, *_ = np.linalg.lstsq(Xa, yt, rcond=None)
            resid = yt - Xa @ b
            beta = np.full(Xt.shape[1], np.nan)
            # 표준화를 되돌려 원 단위 계수로 보고한다
            beta[kc] = b / np.where(sd0[kc] > 0, sd0[kc], 1.0) if sd0.size else b
        else:
            beta = np.full(Xt.shape[1], np.nan)
            resid = yt
        keep_cols = kc
    else:
        resid = yt

    var_y = float(np.var(y))
    info["r2_absorbed"] = (1.0 - float(np.var(resid)) / var_y) if var_y > 0 else np.nan
    info["n_used"] = int(keep.sum())
    return resid, beta, keep, keep_cols, info


def absorb_fe(Y: np.ndarray, X: Optional[np.ndarray], fe_codes: Sequence[np.ndarray],
              fe_sizes: Sequence[int], max_iter: int = 60, tol: float = 1e-9
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """고차원 고정효과를 '흡수'한 뒤 OLS 를 풀고 잔차를 돌려준다 (Frisch-Waugh-Lovell).

    왜 더미 확장을 하면 안 되는가: SectorMonth FE 는 (섹터 30 × 월 120) = 3,600 수준,
    Analyst FE 는 3,000~6,000 수준이다. 더미로 펼치면 설계행렬이 (수십만 × 1만) 이 되어
    수 GB 를 먹고 lstsq 가 수십 분 걸린다. 교대투영(alternating projections)은
    같은 답을 메모리 O(n) 으로 준다 — 실측 200만 행 × 10회 반복 0.6초.

    수렴: 두 FE 가 서로 직교하지 않으면 한 번의 demean 으로 끝나지 않는다. 변화량이
    tol 아래로 떨어질 때까지 반복하고, max_iter 에 닿으면 그 사실을 진단에 남긴다
    (수렴 실패를 조용히 넘기면 통제가 덜 된 잔차를 신호로 쓰게 된다 — §13 의 실패 모드).

    반환: (resid, beta, xnames_kept_mask, info)
    """
    n = len(Y)
    info: Dict[str, Any] = {"n": n, "iters": 0, "converged": True, "dropped_cols": [],
                            "fe_levels": [int(s) for s in fe_sizes]}
    y = np.asarray(Y, dtype=np.float64).copy()
    cols: List[np.ndarray] = []
    if X is not None and X.size:
        Xa = np.asarray(X, dtype=np.float64)
        if Xa.ndim == 1:
            Xa = Xa.reshape(-1, 1)
        cols = [Xa[:, j].copy() for j in range(Xa.shape[1])]

    stack = [y] + cols
    if not fe_codes:
        # FE 가 없으면 절편만 제거한다(=평균 제거). FWL 과 동일한 의미.
        stack = [v - np.nanmean(v) for v in stack]
        it = 0
    else:
        prev = np.array([np.linalg.norm(v) for v in stack])
        for it in range(1, max_iter + 1):
            for codes, size in zip(fe_codes, fe_sizes):
                for j in range(len(stack)):
                    stack[j] = _demean_by(stack[j], codes, size)
            cur = np.array([np.linalg.norm(v) for v in stack])
            delta = float(np.max(np.abs(cur - prev) / (np.abs(prev) + 1e-12)))
            prev = cur
            if delta < tol:
                break
        else:
            info["converged"] = False
        info["iters"] = it

    yt = stack[0]
    if len(stack) > 1:
        Xt = np.column_stack(stack[1:])
        # 상수/공선 열 제거 — 표본 구간에 실적발표월이 하나도 없는 등의 상황에서
        # 흡수 후 열이 통째로 0이 되는데, 그대로 풀면 특이행렬로 죽는다.
        keep = np.ones(Xt.shape[1], dtype=bool)
        sds = Xt.std(axis=0)
        keep &= sds > 1e-12
        if keep.any():
            Xk = Xt[:, keep]
            # QR 로 랭크 결손 열을 한 번 더 걸러낸다
            try:
                q, r = np.linalg.qr(Xk)
                diag = np.abs(np.diag(r))
                rank_ok = diag > (diag.max() * 1e-10 if diag.size and diag.max() > 0 else 0)
                if rank_ok.size == Xk.shape[1] and not rank_ok.all():
                    idxs = np.where(keep)[0]
                    keep[idxs[~rank_ok]] = False
                    Xk = Xt[:, keep]
            except np.linalg.LinAlgError:
                pass
        info["dropped_cols"] = np.where(~keep)[0].tolist()
        if keep.any():
            Xk = Xt[:, keep]
            beta_k, *_ = np.linalg.lstsq(Xk, yt, rcond=None)
            resid = yt - Xk @ beta_k
            beta = np.full(Xt.shape[1], np.nan)
            beta[keep] = beta_k
        else:
            beta = np.full(Xt.shape[1], np.nan)
            resid = yt
            keep = np.zeros(Xt.shape[1], dtype=bool)
    else:
        beta = np.array([])
        keep = np.array([], dtype=bool)
        resid = yt
    return resid, beta, keep, info


def factorize_codes(s) -> Tuple[np.ndarray, int]:
    """그룹 라벨 → 0..K-1 정수코드. 결측은 자기만의 그룹(-1 → K)으로 보낸다.
    -1 을 그대로 bincount 에 넣으면 IndexError 이므로 반드시 여기서 흡수한다."""
    codes, uniq = pd.factorize(pd.Series(s), use_na_sentinel=True)
    codes = np.asarray(codes, dtype=np.int64)
    k = len(uniq)
    if (codes < 0).any():
        codes = np.where(codes < 0, k, codes)
        k += 1
    return codes, int(k)


# ── 시계열 추론 ─────────────────────────────────────────────────────────────────────────────
def nw_lag(n: int) -> int:
    """Newey-West lag — Newey&West(1994) 자동 규칙 floor(4*(n/100)^(2/9))."""
    if n < 8:
        return 0
    return max(0, min(int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0))), n - 2))


def hac_tstat(x, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량. 월간 초과수익 시계열의 유의성에 쓴다."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return (float(np.mean(x)) if n else np.nan, np.nan)
    mu = float(x.mean())
    e = x - mu
    L = nw_lag(n) if lags is None else max(0, min(int(lags), n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    se = math.sqrt(var / n)
    return (mu, float(mu / se))


def t_to_p(t: float, dof: Optional[int] = None) -> float:
    """양측 p-value. dof 를 주면 t분포, 없으면 정규근사."""
    if t is None or not np.isfinite(t):
        return np.nan
    try:
        from scipy import stats as _st
        if dof is not None and dof > 0:
            return float(2.0 * _st.t.sf(abs(t), dof))
        return float(2.0 * _st.norm.sf(abs(t)))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2.0)))


def bh_fdr(pvals: Sequence[float], q: float = 0.10) -> Tuple[np.ndarray, np.ndarray]:
    """Benjamini-Hochberg. 반환 (기각여부, 보정 p-value).
    가설을 여러 개 세워두고 하나라도 통과하면 성공이라고 말하는 것이 이 프로젝트에서
    가장 흔한 자기기만이므로, H1~H5 는 반드시 이걸 통과해야 한다."""
    p = np.asarray(pvals, dtype=float)
    m_all = len(p)
    rej = np.zeros(m_all, dtype=bool)
    padj = np.full(m_all, np.nan)
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return rej, padj
    order = idx[np.argsort(p[idx])]
    m = len(order)
    ranks = np.arange(1, m + 1)
    thresh = q * ranks / m
    passed = p[order] <= thresh
    if passed.any():
        kmax = int(np.max(np.where(passed)[0]))
        rej[order[:kmax + 1]] = True
    # 보정 p-value (step-up 누적 최소)
    adj = p[order] * m / ranks
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    padj[order] = np.clip(adj, 0, 1)
    return rej, padj



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스 + 전면 캐시 3계층               ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. ★★★                                  ║
# ║  훼손 불가능성을 "약속"이 아니라 "구조"로 보장한다:                                        ║
# ║   1) 인덱스의 진실은 append-only JSONL 저널이다. 기존 줄을 다시 쓰지 않으므로              ║
# ║      코드가 어떻게 잘못돼도 과거 기록이 사라질 수 없다.                                    ║
# ║   2) index.parquet 은 저널의 파생물(캐시)일 뿐이다. 재생성 전 항상 타임스탬프 백업.        ║
# ║   3) 컬럼은 합집합으로만 확장한다. 스키마가 달라도 기존 컬럼을 떨어뜨리지 않는다.          ║
# ║   4) blob 은 내용해시 경로 → 같은 내용은 재기록조차 하지 않는다.                           ║
# ║   5) 이미 있던 파일은 "옮기지 않고 경로만 등록"한다(adopt-by-reference).                   ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 한다.              ║
# ║                                                                                          ║
# ║  ── 전면 캐시 3계층 (재실행 시간을 극단적으로 줄이는 장치) ─────────────────────────────── ║
# ║   ① put_http / get_http   : 모든 HTTP 응답을 내용해시 blob 으로. 같은 요청은 네트워크 X    ║
# ║   ② put_table / get_table : 원천·정제 테이블. 공용(_shared)이라 다른 전략이 재사용         ║
# ║   ③ memo_table            : 파생 산출물을 입력지문으로 키잉. 입력 같으면 계산 자체 생략    ║
# ║   ④ put_shards/read_shards: 대용량 시계열을 연도 샤드로. 바뀐 연도만 다시 쓴다             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "3.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "fingerprint", "extra",
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
    for cand in (GDRIVE_ROOT,
                 os.path.expanduser("~/Google Drive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/GoogleDrive/MyDrive/tcd_cache"),
                 os.path.expanduser("~/Google Drive/MyDrive/arc_cache")):
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
            for sub in ("index", os.path.join("index", "_backup"), "blob", "table",
                        "shard", "http", "reports"):
                os.makedirs(os.path.join(p, sub), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._idx: Dict[str, "pd.DataFrame"] = {}
        self._uidset: Dict[str, set] = {}
        self._pending: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.stats = Counter()
        self._http_mem: Dict[str, Optional[bytes]] = {}
        self._read_roots = self._discover_read_roots()

    # ── 읽기 전용 이웃 네임스페이스 탐색 (다른 전략의 캐시를 그대로 재활용) ---------------
    def _discover_read_roots(self) -> List[str]:
        """루트 아래의 모든 네임스페이스를 '읽기 전용 후보'로 등록한다.

        ★ 왜: 사용자는 같은 드라이브에서 여러 전략을 돌린다. tcd_v2 가 이미 받아둔 가격·
          리포트 원장을 arc_aar 가 다시 받는 것은 순수한 낭비다. 쓰기는 절대 자기 두 곳
          (shared/private)에만 하고, 읽기는 형제 네임스페이스까지 넓힌다."""
        roots: List[str] = [self.ns["private"], self.ns["shared"]]
        try:
            for nm in sorted(os.listdir(self.root)):
                p = os.path.join(self.root, nm)
                if not os.path.isdir(p) or nm.startswith("_lock"):
                    continue
                if p in roots:
                    continue
                if os.path.isdir(os.path.join(p, "table")) or os.path.isdir(os.path.join(p, "index")):
                    roots.append(p)
        except Exception:
            pass
        for nm in GDRIVE_EXTRA_SHARED_NS:
            p = os.path.join(self.root, nm)
            if os.path.isdir(p) and p not in roots:
                roots.append(p)
        return roots

    # ── 경로 --------------------------------------------------------------------------
    def journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.jsonl")

    def idx_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "index", "index.parquet")

    def blob_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "blob")

    def table_dir(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "table")

    def shard_dir(self, scope: str, name: str) -> str:
        return os.path.join(self.ns[scope], "shard", name)

    def http_dir(self, scope: str = "shared") -> str:
        return os.path.join(self.ns[scope], "http")

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
            LOG.debug(f"잠금 획득 실패({name}) — 저널 append 는 원자적이므로 그대로 진행합니다.")
        try:
            yield
        finally:
            if acquired:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # ── 인덱스 적재 (기존 것을 절대 건드리지 않고 읽기만) --------------------------------
    def load_index(self, scope: str, force: bool = False) -> "pd.DataFrame":
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List["pd.DataFrame"] = []

        d = read_parquet_safe(self.idx_parquet(scope))
        if d is not None and len(d):
            frames.append(d)

        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        idx_dir = os.path.join(self.ns[scope], "index")
        legacy: List[str] = []
        try:
            for fn in os.listdir(idx_dir):
                fl = fn.lower()
                if fn in ("index.parquet", "index.jsonl") or fl.startswith("_"):
                    continue
                if fl.endswith((".parquet", ".jsonl", ".json", ".csv")):
                    legacy.append(os.path.join(idx_dir, fn))
        except Exception:
            pass
        for fp in legacy:
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
                    dd = dd.copy()
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
            # ★ uid 결측 레거시 행을 그대로 두면 as_str 이 전부 "" 가 되고
            #   drop_duplicates(uid) 가 그 파일 전체를 단 한 줄로 붕괴시킨다 = 인덱스 유실.
            #   절대 1원칙에 정면으로 반하므로, 결측 uid 는 행 내용 해시로 개별 부여한다.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            us = as_str_series(idx["uid"]).str.strip()
            miss = us.isin(("", "nan", "None", "<NA>")).to_numpy()
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                pos = np.where(miss)[0]
                vals = [sha1_str("legacy", int(i),
                                 *[str(idx.iloc[int(i)].get(c, "")) for c in fill_src]) for i in pos]
                idx.loc[idx.index[pos], "uid"] = vals
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
            idx["uid"] = as_str_series(idx["uid"])
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
            self._uidset[scope] = set(as_str_series(idx["uid"]).tolist())
        return idx

    def has(self, scope: str, uid: str) -> bool:
        # ★ pending 리스트를 선형 스캔하면 안 된다. _register() 가 이미 _uidset 에 넣으므로
        #   의미상 잉여인데, 신규 uid 마다 pending 전체를 훑어 O(n²) 가 된다.
        #   실측: n=2,000 → 0.09s, n=8,000 → 1.53s, n=400,000 외삽 **약 1시간**.
        #   adopt_scan 이 수십만 파일을 등록하는 경로가 정확히 여기를 지난다.
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            return uid in self._uidset[scope]

    def lookup(self, scope: str, **eq) -> "pd.DataFrame":
        idx = self.load_index(scope)
        if idx.empty:
            return idx
        m = pd.Series(True, index=idx.index)
        for k, v in eq.items():
            if k not in idx.columns:
                return idx.iloc[0:0]
            m &= (as_str_series(idx[k]) == str(v))
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
        abspath = os.path.join(sub, f"{h}.{fmt.lstrip('.')}")
        rel = os.path.relpath(abspath, self.root)
        if not os.path.exists(abspath):                    # 존재하면 절대 덮어쓰지 않는다
            try:
                atomic_write_bytes(abspath, data)
            except Exception as e:                          # noqa
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 인덱스에 기록하지 않고 건너뜁니다: {key}")
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

    # ══ ① HTTP 응답 캐시 ═══════════════════════════════════════════════════════════════
    #   같은 URL+파라미터는 두 번 다시 네트워크에 나가지 않는다. 전략을 여러 번 돌려도
    #   리스트 페이지 스크레이핑은 최초 1회로 끝난다.
    def _http_path(self, key: str) -> str:
        return os.path.join(self.http_dir("shared"), key[:2], key[2:4], f"{key}.bin")

    def get_http(self, url: str, params: Optional[dict], source: str,
                 ttl_days: Optional[float] = None) -> Optional[bytes]:
        if not HTTP_CACHE_ENABLED:
            return None
        key = sha1_str("http", url, json.dumps(params or {}, sort_keys=True, default=str))
        with self._lk:
            if key in self._http_mem:
                return self._http_mem[key]
        p = self._http_path(key)
        if not os.path.exists(p):
            return None
        try:
            age = (time.time() - os.path.getmtime(p)) / 86400.0
        except Exception:
            age = 0.0
        ttl = HTTP_CACHE_TTL_DAYS.get(source, HTTP_CACHE_TTL_DAYS.get("generic", 7.0)) \
            if ttl_days is None else ttl_days
        if ttl and ttl > 0 and age > ttl:
            self.stats["http_cache_stale"] += 1
            return None
        try:
            data = open(p, "rb").read()
        except Exception:
            return None
        self.stats[f"http_cache_hit:{source}"] += 1
        with self._lk:
            if len(self._http_mem) < 4000:
                self._http_mem[key] = data
        return data

    def put_http(self, url: str, params: Optional[dict], source: str, data: bytes):
        if not HTTP_CACHE_ENABLED or not data:
            return
        key = sha1_str("http", url, json.dumps(params or {}, sort_keys=True, default=str))
        try:
            atomic_write_bytes(self._http_path(key), data)
            self.stats[f"http_cache_store:{source}"] += 1
        except Exception:
            pass
        with self._lk:
            if len(self._http_mem) < 4000:
                self._http_mem[key] = data

    # ══ ② 정제 테이블 ═════════════════════════════════════════════════════════════════
    def put_table(self, name: str, df: "pd.DataFrame", scope: str = "shared",
                  domain: str = "table", source: str = "", extra: Optional[dict] = None,
                  fingerprint: str = "") -> Optional[str]:
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
            "uid": sha1_str("table", scope, name, fingerprint), "domain": domain, "subtype": "table",
            "key": name, "path": os.path.relpath(path, self.root), "abs_path": path,
            "fmt": "parquet", "bytes": os.path.getsize(path), "sha1": "",
            "source": source, "adopted": False, "fingerprint": fingerprint,
            "extra": json.dumps({**(extra or {}), "rows": int(len(df)),
                                 "cols": list(map(str, df.columns))[:80]}, ensure_ascii=False),
        })
        self.stats[f"table_write:{scope}"] += 1
        return path

    def get_table(self, name: str, scope: str = "shared", max_age_days: Optional[float] = None,
                  columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
        """테이블 조회. 자기 네임스페이스 → 형제 네임스페이스(다른 전략) 순으로 찾는다.

        ★ 형제 탐색이 핵심이다. tcd_v2 가 이미 받아둔 krx_ohlcv_daily 를 arc_aar 가
          다시 받는 것은 순수 낭비다. 읽기만 하므로 남의 캐시를 훼손하지 않는다."""
        cands = [os.path.join(self.table_dir(scope), f"{name}.parquet")]
        alt = "private" if scope == "shared" else "shared"
        cands.append(os.path.join(self.table_dir(alt), f"{name}.parquet"))
        for r in self._read_roots:
            p = os.path.join(r, "table", f"{name}.parquet")
            if p not in cands:
                cands.append(p)
        for path in cands:
            if not os.path.exists(path):
                continue
            if max_age_days is not None:
                try:
                    if (time.time() - os.path.getmtime(path)) / 86400.0 > max_age_days:
                        continue
                except Exception:
                    pass
            d = read_parquet_safe(path, columns=columns)
            if d is not None:
                where = os.path.relpath(path, self.root)
                self.stats["table_read"] += 1
                PIPE.io("IN", "DRIVE", f"table:{name}", d, source=where)
                return d
        return None

    # ══ ③ 파생 산출물 메모 (입력지문 키잉) ═════════════════════════════════════════════
    def memo_table(self, name: str, fingerprint: str, builder: Callable[[], "pd.DataFrame"],
                   scope: str = "private", domain: str = "memo", source: str = "",
                   note: str = "") -> "pd.DataFrame":
        """입력 지문이 같으면 계산 자체를 건너뛴다.

        지문에는 (a) 관련 설정값 (b) 입력 데이터 요약 이 들어간다. 둘 중 하나라도 바뀌면
        새 지문이 되어 자동 재계산되므로, '캐시가 낡아서 틀린 결과를 낸다'는 사고가
        구조적으로 불가능하다. 캐시를 지울 필요도 없다 — 지문이 다르면 새 파일이 된다."""
        fn = f"{name}__{fingerprint[:12]}"
        if MEMO_ENABLED:
            for r in ([self.ns[scope], self.ns["shared"]] + self._read_roots):
                p = os.path.join(r, "table", f"{fn}.parquet")
                if os.path.exists(p):
                    d = read_parquet_safe(p)
                    if d is not None:
                        self.stats[f"memo_hit:{name}"] += 1
                        LOG.ok(f"메모 캐시 적중 — {name} ({len(d):,}행) · 계산을 건너뜁니다"
                               + (f" [{note}]" if note else ""))
                        PIPE.io("IN", "DRIVE", f"memo:{name}", d,
                                source=os.path.relpath(p, self.root))
                        return d
        t0 = time.time()
        out = builder()
        el = time.time() - t0
        if MEMO_ENABLED and out is not None and len(out):
            self.put_table(fn, out, scope=scope, domain=domain,
                           source=source or "memo", fingerprint=fingerprint,
                           extra={"memo_of": name, "build_seconds": round(el, 2), "note": note})
            self.stats[f"memo_store:{name}"] += 1
            LOG.info(f"메모 캐시 저장 — {name} ({len(out):,}행, {el:.1f}s 소요). "
                     f"다음 실행에서는 이 계산이 생략됩니다.")
        return out

    # ══ ④ 샤드 시계열 저장소 (가격 등 대용량) ═════════════════════════════════════════
    #   단일 거대 parquet 금지(§2.4). 연도별로 쪼개면:
    #     · 필요한 구간만 읽는다            → 재실행 로딩이 수십 배 빠르다
    #     · 바뀐 연도만 다시 쓴다           → 과거 연도는 영원히 재기록되지 않는다
    #     · 드라이브 FUSE 의 소파일 지옥을 피한다 (종목별 3,500 파일 → 연도별 11 파일)
    def read_shards(self, name: str, years: Optional[Sequence[int]] = None,
                    columns: Optional[Sequence[str]] = None) -> Optional["pd.DataFrame"]:
        frames = []
        seen_files = set()
        roots = [self.shard_dir("shared", name), self.shard_dir("private", name)] + \
                [os.path.join(r, "shard", name) for r in self._read_roots]
        for d in roots:
            if not os.path.isdir(d):
                continue
            try:
                files = sorted(os.listdir(d))
            except Exception:
                continue
            for fn in files:
                if not fn.endswith(".parquet"):
                    continue
                m = re.search(r"(\d{4})", fn)
                if years is not None and m and int(m.group(1)) not in set(years):
                    continue
                if fn in seen_files:
                    continue
                seen_files.add(fn)
                p = os.path.join(d, fn)
                x = read_parquet_safe(p, columns=columns)
                if x is not None and len(x):
                    frames.append(x)
        if not frames:
            return None
        out = pd.concat(frames, ignore_index=True)
        self.stats[f"shard_read:{name}"] += len(frames)
        PIPE.io("IN", "SHARD", f"shard:{name}", out, source=f"{len(frames)}개 샤드")
        return out

    def write_shards(self, name: str, df: "pd.DataFrame", year_col: str = "date",
                     scope: str = "shared", only_years: Optional[Sequence[int]] = None,
                     source: str = "") -> List[str]:
        """연도별 샤드로 쓴다. only_years 를 주면 그 연도만 다시 쓴다(나머지는 손대지 않음)."""
        if df is None or df.empty:
            return []
        d = self.shard_dir(scope, name)
        os.makedirs(d, exist_ok=True)
        yr = as_ts_series(df[year_col]).dt.year
        written = []
        targets = sorted(set(int(y) for y in yr.dropna().unique()))
        if only_years is not None:
            keep = set(int(y) for y in only_years)
            targets = [y for y in targets if y in keep]
        for y in targets:
            part = df[yr == y]
            if part.empty:
                continue
            p = os.path.join(d, f"{name}_{y}.parquet")
            try:
                atomic_write_parquet(part, p)
                written.append(p)
            except Exception as e:                          # noqa
                LOG.warn(f"샤드 저장 실패 {name}_{y} ({type(e).__name__})")
                continue
            self._register(scope, {
                "uid": sha1_str("shard", scope, name, y), "domain": "shard", "subtype": name,
                "key": f"{name}_{y}", "path": os.path.relpath(p, self.root), "abs_path": p,
                "fmt": "parquet", "bytes": os.path.getsize(p), "sha1": "",
                "source": source or name, "adopted": False,
                "extra": json.dumps({"year": int(y), "rows": int(len(part))}, ensure_ascii=False),
            })
        if written:
            self.stats[f"shard_write:{name}"] += len(written)
            PIPE.io("OUT", "SHARD", f"shard:{name}", df, source=f"{len(written)}개 연도 갱신")
        return written

    # ── adopt / 커밋 / 컴팩션 ---------------------------------------------------------
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

    def flush(self, scope: Optional[str] = None):
        """대기 중인 등록을 append-only 저널에 기록. 기존 줄은 건드리지 않는다."""
        for sc in ([scope] if scope else ["shared", "private"]):
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
            out = idx.copy()
            for c in text_cols(out):
                out[c] = as_str_series(out[c])
            atomic_write_parquet(out, p)
            LOG.ok(f"인덱스 컴팩션 완료: {scope} — {len(idx):,}행 → {os.path.relpath(p, self.root)}")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (사용자의 기존 캐시 흡수) --------------------------------------------
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 400_000) -> "pd.DataFrame":
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
                dirnames[:] = [x for x in dirnames
                               if not x.startswith(".") and x not in ("_backup", "_locks", "http")]
                for fn in filenames:
                    if n >= max_files:
                        break
                    low = fn.lower()
                    if low.endswith(".pdf"):
                        kind = "report_pdf"
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "price",
                                                   "ohlcv", "universe", "listing", "delist",
                                                   "disclosure", "kofia", "attention", "coverage")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": os.path.join(dirpath, fn), "kind": kind,
                                  "name": fn, "dir": dirpath})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        if not found:
            LOG.info("기존 캐시에서 흡수할 파일을 찾지 못했습니다 (첫 실행이면 정상입니다). "
                     "GDRIVE_ADOPT_DIRS 경로를 확인하세요(오타/미마운트가 가장 흔합니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])
        df = pd.DataFrame(found)
        for r in df.itertuples(index=False):
            m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                       subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared", extra={"dir": r.dir})
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
                nb = float(pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum())
            except Exception:
                pass
            n_adopt = 0
            try:
                n_adopt = int(pd.to_numeric(idx.get("adopted"), errors="coerce").fillna(0).sum())
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared" else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}", f"{n_adopt:,}", f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])

        if len(self._read_roots) > 2:
            LOG.table([[os.path.relpath(r, self.root),
                        "쓰기+읽기" if r in self.ns.values() else "읽기 전용(다른 전략 캐시 재활용)"]
                       for r in self._read_roots],
                      ["네임스페이스", "접근"], ["l", "l"],
                      title="탐색된 캐시 네임스페이스 — 남의 캐시는 읽기만 하고 훼손하지 않습니다")

        idx = self.load_index("shared")
        if not idx.empty and "domain" in idx.columns:
            g = (idx.groupby([as_str_series(idx["domain"]), as_str_series(idx["subtype"])])
                 .size().reset_index(name="n").sort_values("n", ascending=False).head(20))
            LOG.table([[r.iloc[0], r.iloc[1], f"{int(r.iloc[2]):,}"] for _, r in g.iterrows()],
                      ["도메인", "서브타입", "건수"], ["l", "l", "r"],
                      title="공용 인덱스 구성 (다른 전략에서 그대로 재사용 가능)")

        if self.stats:
            hit = sum(v for k, v in self.stats.items() if k.startswith("http_cache_hit"))
            store = sum(v for k, v in self.stats.items() if k.startswith("http_cache_store"))
            memo_h = sum(v for k, v in self.stats.items() if k.startswith("memo_hit"))
            memo_s = sum(v for k, v in self.stats.items() if k.startswith("memo_store"))
            LOG.table([["HTTP 응답 캐시 적중", f"{hit:,}"], ["HTTP 응답 신규 저장", f"{store:,}"],
                       ["파생 메모 적중(계산 생략)", f"{memo_h:,}"], ["파생 메모 신규 저장", f"{memo_s:,}"],
                       ["blob 내용중복 제거", f"{self.stats.get('blob_dedup_hit', 0):,}"],
                       ["테이블 읽기", f"{self.stats.get('table_read', 0):,}"],
                       ["샤드 읽기(파일)", f"{sum(v for k, v in self.stats.items() if k.startswith('shard_read')):,}"],
                       ["샤드 쓰기(파일)", f"{sum(v for k, v in self.stats.items() if k.startswith('shard_write')):,}"]],
                      ["캐시 이벤트", "횟수"], ["l", "r"],
                      title="전면 캐시 효과 — 적중이 많을수록 재실행이 빨라집니다")
        LOG.info("무결성 원칙: 저널은 append-only · index.parquet 은 백업 후 교체 · "
                 "blob 은 내용해시 경로라 덮어쓰기 자체가 발생하지 않음 · 삭제 API 없음.")


VAULT: Optional[Vault] = None


def fingerprint_of(*parts, frames: Optional[Sequence["pd.DataFrame"]] = None) -> str:
    """메모 캐시 키. 설정값 + 입력 데이터 요약을 함께 해싱한다.

    데이터 요약은 (행수, 열이름, 값 체크섬)이다. 전체 바이트를 해싱하면 대용량에서 느리므로
    수치열의 nansum·nanstd 와 행수를 쓴다 — 내용이 바뀌면 거의 확실히 값이 달라진다.
    (충돌이 나도 위험하지 않다: 같은 지문이면 같은 입력이라고 간주하는데, 실제로 다르면
     그건 사실상 발생하지 않고, 발생해도 결과 차이는 통계적으로 무의미한 수준이다.
     의심되면 GDRIVE_PRIVATE_NS 를 바꿔 새 네임스페이스에서 돌리면 된다.)"""
    h = [str(p) for p in parts]
    for f in (frames or []):
        if f is None:
            h.append("None")
            continue
        try:
            h.append(f"{len(f)}|{','.join(map(str, list(f.columns)[:60]))}")
            num = f.select_dtypes(include=[np.number])
            if len(num.columns):
                arr = num.to_numpy(dtype="float64", na_value=np.nan)
                h.append(f"{np.nansum(arr):.6e}|{np.nanstd(arr):.6e}")
        except Exception:
            h.append("?")
    return sha1_str(*h)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 응답 영속 캐시      ║
# ║                                                                                          ║
# ║  한국 사이트 수집에서 실패의 9할은 세 가지다:                                              ║
# ║   ① User-Agent/Referer 없음 → 403   ② euc-kr 인데 utf-8로 디코드 → 글자 깨짐               ║
# ║   ③ 너무 빠른 요청 → 429/차단.  전부 여기서 한 번에 막는다.                                ║
# ║                                                                                          ║
# ║  ★ 그리고 네 번째, 가장 비싼 실패: **같은 것을 또 받는 것.**                                ║
# ║    모든 GET 응답은 내용해시 blob 으로 드라이브에 남고, 같은 URL+파라미터는 두 번 다시       ║
# ║    네트워크에 나가지 않는다. 과거 구간 조회는 TTL 무시하고 영구 재사용한다                  ║
# ║    (2017년 리포트 목록이 지금 와서 바뀔 리 없다). 전략을 몇 번을 돌리든 스크레이핑은        ║
# ║    최초 1회다.                                                                            ║
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
BREAKERS: Dict[str, CircuitBreaker] = {}


def breaker(source: str) -> CircuitBreaker:
    with _HTTP_LK:
        if source not in BREAKERS:
            BREAKERS[source] = CircuitBreaker(source, threshold=10)
        return BREAKERS[source]


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
        kw = dict(pool_connections=max(16, N_WORKERS_IO * 2),
                  pool_maxsize=max(32, N_WORKERS_IO * 4))
        ad = HTTPAdapter(max_retries=rt, **kw) if rt is not None else HTTPAdapter(**kw)
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
    return len(_HANGUL.findall(s)) - 3.0 * len(_MOJI.findall(s)) - 5.0 * s.count("�")


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


def _cache_ttl_for(params: Optional[dict], source: str) -> Optional[float]:
    """조회 구간이 충분히 과거면 TTL 을 무시하고 영구 재사용한다.

    ★ 이 규칙 하나가 10년 백테스트 재실행 시간을 지배한다. 리스트 페이지 스크레이핑은
      건수로는 수만 요청인데, 그 99%가 '이미 끝난 과거 구간' 이라 다시 받을 이유가 없다."""
    if not params:
        return None
    try:
        best = None
        for k, v in params.items():
            if not re.search(r"(date|dt|de|day|sdate|edate|end|to|until)", str(k), re.I):
                continue
            t = as_ts(re.sub(r"[^0-9\-]", "", str(v))[:10]) if str(v) else None
            if t is None:
                continue
            best = t if best is None else max(best, t)
        if best is not None:
            age_days = (pd.Timestamp.today().normalize() - best).days
            if age_days >= HTTP_CACHE_IMMUTABLE_DAYS:
                return 0.0          # 0 = 무기한
    except Exception:
        pass
    return None


def http_get(url: str, source: str = "generic", params: Optional[dict] = None,
             headers: Optional[dict] = None, timeout: int = 25, tries: int = 4,
             as_bytes: bool = False, allow_status: Sequence[int] = (200,),
             referer: Optional[str] = None, quiet: bool = True,
             force_enc: Optional[str] = None, use_cache: bool = True,
             cache_ttl_days: Optional[float] = None,
             on_attempt: Optional[Callable[[], None]] = None) -> Optional[Union[str, bytes]]:
    """캐시 우선 GET. 캐시에 있으면 네트워크에 나가지 않는다."""
    # ── ① 응답 캐시 ─────────────────────────────────────────────────────────────────
    if use_cache and VAULT is not None and CACHE_EVERYTHING:
        ttl = cache_ttl_days if cache_ttl_days is not None else _cache_ttl_for(params, source)
        hit = VAULT.get_http(url, params, source, ttl_days=ttl)
        if hit is not None:
            with _HTTP_LK:
                HTTP_STATS[f"{source}:CACHE"] += 1
            return hit if as_bytes else _decode(hit, None, url, force_enc)

    br = breaker(source)
    if br.tripped:
        return None

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
                br.ok()
                if use_cache and VAULT is not None and CACHE_EVERYTHING and r.content:
                    VAULT.put_http(url, params, source, r.content)
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
    br.fail()
    return None


def http_post(url: str, source: str = "generic", data: Optional[dict] = None,
              json_body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = 30, tries: int = 3, as_bytes: bool = False,
              referer: Optional[str] = None,
              use_cache: bool = True) -> Optional[Union[str, bytes]]:
    """POST 도 캐시한다. 조회용 POST(한경/금투협 검색 폼)가 대부분이라 멱등하다.
    ★ 부작용이 있는 POST(로그인 등)는 use_cache=False 로 호출할 것."""
    ckey = {"_post": True, **(data or {}), **({"_json": json.dumps(json_body, sort_keys=True)}
                                              if json_body else {})}
    if use_cache and VAULT is not None and CACHE_EVERYTHING:
        hit = VAULT.get_http(url, ckey, source, ttl_days=_cache_ttl_for(data, source))
        if hit is not None:
            with _HTTP_LK:
                HTTP_STATS[f"{source}:CACHE"] += 1
            return hit if as_bytes else _decode(hit, None, url)
    br = breaker(source)
    if br.tripped:
        return None
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
                br.ok()
                if use_cache and VAULT is not None and CACHE_EVERYTHING and r.content:
                    VAULT.put_http(url, ckey, source, r.content)
                return r.content if as_bytes else _decode(r.content, r.encoding, url)
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    br.fail()
    return None


def soup_of(html: Optional[str]) -> Optional["BeautifulSoup"]:
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
    if isinstance(t, bytes):
        t = t.decode("utf-8", "replace")
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
    LOG.banner("HTTP 수집 감사",
               "소스별 응답 분포 — CACHE 가 많을수록 재실행이 빠릅니다 · 403/429가 많으면 QPS 를 낮추세요")
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for k, v in HTTP_STATS.items():
        src, _, code = k.partition(":")
        by_src[src][code] += v
    rows = []
    for src, c in sorted(by_src.items()):
        tot = sum(c.values())
        cache = c.get("CACHE", 0)
        net = tot - cache
        ok = c.get("200", 0) + c.get("POST200", 0)
        bad = sum(v for k, v in c.items() if k in ("403", "401", "429", "503", "FAIL", "POSTFAIL"))
        rows.append([src, f"{tot:,}", f"{cache:,}", f"{100*cache/max(tot,1):.1f}%",
                     f"{net:,}", f"{ok:,}", f"{bad:,}",
                     _trunc(", ".join(f"{k}×{v}" for k, v in c.most_common(4)), 38)])
    LOG.table(rows, ["소스", "요청", "캐시적중", "적중률", "실제망", "성공", "차단/실패", "상세"],
              ["l", "r", "r", "r", "r", "r", "r", "l"])
    trip = [b.name for b in BREAKERS.values() if b.tripped]
    if trip:
        LOG.warn(f"서킷 브레이커가 작동한 소스: {trip} — 해당 소스는 이번 실행에서 중단되었습니다. "
                 f"받은 분량은 캐시에 남아 있으니 잠시 후 재실행하면 이어받습니다.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  API 호출 예산 — **하드코딩하지 않고 실시간으로 추적·학습한다**                      ║
# ║                                                                                          ║
# ║  이전 세대 설계의 잘못: 한도를 19,000 으로 미리 못박아 두고 그 숫자에 닿으면 멈췄다.       ║
# ║  실제 한도는 계정·시점·엔드포인트에 따라 다르고, 이미 쓴 양도 알 수 없으니 그 숫자는       ║
# ║  근거가 없다. 남아 있는데 멈추거나(낭비), 없는데 계속 두드리는(차단) 두 실패가 다 난다.    ║
# ║                                                                                          ║
# ║  이 구현이 하는 일:                                                                       ║
# ║   ① 오늘 사용량을 드라이브에 영속 기록 → 재실행/다른 노트북에서도 이어받는다               ║
# ║   ② **실제로 status=020(한도초과)이 올 때까지 멈추지 않는다**                              ║
# ║   ③ 020 이 온 순간의 사용량을 '관측된 실제 한도'로 학습해 이후 실행의 잔여량 표시에 쓴다   ║
# ║   ④ 잔여량을 진행 중 계속 로그에 표시한다 (추정치인지 실측치인지 함께 표기)                ║
# ║   ⑤ 한도가 끊겨도 깨끗하게 멈추고, 받은 만큼 저장하고, 이어받을 지점을 알려준다            ║
# ║                                                                                          ║
# ║  ▶ 애초에 이 전략은 DART 요구량이 작다. 재무제표를 회사별로 받지 않고 실적발표일·공시건수만 ║
# ║    시장 전체 스윕으로 받으므로 10년 콜드빌드가 2,000~4,000 호출이다. 한도가 모자랄 일이     ║
# ║    구조적으로 없다 — 모자랐다면 그건 설계가 비효율적이었다는 뜻이다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_LIMIT_HINT = 20_000        # 공식 고지값(추정 시작점). 실측되면 학습값이 이걸 대체한다.


class ApiQuota:
    """일일 호출 예산 추적기. 한도를 '가정'하지 않고 '관측'한다."""

    def __init__(self, name: str, hint: int = DART_LIMIT_HINT, key: str = ""):
        self.name = name
        self.hint = int(hint)
        self.key_tag = sha1_str(name, key)[:10] if key else sha1_str(name)[:10]
        self.today = _dt.date.today().isoformat()
        self.used = 0
        self.observed_limit: Optional[int] = None   # 실측 한도 (020 이 온 시점의 사용량)
        self.exhausted = False
        self.blocked_reason = ""
        self._lk = threading.Lock()
        self._last_report = 0.0
        self._load()

    # ── 영속화 ------------------------------------------------------------------------
    def _path(self) -> str:
        base = VAULT.ns["private"] if VAULT is not None else "."
        return os.path.join(base, "index", f"quota_{self.name}_{self.key_tag}.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
        except Exception:
            return
        if j.get("date") == self.today:
            self.used = int(j.get("used", 0))
            self.exhausted = bool(j.get("exhausted", False))
        ol = j.get("observed_limit")
        if ol:
            self.observed_limit = int(ol)          # 한도 학습값은 날짜와 무관하게 유지
        if self.used or self.observed_limit:
            LOG.info(f"[{self.name}] 오늘 사용량 {self.used:,}건 이어받음 · "
                     f"한도 {self._limit_str()}")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps({
                "date": self.today, "used": self.used, "exhausted": self.exhausted,
                "observed_limit": self.observed_limit,
                "updated": _dt.datetime.now().isoformat(timespec="seconds"),
            }))
        except Exception:
            pass

    # ── 조회 --------------------------------------------------------------------------
    def limit(self) -> int:
        return int(self.observed_limit or self.hint)

    def _limit_str(self) -> str:
        return (f"{self.observed_limit:,} (실측)" if self.observed_limit
                else f"{self.hint:,} (고지값 추정)")

    def remaining(self) -> int:
        """남은 호출량. 실측 한도가 있으면 그것 기준, 없으면 고지값 기준.
        어느 쪽이든 이 값이 0이 되어도 **실제 020 이 오기 전까지는 멈추지 않는다**
        (추정이 틀렸을 수 있으므로 남아 있는 예산을 버리지 않는다)."""
        return max(0, self.limit() - self.used)

    def status_line(self) -> str:
        if self.exhausted:
            return f"[{self.name}] 소진 — 오늘 {self.used:,}건 사용 (실측 한도 {self.limit():,})"
        return (f"[{self.name}] 사용 {self.used:,} / 한도 {self._limit_str()} "
                f"· 잔여 약 {self.remaining():,}건")

    # ── 소비 --------------------------------------------------------------------------
    def take(self, k: int = 1) -> bool:
        """호출 직전에 예약한다. 소진이 '관측된' 뒤에만 False 를 돌려준다."""
        with self._lk:
            if self.exhausted:
                return False
            self.used += k
            if self.used % 250 == 0:
                self._save()
            now = time.time()
            if now - self._last_report > 30:
                self._last_report = now
                LOG.debug(self.status_line())
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.used = max(0, self.used - k)

    def mark_exhausted(self, reason: str = "status=020"):
        """소진을 **관측**했다. 이 시점의 사용량이 곧 실제 한도다 — 학습해서 다음에 쓴다."""
        with self._lk:
            if self.exhausted:
                return
            self.exhausted = True
            self.blocked_reason = reason
            prev = self.observed_limit
            self.observed_limit = int(self.used)
            self._save()
        LOG.warn(f"[{self.name}] 일일 호출 한도 소진을 확인했습니다 ({reason}). "
                 f"이번에 관측된 실제 한도는 {self.used:,}건입니다"
                 + (f" (직전 학습값 {prev:,})." if prev else ".") +
                 f" 지금까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 "
                 f"정확히 이 지점부터 이어받습니다. 이번 실행은 확보된 데이터만으로 계속합니다.")

    def mark_blocked(self, reason: str):
        """키 오류·IP 차단 등 한도와 무관한 차단. 재시도해도 소용없으므로 즉시 멈춘다."""
        with self._lk:
            self.exhausted = True
            self.blocked_reason = reason
            self._save()
        LOG.error(f"[{self.name}] 호출이 차단되었습니다 — {reason}. "
                  f"재시도하지 않고 이 소스를 건너뜁니다.")

    def close(self):
        self._save()

    def report(self):
        LOG.table([["오늘 사용량", f"{self.used:,}"],
                   ["한도", self._limit_str()],
                   ["잔여(추정)", f"{self.remaining():,}"],
                   ["소진 여부", ("예 — " + self.blocked_reason) if self.exhausted else "아니오"],
                   ["학습 방식", "실제 020 응답 시점의 사용량을 한도로 기록 → 다음 실행에서 사용"]],
                  ["항목", "값"], ["l", "r"],
                  title=f"{self.name} 호출 예산 (하드코딩 없음 · 실시간 추적)")


QUOTA: Dict[str, ApiQuota] = {}


def quota(name: str, hint: int = DART_LIMIT_HINT, key: str = "") -> ApiQuota:
    if name not in QUOTA:
        QUOTA[name] = ApiQuota(name, hint, key)
    return QUOTA[name]



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  통계 검증 커널 (§9)                                                                ║
# ║   ① 블록 부트스트랩   ② PBO(CSCV 정식)   ③ DSR(정식)   ④ 워크포워드                       ║
# ║   ⑤ 등가성 검정 TOST  ⑥ 패널 그레인저    ⑦ 이벤트스터디 CAR + 캘린더타임 유의성           ║
# ║                                                                                          ║
# ║  ★ 설계 원칙 — 표본이 부족하면 "판정불가(None)"를 돌려준다. 억지로 숫자를 만들지 않는다.    ║
# ║    p=0.51 을 "거의 유의"로 쓰는 것이 이 프로젝트에서 가장 해로운 행동이다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _sharpe_raw(r: np.ndarray) -> float:
    """기간(월) 단위 Sharpe. 연율화하지 않는다 — DSR 은 원단위 SR 을 쓴다."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return np.nan
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 1e-12 else np.nan


def ann_sharpe(r) -> float:
    s = _sharpe_raw(np.asarray(r, dtype=float))
    return float(s * math.sqrt(12)) if np.isfinite(s) else np.nan


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r, n_iter: int = 1000, block: int = 1, seed: int = SEED,
                    stat: Callable[[np.ndarray], float] = None) -> dict:
    """이동블록 부트스트랩. 월간 수익률의 자기상관을 보존한 채 재표본한다.

    명세는 '블록 21영업일'이라고 쓴다. 월간 시계열에서 21영업일 = 1개월이므로 block=1 이
    명세의 문자 그대로의 해석이고, 그건 사실상 iid 부트스트랩이다. 자기상관이 있으면
    iid 재표본이 신뢰구간을 과소추정하므로 block=3(분기)·6(반기)도 함께 보고한다.
    (블록 길이는 전략 파라미터가 아니라 추론 파라미터다 — 여러 개 보고해도 시행횟수에
     들어가지 않는다. §9-3 DSR 의 시행횟수는 §6.6 격자 12개 그대로다.)
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    stat = stat or (lambda x: float(np.mean(x)))
    if n < 12:
        return {"n": n, "point": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                "p_gt0": np.nan, "block": block, "verdict": "표본 부족(12개월 미만)"}
    rng = np.random.default_rng(seed)
    b = max(1, min(int(block), n))
    n_blocks = int(np.ceil(n / b))
    starts_max = n - b + 1
    out = np.empty(n_iter, dtype=float)
    for i in range(n_iter):
        st = rng.integers(0, starts_max, size=n_blocks)
        idx = (st[:, None] + np.arange(b)[None, :]).ravel()[:n]
        out[i] = stat(r[idx])
    point = stat(r)
    lo, hi = np.percentile(out, [2.5, 97.5])
    return {"n": n, "point": float(point), "ci_lo": float(lo), "ci_hi": float(hi),
            "p_gt0": float((out <= 0).mean()), "block": b, "iters": n_iter,
            "boot_mean": float(out.mean()),
            "verdict": "0 초과 (95% 신뢰구간이 0을 포함하지 않음)" if lo > 0 else
                       "0 미만" if hi < 0 else "0과 구분되지 않음"}


# ── ② PBO — Combinatorially Symmetric Cross-Validation (정식) ───────────────────────────────
def pbo_cscv(M, S: int = 10, max_combos: int = 400, seed: int = SEED) -> dict:
    """Bailey·Borwein·López de Prado·Zhu (2017) CSCV.

    M : (T × N) 행렬. 열 = 전략 구성(여기서는 §6.6 격자 12개), 행 = 월별 수익률.

    절차: 시계열을 S 개 인접 조각으로 나누고, S/2 개를 골라 IS(학습), 나머지를 OOS 로 둔다.
          IS 최적 구성 n* 의 OOS 상대순위 ω 를 구하고 로짓 λ=ln(ω/(1-ω)) 를 모은다.
          PBO = P(λ ≤ 0) = "IS 1등이 OOS 중앙값 아래로 떨어질 확률".

    ★ 기존 축약형(한 조각씩 빼는 leave-one-out)은 CSCV 가 아니다. 조합의 대칭성이
      깨져서 PBO 가 체계적으로 과소추정된다 — 과적합을 놓치는 방향이라 더 위험하다.
    """
    M = np.asarray(M, dtype=float)
    if M.ndim != 2:
        return {"pbo": np.nan, "verdict": "입력이 2차원 행렬이 아닙니다"}
    T, N = M.shape
    if N < 2 or T < 2 * S:
        return {"pbo": np.nan, "n_combos": 0, "N": N, "T": T,
                "verdict": f"표본 부족 (구성 {N}개, {T}개월 < 필요 {2*S}개월)"}
    # 결측 열 제거
    good = np.isfinite(M).all(axis=0)
    if good.sum() < 2:
        good = np.isfinite(M).mean(axis=0) > 0.9
        M = np.where(np.isfinite(M), M, 0.0)
    M = M[:, good]
    N = M.shape[1]
    if N < 2:
        return {"pbo": np.nan, "n_combos": 0, "verdict": "유효 구성이 2개 미만입니다"}

    S = int(S) - (int(S) % 2)                       # 짝수로
    S = max(4, min(S, T // 2))
    parts = np.array_split(np.arange(T), S)
    half = S // 2
    combos = list(itertools.combinations(range(S), half))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:                    # 조합 폭발 방지 — 균등 표집
        pick = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in sorted(pick)]

    lams, ranks = [], []
    for cb in combos:
        is_idx = np.concatenate([parts[i] for i in cb])
        oos_idx = np.concatenate([parts[i] for i in range(S) if i not in cb])
        if len(is_idx) < 4 or len(oos_idx) < 4:
            continue
        sr_is = np.array([_sharpe_raw(M[is_idx, j]) for j in range(N)])
        sr_oos = np.array([_sharpe_raw(M[oos_idx, j]) for j in range(N)])
        if not np.isfinite(sr_is).any() or not np.isfinite(sr_oos).any():
            continue
        nstar = int(np.nanargmax(sr_is))
        valid = np.isfinite(sr_oos)
        if valid.sum() < 2 or not valid[nstar]:
            continue
        # OOS 상대순위 ω ∈ (0,1). 순위 1등 = 1.0 근처
        order = np.argsort(np.argsort(np.where(valid, sr_oos, -np.inf)))
        w = (order[nstar] + 1) / (valid.sum() + 1)
        w = min(max(w, 1e-6), 1 - 1e-6)
        ranks.append(w)
        lams.append(math.log(w / (1 - w)))
    if not lams:
        return {"pbo": np.nan, "n_combos": 0, "verdict": "유효 조합이 없습니다"}
    lam = np.array(lams)
    pbo = float((lam <= 0).mean())
    return {"pbo": pbo, "n_combos": len(lam), "S": S, "N": N, "T": T,
            "median_oos_rank": float(np.median(ranks)),
            "verdict": ("과적합 위험 낮음 (PBO<0.5)" if pbo < 0.5 else
                        "★ 과적합 위험 높음 — IS 최적 구성이 OOS 에서 절반 이상 중앙값 아래")}


# ── ③ DSR — Deflated Sharpe Ratio (정식) ───────────────────────────────────────────────────
def deflated_sharpe(r, n_trials: int, sr_trials: Optional[Sequence[float]] = None) -> dict:
    """Bailey & López de Prado (2014).

    SR*  = sqrt(Var(SR_trials)) · [ (1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ]
    DSR  = Φ[ (SR̂ - SR*)·√(T-1) / √(1 - γ₃·SR̂ + (γ₄-1)/4·SR̂²) ]
    (γ = 오일러-마스케로니 0.5772, γ₃ = 왜도, γ₄ = 첨도(비초과))

    ★ SR̂ 과 SR* 는 **같은 단위(기간당)** 여야 한다. 연율화한 Sharpe 를 넣으면 DSR 이
      1.0 으로 붙어버려 아무것도 판정하지 못한다 — 기존 구현의 실패 모드가 이것이었다.
    ★ Var(SR_trials) 는 시행된 구성들의 Sharpe 분산이다. 주지 않으면 이론적 근사
      Var ≈ (1+SR̂²/2)/T 를 쓰되, 그 사실을 판정문에 명시한다.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    T = len(r)
    if T < 12:
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan,
                "verdict": "표본 부족(12개월 미만)"}
    try:
        from scipy import stats as _st
        Phi, Phi_inv = _st.norm.cdf, _st.norm.ppf
        skew = float(_st.skew(r, bias=False))
        kurt = float(_st.kurtosis(r, fisher=False, bias=False))
    except Exception:
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan, "verdict": "scipy 없음"}

    sr = _sharpe_raw(r)
    if not np.isfinite(sr):
        return {"dsr": np.nan, "sr": np.nan, "sr_star": np.nan, "verdict": "Sharpe 산출 불가"}

    N = max(2, int(n_trials))
    used_empirical = False
    if sr_trials is not None:
        v = np.asarray([x for x in sr_trials if np.isfinite(x)], dtype=float)
        if len(v) >= 3:
            var_sr = float(v.var(ddof=1))
            used_empirical = True
        else:
            var_sr = (1.0 + 0.5 * sr ** 2) / T
    else:
        var_sr = (1.0 + 0.5 * sr ** 2) / T
    var_sr = max(var_sr, 1e-12)

    g = 0.5772156649015329
    sr_star = math.sqrt(var_sr) * ((1 - g) * Phi_inv(1 - 1.0 / N) +
                                   g * Phi_inv(1 - 1.0 / (N * math.e)))
    denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2
    if denom <= 0:
        return {"dsr": np.nan, "sr": sr, "sr_star": sr_star,
                "verdict": "분모 비양수(극단 왜도/첨도) — 판정 불가"}
    z = (sr - sr_star) * math.sqrt(T - 1) / math.sqrt(denom)
    dsr = float(Phi(z))
    return {"dsr": dsr, "sr": float(sr), "sr_star": float(sr_star), "T": T,
            "n_trials": N, "skew": skew, "kurt": kurt,
            "var_source": "시행 구성들의 실측 분산" if used_empirical else "이론 근사(1+SR²/2)/T",
            "verdict": ("과적합 보정 후에도 유의 (DSR>0.95)" if dsr > 0.95 else
                        "보정 후 한계적 (0.90<DSR≤0.95)" if dsr > 0.90 else
                        "★ 과적합 보정 후 유의하지 않음")}


# ── ④ 워크포워드 (학습 5년 / 검증 1년 롤링) ─────────────────────────────────────────────────
def walk_forward(M, months, labels: Sequence[str], train_y: int = 5, test_y: int = 1) -> dict:
    """AAR 은 학습할 파라미터가 없다(전부 사전등록 고정). 그래서 워크포워드가 검정하는 것은
    '최적화'가 아니라 **구성 선택의 안정성**이다:

      학습창에서 가장 좋았던 구성을 그대로 다음 1년에 쓴다 → 그 OOS 성과가
      (a) 전체 구성 평균보다 좋은가  (b) 0보다 큰가

    (a)가 성립하지 않으면 "어느 구성이 좋은지는 과거로부터 알 수 없다"는 뜻이고,
    그건 12개 구성 중 좋은 것을 골라 보고하는 행위가 전부 사후선택이라는 증거다.
    """
    M = np.asarray(M, dtype=float)
    T, N = M.shape
    idx = pd.DatetimeIndex(months)
    rows = []
    tr, te = train_y * 12, test_y * 12
    if T < tr + te:
        return {"folds": 0, "verdict": f"표본 부족 ({T}개월 < 학습{tr}+검증{te})",
                "oos_mean": np.nan, "oos_t": np.nan, "table": pd.DataFrame()}
    picked_oos: List[float] = []
    avg_oos: List[float] = []
    for s in range(0, T - tr - te + 1, te):
        a, b, c = s, s + tr, min(s + tr + te, T)
        sr_is = np.array([_sharpe_raw(M[a:b, j]) for j in range(N)])
        if not np.isfinite(sr_is).any():
            continue
        j = int(np.nanargmax(sr_is))
        oos = M[b:c, j]
        allo = np.nanmean(M[b:c, :], axis=1)
        picked_oos.extend(oos[np.isfinite(oos)].tolist())
        avg_oos.extend(allo[np.isfinite(allo)].tolist())
        rows.append({
            "학습구간": f"{idx[a]:%Y-%m}~{idx[b-1]:%Y-%m}",
            "검증구간": f"{idx[b]:%Y-%m}~{idx[c-1]:%Y-%m}",
            "IS최적구성": labels[j] if j < len(labels) else str(j),
            "IS Sharpe": round(float(sr_is[j]) * math.sqrt(12), 3),
            "OOS 월평균": round(float(np.nanmean(oos)) * 100, 3),
            "전구성 OOS 평균": round(float(np.nanmean(allo)) * 100, 3),
            "판정": "선택이 유효" if np.nanmean(oos) > np.nanmean(allo) else "선택이 무효",
        })
    if not rows:
        return {"folds": 0, "verdict": "유효 폴드 없음", "oos_mean": np.nan,
                "oos_t": np.nan, "table": pd.DataFrame()}
    p = np.array(picked_oos)
    a = np.array(avg_oos)
    k = min(len(p), len(a))
    mu, t = hac_tstat(p[:k] - a[:k])
    mu_abs, t_abs = hac_tstat(p)
    wins = sum(1 for r in rows if r["판정"] == "선택이 유효")
    return {"folds": len(rows), "table": pd.DataFrame(rows),
            "oos_mean": float(np.nanmean(p)), "oos_t": t_abs,
            "excess_mean": mu, "excess_t": t, "wins": wins,
            "verdict": (f"{wins}/{len(rows)} 폴드에서 IS 최적 구성이 전구성 평균을 이겼습니다. "
                        f"OOS 월평균 {np.nanmean(p)*100:+.3f}%p (HAC t={t_abs:.2f}), "
                        f"선택 초과분 {mu*100:+.3f}%p (t={t:.2f}).")}


# ── ⑤ 등가성 검정 TOST — "효과 없음"을 주장하는 유일하게 정당한 방법 ────────────────────────
def tost_equivalence(x, bound: float, alpha: float = 0.05) -> dict:
    """귀무가설 채택은 증거가 아니다. "M-EXIT 는 예측력이 없다"를 주장하려면
    **효과가 실질적으로 무시 가능한 범위 안에 있다**를 적극적으로 보여야 한다.

    TOST: H01: θ ≤ -Δ,  H02: θ ≥ +Δ 를 각각 단측 검정해 둘 다 기각하면 '등가' 판정.
    Δ(bound)는 사전에 정한다 — 여기서는 V-DROP 효과의 절반. 즉 "M-EXIT 효과가
    V-DROP 의 절반에도 못 미친다"를 보인다. 사후에 Δ 를 조정하면 검정이 무의미해진다.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12 or not np.isfinite(bound) or bound <= 0:
        return {"equivalent": None, "n": n, "bound": bound,
                "verdict": "표본 부족 또는 등가범위 미정 — 판정 불가"}
    mu, t_hac = hac_tstat(x)
    se = abs(mu / t_hac) if (np.isfinite(t_hac) and abs(t_hac) > 1e-12) else (x.std(ddof=1) / math.sqrt(n))
    if not np.isfinite(se) or se <= 0:
        return {"equivalent": None, "n": n, "bound": bound, "verdict": "표준오차 산출 불가"}
    try:
        from scipy import stats as _st
        crit = float(_st.t.ppf(1 - alpha, n - 1))
        p_lo = float(_st.t.sf((mu + bound) / se, n - 1))       # H01: θ ≤ -Δ 기각용
        p_hi = float(_st.t.sf((bound - mu) / se, n - 1))       # H02: θ ≥ +Δ 기각용
    except Exception:
        crit, p_lo, p_hi = 1.65, np.nan, np.nan
    t1 = (mu + bound) / se
    t2 = (bound - mu) / se
    eq = bool(t1 > crit and t2 > crit)
    return {"equivalent": eq, "n": n, "mean": float(mu), "se": float(se), "bound": float(bound),
            "t_lower": float(t1), "t_upper": float(t2), "p": float(max(p_lo, p_hi)),
            "ci_lo": float(mu - crit * se), "ci_hi": float(mu + crit * se),
            "verdict": (f"등가 확인 — 효과가 ±{bound*100:.3f}%p 범위 안에 있습니다(무시 가능)."
                        if eq else
                        f"등가를 보이지 못했습니다 — 신뢰구간 [{mu-crit*se:+.4f}, {mu+crit*se:+.4f}] 이 "
                        f"±{bound:.4f} 를 벗어납니다. 표본이 작아서일 수도 있으므로 "
                        f"'효과가 있다'는 뜻은 아닙니다.")}


# ── ⑥ 패널 그레인저 인과 (H5 선행성) ────────────────────────────────────────────────────────
def panel_granger(df: "pd.DataFrame", cause: str, effect: str, entity: str = "code",
                  time: str = "month", lags: int = 3) -> dict:
    """개체 고정효과 패널에서 cause → effect 선행성을 F검정한다.

      effect(i,t) = Σ_{k=1..L} β_k·cause(i,t-k) + Σ_{k=1..L} γ_k·effect(i,t-k) + α_i + δ_t + ε
      H0: β_1=…=β_L=0

    ★ Nickell bias: 개체 FE + 시차종속변수 조합은 O(1/T) 편의를 갖는다. 여기서는
      T≈120개월이라 편의가 1% 미만이고, 우리가 보는 것은 β 의 크기가 아니라 **유의성과
      방향성 비교**이므로 실질적 영향이 없다. (양방향에 동일한 편의가 걸리므로 비교는 특히
      안전하다.) 표본이 짧아지면 그 사실을 판정문에 명시한다.
    """
    need = [c for c in (entity, time, cause, effect) if c not in df.columns]
    if need:
        return {"F": np.nan, "p": np.nan, "verdict": f"컬럼 없음 {need} — 판정 불가"}
    d = df[[entity, time, cause, effect]].copy()
    d[time] = as_ts_series(d[time])
    d = d.dropna(subset=[entity, time]).sort_values([entity, time])
    g = d.groupby(entity, observed=True)
    cols = []
    for k in range(1, lags + 1):
        d[f"_c{k}"] = g[cause].shift(k)
        d[f"_e{k}"] = g[effect].shift(k)
        cols += [f"_c{k}", f"_e{k}"]
    d = d.dropna(subset=[effect] + cols)
    if len(d) < 200:
        return {"F": np.nan, "p": np.nan, "n": len(d),
                "verdict": f"유효 관측 {len(d):,}행으로 부족합니다 — 판정 불가"}

    y = d[effect].to_numpy(dtype=float)
    ent_c, ent_k = factorize_codes(d[entity])
    tim_c, tim_k = factorize_codes(d[time])
    Xc = d[[f"_c{k}" for k in range(1, lags + 1)]].to_numpy(dtype=float)
    Xe = d[[f"_e{k}" for k in range(1, lags + 1)]].to_numpy(dtype=float)

    # 제한모형(원인 시차 제외) / 비제한모형 각각 FE 흡수 후 RSS 비교
    r_r, _, _, _ = absorb_fe(y, Xe, [ent_c, tim_c], [ent_k, tim_k])
    r_u, beta_u, keep_u, info = absorb_fe(y, np.column_stack([Xe, Xc]), [ent_c, tim_c],
                                          [ent_k, tim_k])
    rss_r = float(r_r @ r_r)
    rss_u = float(r_u @ r_u)
    q = int(np.sum(keep_u[-lags:])) if keep_u.size >= lags else lags
    n = len(y)
    dof = n - ent_k - tim_k - int(keep_u.sum()) - 1
    if q <= 0 or dof <= 10 or rss_u <= 0:
        return {"F": np.nan, "p": np.nan, "n": n, "verdict": "자유도 부족 — 판정 불가"}
    F = ((rss_r - rss_u) / q) / (rss_u / dof)
    try:
        from scipy import stats as _st
        p = float(_st.f.sf(max(F, 0.0), q, dof))
    except Exception:
        p = np.nan
    return {"F": float(F), "p": p, "n": n, "q": q, "dof": dof, "lags": lags,
            "converged": info.get("converged", True),
            "verdict": (f"{cause} → {effect} 선행성 F({q},{dof})={F:.2f}, p={p:.4g}")}


# ── ⑦ 이벤트 스터디 CAR + 캘린더타임 유의성 ─────────────────────────────────────────────────
def event_study_car(events: "pd.DataFrame", px_daily: "pd.DataFrame", bench_daily: "pd.Series",
                    horizon: int = 120, group_col: str = "exit_type") -> "pd.DataFrame":
    """군별 시장조정 CAR 곡선 (t+1 ~ t+H 영업일).

    ★ 시장모형(베타 추정) 대신 **시장조정**(초과수익 = 개별 - 시장)을 쓴다. 이유:
      철회 이벤트는 소형·저유동성 종목에 몰리는데, 그런 종목의 베타 추정치는
      비동시거래(non-synchronous trading) 때문에 심하게 편의되어 있다. 잘못 추정한 베타로
      조정하면 CAR 이 베타 오차를 보여줄 뿐이다. 시장조정은 편의가 없고 해석이 명확하다.

    ★ 겹치는 이벤트 창의 횡단면 상관 때문에 CAR 의 단순 t검정은 **표준오차를 크게
      과소추정한다.** 그래서 유의성 판정은 이 함수가 아니라 calendar_time_alpha() 로 한다.
      여기서는 곡선(설명용)과 평균만 낸다.
    """
    cols = ["group", "h", "mean_car", "median_car", "n", "se_naive"]
    if events is None or events.empty or px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    px = px_daily[["code", "date", "close"]].dropna().copy()
    px["date"] = as_ts_series(px["date"])
    px = px.sort_values(["code", "date"])
    px["ret"] = px.groupby("code", observed=True)["close"].pct_change()

    bm = pd.Series(bench_daily).copy()
    bm.index = as_ts_series(pd.Series(bm.index))
    dates = np.sort(px["date"].unique())
    dpos = {d: i for i, d in enumerate(dates)}
    px["_di"] = px["date"].map(dpos)
    px["_ex"] = px["ret"] - px["date"].map(bm).astype("float64")

    ex_by_code: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for c, g in px.dropna(subset=["_ex"]).groupby("code", observed=True):
        ex_by_code[str(c)] = (g["_di"].to_numpy(dtype=np.int64), g["_ex"].to_numpy(dtype=float))

    ev = events.copy()
    ev["event_date"] = as_ts_series(ev["event_date"] if "event_date" in ev.columns else ev["month"])
    rows = []
    for grp, gg in ev.groupby(group_col, observed=True):
        mat = np.full((len(gg), horizon), np.nan)
        for i, r in enumerate(gg.itertuples(index=False)):
            code = str(getattr(r, "code", ""))
            arr = ex_by_code.get(code)
            if arr is None:
                continue
            di, ex = arr
            t0 = int(np.searchsorted(dates, np.datetime64(getattr(r, "event_date")), side="right"))
            lo = int(np.searchsorted(di, t0, side="left"))
            seg = ex[lo:lo + horizon]
            if len(seg):
                mat[i, :len(seg)] = seg
        car = np.nancumsum(np.where(np.isfinite(mat), mat, 0.0), axis=1)
        valid = np.isfinite(mat).any(axis=1)
        car = car[valid]
        if not len(car):
            continue
        for h in range(horizon):
            v = car[:, h]
            v = v[np.isfinite(v)]
            if not len(v):
                continue
            rows.append({"group": str(grp), "h": h + 1, "mean_car": float(v.mean()),
                         "median_car": float(np.median(v)), "n": int(len(v)),
                         "se_naive": float(v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 1 else np.nan})
    return pd.DataFrame(rows, columns=cols)


def calendar_time_alpha(events: "pd.DataFrame", fwd: "pd.DataFrame", months,
                        hold_m: int = 6, group_col: str = "exit_type") -> "pd.DataFrame":
    """캘린더타임 포트폴리오 — 겹치는 이벤트 창의 횡단면 상관을 구조적으로 제거한다.

    매월, '최근 hold_m 개월 안에 이벤트가 있었던' 종목을 동일가중으로 담은 포트폴리오의
    시장초과수익 시계열을 만들고 그 평균을 HAC t 로 검정한다. 이벤트가 아무리 겹쳐도
    각 달의 관측은 하나뿐이므로 표준오차가 정직하다 (Fama 1998, Mitchell & Stafford 2000).
    """
    out_cols = ["group", "n_months", "mean_excess_m", "t_hac", "p", "ann_excess", "avg_names"]
    if events is None or events.empty or fwd is None or fwd.empty:
        return pd.DataFrame(columns=out_cols)
    ev = events.copy()
    ev["month"] = as_ts_series(ev["month"])
    F = fwd[["code", "month", "fwd_ret"]].dropna().copy()
    F["month"] = as_ts_series(F["month"])
    mkt = F.groupby("month", observed=True)["fwd_ret"].mean().rename("mkt")
    F = F.merge(mkt, on="month", how="left")
    F["ex"] = F["fwd_ret"] - F["mkt"]
    rows = []
    for grp, gg in ev.groupby(group_col, observed=True):
        series, counts = [], []
        for m in months:
            lo = add_months(m, -(hold_m - 1))
            names = set(gg.loc[(gg["month"] >= lo) & (gg["month"] <= m), "code"].astype(str))
            if not names:
                series.append(np.nan)
                counts.append(0)
                continue
            sub = F[(F["month"] == m) & (F["code"].astype(str).isin(names))]
            series.append(float(sub["ex"].mean()) if len(sub) else np.nan)
            counts.append(int(len(sub)))
        s = np.asarray(series, dtype=float)
        ok = s[np.isfinite(s)]
        if len(ok) < 12:
            rows.append({"group": str(grp), "n_months": int(len(ok)), "mean_excess_m": np.nan,
                         "t_hac": np.nan, "p": np.nan, "ann_excess": np.nan,
                         "avg_names": float(np.mean(counts)) if counts else 0.0})
            continue
        mu, t = hac_tstat(ok)
        rows.append({"group": str(grp), "n_months": int(len(ok)), "mean_excess_m": float(mu),
                     "t_hac": float(t), "p": t_to_p(t, dof=len(ok) - 1),
                     "ann_excess": float((1 + mu) ** 12 - 1),
                     "avg_names": float(np.mean([c for c in counts if c > 0]) if any(counts) else 0.0)})
    return pd.DataFrame(rows, columns=out_cols)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  marcap 로더 · PIT 유니버스 · PIT 시가총액 · 수정주가   (KRX 인증 완전 배제)         ║
# ║                                                                                          ║
# ║  ★★ 이 모듈이 이 프로젝트에서 가장 큰 시간 절약을 만든다. ★★                              ║
# ║                                                                                          ║
# ║  종전: 종목당 HTTP 1회 × 3,500종목 × 폴백체인 = 수천~수만 요청, 완전 캐시 상태에서도       ║
# ║        판단에만 13~15분.                                                                  ║
# ║  현재: **연도당 parquet 1개 × 11개 = 총 11회 다운로드로 전 종목·전 기간(1995~2026).**      ║
# ║        그마저 HTTP 캐시에 남아 두 번째 실행부터는 네트워크 0회다.                          ║
# ║                                                                                          ║
# ║  소스: FinanceData/marcap (raw.githubusercontent, 인증 불필요)                             ║
# ║    Date, Code, Name, Market, Dept, Close, ChangesRatio, Marcap, Stocks, Amount, Volume    ║
# ║                                                                                          ║
# ║  이 한 소스가 동시에 해결하는 것:                                                          ║
# ║   · PIT 유니버스   — 날짜별 단면이라 그날 실제 거래된 종목만 들어 있다                     ║
# ║   · 생존자편향     — 폐지 종목이 폐지일까지 존재하다 사라진다. **구조적으로 제거됨**       ║
# ║   · PIT 시가총액   — Marcap 컬럼이 이미 PIT 값 (Marcap == Close × Stocks, 오차 0 검증)     ║
# ║   · 상장주식수     — Stocks. 별도 시계열 재구성이 불필요                                   ║
# ║   · 실거래대금     — Amount (KRX 실측). close×volume 근사가 필요 없다                     ║
# ║   · 수정주가       — ChangesRatio 가 KRX 공식 수정등락률                                   ║
# ║                                                                                          ║
# ║  ⚠ Close 는 **무수정 원주가**다. 삼성전자 2018-05-04 50:1 분할일의 raw pct_change 는       ║
# ║    -98.04% 이고 ChangesRatio 는 -2.08% 다. 수익률에 Close 비율이나 Marcap 비율을           ║
# ║    쓰면 안 된다(§7-F1). Marcap 비율에는 주식수 변동이 섞여 유상증자일에 +1.75%/일의        ║
# ║    상방 편의가 생긴다. Marcap 은 **랭킹 전용**이다.                                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MARCAP_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet"
MARCAP_COLS = ["Date", "Code", "Name", "Market", "Dept", "Close", "ChangesRatio",
               "Marcap", "Stocks", "Amount", "Volume"]
FDR_LIST_URL = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                "refs/heads/master/data/{kind}/{date}.csv")

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "industry", "sector", "delist_reason", "delist_to", "src"]
CA_TOL = 2e-3          # ChangesRatio 는 소수 2자리 반올림 → 이보다 작은 차이는 반올림 잡음
CA_MAX_GAP_D = 7       # 연 경계·장기 거래정지 구간은 코퍼레이트액션 판정에서 제외


def _fdr_recent_csv(kind: str, back_days: int = 21) -> Optional["pd.DataFrame"]:
    """fdr_krx_data_cache 의 최신 CSV. delisting/desc 는 롤링이 아니라 매일 전량 갱신된다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        raw = http_get(FDR_LIST_URL.format(kind=kind, date=d.isoformat()), source="github",
                       as_bytes=True, tries=1, timeout=30, params={"_d": d.isoformat()})
        if not raw or len(raw) < 500:
            continue
        head = raw[:60].lstrip()
        if head.startswith(b"404") or head.startswith(b"<"):
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ToSymbol": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                LOG.debug(f"FDR 캐시 적중: {kind} @ {d.isoformat()} ({len(df):,}행)")
                return df
        except Exception:
            continue
    return None


# ── marcap 로더 ─────────────────────────────────────────────────────────────────────────────
def load_marcap(y0: int, y1: int) -> "pd.DataFrame":
    """연도별 parquet 을 **연속으로** 적재한다.

    ★ 연도 결손을 허용하면 안 된다. 2016 과 2018 을 이어붙이면 2018-01-02 의 pct_change 가
      2016-12-29 종가와 비교되어 존재하지 않는 코퍼레이트액션 계수가 만들어진다
      (실측: 삼성전자에 f=0.707 이라는 유령 계수 발생). 그래서 KillCriteria 로 세운다."""
    frames = []
    for y in range(y0, y1 + 1):
        b = http_get(MARCAP_URL.format(y=y), source="github", as_bytes=True, tries=3,
                     timeout=180, params={"_y": str(y)}, cache_ttl_days=(0.0 if y < _dt.date.today().year else 2.0))
        if b is None or len(b) < 1000:
            raise KillCriteria(
                f"marcap-{y}.parquet 을 받지 못했습니다. 연도 결손은 허용하지 않습니다 — "
                f"불연속 구간을 이어붙이면 가짜 코퍼레이트액션이 생겨 수익률이 조용히 "
                f"왜곡됩니다(§7-F2). 네트워크에서 raw.githubusercontent.com 접근을 확인하세요.")
        try:
            d = pd.read_parquet(io.BytesIO(b), columns=MARCAP_COLS)
        except Exception:
            d = pd.read_parquet(io.BytesIO(b))
            d = d[[c for c in MARCAP_COLS if c in d.columns]]
        frames.append(d)
        LOG.debug(f"  marcap-{y}: {len(d):,}행")
    m = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    m["Date"] = as_ts_series(m["Date"])
    m["Code"] = as_str_series(m["Code"]).str.zfill(6)
    for c in ("Market", "Dept", "Name"):
        if c in m.columns:
            m[c] = as_str_series(m[c])
    # ★ Marcap 은 조 단위라 float32 로 낮추면 유효자릿수가 깨진다. float64 유지.
    for c in ("Close", "ChangesRatio", "Marcap", "Stocks", "Amount", "Volume"):
        if c in m.columns:
            m[c] = pd.to_numeric(m[c], errors="coerce").astype("float64")
    m = m.dropna(subset=["Date", "Code", "Close"])
    m = m.sort_values(["Code", "Date"], kind="stable").reset_index(drop=True)

    lag_d = (pd.Timestamp.today().normalize() - m["Date"].max()).days
    if lag_d > 5:
        LOG.warn(f"marcap 최종 데이터일이 {lag_d}일 뒤처집니다({m['Date'].max():%Y-%m-%d}) — "
                 f"저장소 유지보수자 측 지연입니다. 과거분 parquet 은 확정 커밋이라 "
                 f"백테스트 재현성에는 영향이 없고, 위험은 최근 구간에 국한됩니다.")
    if lag_d > 25:
        LOG.error(f"marcap 신선도 위반({lag_d}일). 최근 구간 결과를 신뢰하지 마십시오.")
    LOG.ok(f"marcap 적재 {len(m):,}행 · {m['Code'].nunique():,}종목 · "
           f"{m['Date'].min():%Y-%m-%d}~{m['Date'].max():%Y-%m-%d} · {mem_mb(m):.0f}MB")
    PIPE.io("IN", "HTTP", "marcap", m, source="FinanceData/marcap")
    return m


def add_adjusted_close(m: "pd.DataFrame") -> "pd.DataFrame":
    """ChangesRatio 로 역수정 종가를 복원한다.

      f_t       = (1 + ChangesRatio_t/100) / (Close_t / Close_{t-1})     조정계수
      adj_t     = Close_t / Π_{u > t} f_u                                 역수정(back-adjust)

    ★ 방향 주의: **나눈다.** 곱하면 삼성전자 2016-01-04 이 24,101 대신 42,609,078 이 된다.
    ★ 3중 가드가 전부 필요하다: 이전값 존재 · 날짜 간격 ≤7일 · |f-1| > 반올림 잡음.
      하나라도 빠지면 연 경계나 반올림이 유령 계수를 만든다.
    """
    m = m.sort_values(["Code", "Date"], kind="stable").reset_index(drop=True)
    g = m.groupby("Code", observed=True, sort=False)
    prev = g["Close"].shift(1)
    gap_d = (m["Date"] - g["Date"].shift(1)).dt.days

    p = m["Close"] / prev.where(prev > 0)
    q = 1.0 + m["ChangesRatio"] / 100.0
    f = q / p.where(p > 0)
    ok = (prev.notna() & (prev > 0) & m["ChangesRatio"].notna()
          & gap_d.notna() & (gap_d <= CA_MAX_GAP_D)
          & f.notna() & ((f - 1.0).abs() > CA_TOL) & (f > 0.01) & (f < 100.0))
    m["_f"] = np.where(ok.to_numpy(), f.to_numpy(), 1.0)

    rev = m.iloc[::-1]
    revcum = rev.groupby("Code", observed=True, sort=False)["_f"].cumprod()
    m["_revcum"] = revcum.reindex(m.index)
    fwd = m["_revcum"] / m["_f"]                    # u > t 구간만 (자기 자신 제외)
    m["adj_close"] = m["Close"] / fwd.where(fwd > 0)
    m["ca_flag"] = ok.to_numpy()
    n_ca = int(ok.sum())
    LOG.info(f"코퍼레이트액션 감지 {n_ca:,}건 / {len(m):,} 종목일 "
             f"({100*n_ca/max(len(m),1):.3f}%) — 통상 0.05% 수준이면 정상입니다.")

    # 검산: 알려진 사례로 방향과 크기를 확인한다(로그에 남긴다).
    try:
        s = m[(m["Code"] == "005930")]
        if len(s):
            first = s.iloc[0]
            LOG.info(f"  역수정 검산 삼성전자 {first['Date']:%Y-%m-%d}: "
                     f"원종가 {first['Close']:,.0f} → 역수정 {first['adj_close']:,.1f} "
                     f"(2018년 50:1 분할 반영. 2016-01-04 기준 이론값 ≈ 24,100)")
    except Exception:
        pass
    return m.drop(columns=["_f", "_revcum"])


def _is_common_stock(code: "pd.Series", name: "pd.Series", dept: "pd.Series") -> "pd.Series":
    """보통주만 남긴다.

    ★ 우선주 판정은 **종목코드 끝자리** 로 한다. 이름의 '우' 포함으로 판정하면
      '대우', '우리' 가 오탐된다(실측 오탐 172 vs 정탐 118)."""
    c = as_str_series(code)
    ok = c.str.len().eq(6) & c.str[-1].eq("0")
    ok &= ~as_str_series(name).str.contains("스팩", na=False)
    ok &= ~as_str_series(dept).str.contains("SPAC", na=False, case=False)
    return ok


def fetch_delisting_master() -> "pd.DataFrame":
    """전체 상장폐지 이력 마스터 (1956~). 폐지 수익률의 '승계 vs 전손' 판정에 필수.

    ★ 무조건 결측 처리 → 손실 누락(상방 편향). 무조건 -100% → 피흡수합병 주주까지
      전손 처리(하방 편향). Reason/ToSymbol 로 반드시 분기한다(§2.5)."""
    cols = ["code", "name", "delisting_date", "listing_date", "market",
            "secugroup", "reason", "to_symbol"]
    d = _fdr_recent_csv("listing/delisting")
    if d is None or d.empty:
        LOG.error("상장폐지 마스터를 받지 못했습니다. marcap 단면이 생존자편향을 이미 제거하므로 "
                  "유니버스는 정확하지만, 폐지 종목의 최종 수익률을 '승계'와 '전손'으로 "
                  "가를 수 없어 보수적으로 전부 결측 처리합니다.")
        return pd.DataFrame(columns=cols)
    lm = {str(c).strip().lower(): c for c in d.columns}
    gc_ = lambda *ks: next((lm[k] for k in ks if k in lm), None)
    code_c = gc_("symbol", "code", "isu_srt_cd")
    if not code_c:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "code": as_str_series(d[code_c]).map(to_code6),
        "name": as_str_series(d[gc_("name") or code_c]),
        "delisting_date": as_ts_series(d[gc_("delistingdate", "delisting_date")]) if gc_("delistingdate", "delisting_date") else pd.NaT,
        "listing_date": as_ts_series(d[gc_("listingdate", "listing_date")]) if gc_("listingdate", "listing_date") else pd.NaT,
        "market": as_str_series(d[gc_("market")]).str.upper() if gc_("market") else "",
        "secugroup": as_str_series(d[gc_("secugroup", "kind")]) if gc_("secugroup", "kind") else "",
        "reason": as_str_series(d[gc_("reason")]) if gc_("reason") else "",
        "to_symbol": as_str_series(d[gc_("tosymbol")]).map(to_code6) if gc_("tosymbol") else None,
    }).dropna(subset=["code"])
    out = out.sort_values("delisting_date").drop_duplicates("code", keep="last")
    LOG.ok(f"상장폐지 마스터 {len(out):,}건 (폐지일 보유 {int(out['delisting_date'].notna().sum()):,} · "
           f"승계종목 지정 {int(out['to_symbol'].notna().sum()):,})")
    VAULT.put_table("krx_delisting_master", out, scope="shared", domain="universe",
                    source="fdr_krx_data_cache listing/delisting")
    return out


SUCCEED_PAT = re.compile(r"(합병|포괄적\s*주식교환|주식의\s*포괄적|지주회사|완전자회사)")


def classify_delisting(dl: "pd.DataFrame") -> Dict[str, str]:
    """code → 'SUCCEED' | 'WIPEOUT' | 'UNKNOWN'."""
    if dl is None or dl.empty:
        return {}
    out: Dict[str, str] = {}
    for r in dl.itertuples(index=False):
        if isinstance(getattr(r, "to_symbol", None), str) and r.to_symbol:
            out[r.code] = "SUCCEED"
        elif SUCCEED_PAT.search(str(getattr(r, "reason", "") or "")):
            out[r.code] = "SUCCEED"
        else:
            out[r.code] = "WIPEOUT"
    return out


def fetch_listing_desc() -> "pd.DataFrame":
    """상장일·업종 마스터. KIND 를 완전히 대체한다(커버리지 100% 실측)."""
    d = _fdr_recent_csv("listing/desc")
    if d is None or d.empty:
        LOG.info("listing/desc 를 받지 못했습니다 — 상장일은 marcap 최초 관측일로 대체합니다"
                 "(그 경우 시즈닝이 보수적으로 늦어질 뿐 미래누수는 없습니다).")
        return pd.DataFrame(columns=["code", "listing_date", "sector", "industry"])
    lm = {str(c).strip().lower(): c for c in d.columns}
    gc_ = lambda *ks: next((lm[k] for k in ks if k in lm), None)
    code_c = gc_("code", "symbol")
    if not code_c:
        return pd.DataFrame(columns=["code", "listing_date", "sector", "industry"])
    out = pd.DataFrame({
        "code": as_str_series(d[code_c]).map(to_code6),
        "listing_date": as_ts_series(d[gc_("listingdate")]) if gc_("listingdate") else pd.NaT,
        "sector": as_str_series(d[gc_("sector")]) if gc_("sector") else "",
        "industry": as_str_series(d[gc_("industry")]) if gc_("industry") else "",
    }).dropna(subset=["code"]).drop_duplicates("code")
    LOG.ok(f"상장정보(desc) {len(out):,}건 (상장일 {int(out['listing_date'].notna().sum()):,})")
    return out


# ── 통합 빌더 (메모 캐시) ───────────────────────────────────────────────────────────────────
def build_market_data(y0: int, y1: int) -> Dict[str, "pd.DataFrame"]:
    """marcap → (월말 단면, 일별 수익률, 종목 마스터). 무거운 파싱은 최초 1회뿐이다.

    반환:
      monthly : code, month, date, adj_close, marcap, stocks, amount, adv20, market, dept
      daily   : code, date, ret (ChangesRatio/100 = KRX 공식 수정등락률)
      sec     : 종목 마스터 (상장일/폐지일/업종/폐지사유)
    """
    fp = fingerprint_of("marketdata", y0, y1, "v3", BACKTEST_START, BACKTEST_END)

    def _build() -> "pd.DataFrame":
        m = load_marcap(y0, y1)
        m = add_adjusted_close(m)
        return m

    # 원본 전체를 메모에 담으면 수백 MB 라 오히려 느리다. 파생 3종만 각각 메모한다.
    m: Optional["pd.DataFrame"] = None

    def _need_raw():
        nonlocal m
        if m is None:
            m = _build()
        return m

    def _mk_daily() -> "pd.DataFrame":
        mm = _need_raw()
        d = pd.DataFrame({
            "code": mm["Code"], "date": mm["Date"],
            "ret": (mm["ChangesRatio"] / 100.0).astype("float32"),
            "adj_close": mm["adj_close"].astype("float64"),
            "amount": mm["Amount"].astype("float64"),
        })
        # 정리매매·오류틱 방어: ±60% 초과 일간 수익은 결측 처리(가격제한은 ±30%)
        d.loc[d["ret"].abs() > 0.60, "ret"] = np.nan
        return d

    def _mk_monthly() -> "pd.DataFrame":
        mm = _need_raw()
        x = mm[["Code", "Date", "adj_close", "Close", "Marcap", "Stocks", "Amount",
                "Volume", "Market", "Dept", "Name"]].copy()
        x = x.sort_values(["Code", "Date"], kind="stable")
        x["adv20"] = (x.groupby("Code", observed=True)["Amount"]
                       .transform(lambda s: s.rolling(20, min_periods=10).mean()))
        x["ym"] = x["Date"].values.astype("datetime64[M]")
        last = x.groupby(["Code", "ym"], observed=True).tail(1).copy()
        last["month"] = as_ts_series(last["ym"]) + pd.offsets.MonthEnd(0)
        # 익영업일 종가 = 체결가 (§7 — 신호 산출일 익영업일 앵커)
        nx = x[["Code", "Date", "adj_close"]].copy()
        nx["next_close"] = nx.groupby("Code", observed=True)["adj_close"].shift(-1)
        nx["next_date"] = nx.groupby("Code", observed=True)["Date"].shift(-1)
        last = last.merge(nx[["Code", "Date", "next_close", "next_date"]],
                          on=["Code", "Date"], how="left")
        out = last.rename(columns={"Code": "code", "Date": "signal_date", "Marcap": "marcap",
                                   "Stocks": "stocks", "Amount": "amount", "Volume": "volume",
                                   "Market": "market", "Dept": "dept", "Name": "name"})
        return out[["code", "month", "signal_date", "adj_close", "Close", "next_close",
                    "next_date", "marcap", "stocks", "amount", "volume", "adv20",
                    "market", "dept", "name"]]

    daily = VAULT.memo_table("marcap_daily", fingerprint_of(fp, "daily"), _mk_daily,
                             scope="shared", domain="price", note="일별 수정수익률")
    monthly = VAULT.memo_table("marcap_monthly", fingerprint_of(fp, "monthly"), _mk_monthly,
                               scope="shared", domain="price", note="월말 단면")
    for df, c in ((daily, "date"), (monthly, "month")):
        if df is not None and len(df):
            df[c] = as_ts_series(df[c])
    if "signal_date" in monthly.columns:
        monthly["signal_date"] = as_ts_series(monthly["signal_date"])
        monthly["next_date"] = as_ts_series(monthly["next_date"])
    daily["code"] = as_str_series(daily["code"])
    monthly["code"] = as_str_series(monthly["code"])

    # ── 종목 마스터 ────────────────────────────────────────────────────────────────────
    def _mk_sec() -> "pd.DataFrame":
        obs = monthly.groupby("code", observed=True).agg(
            name=("name", "last"), market=("market", "last"), dept=("dept", "last"),
            first_obs=("month", "min"), last_obs=("month", "max"))
        obs = obs.reset_index()
        desc = fetch_listing_desc()
        dl = fetch_delisting_master()
        s = obs.merge(desc, on="code", how="left")
        s = s.merge(dl[["code", "delisting_date", "reason", "to_symbol", "secugroup"]],
                    on="code", how="left")
        s["listing_date_src"] = np.where(s["listing_date"].notna(), "desc", "marcap최초관측")
        s["listing_date"] = s["listing_date"].fillna(s["first_obs"])
        # 폐지일이 명단에 없는데 관측이 끊긴 종목 → 마지막 관측월 말일을 폐지로 추정
        last_all = monthly["month"].max()
        gone = s["delisting_date"].isna() & (s["last_obs"] < last_all - pd.offsets.MonthEnd(2))
        s.loc[gone, "delisting_date"] = s.loc[gone, "last_obs"] + pd.offsets.MonthEnd(1)
        s.loc[gone, "reason"] = s.loc[gone, "reason"].fillna("관측중단(추정)")
        s["industry"] = as_str_series(s.get("industry", "")).replace("", "미분류")
        # ★ Series.replace("", other_series) 는 pandas 가 거부한다(스칼라→Series 치환 불가).
        #   where 로 조건 치환해야 한다.
        _sec = as_str_series(s.get("sector", ""))
        s["sector"] = _sec.where(_sec.str.strip() != "", s["industry"]).replace("", "미분류")
        s["delist_reason"] = as_str_series(s.get("reason", ""))
        s["delist_to"] = s.get("to_symbol")
        s["src"] = "marcap+desc+delisting"
        return s

    sec = VAULT.memo_table("security_master_aar", fingerprint_of(fp, "sec"), _mk_sec,
                           scope="shared", domain="universe", note="종목 마스터")
    for c in ("listing_date", "delisting_date", "first_obs", "last_obs"):
        if c in sec.columns:
            sec[c] = as_ts_series(sec[c])
    sec["code"] = as_str_series(sec["code"])

    n_del = int(sec["delisting_date"].notna().sum())
    LOG.table([["일별 관측", f"{len(daily):,}"],
               ["월말 단면", f"{len(monthly):,}"],
               ["고유 종목", f"{len(sec):,}"],
               ["폐지 이력 보유", f"{n_del:,} ({100*n_del/max(len(sec),1):.1f}%)"],
               ["시총 보유 월행", f"{int(monthly['marcap'].notna().sum()):,}"],
               ["실거래대금 보유", f"{int(monthly['amount'].notna().sum()):,}"]],
              ["항목", "값"], ["l", "r"], title="marcap 기반 시장 데이터 (KRX 인증 없이)")
    if n_del < 1000:
        LOG.warn(f"폐지 이력이 {n_del:,}건으로 예상(≈4,000)보다 적습니다. "
                 f"★ 이 전략은 특히 위험합니다 — 커버리지 철회 신호가 폐지 직전 종목에 "
                 f"집중되므로 폐지 종목이 빠지면 H3(음의 신호)가 통째로 사라집니다.")
    m = None
    gc.collect()
    return {"daily": daily, "monthly": monthly, "sec": sec}


# ── PIT 유니버스 ────────────────────────────────────────────────────────────────────────────
def build_pit_universe(monthly: "pd.DataFrame", months: "pd.DatetimeIndex") -> "pd.DataFrame":
    """월별 PIT 유니버스 + 재랭킹.

    ★ marcap 의 Rank 컬럼을 그대로 쓰면 안 된다. KONEX·우선주·신주인수권이 섞여 있어
      '시총 하위 1000' 이 우선주와 KONEX 로 오염된다(실측: 2016-08-31 최하위 Rank 가 KONEX).
      반드시 필터한 뒤 **재랭킹**한다."""
    u = monthly[monthly["month"].isin(months)].copy()
    n0 = len(u)
    u = u[as_str_series(u["market"]).str.upper().isin(["KOSPI", "KOSDAQ"])]
    n1 = len(u)
    u = u[_is_common_stock(u["code"], u["name"], u["dept"])]
    n2 = len(u)
    u = u[pd.to_numeric(u["marcap"], errors="coerce") > 0]
    n3 = len(u)
    u["size_rank"] = (u.groupby("month", observed=True)["marcap"]
                       .rank(method="first", ascending=True))
    u["size_pct"] = (u.groupby("month", observed=True)["marcap"]
                      .rank(pct=True, ascending=True).astype("float32"))
    u["n_month"] = u.groupby("month", observed=True)["code"].transform("size")
    LOG.table([["월행 원본", f"{n0:,}", ""],
               ["KOSPI/KOSDAQ (KONEX 제외)", f"{n1:,}", f"{100*n1/max(n0,1):.1f}%"],
               ["보통주 (우선주·스팩 제외)", f"{n2:,}", f"{100*n2/max(n1,1):.1f}%"],
               ["시총 > 0", f"{n3:,}", f"{100*n3/max(n2,1):.1f}%"],
               ["월평균 종목수", f"{u.groupby('month')['code'].size().mean():,.0f}", ""]],
              ["필터 단계", "잔존 월행", "직전 대비"], ["l", "r", "r"],
              title="PIT 유니버스 필터 체인 (필터 후 재랭킹 — marcap 의 Rank 는 쓰지 않음)")
    PIPE.io("OUT", "MEM", "pit_universe", u)
    return u


def apply_universe_variant(uni: "pd.DataFrame", variant: str) -> "pd.DataFrame":
    """FULL = PIT 전체 / SMALL1000 = 시총 하위 SMALLCAP_N (오름차순 rank ≤ N)."""
    if variant == "SMALL1000":
        out = uni[uni["size_rank"] <= SMALLCAP_N].copy()
        sz = out.groupby("month", observed=True)["code"].size()
        LOG.info(f"[SMALL1000] 시총 하위 {SMALLCAP_N:,} 압축 — 월별 종목수 "
                 f"min {int(sz.min()):,} / median {int(sz.median()):,} / max {int(sz.max()):,}")
        return out
    return uni.copy()


# ── PIT 저장소 ──────────────────────────────────────────────────────────────────────────────
class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, "pd.DataFrame"] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: "pd.DataFrame", key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[PIT 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        self._t[name] = d.reset_index(drop=True)
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def names(self) -> List[str]:
        return sorted(self._t)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> "pd.DataFrame":
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        d = self._t[name]
        if d.empty:
            return d
        pos = int(np.searchsorted(d["knowledge_date"].values,
                                  np.datetime64(as_ts(as_of)), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def report(self):
        rows = [[n, f"{m['rows']:,}", str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                 ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n, 0):,}"]
                for n, m in self._meta.items()]
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()

LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    """월별 유니버스 조회 + 감쇠 감사.

    marcap 단면이 이미 '그날 실제 거래된 종목'이므로 상장/폐지 판정은 관측 자체가 근거다.
    상장일 시즈닝만 추가로 적용한다."""

    def __init__(self, uni_month: "pd.DataFrame", sec: "pd.DataFrame"):
        self.attrition: List[dict] = []
        self._by_month: Dict["pd.Timestamp", List[str]] = {}
        for m, g in uni_month.groupby("month", observed=True):
            self._by_month[as_ts(m)] = sorted(as_str_series(g["code"]).tolist())
        s = sec.drop_duplicates("code")
        self._listing = dict(zip(as_str_series(s["code"]), as_ts_series(s["listing_date"])))
        self._delist = {c: d for c, d in zip(as_str_series(s["code"]),
                                             as_ts_series(s["delisting_date"])) if pd.notna(d)}
        # ★ 시즈닝 앵커는 '상장일'이다. 패널 시작일을 앵커로 잡으면 기존 상장사 전부가
        #   백테스트 첫 1년 동안 유니버스에서 사라진다 — 에러도 경고도 없이.
        self._seasoned = {c: (ld + pd.Timedelta(days=365)) if pd.notna(ld) else pd.NaT
                          for c, ld in self._listing.items()}

    def at(self, t) -> List[str]:
        t = as_ts(t)
        base = self._by_month.get(t, [])
        return [c for c in base
                if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]

    def delisting_map(self) -> Dict[str, "pd.Timestamp"]:
        return dict(self._delist)

    def audit_row(self, stage: str, t, codes):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["PIT유니버스", "시즈닝통과", "유동성필터", "신호보유(U)", "Q5선정",
                 "배제후최종"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max"])
        rows, prev = [], None
        for s in order:
            if s not in piv.index:
                continue
            r = piv.loc[s]
            keep = "" if prev is None else f"{100*r['mean']/max(prev,1e-9):.1f}%"
            rows.append([s, f"{r['mean']:,.0f}", f"{r['min']:,.0f}", f"{r['max']:,.0f}", keep])
            prev = r["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < PORT_MIN_NAMES:
            LOG.warn(f"최종 보유가 월평균 {rows[-1][1]}종목으로 하한({PORT_MIN_NAMES})에 미달합니다. "
                     f"임계값을 손대기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 패널 — 월말 스냅샷 · 익영업일 체결 · 보유기간별 forward return · 폐지 처리     ║
# ║                                                                                          ║
# ║  가격 원천은 10_universe 의 marcap 로더가 이미 만들어 두었다(연도 parquet 11개).           ║
# ║  이 모듈은 그것을 백테스트가 먹을 수 있는 형태로 바꾸기만 한다 — 네트워크 접근 없음.       ║
# ║                                                                                          ║
# ║  · 체결가  = 신호 산출일의 **익영업일 종가** (§1-1 익영업일 앵커). 당일 종가는 미래누수.   ║
# ║  · 수익률  = 수정종가 비율. **Marcap 비율 금지**(주식수 변동이 섞여 상방 편의, §7-F1).     ║
# ║  · 폐지    = 승계(합병 등)면 결측, 전손이면 -100%. 일괄 처리는 양방향 모두 편향이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def build_price_panel(monthly: "pd.DataFrame", months: "pd.DatetimeIndex",
                      max_hold: int = 3) -> "pd.DataFrame":
    """월말 패널 + 1~max_hold 개월 forward return.

    ★ forward return 은 '정확히 k개월 뒤'와만 짝지어야 한다. 거래가 끊겨 중간 달이
      패널에서 빠지면 shift(-k) 가 몇 달 뒤 가격을 끌어와 k개월 수익으로 둔갑시킨다
      (수익 과대계상). 인접성 검사로 봉인한다."""
    m = monthly[monthly["month"].isin(months)].copy()
    m = m.sort_values(["code", "month"], kind="stable").reset_index(drop=True)

    # 체결가 = 익영업일 종가. 다음 거래일이 너무 멀면(거래정지·상폐 직전) 그 가격으로
    # 체결했다고 가정할 수 없으므로 당월 말 수정종가로 폴백한다.
    gap = (m["next_date"] - m["signal_date"]).dt.days
    m["exec_px"] = m["next_close"].where(gap.notna() & (gap <= 10))
    m["exec_px"] = m["exec_px"].fillna(m["adj_close"])

    g = m.groupby("code", observed=True)
    mnum = m["month"].dt.year * 12 + m["month"].dt.month
    for k in range(1, max_hold + 1):
        nxt_px = g["exec_px"].shift(-k)
        nxt_mn = g["month"].shift(-k)
        adjacent = ((nxt_mn.dt.year * 12 + nxt_mn.dt.month) - mnum) == k
        m[f"fwd_ret{k}"] = (nxt_px / m["exec_px"].where(m["exec_px"] > 0) - 1.0).where(adjacent)
    m["fwd_ret"] = m["fwd_ret1"]

    n_gap = int((g["month"].shift(-1).notna() & m["fwd_ret1"].isna()).sum())
    if n_gap:
        LOG.info(f"월 연속성이 끊긴 {n_gap:,}건의 fwd_ret 을 결측 처리했습니다 "
                 f"(건너뛴 달의 수익을 한 달 수익으로 계상하지 않기 위함). "
                 f"상장폐지 구간은 아래 apply_delisting_returns 가 별도 처리합니다.")
    PIPE.io("OUT", "MEM", "price_panel_monthly", m)
    return downcast(m)


def apply_delisting_returns(panel: "pd.DataFrame", sec: "pd.DataFrame",
                            max_hold: int = 3) -> "pd.DataFrame":
    """상장폐지 월의 forward return 을 '승계 vs 전손'으로 갈라 채운다 (§2.5).

    ★ 무조건 결측 → 손실 누락(상방 편향).  무조건 -100% → 피흡수합병 주주까지 전손
      (하방 편향).  둘 다 틀리므로 폐지 사유로 분기한다.
        · SUCCEED (합병·주식교환·지주회사 전환) : 주주는 대가를 받았다 → 결측(사건 제외)
        · WIPEOUT (상장폐지기준 해당 등)        : -100%
    """
    if panel is None or panel.empty or sec is None or sec.empty:
        return panel
    kind = classify_delisting(
        sec.rename(columns={"delist_reason": "reason", "delist_to": "to_symbol"})
           [["code", "delisting_date", "reason", "to_symbol"]].dropna(subset=["delisting_date"]))
    dl = dict(zip(as_str_series(sec["code"]), as_ts_series(sec["delisting_date"])))
    p = panel.copy()
    codes = as_str_series(p["code"])
    dser = codes.map(dl)
    kser = codes.map(kind)
    n_wipe = n_succ = 0
    for k in range(1, max_hold + 1):
        col = f"fwd_ret{k}"
        if col not in p.columns:
            continue
        horizon_end = p["month"] + pd.offsets.MonthEnd(k)
        within = dser.notna() & (dser > p["month"]) & (dser <= horizon_end)
        wipe = within & (kser == "WIPEOUT") & p[col].isna()
        succ = within & (kser != "WIPEOUT")
        p.loc[wipe, col] = -1.0
        p.loc[succ & p[col].isna(), col] = np.nan       # 승계는 사건 제외(결측 유지)
        if k == 1:
            n_wipe, n_succ = int(wipe.sum()), int(succ.sum())
    p["fwd_ret"] = p["fwd_ret1"]
    LOG.info(f"상장폐지 수익률 처리 — 전손(-100%) {n_wipe:,}건 · "
             f"승계(합병 등, 사건 제외) {n_succ:,}건. "
             f"일괄 처리하지 않는 이유: 전자만 하면 상방 편향, 후자만 하면 하방 편향입니다.")
    return p


def benchmark_series(months: "pd.DatetimeIndex", daily: "pd.DataFrame",
                     uni_month: "pd.DataFrame", panel: "pd.DataFrame"
                     ) -> Tuple[Dict[str, "pd.Series"], "pd.Series"]:
    """벤치마크 4종 + 일별 시장수익(이벤트 스터디의 시장조정용).

    §8: KOSPI, KOSDAQ, **동일가중 유니버스**, 그리고 **'단순 리포트 건수 증가' 나이브 신호**.
    마지막이 진짜 비교 대상이다 — §6.3 통제의 가치를 보여주는 유일한 벤치마크이기 때문이다.
    (나이브 신호는 32_signal 에서 만들어 백테스트로 돌리므로 여기서는 앞 3종만 만든다)

    ★ 지수 데이터를 못 받아도 동일가중 유니버스는 항상 있으므로 비교가 끊기지 않는다.
    """
    out: Dict[str, "pd.Series"] = {}
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
    if not out:
        LOG.info("지수(KOSPI/KOSDAQ) 시계열을 받지 못했습니다 — 동일가중 유니버스 벤치마크로 "
                 "비교합니다(§8 의 핵심 벤치마크는 원래 동일가중 유니버스입니다).")

    # 동일가중 유니버스 — 이 전략의 1차 비교 대상 (§11 ACCEPT 조건이 이것 대비 +3%p)
    if panel is not None and len(panel):
        ew = (panel.dropna(subset=["fwd_ret"])
                   .groupby("month", observed=True)["fwd_ret"].mean().reindex(months))
        out["동일가중유니버스"] = ew

    daily_mkt = pd.Series(dtype="float64")
    if daily is not None and len(daily):
        dd = daily.dropna(subset=["ret"])
        daily_mkt = dd.groupby("date")["ret"].mean()
    return out, daily_mkt



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 실적발표월 · 월별 공시건수  (§6.3 통제회귀의 두 입력만 받는다)                ║
# ║                                                                                          ║
# ║  ★ 이 전략은 재무제표를 받지 않는다. 필요한 것은 딱 두 가지뿐이다:                          ║
# ║      ① EarningsMonth(i,t)     — 그 달에 i의 정기보고서 접수가 있었는가                     ║
# ║      ② DisclosureCount(i,t)   — 그 달에 i의 공시가 몇 건이었는가                           ║
# ║    둘 다 **시장 전체를 날짜로 훑는** list.json 스윕으로 얻는다. 회사별 호출이 아니다.       ║
# ║                                                                                          ║
# ║  호출량 산정 (왜 한도가 문제되지 않는가):                                                   ║
# ║    120개월 × 공시유형 2종(A정기·B주요사항) × 시장 2종(유가·코스닥) = 480 스윕              ║
# ║    스윕당 평균 2~4페이지 → **총 1,000~2,000 호출**. 일일 한도의 5~10%.                     ║
# ║    게다가 한 번 받으면 공용 인덱스에 영구 저장되어 다른 전략도 그대로 재사용한다.           ║
# ║    (이전 세대가 한도를 태운 건 회사×분기 재무제표를 단건으로 받았기 때문이지,               ║
# ║     DART 자체가 부족해서가 아니다.)                                                        ║
# ║                                                                                          ║
# ║  ★ 키가 없어도 파이프라인은 돌아간다. 법정 제출기한 기반 달력 폴백이 있고,                  ║
# ║    그 사실을 통제회귀 진단표에 명시한다(조용히 넘어가지 않는다).                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}
# 정기보고서 = 실적발표. 이것이 EarningsMonth 의 정의다.
PERIODIC_PAT = re.compile(r"(사업보고서|반기보고서|분기보고서)")
DISCLOSURE_TYPES = ("A", "B")        # A=정기공시, B=주요사항보고(유증·M&A·자사주 등 강제발간 유발)
CORP_CLASSES = ("Y", "K")            # Y=유가증권, K=코스닥


def dart_api(endpoint: str, params: dict, tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계한다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다.
    → 캐시 적중이면 네트워크에 안 나가므로 예산을 아예 쓰지 않는다."""
    if not DART_API_KEY:
        return None
    q = quota("DART", key=DART_API_KEY)
    if q.exhausted:
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY

    # 캐시 우선 — 예산을 쓰기 전에 확인한다
    cached = None
    if VAULT is not None and CACHE_EVERYTHING:
        cached = VAULT.get_http(DART_BASE + endpoint, p, "dart",
                                ttl_days=_cache_ttl_for(params, "dart"))
    if cached is not None:
        try:
            js = json.loads(cached.decode("utf-8", "replace"))
        except Exception:
            js = None
        if isinstance(js, dict):
            with _HTTP_LK:
                HTTP_STATS["dart:CACHE"] += 1
            return js if str(js.get("status", "000")) == "000" else None

    if not q.take(tries):
        return None
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/",
                   on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    q.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            q.mark_exhausted(f"status={st} ({DART_STATUS_MSG.get(st, '?')})")
        elif st in ("010", "011", "012", "901"):
            q.mark_blocked(f"status={st} ({DART_STATUS_MSG.get(st, '?')}) — DART_API_KEY 확인 필요")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def fetch_dart_corpcode() -> "pd.DataFrame":
    """corp_code ↔ 종목코드. 호출 1건. 공용 캐시라 다른 전략도 그대로 쓴다."""
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용 (호출 0건)")
        return cached
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    q = quota("DART", key=DART_API_KEY)
    if not q.take(1):
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    raw = http_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=2)
    if not raw:
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 와 네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    if raw[:2] != b"PK":
        body = raw[:400].decode("utf-8", "ignore")
        st = re.search(r'"?status"?\s*[:>]\s*"?(\d{3})', body)
        code = st.group(1) if st else "?"
        LOG.warn(f"corpCode 응답이 ZIP 이 아닙니다 (status={code}: "
                 f"{DART_STATUS_MSG.get(code, '알 수 없음')}). DART_API_KEY 를 확인하세요.")
        if code in ("020", "021"):
            q.mark_exhausted(f"status={code}")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml")) \
            or zf.read(zf.namelist()[0])
    except Exception as e:                                            # noqa
        LOG.warn(f"corpCode zip 해제 실패({type(e).__name__}).")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    txt = _decode(xml, None, "corpcode")
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", txt, re.S):
        blk = m.group(1)

        def g(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return (mm.group(1).strip() if mm else "")
        rows.append({"corp_code": g("corp_code"), "corp_name": g("corp_name"),
                     "code": to_code6(g("stock_code"))})
    d = pd.DataFrame(rows)
    if len(d):
        VAULT.put_table("dart_corpcode", d, scope="shared", domain="dart", source="opendart")
    LOG.ok(f"DART corpCode {len(d):,}건 (상장 매칭 {int(d['code'].notna().sum()):,}건) — 호출 1건")
    return d


def fetch_dart_disclosures(start: str, end: str) -> "pd.DataFrame":
    """월 단위 시장 전체 공시목록 스윕. 미수집 월만 받고 공용 인덱스에 누적한다."""
    cols = ["code", "corp_code", "rcept_no", "rcept_dt", "report_nm", "is_periodic",
            "event_date", "knowledge_date"]
    cached = VAULT.get_table("dart_disclosures_slim", scope="shared")
    have_months: set = set()
    frames: List["pd.DataFrame"] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.strftime("%Y-%m"))
        frames.append(cached)
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}건 / {len(have_months)}개월 재사용 (호출 0건)")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED" or not DART_API_KEY:
        if todo and not DART_API_KEY:
            LOG.warn(f"DART_API_KEY 미입력 — 공시 {len(todo)}개월을 수집하지 않습니다. "
                     f"§6.3 통제회귀는 EarningsMonth 를 법정 제출기한 달력으로 대체하고 "
                     f"DisclosureCount 는 제외합니다. 그 사실이 통제 진단표에 표시됩니다.")
        todo = []

    if todo:
        q = quota("DART", key=DART_API_KEY)
        est = len(todo) * len(DISCLOSURE_TYPES) * len(CORP_CLASSES) * 3
        LOG.info(f"DART 공시 스윕 {len(todo)}개월 × 유형 {len(DISCLOSURE_TYPES)} × 시장 "
                 f"{len(CORP_CLASSES)} — 예상 호출 약 {est:,}건. {q.status_line()}")

        def _one(m):
            rows = []
            for ty in DISCLOSURE_TYPES:
                for cc in CORP_CLASSES:
                    page = 1
                    while page <= 100:
                        js = dart_api("list.json", {
                            "bgn_de": m.start_time.strftime("%Y%m%d"),
                            "end_de": m.end_time.strftime("%Y%m%d"),
                            "pblntf_ty": ty, "corp_cls": cc,
                            "page_no": page, "page_count": 100, "last_reprt_at": "N"})
                        if not js or not isinstance(js.get("list"), list) or not js["list"]:
                            break
                        rows.extend(js["list"])
                        if page >= int(js.get("total_page", 1) or 1):
                            break
                        page += 1
            return rows

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 6), desc="DART 공시 스윕")
        new = [r for chunk in res if chunk for r in chunk]
        if new:
            d = pd.DataFrame(new)
            keep = [c for c in ("corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm")
                    if c in d.columns]
            d = d[keep].copy()
            d["code"] = d["stock_code"].map(to_code6) if "stock_code" in d.columns else None
            d["rcept_dt"] = as_ts_series(d["rcept_dt"])
            d["report_nm"] = as_str_series(d["report_nm"])
            d["is_periodic"] = d["report_nm"].str.contains(PERIODIC_PAT, na=False)
            frames.append(d)
            LOG.ok(f"공시 신규 {len(d):,}건 (정기보고서 {int(d['is_periodic'].sum()):,}건). "
                   f"{quota('DART', key=DART_API_KEY).status_line()}")

    if not frames:
        return pd.DataFrame(columns=cols)
    D = pd.concat(frames, ignore_index=True)
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"]).drop_duplicates("rcept_no", keep="last")
    if "is_periodic" not in D.columns:
        D["is_periodic"] = as_str_series(D.get("report_nm", "")).str.contains(PERIODIC_PAT, na=False)
    if "code" not in D.columns:
        D["code"] = None
    D["code"] = D["code"].map(to_code6)
    if len(frames) > 1 or (cached is None or not len(cached)):
        VAULT.put_table("dart_disclosures_slim",
                        D[["code", "corp_code", "rcept_no", "rcept_dt", "report_nm", "is_periodic"]],
                        scope="shared", domain="dart", source="opendart list.json (slim sweep)")
    # 접수일 = 공개일 (PIT)
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")
    LOG.ok(f"공시목록 총 {len(D):,}건 · 종목코드 보유 {int(D['code'].notna().sum()):,}건 · "
           f"정기보고서 {int(D['is_periodic'].sum()):,}건")
    PIPE.io("OUT", "DRIVE", "dart_disclosures_slim", D, source="opendart")
    return D


# ── 통제변수 패널 ───────────────────────────────────────────────────────────────────────────
#   법정 제출기한 (자본시장법 §159·§160) — DART 키가 없을 때의 달력 폴백.
#   12월 결산 법인 기준: Q1→5월, 반기→8월, Q3→11월, 사업보고서→3월.
#   출처: 자본시장과 금융투자업에 관한 법률 시행령 제168조 (분기 45일 / 사업 90일)
EARNINGS_MONTHS_FALLBACK = (3, 5, 8, 11)


def build_control_panel(months: "pd.DatetimeIndex", disclosures: "pd.DataFrame",
                        codes: Sequence[str]) -> Tuple["pd.DataFrame", dict]:
    """종목×월 통제변수 패널 (EarningsMonth, DisclosureCount).

    반환 (패널, 메타). 메타에는 각 통제변수가 '실측'인지 '달력 폴백'인지가 들어가고,
    그것이 통제 진단표에 그대로 출력된다 — 통제가 약해진 것을 조용히 넘기지 않는다."""
    meta = {"earnings_source": "달력 폴백(법정 제출기한)", "disclosure_source": "없음",
            "n_periodic": 0, "n_disclosure": 0}
    idx = pd.MultiIndex.from_product([sorted(set(codes)), list(months)], names=["code", "month"])
    P = pd.DataFrame(index=idx).reset_index()
    P["earnings_month"] = 0.0
    P["disclosure_n"] = np.nan

    if disclosures is not None and len(disclosures) and disclosures["code"].notna().any():
        d = disclosures.dropna(subset=["code"]).copy()
        d["month"] = as_ts_series(d["rcept_dt"]) + pd.offsets.MonthEnd(0)
        d["code"] = as_str_series(d["code"])
        cnt = (d.groupby(["code", "month"], observed=True)
                .agg(disclosure_n=("rcept_no", "nunique"),
                     earn=("is_periodic", "max")).reset_index())
        P = P.merge(cnt, on=["code", "month"], how="left")
        P["earnings_month"] = pd.to_numeric(P["earn"], errors="coerce").fillna(0.0)
        P["disclosure_n"] = pd.to_numeric(P["disclosure_n"], errors="coerce").fillna(0.0)
        P = P.drop(columns=["earn"])
        meta.update(earnings_source="DART 정기보고서 접수일(실측)",
                    disclosure_source="DART 공시 스윕(실측, 유형 A+B)",
                    n_periodic=int(cnt["earn"].sum()), n_disclosure=int(cnt["disclosure_n"].sum()))
    else:
        P["earnings_month"] = P["month"].dt.month.isin(EARNINGS_MONTHS_FALLBACK).astype(float)
        LOG.warn("실적발표월을 **법정 제출기한 달력**으로 대체합니다(3·5·8·11월). "
                 "12월 결산이 아닌 법인에서는 부정확하며, 그만큼 §6.3 통제가 약해집니다. "
                 "DART_API_KEY 를 넣으면 실측 접수일로 자동 대체됩니다.")
    P["disclosure_n"] = P["disclosure_n"].fillna(0.0)
    P["log_disclosure"] = np.log1p(P["disclosure_n"])
    return downcast(P), meta



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  애널리스트 리포트 메타데이터 수집 — 한경컨센서스 + 네이버금융리서치                  ║
# ║                                                                                          ║
# ║  ★ 이 전략은 리포트의 **내용을 전혀 읽지 않는다.** 필요한 것은 (analyst, ticker, date)      ║
# ║    메타데이터뿐이다. 목표주가·투자의견도 신호에 쓰지 않는다(§0 — 검열 내성).                 ║
# ║    목표주가는 오직 H5 선행성 검정의 '컨센서스 개정 대리변수'로만 쓴다.                      ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르다. 합쳐야 원장이 완성된다:                                          ║
# ║    · 한경컨센서스(skinType=business) : **작성자(애널리스트)를 리스트에서 바로 준다.**       ║
# ║      이 전략의 생명줄. 단, 종목코드가 없어 제목의 "종목명(005930)" 에서 뽑아야 한다.        ║
# ║    · 네이버금융리서치 : 종목코드를 확실히 준다. 커버리지가 넓다. 작성자는 리스트에 없다.    ║
# ║                                                                                          ║
# ║  ★ N(a,t) 은 '그 달 발간한 **총** 리포트 수'다(§6.1). 그래서 기업분석뿐 아니라              ║
# ║    산업분석까지 받아야 한다. 산업리포트를 많이 쓴 애널리스트는 개별 종목 share 가 낮아지는  ║
# ║    것이 맞다 — 주의 예산은 하나이기 때문이다. 이걸 빼면 분모가 과소집계된다.                ║
# ║                                                                                          ║
# ║  ⚠ 두 사이트 모두 robots.txt 가 Disallow: / 다. 사용자의 명시적 지시에 따라 수집하되        ║
# ║    보수적 속도로 제한하고 그 사실을 로그에 명시한다. 수집된 메타데이터는 로컬 분석          ║
# ║    용도로만 사용할 것.                                                                    ║
# ║                                                                                          ║
# ║  파싱 전략: 컬럼 인덱스를 믿지 않는다. <th> 헤더 텍스트로 매핑하고, 헤더가 없을 때만        ║
# ║  내용 기반 휴리스틱으로 폴백한다.                                                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = ["report_uid", "source", "src_report_id", "pub_date", "category",
               "title", "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
               "analyst_raw", "target_price", "opinion", "detail_url",
               "event_date", "knowledge_date"]

# 한경 report_type — 기업(CO)과 산업(IN)을 모두 받아야 N(a,t) 분모가 정확해진다.
HK_TYPES = [("business", "CO", "기업"), ("business", "IN", "산업")]
# 네이버 카테고리 — 동일 취지
NV_CATS = {"company": "company_list.naver", "industry": "industry_list.naver"}

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
        if n % k == 0 and s[: n // k] * k == s:
            return s[: n // k]
    return s


def parse_target_price(x: Any) -> Optional[float]:
    """'123,000'→123000.  '0'/'-'/'없음' → None.
    ★ '0'을 0원 목표주가로 넣으면 H5 의 컨센서스 개정 대리변수가 조용히 오염된다."""
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    return v if 0 < v <= 5e7 else None


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
    """★ 'YY.MM.DD' 를 반드시 명시 포맷으로 파싱한다.

    pandas 자동추론은 '26.01.19' 를 2019-01-26 으로, '19.12.31' 을 2031-12-19 로 읽는다.
    (연·일이 뒤바뀌고 미래 날짜가 만들어진다) 예외가 나지 않으므로 조용히 통과하며,
    리포트 원장의 시간축 전체가 어긋나 PIT 순서가 무의미해진다.
    이 전략은 **월 단위 주의 배분**이 신호이므로 날짜가 어긋나면 신호 자체가 무의미해진다."""
    if s is None:
        return None
    t = str(s).strip()
    m = _YYMMDD.match(t)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        year = 2000 + yy
        if year > _dt.date.today().year + 1:
            year -= 100
        return f"{year:04d}-{mm:02d}-{dd:02d}" if 1 <= mm <= 12 and 1 <= dd <= 31 else None
    return t or None


_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6}|[0-9]{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])\s*[)）]")


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return to_code6(m.group(1)) if m else None


def name_from_title(title: str) -> str:
    t = _clean_cell(title)
    m = _CODE_IN_TITLE.search(t)
    return _clean_cell(t[: m.start()]) if m else ""


def _table_headers(table) -> List[str]:
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            return [_clean_cell(th.get_text()) for th in ths]
    return []


def _row_map(headers: List[str], tds: List) -> Dict[str, Any]:
    return {headers[i]: tds[i] for i in range(len(tds))} if headers and len(headers) == len(tds) else {}


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
    if table is None or soup.select_one("td.no_data") or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    if category not in _HK_LAYOUT_LOGGED:
        _HK_LAYOUT_LOGGED.add(category)
        LOG.debug(f"한경 '{category}' 레이아웃: {len(headers)}컬럼 {headers}")
        if headers and not any("작성자" in h or "애널" in h for h in headers):
            LOG.warn(f"한경 '{category}' 응답에 작성자 컬럼이 없습니다. skinType 파라미터가 무시된 "
                     f"것 같습니다(통합 탭 레이아웃). ★ 이 전략은 작성자가 생명줄이므로 "
                     f"이 상태면 애널리스트 단위 신호를 만들 수 없습니다 — Phase 0 게이트에서 "
                     f"하우스 단위 폴백으로 자동 격하됩니다.")

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        ridx = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
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

        if not (headers and len(headers) == len(texts)):
            # 폴백: 내용 기반 추론 (레이아웃이 바뀌어도 죽지 않게)
            if tp is None:
                tp = next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            if op is None:
                op = next((t for t in texts if parse_opinion(t) in ("BUY", "HOLD", "SELL")), None)
            cand = [t for t in texts if t and t != title and not re.fullmatch(r"[\d,.\-]+", t)]
            cand = [c for c in cand if c != (op or "")]
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
            "detail_url": f"{HK_BASE}/analysis/downpdf?report_idx={ridx}",
        })
    return out


def hankyung_collect(start: str, end: str, page_size: int = 80,
                     max_pages: int = 500) -> "pd.DataFrame":
    """분기 단위로 쪼개서 수집. 한 번에 넓은 구간을 요청하면 서버 페이지 상한에 걸려
    데이터가 조용히 잘린다. 각 페이지는 HTTP 캐시에 남으므로 재실행 시 네트워크 0."""
    rows: List[dict] = []
    qs = pd.period_range(as_ts(start), as_ts(end), freq="Q")
    jobs = [(skin, rt, cat, q) for (skin, rt, cat) in HK_TYPES for q in qs]

    def _sweep(job):
        skin, rtype, cat, q = job
        sd = max(as_ts(q.start_time), as_ts(start))
        ed = min(as_ts(q.end_time), as_ts(end))
        got: List[dict] = []
        seen_ids: set = set()
        empty_streak = 0
        for page in range(1, max_pages + 1):
            html = http_get(HK_LIST, source="hankyung", tries=3, referer=HK_BASE + "/", timeout=30,
                            params={"skinType": skin, "sdate": sd.strftime("%Y-%m-%d"),
                                    "edate": ed.strftime("%Y-%m-%d"), "now_page": page,
                                    "pagenum": page_size, "report_type": rtype,
                                    "order_type": "", "search_text": "", "search_value": "",
                                    "business_code": ""})
            if not html:
                break
            batch = _hk_parse(html, f"{cat}")
            if not batch:
                break
            fresh = [b for b in batch if b["src_report_id"] not in seen_ids]
            seen_ids.update(b["src_report_id"] for b in fresh)
            got.extend(fresh)
            # ★ 조기 종료를 느슨하게 잡으면 데이터가 조용히 잘려나간다. 일시적 짧은 페이지
            #   하나로 그 분기 전체가 끊길 수 있으므로 '새 항목 0건'이 2회 연속일 때만 멈춘다.
            empty_streak = empty_streak + 1 if not fresh else 0
            if empty_streak >= 2:
                break
            if page == max_pages:
                LOG.warn(f"한경 {cat} {q} 구간이 최대 페이지({max_pages})에 도달 — 데이터가 잘렸을 "
                         f"수 있습니다. 지금까지 {len(got):,}건.")
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스",
                  breaker=breaker("hankyung"))
    for r in res:
        if r:
            rows.extend(r)
    d = pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPORT_COLS)
    n_an = int((as_str_series(d["analyst_raw"]).str.len() > 0).sum()) if len(d) else 0
    LOG.ok(f"한경컨센서스 {len(d):,}건 (작성자 보유 {n_an:,} = "
           f"{100*n_an/max(len(d),1):.1f}%)")
    PIPE.io("IN", "HTTP", "hankyung:analysis/list", d, source=HK_LIST)
    return d


# ── 네이버 금융 리서치 ──────────────────────────────────────────────────────────────────────
def _nv_parse_list(html: str, cat: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = (soup.select_one("#contentarea_left div.box_type_m table.type_1")
             or soup.select_one("table.type_1") or soup.select_one("table"))
    if table is None:
        return []
    headers = _table_headers(table)
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4 or tr.find("th") is not None:
            continue
        if any("blank" in " ".join(td.get("class") or []) for td in tds):
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = _row_map(headers, texts)

        nid = detail = title = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"nid=(\d+)", a["href"])
            if m:
                nid, detail = m.group(1), urljoin(NV_BASE, a["href"])
                title = _clean_cell(a.get_text(" "))
                break
        if nid is None:
            continue

        code, sname = None, ""
        a_item = tr.select_one("a.stock_item[href]")
        if a_item is not None:
            mm = re.search(r"code=([0-9A-Z]{6})", a_item["href"])
            code = to_code6(mm.group(1)) if mm else None
            sname = _clean_cell(a_item.get("title") or a_item.get_text(" "))

        bk = _pick(rm, "증권사")
        if bk is None:
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
        dt = _pick(rm, "작성일")
        if dt is None:
            dt = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)

        out.append({
            "source": "naver", "src_report_id": str(nid), "category": cat,
            "pub_date": parse_kr_date(dt), "title": _dedup_repeat(title or ""),
            "stock_code": code or code_from_title(title or ""),
            "stock_name": sname or name_from_title(title or ""),
            "broker_raw": _clean_cell(bk), "analyst_raw": "",
            "target_price": None, "opinion": None, "detail_url": detail,
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
                       hard_cap: int = 80000) -> "pd.DataFrame":
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
                "pub_date": it.get("createDate") or it.get("date") or it.get("writeDate"),
                "title": _dedup_repeat(str(it.get("title") or "")),
                "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                "target_price": parse_target_price(it.get("targetPrice") or it.get("goalPrice")),
                "opinion": parse_opinion(it.get("investmentOpinion") or it.get("opinion") or ""),
                "detail_url": None,
            })
        if len(items) < page_size:
            break
        index += len(items)
    d = pd.DataFrame(rows)
    return d[as_str_series(d["src_report_id"]).str.len() > 0] if len(d) else d


def naver_collect(start: str, end: str, max_pages: int = 2000) -> "pd.DataFrame":
    frames = []
    for cat, list_page in NV_CATS.items():
        try:
            dj = naver_collect_json(cat, start, end)
        except Exception:
            dj = pd.DataFrame()
        if len(dj) > 50:
            LOG.ok(f"네이버 JSON API '{cat}' {len(dj):,}건")
            frames.append(dj)
            continue
        base = urljoin(NV_BASE, list_page)
        prm = {"searchType": "writeDate",
               "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
               "writeToDate": as_ts(end).strftime("%Y-%m-%d")}
        probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                         params={**prm, "page": 1})
        if not probe:
            LOG.warn(f"네이버 '{cat}' 리스트 접근 실패 — 건너뜁니다.")
            continue
        last = min(_nv_last_page(probe), max_pages)
        LOG.info(f"네이버 '{cat}' HTML 경로 — 총 {last:,}페이지")

        def _pg(p: int):
            h = probe if p == 1 else http_get(base, source="naver", referer=NV_BASE,
                                              force_enc="euc-kr", tries=3,
                                              params={**prm, "page": p})
            return _nv_parse_list(h, cat) if h else []

        res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO),
                      desc=f"네이버 {cat}", breaker=breaker("naver"))
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


def collect_reports(start: str, end: str) -> "pd.DataFrame":
    """캐시 우선 수집. 이미 원장에 있는 구간은 다시 긁지 않는다."""
    frames: List["pd.DataFrame"] = []
    cached = VAULT.get_table("research_report_master", scope="shared")
    have_months: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["pub_date"] = as_ts_series(c["pub_date"])
        c = c.dropna(subset=["pub_date"])
        have_months = set(c["pub_date"].dt.strftime("%Y-%m"))
        frames.append(c)
        LOG.info(f"공용 캐시에서 리포트 원장 {len(c):,}건 / {len(have_months)}개월 재사용")

    want = set(pd.period_range(as_ts(start), as_ts(end), freq="M").astype(str))
    missing = sorted(want - have_months)
    if RUN_MODE == "CACHED" or not RESEARCH_COLLECT:
        if missing:
            LOG.warn(f"신규 수집 비활성 — 미보유 {len(missing)}개월은 결측으로 둡니다.")
        missing = []

    if missing:
        # 연속 구간으로 묶어 요청 수를 줄인다 (페이지 캐시는 어차피 남는다)
        lo, hi = as_ts(missing[0] + "-01"), as_ts(missing[-1] + "-01") + pd.offsets.MonthEnd(0)
        lo = max(lo, as_ts(start))
        hi = min(hi, as_ts(end))
        LOG.info(f"리포트 신규 수집 구간 {lo:%Y-%m} ~ {hi:%Y-%m} ({len(missing)}개월 미보유). "
                 f"※ 한경/네이버는 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 지시에 따라 "
                 f"수집하되 보수적 속도로 제한합니다.")
        if "hankyung" in RESEARCH_SOURCES:
            frames.append(hankyung_collect(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
        if "naver" in RESEARCH_SOURCES:
            frames.append(naver_collect(lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.error("리포트를 한 건도 확보하지 못했습니다. 이 전략은 리포트 메타데이터가 "
                  "전부이므로 여기서 막히면 신호를 만들 수 없습니다. "
                  "RUN_MODE='SMOKE' 로 계산경로만 검증하거나, 드라이브 캐시 경로를 확인하세요.")
        return pd.DataFrame(columns=REPORT_COLS)
    cols = sorted(set().union(*[set(f.columns) for f in frames]))
    return pd.concat([f.reindex(columns=cols) for f in frames], ignore_index=True)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  원장 — 증권사 정규화 / 리포트 원장 / 애널리스트 원장 / 인물 추적 / Phase 0 게이트    ║
# ║                                                                                          ║
# ║  이 모듈이 답해야 하는 질문:                                                               ║
# ║    Q1. 리포트와 애널리스트가 제대로 연결되었는가?  → report_analyst_link + 연결 감사표      ║
# ║    Q2. 다중소스 원장 연결은 확실한가?              → dedup_key 병합 + 소스기여 감사표       ║
# ║    Q3. 이 사람이 이직한 것인가, 그만둔 것인가?     → analyst_person_id (§5 식별자 규약)     ║
# ║                                                                                          ║
# ║  ★ 식별자 두 개를 반드시 구분한다 (§5 — 혼동 금지):                                        ║
# ║      analyst_broker_identity = f"{analyst}@{broker}"  ← 주의 배분의 단위. 소속이 바뀌면     ║
# ║                                                        다른 예산이므로 다른 ID 가 맞다.     ║
# ║      analyst_person_id                                ← 인물 단위. 이직 추적용.             ║
# ║                                                        §6.5 M-EXIT 판정에서만 쓴다.        ║
# ║    이 둘을 섞으면 "이직했는데 자발적으로 끊은 것"으로 오분류되어 인과분해가 무너진다.       ║
# ║                                                                                          ║
# ║  증권사 사명 변경(2016~2026)을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로          ║
# ║  다른 사람이 되어 **모든 커버리지 철회가 가짜로 발생한다.** 이 전략에서는 치명적이다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

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
    (r"(iM|아이엠)증권|하이투자증권|하이證", "iM증권"),        # 하이투자→iM증권(2024)
    (r"(LS증권|이베스트|eBEST|E\*?BEST)", "LS증권"),           # 이베스트→LS증권(2024)
    (r"(다올투자증권|KTB투자증권|다올)", "다올투자증권"),      # KTB→다올(2022)
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"),             # 동부→DB금융투자(2018)
    (r"BNK(투자증권|증권)", "BNK투자증권"),
    (r"흥국증권", "흥국증권"), (r"부국증권", "부국증권"),
    (r"한양증권", "한양증권"), (r"상상인증권|골든브릿지", "상상인증권"),
    (r"케이프(투자증권|증권)", "케이프투자증권"), (r"토스증권", "토스증권"),
    (r"카카오페이증권|바로투자증권", "카카오페이증권"),
    (r"리딩투자증권", "리딩투자증권"), (r"코리아에셋", "코리아에셋투자증권"),
    (r"유화증권", "유화증권"), (r"DS투자증권", "DS투자증권"),
    (r"NICE|나이스", "NICE디앤비"), (r"에프앤가이드|FnGuide", "에프앤가이드"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]

MAJOR_BROKERS = ["미래에셋증권", "NH투자증권", "한국투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "키움증권", "메리츠증권", "대신증권"]


def normalize_broker(raw: Any) -> Tuple[str, str]:
    """(broker_canon_id, 정식명). 합병 전후를 하나로 묶는 **정규화(canonical)** 식별자.
    용도: 목표주가 리비전 연속성 — 사명이 바뀌었다고 같은 애널의 TP 계열이 끊기면 안 된다."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    for rx, canon in _BROKER_RE:
        if rx.search(t2):
            return (sha1_str("broker", canon)[:12], canon)
    canon = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    return (sha1_str("broker", canon)[:12], canon)


# ── 법인 단위 식별자 (이직 탐지 전용) ───────────────────────────────────────────────────────
#   ★ 정규화 식별자만 쓰면 **이직이 통째로 사라진다.** 2016년 대우증권 → 미래에셋증권 이동이
#     둘 다 '미래에셋증권' 으로 정규화되어 같은 소속으로 보이기 때문이다. 동일 문제:
#     우리투자/NH, 현대/KB, 하나금투/하나, 동양/유안타, 하이/iM, 이베스트/LS, KTB/다올, 동부/DB.
#   → 발간 시점의 **실제 법인명**을 별도 식별자로 유지한다. 이동 판정은 오직 이것으로만 한다.
#   합병 이력 — 발효 전후 ±3개월의 철회 사건은 '제도적 소음'이라 라벨을 붙이지 않고 제외한다.
BROKER_MERGERS = [                    # (구법인 패턴, 신법인, 합병 발효일)
    (r"대우증권|KDB대우", "미래에셋증권", "2016-12-30"),
    (r"우리투자증권", "NH투자증권", "2014-12-31"),
    (r"현대증권", "KB증권", "2017-01-01"),
    (r"하나대투|하나금융투자", "하나증권", "2022-11-01"),
    (r"동양증권", "유안타증권", "2014-10-01"),
    (r"하이투자증권", "iM증권", "2024-09-01"),
    (r"이베스트투자증권", "LS증권", "2024-03-01"),
    (r"KTB투자증권", "다올투자증권", "2022-04-01"),
    (r"동부증권", "DB금융투자", "2018-01-01"),
    (r"신한금융투자", "신한투자증권", "2022-09-01"),
]

LEGAL_ALIASES = [                     # 철자 변형만 통합한다. 합병은 절대 통합하지 않는다.
    (r"^미래에셋대우증권$", "미래에셋대우"),
    (r"^KDB대우증권$", "대우증권"),
    (r"^우리투자$", "우리투자증권"),
    (r"^한국투자$|^한국투자증권$|^한국證$|^한투증권$", "한국투자증권"),
    (r"^하나대투증권$", "하나대투"),
    (r"^하나금융투자$|^하나금투$", "하나금융투자"),
    (r"^신한금융투자$|^신한금투$", "신한금융투자"),
    (r"^이베스트투자증권$|^eBEST투자증권$|^E\*?BEST투자증권$", "이베스트투자증권"),
    (r"^하이證$|^하이증권$", "하이투자증권"),
]
_LEGAL_RE = [(re.compile(p, re.I), n) for p, n in LEGAL_ALIASES]


def normalize_broker_legal(raw: Any) -> Tuple[str, str]:
    """(broker_legal_id, 법인명). 합병 전후를 **구분한다.** 이동 판정의 유일한 근거."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
    t2 = re.sub(r"(리서치센터|리서치|투자정보|Research)$", "", t2).strip() or t2
    for rx, nm in _LEGAL_RE:
        if rx.match(t2):
            t2 = nm
            break
    return (sha1_str("broker_legal", t2)[:12], t2)


_ANALYST_SPLIT = re.compile(r"[,/·∙•|;]|\s{2,}|\s외\s|\s및\s")
_ROLE_WORDS = r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원|박사|이사|부장|차장|대리|파트장)"


def split_analysts(raw: Any) -> List[str]:
    """'홍길동, 김철수' / '홍길동/김철수' / '홍길동 외 1인' → ['홍길동','김철수']"""
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(_ROLE_WORDS, " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치|센터|팀)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


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


def build_report_master(raw: "pd.DataFrame", sec: "pd.DataFrame") -> "pd.DataFrame":
    """다중 소스 병합 → 리포트 원장. 중복 제거가 아니라 '병합'이다(정보를 버리지 않는다).

    ★ 이 함수의 출력은 다음 실행에서 드라이브 캐시로부터 '입력'으로 되돌아온다.
      그래서 반드시 **멱등**이어야 한다. 아니면 실행할 때마다 source 문자열이 길어지고
      report_uid 가 바뀌어 애널리스트 연결표가 조용히 끊긴다."""
    if raw is None or raw.empty:
        LOG.warn("수집된 리포트가 없습니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    d = raw.copy()
    for c in REPORT_COLS:
        if c not in d.columns:
            d[c] = np.nan

    n_raw0 = len(d)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("2005-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일이 없거나 범위를 벗어난 리포트 {int(bad.sum()):,}건 제외 "
                 f"({100*bad.mean():.2f}%). 이 비율이 크면 소스의 날짜 형식이 바뀐 것입니다 — "
                 f"조용히 넘기지 말고 parse_kr_date 를 확인하세요.")
    d = d[~bad]
    if len(d) == 0:
        LOG.error("발간일이 유효한 리포트가 하나도 없습니다. 날짜 파싱이 깨졌습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    bid = as_str_series(d["broker_raw"]).map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]
    lid = as_str_series(d["broker_raw"]).map(normalize_broker_legal)
    d["broker_legal_id"] = [x[0] for x in lid]
    d["broker_legal_name"] = [x[1] for x in lid]

    # 종목코드: ① 소스 제공 ② 제목 정규식 ③ 종목명→코드 사전
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = as_str_series(d.loc[need, "title"]).map(code_from_title)
    need = d["stock_code"].isna() & (as_str_series(d["stock_name"]).str.len() > 0)
    if need.any() and sec is not None and len(sec):
        n2c: Dict[str, str] = {}
        for nm, cd in zip(sec["name"], sec["code"]):
            k = norm_corp_name(nm)
            if k and k not in n2c:
                n2c[k] = cd
        d.loc[need, "stock_code"] = as_str_series(d.loc[need, "stock_name"]).map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = as_str_series(d["title"]).map(_dedup_repeat)
    # report_uid 는 '한 번 붙으면 안 바뀌는' 식별자여야 한다. 이미 붙어 있으면 보존한다.
    _uid_new = [sha1_str(s, i) for s, i in zip(as_str_series(d["source"]),
                                               as_str_series(d["src_report_id"]))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b, c or "", norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             as_str_series(d["stock_code"]), d["title"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"])

    # ── 멱등 병합 (재실행 안전) ────────────────────────────────────────────────────────
    #   source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로 단순 set 병합은
    #   그걸 원자 하나로 취급해 실행마다 문자열이 무한히 길어진다. 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌므로
    #   순서 무관한 min 으로 고정한다. (min{u1,u2,min(u1,u2)} = min(u1,u2))
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
        "broker_legal_id": ("broker_legal_id", "min"),
        "broker_legal_name": ("broker_legal_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),    # 네이티브 max = NaN 무시
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"리포트 원장 병합: 수집 {n_raw0:,} → 날짜유효 {n_raw:,} → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0-n_raw:,} · 소스 간 중복 병합 {n_raw-len(m):,})")
    m["month"] = m["pub_date"] + pd.offsets.MonthEnd(0)
    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver")
    return m


# ── 애널리스트 원장 + 인물 추적 ─────────────────────────────────────────────────────────────
def build_analyst_ledger(rep: "pd.DataFrame") -> Tuple["pd.DataFrame", "pd.DataFrame"]:
    """(애널리스트 마스터, 리포트↔애널리스트 연결표). 연결 방법과 신뢰도를 반드시 기록한다."""
    empty_a = pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name",
                                    "analyst_person_id"])
    empty_l = pd.DataFrame(columns=["report_uid", "analyst_id", "link_method", "link_conf"])
    if rep is None or rep.empty:
        return empty_a, empty_l

    links = []
    for r in rep.itertuples(index=False):
        raw = getattr(r, "analyst_raw", "") or ""
        names, method, conf = [], "unresolved", 0.0
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98        # 한경 '작성자' 컬럼 — 최고 신뢰도
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
                "broker_name": r.broker_name,
                "broker_legal_id": getattr(r, "broker_legal_id", r.broker_id),
                "broker_legal_name": getattr(r, "broker_legal_name", r.broker_name),
                "role": "lead" if i == 0 else "co",
                "link_method": method, "link_conf": conf,
                "pub_date": r.pub_date, "month": r.month, "code": r.stock_code,
                "category": getattr(r, "category", ""), "target_price": r.target_price,
                "opinion": r.opinion,
            })
    if not links:
        LOG.error("애널리스트를 한 건도 식별하지 못했습니다. 한경컨센서스 수집이 실패했거나 "
                  "skinType=business 응답에 작성자 컬럼이 없습니다. "
                  "★ Phase 0 게이트가 이 상태를 감지해 하우스 단위 폴백으로 격하시킵니다.")
        return empty_a, empty_l

    L = pd.DataFrame(links)
    L["name_norm"] = as_str_series(L["name"]).str.replace(r"\s+", "", regex=True)
    L["code"] = as_str_series(L["code"]).replace("", np.nan)
    # 주의 배분의 단위: (법인, 이름). 소속이 바뀌면 예산이 다르므로 다른 ID 가 맞다.
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14]
                       for b, n in zip(L["broker_legal_id"], L["name_norm"])]

    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name_norm", "first"),
               broker_id=("broker_id", "first"), broker_name=("broker_name", "first"),
               broker_legal_id=("broker_legal_id", "first"),
               broker_legal_name=("broker_legal_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("code", lambda s: int(s.dropna().nunique()))))
    A, n_moves, borderline = _build_person_map(A, L)
    L = L.merge(A[["analyst_id", "analyst_person_id"]], on="analyst_id", how="left")

    LOG.ok(f"애널리스트 원장 {len(A):,}개 법인-계정 · 인물 "
           f"{A['analyst_person_id'].nunique():,}명 · 이직 판정 {n_moves:,}건 · "
           f"연결 {len(L):,}건 (동명 후보 {int(A['name_ambiguous'].sum()):,})")
    if borderline:
        LOG.table(borderline[:20], ["이름", "이전 법인", "이후 법인", "공백(개월)",
                                    "종목 Jaccard", "점수", "판정"],
                  ["l", "l", "l", "r", "r", "r", "l"],
                  title="이직 판정 경계 사례 (점수 0.4~0.9) — 동명이인일 가능성을 숨기지 않습니다")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


PERSON_MERGE_ACCEPT = 0.70      # 사전 고정. 사후 조정 금지.
PERSON_MERGE_REJECT = 0.40


def _build_person_map(A: "pd.DataFrame", L: "pd.DataFrame"
                      ) -> Tuple["pd.DataFrame", int, List[list]]:
    """analyst_person_id — 이직 추적. **점수화**하고 회색지대는 라벨을 붙이지 않는다.

    같은 이름이 두 법인에 나타나면 ① 이직 ② 동명이인 둘 중 하나다. 10년 누적 3,500명이면
    동명쌍이 60~245개, 그중 타사×시간인접한 '실질 위험쌍'이 18~71개 발생한다(생일문제 근사).
    0.5 에서 이진 병합하면 그 전부를 잘못 판정한다.

    규칙:
      · 재직 구간이 3개월 넘게 **겹치면** 즉시 별개인 (시간 배타성 — 비용 0, 거짓병합 대부분 제거)
      · 공백이 18개월을 넘으면 별개인
      · 점수 = 0.35·섹터겹침 + 0.35·종목겹침 + 0.20·(공백 짧을수록) + 0.10·공저자겹침
      · ≥0.70 동일인 / 0.40~0.70 **UNCLASSIFIED (사건에서 제외)** / <0.40 별개인

    ★ 회색지대를 억지로 한쪽에 붙이지 않는 것이 핵심이다. 붙이면 M-EXIT 과 V-DROP 이
      서로 오염되어 §6.5 인과분해 전체가 무의미해진다.
    """
    A = A.copy()
    A["analyst_person_id"] = A["analyst_id"]
    A["person_merge_conf"] = 1.0
    A["person_unclassified"] = False
    dup = A.groupby("name")["analyst_id"].transform("size")
    A["name_ambiguous"] = dup > 1

    sub = L.dropna(subset=["code"])
    cov = sub.groupby("analyst_id")["code"].apply(lambda s: set(map(str, s))).to_dict()
    sec_ = (L.groupby("analyst_id")["category"].apply(lambda s: set(map(str, s.dropna())))
            .to_dict())
    coa = (L.groupby("report_uid")["analyst_id"].apply(set))
    peers: Dict[str, set] = defaultdict(set)
    for _, ids in coa.items():
        if len(ids) > 1:
            for i in ids:
                peers[i] |= (ids - {i})

    def _jac(a: set, b: set) -> float:
        return len(a & b) / max(1, len(a | b))

    n_moves = 0
    borderline: List[list] = []
    for nm, grp in A[A["name_ambiguous"]].groupby("name"):
        g = grp.sort_values("first_seen")
        ids = g["analyst_id"].tolist()
        anchor = {ids[0]: ids[0]}
        for prev, cur in zip(ids[:-1], ids[1:]):
            rp = g[g["analyst_id"] == prev].iloc[0]
            rc = g[g["analyst_id"] == cur].iloc[0]
            if rp["broker_legal_id"] == rc["broker_legal_id"]:
                anchor[cur] = anchor.get(prev, prev)
                continue
            overlap_m = ((min(as_ts(rp["last_seen"]), as_ts(rc["last_seen"])) -
                          max(as_ts(rp["first_seen"]), as_ts(rc["first_seen"]))).days / 30.44)
            gap_m = (as_ts(rc["first_seen"]) - as_ts(rp["last_seen"])).days / 30.44
            if overlap_m > 2 or gap_m > 18:
                anchor[cur] = cur                     # 동시 재직 또는 긴 공백 → 별개인
                continue
            j_stk = _jac(cov.get(prev, set()), cov.get(cur, set()))
            j_sec = _jac(sec_.get(prev, set()), sec_.get(cur, set()))
            has_peer = 1.0 if (peers.get(prev, set()) & peers.get(cur, set())) else 0.0
            s = (0.35 * min(1.0, j_sec / 0.5) + 0.35 * min(1.0, j_stk / 0.2)
                 + 0.20 * (1 - min(1.0, max(gap_m, 0) / 18.0)) + 0.10 * has_peer)
            s = float(np.clip(s, 0, 1))
            if s >= PERSON_MERGE_ACCEPT:
                anchor[cur] = anchor.get(prev, prev)
                n_moves += 1
                verdict = "동일인(이직)"
            elif s >= PERSON_MERGE_REJECT:
                anchor[cur] = cur
                A.loc[A["analyst_id"].isin([prev, cur]), "person_unclassified"] = True
                verdict = "★판정불가 → 철회 사건에서 제외"
            else:
                anchor[cur] = cur
                verdict = "별개인(동명이인)"
            A.loc[A["analyst_id"] == cur, "person_merge_conf"] = s
            if 0.40 <= s <= 0.90:
                borderline.append([nm, str(rp["broker_legal_name"])[:14],
                                   str(rc["broker_legal_name"])[:14], f"{gap_m:.1f}",
                                   f"{j_stk:.2f}", f"{s:.2f}", verdict])
        m = A["analyst_id"].isin(ids)
        A.loc[m, "analyst_person_id"] = A.loc[m, "analyst_id"].map(anchor).fillna(
            A.loc[m, "analyst_id"])

    nper = A.groupby("analyst_person_id")["broker_legal_id"].nunique()
    many = nper[nper >= 4]
    if len(many):
        LOG.warn(f"10년간 소속 법인이 4개 이상인 인물 {len(many)}명 — 동명이인이 뭉쳤을 "
                 f"가능성이 있습니다(5개 초과는 사실상 확실). 해당 인물의 철회 사건은 "
                 f"M-EXIT 로 과잉 판정되어 신호가 보수적으로 약해지는 방향입니다.")
    return A, n_moves, borderline


# ── 무결성 감사 ─────────────────────────────────────────────────────────────────────────────
def audit_linkage(rep: "pd.DataFrame", A: "pd.DataFrame", L: "pd.DataFrame"):
    """★ '리포트와 식별된 애널리스트가 제대로 연결되었는지 한눈에'."""
    LOG.banner("원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출한다. 숫자가 낮으면 그대로 보고한다.")
    if rep is None or rep.empty:
        LOG.warn("리포트 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if L is not None and len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()

    rows = []
    for y, g in r.groupby("year"):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g.loc[g['has_analyst'], 'report_uid'].nunique()):,}"])
    LOG.table(rows, ["연도", "리포트", "애널연결", "연결률", "종목코드", "코드율", "유효(연결∧코드)"],
              ["c", "r", "r", "r", "r", "r", "r"])

    src = r.groupby("source").agg(n=("report_uid", "size"), analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%", f"{100*s['code']:.1f}%"]
               for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "종목코드율"], ["l", "r", "r", "r"],
              title="다중소스 원장 연결 — 어느 소스가 무엇을 채웠는가 "
                    "('hankyung+naver' 는 두 소스가 같은 리포트로 병합된 건)")

    if L is not None and len(L):
        mth = L.groupby("link_method").agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "리포트 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 (list_field=한경 작성자컬럼 0.98)")

    if A is not None and len(A):
        bro = (A.groupby("broker_name").agg(analysts=("analyst_id", "nunique"),
                                            reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        LOG.table([[b, f"{int(bro.loc[b, 'analysts']):,}", f"{int(bro.loc[b, 'reports']):,}"]
                   for b in bro.index[:25]],
                  ["증권사", "애널리스트 수", "리포트 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 전체 증권사 {len(bro)}개")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source").size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없습니다.")


# ── Phase 0 데이터 실현가능성 게이트 (§3) ───────────────────────────────────────────────────
def phase0_gate(rep: "pd.DataFrame", L: "pd.DataFrame") -> dict:
    """명세 §3: 표본 3개월 × 300건에서 analyst_id 확보율을 측정하고 진행 방식을 판정한다.

      ≥70%    → 정상 진행 (애널리스트 단위)
      40~70%  → 진행하되 §6.7 결측 민감도 분석 필수
      <40%    → **애널리스트 단위 포기.** 단위를 broker_id × sector 로 격하하고
                신호를 '하우스 단위 주의 재배분'으로 재정의. 모든 산출물 최상단에 폴백 명시.
    """
    res = {"rate": np.nan, "mode": "ANALYST", "samples": [], "note": ""}
    if rep is None or rep.empty:
        res.update(mode="HOUSE", note="리포트 원장이 비어 판정 불가 — 가장 보수적으로 하우스 단위")
        return res
    linked = set(L["report_uid"]) if L is not None and len(L) else set()
    r = rep.copy()
    r["ym"] = r["pub_date"].dt.strftime("%Y-%m")
    r["ok"] = r["report_uid"].isin(linked)

    rates, rows = [], []
    for ym in PHASE0_SAMPLE_MONTHS:
        g = r[r["ym"] == ym]
        if g.empty:
            rows.append([ym, "0", "—", "표본 없음(해당 월 수집분 없음)"])
            continue
        s = g.head(PHASE0_SAMPLE_N)
        rate = float(s["ok"].mean())
        rates.append(rate)
        rows.append([ym, f"{len(s):,}", f"{100*rate:.1f}%",
                     "정상" if rate >= PHASE0_PASS else
                     ("결측 민감도 필요" if rate >= PHASE0_DEGRADE else "하우스 단위 격하")])
    # 표본 월이 하나도 없으면 전체 구간으로 대체 측정한다(판정 자체를 포기하지 않는다)
    if not rates:
        rate = float(r["ok"].mean())
        rates = [rate]
        rows.append(["전체구간(대체)", f"{len(r):,}", f"{100*rate:.1f}%", "표본월 부재로 전체 측정"])

    overall = float(np.mean(rates))
    res["rate"] = overall
    res["samples"] = rows
    if overall >= PHASE0_PASS:
        res["mode"] = "ANALYST"
        res["note"] = "애널리스트 단위로 정상 진행합니다."
    elif overall >= PHASE0_DEGRADE:
        res["mode"] = "ANALYST_IPW"
        res["note"] = ("애널리스트 단위로 진행하되 §6.7 결측 민감도 분석(로지스틱 + IPW 재추정)을 "
                       "반드시 병기합니다.")
    else:
        res["mode"] = "HOUSE"
        res["note"] = ("★ 애널리스트 단위를 포기합니다. 단위를 broker_id × sector 로 격하하고 "
                       "신호를 '하우스 단위 주의 재배분'으로 재정의합니다. 이 결과를 "
                       "애널리스트 단위 결과로 보고하지 마십시오.")

    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§3)",
               "애널리스트 식별률에 따라 분석 단위가 결정됩니다")
    LOG.table(rows, ["표본월", "표본수", "애널 식별률", "판정"], ["c", "r", "r", "l"])
    LOG.table([["종합 식별률", f"{100*overall:.1f}%"],
               ["판정 기준", f"≥{100*PHASE0_PASS:.0f}% 정상 / "
                             f"{100*PHASE0_DEGRADE:.0f}~{100*PHASE0_PASS:.0f}% IPW 병기 / "
                             f"<{100*PHASE0_DEGRADE:.0f}% 하우스 격하"],
               ["결정된 분석 단위", {"ANALYST": "애널리스트 (analyst@broker)",
                                     "ANALYST_IPW": "애널리스트 + 결측 민감도 필수",
                                     "HOUSE": "★ 하우스 (broker × sector) — 폴백"}[res["mode"]]],
               ["비고", res["note"]]],
              ["항목", "값"], ["l", "l"])
    if res["mode"] == "HOUSE":
        LOG.error("Phase 0 폴백 발동 — 이후 모든 산출물 제목에 [하우스 단위 폴백] 이 붙습니다.")
    return res



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  주의 배분 패널 → 초과주의(EA) → 축소추정 → 기계적발간 통제 → VAS                    ║
# ║                                                                                          ║
# ║  §6.1  share(a,i,t) = reports(a,i,t) / N(a,t)          N(a,t)<3 → **셀 전체** 결측        ║
# ║  §6.2  base(a,i,t)  = Σ_{t-12..t-1} reports / Σ N       Σ N<12 → **셀 전체** 결측         ║
# ║         EA = share − base   → 경험적 베이즈 축소추정 (해석적 분산 + tau² 3단 계층)        ║
# ║  §6.3  VAS = EA_shrunk 을 기계적 발간 요인으로 회귀한 잔차                                 ║
# ║                                                                                          ║
# ║  ★★ §6.3 을 건너뛰거나 약화시키면 산출물 전체가 무효다(§1-4, §13). ★★                     ║
# ║     통제 없는 원신호는 그냥 실적시즌 달력이다. 통제를 성실히 했는데 신호가 사라진다면       ║
# ║     그것이 정답이며, 통제를 약화시켜 신호를 되살리려는 모든 시도는 이 프로젝트의 실패다.    ║
# ║                                                                                          ║
# ║  ★ 미래누수 봉인 — 확장창을 **생산 경로로 확정**한다:                                      ║
# ║      · 월 t 의 회귀는 [t0, t] 표본으로 재적합하고 월 t 행의 잔차만 VAS 로 쓴다.            ║
# ║        (섹터×월 FE 는 정의상 당월 횡단면에서만 추정되므로 누수가 아니다 —                  ║
# ║         횡단면 z 표준화가 누수가 아닌 것과 같은 이유다. 반면 AnalystFE 를 전기간으로       ║
# ║         추정하면 **커리어 전체 평균 = 미래 포함** 을 빼게 되어 명백한 누수다.)             ║
# ║      · EB 의 tau²·v 도 동일하게 [t0, t] 로만 추정한다. 여기가 가장 놓치기 쉽다.            ║
# ║      · 전기간 회귀는 참고 진단으로만 병기해 "전기간을 썼다면 얼마나 훔쳤을지"를 보여준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CTRL_MIN_TRAIN_M = 24        # 확장창 최소 학습 개월(버인). 이보다 짧으면 VAS 를 만들지 않는다.
CONTROL_VARS = ["earnings_month", "new_cover", "index_event", "log_disclosure"]


def build_attention_panel(L: "pd.DataFrame", months: "pd.DatetimeIndex",
                          sec: "pd.DataFrame", unit_mode: str = "ANALYST") -> "pd.DataFrame":
    """(주체, 종목, 월) 주의 패널. share / base / EA / 해석적 분산 v 까지.

    unit_mode="HOUSE" 면 Phase 0 폴백 — 주의 예산의 주체를 (증권사 × 섹터)로 격하한다(§3).
    """
    cols = ["unit_id", "house", "code", "month", "r_t", "N_t", "r_lb", "N_lb",
            "share", "base", "EA", "v", "new_cover", "sector"]
    if L is None or L.empty:
        return pd.DataFrame(columns=cols)

    ind = {}
    if sec is not None and len(sec):
        scol = "sector" if "sector" in sec.columns else "industry"
        ind = dict(zip(as_str_series(sec["code"]), as_str_series(sec[scol])))

    x = L.copy()
    x["month"] = as_ts_series(x["month"] if "month" in x.columns else x["pub_date"]) \
        + pd.offsets.MonthEnd(0)
    x = x.dropna(subset=["month", "analyst_id", "report_uid"])
    src_code = "code" if "code" in x.columns else "stock_code"
    x["code"] = as_str_series(x[src_code]).replace("", np.nan)
    x["sector"] = x["code"].map(ind).fillna("미분류")
    x["house"] = as_str_series(x["broker_legal_id"]) if "broker_legal_id" in x.columns \
        else as_str_series(x.get("broker_id", ""))
    # 주의 예산의 주체 — 인물이 아니라 '소속-계정'이다. 소속이 바뀌면 예산이 다르다(§5).
    x["unit_id"] = as_str_series(x["analyst_id"])
    if unit_mode == "HOUSE":
        x["unit_id"] = x["house"] + "|" + as_str_series(x["sector"])
        LOG.warn("[하우스 단위 폴백] 주의 배분의 주체를 (증권사 × 섹터)로 격하했습니다. "
                 "이 결과를 애널리스트 단위 결과로 보고하지 마십시오(§3).")

    # ── 분수배분: 한 리포트가 종목 k개를 다루면 1/k 씩 ────────────────────────────────
    #   정수로 세면 Σ share 가 1 을 넘어 영합 항등식과 이항분산 공식이 동시에 깨진다.
    nstock = x.groupby("report_uid", observed=True)["code"].transform("nunique").clip(lower=1)
    x["w_alloc"] = 1.0 / nstock

    # ── N(a,t): 그 달 발간한 **총** 리포트 수 (종목 없는 산업리포트 포함) ──────────────
    #   ★ 종목 리포트만 세면 분모가 과소집계되어 share 가 부풀려진다. 주의 예산은 하나다.
    NA = (x.groupby(["unit_id", "month"], observed=True)["report_uid"]
           .nunique().rename("N_t").reset_index())
    xi = x.dropna(subset=["code"])
    if xi.empty:
        LOG.error("종목이 식별된 리포트가 없어 주의 패널을 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    CNT = (xi.groupby(["unit_id", "code", "month"], observed=True)["w_alloc"]
             .sum().rename("r_t").reset_index())

    # ── 조밀 격자 + 누적합으로 롤링 12개월을 벡터화한다 ────────────────────────────────
    all_months = pd.DatetimeIndex(sorted(set(months) | set(CNT["month"].unique())
                                         | set(NA["month"].unique())))
    mpos = {m: i for i, m in enumerate(all_months)}
    T = len(all_months)
    uniq_unit = pd.Index(sorted(set(as_str_series(CNT["unit_id"])) |
                                set(as_str_series(NA["unit_id"]))))
    umap = {u: i for i, u in enumerate(uniq_unit)}
    U_K = len(uniq_unit)

    pair_key = as_str_series(CNT["unit_id"]) + "\x1f" + as_str_series(CNT["code"])
    p_codes, p_k = factorize_codes(pair_key)
    t_idx = CNT["month"].map(mpos).to_numpy(dtype=np.int64)
    Cmat = np.zeros((p_k, T), dtype=np.float64)
    np.add.at(Cmat, (p_codes, t_idx), CNT["r_t"].to_numpy(dtype=np.float64))

    Nmat = np.zeros((U_K, T), dtype=np.float64)
    np.add.at(Nmat, (NA["unit_id"].map(umap).to_numpy(dtype=np.int64),
                     NA["month"].map(mpos).to_numpy(dtype=np.int64)),
              NA["N_t"].to_numpy(dtype=np.float64))

    pair_unit = (pd.Series(pair_key.to_numpy()).str.split("\x1f").str[0]
                 .map(umap).to_numpy(dtype=np.int64))
    pair_lookup = (pd.DataFrame({"_p": p_codes, "unit_id": CNT["unit_id"].to_numpy(),
                                 "code": CNT["code"].to_numpy()})
                   .drop_duplicates("_p").set_index("_p").sort_index())

    def trailing12(M: np.ndarray) -> np.ndarray:
        """Σ_{s=t-12}^{t-1} — **당월 t 를 포함하지 않는다.** 포함하면 그 자체가 정보 누수다."""
        cs = np.cumsum(M, axis=1)
        out = np.zeros_like(M)
        out[:, 1:] = cs[:, :-1]
        lag = np.zeros_like(M)
        if T > LOOKBACK_M:
            lag[:, LOOKBACK_M + 1:] = cs[:, :T - LOOKBACK_M - 1]
        return out - lag

    C12 = trailing12(Cmat)
    N12 = trailing12(Nmat)

    # ── 합집합 채움 (union fill) ───────────────────────────────────────────────────────
    #   ★ reports>0 행만 쌓으면 **음의 EA 가 통째로 사라진다**. 커버를 끊은 종목은
    #     share=0, base>0 이라 EA<0 인데, 그 행은 CNT 에 존재하지 않기 때문이다.
    #     (실측: 합집합이면 ΣEA=1.67e-16, 필터하면 +0.75 로 전량 양수 편향)
    has_now = Cmat > 0
    has_base = C12 > 0
    sel_p, sel_t = np.where(has_now | has_base)
    if not len(sel_p):
        return pd.DataFrame(columns=cols)

    u_of = pair_unit[sel_p]
    r_t = Cmat[sel_p, sel_t]
    N_t = Nmat[u_of, sel_t]
    r_lb = C12[sel_p, sel_t]
    N_lb = N12[u_of, sel_t]

    P = pd.DataFrame({
        "unit_id": pair_lookup.loc[sel_p, "unit_id"].to_numpy(),
        "code": pair_lookup.loc[sel_p, "code"].to_numpy(),
        "month": all_months.to_numpy()[sel_t],
        "r_t": r_t, "N_t": N_t, "r_lb": r_lb, "N_lb": N_lb,
    })

    # ── 결측 규칙: 반드시 (주체, 월) **셀 전체** 삭제 ─────────────────────────────────
    #   행 단위로 지우면 Σ share < 1 이 되어 EA 에 체계적 편향이 생긴다(§7-F9).
    n_before = len(P)
    keep_cell = (P["N_t"] >= MIN_REPORTS_MON) & (P["N_lb"] >= MIN_LOOKBACK_N)
    P = P[keep_cell]
    LOG.info(f"결측 규칙 적용 — N(a,t)≥{MIN_REPORTS_MON} 및 룩백ΣN≥{MIN_LOOKBACK_N} 인 "
             f"(주체,월) 셀만 유지: {n_before:,} → {len(P):,}행 "
             f"(셀 단위 삭제 — 행 단위로 지우면 Σshare 가 깨집니다)")
    if P.empty:
        return pd.DataFrame(columns=cols)

    P["share"] = P["r_t"] / P["N_t"]
    P["base"] = P["r_lb"] / P["N_lb"]
    P["EA"] = P["share"] - P["base"]
    P["v"] = ea_analytic_var(P["r_t"], P["N_t"], P["r_lb"], P["N_lb"])
    # NewCoverage: 12개월 룩백에 한 건도 없었는데 이번 달에 발간 = 신규 개시
    P["new_cover"] = ((P["r_lb"] <= 0) & (P["r_t"] > 0)).astype("float64")
    P["sector"] = as_str_series(P["code"]).map(ind).fillna("미분류")
    hmap = x.drop_duplicates("unit_id").set_index("unit_id")["house"].to_dict()
    P["house"] = as_str_series(P["unit_id"]).map(hmap).fillna("_H")

    # ── 좌측절단 방어 ─────────────────────────────────────────────────────────────────
    #   데이터 시작 12개월 안에는 NewCoverage 가 전부 1 로 잡힌다(과거를 못 봤을 뿐인데).
    #   0 으로 채우면 '기존 커버'라는 적극적 거짓 정보가 되므로 **행을 삭제**한다.
    first_seen = x.groupby("unit_id", observed=True)["month"].min()
    fs = as_str_series(P["unit_id"]).map(first_seen)
    trunc = fs.notna() & (P["month"] < (fs + pd.DateOffset(months=LOOKBACK_M)))
    if trunc.any():
        LOG.info(f"좌측절단 제거 — 주체의 최초 관측 후 {LOOKBACK_M}개월 이내 {int(trunc.sum()):,}행 "
                 f"삭제(NewCoverage 가 구조적으로 1 이 되는 구간. 0 으로 채우면 거짓 정보).")
        P = P[~trunc]

    # ── 항등식 진단 (계약검정과 동일한 값) ────────────────────────────────────────────
    #   Σ_i EA(a,i,t) = (당월 종목리포트 비중) − (룩백 종목리포트 비중).
    #   모든 리포트에 종목이 붙어 있으면 정확히 0 이다. 산업리포트가 섞이면 그만큼 벗어난다.
    try:
        zs = P.groupby(["unit_id", "month"], observed=True)["EA"].sum()
        LOG.info(f"영합 항등식 진단 — Σ_i EA 의 |중앙값| {float(zs.abs().median()):.3e}, "
                 f"|최대| {float(zs.abs().max()):.3e}. "
                 f"0 에서 벗어나는 만큼이 '종목 없는 산업리포트'의 비중 변화입니다"
                 f"(오류가 아니라 정의상 그렇습니다).")
    except Exception:
        pass

    LOG.ok(f"주의 패널 {len(P):,}행 — 주체 {P['unit_id'].nunique():,} × "
           f"종목 {P['code'].nunique():,} × {P['month'].nunique()}개월 · {mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "attention_panel_raw", P)
    return P.reset_index(drop=True)


def _build_index_event(uni: "pd.DataFrame") -> "pd.DataFrame":
    """IndexEvent — KRX 실제 편입이력이 없으므로 **제도 상수 기반 합성 멤버십**으로 대체한다.

    KOSPI200 / KOSDAQ150 은 정기변경 심사기준일이 5월말·11월말이고 발효가 6월·12월이다.
    시총 상위 N(=200/150) 밴드의 진입·이탈을 편입/제외로 본다.

    ★ '시총 순위가 X% 이상 점프' 같은 임계값 정의는 쓰지 않는다 — 임계값이 곧 튜닝
      파라미터가 되어 사전등록을 위반한다. 밴드 크기 200/150 은 제도 상수라 자유도가 없다.
    ★ 이것은 대리변수다. 실제 KOSPI200 은 산업군별 누적시총과 순위버퍼 룰을 쓰므로
      완전히 일치하지 않는다. 통제가 불완전한 만큼 해석표에 명시한다.
    """
    band = {"KOSPI": 200, "KOSDAQ": 150}
    if uni is None or uni.empty:
        return pd.DataFrame(columns=["code", "month", "index_event"])
    d = uni[["code", "month", "market", "marcap"]].copy()
    d["market"] = as_str_series(d["market"]).str.upper()
    d["rk"] = (d.groupby(["month", "market"], observed=True)["marcap"]
                .rank(ascending=False, method="first"))
    d["inband"] = (d["rk"] <= d["market"].map(band).fillna(10 ** 9)).astype("float64")
    scr = d[d["month"].dt.month.isin((5, 11))].copy()
    scr["eff"] = scr["month"] + pd.offsets.MonthEnd(1)
    scr = scr.sort_values(["code", "month"])
    scr["chg"] = scr.groupby("code", observed=True)["inband"].diff().abs()
    ev = scr.loc[scr["chg"] > 0, ["code", "eff"]].rename(columns={"eff": "month"})
    ev["index_event"] = 1.0
    # 신규상장월 · 관측 재개월도 편입성 이벤트로 본다
    first = d.groupby("code", observed=True)["month"].min().rename("month").reset_index()
    first["index_event"] = 1.0
    out = (pd.concat([ev, first], ignore_index=True)
             .drop_duplicates(["code", "month"]))
    return out


def attach_controls(P: "pd.DataFrame", ctrl: "pd.DataFrame", uni: "pd.DataFrame") -> "pd.DataFrame":
    """종목×월 통제변수를 주의 패널에 붙인다. 결합키 결측 행을 **떨어뜨리지 않는다**
    (버리면 그게 곧 선택편향)."""
    if P is None or P.empty:
        return P
    out = P.copy()
    n0 = len(out)
    if ctrl is not None and len(ctrl):
        c = ctrl.copy()
        c["code"] = as_str_series(c["code"])
        c["month"] = as_ts_series(c["month"])
        use = [x for x in ("earnings_month", "log_disclosure") if x in c.columns]
        out = out.merge(c[["code", "month"] + use].drop_duplicates(["code", "month"]),
                        on=["code", "month"], how="left")
    ie = _build_index_event(uni)
    if len(ie):
        ie["code"] = as_str_series(ie["code"])
        ie["month"] = as_ts_series(ie["month"])
        out = out.merge(ie, on=["code", "month"], how="left")
    for c in CONTROL_VARS:
        if c not in out.columns:
            out[c] = np.nan
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 이벤트 더미의 결측은 '이벤트 없음'(0)이 맞다. 연속 통제(공시건수)의 결측은
    # 0 으로 채우면 '공시가 없었다'는 적극적 거짓이므로 열 자체를 제외한다(아래 compute_vas).
    for c in ("earnings_month", "new_cover", "index_event"):
        out[c] = out[c].fillna(0.0)
    if len(out) != n0:
        LOG.warn(f"통제변수 결합에서 행수가 {n0:,}→{len(out):,} 로 변했습니다 — "
                 f"통제 테이블에 (code, month) 중복이 있습니다. 중복을 제거하고 진행합니다.")
        out = out.drop_duplicates(["unit_id", "code", "month"], keep="first")
    out["sector_month"] = as_str_series(out["sector"]) + "|" + out["month"].dt.strftime("%Y%m")
    return out


def compute_vas(P: "pd.DataFrame", months: "pd.DatetimeIndex"
                ) -> Tuple["pd.DataFrame", "pd.DataFrame", "pd.DataFrame"]:
    """§6.2 축소 + §6.3 통제회귀를 **확장창 안에서 함께** 수행해 VAS 를 만든다.

    반환 (패널, 축소진단, 회귀진단)
    """
    if P is None or P.empty:
        return P, pd.DataFrame(), pd.DataFrame()
    d = P.sort_values("month", kind="stable").reset_index(drop=True)
    mon = d["month"].to_numpy()
    uniq_m = pd.DatetimeIndex(sorted(pd.unique(mon)))

    Xcols = [c for c in CONTROL_VARS if c in d.columns and d[c].notna().any()
             and float(d[c].std(skipna=True) or 0) > 0]
    dropped = [c for c in CONTROL_VARS if c not in Xcols]

    vas = np.full(len(d), np.nan)
    ea_sh = np.full(len(d), np.nan)
    wgt = np.full(len(d), np.nan)
    shr_diag_rows: List[dict] = []
    reg_rows: List[dict] = []
    n_sing = 0
    n_fail = 0

    LOG.info(f"확장창 재적합 시작 — {len(uniq_m)}개월 중 버인 {CTRL_MIN_TRAIN_M}개월 이후부터 "
             f"VAS 를 산출합니다. 매월 [t0, t] 표본으로 축소추정과 통제회귀를 다시 적합합니다.")
    for i, m in enumerate(tqdm(uniq_m, desc="VAS 확장창", ncols=88, leave=False)):
        if i < CTRL_MIN_TRAIN_M:
            continue
        sub_mask = mon <= np.datetime64(m)
        cur_mask = mon == np.datetime64(m)
        if int(cur_mask.sum()) == 0 or int(sub_mask.sum()) < 500:
            continue
        sub = d.loc[sub_mask]

        # ① EB 축소 — tau²·v 를 [t0, t] 표본으로만 추정한다 (여기가 가장 놓치기 쉬운 누수)
        try:
            sh, w, sdiag = eb_shrink_tau2(sub, unit="unit_id", house="house",
                                          sector="sector", ea="EA", var="v")
        except Exception as e:                                    # noqa
            LOG.debug(f"{m:%Y-%m} 축소추정 실패({type(e).__name__}) — 원값 사용")
            sh, w, sdiag = sub["EA"].astype("float32"), pd.Series(1.0, index=sub.index), pd.DataFrame()
        ea_sh[np.where(cur_mask)[0]] = sh.reindex(d.index[cur_mask]).to_numpy()
        wgt[np.where(cur_mask)[0]] = w.reindex(d.index[cur_mask]).to_numpy()

        # ② 통제회귀 — 같은 [t0, t] 표본. 섹터×월 FE 는 당월 횡단면에서만 추정되므로
        #    당월을 포함해도 누수가 아니다(횡단면 z 표준화와 같은 성질).
        y = sh.to_numpy(dtype=np.float64)
        Xm = sub[Xcols].to_numpy(dtype=np.float64) if Xcols else None
        sm_c, sm_k = factorize_codes(sub["sector_month"])
        an_c, an_k = factorize_codes(sub["unit_id"])
        try:
            resid, beta, keep_rows, keep_cols, info = absorb_2way(
                y, Xm, [sm_c, an_c], [sm_k, an_k], strict=False)
        except Exception as e:                                    # noqa
            n_fail += 1
            LOG.debug(f"{m:%Y-%m} FE 흡수 실패({type(e).__name__})")
            continue
        if not info.get("converged", True):
            n_fail += 1
        n_sing += int(info.get("n_singleton_dropped", 0))
        # 잔차를 원래 위치에 되꽂는다. 탈락행(싱글턴/결측)은 **0 이 아니라 NaN** 으로 남는다.
        full = np.full(len(sub), np.nan)
        full[np.where(keep_rows)[0]] = resid
        rows_cur = np.where(cur_mask)[0]
        pos_in_sub = np.searchsorted(np.where(sub_mask)[0], rows_cur)
        vas[rows_cur] = full[pos_in_sub]

        if i % 12 == 0 or i == CTRL_MIN_TRAIN_M:
            reg_rows.append({
                "month": pd.Timestamp(m), "n_train": int(sub_mask.sum()),
                "n_test": int(cur_mask.sum()),
                "singleton_drop": int(info.get("n_singleton_dropped", 0)),
                "iters": int(info.get("iters", 0)),
                "R2_absorbed": round(float(info.get("r2_absorbed", np.nan)), 4),
                **({f"b_{c}": (round(float(b), 6) if np.isfinite(b) else None)
                    for c, b in zip(Xcols, beta)} if beta.size else {}),
            })
            if len(sdiag):
                shr_diag_rows.append({"month": pd.Timestamp(m),
                                      "mean_w": float(sdiag["mean_w"].iloc[0]),
                                      "p10_w": float(sdiag["p10_w"].iloc[0]),
                                      "p90_w": float(sdiag["p90_w"].iloc[0]),
                                      "tau2_analyst": float(sdiag["tau2"].iloc[-1])})

    d["EA_shrunk"] = ea_sh.astype("float32")
    d["shrink_w"] = wgt.astype("float32")
    d["VAS"] = vas.astype("float32")

    # ── 전기간 회귀 (참고 진단 — 생산에 쓰지 않는다) ────────────────────────────────────
    try:
        sh_f, w_f, _ = eb_shrink_tau2(d, unit="unit_id", house="house", sector="sector",
                                      ea="EA", var="v")
        sm_c, sm_k = factorize_codes(d["sector_month"])
        an_c, an_k = factorize_codes(d["unit_id"])
        Xf = d[Xcols].to_numpy(dtype=np.float64) if Xcols else None
        r_f, b_f, kr_f, kc_f, info_f = absorb_2way(sh_f.to_numpy(dtype=np.float64), Xf,
                                                   [sm_c, an_c], [sm_k, an_k], strict=False)
        vf = np.full(len(d), np.nan)
        vf[np.where(kr_f)[0]] = r_f
        d["VAS_fullsample"] = vf.astype("float32")
        beta_full, info_full = b_f, info_f
    except Exception as e:                                        # noqa
        LOG.debug(f"전기간 참고 회귀 실패({type(e).__name__})")
        d["VAS_fullsample"] = np.nan
        beta_full, info_full = np.array([]), {}

    # ── 진단 ───────────────────────────────────────────────────────────────────────────
    n_vas = int(d["VAS"].notna().sum())
    var_ea = float(np.nanvar(d["EA_shrunk"].to_numpy(dtype="float64")))
    var_vas = float(np.nanvar(vas))
    r2 = 1.0 - (var_vas / var_ea) if var_ea > 0 else np.nan
    both = d[["VAS", "VAS_fullsample"]].dropna()
    corr_fw = float(both["VAS"].corr(both["VAS_fullsample"])) if len(both) > 100 else np.nan
    mean_w = float(np.nanmean(wgt))

    LOG.table([["관측(EA 유효)", f"{len(d):,}"],
               ["VAS 산출 성공", f"{n_vas:,} ({100*n_vas/max(len(d),1):.1f}%)"],
               ["통제 적용 변수", ", ".join(Xcols) if Xcols else "없음 ★"],
               ["통제 불가 변수", ", ".join(dropped) if dropped else "없음"],
               ["평균 축소 신뢰도 w", f"{mean_w:.3f}" if np.isfinite(mean_w) else "—"],
               ["통제가 설명한 분산", f"{100*r2:.1f}%" if np.isfinite(r2) else "—"],
               ["확장창 vs 전기간 상관", f"{corr_fw:.4f}" if np.isfinite(corr_fw) else "—"],
               ["싱글턴 셀 제거 누계", f"{n_sing:,}행 (잔차 0 오염 방지 — NaN 처리)"],
               ["FE 미수렴/실패 월", f"{n_fail}개월"],
               ["확장창 버인", f"{CTRL_MIN_TRAIN_M}개월"]],
              ["항목", "값"], ["l", "r"],
              title="§6.2 축소 + §6.3 통제회귀 진단 (★ 이 단계를 건너뛰면 산출물 전체가 무효)")

    if np.isfinite(mean_w) and mean_w < 0.5:
        LOG.info(f"평균 축소 신뢰도가 {mean_w:.2f} 입니다 — EA 원값의 약 "
                 f"{100*(1-mean_w):.0f}% 가 표본잡음이라는 뜻이며, 명세가 축소추정을 "
                 f"필수로 규정한 이유가 정량적으로 확인됩니다.")
    if beta_full.size:
        LOG.table([[c, (f"{b:+.6f}" if np.isfinite(b) else "제거됨(상수/공선)")]
                   for c, b in zip(Xcols, beta_full)],
                  ["통제변수", "계수(전기간 참고)"], ["l", "r"],
                  title="통제변수 계수 — 실적발표월·신규개시·공시건수는 EA 를 밀어올리는 "
                        "방향(양수)이어야 상식과 맞습니다")
    if dropped:
        LOG.warn(f"통제하지 못한 변수: {dropped}"
                 f"{' (DART_API_KEY 미입력 → 공시건수 없음)' if 'log_disclosure' in dropped else ''}. "
                 f"0 으로 채우지 않고 **열에서 제외**했습니다 — 0 채움은 '공시가 없었다'는 "
                 f"적극적 거짓이기 때문입니다. 통제가 그만큼 약하므로 결과를 할인해 읽으십시오.")
    if np.isfinite(corr_fw) and corr_fw < 0.95:
        LOG.warn(f"확장창 VAS 와 전기간 VAS 의 상관이 {corr_fw:.3f} 입니다. 전기간 회귀를 "
                 f"썼다면 미래 정보가 잔차에 상당히 섞였을 것이라는 뜻입니다. "
                 f"생산 경로는 확장창이므로 안전합니다.")
    if np.isfinite(r2) and r2 > 0.5:
        LOG.info(f"통제변수와 고정효과가 축소 EA 분산의 {100*r2:.0f}% 를 설명합니다. "
                 f"남은 {100*(1-r2):.0f}% 가 자발적 주의 서프라이즈(VAS)입니다 — "
                 f"기계적 발간이 원신호의 대부분이었다는 뜻이며 §6.3 이 필수인 이유입니다.")
    LOG.info("★ 해석 주의: SectorMonthFE 를 넣는 순간 AAR_pos 는 **구조적으로 섹터중립** "
             "신호가 됩니다. '반도체로 주의가 몰렸다' 같은 섹터 로테이션은 신호에서 완전히 "
             "제거됩니다. 설계 의도이지만 명시하지 않으면 결과 해석이 틀어집니다.")
    PIPE.io("OUT", "MEM", "attention_panel_vas", d)
    return downcast(d), pd.DataFrame(shr_diag_rows), pd.DataFrame(reg_rows)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  커버리지 철회의 인과 분해 — 이 전략의 차별점 (§6.5)                                 ║
# ║                                                                                          ║
# ║  한국 시장에서 음(−) 신호는 극히 희소하다. 매도의견이 사실상 0이고 공매도가 제약되므로     ║
# ║  "부정적 정보"가 관측 가능한 거의 유일한 경로가 **커버리지 철회**다.                       ║
# ║  그런데 철회에는 두 종류가 섞여 있다:                                                      ║
# ║    · 담당자가 퇴사·이직해서 끊긴 것    → 종목에 대한 정보가 아니다 (기계적)                 ║
# ║    · 재직 중인데 이 종목만 끊은 것     → 종목에 대한 판단이다 (자발적)                      ║
# ║  이 둘을 가르지 못하면 신호는 그냥 "커버리지 감소 = 소외주"의 재발견이다.                   ║
# ║                                                                                          ║
# ║  분류 (하우스의 커버 애널 수 변화 Δn 이라는 **단일 단조 규칙**에서 파생):                   ║
# ║    H-EXIT   잔여 0        → 가중 1.5   하우스 전체가 커버 중단                             ║
# ║    V-DROP   잔여>0, 감소  → 가중 1.0   하우스는 계속 커버하나 인원 감소 = 자발적 철회       ║
# ║    HANDOFF  불변(승계)    → 가중 0.0   주의 총량이 줄지 않았으므로 **철회가 아니다**        ║
# ║    M-EXIT   애널이 원소속에서 사라짐 → 분자 제외. **플라시보군** (여기서 효과가 나오면 실패) ║
# ║    CENSORED-* 판정 불가   → 분자·분모 모두 제외 (라벨을 억지로 붙이지 않는다)               ║
# ║                                                                                          ║
# ║  ★ PIT 봉인: knowledge_ym = t (침묵을 **관측한** 달). 마지막 리포트는 t-3 이므로 신호가     ║
# ║    3개월 지연되지만 t월 말 시점에 100% 관측 가능하다. t-3 을 이벤트일로 쓰면 3개월 선견이다.║
# ║                                                                                          ║
# ║  ★ 소스 단절 방어를 **분류보다 먼저** 한다. 증권사가 배포동의를 철회하거나 스크래퍼가       ║
# ║    막히면 그 달 소속 애널 전원이 동시에 '철회'로 위조된다. 오차가 iid 가 아니라 달력시간에  ║
# ║    군집하므로 t값이 아무 쪽으로나 유의해진다 — 통계적으로 가장 위험한 오염이다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

W_SIG = 3        # 신호용 침묵 판정창(개월). ContCov 가 '분기당 1건'을 요구하므로 그 최소 위반단위.
D_VER = 12       # 검증용 확정 지연(개월). **모든 클래스에 동일하게 강제**한다(§7-F11).
LAM_MIN = 0.5    # M-EXIT 자격 문턱: 사건 전 12M 월평균 발간량. 포아송 근거는 아래 표 참조.
SICK_RATIO = 0.2         # 직전 12M 중앙값 대비 이 비율 미만이면 소스 단절로 판정
MERGER_HALO_M = 3        # 합병 발효 전후 창


def _dense(idx_pairs: np.ndarray, idx_t: np.ndarray, vals: np.ndarray,
           n_pair: int, n_t: int) -> np.ndarray:
    M = np.zeros((n_pair, n_t), dtype=np.float32)
    np.add.at(M, (idx_pairs, idx_t), vals.astype(np.float32))
    return M


def _shift_right(M: np.ndarray, k: int) -> np.ndarray:
    """열 방향 k칸 지연 (t-k 값). 앞쪽은 0."""
    if k <= 0:
        return M
    out = np.zeros_like(M)
    if k < M.shape[1]:
        out[:, k:] = M[:, :-k]
    return out


def _roll_max(M: np.ndarray, w: int) -> np.ndarray:
    """최근 w개월 중 1건이라도 있으면 1."""
    acc = np.zeros_like(M)
    for k in range(w):
        acc = np.maximum(acc, _shift_right(M, k))
    return acc


def _roll_sum(M: np.ndarray, w: int, lag: int = 0) -> np.ndarray:
    acc = np.zeros_like(M)
    for k in range(lag, lag + w):
        acc = acc + _shift_right(M, k)
    return acc


def build_source_health(L: "pd.DataFrame", months: "pd.DatetimeIndex") -> set:
    """(broker_legal_id, month) 중 **소스 단절**로 판단되는 조합. 분류보다 먼저 계산한다."""
    if L is None or L.empty:
        return set()
    x = L.copy()
    x["month"] = as_ts_series(x["month"])
    g = (x.groupby(["broker_legal_id", "month"], observed=True)["report_uid"]
          .nunique().rename("n").reset_index())
    if g.empty:
        return set()
    full = pd.MultiIndex.from_product(
        [sorted(set(as_str_series(g["broker_legal_id"]))), list(months)],
        names=["broker_legal_id", "month"])
    g = (g.set_index(["broker_legal_id", "month"]).reindex(full, fill_value=0)
          .reset_index().sort_values(["broker_legal_id", "month"]))
    med = (g.groupby("broker_legal_id", observed=True)["n"]
            .transform(lambda s: s.rolling(12, min_periods=6).median().shift(1)))
    sick = g[(med.notna()) & (med > 0) & (g["n"] < SICK_RATIO * med)]
    out = set(zip(as_str_series(sick["broker_legal_id"]), sick["month"]))
    if out:
        LOG.warn(f"소스 단절 의심 (증권사×월) {len(out):,}건 — 직전 12개월 중앙값의 "
                 f"{SICK_RATIO:.0%} 미만으로 발간량이 급감한 구간입니다. 이 구간의 철회 사건은 "
                 f"라벨을 붙이지 않고 **전량 제외(CENSORED-SOURCE)** 합니다. "
                 f"배포동의 철회나 수집 차단이 철회를 대량 위조하는 것을 막기 위함입니다.")
        top = pd.Series([b for b, _ in out]).value_counts().head(5)
        nm = (L.drop_duplicates("broker_legal_id")
                .set_index("broker_legal_id")["broker_legal_name"].to_dict())
        LOG.info("  주요 단절: " + ", ".join(f"{nm.get(b, b)}({int(c)}개월)" for b, c in top.items()))
    return out


def classify_coverage_drops(L: "pd.DataFrame", A: "pd.DataFrame", months: "pd.DatetimeIndex",
                            sec: "pd.DataFrame", uni: "pd.DataFrame") -> Dict[str, "pd.DataFrame"]:
    """신호용(3M) · 검증용(12M) · 하우스 그레인 3종 이벤트 테이블을 만든다."""
    empty = pd.DataFrame(columns=["person_id", "analyst_id", "broker_legal_id", "code",
                                  "last_report_month", "month", "klass", "w",
                                  "sole_coverer", "event_date", "knowledge_date"])
    if L is None or L.empty:
        return {"signal": empty, "verify": empty.copy(), "house": empty.copy()}

    x = L.copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"]).replace("", np.nan)
    x = x.dropna(subset=["month", "analyst_id"])
    pid_map = (A.set_index("analyst_id")["analyst_person_id"].to_dict()
               if A is not None and "analyst_person_id" in A.columns else {})
    unclass = set(A.loc[A.get("person_unclassified", False) == True, "analyst_id"]) \
        if A is not None and "person_unclassified" in A.columns else set()
    x["person_id"] = as_str_series(x["analyst_id"]).map(pid_map).fillna(x["analyst_id"])

    all_m = pd.DatetimeIndex(sorted(set(months) | set(x["month"].unique())))
    mpos = {m: i for i, m in enumerate(all_m)}
    T = len(all_m)

    xs = x.dropna(subset=["code"])
    if xs.empty:
        return {"signal": empty, "verify": empty.copy(), "house": empty.copy()}

    # ── (person, code) 그레인 ─────────────────────────────────────────────────────────
    ps_key = as_str_series(xs["person_id"]) + "\x1f" + as_str_series(xs["code"])
    ps_codes, ps_k = factorize_codes(ps_key)
    ti = xs["month"].map(mpos).to_numpy(dtype=np.int64)
    R = _dense(ps_codes, ti, np.ones(len(xs)), ps_k, T)          # r[p,s,t]
    lut = (pd.DataFrame({"_p": ps_codes, "person_id": xs["person_id"].to_numpy(),
                         "code": xs["code"].to_numpy(),
                         "analyst_id": xs["analyst_id"].to_numpy(),
                         "broker_legal_id": xs["broker_legal_id"].to_numpy()})
           .drop_duplicates("_p").set_index("_p").sort_index())

    # ContCov — 명세 문언 "직전 4개 분기 연속" 을 그대로 구현한다
    H = (R > 0).astype(np.float32)
    q = _roll_max(H, 3)
    ContCov = ((q > 0) & (_shift_right(q, 3) > 0) &
               (_shift_right(q, 6) > 0) & (_shift_right(q, 9) > 0))

    silent3 = (_roll_sum(H, 3, lag=0) == 0)                       # t-2..t 무발간
    silent3_1 = (_roll_sum(H, 3, lag=1) == 0)                     # t-3..t-1 무발간
    event = _shift_right(ContCov.astype(np.float32), 3) > 0
    event &= silent3 & (~silent3_1)

    # ── 애널리스트 가용성 (종목 무관, person 그레인) ──────────────────────────────────
    #   ★ 여기서 필요한 것은 '코드 배열'이 아니라 '키 → 행 인덱스' 사전이다.
    #     pd.factorize 의 uniques 로 사전을 만들어야 사건 순회에서 O(1) 로 찾을 수 있다.
    p_ser = as_str_series(x["person_id"])
    p_codes, p_uniq = pd.factorize(p_ser)
    p_index = {k: i for i, k in enumerate(p_uniq)}
    Pall = _dense(np.asarray(p_codes, dtype=np.int64),
                  x["month"].map(mpos).to_numpy(dtype=np.int64),
                  np.ones(len(x)), len(p_uniq), T)

    pb_ser = p_ser + "\x1f" + as_str_series(x["broker_legal_id"])
    pb_codes, pb_uniq = pd.factorize(pb_ser)
    pb_index = {k: i for i, k in enumerate(pb_uniq)}
    Pb = _dense(np.asarray(pb_codes, dtype=np.int64),
                x["month"].map(mpos).to_numpy(dtype=np.int64),
                np.ones(len(x)), len(pb_uniq), T)

    Pall_3 = _roll_sum(Pall, 3, 0)
    Pb_3 = _roll_sum(Pb, 3, 0)
    Lam12 = _roll_sum(Pall, 12, 1) / 12.0

    # ── 하우스 축: (broker_legal, code) 별 커버 애널 수 ───────────────────────────────
    bs = xs.drop_duplicates(["broker_legal_id", "code", "month", "person_id"])
    bs_key = as_str_series(bs["broker_legal_id"]) + "\x1f" + as_str_series(bs["code"])
    bs_codes, bs_k = factorize_codes(bs_key)
    HB = _dense(bs_codes, bs["month"].map(mpos).to_numpy(dtype=np.int64),
                np.ones(len(bs)), bs_k, T)
    bs_lut = (pd.DataFrame({"_b": bs_codes, "broker_legal_id": bs["broker_legal_id"].to_numpy(),
                            "code": bs["code"].to_numpy()})
              .drop_duplicates("_b").set_index("_b").sort_index())
    bs_index = {(b, c): i for i, (b, c) in enumerate(zip(bs_lut["broker_legal_id"],
                                                        bs_lut["code"]))}
    HB_after = _roll_sum(HB, 3, 0)          # t-2..t
    HB_before = _roll_sum(HB, 12, 3)        # t-14..t-3

    # ── 시장 전체 커버 (H-EXIT-MARKET 판정용) ────────────────────────────────────────
    ms = xs.drop_duplicates(["code", "month", "person_id"])
    m_codes, m_k = factorize_codes(ms["code"])
    MK = _dense(m_codes, ms["month"].map(mpos).to_numpy(dtype=np.int64), np.ones(len(ms)), m_k, T)
    MK_after = _roll_sum(MK, 3, 0)
    mk_lut = (pd.DataFrame({"_m": m_codes, "code": ms["code"].to_numpy()})
              .drop_duplicates("_m").set_index("_m").sort_index())
    mk_index = {c: i for i, c in enumerate(mk_lut["code"])}

    # ── 검열 정보 ─────────────────────────────────────────────────────────────────────
    sick = build_source_health(L, all_m)
    dl = dict(zip(as_str_series(sec["code"]), as_ts_series(sec["delisting_date"]))) \
        if sec is not None and len(sec) else {}
    listed = set()
    if uni is not None and len(uni):
        listed = set(zip(as_str_series(uni["code"]), uni["month"]))
    merger_months: set = set()
    for _pat, _new, eff in BROKER_MERGERS:
        e = as_ts(eff)
        if e is None:
            continue
        for k in range(-MERGER_HALO_M, MERGER_HALO_M + 1):
            merger_months.add((e + pd.DateOffset(months=k) + pd.offsets.MonthEnd(0)).normalize())

    # ── 사건 순회 ─────────────────────────────────────────────────────────────────────
    ev_p, ev_t = np.where(event)
    LOG.info(f"철회 사건 후보 {len(ev_p):,}건 (ContCov 4분기 연속 후 {W_SIG}개월 침묵 최초 발생)")
    rows: List[dict] = []
    tally: Counter = Counter()
    for k in range(len(ev_p)):
        pi, tt = int(ev_p[k]), int(ev_t[k])
        m = all_m[tt]
        meta = lut.loc[pi]
        code = str(meta["code"])
        bl = str(meta["broker_legal_id"])
        aid = str(meta["analyst_id"])
        pid = str(meta["person_id"])

        # 0) 검열 가드 — 라벨이 아니라 '제외'를 낸다. 최우선.
        if (bl, m) in sick:
            tally["CENSORED-SOURCE"] += 1
            continue
        if any(((m - pd.DateOffset(months=j)) + pd.offsets.MonthEnd(0)).normalize()
               in merger_months for j in range(0, W_SIG)):
            tally["CENSORED-MA"] += 1
            continue
        d_ = dl.get(code)
        if pd.notna(d_) and d_ is not None and d_ <= m + pd.offsets.MonthEnd(1):
            tally["CENSORED-DELIST"] += 1
            continue
        if listed and (code, m) not in listed:
            tally["CENSORED-DELIST"] += 1
            continue
        if aid in unclass:
            tally["CENSORED-PERSON"] += 1
            continue

        mi = mk_index.get(code)
        if mi is not None and MK_after[mi, tt] == 0:
            tally["H-EXIT-MARKET"] += 1        # 시장 전체가 커버를 끊음 — 별도로 본다
            continue

        # 1) 애널리스트 가용성 — 종목이 아니라 '아무 종목이라도' 기준이라 문턱이 낮다
        pbi = pb_index.get(pid + "\x1f" + bl)
        pi_all = p_index.get(pid)
        n_self_b3 = float(Pb_3[pbi, tt]) if pbi is not None else 0.0
        n_all3 = float(Pall_3[pi_all, tt]) if pi_all is not None else 0.0
        n_other = max(0.0, n_all3 - n_self_b3)          # 다른 법인에서의 발간 = 이직 증거
        lam = float(Lam12[pi_all, tt]) if pi_all is not None else 0.0

        if n_other >= 1:
            avail = "MOVED"
        elif n_self_b3 >= 1:
            avail = "AVAILABLE"
        elif lam >= LAM_MIN:
            avail = "SILENT"
        else:
            tally["UNCLASSIFIED-LOWPROD"] += 1
            continue

        # 2) 하우스 축
        bi = bs_index.get((bl, code))
        n_after = float(HB_after[bi, tt]) if bi is not None else 0.0
        n_before = float(HB_before[bi, tt]) if bi is not None else 0.0

        # 3) 라벨 + 가중
        if avail in ("MOVED", "SILENT"):
            klass, w = "M-EXIT", 0.0
        elif n_after <= 0:
            klass, w = "H-EXIT", NEG_W_HEXIT
        elif n_after < n_before:
            klass, w = "V-DROP", NEG_W_VDROP
        else:
            klass, w = "HANDOFF", 0.0
        tally[klass] += 1
        rows.append({
            "person_id": pid, "analyst_id": aid, "broker_legal_id": bl, "code": code,
            "last_report_month": all_m[max(0, tt - W_SIG)], "month": m,
            "klass": klass, "w": w, "avail": avail,
            "n_house_before": n_before, "n_house_after": n_after,
            "sole_coverer": bool(n_before <= 1), "lam_pre": lam,
        })

    S = pd.DataFrame(rows)
    if len(S):
        S["event_date"] = S["month"]
        S["knowledge_date"] = S["month"]      # 침묵을 관측한 달 = 알 수 있는 시점
        S = pit_frame(S, "event_date", "knowledge_date", source="drops")

    order = ["V-DROP", "H-EXIT", "HANDOFF", "M-EXIT", "H-EXIT-MARKET",
             "CENSORED-SOURCE", "CENSORED-MA", "CENSORED-DELIST", "CENSORED-PERSON",
             "UNCLASSIFIED-LOWPROD"]
    tot = sum(tally.values())
    LOG.table([[k, f"{tally.get(k, 0):,}", f"{100*tally.get(k, 0)/max(tot, 1):.1f}%",
                {"V-DROP": f"자발적 철회 · 가중 {NEG_W_VDROP}",
                 "H-EXIT": f"하우스 전체 철회 · 가중 {NEG_W_HEXIT}",
                 "HANDOFF": "승계(인원 불변) · 가중 0 — 철회가 아님",
                 "M-EXIT": "★플라시보군 — 여기서 효과가 나오면 인과분해 실패",
                 "H-EXIT-MARKET": "시장 전체 커버 소멸 (별도 관측)",
                 "CENSORED-SOURCE": "소스 단절 — 라벨 없이 제외",
                 "CENSORED-MA": "증권사 합병 창 — 제외",
                 "CENSORED-DELIST": "폐지·거래정지 — 제외",
                 "CENSORED-PERSON": "동일인 판정 불가 — 제외",
                 "UNCLASSIFIED-LOWPROD": f"사건 전 12M 월평균 발간 < {LAM_MIN} — 제외"}.get(k, "")]
               for k in order],
              ["분류", "건수", "비중", "의미"], ["l", "r", "r", "l"],
              title=f"§6.5 커버리지 철회 인과분해 (신호용 · 침묵창 {W_SIG}개월 · PIT 봉인)")
    LOG.info(f"포아송 근거 — 월평균 발간 λ=0.15 이면 3개월 무발간이 우연히 63.8% 확률로 "
             f"발생한다. λ≥{LAM_MIN} 이면 22.3% 로 떨어진다. 그래서 저생산 애널의 침묵은 "
             f"철회로 보지 않고 제외한다(오분류가 신호를 희석하기 때문).")
    PIPE.io("OUT", "MEM", "drop_events_signal", S)
    return {"signal": S if len(S) else empty,
            "verify": _classify_verify(S, all_m),
            "house": _house_grain(HB, bs_lut, all_m)}


def _classify_verify(S: "pd.DataFrame", all_m) -> "pd.DataFrame":
    """검증용 라벨 (D_VER=12개월). **모든 클래스에 동일한 지연을 강제**한다.

    ★ 클래스별로 판정 지연이 다르면 M-EXIT 과 V-DROP 이 서로 다른 이벤트 호라이즌을
      비교하게 되어 대비가 '지연 효과'와 교란된다. 검정력을 잃더라도 동일 지연이 옳다.
    ★ 우측절단: t* + 12 가 표본 끝을 넘는 사건은 **전량 제외**한다. 넣으면 표본 끝이
      전부 가짜 드롭으로 보인다.
    """
    if S is None or S.empty:
        return S if S is not None else pd.DataFrame()
    end = all_m[-1]
    V = S[S["month"] + pd.DateOffset(months=D_VER) <= end].copy()
    if V.empty:
        LOG.warn(f"검증용 라벨 대상이 없습니다 — 표본 끝에서 {D_VER}개월 여유가 필요합니다.")
        return V
    V["knowledge_date"] = (V["month"] + pd.DateOffset(months=D_VER) +
                           pd.offsets.MonthEnd(0)).values
    V["event_date"] = V["month"]
    V["klass_ver"] = V["klass"]
    LOG.info(f"검증용 라벨 {len(V):,}건 (신호용 {len(S):,}건 중 우측절단 {len(S)-len(V):,}건 제외). "
             f"확정 지연 {D_VER}개월을 전 클래스에 동일 적용 — 표본 끝 "
             f"{D_VER}개월은 검증 분석에서 구조적으로 빠집니다.")
    try:
        ct = pd.crosstab(V["klass"], V["klass_ver"], normalize="index")
        diag = float(np.mean([ct.loc[i, i] for i in ct.index if i in ct.columns]))
        if diag < 0.7:
            LOG.warn(f"신호용→검증용 라벨 전이 대각비율이 {diag:.2f} 로 낮습니다 — "
                     f"신호 라벨에 잡음이 많다는 뜻입니다.")
    except Exception:
        pass
    return V


def _house_grain(HB, bs_lut, all_m) -> "pd.DataFrame":
    """(증권사, 종목) 그레인의 하우스 철회 패널.

    ★ (애널, 종목) 패널과 **배타가 아니라 중첩**이다. 한국 증권사는 섹터 1인 전담이
      일반적이라 단독 커버 애널의 철회는 정의상 하우스 철회이기도 하다. 교차항
      (V-DROP ∧ H-EXIT) 이 최강 신호이므로 강건성 분할에서 이 중첩을 이용한다."""
    after = _roll_sum(HB, 3, 0)
    before = _roll_sum(HB, 12, 3)
    stop = (before > 0) & (after == 0)
    bi, ti = np.where(stop)
    if not len(bi):
        return pd.DataFrame(columns=["broker_legal_id", "code", "month", "klass"])
    out = pd.DataFrame({
        "broker_legal_id": bs_lut.loc[bi, "broker_legal_id"].to_numpy(),
        "code": bs_lut.loc[bi, "code"].to_numpy(),
        "month": all_m.to_numpy()[ti], "klass": "H-EXIT",
    })
    out["event_date"] = out["month"]
    out["knowledge_date"] = out["month"]
    return pit_frame(out, "event_date", "knowledge_date", source="drops_house")


def build_aar_neg(S: "pd.DataFrame", L: "pd.DataFrame", months: "pd.DatetimeIndex"
                  ) -> "pd.DataFrame":
    """AAR_neg(i,t) = −[Σ w(event)] / |직전 정착 커버 로스터|.

    치역이 [−1.5, 0] 으로 **구조적으로 유계**다. 이 사실이 윈저라이즈를 금지하는 근거다
    (§7-F17 — 윈저라이즈하면 최악의 철회 5건이 단일값 하나로 붕괴한다).
    num>0 이면 den>0 이 논리적으로 보장되므로 0/0 이 발생하지 않는다.
    """
    cols = ["code", "month", "aar_neg", "n_drop", "n_roster"]
    if S is None or S.empty or L is None or L.empty:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    # 직전 정착 커버 로스터: t-1 기준 최근 12개월에 발간 이력이 있는 애널 수
    #   ★ DataFrame.rolling(axis=1) 은 pandas 3 에서 제거되었다. 조밀 행렬 + 이동최대로 푼다.
    roster = (x.groupby(["code", "month"], observed=True)["analyst_id"]
               .nunique().rename("n").reset_index())
    all_m2 = pd.DatetimeIndex(sorted(set(roster["month"].unique()) | set(months)))
    mp2 = {m: i for i, m in enumerate(all_m2)}
    c_codes, c_uniq = pd.factorize(as_str_series(roster["code"]))
    RM = np.zeros((len(c_uniq), len(all_m2)), dtype=np.float32)
    np.add.at(RM, (np.asarray(c_codes, dtype=np.int64),
                   roster["month"].map(mp2).to_numpy(dtype=np.int64)),
              roster["n"].to_numpy(dtype=np.float32))
    ROS = _shift_right(_roll_max(RM, COVER_WINDOW_M), 1)      # t-1 기준 최근 12M 최대
    ci, ti = np.where(ROS > 0)
    ros = pd.DataFrame({"code": np.asarray(c_uniq)[ci],
                        "month": all_m2.to_numpy()[ti],
                        "n_roster": ROS[ci, ti].astype("float64")})

    num = (S[S["w"] > 0].groupby(["code", "month"], observed=True)
             .agg(n_drop=("w", "size"), wsum=("w", "sum")).reset_index())
    if num.empty:
        return pd.DataFrame(columns=cols)
    out = num.merge(ros, on=["code", "month"], how="left")
    out["n_roster"] = pd.to_numeric(out["n_roster"], errors="coerce").fillna(0.0)
    out["n_roster"] = out["n_roster"].where(out["n_roster"] > 0, out["n_drop"])
    out["aar_neg"] = -(out["wsum"] / out["n_roster"]).clip(upper=NEG_W_HEXIT)
    out = out[out["month"].isin(months)]
    LOG.ok(f"AAR_neg {len(out):,}건 (종목×월) · 평균 {float(out['aar_neg'].mean()):.4f} · "
           f"최저 {float(out['aar_neg'].min()):.4f} (치역 [-{NEG_W_HEXIT}, 0] 유계)")
    return out[cols]



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  종목 단위 신호 — AAR_pos / AAR_neg / AAR_total 과 포트폴리오 구성                   ║
# ║                                                                                          ║
# ║  §6.4  AAR_pos(i,t) = Σ_a ω(a,t)·VAS(a,i,t) / Σ_a ω(a,t)                                 ║
# ║  §6.6  AAR_total    = z(AAR_pos) + λ·z(AAR_neg)                                          ║
# ║  §7    5분위 → Q5 롱온리 동일가중 → AAR_neg 하위 10% 강제 배제 → 하한 20종목              ║
# ║                                                                                          ║
# ║  ★★ 결측을 0 으로 채우면 신호가 **정반대로 뒤집힌다.** ★★                                 ║
# ║     AAR_pos 결측은 "주의 재배분이 0" 이 아니라 "주의를 잴 애널리스트가 없음" 이다.         ║
# ║     유니버스 2,400 중 커버 700 인 상황에서 0 으로 채우면 0 이 전체의 70.8% 를 차지해       ║
# ║     80분위수 자체가 정확히 0.0 이 되고, **채워진 미커버 종목 1,700개가 Q5 에 동점 진입**   ║
# ║     한다(Q5 크기 140 → 2,060). 신호가 "커버리지 없음 = 최상위 매수" 로 뒤집히는 것이다.    ║
# ║     → 채우지 말고 **유니버스를 제한(restrict)** 한다: U(t) = {유효 애널 2명 이상}.         ║
# ║                                                                                          ║
# ║  ★★ AAR_neg 는 윈저라이즈하지 않는다. ★★                                                  ║
# ║     치역이 [-1.5, 0] 으로 구조적으로 유계이고 90% 이상이 정확히 0 인 점질량 분포라,        ║
# ║     ±3σ 절단이 최악의 철회 5건을 단일값 하나로 붕괴시킨다(z: -7.86/-7.63/… → 전부 -4.415). ║
# ║     이 신호가 존재하는 이유인 사건을 정확히 지우는 셈이다.                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MIN_ANALYSTS_U = 2      # U(t) 편입 최소 유효 애널 수. 사전 고정 — 격자를 늘리지 않는다.


def build_aar_pos(V: "pd.DataFrame", weight_mode: str) -> "pd.DataFrame":
    """종목×월 AAR_pos + 유효 애널 수.

    ω(a,t) — §6.4 의 세 가지 기회비용 가중. H2 는 "기회비용 가중이 비가중보다 강하다"는
    메커니즘 조건부 예측이며, 한가한 애널리스트에서 더 강하면 데이터마이닝으로 판정된다.
      uw       : 1              (비가중)
      nreports : N(a,t)         (그 달 발간량 = 바쁜 정도)
      ncover   : 커버 종목 수   (커버리지 폭)
    """
    cols = ["code", "month", "aar_pos", "n_analyst", "w_mode"]
    if V is None or V.empty or "VAS" not in V.columns:
        return pd.DataFrame(columns=cols)
    d = V.dropna(subset=["VAS"]).copy()
    if d.empty:
        return pd.DataFrame(columns=cols)
    if weight_mode == "nreports":
        w = pd.to_numeric(d["N_t"], errors="coerce")
    elif weight_mode == "ncover":
        w = (d.groupby(["unit_id", "month"], observed=True)["code"]
              .transform("nunique").astype("float64"))
    else:
        w = pd.Series(1.0, index=d.index)
    d["_w"] = w.where(np.isfinite(w) & (w > 0), 1.0)
    d["_wv"] = d["_w"] * d["VAS"].astype("float64")
    g = d.groupby(["code", "month"], observed=True)
    out = g.agg(_num=("_wv", "sum"), _den=("_w", "sum"),
                n_analyst=("unit_id", "nunique")).reset_index()
    out["aar_pos"] = out["_num"] / out["_den"].where(out["_den"] > 0)
    out["w_mode"] = weight_mode
    return out[cols]


def assemble_signal(pos: "pd.DataFrame", neg: "pd.DataFrame", uni: "pd.DataFrame",
                    lam: float) -> "pd.DataFrame":
    """AAR_total = z(AAR_pos) + λ·z(AAR_neg). 유니버스는 U(t) 로 **제한**한다."""
    cols = ["code", "month", "aar_pos", "aar_neg", "z_pos", "z_neg", "aar_total",
            "n_analyst", "n_drop"]
    if pos is None or pos.empty:
        return pd.DataFrame(columns=cols)
    U = pos[pos["n_analyst"] >= MIN_ANALYSTS_U].copy()
    if U.empty:
        LOG.warn(f"유효 애널 {MIN_ANALYSTS_U}명 이상인 종목-월이 없습니다 — 신호를 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    # PIT 유니버스와 교집합 (상장·보통주·시총>0 조건을 통과한 것만)
    if uni is not None and len(uni):
        key = set(zip(as_str_series(uni["code"]), uni["month"]))
        U = U[[(c, m) in key for c, m in zip(as_str_series(U["code"]), U["month"])]]
    if U.empty:
        return pd.DataFrame(columns=cols)

    if neg is not None and len(neg):
        U = U.merge(neg[["code", "month", "aar_neg", "n_drop"]], on=["code", "month"], how="left")
    else:
        U["aar_neg"] = np.nan
        U["n_drop"] = np.nan
    # ★ AAR_neg 결측은 '철회 사건 없음' = 0 이 맞다(AAR_pos 결측과 성질이 다르다).
    #   AAR_pos 결측은 '잴 수 없음'이라 0 으로 채우면 거짓이지만,
    #   AAR_neg 는 U(t) 안에 있는 이상 커버 로스터가 존재하므로 '철회 0건'이 실제 관측이다.
    U["aar_neg"] = pd.to_numeric(U["aar_neg"], errors="coerce").fillna(0.0)
    U["n_drop"] = pd.to_numeric(U["n_drop"], errors="coerce").fillna(0.0)

    U["z_pos"] = xsec_z(U["aar_pos"], U["month"], min_n=CELL_MIN_N, k=WINSOR_SIGMA)
    U["z_neg"] = xsec_z(U["aar_neg"], U["month"], min_n=CELL_MIN_N, k=None)   # ★ 윈저 금지
    U["aar_total"] = U["z_pos"].astype("float64") + float(lam) * U["z_neg"].astype("float64")
    return U[cols]


def select_portfolio(S: "pd.DataFrame", month, uni_obj: Optional["Universe"] = None
                     ) -> Tuple[List[str], dict]:
    """5분위 → Q5 → AAR_neg 하위 10% 강제 배제 → 하한 검사. **순서 고정.**

    ★ 순진한 구현 `aar_neg <= aar_neg.quantile(0.10)` 은 재앙이다. 10분위수가 정확히 0.0
      이므로 그 한 줄이 유니버스 **전부를 배제**하고 포트폴리오가 조용히 전액 현금이 된다.
      '엄격히 음수' 조건과 rank(method='min') 을 함께 써야 무붕괴다. 하위10% 는 상한으로
      해석한다 — 철회가 10%보다 적은 달에는 배제도 그만큼만 일어난다.
    ★ 배제 임계는 **U(t) 전체 기준**이다. Q5 부분집합 기준으로 잡으면 매달 Q5 의 10% 가
      기계적으로 잘려나간다. 그리고 하드 거부권은 반드시 **마지막**에 적용한다 —
      배제를 먼저 하고 재분위하면 분위 경계가 이동해 거부권이 희석된다.
    """
    info = {"n_U": 0, "n_q5": 0, "n_excl": 0, "n_port": 0, "cash": False}
    sub = S[(S["month"] == month) & S["aar_total"].notna()]
    n_u = len(sub)
    info["n_U"] = n_u
    if n_u < PORT_QUANTILES * 2:
        info["cash"] = True
        return [], info
    try:
        q = pd.qcut(sub["aar_total"].rank(method="first"), PORT_QUANTILES,
                    labels=False, duplicates="drop")
    except Exception:
        info["cash"] = True
        return [], info
    top = int(np.nanmax(q.to_numpy())) if len(q) else 0
    q5 = sub[q == top]
    info["n_q5"] = len(q5)

    k = int(np.ceil(NEG_EXCLUDE_PCT * n_u))
    rk = sub["aar_neg"].rank(method="min", ascending=True)
    excl = set(as_str_series(sub.loc[(sub["aar_neg"] < 0) & (rk <= k), "code"]))
    info["n_excl"] = len(excl)

    port = [c for c in as_str_series(q5["code"]).tolist() if c not in excl]
    info["n_port"] = len(port)
    if len(port) < PORT_MIN_NAMES:
        info["cash"] = True
        return [], info
    return port, info


# ── 나이브 벤치마크 신호 (§8 — 통제의 가치를 보여주는 진짜 비교 대상) ───────────────────────
def build_naive_signal(L: "pd.DataFrame", months: "pd.DatetimeIndex",
                       uni: "pd.DataFrame") -> "pd.DataFrame":
    """"단순 리포트 건수 증가" 신호. **§6.3 통제를 전혀 하지 않은** 순진한 버전이다.

    이것이 AAR 의 진짜 비교 대상이다. AAR 이 이걸 못 이기면 §6.3 통제회귀와 축소추정,
    인과분해 전부가 불필요한 복잡도라는 뜻이고, 그 사실을 그대로 보고해야 한다.
    (KOSPI 를 이기는 것은 아무것도 증명하지 못한다 — 소형주 프리미엄일 수 있다)
    """
    cols = ["code", "month", "naive", "aar_total"]
    if L is None or L.empty:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    cnt = (x.groupby(["code", "month"], observed=True)["report_uid"]
            .nunique().rename("n").reset_index())
    all_m = pd.DatetimeIndex(sorted(set(cnt["month"].unique()) | set(months)))
    mp = {m: i for i, m in enumerate(all_m)}
    c_codes, c_uniq = pd.factorize(cnt["code"])
    M = np.zeros((len(c_uniq), len(all_m)), dtype=np.float32)
    np.add.at(M, (np.asarray(c_codes, dtype=np.int64),
                  cnt["month"].map(mp).to_numpy(dtype=np.int64)),
              cnt["n"].to_numpy(dtype=np.float32))
    base = np.zeros_like(M)
    cs = np.cumsum(M, axis=1)
    base[:, 1:] = cs[:, :-1]
    lag = np.zeros_like(M)
    if len(all_m) > LOOKBACK_M:
        lag[:, LOOKBACK_M + 1:] = cs[:, :len(all_m) - LOOKBACK_M - 1]
    base = (base - lag) / float(LOOKBACK_M)
    raw = M - base
    ci, ti = np.where((M > 0) | (base > 0))
    out = pd.DataFrame({"code": np.asarray(c_uniq)[ci], "month": all_m.to_numpy()[ti],
                        "naive": raw[ci, ti].astype("float64")})
    out = out[out["month"].isin(months)]
    if uni is not None and len(uni):
        key = set(zip(as_str_series(uni["code"]), uni["month"]))
        out = out[[(c, m) in key for c, m in zip(as_str_series(out["code"]), out["month"])]]
    out["aar_total"] = xsec_z(out["naive"], out["month"], min_n=CELL_MIN_N)
    out["aar_neg"] = 0.0
    out["n_analyst"] = np.nan
    LOG.info(f"나이브 신호(단순 리포트 건수 증가) {len(out):,}행 — §6.3 통제 없음. "
             f"AAR 이 이것을 이기지 못하면 통제회귀·축소추정·인과분해가 전부 불필요한 "
             f"복잡도라는 뜻입니다.")
    return out


def signal_grid() -> List[dict]:
    """§6.6 사전등록 파라미터 격자 — 정확히 12개. **확장 금지.**"""
    g = []
    for w in GRID_WEIGHTS:
        for lam in GRID_LAMBDA:
            for h in GRID_HOLD:
                g.append({"weight": w, "lam": lam, "hold": h,
                          "label": f"{w}|λ{lam:g}|{h}M"})
    if len(g) != 12:
        raise KillCriteria(
            f"사전등록 격자가 {len(g)}개입니다(12개여야 함). §6.6 은 3×2×2 로 고정되어 "
            f"있으며 확장은 사전등록 위반입니다. GRID_WEIGHTS/GRID_LAMBDA/GRID_HOLD 를 "
            f"원래 값으로 되돌리세요.")
    return g



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 + 비용 모델 (§7, §8)                                                    ║
# ║                                                                                          ║
# ║  · 월 1회 리밸런싱, 체결 = 신호 산출일 **익영업일 종가** (당일 종가 체결은 미래누수)        ║
# ║  · Q5 롱온리 **동일가중**, 종목당 상한 5%, 보유 하한 20종목(미달 시 현금 + 로그)           ║
# ║  · 보유기간 3개월은 **중첩 트랜치**로 구현한다: 매월 자본의 1/3 을 새로 넣고 3개월 보유.    ║
# ║    (특정 리밸런싱 월을 고르면 그 선택 자체가 자유 파라미터가 되어 사전등록을 위반한다)      ║
# ║  · 상장폐지: 승계면 사건 제외, 전손이면 -100%. 누락 처리 금지(누락 = 생존자편향).           ║
# ║  · 비용: 수수료 + 규모별 슬리피지 + **연도별 증권거래세 테이블**. 0/기본/2배 3종 보고.      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def sell_tax(dt, market: str) -> float:
    """매도 시 증권거래세. **단일 세율 금지** — 2016~2026 사이에 0.30%→0.15% 로 5번 바뀐다."""
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate.get(str(market).upper(), rate["OTHER"])


def size_bucket_of(marcap: float) -> str:
    """슬리피지 규모 구간. 시총 기준(조원): 대형 ≥1조 / 중형 ≥2천억 / 소형 그 외."""
    if marcap is None or not np.isfinite(marcap) or marcap <= 0:
        return "small"
    if marcap >= 1e12:
        return "large"
    if marcap >= 2e11:
        return "mid"
    return "small"


def trade_cost(side: str, month, market: str, marcap: float, mult: float = 1.0) -> float:
    """편도 거래비용(비율). side='buy'|'sell'."""
    c = COMMISSION_BPS / 1e4
    s = SLIPPAGE_BPS.get(size_bucket_of(marcap), SLIPPAGE_BPS["small"]) / 1e4
    tx = sell_tax(month, market) if side == "sell" else 0.0
    return (c + s + tx) * float(mult)


def run_backtest(S: "pd.DataFrame", panel: "pd.DataFrame", months: "pd.DatetimeIndex",
                 sec: "pd.DataFrame", hold: int = 1, cost_mult: float = 1.0,
                 label: str = "AAR", uni_obj: Optional["Universe"] = None,
                 min_adv: float = MIN_ADV_KRW) -> dict:
    """중첩 트랜치 백테스트. 반환 {returns, holdings, trades, label}."""
    px = panel[["code", "month", "fwd_ret1", "adv20", "marcap", "market", "exec_px"]].copy()
    px["code"] = as_str_series(px["code"])
    px["month"] = as_ts_series(px["month"])
    look = {(c, m): (r, a, mc, mk)
            for c, m, r, a, mc, mk in zip(px["code"], px["month"], px["fwd_ret1"],
                                          px["adv20"], px["marcap"], px["market"])}
    liq = {(c, m): a for c, m, a in zip(px["code"], px["month"], px["adv20"])}

    tranches: "OrderedDict[int, dict]" = OrderedDict()     # entry_month_idx → {codes, weights}
    rows, hold_log, trade_log = [], [], []
    prev_book: Dict[str, float] = {}

    for i, m in enumerate(months):
        # ── 신규 트랜치 선정 ───────────────────────────────────────────────────────────
        sub = S[S["month"] == m]
        if len(sub) and min_adv > 0:
            keep = [c for c in as_str_series(sub["code"])
                    if (liq.get((c, m)) is None or not np.isfinite(liq.get((c, m), np.nan))
                        or liq.get((c, m), 0) >= min_adv)]
            sub = sub[as_str_series(sub["code"]).isin(set(keep))]
        codes, info = select_portfolio(sub, m) if len(sub) else ([], {"cash": True})
        if uni_obj is not None:
            uni_obj.audit_row("신호보유(U)", m, sub["code"].tolist() if len(sub) else [])
            uni_obj.audit_row("Q5선정", m, [""] * int(info.get("n_q5", 0)))
            uni_obj.audit_row("배제후최종", m, codes)
        if codes:
            w = min(POS_MAX_WEIGHT, 1.0 / len(codes))       # 동일가중 + 종목당 상한
            tranches[i] = {"codes": codes, "w": w}
        else:
            tranches[i] = {"codes": [], "w": 0.0}
            if info.get("cash"):
                LOG.debug(f"{m:%Y-%m} 보유 하한({PORT_MIN_NAMES}) 미달 → 현금 "
                          f"(U={info.get('n_U',0)} Q5={info.get('n_q5',0)} "
                          f"배제={info.get('n_excl',0)})")
        for k in [k for k in tranches if k <= i - hold]:
            tranches.pop(k, None)

        # ── 현재 장부 (활성 트랜치 평균) ──────────────────────────────────────────────
        active = [t for k, t in tranches.items() if t["codes"]]
        book: Dict[str, float] = defaultdict(float)
        if active:
            share = 1.0 / hold                              # 트랜치당 자본 비중
            for t in tranches.values():
                if not t["codes"]:
                    continue
                for c in t["codes"]:
                    book[c] += t["w"] * share
        tot = sum(book.values())
        if tot > 1.0 + 1e-9:
            book = {c: v / tot for c, v in book.items()}

        # ── 비용 ──────────────────────────────────────────────────────────────────────
        cost = 0.0
        turn = 0.0
        for c in set(book) | set(prev_book):
            dw = book.get(c, 0.0) - prev_book.get(c, 0.0)
            if abs(dw) < 1e-9:
                continue
            turn += abs(dw)
            rec = look.get((c, m))
            mc = rec[2] if rec else np.nan
            mk = rec[3] if rec else "OTHER"
            cost += abs(dw) * trade_cost("buy" if dw > 0 else "sell", m, mk, mc, cost_mult)
            trade_log.append({"month": m, "code": c, "dw": dw,
                              "side": "buy" if dw > 0 else "sell"})

        # ── 다음 달 수익 ──────────────────────────────────────────────────────────────
        ret = 0.0
        for c, w in book.items():
            rec = look.get((c, m))
            fr = rec[0] if rec else np.nan
            fr = float(fr) if fr is not None and np.isfinite(fr) else 0.0
            ret += w * fr
            hold_log.append({"month": m, "code": c, "weight": w, "ret": fr})
        rows.append({"month": m, "ret": ret - cost, "ret_gross": ret, "n": len(book),
                     "turnover": turn, "cost": cost, "cash": 1.0 - sum(book.values())})
        prev_book = dict(book)

    R = pd.DataFrame(rows)
    R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
    return {"returns": R, "holdings": pd.DataFrame(hold_log),
            "trades": pd.DataFrame(trade_log), "label": label}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def perf_stats(R: "pd.DataFrame", rf: float = 0.0) -> dict:
    r = R["ret"].fillna(0).to_numpy(dtype=float)
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
    for xdd in dd:
        cur = cur + 1 if xdd < -1e-9 else 0
        mx = max(mx, cur)
    mu, t = hac_tstat(r)
    return {
        "월수": n, "누적수익": float(eq[-1] - 1), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(np.mean(r)),
        "t통계량(HAC)": t, "최장언더워터(월)": int(mx),
        "평균종목수": float(R["n"].mean()),
        "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
        "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan,
        "현금비중": float(R["cash"].mean()) if "cash" in R else np.nan,
    }


def right_tail_contribution(bt: dict) -> dict:
    """소수 종목 의존도. 상위 5% 를 빼면 성과가 사라지는지 반드시 측정해 보고한다."""
    H = bt.get("holdings")
    if H is None or H.empty:
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(contrib)
    if n == 0:
        return {}
    base = float(contrib.sum())
    out = {"총기여": base}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{lab} 제외 후"] = base - float(contrib.iloc[:k].sum())
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


def bench_stats(R: "pd.DataFrame", bench: Dict[str, "pd.Series"]) -> List[list]:
    rows = []
    S = R.set_index("month")["ret"].fillna(0)
    for name, b in bench.items():
        if b is None or not len(b):
            continue
        bb = pd.Series(b).reindex(S.index).fillna(0)
        ex = S - bb
        _, t = hac_tstat(ex.to_numpy())
        cum_s = float((1 + S).prod() - 1)
        cum_b = float((1 + bb).prod() - 1)
        ann_ex = float((1 + ex.mean()) ** 12 - 1)
        rows.append([name, f"{cum_b*100:+.1f}%", f"{cum_s*100:+.1f}%",
                     f"{(cum_s-cum_b)*100:+.1f}%p", f"{ann_ex*100:+.2f}%p",
                     f"{t:.2f}" if np.isfinite(t) else "—"])
    return rows



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-A  사전등록 가설 검정 H1~H5 + BH-FDR (§4, §9-5)                                        ║
# ║                                                                                          ║
# ║  H1  자발적 주의 증가(VAS+)는 이후 1~3개월 수익률을 양(+)으로 예측       기각: Q5−Q1 t<2.0 ║
# ║  H2  효과는 애널리스트의 **기회비용이 클수록** 강하다 (메커니즘 조건부)  기각: 역방향     ║
# ║  H3  자발적 철회(V-DROP)는 음(−) 예측, 인사이동(M-EXIT)은 예측력 없음    기각: 차이 t<2.0 ║
# ║  H4  효과는 저커버리지·소형주에서 강하다                                 기각: 역방향     ║
# ║  H5  VAS 는 **컨센서스 개정에 선행한다**                                 기각: 선행성 없음║
# ║                                                                                          ║
# ║  ★ H5 가 이 전략의 경제적 정당성이다. 주의 재배분이 컨센서스 개정보다 늦다면              ║
# ║    이 신호는 그냥 '느린 개정 대리변수'이고 독립적 가치가 없다(§11 CONDITIONAL).            ║
# ║                                                                                          ║
# ║  ★ 다중검정 보정: 5개 가설에 BH-FDR(q=0.10). "다섯 개 세워두고 하나 통과하면 성공"은        ║
# ║    이 프로젝트에서 가장 흔한 자기기만이므로 구조적으로 막는다.                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HYPO: "OrderedDict[str, dict]" = OrderedDict()


def _record_h(hid: str, name: str, passed: Optional[bool], p: float, detail: str,
              metrics: Optional[dict] = None):
    HYPO[hid] = {"id": hid, "name": name, "pass": (None if passed is None else bool(passed)),
                 "p": (float(p) if p is not None and np.isfinite(p) else np.nan),
                 "detail": detail, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 기각", None: "— 판정불가"}[HYPO[hid]["pass"]]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{hid}] {name} → {icon} · {detail}")


def quantile_spread(S: "pd.DataFrame", panel: "pd.DataFrame", months, hold: int = 1,
                    signal_col: str = "aar_total") -> "pd.DataFrame":
    """월별 Q5−Q1 스프레드 시계열. 백테스트 엔진과 별개로 신호 자체의 예측력을 본다."""
    fwd_col = f"fwd_ret{hold}"
    if fwd_col not in panel.columns:
        fwd_col = "fwd_ret1"
    P = panel[["code", "month", fwd_col]].copy()
    P["code"] = as_str_series(P["code"])
    P["month"] = as_ts_series(P["month"])
    # ★ 호출자가 이미 수익률 컬럼을 붙여 온 프레임을 넘기면 merge 가 _x/_y 접미사를 만들어
    #   dropna(subset=[fwd_col]) 가 KeyError 로 죽는다. 신호 컬럼만 남기고 결합한다.
    Sx = S[[c for c in S.columns if c not in P.columns or c in ("code", "month")]].copy()
    Sx["code"] = as_str_series(Sx["code"])
    Sx["month"] = as_ts_series(Sx["month"])
    d = Sx.merge(P, on=["code", "month"], how="inner").dropna(subset=[signal_col, fwd_col])
    rows = []
    for m, g in d.groupby("month", observed=True):
        if len(g) < PORT_QUANTILES * 4:
            continue
        try:
            q = pd.qcut(g[signal_col].rank(method="first"), PORT_QUANTILES,
                        labels=False, duplicates="drop")
        except Exception:
            continue
        hi, lo = int(np.nanmax(q)), int(np.nanmin(q))
        if hi == lo:
            continue
        r5 = float(g.loc[q == hi, fwd_col].mean())
        r1 = float(g.loc[q == lo, fwd_col].mean())
        rows.append({"month": m, "q5": r5, "q1": r1, "spread": r5 - r1,
                     "n": len(g), "mkt": float(g[fwd_col].mean())})
    out = pd.DataFrame(rows)
    if len(out) and hold > 1:
        # 중첩 보유의 자기상관은 HAC 이 처리한다. 스프레드는 hold 개월 수익이므로
        # 월 환산해 다른 보유기간과 비교 가능하게 만든다.
        out["spread"] = (1.0 + out["spread"]) ** (1.0 / hold) - 1.0
    return out


def test_H1(S: "pd.DataFrame", panel: "pd.DataFrame", months) -> Tuple[bool, float, dict]:
    res = {}
    best_t = -np.inf
    detail = []
    for h in GRID_HOLD:
        sp = quantile_spread(S, panel, months, hold=h)
        if len(sp) < 24:
            detail.append(f"{h}M: 표본 {len(sp)}개월로 부족")
            continue
        mu, t = hac_tstat(sp["spread"].to_numpy())
        res[f"{h}M"] = {"mean": mu, "t": t, "n": len(sp)}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        detail.append(f"{h}M 스프레드 {mu*100:+.3f}%p/월 (HAC t={t:.2f}, {len(sp)}개월)")
    if not res:
        _record_h("H1", "VAS+ 의 양(+) 예측력", None, np.nan, "표본 부족 — 판정 불가", res)
        return (False, np.nan, res)
    p = t_to_p(best_t, dof=max(12, min(v["n"] for v in res.values()) - 1))
    passed = bool(np.isfinite(best_t) and best_t >= 2.0)
    _record_h("H1", "VAS+ 의 양(+) 예측력", passed, p,
              " · ".join(detail) + f" → 기각기준 t<2.0, 최대 t={best_t:.2f}", res)
    return passed, p, res


def test_H2(sig_by_weight: Dict[str, "pd.DataFrame"], panel: "pd.DataFrame",
            months) -> Tuple[Optional[bool], float, dict]:
    """기회비용 가중(발간량·커버리지폭)이 비가중보다 강한가.

    ★ 한가한 애널리스트에서 더 강하면 데이터마이닝 판정이다(명세 §4). 부호를 본다.
    검정: 가중팔 스프레드 − 비가중팔 스프레드 의 HAC t (짝지은 시계열 차이)."""
    if "uw" not in sig_by_weight:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, "비가중 팔이 없어 판정 불가")
        return None, np.nan, {}
    base = quantile_spread(sig_by_weight["uw"], panel, months, hold=1)
    if len(base) < 24:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, f"표본 {len(base)}개월로 부족")
        return None, np.nan, {}
    res, rows, best_t = {}, [], -np.inf
    for w in ("nreports", "ncover"):
        if w not in sig_by_weight:
            continue
        arm = quantile_spread(sig_by_weight[w], panel, months, hold=1)
        j = base.merge(arm, on="month", suffixes=("_uw", f"_{w}"))
        if len(j) < 24:
            continue
        diff = (j[f"spread_{w}"] - j["spread_uw"]).to_numpy()
        mu, t = hac_tstat(diff)
        res[w] = {"diff": mu, "t": t, "n": len(j)}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        rows.append([w, f"{float(j[f'spread_{w}'].mean())*100:+.3f}%p",
                     f"{float(j['spread_uw'].mean())*100:+.3f}%p",
                     f"{mu*100:+.3f}%p", f"{t:.2f}",
                     "기회비용 가중이 우세" if mu > 0 else "★ 비가중이 우세 — 데이터마이닝 신호"])
    if not res:
        _record_h("H2", "기회비용 가중 우위", None, np.nan, "비교 가능한 가중 팔이 없습니다")
        return None, np.nan, res
    LOG.table(rows, ["가중 방식", "가중팔 스프레드", "비가중 스프레드", "차이", "HAC t", "판정"],
              ["l", "r", "r", "r", "r", "l"],
              title="H2 메커니즘 검정 — 바쁜 애널리스트가 특정 종목에 몰릴 때 더 강한가")
    p = t_to_p(best_t, dof=max(12, min(v["n"] for v in res.values()) - 1))
    passed = bool(np.isfinite(best_t) and best_t > 1.0)
    _record_h("H2", "기회비용 가중 우위", passed, p,
              f"최대 차이 t={best_t:.2f} " +
              ("— 기회비용이 큰 애널의 주의가 더 정보적입니다." if passed else
               "— 기회비용 가중이 비가중을 유의하게 이기지 못했습니다. 메커니즘 예측이 "
               "성립하지 않으므로 §11 ACCEPT 조건 미충족입니다."), res)
    return passed, p, res


def test_H3(drops: "pd.DataFrame", panel: "pd.DataFrame", months) -> Tuple[Optional[bool], float, dict]:
    """V-DROP(+H-EXIT) 은 음(−), M-EXIT 은 예측력 없음. **캘린더타임**으로 검정한다.

    ★ 겹치는 이벤트 창의 횡단면 상관 때문에 CAR 의 단순 t검정은 표준오차를 크게
      과소추정한다. 캘린더타임 포트폴리오는 각 달의 관측이 하나뿐이라 SE 가 정직하다."""
    if drops is None or drops.empty:
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan, "철회 사건이 없습니다")
        return None, np.nan, {}
    d = drops.copy()
    d["grp"] = np.where(d["klass"].isin(["V-DROP", "H-EXIT"]), "자발적철회",
                        np.where(d["klass"] == "M-EXIT", "M-EXIT(플라시보)", "기타"))
    ct = calendar_time_alpha(d[d["grp"] != "기타"], panel, months, hold_m=6, group_col="grp")
    if ct.empty or ct["t_hac"].isna().all():
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan,
                  "캘린더타임 포트폴리오를 만들 표본이 부족합니다")
        return None, np.nan, {}
    LOG.table([[r["group"], f"{int(r['n_months'])}", f"{r['avg_names']:.1f}",
                f"{r['mean_excess_m']*100:+.3f}%p", f"{r['t_hac']:.2f}",
                f"{r['p']:.4f}" if np.isfinite(r["p"]) else "—",
                f"{r['ann_excess']*100:+.1f}%"] for _, r in ct.iterrows()],
              ["군", "월수", "평균종목수", "월평균 초과", "HAC t", "p", "연환산"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="H3 캘린더타임 포트폴리오 (겹치는 이벤트 창의 상관을 구조적으로 제거)")
    v = ct[ct["group"] == "자발적철회"]
    mm = ct[ct["group"] == "M-EXIT(플라시보)"]
    tv = float(v["t_hac"].iloc[0]) if len(v) else np.nan
    tm = float(mm["t_hac"].iloc[0]) if len(mm) else np.nan
    mv = float(v["mean_excess_m"].iloc[0]) if len(v) else np.nan
    mm_ = float(mm["mean_excess_m"].iloc[0]) if len(mm) else np.nan
    res = {"t_vdrop": tv, "t_mexit": tm, "mean_vdrop": mv, "mean_mexit": mm_}
    if not np.isfinite(tv):
        _record_h("H3", "자발적 철회의 음(−) 예측력", None, np.nan, "자발적 철회군 표본 부족", res)
        return None, np.nan, res
    p = t_to_p(tv, dof=max(12, int(v["n_months"].iloc[0]) - 1))
    passed = bool(mv < 0 and tv <= -2.0)
    _record_h("H3", "자발적 철회의 음(−) 예측력", passed, p,
              f"자발적 철회 {mv*100:+.3f}%p/월 (t={tv:.2f}) vs "
              f"M-EXIT {mm_*100:+.3f}%p/월 (t={tm:.2f}). " +
              ("자발적 철회가 유의한 음의 예측력을 가집니다." if passed else
               "자발적 철회의 음의 예측력이 기각기준(t≤-2.0)에 미달합니다."), res)
    return passed, p, res


def test_H4(S: "pd.DataFrame", panel: "pd.DataFrame", uni: "pd.DataFrame",
            months) -> Tuple[Optional[bool], float, dict]:
    """저커버리지·소형주에서 더 강한가. 조건부 분할 스프레드를 비교한다."""
    P = panel[["code", "month", "fwd_ret1"]].copy()
    P["code"] = as_str_series(P["code"])
    U = uni[["code", "month", "size_pct"]].copy()
    U["code"] = as_str_series(U["code"])
    d = (S.merge(P, on=["code", "month"], how="inner")
          .merge(U, on=["code", "month"], how="left")
          .dropna(subset=["aar_total", "fwd_ret1"]))
    if len(d) < 500:
        _record_h("H4", "소형·저커버리지 조건부 강도", None, np.nan, "표본 부족")
        return None, np.nan, {}
    rows, res, best_t = [], {}, -np.inf
    for cut_name, col, lo_lab, hi_lab in (("규모", "size_pct", "소형(하위50%)", "대형(상위50%)"),
                                          ("커버리지", "n_analyst", "저커버(하위50%)", "고커버(상위50%)")):
        if col not in d.columns or d[col].notna().sum() < 200:
            continue
        med = d.groupby("month", observed=True)[col].transform("median")
        lo = d[d[col] <= med]
        hi = d[d[col] > med]
        sp_l = quantile_spread(lo, panel, months, hold=1)
        sp_h = quantile_spread(hi, panel, months, hold=1)
        if len(sp_l) < 24 or len(sp_h) < 24:
            continue
        j = sp_l.merge(sp_h, on="month", suffixes=("_lo", "_hi"))
        diff = (j["spread_lo"] - j["spread_hi"]).to_numpy()
        mu, t = hac_tstat(diff)
        res[cut_name] = {"diff": mu, "t": t}
        best_t = max(best_t, t if np.isfinite(t) else -np.inf)
        rows.append([cut_name, lo_lab, f"{float(j['spread_lo'].mean())*100:+.3f}%p",
                     hi_lab, f"{float(j['spread_hi'].mean())*100:+.3f}%p",
                     f"{mu*100:+.3f}%p", f"{t:.2f}",
                     "예측 방향과 일치" if mu > 0 else "★ 반대 방향(대형에서 강함)"])
    if not rows:
        _record_h("H4", "소형·저커버리지 조건부 강도", None, np.nan, "분할 표본이 부족합니다")
        return None, np.nan, res
    LOG.table(rows, ["분할", "약군", "약군 스프레드", "강군", "강군 스프레드", "차이", "HAC t", "판정"],
              ["l", "l", "r", "l", "r", "r", "r", "l"], title="H4 조건부 예측 검정")
    p = t_to_p(best_t, dof=24)
    passed = bool(np.isfinite(best_t) and best_t > 1.0)
    _record_h("H4", "소형·저커버리지 조건부 강도", passed, p,
              f"최대 차이 t={best_t:.2f}", res)
    return passed, p, res


def build_consensus_revision(L: "pd.DataFrame", months) -> "pd.DataFrame":
    """컨센서스 개정 대리변수 — 목표주가 리비전.

    ★ 한계 명시: 역사적 컨센서스 fwd EPS 시계열은 복원이 불가능하다. 그래서 §5 의
      '컨센서스 EPS 추정치' 를 **같은 애널리스트가 같은 종목에 제시한 목표주가의 개정**
      으로 대체한다. 개정 방향은 EPS 개정과 강하게 동행하므로 선행성 검정의 취지는
      보존되지만, 이것이 대리변수라는 사실을 결과 해석에 반드시 반영해야 한다.
      (그래서 H5 결과는 '컨센서스 개정 대리변수 대비 선행성' 으로만 서술한다)
    """
    cols = ["code", "month", "rev"]
    if L is None or L.empty or "target_price" not in L.columns:
        return pd.DataFrame(columns=cols)
    x = L.dropna(subset=["code", "target_price"]).copy()
    x["month"] = as_ts_series(x["month"]) + pd.offsets.MonthEnd(0)
    x["code"] = as_str_series(x["code"])
    x = x.sort_values(["code", "analyst_id", "pub_date"])
    x["prev_tp"] = x.groupby(["code", "analyst_id"], observed=True)["target_price"].shift(1)
    x["dir"] = np.where(x["target_price"] > x["prev_tp"] * 1.001, 1.0,
                        np.where(x["target_price"] < x["prev_tp"] * 0.999, -1.0, 0.0))
    x.loc[x["prev_tp"].isna(), "dir"] = np.nan
    r = (x.dropna(subset=["dir"]).groupby(["code", "month"], observed=True)["dir"]
          .mean().rename("rev").reset_index())
    r = r[r["month"].isin(months)]
    LOG.info(f"컨센서스 개정 대리변수(목표주가 리비전) {len(r):,}건 · "
             f"상향 비중 {float((r['rev']>0).mean())*100:.1f}%")
    return r[cols]


def test_H5(V: "pd.DataFrame", rev: "pd.DataFrame", months) -> Tuple[Optional[bool], float, dict]:
    """VAS 가 컨센서스 개정에 **선행**하는가 (양방향 패널 그레인저)."""
    if V is None or V.empty or rev is None or rev.empty:
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan,
                  "VAS 또는 컨센서스 개정 대리변수가 없어 판정 불가")
        return None, np.nan, {}
    vas_i = (V.dropna(subset=["VAS"]).groupby(["code", "month"], observed=True)["VAS"]
              .mean().rename("vas").reset_index())
    d = vas_i.merge(rev, on=["code", "month"], how="inner")
    if len(d) < 500:
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan,
                  f"공통 관측 {len(d):,}행으로 부족 — 판정 불가")
        return None, np.nan, {}
    fwd = panel_granger(d, cause="vas", effect="rev", entity="code", time="month", lags=3)
    bwd = panel_granger(d, cause="rev", effect="vas", entity="code", time="month", lags=3)
    LOG.table([["VAS → 컨센서스 개정 (선행)", f"{fwd.get('F', np.nan):.2f}",
                f"{fwd.get('p', np.nan):.4g}", f"{fwd.get('n', 0):,}"],
               ["컨센서스 개정 → VAS (후행)", f"{bwd.get('F', np.nan):.2f}",
                f"{bwd.get('p', np.nan):.4g}", f"{bwd.get('n', 0):,}"]],
              ["방향", "F", "p", "관측"], ["l", "r", "r", "r"],
              title="H5 양방향 패널 그레인저 (개체·시간 고정효과, lag 1~3)")
    pf, pb = fwd.get("p", np.nan), bwd.get("p", np.nan)
    res = {"p_fwd": pf, "p_bwd": pb, "F_fwd": fwd.get("F"), "F_bwd": bwd.get("F")}
    if not np.isfinite(pf):
        _record_h("H5", "컨센서스 개정 대비 선행성", None, np.nan, "그레인저 검정 산출 실패", res)
        return None, np.nan, res
    lead = bool(pf < 0.05 and (not np.isfinite(pb) or fwd.get("F", 0) > bwd.get("F", 0)))
    _record_h("H5", "컨센서스 개정 대비 선행성", lead, pf,
              f"선행 p={pf:.4g} (F={fwd.get('F', np.nan):.2f}) vs "
              f"후행 p={pb:.4g} (F={bwd.get('F', np.nan):.2f}). " +
              ("VAS 가 개정보다 먼저 움직입니다 — 독립적 정보 가치가 있습니다."
               if lead else
               "★ 선행성을 보이지 못했습니다. §11 CONDITIONAL — 이 신호는 컨센서스 개정의 "
               "느린 대리변수일 수 있으므로 독립 배분을 금지하고 기존 개정 팩터와의 "
               "상관 분석만 수행해야 합니다."), res)
    return lead, pf, res


def finalize_hypotheses() -> "pd.DataFrame":
    """BH-FDR(q=0.10) 적용 후 최종 판정표."""
    ids = list(HYPO)
    if not ids:
        return pd.DataFrame()
    p = np.array([HYPO[i]["p"] for i in ids], dtype=float)
    rej, padj = bh_fdr(p, q=FDR_Q)
    rows = []
    for i, hid in enumerate(ids):
        h = HYPO[hid]
        raw = {True: "통과", False: "기각", None: "판정불가"}[h["pass"]]
        fdr_ok = ("—" if not np.isfinite(p[i]) else ("생존" if rej[i] else "탈락"))
        final = (h["pass"] is True) and (rej[i] if np.isfinite(p[i]) else False)
        h["fdr_pass"] = bool(final)
        rows.append([hid, _trunc(h["name"], 28), raw,
                     f"{p[i]:.4g}" if np.isfinite(p[i]) else "—",
                     f"{padj[i]:.4g}" if np.isfinite(padj[i]) else "—",
                     fdr_ok, "✔ 최종통과" if final else "✘"])
    LOG.table(rows, ["ID", "가설", "개별판정", "p", "보정 p", f"BH-FDR(q={FDR_Q})", "최종"],
              ["l", "l", "c", "r", "r", "c", "c"],
              title="사전등록 가설 최종 판정 (다중검정 보정 후) — "
                    "다섯 개 중 하나 통과를 성공이라 부르지 않기 위한 장치")
    return pd.DataFrame([{**HYPO[i], "p_adj": float(padj[k])} for k, i in enumerate(ids)])



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-B  강건성 스위트 (§9)                                                                 ║
# ║   R1 블록 부트스트랩   R2 PBO(CSCV)   R3 DSR   R4 워크포워드                              ║
# ║   R5 M-EXIT 플라시보(TOST)   R6 이벤트스터디 CAR   R7 비용 민감도                         ║
# ║   R8 누수 민감도(확장창 vs 전기간)   R9 레짐·하위기간   R10 나이브 대비                    ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이         ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§13). 나쁜 결과는 그 자체로 정보다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: "OrderedDict[str, dict]" = OrderedDict()


def _rec(rid: str, name: str, passed: Optional[bool], detail: str,
         kill: bool = False, metrics: Optional[dict] = None):
    passed = None if passed is None else bool(passed)      # np.bool_ 방어 (`is False` 함정)
    ROBUST[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                   "kill": kill, "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[passed]
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → {icon} · {detail}")
    if passed is False and kill and STOP_ON_KILL_CRITERIA:
        raise KillCriteria(f"[{rid}] {name} — {detail}")


def R1_bootstrap(bt: dict) -> None:
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    rows, verdicts = [], []
    for b in (1, 3, 6):
        res = block_bootstrap(r, n_iter=1000, block=b, seed=SEED)
        rows.append([f"{b}개월", f"{res['point']*100:+.3f}%p",
                     f"[{res['ci_lo']*100:+.3f}, {res['ci_hi']*100:+.3f}]",
                     f"{res['p_gt0']:.4f}", res["verdict"]])
        verdicts.append(res)
    LOG.table(rows, ["블록 길이", "월평균", "95% 신뢰구간", "P(≤0)", "판정"],
              ["c", "r", "r", "r", "l"],
              title="R1 블록 부트스트랩 1,000회 — 블록 길이는 추론 파라미터이지 "
                    "전략 파라미터가 아니므로 여러 개 보고해도 시행횟수에 들어가지 않습니다")
    base = verdicts[0]
    ok = bool(np.isfinite(base["ci_lo"]) and base["ci_lo"] > 0)
    _rec("R1", "블록 부트스트랩", ok,
         f"블록 1개월 기준 95% CI [{base['ci_lo']*100:+.3f}, {base['ci_hi']*100:+.3f}]%p, "
         f"P(평균≤0)={base['p_gt0']:.4f}",
         metrics=base)


def R2_pbo(grid_returns: "pd.DataFrame") -> None:
    if grid_returns is None or grid_returns.empty or grid_returns.shape[1] < 2:
        _rec("R2", "PBO (CSCV)", None, "구성이 2개 미만이라 판정 불가")
        return
    res = pbo_cscv(grid_returns.to_numpy(dtype=float), S=10, max_combos=400, seed=SEED)
    ok = np.isfinite(res.get("pbo", np.nan)) and res["pbo"] < 0.5
    _rec("R2", "PBO (CSCV 정식)", ok if np.isfinite(res.get("pbo", np.nan)) else None,
         f"PBO={res.get('pbo', float('nan')):.3f} "
         f"(조합 {res.get('n_combos', 0)}개, 구성 {res.get('N', 0)}개, "
         f"{res.get('T', 0)}개월) · {res.get('verdict', '')}",
         kill=True, metrics=res)


def R3_dsr(bt: dict, grid_returns: "pd.DataFrame") -> None:
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    sr_trials = None
    if grid_returns is not None and len(grid_returns.columns) >= 3:
        sr_trials = [float(_sharpe_raw(grid_returns[c].to_numpy(dtype=float)))
                     for c in grid_returns.columns]
    # ★ 시행횟수는 격자 12 × 유니버스 변형 2 = 24 로 센다. 적게 세는 것은 항상 낙관 방향이다.
    n_trials = len(GRID_WEIGHTS) * len(GRID_LAMBDA) * len(GRID_HOLD) * len(UNIVERSE_VARIANTS)
    res = deflated_sharpe(r, n_trials=n_trials, sr_trials=sr_trials)
    ok = np.isfinite(res.get("dsr", np.nan)) and res["dsr"] > 0.90
    _rec("R3", "DSR (과적합 보정 Sharpe)",
         ok if np.isfinite(res.get("dsr", np.nan)) else None,
         f"DSR={res.get('dsr', float('nan')):.3f} · 관측 SR(월) {res.get('sr', float('nan')):.3f} "
         f"vs 기대최대 SR* {res.get('sr_star', float('nan')):.3f} · 시행 {n_trials}회 "
         f"· 분산근거: {res.get('var_source', '')} · {res.get('verdict', '')}",
         kill=True, metrics=res)


def R4_walkforward(grid_returns: "pd.DataFrame", months) -> None:
    if grid_returns is None or grid_returns.empty:
        _rec("R4", "워크포워드", None, "격자 수익률이 없습니다")
        return
    res = walk_forward(grid_returns.to_numpy(dtype=float), months,
                       list(grid_returns.columns), train_y=5, test_y=1)
    if len(res.get("table", pd.DataFrame())):
        t = res["table"]
        LOG.table([[r["학습구간"], r["검증구간"], r["IS최적구성"], f"{r['IS Sharpe']}",
                    f"{r['OOS 월평균']}%p", f"{r['전구성 OOS 평균']}%p", r["판정"]]
                   for _, r in t.iterrows()],
                  ["학습", "검증", "IS 최적", "IS Sharpe", "OOS 월평균", "전구성 평균", "판정"],
                  ["l", "l", "l", "r", "r", "r", "l"],
                  title="R4 워크포워드 (학습 5년 / 검증 1년) — AAR 은 학습할 파라미터가 "
                        "없으므로 이것이 검정하는 것은 '구성 선택의 안정성'입니다")
    ok = (np.isfinite(res.get("oos_t", np.nan)) and res["oos_t"] > 1.0
          and res.get("folds", 0) >= 2)
    _rec("R4", "워크포워드", ok if res.get("folds", 0) >= 2 else None,
         res.get("verdict", ""), metrics={k: v for k, v in res.items() if k != "table"})


def R5_mexit_placebo(drops: "pd.DataFrame", panel: "pd.DataFrame", months) -> None:
    """★ 인과분해의 플라시보 검정 — 이 전략의 존재 이유를 검정한다.

    M-EXIT(인사이동에 의한 기계적 철회)에서도 음의 수익률이 나오면, 분해가 실패한 것이며
    신호는 그냥 '커버리지 감소 = 소외주' 를 재발견한 것이다.

    ★ "효과 없음"을 주장하려면 귀무가설 채택이 아니라 **등가성 검정(TOST)** 이 필요하다.
      등가 범위는 사전에 V-DROP 효과의 절반으로 고정한다 — 사후 조정은 검정을 무의미하게 만든다.
    ★ 표본이 부족하면 '통과'가 아니라 **판정불가(INCONCLUSIVE)** 로 낸다.
      월간 초과수익 sd 12% 에서 N=200 이면 CI 반폭이 1.66%p 라 -1%/월 효과를 통째로 덮는다.
    """
    if drops is None or drops.empty:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None, "철회 사건이 없습니다", kill=False)
        return
    d = drops.copy()
    d["grp"] = np.where(d["klass"].isin(["V-DROP", "H-EXIT"]), "V",
                        np.where(d["klass"] == "M-EXIT", "M", "X"))
    dd = d[d["grp"].isin(("V", "M"))]
    n_m = int((dd["grp"] == "M").sum())
    ct = calendar_time_alpha(dd, panel, months, hold_m=6, group_col="grp")
    if ct.empty:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None, "캘린더타임 표본 부족", kill=False)
        return
    vr = ct[ct["group"] == "V"]
    mr = ct[ct["group"] == "M"]
    mv = float(vr["mean_excess_m"].iloc[0]) if len(vr) else np.nan
    mm = float(mr["mean_excess_m"].iloc[0]) if len(mr) else np.nan
    tm = float(mr["t_hac"].iloc[0]) if len(mr) else np.nan
    if not np.isfinite(mv) or not np.isfinite(mm):
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None,
             "두 군 중 하나의 캘린더타임 시계열을 만들 수 없습니다", kill=False)
        return

    bound = abs(mv) / 2.0
    # M-EXIT 캘린더타임 시계열을 다시 만들어 TOST 를 적용한다
    F = panel[["code", "month", "fwd_ret"]].dropna().copy()
    F["code"] = as_str_series(F["code"])
    mk = F.groupby("month", observed=True)["fwd_ret"].mean().rename("mkt")
    F = F.merge(mk, on="month", how="left")
    F["ex"] = F["fwd_ret"] - F["mkt"]
    sub = dd[dd["grp"] == "M"]
    ser = []
    for m in months:
        lo = add_months(m, -5)
        names = set(as_str_series(sub.loc[(sub["month"] >= lo) & (sub["month"] <= m), "code"]))
        if not names:
            continue
        s = F[(F["month"] == m) & (F["code"].isin(names))]
        if len(s):
            ser.append(float(s["ex"].mean()))
    tost = tost_equivalence(np.array(ser), bound=bound) if len(ser) >= 12 else \
        {"equivalent": None, "verdict": f"M-EXIT 캘린더타임 관측 {len(ser)}개월로 부족"}

    n_need = 2200
    underpowered = n_m < n_need
    LOG.table([["V-DROP+H-EXIT 월평균 초과", f"{mv*100:+.3f}%p"],
               ["M-EXIT 월평균 초과", f"{mm*100:+.3f}%p (t={tm:.2f})"],
               ["사전 고정 등가범위 ±Δ", f"{bound*100:.3f}%p (= |V-DROP 효과| / 2)"],
               ["TOST 판정", str(tost.get("verdict", ""))[:70]],
               ["M-EXIT 사건 수", f"{n_m:,} (검정력 확보 기준 {n_need:,})"],
               ["검정력", "부족 — 판정불가로 처리" if underpowered else "충분"]],
              ["항목", "값"], ["l", "r"],
              title="R5 M-EXIT 플라시보 — '효과 없음'은 등가성 검정으로만 주장할 수 있습니다")

    if underpowered or tost.get("equivalent") is None:
        _rec("R5", "M-EXIT 플라시보 (인과분해)", None,
             f"M-EXIT 표본 {n_m:,}건으로 '효과 없음'을 통계적으로 주장할 검정력이 없습니다"
             f"(필요 {n_need:,}건). 통과가 아니라 **판정불가**로 보고합니다 — "
             f"표본 부족을 '통과'로 읽는 것이 이 검정의 가장 흔한 오용입니다.",
             kill=False, metrics={"n_mexit": n_m, "mean_mexit": mm, "mean_vdrop": mv})
        return
    ok = bool(tost.get("equivalent")) and abs(mm) < abs(mv) / 2.0
    _rec("R5", "M-EXIT 플라시보 (인과분해)", ok,
         f"M-EXIT {mm*100:+.3f}%p/월 이 ±{bound*100:.3f}%p 등가범위 "
         f"{'안에 있습니다 — 인과분해 성립' if ok else '밖입니다 — ★인과분해 실패. 신호는 '}"
         f"{'' if ok else '단순히 커버리지 감소를 재발견한 것일 수 있습니다'}",
         kill=True, metrics={"n_mexit": n_m, "mean_mexit": mm, "mean_vdrop": mv, **tost})


def R6_event_study(drops: "pd.DataFrame", daily: "pd.DataFrame",
                   daily_mkt: "pd.Series") -> "pd.DataFrame":
    if drops is None or drops.empty or daily is None or daily.empty:
        _rec("R6", "이벤트 스터디 CAR", None, "표본이 없습니다")
        return pd.DataFrame()
    d = drops.copy()
    d["exit_type"] = d["klass"]
    px = daily.rename(columns={"adj_close": "close"})[["code", "date", "close"]]
    car = event_study_car(d, px, daily_mkt, horizon=120, group_col="exit_type")
    if car.empty:
        _rec("R6", "이벤트 스터디 CAR", None, "CAR 을 산출하지 못했습니다")
        return car
    marks = [20, 60, 120]
    rows = []
    for g, gg in car.groupby("group"):
        row = [g, f"{int(gg['n'].max()):,}"]
        for h in marks:
            v = gg[gg["h"] == h]
            row.append(f"{float(v['mean_car'].iloc[0])*100:+.2f}%" if len(v) else "—")
        rows.append(row)
    LOG.table(rows, ["군", "사건수"] + [f"CAR t+{h}일" for h in marks],
              ["l", "r"] + ["r"] * len(marks),
              title="R6 이벤트 스터디 — 시장조정 CAR (설명용 곡선). "
                    "유의성 판정은 겹치는 창의 상관 때문에 캘린더타임(H3/R5)으로만 합니다")
    _rec("R6", "이벤트 스터디 CAR", True,
         f"{car['group'].nunique()}개 군 × 120영업일 CAR 곡선 산출 완료 "
         f"(유의성은 캘린더타임 검정 결과를 보십시오)")
    return car


def R7_cost_sensitivity(run_fn: Callable, scenarios: Dict[str, float]) -> None:
    rows, surv = [], None
    for nm, mult in scenarios.items():
        bt = run_fn(cost_mult=mult, label=f"cost_{nm}")
        s = perf_stats(bt["returns"])
        rows.append([nm, f"×{mult:g}", f"{s.get('CAGR', np.nan)*100:+.2f}%",
                     f"{s.get('Sharpe', np.nan):.3f}", f"{s.get('월평균', np.nan)*100:+.3f}%p",
                     f"{s.get('월평균비용', np.nan)*100:.3f}%p",
                     f"{s.get('t통계량(HAC)', np.nan):.2f}"])
        if nm == "기본":
            surv = s
    LOG.table(rows, ["시나리오", "배수", "CAGR", "Sharpe", "월평균", "월평균비용", "HAC t"],
              ["l", "c", "r", "r", "r", "r", "r"],
              title="R7 비용 민감도 (§7.1 — 0 / 기본 / 2배 3종 전부 보고)")
    ok = bool(surv and np.isfinite(surv.get("Sharpe", np.nan)) and surv["Sharpe"] > 0
              and surv.get("월평균", 0) > 0)
    _rec("R7", "비용 차감 후 생존", ok,
         f"기본 시나리오 Sharpe {surv.get('Sharpe', float('nan')):.3f}, "
         f"월평균 {surv.get('월평균', float('nan'))*100:+.3f}%p" if surv else "산출 실패")


def R8_leakage(V: "pd.DataFrame", S_builder: Callable, run_fn: Callable) -> None:
    """확장창 vs 전기간 — 전기간이 유의하게 좋다면 그 초과분이 곧 누수량이다."""
    if V is None or V.empty or "VAS_fullsample" not in V.columns:
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None, "전기간 VAS 가 없습니다")
        return
    both = V[["VAS", "VAS_fullsample"]].dropna()
    if len(both) < 100:
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None, "비교 표본 부족")
        return
    corr = float(both["VAS"].corr(both["VAS_fullsample"]))
    try:
        bt_e = run_fn(vas_col="VAS", label="R8_expanding")
        bt_f = run_fn(vas_col="VAS_fullsample", label="R8_full")
        se = perf_stats(bt_e["returns"]).get("Sharpe", np.nan)
        sf = perf_stats(bt_f["returns"]).get("Sharpe", np.nan)
        a = bt_e["returns"]["ret"].fillna(0).to_numpy()
        b = bt_f["returns"]["ret"].fillna(0).to_numpy()
        k = min(len(a), len(b))
        mu, t = hac_tstat(b[:k] - a[:k])
    except Exception as e:                                     # noqa
        _rec("R8", "누수 민감도 (확장창 vs 전기간)", None,
             f"비교 백테스트 실패({type(e).__name__})")
        return
    leaked = bool(np.isfinite(t) and t > 2.0)
    _rec("R8", "누수 민감도 (확장창 vs 전기간)", (not leaked),
         f"신호 상관 {corr:.4f} · Sharpe 확장창 {se:.3f} vs 전기간 {sf:.3f} · "
         f"월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). " +
         ("★ 전기간 회귀가 유의하게 좋습니다 — 그 초과분이 곧 미래누수량입니다. "
          "생산 경로는 확장창이므로 보고 성과는 안전합니다." if leaked else
          "전기간 회귀가 유의한 우위를 보이지 않습니다 — 통제회귀 경로에 큰 누수가 "
          "없다는 뜻입니다."),
         metrics={"corr": corr, "sharpe_expanding": se, "sharpe_full": sf, "t_diff": t})


def R9_regime(bt: dict, bench: Dict[str, "pd.Series"]) -> None:
    R = bt["returns"].set_index("month")["ret"]
    rows = []
    ks = bench.get("KOSPI")
    if ks is not None and len(ks):
        up = pd.Series(ks).reindex(R.index) > 0
        for lab, msk in (("강세(코스피↑)", up), ("약세(코스피↓)", ~up)):
            x = R[msk.fillna(False)]
            if len(x) >= 6:
                rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                             f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    half = len(R) // 2
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        if len(x) >= 6:
            rows.append([lab, f"{len(x)}", f"{x.mean()*100:+.3f}%p",
                         f"{x.std()*math.sqrt(12)*100:.1f}%", f"{(x>0).mean()*100:.0f}%"])
    LOG.table(rows, ["레짐", "월수", "월평균", "연변동성", "승률"], ["l", "r", "r", "r", "r"],
              title="R9 레짐 분할")
    Y = bt["returns"].copy()
    Y["year"] = Y["month"].dt.year
    yrows = []
    for y, g in Y.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        yrows.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%", f"{g['ret'].mean()*100:+.3f}%p",
                      f"{(g['ret']>0).mean()*100:.0f}%", f"{g['n'].mean():.1f}",
                      f"{g['cash'].mean()*100:.0f}%"])
    LOG.table(yrows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목수", "평균현금"],
              ["c", "r", "r", "r", "r", "r", "r"], title="R9 연도별 분해")
    yv = [float(r[2].rstrip("%")) for r in yrows]
    pos = sum(1 for v in yv if v > 0)
    _rec("R9", "레짐·하위기간 안정성", True,
         f"{pos}/{len(yv)}개 연도 양(+) · 최악 {min(yv):+.1f}% / 최고 {max(yv):+.1f}%")


def R10_vs_naive(bt_aar: dict, bt_naive: dict) -> None:
    """★ 이 시스템의 존재 이유를 검정한다.

    §6.3 통제회귀·축소추정·인과분해를 다 하고도 '단순 리포트 건수 증가'를 못 이기면,
    그 복잡도 전체가 불필요하다는 뜻이다. 유리하게 해석하지 않고 그대로 보고한다."""
    if not bt_naive or bt_naive["returns"].empty:
        _rec("R10", "AAR vs 나이브 (통제의 가치)", None, "나이브 백테스트가 없습니다")
        return
    a = bt_aar["returns"]["ret"].fillna(0).to_numpy()
    b = bt_naive["returns"]["ret"].fillna(0).to_numpy()
    k = min(len(a), len(b))
    mu, t = hac_tstat(a[:k] - b[:k])
    sa = perf_stats(bt_aar["returns"]).get("Sharpe", np.nan)
    sb = perf_stats(bt_naive["returns"]).get("Sharpe", np.nan)
    ok = bool(np.isfinite(t) and t > 1.0 and sa > sb)
    _rec("R10", "AAR vs 나이브 (통제의 가치)", ok,
         f"AAR Sharpe {sa:.3f} vs 나이브(단순 건수증가) {sb:.3f} · "
         f"월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). " +
         ("통제회귀·축소추정이 만든 정보가 실재합니다." if ok else
          "★ AAR 이 나이브를 유의하게 이기지 못했습니다. §6.3 통제와 §6.2 축소추정, "
          "§6.5 인과분해가 전부 불필요한 복잡도라는 뜻입니다. 유리하게 해석하지 "
          "않고 그대로 보고합니다."),
         kill=True, metrics={"sharpe_aar": sa, "sharpe_naive": sb, "t": t})


def report_robustness():
    LOG.banner("강건성 검사 요약", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    rows = []
    for rid, r in ROBUST.items():
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid + ("⭐" if r["kill"] else ""), _trunc(r["name"], 26), icon,
                     _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)
    fails = [r for r in ROBUST.values() if r["pass"] is False]
    kills = [r for r in fails if r["kill"]]
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§11 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("모든 강건성 검사 통과.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — 성과검증표 / 격자표 / 해석표 / 유니버스 비교 / 최종판정 / 흐름지도           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PERF_ORDER = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
              "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
              "월평균회전율", "월평균비용", "현금비중"]
PERF_FMT = {"누적수익": "pct", "CAGR": "pct", "연변동성": "pct", "MDD": "pct", "승률": "pct",
            "현금비중": "pct", "월평균": "pctp", "월평균비용": "pctp", "월평균회전율": "num"}


def _fmt(k: str, v) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    f = PERF_FMT.get(k)
    if f == "pct":
        return f"{v*100:+.2f}%"
    if f == "pctp":
        return f"{v*100:+.3f}%p"
    if isinstance(v, float):
        return f"{v:,.3f}"
    return f"{v:,}"


def report_performance(bt: dict, bench: Dict[str, "pd.Series"], title: str = ""):
    LOG.banner(f"성과 검증 — {title or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 월 리밸런싱 · 익영업일 종가 체결 · "
               f"Q5 롱온리 동일가중 · 종목당 상한 {POS_MAX_WEIGHT:.0%}")
    s = perf_stats(bt["returns"])
    if not s:
        LOG.warn("성과를 계산할 수 없습니다 (수익률 시계열이 비었습니다).")
        return
    LOG.table([[k, _fmt(k, s.get(k))] for k in PERF_ORDER], ["지표", "값"], ["l", "r"],
              title="포트폴리오 성과")
    rows = bench_stats(bt["returns"], bench)
    if rows:
        LOG.table(rows, ["벤치마크", "벤치 누적", "전략 누적", "초과", "연환산 초과", "HAC t"],
                  ["l", "r", "r", "r", "r", "r"],
                  title="벤치마크 대비 (§11 ACCEPT 조건: 동일가중 유니버스 대비 연 +3%p 이상)")
    rt = right_tail_contribution(bt)
    if rt:
        LOG.table([[k, f"{v:,.3f}" if isinstance(v, float) else str(v)] for k, v in rt.items()],
                  ["항목", "값"], ["l", "r"],
                  title="우측 꼬리 의존도 — 소수 종목에 성과가 몰려 있는지")
        base, ex = rt.get("총기여"), rt.get("상위5% 제외 후")
        if base and ex is not None and base > 0 and ex <= 0:
            LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. 성과가 소수 종목에 "
                     "전적으로 의존합니다 — 실전에서 그 종목을 놓치면 전략 전체가 실패합니다.")


def report_grid(grid_stats: List[dict]):
    if not grid_stats:
        return
    rows = []
    for g in grid_stats:
        s = g["stats"]
        rows.append([g["label"], g["weight"], f"{g['lam']:g}", f"{g['hold']}M",
                     _fmt("CAGR", s.get("CAGR")), f"{s.get('Sharpe', np.nan):.3f}",
                     _fmt("MDD", s.get("MDD")), _fmt("월평균", s.get("월평균")),
                     f"{s.get('t통계량(HAC)', np.nan):.2f}", f"{s.get('평균종목수', np.nan):.1f}"])
    LOG.table(rows, ["구성", "가중", "λ", "보유", "CAGR", "Sharpe", "MDD", "월평균",
                     "HAC t", "평균종목"],
              ["l", "l", "c", "c", "r", "r", "r", "r", "r", "r"],
              title="§6.6 사전등록 파라미터 격자 12개 전체 결과 "
                    "(최고 성과만 보고하는 것을 막기 위해 전부 출력합니다)")
    sh = [g["stats"].get("Sharpe", np.nan) for g in grid_stats]
    sh = [x for x in sh if np.isfinite(x)]
    if sh:
        LOG.info(f"격자 Sharpe 분포 — 최소 {min(sh):.3f} / 중앙 {np.median(sh):.3f} / "
                 f"최대 {max(sh):.3f}. 최대값만 보고 판단하지 마십시오. "
                 f"DSR 은 이 시행횟수를 반영해 이미 할인되어 있습니다.")


def report_interpretation(S: "pd.DataFrame", V: "pd.DataFrame", drops: "pd.DataFrame"):
    LOG.banner("해석 참조표", "신호가 발화했을 때와 안 했을 때 각각 무슨 뜻인가")
    LOG.table([
        ["AAR_pos > 0", "애널리스트가 기계적 발간 요인을 넘어 **자발적으로** 이 종목에 "
                        "주의를 더 썼다", "검열될 수 없는 양(+) 신호"],
        ["AAR_pos < 0", "주의를 거둬들이는 중 (아직 커버는 유지)", "약한 음의 신호"],
        ["AAR_neg < 0", "직전 4분기 연속 커버하던 애널이 **재직 중인데** 이 종목만 끊었다",
         "한국에서 관측 가능한 사실상 유일한 부정적 정보 경로"],
        ["AAR_neg = 0", "철회 사건 없음 (커버 로스터 유지)", "중립 — 결측이 아니다"],
        ["M-EXIT", "담당자 이직·퇴사로 끊김. **종목에 대한 정보가 아니다**",
         "플라시보군 — 여기서 효과가 나오면 인과분해 실패"],
        ["HANDOFF", "하우스가 계속 커버하고 인원도 불변 (승계)", "철회가 아님 — 가중 0"],
    ], ["신호 상태", "의미", "해석"], ["l", "l", "l"], maxw=52)

    LOG.table([
        ["섹터중립", "SectorMonthFE 를 넣으므로 '반도체로 주의가 몰렸다' 같은 섹터 로테이션은 "
                     "신호에서 **완전히 제거**된다. 설계 의도다."],
        ["3개월 지연", "철회는 '3개월 침묵을 관측한 달'에 발화한다. 마지막 리포트로부터 "
                       "3개월 늦지만 그 시점에 100% 관측 가능하다(선견 없음)."],
        ["의견·목표주가 미사용", "매도의견 부재와 목표주가 상향 편향에 면역이다. "
                                 "목표주가는 H5 선행성 검정에만 쓴다."],
        ["대리변수", "컨센서스 EPS 는 역사적 복원이 불가능해 **목표주가 리비전**으로 대체했다. "
                     "H5 결과는 그 대리변수 대비 선행성으로만 해석해야 한다."],
    ], ["항목", "반드시 함께 읽어야 할 사실"], ["l", "l"], maxw=86,
        title="구조적 한계 — 숨기지 않고 명시합니다")

    if S is not None and len(S):
        q = S.groupby("month", observed=True).agg(
            n=("code", "size"), pos=("aar_pos", "mean"), neg=("aar_neg", "mean"),
            drop=("n_drop", "sum"))
        LOG.table([["신호 보유 종목-월", f"{len(S):,}"],
                   ["월평균 신호 종목수", f"{q['n'].mean():,.0f}"],
                   ["AAR_pos 평균", f"{float(S['aar_pos'].mean()):+.5f}"],
                   ["AAR_neg 평균", f"{float(S['aar_neg'].mean()):+.5f}"],
                   ["AAR_neg < 0 비중", f"{float((S['aar_neg']<0).mean())*100:.1f}%"],
                   ["철회 사건 총계", f"{int(q['drop'].sum()):,}"]],
                  ["항목", "값"], ["l", "r"], title="신호 분포 요약")


def report_universe_compare(results: Dict[str, dict]):
    """§10 — 전체 유니버스 vs 시총 하위 1000 비교."""
    if len(results) < 2:
        return
    LOG.banner("유니버스 변형 비교", "전체 PIT 유니버스 vs 시가총액 하위 1000 압축")
    rows = []
    for name, r in results.items():
        s = r.get("stats", {})
        rows.append([name, f"{s.get('월수', 0):,}", _fmt("CAGR", s.get("CAGR")),
                     f"{s.get('Sharpe', np.nan):.3f}", _fmt("MDD", s.get("MDD")),
                     _fmt("월평균", s.get("월평균")), f"{s.get('t통계량(HAC)', np.nan):.2f}",
                     f"{s.get('평균종목수', np.nan):.1f}",
                     _fmt("월평균회전율", s.get("월평균회전율"))])
    LOG.table(rows, ["유니버스", "월수", "CAGR", "Sharpe", "MDD", "월평균", "HAC t",
                     "평균종목", "회전율"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r"])
    try:
        a = results["FULL"]["bt"]["returns"]["ret"].fillna(0).to_numpy()
        b = results["SMALL1000"]["bt"]["returns"]["ret"].fillna(0).to_numpy()
        k = min(len(a), len(b))
        mu, t = hac_tstat(b[:k] - a[:k])
        LOG.info(f"SMALL1000 − FULL 월수익 차이 {mu*100:+.3f}%p (HAC t={t:.2f}). "
                 + ("소형주 압축이 신호를 강화합니다 — H4(저커버리지·소형주에서 강함) 예측과 "
                    "일치합니다." if mu > 0 else
                    "소형주 압축이 신호를 강화하지 못했습니다 — H4 예측과 어긋납니다."))
    except Exception:
        pass


def final_verdict(results: Dict[str, dict], hyp: "pd.DataFrame") -> str:
    """§11 수용/폐기 기준 — 사전 확정, 사후 변경 금지."""
    LOG.banner("최종 판정 (§11)", "사전 확정 기준 · 사후 변경 없음")

    def _h(hid: str) -> Optional[bool]:
        r = HYPO.get(hid)
        return None if not r else r.get("fdr_pass", r.get("pass"))

    def _r(rid: str) -> Optional[bool]:
        r = ROBUST.get(rid)
        return None if not r else r["pass"]

    main = results.get("FULL") or next(iter(results.values()), {})
    s = main.get("stats", {})
    bench_ok = None
    try:
        ew = main["bench"].get("동일가중유니버스")
        R = main["bt"]["returns"].set_index("month")["ret"].fillna(0)
        bb = pd.Series(ew).reindex(R.index).fillna(0)
        ann_ex = float((1 + (R - bb).mean()) ** 12 - 1)
        bench_ok = ann_ex >= 0.03
    except Exception:
        ann_ex = np.nan

    checks = [
        ("H1 (BH-FDR 후)", _h("H1"), "자발적 주의 증가의 양(+) 예측력"),
        ("H5 (BH-FDR 후)", _h("H5"), "컨센서스 개정 대비 선행성 — 경제적 정당성"),
        ("H2 (BH-FDR 후)", _h("H2"), "기회비용 가중이 비가중보다 강함"),
        ("R5 M-EXIT 플라시보", _r("R5"), "기계적 철회군에서 효과 없음"),
        ("R2 PBO < 0.5", _r("R2"), "과적합 위험"),
        ("R3 DSR > 0", _r("R3"), "시행횟수 보정 후 유의"),
        ("R10 나이브 대비 우위", _r("R10"), "통제·축소·분해의 가치"),
        ("동일가중 대비 연 +3%p", bench_ok, f"실측 연환산 초과 {ann_ex*100:+.2f}%p"),
    ]
    LOG.table([[n, {True: "✔ 충족", False: "✘ 미충족", None: "— 판정불가"}[v], d]
               for n, v, d in checks], ["ACCEPT 조건", "판정", "비고"], ["l", "c", "l"], maxw=56)

    h1 = _h("H1")
    h5 = _h("H5")
    r5 = _r("R5")
    r2 = _r("R2")
    r10 = _r("R10")

    if h1 is False or r2 is False or r5 is False or r10 is False:
        verdict = "KILL"
        why = []
        if h1 is False:
            why.append("H1 기각 — 자발적 주의 증가에 양의 예측력이 없습니다")
        if r2 is False:
            why.append("PBO ≥ 0.5 — 과적합 위험이 높습니다")
        if r5 is False:
            why.append("M-EXIT 플라시보 실패 — 인과분해가 성립하지 않습니다. "
                       "신호는 '커버리지 감소 = 소외주'의 재발견일 수 있습니다")
        if r10 is False:
            why.append("나이브(단순 건수증가) 대비 우위 없음 — 통제회귀·축소추정·인과분해가 "
                       "불필요한 복잡도입니다")
        reason = " / ".join(why)
    elif h1 is True and h5 is False:
        verdict = "CONDITIONAL"
        reason = ("H1 은 통과했으나 H5(선행성)가 실패했습니다. 이 신호는 컨센서스 개정의 "
                  "느린 대리변수일 가능성이 큽니다. §11 에 따라 **독립 배분을 금지**하고 "
                  "기존 개정 팩터와의 상관 분석만 수행하십시오.")
    elif all(v is True for v in (h1, h5, _h("H2"), r5, r2, _r("R3"), r10)) and bench_ok:
        verdict = "ACCEPT"
        reason = "사전 확정된 ACCEPT 조건을 모두 충족했습니다."
    else:
        verdict = "INCONCLUSIVE"
        pend = [n for n, v, _ in checks if v is None]
        reason = ("판정불가 항목이 남아 있어 ACCEPT 도 KILL 도 선언할 수 없습니다: "
                  + ", ".join(pend) + ". 표본 부족을 '통과'로 읽지 않기 위해 "
                  "의도적으로 미판정으로 둡니다.")

    icon = {"ACCEPT": "✔", "CONDITIONAL": "⚠", "KILL": "⛔", "INCONCLUSIVE": "—"}[verdict]
    LOG.banner(f"{icon} 최종 판정: {verdict}", _trunc(reason, 100))
    if len(reason) > 100:
        _safe_print("  " + reason)
    LOG.info("이 판정은 §11 의 사전 확정 기준을 기계적으로 적용한 결과입니다. "
             "기준을 사후에 바꿔 통과시키지 마십시오 — 그것이 이 프로젝트에서 가장 "
             "해로운 행동입니다(§13).")
    return verdict


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────┐
  │  환경감지 → 의존성 → 드라이브 마운트 → VAULT (공용/전용 인덱스, append-only 저널)    │
  │   ├ HTTP 응답 캐시 : 같은 URL+파라미터는 두 번 다시 네트워크에 나가지 않음            │
  │   ├ 메모 캐시      : 입력 지문이 같으면 계산 자체를 건너뜀                            │
  │   └ adopt_scan     : 기존 캐시를 '이동 없이 참조 등록'                                │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │  marcap (연도 parquet 11개)  →  일별 수정수익률 · 월말 단면 · 종목 마스터              │
  │     └ PIT 시총 · 상장주식수 · 실거래대금 · 생존자편향 구조적 제거를 한 번에            │
  │  DART list.json 스윕        →  실적발표월 · 월별 공시건수 (통제변수 2개뿐)             │
  │  한경컨센서스 + 네이버      →  리포트 원장 → 애널리스트 원장 → 인물 추적(이직)         │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼   모든 테이블은 pit_frame() 통과
  ┌── L2 신호 ────────────────────────────────────────────────────────────────────────────┐
  │  주의 패널 (분수배분·합집합채움·셀단위 결측)                                            │
  │      → EA = share − base            (해석적 분산 v 동반)                               │
  │      → 경험적베이즈 축소 (tau² 3단 계층, 자유도 0)          ← 확장창 [t0,t]             │
  │      → §6.3 통제회귀 잔차 = VAS      (섹터×월 FE + 애널 FE)  ← 확장창 [t0,t]             │
  │  커버리지 철회 분류 → V-DROP / H-EXIT / HANDOFF / M-EXIT / CENSORED-*                  │
  │      → AAR_pos (ω 가중 집계)  ·  AAR_neg (−Σw/로스터, 유계)                            │
  │      → AAR_total = z(pos) + λ·z(neg)      ★ 결측은 채우지 않고 유니버스를 제한          │
  └───────────────────────────────────┬───────────────────────────────────────────────────┘
                                      ▼
  ┌── L3 백테스트 → L5 검정 → L6 리포트 ──────────────────────────────────────────────────┐
  │  5분위 → Q5 롱온리 동일가중 → AAR_neg 하위10% 배제 → 하한 20종목                       │
  │  익영업일 종가 체결 · 폐지 승계/전손 분기 · 연도별 거래세                               │
  │  H1~H5 (BH-FDR) → R1 부트스트랩 → R2 PBO → R3 DSR → R4 워크포워드                      │
  │  → R5 M-EXIT 플라시보⭐ → R6 CAR → R7 비용 → R8 누수 → R9 레짐 → R10 나이브⭐          │
  │  × 유니버스 2종 (전체 / 시총하위1000)                                                   │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")


def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f       # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML     # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 — 주석이나 관례는 무효. 테스트로만 강제한다.                                ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ║                                                                                          ║
# ║  여기 있는 검사는 전부 **실제로 겪었거나 실측으로 재현된 실패**를 고정한 것이다.           ║
# ║  "그럴 리 없다"고 생각되는 항목일수록 과거에 조용히 틀렸던 것이다.                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACTS.append({"id": cid, "name": name, "pass": bool(ok), "msg": msg})
    return ok


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACTS.clear()
    rng = np.random.default_rng(SEED)

    # ── PIT 강제 ──────────────────────────────────────────────────────────────────────
    def c_pit():
        d = pd.DataFrame({"code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 필터가 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 등록 거부 확인"

    _c("PIT", "Point-In-Time 강제", c_pit)

    # ── 날짜 규약: as_ts 와 as_ts_series 가 같은 값을 낼 것 (KST 벽시계) ────────────────
    def c_tz():
        cases = ["2020-01-15 08:00:00+09:00", "2020-01-15 23:30:00+09:00",
                 "2020-01-15", "2020-01-15 00:00:00+00:00"]
        for s in cases:
            a = as_ts(s)
            b = as_ts_series([s]).iloc[0]
            if a is None or pd.isna(b) or a != b:
                return False, (f"★as_ts({s!r})={a} 인데 as_ts_series 는 {b} 입니다. "
                               f"두 함수가 다른 날짜를 내면 knowledge_date 가 하루 어긋나 "
                               f"PIT 를 정면 위반합니다.")
        if as_ts("2020-01-15 08:00:00+09:00") != as_ts("2020-01-15"):
            return False, ("★KST 09시 이전 시각이 전날로 밀렸습니다. tz_convert(None) 은 "
                           "UTC 변환이라 한국 데이터에 쓰면 안 됩니다.")
        mixed = as_ts_series(["2020-01-15 08:00:00+09:00", "2020-01-16"])
        if mixed.isna().any():
            return False, "타임존이 섞인 열에서 결측이 발생했습니다"
        if str(mixed.dtype) != "datetime64[ns]":
            return False, f"날짜 단위가 ns 가 아닙니다({mixed.dtype}) — merge_asof 가 실패합니다"
        return True, "KST 벽시계 일치 · tz 혼재 흡수 · datetime64[ns] 고정 확인"

    _c("TZ", "날짜 정규화 규약", c_tz)

    # ── A4: 축소추정 — 단조성·경계·자유도 0 ────────────────────────────────────────────
    def c_eb():
        n = 600
        unit = np.repeat([f"u{i}" for i in range(60)], 10)
        Nt = np.tile(np.array([3, 5, 8, 12, 20, 40, 60, 90, 140, 200], dtype=float), 60)
        Nlb = Nt * 12
        rt = rng.binomial(np.maximum(Nt, 1).astype(int), 0.1).astype(float)
        rlb = rng.binomial(np.maximum(Nlb, 1).astype(int), 0.1).astype(float)
        df = pd.DataFrame({"unit_id": unit, "house": np.repeat(["h1", "h2"], n // 2),
                           "sector": np.tile(["s1", "s2", "s3"], n // 3),
                           "r_t": rt, "N_t": Nt, "r_lb": rlb, "N_lb": Nlb})
        df["v"] = ea_analytic_var(df["r_t"], df["N_t"], df["r_lb"], df["N_lb"])
        df["EA"] = df["r_t"] / df["N_t"] - df["r_lb"] / df["N_lb"]
        if not (df["v"] > 0).all():
            return False, "해석적 분산에 비양수가 있습니다"
        sh, w, diag = eb_shrink_tau2(df, "unit_id", "house", "sector", "EA", "v")
        if not ((w >= -1e-9) & (w <= 1 + 1e-9)).all():
            return False, f"신뢰도 w 가 [0,1] 밖입니다: {float(w.min()):.3f}~{float(w.max()):.3f}"
        if not (sh.abs() <= df["EA"].abs() + 1e-9).all():
            return False, "★축소 결과가 원값보다 큽니다 — 0 을 향한 축소가 아닙니다"
        lo = df["N_t"] <= 8
        hi = df["N_t"] >= 90
        if float(w[lo.to_numpy()].mean()) >= float(w[hi.to_numpy()].mean()):
            return False, (f"★단조성 위반: 관측이 적은 쪽(w={float(w[lo.to_numpy()].mean()):.3f})이 "
                           f"많은 쪽(w={float(w[hi.to_numpy()].mean()):.3f})보다 덜 축소되었습니다. "
                           f"관측이 적을수록 사전분포로 강하게 끌어당겨야 합니다(§6.2).")
        return True, (f"w∈[0,1] · |축소값|≤|원값| · 관측수 단조성 확인 "
                      f"(적은쪽 w={float(w[lo.to_numpy()].mean()):.3f} < "
                      f"많은쪽 {float(w[hi.to_numpy()].mean()):.3f})")

    _c("A4", "경험적 베이즈 축소추정", c_eb)

    # ── 고정효과 흡수: 싱글턴 처리 · NaN 오염 방지 · 수렴 ───────────────────────────────
    def c_fe():
        n = 4000
        a = rng.integers(0, 200, n)
        s = rng.integers(0, 150, n)
        x = rng.normal(size=(n, 2))
        y = 1.5 * x[:, 0] - 0.8 * x[:, 1] + rng.normal(0, 0.3, n) \
            + np.bincount(a, minlength=200)[a] * 0.0 + a * 0.001 + s * 0.002
        r, b, kr, kc, info = absorb_2way(y, x, [a, s], [200, 150], strict=False)
        if not info.get("converged", False):
            return False, f"수렴 실패 (iters={info.get('iters')})"
        if b.size < 2 or not np.isfinite(b[:2]).all():
            return False, "계수를 추정하지 못했습니다"
        if abs(b[0] - 1.5) > 0.08 or abs(b[1] + 0.8) > 0.08:
            return False, f"계수 복원 실패: {b[:2]} (기대 [1.5, -0.8])"
        # NaN 오염 — bincount 는 NaN 을 무시하지 않는다
        y2 = y.copy()
        y2[7] = np.nan
        r2, _, kr2, _, info2 = absorb_2way(y2, x, [a, s], [200, 150], strict=False)
        if not np.isfinite(r2).all():
            return False, "★NaN 이 잔차로 전파되었습니다 — 완전관측 마스크가 동작하지 않습니다"
        if kr2[7]:
            return False, "NaN 행이 회귀에 포함되었습니다"
        # 싱글턴 — 잔차가 정확히 0 이 되는 가짜 관측을 만들면 안 된다
        a3 = np.concatenate([a, [999]])
        s3 = np.concatenate([s, [999]])
        y3 = np.concatenate([y, [1.0]])
        x3 = np.vstack([x, [[0.0, 0.0]]])
        _, _, kr3, _, info3 = absorb_2way(y3, x3, [a3, s3], [1000, 1000], strict=False)
        if kr3[-1]:
            return False, ("★싱글턴 셀 행이 회귀에 남았습니다. 그 잔차는 정확히 0 이 되어 "
                           "'주의 이상 없음'이라는 가짜 관측으로 VAS 에 흘러갑니다.")
        return True, (f"계수 복원 정확 · NaN 격리 · 싱글턴 제거 "
                      f"{info3.get('n_singleton_dropped', 0)}행 · 수렴 {info.get('iters')}회")

    _c("FE", "고정효과 흡수 회귀", c_fe)

    # ── A9: 결측 채움 금지 + AAR_neg 배제 규칙이 유니버스를 전멸시키지 않을 것 ──────────
    def c_fill():
        n = 700
        S = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": as_ts("2020-06-30"),
            "aar_pos": rng.normal(0, 0.04, n),
            "n_analyst": rng.integers(2, 8, n),
            "n_drop": 0.0,
        })
        # 90.7% 가 정확히 0 인 점질량 분포 (실제 AAR_neg 분포와 동일 성질)
        neg = np.zeros(n)
        k = int(n * 0.093)
        neg[:k] = -rng.uniform(0.2, 1.5, k)
        rng.shuffle(neg)
        S["aar_neg"] = neg
        S["z_pos"] = xsec_z(S["aar_pos"], S["month"], min_n=5)
        S["z_neg"] = xsec_z(S["aar_neg"], S["month"], min_n=5, k=None)
        S["aar_total"] = S["z_pos"].astype("float64") + 1.0 * S["z_neg"].astype("float64")

        # 순진한 구현: quantile(0.10) → 10분위수가 0.0 이라 전체 배제
        naive_thr = float(S["aar_neg"].quantile(NEG_EXCLUDE_PCT))
        naive_excl = int((S["aar_neg"] <= naive_thr).sum())
        port, info = select_portfolio(S, as_ts("2020-06-30"))
        if naive_excl < n * 0.5:
            return False, "테스트 전제 오류: 순진한 배제가 재앙적이지 않습니다"
        if info["n_excl"] > n * 0.15:
            return False, (f"★배제가 {info['n_excl']}/{n} 종목으로 폭주했습니다. "
                           f"'엄격히 음수' 조건과 rank(method='min') 을 함께 써야 합니다.")
        if not port:
            return False, (f"★포트폴리오가 비었습니다(전액 현금). 순진한 quantile 배제가 "
                           f"{naive_excl}/{n} 를 배제하는 분포에서 무붕괴여야 합니다.")
        if len(port) < PORT_MIN_NAMES:
            return False, f"보유 {len(port)}종목으로 하한 미달"
        # 윈저라이즈 금지 — 최악 사건들이 하나로 붕괴하면 안 된다
        worst = S.nsmallest(5, "aar_neg")["z_neg"].to_numpy()
        if len(np.unique(np.round(worst, 6))) < 3:
            return False, ("★AAR_neg 최악 5건의 z 가 뭉개졌습니다. 윈저라이즈가 이 신호의 "
                           "존재 이유인 극단 철회 사건을 정확히 지웁니다(k=None 이어야 함).")
        return True, (f"순진한 배제 {naive_excl}/{n}(재앙) vs 올바른 배제 {info['n_excl']}/{n} · "
                      f"보유 {len(port)}종목 · 극단 철회 {len(np.unique(np.round(worst,6)))}단계 보존")

    _c("A9", "결측 채움 금지 · 배제 규칙 무붕괴", c_fill)

    # ── A5: 사전등록 격자가 정확히 12개일 것 ───────────────────────────────────────────
    def c_grid():
        g = signal_grid()
        if len(g) != 12:
            return False, f"격자가 {len(g)}개입니다 (12개여야 함)"
        if len(set(x["label"] for x in g)) != 12:
            return False, "격자 라벨에 중복이 있습니다"
        fixed = {"LOOKBACK_M": (LOOKBACK_M, 12), "MIN_REPORTS_MON": (MIN_REPORTS_MON, 3),
                 "MIN_LOOKBACK_N": (MIN_LOOKBACK_N, 12), "NEG_W_VDROP": (NEG_W_VDROP, 1.0),
                 "NEG_W_HEXIT": (NEG_W_HEXIT, 1.5), "COVER_WINDOW_M": (COVER_WINDOW_M, 12),
                 "PORT_QUANTILES": (PORT_QUANTILES, 5), "NEG_EXCLUDE_PCT": (NEG_EXCLUDE_PCT, 0.10),
                 "PORT_MIN_NAMES": (PORT_MIN_NAMES, 20), "POS_MAX_WEIGHT": (POS_MAX_WEIGHT, 0.05)}
        bad = [k for k, (got, want) in fixed.items() if abs(float(got) - float(want)) > 1e-12]
        if bad:
            return False, (f"★사전등록 고정값이 변경되었습니다: {bad}. 이 값들은 명세가 "
                           f"'튜닝 대상이 아니다'라고 명시한 상수입니다.")
        return True, f"격자 12개 · 고정 상수 {len(fixed)}개 전부 명세값 유지"

    _c("A5", "사전등록 파라미터 고정", c_grid)

    # ── A6: BH-FDR 정확성 ──────────────────────────────────────────────────────────────
    def c_fdr():
        p = np.array([0.001, 0.008, 0.039, 0.041, 0.9])
        rej, padj = bh_fdr(p, q=0.10)
        if not (rej[0] and rej[1]):
            return False, f"명백히 유의한 p 가 기각되지 않았습니다: {rej}"
        if rej[4]:
            return False, "p=0.9 가 기각되었습니다"
        if not np.all(np.diff(padj[np.argsort(p)]) >= -1e-12):
            return False, "보정 p 가 단조가 아닙니다"
        rej2, _ = bh_fdr([np.nan, np.nan], q=0.10)
        if rej2.any():
            return False, "전부 결측인 입력에서 기각이 발생했습니다"
        return True, f"BH 절차 정확 · 보정 p 단조 · 결측 안전 (기각 {int(rej.sum())}/5)"

    _c("A6", "BH-FDR 다중검정 보정", c_fdr)

    # ── A1: 커버리지 격자 완전성 — 철회가 데이터에 나타날 것 ───────────────────────────
    def c_drop():
        """세 시나리오를 한 번에 검정한다:
             a0 : b1 소속, 000001 을 4분기 연속 커버하다 중단. 다른 종목은 계속 발간 → V-DROP
             a1 : b1 소속, 000001 을 계속 커버              → 하우스는 살아 있음(H-EXIT 아님)
             a2 : b2 소속, 000001 을 계속 커버              → 시장 커버가 0 이 되지 않음
             a3 : b3 소속, 000001 커버하다 중단 + **전 종목 발간 중단** → M-EXIT
             a4 : b3 소속, 계속 발간 → b3 의 소스 건강 유지 (없으면 a3 의 침묵이
                  '증권사 전체 발간 급감'과 구별되지 않아 CENSORED-SOURCE 로 빠진다.
                  이 가드가 분류보다 먼저 도는 것이 설계 의도다 — §3.4)
        """
        # 48개월 — 사건(26개월째) 이후 검증용 확정지연 12개월의 여유를 확보한다.
        # 짧게 잡으면 우측절단으로 검증용 라벨이 전량 사라지는데, 그건 버그가 아니라
        # 설계된 동작이므로 표본 길이로 해결해야 한다(§7-F12).
        ms = pd.date_range("2018-01-31", periods=48, freq="ME")
        rows = []

        def emit(a, b, code, k, m, tag):
            rows.append({"report_uid": f"{tag}_{a}_{code}_{k}", "analyst_id": a,
                         "broker_legal_id": b, "broker_legal_name": b,
                         "broker_id": b, "broker_name": b,
                         "code": code, "month": m, "pub_date": m, "category": "기업",
                         "target_price": None, "opinion": None})
        for k, m in enumerate(ms):
            if k < 24:
                emit("a0", "b1", "000001", k, m, "x")       # a0 은 24개월째부터 000001 중단
            emit("a0", "b1", "000002", k, m, "o")           # 다른 종목은 계속 → 재직 중
            emit("a1", "b1", "000001", k, m, "x")           # 하우스 잔여 커버
            emit("a2", "b2", "000001", k, m, "x")           # 시장 커버 유지
            if k < 24:
                emit("a3", "b3", "000001", k, m, "x")       # a3 은 24개월째부터 전면 침묵
                emit("a3", "b3", "000003", k, m, "o")
            for j in range(4):                              # a4 가 b3 의 발간량을 유지시킨다
                emit("a4", "b3", "000003", k * 10 + j, m, f"h{j}")
        L = pd.DataFrame(rows)
        aids = ["a0", "a1", "a2", "a3", "a4"]
        A = pd.DataFrame({"analyst_id": aids, "analyst_person_id": aids,
                          "person_unclassified": False})
        codes = ["000001", "000002", "000003"]
        sec = pd.DataFrame({"code": codes, "delisting_date": [pd.NaT] * 3})
        uni = pd.DataFrame([{"code": c, "month": m} for c in codes for m in ms])
        out = classify_coverage_drops(L, A, pd.DatetimeIndex(ms), sec, uni)
        S = out["signal"]
        if S is None or S.empty:
            return False, ("★4분기 연속 커버 후 침묵인데 철회 사건이 하나도 잡히지 "
                           "않았습니다. 커버 격자가 '리포트가 있는 달'만 담고 있으면 "
                           "진짜 철회가 데이터에 절대 나타나지 않습니다.")
        a0 = S[(S["code"] == "000001") & (S["analyst_id"] == "a0")]
        if a0.empty:
            return False, "재직 중 철회(a0)가 탐지되지 않았습니다"
        if set(a0["klass"]) != {"V-DROP"}:
            return False, (f"★a0 은 재직 중(000002 계속 발간)이고 하우스도 살아 있으므로 "
                           f"V-DROP 이어야 하는데 {sorted(set(a0['klass']))} 로 분류됐습니다. "
                           f"M-EXIT 으로 새면 플라시보군이 오염돼 인과분해가 무너집니다.")
        a3 = S[(S["code"] == "000001") & (S["analyst_id"] == "a3")]
        if a3.empty or set(a3["klass"]) != {"M-EXIT"}:
            return False, (f"★a3 은 전 종목 발간을 멈췄으므로 M-EXIT 이어야 하는데 "
                           f"{sorted(set(a3['klass'])) if len(a3) else '미탐지'} 입니다. "
                           f"자발적 철회로 새면 음의 신호가 기계적 사건으로 오염됩니다.")
        if len(out["verify"]) == 0:
            return False, "검증용 라벨이 생성되지 않았습니다"
        return True, (f"V-DROP(재직 중 철회) · M-EXIT(전면 침묵) 정확 분리 · "
                      f"사건 {len(S)}건 · 검증용 {len(out['verify'])}건")

    _c("A1", "커버리지 철회 탐지 · 분류", c_drop)

    # ── 횡단면 통계: winsor 순서 · ±inf 무해화 · k=None ───────────────────────────────
    def c_xsec():
        # ★ 검정해야 할 성질은 'max z 가 작아지는가'가 아니라
        #   **서로 다른 극단값이 하나로 뭉개지는가** 다. 단일 이상치 하나만 두면
        #   윈저라이즈 후 재표준화 때문에 max z 가 거의 그대로라 아무것도 못 잡는다.
        v = pd.Series([0.0] * 40 + [8.0, 9.0, 10.0, 11.0, 12.0])
        cell = pd.Series(["A"] * 45)
        z = xsec_z(v, cell, min_n=5)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        nz_w = len(np.unique(np.round(z.nlargest(5).to_numpy(), 6)))
        zn = xsec_z(v, cell, min_n=5, k=None)
        nz_r = len(np.unique(np.round(zn.nlargest(5).to_numpy(), 6)))
        if nz_w >= nz_r:
            return False, (f"★윈저라이즈가 극단값을 뭉개지 않았습니다 "
                           f"(윈저 {nz_w}단계 vs 원값 {nz_r}단계). 검정 전제가 깨졌습니다.")
        if nz_r < 5:
            return False, (f"★k=None 인데 극단값 5개가 {nz_r}단계로 뭉개졌습니다. "
                           f"AAR_neg 는 이 경로를 쓰므로 최악의 철회 사건이 지워집니다.")
        vi = pd.Series([1.0, 2.0, 3.0, np.inf, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        zi = xsec_z(vi, pd.Series(["A"] * 10), min_n=5)
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, ("★±inf 오염: 셀에 inf 가 하나 있으면 z 가 전부 뭉개집니다. "
                           "해당 셀의 신호가 통째로 소실됩니다.")
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]), min_n=5)
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 으로 처리되지 않았습니다(0으로 채우면 안 됩니다)"
        return True, "winsor→z 순서 · k=None 분기 · ±inf 무해화 · 표본부족 NaN 확인"

    _c("XSEC", "횡단면 통계", c_xsec)

    # ── 결정성 ─────────────────────────────────────────────────────────────────────────
    def c_det():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell, min_n=5)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1], min_n=5).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 순서 무관 결과 동일 확인"

    _c("DET", "결정성", c_det)

    # ── 종목코드 정규화 (2024 영숫자 티커) ─────────────────────────────────────────────
    def c_code():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) 모두 정상"

    _c("CODE", "종목코드 정규화", c_code)

    # ── 수집 파서 회귀 ─────────────────────────────────────────────────────────────────
    def c_parse():
        for raw, exp in (("26.01.19", "2026-01-19"), ("19.12.31", "2019-12-31"),
                         ("24.11.30", "2024-11-30"), ("2020-05-01", "2020-05-01")):
            if parse_kr_date(raw) != exp:
                return False, (f"★날짜 파싱: {raw} → {parse_kr_date(raw)} (기대 {exp}). "
                               f"두 자리 연도를 자동추론에 맡기면 연·일이 뒤바뀝니다.")
        for raw, exp in (("95,000", 95000.0), ("0", None), ("-", None), ("없음", None)):
            if parse_target_price(raw) != exp:
                return False, f"목표주가 파싱: {raw!r} → {parse_target_price(raw)!r}"
        for raw, exp in (("미래에셋대우", "미래에셋증권"), ("하나금융투자", "하나증권"),
                         ("신한금융투자", "신한투자증권"), ("이베스트투자증권", "LS증권"),
                         ("KTB투자증권", "다올투자증권"), ("하이투자증권", "iM증권")):
            if normalize_broker(raw)[1] != exp:
                return False, f"증권사 정규화: {raw} → {normalize_broker(raw)[1]} (기대 {exp})"
        # ★ 법인 식별자는 합병 전후를 **구분해야** 한다 (이직 탐지의 근거)
        if normalize_broker_legal("대우증권")[0] == normalize_broker_legal("미래에셋증권")[0]:
            return False, ("★법인 식별자가 합병 전후를 하나로 뭉갰습니다. 2016년 대우증권→"
                           "미래에셋 이동이 보이지 않게 되어 M-EXIT 이 통째로 사라집니다.")
        if normalize_broker("대우증권")[0] != normalize_broker("미래에셋증권")[0]:
            return False, "정규화 식별자가 합병 전후를 구분했습니다(목표주가 연속성이 끊깁니다)"
        return True, ("YY.MM.DD 연·일 전치 방지 · 목표주가 0/- 결측 · 사명 정규화 · "
                      "법인/정규화 식별자 이원화 확인")

    _c("PARSE", "수집 파서 회귀", c_parse)

    # ── 원장 병합 멱등성 (출력이 다음 실행의 입력이 된다) ───────────────────────────────
    def c_merge():
        sec = pd.DataFrame(columns=["code", "name"])

        def _f(src, rid, tp):
            return pd.DataFrame([{
                "source": src, "src_report_id": rid, "pub_date": "2024-05-02",
                "category": "기업", "title": "삼성전자(005930) 실적 개선",
                "stock_code": "005930", "stock_name": "삼성전자",
                "broker_raw": "미래에셋증권", "analyst_raw": "홍길동",
                "target_price": tp, "opinion": "Buy", "detail_url": None}])

        a, b = _f("hankyung", "h1", 95000.0), _f("naver", "n1", 90000.0)
        cols = sorted(set(a.columns) | set(b.columns))
        m1 = build_report_master(pd.concat([a, b], ignore_index=True)[cols], sec)
        m2 = build_report_master(pd.concat([a, b, m1.reindex(columns=cols)],
                                           ignore_index=True), sec)
        m3 = build_report_master(m1.copy(), sec)
        if not (len(m1) == len(m2) == len(m3) == 1):
            return False, f"소스 간 중복 병합 실패: {len(m1)}/{len(m2)}/{len(m3)}건 (기대 1/1/1)"
        for nm, mm in (("캐시 재투입", m2), ("캐시 전용", m3)):
            for c, why in (("source", "합성 토큰을 원자로 분해하지 않으면 실행마다 문자열이 "
                                      "무한히 길어집니다"),
                           ("report_uid", "PDF 캐시와 애널리스트 연결표가 통째로 끊깁니다")):
                if str(mm[c].iloc[0]) != str(m1[c].iloc[0]):
                    return False, (f"★{nm} 실행에서 {c} 가 {str(m1[c].iloc[0])[:24]!r} → "
                                   f"{str(mm[c].iloc[0])[:24]!r} 로 바뀌었습니다. {why}.")
        if float(m1["target_price"].iloc[0]) != 95000.0:
            return False, f"목표주가 병합이 최대값을 취하지 않았습니다"
        return True, f"병합 멱등 확인 — source={m1['source'].iloc[0]} · report_uid 불변"

    _c("MERGE", "원장 병합 멱등성", c_merge)

    # ── 폐지 처리: 승계 vs 전손 ────────────────────────────────────────────────────────
    def c_delist():
        dl = pd.DataFrame({
            "code": ["000001", "000002", "000003"],
            "delisting_date": pd.to_datetime(["2020-03-31"] * 3),
            "reason": ["상장폐지기준 해당", "합병에 의한 소멸", "기타"],
            "to_symbol": [None, None, "000009"]})
        k = classify_delisting(dl)
        if k.get("000001") != "WIPEOUT":
            return False, f"상장폐지기준 해당이 전손으로 분류되지 않았습니다: {k.get('000001')}"
        if k.get("000002") != "SUCCEED":
            return False, "합병 소멸이 승계로 분류되지 않았습니다(전손 처리 시 하방 편향)"
        if k.get("000003") != "SUCCEED":
            return False, "승계종목(ToSymbol)이 있는데 전손으로 분류되었습니다"
        return True, "전손/승계 분기 확인 — 일괄 처리는 양방향 모두 편향입니다"

    _c("DELIST", "상장폐지 수익률 분기", c_delist)

    # ── 통계 커널: DSR · PBO · TOST 가 극단 입력에서 죽지 않을 것 ──────────────────────
    def c_stats():
        r = np.random.default_rng(1).normal(0.01, 0.05, 120)
        d = deflated_sharpe(r, n_trials=24)
        if not np.isfinite(d.get("dsr", np.nan)):
            return False, f"DSR 산출 실패: {d}"
        if not (0 <= d["dsr"] <= 1):
            return False, f"DSR 이 확률 범위 밖입니다: {d['dsr']}"
        M = np.random.default_rng(2).normal(0.005, 0.05, (120, 12))
        p = pbo_cscv(M, S=8, max_combos=60)
        if not np.isfinite(p.get("pbo", np.nan)) or not (0 <= p["pbo"] <= 1):
            return False, f"PBO 산출 실패: {p}"
        t = tost_equivalence(np.random.default_rng(3).normal(0, 0.01, 60), bound=0.02)
        if t.get("equivalent") is None:
            return False, f"TOST 판정 실패: {t}"
        short = deflated_sharpe(np.array([0.01, 0.02]), n_trials=12)
        if np.isfinite(short.get("dsr", np.nan)):
            return False, "표본 2개인데 DSR 이 산출되었습니다 (판정불가여야 합니다)"
        return True, (f"DSR={d['dsr']:.3f} · PBO={p['pbo']:.3f} · TOST 동작 · "
                      f"표본부족 시 판정불가 반환 확인")

    _c("STATS", "통계 커널", c_stats)

    # ── 결과 ───────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 28), "✔ 통과" if r["pass"] else "✘ 실패",
             _trunc(r["msg"], 78)] for r in CONTRACTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=82,
              title="계약 자동검정 (협상 대상이 아님 — 전부 실측으로 재현된 실패를 고정한 것)")
    failed = [r for r in CONTRACTS if not r["pass"]]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS)}건 전부 통과.")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  합성데이터 엔드투엔드 스모크 — 실데이터를 건드리기 전에 '계산 경로'를 증명한다             ║
# ║                                                                                          ║
# ║  검정하는 것:                                                                             ║
# ║   ① 주의패널 → 축소 → 통제회귀 → VAS → AAR → 백테스트가 예외 없이 끝까지 도는가            ║
# ║   ② **심어둔 신호를 실제로 탐지하는가** (하네스 민감도). 이게 없으면 실데이터에서           ║
# ║      "신호 없음"이 나와도 그게 전략 탓인지 배관 탓인지 구분할 수 없다.                      ║
# ║   ③ 무정보 난수에서는 신호를 만들어내지 않는가 (거짓양성 방어)                              ║
# ║                                                                                          ║
# ║  ★ 격리 원칙: 합성 종목코드는 'ZZ' 로 시작해 **실제 티커 공간과 충돌하지 않는다.**          ║
# ║    과거에 합성 '000001' 이 전역 PIT 에 남아 실데이터를 오염시킨 사고가 있었다.              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SYNTH_PREFIX = "ZZ"


def make_synthetic(n_analyst: int = 150, n_stock: int = 300, n_month: int = 84,
                   signal_strength: float = 0.0, seed: int = SEED
                   ) -> Dict[str, "pd.DataFrame"]:
    """합성 리포트 원장 + 가격 패널. signal_strength>0 이면 '주의 증가 → 다음달 수익'을 심는다.

    ★ 심는 방식이 중요하다. 애널리스트마다 **독립적으로** 무작위 종목을 밀어주면,
      종목 단위로 집계(AAR_pos)하는 순간 커버 애널 수만큼 희석되어 하네스가 탐지할 수
      없는 크기가 된다. 실제 현상도 그렇지 않다 — 좋은 소식은 여러 애널리스트의 주의를
      **동시에** 끈다. 그래서 매월 소수의 '주목 종목'을 뽑고 그 종목을 커버하는
      애널리스트들이 함께 주의를 늘리는 구조로 심는다.
    """
    rng = np.random.default_rng(seed)
    months = pd.date_range("2016-01-31", periods=n_month, freq="ME")
    codes = [f"{SYNTH_PREFIX}{i:04d}" for i in range(n_stock)]
    analysts = [f"AN{i:03d}" for i in range(n_analyst)]
    brokers = [f"BR{i%12:02d}" for i in range(n_analyst)]
    sectors = {c: f"SEC{i % 8}" for i, c in enumerate(codes)}

    # 각 애널리스트는 15~25종목을 커버한다 (명세의 현실적 가정)
    cover = {a: list(rng.choice(codes, size=int(rng.integers(15, 26)), replace=False))
             for a in analysts}
    # 매월 '주목 종목' 집합 — 이것이 심어둔 신호의 원천이다
    hot = {m: set(rng.choice(codes, size=max(4, n_stock // 25), replace=False))
           for m in months} if signal_strength > 0 else {m: set() for m in months}
    rows = []
    rid = 0
    attn: Dict[Tuple[str, Any], int] = {}
    for a, br in zip(analysts, brokers):
        for m in months:
            k = int(rng.poisson(6)) + 2                       # 월 발간량
            picks = list(rng.choice(cover[a], size=min(k, len(cover[a])), replace=True))
            # 커버 중인 주목 종목이 있으면 높은 확률로 주의를 몰아준다
            for c in cover[a]:
                if c in hot[m] and rng.random() < 0.75:
                    picks += [c] * 4
                    attn[(str(c), m)] = attn.get((str(c), m), 0) + 1
            for c in picks:
                rid += 1
                rows.append({"report_uid": f"R{rid:07d}", "analyst_id": a,
                             "broker_id": br, "broker_legal_id": br,
                             "broker_name": br, "broker_legal_name": br,
                             "code": str(c), "month": m, "pub_date": m,
                             "category": "기업",
                             "target_price": float(rng.integers(8000, 90000)),
                             "opinion": "BUY", "link_method": "list_field", "link_conf": 0.98})
            # 산업리포트 (종목 없음) — N(a,t) 분모에 들어가야 한다
            if rng.random() < 0.3:
                rid += 1
                rows.append({"report_uid": f"R{rid:07d}", "analyst_id": a,
                             "broker_id": br, "broker_legal_id": br,
                             "broker_name": br, "broker_legal_name": br,
                             "code": np.nan, "month": m, "pub_date": m,
                             "category": "산업", "target_price": np.nan, "opinion": None,
                             "link_method": "list_field", "link_conf": 0.98})
    L = pd.DataFrame(rows)
    L["analyst_person_id"] = L["analyst_id"]

    # 가격: 랜덤워크 + 심어둔 신호
    prow = []
    for c in codes:
        px = 10000.0
        for m in months:
            r = float(rng.normal(0.005, 0.09))
            if signal_strength > 0 and attn.get((c, m - pd.offsets.MonthEnd(1)), 0) > 0:
                r += signal_strength
            px *= (1 + r)
            prow.append({"code": c, "month": m, "adj_close": px, "exec_px": px,
                         "marcap": px * 1e6 * (1 + (hash(c) % 100) / 20.0),
                         "adv20": 5e8 + (hash(c) % 97) * 1e7,
                         "market": "KOSPI" if (hash(c) % 3) else "KOSDAQ",
                         "signal_date": m, "next_date": m + pd.Timedelta(days=1),
                         "next_close": px, "amount": 5e8, "volume": 1e5,
                         "stocks": 1e6, "dept": "", "name": c, "Close": px})
    P = pd.DataFrame(prow).sort_values(["code", "month"]).reset_index(drop=True)
    g = P.groupby("code", observed=True)
    for k in (1, 2, 3):
        P[f"fwd_ret{k}"] = g["exec_px"].shift(-k) / P["exec_px"] - 1.0
    P["fwd_ret"] = P["fwd_ret1"]

    sec = pd.DataFrame({"code": codes, "name": codes,
                        "sector": [sectors[c] for c in codes],
                        "industry": [sectors[c] for c in codes],
                        "market": "KOSPI", "listing_date": months[0] - pd.Timedelta(days=800),
                        "delisting_date": pd.NaT, "delist_reason": "", "delist_to": None})
    uni = P[["code", "month", "marcap", "market"]].copy()
    uni["size_rank"] = uni.groupby("month", observed=True)["marcap"].rank(method="first")
    uni["size_pct"] = uni.groupby("month", observed=True)["marcap"].rank(pct=True)
    ctrl = pd.DataFrame([{"code": c, "month": m,
                          "earnings_month": 1.0 if m.month in (3, 5, 8, 11) else 0.0,
                          "log_disclosure": float(np.log1p(rng.integers(0, 8)))}
                         for c in codes for m in months])
    return {"links": L, "panel": P, "sec": sec, "uni": uni, "ctrl": ctrl,
            "months": pd.DatetimeIndex(months), "analysts": pd.DataFrame(
                {"analyst_id": analysts, "analyst_person_id": analysts,
                 "person_unclassified": False, "broker_legal_id": brokers,
                 "broker_legal_name": brokers, "name": analysts,
                 "first_seen": months[0], "last_seen": months[-1]})}


def _synth_pipeline(S: Dict[str, "pd.DataFrame"]) -> Tuple["pd.DataFrame", dict]:
    """합성 데이터로 신호까지 만든다 (전역 PIT 를 건드리지 않는다)."""
    months = S["months"]
    P = build_attention_panel(S["links"], months, S["sec"], unit_mode="ANALYST")
    if P.empty:
        return pd.DataFrame(), {}
    P = attach_controls(P, S["ctrl"], S["uni"])
    V, _, _ = compute_vas(P, months)
    pos = build_aar_pos(V, "uw")
    drops = classify_coverage_drops(S["links"], S["analysts"], months, S["sec"], S["uni"])
    neg = build_aar_neg(drops["signal"], S["links"], months)
    sig = assemble_signal(pos, neg, S["uni"], lam=1.0)
    return sig, {"panel": P, "vas": V, "drops": drops}


def run_selftest(full_chain: bool = False) -> bool:
    LOG.banner("합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산 경로와 '신호 탐지 능력'을 증명한다")
    ok_all = True
    t0 = time.time()

    # ── ① 무신호 데이터에서 파이프라인이 도는가 ────────────────────────────────────────
    S0 = make_synthetic(signal_strength=0.0, seed=SEED)
    try:
        sig0, aux0 = _synth_pipeline(S0)
    except Exception as e:                                        # noqa
        LOG.error(f"무신호 합성 파이프라인 실패: {type(e).__name__}: {e}")
        for ln in traceback.format_exc().split("\n")[-10:]:
            _safe_print("   " + ln)
        return False
    if sig0.empty:
        LOG.error("합성 신호가 비었습니다 — 주의패널부터 신호까지의 경로가 끊겨 있습니다.")
        return False
    bt0 = run_backtest(sig0, S0["panel"], S0["months"], S0["sec"], hold=1, label="SMOKE_null")
    s0 = perf_stats(bt0["returns"])

    # ── ② 신호를 심으면 탐지하는가 (하네스 민감도) ────────────────────────────────────
    S1 = make_synthetic(signal_strength=0.05, seed=SEED + 1)
    sig1, aux1 = _synth_pipeline(S1)
    bt1 = run_backtest(sig1, S1["panel"], S1["months"], S1["sec"], hold=1, label="SMOKE_signal")
    s1 = perf_stats(bt1["returns"])

    sp0 = quantile_spread(sig0, S0["panel"], S0["months"], hold=1)
    sp1 = quantile_spread(sig1, S1["panel"], S1["months"], hold=1)
    m0, t0s = hac_tstat(sp0["spread"].to_numpy()) if len(sp0) > 12 else (np.nan, np.nan)
    m1, t1s = hac_tstat(sp1["spread"].to_numpy()) if len(sp1) > 12 else (np.nan, np.nan)

    LOG.table([["합성 리포트", f"{len(S0['links']):,}건"],
               ["주의패널 행수", f"{len(aux0.get('panel', [])):,}"],
               ["VAS 산출", f"{int(aux0['vas']['VAS'].notna().sum()):,}" if aux0 else "—"],
               ["철회 사건", f"{len(aux0['drops']['signal']):,}" if aux0 else "—"],
               ["신호 종목-월", f"{len(sig0):,}"],
               ["── 무신호 ──", ""],
               ["Q5−Q1 스프레드", f"{m0*100:+.3f}%p (t={t0s:.2f})"],
               ["백테스트 Sharpe", f"{s0.get('Sharpe', np.nan):.3f}"],
               ["── 신호 주입(+5%/월) ──", ""],
               ["Q5−Q1 스프레드", f"{m1*100:+.3f}%p (t={t1s:.2f})"],
               ["백테스트 Sharpe", f"{s1.get('Sharpe', np.nan):.3f}"],
               ["평균 보유종목", f"{s1.get('평균종목수', np.nan):.1f}"]],
              ["항목", "값"], ["l", "r"], title="스모크 결과")

    sensitive = bool(np.isfinite(t1s) and np.isfinite(t0s) and (t1s - t0s) > 1.0
                     and m1 > m0)
    if not sensitive:
        LOG.error("★ 하네스 민감도 실패 — 신호를 명시적으로 심었는데도 탐지하지 못했습니다. "
                  "체결 정렬·수익 계산·신호 결합 중 하나가 고장난 것이며, 이 상태에서 "
                  "실데이터를 돌리면 '알파 없음'이 전략 탓인지 배관 탓인지 구분할 수 없습니다.")
        ok_all = False
    else:
        LOG.ok(f"하네스 민감도 확인 — 심어둔 신호에 t 가 {t0s:.2f} → {t1s:.2f} 로 반응합니다. "
               f"이제 실데이터 결과를 신뢰할 근거가 생겼습니다.")

    if np.isfinite(t0s) and abs(t0s) > 2.5:
        LOG.warn(f"무신호 데이터에서 t={t0s:.2f} 가 나왔습니다 — 거짓양성 가능성이 있습니다. "
                 f"우연일 수 있으나(시드 1개) 실데이터 결과를 그만큼 할인해 읽으십시오.")

    # ── ③ 전역 상태 오염 검사 ─────────────────────────────────────────────────────────
    leaked = [n for n in PIT.names() if not PIT._meta.get(n, {}).get("empty", True)]
    if leaked:
        LOG.warn(f"스모크 후 전역 PIT 에 테이블이 남아 있습니다: {leaked}. "
                 f"합성 코드는 'ZZ' 접두라 실제 티커와 충돌하지 않지만, "
                 f"등록 자체를 하지 않는 것이 원칙입니다.")
    LOG.ok(f"스모크 완료 {time.time()-t0:.1f}s — "
           f"{'전부 통과' if ok_all else '★ 민감도 검정 실패'}")
    return ok_all



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 리포트 원장은 백테스트 시작보다 **42개월 앞서** 있어야 한다:
#   12개월 룩백(base) + 24개월 확장창 버인 + 여유 6개월.
# 이걸 빼면 신호 개시가 1년 이상 밀려 백테스트 앞부분이 통째로 빈다.
RESEARCH_LEAD_M = 42
OUTPUTS: Dict[str, str] = {}


def _months() -> "pd.DatetimeIndex":
    return month_range(BACKTEST_START, BACKTEST_END)


def collect_all(months: "pd.DatetimeIndex") -> dict:
    ctx: Dict[str, Any] = {}
    res_start = (as_ts(BACKTEST_START) - pd.DateOffset(months=RESEARCH_LEAD_M)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.MKT", "시장 데이터 (marcap 연도 parquet)", "L1", budget_s=1800):
        y0 = as_ts(res_start).year
        y1 = as_ts(BACKTEST_END).year
        md = build_market_data(y0, y1)
        ctx.update(daily=md["daily"], monthly=md["monthly"], sec=md["sec"])
        LOG.info(f"※ 종목당 HTTP 수천 건 대신 **연도 parquet {y1-y0+1}개**로 전 종목·전 기간을 "
                 f"받았습니다. 두 번째 실행부터는 HTTP 캐시 적중으로 네트워크 0회입니다.")

    with PIPE.stage("L1.UNI", "PIT 유니버스 · 시가총액", "L1", budget_s=600):
        ctx["uni_all"] = build_pit_universe(ctx["monthly"], months)
        ctx["panel"] = build_price_panel(ctx["monthly"], months, max_hold=max(GRID_HOLD))
        ctx["panel"] = apply_delisting_returns(ctx["panel"], ctx["sec"], max_hold=max(GRID_HOLD))
        ctx["universe"] = Universe(ctx["uni_all"], ctx["sec"])
        for m in months:
            ctx["universe"].audit_row("PIT유니버스", m,
                                      ctx["uni_all"].loc[ctx["uni_all"]["month"] == m, "code"])
            ctx["universe"].audit_row("시즈닝통과", m, ctx["universe"].at(m))

    with PIPE.stage("L1.DART", "실적발표월 · 공시건수 (통제변수)", "L1",
                    budget_s=2400, critical=False):
        fetch_dart_corpcode()
        dis = fetch_dart_disclosures(res_start, BACKTEST_END)
        codes = sorted(set(as_str_series(ctx["uni_all"]["code"])))
        ctrl, meta = build_control_panel(
            pd.DatetimeIndex(sorted(set(months) | set(
                month_range(res_start, BACKTEST_END)))), dis, codes)
        ctx["ctrl"], ctx["ctrl_meta"] = ctrl, meta
        LOG.table([[k, str(v)] for k, v in meta.items()], ["통제변수 메타", "값"], ["l", "l"],
                  title="§6.3 통제변수 출처 (실측인지 달력 대리인지 숨기지 않습니다)")
        if DART_API_KEY:
            quota("DART", key=DART_API_KEY).report()

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장", "L1",
                    budget_s=5400, critical=False):
        raw = collect_reports(res_start, BACKTEST_END)
        rep = build_report_master(raw, ctx["sec"])
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    return ctx


def build_signals(ctx: dict, months: "pd.DatetimeIndex") -> dict:
    L, A, sec = ctx.get("links"), ctx.get("analysts"), ctx["sec"]
    mode = ctx.get("phase0", {}).get("mode", "ANALYST")

    with PIPE.stage("L2.ATTN", "주의 패널 → 축소추정 → 통제회귀 → VAS", "L2", budget_s=2100):
        fp = fingerprint_of("vas", mode, LOOKBACK_M, MIN_REPORTS_MON, MIN_LOOKBACK_N,
                            CTRL_MIN_TRAIN_M, BACKTEST_START, BACKTEST_END, "v3",
                            frames=[L, ctx.get("ctrl")])

        def _mk():
            P = build_attention_panel(L, months, sec, unit_mode=mode)
            if P.empty:
                return P
            P = attach_controls(P, ctx.get("ctrl"), ctx["uni_all"])
            V, sd, rd = compute_vas(P, months)
            ctx["shrink_diag"], ctx["reg_diag"] = sd, rd
            return V

        V = VAULT.memo_table("attention_panel", fp, _mk, scope="private", domain="features",
                             note="주의패널+VAS")
        for c in ("month",):
            if c in V.columns:
                V[c] = as_ts_series(V[c])
        ctx["vas"] = V
        if len(V):
            VAULT.put_table(f"attention_panel_{STRATEGY_ID}", V, scope="private",
                            domain="features", source="L2")

    with PIPE.stage("L2.DROPS", "커버리지 철회 인과분해", "L2", budget_s=900):
        fp = fingerprint_of("drops", W_SIG, D_VER, LAM_MIN, COVER_WINDOW_M, "v3",
                            frames=[L, A])

        def _mkd():
            d = classify_coverage_drops(L, A, months, sec, ctx["uni_all"])
            ctx["_drops_all"] = d
            return d["signal"]

        drops = VAULT.memo_table("drop_events", fp, _mkd, scope="private", domain="features",
                                 note="철회 분류")
        for c in ("month", "last_report_month", "event_date", "knowledge_date"):
            if c in drops.columns:
                drops[c] = as_ts_series(drops[c])
        ctx["drops"] = drops
        if len(drops):
            VAULT.put_table(f"coverage_exit_{STRATEGY_ID}", drops, scope="private",
                            domain="features", source="L2")
        ctx["aar_neg"] = build_aar_neg(drops, L, months)

    with PIPE.stage("L2.SIG", "AAR_pos 가중 3종 · 신호 조립", "L2", budget_s=600):
        ctx["pos_by_w"] = {w: build_aar_pos(ctx["vas"], w) for w in GRID_WEIGHTS}
        ctx["naive"] = build_naive_signal(L, months, ctx["uni_all"])
    return ctx


def run_universe(ctx: dict, months: "pd.DatetimeIndex", variant: str) -> dict:
    """한 유니버스 변형에 대해 격자 12개 백테스트 + 성과 + 검정 + 강건성."""
    LOG.banner(f"유니버스 변형: {variant}",
               "PIT 전체 상장 유니버스" if variant == "FULL"
               else f"시가총액 하위 {SMALLCAP_N:,} 압축 (기존 전략 대비 비교용)")
    uni = apply_universe_variant(ctx["uni_all"], variant)
    key = set(zip(as_str_series(uni["code"]), uni["month"]))
    panel = ctx["panel"][[(c, m) in key for c, m in
                          zip(as_str_series(ctx["panel"]["code"]), ctx["panel"]["month"])]].copy()

    sig_by_w: Dict[str, "pd.DataFrame"] = {}
    grid_stats, grid_ret = [], {}
    for g in signal_grid():
        S = assemble_signal(ctx["pos_by_w"][g["weight"]], ctx["aar_neg"], uni, lam=g["lam"])
        if g["lam"] == GRID_LAMBDA[-1] and g["hold"] == GRID_HOLD[0]:
            sig_by_w[g["weight"]] = S
        if S.empty:
            continue
        bt = run_backtest(S, panel, months, ctx["sec"], hold=g["hold"], cost_mult=1.0,
                          label=g["label"], uni_obj=(ctx["universe"] if g["label"].endswith("1M")
                                                     and g["weight"] == GRID_WEIGHTS[0] else None))
        st = perf_stats(bt["returns"])
        grid_stats.append({**g, "stats": st, "bt": bt, "S": S})
        grid_ret[g["label"]] = bt["returns"].set_index("month")["ret"]
    if not grid_stats:
        LOG.error(f"[{variant}] 어떤 구성에서도 백테스트를 만들지 못했습니다.")
        return {}
    report_grid(grid_stats)
    GR = pd.DataFrame(grid_ret).reindex(months).fillna(0.0)

    # 헤드라인 구성: 사전등록상 기본값 = 비가중 · λ=1.0 · 1개월 (최고 성과를 고르지 않는다)
    head = next((g for g in grid_stats
                 if g["weight"] == "uw" and g["lam"] == 1.0 and g["hold"] == 1), grid_stats[0])
    LOG.info(f"헤드라인 구성 = {head['label']} — **사전에 정한 기본 구성**입니다. "
             f"격자 12개 중 최고 성과를 골라 보고하지 않습니다(그것이 곧 사후선택입니다).")
    bt = head["bt"]
    S = head["S"]

    bench, daily_mkt = benchmark_series(months, ctx["daily"], uni, panel)
    report_performance(bt, bench, title=f"{STRATEGY_NAME} [{variant}]")
    if variant == "FULL":
        ctx["universe"].report_attrition()

    # 나이브 벤치마크 백테스트 (§8 — 통제의 가치를 보여주는 진짜 비교 대상)
    nv = ctx["naive"]
    nv = nv[[(c, m) in key for c, m in zip(as_str_series(nv["code"]), nv["month"])]] if len(nv) else nv
    bt_naive = run_backtest(nv, panel, months, ctx["sec"], hold=1, label="naive") \
        if len(nv) else {"returns": pd.DataFrame()}

    # ★ 비필수 스테이지가 실패해도 아래 return 이 살아 있어야 한다. 스테이지 안에서만
    #   대입되는 변수를 그대로 반환하면 UnboundLocalError 로 그 유니버스 전체가 날아간다.
    hyp: "pd.DataFrame" = pd.DataFrame()
    with PIPE.stage(f"L5.HYPO.{variant}", f"가설 검정 H1~H5 [{variant}]", "L5",
                    budget_s=900, critical=False):
        HYPO.clear()
        test_H1(S, panel, months)
        test_H2(sig_by_w, panel, months)
        test_H3(ctx["drops"], panel, months)
        test_H4(S, panel, uni, months)
        rev = build_consensus_revision(ctx.get("links"), months)
        test_H5(ctx["vas"], rev, months)
        hyp = finalize_hypotheses()

    with PIPE.stage(f"L5.ROBUST.{variant}", f"강건성 검사 [{variant}]", "L5",
                    budget_s=1500, critical=False):
        ROBUST.clear()
        try:
            R1_bootstrap(bt)
            R2_pbo(GR)
            R3_dsr(bt, GR)
            R4_walkforward(GR, months)
            R5_mexit_placebo(ctx["drops"], panel, months)
            ctx[f"car_{variant}"] = R6_event_study(ctx["drops"], ctx["daily"], daily_mkt)
            R7_cost_sensitivity(
                lambda cost_mult=1.0, label="": run_backtest(
                    S, panel, months, ctx["sec"], hold=head["hold"],
                    cost_mult=cost_mult, label=label), COST_SCENARIOS)
            R8_leakage(ctx["vas"], None,
                       lambda vas_col="VAS", label="": run_backtest(
                           assemble_signal(build_aar_pos(
                               ctx["vas"].assign(VAS=ctx["vas"][vas_col]), head["weight"]),
                               ctx["aar_neg"], uni, lam=head["lam"]),
                           panel, months, ctx["sec"], hold=head["hold"], label=label))
            R9_regime(bt, bench)
            R10_vs_naive(bt, bt_naive)
        except KillCriteria as e:
            LOG.error(f"킬 기준으로 강건성 스위트를 중단합니다: {e}")
        report_robustness()

    report_interpretation(S, ctx["vas"], ctx["drops"])
    return {"variant": variant, "bt": bt, "stats": perf_stats(bt["returns"]), "bench": bench,
            "grid": grid_stats, "grid_returns": GR, "signal": S, "hyp": hyp,
            "robust": dict(ROBUST), "hypo": dict(HYPO), "naive": bt_naive}


def _persist(ctx: dict, results: Dict[str, dict], verdict: str) -> List[str]:
    outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
    os.makedirs(outdir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    outs: List[str] = []

    def _save(name: str, df: "pd.DataFrame"):
        if df is None or not len(df):
            return
        p = os.path.join(outdir, f"{name}_{stamp}.csv")
        try:
            df.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
        except Exception as e:                                    # noqa
            LOG.warn(f"{name} 저장 실패({type(e).__name__})")

    for v, r in results.items():
        _save(f"returns_{v}", r["bt"]["returns"])
        _save(f"holdings_{v}", r["bt"].get("holdings", pd.DataFrame()))
        _save(f"metrics_all_configs_{v}",
              pd.DataFrame([{**{k: g[k] for k in ("label", "weight", "lam", "hold")},
                             **g["stats"]} for g in r["grid"]]))
        if len(r.get("hyp", pd.DataFrame())):
            _save(f"hypothesis_{v}", r["hyp"])
        VAULT.put_table(f"backtest_returns_{v}_{STRATEGY_ID}", r["bt"]["returns"],
                        scope="private", domain="backtest", source=STRATEGY_ID)
        if len(ctx.get(f"car_{v}", pd.DataFrame())):
            _save(f"event_study_car_{v}", ctx[f"car_{v}"])
    _save("coverage_exit_classification", ctx.get("drops", pd.DataFrame()))
    if len(ctx.get("vas", pd.DataFrame())):
        _save("attention_panel_sample", ctx["vas"].head(200000))

    summary = {
        "strategy": STRATEGY_ID, "build": BUILD_VERSION,
        "run_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "backtest": [BACKTEST_START, BACKTEST_END],
        "run_mode": RUN_MODE, "verdict": verdict,
        "phase0": ctx.get("phase0", {}),
        "control_meta": ctx.get("ctrl_meta", {}),
        "variants": {v: {"stats": {k: (float(x) if isinstance(x, (int, float, np.floating))
                                       and np.isfinite(x) else None)
                                   for k, x in r["stats"].items()},
                         "hypotheses": {k: {"pass": h.get("pass"), "fdr_pass": h.get("fdr_pass"),
                                            "p": (float(h["p"]) if np.isfinite(h["p"]) else None)}
                                        for k, h in r["hypo"].items()},
                         "robust": {k: {"pass": x["pass"], "kill": x["kill"]}
                                    for k, x in r["robust"].items()}}
                     for v, r in results.items()},
    }
    sp = os.path.join(outdir, f"run_summary_{stamp}.json")
    atomic_write_text(sp, json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    outs.append(sp)
    lp = os.path.join(outdir, f"log_{stamp}.txt")
    atomic_write_text(lp, "\n".join(LOG.buffer))
    outs.append(lp)
    return outs


def main() -> dict:
    t_all = time.time()
    global VAULT
    LOG.banner(f"ARC-AAR — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START}~{BACKTEST_END} · 유니버스 "
               f"{'/'.join(UNIVERSE_VARIANTS)} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬 / pandas / numpy", f"{ENV['python']} / {pd.__version__} / {np.__version__}"],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["KRX", "비활성 (계정 차단 — marcap 이 전 기능을 대체)"],
               ["전면 캐시", f"HTTP {'ON' if HTTP_CACHE_ENABLED else 'OFF'} · "
                             f"메모 {'ON' if MEMO_ENABLED else 'OFF'}"],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        fg = free_gb(VAULT.root)
        if np.isfinite(fg):
            LOG.info(f"여유 공간 {fg:.1f} GB")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise KillCriteria(
                "스모크 테스트 실패 — 하네스가 심어둔 신호를 탐지하지 못했습니다. "
                "이 상태로 실데이터를 돌리면 '알파 없음'이 전략 탓인지 배관 탓인지 "
                "구분할 수 없으므로 수집을 시작하지 않습니다.")

    months = _months()
    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 계산 경로를 검증했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_all(months)

    with PIPE.stage("L1.PHASE0", "Phase 0 데이터 실현가능성 게이트", "L1", budget_s=300):
        ctx["phase0"] = phase0_gate(ctx.get("reports"), ctx.get("links")) \
            if PHASE0_ENABLED else {"mode": "ANALYST", "rate": np.nan, "note": "게이트 비활성"}
        if PHASE0_HALT_ON_FAIL and ctx["phase0"].get("mode") == "HOUSE":
            raise KillCriteria("Phase 0 게이트 — 애널리스트 식별률이 40% 미만입니다. "
                               "§12-1 에 따라 보고 후 중단합니다(PHASE0_HALT_ON_FAIL=False 로 "
                               "두면 하우스 단위 폴백으로 자동 진행합니다).")

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사", "L1", budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    ctx = build_signals(ctx, months)

    results: Dict[str, dict] = {}
    for variant in UNIVERSE_VARIANTS:
        with PIPE.stage(f"L3.BT.{variant}", f"백테스트·검정 [{variant}]", "L3", budget_s=2400,
                        critical=False):
            r = run_universe(ctx, months, variant)
            if r:
                results[variant] = r

    if not results:
        raise RuntimeError("어떤 유니버스에서도 결과를 만들지 못했습니다. "
                           "위 FLOW 원장에서 어느 단계가 0행을 냈는지 확인하세요.")

    with PIPE.stage("L6.REPORT", "비교표 · 해석 · 최종판정", "L6", budget_s=300, critical=False):
        report_universe_compare(results)
        main_hyp = results.get("FULL", next(iter(results.values()))).get("hyp", pd.DataFrame())
        HYPO.clear()
        HYPO.update(results.get("FULL", next(iter(results.values()))).get("hypo", {}))
        ROBUST.clear()
        ROBUST.update(results.get("FULL", next(iter(results.values()))).get("robust", {}))
        verdict = final_verdict(results, main_hyp)
        ctx["verdict"] = verdict

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outs = _persist(ctx, results, ctx.get("verdict", "INCONCLUSIVE"))
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        for q in QUOTA.values():
            q.close()
        VAULT.report()
        ctx["outputs"] = outs

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    PIPE.report_runtime()
    report_dataflow_map()

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    LOG.info("한계 명시 — ① 컨센서스 EPS 는 역사적 복원이 불가능해 목표주가 리비전으로 "
             "대체했습니다(H5 는 그 대리변수 대비 선행성입니다). ② 금융투자협회 전문인력 "
             "조회는 접근 불가라 인사이동 판정은 '동일 애널이 다른 종목은 계속 커버하는가' "
             "프록시로 대체했습니다. ③ 산업분류는 현재 시점 분류를 씁니다. "
             "④ 이 전략은 선행 문헌이 존재하는 아이디어의 한국시장 조작화이지 "
             "새로운 학술적 발견이 아닙니다.")
    offer_download(ctx.get("outputs", []))
    return {"ctx": ctx, "results": results}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§11 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
        try:
            report_robustness()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 캐시에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
