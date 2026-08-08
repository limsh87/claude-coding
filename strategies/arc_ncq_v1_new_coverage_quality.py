
# ============================================================================================
# 조립 블록 00: ncq_00_header.py
# ============================================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  ARC-NCQ v1.0 — New Coverage × Qualitative Shift
#  소형주 「신규 애널리스트 커버리지 × 보고서 텍스트 질적 변화」 탐지 전략
#  백테스트 구간: 2016-08 ~ 2026-07 (10년)   빌드: ncq1.20260808.0218
#
#  ── 핵심 가설 ───────────────────────────────────────────────────────────────────────────
#   시총 하위권 소형주에 **처음으로 리서치 보고서가 붙는 순간**은, 커버리지를 정당화할 사건
#   (사업구조 전환·대형 수주·신규 라인 양산·전방시장 진입)이 이미 일어났다는 신호다.
#   그러나 스몰캡 리포트의 상당수는 실질 변화 없는 홍보성 보고서다. 그래서 두 단계로 압축한다:
#     ① 신규 커버리지 이벤트  = 1차 필터 (수만 건 → 수천 건)
#     ② 보고서 본문의 '구조적 성장' 밀도를 **같은 달 이벤트 풀 안에서 상대비교** = 2차 압축
#   → 동일 유니버스 동일가중(Bottom-N EW) 대비 12개월 초과수익이 나는가.
#
#  ── 이 파일 하나로 끝납니다 ─────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python arc_ncq_v1.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정 N1~N11
#     [1] 합성데이터 엔드투엔드 스모크 → 실경로 리허설 → 네트워크 카나리 C1~C7
#     [2] Phase 0  PIT 월간 유니버스 (시총 하위 N + 유동성)
#     [3] Phase 1  리포트 인덱스 전수 수집 → 원장 병합 → 커버리지 완결성 진단
#     [4] Phase 2  신규 커버리지 판정 (H1 de novo / H2 broker-new) + 스폰서 분리
#     [5] Phase 3  이벤트 한정 PDF 본문 수집·섹션 추출
#     [6] Phase 4  동결 렉시콘 텍스트 스코어링 → Phase 5 횡단면 z → 상위 tercile
#     [7] Phase 6  12개월 오버랩 코호트 백테스트
#     [8] 성과 검증 → 사전등록 검정 P1~P4(BH-FDR) → 강건성 스위트 → 민감도 9조합
#     [9] 해석표 · 진단 9종 · run_manifest.json · HTML 리포트 · 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
#  ⚠ 렉시콘(config/lexicon_v1.json)은 **수익률을 본 뒤에 수정하면 전 결과가 무효**입니다(§12 R5).
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 —— 여기만 채우면 됩니다 (아래 "설정 끝" 줄까지)
#
#   ▸ 전부 비워둬도 실행됩니다. 키가 없는 데이터원은 자동으로 건너뛰고,
#     "왜 건너뛰었는지"를 한글로 로그에 남깁니다. 조용히 실패하지 않습니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① KRX 데이터 마켓플레이스 —— ⚠ 현재 기본 비활성 (IP 차단 이력) ─────────────────────────
#    가입: https://data.krx.co.kr  →  우측 상단 [회원가입] (무료, 이메일 인증 즉시 완료)
#          가입 후 아래 ID / 비밀번호를 넣고 NCQ_USE_KRX = True 로 바꾸면 사용합니다.
#
#    ★★ 중요 ★★  이 코드는 **KRX 없이도 PIT 유니버스와 생존자편향 제거가 완결되도록**
#       설계되어 있습니다. KRX(data.krx.co.kr / pykrx / kind.krx.co.kr)가 차단되어도
#       아래 KRX-free 3중 경로로 동일한 결과를 만듭니다:
#
#         ① 상장/폐지 명단  : FinanceDataReader GitHub 캐시(raw.githubusercontent.com)
#                             — KRX 서버를 전혀 거치지 않는 정적 CSV
#         ② 상장주식수 이력 : DART OpenAPI 주식총수현황(stockTotqySttus, opendart.fss.or.kr)
#                             — 접수일자(rcept_no) 기준 **진짜 PIT** 주식수. KRX 무관
#         ③ 상장구간 실측   : 네이버 차트 일봉의 '첫 거래일 / 마지막 거래일'로 상장·폐지 구간을
#                             데이터에서 직접 복원 — 명단이 없어도 생존자편향을 막는 최후 방어선
#
#       시가총액 = (②의 PIT 주식수) × (③의 그 시점 수정종가) 로 계산합니다.
#       KRX 를 켜면 월말 스냅샷으로 ②③을 '검증·보강'할 뿐, 의존하지는 않습니다.
#
#    ⚠ 차단 회피 수칙: 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인하지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패하고, 반복되면 IP 차단으로 이어집니다.
NCQ_USE_KRX = False          # ← 차단이 풀렸고 아래 ID/PW 를 넣었을 때만 True 로 바꾸세요
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

#    (선택) KRX Open API 인증키. https://data.krx.co.kr > OPEN API > 인증키 신청.
#    ⚠ 키만으론 즉시 안 됩니다. 엔드포인트별 '이용신청'이 따로 필요하고 승인에 하루쯤 걸립니다.
KRX_OPENAPI_KEY = ""

# ── ② 한경컨센서스 (3차 소스 · 선택) ────────────────────────────────────────────────────────
#    발급: https://consensus.hankyung.com  →  회원가입(무료)
#    ▶ 비워두면 한경 소스는 자동 스킵되고 전략은 정상 동작합니다(명세 §2.1 — 한경 없이 성립).
#      한경은 리스트에 '작성자(애널리스트)'와 '적정가격'을 직접 주는 유일한 소스라, 있으면
#      애널리스트 원장 품질이 크게 올라갑니다. 없으면 broker_id 단위 판정만 사용합니다.
HANKYUNG_ID = ""
HANKYUNG_PW = ""

# ── ③ DART 전자공시 OpenAPI ★KRX 차단 상황의 핵심 대체 경로 ─────────────────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 → [인증키 신청/관리] → 즉시 발급(무료, 즉시)
#    일 20,000건 제한. 코드가 자동 스로틀합니다.
#
#    ▶ KRX 가 막힌 지금 이 키의 역할이 큽니다:
#        · corpCode.xml         → 상장/비상장 전 법인 ↔ 종목코드 (종목명·사명변경 보강)
#        · stockTotqySttus      → **상장주식수 이력(접수일자 기준 PIT)** = 시가총액의 분모
#      비워두면 시가총액이 '현재 주식수 × 과거 종가' 근사로 낮아지고, 그 비중이
#      '시가총액 소스 감사표'에 그대로 표시됩니다(숨기지 않습니다).
DART_API_KEY = ""

# ── ④ 구글드라이브 캐시 ★★★ 절대 1원칙 ★★★ ──────────────────────────────────────────────
#    이 코드는 기존 캐시를 **절대 삭제·덮어쓰기하지 않습니다.** 약속이 아니라 구조로 보장합니다:
#      · 인덱스의 진실은 append-only JSONL 저널 (기존 줄을 다시 쓰지 않음)
#      · index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업
#      · blob 은 내용해시 경로 → 같은 내용은 재기록조차 안 하고, 다르면 새 리비전
#      · 이미 드라이브에 있던 리포트는 이동·개명 없이 '경로만 등록'(adopt-by-reference)
#      · 삭제 API 자체가 존재하지 않습니다
#
#    GDRIVE_ROOT      : "" 로 두면 환경에 맞게 자동 탐색합니다(권장).
#                       Colab → /content/drive/MyDrive/tcd_cache
#                       Windows/Mac/Linux → 아래 후보를 순서대로 탐색
#                         %USERPROFILE%\Google Drive\내 드라이브\tcd_cache
#                         G:\내 드라이브\tcd_cache , ~/Google Drive/My Drive/tcd_cache …
#                       원하는 경로가 있으면 직접 적으세요. 예: r"G:\내 드라이브\tcd_cache"
GDRIVE_ROOT = ""
GDRIVE_SHARED_NS = "_shared"        # 공용 인덱스 — 다른 전략(TCD v2 등)과 그대로 공유
GDRIVE_PRIVATE_NS = "arc_ncq_v1"    # 전용 인덱스 — 이 전략 고유의 이벤트·신호·백테스트

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요.
#      재귀 스캔해서 "등록만" 합니다. 파일을 옮기거나 지우지 않습니다.
GDRIVE_ADOPT_DIRS = [
    "",                                   # 비면 GDRIVE_ROOT 자체를 스캔
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # r"G:\내 드라이브\내가모아둔리포트",
]

#    ▸ 드라이브를 못 찾으면 여기로 폴백합니다(로컬 SSD). 실행은 정상 진행됩니다.
LOCAL_CACHE_ROOT = "./arc_ncq_cache"

# ── ⑤ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑥ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전 출력물을 예행연습 (수십 초). 네트워크·키 불필요.
#              백테스트·성과·강건성·해석표가 전부 나옵니다. **처음엔 이걸로 한 번 돌려보세요.**
#    "FULL"  : 계약검정 → 스모크 → 리허설 → 카나리 → 실데이터 수집 → 전체 (권장·기본)
#    "CACHED": 신규 수집 없이 구글드라이브 캐시만으로 재현 (오프라인·재현성 검증용)
RUN_MODE = "FULL"

# ── ⑦ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
#    ★ 명세 §3.4: 리서치 소스는 max_workers=4 초과 금지(차단 회피가 속도보다 우선).
N_WORKERS_IO   = 8      # 일반 네트워크 병렬(스레드). 차단이 잦으면 4로 줄이세요.
N_WORKERS_RESEARCH = 4  # 한경/네이버/IR협의회 전용 상한 — 4 초과 금지
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한. 낮출수록 안전/느림.
    "hankyung":  1.2,
    "naver":     1.5,
    "irs":       1.0,
    "krx":       2.0,
    "dart":      8.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0

# ── ⑧ 리포트 수집 ───────────────────────────────────────────────────────────────────────────
RESEARCH_COLLECT      = True
RESEARCH_SOURCES      = ["naver", "hankyung", "irs"]   # 사용자 지시: 한경·네이버 중심 + IRS 보조
RESEARCH_DOWNLOAD_PDF = True     # Phase 3 은 '이벤트로 판정된 건'만 받습니다(비용 절감 핵심)
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 30 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑨ 전략 파라미터 (사전등록 기준선 — 백테스트 결과를 보고 바꾸면 전 결과가 무효) ────────────
NCQ_UNIVERSE_BOTTOM_N = 1000          # 시총 오름차순 하위 N 종목
NCQ_MIN_ADV           = 100_000_000   # 유동성 하한: 직전 20영업일 평균 거래대금 (1억원)
NCQ_LOOKBACK_M        = 24            # 커버리지 룩백 L
NCQ_BURNIN_M          = 24            # burn-in B (baseline 구축 전용, 신호 생성 금지)
NCQ_HOLD_MONTHS       = 12            # 보유기간 H
NCQ_TERCILE           = 1.0 / 3.0     # z 상위 tercile 편입
NCQ_COST_ROUNDTRIP    = 0.018         # 왕복 거래비용 1.8% (수수료+거래세+슬리피지 75bp 편도)
NCQ_MAX_NEW_PER_MONTH = 20            # 월 신규 편입 상한 (초과 시 z 상위 20종목으로 절단)
NCQ_ADV_PARTICIPATION = 0.10          # 편입 시점 20일 ADV 의 10% 이내(3일 내 청산 가능 규모)
NCQ_ACCOUNT_KRW       = 100_000_000   # 실행가능성 계산용 가정 계좌 규모
NCQ_DELIST_HAIRCUT    = -0.50         # 상장폐지 시 폐지 직전가 -50% 후 현금화 (명세 §10)

#    민감도 스윕 (명세 §15-5: 81조합 전부 금지 → 기본값 1 + 각 축 단독 변동 8 = 9조합만)
NCQ_SENS_ADV     = [50_000_000, 100_000_000, 300_000_000]
NCQ_SENS_TOPPCT  = [0.25, 1.0 / 3.0, 0.50]
NCQ_SENS_HOLD    = [6, 12, 18]
NCQ_SENS_COST    = [0.010, 0.018, 0.030]

#    판정 임계 (명세 §5.2 · §12)
NCQ_MIN_EVENTS_PER_MONTH = 5      # 월평균 이벤트가 이보다 적으면 검정력 부족 경고(최상단)
NCQ_MIN_TOTAL_EVENTS     = 800    # 총 이벤트가 이보다 적으면 강한 결론 금지
NCQ_MIN_VALID_YEARS      = 5.0    # 유효 백테스트 윈도우가 이보다 짧으면 중단하고 사용자 판단 요청
NCQ_STOP_IF_SHORT_WINDOW = True   # ↑ 위반 시 백테스트를 실제로 중단할지 (명세 §15-2 기본 준수).
                                  #   False 로 두면 경고만 하고 진행합니다 — 그 경우 결과를
                                  #   '검정력 부족'으로 해석해야 하며 리포트 최상단에 표시됩니다.
NCQ_ARCHIVE_DEFICIT_FRAC = 0.40   # 직후 12개월 중앙값의 40% 미만이면 archive_incomplete
NCQ_ARCHIVE_RUN_MONTHS   = 3      # 연속 3개월 이상 결손이면 그 이전 구간 배제
NCQ_SPONSOR_WARN_FRAC    = 0.70   # 스폰서(IRS) 비중이 이보다 크면 'IR 활동 팩터' 경고
NCQ_MAP_FAIL_WARN_FRAC   = 0.10   # 종목명→티커 매핑 실패율 경고 임계
NCQ_ZPOOL_MIN_N          = 5      # 월 이벤트가 이보다 적으면 직전 3개월 롤링 풀로 z 계산

# ── ⑩ Phase 예산 (초) — 하드캡 도달 시 예외가 아니라 '열화 사다리'가 발동합니다(명세 §3) ──────
NCQ_PHASE_BUDGET_S = {
    "P0": 2700,    # 유니버스 + 가격/시총      45분
    "P1": 7200,    # 리포트 인덱스 전수 수집   120분
    "P2": 300,     # 신규 커버리지 판정        5분
    "P3": 3600,    # PDF 수집 + 텍스트 추출    60분
    "P4": 600,     # 텍스트 스코어링           10분
    "P5": 300,     # 포트폴리오 구성           5분
    "P6": 1500,    # 백테스트 + 통계 검증      25분
}
NCQ_TOTAL_BUDGET_S = 4 * 3600    # 4시간 하드캡

SEED = 20260808          # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True   # 킬 기준 위반 시 즉시 중단하고 보고 (False 로 끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "ARC_NCQ_V1"
STRATEGY_NAME = "ARC-NCQ — 신규 커버리지 × 텍스트 질적 변화"
BUILD_VERSION = "ncq1.20260808.0218"
ACTIVE_PACKS  = []          # (TCD 코어 호환용 — 이 전략은 센서팩 구조를 쓰지 않습니다)

# build/10_ingest_universe.py 의 corpCode 오류 진단이 참조하는 표.
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일 20,000건)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "오픈API 이용동의 필요",
}

# TCD 코어(build/11_ingest_price.py, build/13_ingest_research.py)가 참조하는 이름들.
# ARC-NCQ 의 사이징은 ncq_50_backtest.py 가 별도로 정의하므로 여기 값은 폴백 상수일 뿐이다.
POS_ADV_PARTICIPATION = NCQ_ADV_PARTICIPATION
ACCOUNT_KRW           = NCQ_ACCOUNT_KRW
MIN_ADV_KRW           = NCQ_MIN_ADV


# ============================================================================================
# 조립 블록 01: 01_bootstrap.py
# ============================================================================================


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


# ============================================================================================
# 조립 블록 02: 02_kernel.py
# ============================================================================================



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


# ============================================================================================
# 조립 블록 03: 03_util.py
# ============================================================================================



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
    out = pd.to_datetime(pd.Series(s), errors="coerce")
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
    w = v.clip(lower=mu0 - k * sd0, upper=mu0 + k * sd0)          # ① winsorize

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


def tp_product(z_improve: pd.Series, z_nopay: pd.Series) -> pd.Series:
    """트레이드오프 쌍 = z(개선) × z(대가회피).  ★ 절대로 합으로 바꾸지 말 것 (§1.1).

    합으로 바꾸면 평범한 퀄리티 팩터가 되고 이 전략의 존재 이유가 사라진다.
    한쪽이 결측이면 결과도 결측 — 0으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다.
    """
    a = pd.to_numeric(z_improve, errors="coerce")
    b = pd.to_numeric(z_nopay, errors="coerce")
    return (a * b).astype("float32")


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


# ============================================================================================
# 조립 블록 04: 04_vault.py
# ============================================================================================



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
                idx.loc[miss, "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in fill_src])
                    for i in np.where(miss.to_numpy())[0]]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 를 부여했습니다 "
                         f"(uid 결측 행이 하나로 뭉개지는 것을 방지 — 기존 기록 보존).")
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
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return float("nan")


VAULT: Optional[Vault] = None


# ============================================================================================
# 조립 블록 05: 05_http.py
# ============================================================================================



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


# ============================================================================================
# 조립 블록 06: 10_ingest_universe.py
# ============================================================================================


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
        if n_badcode > n_raw * 0.25:
            LOG.warn(f"폐지목록의 {100*n_badcode/max(n_raw,1):.0f}% 가 코드 형식 불일치로 "
                     f"탈락했습니다. 이 비율이 크면 생존자편향이 그만큼 남습니다 — "
                     f"원본 코드 예시: {raw_codes[codes.isna()].head(5).tolist()}")
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


# ============================================================================================
# 조립 블록 07: 11_ingest_price.py
# ============================================================================================



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
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
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


# ============================================================================================
# 조립 블록 08: 13_ingest_research.py
# ============================================================================================



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
                "pub_date": it.get("createDate") or it.get("date") or it.get("writeDate"),
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


# ============================================================================================
# 조립 블록 09: 14_entity_research.py
# ============================================================================================



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

    out = []
    for m in months:
        lo = m - pd.Timedelta(days=window_days)
        w = x[(x["pub_date"] > lo) & (x["pub_date"] <= m)]
        if w.empty:
            continue
        g = w.groupby("stock_code", observed=True)
        agg = pd.DataFrame({
            "n_analyst": g["analyst_id"].nunique(),
            "tp_median": g["target_price"].median(),
            "rev_up": g["rev"].apply(lambda s: float((s > 0).sum())),
            "rev_dn": g["rev"].apply(lambda s: float((s < 0).sum())),
        }).reset_index().rename(columns={"stock_code": "code"})
        agg["month"] = m
        out.append(agg)
    if not out:
        return pd.DataFrame(columns=cols)
    P = pd.concat(out, ignore_index=True)
    P = P.sort_values(["code", "month"])
    # d2 = -(상향 리비전 수 / 커버리지)   d4 = -Δ(커버리지 애널리스트 수)
    P["d2_raw"] = -(P["rev_up"] / P["n_analyst"].replace(0, np.nan))
    P["d4_raw"] = -P.groupby("code", observed=True)["n_analyst"].diff()
    LOG.ok(f"컨센서스 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['month'].nunique()}개월) — "
           f"목표주가 리비전 관측 {int((P['rev_up']+P['rev_dn']).sum()):,}건")
    PIPE.io("OUT", "MEM", "consensus_panel", P)
    return downcast(P)


# ============================================================================================
# 조립 블록 10: 20_pit.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  PIT 저장소 / 유니버스 / 셀  (계약 C1·C2·C3·C4·C11)                                 ║
# ║                                                                                          ║
# ║  C1: 모든 데이터 접근은 PIT.get(table, as_of) 한 곳만 통과한다.                            ║
# ║      DataFrame 직접 슬라이싱 금지. 우회 파라미터를 만들지 않는다.                          ║
# ║  C2: 유니버스는 상장폐지 종목을 포함한다. 정리매매가 없으면 -100%.                          ║
# ║  C11: 셀 = (date, industry, size_bucket). 다른 그룹키 금지.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class PITStore:
    """유일한 데이터 게이트웨이. 등록된 테이블은 knowledge_date 로 정렬되어 보관되고,
    as_of 조회는 항상 knowledge_date <= as_of 를 강제한다. 예외 경로는 존재하지 않는다."""

    def __init__(self):
        self._t: Dict[str, pd.DataFrame] = {}
        self._meta: Dict[str, dict] = {}
        self.access_log: Counter = Counter()

    def register(self, name: str, df: pd.DataFrame, key_cols: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._t[name] = pd.DataFrame(columns=list(PIT_COLS))
            self._meta[name] = {"rows": 0, "keys": list(key_cols), "empty": True}
            LOG.debug(f"PIT 등록(빈 테이블): {name}")
            return
        missing = [c for c in PIT_COLS if c not in df.columns]
        if missing:
            raise KeyError(
                f"[C1 위반] 테이블 '{name}' 에 PIT 컬럼 {missing} 이 없습니다. "
                f"수집 함수의 반환값을 pit_frame(df, event_date, knowledge_date) 로 감싸세요. "
                f"이 검사를 우회하는 방법은 의도적으로 만들지 않았습니다.")
        d = df.copy()
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        d = d.reset_index(drop=True)
        self._t[name] = d
        self._meta[name] = {"rows": len(d), "keys": list(key_cols), "empty": False,
                            "kd_min": d["knowledge_date"].min(), "kd_max": d["knowledge_date"].max()}
        PIPE.io("OUT", "MEM", f"PIT:{name}", d)

    def has(self, name: str) -> bool:
        return name in self._t and not self._meta.get(name, {}).get("empty", True)

    def get(self, name: str, as_of, cols: Optional[Sequence[str]] = None,
            latest_by: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """시점 as_of 에서 '알 수 있었던' 행만 반환.
        latest_by 를 주면 그 키별 최신 1행(=당시 최신 관측)만 남긴다."""
        self.access_log[name] += 1
        if name not in self._t:
            return pd.DataFrame()
        t = as_ts(as_of)
        d = self._t[name]
        if d.empty:
            return d
        # knowledge_date 정렬되어 있으므로 searchsorted 로 O(log n) 절단
        pos = int(np.searchsorted(d["knowledge_date"].values, np.datetime64(t), side="right"))
        d = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in d.columns]
            if lb:
                d = d.drop_duplicates(subset=lb, keep="last")
        return d[list(cols)] if cols else d

    def asof_join(self, panel: pd.DataFrame, name: str, by: str,
                  left_time: str = "month", cols: Optional[Sequence[str]] = None,
                  suffix: str = "") -> pd.DataFrame:
        """get() 의 벡터화 등가물. 패널 전체에 대해 한 번에 as-of 결합한다.

        merge_asof(direction='backward') 는 knowledge_date <= month 인 마지막 행만 붙이므로
        C1 과 정확히 동일한 의미를 갖는다. 루프로 get() 을 3만 번 부르는 대신 이걸 쓴다.
        """
        self.access_log[name] += 1
        if name not in self._t or self._t[name].empty or panel.empty:
            return panel
        right = self._t[name]
        if by not in right.columns or by not in panel.columns:
            LOG.debug(f"asof_join 건너뜀: '{name}' 에 결합키 '{by}' 없음")
            return panel
        use = [c for c in (cols or [c for c in right.columns
                                    if c not in ("event_date", "_src")]) if c in right.columns]
        for c in (by, "knowledge_date"):
            if c not in use:
                use.append(c)
        R = (right[use].dropna(subset=["knowledge_date", by])
                        .sort_values("knowledge_date", kind="stable")).copy()
        if R.empty:
            return panel

        # ★★ 결합키가 결측인 패널 행을 '떨어뜨리면' 안 된다. ★★
        #   attach_fundamentals 에서 corp_code 가 없는 종목(대개 상장폐지·신규상장·비DART)이
        #   통째로 사라지면 그게 곧 생존자편향 재유입이다(C2 위반). merge_asof 는 by 키에
        #   NaN 이 있으면 다루지 못하므로, 유효키 부분만 결합한 뒤 전체 패널에 되붙인다.
        base = panel.copy()
        base["_ord"] = np.arange(len(base))
        mask = base[left_time].notna() & base[by].notna()
        n_drop = int((~mask).sum())
        if n_drop:
            LOG.debug(f"asof_join '{name}': 결합키 결측 {n_drop:,}행은 결측값으로 보존합니다"
                      f"(행을 버리지 않습니다 — C2).")
        L = base[mask].copy()
        if L.empty:
            LOG.warn(f"asof_join '{name}': 결합 가능한 행이 없습니다. 결합을 건너뜁니다.")
            return panel
        R[by] = R[by].astype(str)
        L[by] = L[by].astype(str)
        L = L.sort_values(left_time, kind="stable")
        try:
            M = pd.merge_asof(L, R, left_on=left_time, right_on="knowledge_date",
                              by=by, direction="backward", suffixes=("", suffix or "_r"))
        except Exception as e:                                     # noqa
            LOG.warn(f"asof_join 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다. "
                     f"대개 정렬/타입 문제입니다.")
            return panel
        new_cols = [c for c in M.columns if c not in base.columns]
        if not new_cols:
            return panel
        add = M.set_index("_ord")[new_cols]
        out = base.set_index("_ord")
        out = out.join(add, how="left")            # 결합 실패 행은 NaN 으로 남고, 행은 유지된다
        out = out.sort_index().reset_index(drop=True)
        out.index = panel.index
        return out

    def report(self):
        rows = []
        for n, m in self._meta.items():
            rows.append([n, f"{m['rows']:,}",
                         str(m.get("kd_min", ""))[:10], str(m.get("kd_max", ""))[:10],
                         ",".join(m.get("keys", []))[:30], f"{self.access_log.get(n,0):,}"])
        LOG.table(rows, ["PIT 테이블", "행수", "knowledge 최소", "knowledge 최대", "키", "조회횟수"],
                  ["l", "r", "l", "l", "l", "r"],
                  title="PIT 저장소 상태 (C1 — 모든 조회는 knowledge_date <= as_of 강제)")


PIT = PITStore()


# ── 유니버스 (C2) ───────────────────────────────────────────────────────────────────────────
LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년


class Universe:
    def __init__(self, sec: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame,
                 snap_window_days: int = 100):
        self.sec = sec.copy()
        self.snap = snapshots
        self.attrition: List[dict] = []
        self._cache_at: Dict[pd.Timestamp, List[str]] = {}
        # 스냅샷 주기가 분기면 ±45일 창으로는 대부분의 달이 스냅샷을 못 만난다 → 창을 넓힌다.
        self._snap_window_days = snap_window_days
        self._trading_days = (np.sort(pd.unique(as_ts_series(px_daily["date"]).values))
                              if px_daily is not None and len(px_daily) else
                              np.array([], dtype="datetime64[ns]"))
        self._snap_by_month: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            for d, g in snapshots.groupby("snap_date"):
                self._snap_by_month[as_ts(d)] = set(g["code"])

        self.sec["listing_date"] = as_ts_series(self.sec["listing_date"])
        self.sec["delisting_date"] = as_ts_series(self.sec["delisting_date"])
        self.sec = self.sec.drop_duplicates("code").reset_index(drop=True)

        # 벡터화용 배열 (at() 이 매월 3,500행 itertuples 를 도는 것을 없앤다)
        self._codes_arr = self.sec["code"].to_numpy(dtype=object)
        self._ld_arr = self.sec["listing_date"].to_numpy(dtype="datetime64[ns]")
        self._dd_arr = self.sec["delisting_date"].to_numpy(dtype="datetime64[ns]")
        self._delist = {c: d for c, d in zip(self._codes_arr, self.sec["delisting_date"])
                        if pd.notna(d)}

        # 상장 후 250거래일 시즈닝 — 거래일 배열에 대한 searchsorted 를 한 번에 벡터화
        #
        # ★ 앵커 주의 (조용한 유니버스 붕괴의 원인) ─────────────────────────────────────
        #   searchsorted 는 '가격패널 시작일 이전에 상장한' 종목을 전부 index 0 으로 보낸다.
        #   거기에 +250 을 더하면 1990년 상장 종목조차 "패널 시작 후 250거래일"에야 시즈닝이
        #   끝난 것으로 계산된다. 2016-08 시작 패널이면 2017년 중반까지 삼성전자를 포함한
        #   기존 상장사 전부가 유니버스에서 빠진다. 에러 없이, 로그도 없이.
        #   → 시즈닝의 앵커는 '패널 시작일'이 아니라 '상장일'이다. 패널 시작 전 상장분은
        #     이미 오래전에 시즈닝이 끝난 것으로 확정한다.
        self._seasoned: Dict[str, Any] = {}
        _FAR = pd.Timestamp("2100-01-01")     # 패널 안에서 시즈닝이 끝나지 않는 신규 상장
        if len(self._trading_days):
            t0 = self._trading_days[0]
            idx = np.searchsorted(self._trading_days, self._ld_arr, side="left")
            idx_s = idx + LISTING_SEASONING_DAYS
            n_td = len(self._trading_days)
            inside = idx_s < n_td
            seas = np.where(inside,
                            self._trading_days[np.minimum(idx_s, n_td - 1)],
                            np.datetime64(_FAR.isoformat(), "ns"))
            # 패널 시작 전 상장 → 달력 1년으로 확정(패널 시작보다 앞서므로 사실상 제약이 아님)
            pre = (~np.isnat(self._ld_arr)) & (self._ld_arr < t0)
            for c, ld, s, p in zip(self._codes_arr, self._ld_arr, seas, pre):
                if np.isnat(ld):
                    self._seasoned[c] = pd.NaT
                elif p:
                    self._seasoned[c] = as_ts(ld) + pd.Timedelta(days=365)
                else:
                    self._seasoned[c] = as_ts(s)
        else:
            for c, ld in zip(self._codes_arr, self._ld_arr):
                self._seasoned[c] = pd.NaT if np.isnat(ld) else as_ts(ld) + pd.Timedelta(days=365)

    def at(self, t) -> List[str]:
        """시점 t 의 유니버스. t 이후 상장 종목이 하나라도 섞이면 그 자체로 C2 위반이다."""
        t = as_ts(t)
        if t in self._cache_at:
            return self._cache_at[t]

        # ① 상장일·폐지일로 유도한 집합이 '기준선'이다. 이건 항상 성립해야 한다.
        base = set(self._codes_dated_at(t))

        # ② 스냅샷은 '보강'이다. 대체가 아니다.
        #    ★ 과거 스냅샷만 쓴다(미래 스냅샷을 고르면 그 자체가 누수).
        #    ★ 교집합이 아니라 합집합이다. 부분 응답 스냅샷으로 기준선을 깎으면
        #      그 달 유니버스가 조용히 줄어 곧바로 선택편향이 된다. 늘리기만 한다.
        past = [d for d in self._snap_by_month if d <= t]
        if past:
            key = max(past)
            if (t - key).days <= self._snap_window_days:
                base |= set(self._snap_by_month[key])

        # ③ 폐지 이후 종목은 어떤 경로로 들어왔든 반드시 제외한다.
        base -= {c for c, dd in self._delist.items() if pd.notna(dd) and dd <= t}

        # ④ 상장 후 250거래일 시즈닝
        out = [c for c in base
               if not (pd.notna(self._seasoned.get(c, pd.NaT)) and self._seasoned[c] > t)]
        out = sorted(out)
        self._cache_at[t] = out
        return out

    def _codes_dated_at(self, t: pd.Timestamp) -> List[str]:
        """상장일/폐지일 기반 멤버십. itertuples 루프를 매월 도는 대신 벡터화한다
        (종목 3,500 × 120개월 = 42만 회 파이썬 루프였다)."""
        ld, dd = self._ld_arr, self._dd_arr
        tt = np.datetime64(t)
        ok = ~((~np.isnat(ld)) & (ld > tt)) & ~((~np.isnat(dd)) & (dd <= tt))
        ok &= ~(np.isnat(ld) & np.isnat(dd))        # 근거가 전혀 없는 종목은 넣지 않는다
        return self._codes_arr[ok].tolist()

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"month": as_ts(t), "stage": stage, "n": len(codes)})

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "PIT유니버스", "가격보유", "유동성필터", "거부권통과",
                 "하한선통과", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max", "size"])
        rows = []
        prev = None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/prev:.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "월평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 (§10.4) — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < 5:
            LOG.warn("최종 선정 종목이 월평균 5개 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 어느 게이트가 원인인지 위 표에서 먼저 확인하세요.")


# ── 셀 (C11) ────────────────────────────────────────────────────────────────────────────────
SIZE_BUCKETS = [(0, 50, "<50"), (50, 100, "50-99"), (100, 300, "100-299"),
                (300, 1000, "300-999"), (1000, 10 ** 9, "1000+")]


def size_bucket(n_emp: float) -> str:
    if n_emp is None or not np.isfinite(n_emp) or n_emp <= 0:
        return "미상"
    for lo, hi, lab in SIZE_BUCKETS:
        if lo <= n_emp < hi:
            return lab
    return "1000+"


def build_cells(panel: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell_key = (date, industry, size_bucket). 규모를 넣는 이유는 §5.6-② 참조:
    정부 지원제도 요건 대부분이 기업 규모에 연동되므로 정책효과가 셀 내 공통충격으로 흡수된다.
    비용 0의 오염 제거."""
    ind = sec.set_index("code")["industry"].astype(str).to_dict()
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["industry_l1"] = p["industry"].str.slice(0, 4)                 # 폴백용 상위 단위
    p["size_bucket"] = p["employees"].map(size_bucket) if "employees" in p.columns else "미상"
    ym = p["month"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["industry"] + "|" + p["size_bucket"]
    # 폴백 사다리를 컬럼으로 미리 만들어 둔다. 센서별로 유효 관측이 부족할 때
    # xsec_z_l 이 이 사다리를 타고 내려간다(C11 "산업 상위 단위로 폴백").
    p["cell_l2"] = ym + "|" + p["industry_l1"] + "|ALL"
    p["cell_l3"] = ym + "|ALL|ALL"

    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    n_small = int(small.sum())
    still_n = 0
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        still_n = int(still.sum())
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백 발생: 1차 {n_small:,}행(산업 상위단위로) / 2차 {still_n:,}행(전체로). "
                 f"C11 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 1단계 {p['cell'].nunique():,}개 · 2단계 {p['cell_l2'].nunique():,}개 · "
              f"3단계 {p['cell_l3'].nunique():,}개")
    return p


# ============================================================================================
# 조립 블록 11: ncq_05_budget.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  Phase 예산 · 열화 사다리 · 실행 매니페스트 · 드라이브 루트 해석                     ║
# ║                                                                                          ║
# ║  입력: 없음        출력: PhaseBudget / degrade() / MANIFEST / resolve_gdrive_root()       ║
# ║                                                                                          ║
# ║  ★ 명세 §3.2 의 핵심 의미론: 예산 하드캡에 도달해도 **예외를 던지지 않는다.**              ║
# ║    현재까지 수집분을 저장하고, 열화 사다리를 한 단계 내려간 뒤, 그 사실을 로그와            ║
# ║    run_manifest.json 에 명시적으로 남긴다. 조용히 잘린 결과가 가장 위험하다.               ║
# ║  ★ L5(IR협의회 단독으로 축소)는 전략 취지를 훼손하므로 **자동 적용 금지**. 예외를 던진다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MANIFEST: Dict[str, Any] = {
    "strategy_id": STRATEGY_ID,
    "build_version": BUILD_VERSION,
    "started_at": _dt.datetime.now().isoformat(timespec="seconds"),
    "run_mode": RUN_MODE,
    "seed": SEED,
    "backtest_window_requested": [BACKTEST_START, BACKTEST_END],
    "degradation_applied": [],
    "phase_seconds": {},
    "phase_budget_seconds": dict(NCQ_PHASE_BUDGET_S),
    "notes": [],
}


def manifest_put(key: str, value: Any) -> None:
    """매니페스트 갱신. 직렬화 불가 값은 문자열로 낮춰 저장한다(매니페스트가 실패의 원인이 되면 안 된다)."""
    try:
        json.dumps({key: value}, ensure_ascii=False, default=str)
        MANIFEST[key] = value
    except Exception:
        MANIFEST[key] = str(value)


def manifest_note(msg: str) -> None:
    MANIFEST.setdefault("notes", []).append(f"[{_dt.datetime.now():%H:%M:%S}] {msg}")


# ── 열화 사다리 (명세 §3.3) ─────────────────────────────────────────────────────────────────
LADDER: "OrderedDict[str, str]" = OrderedDict([
    ("L1", "한경컨센서스 소스 드롭 (전략 취지 손상: 낮음 — 이미 선택 소스)"),
    ("L2", "PDF 텍스트 추출을 앞 6페이지로 제한 (낮음 — 투자포인트는 전면부 집중)"),
    ("L3", "백테스트 윈도우 10년 → 7년 (중간 — 검정력 감소)"),
    ("L4", "유니버스 하위 1000 → 하위 700 (중간 — 이벤트 수 감소)"),
    ("L5", "인덱스 수집을 IR협의회 단독으로 축소 (높음 — 자동 적용 금지)"),
])
_DEGRADED: "OrderedDict[str, str]" = OrderedDict()


def degrade(level: str, reason: str) -> None:
    """열화 단계를 적용한다. 같은 단계를 두 번 적용해도 부작용이 없어야 한다(멱등)."""
    level = str(level).upper()
    if level not in LADDER:
        raise ValueError(f"알 수 없는 열화 단계: {level} (가능: {list(LADDER)})")
    if level == "L5":
        raise KillCriteria(
            "열화 L5(IR협의회 단독 축소)는 자동 적용이 금지되어 있습니다(명세 §3.3). "
            "L4 까지 적용해도 예산을 못 맞추면 실행을 중단하고 사용자 판단을 요청합니다. "
            f"사유: {reason}")
    if level in _DEGRADED:
        return
    _DEGRADED[level] = reason
    MANIFEST["degradation_applied"] = [{"level": k, "reason": v} for k, v in _DEGRADED.items()]
    LOG.warn(f"⚠ 열화 사다리 {level} 적용 — {LADDER[level]}  |  사유: {reason}")
    manifest_note(f"열화 {level} 적용: {reason}")

    # 단계별 실제 부작용을 여기서 한 번에 반영한다(호출측이 잊어버릴 수 없도록).
    G = globals()
    if level == "L1":
        G["RESEARCH_SOURCES"] = [s for s in RESEARCH_SOURCES if s != "hankyung"]
        LOG.info(f"  → 활성 리서치 소스: {G['RESEARCH_SOURCES']}")
    elif level == "L2":
        G["NCQ_PDF_MAX_PAGES"] = 6
        LOG.info("  → PDF 텍스트 추출을 앞 6페이지로 제한합니다.")
    elif level == "L3":
        new_start = (as_ts(BACKTEST_END) - pd.DateOffset(years=7) + pd.Timedelta(days=1))
        G["BACKTEST_START"] = new_start.strftime("%Y-%m-%d")
        LOG.info(f"  → 백테스트 시작을 {G['BACKTEST_START']} 로 축소합니다. "
                 f"BH-FDR 임계는 그대로 두되 검정력 감소를 리포트에 명시합니다.")
    elif level == "L4":
        G["NCQ_UNIVERSE_BOTTOM_N"] = 700
        LOG.info("  → 유니버스를 시총 하위 700 종목으로 축소합니다.")


def degraded() -> List[str]:
    return list(_DEGRADED.keys())


def is_degraded(level: str) -> bool:
    return str(level).upper() in _DEGRADED


NCQ_PDF_MAX_PAGES = 0        # 0 = 전체. degrade("L2") 가 6 으로 바꾼다.


# ── Phase 예산 가드 ─────────────────────────────────────────────────────────────────────────
class PhaseBudget:
    """Phase 별 시간 예산. 캡 도달 시 check() 가 False 를 돌려주고 **예외는 던지지 않는다.**

    사용법:
        with PhaseBudget("P1", NCQ_PHASE_BUDGET_S["P1"], on_exceed="L3") as B:
            for job in jobs:
                if not B.check():
                    break                      # 부분 결과를 저장하고 정상 종료
                ...

    ★ time.monotonic() 을 쓴다. time.time() 은 NTP 보정으로 뒤로 갈 수 있어서
      장시간 실행 중 예산이 음수가 되는 사고가 실제로 난다.
    """

    _spent: Dict[str, float] = {}

    def __init__(self, name: str, cap_seconds: float, on_exceed: Optional[str] = None,
                 quiet: bool = False):
        self.name = str(name)
        self.cap = float(cap_seconds) if cap_seconds and cap_seconds > 0 else float("inf")
        self.on_exceed = on_exceed
        self.quiet = quiet
        self.t0 = time.monotonic()
        self.exceeded = False
        self._warned = False

    # -- 컨텍스트 --------------------------------------------------------------------------
    def __enter__(self) -> "PhaseBudget":
        self.t0 = time.monotonic()
        if not self.quiet:
            LOG.info(f"[{self.name}] 예산 {self.cap/60:.0f}분 — 시작")
        return self

    def __exit__(self, exc_type, exc, tb):
        el = self.elapsed()
        PhaseBudget._spent[self.name] = PhaseBudget._spent.get(self.name, 0.0) + el
        MANIFEST["phase_seconds"][self.name] = round(PhaseBudget._spent[self.name], 1)
        if not self.quiet:
            pct = 100.0 * el / self.cap if np.isfinite(self.cap) and self.cap > 0 else float("nan")
            LOG.info(f"[{self.name}] 종료 — {el/60:.1f}분 / 예산 {self.cap/60:.0f}분"
                     + (f" ({pct:.0f}%)" if np.isfinite(pct) else ""))
        return False        # 예외를 삼키지 않는다

    # -- 조회 ------------------------------------------------------------------------------
    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.t0)

    def frac(self) -> float:
        return self.elapsed() / self.cap if np.isfinite(self.cap) and self.cap > 0 else 0.0

    def remaining(self) -> float:
        return max(0.0, self.cap - self.elapsed()) if np.isfinite(self.cap) else float("inf")

    def check(self) -> bool:
        """캡 도달 시 False. 최초 1회만 경고하고 on_exceed 열화를 적용한다."""
        if self.elapsed() < self.cap:
            return True
        self.exceeded = True
        if not self._warned:
            self._warned = True
            LOG.warn(f"[{self.name}] 시간 예산 {self.cap/60:.0f}분을 초과했습니다 — "
                     f"여기까지 수집된 결과를 저장하고 정상 종료합니다(예외 아님).")
            manifest_note(f"{self.name} 예산 초과 ({self.elapsed()/60:.1f}분)")
            if self.on_exceed:
                try:
                    degrade(self.on_exceed, f"{self.name} 예산 초과")
                except KillCriteria:
                    raise
                except Exception as e:                       # noqa
                    LOG.warn(f"열화 적용 실패({type(e).__name__}) — 계속 진행합니다.")
        return False

    @classmethod
    def total_spent(cls) -> float:
        return float(sum(cls._spent.values()))

    @classmethod
    def report(cls) -> None:
        if not cls._spent:
            return
        rows = []
        for k in ("P0", "P1", "P2", "P3", "P4", "P5", "P6"):
            if k not in cls._spent:
                continue
            cap = NCQ_PHASE_BUDGET_S.get(k, 0)
            sp = cls._spent[k]
            rows.append([k, f"{sp/60:7.1f}분", f"{cap/60:5.0f}분",
                         f"{100*sp/cap:5.0f}%" if cap else "—",
                         "✔ 예산 내" if (not cap or sp <= cap) else "❗ 초과"])
        tot = cls.total_spent()
        rows.append(["합계", f"{tot/60:7.1f}분", f"{NCQ_TOTAL_BUDGET_S/60:5.0f}분",
                     f"{100*tot/NCQ_TOTAL_BUDGET_S:5.0f}%",
                     "✔ 4시간 이내" if tot <= NCQ_TOTAL_BUDGET_S else "❗ 4시간 초과"])
        LOG.table(rows, ["Phase", "실측", "예산", "소진율", "판정"], ["c", "r", "r", "r", "l"],
                  title="Phase 시간 예산 (명세 §3.1 — 하드캡 4시간)")
        if degraded():
            LOG.table([[lv, LADDER[lv], _DEGRADED[lv]] for lv in degraded()],
                      ["단계", "조치", "발동 사유"], ["c", "l", "l"],
                      title="적용된 열화 사다리 (리포트 최상단에도 표시됩니다)")


# ── 구글드라이브 루트 해석 (Colab / JupyterLab / Windows 양방향) ────────────────────────────
def _ncq_drive_candidates() -> List[str]:
    """드라이브 루트 후보를 우선순위대로. 존재 검사는 호출측에서 한다."""
    home = os.path.expanduser("~")
    leaf = "tcd_cache"          # ★ 공용 인덱스를 TCD v2 와 공유하려면 같은 루트를 써야 한다
    cands = [
        os.environ.get("ARC_NCQ_GDRIVE_ROOT", ""),
        os.environ.get("GDRIVE_ROOT", ""),
        "/content/drive/MyDrive/" + leaf,
        os.path.join(home, "Google Drive", "내 드라이브", leaf),
        os.path.join(home, "Google Drive", "My Drive", leaf),
        os.path.join(home, "GoogleDrive", "MyDrive", leaf),
        os.path.join(home, "Google 드라이브", "내 드라이브", leaf),
    ]
    # 윈도우 드라이브 문자 마운트 (구글 드라이브 데스크톱 기본 G:)
    for dl in ("G:", "H:", "I:"):
        cands.append(os.path.join(dl + os.sep, "내 드라이브", leaf))
        cands.append(os.path.join(dl + os.sep, "My Drive", leaf))
    return [c for c in cands if c]


def resolve_gdrive_root() -> str:
    """GDRIVE_ROOT 를 환경에 맞게 확정하고 전역에 반영한다.

    ★ 하드코딩된 '/content/...' 를 절대 그대로 쓰지 않는다(명세 §13.2). Colab 이면 마운트를
      시도하고, 아니면 이미 동기화된 드라이브 폴더를 찾고, 그마저 없으면 로컬로 폴백한다.
      어느 경로가 선택됐는지는 반드시 로그와 매니페스트에 남긴다.
    """
    G = globals()
    explicit = str(GDRIVE_ROOT or "").strip()
    if explicit:
        os.makedirs(explicit, exist_ok=True)
        G["GDRIVE_ROOT"] = explicit
        manifest_put("gdrive_root", explicit)
        manifest_put("gdrive_root_mode", "EXPLICIT")
        LOG.ok(f"드라이브 루트(사용자 지정): {explicit}")
        return explicit

    if ENV.get("colab"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            if not os.path.isdir("/content/drive/MyDrive"):
                LOG.info("Colab 구글드라이브 마운트를 시도합니다 — 인증 팝업을 승인해 주세요.")
                _gdrive.mount("/content/drive", force_remount=False)
        except Exception as e:                                  # noqa
            LOG.warn(f"Colab 드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다. "
                     f"이 경우 캐시가 세션 종료와 함께 사라지므로 재실행 비용이 큽니다.")

    for c in _ncq_drive_candidates():
        try:
            if os.path.isdir(c) or os.path.isdir(os.path.dirname(c)):
                os.makedirs(c, exist_ok=True)
                G["GDRIVE_ROOT"] = c
                manifest_put("gdrive_root", c)
                manifest_put("gdrive_root_mode", "AUTO_DRIVE")
                LOG.ok(f"드라이브 루트(자동 탐색): {c}")
                return c
        except Exception:
            continue

    root = os.path.abspath(LOCAL_CACHE_ROOT)
    os.makedirs(root, exist_ok=True)
    G["GDRIVE_ROOT"] = root
    manifest_put("gdrive_root", root)
    manifest_put("gdrive_root_mode", "LOCAL_FALLBACK")
    LOG.warn(f"구글드라이브를 찾지 못해 로컬 캐시를 사용합니다: {root}\n"
             f"    드라이브를 쓰려면 상단 GDRIVE_ROOT 에 경로를 직접 적어주세요 "
             f"(예: r\"G:\\내 드라이브\\tcd_cache\").")
    return root


def ncq_adopt_dirs() -> List[str]:
    """빈 문자열을 GDRIVE_ROOT 로 치환하고 중복·미존재를 정리한 스캔 대상 목록."""
    out, seen = [], set()
    for d in GDRIVE_ADOPT_DIRS:
        p = (d or "").strip() or GDRIVE_ROOT
        if not p:
            continue
        rp = os.path.abspath(p)
        if rp in seen or not os.path.isdir(rp):
            continue
        seen.add(rp)
        out.append(rp)
    return out


# ============================================================================================
# 조립 블록 12: ncq_08_sources.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-0  KRX-free 다중소스 계층 — PIT 유니버스 · 생존자편향 제거 · PIT 상장주식수            ║
# ║                                                                                          ║
# ║  ⚠ 배경: KRX(data.krx.co.kr / pykrx / kind.krx.co.kr)가 차단된 환경을 **정상 경로**로       ║
# ║    간주한다. KRX 는 '있으면 검증에 쓰는 보조'일 뿐, 어떤 결과도 KRX 에 의존하지 않는다.     ║
# ║                                                                                          ║
# ║  입력 : 없음(네트워크) / px_daily(일봉)                                                    ║
# ║  출력 : ① 상장·폐지 원장(생존자편향)  ② PIT 상장주식수 이력  ③ 소스 가용성 감사표          ║
# ║  실패 : 모든 함수는 예외 대신 빈 DataFrame 을 돌려주고, 무엇이 없는지 감사표에 남긴다.      ║
# ║                                                                                          ║
# ║  ── 생존자편향 4중 방어 ────────────────────────────────────────────────────────────────  ║
# ║   D1 FDR GitHub 폐지원장   raw.githubusercontent.com 정적 CSV. 1956년부터 전 폐지 종목의   ║
# ║                            상장일·폐지일·폐지사유·상장주식수. **KRX 서버를 거치지 않음**   ║
# ║   D2 가격 구간 실측        일봉의 첫/마지막 거래일로 상장·폐지 구간을 데이터에서 복원.      ║
# ║                            명단에 없는 종목도 잡는다(명단 결손의 최후 방어선)              ║
# ║   D3 DART 존재성           corpCode ↔ 종목코드. 이름·사명변경 보강                         ║
# ║   D4 KRX 월말 스냅샷       NCQ_USE_KRX=True 일 때만. 검증·보강 용도(합집합, 절대 교집합 아님)║
# ║                                                                                          ║
# ║  ── PIT 시가총액 = PIT 상장주식수 × 그 시점 수정종가 ──────────────────────────────────    ║
# ║   S1 DART 주식총수현황(stockTotqySttus) — 접수일자 기준 진짜 PIT. 증자·분할·감자 반영       ║
# ║   S2 폐지원장의 ListingShares — 폐지 종목의 상장주식수(그 종목 생애 상수로 사용)            ║
# ║   S3 현재 상장목록의 Stocks — 최신 값. 과거 적용 시 근사(증자 미반영)이며 그 사실을 표기    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

NCQ_SOURCE_STATUS: "OrderedDict[str, dict]" = OrderedDict()


def ncq_src(name: str, ok: bool, n: int = -1, note: str = "", krx: bool = False):
    NCQ_SOURCE_STATUS[name] = {"name": name, "ok": bool(ok), "n": int(n), "note": note, "krx": krx}


def ncq_krx_enabled() -> bool:
    """KRX 계열 경로를 쓸지. 기본은 False(차단 이력). 자격증명 없이 True 여도 켜지 않는다."""
    if not bool(globals().get("NCQ_USE_KRX", False)):
        return False
    if not (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW) and not KRX_OPENAPI_KEY:
        return False
    return True


def ncq_configure_sources() -> None:
    """KRX 차단 상황에 맞게 전역 수집 경로를 재배선한다. main 초반에 1회 호출.

    ★ 이게 없으면 pykrx 가 설치된 환경에서 종목마다 KRX 로 먼저 붙었다가 타임아웃으로 실패한다.
      2,600종목 × 타임아웃이면 그것만으로 수십 분을 버리고, 차단을 더 악화시킨다.
    """
    G = globals()
    if ncq_krx_enabled():
        LOG.info("KRX 경로 활성 — 월말 스냅샷을 '검증·보강'으로만 사용합니다(의존하지 않음).")
        return
    # ① pykrx 자체를 끈다 (KRXGate.warmup / 가격 체인 / 스냅샷이 전부 이 핸들을 본다)
    if G.get("pykrx_stock") is not None:
        G["pykrx_stock"] = None
    # ② 가격 폴백 체인에서 KRX 계열을 제거하고 네이버를 1순위로
    try:
        G["PRICE_CHAIN"] = [("naver", _px_naver), ("fdr", _px_fdr), ("yfinance", _px_yf)]
    except Exception:
        pass
    # ③ 유니버스 스냅샷 비활성
    G["UNIVERSE_SNAPSHOT_FREQ"] = "off"
    LOG.warn("KRX 경로 비활성 (NCQ_USE_KRX=False 또는 자격증명 없음) — "
             "네이버 차트 → FDR → yfinance 순으로 가격을 받고, 상장·폐지와 상장주식수는 "
             "FDR GitHub 정적 캐시 + DART + 가격구간 실측으로 구성합니다. "
             "이 경로만으로 PIT 유니버스와 생존자편향 제거가 완결됩니다.")
    manifest_put("krx_enabled", False)


# ── D1. FDR GitHub 폐지원장 (풍부한 컬럼 버전) ──────────────────────────────────────────────
NCQ_DELIST_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "reason", "industry", "shares_listing", "secugroup"]


def ncq_fdr_delisting_full() -> pd.DataFrame:
    """폐지 종목 원장. build/10 의 fetch_fdr_delisting 보다 많은 컬럼을 살린다.

    실측 컬럼: Symbol, Name, Market, SecuGroup, Kind, ListingDate, DelistingDate, Reason,
              ArrantEnforceDate, ArrantEndDate, Industry, ParValue, ListingShares, ToSymbol, ToName
    ★ ListingDate 가 여기에만 있다. 현재 상장목록 CSV 에는 상장일 컬럼이 없어서, KIND 가 막히면
      '현재 상장 종목의 상장일'은 가격 구간 실측(D2)으로 복원해야 한다.
    """
    d = _fdr_cache_csv("listing/delisting")
    if d is None or len(d) == 0:
        ncq_src("FDR폐지원장", False, 0, "정적 CSV 수신 실패 — 생존자편향 제거가 약해집니다")
        LOG.warn("폐지 종목 원장을 받지 못했습니다. 생존자편향 제거는 '가격 구간 실측'에만 "
                 "의존하게 됩니다(약화). raw.githubusercontent.com 접근을 확인하세요.")
        return pd.DataFrame(columns=NCQ_DELIST_COLS)
    col = {str(c).strip().lower(): c for c in d.columns}

    def g(*names, default=None):
        for n in names:
            if n in col:
                return d[col[n]]
        return pd.Series([default] * len(d))

    t = pd.DataFrame({
        "code": g("symbol", "code", "isu_cd", "isu_srt_cd").map(to_code6),
        "name": g("name", "isu_nm", default="").astype(str).str.strip(),
        "market": g("market", default="").astype(str),
        "listing_date": as_ts_series(g("listingdate", "listing_date")),
        "delisting_date": as_ts_series(g("delistingdate", "delisting_date", "dedate")),
        "reason": g("reason", default="").astype(str),
        "industry": g("industry", "sector", default="").astype(str),
        "shares_listing": pd.to_numeric(g("listingshares", "stocks", "listing_shares"),
                                        errors="coerce"),
        "secugroup": g("secugroup", "kind", default="").astype(str),
    })
    n_raw = len(t)
    t = t.dropna(subset=["code"])
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (이른 쪽을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 줄어든다)
    t = t.sort_values("delisting_date").drop_duplicates("code", keep="last")
    # 주권(보통주)이 아닌 것은 여기서 표시만 하고 버리지 않는다 — 제외는 유니버스 단계에서.
    n_ok = int(t["delisting_date"].notna().sum())
    LOG.ok(f"[D1] 폐지 종목 원장 {len(t):,}건 (원본 {n_raw:,} → 코드정규화·중복제거 후 {len(t):,}) · "
           f"폐지일 보유 {n_ok:,}건 · 상장일 보유 "
           f"{int(t['listing_date'].notna().sum()):,}건 — KRX 무관 정적 경로")
    ncq_src("FDR폐지원장", True, len(t), "생존자편향 1차 방어 · 상장일/폐지일/폐지사유/상장주식수")
    return t


def ncq_fdr_listing_full() -> pd.DataFrame:
    """현재 상장목록(종가·시가총액·상장주식수 포함). 상장일 컬럼은 없다."""
    d = _fdr_cache_csv("listing/krx")
    if d is None or len(d) == 0:
        ncq_src("FDR상장목록", False, 0, "정적 CSV 수신 실패")
        return pd.DataFrame(columns=["code", "name", "market", "close", "marcap", "shares"])
    col = {str(c).strip().lower(): c for c in d.columns}
    code_c = col.get("code") or col.get("symbol") or col.get("isu_cd")
    if not code_c:
        ncq_src("FDR상장목록", False, 0, f"종목코드 컬럼 없음: {list(d.columns)[:8]}")
        return pd.DataFrame(columns=["code", "name", "market", "close", "marcap", "shares"])
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[col["name"]].astype(str).str.strip() if "name" in col else "",
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "close": pd.to_numeric(d[col["close"]], errors="coerce") if "close" in col else np.nan,
        "marcap": pd.to_numeric(d[col["marcap"]], errors="coerce") if "marcap" in col else np.nan,
        "shares": pd.to_numeric(d[col["stocks"]], errors="coerce") if "stocks" in col else np.nan,
    }).dropna(subset=["code"]).drop_duplicates("code")
    need = t["shares"].isna() & t["marcap"].notna() & (t["close"] > 0)
    if need.any():
        t.loc[need, "shares"] = t.loc[need, "marcap"] / t.loc[need, "close"]
    LOG.ok(f"[S3] 현재 상장목록 {len(t):,}건 (상장주식수 보유 {int(t['shares'].notna().sum()):,}건)")
    ncq_src("FDR상장목록", True, len(t), "현재 시점 상장주식수 — 과거 적용 시 근사")
    return t


# ── D2. 가격 구간 실측 ──────────────────────────────────────────────────────────────────────
def ncq_listing_intervals_from_prices(px_daily: pd.DataFrame, panel_start, panel_end
                                      ) -> pd.DataFrame:
    """일봉의 첫/마지막 거래일로 상장·폐지 구간을 복원한다.

    ★ 이것이 명단 결손의 최후 방어선이다. 폐지원장에 없는 종목도, 상장일 컬럼이 없는 종목도
      '언제부터 언제까지 실제로 거래됐는가'는 가격 데이터가 알고 있다.
    ★ 주의: 데이터 수집 시작일에 붙어 있는 first_trade 는 '상장일'이 아니라 '수집 시작일'이다.
      이걸 상장일로 쓰면 기존 상장사 전부가 신규 상장으로 둔갑해 시즈닝에 걸린다(유니버스 붕괴).
      → 수집 시작일 + 10영업일 이내면 상장일 미상(NaT)으로 둔다.
    ★ 마지막 거래일이 패널 종료보다 한참 이르면 폐지로 본다. 단, 거래정지 후 재개도 있으므로
      임계를 넉넉히(90일) 잡고, 폐지원장에 있는 종목은 원장 날짜를 우선한다.
    """
    cols = ["code", "first_trade", "last_trade", "n_days"]
    if px_daily is None or len(px_daily) == 0:
        return pd.DataFrame(columns=cols)
    p = px_daily[["code", "date"]].dropna()
    g = p.groupby("code", observed=True)["date"]
    T = pd.DataFrame({"first_trade": g.min(), "last_trade": g.max(),
                      "n_days": g.size()}).reset_index()
    ps, pe = as_ts(panel_start), as_ts(panel_end)
    edge = ps + pd.Timedelta(days=21)
    T["listing_date_est"] = T["first_trade"].where(T["first_trade"] > edge)
    T["delisting_date_est"] = (T["last_trade"] + pd.offsets.MonthEnd(1)).where(
        T["last_trade"] < pe - pd.Timedelta(days=90))
    n_l = int(T["listing_date_est"].notna().sum())
    n_d = int(T["delisting_date_est"].notna().sum())
    LOG.ok(f"[D2] 가격 구간 실측 {len(T):,}종목 — 신규상장 추정 {n_l:,}건 · 폐지 추정 {n_d:,}건")
    ncq_src("가격구간실측", True, len(T), "명단 결손의 최후 방어선(상장·폐지 구간을 데이터에서 복원)")
    return T


def ncq_enrich_security_master(sec: pd.DataFrame, px_daily: pd.DataFrame,
                               dead: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """종목 마스터에 상장일·폐지일·상장주식수를 다중소스로 채운다(생존자편향 제거의 완성).

    우선순위: 폐지원장(D1) > 기존 마스터 값 > 가격 구간 실측(D2)
    ★ 절대 규칙: 어떤 소스로도 근거를 못 찾은 종목을 **버리지 않는다.** 버리는 순간 그게
      생존자편향이다. 근거가 없으면 상장일=가격 첫 거래일, 폐지일=NaT 로 두어 유니버스에 남긴다.
    """
    if sec is None or sec.empty:
        return sec
    s = sec.copy()
    for c in ("listing_date", "delisting_date"):
        if c not in s.columns:
            s[c] = pd.NaT
        s[c] = as_ts_series(s[c])
    if "shares_master" not in s.columns:
        s["shares_master"] = np.nan

    if dead is not None and len(dead):
        d = dead.drop_duplicates("code").set_index("code")
        idx = s["code"].to_numpy()
        for col_src, col_dst in (("listing_date", "listing_date"),
                                 ("delisting_date", "delisting_date"),
                                 ("shares_listing", "shares_master")):
            if col_src not in d.columns:
                continue
            v = d[col_src].reindex(idx)
            v.index = s.index
            if col_dst.endswith("_date"):
                v = as_ts_series(v)
                s[col_dst] = v.where(v.notna(), s[col_dst])
            else:
                s[col_dst] = pd.to_numeric(v, errors="coerce").where(
                    pd.to_numeric(v, errors="coerce").notna(), s[col_dst])

    T = ncq_listing_intervals_from_prices(px_daily, BACKTEST_START, BACKTEST_END)
    if len(T):
        t = T.set_index("code")
        idx = s["code"].to_numpy()
        ld_est = as_ts_series(t["listing_date_est"].reindex(idx)); ld_est.index = s.index
        dd_est = as_ts_series(t["delisting_date_est"].reindex(idx)); dd_est.index = s.index
        first = as_ts_series(t["first_trade"].reindex(idx)); first.index = s.index
        n_fill_l = int((s["listing_date"].isna() & ld_est.notna()).sum())
        n_fill_d = int((s["delisting_date"].isna() & dd_est.notna()).sum())
        s["listing_date"] = s["listing_date"].where(s["listing_date"].notna(), ld_est)
        s["delisting_date"] = s["delisting_date"].where(s["delisting_date"].notna(), dd_est)
        # 그래도 상장일이 없으면 '첫 거래일'로 최소한의 근거를 부여한다(행을 버리지 않기 위함).
        still = s["listing_date"].isna() & first.notna()
        s.loc[still, "listing_date"] = first[still]
        LOG.info(f"[D2] 상장일 {n_fill_l:,}건 · 폐지일 {n_fill_d:,}건을 가격 구간으로 보강, "
                 f"근거 없던 {int(still.sum()):,}종목에 첫 거래일을 상장일로 부여(유니버스 유지).")

    n_no = int(s["listing_date"].isna().sum())
    n_del = int(s["delisting_date"].notna().sum())
    LOG.table([["종목 마스터 전체", f"{len(s):,}"],
               ["상장일 확보", f"{len(s)-n_no:,} ({100*(len(s)-n_no)/max(len(s),1):.0f}%)"],
               ["폐지일 확보", f"{n_del:,} ({100*n_del/max(len(s),1):.0f}%)"],
               ["근거 부족(유지)", f"{n_no:,}"]],
              ["항목", "값"], ["l", "r"],
              title="생존자편향 방어 상태 (근거가 없어도 종목을 버리지 않습니다)")
    if n_del < 500:
        LOG.warn(f"폐지 종목이 {n_del:,}건입니다. 10년 구간이면 통상 1,000건 이상이어야 합니다. "
                 f"생존자편향이 그만큼 남아 있으니 결과 해석 시 반드시 감안하세요.")
        PIPE.note("WARN: 폐지 표본 부족 — 생존자편향 완전 제거 미달")
    manifest_put("survivorship", {"n_codes": int(len(s)), "n_delisted": n_del,
                                  "n_no_listing_date": n_no})
    return s


# ── S1. DART 주식총수현황 = PIT 상장주식수 ──────────────────────────────────────────────────
DART_SHARES_URL = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
NCQ_DART_SHARES_MAX_CALLS = 12000        # 일 20,000 한도 안에서 안전 마진
_NCQ_DART_CALLS = {"n": 0}


def _ncq_dart_shares_one(job: Tuple[str, int, str]) -> Optional[List[dict]]:
    corp, year, rc = job
    js = http_json(DART_SHARES_URL, source="dart", tries=2,
                   params={"crtfc_key": DART_API_KEY, "corp_code": corp,
                           "bsns_year": str(year), "reprt_code": rc})
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st == "020":
        LOG.warn("DART 일일 호출한도(020)에 도달했습니다 — 여기까지 받은 주식수 이력을 저장하고 "
                 "나머지는 근사 경로로 대체합니다. 내일 재실행하면 정확히 이어받습니다.")
        return "LIMIT"                                   # type: ignore[return-value]
    if st != "000":
        return None
    rows = []
    for it in (js.get("list") or []):
        se = str(it.get("se", ""))
        # '합계' 행만 쓴다. 보통주/우선주 행을 모두 더하면 이중계상이 된다.
        if "합계" not in se:
            continue
        v = re.sub(r"[^\d]", "", str(it.get("istc_totqy") or it.get("isu_stock_totqy") or ""))
        if not v:
            continue
        rcept = str(it.get("rcept_no") or "")
        kd = rcept[:8] if len(rcept) >= 8 else f"{year+1}0401"
        rows.append({"corp_code": corp, "shares": float(v),
                     "knowledge_date": kd, "bsns_year": year, "reprt_code": rc})
    return rows or None


def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int],
                      max_calls: int = NCQ_DART_SHARES_MAX_CALLS) -> pd.DataFrame:
    """DART 주식총수현황으로 PIT 상장주식수 이력을 만든다(KRX 무관).

    ★ knowledge_date = 접수일자(rcept_no 앞 8자리). 결산일이 아니다. 결산일을 쓰면
      아직 공시되지 않은 주식수를 그 시점에 알았다고 주장하는 것이라 명백한 미래누수다.
    ★ 호출량이 크므로 ① 공용 캐시 재활용 ② 우선순위 순서 ③ 상한 을 모두 적용한다.
    """
    cols = ["corp_code", "shares", "knowledge_date", "bsns_year", "reprt_code"]
    if not DART_API_KEY:
        ncq_src("DART주식총수", False, 0, "DART_API_KEY 미입력 — 시가총액이 근사 경로로 낮아집니다")
        LOG.warn("DART_API_KEY 가 없어 PIT 상장주식수를 만들 수 없습니다. 시가총액은 "
                 "'현재 주식수 × 과거 종가' 근사가 되며, 증자가 잦은 소형주에서 오차가 큽니다. "
                 "무료·즉시 발급이므로 넣어 두시길 권합니다: https://opendart.fss.or.kr")
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("dart_shares_history", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        have = set(zip(c["corp_code"].astype(str), c["bsns_year"].astype(int),
                       c["reprt_code"].astype(str)))
        frames.append(c)
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(c):,}행 재사용 ({len(have):,} 조합)")

    jobs = [(str(c), int(y), "11011") for y in sorted(years, reverse=True)
            for c in corp_codes if (str(c), int(y), "11011") not in have]
    if RUN_MODE == "CACHED":
        jobs = []
    if len(jobs) > max_calls:
        LOG.warn(f"DART 주식총수 요청 대상이 {len(jobs):,}건이라 상한 {max_calls:,}건으로 자릅니다. "
                 f"최근 연도·우선순위 종목부터 받았으므로, 재실행하면 나머지를 이어받습니다. "
                 f"이번 실행에서 못 받은 구간은 근사 경로로 대체되고 감사표에 표시됩니다.")
        jobs = jobs[:max_calls]

    new_rows: List[dict] = []
    if jobs:
        LOG.info(f"DART 주식총수현황 {len(jobs):,}건 수집 (PIT 상장주식수 — 시가총액의 분모)")
        stop = False
        CH = 500
        for k0 in range(0, len(jobs), CH):
            if stop:
                break
            chunk = jobs[k0:k0 + CH]
            res = pmap_io(_ncq_dart_shares_one, chunk, workers=min(N_WORKERS_IO, 8),
                          desc=f"DART 주식수 {k0//CH+1}/{(len(jobs)-1)//CH+1}")
            for r in res:
                if r == "LIMIT":
                    stop = True
                    continue
                if r:
                    new_rows.extend(r)
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        ncq_src("DART주식총수", False, 0, "수집 실패")
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["corp_code", "bsns_year", "reprt_code"], keep="last")
    if new_rows:
        VAULT.put_table("dart_shares_history", S, scope="shared", domain="universe",
                        source="opendart:stockTotqySttus",
                        extra={"note": "PIT 상장주식수(접수일자 기준) — 전 전략 공용"})
    LOG.ok(f"[S1] DART 주식총수 {len(S):,}행 · {S['corp_code'].nunique():,}개 법인 (진짜 PIT)")
    ncq_src("DART주식총수", True, len(S), "접수일자 기준 PIT 상장주식수 — KRX 무관")
    return S


def ncq_build_shares_history(sec: pd.DataFrame, dart_shares: pd.DataFrame,
                             listing_now: pd.DataFrame) -> pd.DataFrame:
    """PIT 상장주식수 이력을 하나의 긴 테이블로 통합한다.

    반환: [code, knowledge_date, shares, shares_src]  — merge_asof(backward) 용
    """
    out: List[pd.DataFrame] = []
    c2corp = {}
    if sec is not None and len(sec) and "corp_code" in sec.columns:
        c2corp = (sec.dropna(subset=["corp_code"])
                     .drop_duplicates("code").set_index("corp_code")["code"].to_dict())

    if dart_shares is not None and len(dart_shares) and c2corp:
        d = dart_shares.copy()
        d["code"] = d["corp_code"].astype(str).map(c2corp)
        d = d.dropna(subset=["code"])
        d["knowledge_date"] = as_ts_series(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"])
        d["shares_src"] = "dart_pit"
        out.append(d[["code", "knowledge_date", "shares", "shares_src"]])

    # 폐지 종목: 상장주식수를 생애 상수로 사용(그 종목의 마지막 알려진 값)
    if sec is not None and len(sec) and "shares_master" in sec.columns:
        m = sec.dropna(subset=["shares_master"])[["code", "listing_date", "shares_master"]].copy()
        if len(m):
            m["knowledge_date"] = as_ts_series(m["listing_date"]).fillna(as_ts("1990-01-01"))
            m = m.rename(columns={"shares_master": "shares"})
            m["shares_src"] = "delist_registry"
            out.append(m[["code", "knowledge_date", "shares", "shares_src"]])

    # 현재 상장목록: 아주 이른 시점에 놓아 '최후 폴백'이 되게 한다(근사임을 라벨로 남김)
    if listing_now is not None and len(listing_now):
        n = listing_now.dropna(subset=["shares"])[["code", "shares"]].copy()
        if len(n):
            n["knowledge_date"] = as_ts("1990-01-01")
            n["shares_src"] = "approx_const_shares"
            out.append(n[["code", "knowledge_date", "shares", "shares_src"]])

    if not out:
        return pd.DataFrame(columns=["code", "knowledge_date", "shares", "shares_src"])
    S = pd.concat(out, ignore_index=True)
    S["shares"] = pd.to_numeric(S["shares"], errors="coerce")
    # 시간 해상도를 ns 로 못박는다(merge_asof 의 dtype 일치 요구 — ncq_ns 주석 참조)
    S["knowledge_date"] = pd.to_datetime(S["knowledge_date"], errors="coerce")
    try:
        S["knowledge_date"] = S["knowledge_date"].astype("datetime64[ns]")
    except Exception:
        pass
    S["code"] = S["code"].astype(str)
    S = S[(S["shares"] > 0)].dropna(subset=["code", "knowledge_date"])
    # 같은 (code, knowledge_date) 가 여러 소스에서 오면 PIT 소스를 우선한다.
    pri = {"dart_pit": 0, "delist_registry": 1, "approx_const_shares": 2}
    S["_p"] = S["shares_src"].map(pri).fillna(9)
    S = (S.sort_values(["code", "knowledge_date", "_p"])
           .drop_duplicates(["code", "knowledge_date"], keep="first")
           .drop(columns=["_p"])
           .sort_values("knowledge_date", kind="stable")
           .reset_index(drop=True))
    mix = Counter(S["shares_src"])
    LOG.table([[k, f"{v:,}", {"dart_pit": "진짜 PIT (접수일자 기준)",
                              "delist_registry": "폐지원장 상장주식수(생애 상수)",
                              "approx_const_shares": "현재 주식수(과거 적용 시 근사)"}.get(k, "")]
               for k, v in mix.most_common()],
              ["주식수 소스", "행수", "성질"], ["l", "r", "l"],
              title="PIT 상장주식수 소스 구성 — 시가총액의 분모")
    return S


def ncq_report_sources():
    """소스 가용성 감사표 — '무엇이 살아 있고 무엇이 죽었는지'를 한 화면에."""
    if not NCQ_SOURCE_STATUS:
        return
    LOG.banner("데이터 소스 가용성 감사",
               "KRX 차단을 정상 상황으로 간주합니다. KRX 항목이 전부 꺼져 있어도 결과는 성립합니다.")
    rows = []
    for s in NCQ_SOURCE_STATUS.values():
        rows.append([s["name"], "KRX" if s["krx"] else "KRX-free",
                     "✔ 가용" if s["ok"] else "✘ 불가",
                     f"{s['n']:,}" if s["n"] >= 0 else "—", _trunc(s["note"], 52)])
    LOG.table(rows, ["소스", "계열", "상태", "건수", "역할 / 비고"], ["l", "c", "c", "r", "l"])
    krxfree_ok = [s for s in NCQ_SOURCE_STATUS.values() if s["ok"] and not s["krx"]]
    if not krxfree_ok:
        LOG.error("KRX-free 소스가 하나도 살아 있지 않습니다. 이 상태에서는 PIT 유니버스를 "
                  "구성할 수 없으므로 결과가 무효입니다. 네트워크에서 "
                  "raw.githubusercontent.com / finance.naver.com / opendart.fss.or.kr "
                  "접근이 가능한지 먼저 확인하세요.")
    manifest_put("source_status", {k: {"ok": v["ok"], "n": v["n"]}
                                   for k, v in NCQ_SOURCE_STATUS.items()})


# ============================================================================================
# 조립 블록 13: ncq_10_universe.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 0 — PIT 월간 유니버스 (시총 하위 N + 유동성)                                        ║
# ║                                                                                          ║
# ║  입력 : sec(종목마스터) · px_daily(일봉) · pxm(월말 패널) · Universe(상장/폐지 기반 멤버십) ║
# ║  출력 : MCAP(code,month,mcap,shares,mcap_src) · UNI(month,code,...,in_uni,liq_pass,excl)   ║
# ║  실패 : 예외를 던지지 않고 '무엇을 못 구했는지'를 감사표로 노출한 뒤 폴백 경로로 계속한다.  ║
# ║                                                                                          ║
# ║  ★ 이 전략의 성패는 "하위 1000" 경계의 PIT 정확도에 달려 있다. 현재 시총으로 과거를 자르면 ║
# ║    그 자체가 미래누수다(지금 대형주인 종목이 2016년엔 소형주였다). 그래서 시가총액은        ║
# ║    ① KRX 월말 스냅샷(pykrx, 상장주식수 포함) 을 1순위로 쓰고,                              ║
# ║    ② 실패 시 '현재 주식수 × 과거 종가' 근사로 낮추되 그 사실을 감사표와 매니페스트에 남긴다.║
# ║    ②는 유상증자·액면분할이 잦은 소형주에서 오차가 크다 — 숨기지 않고 표기한다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 명세 §5.1-3: "상장 후 6개월 미만" 제외. TCD 코어의 기본값(250거래일 ≈ 1년)보다 완화된 기준이라
# Universe 를 만들기 전에 전역을 바꿔 둔다. (Universe.__init__ 이 이 값을 읽어 시즈닝을 확정한다)
LISTING_SEASONING_DAYS = 120

MCAP_COLS = ["code", "month", "close", "mcap", "shares", "mcap_src"]
UNI_COLS = ["month", "code", "mcap", "adv20", "mcap_rank", "in_uni", "liq_pass", "excl"]

# 제외 사유 라벨 — 퍼널 표에서 그대로 쓰인다
EXCL_NONE = ""
EXCL_PREF = "우선주"
EXCL_SPAC = "스팩"
EXCL_REIT = "리츠"
EXCL_NEW = "상장6개월미만"
EXCL_HALT = "거래정지추정"
EXCL_NOMCAP = "시총결측"
EXCL_ETF = "ETF/ETN/펀드"

_PREF_NAME_RE = re.compile(r"(우[BC]?|우선주)$")
_SPAC_RE = re.compile(r"(스팩|기업인수목적)")
_REIT_RE = re.compile(r"(리츠|부동산투자회사|리얼티)")
_FUND_RE = re.compile(r"(ETN|ETF|レ|인버스|레버리지|선물|KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE )")


def ncq_ns(s) -> pd.Series:
    """어떤 시간 해상도로 들어오든 datetime64[ns] 로 통일한다.

    ★ pandas 2.x 는 해상도를 값에서 추론한다: pd.Timestamp("1990-01-01") 를 대입하면
      datetime64[s], pd.to_datetime(...) 는 datetime64[ns] 가 되기 쉽다. 두 계열이 섞이면
      merge_asof / 비교 연산이 조용히 실패하거나 엉뚱한 예외를 던진다. 경계에서 못박는다.
    """
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    try:
        return out.astype("datetime64[ns]")
    except Exception:
        return out


def ncq_is_preferred(code: str, name: str) -> bool:
    """우선주 판정. 코드 끝자리(5/7/9)와 종목명을 **둘 다** 본다.

    ★ 2024-01 종목코드 개편으로 영숫자 코드가 도입되어 '끝자리 숫자' 규칙만으로는 오탐이 난다.
      그래서 '앞 5자리가 숫자이고 6번째가 5/7/9' 인 고전 형식일 때만 코드 규칙을 적용하고,
      나머지는 종목명 규칙에 맡긴다.
    """
    c = str(code or "")
    n = str(name or "").strip()
    if _PREF_NAME_RE.search(n):
        return True
    if len(c) == 6 and c[:5].isdigit() and c[5] in ("5", "7", "9"):
        # 보통주 중에도 6번째가 0인 것이 원칙이므로 5/7/9 는 우선주 계열로 본다.
        return True
    return False


def ncq_static_exclusion(sec: pd.DataFrame) -> pd.DataFrame:
    """종목 단위 정적 제외 사유(우선주/스팩/리츠/ETF)를 한 번에 계산한다."""
    d = sec[["code", "name", "industry"]].copy() if len(sec) else \
        pd.DataFrame(columns=["code", "name", "industry"])
    if d.empty:
        d["excl_static"] = pd.Series(dtype=object)
        return d
    d["name"] = d["name"].astype(str).fillna("")
    d["industry"] = d["industry"].astype(str).fillna("")
    ex = np.full(len(d), EXCL_NONE, dtype=object)
    nm, ind, cd = d["name"].to_numpy(), d["industry"].to_numpy(), d["code"].astype(str).to_numpy()
    for i in range(len(d)):
        if _SPAC_RE.search(nm[i]):
            ex[i] = EXCL_SPAC
        elif _REIT_RE.search(nm[i]) or _REIT_RE.search(ind[i]):
            ex[i] = EXCL_REIT
        elif _FUND_RE.search(nm[i]):
            ex[i] = EXCL_ETF
        elif ncq_is_preferred(cd[i], nm[i]):
            ex[i] = EXCL_PREF
    d["excl_static"] = ex
    n_ex = int((d["excl_static"] != EXCL_NONE).sum())
    LOG.info(f"정적 제외 대상 {n_ex:,}종목 — " +
             ", ".join(f"{k}×{v:,}" for k, v in
                       Counter(d.loc[d['excl_static'] != EXCL_NONE, 'excl_static']).most_common()))
    return d[["code", "excl_static"]]


# ── 시가총액 (PIT) ──────────────────────────────────────────────────────────────────────────
def _ncq_mcap_from_pykrx(month_ends: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """(선택) KRX 월말 스냅샷 — 시가총액·상장주식수의 '그 시점 값'.

    ⚠ KRX 차단 환경에서는 호출되지 않는다(ncq_krx_enabled() 가 False). 이 함수는 **보강**이지
      의존 대상이 아니다. KRX 없이도 DART PIT 주식수 × 수정종가로 시가총액이 완성된다.
    ★ 전부 KRXG 게이트를 통해 직렬 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), JSON 대신 로그인 HTML 을 받아 대량 실패한다.
    ★ 1회 호출이 전 종목을 돌려주므로 120개월이면 120회면 끝난다. 종목별 루프 금지.
    """
    if not ncq_krx_enabled():
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    if pykrx_stock is None or not month_ends:
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    if not KRXG.warmup():
        LOG.info("KRX 세션이 없어 월말 시가총액 스냅샷을 건너뜁니다 — 근사 경로로 폴백합니다.")
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])

    rows: List[pd.DataFrame] = []
    bad_streak = 0
    for m in tqdm(list(month_ends), desc="KRX 월말 시가총액", ncols=88, leave=False):
        bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                       m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
        d = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market="ALL")
        if d is None or len(d) == 0:
            bad_streak += 1
            if bad_streak >= 5:
                LOG.warn("KRX 시가총액 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 "
                         "상태입니다. 수집을 중단하고 근사 경로로 폴백합니다(정상 폴백).")
                break
            continue
        bad_streak = 0
        t = d.reset_index()
        ren = {"티커": "code", "종가": "close", "시가총액": "mcap", "상장주식수": "shares"}
        t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
        if "code" not in t.columns:
            t = t.rename(columns={t.columns[0]: "code"})
        for c in ("close", "mcap", "shares"):
            if c not in t.columns:
                t[c] = np.nan
        t["code"] = t["code"].map(to_code6)
        t["date"] = m
        rows.append(t[["date", "code", "close", "mcap", "shares"]].dropna(subset=["code"]))
    if not rows:
        return pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
    out = pd.concat(rows, ignore_index=True)
    LOG.ok(f"KRX 월말 시가총액 스냅샷 {out['date'].nunique()}개월 × 평균 "
           f"{len(out)/max(out['date'].nunique(),1):,.0f}종목 확보 (진짜 PIT 경로)")
    return out


def ncq_month_end_close(px_daily: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 수정종가 패널 [code, month, close]. 시가총액의 '분자'."""
    if px_daily is None or len(px_daily) == 0:
        return pd.DataFrame(columns=["code", "month", "close"])
    p = px_daily[["code", "date", "close"]].dropna(subset=["date", "close"]).copy()
    p["month"] = as_ts_series(p["date"]) + pd.offsets.MonthEnd(0)
    out = (p.sort_values("date").groupby(["code", "month"], observed=True)
             .tail(1)[["code", "month", "close"]])
    return out[out["month"].isin(months)].reset_index(drop=True)


def ncq_shares_asof(px_m: pd.DataFrame, shares_hist: pd.DataFrame) -> pd.DataFrame:
    """월말 시점에 '알 수 있었던' 상장주식수를 as-of 결합한다 (C1 과 동일한 의미론).

    ★ merge_asof(direction="backward") 는 knowledge_date <= month 인 마지막 행만 붙인다.
      결산일이 아니라 **접수일자**를 knowledge_date 로 썼기 때문에, 아직 공시되지 않은
      주식수가 과거 시점으로 새어 들어오지 않는다.
    ★ by="code" 결합키가 결측이면 merge_asof 가 다루지 못하므로 유효 행만 결합하고
      나머지는 NaN 으로 되붙인다. 행을 버리면 그게 곧 생존자편향이다.
    """
    if px_m is None or px_m.empty:
        return pd.DataFrame(columns=["code", "month", "close", "shares", "shares_src"])
    L = px_m.dropna(subset=["code", "month"]).copy()
    if shares_hist is None or len(shares_hist) == 0:
        L["shares"] = np.nan
        L["shares_src"] = ""
        return L
    R = shares_hist.dropna(subset=["code", "knowledge_date"]).copy()
    # ★★ merge_asof 는 좌·우 키의 **dtype 이 정확히 같아야** 한다. pandas 2.x 는 스칼라
    #    Timestamp 로 만든 컬럼을 datetime64[s] 로, to_datetime 결과를 datetime64[ns] 로
    #    만들기 때문에 두 경로가 섞이면 MergeError 가 난다. 예외 메시지가 "keys must be
    #    sorted" 류라 정렬 문제로 오인하기 딱 좋다 — 실제로 그렇게 한 시간을 날린 버그다.
    #    양쪽을 ns 로 못박고, 카테고리 dtype 인 code 도 문자열로 통일한다.
    R["code"] = R["code"].astype(str)
    L["code"] = L["code"].astype(str)
    R["knowledge_date"] = ncq_ns(R["knowledge_date"])
    L["month"] = ncq_ns(L["month"])
    L = L.sort_values("month", kind="stable")
    R = R.sort_values("knowledge_date", kind="stable")
    try:
        M = pd.merge_asof(L, R[["code", "knowledge_date", "shares", "shares_src"]],
                          left_on="month", right_on="knowledge_date",
                          by="code", direction="backward")
    except Exception as e:                                        # noqa
        LOG.warn(f"상장주식수 as-of 결합 실패({type(e).__name__}: {e}) — 시가총액을 만들 수 "
                 f"없습니다. 좌={L['month'].dtype} 우={R['knowledge_date'].dtype} "
                 f"(두 dtype 이 다르면 merge_asof 는 정렬 오류처럼 보이는 예외를 냅니다).")
        L["shares"] = np.nan
        L["shares_src"] = ""
        return L
    M = M.drop(columns=[c for c in ("knowledge_date",) if c in M.columns])
    M["shares_src"] = M["shares_src"].fillna("")
    return M


def build_marketcap_panel(codes: Sequence[str], months: pd.DatetimeIndex,
                          px_daily: pd.DataFrame, sec: pd.DataFrame,
                          shares_hist: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """PIT 월말 시가총액 패널. 공용 인덱스에 캐시하여 다른 전략도 그대로 재사용한다.

    시가총액 = PIT 상장주식수(DART 접수일자 기준) × 그 시점 수정종가.
    KRX 월말 스냅샷이 있으면(선택) 그 값을 우선하고, 없으면 위 식으로 만든다.

    반환: MCAP[code, month, close, mcap, shares, mcap_src]
    """
    cached = VAULT.get_table("krx_marketcap_monthly", scope="shared")
    have_dates: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        # 과거 버전이 'month' 로 저장했을 수도 있다. 둘 다 없으면 이 캐시는 쓸 수 없다.
        _dc = "date" if "date" in c.columns else ("month" if "month" in c.columns else None)
        if _dc is None:
            LOG.warn("시가총액 캐시에 날짜 컬럼이 없습니다 — 이 캐시는 건너뜁니다(원본 보존).")
            c = pd.DataFrame(columns=["date", "code", "close", "mcap", "shares"])
        else:
            c["date"] = as_ts_series(c[_dc])
        for _c in ("close", "mcap", "shares"):
            if _c not in c.columns:
                c[_c] = np.nan
        c = c.dropna(subset=["date", "code"])
        have_dates = set(c["date"].dt.strftime("%Y-%m"))
        frames.append(c[["date", "code", "close", "mcap", "shares"]])
        LOG.info(f"공용 캐시에서 월말 시가총액 {len(c):,}행 재사용 ({len(have_dates)}개월)")

    todo = [m for m in months if m.strftime("%Y-%m") not in have_dates]
    if RUN_MODE == "CACHED" and todo:
        LOG.warn(f"CACHED 모드 — 미수집 {len(todo)}개월의 시가총액 스냅샷을 건너뜁니다.")
        todo = []
    new = _ncq_mcap_from_pykrx(todo) if todo else pd.DataFrame(
        columns=["date", "code", "close", "mcap", "shares"])
    if len(new):
        frames.append(new)
        out = pd.concat(frames, ignore_index=True)
        out = out.dropna(subset=["date", "code"]).drop_duplicates(["date", "code"], keep="last")
        save = out.copy()
        save["date"] = as_ts_series(save["date"]).dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_monthly", save, scope="shared", domain="universe",
                        source="pykrx:get_market_cap_by_ticker",
                        extra={"note": "월말 시가총액·상장주식수 — 전 전략 공용 PIT 입력"})

    M = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "code", "close", "mcap", "shares"])
    if len(M):
        M["date"] = as_ts_series(M["date"])
        M = M.dropna(subset=["date", "code"]).drop_duplicates(["date", "code"], keep="last")
        M["month"] = M["date"] + pd.offsets.MonthEnd(0)
        M = M[["code", "month", "close", "mcap", "shares"]]
        M["mcap_src"] = "krx_snapshot"
    else:
        M = pd.DataFrame(columns=MCAP_COLS)

    # ── KRX-free 주 경로: PIT 상장주식수 × 월말 수정종가 ──────────────────────────────────
    px_m = ncq_month_end_close(px_daily, months)
    if len(px_m):
        base = ncq_shares_asof(px_m, shares_hist)
        if len(M):
            # 스냅샷이 이미 채운 (code, month) 는 그대로 둔다(그 시점 관측이 더 정확하다).
            key_have = set(zip(M["code"].astype(str), M["month"].values))
            keep = [(c, mm) not in key_have
                    for c, mm in zip(base["code"].astype(str), base["month"].values)]
            base = base[pd.Series(keep, index=base.index)]
        base = base.dropna(subset=["shares"])
        if len(base):
            base["mcap"] = pd.to_numeric(base["close"], errors="coerce") * \
                pd.to_numeric(base["shares"], errors="coerce")
            base["mcap_src"] = base["shares_src"].replace("", "unknown")
            M = pd.concat([M, base[MCAP_COLS]], ignore_index=True)

    if M.empty:
        LOG.error("시가총액을 한 행도 만들지 못했습니다. 'KRX 스냅샷'도 '주식수 폴백'도 실패했습니다. "
                  "하위 N 유니버스를 구성할 수 없으므로 이 상태의 결과는 무효입니다.")
        return pd.DataFrame(columns=MCAP_COLS)

    M = M.dropna(subset=["code", "month"]).drop_duplicates(["code", "month"], keep="first")
    M = M[M["month"].isin(months)]
    M["mcap"] = pd.to_numeric(M["mcap"], errors="coerce")
    M = M[M["mcap"] > 0]

    _MCAP_SRC_DESC = {
        "krx_snapshot": "KRX 월말 스냅샷 — 그 시점 주식수 (진짜 PIT)",
        "dart_pit": "DART 주식총수현황 — 접수일자 기준 (진짜 PIT · KRX 무관)",
        "delist_registry": "폐지원장 상장주식수 — 그 종목 생애 상수로 사용",
        "approx_const_shares": "근사 — 현재 주식수 × 과거 종가 (증자·분할 미반영)",
    }
    cnt = Counter(M["mcap_src"])
    tot = max(len(M), 1)
    LOG.table([[k, f"{v:,}", f"{100*v/tot:.1f}%", _MCAP_SRC_DESC.get(k, "미상")]
               for k, v in cnt.most_common()],
              ["시총 소스", "행수", "비중", "성질"], ["l", "r", "r", "l"],
              title="시가총액 소스 감사 — 근사 비중이 크면 '하위 N' 경계가 그만큼 흐려집니다")
    manifest_put("mcap_source_mix", {k: int(v) for k, v in cnt.items()})
    pit_share = (cnt.get("krx_snapshot", 0) + cnt.get("dart_pit", 0)) / tot
    approx = cnt.get("approx_const_shares", 0) / tot
    manifest_put("mcap_pit_share", round(float(pit_share), 4))
    if approx > 0.5:
        LOG.warn(f"시가총액의 {100*approx:.0f}% 가 근사 경로(현재 주식수 × 과거 종가)입니다. "
                 f"유상증자가 잦은 소형주 구간이라 '하위 {NCQ_UNIVERSE_BOTTOM_N}' 경계가 흔들립니다.\n"
                 f"    개선 순서: ① DART_API_KEY 입력(무료·즉시, KRX 무관 — 가장 효과적)\n"
                 f"               ② 차단이 풀렸다면 NCQ_USE_KRX=True + KRX ID/PW")
        PIPE.note("WARN: 시가총액 근사 비중 과다")
    else:
        LOG.ok(f"시가총액의 {100*pit_share:.0f}% 가 진짜 PIT 경로입니다.")
    PIPE.io("OUT", "MEM", "marketcap_monthly", M, source="pykrx+fdr")
    return downcast(M)


# ── 유니버스 ────────────────────────────────────────────────────────────────────────────────
def build_ncq_universe(months: pd.DatetimeIndex, pxm: pd.DataFrame, mcap: pd.DataFrame,
                       uni_obj: "Universe", sec: pd.DataFrame,
                       bottom_n: Optional[int] = None,
                       min_adv: Optional[float] = None) -> pd.DataFrame:
    """월말 기준 PIT 유니버스. 명세 §5.1 의 제외조건 → 시총 오름차순 하위 N → 유동성 필터.

    ★ 제외된 종목을 **버리지 않고** excl 사유와 함께 전부 남긴다. 그래야 퍼널에서 어느 게이트가
      표본을 붕괴시켰는지 보인다. in_uni / liq_pass 두 불리언으로 단계를 구분한다.
    """
    bottom_n = int(bottom_n or NCQ_UNIVERSE_BOTTOM_N)
    min_adv = float(min_adv if min_adv is not None else NCQ_MIN_ADV)

    # ① 상장/폐지 기반 PIT 멤버십 (상장폐지 종목 포함 — 생존자편향 방지)
    parts = []
    for m in months:
        cs = uni_obj.at(m)
        if cs:
            parts.append(pd.DataFrame({"month": m, "code": cs}))
        uni_obj.audit_row("전체상장", m, cs)
    if not parts:
        LOG.error("PIT 멤버십이 비었습니다 — 상장일·폐지일 소스를 확보하지 못했습니다.")
        return pd.DataFrame(columns=UNI_COLS)
    U = pd.concat(parts, ignore_index=True)

    # ② 시총·유동성 결합
    if mcap is not None and len(mcap):
        U = U.merge(mcap[["code", "month", "mcap"]], on=["code", "month"], how="left")
    else:
        U["mcap"] = np.nan
    if pxm is not None and len(pxm):
        U = U.merge(pxm[["code", "month", "adv20"]], on=["code", "month"], how="left")
    else:
        U["adv20"] = np.nan

    # ③ 정적 제외 (우선주/스팩/리츠/ETF)
    st = ncq_static_exclusion(sec)
    U = U.merge(st, on="code", how="left")
    U["excl"] = U["excl_static"].fillna(EXCL_NONE)
    U = U.drop(columns=["excl_static"])

    # ④ 상장 6개월 미만 — Universe 의 시즈닝(120거래일)이 1차 방어, 여기서 달력 기준 2차 확인
    # ★ sec 에 같은 코드가 두 번 있으면 reindex 가 InvalidIndexError 로 죽는다. 먼저 유일화한다.
    _sec1 = sec.drop_duplicates("code") if (sec is not None and len(sec)) else pd.DataFrame(
        columns=["code", "listing_date"])
    ld = (_sec1.set_index("code")["listing_date"] if "listing_date" in _sec1.columns
          else pd.Series(dtype="datetime64[ns]"))
    ld = as_ts_series(ld.reindex(U["code"].to_numpy())).to_numpy()
    too_new = (~pd.isna(ld)) & (U["month"].to_numpy() < (ld + np.timedelta64(182, "D")))
    U.loc[(U["excl"] == EXCL_NONE) & too_new, "excl"] = EXCL_NEW

    # ⑤ 거래정지 추정 — 그 달 거래대금이 0/결측이면 체결 자체가 불가능하다.
    #    관리종목·투자주의환기종목 지정 이력은 PIT 확보가 어려워 대용 지표를 쓴다(한계로 명시).
    halted = (~(U["adv20"] > 0)) & U["adv20"].notna()
    U.loc[(U["excl"] == EXCL_NONE) & halted, "excl"] = EXCL_HALT
    U.loc[(U["excl"] == EXCL_NONE) & U["mcap"].isna(), "excl"] = EXCL_NOMCAP

    # ⑥ 시총 오름차순 하위 N
    elig = U["excl"] == EXCL_NONE
    U["mcap_rank"] = np.nan
    U.loc[elig, "mcap_rank"] = (U.loc[elig].groupby("month", observed=True)["mcap"]
                                .rank(method="first", ascending=True))
    U["in_uni"] = elig & (U["mcap_rank"] <= bottom_n)
    U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= min_adv)

    for m, g in U.groupby("month", observed=True):
        uni_obj.audit_row("PIT유니버스", m, g.loc[g["in_uni"], "code"].tolist())
        uni_obj.audit_row("유동성필터", m, g.loc[g["liq_pass"], "code"].tolist())

    n_uni = int(U["in_uni"].sum())
    n_liq = int(U["liq_pass"].sum())
    n_m = max(U["month"].nunique(), 1)
    LOG.ok(f"PIT 유니버스 구성 완료 — 월평균 상장 {len(U)/n_m:,.0f}종목 → "
           f"하위 {bottom_n} {n_uni/n_m:,.0f}종목 → 유동성(ADV≥{min_adv/1e8:.1f}억) "
           f"{n_liq/n_m:,.0f}종목")
    if n_liq / n_m < 50:
        LOG.warn(f"유동성 통과 종목이 월평균 {n_liq/n_m:,.0f}개뿐입니다. 하위 소형주 구간이라 "
                 f"당연한 결과일 수 있으나, 이벤트 표본이 그만큼 줄어 검정력이 낮아집니다. "
                 f"NCQ_MIN_ADV 민감도(5천만/1억/3억)를 반드시 함께 보세요.")
    manifest_put("universe_monthly_avg", {"listed": round(len(U)/n_m, 1),
                                          "bottom_n": round(n_uni/n_m, 1),
                                          "liquid": round(n_liq/n_m, 1)})
    PIPE.io("OUT", "MEM", "ncq_universe", U, source="PIT membership + mcap + adv")
    return downcast(U[UNI_COLS])


def universe_funnel(UNI: pd.DataFrame, EV: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """명세 §5.2 필수 산출물 — 월별 3단 퍼널 (유니버스 → 유동성통과 → 신규커버리지 이벤트)."""
    if UNI is None or UNI.empty:
        return pd.DataFrame(columns=["month", "listed", "in_uni", "liq_pass", "events"])
    g = UNI.groupby("month", observed=True)
    F = pd.DataFrame({
        "listed": g["code"].size(),
        "in_uni": g["in_uni"].sum(),
        "liq_pass": g["liq_pass"].sum(),
    }).reset_index()
    if EV is not None and len(EV):
        ev = EV.groupby("month", observed=True)["code"].nunique().rename("events").reset_index()
        F = F.merge(ev, on="month", how="left")
    else:
        F["events"] = np.nan
    F["events"] = F["events"].fillna(0).astype(int)
    F["conv_uni"] = F["in_uni"] / F["listed"].replace(0, np.nan)
    F["conv_liq"] = F["liq_pass"] / F["in_uni"].replace(0, np.nan)
    F["conv_ev"] = F["events"] / F["liq_pass"].replace(0, np.nan)
    return F


# ============================================================================================
# 조립 블록 14: ncq_20_index.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 1 — 리포트 인덱스 전수 수집 · 원장 병합 · 커버리지 완결성 진단                      ║
# ║                                                                                          ║
# ║  입력 : sec(종목마스터) · months · 드라이브 공용 캐시(research_report_master)               ║
# ║  출력 : REP(보고서 원장) · diag(완결성 진단표) · valid_start(유효 백테스트 시작월)          ║
# ║  실패 : 소스 하나가 죽어도 나머지로 계속한다. 전부 죽으면 캐시만으로 진행하고 그 사실을 명시.║
# ║                                                                                          ║
# ║  ★ 본문이 아니라 **메타데이터만** 받는다. 본문(PDF)은 Phase 3 에서 '이벤트로 판정된 건'만   ║
# ║    받는다. 이 순서가 이 전략의 비용 구조 전체를 결정한다(수만 건 → 수천 건).                ║
# ║  ★ 수집은 **최신 → 과거 역순**(명세 §6.2). 예산 초과로 중단돼도 최근 구간이 살아 있어야     ║
# ║    열화 L3(윈도우 축소)를 바로 적용할 수 있다. 과거부터 받으면 중단 시 전략이 무효가 된다.  ║
# ║  ★ 유니버스로 먼저 자르지 않는다(명세 §1.3). 시총 상위였다가 하위로 내려온 종목의 과거      ║
# ║    커버리지 이력이 사라지면 '가짜 신규 커버리지'가 대량 발생한다.                           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 한국IR협의회 — 기업리서치·기술분석보고서. 기업 신청/사업 기반이라 자발적 커버리지가 아니다.
# → is_sponsored=True 로 태깅하고 이벤트 서브그룹을 분리한다(명세 §7.2).
IRS_HOSTS = [
    "https://www.kirs.or.kr",
    "https://kirs.or.kr",
    "https://www.irsolution.or.kr",
    "https://irsolution.or.kr",
]
IRS_LIST_PATHS = [
    "/information/tech1.html",       # 기술분석보고서
    "/information/tech2.html",
    "/information/research1.html",   # 기업리서치
    "/board/list.html",
]


class NcqCircuit:
    """소스별 서킷 브레이커 (명세 §3.4).

    연속 실패 5회 → 60초 대기 후 '축소 모드'로 재시도 → 다시 5회 실패 → 영구 스킵.
    ★ 예외를 던지지 않는다. open() 이 True 면 호출측이 그 소스를 조용히 건너뛰되 로그는 남는다.
    """

    def __init__(self, name: str, threshold: int = 5, cooldown: float = 60.0):
        self.name, self.threshold, self.cooldown = name, threshold, cooldown
        self.fails = 0
        self.trips = 0
        self.dead = False

    def ok(self):
        self.fails = 0

    def fail(self) -> bool:
        """True 를 돌려주면 '이 소스는 이제 끝'이라는 뜻."""
        self.fails += 1
        if self.fails < self.threshold:
            return self.dead
        self.trips += 1
        self.fails = 0
        if self.trips == 1:
            LOG.warn(f"[{self.name}] 연속 {self.threshold}회 실패 — 서킷 브레이커 발동. "
                     f"{self.cooldown:.0f}초 대기 후 축소 모드(워커 2)로 재시도합니다.")
            time.sleep(self.cooldown)
            globals()["N_WORKERS_RESEARCH"] = 2
        else:
            self.dead = True
            LOG.error(f"[{self.name}] 재차 {self.threshold}회 실패 — 이 소스를 영구 스킵합니다. "
                      f"수집된 분량까지는 그대로 사용하고, 결손은 완결성 진단에 반영됩니다.")
            manifest_note(f"소스 영구 스킵: {self.name}")
        return self.dead


# ── IR협의회 ────────────────────────────────────────────────────────────────────────────────
_IRS_DATE_RE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_IRS_ENDPOINT_CACHE: Dict[str, Any] = {"url": None, "probed": False}


def ncq_irs_probe() -> Optional[str]:
    """IR협의회 리스트 엔드포인트를 한 번만 탐색한다. 못 찾으면 None(정상 스킵)."""
    if _IRS_ENDPOINT_CACHE["probed"]:
        return _IRS_ENDPOINT_CACHE["url"]
    _IRS_ENDPOINT_CACHE["probed"] = True
    for host in IRS_HOSTS:
        for path in IRS_LIST_PATHS:
            url = host + path
            html = http_get(url, source="irs", tries=1, timeout=20, referer=host + "/")
            if not html or len(html) < 800:
                continue
            s = soup_of(html)
            if s is None:
                continue
            # 표 안에 날짜 + PDF 링크(또는 상세 링크)가 함께 있으면 리스트 페이지로 본다
            if s.find("table") is not None and _IRS_DATE_RE.search(html):
                _IRS_ENDPOINT_CACHE["url"] = url
                LOG.ok(f"IR협의회 리스트 엔드포인트 확인: {url}")
                return url
    LOG.info("IR협의회 리스트 페이지를 찾지 못했습니다 — 이 소스는 건너뜁니다. "
             "명세상 IRS 는 스폰서 리포트(비자발적 커버리지)이므로, 없어도 주가설 H1 은 "
             "'ORGANIC_ONLY' 로 그대로 검정됩니다.")
    return None


def ncq_irs_collect(start: str, end: str, max_pages: int = 40) -> pd.DataFrame:
    """IR협의회 인덱스 수집(베스트에포트). 실패는 예외가 아니라 빈 DataFrame 이다."""
    base = ncq_irs_probe()
    if not base:
        return pd.DataFrame(columns=REPORT_COLS)
    lo, hi = as_ts(start), as_ts(end)
    rows: List[dict] = []
    for page in range(1, max_pages + 1):
        html = http_get(base, source="irs", tries=2, timeout=25, referer=base,
                        params={"page": page, "pageIndex": page,
                                "sdate": lo.strftime("%Y-%m-%d"), "edate": hi.strftime("%Y-%m-%d")})
        if not html:
            break
        s = soup_of(html)
        if s is None:
            break
        got = 0
        for tr in s.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            txt = " ".join(_clean_cell(td.get_text(" ")) for td in tds)
            m = _IRS_DATE_RE.search(txt)
            if not m:
                continue
            d = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            dt = as_ts(d)
            if dt is None or dt < lo or dt > hi:
                continue
            a = tr.find("a", href=True)
            href = urljoin(base, a["href"]) if a is not None else None
            title = _clean_cell(a.get_text(" ")) if a is not None else \
                _clean_cell(tds[1].get_text(" "))
            pdf = None
            for aa in tr.find_all("a", href=True):
                if ".pdf" in aa["href"].lower() or "download" in aa["href"].lower():
                    pdf = urljoin(base, aa["href"])
                    break
            name = _clean_cell(tds[0].get_text(" "))
            if len(name) > 20 or not name:
                name = name_from_title(title)
            rid = sha1_str("irs", href or title, d)[:16]
            rows.append({
                "source": "irs", "src_report_id": rid, "category": "company",
                "pub_date": d, "title": title,
                "stock_code": code_from_title(title),
                "stock_name": name,
                "broker_raw": "한국IR협의회", "analyst_raw": "",
                "target_price": None, "opinion": None,
                "pdf_url": pdf, "detail_url": href, "views": None,
            })
            got += 1
        if got == 0:
            break
    d = pd.DataFrame(rows)
    if len(d):
        d = d.drop_duplicates("src_report_id")
        LOG.ok(f"IR협의회 {len(d):,}건 (스폰서 리포트로 태깅됩니다)")
    return d if len(d) else pd.DataFrame(columns=REPORT_COLS)


# ── 세션 지속성 (_done.jsonl) ───────────────────────────────────────────────────────────────
def ncq_done_path(phase: str) -> str:
    p = os.path.join(VAULT.ns["private"], "index", f"ncq_{phase}_done.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def ncq_done_load(phase: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for r in read_jsonl(ncq_done_path(phase)):
        k = str(r.get("key", ""))
        if k:
            out[k] = r
    return out


def ncq_done_mark(phase: str, key: str, **info):
    append_jsonl(ncq_done_path(phase), [{"key": key, "at": _dt.datetime.now().isoformat(
        timespec="seconds"), **info}])


# ── 월 단위 역순 수집 ───────────────────────────────────────────────────────────────────────
_SOURCE_FN = {
    "naver": lambda s, e: naver_collect(s, e, cats=("company",)),
    "hankyung": lambda s, e: hankyung_collect(s, e),
    "irs": lambda s, e: ncq_irs_collect(s, e),
}


def ncq_collect_source_by_month(source: str, months: pd.DatetimeIndex,
                                budget: "PhaseBudget") -> pd.DataFrame:
    """한 소스를 **최신 → 과거 역순**으로 월 단위 수집한다. 월 1개 = 청크 1개.

    · 이미 처리한 월은 _done.jsonl 로 건너뛴다(재실행 시 이어받기).
    · 청크마다 연도별 parquet 으로 공용 인덱스에 저장한다(단일 거대 parquet 금지).
    · 예산 초과 시 예외 없이 루프를 정상 종료하고 부분 결과를 돌려준다.
    """
    fn = _SOURCE_FN.get(source)
    if fn is None:
        return pd.DataFrame(columns=REPORT_COLS)
    done = ncq_done_load(f"p1_{source}")
    cb = NcqCircuit(source)
    frames: List[pd.DataFrame] = []
    n_skip = n_new = 0

    todo = [m for m in reversed(list(months))]
    bar = tqdm(todo, desc=f"P1 {source}", ncols=88, leave=False)
    for m in bar:
        ym = m.strftime("%Y-%m")
        if ym in done:
            n_skip += 1
            continue
        if cb.dead:
            break
        if not budget.check():
            LOG.warn(f"[P1/{source}] 예산 소진 — {ym} 이전 구간은 수집하지 않습니다. "
                     f"최신 구간부터 받았으므로 확보된 구간만으로 백테스트가 가능합니다.")
            break
        s = m.replace(day=1).strftime("%Y-%m-%d")      # 그 달 1일
        e = m.strftime("%Y-%m-%d")                     # 그 달 말일 (month_end 이므로 그대로)
        try:
            d = fn(s, e)
        except Exception as ex:                                  # noqa
            LOG.debug(f"[{source}] {ym} 수집 예외 {type(ex).__name__}: {ex}")
            d = None
        if d is None or len(d) == 0:
            if cb.fail():
                break
            ncq_done_mark(f"p1_{source}", ym, n=0, note="empty")
            continue
        cb.ok()
        d = d.copy()
        d["_ym"] = ym
        frames.append(d)
        n_new += len(d)
        ncq_done_mark(f"p1_{source}", ym, n=int(len(d)))
        # 연 단위 샤딩 저장 (공용 — 다른 전략도 그대로 재사용)
        if m.month == 1 or m == todo[-1] or len(frames) % 12 == 0:
            _ncq_flush_index_shard(source, frames)
    try:
        bar.close()
    except Exception:
        pass
    _ncq_flush_index_shard(source, frames, final=True)
    LOG.ok(f"[P1/{source}] 신규 {n_new:,}건 · 캐시 스킵 {n_skip}개월 · "
           f"소요 {budget.elapsed()/60:.1f}분")
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    return pd.concat(frames, ignore_index=True)


def _ncq_flush_index_shard(source: str, frames: List[pd.DataFrame], final: bool = False):
    """연도별 샤드로 공용 인덱스에 저장. 기존 샤드와 합집합 병합(정보를 버리지 않는다)."""
    if not frames:
        return
    d = pd.concat(frames, ignore_index=True)
    if "pub_date" not in d.columns:
        return
    yr = as_ts_series(d["pub_date"]).dt.year
    for y, g in d.groupby(yr):
        if not np.isfinite(y):
            continue
        name = f"report_index_{source}_{int(y)}"
        old = VAULT.get_table(name, scope="shared")
        merged = g
        if old is not None and len(old):
            cols = list(dict.fromkeys(list(old.columns) + list(g.columns)))
            merged = pd.concat([old.reindex(columns=cols), g.reindex(columns=cols)],
                               ignore_index=True)
            if "src_report_id" in merged.columns:
                merged = merged.drop_duplicates(["source", "src_report_id"], keep="last")
        VAULT.put_table(name, merged, scope="shared", domain="research",
                        source=f"{source} index shard",
                        extra={"note": "리포트 인덱스 연도 샤드 — 전 전략 공용"})
    if final:
        VAULT.flush("shared")


def ncq_load_cached_index() -> List[pd.DataFrame]:
    """드라이브 공용 인덱스에 이미 있는 리포트 원장/샤드를 전부 끌어온다.

    ★ 사용자의 기존 캐시(다른 전략이 만든 research_report_master 포함)를 **적극 재활용**한다.
      이게 있으면 네트워크가 막혀도 백테스트가 성립한다.
    """
    out: List[pd.DataFrame] = []
    master = VAULT.get_table("research_report_master", scope="shared")
    if master is not None and len(master):
        LOG.ok(f"공용 캐시 재활용 — 보고서 원장 {len(master):,}건 "
               f"(다른 전략이 수집한 것도 그대로 씁니다)")
        out.append(master)
    idx = VAULT.load_index("shared")
    if idx is not None and len(idx) and "key" in idx.columns:
        shard_keys = sorted({str(k) for k in idx["key"].astype(str)
                             if k.startswith("report_index_")})
        for k in shard_keys:
            d = VAULT.get_table(k, scope="shared")
            if d is not None and len(d):
                out.append(d)
        if shard_keys:
            LOG.info(f"공용 캐시 연도 샤드 {len(shard_keys)}개 재활용")
    return out


# ── 통합 수집 ───────────────────────────────────────────────────────────────────────────────
def collect_report_index(months: pd.DatetimeIndex, sec: pd.DataFrame) -> pd.DataFrame:
    """Phase 1 전체. 캐시 우선 → 부족분만 신규 수집 → 다중소스 병합 → 공용/전용 인덱스 저장."""
    frames = ncq_load_cached_index()
    n_cached = int(sum(len(f) for f in frames))

    if RESEARCH_COLLECT and RUN_MODE != "CACHED":
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도(소스별 QPS 상한·워커 4 이하)로 제한합니다. "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        with PhaseBudget("P1", NCQ_PHASE_BUDGET_S["P1"], on_exceed="L3") as B:
            for src in list(RESEARCH_SOURCES):
                if not B.check():
                    break
                d = ncq_collect_source_by_month(src, months, B)
                if d is not None and len(d):
                    frames.append(d)
    else:
        LOG.info(f"신규 수집을 하지 않습니다 (RUN_MODE={RUN_MODE}, "
                 f"RESEARCH_COLLECT={RESEARCH_COLLECT}) — 캐시만 사용합니다.")

    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.error("리포트를 한 건도 확보하지 못했습니다. 캐시도 비어 있고 신규 수집도 실패했습니다. "
                  "이 상태에서는 신규 커버리지 이벤트가 정의될 수 없으므로 백테스트를 진행하지 않습니다.")
        return pd.DataFrame(columns=REPORT_COLS)

    REP = build_report_master(frames, sec)
    if REP.empty:
        return REP

    # 스폰서 태깅 — 병합 후 source 는 "naver+hankyung" 같은 합성 토큰이 될 수 있다.
    src_s = REP["source"].astype(str)
    REP["is_sponsored"] = src_s.str.contains("irs", case=False, na=False)

    # 매핑 실패율 (명세 §6.3 — 실패 건을 버리지 않고 결손율로 노출)
    n_all = len(REP)
    n_nocode = int(REP["stock_code"].isna().sum())
    fail_rate = n_nocode / max(n_all, 1)
    manifest_put("ticker_map_fail_rate", round(fail_rate, 4))
    manifest_put("report_index_total", int(n_all))
    manifest_put("report_index_cached_reused", int(n_cached))
    if fail_rate > NCQ_MAP_FAIL_WARN_FRAC:
        LOG.warn(f"종목명→티커 매핑 실패율 {100*fail_rate:.1f}% (> {100*NCQ_MAP_FAIL_WARN_FRAC:.0f}%). "
                 f"사명 변경 이력이 반영되지 않은 구간이 있을 수 있습니다. 실패 건은 버리지 않고 "
                 f"ticker=NULL 로 보존되며, 커버리지 이력에서 빠지므로 '가짜 신규'를 만들 수 있습니다.")
    else:
        LOG.ok(f"종목명→티커 매핑 실패율 {100*fail_rate:.2f}% ({n_nocode:,}/{n_all:,}건)")

    VAULT.put_table("research_report_master", REP, scope="shared", domain="research",
                    source="+".join(RESEARCH_SOURCES))
    VAULT.put_table(f"report_index_{STRATEGY_ID}", REP, scope="private", domain="research",
                    source="strategy view")
    VAULT.flush()
    PIPE.io("OUT", "DRIVE", "research_report_master", REP, source="naver+hankyung+irs")
    return REP


# ── 커버리지 완결성 진단 (명세 §6.4 — 이 전략의 생사를 가름) ────────────────────────────────
def coverage_completeness(REP: pd.DataFrame, months: pd.DatetimeIndex
                          ) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """월별 리포트 건수의 계단형 하락을 아카이브 결손으로 판정하고, 유효 백테스트 시작월을 정한다.

    판정 규칙(§6.4-3): 특정 월의 총 건수가 **직후 12개월 중앙값의 40% 미만**이면 결손.
    확정 규칙(§6.4-4): **연속 3개월 이상 결손인 구간 이전은 백테스트 시작점에서 배제**한다.

    ★ '직후 12개월'을 쓰는 이유: 과거로 갈수록 아카이브가 얕아지는 것이 결손의 전형적 형태라,
      직전 구간과 비교하면 결손이 결손을 정상으로 만들어 버린다. 미래 방향 기준선이 필요하다.
      이 기준선은 **진단 전용**이며 신호 산출에는 절대 쓰이지 않는다(누수 아님).
    """
    cols = ["month", "n_reports", "n_codes", "n_brokers", "base12", "ratio", "archive_incomplete"]
    if REP is None or REP.empty:
        LOG.error("보고서 원장이 비어 완결성 진단을 할 수 없습니다.")
        return pd.DataFrame(columns=cols), as_ts(BACKTEST_START)

    r = REP.copy()
    r["month"] = as_ts_series(r["pub_date"]) + pd.offsets.MonthEnd(0)
    r = r.dropna(subset=["month"])
    g = r.groupby("month", observed=True)
    D = pd.DataFrame({
        "n_reports": g["report_uid"].nunique(),
        "n_codes": g["stock_code"].nunique(),
        "n_brokers": g["broker_id"].nunique(),
    }).reindex(months).fillna(0).reset_index().rename(columns={"index": "month"})
    if "month" not in D.columns:
        D = D.rename(columns={D.columns[0]: "month"})

    n = D["n_reports"].to_numpy(dtype=float)
    base = np.full(len(n), np.nan)
    for i in range(len(n)):
        fut = n[i + 1: i + 13]
        if len(fut) >= 6:
            base[i] = float(np.median(fut))
    D["base12"] = base
    D["ratio"] = np.where(np.isfinite(base) & (base > 0), n / base, np.nan)
    D["archive_incomplete"] = np.isfinite(D["ratio"]) & (D["ratio"] < NCQ_ARCHIVE_DEFICIT_FRAC)

    # 연속 결손 구간 탐지 → 마지막 결손 런의 끝 다음 달이 유효 시작월
    flags = D["archive_incomplete"].to_numpy()
    valid_idx = 0
    runs = []
    i = 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            if (j - i + 1) >= NCQ_ARCHIVE_RUN_MONTHS:
                runs.append((i, j))
                valid_idx = max(valid_idx, j + 1)
            i = j + 1
        else:
            i += 1

    valid_idx = min(valid_idx, len(D) - 1) if len(D) else 0
    valid_start = as_ts(D["month"].iloc[valid_idx]) if len(D) else as_ts(BACKTEST_START)

    n_bad = int(flags.sum())
    LOG.banner("커버리지 완결성 진단 (§6.4)",
               "아카이브 결손 = 가짜 신규 커버리지의 최대 원인. 이 진단이 유일한 방어선이다.")
    LOG.info(f"결손 판정 월 {n_bad}/{len(D)}개 · 연속 {NCQ_ARCHIVE_RUN_MONTHS}개월 이상 결손 구간 "
             f"{len(runs)}개")
    for a, b in runs[:8]:
        LOG.warn(f"  결손 구간: {D['month'].iloc[a]:%Y-%m} ~ {D['month'].iloc[b]:%Y-%m} "
                 f"({b-a+1}개월, 직후12M 중앙값 대비 "
                 f"{100*np.nanmean(D['ratio'].iloc[a:b+1]):.0f}%)")
    yrs = (as_ts(BACKTEST_END) - valid_start).days / 365.25
    LOG.ok(f"유효 백테스트 시작월 확정: {valid_start:%Y-%m} → 유효 윈도우 {yrs:.1f}년")
    manifest_put("archive_incomplete_months", int(n_bad))
    manifest_put("archive_deficit_runs", [[str(D['month'].iloc[a].date()),
                                           str(D['month'].iloc[b].date())] for a, b in runs])
    manifest_put("valid_backtest_start", str(valid_start.date()))
    manifest_put("valid_backtest_years", round(float(yrs), 2))

    if yrs < NCQ_MIN_VALID_YEARS:
        LOG.error(f"유효 윈도우가 {yrs:.1f}년으로 최소 기준 {NCQ_MIN_VALID_YEARS:.0f}년 미만입니다. "
                  f"명세 §15-2 에 따라 백테스트를 진행하지 않고 사용자 판단을 요청합니다. "
                  f"원인은 대개 네이버 리서치의 과거 페이지네이션 깊이 제한입니다. "
                  f"드라이브 캐시에 과거 리포트를 더 확보하거나, IR협의회 단독 + 짧은 윈도우로 "
                  f"재설계해야 합니다.")
    VAULT.put_table(f"coverage_diagnostics_{STRATEGY_ID}", D, scope="private",
                    domain="diagnostics", source="coverage_completeness")
    PIPE.io("OUT", "MEM", "coverage_diagnostics", D)
    return D, valid_start


# ============================================================================================
# 조립 블록 15: ncq_30_coverage.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 2 — 신규 커버리지 판정 (H1 de novo / H2 broker-new) · 스폰서 분리                   ║
# ║                                                                                          ║
# ║  입력 : REP(보고서 원장) · UNI(PIT 유니버스) · valid_start(완결성 진단 결과)                ║
# ║  출력 : EV[month,code,event_type,n_reports,n_brokers,sources,broker_ids,                  ║
# ║           sponsor_group,report_uids,first_broker,analyst_new]                             ║
# ║  실패 : 이벤트가 0건이면 예외가 아니라 '왜 0건인지'(어느 게이트에서 죽었는지)를 표로 낸다.  ║
# ║                                                                                          ║
# ║  ★ 이 단계가 비용 구조의 분기점이다. 여기서 수만 건이 수천 건으로 압축되고, Phase 3 는      ║
# ║    그 수천 건의 PDF 만 받는다. 판정이 헐거우면 PDF 비용이 폭발하고, 빡빡하면 표본이 죽는다. ║
# ║  ★ 브로커 합병은 PIT 로 다룬다. 합병 후 ID 로 과거를 소급 통합하면 '신규'가 조용히 사라진다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EV_COLS = ["month", "code", "event_type", "n_reports", "n_brokers", "sources", "broker_ids",
           "sponsor_group", "report_uids", "first_broker", "analyst_new", "is_denovo"]

# 실제 '합병'(서로 다른 두 법인의 결합)만 PIT 로 분리한다. 단순 사명변경은 동일 법인이므로
# 소급 통합이 오히려 정확하다(같은 브로커가 커버리지를 이어간 것).
#   (합병 후 정식명, 합병 전 별칭 정규식, 합병 전 표시명, 발효일)
NCQ_BROKER_MERGERS: List[Tuple[str, str, str, str]] = [
    ("미래에셋증권", r"(대우증권|KDB대우|KDB\s*대우)", "대우증권", "2016-12-29"),
    ("KB증권",       r"현대증권",                        "현대증권", "2017-01-01"),
    ("NH투자증권",   r"(우리투자증권|NH농협증권)",       "우리투자증권", "2014-12-31"),
    ("유안타증권",   r"동양증권",                        "동양증권", "2014-10-01"),
]
_NCQ_MERGE_RE = [(post, re.compile(pat), pre, as_ts(eff))
                 for post, pat, pre, eff in NCQ_BROKER_MERGERS]


def ncq_pit_broker_id(broker_raw: Any, pub_date: Any) -> Tuple[str, str]:
    """PIT 브로커 ID. 합병 발효일 **이전** 리포트는 합병 전 법인 ID 를 유지한다.

    ★ 왜 필요한가: 대우증권이 2015년에 A사를 커버했고 미래에셋이 2018년에 A사를 처음 커버했다면,
      2018년은 '미래에셋 입장에서 신규'다. 그런데 두 법인을 하나로 소급 통합하면 2015년 커버리지가
      미래에셋의 것으로 계상되어 2018년 이벤트가 사라진다. 반대로 사명만 바뀐 경우(하나금투→
      하나증권)는 같은 법인이므로 통합이 맞다. 이 둘을 구분하지 않으면 이벤트 수가 조용히 틀어진다.
    """
    bid, canon = normalize_broker(broker_raw)
    if not canon:
        return ("", "")
    t = as_ts(pub_date)
    if t is None:
        return (bid, canon)
    raw = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(broker_raw or "")))
    for post, rx, pre, eff in _NCQ_MERGE_RE:
        if canon == post and eff is not None and t < eff and rx.search(raw):
            return (sha1_str("broker", pre)[:12], pre)
    return (bid, canon)


def _ncq_mi(months_like) -> pd.Series:
    """월 인덱스(연*12+월)를 정수로. 개월 차이를 뺄셈 한 번으로 구하기 위한 표준화."""
    t = as_ts_series(months_like)
    return (t.dt.year.astype("float") * 12 + t.dt.month.astype("float"))


def build_coverage_events(REP: pd.DataFrame, UNI: pd.DataFrame, months: pd.DatetimeIndex,
                          valid_start: Optional[pd.Timestamp] = None,
                          lookback_m: Optional[int] = None,
                          burnin_m: Optional[int] = None,
                          links: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """신규 커버리지 이벤트 원장.

    H1 (주 정의) denovo(i,t) : [t-L, t) 에 **어떤 브로커의 리포트도 없음** AND 월 t 에 ≥1건
    H2 (부 정의) broker_new  : [t-L, t) 에 **브로커 b 의 리포트 없음**   AND 월 t 에 b 의 리포트 ≥1건

    ★ 커버리지 이력 판정에는 유니버스 필터를 걸지 않는다(명세 §1.3). 유니버스는 마지막에
      '이벤트를 신호로 채택할지'에만 적용한다. 먼저 자르면 과거 커버리지가 소실되어
      가짜 신규가 대량 발생한다.
    """
    L = int(lookback_m or NCQ_LOOKBACK_M)
    B = int(burnin_m or NCQ_BURNIN_M)
    if REP is None or REP.empty:
        LOG.error("보고서 원장이 비어 신규 커버리지를 판정할 수 없습니다.")
        return pd.DataFrame(columns=EV_COLS)

    r = REP.copy()
    r["code"] = r["stock_code"].map(to_code6)
    n_all = len(r)
    r = r.dropna(subset=["code"])
    n_code = len(r)
    r["pub_date"] = as_ts_series(r["pub_date"])
    r = r.dropna(subset=["pub_date"])
    r["month"] = r["pub_date"] + pd.offsets.MonthEnd(0)
    r["mi"] = _ncq_mi(r["month"])

    # PIT 브로커 ID 재계산 (원장의 broker_id 는 비-PIT 통합본이라 그대로 쓰면 안 된다)
    pit = [ncq_pit_broker_id(b, d) for b, d in zip(r["broker_raw"].fillna(r.get("broker_name", "")),
                                                   r["pub_date"])]
    r["pit_broker_id"] = [p[0] for p in pit]
    r["pit_broker_name"] = [p[1] for p in pit]
    n_nobroker = int((r["pit_broker_id"].astype(str) == "").sum())
    if n_nobroker:
        # 브로커를 알 수 없는 건은 H2 판정에서 제외하되 H1(종목 단위)에는 남긴다.
        LOG.warn(f"증권사를 식별하지 못한 리포트 {n_nobroker:,}건 — H2(브로커 단위) 판정에서만 "
                 f"제외하고 H1(종목 단위)에는 포함합니다.")
    if "is_sponsored" not in r.columns:
        r["is_sponsored"] = r["source"].astype(str).str.contains("irs", case=False, na=False)

    # ── H1: 종목 단위 de novo ─────────────────────────────────────────────────────────────
    cm = (r.groupby(["code", "mi"], observed=True)
            .agg(n_reports=("report_uid", "nunique"))
            .reset_index()
            .sort_values(["code", "mi"]))
    cm["prev_mi"] = cm.groupby("code", observed=True)["mi"].shift(1)
    cm["gap"] = cm["mi"] - cm["prev_mi"]
    cm["is_denovo"] = cm["prev_mi"].isna() | (cm["gap"] > L)

    # ── H2: (종목, 브로커) 단위 신규 ──────────────────────────────────────────────────────
    rb = r[r["pit_broker_id"].astype(str) != ""]
    if len(rb):
        cb = (rb.groupby(["code", "pit_broker_id", "mi"], observed=True)
                .size().rename("n").reset_index()
                .sort_values(["code", "pit_broker_id", "mi"]))
        cb["prev_mi"] = cb.groupby(["code", "pit_broker_id"], observed=True)["mi"].shift(1)
        cb["gap"] = cb["mi"] - cb["prev_mi"]
        cb["broker_new"] = cb["prev_mi"].isna() | (cb["gap"] > L)
        bn = (cb[cb["broker_new"]].groupby(["code", "mi"], observed=True)
                .agg(n_new_brokers=("pit_broker_id", "nunique")).reset_index())
    else:
        bn = pd.DataFrame(columns=["code", "mi", "n_new_brokers"])

    E = cm.merge(bn, on=["code", "mi"], how="left")
    E["n_new_brokers"] = E["n_new_brokers"].fillna(0).astype(int)
    E = E[E["is_denovo"] | (E["n_new_brokers"] > 0)].copy()
    E["event_type"] = np.where(E["is_denovo"], "H1", "H2")

    # ── 월 단위 부가정보 결합 ─────────────────────────────────────────────────────────────
    meta = (r.groupby(["code", "mi"], observed=True)
             .agg(n_brokers=("pit_broker_id", lambda s: int(pd.Series(s).astype(str)
                                                            .replace("", np.nan).nunique())),
                  sources=("source", lambda s: "+".join(sorted({t for v in s
                                                                for t in str(v).split("+") if t}))),
                  broker_ids=("pit_broker_id", lambda s: "|".join(sorted({str(v) for v in s if v}))),
                  first_broker=("pit_broker_name", lambda s: sorted({str(v) for v in s if v})[:1]),
                  report_uids=("report_uid", lambda s: "|".join(sorted(map(str, set(s))))[:4000]),
                  n_sponsored=("is_sponsored", "sum"),
                  n_tot=("is_sponsored", "size"))
             .reset_index())
    meta["first_broker"] = meta["first_broker"].map(lambda x: x[0] if isinstance(x, list) and x else "")
    E = E.merge(meta, on=["code", "mi"], how="left")

    # 스폰서 그룹 (명세 §7.2)
    ns, nt = E["n_sponsored"].fillna(0).to_numpy(), E["n_tot"].fillna(0).to_numpy()
    grp = np.where(nt <= 0, "UNKNOWN",
                   np.where(ns >= nt, "SPONSORED_ONLY",
                            np.where(ns <= 0, "ORGANIC_ONLY", "MIXED")))
    E["sponsor_group"] = grp

    # 애널리스트 단위 신규 (보조 지표 — PDF/리스트에서 애널리스트를 식별한 부분집합에서만)
    E["analyst_new"] = np.nan
    if links is not None and len(links):
        try:
            E = _ncq_attach_analyst_new(E, links, L)
        except Exception as e:                                    # noqa
            LOG.warn(f"애널리스트 단위 보조 판정을 건너뜁니다({type(e).__name__}) — "
                     f"주 판정(H1/H2)에는 영향 없습니다.")

    # ── 월 복원 · burn-in · 유니버스 게이트 ───────────────────────────────────────────────
    # mi = y*12 + m 이므로 단순 나머지 연산은 12월에서 0 이 된다. -1 보정 후 복원한다.
    yy = ((E["mi"] - 1) // 12).astype(int)
    mm = (E["mi"] - yy * 12).astype(int)
    E["month"] = pd.to_datetime(dict(year=yy, month=mm, day=1), errors="coerce") + \
        pd.offsets.MonthEnd(0)
    E = E.dropna(subset=["month"])

    n_before_gate = len(E)
    vs = as_ts(valid_start) if valid_start is not None else as_ts(BACKTEST_START)
    burn_end = (vs + pd.DateOffset(months=max(L, B))) + pd.offsets.MonthEnd(0)
    E = E[E["month"] >= burn_end]
    n_after_burn = len(E)

    E = E[E["month"].isin(months)]
    n_after_win = len(E)

    if UNI is not None and len(UNI):
        u = UNI[["month", "code", "in_uni", "liq_pass", "mcap", "adv20"]]
        E = E.merge(u, on=["month", "code"], how="left")
        E["in_uni"] = E["in_uni"].fillna(False).astype(bool)
        E["liq_pass"] = E["liq_pass"].fillna(False).astype(bool)
        n_uni = int(E["in_uni"].sum())
        E = E[E["liq_pass"]]
    else:
        n_uni = len(E)
        E["in_uni"] = True
        E["liq_pass"] = True

    LOG.table([["리포트 원장 전체", f"{n_all:,}"],
               ["종목코드 매핑 성공", f"{n_code:,}"],
               ["(종목,월) 관측", f"{len(cm):,}"],
               [f"신규 커버리지 후보 (L={L}M)", f"{n_before_gate:,}"],
               [f"burn-in {max(L,B)}M 통과 (≥{burn_end:%Y-%m})", f"{n_after_burn:,}"],
               ["백테스트 윈도우 내", f"{n_after_win:,}"],
               [f"시총 하위 {NCQ_UNIVERSE_BOTTOM_N} 유니버스", f"{n_uni:,}"],
               ["유동성 필터 통과 = 최종 이벤트", f"{len(E):,}"]],
              ["게이트", "잔존"], ["l", "r"],
              title="신규 커버리지 판정 퍼널 — 어느 게이트에서 표본이 줄었는지")

    if E.empty:
        LOG.error("최종 이벤트가 0건입니다. 위 퍼널에서 어느 게이트가 원인인지 먼저 확인하세요. "
                  "가장 흔한 원인은 ① 리포트 원장의 종목코드 매핑 실패 ② 유동성 필터가 소형주를 "
                  "전부 걸러냄 ③ 아카이브 결손으로 burn-in 이 너무 늦게 끝남 입니다.")
        return pd.DataFrame(columns=EV_COLS)

    E = E.sort_values(["month", "code"]).reset_index(drop=True)
    out = E[[c for c in EV_COLS if c in E.columns] +
            [c for c in ("in_uni", "liq_pass", "mcap", "adv20", "n_new_brokers") if c in E.columns]]
    PIPE.io("OUT", "MEM", "coverage_events", out, source="H1/H2 판정")
    VAULT.put_table(f"event_log_{STRATEGY_ID}", out, scope="private", domain="events",
                    source="build_coverage_events",
                    extra={"lookback_m": L, "burnin_m": B, "valid_start": str(vs.date())})
    return out


def _ncq_attach_analyst_new(E: pd.DataFrame, links: pd.DataFrame, L: int) -> pd.DataFrame:
    """애널리스트 단위 신규 여부(보조 지표). 애널리스트를 식별한 부분집합에서만 값이 채워진다."""
    x = links.dropna(subset=["stock_code"]).copy()
    if x.empty:
        return E
    x["code"] = x["stock_code"].map(to_code6)
    x = x.dropna(subset=["code"])
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    x["mi"] = _ncq_mi(x["pub_date"] + pd.offsets.MonthEnd(0))
    a = (x.groupby(["code", "analyst_id", "mi"], observed=True).size().rename("n").reset_index()
          .sort_values(["code", "analyst_id", "mi"]))
    a["prev_mi"] = a.groupby(["code", "analyst_id"], observed=True)["mi"].shift(1)
    a["new"] = a["prev_mi"].isna() | ((a["mi"] - a["prev_mi"]) > L)
    an = (a[a["new"]].groupby(["code", "mi"], observed=True)
            .agg(analyst_new=("analyst_id", "nunique")).reset_index())
    E = E.drop(columns=["analyst_new"], errors="ignore").merge(an, on=["code", "mi"], how="left")
    cov = float(E["analyst_new"].notna().mean()) if len(E) else 0.0
    LOG.info(f"애널리스트 단위 보조 판정 커버리지 {100*cov:.1f}% — 네이버 단독 건은 리스트에 "
             f"작성자가 없어 PDF 추출에 의존하므로 낮게 나오는 것이 정상입니다.")
    return E


def audit_events(EV: pd.DataFrame, REP: pd.DataFrame) -> dict:
    """이벤트 원장 감사 — 명세 §12 의 R2·R3 경고를 여기서 낸다."""
    out: Dict[str, Any] = {}
    if EV is None or EV.empty:
        LOG.warn("이벤트가 없어 감사를 수행할 수 없습니다.")
        return {"n_events": 0}
    n = len(EV)
    n_m = max(EV["month"].nunique(), 1)
    per_m = n / n_m
    grp = Counter(EV["sponsor_group"].astype(str))
    typ = Counter(EV["event_type"].astype(str))
    irs_share = (grp.get("SPONSORED_ONLY", 0) + 0.5 * grp.get("MIXED", 0)) / max(n, 1)

    LOG.table([["총 이벤트", f"{n:,}"],
               ["관측 월수", f"{n_m}"],
               ["월평균 이벤트", f"{per_m:.1f}"],
               ["H1 de novo", f"{typ.get('H1',0):,} ({100*typ.get('H1',0)/n:.0f}%)"],
               ["H2 broker-new", f"{typ.get('H2',0):,} ({100*typ.get('H2',0)/n:.0f}%)"],
               ["ORGANIC_ONLY", f"{grp.get('ORGANIC_ONLY',0):,} ({100*grp.get('ORGANIC_ONLY',0)/n:.0f}%)"],
               ["SPONSORED_ONLY", f"{grp.get('SPONSORED_ONLY',0):,} ({100*grp.get('SPONSORED_ONLY',0)/n:.0f}%)"],
               ["MIXED", f"{grp.get('MIXED',0):,} ({100*grp.get('MIXED',0)/n:.0f}%)"],
               ["고유 종목", f"{EV['code'].nunique():,}"]],
              ["항목", "값"], ["l", "r"], title="신규 커버리지 이벤트 감사")

    if per_m < NCQ_MIN_EVENTS_PER_MONTH:
        LOG.warn(f"★ 월평균 이벤트가 {per_m:.1f}건으로 기준({NCQ_MIN_EVENTS_PER_MONTH}건) 미만입니다. "
                 f"횡단면 z-score 가 불안정해지고 통계 검정력이 부족합니다. 리포트 최상단에 "
                 f"경고로 표시됩니다(명세 §5.2).")
    if n < NCQ_MIN_TOTAL_EVENTS:
        LOG.warn(f"★ 총 이벤트 {n:,}건이 기준({NCQ_MIN_TOTAL_EVENTS:,}건) 미만입니다. "
                 f"어떤 결과도 강한 결론으로 취급하지 마십시오(명세 §12 R3).")
    if irs_share > NCQ_SPONSOR_WARN_FRAC:
        LOG.warn(f"★ 스폰서(IR협의회) 비중이 {100*irs_share:.0f}% 로 기준"
                 f"({100*NCQ_SPONSOR_WARN_FRAC:.0f}%)을 넘습니다. 이 전략은 '신규 커버리지 알파'가 "
                 f"아니라 'IR 활동 팩터'일 가능성이 큽니다(명세 §12 R2). P3(ORGANIC_ONLY 유지) "
                 f"검정 결과를 헤드라인보다 우선해서 보십시오.")

    out = {"n_events": int(n), "months": int(n_m), "per_month": float(per_m),
           "type_mix": {k: int(v) for k, v in typ.items()},
           "sponsor_mix": {k: int(v) for k, v in grp.items()},
           "irs_share": float(irs_share), "n_codes": int(EV["code"].nunique())}
    manifest_put("events", out)
    return out


# ============================================================================================
# 조립 블록 16: ncq_40_text.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 3·4·5 — PDF 본문 수집 · 동결 렉시콘 스코어링 · 횡단면 상대비교                       ║
# ║                                                                                          ║
# ║  입력 : EV(이벤트) · REP(원장) · UNI · pxm                                                 ║
# ║  출력 : TXT(섹션 분할 본문) · SCORE(문서 점수) · SIG(신호 패널)                             ║
# ║  실패 : 스캔 PDF/추출 실패는 예외가 아니라 '결손율'이다. 반드시 수치로 노출한다.            ║
# ║                                                                                          ║
# ║  ★ 왜 LLM 임베딩을 1차 스코어러로 쓰지 않는가(명세 §9.1)                                    ║
# ║    사전학습 모델은 2016년 리포트를 채점할 때 이미 2024년까지를 학습한 상태다. 어떤 소형주가 ║
# ║    결국 대박이 났는지를 모델이 '알고' 있을 수 있다 — 미묘하지만 실질적인 룩어헤드다.        ║
# ║    그래서 1차 스코어러는 **수익률을 보기 전에 동결한 룰 기반 렉시콘**이다.                  ║
# ║                                                                                          ║
# ║  ⚠⚠ 렉시콘을 백테스트 수익률을 확인한 뒤에 수정하면 이 전략의 모든 결과가 무효다(§12 R5).   ║
# ║     수정이 필요하면 버전을 올리고(v2) 사전등록을 새로 써야 한다. 해시가 매니페스트에 남는다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 렉시콘 v1.0 (동결 대상) ─────────────────────────────────────────────────────────────────
NCQ_LEXICON: Dict[str, Any] = {
    "version": "v1.0",
    "frozen_at": "2026-08-08",
    "note": "수익률 확인 전에 동결. 수정 시 버전 증가 + 사전등록 재작성 필수(명세 §9.2).",
    "section_weight": {"TITLE": 3.0, "HEADLINE": 2.0, "BODY": 1.0},
    "negation_window": 30,
    "negation_markers": ["아니", "못하", "없", "어렵", "힘들"],
    "groups": {
        "A": {"weight": 3.0, "label": "구조적 전환", "terms": [
            "사업구조 전환", "사업구조전환", "사업 재편", "사업재편", "체질 개선", "체질개선",
            "턴어라운드", "흑자전환", "흑자 전환", "퀀텀점프", "퀀텀 점프",
            "신규 사업 진출", "신규사업 진출", "신사업 진출", "주력 제품 교체",
            "포트폴리오 전환", "밸류체인 진입", "밸류체인 편입", "수직계열화"]},
        "B": {"weight": 2.5, "label": "캐파·양산", "terms": [
            "증설", "신규 라인", "신규라인", "양산 개시", "양산개시", "첫 양산", "본격 양산",
            "캐파 확대", "캐파확대", "가동률 상승", "공장 준공", "설비 투자", "설비투자",
            "생산능력", "생산 능력", "라인 증설", "증설 투자"]},
        "C": {"weight": 2.0, "label": "수요·고객", "terms": [
            "신규 수주", "신규수주", "대형 수주", "대형수주", "수주 잔고", "수주잔고",
            "장기공급계약", "장기 공급 계약", "고객사 다변화", "신규 고객사", "신규 고객",
            "1차 벤더", "1차벤더", "레퍼런스 확보", "전방시장 확대", "전방 시장 확대",
            "국산화", "수입 대체", "수입대체", "진입장벽", "진입 장벽"]},
        "D": {"weight": 2.0, "label": "인증·승인", "terms": [
            "인증 획득", "인증획득", "품질 승인", "품질승인", "벤더 등록", "벤더등록",
            "특허 등록", "특허등록", "규제 통과", "승인 완료", "승인완료", "임상 진입",
            "임상 개시", "허가 획득"]},
        "H": {"weight": -1.0, "label": "헤지·불확실성", "terms": [
            "기대", "전망", "가능성", "예상", "할 것으로 보인다", "될 것으로 보인다",
            "추정", "관측", "여겨진다", "지켜볼 필요", "검토 중", "검토중",
            "계획 중", "계획중", "논의 중", "논의중", "협의 중", "협의중"]},
        "N": {"weight": -2.5, "label": "부정", "terms": [
            "지연", "차질", "부진", "둔화", "감소", "하향", "우려", "리스크",
            "불확실", "악화", "적자 전환", "적자전환"]},
    },
}

NCQ_PREREG: Dict[str, Any] = {
    "version": "v1.0",
    "frozen_at": "2026-08-08",
    "strategy": "ARC-NCQ v1.0 — New Coverage × Qualitative Shift",
    "primary_hypothesis": (
        "시총 하위 N 소형주에서 발생한 신규 애널리스트 커버리지 이벤트 중, "
        "동월 이벤트 풀 내 텍스트 z-score 상위 tercile 종목군이 "
        "동일 유니버스 동일가중(Bottom-N EW) 대비 12개월 초과수익을 낸다."),
    "hypotheses": [
        {"id": "P1", "text": "De novo 신규커버리지 × z상위tercile 포트폴리오가 Bottom-N EW 대비 초과수익",
         "stat": "월별 초과수익 평균, Newey-West t (lag=12)", "direction": ">0"},
        {"id": "P2", "text": "텍스트 z점수의 단조성: 상위 tercile − 하위 tercile 스프레드",
         "stat": "롱숏 스프레드 HAC t", "direction": ">0"},
        {"id": "P3", "text": "ORGANIC_ONLY 서브그룹에서도 P1 유지",
         "stat": "서브그룹 초과수익 HAC t", "direction": ">0"},
        {"id": "P4", "text": "텍스트 점수가 신규커버리지 이벤트 단독 대비 증분 정보 제공",
         "stat": "전체 이벤트 EW 대비 z상위 tercile 스프레드 HAC t", "direction": ">0"},
    ],
    "multiple_testing": "BH-FDR (alpha=0.10) applied to P1~P4",
    "adoption_criteria": [
        "P1 과 P3 가 BH-FDR 통과",
        "왕복 거래비용 3.0% 시나리오에서도 초과수익 > 0",
        "Placebo(z 하위 tercile) 대비 스프레드 > 0",
    ],
    "parameters": {
        "universe_bottom_n": None, "min_adv_krw": None, "lookback_months": None,
        "burnin_months": None, "hold_months": None, "tercile": None,
        "cost_roundtrip": None, "max_new_per_month": None,
    },
    "sensitivity_plan": "기본 1조합 + 각 축 단독 변동 8조합 = 9조합만 실행. DSR 시행횟수에 9 반영.",
    "kill_criteria": [
        "커버리지 완결성 진단에서 유효 윈도우 < 5년이면 백테스트 중단",
        "하네스 누수 민감도(N11) 실패 시 전 결과 무효",
    ],
}

NCQ_LEXICON_SHA = ""
NCQ_PREREG_SHA = ""
NCQ_PDF_ENGINE = "auto"          # "auto" | "fitz" | "pdfplumber"

TXT_COLS = ["report_uid", "code", "pub_date", "sec_title", "sec_headline", "sec_body",
            "n_chars", "n_pages", "extract_ok", "extract_method"]
SCORE_COLS = ["report_uid", "code", "month", "doc_raw", "doc_score", "n_chars",
              "g_A", "g_B", "g_C", "g_D", "g_H", "g_N"]
SIG_COLS = ["month", "code", "event_score", "z", "pooled", "pool_n", "rank_pct",
            "selected", "placebo", "sponsor_group", "event_type", "exec_px", "adv20", "fwd_ret"]


def _ncq_canon_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def freeze_configs(outdir: str) -> Tuple[dict, str, dict, str]:
    """렉시콘·사전등록을 JSON 으로 동결하고 SHA256 을 기록한다.

    ★ 이미 파일이 있으면 **그 파일을 정본으로 삼는다.** 코드 안의 딕셔너리로 덮어쓰지 않는다.
      한 번 동결한 뒤 코드를 수정해도 과거 실행의 정의가 바뀌지 않아야 재현성이 성립한다.
      내용이 다르면 경고를 띄우고 파일 쪽을 쓴다(사용자가 의도적으로 v2 를 만든 경우 대비).
    """
    global NCQ_LEXICON, NCQ_PREREG, NCQ_LEXICON_SHA, NCQ_PREREG_SHA
    os.makedirs(outdir, exist_ok=True)
    # 사전등록에 현재 파라미터를 박아 넣는다(무엇을 사전등록했는지 나중에 다툴 여지를 없앤다).
    prereg = json.loads(_ncq_canon_json(NCQ_PREREG))
    prereg["parameters"] = {
        "universe_bottom_n": NCQ_UNIVERSE_BOTTOM_N, "min_adv_krw": NCQ_MIN_ADV,
        "lookback_months": NCQ_LOOKBACK_M, "burnin_months": NCQ_BURNIN_M,
        "hold_months": NCQ_HOLD_MONTHS, "tercile": round(float(NCQ_TERCILE), 6),
        "cost_roundtrip": NCQ_COST_ROUNDTRIP, "max_new_per_month": NCQ_MAX_NEW_PER_MONTH,
        "backtest_window": [BACKTEST_START, BACKTEST_END], "seed": SEED,
    }

    pairs = [("lexicon_v1.json", NCQ_LEXICON, "렉시콘"), ("prereg_v1.json", prereg, "사전등록")]
    loaded: Dict[str, Any] = {}
    for fn, obj, label in pairs:
        path = os.path.join(outdir, fn)
        if os.path.exists(path):
            try:
                on_disk = json.loads(open(path, encoding="utf-8").read())
                if _ncq_canon_json(on_disk) != _ncq_canon_json(obj):
                    LOG.warn(f"{label} 파일이 코드 안의 정의와 다릅니다 — **파일 쪽을 정본으로 "
                             f"사용합니다**({fn}). 동결 원칙상 이미 고정된 정의가 우선합니다. "
                             f"의도한 변경이면 버전을 올려 새 파일로 만드세요.")
                loaded[fn] = on_disk
                continue
            except Exception as e:                                # noqa
                LOG.warn(f"{label} 파일을 읽지 못해({type(e).__name__}) 코드 정의로 새로 씁니다.")
        atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))
        loaded[fn] = obj
        LOG.ok(f"{label} 동결: {path}")

    NCQ_LEXICON = loaded["lexicon_v1.json"]
    NCQ_PREREG = loaded["prereg_v1.json"]
    NCQ_LEXICON_SHA = hashlib.sha256(_ncq_canon_json(NCQ_LEXICON).encode()).hexdigest()
    NCQ_PREREG_SHA = hashlib.sha256(_ncq_canon_json(NCQ_PREREG).encode()).hexdigest()
    _ncq_compile_lexicon()
    manifest_put("lexicon_version", NCQ_LEXICON.get("version"))
    manifest_put("lexicon_sha256", NCQ_LEXICON_SHA)
    manifest_put("prereg_version", NCQ_PREREG.get("version"))
    manifest_put("prereg_sha256", NCQ_PREREG_SHA)
    LOG.table([["렉시콘", NCQ_LEXICON.get("version", "?"), NCQ_LEXICON_SHA[:16] + "…",
                f"{sum(len(g['terms']) for g in NCQ_LEXICON['groups'].values())}개 어휘"],
               ["사전등록", NCQ_PREREG.get("version", "?"), NCQ_PREREG_SHA[:16] + "…",
                f"{len(NCQ_PREREG.get('hypotheses', []))}개 가설"]],
              ["구성", "버전", "SHA256", "규모"], ["l", "c", "l", "l"],
              title="동결 설정 (백테스트 수익률을 보기 전에 고정됨 — 사후 수정 시 전 결과 무효)")
    return NCQ_LEXICON, NCQ_LEXICON_SHA, NCQ_PREREG, NCQ_PREREG_SHA


# ── 렉시콘 컴파일 (그룹당 정규식 1개 — 어휘당 스캔은 너무 느리다) ────────────────────────────
_NCQ_GRP_RE: Dict[str, Any] = {}
_NCQ_NEG_RE = None


def _ncq_compile_lexicon():
    global _NCQ_GRP_RE, _NCQ_NEG_RE
    _NCQ_GRP_RE = {}
    for g, spec in NCQ_LEXICON["groups"].items():
        terms = sorted({str(t).strip() for t in spec["terms"] if str(t).strip()},
                       key=len, reverse=True)      # 긴 어휘 우선 매칭
        if not terms:
            continue
        # ★ 어휘 안의 공백은 \s* 로 바꾼다. PDF 텍스트는 줄바꿈이 단어 사이에 끼어들어
        #   "신규 수주" 가 "신규\n수주" 로 나오는 일이 매우 흔하다. 공백을 고정으로 두면
        #   그 건들이 통째로 미검출되고, 그 결손은 예외가 아니라 '점수 0'으로 조용히 남는다.
        #   (Python 3.7+ 의 re.escape 는 공백을 이스케이프하지 않으므로 예전 방식은 무동작이었다)
        pat = "|".join(r"\s*".join(re.escape(part) for part in t.split()) for t in terms)
        _NCQ_GRP_RE[g] = re.compile(pat)
    marks = NCQ_LEXICON.get("negation_markers", [])
    _NCQ_NEG_RE = re.compile("|".join(re.escape(m) for m in marks)) if marks else None


_ncq_compile_lexicon()


# ── PDF 섹션 추출 ───────────────────────────────────────────────────────────────────────────
_NCQ_COMPLIANCE_RE = re.compile(
    r"(Compliance\s*Notice|본\s*자료는|본\s*조사분석자료는|투자등급\s*및|투자의견\s*및\s*목표주가|"
    r"이해\s*관계\s*고지|이해관계|당사는\s*동\s*자료를|고지사항|Disclaimer|법적\s*고지)")
_NCQ_NUMLINE_RE = re.compile(r"[\d.,%\-+()/\s]")


def ncq_pdf_engine() -> str:
    """추출 엔진 선택. 명세 §8.2 는 pdfplumber 우선이지만 실측 10배 차이라 기본은 자동이다.

    두 엔진의 섹션 분할 결과는 동일한 규칙(첫 페이지 상위 40%)을 쓰므로 점수 분포가 달라지지
    않는다. 어떤 엔진이 쓰였는지는 TXT.extract_method 와 결손율 표에 그대로 남는다.
    """
    e = str(NCQ_PDF_ENGINE).lower()
    if e == "fitz":
        return "fitz" if fitz is not None else ("pdfplumber" if pdfplumber is not None else "")
    if e == "pdfplumber":
        return "pdfplumber" if pdfplumber is not None else ("fitz" if fitz is not None else "")
    if fitz is not None:
        return "fitz"
    if pdfplumber is not None:
        return "pdfplumber"
    return ""


def ncq_clean_text(pages: List[str]) -> str:
    """노이즈 제거 (명세 §8.3): 컴플라이언스 블록 절단 · 숫자 라인 제거 · 반복 헤더/푸터 제거."""
    if not pages:
        return ""
    # ① 반복 헤더/푸터 — 같은 줄이 페이지 수의 70% 이상 나오면 제거
    n_pg = len(pages)
    line_pages: Counter = Counter()
    per_page_lines = []
    for p in pages:
        ls = [ln.strip() for ln in str(p).split("\n")]
        per_page_lines.append(ls)
        for ln in set(ls):
            if len(ln) >= 4:
                line_pages[ln] += 1
    repeated = {ln for ln, c in line_pages.items() if n_pg >= 3 and c >= 0.7 * n_pg}

    out_lines: List[str] = []
    for ls in per_page_lines:
        for ln in ls:
            if not ln or ln in repeated:
                continue
            # ② 표·숫자 라인 — 숫자·기호 비중 60% 초과
            if len(ln) >= 6:
                nsym = len(_NCQ_NUMLINE_RE.findall(ln))
                if nsym / max(len(ln), 1) > 0.60:
                    continue
            out_lines.append(ln)
    txt = "\n".join(out_lines)
    # ③ 컴플라이언스 고지 이후 전체 절단
    m = _NCQ_COMPLIANCE_RE.search(txt)
    if m and m.start() > 200:
        txt = txt[:m.start()]
    return txt


def ncq_pdf_sections(data: bytes, max_pages: int = 0) -> dict:
    """PDF → {headline, body, n_pages, method, ok}.

    HEADLINE = 첫 페이지 상위 40% 영역(투자포인트·요약이 몰려 있는 블록). BODY = 나머지.
    ★ 텍스트 레이어가 비면(스캔 PDF) OCR 을 시도하지 않는다 — 예산을 파괴한다(명세 §8.2-3).
      대신 결손으로 기록한다.
    """
    res = {"headline": "", "body": "", "n_pages": 0, "method": "", "ok": False}
    if not data or data[:5] != b"%PDF-":
        return res
    eng = ncq_pdf_engine()
    cap = int(max_pages or globals().get("NCQ_PDF_MAX_PAGES", 0) or 0)
    head_parts: List[str] = []
    body_pages: List[str] = []

    if eng == "fitz" and fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                n = doc.page_count
                last = min(cap, n) if cap else n
                res["n_pages"] = n
                for i in range(last):
                    pg = doc[i]
                    if i == 0:
                        h = float(pg.rect.height) or 1.0
                        blocks = pg.get_text("blocks") or []
                        top, rest = [], []
                        for b in blocks:
                            try:
                                y0, t = float(b[1]), str(b[4])
                            except Exception:
                                continue
                            (top if y0 < 0.40 * h else rest).append(t)
                        head_parts.append("\n".join(top))
                        body_pages.append("\n".join(rest))
                    else:
                        body_pages.append(pg.get_text())
            res["method"] = "fitz"
        except Exception:
            eng = "pdfplumber" if pdfplumber is not None else ""

    if not res["method"] and eng == "pdfplumber" and pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                n = len(pdf.pages)
                last = min(cap, n) if cap else n
                res["n_pages"] = n
                for i in range(last):
                    pg = pdf.pages[i]
                    if i == 0:
                        h = float(pg.height) or 1.0
                        try:
                            top = pg.crop((0, 0, pg.width, 0.40 * h)).extract_text() or ""
                            rest = pg.crop((0, 0.40 * h, pg.width, h)).extract_text() or ""
                        except Exception:
                            top, rest = "", (pg.extract_text() or "")
                        head_parts.append(top)
                        body_pages.append(rest)
                    else:
                        body_pages.append(pg.extract_text() or "")
            res["method"] = "pdfplumber"
        except Exception:
            return res

    if not res["method"]:
        return res
    head = ncq_clean_text(head_parts)
    body = ncq_clean_text(body_pages)
    res["headline"], res["body"] = head, body
    res["ok"] = (len(head) + len(body)) >= 200        # 스캔 PDF 는 여기서 걸러진다
    return res


def collect_event_texts(EV: pd.DataFrame, REP: pd.DataFrame,
                        extra_text: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Phase 3 — **이벤트로 판정된 (종목, 월) 의 리포트만** PDF 를 받는다.

    ★ 이 한 줄이 이 전략의 비용 구조 전체다. 인덱스는 수만 건이지만 PDF 는 수천 건만 받는다.
    ★ 이미 드라이브 공용 인덱스에 있는 PDF 는 다시 받지 않는다(내용해시 경로 → 중복 저장 없음).
    """
    if EV is None or EV.empty or REP is None or REP.empty:
        return pd.DataFrame(columns=TXT_COLS)
    want: set = set()
    for s in EV["report_uids"].astype(str):
        for u in s.split("|"):
            if u and u != "nan":
                want.add(u)
    R = REP[REP["report_uid"].astype(str).isin(want)].copy()
    if R.empty:
        LOG.warn("이벤트에 연결된 리포트를 원장에서 찾지 못했습니다 — report_uid 연결이 깨졌습니다.")
        return pd.DataFrame(columns=TXT_COLS)
    R["code"] = R["stock_code"].map(to_code6)

    # 이미 추출해 둔 본문(공용 캐시) 재사용 — 티커 앞 2자리 샤드만 골라 읽는다
    cached_txt: List[pd.DataFrame] = []
    for pref in sorted({str(c)[:2] for c in R["code"].dropna().astype(str)}):
        d = VAULT.get_table(f"report_text_{pref}", scope="shared")
        if d is not None and len(d):
            cached_txt.append(d)
    if extra_text is not None and len(extra_text):
        # 호출자가 이미 확보한 본문(스모크의 합성 텍스트 · 외부에서 추출해 둔 본문)을 우선 사용.
        # 네트워크 없이도 텍스트 경로 전체를 실제로 검증할 수 있게 하는 통로다.
        cached_txt.insert(0, extra_text.reindex(columns=TXT_COLS))
    T_cached = pd.concat(cached_txt, ignore_index=True) if cached_txt else pd.DataFrame(columns=TXT_COLS)
    if len(T_cached):
        T_cached = T_cached.drop_duplicates("report_uid", keep="first")
    have = set(T_cached["report_uid"].astype(str)) if len(T_cached) else set()
    todo = R[~R["report_uid"].astype(str).isin(have)]
    LOG.info(f"Phase 3 대상 리포트 {len(R):,}건 — 본문 캐시 보유 {len(R)-len(todo):,}건 / "
             f"신규 추출 {len(todo):,}건")

    if len(todo) and RESEARCH_DOWNLOAD_PDF and RUN_MODE != "CACHED":
        if not ncq_pdf_engine():
            LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 본문 추출을 건너뜁니다. "
                     "제목(TITLE)만으로 점수가 계산되며 변별력이 크게 떨어집니다. "
                     "`pip install pymupdf` 를 권합니다.")
        else:
            new = _ncq_download_and_extract(todo)
            if len(new):
                T_cached = pd.concat([T_cached, new], ignore_index=True)
    elif len(todo):
        LOG.info(f"신규 PDF 수집을 하지 않습니다 (RUN_MODE={RUN_MODE}, "
                 f"RESEARCH_DOWNLOAD_PDF={RESEARCH_DOWNLOAD_PDF}).")

    if T_cached.empty:
        T_cached = pd.DataFrame(columns=TXT_COLS)
    T = T_cached[T_cached["report_uid"].astype(str).isin(set(R["report_uid"].astype(str)))].copy()
    # 제목은 원장에서 항상 붙인다(PDF 가 없어도 TITLE 섹션은 살아 있어야 한다)
    tmap = dict(zip(R["report_uid"].astype(str), R["title"].astype(str)))
    cmap = dict(zip(R["report_uid"].astype(str), R["code"]))
    dmap = dict(zip(R["report_uid"].astype(str), R["pub_date"]))
    miss = R[~R["report_uid"].astype(str).isin(set(T["report_uid"].astype(str)))]
    if len(miss):
        add = pd.DataFrame({
            "report_uid": miss["report_uid"].astype(str), "code": miss["code"],
            "pub_date": miss["pub_date"], "sec_title": miss["title"].astype(str),
            "sec_headline": "", "sec_body": "", "n_chars": 0, "n_pages": 0,
            "extract_ok": False, "extract_method": "none"})
        T = pd.concat([T, add], ignore_index=True)
    _tt = T["report_uid"].astype(str).map(tmap)
    T["sec_title"] = _tt.where(_tt.astype(str).str.len() > 0, T.get("sec_title", ""))
    T["code"] = T["report_uid"].astype(str).map(cmap).fillna(T.get("code"))
    T["pub_date"] = as_ts_series(T["report_uid"].astype(str).map(dmap))
    T = T.drop_duplicates("report_uid", keep="first")

    n_ok = int(T["extract_ok"].fillna(False).astype(bool).sum())
    fail = 1.0 - n_ok / max(len(T), 1)
    LOG.table([["대상 리포트", f"{len(T):,}"],
               ["본문 추출 성공", f"{n_ok:,} ({100*(1-fail):.1f}%)"],
               ["추출 실패/스캔 PDF", f"{len(T)-n_ok:,} ({100*fail:.1f}%)"],
               ["평균 본문 길이", f"{float(pd.to_numeric(T['n_chars'], errors='coerce').mean() or 0):,.0f}자"]],
              ["항목", "값"], ["l", "r"], title="Phase 3 본문 추출 결손율 (OCR 은 시도하지 않습니다)")
    manifest_put("pdf_extract_fail_rate", round(float(fail), 4))
    if fail > 0.5:
        LOG.warn(f"본문 추출 실패율이 {100*fail:.0f}% 입니다. 제목만으로 채점된 건이 많아 "
                 f"텍스트 점수의 변별력이 떨어집니다 — P4(증분 정보) 검정을 특히 주의해 보세요.")
    PIPE.io("OUT", "MEM", "report_text", T)
    return T[TXT_COLS]


def _ncq_download_and_extract(todo: pd.DataFrame) -> pd.DataFrame:
    """PDF 다운로드 + 섹션 추출. 청크 단위로 소비하고 버려 RAM 상주량을 평평하게 유지한다."""
    idx = VAULT.load_index("shared")
    known: Dict[str, str] = {}
    if idx is not None and len(idx) and "domain" in idx.columns:
        sub = idx[(idx["domain"].astype(str) == "research") &
                  (idx["subtype"].astype(str) == "report_pdf")]
        known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))

    jobs = list(zip(todo["report_uid"].astype(str), todo["pdf_url"].astype(str),
                    todo["code"].astype(str), todo["pub_date"], todo["title"].astype(str)))
    jobs = [j for j in jobs if j[1] and j[1].lower() not in ("nan", "none")]
    if not jobs:
        return pd.DataFrame(columns=TXT_COLS)

    def _one(job):
        uid, url, code, pdt, title = job
        data = None
        if uid in known:
            data = VAULT.get_blob(known[uid], "shared")
        if not data:
            src = "hankyung" if "hankyung" in url else ("irs" if "kirs" in url or "irsolution" in url
                                                        else "naver")
            ref = {"hankyung": "https://consensus.hankyung.com/",
                   "naver": "https://finance.naver.com/research/",
                   "irs": "https://www.kirs.or.kr/"}[src]
            raw = http_get(url, source=src, as_bytes=True, tries=2, referer=ref)
            # ★ 로그인/에러 HTML 이 200 으로 오는 케이스 방어 — 매직바이트를 반드시 본다
            data = raw if (raw and raw[:5] == b"%PDF-") else None
            if data:
                VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                               source="report_pdf", scope="shared",
                               event_date=pdt, knowledge_date=pdt)
        if not data:
            return {"report_uid": uid, "code": code, "pub_date": pdt, "sec_title": title,
                    "sec_headline": "", "sec_body": "", "n_chars": 0, "n_pages": 0,
                    "extract_ok": False, "extract_method": "download_failed"}
        s = ncq_pdf_sections(data)
        return {"report_uid": uid, "code": code, "pub_date": pdt, "sec_title": title,
                "sec_headline": s["headline"], "sec_body": s["body"],
                "n_chars": len(title) + len(s["headline"]) + len(s["body"]),
                "n_pages": s["n_pages"], "extract_ok": bool(s["ok"]),
                "extract_method": s["method"] or "no_engine"}

    rows: List[dict] = []
    CH = 400
    with PhaseBudget("P3", NCQ_PHASE_BUDGET_S["P3"], on_exceed="L2") as B:
        for k0 in range(0, len(jobs), CH):
            if not B.check():
                LOG.warn(f"[P3] 예산 소진 — {k0:,}/{len(jobs):,}건까지만 본문을 확보했습니다. "
                         f"나머지는 제목만으로 채점되며 결손율에 반영됩니다.")
                break
            chunk = jobs[k0:k0 + CH]
            res = pmap_io(_one, chunk, workers=min(N_WORKERS_RESEARCH, 4),
                          desc=f"리포트 PDF {k0//CH+1}/{(len(jobs)-1)//CH+1}")
            got = [r for r in res if r]
            rows.extend(got)
            _ncq_flush_text_shards(pd.DataFrame(got))
            VAULT.flush("shared")
            del res, got
    if not rows:
        return pd.DataFrame(columns=TXT_COLS)
    return pd.DataFrame(rows).reindex(columns=TXT_COLS)


def _ncq_flush_text_shards(new: pd.DataFrame):
    """본문을 티커 앞 2자리로 샤딩 저장(단일 거대 parquet 금지 — 기존 규약)."""
    if new is None or new.empty:
        return
    d = new.copy()
    d["_pref"] = d["code"].astype(str).str[:2]
    for pref, g in d.groupby("_pref"):
        if not pref or pref == "na":
            continue
        name = f"report_text_{pref}"
        old = VAULT.get_table(name, scope="shared")
        merged = g.drop(columns=["_pref"])
        if old is not None and len(old):
            cols = list(dict.fromkeys(list(old.columns) + list(merged.columns)))
            merged = pd.concat([old.reindex(columns=cols), merged.reindex(columns=cols)],
                               ignore_index=True).drop_duplicates("report_uid", keep="last")
        VAULT.put_table(name, merged, scope="shared", domain="research",
                        source="ncq pdf sections",
                        extra={"note": "리포트 본문 섹션 — 티커 앞2자리 샤딩 · 전 전략 공용"})


# ── Phase 4 — 스코어링 ──────────────────────────────────────────────────────────────────────
def _ncq_count_group(text: str, rx, neg_window: int) -> int:
    """그룹 어휘 출현 수. 같은 문장 안에서 어휘 뒤 30자 이내에 부정 어미가 오면 무효화한다.

    ★ 문장 경계를 넘어가면 부정이 아니다. 경계를 안 보면 다음 문장의 '없다'가 앞 문장의
      '수주 확대'를 지워버리는 오탐이 대량 발생한다.
    """
    if not text or rx is None:
        return 0
    n = 0
    for m in rx.finditer(text):
        if _NCQ_NEG_RE is not None:
            tail = text[m.end(): m.end() + neg_window]
            cut = re.search(r"[.!?\n]", tail)
            scope = tail[:cut.start()] if cut else tail
            if _NCQ_NEG_RE.search(scope):
                continue                                  # 부정 → 이 출현은 0점
        n += 1
    return n


def score_texts(TXT: pd.DataFrame) -> pd.DataFrame:
    """문서 점수 (명세 §9.3).

        doc_raw   = Σ_g w_g × [3.0·cnt(TITLE) + 2.0·cnt(HEADLINE) + 1.0·cnt(BODY)]
        doc_score = doc_raw / (총 문자수 / 1000)          ← 길이 정규화

    길이 정규화를 빼면 '긴 리포트일수록 고득점'이라는 자명한 편향이 생기고, 대형사 리포트가
    구조적으로 유리해진다. 우리가 재려는 것은 밀도이지 분량이 아니다.
    """
    if TXT is None or TXT.empty:
        return pd.DataFrame(columns=SCORE_COLS)
    sw = NCQ_LEXICON.get("section_weight", {"TITLE": 3.0, "HEADLINE": 2.0, "BODY": 1.0})
    negw = int(NCQ_LEXICON.get("negation_window", 30))
    groups = NCQ_LEXICON["groups"]

    T = TXT.copy()
    for c in ("sec_title", "sec_headline", "sec_body"):
        if c not in T.columns:
            T[c] = ""
        T[c] = T[c].fillna("").astype(str)

    def _row(r):
        raw = 0.0
        counts = {}
        for g, spec in groups.items():
            rx = _NCQ_GRP_RE.get(g)
            ct = _ncq_count_group(r[0], rx, negw)
            ch = _ncq_count_group(r[1], rx, negw)
            cb = _ncq_count_group(r[2], rx, negw)
            counts[g] = ct + ch + cb
            raw += float(spec["weight"]) * (sw["TITLE"] * ct + sw["HEADLINE"] * ch +
                                            sw["BODY"] * cb)
        return raw, counts

    tri = list(zip(T["sec_title"], T["sec_headline"], T["sec_body"]))
    out_raw, out_cnt = [], []
    for r in tqdm(tri, desc="텍스트 스코어링", ncols=88, leave=False):
        a, b = _row(r)
        out_raw.append(a)
        out_cnt.append(b)

    S = pd.DataFrame({"report_uid": T["report_uid"].astype(str), "code": T["code"],
                      "pub_date": as_ts_series(T["pub_date"]), "doc_raw": out_raw})
    for g in groups:
        S[f"g_{g}"] = [c.get(g, 0) for c in out_cnt]
    S["n_chars"] = (T["sec_title"].str.len() + T["sec_headline"].str.len() +
                    T["sec_body"].str.len()).to_numpy()
    denom = (S["n_chars"] / 1000.0).replace(0, np.nan)
    # ★ 본문이 아주 짧으면(제목만 있는 건) 분모가 0에 수렴해 점수가 폭발한다. 하한을 둔다.
    denom = denom.clip(lower=0.25)
    S["doc_score"] = S["doc_raw"] / denom
    S["month"] = S["pub_date"] + pd.offsets.MonthEnd(0)
    S = S.dropna(subset=["code", "month"])
    LOG.ok(f"텍스트 스코어링 {len(S):,}건 — doc_score 평균 {S['doc_score'].mean():.3f} / "
           f"표준편차 {S['doc_score'].std():.3f}")
    PIPE.io("OUT", "MEM", "text_scores", S)
    return S.reindex(columns=SCORE_COLS + [])


# ── Phase 5 — 횡단면 상대비교 → 상위 tercile ────────────────────────────────────────────────
def build_signal_panel(SCORE: pd.DataFrame, EV: pd.DataFrame, UNI: pd.DataFrame,
                       pxm: pd.DataFrame, months: pd.DatetimeIndex,
                       top_pct: Optional[float] = None) -> pd.DataFrame:
    """명세 §9.4 — **절대 임계를 쓰지 않는다.** 같은 달 이벤트 풀 안에서만 z-score 로 비교한다.

    · 월 이벤트가 5건 미만이면 z 가 불안정하므로 직전 3개월 롤링 풀로 계산하고 pooled=True 태깅.
    · 편입 = z 상위 tercile.  대조군(Placebo) = z 하위 tercile.
    """
    tp = float(top_pct if top_pct is not None else NCQ_TERCILE)
    if EV is None or EV.empty:
        return pd.DataFrame(columns=SIG_COLS)

    E = EV.copy()
    if SCORE is not None and len(SCORE):
        # 같은 달 복수 리포트면 **최댓값**. 평균이 아니다 — 가장 강한 주장이 정보다(§9.3).
        agg = (SCORE.groupby(["code", "month"], observed=True)["doc_score"]
                    .max().rename("event_score").reset_index())
        E = E.merge(agg, on=["code", "month"], how="left")
    else:
        E["event_score"] = np.nan
    n_noscore = int(E["event_score"].isna().sum())
    if n_noscore:
        LOG.warn(f"이벤트 {n_noscore:,}건에 텍스트 점수가 없습니다(본문 미확보). "
                 f"z 계산에서 제외되며 결손으로 남습니다 — 0점으로 채우지 않습니다.")

    E = E.dropna(subset=["event_score"]).copy()
    if E.empty:
        LOG.error("텍스트 점수가 있는 이벤트가 하나도 없습니다. Phase 3(PDF) 이 전부 실패한 상태입니다.")
        return pd.DataFrame(columns=SIG_COLS)

    E = E.sort_values(["month", "code"]).reset_index(drop=True)
    mi = _ncq_mi(E["month"])
    E["_mi"] = mi
    rows = []
    for m, g in E.groupby("month", observed=True):
        pool = g
        pooled = False
        if len(g) < NCQ_ZPOOL_MIN_N:
            m0 = float(_ncq_mi(pd.Series([m])).iloc[0])
            pool = E[(E["_mi"] <= m0) & (E["_mi"] > m0 - 3)]
            pooled = len(pool) > len(g)
        v = pd.to_numeric(pool["event_score"], errors="coerce")
        mu, sd = float(v.mean()), float(v.std(ddof=0))
        z = (pd.to_numeric(g["event_score"], errors="coerce") - mu) / (sd if sd > 0 else np.nan)
        # 표준편차가 0(전원 동일 점수)이면 변별이 불가능하다. 0으로 두고 선정에서 전원 동률 처리.
        z = z.fillna(0.0) if (not np.isfinite(sd) or sd <= 0) else z
        t = g.copy()
        t["z"] = z.to_numpy()
        t["pooled"] = pooled
        t["pool_n"] = int(len(pool))
        rows.append(t)
    Z = pd.concat(rows, ignore_index=True) if rows else E

    # 월별 백분위 랭크 → 상·하위 tercile
    Z["rank_pct"] = Z.groupby("month", observed=True)["z"].rank(pct=True, method="average")
    Z["selected"] = Z["rank_pct"] >= (1.0 - tp)
    Z["placebo"] = Z["rank_pct"] <= tp

    # 월 신규 편입 상한 (§10 — 초과 시 z 상위 N 으로 절단)
    if NCQ_MAX_NEW_PER_MONTH and NCQ_MAX_NEW_PER_MONTH > 0:
        sel = Z[Z["selected"]].copy()
        over = sel.groupby("month", observed=True)["code"].size()
        over = over[over > NCQ_MAX_NEW_PER_MONTH]
        if len(over):
            keep_idx = (sel[sel["month"].isin(over.index)]
                        .sort_values(["month", "z", "code"], ascending=[True, False, True])
                        .groupby("month", observed=True).head(NCQ_MAX_NEW_PER_MONTH).index)
            drop_idx = sel[sel["month"].isin(over.index)].index.difference(keep_idx)
            Z.loc[drop_idx, "selected"] = False
            LOG.info(f"월 신규 편입 상한({NCQ_MAX_NEW_PER_MONTH}종목) 적용 — "
                     f"{len(drop_idx):,}건을 z 하위부터 절단했습니다.")

    if pxm is not None and len(pxm):
        # ★ (code, month) 가 유일하지 않으면 merge 가 행을 증식시켜 이벤트가 복제된다.
        _px1 = pxm.drop_duplicates(["code", "month"], keep="last")
        _n0 = len(Z)
        Z = Z.merge(_px1[["code", "month", "exec_px", "fwd_ret", "signal_date"]],
                    on=["code", "month"], how="left")
        if len(Z) != _n0:
            LOG.warn(f"가격 결합에서 행수가 {_n0:,}→{len(Z):,} 로 변했습니다 — 중복 키입니다.")
            Z = Z.drop_duplicates(["month", "code"], keep="first")
    for c in ("exec_px", "fwd_ret"):
        if c not in Z.columns:
            Z[c] = np.nan
    if "adv20" not in Z.columns:
        Z["adv20"] = np.nan

    n_sel = int(Z["selected"].sum())
    n_pool = int(Z["pooled"].sum())
    LOG.ok(f"신호 패널 {len(Z):,}행 — 편입 {n_sel:,}건(상위 {100*tp:.0f}%) · "
           f"대조군 {int(Z['placebo'].sum()):,}건 · 풀링 사용 {n_pool:,}건")
    if n_pool > 0.3 * len(Z):
        LOG.warn(f"이벤트가 적어 {100*n_pool/max(len(Z),1):.0f}% 의 달에서 3개월 롤링 풀로 z 를 "
                 f"계산했습니다. 동월 횡단면 비교라는 설계 취지가 그만큼 희석됩니다.")
    VAULT.put_table(f"signal_panel_{STRATEGY_ID}", Z, scope="private", domain="signals",
                    source="build_signal_panel", extra={"top_pct": tp})
    PIPE.io("OUT", "MEM", "signal_panel", Z)
    keep = [c for c in SIG_COLS if c in Z.columns]
    extra = [c for c in ("n_reports", "n_brokers", "sources", "broker_ids", "report_uids",
                         "mcap", "signal_date", "is_denovo") if c in Z.columns]
    return Z[keep + extra]


# ============================================================================================
# 조립 블록 17: ncq_50_backtest.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  Phase 6 — 12개월 오버랩 코호트 백테스트 · 벤치마크 · 성과지표                              ║
# ║                                                                                          ║
# ║  입력 : SIG(신호) · pxm(월말 패널) · sec · Universe · months                                ║
# ║  출력 : BT{returns, holdings, cohorts, label}                                              ║
# ║  실패 : 신호가 없는 달은 예외가 아니라 '현금 보유'다. 강제 편입하지 않는다(명세 §10).       ║
# ║                                                                                          ║
# ║  ── 구조 (명세 §10) ────────────────────────────────────────────────────────────────────  ║
# ║   · 매월 1/H 코호트를 신규 편입하고 H개월 뒤 청산하는 **오버랩 포트폴리오**                 ║
# ║   · 코호트 내 동일가중. 신호 없는 코호트 슬롯은 현금(수익 0) — 억지로 채우지 않는다         ║
# ║   · 체결 = 월말 신호 → **다음 영업일 시가**(pxm.exec_px). 당일 종가 체결은 미래누수다       ║
# ║   · 상장폐지: 폐지 직전가 -50% 적용 후 현금화. 누락 처리 금지(= 생존자편향)                 ║
# ║   · 거래정지: 정지 직전가로 마킹(수익 0), 재개 시 실가 반영                                 ║
# ║   · 종목당 상한: 편입 시점 20일 ADV 의 10% (3일 내 청산 가능 규모). 초과분은 현금           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시, 총부담 기준). 비용의 '비대칭'을 만들기 위해 쓴다.
NCQ_TAX_SCHEDULE = [("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
                    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015)]
NCQ_COMMISSION = 0.00015          # 편도 수수료 0.015%


def ncq_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = NCQ_TAX_SCHEDULE[0][1]
    for d, r in NCQ_TAX_SCHEDULE:
        if t is not None and t >= as_ts(d):
            rate = r
    return rate


def ncq_split_cost(cost_roundtrip: float, entry_dt, exit_dt) -> Tuple[float, float]:
    """왕복 비용을 진입/청산으로 쪼갠다.

    ★ 왕복 총액은 사용자가 지정한 값(민감도 축)을 **정확히** 지킨다. 다만 매도 쪽에만 붙는
      증권거래세 때문에 실제 부담은 비대칭이므로, 세율만큼을 청산 쪽에 얹고 나머지 슬리피지를
      균등 분배한다. 이렇게 하면 '왕복 1.8%' 라는 계약을 지키면서 세율 이력도 반영된다.
    """
    tax = ncq_sell_tax(exit_dt)
    rest = float(cost_roundtrip) - 2 * NCQ_COMMISSION - tax
    slip = max(0.0, rest / 2.0)
    entry = NCQ_COMMISSION + slip
    exit_ = NCQ_COMMISSION + slip + tax
    if rest < 0:                       # 지정 왕복비용이 세금+수수료보다 작으면 균등 분배로 낮춘다
        entry = exit_ = max(0.0, float(cost_roundtrip) / 2.0)
    return entry, exit_


def perf_stats(R: pd.DataFrame, rf: float = 0.0) -> dict:
    """월별 수익률 시계열의 성과 지표. 값이 정의되지 않으면 NaN 으로 둔다(0으로 채우지 않음)."""
    if R is None or len(R) == 0 or "ret" not in R.columns:
        return {}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / 12.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = float(r.std(ddof=1) * math.sqrt(12)) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = float(dn.std(ddof=1) * math.sqrt(12)) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if n else np.nan
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, t = hac_tstat(r, lags=12)
    return {
        "월수": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "월평균": float(r.mean()),
        "t통계량(HAC12)": t, "최장언더워터(월)": int(mx),
        "평균종목수": float(pd.to_numeric(R.get("n"), errors="coerce").mean())
        if "n" in R.columns else np.nan,
        "월평균비용": float(pd.to_numeric(R.get("cost"), errors="coerce").mean())
        if "cost" in R.columns else np.nan,
        "월평균현금비중": float(pd.to_numeric(R.get("cash"), errors="coerce").mean())
        if "cash" in R.columns else np.nan,
    }


def _ncq_ret_matrix(pxm: pd.DataFrame, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(월 × 종목) 수익률 행렬과 ADV 행렬. 종목별 루프를 없애기 위한 벡터화 준비."""
    if pxm is None or pxm.empty:
        return (pd.DataFrame(index=months), pd.DataFrame(index=months))
    p = pxm.drop_duplicates(["code", "month"], keep="last")
    RM = p.pivot(index="month", columns="code", values="fwd_ret").reindex(months)
    AM = (p.pivot(index="month", columns="code", values="adv20").reindex(months)
          if "adv20" in p.columns else pd.DataFrame(index=months))
    return RM, AM


def run_overlap_backtest(SIG: pd.DataFrame, pxm: pd.DataFrame, sec: pd.DataFrame,
                         uni_obj: Optional["Universe"], months: pd.DatetimeIndex,
                         hold_months: Optional[int] = None, sel_col: str = "selected",
                         cost_roundtrip: Optional[float] = None, adv_cap: bool = True,
                         label: str = "NCQ") -> dict:
    """오버랩 코호트 백테스트.

    수익률 인덱싱 규약: 월 t 의 수익률은 'exec_px(t) → exec_px(t+1)' 사이의 실현분이다
    (pxm.fwd_ret 과 동일). 월말 신호 → 익영업일 시가 진입이므로, 월 t 에 편입한 코호트는
    월 t 의 수익률부터 받는다. 이 규약을 벤치마크·플라시보에도 **동일하게** 적용한다.
    """
    H = int(hold_months or NCQ_HOLD_MONTHS)
    cost = float(cost_roundtrip if cost_roundtrip is not None else NCQ_COST_ROUNDTRIP)
    empty = {"returns": pd.DataFrame(columns=["month", "ret", "ret_gross", "n", "turnover",
                                              "cost", "cash", "equity"]),
             "holdings": pd.DataFrame(columns=["month", "code", "weight", "ret", "cohort", "z"]),
             "cohorts": pd.DataFrame(columns=["cohort", "code", "entry_month", "exit_month",
                                              "ret_h", "n_months"]),
             "label": label}
    if SIG is None or SIG.empty or sel_col not in SIG.columns:
        return empty

    RM, AM = _ncq_ret_matrix(pxm, months)
    if RM.empty:
        LOG.warn("수익률 행렬이 비어 백테스트를 수행할 수 없습니다(가격 패널 확인).")
        return empty
    mon_pos = {m: i for i, m in enumerate(months)}
    delist = {}
    if uni_obj is not None:
        try:
            delist = uni_obj.delisting_map()
        except Exception:
            delist = {}

    S = SIG[SIG[sel_col].fillna(False).astype(bool)].copy()
    S = S[S["month"].isin(months)]
    if S.empty:
        LOG.warn(f"[{label}] 선정된 이벤트가 없어 전 구간 현금 보유가 됩니다.")
        return empty

    n_m = len(months)
    port_ret = np.zeros(n_m)
    port_cost = np.zeros(n_m)
    invested = np.zeros(n_m)         # 실제 투자된 비중(나머지는 현금)
    n_names = np.zeros(n_m)
    turnover = np.zeros(n_m)
    holdings: List[dict] = []
    cohorts: List[dict] = []
    slot_w = 1.0 / float(H)          # 코호트 슬롯당 자본 배분 (신호 없으면 현금)

    for c_month, g in S.groupby("month", observed=True):
        c0 = mon_pos.get(c_month)
        if c0 is None:
            continue
        names = [c for c in g["code"].astype(str).tolist() if c in RM.columns]
        if not names:
            continue
        zs = dict(zip(g["code"].astype(str), pd.to_numeric(g.get("z"), errors="coerce")))
        k = len(names)
        w_each = slot_w / k

        # ── 종목당 상한 = 편입 시점 20일 ADV × 참여율. 초과분은 현금으로 남긴다(§10, R4) ──
        if adv_cap and not AM.empty and c_month in AM.index:
            adv = pd.to_numeric(AM.loc[c_month].reindex(names), errors="coerce").to_numpy()
            cap_krw = adv * NCQ_ADV_PARTICIPATION
            cap_w = np.where(np.isfinite(cap_krw) & (cap_krw > 0),
                             cap_krw / max(NCQ_ACCOUNT_KRW, 1.0), 0.0)
            w = np.minimum(np.full(k, w_each), cap_w)
        else:
            w = np.full(k, w_each)
        w = np.where(np.isfinite(w), w, 0.0)
        if w.sum() <= 0:
            continue

        e_cost, x_cost = ncq_split_cost(cost, c_month, months[min(c0 + H, n_m - 1)])
        port_cost[c0] += float(w.sum()) * e_cost
        turnover[c0] += float(w.sum())

        alive = np.ones(k, dtype=bool)
        haircut_done = np.zeros(k, dtype=bool)
        cum = np.ones(k)
        n_held = np.zeros(k, dtype=int)
        for h in range(H):
            t = c0 + h
            if t >= n_m:
                break
            m_t = months[t]
            row = RM.loc[m_t].reindex(names)
            r = pd.to_numeric(row, errors="coerce").to_numpy(dtype=float)
            for j, cd in enumerate(names):
                if not alive[j]:
                    r[j] = 0.0
                    continue
                dl = delist.get(cd)
                if dl is not None and pd.notna(dl) and as_ts(dl) <= m_t + pd.offsets.MonthEnd(0):
                    # 상장폐지: 폐지 직전가 -50% 적용 후 현금화 (명세 §10)
                    if not haircut_done[j]:
                        r[j] = NCQ_DELIST_HAIRCUT
                        haircut_done[j] = True
                    else:
                        r[j] = 0.0
                    alive[j] = False
                elif not np.isfinite(r[j]):
                    # 거래정지·데이터 결손 → 정지 직전가로 마킹(수익 0). 재개 시 실가가 들어온다.
                    r[j] = 0.0
                else:
                    n_held[j] += 1
            port_ret[t] += float(np.dot(w, r))
            invested[t] += float(w.sum())
            n_names[t] += float(np.sum(w > 0))
            cum = cum * (1.0 + r)
            for j, cd in enumerate(names):
                holdings.append({"month": m_t, "code": cd, "weight": float(w[j]),
                                 "ret": float(r[j]), "cohort": c_month,
                                 "z": float(zs.get(cd, np.nan))})
            if h == H - 1 or t == n_m - 1:
                port_cost[t] += float(w.sum()) * x_cost
                turnover[t] += float(w.sum())
        ex_i = min(c0 + H, n_m - 1)
        for j, cd in enumerate(names):
            cohorts.append({"cohort": c_month, "code": cd, "entry_month": c_month,
                            "exit_month": months[ex_i], "ret_h": float(cum[j] - 1.0),
                            "n_months": int(n_held[j]), "weight": float(w[j]),
                            "z": float(zs.get(cd, np.nan))})

    R = pd.DataFrame({"month": months, "ret_gross": port_ret, "cost": port_cost,
                      "n": n_names, "turnover": turnover,
                      "cash": np.clip(1.0 - invested, 0.0, 1.0)})
    R["ret"] = R["ret_gross"] - R["cost"]
    R["equity"] = (1.0 + R["ret"].fillna(0.0)).cumprod()
    H_df = pd.DataFrame(holdings) if holdings else pd.DataFrame(
        columns=["month", "code", "weight", "ret", "cohort", "z"])
    C_df = pd.DataFrame(cohorts) if cohorts else pd.DataFrame(
        columns=["cohort", "code", "entry_month", "exit_month", "ret_h", "n_months"])
    LOG.info(f"[{label}] 백테스트 완료 — 코호트 {C_df['cohort'].nunique() if len(C_df) else 0}개 · "
             f"연인원 {len(H_df):,} · 평균 현금비중 {100*R['cash'].mean():.0f}% · "
             f"누적 {100*(R['equity'].iloc[-1]-1):+.1f}%")
    return {"returns": R, "holdings": H_df, "cohorts": C_df, "label": label}


# ── 벤치마크 ────────────────────────────────────────────────────────────────────────────────
def bench_universe_ew(UNI: pd.DataFrame, pxm: pd.DataFrame,
                      months: pd.DatetimeIndex) -> pd.Series:
    """주 벤치마크 — 동일 유니버스 동일가중(Bottom-N EW).

    ★ 이것이 진짜 비교 대상이다. KOSDAQ 지수와 비교하면 '소형주 프리미엄'을 알파로 착각한다.
      같은 유니버스, 같은 유동성 필터, 같은 체결 규약에서 동일가중으로 담았을 때와 비교해야
      신호의 순수 기여가 드러난다.
    """
    if UNI is None or UNI.empty or pxm is None or pxm.empty:
        return pd.Series(np.nan, index=months, name="Bottom-N EW")
    u = UNI[UNI["liq_pass"].fillna(False).astype(bool)][["month", "code"]]
    j = u.merge(pxm[["month", "code", "fwd_ret"]], on=["month", "code"], how="left")
    s = j.groupby("month", observed=True)["fwd_ret"].mean().reindex(months)
    s.name = "Bottom-N EW"
    n = j.groupby("month", observed=True)["code"].size().reindex(months)
    LOG.info(f"주 벤치마크(Bottom-N EW) 구성 — 월평균 {float(n.mean() or 0):,.0f}종목 동일가중")
    return s


def bench_event_ew(SIG: pd.DataFrame, pxm: pd.DataFrame, months: pd.DatetimeIndex,
                   uni_obj=None, sec=None) -> dict:
    """전체 신규커버리지 이벤트를 텍스트 점수와 무관하게 전부 담은 팔 (P4 의 대조군)."""
    if SIG is None or SIG.empty:
        return {"returns": pd.DataFrame(columns=["month", "ret", "equity"]), "label": "이벤트 EW"}
    S = SIG.copy()
    S["_all"] = True
    return run_overlap_backtest(S, pxm, sec, uni_obj, months, sel_col="_all",
                                label="이벤트 EW(텍스트 미사용)")


def bench_index(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """보조 벤치마크 — KOSPI / KOSDAQ. 실패해도 조용히 빈 dict(전략은 주 벤치마크로 판정)."""
    out: Dict[str, pd.Series] = {}
    if fdr is None:
        LOG.info("FinanceDataReader 가 없어 지수 벤치마크를 건너뜁니다 "
                 "(주 벤치마크는 Bottom-N EW 이므로 판정에는 영향 없음).")
        return out
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            d = fdr.DataReader(sym, (months[0] - pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d"),
                               months[-1].strftime("%Y-%m-%d"))
        except Exception as e:                                   # noqa
            LOG.debug(f"지수 {name} 조회 실패: {type(e).__name__}")
            continue
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d["month"] = d["date"] + pd.offsets.MonthEnd(0)
        s = d.groupby("month")["close"].last().pct_change().reindex(months)
        s.name = name
        out[name] = s
    if out:
        LOG.ok(f"지수 벤치마크 확보: {', '.join(out)}")
    return out


def excess_series(BT: dict, bench: pd.Series) -> pd.Series:
    """전략 − 벤치마크 월별 초과수익. **month 인덱스로 정렬 후 교집합만** 사용한다.

    ★ 위치 기반 뺄셈(np 배열끼리)은 두 시계열의 시작월이 다르면 조용히 어긋난다.
      한 달만 밀려도 t 통계량이 완전히 달라진다 — 반드시 인덱스로 맞춘다.
    """
    if not BT or "returns" not in BT or BT["returns"] is None or len(BT["returns"]) == 0:
        return pd.Series(dtype=float)
    R = BT["returns"].set_index("month")["ret"]
    if bench is None or len(bench) == 0:
        return R
    b = pd.Series(bench).copy()
    b.index = as_ts_series(pd.Series(b.index))
    idx = R.index.intersection(b.index)
    if len(idx) == 0:
        return pd.Series(dtype=float)
    return (R.reindex(idx).fillna(0.0) - b.reindex(idx).fillna(0.0)).sort_index()


def right_tail_contribution(BT: dict) -> dict:
    """우측 꼬리 의존도 — 상위 소수 종목을 빼면 성과가 사라지는가(명세 §11.3-7)."""
    H = BT.get("holdings") if BT else None
    if H is None or len(H) == 0:
        return {}
    contrib = (pd.to_numeric(H["weight"], errors="coerce") *
               pd.to_numeric(H["ret"], errors="coerce"))
    s = contrib.groupby(H["code"]).sum().sort_values(ascending=False)
    n = len(s)
    if n == 0:
        return {}
    base = float(s.sum())
    out = {"총기여": base, "종목수": n}
    for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(n * q)))
        out[f"{lab} 기여"] = float(s.iloc[:k].sum())
        out[f"{lab} 제외 후"] = base - float(s.iloc[:k].sum())
    out["기여 상위5"] = ", ".join(f"{c}({v:+.3f})" for c, v in s.head(5).items())
    out["기여 하위5"] = ", ".join(f"{c}({v:+.3f})" for c, v in s.tail(5).items())
    return out


# ============================================================================================
# 조립 블록 18: ncq_60_robust.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  ARC-NCQ 강건성·통계검증 계층 (§11)                                                   ║
# ║                                                                                          ║
# ║  목적 : "이 성과가 우연·과적합·비용무시·소스편향의 산물이 아님"을 사전등록된 순서로        ║
# ║         정면 검정한다. 사전등록 가설 P1~P4 → BH-FDR → 부트스트랩/순열/워크포워드/        ║
# ║         PBO/DSR/Holm → 민감도 9조합 → 구조적 리스크 R1~R6.                               ║
# ║                                                                                          ║
# ║  입력 : SIG(신호패널) · BT(백테스트 결과 dict) · bench_ew(Bottom-N 동일가중 월수익)       ║
# ║         months(월말 DatetimeIndex) · ctx(파이프라인 산출물 모음: dict 또는 객체)          ║
# ║         run_fn(SIG, hold_months=, cost_roundtrip=, sel_col=, label=) -> BT   ← 스파인 주입 ║
# ║         build_sig_fn(top_pct=, min_adv=) -> SIG                              ← 스파인 주입 ║
# ║  출력 : NCQ_ROBUST 원장(OrderedDict) + LOG.table 표 + 사전등록/민감도 DataFrame           ║
# ║                                                                                          ║
# ║  실패 시 동작 :                                                                           ║
# ║    · 표본 부족(월수<12, 이벤트<50 …)·콜백 부재·백테스트 실패 → 예외가 아니라              ║
# ║      passed=None(판정불가) + 사유 문자열. 없는 결론을 만들어내지 않는다.                   ║
# ║    · 사전등록 채택 기준 미충족 → ⭐킬 게이트. 다만 반환 dict 를 NCQ_PREREG_RESULT 전역에   ║
# ║      먼저 저장한 뒤 올리므로, 호출부가 KillCriteria 를 잡아도 근거는 사라지지 않는다.      ║
# ║                                                                                          ║
# ║  ★ 원칙 : 나쁜 결과를 좋게 보이게 만들지 않는다. 실패·판정불가는 그대로 출력한다.          ║
# ║           결측은 "—" 로 표기하고 절대 0 으로 치환하지 않는다.                              ║
# ║           없는 최적화를 있는 척하지 않는다(워크포워드 주석 참조).                          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 원장 / 모듈 상태 ────────────────────────────────────────────────────────────────────────
NCQ_ROBUST: "OrderedDict[str, dict]" = OrderedDict()

# 민감도 실행이 남기는 부산물. run_stat_suite 의 PBO(CSCV)·Holm 이 인자 없이도 이걸 주워 쓴다.
# (성과 벡터가 1개뿐이면 PBO 는 '근사'가 되므로, 민감도 9조합 곡선이 있으면 정식 CSCV 가 된다)
NCQ_SENS_CURVES: "OrderedDict[str, pd.Series]" = OrderedDict()
NCQ_SENS_TABLE = None                 # 마지막 run_sensitivity 반환 표 (Holm 입력)
NCQ_PREREG_RESULT = None              # 킬 게이트 발동 전에 저장되는 사전등록 결과

# 검정 상수 (사전등록 값 — 결과를 보고 바꾸지 말 것)
NCQ_FDR_Q = 0.10                      # BH-FDR α (P1~P4 전체에 적용)
NCQ_HAC_LAG = 12                      # Newey-West lag (보유 12개월 오버랩과 맞춤)
NCQ_BOOT_BLOCK = 12                   # 블록 부트스트랩 블록 길이(개월)
NCQ_BOOT_ITER = 1000
NCQ_PERM_ITER = 1000
NCQ_CSCV_S = 16                       # PBO 분할 수
NCQ_CSCV_MAX_COMBOS = 2000            # 조합 폭발 시 무작위 표본 상한
NCQ_WF_IS_M = 60                      # 워크포워드 IS 5년
NCQ_WF_OOS_M = 12                     # OOS 롤링 1년
NCQ_WF_STEP_M = 12                    # 1년 스텝
NCQ_HOLM_ALPHA = 0.05
NCQ_COST_STRESS = 0.030               # 채택 조건의 왕복비용 스트레스 시나리오
NCQ_MIN_MONTHS = 12                   # 이보다 짧으면 HAC t 자체가 정의되지 않는다
NCQ_MIN_EVENTS_SUB = 50               # 서브그룹 검정 최소 이벤트 수


# ══════════════════════════════════════════════════════════════════════════════════════════
#  0. 공용 유틸 — 정렬·포맷·안전 접근
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_cfg(name: str, default):
    """헤더 상수를 안전하게 읽는다. 조립 순서가 바뀌거나 헤더가 축약돼도 이 계층은 죽지 않는다."""
    v = globals().get(name, None)
    return default if v is None else v


def ncq_f(v, kind: str = "num", nd: int = 3) -> str:
    """결측/비유한은 항상 '—'. NaN 을 0 으로 치환하지 않는다(계약 §3)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(x):
        return "—"
    if kind == "pct":
        return f"{x * 100:+.2f}%"
    if kind == "pctp":
        return f"{x * 100:+.3f}%p"
    if kind == "pct0":
        return f"{x * 100:.1f}%"
    if kind == "p":
        return f"{x:.4f}"
    if kind == "t":
        return f"{x:+.2f}"
    if kind == "int":
        return f"{int(round(x)):,}"
    return f"{x:,.{nd}f}"


def ncq_mark(passed) -> str:
    """True/False/None → 표에 쓰는 판정 아이콘. None 은 '실패'가 아니라 '판정불가'다."""
    if passed is None:
        return "— 판정불가"
    return "✔ 통과" if bool(passed) else "✘ 실패"


def ncq_is_pass(v) -> bool:
    """'명시적 통과'인가. 판정불가(None)는 통과가 아니다.

    ★ `v is True` 로 쓰면 안 된다 — np.True_ is True 는 False 라서, numpy bool 이 한 번이라도
      섞이면 통과 분기가 조용히 죽는다(판정이 전부 '실패'로 보이는 사고). 여기로만 통과시킨다.
    """
    return v is not None and bool(v)


def ncq_is_fail(v) -> bool:
    """'명시적 실패'인가. 판정불가(None)는 실패가 아니다(킬 게이트를 발동시키지 않는다).

    ★ `v is False` 금지 — np.False_ is False 가 False 라 킬 게이트가 발동하지 않는 사고가 났다.
    """
    return v is not None and not bool(v)


def ncq_ctx_get(ctx, key: str, default=None):
    """ctx 가 dict 이든 네임스페이스 객체이든 동일하게 꺼낸다. 없으면 default."""
    if ctx is None:
        return default
    try:
        if isinstance(ctx, dict):
            v = ctx.get(key, None)
            return default if v is None else v
    except Exception:
        pass
    v = getattr(ctx, key, None)
    return default if v is None else v


def ncq_boolmask(s) -> pd.Series:
    """selected/placebo 같은 이진 컬럼 → bool 마스크. NaN 은 False(=선택 안 됨)로 본다.

    ★ .astype(bool) 을 그냥 쓰면 NaN 이 True 가 되어 '선택되지 않은 종목이 조용히 편입'된다.
    """
    if s is None:
        return pd.Series(dtype=bool)
    x = pd.Series(s)
    if x.dtype == bool:
        return x
    if x.dtype.kind in "iufb":
        return (pd.to_numeric(x, errors="coerce").fillna(0) != 0)
    return x.map(lambda v: bool(v) if (v is not None and v == v) else False).astype(bool)


def ncq_month_series(x, col: str = "ret") -> pd.Series:
    """무엇이 들어오든 'month(DatetimeIndex) → 값' Series 로 정규화한다.

    ★ 두 팔의 시계열을 뺄 때 위치 기반(iloc) 뺄셈은 금지다. 길이가 하루라도 다르면
      조용히 다른 달끼리 빼면서 그럴듯한 숫자를 만든다. 모든 시계열은 이 관문을 통과시킨 뒤
      ncq_align_diff 로만 뺀다.
    """
    if x is None:
        return pd.Series(dtype="float64")
    if isinstance(x, dict):                       # BT dict
        x = x.get("returns")
    if isinstance(x, pd.DataFrame):
        if x.empty or "month" not in x.columns:
            return pd.Series(dtype="float64")
        use = col if col in x.columns else ("ret" if "ret" in x.columns else None)
        if use is None:
            return pd.Series(dtype="float64")
        vals = pd.to_numeric(x[use], errors="coerce").to_numpy(dtype="float64")
        idx = pd.to_datetime(pd.Series(x["month"]), errors="coerce")
    elif isinstance(x, pd.Series):
        vals = pd.to_numeric(x, errors="coerce").to_numpy(dtype="float64")
        idx = pd.to_datetime(pd.Series(x.index), errors="coerce")
    else:
        return pd.Series(dtype="float64")
    try:
        idx = pd.DatetimeIndex(idx).normalize()
    except Exception:
        return pd.Series(dtype="float64")
    s = pd.Series(vals, index=idx, name=col)
    s = s[~s.index.isna()]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def ncq_align_diff(a: pd.Series, b: pd.Series) -> pd.Series:
    """month 인덱스 교집합에서만 뺀다. 교집합이 비면 빈 Series(길이 0)."""
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return pd.Series(dtype="float64")
    idx = a.index.intersection(b.index)
    if len(idx) == 0:
        return pd.Series(dtype="float64")
    return (a.reindex(idx) - b.reindex(idx)).dropna().sort_index()


def ncq_cum_return(s) -> float:
    """누적수익 = ∏(1+r)-1. 결측은 계산에서 제외(0으로 채우지 않는다)."""
    x = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    if x.empty:
        return float("nan")
    return float(np.prod(1.0 + x.to_numpy(dtype="float64")) - 1.0)


def ncq_sharpe(BT) -> float:
    """BT 의 연율 Sharpe. perf_stats(스파인) 우선, 실패하면 월수익 기반으로 직접 계산."""
    R = BT.get("returns") if isinstance(BT, dict) else BT
    if not isinstance(R, pd.DataFrame) or R.empty or "ret" not in R.columns:
        return float("nan")
    try:
        st = perf_stats(R)                                    # noqa — ncq_50_backtest 제공
        if st:
            v = st.get("Sharpe", None)
            if v is not None and np.isfinite(float(v)):
                return float(v)
    except Exception:
        pass
    r = pd.to_numeric(R["ret"], errors="coerce").dropna().to_numpy(dtype="float64")
    if len(r) < 2:
        return float("nan")
    sd = float(r.std(ddof=1))
    return float(r.mean() / sd * math.sqrt(12.0)) if sd > 0 else float("nan")


def ncq_norm_cdf(z) -> float:
    """표준정규 CDF. scipy 없이도 되게 math.erfc 로 계산한다(부트스트랩 환경 편차 방지)."""
    try:
        x = float(z)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x):
        return float("nan")
    return float(0.5 * math.erfc(-x / math.sqrt(2.0)))


def ncq_p_onesided(t) -> float:
    """방향 가설(> 0)의 단측 p = 1 - Φ(t). 양측을 반으로 나누지 않고 정의대로 계산한다."""
    try:
        x = float(t)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(x):
        return float("nan")
    return float(1.0 - ncq_norm_cdf(x))


def ncq_hac(x, lags: int = None):
    """(월평균, HAC t). 표본이 12개월 미만이면 (nan, nan) — 억지로 t 를 만들지 않는다."""
    if isinstance(x, pd.Series):
        x = x.to_numpy(dtype="float64")
    arr = np.asarray(x, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if len(arr) < NCQ_MIN_MONTHS:
        return (float("nan"), float("nan"))
    L = NCQ_HAC_LAG if lags is None else int(lags)
    try:
        mu, t = hac_tstat(arr, lags=L)
        return (float(mu), float(t))
    except Exception:
        return (float("nan"), float("nan"))


def ncq_bh_adjusted(pvals) -> np.ndarray:
    """BH 보정 p값(step-up). bh_fdr 은 통과여부만 주므로 '얼마나 아슬아슬한지'를 같이 보인다."""
    p = np.asarray(pvals, dtype="float64")
    out = np.full(p.shape, np.nan, dtype="float64")
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.clip(adj, 0.0, 1.0)
    return out


def ncq_holm(pvals, alpha: float = None) -> np.ndarray:
    """Holm-Bonferroni step-down. 첫 미기각에서 즉시 멈춘다(절차 정의 그대로)."""
    a = NCQ_HOLM_ALPHA if alpha is None else float(alpha)
    p = np.asarray(pvals, dtype="float64")
    out = np.zeros(p.shape, dtype=bool)
    idx = np.where(np.isfinite(p))[0]
    if len(idx) == 0:
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    for i, j in enumerate(order):
        if p[j] <= a / max(m - i, 1):
            out[j] = True
        else:
            break
    return out


def ncq_moments(x):
    """(왜도, 첨도[정규=3]). scipy 있으면 scipy, 없으면 직접 계산."""
    arr = np.asarray(x, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if len(arr) < 4:
        return (float("nan"), float("nan"))
    try:
        from scipy import stats as _st
        return (float(_st.skew(arr)), float(_st.kurtosis(arr, fisher=False)))
    except Exception:
        mu = arr.mean()
        sd = arr.std(ddof=0)
        if not np.isfinite(sd) or sd <= 0:
            return (float("nan"), float("nan"))
        z = (arr - mu) / sd
        return (float(np.mean(z ** 3)), float(np.mean(z ** 4)))


def ncq_run(run_fn, label: str, SIG, extra=None, **kw):
    """run_fn 호출 래퍼. 실패는 삼키지 않고 **None 을 돌려주고 사유를 로그에 남긴다.**

    반환 None 을 받은 검정은 반드시 passed=None(판정불가)으로 기록한다 —
    실패한 팔을 조용히 건너뛰면 '통과'로 오해되기 때문이다.
    extra: run_fn 이 (SIG, pxm, sec, uni_obj, months) 를 직접 받는 형태일 때의 추가 위치인자.
    """
    if run_fn is None:
        LOG.warn(f"[{label}] run_fn 이 주입되지 않아 실행할 수 없습니다.")
        return None
    try:
        return run_fn(SIG, label=label, **kw)
    except TypeError as e:
        if extra:
            try:
                return run_fn(SIG, *extra, label=label, **kw)
            except Exception as e2:                                   # noqa
                LOG.error(f"[{label}] run_fn 재호출 실패 — {type(e2).__name__}: {e2}")
                return None
        LOG.error(f"[{label}] run_fn 인자 불일치 — {e}. 이 팔은 판정에서 제외합니다.")
        return None
    except Exception as e:                                            # noqa
        LOG.error(f"[{label}] 백테스트 실패 — {type(e).__name__}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  1. 원장 기록기
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_record(rid: str, name: str, passed, detail: str,
               kill: bool = False, metrics: Optional[dict] = None) -> None:
    """검정 결과를 NCQ_ROBUST 에 남기고 즉시 한 줄 출력한다.

    passed 는 True(통과) / False(실패) / None(판정불가) 세 가지다.
    ★ numpy bool 주의: `np.False_ is False` 는 False 다. `is False` 분기가 조용히 안 먹어서
      킬 게이트가 발동하지 않는 사고가 실제로 있었다. 여기서 파이썬 bool 로 강제 변환하고,
      이후 분기는 전부 ncq_is_pass / ncq_is_fail 로만 판단한다(항등비교 금지).
    """
    passed = None if passed is None else bool(passed)
    NCQ_ROBUST[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                       "kill": bool(kill), "metrics": dict(metrics or {})}
    icon = ncq_mark(passed)
    emit = LOG.warn if passed is None else (LOG.ok if passed else LOG.error)
    emit(f"[{rid}] {name} → {icon} · {detail}")
    if ncq_is_fail(passed) and kill and ncq_cfg("STOP_ON_KILL_CRITERIA", True):
        raise KillCriteria(f"[{rid}] {name} — {detail}")


# ══════════════════════════════════════════════════════════════════════════════════════════
#  2. §11.1 사전등록 가설 P1~P4 + BH-FDR + 채택 기준
# ══════════════════════════════════════════════════════════════════════════════════════════

def run_prereg_tests(SIG, BT, bench_ew, pxm, sec, uni_obj, months, run_fn) -> dict:
    """사전등록 가설 P1~P4 를 검정하고 BH-FDR(α=0.10)을 P1~P4 **전체**에 적용한다.

      P1  전략(신규커버리지 × 텍스트 z 상위 tercile) 월별 초과수익(vs Bottom-N 동일가중) > 0
      P2  z 상위 tercile − z 하위 tercile(placebo) 롱숏 스프레드 > 0
      P3  ORGANIC_ONLY 서브그룹만으로 P1 재검정 (스폰서 리포트가 만든 것이 아님을 확인)
      P4  전 이벤트 동일가중(선정 없이 이벤트 전부 보유) 대비 z 상위 스프레드 > 0
          = 텍스트 점수의 '증분' 정보. 이벤트 발생 자체의 효과와 분리한다.

    채택(§11.1) = P1·P3 가 BH-FDR 통과  AND  왕복비용 3.0% 에서도 초과수익>0
                  AND  placebo 대비 스프레드>0.

    반환: {"table": DataFrame[id,hypothesis,stat,t,p,p_bh,pass], "adopt": bool, "detail": {...}}
    표본 부족·콜백 부재는 예외 대신 passed=None + 사유. 채택 미충족은 ⭐킬 게이트이며,
    반환 dict 는 그 전에 NCQ_PREREG_RESULT 전역에 저장된다.
    """
    global NCQ_PREREG_RESULT
    LOG.banner("사전등록 검정 P1~P4 (§11.1)",
               "가설은 수익률을 보기 전에 동결되었다 · BH-FDR α=0.10 · HAC lag=12 · 단측")

    bench = ncq_month_series(bench_ew)
    strat = ncq_month_series(BT)
    if len(bench) == 0:
        LOG.warn("Bottom-N 동일가중 벤치마크가 비었습니다 — 초과수익 검정(P1·P3)은 판정불가가 됩니다.")

    S = SIG if isinstance(SIG, pd.DataFrame) else pd.DataFrame()
    has_sig = (not S.empty) and {"month", "code"}.issubset(set(S.columns))
    detail: Dict[str, Any] = {"n_month_strategy": int(len(strat)), "n_month_bench": int(len(bench))}
    rows = []                       # (id, hypothesis, stat, t, p, note)

    # ── P1 ────────────────────────────────────────────────────────────────────────────────
    ex1 = ncq_align_diff(strat, bench)
    mu1, t1 = ncq_hac(ex1)
    p1 = ncq_p_onesided(t1)
    note1 = (f"공통 {len(ex1)}개월" if len(ex1) >= NCQ_MIN_MONTHS
             else f"공통 {len(ex1)}개월 — {NCQ_MIN_MONTHS}개월 미만이라 판정불가")
    rows.append(["P1", "전략 초과수익(vs Bottom-N EW) > 0", mu1, t1, p1, note1])
    detail["P1"] = {"months": int(len(ex1)), "mu": mu1, "t": t1, "p": p1}

    # ── P2 : placebo(하위 tercile) 팔을 실제로 돌린다 ──────────────────────────────────────
    #   z 상위 팔은 본선 BT 를 그대로 쓴다(동일 설정). 불필요한 재계산을 하지 않는다.
    bt_pl = None
    if has_sig and "placebo" in S.columns and int(ncq_boolmask(S["placebo"]).sum()) > 0:
        bt_pl = ncq_run(run_fn, "P2_placebo_bottom", S, extra=(pxm, sec, uni_obj, months),
                        sel_col="placebo")
    else:
        LOG.warn("SIG 에 placebo(하위 tercile) 표식이 없거나 비어 있어 P2 를 돌릴 수 없습니다.")
    pl = ncq_month_series(bt_pl)
    d2 = ncq_align_diff(strat, pl)
    mu2, t2 = ncq_hac(d2)
    p2 = ncq_p_onesided(t2)
    note2 = (f"공통 {len(d2)}개월 · placebo 월평균 "
             f"{ncq_f(pl.mean() if len(pl) else np.nan, 'pctp')}"
             if len(d2) >= NCQ_MIN_MONTHS else
             ("placebo 팔 실행 실패 — 판정불가" if bt_pl is None
              else f"공통 {len(d2)}개월 — 표본 부족으로 판정불가"))
    rows.append(["P2", "z상위 − z하위(placebo) 스프레드 > 0", mu2, t2, p2, note2])
    detail["P2"] = {"months": int(len(d2)), "mu": mu2, "t": t2, "p": p2,
                    "arm_ok": bt_pl is not None}

    # ── P3 : ORGANIC_ONLY 서브그룹 재검정 ─────────────────────────────────────────────────
    #   ★ tercile 소속은 '전체 횡단면에서 매긴 순위'를 그대로 물려받는다. 유기적 리포트만
    #     따로 모아 다시 순위를 매기면, 실제 운용 시점에 알 수 없는 정보로 재선별하는 셈이라
    #     그 자체가 미래참조가 된다. 여기서는 '이미 선정된 것 중 유기적인 것만' 본다.
    bt_org = None
    n_org = 0
    reason3 = ""
    if has_sig and "sponsor_group" in S.columns:
        org_mask = S["sponsor_group"].astype(str).str.upper().eq("ORGANIC_ONLY")
        sel_mask = ncq_boolmask(S["selected"]) if "selected" in S.columns else pd.Series(
            True, index=S.index)
        n_org = int((org_mask & sel_mask).sum())
        n_org_m = int(S.loc[org_mask & sel_mask, "month"].nunique()) if n_org else 0
        if n_org < NCQ_MIN_EVENTS_SUB or n_org_m < NCQ_MIN_MONTHS:
            reason3 = (f"ORGANIC_ONLY 선정 이벤트 {n_org}건 / {n_org_m}개월 — "
                       f"기준({NCQ_MIN_EVENTS_SUB}건·{NCQ_MIN_MONTHS}개월) 미달이라 판정불가")
            LOG.warn("P3 표본 부족 — " + reason3)
        else:
            bt_org = ncq_run(run_fn, "P3_organic_only", S[org_mask].copy(),
                             extra=(pxm, sec, uni_obj, months))
            if bt_org is None:
                reason3 = "ORGANIC_ONLY 백테스트 실행 실패"
    else:
        reason3 = "SIG 에 sponsor_group 컬럼이 없어 스폰서 분리가 불가능"
        LOG.warn("P3 — " + reason3)
    ex3 = ncq_align_diff(ncq_month_series(bt_org), bench)
    mu3, t3 = ncq_hac(ex3)
    p3 = ncq_p_onesided(t3)
    note3 = reason3 or f"유기적 이벤트 {n_org:,}건 · 공통 {len(ex3)}개월"
    rows.append(["P3", "ORGANIC_ONLY 서브그룹 초과수익 > 0", mu3, t3, p3, note3])
    detail["P3"] = {"months": int(len(ex3)), "mu": mu3, "t": t3, "p": p3,
                    "n_events": n_org, "reason": reason3}

    # ── P4 : 전 이벤트 동일가중 대비 증분 ─────────────────────────────────────────────────
    bt_all = None
    if has_sig:
        S_all = S.copy()
        S_all["ncq_all_ev"] = True          # 선정하지 않고 이벤트를 전부 보유하는 팔
        bt_all = ncq_run(run_fn, "P4_all_events", S_all, extra=(pxm, sec, uni_obj, months),
                         sel_col="ncq_all_ev")
    all_s = ncq_month_series(bt_all)          # ★ DataFrame 을 if 로 평가하면 ValueError 가 난다
    d4 = ncq_align_diff(strat, all_s)
    mu4, t4 = ncq_hac(d4)
    p4 = ncq_p_onesided(t4)
    note4 = (f"공통 {len(d4)}개월 · 전이벤트 팔 월평균 "
             f"{ncq_f(all_s.mean() if len(all_s) else np.nan, 'pctp')}"
             if len(d4) >= NCQ_MIN_MONTHS else
             ("전 이벤트 팔 실행 실패 — 판정불가" if bt_all is None
              else f"공통 {len(d4)}개월 — 표본 부족으로 판정불가"))
    rows.append(["P4", "z상위 − 전이벤트 EW 스프레드 > 0 (텍스트 증분)", mu4, t4, p4, note4])
    detail["P4"] = {"months": int(len(d4)), "mu": mu4, "t": t4, "p": p4,
                    "arm_ok": bt_all is not None}

    # ── BH-FDR (P1~P4 전체) ───────────────────────────────────────────────────────────────
    pv = np.array([r[4] for r in rows], dtype="float64")
    try:
        fdr_pass = bh_fdr(pv, q=NCQ_FDR_Q)
    except Exception:
        fdr_pass = np.zeros(len(pv), dtype=bool)
    p_bh = ncq_bh_adjusted(pv)

    tbl = pd.DataFrame({
        "id": [r[0] for r in rows],
        "hypothesis": [r[1] for r in rows],
        "stat": [float(r[2]) if r[2] is not None else np.nan for r in rows],
        "t": [float(r[3]) if r[3] is not None else np.nan for r in rows],
        "p": pv,
        "p_bh": p_bh,
        "pass": [(None if not np.isfinite(pv[i]) else bool(fdr_pass[i])) for i in range(len(rows))],
    })
    tbl["note"] = [r[5] for r in rows]

    LOG.table(
        [[tbl.at[i, "id"], _trunc(tbl.at[i, "hypothesis"], 42),
          ncq_f(tbl.at[i, "stat"], "pctp"), ncq_f(tbl.at[i, "t"], "t"),
          ncq_f(tbl.at[i, "p"], "p"), ncq_f(tbl.at[i, "p_bh"], "p"),
          ncq_mark(tbl.at[i, "pass"]), _trunc(tbl.at[i, "note"], 44)] for i in tbl.index],
        ["ID", "가설", "월평균", "HAC t", "p(단측)", "p(BH)", "FDR 판정", "비고"],
        ["c", "l", "r", "r", "r", "r", "c", "l"], maxw=46,
        title=f"사전등록 가설 검정 (BH-FDR α={NCQ_FDR_Q:.2f}, P1~P4 동시 보정)")

    for i in tbl.index:
        rid = tbl.at[i, "id"]
        ncq_record(rid, tbl.at[i, "hypothesis"], tbl.at[i, "pass"],
                   f"월평균 {ncq_f(tbl.at[i,'stat'],'pctp')} · HAC t={ncq_f(tbl.at[i,'t'],'t')} · "
                   f"p={ncq_f(tbl.at[i,'p'],'p')} → BH p={ncq_f(tbl.at[i,'p_bh'],'p')}. "
                   f"{tbl.at[i,'note']}",
                   kill=False,
                   metrics={"mu": float(tbl.at[i, "stat"]), "t": float(tbl.at[i, "t"]),
                            "p": float(tbl.at[i, "p"]), "p_bh": float(tbl.at[i, "p_bh"])})

    # ── 채택 조건 3종 (§11.1) ─────────────────────────────────────────────────────────────
    # 조건 ①  P1·P3 BH-FDR 동시 통과
    def _verdict_of(hid):
        """행 순서에 의존하지 않고 id 로 판정을 꺼낸다. None(판정불가)을 False 로 뭉개지 않는다."""
        sel = tbl.loc[tbl["id"] == hid, "pass"]
        if len(sel) == 0:
            return None
        v = sel.iloc[0]
        return None if v is None else bool(v)

    c1_p1, c1_p3 = _verdict_of("P1"), _verdict_of("P3")
    c1 = None if (c1_p1 is None or c1_p3 is None) else bool(c1_p1 and c1_p3)
    c1_txt = (f"P1 {ncq_mark(c1_p1)} · P3 {ncq_mark(c1_p3)}"
              + (f" ({reason3})" if reason3 else ""))

    # 조건 ②  왕복비용 3.0% 스트레스에서도 초과수익 > 0 (직접 돌린다 — 추정하지 않는다)
    bt_cost = None
    if has_sig:
        bt_cost = ncq_run(run_fn, "ADOPT_cost300bp", S, extra=(pxm, sec, uni_obj, months),
                          cost_roundtrip=NCQ_COST_STRESS)
    ex_c = ncq_align_diff(ncq_month_series(bt_cost), bench)
    mu_c, t_c = ncq_hac(ex_c)
    c2 = None if not np.isfinite(mu_c) else bool(mu_c > 0)
    c2_txt = (f"왕복 {NCQ_COST_STRESS*100:.1f}% 시 월평균 초과 {ncq_f(mu_c,'pctp')} "
              f"(HAC t={ncq_f(t_c,'t')}, {len(ex_c)}개월)" if np.isfinite(mu_c)
              else f"왕복 {NCQ_COST_STRESS*100:.1f}% 시나리오 실행 실패/표본 부족 — 판정불가")
    detail["cost_stress"] = {"cost": NCQ_COST_STRESS, "mu": mu_c, "t": t_c,
                             "months": int(len(ex_c))}

    # 조건 ③  placebo 대비 스프레드 > 0 (P2 의 부호 조건 — 유의성이 아니라 부호를 본다)
    c3 = None if not np.isfinite(mu2) else bool(mu2 > 0)
    c3_txt = (f"placebo 대비 월평균 스프레드 {ncq_f(mu2,'pctp')} (HAC t={ncq_f(t2,'t')})"
              if np.isfinite(mu2) else "placebo 팔 부재 — 판정불가")

    # ★ '검정해서 떨어진 것'과 '검정 자체를 못 한 것'을 구분한다.
    #   하나라도 명시적 False → 채택 실패(킬 게이트 발동 대상).
    #   False 는 없는데 판정불가가 섞임 → passed=None. 데이터가 없어서 결론을 못 냈을 뿐인데
    #   킬 기준으로 파이프라인을 끊으면, 정작 원인(구조적 리스크 표)을 못 보게 된다.
    conds = [c1, c2, c3]
    if any(ncq_is_fail(c) for c in conds):
        adopt_verdict = False
    elif any(c is None for c in conds):
        adopt_verdict = None
    else:
        adopt_verdict = True
    adopt = ncq_is_pass(adopt_verdict)           # 채택은 세 조건이 '모두 명시적 통과'일 때만
    LOG.table(
        [["①", "P1·P3 BH-FDR 동시 통과", ncq_mark(c1), _trunc(c1_txt, 60)],
         ["②", f"왕복비용 {NCQ_COST_STRESS*100:.1f}% 에서도 초과수익 > 0", ncq_mark(c2),
          _trunc(c2_txt, 60)],
         ["③", "placebo(하위 tercile) 대비 스프레드 > 0", ncq_mark(c3), _trunc(c3_txt, 60)],
         ["=", "최종 채택 여부",
          ("✔ 채택" if adopt else ("✘ 미채택" if ncq_is_fail(adopt_verdict) else "— 판정불가")),
          "세 조건이 모두 명시적으로 충족돼야 채택한다"]],
        ["", "조건 (§11.1)", "판정", "관측"], ["c", "l", "c", "l"], maxw=62,
        title="사전등록 채택 기준 — 하나라도 미충족이면 채택하지 않는다")

    detail["conditions"] = {"c1_fdr_p1_p3": c1, "c2_cost300bp": c2, "c3_placebo_spread": c3}
    out = {"table": tbl, "adopt": adopt, "detail": detail}
    NCQ_PREREG_RESULT = out               # ★ 킬 게이트로 예외가 올라가도 근거는 남긴다

    if ncq_is_fail(adopt_verdict):
        LOG.banner("⛔ 사전등록 채택 기준 미충족",
                   "파라미터를 바꿔 통과시키지 마십시오 — 미채택도 결론입니다(§16.3)")
    elif adopt_verdict is None:
        LOG.warn("사전등록 채택 여부를 판정할 수 없습니다(입력·표본 부족). "
                 "'판정불가'는 '통과'가 아니며, 이 상태의 성과 수치를 근거로 삼으면 안 됩니다.")
    ncq_record("ADOPT", "사전등록 채택 기준 (§11.1)", adopt_verdict,
               f"① {ncq_mark(c1)} / ② {ncq_mark(c2)} / ③ {ncq_mark(c3)}. "
               f"{c1_txt} | {c2_txt} | {c3_txt}",
               kill=True,
               metrics={"c1": c1, "c2": c2, "c3": c3, "adopt": adopt,
                        "mu_cost300bp": mu_c, "mu_placebo_spread": mu2})
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  3. §11.2 통계 스위트 — 부트스트랩 / 순열 / 워크포워드 / PBO / DSR / Holm
# ══════════════════════════════════════════════════════════════════════════════════════════

def ncq_block_bootstrap(x, block: int = None, n_iter: int = None, seed=None):
    """원형(circular) 블록 부트스트랩. 반환 (경험적 p(평균≤0), 부트평균 배열, 실제평균).

    자기상관이 있는 월별 초과수익에 iid 부트스트랩을 쓰면 p 값이 과소평가된다.
    12개월 오버랩 보유 구조상 블록 12개월이 자연스러운 선택이다.
    """
    # 0/음수가 들어오면 math.ceil(n/b) 에서 ZeroDivisionError, 빈 재표집에서 nan 경고가 난다.
    b = max(1, int(NCQ_BOOT_BLOCK if block is None else block))
    n_it = max(1, int(NCQ_BOOT_ITER if n_iter is None else n_iter))
    arr = np.asarray(pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(), dtype="float64")
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < max(NCQ_MIN_MONTHS, b):
        return (float("nan"), np.array([], dtype="float64"), float("nan"))
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    nb = int(math.ceil(n / b))
    starts = rng.integers(0, n, size=(n_it, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]) % n          # 원형 wrap
    idx = idx.reshape(n_it, nb * b)[:, :n]
    means = arr[idx].mean(axis=1)
    return (float((means <= 0.0).mean()), means, float(arr.mean()))


def ncq_permutation_spread(SIG, n_iter: int = None, pool_df=None,
                           sel_col: str = "selected", seed=None):
    """월별 fwd_ret 기반 '근사 스프레드'의 순열 검정. 반환 dict.

    ★ 근사임을 숨기지 않는다:
      ① 백테스트(12개월 오버랩 보유)를 1000회 돌릴 수 없으므로, 월별 1개월 fwd_ret 로
         (선택군 평균 − 풀 평균) 스프레드를 계산한다. 절대 수준은 백테스트와 다르다.
      ② 재배치 풀은 pool_df(유니버스×fwd_ret)가 주어지면 유니버스, 없으면 '그 달의 이벤트 풀'.
         후자면 이 검정이 반증하는 것은 "텍스트 z 가 이벤트 중에서 고르는 능력"이지
         "이벤트 발생 자체의 정보"가 아니다.
      ③ 재배치는 '같은 달, 같은 개수'를 유지한다(월별 표본수 차이가 결과를 만들지 않게).
    """
    # n_it 이 0 이면 귀무분포가 빈 배열이 되어 np.quantile 이 예외를 던진다.
    n_it = max(1, int(NCQ_PERM_ITER if n_iter is None else n_iter))
    out = {"real": float("nan"), "p": float("nan"), "q95": float("nan"),
           "n_month": 0, "pool_src": "—", "null": np.array([], dtype="float64")}
    if not isinstance(SIG, pd.DataFrame) or SIG.empty:
        return out
    if not {"month", "fwd_ret"}.issubset(set(SIG.columns)) or sel_col not in SIG.columns:
        return out

    S = SIG[["month", "fwd_ret", sel_col]].copy()
    S["fwd_ret"] = pd.to_numeric(S["fwd_ret"], errors="coerce")
    S["_sel"] = ncq_boolmask(S[sel_col]).to_numpy()

    use_uni = (isinstance(pool_df, pd.DataFrame) and not pool_df.empty
               and {"month", "fwd_ret"}.issubset(set(pool_df.columns)))
    if use_uni:
        P = pool_df[["month", "fwd_ret"]].copy()
        P["fwd_ret"] = pd.to_numeric(P["fwd_ret"], errors="coerce")
        out["pool_src"] = "유니버스(pool_df 제공)"
    else:
        P = S[["month", "fwd_ret"]].copy()
        out["pool_src"] = "그 달의 이벤트 풀 (유니버스 수익 미제공)"

    pools = {m: g["fwd_ret"].dropna().to_numpy(dtype="float64")
             for m, g in P.groupby("month", observed=True)}
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    real_acc: List[float] = []
    null_acc = np.zeros(n_it, dtype="float64")
    used = 0
    for m, g in S.groupby("month", observed=True):
        sel = g.loc[g["_sel"] & g["fwd_ret"].notna(), "fwd_ret"].to_numpy(dtype="float64")
        k = len(sel)
        pool = pools.get(m, np.array([], dtype="float64"))
        if k < 1 or len(pool) < k + 5:            # 풀이 선택군과 사실상 같으면 재배치가 무의미
            continue
        pm = float(pool.mean())
        real_acc.append(float(sel.mean()) - pm)
        r = rng.random((n_it, len(pool)))
        idx = np.argpartition(r, k - 1, axis=1)[:, :k]
        null_acc += pool[idx].mean(axis=1) - pm
        used += 1
    if used == 0:
        return out
    null = null_acc / float(used)
    real = float(np.mean(real_acc))
    out.update({"real": real, "null": null, "n_month": used,
                "p": float((null >= real).mean()),
                "q95": float(np.quantile(null, 0.95))})
    return out


def ncq_walk_forward(ex: pd.Series, is_m: int = None, oos_m: int = None, step_m: int = None):
    """롤링 워크포워드. 반환 (행 리스트, 요약 dict).

    ★ 이 전략에는 최적화할 파라미터가 없다(렉시콘·tercile·보유기간 모두 사전등록 동결).
      따라서 IS 구간은 '학습'이 아니라 **관측만** 하고, OOS 성과를 그대로 보고한다.
      없는 최적화를 있는 척하지 않기 위해 이 사실을 표 제목과 로그에 명시한다.
    """
    # ★ step 이 0/음수면 while 루프가 영원히 돌면서 파이프라인이 멈춘 것처럼 보인다. 반드시 ≥1.
    I = max(1, int(NCQ_WF_IS_M if is_m is None else is_m))
    O = max(1, int(NCQ_WF_OOS_M if oos_m is None else oos_m))
    T_ = max(1, int(NCQ_WF_STEP_M if step_m is None else step_m))
    e = pd.to_numeric(pd.Series(ex), errors="coerce").dropna().sort_index()
    n = len(e)
    rows: List[dict] = []
    if n < I + O:
        return (rows, {"n_win": 0, "reason": f"{n}개월 — IS {I} + OOS {O} 개월에 못 미침"})
    s = I
    while s + O <= n:
        is_x = e.iloc[s - I:s].to_numpy(dtype="float64")
        oo = e.iloc[s:s + O]
        oo_x = oo.to_numpy(dtype="float64")
        # OOS 가 12개월뿐이라 lag=12 는 자유도를 다 먹는다. 표본에 맞춰 lag 를 줄인다(n//4).
        lag = max(1, min(NCQ_HAC_LAG, len(oo_x) // 4))
        mu_o, t_o = ncq_hac(oo_x, lags=lag)
        rows.append({
            "구간": f"{pd.Timestamp(oo.index[0]).strftime('%Y-%m')}~"
                    f"{pd.Timestamp(oo.index[-1]).strftime('%Y-%m')}",
            "IS월수": int(len(is_x)),
            # 전부 NaN 인 구간에서 np.nanmean 은 경고를 뿜는다 — 유한값만 남기고 없으면 NaN.
            "IS월평균": (float(is_x[np.isfinite(is_x)].mean())
                        if np.isfinite(is_x).any() else float("nan")),
            "OOS월수": int(len(oo_x)), "OOS월평균": mu_o, "OOS_t": t_o,
            "OOS누적": ncq_cum_return(oo),
        })
        s += T_
    pos = sum(1 for r in rows if np.isfinite(r["OOS월평균"]) and r["OOS월평균"] > 0)
    allo = np.array([r["OOS월평균"] for r in rows], dtype="float64")
    allo = allo[np.isfinite(allo)]
    summ = {"n_win": len(rows), "n_pos": pos,
            "mu_all": float(allo.mean()) if len(allo) else float("nan"),
            "hac_lag": max(1, min(NCQ_HAC_LAG, O // 4))}
    return (rows, summ)


def ncq_pbo_cscv(M, S: int = None, max_combos: int = None, seed=None):
    """CSCV 기반 PBO. 반환 (pbo, n_combos, approx, note).

    성과 벡터가 2개 이상(민감도 조합 곡선)이면 정식 CSCV:
      IS 에서 최고인 조합을 고르고, 그 조합의 OOS 상대순위 로짓이 ≤0 인 비율이 PBO.
    벡터가 1개뿐이면 '전략 선택' 자체가 없으므로 정식 CSCV 가 성립하지 않는다.
      이때는 시계열 분할 근사(IS 평균>0 인데 OOS 평균≤0 인 비율)를 쓰고 approx=True 로 표시한다.
    """
    import itertools
    s_n = int(NCQ_CSCV_S if S is None else S)
    cap = int(NCQ_CSCV_MAX_COMBOS if max_combos is None else max_combos)
    if not isinstance(M, pd.DataFrame) or M.empty:
        return (float("nan"), 0, True, "성과 행렬이 비어 계산 불가")
    A = M.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    A = A.dropna(axis=1, how="all")
    if A.empty:
        return (float("nan"), 0, True, "유효 성과 벡터 없음")
    X = A.to_numpy(dtype="float64")
    T, N = X.shape
    if s_n % 2 == 1:                       # 짝수 분할이어야 IS/OOS 를 반씩 나눌 수 있다
        s_n -= 1
    if s_n < 2:                            # ★ 0 이면 np.array_split 이 ValueError 를 던진다
        return (float("nan"), 0, True, f"분할 수 S={s_n} — 2 미만이라 CSCV 불가")
    if T < s_n * 3:
        return (float("nan"), 0, True, f"관측 {T}개월 < 분할 {s_n}×3 — 분할 불가")
    blocks = np.array_split(np.arange(T), s_n)
    combos = list(itertools.combinations(range(s_n), s_n // 2))
    n_total = len(combos)
    rng = np.random.default_rng(int(ncq_cfg("SEED", 0)) if seed is None else int(seed))
    sampled = False
    if n_total > cap:
        pick = rng.choice(n_total, size=cap, replace=False)
        combos = [combos[i] for i in sorted(pick.tolist())]
        sampled = True
    # 표본추출 사실을 반드시 남긴다 — 전수 계산인 척하면 PBO 의 신뢰구간을 오해하게 된다.
    note = (f"C({s_n},{s_n//2})={n_total:,} 조합 중 {len(combos):,}개를 무작위 표본추출"
            if sampled else f"C({s_n},{s_n//2})={n_total:,} 조합 전수")

    def _sr(a: np.ndarray) -> np.ndarray:
        mu = np.nanmean(a, axis=0)
        sd = np.nanstd(a, axis=0, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = np.where(sd > 0, mu / np.where(sd > 0, sd, np.nan), np.nan)
        return np.where(np.isfinite(v), v, -np.inf)

    losses = 0
    valid = 0
    approx = (N < 2)
    for cb in combos:
        is_idx = np.concatenate([blocks[j] for j in cb])
        oos_idx = np.concatenate([blocks[j] for j in range(s_n) if j not in cb])
        if len(is_idx) < 6 or len(oos_idx) < 6:
            continue
        Xi, Xo = X[is_idx, :], X[oos_idx, :]
        if approx:
            mi, mo = float(np.nanmean(Xi)), float(np.nanmean(Xo))
            if not (np.isfinite(mi) and np.isfinite(mo)):
                continue
            valid += 1
            losses += int(mi > 0 and mo <= 0)
            continue
        sr_i, sr_o = _sr(Xi), _sr(Xo)
        if not np.isfinite(sr_i).any():
            continue
        best = int(np.argmax(sr_i))
        # 동점은 argsort 로 임의 해소된다(순위 자체가 아니라 분포의 위치만 쓰므로 영향 미미).
        rank = int(np.argsort(np.argsort(sr_o))[best]) + 1
        w = rank / float(N + 1)
        w = min(max(w, 1e-9), 1 - 1e-9)
        valid += 1
        losses += int(math.log(w / (1.0 - w)) <= 0.0)
    if valid == 0:
        return (float("nan"), 0, approx, note + " · 유효 분할 없음")
    return (losses / float(valid), valid, approx, note)


def ncq_dsr(sharpe, n: int, skew, kurt, n_trials: int) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado).

    n_trials 는 **실제 실행한 파라미터 조합 수**여야 한다. 작게 적으면 DSR 이 부풀려진다 —
    이 프로젝트에서는 민감도 실행 수(기본 9)를 그대로 넣는다.
    sharpe 는 월별(비연율) Sharpe.
    """
    try:
        sr = float(sharpe)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(sr) or n is None or int(n) < NCQ_MIN_MONTHS:
        return float("nan")
    n = int(n)
    N = max(int(n_trials), 2)
    e = 0.5772156649015329
    sr0 = (math.sqrt(2.0 * math.log(N)) * (1.0 - e) +
           e * math.sqrt(2.0 * math.log(N * math.e))) / math.sqrt(n)
    sk = float(skew) if (skew is not None and np.isfinite(skew)) else 0.0
    ku = float(kurt) if (kurt is not None and np.isfinite(kurt)) else 3.0
    denom = math.sqrt(max(1e-12, 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2))
    return ncq_norm_cdf((sr - sr0) * math.sqrt(max(n - 1, 1)) / denom)


def run_stat_suite(BT, bench_ew, SIG, months, run_fn, n_trials: int = 9,
                   perf_matrix: Optional[pd.DataFrame] = None,
                   sens: Optional[pd.DataFrame] = None,
                   pool_df: Optional[pd.DataFrame] = None) -> dict:
    """§11.2 통계 스위트. 각 검정을 ncq_record 로 기록하고 dict 로도 반환한다.

    perf_matrix : 행=월, 열=성과벡터(민감도 조합) 인 수익 행렬. 없으면 NCQ_SENS_CURVES 를 쓰고,
                  그것도 없으면 단일 시계열 분할 '근사'로 PBO 를 계산하고 근사임을 명시한다.
    sens        : run_sensitivity 반환 표(Holm 입력). 없으면 NCQ_SENS_TABLE 을 쓴다.
    pool_df     : 순열 검정 재배치 풀(month,fwd_ret). 없으면 이벤트 풀로 근사한다.
    표본 부족은 예외가 아니라 passed=None + 사유.
    """
    LOG.banner("통계 스위트 (§11.2)",
               "블록부트스트랩 · 순열 · 워크포워드 · PBO(CSCV) · DSR · Holm-Bonferroni")
    try:                                   # 호출부가 None/문자열을 넘겨도 DSR 이 죽지 않게
        n_trials = max(1, int(n_trials))
    except (TypeError, ValueError):
        LOG.warn(f"n_trials={n_trials!r} 를 정수로 읽을 수 없어 기본값 9 를 씁니다.")
        n_trials = 9
    bench = ncq_month_series(bench_ew)
    strat = ncq_month_series(BT)
    ex = ncq_align_diff(strat, bench)
    out: Dict[str, Any] = {"n_month": int(len(ex))}

    # ── S1. 블록 부트스트랩 ───────────────────────────────────────────────────────────────
    p_b, boots, real_mu = ncq_block_bootstrap(ex)
    if not np.isfinite(p_b):
        ncq_record("S1", f"블록 부트스트랩 (블록 {NCQ_BOOT_BLOCK}개월 × {NCQ_BOOT_ITER:,}회)", None,
                   f"초과수익 표본 {len(ex)}개월 — 블록 {NCQ_BOOT_BLOCK}개월/최소 "
                   f"{NCQ_MIN_MONTHS}개월 요건에 미달하여 판정불가")
    else:
        ncq_record("S1", f"블록 부트스트랩 (블록 {NCQ_BOOT_BLOCK}개월 × {NCQ_BOOT_ITER:,}회)",
                   bool(p_b < 0.05),
                   f"실제 월평균 초과 {ncq_f(real_mu,'pctp')} · 재표집 평균 "
                   f"{ncq_f(float(np.mean(boots)),'pctp')} · 경험적 p(평균≤0)={ncq_f(p_b,'p')} "
                   f"({len(ex)}개월). " +
                   ("자기상관을 보정해도 평균이 0보다 큽니다."
                    if p_b < 0.05 else
                    "★ 자기상관 보정 재표집에서 평균>0 이 유의하지 않습니다."),
                   metrics={"p": p_b, "mu": real_mu, "n": int(len(ex))})
    out["bootstrap"] = {"p": p_b, "mu": real_mu, "n": int(len(ex))}

    # ── S2. 순열 검정 ─────────────────────────────────────────────────────────────────────
    LOG.info("순열 검정은 계산량을 줄이기 위해 백테스트 대신 **월별 fwd_ret 기반 근사 스프레드**"
             "(선택군 평균 − 풀 평균)를 사용합니다. 절대 수준은 백테스트 수치와 다릅니다.")
    perm = ncq_permutation_spread(SIG, n_iter=NCQ_PERM_ITER, pool_df=pool_df)
    LOG.info(f"순열 재배치 풀 = {perm['pool_src']} · '같은 달, 같은 개수' 유지 · "
             f"유효 {perm['n_month']}개월")
    if not np.isfinite(perm["real"]) or perm["n_month"] < NCQ_MIN_MONTHS:
        ncq_record("S2", f"순열 검정 (월내 재배치 {NCQ_PERM_ITER:,}회)", None,
                   f"유효 {perm['n_month']}개월 — 재배치 가능한 월이 부족하여 판정불가 "
                   f"(풀: {perm['pool_src']})")
    else:
        passed = bool(perm["real"] > perm["q95"])
        ncq_record("S2", f"순열 검정 (월내 재배치 {NCQ_PERM_ITER:,}회)", passed,
                   f"실제 근사 스프레드 {ncq_f(perm['real'],'pctp')} vs 귀무 95%ile "
                   f"{ncq_f(perm['q95'],'pctp')} (p={ncq_f(perm['p'],'p')}, "
                   f"{perm['n_month']}개월, 풀={perm['pool_src']}). " +
                   ("무작위 선택과 구분됩니다." if passed else
                    "★ 무작위 선택과 통계적으로 구분되지 않습니다 — 텍스트 z 의 선별력 근거가 약합니다."),
                   metrics={"real": perm["real"], "q95": perm["q95"], "p": perm["p"],
                            "n_month": perm["n_month"]})
    out["permutation"] = {k: perm[k] for k in ("real", "p", "q95", "n_month", "pool_src")}

    # ── S3. 워크포워드 ────────────────────────────────────────────────────────────────────
    wf_rows, wf_sum = ncq_walk_forward(ex)
    LOG.info("워크포워드 주의 — 이 전략에는 최적화되는 파라미터가 없습니다(렉시콘·tercile·보유기간 "
             "모두 사전등록 동결). 따라서 IS 는 '관측만' 하고 OOS 성과를 그대로 보고합니다. "
             "없는 최적화를 있는 척하지 않습니다.")
    if wf_rows:
        LOG.table([[r["구간"], f"{r['IS월수']}", ncq_f(r["IS월평균"], "pctp"),
                    f"{r['OOS월수']}", ncq_f(r["OOS월평균"], "pctp"), ncq_f(r["OOS_t"], "t"),
                    ncq_f(r["OOS누적"], "pct")] for r in wf_rows],
                  ["OOS 구간", "IS월", "IS월평균(참고)", "OOS월", "OOS월평균", "OOS HAC t", "OOS누적"],
                  ["l", "r", "r", "r", "r", "r", "r"],
                  title=f"워크포워드 — IS {NCQ_WF_IS_M//12}년 관측 / OOS 롤링 {NCQ_WF_OOS_M//12}년 "
                        f"({NCQ_WF_STEP_M//12}년 스텝, OOS HAC lag={wf_sum.get('hac_lag','—')})")
        passed = bool(wf_sum["n_pos"] * 2 > wf_sum["n_win"] and
                      np.isfinite(wf_sum["mu_all"]) and wf_sum["mu_all"] > 0)
        ncq_record("S3", "워크포워드 (OOS 롤링)", passed,
                   f"OOS 구간 {wf_sum['n_win']}개 중 {wf_sum['n_pos']}개가 양(+) · "
                   f"전 OOS 월평균 {ncq_f(wf_sum['mu_all'],'pctp')}. " +
                   ("OOS 에서 성과가 과반 구간 유지됩니다." if passed else
                    "★ OOS 구간 과반에서 초과수익이 유지되지 않습니다."),
                   metrics=wf_sum)
    else:
        ncq_record("S3", "워크포워드 (OOS 롤링)", None,
                   f"판정불가 — {wf_sum.get('reason','표본 부족')}")
    out["walk_forward"] = {"rows": wf_rows, "summary": wf_sum}

    # ── S4. PBO (CSCV) ────────────────────────────────────────────────────────────────────
    M = perf_matrix
    src_note = "호출부가 제공한 성과 행렬"
    if not isinstance(M, pd.DataFrame) or M.empty:
        if NCQ_SENS_CURVES:
            M = pd.DataFrame(dict(NCQ_SENS_CURVES)).sort_index()
            src_note = f"민감도 {M.shape[1]}조합 곡선(NCQ_SENS_CURVES)"
        else:
            M = ex.to_frame("base") if len(ex) else pd.DataFrame()
            src_note = "단일 전략 시계열 — 정식 CSCV 불가"
    pbo, n_cb, approx, cb_note = ncq_pbo_cscv(M, S=NCQ_CSCV_S, max_combos=NCQ_CSCV_MAX_COMBOS)
    LOG.info(f"PBO 입력 = {src_note} · {cb_note}" + (" · ★근사 경로" if approx else ""))
    if not np.isfinite(pbo):
        ncq_record("S4", f"PBO (CSCV, S={NCQ_CSCV_S})", None,
                   f"판정불가 — {cb_note} ({src_note})")
    else:
        ncq_record("S4", f"PBO (CSCV, S={NCQ_CSCV_S})", bool(pbo < 0.5),
                   f"PBO={ncq_f(pbo)} (<0.5 권장) · 유효 분할 {n_cb:,} · 입력: {src_note}"
                   + ("  ★성과 벡터가 1개뿐이라 정식 CSCV 대신 시계열 분할 **근사**입니다 — "
                      "이 값은 '조합 선택 과적합'이 아니라 '구간 불안정성'을 잰 것입니다."
                      if approx else "") + ". "
                   + ("과적합 위험이 낮습니다." if pbo < 0.5 else
                      "★ 과적합 위험이 낮지 않습니다."),
                   metrics={"pbo": pbo, "n_combos": n_cb, "approx": approx, "source": src_note})
    out["pbo"] = {"pbo": pbo, "n_combos": n_cb, "approx": approx, "source": src_note,
                  "note": cb_note}

    # ── S5. DSR ───────────────────────────────────────────────────────────────────────────
    r = pd.to_numeric(pd.Series(strat), errors="coerce").dropna().to_numpy(dtype="float64")
    if len(r) < NCQ_MIN_MONTHS:
        ncq_record("S5", f"DSR (Deflated Sharpe, 시행 {int(n_trials)}회)", None,
                   f"월수 {len(r)} — {NCQ_MIN_MONTHS}개월 미만이라 판정불가")
        dsr = float("nan")
        sr_m = float("nan")
    else:
        sd = float(r.std(ddof=1))
        sr_m = float(r.mean() / sd) if sd > 0 else float("nan")
        sk, ku = ncq_moments(r)
        dsr = ncq_dsr(sr_m, len(r), sk, ku, int(n_trials))
        ncq_record("S5", f"DSR (Deflated Sharpe, 시행 {int(n_trials)}회)",
                   (None if not np.isfinite(dsr) else bool(dsr > 0.95)),
                   f"월Sharpe {ncq_f(sr_m)} (왜도 {ncq_f(sk)}, 첨도 {ncq_f(ku)}) · "
                   f"DSR={ncq_f(dsr)} (>0.95 권장) · 시행횟수는 실제 실행한 민감도 조합 수 "
                   f"{int(n_trials)} 를 그대로 넣었습니다(작게 적으면 DSR 이 부풀려집니다). " +
                   ("" if not np.isfinite(dsr) else
                    ("다중시행을 감안해도 Sharpe 가 유의합니다." if dsr > 0.95 else
                     "★ 다중시행 보정 후 Sharpe 의 유의성이 남지 않습니다.")),
                   metrics={"dsr": dsr, "sharpe_m": sr_m, "n_trials": int(n_trials)})
    out["dsr"] = {"dsr": dsr, "sharpe_m": sr_m, "n_trials": int(n_trials)}

    # ── S6. Holm-Bonferroni (민감도 스윕) ─────────────────────────────────────────────────
    T = sens if isinstance(sens, pd.DataFrame) else NCQ_SENS_TABLE
    if not isinstance(T, pd.DataFrame) or T.empty or "HAC t" not in T.columns:
        ncq_record("S6", "Holm-Bonferroni (민감도 스윕 다중검정)", None,
                   "판정불가 — 민감도 표가 아직 없습니다(run_sensitivity 를 먼저 실행하세요).")
        out["holm"] = {"n": 0}
    else:
        tv = pd.to_numeric(T["HAC t"], errors="coerce").to_numpy(dtype="float64")
        pv = np.array([ncq_p_onesided(x) for x in tv], dtype="float64")
        rej = ncq_holm(pv, NCQ_HOLM_ALPHA)
        labels = (T["combo"].astype(str).tolist() if "combo" in T.columns
                  else [f"C{i}" for i in range(len(T))])
        axis = (T["축"].astype(str).tolist() if "축" in T.columns else ["—"] * len(T))
        val = (T["값"].astype(str).tolist() if "값" in T.columns else ["—"] * len(T))
        LOG.table([[labels[i], axis[i], val[i], ncq_f(tv[i], "t"), ncq_f(pv[i], "p"),
                    ("✔ 기각" if rej[i] else ("—" if not np.isfinite(pv[i]) else "✘ 미기각"))]
                   for i in range(len(T))],
                  ["조합", "축", "값", "HAC t", "p(단측)", f"Holm α={NCQ_HOLM_ALPHA:.2f}"],
                  ["l", "l", "r", "r", "r", "c"],
                  title="Holm-Bonferroni — 민감도 조합 전체에 대한 다중검정 보정")
        n_ok = int(rej.sum())
        n_val = int(np.isfinite(pv).sum())
        ncq_record("S6", "Holm-Bonferroni (민감도 스윕 다중검정)",
                   (None if n_val == 0 else bool(n_ok > 0)),
                   (f"유효 {n_val}조합 중 {n_ok}개가 Holm(α={NCQ_HOLM_ALPHA:.2f}) 하에서 기각. "
                    + ("가장 보수적인 보정에서도 살아남는 조합이 있습니다." if n_ok > 0 else
                       "★ Holm 보정 후 살아남는 조합이 하나도 없습니다 — 민감도 전반이 약합니다."))
                   if n_val else "유효한 t 통계량이 없어 판정불가",
                   metrics={"n_reject": n_ok, "n_valid": n_val})
        out["holm"] = {"n": n_val, "n_reject": n_ok,
                       "p": pv.tolist(), "reject": rej.tolist()}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  4. §15-5 민감도 — 81조합 전수 금지. 기본값 1 + 각 축 단독 변동 8 = 9조합
# ══════════════════════════════════════════════════════════════════════════════════════════

def run_sensitivity(ctx, months, build_sig_fn, run_fn) -> pd.DataFrame:
    """민감도 9조합. 축을 동시에 흔들지 않는다(§15-5: 81조합 전수 금지).

    축: ADV(NCQ_SENS_ADV) / tercile(NCQ_SENS_TOPPCT) / 보유기간(NCQ_SENS_HOLD) / 비용(NCQ_SENS_COST)
    기본값과 같은 값은 건너뛰어 정확히 9조합(= 1 + 2×4)이 되게 한다.

    ★ 재계산 최소화: ADV·tercile 축은 **신호를 다시 만들어야 하고**, 보유기간·비용 축은
      **백테스트만 다시 돌리면 된다.** (top_pct, min_adv) 를 키로 SIG 를 캐시하고,
      ctx 에 본선 SIG 가 있으면 기본 조합의 신호 생성은 아예 건너뛴다.

    반환: DataFrame[combo,축,값,월수,월평균초과,HAC t,Sharpe,누적,판정]
          (수치 컬럼은 float 로 유지 — Holm 이 'HAC t' 를 그대로 읽는다.
           실제 실행 수는 df.attrs 와 로그에 남긴다.)
    """
    global NCQ_SENS_TABLE
    LOG.banner("민감도 검사 (§15-5)",
               "기본값 1조합 + 각 축 단독 변동 8조합 = 9조합 · 축 동시 변동(81조합)은 금지")

    base = {"adv": float(ncq_cfg("NCQ_MIN_ADV", 100_000_000)),
            "top": float(ncq_cfg("NCQ_TERCILE", 1.0 / 3.0)),
            "hold": int(ncq_cfg("NCQ_HOLD_MONTHS", 12)),
            "cost": float(ncq_cfg("NCQ_COST_ROUNDTRIP", 0.018))}
    axes = [("ADV", "adv", list(ncq_cfg("NCQ_SENS_ADV", [base["adv"]])),
             lambda v: f"{float(v)/1e8:.1f}억원"),
            ("tercile", "top", list(ncq_cfg("NCQ_SENS_TOPPCT", [base["top"]])),
             lambda v: f"상위 {float(v)*100:.1f}%"),
            ("보유기간", "hold", list(ncq_cfg("NCQ_SENS_HOLD", [base["hold"]])),
             lambda v: f"{int(v)}개월"),
            ("비용", "cost", list(ncq_cfg("NCQ_SENS_COST", [base["cost"]])),
             lambda v: f"왕복 {float(v)*100:.1f}%")]

    plans: List[Tuple[str, str, str, dict]] = [("C0", "기본값", "—", dict(base))]
    for ax_name, key, vals, fmt in axes:
        for v in vals:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if abs(fv - float(base[key])) <= 1e-12:      # 기본값과 같은 값은 건너뛴다
                continue
            p = dict(base)
            p[key] = int(round(fv)) if key == "hold" else fv
            plans.append((f"C{len(plans)}", ax_name, fmt(fv), p))
    if len(plans) != 9:
        LOG.warn(f"민감도 조합이 {len(plans)}개입니다(설계값 9). NCQ_SENS_* 목록에 기본값이 "
                 f"포함되어 있는지 확인하세요 — 개수를 억지로 맞추지 않고 실제 값을 그대로 씁니다.")

    bench = ncq_month_series(ncq_ctx_get(ctx, "bench_ew"))
    if len(bench) == 0:
        LOG.warn("ctx 에 bench_ew 가 없습니다 — '월평균초과'는 벤치마크 차감 없는 절대수익입니다. "
                 "표의 의미가 달라지므로 그대로 표기합니다.")

    # run_fn 이 (SIG, pxm, sec, uni_obj, months) 를 직접 받는 형태여도 돌아가게 위치인자를 준비.
    bt_extra = (ncq_ctx_get(ctx, "pxm"), ncq_ctx_get(ctx, "sec"),
                ncq_ctx_get(ctx, "uni_obj"), months)

    sig_cache: Dict[Tuple[float, float], Any] = {}
    SIG0 = ncq_ctx_get(ctx, "SIG")
    if isinstance(SIG0, pd.DataFrame) and not SIG0.empty:
        sig_cache[(round(base["top"], 8), float(base["adv"]))] = SIG0
        LOG.info("기본 조합의 신호는 ctx 의 본선 SIG 를 재사용합니다(신호 재생성 1회 절약).")

    NCQ_SENS_CURVES.clear()
    recs: List[dict] = []
    n_sig = 0
    n_bt = 0
    for i, (cid, ax_name, val_txt, p) in enumerate(plans):
        key = (round(float(p["top"]), 8), float(p["adv"]))
        SIGp = sig_cache.get(key)
        if SIGp is None:
            if build_sig_fn is None:
                LOG.error(f"[{cid}] build_sig_fn 이 주입되지 않아 신호를 만들 수 없습니다 — 건너뜁니다.")
                recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                             "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                             "Sharpe": np.nan, "누적": np.nan, "판정": "— 실행불가(신호 콜백 없음)"})
                continue
            try:
                SIGp = build_sig_fn(top_pct=p["top"], min_adv=p["adv"])
                n_sig += 1
            except Exception as e:                                    # noqa
                LOG.error(f"[{cid}] 신호 생성 실패 — {type(e).__name__}: {e}")
                recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                             "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                             "Sharpe": np.nan, "누적": np.nan,
                             "판정": f"— 신호 생성 실패({type(e).__name__})"})
                continue
            sig_cache[key] = SIGp
        if not isinstance(SIGp, pd.DataFrame) or SIGp.empty:
            LOG.warn(f"[{cid}] 신호 패널이 비어 백테스트를 돌리지 않습니다 — 판정불가로 남깁니다.")
            recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"—/{len(plans)}",
                         "월수": 0, "월평균초과": np.nan, "HAC t": np.nan,
                         "Sharpe": np.nan, "누적": np.nan, "판정": "— 신호 패널 비어 있음"})
            continue
        BTp = ncq_run(run_fn, cid, SIGp, extra=bt_extra,
                      hold_months=p["hold"], cost_roundtrip=p["cost"])
        n_bt += 1
        if BTp is None:
            recs.append({"combo": cid, "축": ax_name, "값": val_txt,
                         "실행": f"{n_bt}/{len(plans)}", "월수": 0, "월평균초과": np.nan,
                         "HAC t": np.nan, "Sharpe": np.nan, "누적": np.nan,
                         "판정": "— 백테스트 실패"})
            continue
        rs = ncq_month_series(BTp)
        exc = ncq_align_diff(rs, bench) if len(bench) else rs
        mu, t = ncq_hac(exc)
        NCQ_SENS_CURVES[cid] = exc
        if not np.isfinite(mu):
            verdict = f"— 판정불가({len(exc)}개월)"
        elif mu <= 0:
            verdict = "✘ 소멸"
        elif np.isfinite(t) and t >= 1.65:
            verdict = "✔ 유지"
        else:
            verdict = "△ 약함(t<1.65)"
        recs.append({"combo": cid, "축": ax_name, "값": val_txt, "실행": f"{n_bt}/{len(plans)}",
                     "월수": int(len(exc)), "월평균초과": mu, "HAC t": t,
                     "Sharpe": ncq_sharpe(BTp), "누적": ncq_cum_return(rs), "판정": verdict})

    df = pd.DataFrame(recs, columns=["combo", "축", "값", "실행", "월수", "월평균초과",
                                     "HAC t", "Sharpe", "누적", "판정"])
    df.attrs["n_sig_builds"] = n_sig
    df.attrs["n_bt_runs"] = n_bt
    df.attrs["n_plans"] = len(plans)

    LOG.table([[r["combo"], r["축"], r["값"], r["실행"], f"{int(r['월수']):,}",
                ncq_f(r["월평균초과"], "pctp"), ncq_f(r["HAC t"], "t"),
                ncq_f(r["Sharpe"]), ncq_f(r["누적"], "pct"), r["판정"]]
               for _, r in df.iterrows()],
              ["조합", "축", "값", "실행", "월수", "월평균초과", "HAC t", "Sharpe", "누적", "판정"],
              ["l", "l", "r", "c", "r", "r", "r", "r", "r", "l"], maxw=24,
              title=f"민감도 9조합 — 실제 실행: 신호 재생성 {n_sig}회 · 백테스트 {n_bt}회 "
                    f"(계획 {len(plans)}조합)")
    LOG.info(f"민감도 실행 회계 — 계획 {len(plans)}조합 / 신호 재생성 {n_sig}회 / 백테스트 {n_bt}회. "
             f"ADV·tercile 축만 신호를 다시 만들고, 보유기간·비용 축은 백테스트만 다시 돌립니다.")

    ok = int((pd.to_numeric(df["월평균초과"], errors="coerce") > 0).sum())
    val = int(pd.to_numeric(df["월평균초과"], errors="coerce").notna().sum())
    ncq_record("S7", "민감도 9조합 (§15-5)",
               (None if val == 0 else bool(ok * 2 > val)),
               (f"유효 {val}조합 중 {ok}개에서 월평균 초과수익 > 0 "
                f"(신호 재생성 {n_sig}회 · 백테스트 {n_bt}회). "
                + ("과반 조합에서 부호가 유지됩니다." if ok * 2 > val else
                   "★ 과반 조합에서 초과수익 부호가 유지되지 않습니다 — 특정 설정에만 의존합니다."))
               if val else "실행 가능한 조합이 없어 판정불가",
               metrics={"n_plans": len(plans), "n_sig": n_sig, "n_bt": n_bt,
                        "n_pos": ok, "n_valid": val})
    NCQ_SENS_TABLE = df
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════
#  5. 요약 리포트 + §12 구조적 리스크 R1~R6
# ══════════════════════════════════════════════════════════════════════════════════════════

def report_robustness() -> None:
    """NCQ_ROBUST 전체를 표로 요약한다. 킬 게이트는 ⭐. 실패는 그대로 남긴다."""
    LOG.banner("ARC-NCQ 강건성 검사 요약 (§11)",
               "킬 게이트는 ⭐ 표시 · 실패와 판정불가는 그대로 보고한다")
    if not NCQ_ROBUST:
        LOG.warn("기록된 강건성 검사가 없습니다 — 이 계층이 실행되지 않았습니다.")
        return
    rows = []
    for r in NCQ_ROBUST.values():
        rows.append([r["id"] + ("⭐" if r["kill"] else ""), _trunc(r["name"], 34),
                     ncq_mark(r["pass"]), _trunc(r["detail"], 92)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=96)

    fails = [r for r in NCQ_ROBUST.values() if ncq_is_fail(r["pass"])]
    unk = [r for r in NCQ_ROBUST.values() if r["pass"] is None]
    kills = [r for r in fails if r["kill"]]
    LOG.info(f"집계 — 통과 {sum(1 for r in NCQ_ROBUST.values() if ncq_is_pass(r['pass']))}건 · "
             f"실패 {len(fails)}건 · 판정불가 {len(unk)}건 (총 {len(NCQ_ROBUST)}건)")
    if unk:
        LOG.warn("판정불가 " + ", ".join(r["id"] for r in unk) +
                 " — '통과'가 아닙니다. 표본이나 입력이 모자라 결론을 낼 수 없었다는 뜻입니다.")
    if kills:
        LOG.banner("⛔ 킬 기준 위반", "§15 — 우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            _safe_print(f"  · [{r['id']}] {r['name']}: {r['detail']}")
    elif fails:
        LOG.warn(f"비(非)킬 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails))
    else:
        LOG.ok("기록된 강건성 검사에서 실패가 없습니다(판정불가 항목은 위를 참고하세요).")


def ncq_right_tail_share(BT):
    """(상위5% 기여비중, 상위5% 제외 후 총기여). 보유이력이 없으면 (nan, nan).

    이 전략은 정보비율이 아니라 소수 종목의 우측 꼬리에 의존할 가능성이 크다(§12 R6).
    그 사실을 감추지 않기 위해 항상 같이 보고한다.
    """
    H = BT.get("holdings") if isinstance(BT, dict) else None
    if not isinstance(H, pd.DataFrame) or H.empty or not {"code", "weight", "ret"} <= set(H.columns):
        return (float("nan"), float("nan"))
    w = pd.to_numeric(H["weight"], errors="coerce")
    r = pd.to_numeric(H["ret"], errors="coerce")
    contrib = (w * r).groupby(H["code"].astype(str)).sum().sort_values(ascending=False)
    contrib = contrib[np.isfinite(contrib.to_numpy(dtype="float64"))]
    n = len(contrib)
    if n == 0:
        return (float("nan"), float("nan"))
    total = float(contrib.sum())
    k = max(1, int(round(n * 0.05)))
    top = float(contrib.iloc[:k].sum())
    share = (top / total) if abs(total) > 1e-12 else float("nan")
    return (share, total - top)


def report_structural_risks(ctx) -> None:
    """§12 구조적 리스크 R1~R6 을 **이번 실행에서 실제 관측된 수치**와 함께 출력한다.

    가정이나 설계 의도가 아니라 관측치를 적는다. 관측할 수 없었던 항목은 "—" 로 두고
    '측정하지 못함'이라고 쓴다 — 측정하지 않은 것을 안전하다고 쓰지 않는다.
    ctx 는 dict/객체 모두 허용하며, 없는 키는 조용히 "—" 가 된다.
    """
    LOG.banner("구조적 리스크 R1~R6 (§12)",
               "설계상의 위험이 이번 실행에서 실제로 얼마나 실현됐는가")

    REP = ncq_ctx_get(ctx, "REP")
    EV = ncq_ctx_get(ctx, "EV")
    TXT = ncq_ctx_get(ctx, "TXT")
    BT = ncq_ctx_get(ctx, "BT")
    diag = ncq_ctx_get(ctx, "diag")
    months = ncq_ctx_get(ctx, "months")
    n_months = 0
    try:
        n_months = int(len(months)) if months is not None else 0
    except Exception:
        n_months = 0

    min_total = int(ncq_cfg("NCQ_MIN_TOTAL_EVENTS", 800))
    min_per_m = float(ncq_cfg("NCQ_MIN_EVENTS_PER_MONTH", 5))

    # R1 — 아카이브 결손 구간 수 (리포트 인덱스가 비어 있는 달)
    n_gap = float("nan")
    if isinstance(diag, pd.DataFrame) and not diag.empty:
        cnt_col = next((c for c in ("n_reports", "n", "건수", "reports", "cnt")
                        if c in diag.columns), None)
        if cnt_col is not None:
            v = pd.to_numeric(diag[cnt_col], errors="coerce")
            n_gap = float((v.fillna(0) <= 0).sum())
    elif isinstance(REP, pd.DataFrame) and not REP.empty and "pub_date" in REP.columns and n_months:
        mm = pd.to_datetime(REP["pub_date"], errors="coerce").dt.to_period("M").nunique()
        n_gap = float(max(0, n_months - int(mm)))

    # R2 — IRS 단일 소스 의존도
    irs_share = float("nan")
    if isinstance(REP, pd.DataFrame) and not REP.empty and "source" in REP.columns:
        src = REP["source"].astype(str).str.lower()
        if len(src) > 0:
            irs_share = float(src.str.contains("irs").mean())

    # R3 — 표본 규모
    n_ev = float(len(EV)) if isinstance(EV, pd.DataFrame) else float("nan")
    ev_per_m = (n_ev / n_months) if (np.isfinite(n_ev) and n_months > 0) else float("nan")

    # R4 — 종목 매핑 실패율 (stock_code 를 붙이지 못한 리포트 비중)
    map_fail = float("nan")
    if isinstance(REP, pd.DataFrame) and not REP.empty and "stock_code" in REP.columns:
        sc = REP["stock_code"].astype(str).str.strip()
        bad = sc.isin(["", "none", "None", "nan", "NaN", "<NA>"]) | REP["stock_code"].isna()
        map_fail = float(bad.mean())

    # R5 — PDF 텍스트 추출 실패율
    pdf_fail = float("nan")
    if isinstance(TXT, pd.DataFrame) and not TXT.empty and "extract_ok" in TXT.columns:
        okm = ncq_boolmask(TXT["extract_ok"])
        if len(okm) > 0:
            pdf_fail = float(1.0 - okm.mean())

    # R6 — 우측 꼬리 의존도
    tail_share, tail_ex = ncq_right_tail_share(BT)

    def _verdict(val, limit, worse_is_high=True, fmt="pct0"):
        if val is None or not np.isfinite(val):
            return ("—", "측정하지 못함")
        bad = (val > limit) if worse_is_high else (val < limit)
        return (("❗ 기준 초과" if bad else "✔ 기준 내"), ncq_f(val, fmt))

    v2, s2 = _verdict(irs_share, 0.70, True, "pct0")
    v3a = ("❗ 미달" if (np.isfinite(n_ev) and n_ev < min_total)
           else ("✔ 충족" if np.isfinite(n_ev) else "—"))
    v3b = ("❗ 미달" if (np.isfinite(ev_per_m) and ev_per_m < min_per_m)
           else ("✔ 충족" if np.isfinite(ev_per_m) else "—"))
    v4, s4 = _verdict(map_fail, 0.10, True, "pct0")

    rows = [
        ["R1", "아카이브 결손 — 리포트 인덱스가 비는 구간",
         (ncq_f(n_gap, "int") + "개월") if np.isfinite(n_gap) else "—",
         "0개월 권장", ("✔ 없음" if (np.isfinite(n_gap) and n_gap == 0)
                      else ("❗ 존재" if np.isfinite(n_gap) else "—")),
         "결손 구간은 커버리지 '신규' 판정을 거짓 양성으로 만든다"],
        ["R2", "IRS 단일 소스 의존", s2, "≤ 70%", v2,
         "IRS 만으로 커버리지를 판정하면 소스 정책 변화가 곧 신호가 된다"],
        ["R3", "총 이벤트 표본", ncq_f(n_ev, "int") + ("건" if np.isfinite(n_ev) else ""),
         f"≥ {min_total:,}건", v3a, "표본이 모자라면 이후 모든 t 통계량이 무의미"],
        ["R3b", "월평균 이벤트", ncq_f(ev_per_m) + ("건/월" if np.isfinite(ev_per_m) else ""),
         f"≥ {min_per_m:.0f}건/월", v3b, "월별 포트폴리오가 소수 종목에 쏠린다"],
        ["R4", "종목코드 매핑 실패율", s4, "≤ 10%", v4,
         "매핑 실패는 무작위가 아니라 소형·신규 종목에 몰린다(선택편향)"],
        ["R5", "PDF 본문 추출 실패율",
         ncq_f(pdf_fail, "pct0"), "낮을수록 좋음(하드 기준 없음)",
         ("—" if not np.isfinite(pdf_fail) else ("❗ 30% 초과" if pdf_fail > 0.30 else "✔ 양호")),
         "추출 실패분은 텍스트 점수가 결측 — 0 으로 채우지 않는다"],
        ["R6", "우측 꼬리 의존 (상위5% 종목 기여비중)",
         ncq_f(tail_share, "pct0"), "참고치(제외 후 총기여 > 0)",
         ("—" if not np.isfinite(tail_share)
          else ("❗ 꼬리 의존" if (np.isfinite(tail_ex) and tail_ex <= 0) else "✔ 분산")),
         f"상위5% 제외 후 총기여 {ncq_f(tail_ex)}"],
    ]
    LOG.table(rows, ["ID", "구조적 리스크", "관측치", "기준", "판정", "왜 위험한가"],
              ["c", "l", "r", "l", "c", "l"], maxw=52)

    # ── 기준 초과 경고 (수치를 그대로 말한다) ─────────────────────────────────────────────
    if np.isfinite(irs_share) and irs_share > 0.70:
        LOG.warn(f"R2 — 리포트의 {irs_share*100:.1f}% 가 IRS 단일 소스입니다(기준 70%). "
                 f"이 상태에서 '신규 커버리지'는 기업 사건이 아니라 소스 수록 정책의 변화를 "
                 f"반영할 수 있습니다. 소스별 하위표본 성과를 반드시 함께 보십시오.")
    if np.isfinite(n_ev) and n_ev < min_total:
        LOG.warn(f"R3 — 총 이벤트가 {int(n_ev):,}건으로 최소 요건 {min_total:,}건에 미달합니다. "
                 f"검정력이 부족하므로 위 모든 t 통계량과 p 값을 그만큼 할인해서 읽어야 합니다.")
    if np.isfinite(ev_per_m) and ev_per_m < min_per_m:
        LOG.warn(f"R3b — 월평균 이벤트가 {ev_per_m:.2f}건으로 최소 {min_per_m:.0f}건에 미달합니다. "
                 f"월별 포트폴리오가 1~2종목에 좌우되어 성과가 사실상 개별 종목 베팅이 됩니다.")
    if np.isfinite(map_fail) and map_fail > 0.10:
        LOG.warn(f"R4 — 종목코드 매핑 실패율이 {map_fail*100:.1f}% 로 기준 10% 를 넘습니다. "
                 f"실패는 무작위가 아니라 소형·신규 상장에 몰리므로 유니버스가 조용히 왜곡됩니다.")
    if np.isfinite(tail_ex) and tail_ex <= 0 and np.isfinite(tail_share):
        LOG.warn(f"R6 — 상위 5% 종목을 제외하면 총기여가 {ncq_f(tail_ex)} 로 0 이하가 됩니다. "
                 f"성과가 소수 종목에 전적으로 의존하므로, 실전에서 그 종목을 놓치면 전략 전체가 "
                 f"실패합니다. 사이징과 기대치를 여기에 맞추십시오.")

    ncq_record("R12", "구조적 리스크 R1~R6 관측 (§12)", None,
               f"IRS 비중 {ncq_f(irs_share,'pct0')} · 총이벤트 {ncq_f(n_ev,'int')} · "
               f"월평균 {ncq_f(ev_per_m)} · 매핑실패 {ncq_f(map_fail,'pct0')} · "
               f"PDF실패 {ncq_f(pdf_fail,'pct0')} · 결손 {ncq_f(n_gap,'int')}개월 · "
               f"상위5% 기여 {ncq_f(tail_share,'pct0')}  (판정이 아니라 관측 기록입니다)",
               kill=False,
               metrics={"irs_share": irs_share, "n_events": n_ev, "ev_per_month": ev_per_m,
                        "map_fail": map_fail, "pdf_fail": pdf_fail, "archive_gap_m": n_gap,
                        "tail_top5_share": tail_share, "tail_ex_total": tail_ex})


# ============================================================================================
# 조립 블록 19: ncq_70_report.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  ARC-NCQ 리포팅 — 헤드라인 / 성과 / 커버리지 진단 / 진단 9종 / 해석표 / HTML · 매니페스트 ║
# ║                                                                                          ║
# ║  목적                                                                                     ║
# ║    "이 전략이 무엇을 보았고, 그 근거가 얼마나 얇은가"를 스크롤 없이 보여준다.               ║
# ║    숫자를 예쁘게 만드는 곳이 아니라, 결손·편향·집중을 먼저 자백하는 곳이다(§16.3).          ║
# ║    ★ 출력 1순위는 콘솔 표다. HTML 은 부가 산출물이며, HTML 이 실패해도 콘솔은 남는다.       ║
# ║                                                                                          ║
# ║  입력 (전부 선택적 — 없으면 "데이터 없음 + 이유"를 출력하고 조용히 건너뛰지 않는다)         ║
# ║    ctx      : dict — BT/SIG/EV/REP/UNI/SCORE/TXT/sec/benches/diag/valid_start/months …    ║
# ║    BT       : {"returns","holdings","cohorts","label"}  (계약 §3)                         ║
# ║    benches  : {이름: 월별 수익 Series}  주=Bottom-N EW · 보조=KOSPI/KOSDAQ · 대조=Placebo  ║
# ║                                                                                          ║
# ║  출력                                                                                     ║
# ║    콘솔 : LOG.banner / LOG.table (폭 104 기준, 한글 폭 보정은 _dw/_pad/_trunc 가 담당)      ║
# ║    파일 : report.html · coverage.html · manifest.json  (전부 atomic_write_text)           ║
# ║                                                                                          ║
# ║  실패 시 동작                                                                             ║
# ║    이 계층은 파이프라인을 죽이지 않는다. 섹션 하나가 터지면 그 섹션만 경고로 남기고 다음     ║
# ║    섹션을 계속 출력한다 — 리포트가 통째로 사라져서 원인을 못 보는 상황이 가장 나쁘다.        ║
# ║    단, 결측을 0으로 채우거나 표본을 잘라 결과를 좋아 보이게 만드는 일은 하지 않는다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

NCQ_W = 104                      # 콘솔 폭 기준 (기존 build/* 와 동일)
NCQ_NA = "—"                     # 결측 표기. NaN 을 0 으로 치환하지 않는다는 원칙의 표면.
NCQ_MARKS = "*o+x#%@"            # ASCII 차트 계열 마커 (전부 ASCII — 한글 폭 문제 회피)
NCQ_BLOCKS = "▁▂▃▄▅▆▇█"          # 스파크라인 블록 (East-Asian-Width='A' → _dw 로 1칸)


# ── 렉시콘 그룹 해석 참조표 (정본은 ncq_40_text 의 NCQ_LEXICON, 여기는 그 요약·폴백) ─────────
#    (라벨, 뜻, 발화했다는 것의 의미, 발화하지 않았다는 것의 의미, 방향)
NCQ_GROUP_DOC = OrderedDict([
    ("A", ("구조적 전환",
           "사업재편·체질개선·턴어라운드·신사업 진출처럼 '무엇을 하는 회사인가'가 바뀌는 서술",
           "애널리스트가 이 회사를 과거와 다른 회사로 보기 시작했다. 신규 커버리지의 가장 강한 명분",
           "전환 서사 없이 커버가 개시됐다 — 기존 사업의 업황 코멘트이거나 의무 발간일 수 있다",
           "+강")),
    ("B", ("캐파·양산",
           "증설·신규 라인·양산 개시·가동률처럼 '이미 돈을 쓴 흔적'의 서술",
           "말이 아니라 자본적 지출로 확인되는 변화. A 와 동시 발화할 때 가장 신뢰도가 높다",
           "설비 근거가 없다 — 전환 주장이 계획 단계에 머물러 있을 수 있다",
           "+")),
    ("C", ("수요·고객",
           "신규 수주·수주잔고·1차 벤더·국산화처럼 '외부가 값을 치렀다'는 증거",
           "제3자 검증이 있다. 회사의 자기 주장이 아니라 고객의 구매 결정이 근거",
           "수요 측 증거 없이 공급 측 이야기만 있다 — 증설이 재고로 남을 위험",
           "+")),
    ("D", ("인증·승인",
           "인증 획득·품질 승인·벤더 등록·특허·임상 진입 등 제도적 관문 통과",
           "되돌리기 어려운 자격을 얻었다. 소형주에서 진입장벽이 실제로 생기는 지점",
           "관문 통과 근거 없음 — 기술·품질 주장이 아직 검증되지 않았다는 뜻",
           "+")),
    ("H", ("헤지·불확실성",
           "'기대', '전망', '가능성', '검토 중' 등 확신을 낮추는 완충 표현",
           "★ 역가중(-1.0). 근거 대신 기대를 적었다는 자기고백. 스폰서 의무 발간에서 특히 흔하다",
           "단정적으로 썼다 — 하우스가 평판을 걸었다는 뜻",
           "−역")),
    ("N", ("부정",
           "지연·차질·부진·둔화·하향·적자전환 등 명시적 악화 서술",
           "★ 역가중(-2.5). 신규 커버리지 리포트에 악재를 적었다는 것은 그만큼 크다는 뜻",
           "악재 서술 없음 — 낙관 편향이거나, 본문 추출이 앞부분에서 잘렸을 수 있다",
           "−역")),
])

# ── 신규 커버리지 이벤트 유형 (정본은 ncq_30_coverage.build_coverage_events) ─────────────────
NCQ_EVENT_TYPE_DOC = OrderedDict([
    ("H1", ("전면 신규 커버리지",
            "직전 lookback 구간(NCQ_LOOKBACK_M) 동안 어떤 증권사도 리포트를 내지 않던 종목에 "
            "리포트가 발간됨. 정보 공백이 가장 큰 상태 — 이 전략의 본류.")),
    ("H2", ("신규 하우스 진입",
            "기존 커버는 있었으나 해당 증권사가 처음 커버를 개시함. 공백은 H1 보다 얕지만 "
            "새 하우스의 자원 배분 결정이라는 점에서 정보가 있다.")),
])

NCQ_SPONSOR_DOC = OrderedDict([
    ("SPONSORED_ONLY", "IRS(거래소 기업분석보고서 발간지원) 등 발행사·기관 스폰서 리포트만으로 구성된 이벤트. "
                       "발간 자체가 의무일 수 있어 '자발적 관심'의 증거로 쓰기 어렵다."),
    ("ORGANIC_ONLY", "스폰서 없이 증권사가 자발적으로 발간한 리포트만으로 구성된 이벤트. 신호의 본체."),
    ("MIXED", "스폰서·자발 리포트가 섞인 이벤트."),
])

NCQ_HTML_CSS = """
*{box-sizing:border-box}
body{margin:0;padding:28px 22px 60px;background:#ffffff;color:#1f2328;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR","Malgun Gothic",sans-serif;
 font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid #1f2328}
h3{font-size:14px;margin:20px 0 6px;color:#39424e}
.sub{color:#6a737d;font-size:13px;margin:0 0 18px}
.note{color:#6a737d;font-size:12px;margin:4px 0 14px}
.alert{border:2px solid #d93025;background:#fdf1f0;border-radius:8px;padding:12px 16px;margin:16px 0}
.alert b{color:#d93025}
.alert ul{margin:6px 0 0;padding-left:20px}
.ok{border:1px solid #188038;background:#f2f9f4;border-radius:8px;padding:10px 16px;margin:16px 0;color:#186c33}
table{border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:13px}
th,td{border:1px solid #d0d7de;padding:5px 9px;text-align:right;white-space:nowrap}
th{background:#f2f4f7;font-weight:600;text-align:center}
td.l,th.l{text-align:left;white-space:normal}
tbody tr:nth-child(even){background:#fafbfc}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.bad{color:#d93025;font-weight:600}
.good{color:#188038}
.mut{color:#6a737d}
.chart{border:1px solid #d0d7de;border-radius:8px;padding:8px;margin:10px 0;overflow-x:auto}
footer{margin-top:44px;padding-top:14px;border-top:1px solid #d0d7de;color:#6a737d;font-size:12px}
"""


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  0. 공통 유틸 — 안전 접근 / 포맷 / 섹션 가드
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_g(name: str, default=None):
    """조립 순서상 아직 정의되지 않았을 수도 있는 전역을 안전하게 읽는다.

    리포트 계층은 모든 상위 모듈에 의존하는데, 부분 실행(SMOKE·CACHED)에서는 그중 일부가
    아예 정의되지 않는다. 그때 NameError 로 리포트가 통째로 죽는 것이 최악이라 이 관문을 둔다.
    """
    return globals().get(name, default)


def ncq_rpt_ctx_get(ctx, key: str, default=None):
    """ctx 는 dict 이거나 속성 객체일 수 있다. 둘 다 받는다."""
    if ctx is None:
        return default
    try:
        if isinstance(ctx, dict):
            return ctx.get(key, default)
        return getattr(ctx, key, default)
    except Exception:
        return default


def ncq_isnum(v) -> bool:
    """유한한 수인가. bool 은 수로 보지 않는다(True 가 1.0 으로 표에 찍히는 사고 방지)."""
    try:
        if v is None or isinstance(v, (bool, np.bool_)):
            return False
        return bool(np.isfinite(float(v)))
    except Exception:
        return False


def ncq_pct(v, digits: int = 2, signed: bool = True) -> str:
    if not ncq_isnum(v):
        return NCQ_NA
    return (f"{float(v) * 100:+.{digits}f}%" if signed else f"{float(v) * 100:.{digits}f}%")


def ncq_pctp(v, digits: int = 3) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{float(v) * 100:+.{digits}f}%p"


def ncq_rpt_num(v, digits: int = 3) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{float(v):,.{digits}f}"


def ncq_int(v) -> str:
    return NCQ_NA if not ncq_isnum(v) else f"{int(round(float(v))):,}"


def ncq_compact(v) -> str:
    """표 폭이 빡빡한 연도×월 매트릭스용 축약 표기."""
    if not ncq_isnum(v):
        return NCQ_NA
    x = float(v)
    a = abs(x)
    if a >= 1e8:
        return f"{x / 1e8:.1f}억"
    if a >= 1e4:
        return f"{x / 1e3:.0f}k"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.1f}"


def ncq_wrap(s, width: int) -> List[str]:
    """한글 폭(_dw)을 반영한 줄바꿈. 공백 없는 한글 장문도 문자 단위로 자른다."""
    words = str(s).replace("\n", " ").split(" ")
    lines: List[str] = []
    cur = ""
    for w0 in words:
        cand = (cur + " " + w0) if cur else w0
        if _dw(cand) <= width:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        while _dw(w0) > width:
            acc = ""
            for ch in w0:
                if _dw(acc) + _dw(ch) > width:
                    break
                acc += ch
            if not acc:                       # 폭보다 넓은 단일 문자 — 무한루프 방지
                acc = w0[0]
            lines.append(acc)
            w0 = w0[len(acc):]
        cur = w0
    if cur:
        lines.append(cur)
    return lines or [""]


def ncq_box(title: str, lines: Sequence[str], width: int = 100) -> List[str]:
    """한글 폭을 보정한 ASCII 박스. 문자열 리터럴로 직접 그리면 반드시 어긋난다."""
    width = max(24, int(width))
    inner = width - 4
    out = ["┌" + "─" * (width - 2) + "┐",
           "│ " + _pad(_trunc(title, inner), inner) + " │"]
    if lines:
        out.append("├" + "─" * (width - 2) + "┤")
    for ln in lines:
        for w in ncq_wrap(ln, inner):
            out.append("│ " + _pad(w, inner) + " │")
    out.append("└" + "─" * (width - 2) + "┘")
    return out


def ncq_alert_box(lines: Sequence[str], title: str = "위험 경고 — 아래 숫자를 읽기 전에 이것부터") -> None:
    """리포트 최상단 경고(§15-6). 눈에 띄지 않으면 없는 것과 같으므로 이중선 박스로 그린다."""
    lines = [l for l in (lines or []) if l]
    if not lines:
        return
    inner = NCQ_W - 4
    _safe_print("")
    _safe_print("┏" + "━" * (NCQ_W - 2) + "┓")
    _safe_print("┃ " + _pad(_trunc("⚠  " + title, inner), inner) + " ┃")
    _safe_print("┠" + "─" * (NCQ_W - 2) + "┨")
    for i, ln in enumerate(lines, 1):
        for k, w in enumerate(ncq_wrap(f"{i}. {ln}", inner)):
            _safe_print("┃ " + _pad(("" if k == 0 else "   ") + w, inner) + " ┃")
    _safe_print("┗" + "━" * (NCQ_W - 2) + "┛")


@contextmanager
def ncq_section(title: str):
    """섹션 가드 — 한 섹션이 터져도 리포트 전체가 사라지지 않게 한다.

    ★ 예외를 삼키는 것이 원칙 위반처럼 보이지만, 이 계층에 한해서는 반대다.
      리포트는 '무엇이 잘못됐는지 보여주는 장치'인데 그게 죽으면 진단 수단이 사라진다.
      대신 삼킨 사실과 예외 종류를 반드시 경고로 남긴다.
    """
    try:
        yield
    except Exception as e:                                        # noqa
        LOG.warn(f"[{title}] 출력 중 오류 — 이 섹션만 건너뜁니다: {type(e).__name__}: {str(e)[:180]}")


def ncq_no_data(title: str, reason: str) -> None:
    """데이터가 없을 때 조용히 건너뛰지 않는다. 무엇이 왜 없는지 항상 적는다."""
    LOG.warn(f"[{title}] 데이터 없음 — {reason}")


def ncq_pick_col(df, cands: Sequence[str], default=None):
    """스키마가 모듈마다 조금씩 다를 수 있는 진단표에서 컬럼을 안전하게 고른다."""
    try:
        if df is None or not hasattr(df, "columns"):
            return default
        for c in cands:
            if c in df.columns:
                return c
    except Exception:
        pass
    return default


def ncq_has_rows(df) -> bool:
    try:
        return df is not None and hasattr(df, "empty") and (not df.empty)
    except Exception:
        return False


def ncq_name_map(sec) -> Dict[str, str]:
    """code → 종목명. 없으면 빈 dict (호출부는 .get(code, '') 로 쓴다)."""
    try:
        if not ncq_has_rows(sec) or "code" not in sec.columns:
            return {}
        s = sec.dropna(subset=["code"]).drop_duplicates(subset=["code"])
        if "name" not in s.columns:
            return {}
        return {str(k): ("" if pd.isna(v) else str(v))
                for k, v in zip(s["code"].astype(str), s["name"])}
    except Exception:
        return {}


def ncq_spearman(x, y) -> Tuple[float, float]:
    """(rho, p). scipy 가 있으면 p 값까지, 없으면 rho 만 (p 는 NaN — 0 으로 채우지 않는다)."""
    try:
        xa = np.asarray(pd.to_numeric(pd.Series(list(x)), errors="coerce"), dtype=float)
        ya = np.asarray(pd.to_numeric(pd.Series(list(y)), errors="coerce"), dtype=float)
        m = np.isfinite(xa) & np.isfinite(ya)
        if int(m.sum()) < 5:
            return (np.nan, np.nan)
        try:
            from scipy import stats as _st
            r, p = _st.spearmanr(xa[m], ya[m])
            return (float(r), float(p))
        except Exception:
            s = pd.DataFrame({"x": xa[m], "y": ya[m]})
            return (float(s["x"].corr(s["y"], method="spearman")), np.nan)
    except Exception:
        return (np.nan, np.nan)


def ncq_xlabel(x) -> str:
    if isinstance(x, (pd.Timestamp, _dt.date, _dt.datetime, np.datetime64)):
        t = as_ts(x)
        return t.strftime("%Y-%m") if t is not None else NCQ_NA
    return _trunc(str(x), 10)


def ncq_rpt_month_series(df, value: Optional[str] = None, how: str = "count") -> pd.Series:
    """month 컬럼을 가진 프레임 → 월말 인덱스 Series. 없는 달은 NaN(0 으로 채우지 않는다)."""
    if not ncq_has_rows(df):
        return pd.Series(dtype="float64")
    mcol = ncq_pick_col(df, ["month", "월"])
    if mcol is None:
        return pd.Series(dtype="float64")
    d = df.copy()
    d["_m"] = as_ts_series(d[mcol]) + pd.offsets.MonthEnd(0)
    g = d.groupby("_m", observed=True)
    if how == "count" or value is None:
        s = g.size().astype("float64")
    elif how == "nunique":
        s = g[value].nunique().astype("float64")
    elif how == "sum":
        s = g[value].sum(min_count=1).astype("float64")
    else:
        s = g[value].mean().astype("float64")
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def ncq_fill_month_gaps(s: pd.Series) -> pd.Series:
    """관측 구간 전체를 월말 그리드로 펴서 '없는 달'이 NaN 으로 드러나게 한다."""
    try:
        if s is None or len(s) == 0:
            return pd.Series(dtype="float64")
        idx = pd.DatetimeIndex(pd.to_datetime(s.index))
        full = pd.date_range(idx.min(), idx.max(), freq="ME")
        return s.reindex(full)
    except Exception:
        return s


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  1. 시각화 유틸 — 스파크라인 / ASCII 차트 / 연도 요약표 / 막대
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_sparkline(values, width: int = 48, lo=None, hi=None) -> str:
    """시계열을 한 줄 블록 문자로. 결측은 '·' 로 남긴다(0 으로 채우면 결손이 사라진다).

    lo/hi 를 주면 여러 줄(예: 연도별 행) 사이에 스케일을 공유해 비교가 가능해진다.
    """
    try:
        v = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    except Exception:
        return NCQ_NA
    if v.size == 0:
        return NCQ_NA
    w = max(1, int(width))
    if v.size > w:                                    # 다운샘플: 구간 평균 (결측은 무시)
        edges = np.linspace(0, v.size, w + 1).astype(int)
        binned = []
        for i in range(w):
            a = edges[i]
            b = max(edges[i] + 1, edges[i + 1])
            seg = v[a:min(b, v.size)]
            seg = seg[np.isfinite(seg)]
            binned.append(float(seg.mean()) if seg.size else np.nan)
        v = np.asarray(binned, dtype=float)
    fin = v[np.isfinite(v)]
    if fin.size == 0:
        return NCQ_NA
    vlo = float(fin.min()) if not ncq_isnum(lo) else float(lo)
    vhi = float(fin.max()) if not ncq_isnum(hi) else float(hi)
    if vhi - vlo < 1e-12:
        return "".join("▄" if np.isfinite(x) else "·" for x in v)
    out = []
    for x in v:
        if not np.isfinite(x):
            out.append("·")
            continue
        k = int(round((x - vlo) / (vhi - vlo) * (len(NCQ_BLOCKS) - 1)))
        out.append(NCQ_BLOCKS[min(len(NCQ_BLOCKS) - 1, max(0, k))])
    return "".join(out)


def ncq_ascii_chart(series_dict: Dict[str, Any], height: int = 14, width: int = 92) -> List[str]:
    """여러 시계열을 하나의 ASCII 라인차트로. 반환은 출력용 줄 리스트(호출자가 _safe_print).

    콘솔이 1순위 출력이라는 원칙 때문에 필요하다 — matplotlib 은 로그에 남지 않는다.
    · 값이 전부 결측인 계열은 조용히 빼지 않고 범례에 '(데이터 없음)' 으로 표기한다.
    · 선이 겹치면 먼저 그린 계열이 보인다(범례 순서 = 그린 순서).
    """
    items: List[List[Any]] = []
    empty: List[str] = []
    for name, s in (series_dict or {}).items():
        try:
            ss = pd.to_numeric(pd.Series(s), errors="coerce").astype(float)
        except Exception:
            ss = None
        if ss is None or int(ss.notna().sum()) == 0:
            empty.append(str(name))
            continue
        items.append([str(name), ss])
    if not items:
        why = ("전부 결측: " + ", ".join(empty)) if empty else "입력이 비었습니다"
        return [f"  (차트 데이터 없음 — {why})"]

    try:                                              # 공통 x축 = 인덱스 합집합
        uni = pd.Index(sorted(set().union(*[set(pd.Index(s.index)) for _, s in items])))
        cols = [pd.Series(s).reindex(uni).astype(float).ffill().to_numpy() for _, s in items]
    except Exception:                                 # 인덱스 타입이 섞이면 위치 기준으로 폴백
        n0 = max(len(s) for _, s in items)
        uni = pd.RangeIndex(n0)
        cols = [np.concatenate([pd.Series(s).to_numpy(dtype=float),
                                np.full(n0 - len(s), np.nan)]) for _, s in items]

    fin = [c[np.isfinite(c)] for c in cols]
    fin = [f for f in fin if f.size]
    if not fin:
        return ["  (차트 데이터 없음 — 정렬 후 유한값이 하나도 남지 않았습니다)"]
    allv = np.concatenate(fin)
    ymin, ymax = float(allv.min()), float(allv.max())
    as_pct = max(abs(ymin), abs(ymax)) <= 50.0        # 수익률 비율값이면 % 로 표시
    if ymax - ymin < 1e-12:
        ymax = ymin + 1e-9
    span = ymax - ymin

    H = max(4, int(height))
    W = max(20, int(width))
    grid = [[" "] * W for _ in range(H)]
    n = len(uni)
    xpos = [0] * W if n <= 1 else [int(round(j * (n - 1) / (W - 1))) for j in range(W)]

    if ymin < 0.0 < ymax:                             # 0 기준선 — 손실 구간이 눈에 보이게
        r0 = min(H - 1, max(0, int(round((ymax - 0.0) / span * (H - 1)))))
        for j in range(W):
            grid[r0][j] = "·"

    for si, (_nm, _s) in enumerate(items):
        m = NCQ_MARKS[si % len(NCQ_MARKS)]
        vals = cols[si]
        prev = None
        for j in range(W):
            v = vals[xpos[j]]
            if not np.isfinite(v):
                prev = None
                continue
            r = min(H - 1, max(0, int(round((ymax - v) / span * (H - 1)))))
            if prev is not None and abs(r - prev) > 1:      # 급변 구간을 세로로 이어 선처럼 보이게
                step = 1 if r > prev else -1
                for rr in range(prev + step, r, step):
                    if grid[rr][j] in (" ", "·"):
                        grid[rr][j] = m
            if grid[r][j] in (" ", "·"):
                grid[r][j] = m
            prev = r

    lines: List[str] = []
    for r in range(H):
        y = ymax - span * r / (H - 1)
        lab = f"{y * 100:+.1f}%" if as_pct else f"{y:+.3g}"
        lines.append("  " + _pad(lab, 9, "r") + " │" + "".join(grid[r]))
    lines.append("  " + " " * 9 + " └" + "─" * W)
    if n:
        bar = [" "] * W
        def _put(pos: int, txt: str):
            pos = max(0, min(W - len(txt), int(pos)))
            for k, ch in enumerate(txt):
                if pos + k < W:
                    bar[pos + k] = ch
        l0, lm, l1 = ncq_xlabel(uni[0]), ncq_xlabel(uni[n // 2]), ncq_xlabel(uni[-1])
        _put(0, l0)
        _put(W // 2 - len(lm) // 2, lm)
        _put(W - len(l1), l1)
        lines.append("  " + " " * 9 + "  " + "".join(bar))
    leg = "  범례: " + "   ".join(f"{NCQ_MARKS[i % len(NCQ_MARKS)]} {nm}"
                                 for i, (nm, _) in enumerate(items))
    if empty:
        leg += "   (데이터 없음: " + ", ".join(empty) + ")"
    lines.append(_trunc(leg, NCQ_W))
    lines.append("  " + ("y축 단위 % · " if as_pct else "y축 원값 · ") +
                 "선이 겹치면 먼저 그린 계열(범례 앞쪽)이 보입니다.")
    return lines


def ncq_print_chart(series_dict: Dict[str, Any], title: str = "",
                    height: int = 14, width: int = 92) -> None:
    if title:
        _safe_print(f"\n▶ {title}")
    for ln in ncq_ascii_chart(series_dict, height=height, width=width):
        _safe_print(ln)


def ncq_year_spark(s: pd.Series, title: str = "", note: str = "",
                   fmt: str = "int") -> None:
    """월별 시계열 → '연도 요약 + 12칸 스파크라인' 표.

    스파크라인 스케일은 전 연도 공통이라 연도 간 비교가 성립한다.
    관측이 없는 달은 '·' 로 남는다 — 결손을 0 으로 그리면 결손이 사라진다.
    """
    if s is None or len(s) == 0:
        ncq_no_data(title or "연도 요약", "입력 시계열이 비었습니다.")
        return
    ss = ncq_fill_month_gaps(pd.to_numeric(pd.Series(s), errors="coerce"))
    idx = pd.DatetimeIndex(pd.to_datetime(ss.index))
    fin = ss.to_numpy(dtype=float)
    fin = fin[np.isfinite(fin)]
    if fin.size == 0:
        ncq_no_data(title or "연도 요약", "유한값이 하나도 없습니다.")
        return
    lo, hi = float(fin.min()), float(fin.max())
    f = (lambda v: ncq_int(v)) if fmt == "int" else \
        (lambda v: ncq_pct(v)) if fmt == "pct" else (lambda v: ncq_rpt_num(v))
    rows = []
    for y in sorted(set(idx.year)):
        m = idx.year == y
        vals = ss[m]
        arr = np.full(12, np.nan, dtype=float)
        for t, v in zip(idx[m], vals.to_numpy(dtype=float)):
            arr[int(t.month) - 1] = v
        obs = int(np.isfinite(arr).sum())
        tot = float(np.nansum(arr)) if obs else np.nan
        rows.append([str(y), f"{obs}/12",
                     f(tot) if fmt != "pct" else NCQ_NA,
                     f(float(np.nanmean(arr))) if obs else NCQ_NA,
                     f(float(np.nanmin(arr))) if obs else NCQ_NA,
                     f(float(np.nanmax(arr))) if obs else NCQ_NA,
                     ncq_sparkline(arr, width=12, lo=lo, hi=hi)])
    LOG.table(rows, ["연도", "관측월", "합계", "평균", "최소", "최대", "1월─────────12월"],
              ["c", "c", "r", "r", "r", "r", "l"], title=title)
    tail = f"스파크라인 스케일 공통 [{ncq_compact(lo)} ~ {ncq_compact(hi)}] · '·' 는 관측 없음(0 아님)"
    LOG.info("    " + (note + " · " if note else "") + tail)


def ncq_year_matrix(s: pd.Series, title: str = "", note: str = "") -> None:
    """연도×월 매트릭스. 값은 축약 표기(ncq_compact)로 폭 104 안에 들어오게 한다."""
    if s is None or len(s) == 0:
        ncq_no_data(title or "연도×월", "입력 시계열이 비었습니다.")
        return
    ss = ncq_fill_month_gaps(pd.to_numeric(pd.Series(s), errors="coerce"))
    idx = pd.DatetimeIndex(pd.to_datetime(ss.index))
    rows = []
    for y in sorted(set(idx.year)):
        m = idx.year == y
        arr = np.full(12, np.nan, dtype=float)
        for t, v in zip(idx[m], ss[m].to_numpy(dtype=float)):
            arr[int(t.month) - 1] = v
        obs = int(np.isfinite(arr).sum())
        rows.append([str(y)] + [ncq_compact(x) if np.isfinite(x) else NCQ_NA for x in arr] +
                    [ncq_compact(float(np.nansum(arr))) if obs else NCQ_NA])
    LOG.table(rows, ["연도"] + [str(i) for i in range(1, 13)] + ["계"],
              ["c"] + ["r"] * 13, maxw=8, title=title)
    if note:
        LOG.info("    " + note)


def ncq_bar(v, vmax, width: int = 30, ch: str = "█") -> str:
    if not ncq_isnum(v) or not ncq_isnum(vmax) or float(vmax) <= 0:
        return ""
    k = int(round(max(0.0, float(v)) / float(vmax) * width))
    return ch * max(0, min(width, k))


def ncq_runs(flags: Sequence[bool], index: Sequence[Any], min_len: int = 1) -> List[Tuple[Any, Any, int]]:
    """True 가 연속된 구간을 (시작, 끝, 길이) 로. 결손 구간 보고용."""
    out: List[Tuple[Any, Any, int]] = []
    start = None
    prev = None
    for f, i in zip(list(flags), list(index)):
        if bool(f):
            if start is None:
                start = i
            prev = i
        else:
            if start is not None:
                out.append((start, prev, 0))
                start = None
    if start is not None:
        out.append((start, prev, 0))
    res = []
    idx_list = list(index)
    for a, b, _ in out:
        try:
            n = idx_list.index(b) - idx_list.index(a) + 1
        except Exception:
            n = 1
        if n >= min_len:
            res.append((a, b, n))
    return res


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  2. 헤드라인 (§15-6) — 리포트 최상단 필수 표시
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_degraded_levels() -> List[str]:
    fn = ncq_g("degraded")
    try:
        return list(fn()) if callable(fn) else []
    except Exception:
        return []


def ncq_archive_gaps(diag) -> Tuple[List[pd.Timestamp], List[Tuple[Any, Any, int]], Optional[pd.Timestamp]]:
    """진단표에서 (결손 태깅 월, 3개월+ 연속 결손 구간, 그로부터 도출되는 유효 시작월).

    스키마가 모듈마다 다를 수 있어 컬럼명을 후보 목록으로 찾는다.
    아무 단서도 없으면 (빈 리스트, 빈 리스트, None) — 추측해서 채우지 않는다.
    """
    if not ncq_has_rows(diag):
        return ([], [], None)
    mcol = ncq_pick_col(diag, ["month", "월"])
    if mcol is None:
        return ([], [], None)
    d = diag.copy()
    d["_m"] = as_ts_series(d[mcol]) + pd.offsets.MonthEnd(0)
    d = d.dropna(subset=["_m"]).sort_values("_m")
    inc_col = ncq_pick_col(d, ["archive_incomplete", "incomplete", "is_incomplete", "gap"])
    ok_col = ncq_pick_col(d, ["archive_ok", "complete", "is_complete"])
    if inc_col is not None:
        flags = d[inc_col].fillna(False).astype(bool).to_numpy()
    elif ok_col is not None:
        flags = (~d[ok_col].fillna(False).astype(bool)).to_numpy()
    else:
        ncol = ncq_pick_col(d, ["n_reports", "n", "count", "n_total"])
        if ncol is None:
            return ([], [], None)
        flags = (pd.to_numeric(d[ncol], errors="coerce").fillna(0) <= 0).to_numpy()
    months = list(pd.DatetimeIndex(d["_m"]))
    tagged = [m for m, f in zip(months, flags) if bool(f)]
    runs = ncq_runs(flags, months, min_len=3)
    valid_start = None
    if runs:
        last_end = runs[-1][1]
        try:
            valid_start = (pd.Timestamp(last_end) + pd.offsets.MonthEnd(1)).normalize()
        except Exception:
            valid_start = None
    elif months:
        valid_start = months[0]
    return (tagged, runs, valid_start)


def ncq_headline_facts(ctx) -> "OrderedDict[str, Any]":
    """§15-6 필수 표시 항목을 한 번에 계산한다(콘솔·HTML·매니페스트가 같은 값을 쓴다)."""
    EV = ncq_rpt_ctx_get(ctx, "EV")
    REP = ncq_rpt_ctx_get(ctx, "REP")
    TXT = ncq_rpt_ctx_get(ctx, "TXT")
    diag = ncq_rpt_ctx_get(ctx, "diag")
    months = ncq_rpt_ctx_get(ctx, "months")
    f: "OrderedDict[str, Any]" = OrderedDict()

    f["열화단계"] = ncq_degraded_levels()

    vs = ncq_rpt_ctx_get(ctx, "valid_start")
    vs = as_ts(vs) if vs is not None else None
    end = None
    try:
        if months is not None and len(months):
            end = as_ts(pd.DatetimeIndex(months)[-1])
    except Exception:
        end = None
    if end is None:
        end = as_ts(ncq_g("BACKTEST_END"))
    if vs is None:
        vs = ncq_archive_gaps(diag)[2]
    f["유효시작월"], f["유효종료월"] = vs, end
    n_month = np.nan
    if vs is not None and end is not None:
        n_month = (end.year - vs.year) * 12 + (end.month - vs.month) + 1
    f["유효개월수"] = float(n_month) if ncq_isnum(n_month) else np.nan
    f["유효연수"] = float(n_month) / 12.0 if ncq_isnum(n_month) else np.nan

    f["총이벤트수"] = float(len(EV)) if ncq_has_rows(EV) else np.nan
    ev_m = ncq_rpt_month_series(EV) if ncq_has_rows(EV) else pd.Series(dtype="float64")
    f["월평균이벤트"] = float(ncq_fill_month_gaps(ev_m).fillna(0).mean()) if len(ev_m) else np.nan
    f["이벤트월수"] = float(len(ev_m)) if len(ev_m) else np.nan

    # IRS(스폰서) 비중 — 리포트 기준과 이벤트 기준을 둘 다 낸다. 둘은 다른 질문에 답한다.
    f["IRS리포트비중"] = np.nan
    if ncq_has_rows(REP) and "is_sponsored" in REP.columns:
        v = REP["is_sponsored"]
        try:
            f["IRS리포트비중"] = float(v.fillna(False).astype(bool).mean())
        except Exception:
            f["IRS리포트비중"] = np.nan
    f["IRS이벤트비중"] = np.nan
    f["ORGANIC이벤트비중"] = np.nan
    if ncq_has_rows(EV) and "sponsor_group" in EV.columns:
        g = EV["sponsor_group"].astype(str)
        n = max(1, len(g))
        f["IRS이벤트비중"] = float(((g == "SPONSORED_ONLY") | (g == "MIXED")).sum()) / n
        f["ORGANIC이벤트비중"] = float((g == "ORGANIC_ONLY").sum()) / n

    # 종목명 → 티커 매핑 실패율: stock_code 가 비어 있는 리포트 비율
    f["티커매핑실패율"] = np.nan
    if ncq_has_rows(REP) and "stock_code" in REP.columns:
        c = REP["stock_code"].astype(object)
        bad = c.isna() | (c.astype(str).str.strip().isin(["", "None", "nan", "NaN"]))
        f["티커매핑실패율"] = float(bad.mean())

    # PDF 추출 실패율
    f["PDF추출실패율"] = np.nan
    f["PDF시도건수"] = np.nan
    if ncq_has_rows(TXT) and "extract_ok" in TXT.columns:
        ok = TXT["extract_ok"].fillna(False).astype(bool)
        f["PDF추출실패율"] = float(1.0 - ok.mean())
        f["PDF시도건수"] = float(len(ok))

    tagged, runs, derived = ncq_archive_gaps(diag)
    f["결손태깅월수"] = float(len(tagged)) if ncq_has_rows(diag) else np.nan
    f["결손구간"] = runs
    f["도출유효시작월"] = derived
    return f


def report_headline(ctx) -> None:
    """리포트 최상단 필수 표시(§15-6) + 위험 경고. 이 함수가 리포트의 첫 출력이어야 한다."""
    LOG.banner("ARC-NCQ v1.0 — 리포트 헤드라인 (§15-6 필수 표시)",
               "아래 경고를 읽기 전에 성과 숫자를 읽지 마세요. 표본이 얇으면 숫자는 의미가 없습니다.")
    f = ncq_headline_facts(ctx)

    min_ev_m = float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5)
    min_ev_t = float(ncq_g("NCQ_MIN_TOTAL_EVENTS", 800) or 800)
    min_years = float(ncq_g("NCQ_MIN_VALID_YEARS", 5.0) or 5.0)

    warns: List[str] = []
    if ncq_isnum(f["월평균이벤트"]) and f["월평균이벤트"] < min_ev_m:
        warns.append(f"월평균 이벤트가 {f['월평균이벤트']:.2f}건으로 최소 기준 {min_ev_m:.0f}건 미달입니다. "
                     f"횡단면 z 와 tercile 선별이 사실상 소수 종목 추첨이 됩니다 — "
                     f"이 상태의 성과 지표는 신뢰구간이 표시되지 않은 채로도 무의미합니다.")
    elif not ncq_isnum(f["월평균이벤트"]):
        warns.append("월평균 이벤트를 계산할 수 없습니다(EV 가 비었거나 month 컬럼이 없음). "
                     "이벤트 판정 단계(P2)를 먼저 확인하세요.")
    if ncq_isnum(f["총이벤트수"]) and f["총이벤트수"] < min_ev_t:
        warns.append(f"총 이벤트가 {int(f['총이벤트수']):,}건으로 최소 기준 {int(min_ev_t):,}건 미달입니다. "
                     f"부트스트랩·순열 검정의 검정력이 낮아 '유의하지 않음'이 '효과 없음'을 뜻하지 않습니다.")
    if ncq_isnum(f["IRS이벤트비중"]) and f["IRS이벤트비중"] > 0.70:
        warns.append(f"IRS(스폰서) 포함 이벤트 비중이 {f['IRS이벤트비중']*100:.1f}% 로 70% 를 넘습니다. "
                     f"이 신호는 '증권사의 자발적 관심'이 아니라 '발간지원 사업의 대상 선정'을 "
                     f"주로 측정하고 있을 가능성이 큽니다 — 진단 8(스폰서 분해)을 반드시 함께 보세요.")
    if ncq_isnum(f["유효연수"]) and f["유효연수"] < min_years:
        warns.append(f"유효 백테스트 구간이 {f['유효연수']:.2f}년으로 최소 {min_years:.1f}년 미달입니다. "
                     f"12개월 오버랩 보유 전략에서 이 길이는 독립 코호트가 몇 개 안 된다는 뜻입니다.")
    if ncq_isnum(f["결손태깅월수"]) and f["결손태깅월수"] > 0:
        runs = f["결손구간"] or []
        gap_txt = ", ".join(f"{ncq_xlabel(a)}~{ncq_xlabel(b)}({n}개월)" for a, b, n in runs[:4])
        warns.append(f"아카이브 결손 월 {int(f['결손태깅월수'])}개" +
                     (f" · 3개월 이상 연속 결손 구간: {gap_txt}" if runs else "") +
                     ". 결손 구간의 '이벤트 없음'은 사건이 없었다는 뜻이 아니라 수집이 안 됐다는 뜻입니다.")
    if ncq_isnum(f["티커매핑실패율"]) and f["티커매핑실패율"] > 0.10:
        warns.append(f"종목명→티커 매핑 실패율 {f['티커매핑실패율']*100:.1f}%. "
                     f"실패는 무작위가 아니라 신규·소형·개명 종목에 몰리는데, 그게 정확히 이 전략의 표적입니다.")
    if ncq_isnum(f["PDF추출실패율"]) and f["PDF추출실패율"] > 0.30:
        warns.append(f"PDF 본문 추출 실패율 {f['PDF추출실패율']*100:.1f}%. "
                     f"텍스트 z 는 추출 성공 문서만으로 계산되므로 표본이 하우스별로 편향됩니다.")
    lv = f["열화단계"]
    if lv:
        warns.append("열화 사다리가 적용된 실행입니다: " + ", ".join(lv) +
                     ". 사전등록 기준선과 다른 조건에서 나온 숫자이므로 그대로 비교하지 마세요.")

    ncq_alert_box(warns)
    if not warns:
        LOG.ok("§15-6 위험 경고 해당 없음 — 다만 '경고가 없다'가 '결과가 좋다'는 뜻은 아닙니다.")

    rows = [
        ["적용된 열화 단계", (", ".join(lv) if lv else "없음 (사전등록 기준선 그대로)"),
         "L5 는 자동 적용 금지"],
        ["유효 백테스트 윈도우",
         f"{ncq_xlabel(f['유효시작월']) if f['유효시작월'] is not None else NCQ_NA}"
         f" ~ {ncq_xlabel(f['유효종료월']) if f['유효종료월'] is not None else NCQ_NA}",
         f"{ncq_rpt_num(f['유효연수'], 2)}년 / 최소 {min_years:.1f}년"],
        ["유효 개월 수", ncq_int(f["유효개월수"]), f"이벤트 관측월 {ncq_int(f['이벤트월수'])}개월"],
        ["총 이벤트 수", ncq_int(f["총이벤트수"]), f"최소 {int(min_ev_t):,}건"],
        ["월평균 이벤트 수", ncq_rpt_num(f["월평균이벤트"], 2), f"최소 {min_ev_m:.0f}건"],
        ["IRS(스폰서) 비중 · 리포트", ncq_pct(f["IRS리포트비중"], 1, signed=False), "REP.is_sponsored"],
        ["IRS(스폰서) 비중 · 이벤트", ncq_pct(f["IRS이벤트비중"], 1, signed=False),
         "경고선 70% (SPONSORED_ONLY+MIXED)"],
        ["ORGANIC_ONLY 이벤트 비중", ncq_pct(f["ORGANIC이벤트비중"], 1, signed=False), "신호의 본체"],
        ["종목명→티커 매핑 실패율", ncq_pct(f["티커매핑실패율"], 2, signed=False), "경고선 10%"],
        ["PDF 추출 실패율", ncq_pct(f["PDF추출실패율"], 2, signed=False),
         f"시도 {ncq_int(f['PDF시도건수'])}건 · 경고선 30%"],
        ["아카이브 결손 태깅 월", ncq_int(f["결손태깅월수"]),
         f"3개월+ 연속 구간 {len(f['결손구간'] or [])}개"],
    ]
    LOG.table(rows, ["필수 표시 항목", "값", "기준 / 비고"], ["l", "r", "l"], maxw=48,
              title="§15-6 리포트 최상단 필수 표시")

    if lv:
        ladder = ncq_g("LADDER") or {}
        why = ncq_g("_DEGRADED") or {}
        lrows = [[x, _trunc(str(ladder.get(x, "설명 없음")), 52),
                  _trunc(str(why.get(x, NCQ_NA)), 34)] for x in lv]
        LOG.table(lrows, ["단계", "무엇을 포기했는가", "발동 사유"], ["c", "l", "l"], maxw=54,
                  title="적용된 열화 사다리 — 이 실행이 기준선과 다른 지점")

    if f["도출유효시작월"] is not None and f["유효시작월"] is not None:
        try:
            if pd.Timestamp(f["도출유효시작월"]) != pd.Timestamp(f["유효시작월"]):
                LOG.warn(f"유효 시작월 불일치 — 호출자 지정 {ncq_xlabel(f['유효시작월'])} vs "
                         f"커버리지 결손에서 도출 {ncq_xlabel(f['도출유효시작월'])}. "
                         f"둘 중 늦은 쪽을 쓰는 것이 안전합니다(결손 구간을 백테스트에 포함하면 "
                         f"'이벤트 없음'이 '현금 보유'로 잘못 해석됩니다).")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  3. 성과 리포트
# ═══════════════════════════════════════════════════════════════════════════════════════════
NCQ_PERF_ORDER = ["월수", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                  "승률", "월평균", "t통계량(HAC)", "최장언더워터(월)", "평균종목수",
                  "월평균회전율", "월평균비용"]
NCQ_PERF_PCT = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
NCQ_PERF_PCTP = {"월평균", "월평균비용"}


def ncq_fmt_metric(k: str, v) -> str:
    """지표 이름으로 단위를 정한다. 결측은 무조건 '—' (0 으로 치환 금지)."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return NCQ_NA
    if k in NCQ_PERF_PCT:
        return ncq_pct(v)
    if k in NCQ_PERF_PCTP:
        return ncq_pctp(v)
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return f"{int(v):,}"
    return ncq_rpt_num(v) if ncq_isnum(v) else _trunc(str(v), 24)


def ncq_ret_series(BT) -> pd.Series:
    """BT["returns"] → month 인덱스 월수익 Series. 형식이 어긋나면 빈 Series."""
    try:
        R = BT.get("returns") if isinstance(BT, dict) else None
        if not ncq_has_rows(R) or "ret" not in R.columns:
            return pd.Series(dtype="float64")
        mcol = ncq_pick_col(R, ["month", "월"])
        if mcol is None:
            return pd.Series(dtype="float64")
        s = pd.Series(pd.to_numeric(R["ret"], errors="coerce").to_numpy(dtype=float),
                      index=pd.DatetimeIndex(as_ts_series(R[mcol]) + pd.offsets.MonthEnd(0)))
        return s.sort_index()
    except Exception:
        return pd.Series(dtype="float64")


def ncq_cum(s: pd.Series) -> pd.Series:
    """누적수익(비율). 결측 월은 0 수익으로 '연결'하되, 그 사실을 호출부가 로그로 밝힌다."""
    if s is None or len(s) == 0:
        return pd.Series(dtype="float64")
    return (1.0 + pd.to_numeric(s, errors="coerce").fillna(0.0)).cumprod() - 1.0


def ncq_bench_role(name: str) -> str:
    low = str(name).lower()
    if "placebo" in low or "플라시보" in str(name) or "대조" in str(name):
        return "대조"
    if "bottom" in low or "ew" in low or "유니버스" in str(name) or "동일가중" in str(name):
        return "주"
    if "kospi" in low or "kosdaq" in low or "코스" in str(name) or "지수" in str(name):
        return "보조"
    return "기타"


def ncq_bench_order(benches: Dict[str, pd.Series]) -> List[str]:
    rank = {"주": 0, "보조": 1, "대조": 2, "기타": 3}
    return sorted(list((benches or {}).keys()), key=lambda k: (rank.get(ncq_bench_role(k), 9), str(k)))


def ncq_bench_table(R: pd.Series, benches: Dict[str, pd.Series]) -> List[List[str]]:
    """벤치마크별 누적 / 월평균 초과 / HAC t. 비교 구간은 항상 전략의 관측월로 제한한다."""
    rows: List[List[str]] = []
    if R is None or len(R) == 0:
        return rows
    cum_s = float((1.0 + R.fillna(0.0)).prod() - 1.0)
    for name in ncq_bench_order(benches):
        b = benches.get(name)
        try:
            bb = pd.to_numeric(pd.Series(b), errors="coerce").reindex(R.index)
        except Exception:
            bb = pd.Series(np.nan, index=R.index)
        n_ov = int(bb.notna().sum())
        if n_ov == 0:
            rows.append([ncq_bench_role(name), _trunc(name, 26), NCQ_NA, ncq_pct(cum_s, 1),
                         NCQ_NA, NCQ_NA, NCQ_NA, "0"])
            continue
        cum_b = float((1.0 + bb.fillna(0.0)).prod() - 1.0)
        ex = R.fillna(0.0) - bb.fillna(0.0)
        try:
            _mu, t = hac_tstat(ex.to_numpy(dtype=float))
        except Exception:
            _mu, t = (np.nan, np.nan)
        rows.append([ncq_bench_role(name), _trunc(name, 26), ncq_pct(cum_b, 1), ncq_pct(cum_s, 1),
                     ncq_pctp(cum_s - cum_b, 1), ncq_pctp(float(ex.mean())),
                     ncq_rpt_num(t, 2), f"{n_ov}"])
    return rows


def report_performance(BT, benches: Dict[str, pd.Series], label: str = "") -> None:
    """포트폴리오 성과 · 벤치마크 대비 · 비용 전후 · 연도별 분해.

    실패해도 예외를 올리지 않는다(리포트 계층). 대신 무엇이 없어서 못 찍었는지 남긴다.
    """
    nm = label or str((BT or {}).get("label") if isinstance(BT, dict) else "") or \
        str(ncq_g("STRATEGY_NAME", "ARC-NCQ"))
    LOG.banner(f"성과 검증 — {nm}",
               f"{ncq_g('BACKTEST_START', '?')} ~ {ncq_g('BACKTEST_END', '?')} · "
               f"오버랩 코호트 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유 · 익영업일 시가 체결 · 롱온리")

    if not isinstance(BT, dict) or not ncq_has_rows(BT.get("returns")):
        ncq_no_data("성과 검증", "BT['returns'] 가 비었습니다. 백테스트(P4)가 실행되지 않았거나 "
                                "선별된 종목이 0 이라 수익 시계열이 만들어지지 않았습니다.")
        return
    Rdf = BT["returns"]

    with ncq_section("포트폴리오 성과"):
        pf = ncq_g("perf_stats")
        s = pf(Rdf) if callable(pf) else {}
        if not s:
            ncq_no_data("포트폴리오 성과", "perf_stats 가 빈 dict 를 반환했습니다(수익 시계열 길이 0).")
        else:
            seen = set()
            rows = []
            for k in NCQ_PERF_ORDER:
                if k in s:
                    rows.append([k, ncq_fmt_metric(k, s.get(k))])
                    seen.add(k)
            for k, v in s.items():                 # 계약 밖 지표도 버리지 않는다
                if k not in seen:
                    rows.append([k, ncq_fmt_metric(k, v)])
            LOG.table(rows, ["지표", "값"], ["l", "r"], title="포트폴리오 성과 (비용 차감 후)")

    R = ncq_ret_series(BT)

    with ncq_section("비용 전·후 비교"):
        if "ret_gross" in Rdf.columns:
            pf = ncq_g("perf_stats")
            G = Rdf.copy()
            G["ret"] = pd.to_numeric(G["ret_gross"], errors="coerce")
            sg = pf(G) if callable(pf) else {}
            sn = pf(Rdf) if callable(pf) else {}
            if sg and sn:
                keys = [k for k in ("누적수익", "CAGR", "Sharpe", "월평균", "MDD", "승률")
                        if k in sg and k in sn]
                rows = []
                for k in keys:
                    a, b = sg.get(k), sn.get(k)
                    d = (float(a) - float(b)) if (ncq_isnum(a) and ncq_isnum(b)) else np.nan
                    rows.append([k, ncq_fmt_metric(k, a), ncq_fmt_metric(k, b),
                                 ncq_fmt_metric(k, d) if ncq_isnum(d) else NCQ_NA])
                cost = float(pd.to_numeric(Rdf.get("cost"), errors="coerce").mean()) \
                    if "cost" in Rdf.columns else np.nan
                LOG.table(rows, ["지표", "비용 전(gross)", "비용 후(net)", "차이"],
                          ["l", "r", "r", "r"],
                          title=f"거래비용 영향 (왕복 {float(ncq_g('NCQ_COST_ROUNDTRIP', 0.018) or 0.018)*100:.1f}% 가정 · "
                                f"월평균 비용 {ncq_pctp(cost)})")
        else:
            LOG.info("    비용 전(gross) 시계열이 BT['returns'] 에 없어 비용 전·후 비교를 생략합니다 "
                     "(ret_gross 컬럼 부재).")

    with ncq_section("벤치마크 대비"):
        rows = ncq_bench_table(R, benches or {})
        if not rows:
            ncq_no_data("벤치마크 대비", "benches 가 비었습니다. 최소한 주 벤치마크(Bottom-N EW)는 "
                                       "bench_universe_ew 로 만들어 넘겨야 비교가 성립합니다.")
        else:
            LOG.table(rows, ["역할", "벤치마크", "벤치 누적", "전략 누적", "초과", "월평균 초과",
                             "HAC t", "겹친 월"],
                      ["c", "l", "r", "r", "r", "r", "r", "r"],
                      title="벤치마크 대비 (구간은 전략 관측월로 제한 · 주=Bottom-N EW, 보조=지수, 대조=Placebo)")
            LOG.info("    ★ 판정의 기준은 주 벤치마크입니다. 하위 N 유니버스가 그 자체로 강세였던 구간에서 "
                     "지수 대비 초과는 전략의 공로가 아닙니다.")
            if not any(r[0] == "주" for r in rows):
                LOG.warn("주 벤치마크(Bottom-N 동일가중)가 없습니다 — 지수 대비 숫자만으로 결론 내리지 마세요.")
            if not any(r[0] == "대조" for r in rows):
                LOG.warn("대조군(Placebo 하위 tercile)이 없습니다 — '텍스트 z 가 방향성을 가진다'는 "
                         "주장을 반증할 장치가 빠졌습니다.")

    with ncq_section("연도별 분해"):
        if len(R) == 0:
            ncq_no_data("연도별 분해", "월수익 시계열이 비었습니다.")
        else:
            main = None
            for k in ncq_bench_order(benches or {}):
                if ncq_bench_role(k) == "주":
                    main = k
                    break
            bb = None
            if main is not None:
                try:
                    bb = pd.to_numeric(pd.Series((benches or {})[main]), errors="coerce").reindex(R.index)
                except Exception:
                    bb = None
            rows = []
            years = sorted(set(pd.DatetimeIndex(R.index).year))
            for y in years:
                m = pd.DatetimeIndex(R.index).year == y
                r = R[m].fillna(0.0)
                cy = float((1.0 + r).prod() - 1.0)
                by = np.nan
                if bb is not None and int(bb[m].notna().sum()) > 0:
                    by = float((1.0 + bb[m].fillna(0.0)).prod() - 1.0)
                nn = np.nan
                if "n" in Rdf.columns:
                    try:
                        nn = float(pd.to_numeric(Rdf["n"], errors="coerce")
                                   .to_numpy(dtype=float)[m].mean())
                    except Exception:
                        nn = np.nan
                rows.append([str(y), f"{int(m.sum())}", ncq_pct(cy, 1),
                             ncq_pct(by, 1) if ncq_isnum(by) else NCQ_NA,
                             ncq_pctp(cy - by, 1) if ncq_isnum(by) else NCQ_NA,
                             ncq_rpt_num(nn, 1),
                             ncq_sparkline(r.to_numpy(dtype=float), width=12)])
            LOG.table(rows, ["연도", "월수", "전략", (f"주벤치({_trunc(main, 14)})" if main else "주벤치"),
                             "초과", "평균종목수", "월수익 추이"],
                      ["c", "r", "r", "r", "r", "r", "l"],
                      title="연도별 성과 (좋은 해와 나쁜 해를 평균으로 덮지 않는다)")

    with ncq_section("우측 꼬리 의존도"):
        H = BT.get("holdings") if isinstance(BT, dict) else None
        if not ncq_has_rows(H) or not {"code", "weight", "ret"}.issubset(set(H.columns)):
            LOG.info("    보유 원장(holdings)이 없거나 code/weight/ret 컬럼이 없어 꼬리 의존도를 생략합니다.")
        else:
            c = (pd.to_numeric(H["weight"], errors="coerce") *
                 pd.to_numeric(H["ret"], errors="coerce"))
            contrib = c.groupby(H["code"].astype(str)).sum().sort_values(ascending=False)
            n = int(len(contrib))
            base = float(contrib.sum())
            rows = [["총기여", ncq_pctp(base, 2), f"종목 {n:,}개"]]
            for q, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
                k = max(1, int(round(n * q)))
                ex = float(contrib.iloc[k:].sum()) if k < n else np.nan
                rows.append([f"{lab} 제외 후 총기여", ncq_pctp(ex, 2), f"제외 {k:,}종목"])
            LOG.table(rows, ["항목", "값", "비고"], ["l", "r", "l"],
                      title="우측 꼬리 의존도 — 신규 커버리지 전략은 구조적으로 소수 종목에 쏠린다")
            k5 = max(1, int(round(n * 0.05)))
            ex5 = float(contrib.iloc[k5:].sum()) if k5 < n else np.nan
            if base > 0 and ncq_isnum(ex5) and ex5 <= 0:
                LOG.warn("상위 5% 종목을 빼면 총기여가 0 이하입니다. 성과가 소수 종목에 전적으로 "
                         "의존하므로, 실전에서 그 종목을 놓치면 전략 전체가 실패합니다. "
                         "사이징과 기대치를 여기에 맞추세요.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  4. 커버리지 완결성 진단 (§6.4)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def report_coverage_diagnostics(diag, REP, EV) -> None:
    """§6.4 — 리서치 아카이브가 '언제부터 믿을 만한가'를 판정한다.

    이 섹션의 결론(유효 백테스트 시작월)이 이후 모든 숫자의 전제다.
    아카이브가 얇은 구간에서 '이벤트가 없었다'는 것은 사건 부재가 아니라 관측 부재이며,
    그 구간을 백테스트에 넣으면 현금 보유 수익이 전략 성과로 둔갑한다.
    """
    LOG.banner("커버리지 완결성 진단 (§6.4)",
               "월별 수집량 · 유니크 커버 종목 · 결손 태깅 · 연속 결손 구간 → 유효 시작월 확정")

    if not ncq_has_rows(REP) and not ncq_has_rows(diag):
        ncq_no_data("커버리지 완결성", "REP(리포트 인덱스)와 diag(완결성 진단표)가 모두 비었습니다. "
                                     "수집(P1)이 전혀 수행되지 않았거나 캐시가 비어 있습니다.")
        return

    # ── (1) 월별 총 리포트 건수 — 소스별 ─────────────────────────────────────────────────
    with ncq_section("월별 리포트 건수(소스별)"):
        if not ncq_has_rows(REP):
            ncq_no_data("월별 리포트 건수", "REP 가 비었습니다(diag 만으로는 소스 분해가 불가).")
        else:
            R = REP.copy()
            dcol = ncq_pick_col(R, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is None:
                ncq_no_data("월별 리포트 건수", "REP 에 pub_date/event_date 계열 날짜 컬럼이 없습니다.")
            else:
                R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
                R = R.dropna(subset=["_m"])
                total = R.groupby("_m", observed=True).size().astype("float64").sort_index()
                total.index = pd.DatetimeIndex(total.index)
                ncq_year_spark(total, title="월별 총 리포트 건수 (전 소스 합)",
                               note="합계가 급감하는 구간은 사이트 개편·차단·PDF 정책 변경을 의심")
                scol = ncq_pick_col(R, ["source", "src", "_src"])
                if scol is None:
                    LOG.info("    소스 컬럼(source)이 없어 소스별 분해를 생략합니다.")
                else:
                    srcs = [s for s in R[scol].astype(str).value_counts().head(6).index]
                    lo = hi = None
                    per = {}
                    for s in srcs:
                        ss = ncq_fill_month_gaps(
                            R[R[scol].astype(str) == s].groupby("_m", observed=True)
                             .size().astype("float64").sort_index())
                        per[s] = ss
                    vals = np.concatenate([x.to_numpy(dtype=float) for x in per.values()]) \
                        if per else np.array([])
                    vals = vals[np.isfinite(vals)]
                    if vals.size:
                        lo, hi = float(vals.min()), float(vals.max())
                    rows = []
                    for s, ss in per.items():
                        arr = ss.to_numpy(dtype=float)
                        obs = int(np.isfinite(arr).sum())
                        rows.append([_trunc(s, 18), ncq_int(float(np.nansum(arr))),
                                     f"{obs}/{len(arr)}",
                                     ncq_xlabel(ss.index[0]) if len(ss) else NCQ_NA,
                                     ncq_xlabel(ss.index[-1]) if len(ss) else NCQ_NA,
                                     ncq_sparkline(arr, width=40, lo=lo, hi=hi)])
                    LOG.table(rows, ["소스", "총건수", "관측월", "최초월", "최종월", "월별 추이"],
                              ["l", "r", "c", "c", "c", "l"], maxw=44,
                              title="소스별 수집량 (스케일 공통 — 소스 간 두께 비교 가능)")

    # ── (2) 월별 유니크 커버 종목 수 ─────────────────────────────────────────────────────
    with ncq_section("월별 유니크 커버 종목 수"):
        if not ncq_has_rows(REP) or "stock_code" not in REP.columns:
            ncq_no_data("월별 유니크 커버 종목", "REP 에 stock_code 컬럼이 없습니다 "
                                               "(종목 매핑 단계가 수행되지 않았을 수 있습니다).")
        else:
            R = REP.copy()
            dcol = ncq_pick_col(R, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is None:
                ncq_no_data("월별 유니크 커버 종목", "날짜 컬럼이 없습니다.")
            else:
                R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
                R = R.dropna(subset=["_m", "stock_code"])
                uq = R.groupby("_m", observed=True)["stock_code"].nunique().astype("float64").sort_index()
                uq.index = pd.DatetimeIndex(uq.index)
                ncq_year_matrix(uq, title="월별 유니크 커버 종목 수 (연도×월)",
                                note="'—' 는 그 달에 매핑된 리포트가 한 건도 없다는 뜻입니다(0 과 구분).")
                ncq_year_spark(uq, title="월별 유니크 커버 종목 수 — 연도 요약")

    # ── (3) archive_incomplete 태깅 월 · 연속 결손 구간 ──────────────────────────────────
    tagged, runs, derived = ncq_archive_gaps(diag)
    with ncq_section("결손 태깅"):
        if not ncq_has_rows(diag):
            ncq_no_data("결손 태깅", "diag(coverage_completeness 산출물)가 없습니다. "
                                    "ncq_20_index.coverage_completeness 결과를 넘겨 주세요.")
        elif not tagged:
            LOG.ok("archive_incomplete 로 태깅된 월이 없습니다 — 다만 '태깅 규칙이 느슨해서 "
                   "안 걸린 것'일 수 있으므로 위 월별 추이의 급감 구간을 눈으로 확인하세요.")
        else:
            byyear: Dict[int, List[int]] = defaultdict(list)
            for m in tagged:
                byyear[int(pd.Timestamp(m).year)].append(int(pd.Timestamp(m).month))
            rows = [[str(y), f"{len(ms)}", ", ".join(f"{x}월" for x in sorted(ms))]
                    for y, ms in sorted(byyear.items())]
            LOG.table(rows, ["연도", "결손 월수", "해당 월"], ["c", "r", "l"], maxw=60,
                      title=f"archive_incomplete 태깅 월 (총 {len(tagged)}개월)")

        if runs:
            rows = [[f"{i}", ncq_xlabel(a), ncq_xlabel(b), f"{n}", "★ 유효 시작 판정 근거"
                     if (derived is not None and i == len(runs)) else ""]
                    for i, (a, b, n) in enumerate(runs, 1)]
            LOG.table(rows, ["#", "시작", "종료", "개월", "비고"], ["r", "c", "c", "r", "l"],
                      title="3개월 이상 연속 결손 구간 — 이 구간은 백테스트 유효 창에서 제외해야 한다")
        elif ncq_has_rows(diag):
            LOG.ok("3개월 이상 연속 결손 구간 없음.")

    # ── (4) 유효 백테스트 시작월 확정 ────────────────────────────────────────────────────
    with ncq_section("유효 시작월"):
        vs_attr = None
        try:
            vs_attr = as_ts((getattr(diag, "attrs", {}) or {}).get("valid_start"))
        except Exception:
            vs_attr = None
        vcol = ncq_pick_col(diag, ["valid_start", "유효시작월"])
        vs_col = None
        if vcol is not None and ncq_has_rows(diag):
            try:
                vs_col = as_ts(diag[vcol].dropna().iloc[0])
            except Exception:
                vs_col = None
        burn = ncq_g("NCQ_BURNIN_M", 24)
        look = ncq_g("NCQ_LOOKBACK_M", 24)
        rows = [
            ["결손 구간에서 도출", ncq_xlabel(derived) if derived is not None else NCQ_NA,
             "마지막 3개월+ 결손 구간의 다음 달"],
            ["diag.attrs['valid_start']", ncq_xlabel(vs_attr) if vs_attr is not None else NCQ_NA,
             "coverage_completeness 가 남긴 값"],
            ["diag 컬럼", ncq_xlabel(vs_col) if vs_col is not None else NCQ_NA, "있으면 우선"],
            ["번인(burn-in)", f"{burn}개월", "신규 커버리지 판정용 과거 관측 확보 구간"],
            ["룩백(lookback)", f"{look}개월", "H1/H2 판정 시 '커버 없음'을 확인하는 창"],
        ]
        LOG.table(rows, ["출처", "유효 시작월", "설명"], ["l", "c", "l"], maxw=52,
                  title="유효 백테스트 시작월 — 여러 출처가 다르면 가장 늦은 것을 쓴다")
        cands = [x for x in (derived, vs_attr, vs_col) if x is not None]
        if cands:
            latest = max(pd.Timestamp(x) for x in cands)
            LOG.info(f"    → 권고 유효 시작월: {ncq_xlabel(latest)} "
                     f"(가장 보수적인 값. 여기보다 앞을 쓰면 관측 부재를 성과로 오독합니다)")
        else:
            LOG.warn("유효 시작월을 어느 출처에서도 확정하지 못했습니다. "
                     "BACKTEST_START 를 그대로 쓰면 초기 구간이 아카이브 결손으로 오염됩니다.")

    # ── (5) 이벤트 쪽 관측과의 정합성 ────────────────────────────────────────────────────
    with ncq_section("리포트 vs 이벤트 정합성"):
        if not ncq_has_rows(EV):
            ncq_no_data("리포트 vs 이벤트", "EV 가 비었습니다 — 이벤트 판정(P2)이 수행되지 않았습니다.")
            return
        ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV))
        ncq_year_spark(ev_m, title="월별 신규 커버리지 이벤트 수",
                       note="리포트는 있는데 이벤트가 0 인 달이 길게 이어지면 판정 규칙(룩백/번인)을 의심")
        if ncq_has_rows(REP):
            dcol = ncq_pick_col(REP, ["pub_date", "event_date", "knowledge_date", "date"])
            if dcol is not None:
                Rm = REP.copy()
                Rm["_m"] = as_ts_series(Rm[dcol]) + pd.offsets.MonthEnd(0)
                rep_m = ncq_fill_month_gaps(
                    Rm.dropna(subset=["_m"]).groupby("_m", observed=True).size().astype("float64"))
                joint = pd.DataFrame({"rep": rep_m, "ev": ev_m}).dropna(how="all")
                bad = joint[(joint["rep"].fillna(0) > 0) & (joint["ev"].fillna(0) <= 0)]
                if len(bad):
                    LOG.warn(f"리포트는 있으나 이벤트가 0 인 달이 {len(bad)}개월 있습니다 "
                             f"(예: {', '.join(ncq_xlabel(x) for x in list(bad.index)[:6])}). "
                             f"신규 커버리지 판정이 지나치게 엄격하거나 유니버스 교집합이 비었을 수 있습니다.")
                else:
                    LOG.ok("리포트가 있는 달에는 이벤트도 관측됩니다(판정 규칙이 전면 차단되지는 않음).")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  5. 진단 9종 (§11.3)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_cohort_table(BT, SIG) -> pd.DataFrame:
    """코호트(진입 연월 × 종목)별 보유수익 + 진입 시점 신호 속성.

    1순위는 BT["cohorts"](ret_h), 없으면 BT["holdings"] 를 코호트별로 복리 합성해 만든다.
    진입 시점 속성(z / sponsor_group / event_type)은 SIG 를 (month=진입월, code) 로 붙인다.
    조인 실패는 결측으로 남긴다 — 채우지 않는다.
    """
    out = pd.DataFrame()
    try:
        C = BT.get("cohorts") if isinstance(BT, dict) else None
        if ncq_has_rows(C):
            ecol = ncq_pick_col(C, ["entry_month", "cohort", "month"])
            rcol = ncq_pick_col(C, ["ret_h", "ret", "ret_hold"])
            if ecol is not None and rcol is not None and "code" in C.columns:
                out = pd.DataFrame({
                    "entry_month": as_ts_series(C[ecol]) + pd.offsets.MonthEnd(0),
                    "code": C["code"].astype(str),
                    "ret_h": pd.to_numeric(C[rcol], errors="coerce"),
                    "n_months": pd.to_numeric(C.get("n_months"), errors="coerce")
                    if "n_months" in C.columns else np.nan,
                })
        if out.empty:
            H = BT.get("holdings") if isinstance(BT, dict) else None
            if ncq_has_rows(H) and {"code", "ret"}.issubset(set(H.columns)):
                h = H.copy()
                ccol = ncq_pick_col(h, ["cohort", "entry_month", "month"])
                if ccol is None:
                    return pd.DataFrame()
                h["_c"] = as_ts_series(h[ccol]) + pd.offsets.MonthEnd(0)
                h["_r"] = pd.to_numeric(h["ret"], errors="coerce")
                g = h.dropna(subset=["_c"]).groupby(["_c", h["code"].astype(str)], observed=True)["_r"]
                comp = g.apply(lambda x: float(np.prod(1.0 + x.dropna().to_numpy()) - 1.0)
                               if int(x.notna().sum()) else np.nan)
                cnt = g.count()
                out = comp.reset_index()
                out.columns = ["entry_month", "code", "ret_h"]
                out["n_months"] = cnt.to_numpy()
    except Exception:
        return pd.DataFrame()
    if out.empty:
        return out
    try:
        if ncq_has_rows(SIG) and {"month", "code"}.issubset(set(SIG.columns)):
            s = SIG.copy()
            s["month"] = as_ts_series(s["month"]) + pd.offsets.MonthEnd(0)
            keep = ["month", "code"] + [c for c in ("z", "sponsor_group", "event_type",
                                                    "rank_pct", "event_score", "pool_n")
                                        if c in s.columns]
            s = s[keep].drop_duplicates(subset=["month", "code"])
            s["code"] = s["code"].astype(str)
            out = out.merge(s, how="left", left_on=["entry_month", "code"],
                            right_on=["month", "code"])
            if "month" in out.columns:
                out = out.drop(columns=["month"])
    except Exception:
        pass
    return out


def ncq_dist_row(label: str, v: pd.Series) -> List[str]:
    """분포 요약 한 줄: n / min / Q1 / 중앙 / Q3 / max / 평균 / 승률."""
    x = pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    if len(x) == 0:
        return [label, "0"] + [NCQ_NA] * 7
    return [label, f"{len(x):,}", ncq_pct(float(x.min()), 1), ncq_pct(float(x.quantile(0.25)), 1),
            ncq_pct(float(x.median()), 1), ncq_pct(float(x.quantile(0.75)), 1),
            ncq_pct(float(x.max()), 1), ncq_pct(float(x.mean()), 1),
            ncq_pct(float((x > 0).mean()), 1, signed=False)]


NCQ_DIST_HEAD = ["구분", "n", "최소", "Q1", "중앙", "Q3", "최대", "평균", "승률"]
NCQ_DIST_ALIGN = ["l", "r", "r", "r", "r", "r", "r", "r", "r"]


def report_diagnostics(SIG, EV, BT, UNI, sec, benches) -> None:
    """§11.3 진단 9종. 각 항목은 데이터가 없으면 '데이터 없음 + 이유'를 반드시 출력한다."""
    LOG.banner("진단 9종 (§11.3)",
               "퍼널 · 커버리지 · 이벤트분포 · 누적곡선 · 코호트 · 섹터 · 기여종목 · 스폰서 · 단조성")
    names = ncq_name_map(sec)
    H = BT.get("holdings") if isinstance(BT, dict) else None
    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) \
        else pd.Series(dtype="float64")

    # ── 진단 1. 3단 퍼널 (유니버스 → 유동성통과 → 이벤트) ────────────────────────────────
    LOG.rule("진단 1 — 3단 퍼널 (유니버스 → 유동성 통과 → 이벤트)")
    with ncq_section("진단1 퍼널"):
        if not ncq_has_rows(UNI):
            ncq_no_data("진단1 퍼널", "UNI 가 비었습니다. PIT 유니버스 구축(P0)이 수행되지 않았습니다.")
        else:
            U = UNI.copy()
            mcol = ncq_pick_col(U, ["month", "월"])
            if mcol is None:
                ncq_no_data("진단1 퍼널", "UNI 에 month 컬럼이 없습니다.")
            else:
                U["_m"] = as_ts_series(U[mcol]) + pd.offsets.MonthEnd(0)
                U = U.dropna(subset=["_m"])
                in_uni = U["in_uni"].fillna(False).astype(bool) if "in_uni" in U.columns \
                    else pd.Series(True, index=U.index)
                liq = U["liq_pass"].fillna(False).astype(bool) if "liq_pass" in U.columns \
                    else pd.Series(np.nan, index=U.index)
                s_cand = U.groupby("_m", observed=True).size().astype("float64")
                s_uni = U[in_uni].groupby("_m", observed=True).size().astype("float64")
                s_liq = (U[in_uni & liq.fillna(False)].groupby("_m", observed=True).size()
                         .astype("float64")) if "liq_pass" in U.columns else pd.Series(dtype="float64")
                for s in (s_cand, s_uni, s_liq):
                    if len(s):
                        s.index = pd.DatetimeIndex(s.index)
                lo = hi = None
                pool = np.concatenate([x.to_numpy(dtype=float) for x in (s_cand, s_uni, s_liq) if len(x)])
                pool = pool[np.isfinite(pool)]
                if pool.size:
                    lo, hi = float(pool.min()), float(pool.max())
                rows = []
                for lab, s in (("① 후보 전체(상장·PIT)", s_cand),
                               (f"② 하위 {ncq_g('NCQ_UNIVERSE_BOTTOM_N', 1000)}개 유니버스", s_uni),
                               (f"③ 유동성 통과(ADV≥{ncq_compact(ncq_g('NCQ_MIN_ADV', 1e8))}원)", s_liq),
                               ("④ 신규 커버리지 이벤트", ev_m)):
                    if s is None or len(s) == 0:
                        rows.append([lab, NCQ_NA, NCQ_NA, NCQ_NA, "관측 없음"])
                        continue
                    ss = ncq_fill_month_gaps(pd.Series(s))
                    arr = ss.to_numpy(dtype=float)
                    rows.append([lab, ncq_rpt_num(float(np.nanmean(arr)), 1),
                                 ncq_int(float(np.nanmin(arr))), ncq_int(float(np.nanmax(arr))),
                                 ncq_sparkline(arr, width=42, lo=lo if lab.startswith(("①", "②", "③")) else None,
                                               hi=hi if lab.startswith(("①", "②", "③")) else None)])
                LOG.table(rows, ["단계", "월평균", "최소", "최대", "월별 추이"],
                          ["l", "r", "r", "r", "l"], maxw=46,
                          title="3단 퍼널 월별 시계열 (①②③ 은 스케일 공통, ④ 는 자체 스케일)")
                try:
                    m_uni = float(np.nanmean(ncq_fill_month_gaps(s_uni).to_numpy(dtype=float)))
                    m_liq = float(np.nanmean(ncq_fill_month_gaps(s_liq).to_numpy(dtype=float))) \
                        if len(s_liq) else np.nan
                    m_ev = float(np.nanmean(ev_m.to_numpy(dtype=float))) if len(ev_m) else np.nan
                    rows2 = [["유니버스 → 유동성", ncq_pct(m_liq / m_uni, 2, signed=False)
                              if ncq_isnum(m_liq) and ncq_isnum(m_uni) and m_uni > 0 else NCQ_NA],
                             ["유동성 → 이벤트", ncq_pct(m_ev / m_liq, 3, signed=False)
                              if ncq_isnum(m_ev) and ncq_isnum(m_liq) and m_liq > 0 else NCQ_NA],
                             ["유니버스 → 이벤트", ncq_pct(m_ev / m_uni, 3, signed=False)
                              if ncq_isnum(m_ev) and ncq_isnum(m_uni) and m_uni > 0 else NCQ_NA]]
                    LOG.table(rows2, ["통과 구간", "월평균 통과율"], ["l", "r"],
                              title="퍼널 감쇠율 — 어느 관문이 표본을 죽이는가")
                except Exception:
                    pass
                ncq_year_spark(ncq_fill_month_gaps(s_uni), title="유니버스 규모 연도 요약")

    # ── 진단 2. 커버리지 완결성 (요약) ───────────────────────────────────────────────────
    LOG.rule("진단 2 — 커버리지 완결성 (요약)")
    with ncq_section("진단2 커버리지 요약"):
        if len(ev_m) == 0:
            ncq_no_data("진단2 커버리지", "EV 가 비어 커버리지 요약을 만들 수 없습니다.")
        else:
            arr = ev_m.to_numpy(dtype=float)
            obs = int(np.isfinite(arr).sum())
            zero = int((np.nan_to_num(arr, nan=0.0) <= 0).sum())
            rows = [["관측 월 수", f"{len(arr)}", "이벤트 시계열이 덮는 월"],
                    ["이벤트 있는 월", f"{obs}", ncq_pct(obs / max(1, len(arr)), 1, signed=False)],
                    ["이벤트 0 인 월", f"{zero}", "결손인지 실제 부재인지는 §6.4 표를 볼 것"],
                    ["총 이벤트", ncq_int(float(np.nansum(arr))), ""],
                    ["월평균 이벤트", ncq_rpt_num(float(np.nanmean(arr)), 2),
                     f"최소 기준 {ncq_g('NCQ_MIN_EVENTS_PER_MONTH', 5)}건"]]
            LOG.table(rows, ["항목", "값", "비고"], ["l", "r", "l"],
                      title="커버리지 완결성 요약 (상세는 report_coverage_diagnostics 참조)")

    # ── 진단 3. 이벤트 수 히스토그램 ─────────────────────────────────────────────────────
    LOG.rule("진단 3 — 월별 이벤트 수 분포")
    with ncq_section("진단3 이벤트 히스토그램"):
        if len(ev_m) == 0:
            ncq_no_data("진단3 히스토그램", "EV 가 비었습니다(이벤트 판정 P2 미수행 또는 결과 0건).")
        else:
            arr = np.nan_to_num(ev_m.to_numpy(dtype=float), nan=0.0)
            edges = [0, 1, 3, 5, 10, 20, 50, 100, float("inf")]
            labs = ["0건", "1–2", "3–4", "5–9", "10–19", "20–49", "50–99", "100+"]
            cnt = [int(((arr >= edges[i]) & (arr < edges[i + 1])).sum()) for i in range(len(labs))]
            mx = max(cnt) if cnt else 0
            rows = [[labs[i], f"{cnt[i]}", ncq_pct(cnt[i] / max(1, len(arr)), 1, signed=False),
                     ncq_bar(cnt[i], mx, 40)] for i in range(len(labs))]
            LOG.table(rows, ["월간 이벤트 수", "월 개수", "비중", "분포"], ["l", "r", "r", "l"],
                      maxw=44, title="월별 이벤트 수 히스토그램 (가로축=한 달에 몇 건 났는가)")
            mean_ev = float(arr.mean())
            med_ev = float(np.median(arr))
            thin = int((arr < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5)).sum())
            LOG.table([["월평균", ncq_rpt_num(mean_ev, 2)], ["중앙값", ncq_rpt_num(med_ev, 2)],
                       ["기준 미달 월", f"{thin} / {len(arr)}"],
                       ["기준 미달 비중", ncq_pct(thin / max(1, len(arr)), 1, signed=False)]],
                      ["항목", "값"], ["l", "r"], title="요약")
            if mean_ev < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5):
                LOG.warn(f"월평균 이벤트 {mean_ev:.2f}건 < 기준 "
                         f"{ncq_g('NCQ_MIN_EVENTS_PER_MONTH', 5)}건. 월별 횡단면 z 가 성립하지 않는 달이 "
                         f"많다는 뜻이며, 이때 tercile 선별은 사실상 무작위 추첨입니다. "
                         f"결과의 부호를 해석하지 마세요.")

    # ── 진단 4. 누적수익 곡선 (ASCII) ────────────────────────────────────────────────────
    LOG.rule("진단 4 — 누적수익 곡선 (전략 vs 주벤치 vs 대조 vs 지수)")
    with ncq_section("진단4 누적곡선"):
        R = ncq_ret_series(BT)
        if len(R) == 0:
            ncq_no_data("진단4 누적곡선", "BT['returns'] 가 비어 전략 곡선을 그릴 수 없습니다.")
        else:
            curves: "OrderedDict[str, pd.Series]" = OrderedDict()
            curves["전략(NCQ)"] = ncq_cum(R)
            for k in ncq_bench_order(benches or {}):
                try:
                    b = pd.to_numeric(pd.Series((benches or {})[k]), errors="coerce").reindex(R.index)
                except Exception:
                    continue
                if int(b.notna().sum()) == 0:
                    continue
                curves[_trunc(k, 22)] = ncq_cum(b)
            ncq_print_chart(curves, title="누적수익 곡선 (전략 관측월 구간 · 비용 차감 후)",
                            height=16, width=88)
            missing = [r for r in ("주", "대조") if not any(ncq_bench_role(k) == r
                                                          for k in (benches or {}).keys())]
            if missing:
                LOG.warn("곡선에 빠진 계열: " + ", ".join(
                    {"주": "Bottom-N EW(주 벤치마크)", "대조": "Placebo 하위 tercile(대조군)"}[m]
                    for m in missing) + " — benches 에 넣어 주지 않으면 비교가 성립하지 않습니다.")

    # ── 진단 5. 코호트별 12개월 수익 분포 ────────────────────────────────────────────────
    LOG.rule("진단 5 — 코호트(진입 연월)별 보유수익 분포")
    COH = ncq_cohort_table(BT, SIG)
    with ncq_section("진단5 코호트 분포"):
        if not ncq_has_rows(COH) or "ret_h" not in COH.columns:
            ncq_no_data("진단5 코호트", "BT['cohorts'] 도 BT['holdings'] 도 코호트 수익을 만들 수 "
                                       "없습니다(진입월/보유수익 컬럼 부재).")
        else:
            rows = []
            yrs = sorted(set(pd.DatetimeIndex(COH["entry_month"].dropna()).year))
            for y in yrs:
                m = pd.DatetimeIndex(COH["entry_month"]).year == y
                rows.append(ncq_dist_row(str(y), COH.loc[m, "ret_h"]))
            rows.append(ncq_dist_row("전체", COH["ret_h"]))
            LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                      title=f"진입 연도별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 분포 "
                            f"(코호트=진입 연월×종목 · 평균이 아니라 분포를 본다)")
            x = pd.to_numeric(COH["ret_h"], errors="coerce").dropna()
            if len(x):
                LOG.info(f"    코호트 {len(x):,}개 · 승률 {float((x > 0).mean())*100:.1f}% · "
                         f"평균 {float(x.mean())*100:+.2f}% · 중앙값 {float(x.median())*100:+.2f}% "
                         f"— 평균 > 중앙값이면 소수 대박에 의존한다는 뜻입니다.")

    # ── 진단 6. 섹터 집중도 시계열 ───────────────────────────────────────────────────────
    LOG.rule("진단 6 — 보유 종목 섹터 집중도")
    with ncq_section("진단6 섹터 집중도"):
        if not ncq_has_rows(H) or "code" not in H.columns:
            ncq_no_data("진단6 섹터", "BT['holdings'] 가 비었거나 code 컬럼이 없습니다.")
        elif not ncq_has_rows(sec) or "industry" not in sec.columns:
            ncq_no_data("진단6 섹터", "sec 에 industry 컬럼이 없어 섹터를 붙일 수 없습니다.")
        else:
            h = H.copy()
            h["code"] = h["code"].astype(str)
            mcol = ncq_pick_col(h, ["month", "cohort", "entry_month"])
            h["_m"] = as_ts_series(h[mcol]) + pd.offsets.MonthEnd(0) if mcol else pd.NaT
            h["_w"] = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns else 1.0
            ind = sec.drop_duplicates(subset=["code"]).set_index(sec.drop_duplicates(
                subset=["code"])["code"].astype(str))["industry"]
            h["_ind"] = h["code"].map(ind.to_dict()).fillna("(미분류)").astype(str)
            miss = float((h["_ind"] == "(미분류)").mean())
            rows = []
            yrs = sorted(set(pd.DatetimeIndex(h["_m"].dropna()).year)) if h["_m"].notna().any() else []
            for y in yrs:
                m = pd.DatetimeIndex(h["_m"]).year == y
                sub = h.loc[m]
                w = sub.groupby("_ind", observed=True)["_w"].sum()
                tot = float(w.sum())
                if tot <= 0:
                    continue
                sh = (w / tot).sort_values(ascending=False)
                top5 = sh.head(5)
                hhi = float((sh ** 2).sum())
                # ★ 폭 104 제약: 1~5위를 각각 컬럼으로 두면 표가 넘친다 → 한 칸에 이어 붙인다.
                cells = " · ".join(f"{_trunc(str(k), 12)} {v*100:.0f}%" for k, v in top5.items())
                rows.append([str(y), ncq_int(float(sub["code"].nunique())),
                             ncq_pct(float(top5.sum()), 0, signed=False), ncq_rpt_num(hhi, 3),
                             cells])
            if not rows:
                ncq_no_data("진단6 섹터", "보유 원장에 유효한 월/가중치가 없어 연도별 집계가 비었습니다.")
            else:
                LOG.table(rows, ["연도", "종목수", "상위5합", "HHI", "상위 5 산업 (비중)"],
                          ["c", "r", "r", "r", "l"], maxw=62,
                          title="연도별 산업 비중 상위 5 (HHI 는 허핀달 — 1 에 가까울수록 한 섹터에 몰림)")
                LOG.info(f"    산업 미분류 비중 {miss*100:.1f}% · "
                         f"상위5 합이 계속 70% 를 넘으면 이 전략은 '신규 커버리지'가 아니라 "
                         f"'특정 섹터 사이클'을 타고 있는 것입니다(R7 레짐 검정과 함께 볼 것).")

    # ── 진단 7. 상·하위 기여 종목 ────────────────────────────────────────────────────────
    LOG.rule("진단 7 — 상위/하위 기여 종목")
    with ncq_section("진단7 기여 종목"):
        if not ncq_has_rows(H) or not {"code", "ret"}.issubset(set(H.columns)):
            ncq_no_data("진단7 기여종목", "BT['holdings'] 에 code/ret 컬럼이 없습니다.")
        else:
            h = H.copy()
            h["code"] = h["code"].astype(str)
            w = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns \
                else pd.Series(1.0, index=h.index)
            r = pd.to_numeric(h["ret"], errors="coerce")
            h["_c"] = w * r
            grp = h.groupby("code", observed=True)
            contrib = grp["_c"].sum().sort_values(ascending=False)
            nmon = grp.size()
            ncoh = grp["cohort"].nunique() if "cohort" in h.columns else None
            def _rows(idx, start=1):
                out = []
                for i, code in enumerate(idx, start):
                    out.append([f"{i}", code, _trunc(names.get(code, ""), 16),
                                ncq_pctp(float(contrib.get(code, np.nan)), 3),
                                ncq_int(float(nmon.get(code, np.nan))),
                                ncq_int(float(ncoh.get(code, np.nan))) if ncoh is not None else NCQ_NA])
                return out
            k = min(20, len(contrib))
            LOG.table(_rows(list(contrib.index[:k])),
                      ["#", "code", "종목명", "기여도", "보유월수", "코호트수"],
                      ["r", "l", "l", "r", "r", "r"],
                      title=f"상위 기여 종목 {k} (기여도 = Σ 월별 weight×ret, 포트 총수익 기여분)")
            tail = list(contrib.index[-k:])[::-1] if k else []
            LOG.table(_rows(tail), ["#", "code", "종목명", "기여도", "보유월수", "코호트수"],
                      ["r", "l", "l", "r", "r", "r"],
                      title=f"하위 기여 종목 {len(tail)} (손실 기여 — 여기가 실전에서 먼저 눈에 띈다)")
            tot = float(contrib.sum())
            top5 = float(contrib.head(max(1, int(round(len(contrib) * 0.05)))).sum())
            LOG.info(f"    총기여 {ncq_pctp(tot, 2)} · 상위 5% 종목 기여 {ncq_pctp(top5, 2)}"
                     + (f" (총기여의 {top5/tot*100:.0f}%)" if tot > 0 else ""))

    # ── 진단 8. 스폰서 그룹별 성과 분해 ──────────────────────────────────────────────────
    LOG.rule("진단 8 — SPONSORED_ONLY vs ORGANIC_ONLY vs MIXED")
    with ncq_section("진단8 스폰서 분해"):
        if not ncq_has_rows(COH) or "sponsor_group" not in COH.columns:
            ncq_no_data("진단8 스폰서", "코호트에 sponsor_group 을 붙이지 못했습니다 "
                                      "(SIG 에 sponsor_group 이 없거나 진입월-종목 조인 실패).")
        else:
            rows = []
            for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                sub = COH[COH["sponsor_group"].astype(str) == g]
                rows.append(ncq_dist_row(g, sub["ret_h"] if len(sub) else pd.Series(dtype=float)))
            other = COH[~COH["sponsor_group"].astype(str).isin(
                ["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"])]
            if len(other):
                rows.append(ncq_dist_row("(그 외/결측)", other["ret_h"]))
            rows.append(ncq_dist_row("전체", COH["ret_h"]))
            LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                      title="스폰서 그룹별 보유수익 분포 — '누가 왜 그 리포트를 냈는가'가 성과를 가르는가")
            trows = []
            for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                x = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == g, "ret_h"],
                                  errors="coerce").dropna()
                t = np.nan
                if len(x) >= 12:
                    try:
                        _mu, t = hac_tstat(x.to_numpy(dtype=float))
                    except Exception:
                        t = np.nan
                trows.append([g, f"{len(x):,}", ncq_pct(float(x.mean()), 2) if len(x) else NCQ_NA,
                              ncq_rpt_num(t, 2),
                              _trunc(NCQ_SPONSOR_DOC.get(g, ""), 44)])
            LOG.table(trows, ["그룹", "n", "평균 보유수익", "t(HAC·참고)", "이 그룹의 뜻"],
                      ["l", "r", "r", "r", "l"], maxw=46,
                      title="그룹별 요약 (t 는 코호트 오버랩 때문에 보수적으로 읽을 것 — 독립표본이 아니다)")
            n_org = int((COH["sponsor_group"].astype(str) == "ORGANIC_ONLY").sum())
            if n_org < 30:
                LOG.warn(f"ORGANIC_ONLY 코호트가 {n_org}개뿐입니다. 이 전략의 핵심 주장(자발적 신규 "
                         f"커버리지에 정보가 있다)을 검정할 표본이 사실상 없습니다.")
            m_org = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == "ORGANIC_ONLY",
                                          "ret_h"], errors="coerce").mean()
            m_spo = pd.to_numeric(COH.loc[COH["sponsor_group"].astype(str) == "SPONSORED_ONLY",
                                          "ret_h"], errors="coerce").mean()
            if ncq_isnum(m_org) and ncq_isnum(m_spo) and m_spo >= m_org:
                LOG.warn("SPONSORED_ONLY 의 평균 수익이 ORGANIC_ONLY 이상입니다. 이는 신호가 "
                         "'증권사의 자발적 관심'이 아니라 '스폰서 프로그램의 종목 선정 기준'을 "
                         "타고 있을 가능성을 시사합니다 — 그대로 보고합니다.")

    # ── 진단 9. 텍스트 z 분위별 수익 (단조성) ────────────────────────────────────────────
    LOG.rule("진단 9 — 텍스트 z 분위(quintile)별 수익 · 단조성")
    with ncq_section("진단9 단조성"):
        did = False
        if ncq_has_rows(COH) and "z" in COH.columns:
            d = COH.dropna(subset=["z", "ret_h"]).copy()
            if len(d) >= 25:
                did = True
                d["_q"] = (d.groupby(pd.DatetimeIndex(d["entry_month"]).to_period("M"),
                                     observed=True)["z"]
                            .rank(pct=True, method="average"))
                d["_qb"] = np.ceil(d["_q"] * 5).clip(1, 5)
                rows = []
                means = []
                for q in range(1, 6):
                    sub = d[d["_qb"] == q]
                    rows.append(ncq_dist_row(f"Q{q}" + (" (최저 z)" if q == 1 else
                                                        " (최고 z)" if q == 5 else ""),
                                             sub["ret_h"]))
                    means.append(float(pd.to_numeric(sub["ret_h"], errors="coerce").mean())
                                 if len(sub) else np.nan)
                LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                          title=f"텍스트 z 분위별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 "
                                f"(코호트 기준 — 선별된 종목만 포함될 수 있음)")
                rho_q, p_q = ncq_spearman(list(range(1, 6)), means)
                rho_i, p_i = ncq_spearman(d["z"].to_numpy(dtype=float),
                                          pd.to_numeric(d["ret_h"], errors="coerce").to_numpy(dtype=float))
                LOG.table([["분위 평균 vs 분위번호", ncq_rpt_num(rho_q, 3),
                            ncq_rpt_num(p_q, 4) if ncq_isnum(p_q) else "scipy 없음",
                            "5점이라 검정력은 매우 낮음"],
                           ["개별 관측 z vs 수익", ncq_rpt_num(rho_i, 3),
                            ncq_rpt_num(p_i, 4) if ncq_isnum(p_i) else "scipy 없음",
                            f"n={len(d):,} · 코호트 오버랩으로 독립 아님"]],
                          ["대상", "스피어만 ρ", "p", "주의"], ["l", "r", "r", "l"], maxw=40,
                          title="단조성 검정")
                mono = all(ncq_isnum(a) and ncq_isnum(b) and b >= a
                           for a, b in zip(means[:-1], means[1:]))
                if mono:
                    LOG.ok("Q1→Q5 평균이 단조 증가합니다. 다만 분위 간 차이가 표본오차 안일 수 있으니 "
                           "위 ρ 와 각 분위 n 을 함께 보세요.")
                else:
                    LOG.warn("Q1→Q5 평균이 단조가 아닙니다. 텍스트 z 가 '연속적인 강도'가 아니라 "
                             "특정 구간에서만 의미를 가지거나, 표본이 얇아 노이즈일 수 있습니다. "
                             "단조성이 없다고 전략이 자동 기각되지는 않지만, 근거는 그만큼 약합니다.")
                cov = [int((d["_qb"] == q).sum()) for q in range(1, 6)]
                if min(cov) == 0:
                    LOG.warn(f"비어 있는 분위가 있습니다(분위별 n={cov}). 코호트가 상위 tercile 만 "
                             f"포함하기 때문일 가능성이 큽니다 — 아래 전 이벤트 기준 표를 보세요.")
        if ncq_has_rows(SIG) and {"z"}.issubset(set(SIG.columns)) and "fwd_ret" in SIG.columns:
            s = SIG.dropna(subset=["z", "fwd_ret"]).copy()
            if len(s) >= 25:
                did = True
                s["month"] = as_ts_series(s["month"]) + pd.offsets.MonthEnd(0)
                s["_q"] = s.groupby("month", observed=True)["z"].rank(pct=True, method="average")
                s["_qb"] = np.ceil(s["_q"] * 5).clip(1, 5)
                rows, means = [], []
                for q in range(1, 6):
                    sub = s[s["_qb"] == q]
                    rows.append(ncq_dist_row(f"Q{q}", sub["fwd_ret"]))
                    means.append(float(pd.to_numeric(sub["fwd_ret"], errors="coerce").mean())
                                 if len(sub) else np.nan)
                LOG.table(rows, NCQ_DIST_HEAD, NCQ_DIST_ALIGN,
                          title="텍스트 z 분위별 1개월 선도수익 (전 이벤트 — 12개월 수익이 "
                                "선별 종목에만 있어 대체 지표로 병기)")
                rho, p = ncq_spearman(list(range(1, 6)), means)
                LOG.info(f"    분위 단조성 ρ={ncq_rpt_num(rho, 3)} "
                         f"p={ncq_rpt_num(p, 4) if ncq_isnum(p) else 'scipy 없음'} "
                         f"— 보유기간이 1개월이라 전략의 실제 구성과 다릅니다(참고용).")
        if not did:
            ncq_no_data("진단9 단조성", "z 와 수익을 함께 가진 관측이 25건 미만입니다 "
                                      "(SIG.z / SIG.fwd_ret / 코호트 ret_h 중 어느 것도 충분치 않음).")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  6. 해석 참조표
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_lexicon_group_info() -> "OrderedDict[str, dict]":
    """렉시콘 그룹 메타 — 라벨/가중/어휘수는 정본(NCQ_LEXICON)에서, 해석문은 이 파일에서.

    정본에만 있는 그룹(렉시콘을 v2 로 올린 경우)도 표에서 빠지지 않게 합집합으로 만든다.
    """
    out: "OrderedDict[str, dict]" = OrderedDict()
    for g, (label, mean_, fire, nofire, sign) in NCQ_GROUP_DOC.items():
        out[g] = {"label": label, "뜻": mean_, "발화": fire, "미발화": nofire,
                  "방향": sign, "weight": None, "n_terms": None, "출처": "내장 참조표"}
    lex = ncq_g("NCQ_LEXICON")
    try:
        groups = lex.get("groups") if isinstance(lex, dict) else None
        if isinstance(groups, dict):
            for k, v in groups.items():
                gid = str(k).upper()
                if gid.startswith("G_"):
                    gid = gid[2:]
                if gid not in out:
                    out[gid] = {"label": str(k), "뜻": "(정본 렉시콘에만 존재 — 해석문 미작성)",
                                "발화": NCQ_NA, "미발화": NCQ_NA, "방향": "?",
                                "weight": None, "n_terms": None, "출처": "NCQ_LEXICON"}
                d = out[gid]
                if isinstance(v, dict):
                    if v.get("label"):
                        d["label"] = str(v["label"])
                        d["출처"] = "NCQ_LEXICON"
                    if ncq_isnum(v.get("weight")):
                        d["weight"] = float(v["weight"])
                    terms = v.get("terms") or v.get("words") or v.get("patterns")
                    if isinstance(terms, (list, tuple, set)):
                        d["n_terms"] = len(terms)
                elif isinstance(v, (list, tuple, set)):
                    d["n_terms"] = len(v)
    except Exception:
        pass
    return out


def report_interpretation(SIG, EV, SCORE) -> None:
    """해석 참조표 — 이 신호가 발화했다는 것이 무엇을 뜻하는가.

    참조표 부분은 데이터가 없어도 항상 출력한다(리포트의 존재 이유가 해석이기 때문).
    통계 부분은 데이터가 없으면 '데이터 없음 + 이유'를 남긴다.
    """
    LOG.banner("해석 참조표",
               "렉시콘 그룹의 뜻 · 발화/미발화의 의미 · 실제 패널의 발화 프로필 · 이벤트 유형 분포")
    info = ncq_lexicon_group_info()

    with ncq_section("렉시콘 그룹 정의"):
        # 폭 104 제약: '정의 출처'는 표에서 빼고 아래 한 줄로 요약한다(값이 대개 동일하다).
        rows = [[g, _trunc(d["label"], 14), d["방향"],
                 ncq_rpt_num(d["weight"], 1) if ncq_isnum(d["weight"]) else NCQ_NA,
                 ncq_int(d["n_terms"]) if ncq_isnum(d["n_terms"]) else NCQ_NA,
                 _trunc(d["뜻"], 54)]
                for g, d in info.items()]
        LOG.table(rows, ["그룹", "라벨", "방향", "가중", "어휘수", "무엇을 잡는가"],
                  ["c", "l", "c", "r", "r", "l"], maxw=56,
                  title="렉시콘 그룹 A/B/C/D/H/N (방향 +강=최대가중, −역=역가중)")
        srcs = sorted(set(d["출처"] for d in info.values()))
        LOG.info(f"    정의 출처: {', '.join(srcs)} "
                 f"(라벨·가중·어휘수는 정본 NCQ_LEXICON, 해석문은 리포트 모듈 내장 참조표)")
        LOG.info(f"    섹션 가중: {json.dumps((ncq_g('NCQ_LEXICON') or {}).get('section_weight', {}), ensure_ascii=False)}"
                 f" · 부정어 창: {(ncq_g('NCQ_LEXICON') or {}).get('negation_window', NCQ_NA)}자 "
                 f"— 부정 문맥에서는 매칭을 무효화합니다(‘증설이 어렵다’를 호재로 세지 않기 위함).")

    with ncq_section("발화/미발화 해석"):
        rows = [[g, _trunc(d["발화"], 44), _trunc(d["미발화"], 44)] for g, d in info.items()]
        LOG.table(rows, ["그룹", "발화했다는 것은 무엇을 뜻하는가", "발화하지 않았다는 것은 무엇을 뜻하는가"],
                  ["c", "l", "l"], maxw=46,
                  title="★ 이 표가 이 전략의 전부다 — 점수는 이 해석의 요약일 뿐이다")
        LOG.info("    주의: H/N 은 역가중이므로 '발화 = 점수 하락'입니다. 발화율이 높은 것 자체가 "
                 "나쁜 것이 아니라, 그 문서가 근거보다 기대를 많이 적었다는 뜻입니다.")

    with ncq_section("실제 패널 발화 통계"):
        gcols = [f"g_{g}" for g in info.keys()]
        have = [c for c in gcols if ncq_has_rows(SCORE) and c in SCORE.columns]
        if not have:
            ncq_no_data("발화 통계", "SCORE 가 비었거나 g_* 컬럼이 없습니다 "
                                   "(텍스트 스코어링 P3 미수행 또는 PDF 추출 전면 실패).")
        else:
            S = SCORE
            abs_mean = {c: float(pd.to_numeric(S[c], errors="coerce").abs().mean()) for c in have}
            tot_abs = float(sum(v for v in abs_mean.values() if np.isfinite(v))) or np.nan
            rows = []
            for c in have:
                v = pd.to_numeric(S[c], errors="coerce")
                obs = int(v.notna().sum())
                fired = v.abs() > 0
                nf = int(fired.sum())
                corr = np.nan
                if "doc_score" in S.columns:
                    try:
                        corr = float(v.corr(pd.to_numeric(S["doc_score"], errors="coerce")))
                    except Exception:
                        corr = np.nan
                rows.append([c.replace("g_", ""), f"{obs:,}", f"{nf:,}",
                             ncq_pct(nf / max(1, obs), 1, signed=False),
                             ncq_rpt_num(float(v[fired].mean()), 3) if nf else NCQ_NA,
                             ncq_rpt_num(float(v.mean()), 3) if obs else NCQ_NA,
                             ncq_pct(abs_mean[c] / tot_abs, 1, signed=False)
                             if ncq_isnum(tot_abs) and tot_abs > 0 else NCQ_NA,
                             ncq_rpt_num(corr, 3)])
            LOG.table(rows, ["그룹", "관측문서", "발화문서", "발화율", "발화시 평균",
                             "전체 평균", "절대기여 비중", "doc_score 상관"],
                      ["c", "r", "r", "r", "r", "r", "r", "r"],
                      title="그룹별 발화 빈도·평균 기여 (문서 단위)")
            dead = [r[0] for r in rows if r[2] == "0"]
            if dead:
                LOG.warn(f"한 번도 발화하지 않은 그룹: {', '.join(dead)}. 렉시콘 어휘가 실제 리포트 "
                         f"문체와 어긋났거나, 해당 섹션이 추출되지 않았습니다 — 점수에서 그 축은 "
                         f"존재하지 않는 것과 같습니다.")

    with ncq_section("z tercile 그룹 프로필"):
        gcols = [f"g_{g}" for g in info.keys()]
        have = [c for c in gcols if ncq_has_rows(SCORE) and c in SCORE.columns]
        if not have or not ncq_has_rows(SIG) or "z" not in getattr(SIG, "columns", []):
            ncq_no_data("z tercile 프로필", "SIG.z 또는 SCORE.g_* 가 없어 상·하위 대비표를 만들 수 없습니다.")
        else:
            S = SCORE.copy()
            if not {"month", "code"}.issubset(set(S.columns)):
                ncq_no_data("z tercile 프로필", "SCORE 에 month/code 가 없어 SIG 와 조인할 수 없습니다.")
            else:
                S["month"] = as_ts_series(S["month"]) + pd.offsets.MonthEnd(0)
                S["code"] = S["code"].astype(str)
                agg = S.groupby(["month", "code"], observed=True)[have].mean().reset_index()
                Q = SIG.copy()
                Q["month"] = as_ts_series(Q["month"]) + pd.offsets.MonthEnd(0)
                Q["code"] = Q["code"].astype(str)
                Q = Q[["month", "code", "z"]].dropna(subset=["z"])
                M = Q.merge(agg, how="inner", on=["month", "code"])
                if len(M) < 20:
                    ncq_no_data("z tercile 프로필", f"조인 결과가 {len(M)}행뿐입니다 "
                                                  f"(month/code 키가 어긋났을 가능성).")
                else:
                    ter = float(ncq_g("NCQ_TERCILE", 1 / 3) or (1 / 3))
                    r = M.groupby("month", observed=True)["z"].rank(pct=True, method="average")
                    hi = M[r >= (1.0 - ter)]
                    lo = M[r <= ter]
                    rows = []
                    for c in have:
                        a = pd.to_numeric(hi[c], errors="coerce")
                        b = pd.to_numeric(lo[c], errors="coerce")
                        ma, mb = (float(a.mean()) if len(a) else np.nan,
                                  float(b.mean()) if len(b) else np.nan)
                        rows.append([c.replace("g_", ""), ncq_rpt_num(ma, 3), ncq_rpt_num(mb, 3),
                                     ncq_rpt_num(ma - mb, 3) if (ncq_isnum(ma) and ncq_isnum(mb)) else NCQ_NA,
                                     ncq_pct(float((a.abs() > 0).mean()), 1, signed=False) if len(a) else NCQ_NA,
                                     ncq_pct(float((b.abs() > 0).mean()), 1, signed=False) if len(b) else NCQ_NA])
                    LOG.table(rows, ["그룹", "상위T 평균", "하위T 평균", "차이",
                                     "상위T 발화율", "하위T 발화율"],
                              ["c", "r", "r", "r", "r", "r"],
                              title=f"z 상위/하위 tercile 의 그룹 프로필 대비 "
                                    f"(상위 n={len(hi):,} · 하위 n={len(lo):,})")
                    LOG.info("    ★ 읽는 법: 상·하위 tercile 을 실제로 가르는 그룹이 무엇인지 보세요. "
                             "차이가 H/N 에서만 크다면 이 신호는 '좋은 이야기'가 아니라 "
                             "'덜 조심스러운 문체'를 고르고 있는 것입니다.")

    with ncq_section("이벤트 유형·스폰서 분포"):
        LOG.table([[k, v[0], _trunc(v[1], 62)] for k, v in NCQ_EVENT_TYPE_DOC.items()],
                  ["유형", "이름", "판정 기준"], ["c", "l", "l"], maxw=64,
                  title="신규 커버리지 이벤트 유형 (정본은 ncq_30_coverage)")
        LOG.table([[k, _trunc(v, 78)] for k, v in NCQ_SPONSOR_DOC.items()],
                  ["스폰서 그룹", "뜻"], ["l", "l"], maxw=80, title="스폰서 그룹")
        if not ncq_has_rows(EV) or "event_type" not in EV.columns:
            ncq_no_data("이벤트 분포", "EV 에 event_type 이 없습니다.")
        else:
            sg = EV["sponsor_group"].astype(str) if "sponsor_group" in EV.columns else None
            et = EV["event_type"].astype(str)
            if sg is None:
                vc = et.value_counts()
                LOG.table([[k, f"{v:,}", ncq_pct(v / max(1, len(et)), 1, signed=False)]
                           for k, v in vc.items()],
                          ["유형", "건수", "비중"], ["c", "r", "r"],
                          title="이벤트 유형 분포 (sponsor_group 부재로 교차표 생략)")
            else:
                cols = ["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"]
                cols += sorted(set(sg.unique()) - set(cols))
                rows = []
                for t in sorted(set(et.unique())):
                    m = et == t
                    n = int(m.sum())
                    cells = [f"{int((m & (sg == c)).sum()):,}" for c in cols]
                    rows.append([t, f"{n:,}"] + cells +
                                [ncq_pct(n / max(1, len(et)), 1, signed=False)])
                tot = [f"{int((sg == c).sum()):,}" for c in cols]
                rows.append(["합계", f"{len(et):,}"] + tot + ["100.0%"])
                LOG.table(rows, ["유형", "건수"] + [_trunc(c, 14) for c in cols] + ["비중"],
                          ["c", "r"] + ["r"] * len(cols) + ["r"], maxw=16,
                          title="이벤트 유형 × 스폰서 그룹 교차표")
                p_h1 = float((et == "H1").mean())
                LOG.info(f"    H1(전면 신규) 비중 {p_h1*100:.1f}%. "
                         f"H2 가 대부분이라면 이 전략은 '정보 공백'이 아니라 "
                         f"'하우스 간 커버 확산'을 측정하고 있는 것입니다.")


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  7. 거시 흐름 지도
# ═══════════════════════════════════════════════════════════════════════════════════════════
NCQ_PHASE_MAP = [
    ("P0", "부트 · 캐시 · PIT 유니버스",
     ["입력  종목마스터(pykrx 월말 스냅샷 / FDR·KIND 상장·폐지 / DART corpCode) · KRX·pykrx 일봉",
      "출력  sec · px_daily · pxm(월말 신호일 → 익영업일 시가 exec_px) · MCAP · UNI",
      "캐시  _shared/table/{krx_ohlcv_daily, security_master_ncq, pykrx_snapshot_*}  ← 공용(타 전략 재사용)",
      "PIT   시총·ADV 는 그 달 말 관측값만. 상폐 종목을 유니버스에서 빼지 않는다(생존자편향 §10)"]),
    ("P1", "리서치 인덱스 수집 (가장 긴 단계 · 예산 초과 시 열화 L1)",
     ["입력  IRS(거래소 발간지원) · 네이버 금융 리서치 · 한경컨센서스",
      "출력  REP(report_uid, source, pub_date, stock_code, broker_id, is_sponsored, …)",
      "캐시  _shared/table/research_report_master · _shared/blob/research/report_pdf/<해시>",
      "함정  종목명→티커 매핑 실패는 신규·소형·개명 종목에 몰린다 = 정확히 이 전략의 표적"]),
    ("P2", "커버리지 완결성 · 신규 커버리지 이벤트 판정",
     ["입력  REP · UNI · months",
      "출력  diag(월별 완결성 · archive_incomplete) → valid_start · EV(H1/H2 · sponsor_group)",
      "게이트 아카이브 3개월+ 연속 결손 구간 이후로 유효 백테스트 시작월을 늦춘다",
      "PIT   판정에 쓰는 리포트는 pub_date ≤ 해당 월말. 룩백/번인 구간은 판정에만 쓰고 매매하지 않는다"]),
    ("P3", "PDF 섹션 추출 · 렉시콘 스코어링 (예산 초과 시 열화 L2)",
     ["입력  EV 에 연결된 리포트의 PDF · 제목 · 요약",
      "출력  TXT(sec_title/headline/body, extract_ok) → SCORE(doc_score, g_A…g_N)",
      "동결  렉시콘·사전등록은 수익률 확인 전에 동결하고 SHA 를 매니페스트에 남긴다(계약 §6-4)",
      "함정  추출 실패는 하우스별로 편향된다 → 텍스트 z 표본이 특정 증권사로 쏠릴 수 있다"]),
    ("P4", "횡단면 z · 신호 패널 · 오버랩 코호트 백테스트",
     ["입력  SCORE · EV · UNI · pxm",
      "출력  SIG(z, rank_pct, selected, placebo) → BT{returns, holdings, cohorts}",
      "체결  월말 신호 → 익영업일 시가 · ADV 참여율 상한 · 왕복비용 · 상폐 시 -50% 후 현금화",
      "대조  placebo = z 하위 tercile · 주 벤치 = Bottom-N 동일가중"]),
    ("P5", "강건성 (사전등록 P1~P4 · BH-FDR · 부트스트랩 · 순열 · WF · PBO · DSR)",
     ["입력  SIG · BT · bench_ew · run_fn",
      "출력  NCQ_ROBUST(검정별 pass/kill) · 민감도 격자 · 다중검정 보정 결과",
      "원칙  실패한 검정은 그대로 출력한다. 파라미터를 바꿔 통과시키는 것이 가장 해로운 행동이다"]),
    ("P6", "리포트 · 산출물",
     ["입력  위 전부 + MANIFEST",
      "출력  콘솔 표(1순위) · report.html · coverage.html · manifest.json · parquet/csv",
      "저장  VAULT.put_table(scope='private') — 공용 인덱스에는 원본·범용 정제본만 넣는다"]),
]


def report_dataflow_map() -> None:
    """거시 흐름 지도 — 에러가 나면 어느 상자인지부터 좁힌다."""
    LOG.banner("데이터 흐름 지도 (거시) — ARC-NCQ v1.0",
               "Phase 0~6 · 각 단계의 입출력 / 캐시 위치 / PIT 관문을 한 화면에")
    budgets = ncq_g("NCQ_PHASE_BUDGET_S", {}) or {}
    spent = {}
    try:
        pb = ncq_g("PhaseBudget")
        spent = dict(getattr(pb, "_spent", {}) or {})
    except Exception:
        spent = {}
    width = min(NCQ_W - 2, 100)
    for i, (pid, title, lines) in enumerate(NCQ_PHASE_MAP):
        cap = budgets.get(pid)
        sp = spent.get(pid)
        head = f"{pid}  {title}"
        if ncq_isnum(cap):
            head += f"   [예산 {float(cap)/60:.0f}분"
            head += (f" · 실측 {float(sp)/60:.1f}분]" if ncq_isnum(sp) else "]")
        for ln in ncq_box(head, lines, width=width):
            _safe_print("  " + ln)
        if i < len(NCQ_PHASE_MAP) - 1:
            gate = "▼   PIT 관문: pub_date ≤ 월말 · 진입은 익영업일 시가" if pid in ("P1", "P3") else "▼"
            _safe_print("  " + " " * (width // 2 - 1) + gate)
    _safe_print("")
    for ln in ncq_box("실패했을 때 보는 순서",
                      ["1) PIPE.report_stages() — 어느 스테이지에서 멈췄는가",
                       "2) PIPE.report_flow()   — 그 스테이지가 몇 행을 읽고 썼는가 (0행이면 수집 실패)",
                       "3) report_coverage_diagnostics — 아카이브가 얇은 구간인가",
                       "4) report_diagnostics 진단1 퍼널 — 어느 관문이 표본을 죽였는가",
                       "5) report_headline — 열화 사다리가 적용된 실행인가"],
                      width=width):
        _safe_print("  " + ln)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  8. HTML 산출물 — 외부 라이브러리 없이 순수 문자열 (인라인 CSS · <table> · 인라인 SVG)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def ncq_html_head(title: str, sub: str = "") -> str:
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{ncq_esc(title)}</title><style>{NCQ_HTML_CSS}</style></head><body><div class='wrap'>"
            f"<h1>{ncq_esc(title)}</h1><p class='sub'>{ncq_esc(sub)}</p>")


def ncq_html_tail(extra: str = "") -> str:
    return (f"<footer>{extra}생성 {ncq_esc(_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} · "
            f"{ncq_esc(ncq_g('STRATEGY_ID', 'ARC_NCQ_V1'))} "
            f"{ncq_esc(ncq_g('BUILD_VERSION', ''))} · "
            f"이 파일은 자체 완결형입니다(외부 리소스 요청 없음).</footer></div></body></html>")


def ncq_html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]],
                   title: str = "", note: str = "", left_cols: Sequence[int] = (0,)) -> str:
    """표 하나. rows 가 비면 '데이터 없음'을 명시해서 남긴다(조용히 사라지지 않게)."""
    out = []
    if title:
        out.append(f"<h3>{ncq_esc(title)}</h3>")
    if not rows:
        out.append("<p class='mut'>데이터 없음 — 이 표를 만들 입력이 비었습니다.</p>")
        if note:
            out.append(f"<p class='note'>{ncq_esc(note)}</p>")
        return "".join(out)
    lc = set(int(i) for i in (left_cols or ()))
    out.append("<table><thead><tr>")
    for i, h in enumerate(headers):
        out.append(f"<th class='{'l' if i in lc else ''}'>{ncq_esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>")
        for i in range(len(headers)):
            v = r[i] if i < len(r) else ""
            cls = "l" if i in lc else ""
            txt = ncq_esc("" if v is None else v)
            if isinstance(v, str) and (v.startswith("✘") or v.startswith("−") or "미달" in v):
                cls += " bad"
            out.append(f"<td class='{cls.strip()}'>{txt}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    if note:
        out.append(f"<p class='note'>{ncq_esc(note)}</p>")
    return "".join(out)


def ncq_svg_line(series_dict: Dict[str, Any], width: int = 880, height: int = 300,
                 title: str = "", pct: bool = True) -> str:
    """인라인 SVG 라인차트. 외부 라이브러리 없음. 그릴 게 없으면 빈 문자열."""
    pal = ["#1a73e8", "#d93025", "#188038", "#f29900", "#9334e6", "#00838f"]
    items = []
    for name, s in (series_dict or {}).items():
        try:
            ss = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            continue
        if len(ss):
            items.append((str(name), ss))
    if not items:
        return ""
    try:
        uni = pd.Index(sorted(set().union(*[set(pd.Index(s.index)) for _, s in items])))
        cols = [(nm, pd.Series(s).reindex(uni).astype(float).ffill()) for nm, s in items]
    except Exception:
        return ""
    allv = np.concatenate([c.dropna().to_numpy(dtype=float) for _, c in cols if c.notna().any()])
    if allv.size == 0:
        return ""
    ymin, ymax = float(allv.min()), float(allv.max())
    if ymax - ymin < 1e-12:
        ymax = ymin + 1e-9
    pad = (ymax - ymin) * 0.06
    ymin, ymax = ymin - pad, ymax + pad
    L, Rr, T, B = 66, 16, 30 if title else 12, 34
    n = len(uni)
    def X(i):
        return L + (0 if n <= 1 else (width - L - Rr) * i / (n - 1))
    def Y(v):
        return T + (height - T - B) * (ymax - float(v)) / (ymax - ymin)
    def fnum(v):
        return f"{v*100:.0f}%" if pct else f"{v:.3g}"
    p = [f"<svg viewBox='0 0 {width} {height}' width='100%' "
         f"style='max-width:{width}px;height:auto' xmlns='http://www.w3.org/2000/svg'>",
         f"<rect x='0' y='0' width='{width}' height='{height}' fill='#ffffff'/>"]
    if title:
        p.append(f"<text x='{L}' y='18' font-size='13' fill='#1f2328'>{ncq_esc(title)}</text>")
    for k in range(5):                                    # y 격자
        v = ymax - (ymax - ymin) * k / 4.0
        y = Y(v)
        p.append(f"<line x1='{L}' y1='{y:.1f}' x2='{width-Rr}' y2='{y:.1f}' "
                 f"stroke='#e6e9ee' stroke-width='1'/>")
        p.append(f"<text x='{L-6}' y='{y+4:.1f}' font-size='11' fill='#6a737d' "
                 f"text-anchor='end'>{ncq_esc(fnum(v))}</text>")
    if ymin < 0 < ymax:
        p.append(f"<line x1='{L}' y1='{Y(0):.1f}' x2='{width-Rr}' y2='{Y(0):.1f}' "
                 f"stroke='#9aa4b0' stroke-width='1' stroke-dasharray='4 3'/>")
    for ci, (nm, c) in enumerate(cols):
        col = pal[ci % len(pal)]
        pts = []
        for i, v in enumerate(c.to_numpy(dtype=float)):
            if np.isfinite(v):
                pts.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(pts) >= 2:
            p.append(f"<polyline fill='none' stroke='{col}' stroke-width='2' "
                     f"stroke-linejoin='round' points='{' '.join(pts)}'/>")
        lx = L + 4 + ci * max(120, int((width - L - Rr) / max(1, len(cols))))
        p.append(f"<rect x='{lx}' y='{height-16}' width='10' height='3' fill='{col}'/>")
        p.append(f"<text x='{lx+14}' y='{height-11}' font-size='11' fill='#39424e'>"
                 f"{ncq_esc(_trunc(nm, 22))}</text>")
    for i, lab in ((0, ncq_xlabel(uni[0])), (n // 2, ncq_xlabel(uni[n // 2])),
                   (n - 1, ncq_xlabel(uni[-1]))):
        p.append(f"<text x='{X(i):.1f}' y='{height-B+16}' font-size='11' fill='#6a737d' "
                 f"text-anchor='middle'>{ncq_esc(lab)}</text>")
    p.append("</svg>")
    return "<div class='chart'>" + "".join(p) + "</div>"


def ncq_headline_html(f: "OrderedDict[str, Any]", warns: Sequence[str]) -> str:
    out = []
    if warns:
        out.append("<div class='alert'><b>⚠ 위험 경고 — 아래 숫자를 읽기 전에</b><ul>" +
                   "".join(f"<li>{ncq_esc(w)}</li>" for w in warns) + "</ul></div>")
    else:
        out.append("<div class='ok'>§15-6 위험 경고 해당 없음. "
                   "다만 '경고가 없다'가 '결과가 좋다'는 뜻은 아닙니다.</div>")
    rows = [
        ["적용된 열화 단계", ", ".join(f["열화단계"]) if f["열화단계"] else "없음 (사전등록 기준선)"],
        ["유효 백테스트 윈도우",
         f"{ncq_xlabel(f['유효시작월']) if f['유효시작월'] is not None else NCQ_NA} ~ "
         f"{ncq_xlabel(f['유효종료월']) if f['유효종료월'] is not None else NCQ_NA} "
         f"({ncq_rpt_num(f['유효연수'], 2)}년)"],
        ["총 이벤트 수", ncq_int(f["총이벤트수"])],
        ["월평균 이벤트 수", ncq_rpt_num(f["월평균이벤트"], 2)],
        ["IRS(스폰서) 비중 · 리포트", ncq_pct(f["IRS리포트비중"], 1, signed=False)],
        ["IRS(스폰서) 비중 · 이벤트", ncq_pct(f["IRS이벤트비중"], 1, signed=False)],
        ["종목명→티커 매핑 실패율", ncq_pct(f["티커매핑실패율"], 2, signed=False)],
        ["PDF 추출 실패율", ncq_pct(f["PDF추출실패율"], 2, signed=False)],
        ["아카이브 결손 태깅 월", ncq_int(f["결손태깅월수"])],
    ]
    out.append(ncq_html_table(["필수 표시 항목(§15-6)", "값"], rows, left_cols=(0,)))
    return "".join(out)


def write_html_report(outdir, ctx) -> str:
    """성과·진단 요약 HTML. ctx 에서 가용한 것만 넣고 없으면 생략한다. 반환은 파일 경로."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, f"ncq_report_{_dt.datetime.now():%Y%m%d_%H%M}.html")
    BT = ncq_rpt_ctx_get(ctx, "BT")
    benches = ncq_rpt_ctx_get(ctx, "benches") or {}
    EV = ncq_rpt_ctx_get(ctx, "EV")
    SIG = ncq_rpt_ctx_get(ctx, "SIG")
    sec = ncq_rpt_ctx_get(ctx, "sec")
    names = ncq_name_map(sec)
    f = ncq_headline_facts(ctx)

    warns = []
    try:
        if ncq_isnum(f["월평균이벤트"]) and f["월평균이벤트"] < float(ncq_g("NCQ_MIN_EVENTS_PER_MONTH", 5) or 5):
            warns.append(f"월평균 이벤트 {f['월평균이벤트']:.2f}건 — 최소 기준 미달. "
                         f"횡단면 선별이 사실상 소수 종목 추첨입니다.")
        if ncq_isnum(f["총이벤트수"]) and f["총이벤트수"] < float(ncq_g("NCQ_MIN_TOTAL_EVENTS", 800) or 800):
            warns.append(f"총 이벤트 {int(f['총이벤트수']):,}건 — 최소 기준 미달. 검정력이 낮습니다.")
        if ncq_isnum(f["IRS이벤트비중"]) and f["IRS이벤트비중"] > 0.70:
            warns.append(f"IRS(스폰서) 포함 이벤트 비중 {f['IRS이벤트비중']*100:.1f}% — 70% 초과. "
                         f"자발적 관심이 아니라 발간지원 대상 선정을 측정할 위험.")
        if ncq_isnum(f["유효연수"]) and f["유효연수"] < float(ncq_g("NCQ_MIN_VALID_YEARS", 5.0) or 5.0):
            warns.append(f"유효 구간 {f['유효연수']:.2f}년 — 최소 기준 미달.")
        if f["열화단계"]:
            warns.append("열화 적용: " + ", ".join(f["열화단계"]) + " — 기준선과 조건이 다릅니다.")
    except Exception:
        pass

    H: List[str] = [ncq_html_head(
        f"ARC-NCQ v1.0 리포트 — {ncq_esc(str((BT or {}).get('label', '') if isinstance(BT, dict) else ''))}",
        f"{ncq_g('BACKTEST_START', '?')} ~ {ncq_g('BACKTEST_END', '?')} · "
        f"오버랩 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유 · 익영업일 시가 체결 · 롱온리 · "
        f"실행모드 {ncq_g('RUN_MODE', '?')}")]

    H.append("<h2>0. 헤드라인 (§15-6)</h2>")
    H.append(ncq_headline_html(f, warns))

    # 성과
    H.append("<h2>1. 성과</h2>")
    R = ncq_ret_series(BT)
    pf = ncq_g("perf_stats")
    s = pf(BT["returns"]) if (callable(pf) and isinstance(BT, dict)
                              and ncq_has_rows(BT.get("returns"))) else {}
    if s:
        order = [k for k in NCQ_PERF_ORDER if k in s] + [k for k in s if k not in NCQ_PERF_ORDER]
        H.append(ncq_html_table(["지표", "값"], [[k, ncq_fmt_metric(k, s[k])] for k in order],
                                title="포트폴리오 성과 (비용 차감 후)", left_cols=(0,)))
    else:
        H.append("<p class='mut'>성과 지표 없음 — BT['returns'] 가 비었습니다.</p>")
    brows = ncq_bench_table(R, benches)
    H.append(ncq_html_table(["역할", "벤치마크", "벤치 누적", "전략 누적", "초과",
                             "월평균 초과", "HAC t", "겹친 월"], brows,
                            title="벤치마크 대비",
                            note="판정 기준은 주 벤치마크(Bottom-N 동일가중)입니다. "
                                 "지수 대비 초과는 소형주 강세 구간에서 전략의 공로가 아닙니다.",
                            left_cols=(0, 1)))
    if len(R):
        curves: "OrderedDict[str, pd.Series]" = OrderedDict()
        curves["전략(NCQ)"] = ncq_cum(R)
        for k in ncq_bench_order(benches):
            try:
                b = pd.to_numeric(pd.Series(benches[k]), errors="coerce").reindex(R.index)
            except Exception:
                continue
            if int(b.notna().sum()):
                curves[_trunc(k, 20)] = ncq_cum(b)
        H.append(ncq_svg_line(curves, title="누적수익 곡선 (전략 관측월 · 비용 차감 후)", pct=True))
        yr = []
        for y in sorted(set(pd.DatetimeIndex(R.index).year)):
            m = pd.DatetimeIndex(R.index).year == y
            yr.append([str(y), f"{int(m.sum())}", ncq_pct(float((1 + R[m].fillna(0)).prod() - 1), 1)])
        H.append(ncq_html_table(["연도", "월수", "전략 수익"], yr, title="연도별 성과", left_cols=(0,)))

    # 이벤트·커버리지
    H.append("<h2>2. 이벤트 · 커버리지</h2>")
    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) else pd.Series(dtype=float)
    if len(ev_m):
        H.append(ncq_svg_line({"월별 이벤트 수": ev_m}, height=220,
                              title="월별 신규 커버리지 이벤트 수", pct=False))
    if ncq_has_rows(EV) and "event_type" in EV.columns:
        et = EV["event_type"].astype(str)
        sg = EV["sponsor_group"].astype(str) if "sponsor_group" in EV.columns else None
        rows = []
        for t in sorted(set(et.unique())):
            m = et == t
            row = [t, f"{int(m.sum()):,}", ncq_pct(float(m.mean()), 1, signed=False)]
            if sg is not None:
                for c in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"):
                    row.append(f"{int((m & (sg == c)).sum()):,}")
            rows.append(row)
        hdr = ["유형", "건수", "비중"] + (["ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY"] if sg is not None else [])
        H.append(ncq_html_table(hdr, rows, title="이벤트 유형 × 스폰서 그룹", left_cols=(0,)))
    else:
        H.append("<p class='mut'>이벤트 분포 없음 — EV 가 비었거나 event_type 이 없습니다.</p>")

    # 코호트·기여 종목
    H.append("<h2>3. 코호트 · 기여 종목</h2>")
    COH = ncq_cohort_table(BT, SIG)
    if ncq_has_rows(COH) and "ret_h" in COH.columns:
        rows = []
        for y in sorted(set(pd.DatetimeIndex(COH["entry_month"].dropna()).year)):
            m = pd.DatetimeIndex(COH["entry_month"]).year == y
            rows.append(ncq_dist_row(str(y), COH.loc[m, "ret_h"]))
        rows.append(ncq_dist_row("전체", COH["ret_h"]))
        H.append(ncq_html_table(NCQ_DIST_HEAD, rows,
                                title=f"진입 연도별 {ncq_g('NCQ_HOLD_MONTHS', 12)}개월 보유수익 분포",
                                left_cols=(0,)))
        if "sponsor_group" in COH.columns:
            srows = [ncq_dist_row(g, COH.loc[COH["sponsor_group"].astype(str) == g, "ret_h"])
                     for g in ("ORGANIC_ONLY", "MIXED", "SPONSORED_ONLY")]
            H.append(ncq_html_table(NCQ_DIST_HEAD, srows, title="스폰서 그룹별 보유수익 분포",
                                    left_cols=(0,)))
    else:
        H.append("<p class='mut'>코호트 없음 — BT['cohorts'] / BT['holdings'] 로 구성할 수 없습니다.</p>")

    Hd = BT.get("holdings") if isinstance(BT, dict) else None
    if ncq_has_rows(Hd) and {"code", "ret"}.issubset(set(Hd.columns)):
        h = Hd.copy()
        h["code"] = h["code"].astype(str)
        w = pd.to_numeric(h.get("weight"), errors="coerce") if "weight" in h.columns \
            else pd.Series(1.0, index=h.index)
        contrib = (w * pd.to_numeric(h["ret"], errors="coerce")).groupby(h["code"]).sum() \
                   .sort_values(ascending=False)
        k = min(20, len(contrib))
        top = [[f"{i}", c, names.get(c, ""), ncq_pctp(float(contrib[c]), 3)]
               for i, c in enumerate(list(contrib.index[:k]), 1)]
        bot = [[f"{i}", c, names.get(c, ""), ncq_pctp(float(contrib[c]), 3)]
               for i, c in enumerate(list(contrib.index[-k:])[::-1], 1)]
        H.append(ncq_html_table(["#", "code", "종목명", "기여도"], top,
                                title=f"상위 기여 종목 {k}", left_cols=(1, 2)))
        H.append(ncq_html_table(["#", "code", "종목명", "기여도"], bot,
                                title=f"하위 기여 종목 {len(bot)}", left_cols=(1, 2)))

    # 강건성
    H.append("<h2>4. 강건성</h2>")
    rob = ncq_rpt_ctx_get(ctx, "robust") or ncq_g("NCQ_ROBUST") or {}
    rrows = []
    try:
        for rid, d in (rob.items() if hasattr(rob, "items") else []):
            p = d.get("pass")
            rrows.append([("⭐ " if d.get("kill") else "") + str(rid), _trunc(str(d.get("name", "")), 34),
                          {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}.get(p, "—"),
                          _trunc(str(d.get("detail", "")), 160)])
    except Exception:
        rrows = []
    H.append(ncq_html_table(["ID", "검정", "판정", "상세"], rrows,
                            title="강건성 검사 (⭐ = 킬 게이트)",
                            note="실패한 검정은 그대로 표시합니다. 파라미터를 바꿔 통과시키지 않습니다.",
                            left_cols=(0, 1, 3)))

    # 해석 참조표
    H.append("<h2>5. 해석 참조표</h2>")
    info = ncq_lexicon_group_info()
    H.append(ncq_html_table(["그룹", "라벨", "방향", "가중", "어휘수", "무엇을 잡는가"],
                            [[g, d["label"], d["방향"],
                              ncq_rpt_num(d["weight"], 1) if ncq_isnum(d["weight"]) else NCQ_NA,
                              ncq_int(d["n_terms"]) if ncq_isnum(d["n_terms"]) else NCQ_NA,
                              d["뜻"]] for g, d in info.items()],
                            title="렉시콘 그룹", left_cols=(0, 1, 5)))
    H.append(ncq_html_table(["그룹", "발화했다는 것은", "발화하지 않았다는 것은"],
                            [[g, d["발화"], d["미발화"]] for g, d in info.items()],
                            title="발화 / 미발화 해석", left_cols=(0, 1, 2)))

    lex_sha = ncq_g("NCQ_LEXICON_SHA", "") or NCQ_NA
    pre_sha = ncq_g("NCQ_PREREG_SHA", "") or NCQ_NA
    H.append(ncq_html_tail(f"렉시콘 SHA <span class='mono'>{ncq_esc(lex_sha)}</span> · "
                           f"사전등록 SHA <span class='mono'>{ncq_esc(pre_sha)}</span> · "))
    atomic_write_text(path, "".join(H))
    LOG.ok(f"HTML 리포트 저장: {path}")
    return path


def write_coverage_html(outdir, ctx) -> str:
    """커버리지 완결성 전용 HTML(§6.4). 반환은 파일 경로."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, f"ncq_coverage_{_dt.datetime.now():%Y%m%d_%H%M}.html")
    REP = ncq_rpt_ctx_get(ctx, "REP")
    EV = ncq_rpt_ctx_get(ctx, "EV")
    diag = ncq_rpt_ctx_get(ctx, "diag")
    tagged, runs, derived = ncq_archive_gaps(diag)

    H: List[str] = [ncq_html_head(
        "ARC-NCQ — 리서치 커버리지 완결성 진단 (§6.4)",
        "언제부터 아카이브를 믿을 수 있는가. 이 페이지의 결론이 백테스트 유효 구간을 정한다.")]

    curves: "OrderedDict[str, pd.Series]" = OrderedDict()
    src_rows = []
    if ncq_has_rows(REP):
        dcol = ncq_pick_col(REP, ["pub_date", "event_date", "knowledge_date", "date"])
        if dcol is not None:
            R = REP.copy()
            R["_m"] = as_ts_series(R[dcol]) + pd.offsets.MonthEnd(0)
            R = R.dropna(subset=["_m"])
            tot = ncq_fill_month_gaps(R.groupby("_m", observed=True).size().astype("float64"))
            curves["전 소스 합"] = tot
            scol = ncq_pick_col(R, ["source", "src", "_src"])
            if scol is not None:
                for s in list(R[scol].astype(str).value_counts().head(5).index):
                    ss = ncq_fill_month_gaps(R[R[scol].astype(str) == s]
                                             .groupby("_m", observed=True).size().astype("float64"))
                    curves[_trunc(s, 18)] = ss
                    arr = ss.to_numpy(dtype=float)
                    src_rows.append([s, ncq_int(float(np.nansum(arr))),
                                     f"{int(np.isfinite(arr).sum())}/{len(arr)}",
                                     ncq_xlabel(ss.index[0]), ncq_xlabel(ss.index[-1])])
            if "stock_code" in R.columns:
                uq = ncq_fill_month_gaps(R.dropna(subset=["stock_code"])
                                         .groupby("_m", observed=True)["stock_code"]
                                         .nunique().astype("float64"))
                curves["유니크 커버 종목"] = uq
    if curves:
        H.append(ncq_svg_line(curves, height=320, title="월별 수집량 · 유니크 커버 종목", pct=False))
    else:
        H.append("<p class='mut'>월별 수집 시계열 없음 — REP 가 비었거나 날짜 컬럼이 없습니다.</p>")

    H.append(ncq_html_table(["소스", "총건수", "관측월", "최초월", "최종월"], src_rows,
                            title="소스별 수집량", left_cols=(0,)))

    grows = [[f"{i}", ncq_xlabel(a), ncq_xlabel(b), f"{n}"] for i, (a, b, n) in enumerate(runs, 1)]
    H.append(ncq_html_table(["#", "시작", "종료", "개월"], grows,
                            title="3개월 이상 연속 결손 구간",
                            note="이 구간의 '이벤트 없음'은 사건 부재가 아니라 관측 부재입니다. "
                                 "백테스트 유효 창에서 제외해야 합니다.", left_cols=(0,)))

    trows = []
    byyear: Dict[int, List[int]] = defaultdict(list)
    for m in tagged:
        byyear[int(pd.Timestamp(m).year)].append(int(pd.Timestamp(m).month))
    for y, ms in sorted(byyear.items()):
        trows.append([str(y), f"{len(ms)}", ", ".join(f"{x}월" for x in sorted(ms))])
    H.append(ncq_html_table(["연도", "결손 월수", "해당 월"], trows,
                            title="archive_incomplete 태깅 월", left_cols=(0, 2)))

    ev_m = ncq_fill_month_gaps(ncq_rpt_month_series(EV)) if ncq_has_rows(EV) else pd.Series(dtype=float)
    if len(ev_m):
        H.append(ncq_svg_line({"월별 이벤트 수": ev_m}, height=220,
                              title="월별 신규 커버리지 이벤트 수", pct=False))

    vs = ncq_rpt_ctx_get(ctx, "valid_start")
    H.append(ncq_html_table(["출처", "유효 시작월"],
                            [["결손 구간에서 도출", ncq_xlabel(derived) if derived is not None else NCQ_NA],
                             ["파이프라인 확정값(ctx)", ncq_xlabel(as_ts(vs)) if vs is not None else NCQ_NA]],
                            title="유효 백테스트 시작월",
                            note="여러 출처가 다르면 가장 늦은 값을 씁니다.", left_cols=(0,)))
    H.append(ncq_html_tail())
    atomic_write_text(path, "".join(H))
    LOG.ok(f"커버리지 HTML 저장: {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  9. 매니페스트 · 다운로드
# ═══════════════════════════════════════════════════════════════════════════════════════════
def ncq_phase_times() -> "OrderedDict[str, float]":
    """Phase 별 실측 소요초. PhaseBudget._spent 가 정본, 없으면 MANIFEST 기록으로 폴백."""
    out: "OrderedDict[str, float]" = OrderedDict()
    try:
        pb = ncq_g("PhaseBudget")
        sp = dict(getattr(pb, "_spent", {}) or {})
    except Exception:
        sp = {}
    if not sp:
        sp = dict((ncq_g("MANIFEST", {}) or {}).get("phase_seconds", {}) or {})
    for k in sorted(sp):
        try:
            out[str(k)] = round(float(sp[k]), 1)
        except Exception:
            continue
    return out


def write_manifest(outdir, ctx) -> str:
    """실행 매니페스트 JSON. 재현에 필요한 것만 정확히 남기고, 모르는 값은 null 로 둔다."""
    outdir = str(outdir or ".")
    path = os.path.join(outdir, "ncq_run_manifest.json")
    man: Dict[str, Any] = {}
    try:
        man = json.loads(json.dumps(ncq_g("MANIFEST", {}) or {}, ensure_ascii=False, default=str))
    except Exception:
        man = dict(ncq_g("MANIFEST", {}) or {})

    f = ncq_headline_facts(ctx)
    man["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    man["elapsed_seconds_total"] = round(float(time.time() - ncq_g("_T0_PROCESS", time.time())), 1)
    man["degradation_applied"] = f["열화단계"]
    try:
        man["degradation_reasons"] = dict(ncq_g("_DEGRADED", {}) or {})
    except Exception:
        man["degradation_reasons"] = {}
    man["valid_window"] = {
        "start": (str(f["유효시작월"].date()) if f["유효시작월"] is not None else None),
        "end": (str(f["유효종료월"].date()) if f["유효종료월"] is not None else None),
        "months": (int(f["유효개월수"]) if ncq_isnum(f["유효개월수"]) else None),
        "years": (round(float(f["유효연수"]), 3) if ncq_isnum(f["유효연수"]) else None),
    }
    man["phase_seconds"] = dict(ncq_phase_times())
    man["phase_budget_seconds"] = dict(ncq_g("NCQ_PHASE_BUDGET_S", {}) or {})
    man["lexicon_sha"] = ncq_g("NCQ_LEXICON_SHA", "") or None
    man["prereg_sha"] = ncq_g("NCQ_PREREG_SHA", "") or None
    man["lexicon_version"] = (ncq_g("NCQ_LEXICON", {}) or {}).get("version")
    man["headline"] = {
        "total_events": (int(f["총이벤트수"]) if ncq_isnum(f["총이벤트수"]) else None),
        "events_per_month": (round(float(f["월평균이벤트"]), 3) if ncq_isnum(f["월평균이벤트"]) else None),
        "irs_share_reports": (round(float(f["IRS리포트비중"]), 4) if ncq_isnum(f["IRS리포트비중"]) else None),
        "irs_share_events": (round(float(f["IRS이벤트비중"]), 4) if ncq_isnum(f["IRS이벤트비중"]) else None),
        "ticker_map_fail_rate": (round(float(f["티커매핑실패율"]), 4) if ncq_isnum(f["티커매핑실패율"]) else None),
        "pdf_extract_fail_rate": (round(float(f["PDF추출실패율"]), 4) if ncq_isnum(f["PDF추출실패율"]) else None),
        "archive_incomplete_months": (int(f["결손태깅월수"]) if ncq_isnum(f["결손태깅월수"]) else None),
        "archive_gap_runs": [[str(pd.Timestamp(a).date()), str(pd.Timestamp(b).date()), int(n)]
                             for a, b, n in (f["결손구간"] or [])],
    }

    # 소스별 수집 건수 — ctx 우선, 없으면 REP 에서 직접 집계
    counts = ncq_rpt_ctx_get(ctx, "source_counts")
    if not isinstance(counts, dict) or not counts:
        counts = {}
        REP = ncq_rpt_ctx_get(ctx, "REP")
        scol = ncq_pick_col(REP, ["source", "src", "_src"])
        if ncq_has_rows(REP) and scol is not None:
            counts = {str(k): int(v) for k, v in REP[scol].astype(str).value_counts().items()}
    man["source_counts"] = counts
    try:
        man["source_status"] = {k: {"ok": bool(v.get("ok")), "n": int(v.get("n", -1)),
                                    "note": str(v.get("note", ""))[:200]}
                                for k, v in (ncq_g("NCQ_SOURCE_STATUS", {}) or {}).items()}
    except Exception:
        man["source_status"] = {}

    # 캐시 히트율 — 계측값이 있을 때만 기록한다(추정치를 진짜처럼 남기지 않는다)
    cs = ncq_rpt_ctx_get(ctx, "cache_stats")
    if isinstance(cs, dict) and cs:
        hit = float(cs.get("hit", np.nan))
        miss = float(cs.get("miss", np.nan))
        man["cache"] = {"hit": cs.get("hit"), "miss": cs.get("miss"),
                        "hit_rate": (round(hit / (hit + miss), 4)
                                     if ncq_isnum(hit) and ncq_isnum(miss) and (hit + miss) > 0 else None)}
    else:
        man["cache"] = {"hit": None, "miss": None, "hit_rate": None,
                        "note": "캐시 히트/미스 계측값이 ctx['cache_stats'] 로 전달되지 않았습니다."}
    try:
        man["http_stats"] = {str(k): int(v) for k, v in (ncq_g("HTTP_STATS", {}) or {}).items()}
    except Exception:
        man["http_stats"] = {}

    # 강건성 요약 (판정만 — 상세는 콘솔/HTML)
    rob = ncq_rpt_ctx_get(ctx, "robust") or ncq_g("NCQ_ROBUST") or {}
    try:
        man["robust"] = {str(k): {"pass": v.get("pass"), "kill": bool(v.get("kill")),
                                  "name": str(v.get("name", ""))}
                         for k, v in (rob.items() if hasattr(rob, "items") else [])}
    except Exception:
        man["robust"] = {}
    man["outputs"] = [str(p) for p in (ncq_rpt_ctx_get(ctx, "outputs") or [])]

    atomic_write_text(path, json.dumps(man, ensure_ascii=False, indent=2, default=str))
    LOG.ok(f"매니페스트 저장: {path}")
    return path


def offer_download(paths) -> None:
    """산출물 다운로드 안내. Colab → google.colab.files, 그 외 → base64 data-URI 링크.

    둘 다 안 되면 경로만 출력한다(헤드리스 실행에서 여기서 죽으면 안 된다).
    40MB 초과 파일은 브라우저 메모리를 터뜨리므로 링크 대신 경로를 안내한다.
    """
    try:
        paths = [str(p) for p in (paths or []) if p and os.path.exists(str(p))]
    except Exception:
        paths = []
    if not paths:
        LOG.info("다운로드할 산출물이 없습니다(경로가 비었거나 파일이 생성되지 않았습니다).")
        return

    rows = []
    for p in paths:
        try:
            sz = os.path.getsize(p)
        except Exception:
            sz = -1
        rows.append([_trunc(os.path.basename(p), 40),
                     f"{sz/1e6:,.2f}MB" if sz >= 0 else NCQ_NA, _trunc(p, 52)])
    LOG.table(rows, ["파일", "크기", "경로"], ["l", "r", "l"], maxw=54, title="산출물")

    env = ncq_g("ENV", {}) or {}
    if env.get("colab"):
        try:
            from google.colab import files as _f                     # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception as e:                                       # noqa
            LOG.warn(f"Colab 다운로드 실패({type(e).__name__}) — 링크 방식으로 전환합니다.")
    try:
        from IPython.display import display, HTML                    # type: ignore
        import base64
        big: List[str] = []
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                big.append(p)
                html.append(f"<div>· {ncq_esc(os.path.basename(p))} — 용량이 커서 링크 대신 경로로 "
                            f"안내합니다: <code>{ncq_esc(p)}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(
                f"<a download='{ncq_esc(os.path.basename(p))}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {ncq_esc(os.path.basename(p))} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
        if big:
            LOG.warn(f"40MB 초과로 링크를 만들지 않은 파일 {len(big)}건 — 위 경로에서 직접 가져가세요.")
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


# ============================================================================================
# 조립 블록 20: ncq_80_verify.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-V  자가검정 계층 — 계약검정 N1~N11 · 카나리 C1~C7 · 실경로 리허설 · 합성 스모크        ║
# ║                                                                                          ║
# ║  입력 : 없음(합성데이터·픽스처). 카나리(B)만 네트워크가 필요하다.                           ║
# ║  출력 : LOG.table 판정표. run_canaries 는 결과 dict, 나머지는 bool.                        ║
# ║  실패 : strict=True 면 RuntimeError(계약검정은 KillCriteria). strict=False 면 False 반환.  ║
# ║                                                                                          ║
# ║  ── 네 검정은 서로 '다른 것'을 본다. 하나가 다른 하나를 대신하지 못한다 ────────────────    ║
# ║   (A) run_contract_tests  협상 불가 규칙(PIT·생존자편향·무기억성·동결·회계)을 테스트로 강제 ║
# ║   (B) run_canaries        외부 소스가 '지금 이 순간' 살아 있는가 (유일하게 네트워크 필요)   ║
# ║   (C) run_rehearsal       네트워크만 가짜, 수집·정제 '함수'는 실물 실행 (파싱·스키마 사고)  ║
# ║   (D) run_selftest        합성데이터로 유니버스→이벤트→텍스트→신호→백테스트 전 경로 관통   ║
# ║                                                                                          ║
# ║  왜 (C)가 따로 필요한가: (D)의 합성 스모크는 완성된 패널을 곧바로 주입하므로                ║
# ║  build_security_master · fetch_prices · naver_collect 같은 수집·정제 함수가 단 한 줄도      ║
# ║  실행되지 않는다. 실제로 그 공백 때문에 스모크를 전부 통과한 빌드가 실수집 2분 만에         ║
# ║  중복 컬럼 한 줄로 죽은 적이 있다. (C)는 그 구멍만을 겨냥한다.                              ║
# ║                                                                                          ║
# ║  ★★ 절대 원칙 ★★  이 계층은 사용자의 드라이브 캐시에 단 한 바이트도 쓰지 않는다.           ║
# ║   합성·픽스처 결과가 공용 인덱스에 섞이면 그 자체가 캐시 오염이고, 다른 전략까지 오염된다.  ║
# ║   그래서 (A)(C)(D)는 tempfile 로 만든 임시 Vault 로 전역 VAULT 를 교체하고,                 ║
# ║   finally 에서 반드시 원복 + 임시 디렉터리 삭제한다.                                       ║
# ║                                                                                          ║
# ║  ★ 스파인 모듈(ncq_40/50/70)이 아직 조립되지 않았을 수 있으므로 모든 호출은                 ║
# ║   `"fn" in globals()` 로 가드하고, 없으면 그 항목을 SKIP 으로 기록한다(하드 실패 금지).     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 공통 유틸 ───────────────────────────────────────────────────────────────────────────────
NCQ_VERIFY_SKIPPED: List[str] = []          # 스파인 미탑재로 건너뛴 항목 (최종 요약에 노출)


def ncq_has(*names: str) -> bool:
    """호출 대상 함수/클래스가 조립되어 있는가. 없으면 검정을 SKIP 으로 낮춘다."""
    G = globals()
    return all(n in G and G[n] is not None for n in names)


def ncq_v_num(v: Any, kind: str = "num", nd: int = 3) -> str:
    """수치 포맷. **결측은 반드시 '—'** — NaN 을 0으로 치환하면 없는 근거를 있다고 주장하는 것이다."""
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except Exception:
        return str(v)
    if not np.isfinite(f):
        return "—"
    if kind == "pct":
        return f"{f*100:+.2f}%"
    if kind == "pctp":
        return f"{f*100:+.3f}%p"
    if kind == "int":
        return f"{int(round(f)):,}"
    return f"{f:,.{nd}f}"


def ncq_tail_tb(n: int = 10) -> List[str]:
    """마지막 트레이스백 n줄. 실패 원인을 스크롤 없이 보이게 하는 최소 장치."""
    try:
        return [ln for ln in traceback.format_exc().rstrip().split("\n")[-n:]]
    except Exception:
        return []


def ncq_call_event_texts(EV, REP, extra=None):
    """collect_event_texts 호출 어댑터.

    ★ 계약 §4 의 시그니처는 (EV, REP) 뿐이다. 구현이 합성 본문 주입용 선택 인자
      (extra_text)를 추가로 받을 수도 있는데, 그 인자를 무조건 넘기면 계약대로 만든
      구현에서 TypeError 로 죽는다. 반대로 아예 안 넘기면 네트워크 없는 환경에서
      본문이 비어 doc_score 가 전부 0이 되고, 그 0 은 '스코어러 고장'과 '텍스트 없음'을
      구분하지 못한다. 그래서 **시그니처를 보고** 받을 수 있을 때만 넘긴다.
    """
    fn = globals().get("collect_event_texts")
    if fn is None:
        return None
    if extra is not None:
        try:
            import inspect as _isp                       # 지역 import (최상위 import 금지)
            if "extra_text" in _isp.signature(fn).parameters:
                return fn(EV, REP, extra_text=extra)
        except Exception:
            pass
    return fn(EV, REP)


@contextmanager
def ncq_tmp_vault(prefix: str = "ncq_verify_"):
    """임시 Vault 로 전역을 교체한다(캐시 무해성).

    ★ 이게 없으면 계약검정·리허설·스모크가 만든 합성 테이블이 사용자의 공용 인덱스에
      그대로 들어간다. 다른 전략이 그 테이블을 '진짜 데이터'로 재사용하면 조용한 오염이다.
    """
    G = globals()
    saved = G.get("VAULT")
    tmp = tempfile.mkdtemp(prefix=prefix)
    try:
        G["VAULT"] = Vault(tmp, "VERIFY")
        yield tmp
    finally:
        G["VAULT"] = saved
        shutil.rmtree(tmp, ignore_errors=True)


def ncq_lexicon_words() -> Tuple[List[str], List[str]]:
    """합성 텍스트에 섞을 어휘. 동결 렉시콘이 있으면 그 어휘를 그대로 쓴다.

    ★ 렉시콘 어휘를 쓰지 않으면 score_texts 가 전부 0점을 내고, 그러면 횡단면 z 가
      전 종목 동일값이 되어 스모크가 '통과'해도 아무것도 증명하지 못한다.
    """
    pos: List[str] = []
    neg: List[str] = []
    lex = globals().get("NCQ_LEXICON")
    if isinstance(lex, dict):
        def _walk(node, negative: bool):
            if isinstance(node, str):
                (neg if negative else pos).append(node)
            elif isinstance(node, (list, tuple, set)):
                for x in node:
                    _walk(x, negative)
            elif isinstance(node, dict):
                for k, v in node.items():
                    kk = str(k).lower()
                    _walk(v, negative or kk in ("n", "neg", "negative") or "neg" in kk)
        _walk(lex, False)
    pos = [w for w in dict.fromkeys(pos) if isinstance(w, str) and 1 < len(w) <= 20]
    neg = [w for w in dict.fromkeys(neg) if isinstance(w, str) and 1 < len(w) <= 20]
    if len(pos) < 6:
        pos = ["신규 수주", "양산 개시", "전방시장 진입", "생산능력 증설", "구조적 성장",
               "고객사 다변화", "사업구조 전환", "점유율 확대", "장기공급계약", "수직계열화",
               "신규 라인", "턴어라운드"]
    if len(neg) < 4:
        neg = ["일회성 요인", "기저효과", "단기 반등", "환율 효과", "재고 소진", "홍보성"]
    return pos, neg


# ══════════════════════════════════════════════════════════════════════════════════════════
#  0. 합성 데이터 생성기 — (A)(D) 가 공유한다. 반드시 결정적(seed 고정).
# ══════════════════════════════════════════════════════════════════════════════════════════
def ncq_make_synthetic(n_codes: int = 180, n_months: int = 72, seed: int = SEED) -> dict:
    """네트워크·키 없이 전 경로를 돌리기 위한 합성 세계.

    반환: sec / px_daily / pxm / mcap / UNI / REP / TXT / months / uni_obj / snapshots / quality

    설계 의도(중요):
      · 종목을 세 무리로 나눈다.
          bg   (전체의 1/3) — 매달 꾸준히 커버리지가 있는 종목. **이벤트가 나오면 안 된다.**
                              동시에 월별 리포트 건수를 안정시켜 아카이브 결손 오판을 막는다.
          ev   (전체의 1/2) — 중간 어느 달에 처음 커버리지가 붙는 종목. 여기서 H1 이 나온다.
          dark (나머지)     — 끝까지 커버리지가 없는 종목. 유니버스 분모 역할.
      · ev 종목은 첫 커버리지 이후 28~34개월 뒤 두 번째 에피소드를 갖는다 → 이벤트 밀도를 올린다.
        그래도 월평균 이벤트는 의도적으로 NCQ_MIN_EVENTS_PER_MONTH 근방에 머문다.
        z 표본 부족 → pooled 경로가 실제로 발화해야 그 경로가 검증되기 때문이다.
      · 텍스트는 동결 렉시콘 어휘를 quality 에 비례해 섞는다 → score_texts 가 분산을 낸다.
      · quality 는 미래수익 드리프트에도 들어간다 → 스모크에서 '신호가 있는' 상황을 만든다.
        (성과 수치는 난수다. 절대 해석 대상이 아니다 — 배관 검증용이다.)
    """
    rng = np.random.default_rng(int(seed))
    end = as_ts(BACKTEST_END) or as_ts("2026-07-31")
    months = pd.date_range(end - pd.DateOffset(months=int(n_months) - 1), end, freq="ME")
    n_codes = int(n_codes)

    # 코드 끝자리를 0 으로 고정한다. 끝자리 5/7/9 는 ncq_is_preferred 가 우선주로 보므로
    # 합성 종목의 1/3 이 이유 없이 유니버스에서 빠져 표본이 조용히 줄어든다.
    codes = [f"{(i + 1) * 10:06d}" for i in range(n_codes)]
    inds = rng.choice(["화학", "전자부품", "기계", "소프트웨어", "제약", "건설"], n_codes)
    quality = rng.normal(size=n_codes)

    n_bg = max(4, n_codes // 3)
    n_ev = max(4, n_codes // 2)
    bg_idx = list(range(0, n_bg))
    ev_idx = list(range(n_bg, min(n_codes, n_bg + n_ev)))
    dark_idx = list(range(min(n_codes, n_bg + n_ev), n_codes))

    # ── 상장/폐지 (생존자편향 경로를 실제로 태운다) ────────────────────────────────────────
    listing = [months[0] - pd.DateOffset(years=int(rng.integers(3, 12))) for _ in codes]
    delist: List[Any] = [pd.NaT] * n_codes
    if n_months > 24:
        for i in rng.choice(n_codes, size=max(1, n_codes // 14), replace=False):
            listing[int(i)] = months[int(rng.integers(4, max(5, n_months - 14)))]
        for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
            delist[int(i)] = months[int(rng.integers(max(6, n_months // 3), n_months - 2))]

    names = [f"합성{i+1:03d}" for i in range(n_codes)]
    for k in range(min(3, n_codes)):                 # 스팩 제외 경로를 태우기 위한 소수 표본
        names[dark_idx[k] if k < len(dark_idx) else k] = f"합성스팩{k+1}호"

    sec = pd.DataFrame({
        "code": codes, "name": names,
        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
        "listing_date": listing, "delisting_date": delist,
        "industry": inds,
        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)],
        "src": "synthetic"})

    # ── 일봉 ──────────────────────────────────────────────────────────────────────────────
    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1] + pd.Timedelta(days=6))
    frames = []
    for i, c in enumerate(codes):
        drift = 0.0003 + 0.0015 * quality[i]
        r = rng.normal(drift, 0.024, len(days))
        p = float(np.exp(rng.normal(8.6, 0.6))) * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.2, 0.7, len(days))
        frames.append(pd.DataFrame({
            "code": c, "date": days,
            "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * 1.012, "low": p * 0.988, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(frames, ignore_index=True)
    keep = np.ones(len(px), dtype=bool)
    dcol = px["date"].to_numpy()
    ccol = px["code"].to_numpy()
    for i, c in enumerate(codes):
        m = (ccol == c)
        keep &= ~(m & (dcol < np.datetime64(as_ts(listing[i]))))
        if pd.notna(delist[i]):
            keep &= ~(m & (dcol > np.datetime64(as_ts(delist[i]))))
    px = px[keep].reset_index(drop=True)

    panel = build_price_panel(px, months)
    px_daily, pxm = panel["daily"], panel["monthly"]

    # ── 시가총액 (PIT 근사 — 합성이므로 주식수는 상수) ─────────────────────────────────────
    shares = pd.Series(np.exp(rng.normal(15.5, 0.7, n_codes)), index=codes)
    mcap = pxm[["code", "month", "close"]].copy()
    mcap["shares"] = mcap["code"].map(shares).astype(float)
    mcap["mcap"] = pd.to_numeric(mcap["close"], errors="coerce") * mcap["shares"]
    mcap["mcap_src"] = "synthetic"
    mcap = mcap[["code", "month", "close", "mcap", "shares", "mcap_src"]]

    # ── 픽스처 UNI (실제 build_ncq_universe 결과와 비교·대체용) ────────────────────────────
    U = pxm[["code", "month", "adv20"]].merge(mcap[["code", "month", "mcap"]],
                                              on=["code", "month"], how="left")
    U["excl"] = ""
    U["mcap_rank"] = U.groupby("month", observed=True)["mcap"].rank(method="first", ascending=True)
    U["in_uni"] = U["mcap_rank"] <= float(NCQ_UNIVERSE_BOTTOM_N)
    U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= float(NCQ_MIN_ADV))
    UNI = U[["month", "code", "mcap", "adv20", "mcap_rank", "in_uni", "liq_pass", "excl"]]

    # ── 리포트 원장 ───────────────────────────────────────────────────────────────────────
    brokers = (MAJOR_BROKERS[:8] + MINOR_BROKERS[:8]) if ncq_has("MAJOR_BROKERS", "MINOR_BROKERS") \
        else ["삼성증권", "KB증권", "NH투자증권", "신영증권", "유진투자증권", "하나증권"]
    hist0 = months[0] - pd.DateOffset(months=36)          # 룩백 이력을 위해 창보다 앞서 시작
    hist_months = pd.date_range(hist0, months[-1], freq="ME")
    pos_w, neg_w = ncq_lexicon_words()
    rows: List[dict] = []

    def _one(code: str, m: pd.Timestamp, broker: str, sponsored: bool):
        d = (m - pd.Timedelta(days=int(rng.integers(0, 26)))).normalize()
        uid = sha1_str("ncqsyn", code, str(m.date()), broker, int(rng.integers(0, 10 ** 9)))
        rows.append({
            "report_uid": uid, "source": "irs" if sponsored else
            ("naver" if rng.random() < 0.7 else "hankyung"),
            "src_report_id": uid[:12], "pub_date": d, "category": "company",
            "title": f"{code} 합성 리포트", "stock_code": code,
            "stock_name": f"합성{code}", "broker_raw": broker,
            "analyst_raw": f"애널{int(rng.integers(0, 40)):02d}",
            "target_price": float(np.exp(rng.normal(9.5, 0.4))), "opinion": "BUY",
            "pdf_url": None, "detail_url": None, "views": None,
            "is_sponsored": bool(sponsored), "event_date": d, "knowledge_date": d})

    # bg: 꾸준한 커버리지 (이벤트가 나오면 안 되는 대조군 + 월별 건수 안정화)
    for i in bg_idx:
        for m in hist_months:
            if rng.random() < 0.75:
                _one(codes[i], m, str(rng.choice(brokers)), False)

    # ev: 첫 커버리지 + (선택) 두 번째 에피소드
    ev_months: Dict[str, List[pd.Timestamp]] = {}
    for i in ev_idx:
        lo = 26                                   # burn-in 이후에 놓이도록 충분히 뒤로
        hi = max(lo + 1, len(hist_months) - 16)
        k0 = int(rng.integers(lo, hi))
        eps = [k0]
        k1 = k0 + int(rng.integers(28, 35))
        if k1 < len(hist_months) - 2:
            eps.append(k1)
        ev_months[codes[i]] = [hist_months[k] for k in eps]
        for k in eps:
            m = hist_months[k]
            sponsored = bool(rng.random() < 0.18)
            for _ in range(int(rng.integers(1, 4))):
                _one(codes[i], m, str(rng.choice(brokers)), sponsored)
            for step in (2, 4, 7):                # 후속 커버리지 (신규 판정에는 영향 없음)
                if k + step < len(hist_months) and rng.random() < 0.55:
                    _one(codes[i], hist_months[k + step], str(rng.choice(brokers)), False)

    REP = pd.DataFrame(rows)
    if len(REP):
        REP["broker_id"] = [normalize_broker(b)[0] for b in REP["broker_raw"]]
        REP["broker_name"] = [normalize_broker(b)[1] for b in REP["broker_raw"]]
        REP["dedup_key"] = REP["report_uid"]
        REP = REP.sort_values("pub_date").reset_index(drop=True)

    # ── 텍스트 (렉시콘 어휘를 quality 에 비례해 섞는다) ────────────────────────────────────
    trows: List[dict] = []
    qmap = {codes[i]: float(quality[i]) for i in range(n_codes)}
    for r in REP.itertuples(index=False):
        q = qmap.get(str(r.code) if hasattr(r, "code") else str(r.stock_code), 0.0)
        npos = int(rng.poisson(1.5 + 3.5 * max(q, 0.0)))
        nneg = int(rng.poisson(1.5 + 2.0 * max(-q, 0.0)))
        toks = [str(rng.choice(pos_w)) for _ in range(npos)] + \
               [str(rng.choice(neg_w)) for _ in range(nneg)]
        rng.shuffle(toks)
        body = ("동사는 소형 부품 전문업체입니다. " +
                " ".join(f"{t} 관련 언급이 확인됩니다." for t in toks) +
                " 투자의견과 목표주가는 별도 표기합니다. " * 3)
        trows.append({"report_uid": r.report_uid, "code": r.stock_code, "pub_date": r.pub_date,
                      "sec_title": f"{r.stock_code} 합성 리포트",
                      "sec_headline": (toks[0] if toks else "커버리지 개시"),
                      "sec_body": body, "n_chars": len(body), "n_pages": 6,
                      "extract_ok": True, "extract_method": "synthetic"})
    TXT = pd.DataFrame(trows, columns=["report_uid", "code", "pub_date", "sec_title",
                                       "sec_headline", "sec_body", "n_chars", "n_pages",
                                       "extract_ok", "extract_method"])

    snapshots = pd.DataFrame(columns=["snap_date", "code", "market"])
    uni_obj = Universe(sec, snapshots, px_daily)

    return {"months": months, "codes": codes, "sec": sec, "px_daily": px_daily, "pxm": pxm,
            "mcap": mcap, "UNI": UNI, "REP": REP, "TXT": TXT, "uni_obj": uni_obj,
            "snapshots": snapshots, "quality": quality, "event_months": ev_months,
            "hist_months": hist_months}


def ncq_toy_sig(W: dict, rng, top_k: int = 8, oracle: bool = False,
                months: Optional[pd.DatetimeIndex] = None) -> pd.DataFrame:
    """계약검정용 합성 SIG (계약 §3 스키마 그대로).

    oracle=True 면 **미래수익을 그대로 신호로 심는다**(고의 누수). N11 이 이걸 쓴다.
    """
    pxm = W["pxm"]
    ms = list(months if months is not None else W["months"])
    parts = []
    for m in ms:
        g = pxm[(pxm["month"] == m)].copy()
        g = g[pd.to_numeric(g["adv20"], errors="coerce").notna()]
        if g.empty:
            continue
        if oracle:
            score = pd.to_numeric(g["fwd_ret"], errors="coerce")
        else:
            score = pd.Series(rng.normal(size=len(g)), index=g.index)
        g["event_score"] = score.astype(float)
        mu, sd = float(np.nanmean(score)), float(np.nanstd(score))
        g["z"] = (score - mu) / (sd if sd > 0 else np.nan)
        g["pooled"] = False
        g["pool_n"] = int(len(g))
        g["rank_pct"] = score.rank(pct=True)
        thr = g["event_score"].rank(ascending=False, method="first")
        g["selected"] = thr <= top_k
        g["placebo"] = False
        g["sponsor_group"] = "ORGANIC_ONLY"
        g["event_type"] = "H1"
        parts.append(g[["month", "code", "event_score", "z", "pooled", "pool_n", "rank_pct",
                        "selected", "placebo", "sponsor_group", "event_type",
                        "exec_px", "adv20", "fwd_ret"]])
    if not parts:
        return pd.DataFrame(columns=["month", "code", "event_score", "z", "pooled", "pool_n",
                                     "rank_pct", "selected", "placebo", "sponsor_group",
                                     "event_type", "exec_px", "adv20", "fwd_ret"])
    return pd.concat(parts, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (A) 계약 자동검정 N1~N11 — 주석과 관례는 무효. 테스트로만 강제한다.
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_CONTRACTS: List[dict] = []


def ncq_c(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    """검정 1건. 예외는 '실패'로 흡수한다 — 검정기가 죽어서 검정이 생략되면 안 된다.
    fn 은 (통과여부, 한글 상세) 를 돌려준다. 통과여부가 None 이면 SKIP 으로 기록한다."""
    t0 = time.time()
    tb = ""
    try:
        ok, msg = fn()
    except Exception as e:                                          # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:220]}"
        tb = "\n".join(ncq_tail_tb(10))
    NCQ_CONTRACTS.append({"id": cid, "name": name, "pass": ok, "msg": str(msg),
                          "sec": time.time() - t0, "tb": tb})
    if ok is None:
        NCQ_VERIFY_SKIPPED.append(f"{cid} {name}")
    return bool(ok) if ok is not None else True


def run_contract_tests(strict: bool = True) -> bool:
    """계약검정 N1~N11. 실데이터를 한 바이트도 받기 전에 전부 통과해야 한다."""
    LOG.banner("① 계약 자동검정 N1~N11",
               "PIT · 생존자편향 · 무기억성 · 동결 · 표본가드 · 코호트회계 · 체결앵커 · "
               "폐지처리 · 캐시무해 · 결정성 · 누수민감도")
    NCQ_CONTRACTS.clear()
    rng = np.random.default_rng(SEED)

    # ── N1. PIT 강제 ──────────────────────────────────────────────────────────────────────
    def n1():
        d = pd.DataFrame({"code": ["000010", "000010", "000020"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15",
                                                            "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 절단이 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "★knowledge_date > as_of 인 행이 새어나왔습니다 = 미래누수"
        # PIT 컬럼이 없는 테이블은 반드시 KeyError 로 거부돼야 한다(우회 경로를 두지 않는다)
        for bad, why in ((pd.DataFrame({"x": [1]}), "PIT 컬럼 전무"),
                         (pd.DataFrame({"x": [1], "event_date": [as_ts("2020-01-01")]}),
                          "knowledge_date 만 누락")):
            try:
                st.register("bad", bad)
                return False, f"★PIT 컬럼 없는 테이블({why}) 등록이 거부되지 않았습니다"
            except KeyError:
                pass
        return True, "as_of 절단 정확 · PIT 컬럼 누락 시 KeyError 로 등록 거부 확인"

    ncq_c("N1", "PIT 강제 (PITStore)", n1)

    # ── N2. 생존자편향 ────────────────────────────────────────────────────────────────────
    def n2():
        sec = pd.DataFrame({
            "code": ["000010", "000020", "000030"],
            "name": ["기존", "미래상장", "폐지"], "market": ["KOSPI"] * 3,
            "industry": ["화학"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"])})
        days = pd.bdate_range("2009-01-01", "2026-08-01")
        px = pd.DataFrame({"date": days, "code": "000010"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        a16 = u.at("2016-08-31")
        if "000020" in a16:
            return False, "★2016년 유니버스에 2025년 상장 종목이 들어 있습니다(미래 정보 유입)"
        if "000030" not in a16:
            return False, ("★2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다. "
                           "이게 정확히 생존자편향입니다 — 폐지 종목은 폐지 전까지 남아야 합니다")
        if "000030" in u.at("2020-01-31"):
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지 전 포함 · 폐지 후 제외 3분기 전부 정상"

    ncq_c("N2", "생존자편향 제거 (Universe)", n2)

    # ── N3. 신규 커버리지 판정의 무기억성 ─────────────────────────────────────────────────
    def n3():
        if not ncq_has("build_coverage_events"):
            return None, "build_coverage_events 미탑재 — SKIP"
        ms = pd.date_range("2016-01-31", "2024-12-31", freq="ME")
        t = as_ts("2022-06-30") + pd.offsets.MonthEnd(0)
        code = "000010"
        broker = "삼성증권"

        def _rep(dates: Sequence[str]) -> pd.DataFrame:
            rr = []
            for k, ds in enumerate(dates):
                d = as_ts(ds)
                uid = sha1_str("n3", code, ds, k)
                rr.append({"report_uid": uid, "source": "naver", "src_report_id": uid[:10],
                           "pub_date": d, "category": "company", "title": f"{code} 리포트",
                           "stock_code": code, "stock_name": "합성", "broker_raw": broker,
                           "broker_id": normalize_broker(broker)[0],
                           "broker_name": normalize_broker(broker)[1],
                           "analyst_raw": "애널00", "target_price": 10000.0, "opinion": "BUY",
                           "pdf_url": None, "detail_url": None, "is_sponsored": False,
                           "event_date": d, "knowledge_date": d})
            return pd.DataFrame(rr)

        U = pd.DataFrame({"month": ms, "code": code})
        U["mcap"] = 5.0e10
        U["adv20"] = 5.0e8
        U["mcap_rank"] = 1.0
        U["in_uni"] = True
        U["liq_pass"] = True
        U["excl"] = ""

        # ① t-30M 과 t 에만 리포트 → 갭 30M > L(24M) → t 는 '신규'여야 한다
        A = _rep(["2019-12-10", "2022-06-10"])
        # ② 중간(t-12M)에 한 건 더 → 갭 12M ≤ L → t 는 '신규가 아니'어야 한다
        B = _rep(["2019-12-10", "2021-06-10", "2022-06-10"])
        with ncq_tmp_vault("ncq_n3_"):
            EA = build_coverage_events(A, U, ms, as_ts("2016-01-31"), lookback_m=24, burnin_m=24)
            EB = build_coverage_events(B, U, ms, as_ts("2016-01-31"), lookback_m=24, burnin_m=24)

        def _at(E):
            if E is None or len(E) == 0:
                return None
            m = (as_ts_series(E["month"]) == t) & (E["code"].astype(str) == code)
            return E[m]

        ra, rb = _at(EA), _at(EB)
        if ra is None or len(ra) == 0:
            return False, (f"★갭 30M(>L=24M) 인데 {t:%Y-%m} 이 신규로 판정되지 않았습니다. "
                           f"룩백 창이 무기억성을 잃었거나 burn-in 이 과하게 잘라냈습니다")
        if str(ra["event_type"].iloc[0]) != "H1":
            return False, f"신규로는 잡혔으나 event_type 이 H1 이 아닙니다: {ra['event_type'].iloc[0]}"
        if rb is not None and len(rb) > 0:
            return False, (f"★t-12M 에 리포트가 있는데도 {t:%Y-%m} 이 신규로 판정됐습니다. "
                           f"L=24M 룩백이 실제로 적용되지 않고 있습니다 — 가짜 신규가 대량 발생합니다")
        return True, ("갭 30M → 신규(H1), 갭 12M → 비신규. 판정이 룩백 창 안의 사실에만 "
                      "의존함(무기억성) 확인")

    ncq_c("N3", "신규 커버리지 무기억성 (L=24M)", n3)

    # ── N4. 렉시콘·사전등록 동결 ──────────────────────────────────────────────────────────
    def n4():
        if not ncq_has("NCQ_LEXICON", "NCQ_LEXICON_SHA"):
            return None, "NCQ_LEXICON / NCQ_LEXICON_SHA 미탑재 (ncq_40_text) — SKIP"
        lex, sha = globals()["NCQ_LEXICON"], str(globals()["NCQ_LEXICON_SHA"])
        if not sha or len(sha) < 8:
            return False, f"NCQ_LEXICON_SHA 가 비었거나 너무 짧습니다: {sha!r}"

        # ① 결정성: freeze_configs 가 있으면 그 경로로 두 번 계산해 동일한지 본다
        if ncq_has("freeze_configs"):
            d1, d2 = tempfile.mkdtemp(prefix="ncq_n4a_"), tempfile.mkdtemp(prefix="ncq_n4b_")
            try:
                l1, s1, p1, ps1 = freeze_configs(d1)
                l2, s2, p2, ps2 = freeze_configs(d2)
            finally:
                shutil.rmtree(d1, ignore_errors=True)
                shutil.rmtree(d2, ignore_errors=True)
            if s1 != s2 or ps1 != ps2:
                return False, (f"★freeze_configs 가 호출마다 다른 SHA 를 냅니다 "
                               f"(lexicon {s1[:10]} vs {s2[:10]}). 동결이 성립하지 않습니다")
            if s1 != sha:
                return False, (f"★NCQ_LEXICON_SHA({sha[:12]}) 와 freeze_configs 재계산값"
                               f"({s1[:12]})이 다릅니다. 매니페스트의 SHA 가 실제 렉시콘을 "
                               f"가리키지 않습니다")
            ok_prereg = (not ncq_has("NCQ_PREREG_SHA")) or ps1 == str(globals()["NCQ_PREREG_SHA"])
            if not ok_prereg:
                return False, "NCQ_PREREG_SHA 가 freeze_configs 재계산값과 다릅니다"
            return True, (f"freeze_configs 2회 재계산 동일 · 전역 SHA 일치 "
                          f"(lex {s1[:10]} · prereg {ps1[:10]})")

        # ② freeze_configs 가 없으면 표준 정규화 후보들로 대조한다
        blob = json.dumps(lex, ensure_ascii=False, sort_keys=True, default=str)
        cands = {
            "json.sort_keys": hashlib.sha1(blob.encode("utf-8")).hexdigest(),
            "json.sort_keys.indent2": hashlib.sha1(
                json.dumps(lex, ensure_ascii=False, sort_keys=True, indent=2,
                           default=str).encode("utf-8")).hexdigest(),
            "sha1_str": sha1_str(blob),
            "sha256.sort_keys": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        }
        hit = [k for k, v in cands.items() if v[:len(sha)] == sha]
        if not hit:
            return False, ("★NCQ_LEXICON_SHA 가 어떤 표준 정규화로도 렉시콘 내용과 일치하지 "
                           "않습니다. 동결 SHA 가 내용을 증명하지 못하면 사후수정을 막을 수 없습니다")
        # 내용을 한 글자 바꾸면 SHA 가 변해야 한다(민감도)
        mut = json.loads(json.dumps(lex, ensure_ascii=False, default=str))
        mut["__ncq_probe__"] = "x"
        if hashlib.sha1(json.dumps(mut, ensure_ascii=False, sort_keys=True,
                                   default=str).encode("utf-8")).hexdigest()[:len(sha)] == sha:
            return False, "★렉시콘을 변경했는데도 SHA 가 그대로입니다(해시가 내용을 안 봅니다)"
        return True, f"내용해시 일치({hit[0]}) · 재계산 동일 · 변경 시 SHA 변동 확인"

    ncq_c("N4", "렉시콘·사전등록 동결(SHA)", n4)

    # ── N5. 횡단면 z 의 표본 가드 ─────────────────────────────────────────────────────────
    def n5():
        if not ncq_has("build_signal_panel"):
            return None, "build_signal_panel 미탑재 (ncq_40_text) — SKIP"
        W = ncq_make_synthetic(n_codes=40, n_months=30, seed=SEED)
        ms = W["months"][-8:-1]                      # fwd_ret 이 존재하는 구간만
        codes = W["codes"]
        big, small = list(ms[:-1]), [ms[-1]]
        ev_rows, sc_rows = [], []
        k = 0
        for m in list(big) + list(small):
            n_ev = 8 if m in big else 2              # 마지막 달만 표본 부족(<NCQ_ZPOOL_MIN_N)
            for j in range(n_ev):
                c = codes[(k + j) % len(codes)]
                uid = sha1_str("n5", str(m.date()), c)
                ev_rows.append({"month": m, "code": c, "event_type": "H1", "n_reports": 1,
                                "n_brokers": 1, "sources": "naver", "broker_ids": "b1",
                                "sponsor_group": "ORGANIC_ONLY", "report_uids": uid})
                sc_rows.append({"report_uid": uid, "code": c, "month": m,
                                "doc_raw": float(rng.normal()), "doc_score": float(rng.normal()),
                                "n_chars": 900, "g_A": 1.0, "g_B": 0.0, "g_C": 1.0,
                                "g_D": 0.0, "g_H": 0.0, "g_N": 0.0})
            k += 3
        EV, SCORE = pd.DataFrame(ev_rows), pd.DataFrame(sc_rows)
        with ncq_tmp_vault("ncq_n5_"):
            SIG = build_signal_panel(SCORE, EV, W["UNI"], W["pxm"], W["months"])
        if SIG is None or len(SIG) == 0:
            return False, "SIG 가 0행입니다 — 표본 가드 이전에 신호 산출 자체가 실패했습니다"
        for c in ("pooled", "pool_n"):
            if c not in SIG.columns:
                return False, f"★SIG 에 '{c}' 컬럼이 없습니다. 계약 §3 SIG 스키마 위반입니다"
        sm = SIG[as_ts_series(SIG["month"]) == small[0]]
        bg = SIG[as_ts_series(SIG["month"]).isin(list(big))]
        if len(sm) == 0:
            return False, f"표본 부족 달({small[0]:%Y-%m}) 의 신호가 통째로 사라졌습니다"
        if not bool(sm["pooled"].astype(bool).all()):
            return False, (f"★이벤트 {len(sm)}건(< {NCQ_ZPOOL_MIN_N}) 인 달인데 pooled=False 입니다. "
                           f"표본 2건으로 계산한 z 는 의미가 없습니다")
        pn = pd.to_numeric(sm["pool_n"], errors="coerce")
        if pn.isna().all() or float(pn.max()) <= len(sm):
            return False, (f"pool_n 이 기록되지 않았거나(결측) 풀이 확장되지 않았습니다 "
                           f"(pool_n={ncq_v_num(pn.max())}, 당월 {len(sm)}건)")
        if len(bg) and bool(bg["pooled"].astype(bool).all()):
            return False, "이벤트 8건인 달까지 pooled 로 넘어갔습니다 — 가드가 과하게 발동합니다"
        return True, (f"이벤트 {len(sm)}건 달 → pooled=True · pool_n={ncq_v_num(pn.max(),'int')} 기록, "
                      f"8건 달은 당월 z 유지 확인")

    ncq_c("N5", "횡단면 z 표본 가드 (pooled/pool_n)", n5)

    # ── N6. 오버랩 코호트 회계 ────────────────────────────────────────────────────────────
    def n6():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        H = int(NCQ_HOLD_MONTHS)
        W = ncq_make_synthetic(n_codes=40, n_months=H * 3, seed=SEED)
        SIG = ncq_toy_sig(W, np.random.default_rng(SEED + 1), top_k=6)
        with ncq_tmp_vault("ncq_n6_"):
            BT = run_overlap_backtest(SIG, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=H, label="N6")
        Hd = BT.get("holdings") if isinstance(BT, dict) else None
        if Hd is None or len(Hd) == 0:
            return False, "holdings 가 비었습니다 — 코호트 회계를 검증할 수 없습니다"
        if "cohort" not in Hd.columns or "weight" not in Hd.columns:
            return False, "holdings 에 cohort/weight 컬럼이 없습니다 (계약 §3 BT 스키마 위반)"
        g = Hd.groupby("month", observed=True)
        nc = g["cohort"].nunique()
        ws = g["weight"].sum()
        bad_c = nc[nc > H]
        bad_w = ws[ws > 1.0 + 1e-6]
        if len(bad_c):
            return False, (f"★활성 코호트가 H={H} 를 초과한 달 {len(bad_c)}개 "
                           f"(최대 {int(bad_c.max())}개). 오버랩 회계가 코호트를 청산하지 "
                           f"않고 있습니다 = 레버리지 자동 발생")
        if len(bad_w):
            return False, (f"★가중치 합이 1을 넘는 달 {len(bad_w)}개 (최대 {float(bad_w.max()):.4f}). "
                           f"1/H 배분이 깨졌습니다 — 성과가 그만큼 부풀려집니다")
        return True, (f"전 {int(nc.size)}개월에서 활성 코호트 ≤ {H} (최대 {int(nc.max())}) · "
                      f"가중치 합 ≤ 1 (최대 {float(ws.max()):.4f})")

    ncq_c("N6", "오버랩 코호트 회계 (≤H · Σw≤1)", n6)

    # ── N7. 체결 앵커 ─────────────────────────────────────────────────────────────────────
    def n7():
        days = pd.bdate_range("2022-01-03", "2023-06-30")
        r = np.random.default_rng(SEED + 7)
        parts = []
        for c in ("000010", "000020"):
            p = 10000 * np.exp(np.cumsum(r.normal(0.0003, 0.02, len(days))))
            parts.append(pd.DataFrame({
                "code": c, "date": days, "open": p * (1 + r.normal(0, 0.006, len(days))),
                "high": p * 1.01, "low": p * 0.99, "close": p,
                "volume": 100000.0, "amount": p * 100000.0, "src": "synthetic"}))
        px = pd.concat(parts, ignore_index=True)
        ms = pd.date_range("2022-02-28", "2023-05-31", freq="ME")
        panel = build_price_panel(px, ms)
        M, D = panel["monthly"], panel["daily"]
        if M.empty:
            return False, "월간 패널이 비었습니다"
        nn = M[M["next_date"].notna()]
        if len(nn) == 0:
            return False, "next_date 가 한 행도 채워지지 않았습니다 — 체결 앵커가 없습니다"
        if not bool((nn["next_date"] > nn["signal_date"]).all()):
            k = int((nn["next_date"] <= nn["signal_date"]).sum())
            return False, (f"★next_date <= signal_date 인 행 {k}건. 신호 산출일 당일(또는 이전) "
                           f"가격으로 체결하고 있습니다 = 명백한 미래누수")
        # exec_px 가 정말 '익영업일 시가'에서 오는지 원본 일봉과 대조한다
        key = D[["code", "date", "open"]].rename(columns={"date": "next_date",
                                                          "open": "open_next"})
        chk = nn.merge(key, on=["code", "next_date"], how="left")
        same = np.isclose(pd.to_numeric(chk["exec_px"], errors="coerce"),
                          pd.to_numeric(chk["open_next"], errors="coerce"),
                          rtol=1e-9, atol=1e-9, equal_nan=False)
        frac = float(np.mean(same)) if len(chk) else 0.0
        if frac < 0.95:
            return False, (f"★exec_px 가 익영업일 시가와 일치하는 비율이 {100*frac:.1f}% 뿐입니다. "
                           f"종가 체결로 폴백한 행이 과다합니다(당일 종가 체결은 누수)")
        eq_close = float(np.mean(np.isclose(pd.to_numeric(chk["exec_px"], errors="coerce"),
                                            pd.to_numeric(chk["close"], errors="coerce"))))
        if eq_close > 0.5:
            return False, f"★exec_px 의 {100*eq_close:.0f}% 가 당월 종가와 같습니다 — 당일 종가 체결"
        return True, (f"월말 신호 → 익영업일 시가 체결 확인 (next_date>signal_date 100% · "
                      f"exec_px=익일시가 {100*frac:.1f}%)")

    ncq_c("N7", "체결 앵커 (월말 신호 → 익영업일 시가)", n7)

    # ── N8. 상장폐지 처리 ─────────────────────────────────────────────────────────────────
    def n8():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        hair = float(globals().get("NCQ_DELIST_HAIRCUT", -0.50))
        W = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED + 8)
        pxm, ms = W["pxm"].copy(), W["months"]

        # ★ 시드 운에 맡기지 않고 폐지를 '직접 만든다'. 폐지 종목이 없어 SKIP 되면
        #   이 계약은 사실상 검정되지 않은 채로 통과 표시가 남는다 — 그게 가장 나쁘다.
        alive = pxm.groupby("code", observed=True)["month"].nunique()
        alive = alive[alive >= len(ms) - 1]
        if len(alive) == 0:
            return False, "합성 세계에 전 구간 거래된 종목이 없습니다(가격 생성 확인 필요)"
        code = str(sorted(alive.index.astype(str))[0])
        di = len(ms) // 2
        dm = as_ts(ms[di])
        sec = W["sec"].copy()
        sec.loc[sec["code"].astype(str) == code, "delisting_date"] = dm
        # 폐지 이후엔 가격 자체가 없다 — 엔진이 '가격이 없어서 조용히 사라지는' 길을 못 타게 한다
        pxm = pxm[~((pxm["code"].astype(str) == code) & (as_ts_series(pxm["month"]) > dm))]
        px_daily = W["px_daily"]
        px_daily = px_daily[~((px_daily["code"].astype(str) == code) &
                              (as_ts_series(px_daily["date"]) > dm))]
        uni_obj = Universe(sec, W["snapshots"], px_daily)

        enter = as_ts(ms[max(0, di - 3)])
        SIG = ncq_toy_sig(W, np.random.default_rng(SEED + 9), top_k=6)
        SIG["selected"] = False
        sel = (as_ts_series(SIG["month"]) == enter)
        others = SIG.index[sel & (SIG["code"].astype(str) != code)][:4]
        SIG.loc[sel & (SIG["code"].astype(str) == code), "selected"] = True
        SIG.loc[others, "selected"] = True
        if not bool(SIG.loc[sel & (SIG["code"].astype(str) == code), "selected"].any()):
            return False, f"폐지 예정 종목 {code} 이 {enter:%Y-%m} 신호 패널에 없습니다"
        with ncq_tmp_vault("ncq_n8_"):
            BT = run_overlap_backtest(SIG, pxm, sec, uni_obj, ms, hold_months=12,
                                      cost_roundtrip=0.0, label="N8")
        Hd = BT.get("holdings") if isinstance(BT, dict) else None
        if Hd is None or len(Hd) == 0:
            return False, "holdings 가 비었습니다"
        h = Hd[Hd["code"].astype(str) == code].copy()
        if len(h) == 0:
            return False, f"폐지 종목 {code} 이 한 번도 보유되지 않았습니다(선정 로직 확인)"
        h["month"] = as_ts_series(h["month"])
        h = h.sort_values("month")
        at = h[h["month"] == dm]
        if len(at) == 0:
            return False, (f"★폐지월 {dm:%Y-%m} 에 해당 종목의 보유 기록이 없습니다. "
                           f"폐지 손실을 계상하지 않고 조용히 사라지면 성과가 부풀려집니다")
        got = float(pd.to_numeric(at["ret"], errors="coerce").iloc[0])
        if not np.isfinite(got) or abs(got - hair) > 1e-6:
            return False, (f"★폐지월 수익이 {ncq_v_num(got,'pct')} 입니다. 명세 §10 은 "
                           f"{ncq_v_num(hair,'pct')}(폐지 직전가 -50% 후 현금화)를 요구합니다")
        after = h[h["month"] > dm]
        if len(after) and float(np.nanmax(np.abs(pd.to_numeric(after["ret"],
                                                               errors="coerce")))) > 1e-9:
            return False, ("폐지 이후에도 해당 종목이 0 이 아닌 수익을 내고 있습니다 — "
                           "현금화되지 않았습니다")
        return True, (f"{code} 폐지월 {dm:%Y-%m} 수익 {ncq_v_num(got,'pct')} = 명세값 · "
                      f"이후 {len(after)}개월 현금(0%) 확인")

    ncq_c("N8", "상장폐지 처리 (-50% 후 현금화)", n8)

    # ── N9. 캐시 무해성 ───────────────────────────────────────────────────────────────────
    def n9():
        banned = re.compile(r"^(delete|del|remove|rm|drop|purge|clear|wipe|unlink|truncate|"
                            r"erase|reset|prune)", re.I)
        pub = [n for n in dir(Vault) if not n.startswith("_") and banned.match(n)]
        if pub:
            return False, (f"★Vault 에 삭제 계열 공개 메서드가 있습니다: {pub}. "
                           f"절대 1원칙은 '약속'이 아니라 '구조'로 지켜야 합니다 — "
                           f"삭제 API 는 존재 자체가 위험입니다")
        tmp = tempfile.mkdtemp(prefix="ncq_n9_")
        try:
            v = Vault(tmp, "VERIFY")
            d1 = pd.DataFrame({"a": [1, 2, 3]})
            d2 = pd.DataFrame({"a": [9, 9, 9, 9]})
            p1 = v.put_table("ncq_probe", d1, scope="shared")
            if not p1 or not os.path.exists(p1):
                return False, "put_table 이 파일을 만들지 못했습니다"
            p2 = v.put_table("ncq_probe", d2, scope="shared")
            bdir = os.path.join(v.ns["shared"], "index", "_backup")
            baks = [f for f in os.listdir(bdir)] if os.path.isdir(bdir) else []
            hit = [f for f in baks if f.startswith("ncq_probe.")]
            if not hit:
                return False, ("★기존 테이블을 백업 없이 교체했습니다. 실행 중 중단되면 "
                               "사용자의 기존 캐시가 그대로 소실됩니다")
            back = read_parquet_safe(os.path.join(bdir, hit[0]))
            if back is None or len(back) != len(d1):
                return False, f"백업 파일이 이전 내용을 담고 있지 않습니다({hit[0]})"
            cur = read_parquet_safe(p2 or p1)
            if cur is None or len(cur) != len(d2):
                return False, "교체 후 현재 파일이 새 내용이 아닙니다"
            return True, (f"삭제 계열 공개 API 없음 · put_table 재기록 시 백업 생성 확인"
                          f"({hit[0]} · {len(back)}행 보존)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    ncq_c("N9", "캐시 무해성 (삭제 API 부재 · 백업 후 교체)", n9)

    # ── N10. 결정성 (C8) ──────────────────────────────────────────────────────────────────
    def n10():
        A = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED)
        B = ncq_make_synthetic(n_codes=24, n_months=24, seed=SEED)
        for key in ("px_daily", "pxm", "REP"):
            a, b = A[key], B[key]
            if a.shape != b.shape:
                return False, f"★같은 시드인데 {key} 의 shape 가 다릅니다: {a.shape} vs {b.shape}"
            ha = sha1_str(key, pd.util.hash_pandas_object(a.reset_index(drop=True),
                                                          index=False).sum())
            hb = sha1_str(key, pd.util.hash_pandas_object(b.reset_index(drop=True),
                                                          index=False).sum())
            if ha != hb:
                return False, f"★같은 시드인데 {key} 내용 해시가 다릅니다 — 결정성 붕괴"
        detail = "합성 데이터 3종(px_daily·pxm·REP) 해시 동일"
        if ncq_has("run_overlap_backtest"):
            S1 = ncq_toy_sig(A, np.random.default_rng(SEED + 3), top_k=5)
            S2 = ncq_toy_sig(B, np.random.default_rng(SEED + 3), top_k=5)
            with ncq_tmp_vault("ncq_n10_"):
                B1 = run_overlap_backtest(S1, A["pxm"], A["sec"], A["uni_obj"], A["months"],
                                          hold_months=6, label="N10a")
                B2 = run_overlap_backtest(S2, B["pxm"], B["sec"], B["uni_obj"], B["months"],
                                          hold_months=6, label="N10b")
            r1 = pd.to_numeric(B1["returns"]["ret"], errors="coerce").to_numpy()
            r2 = pd.to_numeric(B2["returns"]["ret"], errors="coerce").to_numpy()
            if r1.shape != r2.shape or not np.allclose(np.nan_to_num(r1, nan=-9.0),
                                                       np.nan_to_num(r2, nan=-9.0),
                                                       rtol=0, atol=0):
                return False, "★같은 시드로 두 번 돌린 백테스트 월수익이 다릅니다 — 결정성 붕괴"
            detail += f" · 백테스트 월수익 {len(r1)}개월 완전 일치"
        else:
            NCQ_VERIFY_SKIPPED.append("N10 백테스트 결정성(run_overlap_backtest 미탑재)")
            detail += " · 백테스트 부분은 SKIP(run_overlap_backtest 미탑재)"
        return True, detail

    ncq_c("N10", "결정성 (동일 SEED → 동일 결과)", n10)

    # ── N11. 미래누수 하네스 민감도 ───────────────────────────────────────────────────────
    def n11():
        if not ncq_has("run_overlap_backtest"):
            return None, "run_overlap_backtest 미탑재 (ncq_50_backtest) — SKIP"
        W = ncq_make_synthetic(n_codes=60, n_months=36, seed=SEED + 11)
        base = ncq_toy_sig(W, np.random.default_rng(SEED + 12), top_k=8, oracle=False)
        ora = ncq_toy_sig(W, np.random.default_rng(SEED + 12), top_k=8, oracle=True)
        with ncq_tmp_vault("ncq_n11_"):
            Bb = run_overlap_backtest(base, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=1, cost_roundtrip=0.0, adv_cap=False,
                                      label="N11_base")
            Bo = run_overlap_backtest(ora, W["pxm"], W["sec"], W["uni_obj"], W["months"],
                                      hold_months=1, cost_roundtrip=0.0, adv_cap=False,
                                      label="N11_oracle")

        def _cum(BT):
            s = pd.to_numeric(BT["returns"]["ret"], errors="coerce").fillna(0.0)
            return float((1.0 + s).prod() - 1.0), float(s.mean())

        cb, mb = _cum(Bb)
        co, mo = _cum(Bo)
        if not np.isfinite(co) or not np.isfinite(cb):
            return False, "누적수익이 계산되지 않았습니다(수익률 시계열 확인 필요)"
        n_pos = int(pd.to_numeric(Bo["returns"].get("n", pd.Series(dtype=float)),
                                  errors="coerce").fillna(0).sum())
        if n_pos <= 0:
            return False, ("오라클 백테스트에서 포지션이 한 건도 잡히지 않았습니다. "
                           "'하네스 둔감'이 아니라 '게이트가 전부 막았다'는 뜻이므로 "
                           "선정 게이트를 먼저 확인해야 합니다")
        if mo <= mb + 0.002:
            return False, (f"★미래수익을 그대로 신호로 심었는데도 성과가 개선되지 않습니다 "
                           f"(월평균 오라클 {ncq_v_num(mo,'pctp')} vs 기준 {ncq_v_num(mb,'pctp')}). "
                           f"백테스트 엔진이 신호에 반응하지 못하는 상태이므로 "
                           f"이 빌드의 모든 성과 수치는 무효입니다 — 체결·정렬·수익계산을 보세요")
        return True, (f"고의 누수 주입 시 월평균 {ncq_v_num(mb,'pctp')} → {ncq_v_num(mo,'pctp')} "
                      f"(누적 {ncq_v_num(cb,'pct')} → {ncq_v_num(co,'pct')}). 하네스가 누수에 반응함")

    ncq_c("N11", "미래누수 하네스 민감도", n11)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = []
    for r in NCQ_CONTRACTS:
        icon = "✔ 통과" if r["pass"] is True else ("→ SKIP" if r["pass"] is None else "✘ 실패")
        rows.append([r["id"], _trunc(r["name"], 34), icon, f"{r['sec']:.2f}s",
                     _trunc(r["msg"], 78)])
    LOG.table(rows, ["계약", "내용", "판정", "소요", "상세"], ["l", "l", "c", "r", "l"], maxw=82,
              title="계약 자동검정 N1~N11 (협상 대상이 아님 — 우회하지 말고 원인을 고치십시오)")

    failed = [r for r in NCQ_CONTRACTS if r["pass"] is False]
    skipped = [r for r in NCQ_CONTRACTS if r["pass"] is None]
    if skipped:
        LOG.warn(f"스파인 미탑재로 건너뛴 계약 {len(skipped)}건: " +
                 ", ".join(r["id"] for r in skipped) +
                 " — 해당 모듈이 조립되면 반드시 다시 돌려야 합니다.")
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        for r in failed[:3]:
            if r.get("tb"):
                LOG.banner(f"✘ 계약 실패: [{r['id']}] {r['name']}", _trunc(r["msg"], 96))
                for ln in str(r["tb"]).split("\n"):
                    _safe_print("   " + ln)
        if strict:
            raise KillCriteria(
                f"계약 위반 {len(failed)}건으로 파이프라인을 중단합니다. "
                f"이 규칙들은 결과의 유효성 그 자체이므로, 임계를 낮춰 통과시키지 말고 "
                f"원인을 고쳐야 합니다.")
        return False
    LOG.ok(f"계약 {len(NCQ_CONTRACTS) - len(skipped)}건 통과"
           + (f" (SKIP {len(skipped)}건)" if skipped else "") + ".")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (B) 네트워크 카나리 C1~C7 (명세 §13.3) — 유일하게 네트워크가 필요한 계층
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_CANARY: "OrderedDict[str, dict]" = OrderedDict()


def ncq_canary(cid: str, name: str, fn: Callable[[], Tuple[bool, str]],
               blocking: bool = False) -> dict:
    """카나리 1건. **예외를 절대 밖으로 내지 않는다** — 한 소스가 죽었다고 실행이 죽으면 안 된다."""
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:                                          # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
    rec = {"id": cid, "name": name, "ok": (None if ok is None else bool(ok)),
           "detail": str(detail), "sec": round(time.time() - t0, 2),
           "blocking": bool(blocking), "skipped": ok is None}
    NCQ_CANARY[cid] = rec
    return rec


def run_canaries(strict: bool = True) -> dict:
    """C1~C7. 실수집을 시작하기 전에 '외부 소스가 지금 살아 있는가'를 5분 안에 확인한다.

    ★ C3(36개월 전 아카이브)만 차단성이다. 과거 아카이브에 못 닿으면 10년 백테스트가
      성립하지 않으므로 즉시 멈추고 사용자에게 보고한다. 단 드라이브 캐시에 그 구간
      리포트가 이미 충분하면 '캐시로 대체 가능'으로 통과시킨다(캐시 우선 원칙).
    """
    LOG.banner("③ 네트워크 카나리 C1~C7 (명세 §13.3)",
               "외부 소스 가용성 사전 점검 — 여기서 막는 것이 몇 시간 뒤 P1 에서 죽는 것보다 싸다")
    NCQ_CANARY.clear()

    if RUN_MODE == "SMOKE":
        for cid, nm in (("C1", "IR협의회 최근 인덱스"), ("C2", "네이버 리서치 최근 인덱스"),
                        ("C3", "네이버 리서치 36개월 전 인덱스"), ("C4", "한경컨센서스 접근"),
                        ("C5", "PDF 다운로드·텍스트 추출"), ("C6", "FDR 유니버스 조회"),
                        ("C7", "pykrx 가격 조회")):
            NCQ_CANARY[cid] = {"id": cid, "name": nm, "ok": None, "skipped": True,
                               "detail": "RUN_MODE='SMOKE' — 네트워크를 쓰지 않습니다",
                               "sec": 0.0, "blocking": False}
        LOG.table([[r["id"], _trunc(r["name"], 30), "→ SKIP", r["detail"]]
                   for r in NCQ_CANARY.values()],
                  ["카나리", "대상", "판정", "상세"], ["l", "l", "c", "l"], maxw=70,
                  title="카나리 — SMOKE 모드에서는 전부 건너뜁니다")
        LOG.info("실데이터가 필요하면 RUN_MODE='FULL' 로 바꾸고 다시 실행하세요.")
        out = dict(NCQ_CANARY)
        out["_summary"] = {"ok": True, "skipped": True, "blocking_failed": []}
        return out

    today = as_ts(_dt.date.today()) or as_ts(BACKTEST_END)
    m_recent_hi = today
    m_recent_lo = (today - pd.DateOffset(days=31)).normalize()
    d36 = (today - pd.DateOffset(months=36)).normalize()
    m36_lo = d36.replace(day=1)
    m36_hi = (m36_lo + pd.offsets.MonthEnd(0))
    pdf_urls: List[str] = []

    def _collect_pdf_urls(d):
        try:
            if d is not None and len(d) and "pdf_url" in d.columns:
                for u in d["pdf_url"].dropna().astype(str).tolist():
                    if u.lower().endswith(".pdf") or "downpdf" in u.lower():
                        pdf_urls.append(u)
        except Exception:
            pass

    # ── C1. IR협의회 ──────────────────────────────────────────────────────────────────────
    def c1():
        if ncq_has("ncq_irs_fetch_index"):
            d = globals()["ncq_irs_fetch_index"](m_recent_lo.strftime("%Y-%m-%d"),
                                                 m_recent_hi.strftime("%Y-%m-%d"))
        elif ncq_has("ncq_irs_collect"):
            d = ncq_irs_collect(m_recent_lo.strftime("%Y-%m-%d"),
                                m_recent_hi.strftime("%Y-%m-%d"), max_pages=1)
        else:
            return None, "IR협의회 수집 함수 미탑재 — SKIP"
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            return False, ("IR협의회 인덱스 0건. 스폰서 리포트 소스가 빠지므로 "
                           "SPONSORED/ORGANIC 분리 검정(P3)의 표본이 줄어듭니다. "
                           "주가설 H1 자체는 ORGANIC_ONLY 로 그대로 검정됩니다")
        return True, f"최근 1개월 인덱스 1페이지 {n:,}건"

    ncq_canary("C1", "IR협의회 최근 인덱스", c1)

    # ── C2. 네이버 최근 ───────────────────────────────────────────────────────────────────
    def c2():
        if not ncq_has("naver_collect"):
            return None, "naver_collect 미탑재 — SKIP"
        d = naver_collect(m_recent_lo.strftime("%Y-%m-%d"), m_recent_hi.strftime("%Y-%m-%d"),
                          cats=("company",), max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            return False, ("네이버 리서치 최근 인덱스가 0건입니다. 주 소스가 죽으면 "
                           "이 전략의 인덱스 수집이 성립하지 않습니다 — 차단(403)/구조 변경을 "
                           "먼저 확인하세요")
        nc = int(d["stock_code"].notna().sum()) if "stock_code" in d.columns else -1
        return True, f"최근 1개월 1페이지 {n:,}건 (종목코드 보유 {ncq_v_num(nc,'int')})"

    ncq_canary("C2", "네이버 리서치 최근 인덱스", c2)

    # ── C3. ★네이버 36개월 전 (차단성) ───────────────────────────────────────────────────
    def _cached_reports_in(lo: pd.Timestamp, hi: pd.Timestamp) -> int:
        """드라이브 캐시에 해당 구간 리포트가 몇 건이나 이미 있는가."""
        V = globals().get("VAULT")
        if V is None:
            return -1
        names = ["research_report_master"]
        for y in {lo.year, hi.year}:
            for src in ("naver", "hankyung", "irs"):
                names.append(f"report_index_{src}_{y}")
        best = 0
        for nm in names:
            try:
                d = V.get_table(nm, scope="shared")
            except Exception:
                d = None
            if d is None or len(d) == 0 or "pub_date" not in d.columns:
                continue
            try:
                t = as_ts_series(d["pub_date"])
                best = max(best, int(((t >= lo) & (t <= hi)).sum()))
            except Exception:
                continue
        return best

    def c3():
        cached_n = _cached_reports_in(m36_lo, m36_hi)
        if RUN_MODE == "CACHED":
            return True, (f"RUN_MODE='CACHED' — 과거 아카이브 접근을 시도하지 않고 "
                          f"드라이브 캐시로 대체합니다 (해당 월 캐시 {ncq_v_num(cached_n,'int')}건)")
        if not ncq_has("naver_collect"):
            return None, "naver_collect 미탑재 — SKIP"
        d = naver_collect(m36_lo.strftime("%Y-%m-%d"), m36_hi.strftime("%Y-%m-%d"),
                          cats=("company",), max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n > 0:
            return True, f"{m36_lo:%Y-%m} 인덱스 1페이지 {n:,}건 — 과거 아카이브 접근 가능"
        if cached_n >= 30:
            LOG.warn(f"★C3: 네이버 {m36_lo:%Y-%m} 아카이브에 직접 닿지 못했지만, 드라이브 캐시에 "
                     f"해당 월 리포트가 {cached_n:,}건 있어 '캐시로 대체 가능'으로 통과시킵니다. "
                     f"캐시 우선 원칙에 따른 판정이며, 캐시가 없는 구간은 완결성 진단에서 "
                     f"결손으로 잡혀 백테스트 시작월이 뒤로 밀립니다.")
            return True, (f"직접 접근 실패 · 드라이브 캐시 {cached_n:,}건으로 대체 가능 "
                          f"(캐시 우선 원칙)")
        return False, (f"★{m36_lo:%Y-%m} 인덱스에 접근하지 못했고(0건) 드라이브 캐시에도 "
                       f"{ncq_v_num(cached_n,'int')}건뿐입니다. 네이버 리서치의 과거 "
                       f"페이지네이션 깊이 제한이 가장 흔한 원인입니다. 이 상태로는 10년 "
                       f"백테스트가 성립하지 않습니다")

    ncq_canary("C3", "네이버 리서치 36개월 전 인덱스", c3, blocking=True)

    # ── C4. 한경컨센서스 (실패 예상 — 조용히 degrade) ─────────────────────────────────────
    def c4():
        if "hankyung" not in list(RESEARCH_SOURCES):
            return None, "RESEARCH_SOURCES 에 hankyung 이 없습니다 — SKIP"
        if not ncq_has("hankyung_collect"):
            return None, "hankyung_collect 미탑재 — SKIP"
        d = hankyung_collect(m_recent_lo.strftime("%Y-%m-%d"), m_recent_hi.strftime("%Y-%m-%d"),
                             max_pages=1)
        n = 0 if d is None else len(d)
        _collect_pdf_urls(d)
        if n <= 0:
            if ncq_has("degrade"):
                try:
                    degrade("L1", "카나리 C4 실패 — 한경컨센서스 접근 불가")
                except Exception:                                    # noqa
                    pass
            return False, ("접근 불가 → 열화 L1(한경 소스 드롭) 적용. 명세 §2.1 상 한경 없이도 "
                           "전략은 성립합니다(애널리스트 원장 품질만 낮아집니다)")
        return True, f"최근 1개월 1페이지 {n:,}건 (작성자·적정가격 직접 제공 소스)"

    ncq_canary("C4", "한경컨센서스 접근", c4)

    # ── C5. PDF 1건 다운로드 + 텍스트 추출 ────────────────────────────────────────────────
    def c5():
        if not ncq_has("pdf_text"):
            return None, "pdf_text 미탑재 — SKIP"
        if not pdf_urls:
            return None, "C1~C4 에서 PDF 링크를 하나도 얻지 못해 시험할 대상이 없습니다 — SKIP"
        last_err = ""
        for u in pdf_urls[:5]:
            try:
                raw = http_get(u, source="naver" if "pstatic" in u else "generic",
                               as_bytes=True, tries=2, timeout=40,
                               referer="https://finance.naver.com/research/")
            except Exception as e:                                   # noqa
                last_err = f"{type(e).__name__}"
                continue
            if not raw or len(raw) < 2000:
                last_err = f"본문 {0 if not raw else len(raw)}바이트"
                continue
            txt = pdf_text(raw, max_pages=3) or ""
            if len(txt) > 500:
                return True, (f"{len(raw)/1024:.0f}KB PDF → 텍스트 {len(txt):,}자 추출 성공 "
                              f"({os.path.basename(u.split('?')[0])[:40]})")
            last_err = f"텍스트 {len(txt)}자 (스캔 이미지형 PDF 가능성)"
        return False, (f"PDF 텍스트 추출 실패 — {last_err}. pdfplumber/PyPDF2 설치 여부와 "
                       f"이미지형 PDF 비중을 확인하세요. 실패해도 인덱스 메타데이터만으로 "
                       f"이벤트 판정은 되지만, 텍스트 스코어(2차 압축)가 불가능해집니다")

    ncq_canary("C5", "PDF 다운로드·텍스트 추출", c5)

    # ── C6. FDR 유니버스 ──────────────────────────────────────────────────────────────────
    def c6():
        if not ncq_has("fetch_fdr_listing"):
            return None, "fetch_fdr_listing 미탑재 — SKIP"
        d = fetch_fdr_listing()
        n = 0 if d is None else len(d)
        if n <= 2000:
            return False, (f"상장 종목이 {n:,}건뿐입니다(기대 >2,000). KRX 전체 상장사는 "
                           f"2,600여 종목이므로, 이 상태면 유니버스 자체가 잘려 있습니다 — "
                           f"raw.githubusercontent.com 접근을 확인하세요")
        return True, f"현재 상장 {n:,}종목 (KRX 무관 정적 CSV 경로)"

    ncq_canary("C6", "FDR 유니버스 조회", c6)

    # ── C7. pykrx (실패해도 경고만) ───────────────────────────────────────────────────────
    def c7():
        if globals().get("pykrx_stock") is None:
            return None, "pykrx 비활성(NCQ_USE_KRX=False 또는 미설치) — 정상. KRX-free 경로로 진행"
        if not ncq_has("KRXG"):
            return None, "KRXG 게이트 미탑재 — SKIP"
        ok = bool(KRXG.warmup())
        if not ok:
            return False, ("KRX 세션을 확보하지 못했습니다(차단 또는 자격증명 문제). "
                           "가격·시총은 네이버 차트 + DART PIT 주식수로 폴백하므로 "
                           "치명적이지 않습니다 — 경고로만 처리합니다")
        return True, "KRX 세션 확보 (월말 스냅샷을 '검증·보강'으로만 사용합니다)"

    ncq_canary("C7", "pykrx 가격 조회 / 차단 여부", c7)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = []
    for r in NCQ_CANARY.values():
        icon = "→ SKIP" if r["ok"] is None else ("✔ 가용" if r["ok"] else
                                                 ("✘ 차단성 실패" if r["blocking"] else "⚠ 불가"))
        rows.append([r["id"], _trunc(r["name"], 28), icon, f"{r['sec']:.1f}s",
                     _trunc(r["detail"], 76)])
    LOG.table(rows, ["카나리", "대상", "판정", "소요", "상세"], ["l", "l", "c", "r", "l"], maxw=80,
              title="네트워크 카나리 C1~C7 — 실패는 그대로 표시합니다(좋아 보이게 만들지 않습니다)")

    blocking_failed = [r["id"] for r in NCQ_CANARY.values()
                       if r["blocking"] and r["ok"] is False]
    soft_failed = [r["id"] for r in NCQ_CANARY.values()
                   if (not r["blocking"]) and r["ok"] is False]
    if soft_failed:
        LOG.warn(f"비차단 카나리 실패: {', '.join(soft_failed)} — 해당 소스를 빼고 진행합니다. "
                 f"결손은 완결성 진단과 리포트 최상단에 그대로 표시됩니다.")
    if ncq_has("manifest_put"):
        manifest_put("canaries", {k: {"ok": v["ok"], "detail": v["detail"][:200]}
                                  for k, v in NCQ_CANARY.items()})

    out = dict(NCQ_CANARY)
    out["_summary"] = {"ok": not blocking_failed, "skipped": False,
                       "blocking_failed": blocking_failed, "soft_failed": soft_failed}
    if blocking_failed:
        c3r = NCQ_CANARY.get("C3", {})
        LOG.error("★ 과거 아카이브(36개월 전)에 접근하지 못했습니다 — " + str(c3r.get("detail", "")))
        LOG.error("이 상태로 수집을 진행하면 최근 구간만 모인 뒤 '유효 윈도우 부족'으로 몇 시간을 "
                  "버리게 됩니다. 지금 중단하고 사용자 판단을 요청합니다.\n"
                  "  선택지 ① 드라이브 캐시에 과거 리포트를 확보한 뒤 RUN_MODE='CACHED' 로 재현\n"
                  "         ② IR협의회 단독 + 짧은 윈도우로 재설계(검정력 감소를 명시)\n"
                  "         ③ 네트워크/차단 상태를 해소한 뒤 재시도")
        if strict:
            raise RuntimeError(
                f"차단성 카나리 실패({', '.join(blocking_failed)}) — 과거 아카이브에 접근할 수 "
                f"없어 10년 백테스트가 성립하지 않습니다. 수집을 시작하지 않습니다.")
    else:
        LOG.ok("차단성 카나리(C3) 통과 — 과거 아카이브 경로가 확보되었습니다.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (C) 실경로 리허설 — 네트워크만 가짜, 수집·정제 함수는 실물 실행
# ══════════════════════════════════════════════════════════════════════════════════════════
NCQ_REHEARSAL: List[dict] = []


def ncq_rh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    """리허설 1건. 예외는 실패. '정상 응답인데 0행'도 (기대했다면) 실패다 — 파싱이 죽은 것이다."""
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        NCQ_REHEARSAL.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0, "note": note,
            "err": "" if ok else "정상 픽스처를 줬는데 0행입니다(파싱 실패 가능성)", "tb": ""})
        return out
    except Exception as e:                                          # noqa
        NCQ_REHEARSAL.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0, "note": note,
            "err": f"{type(e).__name__}: {str(e)[:200]}",
            "tb": "\n".join(ncq_tail_tb(10))})
        return None


class NcqFixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크.

    mode:
      "ok"          정상 응답
      "empty"       빈 응답 (소스가 살아 있지만 데이터가 없는 상황)
      "broken"      깨진 응답 (로그인 페이지·오류 HTML·바이너리 쓰레기)
      "missingcol"  기대 컬럼이 빠진 응답 (업스트림 스키마 변경)

    ★ build/75 의 _FixtureNet 과 이름을 겹치지 않게 새로 만든다(조립 시 중복 정의 금지).
    """

    def __init__(self, mode: str = "ok"):
        self.mode = str(mode)
        self.hits: Counter = Counter()

    # -- 픽스처 -----------------------------------------------------------------------
    @staticmethod
    def fdr_listing_csv(n: int = 40) -> bytes:
        head = ",Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"
        rows = [head]
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(f"{i},{code},KR7{code}003,합성{i+1:03d},"
                        f"{'KOSPI' if i % 2 else 'KOSDAQ'},,10000,0.5,1000000000,100000,"
                        f"{'STK' if i % 2 else 'KSQ'}")
        return ("﻿" + "\n".join(rows)).encode("utf-8")

    @staticmethod
    def fdr_delisting_csv(n: int = 30) -> bytes:
        head = ("Symbol,Name,Market,SecuGroup,Kind,ListingDate,DelistingDate,Reason,"
                "Industry,ListingShares,ToSymbol,ToName")
        rows = [head]
        for i in range(n):
            # 뒤 10건은 비표준 코드(ETF/ELW/스팩) — 탈락 집계가 정상 동작하는지 함께 본다
            code = f"{900000 + i:06d}" if i < 20 else f"KR{i:08d}"
            rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,2005-03-02,"
                        f"{2017 + (i % 8)}-0{1 + (i % 9)}-15,상장폐지,화학,1000000,,")
        return ("﻿" + "\n".join(rows)).encode("utf-8")

    @staticmethod
    def kind_html(n: int = 40) -> bytes:
        # KIND 는 HTML 표이고 종목코드가 '정수'로 와서 앞자리 0 이 날아간다
        head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
                "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
        body = "".join(
            f"<tr><td>합성{i+1:03d}</td><td>{(i+1)*10}</td><td>화학</td><td>부품</td>"
            f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td><td>서울</td></tr>"
            for i in range(n))
        return (head + body + "</table>").encode("euc-kr")

    @staticmethod
    def naver_list_html(n: int = 12) -> str:
        hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
               "<th>작성일</th><th>조회수</th></tr>")
        rows = []
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td style='padding-left:10'><a class='stock_item' "
                f"href='/item/main.naver?code={code}' title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
                f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>구조적 성장 전망</a></td>"
                f"<td>{'KB증권' if i % 2 else '신한투자증권'}</td>"
                f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
                f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
                f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
        nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
               "<a href='/research/company_list.naver?&amp;page=3'>맨뒤</a></td></tr></table>")
        return (f"<div id='contentarea_left'><div class='box_type_m'>"
                f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")

    @staticmethod
    def hankyung_html(n: int = 12) -> str:
        hdr = ("<tr>" + "".join(f"<th>{h}</th>" for h in
               ["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
                "기업정보", "차트", "첨부"]) + "</tr>")
        rows = []
        for i in range(n):
            idx = 500000 + i
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td>2024-0{1+(i%9)}-15</td>"
                f"<td class='text_l'><a href='/analysis/downpdf?report_idx={idx}'>"
                f"합성{i+1:03d}({code}) 신규 라인 양산</a></td>"
                f"<td class='text_r'>{(i+5)*10000:,}</td><td>Buy</td>"
                f"<td>애널{i%7:02d}</td><td>{'미래에셋증권' if i % 2 else '하나증권'}</td>"
                f"<td>-</td><td>-</td>"
                f"<td><a href='/analysis/downpdf?report_idx={idx}'>PDF</a></td></tr>")
        return (f"<div id='contents'><div class='table_style01'>"
                f"<table>{hdr}{''.join(rows)}</table></div></div>")

    @staticmethod
    def irs_html(n: int = 10) -> str:
        rows = []
        for i in range(n):
            code = f"{(i + 1) * 10:06d}"
            rows.append(
                "<tr>"
                f"<td>합성{i+1:03d}</td>"
                f"<td><a href='/board/view.html?idx={7000+i}'>"
                f"합성{i+1:03d}({code}) 기술분석보고서</a></td>"
                f"<td>2024.0{1+(i%9)}.1{i%9}</td>"
                f"<td><a href='/download/tech_{7000+i}.pdf'>PDF</a></td></tr>")
        return ("<html><body><div class='board'><table>"
                "<tr><th>기업명</th><th>제목</th><th>등록일</th><th>첨부</th></tr>"
                + "".join(rows) + "</table></div>"
                + "안내문 " * 200 + "</body></html>")

    @staticmethod
    def sise_json(url: str) -> str:
        m = re.search(r"startTime=(\d{8}).*?endTime=(\d{8})", str(url))
        s = as_ts(m.group(1)) if m else as_ts(BACKTEST_START)
        e = as_ts(m.group(2)) if m else as_ts(BACKTEST_END)
        days = pd.bdate_range(s, e)
        if len(days) > 3000:
            days = days[-3000:]
        rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
        px = 10000.0
        for i, d in enumerate(days):
            px *= 1.0002
            rows.append(f"['{d:%Y%m%d}',{px*0.995:.0f},{px*1.01:.0f},{px*0.99:.0f},"
                        f"{px:.0f},{120000 + i},5.0]")
        return "[" + ",".join(rows) + "]"

    @staticmethod
    def pdf_bytes() -> bytes:
        return b"%PDF-1.4\n% ncq synthetic fixture\n%%EOF\n"

    # -- 라우팅 -----------------------------------------------------------------------
    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u = str(url)
        p = params or {}
        self.hits[source] += 1
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return (b"\x00\x01garbage" if as_bytes else
                    "<html><body>로그인이 필요합니다</body></html>")

        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                return self.fdr_delisting_csv()
            if self.mode == "missingcol":
                return "﻿,Foo,Bar\n0,1,2\n".encode("utf-8")
            return self.fdr_listing_csv()
        if "kind.krx.co.kr" in u:
            return self.kind_html()
        if "corpCode.xml" in u:
            buf = io.BytesIO()
            xml = "<result>" + "".join(
                f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
                f"<stock_code>{(i+1)*10:06d}</stock_code><modify_date>20240101</modify_date>"
                f"</list>" for i in range(40)) + "</result>"
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("CORPCODE.xml", xml.encode("utf-8"))
            return buf.getvalue()
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                return self.pdf_bytes()
            page = int(p.get("now_page", 1) or 1)
            return self.hankyung_html() if page == 1 else "<td class='no_data'>데이터가 없습니다</td>"
        if "finance.naver.com/research" in u:
            page = int(p.get("page", 1) or 1)
            if page <= 3:
                return self.naver_list_html()
            return "<div id='contentarea_left'><table class='type_1'></table></div>"
        if "finance.naver.com/item/main" in u:
            return '<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>'
        if "stock.pstatic.net" in u:
            return self.pdf_bytes()
        if "siseJson" in u:
            return self.sise_json(u)
        if any(h in u for h in ("kirs.or.kr", "irsolution.or.kr")):
            return self.irs_html()
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        self.hits[f"json:{source}"] += 1
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "stockTotqySttus" in u:
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return {"status": "000", "message": "정상", "list": [
                {"rcept_no": f"{int(p.get('bsns_year', 2020))+1}0401000001",
                 "corp_code": p.get("corp_code", "C0000001"), "se": "합계",
                 "istc_totqy": "100,000"}]}
        if "stockSecurity/researches" in u:
            return []                      # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        return None

    def post(self, *a, **kw):
        return "" if self.mode != "broken" else "<html>오류</html>"


def run_rehearsal(strict: bool = True) -> bool:
    """수집·정제 함수를 픽스처로 전부 '실물 실행'한다. 네트워크·키 불필요, 수 초.

    ★ 이 검정만이 잡는 사고: 파싱 회귀·컬럼 중복·스키마 변경·인코딩·빈 응답 크래시.
      합성 스모크(D)는 완성 패널을 주입하므로 이 구간을 단 한 줄도 실행하지 않는다.
    """
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다 — 키 불필요")
    NCQ_REHEARSAL.clear()
    G = globals()
    keys = ("http_get", "http_json", "http_post", "fdr", "pykrx_stock", "yf",
            "RUN_MODE", "DART_API_KEY", "RESEARCH_COLLECT", "RESEARCH_SOURCES",
            "RESEARCH_DOWNLOAD_PDF", "N_WORKERS_RESEARCH", "UNIVERSE_SNAPSHOT_FREQ",
            "NCQ_USE_KRX")
    saved = {k: G.get(k) for k in keys}
    saved_vault = G.get("VAULT")
    # ★ IR협의회 엔드포인트 탐색 결과는 모듈 전역에 캐시된다. 픽스처로 탐색한 결과가 남으면
    #   이후 실수집이 가짜 URL 을 진짜로 믿는다. 반드시 원복한다.
    saved_irs = dict(globals().get("_IRS_ENDPOINT_CACHE", {})) \
        if "_IRS_ENDPOINT_CACHE" in G else None
    tmp = tempfile.mkdtemp(prefix="ncq_rehearsal_")
    months = pd.date_range(as_ts(BACKTEST_END) - pd.DateOffset(months=5),
                           as_ts(BACKTEST_END), freq="ME")

    try:
        net = NcqFixtureNet("ok")
        G["http_get"], G["http_json"], G["http_post"] = net.get, net.json, net.post
        G["fdr"] = None
        G["pykrx_stock"] = None            # KRX-free 경로가 진짜로 자립하는지 본다
        G["yf"] = None
        G["RUN_MODE"] = "FULL"
        G["DART_API_KEY"] = "REHEARSAL"
        G["RESEARCH_COLLECT"] = True
        G["RESEARCH_SOURCES"] = ["naver", "hankyung", "irs"]
        G["RESEARCH_DOWNLOAD_PDF"] = False       # 리허설에서 PDF 본문 수집은 대상이 아니다
        G["NCQ_USE_KRX"] = False
        G["UNIVERSE_SNAPSHOT_FREQ"] = "off"
        G["VAULT"] = Vault(tmp, "REHEARSAL")

        # ── ① 종목 마스터 ─────────────────────────────────────────────────────────────────
        snaps = pd.DataFrame(columns=["snap_date", "code", "market"])
        ncq_rh("fetch_fdr_listing", fetch_fdr_listing)
        ncq_rh("fetch_fdr_delisting", fetch_fdr_delisting,
               note="여기서 조용히 버려지는 종목이 그대로 생존자편향이 된다")
        ncq_rh("fetch_kind_listing", fetch_kind_listing)
        sec = ncq_rh("build_security_master", lambda: build_security_master(snaps),
                     note="중복 컬럼 → groupby.agg 폭발이 과거 실크래시 지점")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{(i+1)*10:06d}" for i in range(40)],
                                "name": [f"합성{i+1:03d}" for i in range(40)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(40)],
                                "listing_date": as_ts("2010-03-15"),
                                "delisting_date": pd.NaT, "src": "fx"})

        # ── ② 가격 · 시가총액 · 유니버스 ──────────────────────────────────────────────────
        codes = sec["code"].dropna().astype(str).tolist()[:10]
        px = ncq_rh("fetch_prices (네이버 차트 폴백)",
                    lambda: fetch_prices(codes, BACKTEST_START, BACKTEST_END),
                    note="pykrx/FDR/yfinance 없이 네이버 경로만으로 동작해야 한다")
        panel = None
        if px is not None and len(px):
            panel = ncq_rh("build_price_panel", lambda: build_price_panel(px, months))
        px_daily = panel["daily"] if isinstance(panel, dict) else pd.DataFrame(
            columns=["code", "date", "open", "high", "low", "close", "volume", "amount"])
        pxm = panel["monthly"] if isinstance(panel, dict) else pd.DataFrame(
            columns=["code", "month", "adv20", "exec_px", "fwd_ret"])

        if ncq_has("ncq_fdr_listing_full", "ncq_build_shares_history"):
            listing_now = ncq_rh("ncq_fdr_listing_full", ncq_fdr_listing_full)
            shares_hist = ncq_rh(
                "ncq_build_shares_history",
                lambda: ncq_build_shares_history(
                    sec, pd.DataFrame(columns=["corp_code", "shares", "knowledge_date",
                                               "bsns_year", "reprt_code"]),
                    listing_now if listing_now is not None else pd.DataFrame(
                        columns=["code", "shares"])),
                expect_rows=False)
        else:
            shares_hist = None
        if ncq_has("ncq_enrich_security_master"):
            sec2 = ncq_rh("ncq_enrich_security_master",
                          lambda: ncq_enrich_security_master(sec, px_daily),
                          note="상장일·폐지일을 다중소스로 채운다(근거 없어도 종목을 버리지 않음)")
            if sec2 is not None and len(sec2):
                sec = sec2

        mcap = None
        if ncq_has("build_marketcap_panel"):
            # ★ expect_rows=True 로 둔다. 픽스처는 상장주식수(Stocks)와 종가를 모두 주므로
            #   시가총액이 0행이면 그것은 '데이터가 없어서'가 아니라 **코드가 고장난 것**이다.
            #   여기를 관대하게 두면 하위 N 유니버스가 통째로 비는 사고가 조용히 통과한다.
            mcap = ncq_rh("build_marketcap_panel",
                          lambda: build_marketcap_panel(codes, months, px_daily, sec,
                                                        shares_hist),
                          note="주식수·종가가 모두 주어졌으므로 0행이면 코드 결함이다")
        uni_obj = Universe(sec, snaps, px_daily)
        UNI = None
        if ncq_has("build_ncq_universe"):
            UNI = ncq_rh("build_ncq_universe",
                         lambda: build_ncq_universe(
                             months, pxm,
                             mcap if mcap is not None else pd.DataFrame(columns=MCAP_COLS),
                             uni_obj, sec),
                         note="유니버스가 0행이면 하류 전 단계가 무의미해진다")

        # ── ③ 리서치 인덱스 ───────────────────────────────────────────────────────────────
        s0 = months[0].replace(day=1).strftime("%Y-%m-%d")
        s1 = months[-1].strftime("%Y-%m-%d")
        nv = ncq_rh("naver_collect", lambda: naver_collect(s0, s1, cats=("company",),
                                                           max_pages=3))
        hk = ncq_rh("hankyung_collect", lambda: hankyung_collect(s0, s1, max_pages=3))
        if ncq_has("ncq_irs_collect"):
            ncq_rh("ncq_irs_collect", lambda: ncq_irs_collect(s0, s1, max_pages=2),
                   expect_rows=False, note="IRS 는 못 찾으면 정상 스킵이어야 한다")
        frames = [f for f in (nv, hk) if f is not None and len(f)]
        rep = ncq_rh("build_report_master (다중소스 병합)",
                     lambda: build_report_master(frames, sec)) if frames else None
        REP = rep if (rep is not None and len(rep)) else pd.DataFrame(columns=REPORT_COLS)

        if len(REP):
            AL = ncq_rh("build_analyst_ledger", lambda: build_analyst_ledger(REP),
                        expect_rows=False)
            if AL is not None:
                A, L = AL
                ncq_rh("audit_linkage", lambda: (audit_linkage(REP, A, L) or [1]),
                       expect_rows=False)

        # collect_report_index 는 캐시·세션지속·연도샤딩·예산까지 한 번에 태우는 통합 경로다.
        # 월 3개만 준다(소스별 연속 실패 5회 → 60초 서킷 대기를 유발하지 않기 위함).
        if ncq_has("collect_report_index"):
            def _cri():
                try:
                    return collect_report_index(months[-3:], sec)
                except TypeError:
                    return collect_report_index(months[-3:])
            REP2 = ncq_rh("collect_report_index (캐시+수집+샤딩 통합)", _cri, expect_rows=False)
            if REP2 is not None and len(REP2):
                REP = REP2

        # ── ④ 완결성 · 이벤트 · 텍스트 · 신호 · 백테스트 ─────────────────────────────────
        valid_start = as_ts(BACKTEST_START)
        if ncq_has("coverage_completeness"):
            dg = ncq_rh("coverage_completeness", lambda: coverage_completeness(REP, months),
                        expect_rows=False)
            if isinstance(dg, tuple) and len(dg) == 2 and dg[1] is not None:
                valid_start = as_ts(dg[1])
        EV = None
        if ncq_has("build_coverage_events"):
            EV = ncq_rh("build_coverage_events",
                        lambda: build_coverage_events(
                            REP, UNI if UNI is not None else pd.DataFrame(columns=UNI_COLS),
                            months, valid_start), expect_rows=False,
                        note="6개월 창이라 burn-in 에 전부 걸려 0건이 정상 — 예외만 없으면 통과")
        EV = EV if EV is not None else pd.DataFrame(columns=EV_COLS)
        TXT = None
        if ncq_has("collect_event_texts"):
            TXT = ncq_rh("collect_event_texts", lambda: ncq_call_event_texts(EV, REP),
                         expect_rows=False)
        if ncq_has("score_texts"):
            SCORE = ncq_rh("score_texts",
                           lambda: score_texts(TXT if TXT is not None else pd.DataFrame(
                               columns=["report_uid", "code", "sec_body"])), expect_rows=False)
        else:
            SCORE = None
        if ncq_has("build_signal_panel"):
            SIG = ncq_rh("build_signal_panel",
                         lambda: build_signal_panel(
                             SCORE if SCORE is not None else pd.DataFrame(),
                             EV, UNI if UNI is not None else pd.DataFrame(columns=UNI_COLS),
                             pxm, months), expect_rows=False)
        else:
            SIG = None
        if ncq_has("run_overlap_backtest") and SIG is not None:
            ncq_rh("run_overlap_backtest",
                   lambda: run_overlap_backtest(SIG, pxm, sec, uni_obj, months,
                                                label="REHEARSAL"), expect_rows=False)

        # ── ⑤ 이상 응답 내성 (빈 / 깨짐 / 컬럼누락) ──────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = NcqFixtureNet(mode)
            G["http_get"], G["http_json"], G["http_post"] = bad.get, bad.json, bad.post
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"ncq_rh_{mode}_"), "REHEARSAL")
            if "_IRS_ENDPOINT_CACHE" in G:
                G["_IRS_ENDPOINT_CACHE"].update({"url": None, "probed": False})
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing)):
                ncq_rh(f"[{label}] {fname}", fn, expect_rows=False,
                       note="예외 없이 빈 결과를 돌려줘야 한다")
            ncq_rh(f"[{label}] naver_collect",
                   lambda: naver_collect(s0, s1, cats=("company",), max_pages=1),
                   expect_rows=False)
            ncq_rh(f"[{label}] hankyung_collect",
                   lambda: hankyung_collect(s0, s1, max_pages=1), expect_rows=False)
            if ncq_has("ncq_irs_collect"):
                ncq_rh(f"[{label}] ncq_irs_collect",
                       lambda: ncq_irs_collect(s0, s1, max_pages=1), expect_rows=False)
            ncq_rh(f"[{label}] build_report_master(빈 입력)",
                   lambda: build_report_master([], sec), expect_rows=False)
            if ncq_has("build_coverage_events"):
                ncq_rh(f"[{label}] build_coverage_events(빈 원장)",
                       lambda: build_coverage_events(
                           pd.DataFrame(columns=REPORT_COLS),
                           pd.DataFrame(columns=UNI_COLS), months, valid_start),
                       expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"] = saved_vault
        if saved_irs is not None and "_IRS_ENDPOINT_CACHE" in G:
            G["_IRS_ENDPOINT_CACHE"].clear()
            G["_IRS_ENDPOINT_CACHE"].update(saved_irs)
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in NCQ_REHEARSAL if r["ok"])
    LOG.table([[_trunc(r["name"], 44), "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 60)]
               for r in NCQ_REHEARSAL],
              ["실경로 함수", "판정", "결과", "소요", "비고"], ["l", "c", "r", "r", "l"], maxw=62,
              title="실경로 리허설 — 정상/빈/깨짐/컬럼누락 4종 응답에 대한 내성")
    fails = [r for r in NCQ_REHEARSAL if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(NCQ_REHEARSAL)}건 실패")
        for r in fails[:4]:
            LOG.banner(f"✘ 리허설 실패: {_trunc(r['name'], 60)}", _trunc(r["err"], 96))
            for ln in str(r.get("tb", "")).split("\n"):
                if ln.strip():
                    _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"이 검사는 '수집 함수가 진짜 데이터 모양에서 도는지'를 보는 것이라, "
                f"여기서 막는 것이 몇 시간 뒤 P1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(NCQ_REHEARSAL)}건 통과 — 수집·정제 함수가 실제 데이터 "
           f"모양과 이상 응답 모두에서 정상 동작합니다.")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (D) 합성 데이터 엔드투엔드 스모크
# ══════════════════════════════════════════════════════════════════════════════════════════
def run_selftest(full_chain: bool = False) -> bool:
    """네트워크·키 없이 유니버스→이벤트→텍스트→신호→백테스트→성과 전 경로를 실제로 돌린다.

    목적은 성과 측정이 아니라 **배관 검증**이다. 출력되는 모든 성과 수치는 합성 난수이며
    전략의 실제 성과가 아니다. 절대 해석하지 말 것.

    full_chain=True 면 강건성·해석표·리포트까지 예행연습한다(RUN_MODE='SMOKE' 의 목적).
    """
    LOG.banner("④ 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수 초)"
               + (" · full_chain: 강건성·리포트까지" if full_chain else ""))
    t0 = time.time()
    stage = {"name": "초기화"}
    missing: List[str] = []
    result: Dict[str, Any] = {}

    def _step(name: str, fn: Callable, required: Optional[Sequence[str]] = None):
        """단계 실행. 어디서 죽었는지가 스크롤 없이 보여야 한다."""
        if required and not ncq_has(*required):
            missing.extend([r for r in required if not ncq_has(r)])
            LOG.warn(f"[{name}] 건너뜀 — 미탑재: {', '.join(r for r in required if not ncq_has(r))}")
            return None
        stage["name"] = name
        LOG.info(f"▷ {name}")
        return fn()

    try:
        with ncq_tmp_vault("ncq_selftest_"):
            S = _step("합성 데이터 생성", lambda: ncq_make_synthetic())
            months, sec, pxm = S["months"], S["sec"], S["pxm"]
            px_daily, uni_obj = S["px_daily"], S["uni_obj"]
            LOG.info(f"합성 세계 — 종목 {len(sec):,} · 월 {len(months)} · "
                     f"일봉 {len(px_daily):,} · 리포트 {len(S['REP']):,} · 텍스트 {len(S['TXT']):,}")

            UNI = _step("PIT 유니버스 (build_ncq_universe)",
                        lambda: build_ncq_universe(months, pxm, S["mcap"], uni_obj, sec),
                        ["build_ncq_universe"])
            if UNI is None or len(UNI) == 0:
                UNI = S["UNI"]
                LOG.warn("build_ncq_universe 가 빈 결과를 돌려줘 픽스처 UNI 로 대체합니다.")

            dg = _step("커버리지 완결성 진단",
                       lambda: coverage_completeness(S["REP"], months), ["coverage_completeness"])
            valid_start = as_ts(dg[1]) if isinstance(dg, tuple) and len(dg) == 2 else months[0]

            EV = _step("신규 커버리지 이벤트 판정",
                       lambda: build_coverage_events(S["REP"], UNI, months, valid_start),
                       ["build_coverage_events"])
            if EV is None:
                EV = pd.DataFrame(columns=globals().get("EV_COLS", ["month", "code"]))
            if ncq_has("audit_events") and len(EV):
                _step("이벤트 감사", lambda: audit_events(EV, S["REP"]), ["audit_events"])
            if len(EV) == 0:
                LOG.error("합성 세계에서 이벤트가 0건입니다 — 신규 커버리지 판정 경로를 "
                          "증명하지 못했습니다. 위 퍼널에서 어느 게이트가 원인인지 보세요.")
                result["events"] = 0

            # 텍스트: 실 경로(PDF)가 없으므로 합성 본문을 extra_text 로 주입해 '본문이 있는
            # 상태'를 재현한다. 이렇게 해야 섹션 가중·부정어미 무효화·길이 정규화까지 전부
            # 실제 코드로 검증된다. (주입 없이 돌리면 제목만 남아 doc_score 가 전부 0이 되고,
            # 그 0 은 '스코어러가 고장났다'와 '텍스트가 없다'를 구분하지 못한다)
            TXT = _step("이벤트 본문 수집 (collect_event_texts)",
                        lambda: ncq_call_event_texts(EV, S["REP"], extra=S["TXT"]),
                        ["collect_event_texts"])
            if TXT is None or len(TXT) == 0:
                uids = set()
                if "report_uids" in getattr(EV, "columns", []):
                    for v in EV["report_uids"].dropna().astype(str):
                        uids.update([x for x in v.split("|") if x])
                T = S["TXT"]
                TXT = T[T["report_uid"].isin(uids)] if uids else T
                LOG.warn(f"PDF 원문이 없어 합성 TXT {len(TXT):,}행으로 대체합니다 "
                         f"(네트워크 없는 환경의 정상 폴백 — 스코어링 경로는 그대로 검증됩니다).")

            SCORE = _step("텍스트 스코어링 (score_texts)", lambda: score_texts(TXT),
                          ["score_texts"])
            if SCORE is not None and len(SCORE):
                sd = float(pd.to_numeric(SCORE.get("doc_score"), errors="coerce").std())
                if not np.isfinite(sd) or sd <= 1e-12:
                    LOG.error("★doc_score 의 표준편차가 0입니다 — 렉시콘이 텍스트에서 아무것도 "
                              "잡지 못했습니다. 이 상태에서는 횡단면 z 가 전부 동일값이 되어 "
                              "편입 종목이 0건이 됩니다. 스코어러(정규식 컴파일·섹션 분할)나 "
                              "본문 전달 경로를 먼저 고쳐야 합니다.")
                    result["score_variance_zero"] = True

            SIG = _step("신호 패널 (build_signal_panel)",
                        lambda: build_signal_panel(SCORE, EV, UNI, pxm, months),
                        ["build_signal_panel"])
            BT = _step("오버랩 코호트 백테스트",
                       lambda: run_overlap_backtest(SIG, pxm, sec, uni_obj, months,
                                                    label=f"{STRATEGY_ID} (합성)"),
                       ["run_overlap_backtest"])
            st = _step("성과 통계 (perf_stats)",
                       lambda: perf_stats(BT["returns"]), ["perf_stats"]) if BT else None
            if ncq_has("universe_funnel"):
                _step("3단 퍼널", lambda: universe_funnel(UNI, EV), ["universe_funnel"])

            dur = time.time() - t0
            n_ret = len(BT["returns"]) if isinstance(BT, dict) and "returns" in BT else 0
            rows = [
                ["합성 종목수", ncq_v_num(len(sec), "int")],
                ["유니버스 행수", ncq_v_num(len(UNI) if UNI is not None else None, "int")],
                ["신규 커버리지 이벤트", ncq_v_num(len(EV), "int")],
                ["이벤트 텍스트", ncq_v_num(len(TXT) if TXT is not None else None, "int")],
                ["스코어 행수", ncq_v_num(len(SCORE) if SCORE is not None else None, "int")],
                ["신호 행수 / 선정", (ncq_v_num(len(SIG) if SIG is not None else None, "int") + " / " +
                                 ncq_v_num(int(SIG["selected"].sum())
                                         if (SIG is not None and "selected" in SIG.columns)
                                         else None, "int"))],
                ["백테스트 월수", ncq_v_num(n_ret, "int")],
                ["합성 CAGR", ncq_v_num((st or {}).get("CAGR"), "pct")],
                ["합성 Sharpe", ncq_v_num((st or {}).get("Sharpe"))],
                ["소요시간", f"{dur:.2f}초"],
            ]
            LOG.table(rows, ["항목", "값"], ["l", "r"],
                      title="스모크 결과 (성과 수치는 합성 난수 — 배관 검증용이며 해석 대상이 아님)")

            ok = bool(UNI is not None and len(UNI) > 0 and len(EV) > 0 and
                      SCORE is not None and len(SCORE) > 0 and
                      SIG is not None and len(SIG) > 0 and n_ret > 0)
            if missing:
                uniq = list(dict.fromkeys(missing))
                LOG.error("아직 조립되지 않은 스파인 함수가 있어 전 경로를 증명하지 못했습니다: "
                          + ", ".join(uniq) + "\n"
                          "  → 해당 모듈(ncq_40_text / ncq_50_backtest 등)을 조립한 뒤 "
                          "반드시 스모크를 다시 돌리십시오.")
                NCQ_VERIFY_SKIPPED.extend(uniq)
                return False
            if not ok:
                LOG.error("스모크 실패 — 실데이터를 수집하기 전에 계산경로를 먼저 고쳐야 합니다. "
                          "위 표에서 어느 단계가 0행인지 보세요(그 직전 단계가 원인입니다).")
                return False
            LOG.ok(f"스모크 통과 ({dur:.2f}초) — 네트워크·키 없이 유니버스→이벤트→텍스트→신호→"
                   f"백테스트→성과 전 경로에서 출력물이 생성됩니다.")

            if not full_chain:
                return True

            # ── 최종 출력물 예행연습 ─────────────────────────────────────────────────────
            LOG.warn("아래 성과·강건성 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 "
                     "아니라 '출력물이 제대로 나오는지'를 보여주는 예행연습입니다. "
                     "절대 해석하지 마세요.")
            benches: Dict[str, pd.Series] = {}
            ew = None
            if ncq_has("bench_universe_ew"):
                try:
                    ew = bench_universe_ew(UNI, pxm, months)
                except Exception as e:                              # noqa
                    LOG.warn(f"합성 벤치마크 생성 실패({type(e).__name__}) — 폴백을 씁니다.")
            if ew is None or len(ew) == 0:
                # ★ 벤치가 없으면 P1/P3(초과수익) 이 전부 '판정불가'로 떨어져 예행연습이
                #   정작 봐야 할 경로를 하나도 안 밟는다. 유니버스 동일가중을 직접 만들어
                #   그 경로를 반드시 태우고, '폴백을 썼다'는 사실을 로그에 남긴다.
                u = UNI[UNI["liq_pass"].astype(bool)][["month", "code"]] \
                    if "liq_pass" in UNI.columns else UNI[["month", "code"]]
                b = u.merge(pxm[["month", "code", "fwd_ret"]], on=["month", "code"], how="left")
                ew = (b.groupby("month", observed=True)["fwd_ret"].mean()
                        .reindex(months))
                LOG.warn("bench_universe_ew 미탑재/빈 결과 — 유니버스 동일가중 폴백 벤치를 "
                         "직접 계산했습니다(예행연습 전용, 본선에서는 쓰이지 않습니다).")
            benches["Bottom-N 동일가중"] = ew

            def _run(sig, label="smoke", **kw):
                return run_overlap_backtest(sig, pxm, sec, uni_obj, months, label=label, **kw)

            def _build_sig(top_pct=None, min_adv=None):
                """민감도 축(ADV/tercile)이 신호를 다시 만드는 경로까지 실제로 태운다."""
                U2 = UNI
                if min_adv is not None and ncq_has("build_ncq_universe"):
                    U2 = build_ncq_universe(months, pxm, S["mcap"], uni_obj, sec,
                                            min_adv=min_adv)
                E2 = EV
                if U2 is not UNI and ncq_has("build_coverage_events"):
                    E2 = build_coverage_events(S["REP"], U2, months, valid_start)
                return build_signal_panel(SCORE, E2, U2, pxm, months, top_pct=top_pct)

            with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
                if ncq_has("report_performance"):
                    report_performance(BT, benches, label=f"{STRATEGY_NAME} (합성 예행연습)")
                if hasattr(uni_obj, "report_attrition"):
                    uni_obj.report_attrition()
                if ncq_has("report_coverage_diagnostics") and isinstance(dg, tuple):
                    report_coverage_diagnostics(dg[0], S["REP"], EV)

            keep_kill = STOP_ON_KILL_CRITERIA
            globals()["STOP_ON_KILL_CRITERIA"] = False   # 예행연습은 킬로 멈추지 않는다
            try:
                with PIPE.stage("SMOKE.ROBUST", "[합성] 사전등록·강건성", "L5",
                                budget_s=900, critical=False):
                    ctx = {"SIG": SIG, "BT": BT, "bench_ew": ew, "EV": EV, "UNI": UNI,
                           "SCORE": SCORE, "REP": S["REP"], "sec": sec, "pxm": pxm,
                           "uni_obj": uni_obj, "months": months, "valid_start": valid_start}
                    if ncq_has("run_prereg_tests"):
                        run_prereg_tests(SIG, BT, ew, pxm, sec, uni_obj, months, _run)
                    if ncq_has("run_sensitivity"):
                        # 민감도는 신호 재생성까지 도는 가장 무거운 경로다. 예행연습에서
                        # 실패해도 나머지 출력물을 잃지 않도록 여기서만 예외를 흡수한다.
                        try:
                            run_sensitivity(ctx, months, _build_sig, _run)
                        except Exception as e:                       # noqa
                            LOG.warn(f"[합성] 민감도 예행연습 실패({type(e).__name__}: {e}) — "
                                     f"S6(Holm)는 판정불가로 남습니다.")
                    if ncq_has("run_stat_suite"):
                        run_stat_suite(BT, ew, SIG, months, _run, n_trials=9)
                    if ncq_has("report_structural_risks"):
                        report_structural_risks(ctx)
                    if ncq_has("report_robustness"):
                        report_robustness()
            finally:
                globals()["STOP_ON_KILL_CRITERIA"] = keep_kill

            with PIPE.stage("SMOKE.REPORT", "[합성] 진단·해석표", "L6",
                            budget_s=180, critical=False):
                if ncq_has("report_diagnostics"):
                    report_diagnostics(SIG, EV, BT, UNI, sec, benches)
                if ncq_has("report_interpretation"):
                    report_interpretation(SIG, EV, SCORE)
                if ncq_has("report_dataflow_map"):
                    report_dataflow_map()
            LOG.ok("full_chain 예행연습 완료 — 백테스트·성과·강건성·진단·해석표가 모두 "
                   "정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 같은 출력이 실데이터로 나옵니다.")
            if ncq_has("NCQ_ROBUST"):
                try:
                    globals()["NCQ_ROBUST"].clear()   # 예행연습 결과가 실행 결과로 새지 않게
                except Exception:
                    pass
            return True

    except Exception as e:                                          # noqa
        LOG.error(f"스모크가 [{stage['name']}] 단계에서 중단됐습니다 — {type(e).__name__}: {e}")
        LOG.info("진단: " + diagnose(e, extra=f"selftest stage={stage['name']}"))
        for ln in ncq_tail_tb(10):
            _safe_print("   " + ln)
        return False


# ============================================================================================
# 조립 블록 21: ncq_90_main.py
# ============================================================================================



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — Phase 0~6 실행 순서와 산출물                                             ║
# ║                                                                                          ║
# ║  모든 단계는 PIPE.stage(...) 안에서 돈다. 실패하면 자동으로 출력되는 것:                    ║
# ║    실패 지점(스테이지ID·계층·경과) / 직전 입출력 스냅샷(행수·PIT컬럼) / 한글 진단 힌트 /    ║
# ║    트레이스백 마지막 12줄.  → "어디서 터졌고 무슨 데이터가 어디로 흘렀는가"가 한 화면에.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def ncq_outdir() -> str:
    d = os.path.join(VAULT.ns["private"], "outputs", STRATEGY_ID)
    os.makedirs(d, exist_ok=True)
    return d


def ncq_configdir() -> str:
    d = os.path.join(VAULT.ns["private"], "config")
    os.makedirs(d, exist_ok=True)
    return d


def ncq_phase0(months: pd.DatetimeIndex) -> dict:
    """Phase 0 — 종목마스터 · 가격 · PIT 상장주식수 · 시가총액 · 유니버스."""
    ctx: Dict[str, Any] = {}
    with PhaseBudget("P0", NCQ_PHASE_BUDGET_S["P0"]) as B:

        with PIPE.stage("P0.SEC", "종목 마스터 (다중소스 · 생존자편향 제거)", "L1", budget_s=900):
            snaps = fetch_pykrx_snapshots(months) if ncq_krx_enabled() else \
                pd.DataFrame(columns=["snap_date", "code", "market"])
            sec = build_security_master(snaps)
            dead = ncq_fdr_delisting_full()
            listing_now = ncq_fdr_listing_full()
            ctx.update(sec=sec, snapshots=snaps, dead=dead, listing_now=listing_now)

        with PIPE.stage("P0.PX", "가격 · 거래대금 (KRX-free 폴백 체인)", "L1", budget_s=1500):
            if ncq_krx_enabled():
                KRX.login()
            px = fetch_prices(ctx["sec"]["code"].tolist(),
                              (as_ts(BACKTEST_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                              BACKTEST_END)
            ctx["px"] = px
            ctx["panel"] = build_price_panel(px, months)
            ctx["pxm"] = ctx["panel"]["monthly"]

        with PIPE.stage("P0.SURV", "상장·폐지 구간 보강 (생존자편향 4중 방어)", "L1", budget_s=180):
            ctx["sec"] = ncq_enrich_security_master(ctx["sec"], ctx["panel"]["daily"], ctx["dead"])
            VAULT.put_table("security_master_ncq", ctx["sec"], scope="shared", domain="universe",
                            source="fdr+dart+price_intervals")
            ctx["uni_obj"] = Universe(ctx["sec"], ctx["snapshots"], ctx["panel"]["daily"])

        with PIPE.stage("P0.SHARES", "PIT 상장주식수 (DART 접수일자 기준)", "L1",
                        budget_s=1200, critical=False):
            corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist() \
                if "corp_code" in ctx["sec"].columns else []
            years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
            ds = fetch_dart_shares(corps, years) if corps else pd.DataFrame()
            ctx["shares_hist"] = ncq_build_shares_history(ctx["sec"], ds, ctx["listing_now"])

        with PIPE.stage("P0.MCAP", "PIT 시가총액", "L1", budget_s=900):
            ctx["mcap"] = build_marketcap_panel(ctx["sec"]["code"].tolist(), months,
                                                ctx["panel"]["daily"], ctx["sec"],
                                                ctx.get("shares_hist"))

        with PIPE.stage("P0.UNI", f"PIT 유니버스 (시총 하위 {NCQ_UNIVERSE_BOTTOM_N})", "L1",
                        budget_s=300):
            ctx["UNI"] = build_ncq_universe(months, ctx["pxm"], ctx["mcap"],
                                            ctx["uni_obj"], ctx["sec"])
            VAULT.put_table(f"universe_{STRATEGY_ID}", ctx["UNI"], scope="private",
                            domain="universe", source="build_ncq_universe")
        B.check()
    return ctx


def ncq_phase1(ctx: dict, months: pd.DatetimeIndex) -> dict:
    """Phase 1 — 리포트 인덱스 · 원장 · 애널리스트 연결 · 완결성 진단."""
    with PIPE.stage("P1.INDEX", "리포트 인덱스 전수 수집 (최신→과거 역순)", "L1",
                    budget_s=NCQ_PHASE_BUDGET_S["P1"] + 600):
        ctx["REP"] = collect_report_index(months, ctx["sec"])

    with PIPE.stage("P1.LEDGER", "애널리스트 원장 · 보고서↔애널리스트 연결", "L1",
                    budget_s=300, critical=False):
        A, L = build_analyst_ledger(ctx["REP"])
        ctx["analysts"], ctx["links"] = A, L
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        audit_linkage(ctx["REP"], A, L)

    with PIPE.stage("P1.DIAG", "커버리지 완결성 진단 (백테스트보다 먼저)", "L1", budget_s=120):
        diag, valid_start = coverage_completeness(ctx["REP"], months)
        ctx["diag"], ctx["valid_start"] = diag, valid_start
    return ctx


def ncq_phase2to5(ctx: dict, months_eff: pd.DatetimeIndex) -> dict:
    with PIPE.stage("P2.EVENT", "신규 커버리지 판정 (H1 de novo / H2 broker-new)", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P2"] + 300):
        ctx["EV"] = build_coverage_events(ctx["REP"], ctx["UNI"], months_eff,
                                          ctx["valid_start"], links=ctx.get("links"))
        ctx["event_audit"] = audit_events(ctx["EV"], ctx["REP"])

    with PIPE.stage("P3.TEXT", "이벤트 한정 PDF 본문 수집·섹션 추출", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P3"] + 600, critical=False):
        ctx["TXT"] = collect_event_texts(ctx["EV"], ctx["REP"])

    with PIPE.stage("P4.SCORE", "동결 렉시콘 텍스트 스코어링", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P4"] + 300):
        ctx["SCORE"] = score_texts(ctx["TXT"])

    with PIPE.stage("P5.SIGNAL", "횡단면 z → 상위 tercile 편입", "L2",
                    budget_s=NCQ_PHASE_BUDGET_S["P5"] + 120):
        ctx["SIG"] = build_signal_panel(ctx["SCORE"], ctx["EV"], ctx["UNI"],
                                        ctx["pxm"], months_eff)
    return ctx


def ncq_make_runners(ctx: dict, months_eff: pd.DatetimeIndex):
    """강건성·민감도가 쓰는 두 콜백을 만든다.

    · run_fn(SIG, ...)      → 백테스트만 다시 (보유기간·비용 축)
    · build_sig_fn(top_pct, min_adv) → 신호를 다시 (tercile·유동성 축)
      ★ 유동성 축은 유니버스의 liq_pass 만 바뀌므로 이벤트 판정을 통째로 다시 하지 않는다.
        (다시 하면 민감도 9조합에 수십 분이 든다)
    """
    UNI, SCORE, EV, pxm, sec, uni_obj = (ctx["UNI"], ctx["SCORE"], ctx["EV"], ctx["pxm"],
                                         ctx["sec"], ctx["uni_obj"])

    def run_fn(SIG, hold_months=None, cost_roundtrip=None, sel_col="selected",
               adv_cap=True, label="NCQ", months_override=None):
        return run_overlap_backtest(SIG, pxm, sec, uni_obj,
                                    months_override if months_override is not None else months_eff,
                                    hold_months=hold_months, sel_col=sel_col,
                                    cost_roundtrip=cost_roundtrip, adv_cap=adv_cap, label=label)

    def build_sig_fn(top_pct=None, min_adv=None):
        U, E = UNI, EV
        if min_adv is not None and abs(float(min_adv) - float(NCQ_MIN_ADV)) > 1e-6:
            U = UNI.copy()
            U["liq_pass"] = U["in_uni"] & (pd.to_numeric(U["adv20"], errors="coerce") >= float(min_adv))
            ok = set(zip(U.loc[U["liq_pass"], "month"].to_numpy(),
                         U.loc[U["liq_pass"], "code"].astype(str)))
            keep = [(m, c) in ok for m, c in zip(EV["month"].to_numpy(), EV["code"].astype(str))]
            E = EV[pd.Series(keep, index=EV.index)]
        return build_signal_panel(SCORE, E, U, pxm, months_eff, top_pct=top_pct)

    return run_fn, build_sig_fn


def offer_download_fallback(paths):
    """리포트 모듈의 offer_download 가 없을 때만 쓰는 최소 폴백."""
    for p in paths or []:
        if p and os.path.exists(p):
            _safe_print(f"⬇  산출물 경로: {p}")


def main() -> dict:
    t_all = time.time()
    global VAULT
    LOG.banner(f"{STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 실행모드 {RUN_MODE} · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("JupyterLab/IPython" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 (리서치 {N_WORKERS_RESEARCH} 상한) / "
                        f"CPU {N_CPU} " + ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가→폴백)")],
               ["KRX 경로", "활성" if ncq_krx_enabled() else "비활성 — KRX-free 경로로 진행"],
               ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    # ── L0 캐시 · 소스 배선 · 동결 ────────────────────────────────────────────────────────
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0", budget_s=600):
        root = resolve_gdrive_root()
        VAULT = Vault(root, MANIFEST.get("gdrive_root_mode", "AUTO"))
        globals()["VAULT"] = VAULT
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(ncq_adopt_dirs())

    with PIPE.stage("L0.SRC", "데이터 소스 배선 (KRX 차단 대응)", "L0", budget_s=60):
        ncq_configure_sources()

    with PIPE.stage("L0.FREEZE", "렉시콘·사전등록 동결 (백테스트 실행 전)", "L0", budget_s=60):
        freeze_configs(ncq_configdir())

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 N1~N11", "L0", budget_s=300):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(1800 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    # ★ 스모크는 '계산경로'를, 리허설은 '수집경로'를 증명한다. 둘은 겹치지 않는다.
    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=900):
        run_rehearsal(strict=True)

    with PIPE.stage("L0.CANARY", "네트워크 카나리 C1~C7", "L0", budget_s=600):
        ctx_canary = run_canaries(strict=True)

    months = month_range(BACKTEST_START, BACKTEST_END)
    ctx = ncq_phase0(months)
    ctx["canary"] = ctx_canary
    ctx = ncq_phase1(ctx, months)

    # ── 유효 윈도우 판정 (명세 §15-2 — 5년 미만이면 중단하고 보고) ────────────────────────
    yrs = float(MANIFEST.get("valid_backtest_years", 0.0) or 0.0)
    burn_end = (as_ts(ctx["valid_start"]) +
                pd.DateOffset(months=max(NCQ_LOOKBACK_M, NCQ_BURNIN_M))) + pd.offsets.MonthEnd(0)
    months_eff = months[months >= burn_end]
    manifest_put("months_effective", [str(months_eff[0].date()), str(months_eff[-1].date())]
                 if len(months_eff) else [])
    if yrs < NCQ_MIN_VALID_YEARS and NCQ_STOP_IF_SHORT_WINDOW:
        LOG.banner("⛔ 중단 — 유효 백테스트 윈도우 부족",
                   f"유효 {yrs:.1f}년 < 최소 {NCQ_MIN_VALID_YEARS:.0f}년 (명세 §15-2)")
        _safe_print("  아카이브 결손 구간을 그대로 쓰면 '가짜 신규 커버리지'가 대량 발생해\n"
                    "  백테스트 결과 전체가 무효가 됩니다. 다음 중 하나를 선택하세요:\n"
                    "    ① 구글드라이브에 과거 리포트를 더 확보한 뒤 재실행 (권장)\n"
                    "    ② NCQ_STOP_IF_SHORT_WINDOW=False 로 두고 '검정력 부족'을 감수하고 진행\n"
                    "    ③ IR협의회 단독 + 짧은 윈도우로 전략을 재설계\n")
        try:
            report_coverage_diagnostics(ctx["diag"], ctx["REP"], None)
            outs = [write_manifest(ncq_outdir(), ctx), write_coverage_html(ncq_outdir(), ctx)]
        except Exception:
            outs = []
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        PIPE.report_stages(); PhaseBudget.report()
        offer_download([p for p in outs if p])
        return {"stopped": "short_window", "years": yrs, "ctx": ctx}
    if len(months_eff) < 24:
        raise RuntimeError(f"유효 월수가 {len(months_eff)}개월뿐이라 백테스트가 무의미합니다. "
                           f"완결성 진단(유효 시작 {ctx['valid_start']:%Y-%m})을 먼저 확인하세요.")
    LOG.ok(f"유효 백테스트 구간 확정: {months_eff[0]:%Y-%m} ~ {months_eff[-1]:%Y-%m} "
           f"({len(months_eff)}개월) — burn-in {max(NCQ_LOOKBACK_M, NCQ_BURNIN_M)}개월 반영")

    ctx = ncq_phase2to5(ctx, months_eff)
    run_fn, build_sig_fn = ncq_make_runners(ctx, months_eff)

    # ── Phase 6 백테스트 ──────────────────────────────────────────────────────────────────
    with PhaseBudget("P6", NCQ_PHASE_BUDGET_S["P6"]) as B6:
        with PIPE.stage("P6.BT", "12개월 오버랩 코호트 백테스트", "L3", budget_s=600):
            ctx["BT"] = run_fn(ctx["SIG"], label="ARC-NCQ 전략")
            ctx["BT_placebo"] = run_fn(ctx["SIG"], sel_col="placebo", label="Placebo(z 하위)")
            ctx["BT_eventew"] = run_fn(ctx["SIG"].assign(_all=True), sel_col="_all",
                                       label="이벤트 EW(텍스트 미사용)")
            ctx["BT_nocap"] = run_fn(ctx["SIG"], adv_cap=False, label="ADV 제약 미적용")

        with PIPE.stage("P6.BENCH", "벤치마크 구성", "L3", budget_s=300, critical=False):
            bench_ew = bench_universe_ew(ctx["UNI"], ctx["pxm"], months_eff)
            benches: Dict[str, pd.Series] = {"Bottom-N EW(주)": bench_ew}
            benches.update(bench_index(months_eff))
            benches["Placebo(z 하위)"] = ctx["BT_placebo"]["returns"].set_index("month")["ret"]
            benches["이벤트 EW"] = ctx["BT_eventew"]["returns"].set_index("month")["ret"]
            ctx["bench_ew"], ctx["benches"] = bench_ew, benches

        with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=180, critical=False):
            report_performance(ctx["BT"], benches, label="ARC-NCQ")
            ctx["uni_obj"].report_attrition()
        B6.check()

    # ── 강건성 · 사전등록 검정 · 민감도 ───────────────────────────────────────────────────
    with PIPE.stage("L5.PREREG", "사전등록 가설 P1~P4 (BH-FDR)", "L5", budget_s=1200,
                    critical=False):
        # ★ 채택 기준 미충족(킬 게이트)은 '결론'이지 '사고'가 아니다. 여기서 예외로 실행을
        #   끊어버리면 진단·해석·리포트가 통째로 사라져서, 왜 미채택인지 볼 수단이 없어진다.
        #   그래서 킬 사유를 기록만 하고 리포트까지 끝낸 뒤 마지막에 다시 크게 알린다.
        #   (파라미터를 바꿔 통과시키지 않는다는 원칙은 그대로다 — 결과는 미채택으로 남는다)
        try:
            ctx["prereg"] = run_prereg_tests(ctx["SIG"], ctx["BT"], bench_ew, ctx["pxm"],
                                             ctx["sec"], ctx["uni_obj"], months_eff, run_fn)
        except KillCriteria as e:
            ctx["kill"] = str(e)
            ctx["prereg"] = globals().get("NCQ_PREREG_RESULT") or {}
            LOG.error(f"킬 기준 발동 — {e}")
            LOG.warn("킬 기준이 발동했지만 진단·리포트는 끝까지 생성합니다. "
                     "'왜 미채택인지'를 볼 수 없으면 판단 자체가 불가능하기 때문입니다.")
            manifest_note(f"KILL: {e}")
        except Exception as e:                                    # noqa
            LOG.error(f"사전등록 검정 실패({type(e).__name__}: {e}) — 이후 판정은 보류합니다.")
            ctx["prereg"] = {}

    with PIPE.stage("L5.SENS", "민감도 9조합 (81조합 전부 금지 — 명세 §15-5)", "L5",
                    budget_s=1800, critical=False):
        ctx["sens"] = run_sensitivity(ctx, months_eff, build_sig_fn, run_fn)

    with PIPE.stage("L5.STAT", "통계 검정 스위트 (부트스트랩·순열·WF·PBO·DSR·Holm)", "L5",
                    budget_s=1800, critical=False):
        n_trials = int(len(ctx["sens"])) if isinstance(ctx.get("sens"), pd.DataFrame) and \
            len(ctx["sens"]) else 9
        ctx["stats"] = run_stat_suite(ctx["BT"], bench_ew, ctx["SIG"], months_eff, run_fn,
                                      n_trials=n_trials)
        report_robustness()
        try:
            report_structural_risks(ctx)
        except Exception as e:                                    # noqa
            LOG.warn(f"구조적 리스크 표 생성 실패({type(e).__name__})")

    # ── 리포트 · 산출물 ───────────────────────────────────────────────────────────────────
    with PIPE.stage("L6.REPORT", "진단 9종 · 해석표 · 흐름지도", "L6", budget_s=300,
                    critical=False):
        report_headline(ctx)
        report_coverage_diagnostics(ctx["diag"], ctx["REP"], ctx["EV"])
        report_diagnostics(ctx["SIG"], ctx["EV"], ctx["BT"], ctx["UNI"], ctx["sec"], benches)
        report_interpretation(ctx["SIG"], ctx["EV"], ctx["SCORE"])
        report_dataflow_map()

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outdir = ncq_outdir()
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs: List[str] = []
        try:
            bt_path = os.path.join(outdir, f"backtest_results_{stamp}.parquet")
            atomic_write_parquet(ctx["BT"]["returns"], bt_path); outs.append(bt_path)
            ev_path = os.path.join(outdir, f"event_log_{stamp}.parquet")
            atomic_write_parquet(ctx["EV"], ev_path); outs.append(ev_path)
            hd_path = os.path.join(outdir, f"holdings_{stamp}.csv")
            ctx["BT"]["holdings"].to_csv(hd_path, index=False, encoding="utf-8-sig")
            outs.append(hd_path)
        except Exception as e:                                    # noqa
            LOG.warn(f"산출물 일부 저장 실패({type(e).__name__})")
        try:
            outs.append(write_coverage_html(outdir, ctx))
            outs.append(write_html_report(outdir, ctx))
            outs.append(write_manifest(outdir, ctx))
        except Exception as e:                                    # noqa
            LOG.warn(f"리포트 생성 실패({type(e).__name__}: {e})")
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer)); outs.append(lp)

        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", ctx["BT"]["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.put_table(f"cohorts_{STRATEGY_ID}", ctx["BT"]["cohorts"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        VAULT.report()
        ctx["outputs"] = [p for p in outs if p and os.path.exists(p)]

    PIPE.report_stages()
    PIPE.report_flow()
    PIT.report()
    report_http()
    ncq_report_sources()
    PhaseBudget.report()
    PIPE.report_runtime()

    if ctx.get("kill"):
        LOG.banner("⛔ 사전등록 채택 기준 미충족 — 이 전략은 '미채택'입니다",
                   "파라미터를 조정해 통과시키지 마십시오. 미채택도 결론입니다.")
        _safe_print(f"  {ctx['kill']}\n"
                    "  다음 단계는 '기준을 낮추는 것'이 아니라 ① 커버리지 완결성을 더 확보하거나\n"
                    "  ② 표본(이벤트 수)을 늘리거나 ③ 이 전략을 위성 배분 후보에서 제외하는 것입니다.")

    LOG.banner("완료", f"총 소요 {(time.time()-t_all)/60:.1f}분 · "
                       f"산출물은 구글드라이브 전용 인덱스에 저장되었습니다: {ncq_outdir()}")
    LOG.info("한계 명시 — ① 아카이브 결손이 곧 가짜 신규 커버리지다(§12 R1). 완결성 진단이 "
             "유일한 방어선이며 통과 실패 시 결과 전체가 무효입니다. "
             "② 렉시콘은 연구자 편향을 담고 있으며, 수익률 확인 후 수정하면 전 결과가 무효입니다.")
    offer_download(ctx.get("outputs", []))
    return {"ctx": ctx, "backtest": ctx.get("BT"), "signal": ctx.get("SIG"),
            "robust": NCQ_ROBUST, "prereg": ctx.get("prereg"), "sens": ctx.get("sens")}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        try:
            report_robustness()
            PhaseBudget.report()
        except Exception:
            pass
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
        try:
            ncq_report_sources(); PhaseBudget.report()
        except Exception:
            pass
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 _done.jsonl 로 정확히 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
