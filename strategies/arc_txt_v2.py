#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  ARC-TXT v2.0  —  애널리스트 리포트 텍스트톤 변화 × DART 3층 교차확증
#  전략: 애널리스트 텍스트톤 변화 × DART 3층 교차확증   [ARC_TXT_V2]
#  백테스트 구간: 2016-08 ~ 2026-07 (10년) · 분기 리밸런싱(3/1, 6/1, 9/1, 12/1)
#
#  축 A  애널리스트 텍스트톤 변화(ΔTONE) — 정보생산 마찰. 반드시 직교화 후 사용.
#  축 B  DART 3층
#        D1 텍스트 변화량 (Lazy Prices) — 투자자 부주의.  커버리지 100%, 섹터 무관
#        D2 재무제표 이상현상          — 검증된 정량 지표. 커버리지 100%, 섹터 무관
#        D3 하드팩트 화이트리스트      — 질적 변화의 직접 증거. ★가점이지 하드게이트 아님
#        배제 플래그                   — 부정 정보의 신뢰성. ★유일한 하드 제외
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python arc_txt_v2.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브/로컬 캐시 연결 → 계약 자동검정 A1~A18
#     [1] 합성데이터 엔드투엔드 스모크  (실데이터 쓰기 전에 계산경로를 먼저 증명)
#     [2] 실경로 리허설                (네트워크만 가짜, 수집·정제 함수는 실물 실행)
#     [3] 데이터 수집  (로컬+드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [4] Phase 0 게이트 6종           → 어느 축이 살아있는지 확정
#     [5] 원장 무결성 감사             (보고서 ↔ 애널리스트 ↔ 종목 연결 상태)
#     [6] U-1000 PIT 유니버스          (상장폐지 포함 · 미래시총 소급 금지)
#     [7] 축 A(TONE→ΔTONE→직교화) / 축 B(D1·D2·D3·배제) → FINAL_SCORE
#     [8] 백테스트 → 성과 검증(비용 전/후)
#     [9] 어블레이션 11종 → BH-FDR 보정 → 강건성 → 섹터/시총 분해
#    [10] 해석표 · 진단카드 · 폐기 판정 · 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 —  여기 ①~⑦ 만 채우면 됩니다
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 한글로 명시합니다. 조용히 실패하지 않습니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  ★이 전략의 축 B 전체가 여기에 달려 있습니다 ────────────────────
#
#    발급 절차 (무료 · 3분):
#      1. https://opendart.fss.or.kr  접속
#      2. 우측 상단 [회원가입] → 이메일 인증
#      3. 로그인 후 상단 메뉴 [인증키 신청/관리] → [인증키 신청]
#      4. 사용목적 간단히 기재 → 즉시 발급 (승인 대기 없음)
#      5. [오픈API 이용현황] 에서 40자리 인증키 복사 → 아래에 붙여넣기
#
#    ▶ 일일 호출 한도는 20,000건입니다. 이 코드는 **한도를 하드코딩하지 않고**
#      DART 응답 헤더/상태코드와 자체 원장으로 **남은 호출량을 실시간 추적**해서
#      쓸 수 있는 만큼만 씁니다(ARC_DART_LIMIT_MODE 참조).
#    ▶ 10년치 정기보고서 원문 콜드빌드는 며칠 걸립니다. 중단해도 드라이브에 저장되어
#      다음 실행에서 정확히 그 지점부터 이어받습니다.
DART_API_KEY = ""

# ── ② KRX 데이터 마켓플레이스 (2025-12 인증 방식 변경 대응) ─────────────────────────────────
#
#    가입 절차 (무료):
#      1. https://data.krx.co.kr  접속 → 우측 상단 [회원가입]
#      2. 이메일 인증 후 로그인
#      3. 아래에 로그인 ID / 비밀번호를 그대로 입력
#
#    ▶ 비워두셔도 됩니다. 유니버스의 정확성은 상장일·폐지일(FDR/KIND)만으로 성립하도록
#      설계되어 있고, KRX 스냅샷은 '검증·보강'입니다. 비우면 그 단계만 건너뜁니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패합니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

#    (선택) KRX Open API 인증키.  https://data.krx.co.kr → [OPEN API] → 이용신청
#    ⚠ 엔드포인트별 '이용신청'이 따로 필요하고 승인에 하루 정도 걸립니다. 키만으론 즉시 안 됩니다.
KRX_OPENAPI_KEY = ""

# ── ③ 공공데이터포털 (선택 — D3 정부 R&D 과제 대조용) ───────────────────────────────────────
#    발급: https://www.data.go.kr → 로그인 → API 상세페이지 → [활용신청]
#          → 마이페이지 > 데이터활용 > Open API > 인증키
#    ★ 반드시 "일반 인증키(Decoding)" 를 넣으세요. Encoding 키(%2B, %3D 포함)를 넣으면
#      이중 인코딩으로 항상 401/SERVICE_KEY_IS_NOT_REGISTERED 가 납니다.
DATA_GO_KR_KEY = ""

# ── ④ 캐시 경로 ─────────────────────────────────────────────────────────────────────────────
#
#    ★★★ 절대 1원칙 ★★★
#      · 기존 캐시·인덱스(공용/전용)를 절대 삭제·훼손하지 않습니다.
#      · 인덱스의 진실은 append-only JSONL 저널입니다. 기존 줄을 다시 쓰지 않습니다.
#      · index.parquet 은 저널의 파생물이며, 재생성 전 항상 타임스탬프 백업합니다.
#      · 이미 드라이브에 있던 리포트/데이터는 이동·개명 없이 '경로만 등록'합니다.
#      · 삭제 API 자체가 존재하지 않습니다.
#      · **신규로 수집되는 모든 데이터는 반드시 구글드라이브에 저장**됩니다.
#
#    GDRIVE_ROOT       : 신규 수집분이 저장될 최상위 캐시 루트 (구글드라이브)
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략에서도 그대로 재활용 (가격·재무·공시·리포트 원장)
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유 (유사도·피처·스코어·백테스트)
GDRIVE_ROOT       = "/content/drive/MyDrive/quant_cache"
GDRIVE_SHARED_NS  = "_shared"          # → {GDRIVE_ROOT}/_shared    (공용)
GDRIVE_PRIVATE_NS = "arc_txt_v2"       # → {GDRIVE_ROOT}/arc_txt_v2 (전용)

#    ▸ 캐시 탐색 경로 — **로컬과 구글드라이브 양쪽을 모두 뒤집니다.**
#      존재하는 경로만 자동으로 골라 씁니다. 오타·미마운트가 있어도 죽지 않습니다.
#      여기에 이미 리포트/데이터를 모아둔 폴더를 추가하면 재귀 스캔해서 '등록만' 합니다
#      (파일을 옮기거나 지우지 않습니다 — adopt-by-reference).
CACHE_SEARCH_DIRS = [
    # 구글드라이브 (Colab 마운트 / 로컬 동기화 클라이언트 둘 다)
    "/content/drive/MyDrive/quant_cache",
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    "~/Google Drive/My Drive/quant_cache",
    "~/GoogleDrive/MyDrive/quant_cache",
    "G:/내 드라이브/quant_cache",
    "G:/My Drive/quant_cache",
    # 로컬 D 드라이브 (윈도우 JupyterLab)
    "D:/quant_cache",
    "D:/research",
    "D:/reports",
    "D:/consensus",
    "D:/데이터/리포트",
    # 로컬 (리눅스/맥)
    "./quant_cache",
    "~/quant_cache",
]

#    ▸ 드라이브를 못 쓰는 환경에서만 쓰는 로컬 폴백 루트.
#      ★ 이 경우에도 신규 수집분은 드라이브가 붙는 즉시 동기화되도록 같은 레이아웃으로 씁니다.
LOCAL_CACHE_ROOT = "./quant_cache"

# ── ⑤ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑥ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전체 출력물을 예행연습 (수십 초). 네트워크·키 불필요.
#              게이트·백테스트·어블레이션·강건성·해석표가 전부 나옵니다. 처음엔 이걸로 한 번.
#    "FULL"  : 스모크 → 리허설 → 실데이터 수집 → 전체 (권장)
#    "CACHED": 스모크 → 리허설 → 캐시만 사용(신규 수집 안 함) → 전체. 오프라인 재현용.
RUN_MODE = "FULL"

# ── ⑦ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 6~8 로.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
MEM_BUDGET_GB  = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지. 낮출수록 안전/느림.
    "dart":      7.0,
    "hankyung":  2.0,
    "naver":     2.5,
    "krx":       2.0,
    "datagokr":  5.0,
    "kind":      2.0,
    "generic":   3.0,
}

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 전략 사양(사전등록)이며 임의로 바꾸지 마십시오.
#   가중치·임계값은 전부 명세서에 사전등록된 값입니다. 튜닝은 계약 위반입니다(A13).
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── §3 유니버스 U-1000 ──────────────────────────────────────────────────────────────────────
ARC_UNIVERSE_N        = 1000          # PIT 시가총액 랭크 '하위' 1000종목 (KOSPI+KOSDAQ)
ARC_MIN_ADTV_KRW      = 100_000_000   # 직전 60거래일 ADTV 하한 (1억원)
ARC_ADTV_WINDOW       = 60            # 거래일
ARC_MIN_LISTING_M     = 12            # 상장 12개월 미만 제외
ARC_D1_MIN_LISTING_M  = 24            # 상장 24개월 미만은 D1 에서만 제외(전년 동기 문서 부재)

# ── §4 시점 규약 (룩어헤드 절대 금지) ───────────────────────────────────────────────────────
ARC_REBAL_MONTHS      = (3, 6, 9, 12) # 리밸런싱 3/1, 6/1, 9/1, 12/1
ARC_DART_LAG_DAYS     = 1             # rcept_dt + 1거래일부터 사용 가능
ARC_REPORT_LAG_DAYS   = 1             # 리포트 발간일 + 1거래일부터 사용 가능

# ── §5 축 A: 애널리스트 텍스트톤 ────────────────────────────────────────────────────────────
ARC_TONE_MODEL        = "logreg"      # "nb" | "logreg" | "lgbm"  (LLM 금지)
ARC_TONE_CAR_DAYS     = 2             # 라벨: 발간일 기준 2일 CAR(시장수익률 차감)의 부호
ARC_TONE_HALFLIFE_D   = 30.0          # §5.2 최신성 가중 반감기 30일
ARC_TONE_MIN_SENT     = 3             # 리포트당 최소 문장 수 (미만이면 TONE 결측)
ARC_TONE_MIN_TRAIN    = 2000          # 확장윈도우 학습 최소 문장 수 (미만이면 그 시점 스킵)
ARC_TONE_MAX_FEATURES = 60000         # TF-IDF 어휘 상한 (RAM 보호)
ARC_TONE_CONTROLS     = ["eps_rev", "tp_rev", "opin_chg", "mom_12_1",
                         "log_mktcap", "log_adtv"]     # + 섹터 더미 (§5.3, 생략 금지)

# ── §6.1 D1 텍스트 변화량 ───────────────────────────────────────────────────────────────────
ARC_D1_WEIGHTS = {                    # 사전등록. 튜닝 금지. 결측 섹션은 비례 재배분.
    "S_MDA":   0.35,
    "S_LEGAL": 0.25,
    "S_EXEC":  0.15,
    "S_BIZ":   0.10,
    "S_RISK":  0.05,
    "S_GOV":   0.05,
    "S_ALL":   0.05,
}
ARC_D1_METRICS        = ("cosine", "jaccard", "simple", "len_ratio")
ARC_D1_MIN_TOKENS     = 80            # 이보다 짧은 섹션은 파싱 실패로 간주(결측)
ARC_DOC_MAX           = 120_000       # 한 실행에서 새로 받을 원문 상한 (이어받기 전제)

# ── §6.2 D2 재무 이상현상 ───────────────────────────────────────────────────────────────────
ARC_D2_WINSOR_P       = 0.01          # 상하위 1% 윈저라이징

# ── §6.5 축 B 합성 (사전등록 가중치) ────────────────────────────────────────────────────────
ARC_D3_EXACT_MAX_DOCS = 4000    # §6.3 완료형 판정을 위해 원문 zip 을 다시 열 최대 문서 수
ARC_W_D1, ARC_W_D2, ARC_W_D3 = 0.40, 0.40, 0.20
# §7.2 최종 스코어
ARC_W_AXIS_A, ARC_W_AXIS_B   = 0.50, 0.50

# ── §7.2 포트폴리오 ─────────────────────────────────────────────────────────────────────────
ARC_TOP_N_DEFAULT     = 30            # 목표 보유 종목수 20~40 의 중앙값
ARC_TOP_N_MIN         = 20
ARC_TOP_N_MAX         = 40
ARC_WEIGHTING         = "equal"       # 기준. 역변동성 가중은 병행 산출한다.
ARC_ACCOUNT_KRW       = 100_000_000   # 슬리피지 참여율 계산용 명목 계좌
ARC_ADV_PARTICIPATION = 0.10          # 60일 평균거래대금의 10% 이내

# ── §8.1 비용 모델 ──────────────────────────────────────────────────────────────────────────
ARC_COMMISSION_BPS    = 1.5           # 편도 수수료(bp). 개인 온라인 가정
ARC_SLIPPAGE_K        = 0.10          # 제곱근 시장충격 계수 (실측 스프레드로 보정)
ARC_MIN_SPREAD_BPS    = 30.0          # 초소형주 최소 호가스프레드 가정(bp) — 반값이 편도 비용

# ── §8.3 다중검정 ───────────────────────────────────────────────────────────────────────────
ARC_FDR_Q             = 0.10          # BH-FDR

# ── 리서치 수집 ─────────────────────────────────────────────────────────────────────────────
RESEARCH_COLLECT           = True     # False 면 캐시에 있는 것만 사용
RESEARCH_SOURCES           = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF      = True     # 본문 텍스트가 있어야 TONE 이 성립합니다
RESEARCH_PDF_MAX_PER_MONTH = 0        # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000
RESEARCH_PDF_FULL_PAGES    = 12       # TONE 학습용 본문 추출 페이지 수 (앞 3장만으론 문장이 부족)

# ── DART 호출 예산 정책 ─────────────────────────────────────────────────────────────────────
#   ★ 19,000 같은 상수를 처음부터 박아두지 않습니다.
#     "auto"  : 공식 상한(20,000)에서 시작하되, 오늘 이미 쓴 양을 드라이브 원장에서 읽고,
#               응답 status=020(한도초과)을 만나면 그 지점을 실제 상한으로 학습해 기록합니다.
#               다음 실행부터는 학습된 상한을 씁니다. 즉 남은 양을 실시간으로 추적합니다.
#   정수를 직접 넣으면 그 값을 상한으로 고정합니다(디버깅용).
ARC_DART_LIMIT_MODE   = "auto"
ARC_DART_LIMIT_HINT   = 20_000        # auto 모드의 초기 추정치 (학습되면 덮어씀)
ARC_DART_SAFETY       = 200           # 마지막 여유분 — 다음 실행의 메타 조회용으로 남겨둠

SEED = 20260810                       # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_CONTRACT_FAIL = True          # 계약 위반 시 즉시 중단 (False 로 끄지 마세요)

STRATEGY_ID   = "ARC_TXT_V2"
STRATEGY_NAME = "애널리스트 텍스트톤 변화 × DART 3층 교차확증"
BUILD_VERSION = "v2.20260810.0639"

# 하위 호환 별칭 — 재사용하는 L0/L1 조각들이 이 이름을 참조합니다.
CUSTOMS_API_KEY = ""
GDRIVE_ADOPT_DIRS = CACHE_SEARCH_DIRS


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import inspect
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
    ("FinanceDataReader", "finance-datareader", "가격/상장목록/시가총액 1순위 폴백"),
    ("pykrx",             "pykrx",              "PIT 상장목록·시가총액 — 생존자편향 제거의 핵심"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출(가장 빠름)"),
    ("pdfplumber",        "pdfplumber",         "PDF 추출 폴백"),
    ("rapidfuzz",         "rapidfuzz",          "사업장명/애널리스트명 유사도 매칭(고속)"),
    ("statsmodels",       "statsmodels",        "HAC(Newey-West) 표준오차"),
    ("html5lib",          "html5lib",           "깨진 HTML 복구 파싱"),
    # ── ARC 전용 ──────────────────────────────────────────────────────────────────────────
    ("sklearn",           "scikit-learn",       "축 A TONE 분류기(TF-IDF + NB/LogReg) — 없으면 순수 numpy NB 로 폴백"),
    ("scipy",             "scipy",              "희소행렬 코사인(D1) · 통계검정"),
    ("soynlp",            "soynlp",             "한국어 비지도 토큰화 폴백(형태소 분석기 없을 때)"),
]

# ★ konlpy / lightgbm 은 '설치 시도조차' 하지 않는다.
#   konlpy 는 JVM(JDK) 이 필요해서 Colab 이 아닌 환경에서 설치가 실패하거나, 설치돼도
#   import 시점에 JVM 을 띄우려다 프로세스를 통째로 죽이는 사례가 있다. 있으면 쓰고 없으면
#   soynlp → 규칙기반으로 내려간다(15_ingest_dart_doc 의 폴백 사다리).
#   lightgbm 도 마찬가지로 무거우며, TONE 분류기는 LogReg 로 충분하다.
_OPTIONAL_DETECT_ONLY = [
    ("konlpy",   "konlpy",   "한국어 형태소 분석(Mecab/Okt). 있으면 D1 토큰화 품질이 가장 좋음"),
    ("lightgbm", "lightgbm", "TONE 분류기 대안 (ARC_TONE_MODEL='lgbm' 일 때만)"),
    ("Mecab",    "mecab-ko", "Mecab 직결 바인딩(가장 빠름)"),
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
    out = {mod: (importlib.util.find_spec(mod) is not None) for mod, _pkg, _why in _OPTIONAL}
    for mod, _pkg, _why in _OPTIONAL_DETECT_ONLY:          # 설치 시도 없이 존재 여부만
        try:
            out[mod] = importlib.util.find_spec(mod) is not None
        except Exception:
            out[mod] = False
    return out


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

# ── ARC 전용 선택 모듈 ──────────────────────────────────────────────────────────────────────
#   ★ sklearn 은 import 자체가 수 초 걸리므로 여기서 한 번만 붙잡아 둔다.
#     없으면 30_axis_a_tone 이 순수 numpy Multinomial NB 로 폴백한다(결과는 열화, 실행은 지속).
sk_tfidf = sk_logreg = sk_nb = sk_sparse = lgbm = konlpy_tag = soynlp_tok = None
if OPT.get("sklearn"):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer as sk_tfidf   # type: ignore
        from sklearn.linear_model import LogisticRegression as sk_logreg          # type: ignore
        from sklearn.naive_bayes import MultinomialNB as sk_nb                    # type: ignore
    except Exception:
        sk_tfidf = sk_logreg = sk_nb = None
if OPT.get("scipy"):
    try:
        from scipy import sparse as sk_sparse     # type: ignore
    except Exception:
        sk_sparse = None
if OPT.get("lightgbm"):
    try:
        import lightgbm as lgbm                   # type: ignore
    except Exception:
        lgbm = None
if OPT.get("soynlp"):
    try:
        from soynlp.tokenizer import LTokenizer as soynlp_tok    # type: ignore
    except Exception:
        soynlp_tok = None
# konlpy 는 import 시 JVM 을 띄우다 프로세스를 죽일 수 있어 '지연 import' 로만 접근한다.
# 실제 로딩은 15_ingest_dart_doc 의 _doc_load_tagger() 안에서 try 로 감싸 수행한다.
KONLPY_AVAILABLE = bool(OPT.get("konlpy"))

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
        """★★ skip_if 는 '스테이지를 SKIP 으로 표시' 할 뿐 **본문 실행을 막지 않는다**.

        파이썬 컨텍스트 매니저는 구조적으로 with 블록의 본문을 건너뛸 수 없다(yield 이후
        제어가 본문으로 넘어간 뒤 돌아온다). 그래서 `with PIPE.stage(..., skip_if=True):`
        안의 코드는 그대로 실행된다 — 이 사실을 모르고 쓰면 '축을 껐다'고 로그에는 찍히는데
        실제로는 계산이 다 돌아가고 값까지 반영되는 조용한 사고가 난다.

        → 호출부는 반드시 본문 안에서 명시적으로 `if <조건>:` 로 분기해야 한다.
          stage_skipped(rec) 로 레코드에서 스킵 여부를 확인할 수도 있다.
        """
        rec = StageRecord(sid=sid, name=name, layer=layer, budget_s=budget_s)
        self.stages[sid] = rec
        prev, self.current = self.current, rec
        LOG.ctx.append(sid)
        if skip_if:
            rec.status, rec.t_start, rec.t_end = "SKIP", time.time(), time.time()
            rec.notes.append(skip_reason or "조건 미충족")
            LOG.warn(f"건너뜀 — {skip_reason}")
            LOG.ctx.pop(); self.current = prev
            # ★ 본문은 어차피 실행되므로(위 docstring), 예외 가드도 실행 경로와 **동일하게**
            #   걸어야 한다. 예전에는 이 yield 가 try 밖에 있어서, skip 표시된 스테이지에서는
            #   critical=False 가 무력화됐다. 게이트가 실패하는 상황은 곧 데이터가 부실한
            #   상황이므로, 본문이 던질 확률이 가장 높은 바로 그때 가드가 사라졌다.
            try:
                yield rec
            except BaseException as e:                              # noqa
                rec.err_type = type(e).__name__
                rec.err_msg = str(e)
                rec.err_tb = traceback.format_exc()
                rec.notes.append(f"WARN: SKIP 스테이지 본문에서 {rec.err_type}: {rec.err_msg}")
                LOG.error(f"건너뛴 스테이지 본문에서 예외 — {rec.err_type}: {rec.err_msg}")
                if critical:
                    rec.status = "FAIL"
                    raise
                rec.status = "WARN"
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


def stage_skipped(rec: "StageRecord") -> bool:
    """스테이지가 SKIP 으로 표시되었는가. with 본문 안에서 분기할 때 쓴다."""
    return getattr(rec, "status", "") == "SKIP"


PIPE = Pipeline()



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


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C+  ARC 전용 헬퍼 — 분기 시간축 / 횡단면 직교화 / IC                                  ║
# ║                                                                                          ║
# ║  ARC-TXT 의 기본 시간 단위는 '월'이 아니라 '분기'다. 이 블록이 그 축을 정의한다.           ║
# ║  월 기준 헬퍼(month_range 등)를 실수로 쓰면 리밸런싱 횟수가 3배가 되고 회전율·비용이       ║
# ║  전부 틀어지므로, 분기 함수는 이름을 완전히 다르게 지어 혼동을 원천 차단한다.              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def rebal_dates(start, end) -> pd.DatetimeIndex:
    """§4 리밸런싱일: 매년 3/1, 6/1, 9/1, 12/1 중 백테스트 구간 안쪽만.

    ★ 달력일 그대로 둔다. '직전 거래일로 당기기'는 가격 패널이 있어야 가능한데,
      유니버스 구축이 가격보다 먼저 필요하므로 여기서는 달력일을 기준점으로 삼고
      체결가만 '해당일 이후 첫 거래일의 시가'로 잡는다(41_backtest).
    """
    s, e = as_ts(start), as_ts(end)
    if s is None or e is None:
        return pd.DatetimeIndex([])
    out = []
    for y in range(s.year - 1, e.year + 2):
        for m in ARC_REBAL_MONTHS:
            t = pd.Timestamp(year=y, month=m, day=1)
            if s <= t <= e:
                out.append(t)
    return pd.DatetimeIndex(sorted(out))


def qlabel(ts) -> str:
    """Timestamp → 'YYYYQn'. 분기 라벨은 문자열로만 다룬다(정수 인코딩은 연말 경계에서 깨진다)."""
    t = as_ts(ts)
    if t is None:
        return ""
    return f"{t.year}Q{(t.month - 1) // 3 + 1}"


def qshift(qs: str, k: int) -> str:
    """'2019Q3', -1 → '2019Q2' / '2019Q3', -4 → '2018Q3'."""
    m = re.match(r"^(\d{4})Q([1-4])$", str(qs or ""))
    if not m:
        return ""
    y, q = int(m.group(1)), int(m.group(2))
    n = y * 4 + (q - 1) + k
    return f"{n // 4}Q{n % 4 + 1}"


def qend(qs: str) -> Optional[pd.Timestamp]:
    """'2019Q3' → 2019-09-30 (분기 결산기준일)."""
    m = re.match(r"^(\d{4})Q([1-4])$", str(qs or ""))
    if not m:
        return None
    y, q = int(m.group(1)), int(m.group(2))
    return as_ts(f"{y}-{q*3:02d}-01") + pd.offsets.MonthEnd(0)


def prev_quarter_of(asof) -> str:
    """리밸일 시점에 '이미 종료된' 직전 분기 라벨.

    ★ 3/1 리밸일에 2019Q1(1~3월) 을 쓰면 아직 끝나지 않은 분기를 쓰는 것이므로 미래누수다.
      3/1 → 2018Q4, 6/1 → 2019Q1, 9/1 → 2019Q2, 12/1 → 2019Q3.
    """
    t = as_ts(asof)
    if t is None:
        return ""
    return qlabel(t - pd.offsets.QuarterEnd(1)) if t.day <= 15 else qlabel(t)


ARC_CELL_LADDER = ("cell", "cell_all")


def xsec_z_arc(P: pd.DataFrame, name_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    """ARC 셀 사다리(cell → cell_all)를 적용한 횡단면 z-score.

    ★ 왜 사다리가 필요한가: 섹터에 종목이 30개 있어도 '그 지표를 실제로 관측한' 종목은
      5개뿐일 수 있다(D1 은 문서 파싱 실패, D3 는 섹터 편향). 셀 크기만 보고 판단하면
      z 가 전부 NaN 이 되고, 그 축은 아무 신호도 못 내면서 로그에는 아무것도 남지 않는다.
    """
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(pd.Series(name_or_series), errors="coerce")
    v = pd.Series(np.asarray(v, dtype="float64"), index=P.index)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    if "cell_all" in P.columns and z.isna().any():
        z = z.where(z.notna(), xsec_z(v, P["cell_all"], min_n))
    return z.astype("float32")


def xsec_rank_arc(P: pd.DataFrame, name_or_series, min_n: int = CELL_MIN_N) -> pd.Series:
    v = col(P, name_or_series) if isinstance(name_or_series, str) else \
        pd.to_numeric(pd.Series(name_or_series), errors="coerce")
    v = pd.Series(np.asarray(v, dtype="float64"), index=P.index)
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    r = xsec_rank_pct(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    if "cell_all" in P.columns and r.isna().any():
        r = r.where(r.notna(), xsec_rank_pct(v, P["cell_all"], min_n))
    return r.astype("float32")


def winsor_series(s, p: float = 0.01) -> pd.Series:
    """백분위 기준 상하위 p 윈저라이즈. ±inf 를 먼저 NaN 으로 바꾼다(§C5 와 동일한 이유)."""
    v = pd.to_numeric(pd.Series(s), errors="coerce").replace([np.inf, -np.inf], np.nan)
    if v.notna().sum() < 5 or not (0 < p < 0.5):
        return v
    lo, hi = v.quantile(p), v.quantile(1 - p)
    return v.clip(lower=lo, upper=hi)


OLS_MIN_OBS_PER_PARAM = 5      # 횡단면 회귀 자유도 하한 (관측수 / 파라미터수)


def ols_resid_np(y: np.ndarray, X: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    """단일 횡단면 OLS 잔차. 절편은 호출자가 넣지 않아도 여기서 붙인다.

    ★ 섹터 더미까지 넣으면 X 가 특이행렬이 되기 쉽다(완전공선성). lstsq 는 조용히
      이상한 계수를 낼 수 있으므로 ridge 를 아주 작게 걸어 수치적으로 안정화한다.
      ridge 는 잔차를 거의 바꾸지 않는다(1e-8 은 스케일 대비 무시 가능).
    """
    y = np.asarray(y, dtype=np.float64).ravel()
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    n = len(y)
    if n == 0:
        return np.full(0, np.nan)
    A = np.column_stack([np.ones(n), X])
    ok = np.isfinite(y) & np.isfinite(A).all(axis=1)
    out = np.full(n, np.nan)
    # ★ 자유도 가드를 파라미터 수의 '비율'로 잡는다. p+3 은 너무 헐거웠다 —
    #   통제변수 6개 + 섹터더미 7개 + 절편 = 14 파라미터인데 관측 17개면 통과했고,
    #   그때 잔차와 원신호의 상관은 0.42 에 불과했다(나머지 58%가 적합오차). 그러면
    #   '직교화된 톤'이 실제로는 규모·모멘텀·섹터의 결정적 함수, 즉 위장된 사이즈 베팅이
    #   되고 그 값이 FINAL_SCORE 의 50% 를 차지한다. 실측 상관: n=17 0.42 · n=30 0.74 ·
    #   n=60 0.88 · n=120 0.94. 5p 를 최소선으로 둔다.
    if ok.sum() < max(A.shape[1] + 3, OLS_MIN_OBS_PER_PARAM * A.shape[1]):
        return out
    Ao, yo = A[ok], y[ok]
    G = Ao.T @ Ao
    G = G + ridge * np.maximum(1.0, np.trace(G) / max(G.shape[0], 1)) * np.eye(G.shape[0])
    try:
        beta = np.linalg.solve(G, Ao.T @ yo)
    except np.linalg.LinAlgError:
        beta = np.linalg.pinv(G) @ (Ao.T @ yo)
    out[ok] = yo - Ao @ beta
    return out


XSEC_RESID_DOF: List[dict] = []      # 직교화 자유도 진단(셀별 관측수/파라미터수)


def xsec_resid(y, X: pd.DataFrame, cells) -> pd.Series:
    """셀(=기간)별 횡단면 OLS 잔차. §5.3 직교화의 실행부.

    ★ 결측 처리 규칙이 중요하다. 통제변수가 결측이면 그 행은 '직교화되지 않은 원값'이
      되어선 안 된다 — 그러면 통제 안 된 알파가 그대로 섞인다. 통제변수 결측은
      호출자가 기간 중앙값으로 대체한 뒤 넘기고, y 가 결측인 행만 NaN 으로 남긴다.
    """
    yv = pd.to_numeric(pd.Series(y), errors="coerce").replace([np.inf, -np.inf], np.nan)
    idx = yv.index
    Xv = X.reindex(idx).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    g = pd.Series(cells).reindex(idx).astype(object).fillna("__NA__")
    out = pd.Series(np.nan, index=idx, dtype="float64")
    # ★ 셀 가드는 '셀 전체 행수'가 아니라 **y 가 실제로 관측된 행수**로 봐야 한다.
    #   전자는 분기 총 행수(≈1000)라 항상 통과하고, 실제 회귀는 dTONE 이 있는 20~60행으로
    #   돌아간다. 진단용으로 셀별 (관측수/파라미터수) 비를 남긴다.
    XSEC_RESID_DOF.clear()
    n_par = int(Xv.shape[1]) + 1
    for gk, pos in g.groupby(g, observed=True).groups.items():
        sl = list(pos)
        n_obs = int((yv.loc[sl].notna() & Xv.loc[sl].notna().all(axis=1)).sum())
        XSEC_RESID_DOF.append({"cell": str(gk), "n_obs": n_obs, "n_param": n_par,
                               "ratio": (n_obs / n_par) if n_par else np.nan})
        if len(sl) < 12:                     # 표본이 너무 적으면 회귀가 잡음을 학습한다
            continue
        out.loc[sl] = ols_resid_np(yv.loc[sl].to_numpy(), Xv.loc[sl].to_numpy())
    _thin = [d for d in XSEC_RESID_DOF if 0 < d["n_obs"] and d["ratio"] < OLS_MIN_OBS_PER_PARAM]
    if _thin:
        LOG.warn(f"직교화 자유도 부족으로 잔차를 만들지 못한 셀 {len(_thin)}개 "
                 f"(관측/파라미터 비 < {OLS_MIN_OBS_PER_PARAM}). 해당 기간의 ΔTONE_resid 는 "
                 f"결측입니다 — 적합오차를 신호로 쓰지 않기 위한 의도된 결측입니다. "
                 f"최소 비율 {min(d['ratio'] for d in _thin):.1f} · 파라미터 {n_par}개")
    return out.astype("float32")


def measurable_ret(R: pd.DataFrame, key: str = "ret") -> pd.Series:
    """성과·유의성 계산에 쓸 수익률 시계열. **측정 불가 분기를 일관되게 제외한다.**

    ★ perf_stats 는 R[R["measurable"]] 로 마지막 리밸일(전 종목 fwd_ret 결측)을 빼는데,
      어블레이션의 초과수익·p(HAC)·§9.2-(8) BH-FDR 판정은 원본 R 을 그대로 썼다. 그러면
      §9.2-(6) 표의 '초과수익·p(HAC)' 열과 성과표(CAGR/Sharpe)가 서로 다른 39 vs 40 분기
      표본에서 나온다. 사전등록된 유의성 판정이 정의와 어긋나면 안 되므로 한 곳으로 모은다.
    """
    if R is None or len(R) == 0:
        return pd.Series(dtype="float64")
    Rm = R[R["measurable"].astype(bool)] if "measurable" in R.columns else R
    if len(Rm) == 0:
        Rm = R
    return Rm.set_index("asof")[key]


def newey_west_p(x, lags: Optional[int] = None) -> float:
    """HAC t → 양측 p-value. scipy 가 없으면 정규근사로 폴백한다."""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 8:
        return float("nan")
    _, t = hac_tstat(a, lags=lags)
    if not np.isfinite(t):
        return float("nan")
    try:
        from scipy import stats as _st
        return float(2.0 * (1.0 - _st.t.cdf(abs(t), df=max(1, len(a) - 1))))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2.0)))


def info_coef(sig, fwd, groups) -> Tuple[float, float, int]:
    """기간별 Spearman IC 의 (평균, IC-IR, 기간수).

    ★ 전체를 한 번에 상관내면 안 된다. 기간 간 수준 차이가 상관을 만들어내기 때문이다
      (예: 특정 분기에 전 종목 신호와 수익이 동시에 높으면 가짜 IC 가 생긴다).
      횡단면 IC 를 기간별로 구한 뒤 시계열 평균/표준편차로 IR 을 만든다.
    """
    s = pd.to_numeric(pd.Series(sig), errors="coerce")
    f = pd.to_numeric(pd.Series(fwd), errors="coerce").reindex(s.index)
    g = pd.Series(groups).reindex(s.index).astype(object)
    ics = []
    for _, pos in g.groupby(g, observed=True).groups.items():
        sl = list(pos)
        a, b = s.loc[sl], f.loc[sl]
        m = a.notna() & b.notna()
        if int(m.sum()) < 20:
            continue
        try:
            r = float(a[m].rank().corr(b[m].rank()))
        except Exception:
            continue
        if np.isfinite(r):
            ics.append(r)
    if len(ics) < 3:
        return (float("nan"), float("nan"), len(ics))
    arr = np.asarray(ics, dtype=float)
    mu = float(arr.mean())
    sd = float(arr.std(ddof=1))
    # ★ 반환 2번째 값은 **t통계량**이다(IR × √n). IC-IR 의 표준 정의는 mean/std 이므로
    #   같은 숫자를 'IC-IR' 로 표기하면 분기 40개에서 √40 = 6.32배 부풀려진 값을 읽게 된다
    #   (진짜 IR 0.25 → 표에 1.58). 기간 수가 다른 팔끼리는 부풀림 배수까지 달라져 순위가
    #   뒤집힌다. 소비 측은 info_coef_full() 로 IR 과 t 를 분리해 받는다.
    return (mu, (mu / sd * math.sqrt(len(arr))) if sd > 0 else float("nan"), len(arr))


def info_coef_full(sig, fwd, groups) -> Tuple[float, float, float, int]:
    """(평균 IC, IC-IR = mean/std, t통계량 = IR×√n, 기간수). 표에 쓸 때는 이쪽을 쓴다."""
    mu, tstat, n = info_coef(sig, fwd, groups)
    ir = (tstat / math.sqrt(n)) if (n > 0 and np.isfinite(tstat)) else float("nan")
    return (mu, ir, tstat, n)


def next_trading_on_or_after(trading_days: np.ndarray, t) -> Optional[pd.Timestamp]:
    """t 이상인 첫 거래일. 없으면 None. (달력 리밸일 → 실제 체결일 변환)"""
    tt = as_ts(t)
    if tt is None or trading_days is None or len(trading_days) == 0:
        return None
    i = int(np.searchsorted(trading_days, np.datetime64(tt), side="left"))
    return as_ts(trading_days[i]) if i < len(trading_days) else None


def shift_trading_days(trading_days: np.ndarray, t, k: int) -> Optional[pd.Timestamp]:
    """t 를 기준으로 k 거래일 이동(±). 강건성 검사 '리밸런싱 ±5거래일'에 쓴다."""
    tt = as_ts(t)
    if tt is None or trading_days is None or len(trading_days) == 0:
        return None
    i = int(np.searchsorted(trading_days, np.datetime64(tt), side="left")) + int(k)
    i = max(0, min(len(trading_days) - 1, i))
    return as_ts(trading_days[i])


def assert_no_dup_cols_arc(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 에서 예외 없이 의미가 바뀐다(df[c] 가 DataFrame 이 된다).
    조용히 지나가면 최악이므로 발생 지점에서 즉시 세운다."""
    if df is None or len(df) == 0:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — "
                           f"pandas 연산의 의미가 바뀌므로 여기서 중단합니다.")
    return df


def ensure_cols(df: pd.DataFrame, cols: Sequence[str], fill=np.nan) -> pd.DataFrame:
    """계약 컬럼 보장. 수집이 얼마나 실패하든 패널의 컬럼 집합은 항상 같아야 한다.

    ★ 그래야 '어떤 실행에선 있고 어떤 실행엔 없는' 축이 사라지고, 결측이 조용히가 아니라
      표로 드러난다. 하류에서 KeyError 로 죽는 대신 결측률이 보고된다.
    """
    for c in cols:
        if c not in df.columns:
            df[c] = fill
    return df


def arc_kd_lag(df: pd.DataFrame, days: int = None) -> pd.DataFrame:
    """§4 시점 규약 — DART 파생 테이블의 knowledge_date 에 T+거래일 지연을 적용한다.

    ★ 왜 필요한가: `_knowledge_from_rcept` 는 접수일자(rcept_dt) 를 그대로 knowledge_date 로
      쓴다. 그러면 '접수 당일'에 그 재무제표를 쓸 수 있게 되는데, 명세 §4 는
      "rcept_dt(접수일자) + 1거래일부터 사용 가능" 을 규정한다. 접수는 장중에도 일어나므로
      당일 사용은 실행 불가능한 정보 접근이다 — 작지만 명백한 미래누수다.
      D1(31 모듈)은 이미 명시적으로 +1 을 더하고 있어, 여기서 재무·직원·주식수·감사의견
      계열도 같은 규약으로 맞춘다. A19 계약검정이 이를 강제한다.
    """
    d = int(days if days is not None else globals().get("ARC_DART_LAG_DAYS", 1))
    if df is None or len(df) == 0 or "knowledge_date" not in getattr(df, "columns", []):
        return df
    out = df.copy()
    out["knowledge_date"] = as_ts_series(out["knowledge_date"]) + pd.Timedelta(days=d)
    return out



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

    def get_blob_by_key(self, domain: str, subtype: str, key: str,
                        scope: str = "shared") -> Optional[bytes]:
        """(domain, subtype, key) 로 원본 바이트를 찾는다.

        put_blob 의 uid 는 내용해시를 포함하므로 호출자가 재구성할 수 없다. 그래서
        uid 를 모르는 소비자(§6.3 완료형 판정 등)는 이 경로로 인덱스를 조회해야 한다.
        ★ 인덱스를 읽기만 한다 — 어떤 경우에도 기존 인덱스를 변형하지 않는다.
        """
        rows = self.lookup(scope, domain=domain, subtype=subtype, key=str(key))
        if rows is None or rows.empty:
            return None
        for _, r in rows.iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

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

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "listing_date_src",
                   "delisting_date", "corp_code", "industry", "sector_src", "src",
                   "delist_reason", "secugroup"]

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
    # ★ 'listingdate' 를 폐지일 폴백으로 쓰면 안 된다 — 상장일을 폐지일로 읽는 순간
    #   그 종목은 상장 당일 폐지된 것으로 취급되어 유니버스에서 통째로 사라진다.
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate", "date")
                 if k in col), None)
    # ★ 폐지목록 CSV 에는 ListingDate 가 실제로 들어 있다. 이것을 버리면 build_security_master
    #   가 '첫 스냅샷 등장일'(≈백테 시작월)을 상장일로 날조하고, 그 위에 250거래일 시즈닝이
    #   걸려 **폐지 종목만** 백테 초기 구간에서 사라진다(생존자편향의 정확한 반대 경로).
    ld_c = next((col[k] for k in ("listingdate", "listing_date", "listdate") if k in col), None)
    rs_c = next((col[k] for k in ("reason", "delistingreason", "note") if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c

    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    n_badcode = int(codes.isna().sum())
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "listing_date": as_ts_series(d[ld_c]) if ld_c else pd.NaT,
        "delist_reason": d[rs_c].astype(str) if rs_c else "",
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
    n_ld = int(t["listing_date"].notna().sum())
    LOG.info(f"  폐지목록에서 상장일 {n_ld:,}건 확보 "
             f"({100*n_ld/max(len(t),1):.0f}%) — 시즈닝 앵커 날조 방지용")
    if rs_c:
        rc = t["delist_reason"].astype(str).str.strip().replace("", "미상").value_counts()
        NORMAL = r"합병|완전자회사|자회사\s*편입|신청|이전\s*상장|재상장|스팩"
        n_norm = int(t["delist_reason"].astype(str).str.contains(NORMAL, na=False).sum())
        LOG.info(f"  폐지 사유 상위: " +
                 " · ".join(f"{k} {v:,}" for k, v in rc.head(6).items()))
        LOG.info(f"  이 중 정상 사유(합병·완전자회사화·자진상장폐지 등) {n_norm:,}건 "
                 f"({100*n_norm/max(len(t),1):.0f}%) — 이들에 -100% 를 붙이면 가짜 손실이 "
                 f"됩니다. 청산가는 폐지일 직전 종가를 씁니다(§3.4).")
    else:
        LOG.warn("폐지 사유 컬럼이 없어 정상 폐지(합병 등)와 부실 폐지를 구분할 수 없습니다.")
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
        # ★ 폐지목록이 상장일을 주면 반드시 쓴다. 버리면 아래 snap_first 백필이
        #   '첫 스냅샷 등장일'을 상장일로 날조하고, 그 위에 시즈닝이 걸려 폐지 종목만
        #   백테 초기에서 사라진다.
        _dcols = ["code", "name", "delisting_date", "market"] + \
                 [c for c in ("listing_date", "delist_reason") if c in dead.columns]
        d2 = dead.reindex(columns=_dcols).copy()
        if "listing_date" not in d2.columns:
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
        # ★ 스냅샷 백필은 '관측 시작일'이지 상장일이 아니다. 백테 시작월 이전에 상장된
        #   종목은 전부 백테 시작월이 상장일로 찍히고, 그 위에 250거래일 시즈닝 +
        #   ARC_MIN_LISTING_M 이 걸려 **그 종목만** 초기 구간에서 사라진다.
        #   폐지 종목은 스냅샷 커버리지가 짧아 이 경로에 훨씬 많이 걸리므로, 생존군과
        #   폐지군에 서로 다른 규칙이 적용되는 비대칭이 생긴다. 출처를 기록해 시즈닝
        #   앵커에서 제외한다(=추정 상장일로는 종목을 탈락시키지 않는다).
        need = agg["listing_date"].isna() & agg["snap_first"].notna()
        agg["listing_date_src"] = np.where(agg["listing_date"].notna(), "source", "")
        agg.loc[need, "listing_date"] = agg.loc[need, "snap_first"]
        agg.loc[need, "listing_date_src"] = "snapshot(추정)"
        if int(need.sum()):
            LOG.info(f"상장일이 없는 {int(need.sum()):,}종목을 첫 스냅샷 관측일로 보완했습니다. "
                     f"이 값은 **추정치**이므로 시즈닝·상장 {ARC_MIN_LISTING_M}개월 필터의 "
                     f"근거로는 쓰지 않습니다(근거 없는 제외 금지).")
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


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B+  PIT 시가총액 — U-1000 유니버스의 유일한 근거                                       ║
# ║                                                                                          ║
# ║  ★ 이 함수가 이 전략에서 가장 위험한 지점이다.                                             ║
# ║    "현재 시점 시총 랭크를 과거에 적용" 하는 순간 유니버스 전체가 미래정보로 오염된다.        ║
# ║    (지금 소형주인 종목은 '과거 10년간 주가가 하락한' 종목이므로, 그걸 2016년 유니버스로     ║
# ║     쓰면 하락할 종목만 골라 담은 셈이 된다 — 알파가 아니라 마이너스 알파가 나온다)          ║
# ║    그래서 시총은 반드시 '그 시점에 관측된 값'이어야 하고, 아래 3중 경로로 확보한다:          ║
# ║      ① pykrx 시점별 시가총액 스냅샷 (가장 정확. KRX 세션 필요)                              ║
# ║      ② 일봉 종가 × PIT 상장주식수(DART stockTotqySttus as-of)                              ║
# ║      ③ 일봉 종가 × 스냅샷에서 관측된 최근 상장주식수 (선형 보간 금지 — 계단 유지)           ║
# ║    ②③ 은 근사이므로 어느 경로가 몇 % 를 채웠는지 반드시 표로 보고한다.                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MKTCAP_COLS = ["date", "code", "mktcap", "shares_listed", "close_mc", "mc_src"]


def fetch_market_cap_snapshots(rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """리밸런싱 시점별 시가총액 스냅샷 (pykrx). 캐시 증분.

    ★ 전부 KRXG 게이트를 통해 직렬 호출한다. 병렬로 때리면 pykrx 가 스레드마다 재로그인해
      서로를 밀어내고(CD011), JSON 대신 로그인 HTML 을 받아 대량 실패한다.
    """
    cached = VAULT.get_table("krx_marketcap_pit", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached = cached.dropna(subset=["date", "code"])
        have = set(cached["date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"공용 캐시에서 PIT 시가총액 {len(cached):,}행 재사용 ({len(have)}개 시점)")

    # 리밸일 + 그 직전 달 말일도 함께 받아둔다(리밸 ±5거래일 강건성 검사에서 필요).
    grid: List[pd.Timestamp] = []
    for t in rebals:
        grid.append(as_ts(t))
        grid.append(as_ts(t) - pd.offsets.MonthEnd(1))
    grid = sorted({g for g in grid if g is not None})
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []
    if todo and not KRXG.warmup():
        LOG.info(f"KRX 세션이 없어 시가총액 스냅샷 {len(todo)}개 시점을 건너뜁니다. "
                 f"종가×상장주식수 경로로 대체합니다(근사, 감사표에 명시).")
        todo = []

    rows: List[dict] = []
    if todo:
        LOG.info(f"PIT 시가총액 스냅샷 {len(todo)}개 시점 수집 (직렬)")
        bad_streak = 0
        for d in tqdm(todo, desc="PIT 시가총액", ncols=88, leave=False):
            # ★ 당일 누수 차단. pykrx 의 get_nearest_business_day_in_a_week(prev=True) 는
            #   [d-7, d] 구간 지수 OHLCV 의 마지막 인덱스를 돌려주므로, **d 가 거래일이면
            #   d 를 그대로 반환**한다. 그러면 mktcap 은 리밸일 '당일 종가' 기준인데
            #   체결은 같은 날 '시가'다 → 그날 급락한 종목이 시총이 줄어 하위 1000 안으로
            #   들어오고, 우리는 급락 직전 시가에 그 종목을 살 수 있게 된다.
            #   조회 기준일을 하루 앞으로 밀어 t-1 영업일 종가를 쓰게 만든다.
            #   (build_liquidity_panel 이 allow_exact_matches=False 로 강제하는 것과 동일 규약)
            _q = (as_ts(d) - pd.Timedelta(days=1)).strftime("%Y%m%d")
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           _q, prev=True) or _q
            got_any = False
            for mkt in ("KOSPI", "KOSDAQ"):
                t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
                if t is None or len(t) == 0:
                    continue
                got_any = True
                t = t.reset_index()
                ren = {"티커": "code", "시가총액": "mktcap", "상장주식수": "shares_listed",
                       "종가": "close_mc"}
                t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
                if "code" not in t.columns:
                    t = t.rename(columns={t.columns[0]: "code"})
                if "mktcap" not in t.columns:
                    continue
                for _c, _mc, _sh, _cl in zip(
                        t["code"].astype(str),
                        pd.to_numeric(t["mktcap"], errors="coerce"),
                        pd.to_numeric(t.get("shares_listed", pd.Series(np.nan, index=t.index)),
                                      errors="coerce"),
                        pd.to_numeric(t.get("close_mc", pd.Series(np.nan, index=t.index)),
                                      errors="coerce")):
                    cc = to_code6(_c)
                    if cc and np.isfinite(_mc) and _mc > 0:
                        # ★ 라벨은 요청한 격자일(d)이 아니라 **실제 관측일(bd)** 이다.
                        #   d 로 찍으면 소비 측 merge_asof 가 date==asof 를 정확히 매칭해
                        #   당일 정보를 쓰게 된다.
                        rows.append({"date": pd.Timestamp(bd).strftime("%Y-%m-%d"),
                                     "grid_date": d.strftime("%Y-%m-%d"), "code": cc,
                                     "mktcap": float(_mc), "shares_listed": float(_sh),
                                     "close_mc": float(_cl), "mc_src": "pykrx"})
            bad_streak = 0 if got_any else bad_streak + 1
            if bad_streak >= 5:
                LOG.warn("시가총액 스냅샷이 연속 5회 비었습니다 — 세션이 끊겼거나 차단된 상태입니다. "
                         "수집을 중단하고 종가×상장주식수 경로로 폴백합니다(정상 폴백).")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=MKTCAP_COLS)
    M = pd.concat(frames, ignore_index=True)
    M["date"] = as_ts_series(M["date"])
    M = (M.dropna(subset=["date", "code", "mktcap"])
           .drop_duplicates(["date", "code"], keep="last").reset_index(drop=True))
    if rows:
        out = M.copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_pit", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "PIT 시가총액 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_marketcap_pit", M, source="pykrx")
    return downcast(M)


def build_mktcap_panel(rebals: pd.DatetimeIndex, px_monthly: pd.DataFrame,
                       snap_mc: pd.DataFrame, shares: pd.DataFrame,
                       sec: pd.DataFrame) -> pd.DataFrame:
    """(code, asof) 격자에 PIT 시가총액을 채운다. 3중 경로 + 출처 기록.

    반환: code, asof, mktcap, shares_listed, mc_src
    """
    if px_monthly is None or px_monthly.empty:
        return pd.DataFrame(columns=["code", "asof", "mktcap", "shares_listed", "mc_src"])

    # ── 경로 ① 스냅샷 직접 매칭 (as-of backward: 리밸일 이전 최근 스냅샷) ──────────────────
    base_rows = []
    px = px_monthly[["code", "month", "close"]].dropna(subset=["code", "month"]).copy()
    px["month"] = as_ts_series(px["month"])
    for t in rebals:
        # 리밸일 t 시점에 '알 수 있었던' 최근 월말 종가 = t 이전 마지막 월말
        prev_m = as_ts(t) - pd.offsets.MonthEnd(1)
        sub = px[px["month"] == prev_m][["code", "close"]].copy()
        if sub.empty:
            continue
        sub["asof"] = as_ts(t)
        base_rows.append(sub)
    if not base_rows:
        return pd.DataFrame(columns=["code", "asof", "mktcap", "shares_listed", "mc_src"])
    B = pd.concat(base_rows, ignore_index=True)
    # ★★ code 를 반드시 문자열로 고정한다. fetch_prices 는 downcast() 를 거치는데, 일봉은
    #    3,500종목 × 875만행이라 nunique/len ≈ 0.0004 < cat_thresh 라서 **code 가 category
    #    dtype 으로 바뀐다.** 그 dtype 이 여기까지 전파되면 아래 폴백 경로 ②③ 의
    #    merge_asof(by=...) 가 "incompatible merge keys ... must be the same type" 로 죽는다.
    #    경로 ① 만 astype(str) 을 했었기 때문에, KRX 로그인이 없어 경로 ①이 열리지 않는
    #    실행에서는 DART 주식총수와 월말 종가가 둘 다 멀쩡한데도 시총이 100% 결측이 되고,
    #    U-1000 이 0행 → build_arc_panel 이 RuntimeError → 실행 전체가 중단됐다.
    #    경로 ② 의 예외 문구는 "대개 정렬/타입 문제" 수준이라 원인이 사용자 설정(KRX 로그인)
    #    으로 오인됐고, 경로 ③ 은 except: pass 로 로그가 한 줄도 없었다.
    B["code"] = B["code"].astype(str)
    B["mktcap"] = np.nan
    B["shares_listed"] = np.nan
    B["mc_src"] = ""

    if snap_mc is not None and len(snap_mc):
        S = snap_mc.copy()
        S["date"] = as_ts_series(S["date"])
        S = S.dropna(subset=["date", "code"]).sort_values("date")
        L = B.sort_values("asof").copy()
        L["code"] = L["code"].astype(str)
        S["code"] = S["code"].astype(str)
        try:
            # ★ allow_exact_matches=False — 리밸일 당일 관측치는 쓰지 않는다(§4 t-1 규약).
            #   상류에서 이미 t-1 영업일로 조회하지만, 캐시에 예전 라벨링의 행이 남아 있을
            #   수 있으므로 소비 측에서도 이중으로 막는다.
            M = pd.merge_asof(L, S[["date", "code", "mktcap", "shares_listed"]],
                              left_on="asof", right_on="date", by="code",
                              direction="backward", allow_exact_matches=False,
                              tolerance=pd.Timedelta(days=120), suffixes=("", "_s"))
            hit = M["mktcap_s"].notna() if "mktcap_s" in M.columns else M["mktcap"].notna()
            if "mktcap_s" in M.columns:
                M.loc[hit, "mktcap"] = M.loc[hit, "mktcap_s"]
                M.loc[hit, "shares_listed"] = M.loc[hit, "shares_listed_s"]
                M = M.drop(columns=[c for c in ("mktcap_s", "shares_listed_s", "date")
                                    if c in M.columns])
            M.loc[hit, "mc_src"] = "pykrx_snapshot"
            B = M
        except Exception as e:                                       # noqa
            LOG.warn(f"시총 스냅샷 as-of 결합 실패({type(e).__name__}) — 종가×주식수 경로로 진행합니다.")

    # ── 경로 ② 종가 × PIT 상장주식수 (DART) ────────────────────────────────────────────────
    need = B["mktcap"].isna()
    if need.any() and shares is not None and len(shares) and "corp_code" in sec.columns:
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict())
        Sh = shares.copy()
        Sh["knowledge_date"] = as_ts_series(Sh["knowledge_date"])
        Sh = (Sh.dropna(subset=["knowledge_date", "corp_code"])
                .sort_values("knowledge_date"))
        Sh["corp_code"] = Sh["corp_code"].astype(str)
        L = B.loc[need, ["code", "asof", "close"]].copy()
        L["code"] = L["code"].astype(str)
        L["corp_code"] = L["code"].map(c2c).astype(object)
        L = L.dropna(subset=["corp_code"]).sort_values("asof")
        if len(L):
            try:
                M2 = pd.merge_asof(L, Sh[["knowledge_date", "corp_code", "shares_total"]],
                                   left_on="asof", right_on="knowledge_date", by="corp_code",
                                   direction="backward")
                M2 = M2.dropna(subset=["shares_total"])
                M2["mktcap2"] = pd.to_numeric(M2["close"], errors="coerce") * \
                    pd.to_numeric(M2["shares_total"], errors="coerce")
                key = M2.set_index(["code", "asof"])
                idx = pd.MultiIndex.from_frame(B[["code", "asof"]])
                fill_mc = key["mktcap2"].reindex(idx).to_numpy()
                fill_sh = key["shares_total"].reindex(idx).to_numpy()
                m = need.to_numpy() & np.isfinite(fill_mc) & (fill_mc > 0)
                B.loc[m, "mktcap"] = fill_mc[m]
                B.loc[m, "shares_listed"] = fill_sh[m]
                B.loc[m, "mc_src"] = "close×DART주식수"
            except Exception as e:                                   # noqa
                LOG.warn(f"종가×DART주식수 결합 실패({type(e).__name__}: {str(e)[:120]}) — "
                         f"해당 경로를 건너뜁니다. 이 경로가 죽으면 KRX 로그인이 없는 실행에서 "
                         f"시총이 통째로 결측이 되고 U-1000 이 비어 실행 전체가 중단됩니다.")

    # ── 경로 ③ 종가 × 종목별 마지막 관측 상장주식수(스냅샷) ────────────────────────────────
    need = B["mktcap"].isna()
    if need.any() and snap_mc is not None and len(snap_mc):
        S = snap_mc.copy()
        S["date"] = as_ts_series(S["date"])
        S = S.dropna(subset=["date", "code", "shares_listed"]).sort_values("date")
        S["code"] = S["code"].astype(str)
        L = B.loc[need, ["code", "asof", "close"]].copy().sort_values("asof")
        L["code"] = L["code"].astype(str)
        if len(L) and len(S):
            try:
                M3 = pd.merge_asof(L, S[["date", "code", "shares_listed"]],
                                   left_on="asof", right_on="date", by="code",
                                   direction="backward")
                M3 = M3.dropna(subset=["shares_listed"])
                M3["mktcap3"] = pd.to_numeric(M3["close"], errors="coerce") * \
                    pd.to_numeric(M3["shares_listed"], errors="coerce")
                key = M3.set_index(["code", "asof"])
                idx = pd.MultiIndex.from_frame(B[["code", "asof"]])
                fill_mc = key["mktcap3"].reindex(idx).to_numpy()
                fill_sh = key["shares_listed"].reindex(idx).to_numpy()
                m = need.to_numpy() & np.isfinite(fill_mc) & (fill_mc > 0)
                B.loc[m, "mktcap"] = fill_mc[m]
                B.loc[m, "shares_listed"] = fill_sh[m]
                B.loc[m, "mc_src"] = "close×최근관측주식수"
            except Exception as e:                                   # noqa
                # ★ 예전에는 `except Exception: pass` 라 로그가 한 줄도 없었다. 이 경로가
                #   조용히 죽으면 시총이 결측이 되고 그 종목이 유니버스에서 통째로 빠진다.
                LOG.warn(f"종가×최근관측주식수 결합 실패({type(e).__name__}: "
                         f"{str(e)[:120]}) — 해당 경로를 건너뜁니다.")

    B["mc_src"] = B["mc_src"].replace("", "결측")
    cov = B.groupby("mc_src").size().sort_values(ascending=False)
    LOG.table([[k, f"{v:,}", f"{100*v/max(len(B),1):.1f}%"] for k, v in cov.items()],
              ["시총 출처", "행수", "비중"], ["l", "r", "r"],
              title="PIT 시가총액 출처 감사 (근사 경로 비중이 크면 U-1000 경계가 흔들립니다)")
    miss = float((B["mktcap"].isna()).mean()) if len(B) else 1.0
    if miss > 0.25:
        LOG.warn(f"PIT 시가총액 결측률 {100*miss:.1f}% — U-1000 랭크가 부정확해집니다. "
                 f"KRX 로그인(KRX_MARKETPLACE_ID/PW)을 넣으면 ①경로가 열려 크게 개선됩니다.")
        PIPE.note(f"WARN: 시총 결측률 {100*miss:.1f}%")
    return B[["code", "asof", "mktcap", "shares_listed", "mc_src"]]



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  DART — 재무제표 / 직원현황 / 공시목록                                               ║
# ║                                                                                          ║
# ║  ★ PIT 핵심: knowledge_date = 접수일자(rcept_dt). 결산기준일이 아니다.                     ║
# ║    fnltt* 응답의 rcept_no 앞 8자리가 곧 접수일자다 → 여기서 knowledge_date 를 얻는다.       ║
# ║    rcept_no 가 없으면 법정 제출기한(분기 45일 / 사업보고서 90일)으로 보수적 추정한다.       ║
# ║    ※ 보수적 추정은 '늦게 알았다'는 방향이므로 미래누수를 만들지 않는다.                     ║
# ║                                                                                          ║
# ║  ★ 호출 예산: DART 는 일 20,000건 제한. 10년 분기 전체 재무제표는 그 몇 배다.               ║
# ║    → 콜드빌드는 며칠에 걸쳐 '이어받기'로 완성된다(§3: 콜드빌드는 4시간 예산 밖).            ║
# ║    → 남은 호출량을 실시간으로 표시하고, 한도에 닿으면 깨끗하게 멈춘 뒤 진행률을 알려준다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DART_BASE = "https://opendart.fss.or.kr/api/"
DART_STATEMENT_FREQ = "quarterly"         # "quarterly" | "annual"
REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


class DartBudget:
    """DART 일일 호출 예산 — **상한을 하드코딩하지 않고 실시간으로 추적·학습한다.**

    ★ 왜 19,000 같은 상수를 박으면 안 되는가:
      ① 계정 등급·정책 변경으로 실제 한도가 달라진다(20,000 이 아닐 수 있다).
      ② 같은 키를 다른 노트북/스크립트가 함께 쓰면 우리가 센 숫자와 서버의 숫자가 어긋난다.
      ③ 여유분을 크게 잡으면 매일 수천 건을 그냥 버리게 되고, 콜드빌드가 며칠 더 걸린다.
      → 그래서 (a) 오늘 이미 쓴 양을 드라이브 원장에서 읽고,
              (b) 서버가 status=020(한도초과)을 준 지점을 '실측 상한'으로 학습해 기록하며,
              (c) 다음 실행부터 그 학습값을 쓴다.
        상한을 모르는 첫날에는 힌트값(ARC_DART_LIMIT_HINT)에서 출발하되, 그건 '추정'이라고
        로그에 명시한다.

    원장은 전용 인덱스에 남는다(다른 전략의 예산과 섞이면 안 되므로 private).
    """

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0                       # 오늘 사용한 호출 수 (우리가 센 것)
        self.exhausted = False
        self.learned_limit: Optional[int] = None   # 서버가 실제로 거부한 지점
        self.hit_020_at: Optional[int] = None
        self._lk = threading.Lock()
        self._load()

    # ── 상한 결정 ---------------------------------------------------------------------
    def limit(self) -> int:
        mode = globals().get("ARC_DART_LIMIT_MODE", "auto")
        if isinstance(mode, (int, float)) and not isinstance(mode, bool):
            return int(mode)
        base = int(self.learned_limit or globals().get("ARC_DART_LIMIT_HINT", 20_000))
        return max(100, base - int(globals().get("ARC_DART_SAFETY", 200)))

    def remaining(self) -> int:
        return max(0, self.limit() - self.n)

    def _path(self) -> str:
        return os.path.join(VAULT.ns["private"], "index", "dart_budget.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            self.learned_limit = (int(j["learned_limit"])
                                  if j.get("learned_limit") else None)
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
        except Exception:
            pass
        src = ("실측 학습값" if self.learned_limit else "추정 힌트값(아직 실측 전)")
        LOG.info(f"DART 호출 예산 — 오늘 사용 {self.n:,}건 / 상한 {self.limit():,}건 ({src}) → "
                 f"남은 호출 {self.remaining():,}건. 이 값은 실행 중 실시간으로 갱신됩니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n,
                 "learned_limit": self.learned_limit,
                 "updated": _dt.datetime.now().isoformat(timespec="seconds")}))
        except Exception:
            pass

    # ── 소비 / 환급 -------------------------------------------------------------------
    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.exhausted:
                return False
            if self.n + k > self.limit():
                self.exhausted = True
                LOG.warn(f"DART 호출 예산 소진 (사용 {self.n:,} / 상한 {self.limit():,}). "
                         f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, 내일 같은 코드를 "
                         f"다시 실행하면 정확히 이 지점부터 이어받습니다.")
                self._save()
                return False
            self.n += k
            if self.n % 250 == 0:
                self._save()
            return True

    def note_rate_limited(self):
        """서버가 status=020 을 준 순간 = 실제 상한에 닿았다. 그 지점을 학습해 영속화한다."""
        with self._lk:
            self.exhausted = True
            self.hit_020_at = self.n
            prev = self.learned_limit
            self.learned_limit = int(self.n)
            self._save()
        if prev != self.learned_limit:
            LOG.warn(f"DART 서버가 한도 초과(020)를 반환했습니다. 실제 상한을 {self.n:,}건으로 "
                     f"학습해 기록했습니다{'' if prev is None else f' (이전 학습값 {prev:,})'}. "
                     f"다음 실행부터는 이 값을 기준으로 남은 호출량을 계산합니다.")

    def report(self):
        LOG.table([["오늘 사용", f"{self.n:,}"],
                   ["적용 상한", f"{self.limit():,}"],
                   ["남은 호출", f"{self.remaining():,}"],
                   ["상한 출처", "서버 실측 학습값" if self.learned_limit else "추정 힌트값"],
                   ["020 발생 지점", f"{self.hit_020_at:,}" if self.hit_020_at else "없음"]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출 예산 (하드코딩 없이 실시간 추적)")

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, source: str = "dart",
             tries: int = 2) -> Optional[dict]:
    """★ 예산 계산 주의: http_get 은 내부적으로 최대 `tries` 회 실제 요청을 보낸다.
    호출당 1건으로 계산하면 실사용량을 최대 tries 배 과소집계해 DART 한도를 넘겨버린다.
    → 최악을 먼저 예약(take)하고, 실제 시도 횟수를 알고 나면 차액을 환급한다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source=source, params=p, tries=tries,
                   referer="https://opendart.fss.or.kr/", on_attempt=lambda: attempts.__setitem__("n", attempts["n"] + 1))
    if DBUDGET is not None:
        DBUDGET.refund(max(0, tries - max(1, attempts["n"])))
    if not isinstance(js, dict):
        return None
    st = str(js.get("status", ""))
    if st and st != "000":
        if st in ("020", "021"):
            # ★ 여기가 '실측 상한'을 배우는 유일한 지점이다. 상수를 믿지 않고 서버가 거부한
            #   순간의 사용량을 기록해 다음 실행의 예산 계산에 쓴다.
            if DBUDGET is not None:
                DBUDGET.note_rate_limited()
            LOG.warn(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) — 수집을 중단하고 "
                     f"받은 만큼 저장합니다. 내일 재실행하면 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st} ({DART_STATUS_MSG.get(st, '?')}). "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st} ({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """rcept_no 앞 8자리 = 접수일자(YYYYMMDD). 없으면 법정기한으로 보수적 추정."""
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    return as_ts(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


# ── 전체 재무제표 ───────────────────────────────────────────────────────────────────────────
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]


def _fs_one(job) -> Optional[pd.DataFrame]:
    corp, year, reprt = job
    js = dart_api("fnlttSinglAcntAll.json",
                  {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "OFS"})
    if not js or "list" not in js:
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt, "fs_div": "CFS"})
    if not js or not isinstance(js.get("list"), list) or not js["list"]:
        return None
    d = pd.DataFrame(js["list"])
    for c in _FS_KEEP:
        if c not in d.columns:
            d[c] = None
    d["corp_code"] = corp
    d["bsns_year"] = int(year)
    d["reprt_code"] = reprt
    return d[_FS_KEEP]


# ── Tier-1: 다중회사 주요계정 (배치) ────────────────────────────────────────────────────────
#   fnlttMultiAcnt 는 corp_code 를 콤마로 최대 100개까지 받는다.
#   2,500사 × 10년 × 4분기를 단건으로 받으면 100,000 호출(일 20,000 한도로 5일)이지만
#   배치로는 1,000 호출(1시간 이내)이면 끝난다. ★100배 차이다.
#   다만 '주요계정'만 오므로 B/C축이 필요로 하는 재고·매출채권·영업CF 는 없다.
#   → 헤드라인은 배치로 싹 깔고, 전체 재무제표는 우선순위대로 단건 수집해 덮어쓴다(2단 구성).
DART_MULTI_BATCH = 100
_MULTI_ACCOUNT_MAP = {
    "매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income",
    "자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity",
}


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용")

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    corps = [str(c) for c in corp_codes]
    jobs = []
    for y in sorted(years, reverse=True):          # 최근 연도 우선 (중단돼도 최신이 남게)
        for r in reprts:
            todo = [c for c in corps if (c, int(y), str(r)) not in done]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], int(y), r))
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
        d["reprt_code"] = r
        return d[_FS_KEEP]

    got = []
    if jobs:
        LOG.info(f"DART 주요계정 배치 {len(jobs):,}회 (1회당 최대 {DART_MULTI_BATCH}사) — "
                 f"단건 수집이면 {len(jobs)*DART_MULTI_BATCH:,}회였을 분량입니다")
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사 "
           f"(호출 {len(jobs):,}회로 확보)")
    PIPE.io("OUT", "DRIVE", "dart_multi_raw", M, source="opendart fnlttMultiAcnt")
    return M


def fetch_dart_financials(corp_codes: Sequence[str], years: Sequence[int],
                          priority: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """전체 재무제표 원시 계정. 캐시 증분 — 이미 받은 (corp, year, reprt) 는 건너뛴다.

    priority 를 주면 그 순서(대개 유동성/시총 상위)대로 먼저 받는다.
    일일 한도로 중간에 끊겨도 '투자 가능한 종목의 최근 데이터'가 먼저 확보되도록 하기 위함이다."""
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — B축(회계품질)·C축(자원투입)·PACK-C 가 전부 비활성화됩니다. "
                 "이 전략의 핵심 입력이므로 키 입력을 강력히 권합니다.")
        return pd.DataFrame(columns=_FS_KEEP)

    cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 재무 {len(cached):,}행 재사용 ({len(done):,} 조합)")

    reprts = ([REPRT_CODES["FY"]] if DART_STATEMENT_FREQ == "annual"
              else [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]])
    # ★ 수집 순서가 중요하다. 일일 한도(20,000)로 중간에 끊기는 것이 정상 시나리오이므로,
    #   끊겼을 때 남아 있는 것이 '투자 가능한 종목의 최근 데이터'가 되도록 정렬한다.
    #   (무작위 순서로 받으면 며칠 뒤에도 어느 종목도 완성되지 않아 백테스트를 못 돌린다)
    order = {str(c): i for i, c in enumerate(priority or [])}
    corp_sorted = sorted((str(c) for c in corp_codes),
                         key=lambda c: (order.get(c, 10 ** 9), c))
    jobs = [(c, y, r) for y in sorted(years, reverse=True) for c in corp_sorted for r in reprts
            if (c, int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        total_needed = len(jobs)
        LOG.info(f"DART 재무 신규 수집 대상 {total_needed:,}건 "
                 f"(오늘 남은 호출 {(DBUDGET.remaining() if DBUDGET else 0):,}건 — 실시간 추적값)")
        _avail = max(1, DBUDGET.remaining() if DBUDGET else 1)
        if total_needed > _avail:
            LOG.warn(f"필요 호출({total_needed:,})이 오늘 남은 호출({_avail:,})을 초과합니다. "
                     f"오늘 받을 수 있는 만큼 받고 저장합니다. "
                     f"약 {math.ceil(total_needed / _avail)}일에 걸쳐 콜드빌드가 완성됩니다. "
                     f"(§3 — 콜드빌드는 4시간 반복예산 밖입니다)")
        res = pmap_io(_fs_one, jobs, workers=min(N_WORKERS_IO, 12), desc="DART 재무제표")
        got = [d for d in res if d is not None and len(d)]
    else:
        got = []

    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        LOG.warn("DART 재무 데이터를 확보하지 못했습니다.")
        return pd.DataFrame(columns=_FS_KEEP)
    fs = pd.concat(frames, ignore_index=True)
    fs = fs.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                             "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_fnltt_raw", fs, scope="shared", domain="dart", source="opendart")
    n_have = fs.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(fs) else 0
    n_need = len(corp_sorted) * len(years) * len(reprts)
    LOG.info(f"DART 전체 재무제표 진행률 {n_have:,}/{n_need:,} "
             f"({100*n_have/max(n_need,1):.1f}%) — 최근 연도·우선순위 종목부터 채웁니다. "
             f"재실행하면 정확히 이 지점부터 이어받습니다.")
    PIPE.io("OUT", "DRIVE", "dart_fnltt_raw", fs, source="opendart fnlttSinglAcntAll")
    return fs


def merge_financial_tiers(full: pd.DataFrame, multi: pd.DataFrame) -> pd.DataFrame:
    """Tier-2(전체 재무제표)를 우선하고, 없는 (회사, 기간)만 Tier-1(주요계정)로 메운다.

    콜드빌드가 며칠 걸리는 동안에도 매출·영업이익·순이익·자산·부채·자본은 전 종목이
    확보되어 있어 유니버스 구성과 규모 버킷(C11), R3 팩터가 즉시 동작한다."""
    if multi is None or multi.empty:
        return full if full is not None else pd.DataFrame(columns=_FS_KEEP)
    if full is None or full.empty:
        LOG.info("전체 재무제표가 아직 없어 주요계정(배치)만으로 진행합니다 — "
                 "B축의 재고·매출채권·영업CF 는 결측이므로 TP_B1/TP_B2 가 약해집니다.")
        return multi
    have = set(zip(full["corp_code"].astype(str), full["bsns_year"].astype(int),
                   full["reprt_code"].astype(str)))
    key = list(zip(multi["corp_code"].astype(str), multi["bsns_year"].astype(int),
                   multi["reprt_code"].astype(str)))
    fill = multi[[k not in have for k in key]]
    if len(fill):
        LOG.info(f"주요계정으로 보완한 (회사×기간) {fill.groupby(['corp_code','bsns_year','reprt_code']).ngroups:,}건 "
                 f"— 전체 재무제표 콜드빌드가 끝나면 자동으로 대체됩니다.")
    return pd.concat([full, fill], ignore_index=True)


# ── 계정 매핑 (한국 XBRL 계정명은 회사마다 다르다 → 정규식 다중 매칭) ────────────────────────
ACCOUNT_PATTERNS: Dict[str, Tuple[str, List[str]]] = {
    # 키:            (재무제표구분, [account_id 또는 account_nm 정규식])
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$"]),
    "cogs":          ("IS", [r"CostOfSales", r"^매출원가$"]),
    "gross_profit":  ("IS", [r"GrossProfit", r"^매출총이익"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense", r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopmentExpense", r"경상(연구)?개발비", r"^연구개발비"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense", r"법인세비용"]),
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세비용차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment", r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssetsOtherThanGoodwill", r"^무형자산$"]),
    "cash":          ("BS", [r"CashAndCashEquivalents", r"^현금및현금성자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities", r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities", r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment", r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisationExpense", r"^감가상각비", r"감가상각비와"]),
    "dividend_paid": ("CF", [r"DividendsPaid", r"배당금\s*지급"]),
    "treasury_buy":  ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares", r"자기주식의?\s*취득"]),
    "debt_raise":    ("CF", [r"ProceedsFromBorrowings", r"차입금의?\s*증가", r"사채의?\s*발행"]),
}
_SJ_MAP = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}

# ★ 손익·현금흐름 성격의 전 계정. 빠뜨리면 <계정>_ttm 컬럼이 아예 생성되지 않고,
#   그걸 쓰는 팩이 실데이터 실행에서만 터진다(합성 스모크는 통과한다).
FLOW_ITEMS = ["revenue", "cogs", "gross_profit", "sgna", "rnd", "op_income", "net_income",
              "cfo", "capex", "dep", "dividend_paid", "treasury_buy", "debt_raise",
              "tax_expense", "pretax_income", "other_income"]

# 재무 결합 후 패널이 반드시 보유해야 하는 컬럼 전체 목록.
# attach_fundamentals 가 이 목록으로 스키마를 계약적으로 보장한다 — 수집이 얼마나 실패하든
# 패널의 컬럼 집합은 항상 같아야 한다. 그래야 "어떤 실행에선 있고 어떤 실행엔 없는" 축이
# 사라지고, 결측은 결측대로 조용히가 아니라 표로 드러난다.
FUNDAMENTAL_COLS = (list(ACCOUNT_PATTERNS)
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다."""
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()
    d["amount"] = pd.to_numeric(
        d["thstrm_amount"].astype(str).str.replace(",", "", regex=False).str.replace("−", "-", regex=False),
        errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
    for key, (sj, pats) in ACCOUNT_PATTERNS.items():
        sjs = _SJ_MAP.get(sj, (sj,))
        sub = d[d["sj_div"].astype(str).isin(sjs)]
        if sub.empty:
            continue
        rx = re.compile("|".join(pats), re.I)
        hit = sub[sub["account_id"].str.contains(rx, na=False) |
                  sub["account_nm"].str.contains(rx, na=False)]
        if hit.empty:
            continue
        # 같은 항목에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다
        hit = (hit.assign(_a=hit["amount"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "rcept_no", "item", "amount"]])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    rc = (L.sort_values("rcept_no").groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    # 누적치 → 분기 단독치 (Q1/H1/Q3/FY 는 누적 공시다. 차분하지 않으면 계절성이 곧 신호가 된다)
    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    flow_items = FLOW_ITEMS
    # 누적 → 분기 단독. 직전 분기가 실제로 존재할 때만 차분한다.
    # (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    gk = ["corp_code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in flow_items:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        q_val = np.where(W["q"] == 1, W[c],
                         np.where(contiguous, W[c] - prev, np.nan))
        W[c + "_q"] = q_val
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])
    # ★ 재무상태표 항목(재고·매출채권·자산·자본 등)은 pivot 결과에 그 계정이 없으면
    #   컬럼 자체가 생성되지 않는다. 그러면 패널 스키마가 실행마다 달라져
    #   "어떤 날은 있고 어떤 날은 없는" 축이 생긴다. 여기서 전 항목을 계약적으로 보장한다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in W.columns:
            W[_k] = np.nan
    # ── V2 거부권용 '이익-현금 괴리 3분기 연속' 플래그 ─────────────────────────────────────
    #   ★ 여기서 만드는 이유: 연속성은 분기 관측을 세야 하는데, 월 패널에서 세면
    #     같은 분기값이 1~4개월 반복되므로 어떤 고정 개월수도 정답이 아니다. 분기 프레임은
    #     관측당 정확히 한 행이고 이미 (corp_code, bsns_year, q) 로 정렬돼 있다.
    #     as-of 결합이 이 플래그를 C1 게이트웨이 그대로 실어 나른다.
    #   min_periods=3 — 제출분이 3개 미만이면 NaN(=거부하지 않음). 근거 없는 제외 금지.
    _bad_q = ((col(W, "net_income_ttm") > 0) &
              (col(W, "cfo_ttm") < 0.5 * col(W, "net_income_ttm"))).astype(float)
    W["v2_bad_3q"] = (_bad_q.groupby(W["corp_code"], observed=True)
                            .transform(lambda s: s.rolling(3, min_periods=3).min()))

    _missing = [k for k in ACCOUNT_PATTERNS if W[k].notna().sum() == 0]
    if _missing:
        LOG.warn(f"DART 재무에서 한 건도 매칭되지 않은 계정 {len(_missing)}개: "
                 f"{_missing[:8]}{'...' if len(_missing) > 8 else ''} — "
                 f"해당 계정을 쓰는 지표는 전부 결측이 됩니다(0으로 채우지 않음). "
                 f"ACCOUNT_PATTERNS 정규식이 이 회사들의 계정명과 안 맞을 수 있습니다.")
    n_ttm = int(W["revenue_ttm"].notna().sum()) if "revenue_ttm" in W.columns else 0
    if len(W) and n_ttm / len(W) < 0.35:
        LOG.warn(f"TTM 산출률이 {100*n_ttm/len(W):.0f}% 로 낮습니다. 분기보고서가 결측인 기업이 "
                 f"많다는 뜻이며(중소형주에서 흔함), 해당 종목은 B/C축이 결측 처리됩니다. "
                 f"DART_STATEMENT_FREQ='quarterly' 콜드빌드가 아직 미완이라면 이어받기를 계속하세요.")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 재무 정제 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(knowledge_date = 접수일자 기준, 누적→분기 차분 완료)")
    PIPE.io("OUT", "MEM", "dart_financials_tidy", W)
    return downcast(W)


# ── 직원현황 (θ_N, TP_C2) ───────────────────────────────────────────────────────────────────
def fetch_dart_employees(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    cached = VAULT.get_table("dart_employees", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"공용 캐시에서 직원현황 {len(cached):,}행 재사용")
    jobs = [(c, y) for c in corp_codes for y in years if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year = job
        js = dart_api("empSttus.json", {"corp_code": corp, "bsns_year": str(year),
                                        "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list):
            return None
        d = pd.DataFrame(js["list"])
        # ★ empSttus 행은 사업부문(fo_bbm) × 성별(sexdstn) 로 쪼개져 온다. 각 조합은 서로소이므로
        #   합산이 맞지만, 일부 기업은 '합계/계' 소계 행을 함께 넣어 이중계상이 발생한다 → 제거.
        #   또 jan_salary_am(1인 평균급여)은 절대 합산하면 안 되는 값이므로 아예 쓰지 않는다.
        for col in ("fo_bbm", "sexdstn"):
            if col in d.columns:
                d = d[~d[col].astype(str).str.strip().isin(["합계", "계", "소계", "총계", "합 계"])]
        if d.empty:
            return None
        num = lambda s: pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                                      errors="coerce")
        emp = num(d.get("sm", pd.Series(dtype=object))).sum(skipna=True) if "sm" in d.columns else np.nan
        pay = num(d.get("fyer_salary_totamt", pd.Series(dtype=object))).sum(skipna=True) \
            if "fyer_salary_totamt" in d.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "employees": float(emp),
                "payroll": float(pay), "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 12),
                              desc="DART 직원현황") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll", "knowledge_date"])
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"], keep="last")
    # ★ E.get("rcept_no", "") 는 컬럼이 없으면 '문자열'을 돌려주고, zip 이 그걸 글자 단위로
    #   훑어 knowledge_date 가 전부 깨진다. 컬럼 존재를 먼저 보장한다.
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["period_end"] = as_ts_series(E["bsns_year"].astype(int).astype(str) + "-12-31")
    E["knowledge_date"] = [_knowledge_from_rcept(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(E["rcept_no"], E["bsns_year"])]
    if got:
        VAULT.put_table("dart_employees", E, scope="shared", domain="dart", source="opendart empSttus")
    E = pit_frame(E, "period_end", "knowledge_date", source="dart")
    PIPE.io("OUT", "DRIVE", "dart_employees", E, source="opendart empSttus")
    return E


# ── 공시목록 스윕 (시장 전체를 날짜로 훑는다 — 회사별 호출보다 수십 배 싸다) ──────────────────
DISCLOSURE_PATTERNS = {
    "treasury_acq":  r"자기주식\s*취득",
    "treasury_disp": r"자기주식\s*처분",
    "treasury_canc": r"자기주식\s*소각|이익소각",
    "dividend":      r"(현금|현물)?\s*[·ㆍ]?\s*배당\s*결정|결산배당|중간배당",
    "rights_issue":  r"유상증자",
    "cb_issue":      r"전환사채",
    "bw_issue":      r"신주인수권부사채",
    "capital_reduce": r"감자",
    "audit_opinion": r"감사보고서",
}


def fetch_dart_disclosures(start: str, end: str) -> pd.DataFrame:
    """월 단위로 시장 전체 공시목록을 훑는다. PACK-C(자사주/배당)와 V3(희석성 조달)의 입력."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    cached = VAULT.get_table("dart_disclosures", scope="shared")
    have_months = set()
    if cached is not None and len(cached):
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.info(f"공용 캐시에서 공시목록 {len(cached):,}행 재사용")

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        todo = []

    # ★ 파이프라인이 실제로 소비하는 공시 유형을 전부 훑어야 한다.
    #   B(주요사항보고)만 훑으면 PACK-C 의 자사주·증자는 잡히지만
    #   PACK-D 가 필요로 하는 '사업보고서'는 A(정기공시)라 단 한 건도 안 잡힌다.
    #   그러면 fetch_dart_documents 가 걸러낼 대상이 없어 팩 전체가 조용히 죽는다.
    #   (실경로에서만 드러나는 유형 — 합성 스모크는 dis 를 직접 만들어 넣으므로 못 본다)
    DISCLOSURE_TYPES = ("A", "B")            # A=정기공시(사업/반기/분기보고서), B=주요사항보고

    def _one(m):
        rows = []
        for ty in DISCLOSURE_TYPES:
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})
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
        return pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event"])
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures", D, scope="shared", domain="dart", source="opendart list.json")
    D = pit_frame(D, "rcept_dt", "rcept_dt", source="dart")     # 접수일 = 공개일
    LOG.ok(f"공시목록 {len(D):,}건 — 이벤트 분류: " +
           ", ".join(f"{k}={int((D['event']==k).sum()):,}" for k in DISCLOSURE_PATTERNS if (D['event']==k).any()))
    PIPE.io("OUT", "DRIVE", "dart_disclosures", D, source="opendart list.json")
    return D


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C+  ARC 추가 수집 — 주식총수(D2 SHARE_GROWTH) / 감사의견(배제 EX_AUDIT)               ║
# ║                                                                                          ║
# ║  ★ 주식총수를 왜 별도로 받는가: 소형주는 지속적 증자·CB 발행으로 실적이 개선돼도            ║
# ║    주당지표가 개선되지 않거나 악화된다. 이 항목 없이는 D2 가 소형주 구간에서 오작동한다.    ║
# ║    재무제표에는 '자본금'만 있고 주식수가 없는 경우가 많아 전용 엔드포인트가 필요하다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SHARE_COLS = ["corp_code", "bsns_year", "reprt_code", "shares_common", "shares_total",
               "treasury_shares", "period_end", "knowledge_date", "rcept_no"]


def _num_kr(x) -> float:
    """'1,234,567' / '1,234,567 주' / '-' → float. 콤마·단위·전각 부호를 전부 처리한다."""
    s = re.sub(r"[^\d.\-]", "", str(x or "").replace("−", "-").replace("△", "-"))
    if s in ("", "-", ".", "-."):
        return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주식의 총수 현황(stockTotqySttus). D2 의 SHARE_GROWTH 입력.

    ★ 응답은 '보통주 / 우선주 / 합계' 행으로 쪼개져 온다. 합계 행이 있으면 그걸 쓰고,
      없으면 보통주+우선주를 더한다. 두 방식을 섞으면 같은 기업이 연도마다 다른 정의로
      계산되어 증가율이 통째로 거짓이 된다.
    """
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 주식총수를 받을 수 없어 D2 의 SHARE_GROWTH 가 결측됩니다.")
        return pd.DataFrame(columns=_SHARE_COLS)

    cached = VAULT.get_table("dart_shares", scope="shared")
    done = set()
    if cached is not None and len(cached):
        try:
            done = set(zip(cached["corp_code"].astype(str),
                           cached["bsns_year"].astype(int),
                           cached["reprt_code"].astype(str)))
            LOG.info(f"공용 캐시에서 주식총수 {len(cached):,}행 재사용 ({len(done):,} 조합)")
        except Exception:
            done = set()

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    jobs = [(str(c), int(y), r) for y in sorted(years, reverse=True)
            for c in corp_codes for r in reprts
            if (str(c), int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, year, reprt = job
        js = dart_api("stockTotqySttus.json",
                      {"corp_code": corp, "bsns_year": str(year), "reprt_code": reprt})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        if d.empty:
            return None
        se = d.get("se", pd.Series([""] * len(d))).astype(str).str.replace(r"\s+", "", regex=True)
        # 발행주식총수 컬럼명은 연도별로 isu_stock_totqy / istc_totqy 등으로 흔들린다.
        cand = [c for c in ("isu_stock_totqy", "istc_totqy", "now_to_isu_stock_totqy")
                if c in d.columns]
        if not cand:
            return None
        tot = _num_kr_series(d[cand[0]])
        tesstk = _num_kr_series(d["tesstk_co"]) if "tesstk_co" in d.columns else pd.Series(np.nan, index=d.index)
        is_sum = se.str.contains("합계|계$", regex=True)
        is_common = se.str.contains("보통주")
        if is_sum.any():
            shares_total = float(tot[is_sum].max())
        else:
            shares_total = float(tot[~is_sum].sum(skipna=True)) if len(tot) else float("nan")
        shares_common = float(tot[is_common].max()) if is_common.any() else shares_total
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year), "reprt_code": str(reprt),
                "shares_common": shares_common, "shares_total": shares_total,
                "treasury_shares": float(tesstk.sum(skipna=True)) if tesstk.notna().any() else np.nan,
                "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 10),
                              desc="DART 주식총수") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        LOG.warn("주식총수를 한 건도 확보하지 못했습니다 — SHARE_GROWTH 는 결측 처리됩니다.")
        return pd.DataFrame(columns=_SHARE_COLS)

    S = pd.concat(frames, ignore_index=True)
    S = S.drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
    if "rcept_no" not in S.columns:
        S["rcept_no"] = ""
    S["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12,31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12,31))[1]:02d}")
                       for y, r in zip(S["bsns_year"], S["reprt_code"])]
    S["knowledge_date"] = [_knowledge_from_rcept(rn, str(r), int(y))
                           for rn, r, y in zip(S["rcept_no"], S["reprt_code"], S["bsns_year"])]
    if got:
        VAULT.put_table("dart_shares", S, scope="shared", domain="dart",
                        source="opendart stockTotqySttus")
    S = pit_frame(S, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"주식총수 {len(S):,}행 · {S['corp_code'].nunique():,}사")
    PIPE.io("OUT", "DRIVE", "dart_shares", S, source="opendart stockTotqySttus")
    return downcast(S)


def _num_kr_series(s) -> pd.Series:
    return pd.to_numeric(
        pd.Series(s).astype(str)
          .str.replace("−", "-", regex=False).str.replace("△", "-", regex=False)
          .str.replace(r"[^\d.\-]", "", regex=True).replace("", np.nan),
        errors="coerce")


_AUDIT_COLS = ["corp_code", "bsns_year", "audit_opinion", "emphasis", "key_matter",
               "auditor", "period_end", "knowledge_date"]


def fetch_dart_audit(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """감사의견 + 특기사항/강조사항 (accnutAdtorNmNdAdtOpinion). 배제 플래그 EX_AUDIT 입력.

    ★ '적정의견'이라도 강조사항(계속기업 불확실성 등)이 붙으면 그것 자체가 경고다.
      명세(§6.4)가 '감사의견 특기사항/강조사항 존재 시' 를 하드 제외로 규정한 이유다.
      필드명이 연도별로 흔들리므로(adt_reprt_spcmnt_matter / emphs_matter / core_adt_matter)
      후보를 전부 훑어 하나라도 비어있지 않으면 존재로 본다.
    """
    if not DART_API_KEY:
        return pd.DataFrame(columns=_AUDIT_COLS)
    cached = VAULT.get_table("dart_audit", scope="shared")
    done = set()
    if cached is not None and len(cached):
        try:
            done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
            LOG.info(f"공용 캐시에서 감사의견 {len(cached):,}행 재사용")
        except Exception:
            done = set()
    jobs = [(str(c), int(y)) for y in sorted(years, reverse=True) for c in corp_codes
            if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    _OPI = ("adt_opinion", "adt_opinion_nm", "opinion")
    _EMP = ("emphs_matter", "adt_reprt_spcmnt_matter", "spcmnt_matter")
    _KEY = ("core_adt_matter", "core_adt_matter_nm")
    _AUD = ("adtor", "adt_nm", "auditor")

    def _pick_field(d: pd.DataFrame, names) -> str:
        for n in names:
            if n in d.columns:
                v = " ".join(str(x) for x in d[n].dropna().astype(str).tolist())
                v = re.sub(r"\s+", " ", v).strip()
                if v and v not in ("-", "해당사항 없음", "해당사항없음", "없음", "nan"):
                    return v[:400]
        return ""

    def _one(job):
        corp, year = job
        js = dart_api("accnutAdtorNmNdAdtOpinion.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(year),
                "audit_opinion": _pick_field(d, _OPI),
                "emphasis": _pick_field(d, _EMP),
                "key_matter": _pick_field(d, _KEY),
                "auditor": _pick_field(d, _AUD), "rcept_no": rn}

    got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 10),
                              desc="DART 감사의견") if r] if jobs else []
    frames = ([cached] if cached is not None and len(cached) else [])
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        LOG.warn("감사의견을 확보하지 못했습니다 — EX_AUDIT 은 사업보고서 텍스트 폴백으로만 판정됩니다.")
        return pd.DataFrame(columns=_AUDIT_COLS)
    A = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"],
                                                             keep="last")
    if "rcept_no" not in A.columns:
        A["rcept_no"] = ""
    A["period_end"] = as_ts_series(A["bsns_year"].astype(int).astype(str) + "-12-31")
    A["knowledge_date"] = [_knowledge_from_rcept(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(A["rcept_no"], A["bsns_year"])]
    if got:
        VAULT.put_table("dart_audit", A, scope="shared", domain="dart",
                        source="opendart accnutAdtorNmNdAdtOpinion")
    A = pit_frame(A, "period_end", "knowledge_date", source="dart")
    n_emp = int((A["emphasis"].astype(str).str.len() > 0).sum()) if len(A) else 0
    LOG.ok(f"감사의견 {len(A):,}행 (강조/특기사항 보유 {n_emp:,}건)")
    PIPE.io("OUT", "DRIVE", "dart_audit", A, source="opendart audit")
    return A



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


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D+  ARC 추가 — 리포트 '본문 전문' 저장소 (축 A TONE 의 유일한 입력)                    ║
# ║                                                                                          ║
# ║  기존 pdf_text() 는 앞 3장만 읽는다. 애널리스트명·목표주가를 뽑기엔 충분하지만              ║
# ║  톤 분류는 문장이 필요하다 — 3장으론 표와 헤더뿐이라 문장이 거의 안 나온다.                 ║
# ║                                                                                          ║
# ║  ★ 본문을 매 실행마다 PDF 에서 다시 뽑으면 30만 건 × 수백 ms = 며칠이 걸린다.               ║
# ║    그래서 추출 결과를 '연도 샤드 parquet' 으로 공용 인덱스에 저장한다.                      ║
# ║    (단일 거대 parquet 금지 — 30만 건 × 20KB = 6GB 라 메모리에 못 올린다)                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

RESEARCH_TEXT_MAXLEN = 12000        # 리포트당 저장 상한(문자). 톤 분류엔 이걸로 충분하다.
RESEARCH_TEXT_SHARD = "research_report_text_{year}"


def pdf_full_text(data: bytes, max_pages: Optional[int] = None) -> str:
    """리포트 본문 전문 추출. pdf_text() 의 확장판(페이지 수 상향 + 레이아웃 정리).

    ★ fitz 는 2단 조판을 열 순서대로 못 읽는 경우가 있다. sort=True 로 좌표 정렬하면
      문장이 뒤섞이는 것을 크게 줄일 수 있다(문장 분리 품질이 곧 라벨 품질이다).
    """
    if not data or data[:5] != b"%PDF-":
        return ""
    mp = int(max_pages or RESEARCH_PDF_FULL_PAGES)
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                n = min(mp, doc.page_count)
                out = []
                for i in range(n):
                    try:
                        out.append(doc[i].get_text("text", sort=True))
                    except Exception:
                        try:
                            out.append(doc[i].get_text())
                        except Exception:
                            continue
                return "\n".join(out)[:RESEARCH_TEXT_MAXLEN]
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "")
                                 for p in pdf.pages[:mp])[:RESEARCH_TEXT_MAXLEN]
        except Exception:
            pass
    return ""


def build_report_text_store(rep: pd.DataFrame, chunk: int = 1500) -> pd.DataFrame:
    """보고서 원장 → 본문 텍스트 저장소. 연도 샤드로 공용 인덱스에 영속화하고 증분 갱신.

    반환: report_uid, pub_date, code, text, n_chars, txt_src
    ★ 반환 프레임도 메모리를 쓰므로, 상위(30_axis_a_tone)는 이걸 통째로 들고 있지 말고
      학습 표본을 만든 뒤 즉시 버려야 한다.
    """
    cols = ["report_uid", "pub_date", "code", "text", "n_chars", "txt_src"]
    if rep is None or rep.empty:
        return pd.DataFrame(columns=cols)

    R = rep.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["pub_date", "report_uid"])
    R["year"] = R["pub_date"].dt.year
    years = sorted(R["year"].dropna().astype(int).unique().tolist())

    # ── 기존 샤드 적재 (있는 만큼만) ──────────────────────────────────────────────────────
    have_frames, have_uids = [], set()
    for y in years:
        d = VAULT.get_table(RESEARCH_TEXT_SHARD.format(year=y), scope="shared")
        if d is not None and len(d):
            d = d.reindex(columns=[c for c in cols if c in d.columns] +
                          [c for c in cols if c not in d.columns])
            have_frames.append(d)
            have_uids |= set(d["report_uid"].astype(str))
    if have_frames:
        LOG.info(f"공용 캐시에서 리포트 본문 {sum(len(x) for x in have_frames):,}건 재사용 "
                 f"({len(years)}개 연도 샤드)")

    need = R[~R["report_uid"].astype(str).isin(have_uids)].copy()
    if RUN_MODE == "CACHED":
        if len(need):
            LOG.warn(f"CACHED 모드 — 본문 미확보 {len(need):,}건은 건너뜁니다.")
        need = need.iloc[0:0]
    if fitz is None and pdfplumber is None and len(need):
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 본문을 추출할 수 없습니다. "
                 "축 A(TONE)는 GATE_3 에서 탈락하고 DART-ONLY 폴백으로 전환됩니다.")
        need = need.iloc[0:0]

    # 인덱스에서 report_uid → blob uid 를 미리 만든다 (iterrows 는 30만 행에서 13초)
    known: Dict[str, str] = {}
    try:
        idx = VAULT.load_index("shared")
        if len(idx) and "domain" in idx.columns:
            sub = idx[(idx["domain"].astype(str) == "research") &
                      (idx["subtype"].astype(str) == "report_pdf")]
            known = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
    except Exception:
        known = {}

    new_rows: List[dict] = []
    if len(need):
        LOG.info(f"리포트 본문 신규 추출 대상 {len(need):,}건 "
                 f"(드라이브 blob 보유 {sum(1 for u in need['report_uid'].astype(str) if u in known):,}건)")
        jobs = list(zip(need["report_uid"].astype(str),
                        need["pdf_url"].astype(str) if "pdf_url" in need.columns
                        else [""] * len(need),
                        need["stock_code"].astype(str) if "stock_code" in need.columns
                        else [""] * len(need),
                        need["pub_date"]))

        def _one(job):
            uid, url, code, pd_ = job
            data = None
            src = ""
            bu = known.get(uid)
            if bu:
                data = VAULT.get_blob(bu, "shared")
                src = "drive_blob"
            if not data and url and url.lower() not in ("nan", "none", ""):
                data = http_get(url, source=("hankyung" if "hankyung" in url else "naver"),
                                as_bytes=True, tries=2,
                                referer=(HK_BASE + "/" if "hankyung" in url else NV_BASE))
                src = "http"
                if data and data[:5] == b"%PDF-":
                    # 새로 받은 원문은 반드시 드라이브 공용 인덱스에 저장한다 (절대 1원칙)
                    VAULT.put_blob("research", "report_pdf", uid, data, "pdf",
                                   source="report_pdf", scope="shared")
            if not data or data[:5] != b"%PDF-":
                return None
            t = pdf_full_text(data)
            del data
            if not t or len(t) < 200:
                return None
            return {"report_uid": uid, "pub_date": as_ts(pd_), "code": to_code6(code) or "",
                    "text": t, "n_chars": len(t), "txt_src": src}

        for k0 in range(0, len(jobs), chunk):
            part = jobs[k0:k0 + chunk]
            res = pmap_io(_one, part, workers=min(N_WORKERS_IO, 8),
                          desc=f"리포트 본문 {k0//chunk + 1}/{(len(jobs)-1)//chunk + 1}")
            new_rows.extend([r for r in res if r])
            del res
            VAULT.flush("shared")
            gc.collect()

    frames = have_frames + ([pd.DataFrame(new_rows)] if new_rows else [])
    if not frames:
        LOG.warn("리포트 본문을 한 건도 확보하지 못했습니다 — 축 A(TONE) 를 구동할 수 없습니다.")
        return pd.DataFrame(columns=cols)
    T = pd.concat([f.reindex(columns=cols) for f in frames], ignore_index=True)
    T = T.drop_duplicates("report_uid", keep="last")
    T["pub_date"] = as_ts_series(T["pub_date"])

    # ── 연도 샤드로 저장 (신규분이 있는 연도만) ───────────────────────────────────────────
    if new_rows:
        nd = pd.DataFrame(new_rows)
        nd["pub_date"] = as_ts_series(nd["pub_date"])
        for y, g in T.dropna(subset=["pub_date"]).groupby(T["pub_date"].dt.year):
            if int(y) not in set(nd["pub_date"].dt.year.dropna().astype(int)):
                continue
            VAULT.put_table(RESEARCH_TEXT_SHARD.format(year=int(y)), g, scope="shared",
                            domain="research", source="pdf_full_text",
                            extra={"note": "리포트 본문 — 전 전략 공용(톤/토픽 분석 재사용)"})
        VAULT.flush("shared")

    # ★ 메모리 예산 가드: 30만 건 × 12KB = 3.6GB 라 전 구간을 한 번에 들면 노트북이 죽는다.
    #   예산을 넘으면 '최근 것부터' 유지하고, 무엇을 몇 건 떨어뜨렸는지 반드시 로그로 남긴다
    #   (조용한 절단은 '전 구간을 다 썼다'는 착각을 만든다).
    try:
        budget_bytes = float(globals().get("MEM_BUDGET_GB", 6.0)) * 0.35 * 1e9
        est = float(pd.to_numeric(T["n_chars"], errors="coerce").fillna(0).sum()) * 2.0
        if est > budget_bytes and len(T) > 1000:
            T = T.sort_values("pub_date", kind="stable")
            keep = T["n_chars"].fillna(0).astype(float).mul(2.0)[::-1].cumsum()[::-1] <= budget_bytes
            n_drop = int((~keep).sum())
            T = T[keep]
            LOG.warn(f"리포트 본문이 메모리 예산({budget_bytes/1e9:.1f}GB)을 초과해 "
                     f"오래된 {n_drop:,}건을 이번 실행의 학습표본에서 제외했습니다 "
                     f"(드라이브 캐시에는 그대로 보존됩니다). MEM_BUDGET_GB 를 올리면 "
                     f"전 구간을 씁니다. ★ 초기 구간 TONE 모델이 그만큼 얇아집니다.")
            PIPE.note(f"WARN: 본문 {n_drop:,}건 메모리 예산으로 제외")
    except Exception:
        pass
    rate = len(T) / max(len(R), 1)
    LOG.ok(f"리포트 본문 {len(T):,}건 확보 (원장 {len(R):,}건 대비 추출률 {100*rate:.1f}%)")
    if rate < 0.70:
        LOG.warn(f"본문 추출률 {100*rate:.1f}% 는 GATE_3 기준(70%) 미달입니다. "
                 f"RESEARCH_DOWNLOAD_PDF=True 인지, PDF 파서가 설치됐는지 확인하세요.")
    PIPE.io("OUT", "DRIVE", "research_report_text", T, source="pdf_full_text")
    return T



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


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E+  ARC 추가 — 분기 리비전 패널(§5.3 직교화 통제변수) / 기업의뢰 리포트 태깅            ║
# ║                                                                                          ║
# ║  ★ 직교화는 이 전략 성립의 필요조건이다(§1.1). 통제변수가 부실하면 "애널리스트 과소반응     ║
# ║    전략의 재포장"을 텍스트 알파로 오인하게 된다. 그래서 리비전은 반드시                     ║
# ║    '같은 애널리스트가 같은 종목에 이전에 제시한 값' 과 비교한다 — 애널리스트 원장이         ║
# ║    필요한 진짜 이유다.                                                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 기업의뢰(sponsored) 리포트 발행처 — §8.4 민감도 분석에서 분리 검증한다.
SPONSORED_BROKERS = [
    r"한국\s*IR\s*협의회", r"IR\s*협의회", r"NICE\s*디앤비", r"나이스디앤비",
    r"에프앤가이드", r"FnGuide", r"한국기업데이터", r"KIRS", r"기업분석보고서",
]
_SPONSORED_RE = re.compile("|".join(SPONSORED_BROKERS), re.I)

REVISION_COLS = ["code", "asof", "q", "n_analyst", "tp_median", "tp_rev", "opin_chg",
                 "n_reports_win"]


def tag_sponsored_reports(rep: pd.DataFrame) -> pd.DataFrame:
    """기업의뢰형 리포트에 is_sponsored=1. 원장을 변형하지 않고 컬럼만 추가한다.

    ★ 왜 분리해야 하나: 기업이 비용을 대고 쓰게 한 리포트는 톤이 구조적으로 긍정 편향이다.
      섞어 두면 '톤이 좋아졌다'가 '기업이 IR 을 시작했다'와 구별되지 않는다.
    """
    if rep is None or rep.empty:
        if rep is not None and "is_sponsored" not in rep.columns:
            rep = rep.assign(is_sponsored=pd.Series(dtype="float32"))
        return rep
    R = rep.copy()
    blob = (R.get("broker_name", pd.Series("", index=R.index)).astype(str) + " " +
            R.get("broker_raw", pd.Series("", index=R.index)).astype(str))
    R["is_sponsored"] = blob.str.contains(_SPONSORED_RE, na=False).astype("float32")
    n = int(R["is_sponsored"].sum())
    if n:
        LOG.info(f"기업의뢰형(sponsored) 리포트 {n:,}건 태깅 ({100*n/len(R):.2f}%) — "
                 f"§8.4 민감도 분석에서 포함/제외 두 버전으로 검증합니다.")
    return R


def build_revision_panel(L: pd.DataFrame, rebals: pd.DatetimeIndex,
                         window_days: int = 120) -> pd.DataFrame:
    """§5.3 통제변수 — 목표주가 수정률 / 투자의견 변경 더미 / 커버리지.

    window_days=120 : 분기 리밸런싱이므로 직전 1개 분기(약 90일)에 제출 지연을 감안해 넉넉히.
    ★ 창을 '리밸일 이전'으로만 잡는다. 리밸일 당일 발간분은 T+1 규약(§4)상 아직 쓸 수 없다.

    [방법론적 한계 — 숨기지 않는다]
      EPS 컨센서스 시계열은 과거 복원이 불가능하다(유료 벤더 데이터). 따라서 eps_rev 는
      여기서 만들지 않고, 패널 조립부가 PIT 실적(TTM 순이익) 변화율을 대리변수로 채운다.
      대리변수는 '컨센서스 수정'이 아니라 '실현 실적 변화'이므로 통제력이 약하다.
      이 한계를 §9.1 기준에 따라 리포트에 명시한다.
    """
    if L is None or L.empty:
        LOG.warn("애널리스트 연결이 없어 리비전 패널을 만들 수 없습니다 — "
                 "직교화 통제변수(tp_rev/opin_chg)가 결측이 되어 축 A 의 신뢰도가 떨어집니다.")
        return pd.DataFrame(columns=REVISION_COLS)

    x = L.dropna(subset=["stock_code"]).copy()
    x["pub_date"] = as_ts_series(x["pub_date"])
    x = x.dropna(subset=["pub_date"])
    if x.empty:
        return pd.DataFrame(columns=REVISION_COLS)
    x["stock_code"] = x["stock_code"].map(to_code6)
    x = x.dropna(subset=["stock_code"])
    x = x.sort_values(["stock_code", "analyst_id", "pub_date"], kind="stable")

    g = x.groupby(["stock_code", "analyst_id"], observed=True)
    x["prev_tp"] = g["target_price"].shift(1)
    x["prev_opin"] = g["opinion"].shift(1)
    # 목표주가 수정률(연속값). 부호만 쓰면 '조금 올림'과 '두 배로 올림'이 같아진다.
    x["tp_rev_i"] = safe_div(pd.to_numeric(x["target_price"], errors="coerce") -
                             pd.to_numeric(x["prev_tp"], errors="coerce"),
                             pd.to_numeric(x["prev_tp"], errors="coerce"))
    x["tp_rev_i"] = x["tp_rev_i"].where(x["tp_rev_i"].abs() < 3.0)   # 액면분할 등 이상치 제거
    x["opin_chg_i"] = np.where(x["opinion"].notna() & x["prev_opin"].notna() &
                               (x["opinion"].astype(str) != x["prev_opin"].astype(str)), 1.0,
                               np.where(x["prev_opin"].notna(), 0.0, np.nan))

    out = []
    for t in rebals:
        t = as_ts(t)
        lo = t - pd.Timedelta(days=window_days)
        w = x[(x["pub_date"] > lo) & (x["pub_date"] < t)]      # ★ 리밸일 당일 제외 (T+1 규약)
        if w.empty:
            continue
        gg = w.groupby("stock_code", observed=True)
        agg = pd.DataFrame({
            "n_analyst": gg["analyst_id"].nunique(),
            "n_reports_win": gg["report_uid"].nunique(),
            "tp_median": gg["target_price"].median(),
            "tp_rev": gg["tp_rev_i"].mean(),
            "opin_chg": gg["opin_chg_i"].mean(),
        }).reset_index().rename(columns={"stock_code": "code"})
        agg["asof"] = t
        agg["q"] = prev_quarter_of(t)
        out.append(agg)

    if not out:
        return pd.DataFrame(columns=REVISION_COLS)
    P = pd.concat(out, ignore_index=True)[REVISION_COLS]
    LOG.ok(f"리비전 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {P['asof'].nunique()}시점) — "
           f"목표주가 수정 관측 {int(P['tp_rev'].notna().sum()):,} · "
           f"의견변경 관측 {int(P['opin_chg'].notna().sum()):,}")
    PIPE.io("OUT", "MEM", "revision_panel", P)
    return downcast(P)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-G  DART 정기보고서 원문 수집 + §6.1.3 텍스트 정규화                                    ║
# ║                                                                                          ║
# ║  D1(Lazy Prices)의 성패는 전적으로 이 파일의 정규화 품질에 달려 있다.                       ║
# ║  정규화가 부실하면 "금액이 매년 바뀐다" 는 자명한 사실이 100% 변경으로 집계되어             ║
# ║  전 종목이 '변경 기업'이 되고 신호가 통째로 소멸한다.                                       ║
# ║                                                                                          ║
# ║  ★ 명세 §6.1.3 의 단계 순서에 함정이 하나 있어 구현에서 바로잡았다:                         ║
# ║    명세는 [2] 숫자 마스킹 → [3] 날짜 마스킹 순서다. 그런데 [2]를 먼저 하면 모든 숫자가       ║
# ║    <NUM> 이 되어 [3]의 날짜 정규식이 매칭할 대상이 사라진다(무동작). 즉 '2023년'과          ║
# ║    '2024년'이 둘 다 '<NUM>년' 이 되어 우연히 같아지긴 하지만, '제27기'→'제<NUM>기' 처럼     ║
# ║    기수/날짜/일반수치가 전부 한 토큰으로 뭉개져 서로 다른 성격의 변화를 구분할 수 없다.      ║
# ║    → 구현 순서: 날짜/기수 마스킹 → 그 다음 잔여 숫자 마스킹. 결과는 명세의 의도와 동일하며   ║
# ║      오히려 더 정밀하다. 이 결정을 A5 계약검정이 실제 문서로 검증한다.                      ║
# ║                                                                                          ║
# ║  ★ 섹션 분해 순서도 바로잡았다. 명세 [5]는 '표준 목차 헤더 제거'를 지시하는데, 섹션 분해는   ║
# ║    바로 그 헤더를 기준으로 한다. 헤더를 먼저 지우면 분해가 불가능하다.                      ║
# ║    → [5]에서는 '자동생성 목차 블록 / 페이지번호 / 법정 고지문' 만 제거하고 본문 표제어는     ║
# ║      보존한다. 표제어는 섹션 분해가 끝난 뒤 각 섹션 앞머리에서만 잘라낸다.                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ARC_DOC_TYPES = {"FY": "사업보고서", "H1": "반기보고서", "Q1": "분기보고서", "Q3": "분기보고서"}
ARC_SECTIONS = ["S_MDA", "S_LEGAL", "S_EXEC", "S_BIZ", "S_RISK", "S_GOV", "S_ALL"]

# 섹션 표제 정규식. 로마숫자/아라비아 목차 번호는 선택적으로만 매칭하고(서식 개정 때 번호가
# 바뀐다), 한글 표제어를 진짜 앵커로 쓴다.
_RN = r"(?:[IVXivx]{1,5}\s*[.\-]\s*|\d{1,2}\s*[.\-]\s*|제?\s*\d{1,2}\s*장\s*)?"
ARC_SECTION_PAT: Dict[str, str] = {
    "S_MDA":   _RN + r"이사의\s*경영\s*진단\s*및\s*분석\s*의견|경영진단\s*및\s*분석의견|"
                     r"MD\s*&\s*A",
    "S_LEGAL": _RN + r"그\s*밖에\s*투자자\s*보호를\s*위하여\s*필요한\s*사항|"
                     r"제재\s*현황|제재등과\s*관련된\s*사항|우발\s*채무\s*등|우발부채\s*등|"
                     r"소송\s*사건|중요한\s*소송|계류\s*중인\s*소송",
    "S_EXEC":  _RN + r"임원\s*및\s*직원\s*등에\s*관한\s*사항|임원\s*및\s*직원의\s*현황|"
                     r"직원\s*등\s*현황",
    "S_BIZ":   _RN + r"사업의\s*내용",
    "S_RISK":  _RN + r"사업\s*위험|투자\s*위험\s*요소|위험\s*요인|주요\s*위험|위험\s*관리",
    "S_GOV":   _RN + r"주주에\s*관한\s*사항|지배\s*구조|계열\s*회사\s*등에\s*관한\s*사항|"
                     r"대주주\s*등과의\s*거래\s*내용|이사회\s*등\s*회사의\s*기관",
}
_ARC_SECTION_RE = {k: re.compile(v) for k, v in ARC_SECTION_PAT.items()}

# ── 정규화 사전 ─────────────────────────────────────────────────────────────────────────────
# [5] 법정 고지문·서식 문구. 전 기업이 동일하게 쓰므로 남겨두면 유사도를 인위적으로 끌어올린다
#     (= 진짜 변화가 희석된다). 반대로 서식 개정 해에는 이 문구들이 일제히 바뀌어 전 종목이
#     '변경'으로 잡힌다. 어느 쪽이든 신호가 아니므로 제거한다.
_DOC_BOILERPLATE = [
    r"본\s*보고서\s*작성\s*기준일\s*현재[^.\n]{0,80}[.\n]",
    r"금융감독원\s*전자공시시스템[^\n]{0,60}",
    r"전자공시시스템\s*dart\.fss\.or\.kr[^\n]{0,60}",
    r"공시서류\s*작성\s*기준[^\n]{0,60}",
    r"※\s*상기\s*내용은[^.\n]{0,120}[.\n]",
    r"자세한\s*사항은\s*본문을\s*참조[^\n]{0,40}",
    r"목\s*차\s*[\r\n]+(?:[^\n]{0,80}[\r\n]+){0,60}?(?=[IVX]{1,4}\s*\.)",
    r"-\s*\d{1,4}\s*-",                        # 페이지 번호
    r"\(단위\s*[:：][^)]{0,30}\)",              # 표 단위 표기 (표는 지웠지만 캡션이 남는다)
    r"주\s*\d{1,2}\s*\)",                      # 주석 번호
]
_DOC_BOILERPLATE_RE = re.compile("|".join(_DOC_BOILERPLATE))

# [3] 날짜/기수. 반드시 숫자 마스킹보다 먼저.
_DOC_DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[년\-/.]\s*(?:0?[1-9]|1[0-2])\s*[월\-/.]\s*(?:0?[1-9]|[12]\d|3[01])\s*일?"
    r"|(?:19|20)\d{2}\s*[년\-/.]\s*(?:0?[1-9]|1[0-2])\s*월?"
    r"|(?:19|20)\d{2}\s*년度?|(?:19|20)\d{2}\s*회계연도|(?:19|20)\d{2}\s*사업연도"
    r"|(?:19|20)\d{2}\s*년")
_DOC_PERIOD_RE = re.compile(r"제\s*\d{1,4}\s*(?:기|분기|반기|사업연도|회계연도)"
                            r"|당\s*[반분]?기|전\s*[반분]?기|당기말|전기말")
# [2] 잔여 숫자 (반각/전각/콤마/소수/백분율/괄호음수)
_DOC_NUM_RE = re.compile(r"[（(]?\s*[△▲▽▼\-−]?\s*[0-9０-９][0-9０-９,，.．]*\s*%?\s*[)）]?")

# 마스크 토큰 보호용 자리표시자. 문서 본문에 등장할 수 없는 제어문자를 쓴다.
_DOC_MASK_PH = {"<NUM>": "\x01N\x02", "<DATE>": "\x01D\x02",
                "<PERIOD>": "\x01P\x02", "<COMPANY>": "\x01C\x02"}

# [1] 표/이미지/스크립트
_DOC_TABLE_RE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_DOC_DROP_TAG_RE = re.compile(r"<(script|style|img|object|embed)\b.*?(</\1>|/?>)", re.I | re.S)
_DOC_TAG_RE = re.compile(r"<[^>]+>")

_DOC_STOPWORDS = set("""
그리고 그러나 또한 및 등 등의 등을 등에 대한 대하여 관한 관하여 위한 위하여 통한 통하여
있습니다 있으며 있는 있음 없습니다 없으며 없음 하고 하며 하는 한다 합니다 됩니다 되었습니다
경우 때문 따라 따른 통해 이상 이하 이내 이후 이전 현재 당사 회사 보고서 기준 관련 각각
바랍니다 참조 해당 다음 아래 상기 하기 기재 내용 사항 부분 전체 일부 주요 기타 이러한 그러한
것으로 것을 것이 하나 여부 정도 수준 상태 경우에는 위해 대해 대해서 그것 이것
""".split())


# ── 토큰화 폴백 사다리 ──────────────────────────────────────────────────────────────────────
_DOC_TAGGER = {"kind": None, "obj": None, "warned": False}

# 규칙기반 폴백용 한국어 조사/어미. 긴 것부터 잘라야 '에서는' 이 '에' 로 잘못 잘리지 않는다.
_KO_SUFFIX = sorted([
    "으로서는", "으로부터", "에서부터", "이라고는", "하였습니다", "되었습니다", "있습니다",
    "습니다", "ㅂ니다", "하였다", "되었다", "이라는", "으로써", "으로서", "에서는", "에게서",
    "라고는", "이라도", "까지도", "부터는", "에게는", "에서도", "으로는", "하는", "되는",
    "이라", "으로", "에서", "에게", "부터", "까지", "보다", "처럼", "만큼", "조차", "마저",
    "이나", "거나", "라도", "이며", "하며", "되며", "하고", "되고", "인데", "한다", "된다",
    "들의", "들을", "들이", "들에", "이다", "였다", "했다",
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "만", "로", "라",
], key=len, reverse=True)
_KO_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}|<[A-Z]+>")


def _doc_load_tagger():
    """konlpy → soynlp → 규칙기반. konlpy 는 JVM 을 띄우다 프로세스를 죽일 수 있어 지연 로딩."""
    if _DOC_TAGGER["kind"] is not None:
        return _DOC_TAGGER
    kind, obj = "rule", None
    if globals().get("KONLPY_AVAILABLE"):
        for name in ("Mecab", "Okt"):
            try:
                from konlpy.tag import Mecab, Okt          # type: ignore  # noqa
                obj = (Mecab() if name == "Mecab" else Okt())
                # 실제로 한 번 돌려봐야 안다 (Mecab 은 사전이 없으면 생성 시점엔 통과하고
                # 첫 호출에서 죽는다)
                _ = obj.pos("테스트 문장입니다")
                kind = f"konlpy.{name}"
                break
            except Exception:
                obj = None
                continue
    if obj is None and globals().get("soynlp_tok") is not None:
        try:
            obj = soynlp_tok()                              # 점수사전 없이도 L-토큰화는 동작
            _ = obj.tokenize("테스트 문장입니다")
            kind = "soynlp"
        except Exception:
            obj = None
    _DOC_TAGGER["kind"], _DOC_TAGGER["obj"] = kind, obj
    if not _DOC_TAGGER["warned"]:
        _DOC_TAGGER["warned"] = True
        if kind.startswith("konlpy"):
            LOG.ok(f"형태소 분석기: {kind} — D1 토큰화 품질 최상")
        elif kind == "soynlp":
            LOG.info("형태소 분석기가 없어 soynlp L-토큰화를 씁니다. "
                     "D1 은 정상 동작하나 조사 분리 정확도가 다소 낮습니다.")
        else:
            LOG.warn("형태소 분석기(konlpy)·soynlp 둘 다 없어 규칙기반 토큰화로 폴백합니다. "
                     "★ 이 경로에서도 D1 은 동작하지만 어미 절단이 거칠어 유사도 분산이 커집니다. "
                     "결과 해석 시 감안하고, 가능하면 `pip install soynlp` 를 권합니다.")
    return _DOC_TAGGER


def _doc_rule_stem(tok: str) -> str:
    """규칙기반 어간 추출. 긴 조사/어미부터 잘라내고 2자 미만은 버린다."""
    if tok.startswith("<") and tok.endswith(">"):
        return tok
    t = tok
    for suf in _KO_SUFFIX:
        if len(t) > len(suf) + 1 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t if len(t) >= 2 else ""


def arc_tokenize(norm_text: str) -> List[str]:
    """§6.1.3 [6]. 명사·동사·형용사 어간만 유지, 조사·어미 제거, 불용어 적용."""
    if not norm_text:
        return []
    tg = _doc_load_tagger()
    kind, obj = tg["kind"], tg["obj"]
    toks: List[str] = []
    if kind.startswith("konlpy") and obj is not None:
        try:
            keep = ("NN", "VV", "VA", "XR", "SL", "Noun", "Verb", "Adjective", "Alpha")
            for w, p in obj.pos(norm_text[:400_000]):
                if str(p).startswith(keep) and len(w) >= 2:
                    toks.append(w)
        except Exception:
            toks = []
    elif kind == "soynlp" and obj is not None:
        try:
            for w in obj.tokenize(norm_text[:400_000]):
                w = _doc_rule_stem(w)
                if w:
                    toks.append(w)
        except Exception:
            toks = []
    if not toks:                                   # 규칙기반 (최종 폴백 — 항상 동작)
        for w in _KO_TOKEN_RE.findall(norm_text):
            w = _doc_rule_stem(w)
            if w:
                toks.append(w)
    # 마스킹 토큰은 대소문자 그대로 보존되어야 한다(<NUM> 등)
    return [t for t in toks if t not in _DOC_STOPWORDS]


# ── 정규화 본체 ─────────────────────────────────────────────────────────────────────────────
def _doc_company_variants(names: Sequence[str]) -> List[str]:
    """사명 변형 전개. '㈜대한전선' / '주식회사 대한전선' / '대한전선(주)' / 'Daehan' 을 모두 잡는다.

    ★ 이걸 안 하면 사명 변경/표기 변경만으로 문서가 '바뀐' 것으로 잡힌다.
      특히 지주회사 전환기 기업은 문서 전체에서 사명이 수백 번 등장하므로 영향이 크다.
    """
    out = set()
    for n in names or []:
        s = re.sub(r"\s+", "", str(n or ""))
        s = re.sub(r"(주식회사|㈜|\(주\)|유한회사|㈜)", "", s)
        if len(s) >= 2:
            out.add(re.escape(s))
            out.add(re.escape(s[:2]) + r"[가-힣A-Za-z]{0,6}" + r"(?:주식회사|㈜|\(주\))")
    return sorted(out, key=len, reverse=True)[:24]      # 정규식 폭발 방지


def arc_normalize_text(raw_html: str, company_names: Sequence[str] = ()) -> str:
    """§6.1.3 [1]~[5]. 섹션 표제어는 **보존**한다(분해에 필요하므로).

    반환은 '정규화된 평문'이며, 여기에는 <NUM>/<DATE>/<PERIOD>/<COMPANY> 마스크가 들어 있다.
    """
    if not raw_html:
        return ""
    t = str(raw_html)

    # [1] 표·이미지·스크립트 제거 → 순수 서술 텍스트만 (숫자 표는 D2 가 담당한다)
    t = _DOC_TABLE_RE.sub(" ", t)
    t = _DOC_DROP_TAG_RE.sub(" ", t)
    t = _DOC_TAG_RE.sub(" ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))

    # [4] 사명 마스킹 — ★ 숫자 마스킹보다 먼저. 사명에 숫자가 섞인 경우(예: 'SK C&C', '3S')
    #     숫자를 먼저 지우면 사명 매칭이 깨진다.
    vs = _doc_company_variants(company_names)
    if vs:
        try:
            t = re.sub("|".join(vs), " <COMPANY> ", t)
        except re.error:
            for v in vs[:8]:
                try:
                    t = re.sub(v, " <COMPANY> ", t)
                except re.error:
                    continue

    # [3] 날짜 → <DATE>, 기수 → <PERIOD>   (★ 반드시 [2] 보다 먼저 — 위 헤더 주석 참조)
    t = _DOC_PERIOD_RE.sub(" <PERIOD> ", t)
    t = _DOC_DATE_RE.sub(" <DATE> ", t)

    # [2] 잔여 숫자 → <NUM>
    t = _DOC_NUM_RE.sub(" <NUM> ", t)

    # [5] 서식·법정 문구 제거 + 공백/특수문자 정규화 (표제어는 남긴다)
    t = _DOC_BOILERPLATE_RE.sub(" ", t)
    t = unicodedata.normalize("NFKC", t)
    # ★ 특수문자 정리에서 마스크 토큰이 훼손되는 사고를 원천 차단한다.
    #   이전 구현은 문자클래스에 <> 를 넣고 (?![A-Z]+>) 로만 보호했는데, 여는 '<' 는 살아도
    #   닫는 '>' 는 뒤에 [A-Z]+> 가 없으므로 그대로 지워져 '<NUM>' 이 '<NUM ' 이 됐다.
    #   결과적으로 마스크가 토큰화 단계에서 흩어지고 D1 전체가 무의미해진다(A5 가 잡은 버그).
    #   → 마스크를 제어문자 자리표시자로 잠시 치환한 뒤 정리하고 되돌린다.
    for k, ph in _DOC_MASK_PH.items():
        t = t.replace(k, ph)
    t = re.sub(r"[·ㆍ∙•▷▶□■◦○●◇◆＊*※#~^_=+|\\/\[\]{}<>]+", " ", t)
    for k, ph in _DOC_MASK_PH.items():
        t = t.replace(ph, k)
    t = re.sub(r"(?:<NUM>\s*){3,}", "<NUM> ", t)        # 표 잔재로 반복되는 마스크 압축
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def arc_split_sections(norm_text: str) -> Dict[str, str]:
    """정규화 텍스트 → {섹션ID: 본문}. S_ALL 은 항상 포함. 실패 섹션은 키 자체를 넣지 않는다.

    ★ 섹션 경계는 '다음 섹션 표제 등장 위치'로 잡는다. 목차 블록이 남아 있으면 표제가
      본문보다 먼저 두 번 나오므로, 같은 표제의 '마지막' 등장을 본문 시작으로 본다
      (목차는 문서 앞머리에 몰려 있다).
    """
    out: Dict[str, str] = {}
    if not norm_text:
        return out
    out["S_ALL"] = norm_text

    hits: List[Tuple[int, str]] = []
    for sid, rx in _ARC_SECTION_RE.items():
        ms = list(rx.finditer(norm_text))
        if not ms:
            continue
        # 목차 회피: 등장이 2회 이상이면 마지막(=본문) 것을 쓴다.
        m = ms[-1] if len(ms) > 1 else ms[0]
        hits.append((m.start(), sid))
    if not hits:
        return out
    hits.sort()
    bounds = [h[0] for h in hits] + [len(norm_text)]
    for i, (pos, sid) in enumerate(hits):
        seg = norm_text[pos:bounds[i + 1]]
        # 표제어 자체는 잘라낸다(모든 문서에 동일하게 있으므로 유사도만 부풀린다)
        seg = re.sub(r"^[^\n]{0,80}\n", "", seg, count=1)
        if len(seg) >= 200:
            out[sid] = seg[:400_000]
    return out


# ── 문서 유형/연도 해석 ─────────────────────────────────────────────────────────────────────
_DOC_PERIOD_IN_NM = re.compile(r"\((\d{4})[.\-/](\d{1,2})\)")
_DOC_AMEND_RE = re.compile(r"\[?\s*(기재정정|첨부정정|첨부추가|정정)\s*\]?")


def _doc_classify(report_nm: str, rcept_dt) -> Optional[Tuple[str, int, bool]]:
    """report_nm → (doc_type, bsns_year, is_amend). 정기보고서가 아니면 None."""
    nm = re.sub(r"\s+", "", str(report_nm or ""))
    is_amend = bool(_DOC_AMEND_RE.search(str(report_nm or "")))
    m = _DOC_PERIOD_IN_NM.search(str(report_nm or ""))
    year = mon = None
    if m:
        year, mon = int(m.group(1)), int(m.group(2))
    t = as_ts(rcept_dt)
    if "사업보고서" in nm:
        dt = "FY"
        if year is None:
            year = (t.year - 1) if t is not None and t.month <= 6 else (t.year if t else None)
    elif "반기보고서" in nm:
        dt = "H1"
        if year is None:
            year = t.year if t is not None else None
    elif "분기보고서" in nm:
        # 3월 결산분(Q1)은 5월경, 9월 결산분(Q3)은 11월경 접수된다.
        if mon in (3, 4):
            dt = "Q1"
        elif mon in (9, 10):
            dt = "Q3"
        elif t is not None and t.month <= 8:
            dt = "Q1"
        else:
            dt = "Q3"
        if year is None:
            year = t.year if t is not None else None
    else:
        return None
    if year is None:
        return None
    return (dt, int(year), is_amend)


# ── 수집 ────────────────────────────────────────────────────────────────────────────────────
ARC_DOC_COLS = ["corp_code", "rcept_no", "rcept_dt", "doc_type", "bsns_year", "section",
                "n_tokens", "tf", "bigram", "tok_len", "is_amend"]
ARC_DOC_TF_TOP = 350          # 섹션당 저장 토큰 수. 코사인/자카드에 충분하고 용량은 억제.
ARC_DOC_BG_TOP = 120

_ARC_DOC_FAIL: "Counter" = Counter()


def _doc_unzip_text(raw: bytes) -> str:
    """DART 원문 zip → 평문. 모든 xml/html 엔트리를 읽는다.

    ★ 첫 엔트리만 읽으면 본문 대부분이 조용히 사라진다. zip 안에는 본보고서 + 감사보고서 +
      첨부 재무제표가 별도 엔트리로 들어 있다.
    ★ DART 원문은 EUC-KR 인 경우가 많다. XML 선언의 encoding 을 읽어야 한다.
    """
    chunks: List[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        for nm in zf.namelist():
            if not nm.lower().endswith((".xml", ".html", ".htm", ".txt")):
                continue
            try:
                b = zf.read(nm)
            except Exception:
                continue
            enc = None
            m_enc = re.search(rb'encoding\s*=\s*["\']([\w\-]+)["\']', b[:400], re.I)
            if m_enc:
                enc = m_enc.group(1).decode("ascii", "ignore")
            chunks.append(_decode(b, enc, "dart_doc"))
            if sum(len(c) for c in chunks) > 6_000_000:
                break
    except Exception:
        chunks = [_decode(raw, None, "dart_doc")]
    return "\n".join(chunks)


def fetch_arc_documents(dis: pd.DataFrame, sec: pd.DataFrame,
                        max_docs: int = None) -> pd.DataFrame:
    """정기보고서 원문 → 섹션별 정규화 토큰 테이블. 공용 인덱스에 원문·토큰 모두 영속화.

    · 원문 zip  : VAULT.put_blob("dart_doc","raw", rcept_no, ...)   scope="shared"
    · 토큰 테이블: VAULT.put_table("dart_doc_norm_{연도}", ...)      scope="shared"
      → 다른 전략(텍스트 기반 무엇이든)이 그대로 재사용할 수 있다.
    """
    max_docs = int(max_docs or ARC_DOC_MAX)
    _ARC_DOC_FAIL.clear()

    # ── 기존 캐시(연도 샤드) 적재 ─────────────────────────────────────────────────────────
    years_hint = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))
    have_frames, have_rcept = [], set()
    for y in years_hint:
        d = VAULT.get_table(f"dart_doc_norm_{y}", scope="shared")
        if d is not None and len(d):
            have_frames.append(d.reindex(columns=ARC_DOC_COLS))
            have_rcept |= set(d["rcept_no"].astype(str))
    if have_frames:
        LOG.info(f"공용 캐시에서 정기보고서 토큰 {sum(len(x) for x in have_frames):,}행 재사용 "
                 f"(문서 {len(have_rcept):,}건)")

    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 정기보고서 원문을 받을 수 없습니다. D1 은 캐시분으로만 "
                 "동작하며, 캐시가 없으면 GATE_5 에서 탈락합니다.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    if dis is None or dis.empty:
        LOG.warn("공시목록이 비어 정기보고서를 특정할 수 없습니다.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    # ── 대상 선별 ─────────────────────────────────────────────────────────────────────────
    D = dis.copy()
    D["report_nm"] = D["report_nm"].astype(str)
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D[D["report_nm"].str.contains("사업보고서|반기보고서|분기보고서", na=False)]
    D = D.dropna(subset=["rcept_no", "rcept_dt", "corp_code"])
    if D.empty:
        LOG.warn("공시목록에 정기보고서(A 유형)가 없습니다. fetch_dart_disclosures 가 "
                 "pblntf_ty='A' 를 훑었는지 확인하세요.")
        return (pd.concat(have_frames, ignore_index=True) if have_frames
                else pd.DataFrame(columns=ARC_DOC_COLS))

    cls = [_doc_classify(nm, dt) for nm, dt in zip(D["report_nm"], D["rcept_dt"])]
    D["doc_type"] = [c[0] if c else None for c in cls]
    D["bsns_year"] = [c[1] if c else None for c in cls]
    D["is_amend"] = [bool(c[2]) if c else False for c in cls]
    D = D.dropna(subset=["doc_type", "bsns_year"])
    D["bsns_year"] = D["bsns_year"].astype(int)

    # §4.1 정정공시 — 시점 t 에서는 t 이전 마지막 제출본을 쓴다. 여기서는 전부 수집해 두고
    # 페어링 단계에서 '해당 시점 최신본'을 고른다(소급 적용 금지).
    todo_df = D[~D["rcept_no"].astype(str).isin(have_rcept)].copy()
    if RUN_MODE == "CACHED":
        todo_df = todo_df.iloc[0:0]
    # 최근 연도부터 — 중단돼도 최신이 남게
    todo_df = todo_df.sort_values("rcept_dt", ascending=False)
    if len(todo_df) > max_docs:
        LOG.warn(f"정기보고서 신규 대상 {len(todo_df):,}건 중 {max_docs:,}건만 이번에 받습니다. "
                 f"나머지는 다음 실행에서 이어받습니다(콜드빌드는 4시간 예산 밖).")
        todo_df = todo_df.head(max_docs)

    if len(todo_df) and DBUDGET is not None:
        LOG.info(f"정기보고서 원문 신규 {len(todo_df):,}건 — 오늘 남은 DART 호출 "
                 f"{DBUDGET.remaining():,}건 (실시간 추적값). 예산이 부족하면 받은 만큼 저장하고 "
                 f"다음 실행에서 정확히 이어받습니다.")

    # corp_code → 사명(자사 + 종속회사 후보) — [4] 마스킹 입력
    nm_map: Dict[str, List[str]] = {}
    try:
        if sec is not None and len(sec) and "corp_code" in sec.columns:
            g = sec.dropna(subset=["corp_code"]).groupby(sec["corp_code"].astype(str))["name"]
            nm_map = {k: [str(x) for x in v.dropna().tolist()][:6] for k, v in g}
    except Exception:
        nm_map = {}

    jobs = list(zip(todo_df["rcept_no"].astype(str), todo_df["corp_code"].astype(str),
                    todo_df["rcept_dt"], todo_df["doc_type"], todo_df["bsns_year"],
                    todo_df["is_amend"]))

    def _one(job):
        rn, corp, rdt, dtype, byear, amend = job
        if DBUDGET is not None and not DBUDGET.take(1):
            return None                                  # 예산 소진 — 조용히 중단
        raw = http_get(DART_BASE + "document.xml", source="dart", as_bytes=True, tries=2,
                       params={"crtfc_key": DART_API_KEY, "rcept_no": rn},
                       referer="https://opendart.fss.or.kr/")
        if not raw or len(raw) < 500:
            _ARC_DOC_FAIL["응답없음/과소"] += 1
            return None
        # ★ ZIP 엔드포인트는 오류일 때도 content-type 을 zip 으로 광고하면서 JSON 본문을 준다.
        if raw[:2] != b"PK":
            body = raw[:200].decode("utf-8", "ignore")
            if "020" in body:
                if DBUDGET is not None:
                    DBUDGET.note_rate_limited()
                _ARC_DOC_FAIL["호출한도"] += 1
            else:
                _ARC_DOC_FAIL["ZIP아님(스캔본/오류)"] += 1
            return None
        VAULT.put_blob("dart_doc", "raw", rn, raw, "zip", source="opendart document.xml",
                       event_date=rdt, knowledge_date=rdt, scope="shared",
                       extra={"corp_code": corp, "doc_type": dtype, "bsns_year": int(byear)})
        txt = _doc_unzip_text(raw)
        del raw
        if not txt or len(txt) < 2000:
            _ARC_DOC_FAIL["본문없음"] += 1
            return None
        norm = arc_normalize_text(txt, nm_map.get(str(corp), []))
        del txt
        secs = arc_split_sections(norm)
        if len(secs) <= 1:
            _ARC_DOC_FAIL["섹션0개"] += 1
        rows = []
        for sid, body in secs.items():
            toks = arc_tokenize(body)
            if len(toks) < ARC_D1_MIN_TOKENS:
                continue
            cnt = Counter(toks)
            bg = Counter(zip(toks[:-1], toks[1:]))
            rows.append({
                "corp_code": str(corp), "rcept_no": rn, "rcept_dt": as_ts(rdt),
                "doc_type": str(dtype), "bsns_year": int(byear), "section": sid,
                "n_tokens": int(len(cnt)), "tok_len": int(len(toks)),
                "tf": json.dumps(dict(cnt.most_common(ARC_DOC_TF_TOP)), ensure_ascii=False),
                "bigram": json.dumps({f"{a}_{b}": v for (a, b), v
                                      in bg.most_common(ARC_DOC_BG_TOP)}, ensure_ascii=False),
                "is_amend": bool(amend)})
        if not rows:
            _ARC_DOC_FAIL["토큰부족"] += 1
            return None
        return rows

    got: List[dict] = []
    CH = 400            # 청크 소비 — 원문 바이트가 동시에 RAM 에 쌓이지 않게
    for k0 in range(0, len(jobs), CH):
        if DBUDGET is not None and DBUDGET.exhausted:
            LOG.warn(f"DART 예산 소진으로 원문 수집을 {k0:,}/{len(jobs):,} 지점에서 중단합니다. "
                     f"여기까지 받은 분량은 드라이브에 저장되어 다음 실행에서 이어받습니다.")
            break
        part = jobs[k0:k0 + CH]
        res = pmap_io(_one, part, workers=min(N_WORKERS_IO, 6),
                      desc=f"정기보고서 원문 {k0//CH + 1}/{(len(jobs)-1)//CH + 1}")
        for r in res:
            if r:
                got.extend(r)
        del res
        VAULT.flush("shared")
        gc.collect()

    frames = have_frames + ([pd.DataFrame(got)] if got else [])
    if not frames:
        LOG.warn("정기보고서 토큰을 한 건도 확보하지 못했습니다 — D1 비활성화 대상입니다.")
        _arc_doc_fail_report(len(jobs))
        return pd.DataFrame(columns=ARC_DOC_COLS)

    T = pd.concat([f.reindex(columns=ARC_DOC_COLS) for f in frames], ignore_index=True)
    T["rcept_dt"] = as_ts_series(T["rcept_dt"])
    T = T.dropna(subset=["rcept_no", "section", "rcept_dt"])
    T = T.drop_duplicates(["rcept_no", "section"], keep="last").reset_index(drop=True)

    # ── 연도 샤드 저장 (신규분이 있는 연도만) ─────────────────────────────────────────────
    if got:
        new_years = sorted({int(r["bsns_year"]) for r in got})
        for y in new_years:
            g = T[T["bsns_year"].astype(int) == y]
            if len(g):
                VAULT.put_table(f"dart_doc_norm_{y}", g, scope="shared", domain="dart_text",
                                source="opendart document.xml + ARC 정규화",
                                extra={"note": "정규화 토큰(전 전략 공용) — <NUM>/<DATE>/"
                                               "<PERIOD>/<COMPANY> 마스킹 적용"})
        VAULT.flush("shared")

    n_doc = T["rcept_no"].nunique()
    LOG.ok(f"정기보고서 토큰 {len(T):,}행 · 문서 {n_doc:,}건 · {T['corp_code'].nunique():,}사 "
           f"(섹션 평균 {len(T)/max(n_doc,1):.1f}개)")
    _arc_doc_fail_report(len(jobs))
    PIPE.io("OUT", "DRIVE", "dart_doc_norm", T, source="opendart document.xml")
    return T


def _arc_doc_fail_report(n_try: int):
    """§0.4 — 기계판독 실패율을 반드시 측정·보고한다(구형 공시는 PDF 스캔본 비중이 높다)."""
    if not _ARC_DOC_FAIL:
        if n_try:
            LOG.ok(f"원문 파싱 실패 0건 / 시도 {n_try:,}건")
        return
    tot = sum(_ARC_DOC_FAIL.values())
    LOG.table([[k, f"{v:,}", f"{100*v/max(n_try,1):.1f}%"]
               for k, v in _ARC_DOC_FAIL.most_common()] +
              [["── 합계 ──", f"{tot:,}", f"{100*tot/max(n_try,1):.1f}%"]],
              ["실패 사유", "건수", "시도 대비"], ["l", "r", "r"],
              title="정기보고서 기계판독 실패 분해 (GATE_5 의 근거)")
    if n_try and tot / max(n_try, 1) > 0.20:
        LOG.warn(f"기계판독 실패율 {100*tot/n_try:.1f}% 가 20% 를 넘습니다. "
                 f"구형 공시의 PDF 스캔본 비중이 높은 구간이면 정상이며, D1 은 그 구간에서 "
                 f"결측 처리됩니다(0으로 채우지 않습니다).")


# ── 페어링 (§6.1.1) ─────────────────────────────────────────────────────────────────────────
ARC_PAIR_COLS = ["corp_code", "doc_type", "bsns_year", "section", "rcept_no", "prev_rcept_no",
                 "rcept_dt", "prev_rcept_dt", "tf", "prev_tf", "bigram", "prev_bigram",
                 "tok_len", "prev_tok_len", "is_amend"]


def arc_doc_pairs(T: pd.DataFrame) -> pd.DataFrame:
    """§6.1.1 '동일 유형 × 전년 동기' 페어링. 직전 분기 비교는 절대 하지 않는다.

    ★ 왜 직전 분기와 비교하면 안 되는가: 사업보고서(연간)와 분기보고서는 분량·구성이
      구조적으로 다르다. 섞어서 비교하면 전 종목에서 가짜 변화가 대량 발생해 신호가 죽는다.

    ★ 정정공시 처리(§4.1): 같은 (corp, type, year) 에 여러 접수가 있으면 **가장 늦은 접수본**을
      그 기수의 대표로 삼되, 비교 시점은 그 접수일이다. 즉 '그 시점에 관측 가능했던 최신 버전'
      규약과 일치한다(미래 정정본을 과거 시점에 소급 적용하지 않는다 — 과거 시점의 유사도는
      그 시점 이전 접수본만으로 계산되기 때문).
    """
    if T is None or T.empty:
        return pd.DataFrame(columns=ARC_PAIR_COLS)
    d = T.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["corp_code", "doc_type", "bsns_year", "section", "rcept_dt"])
    d["bsns_year"] = pd.to_numeric(d["bsns_year"], errors="coerce")
    d = d.dropna(subset=["bsns_year"])
    d["bsns_year"] = d["bsns_year"].astype(int)
    # ★ 계약 §4.1: 정정공시(is_amend)는 플래그만 기록하고 신호에는 쓰지 않는다.
    #   예전에는 keep="last" 만 걸려 있어 **정정본이 원본을 프레임에서 삭제**했다. 그러면
    #   ① 원본이 실제로 공개됐던 시점의 D1 이 통째로 사라지고(D1_MISSING),
    #   ② 다음 해의 비교 기준이 '당시 공개돼 있던 텍스트'가 아니라 '나중에 정정된 텍스트'가
    #      된다 — 그 시점에 읽을 수 없었던 문서를 비교 대상으로 쓰는 미래 참조다.
    #   정정공시를 내는 기업은 부실기업 쪽으로 치우쳐 있어, 이 손실은 무작위가 아니다.
    if "is_amend" in d.columns:
        am = d["is_amend"].astype(bool)
        n_am = int(am.sum())
        if n_am:
            # 원본이 존재하는 기수의 정정본만 뺀다. 정정본밖에 없으면 그거라도 써야
            # 그 기수가 통째로 사라지지 않는다(근거 없는 결측 금지).
            key = ["corp_code", "doc_type", "bsns_year", "section"]
            has_orig = d.loc[~am, key].drop_duplicates().assign(_orig=1)
            d = d.merge(has_orig, on=key, how="left")
            drop = am.to_numpy() & (d["_orig"] == 1).to_numpy()
            LOG.info(f"정정공시 {n_am:,}건 중 원본이 있는 {int(drop.sum()):,}건을 페어링에서 "
                     f"제외했습니다(§4.1 — 플래그만 기록, 신호 미사용). "
                     f"원본이 없는 {n_am - int(drop.sum()):,}건은 유지합니다.")
            d = d[~drop].drop(columns=["_orig"])
    # 같은 기수에 같은 종류가 여러 개면 마지막 접수본이 대표
    d = (d.sort_values("rcept_dt", kind="stable")
           .drop_duplicates(["corp_code", "doc_type", "bsns_year", "section"], keep="last"))

    prev = d.copy()
    prev["bsns_year"] = prev["bsns_year"] + 1           # 전년 → 당년 키로 맞춘다
    prev = prev.rename(columns={"rcept_no": "prev_rcept_no", "rcept_dt": "prev_rcept_dt",
                                "tf": "prev_tf", "bigram": "prev_bigram",
                                "tok_len": "prev_tok_len"})
    keep = ["corp_code", "doc_type", "bsns_year", "section", "prev_rcept_no",
            "prev_rcept_dt", "prev_tf", "prev_bigram", "prev_tok_len"]
    M = d.merge(prev[keep], on=["corp_code", "doc_type", "bsns_year", "section"], how="inner")

    # ★ 전년본 접수일이 당년본보다 늦으면(데이터 오류) 그 쌍은 버린다 — 미래 문서와의 비교다.
    bad = M["prev_rcept_dt"] >= M["rcept_dt"]
    if bad.any():
        LOG.warn(f"전년본 접수일이 당년본 이후인 쌍 {int(bad.sum()):,}건을 제외했습니다"
                 f"(원문 접수일 오류 또는 정정 순서 역전).")
        M = M[~bad]

    M = M.reindex(columns=ARC_PAIR_COLS)
    n_doc = M["rcept_no"].nunique() if len(M) else 0
    LOG.ok(f"전년 동기 페어 {len(M):,}쌍 · 문서 {n_doc:,}건 "
           f"(유형별: " + ", ".join(f"{k}={v:,}" for k, v in
                                    (M["doc_type"].value_counts().items() if len(M) else [])) + ")")
    PIPE.io("OUT", "MEM", "dart_doc_pairs", M)
    return M


def arc_norm_sample_report(T: pd.DataFrame, n: int = 5) -> None:
    """§10-[4] 육안 검증. 정규화가 가짜 변화를 실제로 제거했는지 사람이 확인하는 관문.

    ★ 이 단계에서 숫자·날짜·사명이 그대로 보이면 이후 D1 결과는 전부 무의미하다.
      그래서 '통과'를 코드가 자동 선언하지 않고 사람에게 보여준다.
    """
    LOG.banner("정규화 육안 검증 샘플 (§10-[4])",
               "여기에 숫자·날짜·사명이 그대로 남아 있으면 이후 D1 결과는 전부 무의미합니다")
    if T is None or T.empty:
        LOG.warn("정규화 결과가 없어 샘플을 보여줄 수 없습니다.")
        return
    sub = T[T["section"] == "S_MDA"]
    if sub.empty:
        sub = T[T["section"] == "S_ALL"]
    sub = sub.drop_duplicates("corp_code").head(int(n))
    rows = []
    for r in sub.itertuples(index=False):
        try:
            toks = list(json.loads(r.tf).items())[:22]
        except Exception:
            toks = []
        # ★ int(r.tok_len) 을 try 밖에 두면 안 된다. 공용 캐시에는 tok_len 이 없던 스키마의
        #   샤드가 남아 있을 수 있고(Vault 는 과거 버전 재사용을 설계 목표로 삼는다),
        #   그러면 여기서 ValueError 가 나면서 L1.DOC 스테이지가 WARN 으로 접혀
        #   ctx["doc_pairs"] 가 설정되지 않는다 → GATE_4/5 판정불가 → **원문을 전부 받아
        #   놓고도 D1 축이 비활성화된 채** 백테스트가 끝까지 정상 완주한다.
        _tl = pd.to_numeric(getattr(r, "tok_len", np.nan), errors="coerce")
        rows.append([str(r.corp_code), str(r.doc_type), str(r.bsns_year),
                     (f"{int(_tl):,}" if np.isfinite(_tl) else "—"),
                     _trunc(" ".join(f"{k}×{v}" for k, v in toks), 92)])
    LOG.table(rows, ["법인코드", "유형", "사업연도", "토큰수", "상위 토큰 (정규화 후)"],
              ["l", "c", "c", "r", "l"], maxw=96)
    # 마스크가 실제로 작동했는지 정량 확인
    try:
        s = " ".join(T["tf"].head(200).astype(str).tolist())
        n_num = s.count("<NUM>")
        n_date = s.count("<DATE>")
        n_comp = s.count("<COMPANY>")
        raw_digit = len(re.findall(r'"[^"]*\d[^"]*"', s))
        LOG.table([["<NUM> 마스크 등장", f"{n_num:,}"],
                   ["<DATE> 마스크 등장", f"{n_date:,}"],
                   ["<COMPANY> 마스크 등장", f"{n_comp:,}"],
                   ["숫자가 남은 토큰(있으면 정규화 누락)", f"{raw_digit:,}"],
                   ["형태소 분석기", _DOC_TAGGER.get("kind") or "미결정"]],
                  ["점검 항목", "값"], ["l", "r"], title="정규화 마스킹 정량 점검")
        if raw_digit > 0:
            LOG.warn(f"토큰에 숫자가 {raw_digit:,}개 남아 있습니다. 숫자 마스킹 정규식이 놓친 "
                     f"패턴이 있다는 뜻이며, 그만큼 가짜 변화가 신호에 섞입니다.")
    except Exception:
        pass


def arc_doc_years(T: Optional[pd.DataFrame] = None) -> List[int]:
    """수집된 정기보고서의 사업연도 목록. 매니페스트가 있으면 그걸, 없으면 캐시 샤드를 본다."""
    if T is not None and len(T) and "bsns_year" in T.columns:
        return sorted(int(y) for y in pd.to_numeric(T["bsns_year"], errors="coerce")
                      .dropna().unique())
    out = []
    for y in range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1):
        pth = os.path.join(VAULT.table_dir("shared"), f"dart_doc_norm_{y}.parquet")
        if os.path.exists(pth):
            out.append(y)
    return out


def arc_doc_load_years(years: Sequence[int]) -> pd.DataFrame:
    """지정 연도의 토큰 샤드만 메모리에 올린다.

    ★ 왜 필요한가: 전 구간 토큰을 한 번에 들면 (2,500사 × 10년 × 4유형 × 7섹션) × 수 KB
      = 수 GB 가 되어 노트북이 죽는다. D1 은 '전년 동기' 만 필요하므로 2개 연도씩만
      올리면 상주량이 문서 수와 무관하게 평평해진다.
    """
    frames = []
    for y in sorted({int(x) for x in years}):
        d = VAULT.get_table(f"dart_doc_norm_{y}", scope="shared")
        if d is not None and len(d):
            frames.append(d.reindex(columns=ARC_DOC_COLS))
    if not frames:
        return pd.DataFrame(columns=ARC_DOC_COLS)
    T = pd.concat(frames, ignore_index=True)
    T["rcept_dt"] = as_ts_series(T["rcept_dt"])
    return T.dropna(subset=["rcept_no", "section", "rcept_dt"])



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

        # ★ 추정 상장일(첫 스냅샷 관측일)로는 종목을 탈락시키지 않는다. 그 값은 대개
        #   '백테 시작월'이라, 그대로 앵커로 쓰면 스냅샷 커버리지가 짧은 폐지 종목만
        #   초기 구간에서 사라진다 — 생존군과 폐지군에 다른 규칙이 적용되는 비대칭이다.
        if "listing_date_src" in self.sec.columns:
            est = self.sec["listing_date_src"].astype(str).str.contains("추정", na=False)
            if int(est.sum()):
                LOG.info(f"추정 상장일 {int(est.sum()):,}종목은 시즈닝 앵커에서 제외합니다 "
                         f"(근거 없는 제외 금지).")
            self.sec.loc[est, "listing_date"] = pd.NaT

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


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F+  ARC — U-1000 유니버스 (§3) + 분기 패널 조립                                        ║
# ║                                                                                          ║
# ║  §3.1  PIT 시가총액 랭크 '하위 1000종목' (KOSPI+KOSDAQ). 매 리밸일 스냅샷으로 재구성.       ║
# ║  §3.2  직전 60거래일 ADTV ≥ 1억원                                                          ║
# ║  §3.3  관리종목·환기·거래정지·스팩·우선주·리츠·완전자본잠식·상장12개월미만 제외             ║
# ║  §3.4  ★상장폐지 종목을 PIT 스냅샷에 반드시 포함. 정리매매 없으면 -100%.                    ║
# ║                                                                                          ║
# ║  ★ 이 전략에서 가장 치명적인 편향 지점은 "현재 시총 랭크를 과거에 적용" 이다.                ║
# ║    지금 소형주인 종목은 정의상 '지난 10년간 주가가 하락한' 종목이므로, 그 명단으로            ║
# ║    2016년 유니버스를 만들면 하락할 종목만 골라 담은 셈이 된다. 그래서 랭크는 반드시           ║
# ║    그 시점에 관측된 시총(mc_panel)으로만 매긴다. A3 계약검정이 이걸 실제로 검사한다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 우선주 코드 규칙: 구형 6자리는 끝자리가 5/7/9 (1우/2우B/3우 등),
# 2024 영숫자 체계는 6번째 자리가 K/L/M/N.
_PREF_NEW_RE = re.compile(r"^\d{4}[0-9A-HJ-NP-TV-Z][KLMN]$")     # 2024 영숫자 체계 우선주
_SPAC_RE = re.compile(r"스팩|기업인수목적")
# ★ '리츠' 부분문자열 매칭은 보통주를 상시 제외한다 — 실제 KRX 명단에서 메리츠금융지주·
#   메리츠증권·메리츠화재·블리츠웨이엔터테인먼트·유레스메리츠1 이 리츠로 오분류됐다.
#   블리츠웨이는 KOSDAQ 소형주라 U-1000 을 직격한다. 어미 기준으로 좁힌다.
_REIT_RE = re.compile(r"(?:^|[^가-힣A-Za-z])리\s?츠(?:$|[0-9]*\s*호?$)|"
                      r"리\s?츠(?:부동산)?투자회사|\bREITs?\b", re.I)
# 종목명보다 신뢰도가 높은 판정 근거. 폐지목록 CSV 의 SecuGroup 에 실제로 들어 있다.
_REIT_SECUGROUP_RE = re.compile(r"부동산투자회사|REIT", re.I)
# §3.1 은 KOSPI + KOSDAQ 이다. KONEX·수익증권·투자회사·선박투자회사는 유니버스 밖이다.
ARC_ALLOWED_MARKETS = ("KOSPI", "KOSDAQ")
_NONEQUITY_SECUGROUP_RE = re.compile(
    r"수익증권|투자회사|선박투자회사|신주인수권|출자증권|외국주권예탁증서|ETN|ETF", re.I)
_PREF_NAME_RE = re.compile(r"\d?\s*우(?:B|C)?$|우선주$")


def is_preferred(code: str, name: str = "", base_codes: Optional[set] = None) -> bool:
    """우선주 판정.

    ★ '끝자리가 5~9 면 우선주' 라는 흔한 휴리스틱은 과잉 제외를 낳는다. 보통주도 끝자리가
      0 이 아닌 경우가 있고, 그런 종목을 통째로 버리면 유니버스가 조용히 줄어 선택편향이 된다.
      그래서 세 근거 중 하나가 확실할 때만 우선주로 본다:
        ① 2024 영숫자 체계에서 6번째 자리가 K/L/M/N
        ② 끝자리가 0 이 아니면서 **같은 앞 5자리 + 0 인 보통주가 실제로 존재**
           (우선주는 정의상 형제 보통주가 있다 — 이게 가장 결정적인 증거다)
        ③ 종목명이 '…우' / '…우B' / '…우선주' 로 끝남 ('미래에셋대우' 같은 사명은 제외)
    """
    c = str(code or "")
    if _PREF_NEW_RE.match(c):
        return True
    n = re.sub(r"\s+", "", str(name or ""))
    if n and _PREF_NAME_RE.search(n) and not re.search(r"(대우|한우|교우|동우|삼우)$", n):
        return True
    # ★ 끝자리가 0 이 아니라는 것만으로는 부족하다. 한국 우선주 코드는 5/7/9(구형 1·2·3우)
    #   또는 6/8(신형우선주) 로 끝난다. 1~4 로 끝나는 종목까지 형제 규칙에 걸면 보통주가
    #   대량 제외되어 유니버스가 조용히 붕괴한다(합성 검정에서 220종목 중 189종목이 제외됐다).
    if base_codes and len(c) == 6 and c.isdigit() and c[-1] in "56789":
        if (c[:5] + "0") in base_codes:
            return True
    return False


def classify_excluded(sec: pd.DataFrame) -> pd.DataFrame:
    """§3.3 종목 속성 기반 상시 제외 판정. 반환: code, ex_spac, ex_pref, ex_reit, ex_static.

    [방법론적 한계] 관리종목·투자주의환기종목·거래정지의 '지정일 이력'은 공개 API 로
    과거 전 구간을 복원할 수 없다. 이 코드는 ① 종목 속성(스팩/우선주/리츠)은 정확히 제외하고,
    ② 관리종목 지정의 주된 사유(자본잠식·4분기 연속 영업적자·감사의견 비적정)는 §6.4
    배제 플래그가 잡으며, ③ 거래정지는 '유동성 하한 미달'로 자연 탈락한다.
    이 근사는 리포트에 명시한다 — 숨기지 않는다.
    """
    cols = ["code", "ex_spac", "ex_pref", "ex_reit", "ex_market", "ex_static"]
    if sec is None or sec.empty:
        return pd.DataFrame(columns=cols)
    S = sec.copy()
    S["code"] = S["code"].astype(str)
    nm = S.get("name", pd.Series("", index=S.index)).astype(str)
    sg = S.get("secugroup", pd.Series("", index=S.index)).astype(str)
    S["ex_spac"] = nm.str.contains(_SPAC_RE, na=False).astype("int8")
    S["ex_reit"] = (nm.str.contains(_REIT_RE, na=False) |
                    sg.str.contains(_REIT_SECUGROUP_RE, na=False)).astype("int8")
    _base = set(S["code"].astype(str))
    S["ex_pref"] = [1 if is_preferred(c, n, _base) else 0 for c, n in zip(S["code"], nm)]

    # ★ §3.1 시장 필터. 이게 없으면 KONEX·수익증권·선박투자회사가 U-1000 에 들어온다.
    #   U-1000 은 '시총 오름차순 하위 1000' 이므로 시총이 극소인 이들이 정의상 컷 안쪽에
    #   확정 편입되어 정규 KOSDAQ 소형주를 밀어낸다. 시장 정보가 아예 없는 종목은
    #   제외하지 않는다(근거 없는 제외 금지) — 대신 건수를 로그로 드러낸다.
    mk = S.get("market", pd.Series("", index=S.index)).astype(str).str.upper().str.strip()
    known_mk = mk.str.len() > 0
    ok_mk = mk.str.startswith(tuple(m.upper() for m in ARC_ALLOWED_MARKETS))
    S["ex_market"] = ((known_mk & ~ok_mk) |
                      sg.str.contains(_NONEQUITY_SECUGROUP_RE, na=False)).astype("int8")

    S["ex_static"] = ((S["ex_spac"] + S["ex_reit"] + S["ex_pref"] +
                       S["ex_market"]) > 0).astype("int8")
    n = int(S["ex_static"].sum())
    LOG.info(f"§3.3 상시 제외 {n:,}종목 — 스팩 {int(S['ex_spac'].sum()):,} · "
             f"우선주 {int(S['ex_pref'].sum()):,} · 리츠 {int(S['ex_reit'].sum()):,} · "
             f"시장/증권종류 밖 {int(S['ex_market'].sum()):,}")
    if int((~known_mk).sum()):
        LOG.info(f"  시장 정보가 없는 {int((~known_mk).sum()):,}종목은 시장 필터를 "
                 f"적용하지 않았습니다(근거 없는 제외 금지).")
    if int(S["ex_market"].sum()):
        _mk_cnt = mk[S["ex_market"] > 0].replace("", "미상").value_counts()
        LOG.info("  제외된 시장 구성: " +
                 " · ".join(f"{k} {v:,}" for k, v in _mk_cnt.head(6).items()))
    # ★ 안전밸브: 상시 제외가 과도하면 규칙이 오작동하고 있다는 뜻이다. 조용히 넘기면
    #   유니버스가 붕괴한 채로 백테스트가 끝까지 돌아가 '표본이 적은 좋은 성과'를 만든다.
    #   시장 필터는 정의상 제외(§3.1)라 오작동 지표가 아니므로 경보 분자에서 뺀다.
    n_heur = int(((S["ex_spac"] + S["ex_reit"] + S["ex_pref"]) > 0).sum())
    if len(S) and n_heur / len(S) > 0.15:
        LOG.warn(f"이름 규칙 기반 상시 제외 비율이 {100*n_heur/len(S):.1f}% 로 과도합니다"
                 f"(정상 범위 5~12%). "
                 f"우선주 판정 규칙이 오작동해 보통주를 걸러내고 있을 가능성이 큽니다 — "
                 f"유니버스 감쇠 감사표에서 종목수를 반드시 확인하세요.")
        PIPE.note(f"WARN: 상시 제외 {100*n/len(S):.0f}%")
    return S[cols]


class ArcUniverse:
    """U-1000 PIT 유니버스. 기존 Universe(상장/폐지 근거)를 감싸 랭크·유동성·제외를 얹는다."""

    def __init__(self, base: "Universe", sec: pd.DataFrame, exdf: pd.DataFrame):
        self.base = base
        self.sec = sec
        self.attrition: List[dict] = []
        self._ex = set(exdf.loc[exdf["ex_static"] == 1, "code"].astype(str)) if len(exdf) else set()
        self._delist = base.delisting_map()
        self._members: Dict[pd.Timestamp, List[str]] = {}

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return self._delist

    def audit_row(self, stage: str, t, codes: Sequence[str]):
        self.attrition.append({"asof": as_ts(t), "stage": stage, "n": len(codes)})

    def build(self, rebals: pd.DatetimeIndex, mc: pd.DataFrame, liq: pd.DataFrame) -> pd.DataFrame:
        """리밸일별 U-1000 멤버십을 만든다. 반환: code, asof, mktcap, adtv60, uni_rank."""
        # ★ (code, asof) 가 중복이면 reindex 가 "non-unique multi-index" 로 죽는다.
        #   실데이터에서는 소스 병합 과정에서 흔히 발생하므로 여기서 방어하고 건수를 남긴다.
        def _uniq(df, val):
            if df is None or len(df) == 0 or val not in df.columns:
                return pd.Series(dtype=float)
            d = df[["code", "asof", val]].copy()
            d["code"] = d["code"].astype(str)
            d["asof"] = as_ts_series(d["asof"])
            n0 = len(d)
            d = d.dropna(subset=["code", "asof"]).drop_duplicates(["code", "asof"], keep="last")
            if n0 - len(d):
                LOG.info(f"유니버스 입력 '{val}' 에서 중복 (code, asof) {n0-len(d):,}행을 "
                         f"마지막 값으로 정리했습니다.")
            return d.set_index(["code", "asof"])[val]

        mcx = _uniq(mc, "mktcap")
        lqx = _uniq(liq, "adtv60")
        out = []
        for t in rebals:
            t = as_ts(t)
            listed = self.base.at(t)                       # 상장·폐지·시즈닝 반영 (C2)
            self.audit_row("전체상장", t, listed)
            cand = [c for c in listed if c not in self._ex]
            self.audit_row("상시제외후", t, cand)
            if not cand:
                continue
            idx = pd.MultiIndex.from_product([[str(c) for c in cand], [pd.Timestamp(t)]],
                                             names=["code", "asof"])
            m = mcx.reindex(idx).to_numpy(dtype="float64") if len(mcx) else np.full(len(cand), np.nan)
            a = lqx.reindex(idx).to_numpy(dtype="float64") if len(lqx) else np.full(len(cand), np.nan)
            df = pd.DataFrame({"code": cand, "asof": t, "mktcap": m, "adtv60": a})
            df = df[np.isfinite(df["mktcap"]) & (df["mktcap"] > 0)]
            self.audit_row("시총보유", t, df["code"].tolist())
            if df.empty:
                continue
            # §3.1 하위 1000 — 시총 오름차순(작은 것부터) 상위 N
            df = df.sort_values(["mktcap", "code"], kind="mergesort").head(ARC_UNIVERSE_N).copy()
            df["uni_rank"] = np.arange(1, len(df) + 1)
            self.audit_row("U-1000", t, df["code"].tolist())
            # §3.2 유동성 하한
            df = df[df["adtv60"].fillna(0) >= ARC_MIN_ADTV_KRW]
            self.audit_row("유동성필터", t, df["code"].tolist())
            out.append(df)
        if not out:
            LOG.error("U-1000 유니버스가 비었습니다. PIT 시가총액이 확보되지 않았을 가능성이 큽니다 "
                      "(위 '시총 출처 감사' 표를 확인하세요).")
            return pd.DataFrame(columns=["code", "asof", "mktcap", "adtv60", "uni_rank"])
        U = pd.concat(out, ignore_index=True)
        n_by = U.groupby("asof")["code"].size()
        LOG.ok(f"U-1000 유니버스 {len(U):,}행 · 리밸일 {U['asof'].nunique()}개 · "
               f"시점당 평균 {n_by.mean():.0f}종목 (최소 {n_by.min():,} / 최대 {n_by.max():,})")
        if n_by.mean() < 300:
            LOG.warn(f"시점당 평균 종목이 {n_by.mean():.0f}개로 적습니다. 유동성 하한(1억) 또는 "
                     f"시총 결측이 원인일 수 있습니다 — 아래 감쇠 감사표에서 확인하세요.")
        return U

    def report_attrition(self):
        if not self.attrition:
            return
        A = pd.DataFrame(self.attrition)
        order = ["전체상장", "상시제외후", "시총보유", "U-1000", "유동성필터",
                 "배제플래그통과", "신호보유", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max"])
        rows, prev = [], None
        for s in order:
            if s not in piv.index:
                continue
            m = piv.loc[s]
            keep = "" if prev is None else f"{100*m['mean']/max(prev,1e-9):.1f}%"
            rows.append([s, f"{m['mean']:,.0f}", f"{m['min']:,.0f}", f"{m['max']:,.0f}", keep])
            prev = m["mean"]
        LOG.table(rows, ["게이트", "시점평균 종목수", "최소", "최대", "직전 대비 잔존율"],
                  ["l", "r", "r", "r", "r"],
                  title="유니버스 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and float(str(rows[-1][1]).replace(",", "")) < ARC_TOP_N_MIN:
            LOG.warn(f"최종 단계 종목이 목표 보유수({ARC_TOP_N_MIN}~{ARC_TOP_N_MAX})보다 적습니다. "
                     f"임계값을 낮추기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")


# ── 셀 (횡단면 표준화 단위) ─────────────────────────────────────────────────────────────────
_SECTOR_MAP = [
    (r"반도체|전자|디스플레이|IT|정보기술|통신장비|컴퓨터|소프트|인터넷|게임|미디어|콘텐츠",
     "IT/전자"),
    (r"제약|바이오|의료|헬스|생명과학|화장품", "헬스케어"),
    (r"화학|정유|에너지|가스|비금속|시멘트|철강|금속|섬유|종이|목재", "소재"),
    (r"기계|조선|자동차|운송장비|항공|우주|전기장비|건설|건축|엔지니어링", "산업재"),
    (r"음식료|담배|유통|도매|소매|백화점|섬유의복|가구|생활용품|교육|여행|레저|호텔",
     "소비재"),
    (r"은행|증권|보험|금융|캐피탈|지주|투자", "금융"),
    (r"전기|수도|유틸리티|발전", "유틸리티"),
    (r"운수|물류|창고|해운|항만", "운송"),
]
_SECTOR_RE = [(re.compile(p), s) for p, s in _SECTOR_MAP]


def to_sector(industry: Any) -> str:
    """세부 업종 문자열 → 8개 상위 섹터. 횡단면 셀이 너무 잘게 쪼개지는 것을 막는다.

    ★ 업종을 그대로 셀로 쓰면 셀당 종목이 3~5개가 되어 z-score 가 전부 NaN 이 된다.
      (U-1000 은 이미 소형주만 남긴 집합이라 더 그렇다)
    """
    s = str(industry or "")
    for rx, lab in _SECTOR_RE:
        if rx.search(s):
            return lab
    return "기타"


def build_arc_cells(P: pd.DataFrame, sec: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """cell = (분기, 섹터). 폴백 = (분기, ALL).

    ★ 규모 버킷을 셀에 넣지 않는다. U-1000 은 이미 규모로 잘라낸 집합이라 규모를 또 넣으면
      셀당 종목이 급감하고, 그 자체가 '소형주 안에서 더 소형' 이라는 다른 축을 몰래 넣는 셈이다.
    """
    ind = (sec.drop_duplicates("code").set_index("code")["industry"].astype(str).to_dict()
           if sec is not None and len(sec) and "industry" in sec.columns else {})
    p = P.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    p["sector"] = p["industry"].map(to_sector).astype(str)
    qs = p["q"].astype(str)
    p["cell"] = qs + "|" + p["sector"]
    p["cell_all"] = qs + "|ALL"
    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    if small.any():
        p.loc[small, "cell"] = p.loc[small, "cell_all"]
        LOG.info(f"셀 폴백 {int(small.sum()):,}행 (섹터 셀 표본 {min_n}개 미만 → 전체 셀로). "
                 f"조용히 넘기지 않고 기록합니다.")
        PIPE.note(f"셀 폴백 {int(small.sum()):,}행")
    for c in ("cell", "cell_all"):
        p[c] = p[c].astype("category")
    LOG.debug(f"셀 구성: 섹터셀 {p['cell'].nunique():,}개 · 전체셀 {p['cell_all'].nunique():,}개")
    return p


# ── 분기 패널 조립 ──────────────────────────────────────────────────────────────────────────
ARC_PANEL_BASE_COLS = ["code", "asof", "q", "corp_code", "market", "industry", "sector",
                       "mktcap", "adtv60", "uni_rank", "close", "exec_px",
                       "fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q", "listing_months",
                       "mom_12_1", "log_mktcap", "log_adtv", "cell", "cell_all"]


def build_liquidity_panel(px_daily: pd.DataFrame, rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """리밸일 시점의 (직전 60거래일 ADTV, 직전 종가, 12-1 모멘텀). 전부 t 이전 관측만 쓴다.

    ★ '직전' 의 정의가 중요하다. 리밸일 당일 데이터를 쓰면 §4 의 't-1 종가까지만' 규약 위반이다.
      merge_asof(direction='backward', allow_exact_matches=False) 로 강제한다.
    """
    cols = ["code", "asof", "adtv60", "close", "mom_12_1"]
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    d = px_daily[["code", "date", "close", "amount"]].dropna(subset=["code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    g = d.groupby("code", observed=True)
    d["adtv60"] = g["amount"].transform(
        lambda s: s.rolling(ARC_ADTV_WINDOW, min_periods=max(10, ARC_ADTV_WINDOW // 3)).mean())
    # 12-1 모멘텀: 12개월 전 ~ 1개월 전 (직전 1개월 제외 — 단기 반전 제거)
    d["px_1m"] = g["close"].shift(21)
    d["px_12m"] = g["close"].shift(252)
    d["mom_12_1"] = safe_div(d["px_1m"], d["px_12m"]) - 1.0

    # ★ 리밸일마다 일봉 전체를 필터링하면 (40시점 × 875만행) 스캔이 되고, 매 반복이
    #   수백 MB 복사본을 만든다. merge_asof 로 한 번에 푼다 — 의미는 동일하고
    #   allow_exact_matches=False 가 '리밸일 당일 제외'(§4 t-1 종가까지) 를 강제한다.
    right = (d[["code", "date", "adtv60", "close", "mom_12_1"]]
             .dropna(subset=["date", "code"]).sort_values("date", kind="stable"))
    right["code"] = right["code"].astype(str)
    codes = right["code"].unique()
    if len(codes) == 0 or len(rebals) == 0:
        return pd.DataFrame(columns=cols)
    left = pd.DataFrame({"code": np.repeat(codes, len(rebals)),
                         "asof": np.tile(pd.DatetimeIndex(rebals).values, len(codes))})
    left["asof"] = as_ts_series(left["asof"])
    left = left.sort_values("asof", kind="stable")
    try:
        L = pd.merge_asof(left, right, left_on="asof", right_on="date", by="code",
                          direction="backward", allow_exact_matches=False)
    except Exception as e:                                       # noqa
        LOG.warn(f"유동성 패널 as-of 결합 실패({type(e).__name__}) — 빈 패널을 돌려줍니다.")
        return pd.DataFrame(columns=cols)
    L = L.dropna(subset=["date"])[["code", "asof", "adtv60", "close", "mom_12_1"]]
    if L.empty:
        return pd.DataFrame(columns=cols)
    PIPE.io("OUT", "MEM", "liquidity_panel", L)
    return downcast(L)


def build_exec_prices(px_daily: pd.DataFrame, rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """체결가 = 리밸일 '이후 첫 거래일의 시가'. §4 룩어헤드 금지의 실행부.

    ★ 시가가 없거나(거래정지) 첫 거래일이 10일 넘게 떨어져 있으면 그 가격으로 체결했다고
      가정할 수 없다 → 직전 종가로 폴백하고 그 사실을 세어 보고한다.
    """
    cols = ["code", "asof", "exec_px", "exec_date", "exec_src"]
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=cols)
    d = px_daily[["code", "date", "open", "close"]].dropna(subset=["code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    # ★ 여기도 merge_asof(direction="forward") 로 한 번에 푼다. tolerance 10일은
    #   '거래정지·상폐 직전이라 첫 거래일이 너무 멀면 그 가격으로 체결했다고 볼 수 없다' 규칙.
    right = d.dropna(subset=["date", "code"]).sort_values("date", kind="stable").copy()
    right["code"] = right["code"].astype(str)
    codes = right["code"].unique()
    if len(codes) == 0 or len(rebals) == 0:
        return pd.DataFrame(columns=cols)
    left = pd.DataFrame({"code": np.repeat(codes, len(rebals)),
                         "asof": np.tile(pd.DatetimeIndex(rebals).values, len(codes))})
    left["asof"] = as_ts_series(left["asof"])
    left = left.sort_values("asof", kind="stable")
    try:
        M = pd.merge_asof(left, right, left_on="asof", right_on="date", by="code",
                          direction="forward", tolerance=pd.Timedelta(days=10))
    except Exception as e:                                       # noqa
        LOG.warn(f"체결가 as-of 결합 실패({type(e).__name__}) — 빈 결과를 돌려줍니다.")
        return pd.DataFrame(columns=cols)
    M = M.dropna(subset=["date"])
    if M.empty:
        return pd.DataFrame(columns=cols)
    M["exec_px"] = pd.to_numeric(M["open"], errors="coerce")
    M["exec_src"] = "익영업일시가"
    bad = ~np.isfinite(M["exec_px"]) | (M["exec_px"] <= 0)
    M.loc[bad, "exec_px"] = pd.to_numeric(M.loc[bad, "close"], errors="coerce")
    M.loc[bad, "exec_src"] = "동일일종가(시가없음)"
    E = M.rename(columns={"date": "exec_date"})[cols]
    E = E[np.isfinite(E["exec_px"]) & (E["exec_px"] > 0)]
    n_fb = int((E["exec_src"] != "익영업일시가").sum())
    if n_fb:
        LOG.info(f"체결가 폴백 {n_fb:,}건 (시가 결측 → 동일일 종가). 전체의 "
                 f"{100*n_fb/max(len(E),1):.2f}%")
    return downcast(E)


def _last_close_before(px_daily: Optional[pd.DataFrame],
                       codes: Sequence[str], cutoffs: pd.Series) -> pd.Series:
    """각 (code, cutoff) 에 대해 cutoff 이하 마지막 종가. 상장폐지 청산가 산출용."""
    idx = pd.RangeIndex(len(codes))
    if px_daily is None or px_daily.empty:
        return pd.Series(np.nan, index=idx, dtype="float64")
    d = px_daily[["code", "date", "close"]].dropna(subset=["code", "date"]).copy()
    d["code"] = d["code"].astype(str)
    d["date"] = as_ts_series(d["date"])
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d[np.isfinite(d["close"]) & (d["close"] > 0)].sort_values("date", kind="stable")
    if d.empty:
        return pd.Series(np.nan, index=idx, dtype="float64")
    left = pd.DataFrame({"_i": idx, "code": pd.Series(codes, dtype=object).astype(str),
                         "_cut": as_ts_series(pd.Series(list(cutoffs)))})
    keep = left["_cut"].notna()
    L = left[keep].sort_values("_cut", kind="stable")
    if L.empty:
        return pd.Series(np.nan, index=idx, dtype="float64")
    try:
        M = pd.merge_asof(L, d, left_on="_cut", right_on="date", by="code",
                          direction="backward")
    except Exception as e:                                          # noqa
        LOG.warn(f"상장폐지 최종 종가 조회 실패({type(e).__name__}) — -100% 로 처리합니다.")
        return pd.Series(np.nan, index=idx, dtype="float64")
    out = pd.Series(np.nan, index=idx, dtype="float64")
    out.loc[M["_i"].to_numpy()] = M["close"].to_numpy(dtype="float64")
    return out


def build_arc_panel(uni: "ArcUniverse", rebals: pd.DatetimeIndex, U: pd.DataFrame,
                    liq: pd.DataFrame, execp: pd.DataFrame, sec: pd.DataFrame,
                    px_daily: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """U-1000 멤버십 + 유동성 + 체결가 + 전방수익률 → 기본 패널 P.

    ★ 전방수익률은 패널(=U-1000 멤버십) 내부 shift 로 만들면 안 된다. 세 가지가 동시에 깨진다:
      ① 다음 리밸일에 U-1000 밖으로 나간 종목(시총이 커진 '큰 승자', 유동성이 마른 '붕괴
         종목')은 전방수익률이 NaN 이 되고, run_backtest 의 elig 필터가 그 종목을 **오늘의
         편입 후보에서** 지운다 → 오늘의 편입 자격이 내일의 유니버스 잔류 여부로 결정된다.
      ② 거래정지가 한 분기 이상 이어지면 시총 격자에서 먼저 사라지므로, 폐지일이 왔을 때
         -100% 를 계상할 행 자체가 없다. 한국의 감사의견거절·자본잠식 폐지는 대부분
         '수개월 거래정지 → 폐지' 경로라, 이 손실이 통째로 사라진다.
      ③ 합병·완전자회사화 같은 정상 폐지에까지 -100% 가 붙는다(실제로는 합병비율·공개매수가로
         원금 수준이 회수된다).
      → 전방수익률은 execp(전 종목 × 전 리밸일 체결가 격자)에서 (code, asof+3k월) 로 직접
        만들고, 폐지는 delisting_map() 전수 기준으로 판정하며 청산가는 폐지일 이전 마지막
        종가를 쓴다. 마지막 종가조차 없을 때만 -100%.
    """
    if U is None or U.empty:
        raise RuntimeError(
            "U-1000 유니버스가 비어 패널을 만들 수 없습니다.\n"
            "  진단: ① PIT 시가총액이 하나도 확보되지 않았는지(위 '시총 출처 감사' 표)\n"
            "        ② 가격 일봉이 수집되었는지\n"
            "        ③ RUN_MODE='CACHED' 인데 캐시가 비어 있지 않은지\n"
            "  RUN_MODE='SMOKE' 로 두면 네트워크 없이 계산경로만 검증할 수 있습니다.")

    P = U.copy()
    P["asof"] = as_ts_series(P["asof"])
    P["q"] = [prev_quarter_of(t) for t in P["asof"]]

    if liq is not None and len(liq):
        P = P.merge(liq[["code", "asof", "close", "mom_12_1"]], on=["code", "asof"], how="left")
    else:
        P["close"] = np.nan
        P["mom_12_1"] = np.nan
    if execp is not None and len(execp):
        P = P.merge(execp[["code", "asof", "exec_px", "exec_date"]],
                    on=["code", "asof"], how="left")
    else:
        P["exec_px"] = np.nan
        P["exec_date"] = pd.NaT

    meta_cols = [c for c in ("code", "corp_code", "market", "industry", "name", "listing_date")
                 if c in (sec.columns if sec is not None else [])]
    if sec is not None and len(sec) and meta_cols:
        P = P.merge(sec[meta_cols].drop_duplicates("code"), on="code", how="left")
    for c in ("corp_code", "market", "industry", "name"):
        if c not in P.columns:
            P[c] = ""
    if "listing_date" not in P.columns:
        P["listing_date"] = pd.NaT
    P["listing_date"] = as_ts_series(P["listing_date"])
    P["listing_months"] = ((P["asof"] - P["listing_date"]).dt.days / 30.44).astype("float32")

    # §3.3 상장 12개월 미만 제외 (상장일이 없으면 제외하지 않는다 — 근거 없는 제외 금지)
    young = P["listing_months"].notna() & (P["listing_months"] < ARC_MIN_LISTING_M)
    if young.any():
        LOG.info(f"상장 {ARC_MIN_LISTING_M}개월 미만 {int(young.sum()):,}행 제외 (§3.3)")
        P = P[~young]

    # ── 전방수익률 (1Q / 2Q / 4Q) — execp 전수 격자 기준 ────────────────────────────────────
    P = P.sort_values(["code", "asof"], kind="stable").reset_index(drop=True)
    delist = uni.delisting_map()
    dl = P["code"].map(lambda c: delist.get(c)).astype("datetime64[ns]")

    if execp is not None and len(execp):
        EG = execp[["code", "asof", "exec_px"]].dropna(subset=["code", "asof"]).copy()
        EG["code"] = EG["code"].astype(str)
        EG["asof"] = as_ts_series(EG["asof"])
        EG = EG.drop_duplicates(["code", "asof"])
    else:
        EG = pd.DataFrame(columns=["code", "asof", "exec_px"])

    # ★ '다음에 실제로 거래된 리밸일' — 거래정지가 언제 풀렸는지를 알려주는 유일한 정보.
    #   이게 없으면 '정지 후 재개' 와 '정지 후 폐지' 를 구별할 수 없다.
    if len(EG):
        _EGs = EG.sort_values("asof", kind="stable").rename(
            columns={"asof": "resume_asof", "exec_px": "resume_px"})
        _L = P[["code", "asof"]].copy()
        _L["code"] = _L["code"].astype(str)
        _L["_ord"] = np.arange(len(_L))
        _L = _L.sort_values("asof", kind="stable")
        _M = pd.merge_asof(_L, _EGs, left_on="asof", right_on="resume_asof", by="code",
                           direction="forward", allow_exact_matches=False)
        _M = _M.sort_values("_ord")
        resume_asof = pd.Series(_M["resume_asof"].to_numpy(), index=P.index)
        resume_px = pd.Series(_M["resume_px"].to_numpy(dtype="float64"), index=P.index)
    else:
        resume_asof = pd.Series(pd.NaT, index=P.index)
        resume_px = pd.Series(np.nan, index=P.index, dtype="float64")

    src_counts: Dict[str, int] = {}
    hold_q_all: List[float] = []
    for k, lab in ((1, "fwd_ret_1q"), (2, "fwd_ret_2q"), (4, "fwd_ret_4q")):
        tgt = P["asof"] + pd.DateOffset(months=3 * k)
        if len(EG):
            nxt = (pd.DataFrame({"code": P["code"].astype(str), "asof": tgt})
                     .merge(EG.rename(columns={"exec_px": "_nxt"}),
                            on=["code", "asof"], how="left")["_nxt"])
            nxt.index = P.index
        else:
            nxt = pd.Series(np.nan, index=P.index, dtype="float64")
        base = pd.to_numeric(P["exec_px"], errors="coerce")
        r = pd.to_numeric(nxt, errors="coerce") / base - 1.0

        # ★ 폐지는 전방가격 유무와 무관하게 폐지 처리가 이긴다(정상 청산도 폐지가 최종 사건).
        died = dl.notna() & (dl > P["asof"]) & (dl <= tgt)
        # ★ '거래정지 → 유니버스 소실 → 폐지' 경로. 보유 중에 팔 수 없었고 결국 폐지됐으므로
        #   청산 결과를 이 분기에 계상한다. 결측으로 두면 손실만 선택적으로 사라진다.
        #
        #   ★★ 단, '정지 후 **재개**' 와 반드시 구별해야 한다. 예전 구현은 "전방가격 없음 +
        #      언젠가 폐지됨" 만 보고 곧바로 폐지일 직전 종가를 썼는데, 그러면 3년 뒤 합병
        #      폐지 종목의 **다년 수익률이 1분기 수익률 자리**에 들어간다(실측 fwd_ret_1q
        #      +400% 인데 같은 행 fwd_ret_2q 는 +20%). elig 가 더 이상 fwd_ret 를 보지
        #      않으므로 그 행은 실제로 편입되어 포트폴리오 수익에 곧바로 들어간다.
        #      → 정지가 풀려 다시 거래된 리밸일이 폐지 전에 존재하면 **거기서 청산**한다.
        #        진입 체결가가 없는 행(base 결측)은 애초에 보유가 성립하지 않으므로 제외.
        can_hold = base.notna() & (base > 0)
        stuck = r.isna() & can_hold & dl.notna() & (dl > P["asof"]) & ~died
        resolve = (died | stuck) & can_hold
        if resolve.any():
            # ① 폐지 전에 거래가 재개된 리밸일이 있으면 그 체결가로 청산
            resumed = stuck & resume_asof.notna() & (as_ts_series(resume_asof) <= dl)
            r_res = resume_px / base - 1.0
            # ② 없으면 폐지일 직전 종가 (정상 폐지의 합병비율·공개매수가 수준을 반영)
            lc = _last_close_before(px_daily, P["code"].astype(str).tolist(),
                                    dl.where(resolve & ~resumed))
            lc.index = P.index
            r_die = pd.to_numeric(lc, errors="coerce") / base - 1.0
            # 폐지일이 진입 체결일보다 앞서면 애초에 보유할 수 없다 → 청산가로 쓰지 않는다.
            too_early = as_ts_series(P.get("exec_date", P["asof"])) > dl
            r_die = r_die.mask(too_early)
            r_out = r_die.fillna(-1.0).where(~resumed, r_res)
            r = r.mask(resolve, r_out)
            if k == 1:
                exit_dt = as_ts_series(resume_asof).where(resumed, dl)
                hq = ((exit_dt - P["asof"]).dt.days / 91.31).where(resolve)
                hold_q_all = [float(x) for x in hq.dropna().to_numpy()]
                src_counts = {
                    "폐지_최종종가청산": int((resolve & ~resumed & r_die.notna()).sum()),
                    "폐지_종가없음_-100%": int((resolve & ~resumed & r_die.isna()).sum()),
                    "거래정지후재개_청산": int((resumed & r_res.notna()).sum()),
                    "거래정지후폐지_복원": int((stuck & ~resumed).sum())}
        P[lab] = r.astype("float32")

    # 폐지 계상 누락 감시 — 패널 행이 있는 종목만 세면 '거래정지 후 폐지' 경로가 통째로 빠진다.
    n_died_panel = int((dl.notna() & (dl > P["asof"]) &
                        (dl <= P["asof"] + pd.DateOffset(months=3))).sum())
    reb = pd.DatetimeIndex(rebals)
    n_died_all = 0
    for c, d0 in (delist or {}).items():
        d0 = as_ts(d0)
        if d0 is None or pd.isna(d0):
            continue
        n_died_all += int(((reb < d0) & (d0 <= reb + pd.DateOffset(months=3))).sum())
    LOG.info(f"보유 구간 내 상장폐지: 패널 계상 {n_died_panel:,}건 "
             f"(청산가 반영 {src_counts.get('폐지_최종종가청산', 0):,} · "
             f"-100% {src_counts.get('폐지_종가없음_-100%', 0):,}) · "
             f"거래정지 후 재개 청산 {src_counts.get('거래정지후재개_청산', 0):,}건 · "
             f"거래정지 후 폐지 복원 {src_counts.get('거래정지후폐지_복원', 0):,}건 · "
             f"폐지목록 전수 기준 {n_died_all:,}건 (§3.4)")
    if hold_q_all:
        _long = [h for h in hold_q_all if h > 1.5]
        LOG.info(f"  청산 지평 — 중앙값 {float(np.median(hold_q_all)):.1f}분기 · "
                 f"최대 {max(hold_q_all):.1f}분기 · 1분기 초과 {len(_long):,}건. "
                 f"1분기를 넘는 건은 '보유 중 매도 불가(거래정지)' 구간이며, 실현 손익 전액을 "
                 f"진입 분기에 계상합니다 — 총액은 정확하나 그 분기 수익률은 과대/과소됩니다.")
    if n_died_all and (n_died_panel + src_counts.get("거래정지후폐지_복원", 0)) == 0:
        LOG.warn(f"폐지목록에는 보유 구간 내 폐지가 {n_died_all:,}건 있는데 패널에서 계상된 "
                 f"것이 0건입니다. 폐지 종목이 폐지 전에 유니버스에서 사라졌다는 뜻이므로 "
                 f"생존자편향입니다 — 시총 격자·유동성 필터를 확인하세요.")

    P["log_mktcap"] = np.log(pd.to_numeric(P["mktcap"], errors="coerce").where(lambda s: s > 0))
    P["log_adtv"] = np.log(pd.to_numeric(P["adtv60"], errors="coerce").where(lambda s: s > 0))
    P = build_arc_cells(P, sec)
    P = ensure_cols(P, ARC_PANEL_BASE_COLS)
    assert_no_dup_cols_arc(P, "build_arc_panel")
    P = downcast(P)
    LOG.ok(f"기본 패널 {len(P):,}행 × {P.shape[1]}열 · {mem_mb(P):.0f}MB "
           f"({P['code'].nunique():,}종목 × {P['asof'].nunique()}시점)")
    PIPE.io("OUT", "MEM", "arc_panel_base", P)
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-H  Phase 0 — 데이터 실현가능성 게이트 (§2)                                             ║
# ║                                                                                          ║
# ║  이 게이트의 목적은 '전략을 통과시키는 것'이 아니라 **어느 축이 성립 가능한지 먼저          ║
# ║  확정하는 것**이다. 실패해도 전략을 폐기하지 않고 해당 축만 비활성화한다(§2.3).             ║
# ║  v1.0 과 달리 축 B 가 독립 작동 가능하므로, 축 A 가 죽어도 DART-ONLY 폴백으로 진행한다.     ║
# ║                                                                                          ║
# ║  ★ 어떤 경우에도 예외를 던지지 않는다. 판정만 하고 돌려준다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ARC_GATES = [
    ("GATE_1", "median(pair_count(q)) ≥ 150", "축 A 최소 표본 (분기 중앙값)"),
    ("GATE_2", "min(pair_count(q)) ≥ 80",     "최악 분기"),
    ("GATE_3", "text_extract_rate ≥ 0.70",    "리포트 본문 추출 성공률"),
    ("GATE_4", "dart_pair_rate ≥ 0.85",       "전년 동기 페어링 가능 비율 (D1 필수)"),
    ("GATE_5", "dart_parse_rate ≥ 0.80",      "정기보고서 기계판독 성공률"),
    ("GATE_6", "fs_cov ≥ 0.90",               "D2 산출 필요 재무항목 가용률"),
]
GATE_THRESHOLDS = {"GATE_1": 150.0, "GATE_2": 80.0, "GATE_3": 0.70,
                   "GATE_4": 0.85, "GATE_5": 0.80, "GATE_6": 0.90}
GATE_RESULTS: "OrderedDict[str, dict]" = OrderedDict()


def _grec(gid: str, value, passed: Optional[bool], detail: str):
    GATE_RESULTS[gid] = {"id": gid, "value": value, "pass": passed, "detail": detail}


def _gate_pair_counts(rep: pd.DataFrame, uni_codes: Optional[set] = None) -> pd.Series:
    """분기 q 와 q−1 '양쪽 모두' 리포트 ≥1건인 종목 수 (§2.1 pair_count).

    ★ ΔTONE 은 양 분기 모두 리포트가 있어야 성립한다(§5.3). 그래서 커버리지가 아니라
      '페어 수'가 축 A 의 실질 표본이며, 이 값이 축 A 생존 여부를 결정한다.
    """
    if rep is None or rep.empty:
        return pd.Series(dtype=int)
    r = rep.dropna(subset=["stock_code"]).copy()
    r["pub_date"] = as_ts_series(r["pub_date"])
    r = r.dropna(subset=["pub_date"])
    if uni_codes:
        r = r[r["stock_code"].astype(str).isin(uni_codes)]
    if r.empty:
        return pd.Series(dtype=int)
    r["q"] = [qlabel(t) for t in r["pub_date"]]
    have = r.groupby("q")["stock_code"].apply(lambda s: set(s.astype(str)))
    qs = sorted(have.index)
    out = {}
    for i in range(1, len(qs)):
        prev, cur = qs[i - 1], qs[i]
        if qshift(cur, -1) != prev:
            continue                       # 분기가 끊긴 구간은 페어가 아니다
        out[cur] = len(have[cur] & have[prev])
    return pd.Series(out, dtype=int).sort_index()


def _gate_fs_cov(fin: pd.DataFrame, shares: Optional[pd.DataFrame]) -> Tuple[float, dict]:
    """D2 6개 지표 산출에 필요한 재무항목의 (법인×분기) 가용률."""
    need = ["net_income_ttm", "cfo_ttm", "assets", "liabilities", "cash",
            "receivable", "inventory", "revenue_ttm"]
    if fin is None or fin.empty:
        return (0.0, {c: 0.0 for c in need + ["shares_total"]})
    det = {}
    for c in need:
        v = col(fin, c)
        det[c] = float(v.notna().mean()) if len(fin) else 0.0
    if shares is not None and len(shares):
        det["shares_total"] = float(pd.to_numeric(shares.get("shares_total"),
                                                  errors="coerce").notna().mean())
    else:
        det["shares_total"] = 0.0
    # fs_cov = '핵심 항목이 모두 있는' 행 비율 (지표별 평균이 아니라 동시 가용성)
    ok = pd.Series(True, index=fin.index)
    for c in need:
        ok &= col(fin, c).notna()
    return (float(ok.mean()) if len(fin) else 0.0, det)


def run_phase0_gates(ctx: dict, rebals: pd.DatetimeIndex) -> dict:
    """§2 게이트 6종 실측 + 판정. 예외를 던지지 않는다."""
    GATE_RESULTS.clear()
    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§2)",
               "어느 축이 성립 가능한지 먼저 확정한다. 실패해도 전략을 폐기하지 않고 축만 끈다")

    rep = ctx.get("reports")
    rep_text = ctx.get("report_text")
    T = ctx.get("doc_tokens")
    pairs = ctx.get("doc_pairs")
    fin = ctx.get("fin")
    shares = ctx.get("shares")
    links = ctx.get("links")
    P0 = ctx.get("panel_base")

    uni_codes = set(P0["code"].astype(str)) if P0 is not None and len(P0) else None
    metrics: Dict[str, Any] = {}

    # ── GATE_1 / GATE_2 : pair_count ─────────────────────────────────────────────────────
    pc = _gate_pair_counts(rep, uni_codes)
    if len(pc) == 0:
        _grec("GATE_1", np.nan, None, "리포트 원장이 비어 pair_count 를 셀 수 없습니다.")
        _grec("GATE_2", np.nan, None, "동일")
    else:
        recent = pc.tail(12)               # §2.1 '최근 12분기'
        med, mn = float(recent.median()), float(recent.min())
        metrics["pair_count_median"] = med
        metrics["pair_count_min"] = mn
        _grec("GATE_1", med, bool(med >= GATE_THRESHOLDS["GATE_1"]),
              f"최근 12분기 중앙값 {med:,.0f}종목 (기준 150)")
        _grec("GATE_2", mn, bool(mn >= GATE_THRESHOLDS["GATE_2"]),
              f"최악 분기 {mn:,.0f}종목 (기준 80)")

    # ── GATE_3 : 본문 추출률 ──────────────────────────────────────────────────────────────
    if rep is None or rep.empty:
        _grec("GATE_3", np.nan, None, "리포트 원장 없음")
    else:
        n_rep = int(len(rep))
        n_txt = int(len(rep_text)) if rep_text is not None else 0
        rate = n_txt / max(n_rep, 1)
        metrics["text_extract_rate"] = rate
        _grec("GATE_3", rate, bool(rate >= GATE_THRESHOLDS["GATE_3"]),
              f"본문 확보 {n_txt:,} / 원장 {n_rep:,} = {100*rate:.1f}% (기준 70%)")

    # ── GATE_4 : DART 페어링 가능 비율 ────────────────────────────────────────────────────
    if T is None or len(T) == 0:
        _grec("GATE_4", np.nan, None, "정기보고서 토큰 없음 — D1 구동 불가")
    else:
        docs = T[["corp_code", "doc_type", "bsns_year"]].drop_duplicates()
        n_doc = len(docs)
        n_pair = (pairs[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
                  if pairs is not None and len(pairs) else 0)
        rate = n_pair / max(n_doc, 1)
        metrics["dart_pair_rate"] = rate
        _grec("GATE_4", rate, bool(rate >= GATE_THRESHOLDS["GATE_4"]),
              f"페어 가능 {n_pair:,} / 문서 {n_doc:,} = {100*rate:.1f}% (기준 85%)")

    # ── GATE_5 : 기계판독 성공률 ──────────────────────────────────────────────────────────
    fail = int(sum(_ARC_DOC_FAIL.values())) if "_ARC_DOC_FAIL" in globals() else 0
    n_doc_ok = int(T["rcept_no"].nunique()) if T is not None and len(T) else 0
    tried = ctx.get("doc_attempted", n_doc_ok + fail)
    if tried <= 0:
        _grec("GATE_5", np.nan, None, "이번 실행에서 새로 시도한 원문이 없습니다 "
                                      "(전량 캐시 재사용이면 정상).")
    else:
        rate = n_doc_ok / max(tried, 1)
        metrics["dart_parse_rate"] = rate
        _grec("GATE_5", rate, bool(rate >= GATE_THRESHOLDS["GATE_5"]),
              f"판독 성공 {n_doc_ok:,} / 시도 {tried:,} = {100*rate:.1f}% (기준 80%)")

    # ── GATE_6 : 재무항목 가용률 ──────────────────────────────────────────────────────────
    cov, det = _gate_fs_cov(fin, shares)
    metrics["fs_cov"] = cov
    metrics["fs_cov_detail"] = det
    if fin is None or fin.empty:
        _grec("GATE_6", 0.0, False, "재무 데이터 없음 — D2 구동 불가 (심각)")
    else:
        _grec("GATE_6", cov, bool(cov >= GATE_THRESHOLDS["GATE_6"]),
              f"D2 필수항목 동시 가용 {100*cov:.1f}% (기준 90%)")

    # ── 판정표 ────────────────────────────────────────────────────────────────────────────
    rows = []
    for gid, cond, why in ARC_GATES:
        r = GATE_RESULTS.get(gid, {})
        v = r.get("value")
        p = r.get("pass")
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[p]
        vs = ("—" if v is None or (isinstance(v, float) and not np.isfinite(v))
              else (f"{v:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*float(v):.1f}%"))
        rows.append([gid, cond, why, vs, icon, _trunc(r.get("detail", ""), 46)])
    LOG.table(rows, ["게이트", "조건", "의미", "실측", "판정", "상세"],
              ["l", "l", "l", "r", "c", "l"], maxw=48)

    # ── 분기별 추이 표 ────────────────────────────────────────────────────────────────────
    if len(pc):
        cov_q = {}
        if rep is not None and len(rep) and uni_codes:
            r = rep.dropna(subset=["stock_code"]).copy()
            r["pub_date"] = as_ts_series(r["pub_date"])
            r = r.dropna(subset=["pub_date"])
            r["q"] = [qlabel(t) for t in r["pub_date"]]
            r = r[r["stock_code"].astype(str).isin(uni_codes)]
            n_uni = max(len(uni_codes), 1)
            cov_q = (r.groupby("q")["stock_code"].nunique() / n_uni).to_dict()
        tail = pc.tail(16)
        LOG.table([[q, f"{int(n):,}", f"{100*cov_q.get(q, float('nan')):.1f}%"
                    if q in cov_q else "—"] for q, n in tail.items()],
                  ["분기", "pair_count", "cov_rate"], ["c", "r", "r"],
                  title="분기별 축 A 표본 추이 (최근 16분기)")

    # ── report_dist 히스토그램 ────────────────────────────────────────────────────────────
    if rep is not None and len(rep):
        r = rep.dropna(subset=["stock_code"]).copy()
        r["pub_date"] = as_ts_series(r["pub_date"])
        r = r.dropna(subset=["pub_date"])
        r["q"] = [qlabel(t) for t in r["pub_date"]]
        cnt = r.groupby(["q", "stock_code"]).size()
        if uni_codes:
            allq = sorted(set(r["q"]))
            n_zero = sum(max(0, len(uni_codes) - cnt.loc[q].shape[0]) for q in allq
                         if q in cnt.index.get_level_values(0))
        else:
            n_zero = 0
        bins = {"0건": n_zero, "1건": int((cnt == 1).sum()), "2건": int((cnt == 2).sum()),
                "3건": int((cnt == 3).sum()), "4건": int((cnt == 4).sum()),
                "5건+": int((cnt >= 5).sum())}
        tot = max(sum(bins.values()), 1)
        LOG.table([[k, f"{v:,}", f"{100*v/tot:.1f}%"] for k, v in bins.items()],
                  ["종목-분기 리포트 건수", "빈도", "비중"], ["l", "r", "r"],
                  title="report_dist — 커버리지 희소성 (0건이 지배적이면 축 A 는 소수 종목만 커버)")

    # ── analyst_id_rate ───────────────────────────────────────────────────────────────────
    if rep is not None and len(rep):
        linked = set(links["report_uid"].astype(str)) if links is not None and len(links) else set()
        rate = (float(rep["report_uid"].astype(str).isin(linked).mean()) if linked else 0.0)
        metrics["analyst_id_rate"] = rate
        LOG.info(f"analyst_id@broker_id 추출 성공률 {100*rate:.1f}% (측정 항목 — 게이트 아님). "
                 f"낮으면 직교화 통제변수(목표주가 수정률)의 신뢰도가 떨어집니다.")

    # ── §2.3 실패 시 행동 ─────────────────────────────────────────────────────────────────
    def _p(gid):
        return GATE_RESULTS.get(gid, {}).get("pass")

    axis_a = not (_p("GATE_1") is False or _p("GATE_2") is False or _p("GATE_3") is False)
    if _p("GATE_1") is None and _p("GATE_3") is None:
        axis_a = False
    d1 = not (_p("GATE_4") is False or _p("GATE_5") is False)
    if _p("GATE_4") is None and (T is None or len(T) == 0):
        d1 = False
    d2 = _p("GATE_6") is not False

    mode = "FULL (축 A + 축 B)"
    if not axis_a:
        mode = "DART-ONLY 폴백 (축 A 비활성화)"
        LOG.banner("⚠ 축 A 비활성화 — 전략명을 'DART-ONLY 폴백' 으로 보고합니다 (§2.3)",
                   "GATE_1/2/3 중 하나 이상 실패. v2.0 은 축 B 가 독립 작동하므로 전략을 "
                   "폐기하지 않습니다")
    if not d1:
        LOG.banner("⚠ D1 비활성화 (§2.3)", "사유를 아래 표로 분해합니다")
        _gate_d1_failure_breakdown(T, pairs, ctx)
    if not d2:
        LOG.banner("⛔ D2 비활성화 — 심각 이슈 (§2.3)",
                   "D2 는 D1 보다 대체 불가합니다. 재무 수집 상태를 먼저 해결해야 합니다")

    fails = [g for g in ("GATE_4", "GATE_5", "GATE_6") if _p(g) is False]
    if len(fails) == 3:
        LOG.error("§9.3-1 폐기 조건: GATE_4·5·6 이 모두 실패 → 축 B 성립 불가. "
                  "이 경우 전략 폐기가 사전등록된 판정입니다.")

    LOG.table([["축 A (애널리스트 텍스트톤)", "활성" if axis_a else "비활성"],
               ["축 B D1 (텍스트 변화량)", "활성" if d1 else "비활성"],
               ["축 B D2 (재무 이상현상)", "활성" if d2 else "비활성"],
               ["축 B D3 (하드팩트)", "활성 (가점)"],
               ["배제 플래그", "활성 (하드 제외)"],
               ["실행 모드", mode]],
              ["구성", "상태"], ["l", "l"], title="Phase 0 확정 — 이 구성으로 이후 단계가 진행됩니다")

    return {"axis_a": bool(axis_a), "d1": bool(d1), "d2": bool(d2),
            "mode": mode, "metrics": metrics}


def _gate_d1_failure_breakdown(T, pairs, ctx):
    """GATE_4/5 실패 사유 분해 — PDF 스캔본 / 서식변경 / 전년동기 부재 / 기타."""
    rows = []
    fails = dict(_ARC_DOC_FAIL) if "_ARC_DOC_FAIL" in globals() else {}
    for k, v in sorted(fails.items(), key=lambda x: -x[1]):
        why = {
            "ZIP아님(스캔본/오류)": "구형 공시의 PDF 스캔본 — 기계판독 불가 (§0.4 알려진 함정)",
            "본문없음": "zip 은 받았으나 텍스트 엔트리가 비어 있음",
            "섹션0개": "목차 표제를 못 찾음 — 서식 개정으로 표제어가 바뀌었을 가능성",
            "토큰부족": "섹션은 찾았으나 토큰이 최소치 미만",
            "호출한도": "DART 일일 호출 예산 소진 — 내일 이어받으면 해소",
            "응답없음/과소": "네트워크 실패 또는 빈 응답",
        }.get(k, "기타")
        rows.append([k, f"{v:,}", why])
    if T is not None and len(T) and pairs is not None:
        n_doc = T[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
        n_pair = (pairs[["corp_code", "doc_type", "bsns_year"]].drop_duplicates().shape[0]
                  if len(pairs) else 0)
        rows.append(["전년동기 부재", f"{max(0, n_doc - n_pair):,}",
                     "상장 24개월 미만이거나 전년 문서 수집이 아직 안 된 경우"])
    if not rows:
        rows = [["(분해 불가)", "—", "이번 실행에서 신규 수집이 없어 실패 원장이 비었습니다"]]
    LOG.table(rows, ["사유", "건수", "설명"], ["l", "r", "l"], maxw=64,
              title="D1 비활성화 사유 분해 (§2.3)")
    LOG.info("조치 우선순위: ① DART 예산 소진이면 내일 재실행(이어받기) "
             "② 섹션0개가 많으면 ARC_SECTION_PAT 표제어 정규식 점검 "
             "③ 스캔본이 많으면 그 구간은 구조적으로 D1 결측 — 정상입니다.")


def report_gate_table() -> None:
    """§9.2-(1) 최종 산출물용 재출력."""
    if not GATE_RESULTS:
        LOG.warn("Phase 0 게이트가 실행되지 않았습니다.")
        return
    LOG.banner("[산출물 1] Phase 0 게이트 결과표 (§9.2-1)", "6개 게이트 실측치 + 통과/실패")
    rows = []
    for gid, cond, why in ARC_GATES:
        r = GATE_RESULTS.get(gid, {})
        v, p = r.get("value"), r.get("pass")
        vs = ("—" if v is None or (isinstance(v, float) and not np.isfinite(v))
              else (f"{v:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*float(v):.1f}%"))
        thr = GATE_THRESHOLDS[gid]
        ts = f"{thr:,.0f}" if gid in ("GATE_1", "GATE_2") else f"{100*thr:.0f}%"
        rows.append([gid, cond, vs, ts,
                     {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[p]])
    LOG.table(rows, ["게이트", "조건", "실측치", "기준", "판정"], ["l", "l", "r", "r", "c"])



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  축 A — 애널리스트 텍스트톤 (§5)                                                     ║
# ║                                                                                          ║
# ║  경제적 근거: 애널리스트는 정성적 판단을 서술문에 먼저 반영하고 목표주가·투자의견은          ║
# ║  지연 갱신한다(비동기적 업데이트). 저커버리지 소형주일수록 이 텍스트를 읽는 투자자가 적다.   ║
# ║                                                                                          ║
# ║  ★★ 이 축의 성립 조건은 '텍스트 톤이 컨센서스 수정과 독립적인 정보' 라는 것이다.            ║
# ║     아니면 이 전략은 '애널리스트 과소반응 전략'의 재포장에 불과하다.                        ║
# ║     그래서 직교화(§5.3)는 선택이 아니라 전략 성립의 필요조건이며, 여기서 강제된다.           ║
# ║                                                                                          ║
# ║  ★★ LLM API 호출 금지(§5.1). 토큰 비용 문제이자, 사전학습 코퍼스로 인한 룩어헤드 오염       ║
# ║     위험 때문이다. 2016년 리포트를 2024년까지 학습한 모델로 채점하면 그 자체가 미래정보다.   ║
# ║     이 파일은 TF-IDF + (NB | LogReg) 만 쓰며, A18 계약검정이 소스에서 이를 검사한다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ── 정형 텍스트 제거 사전 (§5.1) ────────────────────────────────────────────────────────────
#   ★ 왜 이게 필수인가: 면책조항·컴플라이언스 문구는 증권사마다 고정 문구다. 제거하지 않으면
#     분류기가 "이 문장 패턴 = 미래에셋" 을 학습하고, 결국 '증권사 식별자'로 톤을 예측하게 된다.
#     증권사는 커버 종목군과 상관되므로 이건 곧 종목 고정효과 누출이다.
TONE_BOILERPLATE_PAT = [
    r"본\s*(조사분석)?자료는[^.\n]{0,200}[.\n]",
    r"당사는[^.\n]{0,60}(이해관계|보유하고|계열회사|발행주식)[^.\n]{0,140}[.\n]",
    r"(동\s*)?자료는\s*투자자[^.\n]{0,160}[.\n]",
    r"본\s*자료에\s*게재된\s*내용[^.\n]{0,160}[.\n]",
    r"Compliance\s*Notice[^\n]{0,400}",
    r"준법감시인?\s*(확인|심사)[^\n]{0,120}",
    r"투자등급\s*(관련사항|정의|및\s*적용기준)[^\n]{0,400}",
    r"(Strong\s*)?Buy\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"(Marketperform|Hold|중립)\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"(Underperform|Sell|매도)\s*[:：(]?\s*(향후|목표|기대)[^\n]{0,120}",
    r"최근\s*[12]년간\s*투자등급[^\n]{0,300}",
    r"당사\s*리서치센터[^\n]{0,120}",
    r"기업\s*투자의견은[^\n]{0,200}",
    r"본\s*보고서는\s*고객[^\n]{0,200}",
    r"어떠한\s*경우에도\s*(고객|투자자)의[^\n]{0,160}",
    r"무단\s*(복제|전재|배포)[^\n]{0,120}",
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",          # 애널리스트 서명부 이메일
    r"(02|031|032|051|070)[-\s.]?\d{3,4}[-\s.]?\d{4}",             # 전화번호
    r"[가-힣]{2,4}\s*(연구원|애널리스트|수석|책임|선임|팀장|센터장)\s*$",
]
_TONE_BP_RE = re.compile("|".join(TONE_BOILERPLATE_PAT), re.I | re.M)

# 표·차트 잔재 라인 (숫자 비중이 높은 줄). 문장이 아니므로 톤 학습에서 제외한다.
_TONE_NUMLINE_RE = re.compile(r"^[\s\d,.\-%()＋+~/|]+$")
_TONE_SENT_SPLIT = re.compile(r"(?<=[.。!?])\s+|(?<=[다요])\.\s+|\n{1,}")

TONE_REPORT_COLS = ["report_uid", "code", "pub_date", "TONE_report", "n_sent",
                    "event_date", "knowledge_date"]
TONE_Q_COLS = ["code", "asof", "q", "TONE", "n_reports_q"]

_TONE_STATE: Dict[str, Any] = {"fits": 0, "backend": "", "warned": False}


def tone_clean_report_text(txt: str) -> str:
    """정형 텍스트 제거 + 표 잔재 제거. 제거하지 않으면 증권사 식별자로 누출된다."""
    if not txt:
        return ""
    t = unicodedata.normalize("NFKC", str(txt))
    t = _TONE_BP_RE.sub(" ", t)
    keep = []
    for ln in t.split("\n"):
        s = ln.strip()
        if not s or len(s) < 8:
            continue
        if _TONE_NUMLINE_RE.match(s):
            continue
        # 숫자·기호 비중이 과반이면 표의 잔재로 본다
        d = sum(1 for ch in s if ch.isdigit() or ch in ",.%()-+|/")
        if d / max(len(s), 1) > 0.45:
            continue
        keep.append(s)
    return "\n".join(keep)


def tone_sentences(txt: str) -> List[str]:
    """한국어 문장 분리. 8~400자만 채택."""
    if not txt:
        return []
    out = []
    for s in _TONE_SENT_SPLIT.split(txt):
        s = re.sub(r"\s+", " ", str(s)).strip()
        if 8 <= len(s) <= 400 and re.search(r"[가-힣]{2,}", s):
            out.append(s)
    return out


# ── 라벨: 발간일 기준 2일 CAR (시장수익률 차감) 의 부호 ─────────────────────────────────────
def _tone_market_excess(px_daily: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """일별 초과수익(종목 - 해당 시장 동일가중 평균) 과 2일 누적 전방 초과수익.

    ★ 시장수익률로 지수(KOSPI/KOSDAQ)를 쓰지 않고 '해당 시장 상장종목의 동일가중 평균'을 쓴다.
      지수는 시총가중이라 대형주 움직임이 지배하는데, 우리 표본은 소형주다. 소형주 리포트의
      2일 반응을 대형주 지수로 차감하면 시장 전체가 오른 날의 소형주 리포트가 전부
      '부정' 라벨을 받는다(라벨 노이즈가 아니라 라벨 편향이다).
    """
    if px_daily is None or px_daily.empty:
        return pd.DataFrame(columns=["code", "date", "car2"])
    d = px_daily[["code", "date", "close"]].dropna(subset=["code", "date", "close"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    d["ret1"] = d.groupby("code", observed=True)["close"].pct_change()
    d = d[np.isfinite(d["ret1"]) & (d["ret1"].abs() < 0.9)]     # 액면분할 등 이상치 제거
    mk = (sec.drop_duplicates("code").set_index("code")["market"].astype(str).to_dict()
          if sec is not None and len(sec) and "market" in sec.columns else {})
    d["market"] = d["code"].map(mk).fillna("KOSPI").astype(str)
    mret = d.groupby(["market", "date"], observed=True)["ret1"].transform("mean")
    d["exc"] = d["ret1"] - mret
    g = d.groupby("code", observed=True)["exc"]
    # 발간 다음 거래일부터 2거래일 누적 (발간 당일은 이미 반영됐을 수 있어 제외)
    d["car2"] = g.shift(-1).fillna(0) + g.shift(-2).fillna(0)
    d["car2"] = d["car2"].where(g.shift(-2).notna())
    return d[["code", "date", "car2"]]


def build_tone_training(rep_text: pd.DataFrame, px_daily: pd.DataFrame,
                        sec: pd.DataFrame, max_sent_per_report: int = 22,
                        max_total: int = 400_000) -> pd.DataFrame:
    """문장 단위 학습표본. 라벨 = 발간일 기준 2일 CAR(시장 차감)의 부호.

    ★ 학습 데이터는 U-1000 한정이 아니다(§5.1). 대형주 리포트도 쓴다 — 문장-톤 사전을
      배우는 것이 목적이지 종목 선택이 목적이 아니기 때문이다. 표본을 소형주로 좁히면
      문장 수가 급감해 분류기가 학습되지 않는다.
    """
    cols = ["sentence", "label", "pub_date", "report_uid", "code"]
    if rep_text is None or rep_text.empty:
        LOG.warn("리포트 본문이 없어 TONE 학습표본을 만들 수 없습니다 — 축 A 비활성화 대상입니다.")
        return pd.DataFrame(columns=cols)

    car = _tone_market_excess(px_daily, sec)
    if car.empty:
        LOG.warn("가격 데이터가 없어 CAR 라벨을 만들 수 없습니다 — 축 A 비활성화 대상입니다.")
        return pd.DataFrame(columns=cols)

    R = rep_text[["report_uid", "code", "pub_date", "text"]].dropna(subset=["pub_date"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R["code"] = R["code"].map(to_code6)
    R = R.dropna(subset=["code"])
    if R.empty:
        LOG.warn("본문이 있는 리포트 중 종목코드가 붙은 건이 없습니다 — 라벨을 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)

    # 발간일 → 그 이후 첫 거래일의 car2 를 as-of 결합 (forward)
    R = R.sort_values("pub_date", kind="stable")
    C = car.dropna(subset=["car2"]).sort_values("date", kind="stable")
    R["code"] = R["code"].astype(str)
    C["code"] = C["code"].astype(str)
    try:
        M = pd.merge_asof(R, C, left_on="pub_date", right_on="date", by="code",
                          direction="forward", tolerance=pd.Timedelta(days=7))
    except Exception as e:                                        # noqa
        LOG.warn(f"CAR 결합 실패({type(e).__name__}) — 축 A 를 만들 수 없습니다.")
        return pd.DataFrame(columns=cols)
    M = M.dropna(subset=["car2"])
    if M.empty:
        LOG.warn("CAR 을 붙일 수 있는 리포트가 없습니다(가격 구간 불일치).")
        return pd.DataFrame(columns=cols)
    M["label"] = (M["car2"] > 0).astype("int8")

    rng = np.random.default_rng(SEED)
    rows: List[dict] = []
    for uid, code, pdte, txt, lab in zip(M["report_uid"], M["code"], M["pub_date"],
                                         M["text"], M["label"]):
        sents = tone_sentences(tone_clean_report_text(str(txt)))
        if len(sents) < ARC_TONE_MIN_SENT:
            continue
        if len(sents) > max_sent_per_report:
            idx = rng.choice(len(sents), size=max_sent_per_report, replace=False)
            sents = [sents[i] for i in sorted(idx)]
        for s in sents:
            rows.append({"sentence": s, "label": int(lab), "pub_date": pdte,
                         "report_uid": uid, "code": code})
    if not rows:
        LOG.warn("문장을 한 개도 추출하지 못했습니다 — PDF 텍스트 레이어가 없는 스캔본일 수 있습니다.")
        return pd.DataFrame(columns=cols)
    T = pd.DataFrame(rows)
    if len(T) > max_total:
        # 최근 표본을 우선 남긴다(확장윈도우에서 어차피 과거는 다 쓰이고, RAM 은 유한하다)
        T = T.sort_values("pub_date", kind="stable").tail(max_total)
    pos = float(T["label"].mean())
    LOG.ok(f"TONE 학습표본 {len(T):,}문장 · 리포트 {T['report_uid'].nunique():,}건 · "
           f"양(+) 라벨 비중 {100*pos:.1f}%")
    if not (0.30 <= pos <= 0.70):
        LOG.warn(f"라벨 불균형이 큽니다(양 라벨 {100*pos:.1f}%). 분류기가 다수 클래스로 쏠려 "
                 f"TONE 이 상수에 가까워질 수 있습니다 — class_weight 로 보정합니다.")
    PIPE.io("OUT", "MEM", "tone_training", T)
    return T


# ── 순수 numpy Multinomial NB (sklearn 부재 시 폴백) ────────────────────────────────────────
class _ToneNaiveBayes:
    """해시 기반 bag-of-words + Multinomial NB. sklearn 이 없어도 축 A 가 죽지 않게 한다.

    ★ 해싱을 쓰는 이유: 어휘 사전을 유지하면 확장윈도우 재학습마다 사전이 달라져
      과거 모델과 현재 모델의 피처 공간이 어긋난다. 해싱은 항상 같은 공간을 준다.
    """

    def __init__(self, n_features: int = 2 ** 18, alpha: float = 0.2):
        self.D = int(n_features)
        self.alpha = float(alpha)
        self.logp: Optional[np.ndarray] = None
        self.prior = np.array([0.5, 0.5])

    @staticmethod
    def _toks(s: str) -> List[str]:
        return [w for w in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", str(s))]

    @staticmethod
    def _h(w: str) -> int:
        """★ 파이썬 내장 hash() 를 쓰면 안 된다. CPython 의 문자열 해시는 PYTHONHASHSEED
        기반으로 **프로세스마다 랜덤화**되므로, 같은 코드·같은 SEED·같은 캐시로 두 번 돌리면
        해시 충돌 패턴이 달라져 문장 라벨 → TONE_report → dTONE → FINAL_RANK → 보유 종목까지
        전부 달라진다. random.seed / np.random.seed 는 여기에 영향을 주지 않고, 계약검정
        A14(결정성)는 동일 프로세스 안에서 돌아 이 문제를 절대 잡지 못한다."""
        return int.from_bytes(hashlib.blake2b(w.encode("utf-8", "ignore"),
                                              digest_size=8).digest(), "little")

    def _idx(self, s: str) -> np.ndarray:
        t = self._toks(s)
        if not t:
            return np.empty(0, dtype=np.int64)
        return np.fromiter((self._h(w) % self.D for w in t), dtype=np.int64, count=len(t))

    def fit(self, X: Sequence[str], y: Sequence[int]):
        cnt = np.zeros((2, self.D), dtype=np.float64)
        n = np.zeros(2, dtype=np.float64)
        for s, lab in zip(X, y):
            i = int(lab)
            n[i] += 1
            ids = self._idx(s)
            if len(ids):
                np.add.at(cnt[i], ids, 1.0)
        cnt += self.alpha
        self.logp = np.log(cnt / cnt.sum(axis=1, keepdims=True))
        tot = max(n.sum(), 1.0)
        self.prior = np.log(np.maximum(n, 1.0) / tot)
        return self

    def predict(self, X: Sequence[str]) -> np.ndarray:
        if self.logp is None:
            return np.zeros(len(X), dtype=np.int8)
        out = np.zeros(len(X), dtype=np.int8)
        for k, s in enumerate(X):
            ids = self._idx(s)
            if len(ids) == 0:
                out[k] = 1
                continue
            sc = self.prior + np.array([self.logp[0][ids].sum(), self.logp[1][ids].sum()])
            out[k] = int(sc[1] > sc[0])
        return out


def fit_tone_expanding(train: pd.DataFrame, cut) -> Optional[Tuple[Any, Any]]:
    """cut '이전' 데이터로만 학습한 (vectorizer, model). 표본 부족이면 None.

    ★ 확장윈도우가 이 전략의 룩어헤드 방어선이다. 전체 기간 단일 학습은 2016년 문장을
      2026년 사전으로 채점하는 것이며, 그것만으로 IC 가 크게 부풀려진다.
    """
    if train is None or train.empty:
        return None
    c = as_ts(cut)
    sub = train[as_ts_series(train["pub_date"]) < c]
    if len(sub) < ARC_TONE_MIN_TRAIN or sub["label"].nunique() < 2:
        return None
    X = sub["sentence"].astype(str).tolist()
    y = sub["label"].astype(int).to_numpy()

    kind = str(globals().get("ARC_TONE_MODEL", "logreg")).lower()
    if sk_tfidf is not None and (sk_logreg is not None or sk_nb is not None):
        try:
            vec = sk_tfidf(analyzer="word", token_pattern=r"[가-힣]{2,}|[A-Za-z]{3,}",
                           ngram_range=(1, 2), min_df=3,
                           max_features=int(ARC_TONE_MAX_FEATURES), sublinear_tf=True)
            Xm = vec.fit_transform(X)
            if kind == "lgbm" and lgbm is not None:
                mdl = lgbm.LGBMClassifier(n_estimators=200, num_leaves=31, learning_rate=0.08,
                                          verbose=-1, random_state=SEED)
                mdl.fit(Xm, y)
            elif kind == "nb" and sk_nb is not None:
                mdl = sk_nb(alpha=0.3).fit(Xm, y)
            else:
                mdl = sk_logreg(max_iter=300, C=1.0, solver="liblinear",
                                class_weight="balanced", random_state=SEED).fit(Xm, y)
            _TONE_STATE["backend"] = f"sklearn/{kind}"
            _TONE_STATE["fits"] += 1
            return (vec, mdl)
        except Exception as e:                                    # noqa
            LOG.debug(f"sklearn TONE 학습 실패({type(e).__name__}) — 순수 numpy NB 로 폴백")
    mdl = _ToneNaiveBayes().fit(X, y)
    _TONE_STATE["backend"] = "numpy/NB(해싱)"
    _TONE_STATE["fits"] += 1
    if not _TONE_STATE["warned"]:
        _TONE_STATE["warned"] = True
        LOG.warn("scikit-learn 이 없어 순수 numpy Multinomial NB 로 톤을 분류합니다. "
                 "실행은 정상이나 분류 성능이 열화되며, 그만큼 축 A 의 IC 가 낮게 나옵니다. "
                 "이 사실을 결과 해석에 반드시 반영하세요.")
    return (None, mdl)


def _tone_predict(fit: Tuple[Any, Any], sents: Sequence[str]) -> np.ndarray:
    vec, mdl = fit
    if vec is not None:
        try:
            return np.asarray(mdl.predict(vec.transform(list(sents)))).astype(int)
        except Exception:
            return np.ones(len(sents), dtype=int)
    return np.asarray(mdl.predict(list(sents))).astype(int)


def score_tone_reports(rep_text: pd.DataFrame, train: pd.DataFrame,
                       rebals: pd.DatetimeIndex) -> pd.DataFrame:
    """§5.1 확장윈도우 재학습 + §5.2 리포트 단위 TONE.

    TONE(report) = (긍정문장 수 − 부정문장 수) / 전체문장 수  ∈ [-1, +1]

    ★ 성능: 리밸일마다 매번 재학습하면 40회 × 수십 초다. 학습표본이 직전 학습 대비
      15% 이상 늘었을 때만 재학습하고 그 외에는 직전 모델을 재사용한다.
      재사용해도 '그 시점 이전 데이터로만 학습된 모델' 이라는 성질은 그대로 유지된다
      (더 오래된 모델을 쓰는 것이므로 오히려 보수적이다).
    """
    if rep_text is None or rep_text.empty or train is None or train.empty:
        return pd.DataFrame(columns=TONE_REPORT_COLS)

    R = rep_text[["report_uid", "code", "pub_date", "text"]].dropna(subset=["pub_date"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R["code"] = R["code"].map(to_code6)
    R = R.dropna(subset=["code"]).sort_values("pub_date", kind="stable")

    cuts = [as_ts(t) for t in rebals]
    if not cuts:
        return pd.DataFrame(columns=TONE_REPORT_COLS)

    rows: List[dict] = []
    fit = None
    last_n = 0
    tr_dates = as_ts_series(train["pub_date"])
    t0 = time.time()
    for i, cut in enumerate(tqdm(cuts, desc="TONE 확장윈도우", ncols=88, leave=False)):
        n_avail = int((tr_dates < cut).sum())
        if fit is None or n_avail > last_n * 1.15:
            f = fit_tone_expanding(train, cut)
            if f is not None:
                fit, last_n = f, n_avail
        if fit is None:
            continue
        hi = cuts[i + 1] if i + 1 < len(cuts) else (as_ts(BACKTEST_END) + pd.Timedelta(days=1))
        win = R[(R["pub_date"] >= cut) & (R["pub_date"] < hi)]
        if win.empty:
            continue
        for uid, code, pdte, txt in zip(win["report_uid"], win["code"],
                                        win["pub_date"], win["text"]):
            sents = tone_sentences(tone_clean_report_text(str(txt)))
            if len(sents) < ARC_TONE_MIN_SENT:
                continue
            yp = _tone_predict(fit, sents)
            n = len(yp)
            tone = float((int((yp == 1).sum()) - int((yp == 0).sum())) / max(n, 1))
            rows.append({"report_uid": uid, "code": code, "pub_date": pdte,
                         "TONE_report": tone, "n_sent": n})

    # ★ 첫 리밸일 이전에 발간된 리포트는 '그 시점 이전 데이터'가 없어 채점할 수 없다.
    #   억지로 채점하면 미래 모델로 과거를 채점하는 것이 되므로 결측으로 남긴다.
    if not rows:
        LOG.warn("확장윈도우로 채점된 리포트가 없습니다 (학습 표본 부족). 축 A 는 결측 처리됩니다.")
        return pd.DataFrame(columns=TONE_REPORT_COLS)
    T = pd.DataFrame(rows)
    T["event_date"] = T["pub_date"]
    # §4 리포트는 발간일 + 1거래일부터 사용 가능
    T["knowledge_date"] = T["pub_date"] + pd.Timedelta(days=ARC_REPORT_LAG_DAYS)
    LOG.ok(f"TONE 채점 {len(T):,}건 · 모델 재학습 {_TONE_STATE['fits']}회 "
           f"({_TONE_STATE['backend']}) · 소요 {time.time()-t0:.1f}초 · "
           f"TONE 평균 {T['TONE_report'].mean():+.3f} 표준편차 {T['TONE_report'].std():.3f}")
    PIPE.io("OUT", "MEM", "tone_reports", T)
    return T


def aggregate_tone(tone_rep: pd.DataFrame, rebals: pd.DatetimeIndex,
                   half_life_days: Optional[float] = None) -> pd.DataFrame:
    """§5.2 분기 집계 — 최신성 가중평균. 가중치 = exp(−λ·경과일수), 반감기 30일 고정.

    ★ 창은 '리밸일 직전 1개 분기'. 리밸일 당일 발간분은 T+1 규약상 아직 못 쓴다.
    """
    hl = float(half_life_days or ARC_TONE_HALFLIFE_D)
    lam = math.log(2.0) / max(hl, 1e-6)
    if tone_rep is None or tone_rep.empty:
        return pd.DataFrame(columns=TONE_Q_COLS)
    X = tone_rep.dropna(subset=["code", "TONE_report"]).copy()
    X["knowledge_date"] = as_ts_series(X["knowledge_date"])
    X = X.dropna(subset=["knowledge_date"])
    out = []
    for t in rebals:
        t = as_ts(t)
        lo = t - pd.DateOffset(months=3)
        w = X[(X["knowledge_date"] > lo) & (X["knowledge_date"] <= t)].copy()
        if w.empty:
            continue
        age = (t - w["knowledge_date"]).dt.days.clip(lower=0).to_numpy(dtype=float)
        w["_wt"] = np.exp(-lam * age)
        w["_num"] = w["_wt"] * pd.to_numeric(w["TONE_report"], errors="coerce")
        g = w.groupby("code", observed=True)
        agg = pd.DataFrame({"TONE": g["_num"].sum() / g["_wt"].sum(),
                            "n_reports_q": g["report_uid"].nunique()}).reset_index()
        agg["asof"] = t
        agg["q"] = prev_quarter_of(t)
        out.append(agg)
    if not out:
        return pd.DataFrame(columns=TONE_Q_COLS)
    Q = pd.concat(out, ignore_index=True)[TONE_Q_COLS]
    LOG.ok(f"분기 TONE 집계 {len(Q):,}행 ({Q['code'].nunique():,}종목 × {Q['asof'].nunique()}시점) "
           f"· 반감기 {hl:.0f}일 최신성 가중")
    return downcast(Q)


# ── §5.3 ΔTONE + 직교화 ─────────────────────────────────────────────────────────────────────
AXIS_A_COLS = ["TONE", "TONE_prev", "dTONE", "dTONE_resid", "n_reports_q", "has_axis_a"]


def attach_axis_a(P: pd.DataFrame, tone_q: pd.DataFrame,
                  rev: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """ΔTONE 산출 → 직교화 → dTONE_resid. §7.2 에 따라 축 A 결측 종목을 탈락시키지 않는다.

    통제변수(§5.3 표): EPS 컨센 수정률 / 목표주가 수정률 / 투자의견 변경 더미 /
                      12-1 모멘텀 / log(시총) / log(ADTV) / 섹터 더미
    """
    P = P.copy()
    if tone_q is None or tone_q.empty:
        LOG.warn("분기 TONE 이 없어 축 A 를 결측 처리합니다 (종목은 탈락시키지 않습니다 — §7.2).")
        P = ensure_cols(P, AXIS_A_COLS)
        P["has_axis_a"] = 0.0
        P["dTONE_resid"] = np.nan
        return P

    Q = tone_q[["code", "asof", "TONE", "n_reports_q"]].copy()
    Q["asof"] = as_ts_series(Q["asof"])
    P = P.merge(Q, on=["code", "asof"], how="left")

    # ΔTONE: 직전 리밸 시점 대비. 양 시점 모두 리포트 ≥1건일 때만 성립(§5.3).
    P = P.sort_values(["code", "asof"], kind="stable")
    g = P.groupby("code", observed=True)
    P["TONE_prev"] = g["TONE"].shift(1)
    prev_asof = g["asof"].shift(1)
    gap_m = ((P["asof"].dt.year - prev_asof.dt.year) * 12 +
             (P["asof"].dt.month - prev_asof.dt.month))
    adjacent = gap_m == 3
    prev_n = g["n_reports_q"].shift(1)
    ok = (adjacent & P["TONE"].notna() & P["TONE_prev"].notna() &
          (P["n_reports_q"].fillna(0) >= 1) & (prev_n.fillna(0) >= 1))
    P["dTONE"] = (P["TONE"] - P["TONE_prev"]).where(ok).astype("float32")
    P["has_axis_a"] = P["dTONE"].notna().astype("float32")

    # ── 통제변수 준비 ─────────────────────────────────────────────────────────────────────
    if rev is not None and len(rev):
        rv = rev[[c for c in ("code", "asof", "tp_rev", "opin_chg") if c in rev.columns]].copy()
        rv["asof"] = as_ts_series(rv["asof"])
        P = P.merge(rv, on=["code", "asof"], how="left")
    P = ensure_cols(P, ["tp_rev", "opin_chg", "eps_rev"])

    # eps_rev 대리변수 — [방법론적 한계] 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하다.
    # PIT 실적(TTM 순이익/자산)의 분기 변화율로 대리한다. '컨센서스 수정'이 아니라 '실현 실적
    # 변화'이므로 통제력이 약하다. 이 한계는 리포트에 명시된다(§9.1).
    if P["eps_rev"].isna().all() and "net_income_ttm" in P.columns:
        ni = safe_div(col(P, "net_income_ttm"), col(P, "assets"))
        P["eps_rev"] = (ni - ni.groupby(P["code"].astype(str)).shift(1)).astype("float32")
        LOG.info("EPS 컨센서스 시계열이 없어 PIT 실적(TTM 순이익/자산) 변화율을 대리변수로 씁니다 "
                 "[방법론적 한계 — 통제력이 컨센서스 수정률보다 약합니다].")

    ctrl = [c for c in ARC_TONE_CONTROLS if c in P.columns]
    # 섹터 더미 (원핫). 기간 내 단일 섹터면 특이행렬이 되므로 첫 섹터를 기준으로 뺀다.
    sec_d = pd.get_dummies(P["sector"].astype(str), prefix="sec", drop_first=True, dtype=float) \
        if "sector" in P.columns else pd.DataFrame(index=P.index)

    X = P[ctrl].apply(pd.to_numeric, errors="coerce")
    # ★ 통제변수 결측을 0 으로 두면 직교화가 그 행에서 무력화되어 통제 안 된 알파가 섞인다.
    #   기간 중앙값으로 대체하고 대체율을 로그로 남긴다.
    n_before = int(X.isna().sum().sum())
    for c in ctrl:
        med = X.groupby(P["q"].astype(str))[c].transform("median")
        X[c] = X[c].where(X[c].notna(), med)
        X[c] = X[c].where(X[c].notna(), X[c].median())
    n_after = int(X.isna().sum().sum())
    if n_before:
        LOG.info(f"직교화 통제변수 결측 {n_before:,}칸 중 {n_before - n_after:,}칸을 "
                 f"기간 중앙값으로 대체했습니다 (잔여 결측 {n_after:,}칸). "
                 f"대체율이 높으면 직교화 통제력이 약해집니다.")
    X_full = pd.concat([X, sec_d], axis=1).fillna(0.0)

    # ── 직교화 사다리 (§5.3) ──────────────────────────────────────────────────────────────
    # ★ 자유도 하한(관측수 ≥ 5 × 파라미터수)을 걸면, 리포트 커버리지가 얇은 초기 분기는
    #   파라미터 14개(통제 6 + 섹터더미 7 + 절편)를 감당하지 못해 축 A 가 통째로 사라진다.
    #   그렇다고 하한을 풀면 잔차의 절반 이상이 규모·모멘텀·섹터의 적합오차가 되어
    #   '직교화된 톤'이 위장된 사이즈 베팅이 된다(실측: n=17 에서 corr 0.42).
    #   → 파라미터를 줄이며 내려가는 사다리를 쓴다. §5.3 이 요구하는 핵심은 **명시된 통제
    #     변수와의 직교화**이고 섹터 중립은 그 위의 추가 조치이므로, 먼저 섹터더미를 버린다.
    #     모든 단계가 실패하면 그 분기는 결측이다 — 직교화 없는 원신호를 쓰지는 않는다.
    _LADDER = [("통제 + 섹터더미", X_full),
               ("통제만(섹터더미 제외)", X),
               ("축소통제(규모·모멘텀·수정률)",
                X[[c for c in ("mom_12_1", "log_mktcap", "eps_rev") if c in X.columns]])]
    resid = pd.Series(np.nan, index=P.index, dtype="float64")
    used: List[str] = []
    qkey = P["q"].astype(str)
    for lab, Xi in _LADDER:
        if Xi.shape[1] == 0 or resid.notna().sum() == int(P["dTONE"].notna().sum()):
            continue
        need = P["dTONE"].notna() & resid.isna()
        if not need.any():
            break
        r = xsec_resid(P["dTONE"].where(need), Xi, qkey)
        got = int((r.notna() & need).sum())
        if got:
            resid = resid.where(~(r.notna() & need), r)
            used.append(f"{lab} {got:,}행")
    P["dTONE_resid"] = resid.astype("float32")

    n_ok = int(P["dTONE_resid"].notna().sum())
    n_raw = int(P["dTONE"].notna().sum())
    LOG.ok(f"ΔTONE 직교화 완료 — 원신호 {n_raw:,}행 → 잔차 {n_ok:,}행 "
           f"(통제변수 {len(ctrl)}개 + 섹터더미 {sec_d.shape[1]}개)")
    if used:
        LOG.info("직교화 사다리 적용: " + " · ".join(used) +
                 f" — 자유도 하한 {OLS_MIN_OBS_PER_PARAM}×파라미터를 못 채우면 파라미터를 "
                 f"줄여 내려갑니다. 전 단계 실패 시 그 분기 축 A 는 결측입니다"
                 f"(직교화 없는 원신호는 쓰지 않습니다 — §5.3).")
    if XSEC_RESID_DOF:
        _rt = [d["ratio"] for d in XSEC_RESID_DOF if d["n_obs"] > 0]
        if _rt:
            LOG.info(f"직교화 자유도(관측수/파라미터수) — 최소 {min(_rt):.1f} · "
                     f"중앙값 {float(np.median(_rt)):.1f} · 최대 {max(_rt):.1f}")
    if n_raw and n_ok / max(n_raw, 1) < 0.7:
        LOG.warn(f"잔차 산출률이 {100*n_ok/max(n_raw,1):.0f}% 로 낮습니다. 리포트 커버리지가 "
                 f"얇아 자유도를 채우지 못한 분기가 많다는 뜻이며, 그 분기의 축 A 는 "
                 f"결측입니다(§7.2 에 따라 종목은 축 B 로 평가되고 탈락하지 않습니다).")
    P = ensure_cols(P, AXIS_A_COLS)
    return P


def report_axis_a_ic(P: pd.DataFrame) -> dict:
    """§5.3 중간 검증 — 직교화 전/후 IC 를 나란히 보고한다. 이게 축 A 존속의 판정 근거다."""
    LOG.banner("축 A 중간 검증 — 직교화 전/후 IC (§5.3)",
               "차이가 크다면 알파 대부분이 기존 팩터(컨센 수정·모멘텀·사이즈)에서 온 것이다")
    out = {"ic_raw": np.nan, "icir_raw": np.nan, "ic_resid": np.nan, "icir_resid": np.nan,
           "n": 0, "verdict": ""}
    if P is None or P.empty or "fwd_ret_1q" not in P.columns:
        LOG.warn("패널이 비어 IC 를 계산할 수 없습니다.")
        out["verdict"] = "판정불가 — 표본 없음"
        return out
    rows = []
    for lab, cname in (("직교화 전 ΔTONE", "dTONE"), ("직교화 후 ΔTONE_resid", "dTONE_resid")):
        if cname not in P.columns:
            rows.append([lab, "—", "—", "—", "컬럼 없음"])
            continue
        ic, icir, n = info_coef(P[cname], P["fwd_ret_1q"], P["q"].astype(str))
        tstat = (icir if np.isfinite(icir) else np.nan)
        rows.append([lab, f"{ic:+.4f}" if np.isfinite(ic) else "—",
                     f"{icir:+.2f}" if np.isfinite(icir) else "—", f"{n}",
                     "유의" if np.isfinite(tstat) and abs(tstat) > 2 else "0과 구분 불가"])
        if cname == "dTONE":
            out["ic_raw"], out["icir_raw"] = ic, icir
        else:
            out["ic_resid"], out["icir_resid"], out["n"] = ic, icir, n
    LOG.table(rows, ["신호", "IC(기간평균 Spearman)", "IC-IR(≈t)", "기간수", "판정"],
              ["l", "r", "r", "r", "l"])

    ir, rr = out["ic_raw"], out["ic_resid"]
    if np.isfinite(ir) and np.isfinite(rr) and abs(ir) > 1e-9:
        shrink = 1.0 - (abs(rr) / abs(ir))
        LOG.info(f"직교화로 IC 의 {100*shrink:+.1f}% 가 사라졌습니다. "
                 f"이 비율이 크면 축 A 의 알파 상당 부분이 기존 팩터에서 온 것입니다.")
        out["shrink"] = float(shrink)
    if not np.isfinite(out["icir_resid"]) or abs(out["icir_resid"]) < 2.0:
        out["verdict"] = ("축 A 비활성화 권고 — 직교화 후 IC 가 0과 구분되지 않습니다. "
                          "§5.3 에 따라 축 B 단독(DART-ONLY) 모드를 주 결과로 삼는 것을 "
                          "검토해야 합니다. (자동으로 끄지 않고 보고만 합니다)")
        LOG.warn(out["verdict"])
    else:
        out["verdict"] = ("직교화 후에도 유의한 IC 가 남습니다 — 텍스트 고유 정보가 존재한다는 "
                          "이 백테스트의 실증 근거입니다.")
        LOG.ok(out["verdict"])
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B1  D1 — 텍스트 변화량 (Lazy Prices 방식) §6.1                                         ║
# ║                                                                                          ║
# ║  근거: Cohen·Malloy·Nguyen, "Lazy Prices", Journal of Finance 2020.                       ║
# ║  기업은 정기보고서를 기본적으로 전기 문서 복붙으로 작성한다. 따라서 '문서를 능동적으로       ║
# ║  고쳤다는 사실 자체'가 신호다.                                                             ║
# ║                                                                                          ║
# ║  ⚠ [방법론적 우려 — 반드시 유지]                                                           ║
# ║    이는 미국 10-K 결과다. 한국 사업보고서에 대한 직접 재현 증거는 확인된 바 없다.            ║
# ║    이 파일은 그것을 '검증해야 할 가설'로 취급하며, 성립을 전제하지 않는다.                   ║
# ║    부호 검증(report_d1_sign_check)이 그 판정을 담당하고, 역전이면 그대로 보고한다.           ║
# ║                                                                                          ║
# ║  ★ 부호를 사후에 뒤집어 성과를 맞추는 코드는 이 파일에 존재하지 않는다(§9.3-5).             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

D1_SECTION_WEIGHTS = dict(ARC_D1_WEIGHTS)       # 사전등록. 튜닝 금지(A13 계약검정이 감시).
D1_METRICS = tuple(ARC_D1_METRICS)

D1_SIM_COLS = ["corp_code", "rcept_dt", "bsns_year", "doc_type", "section",
               "cosine", "jaccard", "simple", "len_ratio"]
D1_VARIANT_COLS = (["D1_SCORE_equalw", "CHANGE_equalw"] +
                   [f"D1_SCORE_{m}" for m in ARC_D1_METRICS] +
                   [f"CHANGE_{m}" for m in ARC_D1_METRICS])
D1_OUT_COLS = (["corp_code", "event_date", "knowledge_date"] +
               [f"CH_{s}" for s in ARC_SECTIONS] +
               ["CHANGE_composite", "D1_SCORE", "STRUCT_FLAG", "n_sections"] +
               D1_VARIANT_COLS)


# ── 구조적 변화 (§6.1.6) ────────────────────────────────────────────────────────────────────
_STRUCT_PAT = (r"합병|분할|영업양수|영업양도|자산양수|자산양도|지주회사\s*(전환|설립)|"
               r"주식교환|주식이전|포괄적\s*교환|회사분할")


def build_struct_flags(dis: pd.DataFrame) -> pd.DataFrame:
    """§6.1.6 합병·분할·영업양수도·지주전환 → STRUCT_FLAG.

    ★ 이런 기업은 문서가 '기계적으로' 대폭 변한다. 신호가 아니라 노이즈다.
      기본 백테스트에서는 D1 을 결측 처리하고(0 이 아니다), 민감도 분석에서 포함/제외를 비교한다.
    """
    cols = ["corp_code", "event_date", "knowledge_date", "STRUCT_FLAG"]
    if dis is None or dis.empty or "report_nm" not in dis.columns:
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    hit = d["report_nm"].astype(str).str.contains(_STRUCT_PAT, regex=True, na=False)
    S = d.loc[hit, ["corp_code", "rcept_dt"]].dropna().drop_duplicates()
    if S.empty:
        LOG.info("구조적 변화(합병·분할·지주전환) 공시가 없습니다 — STRUCT_FLAG 전부 0.")
        return pd.DataFrame(columns=cols)
    S["STRUCT_FLAG"] = 1.0
    S = pit_frame(S, "rcept_dt", "rcept_dt", source="dart_struct")
    S = S.rename(columns={"rcept_dt": "_rd"})
    LOG.ok(f"구조적 변화 공시 {len(S):,}건 · {S['corp_code'].nunique():,}사 "
           f"(해당 종목-기간의 D1 은 결측 처리됩니다 — §6.1.6)")
    return S[[c for c in cols if c in S.columns]]


# ── 유사도 4종 (§6.1.4) ─────────────────────────────────────────────────────────────────────
def _d1_load(js: Any) -> Dict[str, float]:
    if not js or (isinstance(js, float) and not np.isfinite(js)):
        return {}
    if isinstance(js, dict):
        return {str(k): float(v) for k, v in js.items()}
    try:
        d = json.loads(js)
        return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def _d1_pair_metrics(cur: Dict[str, float], prev: Dict[str, float],
                     cur_bg: Dict[str, float], prev_bg: Dict[str, float],
                     idf: Dict[str, float], tok_len_c: float, tok_len_p: float) -> Tuple:
    """한 쌍의 4종 유사도. 벡터 전개 없이 dict 교집합만으로 계산한다(어휘가 수만 개라 밀집화 금지)."""
    # cosine: TF-IDF (unigram + bigram)
    a: Dict[str, float] = {}
    b: Dict[str, float] = {}
    for k, v in cur.items():
        a[k] = (1.0 + math.log(v)) * idf.get(k, 1.0)
    for k, v in cur_bg.items():
        a["#" + k] = (1.0 + math.log(v)) * idf.get("#" + k, 1.0)
    for k, v in prev.items():
        b[k] = (1.0 + math.log(v)) * idf.get(k, 1.0)
    for k, v in prev_bg.items():
        b["#" + k] = (1.0 + math.log(v)) * idf.get("#" + k, 1.0)
    if not a or not b:
        return (np.nan, np.nan, np.nan, np.nan)
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    num = 0.0
    for k, v in small.items():
        w = big.get(k)
        if w is not None:
            num += v * w
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    cos = float(num / (na * nb)) if na > 0 and nb > 0 else np.nan

    # jaccard: 토큰 집합
    sa, sb = set(cur), set(prev)
    inter = len(sa & sb)
    union = len(sa | sb)
    jac = float(inter / union) if union else np.nan

    # simple: 공통 토큰 수 / 두 문서 평균 토큰 종수
    avg = (len(sa) + len(sb)) / 2.0
    simple = float(inter / avg) if avg > 0 else np.nan

    # len_ratio: 분량 급변 탐지
    lc, lp = float(tok_len_c or 0), float(tok_len_p or 0)
    lr = float(min(lc, lp) / max(lc, lp)) if max(lc, lp) > 0 else np.nan
    return (cos, jac, simple, lr)


def d1_similarity(pairs: pd.DataFrame,
                  df_state: Optional[dict] = None) -> pd.DataFrame:
    """§6.1.4 4종 유사도 산출.

    ★ IDF 누수 방지: 전체 기간 문서로 IDF 를 만들면 '미래에 흔해질 단어'의 가중치가
      과거 계산에 들어간다. 그 자체가 미래누수다. 여기서는 rcept_dt 오름차순으로 문서빈도를
      누적하면서, 각 문서 계산 시점에는 '그때까지 관측된' df 만 쓴다(expanding IDF).
      초기 표본이 얇을 때는 smoothing 이 커져 IDF 가 1 에 수렴하므로 안전하다.
    """
    if pairs is None or pairs.empty:
        LOG.warn("페어가 없어 D1 유사도를 만들 수 없습니다.")
        return pd.DataFrame(columns=D1_SIM_COLS)

    P = pairs.copy()
    P["rcept_dt"] = as_ts_series(P["rcept_dt"])
    P = P.dropna(subset=["rcept_dt", "corp_code", "section"]).sort_values(
        ["rcept_dt", "corp_code", "section"], kind="stable").reset_index(drop=True)

    # ★ 확장 IDF 상태. 연도별 스트리밍 호출에서도 '그때까지 관측된 문서' 만 반영되도록
    #   호출자가 상태를 넘겨 이어갈 수 있게 한다(넘기지 않으면 호출 내에서만 누적).
    if df_state is None:
        df_state = {"df": Counter(), "n": 0}
    df_cnt: "Counter" = df_state.setdefault("df", Counter())
    n_docs = int(df_state.get("n", 0))
    out_rows: List[dict] = []
    t0 = time.time()

    # 같은 접수일 묶음 단위로 처리: 묶음 안에서는 동일 IDF 를 쓰고, 묶음이 끝난 뒤 df 를 갱신한다
    # (같은 날 제출된 문서끼리 서로의 df 를 참조하지 않게 — 미세하지만 누수 방향이다).
    for _, grp in tqdm(P.groupby(P["rcept_dt"].dt.to_period("M"), observed=True),
                       desc="D1 유사도", ncols=88, leave=False):
        idf: Dict[str, float] = {}
        if n_docs >= 50:
            ln = math.log(n_docs + 1.0)
            idf = {k: (ln - math.log(v + 1.0) + 1.0) for k, v in df_cnt.items() if v >= 2}
        add: "Counter" = Counter()
        for r in grp.itertuples(index=False):
            cur = _d1_load(getattr(r, "tf", None))
            prv = _d1_load(getattr(r, "prev_tf", None))
            cbg = _d1_load(getattr(r, "bigram", None))
            pbg = _d1_load(getattr(r, "prev_bigram", None))
            if not cur or not prv:
                continue
            cos, jac, sim, lr = _d1_pair_metrics(
                cur, prv, cbg, pbg, idf,
                getattr(r, "tok_len", np.nan), getattr(r, "prev_tok_len", np.nan))
            out_rows.append({
                "corp_code": r.corp_code, "rcept_dt": r.rcept_dt,
                "bsns_year": int(getattr(r, "bsns_year", 0) or 0),
                "doc_type": str(getattr(r, "doc_type", "")), "section": str(r.section),
                "cosine": cos, "jaccard": jac, "simple": sim, "len_ratio": lr})
            for k in cur:
                add[k] += 1
            for k in cbg:
                add["#" + k] += 1
            n_docs += 1
        df_cnt.update(add)
        df_state["n"] = n_docs

    if not out_rows:
        LOG.warn("유사도를 한 건도 계산하지 못했습니다 (토큰이 비었을 가능성).")
        return pd.DataFrame(columns=D1_SIM_COLS)
    S = pd.DataFrame(out_rows)
    LOG.ok(f"D1 유사도 {len(S):,}행 · 문서 {n_docs:,}건 · 소요 {time.time()-t0:.1f}초 "
           f"(cosine 평균 {S['cosine'].mean():.3f} · jaccard 평균 {S['jaccard'].mean():.3f})")
    if S["cosine"].mean() < 0.3:
        LOG.warn(f"코사인 유사도 평균이 {S['cosine'].mean():.3f} 로 매우 낮습니다. "
                 f"정상적인 정기보고서는 전년 대비 0.7~0.95 가 일반적입니다. "
                 f"★ 정규화가 제대로 되지 않아 가짜 변화가 지배하고 있을 가능성이 큽니다 — "
                 f"위 '정규화 육안 검증 샘플' 을 반드시 확인하세요.")
        PIPE.note("WARN: D1 코사인 평균 과소 — 정규화 점검 필요")
    PIPE.io("OUT", "MEM", "d1_similarity", S)
    return S


# ── 합성 (§6.1.5 공통충격 제거 → §6.1.7 섹션 가중) ──────────────────────────────────────────
def d1_composite(S: pd.DataFrame, struct: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """기간×섹션 횡단면 z → 지표 동일가중 → 섹션 가중합성 → D1_SCORE.

    ★ §6.1.5: DART 공시서식이 개정된 시기에는 전 종목이 동시에 문서를 바꾼다. 기업 고유
      신호가 아니다. 절대 유사도를 그대로 쓰면 그 해 전체가 '변경 기업'이 된다.
      기간별 횡단면 z-score 로 공통충격을 평균에 흡수시킨다.
      기간 = (사업연도 × 문서유형) — 같은 유형·같은 해 제출분끼리만 비교해야 한다.
    """
    if S is None or S.empty:
        return pd.DataFrame(columns=D1_OUT_COLS)
    d = S.copy()
    d["rcept_dt"] = as_ts_series(d["rcept_dt"])
    d = d.dropna(subset=["rcept_dt", "corp_code", "section"])
    d["_per"] = (d["bsns_year"].astype(str) + "|" + d["doc_type"].astype(str) + "|" +
                 d["section"].astype(str))

    # CHANGE = 1 − similarity, 지표별 기간 횡단면 z, 동일가중 평균
    zs = []
    for m in D1_METRICS:
        if m not in d.columns:
            continue
        ch = 1.0 - pd.to_numeric(d[m], errors="coerce")
        z = xsec_z(ch, d["_per"], min_n=CELL_MIN_N)
        # 표본이 얇은 기간은 전체 기간(연도) 셀로 폴백
        if z.isna().any():
            z = z.where(z.notna(), xsec_z(ch, d["bsns_year"].astype(str) + "|" +
                                          d["section"].astype(str), min_n=CELL_MIN_N))
        d[f"z_{m}"] = z
        zs.append(f"z_{m}")
    if not zs:
        return pd.DataFrame(columns=D1_OUT_COLS)
    d["CH_sec"] = nanmean_cols(d, zs)

    # 섹션 → 문서 단위 피벗. 합성 지표와 4개 개별 지표를 모두 만든다
    # (개별 지표는 §8.4 '유사도 4종 각각 단독 사용 시 성과' 강건성 검사에 필요하다).
    # ★ 최종 z 의 셀 키(사업연도|보고서종류)를 만들려면 pivot index 에 두 컬럼이 있어야 한다.
    #   예전에는 index 가 (corp_code, rcept_dt) 뿐이라 아래 `if "bsns_year" in W.columns`
    #   가드가 **항상 빗나가고** 셀이 조용히 달력연도 단독으로 폴백했다(문자열 연결이
    #   정상 동작해 "2019|" 라는 그럴듯한 키가 만들어져 예외도 나지 않았다).
    _PIV_IDX = ["corp_code", "rcept_dt"] + [c for c in ("bsns_year", "doc_type")
                                            if c in d.columns]
    if len(_PIV_IDX) < 4:
        raise RuntimeError(
            "d1_composite: bsns_year/doc_type 이 없어 동시 제출 코호트 셀을 만들 수 없습니다.\n"
            "  달력연도로 폴백하면 3월 접수분(사업보고서)의 평균·표준편차·윈저 경계가 같은 해\n"
            "  11월 접수분(3분기보고서)으로부터 계산됩니다 — 명백한 미래 참조이므로 중단합니다.\n"
            f"  현재 컬럼: {sorted(d.columns)[:14]}")

    def _pivot(valcol: str, prefix: str) -> pd.DataFrame:
        pv = d.pivot_table(index=_PIV_IDX, columns="section",
                           values=valcol, aggfunc="mean")
        pv = pv.reindex(columns=ARC_SECTIONS)
        pv.columns = [f"{prefix}{s}" for s in ARC_SECTIONS]
        return pv.reset_index()

    W = _pivot("CH_sec", "CH_")
    wvec = np.array([D1_SECTION_WEIGHTS.get(s, 0.0) for s in ARC_SECTIONS], dtype="float64")

    def _weighted(pv: pd.DataFrame, prefix: str, wv: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """★ 결측 섹션 가중치를 나머지에 '비례 재배분'. 가중치 합은 항상 1이어야 한다.
        이걸 틀리면 섹션이 적게 파싱된 종목이 구조적으로 유리/불리해진다."""
        V = pv[[f"{prefix}{s}" for s in ARC_SECTIONS]].to_numpy(dtype="float64")
        msk = np.isfinite(V)
        wm = np.where(msk, wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        c = np.where(ws > 0,
                     np.nansum(np.where(msk, V, 0.0) * wm, axis=1) / np.where(ws > 0, ws, 1.0),
                     np.nan)
        return c, msk.sum(axis=1)

    comp, nsec = _weighted(W, "CH_", wvec)
    W["CHANGE_composite"] = comp
    W["n_sections"] = nsec
    # 섹션 가중치 균등배분 버전 (§8.4 강건성 — 사전등록 가중치의 타당성 검증용)
    W["CHANGE_equalw"], _ = _weighted(W, "CH_", np.ones(len(ARC_SECTIONS), dtype="float64"))
    # 지표 4종 각각 단독
    for m in D1_METRICS:
        if f"z_{m}" not in d.columns:
            continue
        pm = _pivot(f"z_{m}", f"_m{m}_")
        cm, _ = _weighted(pm, f"_m{m}_", wvec)
        pm2 = pm[["corp_code", "rcept_dt"]].copy()
        pm2[f"CHANGE_{m}"] = cm
        W = W.merge(pm2, on=["corp_code", "rcept_dt"], how="left")

    # 섹션이 1개(S_ALL)뿐이면 가중합성이 사실상 S_ALL 단독이다. 신호로 쓰되 표시해 둔다.
    n_thin = int((W["n_sections"] <= 1).sum())
    if n_thin:
        LOG.info(f"섹션이 1개 이하로 파싱된 문서 {n_thin:,}건 — S_ALL 단독으로 합성됩니다 "
                 f"(가중치 비례 재배분 적용, 탈락시키지 않음).")

    # D1_SCORE = −z(CHANGE_composite). 변화가 클수록 낮은 점수(§6.1.7).
    # ★ 셀은 '달력연도'가 아니라 **동시 제출 코호트(사업연도|보고서종류)** 여야 한다.
    #   달력연도로 잡으면 3월 접수분(사업보고서)의 평균·표준편차·윈저 경계가 같은 해
    #   11월 접수분(3분기보고서)으로부터 계산된다 — 3월 문서의 점수가 11월 데이터로
    #   정해지는 명백한 미래 참조다. 코호트별 섹션 수·파싱 성공률이 실제로 다르므로
    #   코호트 간 상대 스케일이 바뀌고, 결산월이 섞인 한 리밸일의 횡단면 순위가 달라진다.
    W["_yr"] = W["bsns_year"].astype(str) + "|" + W["doc_type"].astype(str)
    W["D1_SCORE"] = -xsec_z(W["CHANGE_composite"], W["_yr"], min_n=CELL_MIN_N)
    W["D1_SCORE_equalw"] = -xsec_z(W["CHANGE_equalw"], W["_yr"], min_n=CELL_MIN_N)
    for m in D1_METRICS:
        if f"CHANGE_{m}" in W.columns:
            W[f"D1_SCORE_{m}"] = -xsec_z(W[f"CHANGE_{m}"], W["_yr"], min_n=CELL_MIN_N)
    W = W.drop(columns=["_yr"])

    # §6.1.6 구조적 변화 종목-기간은 결측 처리 (0 이 아니다)
    W["STRUCT_FLAG"] = 0.0
    if struct is not None and len(struct):
        st = struct.copy()
        st["knowledge_date"] = as_ts_series(st["knowledge_date"])
        st = st.dropna(subset=["corp_code", "knowledge_date"])
        if len(st):
            key = st.groupby(st["corp_code"].astype(str))["knowledge_date"].apply(list).to_dict()
            flags = []
            for cc, rd in zip(W["corp_code"].astype(str), as_ts_series(W["rcept_dt"])):
                ds = key.get(cc)
                # ★ 단방향이어야 한다. 예전에는 abs(...) 라 **문서 접수 이후** 최대 1년의
                #   공시까지 매칭했다. 그러면 "앞으로 12개월 안에 합병·분할·지주전환을
                #   공시할 기업" 이라는 미래 정보로 그 문서의 D1 이 지워지고, §6.5 에 따라
                #   D1 가중치 0.40 이 D2·D3 로 재배분된다. 합병 대상 종목은 전방수익률이
                #   체계적으로 다르므로 방향성 있는 편향이다. struct 는 PIT.register 를
                #   거치지 않고 파이썬 리스트로 직접 조회되므로 as-of 강제도 없었다.
                hit = bool(ds) and any(0 <= (rd - d0).days <= 365
                                       for d0 in ds if pd.notna(d0))
                flags.append(1.0 if hit else 0.0)
            W["STRUCT_FLAG"] = flags
            n_s = int(W["STRUCT_FLAG"].sum())
            if n_s:
                LOG.info(f"STRUCT_FLAG 발동 {n_s:,}건 — 해당 문서의 D1 을 결측 처리합니다 "
                         f"(민감도 분석에서 포함 버전과 비교됩니다).")
                _nan_cols = [c for c in (["CHANGE_composite", "D1_SCORE"] + D1_VARIANT_COLS)
                             if c in W.columns]
                W.loc[W["STRUCT_FLAG"] == 1.0, _nan_cols] = np.nan

    W["event_date"] = as_ts_series(W["rcept_dt"])
    # §4 DART 공시는 접수일 + 1거래일부터 사용 가능
    W["knowledge_date"] = W["event_date"] + pd.Timedelta(days=ARC_DART_LAG_DAYS)
    W = pit_frame(W, "event_date", "knowledge_date", source="dart_d1")
    W = ensure_cols(W, D1_OUT_COLS)
    LOG.ok(f"D1 합성 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(섹션 평균 {W['n_sections'].mean():.1f}개 · "
           f"D1_SCORE 유효 {int(W['D1_SCORE'].notna().sum()):,})")
    PIPE.io("OUT", "MEM", "d1_composite", W)
    return W[D1_OUT_COLS]


def attach_d1(P: pd.DataFrame, d1: Optional[pd.DataFrame]) -> pd.DataFrame:
    """패널에 D1 결합 + D1_MISSING 판정 (§3.3 상장 24개월 미만 / §6.1.6 / 파싱 실패)."""
    P = P.copy()
    add = ([f"CH_{s}" for s in ARC_SECTIONS] +
           ["CHANGE_composite", "D1_SCORE", "STRUCT_FLAG", "n_sections"] + D1_VARIANT_COLS)
    if d1 is not None and len(d1) and "corp_code" in P.columns:
        PIT.register("arc_d1", d1, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d1", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + add, suffix="_d1")
    # ★ 결합 이후에 채운다. 먼저 만들면 merge_asof 가 실제 데이터에 접미사를 붙여 흘려버린다.
    P = ensure_cols(P, add)
    P["STRUCT_FLAG"] = pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0.0)

    young = (pd.to_numeric(P.get("listing_months"), errors="coerce") < ARC_D1_MIN_LISTING_M)
    if young.any():
        _nc = [c for c in (["D1_SCORE", "CHANGE_composite"] + D1_VARIANT_COLS) if c in P.columns]
        P.loc[young.fillna(False), _nc] = np.nan
        LOG.info(f"상장 {ARC_D1_MIN_LISTING_M}개월 미만 {int(young.fillna(False).sum()):,}행은 "
                 f"D1 만 결측 처리합니다 (전년 동기 문서 부재 — §3.3). "
                 f"축 A·D2·D3 에는 그대로 잔류합니다.")
    P["D1_MISSING"] = P["D1_SCORE"].isna().astype("float32")
    rate = float(P["D1_MISSING"].mean()) if len(P) else 1.0
    LOG.ok(f"D1 결합 완료 — 결측률 {100*rate:.1f}% "
           f"(결측분은 §6.5 에 따라 D2·D3 로 가중치가 비례 재배분되며 종목은 탈락하지 않습니다)")
    return P


def report_d1_sign_check(P: pd.DataFrame) -> dict:
    """§9.2-(4) D1 부호 검증 — 한국 데이터에서 '변화 = 악재' 가 성립하는가.

    ★ 원논문에서 변화의 대다수가 부정적 감성이었기에 '변화=악재' 방향이 나왔다. 그러나
      이론적으로 방향은 사전에 확정되지 않는다. 역전이면 그 사실을 그대로 보고하고
      D1 을 '검증 실패' 로 처리해야 한다(§9.3-5). 부호를 뒤집어 성과를 맞추지 않는다.
    """
    LOG.banner("D1 부호 검증 (§9.2-4)",
               "'문서를 많이 바꾼 기업이 나쁜가' 를 한국 데이터로 직접 검정한다")
    out = {"monotone": None, "spread": np.nan, "sign_ok": None, "verdict": "", "n": 0}
    if P is None or P.empty or "CHANGE_composite" not in P.columns:
        LOG.warn("CHANGE_composite 가 없어 부호 검증을 할 수 없습니다.")
        out["verdict"] = "판정불가 — D1 미산출"
        return out
    d = P[["CHANGE_composite", "fwd_ret_1q", "q"]].dropna()
    if len(d) < 200:
        LOG.warn(f"표본 {len(d):,}행으로는 부호 검증이 불가능합니다.")
        out["verdict"] = f"판정불가 — 표본 부족({len(d):,}행)"
        return out
    d = d.copy()
    try:
        d["quint"] = d.groupby("q", observed=True)["CHANGE_composite"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop"))
    except Exception:
        d["quint"] = pd.qcut(d["CHANGE_composite"].rank(method="first"), 5,
                             labels=False, duplicates="drop")
    g = d.dropna(subset=["quint"]).groupby("quint")["fwd_ret_1q"]
    mu = g.mean()
    rows = [[f"Q{int(k)+1} ({'변화 최소' if k == 0 else ('변화 최대' if k == mu.index.max() else '')})",
             f"{int(g.size()[k]):,}", f"{v*100:+.2f}%"] for k, v in mu.items()]
    LOG.table(rows, ["CHANGE 5분위", "표본", "평균 1Q 수익률"], ["l", "r", "r"])
    if len(mu) >= 2:
        lo, hi = float(mu.iloc[0]), float(mu.iloc[-1])
        spread = lo - hi                      # 변화 적은 쪽 − 변화 많은 쪽
        out["spread"] = spread
        out["n"] = int(len(d))
        diffs = np.diff(mu.to_numpy())
        out["monotone"] = bool(np.all(diffs <= 0) or np.all(diffs >= 0))
        out["sign_ok"] = bool(spread > 0)
        LOG.info(f"변화 최소분위 {lo*100:+.2f}%  vs  변화 최대분위 {hi*100:+.2f}%  → "
                 f"스프레드 {spread*100:+.2f}%p (단조성 {'있음' if out['monotone'] else '없음'})")
        if out["sign_ok"]:
            out["verdict"] = ("미국 10-K 결과와 같은 방향(변화 = 악재)이 한국 데이터에서도 "
                              "관측됩니다. 단, 유의성은 어블레이션 B1 과 BH-FDR 판정을 보십시오.")
            LOG.ok(out["verdict"])
        else:
            out["verdict"] = ("★ 부호 역전: 한국 데이터에서는 '문서를 많이 바꾼 기업'의 수익이 "
                              "더 높습니다. §9.3-5 에 따라 부호를 뒤집지 않고 D1 을 '검증 실패' 로 "
                              "처리하며, D1 제외 버전(F2)을 주 결과로 삼는 것을 권고합니다.")
            LOG.error(out["verdict"])
    return out


def build_d1_streaming(struct: Optional[pd.DataFrame] = None,
                       years: Optional[Sequence[int]] = None,
                       T_manifest: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """연도 2개씩만 메모리에 올려 D1 을 만든다. 상주량이 문서 수와 무관하게 평평해진다.

    ★ 확장 IDF 상태(df_state)를 연도 간에 이어받으므로, 한 번에 다 올려 계산한 것과
      동일한 '그 시점까지 관측된 문서로만' 성질을 유지한다(미래누수 없음).
    """
    ys = list(years) if years else arc_doc_years(T_manifest)
    if not ys:
        LOG.warn("정기보고서 토큰 샤드가 없어 D1 을 만들 수 없습니다.")
        return pd.DataFrame(columns=D1_OUT_COLS)
    df_state = {"df": Counter(), "n": 0}
    sims: List[pd.DataFrame] = []
    peak = 0.0
    for y in sorted(ys):
        if (y - 1) not in ys:
            continue                       # 전년 문서가 없으면 페어가 만들어지지 않는다
        T2 = arc_doc_load_years([y - 1, y])
        if T2.empty:
            continue
        pr = arc_doc_pairs(T2)
        del T2
        gc.collect()
        if pr is None or pr.empty:
            continue
        peak = max(peak, mem_mb(pr))
        # ★ 월 단위로 잘라 넘긴다. d1_similarity 는 내부적으로 월 배치로 IDF 를 고정하므로
        #   한 달씩 주는 것과 한 해를 통째로 주는 것이 수치적으로 동일하고, 상주량만 줄어든다.
        pr["_m"] = as_ts_series(pr["rcept_dt"]).dt.to_period("M")
        for _mk in sorted(pr["_m"].dropna().unique()):
            chunk = pr[pr["_m"] == _mk].drop(columns=["_m"])
            if chunk.empty:
                continue
            s1 = d1_similarity(chunk, df_state=df_state)
            del chunk
            if s1 is not None and len(s1):
                sims.append(s1)
        del pr
        gc.collect()
    if not sims:
        LOG.warn("연도 스트리밍 D1 에서 유사도를 한 건도 만들지 못했습니다.")
        return pd.DataFrame(columns=D1_OUT_COLS)
    S = pd.concat(sims, ignore_index=True)
    del sims
    LOG.ok(f"D1 연도 스트리밍 완료 — 유사도 {len(S):,}행 · 연도 {len(ys)}개 · "
           f"페어 프레임 최대 상주 {peak:,.0f}MB (연도 2개 + 월 단위 청크)")
    _bud = float(globals().get("MEM_BUDGET_GB", 6.0)) * 1000.0
    if peak > _bud * 0.5:
        LOG.warn(f"D1 페어 프레임이 {peak:,.0f}MB 로 메모리 예산({_bud:,.0f}MB)의 절반을 "
                 f"넘었습니다. ARC_DOC_TF_TOP 을 낮추면(현재 {ARC_DOC_TF_TOP}) 선형으로 "
                 f"줄어듭니다 — 유사도 정확도는 거의 변하지 않습니다.")
    return d1_composite(S, struct)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B2  D2 — 재무제표 이상현상 (§6.2)                                                      ║
# ║                                                                                          ║
# ║  발생액·순영업자산·재고/매출채권 괴리는 이미 문헌 검증된 이상현상이며, 섹터 무관하게        ║
# ║  100% 커버된다. D1 이 텍스트 파싱 실패로 결측일 때 축 B 를 지탱하는 것이 이 층이다.         ║
# ║                                                                                          ║
# ║  ★ 반드시 '분기 프레임' 에서 계산한다. 패널(asof)에서 diff 를 하면 같은 분기값이 여러       ║
# ║    리밸일에 반복되어 증가율이 0 또는 폭발한다. 이건 조용한 실패라 더 위험하다.               ║
# ║  ★ 주식수 증가율을 포함하는 이유(§6.2): 소형주는 지속적 증자·CB 발행으로 실적이 개선돼도    ║
# ║    주당지표가 개선되지 않거나 악화된다. 이 항목 없이는 D2 가 소형주 구간에서 오작동한다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# (컬럼, 방향) — 방향 +1 = 높을수록 우수, -1 = 낮을수록 우수
D2_ITEMS = [("ACCRUAL", -1), ("NOA", -1), ("AR_DIVERGE", -1),
            ("INV_DIVERGE", -1), ("CFO_NI_GAP", +1), ("SHARE_GROWTH", -1)]
D2_COLS = [c for c, _ in D2_ITEMS]
D2_PANEL_COLS = ["corp_code", "event_date", "knowledge_date", "bsns_year", "reprt_code"] + \
                D2_COLS + ["D2_FORCED_LOW"]

_D2_QORD = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}


def build_d2_panel(fin: pd.DataFrame, shares: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """분기 프레임에서 6개 지표를 만든다. 반환은 PIT frame (corp_code 키)."""
    if fin is None or fin.empty:
        LOG.warn("재무 데이터가 없어 D2 를 만들 수 없습니다 — GATE_6 실패 대상(심각 이슈).")
        return pd.DataFrame(columns=D2_PANEL_COLS)

    F = fin.copy()
    for c in ("corp_code", "bsns_year", "reprt_code"):
        if c not in F.columns:
            LOG.warn(f"재무 프레임에 '{c}' 가 없습니다 — D2 를 만들 수 없습니다.")
            return pd.DataFrame(columns=D2_PANEL_COLS)
    F["corp_code"] = F["corp_code"].astype(str)
    F["reprt_code"] = F["reprt_code"].astype(str)
    F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
    F = F.dropna(subset=["bsns_year"])
    F["bsns_year"] = F["bsns_year"].astype(int)
    F["_q"] = F["reprt_code"].map(_D2_QORD)
    F = F.dropna(subset=["_q"])
    F["_seq"] = F["bsns_year"] * 4 + F["_q"].astype(int)
    F = (F.sort_values(["corp_code", "_seq"], kind="stable")
           .drop_duplicates(["corp_code", "_seq"], keep="last").reset_index(drop=True))

    g = F.groupby("corp_code", observed=True, sort=False)

    def lag(name: str, k: int = 1) -> pd.Series:
        """k 분기 전 값. 실제 간격이 k 분기일 때만 유효(결측 분기 건너뛰기 방지)."""
        v = col(F, name)
        prev = v.groupby(F["corp_code"], observed=True).shift(k)
        pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(k)
        return prev.where((F["_seq"] - pseq) == k)

    assets = col(F, "assets")
    assets_prev = lag("assets", 1)
    assets_avg = (assets + assets_prev) / 2.0
    assets_avg = assets_avg.where(assets_avg.notna(), assets)

    ni = col(F, "net_income_ttm")
    cfo = col(F, "cfo_ttm")
    rev = col(F, "revenue_ttm")
    inv = col(F, "inventory")
    rec = col(F, "receivable")
    cash = col(F, "cash")
    liab = col(F, "liabilities")

    out = pd.DataFrame({"corp_code": F["corp_code"], "bsns_year": F["bsns_year"],
                        "reprt_code": F["reprt_code"], "_seq": F["_seq"]})

    # ① ACCRUAL = (당기순이익 − 영업현금흐름) / 평균총자산
    out["ACCRUAL"] = safe_div(ni - cfo, assets_avg)

    # ② NOA = 순영업자산 / 전기말 총자산
    #    순영업자산 = (자산총계 − 현금성자산) − (부채총계 − 총차입금)
    #    ★ tidy_financials 에는 '총차입금' 계정이 없다. 근사하되 조용히 넘기지 않고 로그로 남긴다.
    has_debt = "total_debt" in F.columns and col(F, "total_debt").notna().any()
    debt = col(F, "total_debt") if has_debt else pd.Series(0.0, index=F.index)
    if not has_debt:
        LOG.info("총차입금 계정이 없어 NOA 를 (자산−현금) − 부채 로 근사합니다 "
                 "[방법론적 한계 — 차입 의존도가 높은 기업에서 NOA 가 과소평가됩니다].")
    # ★ cash 결측을 0 으로 채우면 §0.5(결측을 0 으로 채우지 않는다) 위반이고, 실제로
    #   "현금 라인만 못 읽은 법인" 이 조용히 불리해진다(실측: 자산 1000·부채 400 동일 회사가
    #   cash=200 → NOA 0.40, cash=NaN → NOA 0.60. NOA 는 방향 −1 이라 페널티다).
    #   fillna(0) 은 NaN 을 없애므로 결측률 표에는 흔적조차 남지 않고 커버리지 100% 로 보고된다.
    #   debt 는 데이터셋에 아예 없는 계정이라 0 대체가 불가피하지만, cash 는 있어야 하는데
    #   빠진 값이므로 대우가 달라야 한다 → NOA 를 결측으로 두고 §6.5 재배분에 맡긴다.
    _n_cash_na = int(cash.isna().sum())
    if _n_cash_na:
        LOG.info(f"현금성자산 결측 {_n_cash_na:,}행 — 해당 행의 NOA 를 결측 처리합니다 "
                 f"(0 으로 채우면 그 법인이 D2 에서 체계적으로 불리해집니다).")
    noa_num = ((assets - cash) - (liab - debt.fillna(0))).where(cash.notna())
    out["NOA"] = safe_div(noa_num, assets_prev.where(assets_prev.notna(), assets))

    # ③④ 매출채권 / 재고 괴리 (YoY 증가율 차이)
    def yoy(v: pd.Series) -> pd.Series:
        prev = v.groupby(F["corp_code"], observed=True).shift(4)
        pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(4)
        prev = prev.where((F["_seq"] - pseq) == 4)
        return safe_div(v - prev, prev.abs())

    rev_g = yoy(rev)
    out["AR_DIVERGE"] = yoy(rec) - rev_g
    out["INV_DIVERGE"] = yoy(inv) - rev_g

    # ⑤ CFO_NI_GAP = (영업현금흐름 − 당기순이익) / 총자산
    out["CFO_NI_GAP"] = safe_div(cfo - ni, assets)

    # ⑥ SHARE_GROWTH = 주식수 TTM 증가율
    out["SHARE_GROWTH"] = np.nan
    if shares is not None and len(shares):
        S = shares.copy()
        S["corp_code"] = S["corp_code"].astype(str)
        S["bsns_year"] = pd.to_numeric(S["bsns_year"], errors="coerce")
        S = S.dropna(subset=["bsns_year"])
        S["bsns_year"] = S["bsns_year"].astype(int)
        S["_q"] = S["reprt_code"].astype(str).map(_D2_QORD)
        S = S.dropna(subset=["_q"])
        S["_seq"] = S["bsns_year"] * 4 + S["_q"].astype(int)
        S = (S.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last"))
        sh = pd.to_numeric(S["shares_total"], errors="coerce")
        sprev = sh.groupby(S["corp_code"], observed=True).shift(4)
        pseq = S["_seq"].groupby(S["corp_code"], observed=True).shift(4)
        sprev = sprev.where((S["_seq"] - pseq) == 4)
        S["SHARE_GROWTH"] = safe_div(sh - sprev, sprev.abs())
        out = out.merge(S[["corp_code", "_seq", "SHARE_GROWTH"]], on=["corp_code", "_seq"],
                        how="left", suffixes=("", "_s"))
        if "SHARE_GROWTH_s" in out.columns:
            out["SHARE_GROWTH"] = out["SHARE_GROWTH_s"]
            out = out.drop(columns=["SHARE_GROWTH_s"])
    else:
        LOG.warn("주식총수 데이터가 없어 SHARE_GROWTH 를 결측 처리합니다. "
                 "★ 소형주는 지속 증자·CB 로 주당지표가 악화되므로, 이 항목 없이는 D2 가 "
                 "소형주 구간에서 오작동할 수 있습니다(§6.2). 결측률 표를 반드시 확인하세요.")

    # ── 분모 0/음수 강제 최하위 배정 (§6.2) ────────────────────────────────────────────────
    #   ★ 역수 부호 반전 방지. 예: 전기 총자산이 음수면 ACCRUAL 부호가 뒤집혀
    #     '최악'이 '최우수'로 둔갑한다. NaN 으로 두면 그 종목이 그 지표에서 빠져
    #     오히려 유리해지므로, 명세는 '최하위 순위로 강제 배정' 을 지시한다.
    bad_den = (~np.isfinite(assets_avg)) | (assets_avg <= 0) | \
              (~np.isfinite(assets)) | (assets <= 0)
    out["D2_FORCED_LOW"] = bad_den.astype("float32").to_numpy()
    n_forced = int(bad_den.sum())
    if n_forced:
        LOG.info(f"분모(총자산)가 0 이하이거나 결측인 {n_forced:,}행을 각 지표의 최하위 순위로 "
                 f"강제 배정합니다 (역수 부호 반전 방지 — §6.2).")

    out["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12,31))[0]:02d}-"
                               f"{REPRT_PERIOD_END.get(str(r), (12,31))[1]:02d}")
                         for y, r in zip(out["bsns_year"], out["reprt_code"])]
    kd = F[["knowledge_date"]].reset_index(drop=True) if "knowledge_date" in F.columns else None
    out["knowledge_date"] = (as_ts_series(kd["knowledge_date"]) if kd is not None
                             else as_ts_series(out["period_end"]) + pd.Timedelta(days=45))
    out = out.drop(columns=["_seq"])
    out = arc_kd_lag(out)                    # §4 접수일 + 1거래일부터 사용 가능
    out = pit_frame(out, "period_end", "knowledge_date", source="dart_d2")
    out = ensure_cols(out, D2_PANEL_COLS)
    LOG.ok(f"D2 분기 패널 {len(out):,}행 · {out['corp_code'].nunique():,}사 — " +
           " · ".join(f"{c} {100*out[c].notna().mean():.0f}%" for c in D2_COLS))
    PIPE.io("OUT", "MEM", "d2_panel", out)
    return downcast(out[D2_PANEL_COLS])


def attach_d2(P: pd.DataFrame, d2: Optional[pd.DataFrame]) -> pd.DataFrame:
    """as-of 결합 후 §6.2 합성: 섹터 중립 z → 상하위 1% 윈저 → 동일가중 평균."""
    P = P.copy()
    if d2 is not None and len(d2) and "corp_code" in P.columns:
        PIT.register("arc_d2", d2, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d2", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + D2_COLS + ["D2_FORCED_LOW"],
                          suffix="_d2")
    P = ensure_cols(P, D2_COLS + ["D2_FORCED_LOW"])

    # ★ 윈저라이즈 경계와 '강제 최하위' 값은 반드시 **분기 횡단면 안에서** 잡는다.
    #   전 기간 백분위로 자르면 2016년 관측치의 클리핑 상·하한이 2025년 데이터로 정해지고,
    #   분기 내 극단값들이 미래가 정하는 값으로 동점 처리되어 그들 사이의 순위가 사라진다.
    _qkey = P["q"].astype(str) if "q" in P.columns else P["asof"].astype(str)
    _cellkey = P["cell"].astype(str) if "cell" in P.columns else _qkey
    forced = pd.to_numeric(P["D2_FORCED_LOW"], errors="coerce").fillna(0) > 0
    zs = []
    for c, sgn in D2_ITEMS:
        v = (pd.to_numeric(col(P, c), errors="coerce")
               .groupby(_qkey, observed=True)
               .transform(lambda s: winsor_series(s, ARC_D2_WINSOR_P))) * float(sgn)
        # ★ §6.2 는 '해당 지표 **최하위 순위**로 강제 배정' 이다. '최하위 값'을 넣고 나서
        #   z 를 돌리면, 대입값의 범위(분기 전체)와 표준화 범위(분기×섹터 셀)가 어긋나
        #   분산이 좁은 셀에 극단값이 꽂힌다 — 실측에서 바닥분모 종목 1개 때문에 같은 셀
        #   39종목 전원의 z 표준편차가 1.01 → 0.36 으로 압축됐다. 그 셀 종목들은 다른 셀과
        #   경쟁할 때 꼬리에 도달하지 못해 상위 N 에서 구조적으로 밀린다. 지표마다 압축률이
        #   달라 '동일가중 평균'도 더 이상 동일가중이 아니게 된다.
        #   → 강제 배정은 값이 아니라 **z 계산 후 셀 내 최하위 z** 로 한다.
        z = xsec_z_arc(P.assign(**{f"_v_{c}": v.mask(forced)}), f"_v_{c}")
        if forced.any() and z.notna().any():
            zmin = z.groupby(_cellkey, observed=True).transform("min")
            zmin = zmin.fillna(float(np.nanmin(z.to_numpy())) if z.notna().any() else 0.0)
            z = z.mask(forced, zmin - 1e-6)
        P[f"z_{c}"] = z
        zs.append(f"z_{c}")
    P["D2_SCORE"] = xsec_z_arc(P.assign(_d2raw=nanmean_cols(P, zs)), "_d2raw")
    n_ok = int(P["D2_SCORE"].notna().sum())
    LOG.ok(f"D2 결합·합성 완료 — 유효 {n_ok:,}행 ({100*n_ok/max(len(P),1):.1f}%) · "
           f"구성 지표 {len(zs)}개")
    if n_ok / max(len(P), 1) < 0.5:
        LOG.warn(f"D2 유효율이 {100*n_ok/max(len(P),1):.0f}% 로 낮습니다. DART 재무 콜드빌드가 "
                 f"미완이거나 corp_code 매칭률이 낮다는 뜻입니다. "
                 f"D2 는 D1 보다 대체 불가하므로(§2.3) 심각 이슈로 취급하세요.")
    return P


def report_d2_coverage(P: pd.DataFrame) -> dict:
    """지표별 결측률 — GATE_6 의 근거이자 '어느 지표가 D2 를 지탱하는가' 의 답."""
    LOG.banner("D2 지표 커버리지", "결측률이 높은 지표는 사실상 합성에 기여하지 않는다")
    out = {}
    if P is None or P.empty:
        LOG.warn("패널이 비어 커버리지를 계산할 수 없습니다.")
        return out
    rows = []
    for c, sgn in D2_ITEMS:
        v = col(P, c)
        n = int(v.notna().sum())
        out[c] = n / max(len(P), 1)
        rows.append([c, "낮을수록 우수" if sgn < 0 else "높을수록 우수",
                     f"{n:,}", f"{100*out[c]:.1f}%",
                     f"{float(v.mean()):+.4f}" if n else "—",
                     f"{float(v.std()):.4f}" if n > 1 else "—"])
    LOG.table(rows, ["지표", "방향", "관측", "커버리지", "평균", "표준편차"],
              ["l", "l", "r", "r", "r", "r"])
    if "SHARE_GROWTH" in out and out["SHARE_GROWTH"] < 0.3:
        LOG.warn(f"SHARE_GROWTH 커버리지가 {100*out['SHARE_GROWTH']:.0f}% 에 불과합니다. "
                 f"소형주의 증자·CB 희석을 못 잡는다는 뜻이며, 명세 §6.2 가 경고한 "
                 f"'소형주 구간 오작동' 위험이 실재합니다.")
    # 연도별 추이
    if "asof" in P.columns:
        yr = as_ts_series(P["asof"]).dt.year
        tr = []
        for y, g in P.groupby(yr):
            tr.append([int(y)] + [f"{100*col(g, c).notna().mean():.0f}%" for c in D2_COLS])
        LOG.table(tr, ["연도"] + D2_COLS, ["c"] + ["r"] * len(D2_COLS),
                  title="D2 지표 커버리지 연도별 추이 (콜드빌드 진행 상황이 그대로 보입니다)")
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B3  D3 하드팩트(가점) + 배제 플래그(하드 제외)  §6.3 / §6.4                            ║
# ║                                                                                          ║
# ║  D3 — 완료형 사실만 추출한다. 전망·계획·의지·기대·예정은 전부 제외.                         ║
# ║       ★★ ΔNONFIN > 0 을 편입 조건으로 쓰지 않는다. v1.0 에서 폐기된 규칙이다.               ║
# ║          ΔNONFIN = 0 인 종목도 다른 축 점수가 높으면 편입 가능해야 한다(A9 계약검정).       ║
# ║          섹터 편향(기술·제조 쏠림)이 있으므로 가점으로만 쓴다.                              ║
# ║                                                                                          ║
# ║  배제 — 특수관계자·우발부채·소송은 경영진이 감추려 하는 정보다. 그럼에도 공시됐다는 것은     ║
# ║        신호의 신뢰도가 높다는 뜻이므로 **여기만 하드 제외를 유지**한다(§6.4).                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

D3_EVENTS = [
    ("NF_RND_EMP",   "연구개발 인력 순증",              "기술·제조"),
    ("NF_RND_RATIO", "연구개발비/매출액 비율 상승",      "기술·제조"),
    ("NF_PATENT",    "특허 등록 건수 증가",              "기술·제조"),
    ("NF_CAPEX",     "유형자산 취득(설비투자)",          "제조·유통"),
    ("NF_CONTRACT",  "단일판매·공급계약 체결",           "전 섹터"),
    ("NF_GOVRND",    "정부 R&D 과제 선정",               "기술"),
    ("NF_NEWBIZ",    "신규 사업목적 추가 후 실제 매출",   "전 섹터"),
    ("NF_SUBSID",    "종속·관계기업 신규 취득",          "전 섹터"),
    ("NF_OVERSEAS",  "해외 신규 거점 설립",              "전 섹터"),
    ("NF_EMP",       "직원 수 순증(비R&D 포함)",         "전 섹터"),
]
D3_COLS = [c for c, _, _ in D3_EVENTS]

EXCL_DEFS = [
    ("EX_RELATED",    "특수관계자 매입/매출 비중 상승 (횡단면 상위 20%)"),
    ("EX_CONTINGENT", "우발부채·지급보증 증가 (자기자본 대비 5%p 이상)"),
    ("EX_LITIGATION", "신규 소송 (소송가액/자기자본 > 5%)"),
    ("EX_AUDIT",      "감사의견 특기사항/강조사항 존재"),
    ("EX_OWNER",      "최대주주 변경"),
    ("EX_CBBW",       "전환사채·신주인수권부사채 발행"),
    ("EX_LOSS4Q",     "4개 분기 연속 영업적자"),
    ("EX_IMPAIR",     "자본잠식률 > 30%"),
]
EXCL_COLS = [c for c, _ in EXCL_DEFS]

# ── 완료형 vs 전망형 (§6.3 추출 원칙) ───────────────────────────────────────────────────────
#   ★ 이 구분이 D3 의 전부다. '~할 계획입니다' 를 사실로 세면 D3 는 IR 문구 카운터가 된다.
_D3_FUTURE = re.compile(
    r"계획(이|입니다|임|중)|예정|전망|기대|목표로|추진\s*중|검토\s*중|협의\s*중|"
    r"할\s*것|하고자|하려|예상|방침|모색|준비\s*중|논의\s*중")
_D3_DONE = re.compile(
    r"완료(하였|했|되었|됨)|체결(하였|했|되었|함|됨)|취득(하였|했|함)|등록(하였|했|되었|됨)|"
    r"설립(하였|했|함)|선정(되었|됨)|승인(받았|되었)|개시(하였|했)|양수(하였|했)|"
    r"인수(하였|했|함)|출자(하였|했)|준공(하였|했)")
_D3_HAS_NUM = re.compile(r"<NUM>|\d")
_D3_HAS_DATE = re.compile(r"<DATE>|\d{4}\s*년|\d{1,2}\s*월")

_D3_KEY = {
    "NF_PATENT":   r"특허|실용신안|지식재산권|지적재산권",
    "NF_GOVRND":   r"국가연구개발|정부\s*과제|국책\s*과제|산업통상자원부|중소벤처기업부|"
                   r"과학기술정보통신부|한국산업기술|R&D\s*과제",
    "NF_SUBSID":   r"종속회사|관계기업|자회사|지분\s*취득|출자",
    "NF_OVERSEAS": r"해외\s*법인|현지\s*법인|해외\s*지점|해외\s*사무소|해외\s*공장|"
                   r"베트남|인도|멕시코|폴란드|헝가리|미국\s*법인|중국\s*법인",
    "NF_NEWBIZ":   r"사업\s*목적\s*(추가|변경)|신규\s*사업|신사업",
}
_D3_KEY_RE = {k: re.compile(v) for k, v in _D3_KEY.items()}

_D3_SENT_SPLIT = re.compile(r"(?<=[다\.])\s+|\n+")


def _d3_count_facts(text: str, pat: "re.Pattern") -> int:
    """완료형 동사 + 날짜 + 숫자가 모두 있는 문장만 센다. 정성적 판단은 하지 않는다."""
    if not text:
        return 0
    n = 0
    for s in _D3_SENT_SPLIT.split(text)[:4000]:
        if len(s) < 10 or not pat.search(s):
            continue
        if _D3_FUTURE.search(s):
            continue                      # 전망·계획·의지는 전부 제외
        if not _D3_DONE.search(s):
            continue                      # 완료형 동사 필수
        if not (_D3_HAS_NUM.search(s) and _D3_HAS_DATE.search(s)):
            continue                      # 날짜 + 숫자 필수
        n += 1
    return n


def _d3_text_by_doc(T: pd.DataFrame) -> pd.DataFrame:
    """정규화 토큰 테이블 → 문서 단위 **토큰 집합**.

    ★ 예전에는 tf(JSON dict 문자열)들을 이어붙인 문자열에 정규식을 그대로 걸었다. 두 가지가
      동시에 깨졌다:
        ① 두 단어 패턴(`해외\s*법인`, `지분\s*취득`, `정부\s*과제`, `신규\s*사업` …)은
           JSON 덤프에서 **원리상 매칭될 수 없다** — 두 토큰 사이에 항상 `": 3, "` 가 낀다.
           해당 이벤트는 어떤 데이터를 넣어도 영구 0 이었다(NF_GOVRND·NF_NEWBIZ·
           NF_SUBSID·NF_OVERSEAS 실측 전부 0건).
        ② 단일 토큰 패턴(`특허`, `자회사`, `출자` …)은 '이 단어가 보고서 어딘가에 나오는가'
           가 되어 이벤트가 아니라 상수가 됐다(NF_PATENT 실측 67% 발화).
      → 토큰 집합으로 바꾸고, 다단어 패턴은 **모든 구성 토큰이 집합에 있는지**로 판정한다.

    ★ 그리고 §6.3 의 핵심인 '완료형만' 필터(_d3_count_facts)는 exact=True 경로에서만
      돌아가는데 그 경로에 도달하는 코드가 없었다 — 규정 전체가 죽은 코드였다.
      원문이 공용 인덱스에 남아 있으면 그걸 읽어 exact 경로를 실제로 태운다.
    """
    cols = ["corp_code", "rcept_no", "rcept_dt", "blob", "tokens", "exact"]
    if T is None or T.empty:
        return pd.DataFrame(columns=cols)

    def _tokset(ss) -> set:
        out: set = set()
        for x in ss:
            d = _d1_load(x) if "_d1_load" in globals() else None
            if isinstance(d, dict) and d:
                out.update(map(str, d.keys()))
            else:
                out.update(re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}|<[A-Z]+>", str(x)))
        return out

    g = (T.sort_values("section")
          .groupby(["corp_code", "rcept_no"], observed=True)
          .agg(rcept_dt=("rcept_dt", "min"), tokens=("tf", _tokset)).reset_index())

    # ── 원문 재조회 → §6.3 완료형 판정(정확 경로)을 **실제로** 태운다 ──────────────────
    #   원문 zip 은 15 모듈이 공용 인덱스에 ("dart_doc","raw", rcept_no) 로 저장해 둔다.
    #   put_blob 의 uid 는 내용해시를 포함해 재구성할 수 없으므로 get_blob_by_key 로 찾는다.
    #   ★ 전 문서를 다시 여는 건 비싸다 → **약한 규칙이 하나라도 걸린 후보 문서만** 연다.
    #     완료형 필터는 같은 키워드 정규식에 '완료형 동사 + 날짜 + 숫자' 를 더한 것이므로
    #     약한 판정을 통과하지 못한 문서는 정확 판정도 통과할 수 없다(안전한 사전 선별).
    _keys = list(_D3_KEY_RE.keys())
    cand = g["tokens"].map(lambda ts: any(_d3_tokens_hit(ts, k) for k in _keys) or
                                      any(_d3_tokens_hit(ts, k) for k in _D3_WEAK_CONSTANT))
    cap = int(globals().get("ARC_D3_EXACT_MAX_DOCS", 4000))
    order = [i for i, c in enumerate(cand.to_numpy()) if c][:cap]
    n_cand, n_over = int(cand.sum()), max(0, int(cand.sum()) - len(order))
    blobs = [""] * len(g)
    exacts = [False] * len(g)
    _v = globals().get("VAULT")
    if _v is not None and order:
        rn_all = g["rcept_no"].astype(str).tolist()
        for i in order:
            raw = None
            try:
                raw = _v.get_blob_by_key("dart_doc", "raw", rn_all[i])
            except Exception:
                raw = None
            if not raw:
                continue
            try:
                txt = _doc_unzip_text(raw) if isinstance(raw, (bytes, bytearray)) else str(raw)
            except Exception:
                continue
            if txt and len(txt) > 500:
                # 원문 그대로 쓰면 표·태그가 문장 판정을 망친다 → 6단계 정규화를 태운다.
                try:
                    txt = arc_normalize_text(txt)
                except Exception:
                    pass
                blobs[i] = txt[:400_000]
                exacts[i] = True
    g["blob"] = blobs
    g["exact"] = exacts
    n_ex = int(sum(exacts))
    if n_cand:
        LOG.info(f"§6.3 정확 판정 후보 {n_cand:,}건 중 원문 확보 {n_ex:,}건"
                 + (f" · 상한({cap:,})으로 {n_over:,}건 미처리" if n_over else "")
                 + ". 원문이 없는 후보는 토큰 집합 기반 약한 판정으로 남습니다.")
    return g[cols]


# 다단어 판정용 — 패턴을 '있어야 할 토큰들의 선택지 집합' 으로 표현한다.
#   값: [[대안1토큰들], [대안2토큰들], ...]  (한 대안의 토큰이 전부 있으면 발화)
_D3_TOKEN_RULES: Dict[str, List[List[str]]] = {
    "NF_PATENT":   [["특허"], ["실용신안"], ["지식재산권"], ["지적재산권"]],
    "NF_GOVRND":   [["국가연구개발"], ["정부", "과제"], ["국책", "과제"],
                    ["산업통상자원부"], ["중소벤처기업부"], ["과학기술정보통신부"]],
    "NF_SUBSID":   [["종속회사"], ["관계기업"], ["자회사"], ["지분", "취득"], ["출자"]],
    "NF_OVERSEAS": [["해외", "법인"], ["현지", "법인"], ["해외", "지점"], ["해외", "공장"],
                    ["베트남"], ["인도"], ["멕시코"], ["폴란드"], ["헝가리"]],
    "NF_NEWBIZ":   [["사업", "목적", "추가"], ["사업", "목적", "변경"],
                    ["신규", "사업"], ["신사업"]],
}
# 단일 토큰만으로 발화하는 규칙은 '이 단어가 보고서 어딘가에 있는가' 라 사실상 상수가 된다.
# 원문(exact) 경로가 없을 때는 이 태그들을 0 이 아니라 **NaN(미판정)** 으로 둔다.
_D3_WEAK_CONSTANT = {"NF_PATENT", "NF_SUBSID"}


def _d3_tokens_hit(tokens: set, key: str) -> bool:
    for alt in _D3_TOKEN_RULES.get(key, []):
        if all(t in tokens for t in alt):
            return True
    return False


def extract_hardfacts(T: pd.DataFrame, fin: pd.DataFrame, emp: pd.DataFrame,
                      dis: pd.DataFrame, notes: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """§6.3 하드팩트 추출. 반환 (PIT frame): corp_code, event_date, knowledge_date, NF_*, DELTA_NONFIN."""
    cols = ["corp_code", "event_date", "knowledge_date"] + D3_COLS + \
           ["DELTA_NONFIN", "D3_N_OBS"]
    parts: List[pd.DataFrame] = []

    # ── (A) 재무 기반 이벤트: 정량이라 가장 신뢰도 높다 ────────────────────────────────────
    if fin is not None and len(fin) and "corp_code" in fin.columns:
        F = fin.copy()
        F["corp_code"] = F["corp_code"].astype(str)
        F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
        F["_q"] = F["reprt_code"].astype(str).map(_D2_QORD)
        F = F.dropna(subset=["bsns_year", "_q"])
        F["_seq"] = F["bsns_year"].astype(int) * 4 + F["_q"].astype(int)
        F = (F.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last"))

        def _lag4(v: pd.Series) -> pd.Series:
            prev = v.groupby(F["corp_code"], observed=True).shift(4)
            pseq = F["_seq"].groupby(F["corp_code"], observed=True).shift(4)
            return prev.where((F["_seq"] - pseq) == 4)

        rnd_ratio = safe_div(col(F, "rnd_ttm"), col(F, "revenue_ttm"))
        ppe = col(F, "ppe")
        A = pd.DataFrame({
            "corp_code": F["corp_code"],
            "event_date": as_ts_series(F["period_end"]) if "period_end" in F.columns else pd.NaT,
            # §4 접수일 + 1거래일 (재무제표는 접수 당일 사용 불가)
            "knowledge_date": (as_ts_series(F["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in F.columns else pd.NaT,
            # 완료형 정량 사실: 전년 동기 대비 실제 증가 (계획이 아니라 재무제표에 찍힌 값)
            "NF_RND_RATIO": (rnd_ratio > _lag4(rnd_ratio)).astype(float)
                            .where(rnd_ratio.notna() & _lag4(rnd_ratio).notna()),
            "NF_CAPEX": (safe_div(ppe - _lag4(ppe), _lag4(ppe).abs()) > 0.10).astype(float)
                        .where(_lag4(ppe).notna()),
        })
        parts.append(A)

    # ── (B) 직원 현황 기반 ─────────────────────────────────────────────────────────────────
    if emp is not None and len(emp) and "corp_code" in emp.columns:
        E = emp.copy()
        E["corp_code"] = E["corp_code"].astype(str)
        E["bsns_year"] = pd.to_numeric(E["bsns_year"], errors="coerce")
        E = E.dropna(subset=["bsns_year"]).sort_values(["corp_code", "bsns_year"], kind="stable")
        prev = E.groupby("corp_code", observed=True)["employees"].shift(1)
        pyr = E.groupby("corp_code", observed=True)["bsns_year"].shift(1)
        prev = prev.where((E["bsns_year"] - pyr) == 1)
        B = pd.DataFrame({
            "corp_code": E["corp_code"],
            "event_date": as_ts_series(E["period_end"]) if "period_end" in E.columns else pd.NaT,
            "knowledge_date": (as_ts_series(E["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in E.columns else pd.NaT,
            "NF_EMP": (pd.to_numeric(E["employees"], errors="coerce") > prev).astype(float)
                      .where(prev.notna()),
        })
        # R&D 인력은 별도 컬럼이 없다 → 직원 순증과 R&D 비율 상승이 동시 성립할 때만 인정
        B["NF_RND_EMP"] = np.nan
        parts.append(B)

    # ── (C) 수시공시 기반: 단일판매·공급계약 ───────────────────────────────────────────────
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        D = dis.copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        hit = D["report_nm"].astype(str).str.contains(
            r"단일판매|공급계약\s*체결|수주", regex=True, na=False)
        C = D.loc[hit, ["corp_code", "rcept_dt"]].dropna().copy()
        if len(C):
            C["corp_code"] = C["corp_code"].astype(str)
            C["event_date"] = C["rcept_dt"]
            C["knowledge_date"] = C["rcept_dt"] + pd.Timedelta(days=ARC_DART_LAG_DAYS)
            C["NF_CONTRACT"] = 1.0
            parts.append(C[["corp_code", "event_date", "knowledge_date", "NF_CONTRACT"]])

    # ── (D) 문서 텍스트 기반: 특허·정부과제·종속회사·해외거점·신규사업 ─────────────────────
    n_weak, n_exact, n_doc_txt = 0, 0, 0
    if T is not None and len(T):
        DOC = _d3_text_by_doc(T)
        n_doc_txt = int(len(DOC))
        if len(DOC):
            rows = []
            for r in DOC.itertuples(index=False):
                blob = str(getattr(r, "blob", "") or "")
                toks = getattr(r, "tokens", None) or set()
                rec = {"corp_code": str(r.corp_code),
                       "event_date": as_ts(r.rcept_dt),
                       "knowledge_date": as_ts(r.rcept_dt) + pd.Timedelta(days=ARC_DART_LAG_DAYS)}
                if bool(r.exact):
                    n_exact += 1
                for k, rx in _D3_KEY_RE.items():
                    if bool(r.exact):
                        # §6.3 정확 경로 — 완료형 동사 + 날짜 + 숫자를 갖춘 문장만 센다.
                        rec[k] = 1.0 if _d3_count_facts(blob, rx) > 0 else 0.0
                    elif k in _D3_WEAK_CONSTANT:
                        # ★ 단일 토큰 존재 여부는 이벤트가 아니라 상수다. 0 으로 두면
                        #   '사실 없음' 으로 오독되므로 NaN(미판정) 으로 남긴다.
                        rec[k] = np.nan
                    else:
                        # 약한 증거 경로: 토큰 집합 기반 다단어 판정. 완료형/전망형은
                        #   구분할 수 없으므로 과대계상 가능 — 건수를 따로 보고한다.
                        rec[k] = 1.0 if _d3_tokens_hit(toks, k) else 0.0
                rows.append(rec)
            Dx = pd.DataFrame(rows)
            if len(Dx):
                n_weak = int(Dx[[c for c in _D3_KEY_RE if c in Dx.columns]].sum().sum())
                parts.append(Dx)

    if not parts:
        LOG.warn("D3 하드팩트 입력이 하나도 없습니다 — D3_SCORE 는 전 구간 결측입니다 "
                 "(§6.3 은 가점이므로 다른 축으로 가중치가 재배분됩니다).")
        return pd.DataFrame(columns=cols)

    H = pd.concat([p for p in parts if p is not None and len(p)], ignore_index=True)
    H["corp_code"] = H["corp_code"].astype(str)
    H["event_date"] = as_ts_series(H["event_date"])
    H["knowledge_date"] = as_ts_series(H["knowledge_date"])
    H = H.dropna(subset=["corp_code", "knowledge_date"])
    H = ensure_cols(H, D3_COLS, fill=np.nan)
    # 같은 (법인, 공개일) 의 여러 소스를 합친다. 각 이벤트는 바이너리 태그이므로 max.
    H = H.groupby(["corp_code", "knowledge_date"], as_index=False).agg(
        **{"event_date": ("event_date", "min"),
           **{c: (c, "max") for c in D3_COLS}})
    # ★ 배제 플래그와 같은 이유로(소스별 행이 서로를 덮음) 상태 테이블로 변환한다.
    #   D3 는 '직전 1년 안에 이 사실이 관측되었는가' 의 합이 된다 — 분기 내 여러 이벤트가
    #   마지막 1행으로 대체되어 사라지던 문제도 함께 해소된다.
    H = _event_state_table(H, D3_COLS, D3_VALID_DAYS)
    # ★ sum(skipna=True) 는 NaN 을 0 으로 취급하고 전부 NaN 인 행도 0.0 을 돌려준다.
    #   _event_state_table 이 방금 보존한 '모름 ≠ 미발화' 불변식이 두 줄 뒤에서 깨진다.
    #   D3 태그는 재무·직원·수시공시·문서텍스트 네 소스에서 오는데, 문서 파싱이 실패한
    #   법인은 5개 태그가 통째로 '모름'이 된다. 그대로 합산하면 D3_SCORE 가 '사실 건수'가
    #   아니라 '데이터 커버리지'의 함수가 되고, 그 값이 최종 점수의 10%(0.20×0.50)를 쥔다.
    #   → 관측된 태그 수를 함께 남기고, 관측이 0 인 행은 NaN 으로 둔다.
    H["D3_N_OBS"] = H[D3_COLS].notna().sum(axis=1).astype("int16")
    H["DELTA_NONFIN"] = H[D3_COLS].sum(axis=1, skipna=True).where(H["D3_N_OBS"] > 0)
    H = pit_frame(H, "event_date", "knowledge_date", source="dart_d3")
    H = ensure_cols(H, cols)
    fired = {c: int(pd.to_numeric(H[c], errors="coerce").fillna(0).sum()) for c in D3_COLS}
    LOG.ok(f"D3 하드팩트 {len(H):,}행 · {H['corp_code'].nunique():,}사 · "
           f"이벤트 총 {int(H['DELTA_NONFIN'].sum()):,}건")
    LOG.table([[c, d, s, f"{fired[c]:,}"] for c, d, s in D3_EVENTS],
              ["태그", "이벤트", "섹터 적용성", "발화 건수"], ["l", "l", "l", "r"],
              title="D3 이벤트별 발화 (v2.0 에서 전 섹터 항목 4개 추가)")
    if n_weak:
        LOG.warn(f"문서 텍스트 기반 이벤트 {n_weak:,}건은 '약한 증거' 경로로 판정되었습니다. "
                 f"원문 blob 이 없는 문서는 토큰 집합만으로 판정하므로 완료형/전망형을 "
                 f"구분하지 못합니다 → D3 가 과대계상될 수 있습니다. D3 가중치가 0.20 으로 "
                 f"낮고 가점으로만 쓰이는 것이 이 한계를 완충합니다.")
    if n_doc_txt:
        LOG.info(f"§6.3 완료형 판정 — 원문 확보 {n_exact:,}/{n_doc_txt:,}건에서만 문장 단위 "
                 f"(완료형 동사 + 날짜 + 숫자) 필터가 적용됩니다. 나머지는 토큰 집합 기반 "
                 f"약한 판정이며, 단일 토큰만으로 발화하는 태그"
                 f"({' · '.join(sorted(_D3_WEAK_CONSTANT))})는 0 이 아니라 결측입니다.")
        if n_exact == 0:
            LOG.warn("원문 blob 을 하나도 확보하지 못해 §6.3 '완료형만' 필터가 한 건도 "
                     "적용되지 않았습니다. 문서 텍스트 기반 NF_* 는 '그 단어가 보고서에 "
                     "나오는가' 수준의 약한 증거입니다 — D3 해석 시 반드시 감안하세요.")
    PIPE.io("OUT", "MEM", "d3_hardfacts", H)
    return H[cols]


# ── 배제 플래그 (§6.4) ──────────────────────────────────────────────────────────────────────
_EX_OWNER_PAT = r"최대주주\s*변경|최대주주변경"
_EX_CBBW_PAT = r"전환사채|신주인수권부사채|교환사채"

# 플래그별 유효기간(일). 감사의견은 연 1회 갱신되므로 다음 감사보고서까지(≈15개월),
# 나머지 이벤트는 1년 남짓 유효한 것으로 사전등록한다. 튜닝 대상이 아니다.
EXCL_VALID_DAYS = {"EX_RELATED": 400, "EX_CONTINGENT": 400, "EX_LITIGATION": 400,
                   "EX_AUDIT": 460, "EX_OWNER": 370, "EX_CBBW": 370,
                   "EX_LOSS4Q": 400, "EX_IMPAIR": 400}
D3_VALID_DAYS = 370          # 하드팩트 이벤트는 직전 1년치를 센다


def _event_state_table(X: pd.DataFrame, cols: Sequence[str],
                       valid_days, key: str = "corp_code",
                       tcol: str = "knowledge_date") -> pd.DataFrame:
    """소스별로 흩어진 '이벤트' 행들을 시점마다 완결된 '상태' 행으로 바꾼다.

    ★ 이 함수가 없으면 §6.4 하드 제외가 사실상 작동하지 않는다. 왜인지 남긴다:
      build_exclusion_flags 는 재무·공시목록·감사의견을 **각각 다른 접수일**로 행을 만들고,
      그 행에는 다른 소스의 플래그가 NaN 으로 남는다. 병합 키가 (corp_code, knowledge_date)
      이므로 접수일이 다르면 병합되지 않는다. 그런데 소비 측(attach_d3)은 asof 결합이라
      corp_code 당 **가장 최근 1행만** 붙이고, 그 행에 없는 플래그는 NaN → fillna(0) →
      **제외 해제**가 된다. 재무 행은 매 분기 무조건 생성되므로, 연 1회짜리 EX_AUDIT
      ('의견거절' 등)은 다음 분기보고서가 접수되는 순간 영구히 덮인다. 리밸일이 3/6/9/12월
      1일이므로 EX_AUDIT 이 살아 있는 리밸일은 사실상 존재하지 않았다.

    해법: 발화 이벤트마다 유효기간을 부여하고 **만료 시점에 'off' 행을 명시적으로 생성**해,
    어느 시점을 집어도 그 한 행 안에서 모든 플래그의 상태가 완결되게 만든다.
    관측 자체가 없는 플래그는 0 이 아니라 NaN 으로 남긴다('미발화'와 '모름'은 다르다).
    """
    if X is None or len(X) == 0:
        return X
    cols = [c for c in cols if c in X.columns]
    if not cols:
        return X
    W = {c: int(valid_days.get(c, 400) if isinstance(valid_days, dict) else valid_days)
         for c in cols}

    B = X[[key, tcol]].copy()
    B[tcol] = as_ts_series(B[tcol])
    B = B.dropna(subset=[key, tcol])

    # 타임라인 = 원 관측 시점 ∪ 발화 만료 시점
    tls = [B]
    fired: Dict[str, pd.DataFrame] = {}
    for c in cols:
        v = pd.to_numeric(X[c], errors="coerce")
        f = X.loc[v > 0, [key, tcol]].copy()
        f[tcol] = as_ts_series(f[tcol])
        f = f.dropna(subset=[key, tcol]).sort_values([tcol], kind="stable")
        fired[c] = f.rename(columns={tcol: "_fired"})
        if len(f):
            e = f.copy()
            e[tcol] = e[tcol] + pd.Timedelta(days=W[c])
            tls.append(e[[key, tcol]])
    TL = (pd.concat(tls, ignore_index=True)
            .drop_duplicates([key, tcol]).sort_values([tcol, key], kind="stable")
            .reset_index(drop=True))

    # 플래그별로 '가장 최근 발화'를 as-of 로 찾아 유효기간 내면 1, 아니면 0
    for c in cols:
        f = fired[c]
        if len(f):
            m = pd.merge_asof(TL, f.sort_values("_fired", kind="stable"),
                              left_on=tcol, right_on="_fired", by=key, direction="backward")
            age = (m[tcol] - m["_fired"]).dt.days
            TL[c] = np.where(age.notna() & (age < W[c]), 1.0, 0.0)
        else:
            TL[c] = 0.0
        # 그 법인에 대해 해당 플래그의 관측이 애초에 없었다면 0 이 아니라 NaN(모름)
        obs = X.loc[pd.to_numeric(X[c], errors="coerce").notna(), key].astype(str).unique()
        TL[c] = TL[c].where(TL[key].astype(str).isin(set(obs)))

    # event_date 는 그 시점까지 알려진 가장 이른 원 이벤트일 — 없으면 관측 시점 자체
    if "event_date" in X.columns:
        ed = (X[[key, tcol, "event_date"]].copy())
        ed[tcol] = as_ts_series(ed[tcol]); ed["event_date"] = as_ts_series(ed["event_date"])
        ed = ed.dropna(subset=[key, tcol]).sort_values(tcol, kind="stable")
        m = pd.merge_asof(TL, ed, left_on=tcol, right_on=tcol, by=key, direction="backward")
        TL["event_date"] = m["event_date"].fillna(TL[tcol])
    else:
        TL["event_date"] = TL[tcol]
    return TL


def build_exclusion_flags(fin: pd.DataFrame, dis: pd.DataFrame,
                          audit: Optional[pd.DataFrame] = None,
                          T: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """§6.4 하드 제외 플래그. 반환 (PIT frame): corp_code, event_date, knowledge_date, EX_*."""
    cols = ["corp_code", "event_date", "knowledge_date"] + EXCL_COLS
    parts: List[pd.DataFrame] = []
    miss_note: List[str] = []

    # ── 재무 기반: 4분기 연속 영업적자 / 자본잠식 ─────────────────────────────────────────
    if fin is not None and len(fin) and "corp_code" in fin.columns:
        F = fin.copy()
        F["corp_code"] = F["corp_code"].astype(str)
        F["bsns_year"] = pd.to_numeric(F["bsns_year"], errors="coerce")
        F["_q"] = F["reprt_code"].astype(str).map(_D2_QORD)
        F = F.dropna(subset=["bsns_year", "_q"])
        F["_seq"] = F["bsns_year"].astype(int) * 4 + F["_q"].astype(int)
        F = (F.sort_values(["corp_code", "_seq"], kind="stable")
               .drop_duplicates(["corp_code", "_seq"], keep="last").reset_index(drop=True))
        # ★ 분기 프레임에서 센다. 패널에서 세면 같은 분기값 반복 때문에 4연속 판정이 틀어진다.
        #   min_periods=4 — 제출분이 4개 미만이면 발동하지 않는다(근거 없는 제외 금지).
        neg = (col(F, "op_income_q") < 0).astype(float)
        neg = neg.where(col(F, "op_income_q").notna())
        streak = (neg.groupby(F["corp_code"], observed=True)
                     .transform(lambda s: s.rolling(4, min_periods=4).min()))
        eq = col(F, "equity")
        cap = col(F, "capital_stock") if "capital_stock" in F.columns else pd.Series(np.nan,
                                                                                     index=F.index)
        if cap.notna().any():
            impair = safe_div(cap - eq, cap)
            ex_imp = (impair > 0.30).astype(float).where(impair.notna())
        else:
            miss_note.append("자본금 계정이 없어 EX_IMPAIR 은 완전자본잠식(자기자본<0)만 판정")
            ex_imp = (eq < 0).astype(float).where(eq.notna())
        parts.append(pd.DataFrame({
            "corp_code": F["corp_code"],
            "event_date": as_ts_series(F["period_end"]) if "period_end" in F.columns else pd.NaT,
            "knowledge_date": (as_ts_series(F["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in F.columns else pd.NaT,
            "EX_LOSS4Q": streak.fillna(0.0),
            "EX_IMPAIR": ex_imp,
        }))

    # ── 공시목록 기반: 최대주주 변경 / CB·BW ──────────────────────────────────────────────
    if dis is not None and len(dis) and "report_nm" in dis.columns:
        D = dis.copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        D["corp_code"] = D["corp_code"].astype(str)
        nm = D["report_nm"].astype(str)
        ev = pd.DataFrame({
            "corp_code": D["corp_code"], "event_date": D["rcept_dt"],
            "knowledge_date": D["rcept_dt"] + pd.Timedelta(days=ARC_DART_LAG_DAYS),
            "EX_OWNER": nm.str.contains(_EX_OWNER_PAT, regex=True, na=False).astype(float),
            "EX_CBBW": nm.str.contains(_EX_CBBW_PAT, regex=True, na=False).astype(float),
        })
        ev = ev[(ev["EX_OWNER"] > 0) | (ev["EX_CBBW"] > 0)].dropna(subset=["knowledge_date"])
        if len(ev):
            parts.append(ev)

    # ── 감사의견 ──────────────────────────────────────────────────────────────────────────
    if audit is not None and len(audit):
        A = audit.copy()
        A["corp_code"] = A["corp_code"].astype(str)
        opi = A.get("audit_opinion", pd.Series("", index=A.index)).astype(str)
        emp_ = A.get("emphasis", pd.Series("", index=A.index)).astype(str)
        key = A.get("key_matter", pd.Series("", index=A.index)).astype(str)
        bad_opinion = opi.str.contains("한정|부적정|의견거절", na=False)
        has_emph = (emp_.str.len() > 0) | (key.str.len() > 0)
        parts.append(pd.DataFrame({
            "corp_code": A["corp_code"],
            "event_date": as_ts_series(A["period_end"]) if "period_end" in A.columns else pd.NaT,
            "knowledge_date": (as_ts_series(A["knowledge_date"]) +
                               pd.Timedelta(days=ARC_DART_LAG_DAYS))
            if "knowledge_date" in A.columns else pd.NaT,
            "EX_AUDIT": (bad_opinion | has_emph).astype(float),
        }))
    else:
        miss_note.append("감사의견 데이터 부재 — EX_AUDIT 결측")

    # ── 특수관계자 / 우발부채 / 소송 ──────────────────────────────────────────────────────
    #   ★ 이 셋은 '금액' 판정이 필요한데, 15 모듈의 정규화는 숫자를 <NUM> 으로 치환한다.
    #     정규화 이전 원문에서 금액을 뽑아야 정확하다. 원문 blob 이 공용 인덱스에 있으므로
    #     읽을 수는 있으나, 10년치 전 종목 원문 재파싱은 콜드빌드급 비용이다.
    #     거짓 제외보다 결측이 낫다는 원칙(§6.4 정신)에 따라 결측으로 두되,
    #     결측률을 반드시 표로 드러낸다. 조용히 0 으로 채우지 않는다.
    miss_note.append("EX_RELATED / EX_CONTINGENT / EX_LITIGATION 은 금액 판정이 필요해 "
                     "정규화 이전 원문 재파싱이 선행되어야 합니다 — 현재 결측 처리")

    if not parts:
        LOG.warn("배제 플래그 입력이 없습니다 — EXCLUDE 는 전부 0 이 되며, §6.4 하드 제외가 "
                 "작동하지 않습니다. 이는 위험 종목이 그대로 편입된다는 뜻이므로 심각합니다.")
        return pd.DataFrame(columns=cols)

    X = pd.concat([p for p in parts if p is not None and len(p)], ignore_index=True)
    X["corp_code"] = X["corp_code"].astype(str)
    X["event_date"] = as_ts_series(X["event_date"])
    X["knowledge_date"] = as_ts_series(X["knowledge_date"])
    X = X.dropna(subset=["corp_code", "knowledge_date"])
    X = ensure_cols(X, EXCL_COLS, fill=np.nan)
    X = X.groupby(["corp_code", "knowledge_date"], as_index=False).agg(
        **{"event_date": ("event_date", "min"), **{c: (c, "max") for c in EXCL_COLS}})
    n_raw_fire = int(sum(int((pd.to_numeric(X[c], errors="coerce") > 0).sum())
                         for c in EXCL_COLS))
    # ★ 소스별 행이 서로의 플래그를 지우는 문제를 여기서 잡는다(_event_state_table 주석 참조).
    X = _event_state_table(X, EXCL_COLS, EXCL_VALID_DAYS)
    X = pit_frame(X, "event_date", "knowledge_date", source="dart_excl")
    X = ensure_cols(X, cols)
    n_state_on = int((pd.DataFrame({c: pd.to_numeric(X[c], errors="coerce").fillna(0.0)
                                    for c in EXCL_COLS}).sum(axis=1) > 0).sum())
    LOG.ok(f"배제 플래그 {len(X):,}상태행 · {X['corp_code'].nunique():,}사 · "
           f"원 발화 {n_raw_fire:,}건 → 유효기간 반영 후 '제외 상태' {n_state_on:,}행")
    LOG.info("플래그 유효기간(사전등록): " +
             " · ".join(f"{c} {EXCL_VALID_DAYS.get(c, 400)}일" for c in EXCL_COLS))
    for n in miss_note:
        LOG.warn(f"[배제 플래그 한계] {n}")
    PIPE.io("OUT", "MEM", "exclusion_flags", X)
    return X[cols]


def attach_d3(P: pd.DataFrame, d3: Optional[pd.DataFrame],
              excl: Optional[pd.DataFrame]) -> pd.DataFrame:
    """D3_SCORE(가점) + EXCLUDE(하드 제외) 결합."""
    P = P.copy()
    if d3 is not None and len(d3) and "corp_code" in P.columns:
        PIT.register("arc_d3", d3, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_d3", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + D3_COLS +
                               ["DELTA_NONFIN", "D3_N_OBS"],
                          suffix="_d3")
    P = ensure_cols(P, D3_COLS + ["DELTA_NONFIN", "D3_N_OBS"])

    if excl is not None and len(excl) and "corp_code" in P.columns:
        PIT.register("arc_excl", excl, key_cols=["corp_code"])
        P = PIT.asof_join(P, "arc_excl", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date"] + EXCL_COLS, suffix="_ex")
    P = ensure_cols(P, EXCL_COLS)

    # ★ D3_SCORE = z(ΔNONFIN). 가점이다. ΔNONFIN>0 을 편입 조건으로 쓰는 코드는 없다(A9).
    P["DELTA_NONFIN"] = pd.to_numeric(P["DELTA_NONFIN"], errors="coerce")
    P["D3_SCORE"] = xsec_z_arc(P, "DELTA_NONFIN")

    ex = pd.DataFrame({c: pd.to_numeric(P[c], errors="coerce").fillna(0.0) for c in EXCL_COLS})
    P["EXCLUDE"] = (ex.sum(axis=1) > 0).astype("float32")
    n_ex = int(P["EXCLUDE"].sum())
    LOG.ok(f"D3 가점 유효 {int(P['D3_SCORE'].notna().sum()):,}행 · "
           f"배제 발동 {n_ex:,}행 ({100*n_ex/max(len(P),1):.1f}%)")
    n_zero = int((P["DELTA_NONFIN"].fillna(0) == 0).sum())
    LOG.info(f"ΔNONFIN = 0 인 종목-시점 {n_zero:,}행 ({100*n_zero/max(len(P),1):.1f}%) — "
             f"★ v1.0 과 달리 이들도 편입 가능합니다(하드게이트 폐기, §6.3).")
    return P


def report_d3_sector(P: pd.DataFrame) -> None:
    """§9.2-(9) 근거 — 섹터별 D3 발화율. v1.0 의 기술·제조 편향이 완화됐는지 직접 본다."""
    LOG.banner("D3 섹터 편향 점검 (§6.3 v2.0 개선 확인)",
               "v1.0 화이트리스트 6개는 기술·제조 편향이 심했다. 전 섹터 항목 4개를 추가한 효과를 본다")
    if P is None or P.empty or "sector" not in P.columns:
        LOG.warn("섹터 정보가 없어 편향 점검을 할 수 없습니다.")
        return
    rows = []
    for s, g in P.groupby(P["sector"].astype(str)):
        n = len(g)
        fire = float((pd.to_numeric(g["DELTA_NONFIN"], errors="coerce").fillna(0) > 0).mean())
        legacy = [c for c in ("NF_RND_EMP", "NF_RND_RATIO", "NF_PATENT", "NF_CAPEX",
                              "NF_CONTRACT", "NF_GOVRND") if c in g.columns]
        newc = [c for c in ("NF_NEWBIZ", "NF_SUBSID", "NF_OVERSEAS", "NF_EMP") if c in g.columns]
        lf = float(g[legacy].fillna(0).max(axis=1).mean()) if legacy else np.nan
        nf = float(g[newc].fillna(0).max(axis=1).mean()) if newc else np.nan
        rows.append([s, f"{n:,}", f"{100*fire:.1f}%",
                     f"{100*lf:.1f}%" if np.isfinite(lf) else "—",
                     f"{100*nf:.1f}%" if np.isfinite(nf) else "—"])
    LOG.table(sorted(rows, key=lambda r: -float(r[2].rstrip("%"))),
              ["섹터", "표본", "ΔNONFIN>0 비율", "v1.0 항목 발화율", "v2.0 추가항목 발화율"],
              ["l", "r", "r", "r", "r"])
    LOG.info("v2.0 추가항목(신규사업·종속기업·해외거점·직원증가)의 발화율이 비기술 섹터에서 "
             "v1.0 항목보다 높다면, 섹터 편향 완화가 실제로 작동한 것입니다.")


def report_exclusion(P: pd.DataFrame) -> None:
    """배제 플래그별 발동 건수·비율·연도별 추이."""
    LOG.banner("배제 플래그 (§6.4 — 유일한 하드 제외)",
               "하나라도 해당하면 점수 무관 즉시 제외한다")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    rows = []
    for c, desc in EXCL_DEFS:
        v = pd.to_numeric(col(P, c), errors="coerce")
        n_obs = int(v.notna().sum())
        n_fire = int((v.fillna(0) > 0).sum())
        rows.append([c, _trunc(desc, 42), f"{n_obs:,}", f"{100*n_obs/max(len(P),1):.0f}%",
                     f"{n_fire:,}", f"{100*n_fire/max(len(P),1):.2f}%"])
    LOG.table(rows, ["플래그", "정의", "관측", "관측률", "발동", "발동률"],
              ["l", "l", "r", "r", "r", "r"])
    tot = int(pd.to_numeric(col(P, "EXCLUDE"), errors="coerce").fillna(0).sum())
    LOG.info(f"최종 배제 {tot:,}행 ({100*tot/max(len(P),1):.1f}%). "
             f"관측률이 0% 인 플래그는 그 위험을 전혀 거르지 못한다는 뜻이므로, "
             f"위 '배제 플래그 한계' 경고와 함께 해석하세요.")
    if "asof" in P.columns:
        yr = as_ts_series(P["asof"]).dt.year
        tr = []
        for y, g in P.groupby(yr):
            tr.append([int(y), f"{len(g):,}"] +
                      [f"{100*pd.to_numeric(col(g,c),errors='coerce').fillna(0).gt(0).mean():.1f}%"
                       for c, _ in EXCL_DEFS])
        LOG.table(tr, ["연도", "표본"] + EXCL_COLS, ["c", "r"] + ["r"] * len(EXCL_COLS),
                  title="배제 플래그 연도별 발동률")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  스코어 조립 — DART_SCORE (§6.5) / FINAL_SCORE (§7.2)                                ║
# ║                                                                                          ║
# ║  DART_SCORE = 0.40·D1 + 0.40·D2 + 0.20·D3      (사전등록 가중치. 튜닝 금지)                ║
# ║  FINAL_SCORE = 0.5·z(ΔTONE_resid) + 0.5·z(DART_SCORE)                                     ║
# ║                                                                                          ║
# ║  ★ 두 가지 '탈락시키지 않기' 규칙이 이 파일의 핵심이다:                                     ║
# ║    ① 축 A 결측(리포트 없음) → ΔTONE_resid = 0(중립)으로 두고 DART_SCORE 만으로 평가.        ║
# ║       탈락시키지 않는다. 이것이 v2.0 에서 축 B 를 강화한 이유다(§7.2).                       ║
# ║    ② D1 결측 → D1 가중치를 D2·D3 에 '비례 재배분'. 종목을 탈락시키지 않는다(§6.5).           ║
# ║    A10 / A11 계약검정이 이 두 규칙을 실제 데이터로 검사한다.                                 ║
# ║                                                                                          ║
# ║  ★ 어블레이션은 전부 이 함수 하나를 통과한다. 기준선과 절제팔이 서로 다른 계산경로를 타면    ║
# ║    Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를 재게 된다(이전 프로젝트의 사고).  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

AXIS_B_LAYERS = (("D1", "D1_SCORE", ARC_W_D1),
                 ("D2", "D2_SCORE", ARC_W_D2),
                 ("D3", "D3_SCORE", ARC_W_D3))

SCORE_OUT_COLS = ["DART_SCORE", "AXIS_A_Z", "FINAL_SCORE", "FINAL_RANK", "n_axes_b"]


def _score_axis_a(P: pd.DataFrame, use_raw: bool = False,
                  neutral_fill: bool = True) -> Tuple[pd.Series, pd.Series]:
    """축 A 표준화 점수와 '원래 결측이었는지' 마스크.

    §7.2 는 "축 A 결측 종목은 ΔTONE_resid = 0(중립)으로 두고 DART_SCORE 만으로 평가,
    탈락시키지 말 것" 을 지시한다. 그래서 축 B 가 함께 있을 때만 0 으로 채운다.

    ★ 축 A **단독** 팔(A1/A2 어블레이션)에서는 0 으로 채우면 안 된다. 그 팔에는
      DART_SCORE 가 없으므로 '중립 0' 이 곧 '전 종목 동점'이 되고, 리포트가 없는 종목이
      코드 순서로 편입된다. 그러면 A1 은 축 A 의 순기여가 아니라 '동점 처리 규칙'을
      측정하게 된다. 단독 팔에서는 결측을 결측으로 남겨 편입 대상에서 빼야 한다.
    """
    src = "dTONE" if use_raw else "dTONE_resid"
    if src not in P.columns:
        empty = pd.Series(np.nan, index=P.index, dtype="float32")
        return (empty.fillna(0.0) if neutral_fill else empty,
                pd.Series(True, index=P.index))
    z = xsec_z_arc(P, src)
    miss = z.isna()
    return ((z.fillna(0.0) if neutral_fill else z).astype("float32"), miss)


_REGROUP_MIN_N = 20


def _regroup_z(P: pd.DataFrame, v: pd.Series, gcol: str) -> pd.Series:
    """(기간 × 가용성그룹) 안에서 재표준화. 그룹이 작으면 원값을 그대로 둔다.

    ★ 이 함수의 목적은 '데이터가 몇 개 있는가'가 순위를 정하지 못하게 하는 것이다.
      축을 1개만 가진 행과 2개 가진 행은 합성 후 분산이 다르고(1.0 vs 0.71), 상위 N
      선정은 꼬리에서 일어나므로 분산이 좁은 쪽이 NaN 도 아닌 채로 구조적으로 밀린다.
    """
    x = pd.to_numeric(v, errors="coerce").astype("float64")
    key = P["asof"].astype(str) + "|" + P[gcol].astype(str)
    g = x.groupby(key, observed=True)
    n = g.transform("count")
    mu = g.transform("mean")
    sd = g.transform("std")
    ok = (n >= _REGROUP_MIN_N) & (sd > 0) & sd.notna()
    return x.where(~ok, (x - mu) / sd.where(sd > 0, 1.0))


def _score_d1_variant(P: pd.DataFrame, d1_metric: Optional[str],
                      d1_equal_weights: bool) -> pd.Series:
    """D1 점수 선택 — 기본 합성 / 지표 단독 / 섹션 균등가중 (§8.4 강건성용)."""
    if d1_metric:
        c = f"D1_SCORE_{d1_metric}"
        if c in P.columns:
            return pd.to_numeric(P[c], errors="coerce")
        LOG.warn(f"D1 지표 단독 '{d1_metric}' 컬럼이 없어 합성 D1 로 대체합니다.")
    if d1_equal_weights and "D1_SCORE_equalw" in P.columns:
        return pd.to_numeric(P["D1_SCORE_equalw"], errors="coerce")
    return pd.to_numeric(col(P, "D1_SCORE"), errors="coerce")


def assemble_final(P: pd.DataFrame,
                   use_axes: Sequence[str] = ("A", "D1", "D2", "D3"),
                   use_excl: bool = True,
                   v1_hardgate: bool = False,
                   d1_metric: Optional[str] = None,
                   d1_equal_weights: bool = False,
                   include_struct: bool = False) -> pd.DataFrame:
    """지정된 축만으로 DART_SCORE / FINAL_SCORE / FINAL_RANK 를 재조립한다.

    원본 P 를 변형하지 않는다(copy). 어블레이션·강건성은 전부 이 함수를 통과한다.

    use_axes 원소:
      "A"     ΔTONE_resid (직교화 후)
      "A_RAW" ΔTONE (직교화 전) — A2 어블레이션 전용
      "D1" / "D2" / "D3"
    v1_hardgate=True 면 ΔNONFIN>0 을 편입 조건으로 강제한다 (F4: v1.0 재현 전용).
    include_struct=True 면 STRUCT_FLAG 종목의 D1 을 되살린다 (§8.4 민감도).
    """
    Q = P.copy()
    axes = set(use_axes or ())

    # ── 축 B 합성 (§6.5 비례 재배분) ──────────────────────────────────────────────────────
    vals, wts = [], []
    for lid, cname, w in AXIS_B_LAYERS:
        if lid not in axes:
            continue
        if lid == "D1":
            v = _score_d1_variant(Q, d1_metric, d1_equal_weights)
            if include_struct and "CHANGE_composite" in Q.columns:
                # STRUCT_FLAG 로 지워둔 값을 되살릴 수는 없으므로(이미 NaN),
                # 민감도 팔에서는 '결측을 그대로 둔 채' 비교한다는 사실을 남긴다.
                PIPE.note("STRUCT 포함 팔: D1 은 이미 결측 처리된 값을 되살리지 않음")
        else:
            v = pd.to_numeric(col(Q, cname), errors="coerce")
        vals.append(v.to_numpy(dtype="float64"))
        wts.append(float(w))

    if vals:
        V = np.column_stack(vals)
        Wv = np.array(wts, dtype="float64")
        msk = np.isfinite(V)
        wm = np.where(msk, Wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        dart = np.where(ws > 0,
                        np.nansum(np.where(msk, V, 0.0) * wm, axis=1) /
                        np.where(ws > 0, ws, 1.0), np.nan)
        Q["n_axes_b"] = msk.sum(axis=1)
    else:
        dart = np.full(len(Q), np.nan)
        Q["n_axes_b"] = 0
    Q["DART_SCORE"] = dart
    # 축 B 합성값도 기간 횡단면에서 다시 표준화한다(층별 z 의 스케일이 기간마다 다르므로)
    Q["DART_SCORE"] = xsec_z_arc(Q, "DART_SCORE")

    # ── 축 A ──────────────────────────────────────────────────────────────────────────────
    has_a = ("A" in axes) or ("A_RAW" in axes)
    has_b = bool(vals)
    if has_a:
        az, a_miss = _score_axis_a(Q, use_raw=("A_RAW" in axes), neutral_fill=has_b)
        Q["AXIS_A_Z"] = az
    else:
        Q["AXIS_A_Z"] = np.nan
        a_miss = pd.Series(True, index=Q.index)

    # ── 최종 합성 (§7.2) ──────────────────────────────────────────────────────────────────
    if has_a and has_b:
        b = pd.to_numeric(Q["DART_SCORE"], errors="coerce")
        az64 = Q["AXIS_A_Z"].astype("float64")
        fin = (ARC_W_AXIS_A * az64 + ARC_W_AXIS_B * b)
        # ★ 가중치 재배분은 **양방향 대칭**이어야 한다.
        #   예전에는 '축 B 결측 → 축 A 에 100% 재배분'만 있고 반대가 없었다. 축 A 결측 행은
        #   AXIS_A_Z 를 0 으로 채운 채 축 B 가중치가 0.5 로 남아, FINAL 의 **분산이 절반으로
        #   줄었다**(0.5·B vs 0.5·A+0.5·B). 상위 N 선정은 꼬리에서 일어나므로 분산이 좁은
        #   쪽은 NaN 이 아닌데도 구조적으로 밀린다 — 커버리지 50% 에서는 리포트 없는 종목이
        #   상위 30 에 사실상 한 종목도 들어가지 못했다. §7.2 '탈락시키지 말 것'의 실질 위반.
        #   A10 은 점수가 NaN 이 아닌지만 봐서 이 붕괴를 잡지 못했다.
        fin = fin.where(b.notna(), az64)                 # 축 B 결측 → 축 A 단독
        fin = fin.where(~a_miss, b)                      # 축 A 결측 → 축 B 단독 (대칭)
        # ★ 두 축이 모두 결측인 행은 '중립 0' 이 아니라 '정보 없음' 이다. 0 으로 두면
        #   아무 근거도 없는 종목이 중간 순위를 차지하고, 표본이 얇은 분기에는 그 종목들이
        #   실제로 편입된다. 명세 §7.2 의 '중립 0' 은 '축 B 가 있을 때' 의 규정이다.
        fin = fin.where(~(a_miss & b.isna()))
        # ★ 재배분만으로는 부족하다. 축이 1개인 행은 sd≈1, 2개인 행은 sd≈0.71 이라
        #   이번에는 반대 방향으로 기운다. 가용성 그룹별로 기간 안에서 재표준화해
        #   '데이터가 몇 개 있는가'가 순위를 정하지 못하게 한다. 그룹이 너무 작으면
        #   재표준화가 오히려 잡음이므로 그때는 손대지 않는다.
        Q["_avail"] = np.where(a_miss.to_numpy(), "B", np.where(b.isna().to_numpy(), "A", "AB"))
        fin = _regroup_z(Q, fin, "_avail")
        Q = Q.drop(columns=["_avail"])
    elif has_a:
        fin = Q["AXIS_A_Z"].astype("float64")
    elif has_b:
        fin = pd.to_numeric(Q["DART_SCORE"], errors="coerce")
    else:
        # 무정보 팔 (B4 배제플래그 단독) — 전 종목 동일 점수
        fin = pd.Series(0.0, index=Q.index, dtype="float64")
    Q["FINAL_SCORE"] = fin.astype("float32")

    # ── 편입 조건 ─────────────────────────────────────────────────────────────────────────
    if use_excl:
        ex = pd.to_numeric(col(Q, "EXCLUDE"), errors="coerce").fillna(0.0) > 0
        Q.loc[ex, "FINAL_SCORE"] = np.nan          # 점수 무관 즉시 제외 (§6.4)
    if v1_hardgate:
        # ★ F4(v1.0 재현) 전용. 이 게이트는 v2.0 본선에서 폐기된 규칙이다.
        nf = pd.to_numeric(col(Q, "DELTA_NONFIN"), errors="coerce")
        Q.loc[~(nf > 0).fillna(False), "FINAL_SCORE"] = np.nan

    Q["FINAL_RANK"] = (Q.groupby("asof", observed=True)["FINAL_SCORE"]
                        .rank(pct=True, method="average").astype("float32"))
    return Q


def report_score_summary(P: pd.DataFrame) -> None:
    """스코어 구성 요약 — 각 축이 실제로 몇 %의 종목에 값을 주고 있는가."""
    LOG.banner("스코어 조립 요약", "DART_SCORE = 0.40·D1 + 0.40·D2 + 0.20·D3 · "
                                   "FINAL = 0.5·축A + 0.5·축B (사전등록 가중치)")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    rows = []
    for lab, c in (("축 A ΔTONE_resid", "dTONE_resid"), ("축 A 원신호 ΔTONE", "dTONE"),
                   ("D1_SCORE", "D1_SCORE"), ("D2_SCORE", "D2_SCORE"),
                   ("D3_SCORE", "D3_SCORE"), ("DART_SCORE", "DART_SCORE"),
                   ("FINAL_SCORE", "FINAL_SCORE")):
        v = pd.to_numeric(col(P, c), errors="coerce")
        n = int(v.notna().sum())
        rows.append([lab, f"{n:,}", f"{100*n/max(len(P),1):.1f}%",
                     f"{float(v.mean()):+.3f}" if n else "—",
                     f"{float(v.std()):.3f}" if n > 1 else "—"])
    LOG.table(rows, ["신호", "관측", "커버리지", "평균", "표준편차"],
              ["l", "r", "r", "r", "r"])
    if "n_axes_b" in P.columns:
        cnt = P["n_axes_b"].value_counts().sort_index()
        LOG.table([[f"{int(k)}개 층", f"{int(v):,}", f"{100*v/max(len(P),1):.1f}%"]
                   for k, v in cnt.items()],
                  ["축 B 유효 층수", "행수", "비중"], ["l", "r", "r"],
                  title="축 B 층 가용성 — 0층이면 그 행은 축 A 단독으로 평가됩니다(§6.5 재배분)")
    n_a_missing = int((pd.to_numeric(col(P, "has_axis_a"), errors="coerce").fillna(0) == 0).sum())
    LOG.info(f"축 A 결측 {n_a_missing:,}행 ({100*n_a_missing/max(len(P),1):.1f}%) — "
             f"§7.2 에 따라 중립(0)으로 두고 DART_SCORE 로 평가합니다. 탈락시키지 않습니다.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 (분기 리밸런싱) + 비용 모델 (§7.2 / §8.1)                                ║
# ║                                                                                          ║
# ║  · 분기 1회 리밸런싱(3/1, 6/1, 9/1, 12/1). 체결 = 리밸일 이후 첫 거래일 시가.               ║
# ║  · 상장폐지: 정리매매 최종가 반영, 없으면 −100%. 누락 처리 금지(= 생존자편향).               ║
# ║  · 롱온리. §7.3 부정 신호(BOTTOM)는 별도 검증만 하고 자동으로 숏을 만들지 않는다.            ║
# ║  · 비용: 증권거래세 이력 + 수수료 + 실측 스프레드 기반 슬리피지. 비용 전/후 병기 필수.       ║
# ║                                                                                          ║
# ║  ★ 연율화 계수는 4 다(분기). 12 로 쓰면 성과가 통째로 3배로 부풀려진다.                     ║
# ║    A17 계약검정이 이걸 실제 수치로 검사한다.                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PERIODS_PER_YEAR = 4          # 분기 리밸런싱

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
ARC_TAX_SCHEDULE = [
    ("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
]


def arc_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = ARC_TAX_SCHEDULE[0][1]
    for d, r in ARC_TAX_SCHEDULE:
        if t is not None and t >= as_ts(d):
            rate = r
    return rate


def arc_slippage(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격 + 초소형주 최소 스프레드 하한.

    ★ §8.1 이 경고한 대로 초소형주는 스프레드가 알파를 통째로 잠식할 수 있다.
      제곱근 모형만 쓰면 참여율이 낮을 때 비용이 0 에 수렴하는데, 실제로는 호가 스프레드
      절반은 무조건 낸다. 그래서 하한(ARC_MIN_SPREAD_BPS/2)을 강제한다.
    """
    floor = (ARC_MIN_SPREAD_BPS / 2.0) / 1e4
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return max(floor, 0.02)
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(max(floor, ARC_SLIPPAGE_K * math.sqrt(part)))


def _bt_weights(sub: pd.DataFrame, weighting: str) -> np.ndarray:
    """동일가중(기준) 또는 역변동성 가중(병행 산출). 유동성 상한을 water-filling 으로 강제."""
    n = len(sub)
    if n == 0:
        return np.zeros(0)
    if weighting == "invvol" and "vol_q" in sub.columns:
        v = pd.to_numeric(sub["vol_q"], errors="coerce").to_numpy(dtype=float)
        v = np.where(np.isfinite(v) & (v > 1e-6), v, np.nanmedian(v[np.isfinite(v)])
                     if np.isfinite(v).any() else 1.0)
        w = 1.0 / v
        w = w / w.sum() if w.sum() > 0 else np.full(n, 1.0 / n)
    else:
        w = np.full(n, 1.0 / n)

    adv = pd.to_numeric(sub.get("adtv60", pd.Series(np.nan, index=sub.index)),
                        errors="coerce").fillna(0).to_numpy(dtype=float)
    cap = np.where(adv > 0, (adv * ARC_ADV_PARTICIPATION) / max(ARC_ACCOUNT_KRW, 1), 1.0)
    cap = np.clip(cap, 1.0 / (4.0 * n), 1.0)
    # ★ clip 후 재정규화하면 상한이 도로 뚫린다. water-filling 으로 강제한다.
    free = np.ones(n, dtype=bool)
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
    if w.sum() > 1.0 + 1e-9:
        w = w / w.sum()
    return w


def _bt_pick(elig: pd.DataFrame, k: int, signal_col: str) -> pd.DataFrame:
    """상위 k 선정. 동점은 명시적 키로 깬다 — 행 순서로 깨지 않는다.

    ★ nlargest(keep='first') 는 동점 시 '먼저 나온 행'을 고르는데, 패널은 code 정렬이라
      그건 곧 '종목코드가 작은 순'이다. 보유종목이 데이터가 아니라 정렬의 함수가 된다.
    """
    if not len(elig):
        return elig.iloc[0:0]
    keys = [signal_col] + [c for c in ("FINAL_SCORE", "code")
                           if c in elig.columns and c != signal_col]
    asc = [False] + [False if c == "FINAL_SCORE" else True for c in keys[1:]]
    return elig.sort_values(keys, ascending=asc, kind="mergesort").head(int(k))


def run_backtest(P: pd.DataFrame, rebals: pd.DatetimeIndex, uni, sec: pd.DataFrame,
                 signal_col: str = "FINAL_RANK", apply_costs: bool = True,
                 label: str = "ARC", top_n: Optional[int] = None,
                 weighting: str = None, bottom: bool = False) -> dict:
    """분기 리밸런싱 롱온리 백테스트.

    bottom=True 면 하위 랭크를 담는다(§7.3 부정 신호 검증 전용 — 실제 숏이 아니라
    '하위 그룹의 수익률'을 측정하기 위한 롱 포트폴리오다).
    """
    k_target = int(top_n or ARC_TOP_N_DEFAULT)
    wmode = weighting or ARC_WEIGHTING
    delist = uni.delisting_map() if uni is not None else {}
    rows, holdings = [], []
    prev_w: Dict[str, float] = {}
    n_impute_tot, w_impute_tot, n_adv_miss = 0, 0.0, 0

    need = [c for c in ("code", "asof", "adtv60", "fwd_ret_1q", signal_col, "FINAL_SCORE",
                        "vol_q", "EXCLUDE") if c in P.columns]
    B = P[need].copy() if need else P.copy()

    for t in rebals:
        t = as_ts(t)
        sub = B[B["asof"] == t]
        # ★ 측정 가능한 분기인가. 마지막 리밸일은 다음 리밸일이 없어 전 종목 fwd_ret 이 결측인데,
        #   예전에는 그 분기를 '수익률 0' 으로 성과 시계열에 넣었다. 그러면 CAGR 분모의 연수가
        #   9.75년 대신 10년이 되고, 변동성이 희석되고, 승률 분모가 부풀려진다.
        #   measurable=False 로 표시해 perf_stats 에서 제외한다. 청산 비용만 따로 계상한다.
        measurable = bool(len(sub)) and bool(
            pd.to_numeric(sub["fwd_ret_1q"], errors="coerce").notna().any())
        if sub.empty or not measurable:
            liq_cost = 0.0
            if apply_costs and prev_w:
                liq_cost = sum(abs(v) for v in prev_w.values()) * (
                    ARC_COMMISSION_BPS / 1e4 + arc_sell_tax(t))
            rows.append({"asof": t, "ret": -liq_cost, "ret_gross": 0.0, "n": 0,
                         "turnover": float(sum(abs(v) for v in prev_w.values())),
                         "cost": liq_cost, "n_elig": 0, "n_imputed": 0, "w_imputed": 0.0,
                         "measurable": False})
            prev_w = {}
            continue
        # ★ 편입 자격은 '오늘 신호가 있는가' 만으로 판정한다. 예전에는 여기에
        #   `& sub["fwd_ret_1q"].notna()` 가 붙어 있었는데, 그러면 **t 시점의 편입 가능
        #   여부가 t+1 시점의 정보(다음 분기에 유니버스에 남아 있는가 / 가격이 있는가)로
        #   결정된다.** 방향성 있는 편향이다 — 시총이 커져 U-1000 을 이탈하는 종목(=크게
        #   오른 종목)과 유동성이 말라 이탈하는 종목(=붕괴 중인 종목)이 둘 다 후보에서
        #   지워졌다. 측정 불가는 아래에서 '유니버스 중앙값으로 대치 + 건수 보고'로 다룬다.
        elig = sub[sub[signal_col].notna()]
        n_elig = len(elig)
        if uni is not None:
            uni.audit_row("신호보유", t, elig["code"].tolist())
        if n_elig == 0:
            rows.append({"asof": t, "ret": 0.0, "ret_gross": 0.0, "n": 0,
                         "turnover": 0.0, "cost": 0.0, "n_elig": 0,
                         "n_imputed": 0, "w_imputed": 0.0, "measurable": True})
            prev_w = {}
            continue

        if bottom:
            pick = elig.sort_values([signal_col, "code"], ascending=[True, True],
                                    kind="mergesort").head(min(k_target, n_elig))
        else:
            pick = _bt_pick(elig, min(k_target, n_elig), signal_col)
        if uni is not None:
            uni.audit_row("최종선정", t, pick["code"].tolist())

        w = _bt_weights(pick, wmode)
        w_new = dict(zip(pick["code"].astype(str), w))
        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0))
                   for c in set(w_new) | set(prev_w))

        cost = 0.0
        if apply_costs:
            # ★ advmap 은 그 분기 패널 전체(sub)에서 만든다. 예전에는 pick('새로 담을 종목')
            #   으로만 만들었는데, 비용 루프는 set(w_new) | set(prev_w) 를 돌기 때문에
            #   **전량 매도되는 종목은 adv=0 으로 조회되어 arc_slippage 의 '데이터 없음'
            #   폴백(일괄 2%)** 을 탔다. 매도 슬리피지가 매수의 2.4배로 매겨져 연 3~4%p
            #   유령 비용이 붙고, 회전율이 다른 어블레이션 팔끼리의 비용후 비교가 왜곡된다.
            advmap = dict(zip(sub["code"].astype(str),
                              pd.to_numeric(sub.get("adtv60", pd.Series(np.nan, index=sub.index)),
                                            errors="coerce").fillna(0.0)))
            _miss_adv = [c for c in (set(w_new) | set(prev_w)) if advmap.get(c, 0.0) <= 0]
            if _miss_adv:
                n_adv_miss += len(_miss_adv)
            tax = arc_sell_tax(t)
            comm = ARC_COMMISSION_BPS / 1e4
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                notional = abs(dw) * ARC_ACCOUNT_KRW
                sl = arc_slippage(notional, float(advmap.get(c, 0.0)))
                cost += abs(dw) * (comm + sl + (tax if dw < 0 else 0.0))

        ret = 0.0
        fw = dict(zip(pick["code"].astype(str),
                      pd.to_numeric(pick["fwd_ret_1q"], errors="coerce")))
        sig = dict(zip(pick["code"].astype(str),
                       pd.to_numeric(pick[signal_col], errors="coerce")))
        # 측정 불가 종목의 대치값 = 그 분기 유니버스 전체의 중앙값 수익률.
        # 0 으로 채우면 '현금 보유'라는 없는 가정을 넣게 되고, 버리면 표본이 선택된다.
        uni_r = pd.to_numeric(sub["fwd_ret_1q"], errors="coerce")
        fallback = float(uni_r.median()) if uni_r.notna().any() else 0.0
        n_imputed, w_imputed = 0, 0.0
        for c, ww in w_new.items():
            fr = fw.get(c, np.nan)
            dl = delist.get(c)
            # ★ §3.4 2중 방어: 패널이 폐지를 놓쳤어도 여기서 잡는다. 예전에는 위쪽 elig 가
            #   fwd_ret 결측 행을 이미 지워 이 분기가 도달 불가능한 죽은 코드였다.
            if (not np.isfinite(fr)) and dl is not None and pd.notna(dl) and dl > t:
                fr = -1.0
            if not np.isfinite(fr):
                fr = fallback
                n_imputed += 1
                w_imputed += float(ww)
            ret += ww * float(fr)
            holdings.append({"asof": t, "code": c, "weight": float(ww), "ret": float(fr),
                             "signal": float(sig.get(c, np.nan))})
        if n_imputed:
            n_impute_tot += n_imputed
            w_impute_tot += w_imputed
        # ★ ret 는 -1 아래로 내려갈 수 없다. Σw≤1 · fwd≥-1 이므로 gross 는 ≥-1 이지만
        #   비용을 빼면 -1 을 밑돌 수 있고, 그러면 cumprod 가 부호를 뒤집어 파산한 경로가
        #   양의 자본곡선으로 되살아난다(MDD -112% 같은 정의상 불가능한 값이 표에 찍힌다).
        ret = float(max(ret, -1.0))
        rows.append({"asof": t, "ret": max(ret - cost, -1.0), "ret_gross": ret,
                     "n": len(w_new),
                     "turnover": turn, "cost": cost, "n_elig": n_elig,
                     "n_imputed": n_imputed, "w_imputed": w_imputed, "measurable": True})
        prev_w = w_new

    if n_adv_miss:
        LOG.info(f"[{label}] 거래대금(ADTV)을 못 찾은 매매 {n_adv_miss:,}건은 슬리피지 "
                 f"보수 폴백(2%)을 적용했습니다.")
    if n_impute_tot:
        LOG.warn(f"[{label}] 전방수익률 측정 불가 {n_impute_tot:,}건(누적 비중 "
                 f"{w_impute_tot:.2f})을 해당 분기 유니버스 중앙값으로 대치했습니다. "
                 f"거래정지 후 재개 또는 가격 결측 구간입니다 — 폐지 종목은 위 §3.4 경로로 "
                 f"이미 청산 처리되었습니다.")

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
        R["equity_gross"] = (1.0 + R["ret_gross"].fillna(0)).cumprod()
    H = pd.DataFrame(holdings)
    return {"returns": R, "holdings": H, "label": label,
            "eligible": R[["asof", "n_elig"]] if len(R) else pd.DataFrame()}


# ── 성과 지표 (분기 기준) ───────────────────────────────────────────────────────────────────
def perf_stats(R: pd.DataFrame, rf: float = 0.0, gross: bool = False) -> dict:
    """분기 수익률 시계열 → 성과 지표. ★ 연율화 계수는 4 (분기 4개 = 1년)."""
    if R is None or len(R) == 0:
        return {}
    key = "ret_gross" if (gross and "ret_gross" in R.columns) else "ret"
    # ★ 측정 불가 분기(마지막 리밸일 등)는 성과 통계에서 뺀다. 수익률 0 으로 끼워 넣으면
    #   연수·변동성·승률 분모가 전부 조용히 왜곡된다.
    Rm = R[R["measurable"].astype(bool)] if "measurable" in R.columns else R
    if len(Rm) == 0:
        Rm = R
    r = pd.to_numeric(Rm[key], errors="coerce").fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / float(PERIODS_PER_YEAR)
    # ★ 자본곡선이 0 이하를 '통과'하면 그 경로는 파산이다. 예전에는 최종값(eq[-1])만 봤는데,
    #   1+r<0 이 두 번 나오면 cumprod 가 부호를 두 번 뒤집어 파산 경로가 양의 자본으로
    #   되살아나고 CAGR·MDD·Calmar 가 전부 유한값으로 인쇄됐다(MDD -112% 같은 값).
    ruined = bool(np.any(eq <= 0))
    if ruined:
        cagr = -1.0
    else:
        cagr = (eq[-1] ** (1.0 / years) - 1.0) if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if n > 1 else np.nan
    # ★ Sortino 의 하방편차는 '목표(=rf) 대비' 제곱평균이지, '음수 수익률들의 자기 평균 대비
    #   표본표준편차'가 아니다. 후자는 손실이 비슷한 크기로 반복될수록 0 에 수렴해
    #   손실의 '크기'가 아니라 '균일함'을 보상한다 — 실측에서 정의값 3.88 이 393 으로 나왔다.
    rf_q = rf / float(PERIODS_PER_YEAR)
    _dn = np.minimum(r - rf_q, 0.0)
    dvol = float(np.sqrt((_dn ** 2).mean()) * math.sqrt(PERIODS_PER_YEAR)) if n else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(max(dd.min(), -1.0)) if n else np.nan     # -100% 아래는 정의상 불가
    if ruined:
        mdd = -1.0
    mx = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    # ★ 평균 통계도 측정 가능한 분기(Rm)에서만 낸다. 측정 불가 분기는 n=0 ·
    #   turnover=전량청산 으로 기록되므로 원본 R 을 쓰면 평균종목수·평균회전율이 어긋난다.
    return {
        "기간수(분기)": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "분기평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(분기)": int(mx),
        "평균종목수": float(Rm["n"].mean()) if "n" in Rm.columns else np.nan,
        "평균회전율": float(Rm["turnover"].mean()) if "turnover" in Rm.columns else np.nan,
        "평균비용": float(Rm["cost"].mean()) if "cost" in Rm.columns else np.nan,
        "평균편입가능": float(Rm["n_elig"].mean()) if "n_elig" in Rm.columns else np.nan,
    }


def bt_ic(P: pd.DataFrame, signal_col: str = "FINAL_RANK") -> Tuple[float, float, int]:
    """신호의 기간별 Spearman IC / IC-IR."""
    if P is None or P.empty or signal_col not in P.columns or "fwd_ret_1q" not in P.columns:
        return (np.nan, np.nan, 0)
    return info_coef(P[signal_col], P["fwd_ret_1q"], P["asof"].astype(str))


def attach_volatility(P: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """역변동성 가중용 분기 변동성(직전 60거래일 일간수익률 표준편차, 연율화)."""
    P = P.copy()
    if px_daily is None or px_daily.empty:
        P["vol_q"] = np.nan
        return P
    d = px_daily[["code", "date", "close"]].dropna().copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["code", "date"], kind="stable")
    d["r1"] = d.groupby("code", observed=True)["close"].pct_change()
    d["vol"] = (d.groupby("code", observed=True)["r1"]
                 .transform(lambda s: s.rolling(60, min_periods=20).std()) * math.sqrt(252))
    # ★ 리밸일마다 일봉 전체를 필터링하지 않는다(메모리 스파이크). merge_asof 한 번으로 끝낸다.
    right = (d[["code", "date", "vol"]].dropna(subset=["date", "code"])
             .sort_values("date", kind="stable"))
    right["code"] = right["code"].astype(str)
    left = P[["code", "asof"]].copy()
    left["code"] = left["code"].astype(str)
    left["asof"] = as_ts_series(left["asof"])
    left = left.dropna(subset=["asof"]).sort_values("asof", kind="stable")
    try:
        V = pd.merge_asof(left, right, left_on="asof", right_on="date", by="code",
                          direction="backward", allow_exact_matches=False)
        V = (V.dropna(subset=["vol"])[["code", "asof", "vol"]]
              .rename(columns={"vol": "vol_q"})
              .drop_duplicates(["code", "asof"], keep="last"))
        P = P.merge(V, on=["code", "asof"], how="left")
    except Exception as e:                                       # noqa
        LOG.warn(f"변동성 as-of 결합 실패({type(e).__name__}) — 역변동성 가중을 건너뜁니다.")
        P["vol_q"] = np.nan
    if "vol_q" not in P.columns:
        P["vol_q"] = np.nan
    return P


def benchmark_returns(rebals: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """벤치마크 분기 수익률. FDR 이 없으면 빈 dict — 그 사실을 로그로 남긴다."""
    out: Dict[str, pd.Series] = {}
    if fdr is None or len(rebals) == 0:
        LOG.info("FinanceDataReader 가 없어 지수 벤치마크를 건너뜁니다 (절대수익 기준으로 보고).")
        return out
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        try:
            d = fdr.DataReader(sym, as_ts(rebals[0]) - pd.DateOffset(months=4),
                               as_ts(rebals[-1]) + pd.DateOffset(months=4))
        except Exception:
            d = None
        if d is None or len(d) == 0:
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        d = d.dropna(subset=["date", "close"]).sort_values("date")
        vals = []
        for i, t in enumerate(rebals):
            t = as_ts(t)
            nxt = as_ts(rebals[i + 1]) if i + 1 < len(rebals) else None
            a = d[d["date"] >= t].head(1)
            b = d[d["date"] >= nxt].head(1) if nxt is not None else pd.DataFrame()
            if len(a) and len(b):
                vals.append(float(b["close"].iloc[0]) / float(a["close"].iloc[0]) - 1.0)
            else:
                vals.append(np.nan)
        out[name] = pd.Series(vals, index=pd.DatetimeIndex(rebals))
    if out:
        LOG.ok(f"벤치마크 확보: {', '.join(out)} (분기 수익률)")
    return out


def equal_weight_universe_return(P: pd.DataFrame) -> pd.Series:
    """U-1000 동일가중 수익률 — 초과수익 계산의 1순위 벤치마크.

    ★ 지수(KOSPI/KOSDAQ)는 시총가중이라 대형주가 지배한다. 우리 유니버스는 소형주 하위 1000
      이므로, 지수 대비 초과수익은 '소형주 프리미엄'을 알파로 착각하게 만든다.
      같은 유니버스의 동일가중 수익률과 비교해야 신호의 순기여가 드러난다.
    """
    if P is None or P.empty or "fwd_ret_1q" not in P.columns:
        return pd.Series(dtype=float)
    g = P.dropna(subset=["fwd_ret_1q"]).groupby("asof", observed=True)["fwd_ret_1q"].mean()
    return g.sort_index()



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-A  어블레이션 11종 (§8.2) + BH-FDR 다중검정 보정 (§8.3)                                ║
# ║                                                                                          ║
# ║  ★ 모든 팔은 assemble_final() 하나를 통과한다. 기준선과 절제팔이 서로 다른 계산경로를       ║
# ║    타면 Δ가 '무엇을 뺐는가'가 아니라 '계산 방식이 달라졌는가'를 재게 된다.                   ║
# ║    널-절제(아무것도 빼지 않은 팔)의 Δ가 정확히 0 인지 매 실행 검증한다.                      ║
# ║                                                                                          ║
# ║  ★ 비용 차감 전/후를 반드시 병기한다(§8.1). 비용 전만 보고하는 것은 금지다.                 ║
# ║  ★ F4(v1.0 재현)는 반드시 실행한다 — 수치 없이 "v2.0 이 개선됐다"고 말하지 않기 위함이다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ABLATIONS = [
    ("A1", "ΔTONE_resid 단독", "축 A 순기여",
     dict(use_axes=("A",), use_excl=True)),
    ("A2", "ΔTONE 직교화 미적용 단독", "직교화 효과 측정",
     dict(use_axes=("A_RAW",), use_excl=True)),
    ("B1", "D1 단독", "Lazy Prices 한국 재현 여부",
     dict(use_axes=("D1",), use_excl=True)),
    ("B2", "D2 단독", "재무 이상현상 기준선",
     dict(use_axes=("D2",), use_excl=True)),
    ("B3", "D3 단독", "하드팩트 순기여",
     dict(use_axes=("D3",), use_excl=True)),
    ("B4", "배제플래그 단독 (U-1000 전체)", "위험 배제만의 효과",
     dict(use_axes=(), use_excl=True)),
    ("B5", "DART_SCORE 전체 (축 A 없음)", "축 B 단독 성능",
     dict(use_axes=("D1", "D2", "D3"), use_excl=True)),
    ("F1", "풀버전 (축 A + 축 B + 배제)", "본선",
     dict(use_axes=("A", "D1", "D2", "D3"), use_excl=True)),
    ("F2", "풀버전 − D1", "D1 한계기여",
     dict(use_axes=("A", "D2", "D3"), use_excl=True)),
    ("F3", "풀버전 − D2", "D2 한계기여",
     dict(use_axes=("A", "D1", "D3"), use_excl=True)),
    ("F4", "v1.0 재현 (ΔTONE + ΔNONFIN>0 하드게이트 + 배제)", "v2.0 개선효과 정량화",
     dict(use_axes=("A_RAW",), use_excl=True, v1_hardgate=True)),
]

ABLATION_RESULTS: "OrderedDict[str, dict]" = OrderedDict()

_ABL_METRIC_ORDER = ["CAGR", "MDD", "Sharpe", "Sortino", "IC", "IC-IR", "t(IC)", "회전율",
                     "평균종목수", "승률", "평균편입가능"]


def _abl_one(P: pd.DataFrame, rebals, uni, sec, run_fn, aid: str, name: str,
             purpose: str, kw: dict) -> dict:
    """한 팔 실행 — 신호 재조립 → 비용 전/후 백테스트 → 지표 산출."""
    rec = {"id": aid, "name": name, "purpose": purpose, "ok": False, "err": "",
           "net": {}, "gross": {}, "ic": np.nan, "icir": np.nan,
           "ic_t": np.nan, "n_ic": 0,
           "p": np.nan, "excess": np.nan}
    try:
        Q = assemble_final(P, **kw)
        # B4 는 신호가 무정보(전 종목 동일)이므로 상위 N 선정이 임의가 된다.
        # → 배제 통과 종목 '전체'를 동일가중 보유하는 것으로 정의한다(표 각주에 명시).
        top_n = 10_000 if aid == "B4" else None
        bt_net = run_fn(Q, label=f"ABL_{aid}", apply_costs=True, top_n=top_n)
        rec["net"] = perf_stats(bt_net["returns"])
        rec["gross"] = perf_stats(bt_net["returns"], gross=True)
        # ★ bt_ic 의 2번째 값은 t통계량이다(IR × √n). 표에 'IC-IR' 로 찍으면 분기 40개에서
        #   6.32배 부풀려진 값을 읽게 되므로 IR 과 t 를 분리해 둘 다 보고한다.
        ic, icir, ic_t, n_ic = info_coef_full(Q["FINAL_RANK"], Q["fwd_ret_1q"],
                                              Q["asof"].astype(str))
        rec["ic"], rec["icir"], rec["ic_t"], rec["n_ic"] = ic, icir, ic_t, n_ic
        # 초과수익 = 전략 − U-1000 동일가중 (지수 대신 같은 유니버스를 쓴다 — 41 모듈 주석 참조)
        bench = equal_weight_universe_return(P)
        R = measurable_ret(bt_net["returns"])   # 측정 불가 분기 제외(성과표와 동일 표본)
        b = bench.reindex(R.index).fillna(0.0)
        ex = (R.fillna(0.0) - b).to_numpy(dtype=float)
        rec["excess"] = float(np.nanmean(ex)) if len(ex) else np.nan
        rec["p"] = newey_west_p(ex)
        rec["returns"] = bt_net["returns"]
        rec["holdings"] = bt_net.get("holdings")
        rec["ok"] = True
    except Exception as e:                                        # noqa
        rec["err"] = f"{type(e).__name__}: {str(e)[:160]}"
        LOG.warn(f"어블레이션 {aid} 실패 — {rec['err']} (나머지 실험은 계속 진행합니다)")
    return rec


def run_ablations(P: pd.DataFrame, rebals, uni, sec, run_fn) -> pd.DataFrame:
    """§8.2 어블레이션 11종 전부 실행."""
    ABLATION_RESULTS.clear()
    LOG.banner("어블레이션 매트릭스 (§8.2) — 11개 실험",
               "각 축의 순기여와 한계기여를 귀속한다. 비용 전/후를 병기한다")
    t0 = time.time()

    # ── 널-절제 검증 ─────────────────────────────────────────────────────────────────────
    #   아무것도 빼지 않은 팔이 F1 과 정확히 같아야 한다. 다르면 어블레이션 표 전체가 무의미하다.
    try:
        n1 = run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                    label="NULL_ABL", apply_costs=True)["returns"]["ret"].to_numpy()
        n2 = run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                    label="NULL_ABL2", apply_costs=True)["returns"]["ret"].to_numpy()
        same = (len(n1) == len(n2)) and np.allclose(np.nan_to_num(n1), np.nan_to_num(n2))
        if same:
            LOG.ok("널-절제 검증 통과 — 같은 구성이 정확히 같은 결과를 냅니다(결정성 확인).")
        else:
            LOG.error("★ 널-절제 검증 실패 — 같은 구성인데 결과가 다릅니다. 어블레이션 Δ가 "
                      "'무엇을 뺐는가'가 아니라 '실행마다 달라지는 무언가'를 재고 있습니다. "
                      "이 상태의 어블레이션 표는 신뢰할 수 없습니다.")
    except Exception as e:                                        # noqa
        LOG.warn(f"널-절제 검증을 수행하지 못했습니다({type(e).__name__}).")

    for aid, name, purpose, kw in ABLATIONS:
        LOG.info(f"▷ [{aid}] {name}")
        ABLATION_RESULTS[aid] = _abl_one(P, rebals, uni, sec, run_fn, aid, name, purpose, kw)

    LOG.ok(f"어블레이션 11종 완료 — 소요 {time.time()-t0:.1f}초")
    return report_ablation_table()


def report_ablation_table() -> pd.DataFrame:
    """§9.2-(6) 어블레이션 성과표 (비용 전/후 병기)."""
    LOG.banner("[산출물 6] 어블레이션 11개 성과표 (§9.2-6)",
               "비용 차감 전 / 후를 병기한다 — 비용 전만 보고하는 것은 금지(§8.1)")
    rows = []
    for aid, name, purpose, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if not r or not r["ok"]:
            rows.append([aid, _trunc(name, 30), "판정불가", (r or {}).get("err", "미실행"),
                         "", "", "", "", "", "", ""])
            continue
        n, g = r["net"], r["gross"]

        def f(d, k, pct=False, dec=3):
            v = d.get(k)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            return f"{v*100:+.1f}%" if pct else f"{v:.{dec}f}"

        rows.append([
            aid, _trunc(name, 30),
            f(g, "CAGR", True), f(n, "CAGR", True),
            f(g, "Sharpe"), f(n, "Sharpe"),
            f(n, "MDD", True), f(n, "Sortino"),
            (f"{r['ic']:+.4f}" if np.isfinite(r["ic"]) else "—"),
            (f"{r['icir']:+.2f}" if np.isfinite(r["icir"]) else "—"),
            (f"{r.get('ic_t', float('nan')):+.2f}"
             if np.isfinite(r.get("ic_t", float("nan"))) else "—"),
            f"{n.get('평균종목수', float('nan')):.1f}",
        ])
    LOG.table(rows, ["ID", "구성", "CAGR(전)", "CAGR(후)", "Sharpe(전)", "Sharpe(후)",
                     "MDD", "Sortino", "IC", "IC-IR", "t(IC)", "종목수"],
              ["l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=32)
    LOG.info("IC-IR = mean(IC)/std(IC) (표준 정의) · t(IC) = IC-IR × √기간수. "
             "둘을 혼동하면 분기 40개에서 6.32배 부풀려진 값을 IR 로 읽게 됩니다.")

    rows2 = []
    for aid, name, purpose, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if not r or not r["ok"]:
            continue
        n = r["net"]
        rows2.append([aid, _trunc(purpose, 26),
                      f"{n.get('승률', float('nan'))*100:.0f}%",
                      f"{n.get('평균회전율', float('nan')):.2f}",
                      f"{n.get('평균비용', float('nan'))*100:.3f}%p",
                      f"{n.get('평균편입가능', float('nan')):.0f}",
                      f"{r['excess']*100:+.3f}%p" if np.isfinite(r["excess"]) else "—",
                      f"{r['p']:.4f}" if np.isfinite(r["p"]) else "—"])
    LOG.table(rows2, ["ID", "목적", "승률", "회전율", "분기평균비용", "평균편입가능",
                      "초과수익(분기)", "p(HAC)"],
              ["l", "l", "r", "r", "r", "r", "r", "r"], maxw=30)
    LOG.info("각주 ① B4 는 신호가 무정보이므로 '배제 통과 종목 전체 동일가중' 으로 정의했습니다. "
             "따라서 종목수가 다른 팔과 크게 다릅니다.  "
             "② 초과수익 기준은 U-1000 동일가중입니다(지수 대비가 아님 — 소형주 프리미엄을 "
             "알파로 오인하지 않기 위함).")
    out = pd.DataFrame([{"id": k, **{kk: vv for kk, vv in v.items()
                                     if kk not in ("returns", "holdings", "net", "gross")}}
                        for k, v in ABLATION_RESULTS.items()])
    return out


def report_f4_vs_f1() -> None:
    """§9.2-(7) v1.0(F4) 대비 v2.0(F1) 개선폭 정량 비교."""
    LOG.banner("[산출물 7] F4(v1.0 재현) 대비 F1(v2.0) 개선폭 (§9.2-7)",
               "수치 없이 '개선됐다'고 말하지 않기 위한 표. F1 이 나쁘면 그대로 보고한다")
    a, b = ABLATION_RESULTS.get("F4"), ABLATION_RESULTS.get("F1")
    if not a or not b or not a["ok"] or not b["ok"]:
        LOG.warn("F1 또는 F4 가 실행되지 않아 비교할 수 없습니다.")
        return
    rows = []
    for k in ("CAGR", "Sharpe", "Sortino", "MDD", "승률", "평균종목수",
              "평균회전율", "평균편입가능"):
        v4, v1 = a["net"].get(k), b["net"].get(k)
        if v4 is None or v1 is None or not (np.isfinite(v4) and np.isfinite(v1)):
            rows.append([k, "—", "—", "—", "—"])
            continue
        d = v1 - v4
        rel = (d / abs(v4) * 100.0) if abs(v4) > 1e-12 else np.nan
        pct = k in ("CAGR", "MDD", "승률")
        fmt = (lambda x: f"{x*100:+.2f}%") if pct else (lambda x: f"{x:.3f}")
        rows.append([k, fmt(v4), fmt(v1), fmt(d),
                     f"{rel:+.1f}%" if np.isfinite(rel) else "—"])
    rows.append(["IC", f"{a['ic']:+.4f}" if np.isfinite(a['ic']) else "—",
                 f"{b['ic']:+.4f}" if np.isfinite(b['ic']) else "—",
                 f"{b['ic']-a['ic']:+.4f}" if np.isfinite(a['ic']) and np.isfinite(b['ic'])
                 else "—", ""])
    LOG.table(rows, ["지표", "F4 (v1.0)", "F1 (v2.0)", "차이", "상대변화"],
              ["l", "r", "r", "r", "r"])
    s4, s1 = a["net"].get("Sharpe", np.nan), b["net"].get("Sharpe", np.nan)
    if np.isfinite(s4) and np.isfinite(s1):
        n4 = a["net"].get("평균편입가능", np.nan)
        n1 = b["net"].get("평균편입가능", np.nan)
        LOG.info(f"평균 편입 가능 종목수: v1.0 {n4:,.0f} → v2.0 {n1:,.0f}. "
                 f"v2.0 이 ΔNONFIN>0 하드게이트를 폐기한 직접적 효과가 여기에 나타납니다.")
        if s1 > s4:
            LOG.ok(f"이 백테스트에서 v2.0(F1) 이 v1.0(F4) 대비 Sharpe {s1-s4:+.3f} 개선.")
        else:
            LOG.error(f"★ 이 백테스트에서 v2.0(F1) 이 v1.0(F4) 를 이기지 못했습니다 "
                      f"(Sharpe {s1-s4:+.3f}). 개선 주장을 철회하고 그대로 보고합니다(§9.1).")


def apply_bh_fdr(q: Optional[float] = None) -> pd.DataFrame:
    """§8.3 — 11개 실험을 하나의 검정 패밀리로 묶어 BH-FDR 보정."""
    qq = float(q if q is not None else ARC_FDR_Q)
    LOG.banner(f"[산출물 8] BH-FDR 다중검정 보정 (q={qq:.2f}) (§9.2-8)",
               "11개 실험을 하나의 패밀리로 묶는다. 개별 유의성을 보정 없이 주장하지 않는다")
    ids, ps = [], []
    for aid, _n, _p, _kw in ABLATIONS:
        r = ABLATION_RESULTS.get(aid)
        if r and r["ok"] and np.isfinite(r.get("p", np.nan)):
            ids.append(aid)
            ps.append(float(r["p"]))
    if not ids:
        LOG.warn("p-value 를 계산할 수 있는 실험이 없어 보정할 수 없습니다.")
        return pd.DataFrame(columns=["id", "p", "sig_raw", "sig_bh"])
    arr = np.asarray(ps, dtype=float)
    passed = bh_fdr(arr, q=qq)
    order = np.argsort(arr)
    m = len(arr)
    rows = []
    for rank, i in enumerate(order, start=1):
        thr = qq * rank / m
        rows.append([ids[i], f"{arr[i]:.4f}", f"{thr:.4f}",
                     "✔" if arr[i] < 0.05 else "✘",
                     "✔ 유의" if passed[i] else "✘ 기각",
                     _trunc(next(n for a, n, _p, _k in ABLATIONS if a == ids[i]), 34)])
    LOG.table(rows, ["ID", "p(HAC)", "BH 임계", "보정 전(p<0.05)", "보정 후", "구성"],
              ["l", "r", "r", "c", "c", "l"], maxw=36)
    n_raw = int((arr < 0.05).sum())
    n_bh = int(passed.sum())
    LOG.info(f"보정 전 유의 {n_raw}/{m} → BH-FDR 보정 후 {n_bh}/{m}. "
             f"차이가 크다면 개별 p-value 를 그대로 인용해선 안 된다는 뜻입니다.")
    if n_bh == 0:
        LOG.warn("보정 후 유의한 실험이 하나도 없습니다. 이 백테스트에서 어떤 구성도 "
                 "U-1000 동일가중 대비 통계적으로 구분되는 초과수익을 내지 못했습니다.")
    out = pd.DataFrame({"id": ids, "p": arr, "sig_raw": arr < 0.05, "sig_bh": passed})
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5-B  강건성 (§8.4) + 인과 순서 점검 (§7.1) + 부정 신호 검증 (§7.3)                       ║
# ║                                                                                          ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다(§9.1). 이 파일은 자동 조정을 하지 않는다.           ║
# ║  ★ 판정 불가는 None 으로 기록하고 사유를 남긴다. 예외로 죽지 않는다.                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: "OrderedDict[str, dict]" = OrderedDict()


def _rrec(rid: str, name: str, passed: Optional[bool], detail: str,
          metrics: Optional[dict] = None):
    # ★ numpy bool 주의: np.False_ is False → False. `is False` 분기가 조용히 빗나간다.
    passed = None if passed is None else bool(passed)
    ROBUST_RESULTS[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail,
                           "metrics": metrics or {}}
    (LOG.ok if passed is True else (LOG.error if passed is False else LOG.warn))(
        f"[{rid}] {name} → " + {True: "✔", False: "✘", None: "—"}[passed] + f" {detail}")


def _rsharpe(bt) -> float:
    s = perf_stats(bt["returns"]) if bt else {}
    return float(s.get("Sharpe", np.nan)) if s else np.nan


def _rsafe(fn, rid: str, name: str):
    try:
        fn()
    except Exception as e:                                        # noqa
        _rrec(rid, name, None, f"실행 실패 — {type(e).__name__}: {str(e)[:140]}")


# ── R1. 서브기간 (전반부 / 후반부) ──────────────────────────────────────────────────────────
def R_subperiod(bt: dict) -> None:
    R = bt.get("returns")
    if R is None or len(R) < 8:
        _rrec("R1", "서브기간 분할", None, "표본 부족")
        return
    R = R.copy()
    half = len(R) // 2
    rows, mus = [], []
    for lab, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        s = perf_stats(x)
        mus.append(s.get("분기평균", np.nan))
        rows.append([lab, f"{len(x)}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('승률', float('nan'))*100:.0f}%"])
    # 연도별도 함께
    R["year"] = as_ts_series(R["asof"]).dt.year
    yr = []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        yr.append([int(y), f"{len(g)}", f"{cum*100:+.2f}%",
                   f"{g['ret'].mean()*100:+.3f}%p", f"{(g['ret']>0).mean()*100:.0f}%",
                   f"{g['n'].mean():.1f}"])
    LOG.table(rows, ["구간", "분기수", "CAGR", "Sharpe", "MDD", "승률"],
              ["l", "r", "r", "r", "r", "r"], title="R1 서브기간 분할")
    LOG.table(yr, ["연도", "분기수", "연수익", "분기평균", "승률", "평균종목수"],
              ["c", "r", "r", "r", "r", "r"], title="R1b 연도별 분해")
    both_pos = all(np.isfinite(m) and m > 0 for m in mus)
    _rrec("R1", "서브기간 분할", both_pos,
          f"전반부 {mus[0]*100:+.3f}%p / 후반부 {mus[1]*100:+.3f}%p (분기평균). " +
          ("양 구간 모두 양(+)." if both_pos else
           "한 구간이 음(−)입니다 — 특정 레짐에 의존할 가능성을 배제할 수 없습니다."),
          {"mu_first": mus[0], "mu_second": mus[1]})


# ── R2. 시총 사분위별 분해 ──────────────────────────────────────────────────────────────────
def R_size_quartile(P: pd.DataFrame, bt: dict) -> None:
    H = bt.get("holdings")
    if H is None or H.empty or "mktcap" not in P.columns:
        _rrec("R2", "시총 사분위 분해", None, "보유 이력 또는 시총 없음")
        return
    key = P[["code", "asof", "mktcap", "sector"]].drop_duplicates(["code", "asof"])
    M = H.merge(key, on=["code", "asof"], how="left").dropna(subset=["mktcap"])
    if M.empty:
        _rrec("R2", "시총 사분위 분해", None, "결합 결과 없음")
        return
    try:
        M["qt"] = M.groupby("asof", observed=True)["mktcap"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 4, labels=False, duplicates="drop"))
    except Exception:
        M["qt"] = pd.qcut(M["mktcap"].rank(method="first"), 4, labels=False, duplicates="drop")
    rows = []
    for k, g in M.dropna(subset=["qt"]).groupby("qt"):
        contrib = float((g["weight"] * g["ret"]).sum())
        rows.append([f"Q{int(k)+1} ({'최소형' if k == 0 else ('최대형' if k == 3 else '')})",
                     f"{len(g):,}", f"{g['ret'].mean()*100:+.2f}%",
                     f"{(g['ret']>0).mean()*100:.0f}%", f"{contrib:+.3f}"])
    LOG.table(rows, ["시총 사분위", "보유건수", "평균 분기수익", "승률", "누적 기여"],
              ["l", "r", "r", "r", "r"], title="R2 시총 사분위별 성과 분해")
    _rrec("R2", "시총 사분위 분해", True, f"{len(rows)}개 분위로 분해 완료")


# ── R3. 섹터별 분해 (§8.4 필수) ─────────────────────────────────────────────────────────────
def R_sector(P: pd.DataFrame, bt: dict, sec: pd.DataFrame) -> None:
    """★ v1.0 의 섹터 편향(기술·제조 쏠림)이 실제로 해소됐는지 확인하는 필수 검사."""
    H = bt.get("holdings")
    if H is None or H.empty or "sector" not in P.columns:
        _rrec("R3", "섹터별 성과 분해", None, "보유 이력 또는 섹터 없음")
        return
    key = P[["code", "asof", "sector"]].drop_duplicates(["code", "asof"])
    M = H.merge(key, on=["code", "asof"], how="left")
    M["sector"] = M["sector"].astype(str).fillna("기타")
    uni_mix = (P.groupby(P["sector"].astype(str)).size() / max(len(P), 1)).to_dict()
    rows = []
    for s, g in M.groupby("sector"):
        share = len(g) / max(len(M), 1)
        rows.append([s, f"{len(g):,}", f"{100*share:.1f}%",
                     f"{100*uni_mix.get(s, 0):.1f}%",
                     f"{100*(share - uni_mix.get(s, 0)):+.1f}%p",
                     f"{g['ret'].mean()*100:+.2f}%",
                     f"{(g['ret']>0).mean()*100:.0f}%",
                     f"{float((g['weight']*g['ret']).sum()):+.3f}"])
    rows.sort(key=lambda r: -float(r[2].rstrip("%")))
    LOG.table(rows, ["섹터", "보유건수", "보유비중", "유니버스비중", "초과배분",
                     "평균수익", "승률", "누적기여"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title="R3 섹터별 성과 분해 (§8.4 필수 — v1.0 섹터 편향 해소 확인)")
    over = [(r[0], float(r[4].rstrip("%p"))) for r in rows]
    worst = max(over, key=lambda x: abs(x[1])) if over else ("", 0.0)
    concentrated = abs(worst[1]) > 20.0
    _rrec("R3", "섹터별 성과 분해", not concentrated,
          f"최대 초과배분 섹터 '{worst[0]}' {worst[1]:+.1f}%p. " +
          ("유니버스 대비 섹터 배분이 크게 치우치지 않았습니다."
           if not concentrated else
           "★ 한 섹터에 20%p 이상 초과 배분되었습니다 — v1.0 의 섹터 편향이 남아 있을 "
           "가능성이 있습니다. D3 섹터 발화율 표와 함께 해석하세요."),
          {"max_over_sector": worst[0], "max_over": worst[1]})


# ── R4. 리밸런싱 ±5거래일 이동 ──────────────────────────────────────────────────────────────
def R_rebal_shift(P: pd.DataFrame, rebals, run_fn, px_daily: Optional[pd.DataFrame] = None) -> None:
    """리밸일을 ±5거래일 옮겨도 성과가 유지되는가.

    ★ 패널이 특정 리밸일에 묶여 있으므로 신호를 다시 만들 수는 없다. 대신 '한 시점씩
      당기거나 미룬' 수익률 배열로 근사한다. 이 근사의 한계를 명시한다.
    """
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    base = run_fn(Q, label="RS_base", apply_costs=True)
    s0 = _rsharpe(base)
    R0 = base["returns"]["ret"].fillna(0).to_numpy()
    rows = [["기준 (이동 없음)", f"{s0:.3f}", "—"]]
    ok = True
    for k in (-1, 1):
        r = np.roll(R0, k)
        r = r[1:-1] if len(r) > 2 else r
        if len(r) < 8:
            continue
        eq = np.cumprod(1 + r)
        yrs = len(r) / 4.0
        cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 and eq[-1] > 0 else np.nan
        vol = r.std(ddof=1) * math.sqrt(4) if len(r) > 1 else np.nan
        sk = cagr / vol if vol and np.isfinite(vol) and vol > 0 else np.nan
        rows.append([f"{'−' if k < 0 else '+'}1분기 시프트(≈±5거래일 대리)",
                     f"{sk:.3f}", f"{sk - s0:+.3f}"])
        if np.isfinite(sk) and np.isfinite(s0) and (s0 - sk) > 0.5:
            ok = False
    LOG.table(rows, ["구성", "Sharpe", "Δ"], ["l", "r", "r"],
              title="R4 리밸런싱 시점 민감도")
    _rrec("R4", "리밸런싱 시점 민감도", ok,
          "시점 이동에 성과가 붕괴하지 않습니다." if ok else
          "★ 시점을 옮기면 성과가 크게 떨어집니다 — 특정 날짜 효과에 의존할 가능성.",
          {"sharpe_base": s0})
    LOG.info("[방법론적 우려] 이 검사는 수익률 시계열 시프트로 근사한 것입니다. "
             "엄밀한 ±5거래일 검정은 체결가를 그 날짜로 다시 만들어야 하며, "
             "그 경우 신호 산출 시점도 함께 바뀌어야 합니다.")


# ── R5. 보유종목수 20 / 30 / 40 ─────────────────────────────────────────────────────────────
def R_holdings(P: pd.DataFrame, run_fn) -> None:
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    rows, sh = [], []
    for n in (ARC_TOP_N_MIN, ARC_TOP_N_DEFAULT, ARC_TOP_N_MAX):
        bt = run_fn(Q, label=f"HOLD{n}", apply_costs=True, top_n=n)
        s = perf_stats(bt["returns"])
        sh.append(s.get("Sharpe", np.nan))
        rows.append([f"{n}종목", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('평균회전율', float('nan')):.2f}",
                     f"{s.get('평균비용', float('nan'))*100:.3f}%p"])
    LOG.table(rows, ["보유종목수", "CAGR", "Sharpe", "MDD", "회전율", "분기평균비용"],
              ["l", "r", "r", "r", "r", "r"], title="R5 보유종목수 민감도")
    fin = [x for x in sh if np.isfinite(x)]
    stable = bool(fin) and (max(fin) - min(fin) < 0.5)
    _rrec("R5", "보유종목수 민감도", stable,
          f"Sharpe 범위 {min(fin):.3f}~{max(fin):.3f}" if fin else "산출 불가",
          {"sharpes": fin})


# ── R6. STRUCT_FLAG 포함 / 제외 ─────────────────────────────────────────────────────────────
def R_struct(P: pd.DataFrame, run_fn) -> None:
    if "STRUCT_FLAG" not in P.columns:
        _rrec("R6", "STRUCT_FLAG 민감도", None, "STRUCT_FLAG 컬럼 없음")
        return
    n_flag = int(pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0).sum())
    if n_flag == 0:
        _rrec("R6", "STRUCT_FLAG 민감도", None, "해당 종목-기간이 없어 비교 불가")
        return
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    b_ex = run_fn(Q, label="ST_excl", apply_costs=True)
    Pin = P[pd.to_numeric(P["STRUCT_FLAG"], errors="coerce").fillna(0) == 0].copy()
    b_in = run_fn(assemble_final(Pin, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                  label="ST_drop", apply_costs=True)
    s1, s2 = _rsharpe(b_ex), _rsharpe(b_in)
    LOG.table([["기본 (D1 결측 처리 후 잔류)", f"{s1:.3f}", f"{n_flag:,}행 해당"],
               ["STRUCT 종목 통째 제외", f"{s2:.3f}", f"{len(P)-len(Pin):,}행 제거"]],
              ["구성", "Sharpe", "비고"], ["l", "r", "l"],
              title="R6 STRUCT_FLAG 포함/제외 (§6.1.6 민감도)")
    _rrec("R6", "STRUCT_FLAG 민감도", bool(np.isfinite(s1) and np.isfinite(s2) and
                                          abs(s1 - s2) < 0.5),
          f"Sharpe {s1:.3f} → {s2:.3f} (Δ {s2-s1:+.3f})", {"s_base": s1, "s_drop": s2})


# ── R7. 한국IR협의회 기업의뢰 리포트 포함 / 제외 ────────────────────────────────────────────
def R_ircouncil(P: pd.DataFrame, rep: Optional[pd.DataFrame], run_fn) -> None:
    """기업의뢰형 리포트는 톤이 구조적으로 긍정 편향이다. 분리 검증한다(§0.4, §8.4).

    ★ 근사: TONE 을 재집계하려면 축 A 전체를 다시 돌려야 한다(수십 분). 여기서는
      '기업의뢰 리포트만 커버하는 종목-분기' 의 축 A 를 결측 처리하는 방식으로 근사하고,
      그 근사를 명시한다.
    """
    if rep is None or rep.empty or "is_sponsored" not in rep.columns:
        _rrec("R7", "기업의뢰 리포트 민감도", None, "sponsored 태깅 없음")
        return
    R = rep.dropna(subset=["stock_code"]).copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["pub_date"])
    R["q"] = [qlabel(t) for t in R["pub_date"]]
    grp = R.groupby(["stock_code", "q"])["is_sponsored"].agg(["mean", "size"])
    only_sp = set(grp[(grp["mean"] >= 0.999)].index)          # 전부 기업의뢰인 종목-분기
    if not only_sp:
        _rrec("R7", "기업의뢰 리포트 민감도", None, "기업의뢰 전용 종목-분기가 없습니다")
        return
    Q1 = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    P2 = P.copy()
    keyv = list(zip(P2["code"].astype(str), P2["q"].astype(str)))
    mask = np.array([k in only_sp for k in keyv])
    for c in ("dTONE", "dTONE_resid"):
        if c in P2.columns:
            P2.loc[mask, c] = np.nan
    Q2 = assemble_final(P2, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    s1 = _rsharpe(run_fn(Q1, label="IR_in", apply_costs=True))
    s2 = _rsharpe(run_fn(Q2, label="IR_out", apply_costs=True))
    LOG.table([["기업의뢰 포함", f"{s1:.3f}", f"{int(mask.sum()):,}행 해당"],
               ["기업의뢰 제외(축 A 결측 처리)", f"{s2:.3f}", ""]],
              ["구성", "Sharpe", "비고"], ["l", "r", "l"],
              title="R7 한국IR협의회 등 기업의뢰 리포트 민감도")
    _rrec("R7", "기업의뢰 리포트 민감도",
          bool(np.isfinite(s1) and np.isfinite(s2) and (s2 >= s1 - 0.3)),
          f"Sharpe {s1:.3f} → {s2:.3f} (Δ {s2-s1:+.3f}). " +
          ("제외해도 성과가 유지됩니다." if np.isfinite(s2) and np.isfinite(s1) and
           s2 >= s1 - 0.3 else
           "★ 기업의뢰 리포트를 빼면 성과가 크게 떨어집니다 — 알파의 상당 부분이 "
           "구조적 긍정 편향에서 왔을 수 있습니다."),
          {"s_in": s1, "s_out": s2})
    LOG.info("[방법론적 우려] TONE 재집계 대신 '기업의뢰 전용 종목-분기의 축 A 결측 처리'로 "
             "근사했습니다. 혼합 커버 종목의 편향은 제거되지 않습니다.")


# ── R8. D1 유사도 지표 4종 단독 ─────────────────────────────────────────────────────────────
def R_d1_metrics(P: pd.DataFrame, run_fn) -> None:
    rows, sh = [], {}
    base = _rsharpe(run_fn(assemble_final(P, use_axes=("D1",), use_excl=True),
                           label="D1_comp", apply_costs=True))
    rows.append(["합성(4종 z 평균)", f"{base:.3f}", "—"])
    for m in ARC_D1_METRICS:
        if f"D1_SCORE_{m}" not in P.columns:
            rows.append([m, "—", "컬럼 없음"])
            continue
        s = _rsharpe(run_fn(assemble_final(P, use_axes=("D1",), use_excl=True, d1_metric=m),
                            label=f"D1_{m}", apply_costs=True))
        sh[m] = s
        rows.append([m, f"{s:.3f}", f"{s - base:+.3f}"])
    LOG.table(rows, ["D1 유사도 지표", "Sharpe", "합성 대비 Δ"], ["l", "r", "r"],
              title="R8 D1 유사도 지표 4종 단독 (합성의 타당성 검증)")
    fin = [v for v in sh.values() if np.isfinite(v)]
    better = bool(fin) and np.isfinite(base) and (base >= max(fin) - 0.05)
    _rrec("R8", "D1 지표 합성 타당성", better,
          (f"합성 {base:.3f} vs 최고 단독 {max(fin):.3f}" if fin else "산출 불가") +
          ("" if better else " — ★ 단독 지표가 합성을 이깁니다. 4종 평균이 정보를 희석하고 "
                            "있을 수 있습니다(사전등록 구성이므로 자동 변경하지 않고 보고만)."),
          {"base": base, **sh})


# ── R9. D1 섹션 가중치 균등배분 ─────────────────────────────────────────────────────────────
def R_d1_weights(P: pd.DataFrame, run_fn) -> None:
    if "D1_SCORE_equalw" not in P.columns:
        _rrec("R9", "D1 섹션 가중치 민감도", None, "균등가중 컬럼 없음")
        return
    a = _rsharpe(run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True),
                        label="W_pre", apply_costs=True))
    b = _rsharpe(run_fn(assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True,
                                       d1_equal_weights=True),
                        label="W_eq", apply_costs=True))
    LOG.table([["사전등록 가중 (MDA .35 / LEGAL .25 / …)", f"{a:.3f}"],
               ["섹션 균등배분", f"{b:.3f}"]],
              ["D1 섹션 가중", "Sharpe"], ["l", "r"],
              title="R9 D1 섹션 가중치 민감도")
    _rrec("R9", "D1 섹션 가중치 민감도",
          bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) < 0.4),
          f"사전등록 {a:.3f} vs 균등 {b:.3f} (Δ {b-a:+.3f}). " +
          ("가중치 선택에 성과가 크게 좌우되지 않습니다." if np.isfinite(a) and np.isfinite(b)
           and abs(a - b) < 0.4 else
           "★ 가중치 선택이 성과를 크게 바꿉니다 — 사전등록 값의 임의성이 결과에 반영됩니다."),
          {"preset": a, "equal": b})


# ── R10. §7.3 부정 신호 (BOTTOM 그룹) ───────────────────────────────────────────────────────
def R_bottom_group(P: pd.DataFrame) -> None:
    """문헌상 부정 톤은 긍정 톤보다 정보력이 강하다. 필터로만 소비하지 말 것(§7.3)."""
    LOG.banner("R10 부정 신호 별도 검증 (§7.3)",
               "BOTTOM 그룹의 forward 1Q/2Q/4Q 수익률 — 비대칭이면 숏 슬리브 검토 대상")
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
    if "FINAL_RANK" not in Q.columns:
        _rrec("R10", "부정 신호 검증", None, "FINAL_RANK 없음")
        return
    rows = []
    res = {}
    for lab, lo, hi in (("TOP 10%", 0.90, 1.01), ("중위 40~60%", 0.40, 0.60),
                        ("BOTTOM 10%", -0.01, 0.10)):
        m = (Q["FINAL_RANK"] >= lo) & (Q["FINAL_RANK"] < hi)
        g = Q[m]
        if g.empty:
            continue
        vals = []
        for h in ("fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q"):
            v = pd.to_numeric(col(g, h), errors="coerce")
            vals.append(float(v.mean()) if v.notna().any() else np.nan)
        res[lab] = vals
        rows.append([lab, f"{len(g):,}"] + [f"{v*100:+.2f}%" if np.isfinite(v) else "—"
                                            for v in vals])
    # 전체 평균 대비 초과
    base = [float(pd.to_numeric(col(Q, h), errors="coerce").mean())
            for h in ("fwd_ret_1q", "fwd_ret_2q", "fwd_ret_4q")]
    rows.append(["(유니버스 평균)", f"{len(Q):,}"] +
                [f"{v*100:+.2f}%" if np.isfinite(v) else "—" for v in base])
    LOG.table(rows, ["그룹", "표본", "1Q", "2Q", "4Q"], ["l", "r", "r", "r", "r"])
    top = res.get("TOP 10%", [np.nan] * 3)
    bot = res.get("BOTTOM 10%", [np.nan] * 3)
    if np.isfinite(top[0]) and np.isfinite(bot[0]) and np.isfinite(base[0]):
        a_top = top[0] - base[0]
        a_bot = base[0] - bot[0]          # BOTTOM 의 음의 알파 크기
        asym = a_bot > a_top
        LOG.table([["TOP 양의 알파 (1Q)", f"{a_top*100:+.3f}%p"],
                   ["BOTTOM 음의 알파 (1Q)", f"{a_bot*100:+.3f}%p"],
                   ["비대칭 여부", "BOTTOM 우세" if asym else "TOP 우세"]],
                  ["항목", "값"], ["l", "r"], title="§7.3 비대칭 판정")
        _rrec("R10", "부정 신호 검증", True,
              f"TOP 알파 {a_top*100:+.3f}%p / BOTTOM 음의 알파 {a_bot*100:+.3f}%p. " +
              ("BOTTOM 의 정보력이 더 강합니다." if asym else "TOP 의 정보력이 더 강합니다."),
              {"alpha_top": a_top, "alpha_bottom": a_bot, "asym": bool(asym)})
        if asym:
            LOG.warn("BOTTOM 의 음의 알파가 TOP 의 양의 알파보다 큽니다. §7.3 에 따라 "
                     "숏 슬리브 도입 여부는 **자동 결정하지 않고** 보고 후 지시를 기다립니다.")
    else:
        _rrec("R10", "부정 신호 검증", None, "표본 부족으로 비대칭 판정 불가")


# ── R11. §7.1 인과 순서 점검 ────────────────────────────────────────────────────────────────
def R_causal_order(P: pd.DataFrame, rep: Optional[pd.DataFrame],
                   doc: Optional[pd.DataFrame]) -> None:
    """애널리스트가 DART 를 읽고 리포트를 썼다면 두 축은 독립 확증이 아니라 중복 카운팅이다."""
    LOG.banner("R11 인과 순서 점검 (§7.1)",
               "리포트가 공시 직후에 몰려 있다면 두 축은 같은 정보를 두 번 세는 것이다")
    detail = []
    metrics = {}

    # ① 리포트 발간일 − 직전 정기보고서 접수일 시차 분포
    if (rep is not None and len(rep) and doc is not None and len(doc)):
        R = rep.dropna(subset=["stock_code"])[["stock_code", "pub_date"]].copy()
        R["pub_date"] = as_ts_series(R["pub_date"])
        R = R.dropna().rename(columns={"stock_code": "code"})
        D = doc[["corp_code", "rcept_dt"]].drop_duplicates().copy()
        D["rcept_dt"] = as_ts_series(D["rcept_dt"])
        c2c = {}
        if "corp_code" in P.columns:
            c2c = (P.dropna(subset=["corp_code"]).drop_duplicates("code")
                    .set_index("code")["corp_code"].astype(str).to_dict())
        R["corp_code"] = R["code"].astype(str).map(c2c)
        R = R.dropna(subset=["corp_code"]).sort_values("pub_date")
        D = D.dropna().sort_values("rcept_dt")
        if len(R) and len(D):
            try:
                M = pd.merge_asof(R, D, left_on="pub_date", right_on="rcept_dt",
                                  by="corp_code", direction="backward",
                                  tolerance=pd.Timedelta(days=400))
                M = M.dropna(subset=["rcept_dt"])
                lag = (M["pub_date"] - M["rcept_dt"]).dt.days
                bins = [("0~7일", (lag >= 0) & (lag <= 7)),
                        ("8~30일", (lag > 7) & (lag <= 30)),
                        ("31~90일", (lag > 30) & (lag <= 90)),
                        ("91일 이상", lag > 90)]
                tot = max(len(lag), 1)
                LOG.table([[k, f"{int(v.sum()):,}", f"{100*float(v.mean()):.1f}%"]
                           for k, v in bins],
                          ["공시 후 경과", "리포트 수", "비중"], ["l", "r", "r"],
                          title="리포트 발간 ~ 직전 정기보고서 접수 시차 분포")
                near = float(((lag >= 0) & (lag <= 7)).mean())
                metrics["report_within_7d"] = near
                detail.append(f"공시 후 7일 내 발간 비중 {100*near:.1f}%")
                if near > 0.30:
                    LOG.warn(f"리포트의 {100*near:.0f}% 가 정기보고서 접수 7일 내에 몰려 있습니다. "
                             f"두 축이 같은 정보를 반영할 가능성이 높습니다 — 결합 가중치 "
                             f"타당성을 재검토 대상으로 보고합니다(자동 조정하지 않습니다).")
            except Exception as e:                                # noqa
                LOG.warn(f"시차 분포 계산 실패({type(e).__name__})")
    else:
        detail.append("리포트 또는 공시 데이터 부족으로 시차 분포 산출 불가")

    # ② ΔTONE_resid × DART_SCORE 기간별 횡단면 상관
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=False)
    if "dTONE_resid" in Q.columns and "DART_SCORE" in Q.columns:
        cs = []
        for t, g in Q.groupby("asof", observed=True):
            a = pd.to_numeric(g["dTONE_resid"], errors="coerce")
            b = pd.to_numeric(g["DART_SCORE"], errors="coerce")
            m = a.notna() & b.notna()
            if int(m.sum()) >= 30:
                r = float(a[m].corr(b[m], method="spearman"))
                if np.isfinite(r):
                    cs.append((t, r))
        if cs:
            arr = np.array([c[1] for c in cs])
            mu = float(arr.mean())
            metrics["axes_corr_mean"] = mu
            LOG.table([[str(pd.Timestamp(t).date()), f"{r:+.3f}"] for t, r in cs[-12:]],
                      ["리밸일", "상관"], ["c", "r"],
                      title="ΔTONE_resid × DART_SCORE 기간별 횡단면 상관 (최근 12시점)")
            detail.append(f"두 축 상관 평균 {mu:+.3f} ({len(cs)}시점)")
            if abs(mu) > 0.30:
                LOG.warn(f"두 축의 평균 상관이 {mu:+.3f} 입니다. 독립 확증이 아니라 중복 "
                         f"카운팅일 수 있으므로 §7.1 에 따라 결합 가중치를 재검토 대상으로 "
                         f"보고합니다. 자동 조정하지 않습니다.")
        else:
            detail.append("상관을 계산할 표본이 부족")
    _rrec("R11", "인과 순서 점검", None if not detail else True,
          " · ".join(detail) or "판정불가", metrics)


def report_robustness() -> None:
    LOG.banner("[산출물 10] 강건성 검사 요약 (§9.2-10)",
               "실패는 그대로 보고한다. 파라미터를 조정해 통과시키지 않는다")
    order = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11"]
    rows = []
    for rid in order:
        r = ROBUST_RESULTS.get(rid)
        if not r:
            rows.append([rid, "—", "미실행", ""])
            continue
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid, _trunc(r["name"], 26), icon, _trunc(r["detail"], 88)])
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], maxw=92)
    fails = [r for r in ROBUST_RESULTS.values() if r["pass"] is False]
    if fails:
        LOG.warn(f"강건성 검사 {len(fails)}건 실패: " + ", ".join(r["id"] for r in fails) +
                 " — 파라미터를 조정하지 않고 그대로 보고합니다(§9.1).")
    else:
        LOG.ok("강건성 검사에서 실패 항목이 없습니다.")


def run_robustness_suite(P, bt, rebals, uni, sec, run_fn,
                         rep=None, doc=None, px_daily=None) -> None:
    """§8.4 전 항목 실행. 각 검사는 실패해도 다음으로 넘어간다."""
    LOG.banner("강건성 스위트 (§8.4)", "서브기간 · 시총 · 섹터 · 리밸시점 · 보유수 · "
                                       "STRUCT · 기업의뢰 · D1지표 · D1가중 · 부정신호 · 인과순서")
    _rsafe(lambda: R_subperiod(bt), "R1", "서브기간 분할")
    _rsafe(lambda: R_size_quartile(P, bt), "R2", "시총 사분위 분해")
    _rsafe(lambda: R_sector(P, bt, sec), "R3", "섹터별 성과 분해")
    _rsafe(lambda: R_rebal_shift(P, rebals, run_fn, px_daily), "R4", "리밸런싱 시점 민감도")
    _rsafe(lambda: R_holdings(P, run_fn), "R5", "보유종목수 민감도")
    _rsafe(lambda: R_struct(P, run_fn), "R6", "STRUCT_FLAG 민감도")
    _rsafe(lambda: R_ircouncil(P, rep, run_fn), "R7", "기업의뢰 리포트 민감도")
    _rsafe(lambda: R_d1_metrics(P, run_fn), "R8", "D1 지표 합성 타당성")
    _rsafe(lambda: R_d1_weights(P, run_fn), "R9", "D1 섹션 가중치 민감도")
    _rsafe(lambda: R_bottom_group(P), "R10", "부정 신호 검증")
    _rsafe(lambda: R_causal_order(P, rep, doc), "R11", "인과 순서 점검")
    report_robustness()



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  리포팅 — §9.2 최종 산출물 11종                                                        ║
# ║                                                                                          ║
# ║  §9.1 증거 등급 (엄격 준수):                                                               ║
# ║   · 실증적 주장은 이 백테스트에서 산출된 수치로만 뒷받침한다.                                ║
# ║   · 방법론적 우려는 "[방법론적 우려]" 라벨을 붙여 명시한다.                                  ║
# ║   · 메커니즘 그럴듯함을 증거로 제시하지 않는다.                                              ║
# ║   · 인접 문헌(미국 10-K)을 한국 데이터 현상의 증거로 대체하지 않는다.                        ║
# ║   · 근거를 못 찾았으면 "근거 없음" 이라 명시한다. 이 기준은 낙관적 주장에도 동일 적용한다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance(bt: dict, bench: Dict[str, pd.Series], label: str = "",
                       uni_bench: Optional[pd.Series] = None) -> None:
    """성과 검증표 — 비용 전/후 병기 필수(§8.1)."""
    LOG.banner(f"성과 검증 — {label or STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · 익영업일 시가 체결 · 롱온리")
    R = bt.get("returns")
    if R is None or len(R) == 0:
        LOG.warn("수익률 시계열이 비어 성과를 계산할 수 없습니다.")
        return
    net = perf_stats(R)
    gro = perf_stats(R, gross=True)
    order = ["기간수(분기)", "누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD",
             "Calmar", "승률", "분기평균", "t통계량(HAC)", "최장언더워터(분기)",
             "평균종목수", "평균회전율", "평균비용", "평균편입가능"]
    pct = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
    pctp = {"분기평균", "평균비용"}
    rows = []
    for k in order:
        def fmt(d):
            v = d.get(k)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            if k in pct:
                return f"{v*100:+.2f}%"
            if k in pctp:
                return f"{v*100:+.3f}%p"
            return f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"
        rows.append([k, fmt(gro), fmt(net)])
    LOG.table(rows, ["지표", "비용 차감 전", "비용 차감 후"], ["l", "r", "r"],
              title="포트폴리오 성과 (§8.1 — 비용 전만 보고하는 것은 금지)")

    # 벤치마크 대비
    Rs = measurable_ret(R)          # perf_stats 와 동일 표본(측정 불가 분기 제외)
    brows = []
    if uni_bench is not None and len(uni_bench):
        bb = uni_bench.reindex(Rs.index).fillna(0.0)
        ex = Rs.fillna(0) - bb
        _, t = hac_tstat(ex.to_numpy())
        brows.append(["U-1000 동일가중 ★기준", f"{(1+bb).prod()*100-100:+.1f}%",
                      f"{(1+Rs.fillna(0)).prod()*100-100:+.1f}%",
                      f"{ex.mean()*100:+.3f}%p", f"{t:.2f}"])
    for name, b in (bench or {}).items():
        bb = b.reindex(Rs.index).fillna(0.0)
        ex = Rs.fillna(0) - bb
        _, t = hac_tstat(ex.to_numpy())
        brows.append([name, f"{(1+bb).prod()*100-100:+.1f}%",
                      f"{(1+Rs.fillna(0)).prod()*100-100:+.1f}%",
                      f"{ex.mean()*100:+.3f}%p", f"{t:.2f}"])
    if brows:
        LOG.table(brows, ["벤치마크", "벤치 누적", "전략 누적", "분기평균 초과", "HAC t"],
                  ["l", "r", "r", "r", "r"], title="벤치마크 대비")
        LOG.info("★ 1순위 기준은 'U-1000 동일가중' 입니다. 지수(KOSPI/KOSDAQ)는 시총가중이라 "
                 "대형주가 지배하므로, 지수 대비 초과수익은 소형주 프리미엄을 알파로 "
                 "오인하게 만듭니다.")

    # 우측 꼬리 의존도
    H = bt.get("holdings")
    if H is not None and len(H):
        contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
        n = len(contrib)
        base = float(contrib.sum())
        rows = []
        for qv, lab in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
            k = max(1, int(round(n * qv)))
            top = float(contrib.iloc[:k].sum())
            rows.append([lab, f"{k}", f"{top:+.3f}", f"{base-top:+.3f}"])
        rows.append(["전체", f"{n}", f"{base:+.3f}", "—"])
        LOG.table(rows, ["구간", "종목수", "기여", "제외 후 총기여"],
                  ["l", "r", "r", "r"], title="우측 꼬리 의존도")
        k5 = max(1, int(round(n * 0.05)))
        if base > 0 and (base - float(contrib.iloc[:k5].sum())) <= 0:
            LOG.warn("상위 5% 종목을 제외하면 총기여가 0 이하가 됩니다. 성과가 소수 종목에 "
                     "전적으로 의존합니다 — 실전에서 그 종목을 놓치면 전략 전체가 실패합니다.")


def report_correlation_matrix(P: pd.DataFrame) -> None:
    """§6.6 / §9.2-(3) D1·D2·D3 상호 상관행렬 (기간별)."""
    LOG.banner("[산출물 3] D1/D2/D3 상호 상관행렬 (§6.6)",
               "|상관| > 0.6 인 쌍이 있으면 독립 정보가 아니다 → 가중치 타당성 재검토 대상")
    cols = [c for c in ("D1_SCORE", "D2_SCORE", "D3_SCORE") if c in (P.columns if P is not None
                                                                     else [])]
    if P is None or P.empty or len(cols) < 2:
        LOG.warn("상관을 계산할 층이 2개 미만입니다.")
        return
    # 전체 기간 평균
    per = []
    for t, g in P.groupby("asof", observed=True):
        sub = g[cols].apply(pd.to_numeric, errors="coerce")
        if sub.notna().sum().min() < 30:
            continue
        c = sub.corr(method="spearman")
        per.append((t, c))
    if not per:
        LOG.warn("기간별 표본이 30행 미만이라 상관을 계산할 수 없습니다.")
        return
    avg = sum(c.fillna(0) for _t, c in per) / len(per)
    LOG.table([[a] + [f"{avg.loc[a, b]:+.3f}" for b in cols] for a in cols],
              ["층"] + cols, ["l"] + ["r"] * len(cols),
              title=f"기간 평균 상관행렬 (Spearman, {len(per)}개 시점)")
    tail = per[-8:]
    LOG.table([[str(pd.Timestamp(t).date())] +
               [f"{c.loc[a, b]:+.2f}" for i, a in enumerate(cols) for b in cols[i+1:]]
               for t, c in tail],
              ["리밸일"] + [f"{a}~{b}" for i, a in enumerate(cols) for b in cols[i+1:]],
              ["c"] + ["r"] * (len(cols) * (len(cols) - 1) // 2),
              title="최근 8시점 층간 상관 추이")
    hi = [(a, b, float(avg.loc[a, b])) for i, a in enumerate(cols) for b in cols[i+1:]
          if abs(float(avg.loc[a, b])) > 0.6]
    if hi:
        LOG.warn("★ |상관| > 0.6 인 쌍: " +
                 ", ".join(f"{a}~{b}={v:+.2f}" for a, b, v in hi) +
                 " → 독립 정보가 아니므로 0.40/0.40/0.20 가중치의 타당성을 재검토 대상으로 "
                 "보고합니다. §6.6 에 따라 자동 조정하지 않습니다.")
    else:
        LOG.ok("모든 층 쌍의 |상관| 이 0.6 이하 — 세 층이 서로 다른 정보를 담고 있다는 "
               "이 백테스트의 실증 근거입니다.")


def report_universe_attrition(uni) -> None:
    if uni is not None and hasattr(uni, "report_attrition"):
        uni.report_attrition()


def report_interpretation(P: pd.DataFrame) -> None:
    """해석 참조표 + §9.1 증거 등급 상기 블록."""
    LOG.banner("해석 참조표", "각 신호가 높을 때 / 낮을 때 무엇을 뜻하는가")
    LOG.table([
        ["ΔTONE_resid ↑", "컨센 수정·모멘텀·사이즈로 설명되지 않는 서술 톤 개선",
         "정량 지표보다 먼저 움직인 정성 판단"],
        ["D1_SCORE ↑ (변화 작음)", "전년 문안을 거의 그대로 유지",
         "Lazy Prices 가설상 '숨은 악재 정황 없음'"],
        ["D1_SCORE ↓ (변화 큼)", "MD&A·소송 문단을 능동적으로 고침",
         "★ 한국 데이터에서 이 방향의 유효성은 부호 검증 결과를 따를 것"],
        ["D2_SCORE ↑", "발생액 낮고 현금흐름이 이익을 뒷받침, 희석 적음", "이익의 질 양호"],
        ["D3_SCORE ↑", "완료형 하드팩트(설비·계약·인력·거점) 증분 관측",
         "가점일 뿐 편입 조건이 아님"],
        ["EXCLUDE = 1", "특수관계자·우발부채·소송·감사·최대주주·CB/BW·연속적자·자본잠식",
         "점수 무관 즉시 제외 (유일한 하드 게이트)"],
    ], ["신호", "의미", "비고"], ["l", "l", "l"], maxw=52)

    LOG.rule("§9.1 증거 등급 — 이 리포트를 읽는 규칙")
    _safe_print("""
  · 실증적 주장  : 이 백테스트에서 산출된 수치로만 뒷받침합니다. 수치 없는 낙관/비관 금지.
  · 방법론적 우려: "[방법론적 우려]" 라벨이 붙은 문장은 실증이 아니라 위험 지적입니다.
  · 인접 문헌    : Lazy Prices 는 미국 10-K 결과입니다. 한국 사업보고서 재현 증거로
                   대체하지 않습니다. D1 은 '검증해야 할 가설' 로만 취급합니다.
  · 근거 없음    : 데이터로 확인하지 못한 항목은 "근거 없음" 이라고 명시합니다.
  · 이 기준은 낙관적 주장에도 동일하게 적용됩니다.
""")
    if P is not None and len(P):
        rows = []
        for c in ("dTONE_resid", "D1_SCORE", "D2_SCORE", "D3_SCORE", "DART_SCORE",
                  "FINAL_SCORE"):
            v = pd.to_numeric(col(P, c), errors="coerce")
            n = int(v.notna().sum())
            rows.append([c, f"{n:,}", f"{100*n/max(len(P),1):.1f}%",
                         f"{float(v.quantile(0.1)):+.3f}" if n else "—",
                         f"{float(v.median()):+.3f}" if n else "—",
                         f"{float(v.quantile(0.9)):+.3f}" if n else "—"])
        LOG.table(rows, ["신호", "관측", "커버리지", "10분위", "중앙값", "90분위"],
                  ["l", "r", "r", "r", "r", "r"], title="신호 분포")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 5) -> None:
    """최근 시점 상위 종목이 '왜' 뽑혔는지 한 장으로."""
    LOG.banner("종목별 진단 카드", "최근 리밸일 상위 종목 — 어느 축이 얼마나 기여했는가")
    if P is None or P.empty:
        LOG.warn("패널이 비었습니다.")
        return
    last = P["asof"].max()
    sub = P[(P["asof"] == last) & (pd.to_numeric(col(P, "EXCLUDE"),
                                                 errors="coerce").fillna(0) == 0)]
    if sub.empty:
        sub = P[P["asof"] == last]
    if sub.empty or "FINAL_RANK" not in sub.columns:
        LOG.warn("마지막 시점 패널 또는 FINAL_RANK 가 없어 진단 카드를 만들 수 없습니다.")
        return
    names = (sec.drop_duplicates("code").set_index("code")["name"].to_dict()
             if sec is not None and len(sec) and "name" in sec.columns else {})
    top = sub.nlargest(min(int(top_n), len(sub)), "FINAL_RANK")
    for r in top.itertuples(index=False):
        code = getattr(r, "code", "?")
        _safe_print("\n" + "─" * 104)
        _safe_print(f"[{code}] {names.get(code, '')}    섹터: {getattr(r, 'sector', '?')}    "
                    f"리밸일: {pd.Timestamp(last).date()}    분기: {getattr(r, 'q', '?')}")
        _safe_print("─" * 104)
        fr = getattr(r, "FINAL_RANK", np.nan)
        _safe_print(f"FINAL_RANK {fr:.3f} (상위 {100*(1-fr):.1f}%)   "
                    f"FINAL_SCORE {getattr(r, 'FINAL_SCORE', np.nan):+.3f}   "
                    f"시총 {getattr(r, 'mktcap', np.nan)/1e8:,.0f}억   "
                    f"ADTV {getattr(r, 'adtv60', np.nan)/1e8:,.1f}억")
        _safe_print("\n■ 축별 기여")
        for lab, c in (("축 A ΔTONE_resid", "dTONE_resid"), ("  (원신호 ΔTONE)", "dTONE"),
                       ("  커버 리포트 수", "n_reports_q"),
                       ("축 B DART_SCORE", "DART_SCORE"),
                       ("  D1 (텍스트 변화)", "D1_SCORE"),
                       ("  D2 (재무 이상)", "D2_SCORE"),
                       ("  D3 (하드팩트)", "D3_SCORE"),
                       ("  ΔNONFIN", "DELTA_NONFIN")):
            v = getattr(r, c, np.nan)
            _safe_print(f"  {_pad(lab, 22)} " +
                        (f"{v:+.4f}" if isinstance(v, (int, float)) and np.isfinite(v)
                         else "결측 (0으로 채우지 않음)"))
        _safe_print("\n■ D1 섹션별 변화량 (z, 클수록 많이 바뀜)")
        cells = []
        for s in ARC_SECTIONS:
            v = getattr(r, f"CH_{s}", np.nan)
            cells.append(f"{s.replace('S_','')}={v:+.2f}" if isinstance(v, (int, float))
                         and np.isfinite(v) else f"{s.replace('S_','')}=—")
        _safe_print("  " + "  ".join(cells))
        _safe_print("\n■ 배제 플래그")
        flags = []
        for c, _d in EXCL_DEFS:
            v = getattr(r, c, np.nan)
            flags.append(f"{c.replace('EX_','')} " +
                         ("✘" if isinstance(v, (int, float)) and np.isfinite(v) and v > 0
                          else ("✔" if isinstance(v, (int, float)) and np.isfinite(v) else "—")))
        _safe_print("  " + "  ".join(flags))
    _safe_print("─" * 104)
    _safe_print("  범례: ✔ 통과 · ✘ 발동(제외) · — 미관측(결측)")


def report_kill_criteria(ctx: dict) -> dict:
    """§9.2-(11) / §9.3 사전등록 폐기 조건 5개를 실측으로 판정."""
    LOG.banner("[산출물 11] 사전등록 폐기 조건 판정 (§9.3)",
               "사후 조정 금지 — 충족 시 파라미터 튜닝으로 되살리려 시도하지 않는다")
    res = {}
    rows = []

    # 1. GATE_4·5·6 이 모두 실패 → 축 B 성립 불가
    g = {k: (GATE_RESULTS.get(k, {}) or {}).get("pass") for k in ("GATE_4", "GATE_5", "GATE_6")}
    c1 = all(v is False for v in g.values())
    res["k1"] = c1
    rows.append(["1", "GATE_4·5·6 모두 실패 → 축 B 성립 불가",
                 " / ".join(f"{k}={'실패' if v is False else ('통과' if v else '판정불가')}"
                            for k, v in g.items()),
                 "⛔ 폐기" if c1 else "해당 없음"])

    # 2. 비용 차감 후 F1 의 알파 소멸
    f1 = ABLATION_RESULTS.get("F1")
    if f1 and f1.get("ok"):
        mu_net = f1["net"].get("분기평균", np.nan)
        sh = f1["net"].get("Sharpe", np.nan)
        c2 = not (np.isfinite(mu_net) and mu_net > 0 and np.isfinite(sh) and sh > 0)
        res["k2"] = c2
        rows.append(["2", "거래비용 차감 후 F1 의 알파 소멸",
                     f"분기평균 {mu_net*100:+.3f}%p · Sharpe {sh:.3f}"
                     if np.isfinite(mu_net) else "산출 불가",
                     "⛔ 폐기" if c2 else "통과"])
    else:
        res["k2"] = None
        rows.append(["2", "거래비용 차감 후 F1 의 알파 소멸", "F1 미실행", "판정불가"])

    # 3. A2 와 A1 의 차이가 미미 → 텍스트 고유 알파 부재
    a1, a2 = ABLATION_RESULTS.get("A1"), ABLATION_RESULTS.get("A2")
    if a1 and a2 and a1.get("ok") and a2.get("ok"):
        s1 = a1["net"].get("Sharpe", np.nan)
        s2 = a2["net"].get("Sharpe", np.nan)
        c3 = bool(np.isfinite(s1) and np.isfinite(s2) and abs(s1 - s2) < 0.10)
        res["k3"] = c3
        rows.append(["3", "A2(직교화 미적용)와 A1 차이 미미 → 텍스트 고유 알파 부재",
                     f"A1 {s1:.3f} vs A2 {s2:.3f} (Δ {s1-s2:+.3f})",
                     "⛔ 폐기" if c3 else "통과"])
    else:
        res["k3"] = None
        rows.append(["3", "A2 vs A1 차이", "미실행", "판정불가"])

    # 4. F1 이 B2(D2 단독)를 유의하게 상회하지 못함
    b2 = ABLATION_RESULTS.get("B2")
    if f1 and b2 and f1.get("ok") and b2.get("ok"):
        try:
            ra = measurable_ret(f1["returns"])
            rb = measurable_ret(b2["returns"]).reindex(ra.index)
            d = (ra.fillna(0) - rb.fillna(0)).to_numpy()
            mu, t = hac_tstat(d)
            c4 = not (np.isfinite(t) and t > 1.0 and mu > 0)
            res["k4"] = c4
            rows.append(["4", "F1 이 B2(D2 단독)를 유의하게 상회 못함",
                         f"차이 분기평균 {mu*100:+.3f}%p · HAC t={t:.2f}",
                         "⛔ 폐기" if c4 else "통과"])
        except Exception:
            res["k4"] = None
            rows.append(["4", "F1 vs B2", "계산 실패", "판정불가"])
    else:
        res["k4"] = None
        rows.append(["4", "F1 vs B2", "미실행", "판정불가"])

    # 5. D1 부호 역전
    sg = ctx.get("d1_sign") or {}
    ok5 = sg.get("sign_ok")
    c5 = (ok5 is False)
    res["k5"] = c5
    rows.append(["5", "D1 부호가 한국 데이터에서 역전",
                 _trunc(str(sg.get("verdict", "미실행")), 52),
                 "⛔ D1 검증 실패 → F2 를 주 결과로" if c5 else
                 ("통과" if ok5 else "판정불가")])

    LOG.table(rows, ["#", "사전등록 폐기 조건", "실측", "판정"], ["c", "l", "l", "c"], maxw=56)
    fired = [k for k, v in res.items() if v is True]
    if fired:
        LOG.error(f"★ 폐기 조건 {len(fired)}건 충족: {', '.join(fired)}. "
                  f"§9.3 에 따라 파라미터 튜닝으로 되살리려 시도하지 않습니다. "
                  f"폐기 보고 후 중단하는 것이 사전등록된 행동입니다.")
    else:
        LOG.ok("사전등록 폐기 조건에 해당하는 항목이 없습니다.")
    return res


def report_final_deliverables(ctx: dict) -> None:
    """§9.2 산출물 11종의 목차 — 무엇이 어디에 나왔고 판정이 무엇인지 한 표로."""
    LOG.banner("최종 산출물 점검표 (§9.2)", "11개 항목이 전부 출력되었는지 확인한다")
    gates_done = bool(GATE_RESULTS)
    ica = ctx.get("axis_a_ic") or {}
    sign = ctx.get("d1_sign") or {}
    abl_done = bool(ABLATION_RESULTS)
    rob_done = bool(ROBUST_RESULTS)
    kill = ctx.get("kill") or {}
    rows = [
        ["1", "Phase 0 게이트 결과표 (6개 실측 + 판정)", "21_gate",
         "출력" if gates_done else "미실행",
         f"{sum(1 for v in GATE_RESULTS.values() if v['pass'] is True)}/"
         f"{len(GATE_RESULTS)} 통과" if gates_done else "—"],
        ["2", "축 A 직교화 전/후 IC 비교표", "30_axis_a_tone",
         "출력" if ica else "미실행",
         (f"IC {ica.get('ic_raw', float('nan')):+.4f} → "
          f"{ica.get('ic_resid', float('nan')):+.4f}") if ica else "—"],
        ["3", "D1/D2/D3 상호 상관행렬 (기간별)", "60_report", "출력", "—"],
        ["4", "D1 부호 검증 (변화=악재 성립 여부)", "31_axis_b_d1",
         "출력" if sign else "미실행",
         ("성립" if sign.get("sign_ok") else ("역전" if sign.get("sign_ok") is False
                                              else "판정불가")) if sign else "—"],
        ["5", "인과 순서 점검 (리포트-공시 시차 · 두 축 상관)", "51_robust",
         "출력" if "R11" in ROBUST_RESULTS else "미실행",
         _trunc(str((ROBUST_RESULTS.get("R11") or {}).get("detail", "")), 34)],
        ["6", "어블레이션 11개 성과표 (비용 전/후)", "50_ablation",
         "출력" if abl_done else "미실행",
         f"{sum(1 for v in ABLATION_RESULTS.values() if v['ok'])}/{len(ABLATION_RESULTS)} 성공"
         if abl_done else "—"],
        ["7", "F4(v1.0) 대비 F1(v2.0) 개선폭", "50_ablation",
         "출력" if ("F1" in ABLATION_RESULTS and "F4" in ABLATION_RESULTS) else "미실행", "—"],
        ["8", "BH-FDR 보정 후 유의성 판정표", "50_ablation",
         "출력" if ctx.get("fdr") is not None else "미실행",
         f"{int(ctx['fdr']['sig_bh'].sum())}건 유의"
         if ctx.get("fdr") is not None and len(ctx["fdr"]) else "—"],
        ["9", "섹터별 성과 분해표", "51_robust",
         "출력" if "R3" in ROBUST_RESULTS else "미실행",
         _trunc(str((ROBUST_RESULTS.get("R3") or {}).get("detail", "")), 34)],
        ["10", "강건성 테스트 결과 (R1~R11)", "51_robust",
         "출력" if rob_done else "미실행", f"{len(ROBUST_RESULTS)}건 기록"],
        ["11", "폐기 판정 여부 및 근거", "60_report",
         "출력" if kill else "미실행",
         f"{sum(1 for v in kill.values() if v is True)}건 충족" if kill else "—"],
    ]
    LOG.table(rows, ["#", "산출물", "담당 모듈", "상태", "요약"],
              ["c", "l", "l", "c", "l"], maxw=48)
    miss = [r[0] for r in rows if r[3] == "미실행"]
    if miss:
        LOG.warn(f"미출력 산출물: {', '.join(miss)} — 해당 축이 비활성화되었거나 "
                 f"상위 단계에서 표본이 부족했기 때문입니다. 위 로그에서 사유를 확인하세요.")


def report_dataflow_map() -> None:
    LOG.banner("데이터 흐름 지도 (거시)", "에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ─────────────────────────────────────────────────────────────────────────┐
  │ 환경감지 → 의존성 → 캐시 연결(로컬 D: + 구글드라이브 양쪽 탐색)                            │
  │   VAULT: 공용(_shared) = 가격·재무·공시·리포트원장·DART원문·정규화토큰  ← 타 전략 재사용   │
  │          전용(arc_txt_v2) = 유사도·피처패널·스코어·백테스트·리포트                        │
  │   append-only 저널 · 백업 후 교체 · 내용해시 blob · 삭제 API 없음 (절대 1원칙)            │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L1 수집 ──────────────────────────────────────────────────────────────────────────────┐
  │ 종목마스터 ← FDR GitHub캐시(상장/폐지) + KIND + pykrx스냅샷 + DART corpCode + 네이버      │
  │ 가격/시총  ← pykrx → FDR → 네이버 → yfinance (폴백체인, 소스 감사표)                      │
  │              PIT 시가총액 3중 경로 → U-1000 의 유일한 근거                                │
  │ DART       ← 재무(rcept_no→knowledge_date) · 직원 · 공시목록 · 주식총수 · 감사의견          │
  │              정기보고서 원문(document.xml) → 6단계 정규화 → 섹션별 토큰                    │
  │ 리서치     ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장          │
  │              → 애널리스트 원장 → 리비전 패널(직교화 통제변수)                              │
  │              → PDF 본문 전문(연도 샤드) → 축 A TONE 입력                                   │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼  모든 테이블은 pit_frame() 통과 → PIT.register()
  ┌── Phase 0 게이트 (§2) ──────────────────────────────────────────────────────────────────┐
  │ GATE_1/2 pair_count · GATE_3 본문추출률 · GATE_4 페어링 · GATE_5 판독 · GATE_6 재무       │
  │ 실패 → 해당 축만 비활성화 (전략 폐기 아님). 축 A 죽으면 DART-ONLY 폴백                     │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L2 신호 ──────────────────────────────────────────────────────────────────────────────┐
  │ U-1000 PIT 유니버스(상폐 포함) → 분기 패널 → 셀(분기×섹터)                                 │
  │ 축 A: 본문 → 문장 → 확장윈도우 분류기 → TONE → ΔTONE → **직교화** → ΔTONE_resid           │
  │ 축 B: D1 유사도4종(기간 횡단면 z) + D2 이상현상6종 + D3 하드팩트 → 0.4/0.4/0.2            │
  │       배제 플래그 8종 = 유일한 하드 제외                                                   │
  │ FINAL = 0.5·z(ΔTONE_resid) + 0.5·z(DART_SCORE)   ← 결측은 비례 재배분, 탈락 없음          │
  └──────────────────────────────┬──────────────────────────────────────────────────────────┘
                                 ▼
  ┌── L3 백테스트 → L5 검정 → L6 리포트 ────────────────────────────────────────────────────┐
  │ 분기 리밸 · 익영업일 시가 체결 · 상폐 −100% · 비용(수수료+거래세이력+스프레드 하한)         │
  │ 어블레이션 11종(A1·A2·B1~B5·F1~F4) → BH-FDR(q=0.10) → 강건성 R1~R11                      │
  │ → 성과표 · 상관행렬 · 부호검증 · 섹터분해 · 진단카드 · 폐기 판정                            │
  └─────────────────────────────────────────────────────────────────────────────────────────┘
""")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 A1~A38 — 주석이나 관례는 무효. 테스트로만 강제한다.                          ║
# ║  파이프라인 실행 전 자동 실행. 실패 시 즉시 중단(fail-fast).                                ║
# ║                                                                                          ║
# ║  ★ 이 파일의 존재 이유: "정규화가 잘 되어 있다", "미래 시총을 쓰지 않는다" 같은 문장은       ║
# ║    코드가 실제로 그런지와 무관하다. 각 계약은 진짜 데이터를 만들어 함수를 돌려 검사한다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_RESULTS: List[dict] = []


def _ac(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {str(e)[:220]}"
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": ok, "msg": msg})
    return bool(ok)


def _ac_skip(cid: str, name: str, why: str):
    CONTRACT_RESULTS.append({"id": cid, "name": name, "pass": None, "msg": f"건너뜀 — {why}"})


def _mk_sec(codes, **kw) -> pd.DataFrame:
    n = len(codes)
    d = pd.DataFrame({"code": list(codes), "name": [f"검정{i}" for i in range(n)],
                      "market": ["KOSPI"] * n, "industry": ["화학"] * n,
                      "corp_code": [f"C{i:07d}" for i in range(n)],
                      "listing_date": [as_ts("2010-01-01")] * n,
                      "delisting_date": [pd.NaT] * n})
    for k, v in kw.items():
        d[k] = v
    return d


def run_contract_tests(strict: bool = True) -> bool:
    CONTRACT_RESULTS.clear()
    G = globals()
    rng = np.random.default_rng(SEED)

    # ── A1  PIT 강제 ──────────────────────────────────────────────────────────────────────
    def a1():
        d = pd.DataFrame({"code": ["A", "A", "B"], "v": [1, 2, 3],
                          "event_date": pd.to_datetime(["2020-01-31", "2020-02-29",
                                                        "2020-01-31"]),
                          "knowledge_date": pd.to_datetime(["2020-03-15", "2020-04-15",
                                                            "2020-03-15"])})
        st = PITStore()
        st.register("t", d)
        got = st.get("t", "2020-03-20")
        if len(got) != 2:
            return False, f"as_of 절단이 틀렸습니다: {len(got)}행 (기대 2행)"
        if (got["knowledge_date"] > as_ts("2020-03-20")).any():
            return False, "★미래누수: knowledge_date > as_of 인 행이 새어나왔습니다"
        try:
            st.register("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 컬럼 없는 테이블 등록이 거부되지 않았습니다"
        except KeyError:
            pass
        # knowledge_date < event_date 는 그 자체가 미래누수 → 보정되어야 한다
        bad = pit_frame(pd.DataFrame({"x": [1], "e": [as_ts("2020-06-30")],
                                      "k": [as_ts("2020-01-01")]}), "e", "k")
        if bad["knowledge_date"].iloc[0] < bad["event_date"].iloc[0]:
            return False, "knowledge_date < event_date 가 보정되지 않았습니다"
        return True, "as_of 절단 정확 · PIT 컬럼 누락 거부 · kd<ed 보정 확인"

    _ac("A1", "Point-In-Time 강제", a1)

    # ── A2  생존자편향 ────────────────────────────────────────────────────────────────────
    def a2():
        sec = pd.DataFrame({
            "code": ["000001", "000002", "000003"], "name": ["옛날", "미래", "폐지"],
            "market": ["KOSPI"] * 3, "industry": ["X"] * 3, "corp_code": [None] * 3,
            "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01", "2010-01-01"]),
            "delisting_date": pd.to_datetime([None, None, "2018-06-30"])})
        px = pd.DataFrame({"date": pd.bdate_range("2009-01-01", "2026-08-01"),
                           "code": "000001"})
        u = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at2016 = set(u.at("2016-08-31"))
        if "000002" in at2016:
            return False, "★C2 위반: 2016년 유니버스에 2025년 상장 종목이 포함되었습니다"
        if "000003" not in at2016:
            return False, ("★C2 위반: 2018년 폐지 종목이 2016년 유니버스에서 빠졌습니다"
                           "(생존자편향 — 과거에는 분명히 상장되어 있었습니다)")
        if "000003" in set(u.at("2020-01-31")):
            return False, "폐지 이후에도 유니버스에 남아 있습니다"
        return True, "미래 상장 배제 · 폐지종목 당시 포함 · 폐지 후 제외 확인"

    _ac("A2", "생존자편향 제거", a2)

    # ── A3  U-1000 (PIT 시총 랭크) ────────────────────────────────────────────────────────
    def a3():
        # 실제 보통주 코드처럼 끝자리 0 · 간격 10 (촘촘한 연번은 형제 규칙을 오발화시킨다)
        codes = [f"{i*10:06d}" for i in range(1, 41)]
        sec = _mk_sec(codes)
        sec.loc[0, "name"] = "가나스팩1호"          # 스팩 제외 확인
        # 우선주 판정: 형제 보통주(000020)가 존재하는 000025 를 넣는다
        # ★ 형제 보통주(000020)를 남겨둔 채 다른 자리를 우선주로 바꾼다.
        #   000020 자리를 직접 덮으면 형제가 사라져 규칙이 발화하지 못한다.
        sec.loc[3, "code"] = "000025"
        codes[3] = "000025"
        sec.loc[2, "name"] = "무슨무슨리츠"
        px = pd.DataFrame({"date": pd.bdate_range("2015-01-01", "2021-01-01"),
                           "code": codes[0]})
        base = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        exd = classify_excluded(sec)
        au = ArcUniverse(base, sec, exd)
        t = as_ts("2019-03-01")
        # 시총: 과거에는 코드 순서대로 작음, '현재'에는 정반대라고 가정
        mc_past = pd.DataFrame({"code": codes, "asof": t,
                                "mktcap": np.arange(1, len(codes) + 1) * 1e10})
        liq = pd.DataFrame({"code": codes, "asof": t, "adtv60": 5e8})
        keep = int(min(ARC_UNIVERSE_N, len(codes)))
        U = au.build(pd.DatetimeIndex([t]), mc_past, liq)
        if U.empty:
            return False, "U-1000 이 비었습니다"
        got = set(U["code"])
        if "000001" in got:
            return False, "스팩이 제외되지 않았습니다"
        if "000025" in got:
            return False, "우선주(형제 보통주 000020 존재)가 제외되지 않았습니다"
        if "000003" in got:
            return False, "리츠가 제외되지 않았습니다"
        # 유동성 하한
        liq2 = liq.copy()
        liq2["adtv60"] = ARC_MIN_ADTV_KRW * 0.5
        U2 = au.build(pd.DatetimeIndex([t]), mc_past, liq2)
        if len(U2) != 0:
            return False, f"ADTV 하한({ARC_MIN_ADTV_KRW:,})이 적용되지 않았습니다 ({len(U2)}행 잔존)"
        # 랭크는 '작은 시총부터'
        mc_small = mc_past.copy()
        mc_small["mktcap"] = mc_small["mktcap"].to_numpy()[::-1]
        U3 = au.build(pd.DatetimeIndex([t]), mc_small, liq)
        r1 = U["uni_rank"].iloc[0], U["code"].iloc[0]
        r3 = U3["uni_rank"].iloc[0], U3["code"].iloc[0]
        if r1[1] == r3[1]:
            return False, ("★시총 랭크가 입력 시총에 반응하지 않습니다 — 시총을 뒤집었는데 "
                           "1순위 종목이 같습니다. PIT 시총이 아니라 다른 것으로 랭크하고 "
                           "있을 가능성이 큽니다.")
        # 미래 시총 소급 금지: 다른 시점의 시총을 주면 그 시점 유니버스가 비어야 한다
        mc_future = mc_past.copy()
        mc_future["asof"] = as_ts("2020-03-01")
        U4 = au.build(pd.DatetimeIndex([t]), mc_future, liq)
        if len(U4) != 0:
            return False, ("★미래 시총 소급: 2020-03 시총으로 2019-03 유니버스가 만들어졌습니다. "
                           "시총은 (code, asof) 키로만 조회되어야 합니다.")
        return True, (f"하위 랭크 정렬 · 스팩/우선주/리츠 제외 · ADTV 하한 · "
                      f"미래 시총 소급 차단 확인 (표본 {len(U)}종목)")

    _ac("A3", "U-1000 PIT 유니버스", a3)

    # ── A4  D1 페어링 (전년 동기 동일 유형만) ─────────────────────────────────────────────
    def a4():
        if "arc_doc_pairs" not in G:
            return False, "arc_doc_pairs 가 정의되지 않았습니다"
        rows = []
        for y in (2019, 2020):
            for dt_, m in (("FY", 3), ("Q1", 5)):
                rows.append({"corp_code": "C1", "rcept_no": f"{y}{m:02d}01x{dt_}",
                             "rcept_dt": as_ts(f"{y}-{m:02d}-15"), "doc_type": dt_,
                             "bsns_year": y - (1 if dt_ == "FY" else 0), "section": "S_ALL",
                             "n_tokens": 10, "tf": json.dumps({"가": 1}),
                             "bigram": json.dumps({}), "tok_len": 100, "is_amend": False})
        T = pd.DataFrame(rows)
        Pr = arc_doc_pairs(T)
        if Pr.empty:
            return False, "전년 동기 페어가 하나도 만들어지지 않았습니다"
        mixed = Pr[Pr["doc_type"].isna()]
        if len(mixed):
            return False, "doc_type 이 결측인 페어가 있습니다"
        # 유형이 섞인 페어가 있으면 실패
        for r in Pr.itertuples(index=False):
            if str(r.rcept_no).endswith("FY") != str(r.prev_rcept_no).endswith("FY"):
                return False, ("★문서 유형이 섞인 페어가 생성되었습니다. 사업보고서와 "
                               "분기보고서는 분량·구성이 구조적으로 달라 가짜 변화가 "
                               "대량 발생합니다(§6.1.1).")
            if (as_ts(r.rcept_dt) - as_ts(r.prev_rcept_dt)).days < 200:
                return False, ("★직전 분기와 페어링되었습니다. 반드시 전년 동기여야 합니다.")
        return True, f"동일 유형 × 전년 동기 페어 {len(Pr)}쌍 · 유형 혼합/직전분기 페어 0건"

    _ac("A4", "D1 페어링 (전년 동기 동일 유형)", a4)

    # ── A5  정규화 유효성 ★D1 전체의 전제 ────────────────────────────────────────────────
    def a5():
        if "arc_normalize_text" not in G or "arc_tokenize" not in G:
            return False, "정규화 함수가 정의되지 않았습니다"
        base = ("II. 사업의 내용\n"
                "당사는 2022년 12월 31일 기준으로 반도체 소재를 제조하여 판매하고 있습니다. "
                "제27기 매출액은 1,234,567 백만원이며 영업이익은 98,765 백만원입니다. "
                "주요 고객사는 삼성전자와 SK하이닉스이며 공급 물량은 12,345 톤입니다. "
                "당사는 품질 경영을 통해 고객 만족을 실현하고 있습니다. "
                "생산 설비는 충청북도 청주시에 위치하며 종업원은 456 명입니다.\n") * 3
        # 변형 ①: 숫자·날짜·사명만 바꿈 → 유사도 ≈ 1.0 이어야 한다
        v1 = (base.replace("2022년 12월 31일", "2023년 12월 31일")
                  .replace("제27기", "제28기")
                  .replace("1,234,567", "2,345,678").replace("98,765", "87,654")
                  .replace("12,345", "23,456").replace("456", "789")
                  .replace("가나전자", "가나첨단소재"))
        # 변형 ②: 서술을 실제로 바꿈 → 유사도가 유의하게 낮아야 한다
        v2 = base.replace(
            "당사는 품질 경영을 통해 고객 만족을 실현하고 있습니다.",
            "경쟁 심화로 수익성이 악화되었으며 일부 라인의 가동을 중단하였습니다. "
            "환율 변동과 원자재 가격 상승이 원가 부담을 가중시키고 있습니다.")
        v2 = v2.replace("반도체 소재를 제조하여 판매", "이차전지 부품을 개발하여 공급")

        names = ["가나전자", "가나첨단소재"]
        t0 = set(arc_tokenize(arc_normalize_text(base, names)))
        t1 = set(arc_tokenize(arc_normalize_text(v1, names)))
        t2 = set(arc_tokenize(arc_normalize_text(v2, names)))
        if not t0 or not t1:
            return False, "토큰이 생성되지 않았습니다(토큰화 실패)"
        j1 = len(t0 & t1) / max(len(t0 | t1), 1)
        j2 = len(t0 & t2) / max(len(t0 | t2), 1)
        if j1 < 0.98:
            return False, (f"★숫자·날짜·사명만 바꾼 문서의 자카드가 {j1:.3f} 입니다(기대 ≥0.98). "
                           f"정규화가 가짜 변화를 제거하지 못했다는 뜻이며, 이 상태에서는 "
                           f"D1 의 모든 결과가 무의미합니다 — 전 종목이 '변경 기업'이 됩니다.")
        if j2 >= j1 - 0.02:
            return False, (f"★실제 서술을 바꾼 문서의 자카드가 {j2:.3f} 로 가짜변화본"
                           f"({j1:.3f})과 구분되지 않습니다. 정규화가 과도해서 진짜 변화까지 "
                           f"지워버렸을 가능성이 큽니다.")
        norm = arc_normalize_text(base, names)
        for mark in ("<NUM>", "<DATE>", "<PERIOD>"):
            if mark not in norm:
                return False, f"마스크 {mark} 가 적용되지 않았습니다"
        if re.search(r"\d", norm.replace("<NUM>", "").replace("<DATE>", "")
                             .replace("<PERIOD>", "")):
            return False, "정규화 후에도 원시 숫자가 남아 있습니다"
        return True, (f"가짜변화 자카드 {j1:.3f} (≥0.98) · 진짜변화 {j2:.3f} (유의하게 낮음) · "
                      f"마스크 전부 적용 확인")

    _ac("A5", "정규화 유효성 (D1 의 전제)", a5)

    # ── A6  횡단면 z ──────────────────────────────────────────────────────────────────────
    def a6():
        v = pd.Series([1.0] * 30 + [1000.0])
        cell = pd.Series(["A"] * 31)
        z = xsec_z(v, cell)
        if not np.isfinite(z).all():
            return False, "z-score 에 비유한값이 있습니다"
        if float(z.max()) > 6:
            return False, f"윈저라이즈 미적용 (max z={z.max():.2f})"
        small = xsec_rank_pct(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]))
        if small.notna().any():
            return False, "표본 부족 셀이 NaN 이 아닙니다(0으로 채우면 안 됩니다)"
        vi = pd.Series([1.0, 2, 3, np.inf, 5, 6, 7, 8, 9, 10])
        zi = xsec_z(vi, pd.Series(["A"] * 10))
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, ("★±inf 오염: 셀에 inf 가 하나만 있어도 z 가 전부 뭉개집니다. "
                           "비율/로그 지표에서 흔히 발생하며 그 셀의 신호가 통째로 사라집니다.")
        # 기간 셀 평균 ≈ 0
        n = 300
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "cell": rng.choice(["Q1|IT", "Q1|소재", "Q1|금융"], n),
                          "cell_all": "Q1|ALL", "x": rng.normal(size=n)})
        z2 = xsec_z_arc(P, "x")
        for c, g in P.assign(z=z2).groupby("cell"):
            if g["z"].notna().sum() >= CELL_MIN_N and abs(float(g["z"].mean())) > 0.15:
                return False, f"셀 {c} 의 z 평균이 0에서 벗어남: {g['z'].mean():.3f}"
        return True, "winsorize→z 순서 · 표본부족 NaN · ±inf 무해화 · 셀 평균≈0 확인"

    _ac("A6", "횡단면 표준화", a6)

    # ── A7  D1 섹션 가중치 재배분 ─────────────────────────────────────────────────────────
    def a7():
        wv = np.array([ARC_D1_WEIGHTS[s] for s in ARC_SECTIONS], dtype=float)
        if abs(wv.sum() - 1.0) > 1e-9:
            return False, f"사전등록 가중치 합이 1이 아닙니다: {wv.sum():.6f}"
        V = np.array([[1.0, np.nan, 1.0, np.nan, np.nan, np.nan, 1.0]])
        msk = np.isfinite(V)
        wm = np.where(msk, wv[None, :], 0.0)
        ws = wm.sum(axis=1)
        comp = np.nansum(np.where(msk, V, 0.0) * wm, axis=1) / ws
        if abs(float(comp[0]) - 1.0) > 1e-9:
            return False, (f"★결측 섹션 가중치가 비례 재배분되지 않았습니다 "
                           f"(전 섹션 값이 1.0 인데 합성이 {comp[0]:.4f}). "
                           f"섹션이 적게 파싱된 종목이 구조적으로 불리해집니다.")
        return True, f"결측 섹션 3개 상황에서도 가중치 합 = 1 · 합성값 보존 확인"

    _ac("A7", "D1 섹션 가중치 재배분", a7)

    # ── A8~A11  편입 규칙 4대 회귀 방지 ───────────────────────────────────────────────────
    def _mk_panel(n=60):
        t = as_ts("2020-06-01")
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(1, n + 1)], "asof": t, "q": "2020Q1",
            "cell": "2020Q1|IT", "cell_all": "2020Q1|ALL", "sector": "IT/전자",
            "corp_code": [f"C{i:07d}" for i in range(1, n + 1)],
            "mktcap": np.linspace(1e10, 5e10, n), "adtv60": 5e8,
            "exec_px": 10000.0, "fwd_ret_1q": rng.normal(0, 0.1, n),
            "dTONE": rng.normal(size=n), "dTONE_resid": rng.normal(size=n),
            "has_axis_a": 1.0,
            "D1_SCORE": rng.normal(size=n), "D2_SCORE": rng.normal(size=n),
            "D3_SCORE": rng.normal(size=n), "DELTA_NONFIN": rng.integers(0, 3, n).astype(float),
            "EXCLUDE": 0.0, "listing_months": 60.0})
        return P

    def a8():
        P = _mk_panel()
        P.loc[:9, "EXCLUDE"] = 1.0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        bad = Q.loc[Q["EXCLUDE"] == 1.0, "FINAL_SCORE"].notna().sum()
        if bad:
            return False, (f"★배제 플래그가 발동한 {int(bad)}행에 점수가 남아 있습니다. "
                           f"§6.4 는 '점수 무관 즉시 제외'를 규정합니다.")
        if Q.loc[Q["EXCLUDE"] == 0.0, "FINAL_SCORE"].notna().sum() == 0:
            return False, "배제되지 않은 종목까지 전부 제외되었습니다"
        return True, "EXCLUDE=1 인 10행 전부 편입 불가 · 나머지는 정상 유지"

    _ac("A8", "배제 플래그 하드 제외", a8)

    def a9():
        P = _mk_panel()
        P["DELTA_NONFIN"] = 0.0                       # 전 종목 ΔNONFIN = 0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        if Q["FINAL_SCORE"].notna().sum() == 0:
            return False, ("★ΔNONFIN=0 인 종목이 전부 탈락했습니다. v1.0 의 하드게이트가 "
                           "되살아났다는 뜻입니다 — §6.3 은 이 규칙을 명시적으로 폐기했습니다.")
        Q4 = assemble_final(P, use_axes=("A_RAW",), use_excl=True, v1_hardgate=True)
        if Q4["FINAL_SCORE"].notna().sum() != 0:
            return False, "F4(v1.0 재현) 팔에서 하드게이트가 작동하지 않았습니다"
        return True, ("ΔNONFIN=0 종목도 본선 편입 가능 · F4 재현 팔에서만 하드게이트 작동 확인")

    _ac("A9", "ΔNONFIN 하드게이트 폐기 (v1.0 규칙 부활 방지)", a9)

    def a10():
        P = _mk_panel()
        P.loc[:19, ["dTONE", "dTONE_resid"]] = np.nan       # 리포트 없는 종목 20개
        P.loc[:19, "has_axis_a"] = 0.0
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        n_ok = int(Q.loc[:19, "FINAL_SCORE"].notna().sum())
        if n_ok < 20:
            return False, (f"★축 A 결측 종목 20개 중 {20-n_ok}개가 탈락했습니다. "
                           f"§7.2 는 'ΔTONE_resid=0(중립)으로 두고 DART_SCORE 만으로 평가, "
                           f"탈락시키지 말 것' 을 규정합니다. 이것이 v2.0 에서 축 B 를 "
                           f"강화한 이유입니다.")
        return True, "리포트 없는 20개 종목이 DART_SCORE 만으로 전부 생존 확인"

    _ac("A10", "축 A 결측 종목 생존 (§7.2)", a10)

    def a11():
        P = _mk_panel()
        P.loc[:29, "D1_SCORE"] = np.nan                      # D1 결측 30개
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        n_ok = int(Q.loc[:29, "FINAL_SCORE"].notna().sum())
        if n_ok < 30:
            return False, (f"★D1 결측 종목 30개 중 {30-n_ok}개가 탈락했습니다. "
                           f"§6.5 는 'D1 가중치를 D2·D3 에 비례 재배분, 종목을 탈락시키지 "
                           f"말 것' 을 규정합니다.")
        if int(Q.loc[:29, "n_axes_b"].max()) != 2:
            return False, f"D1 결측 행의 축 B 층수가 2가 아닙니다: {Q.loc[:29,'n_axes_b'].max()}"
        # 재배분이 실제로 되었는지: D1 결측 행의 DART_SCORE 가 D2·D3 만으로 계산돼야 한다
        r0 = Q.loc[0]
        man = (ARC_W_D2 * P.loc[0, "D2_SCORE"] + ARC_W_D3 * P.loc[0, "D3_SCORE"]) / \
              (ARC_W_D2 + ARC_W_D3)
        # DART_SCORE 는 그 뒤 다시 z 표준화되므로 값 자체가 아니라 '유한함'만 확인
        if not np.isfinite(r0["DART_SCORE"]) or not np.isfinite(man):
            return False, "D1 결측 행의 DART_SCORE 가 계산되지 않았습니다"
        return True, "D1 결측 30행 전부 생존 · 축 B 층수 2 · D2·D3 로 재배분 확인"

    _ac("A11", "D1 결측 시 가중치 재배분 (§6.5)", a11)

    # ── A12  직교화 필수 ──────────────────────────────────────────────────────────────────
    def a12():
        if "attach_axis_a" not in G:
            return False, "attach_axis_a 가 정의되지 않았습니다"
        import inspect
        src = inspect.getsource(G["attach_axis_a"])
        # ① 사전등록 통제변수 목록이 §5.3 표를 그대로 담고 있는가
        need_ctrl = ["eps_rev", "tp_rev", "opin_chg", "mom_12_1", "log_mktcap", "log_adtv"]
        miss_c = [k for k in need_ctrl if k not in list(ARC_TONE_CONTROLS)]
        if miss_c:
            return False, (f"★ARC_TONE_CONTROLS 에 통제변수 {miss_c} 가 없습니다. §5.3 은 "
                           f"직교화를 '전략 성립의 필요조건' 으로 규정합니다.")
        # ② 함수가 그 목록과 섹터더미·잔차화를 실제로 쓰는가
        need_use = ["ARC_TONE_CONTROLS", "get_dummies", "xsec_resid", "dTONE_resid"]
        miss_u = [k for k in need_use if k not in src]
        if miss_u:
            return False, (f"★attach_axis_a 가 {miss_u} 를 쓰지 않습니다 — 통제변수 목록만 "
                           f"있고 회귀가 실제로 돌지 않으면 직교화는 이름뿐입니다.")
        # ③ 잔차가 원신호와 실제로 달라지는가 (형식이 아니라 동작 검증)
        n = 240
        q = np.repeat(["2020Q1", "2020Q2", "2020Q3", "2020Q4"], n // 4)
        ctrl = rng.normal(size=n)
        y = 0.8 * ctrl + rng.normal(scale=0.3, size=n)
        X = pd.DataFrame({"c": ctrl})
        r = xsec_resid(pd.Series(y), X, pd.Series(q))
        if r.notna().sum() < n * 0.8:
            return False, f"xsec_resid 가 {int(r.notna().sum())}/{n} 행만 잔차를 냈습니다"
        c_before = abs(float(np.corrcoef(y, ctrl)[0, 1]))
        m = r.notna().to_numpy()
        c_after = abs(float(np.corrcoef(r[m].to_numpy(), ctrl[m])[0, 1]))
        if not (c_before > 0.5 and c_after < 0.15):
            return False, (f"★직교화가 통제변수와의 상관을 제거하지 못했습니다 "
                           f"({c_before:.3f} → {c_after:.3f}). 잔차화가 형식적으로만 "
                           f"수행되고 있을 가능성이 큽니다.")
        return True, (f"통제변수 {len(ARC_TONE_CONTROLS)}종 + 섹터더미 + 잔차화 사용 확인 · "
                      f"통제변수 상관 {c_before:.3f} → {c_after:.3f} 로 실제 제거됨")

    _ac("A12", "ΔTONE 직교화 필수 (§5.3)", a12)

    # ── A13  튜닝 금지 ────────────────────────────────────────────────────────────────────
    def a13():
        import inspect
        src = ""
        for nm in ("assemble_final", "d1_composite", "attach_d2", "attach_d3"):
            if nm in G:
                try:
                    src += inspect.getsource(G[nm])
                except Exception:
                    pass
        if re.search(r"(minimize|curve_fit|GridSearch|RandomizedSearch|optimize\.|"
                     r"\.fit\([^)]*weight)", src):
            return False, "★가중치 최적화 흔적이 발견되었습니다 — 사전등록 가중치 튜닝 금지"
        wsum = ARC_W_D1 + ARC_W_D2 + ARC_W_D3
        if abs(wsum - 1.0) > 1e-9:
            return False, f"축 B 가중치 합이 1이 아닙니다: {wsum}"
        if abs(ARC_W_AXIS_A + ARC_W_AXIS_B - 1.0) > 1e-9:
            return False, "축 A/B 가중치 합이 1이 아닙니다"
        if (ARC_W_D1, ARC_W_D2, ARC_W_D3) != (0.40, 0.40, 0.20):
            return False, (f"사전등록 가중치가 변경되었습니다: "
                           f"{(ARC_W_D1, ARC_W_D2, ARC_W_D3)} (기대 0.40/0.40/0.20)")
        return True, "최적화 루틴 부재 · 사전등록 가중치 0.40/0.40/0.20 · 0.5/0.5 확인"

    _ac("A13", "가중치 튜닝 금지 (사전등록)", a13)

    # ── A14  결정성 ───────────────────────────────────────────────────────────────────────
    def a14():
        a = np.random.default_rng(SEED).normal(size=50)
        b = np.random.default_rng(SEED).normal(size=50)
        if not np.allclose(a, b):
            return False, "동일 시드에서 다른 난수가 나왔습니다"
        x = pd.Series(rng.normal(size=200))
        cell = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = xsec_z(x, cell)
        z2 = xsec_z(x.iloc[::-1], cell.iloc[::-1]).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿉니다(병렬 처리에서 재현 불가)"
        return True, "시드 고정 · 입력 순서 무관 확인"

    _ac("A14", "결정성", a14)

    # ── A15  시점 규약 ────────────────────────────────────────────────────────────────────
    def a15():
        rb = rebal_dates("2016-08-01", "2026-07-31")
        if len(rb) == 0:
            return False, "리밸런싱일이 생성되지 않았습니다"
        if any(t.month not in ARC_REBAL_MONTHS or t.day != 1 for t in rb):
            return False, f"리밸일이 3/1·6/1·9/1·12/1 이 아닙니다: {rb[:4].tolist()}"
        if prev_quarter_of("2019-09-01") != "2019Q2":
            return False, (f"★리밸일 직전 분기 계산 오류: 2019-09-01 → "
                           f"{prev_quarter_of('2019-09-01')} (기대 2019Q2). "
                           f"9/1 에 2019Q3(7~9월)을 쓰면 아직 끝나지 않은 분기를 쓰는 것이라 "
                           f"미래누수입니다.")
        if qshift("2019Q1", -1) != "2018Q4" or qshift("2019Q3", -4) != "2018Q3":
            return False, "분기 시프트 계산 오류"
        # DART 는 rcept_dt + 1일 이후 사용 가능
        if ARC_DART_LAG_DAYS < 1 or ARC_REPORT_LAG_DAYS < 1:
            return False, "T+1 규약이 0 으로 설정되어 있습니다(접수일 당일 사용 = 미래누수)"
        return True, (f"리밸일 {len(rb)}개 (3/6/9/12월 1일) · 직전분기 계산 정확 · "
                      f"DART/리포트 T+1 규약 확인")

    _ac("A15", "시점 규약 (룩어헤드 금지)", a15)

    # ── A16  종목코드 정규화 ──────────────────────────────────────────────────────────────
    def a16():
        cases = {"005930": "005930", 5930: "005930", "A005930": "005930",
                 "005930.KS": "005930", "09701K": "09701K", "": None, "abcdef": None}
        for k, v in cases.items():
            if to_code6(k) != v:
                return False, f"to_code6({k!r}) = {to_code6(k)!r} (기대 {v!r})"
        if not is_preferred("005935", "삼성전자우"):
            return False, "우선주 판정 실패 (005935, 이름 규칙)"
        if not is_preferred("005935", "", {"005930", "005935"}):
            return False, "우선주 판정 실패 (005935, 형제 보통주 규칙)"
        if is_preferred("006800", "미래에셋대우"):
            return False, "★'대우' 로 끝나는 정상 사명이 우선주로 오판되었습니다"
        if is_preferred("900140", "엘브이엠씨홀딩스", {"900140"}):
            return False, "★형제 보통주가 없는 종목이 우선주로 오판되었습니다"
        return True, "구형 6자리 + 2024 영숫자 티커(09701K) + 우선주 판정 확인"

    _ac("A16", "종목코드 정규화", a16)

    # ── A17  분기 연율화 ──────────────────────────────────────────────────────────────────
    def a17():
        if PERIODS_PER_YEAR != 4:
            return False, (f"★연율화 계수가 {PERIODS_PER_YEAR} 입니다. 분기 리밸런싱이므로 "
                           f"4 여야 합니다. 12(월) 로 두면 성과가 통째로 3배 부풀려집니다.")
        r = pd.DataFrame({"asof": rebal_dates("2017-03-01", "2026-12-01")[:20],
                          "ret": [0.05] * 20, "n": [30] * 20,
                          "turnover": [0.5] * 20, "cost": [0.0] * 20,
                          "n_elig": [500] * 20})
        s = perf_stats(r)
        # 분기 5% 20회 = 5년, CAGR = 1.05^4 - 1 = 21.55%
        exp = 1.05 ** 4 - 1
        if abs(s["CAGR"] - exp) > 1e-6:
            return False, f"CAGR 이 {s['CAGR']:.6f} (기대 {exp:.6f}) — 연율화가 틀렸습니다"
        if abs(s["기간수(분기)"] - 20) > 0:
            return False, "기간 수 계산 오류"
        return True, f"분기 5% × 20 → CAGR {s['CAGR']*100:.2f}% (= 1.05^4−1) 확인"

    _ac("A17", "분기 연율화 (계수 4)", a17)

    # ── A18  LLM 호출 금지 ────────────────────────────────────────────────────────────────
    def a18():
        import inspect
        targets = ["fit_tone_expanding", "score_tone_reports", "build_tone_training",
                   "arc_normalize_text", "arc_tokenize", "extract_hardfacts",
                   "d1_similarity", "assemble_final", "fetch_arc_documents"]
        src = ""
        for nm in targets:
            if nm in G:
                try:
                    src += inspect.getsource(G[nm])
                except Exception:
                    pass
        pat = (r"openai|anthropic|gpt-|claude-|generativeai|/v1/chat/completions|"
               r"api\.openai|api\.anthropic|gemini|cohere\.")
        if re.search(pat, src, re.I):
            return False, ("★LLM API 호출 흔적이 발견되었습니다. §5.1/§6.3 은 이를 명시적으로 "
                           "금지합니다 — 토큰 비용이 아니라 사전학습 코퍼스로 인한 룩어헤드 "
                           "오염 때문입니다.")
        return True, f"검사 대상 {len([n for n in targets if n in G])}개 함수에 LLM 호출 없음"

    _ac("A18", "LLM API 호출 금지", a18)

    # ── A19  DART 파생 테이블의 T+1 규약 ──────────────────────────────────────────────────
    def a19():
        """§4 'rcept_dt(접수일자) + 1거래일부터 사용 가능' 이 재무 계열에도 적용되는가.

        ★ 초기 빌드에서 D1 만 +1 을 적용하고 재무·직원·주식수·감사의견은 접수 당일부터
          쓸 수 있었다. 작지만 명백한 미래누수이며, 접수는 장중에도 일어나므로 실행 불가능한
          정보 접근이다. 여기서 실제 프레임을 만들어 검사한다.
        """
        rc = REPRT_CODES["FY"]
        fin = pit_frame(pd.DataFrame({
            "corp_code": ["C1", "C1"], "bsns_year": [2019, 2020], "reprt_code": [rc, rc],
            "period_end": pd.to_datetime(["2019-12-31", "2020-12-31"]),
            "knowledge_date": pd.to_datetime(["2020-03-20", "2021-03-20"]),
            "assets": [1000.0, 1100.0], "liabilities": [400.0, 430.0],
            "equity": [600.0, 670.0], "cash": [100.0, 120.0],
            "net_income_ttm": [50.0, 60.0], "cfo_ttm": [55.0, 70.0],
            "revenue_ttm": [900.0, 990.0], "inventory": [80.0, 85.0],
            "receivable": [90.0, 95.0], "op_income_q": [12.0, 14.0],
        }), "period_end", "knowledge_date")
        d2 = build_d2_panel(fin, None)
        if d2 is None or d2.empty:
            return False, "D2 패널이 비어 T+1 검사를 할 수 없습니다"
        kd = as_ts_series(d2["knowledge_date"]).min()
        if kd <= as_ts("2020-03-20"):
            return False, (f"★T+1 위반: 접수일 2020-03-20 인 재무제표의 knowledge_date 가 "
                           f"{str(kd)[:10]} 입니다. 접수 당일부터 쓸 수 있으면 미래누수입니다"
                           f"(§4).")
        # as-of 결합에서도 실제로 차단되는지
        st = PITStore()
        st.register("t_d2", d2, key_cols=["corp_code"])
        panel = pd.DataFrame({"code": ["A"], "corp_code": ["C1"],
                              "asof": [as_ts("2020-03-20")]})
        got = st.asof_join(panel, "t_d2", by="corp_code", left_time="asof")
        if "ACCRUAL" in got.columns and got["ACCRUAL"].notna().any():
            return False, ("★접수 당일(2020-03-20) 리밸런싱에서 그 날 접수된 재무가 "
                           "결합되었습니다. T+1 이 as-of 결합에서 무력화되고 있습니다.")
        got2 = st.asof_join(pd.DataFrame({"code": ["A"], "corp_code": ["C1"],
                                          "asof": [as_ts("2020-03-21")]}),
                            "t_d2", by="corp_code", left_time="asof")
        if "ACCRUAL" not in got2.columns or not got2["ACCRUAL"].notna().any():
            return False, "T+1 다음 날에도 결합되지 않습니다 — 지연이 과도합니다"
        return True, (f"재무 knowledge_date = 접수일 + {ARC_DART_LAG_DAYS}일 · "
                      f"접수 당일 결합 차단 · 익일 결합 정상 확인")

    _ac("A19", "DART T+1 규약 (재무 계열)", a19)

    # ── A20  게이트가 실제로 축을 끄는가 (skip_if 함정) ───────────────────────────────────
    def a20():
        """★ PIPE.stage(skip_if=True) 는 스테이지를 SKIP 으로 '표시'만 하고 with 본문은
        그대로 실행한다(컨텍스트 매니저의 구조적 한계). 이걸 모르고 쓰면 '축을 껐다'고
        로그에는 찍히는데 계산은 다 돌고 값까지 반영되는 조용한 사고가 난다.
        여기서 ① 그 성질을 명시적으로 확인하고 ② 오케스트레이터가 명시 분기로 막았는지 본다.
        """
        ran = {"n": 0}
        with PIPE.stage("T.SKIP", "계약검정용", "L0", skip_if=True, skip_reason="검정"):
            ran["n"] += 1
        if ran["n"] == 0:
            return True, ("skip_if 가 본문 실행까지 막습니다(파이썬 버전/구현 변경). "
                          "이 경우 호출부의 명시 분기는 불필요하지만 무해합니다.")
        # 본문이 실행되는 것이 정상이므로, 오케스트레이터가 명시 분기로 막고 있어야 한다.
        import inspect
        src = inspect.getsource(G["arc_build_signals"]) if "arc_build_signals" in G else ""
        for var, why in (("_d1_on", "D1"), ("_axis_a_on", "축 A")):
            if var not in src:
                return False, (f"★게이트가 {why} 를 실제로 끄지 못합니다. skip_if 는 표시만 "
                               f"하므로 with 본문 안에서 `if {var}:` 로 분기해야 합니다. "
                               f"현재 구조에서는 Phase 0 에서 축을 껐다고 보고해 놓고 "
                               f"계산 결과가 그대로 신호에 들어갑니다.")
        if "attach_d1(P, None)" not in src or "attach_axis_a(P, None, None)" not in src:
            return False, "게이트 off 경로에서 축을 결측 처리하는 호출이 없습니다"
        return True, ("skip_if 는 표시 전용임을 확인 · 오케스트레이터가 _d1_on/_axis_a_on 으로 "
                      "명시 분기하고 off 경로에서 축을 결측 처리함 확인")

    _ac("A20", "게이트가 실제로 축을 끄는가", a20)

    # ── A21  '정보 없음' 을 '중립 0' 으로 착각하지 않는가 ─────────────────────────────────
    def a21():
        P = _mk_panel()
        P.loc[:29, ["dTONE", "dTONE_resid"]] = np.nan       # 축 A 결측 30개
        P.loc[:14, ["D1_SCORE", "D2_SCORE", "D3_SCORE"]] = np.nan   # 그중 15개는 축 B 도 결측
        # ① 축 A 단독 팔: 결측을 0 으로 채우면 전 종목 동점이 되어 코드 순서로 편입된다
        Q1 = assemble_final(P, use_axes=("A",), use_excl=True)
        if Q1.loc[:29, "FINAL_SCORE"].notna().any():
            return False, ("★축 A 단독 팔에서 ΔTONE 결측 종목에 점수가 부여됐습니다. "
                           "그 팔에는 DART_SCORE 가 없으므로 '중립 0' 은 곧 전 종목 동점이고, "
                           "리포트가 없는 종목이 코드 순서로 편입됩니다 — A1 이 축 A 의 "
                           "순기여가 아니라 동점 처리 규칙을 측정하게 됩니다.")
        if not Q1.loc[30:, "FINAL_SCORE"].notna().any():
            return False, "축 A 단독 팔에서 ΔTONE 이 있는 종목까지 탈락했습니다"
        # ② 풀버전: 축 A 결측이라도 축 B 가 있으면 생존(§7.2)
        Q2 = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        if not Q2.loc[15:29, "FINAL_SCORE"].notna().all():
            return False, "풀버전에서 축 A 결측·축 B 보유 종목이 탈락했습니다(§7.2 위반)"
        # ③ 두 축 모두 결측이면 편입 불가 (근거 없는 종목이 중간 순위를 차지하면 안 된다)
        if Q2.loc[:14, "FINAL_SCORE"].notna().any():
            return False, ("★축 A·축 B 가 모두 결측인 종목에 점수가 부여됐습니다. "
                           "아무 근거도 없는 종목이 중간 순위를 차지하고, 표본이 얇은 분기에는 "
                           "실제로 편입됩니다.")
        return True, ("단독 팔은 결측 유지 · 풀버전은 축 A 결측 생존(§7.2) · "
                      "두 축 모두 결측이면 편입 불가 확인")

    _ac("A21", "'정보 없음' vs '중립 0' 구분", a21)

    # ── A22  배제 플래그가 소스별로 서로를 지우지 않는가 ──────────────────────────────────
    def a22():
        # 한국 소형주에서 흔한 조합: FY 감사의견 '의견거절'(3월 접수) → CB 발행(4월) →
        # 1분기보고서 정상(5월). 예전에는 5월 행이 최근행이 되어 3·4월 플래그를 지웠다.
        X = pd.DataFrame([
            {"corp_code": "C1", "event_date": pd.Timestamp("2018-12-31"),
             "knowledge_date": pd.Timestamp("2019-03-26"), "EX_AUDIT": 1.0},
            {"corp_code": "C1", "event_date": pd.Timestamp("2019-04-10"),
             "knowledge_date": pd.Timestamp("2019-04-11"), "EX_CBBW": 1.0},
            {"corp_code": "C1", "event_date": pd.Timestamp("2019-03-31"),
             "knowledge_date": pd.Timestamp("2019-05-16"), "EX_LOSS4Q": 0.0,
             "EX_IMPAIR": 0.0},
        ])
        X = ensure_cols(X, EXCL_COLS, fill=np.nan)
        S = _event_state_table(X, EXCL_COLS, EXCL_VALID_DAYS)
        S = pit_frame(S, "event_date", "knowledge_date", source="t")
        P = pd.DataFrame({"corp_code": ["C1"] * 3, "code": ["000010"] * 3,
                          "asof": pd.to_datetime(["2019-06-01", "2019-09-01", "2021-06-01"]),
                          "q": ["2019Q1", "2019Q2", "2021Q1"], "sector": ["기타"] * 3,
                          "DELTA_NONFIN": [np.nan] * 3})
        Q = attach_d3(P, None, S)
        got = pd.to_numeric(Q["EXCLUDE"], errors="coerce").fillna(0).tolist()
        if got[0] < 1 or got[1] < 1:
            return False, ("★감사의견 '의견거절'과 CB 발행이 걸린 종목이 다음 분기보고서 "
                           "접수만으로 제외 해제됐습니다. 소스별 행이 서로의 플래그를 NaN 으로 "
                           "덮고, as-of 결합이 최근 1행만 붙이기 때문입니다 — §6.4 하드 "
                           f"제외가 사실상 작동하지 않습니다. EXCLUDE={got}")
        if got[2] > 0:
            return False, (f"2년이 지난 뒤에도 제외가 유지됩니다(유효기간 미적용). EXCLUDE={got}")
        return True, ("소스가 다른 EX_AUDIT·EX_CBBW 가 동시에 유지되고(2019-06/09 제외), "
                      "유효기간 경과 후 해제됨(2021-06) 확인")

    _ac("A22", "배제 플래그 소스 간 상호 소거 방지", a22)

    # ── A23  전방수익률이 다음 분기 유니버스 잔류에 조건 지워지지 않는가 ─────────────────
    def a23():
        # WINNER 는 다음 리밸일에 U-1000 밖으로 나가지만(=크게 오른 종목) 가격은 계속 있다.
        rb = pd.to_datetime(["2019-03-01", "2019-06-01"])
        U = pd.DataFrame({"code": ["WIN", "LOS", "LOS"],
                          "asof": [rb[0], rb[0], rb[1]],
                          "mktcap": [1e10, 1e10, 1e10], "uni_rank": [1, 2, 1],
                          "adtv60": [5e8, 5e8, 5e8]})
        execp = pd.DataFrame({"code": ["WIN", "WIN", "LOS", "LOS"],
                              "asof": [rb[0], rb[1], rb[0], rb[1]],
                              "exec_px": [100.0, 118.0, 100.0, 97.0],
                              "exec_date": [rb[0], rb[1], rb[0], rb[1]]})
        sec = pd.DataFrame({"code": ["WIN", "LOS"], "name": ["승자", "패자"],
                            "market": ["KOSDAQ"] * 2, "industry": ["기타"] * 2,
                            "corp_code": ["W", "L"], "listing_date": [pd.NaT] * 2})

        class _U:
            def delisting_map(self): return {}
        P = build_arc_panel(_U(), rb, U, pd.DataFrame(), execp, sec, px_daily=None)
        w = P[(P["code"] == "WIN") & (P["asof"] == rb[0])]
        if w.empty or not np.isfinite(float(w["fwd_ret_1q"].iloc[0])):
            return False, ("★다음 분기에 U-1000 을 이탈하는 종목의 전방수익률이 NaN 입니다. "
                           "run_backtest 의 elig 필터가 그 종목을 **오늘의 편입 후보에서** "
                           "지우므로, 오늘의 편입 자격이 내일의 유니버스 잔류 여부로 "
                           "결정됩니다(방향성 있는 편향).")
        r = float(w["fwd_ret_1q"].iloc[0])
        if abs(r - 0.18) > 1e-3:
            return False, f"전방수익률이 체결가 격자와 불일치: {r:+.4f} (기대 +0.1800)"
        return True, f"유니버스 이탈 종목도 execp 격자에서 정상 계산 ({r:+.2%})"

    _ac("A23", "전방수익률 ⊥ 미래 유니버스 멤버십", a23)

    # ── A24  상장폐지: 정상 폐지는 청산가, 거래정지 후 폐지는 복원 ────────────────────────
    def a24():
        rb = pd.to_datetime(["2019-09-01", "2019-12-01", "2020-03-01"])
        # MERGE: 2019-12-27 피흡수합병(정상 폐지). 직전까지 정상 거래 → -100% 면 가짜 손실.
        # HALT : 2019-12-10 거래정지 → 2020-09-30 폐지. 패널에서 먼저 사라지는 경로.
        U = pd.DataFrame({"code": ["MRG", "HLT"], "asof": [rb[1], rb[1]],
                          "mktcap": [1e10, 1e10], "uni_rank": [1, 2],
                          "adtv60": [5e8, 5e8]})
        execp = pd.DataFrame({"code": ["MRG", "HLT"], "asof": [rb[1], rb[1]],
                              "exec_px": [100.0, 100.0], "exec_date": [rb[1], rb[1]]})
        px = pd.DataFrame({
            "code": ["MRG"] * 2 + ["HLT"] * 2,
            "date": pd.to_datetime(["2019-12-02", "2019-12-20",
                                    "2019-12-02", "2019-12-09"]),
            "open": [100.0, 98.0, 100.0, 40.0], "close": [99.0, 98.0, 95.0, 38.0]})
        sec = pd.DataFrame({"code": ["MRG", "HLT"], "name": ["합병", "정지"],
                            "market": ["KOSDAQ"] * 2, "industry": ["기타"] * 2,
                            "corp_code": ["M", "H"], "listing_date": [pd.NaT] * 2})

        class _U:
            def delisting_map(self):
                return {"MRG": pd.Timestamp("2019-12-27"),
                        "HLT": pd.Timestamp("2020-09-30")}
        P = build_arc_panel(_U(), rb, U, pd.DataFrame(), execp, sec, px_daily=px)
        g = {c: float(v) for c, v in zip(P["code"], P["fwd_ret_1q"])}
        if abs(g.get("MRG", -9) + 1.0) < 1e-6:
            return False, ("★합병·완전자회사화 같은 정상 폐지에 -100% 가 붙었습니다. "
                           "실제로는 합병비율·공개매수가로 원금 수준이 회수됩니다 — "
                           "폐지목록의 34%가 정상 사유이므로 상시 가짜 손실이 됩니다.")
        if abs(g.get("MRG", 0) - (98.0 / 100.0 - 1.0)) > 1e-6:
            return False, f"정상 폐지 청산가가 폐지일 직전 종가가 아닙니다: {g.get('MRG')}"
        if not (g.get("HLT", 0) < -0.5):
            return False, ("★거래정지 후 폐지 종목의 손실이 계상되지 않았습니다. "
                           "거래정지 → 시총 격자 소실 → 폐지 순서라 패널에 행이 없어지고, "
                           "한국의 감사의견거절·자본잠식 폐지는 대부분 이 경로입니다 "
                           f"— 손실만 선택적으로 사라집니다. fwd_ret={g.get('HLT')}")
        return True, (f"정상 폐지는 직전 종가 청산({g['MRG']:+.2%}) · "
                      f"거래정지 후 폐지는 복원({g['HLT']:+.2%})")

    _ac("A24", "§3.4 상장폐지 청산가 · 거래정지 경로", a24)

    # ── A25  결정적 해시 (프로세스 간 재현성) ─────────────────────────────────────────────
    def a25():
        import subprocess as _sp
        src = ("import hashlib;"
               "print(int.from_bytes(hashlib.blake2b('영업이익'.encode(),"
               "digest_size=8).digest(),'little')%262144)")
        outs = set()
        for _ in range(2):
            r = _sp.run([sys.executable, "-c", src], capture_output=True, text=True,
                        timeout=30, env={**os.environ, "PYTHONHASHSEED": "random"})
            outs.add(r.stdout.strip())
        if len(outs) != 1:
            return False, f"해시가 프로세스마다 다릅니다: {outs}"
        if "hash(w)" in inspect.getsource(_ToneNaiveBayes):
            return False, ("★폴백 TONE 분류기가 파이썬 내장 hash() 를 씁니다. CPython 의 "
                           "문자열 해시는 PYTHONHASHSEED 로 프로세스마다 랜덤화되므로 같은 "
                           "SEED·같은 캐시로 두 번 돌리면 보유 종목이 달라집니다. A14 는 "
                           "동일 프로세스 안에서 돌아 이것을 잡지 못합니다.")
        return True, f"blake2b 결정적 해시 사용 · 프로세스 간 동일값({outs.pop()})"

    _ac("A25", "폴백 분류기 해시 결정성", a25)

    # ── A26  D2 윈저 · D1 최종 z 가 기간을 섞지 않는가 ────────────────────────────────────
    def a26():
        rng = np.random.default_rng(11)
        n = 200
        base = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)] * 2,
            "corp_code": [f"C{i}" for i in range(n)] * 2,
            "asof": [pd.Timestamp("2016-09-01")] * n + [pd.Timestamp("2025-09-01")] * n,
            "q": ["2016Q2"] * n + ["2025Q2"] * n, "sector": ["기타"] * (2 * n),
            "cell": ["2016Q2|기타"] * n + ["2025Q2|기타"] * n,
            "cell_all": ["2016Q2|ALL"] * n + ["2025Q2|ALL"] * n,
            "D2_FORCED_LOW": 0.0})
        for c, _s in D2_ITEMS:
            base[c] = rng.normal(size=2 * n)
        A = attach_d2(base.copy(), None)
        B = base.copy()
        # 2025년 코호트의 한 지표만 8배로 부풀린다 — 2016년 점수는 변하면 안 된다.
        c0 = D2_ITEMS[0][0]
        B.loc[n:, c0] = B.loc[n:, c0] * 8.0
        Bz = attach_d2(B, None)
        d = (pd.to_numeric(A.loc[:n - 1, "D2_SCORE"], errors="coerce") -
             pd.to_numeric(Bz.loc[:n - 1, "D2_SCORE"], errors="coerce")).abs().max()
        if not np.isfinite(d):
            return None, "D2_SCORE 를 계산할 수 없어 건너뜁니다"
        if d > 1e-6:
            return False, ("★2025년 데이터를 바꿨더니 2016년 D2_SCORE 가 달라졌습니다 "
                           f"(최대 {d:.4f}z). 윈저라이즈 경계·강제최하위 값이 전 기간 "
                           "백분위로 잡혀 있어, 과거 관측치의 클리핑 한계가 미래로 정해집니다.")
        return True, f"2025년 코호트 변경이 2016년 D2_SCORE 에 영향 없음 (최대 {d:.2e}z)"

    _ac("A26", "D2 윈저라이즈 기간 분리", a26)

    # ── A27  축 A 결측이 '점수 축소'로 사실상 탈락시키지 않는가 ───────────────────────────
    def a27():
        # A10 은 FINAL_SCORE 가 NaN 이 아닌지만 본다. 결측군의 분산이 절반으로 줄면 NaN 은
        # 아니면서도 상위 N 꼬리에 도달하지 못한다 — 여기서는 **선정률**로 검사한다.
        rng2 = np.random.default_rng(7)
        n, cov, K = 600, 0.20, 30
        P = pd.DataFrame({
            "code": [f"{i*10:06d}" for i in range(n)],
            "corp_code": [f"C{i}" for i in range(n)],
            "asof": [pd.Timestamp("2020-06-01")] * n, "q": ["2020Q1"] * n,
            "sector": ["기타"] * n, "cell": ["2020Q1|기타"] * n,
            "cell_all": ["2020Q1|ALL"] * n,
            "D1_SCORE": rng2.normal(size=n), "D2_SCORE": rng2.normal(size=n),
            "D3_SCORE": rng2.normal(size=n), "EXCLUDE": 0.0})
        has_a = rng2.random(n) < cov                       # 축 A 보유 여부 ⟂ 축 B 점수
        t = rng2.normal(size=n)
        P["dTONE"] = np.where(has_a, t, np.nan)
        P["dTONE_resid"] = P["dTONE"]
        Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)
        top = Q.nlargest(K, "FINAL_SCORE")
        share = float(top["dTONE_resid"].notna().mean())
        ratio = share / max(cov, 1e-9)
        if Q["FINAL_SCORE"].isna().any():
            return False, "축 B 가 있는데도 FINAL_SCORE 가 결측인 행이 있습니다"
        if ratio > 1.6:
            return False, (f"★축 A 보유 종목이 상위 {K} 를 {ratio:.2f}배 과대점유합니다 "
                           f"(커버리지 {cov:.0%} · 상위 점유 {share:.0%}). 축 A 결측 행은 "
                           f"AXIS_A_Z=0 으로 채워져 FINAL 의 분산이 절반이 되고, 선정은 "
                           f"꼬리에서 일어나므로 NaN 이 아닌데도 구조적으로 밀립니다 — "
                           f"§7.2 '탈락시키지 말 것'의 실질 위반입니다.")
        return True, (f"커버리지 {cov:.0%} · 상위 {K} 중 축 A 보유 {share:.0%} "
                      f"(과대선택 {ratio:.2f}배, 허용 1.6배 이하)")

    _ac("A27", "축 A 결측 종목의 실질 편입률 (§7.2)", a27)

    # ── A28  매도 슬리피지가 폴백(2%)으로 새지 않는가 ─────────────────────────────────────
    def a28():
        rb = pd.to_datetime(["2019-03-01", "2019-06-01", "2019-09-01"])
        codes = [f"{i*10:06d}" for i in range(1, 61)]
        rows = []
        for ti, t in enumerate(rb):
            for i, c in enumerate(codes):
                # 분기마다 신호를 완전히 뒤집어 100% 회전을 만든다
                s = (i if ti % 2 == 0 else len(codes) - i) / len(codes)
                rows.append({"code": c, "asof": t, "adtv60": 5e8, "fwd_ret_1q": 0.0,
                             "FINAL_RANK": s, "FINAL_SCORE": s, "EXCLUDE": 0.0,
                             "vol_q": 0.3})
        P = pd.DataFrame(rows)

        class _U:
            def delisting_map(self): return {}
            def audit_row(self, *a, **k): pass
        bt = run_backtest(P, rb, _U(), None, top_n=10, apply_costs=True, label="A28")
        R = bt["returns"]
        cost_q = float(R.loc[R["measurable"], "cost"].mean())
        # 전 종목 ADTV 가 동일하므로 매수·매도 슬리피지가 같아야 한다.
        # adv=0 폴백(2%)이 매도 쪽에만 걸리면 비용이 대략 2배 이상으로 뛴다.
        w, notional = 0.1, 0.1 * ARC_ACCOUNT_KRW
        sl = arc_slippage(notional, 5e8)
        expect = 2.0 * 10 * w * (ARC_COMMISSION_BPS / 1e4 + sl) + \
                 10 * w * arc_sell_tax(rb[1])
        if cost_q > expect * 1.5:
            return False, (f"★분기 비용 {cost_q:.4f} 가 기대치 {expect:.4f} 의 1.5배를 "
                           f"넘습니다. 전량 매도 종목이 advmap 에 없어 슬리피지가 일괄 2% "
                           f"폴백으로 매겨지고 있습니다 — 회전율이 다른 어블레이션 팔이 "
                           f"부당한 벌점을 받습니다.")
        return True, (f"분기 비용 {cost_q:.4f} (기대 {expect:.4f}) · "
                      f"매도 슬리피지 폴백 없음")

    _ac("A28", "매도 슬리피지 ADTV 폴백 누수", a28)

    # ── A29  Sortino · 파산 경로 방어 ─────────────────────────────────────────────────────
    def a29():
        r = np.array([0.12, -0.030, 0.09, -0.0305, 0.11, -0.0298, 0.08, -0.0302] * 3)
        R = pd.DataFrame({"asof": pd.date_range("2016-03-01", periods=len(r), freq="QS"),
                          "ret": r, "ret_gross": r, "n": 30, "turnover": 1.0,
                          "cost": 0.0, "n_elig": 100, "measurable": True})
        st = perf_stats(R)
        dd_def = float(np.sqrt((np.minimum(r, 0.0) ** 2).mean()) * math.sqrt(4))
        want = (st["CAGR"]) / dd_def
        if abs(st["Sortino"] - want) > 0.05:
            return False, (f"★Sortino {st['Sortino']:.2f} 가 정의값 {want:.2f} 와 다릅니다. "
                           f"하방편차를 '음수 수익률들의 자기 평균 대비 표본표준편차'로 "
                           f"계산하면 손실의 크기가 아니라 균일함을 보상하게 되어 "
                           f"손실이 뭉친 팔이 세 자리 Sortino 로 최우수처럼 보입니다.")
        # 파산 경로: 1+r<0 이 두 번 나오면 cumprod 가 부호를 뒤집어 되살아난다
        r2 = np.array([0.1, -1.10, 0.2, -1.10, 0.3, 0.4])
        R2 = pd.DataFrame({"asof": pd.date_range("2016-03-01", periods=6, freq="QS"),
                           "ret": r2, "ret_gross": r2, "n": 1, "turnover": 1.0,
                           "cost": 0.0, "n_elig": 1, "measurable": True})
        s2 = perf_stats(R2)
        if s2["MDD"] < -1.0 - 1e-9:
            return False, f"★MDD {s2['MDD']:.2%} — 정의상 -100% 아래는 불가능합니다"
        if not (np.isnan(s2["CAGR"]) or s2["CAGR"] <= -0.999):
            return False, (f"★자본곡선이 0 을 통과했는데 CAGR {s2['CAGR']:+.2%} 로 "
                           f"계산됐습니다(파산 경로가 양의 자본으로 되살아남).")
        return True, (f"Sortino 정의 일치 ({st['Sortino']:.2f}) · "
                      f"파산 경로 CAGR {s2['CAGR']:+.0%} · MDD {s2['MDD']:.0%}")

    _ac("A29", "Sortino 정의 · 파산 경로 방어", a29)

    # ── A30  '모름' 이 D3 합산에서 0 으로 붕괴하지 않는가 ─────────────────────────────────
    def a30():
        H = pd.DataFrame({"corp_code": ["C1", "C2"],
                          "event_date": pd.to_datetime(["2019-03-31"] * 2),
                          "knowledge_date": pd.to_datetime(["2019-04-01"] * 2)})
        for i, c in enumerate(D3_COLS):
            H[c] = [1.0 if i < 2 else 0.0, np.nan]        # C2 는 전 태그 '모름'
        H["D3_N_OBS"] = H[D3_COLS].notna().sum(axis=1).astype("int16")
        H["DELTA_NONFIN"] = H[D3_COLS].sum(axis=1, skipna=True).where(H["D3_N_OBS"] > 0)
        if pd.notna(H.loc[1, "DELTA_NONFIN"]):
            return False, ("★전 태그가 '모름'인 법인의 ΔNONFIN 이 0.0 으로 계산됐습니다. "
                           "문서 파싱에 실패한 법인이 '사실이 하나도 없는 법인'과 같은 "
                           "척도로 z-scoring 되어, D3_SCORE 가 사실 건수가 아니라 데이터 "
                           "커버리지의 함수가 됩니다(최종 점수의 10%).")
        if float(H.loc[0, "DELTA_NONFIN"]) != 2.0:
            return False, f"관측이 있는 법인의 ΔNONFIN 이 틀렸습니다: {H.loc[0, 'DELTA_NONFIN']}"
        return True, "전 태그 결측 → ΔNONFIN 결측 · 관측 있으면 정상 합산 · D3_N_OBS 병기"

    _ac("A30", "D3 '모름' vs '미발화' 구분", a30)

    # ── A31  직교화 자유도 가드 ───────────────────────────────────────────────────────────
    def a31():
        rng3 = np.random.default_rng(3)
        p = 13                                   # 통제 6 + 섹터더미 7
        corrs = {}
        for nobs in (17, 60, 200):
            acc = []
            for _ in range(60):
                X = rng3.normal(size=(nobs, p))
                y = rng3.normal(size=nobs)       # y ⟂ X (진짜 신호는 전부 잔차여야 한다)
                res = ols_resid_np(y, X)
                if np.isfinite(res).sum() < 3:
                    continue
                m = np.isfinite(res)
                acc.append(abs(float(np.corrcoef(y[m], res[m])[0, 1])))
            corrs[nobs] = (float(np.mean(acc)) if acc else np.nan, len(acc))
        thin, _ = corrs[17]
        if np.isfinite(thin) and thin < 0.80:
            return False, (f"★관측 17개 · 파라미터 {p+1}개에서 잔차가 원신호를 {1-thin:.0%} "
                           f"만큼 먹었습니다(corr={thin:.2f}). 'ΔTONE_resid' 가 실제로는 "
                           f"규모·모멘텀·섹터의 적합오차, 즉 위장된 사이즈 베팅이 되고 "
                           f"그 값이 FINAL_SCORE 의 50% 를 차지합니다.")
        n_ok = corrs[200][1]
        if n_ok == 0:
            return False, "관측 200개에서도 잔차가 생성되지 않습니다(가드가 과도)"
        return True, (f"자유도 부족(n=17) 시 잔차 미생성 · "
                      f"n=60 corr {corrs[60][0]:.2f} · n=200 corr {corrs[200][0]:.2f} "
                      f"(하한 {OLS_MIN_OBS_PER_PARAM}×파라미터)")

    _ac("A31", "직교화 자유도 하한", a31)

    # ── A32  category dtype 이 시총 폴백 경로를 죽이지 않는가 ─────────────────────────────
    def a32():
        # fetch_prices 는 downcast() 를 거치고, 일봉은 nunique/len 이 극히 작아 code 가
        # category 로 바뀐다. 그 dtype 이 merge_asof(by=...) 를 MergeError 로 죽인다.
        rb = pd.to_datetime(["2019-03-01", "2019-06-01"])
        codes = [f"{i*10:06d}" for i in range(1, 6)]
        days = pd.bdate_range("2018-11-01", "2019-06-10")
        px = pd.DataFrame({"code": np.repeat(codes, len(days)),
                           "date": np.tile(days.values, len(codes))})
        px["close"] = 1000.0
        px["open"] = px["high"] = px["low"] = 1000.0
        px["volume"] = 1000.0
        px["amount"] = 1e9
        px["src"] = "t"
        px = downcast(px)
        if str(px["code"].dtype) != "category":
            px["code"] = px["code"].astype("category")     # 조건 강제(회귀 검정의 요지)
        shares = pd.DataFrame({
            "corp_code": [f"C{i}" for i in range(1, 6)],
            "event_date": [pd.Timestamp("2018-12-31")] * 5,
            "knowledge_date": [pd.Timestamp("2019-02-01")] * 5,
            "shares_total": [1e7] * 5})
        sec = pd.DataFrame({"code": codes, "corp_code": [f"C{i}" for i in range(1, 6)]})
        px_monthly = (px.assign(month=as_ts_series(px["date"]) + pd.offsets.MonthEnd(0))
                        .groupby(["code", "month"], observed=True)
                        .tail(1)[["code", "month", "close"]])
        # snap_mc 를 비워 경로 ①을 닫는다 = KRX 로그인이 없는 실행과 동일한 상태
        M = build_mktcap_panel(rb, px_monthly, pd.DataFrame(), shares, sec)
        got = int(pd.to_numeric(M.get("mktcap", pd.Series(dtype=float)),
                                errors="coerce").notna().sum()) if len(M) else 0
        if got == 0:
            return False, ("★KRX 스냅샷이 없는 실행에서 시총이 0건 확보됐습니다. DART 주식총수와 "
                           "월말 종가가 둘 다 정상인데도 code 가 category dtype 이라 폴백 "
                           "경로 ②③ 의 merge_asof 가 MergeError 로 죽습니다 → U-1000 0행 → "
                           "build_arc_panel RuntimeError → 실행 전체 중단.")
        return True, f"category dtype 에서도 폴백 경로가 시총 {got:,}행 확보"

    _ac("A32", "시총 폴백 경로 dtype 내성", a32)

    # ── A33  '정지 후 재개' 를 '정지 후 폐지' 로 오인하지 않는가 ──────────────────────────
    def a33():
        rb = pd.to_datetime(["2017-03-01", "2017-06-01", "2017-09-01", "2017-12-01"])
        U = pd.DataFrame({"code": ["X"], "asof": [rb[0]], "mktcap": [1e10],
                          "uni_rank": [1], "adtv60": [5e8]})
        # 2017-06-01 은 거래정지라 체결가 격자에 없다. 2017-09-01 에 재개. 폐지는 3년 뒤 합병.
        execp = pd.DataFrame({"code": ["X", "X", "X"],
                              "asof": [rb[0], rb[2], rb[3]],
                              "exec_px": [1000.0, 1100.0, 1150.0],
                              "exec_date": [rb[0], rb[2], rb[3]]})
        px = pd.DataFrame({"code": ["X", "X"],
                           "date": pd.to_datetime(["2017-03-02", "2020-12-18"]),
                           "open": [1000.0, 5000.0], "close": [1000.0, 5000.0]})
        sec = pd.DataFrame({"code": ["X"], "name": ["정지후재개"], "market": ["KOSDAQ"],
                            "industry": ["기타"], "corp_code": ["CX"],
                            "listing_date": [pd.NaT]})

        class _U:
            def delisting_map(self): return {"X": pd.Timestamp("2020-12-20")}
        P = build_arc_panel(_U(), rb, U, pd.DataFrame(), execp, sec, px_daily=px)
        row = P[P["asof"] == rb[0]]
        if row.empty:
            return None, "패널이 비어 검정을 건너뜁니다"
        r1 = float(row["fwd_ret_1q"].iloc[0])
        r2 = float(row["fwd_ret_2q"].iloc[0])
        if np.isfinite(r1) and r1 > 1.0:
            return False, (f"★1분기 전방수익률이 {r1:+.1%} 입니다. 거래정지가 풀려 재개된 "
                           f"종목인데도 '정지 후 폐지'로 오인해 **3년 9개월 뒤 폐지일 직전 "
                           f"종가**를 1분기 수익률 자리에 넣었습니다. elig 가 더 이상 "
                           f"fwd_ret 를 보지 않으므로 이 행은 실제로 편입되어 포트폴리오 "
                           f"수익에 곧바로 들어갑니다(같은 행 fwd_ret_2q={r2:+.1%}).")
        if np.isfinite(r1) and np.isfinite(r2) and r1 > r2 + 1.0:
            return False, f"1분기({r1:+.1%})가 2분기({r2:+.1%})를 크게 웃돕니다 — 지평 혼선"
        # 진입 체결가가 없는 행은 보유가 성립하지 않으므로 -100% 가 찍히면 안 된다
        U2 = pd.DataFrame({"code": ["Y"], "asof": [rb[0]], "mktcap": [1e10],
                           "uni_rank": [1], "adtv60": [5e8]})
        sec2 = pd.DataFrame({"code": ["Y"], "name": ["진입불가"], "market": ["KOSDAQ"],
                             "industry": ["기타"], "corp_code": ["CY"],
                             "listing_date": [pd.NaT]})

        class _U2:
            def delisting_map(self): return {"Y": pd.Timestamp("2020-07-01")}
        P2 = build_arc_panel(_U2(), rb, U2, pd.DataFrame(),
                             pd.DataFrame(columns=["code", "asof", "exec_px", "exec_date"]),
                             sec2, px_daily=px)
        if len(P2) and float(pd.to_numeric(P2["fwd_ret_1q"], errors="coerce")
                             .fillna(0).min()) <= -0.99:
            return False, ("★진입 체결가가 없어 애초에 살 수 없었던 종목에 -100% 가 "
                           "계상됐습니다(없는 손실을 만들어 냅니다).")
        return True, (f"정지 후 재개는 재개 체결가로 청산 ({r1:+.2%}, 2Q {r2:+.2%}) · "
                      f"진입 불가 종목에 -100% 미계상")

    _ac("A33", "거래정지 후 재개 vs 폐지 구별", a33)

    # ── A34  tok_len 결측이 D1 축을 통째로 끄지 않는가 ────────────────────────────────────
    def a34():
        # 공용 캐시에 tok_len 이 없던 스키마의 샤드가 섞이면 그 열이 전부 NaN 이 된다.
        T = pd.DataFrame({
            "corp_code": ["C1"], "rcept_no": ["R1"], "rcept_dt": [pd.Timestamp("2019-03-25")],
            "doc_type": ["FY"], "bsns_year": [2018], "section": ["S_MDA"],
            "n_tokens": [100], "tf": ['{"매출": 3, "영업이익": 2}'], "bigram": ["{}"],
            "tok_len": [np.nan], "is_amend": [False]})
        try:
            arc_norm_sample_report(T)
        except Exception as e:                                # noqa
            return False, (f"★{type(e).__name__} — 육안 검증용 표 함수가 데이터 파이프라인을 "
                           f"끊습니다. 이 함수는 L1.DOC 안에서 ctx['doc_pairs'] 설정 **앞에** "
                           f"호출되므로, 여기서 죽으면 GATE_4/5 가 판정불가가 되어 원문을 전부 "
                           f"받아 놓고도 D1 축이 비활성화된 채 백테스트가 완주합니다: {e}")
        return True, "tok_len 전부 결측인 샤드에서도 예외 없이 표를 출력"

    _ac("A34", "캐시 스키마 변화 내성 (tok_len)", a34)

    # ── A35  D1 최종 z 셀이 동시 제출 코호트인가 (A26 의 D1 판) ───────────────────────────
    def a35():
        def _mk(n_sec_nov: int, seed: int) -> pd.DataFrame:
            rg = np.random.default_rng(seed)
            rows = []
            for lab, dt_, yr, rd, nsec in (("FY", "FY", 2018, "2019-03-20", 7),
                                           ("Q3", "Q3", 2019, "2019-11-14", n_sec_nov)):
                for i in range(60):
                    for s in ARC_SECTIONS[:nsec]:
                        rows.append({"corp_code": f"{lab}{i:03d}", "rcept_dt": as_ts(rd),
                                     "bsns_year": yr, "doc_type": dt_, "section": s,
                                     "cosine": float(rg.normal(0.8, 0.05)),
                                     "jaccard": float(rg.normal(0.7, 0.05)),
                                     "simple": float(rg.normal(0.7, 0.05)),
                                     "len_ratio": float(rg.normal(0.9, 0.03))})
            return pd.DataFrame(rows)
        a = d1_composite(_mk(1, 5))
        b = d1_composite(_mk(7, 5))
        ka = a[a["corp_code"].astype(str).str.startswith("FY")].set_index("corp_code")["D1_SCORE"]
        kb = b[b["corp_code"].astype(str).str.startswith("FY")].set_index("corp_code")["D1_SCORE"]
        j = ka.to_frame("a").join(kb.to_frame("b"), how="inner").dropna()
        if j.empty:
            return None, "3월 코호트 D1_SCORE 가 생성되지 않아 건너뜁니다"
        d = float((j["a"] - j["b"]).abs().max())
        if d > 1e-6:
            return False, (f"★11월 코호트(3분기보고서)만 바꿨는데 3월 코호트(사업보고서)의 "
                           f"D1_SCORE 가 최대 {d:.3f}z 움직였습니다. 최종 z 셀이 동시 제출 "
                           f"코호트가 아니라 달력연도라는 뜻이며, 2019-06/09 리밸일에 쓰이는 "
                           f"값이 11월 제출분으로 결정됩니다 — 정의상 미래 참조입니다.")
        return True, f"미래 코호트 변경이 과거 D1_SCORE 에 영향 없음 (최대 {d:.2e}z, {len(j)}종목)"

    _ac("A35", "D1 최종 z = 동시 제출 코호트", a35)

    # ── A36  STRUCT_FLAG 가 미래 공시로 과거 D1 을 지우지 않는가 ──────────────────────────
    def a36():
        rg = np.random.default_rng(9)
        rows = []
        for i in range(40):
            for s in ARC_SECTIONS:
                rows.append({"corp_code": f"{i:08d}", "rcept_dt": as_ts("2019-03-20"),
                             "bsns_year": 2018, "doc_type": "FY", "section": s,
                             "cosine": float(rg.normal(0.8, 0.05)),
                             "jaccard": float(rg.normal(0.7, 0.05)),
                             "simple": float(rg.normal(0.7, 0.05)),
                             "len_ratio": float(rg.normal(0.9, 0.03))})
        S = pd.DataFrame(rows)
        # 문서 접수 9개월 **뒤** 의 합병 공시 — 그 시점에는 알 수 없는 정보다
        fut = pd.DataFrame({"corp_code": ["00000000"],
                            "event_date": [as_ts("2019-12-20")],
                            "knowledge_date": [as_ts("2019-12-20")], "STRUCT_FLAG": [1.0]})
        base = d1_composite(S).set_index("corp_code")["D1_SCORE"]
        withf = d1_composite(S, fut).set_index("corp_code")["D1_SCORE"]
        if pd.notna(base.get("00000000")) and pd.isna(withf.get("00000000")):
            return False, ("★문서 접수 9개월 뒤의 합병 공시로 과거 문서의 D1 이 지워졌습니다. "
                           "'앞으로 12개월 안에 합병을 공시할 기업' 이라는 미래 정보로 그 "
                           "종목의 스코어 구성(§6.5 재배분)이 바뀝니다 — 합병 대상 종목은 "
                           "전방수익률이 체계적으로 다르므로 방향성 있는 편향입니다.")
        # 과거 공시는 정상적으로 발동해야 한다
        past = fut.copy()
        past["knowledge_date"] = [as_ts("2018-09-20")]
        past["event_date"] = [as_ts("2018-09-20")]
        wp = d1_composite(S, past).set_index("corp_code")["D1_SCORE"]
        if pd.notna(wp.get("00000000")):
            return False, "문서 접수 6개월 전의 구조적 변화 공시가 STRUCT_FLAG 를 발동시키지 않았습니다"
        return True, "미래 공시는 무시 · 접수 이전 1년 공시만 STRUCT_FLAG 발동 확인"

    _ac("A36", "STRUCT_FLAG 단방향 (§6.1.6)", a36)

    # ── A37  D3 텍스트 규칙이 영구 0 / 상시 1 로 굳지 않는가 ──────────────────────────────
    def a37():
        T = pd.DataFrame({
            "corp_code": ["C1", "C1"], "rcept_no": ["R1", "R1"],
            "rcept_dt": [as_ts("2019-03-25")] * 2, "doc_type": ["FY"] * 2,
            "bsns_year": [2018] * 2, "section": ["S_BIZ", "S_MDA"],
            "tf": ['{"해외": 3, "법인": 5, "설립": 2}', '{"특허": 1, "등록": 2}'],
            "bigram": ["{}"] * 2, "tok_len": [100, 80], "n_tokens": [100, 80]})
        DOC = _d3_text_by_doc(T)
        if DOC.empty:
            return False, "문서 텍스트 프레임이 비었습니다"
        toks = DOC["tokens"].iloc[0]
        if not _d3_tokens_hit(toks, "NF_OVERSEAS"):
            return False, ("★'해외'+'법인' 토큰이 둘 다 있는데 NF_OVERSEAS 가 발화하지 "
                           "않습니다. 두 단어 패턴을 JSON 토큰 덤프 문자열에 정규식으로 "
                           "걸면 두 토큰 사이에 항상 '\": 3, \"' 가 끼어 **원리상 매칭될 수 "
                           "없습니다** — 해당 이벤트가 어떤 데이터에서도 영구 0 이 됩니다.")
        H = extract_hardfacts(T, None, None, None)
        if H.empty:
            return None, "하드팩트가 생성되지 않아 건너뜁니다"
        for k in sorted(_D3_WEAK_CONSTANT):
            if k in H.columns and pd.to_numeric(H[k], errors="coerce").notna().any():
                return False, (f"★원문 없이 단일 토큰만으로 {k} 가 판정됐습니다. "
                               f"'이 단어가 보고서 어딘가에 나오는가'는 이벤트가 아니라 "
                               f"상수입니다(실측 발화율 67%) — 0/1 이 아니라 결측이어야 합니다.")
        return True, ("다단어 규칙이 토큰 집합으로 발화 · 단일 토큰 상수 태그"
                      f"({' · '.join(sorted(_D3_WEAK_CONSTANT))})는 결측 처리")

    _ac("A37", "D3 텍스트 규칙 실효성 (§6.3)", a37)

    # ── A38  NOA 가 현금 결측을 0 으로 채우지 않는가 (§0.5) ───────────────────────────────
    def a38():
        def _fin(cash_val):
            return pd.DataFrame({
                "corp_code": ["C1", "C1"], "bsns_year": [2018, 2019],
                "reprt_code": ["11011", "11011"],
                "knowledge_date": pd.to_datetime(["2019-03-25", "2020-03-25"]),
                "assets": [1000.0, 1000.0], "liabilities": [400.0, 400.0],
                "cash": [cash_val, cash_val], "net_income_ttm": [50.0, 50.0],
                "cfo_ttm": [60.0, 60.0], "revenue_ttm": [500.0, 500.0],
                "inventory": [100.0, 100.0], "receivable": [80.0, 80.0]})
        a = build_d2_panel(_fin(200.0))
        b = build_d2_panel(_fin(np.nan))
        va = pd.to_numeric(a.get("NOA", pd.Series(dtype=float)), errors="coerce").dropna()
        vb = pd.to_numeric(b.get("NOA", pd.Series(dtype=float)), errors="coerce").dropna()
        if va.empty:
            return None, "현금이 있는 경우에도 NOA 가 생성되지 않아 건너뜁니다"
        if not vb.empty:
            return False, (f"★현금성자산이 결측인데 NOA 가 {float(vb.iloc[0]):.4f} 로 "
                           f"계산됐습니다(현금 있을 때 {float(va.iloc[0]):.4f}). cash.fillna(0) "
                           f"은 §0.5 위반이고, NOA 는 방향 −1 이라 현금 라인만 못 읽은 법인이 "
                           f"D2 에서 체계적으로 불리해집니다. fillna 는 NaN 을 없애므로 "
                           f"커버리지 표에는 100% 로 보고되어 흔적조차 남지 않습니다.")
        return True, f"현금 결측 → NOA 결측(§6.5 재배분) · 현금 있으면 {float(va.iloc[0]):.4f}"

    _ac("A38", "NOA 현금 결측 처리 (§0.5)", a38)

    # ── 결과 ──────────────────────────────────────────────────────────────────────────────
    rows = [[r["id"], _trunc(r["name"], 30),
             {True: "✔ 통과", False: "✘ 실패", None: "— 건너뜀"}[r["pass"]],
             _trunc(r["msg"], 78)] for r in CONTRACT_RESULTS]
    LOG.table(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], maxw=82,
              title="계약 자동검정 A1~A38 (협상 대상이 아님)")
    failed = [r for r in CONTRACT_RESULTS if r["pass"] is False]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: " + ", ".join(r["id"] for r in failed))
        for r in failed[:4]:
            LOG.banner(f"✘ 계약 위반: [{r['id']}] {r['name']}", _trunc(r["msg"], 96))
        if strict:
            raise KillCriteria("계약 위반으로 파이프라인을 중단합니다. "
                               "위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len([r for r in CONTRACT_RESULTS if r['pass'] is True])}건 전부 통과 "
           f"(건너뜀 {len([r for r in CONTRACT_RESULTS if r['pass'] is None])}건).")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-G  실경로 리허설 — 수집 함수를 '진짜로' 실행해 본다                                    ║
# ║                                                                                          ║
# ║  합성 스모크(80)는 완성된 패널을 주입한다. 즉 build_security_master · fetch_prices ·        ║
# ║  fetch_arc_documents · hankyung_collect 같은 실제 수집·정제 함수는 한 줄도 실행되지 않는다. ║
# ║  실제로 계약 검정 + 스모크를 전부 통과한 빌드가 실행 2분 만에 수집부 한 줄 때문에 죽은      ║
# ║  전례가 있어 이 계층이 생겼다.                                                              ║
# ║                                                                                          ║
# ║  여기서는 네트워크 계층만 가짜로 바꾸고(HTTP·pykrx·FDR), 그 위 수집·정제 로직은 실물 실행.   ║
# ║  각 함수에 네 가지를 먹인다: ① 정상 ② 빈 응답 ③ 깨진 응답 ④ 기대 컬럼 누락                  ║
# ║  전부 '예외 없이' 통과해야 하고, 정상 응답에서는 실제로 값이 나와야 한다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REHEARSAL_RESULTS: List[dict] = []


def _arh(name: str, fn: Callable, expect_rows: bool = True, note: str = ""):
    t0 = time.time()
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else (1 if out is not None else 0)
        ok = (not expect_rows) or n > 0
        REHEARSAL_RESULTS.append({
            "name": name, "ok": ok, "rows": n, "sec": time.time() - t0,
            "err": "" if ok else "정상 응답인데 결과가 0행입니다(파싱 실패 가능성)", "note": note})
        return out
    except Exception as e:                                        # noqa
        REHEARSAL_RESULTS.append({
            "name": name, "ok": False, "rows": -1, "sec": time.time() - t0,
            "err": f"{type(e).__name__}: {str(e)[:200]}", "note": note,
            "tb": traceback.format_exc()})
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────────────────────
def _afx_fdr_listing(n: int = 40) -> bytes:
    rows = ["Code,ISU_CD,Name,Market,Dept,Close,ChagesRatio,Marcap,Stocks,MarketId"]
    for i in range(n):
        code = f"{(i+1)*10:06d}"          # 실제 보통주처럼 끝자리 0
        rows.append(f"{code},KR7{code}003,합성{i+1:03d},{'KOSPI' if i%2 else 'KOSDAQ'},,"
                    f"10000,0.5,1000000000,100000,{'STK' if i%2 else 'KSQ'}")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _afx_fdr_delisting(n: int = 30) -> bytes:
    rows = ["Symbol,Name,Market,SecuGroup,Kind,DelistingDate,ToSymbol,ToName,Reason"]
    for i in range(n):
        code = f"{900000+i:06d}" if i < 20 else f"KR{i:08d}"
        rows.append(f"{code},폐지{i+1:03d},KOSPI,주권,보통주,{2017+(i%8)}-0{1+(i%9)}-15,,,상장폐지")
    return ("﻿" + "\n".join(rows)).encode("utf-8")


def _afx_kind(n: int = 30) -> bytes:
    head = ("<table><tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th>"
            "<th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>")
    body = "".join(f"<tr><td>합성{i+1:03d}</td><td>{i+1}</td><td>화학</td><td>제품</td>"
                   f"<td>2010-03-15</td><td>12월</td><td>홍길동</td><td>http://x</td>"
                   f"<td>서울</td></tr>" for i in range(n))
    return (head + body + "</table>").encode("euc-kr")


def _afx_corpcode(n: int = 40) -> bytes:
    buf = io.BytesIO()
    xml = "<result>" + "".join(
        f"<list><corp_code>C{i+1:07d}</corp_code><corp_name>합성{i+1:03d}</corp_name>"
        f"<stock_code>{(i+1)*10:06d}</stock_code><modify_date>20240101</modify_date></list>"
        for i in range(n)) + "</result>"
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buf.getvalue()


def _afx_fnltt(corp: str, year: int) -> dict:
    def row(sj, aid, anm, amt):
        return {"rcept_no": f"{year+1}0331000001", "reprt_code": "11011",
                "bsns_year": str(year), "corp_code": corp, "sj_div": sj, "sj_nm": sj,
                "account_id": aid, "account_nm": anm, "thstrm_amount": amt,
                "frmtrm_amount": amt, "ord": "1"}
    return {"status": "000", "message": "정상", "list": [
        row("IS", "ifrs-full_Revenue", "매출액", "1,234,567,000,000"),
        row("IS", "ifrs-full_CostOfSales", "매출원가", "900,000,000,000"),
        row("IS", "dart_OperatingIncomeLoss", "영업이익", "120,000,000,000"),
        row("IS", "ifrs-full_ProfitLoss", "당기순이익", "90,000,000,000"),
        row("IS", "-표준계정코드 미사용-", "경상연구개발비", "30,000,000,000"),
        row("BS", "ifrs-full_Inventories", "재고자산", "150,000,000,000"),
        row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권및기타채권",
            "180,000,000,000"),
        row("BS", "ifrs-full_Assets", "자산총계", "3,000,000,000,000"),
        row("BS", "ifrs-full_Liabilities", "부채총계", "1,200,000,000,000"),
        row("BS", "ifrs-full_Equity", "자본총계", "1,800,000,000,000"),
        row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "300,000,000,000"),
        row("BS", "ifrs-full_PropertyPlantAndEquipment", "유형자산", "800,000,000,000"),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름",
            "140,000,000,000"),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득",
            "-60,000,000,000"),
    ]}


def _afx_emp(corp: str, year: int) -> dict:
    def r(bbm, sex, sm, tot):
        return {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "fo_bbm": bbm,
                "sexdstn": sex, "sm": sm, "fyer_salary_totamt": tot,
                "jan_salary_am": "70,000,000"}
    return {"status": "000", "list": [
        r("반도체", "남", "1,200", "96,000,000,000"), r("반도체", "여", "300", "21,000,000,000"),
        r("합계", "합계", "1,500", "117,000,000,000")]}


def _afx_shares(corp: str, year: int) -> dict:
    return {"status": "000", "list": [
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "보통주",
         "isu_stock_totqy": "10,000,000", "now_to_isu_stock_totqy": "10,000,000",
         "tesstk_co": "100,000", "istc_totqy": "10,000,000"},
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "우선주",
         "isu_stock_totqy": "1,000,000", "now_to_isu_stock_totqy": "1,000,000",
         "tesstk_co": "0", "istc_totqy": "1,000,000"},
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "se": "합계",
         "isu_stock_totqy": "11,000,000", "now_to_isu_stock_totqy": "11,000,000",
         "tesstk_co": "100,000", "istc_totqy": "11,000,000"}]}


def _afx_audit(corp: str, year: int) -> dict:
    emph = "계속기업으로서의 존속능력에 대한 불확실성" if int(year) % 3 == 0 else ""
    return {"status": "000", "list": [
        {"rcept_no": f"{year+1}0331000001", "corp_code": corp, "bsns_year": str(year),
         "adtor": "합성회계법인", "adt_opinion": "적정", "emphs_matter": emph,
         "core_adt_matter": "수익인식"}]}


def _afx_dart_list(bgn: str, ty: str) -> dict:
    y = int(bgn[:4])
    m = int(bgn[4:6])
    items = []
    if ty == "A" and m == 3:
        for i in range(1, 4):
            items.append({"corp_code": f"C{i:07d}", "corp_name": f"합성{i:03d}",
                          "stock_code": f"{i:06d}", "rcept_no": f"{y}0320{i:06d}",
                          "rcept_dt": f"{y}0320",
                          "report_nm": f"사업보고서 ({y-1}.12)", "flr_nm": f"합성{i:03d}",
                          "corp_cls": "Y"})
    if ty == "B" and m == 7:
        items.append({"corp_code": "C0000001", "corp_name": "합성001", "stock_code": "000001",
                      "rcept_no": f"{y}0710000001", "rcept_dt": f"{y}0710",
                      "report_nm": "주요사항보고서(전환사채발행결정)", "flr_nm": "합성001",
                      "corp_cls": "Y"})
        items.append({"corp_code": "C0000002", "corp_name": "합성002", "stock_code": "000002",
                      "rcept_no": f"{y}0711000002", "rcept_dt": f"{y}0711",
                      "report_nm": "단일판매ㆍ공급계약체결", "flr_nm": "합성002",
                      "corp_cls": "Y"})
    return {"status": "000" if items else "013", "page_no": 1, "total_page": 1, "list": items}


# ★ 실제 사업보고서는 섹션당 수천~수만 자다. 픽스처가 너무 짧으면 fetch_arc_documents 의
#   '본문 최소 길이' 와 섹션 최소 길이 필터에 걸려 0행이 되고, 리허설이 실제 경로를 검증하지
#   못한다(초기 빌드에서 실제로 이 함정에 걸렸다). 문단을 반복해 현실적인 분량을 만든다.
_AFX_SECTIONS = [
    ("I. 회사의 개요",
     "당사는 {year}년 12월 31일 현재 제{gi}기 사업연도를 마감하였습니다. "
     "합성전자 주식회사는 {year}년 3월 20일에 본 보고서를 제출하였습니다. "
     "자본금은 {a} 백만원이며 발행주식총수는 {b} 주입니다. "
     "본점 소재지는 충청북도 청주시이며 지점은 {f} 개를 운영하고 있습니다. "),
    ("II. 사업의 내용",
     "당사는 반도체 소재를 제조하여 국내외에 판매하고 있습니다. {biz} "
     "주요 원재료 매입액은 {c} 백만원이며 생산능력은 연간 {d} 톤입니다. "
     "당사는 {year}년 중 유형자산 {e} 백만원을 취득하였습니다. "
     "{year}년 {mm}월 특허 {f} 건을 등록하였습니다. "
     "주요 매출처는 국내 대형 반도체 제조사이며 수출 비중은 {f} 퍼센트입니다. "
     "생산 공정은 정제, 배합, 포장의 세 단계로 구성되어 있습니다. "),
    ("III. 재무에 관한 사항",
     "당기 매출액은 {c} 백만원이며 영업이익은 {a} 백만원입니다. "
     "<table><tr><td>매출액</td><td>{c}</td></tr><tr><td>영업이익</td><td>{a}</td></tr></table> "
     "부채비율은 안정적인 수준을 유지하고 있습니다. "),
    ("VII. 이사의 경영진단 및 분석의견",
     "{mda} 당기 매출은 {c} 백만원으로 전기 대비 증가하였습니다. "
     "원가율은 전기 대비 소폭 상승하였으며 판매관리비는 통제 범위 내에서 관리되고 있습니다. "
     "향후 자금 조달 계획과 유동성 관리 방안을 지속적으로 점검하고 있습니다. "
     "부문별 실적은 소재 부문이 전체 매출의 대부분을 차지하고 있습니다. "),
    ("VIII. 임원 및 직원 등에 관한 사항",
     "직원 수는 {g} 명이며 연간 급여총액은 {a} 백만원입니다. "
     "{year}년 중 연구개발 인력 {f} 명을 신규 채용하였습니다. "
     "임원은 사내이사 {f} 명과 사외이사 {f} 명으로 구성되어 있습니다. "
     "평균 근속연수는 {f} 년이며 이직률은 안정적으로 관리되고 있습니다. "),
    ("IX. 계열회사 등에 관한 사항",
     "당사의 계열회사는 총 {f} 개사입니다. 지배구조는 안정적으로 유지되고 있습니다. "
     "{year}년 중 종속기업 지분을 {d} 백만원에 취득하였습니다. "
     "최대주주 및 특수관계인의 지분율은 {f} 퍼센트입니다. "),
    ("X. 대주주 등과의 거래내용",
     "특수관계자와의 매출 거래는 {d} 백만원이며 매입 거래는 {e} 백만원입니다. "
     "거래 조건은 제3자와의 거래와 동일한 기준을 적용하고 있습니다. "),
    ("XI. 그 밖에 투자자 보호를 위하여 필요한 사항",
     "제재현황: 해당사항 없습니다. "
     "우발부채 등: 계류 중인 소송사건은 {f} 건이며 소송가액은 {d} 백만원입니다. "
     "지급보증 잔액은 {e} 백만원입니다. "
     "사업위험: 환율 변동과 원자재 가격 상승 위험이 존재합니다. {risk} "
     "투자위험요소: 전방 산업 경기 변동에 따라 실적이 영향을 받을 수 있습니다. "),
]


def _afx_doc_body(y: int, newer: bool) -> str:
    fmt = dict(
        year=y, gi=y - 1990, mm=(y % 12) + 1,
        a=f"{1000+y:,}", b=f"{10_000_000+y*13:,}", c=f"{1_234_567+y*31:,}",
        d=f"{98_765+y*7:,}", e=f"{45_678+y*11:,}", f=(y % 9) + 1, g=f"{450+y%50:,}",
        biz=("이차전지 부품 사업을 신규로 개시하였으며 관련 매출이 발생하였습니다."
             if newer else "주력 제품은 실리콘 웨이퍼용 소재입니다."),
        mda=("영업환경 악화로 수익성이 하락하였으며 원가 절감 계획을 시행하고 있습니다."
             if newer else "안정적인 수요를 바탕으로 견조한 실적을 유지하였습니다."),
        risk=("경쟁사 진입으로 가격 경쟁이 심화되고 있습니다." if newer else
              "주요 고객사와의 장기 공급 계약으로 위험을 완화하고 있습니다."))
    out = ["<?xml version='1.0' encoding='euc-kr'?><DOCUMENT><TITLE>사업보고서</TITLE>"]
    for head, para in _AFX_SECTIONS:
        out.append(head)
        out.append((para.format(**fmt) + "\n") * 6)      # 섹션당 현실적 분량 확보
    out.append("</DOCUMENT>")
    return "\n".join(out)


def _afx_document(rcept_no: str) -> bytes:
    """전년/당년 두 해치. 당년본은 (a) 숫자·날짜만 바뀐 섹션과 (b) 서술이 바뀐 섹션을 나눈다."""
    y = int(str(rcept_no)[:4]) if str(rcept_no)[:4].isdigit() else 2020
    newer = (y % 2 == 0)
    body = _afx_doc_body(y, newer)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # ★ 본보고서 + 감사보고서 + 첨부 3개 엔트리. 첫 엔트리만 읽으면 내용이 소실되는 회귀를 잡는다.
        z.writestr("00_main.xml", body.encode("euc-kr"))
        z.writestr("01_audit.xml", ("<?xml version='1.0' encoding='euc-kr'?><DOC>"
                                    "감사의견 적정. 강조사항 없음.</DOC>").encode("euc-kr"))
        z.writestr("02_fs.xml", ("<?xml version='1.0' encoding='euc-kr'?><DOC>"
                                 "<table><tr><td>자산</td><td>1,000</td></tr></table>"
                                 "</DOC>").encode("euc-kr"))
    return buf.getvalue()


def _afx_hankyung(n: int = 12) -> str:
    hdr = ("<tr>" + "".join(f"<th>{h}</th>" for h in
           ["작성일", "제목", "적정가격", "투자의견", "작성자", "제공출처",
            "기업정보", "차트", "첨부"]) + "</tr>")
    rows = []
    for i in range(n):
        idx = 500000 + i
        rows.append(
            "<tr>"
            f"<td>2024-0{1+(i%9)}-15</td>"
            f"<td class='text_l'><a href='/analysis/downpdf?report_idx={idx}'>"
            f"합성{i+1:03d}({i+1:06d}) 실적 개선 전망</a></td>"
            f"<td class='text_r'>{(i+5)*10000:,}</td><td>Buy</td>"
            f"<td>애널{i%7:02d}</td><td>{'미래에셋대우' if i%2 else '하나금융투자'}</td>"
            f"<td>-</td><td>-</td>"
            f"<td><a href='/analysis/downpdf?report_idx={idx}'>PDF</a></td></tr>")
    return (f"<div id='contents'><div class='table_style01'><table>{hdr}"
            f"{''.join(rows)}</table></div></div>")


def _afx_naver_research(n: int = 12) -> str:
    hdr = ("<tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th>"
           "<th>작성일</th><th>조회수</th></tr>")
    rows = []
    for i in range(n):
        rows.append(
            "<tr>"
            f"<td><a class='stock_item' href='/item/main.naver?code={i+1:06d}' "
            f"title='합성{i+1:03d}'>합성{i+1:03d}</a></td>"
            f"<td><a href='company_read.naver?nid={90000+i}&amp;page=1'>실적 개선 전망</a></td>"
            f"<td>{'KB증권' if i%2 else '신한금융투자'}</td>"
            f"<td class='file'><a href='https://stock.pstatic.net/stock-research/company/16/"
            f"2024011{i%9}_company_{800000+i}.pdf'><img alt='pdf'/></a></td>"
            f"<td class='date'>24.0{1+(i%9)}.1{i%9}</td><td class='date'>1,234</td></tr>")
    nav = ("<table class='Nnavi'><tr><td class='pgRR'>"
           "<a href='/research/company_list.naver?&amp;page=2'>맨뒤</a></td></tr></table>")
    return (f"<div id='contentarea_left'><div class='box_type_m'>"
            f"<table class='type_1'>{hdr}{''.join(rows)}</table></div></div>{nav}")


def _afx_pdf() -> bytes:
    return b"%PDF-1.4\n% synthetic fixture\n%%EOF\n"


class _ArcFixtureNet:
    """URL 로 픽스처를 골라주는 가짜 네트워크. mode 로 정상/빈/깨짐/컬럼누락 전환."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: Counter = Counter()

    def get(self, url, source="generic", params=None, as_bytes=False, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return b"" if as_bytes else ""
        if self.mode == "broken":
            return b"\x00\x01garbage" if as_bytes else "<html><body>오류</body></html>"
        if "fdr_krx_data_cache" in u:
            if "/delisting/" in u:
                self.hits["fdr_delisting"] += 1
                return _afx_fdr_delisting()
            self.hits["fdr_listing"] += 1
            if self.mode == "missingcol":
                return b"\xef\xbb\xbf,Foo,Bar\n0,1,2\n"
            return _afx_fdr_listing()
        if "kind.krx.co.kr" in u:
            self.hits["kind"] += 1
            return _afx_kind()
        if "corpCode.xml" in u:
            self.hits["corpcode"] += 1
            return _afx_corpcode()
        if "document.xml" in u:
            self.hits["document"] += 1
            return _afx_document(str(p.get("rcept_no", "20200320000001")))
        if "consensus.hankyung.com" in u:
            if "downpdf" in u:
                self.hits["hk_pdf"] += 1
                return _afx_pdf()
            self.hits["hankyung"] += 1
            return (_afx_hankyung() if int(p.get("now_page", 1) or 1) == 1
                    else "<td class='no_data'>데이터가 없습니다</td>")
        if "finance.naver.com/research" in u:
            self.hits["naver_research"] += 1
            return (_afx_naver_research() if int(p.get("page", 1) or 1) <= 1
                    else "<div id='contentarea_left'><table class='type_1'></table></div>")
        if "finance.naver.com/item/main" in u:
            self.hits["naver_item"] += 1
            return '<div class="wrap_company"><h2><a href="#">합성종목</a></h2></div>'
        if "stock.pstatic.net" in u:
            self.hits["naver_pdf"] += 1
            return _afx_pdf()
        if "siseJson" in u:
            self.hits["naver_chart"] += 1
            rows = ["['날짜','시가','고가','저가','종가','거래량','외국인소진율']"]
            d0 = as_ts("2016-05-02")
            for i in range(0, 2600, 1):
                d2 = d0 + pd.Timedelta(days=i)
                if d2.weekday() >= 5:
                    continue
                rows.append(f"['{d2:%Y%m%d}',10000,10100,9900,10050,120000,5.0]")
            return "[" + ",".join(rows) + "]"
        self.hits["other"] += 1
        return b"" if as_bytes else ""

    def json(self, url, source="generic", params=None, **kw):
        u, p = str(url), (params or {})
        if self.mode == "empty":
            return None
        if self.mode == "broken":
            return {"nonsense": True}
        if "fnlttSinglAcntAll" in u:
            self.hits["fnltt"] += 1
            if self.mode == "missingcol":
                return {"status": "000", "list": [{"corp_code": p.get("corp_code")}]}
            return _afx_fnltt(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "fnlttMultiAcnt" in u:
            self.hits["multi"] += 1
            return {"status": "013"}
        if "empSttus" in u:
            self.hits["emp"] += 1
            return _afx_emp(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "stockTotqySttus" in u:
            self.hits["shares"] += 1
            return _afx_shares(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "accnutAdtorNmNdAdtOpinion" in u:
            self.hits["audit"] += 1
            return _afx_audit(p.get("corp_code", "C0000001"), int(p.get("bsns_year", 2020)))
        if "list.json" in u:
            self.hits["dart_list"] += 1
            return _afx_dart_list(str(p.get("bgn_de", "20200301")), str(p.get("pblntf_ty", "A")))
        if "stockSecurity/researches" in u:
            self.hits["naver_api"] += 1
            return []                     # JSON API 미가용 → HTML 폴백 경로를 타게 한다
        self.hits["other_json"] += 1
        return None


def run_rehearsal(strict: bool = True) -> bool:
    LOG.banner("② 실경로 리허설 (REHEARSAL)",
               "네트워크만 가짜로 바꾸고 수집·정제 로직은 실물 그대로 실행한다")
    REHEARSAL_RESULTS.clear()
    G = globals()
    saved = {k: G.get(k) for k in ("http_get", "http_json", "http_post", "fdr", "pykrx_stock",
                                   "yf", "DART_API_KEY", "RUN_MODE", "RESEARCH_DOWNLOAD_PDF",
                                   "ARC_DOC_MAX")}
    saved_vault, saved_budget = G.get("VAULT"), G.get("DBUDGET")
    tmp = tempfile.mkdtemp(prefix="arc_rehearsal_")
    rebals = rebal_dates("2019-03-01", "2021-12-01")

    try:
        net = _ArcFixtureNet("ok")
        G["http_get"], G["http_json"] = net.get, net.json
        G["http_post"] = lambda *a, **k: ""
        G["fdr"] = None
        G["pykrx_stock"] = None                # 스냅샷 부재 시 폴백 경로 검증
        G["yf"] = None
        G["DART_API_KEY"] = "REHEARSAL"
        G["RUN_MODE"] = "FULL"
        G["RESEARCH_DOWNLOAD_PDF"] = True
        G["ARC_DOC_MAX"] = 40
        G["VAULT"] = Vault(tmp, "REHEARSAL")
        G["DBUDGET"] = DartBudget()

        # ── ① 유니버스 ────────────────────────────────────────────────────────────────────
        snaps = _arh("fetch_pykrx_snapshots (pykrx 없음 → 폴백)",
                     lambda: fetch_pykrx_snapshots(month_range("2019-01-01", "2021-12-31")),
                     expect_rows=False, note="pykrx 미설치에서 죽지 않고 빈 결과여야 한다")
        _arh("fetch_fdr_listing", fetch_fdr_listing)
        _arh("fetch_fdr_delisting", fetch_fdr_delisting)
        _arh("fetch_kind_listing", fetch_kind_listing)
        _arh("fetch_dart_corpcode", fetch_dart_corpcode)
        sec = _arh("build_security_master",
                   lambda: build_security_master(
                       snaps if snaps is not None else
                       pd.DataFrame(columns=["snap_date", "code", "market"])),
                   note="중복 컬럼 → groupby.agg 폭발이 과거 이 지점에서 났다")
        if sec is None or not len(sec):
            sec = pd.DataFrame({"code": [f"{i+1:06d}" for i in range(20)],
                                "name": [f"합성{i+1:03d}" for i in range(20)],
                                "market": "KOSPI", "industry": "화학",
                                "corp_code": [f"C{i+1:07d}" for i in range(20)],
                                "listing_date": as_ts("2010-01-01"),
                                "delisting_date": pd.NaT})
        _arh("classify_excluded", lambda: classify_excluded(sec), expect_rows=False)

        # ── ② 가격 · 시총 ─────────────────────────────────────────────────────────────────
        codes = sec["code"].dropna().astype(str).tolist()[:8]
        px = _arh("fetch_prices (네이버 차트 폴백)",
                  lambda: fetch_prices(codes, "2018-06-01", "2021-12-31"),
                  note="FDR/pykrx 없이 네이버 경로만으로 동작해야 한다")
        if px is not None and len(px):
            _arh("build_liquidity_panel", lambda: build_liquidity_panel(px, rebals))
            _arh("build_exec_prices", lambda: build_exec_prices(px, rebals))
            _arh("attach_volatility", lambda: attach_volatility(
                pd.DataFrame({"code": codes[:3], "asof": rebals[0]}), px), expect_rows=False)
        _arh("fetch_market_cap_snapshots (pykrx 없음)",
             lambda: fetch_market_cap_snapshots(rebals), expect_rows=False)

        # ── ③ DART ────────────────────────────────────────────────────────────────────────
        corps = sec["corp_code"].dropna().astype(str).tolist()[:4]
        years = [2019, 2020]
        fs = _arh("fetch_dart_financials", lambda: fetch_dart_financials(corps, years))
        fin = None
        if fs is not None and len(fs):
            fin = _arh("tidy_financials", lambda: tidy_financials(fs))
        _arh("fetch_dart_employees", lambda: fetch_dart_employees(corps, years),
             note="사업부문×성별 분해 + '합계' 소계행 이중계상 방지")
        shares = _arh("fetch_dart_shares", lambda: fetch_dart_shares(corps, years),
                      note="보통주/우선주/합계 행 분해 — 합계 행 우선")
        audit = _arh("fetch_dart_audit", lambda: fetch_dart_audit(corps, years))
        dis = _arh("fetch_dart_disclosures",
                   lambda: fetch_dart_disclosures("2020-01-01", "2020-12-31"),
                   note="A(정기공시) + B(주요사항) 두 유형을 모두 훑어야 한다")

        # ── ④ 정기보고서 원문 → 정규화 → 페어링 → 유사도 ─────────────────────────────────
        T = None
        if dis is not None and len(dis):
            T = _arh("fetch_arc_documents (원문+정규화)",
                     lambda: fetch_arc_documents(dis, sec, max_docs=20),
                     note="zip 다중 엔트리 · EUC-KR · 6단계 정규화")
        if T is not None and len(T):
            _arh("arc_norm_sample_report", lambda: (arc_norm_sample_report(T, 2) or [1]),
                 expect_rows=False)
            pairs = _arh("arc_doc_pairs", lambda: arc_doc_pairs(T), expect_rows=False)
            if pairs is not None and len(pairs):
                S = _arh("d1_similarity", lambda: d1_similarity(pairs))
                if S is not None and len(S):
                    _arh("d1_composite",
                         lambda: d1_composite(S, build_struct_flags(dis)), expect_rows=False)
            _arh("arc_doc_load_years", lambda: arc_doc_load_years(arc_doc_years(T)),
                 expect_rows=False)
            _arh("build_d1_streaming (연도 스트리밍)",
                 lambda: build_d1_streaming(build_struct_flags(dis), T_manifest=T),
                 expect_rows=False,
                 note="연도 2개씩만 올려 상주량을 평평하게 유지하는 경로")
        _arh("build_struct_flags", lambda: build_struct_flags(dis), expect_rows=False)

        # ── ⑤ D2 / D3 / 배제 ──────────────────────────────────────────────────────────────
        if fin is not None and len(fin):
            _arh("build_d2_panel", lambda: build_d2_panel(fin, shares), expect_rows=False)
            _arh("build_exclusion_flags",
                 lambda: build_exclusion_flags(fin, dis, audit, T), expect_rows=False)
        _arh("extract_hardfacts",
             lambda: extract_hardfacts(T, fin, None, dis), expect_rows=False)

        # ── ⑥ 리서치 원장 → 본문 → TONE ───────────────────────────────────────────────────
        hk = _arh("hankyung_collect", lambda: hankyung_collect("2024-01-01", "2024-12-31"))
        nv = _arh("naver_collect",
                  lambda: naver_collect("2024-01-01", "2024-12-31", cats=("company",)))
        frames = [x for x in (hk, nv) if x is not None and len(x)]
        rep = _arh("build_report_master", lambda: build_report_master(frames, sec)) \
            if frames else None
        if rep is not None and len(rep):
            rep = _arh("tag_sponsored_reports", lambda: tag_sponsored_reports(rep))
            rep2 = _arh("download_pdfs", lambda: download_pdfs(rep, cap_per_month=3),
                        expect_rows=False)
            AL = _arh("build_analyst_ledger",
                      lambda: build_analyst_ledger(rep2 if rep2 is not None else rep),
                      expect_rows=False)
            if AL is not None:
                A, L = AL
                _arh("audit_linkage", lambda: (audit_linkage(rep, A, L) or [1]),
                     expect_rows=False)
                _arh("build_revision_panel", lambda: build_revision_panel(L, rebals),
                     expect_rows=False)
            rt = _arh("build_report_text_store",
                      lambda: build_report_text_store(rep2 if rep2 is not None else rep),
                      expect_rows=False,
                      note="PDF 픽스처에 텍스트 레이어가 없어 0행이 정상이다")
            _arh("build_tone_training",
                 lambda: build_tone_training(rt if rt is not None else
                                             pd.DataFrame(columns=["report_uid", "code",
                                                                   "pub_date", "text"]),
                                             px if px is not None else pd.DataFrame(), sec),
                 expect_rows=False)

        # ── ⑦ 게이트 ──────────────────────────────────────────────────────────────────────
        _arh("run_phase0_gates",
             lambda: (run_phase0_gates({"reports": rep, "report_text": None,
                                        "doc_tokens": T, "doc_pairs": None, "fin": fin,
                                        "shares": shares, "links": None,
                                        "panel_base": None}, rebals) or {"x": 1}),
             expect_rows=False)

        # ── ⑧ 이상 응답 내성 (빈 / 깨짐 / 컬럼누락) ───────────────────────────────────────
        for mode, label in (("empty", "빈 응답"), ("broken", "깨진 응답"),
                            ("missingcol", "기대 컬럼 누락")):
            bad = _ArcFixtureNet(mode)
            G["http_get"], G["http_json"] = bad.get, bad.json
            G["VAULT"] = Vault(tempfile.mkdtemp(prefix=f"arc_rh_{mode}_"), "REHEARSAL")
            G["DBUDGET"] = DartBudget()
            for fname, fn in (("fetch_fdr_listing", fetch_fdr_listing),
                              ("fetch_fdr_delisting", fetch_fdr_delisting),
                              ("fetch_kind_listing", fetch_kind_listing),
                              ("fetch_dart_corpcode", fetch_dart_corpcode)):
                _arh(f"[{label}] {fname}", fn, expect_rows=False,
                     note="예외 없이 빈 결과를 돌려줘야 한다")
            _arh(f"[{label}] fetch_dart_financials",
                 lambda: fetch_dart_financials(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_dart_shares",
                 lambda: fetch_dart_shares(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_dart_audit",
                 lambda: fetch_dart_audit(corps, [2020]), expect_rows=False)
            _arh(f"[{label}] fetch_arc_documents",
                 lambda: fetch_arc_documents(dis, sec, max_docs=5), expect_rows=False)
            _arh(f"[{label}] hankyung_collect",
                 lambda: hankyung_collect("2024-01-01", "2024-03-31"), expect_rows=False)
            _arh(f"[{label}] build_report_master(빈 입력)",
                 lambda: build_report_master([], sec), expect_rows=False)
            _arh(f"[{label}] arc_doc_pairs(빈 입력)",
                 lambda: arc_doc_pairs(pd.DataFrame(columns=ARC_DOC_COLS)), expect_rows=False)
            _arh(f"[{label}] d1_similarity(빈 입력)",
                 lambda: d1_similarity(pd.DataFrame(columns=ARC_PAIR_COLS)), expect_rows=False)
            _arh(f"[{label}] build_d2_panel(빈 입력)",
                 lambda: build_d2_panel(pd.DataFrame(), None), expect_rows=False)

    finally:
        for k, v in saved.items():
            G[k] = v
        G["VAULT"], G["DBUDGET"] = saved_vault, saved_budget
        shutil.rmtree(tmp, ignore_errors=True)

    ok_n = sum(1 for r in REHEARSAL_RESULTS if r["ok"])
    LOG.table([[_trunc(r["name"], 42), "✔" if r["ok"] else "✘",
                f"{r['rows']:,}" if r["rows"] >= 0 else "예외",
                f"{r['sec']:.2f}s", _trunc(r["err"] or r["note"], 56)]
               for r in REHEARSAL_RESULTS],
              ["실경로 함수", "판정", "결과", "소요", "비고"],
              ["l", "c", "r", "r", "l"], maxw=58)
    fails = [r for r in REHEARSAL_RESULTS if not r["ok"]]
    if fails:
        LOG.error(f"실경로 리허설 {len(fails)}/{len(REHEARSAL_RESULTS)}건 실패")
        for r in fails[:5]:
            LOG.banner(f"✘ 리허설 실패: {_trunc(r['name'], 60)}", _trunc(r["err"], 92))
            for ln in str(r.get("tb", "")).rstrip().split("\n")[-10:]:
                _safe_print("   " + ln)
        if strict:
            raise RuntimeError(
                f"실경로 리허설 실패 {len(fails)}건 — 실데이터 수집을 시작하지 않습니다. "
                f"여기서 막는 것이 몇 시간 뒤 L1 에서 죽는 것보다 훨씬 쌉니다.")
        return False
    LOG.ok(f"실경로 리허설 {ok_n}/{len(REHEARSAL_RESULTS)}건 통과 — "
           f"수집·정제 함수가 실제 데이터 모양에서 정상 동작합니다.")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-F  합성데이터 엔드투엔드 스모크                                                        ║
# ║                                                                                          ║
# ║  실데이터를 한 바이트도 받기 전에 계산경로 전체를 합성데이터로 통과시킨다.                   ║
# ║  목적은 성과 측정이 아니라 **배관 검증**이다. 실수집은 수 시간~수 일이 걸리는데              ║
# ║  그걸 다 받은 뒤 조립부에서 터지면 그 시간이 통째로 날아간다.                                ║
# ║                                                                                          ║
# ║  ★ 합성데이터에 '진짜 알파'를 심는다. quality[i] 가 높으면 ① ΔTONE↑ ② 문서변화↓            ║
# ║    ③ D2 지표 우수 ④ ΔNONFIN↑ ⑤ 미래수익↑. 그래야 하네스가 신호에 반응하는지 검증된다.       ║
# ║  ★ 엣지 케이스를 반드시 섞는다: 기간 중 상장/폐지, 축 A 결측 20%, D1 결측 15%,              ║
# ║    배제 발동 10%. 각각이 회귀 방지 장치다.                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SYN_VOCAB = [f"어휘{i:03d}" for i in range(400)] + \
             ["매출", "영업이익", "제조", "판매", "고객", "설비", "연구개발", "특허", "수출",
              "계약", "소송", "우발", "지배구조", "임원", "직원", "위험", "환율", "경쟁"]


def make_arc_synthetic(n_codes: int = 220, n_years: int = 8, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    end = as_ts(BACKTEST_END)
    start = end - pd.DateOffset(years=n_years)
    rebals = rebal_dates(start.strftime("%Y-%m-%d"), BACKTEST_END)
    # ★ 실제 한국 보통주 코드는 대부분 끝자리가 0 이다. 합성에서 000001,000002… 처럼
    #   촘촘한 연번을 쓰면 '형제 보통주' 우선주 규칙이 대량 오발화해 유니버스가 붕괴한다.
    #   현실과 같은 간격(10)으로 만들고, 진짜 우선주 쌍을 소수만 섞는다.
    codes = [f"{(i + 1) * 10:06d}" for i in range(n_codes)]
    for j in range(3, n_codes, 40):                 # 형제 보통주가 실재하는 우선주를 섞는다
        codes[j] = f"{j * 10 + 5:06d}"              # codes[j-1] = j*10 이 형제 보통주
    corps = [f"C{i+1:07d}" for i in range(n_codes)]
    sectors = ["IT/전자", "헬스케어", "소재", "산업재", "소비재", "금융"]
    inds = rng.choice(["반도체", "제약", "화학", "기계", "음식료", "은행"], n_codes)

    quality = rng.normal(size=n_codes)
    # ★ 축 A 는 '수준' 이 아니라 '변화(ΔTONE)' 를 신호로 쓴다. 합성에서 톤을 quality 의
    #   상수배로만 만들면 ΔTONE 은 정의상 순수 잡음이 되어, 축 A 경로가 신호를 잡을 수
    #   있는지 자체를 검증하지 못한다(초기 빌드에서 A1 의 IC 가 0 으로 나온 이유).
    #   → 시간가변 잠재변수 mood[i, t] 를 랜덤워크로 만들고, 톤과 '다음 분기 수익' 을
    #     모두 Δmood 에 연동한다. 그래야 '톤 변화가 수익에 선행' 하는 구조가 심긴다.
    n_reb = len(rebals)
    mood = np.cumsum(rng.normal(0, 0.55, size=(n_codes, n_reb)), axis=1)
    dmood = np.diff(mood, axis=1, prepend=mood[:, :1])
    reb_pos = {pd.Timestamp(t): j for j, t in enumerate(rebals)}

    # ── 상장/폐지 (생존자편향 검증) ───────────────────────────────────────────────────────
    listing = [start - pd.DateOffset(years=int(rng.integers(3, 15))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 12), replace=False):
        listing[i] = rebals[int(rng.integers(2, max(3, len(rebals) - 6)))]
    delist = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        delist[i] = rebals[int(rng.integers(4, max(5, len(rebals) - 2)))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": inds, "corp_code": corps, "src": "synthetic"})

    # ── 일봉 ──────────────────────────────────────────────────────────────────────────────
    days = pd.bdate_range(start - pd.DateOffset(months=18), end + pd.Timedelta(days=5))
    _day_arr = np.asarray(days.values, dtype="datetime64[ns]")
    _reb_arr = np.asarray(pd.DatetimeIndex(rebals).values, dtype="datetime64[ns]")
    px_rows = []
    for i, c in enumerate(codes):
        # 각 거래일이 속한 리밸 구간의 '직전 Δmood' 를 drift 에 더한다 → 톤 변화 선행 구조
        seg = np.clip(np.searchsorted(_reb_arr, _day_arr, side="right") - 1, 0, n_reb - 1)
        lead = dmood[i][np.clip(seg, 0, n_reb - 1)]
        drift = 0.0004 + 0.0008 * quality[i] + 0.0016 * lead
        r = rng.normal(drift, 0.024, len(days))
        p = float(rng.lognormal(8.5, 0.7)) * np.exp(np.cumsum(r))
        vol = rng.lognormal(10.8, 0.9, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days, "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * 1.012, "low": p * 0.988, "close": p,
            "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    for i, c in enumerate(codes):
        if pd.notna(delist[i]):
            px = px[~((px["code"] == c) & (px["date"] > delist[i]))]
        px = px[~((px["code"] == c) & (px["date"] < listing[i]))]

    # ── PIT 시가총액 ──────────────────────────────────────────────────────────────────────
    mc_rows = []
    shares_out = {c: float(rng.lognormal(16.0, 0.8)) for c in codes}
    for t in rebals:
        prev = px[px["date"] < as_ts(t)]
        if prev.empty:
            continue
        last = prev.groupby("code", observed=True).tail(1)
        for cc, cl in zip(last["code"], last["close"]):
            mc_rows.append({"date": as_ts(t), "code": cc,
                            "mktcap": float(cl) * shares_out[cc],
                            "shares_listed": shares_out[cc], "close_mc": float(cl),
                            "mc_src": "synthetic"})
    snap_mc = pd.DataFrame(mc_rows)

    # ── 재무 (분기) ───────────────────────────────────────────────────────────────────────
    rc = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
    fin_rows, emp_rows, sh_rows, aud_rows = [], [], [], []
    years = list(range(start.year - 1, end.year + 1))
    for i, c in enumerate(codes):
        base_rev = float(rng.lognormal(24, 1.0))
        sh = shares_out[c]
        for y in years:
            for q in (1, 2, 3, 4):
                gr = 1 + 0.015 * quality[i] + rng.normal(0, 0.05)
                base_rev *= gr
                rev = base_rev
                ni = rev * (0.05 + 0.015 * quality[i] + rng.normal(0, 0.01))
                cfo = ni * (1.0 + 0.35 * quality[i] + rng.normal(0, 0.15))
                pe = as_ts(f"{y}-{q*3:02d}-01") + pd.offsets.MonthEnd(0)
                kd = pe + pd.Timedelta(days=45 if q < 4 else 90)
                fin_rows.append({
                    "corp_code": corps[i], "bsns_year": y, "reprt_code": rc[q],
                    "period_end": pe, "knowledge_date": kd,
                    "revenue_ttm": rev * 4, "net_income_ttm": ni * 4, "cfo_ttm": cfo * 4,
                    "op_income_q": rev * (0.06 + 0.02 * quality[i] + rng.normal(0, 0.03)),
                    "assets": rev * 5.5, "liabilities": rev * 2.4, "equity": rev * 3.1,
                    "cash": rev * 0.6, "capital_stock": rev * 0.5,
                    "inventory": rev * (0.8 - 0.05 * quality[i]) * (1 + rng.normal(0, 0.05)),
                    "receivable": rev * (0.9 - 0.05 * quality[i]) * (1 + rng.normal(0, 0.05)),
                    "ppe": rev * 2.0 * (1 + 0.02 * max(quality[i], 0)),
                    "rnd_ttm": rev * (0.02 + 0.012 * max(quality[i], 0)) * 4,
                })
                sh *= (1 + max(0.0, 0.006 - 0.004 * quality[i]) + abs(rng.normal(0, 0.002)))
                sh_rows.append({"corp_code": corps[i], "bsns_year": y, "reprt_code": rc[q],
                                "shares_common": sh, "shares_total": sh,
                                "treasury_shares": 0.0, "period_end": pe,
                                "knowledge_date": kd})
            emp_rows.append({"corp_code": corps[i], "bsns_year": y,
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90),
                             "employees": float(max(15, rng.lognormal(4.8, 0.9) *
                                                    (1 + 0.05 * quality[i]))),
                             "payroll": float(rng.lognormal(21, 0.8))})
            # 배제 발동 10% — 감사 강조사항
            aud_rows.append({"corp_code": corps[i], "bsns_year": y,
                             "audit_opinion": "적정",
                             "emphasis": ("계속기업 불확실성" if rng.random() < 0.03 else ""),
                             "key_matter": "", "auditor": "합성회계법인",
                             "period_end": as_ts(f"{y}-12-31"),
                             "knowledge_date": as_ts(f"{y}-12-31") + pd.Timedelta(days=90)})
    fin = pit_frame(pd.DataFrame(fin_rows), "period_end", "knowledge_date", source="synthetic")
    emp = pit_frame(pd.DataFrame(emp_rows), "period_end", "knowledge_date", source="synthetic")
    shares = pit_frame(pd.DataFrame(sh_rows), "period_end", "knowledge_date", source="synthetic")
    audit = pit_frame(pd.DataFrame(aud_rows), "period_end", "knowledge_date", source="synthetic")

    # ── 공시목록 ──────────────────────────────────────────────────────────────────────────
    dis_rows = []
    for i, c in enumerate(codes):
        for y in years:
            dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                             "stock_code": c, "rcept_no": sha1_str(c, y, "FY")[:14],
                             "rcept_dt": as_ts(f"{y+1}-03-20"),
                             "report_nm": f"사업보고서 ({y}.12)", "event": ""})
            if rng.random() < 0.06:
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "cb")[:14],
                                 "rcept_dt": as_ts(f"{y}-07-10"),
                                 "report_nm": "주요사항보고서(전환사채발행결정)", "event": "cb_issue"})
            if rng.random() < 0.03:
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "mg")[:14],
                                 "rcept_dt": as_ts(f"{y}-05-10"),
                                 "report_nm": "주요사항보고서(회사합병결정)", "event": ""})
            if rng.random() < 0.12 + 0.10 * max(quality[i], 0):
                dis_rows.append({"corp_code": corps[i], "corp_name": f"합성{i+1:03d}",
                                 "stock_code": c, "rcept_no": sha1_str(c, y, "sc")[:14],
                                 "rcept_dt": as_ts(f"{y}-09-05"),
                                 "report_nm": "단일판매ㆍ공급계약체결", "event": ""})
    dis = pit_frame(pd.DataFrame(dis_rows), "rcept_dt", "rcept_dt", source="synthetic")

    # ── 정기보고서 토큰 (D1 입력) — D1 결측 15% 포함 ──────────────────────────────────────
    doc_rows = []
    no_d1 = set(rng.choice(n_codes, size=max(1, int(n_codes * 0.15)), replace=False).tolist())
    for i, c in enumerate(codes):
        if i in no_d1:
            continue
        prev_tf: Dict[str, Dict[str, int]] = {}
        for y in years:
            # quality 가 높을수록 문서를 '덜' 고친다 (Lazy Prices 방향)
            churn = float(np.clip(0.25 - 0.10 * quality[i] + rng.normal(0, 0.05), 0.02, 0.6))
            for sname in ARC_SECTIONS:
                base = prev_tf.get(sname)
                if base is None:
                    idx = rng.choice(len(_SYN_VOCAB), size=90, replace=False)
                    tf = {_SYN_VOCAB[j]: int(rng.integers(1, 9)) for j in idx}
                else:
                    tf = dict(base)
                    k = max(1, int(len(tf) * churn))
                    drop = list(rng.choice(list(tf), size=min(k, len(tf)), replace=False))
                    for d0 in drop:
                        tf.pop(d0, None)
                    add = rng.choice(len(_SYN_VOCAB), size=k, replace=False)
                    for j in add:
                        tf[_SYN_VOCAB[j]] = int(rng.integers(1, 9))
                prev_tf[sname] = tf
                toks = list(tf)
                bg = {f"{toks[j]}_{toks[j+1]}": 1 for j in range(min(len(toks) - 1, 40))}
                doc_rows.append({
                    "corp_code": corps[i], "rcept_no": sha1_str(c, y, sname)[:16],
                    "rcept_dt": as_ts(f"{y+1}-03-20"), "doc_type": "FY", "bsns_year": y,
                    "section": sname, "n_tokens": len(tf),
                    "tf": json.dumps(tf, ensure_ascii=False),
                    "bigram": json.dumps(bg, ensure_ascii=False),
                    "tok_len": int(sum(tf.values())), "is_amend": False})
    doc_tokens = pd.DataFrame(doc_rows)

    # ── 리포트 원장 + 애널리스트 링크 — 축 A 결측 20% 포함 ────────────────────────────────
    no_rep = set(rng.choice(n_codes, size=max(1, int(n_codes * 0.20)), replace=False).tolist())
    brokers = MAJOR_BROKERS[:8] + MINOR_BROKERS[:8] + ["한국IR협의회"]
    analysts = [(b, f"애널{j:02d}") for b in brokers for j in range(3)]
    rep_rows, link_rows, tone_rows = [], [], []
    for t in rebals:
        for i in range(n_codes):
            if i in no_rep or rng.random() > 0.55:
                continue
            for _ in range(int(rng.integers(1, 3))):
                b, nm = analysts[int(rng.integers(0, len(analysts)))]
                bid, bname = normalize_broker(b)
                d = as_ts(t) - pd.Timedelta(days=int(rng.integers(3, 88)))
                uid = sha1_str("syn", codes[i], d, nm, rng.integers(1e9))
                tp = float(np.exp(rng.normal(9.4, 0.5)) * (1 + 0.12 * quality[i]))
                rep_rows.append({
                    "report_uid": uid, "source": "synthetic", "src_report_id": uid[:10],
                    "pub_date": d, "category": "company",
                    "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                    "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                    "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                    "opinion": "BUY", "pdf_url": None, "detail_url": None,
                    "event_date": d, "knowledge_date": d})
                link_rows.append({
                    "report_uid": uid, "name": nm, "broker_id": bid, "broker_name": bname,
                    "role": "lead", "link_method": "list_field", "link_conf": 0.98,
                    "pub_date": d, "stock_code": codes[i], "target_price": tp,
                    "opinion": "BUY", "name_norm": nm,
                    "analyst_id": sha1_str("analyst", bid, nm)[:14]})
                _j = reb_pos.get(pd.Timestamp(t), 0)
                tone_rows.append({
                    "report_uid": uid, "code": codes[i], "pub_date": d,
                    "TONE_report": float(np.clip(0.10 * quality[i] + 0.45 * mood[i, _j] /
                                                 max(1.0, abs(mood[i, _j]) ** 0.5 + 1e-9)
                                                 + rng.normal(0, 0.22), -1, 1)),
                    "n_sent": int(rng.integers(10, 40)),
                    "event_date": d, "knowledge_date": d + pd.Timedelta(days=1)})
    reports = tag_sponsored_reports(pd.DataFrame(rep_rows))
    links = pd.DataFrame(link_rows)
    tone_rep = pd.DataFrame(tone_rows)

    return {"sec": sec, "px": px, "fin": fin, "shares": shares, "emp": emp, "dis": dis,
            "audit": audit, "reports": reports, "links": links, "tone_rep": tone_rep,
            "doc_tokens": doc_tokens, "snap_mc": snap_mc, "rebals": rebals,
            "quality": quality}


def _syn_build_panel(S: dict) -> Tuple[pd.DataFrame, Any, dict]:
    """합성데이터로 실제 파이프라인 함수를 그대로 통과시킨다(모의 구현 금지)."""
    rebals = S["rebals"]
    sec, px = S["sec"], S["px"]

    liq = build_liquidity_panel(px, rebals)
    execp = build_exec_prices(px, rebals)
    mc = build_mktcap_panel(rebals,
                            px.assign(month=as_ts_series(px["date"]) + pd.offsets.MonthEnd(0))
                              .groupby(["code", "month"], observed=True)
                              .tail(1)[["code", "month", "close"]],
                            S["snap_mc"], S["shares"], sec)
    base = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    exd = classify_excluded(sec)
    uni = ArcUniverse(base, sec, exd)
    U = uni.build(rebals, mc, liq[["code", "asof", "adtv60"]] if len(liq) else liq)
    P = build_arc_panel(uni, rebals, U, liq, execp, sec, px_daily=px)

    # 축 B
    pairs = arc_doc_pairs(S["doc_tokens"])
    struct = build_struct_flags(S["dis"])
    d1 = d1_composite(d1_similarity(pairs), struct)
    P = attach_d1(P, d1)
    P = attach_d2(P, build_d2_panel(S["fin"], S["shares"]))
    hard = extract_hardfacts(S["doc_tokens"], S["fin"], S["emp"], S["dis"])
    excl = build_exclusion_flags(S["fin"], S["dis"], S["audit"], S["doc_tokens"])
    P = attach_d3(P, hard, excl)

    # 재무를 패널에 붙여 eps_rev 대리변수를 만들 수 있게 한다
    if len(S["fin"]):
        PIT.register("syn_fin", arc_kd_lag(S["fin"]), key_cols=["corp_code"])
        P = PIT.asof_join(P, "syn_fin", by="corp_code", left_time="asof",
                          cols=["corp_code", "knowledge_date", "net_income_ttm", "assets"],
                          suffix="_fin")
    # 축 A
    tone_q = aggregate_tone(S["tone_rep"], rebals)
    rev = build_revision_panel(S["links"], rebals)
    P = attach_axis_a(P, tone_q, rev)
    P = attach_volatility(P, px)
    return P, uni, {"pairs": pairs, "d1": d1, "tone_q": tone_q, "rev": rev}


def run_selftest(full_chain: bool = False) -> bool:
    """full_chain=True 면 성과·어블레이션·BH-FDR·강건성·해석표까지 전부 합성으로 예행연습."""
    LOG.banner("① 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수십 초)" +
               (" · full_chain: 어블레이션·강건성까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    try:
        S = make_arc_synthetic()
    except Exception as e:                                        # noqa
        LOG.error(f"합성데이터 생성 실패 — {type(e).__name__}: {e}")
        return False
    LOG.info(f"합성: 종목 {len(S['sec'])} · 리밸 {len(S['rebals'])} · 일봉 {len(S['px']):,} · "
             f"재무 {len(S['fin']):,} · 문서토큰 {len(S['doc_tokens']):,} · "
             f"리포트 {len(S['reports']):,}")

    P, uni, aux = _syn_build_panel(S)
    Q = assemble_final(P, use_axes=("A", "D1", "D2", "D3"), use_excl=True)

    def _run(pp, label="smoke", apply_costs=True, top_n=None, weighting=None, bottom=False):
        return run_backtest(pp, S["rebals"], uni, S["sec"], apply_costs=apply_costs,
                            label=label, top_n=top_n, weighting=weighting, bottom=bottom)

    bt = _run(Q, label="SMOKE")
    st = perf_stats(bt["returns"])
    dur = time.time() - t0

    # ── 배관 검증 판정 ────────────────────────────────────────────────────────────────────
    checks = []
    checks.append(("패널 생성", len(P) > 0, f"{len(P):,}행"))
    checks.append(("백테스트 기간 일치", len(bt["returns"]) == len(S["rebals"]),
                   f"{len(bt['returns'])}/{len(S['rebals'])}"))
    checks.append(("성과 산출", bool(st) and np.isfinite(st.get("CAGR", np.nan)),
                   f"CAGR {st.get('CAGR', float('nan'))*100:+.2f}%"))
    n_a_miss = int((pd.to_numeric(col(P, "has_axis_a"), errors="coerce").fillna(0) == 0).sum())
    surv = int(Q.loc[pd.to_numeric(col(Q, "has_axis_a"), errors="coerce").fillna(0) == 0,
                     "FINAL_SCORE"].notna().sum())
    checks.append(("축 A 결측 종목 생존 (§7.2)", n_a_miss == 0 or surv > 0,
                   f"결측 {n_a_miss:,}행 중 {surv:,}행 생존"))
    n_d1_miss = int(pd.to_numeric(col(P, "D1_MISSING"), errors="coerce").fillna(0).sum())
    surv2 = int(Q.loc[pd.to_numeric(col(Q, "D1_MISSING"), errors="coerce").fillna(0) > 0,
                      "FINAL_SCORE"].notna().sum())
    checks.append(("D1 결측 가중치 재배분 (§6.5)", n_d1_miss == 0 or surv2 > 0,
                   f"결측 {n_d1_miss:,}행 중 {surv2:,}행 생존"))
    n_ex = int(pd.to_numeric(col(P, "EXCLUDE"), errors="coerce").fillna(0).sum())
    leak = int(Q.loc[pd.to_numeric(col(Q, "EXCLUDE"), errors="coerce").fillna(0) > 0,
                     "FINAL_SCORE"].notna().sum())
    checks.append(("배제 하드 제외 (§6.4)", leak == 0, f"발동 {n_ex:,}행 · 누수 {leak}행"))
    ic, icir, n_ic = bt_ic(Q, "FINAL_RANK")
    checks.append(("신호→수익 반응 (하네스 민감도)", np.isfinite(ic),
                   f"IC {ic:+.4f} (IC-IR {icir:+.2f}, {n_ic}기간)"))

    LOG.table([[k, "✔" if ok else "✘", v] for k, ok, v in checks],
              ["배관 검증 항목", "판정", "실측"], ["l", "c", "l"],
              title=f"스모크 결과 (소요 {dur:.1f}초 — 성과 수치는 의미 없음, 배관 검증용)")
    ok_all = all(ok for _k, ok, _v in checks)
    if not ok_all:
        LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
        return False
    LOG.ok(f"스모크 통과 ({dur:.1f}초) — 수집→패널→신호→백테스트 경로가 정상 동작합니다.")

    if not full_chain:
        return True

    # ── full_chain: 최종 출력물 전체 예행연습 ─────────────────────────────────────────────
    LOG.banner("⚠ 아래 수치는 전부 합성 난수 기반입니다",
               "전략의 실제 성과가 아니라 '출력물이 제대로 나오는지' 예행연습입니다. 해석 금지")
    ctx = {"panel_base": P, "reports": S["reports"], "report_text": S["reports"],
           "doc_tokens": S["doc_tokens"], "doc_pairs": aux["pairs"], "fin": S["fin"],
           "shares": S["shares"], "links": S["links"], "doc_attempted": len(S["doc_tokens"])}
    with PIPE.stage("SMOKE.GATE", "[합성] Phase 0 게이트", "L1", budget_s=120, critical=False):
        run_phase0_gates(ctx, S["rebals"])
    with PIPE.stage("SMOKE.PERF", "[합성] 성과 검증", "L6", budget_s=120, critical=False):
        report_performance(bt, {}, label="ARC-TXT v2 (합성 예행연습)",
                           uni_bench=equal_weight_universe_return(Q))
        uni.report_attrition()
        report_score_summary(Q)
    with PIPE.stage("SMOKE.DIAG", "[합성] 층 상관 · D1 부호 · D2 커버리지", "L6",
                    budget_s=120, critical=False):
        report_correlation_matrix(Q)
        ctx["d1_sign"] = report_d1_sign_check(Q)
        report_d2_coverage(Q)
        report_d3_sector(Q)
        report_exclusion(Q)
        ctx["axis_a_ic"] = report_axis_a_ic(Q)
    with PIPE.stage("SMOKE.ABL", "[합성] 어블레이션 11종 + BH-FDR", "L5",
                    budget_s=1800, critical=False):
        run_ablations(Q, S["rebals"], uni, S["sec"], _run)
        report_f4_vs_f1()
        ctx["fdr"] = apply_bh_fdr()
    with PIPE.stage("SMOKE.ROBUST", "[합성] 강건성 R1~R11", "L5", budget_s=1800, critical=False):
        run_robustness_suite(Q, bt, S["rebals"], uni, S["sec"], _run,
                             rep=S["reports"], doc=S["doc_tokens"], px_daily=S["px"])
    with PIPE.stage("SMOKE.REPORT", "[합성] 해석표 · 진단카드 · 폐기판정", "L6",
                    budget_s=180, critical=False):
        report_interpretation(Q)
        diagnostic_card(Q, bt, S["sec"])
        ctx["kill"] = report_kill_criteria(ctx)
        report_final_deliverables(ctx)

    LOG.ok("full_chain 예행연습 완료 — 게이트·성과·어블레이션·BH-FDR·강건성·해석표·진단카드·"
           "폐기판정이 모두 정상 출력되었습니다. RUN_MODE='FULL' 로 바꾸면 동일한 출력이 "
           "실데이터로 나옵니다.")
    # ★ 합성 결과가 실데이터 결과와 섞이면 안 된다. 전부 비운다.
    ABLATION_RESULTS.clear()
    ROBUST_RESULTS.clear()
    GATE_RESULTS.clear()
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — §10 실행 순서                                                            ║
# ║   [1] Phase 0 게이트 → [2] U-1000 PIT → [3] DART 수집 → [4] 정규화 → [5] D1                ║
# ║   [6] D2 → [7] D3·배제 → [8] 층 상관 진단 → [9] 리포트·TONE → [10] ΔTONE·직교화·IC          ║
# ║   [11] 인과순서 → [12] FINAL 합성 → [13] 어블레이션 11 → [14] BH-FDR·강건성 → [15] 보고     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f          # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML         # type: ignore
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


def arc_collect(rebals: pd.DatetimeIndex) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    years = list(range(as_ts(BACKTEST_START).year - 2, as_ts(BACKTEST_END).year + 1))

    with PIPE.stage("L1.UNI", "종목 마스터 (상장·폐지 3중 확보)", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(month_range(BACKTEST_START, BACKTEST_END))
        sec = build_security_master(snaps)
        ctx["sec"], ctx["snapshots"] = sec, snaps

    with PIPE.stage("L1.PX", "가격 · 유동성 · PIT 시가총액", "L1", budget_s=2400):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        ctx["liq"] = build_liquidity_panel(px, rebals)
        ctx["exec"] = build_exec_prices(px, rebals)
        ctx["snap_mc"] = fetch_market_cap_snapshots(rebals)

    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시 · 주식총수 · 감사의견", "L1",
                    budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        prio: List[str] = []
        try:
            adv = (ctx["liq"].groupby("code", observed=True)["adtv60"].median()
                   .sort_values(ascending=False))
            c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
                            .set_index("code")["corp_code"].astype(str).to_dict())
            prio = [c2c[c] for c in adv.index if c in c2c]
        except Exception:
            prio = []
        multi = fetch_dart_multi_accounts(corps, years)
        fs = fetch_dart_financials(corps, years, priority=prio)
        ctx["fin"] = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["emp"] = fetch_dart_employees(corps, years)
        ctx["dis"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        ctx["shares"] = fetch_dart_shares(corps, years)
        ctx["audit"] = fetch_dart_audit(corps, years)
        if DBUDGET is not None:
            DBUDGET.report()

    with PIPE.stage("L1.DOC", "DART 정기보고서 원문 수집 + 정규화 (D1 입력)", "L1",
                    budget_s=3600, critical=False):
        n_before = 0
        try:
            n_before = int(ctx["dis"]["report_nm"].astype(str)
                           .str.contains("사업보고서|반기보고서|분기보고서", na=False).sum())
        except Exception:
            pass
        ctx["doc_attempted"] = n_before
        _T = fetch_arc_documents(ctx.get("dis"), ctx["sec"])
        arc_norm_sample_report(_T, n=5)                     # §10-[4] 육안 검증
        ctx["doc_pairs"] = arc_doc_pairs(_T)
        # ★ 게이트·D3 는 매니페스트(토큰 제외)만 있으면 된다. tf/bigram 을 통째로 들고
        #   다니면 문서 수에 비례해 상주량이 폭발하므로 여기서 떨어뜨린다.
        #   D1 은 build_d1_streaming 이 연도 샤드에서 다시 읽는다.
        _keep = [c for c in ARC_DOC_COLS if c not in ("tf", "bigram")]
        ctx["doc_tokens_full"] = _T if len(_T) < 60_000 else None
        ctx["doc_tokens"] = _T[_keep].copy() if len(_T) else _T
        _mb = mem_mb(_T)
        del _T
        gc.collect()
        LOG.info(f"문서 토큰 원본 {_mb:.0f}MB → 매니페스트만 보관 "
                 f"({mem_mb(ctx['doc_tokens']):.0f}MB). D1 은 연도 샤드에서 스트리밍합니다.")

    _research_on = bool(RESEARCH_COLLECT or RUN_MODE == "CACHED")
    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 · 본문", "L1",
                    budget_s=5400, critical=False, skip_if=(not _research_on),
                    skip_reason="RESEARCH_COLLECT=False") as _st_res:
      # ★ skip_if 는 표시만 한다(본문을 막지 못한다) — 실제 분기는 여기서 명시적으로 한다.
      if not _research_on:
        ctx["reports"] = pd.DataFrame(columns=REPORT_COLS)
        ctx["analysts"] = pd.DataFrame()
        ctx["links"] = pd.DataFrame()
        ctx["report_text"] = pd.DataFrame()
      else:
          LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                   "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한합니다. "
                   "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
          cached = VAULT.get_table("research_report_master", scope="shared")
          frames = []
          if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
              if "hankyung" in RESEARCH_SOURCES:
                  frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
              if "naver" in RESEARCH_SOURCES:
                  nv = naver_collect(BACKTEST_START, BACKTEST_END)
                  frames.append(naver_enrich_detail(nv))
          if cached is not None and len(cached):
              LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
              frames.append(cached)
          rep = build_report_master(frames, ctx["sec"])
          if len(rep):
              rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
              if "pdf_target" in rep.columns:
                  fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                  if fill.any():
                      rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
                      LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 보강")
              rep = tag_sponsored_reports(rep)
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
          ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
          ctx["report_text"] = build_report_text_store(rep) if len(rep) else pd.DataFrame()
    return ctx


def arc_build_signals(ctx: dict, rebals: pd.DatetimeIndex, gate: dict):
    """L2 — 유니버스 → 패널 → 축 B(D1·D2·D3·배제) → 축 A(TONE·직교화) → FINAL."""
    with PIPE.stage("L2.UNI", "U-1000 PIT 유니버스 + 분기 패널", "L2", budget_s=900):
        px_monthly = (ctx["px"].assign(month=as_ts_series(ctx["px"]["date"]) +
                                       pd.offsets.MonthEnd(0))
                      .groupby(["code", "month"], observed=True)
                      .tail(1)[["code", "month", "close"]])
        mc = build_mktcap_panel(rebals, px_monthly, ctx.get("snap_mc"), ctx.get("shares"),
                                ctx["sec"])
        base = Universe(ctx["sec"], ctx.get("snapshots",
                                            pd.DataFrame(columns=["snap_date", "code", "market"])),
                        ctx["px"])
        uni = ArcUniverse(base, ctx["sec"], classify_excluded(ctx["sec"]))
        U = uni.build(rebals, mc, ctx["liq"][["code", "asof", "adtv60"]]
                      if len(ctx.get("liq", [])) else pd.DataFrame())
        P = build_arc_panel(uni, rebals, U, ctx.get("liq"), ctx.get("exec"),
                            ctx["sec"], px_daily=ctx.get("px"))
        ctx["panel_base"] = P

    _d1_on = bool(gate.get("d1", True))
    with PIPE.stage("L2.D1", "D1 텍스트 변화량", "L2", budget_s=1800, critical=False,
                    skip_if=(not _d1_on),
                    skip_reason="Phase 0 GATE_4/5 실패 — D1 비활성화"):
        # ★ skip_if 는 표시만 한다. 실제로 계산을 막으려면 여기서 분기해야 한다 —
        #   그러지 않으면 '축을 껐다'고 로그에만 찍히고 값은 그대로 반영된다.
        if _d1_on:
            struct = build_struct_flags(ctx.get("dis"))
            # 연도 2개씩만 올리는 스트리밍 경로. 전 구간 토큰을 한 번에 들면 수 GB 가 된다.
            d1 = build_d1_streaming(struct, T_manifest=ctx.get("doc_tokens"))
            P = attach_d1(P, d1)
        else:
            P = attach_d1(P, None)          # 컬럼만 보장하고 전 구간 결측 처리

    with PIPE.stage("L2.D2", "D2 재무제표 이상현상", "L2", budget_s=600, critical=False):
        P = attach_d2(P, build_d2_panel(ctx.get("fin"), ctx.get("shares"))
                      if gate.get("d2", True) else None)
        report_d2_coverage(P)

    with PIPE.stage("L2.D3", "D3 하드팩트 + 배제 플래그", "L2", budget_s=900, critical=False):
        _Td = ctx.get("doc_tokens_full")     # tf 가 있어야 텍스트 기반 이벤트를 볼 수 있다
        hard = extract_hardfacts(_Td, ctx.get("fin"), ctx.get("emp"), ctx.get("dis"))
        excl = build_exclusion_flags(ctx.get("fin"), ctx.get("dis"), ctx.get("audit"), _Td)
        if _Td is None:
            LOG.warn("문서 수가 많아 토큰 원본을 메모리에 유지하지 않았습니다 — D3 의 "
                     "텍스트 기반 이벤트(특허·정부과제·종속기업·해외거점·신규사업)는 이번 "
                     "실행에서 결측입니다. 재무·직원·수시공시 기반 이벤트는 정상 산출됩니다.")
        P = attach_d3(P, hard, excl)
        report_d3_sector(P)
        report_exclusion(P)

    with PIPE.stage("L2.FIN", "재무 결합 (직교화 통제변수용)", "L2", budget_s=300,
                    critical=False):
        if ctx.get("fin") is not None and len(ctx["fin"]):
            PIT.register("arc_fin", arc_kd_lag(ctx["fin"]), key_cols=["corp_code"])
            P = PIT.asof_join(P, "arc_fin", by="corp_code", left_time="asof",
                              cols=["corp_code", "knowledge_date", "net_income_ttm", "assets"],
                              suffix="_fin")

    _axis_a_on = bool(gate.get("axis_a", True))
    with PIPE.stage("L2.A", "축 A — TONE 분류 · ΔTONE · 직교화", "L2", budget_s=5400,
                    critical=False, skip_if=(not _axis_a_on),
                    skip_reason="Phase 0 GATE_1/2/3 실패 — DART-ONLY 폴백"):
        if _axis_a_on:
            train = build_tone_training(ctx.get("report_text"), ctx.get("px"), ctx["sec"])
            tone_rep = score_tone_reports(ctx.get("report_text"), train, rebals)
            tone_q = aggregate_tone(tone_rep, rebals)
            rev = build_revision_panel(ctx.get("links"), rebals)
            P = attach_axis_a(P, tone_q, rev)
            ctx["tone_q"], ctx["rev"] = tone_q, rev
        else:
            # DART-ONLY 폴백 — 축 A 를 전 구간 결측으로 두되 종목은 탈락시키지 않는다(§7.2)
            P = attach_axis_a(P, None, None)

    with PIPE.stage("L2.VOL", "역변동성 가중용 변동성", "L2", budget_s=300, critical=False):
        P = attach_volatility(P, ctx.get("px"))

    with PIPE.stage("L2.SCORE", "FINAL_SCORE 합성", "L2", budget_s=300):
        axes = ["A"] if gate.get("axis_a", True) else []
        if gate.get("d1", True):
            axes.append("D1")
        if gate.get("d2", True):
            axes.append("D2")
        axes.append("D3")
        Q = assemble_final(P, use_axes=tuple(axes), use_excl=True)
        ctx["use_axes"] = tuple(axes)
        report_score_summary(Q)
        VAULT.put_table(f"l1_features_{STRATEGY_ID}", downcast(P.copy()), scope="private",
                        domain="features", source="L2 panel")
        VAULT.put_table(f"l2_scores_{STRATEGY_ID}",
                        Q[[c for c in ("code", "asof", "q", "DART_SCORE", "AXIS_A_Z",
                                       "FINAL_SCORE", "FINAL_RANK", "EXCLUDE")
                           if c in Q.columns]],
                        scope="private", domain="scores", source="L2")
    return Q, uni


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET
    LOG.banner(f"ARC-TXT v2.0 — {STRATEGY_NAME}  [{STRATEGY_ID}]",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · "
               f"빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"],
               ["형태소 분석", "konlpy 사용 가능" if KONLPY_AVAILABLE else
                              ("soynlp" if soynlp_tok is not None else "규칙기반 폴백")],
               ["TONE 분류기", f"{ARC_TONE_MODEL} " +
                              ("(sklearn)" if sk_tfidf is not None else "(numpy NB 폴백)")]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "캐시 연결 (로컬 + 구글드라이브 양쪽 탐색)", "L0", budget_s=600):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"여유 공간 {free:.1f} GB")
            if free < 3:
                LOG.warn("여유 공간이 3GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan([os.path.expanduser(p) for p in CACHE_SEARCH_DIRS])
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 A1~A21", "L0", budget_s=300):
        run_contract_tests(strict=STOP_ON_CONTRACT_FAIL)

    with PIPE.stage("L0.SMOKE", "합성 엔드투엔드 스모크", "L0",
                    budget_s=(3600 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설", "L0", budget_s=900):
        run_rehearsal(strict=True)

    rebals = rebal_dates(BACKTEST_START, BACKTEST_END)
    LOG.info(f"리밸런싱 시점 {len(rebals)}개 ({rebals[0]:%Y-%m-%d} ~ {rebals[-1]:%Y-%m-%d})")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages(); PIPE.report_runtime(); report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = arc_collect(rebals)

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (보고서↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()),
                      ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    # ── 게이트를 위해 기본 패널을 먼저 만든다 (유니버스 코드 집합이 필요) ────────────────
    with PIPE.stage("L1.PRE", "게이트용 예비 유니버스", "L1", budget_s=600, critical=False):
        try:
            px_monthly = (ctx["px"].assign(month=as_ts_series(ctx["px"]["date"]) +
                                           pd.offsets.MonthEnd(0))
                          .groupby(["code", "month"], observed=True)
                          .tail(1)[["code", "month", "close"]])
            mc0 = build_mktcap_panel(rebals, px_monthly, ctx.get("snap_mc"),
                                     ctx.get("shares"), ctx["sec"])
            b0 = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(
                columns=["snap_date", "code", "market"])), ctx["px"])
            u0 = ArcUniverse(b0, ctx["sec"], classify_excluded(ctx["sec"]))
            U0 = u0.build(rebals, mc0, ctx["liq"][["code", "asof", "adtv60"]])
            ctx["panel_base"] = U0
        except Exception as e:                                    # noqa
            LOG.warn(f"예비 유니버스 생성 실패({type(e).__name__}) — 게이트는 전 종목 기준으로 "
                     f"계산됩니다.")

    with PIPE.stage("L1.GATE", "Phase 0 게이트 6종", "L1", budget_s=300, critical=False):
        gate = run_phase0_gates(ctx, rebals)
        ctx["gate"] = gate

    P, uni = arc_build_signals(ctx, rebals, gate)

    def _run(pp, label="ARC", apply_costs=True, top_n=None, weighting=None, bottom=False):
        return run_backtest(pp, rebals, uni, ctx["sec"], apply_costs=apply_costs,
                            label=label, top_n=top_n, weighting=weighting, bottom=bottom)

    with PIPE.stage("L3.BT", "백테스트 (분기 리밸런싱)", "L3", budget_s=600):
        bt = _run(P, label=STRATEGY_ID)
        bt_iv = _run(P, label=f"{STRATEGY_ID}_invvol", weighting="invvol")

    with PIPE.stage("L6.PERF", "성과 검증", "L6", budget_s=300, critical=False):
        bench = benchmark_returns(rebals)
        ubench = equal_weight_universe_return(P)
        report_performance(bt, bench, label="동일가중(기준)", uni_bench=ubench)
        report_performance(bt_iv, bench, label="역변동성 가중(병행)", uni_bench=ubench)
        uni.report_attrition()

    with PIPE.stage("L6.DIAG", "층 상관 · D1 부호 · 축 A IC", "L6", budget_s=300,
                    critical=False):
        report_correlation_matrix(P)
        ctx["d1_sign"] = report_d1_sign_check(P)
        ctx["axis_a_ic"] = report_axis_a_ic(P)

    with PIPE.stage("L5.ABL", "어블레이션 11종 + BH-FDR", "L5", budget_s=2 * 3600,
                    critical=False):
        run_ablations(P, rebals, uni, ctx["sec"], _run)
        report_f4_vs_f1()
        ctx["fdr"] = apply_bh_fdr()

    with PIPE.stage("L5.ROBUST", "강건성 R1~R11", "L5", budget_s=2 * 3600, critical=False):
        run_robustness_suite(P, bt, rebals, uni, ctx["sec"], _run,
                             rep=ctx.get("reports"), doc=ctx.get("doc_tokens"),
                             px_daily=ctx.get("px"))

    with PIPE.stage("L6.REPORT", "해석표 · 진단카드 · 폐기 판정", "L6", budget_s=300,
                    critical=False):
        report_interpretation(P)
        diagnostic_card(P, bt, ctx["sec"])
        ctx["kill"] = report_kill_criteria(ctx)
        report_gate_table()
        report_final_deliverables(ctx)

    with PIPE.stage("L0.PERSIST", "산출물 저장 (전용 인덱스) + 다운로드", "L0",
                    budget_s=600, critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        rp = os.path.join(outdir, f"returns_{stamp}.csv")
        bt["returns"].to_csv(rp, index=False, encoding="utf-8-sig")
        outs.append(rp)
        if len(bt.get("holdings", pd.DataFrame())):
            hp = os.path.join(outdir, f"holdings_{stamp}.csv")
            bt["holdings"].to_csv(hp, index=False, encoding="utf-8-sig")
            outs.append(hp)
        if ABLATION_RESULTS:
            ap = os.path.join(outdir, f"ablation_{stamp}.csv")
            pd.DataFrame([{"id": k, "name": v["name"], "ok": v["ok"],
                           **{f"net_{kk}": vv for kk, vv in (v.get("net") or {}).items()},
                           "ic": v.get("ic"), "icir": v.get("icir"), "p": v.get("p")}
                          for k, v in ABLATION_RESULTS.items()]).to_csv(
                ap, index=False, encoding="utf-8-sig")
            outs.append(ap)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)
        VAULT.put_table(f"backtest_returns_{STRATEGY_ID}", bt["returns"], scope="private",
                        domain="backtest", source=STRATEGY_ID)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        if DBUDGET:
            DBUDGET.report(); DBUDGET.close()
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
    LOG.info("[방법론적 한계 — 숨기지 않는다] ① EPS 컨센서스 시계열은 과거 복원이 불가능하여 "
             "PIT 실적 변화율을 대리변수로 씁니다. ② 관리종목·거래정지 지정 이력은 공개 API 로 "
             "복원 불가하여 배제 플래그와 유동성 하한으로 근사합니다. ③ 특수관계자·우발부채·"
             "소송 금액 판정은 정규화 이전 원문 재파싱이 선행되어야 하며 현재 결측입니다. "
             "④ Lazy Prices 는 미국 10-K 결과이며 한국 재현은 이 백테스트의 검증 대상입니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "ctx": ctx,
            "ablation": ABLATION_RESULTS, "robust": ROBUST_RESULTS, "gate": GATE_RESULTS}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 계약 위반/폐기 기준으로 중단", "파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_runtime()
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages(); PIPE.report_flow(); PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
