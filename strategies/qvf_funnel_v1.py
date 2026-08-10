#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  QVF-FUNNEL v1.0 — 가치·퀄리티·수급 1차선별 → DART+애널리스트 2차 → 규칙화 3차 깔때기 전략
#  백테스트 구간: 2016-08 ~ 2026-07 (10년) · 분기 리밸런싱(3/1, 6/1, 9/1, 12/1)
#
#  U-1000 (PIT 시총 하위 1000)
#     └─[1차] 가치(V)/퀄리티(Q)/수급(F) 스코어 — 3변형 V · VQ · VQF ──────────→ U-200
#            └─[2차] DART 하드팩트 ΔNONFIN + 애널리스트 ΔTONE(결측허용) − 배제플래그 → 60~80
#                   └─[3차 3-A] 규칙 체크리스트 ────────────────────────────→ 20~40 종목
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python qvf_funnel_v1.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성·계약(Q1~Q12) 자가검정 → 합성 스모크 → 실경로 리허설
#     [1] Phase 0 데이터 실현가능성 게이트 (fin_cov / flow_cov / dart_parse_rate / report_cov)
#     [2] 데이터 수집 (로컬+드라이브 양쪽 캐시 탐색 → 부족분만 신규 → 드라이브에 재적재)
#     [3] 원장 무결성 감사 (보고서 ↔ 애널리스트 ↔ 종목 연결)
#     [4] U-1000 PIT 유니버스 (상장폐지 포함 검증 + 감쇠 감사)
#     [5] 1차필터 3변형 → U-200 ×3 + 중복률·특성 비교표  ← §11 중간보고 지점
#     [6] DART 하드팩트 + 배제플래그   [7] TONE 분류기(확장윈도우) + 직교화
#     [8] 인과 순서 점검   [9] 2차필터   [10] 3-A 규칙판
#     [11] 주 실험 3개 백테스트   [12] 어블레이션 X1~X4
#     [13] BH-FDR + 강건성   [14] 수급축 C1~C5 판정   [15] 보고서·산출물 다운로드
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다  (아무것도 안 채워도 실행은 됩니다)
#
#   ▸ 키가 없는 데이터원은 자동으로 건너뛰고 "왜 건너뛰었는지"를 한글로 로그에 남깁니다.
#     조용히 실패하지 않습니다.
#   ▸ 구글드라이브(또는 로컬)에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  (이 전략의 2차필터 백본 — 사실상 필수) ─────────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 → [인증키 신청/관리] → API 인증키 발급
#    무료, 발급 즉시 사용. 일일 호출 한도가 있습니다(계정 등급별로 다름).
#    ▶ 이 코드는 한도를 20,000 같은 숫자로 고정하지 않습니다. 오늘 남은 호출량을
#      실시간으로 추정·측정해서 그만큼만 씁니다(§DartQuota). 한도에 닿으면 깨끗하게
#      멈추고, 내일 재실행하면 정확히 그 지점부터 이어받습니다.
DART_API_KEY = ""

# ── ② KRX 데이터 마켓플레이스 (2025-12 인증 방식 변경 대응) ─────────────────────────────────
#    가입: https://data.krx.co.kr  →  우측 상단 [회원가입] (무료) → 아래에 ID/PW 입력
#
#    ▶ 비워두셔도 됩니다. 유니버스의 정확성은 상장일·폐지일(FDR/KIND)만으로 성립하도록
#      설계되어 있고, KRX 는 '검증·보강'입니다. 비우면 그 단계만 건너뜁니다.
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패합니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""
KRX_OPENAPI_KEY    = ""   # (선택) KRX Open API 인증키. 엔드포인트별 '이용신청'이 따로 필요하고
                          #        승인에 하루 정도 걸립니다. 키만으론 즉시 안 됩니다.

# ── ③ 공공데이터포털 (선택 — 정부 R&D 과제 대조용) ──────────────────────────────────────────
#    발급: https://www.data.go.kr → 로그인 → API 상세 → [활용신청]
#          → 마이페이지 > 데이터활용 > Open API > 인증키
#    ★ 반드시 "일반 인증키(Decoding)" 값을 넣으세요. Encoding 키(%2B, %3D 포함)를 넣으면
#      이중 인코딩으로 항상 401/SERVICE_KEY_IS_NOT_REGISTERED 가 납니다.
DATA_GO_KR_KEY = ""
CUSTOMS_API_KEY = ""      # 이 전략은 사용하지 않습니다(공용 코어 호환용 자리표시자).

# ═══════════════════════════════════════════════════════════════════════════════════════════
#  ④ 캐시 — ★★★ 절대 1원칙 ★★★
#
#    · 읽기: 구글드라이브 + 로컬(D: 등) 양쪽을 모두 탐색합니다.
#    · 쓰기: 신규 수집분은 언제나 구글드라이브에만 씁니다. 로컬 미러는 구조적으로 읽기 전용
#            입니다(쓰기 API 자체가 로컬 미러 경로를 받지 않습니다).
#    · 기존 인덱스(공용/전용)는 절대 삭제·덮어쓰기하지 않습니다.
#        - 인덱스의 진실은 append-only JSONL 저널입니다(기존 줄을 재기록하지 않음)
#        - index.parquet 은 저널의 파생물이며 재생성 전 항상 타임스탬프 백업
#        - blob 은 내용해시 경로 → 같은 내용은 재기록조차 발생하지 않음
#        - 삭제 API 가 존재하지 않습니다. 손상 파일도 지우지 않고 .corrupt 로 격리만 합니다
#
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략(TCD 등)이 그대로 재사용 가능한 원본/정제본
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유의 피처/스코어/백테스트 산출물
# ═══════════════════════════════════════════════════════════════════════════════════════════

#  쓰기 루트 후보. 위에서부터 '이미 존재하고 _shared 인덱스가 들어 있는' 곳을 우선 채택하며,
#  하나도 없으면 첫 후보를 새로 만듭니다. (다른 전략이 쓰던 캐시를 자동으로 이어받습니다)
GDRIVE_ROOT        = ""            # 비워두면 아래 후보에서 자동 탐지. 직접 지정도 가능.
GDRIVE_ROOT_NAMES  = ["quant_cache", "tcd_cache", "qvf_cache"]   # MyDrive 하위 폴더 이름 후보
GDRIVE_SHARED_NS   = "_shared"     # → {ROOT}/_shared   (공용 — 전략 간 공유)
GDRIVE_PRIVATE_NS  = "qvf_v1"      # → {ROOT}/qvf_v1    (전용 — 이 전략)

#  ▸ 읽기 전용 미러. 로컬 D: 드라이브나 예전 캐시 폴더를 여기에 넣으면 탐색 대상에 포함됩니다.
#    ★ 없는 경로는 자동으로 건너뜁니다. D: 가 없는 PC나 Colab 에서는 구글드라이브만 탐색하며,
#      "로컬 미러 없음 — 드라이브만 탐색" 이라고 로그에 명시합니다. 설정을 지울 필요 없습니다.
CACHE_MIRROR_ROOTS = [
    "D:/quant_cache", "D:/tcd_cache", "D:/qvf_cache", "D:/cache",
    "E:/quant_cache",
    "./quant_cache", "./tcd_cache",
    # "/내가/쓰던/캐시/폴더",
]

#  ▸ 이미 리포트를 모아둔 '외부' 폴더가 있으면 여기에 추가하세요. 재귀 스캔해서 '등록만' 합니다.
#    (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록 — adopt-by-reference)
#    ★ 캐시 루트 자신(_shared/blob 등)은 넣지 마세요 — 이미 인덱스에 있고, 내용해시 2단 디렉터리라
#      드라이브 FUSE 에서 최대 65,536개 폴더를 열거하게 되어 몇 시간씩 멈춘 것처럼 보입니다.
#      코드가 관리 트리는 자동으로 제외하지만, 애초에 넣지 않는 것이 가장 안전합니다.
GDRIVE_ADOPT_DIRS = [
    "research", "reports", "consensus", "hankyung", "naver_research",
]

#  ▸ 기존 리포트 폴더 스캔 제어. 드라이브는 파일당 왕복 지연이 커서 상한이 반드시 필요합니다.
#    한 번 스캔한 디렉터리는 mtime 체크포인트로 기억해 다음 실행에서 건너뜁니다(이어받기).
ADOPT_SCAN_ENABLED     = True
ADOPT_SCAN_MAX_FILES   = 120_000    # 이 개수를 넘으면 중단하고 다음 실행에서 이어받습니다
ADOPT_SCAN_MAX_SECONDS = 240        # 시간 예산. 초과 시 깨끗하게 중단하고 진행률을 보고합니다

#  ▸ 드라이브를 못 찾았을 때의 로컬 폴백(그때만 쓰기 대상이 됩니다).
LOCAL_CACHE_ROOT  = "./qvf_cache"

# ── ⑤ 백테스트 구간 / 리밸런싱 ──────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"
REBAL_MONTHS   = (3, 6, 9, 12)      # §4 — 분기 1회: 3/1, 6/1, 9/1, 12/1
REBAL_DAY      = 1

# ── ⑥ 유니버스 U-1000 (§3) ──────────────────────────────────────────────────────────────────
U1000_N          = 1000             # PIT 시가총액 랭크 '하위' N종목 (KOSPI+KOSDAQ 통합)
ADTV_WINDOW_DAYS = 60               # §3.2 직전 60거래일
MIN_ADTV_KRW     = 100_000_000      # §3.2 1억원
SEASONING_DAYS   = 250              # §3.3 상장 12개월 미만 제외 (≈250거래일)

# ── ⑦ 1차필터 (§5) — 사전등록 가중치. 튜닝 금지 ─────────────────────────────────────────────
U200_N       = 200
VARIANTS     = ("V", "VQ", "VQF")
VARIANT_W    = {                    # (w_V, w_Q, w_F)
    "V":   (1.0, 0.0, 0.0),
    "VQ":  (0.5, 0.5, 0.0),
    "VQF": (0.4, 0.4, 0.2),
}
FLOW_WINDOW_DAYS = 60               # §5.4 수급 60일 창
WINSOR_PCT       = 0.01             # §5.2/5.3 상하위 1% 윈저라이징

# ── ⑧ 2차필터 (§6) — 사전등록 가중치. 튜닝 금지 ─────────────────────────────────────────────
SECOND_N        = 70                # §6.3 60~80 → 중앙값 70
SCORE2_W_NONFIN = 2.0
SCORE2_W_TONE   = 1.0
RELATED_PARTY_TOPQ = 0.20           # §6.1 특수관계자 비중 상승폭 상위 20%
CONTINGENT_EQ_PP   = 0.05           # §6.1 우발부채/지급보증 자기자본 대비 5%p
LAWSUIT_EQ_2ND     = 0.05           # §6.1 소송가액/자기자본 5%

# ── ⑨ 3차필터 3-A (§7.2) — 사전등록 임계값. 튜닝 금지 ───────────────────────────────────────
RULE_LAWSUIT_EQ      = 0.10         # 소송가액/자기자본 > 10% 제외
RULE_RELATED_SALES   = 0.30         # 특수관계자 매출 비중 > 30% 제외
RULE_MAJOR_HOLDER    = 0.15         # 최대주주 지분율 < 15% 제외
RULE_OP_LOSS_QUARTERS = 4           # 4개 분기 연속 영업적자 제외
RULE_IMPAIRMENT      = 0.30         # 자본잠식률 > 30% 제외

# ── ⑩ 포트폴리오 (§7.4) ─────────────────────────────────────────────────────────────────────
FINAL_N_MIN   = 20
FINAL_N       = 30                  # 기준값 (민감도 20/30/40 은 강건성에서 별도 검정)
FINAL_N_MAX   = 40
WEIGHT_SCHEMES = ("equal", "invvol")   # 동일가중(기준) + 역변동성(병행 산출)
INVVOL_WINDOW_DAYS = 120
ACCOUNT_KRW   = 100_000_000         # 슬리피지 참여율 계산용 가정 계좌 규모

# ── ⑪ 비용 모델 (§8.1) ──────────────────────────────────────────────────────────────────────
COMMISSION_BPS = 1.5                # 편도 위탁수수료(개인 온라인 가정), bp
SLIPPAGE_MODE  = "corwin_schultz"   # "corwin_schultz" | "amihud" | "fixed"
SLIPPAGE_FLOOR_BPS = 15.0           # 초소형주 최소 스프레드 가정 하한
SLIPPAGE_CAP_BPS   = 400.0          # 추정 스프레드 상한 (추정치 폭주 방지)
IMPACT_K       = 0.10               # 제곱근 시장충격 계수

# ── ⑫ 강건성 (§8.3 / §8.4) ──────────────────────────────────────────────────────────────────
BH_FDR_Q          = 0.10
SENS_U200_SIZES   = (150, 200, 300)
SENS_FINAL_SIZES  = (20, 30, 40)
SENS_FLOW_WINDOWS = (20, 60, 120)
SENS_REBAL_SHIFTS = (-5, 0, 5)      # 리밸런싱 시점 ±5거래일

# ── ⑬ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 8 이하로.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.0,
    "naver":     2.5,
    "krx":       2.0,
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0
CIRCUIT_BREAKER_FAILS = 40   # §0.3 서킷 브레이커: 한 수집 스테이지에서 연속 실패 N회 → 중단

# ── ⑭ 애널리스트 리포트 (§6.2) ──────────────────────────────────────────────────────────────
RESEARCH_COLLECT       = True    # False 면 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES       = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF  = True    # TONE 분류기는 PDF 본문이 있어야 제대로 학습됩니다
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000
TONE_RETRAIN_FREQ      = "Y"     # 확장윈도우 재학습 주기: "Y"(연) | "Q"(분기)
TONE_MIN_TRAIN_DOCS    = 400     # 이보다 적으면 그 시점 모델은 만들지 않고 ΔTONE=결측
IRC_TAG_PATTERN        = r"한국IR협의회|IR협의회|기업리서치센터"   # §0.4 기업의뢰형 태깅
IRC_EXCLUDE            = False   # 기준 실행은 포함. 강건성에서 포함/제외 양쪽 산출.

# ── ⑮ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전체 출력물을 예행연습 (수십 초). 네트워크/키 불필요.
#              Phase0~보고서까지 전부 나옵니다. 처음엔 이걸로 한 번 돌려보세요.
#    "FULL"  : 스모크 → 실경로 리허설 → 실데이터 수집 → 전체 파이프라인 (권장)
#    "CACHED": 스모크 → 리허설 → 캐시만 사용(신규 수집 안 함) → 전체 파이프라인
RUN_MODE = "FULL"

SEED = 20260810          # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True   # §10.4 사전등록 폐기 조건 위반 시 보고하고 중단

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID        = "QVF_FUNNEL_V1"
STRATEGY_NAME      = "가치·퀄리티·수급 깔때기 (U-1000 → U-200 → 60~80 → 20~40)"
BUILD_VERSION      = "qvf1.20260810.0457"
ACTIVE_PACKS: list = []          # 공용 코어 호환용(이 전략은 센서팩 구조를 쓰지 않습니다)

# 공용 코어(12_ingest_dart_fin)는 모듈 로드 시점에 DART_DAILY_LIMIT 를 19,000 으로 되돌려
# 놓습니다(조립 순서상 이 헤더보다 뒤). 사용자가 명시적으로 거부한 고정값이므로, 실측 소유자인
# DartQuota 가 생성 시점에 아래 '힌트'로 되찾아오고 020 을 확인하면 실측치로 다시 덮습니다.
# ★ 이 값은 '계획용 표시치'일 뿐이며 소비를 막지 않습니다(계약 Q12 가 강제).
DART_DAILY_LIMIT_HINT = 20_000
DART_DAILY_LIMIT = DART_DAILY_LIMIT_HINT


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
# ║  L0-G  다중루트 캐시 (구글드라이브 + 로컬 미러) · DART 동적 호출한도                        ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙의 구조적 보장 ★★★                                                        ║
# ║   · 읽기는 여러 루트에서, 쓰기는 오직 '드라이브 쓰기루트' 하나에서만 일어난다.              ║
# ║     로컬 미러가 읽기 전용인 것은 규율이 아니라 구조다 — 쓰기 함수(put_table/put_blob/      ║
# ║     flush/compact)는 self.root 만 사용하고, 미러 경로는 애초에 그 함수들에 도달하지 않는다.║
# ║   · 미러에서 찾은 항목은 인덱스에 '_root' 를 달고 들어오며, 실제 파일 해석도 그 루트를      ║
# ║     기준으로 한다. (미러 상대경로를 쓰기루트에 이어붙이는 순간 조용히 엉뚱한 파일을 연다)  ║
# ║   · 미러에만 있는 '테이블'은 드라이브로 승격 복사한다(원본은 그대로 둔다). 드라이브에       ║
# ║     이미 있으면 승격 자체가 일어나지 않으므로 최신본을 과거본으로 덮을 수 없다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def ro_read_parquet(path: str) -> Tuple[Optional[pd.DataFrame], str]:
    """읽기 전용 parquet 리더. (프레임, 상태). ★ 어떤 경우에도 파일을 건드리지 않는다.

    ★★ 왜 read_parquet_safe 를 쓰면 안 되는가 (적대적 감사가 실증한 치명 결함) ★★
      공용 코어의 read_parquet_safe 는 읽기에 실패하면 손상 추정 파일을 `.corrupt.<ts>` 로
      **개명**한다. 자기 캐시에는 타당한 처리지만, 미러(사용자의 로컬 D: 또는 다른 전략의
      드라이브 캐시)에 대고 실행하면 남의 파일을 파괴하는 것이다.
      게다가 실패 원인 1·2위가 이상 상황도 아니다:
        · Drive for Desktop / rclone 의 placeholder(구체화 전 0바이트)
        · 동기화가 진행 중인 부분 파일
      둘 다 ArrowInvalid 를 던진다. 즉 '정상 동작 중인 드라이브'가 곧 파괴 조건이다.
      → 미러는 반드시 이 함수로만 읽는다. 실패는 그냥 결측으로 돌린다.
    """
    try:
        st1 = os.stat(path)
        if st1.st_size == 0:
            return None, "empty(동기화 미완료 추정)"
        time.sleep(0.05)
        st2 = os.stat(path)
        if (st2.st_size, st2.st_mtime_ns) != (st1.st_size, st1.st_mtime_ns):
            return None, "syncing(동기화 진행 중)"
        with open(path, "rb") as f:
            blob = f.read()
        return pd.read_parquet(io.BytesIO(blob)), "ok"
    except Exception as e:                                      # noqa
        return None, type(e).__name__


def _expand(p: str) -> str:
    try:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(str(p))))
    except Exception:
        return str(p)


def _same_place_key(p: str):
    """경로의 '실체' 식별자. 문자열 비교로는 같은 폴더를 두 번 걷는 것을 못 막는다.

    ★ Colab 은 /content/drive/MyDrive 와 /content/drive/My Drive 를 '둘 다' 만든다.
      realpath 가 서로 다르게 나오므로 문자열 dedup 이 실패하고, 같은 트리를 두 번 스캔한다.
      드라이브 FUSE 에서 그건 그대로 2배의 시간이다. (st_dev, st_ino) 가 있으면 그걸 쓰고,
      없으면 'My Drive' → 'MyDrive' 정규화한 realpath 로 떨어진다.
    """
    try:
        st = os.stat(p)
        if st.st_ino:
            return ("ino", st.st_dev, st.st_ino)
    except Exception:
        pass
    rp = os.path.realpath(p).replace("/My Drive/", "/MyDrive/").replace("\\My Drive\\", "\\MyDrive\\")
    return ("path", os.path.normcase(rp))


def _drive_mount_points() -> List[Tuple[str, str]]:
    """(마운트경로, 라벨) 후보. Colab / Windows / macOS / Linux 전부를 커버한다.
    존재하지 않는 경로는 호출자가 걸러낸다."""
    home = os.path.expanduser("~")
    cands: List[Tuple[str, str]] = []

    if ENV["colab"]:
        cands.append(("/content/drive/MyDrive", "COLAB"))
        cands.append(("/content/drive/My Drive", "COLAB"))

    # Windows — Drive for Desktop 은 드라이브 문자로 붙는다. 한글 로케일은 '내 드라이브'.
    for dl in ("G:", "H:", "I:", "J:"):
        for leaf in ("My Drive", "내 드라이브"):
            cands.append((f"{dl}/{leaf}", "WIN_DRIVE_FS"))
    cands.append((os.path.join(home, "Google Drive", "My Drive"), "WIN_LEGACY"))

    # macOS — CloudStorage 는 계정별 폴더명이라 glob 로 찾는다.
    cands.append((os.path.join(home, "Google Drive", "My Drive"), "MAC"))
    try:
        import glob as _glob
        for p in _glob.glob(os.path.join(home, "Library", "CloudStorage", "GoogleDrive-*", "My Drive")):
            cands.append((p, "MAC_CLOUDSTORAGE"))
    except Exception:
        pass

    # Linux — rclone / insync / gdrive 관행 경로
    for leaf in ("GoogleDrive", "google-drive", "gdrive", "Google Drive"):
        cands.append((os.path.join(home, leaf), "LINUX_SYNC"))

    seen, out = set(), []
    for p, lab in cands:
        e = _expand(p)
        if e not in seen:
            seen.add(e)
            out.append((e, lab))
    return out


def _looks_like_cache_root(p: str) -> int:
    """캐시 루트다움 점수. 이미 공용 인덱스가 들어 있는 폴더를 최우선으로 고른다.
    (다른 전략이 쓰던 캐시를 그대로 이어받는 것이 사용자 요구사항이다)"""
    if not p or not os.path.isdir(p):
        return -1
    score = 0
    for sub, w in ((os.path.join(GDRIVE_SHARED_NS, "index", "index.jsonl"), 100),
                   (os.path.join(GDRIVE_SHARED_NS, "index", "index.parquet"), 60),
                   (os.path.join(GDRIVE_SHARED_NS, "table"), 30),
                   (os.path.join(GDRIVE_SHARED_NS, "blob"), 20),
                   (GDRIVE_PRIVATE_NS, 10)):
        if os.path.exists(os.path.join(p, sub)):
            score += w
    return score


def qvf_resolve_roots() -> Tuple[str, str, List[str]]:
    """(쓰기루트, 모드, 읽기전용 미러들).

    쓰기루트 선택 규칙:
      ① 사용자가 GDRIVE_ROOT 를 직접 지정했으면 그대로 (없으면 생성)
      ② 드라이브 마운트가 있으면 그 아래 GDRIVE_ROOT_NAMES 후보 중 '캐시다움 점수'가
         가장 높은 곳. 전부 비어 있으면 첫 이름으로 새로 만든다.
      ③ 드라이브가 없으면 LOCAL_CACHE_ROOT (그때만 로컬이 쓰기 대상이 된다)
    """
    # Colab 이면 먼저 마운트를 시도한다. 실패해도 죽지 않는다.
    if ENV["colab"] and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive as _gdrive          # type: ignore
            _gdrive.mount("/content/drive", force_remount=False)
        except Exception as e:                                  # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 진행합니다. "
                     f"Colab 이라면 셀 실행 시 뜨는 인증 팝업을 승인하세요.")

    mounts = [(p, lab) for p, lab in _drive_mount_points() if os.path.isdir(p)]

    write_root, mode = "", "LOCAL"
    if str(GDRIVE_ROOT or "").strip():
        write_root, mode = _expand(GDRIVE_ROOT), "EXPLICIT"
    else:
        best, best_s, best_lab = "", -1, ""
        for mp, lab in mounts:
            for nm in GDRIVE_ROOT_NAMES:
                cand = os.path.join(mp, nm)
                s = _looks_like_cache_root(cand)
                if s > best_s:
                    best, best_s, best_lab = cand, s, lab
        if best and best_s > 0:
            write_root, mode = best, f"DRIVE:{best_lab}(기존캐시 이어받기)"
        elif mounts:
            write_root, mode = os.path.join(mounts[0][0], GDRIVE_ROOT_NAMES[0]), \
                f"DRIVE:{mounts[0][1]}(신규)"
        else:
            write_root, mode = _expand(LOCAL_CACHE_ROOT), "LOCAL(드라이브 미발견)"

    try:
        os.makedirs(write_root, exist_ok=True)
    except Exception as e:                                      # noqa
        LOG.warn(f"쓰기루트 생성 실패({type(e).__name__}) — 로컬로 폴백합니다: {write_root}")
        write_root, mode = _expand(LOCAL_CACHE_ROOT), "LOCAL(쓰기루트 생성 실패)"
        os.makedirs(write_root, exist_ok=True)

    # 읽기 전용 미러: 사용자가 지정한 로컬 경로 + 드라이브의 다른 캐시 폴더들
    mirrors: List[str] = []
    for m in list(CACHE_MIRROR_ROOTS):
        e = _expand(m)
        if os.path.isdir(e) and os.path.realpath(e) != os.path.realpath(write_root):
            mirrors.append(e)
    for mp, _lab in mounts:
        for nm in GDRIVE_ROOT_NAMES:
            cand = os.path.join(mp, nm)
            if os.path.isdir(cand) and os.path.realpath(cand) != os.path.realpath(write_root):
                mirrors.append(_expand(cand))
    # 로컬 폴백 루트도 (쓰기루트가 아니라면) 읽기 대상에 넣는다
    lf = _expand(LOCAL_CACHE_ROOT)
    if os.path.isdir(lf) and os.path.realpath(lf) != os.path.realpath(write_root):
        mirrors.append(lf)

    seen, uniq = {_same_place_key(write_root)}, []
    for m in mirrors:
        k = _same_place_key(m)
        if k not in seen:
            seen.add(k)
            uniq.append(m)
    return write_root, mode, uniq


class QVFVault(Vault):
    """Vault + 다중루트 읽기. 쓰기 경로는 부모 그대로(=self.root 전용)라 미러는 절대 안 건드린다."""

    def __init__(self, root: str, mode: str, mirrors: Optional[Sequence[str]] = None,
                 promote_tables: bool = True):
        super().__init__(root, mode)
        # ★ 미러 중복제거는 생성자에서도 한 번 더 한다. qvf_resolve_roots 만 믿으면, 다른 경로로
        #   생성자를 부르는 순간(테스트·재구성) 같은 트리를 두 번 읽고 인덱스가 두 배가 된다.
        #   Colab 의 MyDrive / "My Drive" 처럼 문자열은 다른데 실체가 같은 경우가 실제로 있다.
        _seen = {_same_place_key(self.root)}
        _keep: List[str] = []
        _dupes: List[str] = []
        for m in (mirrors or []):
            if not m or not os.path.isdir(m):
                continue
            k = _same_place_key(m)
            if k in _seen:
                _dupes.append(m)
                continue
            _seen.add(k)
            _keep.append(m)
        if _dupes:
            LOG.info(f"쓰기루트와 같은 실체를 가리키는 미러 {len(_dupes)}개를 제외했습니다 "
                     f"(같은 트리를 두 번 읽지 않습니다): {_trunc(', '.join(_dupes[:3]), 60)}")
        self.mirrors: List[str] = _keep
        self.promote_tables = bool(promote_tables)
        self._mirror_idx: Dict[str, pd.DataFrame] = {}
        self.table_src: Dict[str, str] = {}          # 어느 루트가 이 테이블을 줬는가(감사용)
        self._own_only = False                       # compact 중 미러 행을 배제하기 위한 스위치
        self._merged: Dict[str, pd.DataFrame] = {}   # 미러 병합 결과 캐시(더티 시 무효화)
        self._uidpath: Dict[str, Dict[str, Tuple[str, str, str]]] = {}   # uid → 경로

    # ── 쓰기 경로 구조적 봉인 ----------------------------------------------------------
    def _wpath(self, path: str) -> str:
        """쓰기 대상 경로 검증. 쓰기루트 밖이면 예외. 상속받은 어떤 코드도 미러를 못 쓴다.
        ★ 주석으로 '도달하지 않는다'고 쓰는 것과, 도달하면 터지게 만드는 것은 다르다."""
        rp = os.path.realpath(path)
        root = os.path.realpath(self.root)
        if not (rp == root or rp.startswith(root + os.sep)):
            raise PermissionError(
                f"[절대 1원칙 위반 차단] 쓰기루트 밖 경로에 쓰려 했습니다: {path}\n"
                f"  쓰기루트: {self.root}\n"
                f"  미러는 읽기 전용입니다. 이 예외는 버그를 조용히 넘기지 않기 위한 것입니다.")
        return path

    def journal(self, scope: str) -> str:
        return self._wpath(super().journal(scope))

    def idx_parquet(self, scope: str) -> str:
        return self._wpath(super().idx_parquet(scope))

    def blob_dir(self, scope: str) -> str:
        return self._wpath(super().blob_dir(scope))

    def table_dir(self, scope: str) -> str:
        return self._wpath(super().table_dir(scope))

    # ── 미러 인덱스 (읽기 전용) ---------------------------------------------------------
    def _load_mirror_index(self, scope: str) -> pd.DataFrame:
        key = scope
        if key in self._mirror_idx:
            return self._mirror_idx[key]
        frames: List[pd.DataFrame] = []
        for mr in self.mirrors:
            base = os.path.join(mr, GDRIVE_SHARED_NS if scope == "shared" else GDRIVE_PRIVATE_NS)
            idx_dir = os.path.join(base, "index")
            if not os.path.isdir(idx_dir):
                continue
            got: List[pd.DataFrame] = []
            d, _st = ro_read_parquet(os.path.join(idx_dir, "index.parquet"))
            if d is not None and len(d):
                got.append(d)
            elif _st not in ("ok", "FileNotFoundError"):
                LOG.debug(f"미러 인덱스 읽기 건너뜀({_st}): {idx_dir} — 파일은 그대로 둡니다.")
            jr = read_jsonl(os.path.join(idx_dir, "index.jsonl"))
            if jr:
                got.append(pd.DataFrame(jr))
            if not got:
                continue
            allc: List[str] = []
            for g in got:
                for c in g.columns:
                    if c not in allc:
                        allc.append(c)
            g2 = pd.concat([g.reindex(columns=allc) for g in got], ignore_index=True)
            g2["_root"] = mr
            frames.append(g2)
            self.stats[f"mirror_index_read:{os.path.basename(mr)}"] += len(g2)
        if not frames:
            out = pd.DataFrame(columns=list(INDEX_COLUMNS) + ["_root"])
        else:
            allc = []
            for f in frames:
                for c in f.columns:
                    if c not in allc:
                        allc.append(c)
            out = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
            if "uid" not in out.columns:
                out["uid"] = np.nan
            miss = out["uid"].isna() | out["uid"].astype(str).str.strip().isin(("", "nan", "None"))
            if miss.any():
                src = [c for c in ("path", "abs_path", "key", "sha1", "_root") if c in out.columns]
                out.loc[miss, "uid"] = [
                    sha1_str("mirror", i, *[str(out.iloc[i].get(c, "")) for c in src])
                    for i in np.where(miss.to_numpy())[0]]
            out["uid"] = out["uid"].astype(str)
            out = out.drop_duplicates(subset=["uid"], keep="last").reset_index(drop=True)
        self._mirror_idx[key] = out
        return out

    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        own = super().load_index(scope, force=force)
        if self._own_only:
            return own
        if not force:
            cached = self._merged.get(scope)
            if cached is not None:
                return cached
        mir = self._load_mirror_index(scope)
        if mir.empty:
            self._merged[scope] = own
            return own
        o = own.copy()
        if "_root" not in o.columns:
            o["_root"] = self.root
        else:
            o["_root"] = o["_root"].fillna(self.root)
        allc: List[str] = []
        for f in (o, mir):
            for c in f.columns:
                if c not in allc:
                    allc.append(c)
        merged = pd.concat([o.reindex(columns=allc), mir.reindex(columns=allc)], ignore_index=True)
        # 쓰기루트(own)를 뒤에 두지 않는다 — 같은 uid 면 '쓰기루트 우선'이어야 하므로
        # keep="first" 로 own 이 이긴다.
        merged = merged.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)
        with self._lk:
            self._idx[scope] = merged
            self._uidset[scope] = set(merged["uid"].astype(str).tolist())
            self._merged[scope] = merged
        return merged

    # ── 다중루트 읽기 -------------------------------------------------------------------
    def get_table(self, name: str, scope: str = "shared",
                  max_age_days: Optional[float] = None) -> Optional[pd.DataFrame]:
        d = super().get_table(name, scope=scope, max_age_days=max_age_days)
        if d is not None:
            self.table_src[name] = self.root
            return d
        for mr in self.mirrors:
            for sc in (scope, "private" if scope == "shared" else "shared"):
                ns = GDRIVE_SHARED_NS if sc == "shared" else GDRIVE_PRIVATE_NS
                p = os.path.join(mr, ns, "table", f"{name}.parquet")
                if not os.path.exists(p):
                    continue
                if max_age_days is not None:
                    if (time.time() - os.path.getmtime(p)) / 86400.0 > max_age_days:
                        continue
                dd, _st = ro_read_parquet(p)
                if dd is None or not len(dd):
                    if _st not in ("ok", "FileNotFoundError"):
                        LOG.debug(f"미러 테이블 읽기 건너뜀({_st}): {p} — 파일은 그대로 둡니다.")
                    continue
                self.table_src[name] = mr
                self.stats[f"mirror_table_hit:{name}"] += 1
                LOG.info(f"로컬/미러 캐시 적중: {name} ({len(dd):,}행) ← {mr}")
                PIPE.io("IN", "MIRROR", f"table:{name}", dd, source=mr)
                if self.promote_tables:
                    # 드라이브에 '없을 때만' 승격한다 → 최신본을 과거본으로 덮을 수 없다.
                    try:
                        self.put_table(name, dd, scope=scope, domain="table",
                                       source=f"promoted_from_mirror:{os.path.basename(mr)}")
                        LOG.ok(f"  → 구글드라이브로 승격 복사 완료 (원본은 그대로 둡니다): {name}")
                    except Exception as e:                       # noqa
                        LOG.warn(f"  → 드라이브 승격 실패({type(e).__name__}) — 읽기만 하고 진행합니다.")
                return dd
        return None

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        rows = self.lookup(scope, uid=uid)
        if rows.empty:
            return None
        for _, r in rows.iterrows():
            base = str(r.get("_root") or self.root)
            cands = [r.get("abs_path")]
            rel = str(r.get("path") or "")
            if rel:
                cands.append(os.path.join(base, rel))
                if base != self.root:
                    cands.append(os.path.join(self.root, rel))
            for cand in cands:
                try:
                    if cand and isinstance(cand, str) and os.path.exists(cand):
                        return open(cand, "rb").read()
                except Exception:
                    continue
        return None

    # ── O(1) 인덱스 계층 -----------------------------------------------------------------
    #  ★ 공용 Vault 는 규모를 가정하지 않고 짜여 있다. 30만 행 인덱스 + 수만 건 blob 조회에서는
    #    그 가정이 그대로 병목이 된다. 세 곳을 상수시간으로 내린다(코어는 손대지 않는다):
    #      ① has()      : _pending 리스트 선형탐색 → uid 집합 조회. 신규 uid n 건이면 O(n²)→O(n)
    #      ② load_index : 호출마다 미러 재병합 → 더티 플래그 캐시
    #      ③ get_blob   : 전 인덱스 불리언 마스크 → uid→경로 사전
    def _register(self, scope: str, rec: dict):
        super()._register(scope, rec)
        self._merged.pop(scope, None)
        self._uidpath.pop(scope, None)

    def has(self, scope: str, uid: str) -> bool:
        if scope not in self._uidset:
            self.load_index(scope)
        with self._lk:
            # _register 가 이미 _uidset 에 넣으므로 pending 을 따로 훑을 필요가 없다.
            return str(uid) in self._uidset.get(scope, set())

    def _uid_path_map(self, scope: str) -> Dict[str, Tuple[str, str, str]]:
        m = self._uidpath.get(scope)
        if m is not None:
            return m
        idx = self.load_index(scope)
        m = {}
        if len(idx):
            root_col = (idx["_root"].astype(str) if "_root" in idx.columns
                        else pd.Series([self.root] * len(idx), index=idx.index))
            for u, ap, rel, rt in zip(idx["uid"].astype(str),
                                      idx.get("abs_path", pd.Series([""] * len(idx))).astype(str),
                                      idx.get("path", pd.Series([""] * len(idx))).astype(str),
                                      root_col):
                m[u] = (ap, rel, rt if rt and rt != "nan" else self.root)
        self._uidpath[scope] = m
        return m

    def get_blob(self, uid: str, scope: str = "shared") -> Optional[bytes]:
        ent = self._uid_path_map(scope).get(str(uid))
        if ent is None:
            return None
        ap, rel, base = ent
        cands = [ap]
        if rel and rel not in ("", "nan"):
            cands.append(os.path.join(base, rel))
            if base != self.root:
                cands.append(os.path.join(self.root, rel))
        for c in cands:
            try:
                if c and c not in ("", "nan") and os.path.exists(c):
                    return open(c, "rb").read()
            except Exception:
                continue
        return None

    # ── 기존 리포트 폴더 흡수 (드라이브 FUSE 안전판) --------------------------------------
    _MANAGED_DIRNAMES = {"blob", "table", "index", "_backup", "_locks", "reports"}
    _SKIP_DIRNAMES = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules",
                      ".cache", ".Trash", "$RECYCLE.BIN", "System Volume Information"}

    def _managed_keys(self) -> set:
        """쓰기루트·미러의 관리 트리. 여기는 이미 인덱스에 있으므로 절대 걷지 않는다."""
        out = set()
        for r in [self.root] + list(self.mirrors):
            out.add(_same_place_key(r))
            for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):
                p = os.path.join(r, ns)
                if os.path.isdir(p):
                    out.add(_same_place_key(p))
        return out

    def adopt_scan(self, dirs: Sequence[str], max_files: int = None,
                   max_seconds: float = None) -> pd.DataFrame:
        """기존에 모아둔 리포트를 '등록만' 한다. 이동·개명·삭제 없음.

        ★ 사용자의 실제 Colab 실행이 여기서 멈췄다. 원인은 하나가 아니라 넷이 겹친 것이었다:
          ① 캐시 루트 자신을 스캔했다 → blob 은 내용해시 2단이라 최대 65,536개 디렉터리이고
             드라이브 FUSE 에서 listdir 한 번이 50~200ms 다. 열거만 1~2시간인데,
             그 파일들은 '이미 인덱스에 있는 것'이라 전부 무의미한 작업이다.
          ② /content/drive/MyDrive 와 /content/drive/My Drive 를 중복 스캔했다.
          ③ 파일마다 getsize() 로 FUSE 왕복이 한 번 더 붙었다.
          ④ 코어의 max_files 상한은 안쪽 for 만 끊고 os.walk 는 계속 돌았다.
        → 관리 트리 프루닝 + 실체 기준 중복제거 + scandir 1회 stat + '진짜' 상한 +
          디렉터리 mtime 체크포인트(재실행 시 이어받기) + 진행률 출력.
        """
        max_files = int(ADOPT_SCAN_MAX_FILES if max_files is None else max_files)
        max_seconds = float(ADOPT_SCAN_MAX_SECONDS if max_seconds is None else max_seconds)
        if not ADOPT_SCAN_ENABLED:
            LOG.info("ADOPT_SCAN_ENABLED=False — 기존 리포트 폴더 스캔을 건너뜁니다 "
                     "(인덱스에 이미 등록된 자료는 그대로 사용됩니다).")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])

        managed = self._managed_keys()
        roots, skipped_missing, skipped_managed = [], [], []
        seen_keys = set()
        for d in dirs:
            if not d:
                continue
            e = _expand(d)
            if not os.path.isdir(e):
                skipped_missing.append(d)
                continue
            k = _same_place_key(e)
            if k in managed:
                skipped_managed.append(e)
                continue
            if k in seen_keys:
                continue
            seen_keys.add(k)
            roots.append(e)

        if skipped_missing:
            LOG.info(f"존재하지 않는 스캔 경로 {len(skipped_missing)}개는 건너뜁니다"
                     f"(로컬 D: 가 없는 환경에서는 정상): "
                     f"{_trunc(', '.join(skipped_missing[:4]), 70)}")
        if skipped_managed:
            LOG.info(f"캐시 관리 트리 {len(skipped_managed)}개는 스캔 대상에서 제외합니다 — "
                     f"이미 인덱스에 있고, blob 은 내용해시 2단 구조라 드라이브에서 열거만 "
                     f"수 시간이 걸립니다.")
        if not roots:
            LOG.info("스캔할 외부 리포트 폴더가 없습니다. (기존 인덱스는 그대로 사용됩니다)")
            return pd.DataFrame(columns=["abs_path", "kind", "name"])

        # 디렉터리 mtime 체크포인트 — 바뀌지 않은 폴더는 다시 걷지 않는다
        ckpt: Dict[str, float] = {}
        cdf = self.get_table("qvf_adopt_scan_state", scope="private")
        if cdf is not None and len(cdf):
            try:
                ckpt = dict(zip(cdf["dirpath"].astype(str),
                                pd.to_numeric(cdf["mtime"], errors="coerce").fillna(-1.0)))
            except Exception:
                ckpt = {}
            LOG.info(f"이전 스캔 체크포인트 {len(ckpt):,}개 디렉터리 — 변경되지 않은 폴더는 "
                     f"다시 걷지 않습니다.")

        t0 = time.time()
        found: List[dict] = []
        new_ckpt: Dict[str, float] = dict(ckpt)
        n_files = n_dirs = n_skipped_dirs = 0
        stopped = ""

        for root in roots:
            if stopped:
                break
            LOG.info(f"기존 리포트 폴더 스캔: {root}")
            stack = [root]
            while stack:
                if time.time() - t0 > max_seconds:
                    stopped = f"시간 예산 {max_seconds:.0f}초 초과"
                    break
                if n_files >= max_files:
                    stopped = f"파일 상한 {max_files:,}건 도달"
                    break
                cur = stack.pop()
                try:
                    st_m = os.stat(cur).st_mtime
                except Exception:
                    continue
                n_dirs += 1
                if n_dirs % 200 == 0:
                    LOG.info(f"  … 디렉터리 {n_dirs:,} · 파일 {n_files:,} · "
                             f"{time.time()-t0:.0f}초 경과")
                unchanged = (abs(ckpt.get(cur, -1.0) - st_m) < 1e-6)
                new_ckpt[cur] = st_m
                try:
                    with os.scandir(cur) as it:
                        for ent in it:
                            try:
                                if ent.is_dir(follow_symlinks=False):
                                    nm = ent.name
                                    if (nm.startswith(".") or nm in self._MANAGED_DIRNAMES
                                            or nm in self._SKIP_DIRNAMES):
                                        n_skipped_dirs += 1
                                        continue
                                    if _same_place_key(ent.path) in managed:
                                        n_skipped_dirs += 1
                                        continue
                                    stack.append(ent.path)
                                    continue
                                if unchanged:
                                    continue          # 내용이 안 바뀐 폴더의 파일은 건너뛴다
                                low = ent.name.lower()
                                if low.endswith(".pdf"):
                                    kind = "report_pdf"
                                elif low.endswith((".parquet", ".jsonl", ".json", ".csv")) and \
                                        any(t in low for t in
                                            ("report", "consensus", "research", "analyst",
                                             "hankyung", "naver", "dart", "krx", "price",
                                             "ohlcv", "universe", "fnltt")):
                                    kind = "table_like"
                                else:
                                    continue
                                try:
                                    sz = ent.stat(follow_symlinks=False).st_size
                                except Exception:
                                    sz = -1
                                found.append({"abs_path": ent.path, "kind": kind,
                                              "name": ent.name, "dir": cur, "bytes": sz})
                                n_files += 1
                                if n_files >= max_files:
                                    break
                            except Exception:
                                continue
                except Exception as e:                              # noqa
                    LOG.debug(f"  디렉터리 열람 실패({type(e).__name__}): {cur}")
                    continue

        dur = time.time() - t0
        if not found:
            LOG.info(f"새로 등록할 리포트 파일이 없습니다 (디렉터리 {n_dirs:,}개 · {dur:.1f}초"
                     + (f" · {stopped}" if stopped else "") + "). "
                     f"이미 인덱스에 있는 자료는 그대로 사용됩니다.")
        else:
            df = pd.DataFrame(found)
            for r in df.itertuples(index=False):
                m = self._DATE_PAT.search(r.name) or self._DATE_PAT.search(r.dir)
                ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
                self.adopt(r.abs_path, domain="research" if r.kind == "report_pdf" else "table",
                           subtype=r.kind, key=r.name, source="preexisting_drive_cache",
                           event_date=ed, knowledge_date=ed, scope="shared",
                           extra={"dir": r.dir})
            self.flush("shared")
            LOG.ok(f"기존 리포트 {len(df):,}건을 공용 인덱스에 '참조 등록'했습니다 "
                   f"(파일은 원위치 그대로, 이동·삭제 없음) — "
                   f"디렉터리 {n_dirs:,}개 · {dur:.1f}초")

        if stopped:
            LOG.warn(f"스캔을 중단했습니다: {stopped}. 여기까지의 체크포인트를 저장했으므로 "
                     f"다음 실행에서 걷지 않은 폴더부터 이어받습니다. 상한을 늘리려면 "
                     f"ADOPT_SCAN_MAX_FILES / ADOPT_SCAN_MAX_SECONDS 를 조정하세요.")
        try:
            self.put_table("qvf_adopt_scan_state",
                           pd.DataFrame({"dirpath": list(new_ckpt.keys()),
                                         "mtime": list(new_ckpt.values())}),
                           scope="private", domain="index", source="adopt_scan checkpoint")
        except Exception as e:                                      # noqa
            LOG.debug(f"스캔 체크포인트 저장 실패({type(e).__name__}) — 기능에 영향 없음")
        return pd.DataFrame(found) if found else pd.DataFrame(columns=["abs_path", "kind", "name"])

    def compact(self, scope: str):
        """★ 미러 행을 드라이브 인덱스에 쓰면 안 된다.

        load_index 는 조회 편의를 위해 미러 행을 합쳐서 돌려주는데, 부모의 compact 는
        그 결과를 그대로 index.parquet 에 기록한다. 그러면 '로컬에만 존재하는 파일 경로'가
        공용 드라이브 인덱스에 박히고, 다른 기기·다른 전략이 그 경로를 열려다 실패한다.
        컴팩션 동안만 자기 루트 전용 모드로 내린다.
        """
        keep = self._own_only
        self._own_only = True
        try:
            super().compact(scope)
        finally:
            self._own_only = keep
            self._idx.pop(scope, None)      # 합쳐진 조회용 뷰를 다음 조회에서 재구성
            self._uidset.pop(scope, None)
            self._merged.pop(scope, None)
            self._uidpath.pop(scope, None)

    def report_roots(self):
        rows = [["쓰기 루트 (신규 수집분 저장)", self.root, self.mode]]
        for m in self.mirrors:
            rows.append(["읽기 전용 미러", m, "탐색만 — 절대 쓰지 않음"])
        missing = [m for m in CACHE_MIRROR_ROOTS if not os.path.isdir(_expand(m))]
        if missing:
            rows.append(["(없음 — 건너뜀)", _trunc(", ".join(missing), 44),
                         "이 환경에 없는 경로. 정상입니다"])
        LOG.table(rows, ["역할", "경로", "비고"], ["l", "l", "l"],
                  title="캐시 루트 구성 (로컬·드라이브 양쪽 탐색 → 신규는 드라이브에만 기록)")
        if not self.mirrors:
            LOG.info("읽기 전용 미러가 없습니다 — 구글드라이브만 탐색합니다. "
                     "로컬 D: 가 없는 PC나 Colab 에서는 정상이며, 기능에 영향이 없습니다. "
                     "다른 PC의 로컬 캐시를 함께 쓰려면 CACHE_MIRROR_ROOTS 에 경로를 "
                     "추가하세요(탐색만 하고 절대 쓰지 않습니다).")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  DART 일일 호출한도 — 고정값이 아니라 '실측·발견'                                          ║
# ║                                                                                          ║
# ║  사실 확인: OpenDART 는 잔여 호출량을 알려주는 엔드포인트나 응답필드/헤더를 제공하지        ║
# ║  않는다. 확인 가능한 신호는 한도 초과 시 돌아오는 status="020" 뿐이다.                     ║
# ║  → 따라서 '남은 양'은 조회하는 것이 아니라 다음 방식으로 실측한다:                          ║
# ║     ① 같은 키를 쓰는 모든 전략이 공용 저널에 사용량을 append 한다 (전략 간 합산)            ║
# ║     ② 020 을 처음 만난 순간의 누적 사용량 = 그날의 실측 상한. 저널에 기록한다.              ║
# ║     ③ 과거에 실측된 상한이 있으면 그것을 '계획용 추정치'로 쓰되, 소비는 020 이 실제로       ║
# ║        올 때까지 계속한다. 추정치 때문에 남은 호출을 못 쓰는 일이 없다.                     ║
# ║     ④ 상한이 아직 미확정이면 '미확정'이라고 표시한다. 20,000 같은 숫자를 지어내지 않는다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class DartQuota:
    """DartBudget 의 드롭인 대체(take/refund/close/n/exhausted 동일 인터페이스).

    ★ 공용 스코프에 기록하는 이유: 하나의 DART 키를 여러 전략(TCD, QVF …)이 나눠 쓰면
      전략별 사설 카운터는 서로를 못 본다. 그러면 각자 '아직 여유 있다'고 믿으면서
      합계로는 한도를 넘겨 020 폭풍을 맞는다.
    """

    FLUSH_EVERY = 200
    # DART 한도는 한국시간 자정에 리셋된다. 로컬시간을 쓰면 Colab(UTC)에서 9시간 어긋나고,
    # 구축 시점에 한 번만 계산하면 자정을 넘긴 장시간 실행이 '어제 한도'에 계속 묶인다.
    KST = _dt.timezone(_dt.timedelta(hours=9))

    @staticmethod
    def _day_key() -> str:
        return _dt.datetime.now(DartQuota.KST).date().isoformat()

    def __init__(self, vault: "Vault"):
        self.vault = vault
        self.today = self._day_key()
        self.key_fp = sha1_str("dartkey", DART_API_KEY or "")[:12]
        self.n = 0                     # 이번 프로세스가 쓴 양
        self.n_other = 0               # 같은 키로 오늘 다른 프로세스/전략이 쓴 양
        self.observed_limit: Optional[int] = None   # 오늘 실측된 상한
        self.hist_limit: Optional[int] = None       # 과거 실측 상한(계획용 추정치)
        self._exhausted = False
        self._lk = threading.RLock()
        self._unflushed = 0
        self._probe_at = 0.0
        self._load()
        # 공용 코어(12_ingest_dart_fin)가 모듈 로드 시점에 DART_DAILY_LIMIT 를 19,000 으로
        # 되돌려 놓는다(조립 순서상 헤더보다 뒤). 사용자가 명시적으로 거부한 값이므로
        # 실측 소유자인 이 클래스가 되찾아온다. 실측되면 그 값으로 다시 덮인다.
        globals()["DART_DAILY_LIMIT"] = int(self.hist_limit or DART_DAILY_LIMIT_HINT)

    def _roll_if_needed(self):
        """자정(KST)을 넘겼으면 카운터를 새 날짜로 되돌린다. 며칠에 걸친 콜드빌드에서
        '어제 소진'을 오늘까지 끌고 가 하루를 통째로 버리는 사고를 막는다."""
        d = self._day_key()
        if d == self.today:
            return
        self._flush_locked()
        LOG.ok(f"DART 한도 리셋 감지 (KST {self.today} → {d}) — 카운터를 초기화하고 계속합니다.")
        self.today = d
        self.n = 0
        self.n_other = 0
        self.observed_limit = None
        self._exhausted = False
        self._unflushed = 0

    # -- 저널 ---------------------------------------------------------------------------
    def _path(self) -> str:
        return os.path.join(self.vault.ns["shared"], "index", "dart_quota.jsonl")

    def _mirror_paths(self) -> List[str]:
        out = []
        for mr in getattr(self.vault, "mirrors", []) or []:
            p = os.path.join(mr, GDRIVE_SHARED_NS, "index", "dart_quota.jsonl")
            if os.path.exists(p):
                out.append(p)
        return out

    def _load(self):
        rows: List[dict] = []
        for p in [self._path()] + self._mirror_paths():
            rows.extend(read_jsonl(p))
        mine_pid = os.getpid()
        for r in rows:
            if str(r.get("key_fp")) != self.key_fp:
                continue
            if r.get("event") == "limit_observed":
                try:
                    lim = int(r.get("limit", 0))
                except Exception:
                    continue
                if lim > 0:
                    self.hist_limit = max(self.hist_limit or 0, lim)
                    if str(r.get("date")) == self.today:
                        self.observed_limit = lim
                        self._exhausted = True
            elif r.get("event") == "use" and str(r.get("date")) == self.today:
                try:
                    k = int(r.get("n", 0))
                except Exception:
                    k = 0
                # 같은 pid 의 기록은 재실행 시 '남이 쓴 양'으로 다시 세면 안 되지만,
                # 프로세스가 죽었다 살아난 경우엔 실제로 소비된 양이므로 세는 게 맞다.
                # 보수적으로(=과다계상 방향) 전부 센다. 과소계상은 020 폭풍을 부른다.
                self.n_other += max(0, k)
        if self.n_other:
            LOG.info(f"오늘 이 DART 키로 이미 사용된 호출 {self.n_other:,}건 "
                     f"(다른 전략/이전 실행 포함, 공용 저널 기준) — 이어서 진행합니다.")
        if self.observed_limit:
            LOG.warn(f"오늘({self.today}) 이 키의 실측 한도 {self.observed_limit:,}건에 이미 "
                     f"도달한 기록이 있습니다. DART 신규 수집은 건너뛰고 캐시로 진행합니다. "
                     f"내일 재실행하면 정확히 이 지점부터 이어받습니다.")
        elif self.hist_limit:
            LOG.info(f"과거 실측된 일일 한도 {self.hist_limit:,}건을 '계획용 추정치'로만 씁니다. "
                     f"실제 소비는 서버가 020(한도초과)을 줄 때까지 계속합니다 — "
                     f"추정치 때문에 남은 호출을 놀리지 않습니다.")
        else:
            LOG.info("이 키의 일일 한도 실측 기록이 아직 없습니다. OpenDART 는 잔여량 조회 API 를 "
                     "제공하지 않으므로, 서버가 020 을 줄 때까지 소비하며 그 지점을 한도로 "
                     "기록합니다(다음 실행부터 계획에 반영됩니다).")

    def _append(self, rec: dict):
        rec = {"date": self.today, "key_fp": self.key_fp, "pid": os.getpid(),
               "host": platform.node(), "ts": _dt.datetime.now().isoformat(timespec="seconds"),
               **rec}
        try:
            with self.vault.lock("dart_quota", timeout=15.0):
                append_jsonl(self._path(), [rec])
        except Exception:
            try:
                append_jsonl(self._path(), [rec])
            except Exception:
                pass

    # -- 인터페이스 ---------------------------------------------------------------------
    @property
    def used_today(self) -> int:
        return self.n + self.n_other

    @property
    def exhausted(self) -> bool:
        return self._exhausted

    @exhausted.setter
    def exhausted(self, v: bool):
        """★ 공용 코어(dart_api)가 status 020/021 을 보면 여기에 True 를 넣는다.
        그 순간의 누적 사용량이 곧 '오늘의 실측 한도'다. 이 setter 가 발견 지점이다."""
        v = bool(v)
        if not v:
            self._exhausted = False
            return
        if self._exhausted:
            return
        # ★ 공용 코어는 020(일일한도 초과)과 021(조회 가능 회사 수 초과)을 같은 분기에서
        #   처리하며 둘 다 여기로 True 를 보낸다. 그런데 021 은 '요청이 잘못됐다'는 뜻이지
        #   한도와 아무 상관이 없다. 이를 한도로 기록하면 (a) 남은 호출을 전부 못 쓰고
        #   (b) 그 거짓 상한이 공용 저널에 박혀 내일 이후 실행과 '다른 전략'까지 오염된다.
        #   → 값싼 확인 호출을 한 번 던져 진짜 020 인지 확증한 뒤에만 기록한다.
        self._exhausted = True                      # 확인 전까지는 잠정 정지(호출 폭주 방지)
        if not self._confirm_exhaustion():
            self._exhausted = False
            LOG.warn("DART 오류를 받았지만 확인 호출이 성공했습니다 — 일일한도(020)가 아니라 "
                     "요청 오류(021 등)로 판단하고 수집을 계속합니다. 한도로 기록하지 않습니다.")
            return
        self.observed_limit = int(self.used_today)
        self._flush()
        self._append({"event": "limit_observed", "limit": int(self.observed_limit)})
        globals()["DART_DAILY_LIMIT"] = int(self.observed_limit)
        LOG.warn(f"DART 일일 한도 실측: {self.observed_limit:,}건에서 020(한도초과)을 확인했습니다. "
                 f"여기까지 받은 데이터는 캐시에 저장되어 있으며, 내일 재실행하면 정확히 "
                 f"이 지점부터 이어받습니다. (한도값을 코드에 고정하지 않고 실측한 값입니다)")

    def _confirm_exhaustion(self) -> bool:
        """가장 값싼 정상 요청을 한 번 던져 020 이 재현되는지 본다. True = 진짜 한도 소진."""
        now = time.monotonic()
        if now - self._probe_at < 30.0:
            return True                              # 직전에 확인함 — 중복 확인 금지
        self._probe_at = now
        if not DART_API_KEY:
            return True
        try:
            d = (_dt.datetime.now(self.KST) - _dt.timedelta(days=3)).strftime("%Y%m%d")
            js = http_json("https://opendart.fss.or.kr/api/list.json", source="dart", tries=1,
                           params={"crtfc_key": DART_API_KEY, "bgn_de": d, "end_de": d,
                                   "page_no": 1, "page_count": 1},
                           referer="https://opendart.fss.or.kr/")
        except Exception:
            return True                              # 확인 불가 → 보수적으로 소진 처리
        if not isinstance(js, dict):
            return True
        st = str(js.get("status", ""))
        # 000(정상) 또는 013(데이터 없음)이면 키는 살아 있다 = 한도 소진이 아니다.
        return st not in ("000", "013")

    def take(self, k: int = 1) -> bool:
        if not DART_API_KEY:
            return False
        with self._lk:
            self._roll_if_needed()
            if self._exhausted:
                return False
            # 과거 실측 상한이 있으면 '거기서 멈추지 않고' 계속 쓴다(§요구사항).
            # 다만 추정치의 2배를 넘어서면 저널이 오염됐을 가능성이 크므로 안전 정지한다.
            if self.hist_limit and self.used_today > self.hist_limit * 2:
                LOG.warn(f"누적 사용량({self.used_today:,})이 과거 실측 한도({self.hist_limit:,})의 "
                         f"2배를 넘었습니다. 저널 오염 가능성이 있어 안전 정지합니다.")
                self._exhausted = True
                return False
            self.n += k
            self._unflushed += k
            if self._unflushed >= self.FLUSH_EVERY:
                self._flush_locked()
            return True

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)
            self._unflushed = max(0, self._unflushed - k)

    def _flush_locked(self):
        if self._unflushed <= 0:
            return
        k, self._unflushed = self._unflushed, 0
        self._append({"event": "use", "n": int(k)})

    def _flush(self):
        with self._lk:
            self._flush_locked()

    def remaining_str(self) -> str:
        if self.observed_limit is not None:
            return f"0 (오늘 실측 한도 {self.observed_limit:,} 도달)"
        if self.hist_limit:
            return f"약 {max(0, self.hist_limit - self.used_today):,} (과거 실측 {self.hist_limit:,} 기준 추정)"
        return "미확정 (OpenDART 는 잔여량 API 를 제공하지 않음 — 020 수신 시 확정)"

    def report(self):
        LOG.table([["오늘 날짜", self.today],
                   ["키 지문", self.key_fp or "(키 없음)"],
                   ["이번 실행 사용", f"{self.n:,}"],
                   ["오늘 누적 사용(공용 저널)", f"{self.used_today:,}"],
                   ["오늘 실측 한도", f"{self.observed_limit:,}" if self.observed_limit else "미도달"],
                   ["과거 실측 한도", f"{self.hist_limit:,}" if self.hist_limit else "기록 없음"],
                   ["남은 호출량", self.remaining_str()]],
                  ["항목", "값"], ["l", "r"],
                  title="DART 호출량 (고정 상수가 아니라 실측 — 공용 저널로 전략 간 합산)")

    def close(self):
        self._flush()


DQUOTA: Optional["DartQuota"] = None


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
DART_DAILY_LIMIT = 19_000                 # 공식 20,000 대비 여유
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
    """일일 호출 한도를 드라이브에 영속 기록. 재실행 시 이어받기의 근거가 된다."""

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
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.n + k > DART_DAILY_LIMIT:
                if not self.exhausted:
                    self.exhausted = True
                    LOG.warn(f"DART 일일 호출 한도({DART_DAILY_LIMIT:,})에 도달했습니다. "
                             f"여기까지 받은 데이터는 드라이브에 저장되어 있으니, "
                             f"내일 같은 코드를 다시 실행하면 정확히 이 지점부터 이어받습니다.")
                return False
            self.n += k
            if self.n % 500 == 0:
                self._save()
            return True

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
                 f"(오늘 가용 호출 {max(0, DART_DAILY_LIMIT - (DBUDGET.n if DBUDGET else 0)):,}건)")
        if total_needed > DART_DAILY_LIMIT:
            LOG.warn(f"필요 호출({total_needed:,})이 일일 한도({DART_DAILY_LIMIT:,})를 초과합니다. "
                     f"오늘 받을 수 있는 만큼 받고 저장합니다. "
                     f"약 {math.ceil(total_needed / DART_DAILY_LIMIT)}일에 걸쳐 콜드빌드가 완성됩니다. "
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



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q1  분기 리밸런싱 캘린더 · PIT 시가총액 · U-1000 유니버스 (§3, §4)                      ║
# ║                                                                                          ║
# ║  시점 규약(§4)을 코드로 못박는다:                                                          ║
# ║    signal_date = 리밸런싱일(3/1·6/1·9/1·12/1) 직전 거래일  ← 가격/수급은 t-1 종가까지만     ║
# ║    exec_date   = 리밸런싱일 이후 첫 거래일의 '시가'로 체결                                  ║
# ║  둘을 분리하지 않으면 '오늘 종가를 보고 오늘 종가에 산다'가 되어 곧바로 미래누수다.          ║
# ║                                                                                          ║
# ║  시가총액은 반드시 PIT 여야 한다. 현재 시점 시총으로 과거 랭크를 만들면 (a) 그 사이 급등한  ║
# ║  종목이 과거에 대형주였던 것처럼 취급되고 (b) 폐지 종목은 시총이 없어 통째로 사라진다.      ║
# ║  → 두 번째가 곧 생존자편향이다. 그래서 폐지 종목의 시총도 '살아 있던 시점 기준'으로 만든다. ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 20_pit.Universe 가 읽는 시즈닝 상수를 헤더 설정과 일치시킨다(Universe 생성 전에 적용된다).
LISTING_SEASONING_DAYS = SEASONING_DAYS

# ── 키 컬럼은 절대 category 로 만들지 않는다 ────────────────────────────────────────────────
#  ★ 공용 downcast_q() 는 저카디널리티 object 컬럼을 category 로 바꿔 RAM 을 크게 줄인다.
#    그런데 category Series 에 .map() 을 걸면 결과도 category 로 나온다. 그 결과가 날짜라면
#    `ld >= dl - 15일` 같은 비교에서 "Unordered Categoricals can only compare equality" 로
#    죽고, 하필 그 코드가 '보유 중 상장폐지 처리'라 생존자편향 방어가 통째로 무너진다.
#    (실제로 계약 Q3 가 이 경로를 잡아냈다)
#    merge/merge_asof 의 결합키가 한쪽만 category 인 경우에도 조용히 어긋날 수 있다.
#    → 키·식별자 컬럼만 문자열로 되돌린다. 수치 컬럼의 다운캐스트 이득은 그대로 남는다.
_NEVER_CAT = ("code", "corp_code", "rcept_no", "report_uid", "analyst_id", "stock_code",
              "broker_id", "src_cap", "exit_kind", "flow_src", "parse_status")


def downcast_q(df: pd.DataFrame) -> pd.DataFrame:
    d = downcast(df)
    if d is None or d.empty:
        return d
    for c in _NEVER_CAT:
        if c in d.columns and str(d[c].dtype) == "category":
            d[c] = d[c].astype(str)
    return d

# ── §4 시점 규약: "공시는 rcept_dt + 1거래일부터 사용 가능" ──────────────────────────────────
#  ★ 공용 코어(12_ingest_dart_fin)는 knowledge_date = 접수일자(rcept_dt) 그대로 쓴다.
#    접수는 장중에도 일어나므로 '접수일 종가 기준 신호'에 그 공시를 쓰면 아주 작지만 실재하는
#    누수가 된다. QVF 는 규약대로 한 거래일을 더 민다. 캘린더 하루가 아니라 '거래일' 하루다 —
#    연휴 앞 금요일 접수분을 토요일부터 알 수 있다고 처리하면 결국 같은 누수가 남는다.
QVF_TRADING_DAYS: np.ndarray = np.array([], dtype="datetime64[ns]")


def set_trading_days(px_daily: pd.DataFrame):
    globals()["QVF_TRADING_DAYS"] = qvf_trading_days(px_daily)
    LOG.debug(f"거래일 캘린더 확정: {len(QVF_TRADING_DAYS):,}일")


def next_trading_day(x):
    """x 이후(초과) 첫 거래일. 거래일 배열이 아직 없으면 영업일(Mon-Fri) +1 로 폴백한다."""
    t = as_ts(x)
    if t is None:
        return None
    td = QVF_TRADING_DAYS
    if len(td):
        i = int(np.searchsorted(td, np.datetime64(t), side="right"))
        if i < len(td):
            return as_ts(td[i])
    return (t + pd.offsets.BDay(1)).normalize()


def next_trading_day_series(s) -> pd.Series:
    """벡터화판. 40만 행에 파이썬 루프를 돌리지 않기 위해 searchsorted 를 한 번만 쓴다."""
    v = as_ts_series(s)
    td = QVF_TRADING_DAYS
    if not len(td):
        return (v + pd.offsets.BDay(1)).dt.normalize()
    arr = v.to_numpy(dtype="datetime64[ns]")
    idx = np.searchsorted(td, arr, side="right")
    inside = (idx < len(td)) & ~pd.isna(v).to_numpy()
    out = np.full(len(v), np.datetime64("NaT"), dtype="datetime64[ns]")
    out[inside] = td[idx[inside]]
    res = pd.Series(out, index=v.index)
    # 배열 끝을 넘어선 최근 공시는 영업일 +1 로 보수적으로 처리한다.
    tail = v.notna() & res.isna()
    if tail.any():
        res.loc[tail] = (v[tail] + pd.offsets.BDay(1)).dt.normalize()
    return res


def dart_knowledge_date(rcept_no: Any, reprt_code: str, year: int) -> pd.Timestamp:
    """접수일자 → 사용가능일(= 접수일 다음 거래일). §4 규약."""
    return next_trading_day(_knowledge_from_rcept(rcept_no, reprt_code, int(year)))


def apply_t_plus_1(df: pd.DataFrame, label: str = "") -> pd.DataFrame:
    """공용 코어가 만든 PIT 테이블의 knowledge_date 를 §4 규약(+1거래일)으로 민다.

    ★ event_date 는 건드리지 않는다. 밀어야 하는 것은 '언제 알 수 있었나' 뿐이다.
    """
    if df is None or not len(df) or "knowledge_date" not in df.columns:
        return df
    d = df.copy()
    before = as_ts_series(d["knowledge_date"])
    d["knowledge_date"] = next_trading_day_series(before)
    moved = int((d["knowledge_date"] > before).sum())
    if moved:
        LOG.debug(f"§4 규약 적용({label}): knowledge_date 를 +1거래일 이동 {moved:,}행")
    return d

# 우선주 / 스팩 / 리츠 / ETF·ETN 판별 ------------------------------------------------------
#  ★ 종목코드 6번째 자리 규칙: 보통주는 '0'. 구형 우선주는 5/7/9, 2024 개편 신형은 K/L/M/N.
#    이름만으로 거르면 '삼성전자우' 는 잡아도 '현대차2우B' 같은 변형에서 새고,
#    코드만으로 거르면 6자리 영숫자 신형에서 샌다. 둘을 OR 로 묶는다.
_PREF_NAME_RE = re.compile(r"우(?:B|C)?$|\d+우(?:B|C)?$|우선주")
_SPAC_RE = re.compile(r"스팩|기업인수목적")
_REIT_RE = re.compile(r"리츠|위탁관리부동산투자|기업구조조정부동산투자|부동산투자회사")
_FUND_RE = re.compile(r"^(KODEX|TIGER|KBSTAR|ARIRANG|KINDEX|HANARO|SOL |ACE |PLUS |RISE |"
                      r"KOSEF|TREX|FOCUS|마이다스|파워|미래에셋TIGER)|ETN$|ETF$|"
                      r"레버리지$|인버스$|선물\s*ETN")


def is_preferred(code: str, name: str = "") -> bool:
    c = str(code or "")
    if len(c) == 6 and c[5] not in ("0",):
        # 신형 영숫자 코드는 6번째가 0/K/L/M/N 이고 0 만 보통주다. 구형은 0 이 보통주.
        return True
    return bool(_PREF_NAME_RE.search(str(name or "")))


def classify_exclusion(code: str, name: str) -> str:
    """이름·코드만으로 판별 가능한 구조적 제외 사유. 없으면 빈 문자열."""
    nm = str(name or "").strip()
    if is_preferred(code, nm):
        return "우선주"
    if _SPAC_RE.search(nm):
        return "스팩"
    if _REIT_RE.search(nm):
        return "리츠"
    if _FUND_RE.search(nm):
        return "ETF/ETN"
    return ""


# ── 거래일 캘린더 / 리밸런싱 격자 ────────────────────────────────────────────────────────────
def qvf_trading_days(px_daily: pd.DataFrame) -> np.ndarray:
    """전 종목 일봉에서 유도한 실제 거래일 배열. 공휴일 테이블을 따로 두지 않는다
    (테이블을 두면 그 테이블이 틀렸을 때 조용히 하루씩 밀린다)."""
    if px_daily is None or not len(px_daily):
        return np.array([], dtype="datetime64[ns]")
    d = as_ts_series(px_daily["date"]).dropna()
    return np.sort(pd.unique(d.values))


def qvf_rebal_calendar(px_daily: pd.DataFrame, start: str, end: str,
                       shift_days: int = 0) -> pd.DataFrame:
    """분기 리밸런싱 캘린더.

    shift_days: 강건성(§8.4 '리밸런싱 시점 ±5거래일')용. 거래일 기준으로 민다.
    반환 컬럼: rebal(명목일) · signal_date(직전 거래일) · exec_date(체결 거래일)
    """
    td = qvf_trading_days(px_daily)
    if not len(td):
        raise RuntimeError("거래일을 하나도 만들 수 없습니다 — 일봉 패널이 비었습니다.")
    s, e = as_ts(start), as_ts(end)
    nominal = [as_ts(f"{y}-{m:02d}-{REBAL_DAY:02d}")
               for y in range(s.year, e.year + 1) for m in REBAL_MONTHS]
    nominal = [d for d in nominal if s <= d <= e]

    rows = []
    n_td = len(td)
    for d in nominal:
        dd = np.datetime64(d)
        # 체결일 = 명목일 이후(포함) 첫 거래일
        i_exec = int(np.searchsorted(td, dd, side="left"))
        if i_exec >= n_td:
            continue                      # 패널 끝을 넘어선 리밸런싱은 만들지 않는다
        i_exec = max(0, min(n_td - 1, i_exec + int(shift_days)))
        # 신호일 = 체결일 '직전' 거래일. 반드시 strictly before 여야 한다(t-1 종가 규약).
        i_sig = i_exec - 1
        if i_sig < 0:
            continue
        rows.append({"rebal": d, "signal_date": as_ts(td[i_sig]), "exec_date": as_ts(td[i_exec])})
    cal = pd.DataFrame(rows)
    if cal.empty:
        raise RuntimeError("리밸런싱 캘린더가 비었습니다 — 백테스트 구간과 일봉 구간이 겹치지 않습니다.")
    # 방어: 신호일이 체결일보다 늦거나 같으면 그 자체로 미래누수다. 여기서 세운다.
    bad = cal["signal_date"] >= cal["exec_date"]
    if bad.any():
        raise RuntimeError(f"[시점규약 위반] signal_date >= exec_date 인 리밸런싱이 "
                           f"{int(bad.sum())}건 있습니다. 캘린더 구성이 잘못되었습니다.")
    LOG.ok(f"분기 리밸런싱 캘린더 {len(cal)}개 시점 "
           f"({cal['rebal'].min():%Y-%m} ~ {cal['rebal'].max():%Y-%m}"
           + (f", {shift_days:+d}거래일 이동" if shift_days else "") + ") — "
           f"신호는 직전 거래일 종가까지, 체결은 익 거래일 시가")
    return cal


# ── PIT 시가총액 / 상장주식수 ───────────────────────────────────────────────────────────────
def fetch_krx_cap_snapshots(dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    """★1순위: pykrx 전종목 시총 스냅샷. 날짜당 1~2호출로 전 종목을 받으므로 가장 싸고,
    '그 날 실제 시총'이라 정의상 PIT 이다.

    반환: code · snap_date · mktcap · shares
    """
    cols = ["code", "snap_date", "mktcap", "shares"]
    cached = VAULT.get_table("krx_marketcap_snapshots", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = as_ts_series(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        LOG.info(f"캐시에서 시가총액 스냅샷 {len(have)}개 시점 재사용")

    todo = [d for d in dates if as_ts(d).strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []
    if todo and pykrx_stock is None:
        LOG.warn("pykrx 가 없어 시총 스냅샷을 받지 못합니다 — DART 주식총수 경로로 폴백합니다.")
        todo = []
    if todo:
        KRXG.warmup()

    new_rows: List[dict] = []
    if todo:
        LOG.info(f"KRX 전종목 시가총액 스냅샷 {len(todo)}개 시점 수집 (직렬 — 세션 충돌 방지)")
        streak = 0
        for d in tqdm(todo, desc="시총 스냅샷", ncols=88, leave=False):
            bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                           as_ts(d).strftime("%Y%m%d"), prev=True) or as_ts(d).strftime("%Y%m%d")
            got = False
            for mkt in ("ALL", "KOSPI", "KOSDAQ"):
                t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
                if t is None or not len(t):
                    continue
                t = t.reset_index()
                ren = {"티커": "code", "시가총액": "mktcap", "상장주식수": "shares"}
                t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
                if "code" not in t.columns:
                    t = t.rename(columns={t.columns[0]: "code"})
                if "mktcap" not in t.columns:
                    continue
                t["code"] = t["code"].map(to_code6)
                t = t.dropna(subset=["code"])
                for c in ("mktcap", "shares"):
                    if c not in t.columns:
                        t[c] = np.nan
                    t[c] = pd.to_numeric(t[c], errors="coerce")
                t = t[["code", "mktcap", "shares"]]
                t["snap_date"] = as_ts(d)
                new_rows.extend(t.to_dict("records"))
                got = True
                if mkt == "ALL":
                    break
            streak = 0 if got else streak + 1
            if streak >= 5:
                LOG.warn("시총 스냅샷이 연속 5회 비었습니다(세션 만료/차단 추정) — "
                         "수집을 중단하고 DART 주식총수 경로로 폴백합니다.")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    S = pd.concat(frames, ignore_index=True)
    S["snap_date"] = as_ts_series(S["snap_date"])
    S = (S.dropna(subset=["code", "snap_date"])
          .drop_duplicates(["code", "snap_date"], keep="last")
          .reindex(columns=cols))
    if new_rows:
        out = S.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_marketcap_snapshots", out, scope="shared", domain="universe",
                        source="pykrx get_market_cap_by_ticker",
                        extra={"note": "PIT 시가총액·상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_marketcap_snapshots", S, source="pykrx")
    return S


def fetch_dart_share_counts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """★2순위 겸 Q축 필수 입력: DART '주식의 총수 현황'(stockTotqySttus.json).

    두 가지 역할을 동시에 한다:
      ① 시가총액 폴백 — 발행주식수 × 주가 (knowledge_date = 접수일자라 PIT 가 성립한다)
      ② §5.3 '주식수 증가율(3년)' 의 원천 — 이게 없으면 퀄리티 축이 소형주에서 오작동한다
    반환: corp_code · bsns_year · reprt_code · shares_issued · shares_treasury ·
          period_end · knowledge_date
    """
    cols = ["corp_code", "bsns_year", "reprt_code", "shares_issued", "shares_treasury",
            "period_end", "knowledge_date"]
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 주식총수(주식수 증가율 Q축)를 받을 수 없습니다. "
                 "해당 지표는 결측 처리되고 Q축은 가용 지표 평균으로 축소됩니다(0으로 채우지 않음).")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_share_counts", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"캐시에서 DART 주식총수 {len(cached):,}행 재사용")

    reprts = [REPRT_CODES["Q1"], REPRT_CODES["H1"], REPRT_CODES["Q3"], REPRT_CODES["FY"]]
    jobs = [(str(c), int(y), r) for y in sorted(years, reverse=True)
            for c in corp_codes for r in reprts
            if (str(c), int(y), str(r)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, y, r = job
        js = dart_api("stockTotqySttus.json",
                      {"corp_code": corp, "bsns_year": str(y), "reprt_code": r})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        num = lambda s: pd.to_numeric(
            pd.Series(s).astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
        # se(구분) 가 '합계' 인 행이 발행주식 총수. 종류주식별 행을 다 더하면 이중계상이 난다.
        se = d["se"].astype(str).str.replace(r"\s+", "", regex=True) if "se" in d.columns else pd.Series([""] * len(d))
        tot = d[se.str.contains("합계|총계", na=False)]
        src = tot if len(tot) else d
        issued = float(num(src.get("istc_totqy", pd.Series(dtype=object))).sum(skipna=True)) \
            if "istc_totqy" in src.columns else np.nan
        tre = float(num(src.get("tesstk_co", pd.Series(dtype=object))).sum(skipna=True)) \
            if "tesstk_co" in src.columns else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        if not np.isfinite(issued) or issued <= 0:
            return None
        return {"corp_code": corp, "bsns_year": int(y), "reprt_code": str(r),
                "shares_issued": issued, "shares_treasury": tre, "rcept_no": rn}

    got = []
    if jobs:
        LOG.info(f"DART 주식총수 신규 수집 대상 {len(jobs):,}건 "
                 f"(남은 호출량: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 10),
                                  desc="DART 주식총수") if r]

    frames = [cached] if cached is not None and len(cached) else []
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    W = pd.concat(frames, ignore_index=True)
    W = W.drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last")
    if "rcept_no" not in W.columns:
        W["rcept_no"] = ""
    W["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END.get(str(r), (12, 31))[0]:02d}-"
                             f"{REPRT_PERIOD_END.get(str(r), (12, 31))[1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [dart_knowledge_date(rn, str(r), int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]
    if got:
        VAULT.put_table("dart_share_counts", W, scope="shared", domain="dart",
                        source="opendart stockTotqySttus")
    W = pit_frame(W, "period_end", "knowledge_date", source="dart")
    LOG.ok(f"DART 주식총수 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
           f"(시총 폴백 + 주식수 증가율 Q축 원천)")
    PIPE.io("OUT", "DRIVE", "dart_share_counts", W, source="opendart stockTotqySttus")
    return downcast_q(W)


def build_cap_panel(cal: pd.DataFrame, px_daily: pd.DataFrame, snaps: pd.DataFrame,
                    shares_dart: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """리밸런싱 시점별 PIT 시가총액. 3단 폴백을 쓰고 어느 경로가 쓰였는지 행마다 기록한다.

      ① KRX 스냅샷의 그 시점 시총                          (최우선 — 정의상 PIT)
      ② DART 발행주식수(as-of, 접수일 기준) × 신호일 종가   (PIT 성립)
      ③ 마지막으로 관측된 주식수 이월 × 신호일 종가         (근사 — 감사표에 표시)

    ★ ①만 쓰면 폐지 종목·비상장 이력 구간이 통째로 빠져 생존자편향이 되고,
      ③만 쓰면 증자·감자가 반영되지 않아 시총이 조용히 틀어진다. 셋을 순서대로 쓴다.
    """
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values(["date", "code"], kind="stable")

    sig = cal[["rebal", "signal_date"]].copy()
    # 신호일 종가 (그 날 거래가 없으면 직전 거래일 종가로 backward as-of)
    L = (sig.assign(_k=1).merge(pd.DataFrame({"code": sorted(px["code"].unique()), "_k": 1}),
                                on="_k").drop(columns="_k"))
    L = L.sort_values("signal_date", kind="stable")
    R = px.rename(columns={"date": "px_date"}).sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="signal_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=20))
    M = M.dropna(subset=["close"])
    M["src_cap"] = ""
    M["mktcap"] = np.nan
    M["shares"] = np.nan

    # ① KRX 스냅샷 — signal_date 이하의 가장 최근 스냅샷 (미래 스냅샷 사용 금지)
    if snaps is not None and len(snaps):
        S = snaps.copy()
        S["snap_date"] = as_ts_series(S["snap_date"])
        S = S.dropna(subset=["code", "snap_date"]).sort_values("snap_date", kind="stable")
        M = M.sort_values("signal_date", kind="stable")
        M = pd.merge_asof(M, S.rename(columns={"mktcap": "cap_krx", "shares": "sh_krx"}),
                          left_on="signal_date", right_on="snap_date", by="code",
                          direction="backward", tolerance=pd.Timedelta(days=100))
        hit = M["cap_krx"].notna() & (M["cap_krx"] > 0)
        M.loc[hit, "mktcap"] = M.loc[hit, "cap_krx"]
        M.loc[hit, "shares"] = M.loc[hit, "sh_krx"]
        M.loc[hit, "src_cap"] = "krx_snapshot"

    # ② DART 발행주식수 × 신호일 종가
    c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
              .set_index("code")["corp_code"].astype(str).to_dict()) if "corp_code" in sec.columns else {}
    M["corp_code"] = M["code"].map(c2c)
    if shares_dart is not None and len(shares_dart):
        D = shares_dart[["corp_code", "knowledge_date", "shares_issued"]].copy()
        D["knowledge_date"] = as_ts_series(D["knowledge_date"])
        D = (D.dropna(subset=["corp_code", "knowledge_date", "shares_issued"])
              .sort_values("knowledge_date", kind="stable"))
        base = M.copy()
        base["_ord"] = np.arange(len(base))
        okm = base["corp_code"].notna() & base["signal_date"].notna()
        if okm.any():
            Lp = base[okm].sort_values("signal_date", kind="stable").copy()
            Lp["corp_code"] = Lp["corp_code"].astype(str)
            D["corp_code"] = D["corp_code"].astype(str)
            J = pd.merge_asof(Lp, D, left_on="signal_date", right_on="knowledge_date",
                              by="corp_code", direction="backward")
            add = J.set_index("_ord")[["shares_issued"]]
            base = base.set_index("_ord").join(add, how="left").sort_index().reset_index(drop=True)
            M = base
        else:
            M["shares_issued"] = np.nan
    else:
        M["shares_issued"] = np.nan

    need = M["mktcap"].isna() & M["shares_issued"].notna() & (M["shares_issued"] > 0)
    M.loc[need, "mktcap"] = M.loc[need, "shares_issued"] * M.loc[need, "close"]
    M.loc[need, "shares"] = M.loc[need, "shares_issued"]
    M.loc[need, "src_cap"] = "dart_shares_x_close"

    # ③ 마지막 관측 주식수 이월 × 종가
    M = M.sort_values(["code", "signal_date"], kind="stable")
    carry = M.groupby("code", observed=True)["shares"].ffill()
    need2 = M["mktcap"].isna() & carry.notna() & (carry > 0)
    M.loc[need2, "mktcap"] = carry[need2] * M.loc[need2, "close"]
    M.loc[need2, "shares"] = carry[need2]
    M.loc[need2, "src_cap"] = "carried_shares_x_close"

    out = M[["code", "rebal", "signal_date", "close", "mktcap", "shares", "src_cap"]].copy()
    out = out[out["mktcap"].notna() & (out["mktcap"] > 0)]
    cnt = out["src_cap"].value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/max(len(out),1):.1f}%"] for k, v in cnt.items()],
              ["시총 산출 경로", "행수", "비중"], ["l", "r", "r"],
              title="PIT 시가총액 소스 감사 (①KRX스냅샷 ②DART주식수×종가 ③주식수이월×종가)")
    if cnt.get("carried_shares_x_close", 0) > 0.35 * max(len(out), 1):
        LOG.warn("시총의 35% 이상이 '주식수 이월' 근사입니다. 증자·감자가 반영되지 않으므로 "
                 "그만큼 시총 랭크가 부정확합니다. pykrx 인증(KRX ID/PW) 또는 DART_API_KEY 를 "
                 "넣으면 크게 개선됩니다.")
    PIPE.io("OUT", "MEM", "cap_panel", out)
    return downcast_q(out)


def build_adtv_panel(cal: pd.DataFrame, px_daily: pd.DataFrame,
                     window: int = ADTV_WINDOW_DAYS) -> pd.DataFrame:
    """직전 `window` 거래일 평균 거래대금(§3.2). 종목별 파이썬 루프 없이 한 번에 계산한다."""
    px = px_daily[["code", "date", "amount", "close", "high", "low"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"]).sort_values(["code", "date"], kind="stable")
    g = px.groupby("code", observed=True)
    px["adtv"] = g["amount"].transform(lambda s: s.rolling(window, min_periods=max(10, window // 3)).mean())

    # ── 실측 호가스프레드 추정: Corwin-Schultz(2012) 고가/저가 추정량 ─────────────────────
    #  §8.1 은 '실측 호가스프레드 기반 슬리피지'를 요구한다. 과거 호가(bid/ask) 시계열은
    #  공개 경로로 확보되지 않으므로, 고가·저가만으로 스프레드를 복원하는 CS 추정량을 쓴다.
    #  한계: 변동성이 큰 초소형주에서 상향 편의가 있고 음수 추정치가 자주 나온다(0 으로 절단).
    #  대안(Amihud)은 스프레드가 아니라 충격계수라 §8.1 의 요구와 맞지 않는다.
    _K = 3.0 - 2.0 * math.sqrt(2.0)
    with np.errstate(all="ignore"):
        hi_ = px["high"].where(px["high"] > 0)
        lo_ = px["low"].where(px["low"] > 0)
        hl = np.log(hi_ / lo_)
        # ★ CS 는 2일 추정량이다. (t, t+1) 로 잡으면 signal_date 에서 읽는 스프레드가
        #   '체결일의 고저'를 포함하게 되어 비용 모델에 1일치 미래정보가 들어간다.
        #   (t-1, t) 로 잡으면 동일한 추정량이면서 t 까지의 정보만 쓴다.
        hl_n = g["high"].shift(1)
        lo_n = g["low"].shift(1)
        hl2 = np.log(hl_n.where(hl_n > 0) / lo_n.where(lo_n > 0))
        beta = hl ** 2 + hl2 ** 2
        h2 = pd.concat([hi_, hl_n.where(hl_n > 0)], axis=1).max(axis=1)
        l2 = pd.concat([lo_, lo_n.where(lo_n > 0)], axis=1).min(axis=1)
        gam = np.log(h2 / l2) ** 2
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _K - np.sqrt(gam / _K)
        s_cs = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    px["_cs"] = pd.Series(s_cs, index=px.index).replace([np.inf, -np.inf], np.nan).clip(lower=0.0)
    px["cs_spread"] = (px.groupby("code", observed=True)["_cs"]
                         .transform(lambda s: s.rolling(window, min_periods=max(10, window // 3)).mean()))
    px["ret1d"] = g["close"].pct_change(fill_method=None)
    px["vol_d"] = px.groupby("code", observed=True)["ret1d"].transform(
        lambda s: s.rolling(INVVOL_WINDOW_DAYS, min_periods=max(20, INVVOL_WINDOW_DAYS // 3)).std())

    keep = px[["code", "date", "adtv", "cs_spread", "vol_d"]].dropna(subset=["date"])
    sig = cal[["rebal", "signal_date"]].drop_duplicates().sort_values("signal_date", kind="stable")
    L = (sig.assign(_k=1).merge(pd.DataFrame({"code": sorted(keep["code"].unique()), "_k": 1}),
                                on="_k").drop(columns="_k")).sort_values("signal_date", kind="stable")
    R = keep.rename(columns={"date": "px_date"}).sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="signal_date", right_on="px_date", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=20))
    out = M[["code", "rebal", "adtv", "cs_spread", "vol_d"]].dropna(subset=["adtv"])
    PIPE.io("OUT", "MEM", "adtv_panel", out)
    return downcast_q(out)


# ── U-1000 ──────────────────────────────────────────────────────────────────────────────────
#  랭크 순서 정책. False = 제외·유동성 게이트를 먼저 통과시킨 뒤 그 안에서 하위 1000.
#  True 로 두면 '전 종목 중 하위 1000'을 먼저 뽑고 그 안에서 게이트를 적용해 N 이 크게 줄어든다.
#  §3 은 세 조건을 유니버스의 구성요건으로 나란히 서술하므로 False 가 자연스러운 해석이며,
#  두 해석의 결과 종목수를 모두 로그에 남겨 판단 근거를 남긴다.
U1000_RANK_BEFORE_FILTER = False


def build_universe_grid(uni: "Universe", cal: pd.DataFrame, cap: pd.DataFrame,
                        adtv: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """전 종목 × 전 리밸런싱 격자. U-1000 선정 '이전' 단계다.

    ★ 왜 격자를 먼저 만드는가: 완전자본잠식 판정에는 PIT 재무가 필요한데, 재무를 U-1000
      선정 뒤에 붙이면 '잠식 종목을 U-1000 에 넣은 채로' 랭크가 끝나 버린다. 순서를 뒤집으면
      재무를 두 번 붙여야 하고 두 번째가 첫 번째와 미세하게 달라질 여지가 생긴다.
      격자를 먼저 만들고 → 재무 as-of 결합 → 게이트 적용 순서면 결합이 정확히 한 번이다.
    """
    names = sec.set_index("code")["name"].astype(str).to_dict() if len(sec) else {}
    mkts = sec.set_index("code")["market"].astype(str).to_dict() if len(sec) else {}
    sects = sec.set_index("code")["industry"].astype(str).to_dict() if len(sec) else {}
    struct = {c: classify_exclusion(c, names.get(c, "")) for c in sec["code"]} if len(sec) else {}
    n_struct = sum(1 for v in struct.values() if v)
    if n_struct:
        by = Counter(v for v in struct.values() if v)
        LOG.info(f"구조적 제외 종목 {n_struct:,}건 (시점 불변) — " +
                 ", ".join(f"{k} {v:,}" for k, v in by.most_common()))

    parts = []
    for r in cal.itertuples(index=False):
        codes = uni.at(r.signal_date)      # ★ 신호일 기준 상장 종목 (폐지 반영 · 시즈닝 적용)
        if not codes:
            continue
        d = pd.DataFrame({"code": codes})
        d["rebal"], d["signal_date"], d["exec_date"] = r.rebal, r.signal_date, r.exec_date
        parts.append(d)
    if not parts:
        raise RuntimeError("유니버스 격자가 비었습니다 — 상장일·폐지일 정보를 확인하세요.")
    G = pd.concat(parts, ignore_index=True)
    G["excl_struct"] = G["code"].map(lambda c: struct.get(c, "")).fillna("")
    G["sector"] = G["code"].map(sects).fillna("미분류").replace("", "미분류")
    G["market"] = G["code"].map(mkts).fillna("OTHER")

    if cap is not None and len(cap):
        G = G.merge(cap[["code", "rebal", "mktcap", "shares", "close", "src_cap"]],
                    on=["code", "rebal"], how="left")
    else:
        for c in ("mktcap", "shares", "close", "src_cap"):
            G[c] = np.nan
    if adtv is not None and len(adtv):
        G = G.merge(adtv[["code", "rebal", "adtv", "cs_spread", "vol_d"]],
                    on=["code", "rebal"], how="left")
    else:
        for c in ("adtv", "cs_spread", "vol_d"):
            G[c] = np.nan
    assert_no_dup_cols(G, "universe_grid")
    LOG.ok(f"유니버스 격자 {len(G):,}행 ({G['code'].nunique():,}종목 × {G['rebal'].nunique()}분기) · "
           f"시총 보유 {100*G['mktcap'].notna().mean():.1f}% · "
           f"거래대금 보유 {100*G['adtv'].notna().mean():.1f}%")
    PIPE.io("OUT", "MEM", "universe_grid", G)
    return downcast_q(G)


def select_u1000(G: pd.DataFrame) -> pd.DataFrame:
    """격자 → U-1000. 각 게이트의 탈락 수를 전부 기록한다(§3 감쇠 감사).

    입력 G 에는 이미 PIT 재무(equity 등)가 결합되어 있어야 한다.
    """
    d = G.copy()
    d["liq_ok"] = d["adtv"].notna() & (d["adtv"] >= MIN_ADTV_KRW)
    eq = col(d, "equity")
    # ★ 자기자본을 '모르는' 것과 '음수인' 것은 다르다. 모르는 것을 잠식으로 처리하면
    #   재무 결측이 많은 초소형주가 통째로 사라져 그대로 선택편향이 된다.
    d["erosion"] = eq.notna() & (eq <= 0)
    d["elig"] = (d["excl_struct"] == "") & d["mktcap"].notna() & d["liq_ok"] & ~d["erosion"]

    if U1000_RANK_BEFORE_FILTER:
        pre_rank = d[d["mktcap"].notna()].groupby("rebal", observed=True)["mktcap"] \
                    .rank(method="first", ascending=True)
        d["_prerank"] = pre_rank.reindex(d.index)
        d["in_u1000"] = (d["_prerank"] <= U1000_N) & d["elig"]
    else:
        r = d.where(d["elig"]).groupby("rebal", observed=True)["mktcap"] \
              .rank(method="first", ascending=True)
        d["in_u1000"] = d["elig"] & (r <= U1000_N)

    audit = []
    for t, g in d.groupby("rebal", observed=True):
        n_cap_ok = g[g["mktcap"].notna()]
        alt_rank = n_cap_ok["mktcap"].rank(method="first", ascending=True)
        alt = n_cap_ok[alt_rank <= U1000_N]
        audit.append({
            "rebal": t, "전체상장": len(g),
            "구조제외후": int((g["excl_struct"] == "").sum()),
            "시총보유": int(g["mktcap"].notna().sum()),
            "유동성통과": int(g["liq_ok"].sum()),
            "자본잠식제외": int(g["erosion"].sum()),
            "적격": int(g["elig"].sum()),
            "U1000": int(g["in_u1000"].sum()),
            "대안해석": int(alt["elig"].sum()) if len(alt) else 0})

    U = d[d["in_u1000"]].drop(columns=[c for c in ("_prerank",) if c in d.columns]).copy()
    if U.empty:
        raise RuntimeError("U-1000 이 전 시점에서 비었습니다. 위 감쇠 감사에서 어느 게이트가 "
                           "원인인지 확인하세요(대개 시총 결측 또는 유동성 하한).")
    Aud = pd.DataFrame(audit).sort_values("rebal")
    LOG.table([[f"{r.rebal:%Y-%m}", f"{r.전체상장:,}", f"{r.구조제외후:,}", f"{r.시총보유:,}",
                f"{r.유동성통과:,}", f"{r.자본잠식제외:,}", f"{r.적격:,}", f"{r.U1000:,}"]
               for r in Aud.tail(12).itertuples(index=False)],
              ["리밸런싱", "전체상장", "구조제외후", "시총보유", "유동성통과", "자본잠식", "적격", "U-1000"],
              ["l", "r", "r", "r", "r", "r", "r", "r"],
              title="U-1000 감쇠 감사 (최근 12분기) — 어느 게이트에서 표본이 줄어드는지")
    LOG.info(f"U-1000 평균 {Aud['U1000'].mean():,.0f}종목 "
             f"(적격 평균 {Aud['적격'].mean():,.0f} / 전체상장 평균 {Aud['전체상장'].mean():,.0f}) · "
             f"랭크순서 해석 대안값 평균 {Aud['대안해석'].mean():,.0f}종목")
    if Aud["U1000"].mean() < U1000_N * 0.5:
        LOG.warn(f"U-1000 이 목표 {U1000_N} 의 절반에 못 미칩니다. 위 감쇠 감사표에서 어느 게이트가 "
                 f"원인인지 먼저 확인하세요(대개 시총 결측 또는 유동성 하한).")

    LOG.warn("PIT 관리종목·투자주의환기종목·거래정지 이력은 공개 API 로 소급 조회가 불가능합니다. "
             "현재 시점 명단을 과거에 적용하면 그 자체가 미래누수이므로 적용하지 않았습니다. "
             "대신 PIT 로 확인 가능한 완전자본잠식·4분기연속영업적자·감사의견 강조사항을 "
             "3-A 규칙(§7.2)에서 배제 사유로 사용합니다 — 이는 근사이며 동일하지 않습니다.")
    PIPE.note("PIT 관리종목 이력 미적용(소급 불가) — 3-A 재무기준으로 근사")
    PIPE.io("OUT", "MEM", "U1000", U)
    return downcast_q(U)


def build_sector_cells(P: pd.DataFrame, min_n: int = CELL_MIN_N) -> pd.DataFrame:
    """§5.2/5.3 '섹터 중립' 의 셀. cell = (리밸런싱일, 섹터).
    표본이 부족한 섹터는 상위 단위 → 전체 순으로 폴백하고 그 사실을 로깅한다
    (폴백하지 않으면 소형 섹터의 z-score 가 통째로 NaN 이 되어 조용히 사라진다)."""
    p = P.copy()
    p["sector"] = p["sector"].astype(str).fillna("미분류").replace("", "미분류")
    p["sector_l1"] = p["sector"].str.slice(0, 4)
    ym = p["rebal"].dt.strftime("%Y%m")
    p["cell"] = ym + "|" + p["sector"]
    p["cell_l2"] = ym + "|" + p["sector_l1"]
    p["cell_l3"] = ym + "|ALL"
    cnt = p.groupby("cell", observed=True)["code"].transform("size")
    small = cnt < min_n
    if small.any():
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        cnt2 = p.groupby("cell", observed=True)["code"].transform("size")
        still = cnt2 < min_n
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"섹터 셀 폴백: 1차 {int(small.sum()):,}행(섹터 상위단위) / "
                 f"2차 {int(still.sum()):,}행(전체). 표본 부족 셀을 NaN 으로 버리지 않습니다.")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    return p



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q2  가치(V) · 퀄리티(Q) · 수급(F) 축 (§5.2 ~ §5.4)                                     ║
# ║                                                                                          ║
# ║  이 파일의 존재 이유 절반은 '부호 처리'다(§5.2).                                           ║
# ║    EBIT 이 음수인데 EV/EBIT 를 그대로 쓰면 비율이 음수가 되고, '낮을수록 우수' 규칙에서     ║
# ║    적자기업이 자동으로 최우량이 된다. 예외도 경고도 없이. 딥밸류 스크리너가 망하는          ║
# ║    가장 흔한 방식이며, 이 전략은 하위 1000 구간을 다루므로 적자기업 비중이 특히 높다.       ║
# ║    → 분모가 0 이하인 관측치는 '그 셀의 최하위 z' 로 강제 배정한다. 버리지 않는다            ║
# ║      (버리면 그 종목이 유니버스에서 사라져 곧바로 선택편향이 된다).                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 공용 코어의 계정 매핑에 QVF 가 추가로 필요로 하는 계정을 얹는다.
# ★ tidy_financials 는 호출 시점의 ACCOUNT_PATTERNS 를 순회하므로, 수집 전에 갱신하면
#   추가 API 호출 없이(이미 받아온 원시 계정행에 정규식만 더 돌려서) 그대로 추출된다.
ACCOUNT_PATTERNS.update({
    "st_debt":   ("BS", [r"ShorttermBorrowings", r"^단기차입금$", r"^유동성장기부채$",
                         r"^유동성사채$"]),
    "lt_debt":   ("BS", [r"LongtermBorrowings", r"^장기차입금$"]),
    "bonds":     ("BS", [r"BondsIssued", r"^사채$", r"^전환사채$", r"^신주인수권부사채$"]),
    "lease_liab": ("BS", [r"LeaseLiabilities", r"^리스부채$"]),
    # 자본잠식률(§7.2) = (자본금 − 자기자본) / 자본금. 자본금 계정이 없으면 규칙이 성립하지 않는다.
    "capital_stock": ("BS", [r"ifrs-full_IssuedCapital$", r"^자본금$"]),
})

_V_METRICS = ("ev_ebit", "pbr", "pcr")
_Q_METRICS = ("gp_a", "roic_std3y", "accruals", "debt_ratio", "share_growth3y")


# ── 백분위 윈저라이징 z-score (§5.2/5.3 '상하위 1% 윈저라이징') ──────────────────────────────
def xsec_z_pct(values: pd.Series, cells: pd.Series, pct: float = WINSOR_PCT,
               min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 내 상하위 `pct` 윈저라이징 → z-score. 공용 코어의 xsec_z 는 ±2σ 라 규격이 다르다.

    ±inf 를 먼저 NaN 으로 바꾸는 것이 핵심이다. nanmean 은 NaN 은 무시하지만 inf 는 무시하지
    않으므로, 셀에 inf 가 하나만 있어도 평균이 inf·표준편차가 NaN 이 되어 그 셀 전체의
    z-score 가 통째로 0 이나 NaN 으로 뭉개진다. 비율 지표에서 매우 흔하다.
    """
    v = pd.to_numeric(values, errors="coerce").astype("float64").replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("__NA__").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    cnt = g.transform("count")
    # ★ transform(lambda s: s.quantile(...)) 은 그룹당 파이썬 호출이라 수천 셀 × 수십 회
    #   재실행되는 민감도 분석에서 그대로 분 단위가 된다. 네이티브 집계 후 map 으로 되돌린다.
    gk = pd.Series(grp, index=v.index)
    q_lo = g.quantile(pct)
    q_hi = g.quantile(1.0 - pct)
    lo = gk.map(q_lo).astype("float64")
    hi = gk.map(q_hi).astype("float64")
    w = v.clip(lower=lo, upper=hi)
    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)     # 셀 내 전원 동일값 → 0
    return z.where(cnt >= min_n).astype("float32")


def _cell_ladder_z(P: pd.DataFrame, v: pd.Series, min_n: int = CELL_MIN_N) -> pd.Series:
    """셀 폴백 사다리를 적용한 백분위-윈저 z. 표본 부족 셀을 통째로 NaN 으로 만들지 않는다."""
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    z = xsec_z_pct(v, P["cell"], min_n=min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in ("cell_l2", "cell_l3"):
        if not z.isna().any():
            break
        if lvl in P.columns:
            z = z.where(z.notna(), xsec_z_pct(v, P[lvl], min_n=min_n))
    return z


def z_lower_is_better(P: pd.DataFrame, raw: pd.Series, valid: pd.Series,
                      name: str = "") -> pd.Series:
    """'낮을수록 우수' 지표를 z-score(높을수록 우수)로 바꾸되, 분모 부적격(valid=False)
    관측치는 셀 최하위로 강제 배정한다 (§5.2 부호 처리 규칙).

    ★ 왜 '버리기'가 아니라 '최하위 배정'인가:
      버리면(NaN) 그 종목은 축 평균에서 빠지고, 다른 축 점수만으로 살아남아 오히려
      상위에 오를 수 있다. 즉 적자기업이 벌점 대신 면제를 받는다. 정반대의 결과다.
    """
    r = pd.to_numeric(raw, errors="coerce").replace([np.inf, -np.inf], np.nan)
    ok = valid.fillna(False).to_numpy(dtype=bool) & r.notna().to_numpy()
    sig = pd.Series(np.where(ok, -r.to_numpy(dtype="float64"), np.nan), index=P.index)
    z = _cell_ladder_z(P, sig)
    # 셀별 최하위 z (윈저라이징 이후 값이므로 이상치로 폭주하지 않는다)
    worst = z.groupby(P["cell"].astype(object).fillna("__NA__").to_numpy(),
                      observed=True).transform("min")
    forced = (~pd.Series(ok, index=P.index)) & r.notna().reindex(P.index).fillna(False)
    # raw 자체가 결측(재무 미보유)인 경우는 '부적격'이 아니라 '모름' 이므로 강제하지 않는다.
    z_out = z.copy()
    n_forced = int(forced.sum())
    if n_forced:
        z_out = z_out.where(~forced, worst)
        # 셀 전체가 부적격이라 worst 도 NaN 이면 -3 으로 바닥을 준다(z 스케일상 하위 0.1%).
        z_out = z_out.where(~(forced & z_out.isna()), -3.0)
    if name:
        LOG.debug(f"  {name}: 유효 {int(ok.sum()):,} · 분모부적격 강제최하위 {n_forced:,} · "
                  f"결측(모름) {int(r.isna().sum()):,}")
    return z_out.astype("float32")


# ── 재무 파생 (분기 프레임에서 계산 → 이후 as-of 결합) ──────────────────────────────────────
def build_quarterly_fundamentals(fin: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """corp_code × 분기 프레임에서 ROIC 3년 표준편차 · 주식수 3년 증가율을 만든다.

    ★ 왜 분기 프레임에서 하는가: 리밸런싱 패널에서 rolling(12) 을 돌리면 '12분기'가 아니라
      '12개 리밸런싱 시점'이 되고, 그 사이 결측 분기가 있으면 창 길이가 조용히 달라진다.
      분기 프레임은 관측당 정확히 한 행이라 창의 의미가 흔들리지 않는다.
    ★ 모든 rolling 은 과거만 본다(center=False 기본). knowledge_date 는 그대로 실려 나가므로
      as-of 결합이 C1 을 그대로 강제한다.
    """
    if fin is None or not len(fin):
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "roic_std3y", "share_growth3y"])
    F = fin.copy()
    F["knowledge_date"] = as_ts_series(F["knowledge_date"])
    F = F.dropna(subset=["corp_code", "knowledge_date"]).sort_values(
        ["corp_code", "period_end", "knowledge_date"], kind="stable")

    # 투하자본 = 자기자본 + 총차입금 − 현금. 차입금 계정이 전부 결측이면 부채총계로 폴백한다.
    debt = (col(F, "st_debt").fillna(0) + col(F, "lt_debt").fillna(0) +
            col(F, "bonds").fillna(0) + col(F, "lease_liab").fillna(0))
    has_debt = (col(F, "st_debt").notna() | col(F, "lt_debt").notna() |
                col(F, "bonds").notna() | col(F, "lease_liab").notna())
    debt = debt.where(has_debt, col(F, "liabilities"))
    F["_debt"] = debt
    ic = col(F, "equity") + debt.fillna(0) - col(F, "cash").fillna(0)
    F["_ic"] = ic.where(ic > 0)

    # NOPAT ≈ 영업이익TTM × (1 − 유효세율). 유효세율은 0~40% 로 클립(음수 세율 폭주 방지).
    eff_tax = safe_div(col(F, "tax_expense_ttm"), col(F, "pretax_income_ttm")).clip(0.0, 0.40)
    F["_roic"] = safe_div(col(F, "op_income_ttm") * (1.0 - eff_tax.fillna(0.22)), F["_ic"])
    F["roic_std3y"] = (F.groupby("corp_code", observed=True)["_roic"]
                        .transform(lambda s: s.rolling(12, min_periods=8).std()))

    # §7.2 '4개 분기 연속 영업적자'. 분기 단독 영업이익(op_income_q)으로 센다.
    #   ★ 월/분기 패널에서 세면 같은 분기값이 반복되어 어떤 고정 개수도 정답이 아니다.
    #   ★ min_periods=4 — 제출분이 4개 미만이면 NaN(=배제하지 않음). 근거 없는 제외 금지.
    _loss = (col(F, "op_income_q") < 0).astype(float).where(col(F, "op_income_q").notna())
    F["op_loss_4q"] = (_loss.groupby(F["corp_code"], observed=True)
                            .transform(lambda s: s.rolling(RULE_OP_LOSS_QUARTERS,
                                                           min_periods=RULE_OP_LOSS_QUARTERS).min()))

    # 주식수 3년 증가율 — 분기 12개 전 대비. shift 가 아니라 '실제 12분기 전'이어야 하므로
    # 결측 분기가 있으면 그 관측은 만들지 않는다(min_periods 로 강제).
    if shares is not None and len(shares):
        S = shares[["corp_code", "knowledge_date", "shares_issued", "shares_treasury"]].copy()
        S["knowledge_date"] = as_ts_series(S["knowledge_date"])
        S = (S.dropna(subset=["corp_code", "knowledge_date", "shares_issued"])
              .sort_values(["corp_code", "knowledge_date"], kind="stable")
              .drop_duplicates(["corp_code", "knowledge_date"], keep="last"))
        S["_n"] = S.groupby("corp_code", observed=True).cumcount()
        prev = S.groupby("corp_code", observed=True)["shares_issued"].shift(12)
        prev_n = S.groupby("corp_code", observed=True)["_n"].shift(12)
        # ★ 12행 전이 '정확히 12분기 전'일 때만 3년 증가율로 인정한다. 결측 분기를 건너뛴 채
        #   shift(12) 를 믿으면 5년 전 주식수를 3년 증가율이라 부르게 된다.
        contiguous = (S["_n"] - prev_n) == 12
        S["share_growth3y"] = (safe_div(S["shares_issued"], prev) - 1.0).where(contiguous)
        S = S[["corp_code", "knowledge_date", "shares_issued", "shares_treasury",
               "share_growth3y"]].sort_values("knowledge_date", kind="stable")
        # ★★ outer merge 를 쓰면 안 된다 (적대적 감사가 잡은 조용한 실패) ★★
        #   주식총수(stockTotqySttus)는 전체 재무제표(fnlttSinglAcntAll)보다 훨씬 자주 성공한다
        #   — 특히 소형주에서. outer merge 는 '주식수만 있는 날짜'에 재무 컬럼이 전부 NaN 인
        #   행을 새로 만들고, 하류의 merge_asof(backward)가 신호일 직전의 그 행을 집어간다.
        #   결과: equity=NaN → PBR·부채비율·자본잠식 판정 불가 → fin_cov 붕괴 → §2.2 킬 기준이
        #   "DART 콜드빌드 미완"이라는 엉뚱한 메시지로 전략을 중단시킨다. 원인은 전혀 다른데.
        #   → 재무 관측을 기준 프레임으로 두고, 주식수는 as-of 로 '그 시점까지 알려진 최신값'을
        #     붙인다. 행이 늘어나지 않으므로 재무 결측 행이 생성될 수 없다.
        F = F.sort_values("knowledge_date", kind="stable")
        F["corp_code"] = F["corp_code"].astype(str)
        S["corp_code"] = S["corp_code"].astype(str)
        F = pd.merge_asof(F, S, on="knowledge_date", by="corp_code", direction="backward")
    else:
        for c in ("shares_issued", "shares_treasury", "share_growth3y"):
            F[c] = np.nan

    keep = ["corp_code", "knowledge_date", "period_end", "roic_std3y", "share_growth3y",
            "shares_issued", "shares_treasury", "_debt", "op_loss_4q",
            "gross_profit_ttm", "revenue_ttm", "cogs_ttm", "op_income_ttm", "net_income_ttm",
            "cfo_ttm", "assets", "liabilities", "equity", "cash", "capital_stock"]
    for c in keep:
        if c not in F.columns:
            F[c] = np.nan
    out = F[keep].dropna(subset=["corp_code", "knowledge_date"])
    out = out.rename(columns={"_debt": "total_debt"})
    out = pit_frame(out, "period_end", "knowledge_date", source="dart_q")
    _eqc = float(out["equity"].notna().mean()) if len(out) else 0.0
    LOG.ok(f"분기 재무 파생 {len(out):,}행 · {out['corp_code'].nunique():,}사 "
           f"(자기자본 보유 {100*_eqc:.1f}% · ROIC 3년 표준편차 "
           f"{int(out['roic_std3y'].notna().sum()):,}건 · 주식수 3년 증가율 "
           f"{int(out['share_growth3y'].notna().sum()):,}건 · 주식수 결합 "
           f"{100*float(out['shares_issued'].notna().mean()) if len(out) else 0:.1f}%)")
    if len(out) and _eqc < 0.90:
        LOG.warn(f"자기자본 보유율이 {100*_eqc:.1f}% 로 낮습니다. 이 값이 그대로 Phase 0 의 "
                 f"fin_cov 가 되어 §2.2 중단 조건에 걸릴 수 있습니다. 원인은 대개 "
                 f"fnlttSinglAcntAll 콜드빌드 미완이며, 재실행하면 이어받습니다.")
    return downcast_q(out)


def attach_fundamentals_q(G: pd.DataFrame, fq: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """격자 × 분기재무 as-of 결합. knowledge_date <= signal_date 만 붙는다(C1).

    ★ corp_code 가 없는 종목(대개 폐지·신규상장·비DART)을 결합 과정에서 '떨어뜨리면'
      그게 곧 생존자편향이다. 결합 실패 행은 결측으로 남기고 행 자체는 반드시 보존한다.
    """
    FIN_COLS = ["roic_std3y", "share_growth3y", "shares_issued", "shares_treasury", "total_debt",
                "gross_profit_ttm", "revenue_ttm", "cogs_ttm", "op_income_ttm",
                "net_income_ttm", "cfo_ttm", "assets", "liabilities", "equity", "cash",
                "op_loss_4q", "capital_stock"]
    d = G.copy()
    if "corp_code" not in d.columns:
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict()) \
            if "corp_code" in sec.columns else {}
        d["corp_code"] = d["code"].map(c2c)
    if fq is None or not len(fq):
        for c in FIN_COLS:
            d[c] = np.nan
        LOG.warn("PIT 재무가 비어 가치·퀄리티 축이 전부 결측이 됩니다. DART_API_KEY 를 확인하세요.")
        return d

    R = fq[["corp_code", "knowledge_date"] + [c for c in FIN_COLS if c in fq.columns]].copy()
    R["knowledge_date"] = as_ts_series(R["knowledge_date"])
    R = (R.dropna(subset=["corp_code", "knowledge_date"])
          .sort_values("knowledge_date", kind="stable"))
    R["corp_code"] = R["corp_code"].astype(str)

    base = d.copy()
    base["_ord"] = np.arange(len(base))
    m = base["corp_code"].notna() & base["signal_date"].notna()
    n_drop = int((~m).sum())
    if n_drop:
        LOG.info(f"재무 결합키(corp_code) 결측 {n_drop:,}행은 결측값으로 보존합니다 "
                 f"(행을 버리면 그대로 생존자편향).")
    L = base[m].copy()
    L["corp_code"] = L["corp_code"].astype(str)
    L = L.sort_values("signal_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="signal_date", right_on="knowledge_date",
                      by="corp_code", direction="backward")
    add_cols = [c for c in M.columns if c not in base.columns]
    out = base.set_index("_ord").join(M.set_index("_ord")[add_cols], how="left")
    out = out.sort_index().reset_index(drop=True)
    cov = float(out["equity"].notna().mean()) if "equity" in out.columns else 0.0
    LOG.ok(f"PIT 재무 as-of 결합 완료 — 자기자본 보유율 {100*cov:.1f}% "
           f"(knowledge_date ≤ signal_date 강제)")
    return downcast_q(out)


# ── V 축 (§5.2) ─────────────────────────────────────────────────────────────────────────────
def axis_V(P: pd.DataFrame) -> pd.DataFrame:
    d = P.copy()
    cap = col(d, "mktcap")
    debt = col(d, "total_debt")
    cash = col(d, "cash")
    # EV = 시총 + 순차입금. 차입금 계정이 결측이면 부채총계로 폴백(과대추정 방향 — 보수적).
    ev = cap + debt.fillna(col(d, "liabilities")).fillna(0) - cash.fillna(0)
    ebit = col(d, "op_income_ttm")
    # ★ 순현금이 시총보다 커서 EV<=0 인 경우는 '분모 오류'가 아니라 실제로 최우량이다.
    #   EV 를 0 으로 클립해 비율 0(=최우량)으로 두되, EBIT 부호 규칙은 그대로 적용한다.
    d["ev_ebit"] = safe_div(ev.clip(lower=0), ebit)
    d["_v_ok_ev"] = ebit.notna() & (ebit > 0)

    d["pbr"] = safe_div(cap, col(d, "equity"))
    d["_v_ok_pbr"] = col(d, "equity").notna() & (col(d, "equity") > 0)

    d["pcr"] = safe_div(cap, col(d, "cfo_ttm"))
    d["_v_ok_pcr"] = col(d, "cfo_ttm").notna() & (col(d, "cfo_ttm") > 0)

    LOG.info("V축 부호 처리 (§5.2) — 분모 ≤ 0 관측치는 해당 지표에서 셀 최하위로 강제 배정:")
    d["zV_ev_ebit"] = z_lower_is_better(d, d["ev_ebit"], d["_v_ok_ev"], "EV/EBIT")
    d["zV_pbr"] = z_lower_is_better(d, d["pbr"], d["_v_ok_pbr"], "PBR")
    d["zV_pcr"] = z_lower_is_better(d, d["pcr"], d["_v_ok_pcr"], "PCR")

    zc = [f"zV_{m}" for m in _V_METRICS]
    d["Z_V"] = d[zc].astype("float64").mean(axis=1, skipna=True).astype("float32")
    n_ax = d[zc].notna().sum(axis=1)
    d["Z_V"] = d["Z_V"].where(n_ax >= 1)
    LOG.ok(f"V축 완성 — 관측 {int(d['Z_V'].notna().sum()):,}/{len(d):,}행 "
           f"({100*d['Z_V'].notna().mean():.1f}%) · 지표 3개 중 평균 {n_ax.mean():.2f}개 가용")
    return d


# ── Q 축 (§5.3) ─────────────────────────────────────────────────────────────────────────────
def axis_Q(P: pd.DataFrame) -> pd.DataFrame:
    d = P.copy()
    gp = col(d, "gross_profit_ttm")
    gp = gp.where(gp.notna(), col(d, "revenue_ttm") - col(d, "cogs_ttm"))
    d["gp_a"] = safe_div(gp, col(d, "assets"))            # 높을수록 우수 (Novy-Marx)
    d["accruals"] = safe_div(col(d, "net_income_ttm") - col(d, "cfo_ttm"), col(d, "assets"))
    d["debt_ratio"] = safe_div(col(d, "liabilities"), col(d, "equity"))

    # 높을수록 우수 → 그대로 z
    d["zQ_gp_a"] = _cell_ladder_z(d, d["gp_a"])
    # 낮을수록 우수 → 부호 반전 후 z. 분모 부적격 개념이 없는 지표는 valid=notna.
    d["zQ_roic_std3y"] = z_lower_is_better(d, col(d, "roic_std3y"),
                                           col(d, "roic_std3y").notna(), "ROIC 3년 표준편차")
    d["zQ_accruals"] = z_lower_is_better(d, d["accruals"], d["accruals"].notna(), "발생액")
    # 부채비율은 자기자본이 0 이하면 의미가 뒤집힌다(음수 부채비율=최우량). 부적격 처리.
    d["zQ_debt_ratio"] = z_lower_is_better(
        d, d["debt_ratio"], col(d, "equity").notna() & (col(d, "equity") > 0), "부채비율")
    d["zQ_share_growth3y"] = z_lower_is_better(
        d, col(d, "share_growth3y"), col(d, "share_growth3y").notna(), "주식수 3년 증가율")

    zc = [f"zQ_{m}" for m in _Q_METRICS]
    n_ax = d[zc].notna().sum(axis=1)
    d["Z_Q"] = d[zc].astype("float64").mean(axis=1, skipna=True).astype("float32")
    d["Z_Q"] = d["Z_Q"].where(n_ax >= 1)

    have_sg = float(d["zQ_share_growth3y"].notna().mean())
    LOG.ok(f"Q축 완성 — 관측 {int(d['Z_Q'].notna().sum()):,}/{len(d):,}행 "
           f"({100*d['Z_Q'].notna().mean():.1f}%) · 지표 5개 중 평균 {n_ax.mean():.2f}개 가용")
    if have_sg < 0.30:
        LOG.warn(f"주식수 증가율(3년) 가용률이 {100*have_sg:.1f}% 로 낮습니다. §5.3 은 이 항목을 "
                 f"'반드시 포함'으로 지정합니다 — 소형주는 증자·CB 로 주당지표가 악화되는 사례가 "
                 f"많아 이 항목 없이는 Q축이 오작동할 수 있습니다. DART 주식총수 수집 상태를 "
                 f"확인하세요(콜드빌드 미완이면 재실행 시 이어받습니다).")
        PIPE.note("WARN: 주식수 증가율 커버리지 부족 — Q축 해석 시 감안")
    return d


# ── F 축 (§5.4) ─────────────────────────────────────────────────────────────────────────────
def fetch_flow_netbuy(cal: pd.DataFrame, px_daily: pd.DataFrame,
                      window: int = FLOW_WINDOW_DAYS) -> pd.DataFrame:
    """리밸런싱 시점별 외국인·기관 `window` 거래일 순매수(원). 두 경로를 쓴다.

      ① pykrx get_market_net_purchases_of_equities(from, to, market, investor)
         → 구간 집계를 시장 단위로 한 번에 준다. 시점 40 × 시장 2 × 투자자 2 = 160 호출.
      ② 폴백: 공용 코어가 받아둔 일별 수급(krx_investor_flows)을 창 길이만큼 롤링 합산.
         종목별 2,400 호출이 필요하지만 이미 캐시가 있으면 공짜다.

    ★ ①을 쓰는 이유는 속도만이 아니다. 종목별 호출은 폐지 종목에서 자주 빈손으로 돌아오는데
      그걸 '0 순매수'로 오해하면 폐지 직전 종목이 수급 중립으로 둔갑한다. 시장 단위 집계는
      그 시점에 실제 거래된 종목만 담고 있어 결측과 0 이 구분된다.
    """
    cols = ["code", "rebal", "foreign_net", "inst_net", "flow_src"]
    key = f"qvf_flow_netbuy_w{int(window)}"
    cached = VAULT.get_table(key, scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rebal"] = as_ts_series(cached["rebal"])
        have = set(cached["rebal"].dropna().dt.strftime("%Y-%m-%d"))
        LOG.info(f"캐시에서 수급({window}일) {len(cached):,}행 · {len(have)}개 시점 재사용")

    td = qvf_trading_days(px_daily)
    todo = [r for r in cal.itertuples(index=False)
            if as_ts(r.rebal).strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    new_rows: List[dict] = []
    fn = getattr(pykrx_stock, "get_market_net_purchases_of_equities", None) if pykrx_stock else None
    if todo and fn is not None:
        KRXG.warmup()
        LOG.info(f"수급 {window}거래일 순매수 수집 {len(todo)}개 시점 × 시장2 × 투자자2 "
                 f"(= 최대 {len(todo)*4} 호출 — 종목별 수집이면 수천 호출입니다)")
        fails = 0
        for r in tqdm(todo, desc=f"수급 {window}일", ncols=88, leave=False):
            sd = as_ts(r.signal_date)
            i = int(np.searchsorted(td, np.datetime64(sd), side="right")) - 1
            j = max(0, i - int(window) + 1)
            if i < 0 or not len(td):
                continue
            d0, d1 = as_ts(td[j]).strftime("%Y%m%d"), as_ts(td[i]).strftime("%Y%m%d")
            acc: Dict[str, dict] = {}
            got_any = False
            for mkt in ("KOSPI", "KOSDAQ"):
                for inv, fld in (("외국인", "foreign_net"), ("기관합계", "inst_net")):
                    t = KRXG.call(fn, d0, d1, mkt, inv)
                    if t is None or not len(t):
                        continue
                    got_any = True
                    t = t.reset_index()
                    ccol = next((c for c in t.columns if str(c) in ("티커", "code", "종목코드")), t.columns[0])
                    vcol = next((c for c in t.columns if "순매수거래대금" in str(c)), None)
                    if vcol is None:
                        vcol = next((c for c in t.columns if "순매수" in str(c) and "대금" in str(c)), None)
                    if vcol is None:
                        continue
                    for cc, vv in zip(t[ccol].map(to_code6), pd.to_numeric(t[vcol], errors="coerce")):
                        if not cc:
                            continue
                        acc.setdefault(cc, {})[fld] = float(vv) if pd.notna(vv) else np.nan
            fails = 0 if got_any else fails + 1
            if fails >= 5:
                LOG.warn("수급 수집이 연속 5회 비었습니다(세션 만료/차단 추정) — 중단하고 "
                         "일별 수급 폴백으로 넘어갑니다.")
                break
            for cc, v in acc.items():
                new_rows.append({"code": cc, "rebal": r.rebal,
                                 "foreign_net": v.get("foreign_net", np.nan),
                                 "inst_net": v.get("inst_net", np.nan),
                                 "flow_src": "krx_period_netbuy"})

    frames = [cached] if cached is not None and len(cached) else []
    if new_rows:
        frames.append(pd.DataFrame(new_rows))
    F = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)

    # ② 폴백: 일별 수급 롤링 합산 (경로 ①이 아무것도 못 준 시점만)
    missing = [r for r in cal.itertuples(index=False)
               if len(F) == 0 or not (as_ts_series(F["rebal"]) == as_ts(r.rebal)).any()]
    if missing:
        fl = VAULT.get_table("krx_investor_flows", scope="shared")
        if fl is not None and len(fl):
            LOG.info(f"수급 {len(missing)}개 시점을 일별 수급 캐시에서 롤링 합산으로 채웁니다.")
            fl = fl.copy()
            fl["date"] = as_ts_series(fl["date"])
            fl = fl.dropna(subset=["code", "date"]).sort_values(["code", "date"], kind="stable")
            g = fl.groupby("code", observed=True)
            for c in ("foreign_net", "inst_net"):
                if c not in fl.columns:
                    fl[c] = np.nan
                fl[f"_r_{c}"] = g[c].transform(
                    lambda s: s.rolling(int(window), min_periods=max(5, int(window) // 4)).sum())
            R = fl[["code", "date", "_r_foreign_net", "_r_inst_net"]].rename(
                columns={"date": "px_date"}).sort_values("px_date", kind="stable")
            sig = pd.DataFrame([{"rebal": r.rebal, "signal_date": r.signal_date} for r in missing])
            L = (sig.assign(_k=1).merge(pd.DataFrame({"code": sorted(fl["code"].unique()), "_k": 1}),
                                        on="_k").drop(columns="_k")).sort_values("signal_date", kind="stable")
            M = pd.merge_asof(L, R, left_on="signal_date", right_on="px_date", by="code",
                              direction="backward", tolerance=pd.Timedelta(days=20))
            M = M.dropna(subset=["_r_foreign_net", "_r_inst_net"], how="all")
            if len(M):
                add = M[["code", "rebal", "_r_foreign_net", "_r_inst_net"]].rename(
                    columns={"_r_foreign_net": "foreign_net", "_r_inst_net": "inst_net"})
                add["flow_src"] = "daily_rolling"
                F = pd.concat([F, add], ignore_index=True)
        else:
            LOG.warn(f"수급 {len(missing)}개 시점을 채우지 못했습니다 — 해당 시점의 F축은 결측이며 "
                     f"VARIANT-VQF 는 그 시점에서 VQ 와 동일하게 동작합니다(0 으로 채우지 않음).")

    if not len(F):
        LOG.warn("수급 데이터를 전혀 확보하지 못했습니다. VARIANT-VQF 는 사실상 VQ 와 같아집니다 — "
                 "이 사실을 §9 판정에 반드시 반영해 보고합니다.")
        return pd.DataFrame(columns=cols)
    F["rebal"] = as_ts_series(F["rebal"])
    F = F.dropna(subset=["code", "rebal"]).drop_duplicates(["code", "rebal"], keep="last")
    if new_rows:
        out = F.copy()
        out["rebal"] = out["rebal"].dt.strftime("%Y-%m-%d")
        VAULT.put_table(key, out, scope="shared", domain="flow",
                        source=f"pykrx net purchases {window}d")
    PIPE.io("OUT", "DRIVE", key, F, source="krx flow")
    return downcast_q(F.reindex(columns=cols))


def axis_F(P: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """§5.4 — 순매수를 유동주식 시가총액으로 정규화한다.

    ★ 정규화 없이 절대 금액을 쓰면 시총 큰 종목이 자동으로 상위를 점유한다. 하위1000 안에서도
      시총이 수십 배 차이나므로 이건 신호가 아니라 크기 랭킹이 된다.
    ★ 유동주식 비율은 공개 API 로 소급 조회가 어렵다. 대신 PIT 로 확보 가능한 자기주식 수를
      빼서 부분적으로 유동주식 시총에 근접시키고, 그 한계를 로그에 명시한다.
    """
    d = P.copy()
    for c in ("foreign_net", "inst_net", "flow_src"):
        if c in d.columns:
            d = d.drop(columns=[c])
    if flows is not None and len(flows):
        d = d.merge(flows[["code", "rebal", "foreign_net", "inst_net", "flow_src"]],
                    on=["code", "rebal"], how="left")
    else:
        d["foreign_net"] = np.nan
        d["inst_net"] = np.nan
        d["flow_src"] = None

    shares = col(d, "shares_issued").where(col(d, "shares_issued") > 0, col(d, "shares"))
    tre = col(d, "shares_treasury").fillna(0.0)
    float_sh = (shares - tre).where(lambda s: s > 0)
    float_cap = (float_sh * col(d, "close")).where(lambda s: s > 0)
    d["float_cap"] = float_cap.where(float_cap.notna(), col(d, "mktcap"))
    n_adj = int((float_cap.notna() & (tre > 0)).sum())

    d["flow_f"] = safe_div(col(d, "foreign_net"), d["float_cap"])
    d["flow_i"] = safe_div(col(d, "inst_net"), d["float_cap"])

    obs = d[["flow_f", "flow_i"]].notna().any(axis=1)
    nz = ((col(d, "flow_f").fillna(0).abs() > 0) | (col(d, "flow_i").fillna(0).abs() > 0))
    nonzero_ratio = float(nz[obs].mean()) if int(obs.sum()) else float("nan")
    globals()["FLOW_NONZERO_RATIO"] = nonzero_ratio

    d["zF_foreign"] = _cell_ladder_z(d, d["flow_f"])
    d["zF_inst"] = _cell_ladder_z(d, d["flow_i"])
    zc = ["zF_foreign", "zF_inst"]
    n_ax = d[zc].notna().sum(axis=1)
    d["Z_F"] = d[zc].astype("float64").mean(axis=1, skipna=True).astype("float32")
    d["Z_F"] = d["Z_F"].where(n_ax >= 1)

    LOG.table([["수급 관측 보유", f"{int(obs.sum()):,} / {len(d):,} ({100*obs.mean():.1f}%)"],
               ["비영(non-zero) 관측 비율", f"{100*nonzero_ratio:.1f}%" if np.isfinite(nonzero_ratio) else "—"],
               ["유동주식 보정(자기주식 차감) 적용", f"{n_adj:,}행"],
               ["F축 z 산출", f"{int(d['Z_F'].notna().sum()):,}행"]],
              ["항목", "값"], ["l", "r"],
              title="F축(수급) 진단 — §5.4 결측 처리 및 §9-C4 판정 입력")
    if np.isfinite(nonzero_ratio) and nonzero_ratio < 0.30:
        LOG.warn(f"수급 비영 관측 비율이 {100*nonzero_ratio:.1f}% 로 30% 미만입니다. "
                 f"수급 축은 사실상 소수 종목에만 작동하는 신호이며, 이것이 §1 '검증되지 않은 "
                 f"전제'에 대한 데이터의 답입니다. §9-C4 는 미충족으로 판정됩니다.")
    LOG.info("한계 명시: 유동주식 비율의 PIT 시계열은 공개 경로로 확보되지 않아, 발행주식수에서 "
             "자기주식만 차감한 근사 유동시총을 분모로 씁니다. 대주주·우리사주 물량은 반영되지 "
             "않으므로 유동시총이 과대추정되는 방향이며, 그만큼 정규화 강도가 약합니다.")
    return d


FLOW_NONZERO_RATIO: float = float("nan")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-Q1  1차 필터 — U-1000 → U-200, 3변형 비교 (§5.5, §5.6)                                 ║
# ║                                                                                          ║
# ║  이 전략의 핵심 실험은 "수급 축이 실제로 다른 종목을 뽑는가" 다.                            ║
# ║  세 변형을 끝까지 독립 실행하고, 중복률·특성·회전율을 나란히 놓고 판단한다(§9).             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def score1(P: pd.DataFrame, variant: str) -> pd.Series:
    """Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F  (§5.5 사전등록 가중치, 튜닝 금지)

    ★ 결측 축 처리: 가중치는 고정이지만 축 자체가 결측인 행이 있다. 결측을 0(=셀 평균)으로
      채우면 그 종목이 '평균적인 종목'으로 둔갑해 분산이 압축되고, 결측이 많은 초소형주가
      일제히 중앙으로 몰린다. 대신 '가용 축에 대해 가중치를 재정규화'하고, 재정규화가
      일어난 비율을 반드시 로그로 남긴다(수급 축이 사실상 죽어 있으면 여기서 드러난다).
    """
    if variant not in VARIANT_W:
        raise KeyError(f"알 수 없는 변형: {variant} (가능: {list(VARIANT_W)})")
    wv, wq, wf = VARIANT_W[variant]
    parts = [(col(P, "Z_V"), wv), (col(P, "Z_Q"), wq), (col(P, "Z_F"), wf)]
    parts = [(z, w) for z, w in parts if w > 0]
    num = pd.Series(0.0, index=P.index)
    den = pd.Series(0.0, index=P.index)
    for z, w in parts:
        ok = z.notna()
        num = num.add((z.fillna(0.0) * w).where(ok, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(ok, w, 0.0), index=P.index), fill_value=0.0)
    s = (num / den.where(den > 0)).astype("float32")
    full_w = sum(w for _z, w in parts)
    renorm = float(((den > 0) & (den < full_w - 1e-9)).mean())
    if renorm > 0.01:
        LOG.info(f"  [{variant}] 축 결측으로 가중치 재정규화된 행 {100*renorm:.1f}% "
                 f"(0 으로 채우지 않고 가용 축만으로 계산)")
    return s


def _rank_pick(g: pd.DataFrame, n: int, score_col: str) -> pd.Index:
    """상위 n 선정. 동점은 명시적 키로 깬다 — 행 순서(=대개 종목코드 오름차순)로 깨면
    포트폴리오가 데이터가 아니라 정렬의 함수가 된다."""
    keys = [score_col] + [c for c in ("Z_V", "mktcap", "code") if c in g.columns]
    asc = [False] + [False if c in ("Z_V",) else True for c in keys[1:]]
    return g.sort_values(keys, ascending=asc, kind="mergesort").head(n).index


def build_u200(P: pd.DataFrame, variants: Sequence[str] = VARIANTS,
               n: int = U200_N) -> pd.DataFrame:
    """각 변형별 Score1 과 U-200 소속 플래그를 패널에 추가한다.

    반환 패널에 추가되는 컬럼:  score1_<V>  ·  u200_<V> (bool)
    """
    d = P.copy()
    for v in variants:
        d[f"score1_{v}"] = score1(d, v)
    for v in variants:
        sc = f"score1_{v}"
        flag = pd.Series(False, index=d.index)
        for _t, g in d.groupby("rebal", observed=True):
            gg = g[g[sc].notna()]
            if gg.empty:
                continue
            flag.loc[_rank_pick(gg, min(n, len(gg)), sc)] = True
        d[f"u200_{v}"] = flag
    rows = []
    for v in variants:
        cnt = d.groupby("rebal", observed=True)[f"u200_{v}"].sum()
        rows.append([v, f"{cnt.mean():,.0f}", f"{cnt.min():,.0f}", f"{cnt.max():,.0f}",
                     f"{int(d[f'score1_{v}'].notna().sum()):,}"])
    LOG.table(rows, ["변형", "U-200 평균", "최소", "최대", "Score1 산출행"],
              ["c", "r", "r", "r", "r"],
              title=f"1차 필터 결과 (§5.5 사전등록 가중치 · 목표 상위 {n}종목)")
    return d


# ── §5.6 필수 보고 항목 ─────────────────────────────────────────────────────────────────────
def _jaccard(a: set, b: set) -> float:
    u = a | b
    return float(len(a & b) / len(u)) if u else float("nan")


def report_variant_comparison(P: pd.DataFrame, variants: Sequence[str] = VARIANTS,
                              rep_cov: Optional[pd.DataFrame] = None) -> dict:
    """§5.6 — 세 변형이 실질적으로 다른 종목을 뽑는지 확인한다. [5] 완료 시점의 중간 보고."""
    LOG.banner("① 1차필터 3변형 비교 (§5.6)",
               "변형들이 실제로 다른 종목을 뽑는가 · 수급 축이 유동성/커버리지 편향을 만드는가")

    sets: Dict[str, Dict[pd.Timestamp, set]] = {}
    for v in variants:
        sets[v] = {t: set(g.loc[g[f"u200_{v}"], "code"])
                   for t, g in P.groupby("rebal", observed=True)}

    # (1) 변형 간 중복률
    ov_rows, ov = [], {}
    for i, a in enumerate(variants):
        for b in variants[i + 1:]:
            vals = [_jaccard(sets[a].get(t, set()), sets[b].get(t, set()))
                    for t in sorted(set(sets[a]) | set(sets[b]))]
            vals = [x for x in vals if np.isfinite(x)]
            m = float(np.mean(vals)) if vals else float("nan")
            ov[f"{a}~{b}"] = m
            ov_rows.append([f"{a} ∩ {b}", f"{m:.3f}",
                            f"{np.min(vals):.3f}" if vals else "—",
                            f"{np.max(vals):.3f}" if vals else "—",
                            "실질적으로 동일" if m >= 0.85 else "충분히 다름"])
    LOG.table(ov_rows, ["변형 쌍", "평균 중복률(교집합/합집합)", "최소", "최대", "판정(§9-C3 기준 0.85)"],
              ["l", "r", "r", "r", "l"],
              title="변형 간 U-200 중복률 — 이 값이 0.85 이상이면 변형 비교 자체가 무의미해진다")

    # (2) 변형별 특성 (시총 · 유동성 · 섹터 집중도)
    ch_rows = []
    for v in variants:
        sub = P[P[f"u200_{v}"]]
        if sub.empty:
            ch_rows.append([v, "—", "—", "—", "—", "—"])
            continue
        cap_med = float(pd.to_numeric(sub["mktcap"], errors="coerce").median())
        adtv_med = float(pd.to_numeric(sub["adtv"], errors="coerce").median())
        # 섹터 집중도(HHI): 1 에 가까울수록 한 섹터 쏠림
        sh = sub.groupby("sector", observed=True).size() / len(sub)
        hhi = float((sh ** 2).sum())
        n_sec = int(sub["sector"].nunique())
        ch_rows.append([v, f"{cap_med/1e8:,.0f}억", f"{adtv_med/1e8:,.2f}억",
                        f"{n_sec}", f"{hhi:.3f}", f"{len(sub):,}"])
    LOG.table(ch_rows, ["변형", "시총 중앙값", "60일 ADTV 중앙값", "섹터 수", "섹터 HHI", "총 관측"],
              ["c", "r", "r", "r", "r", "r"],
              title="변형별 U-200 특성 — 수급 축 추가가 유동성 편향을 만드는지")

    # (3) 리포트 커버리지 (§5.6 — 수급 축이 '커버리지 프록시'에 불과한지 판별)
    cov = {}
    if rep_cov is not None and len(rep_cov):
        C = rep_cov[["code", "rebal", "n_reports"]].copy()
        cov_rows = []
        for v in variants:
            sub = P[P[f"u200_{v}"]][["code", "rebal"]].merge(C, on=["code", "rebal"], how="left")
            r = float((pd.to_numeric(sub["n_reports"], errors="coerce").fillna(0) > 0).mean()) \
                if len(sub) else float("nan")
            cov[v] = r
            cov_rows.append([v, f"{100*r:.1f}%" if np.isfinite(r) else "—", f"{len(sub):,}"])
        LOG.table(cov_rows, ["변형", "리포트 ≥1건 종목 비율", "관측"], ["c", "r", "r"],
                  title="변형별 U-200 리포트 커버리지 (§9-C5 판정 입력)")
        if np.isfinite(cov.get("VQF", np.nan)) and np.isfinite(cov.get("VQ", np.nan)):
            gap = cov["VQF"] - cov["VQ"]
            LOG.info(f"VQF − VQ 커버리지 격차 {100*gap:+.1f}%p — "
                     + ("격차가 크면 수급 축은 '기관이 보는 종목=리포트 있는 종목' 을 재발견한 "
                        "커버리지 프록시일 뿐입니다." if gap > 0.10 else
                        "격차가 작아 수급 축이 커버리지의 단순 대리변수는 아닙니다."))
    else:
        LOG.warn("리포트 커버리지 입력이 없어 §5.6 커버리지 비교를 생략합니다 "
                 "(§9-C5 는 '판정 불가'로 보고됩니다).")

    # (4) 변형별 U-200 회전율
    tn_rows, turn = [], {}
    for v in variants:
        ts = sorted(sets[v])
        vals = []
        for a, b in zip(ts, ts[1:]):
            sa, sb = sets[v][a], sets[v][b]
            if not sa and not sb:
                continue
            vals.append(len(sb - sa) / max(len(sb), 1))
        m = float(np.mean(vals)) if vals else float("nan")
        turn[v] = m
        tn_rows.append([v, f"{100*m:.1f}%" if np.isfinite(m) else "—"])
    LOG.table(tn_rows, ["변형", "분기 평균 U-200 교체율"], ["c", "r"],
              title="변형별 회전율 — 수급 축은 60일 창이라 회전율을 크게 높일 수 있다(비용에 직결)")

    LOG.info("§11 중간 보고 지점입니다. 위 중복률이 0.85 이상이면 이후 실험의 의미가 축소되며, "
             "그 사실을 §9 판정(C3)에 그대로 반영합니다. 자동으로 중단하지 않고 계속 진행합니다.")
    return {"overlap": ov, "coverage": cov, "turnover": turn,
            "sets": {v: {str(t): sorted(s) for t, s in sets[v].items()} for v in variants}}



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q3  DART 하드팩트 ΔNONFIN + 배제 플래그 (§6.1)  —  LLM 호출 없음                       ║
# ║                                                                                          ║
# ║  추출 원칙(엄격): 완료형 동사 + 날짜 + 숫자가 모두 있는 사실만 추출한다.                    ║
# ║  전망·계획·의지·기대·예정은 전부 제외한다. 추출기는 좋다/나쁘다를 판단하지 않는다.          ║
# ║                                                                                          ║
# ║  ★ 설계 핵심: '구조화 엔드포인트로 얻을 수 있는 것을 본문 파싱으로 얻으려 하지 않는다'.     ║
# ║    연구개발비/매출액·설비투자·자본잠식률은 이미 받아둔 재무제표로 계산된다. CB/BW 발행,     ║
# ║    최대주주 변경, 단일판매·공급계약은 공시목록(list.json) 한 번의 스윕으로 잡힌다.          ║
# ║    본문(document.xml)이 정말로 필요한 것은 주석에만 있는 4가지뿐이다:                       ║
# ║      특허 등록건수 · 연구개발 인력 · 특수관계자 거래비중 · 우발부채/소송/감사의견 강조사항   ║
# ║    이 구분을 흐리면 호출량이 10배가 되고 콜드빌드가 몇 주가 된다.                           ║
# ║                                                                                          ║
# ║  ★ 구형 공시는 스캔 PDF 비중이 높아 기계판독이 불가능하다(§0.4). 실패율을 반드시 측정하고   ║
# ║    '섹션 없음' / '판독 불가' / 'API 무응답' 을 구분해서 보고한다 — 셋은 원인이 다르다.      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 원문 XML 을 드라이브에 통째로 보관할지. 사업보고서 하나가 수 MB 이고 1만 건이면 수십 GB 라
# 기본은 False 다. 우리가 캐시하는 것은 '추출된 사실 테이블'이며 그것이 공용 인덱스에 남는다.
DART_STORE_RAW_DOCS = False

DOC_API = "document.xml"

# 미래형/의지 표현 — 하나라도 걸리면 그 문장은 사실이 아니다(§6.1)
_FORWARD_RE = re.compile(
    r"예정|계획|전망|기대|목표|추진\s*(?:할|중|예정)|예상|가능성|모색|검토\s*중|"
    r"할\s*것|하고자|하려|추정|예측|목표로")
# 완료형 동사
_DONE_RE = re.compile(
    r"하였|했[다으]|되었|됐[다으]|완료|체결|취득|등록(?:되|하|을|된|함)|선정(?:되|하|된|됨)|"
    r"납품|수주|출원(?:하|되|됨)|승인(?:받|되)|인수(?:하|함)|설립(?:하|됨)")
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DATE_RE = re.compile(r"(?:19|20)\d{2}\s*[.\-/년]\s*(?:\d{1,2})\s*[.\-/월]?|(?:19|20)\d{2}\s*년")


def is_completed_fact(sent: str) -> bool:
    """§6.1 — 완료형 동사 + 날짜 + 숫자가 모두 있고, 미래형 표현이 없어야 사실로 인정한다."""
    if not sent or len(sent) > 800:
        return False
    if _FORWARD_RE.search(sent):
        return False
    return bool(_DONE_RE.search(sent) and _NUM_RE.search(sent) and _DATE_RE.search(sent))


# ── 공시목록 스윕 (거래소공시·외부감사 포함) ────────────────────────────────────────────────
QVF_DISCLOSURE_PATTERNS = {
    # 긍정 하드팩트
    "supply_contract":  r"단일판매[·ㆍ・]?\s*공급계약|공급계약\s*체결|수주",
    # 배제 플래그
    "cb_issue":         r"전환사채",
    "bw_issue":         r"신주인수권부사채",
    "major_holder_chg": r"최대주주\s*(?:변경|변동)",
    "audit_report":     r"감사보고서|감사의견",
    "lawsuit_filed":    r"소송\s*(?:등의?\s*)?(?:제기|판결)",
    "capital_impair":   r"자본잠식",
}
QVF_DISCLOSURE_TYPES = ("A", "B", "F", "I")   # 정기 · 주요사항 · 외부감사 · 거래소공시


def fetch_disclosures_qvf(start: str, end: str) -> pd.DataFrame:
    """월 단위 시장 전체 공시목록 스윕. 공용 코어의 dart_disclosures 와 '별도 테이블'을 쓴다.

    ★ 같은 테이블을 쓰면 안 되는 이유: 코어는 A·B 만 훑는데, 그 캐시에 이미 있는 달을
      QVF 가 '완료'로 보면 거래소공시(I)·외부감사(F)를 영원히 못 받는다. 캐시 키가
      '어떤 유형까지 훑었는가' 를 담고 있지 않으므로 테이블 자체를 분리한다.
    """
    cols = ["corp_code", "stock_code", "rcept_no", "rcept_dt", "report_nm", "event", "pblntf_ty"]
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 미입력 — 공시목록 스윕 불가. ΔNONFIN 의 공급계약 항목과 "
                 "CB/BW·최대주주변경 배제플래그가 전부 결측이 됩니다.")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_disclosures_qvf", scope="shared")
    have: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        have = set(cached["rcept_dt"].dropna().dt.to_period("M").astype(str))
        LOG.info(f"캐시에서 QVF 공시목록 {len(cached):,}행 · {len(have)}개월 재사용")

    months = pd.period_range(as_ts(start) - pd.DateOffset(months=6), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have]
    if RUN_MODE == "CACHED":
        todo = []

    breaker = {"fail": 0}

    def _one(m):
        rows = []
        for ty in QVF_DISCLOSURE_TYPES:
            page, empty = 1, 0
            while page <= 100:
                if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                    return rows
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100, "last_reprt_at": "N"})
                if not js or not isinstance(js.get("list"), list) or not js["list"]:
                    empty += 1
                    breaker["fail"] += 1 if not js else 0
                    break
                breaker["fail"] = 0
                for r in js["list"]:
                    r["pblntf_ty"] = ty
                rows.extend(js["list"])
                if page >= int(js.get("total_page", 1) or 1):
                    break
                page += 1
        return rows

    new = []
    if todo:
        LOG.info(f"QVF 공시목록 스윕 {len(todo)}개월 × 유형 {len(QVF_DISCLOSURE_TYPES)} "
                 f"(남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        for chunk in pmap_io(_one, todo, workers=min(N_WORKERS_IO, 6), desc="DART 공시목록(QVF)"):
            if chunk:
                new.extend(chunk)
        if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
            LOG.warn(f"서킷 브레이커 발동 — 연속 실패 {CIRCUIT_BREAKER_FAILS}회. 공시목록 스윕을 "
                     f"중단하고 받은 만큼만 사용합니다.")

    frames = [cached] if cached is not None and len(cached) else []
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no", "rcept_dt",
                            "report_nm", "pblntf_ty") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=cols)
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["event"] = ""
    for ev, pat in QVF_DISCLOSURE_PATTERNS.items():
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["event"] == "")
        D.loc[hit, "event"] = ev
    if new:
        VAULT.put_table("dart_disclosures_qvf", D, scope="shared", domain="dart",
                        source="opendart list.json A/B/F/I")
    # §4 — 접수일 다음 거래일부터 사용 가능
    D["knowledge_date"] = next_trading_day_series(D["rcept_dt"])
    D = pit_frame(D, "rcept_dt", "knowledge_date", source="dart")
    counts = {k: int((D["event"] == k).sum()) for k in QVF_DISCLOSURE_PATTERNS}
    LOG.ok(f"QVF 공시목록 {len(D):,}건 — " +
           ", ".join(f"{k}={v:,}" for k, v in counts.items() if v))
    PIPE.io("OUT", "DRIVE", "dart_disclosures_qvf", D, source="opendart list.json")
    return downcast_q(D)


# ── 사업보고서 본문 (주석에만 있는 항목) ────────────────────────────────────────────────────
_SECTIONS = {
    "ip":        r"(지식재산권|산업재산권|특허|공업소유권)",
    "rnd":       r"(연구개발\s*(?:활동|조직|인력|실적)|기술개발\s*조직)",
    "related":   r"(특수관계자|특수관계인)\s*(?:와의)?\s*(?:거래|매출|매입)",
    "contingent": r"(우발부채|지급보증|약정사항|담보제공)",
    "lawsuit":   r"(소송|계류중인\s*소송|법적\s*분쟁)",
    "audit":     r"(강조사항|특기사항|감사의견|핵심감사사항)",
    "holder":    r"(최대주주\s*(?:에?\s*관한\s*사항|현황)|주주에\s*관한\s*사항)",
}
_SECTION_RE = {k: re.compile(v) for k, v in _SECTIONS.items()}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def _xml_to_text(raw: bytes) -> Tuple[str, str]:
    """DART document.xml (ZIP) → 평문. (텍스트, 상태) 를 돌려준다.

    상태: ok / not_zip / empty_zip / decode_fail / no_text(스캔본 추정)
    ★ '스캔본'과 '섹션 없음'을 구분하는 유일한 방법이 여기다. 태그를 걷어낸 뒤 남는 글자가
      거의 없으면 그 파일은 이미지이며, 정규식을 아무리 고쳐도 절대 읽히지 않는다.
    """
    if not raw or len(raw) < 64:
        return "", "empty"
    if raw[:2] != b"PK":
        head = raw[:300].decode("utf-8", "ignore")
        if "status" in head:
            return "", "api_error"
        return "", "not_zip"
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in zf.namelist() if n.lower().endswith((".xml", ".html", ".htm"))]
        if not names:
            return "", "empty_zip"
        blob = b"".join(zf.read(n) for n in names[:6])
    except Exception:
        return "", "empty_zip"
    txt = ""
    for enc in ("utf-8", "euc-kr", "cp949", "utf-16"):
        try:
            t = blob.decode(enc)
        except Exception:
            continue
        if len(_HANGUL.findall(t[:8000])) > 20:
            txt = t
            break
        if not txt:
            txt = t
    if not txt:
        return "", "decode_fail"
    txt = _TAG_RE.sub(" ", txt)
    txt = _WS_RE.sub(" ", txt)
    han = len(_HANGUL.findall(txt))
    if han < 500:
        # 태그를 걷어냈는데 한글이 거의 없다 = 본문이 이미지(스캔본)
        return txt, "no_text_scan"
    return txt, "ok"


def _section(text: str, key: str, span: int = 6000) -> str:
    m = _SECTION_RE[key].search(text)
    if not m:
        return ""
    return text[m.start(): m.start() + span]


def _count_patents(sect: str) -> Optional[float]:
    if not sect:
        return None
    m = re.search(r"특허\D{0,12}?([\d,]{1,6})\s*건", sect)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            pass
    n = len(re.findall(r"특허\s*(?:권|등록|제?\s*\d{2,})", sect))
    return float(n) if n else None


def _rnd_headcount(sect: str) -> Optional[float]:
    if not sect:
        return None
    for pat in (r"연구\s*(?:개발)?\s*인력\D{0,12}?([\d,]{1,6})\s*명",
                r"연구소\D{0,20}?([\d,]{1,6})\s*명",
                r"(?:연구원|연구개발\s*인원)\D{0,10}?([\d,]{1,6})\s*명"):
        m = re.search(pat, sect)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _ratio_pct(sect: str, pats: Sequence[str]) -> Optional[float]:
    for p in pats:
        m = re.search(p, sect)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                return v / 100.0 if v > 1.5 else v
            except Exception:
                continue
    return None


def _amount_krw(sect: str, pats: Sequence[str]) -> Optional[float]:
    """'12,345백만원' / '1,234억원' 같은 표기를 원 단위로 환산한다."""
    for p in pats:
        for m in re.finditer(p, sect):
            try:
                v = float(m.group(1).replace(",", ""))
            except Exception:
                continue
            tail = sect[m.end(): m.end() + 8]
            if "억" in m.group(0) or "억" in tail:
                v *= 1e8
            elif "백만" in m.group(0) or "백만" in tail:
                v *= 1e6
            elif "천원" in m.group(0) or "천원" in tail:
                v *= 1e3
            return v
    return None


def extract_report_facts(text: str) -> dict:
    """사업보고서 본문 → 하드팩트 수치. 판단하지 않고 숫자만 뽑는다."""
    out: Dict[str, Any] = {}
    ip = _section(text, "ip")
    out["patents"] = _count_patents(ip)
    out["sect_ip"] = bool(ip)

    rnd = _section(text, "rnd")
    out["rnd_headcount"] = _rnd_headcount(rnd)
    out["sect_rnd"] = bool(rnd)
    # 정부 R&D 과제: 완료형 사실 문장만 인정
    gov = 0
    for s in _SENT_SPLIT.split(rnd)[:400]:
        if re.search(r"(국책|정부|국가)\s*(과제|연구개발사업|R&D)", s) and is_completed_fact(s):
            gov += 1
    out["gov_rnd_facts"] = float(gov)

    rel = _section(text, "related")
    out["sect_related"] = bool(rel)
    out["related_sales_ratio"] = _ratio_pct(
        rel, [r"매출\D{0,20}?([\d,.]+)\s*%", r"비중\D{0,10}?([\d,.]+)\s*%"])
    out["related_purchase_ratio"] = _ratio_pct(
        rel, [r"매입\D{0,20}?([\d,.]+)\s*%"])

    cg = _section(text, "contingent")
    out["sect_contingent"] = bool(cg)
    out["contingent_amt"] = _amount_krw(
        cg, [r"지급보증\D{0,24}?([\d,]{3,})", r"우발부채\D{0,24}?([\d,]{3,})"])

    ls = _section(text, "lawsuit")
    out["sect_lawsuit"] = bool(ls)
    out["lawsuit_amt"] = _amount_krw(
        ls, [r"소송\s*가?액\D{0,24}?([\d,]{3,})", r"청구\s*금액\D{0,24}?([\d,]{3,})"])
    out["lawsuit_new"] = float(sum(1 for s in _SENT_SPLIT.split(ls)[:300]
                                   if re.search(r"소송.{0,20}제기", s) and is_completed_fact(s)))

    au = _section(text, "audit")
    out["sect_audit"] = bool(au)
    out["audit_emphasis"] = float(bool(
        re.search(r"(강조사항|특기사항|계속기업|핵심감사사항)", au) and
        not re.search(r"해당사항\s*없|없습니다", au[:400])))

    hd = _section(text, "holder")
    out["sect_holder"] = bool(hd)
    out["major_holder_pct"] = _ratio_pct(
        hd, [r"최대주주\D{0,40}?([\d,.]+)\s*%", r"소유\s*비율\D{0,10}?([\d,.]+)\s*%"])
    return out


def fetch_annual_report_facts(targets: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """targets: corp_code · bsns_year · rcept_no · rcept_dt (사업보고서 접수건)
    반환: (사실 테이블, 파싱 통계)

    ★ 파싱 결과를 항상 한 행 남긴다. 실패도 행이다 — 실패를 남기지 않으면 재실행마다
      같은 스캔본을 영원히 다시 받고, dart_parse_rate 도 정직하게 계산할 수 없다.
    """
    FACT_COLS = ["corp_code", "bsns_year", "rcept_no", "rcept_dt", "parse_status",
                 "patents", "rnd_headcount", "gov_rnd_facts", "related_sales_ratio",
                 "related_purchase_ratio", "contingent_amt", "lawsuit_amt", "lawsuit_new",
                 "audit_emphasis", "major_holder_pct",
                 "sect_ip", "sect_rnd", "sect_related", "sect_contingent", "sect_lawsuit",
                 "sect_audit", "sect_holder"]
    if targets is None or targets.empty or not DART_API_KEY:
        if not DART_API_KEY:
            LOG.warn("DART_API_KEY 미입력 — 사업보고서 본문 파싱을 건너뜁니다. "
                     "ΔNONFIN 의 특허·연구인력 항목과 특수관계자·우발부채·소송·감사의견 "
                     "배제플래그가 결측이 됩니다(0 으로 채우지 않음).")
        return pd.DataFrame(columns=FACT_COLS), {}

    cached = VAULT.get_table("dart_report_facts", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(cached["rcept_no"].astype(str))
        LOG.info(f"캐시에서 사업보고서 사실 {len(cached):,}건 재사용 "
                 f"(재파싱하지 않습니다 — 스캔본 실패도 기억합니다)")

    todo = targets[~targets["rcept_no"].astype(str).isin(done)].copy()
    if RUN_MODE == "CACHED":
        todo = todo.iloc[0:0]
    stats: Counter = Counter()
    rows: List[dict] = []

    if len(todo):
        LOG.info(f"사업보고서 본문 신규 파싱 대상 {len(todo):,}건 "
                 f"(남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'})")
        breaker = {"fail": 0}

        def _one(rec):
            corp, yr, rno, rdt = rec
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                return None
            if DQUOTA is not None and not DQUOTA.take(1):
                return None
            raw = http_get("https://opendart.fss.or.kr/api/" + DOC_API, source="dart",
                           params={"crtfc_key": DART_API_KEY, "rcept_no": str(rno)},
                           as_bytes=True, tries=2, referer="https://opendart.fss.or.kr/")
            if not raw:
                breaker["fail"] += 1
                return {"corp_code": corp, "bsns_year": yr, "rcept_no": rno,
                        "rcept_dt": rdt, "parse_status": "api_empty"}
            breaker["fail"] = 0
            text, status = _xml_to_text(raw)
            if status == "api_error" and DQUOTA is not None:
                try:
                    if re.search(r'"020"', raw[:300].decode("utf-8", "ignore")):
                        DQUOTA.exhausted = True
                except Exception:
                    pass
            base = {"corp_code": corp, "bsns_year": yr, "rcept_no": rno,
                    "rcept_dt": rdt, "parse_status": status}
            if status != "ok":
                return base
            if DART_STORE_RAW_DOCS:
                VAULT.put_blob("dart", "document_xml", str(rno), raw, "zip",
                               source="opendart document.xml", scope="shared",
                               event_date=rdt, knowledge_date=rdt)
            f = extract_report_facts(text)
            del text, raw
            base.update(f)
            return base

        jobs = list(zip(todo["corp_code"].astype(str), todo["bsns_year"].astype(int),
                        todo["rcept_no"].astype(str), todo["rcept_dt"]))
        CHUNK = 500          # 본문은 수 MB 다. 청크로 끊어 상주 메모리를 평평하게 유지한다.
        for k0 in range(0, len(jobs), CHUNK):
            part = jobs[k0:k0 + CHUNK]
            res = pmap_io(_one, part, workers=min(N_WORKERS_IO, 8),
                          desc=f"사업보고서 본문 {k0//CHUNK+1}/{(len(jobs)-1)//CHUNK+1}")
            rows.extend([r for r in res if r])
            del res
            gc.collect()
            if breaker["fail"] >= CIRCUIT_BREAKER_FAILS:
                LOG.warn(f"서킷 브레이커 발동(연속 실패 {CIRCUIT_BREAKER_FAILS}회) — 본문 파싱 중단.")
                break
            if DQUOTA is not None and DQUOTA.exhausted:
                LOG.warn("DART 호출 한도 도달 — 본문 파싱을 여기서 멈춥니다. "
                         "받은 만큼 저장하고 다음 실행에서 이어받습니다.")
                break

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=FACT_COLS), {}
    F = pd.concat(frames, ignore_index=True)
    for c in FACT_COLS:
        if c not in F.columns:
            F[c] = np.nan
    F = F.drop_duplicates("rcept_no", keep="last")
    if rows:
        VAULT.put_table("dart_report_facts", F, scope="shared", domain="dart",
                        source="opendart document.xml + 규칙기반 추출")
    for s in F["parse_status"].astype(str):
        stats[s] += 1
    PIPE.io("OUT", "DRIVE", "dart_report_facts", F, source="opendart document.xml")
    return downcast_q(F), dict(stats)


def report_parse_rate(F: pd.DataFrame, stats: dict) -> float:
    """§2.1 dart_parse_rate 를 정직하게 분해 보고한다(게이트 ≥ 0.80)."""
    total = int(sum(stats.values())) if stats else 0
    if not total:
        LOG.warn("DART 본문 파싱 시도 기록이 없습니다 — dart_parse_rate 를 산출할 수 없습니다.")
        return float("nan")
    ok = int(stats.get("ok", 0))
    rate = ok / total
    label = {"ok": "정상 판독", "no_text_scan": "스캔본(이미지) — 기계판독 불가",
             "not_zip": "ZIP 아님(대개 API 오류 응답)", "empty_zip": "ZIP 내 문서 없음",
             "decode_fail": "인코딩 판별 실패", "api_empty": "API 무응답/네트워크 실패",
             "api_error": "API 오류코드 응답", "empty": "빈 응답"}
    LOG.table([[label.get(k, k), f"{v:,}", f"{100*v/total:.1f}%"]
               for k, v in sorted(stats.items(), key=lambda x: -x[1])],
              ["파싱 결과", "건수", "비중"], ["l", "r", "r"],
              title=f"DART 본문 기계판독 성공률 = {100*rate:.1f}%  (§2.1 게이트 기준 80%)")
    if len(F):
        sect = [(c, "섹션 발견율") for c in ("sect_ip", "sect_rnd", "sect_related",
                                             "sect_contingent", "sect_lawsuit",
                                             "sect_audit", "sect_holder")]
        okF = F[F["parse_status"].astype(str) == "ok"]
        if len(okF):
            LOG.table([[c.replace("sect_", ""),
                        f"{100*pd.to_numeric(okF[c], errors='coerce').fillna(0).mean():.1f}%"]
                       for c, _ in sect],
                      ["섹션", "정상판독 문서 내 발견율"], ["l", "r"],
                      title="섹션별 발견율 — '판독 실패'와 '해당 섹션 없음'은 다른 사건이다")
    if rate < 0.80:
        LOG.warn(f"dart_parse_rate {100*rate:.1f}% < 80% (§2.1 게이트 미달). "
                 f"주된 사유는 위 표에 분해되어 있습니다. 스캔본 비중이 높다면 정규식을 고쳐도 "
                 f"개선되지 않습니다 — 해당 컴포넌트(특허·연구인력·특수관계자 등)는 결측 처리되고 "
                 f"ΔNONFIN 은 가용 항목만으로 계산됩니다. 전략 전체는 중단하지 않습니다(§2.2).")
    return rate


# ── 최대주주 지분율: 구조화 엔드포인트 폴백 ─────────────────────────────────────────────────
#  §7.2 의 '최대주주 지분율 < 15% 제외'는 3-A 의 하드 규칙인데, 본문 정규식으로 뽑는 지분율은
#  표 레이아웃에 따라 실패율이 높다. 정기보고서 주요정보에 구조화 엔드포인트가 있으므로
#  '본문 추출이 실패한 (회사, 연도)'에 한해서만 추가 호출한다(전량 호출은 호출량 낭비다).
#  ★ 응답 스키마가 기대와 다르면 조용히 결측을 돌려주고, 어느 경로가 값을 채웠는지 로그에 남긴다.
USE_HYSLR_ENDPOINT = True


def fetch_major_holder_stake(targets: pd.DataFrame) -> pd.DataFrame:
    """targets: corp_code · bsns_year  →  corp_code · knowledge_date · major_holder_pct_api

    최대주주 '및 특수관계인 합계' 기말 지분율을 쓴다.
    ★ 행이 (인별 × 주식종류별)로 쪼개져 오고 '계/합계' 소계 행이 섞여 있다. 둘을 함께 더하면
      이중계상이라 지분율이 100% 를 넘는다(코어가 empSttus 에서 이미 겪은 함정과 같은 형태).
    """
    cols = ["corp_code", "bsns_year", "knowledge_date", "major_holder_pct_api"]
    if not (USE_HYSLR_ENDPOINT and DART_API_KEY) or targets is None or targets.empty:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_major_holder", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        LOG.info(f"캐시에서 최대주주 지분율 {len(cached):,}건 재사용")
    jobs = [(str(c), int(y)) for c, y in
            zip(targets["corp_code"], targets["bsns_year"])
            if (str(c), int(y)) not in done]
    if RUN_MODE == "CACHED":
        jobs = []

    def _one(job):
        corp, y = job
        js = dart_api("hyslrSttus.json", {"corp_code": corp, "bsns_year": str(y),
                                          "reprt_code": REPRT_CODES["FY"]})
        if not js or not isinstance(js.get("list"), list) or not js["list"]:
            return None
        d = pd.DataFrame(js["list"])
        rate_col = next((c for c in ("trmend_posesn_stock_qota_rt",
                                     "bsis_posesn_stock_qota_rt") if c in d.columns), None)
        if rate_col is None:
            return None
        rt = pd.to_numeric(d[rate_col].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                           errors="coerce")
        knd = d["stock_knd"].astype(str) if "stock_knd" in d.columns else pd.Series([""] * len(d))
        nm = d["nm"].astype(str) if "nm" in d.columns else pd.Series([""] * len(d))
        common = knd.str.contains("보통", na=False) | (knd.str.strip() == "")
        if not common.any():
            common = pd.Series(True, index=d.index)
        sub_rt, sub_nm = rt[common], nm[common]
        tot = sub_nm.str.replace(r"\s+", "", regex=True).str.contains("계|합계|소계", na=False)
        # 합계 행이 있으면 그것만, 없으면 구성원 합. 둘을 더하면 이중계상이다.
        val = float(sub_rt[tot].max()) if tot.any() and sub_rt[tot].notna().any() \
            else float(sub_rt[~tot].sum(skipna=True))
        if not np.isfinite(val) or val <= 0 or val > 100:
            return None
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": corp, "bsns_year": int(y), "rcept_no": rn,
                "major_holder_pct_api": val / 100.0}

    got = []
    if jobs:
        LOG.info(f"최대주주 지분율 구조화 조회 {len(jobs):,}건 (본문 추출 실패분만) — "
                 f"남은 DART 호출: {DQUOTA.remaining_str() if DQUOTA else '?'}")
        got = [r for r in pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8),
                                  desc="최대주주 지분율") if r]

    frames = [cached] if cached is not None and len(cached) else []
    if got:
        frames.append(pd.DataFrame(got))
    if not frames:
        return pd.DataFrame(columns=cols)
    H = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"],
                                                             keep="last")
    if "rcept_no" not in H.columns:
        H["rcept_no"] = ""
    H["knowledge_date"] = [dart_knowledge_date(rn, REPRT_CODES["FY"], int(y))
                           for rn, y in zip(H["rcept_no"], H["bsns_year"])]
    if got:
        VAULT.put_table("dart_major_holder", H, scope="shared", domain="dart",
                        source="opendart hyslrSttus")
    LOG.ok(f"최대주주 지분율(구조화) {len(H):,}건 확보 — 3-A '지분율 < 15%' 규칙의 근거 보강")
    return downcast_q(H[cols])


# ── ΔNONFIN 조립 ────────────────────────────────────────────────────────────────────────────
NONFIN_ITEMS = ["rnd_headcount_up", "rnd_ratio_up", "patent_up", "capex_up",
                "supply_contract", "gov_rnd"]


def build_nonfin_panel(G: pd.DataFrame, facts: pd.DataFrame, dis: pd.DataFrame,
                       fq: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """ΔNONFIN(f,q) = 항목별 증분 이벤트 개수의 합 (동일가중, 바이너리 태그).

    ★ 전분기(전년) 값이 없으면 '증가'로 세지 않는다. 결측을 0 으로 보고 차분하면
      데이터가 처음 생긴 시점이 전부 '급증'으로 잡혀, 커버리지가 곧 신호가 된다.
    """
    d = G.copy()
    for c in NONFIN_ITEMS + ["dNONFIN"]:
        d[c] = np.nan

    # ① 재무 기반 (추가 호출 없음): 연구개발비/매출액 비율 상승 · 설비투자(유형자산 취득) 증가
    if fq is not None and len(fq):
        Q = fq[["corp_code", "knowledge_date"]].copy()
        Q["rnd_ratio"] = safe_div(col(fq, "rnd_ttm"), col(fq, "revenue_ttm"))
        Q["capex_v"] = col(fq, "capex_ttm").abs()
        Q["knowledge_date"] = as_ts_series(Q["knowledge_date"])
        Q = (Q.dropna(subset=["corp_code", "knowledge_date"])
              .sort_values(["corp_code", "knowledge_date"], kind="stable"))
        g = Q.groupby("corp_code", observed=True)
        for src, dst in (("rnd_ratio", "rnd_ratio_up"), ("capex_v", "capex_up")):
            prev = g[src].shift(1)
            Q[dst] = ((Q[src] > prev) & Q[src].notna() & prev.notna()).astype(float)
            Q[dst] = Q[dst].where(Q[src].notna() & prev.notna())
        d = _asof_attach(d, Q[["corp_code", "knowledge_date", "rnd_ratio_up", "capex_up"]],
                         sec, ["rnd_ratio_up", "capex_up"])

    # ② 사업보고서 본문 기반 (연 1회): 특허 등록 증가 · 연구개발 인력 순증 · 정부 R&D 과제
    if facts is not None and len(facts):
        A = facts[facts["parse_status"].astype(str) == "ok"].copy()
        if len(A):
            A["knowledge_date"] = next_trading_day_series(A["rcept_dt"])
            A = (A.dropna(subset=["corp_code", "knowledge_date"])
                  .sort_values(["corp_code", "knowledge_date"], kind="stable"))
            ga = A.groupby("corp_code", observed=True)
            for src, dst in (("patents", "patent_up"), ("rnd_headcount", "rnd_headcount_up")):
                cur = pd.to_numeric(A[src], errors="coerce")
                prev = ga[src].shift(1)
                prev = pd.to_numeric(prev, errors="coerce")
                A[dst] = ((cur > prev) & cur.notna() & prev.notna()).astype(float)
                A[dst] = A[dst].where(cur.notna() & prev.notna())
            A["gov_rnd"] = (pd.to_numeric(A["gov_rnd_facts"], errors="coerce").fillna(0) > 0).astype(float)
            # ★ 배제플래그의 '전분기 대비 상승' 은 연 1회 관측인 원 프레임에서 차분해야 한다.
            #   as-of 로 패널에 퍼뜨린 뒤 diff 하면 같은 값이 4분기 반복되어 3번은 0, 1번만
            #   진짜 변화가 되고, 그 1번이 어느 분기에 떨어지는지가 접수일에 좌우된다.
            for src in ("related_sales_ratio", "related_purchase_ratio", "contingent_amt"):
                A[f"{src}_prev"] = ga[src].shift(1)
            keep = ["corp_code", "knowledge_date", "patent_up", "rnd_headcount_up", "gov_rnd",
                    "related_sales_ratio", "related_purchase_ratio", "contingent_amt",
                    "related_sales_ratio_prev", "related_purchase_ratio_prev",
                    "contingent_amt_prev",
                    "lawsuit_amt", "lawsuit_new", "audit_emphasis", "major_holder_pct"]
            d = _asof_attach(d, A[keep], sec, [c for c in keep if c not in
                                               ("corp_code", "knowledge_date")])

    # ③ 공시목록 기반: 단일판매·공급계약 체결 (분기 내 발생 여부)
    if dis is not None and len(dis):
        d = _attach_disclosure_events(d, dis, sec)
    else:
        d["supply_contract"] = np.nan

    have = [c for c in NONFIN_ITEMS if c in d.columns]
    n_ok = d[have].notna().sum(axis=1)
    d["dNONFIN"] = d[have].astype("float64").sum(axis=1, skipna=True).where(n_ok > 0)
    d["dNONFIN_n_items"] = n_ok

    LOG.table([[c, f"{int(d[c].notna().sum()):,}",
                f"{100*d[c].notna().mean():.1f}%",
                f"{float(pd.to_numeric(d[c], errors='coerce').mean()):.3f}"
                if d[c].notna().any() else "—"] for c in have],
              ["ΔNONFIN 항목", "관측", "커버리지", "발생률"], ["l", "r", "r", "r"],
              title="ΔNONFIN 구성 항목별 커버리지 (결측은 0 으로 채우지 않고 합계에서 제외)")
    LOG.ok(f"ΔNONFIN 산출 {int(d['dNONFIN'].notna().sum()):,}행 "
           f"(평균 가용 항목 {n_ok.mean():.2f}/{len(have)}개)")
    return d


def attach_major_holder(P: pd.DataFrame, H: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """구조화 조회 결과로 본문 추출값의 빈칸을 메운다(덮어쓰지 않는다)."""
    if H is None or H.empty:
        return P
    d = _asof_attach(P, H[["corp_code", "knowledge_date", "major_holder_pct_api"]],
                     sec, ["major_holder_pct_api"])
    before = float(col(d, "major_holder_pct").notna().mean())
    d["major_holder_pct"] = col(d, "major_holder_pct").where(
        col(d, "major_holder_pct").notna(), col(d, "major_holder_pct_api"))
    after = float(col(d, "major_holder_pct").notna().mean())
    LOG.ok(f"최대주주 지분율 커버리지 {100*before:.1f}% → {100*after:.1f}% "
           f"(본문 추출 + 구조화 엔드포인트 보강)")
    return d


def _asof_attach(base: pd.DataFrame, R: pd.DataFrame, sec: pd.DataFrame,
                 value_cols: Sequence[str]) -> pd.DataFrame:
    """corp_code 기준 as-of 결합. 결합키 결측 행은 반드시 보존한다(생존자편향 방지)."""
    d = base.copy()
    if "corp_code" not in d.columns:
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict()) \
            if "corp_code" in sec.columns else {}
        d["corp_code"] = d["code"].map(c2c)
    RR = R.copy()
    RR["knowledge_date"] = as_ts_series(RR["knowledge_date"])
    RR = (RR.dropna(subset=["corp_code", "knowledge_date"])
            .sort_values("knowledge_date", kind="stable"))
    RR["corp_code"] = RR["corp_code"].astype(str)
    RR = RR.drop_duplicates(["corp_code", "knowledge_date"], keep="last")
    d["_ord"] = np.arange(len(d))
    m = d["corp_code"].notna() & d["signal_date"].notna()
    if not m.any():
        for c in value_cols:
            if c not in d.columns:
                d[c] = np.nan
        return d.drop(columns=["_ord"])
    L = d[m].copy()
    L["corp_code"] = L["corp_code"].astype(str)
    L = L.sort_values("signal_date", kind="stable")
    M = pd.merge_asof(L, RR, left_on="signal_date", right_on="knowledge_date",
                      by="corp_code", direction="backward", suffixes=("", "_r"))
    add = [c for c in value_cols if c in M.columns]
    out = d.set_index("_ord")
    for c in add:
        if c in out.columns:
            out = out.drop(columns=[c])
    out = out.join(M.set_index("_ord")[add], how="left").sort_index().reset_index(drop=True)
    return out


def _attach_disclosure_events(d: pd.DataFrame, dis: pd.DataFrame,
                              sec: pd.DataFrame) -> pd.DataFrame:
    """리밸런싱 직전 1분기 구간에 발생한 공시 이벤트를 바이너리로 붙인다.

    ★ as-of 결합이 아니라 '구간 집계'다. 공급계약이나 CB 발행은 '가장 최근 값'이 아니라
      '지난 분기에 있었는가'가 의미 있는 정보이기 때문이다.
    ★ 구간의 오른쪽 끝은 signal_date(포함)이며, knowledge_date 기준이므로 §4 규약이 지켜진다.
    """
    D = dis.copy()
    D["knowledge_date"] = as_ts_series(D["knowledge_date"])
    D = D.dropna(subset=["knowledge_date"])
    # 종목코드 확보: stock_code 우선, 없으면 corp_code → code 매핑
    if "stock_code" in D.columns:
        D["code"] = D["stock_code"].map(to_code6)
    else:
        D["code"] = None
    if "corp_code" in D.columns and len(sec) and "corp_code" in sec.columns:
        cc2code = (sec.dropna(subset=["corp_code"]).drop_duplicates("corp_code")
                      .set_index(sec.dropna(subset=["corp_code"])
                                 .drop_duplicates("corp_code")["corp_code"].astype(str))["code"]
                      .to_dict())
        need = D["code"].isna()
        if need.any():
            D.loc[need, "code"] = D.loc[need, "corp_code"].astype(str).map(cc2code)
    D = D.dropna(subset=["code"])
    if D.empty:
        d["supply_contract"] = np.nan
        return d

    ev_cols = {"supply_contract": "supply_contract", "cb_issue": "cb_issue",
               "bw_issue": "bw_issue", "major_holder_chg": "major_holder_chg",
               "lawsuit_filed": "lawsuit_filed", "capital_impair": "capital_impair_dis"}
    # ★ 0.0 으로 초기화하면 '스윕을 안 했다'와 '스윕했는데 해당 없음'이 구별되지 않는다.
    #   전자는 근거 부재(배제하면 안 됨), 후자는 근거 있음(배제 판단 가능)이다.
    #   공시 원장이 실제로 덮은 구간에서만 0 을 채우고, 나머지는 결측으로 남긴다.
    _cov_lo = as_ts_series(D["knowledge_date"]).min()
    _cov_hi = as_ts_series(D["knowledge_date"]).max()
    _covered = (as_ts_series(d["signal_date"]) >= _cov_lo) & (as_ts_series(d["signal_date"]) <= _cov_hi)
    for c in ev_cols.values():
        d[c] = np.where(_covered.to_numpy(), 0.0, np.nan)
    if int((~_covered).sum()):
        LOG.info(f"공시 원장이 덮지 못한 {int((~_covered).sum()):,}행은 이벤트를 0 이 아니라 "
                 f"결측으로 둡니다 (근거 없이 '해당 없음'으로 처리하지 않습니다).")

    reb = sorted(pd.unique(as_ts_series(d["rebal"])))
    sig_by_rebal = (d.groupby("rebal", observed=True)["signal_date"].first().to_dict())
    prev_by_rebal: Dict[Any, pd.Timestamp] = {}
    for i, t in enumerate(reb):
        prev_by_rebal[t] = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))

    idx = {(c, as_ts(t)): None for c, t in zip(d["code"], d["rebal"])}
    for t in reb:
        lo = prev_by_rebal[t]
        hi = as_ts(sig_by_rebal.get(t))
        if hi is None:
            continue
        w = D[(D["knowledge_date"] > lo) & (D["knowledge_date"] <= hi)]
        if w.empty:
            continue
        rows_t = d["rebal"] == t
        for ev, cname in ev_cols.items():
            hits = set(w.loc[w["event"] == ev, "code"])
            if hits:
                d.loc[rows_t & d["code"].isin(hits), cname] = 1.0
    LOG.debug("공시 이벤트 구간 결합 완료 — " +
              ", ".join(f"{c}={int(d[c].sum()):,}" for c in ev_cols.values()))
    return d



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-Q4  애널리스트 텍스트 TONE — 결측 허용 오버레이 (§6.2)  ·  인과 순서 점검 (§6.4)       ║
# ║                                                                                          ║
# ║  TONE(report) = (긍정문장 − 부정문장) / 전체문장,  ΔTONE(f,q) = TONE(f,q) − TONE(f,q−1)    ║
# ║  분류기: TF-IDF + Naive Bayes / Logistic Regression.  ★ LLM 사용 금지.                     ║
# ║  라벨: 발간일 2일 CAR 의 부호.  확장윈도우: 시점 t 예측에는 t 이전 데이터로만 학습한 모델.  ║
# ║                                                                                          ║
# ║  ★ 이 모듈에서 조용히 틀리기 가장 쉬운 세 곳 ────────────────────────────────────────      ║
# ║   ① 면책조항·컴플라이언스 문구를 안 지우면 그게 증권사 지문이 되어, 분류기가 감성이 아니라 ║
# ║      '어느 증권사인가'를 학습한다. 지웠는지 믿지 말고 '증권사 분류기 정확도가 기저율로     ║
# ║      무너지는지' 를 직접 측정해서 출력한다. 그 검증이 이 설계의 전부다.                     ║
# ║   ② 확장윈도우를 '연 단위로 한 번 학습'까지는 다들 하는데, 라벨(2일 CAR)이 미래를 보므로   ║
# ║      학습 표본의 컷오프는 '발간일 < 경계' 가 아니라 '발간일 + 2거래일 < 경계' 여야 한다.    ║
# ║   ③ 리포트 없는 종목의 ΔTONE_resid = 0 을 z-score '이전'에 주입하면, 결측이 다수인 구간의  ║
# ║      평균이 0 쪽으로 끌려가 리포트 보유 종목의 z 가 통째로 왜곡된다. 반드시 관측치만으로   ║
# ║      z 를 만든 뒤 결측에 0 을 넣는다.                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_SK: Dict[str, Any] = {}


def ensure_sklearn() -> bool:
    """sklearn 지연 로드. 없으면 설치를 시도하고, 그래도 없으면 TONE 축만 비활성화한다
    (전략 전체는 중단하지 않는다 — §6.2 애널리스트 축은 결측 허용 오버레이다)."""
    if "ok" in _SK:
        return _SK["ok"]
    for attempt in (0, 1):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer      # type: ignore
            from sklearn.linear_model import LogisticRegression              # type: ignore
            from sklearn.naive_bayes import MultinomialNB                    # type: ignore
            from sklearn.model_selection import cross_val_score              # type: ignore
            _SK.update({"ok": True, "Tfidf": TfidfVectorizer, "LR": LogisticRegression,
                        "NB": MultinomialNB, "cvs": cross_val_score})
            return True
        except Exception:
            if attempt == 0:
                LOG.info("scikit-learn 설치 중 (TONE 분류기용, 1~2분)…")
                _pip_install(["scikit-learn"])
                try:
                    import importlib
                    importlib.invalidate_caches()
                except Exception:
                    pass
    _SK["ok"] = False
    LOG.warn("scikit-learn 을 쓸 수 없어 TONE 축을 비활성화합니다. §6.2 설계상 애널리스트 축은 "
             "'있으면 가점, 없으면 중립'이므로 ΔTONE_resid 는 전부 0(중립)이 되고 파이프라인은 "
             "정상 진행됩니다. Score2 는 사실상 ΔNONFIN 단독이 됩니다.")
    return False


# ── 정형 텍스트(면책조항/서명부) 제거 ───────────────────────────────────────────────────────
# ★ 패턴은 반드시 '문장 경계'에서 멈춰야 한다. [^\n]{0,400} 처럼 잡으면 PDF 추출 텍스트에
#   줄바꿈이 드물기 때문에 면책조항 한 줄이 뒤따르는 실제 분석 문장까지 통째로 지워버린다.
#   (리허설이 이 버그를 잡았다: 테스트 문장이 통째로 사라져 반환 길이가 0 이었다)
#   → 마침표/물음표/줄바꿈 앞까지만 소비한다.
_S = r"[^.。!?\n]{0,200}[.。!?]?"
_BOILER_PATTERNS = [
    r"본\s*자료는" + _S,
    r"동\s*자료는" + _S,
    r"당사는[^.。!?\n]{0,120}(?:책임|보증)" + _S,
    r"투자\s*판단의?\s*최종\s*책임" + _S,
    r"어떠한\s*경우에도" + _S,
    r"본\s*조사분석자료" + _S,
    r"compliance\s*notice" + _S,
    r"이\s*보고서는[^.。!?\n]{0,150}(?:작성|배포)" + _S,
    r"(?:기업|산업|시장)?\s*투자의견\s*분류" + _S,
    r"(?:Buy|Hold|Sell|매수|중립|매도)\s*[:：]\s*향후\s*\d+개월" + _S,
    r"자료\s*작성\s*일\s*현재" + _S,
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",           # 이메일(=애널리스트 지문)
    r"\(?\s*0\d{1,2}\s*\)?\s*[-\s.]?\d{3,4}[-\s.]?\d{4}",          # 전화번호
    r"[가-힣]{2,4}\s*(?:연구원|애널리스트|수석연구원|책임연구원|팀장|센터장)",
    r"(?:https?://|www\.)\S+",
    r"\d{4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}",                 # 날짜(발간일 지문화 방지)
]
_BOILER_RE = re.compile("|".join(_BOILER_PATTERNS), re.I)
# 증권사 사명 자체도 지운다 — 남겨두면 분류기가 감성 대신 사명을 학습한다.
_BROKER_TOKEN_RE = re.compile(
    "|".join(sorted({re.escape(n) for _p, n in BROKER_CANON}, key=len, reverse=True)) +
    r"|증권|리서치센터|리서치본부")


def strip_boilerplate(text: str) -> str:
    if not text:
        return ""
    t = _BOILER_RE.sub(" ", text)
    t = _BROKER_TOKEN_RE.sub(" ", t)
    t = re.sub(r"[^\w가-힣.!?%\s]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_KSENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=다)\s{1,}(?=[가-힣A-Z])|\n+")


def split_sentences_ko(text: str, max_sent: int = 400) -> List[str]:
    """한국어 문장 분리. 형태소 분석기 의존 없이 종결어미+구두점 휴리스틱으로 자른다.
    (konlpy/mecab 은 설치 실패율이 높고 Colab/윈도우에서 특히 취약해 의존하지 않는다)"""
    if not text:
        return []
    out = []
    for s in _KSENT_SPLIT.split(text):
        s = s.strip()
        if 8 <= len(s) <= 400:
            out.append(s)
        if len(out) >= max_sent:
            break
    return out


# ── 리포트 본문 테이블 ──────────────────────────────────────────────────────────────────────
TEXT_TRUNC = 4000          # 리포트당 저장 글자수 상한 (앞부분에 요약·투자포인트가 몰려 있다)
TRAIN_CAP_PER_YEAR = 8000  # 학습 코퍼스 상한(연). 전량을 다 쓰면 캐시가 수 GB 가 된다.


def build_report_text_table(rep: pd.DataFrame, need_codes: Optional[set] = None
                            ) -> pd.DataFrame:
    """리포트 PDF blob → 정제 본문 테이블. 한 번 만들면 재학습 때마다 재추출하지 않는다.

    수집 대상 = ① 학습 코퍼스(연도별 상한 표본, 전 종목 — §6.2 '학습 코퍼스는 국내 리포트 전량')
                 ② 채점 대상(U-200 합집합 종목의 전체 리포트)
    """
    cols = ["report_uid", "pub_date", "broker_id", "stock_code", "text", "n_sent", "is_irc"]
    if rep is None or rep.empty:
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("research_report_text", scope="shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(cached["report_uid"].astype(str))
        LOG.info(f"캐시에서 리포트 본문 {len(cached):,}건 재사용 (재추출하지 않습니다)")

    R = rep.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["report_uid", "pub_date"])
    R["_y"] = R["pub_date"].dt.year

    # ① 학습 표본 — 연도별 결정적 샘플링(uid 해시 순). 실행마다 같은 표본이 나온다.
    R["_h"] = R["report_uid"].astype(str).map(lambda u: int(u[:8], 16) if len(str(u)) >= 8 else 0)
    train_pick = (R.sort_values(["_y", "_h"], kind="stable")
                   .groupby("_y", observed=True).head(TRAIN_CAP_PER_YEAR))
    want = set(train_pick["report_uid"].astype(str))
    # ② 채점 대상
    if need_codes:
        want |= set(R.loc[R["stock_code"].isin(need_codes), "report_uid"].astype(str))
    todo = R[R["report_uid"].astype(str).isin(want - done)]

    rows: List[dict] = []
    if len(todo) and (fitz is not None or pdfplumber is not None):
        idx = VAULT.load_index("shared")
        blob_uid: Dict[str, str] = {}
        if len(idx) and "domain" in idx.columns:
            sub = idx[(idx["domain"].astype(str) == "research") &
                      (idx["subtype"].astype(str) == "report_pdf")]
            blob_uid = dict(zip(sub["key"].astype(str), sub["uid"].astype(str)))
        LOG.info(f"리포트 본문 추출 대상 {len(todo):,}건 "
                 f"(드라이브/로컬 blob 보유 {sum(1 for u in todo['report_uid'].astype(str) if u in blob_uid):,}건)")

        def _one(rec):
            uid, pdt, bid, code, title, irc = rec
            data = None
            bu = blob_uid.get(str(uid))
            if bu:
                data = VAULT.get_blob(bu, "shared")
            if not data:
                return None
            raw = pdf_text(data, max_pages=4)
            del data
            if not raw or len(raw) < 200:
                return None
            clean = strip_boilerplate(raw)[:TEXT_TRUNC]
            if len(clean) < 120:
                return None
            return {"report_uid": uid, "pub_date": pdt, "broker_id": bid, "stock_code": code,
                    "text": clean, "n_sent": len(split_sentences_ko(clean)), "is_irc": irc}

        irc_re = re.compile(IRC_TAG_PATTERN)
        jobs = list(zip(todo["report_uid"].astype(str), todo["pub_date"],
                        todo.get("broker_id", pd.Series([""] * len(todo))).astype(str),
                        todo["stock_code"],
                        todo.get("title", pd.Series([""] * len(todo))).astype(str),
                        (todo.get("broker_raw", pd.Series([""] * len(todo))).astype(str)
                         + " " + todo.get("title", pd.Series([""] * len(todo))).astype(str))
                        .map(lambda s: float(bool(irc_re.search(s))))))
        CHUNK = 4000
        for k0 in range(0, len(jobs), CHUNK):
            res = pmap_io(_one, jobs[k0:k0 + CHUNK], workers=min(N_WORKERS_IO, 8),
                          desc=f"리포트 본문 {k0//CHUNK+1}/{(len(jobs)-1)//CHUNK+1}")
            rows.extend([r for r in res if r])
            del res
            gc.collect()
    elif len(todo):
        LOG.warn("PDF 파서(pymupdf/pdfplumber)가 없어 리포트 본문을 추출할 수 없습니다 — "
                 "TONE 축은 전부 중립(0)이 됩니다.")

    frames = [cached] if cached is not None and len(cached) else []
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=cols)
    T = pd.concat(frames, ignore_index=True).drop_duplicates("report_uid", keep="last")
    T["pub_date"] = as_ts_series(T["pub_date"])
    for c in cols:
        if c not in T.columns:
            T[c] = np.nan
    if rows:
        VAULT.put_table("research_report_text", T[cols], scope="shared", domain="research",
                        source="pdf text + boilerplate strip",
                        extra={"trunc": TEXT_TRUNC, "note": "정제 본문 — 전 전략 공용"})
    LOG.ok(f"리포트 본문 테이블 {len(T):,}건 "
           f"(평균 {pd.to_numeric(T['n_sent'], errors='coerce').mean():.0f}문장 · "
           f"IR협의회 태깅 {int(pd.to_numeric(T['is_irc'], errors='coerce').fillna(0).sum()):,}건)")
    PIPE.io("OUT", "DRIVE", "research_report_text", T, source="pdf")
    return T[cols]


# ── 라벨: 발간일 2일 시장조정 CAR ───────────────────────────────────────────────────────────
def build_car_labels(T: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """라벨 = 발간 직후 2거래일 시장조정 누적수익의 부호.

    ★ 시장조정을 '당일 횡단면 중앙값'으로 한다. 지수 데이터를 따로 받지 않아도 되고,
      같은 날 정보만 쓰므로 미래누수가 원천적으로 없다. 지수를 쓰면 KOSPI/KOSDAQ 소속을
      PIT 로 알아야 하는데 그 자체가 또 하나의 누수 표면이 된다.
    """
    if T is None or T.empty or px_daily is None or not len(px_daily):
        return pd.DataFrame(columns=["report_uid", "car2", "label"])
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"], kind="stable")
    g = px.groupby("code", observed=True)["close"]
    px["r2"] = g.shift(-2) / px["close"] - 1.0          # 발간 시점 t 종가 → t+2 종가
    px["mkt"] = px.groupby("date", observed=True)["r2"].transform("median")
    px["car2"] = px["r2"] - px["mkt"]
    px["label_date"] = px["date"]

    L = T[["report_uid", "pub_date", "stock_code"]].dropna(subset=["stock_code"]).copy()
    L = L.rename(columns={"stock_code": "code"})
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"]).sort_values("pub_date", kind="stable")
    R = px[["code", "date", "car2"]].rename(columns={"date": "px_date"}) \
          .sort_values("px_date", kind="stable")
    M = pd.merge_asof(L, R, left_on="pub_date", right_on="px_date", by="code",
                      direction="forward", tolerance=pd.Timedelta(days=7))
    M = M.dropna(subset=["car2"])
    M["label"] = (M["car2"] > 0).astype(int)
    # 라벨이 실제로 확정되는 날 = 발간 매칭일 + 2거래일. 확장윈도우 컷오프는 이 날짜로 잰다.
    M["label_ready"] = next_trading_day_series(next_trading_day_series(M["px_date"]))
    LOG.ok(f"TONE 라벨 {len(M):,}건 (2일 시장조정 CAR · 양(+) 비율 {100*M['label'].mean():.1f}%)")
    return M[["report_uid", "car2", "label", "px_date", "label_ready"]]


# ── 정형문구 누출 검증 ──────────────────────────────────────────────────────────────────────
def verify_boilerplate_leak(T: pd.DataFrame, sample: int = 6000) -> dict:
    """정제 텍스트로 '증권사 맞히기' 분류기를 학습시켜 본다.

    정확도가 기저율(최빈 증권사 비율) 근처로 무너져야 정상이다. 높게 나오면 아직 증권사
    지문이 남아 있다는 뜻이고, 그 상태의 TONE 은 감성이 아니라 증권사 더미를 학습한 것이다.
    """
    if not ensure_sklearn() or T is None or len(T) < 500:
        return {}
    d = T.dropna(subset=["text", "broker_id"])
    d = d[d["broker_id"].astype(str).str.len() > 0]
    if len(d) < 500:
        return {}
    vc = d["broker_id"].value_counts()
    keep = vc[vc >= 40].index
    d = d[d["broker_id"].isin(keep)]
    if d["broker_id"].nunique() < 3 or len(d) < 500:
        return {}
    if len(d) > sample:
        d = d.sample(sample, random_state=SEED)
    base = float(d["broker_id"].value_counts(normalize=True).max())
    try:
        vec = _SK["Tfidf"](analyzer="char_wb", ngram_range=(2, 4), min_df=5,
                           max_features=60000, sublinear_tf=True)
        X = vec.fit_transform(d["text"].astype(str))
        y = d["broker_id"].astype(str).to_numpy()
        acc = float(np.mean(_SK["cvs"](_SK["LR"](max_iter=400, C=1.0), X, y, cv=3,
                                       scoring="accuracy")))
    except Exception as e:                                     # noqa
        LOG.warn(f"정형문구 누출 검증 실패({type(e).__name__}) — 검증 없이 진행하지만, "
                 f"TONE 결과 해석 시 증권사 지문 잔존 가능성을 감안하세요.")
        return {}
    verdict = ("✔ 기저율 수준 — 증권사 지문이 사실상 제거됨" if acc < base + 0.10 else
               "❗ 지문 잔존 — 분류기가 감성 대신 증권사를 학습할 위험")
    LOG.table([["증권사 수", f"{d['broker_id'].nunique()}"],
               ["표본", f"{len(d):,}"],
               ["기저율(최빈 증권사 비율)", f"{100*base:.1f}%"],
               ["증권사 분류 정확도(3-fold)", f"{100*acc:.1f}%"],
               ["판정", verdict]],
              ["항목", "값"], ["l", "r"],
              title="정형문구 제거 검증 (§6.2) — 이 검증이 없으면 TONE 은 증권사 더미일 수 있다")
    if acc >= base + 0.10:
        PIPE.note("WARN: 정형문구 누출 잔존 의심 — TONE 해석 주의")
    return {"base_rate": base, "broker_acc": acc, "n": int(len(d))}


# ── 확장윈도우 학습 + TONE 산출 ─────────────────────────────────────────────────────────────
def build_tone_scores(T: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """리포트별 TONE. 시점 t 의 리포트는 't 이전에 라벨이 확정된' 표본으로만 학습한 모델로 채점.

    반환: report_uid · pub_date · stock_code · tone · n_sent · model_epoch
    """
    out_cols = ["report_uid", "pub_date", "stock_code", "tone", "n_sent", "model_epoch"]
    if not ensure_sklearn() or T is None or T.empty or labels is None or labels.empty:
        return pd.DataFrame(columns=out_cols)
    D = T.merge(labels, on="report_uid", how="left")
    D["pub_date"] = as_ts_series(D["pub_date"])
    D = D.dropna(subset=["pub_date", "text"]).sort_values("pub_date", kind="stable")
    D["label_ready"] = as_ts_series(D["label_ready"])

    freq = "YS" if str(TONE_RETRAIN_FREQ).upper().startswith("Y") else "QS"
    edges = pd.date_range(D["pub_date"].min().normalize(), D["pub_date"].max() + pd.offsets.YearEnd(1),
                          freq=freq)
    edges = [as_ts(e) for e in edges]
    if not edges or edges[0] > D["pub_date"].min():
        edges = [as_ts(D["pub_date"].min())] + edges

    scored: List[pd.DataFrame] = []
    trained = 0
    for i, e in enumerate(edges):
        nxt = edges[i + 1] if i + 1 < len(edges) else (D["pub_date"].max() + pd.Timedelta(days=1))
        apply_mask = (D["pub_date"] >= e) & (D["pub_date"] < nxt)
        if not apply_mask.any():
            continue
        # ★ 학습 표본: '라벨이 e 이전에 확정된' 것만. 발간일 기준으로 자르면 경계 직전 리포트의
        #   2일 CAR 이 경계 이후를 보게 되어 그만큼 미래를 학습한다.
        tr = D[D["label_ready"].notna() & (D["label_ready"] < e) & D["label"].notna()]
        sub = D[apply_mask]
        if len(tr) < TONE_MIN_TRAIN_DOCS or tr["label"].nunique() < 2:
            LOG.debug(f"  {e:%Y-%m}: 학습표본 {len(tr):,}건 < 최소 {TONE_MIN_TRAIN_DOCS} — "
                      f"이 구간 TONE 은 결측(0 으로 채우지 않음)")
            continue
        try:
            vec = _SK["Tfidf"](analyzer="char_wb", ngram_range=(2, 4), min_df=3,
                               max_features=120000, sublinear_tf=True)
            Xtr = vec.fit_transform(tr["text"].astype(str))
            clf = _SK["LR"](max_iter=600, C=0.5)
            clf.fit(Xtr, tr["label"].astype(int).to_numpy())
        except Exception as ex:                                # noqa
            LOG.warn(f"  {e:%Y-%m}: TONE 모델 학습 실패({type(ex).__name__}) — 이 구간은 결측 처리")
            continue
        trained += 1

        # 문장 단위 채점 → TONE = (긍정문장 − 부정문장) / 전체문장
        recs = []
        sents_all: List[str] = []
        owner: List[int] = []
        for j, (uid, txt) in enumerate(zip(sub["report_uid"].astype(str), sub["text"].astype(str))):
            ss = split_sentences_ko(txt)
            if not ss:
                continue
            sents_all.extend(ss)
            owner.extend([j] * len(ss))
        if not sents_all:
            continue
        try:
            P = clf.predict(vec.transform(sents_all))
        except Exception:
            continue
        own = np.asarray(owner)
        pos = np.bincount(own[P == 1], minlength=len(sub))
        neg = np.bincount(own[P == 0], minlength=len(sub))
        tot = pos + neg
        tone = np.where(tot > 0, (pos - neg) / np.maximum(tot, 1), np.nan)
        recs = sub[["report_uid", "pub_date", "stock_code"]].copy()
        recs["tone"] = tone
        recs["n_sent"] = tot
        recs["model_epoch"] = e
        scored.append(recs)
        del sents_all, owner, P

    if not scored:
        LOG.warn("TONE 을 산출한 구간이 없습니다 (학습표본 부족). ΔTONE_resid 는 전부 중립(0)이 "
                 "되고 Score2 는 사실상 ΔNONFIN 단독이 됩니다 — §6.2 설계상 허용됩니다.")
        return pd.DataFrame(columns=out_cols)
    S = pd.concat(scored, ignore_index=True).dropna(subset=["tone"])
    LOG.ok(f"TONE 산출 {len(S):,}건 · 확장윈도우 모델 {trained}개 "
           f"(각 모델은 자기 구간 '이전에 라벨이 확정된' 표본으로만 학습)")
    VAULT.put_table("qvf_report_tone", S, scope="private", domain="research",
                    source="expanding-window TFIDF+LR")
    return S


def build_tone_panel(S: pd.DataFrame, G: pd.DataFrame, cal: pd.DataFrame,
                     exclude_irc: bool = False, T: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """리포트별 TONE → (code, rebal) 의 TONE / ΔTONE / 리포트 건수.

    구간 정의: 직전 리밸런싱 이후 ~ signal_date 까지 발간된 리포트의 TONE 평균.
    ΔTONE = 이번 구간 TONE − 직전 구간 TONE (직전 구간이 없으면 결측).
    """
    base = G[["code", "rebal", "signal_date"]].drop_duplicates()
    if S is None or S.empty:
        base["tone_q"] = np.nan
        base["dTONE"] = np.nan
        base["n_reports"] = 0.0
        return base
    R = S.copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna(subset=["pub_date", "stock_code", "tone"])
    if exclude_irc and T is not None and len(T):
        irc = set(T.loc[pd.to_numeric(T["is_irc"], errors="coerce").fillna(0) > 0,
                        "report_uid"].astype(str))
        n0 = len(R)
        R = R[~R["report_uid"].astype(str).isin(irc)]
        LOG.info(f"한국IR협의회 기업의뢰형 리포트 {n0-len(R):,}건 제외 (§8.4 민감도 분기)")
    R = R.rename(columns={"stock_code": "code"})
    # §4 — 발간일 + 1거래일부터 사용 가능
    R["usable"] = next_trading_day_series(R["pub_date"])

    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        lo = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = R[(R["usable"] > lo) & (R["usable"] <= hi)]
        if w.empty:
            continue
        a = w.groupby("code", observed=True).agg(tone_q=("tone", "mean"),
                                                 n_reports=("report_uid", "nunique")).reset_index()
        a["rebal"] = as_ts(t)
        parts.append(a)
    if not parts:
        base["tone_q"] = np.nan
        base["dTONE"] = np.nan
        base["n_reports"] = 0.0
        return base
    A = pd.concat(parts, ignore_index=True).sort_values(["code", "rebal"], kind="stable")
    # ΔTONE 은 '직전 분기'와만 짝지어야 한다. 중간 분기가 비면 결측이다.
    A["_i"] = A.groupby("code", observed=True).cumcount()
    A["_rank"] = A["rebal"].map({t: k for k, t in enumerate(reb)})
    prev_tone = A.groupby("code", observed=True)["tone_q"].shift(1)
    prev_rank = A.groupby("code", observed=True)["_rank"].shift(1)
    A["dTONE"] = (A["tone_q"] - prev_tone).where((A["_rank"] - prev_rank) == 1)
    out = base.merge(A[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                     on=["code", "rebal"], how="left")
    out["n_reports"] = pd.to_numeric(out["n_reports"], errors="coerce").fillna(0.0)
    cov = float((out["n_reports"] > 0).mean())
    LOG.ok(f"TONE 패널 {len(out):,}행 · 리포트 보유 {100*cov:.1f}% · "
           f"ΔTONE 관측 {int(out['dTONE'].notna().sum()):,}행 "
           f"({100*out['dTONE'].notna().mean():.1f}%)")
    return out


def orthogonalize_tone(P: pd.DataFrame) -> pd.DataFrame:
    """ΔTONE 을 목표주가 수정률·12-1 모멘텀·log(시총)·섹터 더미에 회귀한 잔차(§6.2).

    ★ 회귀는 반드시 '리밸런싱 시점별 횡단면'으로 적합한다. 전 기간을 풀링해서 적합하면
      계수가 미래 관측까지 보고 정해지므로 잔차에 미래정보가 섞인다.
    ★ EPS 컨센서스 수정률은 과거 시계열 복원이 불가능하다(국내 무료 경로 부재). 대신 확보
      가능한 목표주가 수정률을 쓰고, 이 대체 사실을 로그에 명시한다.
    """
    d = P.copy()
    d["dTONE_resid"] = np.nan
    if "dTONE" not in d.columns or d["dTONE"].notna().sum() < 30:
        LOG.warn("ΔTONE 관측이 부족해 직교화를 건너뜁니다 — ΔTONE_resid 는 전부 중립(0)이 됩니다.")
        d["dTONE_resid"] = np.nan
        return d

    feats = [c for c in ("tp_revision", "mom12_1", "log_cap") if c in d.columns]
    if "log_cap" not in d.columns:
        d["log_cap"] = np.log(pd.to_numeric(d["mktcap"], errors="coerce").where(lambda s: s > 0))
        feats = [c for c in ("tp_revision", "mom12_1", "log_cap") if c in d.columns]

    resid = pd.Series(np.nan, index=d.index, dtype="float64")
    n_fit = 0
    for t, g in d.groupby("rebal", observed=True):
        m = g["dTONE"].notna()
        if int(m.sum()) < 20:
            continue
        gg = g[m]
        y = pd.to_numeric(gg["dTONE"], errors="coerce").to_numpy(dtype="float64")
        Xparts = [np.ones((len(gg), 1))]
        for c in feats:
            v = pd.to_numeric(gg[c], errors="coerce")
            v = v.fillna(v.median())
            if v.std(ddof=0) > 0:
                Xparts.append(((v - v.mean()) / v.std(ddof=0)).to_numpy().reshape(-1, 1))
        # 섹터 더미 (관측 20건 이상인 섹터만; 나머지는 절편에 흡수 → 랭크 결손 방지)
        sec_s = gg["sector"].astype(str)
        big = sec_s.value_counts()
        big = big[big >= 20].index.tolist()[:40]
        for s in big[1:]:                       # 첫 섹터는 기준집단(더미 트랩 회피)
            Xparts.append((sec_s == s).to_numpy(dtype="float64").reshape(-1, 1))
        X = np.hstack(Xparts)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if ok.sum() < max(20, X.shape[1] + 5):
            continue
        try:
            beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
            r = y - X @ beta
        except Exception:
            continue
        resid.loc[gg.index[ok]] = r[ok]
        n_fit += 1
    d["dTONE_resid"] = resid.astype("float32")
    LOG.ok(f"ΔTONE 직교화 완료 — 횡단면 회귀 {n_fit}개 시점 · 잔차 {int(d['dTONE_resid'].notna().sum()):,}행 "
           f"(설명변수: {', '.join(feats)} + 섹터더미)")
    LOG.info("한계 명시(§10.1): EPS 컨센서스 수정률의 과거 시계열은 국내 무료 경로로 복원이 "
             "불가능해 직교화 설명변수에서 제외했습니다. 목표주가 수정률로 일부 대체했으나 "
             "동일하지 않으며, 그만큼 ΔTONE_resid 에 컨센서스 성분이 남아 있을 수 있습니다.")
    return d


def build_tp_revision(links: pd.DataFrame, G: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """목표주가 수정률 — 같은 애널리스트가 같은 종목에 직전에 제시한 목표주가 대비 변화율.
    애널리스트 원장이 없으면 만들 수 없는 지표다(원장이 장식이 아닌 이유)."""
    base = G[["code", "rebal", "signal_date"]].drop_duplicates()
    if links is None or links.empty or "target_price" not in links.columns:
        base["tp_revision"] = np.nan
        return base
    L = links.dropna(subset=["stock_code", "target_price"]).copy()
    L["pub_date"] = as_ts_series(L["pub_date"])
    L = L.dropna(subset=["pub_date"]).sort_values(["stock_code", "analyst_id", "pub_date"],
                                                  kind="stable")
    prev = L.groupby(["stock_code", "analyst_id"], observed=True)["target_price"].shift(1)
    L["rev"] = safe_div(pd.to_numeric(L["target_price"], errors="coerce"), prev) - 1.0
    L["usable"] = next_trading_day_series(L["pub_date"])
    L = L.rename(columns={"stock_code": "code"}).dropna(subset=["rev"])
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    sig = dict(zip(as_ts_series(cal["rebal"]), as_ts_series(cal["signal_date"])))
    parts = []
    for i, t in enumerate(reb):
        hi = sig.get(as_ts(t))
        lo = as_ts(reb[i - 1]) if i > 0 else (as_ts(t) - pd.DateOffset(months=3))
        w = L[(L["usable"] > lo) & (L["usable"] <= hi)]
        if w.empty:
            continue
        a = w.groupby("code", observed=True)["rev"].mean().reset_index(name="tp_revision")
        a["rebal"] = as_ts(t)
        parts.append(a)
    if not parts:
        base["tp_revision"] = np.nan
        return base
    A = pd.concat(parts, ignore_index=True)
    out = base.merge(A, on=["code", "rebal"], how="left")
    LOG.info(f"목표주가 수정률 {int(out['tp_revision'].notna().sum()):,}행 확보 "
             f"(애널리스트 원장 기반 — 동일 애널리스트의 직전 제시가 대비)")
    return out


# ── §6.4 인과 순서 점검 ─────────────────────────────────────────────────────────────────────
def check_causal_order(rep: pd.DataFrame, dis: pd.DataFrame, P: pd.DataFrame) -> dict:
    """리포트가 DART 공시를 '보고 쓴 것'이라면 ΔNONFIN 과 ΔTONE 은 독립 확증이 아니라
    같은 정보의 중복 카운팅이다. 선후관계 분포와 두 신호의 상관을 산출해 보고한다.
    ★ 자동으로 가중치를 조정하지 않는다(§6.4) — 보고만 한다."""
    LOG.banner("인과 순서 점검 (§6.4)",
               "리포트 발간이 DART 공시 뒤에 몰려 있다면 두 신호는 독립 확증이 아니다")
    out: Dict[str, Any] = {}
    if rep is None or rep.empty or dis is None or dis.empty:
        LOG.warn("리포트 또는 공시 원장이 비어 인과 순서 점검을 수행할 수 없습니다.")
        return out
    R = rep[["stock_code", "pub_date"]].dropna().copy()
    R["pub_date"] = as_ts_series(R["pub_date"])
    R = R.dropna().rename(columns={"stock_code": "code"}).sort_values("pub_date", kind="stable")
    D = dis.copy()
    if "code" not in D.columns:
        D["code"] = D.get("stock_code", pd.Series([None] * len(D))).map(to_code6)
    D = D.dropna(subset=["code"])
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D = D.dropna(subset=["rcept_dt"]).sort_values("rcept_dt", kind="stable")
    if R.empty or D.empty:
        LOG.warn("종목코드가 붙은 리포트/공시가 부족해 점검을 건너뜁니다.")
        return out

    M = pd.merge_asof(R, D[["code", "rcept_dt"]].rename(columns={"rcept_dt": "prev_disc"}),
                      left_on="pub_date", right_on="prev_disc", by="code",
                      direction="backward", tolerance=pd.Timedelta(days=90))
    lag = (M["pub_date"] - M["prev_disc"]).dt.days.dropna()
    if len(lag):
        bins = [(0, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 90)]
        rows = [[f"{a}~{b}일", f"{int(((lag>=a)&(lag<=b)).sum()):,}",
                 f"{100*float(((lag>=a)&(lag<=b)).mean()):.1f}%"] for a, b in bins]
        rows.append(["공시 없음(90일 내)", f"{int(M['prev_disc'].isna().sum()):,}",
                     f"{100*float(M['prev_disc'].isna().mean()):.1f}%"])
        LOG.table(rows, ["직전 공시 이후 경과", "리포트 수", "비중"], ["l", "r", "r"],
                  title="리포트 발간일 − 직전 DART 공시일 분포")
        within7 = float(((lag >= 0) & (lag <= 7)).mean())
        out["within7"] = within7
        out["median_lag"] = float(lag.median())
        LOG.info(f"직전 공시 후 7일 내 발간 비율 {100*within7:.1f}% · 중앙 시차 {lag.median():.0f}일")

    if P is not None and {"dNONFIN", "dTONE_resid"} <= set(P.columns):
        sub = P[["dNONFIN", "dTONE_resid"]].dropna()
        if len(sub) > 50:
            c = float(sub.corr(method="spearman").iloc[0, 1])
            out["corr"] = c
            LOG.table([["관측 쌍", f"{len(sub):,}"], ["Spearman 상관", f"{c:+.3f}"]],
                      ["항목", "값"], ["l", "r"],
                      title="ΔNONFIN ↔ ΔTONE_resid 상관 (중복 카운팅 여부)")
            if abs(c) > 0.30:
                LOG.warn(f"두 신호의 상관이 {c:+.3f} 로 높습니다. §6.3 의 2:1 결합 가중치는 "
                         f"'커버리지 비대칭'을 근거로 한 사전등록 값인데, 두 신호가 같은 정보를 "
                         f"세고 있다면 그 근거가 약해집니다. §6.4 지시대로 자동 조정하지 않고 "
                         f"재검토 대상으로만 보고합니다.")
            else:
                LOG.ok(f"상관 {c:+.3f} — 두 신호가 대체로 독립적인 정보를 담고 있습니다.")
        else:
            LOG.warn("두 신호가 동시에 관측된 행이 부족해 상관을 산출하지 못했습니다.")
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-Q2  2차 필터 — U-200 → 60~80종목 (§6.3)  ·  3차 필터 3-A 규칙판 (§7.2)                 ║
# ║                                                                                          ║
# ║  Score2 = 2.0·z(ΔNONFIN) + 1.0·z(ΔTONE_resid) − 배제                                      ║
# ║  배제플래그는 페널티가 아니라 '하드 제외'다. 가중치 2:1 은 커버리지 비대칭을 반영한          ║
# ║  사전등록 값이며 튜닝하지 않는다.                                                          ║
# ║                                                                                          ║
# ║  ★ 이 설계의 핵심은 '리포트 없는 종목이 살아남는가' 다(§6.2). 살아남지 못하면 U-200 으로   ║
# ║    유니버스를 넓힌 효과가 통째로 소멸한다. 그래서 코드가 매 실행 그 사실을 표로 검증한다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EXCL_FLAGS = ["x_related_up", "x_contingent", "x_lawsuit", "x_audit", "x_holder_chg", "x_cbbw"]
EXCL_LABEL = {
    "x_related_up": "특수관계자 비중 상승(상위20%)",
    "x_contingent": "우발부채·지급보증 자본대비 5%p↑",
    "x_lawsuit":    "신규 소송 (소송가액/자본 > 5%)",
    "x_audit":      "감사의견 강조사항·특기사항",
    "x_holder_chg": "최대주주 변경",
    "x_cbbw":       "전환사채·신주인수권부사채 발행",
}


def build_exclusion_flags(P: pd.DataFrame) -> pd.DataFrame:
    """§6.1 배제 플래그. 근거가 없으면(관측 결측) 배제하지 않는다 — fail-open 이 아니라
    '근거 없는 제외 금지' 원칙이다. 무엇을 근거 부족으로 넘겼는지는 표로 남긴다."""
    d = P.copy()
    eq = col(d, "equity")

    # ① 특수관계자 매입 또는 매출 비중 전분기 대비 상승 — 상승폭 상위 20%
    up_s = col(d, "related_sales_ratio") - col(d, "related_sales_ratio_prev")
    up_p = col(d, "related_purchase_ratio") - col(d, "related_purchase_ratio_prev")
    up = pd.concat([up_s, up_p], axis=1).max(axis=1, skipna=True)
    d["related_up"] = up
    thr = up.where(up > 0).groupby(d["rebal"], observed=True) \
            .transform(lambda s: s.quantile(1.0 - RELATED_PARTY_TOPQ))
    d["x_related_up"] = ((up > 0) & up.notna() & thr.notna() & (up >= thr)).astype(float)

    # ② 우발부채·지급보증 증가가 자기자본 대비 5%p 이상
    dc = col(d, "contingent_amt") - col(d, "contingent_amt_prev")
    d["contingent_pp"] = safe_div(dc, eq.where(eq > 0))
    d["x_contingent"] = (d["contingent_pp"] >= CONTINGENT_EQ_PP).fillna(False).astype(float)

    # ③ 신규 소송 제기 + 소송가액/자기자본 > 5%
    d["lawsuit_ratio"] = safe_div(col(d, "lawsuit_amt"), eq.where(eq > 0))
    new_suit = (col(d, "lawsuit_new").fillna(0) > 0) | (col(d, "lawsuit_filed").fillna(0) > 0)
    d["x_lawsuit"] = (new_suit & (d["lawsuit_ratio"] > LAWSUIT_EQ_2ND)).fillna(False).astype(float)

    # ④ 감사의견 특기사항 / 강조사항
    d["x_audit"] = (col(d, "audit_emphasis").fillna(0) > 0).astype(float)

    # ⑤ 최대주주 변경   ⑥ 전환사채·신주인수권부사채 발행
    d["x_holder_chg"] = (col(d, "major_holder_chg").fillna(0) > 0).astype(float)
    d["x_cbbw"] = ((col(d, "cb_issue").fillna(0) > 0) |
                   (col(d, "bw_issue").fillna(0) > 0)).astype(float)

    d["EXCLUDED"] = (d[EXCL_FLAGS].sum(axis=1) > 0).astype(int)

    evid = {
        "x_related_up": col(d, "related_sales_ratio").notna() | col(d, "related_purchase_ratio").notna(),
        "x_contingent": col(d, "contingent_amt").notna(),
        "x_lawsuit": col(d, "lawsuit_amt").notna() | col(d, "lawsuit_new").notna(),
        "x_audit": col(d, "audit_emphasis").notna(),
        "x_holder_chg": col(d, "major_holder_chg").notna(),
        "x_cbbw": col(d, "cb_issue").notna() | col(d, "bw_issue").notna(),
    }
    LOG.table([[EXCL_LABEL[f], f"{int(d[f].sum()):,}", f"{100*d[f].mean():.2f}%",
                f"{100*float(evid[f].mean()):.1f}%"] for f in EXCL_FLAGS],
              ["배제 플래그", "발동", "발동률", "근거 관측 보유율"], ["l", "r", "r", "r"],
              title="§6.1 배제 플래그 — 근거가 없으면 배제하지 않는다(근거 보유율을 함께 본다)")
    LOG.ok(f"배제 대상 {int(d['EXCLUDED'].sum()):,}행 / {len(d):,}행 ({100*d['EXCLUDED'].mean():.1f}%)")
    low = [EXCL_LABEL[f] for f in EXCL_FLAGS if float(evid[f].mean()) < 0.30]
    if low:
        LOG.warn("근거 관측 보유율이 30% 미만인 플래그: " + ", ".join(low) +
                 ". 해당 플래그는 사실상 일부 종목에만 작동하므로, 2층(지배구조 위험 배제) 효과가 "
                 "그만큼 약하게 측정됩니다. DART 본문 파싱률(§2.1)을 함께 보세요.")
    return d


def zscore_observed_then_neutral(P: pd.DataFrame, colname: str, mask: pd.Series) -> pd.Series:
    """관측치만으로 z 를 만든 뒤, 비관측치에 0(중립)을 채운다 (§6.2 결측 허용 설계).

    ★ 순서가 전부다. 0 을 먼저 채우고 z 를 만들면, 결측이 다수인 시점에서 평균이 0 으로
      끌려가 리포트를 가진 소수 종목의 z 가 통째로 부풀거나 눌린다. 즉 '리포트가 있다'는
      사실 자체가 신호가 되어 버린다 — 정확히 §6.2 가 막으려는 상황이다.
    """
    v = col(P, colname).where(mask)
    z = _cell_ladder_z(P, v)
    return z.fillna(0.0).astype("float32")


def apply_filter2(P: pd.DataFrame, variant: str, n: int = SECOND_N,
                  use_tone: bool = True, use_nonfin: bool = True,
                  use_exclusion: bool = True) -> pd.DataFrame:
    """U-200(변형별) → 상위 n 종목. 어블레이션(X2/X3)을 위해 구성요소를 켜고 끌 수 있다."""
    d = P.copy()
    inu = col(d, f"u200_{variant}").fillna(0).astype(bool) if f"u200_{variant}" in d.columns \
        else pd.Series(True, index=d.index)

    zN = pd.Series(0.0, index=d.index, dtype="float32")
    if use_nonfin:
        zN = zscore_observed_then_neutral(d, "dNONFIN", inu & col(d, "dNONFIN").notna())
    zT = pd.Series(0.0, index=d.index, dtype="float32")
    if use_tone:
        zT = zscore_observed_then_neutral(d, "dTONE_resid", inu & col(d, "dTONE_resid").notna())

    d[f"score2_{variant}"] = (SCORE2_W_NONFIN * zN + SCORE2_W_TONE * zT).astype("float32")
    excl = col(d, "EXCLUDED").fillna(0).astype(bool) if use_exclusion else \
        pd.Series(False, index=d.index)

    sel = pd.Series(False, index=d.index)
    for _t, g in d.groupby("rebal", observed=True):
        gg = g[inu.loc[g.index] & ~excl.loc[g.index]]
        if gg.empty:
            continue
        keys = [f"score2_{variant}", f"score1_{variant}", "code"]
        keys = [k for k in keys if k in gg.columns]
        asc = [False] * (len(keys) - 1) + [True]
        idx = gg.sort_values(keys, ascending=asc, kind="mergesort").head(min(n, len(gg))).index
        sel.loc[idx] = True
    d[f"f2_{variant}"] = sel
    return d


def verify_missing_tolerance(P: pd.DataFrame, variant: str) -> dict:
    """§6.2 결측 허용 설계가 실제로 지켜지는지 검증한다.
    리포트 없는 종목의 2차필터 통과율이 리포트 보유 종목과 비슷해야 정상이다."""
    d = P[P[f"u200_{variant}"].fillna(False).astype(bool)] if f"u200_{variant}" in P.columns else P
    if d.empty:
        return {}
    has_rep = pd.to_numeric(col(d, "n_reports"), errors="coerce").fillna(0) > 0
    passed = col(d, f"f2_{variant}").fillna(0).astype(bool)
    r_with = float(passed[has_rep].mean()) if int(has_rep.sum()) else float("nan")
    r_wo = float(passed[~has_rep].mean()) if int((~has_rep).sum()) else float("nan")
    LOG.table([["U-200 관측", f"{len(d):,}"],
               ["리포트 보유 종목", f"{int(has_rep.sum()):,} ({100*has_rep.mean():.1f}%)"],
               ["리포트 없는 종목", f"{int((~has_rep).sum()):,} ({100*(~has_rep).mean():.1f}%)"],
               ["2차필터 통과율 — 리포트 보유", f"{100*r_with:.1f}%" if np.isfinite(r_with) else "—"],
               ["2차필터 통과율 — 리포트 없음", f"{100*r_wo:.1f}%" if np.isfinite(r_wo) else "—"],
               ["최종 선정 중 리포트 없는 비중",
                f"{100*float((~has_rep)[passed].mean()):.1f}%" if int(passed.sum()) else "—"]],
              ["항목", "값"], ["l", "r"],
              title=f"[{variant}] §6.2 결측 허용 검증 — 리포트 없는 종목이 실제로 살아남는가")
    if np.isfinite(r_wo) and np.isfinite(r_with) and r_wo < r_with * 0.5:
        LOG.warn("리포트 없는 종목의 통과율이 보유 종목의 절반 미만입니다. ΔTONE_resid 가 "
                 "중립(0)이 아니라 사실상 벌점으로 작동하고 있을 수 있습니다 — "
                 "zscore_observed_then_neutral 의 순서(관측치 z 먼저, 결측 0 은 나중)를 확인하세요.")
        PIPE.note("WARN: 결측 허용 설계 위반 의심")
    else:
        LOG.ok("리포트 없는 종목이 정상적으로 살아남고 있습니다 — U-200 확장 효과가 보존됩니다.")
    return {"pass_with_report": r_with, "pass_without_report": r_wo}


# ── 3차 필터 3-A (§7.2) ─────────────────────────────────────────────────────────────────────
RULE_FLAGS = ["r_lawsuit", "r_related", "r_holder", "r_audit", "r_oploss", "r_impair"]
RULE_LABEL = {
    "r_lawsuit": f"소송가액/자기자본 > {RULE_LAWSUIT_EQ:.0%}",
    "r_related": f"특수관계자 매출비중 > {RULE_RELATED_SALES:.0%}",
    "r_holder":  f"최대주주 지분율 < {RULE_MAJOR_HOLDER:.0%}",
    "r_audit":   "감사보고서 강조사항 존재",
    "r_oploss":  f"{RULE_OP_LOSS_QUARTERS}개 분기 연속 영업적자",
    "r_impair":  f"자본잠식률 > {RULE_IMPAIRMENT:.0%}",
}


def apply_filter3a(P: pd.DataFrame) -> pd.DataFrame:
    """명문화된 체크리스트만 사용한다. 임계값은 사전등록 후 고정이며 튜닝하지 않는다.
    ★ 근거가 결측이면 제외하지 않는다(모른다는 이유로 버리면 그게 곧 선택편향)."""
    d = P.copy()
    eq = col(d, "equity")
    cap_stock = col(d, "capital_stock")

    d["r_lawsuit"] = (col(d, "lawsuit_ratio") > RULE_LAWSUIT_EQ).fillna(False).astype(float)
    d["r_related"] = (col(d, "related_sales_ratio") > RULE_RELATED_SALES).fillna(False).astype(float)
    d["r_holder"] = ((col(d, "major_holder_pct").notna()) &
                     (col(d, "major_holder_pct") < RULE_MAJOR_HOLDER)).astype(float)
    d["r_audit"] = (col(d, "audit_emphasis").fillna(0) > 0).astype(float)
    d["r_oploss"] = (col(d, "op_loss_4q").fillna(0) > 0).astype(float)
    # 자본잠식률 = (자본금 − 자기자본) / 자본금
    d["impair_ratio"] = safe_div(cap_stock - eq, cap_stock.where(cap_stock > 0))
    d["r_impair"] = (d["impair_ratio"] > RULE_IMPAIRMENT).fillna(False).astype(float)

    d["RULE3A_BLOCK"] = (d[RULE_FLAGS].sum(axis=1) > 0).astype(int)
    evid = {
        "r_lawsuit": col(d, "lawsuit_ratio").notna(),
        "r_related": col(d, "related_sales_ratio").notna(),
        "r_holder": col(d, "major_holder_pct").notna(),
        "r_audit": col(d, "audit_emphasis").notna(),
        "r_oploss": col(d, "op_loss_4q").notna(),
        "r_impair": d["impair_ratio"].notna(),
    }
    LOG.table([[RULE_LABEL[f], f"{int(d[f].sum()):,}", f"{100*d[f].mean():.2f}%",
                f"{100*float(evid[f].mean()):.1f}%"] for f in RULE_FLAGS],
              ["3-A 규칙", "발동", "발동률", "근거 관측 보유율"], ["l", "r", "r", "r"],
              title="3-A 규칙판 (§7.2) — 백테스트는 여기까지만 포함한다(3-B 재량은 소급 금지)")
    LOG.ok(f"3-A 차단 {int(d['RULE3A_BLOCK'].sum()):,}행 ({100*d['RULE3A_BLOCK'].mean():.1f}%)")
    return d


def build_final_selection(P: pd.DataFrame, variant: str, n_final: int = FINAL_N,
                          use_rule3a: bool = True, stage: str = "full") -> pd.Series:
    """최종 편입 종목 플래그.

    stage: "full"(1→2→3A) | "x1"(1차만) | "x4"(1→2, 3A 없음)
    """
    d = P
    if stage == "x1":
        pool = col(d, f"u200_{variant}").fillna(0).astype(bool)
        rank_col = f"score1_{variant}"
    else:
        pool = col(d, f"f2_{variant}").fillna(0).astype(bool)
        rank_col = f"score2_{variant}"
    if use_rule3a and stage != "x1":
        pool = pool & (col(d, "RULE3A_BLOCK").fillna(0) == 0)
    elif use_rule3a and stage == "x1":
        pool = pool & (col(d, "RULE3A_BLOCK").fillna(0) == 0)

    sel = pd.Series(False, index=d.index)
    for _t, g in d.groupby("rebal", observed=True):
        gg = g[pool.loc[g.index]]
        if gg.empty:
            continue
        keys = [c for c in (rank_col, f"score1_{variant}", "code") if c in gg.columns]
        asc = [False] * (len(keys) - 1) + [True]
        k = int(min(max(FINAL_N_MIN, min(n_final, FINAL_N_MAX)), len(gg)))
        sel.loc[gg.sort_values(keys, ascending=asc, kind="mergesort").head(k).index] = True
    return sel



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  분기 리밸런싱 백테스트 엔진 + 비용 모델 (§7.4, §8.1)                                  ║
# ║                                                                                          ║
# ║  · 체결 = 리밸런싱일 이후 첫 거래일 '시가'. 신호는 그 전 거래일 종가까지만(§4).             ║
# ║  · 상장폐지: 정리매매 체결가가 있으면 반영, 없으면 −100%. 누락 처리 금지(§3.4).             ║
# ║  · 비용: 증권거래세(연도별 이력) + 실측 스프레드(Corwin-Schultz) + 수수료 + 제곱근 충격.     ║
# ║    비용 전/후를 반드시 병기한다. 비용 전만 보고하는 것은 금지(§8.1).                        ║
# ║  · 연율화 계수는 분기이므로 √4 다. √12 를 쓰면 변동성이 1.7배 과대계상된다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율(매도 시, 농특세 포함 총부담). 10년간 여섯 번 바뀌었다 —
# 한 개의 평균율로 뭉개면 초기 구간 비용이 과소, 말기 구간이 과대계상된다.
QVF_TAX_SCHEDULE = [
    ("2016-01-01", 0.0030),
    ("2019-06-03", 0.0025),
    ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020),
    ("2024-01-01", 0.0018),
    ("2025-01-01", 0.0015),
]
Q_PER_YEAR = 4.0

# 상장폐지 맵을 전역으로 한 번만 세팅한다. 실험·민감도에서 백테스트를 수십 번 부르는데
# 호출부마다 인자로 넘기게 하면 한 군데만 빠뜨려도 그 실험만 조용히 생존자편향을 갖는다.
QVF_DELIST_MAP: Dict[str, Any] = {}


def set_delist_map(m: Optional[Dict[str, Any]]):
    globals()["QVF_DELIST_MAP"] = {str(k): as_ts(v) for k, v in dict(m or {}).items()
                                   if pd.notna(as_ts(v))}
    LOG.debug(f"상장폐지 맵 등록: {len(QVF_DELIST_MAP):,}종목")


def qvf_sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = QVF_TAX_SCHEDULE[0][1]
    for d, r in QVF_TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return float(rate)


def build_exec_prices(cal: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """(code, rebal) → 체결가(체결일 시가) · 체결일. 시가가 없으면 같은 날 종가로 폴백한다."""
    px = px_daily[["code", "date", "open", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date"])
    px["px_exec"] = pd.to_numeric(px["open"], errors="coerce")
    px["px_exec"] = px["px_exec"].where(px["px_exec"] > 0,
                                        pd.to_numeric(px["close"], errors="coerce"))
    px = px.dropna(subset=["px_exec"]).sort_values("date", kind="stable")

    codes = sorted(px["code"].unique())
    L = (cal[["rebal", "exec_date"]].assign(_k=1)
         .merge(pd.DataFrame({"code": codes, "_k": 1}), on="_k").drop(columns="_k"))
    L = L.sort_values("exec_date", kind="stable")
    R = px[["code", "date", "px_exec"]].rename(columns={"date": "px_date"})
    # ★ forward 방향이다. 체결일에 거래가 없으면 '그 이후 첫 거래일'에 체결된 것으로 본다.
    #   backward 로 붙이면 체결일 이전 가격으로 사게 되어 미래를 모르고도 유리해진다.
    M = pd.merge_asof(L, R, left_on="exec_date", right_on="px_date", by="code",
                      direction="forward", tolerance=pd.Timedelta(days=15))
    out = M.dropna(subset=["px_exec"])[["code", "rebal", "exec_date", "px_date", "px_exec"]]
    out = out.rename(columns={"px_date": "fill_date"})
    PIPE.io("OUT", "MEM", "exec_prices", out)
    return downcast_q(out)


def build_forward_returns(execp: pd.DataFrame, cal: pd.DataFrame,
                          delist: Dict[str, pd.Timestamp],
                          px_daily: pd.DataFrame) -> pd.DataFrame:
    """(code, rebal) → 다음 리밸런싱까지의 보유수익률.

    ★ 분기가 건너뛰어졌을 때 shift(-1) 이 두 분기 뒤 가격을 끌어와 '한 분기 수익'으로
      둔갑시키는 사고를 인접성 검사로 막는다.
    ★ 보유기간 중 상장폐지: 정리매매 체결가가 있으면 그 가격, 없으면 −100%.
    """
    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    rank = {t: i for i, t in enumerate(reb)}
    E = execp.copy()
    # ★ code 가 category 이면 .map() 결과도 category 가 되고, 그 값이 날짜일 때
    #   `ld >= dl - 15일` 비교가 TypeError 로 죽는다. 그 코드가 하필 '보유 중 상장폐지'
    #   처리라 생존자편향 방어가 통째로 무너진다(계약 Q3 가 이 경로를 잡는다).
    E["code"] = E["code"].astype(str)
    E["rebal"] = as_ts_series(E["rebal"])
    E["_r"] = E["rebal"].map(rank)
    E = E.dropna(subset=["_r"]).sort_values(["code", "_r"], kind="stable")
    g = E.groupby("code", observed=True)
    E["px_next"] = g["px_exec"].shift(-1)
    E["r_next"] = g["_r"].shift(-1)
    adjacent = (E["r_next"] - E["_r"]) == 1
    E["fwd_ret"] = (E["px_next"] / E["px_exec"] - 1.0).where(adjacent)
    E["exit_kind"] = np.where(E["fwd_ret"].notna(), "normal", "missing")

    # 마지막 리밸런싱은 다음 시점이 없으므로 수익률이 없는 것이 정상이다.
    last_r = max(rank.values()) if rank else -1
    E.loc[E["_r"] == last_r, "exit_kind"] = "terminal"

    # ── 상장폐지 처리 ──────────────────────────────────────────────────────────────────
    px = px_daily[["code", "date", "close"]].copy()
    px["code"] = px["code"].astype(str)
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"])
    last_px = (px.sort_values("date").groupby("code", observed=True)
                 .agg(last_date=("date", "max"), last_close=("close", "last")))
    # ★ 보유구간의 오른쪽 끝은 '다음 체결일'이다. 다음 명목일로 잡으면 그 사이 1~3일의
    #   이음매에서 폐지된 종목이 창 밖으로 새어 −100% 대신 0% 가 된다(분기마다 반복).
    _exec_of = {as_ts(r.rebal): as_ts(r.exec_date) for r in cal.itertuples(index=False)}
    nxt_rebal = {t: (_exec_of.get(reb[i + 1]) if i + 1 < len(reb) else None)
                 for i, t in enumerate(reb)}

    n_liq = n_zero = 0
    if delist:
        dl = {str(k): as_ts(v) for k, v in dict(delist).items()}
        E["_dl"] = as_ts_series(E["code"].map(dl))
        E["_nxt"] = as_ts_series(E["rebal"].map(nxt_rebal))
        in_window = (E["_dl"].notna() & E["_nxt"].notna() &
                     (E["_dl"] > E["exec_date"]) & (E["_dl"] <= E["_nxt"]))
        if in_window.any():
            ld = as_ts_series(E.loc[in_window, "code"].map(last_px["last_date"]))
            lc = pd.to_numeric(E.loc[in_window, "code"].map(last_px["last_close"]),
                               errors="coerce")
            # ── 정리매매가로 인정하는 조건 (§3.4) ──────────────────────────────────────
            #  ① 가격 시계열이 폐지 시점까지 실제로 닿아 있을 것 (닿지 않으면 그냥 데이터가
            #     끊긴 것이지 정리매매를 관측한 게 아니다)
            #  ② 그 가격이 진입가 대비 '손실'일 것.
            #  ★ ②가 없으면 치명적이다: 소스가 폐지 직전에 종목을 드롭하면 마지막 정상가가
            #    청산가로 둔갑해 '상장폐지 = 0% 손실'이 된다. 그게 정확히 생존자편향의
            #    재유입이며, 계약 Q3 가 이 경로를 잡아낸다. 애매하면 규정대로 −100% 로
            #    보수적으로 처리한다(성과를 과소평가하는 방향 = 편향 통제상 옳은 방향).
            entry = E.loc[in_window, "px_exec"]
            reach = ld.notna() & (ld >= E.loc[in_window, "_dl"] - pd.Timedelta(days=7))
            liq_ret = lc / entry - 1.0
            captured = reach & liq_ret.notna() & (liq_ret < 0)
            E.loc[in_window, "fwd_ret"] = liq_ret.where(captured, -1.0)
            E.loc[in_window, "exit_kind"] = np.where(captured.to_numpy(),
                                                     "liquidation", "delist_-100%")
            n_liq = int(captured.sum())
            n_zero = int((~captured).sum())
        E = E.drop(columns=[c for c in ("_dl", "_nxt") if c in E.columns])

    kinds = Counter(E["exit_kind"].astype(str))
    LOG.table([[k, f"{v:,}"] for k, v in kinds.most_common()],
              ["보유 종료 유형", "건수"], ["l", "r"],
              title="보유기간 종료 유형 — 상장폐지가 누락되면 그대로 생존자편향이 된다")
    if n_liq or n_zero:
        LOG.info(f"보유 중 상장폐지 {n_liq + n_zero:,}건 — 정리매매가 반영 {n_liq:,}건 / "
                 f"가격 부재로 −100% 처리 {n_zero:,}건 (§3.4 규정대로 누락 처리하지 않음)")
    return E[["code", "rebal", "exec_date", "px_exec", "fwd_ret", "exit_kind"]]


# ── 가중 ────────────────────────────────────────────────────────────────────────────────────
def compute_weights(sub: pd.DataFrame, scheme: str = "equal") -> pd.Series:
    n = len(sub)
    if n == 0:
        return pd.Series(dtype="float64")
    if scheme == "invvol":
        v = pd.to_numeric(sub.get("vol_d"), errors="coerce")
        # ★ 변동성 결측 종목을 떨어뜨리면 '변동성을 못 구한 종목' = 대개 신규·저유동 종목이
        #   조용히 빠져 선택편향이 된다. 횡단면 중앙값으로 대체하고 개수를 로그로 남긴다.
        med = float(v.median()) if v.notna().any() else np.nan
        v = v.where(v > 0)
        v = v.fillna(med if np.isfinite(med) and med > 0 else 0.02)
        w = 1.0 / v
        w = w / w.sum() if float(w.sum()) > 0 else pd.Series(1.0 / n, index=sub.index)
        return w
    return pd.Series(1.0 / n, index=sub.index)


def run_qbacktest(P: pd.DataFrame, cal: pd.DataFrame, sel_col: str, fwd: pd.DataFrame,
                  scheme: str = "equal", apply_costs: bool = True,
                  label: str = "QVF", delist: Optional[Dict[str, pd.Timestamp]] = None) -> dict:
    """분기 리밸런싱 롱온리 백테스트. 비용 전/후를 동시에 산출한다."""
    need = ["code", "rebal", sel_col]
    d = P[[c for c in P.columns if c in set(need) | {"adtv", "cs_spread", "vol_d", "market",
                                                     "mktcap", "score1_V", "score1_VQ",
                                                     "score1_VQF"}]].copy()
    d = d[d[sel_col].fillna(False).astype(bool)]
    F = fwd.set_index(["code", "rebal"])["fwd_ret"] if len(fwd) else pd.Series(dtype="float64")

    reb = sorted(pd.unique(as_ts_series(cal["rebal"])))
    # ★ 보유구간은 [체결일, 다음 체결일) 이지 [명목일, 다음 명목일) 이 아니다.
    #   3/1 은 삼일절이라 결코 거래일이 아니고 6/1·12/1 도 주말에 자주 걸린다. 두 구간의
    #   차이(1~3일의 이음매)에서 폐지된 종목은 '창 밖'으로 판정되어 −100% 대신 0% 가 된다.
    #   즉 분기마다 며칠씩 생존자편향이 새는 뒷문이 열려 있었다.
    exec_of = {as_ts(r.rebal): as_ts(r.exec_date) for r in cal.itertuples(index=False)}
    exec_next = {t: (exec_of.get(reb[i + 1]) if i + 1 < len(reb) else None)
                 for i, t in enumerate(reb)}
    dlmap = ({str(k): as_ts(v) for k, v in dict(delist).items()} if delist
             else dict(QVF_DELIST_MAP))
    prev_w: Dict[str, float] = {}
    rows, holds = [], []
    n_missing, n_forced_delist, n_empty_q = 0, 0, 0
    for t in reb:
        sub = d[d["rebal"] == t].copy()
        if sub.empty:
            # ★ 3-A 통과 종목이 0 인 분기는 설계상 발생할 수 있는 정상 결과다(사전등록).
            #   그런데 예전 코드는 회전율만 기록하고 비용 0, 수익 0 으로 넘겼다 — 전량 청산을
            #   공짜로 처리하고, 그 분기 보유분의 실제 수익을 통째로 증발시킨 것이다.
            turn0 = float(sum(abs(v) for v in prev_w.values()))
            g0 = 0.0
            nx0 = exec_next.get(t)
            te0 = exec_of.get(t, t)
            for c, w in prev_w.items():
                fr = F.get((c, t), np.nan) if len(F) else np.nan
                fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan
                if not np.isfinite(fr):
                    dl = dlmap.get(str(c))
                    fr = -1.0 if (dl is not None and nx0 is not None and te0 < dl <= as_ts(nx0)) else 0.0
                g0 += w * fr
            c0 = 0.0
            if apply_costs and prev_w:
                tax0 = qvf_sell_tax(te0)
                sp0 = float(np.clip(SLIPPAGE_FLOOR_BPS / 1e4,
                                    SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                for w in prev_w.values():
                    c0 += abs(w) * (COMMISSION_BPS / 1e4 + sp0 / 2.0 + tax0)
            n_empty_q += 1
            rows.append({"rebal": t, "ret": g0 - c0, "ret_gross": g0, "n": 0,
                         "turnover": turn0, "cost": c0})
            prev_w = {}
            continue
        sub["w"] = compute_weights(sub, scheme)
        w_new = dict(zip(sub["code"].astype(str), sub["w"].astype(float)))

        turn = sum(abs(w_new.get(c, 0.0) - prev_w.get(c, 0.0))
                   for c in set(w_new) | set(prev_w))
        cost = 0.0
        if apply_costs:
            # ★ sub.get(없는컬럼) 은 None 을 돌려주고 pd.to_numeric(None) 은 스칼라 nan 이라
            #   zip 이 "float is not iterable" 로 죽는다. 축소된 강건성 실행에서 실제로 도달한다.
            spread = dict(zip(sub["code"].astype(str),
                              pd.to_numeric(col(sub, "cs_spread"), errors="coerce")))
            advm = dict(zip(sub["code"].astype(str),
                            pd.to_numeric(col(sub, "adtv"), errors="coerce")))
            # ★ 세율 구간 경계가 2019-06-03 인데 2019-06-01 은 토요일이라 그 분기 체결일이
            #   정확히 2019-06-03 이다. 명목일로 조회하면 그 한 분기만 구세율(0.30%)이 적용돼
            #   매도 레그 전체에 20bp 를 과다계상한다. 체결일 기준으로 조회한다.
            tax = qvf_sell_tax(exec_of.get(t, t))
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0.0) - prev_w.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                sp = spread.get(c, np.nan)
                sp = float(sp) if sp is not None and np.isfinite(sp) else SLIPPAGE_FLOOR_BPS / 1e4
                sp = float(np.clip(sp, SLIPPAGE_FLOOR_BPS / 1e4, SLIPPAGE_CAP_BPS / 1e4))
                adv = advm.get(c, np.nan)
                adv = float(adv) if adv is not None and np.isfinite(adv) and adv > 0 else 0.0
                notional = abs(dw) * ACCOUNT_KRW
                part = min(1.0, notional / adv) if adv > 0 else 1.0
                impact = IMPACT_K * math.sqrt(part)
                one_way = COMMISSION_BPS / 1e4 + sp / 2.0 + impact
                cost += abs(dw) * one_way + (abs(dw) * tax if dw < 0 else 0.0)

        gross = 0.0
        nx = exec_next.get(t)
        t_exec = exec_of.get(t, t)
        for c, w in w_new.items():
            fr = F.get((c, t), np.nan) if len(F) else np.nan
            fr = float(fr) if fr is not None and np.isfinite(fr) else np.nan
            if not np.isfinite(fr):
                # ★ 체결가가 없어 수익률을 못 만든 종목을 일괄 0% 로 두면, 폐지 직전에
                #   소스에서 사라지는 종목이 전부 '무손실'이 된다 — 생존자편향의 뒷문이다.
                #   보유구간 안에서 폐지가 확인되면 §3.4 규정대로 −100% 를 적용한다.
                dl = dlmap.get(str(c))
                if dl is not None and nx is not None and t_exec < dl <= as_ts(nx):
                    fr = -1.0
                    n_forced_delist += 1
                else:
                    fr = 0.0                  # 마지막 분기 등 — 임의 가정 금지
                    n_missing += 1
            gross += w * fr
            holds.append({"rebal": t, "code": c, "weight": w, "ret": fr})
        rows.append({"rebal": t, "ret": gross - cost, "ret_gross": gross, "n": len(w_new),
                     "turnover": turn, "cost": cost})
        prev_w = w_new

    R = pd.DataFrame(rows)
    if len(R):
        R["equity"] = (1.0 + R["ret"].fillna(0)).cumprod()
        R["equity_gross"] = (1.0 + R["ret_gross"].fillna(0)).cumprod()
    if n_forced_delist or n_missing or n_empty_q:
        LOG.info(f"[{label}] 체결가 결측 보정 — 보유구간 내 폐지 확인 {n_forced_delist:,}건은 "
                 f"−100% · 그 외 {n_missing:,}건은 0%(마지막 분기 등) · "
                 f"선정 0종목 분기 {n_empty_q:,}회(청산비용 부과·보유수익 반영)")
        if n_missing > max(20, 0.02 * len(holds)):
            LOG.warn(f"0% 로 처리된 보유가 {n_missing:,}건으로 많습니다. 폐지·거래정지가 "
                     f"'무손실'로 새고 있을 수 있습니다 — 위 '보유 종료 유형' 표와 함께 보세요.")
    return {"returns": R, "holdings": pd.DataFrame(holds), "label": label, "scheme": scheme,
            "n_forced_delist": n_forced_delist, "n_missing": n_missing}


# ── 성과 지표 ───────────────────────────────────────────────────────────────────────────────
def qperf_stats(R: pd.DataFrame, ret_col: str = "ret", rf: float = 0.0) -> dict:
    if R is None or not len(R):
        return {}
    r = pd.to_numeric(R[ret_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / Q_PER_YEAR
    cagr = eq[-1] ** (1.0 / years) - 1.0 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(Q_PER_YEAR) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(Q_PER_YEAR) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if n else np.nan
    mx, cur = 0, 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        mx = max(mx, cur)
    mu, tstat = hac_tstat(r)
    return {
        "분기수": n, "누적수익": float(eq[-1] - 1.0), "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr - rf) / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr - rf) / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd and mdd < 0 else np.nan,
        "승률": float((r > 0).mean()), "분기평균": float(r.mean()),
        "t통계량(HAC)": tstat, "최장언더워터(분기)": int(mx),
        "평균종목수": float(pd.to_numeric(R["n"], errors="coerce").mean()) if "n" in R else np.nan,
        "분기평균회전율": float(pd.to_numeric(R["turnover"], errors="coerce").mean())
        if "turnover" in R else np.nan,
        "분기평균비용": float(pd.to_numeric(R["cost"], errors="coerce").mean())
        if "cost" in R else np.nan,
    }


def rank_ic(P: pd.DataFrame, score_col: str, fwd: pd.DataFrame,
            pool_col: Optional[str] = None) -> Tuple[float, float, int]:
    """스코어와 다음 분기 수익률의 스피어만 순위상관. (평균 IC, IC-IR, 시점수)"""
    if score_col not in P.columns or fwd is None or not len(fwd):
        return (np.nan, np.nan, 0)
    d = P[["code", "rebal", score_col] + ([pool_col] if pool_col and pool_col in P.columns else [])]
    if pool_col and pool_col in P.columns:
        d = d[d[pool_col].fillna(False).astype(bool)]
    d = d.merge(fwd[["code", "rebal", "fwd_ret"]], on=["code", "rebal"], how="left")
    d = d.dropna(subset=[score_col, "fwd_ret"])
    ics = []
    for _t, g in d.groupby("rebal", observed=True):
        if len(g) < 10:
            continue
        c = g[score_col].rank().corr(g["fwd_ret"].rank())
        if np.isfinite(c):
            ics.append(float(c))
    if not ics:
        return (np.nan, np.nan, 0)
    m = float(np.mean(ics))
    s = float(np.std(ics, ddof=1)) if len(ics) > 1 else np.nan
    return (m, (m / s) if s and np.isfinite(s) and s > 0 else np.nan, len(ics))


def qvf_benchmarks(cal: pd.DataFrame, px_daily: pd.DataFrame) -> Dict[str, pd.Series]:
    """분기 벤치마크. 지수를 못 받으면 유니버스 동일가중 수익률로 대체하고 그 사실을 명시한다."""
    out: Dict[str, pd.Series] = {}
    reb = list(as_ts_series(cal["rebal"]))
    ex = list(as_ts_series(cal["exec_date"]))
    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        d = None
        if fdr is not None:
            try:
                d = fdr.DataReader(sym, (min(ex) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                   (max(ex) + pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
            except Exception:
                d = None
        if d is None or not len(d):
            continue
        d = d.reset_index()
        d.columns = [str(c).lower() for c in d.columns]
        d["date"] = as_ts_series(d[d.columns[0]])
        cl = d[["date", "close"]].dropna().sort_values("date", kind="stable")
        L = pd.DataFrame({"exec_date": ex}).sort_values("exec_date", kind="stable")
        M = pd.merge_asof(L, cl.rename(columns={"date": "px_date"}),
                          left_on="exec_date", right_on="px_date", direction="forward",
                          tolerance=pd.Timedelta(days=15))
        s = pd.Series(M["close"].to_numpy(), index=pd.Index(reb, name="rebal")).pct_change(fill_method=None).shift(-1)
        out[name] = s
    if not out:
        LOG.warn("지수 벤치마크를 받지 못했습니다 — 벤치마크 비교표는 생략됩니다.")
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  실험 매트릭스 · 다중검정 보정 · 강건성 (§8.2, §8.3, §8.4)                              ║
# ║                                                                                          ║
# ║  주 실험 3개(V/VQ/VQF full) + 보조 어블레이션 4개(X1~X4) 를 '하나의 검정 패밀리'로 묶어      ║
# ║  BH-FDR(q=0.10) 보정한다. 개별 실험의 유의성을 보정 없이 주장하지 않는다.                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST_RESULTS: List[dict] = []
EXPERIMENTS: "OrderedDict[str, dict]" = OrderedDict()


def _pval_from_t(t: float, n: int) -> float:
    """★ 단측(우측) p값. 검정 가설은 '알파 > 0' 이다.

    양측 p를 쓰면 t = −4 (강하게 '음의' 알파) 인 실험이 p ≈ 0.0001 로 나와 BH-FDR 를
    통과하고 표에 '✔ 유의' 로 찍힌다. 손실이 유의하다는 뜻인데 읽는 사람은 정반대로 읽는다.
    단측이면 같은 실험의 p ≈ 0.9999 로 정확히 기각된다.
    """
    if t is None or not np.isfinite(t) or n < 3:
        return float("nan")
    try:
        from scipy import stats as _st                       # type: ignore
        return float(1.0 - _st.t.cdf(t, df=max(1, n - 1)))
    except Exception:
        return float(1.0 - 0.5 * (1.0 + math.erf(t / math.sqrt(2.0))))


def run_experiment(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str,
                   u200_n: int = U200_N, final_n: int = FINAL_N, second_n: int = SECOND_N,
                   use_tone: bool = True, use_nonfin: bool = True,
                   use_exclusion: bool = True, use_rule3a: bool = True,
                   stage: str = "full", scheme: str = "equal",
                   label: str = "", quiet: bool = True) -> dict:
    """한 실험(변형 × 구성)을 끝까지 돌린다. 패널 재계산 없이 선정 단계만 다시 돈다.

    ★ 실험 7개 + 민감도 수십 개를 매번 데이터 수집부터 돌리면 4시간 예산(§0.5)을 넘긴다.
      비싼 것(수집·피처)은 한 번만 하고, 싼 것(스코어·선정·체결)만 반복한다.
    """
    keep_level = LOG.min
    if quiet:
        LOG.min = LOG.LEVELS["WARN"]
    try:
        d = build_u200(P, variants=(variant,), n=u200_n)
        if stage != "x1":
            d = apply_filter2(d, variant, n=second_n, use_tone=use_tone,
                              use_nonfin=use_nonfin, use_exclusion=use_exclusion)
        d["_sel"] = build_final_selection(d, variant, n_final=final_n,
                                          use_rule3a=use_rule3a, stage=stage)
        bt = run_qbacktest(d, cal, "_sel", fwd, scheme=scheme, apply_costs=True,
                           label=label or f"{variant}-{stage}")
        bt["panel"] = d
    finally:
        LOG.min = keep_level
    return bt


def summarize_experiment(name: str, bt: dict, P: Optional[pd.DataFrame] = None,
                         variant: str = "", fwd: Optional[pd.DataFrame] = None,
                         desc: str = "") -> dict:
    R = bt["returns"]
    net = qperf_stats(R, "ret")
    gro = qperf_stats(R, "ret_gross")
    ic = icir = np.nan
    n_ic = 0
    if P is not None and fwd is not None and variant:
        sc = f"score2_{variant}" if f"score2_{variant}" in P.columns else f"score1_{variant}"
        pool = f"u200_{variant}" if f"u200_{variant}" in P.columns else None
        ic, icir, n_ic = rank_ic(P, sc, fwd, pool_col=pool)
    rec = {"name": name, "desc": desc, "net": net, "gross": gro,
           "IC": ic, "ICIR": icir, "n_ic": n_ic,
           "t": net.get("t통계량(HAC)", np.nan), "n": net.get("분기수", 0)}
    rec["p"] = _pval_from_t(rec["t"], int(rec["n"] or 0))
    EXPERIMENTS[name] = rec
    return rec


def report_experiment_table(names: Sequence[str], title: str):
    rows = []
    for nm in names:
        e = EXPERIMENTS.get(nm)
        if not e:
            continue
        n_, g_ = e["net"], e["gross"]
        f = lambda v, p=True: ("—" if v is None or not np.isfinite(v) else
                               (f"{v*100:+.2f}%" if p else f"{v:,.3f}"))
        rows.append([nm,
                     f(g_.get("CAGR")), f(n_.get("CAGR")),
                     f(n_.get("MDD")), f(n_.get("Sharpe"), False), f(n_.get("Sortino"), False),
                     f(e.get("IC"), False), f(e.get("ICIR"), False),
                     f(n_.get("분기평균회전율"), False),
                     f"{n_.get('평균종목수', float('nan')):.1f}",
                     f(n_.get("승률")), f(e.get("t"), False)])
    LOG.table(rows, ["실험", "CAGR(비용전)", "CAGR(비용후)", "MDD", "Sharpe", "Sortino",
                     "IC", "IC-IR", "회전율", "평균종목", "승률", "HAC t"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=16, title=title)
    LOG.info("§8.1 — 비용 전/후를 반드시 병기합니다. 초소형주는 스프레드가 알파를 통째로 "
             "잠식할 수 있으므로 판단 기준은 언제나 '비용 차감 후' 입니다.")


def report_bh_fdr(names: Sequence[str], q: float = BH_FDR_Q) -> dict:
    """§8.3 — 주 실험 3개 + 어블레이션 4개를 하나의 패밀리로 묶어 BH-FDR 보정."""
    fam = [n for n in names if n in EXPERIMENTS and np.isfinite(EXPERIMENTS[n].get("p", np.nan))]
    if not fam:
        LOG.warn("유효한 p값이 없어 BH-FDR 보정을 수행할 수 없습니다.")
        return {}
    ps = [EXPERIMENTS[n]["p"] for n in fam]
    passed = bh_fdr(ps, q=q)
    order = np.argsort(ps)
    m = len(ps)
    rows = []
    for rank_i, idx in enumerate(order, start=1):
        nm = fam[idx]
        thr = q * rank_i / m
        rows.append([nm, f"{EXPERIMENTS[nm]['t']:+.2f}", f"{ps[idx]:.4f}", f"{thr:.4f}",
                     "✔ 유의" if passed[idx] else "✘ 기각"])
    LOG.table(rows, ["실험", "HAC t", "p값", "BH 임계값", f"판정(q={q})"],
              ["l", "r", "r", "r", "c"],
              title=f"BH-FDR 다중검정 보정 (패밀리 {m}개 · q={q}, 단측 '알파>0') — "
                    f"보정 없이 개별 유의성을 주장하지 않는다")
    n_pass = int(passed.sum())
    if n_pass == 0:
        LOG.warn(f"패밀리 {m}개 중 BH-FDR 보정 후 유의한 실험이 하나도 없습니다. "
                 f"이는 '알파가 없다'와 '표본({EXPERIMENTS[fam[0]]['n']}분기)이 짧다'를 "
                 f"구분하지 못하는 상태입니다 — 방법론적 우려로 명시합니다.")
    return {n: bool(p) for n, p in zip(fam, passed)}


# ── §8.4 강건성 ─────────────────────────────────────────────────────────────────────────────
def R_subperiod(bt: dict, label: str = ""):
    R = bt["returns"]
    if len(R) < 8:
        return
    h = len(R) // 2
    a, b = qperf_stats(R.iloc[:h]), qperf_stats(R.iloc[h:])
    rows = []
    for k in ("CAGR", "Sharpe", "MDD", "승률"):
        fa, fb = a.get(k), b.get(k)
        fmt = (lambda v: "—" if v is None or not np.isfinite(v) else
               (f"{v*100:+.2f}%" if k in ("CAGR", "MDD", "승률") else f"{v:.3f}"))
        rows.append([k, fmt(fa), fmt(fb)])
    LOG.table(rows, ["지표", f"전반부({h}분기)", f"후반부({len(R)-h}분기)"], ["l", "r", "r"],
              title=f"[{label}] 서브기간 분할 — 한쪽 구간에서만 나오는 알파인가")
    ROBUST_RESULTS.append({"test": "서브기간", "label": label,
                           "detail": f"전반 CAGR {a.get('CAGR', float('nan')):.3f} / "
                                     f"후반 {b.get('CAGR', float('nan')):.3f}"})


def R_size_quartile(bt: dict, P: pd.DataFrame, label: str = ""):
    """시총 사분위별 성과 분해 — 하위 1000 안에서도 어느 크기 구간이 성과를 냈는가."""
    H = bt.get("holdings")
    if H is None or H.empty or "mktcap" not in P.columns:
        return
    cap = P[["code", "rebal", "mktcap"]].drop_duplicates(["code", "rebal"])
    d = H.merge(cap, on=["code", "rebal"], how="left").dropna(subset=["mktcap"])
    if d.empty:
        return
    d["q"] = d.groupby("rebal", observed=True)["mktcap"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 4, labels=["Q1(최소)", "Q2", "Q3", "Q4(최대)"])
        if s.notna().sum() >= 8 else pd.Series(["—"] * len(s), index=s.index))
    g = d.groupby("q", observed=True).agg(n=("code", "size"), ret=("ret", "mean"),
                                          contrib=("ret", lambda s: float(np.nansum(s))))
    LOG.table([[str(i), f"{int(r.n):,}", f"{r.ret*100:+.2f}%"] for i, r in g.iterrows()],
              ["시총 사분위", "관측", "분기 평균수익"], ["l", "r", "r"],
              title=f"[{label}] 시총 사분위별 성과 분해 (§8.4)")
    ROBUST_RESULTS.append({"test": "시총사분위", "label": label,
                           "detail": " / ".join(f"{i}:{r.ret*100:+.2f}%" for i, r in g.iterrows())})


def R_param_sensitivity(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str):
    """U-200 크기 · 최종 보유종목수 민감도 (§8.4). 패널 재계산 없이 선정만 다시 돈다."""
    rows = []
    for n2 in SENS_U200_SIZES:
        bt = run_experiment(P, cal, fwd, variant, u200_n=n2, label=f"U200={n2}")
        s = qperf_stats(bt["returns"])
        rows.append([f"U-200 = {n2}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}", f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    for nf in SENS_FINAL_SIZES:
        bt = run_experiment(P, cal, fwd, variant, final_n=nf, label=f"N={nf}")
        s = qperf_stats(bt["returns"])
        rows.append([f"최종 보유 = {nf}", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}", f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    LOG.table(rows, ["파라미터", "CAGR(비용후)", "Sharpe", "MDD"], ["l", "r", "r", "r"],
              title=f"[{variant}] 파라미터 민감도 — 특정 값에서만 나오는 성과인가")
    ROBUST_RESULTS.append({"test": "파라미터민감도", "label": variant,
                           "detail": f"U200 {SENS_U200_SIZES} · N {SENS_FINAL_SIZES}"})


def R_weight_scheme(P: pd.DataFrame, cal: pd.DataFrame, fwd: pd.DataFrame, variant: str):
    rows = []
    for sch in WEIGHT_SCHEMES:
        bt = run_experiment(P, cal, fwd, variant, scheme=sch, label=f"{variant}-{sch}")
        s = qperf_stats(bt["returns"])
        rows.append([{"equal": "동일가중(기준)", "invvol": "역변동성"}.get(sch, sch),
                     f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('분기평균회전율', float('nan')):.3f}"])
    LOG.table(rows, ["가중 방식", "CAGR(비용후)", "Sharpe", "MDD", "회전율"],
              ["l", "r", "r", "r", "r"], title=f"[{variant}] 가중 방식 (§7.4 동일가중 기준 + 역변동성 병행)")


def R_rebal_shift(rebuild_fn: Callable, variant: str):
    """리밸런싱 시점 ±5거래일 이동 민감도. 캘린더가 바뀌므로 패널을 다시 만들어야 한다 —
    가장 비싼 강건성 검정이라 최우수 변형에만 적용한다."""
    rows = []
    for sh in SENS_REBAL_SHIFTS:
        try:
            s = rebuild_fn(sh, variant)
        except Exception as e:                                # noqa
            LOG.warn(f"리밸런싱 {sh:+d}거래일 재구성 실패({type(e).__name__}) — 건너뜁니다.")
            continue
        if not s:
            continue
        rows.append([f"{sh:+d} 거래일", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    if rows:
        LOG.table(rows, ["리밸런싱 시점 이동", "CAGR(비용후)", "Sharpe", "MDD"],
                  ["l", "r", "r", "r"],
                  title=f"[{variant}] 리밸런싱 시점 ±5거래일 민감도 (§8.4)")
        ROBUST_RESULTS.append({"test": "리밸시점이동", "label": variant,
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def R_flow_window(rebuild_flow_fn: Callable):
    """VQF 수급 창 길이 민감도 20/60/120일 (§8.4)."""
    rows = []
    for w in SENS_FLOW_WINDOWS:
        try:
            s = rebuild_flow_fn(w)
        except Exception as e:                                # noqa
            LOG.warn(f"수급 창 {w}일 재구성 실패({type(e).__name__}) — 건너뜁니다.")
            continue
        if not s:
            continue
        rows.append([f"{w}일", f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%",
                     f"{s.get('분기평균회전율', float('nan')):.3f}"])
    if rows:
        LOG.table(rows, ["수급 창 길이", "CAGR(비용후)", "Sharpe", "MDD", "회전율"],
                  ["l", "r", "r", "r", "r"],
                  title="[VQF] 수급 창 길이 민감도 (§8.4) — 60일이 특별한 값인가")
        ROBUST_RESULTS.append({"test": "수급창길이", "label": "VQF",
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def R_irc_split(rebuild_irc_fn: Callable, variant: str):
    """한국IR협의회 기업의뢰형 리포트 포함/제외 (§0.4, §8.4)."""
    rows = []
    for excl in (False, True):
        try:
            s = rebuild_irc_fn(excl, variant)
        except Exception as e:                                # noqa
            LOG.warn(f"IR협의회 {'제외' if excl else '포함'} 재구성 실패({type(e).__name__})")
            continue
        if not s:
            continue
        rows.append(["제외" if excl else "포함(기준)",
                     f"{s.get('CAGR', float('nan'))*100:+.2f}%",
                     f"{s.get('Sharpe', float('nan')):.3f}",
                     f"{s.get('MDD', float('nan'))*100:+.1f}%"])
    if rows:
        LOG.table(rows, ["기업의뢰형 리포트", "CAGR(비용후)", "Sharpe", "MDD"],
                  ["l", "r", "r", "r"],
                  title=f"[{variant}] 한국IR협의회 기업의뢰형 리포트 포함/제외 (§0.4 별도 태깅 검증)")
        ROBUST_RESULTS.append({"test": "IR협의회분리", "label": variant,
                               "detail": " / ".join(r[0] + " " + r[1] for r in rows)})


def report_robustness():
    if not ROBUST_RESULTS:
        LOG.warn("강건성 결과가 비었습니다.")
        return
    LOG.table([[r["test"], r.get("label", ""), _trunc(str(r.get("detail", "")), 60)]
               for r in ROBUST_RESULTS],
              ["검정", "대상", "요약"], ["l", "l", "l"], maxw=62,
              title="강건성 검사 요약 (§8.4)")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  Phase 0 게이트 · 수급축 판정(§9) · 사전등록 폐기조건(§10.4) · 최종 산출물(§10.3)      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PHASE0: Dict[str, Any] = {}
# Phase 0 판정을 하류가 실제로 읽는다. 표에 "미달 시 행동"을 적어 놓고 아무것도 하지 않으면
# 그 표는 거짓말이 된다(적대적 감사가 지적한 그대로).
PHASE0_FLOW_OK: Optional[bool] = None


def report_phase0(fin_cov: float, flow_cov: float, dart_parse: float,
                  report_cov_200: float, pair_count_200: float) -> dict:
    """§2.1 데이터 실현가능성 게이트. 실패해도 해당 컴포넌트만 끄고 전략은 계속한다(§2.2)."""
    LOG.banner("Phase 0 — 데이터 실현가능성 게이트 (§2)",
               "게이트 실패 시 해당 컴포넌트만 비활성화한다. fin_cov 실패만 전략 중단 사유다.")
    spec = [
        ("fin_cov", fin_cov, 0.90, "U-1000 재무데이터 가용률", "게이트", "전략 중단"),
        # ★ '미달 시 행동' 칸은 코드가 실제로 하는 일과 정확히 일치해야 한다. 하지도 않을
        #   조치를 적어두면 그 표 자체가 거짓 보증이 된다(적대적 감사가 잡아낸 유형).
        ("flow_cov", flow_cov, 0.95, "외국인·기관 순매수 가용률", "게이트",
         "VQF 는 참고 산출, §9 C1·C2 판정 불가"),
        ("dart_parse_rate", dart_parse, 0.80, "DART 본문 기계판독 성공률", "게이트",
         "사유 분해 보고 후 진행(§2.2)"),
        ("report_cov_200", report_cov_200, None, "U-200 내 리포트 ≥1건 비율", "측정만", "—"),
        ("pair_count_200", pair_count_200, None, "U-200 내 연속 2분기 리포트 종목수", "측정만", "—"),
    ]
    rows, verdict = [], {}
    for key, val, thr, desc, kind, action in spec:
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            shown, ok = "—", None
        else:
            shown = f"{val:,.0f}" if key == "pair_count_200" else f"{100*val:.1f}%"
            ok = None if thr is None else bool(val >= thr)
        verdict[key] = {"value": val, "pass": ok}
        rows.append([key, desc, shown,
                     ("—" if thr is None else f"≥ {100*thr:.0f}%"),
                     kind,
                     ("—" if ok is None else ("✔ 통과" if ok else "✘ 미달")),
                     action if ok is False else ""])
    LOG.table(rows, ["항목", "정의", "실측", "기준", "성격", "판정", "미달 시 행동"],
              ["l", "l", "r", "r", "c", "c", "l"], maxw=34)
    LOG.info("§2.2 — report_cov_200 이 낮게 나오는 것은 예상된 결과이며 실패가 아닙니다. "
             "애널리스트 축은 결측 허용 설계(§6.2)이므로 그대로 진행하되 실측치를 보고합니다.")
    PHASE0.update(verdict)
    globals()["PHASE0_FLOW_OK"] = verdict.get("flow_cov", {}).get("pass")
    if verdict.get("flow_cov", {}).get("pass") is False:
        LOG.warn("flow_cov 게이트 미달 — 수급(F) 축의 표본이 부분적입니다. VARIANT-VQF 는 "
                 "참고용으로 끝까지 산출하되, §9 의 C1·C2 는 '판정 불가'로 처리합니다. "
                 "부분 표본으로 계산한 Sharpe 차이를 채택 근거로 쓰지 않기 위함입니다(§10.1).")
    return verdict


def report_flow_verdict(cmp_res: dict, exp_vq: str = "VQ-full", exp_vqf: str = "VQF-full",
                        fdr_pass: Optional[dict] = None) -> dict:
    """§9 — VARIANT-VQF 채택 여부 C1~C5. 자동 채택하지 않고 판정 결과만 보고한다."""
    LOG.banner("수급 축 판정 (§9)",
               "C1~C5 를 모두 충족해야 채택. 하나라도 미충족이면 수급 축 기각 → VQ 채택 권고")
    e_vq = EXPERIMENTS.get(exp_vq, {})
    e_vqf = EXPERIMENTS.get(exp_vqf, {})
    s_vq = (e_vq.get("net") or {}).get("Sharpe", np.nan)
    s_vqf = (e_vqf.get("net") or {}).get("Sharpe", np.nan)

    # C1: 비용 차감 후 Sharpe 우위
    #  ★ flow_cov 게이트가 미달이면 F축 표본 자체가 부분적이라 이 비교가 성립하지 않는다.
    #    숫자는 보여주되 판정은 내리지 않는다 — 근거 없는 채택/기각 둘 다 §10.1 위반이다.
    _flow_ok = globals().get("PHASE0_FLOW_OK")
    if _flow_ok is False:
        c1, c1_d = None, (f"VQF {s_vqf:.3f} vs VQ {s_vq:.3f} — 단, flow_cov 게이트 미달로 "
                          f"판정 불가" if np.isfinite(s_vqf) and np.isfinite(s_vq)
                          else "flow_cov 게이트 미달 — 판정 불가")
    else:
        c1 = bool(np.isfinite(s_vq) and np.isfinite(s_vqf) and s_vqf > s_vq)
        c1_d = (f"VQF {s_vqf:.3f} vs VQ {s_vq:.3f}"
                if np.isfinite(s_vq) and np.isfinite(s_vqf) else "산출 불가")

    # C2: 그 차이가 BH-FDR 보정 후에도 유의
    if _flow_ok is False:
        c2, c2_d = None, "flow_cov 게이트 미달 — 판정 불가"
    elif fdr_pass is None:
        c2, c2_d = None, "BH-FDR 결과 없음"
    else:
        c2 = bool(fdr_pass.get(exp_vqf, False)) and c1
        c2_d = (f"VQF-full BH-FDR {'통과' if fdr_pass.get(exp_vqf) else '기각'}"
                + ("" if c1 else " · C1 미충족이라 차이 자체가 없음"))

    # C3: U-200 중복률 < 0.85
    ov = (cmp_res or {}).get("overlap", {})
    key = next((k for k in ov if set(k.split("~")) == {"VQ", "VQF"}), None)
    o = ov.get(key, np.nan) if key else np.nan
    c3 = bool(np.isfinite(o) and o < 0.85)
    c3_d = f"VQ∩VQF 중복률 {o:.3f}" if np.isfinite(o) else "산출 불가"

    # C4: 수급 비영 관측 비율 ≥ 30%
    nz = globals().get("FLOW_NONZERO_RATIO", float("nan"))
    c4 = bool(np.isfinite(nz) and nz >= 0.30)
    c4_d = f"비영 관측 {100*nz:.1f}%" if np.isfinite(nz) else "산출 불가"

    # C5: 리포트 커버리지가 VQ 대비 크게 높지 않음
    cov = (cmp_res or {}).get("coverage", {})
    cvq, cvqf = cov.get("VQ", np.nan), cov.get("VQF", np.nan)
    if np.isfinite(cvq) and np.isfinite(cvqf):
        gap = cvqf - cvq
        c5 = bool(gap <= 0.10)
        c5_d = f"커버리지 VQF {100*cvqf:.1f}% − VQ {100*cvq:.1f}% = {100*gap:+.1f}%p (기준 ≤ +10%p)"
    else:
        c5, c5_d = None, "리포트 커버리지 산출 불가 → 판정 불가"

    items = [
        ("C1", "비용 차감 후 VQF Sharpe > VQ Sharpe", c1, c1_d),
        ("C2", "그 차이가 BH-FDR 보정 후에도 유의", c2, c2_d),
        ("C3", "VQF 의 U-200 이 VQ 와 충분히 다름 (중복률 < 0.85)", c3, c3_d),
        ("C4", "수급 축 비영 관측 비율 ≥ 30% (U-1000)", c4, c4_d),
        ("C5", "VQF 리포트 커버리지가 VQ 대비 크게 높지 않음", c5, c5_d),
    ]
    LOG.table([[k, d, ("판정불가" if ok is None else ("✔ 충족" if ok else "✘ 미충족")), det]
               for k, d, ok, det in items],
              ["조건", "내용", "판정", "근거 수치"], ["c", "l", "c", "l"], maxw=52)

    # ★ '판정 불가(None)'를 충족으로 세지 않는다. 모르는 것을 근거로 채택하면 안 된다.
    all_ok = all(ok is True for _k, _d, ok, _t in items)
    unknown = [k for k, _d, ok, _t in items if ok is None]
    if all_ok:
        LOG.ok("§9 — C1~C5 를 모두 충족했습니다. 수급 축 채택을 '권고'합니다. "
               "다만 자동 채택하지 않습니다 — 최종 결정은 사용자의 몫입니다.")
    else:
        fail = [k for k, _d, ok, _t in items if ok is False]
        LOG.warn(f"§9 — 미충족 조건 {fail or '없음'}"
                 + (f" · 판정불가 {unknown}" if unknown else "") +
                 ". 규정대로 수급 축을 기각하고 VARIANT-VQ 채택을 권고합니다.")
    return {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5,
            "adopt_flow": all_ok, "details": {k: t for k, _d, _o, t in items}}


def report_preregistration_kill(main_names: Sequence[str], best: str,
                                x1_name: str) -> dict:
    """§10.4 사전등록 폐기 조건. 충족 시 파라미터 튜닝으로 되살리지 않고 보고 후 중단한다."""
    LOG.banner("사전등록 폐기 조건 점검 (§10.4)",
               "충족 시 파라미터 튜닝으로 되살리려 시도하지 않는다 — 폐기 보고 후 중단")
    out = {}

    # ① 세 변형 모두 거래비용 차감 후 알파 소멸
    cagrs = {n: (EXPERIMENTS.get(n, {}).get("net") or {}).get("CAGR", np.nan)
             for n in main_names}
    alive = [n for n, v in cagrs.items() if np.isfinite(v) and v > 0]
    k1 = len(alive) == 0
    out["all_alpha_dead"] = k1

    # ② X1(1차만)과 최우수 full 의 차이가 미미 → 깔때기 구조 무가치
    s_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("Sharpe", np.nan)
    s_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("Sharpe", np.nan)
    k2 = bool(np.isfinite(s_full) and np.isfinite(s_x1) and (s_full - s_x1) < 0.05)
    out["funnel_worthless"] = k2

    # ③ 배제플래그가 MDD 개선에 기여하지 못함 → 2층 논리 반증
    m_full = (EXPERIMENTS.get(best, {}).get("net") or {}).get("MDD", np.nan)
    m_x1 = (EXPERIMENTS.get(x1_name, {}).get("net") or {}).get("MDD", np.nan)
    k3 = bool(np.isfinite(m_full) and np.isfinite(m_x1) and (m_full <= m_x1 + 1e-9))
    out["exclusion_no_mdd_help"] = k3

    LOG.table([
        ["① 세 변형 모두 비용 차감 후 알파 소멸",
         ", ".join(f"{n} {100*cagrs[n]:+.1f}%" for n in main_names if np.isfinite(cagrs.get(n, np.nan))) or "산출 불가",
         "❗ 충족(폐기)" if k1 else "✔ 미충족"],
        ["② X1(1차만) 과 최우수 full 의 차이가 미미",
         f"Sharpe {s_full:.3f} vs X1 {s_x1:.3f}" if np.isfinite(s_full) and np.isfinite(s_x1) else "산출 불가",
         "❗ 충족(폐기)" if k2 else "✔ 미충족"],
        ["③ 배제 컴포넌트가 MDD 개선에 기여 못함",
         f"MDD {100*m_full:+.1f}% vs X1 {100*m_x1:+.1f}%" if np.isfinite(m_full) and np.isfinite(m_x1) else "산출 불가",
         "❗ 충족(폐기)" if k3 else "✔ 미충족"],
    ], ["폐기 조건", "근거 수치", "판정"], ["l", "l", "c"], maxw=48)

    if any(out.values()):
        LOG.warn("§10.4 폐기 조건이 충족되었습니다. 이 결과를 파라미터 조정으로 되살리려 하지 "
                 "마십시오. 위 수치를 그대로 보고하고 중단하는 것이 사전등록의 이행입니다.")
    else:
        LOG.ok("§10.4 폐기 조건에 해당하지 않습니다.")
    LOG.info("§10.2 성격 구분 — 1차필터(가치·퀄리티)의 기여는 알파 창출로, 2차 배제플래그와 "
             "3-A 의 기여는 좌측꼬리 제거(MDD·Sortino)로 해석합니다. 배제 컴포넌트가 CAGR 을 "
             "크게 올렸다면 그것이 우연인지 별도로 검증해야 합니다.")
    return out


def report_final_holdings(P: pd.DataFrame, variant: str, sel_col: str,
                          sec: pd.DataFrame, top_n: int = 60) -> pd.DataFrame:
    """§10.3-9 — 3-A 규칙판 최종 편입 종목 리스트 (3-B 재량 검토용)."""
    if sel_col not in P.columns:
        return pd.DataFrame()
    last = P["rebal"].max()
    sub = P[(P["rebal"] == last) & P[sel_col].fillna(False).astype(bool)].copy()
    if sub.empty:
        LOG.warn("최종 시점 편입 종목이 없습니다.")
        return sub
    names = sec.set_index("code")["name"].astype(str).to_dict() if len(sec) else {}
    sub["name"] = sub["code"].map(names).fillna("")
    cols = ["code", "name", "sector", "mktcap", "adtv", f"score1_{variant}",
            f"score2_{variant}", "dNONFIN", "dTONE_resid", "n_reports"]
    cols = [c for c in cols if c in sub.columns]
    sub = sub.sort_values(f"score2_{variant}" if f"score2_{variant}" in sub.columns
                          else f"score1_{variant}", ascending=False)
    LOG.table([[r.get("code"), _trunc(r.get("name", ""), 16), _trunc(str(r.get("sector", "")), 12),
                f"{r.get('mktcap', float('nan'))/1e8:,.0f}억",
                f"{r.get('adtv', float('nan'))/1e8:,.2f}억",
                f"{r.get(f'score1_{variant}', float('nan')):+.2f}",
                f"{r.get(f'score2_{variant}', float('nan')):+.2f}",
                f"{r.get('dNONFIN', float('nan')):.0f}" if np.isfinite(r.get("dNONFIN", np.nan)) else "—",
                f"{r.get('dTONE_resid', float('nan')):+.3f}" if np.isfinite(r.get("dTONE_resid", np.nan)) else "0(중립)",
                f"{int(r.get('n_reports', 0) or 0)}"]
               for _i, r in sub.head(top_n).iterrows()],
              ["코드", "종목명", "섹터", "시총", "ADTV", "Score1", "Score2", "ΔNONFIN", "ΔTONE_r", "리포트"],
              ["l", "l", "l", "r", "r", "r", "r", "r", "r", "r"],
              title=f"[{variant}] {pd.Timestamp(last):%Y-%m} 3-A 규칙판 최종 편입 종목 "
                    f"(§7.3 3-B 재량 검토용 — 백테스트에는 3-B 를 소급 적용하지 않았습니다)")
    return sub[cols + ["name"]] if cols else sub


def report_dataflow_map():
    """거시적 흐름 한 장 — 어디서 어디로 데이터가 가는지."""
    LOG.banner("데이터 흐름 지도 (거시)", "모듈 경계와 계층 — 에러가 나면 어느 상자인지 먼저 보세요")
    _safe_print("""
  ┌── L0 부트/캐시 ──────────────────────────────────────────────────────────────────────┐
  │ 환경감지 → 의존성 → 캐시루트 해석(드라이브 쓰기 1곳 + 로컬 미러 N곳 읽기전용)          │
  │            └ adopt_scan: 기존 리포트를 '이동 없이 참조 등록'                           │
  │ DartQuota: 공용 저널로 전략 간 사용량 합산 · 020 수신 지점을 그날의 실측 한도로 기록    │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L1 수집 ────────────────────────────────────────────────────────────────────────────┐
  │ 종목마스터  ← FDR GitHub캐시 / KIND / pykrx스냅샷 / DART corpCode / 네이버              │
  │ 가격        ← pykrx → FDR → 네이버차트 → yfinance (폴백 체인 + 소스 감사표)             │
  │ 시가총액    ← ①pykrx 전종목 스냅샷 ②DART 주식총수×종가 ③주식수 이월×종가                │
  │ 수급        ← pykrx 기간 순매수(시장 단위 집계) → 폴백: 일별 수급 롤링                  │
  │ DART        ← 재무제표 / 주식총수 / 공시목록(A·B·F·I) / 사업보고서 본문(규칙기반 추출)  │
  │ 리서치      ← 한경컨센서스(작성자·목표주가) + 네이버(종목코드) → 병합 → 보고서 원장     │
  │               └ 애널리스트 원장 → (analyst_id, code, date, tp) → 목표주가 수정률        │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼ 모든 테이블 pit_frame() 통과 · knowledge_date = 접수일+1거래일
  ┌── L1/L2 피처 ─────────────────────────────────────────────────────────────────────────┐
  │ 분기 캘린더(신호=직전 거래일 / 체결=익 거래일 시가)                                     │
  │ 유니버스 격자 → PIT 재무 as-of 결합 → U-1000 선정(구조제외·유동성·자본잠식)             │
  │ 섹터 셀 → V축(부호처리) · Q축(주식수증가율 포함) · F축(유동시총 정규화)                 │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L2 필터 ────────────────────────────────────────────────────────────────────────────┐
  │ 1차: Score1 = w_V·Z_V + w_Q·Z_Q + w_F·Z_F  → U-200 ×3변형 → 중복률·특성 비교           │
  │ 2차: Score2 = 2·z(ΔNONFIN) + 1·z(ΔTONE_resid) − 배제(하드) → 60~80                     │
  │      ★ 리포트 없는 종목 = ΔTONE_resid 0(중립). 관측치 z 를 만든 '뒤에' 0 을 넣는다     │
  │ 3차: 3-A 규칙 체크리스트(소송·특수관계자·최대주주·감사·연속적자·자본잠식) → 20~40       │
  └──────────────────────────────────┬────────────────────────────────────────────────────┘
                                     ▼
  ┌── L3 백테스트 → L5 강건성 → L6 리포트 ────────────────────────────────────────────────┐
  │ 익일시가 체결 · 폐지 −100%(정리매매 있으면 반영) · 거래세이력+CS스프레드+제곱근충격      │
  │ 주 실험 3 + 어블레이션 X1~X4 → BH-FDR(q=0.10) → 서브기간·시총사분위·민감도             │
  │ → 수급축 C1~C5 판정 → 사전등록 폐기조건 → 최종 편입 종목표                             │
  └───────────────────────────────────────────────────────────────────────────────────────┘
""")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-H  계약 자동검정 Q1~Q12 — 협상 불가 규칙을 코드가 스스로 증명한다                       ║
# ║                                                                                          ║
# ║  주석은 지켜지지 않아도 아무 일이 없지만, 여기의 검정은 실패하면 실행이 멈춘다.             ║
# ║  일부 계약은 '소스 검사'다 — 최적화 루틴이 없다는 것은 실행으로 증명할 수 없고              ║
# ║  코드에 그것이 존재하지 않음을 확인하는 방법밖에 없다.                                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

import inspect as _inspect

CONTRACTS: List[dict] = []


def _contract(cid: str, name: str, critical: bool = True):
    def deco(fn):
        CONTRACTS.append({"id": cid, "name": name, "fn": fn, "critical": critical})
        return fn
    return deco


class ContractViolation(Exception):
    pass


@_contract("Q1", "PIT 게이트 — PIT 컬럼 없는 테이블은 등록 자체가 거부된다")
def _q1():
    st = PITStore()
    bad = pd.DataFrame({"code": ["000660"], "x": [1.0]})
    try:
        st.register("bad", bad)
    except KeyError:
        pass
    else:
        raise ContractViolation("PIT 컬럼이 없는 테이블이 등록되었습니다 — C1 게이트가 열려 있습니다.")
    ok = pit_frame(pd.DataFrame({"code": ["000660"], "x": [1.0]}),
                   "2020-01-01", "2020-02-15")
    st.register("ok", ok)
    got = st.get("ok", "2020-01-31")
    if len(got) != 0:
        raise ContractViolation("knowledge_date 이후 시점의 행이 조회되었습니다 — 미래누수입니다.")
    if len(st.get("ok", "2020-02-20")) != 1:
        raise ContractViolation("knowledge_date 이후에도 행이 보이지 않습니다.")
    return "PIT 등록 거부 + as_of 절단 정상"


@_contract("Q2", "시점 규약 — 신호일 < 체결일, 공시는 접수일+1거래일")
def _q2():
    days = pd.bdate_range("2020-01-01", "2020-06-30")
    px = pd.DataFrame({"code": "000660", "date": days, "open": 1.0, "high": 1.0,
                       "low": 1.0, "close": 1.0, "volume": 1.0, "amount": 1.0})
    set_trading_days(px)
    cal = qvf_rebal_calendar(px, "2020-01-01", "2020-06-30")
    if not (cal["signal_date"] < cal["exec_date"]).all():
        raise ContractViolation("signal_date >= exec_date 인 리밸런싱이 있습니다.")
    d0 = as_ts("2020-03-10")
    d1 = next_trading_day(d0)
    if not (d1 > d0):
        raise ContractViolation("next_trading_day 가 날짜를 미래로 밀지 않습니다 (§4 위반).")
    s = next_trading_day_series(pd.Series([d0, as_ts("2020-03-13")]))
    if not (as_ts_series(s) > pd.Series([d0, as_ts("2020-03-13")])).all():
        raise ContractViolation("next_trading_day_series 가 §4 규약을 만족하지 않습니다.")
    return f"리밸 {len(cal)}시점 · 접수일+1거래일 이동 확인"


@_contract("Q3", "생존자편향 — 폐지 종목이 유니버스에 있고 −100% 가 적용된다")
def _q3():
    days = pd.bdate_range("2020-01-01", "2021-06-30")
    rows = []
    for c, stop in (("000001", None), ("000002", as_ts("2020-08-15"))):
        dd = days if stop is None else days[days <= stop]
        rows.append(pd.DataFrame({"code": c, "date": dd, "open": 100.0, "high": 101.0,
                                  "low": 99.0, "close": 100.0, "volume": 1e5, "amount": 1e7}))
    px = pd.concat(rows, ignore_index=True)
    set_trading_days(px)
    cal = qvf_rebal_calendar(px, "2020-01-01", "2021-06-30")
    sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["A", "B"],
                        "market": ["KOSPI", "KOSDAQ"],
                        "listing_date": [as_ts("2010-01-01")] * 2,
                        "delisting_date": [pd.NaT, as_ts("2020-08-20")],
                        "industry": ["기계", "기계"], "corp_code": ["C1", "C2"], "src": "t"})
    uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
    at = uni.at(as_ts("2020-06-01"))
    if "000002" not in at:
        raise ContractViolation("폐지 예정 종목이 폐지 전 시점의 유니버스에서 빠졌습니다 — 생존자편향.")
    if "000002" in uni.at(as_ts("2020-12-01")):
        raise ContractViolation("폐지 이후 시점에 폐지 종목이 유니버스에 남아 있습니다.")
    ep = build_exec_prices(cal, px)
    fwd = build_forward_returns(ep, cal, {"000002": as_ts("2020-08-20")}, px)
    row = fwd[(fwd["code"] == "000002") & (fwd["rebal"] == as_ts("2020-06-01"))]
    if row.empty or not np.isclose(float(row["fwd_ret"].iloc[0]), -1.0, atol=1e-9):
        raise ContractViolation(
            "보유 중 상장폐지에 −100% 가 적용되지 않았습니다 (§3.4 위반). "
            "가격 시계열이 폐지 직전에 끊겼을 때 마지막 정상가를 청산가로 쓰면 "
            "'상장폐지 = 무손실'이 되어 생존자편향이 그대로 재유입됩니다.")
    # 정리매매가 실제로 관측된 경우에는 그 가격을 써야 한다(무조건 −100% 도 틀렸다).
    px2 = px.copy()
    tail = px2["code"] == "000002"
    px2.loc[tail & (px2["date"] >= as_ts("2020-08-10")), ["close", "open"]] = 12.0
    extra = pd.DataFrame({"code": "000002",
                          "date": pd.bdate_range("2020-08-17", "2020-08-19"),
                          "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
                          "volume": 1e4, "amount": 1e5})
    px2 = pd.concat([px2, extra], ignore_index=True)
    fwd2 = build_forward_returns(build_exec_prices(cal, px2), cal,
                                 {"000002": as_ts("2020-08-20")}, px2)
    r2 = fwd2[(fwd2["code"] == "000002") & (fwd2["rebal"] == as_ts("2020-06-01"))]
    if r2.empty or float(r2["fwd_ret"].iloc[0]) <= -0.999:
        raise ContractViolation("정리매매 체결가가 관측되었는데도 −100% 로 처리했습니다 "
                                "(§3.4 는 '실제 체결가 반영'을 먼저 요구합니다).")
    return (f"폐지 전 포함 · 폐지 후 제외 · 데이터 끊김 → −100% · "
            f"정리매매 관측 → 실가 반영({float(r2['fwd_ret'].iloc[0]):+.1%})")


@_contract("Q4", "부호 처리 — 음수 분모가 최우량이 아니라 최하위로 배정된다")
def _q4():
    n = 40
    P = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
    })
    P["cell"] = "202003|기계"
    P["cell_l2"] = P["cell"]
    P["cell_l3"] = "202003|ALL"
    # 앞 5개는 EBIT 음수(= 분모 부적격), 나머지는 양수이며 비율이 클수록(=비쌀수록) 나쁨
    ebit = pd.Series([-1.0] * 5 + list(np.linspace(1.0, 5.0, n - 5)))
    cap = pd.Series([100.0] * n)
    raw = safe_div(cap, ebit)
    valid = ebit > 0
    z = z_lower_is_better(P, raw, valid, "테스트")
    bad_z = float(z.iloc[:5].mean())
    good_z = float(z.iloc[5:].max())
    if not (bad_z <= z.iloc[5:].min() + 1e-6):
        raise ContractViolation(
            f"음수 EBIT 종목의 z({bad_z:.3f})가 최하위가 아닙니다 — 적자기업이 최우량으로 "
            f"오분류되는 §5.2 위반입니다.")
    if not np.isfinite(good_z):
        raise ContractViolation("정상 관측의 z 가 산출되지 않았습니다.")
    return f"음수분모 z={bad_z:+.2f} ≤ 정상 최소 z={float(z.iloc[5:].min()):+.2f}"


@_contract("Q5", "결측 허용 — 리포트 없는 종목의 z 는 0(중립)이며 관측치 z 를 오염시키지 않는다")
def _q5():
    n = 60
    P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                      "rebal": [as_ts("2020-03-01")] * n,
                      "sector": ["기계"] * n})
    P["cell"] = "202003|기계"
    P["cell_l2"] = P["cell"]
    P["cell_l3"] = "202003|ALL"
    v = np.full(n, np.nan)
    v[:20] = np.linspace(-1.0, 1.0, 20)          # 20개만 관측, 40개는 리포트 없음
    P["dTONE_resid"] = v
    mask = P["dTONE_resid"].notna()
    z = zscore_observed_then_neutral(P, "dTONE_resid", mask)
    if not np.isclose(float(z[~mask].abs().max()), 0.0):
        raise ContractViolation("리포트 없는 종목의 z 가 0(중립)이 아닙니다 (§6.2 위반).")
    obs = z[mask]
    if abs(float(obs.mean())) > 0.15 or abs(float(obs.std(ddof=0)) - 1.0) > 0.25:
        raise ContractViolation(
            f"관측치 z 의 평균 {float(obs.mean()):.3f} / 표준편차 {float(obs.std(ddof=0)):.3f} — "
            f"결측 0 을 z-score '이전'에 주입해 분포가 오염되었습니다 (§6.2 핵심 위반).")
    return f"관측 z 평균 {float(obs.mean()):+.3f} · 표준편차 {float(obs.std(ddof=0)):.3f} · 결측 z=0"


@_contract("Q6", "사전등록 가중치 — 코드 어디에도 가중치 최적화 루틴이 없다")
def _q6():
    if abs(sum(VARIANT_W["VQF"]) - 1.0) > 1e-9 or VARIANT_W["V"] != (1.0, 0.0, 0.0):
        raise ContractViolation("VARIANT_W 가 §5.5 사전등록 값과 다릅니다.")
    if (SCORE2_W_NONFIN, SCORE2_W_TONE) != (2.0, 1.0):
        raise ContractViolation("Score2 가중치가 §6.3 사전등록 값(2:1)과 다릅니다.")
    src = ""
    for fn in (score1, build_u200, apply_filter2, build_final_selection, run_experiment):
        try:
            src += _inspect.getsource(fn)
        except Exception:
            pass
    bad = re.findall(r"\b(minimize|curve_fit|GridSearch|RandomizedSearch|optimize|"
                     r"differential_evolution|fmin|argmax\s*\(\s*sharpe|best_weight)\b", src)
    if bad:
        raise ContractViolation(f"선정 경로에서 최적화 흔적이 발견되었습니다: {sorted(set(bad))}")
    return "가중치 고정 확인 · 선정 경로에 최적화 루틴 없음"


@_contract("Q7", "캐시 무결성 — 삭제 API 부재 · 로컬 미러는 쓰기 경로에 등장하지 않는다")
def _q7():
    for nm in ("delete", "remove", "drop_table", "purge", "rmtree"):
        if hasattr(Vault, nm) or hasattr(QVFVault, nm):
            raise ContractViolation(f"Vault 에 삭제 API '{nm}' 가 존재합니다 — 절대 1원칙 위반.")
    for fn in (Vault.put_table, Vault.put_blob, Vault.flush, Vault.compact):
        s = _inspect.getsource(fn)
        if "mirror" in s.lower():
            raise ContractViolation(f"쓰기 함수 {fn.__name__} 가 미러 경로를 참조합니다 — "
                                    f"로컬 미러는 구조적으로 읽기 전용이어야 합니다.")
    s = _inspect.getsource(QVFVault)
    if re.search(r"os\.(remove|unlink|rmdir)|shutil\.rmtree", s):
        raise ContractViolation("QVFVault 에 파일 삭제 호출이 있습니다 — 절대 1원칙 위반.")

    # ★ 소스 grep 만으로는 '상속받은 쓰기 코드가 미러 경로를 만들 수 있는가'를 못 본다.
    #   실제로 미러에 쓰려고 시도시켜 보고, 막히는지 확인한다.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        wroot, mroot = os.path.join(td, "w"), os.path.join(td, "m")
        os.makedirs(os.path.join(mroot, GDRIVE_SHARED_NS, "table"), exist_ok=True)
        v = QVFVault(wroot, "TEST", [mroot])
        blocked = False
        try:
            v._wpath(os.path.join(mroot, GDRIVE_SHARED_NS, "table", "x.parquet"))
        except PermissionError:
            blocked = True
        if not blocked:
            raise ContractViolation("미러 경로가 쓰기 경로 검증을 통과했습니다 — "
                                    "로컬 미러가 읽기 전용이라는 보장이 구조적이지 않습니다.")
        # 미러의 손상 파일을 읽어도 원본을 개명하지 않아야 한다.
        bad = os.path.join(mroot, GDRIVE_SHARED_NS, "table", "broken.parquet")
        open(bad, "wb").write(b"")                       # 0바이트 = 드라이브 동기화 미완 상황
        v.get_table("broken", scope="shared")
        if not os.path.exists(bad):
            raise ContractViolation("미러의 파일이 사라졌습니다 — 읽기가 파일을 파괴했습니다.")
        if [f for f in os.listdir(os.path.dirname(bad)) if ".corrupt" in f]:
            raise ContractViolation("미러 파일이 .corrupt 로 개명되었습니다 — "
                                    "read_parquet_safe 가 미러에 도달했습니다(절대 1원칙 위반).")
    return "삭제 API 없음 · 미러 쓰기 차단 확인 · 미러 손상파일 읽어도 원본 보존"


@_contract("Q8", "결정성 — 같은 입력에 같은 선정 (동점 처리가 행 순서에 의존하지 않는다)")
def _q8():
    n = 50
    rng = np.random.default_rng(SEED)
    base = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "rebal": [as_ts("2020-03-01")] * n,
        "sector": ["기계"] * n,
        "Z_V": np.round(rng.normal(size=n), 2),      # 반올림으로 동점을 일부러 만든다
        "Z_Q": np.round(rng.normal(size=n), 2),
        "Z_F": np.nan, "mktcap": rng.lognormal(23, 1, n),
    })
    a = build_u200(base, variants=("VQ",), n=20)
    b = build_u200(base.sample(frac=1.0, random_state=7).reset_index(drop=True),
                   variants=("VQ",), n=20)
    sa = set(a.loc[a["u200_VQ"], "code"])
    sb = set(b.loc[b["u200_VQ"], "code"])
    if sa != sb:
        raise ContractViolation(
            f"행 순서를 섞었더니 선정이 달라졌습니다({len(sa ^ sb)}종목 차이) — "
            f"포트폴리오가 데이터가 아니라 정렬의 함수입니다.")
    return f"행 순서 무관 · 선정 {len(sa)}종목 동일"


@_contract("Q9", "분기 연율화 — √4 를 쓴다 (√12 를 쓰면 변동성이 1.7배 과대계상된다)")
def _q9():
    if abs(Q_PER_YEAR - 4.0) > 1e-9:
        raise ContractViolation("Q_PER_YEAR 가 4 가 아닙니다.")
    r = np.array([0.05, -0.03, 0.04, 0.01] * 10)
    R = pd.DataFrame({"rebal": pd.date_range("2016-03-01", periods=len(r), freq="QS"),
                      "ret": r, "n": 30, "turnover": 0.5, "cost": 0.0})
    s = qperf_stats(R)
    exp_vol = float(np.std(r, ddof=1) * math.sqrt(4))
    if abs(s["연변동성"] - exp_vol) > 1e-9:
        raise ContractViolation(f"연변동성 {s['연변동성']:.4f} != √4 기준 {exp_vol:.4f}")
    exp_cagr = float(np.prod(1 + r) ** (1 / (len(r) / 4.0)) - 1)
    if abs(s["CAGR"] - exp_cagr) > 1e-9:
        raise ContractViolation("CAGR 의 연수 환산이 분기 기준이 아닙니다.")
    return f"연변동성 √4 · CAGR 연수 = 분기수/4 확인"


@_contract("Q10", "비용 — 비용 차감 후 수익은 항상 차감 전 이하다")
def _q10():
    src = _inspect.getsource(run_qbacktest) + _inspect.getsource(qvf_sell_tax)
    if "ret_gross" not in src or "gross - cost" not in src:
        raise ContractViolation("백테스트가 비용 전/후를 분리해 산출하지 않습니다 (§8.1 위반).")
    for pat, nm in ((r"QVF_TAX_SCHEDULE", "거래세 이력"),
                    (r"cs_spread|SLIPPAGE_FLOOR_BPS", "실측 스프레드"),
                    (r"IMPACT_K", "시장충격")):
        if not re.search(pat, src):
            raise ContractViolation(f"비용 모델에 {nm} 이 반영되지 않았습니다.")
    if len(QVF_TAX_SCHEDULE) < 5:
        raise ContractViolation("증권거래세를 단일 세율로 처리하고 있습니다 — 10년간 여섯 번 바뀌었습니다.")
    return f"비용 전/후 분리 · 거래세 {len(QVF_TAX_SCHEDULE)}단계 · 스프레드+충격 반영"


@_contract("Q11", "결측을 0 으로 채우지 않는다 — z-score 는 표본 부족 시 NaN 을 유지한다")
def _q11():
    v = pd.Series([1.0, 2.0, np.nan, 4.0, np.inf, -np.inf])
    cells = pd.Series(["A"] * 6)
    z = xsec_z_pct(v, cells, min_n=3)
    if z.isna().sum() < 3:
        raise ContractViolation("±inf 와 NaN 이 결측으로 유지되지 않았습니다.")
    z2 = xsec_z_pct(pd.Series([1.0, 2.0]), pd.Series(["A", "A"]), min_n=8)
    if not z2.isna().all():
        raise ContractViolation("표본 부족 셀의 z 가 NaN 이 아닙니다 — 0 으로 채우면 그 종목이 "
                                "'평균적인 종목'으로 둔갑합니다.")
    return "±inf → NaN · 표본부족 셀 → NaN 유지"


@_contract("Q12", "DART 호출 한도 — 고정 상수가 아니라 실측으로 확정된다")
def _q12():
    s = _inspect.getsource(DartQuota)
    if "limit_observed" not in s:
        raise ContractViolation("DartQuota 가 실측 한도를 기록하지 않습니다.")
    if not re.search(r"def\s+take", s) or re.search(r"self\.n\s*\+\s*k\s*>\s*DART_DAILY_LIMIT", s):
        raise ContractViolation("take() 가 하드코딩된 DART_DAILY_LIMIT 로 소비를 막고 있습니다 — "
                                "남은 호출량을 실시간으로 쓰라는 요구사항 위반입니다.")
    if 'ns["shared"]' not in s:
        raise ContractViolation("DartQuota 저널이 공용 스코프가 아닙니다 — 전략 간 사용량이 "
                                "합산되지 않아 한도를 넘깁니다.")
    if "_confirm_exhaustion" not in s:
        raise ContractViolation("020(일일한도)과 021(요청오류)을 구분하지 않습니다 — "
                                "021 을 한도로 기록하면 거짓 상한이 공용 저널을 오염시킵니다.")
    # ★ 조립본에서 '실효' 상수를 확인한다. 공용 코어(12_ingest_dart_fin)가 헤더보다 뒤에서
    #   DART_DAILY_LIMIT = 19_000 으로 되돌려 놓기 때문에, 선언만 보면 통과하고 실제로는
    #   사용자가 거부한 값이 살아 있다. 계약은 선언이 아니라 실효값을 봐야 한다.
    if int(DART_DAILY_LIMIT) != int(DART_DAILY_LIMIT_HINT):
        raise ContractViolation(
            f"실효 DART_DAILY_LIMIT 이 {DART_DAILY_LIMIT:,} 로 헤더 값 "
            f"{DART_DAILY_LIMIT_HINT:,} 과 다릅니다 — 조립 순서상 뒤에 오는 하드코딩이 "
            f"헤더를 이기고 있습니다. DartQuota 생성 시 되찾아오는지 확인하세요.")
    return f"실측 기반 · 공용 저널 합산 · 020/021 구분 · 실효 한도 {DART_DAILY_LIMIT:,}"


def run_contract_tests(strict: bool = True) -> bool:
    LOG.banner("계약 자동검정 Q1~Q12", "협상 불가 규칙 — 실패하면 실데이터 수집을 시작하지 않습니다")
    rows, ok_all = [], True
    for c in CONTRACTS:
        t0 = time.time()
        try:
            msg = c["fn"]()
            rows.append([c["id"], _trunc(c["name"], 46), "✔ 통과", f"{time.time()-t0:.2f}s",
                         _trunc(str(msg or ""), 40)])
        except Exception as e:                                # noqa
            ok_all = ok_all and not c["critical"]
            rows.append([c["id"], _trunc(c["name"], 46), "✘ 실패", f"{time.time()-t0:.2f}s",
                         _trunc(f"{type(e).__name__}: {e}", 40)])
            LOG.error(f"[{c['id']}] {c['name']} — {type(e).__name__}: {e}")
    LOG.table(rows, ["ID", "계약", "판정", "소요", "비고"], ["c", "l", "c", "r", "l"], maxw=48)
    if not ok_all:
        msg = ("계약 검정에 실패했습니다. 이 규칙들은 결과의 유효성을 결정하므로 "
               "우회하지 말고 원인을 고치십시오.")
        if strict:
            raise ContractViolation(msg)
        LOG.error(msg)
    else:
        LOG.ok("계약 Q1~Q12 전부 통과 — PIT·생존자편향·부호처리·결측허용·비용·캐시 무결성 확인")
    return ok_all



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-I  합성데이터 엔드투엔드 스모크 + 실경로 리허설                                        ║
# ║                                                                                          ║
# ║  두 검증은 서로 다른 것을 본다:                                                            ║
# ║   · 스모크  : 네트워크 없이 '계산경로'(피처→스코어→선정→백테스트→리포트)를 증명한다.        ║
# ║   · 리허설 : 네트워크만 가짜로 두고 '수집·정제 함수'를 실물 실행한다.                       ║
# ║  스모크만 믿으면 수집부 한 줄 때문에 수 시간짜리 실행이 2분 만에 죽는다. 반대도 마찬가지다. ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def make_synthetic(n_codes: int = 200, n_quarters: int = 28, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    end = as_ts(BACKTEST_END)
    q_end = [as_ts(f"{y}-{m:02d}-01") for y in range(end.year - 9, end.year + 1)
             for m in REBAL_MONTHS]
    q_end = [d for d in q_end if d <= end][-n_quarters:]
    start = q_end[0] - pd.DateOffset(months=15)
    days = pd.bdate_range(start, end)

    codes = [f"{i:05d}0" for i in range(1, n_codes + 1)]
    sectors = rng.choice(["화학", "전자부품", "건설", "기계", "소프트웨어", "제약"], n_codes)
    quality = rng.normal(size=n_codes)                       # 진짜 알파를 심는다

    listing = [days[0] - pd.DateOffset(years=int(rng.integers(2, 12))) for _ in codes]
    for i in rng.choice(n_codes, size=max(1, n_codes // 14), replace=False):
        listing[i] = days[int(rng.integers(60, len(days) - 300))]
    delist: List[Any] = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(2, n_codes // 12), replace=False):
        delist[i] = days[int(rng.integers(300, len(days) - 30))]

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": listing, "delisting_date": delist,
                        "industry": sectors,
                        "corp_code": [f"C{i+1:07d}" for i in range(n_codes)], "src": "synthetic"})

    px_rows = []
    for i, c in enumerate(codes):
        drift = 0.0004 + 0.0009 * quality[i]
        r = rng.normal(drift, 0.026, len(days))
        p = np.exp(np.cumsum(r)) * float(rng.lognormal(8.6, 0.6))
        vol = rng.lognormal(10.5, 1.0, len(days))
        px_rows.append(pd.DataFrame({
            "code": c, "date": days,
            "open": p * (1 + rng.normal(0, 0.004, len(days))),
            "high": p * (1 + np.abs(rng.normal(0, 0.012, len(days)))),
            "low": p * (1 - np.abs(rng.normal(0, 0.012, len(days)))),
            "close": p, "volume": vol, "amount": p * vol, "src": "synthetic"}))
    px = pd.concat(px_rows, ignore_index=True)
    keep = pd.Series(True, index=px.index)
    for i, c in enumerate(codes):
        m = px["code"] == c
        keep &= ~(m & (px["date"] < listing[i]))
        if pd.notna(delist[i]):
            keep &= ~(m & (px["date"] > delist[i]))
    px = px[keep].reset_index(drop=True)

    fin_rows, sh_rows = [], []
    for i, c in enumerate(codes):
        rev = float(rng.lognormal(24.5, 1.0))
        sh = float(rng.lognormal(16.0, 0.6))
        for q in pd.date_range(start, end, freq="QE"):
            rev *= (1 + 0.015 * quality[i] + rng.normal(0, 0.05))
            sh *= (1 + max(0.0, rng.normal(0.004 - 0.004 * quality[i], 0.01)))
            eq = rev * (0.7 + 0.1 * quality[i])
            fin_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "period_end": q,
                "knowledge_date": q + pd.Timedelta(days=46),
                "revenue_ttm": rev, "cogs_ttm": rev * (0.74 - 0.03 * quality[i]),
                "gross_profit_ttm": rev * (0.26 + 0.03 * quality[i]),
                "op_income_ttm": rev * (0.06 + 0.025 * quality[i]),
                "op_income_q": rev * 0.25 * (0.06 + 0.025 * quality[i]),
                "net_income_ttm": rev * (0.04 + 0.02 * quality[i]),
                "cfo_ttm": rev * (0.07 + 0.025 * quality[i]),
                "capex_ttm": rev * 0.05 * (1 + 0.2 * rng.normal()),
                "rnd_ttm": rev * max(0.005, 0.02 + 0.012 * quality[i]),
                "tax_expense_ttm": rev * 0.012, "pretax_income_ttm": rev * 0.055,
                "assets": rev * 1.5, "liabilities": rev * (0.8 - 0.1 * quality[i]),
                "equity": eq, "capital_stock": eq * 0.4, "cash": rev * 0.12,
                "st_debt": rev * 0.15, "lt_debt": rev * 0.2, "bonds": 0.0, "lease_liab": 0.0,
            })
            sh_rows.append({"corp_code": sec["corp_code"].iloc[i],
                            "bsns_year": int(q.year), "reprt_code": REPRT_CODES["FY"],
                            "shares_issued": sh, "shares_treasury": sh * 0.01,
                            "period_end": q, "knowledge_date": q + pd.Timedelta(days=46)})
    fin = pit_frame(pd.DataFrame(fin_rows), "period_end", "knowledge_date", source="synthetic")
    shares = pit_frame(pd.DataFrame(sh_rows), "period_end", "knowledge_date", source="synthetic")

    cap_rows = []
    for i, c in enumerate(codes):
        for q in q_end:
            cap_rows.append({"code": c, "snap_date": q - pd.Timedelta(days=3),
                             "mktcap": float(rng.lognormal(24.0, 1.2)),
                             "shares": float(rng.lognormal(16.0, 0.6))})
    snaps = pd.DataFrame(cap_rows)

    dis_rows, fact_rows = [], []
    for i, c in enumerate(codes):
        for q in q_end:
            if rng.random() < 0.10 + 0.12 * max(quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i], "stock_code": c,
                                 "rcept_no": sha1_str(c, q)[:14],
                                 "rcept_dt": q - pd.Timedelta(days=20),
                                 "report_nm": "단일판매ㆍ공급계약체결", "event": "supply_contract",
                                 "pblntf_ty": "I"})
            if rng.random() < 0.05 + 0.06 * max(-quality[i], 0):
                dis_rows.append({"corp_code": sec["corp_code"].iloc[i], "stock_code": c,
                                 "rcept_no": sha1_str(c, q, "cb")[:14],
                                 "rcept_dt": q - pd.Timedelta(days=25),
                                 "report_nm": "전환사채권발행결정", "event": "cb_issue",
                                 "pblntf_ty": "B"})
        for y in sorted({d.year for d in q_end}):
            fact_rows.append({
                "corp_code": sec["corp_code"].iloc[i], "bsns_year": y,
                "rcept_no": sha1_str(c, y, "ar")[:14],
                "rcept_dt": as_ts(f"{y}-03-25"), "parse_status": "ok",
                "patents": float(max(0, 10 + 4 * quality[i] + rng.normal(0, 2))),
                "rnd_headcount": float(max(1, 30 + 12 * quality[i] + rng.normal(0, 5))),
                "gov_rnd_facts": float(rng.random() < 0.15 + 0.12 * max(quality[i], 0)),
                "related_sales_ratio": float(np.clip(0.12 - 0.05 * quality[i] + rng.normal(0, 0.06), 0, 0.9)),
                "related_purchase_ratio": float(np.clip(0.08 + rng.normal(0, 0.04), 0, 0.9)),
                "contingent_amt": float(max(0.0, rng.lognormal(20, 1.2))),
                "lawsuit_amt": float(max(0.0, rng.lognormal(18, 1.5))) if rng.random() < 0.2 else 0.0,
                "lawsuit_new": float(rng.random() < 0.08),
                "audit_emphasis": float(rng.random() < 0.06 + 0.05 * max(-quality[i], 0)),
                "major_holder_pct": float(np.clip(0.35 + 0.08 * quality[i] + rng.normal(0, 0.12), 0.02, 0.8)),
                "sect_ip": True, "sect_rnd": True, "sect_related": True, "sect_contingent": True,
                "sect_lawsuit": True, "sect_audit": True, "sect_holder": True})
    dis = pd.DataFrame(dis_rows)
    dis["knowledge_date"] = as_ts_series(dis["rcept_dt"]) + pd.Timedelta(days=1)
    dis = pit_frame(dis, "rcept_dt", "knowledge_date", source="synthetic")
    facts = pd.DataFrame(fact_rows)

    flow_rows = []
    for i, c in enumerate(codes):
        for q in q_end:
            if rng.random() < 0.55:                            # 45% 는 비영 관측이 없다(현실 반영)
                continue
            flow_rows.append({"code": c, "rebal": q,
                              "foreign_net": float(rng.normal(0, 1) * 1e8 * (1 + quality[i])),
                              "inst_net": float(rng.normal(0, 1) * 1e8),
                              "flow_src": "synthetic"})
    flows = pd.DataFrame(flow_rows)

    brokers = MAJOR_BROKERS[:8] + MINOR_BROKERS[:8]
    rep_rows, link_rows, txt_rows, tone_rows = [], [], [], []
    for q in q_end:
        for _ in range(int(rng.integers(60, 140))):
            i = int(rng.integers(0, n_codes))
            b = brokers[int(rng.integers(0, len(brokers)))]
            bid, bname = normalize_broker(b)
            nm = f"애널{int(rng.integers(0, 24)):02d}"
            d = q - pd.Timedelta(days=int(rng.integers(5, 80)))
            uid = sha1_str("syn", codes[i], d, nm)
            tp = float(np.exp(rng.normal(9.6, 0.5)) * (1 + 0.15 * quality[i]))
            rep_rows.append({"report_uid": uid, "source": "synthetic", "src_report_id": uid[:10],
                             "pub_date": d, "category": "company",
                             "title": f"합성{i+1:03d}({codes[i]}) 리포트", "stock_code": codes[i],
                             "stock_name": f"합성{i+1:03d}", "broker_raw": b, "broker_id": bid,
                             "broker_name": bname, "analyst_raw": nm, "target_price": tp,
                             "opinion": "BUY", "pdf_url": None, "detail_url": None,
                             "event_date": d, "knowledge_date": d})
            link_rows.append({"report_uid": uid, "name": nm, "broker_id": bid,
                              "broker_name": bname, "role": "lead", "link_method": "list_field",
                              "link_conf": 0.98, "pub_date": d, "stock_code": codes[i],
                              "target_price": tp, "opinion": "BUY", "name_norm": nm,
                              "analyst_id": sha1_str("analyst", bid, nm)[:14]})
            txt_rows.append({"report_uid": uid, "pub_date": d, "broker_id": bid,
                             "stock_code": codes[i], "text": "합성 본문", "n_sent": 20,
                             "is_irc": float(rng.random() < 0.05)})
            tone_rows.append({"report_uid": uid, "pub_date": d, "stock_code": codes[i],
                              "tone": float(np.clip(0.15 * quality[i] + rng.normal(0, 0.3), -1, 1)),
                              "n_sent": 20, "model_epoch": as_ts(f"{d.year}-01-01")})
    rep = pd.DataFrame(rep_rows)
    links = pd.DataFrame(link_rows)
    rtext = pd.DataFrame(txt_rows)
    tone = pd.DataFrame(tone_rows)

    return {"sec": sec, "px": px, "fin": fin, "shares": shares, "snaps": snaps,
            "dis": dis, "facts": facts, "flows": flows, "reports": rep, "links": links,
            "rtext": rtext, "tone": tone, "quality": quality}


def _assemble_panel(S: dict, cal: pd.DataFrame, flows: pd.DataFrame) -> Tuple[pd.DataFrame, Any]:
    """합성/실데이터 공통 조립 경로. 스모크와 본 실행이 같은 코드를 타야 검증에 의미가 있다."""
    uni = Universe(S["sec"], pd.DataFrame(columns=["snap_date", "code", "market"]), S["px"])
    cap = build_cap_panel(cal, S["px"], S["snaps"], S["shares"], S["sec"])
    adtv = build_adtv_panel(cal, S["px"])
    G = build_universe_grid(uni, cal, cap, adtv, S["sec"])
    fq = build_quarterly_fundamentals(S["fin"], S["shares"])
    G = attach_fundamentals_q(G, fq, S["sec"])
    U = select_u1000(G)
    U = build_sector_cells(U)
    U = axis_V(U)
    U = axis_Q(U)
    U = axis_F(U, flows)
    U = build_nonfin_panel(U, S["facts"], S["dis"], fq, S["sec"])
    tp = build_tp_revision(S["links"], U, cal)
    U = U.merge(tp[["code", "rebal", "tp_revision"]], on=["code", "rebal"], how="left")
    tpanel = build_tone_panel(S["tone"], U, cal, exclude_irc=IRC_EXCLUDE, T=S.get("rtext"))
    U = U.merge(tpanel[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                on=["code", "rebal"], how="left")
    U["mom12_1"] = np.nan
    U = orthogonalize_tone(U)
    U = build_exclusion_flags(U)
    U = apply_filter3a(U)
    return downcast_q(U), uni


def run_selftest(full_chain: bool = False) -> bool:
    LOG.banner("① 합성데이터 엔드투엔드 스모크",
               "실데이터 수집 전에 계산경로 전체를 증명한다 (수십 초)"
               + (" · full_chain: 실험·강건성·보고서까지 전부 실행" if full_chain else ""))
    t0 = time.time()
    keep = LOG.min
    try:
        S = make_synthetic()
        LOG.info(f"합성 데이터: 종목 {len(S['sec'])} · 일봉 {len(S['px']):,} · "
                 f"재무 {len(S['fin']):,} · 리포트 {len(S['reports']):,} · 수급 {len(S['flows']):,}")
        set_trading_days(S["px"])
        cal = qvf_rebal_calendar(S["px"], BACKTEST_START, BACKTEST_END)
        P, uni = _assemble_panel(S, cal, S["flows"])
        # ★ 합성 유니버스는 200종목뿐이라 U200_N(=200) 을 그대로 쓰면 U-200 이 곧 U-1000 이
        #   되어 3변형이 항상 동일해진다(중복률 1.000). 그러면 §5.6/§9-C3 경로가 실제로
        #   검증되지 않는다. 유니버스 크기에 비례해 줄여 '진짜 부분집합'으로 만든다.
        _u_avg = float(P.groupby("rebal", observed=True).size().mean())
        _n200 = int(max(20, min(U200_N, round(_u_avg * 0.35))))
        P = build_u200(P, variants=VARIANTS, n=_n200)
        set_delist_map(uni.delisting_map())
        ep = build_exec_prices(cal, S["px"])
        fwd = build_forward_returns(ep, cal, uni.delisting_map(), S["px"])

        cmp_res = report_variant_comparison(P, VARIANTS, rep_cov=P[["code", "rebal", "n_reports"]])
        for v in VARIANTS:
            P = apply_filter2(P, v)
        verify_missing_tolerance(P, "VQ")
        P["_sel"] = build_final_selection(P, "VQ", stage="full")
        bt = run_qbacktest(P, cal, "_sel", fwd, label="SMOKE")
        st = qperf_stats(bt["returns"])
        dur = time.time() - t0
        ok = (len(P) > 0 and len(bt["returns"]) > 0 and bool(st) and
              np.isfinite(st.get("CAGR", np.nan)))
        LOG.table([["패널 행수", f"{len(P):,}"],
                   ["U-1000 평균", f"{P.groupby('rebal', observed=True).size().mean():,.0f}"],
                   ["백테스트 분기수", f"{len(bt['returns'])}"],
                   ["평균 보유종목", f"{st.get('평균종목수', float('nan')):.1f}"],
                   ["합성 CAGR(비용후)", f"{st.get('CAGR', float('nan'))*100:+.2f}%"],
                   ["합성 Sharpe", f"{st.get('Sharpe', float('nan')):.3f}"],
                   ["소요시간", f"{dur:.2f}초"]],
                  ["항목", "값"], ["l", "r"],
                  title="스모크 결과 (성과 수치는 의미 없음 — 배관 검증용)")
        if not ok:
            LOG.error("스모크 실패 — 실데이터 수집 전에 계산경로를 먼저 고쳐야 합니다.")
            return False
        LOG.ok(f"스모크 통과 ({dur:.2f}초) — 유니버스→축→필터→백테스트 경로 정상")
        if not full_chain:
            return True

        LOG.warn("아래 수치는 전부 합성 난수 기반입니다. 전략의 실제 성과가 아니라 "
                 "'출력물이 제대로 나오는지'를 보여주는 예행연습입니다. 해석하지 마세요.")
        names = []
        for v in VARIANTS:
            b = run_experiment(P, cal, fwd, v, u200_n=_n200, label=f"{v}-full")
            summarize_experiment(f"{v}-full", b, b["panel"], v, fwd, "1차→2차→3-A")
            names.append(f"{v}-full")
        abl = [("X1", dict(stage="x1"), "1차만"),
               ("X2", dict(use_tone=False, use_nonfin=False), "배제플래그만"),
               ("X3", dict(use_tone=False), "ΔNONFIN만"),
               ("X4", dict(use_rule3a=False), "3-A 없음")]
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, "VQ", u200_n=_n200, label=nm, **kw)
            summarize_experiment(nm, b, b["panel"], "VQ", fwd, desc)
            names.append(nm)
        report_experiment_table([f"{v}-full" for v in VARIANTS], "주 실험 (합성 예행연습)")
        report_experiment_table([n for n, _k, _d in abl], "보조 어블레이션 (합성 예행연습)")
        fdr = report_bh_fdr(names)
        R_subperiod(bt, "SMOKE")
        R_size_quartile(bt, P, "SMOKE")
        report_robustness()
        report_phase0(0.95, 0.60, 0.85, 0.35, 120)
        report_flow_verdict(cmp_res, fdr_pass=fdr)
        report_preregistration_kill([f"{v}-full" for v in VARIANTS], "VQ-full", "X1")
        report_final_holdings(P, "VQ", "_sel", S["sec"], top_n=12)
        LOG.ok("full_chain 예행연습 완료 — 백테스트·성과검증·강건성·판정표가 모두 정상 출력됩니다.")
        return True
    finally:
        LOG.min = keep
        EXPERIMENTS.clear()
        ROBUST_RESULTS.clear()
        PHASE0.clear()


# ── 실경로 리허설 ───────────────────────────────────────────────────────────────────────────
def run_rehearsal(strict: bool = True) -> bool:
    """네트워크만 가짜로 두고 실제 수집·정제 함수를 실행한다.

    ★ 스모크는 합성 '결과물'을 직접 만들어 넣으므로 수집 함수의 코드는 한 줄도 실행하지
      않는다. 실제로 죽는 곳은 대개 거기다(응답 구조 변경, 빈 응답, 컬럼명 오타…).
    """
    LOG.banner("② 실경로 리허설", "네트워크만 가짜로 두고 수집·정제 함수를 실물 실행한다")
    orig_get, orig_post, orig_json = http_get, http_post, http_json
    calls: Counter = Counter()

    def fake_get(url, source="generic", **kw):
        calls[source] += 1
        if kw.get("as_bytes"):
            return b""                        # ZIP/PDF 경로: 빈 바이트 → 실패 분기 검증
        return ""                              # HTML/JSON 경로: 빈 문자열

    def fake_post(url, source="generic", **kw):
        calls[f"{source}:POST"] += 1
        return ""

    def fake_json(url, source="generic", **kw):
        calls[f"{source}:JSON"] += 1
        return None

    checks: List[Tuple[str, str]] = []
    # ★ 키가 비어 있으면 수집 함수 대부분이 첫 줄에서 early-return 해 버려 정작 검증하려던
    #   본문 경로가 한 줄도 실행되지 않는다. 가짜 키를 주입해 '응답이 비었을 때'의 분기를
    #   실제로 태운다. 네트워크는 이미 가짜이므로 외부로 나가는 요청은 없다.
    _keep_key = DART_API_KEY
    globals()["DART_API_KEY"] = _keep_key or "REHEARSAL_FAKE_KEY_0000000000000000000000"
    globals()["http_get"] = fake_get
    globals()["http_post"] = fake_post
    globals()["http_json"] = fake_json
    try:
        cases = [
            ("공시목록 스윕", lambda: fetch_disclosures_qvf("2024-01-01", "2024-03-31")),
            ("DART 주식총수", lambda: fetch_dart_share_counts(["00126380"], [2024])),
            ("사업보고서 본문", lambda: fetch_annual_report_facts(pd.DataFrame(
                {"corp_code": ["00126380"], "bsns_year": [2024],
                 "rcept_no": ["20240101000001"], "rcept_dt": [as_ts("2024-03-25")]}))),
            ("시총 스냅샷", lambda: fetch_krx_cap_snapshots([as_ts("2024-03-01")])),
            ("최대주주 지분율", lambda: fetch_major_holder_stake(pd.DataFrame(
                {"corp_code": ["00126380"], "bsns_year": [2024]}))),
            ("XML→텍스트 판별", lambda: _xml_to_text(b"not a zip at all")),
            ("완료형 사실 판정", lambda: (
                is_completed_fact("2024년 3월 15일 특허 3건을 등록하였다."),
                is_completed_fact("2025년까지 특허 10건을 등록할 예정이다."))),
            ("정형문구 제거", lambda: strip_boilerplate(
                "본 자료는 투자 참고용입니다. 홍길동 연구원 hong@sec.co.kr 실적이 개선되었다.")),
        ]
        for nm, fn in cases:
            try:
                r = fn()
                n = len(r) if hasattr(r, "__len__") else 1
                checks.append((nm, f"✔ 정상 반환 (크기 {n})"))
            except Exception as e:                            # noqa
                checks.append((nm, f"✘ {type(e).__name__}: {str(e)[:60]}"))
        # 완료형 사실 판정의 의미론을 확인 (빈 응답에도 죽지 않는 것과는 별개 문제다)
        if not (is_completed_fact("2024년 3월 15일 특허 3건을 등록하였다.") and
                not is_completed_fact("2025년까지 특허 10건을 등록할 예정이다.")):
            checks.append(("완료형/미래형 구분", "✘ §6.1 추출 원칙 위반"))
        else:
            checks.append(("완료형/미래형 구분", "✔ 미래형 문장 제외 확인"))
        s = strip_boilerplate("본 자료는 투자 참고용입니다. 홍길동 연구원 hong@sec.co.kr 실적이 개선되었다.")
        checks.append(("면책·서명 제거", "✔ 제거됨" if ("연구원" not in s and "@" not in s)
                       else "✘ 잔존 — 증권사 지문 누출 위험"))
    finally:
        globals()["http_get"] = orig_get
        globals()["http_post"] = orig_post
        globals()["http_json"] = orig_json
        globals()["DART_API_KEY"] = _keep_key

    LOG.table([[nm, res] for nm, res in checks], ["수집·정제 함수", "결과"], ["l", "l"], maxw=64)
    bad = [nm for nm, r in checks if r.startswith("✘")]
    if bad:
        msg = f"리허설 실패: {bad} — 실데이터 수집을 시작하면 같은 지점에서 죽습니다."
        if strict:
            raise RuntimeError(msg)
        LOG.error(msg)
        return False
    LOG.ok(f"리허설 통과 — 빈 응답·비정상 응답에도 수집부가 죽지 않고 폴백합니다 "
           f"(가짜 호출 {sum(calls.values())}건)")
    return True



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — §11 실행 순서 [1]~[15]                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크만 띄운다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENV["colab"]:
        try:
            from google.colab import files as _f              # type: ignore
            for p in paths:
                _safe_print(f"⬇  다운로드 시작: {os.path.basename(p)}")
                _f.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML             # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                html.append(f"<div>· {os.path.basename(p)} — 용량이 커서 경로로 안내: "
                            f"<code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                        f"⬇ {os.path.basename(p)} ({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def build_momentum(cal: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """12-1 모멘텀 (직전 1개월 제외 12개월 수익률) — ΔTONE 직교화 설명변수."""
    px = px_daily[["code", "date", "close"]].copy()
    px["date"] = as_ts_series(px["date"])
    px = px.dropna(subset=["code", "date", "close"]).sort_values("date", kind="stable")
    R = px.rename(columns={"date": "px_date"})
    out = []
    for r in cal.itertuples(index=False):
        sd = as_ts(r.signal_date)
        anchors = {"p1": sd - pd.DateOffset(months=1), "p12": sd - pd.DateOffset(months=12)}
        L = pd.DataFrame({"code": sorted(px["code"].unique())})
        vals = {}
        for k, dt in anchors.items():
            LL = L.assign(t=dt).sort_values("t", kind="stable")
            M = pd.merge_asof(LL, R, left_on="t", right_on="px_date", by="code",
                              direction="backward", tolerance=pd.Timedelta(days=20))
            vals[k] = M.set_index("code")["close"]
        m = (vals["p1"] / vals["p12"] - 1.0).rename("mom12_1").reset_index()
        m["rebal"] = r.rebal
        out.append(m)
    if not out:
        return pd.DataFrame(columns=["code", "rebal", "mom12_1"])
    return downcast_q(pd.concat(out, ignore_index=True))


def collect_core(cal_hint: Optional[pd.DataFrame] = None) -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지'를 남긴다."""
    ctx: Dict[str, Any] = {}
    months = month_range(as_ts(BACKTEST_START) - pd.DateOffset(months=18), BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · PIT 유니버스 입력", "L1", budget_s=900):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    with PIPE.stage("L1.PX", "가격 · 거래대금 (폴백 체인)", "L1", budget_s=2400):
        KRX.login()
        px = fetch_prices(ctx["sec"]["code"].tolist(),
                          (as_ts(BACKTEST_START) - pd.DateOffset(months=18)).strftime("%Y-%m-%d"),
                          BACKTEST_END)
        ctx["px"] = px
        set_trading_days(px)

    with PIPE.stage("L1.CAL", "분기 리밸런싱 캘린더 (§4)", "L1", budget_s=60):
        ctx["cal"] = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.CAP", "PIT 시가총액 스냅샷", "L1", budget_s=900, critical=False):
        ctx["snaps_cap"] = fetch_krx_cap_snapshots(list(as_ts_series(ctx["cal"]["signal_date"])))

    with PIPE.stage("L1.DART", "DART 재무 · 주식총수", "L1", budget_s=3600, critical=False):
        corps = ctx["sec"]["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(as_ts(BACKTEST_START).year - 4, as_ts(BACKTEST_END).year + 1))
        multi = fetch_dart_multi_accounts(corps, years)
        fs = fetch_dart_financials(corps, years)
        fin = tidy_financials(merge_financial_tiers(fs, multi))
        ctx["fin"] = apply_t_plus_1(fin, "재무제표")
        ctx["shares"] = fetch_dart_share_counts(corps, years)
        if len(ctx["fin"]):
            PIT.register("dart_financials", ctx["fin"], key_cols=["corp_code"])

    with PIPE.stage("L1.DIS", "DART 공시목록 스윕 (A·B·F·I)", "L1", budget_s=2400, critical=False):
        ctx["dis"] = fetch_disclosures_qvf(BACKTEST_START, BACKTEST_END)

    with PIPE.stage("L1.FLOW", "외국인·기관 순매수 (§5.4)", "L1", budget_s=1800, critical=False):
        ctx["flows"] = fetch_flow_netbuy(ctx["cal"], ctx["px"], window=FLOW_WINDOW_DAYS)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=5400, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. 사용자의 명시적 "
                 "지시에 따라 수집하되 보수적 속도로 제한합니다. PDF 원문은 증권사 저작물이므로 "
                 "로컬 캐시/분석 용도로만 사용하세요.")
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
                    LOG.ok(f"PDF 본문에서 목표주가 {int(fill.sum()):,}건 추가 확보")
            VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                            source="hankyung+naver")
        A, L = build_analyst_ledger(rep)
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
    ctx.setdefault("reports", pd.DataFrame())
    ctx.setdefault("links", pd.DataFrame())
    ctx.setdefault("analysts", pd.DataFrame())
    return ctx


def build_panel_pass1(ctx: dict, cal: pd.DataFrame, flows: pd.DataFrame) -> Tuple[pd.DataFrame, Any]:
    """[2]~[5] — 유니버스 · V/Q/F 축 · 1차필터까지. DART 본문 사실은 아직 필요하지 않다."""
    uni = Universe(ctx["sec"], ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                   ctx["px"])
    cap = build_cap_panel(cal, ctx["px"], ctx.get("snaps_cap", pd.DataFrame()),
                          ctx.get("shares", pd.DataFrame()), ctx["sec"])
    adtv = build_adtv_panel(cal, ctx["px"])
    G = build_universe_grid(uni, cal, cap, adtv, ctx["sec"])
    fq = build_quarterly_fundamentals(ctx.get("fin", pd.DataFrame()), ctx.get("shares", pd.DataFrame()))
    ctx["fq"] = fq
    G = attach_fundamentals_q(G, fq, ctx["sec"])
    U = select_u1000(G)
    U = build_sector_cells(U)
    U = axis_V(U)
    U = axis_Q(U)
    U = axis_F(U, flows)
    U = build_u200(U, variants=VARIANTS, n=U200_N)
    return downcast_q(U), uni


def build_panel_pass2(P: pd.DataFrame, ctx: dict, cal: pd.DataFrame) -> pd.DataFrame:
    """[6]~[10] — DART 하드팩트 · TONE · 2차필터 입력 · 3-A 규칙."""
    P = build_nonfin_panel(P, ctx.get("facts", pd.DataFrame()), ctx.get("dis", pd.DataFrame()),
                           ctx.get("fq", pd.DataFrame()), ctx["sec"])
    P = attach_major_holder(P, ctx.get("holder", pd.DataFrame()), ctx["sec"])
    mom = build_momentum(cal, ctx["px"])
    P = P.merge(mom, on=["code", "rebal"], how="left")
    tp = build_tp_revision(ctx.get("links", pd.DataFrame()), P, cal)
    P = P.merge(tp[["code", "rebal", "tp_revision"]], on=["code", "rebal"], how="left")
    tpanel = build_tone_panel(ctx.get("tone", pd.DataFrame()), P, cal,
                              exclude_irc=IRC_EXCLUDE, T=ctx.get("rtext"))
    P = P.merge(tpanel[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                on=["code", "rebal"], how="left")
    P = orthogonalize_tone(P)
    P = build_exclusion_flags(P)
    P = apply_filter3a(P)
    return downcast_q(P)


def compute_phase0(P: pd.DataFrame, ctx: dict, parse_rate: float) -> dict:
    fin_cov = float(col(P, "equity").notna().mean()) if len(P) else float("nan")
    obs = P[["foreign_net", "inst_net"]].notna().any(axis=1) if "foreign_net" in P.columns \
        else pd.Series(False, index=P.index)
    flow_cov = float(obs.mean()) if len(P) else float("nan")
    u200_any = pd.Series(False, index=P.index)
    for v in VARIANTS:
        if f"u200_{v}" in P.columns:
            u200_any |= P[f"u200_{v}"].fillna(False).astype(bool)
    sub = P[u200_any]
    rep_cov = float((pd.to_numeric(col(sub, "n_reports"), errors="coerce").fillna(0) > 0).mean()) \
        if len(sub) else float("nan")
    pair = float("nan")
    if len(sub) and "n_reports" in sub.columns:
        s = sub[["code", "rebal", "n_reports"]].copy()
        s["has"] = pd.to_numeric(s["n_reports"], errors="coerce").fillna(0) > 0
        s = s.sort_values(["code", "rebal"], kind="stable")
        prev = s.groupby("code", observed=True)["has"].shift(1)
        pair = float((s["has"] & prev.fillna(False)).groupby(s["rebal"]).sum().mean())
    return report_phase0(fin_cov, flow_cov, parse_rate, rep_cov, pair)


def main() -> dict:
    t_all = time.time()
    global VAULT, DQUOTA, DBUDGET
    LOG.banner(f"QVF-FUNNEL v1.0 — {STRATEGY_NAME}",
               f"백테스트 {BACKTEST_START} ~ {BACKTEST_END} · 분기 리밸런싱 · 빌드 {BUILD_VERSION}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]], ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 / CPU {N_CPU} " +
                        ("프로세스(fork)" if CAN_FORK else "스레드(fork 불가 → 폴백)")],
               ["실행 모드", RUN_MODE], ["시드", str(SEED)],
               ["선택 패키지", ", ".join(k for k, v in OPT.items() if v) or "없음"]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "캐시 연결 (드라이브 쓰기 + 로컬 미러 읽기)", "L0", budget_s=600):
        root, mode, mirrors = qvf_resolve_roots()
        VAULT = QVFVault(root, mode, mirrors)
        globals()["VAULT"] = VAULT
        VAULT.report_roots()
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"쓰기 루트 여유 공간 {free:.1f} GB")
            if free < 3:
                LOG.warn("여유 공간이 3GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        # ★ 캐시 루트·미러를 스캔 대상에 넣지 않는다. 그 안의 파일은 이미 인덱스에 있고,
        #   blob 은 내용해시 2단이라 드라이브 FUSE 에서 열거만 수 시간이다(실제로 여기서 멈췄다).
        #   외부에 모아둔 리포트 폴더만 스캔한다. 상대경로는 드라이브 루트 기준으로 푼다.
        _base = os.path.dirname(VAULT.root)
        adopt_dirs = [d if os.path.isabs(d) else os.path.join(_base, d)
                      for d in GDRIVE_ADOPT_DIRS]
        VAULT.adopt_scan(adopt_dirs)
        DQUOTA = DartQuota(VAULT)
        globals()["DQUOTA"] = DQUOTA
        globals()["DBUDGET"] = DQUOTA       # 공용 코어(dart_api)가 참조하는 이름에 주입
        DQUOTA.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정 Q1~Q12", "L0", budget_s=180):
        run_contract_tests(strict=True)

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0",
                    budget_s=(2400 if RUN_MODE == "SMOKE" else 600)):
        if not run_selftest(full_chain=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 테스트 실패 — 실데이터 수집을 시작하지 않습니다.")

    with PIPE.stage("L0.REHEARSAL", "실경로 리허설 (수집 함수 실물 실행)", "L0", budget_s=600):
        run_rehearsal(strict=True)

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_dataflow_map()
        return {"mode": "SMOKE"}

    ctx = collect_core()
    cal = ctx["cal"]

    with PIPE.stage("L1.AUDIT", "원장 무결성 감사 (보고서↔애널리스트↔종목)", "L1",
                    budget_s=180, critical=False):
        audit_linkage(ctx.get("reports", pd.DataFrame()), ctx.get("analysts", pd.DataFrame()),
                      ctx.get("links", pd.DataFrame()))

    with PIPE.stage("L1.PANEL1", "[2]~[5] 유니버스 · V/Q/F 축 · 1차필터", "L1", budget_s=1800):
        P, uni = build_panel_pass1(ctx, cal, ctx.get("flows", pd.DataFrame()))

    with PIPE.stage("L1.FACTS", "[6] DART 하드팩트 (U-200 합집합 대상)", "L1",
                    budget_s=5400, critical=False):
        u_any = pd.Series(False, index=P.index)
        for v in VARIANTS:
            u_any |= P[f"u200_{v}"].fillna(False).astype(bool)
        need_codes = set(P.loc[u_any, "code"].astype(str))
        LOG.info(f"U-200 3변형 합집합 {len(need_codes):,}종목 — DART 본문·리포트 본문 수집을 "
                 f"이 집합으로 한정합니다(전 종목이면 호출량이 수 배가 됩니다).")
        ctx["need_codes"] = need_codes
        dis = ctx.get("dis", pd.DataFrame())
        targets = pd.DataFrame(columns=["corp_code", "bsns_year", "rcept_no", "rcept_dt"])
        if len(dis):
            c2c = (ctx["sec"].dropna(subset=["corp_code"]).drop_duplicates("code")
                   .set_index("code")["corp_code"].astype(str).to_dict())
            want_corp = {c2c[c] for c in need_codes if c in c2c}
            ar = dis[dis["report_nm"].astype(str).str.contains("사업보고서", na=False)].copy()
            if "corp_code" in ar.columns and want_corp:
                ar = ar[ar["corp_code"].astype(str).isin(want_corp)]
            if len(ar):
                ar["bsns_year"] = as_ts_series(ar["rcept_dt"]).dt.year - 1
                targets = ar[["corp_code", "bsns_year", "rcept_no", "rcept_dt"]].drop_duplicates("rcept_no")
        facts, pstats = fetch_annual_report_facts(targets)
        ctx["facts"] = facts
        ctx["parse_rate"] = report_parse_rate(facts, pstats)
        # 3-A 의 '최대주주 지분율 < 15%' 는 하드 규칙인데 본문 표 레이아웃에 따라 추출 실패가
        # 잦다. 실패한 (회사, 연도) 에만 구조화 엔드포인트로 보강한다(전량 호출은 낭비).
        need_h = pd.DataFrame(columns=["corp_code", "bsns_year"])
        if len(facts):
            miss = facts[pd.to_numeric(facts.get("major_holder_pct"), errors="coerce").isna()]
            if len(miss):
                need_h = miss[["corp_code", "bsns_year"]].dropna().drop_duplicates()
        elif len(targets):
            need_h = targets[["corp_code", "bsns_year"]].dropna().drop_duplicates()
        ctx["holder"] = fetch_major_holder_stake(need_h)

    with PIPE.stage("L1.TONE", "[7] 리포트 본문 · TONE 분류기 (확장윈도우)", "L1",
                    budget_s=5400, critical=False):
        T = build_report_text_table(ctx.get("reports", pd.DataFrame()), ctx.get("need_codes"))
        ctx["rtext"] = T
        verify_boilerplate_leak(T)
        lab = build_car_labels(T, ctx["px"])
        ctx["tone"] = build_tone_scores(T, lab)

    with PIPE.stage("L2.PANEL2", "[8]~[10] 하드팩트 · TONE · 배제 · 3-A", "L2", budget_s=1200):
        P = build_panel_pass2(P, ctx, cal)
        VAULT.put_table(f"l1_panel_{STRATEGY_ID}", P, scope="private", domain="features",
                        source="QVF panel")

    with PIPE.stage("L1.EXEC", "체결가 · 보유수익률", "L1", budget_s=600):
        set_delist_map(uni.delisting_map())
        ep = build_exec_prices(cal, ctx["px"])
        fwd = build_forward_returns(ep, cal, uni.delisting_map(), ctx["px"])
        ctx["fwd"] = fwd

    with PIPE.stage("L6.PHASE0", "[1] Phase 0 게이트 (사후 실측)", "L6", budget_s=120,
                    critical=False):
        g = compute_phase0(P, ctx, ctx.get("parse_rate", float("nan")))
        if g.get("fin_cov", {}).get("pass") is False:
            raise KillCriteria(
                f"fin_cov {100*g['fin_cov']['value']:.1f}% < 90% — §2.2 규정상 1차필터가 "
                f"성립하지 않으므로 전략을 중단합니다. DART 재무 콜드빌드를 완료한 뒤 "
                f"재실행하면 정확히 이 지점부터 이어받습니다.")

    with PIPE.stage("L2.CMP", "[5] 3변형 비교 (중간 보고)", "L2", budget_s=300):
        cmp_res = report_variant_comparison(P, VARIANTS, rep_cov=P[["code", "rebal", "n_reports"]])
        ctx["cmp"] = cmp_res

    with PIPE.stage("L2.F2", "[9] 2차필터 · 결측 허용 검증", "L2", budget_s=600):
        for v in VARIANTS:
            P = apply_filter2(P, v)
        for v in VARIANTS:
            verify_missing_tolerance(P, v)

    with PIPE.stage("L2.CAUSAL", "[8] 인과 순서 점검 (§6.4)", "L2", budget_s=180, critical=False):
        ctx["causal"] = check_causal_order(ctx.get("reports", pd.DataFrame()),
                                           ctx.get("dis", pd.DataFrame()), P)

    with PIPE.stage("L3.MAIN", "[11] 주 실험 3개 백테스트", "L3", budget_s=1800):
        main_names = []
        for v in VARIANTS:
            bt = run_experiment(P, cal, fwd, v, label=f"{v}-full", quiet=True)
            summarize_experiment(f"{v}-full", bt, bt["panel"], v, fwd, "1차→2차(DART+TONE)→3-A")
            main_names.append(f"{v}-full")
            ctx[f"bt_{v}"] = bt
        report_experiment_table(main_names, "주 실험 (§8.2) — 1차필터 3변형 × 전체 파이프라인")

    best = max(main_names,
               key=lambda n: (EXPERIMENTS[n]["net"].get("Sharpe", -1e9)
                              if np.isfinite(EXPERIMENTS[n]["net"].get("Sharpe", np.nan)) else -1e9))
    best_v = best.split("-")[0]
    LOG.ok(f"비용 차감 후 Sharpe 기준 최우수 변형: {best} "
           f"(Sharpe {EXPERIMENTS[best]['net'].get('Sharpe', float('nan')):.3f})")

    with PIPE.stage("L3.ABL", "[12] 보조 어블레이션 X1~X4", "L3", budget_s=1800, critical=False):
        abl = [("X1", dict(stage="x1"), "1차만 — 깔때기 자체의 기여"),
               ("X2", dict(use_tone=False, use_nonfin=False), "1차+배제플래그만 — 위험배제 효과"),
               ("X3", dict(use_tone=False), "1차+ΔNONFIN만 — 애널리스트 축 기여"),
               ("X4", dict(use_rule3a=False), "1차+2차, 3-A 없음 — 3-A 기여")]
        abl_names = []
        for nm, kw, desc in abl:
            b = run_experiment(P, cal, fwd, best_v, label=nm, quiet=True, **kw)
            summarize_experiment(nm, b, b["panel"], best_v, fwd, desc)
            abl_names.append(nm)
        report_experiment_table(abl_names, f"보조 어블레이션 (§8.2) — 최우수 변형 {best_v} 기준")

    with PIPE.stage("L5.FDR", "[13] BH-FDR 다중검정 보정", "L5", budget_s=120, critical=False):
        ctx["fdr"] = report_bh_fdr(main_names + abl_names)

    with PIPE.stage("L5.ROBUST", "[13] 강건성 검사 (§8.4)", "L5", budget_s=4 * 3600, critical=False):
        bt_best = ctx.get(f"bt_{best_v}")
        R_subperiod(bt_best, best)
        R_size_quartile(bt_best, P, best)
        R_param_sensitivity(P, cal, fwd, best_v)
        R_weight_scheme(P, cal, fwd, best_v)

        def _rebuild_shift(sh: int, variant: str):
            cal2 = qvf_rebal_calendar(ctx["px"], BACKTEST_START, BACKTEST_END, shift_days=sh)
            fl2 = fetch_flow_netbuy(cal2, ctx["px"], window=FLOW_WINDOW_DAYS)
            P2, uni2 = build_panel_pass1(ctx, cal2, fl2)
            P2 = build_panel_pass2(P2, ctx, cal2)
            ep2 = build_exec_prices(cal2, ctx["px"])
            fwd2 = build_forward_returns(ep2, cal2, uni2.delisting_map(), ctx["px"])
            b = run_experiment(P2, cal2, fwd2, variant, label=f"shift{sh}", quiet=True)
            return qperf_stats(b["returns"])
        R_rebal_shift(_rebuild_shift, best_v)

        if "VQF" in VARIANTS:
            def _rebuild_flow(w: int):
                fl2 = fetch_flow_netbuy(cal, ctx["px"], window=w)
                P2 = axis_F(P.drop(columns=[c for c in ("Z_F", "zF_foreign", "zF_inst",
                                                        "flow_f", "flow_i", "float_cap")
                                            if c in P.columns]), fl2)
                b = run_experiment(P2, cal, fwd, "VQF", label=f"flow{w}", quiet=True)
                return qperf_stats(b["returns"])
            R_flow_window(_rebuild_flow)

        def _rebuild_irc(excl: bool, variant: str):
            tp2 = build_tone_panel(ctx.get("tone", pd.DataFrame()), P, cal,
                                   exclude_irc=excl, T=ctx.get("rtext"))
            P2 = P.drop(columns=[c for c in ("tone_q", "n_reports", "dTONE", "dTONE_resid")
                                 if c in P.columns])
            P2 = P2.merge(tp2[["code", "rebal", "tone_q", "n_reports", "dTONE"]],
                          on=["code", "rebal"], how="left")
            P2 = orthogonalize_tone(P2)
            b = run_experiment(P2, cal, fwd, variant, label=f"irc{int(excl)}", quiet=True)
            return qperf_stats(b["returns"])
        R_irc_split(_rebuild_irc, best_v)
        report_robustness()

    with PIPE.stage("L6.VERDICT", "[14] 수급 축 판정 · 사전등록 폐기조건", "L6", budget_s=120,
                    critical=False):
        ctx["flow_verdict"] = report_flow_verdict(ctx.get("cmp", {}), fdr_pass=ctx.get("fdr"))
        ctx["kill"] = report_preregistration_kill(main_names, best, "X1")

    with PIPE.stage("L6.REPORT", "[15] 최종 산출물", "L6", budget_s=300, critical=False):
        bench = qvf_benchmarks(cal, ctx["px"])
        if bench:
            R = ctx[f"bt_{best_v}"]["returns"].set_index("rebal")["ret"]
            rows = []
            for nm, b in bench.items():
                bb = b.reindex(R.index).fillna(0)
                ex = R.fillna(0) - bb
                _, t = hac_tstat(ex.to_numpy())
                rows.append([nm, f"{float((1+bb).prod()-1)*100:+.1f}%",
                             f"{float((1+R.fillna(0)).prod()-1)*100:+.1f}%",
                             f"{float(ex.mean())*100:+.3f}%p", f"{t:.2f}"])
            LOG.table(rows, ["벤치마크", "벤치 누적", "전략 누적", "분기평균 초과", "HAC t"],
                      ["l", "r", "r", "r", "r"], title=f"[{best}] 벤치마크 대비")
        P["_sel_best"] = build_final_selection(P, best_v, stage="full")
        ctx["holdings_last"] = report_final_holdings(P, best_v, "_sel_best", ctx["sec"])

    with PIPE.stage("L0.PERSIST", "산출물 저장 (공용/전용 인덱스)", "L0", budget_s=600,
                    critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports", STRATEGY_ID)
        os.makedirs(outdir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        for v in VARIANTS:
            b = ctx.get(f"bt_{v}")
            if b is None:
                continue
            p = os.path.join(outdir, f"returns_{v}_{stamp}.csv")
            b["returns"].to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
            VAULT.put_table(f"backtest_returns_{v}", b["returns"], scope="private",
                            domain="backtest", source=STRATEGY_ID)
        h = ctx.get("holdings_last")
        if h is not None and len(h):
            p = os.path.join(outdir, f"holdings_{best_v}_{stamp}.csv")
            h.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
        summ = pd.DataFrame([{"experiment": k, "desc": e.get("desc", ""),
                              **{f"net_{kk}": vv for kk, vv in (e.get("net") or {}).items()},
                              **{f"gross_{kk}": vv for kk, vv in (e.get("gross") or {}).items()},
                              "IC": e.get("IC"), "ICIR": e.get("ICIR"), "p": e.get("p")}
                             for k, e in EXPERIMENTS.items()])
        if len(summ):
            p = os.path.join(outdir, f"experiments_{stamp}.csv")
            summ.to_csv(p, index=False, encoding="utf-8-sig")
            outs.append(p)
            VAULT.put_table("qvf_experiment_summary", summ, scope="private",
                            domain="backtest", source=STRATEGY_ID)
        lp = os.path.join(outdir, f"log_{stamp}.txt")
        atomic_write_text(lp, "\n".join(LOG.buffer))
        outs.append(lp)
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        if DQUOTA:
            DQUOTA.close()
            DQUOTA.report()
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
    LOG.info("§10.1 증거 등급 — 위 표의 모든 수치는 이 백테스트에서 산출된 실측값입니다. "
             "표본은 10년 40분기이며, 그 길이에서 나오는 통계적 불확실성은 방법론적 우려로 "
             "명시합니다. 수치 없는 낙관/비관 주장은 하지 않습니다.")
    offer_download(ctx.get("outputs", []))
    return {"panel": P, "ctx": ctx, "experiments": dict(EXPERIMENTS)}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except KillCriteria as e:
        LOG.banner("⛔ 사전등록 기준으로 중단", "§2.2 / §10.4 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
    except StageFailure as e:
        LOG.banner("실행 중단", "위의 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단. 여기까지 수집된 데이터는 드라이브에 저장되어 있으며 "
                 "재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
            if DQUOTA:
                DQUOTA.close()
        except Exception:
            pass
