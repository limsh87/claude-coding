#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  SHINHAN_EARNINGS_SURPRISE_7F_V1 — 신한 「4분기 서프라이즈 포트폴리오」 7팩터 10년 PIT 백테스트
#
#  원문: 신한투자증권 이정빈 「4분기 서프라이즈 포트폴리오 업데이트」 (2023-01-06)
#  구간: 2016-08 ~ 2026-07 (10년) · 분기 리밸런싱(3/6/9/12월 마지막 거래일) · 상위 30종목 동일가중
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나
#   `python shinhan_7f_earnings_surprise_v1.py` 로 실행해도 동일하게 동작합니다.
#
#   실행 순서(로그에 그대로 출력):
#     [0] 환경·의존성 → 구글드라이브 캐시 연결(공용/전용 인덱스) → 계약 자가검정
#     [1] 합성데이터 엔드투엔드 스모크 (실데이터 수집 전에 계산경로를 먼저 증명)
#     [2] 데이터 수집  (로컬 D드라이브·구글드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [3] 원장 무결성 감사 (보고서 ↔ 애널리스트 ↔ 종목 다중소스 연결)
#     [4] PIT 유니버스(재구성 KOSPI200 + 비교전략용 시총 하위1000) 구축
#     [5] 7팩터 스냅샷 → 표준화 → 합성점수 → 백테스트 (본전략 + 비교전략)
#     [6] 성과 검증표   [7] 강건성 검사   [8] 해석표   [9] 산출물 저장 + 다운로드 링크
#
#  ── 정확모드 vs 재구성모드 (계약 §EXACT/§RECONSTRUCTED — 절대 혼합 금지) ────────────────────
#   EXACT_VENDOR_MODE : FnGuide/신한의 historical composite 또는 표준화 점수+유니버스 마스크가
#                       캐시에 실재할 때만 활성화. 없으면 실행한 척하지 않고
#                       STATUS="EXACT_COMPOSITE_NOT_PUBLICLY_IDENTIFIED" 를 출력한다.
#   RECONSTRUCTED_PUBLIC_MODE (기본) : 공개정보 재구성 규칙(사전고정 z-score·동일가중 30종목).
#                       이 규칙은 '신한 원문 공식'이 아니며 그렇게 표현하지 않는다.
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
#  ⚠ 한경컨센서스·네이버 리서치 페이지는 robots.txt 가 Disallow 입니다. 사용자의 명시적
#    지시에 따라 보수적 속도로만 수집하며, PDF 원문은 증권사 저작물이므로 재배포 금지입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다 (전부 비워도 실행은 됩니다. 키가 없는 소스는
#       건너뛰고 '왜 건너뛰었는지'를 로그에 남깁니다. 조용히 실패하지 않습니다.)
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① KRX 데이터 마켓플레이스 로그인 (가격·시총·수급·지수구성 스냅샷 보강용) ─────────────────
#    발급: https://data.krx.co.kr  →  회원가입(무료) → 그 로그인 ID/비밀번호를 그대로 입력
#    ▶ 2025-12 인증 변경 이후 pykrx 일부 경로가 로그인 세션을 요구합니다.
#    ▶ 비워도 됩니다: 로그인 불필요 경로(FDR GitHub 캐시·marcap·네이버 차트)로 폴백하며
#      백테스트는 정상 동작합니다. 어떤 소스가 쓰였는지는 감사표에 나옵니다.
#    ⚠ 같은 계정을 브라우저/다른 노트북에서 동시에 로그인하지 마세요. KRX 는 중복 로그인 시
#      이전 세션을 강제 종료(CD011)하여 실행 중인 수집이 대량 실패합니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""
KRX_OPENAPI_KEY    = ""   # (선택) KRX 공식 Open API 키 — 시총·주식수 확보용 폴백
#    발급: https://openapi.krx.co.kr → 회원가입 → 마이페이지 [API 인증키 신청](1영업일)
#          → [서비스 이용]에서 쓰려는 API 마다 '이용신청'을 따로 눌러야 승인됩니다
#          (stk_bydd_trd = 유가증권 일별매매정보 / ksq_bydd_trd = 코스닥). JSON 호스트는
#          data-dbg.krx.co.kr 이고 openapi.krx.co.kr 은 발급 포털입니다.
#    ⚠ 이 Open API 에는 **투자자별(기관·외국인) 순매수 엔드포인트가 없습니다**(31개 전수
#      확인). 따라서 F6/F7 은 이 키로 만들 수 없고, 마켓플레이스 세션(위 ①)이 필요합니다.

# ── ② DART 전자공시 OpenAPI (분기 순이익→EPS, 접수일 기반 PIT — F1/F2/F3/F5 프록시의 핵심) ──
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → 즉시 무료 발급
#    ★ 호출량 정책 (v1.1) — 상한을 미리 정해놓고 아끼는 방식을 폐기했습니다.
#      · 20,000 은 "표시용 참고치"일 뿐이며, 코드는 이 숫자로 스스로 멈추지 않습니다.
#      · 멈추는 유일한 조건은 DART 가 실제로 status=020(일일한도 초과)을 돌려줄 때입니다.
#        → 남은 호출량을 실시간으로 재계산해 "쓸 수 있는 만큼" 전부 씁니다.
#      · 시작 전에 '이번 실행에 필요한 호출 수'를 먼저 계산해 표로 보여줍니다.
#        fnlttMultiAcnt 는 corp_code 100개/1호출이라, 종목 2,500개 × 14년 × 4보고서라도
#        25배치 × 56 = 약 1,400회면 끝납니다(한도의 7%). 부족할 일이 없습니다.
#      · 오늘 사용량은 공용 인덱스에 영속 기록되어 같은 키를 쓰는 다른 전략과 합산됩니다.
DART_API_KEY = ""
DART_ADVISORY_DAILY  = 20_000   # 표시용 참고치. 이 값으로 선제 중단하지 않습니다.
DART_STOP_ONLY_ON_020 = True    # True = API 가 실제로 한도초과를 말할 때만 중단(권장)

# ── ③ 구글드라이브 캐시 — ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다 ★★★ ──────────
#    · 인덱스의 진실은 append-only JSONL 저널: 기존 줄을 재기록하지 않으므로 과거 기록이
#      사라질 수 없습니다. index.parquet 은 저널의 파생물이며 재생성 전 반드시 백업합니다.
#    · blob 은 내용해시 경로 → 같은 내용은 재기록 자체가 없고, 삭제 API 는 존재하지 않습니다.
#    · 기존 폴더의 리포트/테이블은 이동·개명 없이 '경로만 등록'(adopt-by-reference)합니다.
#
#    공용 인덱스(_shared)   : 가격/시총/재무/보고서 원장 등 — 다른 전략도 그대로 재사용
#    전용 인덱스(shinhan_7f): 이 전략 고유의 팩터 스냅샷/점수/포트폴리오/리포트
#
#    ★ v1.1: 후보를 "처음 하나만" 쓰지 않습니다. 존재하는 후보를 전부 열어 **읽기는 모든
#      루트에서(로컬 D드라이브 + 구글드라이브 동시), 쓰기는 최우선 루트 하나에만** 합니다.
#      (v1.0 은 D:/tcd_cache 를 먼저 찾으면 거기서 멈춰, 드라이브에만 있던 marcap_YYYY
#       시총 스파인을 못 보고 40개 분기 전부 시총 결손 → 유니버스 붕괴로 이어졌습니다.)
GDRIVE_ROOT_CANDIDATES = [
    "/content/drive/MyDrive/tcd_cache",            # Colab (기존 공용 캐시 — 최우선)
    "~/Google Drive/MyDrive/tcd_cache",            # 로컬 동기화(구글드라이브 데스크톱)
    "~/GoogleDrive/MyDrive/tcd_cache",
    "G:/내 드라이브/tcd_cache", "G:/My Drive/tcd_cache",   # Windows 드라이브 문자 마운트
    "H:/내 드라이브/tcd_cache", "H:/My Drive/tcd_cache",
    "D:/tcd_cache", "D:/GoogleDrive/tcd_cache",           # 로컬 D드라이브 캐시
    "/content/drive/MyDrive/shinhan7f_cache",             # 위가 전부 없으면 새로 만들 위치
]
GDRIVE_SHARED_NS  = "_shared"        # 공용 인덱스 네임스페이스 (기존 규약과 동일 — 호환)
GDRIVE_PRIVATE_NS = "shinhan_7f"     # 전용 인덱스 네임스페이스 (이 전략 고유)

#    ▸ 이미 모아둔 리포트/캐시 폴더 — 재귀 스캔해서 '참조 등록만' 합니다(이동·삭제 없음).
#      경로가 없으면 조용히 건너뜁니다. {DRIVE}는 발견된 드라이브 루트의 부모로 치환됩니다.
GDRIVE_ADOPT_DIRS = [
    "{DRIVE}/TCD_CACHE_V1",            # 다른 전략 버전이 만든 캐시(공용 재활용)
    "{DRIVE}/MIRAE_QUANT_CACHE_V1",    # "
    "{DRIVE}/research", "{DRIVE}/reports", "{DRIVE}/consensus",
    "D:/research", "D:/reports", "D:/consensus", "D:/quant_cache",
]
LOCAL_CACHE_ROOT = "./tcd_cache"     # 드라이브를 못 찾을 때의 로컬 폴백(기존 규약과 동일)

#    ▸ 시가총액 스파인(marcap_YYYY.parquet 류)을 찾을 추가 경로. 위 루트들 아래는 자동으로
#      재귀 탐색하므로 보통 비워둬도 됩니다. 파일을 딴 데 두셨다면 폴더만 적으세요.
MARCAP_EXTRA_DIRS = [
    "D:/marcap", "D:/marcap/data", "D:/tcd_cache/_shared/table",
    "~/marcap/data", "{DRIVE}/marcap", "{DRIVE}/marcap/data",
]
MARCAP_SCAN_MAX_DEPTH = 5        # 루트 아래 재귀 탐색 깊이 상한(윈도우 대용량 드라이브 보호)

#    ▸ ★ marcap 공개 데이터셋 자동 확보 (v1.1.1 — KRX 차단 대응의 핵심)
#      marcap(FinanceData/marcap)은 1995년~현재의 **일별 전종목 시가총액·상장주식수·시세**를
#      상장폐지 종목까지 포함해 공개하는 데이터셋입니다. 이것만 있으면
#        · 시총 스파인(PIT 정확)      · 10년 일봉(폐지종목 포함 → 생존자편향 제거)
#        · F6/F7 의 분모(시총)        · 유니버스 상위200 / 하위1000
#      을 **KRX 를 한 번도 찌르지 않고** 만들 수 있습니다.
#      로컬·드라이브에서 파일을 못 찾으면 필요한 연도만 1회 내려받아 공용 인덱스에 저장하고,
#      이후 실행은 네트워크 0회로 재사용합니다. (연도당 수~수십 MB)
MARCAP_AUTO_DOWNLOAD = True
#      실측 확인(2026-08): data/marcap-YYYY.parquet 가 정답입니다(csv.gz 는 404).
#      2016년 파일 = 19.0MB · 537,665행 · 2,279종목 · Marcap/Stocks 결측 0.
MARCAP_GH_TEMPLATES = [
    "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet",
    "https://raw.githubusercontent.com/FinanceData/marcap/main/data/marcap-{y}.parquet",
    "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.csv.gz",
]

# ── ④ 백테스트 구간 · 전략 파라미터 (계약 사전고정 — 성과를 보고 바꾸지 마세요) ──────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"
TOP_N          = 30          # 상위 30종목 동일가중 (계약)
REBAL_MONTHS   = (3, 6, 9, 12)   # 3/6/9/12월 마지막 KRX 거래일 신호 → 익거래일 시가 체결 (계약)
MIN_ELIGIBLE   = 10          # 적격종목이 이보다 적은 분기는 편입 보류(현금) — 로그에 명시
K200_SIZE      = 200         # 재구성 KOSPI200 규모
CMP_BOTTOM_N   = 1000        # 비교전략: 시가총액 하위 1000종목 유니버스
INCLUDE_COMPARISON = True    # 하위1000 비교전략 백테스트 수행 여부
#    ★ 특정 팩터의 입력을 어떤 소스로도 얻지 못했을 때(예: KRX 차단으로 기관·외국인 수급이
#      전멸) 계약 baseline 은 '7팩터 모두 유효'를 요구하므로 적격종목이 0이 되어 백테스트
#      자체가 성립하지 않습니다. 그때 아무 결과도 못 보는 대신, **가용 팩터만으로 계산한
#      진단용 런**을 별도 라벨로 함께 출력합니다.
#      ⚠ 이것은 계약 baseline 이 아니며 Primary 를 대체하지 않습니다(라벨·STATUS 로 명시).
ALLOW_DEGRADED_DIAGNOSTIC = True

# ── ⑤ 비용 모델 (cost_schedule.parquet 로 그대로 출력됩니다) ────────────────────────────────
COMMISSION_BPS = 1.5         # 편도 수수료(개인 온라인)
SLIPPAGE_K     = 0.10        # 제곱근 시장충격 계수 (참여율 기반)
ACCOUNT_KRW    = 100_000_000 # 슬리피지 참여율 계산용 계좌 규모 가정

# ── ⑥ 애널리스트 리포트 수집 (한경컨센서스 + 네이버리서치 — F4/F5 프록시 입력) ───────────────
RESEARCH_COLLECT      = True     # False 면 캐시(로컬/드라이브)에 있는 것만 사용
RESEARCH_SOURCES      = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF = False    # True 면 PDF 원문까지 저장(애널리스트/목표주가 추출 정확도↑, 시간·용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한
#    ★ 연도별 '충분' 판정 기준 — 행 수가 아니라 **F4 에 실제로 쓸 수 있는 행 수**
#      (목표주가 AND 애널리스트가 모두 있는 리포트)를 셉니다. 네이버 리서치는 이 둘을
#      주지 않아, 행 수로 세면 '충분'으로 오판되어 한경컨센서스를 영구히 수집하지 않고
#      F4 가 40개 분기 전부 결측이 됩니다(실운행에서 발생).
RESEARCH_MIN_USABLE_PER_YEAR = 800

# ── ⑦ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 403/429 가 보이면 8 이하로.
#    ★ krx 는 1.0 qps 로 낮췄습니다. KRX 는 과거에 pykrx 트래픽을 표적 차단한 이력이 있고,
#      마켓플레이스 bld 는 초당 1회 이하가 안전선입니다(차단되면 전 경로가 함께 죽습니다).
#    ★ 실운행 2회차에서 KRX 가 "자동화 대량조회"로 이 IP 를 7일 차단했습니다(1 qps · 160회).
#      그래서 krx 는 0.5 qps(2초 간격)로 낮추고, 실행당 총 호출 상한도 둡니다.
RATE_LIMIT_QPS = {"dart": 8.0, "hankyung": 2.5, "naver": 3.0, "krx": 0.5,
                  "krx_api": 1.0, "kind": 2.0, "generic": 3.0}
KRX_MAX_CALLS_PER_RUN = 300   # 이번 실행의 data.krx.co.kr 호출 상한(차단 예방)
MEM_BUDGET_GB  = 20.0   # 계약 peak RAM<=24GB 목표 — 초과 예상 시 청크 처리로 전환

# ── ⑦-b 가격 수집 규율 (★ v1.1 병목 제거 — "쓸데없는 가격조회 반복" 금지 규칙) ───────────────
#    v1.0 의 병목 원인 3가지를 각각 끊습니다.
#      ① 유니버스를 모르는 상태에서 마스터 전체(5,398종목: 채권·워런트·스팩·우선주·외국주
#         포함)의 일봉을 먼저 받았다  → v1.1 은 시총 스파인 → 유니버스 → **그 종목만** 수집.
#      ② 결손 판정이 상장일/폐지일을 무시했다. 2020년 상장 종목은 2016년 데이터가 "없는 게
#         정상"인데 매 실행마다 백필 대상으로 올라가 영구 재조회 → 2,140종목 전량 실패 반복.
#         v1.1 은 [상장일, 폐지일] ∩ [구간] 안의 거래일 커버리지로만 판정합니다.
#      ③ 음성 캐시가 체인 뒤에 있었고 30일 고정이었다 → v1.1 은 체인 앞에서 막고,
#         실패 횟수에 따라 7/30/120/365일로 늘리며 4회 실패는 영구 제외합니다.
PRICE_COVERAGE_MIN   = 0.90   # 기대 거래일의 90% 이상 있으면 '충분' — 재조회하지 않는다
PRICE_NEG_BACKOFF_D  = (7, 30, 120, 365)   # 실패 1/2/3/4회째의 재시도 유예(일)
PRICE_NEG_PERMANENT  = 4      # 이 횟수 이상 실패하면 영구 제외(구조적 미존재로 확정)
PRICE_NEG_PERMANENT_TTL_D = 365  # 단, 영구제외도 이 기간 뒤에는 반드시 재시도(소스 복구 대비)
ALLOW_YFINANCE       = False  # ★ 기본 OFF. v1.0 의 36분 중 대부분이 yfinance 404 폭풍이었다.
YFINANCE_MAX_CALLS   = 200    # ON 으로 켜도 이 횟수까지만 (최종 폴백은 항상 유한해야 한다)
PRICE_EXTRA_MARGIN_M = 15     # 팩터 룩백용 선행 개월(신호일 이전 데이터 필요분)

# ── ⑦-c 시가총액 스파인 소스 우선순위 (앞에서부터 시도, 성공분은 공용 캐시에 영속) ───────────
#    "marcap"    로컬/드라이브 marcap_YYYY.parquet (폐지종목 포함 · 네트워크 0회 · 최우선)
#    "cache"     공용 캐시 krx_market_cap_monthly (이전 실행이 쌓아둔 단면)
#    "krx_bld"   data.krx.co.kr 전종목시세 bld (로그인 세션) — 시점당 1호출, PIT 정확
#    "krx_api"   data-dbg.krx.co.kr Open API (KRX_OPENAPI_KEY) — 로그인 불필요, PIT 정확
#                ★ 2025-12 이후 bld 계열은 전부 로그인이 필요해졌습니다. Open API 키는
#                  별도 무료 발급이며 로그인 세션과 독립적으로 동작해 이중 안전망이 됩니다.
#    "pykrx"     pykrx get_market_cap_by_ticker — 시점당 2호출, PIT 정확(역시 로그인 필요)
#    "fdr_apx"   FDR 현재 상장주식수 × PIT 종가 (근사 — 주식수 변동 종목은 오차, 감사표에 표기)
#    "liq_proxy" 20일 평균 거래대금 순위 (캐시만 사용 · 최후의 수단 · 반드시 등급 표기)
MCAP_SPINE_SOURCES = ["marcap", "cache", "krx_bld", "krx_api", "pykrx", "fdr_apx",
                      "liq_proxy"]

# ── ⑧ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전 출력물 예행연습(네트워크·키 불필요, 1~2분). 처음엔 이걸로.
#    "FULL"  : 스모크 → 실데이터 수집(캐시 우선) → 백테스트 → 강건성 (기본)
#    "CACHED": 스모크 → 캐시만 사용(신규 수집 0건 · network=0) → 백테스트  ← 계약 timed run
RUN_MODE = "FULL"
PROMPT_FOR_KEYS = True   # 대화형 환경에서 키가 비어 있으면 1회 입력 프롬프트(Enter=건너뜀)

SEED = 20230106          # 결정성: 모든 난수는 이 시드에서 파생 (원문 보고서 발간일)
VERBOSE = True

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "shinhan_7f"
STRATEGY_NAME = "SHINHAN_EARNINGS_SURPRISE_7F_V1"
RECON_LABEL   = "SHINHAN_7F_RECONSTRUCTED"      # 재구성모드 공식 명칭 (계약)
CMP_LABEL     = "SHINHAN_7F_SMALLCAP1000_CMP"   # 비교전략(시총 하위1000) 명칭
DEGRADED_LABEL = "SHINHAN_7F_DEGRADED_DIAGNOSTIC"  # 팩터 결손 시 진단용(계약 baseline 아님)
BUILD_VERSION = "1.1.1"   # v1.1.1: KRX 차단 대응(marcap 자동확보·차단감지) + 감사 15건 반영
SLA_SECONDS   = 14_400                           # 계약 4시간 SLA (cached 구간 기준 판정용)

# 원문 2022-4Q 공개 종목 테이블(발췌) — validation fixture 전용.
# ★ 백테스트 신호로 사용 금지(계약). 우리 2022-Q4 선정과의 겹침 개수만 보고한다.
VALIDATION_2022Q4_NAMES = ["오리온", "제일기획", "하이브", "엔씨소프트",
                           "SK이노베이션", "한화솔루션", "포스코케미칼"]


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트 / 키 입력                             ║
# ║  입력: 없음   출력: 전역 ENV, 임포트된 모듈   실패 시: 원인+설치명령을 한글로 출력 후 중단  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, textwrap, traceback
import random, shutil, platform, subprocess, warnings, threading, unicodedata
import datetime as _dt
from collections import defaultdict, Counter, OrderedDict
from dataclasses import dataclass, field
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, urljoin, quote, unquote

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

# 윈도우 콘솔(cp949)은 罫線문자·✔✘ 를 인코딩하지 못한다 → stdout 을 UTF-8 로 재설정,
# 안 되면 아래 _safe_print 가 ASCII 로 낮춘다. (주피터는 UTF-8 이라 무해)
for _s in ("stdout", "stderr"):
    try:
        _st = getattr(sys, _s, None)
        if _st is not None and hasattr(_st, "reconfigure"):
            _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_ASCII_FALLBACK = str.maketrans({
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "═": "=", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "─": "-", "│": "|",
    "┼": "+", "┬": "+", "┴": "+", "├": "+", "┤": "+",
    "✔": "OK", "✘": "X", "⚠": "!", "★": "*", "▶": ">", "▷": ">", "⬇": "v",
    "…": "...", "·": ".", "×": "x", "Δ": "d", "≥": ">=", "≤": "<=", "≈": "~", "⛔": "STOP",
})


def _safe_print(*args, **kw):
    """어떤 콘솔에서도 죽지 않는 print."""
    try:
        print(*args, **kw)
    except UnicodeEncodeError:
        try:
            print(*[str(a).translate(_ASCII_FALLBACK) for a in args], **kw)
        except Exception:
            enc = (getattr(sys.stdout, "encoding", None) or "ascii")
            print(*[str(a).encode(enc, "replace").decode(enc, "replace") for a in args], **kw)


def _detect_env() -> Dict[str, Any]:
    info = {"colab": False, "ipython": False, "interactive": False}
    try:
        from IPython import get_ipython           # noqa
        ip = get_ipython()
        if ip is not None:
            info["ipython"] = True
            info["interactive"] = True
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

# ── 키 입력 프롬프트 (상단 설정이 비어 있고 대화형이면 1회 요청, Enter=건너뜀) ────────────────
def _prompt_keys():
    global KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW, DART_API_KEY
    if not PROMPT_FOR_KEYS or not ENV["interactive"] or RUN_MODE == "SMOKE":
        return
    if os.environ.get("SH7F_NO_PROMPT"):          # 자동화 실행에서 프롬프트 차단용
        return
    try:
        import getpass
        if not KRX_MARKETPLACE_ID:
            v = input("KRX 마켓플레이스 ID (data.krx.co.kr 회원 ID, Enter=건너뜀): ").strip()
            if v:
                KRX_MARKETPLACE_ID = v
                KRX_MARKETPLACE_PW = getpass.getpass("KRX 마켓플레이스 비밀번호: ").strip()
        if not DART_API_KEY:
            v = getpass.getpass("DART OpenAPI 인증키 (opendart.fss.or.kr, Enter=건너뜀): ").strip()
            if v:
                DART_API_KEY = v
    except Exception:
        pass                                       # 비대화형/파이프 실행이면 조용히 진행


_prompt_keys()

# ── 의존성 ──────────────────────────────────────────────────────────────────────────────────
_REQUIRED = [
    ("numpy",    "numpy",          "모든 수치연산"),
    ("pandas",   "pandas",         "모든 패널 처리"),
    ("pyarrow",  "pyarrow",        "parquet 캐시"),
    ("requests", "requests",       "모든 HTTP 수집"),
]
_OPTIONAL = [
    ("bs4",               "beautifulsoup4",     "리서치 리스트 파싱"),
    ("lxml",              "lxml",               "HTML 고속 파서"),
    ("tqdm",              "tqdm",               "진행률 표시"),
    ("FinanceDataReader", "finance-datareader", "가격/상장목록 폴백"),
    ("pykrx",             "pykrx",              "KRX 시세·시총·수급·지수구성 (생존자편향 제거 보강)"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("scipy",             "scipy",              "스피어만 IC/검정"),
    ("yaml",              "pyyaml",             "config.yaml 출력"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출"),
]


def _pip_install(pkgs: List[str]) -> Tuple[bool, str]:
    if not pkgs:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
           "--no-input", "-q"] + pkgs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
        return r.returncode == 0, (r.stderr or r.stdout)[-1500:]
    except Exception as e:                                    # noqa
        return False, f"{type(e).__name__}: {e}"


def _ensure_deps() -> Dict[str, bool]:
    import importlib, importlib.util
    miss_req = [p for m, p, _w in _REQUIRED if importlib.util.find_spec(m) is None]
    miss_opt = [p for m, p, _w in _OPTIONAL if importlib.util.find_spec(m) is None]
    if miss_req:
        print(f"[부트스트랩] 필수 패키지 설치: {', '.join(miss_req)} (1~3분)")
        ok, err = _pip_install(miss_req)
        if not ok:
            print("=" * 88 + f"\n❌ 필수 패키지 설치 실패. 직접 실행하세요: pip install {' '.join(miss_req)}\n"
                  + err + "\n" + "=" * 88)
            raise SystemExit(1)
        importlib.invalidate_caches()
    if miss_opt and RUN_MODE not in ("SMOKE", "CACHED"):     # CACHED: network=0 약속 준수
        print(f"[부트스트랩] 선택 패키지 설치: {', '.join(miss_opt)}")
        _pip_install(miss_opt)                    # 실패해도 계속 — 기능별로 개별 degrade
        importlib.invalidate_caches()
    # ★ find_spec 만 사용한다(모듈을 실행하지 않음). pykrx 는 import 시점에 KRX 세션을 만들므로
    #   자격증명 주입(아래) 전에 import 되면 비인증 세션이 고착된다.
    return {m: (importlib.util.find_spec(m) is not None) for m, _p, _w in _OPTIONAL}


# ═══ 자격증명은 어떤 서드파티 import 보다 먼저 환경변수로 주입한다 ═══════════════════════════
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

try:
    from bs4 import BeautifulSoup
except Exception:                                             # pragma: no cover
    BeautifulSoup = None                                      # type: ignore
try:
    from tqdm.auto import tqdm
except Exception:                                             # pragma: no cover
    def tqdm(it=None, **kw):                                  # type: ignore
        return it if it is not None else iter(())

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 80)
np.seterr(all="ignore")

random.seed(SEED)
np.random.seed(SEED % (2 ** 32 - 1))
RNG = np.random.default_rng(SEED)

fdr = pykrx_stock = yf = fitz = None
if OPT.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr           # type: ignore
    except Exception:
        fdr = None
_PYKRX_IMPORT_MSG = ""
if OPT.get("pykrx"):
    # ★ pykrx 는 import 시점에 KRX 로그인을 수행하고 결과를 stdout 에 직접 print 한다.
    #   그 한 줄이 로그 맨 앞에 섞여 원인 추적을 방해하므로 캡처해서 우리 로거로 넘긴다.
    #   (자격증명은 위에서 이미 주입됐다 — 순서를 바꾸면 비인증 세션이 고착된다.)
    import contextlib as _ctx
    _buf = io.StringIO()
    try:
        with _ctx.redirect_stdout(_buf), _ctx.redirect_stderr(_buf):
            from pykrx import stock as pykrx_stock    # type: ignore
    except Exception as _e:                            # noqa
        pykrx_stock = None
        _PYKRX_IMPORT_MSG = f"import 실패: {type(_e).__name__}: {_e}"
    _msg = (_buf.getvalue() or "").strip()
    if _msg:
        _PYKRX_IMPORT_MSG = (_PYKRX_IMPORT_MSG + " | " + _msg).strip(" |")
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
    except Exception:
        yf = None
if OPT.get("fitz"):
    try:
        import fitz                               # type: ignore
    except Exception:
        fitz = None
try:
    from scipy import stats as sp_stats           # type: ignore
except Exception:
    sp_stats = None


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-B  커널 — 로깅 / 스테이지 / 데이터흐름 원장(FLOW) / 에러 국소화 / 런타임 계측          ║
# ║  목적 단 하나: "어디서 터졌고, 무슨 데이터가 어디로 흘렀는가"를 한 화면에서 보이게 한다.    ║
# ║  · 모든 연산은 STAGE 컨텍스트 안에서만 수행한다.                                           ║
# ║  · 모든 데이터 입출력은 FLOW 원장에 기록한다(행수·컬럼수·소스·PIT 컬럼 유무).               ║
# ║  · 예외는 "스테이지ID + 직전 입출력 스냅샷 + 한글 진단 힌트"와 함께 재출력한다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_T0_PROCESS = time.time()


def _dw(s: str) -> int:
    """한글 폭 2칸을 반영한 표시 너비 — 표 정렬이 깨지지 않게 하는 유일한 방법."""
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
        scope = ("/".join(self.ctx))[-30:]
        line = f"[{stamp}] {_pad(scope, 30)} {icon}{msg}"
        with self.lock:
            self.buffer.append(line)
            _safe_print(line, flush=True)

    def debug(self, m): self._emit("DEBUG", m, "· ")
    def info(self, m):  self._emit("INFO",  m, "  ")
    def ok(self, m):    self._emit("INFO",  m, "✔ ")
    def warn(self, m):  self._emit("WARN",  m, "⚠ ")
    def error(self, m): self._emit("ERROR", m, "✘ ")

    def banner(self, title: str, sub: str = "", width: int = 104):
        for line in ("", "╔" + "═" * (width - 2) + "╗",
                     "║ " + _pad(_trunc(title, width - 4), width - 4) + " ║"):
            _safe_print(line, flush=True)
            self.buffer.append(line)
        if sub:
            line = "║ " + _pad(_trunc(sub, width - 4), width - 4) + " ║"
            _safe_print(line, flush=True)
            self.buffer.append(line)
        line = "╚" + "═" * (width - 2) + "╝"
        _safe_print(line, flush=True)
        self.buffer.append(line)

    def table(self, rows: List[Sequence[Any]], headers: Sequence[str],
              aligns: Optional[Sequence[str]] = None, maxw: int = 46, title: str = ""):
        """한글 폭 보정 표. 성과/강건성/감사 출력 전부 이걸 쓴다. 로그버퍼에도 저장된다."""
        out_lines = []
        if title:
            out_lines.append(f"\n▶ {title}")
        if not rows:
            out_lines.append("   (행 없음)")
        else:
            ncol = len(headers)
            aligns = list(aligns or ["l"] * ncol)
            cells = [[_trunc("" if c is None else c, maxw) for c in r] + [""] * (ncol - len(r))
                     for r in rows]
            widths = [max(_dw(headers[i]), *(_dw(r[i]) for r in cells)) for i in range(ncol)]
            out_lines.append("  " + " │ ".join(_pad(headers[i], widths[i], "c") for i in range(ncol)))
            out_lines.append("  " + "─┼─".join("─" * widths[i] for i in range(ncol)))
            for r in cells:
                out_lines.append("  " + " │ ".join(_pad(r[i], widths[i], aligns[i])
                                                   for i in range(ncol)))
        with self.lock:
            for line in out_lines:
                self.buffer.append(line)
                _safe_print(line, flush=True)


LOG = _Log("DEBUG" if VERBOSE else "INFO")


# ── 예외 → 한글 진단 힌트 ───────────────────────────────────────────────────────────────────
_DIAG_RULES: List[Tuple[str, str]] = [
    (r"dart.*(013|020|100|800|900)|status.*'0(13|20)'|LIMITED_NUMBER",
     "DART 응답 코드 오류: 013=데이터 없음(정상일 수 있음), 020=일일한도 초과(내일 이어받기), "
     "100=필드 부적절, 800=점검, 900=미정의. DART_API_KEY 와 남은 호출량 표를 확인하세요."),
    (r"HTTPError.*40[13]|Forbidden|403",
     "403 차단입니다. RATE_LIMIT_QPS 를 절반으로, N_WORKERS_IO 를 8 이하로 낮추세요. "
     "네이버/한경은 User-Agent·Referer 헤더가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests",
     "요청 속도 초과입니다. RATE_LIMIT_QPS 를 낮추세요(지수백오프 재시도는 자동입니다)."),
    (r"ConnectionError|Timeout|Max retries|NameResolution|SSLError|ProxyError",
     "네트워크 도달 실패. 방화벽/프록시 환경이면 해당 도메인이 막혔을 수 있습니다. "
     "RUN_MODE='CACHED' 로 캐시만으로도 백테스트할 수 있습니다."),
    (r"No such file or directory.*(drive|MyDrive)",
     "구글드라이브 미마운트. Colab이면 인증 팝업을 승인하세요. JupyterLab이면 "
     "GDRIVE_ROOT_CANDIDATES 의 로컬 경로(D:/, G:/)를 확인하세요 — 없으면 로컬 캐시로 폴백합니다."),
    (r"No space left|Disk quota",
     "디스크/드라이브 용량 부족. RESEARCH_DOWNLOAD_PDF=False 로 두면 PDF 없이 진행됩니다."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족. MEM_BUDGET_GB 를 낮추고 RESEARCH_DOWNLOAD_PDF=False 로 두세요. "
     "패널은 float32/category 로 이미 축소되어 있습니다."),
    (r"pyarrow|parquet|ArrowInvalid|ArrowIOError",
     "parquet 손상(드라이브 FUSE 쓰기 중단 잔재일 가능성). 원자적 쓰기라 이번 실행 산출물은 "
     "안전합니다. 손상 파일은 .corrupt 로 격리되며 재수집으로 복구됩니다."),
    (r"Expecting value: line \d+|JSONDecodeError|Error occurred in get_market",
     "JSON 대신 HTML(로그인/에러 페이지)을 받았습니다. KRX 세션 끊김이 유력합니다 — "
     "모든 pykrx 호출은 KRXG.call() 로 직렬화되어 있는데, 같은 KRX 계정을 다른 브라우저/노트북에서 "
     "동시에 쓰고 있지 않은지 확인하세요(중복 로그인 CD011 은 서로를 밀어냅니다)."),
    (r"UnicodeEncodeError|cp949|charmap",
     "콘솔 인코딩 문제(윈도우 cp949). 코드가 stdout 을 UTF-8 로 바꾸고 실패 시 ASCII 로 낮춥니다. "
     "직접 print 를 추가했다면 _safe_print 를 쓰거나 실행 전 `chcp 65001` 을 하세요."),
    (r"KeyError: 'knowledge_date'|knowledge_date",
     "PIT 컬럼 누락. 모든 수집 테이블은 pit_frame(df, event_date, knowledge_date) 을 통과해야 "
     "합니다. 새 수집 함수를 추가했다면 감싸 주세요."),
    (r"empty|EmptyDataError|No objects to concatenate|zero-size",
     "수집 결과가 비었습니다. ① 키 미입력 ② 조회구간 데이터 없음 ③ 소스 구조 변경 중 하나입니다. "
     "바로 위 FLOW 원장에서 어느 소스가 0행을 반환했는지 보세요."),
    (r"ModuleNotFoundError|ImportError",
     "패키지 누락. 부트스트랩 로그에서 설치 실패 항목을 확인하고 수동 설치하세요."),
    (r"tz-aware|tz-naive|Cannot compare",
     "타임존 혼재 날짜 비교. 모든 날짜는 as_ts()로 tz-naive 정규화됩니다 — 새 소스가 "
     "tz-aware 를 반환했을 가능성이 큽니다."),
]


def diagnose(exc: BaseException, extra: str = "") -> str:
    blob = f"{type(exc).__name__}: {exc}\n{extra}\n{traceback.format_exc()}"
    for pat, hint in _DIAG_RULES:
        if re.search(pat, blob, re.I):
            return hint
    return ("알려진 패턴 밖의 오류입니다. 트레이스백 마지막 프레임과 직전 FLOW 원장 행을 "
            "함께 보면 원인 구간이 좁혀집니다.")


# ── 데이터 흐름 원장 ────────────────────────────────────────────────────────────────────────
@dataclass
class IOEvent:
    stage: str
    direction: str          # IN / OUT
    kind: str               # HTTP / DRIVE / PARQUET / MEM / SYNTH
    name: str
    rows: int = -1
    cols: int = -1
    source: str = ""
    ok: bool = True
    note: str = ""
    pit_cols: str = ""


@dataclass
class StageRecord:
    sid: str
    name: str
    layer: str
    status: str = "PENDING"
    t_start: float = 0.0
    t_end: float = 0.0
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


class StageFailure(Exception):
    pass


class Pipeline:
    """스테이지 실행기 — 모든 계산은 이 안에서만 돈다."""

    def __init__(self):
        self.stages: "OrderedDict[str, StageRecord]" = OrderedDict()
        self.flow: List[IOEvent] = []
        self.current: Optional[StageRecord] = None
        self.failed: List[str] = []
        self._lock = threading.RLock()

    def io(self, direction: str, kind: str, name: str, obj: Any = None,
           source: str = "", ok: bool = True, note: str = ""):
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
                     kind=kind, name=name, rows=rows, cols=cols, source=source, ok=ok,
                     note=note, pit_cols=pit)
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

    def mark_skipped(self, sid: str, name: str, layer: str, reason: str):
        """스테이지를 '실행하지 않고' SKIP 으로 기록한다.
        (컨텍스트매니저의 yield 는 with 본문 실행을 막을 수 없으므로, 건너뛰기는
         호출부의 명시적 if + 이 함수로만 표현한다 — 조용히 반쯤 실행되는 것보다 낫다)"""
        rec = StageRecord(sid=sid, name=name, layer=layer, status="SKIP")
        rec.t_start = rec.t_end = time.time()
        rec.notes.append(reason)
        self.stages[sid] = rec
        LOG.warn(f"[{sid}] 건너뜀 — {reason}")

    @contextmanager
    def stage(self, sid: str, name: str, layer: str = "L?", critical: bool = True):
        rec = StageRecord(sid=sid, name=name, layer=layer)
        self.stages[sid] = rec
        prev, self.current = self.current, rec
        LOG.ctx.append(sid)
        rec.status = "RUNNING"
        rec.t_start = time.time()
        LOG.info(f"▷ {name}")
        try:
            yield rec
            rec.t_end = time.time()
            rec.status = "WARN" if any("WARN:" in n for n in rec.notes) else "OK"
            LOG.ok(f"완료 {rec.dur:6.2f}s  in={rec.rows_in:,} out={rec.rows_out:,}")
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
        _safe_print(f"  예외 : {rec.err_type}: {rec.err_msg}")
        _safe_print(f"  진단 : {rec.hint}")
        recent = [e for e in self.flow if e.stage == rec.sid][-8:]
        if recent:
            LOG.table(
                [[e.direction, e.kind, _trunc(e.name, 34), f"{e.rows:,}" if e.rows >= 0 else "-",
                  e.pit_cols, "OK" if e.ok else "ERR", _trunc(e.source or e.note, 26)]
                 for e in recent],
                ["방향", "종류", "대상", "행수", "PIT", "상태", "소스/비고"],
                ["c", "l", "l", "r", "c", "c", "l"],
                title="이 스테이지의 직전 입출력 (여기서 무엇이 비었는지 보세요)")
        _safe_print("\n  ── 트레이스백 (마지막 12줄) " + "─" * 60)
        for ln in rec.err_tb.rstrip().split("\n")[-12:]:
            _safe_print("   " + ln)
        _safe_print("  " + "─" * 86)

    def report_stages(self):
        LOG.banner("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수")
        rows = []
        for r in self.stages.values():
            icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUNNING": "…"}.get(r.status, "?")
            rows.append([r.layer, r.sid, _trunc(r.name, 40), f"{icon}{r.status}",
                         f"{r.dur:8.2f}", f"{r.rows_in:,}", f"{r.rows_out:,}",
                         _trunc("; ".join(r.notes), 38)])
        LOG.table(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "비고"],
                  ["c", "l", "l", "c", "r", "r", "r", "l"], maxw=44)

    def report_flow(self, limit: int = 160):
        LOG.banner("데이터 흐름 원장 (I/O LEDGER)",
                   "어떤 스테이지가 어디서 몇 행을 읽고 어디에 몇 행을 썼는가 · PIT=E(event)/K(knowledge)")
        evs = self.flow
        if len(evs) > limit:
            LOG.warn(f"원장 {len(evs)}건 중 최근 {limit}건만 출력합니다.")
            evs = evs[-limit:]
        LOG.table(
            [[e.stage, e.direction, e.kind, _trunc(e.name, 38),
              f"{e.rows:,}" if e.rows >= 0 else "-", f"{e.cols}" if e.cols >= 0 else "-",
              e.pit_cols or "—", "OK" if e.ok else "ERR", _trunc(e.source or e.note, 28)]
             for e in evs],
            ["스테이지", "방향", "종류", "대상", "행수", "열수", "PIT", "상태", "소스/비고"],
            ["l", "c", "l", "l", "r", "r", "c", "c", "l"], maxw=40)

    def runtime_profile(self) -> dict:
        agg: Dict[str, float] = defaultdict(float)
        per_stage = {}
        for r in self.stages.values():
            agg[r.layer] += r.dur
            per_stage[r.sid] = {"name": r.name, "layer": r.layer, "status": r.status,
                                "seconds": round(r.dur, 2),
                                "rows_in": r.rows_in, "rows_out": r.rows_out}
        return {"per_layer_seconds": {k: round(v, 2) for k, v in sorted(agg.items())},
                "per_stage": per_stage, "total_seconds": round(sum(agg.values()), 2)}

    def report_runtime(self, timed_core_s: Optional[float] = None):
        LOG.banner("런타임 감사", "계층별 실측 소요시간 · 계약 SLA(cached 코어) 14,400초")
        prof = self.runtime_profile()
        rows = [[k, f"{v:8.2f}s", f"{v/60:6.2f}분"] for k, v in prof["per_layer_seconds"].items()]
        rows.append(["합계", f"{prof['total_seconds']:8.2f}s", f"{prof['total_seconds']/60:6.2f}분"])
        LOG.table(rows, ["계층", "실측(초)", "실측(분)"], ["c", "r", "r"])
        if timed_core_s is not None:
            verdict = "✔ SLA 내" if timed_core_s <= SLA_SECONDS else "✘ FAIL — SLA 초과"
            LOG.info(f"계약 timed run (캐시 이후 팩터→리밸런스→성과) 실측 {timed_core_s:,.1f}초 "
                     f"/ 한도 {SLA_SECONDS:,}초 → {verdict}")
        LOG.info("계층 정의 — L0:부트/캐시  L1:수집·정제  L2:팩터  L3:백테스트  L5:강건성  L6:리포트")


PIPE = Pipeline()


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-C  유틸 — 날짜/해시/원자적IO/JSONL/레이트리미터/재시도/병렬/메모리/PIT 프레임           ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def as_ts(x) -> Optional[pd.Timestamp]:
    """무엇이 들어오든 tz-naive 정규화 Timestamp. tz 혼재는 이 계열 프로젝트 최빈 버그였다."""
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
        try:
            t = t.tz_convert(None)
        except Exception:
            t = t.tz_localize(None)
    return t.normalize()


def as_ts_series(s) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    return out.dt.normalize()


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


# 2024-01 종목코드 개편(영숫자 코드) 대응 — 단순 \D 제거는 신형 티커를 조용히 망가뜨린다.
_TICKER_RE = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0-9KLMN])$")


def to_code6(x: Any) -> Optional[str]:
    """'005930', 5930, 'A005930', '005930.KS', '09701K' → 정규화 코드. 실패 시 None."""
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


# ── 원자적 파일 IO (드라이브 FUSE 에서 반쪽 파일이 생기지 않게) ──────────────────────────────
def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def atomic_write_bytes(path: str, data: bytes) -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass                     # 일부 FUSE 는 fsync 미지원 — replace 는 여전히 유효
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_parquet(df: pd.DataFrame, path: str, compression: str = "zstd") -> str:
    _ensure_dir(path)
    tmp = f"{path}.tmp.{os.getpid()}"
    out = df.copy()
    for c in out.columns:                       # object 혼합형은 arrow 가 거부 → 문자열화
        if out[c].dtype == object:
            try:
                pd.api.types.infer_dtype(out[c], skipna=True)
            except Exception:
                out[c] = out[c].astype(str)
    try:
        out.to_parquet(tmp, index=False, compression=compression)
    except Exception:
        try:
            out.to_parquet(tmp, index=False, compression="snappy")
        except Exception:
            out = out.astype({c: str for c in out.columns if out[c].dtype == object})
            out.to_parquet(tmp, index=False, compression="snappy")
    os.replace(tmp, path)
    return path


def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        # ★ 격리(개명)는 '우리 소유' 캐시에만. adopt 로 참조 등록된 외부 파일을 개명하면
        #   원위치에서 사라져 다른 전략의 조회가 전부 미스난다(절대 1원칙 위반 — 감사 HIGH).
        #   외부 파일은 그대로 두고 None + 경고만 돌려준다(일과성 오류면 다음 실행에 복구).
        owned = False
        try:
            v = globals().get("VAULT")
            owned = v is not None and os.path.abspath(path).startswith(v.root + os.sep)
        except Exception:
            owned = False
        if owned:
            LOG.warn(f"parquet 손상 추정 — 격리 후 재생성 대상: {os.path.basename(path)} "
                     f"({type(e).__name__})")
            try:                               # 지우지 않고 격리 보관 (원본 보호)
                os.replace(path, path + f".corrupt.{int(time.time())}")
            except Exception:
                pass
        else:
            LOG.warn(f"외부/참조 parquet 읽기 실패({type(e).__name__}) — 훼손 방지를 위해 "
                     f"손대지 않고 건너뜁니다: {path}")
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
                continue                        # 반쪽 줄은 건너뜀 (append-only 저널의 정상 동작)
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


# ── 레이트리미터 / 재시도 / 병렬 ────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, qps: float):
        self.interval = 1.0 / max(qps, 0.01)
        self._next = 0.0
        self._lk = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.monotonic()
            d = self._next - now if now < self._next else 0.0
            self._next = max(now, self._next) + self.interval
        if d > 0:
            time.sleep(d)


_LIMITERS: Dict[str, RateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def limiter(source: str) -> RateLimiter:
    with _LIMITER_LOCK:
        if source not in _LIMITERS:
            _LIMITERS[source] = RateLimiter(RATE_LIMIT_QPS.get(source,
                                                               RATE_LIMIT_QPS.get("generic", 3.0)))
        return _LIMITERS[source]


def retry(tries: int = 4, base: float = 1.6, exc=(Exception,), on_fail=None, quiet: bool = True):
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
                        LOG.debug(f"재시도 {i+1}/{tries-1} ({type(e).__name__}) — {slp:.1f}s")
                    time.sleep(slp)
            if on_fail is not None:
                return on_fail(last)
            raise last                                  # type: ignore
        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapped
    return deco


def pmap_io(fn: Callable, items: Sequence, workers: Optional[int] = None,
            desc: str = "", quiet: bool = False) -> List[Any]:
    """네트워크 병렬(스레드). 예외는 None 으로 표시하되 유형별 개수를 로그에 남긴다.
    (노트북 환경에서 ProcessPool 은 pickling 문제로 자주 죽는다 — I/O 는 스레드가 정답이고,
     연산부는 전부 pandas/numpy 벡터화라 프로세스 병렬이 필요 없다)"""
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
        LOG.warn(f"{desc or '병렬작업'} 실패 {sum(errs.values())}/{len(items)}건 — " +
                 ", ".join(f"{k}×{v}" for k, v in errs.most_common(4)))
    return out


def downcast(df: pd.DataFrame, cat_thresh: float = 0.35) -> pd.DataFrame:
    """float64→float32, 저카디널리티 object→category. 10년 패널 RAM 을 3~5배 줄인다."""
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


def mem_mb(df) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / 1e6
    except Exception:
        return -1.0


def col(df: pd.DataFrame, name: str, default: float = np.nan) -> pd.Series:
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자 — 소스가 통째로 비어 컬럼 자체가
    생성되지 않는 상황(키 미입력·한도 소진)이 실데이터 실행의 최빈 경로다."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype="float64")


def safe_div(a, b, eps: float = 1e-12):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


def assert_no_dup_cols(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 의 의미가 예외 없이 바뀌는 최악의 조용한 버그 — 발생 지점에서 세운다."""
    if df is None or df.empty:
        return df
    dup = df.columns[df.columns.duplicated()]
    if len(dup):
        raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — 여기서 중단합니다.")
    return df


# ── PIT 프레임 강제 ─────────────────────────────────────────────────────────────────────────
PIT_COLS = ("event_date", "knowledge_date")


def _resolve_dates(df: pd.DataFrame, arg) -> pd.Series:
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
    """모든 수집 결과는 이 함수를 통과해야 한다. knowledge < event 는 그 자체가 미래누수라 보정."""
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
    bad = out["knowledge_date"] < out["event_date"]
    if bad.any():
        out.loc[bad, "knowledge_date"] = out.loc[bad, "event_date"]
        PIPE.note(f"WARN: knowledge<event {int(bad.sum())}행을 event 로 보정")
    out = out.dropna(subset=["knowledge_date"])
    if source:
        out["_src"] = source
    return out


# ── 통계 소도구 ─────────────────────────────────────────────────────────────────────────────
def hac_tstat(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West HAC 평균 t통계량 — 분기 수익 시계열의 유의성."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return (np.nan, np.nan)
    mu = x.mean()
    e = x - mu
    L = lags if lags is not None else max(1, int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0))))
    L = max(0, min(L, n - 2))
    g0 = float(e @ e) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(e[l:] @ e[:-l]) / n
        var += 2.0 * (1.0 - l / (L + 1.0)) * gl
    var = max(var, 1e-18)
    return (float(mu), float(mu / math.sqrt(var / n)))


def spearman_ic(x: pd.Series, y: pd.Series) -> float:
    """스피어만 랭크 상관 (scipy 없으면 pandas rank 로 동일 계산)."""
    m = x.notna() & y.notna()
    if int(m.sum()) < 8:
        return np.nan
    if sp_stats is not None:
        try:
            return float(sp_stats.spearmanr(x[m], y[m]).statistic)
        except Exception:
            pass
    xr = x[m].rank()
    yr = y[m].rank()
    return float(np.corrcoef(xr, yr)[0, 1])


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-D  캐시 저장소 (VAULT) — 구글드라이브 공용/전용 인덱스                                 ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다 — 약속이 아니라 구조로 보장한다 ★★★    ║
# ║   1) 인덱스의 진실 = append-only JSONL 저널 (기존 줄 재기록 없음 → 과거 기록 유실 불가)     ║
# ║   2) index.parquet 은 저널의 파생물. 재생성 전 반드시 타임스탬프 백업(실패 시 컴팩션 포기)  ║
# ║   3) 컬럼은 합집합으로만 확장 — 다른 전략의 스키마가 달라도 기존 컬럼을 떨어뜨리지 않음     ║
# ║   4) blob 은 내용해시 경로 → 같은 내용은 재기록 자체가 없고, 다르면 새 리비전               ║
# ║   5) 기존 드라이브 파일은 이동·개명 없이 '경로만 등록' (adopt-by-reference)                 ║
# ║   6) 삭제 API 자체가 없다. 손상 파일조차 .corrupt 로 격리만 한다                            ║
# ║                                                                                          ║
# ║  이 저장 형식은 기존 전략(tcd_v2 등)의 vault v2 와 와이어 호환이다. 공용(_shared) 인덱스에  ║
# ║  이미 쌓인 일봉·시총·마스터·리포트 원장을 그대로 재사용하고, 이 전략의 산출물은             ║
# ║  전용(shinhan_7f) 네임스페이스에만 쓴다.                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VAULT_SCHEMA_VER = "2.0"

INDEX_COLUMNS = [
    "uid", "scope", "domain", "subtype", "key", "path", "abs_path", "fmt",
    "bytes", "sha1", "event_date", "knowledge_date", "source", "collected_at",
    "strategy", "adopted", "schema_ver", "extra",
]


# ── ★ v1.1: 읽기 루트 전수 발견 ──────────────────────────────────────────────────────────────
#  v1.0 은 후보 목록에서 '처음 존재하는 하나'만 채택하고 멈췄다. 사용자의 윈도우 환경에서는
#  D:/tcd_cache 가 먼저 잡혀 구글드라이브에만 있던 marcap_YYYY(시총 스파인)를 아예 보지
#  못했고, 그 결과 40개 분기 전부 시총 결손 → KOSPI200 재구성 0시점 → 36분 실행 후 중단.
#  v1.1: 쓰기 루트는 여전히 하나(최우선)지만, 읽기는 존재하는 모든 루트를 합집합으로 본다.
READ_ROOTS: List[str] = []


def _existing_root_candidates() -> List[str]:
    seen, out = set(), []
    for cand in GDRIVE_ROOT_CANDIDATES:
        p = os.path.expanduser(str(cand))
        try:
            if not os.path.isdir(p):
                continue
            rp = os.path.realpath(p)
        except Exception:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def register_read_roots(primary: str) -> List[str]:
    """읽기 전용으로 함께 열어둘 캐시 루트 전체(우선순위 유지, 중복 realpath 제거)."""
    global READ_ROOTS
    seen, out = set(), []
    for p in [primary] + _existing_root_candidates():
        try:
            rp = os.path.realpath(os.path.expanduser(p))
        except Exception:
            continue
        if rp in seen or not os.path.isdir(rp):
            continue
        seen.add(rp)
        out.append(os.path.expanduser(p))
    READ_ROOTS = out
    if len(out) > 1:
        LOG.ok(f"캐시 루트 {len(out)}곳을 동시에 읽습니다(쓰기는 첫 번째만): "
               + " | ".join(out))
        for p in out[1:]:
            LOG.info(f"  읽기 전용 추가 루트: {p}")
    return out


def discover_roots() -> Tuple[str, str, List[str]]:
    """(캐시루트, 모드, adopt 대상 폴더들).
    Colab 이면 드라이브 마운트 후 후보를 탐색하고, 로컬(주피터/CLI)이면 로컬 동기화 경로와
    D드라이브 후보를 순서대로 탐색한다. 어느 쪽이든 죽지 않는다.
    ★ 채택 규칙(v1.1): 존재하는 후보 중 '_shared/table 에 실제 데이터가 가장 많은' 루트를
      쓰기 루트로 고른다. 단순히 목록 순서상 처음 존재하는 것을 쓰면, 비어 있는 로컬 폴더가
      데이터가 가득한 드라이브 루트를 가려버린다(v1.0 의 실제 사고)."""
    if ENV["colab"]:
        try:
            from google.colab import drive as _gdrive      # type: ignore
            mp = "/content/drive"
            if not os.path.isdir(os.path.join(mp, "MyDrive")):
                _gdrive.mount(mp, force_remount=False)
        except Exception as e:                             # noqa
            LOG.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 캐시로 폴백합니다.")

    def _root_payload(p: str) -> Tuple[int, int]:
        """(테이블 파일 수, 총 바이트) — 어느 루트가 '진짜 캐시'인지 판정하는 척도."""
        n, b = 0, 0
        for ns in (GDRIVE_SHARED_NS, GDRIVE_PRIVATE_NS):
            td = os.path.join(p, ns, "table")
            try:
                for f in os.listdir(td):
                    fp = os.path.join(td, f)
                    try:
                        b += os.path.getsize(fp)
                        n += 1
                    except Exception:
                        pass
            except Exception:
                pass
        return n, b

    found_root, mode = None, "LOCAL"
    cands = _existing_root_candidates()
    if cands:
        scored = [(p, _root_payload(p)) for p in cands]
        # 데이터가 있는 루트를 우선. 전부 비어 있으면 후보 목록 순서를 그대로 따른다.
        best = max(range(len(scored)), key=lambda i: (scored[i][1][1], -i))
        if scored[best][1][0] == 0:
            best = 0
        found_root = scored[best][0]
        mode = ("COLAB_DRIVE" if found_root.startswith("/content/drive")
                else "LOCAL_SYNCED_DRIVE")
        if len(scored) > 1:
            LOG.info("캐시 루트 후보(테이블 적재량 기준으로 쓰기 루트 선택): " + " · ".join(
                f"{p} → {n}파일 {b/1e9:.2f}GB" for p, (n, b) in scored))
    if found_root is None:
        # 드라이브 자체는 있는데 루트 폴더만 없는 경우 → 드라이브 안에 새로 만든다(마지막 후보)
        for cand in GDRIVE_ROOT_CANDIDATES:
            p = os.path.expanduser(cand)
            parent = os.path.dirname(p)
            if os.path.isdir(parent):
                try:
                    os.makedirs(p, exist_ok=True)
                    found_root, mode = p, ("COLAB_DRIVE" if p.startswith("/content/drive")
                                           else "LOCAL_SYNCED_DRIVE")
                    LOG.info(f"캐시 루트가 없어 새로 만들었습니다: {p}")
                    break
                except Exception:
                    continue
    if found_root is None:
        found_root, mode = os.path.abspath(LOCAL_CACHE_ROOT), "LOCAL"
        os.makedirs(found_root, exist_ok=True)
        LOG.warn(f"드라이브 경로를 찾지 못해 로컬 캐시({found_root})로 폴백합니다. "
                 f"신규 수집분은 여기 저장되며, 드라이브 연결 후 재실행하면 흡수됩니다.")

    register_read_roots(found_root)
    adopts, seen = [], set()
    for base in READ_ROOTS or [found_root]:
        drive_parent = os.path.dirname(base)
        for d in GDRIVE_ADOPT_DIRS:
            p = os.path.expanduser(str(d).replace("{DRIVE}", drive_parent))
            try:
                rp = os.path.realpath(p)
            except Exception:
                continue
            if rp in seen or not os.path.isdir(p):
                continue
            if rp == os.path.realpath(found_root):
                continue
            seen.add(rp)
            adopts.append(p)
    return found_root, mode, adopts


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

    # ── 잠금 (두 노트북 동시 실행에도 저널이 섞이지 않게) -------------------------------
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

    # ── 인덱스 적재 (기존 것은 읽기만 한다) ---------------------------------------------
    def load_index(self, scope: str, force: bool = False) -> pd.DataFrame:
        with self._lk:
            if not force and scope in self._idx:
                return self._idx[scope]
        frames: List[pd.DataFrame] = []

        p = self.idx_parquet(scope)
        d = read_parquet_safe(p)
        if d is not None and len(d):
            frames.append(d)

        jr = read_jsonl(self.journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))

        # 과거 버전/다른 전략이 남긴 인덱스 파일도 흡수 (읽기 전용, 훼손 없음)
        idx_dir = os.path.join(self.ns[scope], "index")
        legacy_glob = []
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
            allcols: List[str] = []
            for f in frames:
                for c in f.columns:
                    if c not in allcols:
                        allcols.append(c)
            frames = [f.reindex(columns=allcols) for f in frames]
            idx = pd.concat(frames, ignore_index=True)
            # ★ uid 결측 레거시 행을 astype(str) 그대로 두면 전부 "nan" 으로 뭉개져
            #   drop_duplicates 가 그 파일 전체를 1행으로 붕괴시킨다(인덱스 유실) → 개별 부여.
            if "uid" not in idx.columns:
                idx["uid"] = np.nan
            miss = idx["uid"].isna() | (idx["uid"].astype(str).str.strip().isin(("", "nan", "None")))
            if miss.any():
                fill_src = [c for c in ("path", "abs_path", "key", "sha1", "domain", "subtype",
                                        "_legacy_file") if c in idx.columns]
                idx.loc[miss, "uid"] = [
                    sha1_str("legacy", i, *[str(idx.iloc[i].get(c, "")) for c in fill_src])
                    for i in np.where(miss.to_numpy())[0]]
                LOG.info(f"레거시 인덱스 {int(miss.sum()):,}행에 uid 부여 (기존 기록 보존).")
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
            return uid in self._uidset[scope] or \
                any(r.get("uid") == uid for r in self._pending[scope])

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
        """원본 바이트를 내용해시 경로에 저장하고 인덱스에 등록. 같은 내용이면 재기록 없음."""
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
                LOG.warn(f"blob 저장 실패({type(e).__name__}) — 건너뜁니다: {key}")
                return None
        else:
            self.stats["blob_dedup_hit"] += 1
        self._register(scope, {
            "uid": uid, "domain": domain, "subtype": subtype, "key": str(key),
            "path": rel, "abs_path": abspath, "fmt": fmt, "bytes": len(data), "sha1": h,
            "event_date": str(as_ts(event_date) or ""),
            "knowledge_date": str(as_ts(knowledge_date) or ""),
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
                  domain: str = "table", source: str = "",
                  extra: Optional[dict] = None) -> Optional[str]:
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
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 덮어쓰지 않고 "
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
                                 "cols": list(map(str, df.columns))[:60]}, ensure_ascii=False),
        })
        PIPE.io("OUT", "DRIVE", f"table:{name}", df, source=scope)
        return path

    def table_paths(self, name: str, scope: str = "shared") -> List[str]:
        """★ v1.1: 같은 이름의 테이블을 '모든 읽기 루트 × (요청 scope, 반대 scope)' 에서 찾아
        존재하는 경로 전부를 우선순위 순으로 돌려준다. 로컬 D드라이브와 구글드라이브에 나뉘어
        쌓인 캐시를 합집합으로 쓰기 위한 진입점 — v1.0 은 쓰기 루트 하나만 봤다."""
        alt = "private" if scope == "shared" else "shared"
        ns = {"shared": GDRIVE_SHARED_NS, "private": GDRIVE_PRIVATE_NS}
        out, seen = [], set()
        for root in (READ_ROOTS or [self.root]):
            for sc in (scope, alt):
                p = os.path.join(root, ns[sc], "table", f"{name}.parquet")
                try:
                    rp = os.path.realpath(p)
                except Exception:
                    continue
                if rp in seen or not os.path.exists(p):
                    continue
                seen.add(rp)
                out.append(p)
        return out

    def get_table(self, name: str, scope: str = "shared",
                  max_age_days: Optional[float] = None,
                  union_keys: Optional[Sequence[str]] = None) -> Optional[pd.DataFrame]:
        """테이블 로드. 여러 루트에 같은 테이블이 있으면 union_keys 로 합집합 병합한다
        (합집합은 '읽기'만 하므로 어떤 원본도 훼손하지 않는다). union_keys 가 없으면
        가장 행이 많은 파일 하나를 쓴다."""
        paths = self.table_paths(name, scope)
        if not paths:
            return None
        if max_age_days is not None:
            paths = [p for p in paths
                     if (time.time() - os.path.getmtime(p)) / 86400.0 <= max_age_days]
            if not paths:
                return None
        frames: List[Tuple[str, pd.DataFrame]] = []
        for p in paths:
            d = read_parquet_safe(p)
            if d is not None and len(d):
                frames.append((p, d))
            if union_keys is None and frames:
                break                       # 단일 경로 모드: 첫 유효본만
        if not frames:
            return None
        if len(frames) == 1:
            p, d = frames[0]
        else:
            keys = [k for k in (union_keys or []) if all(k in f.columns for _, f in frames)]
            if keys:
                d = pd.concat([f for _, f in frames], ignore_index=True)
                before = len(d)
                # ★ frames 는 READ_ROOTS 순서(0번=쓰기/최우선 루트)로 쌓인다. 같은 키가 여러
                #   루트에 있으면 '최우선 루트의 행'이 이겨야 한다 — 그 루트가 우리가 방금
                #   갱신한 곳이다. keep="last" 로 두면 오래된 보조 루트가 최신본을 덮는다.
                d = d.drop_duplicates(keys, keep="first").reset_index(drop=True)
                p = " + ".join(os.path.basename(os.path.dirname(os.path.dirname(x)))
                               for x, _ in frames)
                LOG.info(f"테이블 '{name}' 을 루트 {len(frames)}곳에서 합집합 병합: "
                         f"{before:,}행 → 중복제거 {len(d):,}행")
            else:
                p, d = max(frames, key=lambda t: len(t[1]))
                LOG.info(f"테이블 '{name}' 이 루트 {len(frames)}곳에 있어 가장 큰 본을 씁니다 "
                         f"({len(d):,}행)")
        try:
            src = os.path.relpath(p, self.root) if os.path.isabs(p) else p
        except Exception:
            src = str(p)
        PIPE.io("IN", "DRIVE", f"table:{name}", d, source=src)
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
            "path": abs_path, "abs_path": abs_path,
            "fmt": os.path.splitext(abs_path)[1].lstrip("."),
            "bytes": sz, "sha1": "", "source": source or "adopted",
            "event_date": str(as_ts(event_date) or ""),
            "knowledge_date": str(as_ts(knowledge_date) or ""),
            "adopted": True, "extra": json.dumps(extra or {}, ensure_ascii=False, default=str),
        })
        self.stats["adopted"] += 1
        return uid

    # ── 커밋 / 컴팩션 ------------------------------------------------------------------
    def flush(self, scope: Optional[str] = None):
        scopes = [scope] if scope else ["shared", "private"]
        for sc in scopes:
            with self._lk:
                rows, self._pending[sc] = self._pending[sc], []
            if not rows:
                continue
            with self.lock(f"journal_{sc}"):
                append_jsonl(self.journal(sc), rows)
            self.stats[f"journal_append:{sc}"] += len(rows)

    def compact(self, scope: str):
        """저널 → index.parquet 재생성. 저널은 남기고, 기존 parquet 은 반드시 백업 후 교체."""
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
                         f"저널에 모든 기록이 남아 있으므로 유실은 없습니다.")
                return
        try:
            atomic_write_parquet(idx.astype({c: str for c in idx.columns
                                             if idx[c].dtype == object}), p)
            LOG.ok(f"인덱스 컴팩션: {scope} — {len(idx):,}행")
        except Exception as e:                              # noqa
            LOG.warn(f"인덱스 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음.")

    # ── 사전 스캔 (기존 캐시 흡수) ------------------------------------------------------
    _DATE_PAT = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], max_files: int = 300_000) -> int:
        """기존 리포트/테이블 폴더를 재귀 스캔해 '등록만' 한다. 이동·개명·삭제 없음."""
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
                    elif low.endswith((".parquet", ".jsonl", ".json", ".csv", ".pkl")) and \
                            any(t in low for t in ("report", "consensus", "research", "analyst",
                                                   "hankyung", "naver", "dart", "krx", "price",
                                                   "ohlcv", "universe", "fnltt", "marcap",
                                                   "fnguide", "eps", "flow", "kospi", "index")):
                        kind = "table_like"
                    else:
                        continue
                    found.append({"abs_path": fp, "kind": kind, "name": fn, "dir": dirpath})
                    n += 1
            LOG.info(f"  → {n:,}개 후보 발견")
        for r in found:
            m = self._DATE_PAT.search(r["name"]) or self._DATE_PAT.search(r["dir"])
            ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            self.adopt(r["abs_path"], domain="research" if r["kind"] == "report_pdf" else "table",
                       subtype=r["kind"], key=r["name"], source="preexisting_drive_cache",
                       event_date=ed, knowledge_date=ed, scope="shared",
                       extra={"dir": r["dir"]})
        self.flush("shared")
        if found:
            LOG.ok(f"기존 캐시 {len(found):,}건을 공용 인덱스에 '참조 등록'했습니다 "
                   f"(파일은 원위치 그대로, 이동·삭제 없음).")
        return len(found)

    def adopted_paths(self, name_keywords: Sequence[str], exts=(".parquet", ".csv")) -> List[str]:
        """adopt 로 등록된 파일 중 이름에 키워드가 들어간 경로 목록 (다른 전략 산출물 재활용)."""
        idx = self.load_index("shared")
        if idx.empty:
            return []
        keys = idx["key"].astype(str).str.lower()
        m = pd.Series(False, index=idx.index)
        for kw in name_keywords:
            m |= keys.str.contains(kw.lower(), regex=False)
        m &= keys.str.endswith(tuple(e.lower() for e in exts))
        out = []
        for _, r in idx[m].iterrows():
            for cand in (r.get("abs_path"), os.path.join(self.root, str(r.get("path") or ""))):
                if cand and isinstance(cand, str) and os.path.exists(cand):
                    out.append(cand)
                    break
        return sorted(set(out))

    # ── 감사 --------------------------------------------------------------------------
    def report(self):
        LOG.banner("구글드라이브 캐시 감사", f"루트: {self.root}   모드: {self.mode}")
        rows = []
        for sc in ("shared", "private"):
            idx = self.load_index(sc)
            nb = 0
            try:
                nb = int(pd.to_numeric(idx.get("bytes"), errors="coerce").fillna(0).sum())
            except Exception:
                pass
            rows.append([("공용 " + GDRIVE_SHARED_NS) if sc == "shared"
                         else ("전용 " + GDRIVE_PRIVATE_NS),
                         f"{len(idx):,}",
                         f"{int(pd.to_numeric(idx.get('adopted'), errors='coerce').fillna(0).sum()):,}"
                         if "adopted" in idx.columns else "0",
                         f"{nb / 1e9:.2f} GB",
                         os.path.relpath(self.journal(sc), self.root)])
        LOG.table(rows, ["인덱스", "등록 항목", "참조등록(adopt)", "용량", "저널"],
                  ["l", "r", "r", "r", "l"])
        LOG.info("무결성 원칙: 저널 append-only · index.parquet 백업 후 교체 · "
                 "blob 내용해시(덮어쓰기 없음) · 삭제 API 없음.")


def free_gb(path: str) -> float:
    try:
        if hasattr(os, "statvfs"):
            st = os.statvfs(path)
            return st.f_bavail * st.f_frsize / 1e9
        import shutil as _sh
        return _sh.disk_usage(path).free / 1e9
    except Exception:
        return float("nan")


VAULT: Optional[Vault] = None


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-E  HTTP 계층 — 스레드로컬 세션 / 소스별 스로틀 / 인코딩 자동판별 / 차단 회피          ║
# ║  한국 사이트 수집 실패의 9할: ①UA/Referer 없음→403 ②euc-kr 을 utf-8 로 디코드→깨짐        ║
# ║  ③과속→429. 전부 여기서 한 번에 막는다.                                                   ║
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
        ad = HTTPAdapter(pool_connections=max(16, N_WORKERS_IO * 2),
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
    """네이버 금융은 body 가 EUC-KR 인데 meta 는 utf-8 이라고 '거짓말'한다 — 점수로 고른다."""
    s = t[:6000]
    if not s:
        return -1.0
    return len(_HANGUL.findall(s)) - 3.0 * len(_MOJI.findall(s)) - 5.0 * s.count("�")


def _decode(content: bytes, resp_enc: Optional[str], url: str,
            force_enc: Optional[str] = None) -> str:
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
        if sc > 30:
            return t
    return best if best is not None else content.decode("utf-8", "replace")


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
            elif r.status_code in (403, 401):
                time.sleep(1.5 * (attempt + 1))
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


def soup_of(html: Optional[str]):
    if not html or BeautifulSoup is None:
        return None
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def report_http():
    if not HTTP_STATS:
        return
    LOG.banner("HTTP 수집 감사", "소스별 응답 분포 — 403/429 가 많으면 RATE_LIMIT_QPS 를 낮추세요")
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
# ║  L0-F  KRX 게이트/인증 + DART 실시간 호출예산                                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class KRXGate:
    """모든 pykrx 호출의 유일한 통로 — 직렬화 + 스로틀 + 예외 흡수.

    pykrx 는 모듈 전역 세션을 락 없이 검사-후-생성한다. 스레드 여럿이 동시에 로그인하면
    KRX 가 중복 로그인(CD011)으로 앞선 세션을 강제 종료해, 살아남은 하나 외에는 전부
    JSON 대신 로그인 HTML 을 받는다. 또 세션은 실효 55분 만료라 장시간 수집은 반드시
    만료를 넘긴다 → ① 메인스레드 1회 워밍업 ② 전 호출 직렬화 ③ 45분마다 선제 갱신."""

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
                # 구버전 pykrx 에는 auth 모듈이 없다(로그인 자체가 불필요) — 인증 없이 사용 가능
                self._authed = not has_cred
            self._t_login = time.time()
            if has_cred and self._authed:
                LOG.ok("KRX 세션 확보(메인스레드 1회) — 이후 모든 pykrx 호출을 직렬화합니다.")
            elif has_cred:
                LOG.warn("KRX 자격증명이 있으나 세션 인증 실패 — ID/PW 확인. "
                         "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
            else:
                LOG.info("KRX ID/PW 미입력 — pykrx 는 비인증 경로로만 시도합니다(실패 시 폴백).")
            return self._authed

    def _refresh_if_stale(self):
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
        if pykrx_stock is None or fn is None:
            return None
        with self._lk:
            self._refresh_if_stale()
            limiter("krx").wait()
            self.calls += 1
            try:
                return fn(*a, **kw)
            except Exception as e:                                     # noqa
                self.fails += 1
                LOG.debug(f"pykrx 실패 {getattr(fn, '__name__', '?')}: {type(e).__name__}")
                return None

    def report(self):
        if self.calls:
            LOG.info(f"pykrx 게이트 — 호출 {self.calls:,} · 실패 {self.fails:,} "
                     f"({100*self.fails/max(self.calls,1):.1f}%) · 직렬화 적용")


KRXG = KRXGate()


# ── KRX 접속차단(IP 제한) 감지 ────────────────────────────────────────────────────────────────
#  ★ 실운행 사고 2회차: KRX Data Marketplace 가 "자동화 수단을 통한 비정상 대량 조회"를 탐지해
#    해당 IP 를 7일간 차단했다. 차단 상태에서는 모든 bld 응답이 HTML 안내페이지로 오고,
#    pykrx 는 import 시점에 그 HTML 을 JSON 으로 파싱하려다 JSONDecodeError 로 죽는다.
#    v1.1 초안은 이를 '무응답'으로만 보고 40+40+80 번을 계속 찔러 150초를 태웠다 —
#    차단을 더 굳히는 최악의 행동이다. 이제 첫 감지 즉시 전 KRX 경로를 봉인한다.
KRX_BLOCK_PAT = re.compile(
    r"KDM\s*이용\s*제한|비정상\s*대량\s*조회|ip-block-page|접속이\s*일시적으로\s*제한|"
    r"이용약관\s*제10조", re.I)


class KRXBlockState:
    """차단 감지 상태 — 한 번 감지되면 이번 실행 내 모든 KRX 경로를 즉시 건너뛴다."""

    def __init__(self):
        self.blocked = False
        self.reported = False
        self.calls = 0
        self.budget_warned = False
        self._lk = threading.Lock()

    def spend(self, n: int = 1) -> bool:
        """이번 실행의 KRX 호출 예산. 소진되면 더 찌르지 않는다 — 재차단이 가장 비싼 사고다."""
        with self._lk:
            if self.blocked:
                return False
            self.calls += n
            if self.calls > KRX_MAX_CALLS_PER_RUN:
                if not self.budget_warned:
                    self.budget_warned = True
                    LOG.warn(f"이번 실행의 KRX 호출 예산 {KRX_MAX_CALLS_PER_RUN:,}회를 "
                             f"소진했습니다 — 남은 KRX 경로를 건너뜁니다(차단 예방). "
                             f"수집분은 캐시에 저장되어 다음 실행에서 이어집니다.")
                return False
            return True

    def note(self, text: Any) -> bool:
        """응답 본문이 차단 안내페이지인지 검사하고, 그렇다면 상태를 세운다."""
        if not text:
            return False
        t = str(text)[:4000]
        if not KRX_BLOCK_PAT.search(t):
            return False
        with self._lk:
            self.blocked = True
            if not self.reported:
                self.reported = True
                LOG.error("KRX Data Marketplace 가 이 IP 의 접속을 차단했습니다 "
                          "(자동화 대량조회 탐지 → 탐지일로부터 7일).")
                LOG.error("  · 이번 실행의 남은 KRX 경로(전종목시세·지수구성·수급)를 "
                          "전부 건너뜁니다 — 더 찌르면 차단이 연장됩니다.")
                LOG.error("  · 대안 ① 시총·일봉: marcap 공개 데이터셋(자동 다운로드)으로 "
                          "KRX 없이 완결됩니다.")
                LOG.error("  · 대안 ② 수급(F6/F7): ★공개 대체 경로가 없습니다. KRX Open API "
                          "에는 투자자별 순매수 엔드포인트가 아예 없고(31개 전수 확인), "
                          "네이버는 20일치만 주며 10년치는 종목당 123페이지가 필요합니다.")
                LOG.error("      → 차단이 풀린 뒤(7일) 1회만 수집하면 공용 인덱스에 영구 "
                          "캐시되어 이후 실행은 네트워크 0회입니다. 그때까지는 F6/F7 이 "
                          "결측이라 계약 baseline 대신 '진단용 축소 런'만 나옵니다.")
        return True

    def skip(self, what: str) -> bool:
        if self.blocked:
            LOG.info(f"KRX 차단 상태 — {what} 경로를 건너뜁니다.")
        return self.blocked


KRXBLOCK = KRXBlockState()


class KRXAuth:
    """KRX 데이터 마켓플레이스 세션 로그인(2025-12 인증 변경 대응). 실패해도 절대 죽지 않는다."""

    LOGIN_WARM1 = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    LOGIN_WARM2 = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    JSONDATA = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"

    def __init__(self, user: str, pw: str):
        self.user, self.pw = (user or "").strip(), (pw or "").strip()
        self.status = "NOT_ATTEMPTED"
        self.session_ok = False

    def login(self) -> bool:
        if not (self.user and self.pw):
            self.status = "NO_CREDENTIALS"
            LOG.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 불필요 경로로 진행합니다. "
                     "(marcap/FDR 캐시 → pykrx 비인증 → 네이버 → yfinance)")
            return False
        w1 = http_get(self.LOGIN_WARM1, source="krx", tries=1)
        if KRXBLOCK.note(w1):
            self.status = "IP_BLOCKED"
            return False
        http_get(self.LOGIN_WARM2, source="krx", tries=1, referer=self.LOGIN_WARM1)
        for extra in ({}, {"skipDup": "Y"}):
            body = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
                    "mbrId": self.user, "pw": self.pw, **extra}
            txt = http_post(self.LOGIN_POST, source="krx", data=body, referer=self.LOGIN_WARM1,
                            headers={"X-Requested-With": "XMLHttpRequest"})
            if txt is None:
                continue
            if re.search(r"CD011|중복\s*로그인", str(txt)):
                LOG.warn("KRX 중복 로그인(CD011) — 같은 계정이 다른 곳에서 로그인 중입니다. "
                         "skipDup 재시도 시 기존 세션이 강제 종료됩니다.")
                continue
            if not re.search(r"(실패|불일치|오류|error|fail|로그인이\s*필요)", str(txt)[:600], re.I):
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패 — ID/PW 확인. 폴백 경로로 정상 진행합니다.")
        return False

    def json_data(self, bld: str, **params) -> Optional[dict]:
        """마켓플레이스 bld 조회 — 세션 없으면 None (로그인 HTML 로 인한 하류 JSON 오류 예방).
        ★ 차단 안내페이지를 받으면 즉시 전 KRX 경로를 봉인한다(재시도 금지)."""
        if not self.session_ok or not KRXBLOCK.spend(1):
            return None
        body = {"bld": bld, "share": "1", "money": "1", "csvxls_isNo": "false", **params}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if KRXBLOCK.note(txt):
            return None
        if not txt or txt.lstrip()[:1] not in ("{", "["):
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None


KRX = KRXAuth(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW)


# ── DART 실시간 호출예산 ────────────────────────────────────────────────────────────────────
DART_BASE = "https://opendart.fss.or.kr/api/"
DART_OFFICIAL_DAILY = DART_ADVISORY_DAILY   # ★ 표시용 참고치일 뿐 — 이 숫자로 멈추지 않는다
DART_SAFETY_MARGIN = 0           # v1.0 은 200 을 미리 떼어놨다. 이제 떼지 않는다.
DART_STATUS_MSG = {
    "000": "정상", "010": "미등록 키", "011": "사용불가 키", "012": "IP 차단",
    "013": "데이터 없음", "014": "파일 없음", "020": "일일한도 초과", "021": "회사수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검", "900": "미정의 오류",
    "901": "계정 폐쇄",
}


class DartBudget:
    """오늘 사용량을 드라이브(공용 ns)에 영속 기록 — 같은 키를 쓰는 다른 전략과 합산 관리.

    ★ v1.1 정책 변경 (사용자 지적 반영)
      v1.0 은 20,000 에서 안전여유 200 을 뺀 값을 '내가 쓸 수 있는 한도'로 삼아 그 앞에서
      스스로 멈췄다. 이는 두 가지로 잘못이었다.
        · 실제 필요 호출은 배치(corp_code 100개/1호출) 덕에 1,400회 수준인데, 마치 한도가
          모자란 것처럼 보이게 만들었다. 필요량을 먼저 계산해 보여주지 않은 것이 원인이다.
        · 남은 호출량을 '실시간으로 확인해서 그만큼 쓴다'는 요구와 반대로, 미리 정한 상수로
          자기 검열을 했다.
      v1.1: 20,000 은 표시만 한다. 멈추는 유일한 조건은 DART 가 실제로 status=020 을
      돌려줄 때다(DART_STOP_ONLY_ON_020). 사용량·잔량은 실시간으로 계속 보고한다."""

    def __init__(self):
        self.today = _dt.date.today().isoformat()
        self.n = 0
        self.exhausted = False
        self._lk = threading.Lock()
        self._last_log = 0
        self._load()

    def _path(self) -> str:
        # 공용 네임스페이스에 둔다: 여러 전략이 같은 DART 키를 쓰므로 사용량은 합산돼야 한다
        return os.path.join(VAULT.ns["shared"], "index", "dart_usage.json")

    def _load(self):
        try:
            j = json.loads(open(self._path()).read())
            if j.get("date") == self.today:
                self.n = int(j.get("n", 0))
        except Exception:
            pass
        if self.n:
            LOG.info(f"오늘 이미 사용한 DART 호출 {self.n:,}건 — 남은 호출량 "
                     f"{self.remaining():,}건부터 이어서 씁니다.")

    def _save(self):
        try:
            atomic_write_text(self._path(), json.dumps(
                {"date": self.today, "n": self.n, "limit": DART_OFFICIAL_DAILY}))
        except Exception:
            pass

    def remaining(self) -> int:
        """참고 잔량(표시용). DART_STOP_ONLY_ON_020=True 면 이 값이 0이어도 계속 시도한다."""
        return max(0, DART_OFFICIAL_DAILY - DART_SAFETY_MARGIN - self.n)

    def refund(self, k: int = 1):
        if k <= 0:
            return
        with self._lk:
            self.n = max(0, self.n - k)

    def preflight(self, n_needed: int, what: str = "DART 배치"):
        """수집 시작 전에 '필요 호출 수 vs 오늘 사용량 vs 참고 잔량'을 표로 보여준다.
        v1.0 이 하지 않아 사용자가 '2~4만회가 왜 부족하냐'고 물어야 했던 정보다."""
        rem = self.remaining()
        rows = [["이번 실행에 필요한 호출(추정)", f"{n_needed:,}회"],
                ["오늘 이미 사용", f"{self.n:,}회"],
                ["참고 잔량(공식 한도 기준)", f"{rem:,}회"],
                ["중단 조건", "DART 가 status=020 을 실제로 반환할 때만"
                 if DART_STOP_ONLY_ON_020 else "참고 잔량 소진 시"]]
        if n_needed and rem:
            rows.append(["필요/잔량 비율", f"{100.0 * n_needed / max(rem, 1):.1f}%"])
        LOG.table(rows, ["항목", "값"], ["l", "r"], title=f"{what} 호출 예산 (실시간)")
        if n_needed > rem and not DART_STOP_ONLY_ON_020:
            LOG.warn("참고 잔량보다 필요량이 많습니다 — 받은 만큼 저장하고 내일 이어받습니다.")

    def take(self, k: int = 1) -> bool:
        with self._lk:
            if self.exhausted:
                return False
            if not DART_STOP_ONLY_ON_020 and self.remaining() < k:
                self.exhausted = True
                LOG.warn(f"DART 참고 잔량 소진(오늘 사용 {self.n:,}건). 받은 데이터는 "
                         f"드라이브에 저장되어 있으니 내일 재실행하면 이 지점부터 이어받습니다.")
                return False
            self.n += k
            if self.n - self._last_log >= 500:
                self._last_log = self.n
                self._save()
                over = "" if self.n <= DART_OFFICIAL_DAILY else " (참고치 초과 — API 가 " \
                                                               "허용하는 한 계속 씁니다)"
                LOG.info(f"DART 사용량 {self.n:,}건 · 참고 잔량 {self.remaining():,}건"
                         f"{over} (실시간)")
            return True

    def mark_exhausted(self):
        with self._lk:
            self.exhausted = True
            self._save()

    def close(self):
        self._save()


DBUDGET: Optional[DartBudget] = None


def dart_api(endpoint: str, params: dict, tries: int = 2) -> Optional[dict]:
    """★ 예산 정산: http_get 은 내부적으로 최대 tries 회 실제 요청을 보낸다. 최악을 먼저
    예약(take)하고 실제 시도 수를 알고 나면 차액을 환급 — 실사용량 과소집계로 한도를 넘는
    사고를 막는다."""
    if not DART_API_KEY:
        return None
    if DBUDGET is not None and not DBUDGET.take(tries):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    attempts = {"n": 0}
    js = http_json(DART_BASE + endpoint, source="dart", params=p, tries=tries,
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
                DBUDGET.mark_exhausted()
            LOG.warn(f"DART status={st}({DART_STATUS_MSG.get(st, '?')}) — 수집 중단, "
                     f"받은 만큼 저장. 내일 이어받습니다.")
        elif st in ("010", "011", "012", "901"):
            LOG.error(f"DART 인증 오류 status={st}({DART_STATUS_MSG.get(st, '?')}) — "
                      f"DART_API_KEY 를 확인하세요.")
        elif st != "013":
            LOG.debug(f"DART status={st}({DART_STATUS_MSG.get(st, '?')}) ep={endpoint}")
        return None
    return js


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 기초 (생존자편향 제거)                                            ║
# ║  다중 소스: ①FDR GitHub 캐시(listing/krx) ②동 delisting(★편향 제거 입력) ③KIND            ║
# ║            ④pykrx 분기 스냅샷(검증·보강) ⑤DART corpCode ⑥marcap(시총 스파인)              ║
# ║  설계 원칙: 유니버스 정확성은 상장일·폐지일·시총스파인만으로 성립. 스냅샷은 보강일 뿐.      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "src"]

FDR_CACHE = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
             "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_csv(kind: str, back_days: int = 14) -> Optional[pd.DataFrame]:
    """FDR 이 실제로 읽는 GitHub 캐시 CSV — 로그인 불필요 1순위 경로. 영업일만 존재하므로
    최근 날짜부터 거꾸로 훑는다."""
    today = _dt.date.today()
    for i in range(back_days):
        d = today - _dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        raw = http_get(FDR_CACHE.format(kind=kind, date=d.isoformat()),
                       source="generic", as_bytes=True, tries=1, timeout=25)
        if not raw or len(raw) < 200 or raw[:15].lstrip().startswith(b"404"):
            continue
        try:
            # ★ index_col=0 강제 금지 — delisting CSV 는 이름없는 인덱스가 없어 첫 실컬럼
            #   (Symbol=종목코드)이 인덱스로 먹혀 통째로 사라진다 = 곧 생존자편향.
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ISU_CD": str})
            if len(df.columns) and str(df.columns[0]).strip().lower() in (
                    "", "unnamed: 0", "unnamed:0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                return df
        except Exception:
            continue
    return None


def _lower_map(d: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in d.columns}


def fetch_fdr_listing() -> pd.DataFrame:
    cached = VAULT.get_table("fdr_cache_listing_krx", scope="shared", max_age_days=45)
    if cached is None and RUN_MODE == "CACHED":                # 계약 timed run: network=0
        cached = VAULT.get_table("fdr_cache_listing_krx", scope="shared")
    d = cached if cached is not None and len(cached) else \
        (_fdr_cache_csv("listing/krx") if RUN_MODE != "CACHED" else None)
    if d is None or not len(d):
        if fdr is not None and RUN_MODE != "CACHED":
            try:
                limiter("krx").wait()
                d = fdr.StockListing("KRX")
            except Exception as e:                                    # noqa
                LOG.warn(f"fdr.StockListing 실패({type(e).__name__}) — GitHub 캐시도 실패한 상태.")
                d = None
    if d is None or not len(d):
        LOG.warn("상장목록 미확보 — 종목 마스터는 marcap/스냅샷만으로 구성됩니다.")
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    cl = _lower_map(d)
    code_c = cl.get("code") or cl.get("symbol") or cl.get("isu_cd")
    name_c = cl.get("name") or cl.get("korean name") or cl.get("isu_nm")
    if not code_c or not name_c:
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[name_c].astype(str).str.strip(),
        "market": (d[cl["market"]].astype(str) if "market" in cl else "KRX"),
        "listing_date": as_ts_series(d[cl["listingdate"]]) if "listingdate" in cl else pd.NaT,
        "industry": (d[cl["sector"]].astype(str) if "sector" in cl
                     else d[cl["industry"]].astype(str) if "industry" in cl else ""),
    })
    t["delisting_date"] = pd.NaT
    t["corp_code"] = np.nan
    t["src"] = "fdr_listing"
    t = t.dropna(subset=["code"]).drop_duplicates("code")
    if cached is None or not len(cached):
        VAULT.put_table("fdr_cache_listing_krx", d, scope="shared", domain="universe",
                        source="fdr_github_cache")
    LOG.ok(f"상장목록 {len(t):,}건 (로그인 불필요 경로)")
    return t


def fetch_fdr_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거의 핵심 입력 — 상장폐지 종목 + 폐지일."""
    cached = VAULT.get_table("fdr_cache_listing_delisting", scope="shared", max_age_days=45)
    if cached is None and RUN_MODE == "CACHED":
        cached = VAULT.get_table("fdr_cache_listing_delisting", scope="shared")
    d = cached if cached is not None and len(cached) else \
        (_fdr_cache_csv("listing/delisting") if RUN_MODE != "CACHED" else None)
    if (d is None or not len(d)) and fdr is not None and RUN_MODE != "CACHED":
        try:
            limiter("krx").wait()
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
    if d is None or not len(d):
        LOG.warn("상장폐지 목록 미확보 — 생존자편향 제거가 marcap 스파인에만 의존합니다.")
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    cl = _lower_map(d)
    code_c = cl.get("symbol") or cl.get("code") or cl.get("isu_cd")
    if not code_c:
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    dl_c = next((cl[k] for k in ("delistingdate", "delisting_date", "dedate", "date") if k in cl),
                None)
    name_c = cl.get("name") or cl.get("isu_nm") or code_c
    t = pd.DataFrame({
        "code": d[code_c].map(to_code6),
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        "market": d[cl["market"]].astype(str) if "market" in cl else "KRX",
    }).dropna(subset=["code"])
    # 재상장/재폐지 중복은 '가장 늦은 폐지일'을 남긴다 (이른 것을 남기면 재상장 구간 유실)
    # na_position="first" — NaT 가 맨 뒤로 가서 실제 폐지일을 이기는 사고 방지(감사 중간)
    t = t.sort_values("delisting_date", na_position="first").drop_duplicates("code", keep="last")
    if cached is None or not len(cached):
        VAULT.put_table("fdr_cache_listing_delisting", d, scope="shared", domain="universe",
                        source="fdr_github_cache")
    LOG.ok(f"상장폐지 목록 {len(t):,}건 — 생존자편향 제거 입력 확보")
    return t


def fetch_kind_listing() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일·업종 보강. 종목코드 앞자리 0 유실을 to_code6 이 복구."""
    if RUN_MODE == "CACHED":
        return pd.DataFrame(columns=SEC_MASTER_COLS)
    for u in ("https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
              "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"):
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
            cl = {str(c).strip(): c for c in d.columns}
            code_c, name_c = cl.get("종목코드"), cl.get("회사명")
            if not code_c or not name_c:
                continue
            t = pd.DataFrame({
                "code": d[code_c].map(to_code6),
                "name": d[name_c].astype(str).str.strip(),
                "listing_date": as_ts_series(d[cl["상장일"]]) if "상장일" in cl else pd.NaT,
                "industry": d[cl["업종"]].astype(str) if "업종" in cl else "",
                "market": "", "delisting_date": pd.NaT, "corp_code": np.nan, "src": "kind",
            }).dropna(subset=["code"]).drop_duplicates("code")
            LOG.ok(f"KIND 상장법인 {len(t):,}건 (상장일 {int(t['listing_date'].notna().sum()):,}건)")
            return t
    LOG.warn("KIND 상장법인목록 미확보 — 상장일은 FDR/marcap 으로만 채웁니다.")
    return pd.DataFrame(columns=SEC_MASTER_COLS)


def fetch_dart_corpcode() -> pd.DataFrame:
    """corp_code ↔ 종목코드 매핑 — DART 재무 조회의 선행 조건."""
    cached = VAULT.get_table("dart_corpcode", scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART corpCode {len(cached):,}건 재사용")
        return cached
    if not DART_API_KEY or RUN_MODE == "CACHED":
        old = VAULT.get_table("dart_corpcode", scope="shared")     # 오래됐어도 없는 것보단 낫다
        if old is not None and len(old):
            LOG.info(f"공용 캐시(구버전)에서 corpCode {len(old):,}건 재사용")
            return old
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    raw = http_get(DART_BASE + "corpCode.xml", source="dart",
                   params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=3)
    if not raw or raw[:2] != b"PK":
        LOG.warn("DART corpCode.xml 수신 실패 — DART_API_KEY 를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code", "modify_date"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith(".xml"))
    except Exception:
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


def build_security_master() -> pd.DataFrame:
    """다중 소스 병합 종목 마스터. 폐지 종목 포함 — 빠뜨리면 곧 생존자편향."""
    fresh = VAULT.get_table("security_master", scope="shared", max_age_days=7)
    if fresh is not None and len(fresh):
        LOG.info(f"공용 캐시에서 종목 마스터 {len(fresh):,}건 재사용 (7일 이내 생성분)")
        for c in SEC_MASTER_COLS:
            if c not in fresh.columns:
                fresh[c] = np.nan
        # ★ 날짜 컬럼에 col()(숫자 강제)을 쓰면 날짜가 전부 NaN 이 된다 — as_ts_series 로만.
        fresh["listing_date"] = as_ts_series(fresh["listing_date"])
        fresh["delisting_date"] = as_ts_series(fresh["delisting_date"])
        fresh["code"] = fresh["code"].astype(str)
        PIPE.io("IN", "DRIVE", "security_master(재사용)", fresh, source="shared cache")
        return fresh

    parts: List[pd.DataFrame] = []
    lst = fetch_fdr_listing()
    if len(lst):
        parts.append(lst)
        PIPE.io("IN", "HTTP", "fdr:listing", lst, source="FDR GitHub cache")
    kind = fetch_kind_listing()
    if len(kind):
        parts.append(kind)
        PIPE.io("IN", "HTTP", "kind:corpList", kind, source="KIND")
    dead = fetch_fdr_delisting()
    PIPE.io("IN", "HTTP", "fdr:delisting", dead, source="FDR GitHub cache",
            ok=len(dead) > 0, note="생존자편향 제거 입력")
    if len(dead):
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market"]).copy()
        d2["listing_date"] = pd.NaT
        d2["industry"] = ""
        d2["corp_code"] = np.nan
        d2["src"] = "fdr_delisting"
        parts.append(d2)

    if not parts:
        cached = VAULT.get_table("security_master", scope="shared")
        if cached is not None and len(cached):
            LOG.warn("신규 소스 전멸 — 캐시된 종목 마스터로 진행합니다.")
            cached["listing_date"] = as_ts_series(col(cached, "listing_date"))
            cached["delisting_date"] = as_ts_series(col(cached, "delisting_date"))
            return cached
        raise RuntimeError(
            "종목 마스터를 만들 소스가 없습니다.\n"
            "  · raw.githubusercontent.com / kind.krx.co.kr 접근 가능 여부\n"
            "  · FinanceDataReader 설치 여부\n"
            "  · 드라이브 캐시(security_master.parquet) 존재 여부를 확인하세요.\n"
            "  RUN_MODE='SMOKE' 로는 네트워크 없이 계산경로를 검증할 수 있습니다.")

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
    cc = fetch_dart_corpcode()
    if len(cc):
        cc2 = cc.dropna(subset=["code"])[["code", "corp_code", "corp_name"]].drop_duplicates("code")
        agg = agg.merge(cc2, on="code", how="left")
        blank = agg["name"].astype(str).str.strip() == ""
        agg.loc[blank, "name"] = agg.loc[blank, "corp_name"].fillna("")
        agg = agg.drop(columns=["corp_name"])
    else:
        agg["corp_code"] = np.nan
    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    assert_no_dup_cols(agg, "security_master:final")

    n_del = int(agg["delisting_date"].notna().sum())
    LOG.table([["고유 종목", f"{len(agg):,}"],
               ["상장일 보유", f"{int(agg['listing_date'].notna().sum()):,}"],
               ["폐지일 보유", f"{n_del:,}"],
               ["corp_code 보유", f"{int(agg['corp_code'].notna().sum()):,}"]],
              ["항목", "건수"], ["l", "r"], title="종목 마스터 구성 (다중소스 병합)")
    if n_del < 200:
        LOG.warn("상장폐지 종목이 200건 미만 — 10년 구간 통상 1,000건 이상이어야 합니다. "
                 "생존자편향이 남을 수 있으니 해석 시 감안하세요.")
        PIPE.note("WARN: 상장폐지 표본 부족")
    VAULT.put_table("security_master", agg, scope="shared", domain="universe",
                    source="fdr+kind+dart")
    return agg


# ── 종목 유형 필터 (지수/비교 유니버스 공통) ────────────────────────────────────────────────
_NONCOMMON_PAT = re.compile(
    r"(스팩|SPAC|리츠|REIT|ETN|ETF|인프라|우$|우B$|우C$|[0-9]우|하이일드|채권|"
    r"KODEX|TIGER|KBSTAR|ARIRANG|HANARO|KOSEF|SOL |ACE |PLUS )", re.I)


def is_common_stock(code: str, name: str) -> bool:
    """보통주 판별: 코드 끝자리 0(신형은 '0'/'K'류 예외) + 이름 기반 스팩/리츠/ETP/우선주 제외.
    과거 시점의 관리종목 여부는 공개 이력이 없으므로 여기서 판단하지 않는다(문서화된 한계)."""
    if not code or len(code) != 6:
        return False
    if code[5] != "0":            # 우선주(5,7,9,K...) 및 신형 우선주 코드 제외
        return False
    nm = str(name or "")
    if _NONCOMMON_PAT.search(nm):
        return False
    return True


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-C  시가총액 스파인 — PIT 유니버스 · F6/F7 분모 · 비교전략의 기반                        ║
# ║                                                                                          ║
# ║  ★ v1.1 전면개편 이유 (v1.0 실운행 사고)                                                  ║
# ║    v1.0 은 ① 캐시 루트 하나만 뒤졌고 ② marcap 파일을 table 디렉토리 1단만 봤고            ║
# ║    ③ 폴백이 pykrx 하나뿐이었다. 사용자 윈도우 환경에서 marcap 이 다른 루트에 있었고        ║
# ║    pykrx 인증이 죽어 있어 **40개 분기 전부 시총 결손** → KOSPI200 재구성 0시점 →           ║
# ║    36분 실행 후 RuntimeError. 원인은 라인 버그가 아니라 '단일 경로 의존' 구조였다.          ║
# ║                                                                                          ║
# ║  v1.1 설계 원칙                                                                           ║
# ║    · 발견: 모든 읽기 루트를 재귀 탐색하고, 무엇을 어디서 몇 개 찾았는지 항상 표로 남긴다.   ║
# ║    · 폴백: 6단 체인(marcap → 공용캐시 → KRX bld → pykrx → FDR근사 → 거래대금 프록시).      ║
# ║           서로 다른 실패 원인(파일 없음 / 인증 없음 / 네트워크 없음)을 각각 우회한다.       ║
# ║    · 등급: 시점마다 어느 소스·어떤 정확도로 만들어졌는지 grade 를 붙여 산출물에 싣는다.     ║
# ║    · 영속: 어떤 경로로 얻었든 공용 인덱스(krx_market_cap_monthly)에 증분 적재 →            ║
# ║           다음 실행은 네트워크 0회. (전용/공용 인덱스 훼손 없음 — 합집합 병합만)            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MCAP_MIN_XSECT = 150     # 단면 채택 최소 종목수 — 모든 소스가 같은 기준을 쓴다
MCAP_SPINE_COLS = ["signal_date", "code", "marcap", "shares", "market", "close",
                   "size_rank", "src", "grade"]

# 소스별 정확도 등급 — 산출물(coverage / data_dictionary)에 그대로 기록된다.
MCAP_GRADE = {
    "marcap":    "PIT_EXACT",          # 폐지종목 포함 일별 실측 시총
    "cache":     "PIT_EXACT_CACHED",   # 이전 실행이 위 경로들로 얻어 저장해둔 단면
    "krx_bld":   "PIT_EXACT",          # KRX 전종목시세 bld(해당 거래일 실측 · 로그인 필요)
    "krx_api":   "PIT_EXACT",          # KRX Open API(해당 거래일 실측 · 로그인 불필요)
    "pykrx":     "PIT_EXACT",          # KRX 시총(해당 거래일 실측 · 로그인 필요)
    "fdr_apx":   "APPROX_SHARES_CONSTANT",   # 현재 주식수 × 과거 종가 (주식수 변동분 오차)
    "liq_proxy": "RANK_ONLY_LIQUIDITY",      # 시총 값 없음. 규모 순위만. F6/F7 분모 사용 불가
}


# ── marcap 파일 발견 (다중 루트 · 재귀) ──────────────────────────────────────────────────────
def _marcap_search_dirs() -> List[str]:
    """marcap 계열 파일을 찾을 디렉토리 전체 — 읽기 루트 + adopt 폴더 + 사용자 추가 경로."""
    dirs, seen = [], set()

    def _add(p: str):
        try:
            p = os.path.expanduser(str(p))
            rp = os.path.realpath(p)
        except Exception:
            return
        if rp in seen or not os.path.isdir(p):
            return
        seen.add(rp)
        dirs.append(p)

    roots = list(READ_ROOTS) if READ_ROOTS else ([VAULT.root] if VAULT is not None else [])
    for r in roots:
        _add(r)
    for r in roots:
        parent = os.path.dirname(r)
        for extra in MARCAP_EXTRA_DIRS:
            _add(str(extra).replace("{DRIVE}", parent))
    for extra in MARCAP_EXTRA_DIRS:
        _add(str(extra).replace("{DRIVE}", ""))
    return dirs


_MARCAP_NAME = re.compile(r"marcap", re.I)
_MARCAP_EXT = (".parquet", ".csv", ".csv.gz", ".pkl", ".feather")
_SKIP_DIRS = {".git", "__pycache__", "_locks", "_backup", "blob", ".ipynb_checkpoints",
              "node_modules", ".cache", "venv", ".venv"}


def _scan_marcap_files() -> Dict[str, List[str]]:
    """디렉토리별 marcap 후보 파일 목록. 깊이 제한 재귀 — 대용량 드라이브에서도 안전."""
    found: Dict[str, List[str]] = {}
    for base in _marcap_search_dirs():
        hits: List[str] = []
        base_depth = base.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(base):
            depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= MARCAP_SCAN_MAX_DEPTH:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for f in filenames:
                low = f.lower()
                if _MARCAP_NAME.search(low) and low.endswith(_MARCAP_EXT):
                    hits.append(os.path.join(dirpath, f))
            if len(hits) > 4000:                     # 병리적 케이스 방어
                break
        if hits:
            found[base] = sorted(hits)
    return found


class MarcapStore:
    """연도별 marcap 테이블의 지연 로더 (다중 루트 · 재귀 발견 · 다중 포맷).

    marcap 연도 parquet 은 상장폐지 종목의 과거 행을 그대로 포함하므로, 생존자편향 없는
    일별 (종목 × 시총 × 상장주식수 × 시장 × 시세) 단면을 신규 수집 없이 얻는 1순위 경로다."""

    _REN = {"date": "date", "code": "code", "name": "name", "market": "market",
            "marcap": "marcap", "stocks": "shares", "shares": "shares",
            "close": "close", "open": "open", "high": "high", "low": "low",
            "volume": "volume", "amount": "amount", "marketid": "market_id",
            "시가총액": "marcap", "상장주식수": "shares", "종가": "close", "시가": "open",
            "고가": "high", "저가": "low", "거래량": "volume", "거래대금": "amount",
            "날짜": "date", "종목코드": "code", "종목명": "name", "시장구분": "market"}

    def __init__(self):
        self._cache: Dict[int, Optional[pd.DataFrame]] = {}
        self._paths: Dict[int, str] = {}
        self._multi: List[str] = []          # 연도 표기가 없는 통합 파일(전 연도 포함 가능)
        self._multi_loaded = False
        self._multi_years: set = set()       # 통합 파일에서 나온 연도 (evict 후 재적재 판단용)
        self._scanned = False
        self._n_reads = 0
        self.report_rows: List[List[str]] = []

    # ── 발견 ────────────────────────────────────────────────────────────────────────────────
    def _scan(self):
        if self._scanned:
            return
        self._scanned = True
        by_dir = _scan_marcap_files()
        adopted = VAULT.adopted_paths(["marcap"], exts=(".parquet", ".csv")) if VAULT else []
        if adopted:
            by_dir.setdefault("(adopt 등록 경로)", []).extend(sorted(set(adopted)))

        for d, files in by_dir.items():
            years = set()
            for p in files:
                base = os.path.basename(p)
                m = re.search(r"((?:19|20)\d{2})", base)
                if not m:
                    self._multi.append(p)
                    continue
                y = int(m.group(1))
                years.add(y)
                cur = self._paths.get(y)
                if cur is None or self._better(p, cur):
                    self._paths[y] = p
            self.report_rows.append([
                d, f"{len(files)}개",
                (f"{min(years)}~{max(years)}" if years else "연도표기 없음")])

        if self._paths or self._multi:
            LOG.table(self.report_rows, ["탐색 경로", "marcap 파일", "연도"], ["l", "r", "l"],
                      title="시총 스파인(marcap) 발견 결과")
            LOG.ok(f"marcap 스파인 {len(self._paths)}개 연도 확보"
                   + (f" ({min(self._paths)}~{max(self._paths)})" if self._paths else "")
                   + (f" · 연도미표기 통합파일 {len(self._multi)}개" if self._multi else "")
                   + " — 시총/주식수/일봉을 신규 수집 없이 씁니다.")
        else:
            LOG.warn("marcap 계열 파일을 한 개도 찾지 못했습니다. 아래 경로를 모두 뒤졌습니다:")
            for d in _marcap_search_dirs():
                LOG.warn(f"    · {d}")
            LOG.warn("  → 파일이 다른 폴더에 있으면 상단 MARCAP_EXTRA_DIRS 에 폴더만 추가하세요. "
                     "없어도 KRX 전종목시세·pykrx·FDR 폴백으로 시총 스파인을 만듭니다.")

    @staticmethod
    def _better(new: str, cur: str) -> bool:
        """같은 연도 후보 중 우선순위: 원본(marcap_YYYY) > spine 정규화본, 그 다음 큰 파일."""
        nb, cb = os.path.basename(new).lower(), os.path.basename(cur).lower()
        n_spine, c_spine = ("spine" in nb), ("spine" in cb)
        if n_spine != c_spine:
            return c_spine                    # 현재가 spine 이면 원본으로 교체
        try:
            return os.path.getsize(new) > os.path.getsize(cur)
        except Exception:
            return False

    # ── 로드 ────────────────────────────────────────────────────────────────────────────────
    def _read_any(self, p: str) -> Optional[pd.DataFrame]:
        low = p.lower()
        try:
            if low.endswith(".parquet"):
                return read_parquet_safe(p)
            if low.endswith(".feather"):
                return pd.read_feather(p)
            if low.endswith(".pkl"):
                return pd.read_pickle(p)
            if low.endswith(".csv") or low.endswith(".csv.gz"):
                for enc in ("utf-8", "cp949", "utf-8-sig"):
                    try:
                        return pd.read_csv(p, encoding=enc, low_memory=False)
                    except UnicodeDecodeError:
                        continue
                return pd.read_csv(p, encoding="utf-8", errors="replace", low_memory=False)
        except Exception as e:                                          # noqa
            LOG.warn(f"marcap 파일 읽기 실패({type(e).__name__}): {os.path.basename(p)}")
        return None

    def _normalize(self, d: pd.DataFrame, where: str) -> Optional[pd.DataFrame]:
        cl = {str(c).strip().lower(): c for c in d.columns}
        out = pd.DataFrame(index=d.index)
        for low, std in self._REN.items():
            if low in cl and std not in out.columns:
                out[std] = d[cl[low]]
        if "code" not in out.columns or "date" not in out.columns:
            LOG.warn(f"marcap 스키마 미인식(code/date 없음) — 건너뜁니다: {where} "
                     f"[컬럼: {', '.join(map(str, list(d.columns)[:10]))}]")
            return None
        out["code"] = out["code"].astype(str).map(to_code6)
        out["date"] = as_ts_series(out["date"])
        out = out.dropna(subset=["code", "date"])
        for c in ("marcap", "shares", "close", "open", "high", "low", "volume", "amount"):
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce")
        out["market"] = (out["market"].astype(str).str.upper()
                         if "market" in out.columns else "")
        return downcast(out) if len(out) else None

    def _load_multi(self, force: bool = False):
        """연도 표기가 없는 통합 marcap 파일을 읽어 연도별로 쪼개 캐시에 채운다.

        ★ 감사 치명(C1): v1.1 초안은 `_multi_loaded` 를 한 번 세우면 다시 내리지 않았다.
          그런데 evict() 는 캐시를 비우므로, 통합파일(marcap.parquet 처럼 파일명에 연도가 없는
          배포본)을 쓰는 환경에서는 첫 evict 이후 모든 연도가 영구 소실됐다 —
          `year()` 가 `_paths` 에도 없고 `_multi_loaded` 가 True 라서 곧바로 None 을 캐싱했다.
          결과: 첫 실행(캐시 없음)에서 bootstrap_calendar 가 evict 하는 순간 시총 스파인이
          전멸하고 40개 분기 유니버스가 통째로 사라진다. → 재적재 가능하게 고친다."""
        if self._multi_loaded and not force:
            return
        self._multi_loaded = True
        for p in self._multi[:3]:                       # 통합파일은 최대 3개까지만
            d = self._read_any(p)
            if d is None or not len(d):
                continue
            nd = self._normalize(d, os.path.basename(p))
            if nd is None:
                continue
            LOG.ok(f"통합 marcap 파일에서 {len(nd):,}행 로드 — 연도별로 분할합니다: "
                   f"{os.path.basename(p)}")
            for y, g in nd.groupby(nd["date"].dt.year):
                y = int(y)
                self._multi_years.add(y)
                if self._cache.get(y) is None:
                    self._cache[y] = g.reset_index(drop=True)

    def year(self, y: int) -> Optional[pd.DataFrame]:
        self._scan()
        y = int(y)
        if y in self._cache:
            return self._cache[y]
        p = self._paths.get(y)
        if p:
            d = self._read_any(p)
            out = self._normalize(d, os.path.basename(p)) if d is not None else None
            self._cache[y] = out
            self._n_reads += 1
            if out is not None:
                PIPE.io("IN", "DRIVE", f"marcap_{y}", out, source=os.path.basename(p))
            return out
        # 연도 표기가 없는 통합 파일 경로 — 아직 안 읽었거나, evict 로 비워졌으면 다시 읽는다
        if self._multi and (not self._multi_loaded or y in self._multi_years):
            self._load_multi(force=True)
            self._n_reads += 1
            if y in self._cache:
                return self._cache[y]
        self._cache[y] = None
        return None

    def years_available(self) -> List[int]:
        self._scan()
        ys = set(self._paths)
        if self._multi:
            self._load_multi()
            ys |= set(self._multi_years)
            ys |= {y for y, v in self._cache.items() if v is not None}
        return sorted(ys)

    def trim(self, max_mb: Optional[float] = None):
        """★ 감사 중간(M2): v1.1 초안은 소비자(캘린더·스파인·가격)마다 evict(()) 를 불러
        같은 연도 parquet 을 실행당 3번 읽었다(34회 읽기 + gc 34회). 연도 프레임은 전부
        합쳐도 보통 수백 MB 라 굳이 버릴 이유가 없다 → 예산 안에서는 유지한다."""
        budget = float(max_mb if max_mb is not None
                       else min(4000.0, MEM_BUDGET_GB * 1000.0 * 0.25))
        tot = sum(mem_mb(v) for v in self._cache.values() if v is not None)
        if tot <= budget:
            return
        for y in sorted(self._cache):                    # 오래된 연도부터 해제
            if tot <= budget:
                break
            v = self._cache.get(y)
            if v is not None:
                tot -= mem_mb(v)
                self._cache.pop(y, None)
        gc.collect()
        LOG.debug(f"marcap 캐시 정리 — 예산 {budget:.0f}MB 내로 축소")

    def evict(self, keep_years: Sequence[int] = ()):
        keep = set(int(y) for y in keep_years)
        for y in list(self._cache):
            if y not in keep:
                self._cache.pop(y, None)
        gc.collect()


MARCAP = MarcapStore()


# ── marcap 공개 데이터셋 자동 확보 (KRX 차단·파일 부재 대응) ───────────────────────────────────
def download_marcap_years(years: Sequence[int], force: bool = False) -> int:
    """공개 marcap 데이터셋에서 필요한 연도만 내려받아 공용 인덱스에 parquet 으로 저장한다.

    ★ 왜 이게 결정적인가 (실운행 사고 2회차)
      KRX Data Marketplace 가 이 IP 를 7일 차단해 시총·지수구성·수급 경로가 모두 죽었고,
      시총이 '거래대금 순위 프록시'로 떨어져 F6/F7 분모가 사라졌다(= 적격종목 0).
      marcap 데이터셋은 상장폐지 종목까지 포함한 일별 시총·주식수·시세를 공개하므로,
      이 한 경로로 시총·일봉·생존자편향을 전부 해결하고 KRX 를 아예 쓰지 않아도 된다.
    저장 이름은 marcap_YYYY.parquet — MarcapStore 가 다음 실행에서 그대로 찾아 쓴다."""
    if not MARCAP_AUTO_DOWNLOAD or RUN_MODE == "CACHED":
        return 0
    have = set(MARCAP.years_available())
    need = [int(y) for y in sorted(set(int(y) for y in years)) if force or int(y) not in have]
    if not need:
        return 0
    LOG.info(f"marcap 공개 데이터셋에서 {len(need)}개 연도({min(need)}~{max(need)})를 "
             f"1회 내려받습니다 — 이후 실행은 네트워크 0회로 재사용합니다.")
    n_ok, tot_rows, tot_bytes = 0, 0, 0
    for y in tqdm(need, desc="marcap 다운로드", ncols=88, leave=False):
        raw = None
        used = ""
        for tpl in MARCAP_GH_TEMPLATES:
            url = tpl.format(y=y)
            raw = http_get(url, source="generic", tries=2, as_bytes=True)
            if raw and len(raw) > 20_000:
                used = url
                break
            raw = None
        if raw is None:
            LOG.warn(f"marcap {y}년 파일을 받지 못했습니다 — 이 연도는 다른 폴백으로 갑니다.")
            continue
        try:
            buf = io.BytesIO(raw)
            if used.endswith(".parquet"):
                d = pd.read_parquet(buf)
            elif used.endswith(".gz"):
                import gzip
                with gzip.open(buf, "rb") as gz:
                    d = pd.read_csv(gz, dtype={"Code": str, "code": str}, low_memory=False)
            else:
                d = pd.read_csv(buf, dtype={"Code": str, "code": str}, low_memory=False)
        except Exception as e:                                          # noqa
            LOG.warn(f"marcap {y}년 파싱 실패({type(e).__name__}) — 건너뜁니다.")
            continue
        nd = MARCAP._normalize(d, f"marcap-{y} (다운로드)")
        if nd is None or not len(nd):
            continue
        VAULT.put_table(f"marcap_{y}", nd, scope="shared", domain="price",
                        source=f"FinanceData/marcap 공개 데이터셋 ({used})")
        MARCAP._paths[y] = os.path.join(VAULT.table_dir("shared"), f"marcap_{y}.parquet")
        MARCAP._cache.pop(y, None)
        n_ok += 1
        tot_rows += len(nd)
        tot_bytes += len(raw)
    if n_ok:
        LOG.ok(f"marcap {n_ok}개 연도 확보 — {tot_rows:,}행 / 원본 {tot_bytes/1e6:.0f}MB 를 "
               f"공용 인덱스(_shared)에 저장했습니다. 상장폐지 종목이 포함되어 "
               f"생존자편향 없는 PIT 시총·일봉이 완성됩니다.")
        MARCAP.trim()
    else:
        LOG.warn("marcap 자동 다운로드가 전부 실패했습니다 — 네트워크(raw.githubusercontent.com) "
                 "접근을 확인하거나, 데이터셋을 직접 받아 MARCAP_EXTRA_DIRS 폴더에 두세요.")
    return n_ok


# ── 소스 ③ KRX 마켓플레이스 전종목시세 (한 호출로 전 종목 단면) ───────────────────────────────
_KRX_QUOTE_BLD = "dbms/MDC/STAT/standard/MDCSTAT01501"
_KRX_QUOTE_FIELDS = {"ISU_SRT_CD": "code", "MKTCAP": "marcap", "LIST_SHRS": "shares",
                     "TDD_CLSPRC": "close", "TDD_OPNPRC": "open", "TDD_HGPRC": "high",
                     "TDD_LWPRC": "low", "ACC_TRDVOL": "volume", "ACC_TRDVAL": "amount",
                     "MKT_NM": "market", "MKT_ID": "market_id", "ISU_ABBRV": "name"}


def _num_kr(s: pd.Series) -> pd.Series:
    """KRX 응답의 '1,234' / '-' / '' 를 숫자로."""
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False)
                         .str.replace("−", "-", regex=False)
                         .replace({"-": np.nan, "": np.nan, "nan": np.nan}), errors="coerce")


def krx_all_quotes(trd_dd: str, mkt_id: str = "ALL") -> Optional[pd.DataFrame]:
    """KRX '전종목 시세' — 임의 과거 거래일의 전 종목 (종가·시총·상장주식수) 단면.
    한 번의 호출로 2,700종목이 오므로 시총 스파인 폴백 중 가장 효율적이다."""
    js = KRX.json_data(_KRX_QUOTE_BLD, mktId=mkt_id, trdDd=str(trd_dd).replace("-", ""))
    if not isinstance(js, dict):
        return None
    items = js.get("OutBlock_1") or js.get("output") or js.get("block1") or []
    if not isinstance(items, list) or not items:
        return None
    d = pd.DataFrame(items)
    if not len(d):
        return None
    out = pd.DataFrame()
    for src, dst in _KRX_QUOTE_FIELDS.items():
        if src in d.columns:
            out[dst] = d[src]
    if "code" not in out.columns:
        LOG.debug(f"KRX 전종목시세 응답에 ISU_SRT_CD 없음 (키: "
                  f"{', '.join(map(str, list(d.columns)[:12]))})")
        return None
    out["code"] = out["code"].astype(str).map(to_code6)
    for c in ("marcap", "shares", "close", "open", "high", "low", "volume", "amount"):
        if c in out.columns:
            out[c] = _num_kr(out[c])
    out["market"] = (out["market"].astype(str).str.upper()
                     if "market" in out.columns else "")
    out = out.dropna(subset=["code"]).drop_duplicates("code")
    return out if len(out) else None


# ── 소스 ④ KRX Open API (data-dbg) — 로그인 세션과 독립. 무료 키만 있으면 된다 ────────────────
#  ★ 실측 확인: openapi.krx.co.kr 은 '키 발급·이용신청 포털'이고 JSON API 는
#    data-dbg.krx.co.kr 이다(두 호스트는 같은 Akamai 엣지로 해석되므로 호스트 교체는 무의미).
#    실운행에서 9초씩 타임아웃한 원인은 호스트가 아니라 **AUTH_KEY 전달 방식**이었다 —
#    공개 클라이언트(pykrx-openapi)는 헤더가 아니라 **쿼리 파라미터**로 보낸다. 둘 다 시도한다.
#    ⚠ 그리고 Open API 에는 투자자별(기관·외국인) 순매수 엔드포인트가 아예 없다(31개 전수 확인)
#      → F6/F7 은 이 경로로 만들 수 없다. 시총·주식수 용도로만 쓴다.
_KRX_API_HOSTS = ["https://data-dbg.krx.co.kr/svc/apis/sto/"]
_KRX_API_EPS = (("stk_bydd_trd", "KOSPI"), ("ksq_bydd_trd", "KOSDAQ"))


def krx_openapi_quotes(bas_dd: str) -> Optional[pd.DataFrame]:
    """KRX Open API 일별 전종목 시세(시총·상장주식수 포함, 2010-01-04~).

    ★ 이 API 는 오류도 HTTP 200 으로 준다 — respCode/respMsg 를 반드시 본다.
      또 {"OutBlock_1":[]} 는 휴장/잘못된 날짜/미래일자/파라미터 누락에 모두 동일하게
      나오므로 '빈 응답 = 휴장' 이라고 추론하면 안 된다(그래서 빈 응답은 실패로 취급)."""
    if not KRX_OPENAPI_KEY:
        return None
    rows = []
    for ep, mkt in _KRX_API_EPS:
        js = None
        _bd = str(bas_dd).replace("-", "")
        # ① 쿼리 파라미터 방식(공개 클라이언트 구현) ② 헤더 방식(KRX 문서 표기) — 순서대로
        for _mode in ("query", "header"):
            if _mode == "query":
                _kw = {"params": {"AUTH_KEY": KRX_OPENAPI_KEY, "basDd": _bd}}
            else:
                _kw = {"params": {"basDd": _bd}, "headers": {"AUTH_KEY": KRX_OPENAPI_KEY}}
            _txt = http_get(_KRX_API_HOSTS[0] + ep, source="krx_api", tries=1, **_kw)
            if KRXBLOCK.note(_txt):
                return None
            if not _txt:
                continue
            try:
                js = json.loads(_txt)
            except Exception:
                js = None
            if isinstance(js, dict):
                break
        if not isinstance(js, dict):
            continue
        rc = str(js.get("respCode") or "")
        if rc and rc != "200":
            LOG.debug(f"KRX Open API {ep} respCode={rc} ({js.get('respMsg')})")
            continue
        items = js.get("OutBlock_1") or js.get("output") or []
        if not isinstance(items, list) or not items:
            continue
        d = pd.DataFrame(items)
        code_c = next((c for c in ("ISU_SRT_CD", "ISU_CD", "SRT_CD") if c in d.columns), None)
        if code_c is None:
            continue
        out = pd.DataFrame({"code": d[code_c].astype(str).map(to_code6)})
        for src, dst in (("MKTCAP", "marcap"), ("LIST_SHRS", "shares"),
                         ("TDD_CLSPRC", "close")):
            out[dst] = _num_kr(d[src]) if src in d.columns else np.nan
        out["market"] = mkt
        rows.append(out.dropna(subset=["code"]))
    if not rows:
        return None
    out = pd.concat(rows, ignore_index=True).drop_duplicates("code")
    return out if len(out) else None


# ── 소스 ⑤ pykrx 시총 단면 ───────────────────────────────────────────────────────────────────
def pykrx_mcap(bd: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        d = KRXG.call(pykrx_stock.get_market_cap_by_ticker, str(bd).replace("-", ""),
                      market=mkt)
        if d is None or not len(d):
            continue
        d = d.reset_index()
        cl = {str(c): c for c in d.columns}
        tick = cl.get("티커") or d.columns[0]
        rows.append(pd.DataFrame({
            "code": d[tick].astype(str).map(to_code6),
            "marcap": pd.to_numeric(d[cl["시가총액"]], errors="coerce")
            if "시가총액" in cl else np.nan,
            "shares": pd.to_numeric(d[cl["상장주식수"]], errors="coerce")
            if "상장주식수" in cl else np.nan,
            "close": pd.to_numeric(d[cl["종가"]], errors="coerce") if "종가" in cl else np.nan,
            "market": mkt}))
    if not rows:
        return None
    out = pd.concat(rows, ignore_index=True).dropna(subset=["code"]).drop_duplicates("code")
    return out if len(out) else None


# ── 소스 ⑤ FDR 현재 상장주식수 (과거 종가와 곱해 근사 시총) ───────────────────────────────────
_FDR_SHARES_CACHE: Dict[str, pd.DataFrame] = {}


def fdr_current_shares() -> Optional[pd.DataFrame]:
    """FDR 상장목록의 현재 상장주식수/시장. 과거 시점에 그대로 쓰면 근사(주식수 변동 무시)."""
    if "v" in _FDR_SHARES_CACHE:
        return _FDR_SHARES_CACHE["v"]
    _FDR_SHARES_CACHE["v"] = pd.DataFrame()
    if fdr is None or RUN_MODE == "CACHED":
        return None
    for key in ("KRX", "KRX-DESC", "KOSPI"):
        try:
            limiter("krx").wait()
            # ★ FDR 의 상장목록 리더는 내부적으로 data.krx.co.kr 을 찔러 max_work_dt 를 받는다.
            #   차단 상태에서는 HTML 안내페이지를 그대로 stdout 에 print 하고 ValueError 를
            #   던진다(실행 로그가 수백 줄 HTML 로 오염됨) → 삼키고 차단으로 기록한다.
            with _quiet_stdout() as _buf:
                d = fdr.StockListing(key)
            KRXBLOCK.note(_buf.getvalue())
        except Exception:
            continue
        if d is None or not len(d):
            continue
        cl = {str(c).strip().lower(): c for c in d.columns}
        code_c = next((cl[k] for k in ("code", "symbol", "종목코드") if k in cl), None)
        sh_c = next((cl[k] for k in ("stocks", "shares", "상장주식수", "listedshares")
                     if k in cl), None)
        mc_c = next((cl[k] for k in ("marcap", "시가총액", "marketcap") if k in cl), None)
        if code_c is None or (sh_c is None and mc_c is None):
            continue
        out = pd.DataFrame({"code": d[code_c].astype(str).map(to_code6)})
        out["shares"] = pd.to_numeric(d[sh_c], errors="coerce") if sh_c else np.nan
        out["marcap_now"] = pd.to_numeric(d[mc_c], errors="coerce") if mc_c else np.nan
        mk_c = next((cl[k] for k in ("market", "시장구분", "marketid") if k in cl), None)
        out["market"] = d[mk_c].astype(str).str.upper() if mk_c else ""
        out = out.dropna(subset=["code"]).drop_duplicates("code")
        if out["shares"].notna().sum() < 100 and out["marcap_now"].notna().sum() < 100:
            continue
        LOG.info(f"FDR 상장목록에서 현재 상장주식수 {int(out['shares'].notna().sum()):,}종목 "
                 f"확보 — 과거 시총 '근사'용으로만 씁니다(등급 APPROX_SHARES_CONSTANT).")
        _FDR_SHARES_CACHE["v"] = out
        return out
    return None


# ══ 시가총액 스파인 빌더 ═════════════════════════════════════════════════════════════════════
class MarketcapSpine:
    """신호일 목록에 대한 (code, marcap, shares, market, close, size_rank) 단면 일괄 생성.

    한 시점이라도 비지 않게 6단 폴백을 돌리고, 시점별로 어느 소스가 쓰였는지 기록한다.
    성공한 단면은 전부 공용 캐시에 증분 적재하므로 다음 실행은 네트워크 0회로 끝난다."""

    def __init__(self):
        self.per_date: Dict[pd.Timestamp, str] = {}     # 시점 → 사용 소스
        self.n_by_src: Counter = Counter()
        self.panel = pd.DataFrame(columns=MCAP_SPINE_COLS)

    # ── ① marcap 연도 파일 ──────────────────────────────────────────────────────────────────
    def _from_marcap(self, dates: List[pd.Timestamp], tol_days: int = 10
                     ) -> Dict[pd.Timestamp, pd.DataFrame]:
        got: Dict[pd.Timestamp, pd.DataFrame] = {}
        avail = set(MARCAP.years_available())
        if not avail:
            return got
        by_year: Dict[int, List[pd.Timestamp]] = defaultdict(list)
        for d in dates:
            by_year[int(d.year)].append(d)
        for y in sorted(by_year):
            need = by_year[y]
            frames = [f for f in (MARCAP.year(y),
                                  MARCAP.year(y - 1) if min(need).month <= 1 else None)
                      if f is not None and len(f)]
            if not frames:
                continue
            dd = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
            for d in need:
                sub = dd[(dd["date"] <= d) & (dd["date"] >= d - pd.Timedelta(days=tol_days))]
                if not len(sub):
                    continue
                last = sub["date"].max()
                snap = sub[sub["date"] == last]
                keep = pd.DataFrame({
                    "code": snap["code"].astype(str),
                    "marcap": col(snap, "marcap"), "shares": col(snap, "shares"),
                    "market": snap["market"] if "market" in snap.columns else "",
                    "close": col(snap, "close")})
                keep = keep.dropna(subset=["code"]).drop_duplicates("code")
                if len(keep) >= MCAP_MIN_XSECT:
                    got[d] = keep
            MARCAP.trim()
        return got

    # ── ② 공용 캐시 ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _from_cache(dates: List[pd.Timestamp], tol_days: int = 10
                    ) -> Dict[pd.Timestamp, pd.DataFrame]:
        got: Dict[pd.Timestamp, pd.DataFrame] = {}
        mc = VAULT.get_table("krx_market_cap_monthly", scope="shared",
                             union_keys=["code", "date"])
        if mc is None or not len(mc):
            return got
        cl = {str(c).lower(): c for c in mc.columns}
        dc = cl.get("date") or cl.get("month") or cl.get("signal_date")
        cc = cl.get("code")
        if not dc or not cc:
            return got
        m = pd.DataFrame({"date": as_ts_series(mc[dc]),
                          "code": mc[cc].astype(str).map(to_code6)})
        for k, std in (("marcap", "marcap"), ("shares", "shares"), ("close", "close")):
            m[std] = pd.to_numeric(mc[cl[k]], errors="coerce") if k in cl else np.nan
        m["market"] = mc[cl["market"]].astype(str).str.upper() if "market" in cl else ""
        m = m.dropna(subset=["date", "code"])
        if not len(m):
            return got
        LOG.info(f"공용 캐시 시총 단면 {len(m):,}행 재사용 "
                 f"({m['date'].nunique()}개 날짜, ~{m['date'].max():%Y-%m-%d})")
        for d in dates:
            sub = m[(m["date"] <= d) & (m["date"] >= d - pd.Timedelta(days=tol_days))]
            if not len(sub):
                continue
            last = sub["date"].max()
            snap = sub[sub["date"] == last].drop(columns=["date"]).drop_duplicates("code")
            if len(snap) >= MCAP_MIN_XSECT and \
                    int(snap["marcap"].notna().sum()) >= MCAP_MIN_XSECT:
                got[d] = snap.reset_index(drop=True)
        return got

    # ── ③④ 네트워크 실측 (KRX bld → pykrx) ─────────────────────────────────────────────────
    def _from_network(self, dates: List[pd.Timestamp], want: str) -> Dict[pd.Timestamp,
                                                                         pd.DataFrame]:
        got: Dict[pd.Timestamp, pd.DataFrame] = {}
        if not dates or RUN_MODE == "CACHED":
            return got
        if want in ("krx_bld", "pykrx") and KRXBLOCK.skip(
                {"krx_bld": "전종목시세 bld", "pykrx": "pykrx 시총"}[want]):
            return got
        if want == "krx_bld" and not KRX.session_ok:
            LOG.info("KRX 마켓플레이스 세션이 없어 전종목시세 bld 경로를 건너뜁니다. "
                     "(2025-12 이후 bld 계열은 전부 로그인이 필요합니다 — 상단 "
                     "KRX_MARKETPLACE_ID/PW 를 채우면 시점당 1호출로 정확한 시총을 씁니다.)")
            return got
        if want == "krx_api" and not KRX_OPENAPI_KEY:
            LOG.info("KRX Open API 키가 없어 이 경로를 건너뜁니다 "
                     "(data-dbg.krx.co.kr 무료 발급 · 로그인 세션과 독립적으로 동작합니다).")
            return got
        if want == "pykrx" and pykrx_stock is None:
            LOG.info("pykrx 를 쓸 수 없어 시총 pykrx 경로를 건너뜁니다.")
            return got
        if want == "pykrx":
            KRXG.warmup()
        fetcher = {"krx_bld": lambda b: krx_all_quotes(b),
                   "krx_api": krx_openapi_quotes,
                   "pykrx": pykrx_mcap}[want]
        n_call = {"krx_bld": "1", "krx_api": "2", "pykrx": "2"}[want]
        label = {"krx_bld": "KRX 전종목시세(bld)", "krx_api": "KRX Open API",
                 "pykrx": "pykrx 시총"}[want]
        fail = 0
        LOG.info(f"{label}로 시총 단면 {len(dates)}개 시점 수집 (시점당 {n_call}호출 · 직렬)")
        for d in tqdm(dates, desc=label, ncols=88, leave=False):
            bd = _prev_business_guess(d)
            snap = fetcher(bd)
            n_mc = int(col(snap, "marcap").notna().sum()) if snap is not None else 0
            if snap is None or len(snap) < MCAP_MIN_XSECT or n_mc < MCAP_MIN_XSECT:
                fail += 1
                if fail >= 5 and not got:
                    LOG.warn(f"{label} 경로가 {fail}회 연속 무응답 — 다음 폴백으로 넘어갑니다.")
                    break
                continue
            fail = 0
            keep = snap.reindex(columns=["code", "marcap", "shares", "market", "close"])
            got[d] = keep.dropna(subset=["code"]).drop_duplicates("code").reset_index(drop=True)
        # ★ 부분응답 방어: 응답 종목수가 중앙값의 80% 미만인 단면은 '반쪽 데이터'다. 그대로 믿으면
        #   그 분기 유니버스만 조용히 쪼그라들어 선택편향이 된다(TCD v2 에서 실제로 겪은 사고).
        if len(got) >= 4:
            cnt = pd.Series({d: len(g) for d, g in got.items()})
            med = float(cnt.median())
            bad = [d for d, n in cnt.items() if n < med * 0.80]
            for d in bad:
                got.pop(d, None)
            if bad:
                LOG.warn(f"{label} 부분응답 {len(bad)}개 시점 폐기(종목수가 중앙값 "
                         f"{med:,.0f}의 80% 미만) — 다음 폴백에서 다시 시도합니다: "
                         f"{[f'{d:%Y-%m}' for d in bad[:6]]}")
        return got

    # ── ⑤ FDR 근사 (현재 주식수 × PIT 종가) ─────────────────────────────────────────────────
    @staticmethod
    def _from_fdr_apx(dates: List[pd.Timestamp], pxc: Optional[pd.DataFrame]
                      ) -> Dict[pd.Timestamp, pd.DataFrame]:
        got: Dict[pd.Timestamp, pd.DataFrame] = {}
        if pxc is None or not len(pxc) or not dates:
            return got
        sh = fdr_current_shares()
        if sh is None or not len(sh) or sh["shares"].notna().sum() < 100:
            return got
        smap = sh.dropna(subset=["shares"]).set_index("code")
        for d in dates:
            sub = pxc[(pxc["date"] <= d) & (pxc["date"] >= d - pd.Timedelta(days=10))]
            if not len(sub):
                continue
            last = sub["date"].max()
            snap = (sub[sub["date"] == last][["code", "close"]]
                    .dropna(subset=["code", "close"]).drop_duplicates("code"))
            snap = snap.join(smap[["shares", "market"]], on="code")
            snap = snap.dropna(subset=["shares"])
            if len(snap) < MCAP_MIN_XSECT:
                continue
            snap["marcap"] = snap["close"].astype(float) * snap["shares"].astype(float)
            got[d] = snap.reindex(columns=["code", "marcap", "shares", "market", "close"]) \
                         .reset_index(drop=True)
        return got

    # ── ⑥ 거래대금 순위 프록시 (캐시만 · 시총 값은 만들지 않는다) ────────────────────────────
    @staticmethod
    def _from_liquidity(dates: List[pd.Timestamp], pxc: Optional[pd.DataFrame]
                        ) -> Dict[pd.Timestamp, pd.DataFrame]:
        got: Dict[pd.Timestamp, pd.DataFrame] = {}
        if pxc is None or not len(pxc) or not dates:
            return got
        LOG.warn("시총 실측을 어느 경로로도 얻지 못한 시점이 있어 '20일 평균 거래대금 순위'를 "
                 "규모 대용으로 씁니다. ★이 시점의 marcap 은 값이 없으므로 F6/F7(순매수/시총)은 "
                 "결측 처리되고, 유니버스 규모 순위에만 사용됩니다(등급 RANK_ONLY_LIQUIDITY).")
        if col(pxc, "amount").notna().sum() < 1000:
            LOG.warn("캐시 일봉에 거래대금(amount)이 거의 없어 거래대금 프록시도 만들 수 없습니다.")
            return got
        for d in dates:
            w = pxc[(pxc["date"] <= d) & (pxc["date"] > d - pd.Timedelta(days=40))]
            if not len(w):
                continue
            w = w.assign(amount=col(w, "amount"))
            amt = w.groupby("code", observed=True)["amount"].mean()
            lastpx = (w.sort_values("date").groupby("code", observed=True)["close"].last())
            snap = pd.DataFrame({"code": amt.index.astype(str), "marcap": np.nan,
                                 "shares": np.nan, "market": "",
                                 "close": lastpx.reindex(amt.index).to_numpy(),
                                 "_liq": amt.to_numpy()})
            snap = snap[snap["_liq"].fillna(0) > 0]
            if len(snap) < MCAP_MIN_XSECT:
                continue
            snap["size_rank"] = snap["_liq"].rank(ascending=False, method="first")
            got[d] = snap.drop(columns=["_liq"]).reset_index(drop=True)
        return got

    # ── 조립 ────────────────────────────────────────────────────────────────────────────────
    def build(self, dates: Sequence[pd.Timestamp], pxc: Optional[pd.DataFrame] = None
              ) -> pd.DataFrame:
        dates = [pd.Timestamp(d) for d in dates]
        remaining = list(dates)
        collected: Dict[pd.Timestamp, Tuple[str, pd.DataFrame]] = {}

        # ★ 로컬·드라이브에 marcap 이 없으면 먼저 공개 데이터셋으로 확보한다. 이 한 수로
        #   시총(PIT 정확)·일봉(폐지종목 포함)·F6/F7 분모가 모두 해결되고 KRX 의존이 사라진다.
        if "marcap" in MCAP_SPINE_SOURCES and not MARCAP.years_available():
            yrs = sorted({int(d.year) for d in dates} | {int(d.year) - 1 for d in dates})
            download_marcap_years(yrs)

        chain = [
            ("marcap",    lambda ds: self._from_marcap(ds)),
            ("cache",     lambda ds: self._from_cache(ds)),
            ("krx_bld",   lambda ds: self._from_network(ds, "krx_bld")),
            ("krx_api",   lambda ds: self._from_network(ds, "krx_api")),
            ("pykrx",     lambda ds: self._from_network(ds, "pykrx")),
            ("fdr_apx",   lambda ds: self._from_fdr_apx(ds, pxc)),
            ("liq_proxy", lambda ds: self._from_liquidity(ds, pxc)),
        ]
        for name, fn in chain:
            if not remaining:
                break
            if name not in MCAP_SPINE_SOURCES:
                continue
            try:
                got = fn(list(remaining))
            except Exception as e:                                      # noqa
                LOG.warn(f"시총 스파인 소스 '{name}' 실패({type(e).__name__}: {e}) — "
                         f"다음 소스로 계속합니다.")
                got = {}
            got = {d: g for d, g in (got or {}).items() if g is not None and len(g)}
            if got:
                for d, g in got.items():
                    collected[d] = (name, g)
                    self.per_date[d] = name
                self.n_by_src[name] += len(got)
                LOG.ok(f"시총 스파인 [{name}] {len(got)}개 시점 확보 "
                       f"(누적 {len(collected)}/{len(dates)}) · 등급 {MCAP_GRADE[name]}")
                remaining = [d for d in remaining if d not in collected]

        if remaining:
            LOG.error(f"시총 단면을 만들지 못한 시점 {len(remaining)}개: "
                      f"{[f'{d:%Y-%m}' for d in remaining[:8]]}")
            LOG.error("  · 해당 분기는 유니버스가 구성되지 않아 현금 보유로 처리됩니다. "
                      "marcap 파일 경로(MARCAP_EXTRA_DIRS) 또는 KRX 로그인/네트워크를 확인하세요.")

        rows = []
        for d, (src, g) in collected.items():
            g = g.copy()
            g["signal_date"] = d
            g["src"] = src
            g["grade"] = MCAP_GRADE[src]
            if "size_rank" not in g.columns:
                mc = pd.to_numeric(g["marcap"], errors="coerce")
                g["size_rank"] = mc.rank(ascending=False, method="first")
            rows.append(g.reindex(columns=MCAP_SPINE_COLS))
        panel = (pd.concat(rows, ignore_index=True) if rows
                 else pd.DataFrame(columns=MCAP_SPINE_COLS))
        if len(panel):
            panel["code"] = panel["code"].astype(str)
            panel["signal_date"] = as_ts_series(panel["signal_date"])
        self.panel = panel

        LOG.table([[k, f"{v}시점", MCAP_GRADE[k]] for k, v in self.n_by_src.items()]
                  + [["(실패)", f"{len(remaining)}시점", "—"]],
                  ["소스", "확보", "정확도 등급"], ["l", "r", "l"],
                  title=f"시총 스파인 소스별 확보 현황 (총 {len(dates)}개 신호일)")
        self._persist(collected)
        PIPE.io("OUT", "MEM", "mcap_spine", panel, source="+".join(self.n_by_src))
        return downcast(panel)

    # ── 영속 (공용 인덱스 · 합집합 증분) ────────────────────────────────────────────────────
    @staticmethod
    def _persist(collected: Dict[pd.Timestamp, Tuple[str, pd.DataFrame]]):
        """네트워크/근사로 새로 얻은 단면만 공용 캐시에 증분 적재 — 다음 실행은 네트워크 0회.
        ★ 기존 행을 지우지 않는다: 기존 테이블과 concat 후 (code,date) 중복만 제거."""
        fresh = {d: g for d, (s, g) in collected.items()
                 if s in ("krx_bld", "krx_api", "pykrx", "fdr_apx")}
        if not fresh or VAULT is None:
            return
        add = []
        for d, g in fresh.items():
            k = g.reindex(columns=["code", "marcap", "shares", "market", "close"]).copy()
            k["date"] = d
            add.append(k)
        new = pd.concat(add, ignore_index=True)
        prev = VAULT.get_table("krx_market_cap_monthly", scope="shared",
                               union_keys=["code", "date"])
        if prev is not None and len(prev):
            if "date" in prev.columns:
                prev["date"] = as_ts_series(prev["date"])
            allm = pd.concat([prev, new], ignore_index=True)
        else:
            allm = new
        allm["date"] = as_ts_series(allm["date"])
        allm["code"] = allm["code"].astype(str)
        allm = (allm.dropna(subset=["date", "code"])
                    .drop_duplicates(["code", "date"], keep="last").reset_index(drop=True))
        VAULT.put_table("krx_market_cap_monthly", allm, scope="shared", domain="price",
                        source="krx_bld/pykrx/fdr_apx 시총 단면(증분)")
        LOG.ok(f"신규 시총 단면 {len(new):,}행을 공용 인덱스에 적재 "
               f"(누적 {len(allm):,}행) — 다음 실행은 이 경로를 네트워크 0회로 씁니다.")


def _prev_business_guess(d: pd.Timestamp) -> str:
    """주말/공휴일 보정: 요청일이 토·일이면 직전 금요일로 당긴다(KRX 응답 빈 단면 방지).
    실제 거래일 판정은 상위에서 거래캘린더로 이미 끝났으므로 여기선 최소 보정만."""
    t = pd.Timestamp(d)
    while t.weekday() >= 5:
        t -= pd.Timedelta(days=1)
    return t.strftime("%Y%m%d")


SPINE = MarketcapSpine()


def spine_snapshots(panel: pd.DataFrame) -> Dict[pd.Timestamp, pd.DataFrame]:
    """신호일 → 시총 단면 dict (팩터 빌더가 기대하는 형태). 없는 시점은 빈 프레임."""
    out: Dict[pd.Timestamp, pd.DataFrame] = {}
    if panel is None or not len(panel):
        return out
    for d, g in panel.groupby("signal_date"):
        out[pd.Timestamp(d)] = (g.drop(columns=["signal_date"], errors="ignore")
                                 .reset_index(drop=True))
    return out


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  일봉 가격 · 거래캘린더 · 리밸런스 일정                                              ║
# ║                                                                                          ║
# ║  ★ v1.1 전면개편 — "쓸데없는 가격조회 반복" 제거                                          ║
# ║   v1.0 실측: 캐시에 이미 6,536,678행(3,290종목·2026-07까지)이 있는데도 3,801종목을          ║
# ║   신규 수집하겠다고 나서서 2,140종목이 전량 실패, 36분 소모. 원인 세 가지를 각각 끊는다.     ║
# ║                                                                                          ║
# ║   ① 호출 대상 자체가 틀렸다 — 유니버스를 모른 채 마스터 5,398종목(채권·워런트·스팩·         ║
# ║      우선주·외국주 포함) 전부를 받았다.  → v1.1 은 시총 스파인→유니버스 확정 후,            ║
# ║      **그 유니버스 종목만** 수집한다(K200 후보 + 하위1000 + 벤치마크 ≈ 1,500~3,000).        ║
# ║   ② 결손 판정이 상장일/폐지일을 무시했다 — 2020년 상장 종목에 2016년 데이터를 요구하니       ║
# ║      매 실행마다 백필 대상으로 올라가 영구히 실패했다. 폐지종목도 마찬가지(끝이 없다).       ║
# ║      → v1.1 은 [상장일, 폐지일] ∩ [백테스트구간] 안의 '기대 거래일 수' 대비 커버리지로만     ║
# ║        판정한다. 90% 이상이면 그 종목은 완결로 보고 건드리지 않는다.                        ║
# ║   ③ 음성 캐시가 체인 뒤에 있었고 30일 고정이었다 — 실패해도 다음 달 또 전 소스를 돌았다.     ║
# ║      → v1.1 은 체인 앞에서 차단하고, 실패 횟수별 7/30/120/365일 백오프 + 4회째 영구 제외.    ║
# ║      → 성공했던 소스를 종목별로 기억해 다음엔 그 소스부터 시도한다(체인 헛돌기 제거).        ║
# ║   ④ yfinance 404 폭풍이 36분의 대부분이었다 → 기본 OFF(ALLOW_YFINANCE) + 호출 상한.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]
ATTEMPT_COLS = ["code", "requested_from", "attempted_at", "n_fail", "best_src", "permanent"]


@contextmanager
def _quiet_stdout():
    """서드파티(FDR 등)가 직접 print 하는 실패 메시지를 삼킨다 — 수천 줄 로그 폭주 방지."""
    import contextlib as _c
    buf = io.StringIO()
    try:
        with _c.redirect_stdout(buf), _c.redirect_stderr(buf):
            yield buf
    finally:
        pass


# ── 개별 소스 ────────────────────────────────────────────────────────────────────────────────
def _px_pykrx(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    d = KRXG.call(pykrx_stock.get_market_ohlcv, start.replace("-", ""),
                  end.replace("-", ""), code)
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


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    qs = (f"?symbol={code}&requestType=1&startTime={as_ts(start):%Y%m%d}"
          f"&endTime={as_ts(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = http_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
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
    d = d.rename(columns={"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
                          "종가": "close", "거래량": "volume"})
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    for c in ("open", "high", "low", "close", "volume"):
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["amount"] = d["close"] * d["volume"]          # 네이버는 거래대금 미제공 → 근사
    d["code"], d["src"] = code, "naver"
    d = d.dropna(subset=["close"])
    return d.reindex(columns=PRICE_COLS) if len(d) else None


def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        limiter("krx").wait()
        with _quiet_stdout():                      # FDR 은 실패를 직접 print 한다 → 삼킨다
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
        d["amount"] = pd.to_numeric(col(d, "close"), errors="coerce") * \
            pd.to_numeric(col(d, "volume"), errors="coerce")     # 근사 — 감사표에 명시
    d["code"], d["src"] = code, "fdr"
    return d.reindex(columns=PRICE_COLS)


_YF_CALLS = {"n": 0}


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """최종 폴백. ★ 기본 OFF + 호출 상한 — v1.0 의 36분 중 대부분이 여기서 404 를 맞았다."""
    if yf is None or not ALLOW_YFINANCE:
        return None
    if _YF_CALLS["n"] >= YFINANCE_MAX_CALLS:
        return None
    for suf in (".KS", ".KQ"):
        _YF_CALLS["n"] += 1
        try:
            limiter("generic").wait()
            with _quiet_stdout():
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
        d = d.reset_index().rename(columns={"index": "date", "Date": "date"})
        if "date" not in d.columns:
            d = d.rename(columns={d.columns[0]: "date"})
        d["amount"] = pd.to_numeric(col(d, "close"), errors="coerce") * \
            pd.to_numeric(col(d, "volume"), errors="coerce")
        d["code"], d["src"] = code, "yfinance"
        return d.reindex(columns=PRICE_COLS)
    return None


PRICE_FN = {"pykrx": _px_pykrx, "naver": _px_naver, "fdr": _px_fdr, "yfinance": _px_yf}
PRICE_CHAIN_ORDER = ["pykrx", "naver", "fdr", "yfinance"]


# ── 구조적 제외 (네트워크를 찌르기 전에 확정 배제) ────────────────────────────────────────────
#  ★ 여기서 과하게 배제하면 '조용한 선택편향'이 된다 — 배제 규칙은 최소한으로만 둔다.
#    · 7xxxxx = 신주인수권증서/증권. 일봉 자체가 없다 → 배제. (v1.0 로그의 701016·702011·
#      713012·719011 이 이것이며, 어차피 끝자리가 0이 아니라 보통주 판정에서도 걸린다.)
#    · 4/5/6/8xxxxx 는 배제하지 않는다. KRX 는 코드를 순차 배정해 2023년 이후 신규 상장주가
#      45xxxx~47xxxx 대역에 있다(예: 450080, 462870). 이 대역을 막으면 최근 상장 코스닥
#      종목이 유니버스에서 통째로 빠져 선택편향이 된다.
#    · 900xxx·950xxx(외국주/DR)도 배제하지 않는다. 실제 거래되는 상장종목이고 하위1000
#      비교전략 유니버스에 정당하게 들어간다. 폐지분은 음성 캐시가 1회 실패로 걸러낸다.
_NONSTOCK_PREFIX = ("7",)


def price_structural_skip(code: str, name: str = "") -> Optional[str]:
    """이 종목코드가 '일봉이 존재할 수 없는' 구조인지 판정. 반환=제외이유 or None."""
    c = str(code or "")
    if len(c) != 6:
        return "코드길이"
    if c[0] in _NONSTOCK_PREFIX:
        return "신주인수권/워런트(7xxxxx)"
    if not is_common_stock(c, name):
        return "우선주/ETP/스팩"
    return None


# ── 음성 캐시(시도 원장) ─────────────────────────────────────────────────────────────────────
class AttemptLedger:
    """종목별 수집 시도 원장. 실패 횟수에 따라 재시도 유예를 늘리고, 성공 소스를 기억한다.
    ★ 성공 여부와 무관하게 '무조건' 저장한다 — 전부 실패한 실행에서 아무것도 남기지 않으면
      다음 실행이 똑같은 헛수고를 처음부터 반복한다(TCD v2 에서 13~15분을 여기서 태웠다)."""

    def __init__(self):
        self.df = pd.DataFrame(columns=ATTEMPT_COLS)
        self.today = as_ts(_dt.date.today().isoformat())
        self._map: Dict[str, dict] = {}
        self._dirty = False

    def load(self):
        d = VAULT.get_table("price_fetch_attempts", scope="shared", union_keys=["code"])
        if d is None or not len(d):
            return
        for c in ATTEMPT_COLS:
            if c not in d.columns:
                d[c] = np.nan
        d["attempted_at"] = as_ts_series(d["attempted_at"])
        d["requested_from"] = as_ts_series(d["requested_from"])
        d["n_fail"] = pd.to_numeric(d["n_fail"], errors="coerce").fillna(1).astype(int)
        d["permanent"] = d["permanent"].fillna(False).astype(bool)
        d["code"] = d["code"].astype(str)
        d = (d.sort_values("attempted_at", na_position="first")
              .drop_duplicates("code", keep="last").reset_index(drop=True))
        self.df = d
        self._map = {r["code"]: r for r in d.to_dict("records")}
        n_perm = int(d["permanent"].sum())
        LOG.info(f"수집 시도 원장 {len(d):,}종목 재사용 (영구제외 {n_perm:,} · "
                 f"백오프 대기 {sum(1 for c in self._map if self.blocked(c, None)):,})")

    def blocked(self, code: str, want_from: Optional[pd.Timestamp]) -> bool:
        r = self._map.get(str(code))
        if r is None:
            return False
        at0 = r.get("attempted_at")
        if bool(r.get("permanent")):
            # ★ 감사 높음(H1): 영구제외에 해제 조건이 없으면 '환경 장애 4회'가 '종목 구조적
            #   부재'로 굳어져 유니버스가 영구 축소된다(프록시 뒤·pykrx 없음·네이버 스로틀
            #   4연속이면 50종목이 통째로 영구 제외됐다). 1년 뒤에는 반드시 다시 시도한다.
            if at0 is None or pd.isna(at0):
                return True
            return (self.today - pd.Timestamp(at0)).days < PRICE_NEG_PERMANENT_TTL_D
        at = r.get("attempted_at")
        if at is None or pd.isna(at):
            return False
        # ★ n_fail=0 은 '최근에 성공했다'는 뜻이다. `or 1` 로 읽으면 0 이 falsy 라서 1회
        #   실패로 오인해 성공한 종목까지 7일간 차단된다(회귀시험에서 잡힌 실제 버그).
        nf = r.get("n_fail")
        nf = 1 if nf is None or (isinstance(nf, float) and pd.isna(nf)) else int(nf)
        if nf <= 0:
            return False
        wait = PRICE_NEG_BACKOFF_D[min(nf, len(PRICE_NEG_BACKOFF_D)) - 1]
        # 이번에 더 이른 구간을 원한다면 이전 실패는 근거가 되지 않는다.
        frm = r.get("requested_from")
        if want_from is not None and frm is not None and pd.notna(frm) and frm > want_from:
            return False
        return (self.today - pd.Timestamp(at)).days < wait

    def best_src(self, code: str) -> Optional[str]:
        r = self._map.get(str(code))
        s = (r or {}).get("best_src")
        return str(s) if s and str(s) in PRICE_FN else None

    def record(self, code: str, ok: bool, requested_from: Any, src: str = "",
               env_failure: bool = False):
        code = str(code)
        r = dict(self._map.get(code) or {"code": code, "n_fail": 0})
        r["attempted_at"] = self.today
        r["requested_from"] = as_ts(requested_from)
        if ok:
            r["n_fail"] = 0
            r["permanent"] = False
            if src:
                r["best_src"] = src
        elif env_failure:
            # ★ H1 후속: 이번 배치의 성공률이 바닥이면 '이 종목이 없는 것'이 아니라
            #   '내 환경이 죽은 것'이다. 실패 횟수를 올리지 않고 짧게만 쉬게 한다.
            r["n_fail"] = min(int(r.get("n_fail") or 0), 1)
            r["permanent"] = False
        else:
            r["n_fail"] = int(r.get("n_fail") or 0) + 1
            r["permanent"] = bool(r["n_fail"] >= PRICE_NEG_PERMANENT)
        self._map[code] = r
        self._dirty = True

    def save(self):
        if not self._dirty or VAULT is None:
            return
        d = pd.DataFrame(list(self._map.values()))
        for c in ATTEMPT_COLS:
            if c not in d.columns:
                d[c] = np.nan
        d["permanent"] = d["permanent"].fillna(False).astype(bool)
        d["n_fail"] = pd.to_numeric(d["n_fail"], errors="coerce").fillna(0).astype(int)
        d["attempted_at"] = as_ts_series(d["attempted_at"]).astype(str)
        d["requested_from"] = as_ts_series(d["requested_from"]).astype(str)
        VAULT.put_table("price_fetch_attempts", d[ATTEMPT_COLS], scope="shared",
                        domain="price", source="negative_cache(backoff+best_src)")
        LOG.info(f"수집 시도 원장 {len(d):,}종목 저장 — 다음 실행은 실패 종목을 "
                 f"{PRICE_NEG_BACKOFF_D[0]}~{PRICE_NEG_BACKOFF_D[-1]}일 건너뜁니다.")


LEDGER = AttemptLedger()


# ── 캐시 로드 (모든 루트 합집합, 1회만) ──────────────────────────────────────────────────────
def load_price_cache() -> pd.DataFrame:
    """공용 일봉 캐시를 모든 읽기 루트에서 합집합으로 1회 로드한다.
    ★ 이 프레임은 이후 캘린더·시총 프록시·커버리지 판정·백테스트에 재사용된다 —
      v1.0 처럼 단계마다 다시 읽지 않는다(6.5M행 재파싱이 순수 낭비였다)."""
    d = VAULT.get_table("krx_ohlcv_daily", scope="shared", union_keys=["code", "date"])
    if d is None or not len(d):
        LOG.warn("공용 일봉 캐시가 비어 있습니다 — 첫 실행이면 정상입니다(신규 수집으로 채웁니다).")
        return pd.DataFrame(columns=PRICE_COLS)
    d["date"] = as_ts_series(d["date"])
    d["code"] = d["code"].astype(str).map(to_code6)
    for c in ("open", "high", "low", "close", "volume", "amount"):
        d[c] = pd.to_numeric(col(d, c), errors="coerce")
    if "src" not in d.columns:
        d["src"] = "cache"
    d = d.dropna(subset=["code", "date", "close"])
    d = d.reindex(columns=PRICE_COLS)
    LOG.ok(f"공용 캐시 일봉 {len(d):,}행 재사용 · {d['code'].nunique():,}종목 · "
           f"{d['date'].min():%Y-%m-%d}~{d['date'].max():%Y-%m-%d} (네트워크 0회)")
    return downcast(d)


# ── 거래캘린더 부트스트랩 (가격 전수수집 없이) ────────────────────────────────────────────────
def trading_calendar(px: pd.DataFrame, dense: bool = True) -> np.ndarray:
    """시장 거래일 = '전 종목 합집합'의 거래일.

    dense=True  : 일별 종목수 중앙값의 20% 미만인 날을 제외(반쪽 데이터일 방어). 가격 패널이
                  구간 전체에 고르게 있을 때만 옳다.
    dense=False : 날짜 합집합 그대로. ★ 부트스트랩에는 반드시 이쪽을 쓴다 —
                  감사 치명(C2): 캐시는 최근 연도가 훨씬 촘촘하므로 밀도필터를 부트스트랩에
                  적용하면 앞 구간 날짜가 통째로 사라져 sch0 이 초기 분기를 잃는다. 그 분기는
                  시총 스파인·유니버스가 '시도조차' 안 되고, 가격 확보 후 캘린더가 복원되며
                  sch 에는 다시 나타나 조용한 현금분기가 된다(10년 중 25%가 평평해짐)."""
    if px is None or not len(px):
        return np.array([], dtype="datetime64[ns]")
    if not dense:
        return np.array(sorted(pd.unique(as_ts_series(px["date"]).dropna())),
                        dtype="datetime64[ns]")
    cnt = px.groupby("date")["code"].size().sort_index()
    med = float(cnt.median()) if len(cnt) else 0.0
    days = cnt[cnt >= max(1.0, med * 0.20)].index
    return np.array(sorted(days), dtype="datetime64[ns]")


def bootstrap_calendar(pxc: pd.DataFrame, start: str, end: str) -> np.ndarray:
    """★ v1.1 핵심 순서 변경: 리밸런스 일정을 '가격 전수수집 이후'가 아니라 '이전'에 만든다.
    유니버스를 정하려면 신호일이 필요하고, 신호일을 정하려면 거래캘린더가 필요한 순환을
    캘린더를 값싸게 확보하는 것으로 끊는다.
      ① 캐시 일봉의 날짜 합집합(6.5M행이 이미 있으면 이걸로 끝 — 네트워크 0회)
      ② marcap 연도 파일의 날짜 합집합
      ③ 벤치마크 지수 시계열 1회 조회(FDR KS200/KS11)
      ④ pykrx 영업일 조회
      ⑤ 최후: 평일 - 한국 공휴일 근사(고정 공휴일 + 대체휴일 미반영) → 경고와 함께"""
    s, e = as_ts(start), as_ts(end)
    lo = s - pd.DateOffset(months=PRICE_EXTRA_MARGIN_M + 3)
    parts: List[np.ndarray] = []
    if pxc is not None and len(pxc):
        c = trading_calendar(pxc, dense=False)     # ★ 부트스트랩은 밀도필터 없이 합집합
        if len(c) > 200:
            parts.append(c)
            LOG.ok(f"거래캘린더: 캐시 일봉에서 {len(c):,}거래일 확보(네트워크 0회 · 날짜 합집합)")
    if not parts:
        ys = MARCAP.years_available()
        got = []
        for y in ys:
            d = MARCAP.year(y)
            if d is not None and len(d):
                got.append(pd.DatetimeIndex(sorted(pd.unique(d["date"]))).to_numpy())
        MARCAP.trim()
        if got:
            c = np.unique(np.concatenate(got))
            parts.append(c)
            LOG.ok(f"거래캘린더: marcap 파일에서 {len(c):,}거래일 확보")
    if not parts and RUN_MODE != "CACHED":
        b = fetch_benchmark_k200(lo.strftime("%Y-%m-%d"), end)
        if b is not None and len(b) > 200:
            c = np.array(sorted(pd.unique(as_ts_series(b["date"]))), dtype="datetime64[ns]")
            parts.append(c)
            LOG.ok(f"거래캘린더: 벤치마크 지수 시계열에서 {len(c):,}거래일 확보(1회 조회)")
    if not parts and RUN_MODE != "CACHED" and KRX.session_ok:
        # KRX 전종목시세를 분기말 후보일에만 찔러 '그 날이 거래일인지'를 확인하는 건 가능하지만
        # 캘린더 전체를 만들 수는 없다 → 아래 ⑤ 근사 후 가격 확정 시점에 재정렬한다.
        pass
    if not parts:
        days = [d for d in pd.date_range(lo, e, freq="D") if d.weekday() < 5]
        parts.append(np.array(days, dtype="datetime64[ns]"))
        LOG.warn("거래캘린더를 어느 소스에서도 얻지 못해 '평일 전체'로 근사합니다. "
                 "공휴일이 거래일로 잡혀 분기말 신호일이 하루 밀릴 수 있습니다 — "
                 "가격 수집 후 실제 거래일로 자동 재정렬합니다.")
    cal = np.unique(np.concatenate(parts))
    cal = cal[(cal >= np.datetime64(lo)) & (cal <= np.datetime64(e))]
    return cal


def rebalance_schedule(cal: np.ndarray, start: str, end: str, quiet: bool = False
                       ) -> pd.DataFrame:
    """분기(3/6/9/12월) 마지막 거래일 = 신호일(종가 후) → 익거래일 = 체결일.
    각 신호의 보유구간은 [exec, 다음 exec) 이다. 마지막 신호는 구간 끝까지 보유."""
    cal_idx = pd.DatetimeIndex(cal)
    s, e = as_ts(start), as_ts(end)
    rows = []
    for y in range(s.year, e.year + 1):
        for m in REBAL_MONTHS:
            month_end = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
            if month_end < s or month_end > e:
                continue
            in_month = cal_idx[(cal_idx.year == y) & (cal_idx.month == m)]
            if not len(in_month):
                continue
            sig = in_month.max()
            nxt = cal_idx[cal_idx > sig]
            if not len(nxt):
                continue                      # 신호일 다음 거래일이 없으면 체결 불가 → 제외
            rows.append({"signal_date": sig, "exec_date": nxt.min(),
                         # ★ 감사 낮음(L1): m//3 은 REBAL_MONTHS 를 바꾸면 'Q0' 이나 중복 키를
                         #   만든다(예: (1,4,7,10)→Q0..Q3, (2,3,5,6)→중복 10건 → remap 누락).
                         "yq": f"{y}Q{(m - 1) // 3 + 1}-M{m:02d}"})
    if not rows:
        return pd.DataFrame(columns=["signal_date", "exec_date", "next_exec", "yq"])
    sch = pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)
    if bool(sch["yq"].duplicated().any()):
        LOG.error(f"리밸런스 분기 키(yq)가 중복됩니다 — REBAL_MONTHS={REBAL_MONTHS} 설정을 "
                  f"확인하세요. 중복 키는 유니버스 리맵을 조용히 누락시킵니다.")
    sch["next_exec"] = sch["exec_date"].shift(-1)
    sch.loc[sch.index[-1], "next_exec"] = pd.Timestamp(cal_idx.max())
    if not quiet:
        LOG.ok(f"리밸런스 일정 {len(sch)}개 분기 "
               f"({sch['signal_date'].min():%Y-%m-%d} ~ {sch['signal_date'].max():%Y-%m-%d}) · "
               f"신호=분기말 종가 후 → 체결=익거래일 시가")
        PIPE.io("OUT", "MEM", "rebalance_schedule", sch)
    return sch


def realign_schedule(sch0: pd.DataFrame, cal1: np.ndarray, start: str, end: str
                     ) -> Tuple[pd.DataFrame, Dict[pd.Timestamp, pd.Timestamp]]:
    """가격 확정 후의 실제 거래캘린더로 일정을 재정렬하고, 구 신호일 → 신 신호일 매핑을 준다.
    분기 키(YYYYQn)로 대응시키므로 하루 밀림/공휴일 오차가 유니버스·수급 키를 깨뜨리지 않는다."""
    sch1 = rebalance_schedule(cal1, start, end, quiet=True)
    if not len(sch1) or not len(sch0):
        return (sch1 if len(sch1) else sch0), {}
    m0 = dict(zip(sch0["yq"], sch0["signal_date"]))
    remap: Dict[pd.Timestamp, pd.Timestamp] = {}
    for yq, sd in zip(sch1["yq"], sch1["signal_date"]):
        old = m0.get(yq)
        if old is not None and pd.Timestamp(old) != pd.Timestamp(sd):
            remap[pd.Timestamp(old)] = pd.Timestamp(sd)
    dropped = [yq for yq in m0 if yq not in set(sch1["yq"])]
    if remap or dropped:
        LOG.warn(f"실제 거래캘린더 확정 후 신호일 {len(remap)}개 재정렬"
                 + (f" · 분기 {len(dropped)}개 소멸({dropped[:4]})" if dropped else "")
                 + " — 유니버스/수급 키를 함께 이동시킵니다.")
    else:
        LOG.ok("부트스트랩 캘린더와 실제 거래캘린더의 신호일이 완전히 일치 — 재정렬 불필요.")
    PIPE.io("OUT", "MEM", "rebalance_schedule", sch1)
    return sch1, remap


def remap_signal_dates(df: pd.DataFrame, remap: Dict[pd.Timestamp, pd.Timestamp],
                       colname: str = "signal_date") -> pd.DataFrame:
    if df is None or not len(df) or not remap or colname not in df.columns:
        return df
    d = df.copy()
    d[colname] = as_ts_series(d[colname]).map(lambda t: remap.get(pd.Timestamp(t),
                                                                 pd.Timestamp(t)))
    return d


# ── marcap 벌크 경로 ─────────────────────────────────────────────────────────────────────────
def _marcap_split_adjust(px: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """marcap 실종가의 액면분할/병합 절벽 보정.
    ★ marcap 은 무수정 실종가라 삼성전자 50:1(2018-05) 같은 분할이 하루 -98% 수익으로
      들어간다(감사 CRITICAL). '주식수 점프 × 시총 연속' 시그니처가 동시에 맞을 때만
      소급계수를 적용한다 — 유상증자(주식수↑·시총도↑)는 보정하지 않는다."""
    if "shares" not in px.columns or px["shares"].notna().sum() == 0:
        return px, 0
    px = px.sort_values(["code", "date"], kind="mergesort").reset_index(drop=True)
    g = px.groupby("code", observed=True)
    r_p = px["close"] / g["close"].shift(1)
    r_s = px["shares"] / g["shares"].shift(1)
    ev = (r_s.notna() & r_p.notna() & ((r_s > 1.2) | (r_s < 1 / 1.2)) &
          ((r_p * r_s - 1).abs() < 0.25))
    n_ev = int(ev.sum())
    if not n_ev:
        return px, 0
    factor = pd.Series(1.0, index=px.index)
    factor[ev] = r_s[ev].astype(float)
    rev_code = px["code"].iloc[::-1]
    suffix = factor.iloc[::-1].groupby(rev_code, observed=True).cumprod().iloc[::-1]
    fut = (suffix / factor).astype(float)      # 행 t 이후(exclusive) 이벤트 계수의 곱
    for c in ("open", "high", "low", "close"):
        if c in px.columns:
            px[c] = pd.to_numeric(px[c], errors="coerce") / fut
    if "volume" in px.columns:
        px["volume"] = pd.to_numeric(px["volume"], errors="coerce") * fut
    return px, n_ev


def prices_from_marcap(codes: set, start: str, end: str) -> Optional[pd.DataFrame]:
    """marcap 연도 parquet(폐지종목 포함 일별 시세)에서 일봉을 벌크로 뽑는다 — 신규 수집 0건.
    ★ v1.1: 연도가 일부만 있어도 '있는 만큼' 쓴다. v1.0 은 한 해라도 빠지면 전체를 포기해
      (부분 사용은 편향이라는 이유로) 캐시가 있는데도 폴백 체인을 돌렸다. 이제는 결손 판정을
      상장기간 기준 커버리지로 하류에서 다시 하므로, 부분 사용이 편향을 만들지 않는다."""
    y0, y1 = as_ts(start).year, as_ts(end).year
    avail = set(MARCAP.years_available())
    if not avail:
        return None
    need = list(range(y0, y1 + 1))
    have = [y for y in need if y in avail]
    if not have:
        return None
    miss = [y for y in need if y not in avail]
    if miss:
        LOG.warn(f"marcap 연도 결손 {miss} — 있는 연도({min(have)}~{max(have)})만 씁니다. "
                 f"빠진 구간은 커버리지 판정 후 폴백 체인이 채웁니다.")
    frames = []
    for y in have:
        d = MARCAP.year(y)
        if d is None or not len(d):
            continue
        sub = d[d["code"].isin(codes)] if codes else d
        if not len(sub):
            continue
        frames.append(pd.DataFrame({
            "code": sub["code"].astype(str), "date": sub["date"],
            "open": col(sub, "open"), "high": col(sub, "high"), "low": col(sub, "low"),
            "close": col(sub, "close"), "volume": col(sub, "volume"),
            "amount": col(sub, "amount"), "shares": col(sub, "shares"), "src": "marcap"}))
        MARCAP.trim()
    if not frames:
        return None
    px = pd.concat(frames, ignore_index=True).dropna(subset=["code", "date", "close"])
    px, n_ev = _marcap_split_adjust(px)
    if n_ev:
        LOG.ok(f"marcap 분할/병합 절벽 {n_ev:,}건 소급 보정 (주식수 점프 × 시총 연속 시그니처)")
    return px.drop(columns=["shares"], errors="ignore") if len(px) else None


# ── 결손 계획 (상장기간 기준 커버리지) ───────────────────────────────────────────────────────
def price_gap_plan(codes: Sequence[str], start: str, end: str, sec: pd.DataFrame,
                   pxc: pd.DataFrame, cal: np.ndarray
                   ) -> Tuple[List[Tuple[str, str, str]], Dict[str, int]]:
    """수집이 실제로 필요한 (code, from, to) 목록과 사유별 집계를 만든다.

    ★ 판정 규칙(v1.0 병목의 정면 수정)
      기대 구간 = [상장일-5일, 폐지일+10일] ∩ [백테스트 시작-여유, 끝]
      기대 거래일 수 대비 보유 행 수가 PRICE_COVERAGE_MIN 이상이면 '완결'로 보고 손대지 않는다.
      2020년 상장 종목에 2016년 데이터를 요구하지 않고, 2018년 폐지 종목에 2026년을 요구하지
      않는다 — v1.0 은 이 둘 때문에 매 실행 2,140종목을 영구히 헛돌았다."""
    start_ts, end_ts = as_ts(start), as_ts(end)
    cal_ns = np.array(sorted(cal), dtype="datetime64[ns]")
    codes = sorted({c for c in map(to_code6, codes) if c})
    stats: Dict[str, int] = Counter()

    names = {}
    lst: Dict[str, pd.Timestamp] = {}
    dl: Dict[str, pd.Timestamp] = {}
    if sec is not None and len(sec):
        names = dict(zip(sec["code"].astype(str), sec["name"].astype(str)))
        ls = as_ts_series(col(sec, "listing_date"))
        ds = as_ts_series(col(sec, "delisting_date"))
        lst = {c: t for c, t in zip(sec["code"].astype(str), ls) if pd.notna(t)}
        dl = {c: t for c, t in zip(sec["code"].astype(str), ds) if pd.notna(t)}

    # ── 종목별 기대구간 [w0, w1] 을 먼저 확정한다 ────────────────────────────────────────────
    keep_codes, w0s, w1s = [], [], []
    for c in codes:
        why = price_structural_skip(c, names.get(c, ""))
        if why:
            stats["구조적제외:" + why] += 1
            continue
        w0 = start_ts
        if c in lst:
            w0 = max(w0, lst[c] - pd.Timedelta(days=5))
        w1 = end_ts
        if c in dl:
            w1 = min(w1, dl[c] + pd.Timedelta(days=10))
        if w1 <= w0:
            stats["구간외(상장전/폐지후)"] += 1
            continue
        keep_codes.append(c)
        w0s.append(w0)
        w1s.append(w1)
    if not keep_codes:
        return [], dict(stats)
    B = pd.DataFrame({"code": keep_codes, "w0": w0s, "w1": w1s})

    # ★ 보유 건수는 반드시 '기대구간 안에서만' 센다. 구간 밖 행(잘못된 상장일, 재상장 등)이
    #   섞이면 커버리지가 부풀어 실제로 7년이 빈 종목을 '충분'으로 오판할 수 있다.
    #   (code,date) 중복도 먼저 제거 — 캐시와 marcap 이 같은 날을 함께 갖고 있으면 이중계상.
    cnt: Dict[str, int] = {}
    mn: Dict[str, pd.Timestamp] = {}
    mx: Dict[str, pd.Timestamp] = {}
    if pxc is not None and len(pxc):
        sub = (pxc.loc[(pxc["date"] >= start_ts) & (pxc["date"] <= end_ts), ["code", "date"]]
               .drop_duplicates(["code", "date"]))
        sub = sub.merge(B, on="code", how="inner")
        sub = sub[(sub["date"] >= sub["w0"]) & (sub["date"] <= sub["w1"])]
        if len(sub):
            g = sub.groupby("code", observed=True)["date"]
            cnt = g.size().to_dict()
            mn = g.min().to_dict()
            mx = g.max().to_dict()

    i0a = np.searchsorted(cal_ns, B["w0"].to_numpy(dtype="datetime64[ns]"), side="left")
    i1a = np.searchsorted(cal_ns, B["w1"].to_numpy(dtype="datetime64[ns]"), side="right")
    expa = np.maximum(i1a - i0a, 0)

    todo: List[Tuple[str, str, str]] = []
    for k, c in enumerate(B["code"]):
        w0, w1 = pd.Timestamp(B["w0"].iloc[k]), pd.Timestamp(B["w1"].iloc[k])
        i0, i1, exp = int(i0a[k]), int(i1a[k]), int(expa[k])
        if exp < 20:
            stats["기대거래일<20"] += 1
            continue
        have = int(cnt.get(c, 0))
        if have == 0:
            if LEDGER.blocked(c, w0):
                stats["음성캐시(백오프/영구)"] += 1
                continue
            todo.append((c, w0.strftime("%Y-%m-%d"), w1.strftime("%Y-%m-%d")))
            stats["신규(보유0)"] += 1
            continue
        c_mn, c_mx = pd.Timestamp(mn[c]), pd.Timestamp(mx[c])
        lead = int(np.searchsorted(cal_ns, np.datetime64(c_mn), side="left") - i0)
        tail = int(i1 - np.searchsorted(cal_ns, np.datetime64(c_mx), side="right"))
        lead_tol, tail_tol = max(5, exp * 0.03), max(3, exp * 0.02)
        # ★ 감사 높음(H2): v1.1 초안은 커버리지 게이트를 먼저 통과시켜, 뒤 구간 3~14개월이
        #   비어 있어도(커버리지 0.90~0.98) '캐시충분'으로 확정해 백필/증분 분기에 도달조차
        #   못했다. 게이트와 결손 검출을 AND 로 묶어 둘 다 만족할 때만 '충분'으로 본다.
        if (have / exp >= PRICE_COVERAGE_MIN and lead <= lead_tol and tail <= tail_tol):
            stats["캐시충분"] += 1
            continue
        if LEDGER.blocked(c, w0):
            stats["음성캐시(백오프/영구)"] += 1
            continue
        added = False
        if lead > lead_tol:
            todo.append((c, w0.strftime("%Y-%m-%d"),
                         (c_mn + pd.Timedelta(days=3)).strftime("%Y-%m-%d")))
            stats["백필(앞구간)"] += 1
            added = True
        if tail > tail_tol:
            todo.append((c, (c_mx - pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                         w1.strftime("%Y-%m-%d")))
            stats["증분(뒤구간)"] += 1
            added = True
        if not added:
            todo.append((c, w0.strftime("%Y-%m-%d"), w1.strftime("%Y-%m-%d")))
            stats["내부공백(전구간 재수집)"] += 1
    return todo, dict(stats)


# ── 절벽 분류·보정 ───────────────────────────────────────────────────────────────────────────
# 액면분할·병합·무상증자의 실제 비율은 사실상 단순 정수비다. |일수익|>50% 절벽이므로
# 비율이 0.5 이하 또는 2 이상인 값만 의미가 있다.
_CA_RATIOS = tuple(sorted(
    [1.0 / x for x in (2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0,
                       40.0, 50.0, 100.0)]
    + [2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 100.0]))


def _near_ca_ratio(r: float, tol: float = 0.02) -> Optional[float]:
    """측정된 가격비가 '기업행위로 설명되는 단순비'에 2% 이내로 맞는지. 맞으면 공칭비 반환."""
    if not np.isfinite(r) or r <= 0:
        return None
    for t in _CA_RATIOS:
        if abs(r / t - 1.0) < tol:
            return float(t)
    return None


def repair_price_cliffs(px: pd.DataFrame, delist: Dict[str, Any]
                        ) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """하루 |수익|>50% 절벽을 분류하고, '기업행위(분할/병합)'로 판정된 것만 소급 보정한다.

    분류 기준
      · 정리매매(정상)  : 폐지일 직전 20거래일 구간 — 가격제한폭이 없어 실제로 반토막이 난다.
      · 기업행위(보정)  : 절벽 전후 20일 중앙값의 비가 절벽 당일 비율과 20% 이내로 일치
                         (= 수준 이동이 지속) → 분할/병합. 이전 가격에 소급계수를 적용.
      · 미분류(경고)    : 위 둘 다 아님 — 산출물 커버리지에 종목·날짜를 남긴다.
    v1.0 은 522건을 '잔존'으로 경고만 했다. 보정하지 않으면 그 종목의 분기수익이 -98% 로
    들어가 백테스트 전체를 오염시킨다."""
    out = {"정리매매": 0, "기업행위보정": 0, "미분류": 0}
    if px is None or len(px) < 10:
        return px, out
    px = px.sort_values(["code", "date"], kind="mergesort").reset_index(drop=True)
    r = px.groupby("code", observed=True)["close"].pct_change()
    hit = r.abs() > 0.5
    if not bool(hit.any()):
        return px, out
    bad_codes = pd.unique(px.loc[hit, "code"])
    factor = pd.Series(1.0, index=px.index)
    unclassified: List[Tuple[str, str, float]] = []
    # ★ 감사 중간(M1): 종목마다 `px["code"] == c` 로 전체 프레임을 훑으면 종목수 × 행수의
    #   이차 비용이 된다(실측: 650만행 × 절벽 200종목 = 26초, 1,000종목이면 2분 이상).
    #   groupby.indices 로 위치 인덱스를 한 번만 만들어 O(N) 으로 끝낸다.
    _idx_map = px.groupby("code", sort=False).indices
    _close_all = pd.to_numeric(px["close"], errors="coerce").to_numpy(dtype=float)
    _date_all = px["date"].to_numpy()
    _hit_all = hit.to_numpy()
    for c in bad_codes:
        pos_arr = _idx_map.get(c)
        if pos_arr is None or len(pos_arr) == 0:
            continue
        idx = px.index[pos_arr]
        cl_arr = _close_all[pos_arr]
        dt_arr = _date_all[pos_arr]
        mask = _hit_all[pos_arr]
        dl_t = as_ts(delist.get(c)) if delist else None
        cliff_pos = np.flatnonzero(mask)
        for j, pos in enumerate(cliff_pos):
            if pos == 0 or not np.isfinite(cl_arr[pos - 1]) or cl_arr[pos - 1] <= 0:
                continue
            ratio = float(cl_arr[pos] / cl_arr[pos - 1])       # 절벽 당일 가격비
            if not np.isfinite(ratio) or ratio <= 0:
                continue
            d = pd.Timestamp(dt_arr[pos])
            if dl_t is not None and pd.notna(dl_t) and -5 <= (dl_t - d).days <= 40:
                out["정리매매"] += 1                            # 가격제한폭 없음 — 실제 급락
                continue
            # ★ 감사 치명(C3) ①: 행간 pct_change 라서 '데이터 공백'도 절벽으로 잡힌다.
            #   18개월 공백 후 -75%(거래정지 재개 / marcap 연도결손)를 기업행위로 오분류하면
            #   실제 손실이 0% 로 지워진다. 거래일이 실제로 인접할 때만 기업행위 후보로 본다.
            gap_days = int((d - pd.Timestamp(dt_arr[pos - 1])).days)
            if gap_days > 5:
                out["미분류(데이터공백)"] = out.get("미분류(데이터공백)", 0) + 1
                out["미분류"] += 1
                unclassified.append((str(c), f"{d:%Y-%m-%d}", ratio - 1.0))
                continue
            # ★ 감사 치명(C3) ②: '수준 이동 지속' 만으로는 정리매매(폐지일 미기록)와 기업행위를
            #   구분할 수 없다 — 1000→300 후 안정도 통과해 실제 -70% 가 0% 로 지워졌다.
            #   액면분할/병합·무상증자는 사실상 항상 단순 정수비다(50:1, 10:1, 1:5 …).
            #   단순비 일치를 '필요조건'으로 두고, 계수는 측정비가 아닌 공칭비를 쓴다
            #   (그러면 그 날의 진짜 등락은 보존된다).
            nominal = _near_ca_ratio(ratio)
            if nominal is None:
                out["미분류"] += 1
                unclassified.append((str(c), f"{d:%Y-%m-%d}", ratio - 1.0))
                continue
            # 수준비교 창은 '이웃 절벽에서 끊는다'(20일 고정창이면 근접 절벽끼리 서로의
            # 중앙값을 오염시켜 둘 다 미분류로 흘러간다 — 엣지 시험에서 실측).
            # 표본이 짧으면(종목 데이터 처음/끝 1~2행) 단순비 일치만으로 인정한다(M3).
            lo = int(cliff_pos[j - 1]) if j > 0 else 0
            hi = int(cliff_pos[j + 1]) if j + 1 < len(cliff_pos) else len(cl_arr)
            pre = cl_arr[max(lo, pos - 20):pos]
            post = cl_arr[pos:min(hi, pos + 20)]
            pre = pre[np.isfinite(pre)]
            post = post[np.isfinite(post)]
            ok_level = True
            if len(pre) >= 3 and len(post) >= 3:
                lvl = float(np.median(post)) / max(float(np.median(pre)), 1e-9)
                ok_level = abs(lvl / nominal - 1.0) < 0.25
            if ok_level:
                factor.loc[idx[pos]] = 1.0 / float(nominal)
                out["기업행위보정"] += 1
                continue
            out["미분류"] += 1
            unclassified.append((str(c), f"{d:%Y-%m-%d}", ratio - 1.0))
    if out["기업행위보정"]:
        rev_code = px["code"].iloc[::-1]
        suffix = factor.iloc[::-1].groupby(rev_code, observed=True).cumprod().iloc[::-1]
        fut = (suffix / factor).astype(float)
        for c in ("open", "high", "low", "close"):
            if c in px.columns:
                px[c] = pd.to_numeric(px[c], errors="coerce") / fut
        if "volume" in px.columns:
            px["volume"] = pd.to_numeric(px["volume"], errors="coerce") * fut
        LOG.ok(f"가격 절벽 분류: 기업행위 {out['기업행위보정']}건 소급보정 · "
               f"정리매매 {out['정리매매']}건 유지 · 미분류 {out['미분류']}건")
    else:
        LOG.info(f"가격 절벽 분류: 정리매매 {out['정리매매']}건 · 미분류 {out['미분류']}건 "
                 f"(보정 대상 없음)")
    if unclassified:
        LOG.warn("미분류 절벽 상위: "
                 + ", ".join(f"{c}@{d}({v:+.0%})" for c, d, v in unclassified[:6]))
    globals()["_PX_CLIFF_DETAIL"] = out
    globals()["_PX_CLIFF_UNCLASSIFIED"] = unclassified
    return px, out


# ── 상위 진입점 ──────────────────────────────────────────────────────────────────────────────
def fetch_prices(codes: Sequence[str], start: str, end: str, sec: pd.DataFrame,
                 pxc: pd.DataFrame, cal: np.ndarray,
                 delist: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """유니버스로 한정된 일봉 확보: ①캐시(이미 로드됨) ②marcap 벌크 ③폴백체인(결손분만).
    신규분은 공용 인덱스에 '날짜 절단 전' 전체본으로 재적재한다."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    LOG.info(f"가격 확보 대상 {len(codes):,}종목 (유니버스 확정 후 — v1.0 은 마스터 전체 "
             f"5,398종목을 받았습니다)")
    LEDGER.load()
    new_frames: List[pd.DataFrame] = []
    have = pxc if pxc is not None else pd.DataFrame(columns=PRICE_COLS)

    # ① marcap 벌크 (폐지종목까지 네트워크 0회로 커버)
    #    ★ RUN_MODE=='CACHED' 에서도 반드시 수행한다. CACHED 의 약속은 'network=0' 이지
    #      'disk=0' 이 아니다. v1.1 초안은 이 블록을 네트워크 체인과 함께 묶어 막아버려,
    #      정작 계약의 timed run(CACHED)에서 marcap 을 읽지 못하고 "가격 0종목"으로
    #      죽었다(통합시험에서 잡힘).
    todo, stats = price_gap_plan(codes, start, end, sec, have, cal)
    if todo:
        mset = {c for c, _, _ in todo}
        mk = prices_from_marcap(mset, start, end)
        if mk is not None and len(mk):
            LOG.ok(f"marcap 스파인에서 일봉 {len(mk):,}행 벌크 확보 "
                   f"({mk['code'].nunique():,}종목) — 네트워크 수집 대상에서 제외합니다.")
            new_frames.append(mk)
            # ★ 커버리지 판정 전에 (code,date) 중복을 반드시 제거한다. 캐시와 marcap 이 같은
            #   날을 함께 가지고 있으면 보유 행수가 부풀어 결손을 '충분'으로 오판한다.
            have = (pd.concat([have.reindex(columns=PRICE_COLS),
                               mk.reindex(columns=PRICE_COLS)], ignore_index=True)
                    .drop_duplicates(["code", "date"], keep="first"))
            todo, stats = price_gap_plan(codes, start, end, sec, have, cal)

    LOG.table([[k, f"{v:,}"] for k, v in sorted(stats.items(), key=lambda kv: -kv[1])]
              + [["→ 실제 수집 작업", f"{len(todo):,}"]],
              ["결손 판정 사유", "종목수"], ["l", "r"],
              title="가격 수집 계획 (상장기간 기준 커버리지 판정)")

    # ② 폴백 체인 — 결손분만, 종목별 '성공했던 소스'부터
    if todo and RUN_MODE != "CACHED":
        if pykrx_stock is not None:
            KRXG.warmup()
        chain_note = " → ".join(
            [s for s in PRICE_CHAIN_ORDER if s != "yfinance" or ALLOW_YFINANCE])
        LOG.info(f"일봉 결손 수집 {len(todo):,}건 (체인: {chain_note}"
                 + ("" if ALLOW_YFINANCE else " · yfinance 는 ALLOW_YFINANCE=False 로 비활성")
                 + ")")

        def _one(job):
            c, st, en = job
            order = list(PRICE_CHAIN_ORDER)
            pref = LEDGER.best_src(c)
            if pref:
                order = [pref] + [s for s in order if s != pref]
            for nm in order:
                if nm == "yfinance" and not ALLOW_YFINANCE:
                    continue
                try:
                    d = PRICE_FN[nm](c, st, en)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        return d, nm
            return None, ""

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 10), desc="일봉 결손 수집")
        n_ok = 0
        # 한 종목에 앞구간/뒤구간 두 작업이 걸릴 수 있다 → 원장 기록은 종목별로 1회만,
        # '하나라도 성공'을 성공으로 본다(둘 다 실패한 종목만 백오프 대상).
        per_code: Dict[str, Tuple[bool, str, str]] = {}
        for (c, st, en), r in zip(todo, res):
            d, nm = (r if isinstance(r, tuple) else (None, ""))
            ok = d is not None and len(d) > 0
            if ok:
                new_frames.append(d)
                n_ok += 1
            prev = per_code.get(c)
            if prev is None or (ok and not prev[0]):
                per_code[c] = (ok, st if prev is None else min(prev[1], st), nm or "")
            elif not ok and prev[0] is False:
                per_code[c] = (False, min(prev[1], st), "")
        fail_codes = [c for c, (ok, _, _) in per_code.items() if not ok]
        _env_fail = (len(per_code) >= 20
                     and (len(per_code) - len(fail_codes)) / max(len(per_code), 1) < 0.20)
        if _env_fail:
            LOG.warn(f"수집 성공률 {100 * (len(per_code) - len(fail_codes)) / len(per_code):.0f}%"
                     f" — 종목별 문제가 아니라 환경/네트워크 장애로 판단합니다. "
                     f"실패 횟수를 누적하지 않아 영구제외로 굳지 않습니다.")
        for c, (ok, st, nm) in per_code.items():
            LEDGER.record(c, ok, st, nm, env_failure=(_env_fail and not ok))
        LEDGER.save()
        LOG.ok(f"일봉 결손 수집 결과 — 성공 {n_ok:,}건 · 실패 {len(fail_codes):,}건"
               + (f" (실패는 원장에 기록되어 {PRICE_NEG_BACKOFF_D[0]}일 이상 재시도하지 "
                  f"않습니다)" if fail_codes else ""))
        if fail_codes:
            LOG.info(f"  실패 예시: {', '.join(fail_codes[:10])}"
                     + (f" 외 {len(fail_codes) - 10:,}종목" if len(fail_codes) > 10 else ""))
    elif todo:
        LOG.warn(f"CACHED 모드 — 결손 {len(todo):,}건을 건너뜁니다(network=0 약속 준수).")

    # ③ 병합 · 중복해소 · 절벽보정 · 저장
    frames = ([pxc] if pxc is not None and len(pxc) else []) + new_frames
    if not frames:
        raise RuntimeError(
            "가격 데이터를 한 종목도 확보하지 못했습니다.\n"
            "  ① 캐시(krx_ohlcv_daily / marcap_YYYY) 경로 — 위 '시총 스파인 발견 결과' 표 확인\n"
            "  ② fchart.stock.naver.com 네트워크 접근 여부\n"
            "  ③ FinanceDataReader/pykrx 설치 여부\n"
            "  RUN_MODE='SMOKE' 로 계산경로만 먼저 검증할 수 있습니다.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].astype(str).map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    for c in ("open", "high", "low", "close", "volume", "amount"):
        px[c] = pd.to_numeric(col(px, c), errors="coerce")
    if "src" not in px.columns:
        px["src"] = "cache"
    # (code,date) 중복은 '소스 우선순위'로 결정적으로 해소 — 비안정 정렬에 맡기면 실행마다
    # 다른 소스가 살아남아 재현성이 깨진다.
    _prio = {"pykrx": 0, "fdr": 1, "naver": 2, "yfinance": 3, "cache": 4, "marcap": 5}
    px["_prio"] = px["src"].astype(str).map(_prio).fillna(6).astype(int)
    px = (px.sort_values(["code", "date", "_prio"], kind="mergesort")
            .drop_duplicates(["code", "date"], keep="first")
            .drop(columns=["_prio"]).reset_index(drop=True))
    # ★ 감사 높음(H6) + 치명(C3) 후속 — 공용 테이블에는 '원본 신규행만' 더한다.
    #   v1.1 초안은 절벽 보정까지 끝낸 프레임을 PRICE_COLS 로 reindex 해서 raw 테이블 이름으로
    #   되썼다. 그 결과 ① 다른 전략이 넣어둔 컬럼(adj_close, market …)이 사라지고
    #   ② close 결측(정지일) 행이 삭제되고 ③ 우리의 보정값이 원본 자리에 영구 기록됐다.
    #   → 기존 테이블을 그대로 읽어 신규행만 합집합으로 얹고(기존 행이 승자), 보정 결과는
    #     이 전략 메모리와 전용 인덱스의 조정원장에만 남긴다.
    if new_frames:
        try:
            _prev = VAULT.get_table("krx_ohlcv_daily", scope="shared")
            _add = pd.concat(new_frames, ignore_index=True)
            _add["date"] = as_ts_series(_add["date"])
            _add["code"] = _add["code"].astype(str).map(to_code6)
            _add = _add.dropna(subset=["code", "date"])
            if _prev is not None and len(_prev):
                _prev["date"] = as_ts_series(_prev["date"])
                _prev["code"] = _prev["code"].astype(str)
                _merged = pd.concat([_prev, _add], ignore_index=True)
            else:
                _merged = _add
            _n0 = 0 if _prev is None else len(_prev)
            _merged = (_merged.drop_duplicates(["code", "date"], keep="first")
                              .reset_index(drop=True))
            VAULT.put_table("krx_ohlcv_daily", _merged, scope="shared", domain="price",
                            source="기존 테이블 + 신규 수집분(원본 · 보정 전)")
            LOG.ok(f"공용 일봉 테이블 갱신: 기존 {_n0:,}행 + 신규 {len(_add):,}행 → "
                   f"{len(_merged):,}행 (기존 컬럼·행 보존, 보정값은 기록하지 않음)")
        except Exception as e:                                          # noqa
            LOG.warn(f"공용 일봉 테이블 갱신 실패({type(e).__name__}) — 캐시는 그대로입니다.")
    px, cliff = repair_price_cliffs(px, delist or {})
    globals()["_PX_CLIFF_COUNT"] = int(cliff.get("미분류", 0))
    try:
        _uc = globals().get("_PX_CLIFF_UNCLASSIFIED") or []
        VAULT.put_table("price_cliff_adjustments",
                        pd.DataFrame([{"item": k, "n": v} for k, v in cliff.items()]
                                     + [{"item": f"미분류:{c}@{d}", "n": round(v, 4)}
                                        for c, d, v in _uc[:200]]),
                        scope="private", domain="audit",
                        source="repair_price_cliffs (전용 인덱스 · 원본 미변경)")
    except Exception:
        pass
    start_ts, end_ts = as_ts(start), as_ts(end)
    px = px[(px["date"] >= start_ts) & (px["date"] <= end_ts)]
    PIPE.io("OUT", "MEM", "prices_daily", px, source="krx_ohlcv_daily")
    return downcast(px.reindex(columns=PRICE_COLS))


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  유니버스 (재구성 KOSPI200 · 비교용 시총하위1000) + 기관/외국인 수급 (F6/F7)          ║
# ║                                                                                          ║
# ║  ★ v1.1 전면개편                                                                          ║
# ║   ① 유니버스는 이제 '시총 스파인 패널'만 입력으로 받는다. v1.0 은 시점마다 marketcap_at()   ║
# ║      을 다시 불러 연도 파일을 반복 로드/축출했고, 그 경로가 죽으면 전체가 죽었다.           ║
# ║   ② 절대 예외를 던지지 않는다. 만들지 못한 분기는 '현금 분기'로 표시하고 계속 간다 —        ║
# ║      36분 수집 후 RuntimeError 로 전부 버리는 일이 다시 없게 한다.                         ║
# ║   ③ pykrx 없이도 동작한다. 지수구성종목·투자자별 순매수를 KRX 마켓플레이스 bld 로 직접      ║
# ║      호출한다(pykrx 1.2.x 가 쓰는 것과 동일한 bld·파라미터·응답키를 소스에서 확인).         ║
# ║      · 지수구성종목      MDCSTAT00601  indIdx=1, indIdx2=028, trdDd     → output           ║
# ║      · 투자자별 순매수   MDCSTAT02401  strtDd,endDd,mktId,invstTpCd     → output           ║
# ║        invstTpCd 7050=기관합계 / 9000=외국인, mktId=ALL 이면 시장 구분 없이 1회로 끝난다    ║
# ║        → 분기당 2호출 × 40분기 = 80호출. 일별 수집 대비 수백 배 싸다.                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_KRX_IDX_BLD = "dbms/MDC/STAT/standard/MDCSTAT00601"
_KRX_FLOW_BLD = "dbms/MDC/STAT/standard/MDCSTAT02401"
KRX_INVESTOR = {"inst_net": "7050", "forg_net": "9000"}      # 기관합계 / 외국인


def krx_index_members(bd: str) -> Optional[List[str]]:
    """KOSPI200 구성종목 (KRX bld). 로그인 세션이 있을 때만 동작. 최소 150종목이어야 채택."""
    if KRXBLOCK.blocked:
        return None
    for group_id, ticker in (("1", "028"), ("1", "28")):
        js = KRX.json_data(_KRX_IDX_BLD, indIdx=group_id, indIdx2=ticker,
                           trdDd=str(bd).replace("-", ""),
                           tboxindIdx_finder_equidx0_0="코스피 200",
                           codeNmindIdx_finder_equidx0_0="코스피 200",
                           param1indIdx_finder_equidx0_0="")
        if not isinstance(js, dict):
            continue
        items = js.get("output") or js.get("OutBlock_1") or js.get("block1") or []
        if not isinstance(items, list) or not items:
            if js:
                LOG.debug("지수구성종목 응답에 목록 없음 (키: "
                          + ", ".join(list(js.keys())[:6]) + ")")
            continue
        codes = [to_code6(it.get("ISU_SRT_CD") or it.get("ISU_CD") or "")
                 for it in items if isinstance(it, dict)]
        codes = [c for c in codes if c]
        if len(codes) >= 150:
            return codes
    return None


def _pykrx_index_pdf(bd: str) -> Optional[List[str]]:
    """pykrx 지수구성종목(PDF). 버전에 따라 시그니처가 달라 전부 시도한다."""
    if pykrx_stock is None:
        return None
    fn = getattr(pykrx_stock, "get_index_portfolio_deposit_file", None)
    if fn is None:
        return None
    for args in ((bd, "1028"), ("1028", bd), ("1028",)):
        r = KRXG.call(fn, *args)
        if isinstance(r, (list, tuple)) and len(r) >= 150:
            codes = [c for c in (to_code6(x) for x in r) if c]
            if len(codes) >= 150:
                return codes
    return None


# ══ 유니버스 ═════════════════════════════════════════════════════════════════════════════════
def _observed_k200(dates: List[pd.Timestamp], spine: Dict[pd.Timestamp, pd.DataFrame]
                   ) -> Dict[pd.Timestamp, List[str]]:
    """관측 경로(캐시 → KRX bld → pykrx)로 얻은 지수구성. 소급복사 의심분은 폐기한다."""
    cached = VAULT.get_table("krx_index_pdf_1028", scope="shared", union_keys=["date", "code"])
    have: Dict[str, List[str]] = {}
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        for d, g in cached.dropna(subset=["date"]).groupby("date"):
            have[d.strftime("%Y-%m-%d")] = [c for c in g["code"].astype(str).map(to_code6) if c]
        LOG.info(f"공용 캐시에서 지수구성 스냅샷 {len(have)}개 시점 재사용")

    observed: Dict[pd.Timestamp, List[str]] = {}
    for k, v in have.items():
        t = as_ts(k)
        if t is not None:
            observed[t] = v
    new_rows: List[dict] = []
    if RUN_MODE != "CACHED":
        miss = [d for d in dates if d.strftime("%Y-%m-%d") not in have]
        if miss and (KRX.session_ok or pykrx_stock is not None):
            LOG.info(f"KOSPI200 구성종목 관측 시도: {len(miss)}개 시점 "
                     f"(KRX bld{' + pykrx' if pykrx_stock is not None else ''} · 직렬)")
            if pykrx_stock is not None:
                KRXG.warmup()
            bad_streak = 0
            for d in tqdm(miss, desc="지수구성 관측", ncols=88, leave=False):
                bd = d.strftime("%Y%m%d")
                if KRXBLOCK.blocked:
                    LOG.info("KRX 차단 — 지수구성 관측을 중단하고 시총 상위200 재구성으로 "
                             "진행합니다.")
                    break
                codes = krx_index_members(bd) or _pykrx_index_pdf(bd)
                if codes:
                    observed[d] = codes
                    new_rows += [{"date": d.strftime("%Y-%m-%d"), "code": c} for c in codes]
                    bad_streak = 0
                else:
                    bad_streak += 1
                    if bad_streak >= 6:
                        LOG.warn("지수구성 관측이 6회 연속 실패 — 잔여 시점은 시총 상위200 "
                                 "재구성으로 대체합니다(계약이 허용하는 경로).")
                        break
        elif miss:
            LOG.info("KRX 세션·pykrx 모두 없어 지수구성 관측을 건너뜁니다 — "
                     "시총 상위200 재구성으로 진행합니다(universe_definition 은 동일).")

    # ── 소급복사 검증 ① 시점 간 변화율 ──────────────────────────────────────────────────────
    if len(observed) >= 2:
        od = sorted(observed)
        first, last = observed[od[0]], observed[od[-1]]
        span = (od[-1] - od[0]).days
        overlap = len(set(first) & set(last)) / max(len(set(first) | set(last)), 1)
        if (span > 365 and overlap > 0.995) or (span > 365 * 3 and overlap > 0.97):
            LOG.warn(f"지수구성 관측치가 {span}일 간 {overlap:.1%} 동일 — "
                     f"'현재 구성의 소급 복사'로 판단하고 전량 폐기합니다(생존자편향 방지).")
            observed, new_rows = {}, []
    # ── 소급복사 검증 ② 시총 교차검증 (스파인 패널만 사용 — 추가 네트워크 0회) ───────────────
    if observed:
        bad_pts = []
        for d in list(observed):
            snap = spine.get(d)
            if snap is None or not len(snap):
                continue
            mc = pd.to_numeric(col(snap, "marcap"), errors="coerce")
            if mc.notna().sum() < 300:
                continue
            top300 = set(snap.loc[mc.nlargest(300).index, "code"].astype(str))
            obs = set(map(str, observed[d]))
            ratio = len(obs & top300) / max(len(obs), 1)
            if ratio < 0.60:
                bad_pts.append((d, ratio))
                observed.pop(d)
        if bad_pts:
            LOG.warn(f"지수구성 관측 {len(bad_pts)}개 시점이 당시 시총 상위300 과 60% 미만 "
                     f"겹침 — 소급복사 의심으로 해당 시점만 폐기: "
                     f"{[(f'{d:%Y-%m}', f'{r:.0%}') for d, r in bad_pts[:4]]}")
    # ★ 감사 높음(H5): 검증 ②에서 '소급복사 의심'으로 폐기한 시점이 new_rows 에 그대로 남아
    #   캐시에 저장됐고, 다음 실행에서 캐시 경로로 부활해 정확히 그 생존자편향이 들어왔다.
    #   → 살아남은 시점만 저장하고, 캐시에 이미 있던 불량 시점도 함께 제거한다.
    if new_rows:
        _keep = set(observed)
        new_rows = [r for r in new_rows if as_ts(r["date"]) in _keep]
    if cached is not None and len(cached):
        _bad_cached = set(pd.to_datetime(cached["date"], errors="coerce").dropna()) - set(observed)
        _bad_cached &= set(dates)
        if _bad_cached:
            cached = cached[~as_ts_series(cached["date"]).isin(_bad_cached)]
            LOG.warn(f"캐시에 있던 소급복사 의심 지수구성 {len(_bad_cached)}개 시점을 "
                     f"저장본에서도 제외합니다.")
            new_rows = new_rows or [{"date": "1900-01-01", "code": "000000"}]
    if new_rows and observed:
        allr = ([cached] if cached is not None and len(cached) else []) + [pd.DataFrame(new_rows)]
        outc = pd.concat(allr, ignore_index=True)
        outc["date"] = as_ts_series(outc["date"]).dt.strftime("%Y-%m-%d")
        outc = outc.dropna(subset=["date", "code"]).drop_duplicates(["date", "code"])
        VAULT.put_table("krx_index_pdf_1028", outc, scope="shared", domain="universe",
                        source="KRX bld MDCSTAT00601 / pykrx 지수구성종목")
    return observed


def _kospi_mask(snap: pd.DataFrame, sec: pd.DataFrame) -> pd.Series:
    """시장 구분이 비어 있는 소스(FDR 근사·거래대금 프록시)도 마스터로 보완해 KOSPI 를 가린다."""
    mkt = col(snap, "market").astype(str).str.upper()
    is_k = (mkt.str.contains("KOSPI|STK|유가", regex=True, na=False) &
            ~mkt.str.contains("KOSDAQ|KSQ|코스닥", regex=True, na=False))
    if int(is_k.sum()) < 100 and sec is not None and len(sec):
        m2 = (snap["code"].astype(str)
              .map(dict(zip(sec["code"].astype(str), sec["market"].astype(str))))
              .fillna("").str.upper())
        is_k = (m2.str.contains("KOSPI|STK|유가", regex=True, na=False) &
                ~m2.str.contains("KOSDAQ|KSQ|코스닥", regex=True, na=False))
    return is_k


def build_universes(sch: pd.DataFrame, spine_panel: pd.DataFrame, sec: pd.DataFrame
                    ) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """신호일별 (본전략 K200 · 비교전략 시총하위1000) 멤버십을 한 번에 만든다.

    ★ 절대 예외를 던지지 않는다. 만들지 못한 분기는 meta['missing'] 에 남기고 계속 간다."""
    dates = [pd.Timestamp(d) for d in sch["signal_date"]]
    spine = spine_snapshots(spine_panel)
    sec_names = (dict(zip(sec["code"].astype(str), sec["name"].astype(str)))
                 if sec is not None and len(sec) else {})

    observed = _observed_k200(dates, spine)

    k_rows, c_rows, missing = [], [], []
    n_obs = n_recon = 0
    grade_cnt: Counter = Counter()
    for d in dates:
        codes = observed.get(d)
        if codes:
            k_rows += [{"signal_date": d, "code": c, "member_src": "observed"} for c in codes]
            n_obs += 1
        snap = spine.get(d)
        if snap is None or not len(snap):
            if not codes:
                missing.append(d)
            continue
        grade_cnt[str(snap["grade"].iloc[0]) if "grade" in snap.columns else "?"] += 1
        keep = [bool(is_common_stock(c, sec_names.get(c, "")))
                for c in snap["code"].astype(str)]
        common = snap[keep].copy()
        if not len(common):
            if not codes:
                missing.append(d)
            continue
        mc = pd.to_numeric(col(common, "marcap"), errors="coerce")
        rank = pd.to_numeric(col(common, "size_rank"), errors="coerce")
        # 규모 순위: marcap 이 있으면 그것으로, 없으면 스파인이 넣어둔 size_rank(거래대금)로.
        if int(mc.notna().sum()) >= 100:
            common["_rank"] = mc.rank(ascending=False, method="first")
            common = common[mc.notna()]
        elif int(rank.notna().sum()) >= 100:
            common["_rank"] = rank
            common = common[rank.notna()]
        else:
            if not codes:
                missing.append(d)
            continue
        # ── 본전략: KOSPI 보통주 시총 상위 200 재구성 ───────────────────────────────────────
        if not codes:
            k = common[_kospi_mask(common, sec)]
            if len(k) < K200_SIZE * 0.5:      # 시장 구분을 못 믿을 때는 전 시장에서 상위 200
                LOG.debug(f"{d:%Y-%m-%d} KOSPI 구분 불충분({len(k):,}) — 전 시장 상위 "
                          f"{K200_SIZE} 로 재구성")
                k = common
            k = k.nsmallest(K200_SIZE, "_rank") if len(k) else k
            if len(k) >= 50:
                k_rows += [{"signal_date": d, "code": c, "member_src": "mcap_top200"}
                           for c in k["code"].astype(str)]
                n_recon += 1
            else:
                missing.append(d)
        # ── 비교전략: 전 시장 보통주 시총 하위 1000 (순위 숫자가 큰 쪽 = 소형) ───────────────
        if INCLUDE_COMPARISON:
            cm = common.nlargest(CMP_BOTTOM_N, "_rank") if len(common) else common
            if len(cm) >= 50:
                c_rows += [{"signal_date": d, "code": c, "member_src": "mcap_bottom1000"}
                           for c in cm["code"].astype(str)]

    mem = pd.DataFrame(k_rows, columns=["signal_date", "code", "member_src"])
    cmp_mem = pd.DataFrame(c_rows, columns=["signal_date", "code", "member_src"])
    if len(mem):
        mem = mem.drop_duplicates(["signal_date", "code"]).reset_index(drop=True)
    if len(cmp_mem):
        cmp_mem = cmp_mem.drop_duplicates(["signal_date", "code"]).reset_index(drop=True)
    method = ("krx_observed_pdf" if n_obs else "") + \
             ("+" if n_obs and n_recon else "") + \
             ("reconstructed_mcap_top200" if n_recon else "")
    if not method:
        method = "unavailable"

    meta = {"method": method, "n_observed": n_obs, "n_reconstructed": n_recon,
            "missing": [f"{d:%Y-%m-%d}" for d in missing],
            "mcap_grades": dict(grade_cnt),
            "universe_definition": "reconstructed_KOSPI200"}

    LOG.ok(f"KOSPI200 멤버십: 관측 {n_obs}시점 · 재구성 {n_recon}시점 · 결손 {len(missing)}시점 "
           f"→ universe_definition='reconstructed_KOSPI200' (method={method})")
    if missing:
        # ★ v1.0 은 여기서 RuntimeError 를 던져 36분치 수집을 전부 버렸다. v1.1 은 계속 간다.
        LOG.warn(f"유니버스를 만들지 못한 분기 {len(missing)}개는 '현금 분기'로 처리하고 계속 "
                 f"진행합니다(성과표에 투자 분기 수로 표시): "
                 f"{[f'{d:%Y-%m}' for d in missing[:8]]}")
        if len(missing) >= len(dates):
            LOG.error("모든 분기에서 유니버스 구성에 실패했습니다. 위 '시총 스파인 소스별 확보 "
                      "현황' 표에서 어느 소스도 성공하지 못한 이유를 확인하세요. "
                      "가장 흔한 원인: ① marcap 파일 경로 미발견(MARCAP_EXTRA_DIRS) "
                      "② KRX 로그인 실패 ③ 오프라인. 산출물·진단은 그대로 저장됩니다.")
    if INCLUDE_COMPARISON:
        LOG.ok(f"비교전략 유니버스(시총 하위{CMP_BOTTOM_N}) — "
               f"{cmp_mem['signal_date'].nunique() if len(cmp_mem) else 0}개 시점 · "
               f"{len(cmp_mem):,}행")
    PIPE.io("OUT", "MEM", "k200_membership", mem, source=method)
    PIPE.io("OUT", "MEM", "cmp_membership", cmp_mem, source="mcap_bottom1000")
    return mem, cmp_mem, meta


# ══ 수급 윈도우 (F6/F7) ══════════════════════════════════════════════════════════════════════
def krx_net_purchases(frm: str, to: str, invst_tp: str,
                      mkt_id: str = "ALL") -> Optional[pd.DataFrame]:
    """투자자별 순매수 (KRX bld MDCSTAT02401). mktId=ALL 이면 1호출로 전 시장이 온다.
    pykrx 의 투자자별_순매수상위종목 과 동일한 bld/파라미터/응답키를 직접 쓴다 —
    pykrx 인증이 죽어 있어도 마켓플레이스 세션만 있으면 F6/F7 을 만들 수 있다."""
    if KRXBLOCK.blocked:
        return None
    js = KRX.json_data(_KRX_FLOW_BLD, strtDd=str(frm).replace("-", ""),
                       endDd=str(to).replace("-", ""), mktId=mkt_id, invstTpCd=str(invst_tp))
    if not isinstance(js, dict):
        return None
    items = js.get("output") or js.get("OutBlock_1") or []
    if not isinstance(items, list) or not items:
        return None
    d = pd.DataFrame(items)
    if "ISU_SRT_CD" not in d.columns:
        LOG.debug("순매수 응답에 ISU_SRT_CD 없음 (키: "
                  + ", ".join(map(str, list(d.columns)[:10])) + ")")
        return None
    net_c = "NETBID_TRDVAL" if "NETBID_TRDVAL" in d.columns else \
        next((c for c in d.columns if "NETBID" in str(c) and "VAL" in str(c)), None)
    if net_c is None:
        return None
    out = pd.DataFrame({"code": d["ISU_SRT_CD"].astype(str).map(to_code6),
                        "net_buy": _num_kr(d[net_c])})
    out = out.dropna(subset=["code"]).groupby("code", as_index=False)["net_buy"].sum()
    if not len(out):
        return None
    # ★ 반쪽 시장 방어: mktId="ALL" 인데 KRX 가 조용히 KOSPI 만 돌려주면(과거 실제로 있던
    #   동작) 코스닥 종목의 F6/F7 이 통째로 결측이 되고, 그 상태가 'cells_ok=2' 로 캐시에
    #   영구 고착된다. ALL 요청의 최소 종목수를 확인하고 미달이면 시장별로 나눠 다시 받는다.
    if str(mkt_id).upper() == "ALL" and len(out) < 1000:
        parts = []
        for mk in ("STK", "KSQ"):
            r = krx_net_purchases(frm, to, invst_tp, mkt_id=mk)
            if r is not None and len(r):
                parts.append(r)
        if parts:
            merged = (pd.concat(parts, ignore_index=True)
                        .groupby("code", as_index=False)["net_buy"].sum())
            if len(merged) > len(out):
                LOG.debug(f"순매수 ALL 응답이 {len(out)}종목뿐 → 시장별 재조회로 "
                          f"{len(merged)}종목 확보")
                return merged
    return out


def _pykrx_net_purchases(frm: str, to: str, market: str, investor: str
                         ) -> Optional[pd.DataFrame]:
    if pykrx_stock is None:
        return None
    for fname in ("get_market_net_purchases_of_equities",
                  "get_market_net_purchases_of_equities_by_ticker"):
        fn = getattr(pykrx_stock, fname, None)
        if fn is None:
            continue
        d = KRXG.call(fn, frm, to, market, investor)
        if d is None or not len(d):
            continue
        d = d.reset_index()
        cl = {str(c): c for c in d.columns}
        tick = cl.get("티커") or d.columns[0]
        net_c = next((cl[k] for k in cl if "순매수" in k and "대금" in k), None) \
            or next((cl[k] for k in cl if "순매수" in k), None)
        if net_c is None:
            continue
        out = pd.DataFrame({"code": d[tick].astype(str).map(to_code6),
                            "net_buy": pd.to_numeric(d[net_c], errors="coerce")})
        out = out.dropna(subset=["code"])
        if len(out):
            return out
    return None


def fetch_flow_windows(sch: pd.DataFrame, cal: np.ndarray) -> pd.DataFrame:
    """신호일마다 [신호일-19거래일, 신호일] 윈도우의 기관/외국인 순매수대금 합계.
    KRX bld 경로는 분기당 2호출(mktId=ALL) → 40분기 80호출. pykrx 는 폴백."""
    cached = VAULT.get_table("krx_flow_windows", scope="shared",
                             union_keys=["signal_date", "code"])
    have = set()
    if cached is not None and len(cached):
        cached["signal_date"] = as_ts_series(cached["signal_date"])
        # ★ 감사 높음(H3): fillna(2) 는 '구 빈티지(NaN)'를 완결로 오판한다. cells_ok 컬럼이
        #   아예 없는 구 캐시도 완결로 취급해, F7 이 전량 결측인 채 재수집 대상에서 빠졌다.
        #   → NaN 은 미완결로 본다(재수집은 분기당 2호출뿐이라 비용이 없다).
        if "cells_ok" in cached.columns:
            ok = (cached.groupby(cached["signal_date"].dt.strftime("%Y-%m-%d"))["cells_ok"]
                  .max())
            have = set(ok[ok.notna() & (ok >= 2)].index)
            _stale = int(len(ok) - len(have))
            if _stale:
                LOG.info(f"수급 캐시 {_stale}개 시점은 완결성 미확인(구 빈티지) — 재수집합니다.")
        else:
            LOG.info("수급 캐시에 완결성 메타(cells_ok)가 없어 전 시점을 재수집합니다 "
                     "(분기당 2호출 · 비용 무시 가능).")
            have = set()
        LOG.info(f"공용 캐시에서 수급 윈도우 {len(have)}개 시점 재사용")

    cal_idx = pd.DatetimeIndex(cal)
    todo = [pd.Timestamp(d) for d in sch["signal_date"]
            if pd.Timestamp(d).strftime("%Y-%m-%d") not in have]
    new_frames = []
    use_bld = bool(KRX.session_ok)
    use_pykrx = pykrx_stock is not None
    if todo and RUN_MODE != "CACHED" and (use_bld or use_pykrx):
        if use_pykrx:
            KRXG.warmup()
        paths = [s for s, on in (("KRX bld(2호출/분기)", use_bld),
                                 ("pykrx(4호출/분기)", use_pykrx)) if on]
        LOG.info(f"수급 윈도우 수집 {len(todo)}개 시점 — 경로: {' → '.join(paths)}")
        n_bld = n_pk = 0
        for d in tqdm(todo, desc="수급 윈도우", ncols=88, leave=False):
            if KRXBLOCK.blocked and not use_pykrx:
                LOG.warn("KRX 차단으로 수급 수집을 중단합니다 — F6/F7 은 결측 처리됩니다.")
                break
            pos = int(cal_idx.searchsorted(d, side="right")) - 1
            if pos < 0:
                continue
            frm = pd.Timestamp(cal_idx[max(0, pos - 19)]).strftime("%Y%m%d")
            to = pd.Timestamp(cal_idx[pos]).strftime("%Y%m%d")
            parts, n_cells = [], 0
            for colname, invst in KRX_INVESTOR.items():
                rr = None
                if use_bld:
                    rr = krx_net_purchases(frm, to, invst)
                    if rr is not None:
                        n_bld += 1
                if rr is None and use_pykrx:
                    inv_nm = "기관합계" if colname == "inst_net" else "외국인"
                    per = [x for x in (_pykrx_net_purchases(frm, to, m, inv_nm)
                                       for m in ("KOSPI", "KOSDAQ")) if x is not None]
                    if per:
                        rr = (pd.concat(per, ignore_index=True)
                              .groupby("code", as_index=False)["net_buy"].sum())
                        n_pk += 1
                if rr is None or not len(rr):
                    continue
                parts.append(rr.rename(columns={"net_buy": colname}))
                n_cells += 1
            if not parts:
                continue
            merged = parts[0]
            for p in parts[1:]:
                merged = merged.merge(p, on="code", how="outer")
            merged["signal_date"] = d
            merged["cells_ok"] = n_cells       # 2 미만이면 다음 실행에서 자동 재수집
            if n_cells < 2:
                LOG.warn(f"{d:%Y-%m-%d} 수급 부분수집({n_cells}/2) — 이번엔 쓰되 "
                         f"다음 실행에서 재수집합니다.")
            new_frames.append(merged)
        if n_bld or n_pk:
            LOG.ok(f"수급 수집 완료 — KRX bld {n_bld}셀 · pykrx {n_pk}셀")
    elif todo:
        LOG.warn(f"수급 윈도우 미수집 {len(todo)}개 시점 (CACHED 모드 또는 KRX 세션·pykrx 부재).\n"
                 f"    ★ F6/F7 이 결측이면 '7팩터 모두 유효' 조건 때문에 해당 분기 적격종목이 "
                 f"0이 됩니다.\n"
                 f"    → 상단 KRX_MARKETPLACE_ID/PW 를 채우거나 pip install pykrx 후 재실행하세요.")

    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        return pd.DataFrame(columns=["signal_date", "code", "inst_net", "forg_net"])
    fl = pd.concat(frames, ignore_index=True)
    fl["signal_date"] = as_ts_series(fl["signal_date"])
    fl["code"] = fl["code"].astype(str).map(to_code6)
    fl = (fl.dropna(subset=["signal_date", "code"])
            .drop_duplicates(["signal_date", "code"], keep="last"))
    if new_frames:
        out = fl.copy()
        out["signal_date"] = out["signal_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_flow_windows", out, scope="shared", domain="flow",
                        source="KRX bld MDCSTAT02401 / pykrx 순매수(20거래일 윈도우)")
    PIPE.io("OUT", "MEM", "flow_windows", fl, source="krx_bld/pykrx")
    return downcast(fl)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-E  DART 분기 실적 (PIT) — F1(서프라이즈 확률 프록시)·F2/F3(EPS 성장 프록시)의 입력      ║
# ║  ★ PIT 핵심: knowledge_date = 접수일자(rcept_no 앞 8자리). 결산기준일이 아니다.             ║
# ║    없으면 법정 제출기한(분기 45일/사업보고서 90일)으로 '늦게 알았다' 방향의 보수적 추정.     ║
# ║  ★ 배치: fnlttMultiAcnt 는 corp_code 100개/호출 → 2,500사×10년×4분기 ≈ 1,000호출이면 끝.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
REPRT_DEADLINE_DAYS = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
REPRT_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
DART_MULTI_BATCH = 100
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "rcept_no"]


def _knowledge_from_rcept(rcept_no: Any, reprt_code: str, year: int) -> Optional[pd.Timestamp]:
    s = re.sub(r"\D", "", str(rcept_no or ""))
    if len(s) >= 8:
        t = as_ts(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = REPRT_PERIOD_END.get(reprt_code, (12, 31))
    base = as_ts(f"{year}-{mm:02d}-{dd:02d}")
    return None if base is None else base + pd.Timedelta(days=REPRT_DEADLINE_DAYS.get(reprt_code, 90))


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정(매출·영업이익·순이익 등) 배치 수집 — 기존 공용 테이블 dart_multi_raw 와
    같은 이름/스키마를 쓰므로 다른 전략과 캐시가 완전 호환된다."""
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용 ({len(done):,} 조합)")
    if not DART_API_KEY or RUN_MODE == "CACHED":
        if not DART_API_KEY and RUN_MODE != "CACHED":
            LOG.warn("DART_API_KEY 미입력 — 실적 기반 팩터(F1/F2/F3)는 캐시분만 사용합니다.")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    reprts = [REPRT_CODES[k] for k in ("Q1", "H1", "Q3", "FY")]
    corps = sorted({str(c) for c in corp_codes if str(c).strip() and str(c) != "nan"})
    jobs = []
    for y in sorted(set(int(y) for y in years), reverse=True):   # 최근 연도 우선(끊겨도 최신 확보)
        for r in reprts:
            todo = [c for c in corps if (c, y, r) not in done]
            for i in range(0, len(todo), DART_MULTI_BATCH):
                jobs.append((todo[i:i + DART_MULTI_BATCH], y, r))
    if jobs:
        # ★ 실제 필요 호출 수를 먼저 계산해 보여준다. corp_code 100개/1호출 배치라
        #   2,500종목 × 14년 × 4보고서라도 25배치 × 56 = 약 1,400회로 끝난다(한도의 7%).
        #   내부 재시도(tries=2)를 감안한 최악치까지 함께 표시한다.
        need = len(jobs)
        if DBUDGET is not None:
            DBUDGET.preflight(need * 2, what=f"DART 주요계정 배치 {need:,}회(최악 재시도 포함)")
        LOG.info(f"DART 주요계정: 종목 {len(corps):,}사 × 연도 "
                 f"{len(set(int(y) for y in years))}개 × 보고서 4종 → "
                 f"배치 {need:,}회 (배치당 최대 {DART_MULTI_BATCH}사)")

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
        res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주요계정(배치)")
        got = [d for d in res if d is not None and len(d)]
    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    M = pd.concat(frames, ignore_index=True)
    M = M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
                           "account_nm"], keep="last")
    if got:
        VAULT.put_table("dart_multi_raw", M, scope="shared", domain="dart",
                        source="opendart fnlttMultiAcnt")
    LOG.ok(f"DART 주요계정 {len(M):,}행 · {M['corp_code'].nunique():,}사")
    return M


def tidy_dart_earnings(raw: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (code, period_end, knowledge_date, ni_q, ni_ttm, op_q, rev_q) 분기 실적.
    누적 공시 → 분기 단독 차분(직전 분기가 실재할 때만 — 없는 분기를 0 취급 금지)."""
    cols = ["code", "corp_code", "period_end", "knowledge_date", "event_date",
            "ni_q", "ni_ttm", "op_q", "rev_q"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=cols)
    d = raw.copy()
    d["amount"] = pd.to_numeric(
        d["thstrm_amount"].astype(str).str.replace(",", "", regex=False)
        .str.replace("−", "-", regex=False), errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    d["fs_div"] = d["fs_div"].astype(str).str.upper()

    pats = {"net_income": r"^당기순이익|ProfitLoss$", "op_income": r"^영업이익",
            "revenue": r"^매출액|^수익\(매출액\)|^영업수익"}
    picked = []
    for item, pat in pats.items():
        hit = d[d["account_nm"].str.contains(pat, regex=True, na=False)].copy()
        if hit.empty:
            continue
        # 연결(CFS) 우선, 없으면 별도(OFS) — 같은 (사·기간)에 둘 다 있으면 CFS 승.
        # kind="stable" — 동순위 중복행의 생존자가 정렬 구현에 좌우되지 않게(재현성).
        hit["_pri"] = np.where(hit["fs_div"].str.contains("CFS"), 0, 1)
        hit = (hit.sort_values(["_pri"], kind="stable")
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        picked.append(hit.assign(item=item)[["corp_code", "bsns_year", "reprt_code",
                                             "rcept_no", "item", "amount"]])
    if not picked:
        return pd.DataFrame(columns=cols)
    L = pd.concat(picked, ignore_index=True)
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values="amount", aggfunc="first").reset_index()
    rc = (L.dropna(subset=["rcept_no"]).sort_values("rcept_no")
           .groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"].first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")
    W["period_end"] = [as_ts(f"{int(y)}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    gk = ["corp_code", "bsns_year"]
    W["_q_prev"] = W.groupby(gk)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for src, dst in (("net_income", "ni"), ("op_income", "op"), ("revenue", "rev")):
        v = col(W, src)
        prev = v.groupby([W[k] for k in gk]).shift(1)
        W[dst + "_q"] = np.where(W["q"] == 1, v, np.where(contiguous, v - prev, np.nan))
    W = W.drop(columns=["_q_prev"])
    W = W.sort_values(["corp_code", "period_end"]).reset_index(drop=True)
    # TTM: 4분기 이동합 (min_periods=4 — 3개로 TTM 이라 부르면 과소계상)
    W["ni_ttm"] = (W.groupby("corp_code")["ni_q"]
                    .transform(lambda s: s.rolling(4, min_periods=4).sum()))

    c2 = sec.dropna(subset=["corp_code"]) if sec is not None and len(sec) else pd.DataFrame()
    if len(c2):
        cmap = dict(zip(c2["corp_code"].astype(str), c2["code"].astype(str)))
        W["code"] = W["corp_code"].astype(str).map(cmap)
    else:
        W["code"] = np.nan
    W = W.dropna(subset=["code", "period_end", "knowledge_date"])
    W["event_date"] = W["period_end"]
    out = W[["code", "corp_code", "period_end", "knowledge_date", "event_date",
             "ni_q", "ni_ttm", "op_q", "rev_q"]].copy()
    out = pit_frame(out, "event_date", "knowledge_date", source="dart")
    LOG.ok(f"DART 분기실적 정제 {len(out):,}행 · {out['code'].nunique():,}종목 "
           f"(knowledge=접수일, 누적→분기 차분)")
    PIPE.io("OUT", "MEM", "dart_earnings_q", out)
    return downcast(out)


def earnings_asof(earn: pd.DataFrame, asof: pd.Timestamp, n_last: int = 14) -> pd.DataFrame:
    """신호일 기준 '알 수 있었던' 분기실적의 종목별 최근 n_last 개. (PIT 절단 단일 통로)"""
    if earn is None or earn.empty:
        return pd.DataFrame(columns=earn.columns if earn is not None else [])
    d = earn[earn["knowledge_date"] <= asof]
    if d.empty:
        return d
    d = d.sort_values(["code", "period_end"])
    return d.groupby("code", observed=True).tail(n_last)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-F  애널리스트 리포트 — 한경컨센서스 + 네이버리서치 수집 · 원장 · 애널리스트 연결        ║
# ║  두 소스의 역할: 한경(작성자·목표주가를 리스트에서 줌) + 네이버(종목코드 확실, 폭 넓음)     ║
# ║  → dedup_key 병합으로 다중소스 원장을 만들고, 연결 상태를 감사표로 출력한다.               ║
# ║  F4(스마트-일반 갭 프록시)·F5(컨센서스 1개월 리비전 프록시)의 입력이 된다.                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

HK_BASE = "https://consensus.hankyung.com"
HK_LIST = HK_BASE + "/analysis/list"
NV_BASE = "https://finance.naver.com/research/"
NV_API = "https://stock.naver.com/api/stockSecurity/researches/v2/{cat}"

REPORT_COLS = ["report_uid", "source", "src_report_id", "pub_date", "category", "title",
               "stock_code", "stock_name", "broker_raw", "broker_id", "broker_name",
               "analyst_raw", "target_price", "opinion", "pdf_url", "detail_url",
               "event_date", "knowledge_date"]

_NULL_TOKENS = {"", "-", "--", "0", "n/a", "na", "없음", "투자의견없음", "nr", "not rated"}
_CODE_IN_TITLE = re.compile(r"[（(]\s*([0-9]{6})\s*[)）]")
_YYMMDD = re.compile(r"^\s*(\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*$")


def _clean_cell(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def _dedup_repeat(s: str) -> str:
    """한경 제목이 'ABCABC' 처럼 반복되는 알려진 버그 복원."""
    s = _clean_cell(s)
    n = len(s)
    if n < 8:
        return s
    for k in (2, 3):
        if n % k == 0 and s[: n // k] * k == s:
            return s[: n // k]
    return s


def parse_target_price(x: Any) -> Optional[float]:
    t = _clean_cell(x).lower().replace(",", "").replace("원", "")
    if t in _NULL_TOKENS:
        return None                    # '0'을 0원 목표주가로 넣으면 리비전이 오염된다
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    return v if 0 < v <= 5e7 else None


def parse_kr_date(s: Any) -> Optional[str]:
    """'YY.MM.DD' 는 반드시 명시 파싱 — pandas 자동추론은 연·일을 뒤바꾼다(조용한 시간축 붕괴)."""
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


def code_from_title(title: str) -> Optional[str]:
    m = _CODE_IN_TITLE.search(str(title or ""))
    return m.group(1) if m else None


BROKER_CANON: List[Tuple[str, str]] = [
    (r"미래에셋(대우|증권|생명)?|대우증권|KDB대우", "미래에셋증권"),
    (r"NH투자|우리투자증권|NH농협증권", "NH투자증권"),
    (r"한국투자|한투증권", "한국투자증권"), (r"삼성증권", "삼성증권"),
    (r"KB(증권|투자증권)|현대증권", "KB증권"),
    (r"신한(투자증권|금융투자|금투)", "신한투자증권"),
    (r"하나(증권|금융투자|금투)", "하나증권"), (r"키움", "키움증권"),
    (r"메리츠(증권|종금증권|종합금융증권)", "메리츠증권"), (r"대신증권", "대신증권"),
    (r"유안타|동양증권", "유안타증권"), (r"한화(투자증권|증권)", "한화투자증권"),
    (r"교보증권", "교보증권"), (r"IBK(투자증권|증권)", "IBK투자증권"),
    (r"신영증권", "신영증권"), (r"현대차(증권|투자증권)|HMC투자증권", "현대차증권"),
    (r"SK증권", "SK증권"), (r"유진(투자증권|증권)", "유진투자증권"),
    (r"(iM|아이엠)증권|하이투자증권", "iM증권"), (r"LS증권|이베스트|eBEST", "LS증권"),
    (r"다올투자증권|KTB투자증권|다올", "다올투자증권"),
    (r"DB(금융투자|증권)|동부증권", "DB금융투자"), (r"BNK(투자증권|증권)", "BNK투자증권"),
]
_BROKER_RE = [(re.compile(p), n) for p, n in BROKER_CANON]


def normalize_broker(raw: Any) -> Tuple[str, str]:
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
    t = _clean_cell(raw)
    if not t:
        return []
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"(연구원|애널리스트|수석|책임|선임|팀장|센터장|위원)", " ", t)
    t = re.sub(r"외\s*\d+\s*인?", " ", t)
    out = []
    for p in _ANALYST_SPLIT.split(t):
        p = re.sub(r"[^가-힣A-Za-z]", "", p).strip()
        if 2 <= len(p) <= 12 and not re.fullmatch(r"(증권|투자|금융|리서치)+", p):
            out.append(p)
    return list(dict.fromkeys(out))


# ── 한경컨센서스 (skinType=business: 작성자·적정가격 컬럼 제공) ─────────────────────────────
def _table_headers(table) -> List[str]:
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if len(ths) >= 3:
            return [_clean_cell(th.get_text()) for th in ths]
    return []


def _pick(rowmap: Dict[str, Any], *names) -> Optional[Any]:
    for n in names:
        for k, v in rowmap.items():
            if n in k:
                return v
    return None


def _hk_parse(html: str) -> List[dict]:
    soup = soup_of(html)
    if soup is None:
        return []
    table = None
    for sel in ("div.table_style01 table", "#contents table", "table"):
        t = soup.select_one(sel)
        if t is not None and t.find("tr") is not None:
            table = t
            break
    if table is None or "데이터가 없습니다" in html:
        return []
    headers = _table_headers(table)
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [_clean_cell(td.get_text(" ")) for td in tds]
        rm = {headers[i]: texts[i] for i in range(len(texts))} \
            if headers and len(headers) == len(texts) else {}
        ridx = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"report_idx=(\d+)", a["href"])
            if m:
                ridx = m.group(1)
                break
        if ridx is None:
            continue
        date_s = _pick(rm, "작성일", "날짜") or next(
            (t for t in texts if re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", t)), None)
        title = _pick(rm, "제목")
        if not title:
            a = tr.find("a", href=re.compile("report_idx"))
            title = _clean_cell(a.get_text(" ")) if a else ""
        title = _dedup_repeat(title)
        tp = _pick(rm, "적정가격", "목표주가", "적정주가")
        an = _pick(rm, "작성자", "애널리스트")
        bk = _pick(rm, "제공출처", "증권사", "출처")
        if not rm:                                     # 헤더 실패 시 내용 기반 폴백
            tp = tp or next((t for t in texts if re.fullmatch(r"[\d,]{3,12}", t)), None)
            cand = [c for c in texts if c and c != title and not re.fullmatch(r"[\d,.\-]+", c)]
            bk = bk or next((c for c in cand if "증권" in c or "투자" in c), None)
            an = an or next((c for c in cand if c != bk and 1 <= len(c) <= 30), None)
        out.append({"source": "hankyung", "src_report_id": str(ridx), "category": "company",
                    "pub_date": parse_kr_date(date_s), "title": title,
                    "stock_code": code_from_title(title),
                    "stock_name": (title[:_CODE_IN_TITLE.search(title).start()].strip()
                                   if _CODE_IN_TITLE.search(title or "") else ""),
                    "broker_raw": _clean_cell(bk), "analyst_raw": _clean_cell(an),
                    "target_price": parse_target_price(tp), "opinion": None,
                    "pdf_url": HK_BASE + f"/analysis/downpdf?report_idx={ridx}",
                    "detail_url": None})
    return out


def hankyung_collect(start: str, end: str, page_size: int = 80, max_pages: int = 400
                     ) -> pd.DataFrame:
    """연 단위 스윕. '새 항목 0건 2회 연속'일 때만 조기 종료(한 페이지 파싱 실패로
    그 해 전체가 잘리는 사고 방지)."""
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    jobs = [(as_ts(max(as_ts(f"{y}-01-01"), as_ts(start))),
             as_ts(min(as_ts(f"{y}-12-31"), as_ts(end)))) for y in years]

    def _sweep(job):
        sd, ed = job
        got, seen, empty_streak = [], set(), 0
        for page in range(1, max_pages + 1):
            html = http_get(HK_LIST, source="hankyung", tries=3, referer=HK_BASE + "/",
                            timeout=30, params={
                                "skinType": "business", "sdate": sd.strftime("%Y-%m-%d"),
                                "edate": ed.strftime("%Y-%m-%d"), "now_page": page,
                                "pagenum": page_size, "report_type": "CO",
                                "order_type": "", "search_text": "", "business_code": ""})
            if not html:
                break
            batch = _hk_parse(html)
            fresh = [b for b in batch if b["src_report_id"] not in seen]
            seen.update(b["src_report_id"] for b in fresh)
            got.extend(fresh)
            # 빈 파싱(일시 차단/레이아웃 요동)도 '새 항목 0건'과 동일하게 연속 2회일 때만
            # 중단한다 — 한 페이지 실패로 그 해 전체가 잘리는 무음 과소수집 방지.
            if not fresh:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
        return got

    res = pmap_io(_sweep, jobs, workers=min(4, N_WORKERS_IO), desc="한경컨센서스")
    rows = [r for chunk in res if chunk for r in chunk]
    d = pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPORT_COLS)
    LOG.ok(f"한경컨센서스 {len(d):,}건 (작성자 보유 "
           f"{int(d['analyst_raw'].astype(str).str.len().gt(0).sum()) if len(d) else 0:,} · "
           f"목표주가 {int(d['target_price'].notna().sum()) if len(d) else 0:,})")
    PIPE.io("IN", "HTTP", "hankyung:list", d, source=HK_LIST)
    return d


# ── 네이버 리서치 (JSON API 우선 → HTML 폴백) ───────────────────────────────────────────────
def naver_collect(start: str, end: str, max_pages: int = 1200) -> pd.DataFrame:
    rows = []
    hdr = {"Accept": "application/json,text/plain,*/*", "Referer": "https://stock.naver.com/"}
    index = 0
    while index < 60000:
        js = http_json(NV_API.format(cat="company"), source="naver", tries=2, headers=hdr,
                       params={"index": index, "size": 100,
                               "startDate": as_ts(start).strftime("%Y-%m-%d"),
                               "endDate": as_ts(end).strftime("%Y-%m-%d")})
        items = (js if isinstance(js, list) else
                 (js.get("researches") or js.get("list") or js.get("items") or
                  js.get("content") or []) if isinstance(js, dict) else [])
        if not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append({"source": "naver", "category": "company",
                         "src_report_id": str(it.get("id") or it.get("nid") or
                                              it.get("researchId") or ""),
                         "pub_date": it.get("createDate") or it.get("date") or
                         it.get("writeDate"),
                         "title": _dedup_repeat(str(it.get("title") or "")),
                         "stock_code": to_code6(it.get("itemCode") or it.get("stockCode") or ""),
                         "stock_name": str(it.get("itemName") or it.get("stockName") or ""),
                         "broker_raw": str(it.get("brokerName") or it.get("broker") or ""),
                         "analyst_raw": str(it.get("analyst") or it.get("writer") or ""),
                         "target_price": parse_target_price(it.get("targetPrice") or
                                                            it.get("goalPrice")),
                         "opinion": None, "pdf_url": it.get("fileUrl") or it.get("pdfUrl"),
                         "detail_url": None})
        if len(items) < 100:
            break
        index += len(items)
    if len(rows) > 50:
        d = pd.DataFrame(rows)
        d = d[d["src_report_id"].astype(str).str.len() > 0]
        LOG.ok(f"네이버 JSON API {len(d):,}건")
        PIPE.io("IN", "HTTP", "naver:json", d, source=NV_API)
        return d

    # HTML 폴백 (company 리스트)
    base = urljoin(NV_BASE, "company_list.naver")
    probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                     params={"searchType": "writeDate",
                             "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                             "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": 1})
    if not probe:
        LOG.warn("네이버 리서치 접근 실패 — 이 소스는 건너뜁니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    soup = soup_of(probe)
    last = 1
    if soup is not None:
        for a in soup.select("table.Nnavi a[href]"):
            m = re.search(r"page=(\d+)", a["href"])
            if m:
                last = max(last, int(m.group(1)))
    last = min(last, max_pages)

    def _pg(p: int):
        h = probe if p == 1 else http_get(
            base, source="naver", referer=NV_BASE, force_enc="euc-kr", tries=3,
            params={"searchType": "writeDate",
                    "writeFromDate": as_ts(start).strftime("%Y-%m-%d"),
                    "writeToDate": as_ts(end).strftime("%Y-%m-%d"), "page": p})
        s = soup_of(h)
        if s is None:
            return []
        table = s.select_one("table.type_1") or s.select_one("table")
        if table is None:
            return []
        out = []
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5 or tr.find("th") is not None:
                continue
            texts = [_clean_cell(td.get_text(" ")) for td in tds]
            nid, title = None, None
            for a in tr.find_all("a", href=True):
                m = re.search(r"nid=(\d+)", a["href"])
                if m:
                    nid = m.group(1)
                    title = _clean_cell(a.get_text(" "))
                    break
            if nid is None:
                continue
            code = None
            a_item = tr.select_one("a.stock_item[href]")
            if a_item is not None:
                mm = re.search(r"code=(\d{6})", a_item["href"])
                code = mm.group(1) if mm else None
            pdf = next((a["href"] for a in tr.find_all("a", href=True)
                        if a["href"].lower().endswith(".pdf")), None)
            bk = next((t for t in texts if ("증권" in t or "투자" in t) and t != title), "")
            dt_s = next((t for t in texts if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", t)), None)
            out.append({"source": "naver", "category": "company", "src_report_id": str(nid),
                        "pub_date": parse_kr_date(dt_s), "title": _dedup_repeat(title or ""),
                        "stock_code": code or code_from_title(title or ""),
                        "stock_name": "", "broker_raw": bk, "analyst_raw": "",
                        "target_price": None, "opinion": None,
                        "pdf_url": pdf, "detail_url": None})
        return out

    res = pmap_io(_pg, list(range(1, last + 1)), workers=min(6, N_WORKERS_IO), desc="네이버 HTML")
    rows = [r for chunk in res if chunk for r in chunk]
    d = pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPORT_COLS)
    LOG.ok(f"네이버 리서치(HTML) {len(d):,}건")
    PIPE.io("IN", "HTTP", "naver:html", d, source=base)
    return d


# ── 원장 병합 (멱등) · 애널리스트 연결 · 감사 ───────────────────────────────────────────────
def _atoms(vals, sep: str) -> List[str]:
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
    c = sorted({str(v).strip() for v in vals
                if v is not None and str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "<na>")})
    return c[0] if c else ""


def build_report_master(frames: Sequence[pd.DataFrame], sec: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 → 보고서 원장. 중복 '제거'가 아니라 '병합'(정보를 버리지 않는다).
    재실행 시에도 uid·source 토큰이 불변인 멱등 병합 — 캐시가 다시 입력으로 돌아와도 안전."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        LOG.warn("수집·캐시된 리포트가 없습니다 — F4/F5 는 DART 폴백 경로만 사용합니다.")
        return pd.DataFrame(columns=REPORT_COLS)
    allcols = sorted(set().union(*[set(map(str, f.columns)) for f in frames]))
    d = pd.concat([f.reindex(columns=allcols) for f in frames], ignore_index=True)
    for c in REPORT_COLS:                     # adopt 전용 입력(열 부족)에서도 KeyError 없이
        if c not in d.columns:
            d[c] = None
    n0 = len(d)
    d["pub_date"] = as_ts_series(d["pub_date"])
    lo, hi = as_ts("1999-01-01"), as_ts(BACKTEST_END) + pd.Timedelta(days=400)
    bad = d["pub_date"].isna() | (d["pub_date"] < lo) | (d["pub_date"] > hi)
    if bad.any():
        LOG.warn(f"발간일 무효 리포트 {int(bad.sum()):,}건 제외 ({100*bad.mean():.2f}%) — "
                 f"비율이 크면 소스 날짜형식 변경을 의심하세요(parse_kr_date).")
    d = d[~bad]
    if not len(d):
        return pd.DataFrame(columns=REPORT_COLS)

    bid = d["broker_raw"].map(normalize_broker)
    d["broker_id"] = [x[0] for x in bid]
    d["broker_name"] = [x[1] for x in bid]
    d["stock_code"] = d["stock_code"].map(to_code6)
    need = d["stock_code"].isna()
    if need.any():
        d.loc[need, "stock_code"] = d.loc[need, "title"].map(code_from_title)
    need = d["stock_code"].isna() & d["stock_name"].astype(str).str.len().gt(0)
    if need.any() and sec is not None and len(sec):
        n2c = {}
        for _, r in sec.iterrows():
            nn = norm_corp_name(r.get("name"))
            if nn and nn not in n2c and isinstance(r.get("code"), str):
                n2c[nn] = r["code"]
        d.loc[need, "stock_code"] = d.loc[need, "stock_name"].map(
            lambda s: n2c.get(norm_corp_name(s)))

    d["title"] = d["title"].map(_dedup_repeat)
    _uid_new = [sha1_str(s, i) for s, i in zip(d["source"].astype(str),
                                               d["src_report_id"].astype(str))]
    _uid_old = (d["report_uid"].tolist() if "report_uid" in d.columns else [None] * len(d))
    d["report_uid"] = [u if isinstance(u, str) and len(u) >= 8 else n
                       for u, n in zip(_uid_old, _uid_new)]
    d["dedup_key"] = [sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b, c or "",
                               norm_text(t)[:40])
                      for dt, b, c, t in zip(d["pub_date"], d["broker_id"],
                                             d["stock_code"].fillna(""), d["title"])]
    n1 = len(d)
    m = d.groupby("dedup_key", as_index=False).agg(**{
        "report_uid": ("report_uid", "min"),
        "src_report_id": ("src_report_id", lambda s: "|".join(_atoms(s, "|"))),
        "source": ("source", lambda s: "+".join(_atoms(s, "+"))),
        "category": ("category", _pick_str),
        "pub_date": ("pub_date", "min"),
        "title": ("title", lambda s: max(sorted(set(map(str, s))), key=len)),
        "stock_code": ("stock_code", lambda s: _pick_str(s) or None),
        "stock_name": ("stock_name", _pick_str),
        "broker_id": ("broker_id", "min"),
        "broker_name": ("broker_name", "min"),
        "broker_raw": ("broker_raw", _pick_str),
        "analyst_raw": ("analyst_raw", _pick_str),
        "target_price": ("target_price", "max"),
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "pdf_url": ("pdf_url", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    LOG.info(f"보고서 원장 병합: 수집 {n0:,} → 날짜유효 {n1:,} → 고유 {len(m):,}건 "
             f"(소스 간 중복 병합 {n1 - len(m):,})")
    m["event_date"] = m["pub_date"]
    m["knowledge_date"] = m["pub_date"]          # 리포트는 발간=공개
    m = pit_frame(m, "event_date", "knowledge_date", source="research")
    PIPE.io("OUT", "MEM", "report_master", m, source="hankyung+naver+cache")
    return m


def build_analyst_ledger(rep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """애널리스트 마스터 + 보고서↔애널리스트 연결표(방법·신뢰도 명기)."""
    a_cols = ["analyst_id", "name", "broker_id", "broker_name"]
    l_cols = ["report_uid", "analyst_id", "name", "broker_id", "broker_name", "role",
              "link_method", "link_conf", "pub_date", "stock_code", "target_price"]
    if rep is None or rep.empty:
        return pd.DataFrame(columns=a_cols), pd.DataFrame(columns=l_cols)
    links = []
    for r in rep.itertuples(index=False):
        raw = getattr(r, "analyst_raw", "") or ""
        names, method, conf = [], "", 0.0
        if str(raw).strip():
            names = split_analysts(raw)
            method, conf = "list_field", 0.98
        if not names:
            continue
        for i, nm in enumerate(names):
            links.append({"report_uid": r.report_uid, "name": nm, "broker_id": r.broker_id,
                          "broker_name": r.broker_name, "role": "lead" if i == 0 else "co",
                          "link_method": method, "link_conf": conf, "pub_date": r.pub_date,
                          "stock_code": r.stock_code, "target_price": r.target_price})
    if not links:
        LOG.warn("애널리스트를 한 건도 식별하지 못했습니다 — F4 스마트/일반 분리가 불가하여 "
                 "해당 분기 F4 는 결측 처리됩니다.")
        return pd.DataFrame(columns=a_cols), pd.DataFrame(columns=l_cols)
    L = pd.DataFrame(links)
    L["name"] = L["name"].map(lambda s: re.sub(r"\s+", "", str(s)))
    # 동일성 = (증권사, 이름) — 동명이인은 소속으로 구분
    L["analyst_id"] = [sha1_str("analyst", b, n)[:14] for b, n in zip(L["broker_id"], L["name"])]
    A = (L.groupby("analyst_id", as_index=False)
          .agg(name=("name", "first"), broker_id=("broker_id", "first"),
               broker_name=("broker_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_targets=("target_price", lambda s: int(s.notna().sum()))))
    LOG.ok(f"애널리스트 원장 {len(A):,}명 · 연결 {len(L):,}건")
    PIPE.io("OUT", "MEM", "analyst_master", A)
    PIPE.io("OUT", "MEM", "report_analyst_link", L)
    return A, L


def audit_linkage(rep: pd.DataFrame, A: pd.DataFrame, L: pd.DataFrame):
    """★ 사용자 요구: '보고서 ↔ 식별된 애널리스트 연결과 다중소스 원장 연결을 한눈에'."""
    LOG.banner("원장 무결성 감사 — 보고서 ↔ 애널리스트 ↔ 종목",
               "연결이 깨진 지점을 연도·소스별로 노출합니다. 낮으면 낮은 대로 보고합니다.")
    if rep is None or rep.empty:
        LOG.warn("보고서 원장이 비어 감사를 수행할 수 없습니다.")
        return
    r = rep.copy()
    r["year"] = r["pub_date"].dt.year
    linked = set(L["report_uid"]) if L is not None and len(L) else set()
    r["has_analyst"] = r["report_uid"].isin(linked)
    r["has_code"] = r["stock_code"].notna()
    r["has_tp"] = r["target_price"].notna()
    rows = []
    for y, g in r.groupby("year"):
        rows.append([int(y), f"{len(g):,}",
                     f"{100*g['has_analyst'].mean():.1f}%",
                     f"{100*g['has_code'].mean():.1f}%",
                     f"{100*g['has_tp'].mean():.1f}%"])
    LOG.table(rows, ["연도", "보고서", "애널연결률", "종목코드율", "목표주가율"],
              ["c", "r", "r", "r", "r"])
    src = r.groupby("source").agg(n=("report_uid", "size"), analyst=("has_analyst", "mean"),
                                  code=("has_code", "mean"), tp=("has_tp", "mean")).reset_index()
    LOG.table([[s["source"], f"{int(s['n']):,}", f"{100*s['analyst']:.1f}%",
                f"{100*s['code']:.1f}%", f"{100*s['tp']:.1f}%"] for _, s in src.iterrows()],
              ["소스 조합", "건수", "애널연결률", "코드율", "TP율"], ["l", "r", "r", "r", "r"],
              title="다중소스 원장 연결 — 'hankyung+naver' 는 두 소스가 같은 보고서로 병합된 건")


# ── 컨센서스 스냅샷 (F4/F5 프록시 입력, PIT) ────────────────────────────────────────────────
class ConsensusStore:
    """리포트 연결표에서 신호일 기준 종목별 목표주가 컨센서스를 뽑는다 (전부 PIT).
    · normal = 최근 90일 전체 애널리스트 목표주가 중앙값
    · smart  = 과거 12M 예측오차(|실현수익-내재수익|)가 작은 상위 1/3 애널리스트의 중앙값
      — FnGuide Smart Consensus 의 공개 프록시일 뿐이며 'exact' 라 부르지 않는다(계약).
    · 예측오차는 발간 후 12개월이 지난 리포트만 사용(그 전에는 결과 자체를 알 수 없음)."""

    def __init__(self, L: pd.DataFrame, px_close: pd.DataFrame):
        self.ok = L is not None and len(L) > 0 and px_close is not None and len(px_close) > 0
        if not self.ok:
            self.L = pd.DataFrame()
            return
        x = L.dropna(subset=["stock_code", "pub_date", "target_price"]).copy()
        x["pub_date"] = as_ts_series(x["pub_date"])
        x["stock_code"] = x["stock_code"].astype(str)
        x = x.dropna(subset=["pub_date"])
        if not len(x):
            self.ok = False
            self.L = pd.DataFrame()
            return
        # ★ merge_asof 는 by-키 dtype 불일치(object vs category)에 MergeError 를 던진다 —
        #   downcast 가 px.code 를 category 로 바꾸므로 여기서 반드시 str 로 통일한다.
        #   (이걸 놓치면 FULL 모드가 F4 전멸 → 'L3.BT 빈 결과' 오진으로 죽는다 — 감사 치명)
        px = px_close[["code", "date", "close"]].copy()
        px["code"] = px["code"].astype(str)
        px = px.sort_values(["code", "date"])
        # 발간일 종가 / 12개월 후 종가를 merge_asof 로 일괄 결합 (루프 금지 — 속도)
        x = x.sort_values("pub_date")
        p0 = pd.merge_asof(x, px.rename(columns={"date": "pub_date", "close": "px0"})
                           [["code", "pub_date", "px0"]].sort_values("pub_date"),
                           left_on="pub_date", right_on="pub_date",
                           left_by="stock_code", right_by="code",
                           direction="backward", tolerance=pd.Timedelta(days=14))
        x["px0"] = p0["px0"].to_numpy()
        x["chk_date"] = x["pub_date"] + pd.Timedelta(days=365)
        x = x.sort_values("chk_date")
        p1 = pd.merge_asof(x, px.rename(columns={"date": "chk_date", "close": "px1"})
                           [["code", "chk_date", "px1"]].sort_values("chk_date"),
                           left_on="chk_date", right_on="chk_date",
                           left_by="stock_code", right_by="code",
                           direction="backward", tolerance=pd.Timedelta(days=21))
        x["px1"] = p1["px1"].to_numpy()
        x["implied"] = x["target_price"] / x["px0"] - 1.0
        x["realized"] = x["px1"] / x["px0"] - 1.0
        x["abs_err"] = (x["realized"] - x["implied"]).abs()
        # 예측오차의 '알게 되는 날' = 발간+12M+가격확인여유 — 이 날 이후에만 스마트 판정에 사용
        x["err_known"] = x["chk_date"] + pd.Timedelta(days=5)
        self.L = x.sort_values("pub_date").reset_index(drop=True)

    def snapshot(self, asof: pd.Timestamp, window_days: int = 90) -> pd.DataFrame:
        """(code, tp_med_all, tp_med_smart, n_analyst, tp_med_prev1m) — 전부 asof 이전 정보만."""
        cols = ["code", "tp_med_all", "tp_med_smart", "n_analyst", "tp_med_prev1m"]
        if not self.ok:
            return pd.DataFrame(columns=cols)
        L = self.L
        w = L[(L["pub_date"] <= asof) & (L["pub_date"] > asof - pd.Timedelta(days=window_days))]
        if not len(w):
            return pd.DataFrame(columns=cols)
        # 같은 애널리스트가 같은 종목에 여러 번 내면 최신 것만
        w = w.sort_values("pub_date").drop_duplicates(["stock_code", "analyst_id"], keep="last")
        # 스마트 집합: asof 까지 오차가 '알려진' 리포트 기준 애널리스트별 평균 |오차| 하위 1/3
        hist = L[(L["err_known"] <= asof) & L["abs_err"].notna()]
        smart_ids: set = set()
        if len(hist) >= 30:
            err = hist.groupby("analyst_id")["abs_err"].agg(["mean", "count"])
            err = err[err["count"] >= 3]
            if len(err) >= 9:
                thr = err["mean"].quantile(1 / 3)
                smart_ids = set(err[err["mean"] <= thr].index)
        g = w.groupby("stock_code")
        out = pd.DataFrame({"tp_med_all": g["target_price"].median(),
                            "n_analyst": g["analyst_id"].nunique()})
        if smart_ids:
            ws = w[w["analyst_id"].isin(smart_ids)]
            if len(ws):
                out["tp_med_smart"] = ws.groupby("stock_code")["target_price"].median()
        if "tp_med_smart" not in out.columns:
            out["tp_med_smart"] = np.nan
        # 1개월 전 시점의 동일 윈도우 중앙값 (F5 리비전용)
        prev_asof = asof - pd.Timedelta(days=30)
        wp = L[(L["pub_date"] <= prev_asof) &
               (L["pub_date"] > prev_asof - pd.Timedelta(days=window_days))]
        if len(wp):
            wp = wp.sort_values("pub_date").drop_duplicates(["stock_code", "analyst_id"],
                                                            keep="last")
            out["tp_med_prev1m"] = wp.groupby("stock_code")["target_price"].median()
        else:
            out["tp_med_prev1m"] = np.nan
        out = out.reset_index().rename(columns={"stock_code": "code"})
        return out.reindex(columns=cols)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-G  EXACT_VENDOR_MODE 판정 — FnGuide/신한 벤더 데이터 실재 검사                          ║
# ║  계약: 벤더 composite(A) 또는 표준화 점수+유니버스 마스크(B)가 있어야 활성화.               ║
# ║  없으면 실행한 척하지 않고 STATUS=EXACT_COMPOSITE_NOT_PUBLICLY_IDENTIFIED 를 출력한다.      ║
# ║  다른 전략이 만든 프록시 테이블(예: smart_consensus_daily)을 벤더 데이터로 오인하지 않도록  ║
# ║  '벤더 마커'를 요구한다 — 마커 없는 유사 파일은 proxy 로 분류하고 그 사실을 로그에 남긴다.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

VENDOR_REQUIRED_COLS = {"surprise_probability", "eps_growth_fq1", "eps_growth_fy1",
                        "smart_consensus", "ordinary_consensus", "eps12mf", "known_at"}


def detect_exact_vendor_mode() -> dict:
    """반환: {"active": bool, "status": str, "detail": [...], "coverage_rows": [...]}"""
    detail, cov_rows = [], []
    candidates: List[Tuple[str, str]] = []           # (설명, 경로)
    for scope in ("private", "shared"):
        for nm in ("fnguide_factor_history", "shinhan_composite_history",
                   "fnguide_component_scores"):
            p = os.path.join(VAULT.table_dir(scope), f"{nm}.parquet")
            if os.path.exists(p):
                candidates.append((f"table:{scope}:{nm}", p))
    for p in VAULT.adopted_paths(["fnguide_factor_history", "shinhan_composite",
                                  "fnguide_component"], exts=(".parquet", ".csv")):
        candidates.append((f"adopt:{os.path.basename(p)}", p))

    active = False
    for label, p in candidates:
        try:
            d = read_parquet_safe(p) if p.endswith(".parquet") else pd.read_csv(p)
        except Exception:
            d = None
        if d is None or not len(d):
            detail.append(f"{label}: 읽기 실패/빈 파일")
            continue
        cols = {str(c).lower() for c in d.columns}
        missing = VENDOR_REQUIRED_COLS - cols
        vendor_marked = ("vendor" in cols and
                         d[[c for c in d.columns if str(c).lower() == "vendor"][0]]
                         .astype(str).str.lower().str.contains("fnguide|shinhan").any())
        if missing:
            detail.append(f"{label}: 필수 컬럼 결측 {sorted(missing)[:4]}… → 벤더 데이터 아님")
            continue
        if not vendor_marked:
            # 완전 스키마인데 마커만 없는 파일 — '미확인 후보'로 보고(자동 활성화는 안 함:
            # 다른 전략이 만든 프록시일 가능성이 높다. 진짜 벤더 파일이면 vendor 컬럼에
            # 'fnguide' 를 채워 재실행하라고 안내).
            detail.append(f"{label}: 계약 스키마와 일치하나 vendor 마커 없음 → 미확인 후보. "
                          f"진짜 FnGuide 원본이면 vendor='fnguide' 컬럼을 추가해 재실행하세요.")
            cov_rows.append({"item": label, "quarters": 0, "tickers": 0,
                             "verdict": "UNVERIFIED_CANDIDATE"})
            continue
        kd = as_ts_series(d[[c for c in d.columns if str(c).lower() == "known_at"][0]])
        n_q = kd.dt.to_period("Q").nunique()
        n_tk = d[[c for c in d.columns if str(c).lower() in ("ticker", "code")][0]].nunique() \
            if cols & {"ticker", "code"} else 0
        if n_q < 36 or n_tk < 100:
            detail.append(f"{label}: 커버리지 부족(분기 {n_q}/40, 종목 {n_tk}) → FAIL_COVERAGE")
            cov_rows.append({"item": label, "quarters": int(n_q), "tickers": int(n_tk),
                             "verdict": "FAIL_COVERAGE"})
            continue
        active = True
        detail.append(f"{label}: 벤더 데이터 검증 통과 (분기 {n_q}, 종목 {n_tk:,})")
        cov_rows.append({"item": label, "quarters": int(n_q), "tickers": int(n_tk),
                         "verdict": "OK"})

    # ★ 벤더 '계산 파이프라인'은 이 코드에 없다. 데이터가 실재해도 EXACT 를 실행한 척하지
    #   않도록(계약 §EXACT 역방향 위반 방지) 항상 재구성 모드로 계산하고, 그 사실을 STATUS 로
    #   정직하게 남긴다.
    if active:
        status = "EXACT_DATA_PRESENT_PIPELINE_NOT_IMPLEMENTED"
        detail.append("벤더 데이터는 검증 통과했으나 벤더 composite 재현 파이프라인은 이 코드에 "
                      "구현되어 있지 않음 — 계산은 RECONSTRUCTED 로만 수행하고 라벨을 혼용하지 "
                      "않는다.")
    else:
        status = "EXACT_COMPOSITE_NOT_PUBLICLY_IDENTIFIED"
    if not candidates:
        detail.append("벤더 후보 파일 자체가 캐시에 없음 (fnguide_factor_history.parquet 등)")
    LOG.banner("EXACT_VENDOR_MODE 판정", f"STATUS = {status}")
    for ln in detail:
        LOG.info("  · " + ln)
    LOG.info("→ 계산은 RECONSTRUCTED_PUBLIC_MODE 로만 수행합니다. 재구성 규칙은 '공개정보 "
             "재구성'이며 신한 원문에 명시된 공식이 아닙니다.")
    return {"active": active, "status": status, "detail": detail, "coverage_rows": cov_rows}


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  7팩터 스냅샷 (분기 신호일에서만 계산 — 일별 전종목 패널 생성 금지: 계약 §속도)          ║
# ║                                                                                          ║
# ║  원문 팩터 ↔ 재구성 입력 (전부 higher=better, 입력등급을 factor_grade 로 기록):             ║
# ║   F1 Surprise Probability  ← [proxy] 최근 8개 기지(旣知) 분기의 YoY 어닝비트 비율           ║
# ║      (원문은 FnGuide item — 직접 재계산분은 SURPRISE_PROB_PROXY 로만 사용, 계약)             ║
# ║   F2 EPS Growth FQ1 (YoY)  ← [proxy] 최신 기지 분기 순이익 YoY 성장률                       ║
# ║   F3 EPS Growth FY1 (YoY)  ← [proxy] 기지 TTM 순이익 YoY 성장률                             ║
# ║   F4 SMART_GAP             ← [proxy] 100*(스마트TP중앙값-전체TP중앙값)/전체TP중앙값          ║
# ║      (분모 abs() 금지·0이면 null — 계약 명시)                                               ║
# ║   F5 EPS_CHANGE_12MF_1M    ← [proxy] TP컨센서스 1개월 변화율, 없으면 TTM순이익의            ║
# ║      knowledge 기준 1개월 리비전                                                            ║
# ║   F6 INST_NETBUY_STRENGTH_20D  ← [public_exact] 100*Σ(기관순매수,20거래일)/시총             ║
# ║   F7 FOREIGN_NETBUY_STRENGTH_20D ← [public_exact] 100*Σ(외국인순매수,20거래일)/시총          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

FACTOR_NAMES = ["F1_SURPRISE_PROB_PROXY", "F2_EPSG_FQ1_PROXY", "F3_EPSG_FY1_PROXY",
                "F4_SMART_GAP_PROXY", "F5_EPS12MF_CHG_1M_PROXY",
                "F6_INST_NETBUY_20D", "F7_FORG_NETBUY_20D"]
FACTOR_GRADE = {"F1_SURPRISE_PROB_PROXY": "public_proxy", "F2_EPSG_FQ1_PROXY": "public_proxy",
                "F3_EPSG_FY1_PROXY": "public_proxy", "F4_SMART_GAP_PROXY": "public_proxy",
                "F5_EPS12MF_CHG_1M_PROXY": "public_proxy",
                "F6_INST_NETBUY_20D": "public_exact", "F7_FORG_NETBUY_20D": "public_exact"}


def _yoy_growth(cur: pd.Series, prev: pd.Series) -> pd.Series:
    """YoY 성장률(%) — 분모 0 은 null. 음수 분모는 abs 로 방향 보존(재구성 사전고정 규칙.
    F4 와 달리 원문이 분모 처리를 공개하지 않으므로 표준 관행을 택하고 문서화한다)."""
    prev = pd.to_numeric(prev, errors="coerce")
    cur = pd.to_numeric(cur, errors="coerce")
    out = 100.0 * (cur - prev) / prev.abs()
    return out.where(prev.abs() > 1e-9).replace([np.inf, -np.inf], np.nan)


def _beat_ratio(s: pd.Series) -> float:
    """최근 8개 유효 YoY 비교의 어닝비트 비율. 유효 4개 미만이면 null(근거 없는 값 금지)."""
    v = s.dropna().tail(8)
    return float(v.mean()) if len(v) >= 4 else np.nan


def _earnings_features(earn_cut: pd.DataFrame) -> pd.DataFrame:
    """asof 로 절단된 분기실적에서 F1/F2/F3 원료를 종목별로 계산 (벡터화).
    ★ groupby 객체는 컬럼 추가 '이전' 프레임에 묶이므로, 파생컬럼을 전부 만든 뒤
      새로 groupby 한다 (변이 후 재사용은 pandas 버전에 따라 조용히 어긋난다)."""
    if earn_cut is None or earn_cut.empty:
        return pd.DataFrame(columns=["code", "f1", "f2", "f3"])
    d = earn_cut.sort_values(["code", "period_end"]).copy()
    g0 = d.groupby("code", observed=True)
    d["ni_q_yoy_prev"] = g0["ni_q"].shift(4)      # '기지 분기' 시퀀스 기준 4칸 전 —
    d["pe_prev4"] = g0["period_end"].shift(4)     # 실제 1년 차이인지는 아래에서 검증
    d["ni_ttm_prev4"] = g0["ni_ttm"].shift(4)
    ok_gap = (d["period_end"] - d["pe_prev4"]).dt.days.between(330, 400)
    d["beat"] = np.where(ok_gap & d["ni_q"].notna() & d["ni_q_yoy_prev"].notna(),
                         (d["ni_q"] > d["ni_q_yoy_prev"]).astype(float), np.nan)
    g = d.groupby("code", observed=True)
    f1 = g["beat"].apply(_beat_ratio)
    last = g.tail(1).set_index("code")
    okl = (last["period_end"] - last["pe_prev4"]).dt.days.between(330, 400)
    f2 = _yoy_growth(last["ni_q"], last["ni_q_yoy_prev"].where(okl))
    f3 = _yoy_growth(last["ni_ttm"], last["ni_ttm_prev4"].where(okl))
    out = pd.DataFrame({"f1": f1, "f2": f2, "f3": f3})
    out.index.name = "code"
    out = out.reset_index()
    out["code"] = out["code"].astype(str)     # category 유입 방지 (병합 키 통일)
    return out


def _f5_dart_revision(earn: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """F5 폴백: knowledge 기준 '지금 아는 TTM' vs '1개월 전에 알던 TTM' 의 변화율."""
    if earn is None or earn.empty:
        return pd.DataFrame(columns=["code", "f5_dart"])
    now = earnings_asof(earn, asof, n_last=1)[["code", "ni_ttm"]].rename(
        columns={"ni_ttm": "ttm_now"})
    ago = earnings_asof(earn, asof - pd.Timedelta(days=30), n_last=1)[["code", "ni_ttm"]].rename(
        columns={"ni_ttm": "ttm_ago"})
    m = now.merge(ago, on="code", how="inner")
    m["f5_dart"] = _yoy_growth(m["ttm_now"], m["ttm_ago"])
    return m[["code", "f5_dart"]]


def build_factor_snapshot(sig: pd.Timestamp, members: List[str], mcap: pd.DataFrame,
                          earn: pd.DataFrame, cons: "ConsensusStore",
                          flows: pd.DataFrame) -> pd.DataFrame:
    """한 신호일의 (code × 7팩터) 스냅샷. 모든 입력은 knowledge<=sig 로 절단된 것만 쓴다."""
    base = pd.DataFrame({"code": sorted(set(members))})
    base["signal_date"] = sig

    ef = _earnings_features(earnings_asof(earn, sig, n_last=14))
    base = base.merge(ef, on="code", how="left")

    snap = cons.snapshot(sig) if cons is not None else pd.DataFrame(
        columns=["code", "tp_med_all", "tp_med_smart", "n_analyst", "tp_med_prev1m"])
    base = base.merge(snap, on="code", how="left")
    # F4: 분모를 abs() 로 바꾸지 않는다. 0이면 null (계약 명시)
    den = pd.to_numeric(base["tp_med_all"], errors="coerce")
    num = pd.to_numeric(base["tp_med_smart"], errors="coerce") - den
    base["f4"] = (100.0 * num / den.where(den.abs() > 1e-9)).replace([np.inf, -np.inf], np.nan)
    # F5: TP 1개월 리비전 → 없으면 DART TTM 리비전
    prev = pd.to_numeric(base["tp_med_prev1m"], errors="coerce")
    base["f5"] = (100.0 * (den - prev) / prev.where(prev.abs() > 1e-9)
                  ).replace([np.inf, -np.inf], np.nan)
    fd = _f5_dart_revision(earn, sig)
    base = base.merge(fd, on="code", how="left")
    base["f5"] = base["f5"].where(base["f5"].notna(), base["f5_dart"])
    base["f5_src"] = np.where(pd.to_numeric(base["tp_med_prev1m"], errors="coerce").notna()
                              & pd.to_numeric(base["tp_med_all"], errors="coerce").notna(),
                              "tp_consensus", np.where(base["f5_dart"].notna(), "dart_ttm", ""))

    # F6/F7: 100 * Σ순매수(20거래일) / 시총(신호일)
    # ★ 병합 키는 반드시 문자열로 통일 — downcast 가 code 를 category 로 바꾼 테이블과
    #   str 리스트 유래 테이블을 섞으면 pandas 버전에 따라 조용한 미스매치가 난다.
    mc = mcap[["code", "marcap"]].copy() if mcap is not None and len(mcap) else \
        pd.DataFrame(columns=["code", "marcap"])
    if len(mc):
        mc["code"] = mc["code"].astype(str)
        mc = mc.drop_duplicates("code")
    base = base.merge(mc, on="code", how="left")
    fl = flows[flows["signal_date"] == sig][["code", "inst_net", "forg_net"]].copy() \
        if flows is not None and len(flows) else pd.DataFrame(columns=["code", "inst_net",
                                                                       "forg_net"])
    if len(fl):
        fl["code"] = fl["code"].astype(str)
        fl = fl.drop_duplicates("code")
    base = base.merge(fl, on="code", how="left")
    mden = pd.to_numeric(base["marcap"], errors="coerce")
    base["f6"] = (100.0 * pd.to_numeric(base["inst_net"], errors="coerce") /
                  mden.where(mden > 0)).replace([np.inf, -np.inf], np.nan)
    base["f7"] = (100.0 * pd.to_numeric(base["forg_net"], errors="coerce") /
                  mden.where(mden > 0)).replace([np.inf, -np.inf], np.nan)

    out = base[["signal_date", "code", "f1", "f2", "f3", "f4", "f5", "f6", "f7",
                "f5_src", "marcap", "n_analyst"]].copy()
    out.columns = ["signal_date", "code"] + FACTOR_NAMES + ["f5_src", "marcap", "n_analyst"]
    return out


# ── 표준화 · 합성 (계약 사전고정 baseline + robustness 변형) ────────────────────────────────
FCOLS = FACTOR_NAMES


def compose_scores(snap: pd.DataFrame, method: str = "baseline") -> pd.DataFrame:
    """한 신호일 스냅샷 → z/합성점수.
    baseline      : 7개 전부 유효한 종목만 대상 · z=(x-mean)/std(모집단 ddof=0) ·
                    winsorization 없음 · COMPOSITE=Σz/7  (계약 사전고정 — Primary)
    [robustness 전용 — 계약 §robustness에서만]
    rank_mean     : 백분위 랭크 [0,1] 평균
    rank_sum      : 랭크 합
    winsor_z      : 1/99 퍼센타일 윈저라이즈 후 z
    missing1_mean : 결측 ≤1 종목까지 대상, 가용 z 평균
    """
    d = snap.copy()
    X = d[FCOLS].apply(pd.to_numeric, errors="coerce")
    n_valid = X.notna().sum(axis=1)
    if method == "missing1_mean":
        elig = n_valid >= len(FCOLS) - 1
    else:
        elig = n_valid == len(FCOLS)          # 계약: 7개 모두 valid 만 baseline 대상
    d["eligible"] = elig
    E = X[elig]
    if not len(E):
        d["COMPOSITE"] = np.nan
        for c in FCOLS:
            d["z_" + c] = np.nan
        return d
    if method in ("baseline", "missing1_mean"):
        mu = E.mean()
        sd = E.std(ddof=0)                    # 모집단 표준편차 (계약 명시)
        Z = (X - mu) / sd.where(sd > 0)
        # σ=0(전원 동일값) 팩터는 z 정의역 밖 — 전원이 평균에 있으므로 0 이 연속 극한이다.
        # NaN 으로 두면 그 분기 '전체'가 부적격으로 죽는다(관측이 있는데 버리는 쪽이 더 왜곡).
        for c0 in FCOLS:
            if c0 in sd.index and sd[c0] == 0:
                Z.loc[X[c0].notna(), c0] = 0.0
        comp = Z[elig].mean(axis=1, skipna=(method == "missing1_mean"))
    elif method == "winsor_z":
        lo = E.quantile(0.01)
        hi = E.quantile(0.99)
        Ew = E.clip(lower=lo, upper=hi, axis=1)
        mu = Ew.mean()
        sd = Ew.std(ddof=0)
        Z = (X.clip(lower=lo, upper=hi, axis=1) - mu) / sd.where(sd > 0)
        for c0 in FCOLS:
            if c0 in sd.index and sd[c0] == 0:
                Z.loc[X[c0].notna(), c0] = 0.0
        comp = Z[elig].mean(axis=1, skipna=False)
    elif method == "rank_mean":
        Z = E.rank(pct=True).reindex(X.index)
        comp = Z[elig].mean(axis=1, skipna=False)
    elif method == "rank_sum":
        Z = E.rank().reindex(X.index)
        comp = Z[elig].sum(axis=1, min_count=len(FCOLS))
    else:
        raise ValueError(f"알 수 없는 표준화 방법: {method}")
    for c in FCOLS:
        d["z_" + c] = Z[c] if c in Z.columns else np.nan
    d["COMPOSITE"] = np.nan
    d.loc[elig, "COMPOSITE"] = comp[elig]
    return d


def select_top(scored: pd.DataFrame, top_n: int = TOP_N) -> pd.DataFrame:
    """합성점수 상위 top_n 동일가중. 동점은 (COMPOSITE, code) 로 결정적으로 깬다."""
    e = scored[scored["eligible"] & scored["COMPOSITE"].notna()].copy()
    if len(e) < MIN_ELIGIBLE:
        return e.iloc[0:0]
    pick = e.sort_values(["COMPOSITE", "code"], ascending=[False, True],
                         kind="mergesort").head(top_n).copy()
    pick["weight"] = 1.0 / len(pick)
    return pick


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 — 분기 리밸런스 · 신호=분기말 종가 후 · 체결=익거래일 시가               ║
# ║  · 당일 종가 체결은 미래누수 → 기본은 next_open, paper_close 는 별도 산출(계약)             ║
# ║  · 상장폐지: 보유 중 가격이 끊기면 마지막 체결가능가(정리매매 최종가 근사)로 청산,          ║
# ║    그것도 없으면 -100%. 누락 처리 금지(누락 = 생존자편향).                                  ║
# ║  · 일별 곡선: 보유 종목의 일별 종가로 드리프트 가중 — 연변동성/MDD/롤링 지표의 근거.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

TAX_SCHEDULE = [
    ("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
]


def sell_tax(dt) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in TAX_SCHEDULE:
        if t >= as_ts(d):
            rate = r
    return rate


def slippage_bps(trade_krw: float, adv_krw: float) -> float:
    """제곱근 시장충격(소수) — 참여율이 높을수록 급격히 비싸진다(소형주 비교전략에서 중요)."""
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    part = min(1.0, abs(trade_krw) / adv_krw)
    return float(SLIPPAGE_K * math.sqrt(part))


class PriceBook:
    """보유 후보 종목만의 (open/close/adv20) 피벗 — 백테스트 전 구간을 벡터화 조회."""

    def __init__(self, px: pd.DataFrame, codes: set):
        sub = px[px["code"].isin(codes)][["code", "date", "open", "close", "amount"]].copy()
        sub = sub.sort_values(["code", "date"])
        sub["adv20"] = (sub.groupby("code", observed=True)["amount"]
                          .transform(lambda s: s.rolling(20, min_periods=5).mean()))
        self.close = sub.pivot_table(index="date", columns="code", values="close",
                                     aggfunc="last").sort_index().astype("float32")
        self.open_ = sub.pivot_table(index="date", columns="code", values="open",
                                     aggfunc="last").sort_index().astype("float32")
        self.adv20 = sub.pivot_table(index="date", columns="code", values="adv20",
                                     aggfunc="last").sort_index().astype("float32")
        self.dates = self.close.index

    def px_at(self, code: str, date: pd.Timestamp, kind: str = "open",
              strict_day: bool = False) -> float:
        """date 당일 시가(결측 시 당일 종가) 조회.
        strict_day=True: 당일 실체결 프린트가 없으면 NaN — '정지 전 과거가로 매수' 방지.
        strict_day=False: 직전 종가 폴백 허용(매도 평가용 — 정지종목은 별도 헤어컷)."""
        v = np.nan
        if code in self.open_.columns and date in self.open_.index:
            tab = self.open_ if kind == "open" else self.close
            v = tab.at[date, code]
            if (v is None or not np.isfinite(v)) and kind == "open":
                v = self.close.at[date, code]          # 당일 시가 결측 → 당일 종가
        if (v is None or not np.isfinite(v)) and not strict_day \
                and code in self.close.columns:
            s = self.close[code].loc[:date].dropna()
            v = float(s.iloc[-1]) if len(s) else np.nan
        return float(v) if v is not None and np.isfinite(v) else np.nan

    def last_trade_pos_gap(self, code: str, upto: pd.Timestamp) -> int:
        """upto 까지 마지막 실거래일로부터의 거래일 간격 (정지/폐지 감지용). 없으면 큰 값."""
        if code not in self.close.columns:
            return 10 ** 6
        s = self.close[code].loc[:upto].dropna()
        if not len(s):
            return 10 ** 6
        li = self.dates.searchsorted(s.index[-1])
        ui = self.dates.searchsorted(upto, side="right") - 1
        return max(0, int(ui - li))

    def last_close_between(self, code: str, d0: pd.Timestamp, d1: pd.Timestamp) -> float:
        if code not in self.close.columns:
            return np.nan
        s = self.close[code].loc[d0:d1].dropna()
        return float(s.iloc[-1]) if len(s) else np.nan


def run_backtest(portfolios: Dict[pd.Timestamp, pd.DataFrame], sch: pd.DataFrame,
                 px: pd.DataFrame, delist: Dict[str, pd.Timestamp],
                 exec_mode: str = "next_open", cost_mult: float = 1.0,
                 label: str = "strategy") -> dict:
    """portfolios: {signal_date: DataFrame(code, weight)}.
    반환: daily(일별 수익), quarterly(분기 수익·회전율·비용), holdings(보유 원장)."""
    all_codes = set()
    for p in portfolios.values():
        if p is not None and len(p):
            all_codes |= set(p["code"])
    if not all_codes:
        empty_d = pd.DataFrame(columns=["date", "ret", "equity"])
        empty_q = pd.DataFrame(columns=["signal_date", "exec_date", "ret", "turnover",
                                        "cost", "n"])
        return {"daily": empty_d, "quarterly": empty_q,
                "holdings": pd.DataFrame(), "label": label}
    book = PriceBook(px, all_codes)

    daily_rows: List[Tuple[pd.Timestamp, float]] = []
    q_rows, hold_rows = [], []
    prev_val: Dict[str, float] = {}          # 직전 리밸런스 직후부터 드리프트된 보유가치(비중)

    n_sch = len(sch)
    for i, r in sch.iterrows():
        sig, ex, nx = r["signal_date"], r["exec_date"], r["next_exec"]
        is_last = (i == n_sch - 1)
        port = portfolios.get(sig)
        tgt = {} if port is None or not len(port) else dict(zip(port["code"], port["weight"]))

        # ── 체결가: next_open(기본) / paper_close(신호일 종가 — 계약 별도 산출) ─────────
        #    strict_day=True — 체결일 당일 실체결이 없는 종목(정지)은 편입하지 않는다.
        entry_px: Dict[str, float] = {}
        for c in tgt:
            p0 = book.px_at(c, ex, "open", strict_day=True) if exec_mode == "next_open" \
                else book.px_at(c, sig, "close", strict_day=True)
            entry_px[c] = p0
        n_drop = sum(1 for c in tgt if not np.isfinite(entry_px.get(c, np.nan)))
        if n_drop:
            LOG.debug(f"{pd.Timestamp(sig):%Y-%m-%d} 체결일 무거래로 제외 {n_drop}종목 "
                      f"(정지 전 과거가 매수 방지)")
        tgt = {c: w for c, w in tgt.items() if np.isfinite(entry_px.get(c, np.nan))}
        if tgt:                                # 체결 불가 종목 제외 후 동일가중 재정규화
            s = sum(tgt.values())
            tgt = {c: w / s for c, w in tgt.items()}

        # ── 거래비용 (수수료+세금+슬리피지) — 직전 드리프트 비중 대비 변화분에 부과 ─────
        turn = sum(abs(tgt.get(c, 0.0) - prev_val.get(c, 0.0))
                   for c in set(tgt) | set(prev_val)) * 0.5
        cost = 0.0
        if cost_mult > 0:
            for c in set(tgt) | set(prev_val):
                dw = tgt.get(c, 0.0) - prev_val.get(c, 0.0)
                if abs(dw) < 1e-9:
                    continue
                adv = np.nan
                if c in book.adv20.columns:
                    s_ = book.adv20[c].loc[:ex].dropna()
                    adv = float(s_.iloc[-1]) if len(s_) else np.nan
                sl = slippage_bps(abs(dw) * ACCOUNT_KRW, adv)
                tx = sell_tax(ex) if dw < 0 else 0.0
                cost += abs(dw) * (COMMISSION_BPS / 1e4 + sl + tx)
        cost *= cost_mult

        # ── 보유구간 일별 가치 경로 ─────────────────────────────────────────────────────
        #   ★ 반개구간 [ex, nx) 로 돌고, nx(다음 리밸런스 체결일)에는 '매도가(시가)'로
        #     마지막 1회 평가한다. nx 를 종가까지 들고 있으면 다음 포트폴리오의 같은 날
        #     장중수익과 이중계상된다(감사 CRITICAL — 40회 리밸런스 누적 왜곡).
        #     마지막 스케줄 행만 매도 없이 nx 종가 평가로 마감한다.
        period_dates = book.dates[(book.dates >= ex) & (book.dates < nx)]
        vals = dict(tgt)                       # 비중 = 가치 (구간 시작 시 1로 정규화된 포트)
        period_ret = 0.0
        if len(period_dates) and vals:
            sub_close = book.close.reindex(index=period_dates,
                                           columns=list(vals)).astype(float)
            first = period_dates[0]
            port_val_prev = 1.0
            cash = 1.0 - sum(vals.values())
            v: Dict[str, float] = {}
            last_px: Dict[str, float] = {}
            dead: set = set()                  # 청산(현금화) 완료 종목 — 가치 고정
            for c, w in vals.items():
                pc = float(sub_close.at[first, c])
                if not np.isfinite(pc):
                    pc = entry_px[c]
                v[c] = w * (pc / entry_px[c]) if np.isfinite(entry_px[c]) and entry_px[c] > 0 \
                    else w
                last_px[c] = pc if np.isfinite(pc) else entry_px[c]
            day_val = sum(v.values()) + cash
            daily_rows.append((first, day_val / port_val_prev - 1.0))
            port_val_prev = day_val
            for d in period_dates[1:]:
                for c in list(v):
                    if c in dead:
                        continue
                    pc = float(sub_close.at[d, c])
                    lp = last_px.get(c)
                    if np.isfinite(pc) and lp is not None and np.isfinite(lp) and lp > 0:
                        v[c] *= pc / lp
                        last_px[c] = pc
                    else:
                        # 가격 공백: 폐지일이 지났으면 마지막 관측가로 청산(정리매매 최종가
                        # 근사 — v[c]는 이미 그 가격 기준). 관측가가 하나도 없으면 -100%.
                        # 폐지가 아니면 일시 거래정지로 보고 직전가를 유지한다.
                        dl = delist.get(c)
                        if dl is not None and pd.notna(dl) and dl <= d:
                            if not np.isfinite(book.last_close_between(c, ex, d)):
                                v[c] = 0.0
                            dead.add(c)
                day_val = sum(v.values()) + cash
                daily_rows.append((d, day_val / port_val_prev - 1.0))
                port_val_prev = day_val
            # ── nx 매도 평가: 직전종가→매도가(시가). 마지막 행은 종가 마감(매도 없음) ──
            sale_kind = "close" if is_last else "open"
            stale_cut = []
            for c in list(v):
                if c in dead:
                    continue
                sp = book.px_at(c, nx, sale_kind, strict_day=False)
                lp = last_px.get(c)
                if np.isfinite(sp) and lp is not None and np.isfinite(lp) and lp > 0:
                    v[c] *= sp / lp
                # 장기 무거래(정지) 종목: 정지 전 가격에 전량 매도했다고 가정하면 낙관 편향.
                # 40거래일 이상 실거래가 없으면 보수적으로 50% 헤어컷 후 현금화 처리.
                if book.last_trade_pos_gap(c, pd.Timestamp(nx)) > 40:
                    v[c] *= 0.5
                    stale_cut.append(c)
            if stale_cut:
                LOG.warn(f"{pd.Timestamp(sig):%Y-%m-%d} 분기 매도 시점에 40거래일+ 무거래 "
                         f"{len(stale_cut)}종목({','.join(stale_cut[:4])}…)에 50% 헤어컷 적용 "
                         f"(정지 전 가격 전량매도 가정의 낙관 편향 방지)")
            day_val = sum(v.values()) + cash
            daily_rows.append((pd.Timestamp(nx), day_val / port_val_prev - 1.0))
            port_val_prev = day_val
            period_ret = port_val_prev - 1.0
            tot = max(port_val_prev, 1e-12)
            prev_val = {c: vv / tot for c, vv in v.items() if vv > 0}
        else:
            prev_val = {}
            for d in period_dates:
                daily_rows.append((d, 0.0))

        # 체결일 수익에서 비용 차감 (일별 곡선·분기수익 동시 반영)
        n_rows_this = len(period_dates) + (1 if (len(period_dates) and vals) else 0)
        if cost > 0 and n_rows_this:
            di = len(daily_rows) - n_rows_this
            d0, r0 = daily_rows[di]
            daily_rows[di] = (d0, r0 - cost)
            period_ret -= cost
        q_rows.append({"signal_date": sig, "exec_date": ex, "next_exec": nx,
                       "ret": period_ret, "turnover": turn, "cost": cost, "n": len(tgt)})
        for c, w in tgt.items():
            hold_rows.append({"signal_date": sig, "code": c, "weight": w,
                              "entry_px": entry_px.get(c, np.nan)})

    D = pd.DataFrame(daily_rows, columns=["date", "ret"])
    if len(D):
        # 같은 날짜에 구포트(매도 오버나이트)와 신포트(당일 장중) 두 구간이 겹칠 수 있다 —
        # 같은 자본의 순차 구간이므로 합이 아니라 '복리'로 결합한다.
        D = (D.groupby("date")["ret"].apply(lambda s: float(np.prod(1.0 + s.values) - 1.0))
              .reset_index().sort_values("date"))
        D["equity"] = (1.0 + D["ret"]).cumprod()
    Q = pd.DataFrame(q_rows)
    if len(Q):
        Q["equity"] = (1.0 + Q["ret"]).cumprod()
    H = pd.DataFrame(hold_rows)
    return {"daily": D, "quarterly": Q, "holdings": H, "label": label,
            "exec_mode": exec_mode, "cost_mult": cost_mult}


def fetch_benchmark_k200(start: str, end: str) -> pd.DataFrame:
    """KOSPI200 지수 일별 종가. 체인: 공용캐시 → pykrx → FDR(KS200) → yfinance(^KS200)
    → KOSPI(KS11, 근사·경고). 반환: date, close, src"""
    cached = VAULT.get_table("benchmark_k200_daily", scope="shared")
    if cached is not None and len(cached):
        cached["date"] = as_ts_series(cached["date"])
        if cached["date"].max() >= as_ts(end) - pd.Timedelta(days=10):
            LOG.info(f"공용 캐시에서 KOSPI200 지수 {len(cached):,}행 재사용")
            return cached
    d = None
    src = ""
    if pykrx_stock is not None and RUN_MODE != "CACHED":
        KRXG.warmup()
        r = KRXG.call(pykrx_stock.get_index_ohlcv_by_date,
                      as_ts(start).strftime("%Y%m%d"), as_ts(end).strftime("%Y%m%d"), "1028")
        if r is not None and len(r):
            r = r.reset_index()
            cl = {str(c): c for c in r.columns}
            dc = cl.get("날짜") or r.columns[0]
            cc = cl.get("종가") or "종가"
            if cc in r.columns:
                d = pd.DataFrame({"date": as_ts_series(r[dc]),
                                  "close": pd.to_numeric(r[cc], errors="coerce")})
                src = "pykrx:1028"
    if d is None and fdr is not None and RUN_MODE != "CACHED":
        try:
            limiter("krx").wait()
            r = fdr.DataReader("KS200", start, end)
            if r is not None and len(r):
                r = r.reset_index()
                r.columns = [str(c).lower() for c in r.columns]
                d = pd.DataFrame({"date": as_ts_series(r[r.columns[0]]),
                                  "close": pd.to_numeric(r["close"], errors="coerce")})
                src = "fdr:KS200"
        except Exception:
            d = None
    if d is None and yf is not None and RUN_MODE != "CACHED":
        try:
            r = yf.download("^KS200", start=start, end=end, progress=False, threads=False)
            if r is not None and len(r):
                if isinstance(r.columns, pd.MultiIndex):
                    r.columns = [str(c[0]).lower() for c in r.columns]
                else:
                    r.columns = [str(c).lower() for c in r.columns]
                r = r.reset_index()
                d = pd.DataFrame({"date": as_ts_series(r[r.columns[0]]),
                                  "close": pd.to_numeric(r["close"], errors="coerce")})
                src = "yfinance:^KS200"
        except Exception:
            d = None
    if d is None:
        ks11 = VAULT.get_table("benchmark_ks11_daily", scope="shared")
        if ks11 is not None and len(ks11):
            cl = {str(c).lower(): c for c in ks11.columns}
            dc, cc = cl.get("date"), cl.get("close")
            if dc and cc:
                d = pd.DataFrame({"date": as_ts_series(ks11[dc]),
                                  "close": pd.to_numeric(ks11[cc], errors="coerce")})
                src = "cache:KS11(KOSPI 근사)"
                LOG.warn("KOSPI200 지수를 못 받아 KOSPI(KS11)로 근사합니다 — 초과수익 해석 주의.")
    if d is None:
        LOG.warn("벤치마크 지수를 확보하지 못했습니다 — 초과수익 지표는 결측 처리됩니다.")
        return pd.DataFrame(columns=["date", "close", "src"])
    d = d.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    d["src"] = src
    if src and not src.startswith("cache"):
        VAULT.put_table("benchmark_k200_daily", d, scope="shared", domain="benchmark", source=src)
    PIPE.io("IN", "HTTP" if "cache" not in src else "DRIVE", "benchmark_k200", d, source=src)
    return d


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증 — CAGR/변동성/Sharpe/Sortino/MDD/Calmar/초과수익/IR/TE/회전율/연도별/        ║
# ║       롤링12M/적중률 + 팩터 IC/상관/기여/leave-one-factor-out/집중도                        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def perf_stats_daily(D: pd.DataFrame, Q: pd.DataFrame,
                     bench_daily: Optional[pd.Series] = None) -> dict:
    """일별 수익 기반 표준 성과지표 + 분기 기반 회전율/적중률."""
    out: Dict[str, Any] = {}
    if D is None or not len(D):
        return out
    r = D.set_index("date")["ret"].astype(float)
    n = len(r)
    ann = 252.0
    eq = (1 + r).cumprod()
    years = n / ann
    out["기간(거래일)"] = n
    out["누적수익"] = float(eq.iloc[-1] - 1)
    out["CAGR"] = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else np.nan
    out["연변동성"] = float(r.std(ddof=1) * math.sqrt(ann)) if n > 2 else np.nan
    dn = r[r < 0]
    dvol = float(dn.std(ddof=1) * math.sqrt(ann)) if len(dn) > 2 else np.nan
    out["Sharpe"] = out["CAGR"] / out["연변동성"] if out.get("연변동성") else np.nan
    out["Sortino"] = out["CAGR"] / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan
    peak = eq.cummax()
    dd = eq / peak - 1
    out["MDD"] = float(dd.min())
    out["Calmar"] = out["CAGR"] / abs(out["MDD"]) if out["MDD"] < 0 else np.nan
    uw, mx = 0, 0
    for x in dd:
        uw = uw + 1 if x < -1e-9 else 0
        mx = max(mx, uw)
    out["최장언더워터(일)"] = int(mx)
    if bench_daily is not None and len(bench_daily):
        b = bench_daily.reindex(r.index).astype(float)
        ex = (r - b).dropna()
        if len(ex) > 20:
            beq = (1 + b.fillna(0)).cumprod()
            b_cagr = float(beq.iloc[-1] ** (1 / years) - 1) if beq.iloc[-1] > 0 else np.nan
            out["벤치마크 CAGR"] = b_cagr
            out["초과 CAGR"] = out["CAGR"] - b_cagr if np.isfinite(b_cagr) else np.nan
            out["누적초과(%p)"] = float((eq.iloc[-1] - beq.reindex(eq.index).ffill().iloc[-1]) * 100)
            te = float(ex.std(ddof=1) * math.sqrt(ann))
            out["트래킹에러"] = te
            out["정보비율(IR)"] = float(ex.mean() * ann / te) if te > 0 else np.nan
    if Q is not None and len(Q):
        qr = Q["ret"].astype(float)
        out["분기 적중률"] = float((qr > 0).mean())
        out["분기평균 회전율(편도)"] = float(Q["turnover"].mean())
        out["분기평균 비용"] = float(Q["cost"].mean())
        out["평균 종목수"] = float(Q["n"].mean())
        n_inv = int((Q["n"] > 0).sum())
        out["투자 분기"] = f"{n_inv}/{len(Q)}"
        if n_inv < len(Q) * 0.7:
            out["⚠ 경고"] = (f"투자 분기가 {n_inv}/{len(Q)} 뿐 — 상당 구간이 현금입니다. "
                            f"커버리지 리포트에서 어느 입력이 비었는지 확인하세요.")
            LOG.warn(f"투자 분기 {n_inv}/{len(Q)} — 대부분 현금인 구간의 성과입니다. "
                     f"입력 커버리지를 반드시 확인하세요(01_coverage_report.csv).")
        mu, t = hac_tstat(qr.to_numpy())
        out["분기평균수익"] = mu
        out["t통계량(HAC)"] = t
    return out


def annual_table(D: pd.DataFrame, bench_daily: Optional[pd.Series]) -> pd.DataFrame:
    if D is None or not len(D):
        return pd.DataFrame()
    r = D.set_index("date")["ret"].astype(float)
    y = (1 + r).groupby(r.index.year).prod() - 1
    out = pd.DataFrame({"전략": y})
    if bench_daily is not None and len(bench_daily):
        b = bench_daily.reindex(r.index).fillna(0)
        yb = (1 + b).groupby(b.index.year).prod() - 1
        out["벤치마크"] = yb
        out["초과(%p)"] = (out["전략"] - out["벤치마크"]) * 100
    return out


def rolling12m_table(D: pd.DataFrame) -> pd.DataFrame:
    if D is None or not len(D):
        return pd.DataFrame()
    r = D.set_index("date")["ret"].astype(float)
    roll = (1 + r).rolling(252).apply(np.prod, raw=True) - 1
    roll = roll.dropna()
    if not len(roll):
        return pd.DataFrame()
    return pd.DataFrame({"stat": ["평균", "중앙값", "최소", "최대", "음수 비율"],
                         "rolling_12m": [roll.mean(), roll.median(), roll.min(), roll.max(),
                                         float((roll < 0).mean())]})


def factor_ic_table(snaps: pd.DataFrame, fwd: pd.DataFrame) -> pd.DataFrame:
    """분기별 팩터 스피어만 IC(팩터값 vs 다음 분기 종목수익) 평균·t통계.
    fwd: (signal_date, code, fwd_ret)"""
    rows = []
    if snaps is None or not len(snaps) or fwd is None or not len(fwd):
        return pd.DataFrame(columns=["factor", "IC_mean", "IC_t", "n_quarters"])
    m = snaps.merge(fwd, on=["signal_date", "code"], how="inner")
    for f in FACTOR_NAMES:
        ics = []
        for sig, g in m.groupby("signal_date"):
            ic = spearman_ic(pd.to_numeric(g[f], errors="coerce"),
                             pd.to_numeric(g["fwd_ret"], errors="coerce"))
            if np.isfinite(ic):
                ics.append(ic)
        if ics:
            mu, t = hac_tstat(np.array(ics))
            rows.append({"factor": f, "IC_mean": mu, "IC_t": t, "n_quarters": len(ics)})
        else:
            rows.append({"factor": f, "IC_mean": np.nan, "IC_t": np.nan, "n_quarters": 0})
    return pd.DataFrame(rows)


def factor_corr_table(snaps: pd.DataFrame) -> pd.DataFrame:
    """분기별 팩터 간 스피어만 상관의 평균 행렬."""
    if snaps is None or not len(snaps):
        return pd.DataFrame()
    mats = []
    for sig, g in snaps.groupby("signal_date"):
        X = g[FACTOR_NAMES].apply(pd.to_numeric, errors="coerce")
        if X.notna().sum().min() < 8:
            continue
        mats.append(X.rank().corr())
    if not mats:
        return pd.DataFrame()
    return sum(mats) / len(mats)


def factor_contribution_table(scored_all: pd.DataFrame) -> pd.DataFrame:
    """선정 포트폴리오의 팩터별 평균 z (합성점수에 대한 기여 = z̄/7)."""
    sel = scored_all[scored_all["selected"] == 1]
    rows = []
    for f in FACTOR_NAMES:
        zc = "z_" + f
        if zc in sel.columns:
            zbar = float(pd.to_numeric(sel[zc], errors="coerce").mean())
            rows.append({"factor": f, "selected_mean_z": zbar, "contribution": zbar / 7.0,
                        "grade": FACTOR_GRADE.get(f, "")})
    return pd.DataFrame(rows)


def concentration_table(bt: dict, sec: pd.DataFrame) -> pd.DataFrame:
    """top30 집중도: 종목 최대비중(동일가중=1/N), 보유빈도 상위, 산업 HHI."""
    H = bt.get("holdings")
    if H is None or not len(H):
        return pd.DataFrame()
    rows = []
    rows.append({"항목": "평균 종목수", "값": f"{H.groupby('signal_date')['code'].size().mean():.1f}"})
    rows.append({"항목": "종목 최대비중", "값": f"{H['weight'].max():.3f}"})
    freq = H["code"].value_counts()
    top5 = ", ".join(f"{c}({int(v)}회)" for c, v in freq.head(5).items())
    rows.append({"항목": "보유빈도 상위5", "값": top5})
    if sec is not None and len(sec):
        ind = sec.set_index("code")["industry"].astype(str).to_dict()
        H2 = H.copy()
        H2["ind"] = H2["code"].map(ind).fillna("미분류")
        hhi = (H2.groupby(["signal_date", "ind"])["weight"].sum() ** 2) \
            .groupby("signal_date").sum()
        rows.append({"항목": "산업 HHI(평균)", "값": f"{hhi.mean():.3f}"})
    return pd.DataFrame(rows)


def print_perf_block(title: str, stats: dict):
    fmt = {"CAGR": "{:+.2%}", "연변동성": "{:.2%}", "Sharpe": "{:.2f}", "Sortino": "{:.2f}",
           "MDD": "{:+.2%}", "Calmar": "{:.2f}", "누적수익": "{:+.2%}",
           "벤치마크 CAGR": "{:+.2%}", "초과 CAGR": "{:+.2%}", "누적초과(%p)": "{:+.1f}",
           "트래킹에러": "{:.2%}", "정보비율(IR)": "{:.2f}", "분기 적중률": "{:.1%}",
           "분기평균 회전율(편도)": "{:.1%}", "분기평균 비용": "{:.3%}",
           "분기평균수익": "{:+.2%}", "t통계량(HAC)": "{:.2f}"}
    rows = []
    for k, v in stats.items():
        if isinstance(v, float) and k in fmt and np.isfinite(v):
            rows.append([k, fmt[k].format(v)])
        else:
            rows.append([k, str(v) if not isinstance(v, float) or np.isfinite(v) else "—"])
    LOG.table(rows, ["지표", "값"], ["l", "r"], title=title)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  전략 실행기 + 강건성 스위트                                                           ║
# ║  계약 §robustness: percentile rank mean / rank sum / zscore winsor 1/99 /                 ║
# ║                    missing<=1 factor mean 을 비교하되 best 를 원형으로 채택하지 않는다.     ║
# ║  추가: paper-close 체결 / 비용 0×·2× / TOP20·40 / 서브기간 / 플라시보(무작위 30종목)        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class StrategyRun:
    """스냅샷(분기×종목×7팩터)에서 표준화→선정→백테스트를 조합 실행·캐시한다."""

    def __init__(self, label: str, snaps: pd.DataFrame, sch: pd.DataFrame,
                 px: pd.DataFrame, delist: Dict[str, pd.Timestamp]):
        self.label = label
        self.snaps = snaps
        self.sch = sch
        self.px = px
        self.delist = delist
        self._cache: Dict[tuple, dict] = {}
        self.scored_baseline: Optional[pd.DataFrame] = None

    def portfolios(self, method: str = "baseline", top_n: int = TOP_N,
                   drop_factor: Optional[str] = None) -> Tuple[Dict, pd.DataFrame]:
        scored_frames = []
        ports: Dict[pd.Timestamp, pd.DataFrame] = {}
        for sig, g in self.snaps.groupby("signal_date"):
            gg = g.copy()
            # drop_factor 는 문자열 하나 또는 목록 — 목록이면 '팩터 부분집합 채점'이 된다.
            # (LOFO 1개 제거 / 수급 결측 시 F6·F7 2개 제거 진단런에 같은 경로를 쓴다)
            drops = ([drop_factor] if isinstance(drop_factor, str)
                     else list(drop_factor or []))
            if drops:
                gg = gg.copy()
                for _df in drops:
                    gg[_df] = np.nan
                use = [f for f in FACTOR_NAMES if f not in drops]
                X = gg[use].apply(pd.to_numeric, errors="coerce")
                elig = X.notna().sum(axis=1) == len(use)
                gg["eligible"] = elig
                E = X[elig]
                if len(E):
                    mu, sd = E.mean(), E.std(ddof=0)
                    Z = (X - mu) / sd.where(sd > 0)
                    for c0 in use:
                        if c0 in sd.index and sd[c0] == 0:
                            Z.loc[X[c0].notna(), c0] = 0.0
                    gg["COMPOSITE"] = np.nan
                    gg.loc[elig, "COMPOSITE"] = Z[elig].mean(axis=1, skipna=False)
                else:
                    gg["COMPOSITE"] = np.nan
                for f in FACTOR_NAMES:
                    gg["z_" + f] = np.nan
                sc = gg
            else:
                sc = compose_scores(gg, method=method)
            pick = select_top(sc, top_n=top_n)
            sc["selected"] = sc["code"].isin(set(pick["code"])).astype(int) if len(pick) else 0
            scored_frames.append(sc)
            if len(pick):
                ports[pd.Timestamp(sig)] = pick[["code", "weight"]]
            elif method == "baseline" and not drop_factor:
                n_e = int(sc["eligible"].sum()) if "eligible" in sc.columns else 0
                LOG.warn(f"{pd.Timestamp(sig):%Y-%m-%d} 편입 보류(현금): 적격 "
                         f"{n_e}<{MIN_ELIGIBLE}종목 — 입력 커버리지를 확인하세요.")
        scored_all = pd.concat(scored_frames, ignore_index=True) if scored_frames \
            else pd.DataFrame()
        return ports, scored_all

    def run(self, method: str = "baseline", exec_mode: str = "next_open",
            cost_mult: float = 1.0, top_n: int = TOP_N,
            drop_factor: Optional[str] = None, tag: str = "") -> dict:
        _dk = (drop_factor if isinstance(drop_factor, str)
               else ("|".join(sorted(drop_factor)) if drop_factor else ""))
        key = (method, exec_mode, round(cost_mult, 4), top_n, _dk)
        if key in self._cache:
            return self._cache[key]
        ports, scored = self.portfolios(method=method, top_n=top_n, drop_factor=drop_factor)
        bt = run_backtest(ports, self.sch, self.px, self.delist,
                          exec_mode=exec_mode, cost_mult=cost_mult,
                          label=tag or f"{self.label}:{method}:{exec_mode}")
        bt["scored"] = scored
        bt["n_ports"] = len(ports)
        if method == "baseline" and exec_mode == "next_open" and cost_mult == 1.0 \
                and top_n == TOP_N and not drop_factor:
            self.scored_baseline = scored
        self._cache[key] = bt
        return bt


def forward_returns_from_bt(sr: StrategyRun) -> pd.DataFrame:
    """(signal_date, code, fwd_ret): 체결일→다음 체결일 보유수익 — IC 계산용.
    유니버스 전 종목에 대해 벡터화 계산 (종목별 루프 금지 — 하위1000 유니버스에서 수 분 차이)."""
    all_codes = set(sr.snaps["code"])
    book = PriceBook(sr.px, all_codes)
    closef = book.close.ffill()
    idx = closef.index
    rows = []
    for _, r in sr.sch.iterrows():
        sig, ex, nx = r["signal_date"], r["exec_date"], r["next_exec"]
        members = sr.snaps.loc[sr.snaps["signal_date"] == sig, "code"].tolist()
        if not members or not len(idx):
            continue

        def _row(ts):
            pos = int(idx.searchsorted(ts, side="right")) - 1
            if pos < 0:
                return None, None
            d0 = idx[pos]
            # ★ open 피벗은 close 피벗과 행이 다를 수 있다(open 전결측 날짜 탈락) —
            #   위치(iloc)가 아니라 라벨(loc)로만 접근한다(감사 높음: 오정렬/IndexError).
            o = book.open_.loc[d0] if (d0 == ts and d0 in book.open_.index) else None
            cfb = closef.iloc[pos]
            return o, cfb

        o0, c0 = _row(pd.Timestamp(ex))
        o1, c1 = _row(pd.Timestamp(nx))
        if c0 is None or c1 is None:
            continue
        p0 = (o0.where(o0.notna(), c0) if o0 is not None else c0)
        p1 = (o1.where(o1.notna(), c1) if o1 is not None else c1)
        fr = (p1 / p0 - 1.0).reindex(members)
        fr = fr[np.isfinite(fr)]
        for c, val in fr.items():
            rows.append({"signal_date": sig, "code": c, "fwd_ret": float(val)})
    return pd.DataFrame(rows)


def run_robustness(sr: StrategyRun, base: dict, bench_daily: Optional[pd.Series],
                   n_placebo: int = 300) -> pd.DataFrame:
    """강건성 표. Primary(사전고정 baseline)는 맨 위, 변형은 비교 전용."""
    rows = []

    def _add(name, bt, note=""):
        st = perf_stats_daily(bt["daily"], bt["quarterly"], bench_daily)
        rows.append({"variant": name, "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe"),
                     "MDD": st.get("MDD"), "IR": st.get("정보비율(IR)"),
                     "hit": st.get("분기 적중률"), "n_q": bt.get("n_ports"), "note": note})

    _add("★PRIMARY baseline(z·ddof0·no-winsor)", base, "사전고정 — 이것만 Primary")
    for m, nm in (("rank_mean", "R1 percentile-rank mean"), ("rank_sum", "R1 rank sum"),
                  ("winsor_z", "R1 zscore winsor 1/99"),
                  ("missing1_mean", "R1 missing<=1 mean")):
        try:
            _add(nm, sr.run(method=m), "계약 robustness 전용 — 원형 채택 금지")
        except Exception as e:                                     # noqa
            rows.append({"variant": nm, "note": f"실패:{type(e).__name__}"})
    try:
        _add("R2 paper-close 체결", sr.run(exec_mode="paper_close"), "신호일 종가 체결(계약 별도)")
    except Exception as e:                                          # noqa
        rows.append({"variant": "R2 paper-close", "note": f"실패:{type(e).__name__}"})
    for cm, nm in ((0.0, "R3 비용 0×"), (2.0, "R3 비용 2×")):
        try:
            _add(nm, sr.run(cost_mult=cm))
        except Exception as e:                                      # noqa
            rows.append({"variant": nm, "note": f"실패:{type(e).__name__}"})
    for tn in (20, 40):
        try:
            _add(f"R4 TOP{tn}", sr.run(top_n=tn))
        except Exception as e:                                      # noqa
            rows.append({"variant": f"R4 TOP{tn}", "note": f"실패:{type(e).__name__}"})

    # R5 서브기간 (전반/후반)
    D = base["daily"]
    if D is not None and len(D) > 100:
        mid = D["date"].iloc[len(D) // 2]
        for nm, seg in (("R5 전반기", D[D["date"] <= mid]), ("R5 후반기", D[D["date"] > mid])):
            st = perf_stats_daily(seg.reset_index(drop=True), None, bench_daily)
            rows.append({"variant": nm, "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe"),
                         "MDD": st.get("MDD"), "note": f"{seg['date'].min():%Y-%m}~"
                                                       f"{seg['date'].max():%Y-%m}"})

    # R6 플라시보: 동일 유니버스에서 무작위 30종목 — 실제 전략 분기수익 평균의 백분위
    try:
        fwd = forward_returns_from_bt(sr)
        if len(fwd):
            actual_q = base["quarterly"]["ret"].mean() if len(base["quarterly"]) else np.nan
            sims = []
            by_sig = {s: g for s, g in fwd.groupby("signal_date")}
            for _ in range(n_placebo):
                qs = []
                for s, g in by_sig.items():
                    if len(g) >= TOP_N:
                        samp = g.sample(TOP_N, random_state=int(RNG.integers(0, 2**31)))
                        qs.append(samp["fwd_ret"].mean())
                if qs:
                    sims.append(float(np.mean(qs)))
            if sims and np.isfinite(actual_q):
                pct = float((np.array(sims) < actual_q).mean())
                rows.append({"variant": "R6 플라시보(무작위30)", "CAGR": np.nan,
                             "note": f"실제 분기평균 {actual_q:+.2%} → 무작위 대비 백분위 "
                                     f"{pct:.1%} (N={len(sims)})"})
    except Exception as e:                                          # noqa
        rows.append({"variant": "R6 플라시보", "note": f"실패:{type(e).__name__}"})

    R = pd.DataFrame(rows)
    LOG.banner(f"강건성 검사 — {sr.label}",
               "계약: 성과 최고 변형을 '원형'으로 채택하지 않는다. Primary=사전고정 baseline")
    LOG.table([[r.get("variant", ""),
                f"{r['CAGR']:+.2%}" if isinstance(r.get("CAGR"), float) and
                np.isfinite(r.get("CAGR", np.nan)) else "—",
                f"{r['Sharpe']:.2f}" if isinstance(r.get("Sharpe"), float) and
                np.isfinite(r.get("Sharpe", np.nan)) else "—",
                f"{r['MDD']:+.1%}" if isinstance(r.get("MDD"), float) and
                np.isfinite(r.get("MDD", np.nan)) else "—",
                f"{r['IR']:.2f}" if isinstance(r.get("IR"), float) and
                np.isfinite(r.get("IR", np.nan)) else "—",
                f"{r['hit']:.0%}" if isinstance(r.get("hit"), float) and
                np.isfinite(r.get("hit", np.nan)) else "—",
                _trunc(str(r.get("note", "")), 44)]
               for r in R.to_dict("records")],
              ["변형", "CAGR", "Sharpe", "MDD", "IR", "적중률", "비고"],
              ["l", "r", "r", "r", "r", "r", "l"])
    return R


def run_lofo(sr: StrategyRun, bench_daily: Optional[pd.Series]) -> pd.DataFrame:
    """leave-one-factor-out — 각 팩터를 빼고 6팩터 합성으로 재실행."""
    rows = []
    base = sr.run()
    st0 = perf_stats_daily(base["daily"], base["quarterly"], bench_daily)
    for f in FACTOR_NAMES:
        try:
            bt = sr.run(drop_factor=f, tag=f"LOFO-{f}")
            st = perf_stats_daily(bt["daily"], bt["quarterly"], bench_daily)
            rows.append({"dropped": f, "CAGR": st.get("CAGR"), "Sharpe": st.get("Sharpe"),
                         "dCAGR": (st.get("CAGR", np.nan) or np.nan) -
                                  (st0.get("CAGR", np.nan) or np.nan)})
        except Exception as e:                                      # noqa
            rows.append({"dropped": f, "CAGR": np.nan, "Sharpe": np.nan, "dCAGR": np.nan,
                         "err": type(e).__name__})
    return pd.DataFrame(rows)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-S  합성데이터 스모크 — 실데이터 수집 전에 '계산경로 전체'를 먼저 증명한다               ║
# ║  (팩터 스냅샷 → 표준화 → 선정 → 백테스트 → 성과 → 강건성 → 산출물 쓰기)                    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _synth_dataset(n_stocks: int = 90, start: str = "2016-08-01", end: str = "2026-07-31"):
    rng = np.random.default_rng(SEED)
    codes = [f"{100000 + i * 7:06d}" for i in range(n_stocks)]
    days = pd.bdate_range(start, end)
    # 가격: GBM + 공통시장요인
    mkt = rng.normal(0.0003, 0.01, len(days)).cumsum()
    px_rows = []
    delist_at = {}
    for i, c in enumerate(codes):
        beta = 0.6 + 0.8 * rng.random()
        idio = rng.normal(0.0002, 0.02, len(days)).cumsum()
        lp = np.log(5000 + 100 * i) + beta * mkt + idio
        close = np.exp(lp)
        n_i = len(days)
        if i % 17 == 5:                              # 일부 종목 상장폐지 (생존자편향 경로 검증)
            n_i = int(len(days) * (0.3 + 0.5 * rng.random()))
            delist_at[c] = days[n_i - 1] + pd.Timedelta(days=30)
        openp = close * (1 + rng.normal(0, 0.004, len(days)))
        vol = rng.integers(1e4, 5e5, len(days)).astype(float)
        px_rows.append(pd.DataFrame({
            "code": c, "date": days[:n_i], "open": openp[:n_i], "high": close[:n_i] * 1.01,
            "low": close[:n_i] * 0.99, "close": close[:n_i], "volume": vol[:n_i],
            "amount": close[:n_i] * vol[:n_i], "src": "synth"}))
    px = pd.concat(px_rows, ignore_index=True)

    sec = pd.DataFrame({"code": codes, "name": [f"합성{i:03d}" for i in range(n_stocks)],
                        "market": ["KOSPI" if i % 3 else "KOSDAQ" for i in range(n_stocks)],
                        "listing_date": as_ts("2010-01-01"),
                        "delisting_date": [delist_at.get(c, pd.NaT) for c in codes],
                        "corp_code": [f"{900000 + i}" for i in range(n_stocks)],
                        "industry": [f"산업{i % 6}" for i in range(n_stocks)], "src": "synth"})

    # 분기 실적 (접수일 = 분기말 + 40일)
    try:
        qs = pd.date_range("2014-03-31", end, freq="QE")     # pandas>=2.2
    except ValueError:
        qs = pd.date_range("2014-03-31", end, freq="Q")      # pandas<2.2 폴백
    earn_rows = []
    for i, c in enumerate(codes):
        base_ni = 1e9 * (1 + i % 7)
        g = rng.normal(0.02, 0.15, len(qs)).cumsum()
        ni = base_ni * np.exp(g)
        for j, q in enumerate(qs):
            earn_rows.append({"code": c, "corp_code": f"{900000 + i}", "period_end": q,
                              "knowledge_date": q + pd.Timedelta(days=40),
                              "event_date": q, "ni_q": ni[j],
                              "op_q": ni[j] * 1.2, "rev_q": ni[j] * 8})
    earn = pd.DataFrame(earn_rows).sort_values(["code", "period_end"])
    earn["ni_ttm"] = (earn.groupby("code")["ni_q"]
                      .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    earn = pit_frame(earn, "event_date", "knowledge_date", source="synth")

    # 리포트 연결표 (애널리스트 40명, 목표주가 = 현재가 × (1+노이즈))
    close_map = px.groupby("code")["close"].last().to_dict()
    li_rows = []
    analysts = [(f"analyst{a:02d}", f"br{a % 8}") for a in range(40)]
    pub_days = pd.date_range("2015-01-15", end, freq="2D")
    for d in pub_days:
        for _ in range(8):        # 90일 윈도우당 종목별 3~4건 — F4/F5 커버리지 경로 검증용 밀도
            c = codes[int(rng.integers(0, n_stocks))]
            a, b = analysts[int(rng.integers(0, len(analysts)))]
            li_rows.append({"report_uid": sha1_str(d, c, a)[:16], "analyst_id": a,
                            "name": a, "broker_id": b, "broker_name": b, "role": "lead",
                            "link_method": "list_field", "link_conf": 0.98,
                            "pub_date": d, "stock_code": c,
                            "target_price": close_map.get(c, 10000) *
                            (1.1 + 0.2 * rng.random())})
    links = pd.DataFrame(li_rows)

    # 수급 윈도우 · 시총 단면은 스냅샷 시점에 즉석 생성
    return {"px": px, "sec": sec, "earn": earn, "links": links, "codes": codes}


def run_smoke(full_outputs: bool = False) -> bool:
    """합성 엔드투엔드. full_outputs=True(RUN_MODE=SMOKE)면 산출물 파일까지 쓴다."""
    t0 = time.time()
    ds = _synth_dataset()
    px, sec, earn, links = ds["px"], ds["sec"], ds["earn"], ds["links"]
    cal = trading_calendar(px)
    sch = rebalance_schedule(cal, "2016-08-01", "2026-07-31")
    assert len(sch) >= 35, f"리밸런스 일정이 {len(sch)}개 — 40개 내외여야 정상"

    cons = ConsensusStore(links, px[["code", "date", "close"]])
    rng = np.random.default_rng(SEED + 1)
    snaps = []
    for _, r in sch.iterrows():
        sig = r["signal_date"]
        alive = px[(px["date"] <= sig) &
                   (px["date"] > sig - pd.Timedelta(days=10))]["code"].unique().tolist()
        mcap = (px[px["date"] <= sig].groupby("code").tail(1)[["code", "close"]]
                .assign(marcap=lambda d: d["close"] * 1e6, shares=1e6, market="KOSPI"))
        fl = pd.DataFrame({"signal_date": sig, "code": alive,
                           "inst_net": rng.normal(0, 1e8, len(alive)),
                           "forg_net": rng.normal(0, 1e8, len(alive))})
        snaps.append(build_factor_snapshot(sig, alive, mcap, earn, cons, fl))
    S = pd.concat(snaps, ignore_index=True)
    n_valid = S[FACTOR_NAMES].notna().all(axis=1).sum()
    assert n_valid > 200, f"7팩터 전부 유효 표본이 {n_valid}건 — 팩터 계산 경로 이상"

    delist = {r.code: r.delisting_date for r in sec.itertuples() if pd.notna(r.delisting_date)}
    sr = StrategyRun("SMOKE", S, sch, px, delist)
    bt = sr.run()
    assert len(bt["quarterly"]) >= 35 and len(bt["daily"]) > 1000, "백테스트 출력 이상"
    st = perf_stats_daily(bt["daily"], bt["quarterly"], None)
    assert np.isfinite(st.get("CAGR", np.nan)), "성과지표 계산 실패"
    _ = run_lofo(sr, None)
    if full_outputs:
        print_perf_block("스모크 성과표 (합성데이터 — 숫자는 무의미, 경로 검증용)", st)
        rob = run_robustness(sr, bt, None, n_placebo=40)
        fwd = forward_returns_from_bt(sr)
        outdir = os.path.join(os.path.abspath("."), "smoke_outputs")
        outs = write_outputs(outdir, {
            "coverage": pd.DataFrame([{"item": "smoke", "verdict": "OK"}]),
            "snaps": S, "scored": bt.get("scored", pd.DataFrame()),
            "holdings": bt.get("holdings", pd.DataFrame()),
            "trades": bt.get("quarterly", pd.DataFrame()),
            "perf_table": pd.DataFrame([{"metric": k, "value": v} for k, v in st.items()]),
            "ic_table": factor_ic_table(S, fwd), "robust_table": rob,
            "vendor": {"status": "SMOKE", "detail": [], "active": False},
            "universe_def": "synthetic", "universe_method": "synthetic",
            "timed_core_s": time.time() - t0})
        LOG.ok(f"스모크 산출물 {len(outs)}개 → {outdir}")
    LOG.ok(f"합성 스모크 통과 ({time.time() - t0:.1f}s) — 계산경로 전체가 증명되었습니다.")
    return True


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  산출물 — 계약 지정 01~11 파일 + config.yaml + data_dictionary.md · 다운로드 링크      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]):
    """미리보기 없이 '클릭하면 바로 저장'되는 링크만 띄운다 (Colab: files.download)."""
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
            html.append(f"<a download='{os.path.basename(p)}' "
                        f"href='data:application/octet-stream;base64,{b64}' "
                        f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                        f"background:#1a73e8;color:#fff;border-radius:6px;"
                        f"text-decoration:none'>⬇ {os.path.basename(p)} "
                        f"({len(b)/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        for p in paths:
            _safe_print(f"⬇  산출물 경로: {p}")


def _csv(path: str, df: pd.DataFrame):
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_outputs(outdir: str, ctx: dict) -> List[str]:
    """계약 [출력] 섹션의 파일 목록을 그대로 만든다. 실패한 항목은 사유를 남기고 계속."""
    os.makedirs(outdir, exist_ok=True)
    outs: List[str] = []

    def _try(fn, name):
        try:
            p = fn()
            if p:
                outs.append(p)
        except Exception as e:                                      # noqa
            LOG.warn(f"산출물 {name} 저장 실패({type(e).__name__}) — 계속 진행합니다.")

    cov = ctx.get("coverage", pd.DataFrame())
    _try(lambda: _csv(os.path.join(outdir, "01_coverage_report.csv"),
                      cov if len(cov) else pd.DataFrame([{"item": "no_data"}])),
         "01_coverage_report")
    snaps = ctx.get("snaps", pd.DataFrame())
    _try(lambda: atomic_write_parquet(snaps, os.path.join(outdir, "02_factor_snapshots.parquet"))
         if len(snaps) else None, "02_factor_snapshots")
    scored = ctx.get("scored", pd.DataFrame())
    zcols = ["signal_date", "code"] + ["z_" + f for f in FACTOR_NAMES] + \
        ["eligible", "selected"]
    _try(lambda: atomic_write_parquet(scored[[c for c in zcols if c in scored.columns]],
                                      os.path.join(outdir, "03_component_scores.parquet"))
         if len(scored) else None, "03_component_scores")
    ccols = ["signal_date", "code", "COMPOSITE", "eligible", "selected"]
    _try(lambda: atomic_write_parquet(scored[[c for c in ccols if c in scored.columns]]
                                      .assign(universe_definition=ctx.get("universe_def", "")),
                                      os.path.join(outdir, "04_composite_scores.parquet"))
         if len(scored) else None, "04_composite_scores")
    holds = ctx.get("holdings", pd.DataFrame())
    _try(lambda: atomic_write_parquet(holds, os.path.join(outdir, "05_portfolios.parquet"))
         if len(holds) else None, "05_portfolios")
    trades = ctx.get("trades", pd.DataFrame())
    _try(lambda: atomic_write_parquet(trades, os.path.join(outdir, "06_trades.parquet"))
         if len(trades) else None, "06_trades")
    perf = ctx.get("perf_table", pd.DataFrame())
    _try(lambda: _csv(os.path.join(outdir, "07_performance.csv"), perf), "07_performance")
    ic = ctx.get("ic_table", pd.DataFrame())
    _try(lambda: _csv(os.path.join(outdir, "08_factor_ic.csv"), ic), "08_factor_ic")
    rob = ctx.get("robust_table", pd.DataFrame())
    _try(lambda: _csv(os.path.join(outdir, "09_robustness.csv"), rob), "09_robustness")

    def _costs():
        p = os.path.join(outdir, "cost_schedule.parquet")
        rows = [{"item": "sell_tax", "effective_from": d, "rate": t} for d, t in TAX_SCHEDULE]
        rows.append({"item": "commission_oneway_bps", "effective_from": "ALL",
                     "rate": COMMISSION_BPS})
        rows.append({"item": "slippage_sqrt_k", "effective_from": "ALL", "rate": SLIPPAGE_K})
        rows.append({"item": "account_krw_for_participation", "effective_from": "ALL",
                     "rate": float(ACCOUNT_KRW)})
        atomic_write_parquet(pd.DataFrame(rows), p)
        return p
    _try(_costs, "cost_schedule")

    def _md():
        p = os.path.join(outdir, "10_exact_vs_reconstructed.md")
        v = ctx.get("vendor", {})
        lines = [
            "# EXACT vs RECONSTRUCTED",
            f"\nSTATUS = **{v.get('status', '?')}**\n",
            f"- 실행(계산) 모드: {RECON_LABEL} — 벤더 데이터 존재 여부와 무관하게 이 실행의 "
            f"모든 수치는 재구성 규칙으로 계산되었다(모드 혼합 금지).",
            f"- universe_definition = `{ctx.get('universe_def', '')}` "
            f"(method: {ctx.get('universe_method', '')})",
            "- 재구성 규칙(사전고정): 각 리밸런스 횡단면에서 z=(x-μ)/σ(모집단 ddof=0), "
            "winsorization 없음, COMPOSITE=Σz/7, 7팩터 전부 유효 종목만, 상위 30 동일가중.",
            "- 이 재구성 규칙은 공개정보 기반 재현이며 **신한 원문에 명시된 공식이 아니다**.",
            "- FnGuide Smart Consensus historical field 부재 시 10년 exact test 불가 → "
            "본 실행의 스마트 컨센서스는 프록시(과거 예측오차 상위 애널리스트군)로만 사용되었고 "
            "'exact' 라 칭하지 않는다.",
            "\n## 팩터 입력 등급", "",
        ]
        for f in FACTOR_NAMES:
            lines.append(f"- {f}: {FACTOR_GRADE.get(f, '?')}")
        lines.append("\n## 벤더 검사 상세\n")
        for dline in v.get("detail", []):
            lines.append(f"- {dline}")
        lines.append("\n## 원문 historical anchor 비교(참고 전용)\n")
        lines.append("- 원문: 2022 누적초과 ≈ +52%p, Covid 이후 ≈ +88%p — 어떤 정규화 선택도 "
                     "이 숫자에 맞추지 않았다(계약 §연구윤리).")
        anchor = ctx.get("anchor_2022")
        if anchor is not None:
            lines.append(f"- 재구성 2022 누적초과: {anchor:+.1f}%p (동일기간·공개데이터 기준)")
        fx = ctx.get("fixture_overlap")
        if fx is not None:
            lines.append(f"- 2022-4Q validation fixture(원문 공개 {len(VALIDATION_2022Q4_NAMES)}종목 "
                         f"발췌) 대비 재구성 선정 겹침: {fx}종목 — fixture 는 신호로 사용하지 않음.")
        atomic_write_text(p, "\n".join(lines))
        return p
    _try(_md, "10_exact_vs_reconstructed")

    def _rt():
        p = os.path.join(outdir, "11_runtime_profile.json")
        prof = PIPE.runtime_profile()
        prof["timed_core_seconds"] = ctx.get("timed_core_s")
        prof["sla_seconds"] = SLA_SECONDS
        prof["sla_verdict"] = ("PASS" if (ctx.get("timed_core_s") or 0) <= SLA_SECONDS
                               else "FAIL")
        prof["run_mode"] = RUN_MODE
        atomic_write_text(p, json.dumps(prof, ensure_ascii=False, indent=2, default=str))
        return p
    _try(_rt, "11_runtime_profile")

    def _cfg():
        p = os.path.join(outdir, "config.yaml")
        cfg = {"strategy_id": STRATEGY_ID, "strategy_name": STRATEGY_NAME,
               "mode": RECON_LABEL,          # 계산은 항상 재구성 — 벤더 상태는 별도 필드
               "vendor_status": ctx.get("vendor", {}).get("status", ""),
               "backtest": {"start": BACKTEST_START, "end": BACKTEST_END,
                            "rebalance": "quarterly last trading day of 3/6/9/12",
                            "signal": "after close", "execution": "next open",
                            "top_n": TOP_N, "weighting": "equal"},
               "normalization": {"z": "population std (ddof=0)", "winsorization": "none",
                                 "composite": "mean of 7 z", "eligibility": "all 7 valid",
                                 "f5_proxy": "TP-consensus 1M revision → DART TTM revision "
                                             "fallback (계약식 EPS12MF 시계열 공개 미가용 — "
                                             "혼합 비중은 01_coverage 의 F5_src_* 행 참조)"},
               "universe_definition": ctx.get("universe_def", ""),
               "universe_method": ctx.get("universe_method", ""),
               "comparison": {"universe": f"bottom {CMP_BOTTOM_N} by marketcap",
                              "enabled": INCLUDE_COMPARISON},
               "costs": {"commission_bps_oneway": COMMISSION_BPS,
                         "sell_tax_schedule": {d: t for d, t in TAX_SCHEDULE},
                         "slippage": f"sqrt impact k={SLIPPAGE_K}",
                         "account_krw": ACCOUNT_KRW},
               "factor_grades": FACTOR_GRADE, "seed": SEED, "build": BUILD_VERSION}
        try:
            import yaml as _yaml                       # type: ignore
            atomic_write_text(p, _yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
        except Exception:
            atomic_write_text(p, json.dumps(cfg, ensure_ascii=False, indent=2, default=str))
        return p
    _try(_cfg, "config.yaml")

    def _dd():
        p = os.path.join(outdir, "data_dictionary.md")
        lines = ["# Data Dictionary — " + STRATEGY_NAME, "",
                 "| 산출물 | 내용 | 키 컬럼 |", "|---|---|---|",
                 "| 01_coverage_report.csv | 팩터·데이터소스 커버리지(분기×팩터 유효비율, "
                 "벤더검사 결과) | signal_date, factor |",
                 "| 02_factor_snapshots.parquet | 분기 신호일 7팩터 원값 | signal_date, code |",
                 "| 03_component_scores.parquet | 팩터별 z-score | signal_date, code |",
                 "| 04_composite_scores.parquet | 합성점수·적격·선정 플래그 | signal_date, code |",
                 "| 05_portfolios.parquet | 분기 보유 30종목·비중·체결가 | signal_date, code |",
                 "| 06_trades.parquet | 분기 매매(진입/청산·회전율·비용) | signal_date |",
                 "| 07_performance.csv | 본전략·비교전략 성과지표 | metric |",
                 "| 08_factor_ic.csv | 팩터별 분기 IC 평균·t | factor |",
                 "| 09_robustness.csv | 강건성 변형별 성과 | variant |",
                 "| 10_exact_vs_reconstructed.md | 정확/재구성 모드 판정·입력등급 | — |",
                 "| 11_runtime_profile.json | 계층·스테이지 실측 런타임, SLA 판정 | — |", "",
                 "## PIT 규약",
                 "- 모든 팩터 입력은 knowledge_date <= signal_date 로 절단(미래누수 차단).",
                 "- 실적 knowledge_date = DART 접수일자(rcept_no). 리포트 = 발간일.",
                 "- 수급 = 신호일 이전 20거래일 윈도우 합계. 시총 = 신호일 단면.",
                 "- Smart Consensus historical revision 을 현재 데이터로 소급복원하지 않음(계약).",
                 "",
                 "## 알려진 한계(정직 명시)",
                 "- FnGuide 벤더 팩터(F1~F5 원본) 부재 → 공개 프록시 사용, 등급을 "
                 "factor_grades 로 기록.",
                 "- EPS 성장 프록시는 순이익 성장(주식수 변동 미반영)이며 컨센서스 추정치가 아닌 "
                 "실적 기지치 기반.",
                 "- 과거 관리종목/거래정지 이력은 공개 소급 불가 → 유니버스 필터에 미반영.",
                 "- KOSPI200 멤버십은 관측 실패 시 시총 상위 200 재구성(정확 지수 규칙과 상이).",
                 "- 가격 소스 혼합: 수정주가 소스(pykrx/FDR/네이버)와 분할보정 marcap 을 "
                 "우선순위 병합. 서로 다른 시기에 수집된 수정주가 구간의 접합부 불연속은 "
                 "|일수익|>50% 절벽 감사로 탐지해 커버리지에 기록한다(완전 재수정은 아님)."]
        atomic_write_text(p, "\n".join(lines))
        return p
    _try(_dd, "data_dictionary.md")

    log_p = os.path.join(outdir, "run_log.txt")
    _try(lambda: atomic_write_text(log_p, "\n".join(LOG.buffer)), "run_log")
    return outs


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC: Optional[pd.DataFrame] = None


def _coverage_report(snaps: pd.DataFrame, vendor: dict, extra_rows: List[dict]) -> pd.DataFrame:
    rows = []
    if snaps is not None and len(snaps):
        for sig, g in snaps.groupby("signal_date"):
            n = len(g)
            for f in FACTOR_NAMES:
                v = int(pd.to_numeric(g[f], errors="coerce").notna().sum())
                rows.append({"signal_date": pd.Timestamp(sig).strftime("%Y-%m-%d"),
                             "factor": f, "grade": FACTOR_GRADE.get(f, ""),
                             "n_universe": n, "n_valid": v,
                             "valid_pct": round(100.0 * v / max(n, 1), 1)})
        allv = snaps[FACTOR_NAMES].notna().all(axis=1)
        rows.append({"signal_date": "ALL", "factor": "ALL7_VALID", "grade": "-",
                     "n_universe": len(snaps), "n_valid": int(allv.sum()),
                     "valid_pct": round(100.0 * allv.mean(), 1)})
    for r in vendor.get("coverage_rows", []):
        rows.append({"signal_date": "VENDOR", "factor": r.get("item", ""),
                     "grade": "vendor", "n_universe": r.get("quarters", 0),
                     "n_valid": r.get("tickers", 0), "valid_pct": np.nan,
                     "verdict": r.get("verdict", "")})
    if not vendor.get("active"):
        rows.append({"signal_date": "VENDOR", "factor": "smart_consensus_historical",
                     "grade": "vendor", "n_universe": 0, "n_valid": 0, "valid_pct": 0.0,
                     "verdict": "EXACT_MODE=FAIL_COVERAGE"})
    rows.extend(extra_rows)
    return pd.DataFrame(rows)


def _collect_research(sec: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """리포트 원장: 캐시 우선 → 부족 연도만 신규 수집 → 드라이브 재적재. (rep, A, L)"""
    cached = VAULT.get_table("research_report_master", scope="shared")
    frames = []
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 보고서 원장 {len(cached):,}건 재사용")
        frames.append(cached)
    # adopt 로 등록된 타 전략 리포트 카탈로그도 흡수 (컬럼이 맞는 것만)
    for p in VAULT.adopted_paths(["report_master", "report_catalog", "research_report_index"],
                                 exts=(".parquet", ".csv"))[:6]:
        try:
            d = read_parquet_safe(p) if p.endswith(".parquet") else pd.read_csv(p)
            if d is not None and len(d) and {"pub_date", "title"} <= set(map(str, d.columns)):
                d["source"] = d.get("source", "adopted")
                if "src_report_id" not in d.columns:
                    d["src_report_id"] = [sha1_str(p, i)[:12] for i in range(len(d))]
                frames.append(d)
                LOG.info(f"adopt 리포트 카탈로그 흡수: {os.path.basename(p)} {len(d):,}건")
        except Exception:
            continue

    if RESEARCH_COLLECT and RUN_MODE == "FULL":
        # ★ 실운행 사고 2회차의 F4 원인 — 커버리지 판정이 '행 수'만 셌다.
        #   네이버 리서치는 애널리스트·목표주가를 주지 않는데(연결률 0.0% · TP율 0.0%),
        #   그 행이 연도당 300건을 넘겨 "캐시 충분"으로 판정되어 한경컨센서스를 2016년 이후
        #   한 해도 수집하지 않았다. 결과: 목표주가가 있는 리포트가 2015년뿐 →
        #   스마트/일반 컨센서스를 만들 수 없어 F4 가 40개 분기 전부 결측 → 적격종목 0.
        #   → F4 에 실제로 쓸 수 있는 행(목표주가 AND 애널리스트)만 센다.
        def _usable_by_year(fs: List[pd.DataFrame]) -> Counter:
            c: Counter = Counter()
            for f in fs:
                if f is None or not len(f) or "pub_date" not in f.columns:
                    continue
                tp = pd.to_numeric(col(f, "target_price"), errors="coerce")
                an = col(f, "analyst_raw").astype(str)
                if an.replace({"nan": "", "None": ""}).str.strip().eq("").all():
                    an = col(f, "analysts").astype(str)
                ok = tp.notna() & (tp > 0) & \
                    an.replace({"nan": "", "None": ""}).str.strip().ne("")
                if not bool(ok.any()):
                    continue
                yy = as_ts_series(f.loc[ok, "pub_date"]).dt.year.dropna().astype(int)
                c.update(yy.value_counts().to_dict())
            return c

        usable = _usable_by_year(frames)
        years_all = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
        need_years = [y for y in years_all if usable.get(y, 0) < RESEARCH_MIN_USABLE_PER_YEAR]
        LOG.table([[str(y), f"{usable.get(y, 0):,}",
                    "수집" if y in need_years else "충분"] for y in years_all],
                  ["연도", "F4 가용 리포트(목표주가+애널리스트)", "판정"], ["c", "r", "c"],
                  title="리서치 커버리지 — '행 수'가 아니라 'F4 에 쓸 수 있는 행 수'로 판정")
        if need_years:
            LOG.info(f"리포트 신규 수집 대상 연도 {len(need_years)}개: {need_years}")
            LOG.info("※ 한경컨센서스·네이버는 robots.txt Disallow — 사용자 지시에 따라 "
                     "보수적 속도로만 수집합니다. PDF 원문은 재배포 금지.")
            LOG.info("※ 한경컨센서스가 애널리스트·목표주가를 주는 유일한 소스입니다 "
                     "(실측 연결률 100% · TP율 90%) → 이쪽을 먼저 채웁니다.")
            for y in need_years:                       # 한경 먼저 전 연도
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(hankyung_collect(f"{y}-01-01", f"{y}-12-31"))
            _u2 = _usable_by_year(frames)
            for y in need_years:                       # 그래도 부족한 연도만 네이버
                if "naver" in RESEARCH_SOURCES and \
                        _u2.get(y, 0) < RESEARCH_MIN_USABLE_PER_YEAR:
                    frames.append(naver_collect(f"{y}-01-01", f"{y}-12-31"))
        else:
            LOG.ok("모든 연도에 F4 가용 리포트가 충분 — 신규 수집 생략.")
    rep = build_report_master(frames, sec)
    if len(rep):
        VAULT.put_table("research_report_master", rep, scope="shared", domain="research",
                        source="hankyung+naver+cache")
    A, L = build_analyst_ledger(rep)
    if len(A):
        VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                        source="entity_resolution")
        VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                        source="entity_resolution")
    audit_linkage(rep, A, L)
    return rep, A, L


def _dump_diagnostics(snaps, k200_mem, cmp_mem, spine_panel, flows, earn, cons,
                      uni_meta, vendor, px) -> List[str]:
    """★ v1.1: 백테스트가 성립하지 않았을 때도 '왜'를 남긴다.
    팩터별 결손율 표를 로그에 찍고, 커버리지 CSV + 진단 마크다운을 전용 인덱스에 저장한다."""
    LOG.banner("입력 결손 진단", "어느 입력이 비어 적격종목 0이 되었는지")
    rows = []
    if snaps is not None and len(snaps):
        for f in FACTOR_NAMES:
            v = int(pd.to_numeric(snaps[f], errors="coerce").notna().sum())
            rows.append([f, FACTOR_GRADE.get(f, ""), f"{v:,}/{len(snaps):,}",
                         f"{100.0 * v / max(len(snaps), 1):.1f}%",
                         "★비었음 — 이 팩터가 원인" if v == 0 else ""])
    else:
        rows.append(["(스냅샷 자체가 0행)", "", "0", "0.0%",
                     "★유니버스가 비었습니다 — 시총 스파인부터 확인"])
    LOG.table(rows, ["팩터", "입력등급", "유효/전체", "유효율", "판정"],
              ["l", "l", "r", "r", "l"], title="7팩터 입력 커버리지")
    LOG.table([["유니버스 방법", str(uni_meta.get("method", ""))],
               ["유니버스 결손 분기", f"{len(uni_meta.get('missing', []))}개"],
               ["시총 스파인 등급", str(uni_meta.get("mcap_grades", {}))],
               ["K200 멤버십 행", f"{len(k200_mem):,}"],
               ["비교 멤버십 행", f"{len(cmp_mem):,}"],
               ["수급(F6/F7) 행", f"{len(flows):,}"],
               ["DART 실적 행", f"{len(earn):,}"],
               ["컨센서스 스토어", "활성" if getattr(cons, "ok", False) else "비활성"],
               ["일봉 행", f"{len(px):,}"]],
              ["항목", "값"], ["l", "r"], title="L1 입력 요약")
    outs: List[str] = []
    try:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(VAULT.ns["private"], "reports", f"diag_{stamp}")
        os.makedirs(outdir, exist_ok=True)
        cov = _coverage_report(snaps, vendor, [
            {"signal_date": "SOURCE", "factor": k, "grade": "input",
             "n_universe": n, "n_valid": n, "valid_pct": np.nan}
            for k, n in (("prices_rows", len(px)), ("k200_membership_rows", len(k200_mem)),
                         ("cmp_membership_rows", len(cmp_mem)),
                         ("mcap_spine_rows", len(spine_panel)),
                         ("flow_rows", len(flows)), ("earnings_rows", len(earn)),
                         ("consensus_ok", int(bool(getattr(cons, "ok", False)))))])
        p1 = os.path.join(outdir, "01_coverage_report.csv")
        cov.to_csv(p1, index=False, encoding="utf-8-sig")
        outs.append(p1)
        md = [f"# 입력 결손 진단 ({stamp})", "",
              "- STATUS: `INSUFFICIENT_INPUT_COVERAGE`",
              f"- universe_method: `{uni_meta.get('method')}`",
              f"- universe_missing_quarters: {uni_meta.get('missing')}",
              f"- mcap_spine_grades: {uni_meta.get('mcap_grades')}", "",
              "## 행 수", ""]
        md += [f"- {k}: {v:,}" for k, v in
               (("prices", len(px)), ("k200_membership", len(k200_mem)),
                ("cmp_membership", len(cmp_mem)), ("mcap_spine", len(spine_panel)),
                ("flows", len(flows)), ("earnings", len(earn)),
                ("factor_snapshots", 0 if snaps is None else len(snaps)))]
        md += ["", "## 다음 조치", "",
               "1. `01_coverage_report.csv` 에서 `valid_pct=0` 인 팩터를 찾습니다.",
               "2. F6/F7 이 0 이면 KRX 세션(또는 pykrx)이 없어 수급을 못 받은 것입니다 — "
               "상단 `KRX_MARKETPLACE_ID/PW` 를 채우세요.",
               "3. F1/F2/F3 이 0 이면 DART 키 또는 `corp_code` 매핑 문제입니다.",
               "4. F4/F5 가 0 이면 리서치 원장(한경/네이버 캐시)이 비어 있습니다.",
               "5. 스냅샷이 0행이면 시총 스파인부터입니다 — 로그의 "
               "'시총 스파인 발견 결과' 표에서 탐색 경로를 확인하고 "
               "`MARCAP_EXTRA_DIRS` 에 폴더를 추가하세요."]
        p2 = os.path.join(outdir, "00_DIAGNOSTIC.md")
        atomic_write_text(p2, "\n".join(md))
        outs.append(p2)
        for p in outs:
            VAULT.adopt(p, domain="report", subtype="diagnostic",
                        key=os.path.basename(p), source="v1.1 diagnostic dump",
                        scope="private")
        LOG.ok(f"진단 산출물 {len(outs)}개 저장 → {outdir}")
        offer_download(outs)
    except Exception as e:                                                  # noqa
        LOG.warn(f"진단 산출물 저장 실패({type(e).__name__}: {e}) — 로그 표만 참고하세요.")
    return outs


def _build_all_snapshots(sch: pd.DataFrame, membership: pd.DataFrame,
                         mcaps: Dict[pd.Timestamp, pd.DataFrame], earn: pd.DataFrame,
                         cons: "ConsensusStore", flows: pd.DataFrame,
                         label: str) -> pd.DataFrame:
    frames = []
    for _, r in sch.iterrows():
        sig = pd.Timestamp(r["signal_date"])
        mem = membership.loc[membership["signal_date"] == sig, "code"].tolist() \
            if membership is not None and len(membership) else []
        if not mem:
            LOG.warn(f"{sig:%Y-%m-%d} {label} 유니버스 멤버가 없습니다 — 이 분기는 건너뜁니다.")
            continue
        mc = mcaps.get(sig)
        frames.append(build_factor_snapshot(sig, mem, mc, earn, cons, flows))
    if not frames:
        return pd.DataFrame(columns=["signal_date", "code"] + FACTOR_NAMES)
    S = pd.concat(frames, ignore_index=True)
    PIPE.io("OUT", "MEM", f"factor_snapshots:{label}", S)
    return S


def _interpretation_tables(sr: StrategyRun, bt: dict, snaps: pd.DataFrame,
                           bench_daily: Optional[pd.Series], label: str) -> dict:
    """기타 해석표: 유니버스 감쇠, F5 소스 구성, 최고/최악 분기, 집중도, 팩터 기여."""
    out: Dict[str, Any] = {}
    LOG.banner(f"해석표 — {label}")
    att = []
    for sig, g in snaps.groupby("signal_date"):
        allv = g[FACTOR_NAMES].notna().all(axis=1)
        att.append({"q": pd.Timestamp(sig), "universe": len(g), "all7": int(allv.sum())})
    A = pd.DataFrame(att)
    if len(A):
        LOG.table([[f"{A['universe'].mean():.0f}", f"{A['all7'].mean():.0f}",
                    f"{100 * (A['all7'] / A['universe'].clip(lower=1)).mean():.1f}%",
                    f"{TOP_N}"]],
                  ["유니버스(평균)", "7팩터 유효(평균)", "유효비율", "선정"],
                  ["r", "r", "r", "r"], title="유니버스 감쇠 (분기 평균)")
        out["attrition"] = A
    if "f5_src" in snaps.columns:
        mix = snaps["f5_src"].replace("", "없음").value_counts()
        LOG.table([[k, f"{v:,}", f"{100 * v / len(snaps):.1f}%"] for k, v in mix.items()],
                  ["F5 입력원", "종목·분기", "비중"], ["l", "r", "r"],
                  title="F5(12MF EPS 1M 변화) 프록시 입력 구성")
    Q = bt.get("quarterly")
    if Q is not None and len(Q):
        qq = Q.sort_values("ret")
        LOG.table([[f"{pd.Timestamp(r.signal_date):%Y-%m}", f"{r.ret:+.1%}",
                    f"{r.turnover:.0%}", f"{r.n}"]
                   for r in pd.concat([qq.head(3), qq.tail(3)]).itertuples()],
                  ["분기", "수익", "회전율", "종목수"], ["c", "r", "r", "r"],
                  title="최악 3분기 / 최고 3분기")
    contrib = factor_contribution_table(bt.get("scored", pd.DataFrame()))
    if len(contrib):
        LOG.table([[r["factor"], r["grade"], f"{r['selected_mean_z']:+.2f}",
                    f"{r['contribution']:+.3f}"] for r in contrib.to_dict("records")],
                  ["팩터", "입력등급", "선정군 평균 z", "합성 기여"], ["l", "l", "r", "r"],
                  title="7팩터 기여 (선정 포트폴리오 평균 z / 7)")
        out["contribution"] = contrib
    conc = concentration_table(bt, SEC)
    if len(conc):
        LOG.table([[r["항목"], _trunc(r["값"], 60)] for r in conc.to_dict("records")],
                  ["항목", "값"], ["l", "l"], title="top30 집중도")
        out["concentration"] = conc
    return out


def main() -> dict:
    t_all = time.time()
    global VAULT, DBUDGET, SEC
    LOG.banner(f"{STRATEGY_NAME}  [{STRATEGY_ID}] v{BUILD_VERSION}",
               f"백테스트 {BACKTEST_START}~{BACKTEST_END} · 분기 리밸런스 · TOP{TOP_N} 동일가중 · "
               f"모드 {RUN_MODE}")
    LOG.table([["환경", "Colab" if ENV["colab"] else ("Jupyter" if ENV["ipython"] else "CLI")],
               ["파이썬", ENV["python"]],
               ["플랫폼", f"{ENV['platform']} / {ENV['cpu']}코어"],
               ["키 입력", f"KRX={'O' if KRX_MARKETPLACE_ID else 'X'} "
                          f"DART={'O' if DART_API_KEY else 'X'}"],
               ["병렬", f"IO {N_WORKERS_IO} 스레드 (연산은 벡터화)"],
               ["시드", str(SEED)]],
              ["항목", "값"], ["l", "l"], title="실행 환경")

    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결 (공용/전용 인덱스)", "L0"):
        root, mode, adopts = discover_roots()
        VAULT = Vault(root, mode)
        globals()["VAULT"] = VAULT
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {mode})")
        fg = free_gb(VAULT.root)
        if np.isfinite(fg):
            LOG.info(f"여유 공간 {fg:.1f} GB")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        if RUN_MODE != "SMOKE":
            VAULT.adopt_scan(adopts)
        DBUDGET = DartBudget()
        globals()["DBUDGET"] = DBUDGET

    vendor: dict = {"active": False, "status": "EXACT_COMPOSITE_NOT_PUBLICLY_IDENTIFIED",
                    "detail": ["판정 스테이지 실패 — 기본값 사용"], "coverage_rows": []}
    with PIPE.stage("L0.VENDOR", "EXACT_VENDOR_MODE 판정", "L0", critical=False):
        vendor = detect_exact_vendor_mode()

    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0"):
        if not run_smoke(full_outputs=(RUN_MODE == "SMOKE")):
            raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터는 RUN_MODE='FULL' 로 바꿔 실행하세요.")
        PIPE.report_stages()
        PIPE.report_runtime()
        return {"mode": "SMOKE"}

    # ══ L1 수집 ════════════════════════════════════════════════════════════════════════════
    with PIPE.stage("L1.UNI", "종목 마스터 (다중소스 · 폐지 포함)", "L1"):
        SEC = build_security_master()
        globals()["SEC"] = SEC

    # ★ v1.1 순서 역전 — 이 순서가 v1.0 병목의 근본 수정이다.
    #   v1.0: 가격(마스터 5,398종목 전량) → 시총 → 유니버스   ← 36분 중 대부분을 여기서 태웠다
    #   v1.1: 캐시·캘린더 → 시총 스파인 → 유니버스 확정 → **그 종목만** 가격
    with PIPE.stage("L1.CACHE", "캐시 일봉 로드 + 거래캘린더·리밸런스 부트스트랩", "L1"):
        if KRX_MARKETPLACE_ID and RUN_MODE != "CACHED":     # CACHED: network=0 약속 준수
            KRX.login()
        if _PYKRX_IMPORT_MSG:
            LOG.info(f"pykrx 로드 메시지: {_trunc(_PYKRX_IMPORT_MSG, 160)}")
        if pykrx_stock is None:
            LOG.warn("pykrx 를 쓸 수 없습니다 — 시총·지수구성·수급을 KRX 마켓플레이스 bld "
                     "직접호출로 대체합니다(동일 데이터). KRX ID/PW 가 비어 있으면 이 경로도 "
                     "막히니 상단 설정을 확인하세요.")
        pxc = load_price_cache()
        cal0 = bootstrap_calendar(pxc, BACKTEST_START, BACKTEST_END)
        sch0 = rebalance_schedule(cal0, BACKTEST_START, BACKTEST_END)
        if len(sch0) < 30:
            raise RuntimeError(
                f"리밸런스 일정이 {len(sch0)}개뿐입니다(정상 40개). 거래캘린더를 만들 수 있는 "
                f"소스가 없었습니다 — 캐시(krx_ohlcv_daily/marcap_YYYY)나 네트워크를 확인하세요.")

    with PIPE.stage("L1.SPINE", "시가총액 스파인 (6단 폴백 · 시점별 등급 기록)", "L1"):
        spine_panel = SPINE.build([pd.Timestamp(d) for d in sch0["signal_date"]], pxc=pxc)

    with PIPE.stage("L1.UNIV", f"유니버스 (재구성 K200 + 비교 하위{CMP_BOTTOM_N})", "L1"):
        k200_mem, cmp_mem, uni_meta = build_universes(sch0, spine_panel, SEC)
        uni_method = uni_meta["method"]
        need_codes = set(k200_mem["code"].astype(str)) if len(k200_mem) else set()
        if INCLUDE_COMPARISON and len(cmp_mem):
            need_codes |= set(cmp_mem["code"].astype(str))
        LOG.ok(f"가격이 필요한 종목 = 유니버스 합집합 {len(need_codes):,}개 "
               f"(마스터 {len(SEC):,}개 중 {100.0 * len(need_codes) / max(len(SEC), 1):.0f}%) — "
               f"v1.0 은 마스터 전체를 받았습니다.")

    with PIPE.stage("L1.PX", "일봉 (유니버스 한정 · 결손분만 · 절벽 분류보정)", "L1"):
        delist0 = {str(r.code): r.delisting_date for r in SEC.itertuples(index=False)
                   if pd.notna(getattr(r, "delisting_date", None))}
        px_start = (as_ts(BACKTEST_START)
                    - pd.DateOffset(months=PRICE_EXTRA_MARGIN_M)).strftime("%Y-%m-%d")
        px = fetch_prices(sorted(need_codes), px_start, BACKTEST_END, SEC, pxc, cal0, delist0)
        del pxc
        gc.collect()
        cal = trading_calendar(px)
        sch, _remap = realign_schedule(sch0, cal, BACKTEST_START, BACKTEST_END)
        if _remap:
            k200_mem = remap_signal_dates(k200_mem, _remap)
            cmp_mem = remap_signal_dates(cmp_mem, _remap)
            spine_panel = remap_signal_dates(spine_panel, _remap)
        # ★ 감사 치명(C2) 2단 방어 — 부트스트랩 캘린더가 못 봤던 분기가 가격 확보 후 새로
        #   생겼다면, 그 분기의 시총 스파인·유니버스를 '지금' 만들어 붙인다. 안 하면 그 분기는
        #   멤버십이 없어 조용히 현금 보유가 되고, uni_meta['missing'] 에도 안 잡혀
        #   커버리지 리포트조차 정상으로 보인다(10년 중 25%가 평평해진 채 통과).
        _known_yq = set(sch0["yq"]) if len(sch0) else set()
        _new = sch[~sch["yq"].isin(_known_yq)] if len(sch) else sch
        if len(_new):
            LOG.warn(f"가격 확보 후 새로 생긴 분기 {len(_new)}개 — 부트스트랩 캘린더가 "
                     f"놓쳤던 구간입니다. 이 분기의 시총·유니버스를 추가로 만듭니다: "
                     f"{list(_new['yq'])[:8]}")
            _sp2 = MarketcapSpine()
            _add_panel = _sp2.build([pd.Timestamp(d) for d in _new["signal_date"]], pxc=px)
            _k2, _c2, _m2 = build_universes(_new, _add_panel, SEC)
            spine_panel = pd.concat([spine_panel, _add_panel], ignore_index=True)
            k200_mem = pd.concat([k200_mem, _k2], ignore_index=True)
            if INCLUDE_COMPARISON:
                cmp_mem = pd.concat([cmp_mem, _c2], ignore_index=True)
            uni_meta["n_observed"] += _m2.get("n_observed", 0)
            uni_meta["n_reconstructed"] += _m2.get("n_reconstructed", 0)
            uni_meta["missing"] = list(uni_meta.get("missing", [])) + list(_m2.get("missing", []))
            for _g, _v in (_m2.get("mcap_grades") or {}).items():
                uni_meta["mcap_grades"][_g] = uni_meta["mcap_grades"].get(_g, 0) + _v
            uni_method = uni_meta["method"] = (uni_meta["method"]
                                              if uni_meta["method"] != "unavailable"
                                              else _m2.get("method", "unavailable"))
            need_codes |= set(_k2["code"].astype(str)) if len(_k2) else set()
            if INCLUDE_COMPARISON and len(_c2):
                need_codes |= set(_c2["code"].astype(str))
        if len(sch) < 30:
            LOG.warn(f"실제 거래캘린더 기준 리밸런스 분기가 {len(sch)}개입니다(정상 40개) — "
                     f"가격 구간이 짧습니다. 성과표의 '투자 분기'로 함께 확인하세요.")
        mcaps: Dict[pd.Timestamp, pd.DataFrame] = spine_snapshots(spine_panel)
        PIPE.io("OUT", "MEM", "mcap_snapshots", sum(len(v) for v in mcaps.values()))

    flows = pd.DataFrame(columns=["signal_date", "code", "inst_net", "forg_net"])
    with PIPE.stage("L1.FLOW", "기관·외국인 수급 20거래일 윈도우 (F6/F7)", "L1",
                    critical=False):
        flows = fetch_flow_windows(sch, cal)

    earn = pd.DataFrame(columns=["code", "period_end", "knowledge_date", "event_date",
                                 "ni_q", "ni_ttm", "op_q", "rev_q"])
    with PIPE.stage("L1.DART", "DART 분기실적 (배치·실시간 호출예산)", "L1", critical=False):
        years = list(range(as_ts(BACKTEST_START).year - 3, as_ts(BACKTEST_END).year + 1))
        need_codes = set(k200_mem["code"])
        if INCLUDE_COMPARISON and len(cmp_mem):
            need_codes |= set(cmp_mem["code"])
        c2corp = SEC.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str)
        corps = sorted({c2corp[c] for c in need_codes if c in c2corp.index})
        LOG.info(f"실적 필요 종목 {len(need_codes):,} → corp_code 매핑 {len(corps):,}")
        raw = fetch_dart_multi_accounts(corps, years)
        earn = tidy_dart_earnings(raw, SEC)

    cons = ConsensusStore(pd.DataFrame(), pd.DataFrame())
    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 원장 (한경+네이버, 캐시 우선)", "L1",
                    critical=False):
        rep, A, L = _collect_research(SEC)
        cons = ConsensusStore(L, px[["code", "date", "close"]])
        if not cons.ok:
            LOG.warn("컨센서스 스토어 비활성 — F4 는 결측, F5 는 DART 폴백만 사용됩니다.")

    # ══ L2 팩터 → L3 백테스트 → L6 성과 (계약 timed core) ═════════════════════════════════
    t_core = time.time()
    with PIPE.stage("L2.FACTOR", "7팩터 스냅샷 (본전략 K200)", "L2"):
        snaps = _build_all_snapshots(sch, k200_mem, mcaps, earn, cons, flows, "K200")
        allv = snaps[FACTOR_NAMES].notna().all(axis=1) if len(snaps) else pd.Series(dtype=bool)
        LOG.ok(f"스냅샷 {len(snaps):,}행 · 7팩터 전부 유효 {int(allv.sum()):,}행 "
               f"({100 * allv.mean() if len(snaps) else 0:.1f}%)")
        if len(snaps) and allv.sum() < TOP_N * 10:
            LOG.warn("7팩터 완전 유효 표본이 매우 적습니다 — 커버리지 리포트를 확인하세요. "
                     "(리서치/실적/수급 중 어느 입력이 비었는지가 원인입니다)")
        tot_gb = (mem_mb(px) + mem_mb(snaps)) / 1000.0
        if np.isfinite(tot_gb) and tot_gb > MEM_BUDGET_GB * 0.6:
            LOG.warn(f"상주 메모리 추정 {tot_gb:.1f}GB — MEM_BUDGET_GB({MEM_BUDGET_GB})의 "
                     f"60% 초과. 이후 단계는 보유종목 피벗만 쓰므로 통상 감소하지만, "
                     f"부족하면 INCLUDE_COMPARISON=False 로 낮추세요.")

    snaps_cmp = pd.DataFrame()
    if INCLUDE_COMPARISON and len(cmp_mem):
        with PIPE.stage("L2.FACTOR.CMP", f"7팩터 스냅샷 (비교: 시총 하위{CMP_BOTTOM_N})", "L2",
                        critical=False):
            snaps_cmp = _build_all_snapshots(sch, cmp_mem, mcaps, earn, cons, flows,
                                             "BOTTOM1000")
    else:
        PIPE.mark_skipped("L2.FACTOR.CMP", "비교전략 스냅샷", "L2",
                          "INCLUDE_COMPARISON=False 또는 비교 유니버스 없음")

    delist = {r.code: r.delisting_date for r in SEC.itertuples(index=False)
              if pd.notna(r.delisting_date)}

    with PIPE.stage("L3.BT", "백테스트 (본전략)", "L3"):
        sr = StrategyRun(RECON_LABEL, snaps, sch, px, delist)
        bt = sr.run(tag=RECON_LABEL)
        if not len(bt["quarterly"]):
            # ★ v1.1: 빈 결과여도 '진단 산출물을 먼저 저장하고' 멈춘다. v1.0 은 여기서 바로
            #   예외를 던져 커버리지 리포트조차 남기지 않았고, 사용자는 수십 분 수집 결과를
            #   전부 잃은 채 원인도 알 수 없었다.
            _dump_diagnostics(snaps, k200_mem, cmp_mem, spine_panel, flows, earn, cons,
                              uni_meta, vendor, px)
            # ★ v1.1.1: 입력을 어떤 소스로도 못 얻은 팩터가 있으면(실제로 KRX 차단으로
            #   F6/F7 이 전멸했다) 가용 팩터만으로 '진단용' 런을 함께 돌려 최소한 결과를 본다.
            #   계약 baseline 이 아니며 Primary 를 대체하지 않는다 — 라벨과 STATUS 로 못박는다.
            _dead = [f for f in FACTOR_NAMES
                     if len(snaps) and int(pd.to_numeric(snaps[f], errors="coerce")
                                           .notna().sum()) == 0]
            _alive = [f for f in FACTOR_NAMES if f not in _dead]
            if ALLOW_DEGRADED_DIAGNOSTIC and _dead and len(_alive) >= 3:
                LOG.banner(f"진단용 축소 런 — {len(_alive)}팩터",
                           "계약 baseline 아님 · Primary 대체 아님 · 라벨 분리")
                LOG.warn(f"입력을 확보하지 못한 팩터: {_dead}")
                LOG.warn(f"가용 팩터 {len(_alive)}개로만 계산한 결과를 별도 라벨"
                         f"({DEGRADED_LABEL})로 출력합니다. STATUS="
                         f"DEGRADED_FACTOR_SUBSET_NOT_CONTRACT_BASELINE")
                _btd = sr.run(drop_factor=_dead, tag=DEGRADED_LABEL)
                if len(_btd.get("quarterly", [])):
                    _bd = fetch_benchmark_k200(BACKTEST_START, BACKTEST_END)
                    _bds = None
                    if _bd is not None and len(_bd):
                        _s = _bd.set_index(as_ts_series(_bd["date"]))["close"].astype(float)
                        _bds = _s.sort_index().pct_change().dropna()
                    print_perf_block(f"진단용 축소 런 ({len(_alive)}팩터) — 계약 baseline 아님",
                                     perf_stats_daily(_btd["daily"], _btd["quarterly"], _bds))
                    globals()["_DEGRADED_BT"] = _btd
                    globals()["_DEGRADED_FACTORS"] = _alive
                    LOG.warn("★ 위 수치는 계약 baseline(7팩터 전부 유효)이 아닙니다. "
                             "결손 팩터의 입력을 확보한 뒤 재실행해야 Primary 가 나옵니다.")
            raise RuntimeError(
                "백테스트(계약 baseline)가 빈 결과를 냈습니다 — 전 분기에서 적격 종목이 "
                f"{MIN_ELIGIBLE}개 미만입니다.\n"
                "  위에 출력된 '입력 결손 진단' 표가 어느 입력이 비었는지 알려줍니다. "
                "진단 파일은 이미 드라이브에 저장되었습니다.")

    sr_cmp, bt_cmp = None, None
    if len(snaps_cmp):
        with PIPE.stage("L3.BT.CMP", "백테스트 (비교전략)", "L3", critical=False):
            sr_cmp = StrategyRun(CMP_LABEL, snaps_cmp, sch, px, delist)
            bt_cmp = sr_cmp.run(tag=CMP_LABEL)
    else:
        PIPE.mark_skipped("L3.BT.CMP", "비교전략 백테스트", "L3", "비교 스냅샷 없음")

    with PIPE.stage("L6.PERF", "성과 검증", "L6"):
        bench = fetch_benchmark_k200(BACKTEST_START, BACKTEST_END)
        bench_daily = None
        if len(bench):
            b = bench.set_index("date")["close"].astype(float).sort_index()
            bench_daily = b.pct_change().dropna()
        st_main = perf_stats_daily(bt["daily"], bt["quarterly"], bench_daily)
        print_perf_block(f"성과 검증표 — {RECON_LABEL} (Primary)", st_main)
        ann = annual_table(bt["daily"], bench_daily)
        if len(ann):
            LOG.table([[str(y)] + [f"{v:+.1%}" if isinstance(v, float) and np.isfinite(v)
                                   and c != "초과(%p)" else
                                   (f"{v:+.1f}" if isinstance(v, float) and np.isfinite(v)
                                    else "—") for c, v in row.items()]
                       for y, row in ann.iterrows()],
                      ["연도"] + list(ann.columns), ["c"] + ["r"] * len(ann.columns),
                      title="연도별 수익률")
        r12 = rolling12m_table(bt["daily"])
        if len(r12):
            LOG.table([[r["stat"], f"{r['rolling_12m']:+.1%}"] for r in r12.to_dict("records")],
                      ["롤링 12M", "값"], ["l", "r"])
        fwd = forward_returns_from_bt(sr)
        ic = factor_ic_table(snaps, fwd)
        if len(ic):
            LOG.table([[r["factor"], f"{r['IC_mean']:+.3f}" if np.isfinite(r["IC_mean"]) else "—",
                        f"{r['IC_t']:.2f}" if np.isfinite(r["IC_t"]) else "—",
                        f"{r['n_quarters']}"] for r in ic.to_dict("records")],
                      ["팩터", "IC 평균", "t", "분기수"], ["l", "r", "r", "r"],
                      title="팩터 IC (스피어만, 다음 분기 수익)")
        corr = factor_corr_table(snaps)
        if len(corr):
            LOG.table([[f] + [f"{corr.loc[f, g]:+.2f}" for g in FACTOR_NAMES]
                       for f in FACTOR_NAMES],
                      ["팩터"] + [f[:6] for f in FACTOR_NAMES],
                      ["l"] + ["r"] * len(FACTOR_NAMES), title="팩터 상관 (분기 평균 스피어만)")
        lofo = run_lofo(sr, bench_daily)
        if len(lofo):
            LOG.table([[r["dropped"], f"{r['CAGR']:+.2%}" if np.isfinite(r.get("CAGR", np.nan))
                        else "—", f"{r['dCAGR']:+.2%}" if np.isfinite(r.get("dCAGR", np.nan))
                        else "—"] for r in lofo.to_dict("records")],
                      ["제외 팩터", "CAGR", "ΔCAGR(vs 원형)"], ["l", "r", "r"],
                      title="leave-one-factor-out")
        # 원문 앵커(참고 전용 — 계약: 이 숫자에 맞춘 정규화 선택 금지)
        anchor_2022 = None
        try:
            D22 = bt["daily"][bt["daily"]["date"].dt.year == 2022]
            if len(D22) > 100 and bench_daily is not None:
                b22 = bench_daily[bench_daily.index.year == 2022]
                s_cum = float((1 + D22.set_index("date")["ret"]).prod() - 1)
                b_cum = float((1 + b22).prod() - 1)
                anchor_2022 = (s_cum - b_cum) * 100
                LOG.info(f"[참고] 2022 누적초과 {anchor_2022:+.1f}%p vs 원문 앵커 ≈ +52%p — "
                         f"차이는 프록시 입력·재구성 유니버스의 한계로 해석하며, 어떤 파라미터도 "
                         f"이 앵커에 맞추지 않았습니다.")
        except Exception:
            pass
        # 2022-4Q validation fixture 겹침 (신호로 사용 금지 — 보고만)
        fixture_overlap = None
        try:
            sig22 = [s for s in sch["signal_date"] if pd.Timestamp(s).year == 2022
                     and pd.Timestamp(s).month == 12]
            if sig22 and sr.scored_baseline is not None:
                pick22 = sr.scored_baseline[
                    (sr.scored_baseline["signal_date"] == sig22[0]) &
                    (sr.scored_baseline["selected"] == 1)]["code"]
                nm = SEC.set_index("code")["name"].astype(str)
                names22 = {norm_corp_name(nm.get(c, "")) for c in pick22}
                fixture_overlap = len(names22 & {norm_corp_name(x)
                                                 for x in VALIDATION_2022Q4_NAMES})
                LOG.info(f"[fixture] 2022-4Q 원문 공개 종목(발췌 {len(VALIDATION_2022Q4_NAMES)}개) "
                         f"대비 재구성 선정 겹침 {fixture_overlap}개 — 검증 전용.")
        except Exception:
            pass
        if bt_cmp is not None:
            st_cmp = perf_stats_daily(bt_cmp["daily"], bt_cmp["quarterly"], bench_daily)
            print_perf_block(f"성과 검증표 — {CMP_LABEL} (시총 하위{CMP_BOTTOM_N} 비교)", st_cmp)
            side = []
            for k in ("CAGR", "연변동성", "Sharpe", "MDD", "정보비율(IR)", "분기 적중률",
                      "분기평균 회전율(편도)", "분기평균 비용"):
                v1, v2 = st_main.get(k), st_cmp.get(k)
                f1s = f"{v1:+.2%}" if isinstance(v1, float) and np.isfinite(v1) and \
                    k not in ("Sharpe", "정보비율(IR)") else \
                    (f"{v1:.2f}" if isinstance(v1, float) and np.isfinite(v1) else "—")
                f2s = f"{v2:+.2%}" if isinstance(v2, float) and np.isfinite(v2) and \
                    k not in ("Sharpe", "정보비율(IR)") else \
                    (f"{v2:.2f}" if isinstance(v2, float) and np.isfinite(v2) else "—")
                side.append([k, f1s, f2s])
            LOG.table(side, ["지표", "본전략(K200)", f"비교(하위{CMP_BOTTOM_N})"],
                      ["l", "r", "r"], title="본전략 vs 비교전략 — 나란히 보기")
        else:
            st_cmp = {}

    rob, rob_cmp = pd.DataFrame(), pd.DataFrame()
    with PIPE.stage("L5.ROBUST", "강건성 검사", "L5", critical=False):
        rob = run_robustness(sr, bt, bench_daily)
        if sr_cmp is not None and bt_cmp is not None:
            rob_cmp = run_robustness(sr_cmp, bt_cmp, bench_daily, n_placebo=100)

    timed_core_s = time.time() - t_core

    with PIPE.stage("L6.INTERP", "해석표", "L6", critical=False):
        _interpretation_tables(sr, bt, snaps, bench_daily, RECON_LABEL)
        if bt_cmp is not None and len(snaps_cmp):
            _interpretation_tables(sr_cmp, bt_cmp, snaps_cmp, bench_daily, CMP_LABEL)

    outs: List[str] = []
    coverage = pd.DataFrame()
    with PIPE.stage("L0.PERSIST", "산출물 저장 (전용 인덱스) + 드라이브 재적재", "L0",
                    critical=False):
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(VAULT.ns["private"], "reports", f"run_{stamp}")
        extra_cov = [{"signal_date": "SOURCE", "factor": s, "grade": "input",
                      "n_universe": n, "n_valid": n, "valid_pct": 100.0}
                     for s, n in (("prices_rows", len(px)), ("earnings_rows", len(earn)),
                                  ("flow_rows", len(flows)),
                                  ("consensus_ok", int(cons.ok)))]
        extra_cov.append({"signal_date": "AUDIT", "factor": "px_cliff_gt50pct_days",
                          "grade": "audit", "n_universe": len(px),
                          "n_valid": int(globals().get("_PX_CLIFF_COUNT", 0)),
                          "valid_pct": np.nan})
        # ★ v1.1: 시총 스파인의 시점별 소스·정확도 등급을 산출물에 싣는다. '어느 분기의 시총이
        #   어떤 경로로 왔는지'를 나중에 재현·감사할 수 있어야 한다.
        for _k, _v in (globals().get("_PX_CLIFF_DETAIL", {}) or {}).items():
            extra_cov.append({"signal_date": "AUDIT", "factor": f"px_cliff_{_k}",
                              "grade": "audit", "n_universe": len(px), "n_valid": int(_v),
                              "valid_pct": np.nan})
        if len(spine_panel):
            for _sd, _g in spine_panel.groupby("signal_date"):
                extra_cov.append({
                    "signal_date": pd.Timestamp(_sd).strftime("%Y-%m-%d"),
                    "factor": f"MCAP_SPINE_{_g['src'].iloc[0]}",
                    "grade": str(_g["grade"].iloc[0]), "n_universe": len(_g),
                    "n_valid": int(pd.to_numeric(col(_g, "marcap"),
                                                 errors="coerce").notna().sum()),
                    "valid_pct": round(100.0 * pd.to_numeric(col(_g, "marcap"),
                                                            errors="coerce").notna().mean(), 1)})
        for _mq in uni_meta.get("missing", []):
            extra_cov.append({"signal_date": _mq, "factor": "UNIVERSE_MISSING",
                              "grade": "cash_quarter", "n_universe": 0, "n_valid": 0,
                              "valid_pct": 0.0})
        extra_cov.append({"signal_date": "SOURCE", "factor": "universe_method",
                          "grade": str(uni_meta.get("method", "")),
                          "n_universe": int(uni_meta.get("n_observed", 0)),
                          "n_valid": int(uni_meta.get("n_reconstructed", 0)),
                          "valid_pct": np.nan})
        if "f5_src" in snaps.columns and len(snaps):
            for sig_, g_ in snaps.groupby("signal_date"):
                mix = g_["f5_src"].replace("", "none").value_counts()
                for k_, v_ in mix.items():
                    extra_cov.append({"signal_date": pd.Timestamp(sig_).strftime("%Y-%m-%d"),
                                      "factor": f"F5_src_{k_}", "grade": "mix",
                                      "n_universe": len(g_), "n_valid": int(v_),
                                      "valid_pct": round(100.0 * v_ / len(g_), 1)})
        coverage = _coverage_report(snaps, vendor, extra_cov)
        perf_rows = [{"strategy": RECON_LABEL, "metric": k, "value": v}
                     for k, v in st_main.items()]
        perf_rows += [{"strategy": CMP_LABEL, "metric": k, "value": v}
                      for k, v in (st_cmp or {}).items()]
        # 계약 [성과] 항목의 기계가독 영속화 — 로그 전용이던 표들을 07 에 long 포맷으로 병합
        try:
            for y_, row_ in annual_table(bt["daily"], bench_daily).iterrows():
                for cn_, v_ in row_.items():
                    perf_rows.append({"strategy": RECON_LABEL,
                                      "metric": f"연간_{y_}_{cn_}", "value": v_})
            for r_ in rolling12m_table(bt["daily"]).to_dict("records"):
                perf_rows.append({"strategy": RECON_LABEL,
                                  "metric": f"롤링12M_{r_['stat']}",
                                  "value": r_["rolling_12m"]})
            for r_ in run_lofo(sr, bench_daily).to_dict("records"):
                perf_rows.append({"strategy": RECON_LABEL,
                                  "metric": f"LOFO_dCAGR_{r_['dropped']}",
                                  "value": r_.get("dCAGR")})
            for r_ in factor_contribution_table(bt.get("scored", pd.DataFrame())
                                                ).to_dict("records"):
                perf_rows.append({"strategy": RECON_LABEL,
                                  "metric": f"기여_{r_['factor']}",
                                  "value": r_["contribution"]})
            for r_ in concentration_table(bt, SEC).to_dict("records"):
                perf_rows.append({"strategy": RECON_LABEL,
                                  "metric": f"집중도_{r_['항목']}", "value": r_["값"]})
        except Exception as e_:                                     # noqa
            LOG.warn(f"성과 확장표 영속화 일부 실패({type(e_).__name__}) — 로그에는 있음.")
        trades = bt["quarterly"].copy()
        trades["strategy"] = RECON_LABEL
        if bt_cmp is not None and len(bt_cmp["quarterly"]):
            t2 = bt_cmp["quarterly"].copy()
            t2["strategy"] = CMP_LABEL
            trades = pd.concat([trades, t2], ignore_index=True)
        holds = bt["holdings"].copy()
        holds["strategy"] = RECON_LABEL
        if bt_cmp is not None and len(bt_cmp["holdings"]):
            h2 = bt_cmp["holdings"].copy()
            h2["strategy"] = CMP_LABEL
            holds = pd.concat([holds, h2], ignore_index=True)
        rob_all = rob.copy()
        rob_all["strategy"] = RECON_LABEL
        if len(rob_cmp):
            r2 = rob_cmp.copy()
            r2["strategy"] = CMP_LABEL
            rob_all = pd.concat([rob_all, r2], ignore_index=True)
        outs = write_outputs(outdir, {
            "coverage": coverage, "snaps": snaps,
            "scored": bt.get("scored", pd.DataFrame()), "holdings": holds, "trades": trades,
            "perf_table": pd.DataFrame(perf_rows), "ic_table": ic, "robust_table": rob_all,
            "vendor": vendor, "universe_def": "reconstructed_KOSPI200",
            "universe_method": uni_method, "timed_core_s": timed_core_s,
            "anchor_2022": anchor_2022, "fixture_overlap": fixture_overlap})
        # 전용 인덱스 재호출용 테이블 (다음 실행·다른 분석에서 즉시 재사용)
        VAULT.put_table(f"{STRATEGY_ID}_factor_snapshots", snaps, scope="private",
                        domain="features", source=RECON_LABEL)
        VAULT.put_table(f"{STRATEGY_ID}_portfolios", holds, scope="private",
                        domain="backtest", source=RECON_LABEL)
        VAULT.put_table(f"{STRATEGY_ID}_returns_daily", bt["daily"], scope="private",
                        domain="backtest", source=RECON_LABEL)
        if len(snaps_cmp):
            VAULT.put_table(f"{STRATEGY_ID}_factor_snapshots_cmp", snaps_cmp, scope="private",
                            domain="features", source=CMP_LABEL)
        if bt_cmp is not None and len(bt_cmp["daily"]):
            VAULT.put_table(f"{STRATEGY_ID}_returns_daily_cmp", bt_cmp["daily"],
                            scope="private", domain="backtest", source=CMP_LABEL)
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        if DBUDGET:
            DBUDGET.close()
        VAULT.report()

    PIPE.report_stages()
    PIPE.report_flow()
    report_http()
    KRXG.report()
    PIPE.report_runtime(timed_core_s=timed_core_s)
    LOG.banner("완료", f"총 {(time.time() - t_all) / 60:.1f}분 · STATUS={vendor['status']} · "
                       f"산출물 {len(outs)}개는 전용 인덱스({GDRIVE_PRIVATE_NS})에 저장")
    LOG.info("한계 명시: FnGuide 벤더 팩터 부재로 F1~F5 는 공개 프록시입니다. 이 결과는 "
             f"{RECON_LABEL} 이며 신한 원문 성과의 재현이 아닙니다. 상세는 "
             "10_exact_vs_reconstructed.md 참조.")
    offer_download(outs)
    return {"snaps": snaps, "backtest": bt, "backtest_cmp": bt_cmp, "robust": rob,
            "coverage": coverage, "outputs": outs}


if __name__ == "__main__" or ENV["ipython"]:
    try:
        RESULT = main()
    except StageFailure as e:
        LOG.banner("실행 중단", "위 '실패 지점' 상세와 아래 표에서 원인을 확인하세요")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단 — 여기까지 수집분은 드라이브에 저장되어 있으며 재실행 시 "
                 "이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
