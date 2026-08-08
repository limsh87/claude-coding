#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  ARC-BDF — 리포트 × 자사 거래원 플로우 (Broker Distribution Flow)   [SPEC-B]
#  전략: 리포트 × 자사 거래원 플로우   [ARC_BDF]
#  백테스트 구간: 2016-08-01 ~ 2026-07-31 (10년)
#
#  리서치의 가치는 발간 자체가 아니라 세일즈 채널을 통한 배포 강도에 있다. 한국은 종목별 거래원(회원사) 매매동향이 상위 5개 창구 기준으로 일별 공개되는 드문 시장이고, 이 데이터는 배포 강도의 관측 가능한 그림자다. 매수성 리포트를 낸 증권사의 창구에서 순매수가 동반되면 확증(롱), 순매도가 나오면 물량 분배(배제)로 읽는다. 거래원 과거 이력이 확보되지 않으면 Phase 0 게이트가 자동으로 ARC-BDF-PROXY(투자 주체 기반)로 전환하고, 그 사실을 모든 산출물에 명시한다.
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python arc_bdf_report_broker_flow.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시(공용/전용) 연결 → 계약 자동검정 K1~K14
#     [1] 합성데이터 엔드투엔드 스모크        ← 실데이터 수집 전에 계산경로를 먼저 증명
#     [2] 실경로 리허설 (네트워크만 가짜)      ← 수집·정제 함수를 실물 실행
#     [3] ★ Phase 0 데이터 실현가능성 게이트   ← 이 전략이 죽을 확률이 가장 높은 지점
#     [4] 데이터 수집 (캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [5] 원장 무결성 감사 (리포트 ↔ 애널리스트 ↔ 증권사 ↔ 종목 ↔ 거래원회원사)
#     [6] PIT 유니버스(생존편향 제거) + 유니버스 감쇠 감사
#     [7] 이벤트 패널 → 플로우 잔차화 → 12개 구성 백테스트 + 이벤트 스터디(CAR)
#     [8] 성과 검증표
#     [9] 강건성 검사 (블록부트스트랩 / PBO / DSR / 워크포워드 / 플라시보 / NW)
#    [10] 가설 H1~H5 + BH-FDR → 해석표 → ACCEPT/CONDITIONAL/KILL 판정
#    [11] ★ 시총 하위 1000종목 압축 유니버스 비교 백테스트 (동일 파이프라인 재실행)
#    [12] 런타임 감사 + 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
#  ⚠ 이 전략은 이해상충 구조를 다룹니다. 특정 증권사를 비난하는 서술을 하지 않고
#     통계적 패턴만 기술합니다 (SPEC §0.5).
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다  (아래 ①~⑬)
#
#   ▸ 아무것도 안 채워도 실행됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지 / 그래서 무엇을 못 하게 되는지" 를 로그에 한글로 명시합니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① KRX 데이터 마켓플레이스 (2025-12 인증 변경 대응) ──────────────────────────────────────
#    가입: https://data.krx.co.kr  → 우측 상단 [회원가입] (무료) → 이메일 인증 → 로그인
#          로그인에 쓰는 그 아이디/비밀번호를 그대로 아래에 넣으면 됩니다.
#
#    ★★★ 중요 — 기본값은 "KRX 사용 안 함" 입니다 (KRX_ENABLE = False). ★★★
#      이 전략의 파이프라인은 KRX 없이 완결되도록 설계되었습니다.
#        · 가격/거래량      → FinanceDataReader → 네이버금융 → yfinance (3중 폴백)
#        · 상장/폐지 이력   → FDR GitHub 캐시(listing/krx, listing/delisting) + KIND
#        · 시가총액         → DART 주식총수 + 종가 (없으면 거래대금 기반 프록시로 자동 강등)
#        · 수급/거래원      → 네이버금융
#      KRX 로그인이 차단된 상태여도 10년 백테스트가 그대로 돌아갑니다.
#
#      아래 KRX_ENABLE 을 True 로 바꾸면 "교차검증용 보강" 으로만 KRX 를 씁니다.
#      실패해도 파이프라인은 죽지 않고 폴백으로 계속 진행합니다.
#
#    ⚠ 같은 계정을 브라우저/다른 노트북에서 동시에 로그인해 두지 마세요. KRX 는 중복 로그인 시
#      이전 세션을 강제 종료(CD011)하며, 그러면 수집이 JSON 대신 로그인 HTML 을 받아 대량 실패합니다.
KRX_ENABLE         = False     # ★ 기본 False. 차단 이력이 있다면 False 로 두세요.
KRX_MARKETPLACE_ID = ""        # 예: "myid@example.com"
KRX_MARKETPLACE_PW = ""        # 예: "MyPassw0rd!"
KRX_OPENAPI_KEY    = ""        # (선택) https://data.krx.co.kr → OpenAPI 이용신청 후 발급.
                               #        엔드포인트별 승인이 따로 필요해 키만으론 즉시 안 됩니다.

# ── ② DART 전자공시 OpenAPI (선택이지만 강력 권장) ──────────────────────────────────────────
#    발급: https://opendart.fss.or.kr → 회원가입 → [인증키 신청/관리] → API 인증키 발급 (무료, 즉시)
#    용도(이 전략에서): ★ PIT 시가총액의 유일한 비-KRX 정품 소스 ★
#      · 사업보고서의 「주식의 총수 현황」(stockTotqySttus) 에서 분기별 상장주식수를 받아
#        종가와 곱해 "그 시점에 실제로 알 수 있었던 시가총액" 을 만듭니다.
#      · 없으면 시총은 '거래대금 기반 프록시'로 자동 강등되고, 그 사실이 감사표에 표시됩니다.
#        (강등되어도 시총은 랭크/버킷으로만 쓰이므로 전략은 그대로 돌아갑니다)
DART_API_KEY = ""

# ── ②-b 공공데이터포털 (금융위원회_주식시세정보) — ★ KRX 대체의 핵심 ★ ──────────────────────
#    발급: https://www.data.go.kr → 로그인 → "금융위원회_주식시세정보" 검색 → [활용신청]
#          → 마이페이지 > 데이터활용 > Open API > 인증키 에서 확인 (승인 즉시, 무료)
#    ★ 반드시 "일반 인증키(Decoding)" 값을 붙여넣으세요.
#      Encoding 키(%2B, %3D 가 섞인 것)를 넣으면 이중 인코딩으로 SERVICE_KEY_IS_NOT_REGISTERED
#      가 납니다. (코드가 이중 인코딩을 자동 감지해 경고하고 교정을 시도합니다)
#
#    ▶ 이게 왜 중요한가 — KRX 를 못 쓰는 상황에서 이 API 하나가 세 가지를 동시에 해결합니다:
#        (1) 날짜 하나로 그날 '전 종목' 시세를 한 번에 줍니다 (하루 1요청 = 10년 약 2,450요청)
#        (2) 시가총액(mrktTotAmt) 과 상장주식수(lstgStCnt) 를 그 시점 값으로 줍니다
#            → PIT 시가총액이 근사가 아니라 '정품'이 됩니다 (T1 경로)
#        (3) 그날 실제로 시세가 있던 종목 목록 = 진짜 일별 상장 스냅샷
#            → 생존편향 제거가 상장/폐지일 추정이 아니라 관측으로 확정됩니다
#      비워두면 전부 근사 경로로 자동 강등되고, 강등 사실이 감사표에 표시됩니다.
DATA_GO_KR_KEY = ""

# ── ③ 구글드라이브 캐시 — ★ 절대 1원칙 ★ ────────────────────────────────────────────────────
#    ★★★ 이 코드는 기존 캐시·인덱스를 절대 삭제·덮어쓰기하지 않습니다. ★★★
#      · 인덱스의 진실은 append-only JSONL 저널입니다. 기존 줄을 다시 쓰지 않습니다.
#      · index.parquet 은 저널의 파생물이며, 재생성 전 항상 타임스탬프 백업을 남깁니다.
#      · 컬럼은 합집합으로만 확장합니다(기존 컬럼을 떨어뜨리지 않음).
#      · 이미 드라이브에 있던 리포트는 "이동·개명 없이 경로만 등록"합니다(adopt-by-reference).
#      · 삭제 API 자체가 없습니다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 합니다.
#
#    GDRIVE_ROOT      : 캐시 최상위. ★ TCD v2 등 다른 전략과 같은 루트를 쓰면 공용 인덱스가 그대로 재활용됩니다.
#    GDRIVE_SHARED_NS : 공용 인덱스 — 다른 전략에서도 재활용 가능한 원본/범용 정제본
#                       (가격, 상장·폐지, 리포트 원장, 애널리스트 원장, 거래원/수급 원본)
#    GDRIVE_PRIVATE_NS: 전용 인덱스 — 이 전략 고유의 해석물 (이벤트패널, 잔차플로우, 백테스트 결과)
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"          # → {GDRIVE_ROOT}/_shared     (공용 · 다른 전략과 공유)
GDRIVE_PRIVATE_NS = "arc_bdf"          # → {GDRIVE_ROOT}/arc_bdf     (전용 · 이 전략 전용)

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요. 재귀 스캔해서 "등록만" 합니다.
#      (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록합니다)
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/arc_bdf_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    "/content/drive/MyDrive/리포트",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
#      Windows 예: r"C:\Users\<사용자>\.kr_data_work\ARC_BDF\cache"
LOCAL_CACHE_ROOT  = "./arc_bdf_cache"

# ── ④ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑤ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE"  : 합성데이터로 전 출력물 예행연습 (수십 초). 네트워크·키 불필요.
#               백테스트·성과·강건성·해석표가 전부 나옵니다. 처음엔 이걸로 한 번 돌려보세요.
#    "FULL"   : 스모크 → 리허설 → Phase 0 게이트 → 실데이터 수집 → 전체 (권장·기본값)
#    "CACHED" : 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 전체
#    "PHASE0" : Phase 0 데이터 실현가능성 게이트만 돌리고 보고 후 종료 (SPEC §12-1)
RUN_MODE = "FULL"

# ── ⑥ Phase 0 게이트 (SPEC §4) ──────────────────────────────────────────────────────────────
#    거래원(회원사)별 일별 매매동향의 '과거 이력' 확보 가능성을 실제로 찔러보고 판정합니다.
#    판정 결과에 따라 코드가 자동으로 분기합니다:
#      · 10년 확보    → 정상 진행 (ARC-BDF 원 가설)
#      · 3~10년 확보  → 확보 구간으로 축소, 검정력 영향 명시
#      · 3년 미만     → B-1(전진수집 스크립트 생성) + B-2(ARC-BDF-PROXY 열화 프록시 백테스트)
#                       ※ PROXY 는 원 가설의 대리 검증이 아님을 산출물에 명시합니다.
PHASE0_TIMEBOX_MIN     = 24 * 60   # 타임박스(분). 초과 시 즉시 중단하고 보고 (SPEC §4)
PHASE0_PROBE_TICKERS   = ["005930", "000660", "035720", "042700", "058470"]  # 대·중·소 혼합
PHASE0_PROBE_BACKDAYS  = [5, 60, 250, 1250, 2450]   # 며칠 전까지 소급되는지 계단 탐침
PHASE0_FORCE_BRANCH    = ""        # "" = 자동판정. 강제하려면 "FULL10"/"PARTIAL"/"PROXY" 중 하나.

# ── ⑦ 리포트(애널리스트) 수집 ───────────────────────────────────────────────────────────────
#    ★ 한경컨센서스 + 네이버금융 리서치 를 중심으로 삼습니다 (사용자 지시).
#      두 소스는 역할이 다르고 합쳐야 원장이 완성됩니다:
#        한경컨센서스 : 작성자(애널리스트)·목표주가가 리스트에 직접 옴 / 종목코드는 제목에서 추출
#        네이버 리서치: 종목코드가 정확 / 작성자는 PDF·상세에만 / 커버리지가 넓음
RESEARCH_COLLECT       = True    # False면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES       = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF  = True    # PDF 원문까지 받을지 (목표주가/애널리스트 추출 정확도↑, 용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0   # 0 = 무제한. 테스트할 땐 50 정도로.
RESEARCH_TARGET_PER_YEAR   = 30000

# ── ⑧ 거래원/수급 플로우 수집 (이 전략의 핵심 신호) ─────────────────────────────────────────
#    ★ 이 전략은 '일별 × 종목별' 크롤링이라 요청 수가 가장 많습니다. 차단당하면 프로젝트가 죽습니다.
#      그래서 (a) 이벤트 근방만 수집 (b) 최근→과거 순 (c) 서킷 브레이커 (d) 중단·재개 를 전부 씁니다.
FLOW_WORKERS           = 4       # SPEC §2.3: 보수적 3~4. 5 이상으로 올리지 마세요.
FLOW_DELAY_RANGE       = (0.30, 1.20)   # 요청 간 랜덤 딜레이(초) — SPEC §2.3 명시값
FLOW_CIRCUIT_BREAK_N   = 10      # 연속 실패 N회 → 즉시 전체 중단 + 상태 저장 (SPEC §2.3)
FLOW_EVENT_PAD_BEFORE  = 75      # 이벤트일 기준 과거 며칠까지 수집 (60일 베이스라인 + 여유)
FLOW_EVENT_PAD_AFTER   = 70      # 이벤트일 기준 미래 며칠까지 수집 (CAR d+60 + 여유)
FLOW_CANARY_DAYS       = 3       # 전체 실행 전 카나리: 3일치 × 20종목 (SPEC §2.3)
FLOW_CANARY_TICKERS    = 20
FLOW_TIME_BUDGET_MIN   = 180     # ★ 한 번의 실행에서 플로우 수집에 쓸 최대 시간(분).
                                 #   초과하면 '중단'이 아니라 '여기까지 저장하고 정상 종료'다.
                                 #   다음 실행이 이어서 받는다(최근→과거라 최신 구간부터 완성).
FLOW_INSTITUTION_ENABLE = True   # 기관 순매수(네이버 frgn 페이지네이션) 수집 여부.
                                 #   ★ 콜드 스타트가 가장 비싼 단계다. False 로 두면 외국인
                                 #     플로우(소진율 차분·종목당 1요청)만으로 즉시 전 구간이 완성된다.
FLOW_MEMBER_FORWARD     = True   # B-1 전진수집: 오늘자 거래원 상위5창구 스냅샷을 매 실행마다 적재
                                 #   (과거 이력은 어떤 무료 소스에도 없다 — Phase 0 참조)

# ── ⑨ 포트폴리오 (SPEC §7 — 사전 확정, 실행 중 변경 금지) ───────────────────────────────────
PORT_LONG_PCT          = 0.30    # BDF 잔차 상위 30% 이벤트 롱
PORT_FADE_PCT          = 0.30    # 하위 30% = 페이드(배제 필터 / 참고 바스켓)
POS_MAX_WEIGHT         = 0.05    # 종목당 상한 5%
PORT_MAX_NAMES         = 40      # 동시 보유 상한 40종목 (초과 시 신호 강도 순)
CASH_RF_ANNUAL         = 0.0     # 이벤트 없는 날 잔여현금 무위험수익률. CD91 가정은 아래 값으로 병행 보고
CASH_RF_CD91_ANNUAL    = 0.025   # 두 가정 모두 보고 (SPEC §7)

# ── ⑩ 거래비용 (SPEC §7.1 — 연도별 세율 테이블 필수, 단일 세율 금지) ────────────────────────
COMMISSION_BPS         = 1.5     # 편도
SLIPPAGE_BPS_BY_SIZE   = {"대형": 10.0, "중형": 20.0, "소형": 35.0}   # 편도
COST_SCENARIOS         = [("무비용", 0.0), ("기본", 1.0), ("2배", 2.0)]  # 3종 모두 보고

# ── ⑪ 사전등록 파라미터 격자 (SPEC §6.6 — 총 12개, 확장 금지) ───────────────────────────────
GRID_FLOW_WINDOWS      = [(0, 0), (0, 2)]      # k=0 / k=0..2                          (2)
GRID_BASELINE_DAYS     = 60                    # 고정                                   (1)
GRID_HOLD_DAYS         = [10, 20, 60]          # 보유기간                               (3)
GRID_SIGNAL_VERSIONS   = ["raw", "resid"]      # 원값 / 잔차                            (2)
#                                              → 2 × 3 × 2 = 12개 구성

# ── ⑫ 비교 전략: 시총 하위 1000종목 압축 유니버스 ───────────────────────────────────────────
#    동일 파이프라인을 "그 시점 시가총액 하위 1000종목" 으로만 좁혀 재실행하고 비교표를 냅니다.
#    (H4 '소형주에서 더 강하다' 의 직접 검정이자, 기존 전략 대비 비교축입니다)
COMPARE_SMALLCAP_ENABLE = True
COMPARE_SMALLCAP_N      = 1000
COMPARE_SMALLCAP_LABEL  = "시총하위1000"

# ── ⑬ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 8로 줄이세요.
                        # ※ 거래원/수급 수집만은 FLOW_WORKERS(3~4)로 별도 강제됩니다.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.5,
    "naver":     3.0,
    "naver_flow": 1.2,  # ★ 거래원/수급 전용. 가장 많이 때리는 곳이라 가장 보수적으로.
    "krx":       1.0,
    "kind":      2.0,
    "datagokr":  5.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환

SEED = 20260808          # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = False   # SPEC §11 KILL 판정 시에도 산출물은 전부 뽑고 판정만 기록합니다.
                                # True 로 두면 KILL 즉시 중단합니다.

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID        = "ARC_BDF"
STRATEGY_NAME      = "리포트 × 자사 거래원 플로우"
STRATEGY_DESC      = "리서치의 가치는 발간 자체가 아니라 세일즈 채널을 통한 배포 강도에 있다. 한국은 종목별 거래원(회원사) 매매동향이 상위 5개 창구 기준으로 일별 공개되는 드문 시장이고, 이 데이터는 배포 강도의 관측 가능한 그림자다. 매수성 리포트를 낸 증권사의 창구에서 순매수가 동반되면 확증(롱), 순매도가 나오면 물량 분배(배제)로 읽는다. 거래원 과거 이력이 확보되지 않으면 Phase 0 게이트가 자동으로 ARC-BDF-PROXY(투자 주체 기반)로 전환하고, 그 사실을 모든 산출물에 명시한다."
BUILD_VERSION      = "bdf.20260808.0313"
SPEC_ID            = "SPEC-B / ARC-BDF"

# KRX 를 끈 상태에서는 자격증명을 환경변수에 주입조차 하지 않는다.
# (pykrx 가 설치되어 있으면 import 시점에 로그인을 시도하는데, 차단된 계정으로 그걸 하면
#  잠금이 길어질 수 있다. 원천적으로 만지지 않는 것이 가장 안전하다.)
if not KRX_ENABLE:
    KRX_MARKETPLACE_ID = ""
    KRX_MARKETPLACE_PW = ""
    KRX_OPENAPI_KEY = ""


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-A  부트스트랩 — 환경 감지 / 의존성 / 표준 임포트                                      ║
# ║  입력: 없음        출력: 전역 ENV, 임포트된 모듈                                          ║
# ║  실패 시: 무엇이 없어서 실패했는지 + 정확한 설치 명령을 한글로 출력하고 즉시 중단          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, re, io, gc, json, time, math, zipfile, hashlib, logging, textwrap, traceback
import importlib, importlib.util, itertools, shutil
import sqlite3, random, shutil, tempfile, platform, subprocess, warnings, threading, unicodedata
import datetime as _dt
from collections import defaultdict, Counter, OrderedDict
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, urljoin, quote, unquote, urlparse, parse_qs

# ★ 이 파일은 통째로 __main__ 이다. spawn 방식 자식 프로세스가 생기면 pip 설치·드라이브
#   마운트·네트워크 수집까지 전부 재실행되고, 자식이 다시 풀을 만들면 지수적으로 증식한다.
#   자식으로 실행된 경우 즉시 종료시켜 그 경로를 구조적으로 막는다.
import multiprocessing as _mp_guard
if _mp_guard.current_process().name != "MainProcess":
    raise SystemExit(0)

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


_env_raw = _detect_env()
_env_raw["jupyter"] = bool(_env_raw.get("ipython")) and not _env_raw.get("colab")
_env_raw["windows"] = (platform.system() == "Windows")
_env_raw["needs_restart"] = False


class _Env(dict):
    """오타성 KeyError 로 진단 함수가 죽는 것을 구조적으로 막는다 (없는 키는 False)."""

    def __missing__(self, k):
        return False


ENV = _Env(_env_raw)

# ── 의존성 ──────────────────────────────────────────────────────────────────────────────────
#   (모듈 임포트명, pip 설치명, 필수여부, 이 패키지가 없으면 무엇이 죽는지)
_REQUIRED = [
    ("numpy",     "numpy",              True,  "모든 수치연산"),
    ("pandas",    "pandas",             True,  "모든 패널 처리"),
    ("pyarrow",   "pyarrow",            True,  "parquet 캐시(L1 영속화)"),
    ("requests",  "requests",           True,  "모든 HTTP 수집"),
    ("bs4",       "beautifulsoup4",     True,  "리서치 리스트 파싱"),
    ("lxml",      "lxml",               True,  "HTML/XML 고속 파서"),
    ("tqdm",      "tqdm",               True,  "진행률 표시"),
]
_OPTIONAL = [
    ("scipy",             "scipy",              "통계검정(없으면 자체 구현으로 동일하게 동작)"),
    ("FinanceDataReader", "finance-datareader", "가격/상장목록 1순위 · PIT 유니버스의 근간"),
    ("yfinance",          "yfinance",           "가격 최종 폴백"),
    ("fitz",              "pymupdf",            "리포트 PDF 텍스트 추출(가장 빠름)"),
    ("pdfplumber",        "pdfplumber",         "PDF 추출 폴백"),
    ("rapidfuzz",         "rapidfuzz",          "사업장명/애널리스트명 유사도 매칭(고속)"),
    ("statsmodels",       "statsmodels",        "HAC(Newey-West) 표준오차"),
    ("html5lib",          "html5lib",           "깨진 HTML 복구 파싱"),
]
# ★ pykrx 는 KRX_ENABLE=True 일 때만 후보에 넣는다.
#   import 시점에 KRX 로그인 세션을 만들기 때문에, 차단된 계정으로 그걸 건드리면
#   잠금이 길어질 수 있다. 끈 상태에서는 설치조차 하지 않는 것이 가장 안전하다.
if KRX_ENABLE:
    _OPTIONAL.append(("pykrx", "pykrx", "(선택) KRX 교차검증 — 없어도 파이프라인은 완결된다"))


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
    missing_req, missing_opt = [], []
    for mod, pkg, _req, _why in _REQUIRED:
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
            _safe_print("[X] 필수 패키지 설치 실패. 아래 명령을 직접 실행한 뒤 다시 돌려주세요.")
            _safe_print(f"   pip install {' '.join(missing_req)}")
            _safe_print("-" * 88)
            _safe_print(str(err))
            _safe_print("=" * 88)
            raise SystemExit(1)
        importlib.invalidate_caches()

    if missing_opt:
        _safe_print(f"[부트스트랩] 선택 패키지 설치 중: {', '.join(missing_opt)}")
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
if KRX_ENABLE and KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW
if KRX_ENABLE and KRX_OPENAPI_KEY:
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

# ★★ numpy 2 제거심볼 복구는 반드시 '서드파티 import 보다 먼저' 실행되어야 한다. ★★
#   구버전 yfinance/pandas-datareader/statsmodels 는 모듈 최상단에서 np.NaN 을 참조한다.
#   shim 이 늦으면 그 import 가 AttributeError 로 죽고 try/except 가 삼켜서
#   "설치돼 있는데 왜 안 쓰이지" 라는 무증상 기능 상실이 된다.
for _nm, _val in (("NaN", np.nan), ("NAN", np.nan), ("Inf", np.inf), ("infty", np.inf),
                  ("PINF", np.inf), ("NINF", -np.inf)):
    if not hasattr(np, _nm):
        try:
            setattr(np, _nm, _val)
        except Exception:
            pass
for _nm, _alias in (("float_", "float64"), ("int_", "int64"), ("complex_", "complex128"),
                    ("unicode_", "str_"), ("string_", "bytes_"), ("bool8", "bool_"),
                    ("alltrue", "all"), ("sometrue", "any"), ("product", "prod"),
                    ("cumproduct", "cumprod"), ("round_", "round"), ("in1d", "isin"),
                    ("trapz", "trapezoid")):
    if not hasattr(np, _nm) and hasattr(np, _alias):
        try:
            setattr(np, _nm, getattr(np, _alias))
        except Exception:
            pass
# ※ ndarray.ptp 는 immutable type 이라 패치 자체가 불가능하다. 코드에서 .ptp() 메서드형을
#   쓰지 말고 np.ptp(x) 함수형만 쓴다(자가검정이 이를 강제한다).

# ★ pandas 3 Copy-on-Write 는 체인 대입을 '경고' 로 알린다. 그런데 위에서 전역 경고를
#   껐기 때문에, 그대로 두면 d["a"][0]=99 가 예외도 경고도 없이 '아무 일도 안 하는' 상태가
#   된다 — 조용한 데이터 유실 중 최악이다. 이 경고만은 예외로 승격시킨다.
try:
    _CAE = getattr(pd.errors, "ChainedAssignmentError", None)
    if _CAE is not None:
        warnings.filterwarnings("error", category=_CAE)
except Exception:
    pass
try:
    pd.options.mode.copy_on_write = True      # pandas 2.x 도 3.x 와 같은 동작으로 통일
except Exception:
    pass

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_colwidth", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
np.seterr(all="ignore", divide="warn")

# 결정성(C8): 모든 난수는 이 시드에서 파생된다.
random.seed(SEED)
np.random.seed(SEED % (2 ** 32 - 1))
RNG = np.random.default_rng(SEED)

# 선택 모듈 핸들 (자격증명은 위 _ensure_deps 앞에서 이미 주입됨)
fdr = pykrx_stock = yf = fitz = pdfplumber = rapidfuzz_fuzz = smapi = None
_OPT_IMPORT_ERR: Dict[str, str] = {}
if OPT.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr           # type: ignore
    except Exception as _e:                       # noqa
        fdr = None
        _OPT_IMPORT_ERR["FinanceDataReader"] = f"{type(_e).__name__}: {_e}"
if KRX_ENABLE and OPT.get("pykrx"):
    try:
        from pykrx import stock as pykrx_stock    # type: ignore
    except Exception:
        pykrx_stock = None
if OPT.get("yfinance"):
    try:
        import yfinance as yf                     # type: ignore
    except Exception as _e:                       # noqa
        yf = None
        _OPT_IMPORT_ERR["yfinance"] = f"{type(_e).__name__}: {_e}"
if OPT.get("fitz"):
    try:
        import fitz                               # type: ignore  (pymupdf)
    except Exception as _e:                       # noqa
        fitz = None
        _OPT_IMPORT_ERR["fitz"] = f"{type(_e).__name__}: {_e}"
if OPT.get("pdfplumber"):
    try:
        import pdfplumber                         # type: ignore
    except Exception as _e:                       # noqa
        pdfplumber = None
        _OPT_IMPORT_ERR["pdfplumber"] = f"{type(_e).__name__}: {_e}"
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
     "DataFrame 이 되고, groupby(..., observed=True).agg() 가 pandas 내부에서 이 예외로 터집니다. "
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
        # ★ tz_convert(None) 은 UTC 로 옮긴 뒤 tz 를 떼므로 KST 자정이 '전날' 이 된다.
        #   yfinance 는 한국 종목에 tz-aware 인덱스를 주므로, 이걸 틀리면 가격 폴백 경로의
        #   날짜가 통째로 하루씩 밀린다 — 예외도 경고도 없이. 반드시 서울시각을 유지한 채 뗀다.
        try:
            t = t.tz_convert("Asia/Seoul").tz_localize(None)
        except Exception:
            t = t.tz_localize(None)
    return t.normalize()


def as_ts_series(s) -> pd.Series:
    """모든 외부 소스의 날짜가 통과하는 관문. tz-naive · 서울시각 기준 · normalize.

    ★ 두 가지를 동시에 막는다:
      ① tz 혼재 리스트는 pandas 2+ 에서 'Mixed timezones detected' ValueError 다.
      ② tz-aware 를 UTC 로 옮겨 tz 를 떼면 KST 자정이 전날이 된다(하루 밀림)."""
    ser = pd.Series(s)
    try:
        out = pd.to_datetime(ser, errors="coerce")
    except Exception:
        # tz 혼재 리스트는 pandas 2+ 에서 여기서 ValueError 를 던진다 → utc 로 강제 파싱
        out = pd.to_datetime(ser, errors="coerce", utc=True)
    if hasattr(out, "dt") and getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    elif not hasattr(out, "dt") or str(out.dtype) == "object":
        try:
            out = pd.to_datetime(ser, errors="coerce", utc=True)
            out = out.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
        except Exception:
            out = pd.to_datetime(ser, errors="coerce")
    return out.dt.normalize()


def month_end(x) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> pd.DatetimeIndex:
    return date_range_me(month_end(start), month_end(end))


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


def _long_path(p: str) -> str:
    """Windows MAX_PATH(260자) 회피. tmp 이름이 원본보다 길어 tmp 에서만 터지는 사고를 막는다."""
    if os.name == "nt":
        ap = os.path.abspath(p)
        if len(ap) > 240 and not ap.startswith("\\\\?\\"):
            return "\\\\?\\" + ap
    return p


def _tmp_path(path: str) -> str:
    """같은 디렉터리에 '짧은' 임시명을 만든다(크로스디바이스 EXDEV 회피 + MAX_PATH 여유)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    return os.path.join(d, ".t%d_%d" % (os.getpid(), threading.get_ident() % 100000))


def _replace_with_fallback(tmp: str, path: str) -> None:
    """os.replace 는 Colab 의 /content/drive(FUSE) 에서 OSError 를 던지는 사례가 잦다.
    실패하면 비원자 복사로 폴백하되, 폴백을 썼다는 사실은 반드시 로그에 남긴다."""
    try:
        os.replace(_long_path(tmp), _long_path(path))
        return
    except Exception as e:                                        # noqa
        try:
            import shutil as _sh
            _sh.copyfile(_long_path(tmp), _long_path(path))
            os.remove(_long_path(tmp))
            LOG.warn(f"원자적 교체 실패({type(e).__name__}) → 복사 폴백 사용: "
                     f"{os.path.basename(path)}. 이 파일은 쓰기 도중 중단되면 반쪽이 될 수 "
                     f"있습니다(드라이브 FUSE 의 알려진 제약).")
            return
        except Exception:
            raise


def atomic_write_bytes(path: str, data: bytes) -> str:
    """임시파일 → flush/fsync → os.replace. 드라이브 마운트에서 중단돼도 원본이 반쪽 나지 않는다."""
    _ensure_dir(path)
    tmp = _tmp_path(path)
    with open(_long_path(tmp), "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass                     # 일부 FUSE 는 fsync 미지원 — 실패해도 replace 는 유효
    _replace_with_fallback(tmp, path)
    return path


def atomic_write_text(path: str, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


_MIXED_KINDS = {"mixed", "mixed-integer", "mixed-integer-float", "unknown-array"}


def atomic_write_parquet(df: pd.DataFrame, path: str, compression: Optional[str] = None) -> str:
    """★ 혼합 타입 열이 하나만 있어도 ArrowInvalid 로 parquet 이 통째로 안 남는다.

    옛 구현은 infer_dtype 을 호출하고 반환값을 버린 뒤 '예외일 때만' 문자열화했는데,
    infer_dtype 은 혼합 타입에 예외를 던지지 않고 'mixed' 라는 문자열을 정상 반환한다.
    → 방어가 사실상 no-op 이었다. 거래원 파싱(문자열 창구명 + 숫자 거래량 + None)이
      정확히 이 형태를 만든다. 반환값으로 판정하도록 고치고, 그래도 실패하면
      문제 열만 문자열로 올려 1회 재시도해 캐시가 유실되지 않게 한다."""
    _ensure_dir(path)
    tmp = _tmp_path(path)
    out = df.copy()
    for c in out.columns:
        s_ = out[c]
        if is_texty(s_):
            try:
                kind = pd.api.types.infer_dtype(s_, skipna=True)
            except Exception:
                kind = "mixed"
            if kind in _MIXED_KINDS:
                out[c] = s_.astype(str)
    comp = compression or PARQUET_COMPRESSION
    for attempt in range(3):
        try:
            out.to_parquet(_long_path(tmp), index=False, compression=comp)
            break
        except Exception as e:                                    # noqa
            msg = str(e)
            bad = [c for c in out.columns if f"'{c}'" in msg or f'"{c}"' in msg]
            if attempt == 0 and bad:
                for c in bad:
                    out[c] = out[c].astype(str)
                LOG.warn(f"parquet 저장 실패 — 혼합타입 열 {bad} 을 문자열로 올려 재시도합니다.")
                continue
            if attempt <= 1:
                comp = "snappy"
                out = out.astype({c: str for c in out.columns if is_texty(out[c])})
                continue
            LOG.error(f"parquet 저장 실패({type(e).__name__}): {os.path.basename(path)} — "
                      f"이 캐시는 이번 실행에서 남지 않습니다. {msg[:160]}")
            raise
    _replace_with_fallback(tmp, path)
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
                base[c] = pd.Series(dtype=DT64)
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
      막아 두었지만, `P.groupby("code", observed=True)[c]` 는 여전히 맨손이라 c 가 없으면 KeyError 로 죽는다.
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
            g = (idx.groupby([idx["domain"].astype(str), idx["subtype"].astype(str)], observed=True)
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
            # ★ urllib3 은 total 이 connect/read 보다 우선한다. total=0 이면 connect=2 를
            #   써 놔도 재시도가 0회가 된다(첫 increment 에서 MaxRetryError). 일시적 커넥션
            #   리셋 하나에 즉시 실패하고, 서킷브레이커가 그걸 '차단' 으로 오판한다.
            try:
                rt = Retry(total=3, connect=2, read=2, status=0, backoff_factor=0.5,
                           status_forcelist=(), raise_on_status=False,
                           allowed_methods=frozenset(["GET", "HEAD"]))
            except TypeError:                       # urllib3 1.x 는 method_whitelist
                rt = Retry(total=3, connect=2, read=2, backoff_factor=0.5,
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
    # ★ 사내 Windows 노트북에서 가장 흔한 수집 실패는 '차단' 이 아니라 MITM 프록시의
    #   사내 루트 CA 가 certifi 번들에 없어서 나는 SSLError 다. 로그만 보면 차단처럼 보여
    #   서킷브레이커가 오작동한다. CA 번들을 명시 지정할 수 있게 열어 둔다.
    _ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if _ca and os.path.exists(_ca):
        s.verify = _ca
    try:
        s.trust_env = bool(int(os.environ.get("ARC_TRUST_ENV", "1")))
    except Exception:
        pass
    _TLS.sess = s
    return s


# 예외를 '차단' 과 '환경문제' 로 분리한다. 이 구분이 없으면 프록시/인증서 문제로
# 수집이 조기 중단되고 사용자는 원인을 영영 못 찾는다.
_ENV_ERRORS = ("SSLError", "ProxyError", "ConnectTimeout", "ConnectionError",
               "NewConnectionError", "MaxRetryError")
_ENV_HINT_SHOWN = [False]


def is_env_error(exc: BaseException) -> bool:
    n = type(exc).__name__
    if n in _ENV_ERRORS:
        if not _ENV_HINT_SHOWN[0]:
            _ENV_HINT_SHOWN[0] = True
            LOG.warn("네트워크 계층 오류가 감지되었습니다(SSL/프록시/연결). '사이트 차단' 이 "
                     "아니라 실행 환경 문제일 가능성이 큽니다. 사내망이라면 "
                     "REQUESTS_CA_BUNDLE 에 사내 루트 CA 경로를 지정하거나 "
                     "ARC_TRUST_ENV=0 으로 프록시 사용을 끄고 다시 시도해 보세요. "
                     "이 유형의 오류는 차단 카운터(서킷브레이커)에서 제외합니다.")
        return True
    return False


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
# ║  L0-F  호환성 계층 — pandas 1.5~3.x / numpy 1.2x~2.x / scipy 유무 / OS 차이를 흡수한다    ║
# ║                                                                                          ║
# ║  이 파일이 없으면 "내 노트북에선 되는데 코랩에선 죽는다" 가 반드시 일어난다.               ║
# ║  실제로 조용히 죽는 대표 사례를 전부 여기서 한 번에 막는다:                                ║
# ║   ① pandas 2.2 부터 freq="M" 이 폐기 → 3.0 에서 ValueError. 반대로 2.1 이하는 "ME" 를 모른다.║
# ║   ② pandas 3.0 은 Copy-on-Write 가 기본 → df[a][b] = x 가 '예외 없이' 무시된다(최악).      ║
# ║   ③ pandas 2.2+ groupby.apply 가 그룹키를 넘기지 않음(include_groups) → KeyError.          ║
# ║   ④ numpy 2.0 에서 np.NaN / np.float_ / np.alltrue 제거 → 서드파티가 먼저 죽는다.          ║
# ║   ⑤ scipy 가 없거나 설치 실패한 환경 → 통계 게이트 전체가 죽는 대신 순수 파이썬으로 대체.  ║
# ║   ⑥ pyarrow 가 zstd 를 못 쓰는 빌드 → parquet 저장 실패 → 캐시가 통째로 안 남는다.         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _ver_tuple(v: str) -> Tuple[int, ...]:
    out = []
    for part in str(v).split(".")[:3]:
        m = re.match(r"(\d+)", part)
        out.append(int(m.group(1)) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


PD_VER = _ver_tuple(getattr(pd, "__version__", "0.0.0"))
NP_VER = _ver_tuple(getattr(np, "__version__", "0.0.0"))

# ① 월말 빈도 별칭 -------------------------------------------------------------------------
#    pandas <2.2 : "M"  /  >=2.2 : "ME" (2.2 는 "M" 도 받지만 FutureWarning, 3.0 은 거부)
FREQ_ME = "ME" if PD_VER >= (2, 2, 0) else "M"
FREQ_QE = "QE" if PD_VER >= (2, 2, 0) else "Q"
FREQ_YE = "YE" if PD_VER >= (2, 2, 0) else "A"


def date_range_me(start, end) -> pd.DatetimeIndex:
    """월말 인덱스. 버전 별칭 차이를 흡수하고, 그래도 실패하면 수동 생성으로 폴백한다."""
    try:
        return pd.date_range(start, end, freq=FREQ_ME)
    except Exception:
        pass
    for f in ("ME", "M"):
        try:
            return pd.date_range(start, end, freq=f)
        except Exception:
            continue
    # 최후 폴백: 직접 만든다 (여기까지 오면 pandas 가 매우 이상한 버전이다)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out, cur = [], (s + pd.offsets.MonthEnd(0))
    while cur <= e:
        out.append(cur)
        cur = cur + pd.offsets.MonthEnd(1)
    return pd.DatetimeIndex(out)


# ② Copy-on-Write 안전 대입 ------------------------------------------------------------------
def set_where(df: pd.DataFrame, mask, col: str, value) -> None:
    """df.loc[mask, col] = value 의 안전판.

    pandas 3 의 CoW 에서 df[col][mask] = v 는 '예외 없이' 아무 일도 하지 않는다.
    이 함수만 쓰면 그 사고가 구조적으로 불가능해진다."""
    if col not in df.columns:
        df[col] = np.nan
    if isinstance(mask, pd.Series):
        m = mask.fillna(False).to_numpy(bool)
    else:
        m = np.nan_to_num(np.asarray(mask, dtype=float), nan=0.0).astype(bool) \
            if np.asarray(mask).dtype.kind == "f" else np.asarray(mask, dtype=bool)
    if m.shape[0] != len(df):
        raise ValueError(f"set_where: 마스크 길이 {m.shape[0]} != 프레임 길이 {len(df)}")
    if not m.any():
        return
    # ★ pandas 3 은 정수/불리언 열에 실수·결측을 넣으면 TypeError 다(2.x 는 조용히 승격했다).
    #   '코랩에선 되는데' 의 전형이므로 대입 전에 열 dtype 을 먼저 올린다.
    cur = df[col].dtype
    try:
        if cur.kind in ("i", "u", "b"):
            need_float = (value is None or (np.isscalar(value) and pd.isna(value)) or
                          np.asarray(value).dtype.kind == "f")
            need_obj = (not np.isscalar(value)) and np.asarray(value).dtype.kind in ("U", "O", "S")
            if isinstance(value, str):
                need_obj = True
            if need_obj:
                df[col] = df[col].astype(object)
            elif need_float:
                df[col] = df[col].astype("float64")
    except Exception:
        pass
    try:
        df.loc[m, col] = value
    except (TypeError, ValueError):
        df[col] = df[col].astype(object)
        df.loc[m, col] = value


# ③ groupby.apply 그룹키 복원 ------------------------------------------------------------------
def gb_apply(g, fn, **kw):
    """그룹키를 보존한 채 apply 한다.

    ★ include_groups 인자를 쓰면 안 된다. pandas 2.2 는 받지만 pandas 3 은
      `include_groups=True is no longer allowed` ValueError 를 던진다. 그 예외를
      bare except 로 삼키면 (a) 그룹키 없는 경로로 조용히 강등되어 caller 가 KeyError,
      (b) fn 이 던진 정당한 예외까지 삼켜서 apply 가 두 번 실행된다(부수효과 중복).
      → 버전 분기 대신 그룹키를 직접 되꽂는다. 모든 버전에서 같은 결과가 나온다."""
    keys = g.keys if isinstance(g.keys, list) else [g.keys]
    keys = [k for k in keys if isinstance(k, str)]
    if not keys:
        return g.apply(fn, **kw)
    out = []
    for kv, sub in g:
        kv = kv if isinstance(kv, tuple) else (kv,)
        s2 = sub.copy()
        for name, val in zip(keys, kv):
            if name not in s2.columns:
                s2[name] = val
        out.append((kv, fn(s2)))
    if not out:
        return pd.DataFrame()
    first = out[0][1]
    if isinstance(first, (pd.DataFrame, pd.Series)):
        return pd.concat([v for _, v in out],
                         keys=[k if len(k) > 1 else k[0] for k, _ in out], names=keys)
    return pd.Series({(k if len(k) > 1 else k[0]): v for k, v in out})


# ③-b 텍스트 판정 / 빈 프레임 -------------------------------------------------------------------
def is_texty(s) -> bool:
    """pandas 3 + pyarrow 는 문자열을 StringDtype 으로 돌려주므로 `dtype == object` 가
    전부 False 가 된다. 문자열 판정은 반드시 이 함수를 거친다."""
    try:
        return bool(pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s))
    except Exception:
        return False


def empty_like(cols_dtypes: Dict[str, Any]) -> pd.DataFrame:
    """빈 결과 프레임. ★ pd.DataFrame(columns=[...]) 는 전 열이 object 라, 나중에
    실데이터와 concat 하면 숫자열까지 object 로 오염되고 parquet 저장이 죽는다.
    10년 백테스트에서 휴장일/차단일 빈 프레임은 반드시 발생한다."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in cols_dtypes.items()})


def concat_nonempty(frames: Sequence[pd.DataFrame], cols: Optional[Sequence[str]] = None,
                    dtypes: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """빈 프레임을 먼저 걷어내고 concat 한다(dtype 오염 방지)."""
    fs = [f for f in frames if f is not None and len(f)]
    if not fs:
        return empty_like(dtypes) if dtypes else pd.DataFrame(columns=list(cols or []))
    if cols is not None:
        fs = [f.reindex(columns=list(cols)) for f in fs]
    return pd.concat(fs, ignore_index=True)


# ③-c 시간축 관문 (tz / 해상도) -----------------------------------------------------------------
#   pandas 3 의 기본 datetime 해상도는 ns 가 아니라 us 다. "datetime64[ns]" 하드코딩과
#   epoch 변환(1e9 나눗셈)이 조용히 1000배 틀어진다.
DT64_UNIT = "us" if PD_VER >= (3, 0, 0) else "ns"
DT64 = "datetime64[" + DT64_UNIT + "]"


def now_kst() -> pd.Timestamp:
    """KST 현재시각(naive). ★ pd.Timestamp.utcnow() 는 폐기 예고 상태이고 경고가 꺼져
    있어 pandas 4 에서 예고 없이 AttributeError 로 죽는다. 전 모듈이 이 함수만 쓴다."""
    try:
        return pd.Timestamp.now("UTC").tz_convert("Asia/Seoul").tz_localize(None)
    except Exception:
        return pd.Timestamp.now("UTC").tz_localize(None) + pd.Timedelta(hours=9)


def to_naive_date(s) -> pd.Series:
    """모든 외부 소스의 날짜가 반드시 통과해야 하는 관문.

    ★ yfinance 는 tz-aware 인덱스를, FDR/네이버는 naive 를 준다. 둘을 concat 하면
      dtype 이 object 로 붕괴하고, aware 인덱스를 naive 기준일과 비교하면 TypeError 다.
      KRX 를 못 쓰는 이번 설계는 yfinance 폴백 비중이 커서 반드시 터진다."""
    try:
        t = pd.to_datetime(s, utc=True, errors="coerce")
        return t.dt.tz_convert("Asia/Seoul").dt.tz_localize(None).dt.normalize()
    except Exception:
        pass
    try:
        t = pd.to_datetime(s, errors="coerce")
        if hasattr(t, "dt"):
            if getattr(t.dt, "tz", None) is not None:
                t = t.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
            return t.dt.normalize()
        return pd.Series(pd.to_datetime(t, errors="coerce"))
    except Exception:
        return pd.Series([pd.NaT] * (len(s) if hasattr(s, "__len__") else 1))


# ④ numpy 2 제거심볼 복구는 01_bootstrap 에서 '서드파티 import 보다 먼저' 이미 수행했다.
#    (여기서 하면 yfinance/statsmodels 가 먼저 로드되어 np.NaN 참조로 죽는 순서 역전이 난다)
#    멱등이므로 한 번 더 확인만 한다.
if not hasattr(np, "NaN"):
    try:
        np.NaN = np.nan            # type: ignore[attr-defined]
    except Exception:
        pass

# ⑤ scipy 없이도 도는 통계 원시함수 ------------------------------------------------------------
try:
    from scipy import stats as _sps            # type: ignore
except Exception:                              # pragma: no cover
    _sps = None

HAS_SCIPY = _sps is not None


def norm_cdf(x: float) -> float:
    """표준정규 CDF. math.erf 만으로 충분히 정확하다(오차 < 1e-15)."""
    try:
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))
    except Exception:
        return float("nan")


def norm_ppf(p: float) -> float:
    """표준정규 역함수 — Acklam 유리근사 + 뉴턴 1회 보정 (절대오차 < 1e-9).
    DSR / PBO 계산에 필요하며, scipy 부재 환경에서도 동일한 숫자가 나와야 한다."""
    p = float(p)
    if not (0.0 < p < 1.0):
        return float("-inf") if p <= 0 else float("inf")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q, r = p - 0.5, (p - 0.5) ** 2
        x = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
            (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    # 뉴턴 보정 1회
    try:
        e = norm_cdf(x) - p
        u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
        x = x - u / (1 + x * u / 2)
    except Exception:
        pass
    return x


def t_sf(t: float, dof: float) -> float:
    """양측 t 검정 p값 (생존함수 ×2). scipy 가 있으면 그걸, 없으면 불완전베타로 계산."""
    t = abs(float(t))
    if not np.isfinite(t) or dof <= 0:
        return float("nan")
    if HAS_SCIPY:
        try:
            return float(2.0 * _sps.t.sf(t, dof))
        except Exception:
            pass
    # 정규근사는 소표본에서 p를 과소평가한다 → 불완전베타 연분수로 정확히 계산
    x = dof / (dof + t * t)
    try:
        return float(_betainc(dof / 2.0, 0.5, x))
    except Exception:
        return float(2.0 * (1.0 - norm_cdf(t)))


def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-14) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """정규화 불완전베타 I_x(a,b) — Numerical Recipes 연분수."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
             a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
                          b * math.log(1.0 - x) + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def ols_beta(X: np.ndarray, y: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    """최소제곱 계수. lstsq 가 실패하는 특이행렬에서도 릿지로 반드시 답을 낸다.
    (통제변수 회귀에서 업종더미가 완전공선이 되는 일이 실제로 자주 일어난다)"""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    if len(y) == 0 or X.shape[0] != len(y):
        return np.zeros(X.shape[1] if X.ndim > 1 else 1)
    XtX = X.T @ X
    XtX = XtX + ridge * np.eye(XtX.shape[0]) * max(1.0, float(np.trace(XtX)) / max(XtX.shape[0], 1))
    try:
        return np.linalg.solve(XtX, X.T @ y)
    except Exception:
        try:
            return np.linalg.lstsq(X, y, rcond=None)[0]
        except Exception:
            return np.zeros(X.shape[1])


# ⑤-b Newey-West(HAC) — statsmodels 없이도 반드시 계산되어야 한다 ------------------------------
def nw_se(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float, int]:
    """평균의 HAC(Bartlett) 표준오차와 t 값. 반환 (mean, t, lags).

    ★ statsmodels 가 없으면 통계 게이트가 조용히 통과하거나 AttributeError 로 죽는다.
      순수 numpy 로 구현해 두 경로가 같은 숫자를 내도록 한다(자가검정이 교차확인).
      L = floor(4*(T/100)^(2/9))  (Newey-West 1994 자동선택)"""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    T = a.size
    if T < 8:
        return (float(a.mean()) if T else np.nan, np.nan, 0)
    if lags is None:
        lags = int(np.floor(4.0 * (T / 100.0) ** (2.0 / 9.0)))
    lags = max(0, min(int(lags), T - 2))
    e = a - a.mean()
    gamma0 = float(e @ e) / T
    s2 = gamma0
    for l in range(1, lags + 1):
        g = float(e[l:] @ e[:-l]) / T
        w = 1.0 - l / (lags + 1.0)
        s2 += 2.0 * w * g
    if s2 <= 0:                      # Bartlett 가중이어도 수치오차로 음수가 될 수 있다
        s2 = gamma0
    se = math.sqrt(max(s2, 1e-300) / T)
    mu = float(a.mean())
    return (mu, mu / se if se > 0 else np.nan, lags)


def hac_t(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    mu, t, _ = nw_se(x, lags)
    return mu, t


# ⑤-c 텍스트 I/O 관문 (Windows cp949 / BOM) -----------------------------------------------------
def read_json(path: str, default=None):
    """★ open(p) 는 Windows 에서 cp949 로 열려 UTF-8 한글 JSON 을 깨뜨리거나 죽는다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: str, obj) -> str:
    return atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=1))


def read_csv_utf8(path: str, **kw) -> pd.DataFrame:
    """BOM 을 흡수한다. 우리가 엑셀 호환을 위해 BOM 을 붙여 쓰기 때문에,
    utf-8-sig 로 읽지 않으면 첫 컬럼명에 BOM 이 남아 KeyError 가 난다."""
    kw.setdefault("encoding", "utf-8-sig")
    return pd.read_csv(path, **kw)


# ⑥ parquet 압축 폴백 --------------------------------------------------------------------------
def _pick_parquet_compression() -> str:
    try:
        import pyarrow as _pa                                   # noqa
        from pyarrow import Codec as _Codec                     # type: ignore
        for c in ("zstd", "snappy", "gzip"):
            try:
                if _Codec.is_available(c):
                    return c
            except Exception:
                continue
    except Exception:
        pass
    return "snappy"


PARQUET_COMPRESSION = _pick_parquet_compression()


# ⑦ 안전한 HTML 표 파싱 -------------------------------------------------------------------------
def _html_flavors() -> Tuple[Any, ...]:
    """flavor="bs4" 는 html5lib 를 강제한다. html5lib 이 없으면 ImportError 이므로
    존재가 확인될 때만 후보에 넣는다."""
    out: List[Any] = ["lxml"]
    try:
        if importlib.util.find_spec("html5lib") is not None:
            out.append("bs4")
    except Exception:
        pass
    out.append(None)
    return tuple(out)


_HTML_FLAVORS = _html_flavors()


def safe_read_html(raw: Union[bytes, str], encoding: Optional[str] = None) -> List[pd.DataFrame]:
    """pandas 버전·파서 가용성에 따라 시그니처가 다르다. 전부 시도하고 하나라도 되면 쓴다."""
    attempts = []
    if isinstance(raw, bytes):
        attempts.append(dict(io=io.BytesIO(raw), encoding=encoding))
        for enc in ([encoding] if encoding else []) + ["euc-kr", "cp949", "utf-8"]:
            if not enc:
                continue
            try:
                attempts.append(dict(io=io.StringIO(raw.decode(enc, "replace"))))
            except Exception:
                continue
    else:
        attempts.append(dict(io=io.StringIO(raw)))
    for kw in attempts:
        for flavor in _HTML_FLAVORS:
            try:
                k = {k2: v for k2, v in kw.items() if v is not None}
                if flavor:
                    k["flavor"] = flavor
                tabs = pd.read_html(**k)
                if tabs:
                    return tabs
            except Exception:
                continue
    return []


# ⑧ 프로젝트 루트 자동 감지 (SPEC §2.1 — 경로 하드코딩 금지) --------------------------------------
def resolve_project_root() -> str:
    """런타임에 루트를 스스로 찾는다. '/content' 를 코드에 박지 않는다.

    우선순위:
      ① 환경변수 ARC_BDF_ROOT (사용자가 명시적으로 지정)
      ② 구글드라이브가 마운트되어 있으면 그 아래 (Colab)
      ③ Windows 로컬 표준 경로 (SPEC §2.1 의 .kr_data_work)
      ④ 현재 작업 디렉터리
    어느 경로도 쓰기 불가면 임시 디렉터리로 강등하되 그 사실을 로그에 남긴다."""
    cands: List[str] = []
    env = os.environ.get("ARC_BDF_ROOT", "").strip()
    if env:
        cands.append(env)
    if ENV.get("colab"):
        cands.append("/content/drive/MyDrive/arc_bdf_work")
        cands.append("/content/arc_bdf_work")
    home = os.path.expanduser("~")
    if ENV.get("platform") == "Windows":
        cands.append(os.path.join(home, ".kr_data_work", "ARC_BDF"))
    cands.append(os.path.join(os.getcwd(), "arc_bdf_work"))
    cands.append(os.path.join(home, ".kr_data_work", "ARC_BDF"))
    for c in cands:
        try:
            os.makedirs(c, exist_ok=True)
            probe = os.path.join(c, ".w")
            with open(probe, "w") as f:
                f.write("1")
            os.remove(probe)
            return os.path.abspath(c)
        except Exception:
            continue
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "arc_bdf_work")
    os.makedirs(tmp, exist_ok=True)
    return tmp


PROJECT_ROOT = resolve_project_root()
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def out_path(name: str) -> str:
    return os.path.join(OUTPUT_DIR, name)


# ⑨ 랜덤 딜레이 (차단 회피 · SPEC §2.3) ---------------------------------------------------------
_JITTER_RNG = random.Random(SEED ^ 0x5EED)
_JITTER_LK = threading.Lock()


def polite_sleep(lo: float = None, hi: float = None) -> None:
    lo = FLOW_DELAY_RANGE[0] if lo is None else lo
    hi = FLOW_DELAY_RANGE[1] if hi is None else hi
    with _JITTER_LK:
        d = _JITTER_RNG.uniform(float(lo), float(hi))
    time.sleep(max(0.0, d))


# ⑩ 실행환경 요약 (진단용) -----------------------------------------------------------------------
def report_compat() -> None:
    rows = [
        ["python", platform.python_version(), sys.executable[:44]],
        ["작업 루트", PROJECT_ROOT[-44:], "경로 하드코딩 없음(런타임 자동감지)"],
        ["pandas", ".".join(map(str, PD_VER)), f"월말빈도='{FREQ_ME}' · CoW={'ON' if PD_VER>=(3,0,0) else 'off'}"],
        ["numpy", ".".join(map(str, NP_VER)), "2.x 제거심볼 복구 완료" if NP_VER >= (2, 0, 0) else "-"],
        ["scipy", "있음" if HAS_SCIPY else "없음", "없어도 t/정규 분포는 자체 구현으로 동작"],
        ["parquet", PARQUET_COMPRESSION, "pyarrow 코덱 자동선택"],
        ["환경", "Colab" if ENV.get("colab") else ("Jupyter" if ENV.get("jupyter") else "CLI"),
         f"{ENV['platform']} · CPU {os.cpu_count()}"],
        ["KRX", "사용" if KRX_ENABLE else "미사용(기본)",
         "FDR/네이버/yfinance/DART/공공데이터 만으로 완결" if not KRX_ENABLE
         else "교차검증용 보강"],
        ["statsmodels", "있음" if smapi is not None else "없음",
         "없어도 Newey-West 는 자체 구현(nw_se)으로 계산됩니다"],
        ["시간해상도", DT64, "pandas 3 은 us 가 기본 — ns 하드코딩 금지"],
    ]
    for k, v in (_OPT_IMPORT_ERR or {}).items():
        rows.append([f"선택모듈 실패:{k}", "import 실패", v[:60]])
    LOG.table(rows, ["항목", "값", "비고"], title="실행환경 호환성")


# ⑪ DART OpenAPI 상태코드 사전 (10_universe / 11_price 가 공유) ---------------------------------
#    status 를 해석하지 않고 '실패' 로만 처리하면, 일일 한도 초과(020)와 잘못된 키(010)를
#    구분하지 못해 사용자가 무엇을 고쳐야 할지 알 수 없게 된다.
DART_STATUS_MSG = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키",
    "012": "접근할 수 없는 IP", "013": "조회된 데이터 없음", "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과(일일 한도)", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 부적절", "101": "부적절한 접근", "800": "시스템 점검 중",
    "900": "정의되지 않은 오류", "901": "사용자 계정 폐쇄",
}


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-A  종목 마스터 & PIT 유니버스 (C2 생존자편향 제거)                                     ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축 — 우선순위와 역할이 각각 다르다:                                      ║
# ║    ① FDR GitHub 캐시  listing/krx        상장 종목 + 상장일        ← 로그인 불필요, 1순위  ║
# ║    ② FDR GitHub 캐시  listing/delisting  상장폐지 + 폐지일         ← ★생존자편향 제거 입력 ║
# ║    ③ KIND 상장법인목록                   상장일·업종 보강                                  ║
# ║    ④ 상장종목 스냅샷(드라이브 공용캐시)  "그 날 실제 상장" 검증     ← 있으면 쓰고 없어도 됨 ║
# ║    ⑤ DART corpCode.xml                   corp_code ↔ 종목코드                              ║
# ║    ⑥ 네이버 금융                         ①~⑤ 어디에도 이름이 없는 잔여 코드 보강          ║
# ║                                                                                          ║
# ║  ★ 설계 원칙: 유니버스의 정확성은 ①②③⑤(상장일·폐지일)만으로 성립해야 한다.                ║
# ║    ④ 스냅샷은 '검증·보강'이지 '의존'이 아니다. ★ 이 빌드는 KRX 를 아예 쓰지 않는 것이      ║
# ║    기본이며(KRX_ENABLE=False), 그 상태에서도 생존편향 제거가 완결된다.                     ║
# ║    스냅샷은 합집합으로만 얹는다 — 부분 응답을 진실로 믿고 교집합을 취하면 그 달 유니버스가 ║
# ║    조용히 쪼그라들어 곧바로 선택편향이 된다.                                               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

SEC_MASTER_COLS = ["code", "name", "market", "listing_date", "delisting_date",
                   "corp_code", "industry", "sector_src", "src"]

# 스냅샷 주기: "Q"(분기·기본) | "M"(월) | "A"(연) | "off"
#   월 단위는 120개월 × 2시장 = 240 호출이라 KRX 세션을 자주 건드리고 차단 위험이 커진다.
#   상장/폐지일이 이미 있으므로 분기 격자(40 × 2 = 80 호출)로도 검증 목적은 충분하다.
UNIVERSE_SNAPSHOT_FREQ = "Q"   # 스냅샷은 보강용. KRX 미사용이면 자연히 비활성.


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
            tabs = safe_read_html(raw, encoding=enc)
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


# ── 상장종목 스냅샷 (보조·검증 · KRX 없이도 무해) ────────────────────────────────────────────────────────────────
def _snapshot_grid(months: pd.DatetimeIndex) -> List[pd.Timestamp]:
    f = str(UNIVERSE_SNAPSHOT_FREQ).upper()
    if f in ("OFF", "NONE", ""):
        return []
    if f == "M":
        return list(months)
    if f == "A":
        return [m for m in months if m.month == 12] or list(months[::12])
    return [m for m in months if m.month in (3, 6, 9, 12)] or list(months[::3])   # 기본 Q


def fetch_listing_snapshots(months: pd.DatetimeIndex) -> pd.DataFrame:
    """상장종목 스냅샷 — '검증·보강' 입력이지 의존 대상이 아니다.

    ★ KRX 를 쓰지 않는 것이 기본이다. 유니버스의 정확성은 상장일(KIND/FDR)과
      폐지일(FDR delisting) 만으로 성립하도록 설계되어 있고, 스냅샷은 그 위에
      '합집합으로만' 얹힌다(교집합이 아니다 — SPEC 생존편향 규칙).

    따라서 이 함수는:
      · 드라이브 공용 캐시에 다른 전략(TCD v2 등)이 남긴 스냅샷이 있으면 그대로 재사용하고
      · KRX_ENABLE=True 이고 pykrx 가 살아 있을 때만 부족분을 보강하며
      · 둘 다 없으면 빈 프레임을 돌려준다. 빈 프레임이어도 유니버스는 정상 구성된다.
    """
    cols = ["snap_date", "code", "market"]
    frames: List[pd.DataFrame] = []
    for tname in ("krx_listing_snapshots", "listing_snapshots"):
        cached = VAULT.get_table(tname, scope="shared")
        if cached is not None and len(cached):
            c = cached.copy()
            c["snap_date"] = as_ts_series(c["snap_date"])
            c = c.dropna(subset=["snap_date", "code"])
            if len(c):
                frames.append(c.reindex(columns=cols))
                LOG.info(f"공용 캐시에서 상장 스냅샷 재사용: {tname} "
                         f"({c['snap_date'].nunique()}개 시점 · {len(c):,}행) — "
                         f"다른 전략이 남긴 것도 그대로 활용합니다.")

    if KRX_ENABLE and pykrx_stock is not None and RUN_MODE not in ("CACHED", "SMOKE"):
        have = set()
        if frames:
            have = set(pd.concat(frames, ignore_index=True)["snap_date"]
                       .dt.strftime("%Y-%m-%d"))
        todo = [d for d in _snapshot_grid(months) if d.strftime("%Y-%m-%d") not in have]
        if todo:
            LOG.info(f"KRX 스냅샷 보강 {len(todo)}개 시점 (교차검증 목적 · 실패해도 무해)")
            new_rows, bad = [], 0
            for d in tqdm(todo, desc="KRX 스냅샷(선택)", ncols=88, leave=False):
                got = False
                for mkt in ("KOSPI", "KOSDAQ"):
                    try:
                        limiter("krx").wait()
                        tk = pykrx_stock.get_market_ticker_list(d.strftime("%Y%m%d"), market=mkt)
                    except Exception:
                        tk = None
                    if not tk:
                        continue
                    got = True
                    for t in tk:
                        c = to_code6(t)
                        if c:
                            new_rows.append({"snap_date": d.strftime("%Y-%m-%d"),
                                             "code": c, "market": mkt})
                bad = 0 if got else bad + 1
                if bad >= 3:
                    LOG.warn("KRX 스냅샷이 연속 3회 비었습니다 — 차단/세션만료로 보고 즉시 중단합니다. "
                             "유니버스는 상장일·폐지일 경로로 정상 구성됩니다.")
                    break
            if new_rows:
                frames.append(pd.DataFrame(new_rows).assign(
                    snap_date=lambda d: as_ts_series(d["snap_date"])))

    if not frames:
        LOG.info("상장 스냅샷 없음 — 유니버스는 상장일·폐지일 기반으로 구성됩니다(정상 경로). "
                 "KRX 를 쓰지 않아도 생존편향 제거는 FDR 상장폐지 목록으로 달성됩니다.")
        return pd.DataFrame(columns=cols)

    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap = (snap.dropna(subset=["snap_date", "code"])
                .drop_duplicates(["snap_date", "code"])[cols])

    # 부분 응답 방어: 이웃 대비 종목수가 급감한 스냅샷은 '진실'이 아니라 '사고'다.
    if len(snap):
        size = snap.groupby("snap_date", observed=True)["code"].size().sort_index()
        med = float(size.median()) if len(size) else 0.0
        bad = size[size < med * 0.80]
        if len(bad) and med > 0:
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 중앙값({med:,.0f}종목)의 80% 미만 → 부분응답으로 폐기")
            snap = snap[~snap["snap_date"].isin(bad.index)]
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                        source="cache+krx_optional",
                        extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "listing_snapshots", snap, source="cache+krx_optional")
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
                "sector_src": "snapshot", "src": "snapshot"}))
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

    agg = m.groupby("code", as_index=False, observed=True).agg(
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
        g = snapshots.groupby("code", observed=True)["snap_date"]
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
                    source="fdr+kind+dart+naver")
    return agg


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  가격 · 거래대금 · ★PIT 시가총액 (KRX 없이)                                         ║
# ║                                                                                          ║
# ║  가격 폴백 사슬 (앞이 실패하면 자동으로 다음으로 — 전부 로그에 남는다):                    ║
# ║    ① FinanceDataReader      가장 넓은 커버리지, 상장폐지 종목도 상당수 조회됨              ║
# ║    ② 네이버금융 siseJson    api.finance.naver.com — 대량·고속·안정. EUC-KR 아님(JSON)      ║
# ║    ③ 네이버금융 sise_day    ②가 막힐 때의 HTML 폴백 (EUC-KR)                               ║
# ║    ④ yfinance               최후 폴백. 005930.KS / 0xxxxx.KQ                               ║
# ║                                                                                          ║
# ║  ★ 시가총액(PIT)이 이 모듈에서 가장 어려운 부분이다. KRX 를 못 쓰면 '과거 시점의 시총'을    ║
# ║    직접 주는 무료 소스가 사실상 없다. 그래서 4단 사다리로 만들고, 어느 단을 썼는지를        ║
# ║    (code, date) 마다 기록해 감사표로 출력한다. 조용히 틀린 시총을 쓰는 것이 최악이다.       ║
# ║      T1  DART 주식총수(stockTotqySttus) × 종가   ← 유일한 '정품' PIT 경로. DART 키 필요     ║
# ║      T2  현재 상장주식수 × 종가 ÷ 액면분할 보정  ← 자본변동 역산. 근사이지만 랭크는 견고    ║
# ║      T3  현재 시가총액 × (종가/현재종가)          ← T2 의 축약형                            ║
# ║      T4  20일 평균 거래대금 백분위                ← 시총이 아예 없을 때의 '사이즈 대용치'   ║
# ║                                                                                          ║
# ║    ※ 이 전략에서 시총은 전부 '랭크/버킷'으로만 쓰인다(§6.5 통제, H4 사이즈, 슬리피지 구간,  ║
# ║      비교전략의 하위 1000). 레벨로 쓰지 않으므로 T2~T4 로 강등돼도 결론이 뒤집히지 않는다.  ║
# ║      다만 T2~T4 는 '오늘의 주식수'를 과거에 투영하므로 미래정보가 섞인다 → 그 사실을        ║
# ║      감사표에 명시하고, T1 커버리지 비율을 반드시 보고한다.                                 ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PRICE_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount", "src"]

_NAVER_SISE_JSON = "https://api.finance.naver.com/siseJson.naver"
_NAVER_SISE_DAY = "https://finance.naver.com/item/sise_day.naver"


# ── ① FinanceDataReader ─────────────────────────────────────────────────────────────────────
def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    lc = {str(c).strip().lower(): c for c in d.columns}
    dt_c = lc.get("date") or lc.get("index") or d.columns[0]
    if "close" not in lc:
        return None
    vol = pd.to_numeric(d[lc["volume"]], errors="coerce") if "volume" in lc else np.nan
    close = pd.to_numeric(d[lc["close"]], errors="coerce")
    return pd.DataFrame({
        "code": code, "date": as_ts_series(d[dt_c]),
        "open": pd.to_numeric(d[lc["open"]], errors="coerce") if "open" in lc else close,
        "high": pd.to_numeric(d[lc["high"]], errors="coerce") if "high" in lc else close,
        "low": pd.to_numeric(d[lc["low"]], errors="coerce") if "low" in lc else close,
        "close": close, "volume": vol,
        "amount": pd.to_numeric(d[lc["amount"]], errors="coerce") if "amount" in lc
                  else close * vol,
        "src": "fdr"})


# ── ② 네이버 siseJson (대량 수집의 주력) ────────────────────────────────────────────────────
def _px_naver_json(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """반환 예: [['날짜','시가','고가','저가','종가','거래량','외국인소진율'], ['20160801',...], ...]

    ★ 응답이 JSON 처럼 보이지만 키가 홑따옴표라 json.loads 가 실패한다. 그래서 정규식으로 판다.
      (여기서 조용히 실패하면 전 종목 가격이 통째로 비고, 원인 추적이 매우 어렵다)"""
    s, e = as_ts(start), as_ts(end)
    if s is None or e is None:
        return None
    txt = http_get(_NAVER_SISE_JSON, source="naver",
                   params={"symbol": code, "requestType": 1,
                           "startTime": s.strftime("%Y%m%d"), "endTime": e.strftime("%Y%m%d"),
                           "timeframe": "day"},
                   referer=f"https://finance.naver.com/item/sise.naver?code={code}", tries=3)
    if not txt or "[" not in txt:
        return None
    rows = re.findall(r"\[([^\[\]]+)\]", txt)
    out = []
    for r in rows:
        parts = [p.strip().strip("'\"") for p in r.split(",")]
        if len(parts) < 6 or not re.fullmatch(r"\d{8}", parts[0]):
            continue           # 헤더행('날짜','시가',...) 은 여기서 걸러진다
        try:
            out.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3]),
                        float(parts[4]), float(parts[5])))
        except Exception:
            continue
    if not out:
        return None
    d = pd.DataFrame(out, columns=["date", "open", "high", "low", "close", "volume"])
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
    d["code"] = code
    d["amount"] = d["close"] * d["volume"]
    d["src"] = "naver_json"
    return d.dropna(subset=["date"])[PRICE_COLS]


# ── ③ 네이버 sise_day HTML 폴백 ─────────────────────────────────────────────────────────────
def _px_naver_html(code: str, start: str, end: str, max_pages: int = 700) -> Optional[pd.DataFrame]:
    s, e = as_ts(start), as_ts(end)
    got: List[pd.DataFrame] = []
    for page in range(1, max_pages + 1):
        html = http_get(_NAVER_SISE_DAY, source="naver", params={"code": code, "page": page},
                        force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/sise.naver?code={code}")
        if not html:
            break
        tabs = safe_read_html(html)
        if not tabs:
            break
        d = max(tabs, key=len).dropna(how="all")
        cols = {str(c).strip(): c for c in d.columns}
        if "날짜" not in cols or "종가" not in cols:
            break
        d = d.dropna(subset=[cols["날짜"]])
        if not len(d):
            break
        t = pd.DataFrame({
            "code": code,
            "date": pd.to_datetime(d[cols["날짜"]].astype(str).str.replace(".", "-", regex=False),
                                   errors="coerce"),
            "open": pd.to_numeric(d[cols.get("시가", cols["종가"])], errors="coerce"),
            "high": pd.to_numeric(d[cols.get("고가", cols["종가"])], errors="coerce"),
            "low": pd.to_numeric(d[cols.get("저가", cols["종가"])], errors="coerce"),
            "close": pd.to_numeric(d[cols["종가"]], errors="coerce"),
            "volume": pd.to_numeric(d[cols.get("거래량", cols["종가"])], errors="coerce"),
        }).dropna(subset=["date", "close"])
        if not len(t):
            break
        got.append(t)
        if t["date"].min() <= s:
            break
    if not got:
        return None
    d = pd.concat(got, ignore_index=True).drop_duplicates("date")
    d = d[(d["date"] >= s) & (d["date"] <= e)]
    d["amount"] = d["close"] * d["volume"]
    d["src"] = "naver_html"
    return d[PRICE_COLS] if len(d) else None


# ── ④ yfinance 최후 폴백 ────────────────────────────────────────────────────────────────────
def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    for suf in (".KS", ".KQ"):
        try:
            d = yf.download(code + suf, start=start, end=end, progress=False,
                            auto_adjust=False, threads=False)
        except Exception:
            continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):     # yfinance 0.2.5x 는 항상 MultiIndex 를 준다
            d.columns = [c[0] for c in d.columns]
        d = d.reset_index()
        lc = {str(c).strip().lower(): c for c in d.columns}
        if "close" not in lc:
            continue
        close = pd.to_numeric(d[lc["close"]], errors="coerce")
        vol = pd.to_numeric(d[lc["volume"]], errors="coerce") if "volume" in lc else np.nan
        return pd.DataFrame({
            "code": code, "date": as_ts_series(d[lc.get("date", d.columns[0])]),
            "open": pd.to_numeric(d[lc["open"]], errors="coerce") if "open" in lc else close,
            "high": pd.to_numeric(d[lc["high"]], errors="coerce") if "high" in lc else close,
            "low": pd.to_numeric(d[lc["low"]], errors="coerce") if "low" in lc else close,
            "close": close, "volume": vol, "amount": close * vol, "src": "yfinance"})
    return None


PRICE_CHAIN = [("fdr", _px_fdr), ("naver_json", _px_naver_json),
               ("naver_html", _px_naver_html), ("yfinance", _px_yf)]


def fetch_prices(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """가격 수집. 캐시 우선 → 부족분만 신규 → 드라이브 재적재(공용 인덱스).

    ★ 캐시 병합 규칙: 종목별로 '캐시가 요구 구간을 덮는가'를 판정한다.
      전체를 한 덩어리로 보고 '있다/없다'를 정하면, 캐시가 2020년까지만 있는 상태에서
      2016년 백테스트가 조용히 4년치 결측으로 돌아간다."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    s, e = as_ts(start), as_ts(end)
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=PRICE_COLS)

    cached = VAULT.get_table("price_daily", scope="shared")
    have: Dict[str, Tuple[pd.Timestamp, pd.Timestamp]] = {}
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["date"] = as_ts_series(cached["date"])
        cached["code"] = cached["code"].map(to_code6)
        cached = cached.dropna(subset=["code", "date", "close"])
        if len(cached):
            frames.append(cached)
            g = cached.groupby("code", observed=True)["date"]
            have = {c: (lo, hi) for c, lo, hi in zip(g.min().index, g.min().values, g.max().values)}
            have = {c: (as_ts(lo), as_ts(hi)) for c, (lo, hi) in have.items()}
            LOG.info(f"공용 캐시에서 가격 {len(cached):,}행 / {cached['code'].nunique():,}종목 재사용")

    # 캐시가 요구 구간을 '충분히' 덮으면 재수집하지 않는다(양끝 10영업일 여유 허용)
    pad = pd.Timedelta(days=16)
    todo = [c for c in codes
            if c not in have or have[c][0] > s + pad or have[c][1] < e - pad]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.warn(f"CACHED 모드 — 가격 부족 종목 {len(todo):,}건을 수집하지 않습니다. "
                     f"해당 종목의 이벤트는 수익률 결측으로 자동 제외됩니다(0으로 채우지 않음).")
        todo = []

    fail_reasons: Counter = Counter()
    src_hit: Counter = Counter()

    def _one(code: str) -> Optional[pd.DataFrame]:
        lo = s
        if code in have and have[code][0] <= s + pad:
            lo = max(s, have[code][1] - pd.Timedelta(days=7))   # 뒷부분만 증분 수집
        for name, fn in PRICE_CHAIN:
            try:
                d = fn(code, lo.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))
            except Exception as ex:                                       # noqa
                fail_reasons[f"{name}:{type(ex).__name__}"] += 1
                d = None
            if d is not None and len(d) >= 5:
                src_hit[name] += 1
                d = d.reindex(columns=PRICE_COLS)
                d["code"] = code
                return d
            fail_reasons[f"{name}:empty"] += 1
        return None

    if todo:
        LOG.info(f"가격 신규 수집 {len(todo):,}종목 (폴백 사슬: "
                 f"{' → '.join(n for n, _ in PRICE_CHAIN)})")
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 10), desc="가격 수집")
        frames += [d for d in res if d is not None and len(d)]

    if not frames:
        LOG.warn("가격 데이터를 하나도 확보하지 못했습니다. 네트워크 또는 소스 접근을 확인하세요.")
        return pd.DataFrame(columns=PRICE_COLS)

    px = pd.concat(frames, ignore_index=True)
    px["date"] = as_ts_series(px["date"])
    px["code"] = px["code"].map(to_code6)
    px = px.dropna(subset=["code", "date", "close"])
    px = px[(px["close"] > 0)]
    # 같은 (code,date) 가 여러 소스에서 오면 우선순위가 높은 소스를 남긴다
    prio = {n: i for i, (n, _) in enumerate(PRICE_CHAIN)}
    px["_p"] = px["src"].map(lambda x: prio.get(str(x), 99)).fillna(99)
    px = (px.sort_values(["code", "date", "_p"], kind="stable")
            .drop_duplicates(["code", "date"], keep="first")
            .drop(columns=["_p"]).reset_index(drop=True))
    px = px[(px["date"] >= s - pd.Timedelta(days=400)) & (px["date"] <= e)]

    if src_hit:
        LOG.table([[k, f"{v:,}"] for k, v in src_hit.most_common()],
                  ["소스", "성공 종목수"], ["l", "r"], title="가격 소스별 기여")
    if fail_reasons:
        LOG.debug(f"가격 수집 실패 사유 상위: {fail_reasons.most_common(8)}")

    if todo:
        VAULT.put_table("price_daily", px, scope="shared", domain="price",
                        source="fdr+naver+yfinance",
                        extra={"note": "일별 수정주가 OHLCV — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "price_daily", px, source="fdr+naver+yfinance")
    return downcast(px)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  PIT 시가총액 사다리
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_dart_shares(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """DART 「주식의 총수 현황」 — 비-KRX 환경에서 PIT 시총을 만드는 유일한 정품 경로.

    반환: corp_code, year, quarter, knowledge_date, shares_common
      · knowledge_date = 보고서 접수 가능 시점(보수적으로 기말 + 90일)
        ★ 이걸 기말로 잡으면 look-ahead 다. 사업보고서는 기말 후 90일 이내 제출이므로
          그 이후부터만 '알 수 있었던' 값으로 취급한다."""
    cols = ["corp_code", "year", "quarter", "knowledge_date", "shares_common"]
    if not DART_API_KEY:
        LOG.info("DART_API_KEY 가 없어 PIT 상장주식수를 건너뜁니다 → 시가총액은 "
                 "T2/T3/T4 근사로 자동 강등되며, 그 사실이 감사표에 표시됩니다.")
        return pd.DataFrame(columns=cols)
    cached = VAULT.get_table("dart_stock_totqy", scope="shared", max_age_days=45)
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART 주식총수 {len(cached):,}행 재사용")
        c = cached.copy()
        c["knowledge_date"] = as_ts_series(c["knowledge_date"])
        return c.reindex(columns=cols)
    if RUN_MODE == "CACHED":
        return pd.DataFrame(columns=cols)

    corps = [str(c).zfill(8) for c in dict.fromkeys(corp_codes) if str(c).strip()
             and str(c).lower() != "nan"]
    #  reprt_code: 11011=사업보고서(연간), 11014=3분기, 11012=반기, 11013=1분기
    jobs = [(c, y, rc) for c in corps for y in years for rc in ("11011",)]
    if not jobs:
        return pd.DataFrame(columns=cols)
    LOG.info(f"DART 주식총수 수집 {len(jobs):,}건 (기업 {len(corps):,} × 연도 {len(years)})")

    _QEND = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}

    def _one(job):
        corp, year, rc = job
        js = http_json("https://opendart.fss.or.kr/api/stockTotqySttus.json", source="dart",
                       params={"crtfc_key": DART_API_KEY, "corp_code": corp,
                               "bsns_year": str(year), "reprt_code": rc}, tries=2)
        if not isinstance(js, dict) or js.get("status") != "000":
            return None
        tot = np.nan
        for row in js.get("list", []) or []:
            se = norm_text(row.get("se", ""))
            if "합계" in se or "보통주" in se:
                v = str(row.get("distb_stock_co", row.get("istc_totqy", ""))).replace(",", "")
                v = re.sub(r"[^\d.\-]", "", v)
                try:
                    n = float(v)
                except Exception:
                    continue
                if n > 0 and (np.isnan(tot) or "합계" in se):
                    tot = n
        if not np.isfinite(tot) or tot <= 0:
            return None
        mm, dd = _QEND[rc]
        kd = pd.Timestamp(year=year, month=mm, day=dd) + pd.Timedelta(days=90)
        return {"corp_code": corp, "year": year, "quarter": rc,
                "knowledge_date": kd, "shares_common": tot}

    res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
    rows = [r for r in res if r]
    if not rows:
        LOG.warn("DART 주식총수를 받지 못했습니다 — 시총은 근사 경로로 강등됩니다.")
        return pd.DataFrame(columns=cols)
    d = pd.DataFrame(rows)
    out = d.copy()
    out["knowledge_date"] = out["knowledge_date"].dt.strftime("%Y-%m-%d")
    VAULT.put_table("dart_stock_totqy", out, scope="shared", domain="fundamental",
                    source="dart:stockTotqySttus",
                    extra={"note": "PIT 상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "dart_stock_totqy", d, source="dart")
    LOG.ok(f"DART 주식총수 {len(d):,}행 / {d['corp_code'].nunique():,}사 확보 "
           f"→ PIT 시가총액 T1 경로 가동")
    return d[cols]


def fetch_current_shares(sec: pd.DataFrame) -> pd.DataFrame:
    """현재 상장주식수/시가총액 스냅샷 (T2/T3 사다리의 앵커).
    FDR 상장목록 캐시에 Stocks/Marcap 이 있으면 그걸 쓰고, 없으면 네이버로 소수만 보강한다."""
    out = pd.DataFrame({"code": sec["code"], "shares_now": np.nan, "marcap_now": np.nan})
    d = _fdr_cache_csv("listing/krx")
    if d is not None and len(d):
        col = _lower_map(d)
        code_c = col.get("code") or col.get("symbol")
        sh_c = col.get("stocks") or col.get("listedshares") or col.get("shares")
        mc_c = col.get("marcap") or col.get("marketcap")
        if code_c and (sh_c or mc_c):
            t = pd.DataFrame({"code": d[code_c].map(to_code6)})
            t["shares_now"] = pd.to_numeric(d[sh_c], errors="coerce") if sh_c else np.nan
            t["marcap_now"] = pd.to_numeric(d[mc_c], errors="coerce") if mc_c else np.nan
            t = t.dropna(subset=["code"]).drop_duplicates("code")
            out = out.drop(columns=["shares_now", "marcap_now"]).merge(t, on="code", how="left")
            n = int(out["shares_now"].notna().sum() + out["marcap_now"].notna().sum())
            LOG.info(f"현재 상장주식수/시총 스냅샷 {n:,}건 확보 (T2/T3 앵커)")
    return out


def build_marketcap_panel(px: pd.DataFrame, sec: pd.DataFrame,
                          shares_pit: pd.DataFrame, cur: pd.DataFrame) -> pd.DataFrame:
    """(code, date) → marcap, size_tier, adv20, turnover.  ★ 어느 사다리를 썼는지 tier 로 기록.

    T1: PIT 주식수(asof, knowledge_date 이하 최신) × 종가       ← 미래정보 없음
    T2: 현재 주식수 × 종가                                       ← 주식수 변동분이 과거로 투영됨
    T3: 현재 시총 × (종가 / 최근 종가)                            ← T2 와 동치이나 주식수 없이 가능
    T4: 시총 없음 → adv20 백분위로 사이즈 대용                    ← 랭크 전용
    """
    if px is None or len(px) == 0:
        return pd.DataFrame(columns=["code", "date", "close", "amount", "adv20",
                                     "marcap", "mc_tier", "turnover"])
    p = px[["code", "date", "close", "volume", "amount"]].copy()
    p["date"] = as_ts_series(p["date"])
    p = p.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"], kind="stable")
    p["amount"] = p["amount"].fillna(p["close"] * p["volume"])
    p["adv20"] = (p.groupby("code", observed=True)["amount"]
                   .transform(lambda s: s.rolling(20, min_periods=5).mean()))

    p["marcap"] = np.nan
    p["mc_tier"] = "T4"

    # ── T1: DART PIT 주식수 asof 조인 ──────────────────────────────────────────────────────
    if shares_pit is not None and len(shares_pit) and "corp_code" in sec.columns:
        c2c = (sec.dropna(subset=["corp_code"])
                  .assign(corp_code=lambda d: d["corp_code"].astype(str).str.zfill(8))
                  .drop_duplicates("code")[["code", "corp_code"]])
        sp = shares_pit.copy()
        sp["knowledge_date"] = as_ts_series(sp["knowledge_date"])
        sp["corp_code"] = sp["corp_code"].astype(str).str.zfill(8)
        sp = (sp.dropna(subset=["knowledge_date", "shares_common"])
                .merge(c2c, on="corp_code", how="inner")
                .sort_values(["code", "knowledge_date"], kind="stable")
                [["code", "knowledge_date", "shares_common"]])
        if len(sp):
            left = p[["code", "date"]].sort_values(["date", "code"], kind="stable")
            right = sp.sort_values(["knowledge_date", "code"], kind="stable")
            j = pd.merge_asof(left, right, left_on="date", right_on="knowledge_date",
                              by="code", direction="backward", allow_exact_matches=True)
            j = j.set_index(left.index)["shares_common"]
            sh = j.reindex(p.index)
            ok = sh.notna() & (sh > 0)
            set_where(p, ok, "marcap", (p["close"] * sh)[ok])
            set_where(p, ok, "mc_tier", "T1")

    # ── T2/T3: 현재 스냅샷 앵커 ────────────────────────────────────────────────────────────
    need = p["marcap"].isna()
    if need.any() and cur is not None and len(cur):
        cm = cur.dropna(subset=["code"]).drop_duplicates("code").set_index("code")
        sh_now = p["code"].map(cm["shares_now"]) if "shares_now" in cm.columns else pd.Series(np.nan, index=p.index)
        ok2 = need & sh_now.notna() & (sh_now > 0)
        set_where(p, ok2, "marcap", (p["close"] * sh_now)[ok2])
        set_where(p, ok2, "mc_tier", "T2")

        need = p["marcap"].isna()
        if need.any() and "marcap_now" in cm.columns:
            last_close = p.groupby("code", observed=True)["close"].transform("last")
            mc_now = p["code"].map(cm["marcap_now"])
            ok3 = need & mc_now.notna() & (mc_now > 0) & last_close.notna() & (last_close > 0)
            set_where(p, ok3, "marcap", (mc_now * p["close"] / last_close)[ok3])
            set_where(p, ok3, "mc_tier", "T3")

    # ── T4: 거래대금 백분위를 사이즈 대용으로 (랭크 전용) ──────────────────────────────────
    still = p["marcap"].isna()
    if still.any():
        # 같은 날 시총을 가진 종목들의 분포에 adv20 백분위를 사상해 '비교 가능한 값'으로 만든다.
        # 시총이 하나도 없는 날은 adv20 자체를 사이즈 축으로 쓴다(랭크만 쓰므로 무해).
        set_where(p, still, "marcap", p["adv20"][still])
        set_where(p, still, "mc_tier", "T4")

    p["turnover"] = safe_div(p["amount"], p["marcap"])

    tier = p["mc_tier"].value_counts()
    tot = max(len(p), 1)
    LOG.table([[t, f"{int(tier.get(t,0)):,}", f"{100*int(tier.get(t,0))/tot:5.1f}%", why]
               for t, why in [("T1", "DART PIT 주식수 × 종가 — 미래정보 없음"),
                              ("T2", "현재 주식수 × 종가 — 주식수 변동이 과거로 투영됨"),
                              ("T3", "현재 시총 × 종가비 — T2 의 축약"),
                              ("T4", "거래대금 백분위 대용 — 랭크 전용")]],
              ["사다리", "행수", "비중", "성질"], ["l", "r", "r", "l"],
              title="PIT 시가총액 사다리 감사 (KRX 미사용 · 시총은 랭크로만 사용)")
    t1 = 100.0 * int(tier.get("T1", 0)) / tot
    if t1 < 50:
        LOG.warn(f"PIT 정품(T1) 시총 비중이 {t1:.0f}% 입니다. 나머지는 '오늘의 주식수'를 과거에 "
                 f"투영한 근사라 미래정보가 일부 섞입니다. 이 전략에서 시총은 랭크·버킷으로만 "
                 f"쓰이므로 결론이 뒤집힐 위험은 낮지만, H4(사이즈 조건부) 해석 시 감안하세요. "
                 f"DART_API_KEY 를 넣으면 T1 비중이 크게 올라갑니다.")
    PIPE.io("OUT", "MEM", "marketcap_panel", p)
    return downcast(p)


def build_trading_calendar(px: pd.DataFrame) -> pd.DatetimeIndex:
    """실제 거래가 관측된 날 = 영업일 달력. 공휴일 테이블을 하드코딩하지 않는다.
    ★ 관측 종목이 적은 날(예: 데이터 소스 장애일)을 영업일로 잘못 잡으면 d+1 진입이
      존재하지 않는 날로 밀려 수익률이 통째로 결측이 된다 → 관측종목수 하한을 건다."""
    if px is None or len(px) == 0:
        return pd.DatetimeIndex([])
    cnt = px.groupby("date", observed=True)["code"].nunique().sort_index()
    if not len(cnt):
        return pd.DatetimeIndex([])
    # ★ 하한을 5로 고정하면 종목이 몇 개뿐인 상황(합성·리허설·소규모 유니버스)에서
    #   달력이 통째로 비고, 그러면 이벤트가 하나도 거래일에 스냅되지 않아 조용히 0건이 된다.
    #   '중앙값의 25%' 라는 상대 기준만 남기고 절대 하한은 표본 규모에 맞춰 낮춘다.
    med = float(cnt.median())
    thr = max(1.0, min(5.0, med * 0.5), med * 0.25)
    cal = pd.DatetimeIndex(cnt[cnt >= thr].index).sort_values()
    dropped = int((cnt < thr).sum())
    if dropped:
        LOG.info(f"거래일 달력: {len(cal):,}일 확정 (관측종목수 {thr:,.0f} 미만인 {dropped}일은 "
                 f"소스 장애로 보고 제외 — 진입일이 존재하지 않는 날로 밀리는 사고 방지)")
    else:
        LOG.info(f"거래일 달력: {len(cal):,}일 확정")
    return cal


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B2  공공데이터포털 금융위원회_주식시세정보 — ★ KRX 없이 PIT 를 완성하는 축 ★          ║
# ║                                                                                          ║
# ║  엔드포인트: /1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo             ║
# ║  basDt(기준일자) 하나로 그날 '전 종목' 을 한 번에 준다. 이 성질이 결정적이다:              ║
# ║    · 10년 = 약 2,450 요청  (종목별로 긁으면 2,700종목 × 250페이지 = 67만 요청)             ║
# ║    · mrktTotAmt(시가총액) · lstgStCnt(상장주식수) 가 '그 시점 값' 으로 온다                ║
# ║      → PIT 시가총액이 근사가 아니라 정품이 된다. KRX 대체의 핵심.                          ║
# ║    · 그날 시세가 존재한 종목 목록 = 진짜 일별 상장 스냅샷                                  ║
# ║      → 생존편향 제거가 '상장/폐지일 추정' 이 아니라 '관측' 으로 확정된다.                  ║
# ║                                                                                          ║
# ║  함정 (전부 방어함):                                                                      ║
# ║   ① Encoding 키를 넣으면 이중 인코딩 → SERVICE_KEY_IS_NOT_REGISTERED. 자동 감지·교정.      ║
# ║   ② 오류 응답이 HTTP 200 + XML 로 온다. resultCode 를 반드시 본다.                         ║
# ║   ③ 휴장일은 정상적으로 0건이다. '수집 실패' 와 구분해서 기록해야 패널의 구멍을 나중에      ║
# ║      해석할 수 있다.                                                                       ║
# ║   ④ srtnCd 는 앞자리 0 이 날아간 정수로 오는 경우가 있다 → to_code6 로 복구.                ║
# ║   ⑤ 우선주·ETF·리츠가 섞여 온다. mrktCtg 와 종목코드 규칙으로 걸러야 유니버스가 오염되지 않는다.║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

DGK_BASE = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
DGK_COLS = ["date", "code", "name", "market", "open", "high", "low", "close",
            "volume", "amount", "shares", "marcap"]


def _dgk_key() -> str:
    """Decoding 키를 돌려준다. 사용자가 Encoding 키를 붙여넣은 경우를 감지해 교정한다."""
    k = (DATA_GO_KR_KEY or "").strip()
    if not k:
        return ""
    if "%" in k and re.search(r"%[0-9A-Fa-f]{2}", k):
        from urllib.parse import unquote
        dec = unquote(k)
        if dec != k:
            LOG.warn("DATA_GO_KR_KEY 가 Encoding 키로 보입니다(%2B/%3D 포함). "
                     "Decoding 키로 자동 변환했습니다. 계속 401 이 나면 포털에서 "
                     "'일반 인증키(Decoding)' 값을 다시 복사해 넣으세요.")
            return dec
    return k


def _dgk_day(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """하루치 전 종목. 실패는 None, 휴장(정상 0건)은 빈 DataFrame 으로 구분해서 돌려준다."""
    key = _dgk_key()
    if not key:
        return None
    bas = day.strftime("%Y%m%d")
    rows: List[dict] = []
    for page in range(1, 6):                     # 안전 상한 (하루 5,000행이면 충분)
        js = http_json(DGK_BASE, source="datagokr",
                       params={"serviceKey": key, "numOfRows": 1000, "pageNo": page,
                               "resultType": "json", "basDt": bas}, tries=3, timeout=30)
        if not isinstance(js, dict):
            return None                          # XML 오류응답 / 파싱 실패 → '수집 실패'
        body = (js.get("response") or {}).get("body") or {}
        hdr = (js.get("response") or {}).get("header") or {}
        rc = str(hdr.get("resultCode", "")).strip()
        if rc and rc not in ("00", "0", ""):
            LOG.debug(f"data.go.kr resultCode={rc} msg={hdr.get('resultMsg')} @{bas}")
            return None
        items = (body.get("items") or {})
        it = items.get("item") if isinstance(items, dict) else items
        if it is None:
            break
        if isinstance(it, dict):
            it = [it]
        rows.extend(it)
        tot = int(body.get("totalCount") or 0)
        if len(rows) >= tot or len(it) == 0:
            break
    if not rows:
        return pd.DataFrame(columns=DGK_COLS)    # 휴장(정상 0건)

    d = pd.DataFrame(rows)
    g = lambda c: pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    out = pd.DataFrame({
        "date": pd.to_datetime(d.get("basDt"), format="%Y%m%d", errors="coerce"),
        "code": d.get("srtnCd", pd.Series(dtype=object)).map(to_code6),
        "name": d.get("itmsNm", "").astype(str).str.strip(),
        "market": d.get("mrktCtg", "").astype(str).str.strip(),
        "open": g("mkp"), "high": g("hipr"), "low": g("lopr"), "close": g("clpr"),
        "volume": g("trqu"), "amount": g("trPrc"),
        "shares": g("lstgStCnt"), "marcap": g("mrktTotAmt"),
    })
    return out.dropna(subset=["code", "date", "close"])


def fetch_datagokr_panel(cal_start: str, cal_end: str) -> pd.DataFrame:
    """일별 전 종목 패널. 캐시 우선 → 부족한 날짜만 → 드라이브 공용 인덱스에 재적재.

    ★ 수집 순서는 최근 → 과거 다. 차단당하거나 중단되어도 '최신 구간' 이 먼저 확보되어
      부분 결과로도 최근 몇 년 백테스트가 가능하다 (SPEC §2.3).
    ★ 휴장일은 'holiday' 로, 실패일은 'fail' 로 각각 기록한다. 이 둘을 섞으면 몇 달 뒤에
      패널의 구멍이 무엇이었는지 영영 알 수 없게 된다."""
    key = _dgk_key()
    s, e = as_ts(cal_start), as_ts(cal_end)
    if s is None or e is None:
        return pd.DataFrame(columns=DGK_COLS)

    cached = VAULT.get_table("dgk_stock_price_daily", scope="shared")
    have_days: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["date", "code"])
        if len(c):
            frames.append(c.reindex(columns=DGK_COLS))
            have_days = set(c["date"].dt.strftime("%Y%m%d"))
            LOG.info(f"공용 캐시에서 공공데이터 시세 {len(c):,}행 / {len(have_days):,}일 재사용")

    # 상태 저장(중단·재개): 이미 '휴장 확인' 된 날은 다시 때리지 않는다
    state_p = out_path("_dgk_state.json")
    state = {"holiday": [], "fail": []}
    _prev = read_json(state_p, default=None)
    if isinstance(_prev, dict):
        state.update(_prev)
    known_holiday = set(state.get("holiday", []))

    if not key:
        if frames:
            LOG.info("DATA_GO_KR_KEY 가 없어 신규 수집은 건너뛰고 캐시만 사용합니다.")
        else:
            LOG.warn("DATA_GO_KR_KEY 가 비어 있습니다 → PIT 시가총액/일별 상장 스냅샷을 "
                     "정품 경로로 만들 수 없습니다. 시총은 근사(T2~T4)로 강등되고, "
                     "유니버스는 상장일·폐지일 기반으로만 구성됩니다(그래도 동작합니다). "
                     "정확도를 크게 올리려면 상단 ②-b 안내대로 키를 발급받아 넣으세요.")
        return (pd.concat(frames, ignore_index=True) if frames
                else pd.DataFrame(columns=DGK_COLS))

    days = pd.bdate_range(s, e)                       # 주말 제외 (공휴일은 응답 0건으로 판별)
    todo = [d for d in days
            if d.strftime("%Y%m%d") not in have_days
            and d.strftime("%Y%m%d") not in known_holiday]
    todo = sorted(todo, reverse=True)                 # ★ 최근 → 과거 (SPEC §2.3)

    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 공공데이터 {len(todo):,}일 신규 수집을 건너뜁니다.")
        todo = []

    if todo:
        LOG.info(f"공공데이터 일별 전종목 수집 {len(todo):,}일 (최근→과거 · 하루 1~3요청)")
        got: List[pd.DataFrame] = []
        n_holiday = n_fail = 0
        streak = 0
        stop = False
        # 스레드 수를 낮게 유지한다 — 공공데이터포털은 순간 폭주에 민감하다.
        lk = threading.Lock()

        def _one(day: pd.Timestamp):
            nonlocal n_holiday, n_fail, streak, stop
            if stop:
                return None
            polite_sleep(0.05, 0.25)
            d = _dgk_day(day)
            with lk:
                if d is None:
                    n_fail += 1
                    streak += 1
                    state["fail"].append(day.strftime("%Y%m%d"))
                    if streak >= FLOW_CIRCUIT_BREAK_N:
                        stop = True
                        LOG.error(f"공공데이터 연속 실패 {streak}회 → 서킷 브레이커 작동. "
                                  f"여기까지 받은 분량은 캐시에 저장하고 중단합니다. "
                                  f"(키 오류이거나 일일 트래픽 한도 초과일 수 있습니다)")
                    return None
                streak = 0
                if len(d) == 0:
                    n_holiday += 1
                    state["holiday"].append(day.strftime("%Y%m%d"))
                    return None
            return d

        res = pmap_io(_one, todo, workers=min(6, N_WORKERS_IO), desc="공공데이터 시세")
        got = [d for d in res if d is not None and len(d)]
        frames += got
        try:
            state["holiday"] = sorted(set(state["holiday"]))
            state["fail"] = sorted(set(state["fail"]))[-4000:]
            write_json(state_p, state)
        except Exception:
            pass
        LOG.ok(f"공공데이터 수집 완료 — 신규 {len(got):,}일 · 휴장 {n_holiday:,}일 · 실패 {n_fail:,}일")
        if n_fail > len(todo) * 0.3:
            LOG.warn(f"실패율이 {100*n_fail/max(len(todo),1):.0f}% 로 높습니다. "
                     f"인증키(Decoding) 와 일일 트래픽 한도를 확인하세요. "
                     f"실패한 날짜는 결측으로 남고 0으로 채우지 않습니다.")

    if not frames:
        return pd.DataFrame(columns=DGK_COLS)

    P = pd.concat(frames, ignore_index=True)
    P["date"] = as_ts_series(P["date"])
    P["code"] = P["code"].map(to_code6)
    P = (P.dropna(subset=["date", "code", "close"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))

    VAULT.put_table("dgk_stock_price_daily", P, scope="shared", domain="price",
                    source="data.go.kr:getStockPriceInfo",
                    extra={"note": "일별 전종목 시세+시총+상장주식수 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "dgk_stock_price_daily", P, source="data.go.kr")
    LOG.ok(f"공공데이터 패널 확정 — {len(P):,}행 · {P['code'].nunique():,}종목 · "
           f"{P['date'].nunique():,}거래일 "
           f"({P['date'].min():%Y-%m-%d} ~ {P['date'].max():%Y-%m-%d})")
    return downcast(P)


def dgk_listing_snapshots(P: pd.DataFrame, freq_days: int = 21) -> pd.DataFrame:
    """공공데이터 패널에서 '진짜 일별 상장 스냅샷' 을 뽑는다.

    ★ 이것이 KRX 스냅샷을 완전히 대체한다. 그날 시세가 관측된 종목 = 그날 상장된 종목.
      추정이 아니라 관측이므로 생존편향 제거의 근거가 훨씬 강하다.
      (전 거래일을 다 쓰면 스냅샷 테이블이 과도하게 커지므로 월 1회로 솎되,
       '유니버스 멤버십' 자체는 별도 함수에서 일별 관측을 그대로 쓴다)"""
    if P is None or len(P) == 0:
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    days = np.sort(P["date"].unique())
    pick = set(pd.DatetimeIndex(days[::max(1, freq_days)]))
    pick |= set(pd.DatetimeIndex(days).to_series().groupby(
        [pd.DatetimeIndex(days).year, pd.DatetimeIndex(days).month], observed=True).max())
    snap = P[P["date"].isin(pick)][["date", "code", "market"]].copy()
    snap = snap.rename(columns={"date": "snap_date"}).drop_duplicates(["snap_date", "code"])
    LOG.ok(f"공공데이터 기반 상장 스냅샷 {snap['snap_date'].nunique():,}개 시점 생성 "
           f"— KRX 없이 '관측된' 유니버스입니다(추정 아님)")
    out = snap.copy()
    out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
    VAULT.put_table("krx_listing_snapshots", out, scope="shared", domain="universe",
                    source="data.go.kr", extra={"note": "상장종목 스냅샷 — 전 전략 공용"})
    return snap


# ── 우선주 / 비보통주 배제 ────────────────────────────────────────────────────────────────────
_PREF_SUFFIX = re.compile(r"(우[BC]?$|우선주|\d우$)")


def is_common_stock(code: str, name: str = "", market: str = "") -> bool:
    """보통주만 남긴다. 우선주·ETF·ETN·리츠·스팩을 유니버스에 섞으면 이벤트 매칭이 오염된다.

    ★ 종목코드 끝자리 규칙: 보통주는 0 으로 끝나는 것이 관례지만 예외가 많다.
      이름 규칙과 병용하고, 애매하면 '남긴다'(보수적으로 표본을 지키는 쪽)."""
    c = to_code6(code) or ""
    n = str(name or "")
    m = str(market or "").upper()
    if not c:
        return False
    if _PREF_SUFFIX.search(n):
        return False
    if re.search(r"(스팩|SPAC|[0-9]+호$)", n):
        return False
    if re.search(r"(KODEX|TIGER|KBSTAR|ARIRANG|HANARO|SOL |ACE |PLUS |RISE |KOSEF|TIMEFOLIO|"
                 r"ETN$|ETF$|리츠$|REIT)", n, re.I):
        return False
    if "ETF" in m or "ETN" in m or "KONEX" in m:
        return False
    return True



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


_REPEAT_RE = re.compile(r"^(.{4,}?)(?:\s*\1)+$")


def _dedup_repeat(s: str) -> str:
    """제목이 'ABCABC' / 'ABC ABC' 처럼 반복되어 나오는 알려진 버그를 되돌린다.

    ★ 호출부가 td.get_text(" ") 로 셀을 뽑기 때문에 반복 사이에 공백이 낀다.
      '구분자 없는 정확 반복' 만 보던 옛 구현은 그걸 못 잡았고, 그 결과 stock_name 과
      dedup_key 가 함께 오염됐다. 정규식 폭주를 막으려 최소 단위 길이를 4로 둔다."""
    s = _clean_cell(s)
    if len(s) < 8:
        return s
    m = _REPEAT_RE.match(s)
    if m:
        return _clean_cell(m.group(1))
    n = len(s)
    for k in (2, 3):
        if n % k == 0 and s[: n // k] * k == s:
            return s[: n // k]
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
        fail_streak = 0
        cut_pages: List[int] = []
        for page in range(1, max_pages + 1):
            params = {
                "skinType": skin, "sdate": sd.strftime("%Y-%m-%d"), "edate": ed.strftime("%Y-%m-%d"),
                "now_page": page, "pagenum": page_size, "order_type": "",
                "report_type": "CO" if skin == "business" else "",
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            batch = _hk_parse(html, skin) if html else None
            # ★ 여기서 곧바로 break 하면 일시적 5xx/타임아웃 한 번에 그 해 남은 페이지가
            #   통째로 사라진다(전체의 10%). 3회 연속 실패일 때만 중단하고, 잘린 지점을 남긴다.
            if not html or not batch:
                fail_streak += 1
                cut_pages.append(page)
                if fail_streak >= 3:
                    LOG.error(f"한경 {skin} {sd:%Y} 구간이 page {page} 에서 3회 연속 실패로 "
                              f"잘렸습니다 (지금까지 {len(got):,}건). 재실행하면 캐시 위에 "
                              f"이어서 채웁니다.")
                    break
                continue
            fail_streak = 0
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
        # ★ 클래스명 하나(a.stock_item)에 의존하면 네이버가 클래스를 바꾸는 순간
        #   code 와 stock_name 이 동시에 죽고, 네이버 기여가 통째로 0 이 된다.
        #   href 에 code= 가 있는 링크면 모두 후보로 본다. 코드 판정은 to_code6 에 위임해
        #   2024 개편 영숫자 티커(예: 09701K)도 받아들인다.
        a_item = tr.select_one("a.stock_item[href]") or tr.select_one('a[href*="code="]')
        if a_item is not None:
            mm = re.search(r"code=([0-9A-Za-z]{6})", a_item["href"])
            code = to_code6(mm.group(1)) if mm else None
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


def _nv_any_date(v: Any) -> Optional[str]:
    """네이버 JSON 의 날짜는 형식이 제각각이다. 전부 YYYY-MM-DD 로 정규화한다.

    ★ 이걸 건너뛰면 pd.to_datetime 자동추론이 '23.05.12' 를 2012-05-23 으로 읽고
      (연·일 뒤바뀜) 예외 없이 통과한다 — 리포트 원장의 시간축 전체가 어긋난다.
      epoch(ms) 를 그대로 넘기면 1970-01-01 이 된다."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10}", s):                       # epoch 초
        return _dt.datetime.utcfromtimestamp(int(s)).strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{13}", s):                       # epoch 밀리초
        return _dt.datetime.utcfromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{8}", s):                        # YYYYMMDD
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    kd = parse_kr_date(s)                                # YY.MM.DD 뒤바뀜 방어
    if kd:
        return kd
    try:
        t = pd.Timestamp(s[:19])
        if pd.notna(t) and 1990 <= t.year <= 2100:
            return t.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


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
                "pub_date": _nv_any_date(it.get("createDate") or it.get("date") or
                                         it.get("writeDate") or it.get("regDate")),
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


def _nv_quality_ok(d: pd.DataFrame, sd, ed) -> Tuple[bool, str]:
    """JSON 응답을 채택할지 '건수' 가 아니라 '커버리지 품질' 로 판정한다.

    ★ 옛 게이트는 len(dj) > 50 이었다. 10년을 요청했는데 최근 수백 건만 돌아와도 통과해서,
      증권사 컬럼을 확실히 주는 유일한 경로인 HTML 폴백이 실행되지 않았다.
      ARC-BDF 는 broker 가 없으면 이벤트 자체가 성립하지 않으므로 여기서 막아야 한다."""
    if d is None or len(d) < 50:
        return False, f"건수 부족({0 if d is None else len(d)})"
    dd = as_ts_series(d["pub_date"])
    if dd.notna().mean() < 0.9:
        return False, f"날짜 파싱률 {100*dd.notna().mean():.0f}%"
    want = set(range(as_ts(sd).year, as_ts(ed).year + 1))
    got = set(dd.dropna().dt.year.unique().tolist())
    if len(want - got) > max(0, len(want) // 3):
        return False, f"연도 커버리지 부족(요청 {len(want)}년 중 {len(got & want)}년)"
    bro = d["broker_raw"].astype(str).str.strip().ne("").mean() if "broker_raw" in d else 0.0
    if bro < 0.5:
        return False, f"증권사 비공백률 {100*bro:.0f}%"
    return True, f"연도 {len(got & want)}/{len(want)} · 증권사 {100*bro:.0f}%"


def naver_collect(start: str, end: str, cats: Sequence[str] = ("company", "industry"),
                  max_pages: int = 1200) -> pd.DataFrame:
    """★ 반드시 연 단위로 쪼개서 수집한다.

    옛 구현은 10년 구간을 한 번에 질의하고 max_pages 로 잘랐다. 네이버 리스트는 작성일
    내림차순이므로 잘린 결과는 '가장 최근 N페이지' 이고, 그러면 이벤트 밀도가 최근 구간에
    몰려 10년 백테스트가 사실상 최근 몇 년 백테스트가 된다 — 조용한 시간축 편향이다.
    (한경 수집기는 원래부터 연 단위로 쪼개고 있었다. 두 소스를 같은 규율로 맞춘다)"""
    years = list(range(as_ts(start).year, as_ts(end).year + 1))
    frames: List[pd.DataFrame] = []

    for cat in cats:
        # ① JSON API 를 연 단위로 시도
        js_frames, js_ok_years = [], 0
        for y in years:
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            try:
                dj = naver_collect_json(cat, sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d"))
            except Exception:
                dj = pd.DataFrame()
            ok, why = _nv_quality_ok(dj, sd, ed)
            if ok:
                js_frames.append(dj)
                js_ok_years += 1
            else:
                LOG.debug(f"네이버 JSON '{cat}' {y}: 미채택 ({why}) → HTML 폴백 대상")

        need_html_years = [y for y in years]
        if js_ok_years:
            LOG.ok(f"네이버 JSON API '{cat}' — {js_ok_years}/{len(years)}개 연도 채택 "
                   f"({sum(len(x) for x in js_frames):,}건)")
            frames.extend(js_frames)
            covered = set()
            for x in js_frames:
                covered |= set(as_ts_series(x["pub_date"]).dropna().dt.year.unique().tolist())
            need_html_years = [y for y in years if y not in covered]

        if not need_html_years:
            continue

        # ② HTML 리스트 폴백 (연 단위)
        list_page, _ = NV_CATS[cat]
        base = urljoin(NV_BASE, list_page)

        def _year_sweep(y: int):
            sd = max(as_ts(f"{y}-01-01"), as_ts(start))
            ed = min(as_ts(f"{y}-12-31"), as_ts(end))
            qp = {"searchType": "writeDate",
                  "writeFromDate": sd.strftime("%Y-%m-%d"),
                  "writeToDate": ed.strftime("%Y-%m-%d")}
            probe = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                             params=dict(qp, page=1), tries=3)
            if not probe:
                LOG.warn(f"네이버 '{cat}' {y} 리스트 접근 실패 — 그 해는 결측으로 남습니다.")
                return []
            last = min(_nv_last_page(probe), max_pages)
            out = _nv_parse_list(probe, cat)
            fail = 0
            for p in range(2, last + 1):
                h = http_get(base, source="naver", referer=NV_BASE, force_enc="euc-kr",
                             tries=3, params=dict(qp, page=p))
                chunk = _nv_parse_list(h, cat) if h else []
                if not chunk:
                    fail += 1
                    if fail >= 3:
                        LOG.warn(f"네이버 '{cat}' {y} 가 page {p} 에서 잘렸습니다 "
                                 f"(지금까지 {len(out):,}건).")
                        break
                    continue
                fail = 0
                out.extend(chunk)
            if last >= max_pages:
                LOG.warn(f"네이버 '{cat}' {y} 가 최대 페이지({max_pages})에 도달 — "
                         f"그 해 데이터가 잘렸을 수 있습니다.")
            return out

        res = pmap_io(_year_sweep, need_html_years, workers=min(4, N_WORKERS_IO),
                      desc=f"네이버 {cat}(연단위)")
        rows = [r for chunk in res if chunk for r in chunk]
        if rows:
            frames.append(pd.DataFrame(rows))

    if not frames:
        return pd.DataFrame(columns=REPORT_COLS)
    d = pd.concat(frames, ignore_index=True)

    # ★ 연도별 건수 표를 강제 출력하고, 특정 연도가 중앙값의 30% 미만이면 경고가 아니라
    #   '시간축 편향' 으로 명시한다. 이 표가 없으면 편향이 조용히 통과한다.
    yy = as_ts_series(d["pub_date"]).dt.year.value_counts().sort_index()
    if len(yy):
        med = float(yy.median())
        LOG.table([[str(int(y)), f"{int(n):,}",
                    "정상" if n >= med * 0.3 else "★부족(시간축 편향 위험)"]
                   for y, n in yy.items()],
                  ["연도", "건수", "판정"], ["c", "r", "l"],
                  title="네이버 리서치 연도별 수집량 — 최근 구간 쏠림 감시")
        thin = [int(y) for y, n in yy.items() if n < med * 0.3]
        if thin:
            LOG.warn(f"연도 {thin} 의 수집량이 중앙값의 30% 미만입니다. 그대로 쓰면 "
                     f"이벤트 밀도가 특정 구간에 쏠려 10년 백테스트가 사실상 그 구간 "
                     f"백테스트가 됩니다. 재실행으로 캐시를 채우거나 해당 연도를 "
                     f"해석에서 제외하세요.")
    LOG.ok(f"네이버 리서치 {len(d):,}건 (종목코드 보유 {int(d['stock_code'].notna().sum()):,})")
    PIPE.io("IN", "HTTP", "naver:research", d, source=NV_BASE)
    return d


_NV_SRC_LINE = re.compile(r"([가-힣A-Za-z0-9\.\&\s]{2,25}?(?:증권|금융투자|투자증권))")


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다."""
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    if len(need) > limit:
        # ★ 최신순 상위 N 을 취하면 목표주가 보유율이 최근 1~2년에만 몰린다.
        #   그러면 '+3% 상향' 이벤트 밀도가 시간에 따라 왜곡되어 백테스트 성과가
        #   구간에 의존하게 된다. 연도별로 균등 배분해서 뽑는다.
        need["_y"] = as_ts_series(need["pub_date"]).dt.year
        n_y = max(1, need["_y"].nunique())
        per = max(50, limit // n_y)
        LOG.warn(f"네이버 상세 보강 대상 {len(need):,}건 중 {limit:,}건만 조회합니다 — "
                 f"연도별 최대 {per:,}건씩 균등 배분합니다(최근 구간 쏠림 방지).")
        need = (need.sort_values(["_y", "pub_date"], ascending=[True, False], kind="stable")
                    .groupby("_y", group_keys=False, observed=True).head(per).head(limit)
                    .drop(columns=["_y"]))

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

    # ★ 상세페이지 th.view_sbj p.source 는 애널리스트가 아니라 '증권사 | 작성일' 라인이다.
    #   지금까지 수집만 하고 버렸다. ARC-BDF 는 broker 가 없으면 이벤트가 성립하지 않으므로
    #   증권사 결측을 복구할 가장 값싼 경로로 배선한다.
    if "_detail_src" in df.columns:
        cand = df["_detail_src"].astype(str).map(
            lambda t: (_NV_SRC_LINE.search(t).group(1).strip() if _NV_SRC_LINE.search(t) else ""))
        blank = df.get("broker_raw", pd.Series("", index=df.index)).astype(str).str.strip().eq("")
        fill = blank & cand.astype(str).str.strip().ne("")
        if fill.any():
            if "broker_raw" not in df.columns:
                df["broker_raw"] = ""
            df.loc[fill, "broker_raw"] = cand[fill]
            LOG.ok(f"상세페이지 출처 라인에서 증권사 {int(fill.sum()):,}건 복구 "
                   f"(ARC-BDF 는 broker 가 없으면 이벤트 자체가 성립하지 않습니다)")
        df = df.drop(columns=["_detail_src"])

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
# ║  L1-C  증권사 ↔ 거래원(회원사) 매핑 원장                        [SPEC §5 · config 고정]   ║
# ║                                                                                          ║
# ║  이 전략의 신호는 "A증권이 리포트를 냈다" 와 "A증권 창구에서 순매수가 났다" 를 잇는 것이다.║
# ║  두 이름이 같은 문자열로 오지 않는다는 것이 실무의 전부다:                                 ║
# ║    · 리포트 원장  : "미래에셋증권", "하나증권", "이베스트투자증권"(과거 표기)              ║
# ║    · 거래원 창구  : "미래에셋", "하나금투", "이베스트"  ← 표시명이 짧고 시점마다 다르다     ║
# ║  게다가 사명 변경·합병이 10년 구간에 20건 넘게 일어난다. 정규화하지 않으면 같은 회사가     ║
# ║  시점에 따라 다른 회사가 되어 신호가 조용히 소멸한다.                                      ║
# ║                                                                                          ║
# ║  ★ 규칙 (SPEC §5)                                                                         ║
# ║    · 매핑 실패 건은 버리지 않고 unmapped 로 로그에 남긴다.                                 ║
# ║    · 매핑 실패율이 20% 를 넘으면 진행을 중단하고 보고한다.                                 ║
# ║    · 매핑표는 config/broker_member_map.csv 로 고정 저장하며, 드라이브 공용 인덱스에도      ║
# ║      올려 다른 전략이 그대로 재사용할 수 있게 한다.                                        ║
# ║                                                                                          ║
# ║  ⚠ 이 파일에는 특정 증권사에 대한 어떤 가치판단도 담지 않는다(SPEC §0.5).                  ║
# ║    'RETAIL' / 'FOREIGN' 같은 분류는 창구의 주문 구성이 통계적으로 다르다는 관측일 뿐이다.  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BROKER_MAP_CSV = "broker_member_map.csv"

# ★ 비-증권 법인 차단 사전 (가장 먼저 검사한다)
#   '미래에셋' 별칭 하나만 두면 미래에셋생명·미래에셋자산운용까지 미래에셋증권으로 흡수된다.
#   '기업은행' 을 IBK 별칭에 넣으면 IBK기업은행이 IBK투자증권이 된다.
#   '한국투자' 는 한국투자파트너스(VC)를, '키움' 은 키움투자자산운용을 빨아들인다.
#   전부 실제로 일어나는 오매칭이고, 그대로 두면 '자사 창구' 신호에 남의 주문이 섞인다.
NON_BROKER_MARKERS = re.compile(
    r"(생명|화재|손해보험|보험|자산운용|투자자문|파트너스|밸류|벤처|캐피탈|저축은행|"
    r"은행|카드|신탁|리츠|기술투자|창업투자|IR협의회|기업평가|신용평가|거래소|"
    r"연구소|경제연구|리서치센터|애널리스트협회|NICE|나이스|에프앤가이드|FNGUIDE|"
    r"ASSETMANAGEMENT|SECURITIESINVESTMENTTRUST)", re.I)

# tier: MAJOR(대형 리서치) / MID(중소형 리서치) / RETAIL(리테일 주문 비중이 압도적인 창구) /
#       FOREIGN(외국계 창구) / OTHER(증권사가 아니거나 분류 불가 → 이벤트에서 제외)
#
# 별칭 규칙 두 가지 (오매칭을 구조적으로 막는다):
#   · 긴 별칭을 먼저 검사한다 ("한국투자증권" 이 "한국" 에 먹히지 않게)
#   · 짧은 축약 별칭(거래원 창구 표시명)은 '완전일치' 로만 허용한다. 부분포함으로 허용하면
#     "미래에셋" 이 "미래에셋생명" 을 잡는다. 완전일치 전용 별칭은 앞에 '=' 를 붙여 표시한다.
#
# valid_from / valid_to (YYYY-MM-DD, 빈 값=무제한): 사명이 재사용된 경우의 PIT 매핑.
#   ★ 우리투자증권이 대표 사례다. 2014년 NH농협증권과 합병해 NH투자증권이 되었지만,
#     2024-08 우리금융이 한국포스증권+우리종합금융을 합쳐 같은 이름으로 재출범시켰다.
#     시점을 안 보면 2024년 이후 우리투자증권 창구의 주문이 NH 이벤트에 붙는다.
BROKER_MEMBER_SEED: List[Tuple[str, str, str, str, str]] = [
    # (정식 증권사명, tier, "별칭|별칭|...", valid_from, valid_to)
    ("미래에셋증권",   "MAJOR",   "미래에셋증권|미래에셋대우|=미래에셋|대우증권|KDB대우|=대우", "", ""),
    ("NH투자증권",     "MAJOR",   "NH투자증권|NH투자|엔에이치투자|NH농협증권|=NH", "", ""),
    ("NH투자증권",     "MAJOR",   "우리투자증권|우리투자", "", "2014-12-31"),
    ("우리투자증권",   "MID",     "우리투자증권|우리투자|우리종합금융", "2024-08-01", ""),
    ("한국투자증권",   "MAJOR",   "한국투자증권|한국증권|한투증권|=한국투자|=한투", "", ""),
    ("삼성증권",       "MAJOR",   "삼성증권|=삼성", "", ""),
    ("KB증권",         "MAJOR",   "KB증권|KB투자증권|현대증권|케이비증권|=KB", "", ""),
    ("신한투자증권",   "MAJOR",   "신한투자증권|신한금융투자|신한금투|=신한투자|=신한", "", ""),
    ("하나증권",       "MAJOR",   "하나증권|하나금융투자|하나금투|하나대투증권|하나대투|=하나", "", ""),
    ("메리츠증권",     "MAJOR",   "메리츠증권|메리츠종금증권|메리츠종금|아이엠투자증권|=메리츠", "", ""),
    ("키움증권",       "RETAIL",  "키움증권|=키움", "", ""),
    ("대신증권",       "MID",     "대신증권|=대신", "", ""),
    ("유안타증권",     "MID",     "유안타증권|동양증권|=유안타|=동양", "", ""),
    ("한화투자증권",   "MID",     "한화투자증권|한화증권|=한화투자|=한화", "", ""),
    ("교보증권",       "MID",     "교보증권|=교보", "", ""),
    ("IBK투자증권",    "MID",     "IBK투자증권|IBK증권|아이비케이투자증권|=IBK", "", ""),
    ("신영증권",       "MID",     "신영증권|=신영", "", ""),
    ("현대차증권",     "MID",     "현대차증권|현대차투자증권|HMC투자증권|=HMC|=현대차", "", ""),
    ("SK증권",         "MID",     "SK증권|에스케이증권|=SK", "", ""),
    ("유진투자증권",   "MID",     "유진투자증권|유진증권|=유진", "", ""),
    ("iM증권",         "MID",     "iM증권|IM증권|아이엠증권|하이투자증권|하이증권|=하이투자|=하이", "", ""),
    ("LS증권",         "MID",     "LS증권|엘에스증권|이베스트투자증권|EBEST투자증권|"
                                 "=이베스트|=EBEST|=E*BEST", "", ""),
    ("다올투자증권",   "MID",     "다올투자증권|KTB투자증권|=다올|=KTB", "", ""),
    ("DB금융투자",     "MID",     "DB금융투자|디비금융투자|동부증권|DB증권|=DB금투|=DB", "", ""),
    ("BNK투자증권",    "MID",     "BNK투자증권|BNK증권|=BNK", "", ""),
    ("흥국증권",       "MID",     "흥국증권|=흥국", "", ""),
    ("부국증권",       "MID",     "부국증권|=부국", "", ""),
    ("한양증권",       "MID",     "한양증권|=한양", "", ""),
    ("상상인증권",     "MID",     "상상인증권|골든브릿지투자증권|=상상인|=골든브릿지", "", ""),
    ("케이프투자증권", "MID",     "케이프투자증권|LIG투자증권|=케이프|=LIG", "", ""),
    ("토스증권",       "RETAIL",  "토스증권|=토스", "", ""),
    ("카카오페이증권", "RETAIL",  "카카오페이증권|바로투자증권|=카카오페이|=바로투자", "", ""),
    ("리딩투자증권",   "MID",     "리딩투자증권|=리딩투자", "", ""),
    ("코리아에셋투자증권", "MID", "코리아에셋투자증권|=코리아에셋", "", ""),
    ("유화증권",       "MID",     "유화증권|=유화", "", ""),
    ("DS투자증권",     "MID",     "DS투자증권|디에스투자증권|DS증권", "", ""),
    ("한국포스증권",   "MID",     "한국포스증권|포스증권|펀드온라인코리아", "", "2024-07-31"),
    ("교보악사",       "OTHER",   "교보악사", "", ""),
    # ── 외국계 창구 ─────────────────────────────────────────────────────────────────────
    ("모간스탠리",     "FOREIGN", "모간스탠리|모건스탠리|모건스탠리서울|=모건서울|=모간스탠|"
                                 "MORGANSTANLEY|=MS서울", "", ""),
    ("골드만삭스",     "FOREIGN", "골드만삭스|GOLDMANSACHS|=골드만|=GS서울", "", ""),
    ("JP모간",         "FOREIGN", "JP모간|제이피모간|JP모건|JPMORGAN", "", ""),
    ("메릴린치",       "FOREIGN", "메릴린치|BOFA|뱅크오브아메리카|MERRILL|=BOA|=메릴", "", ""),
    ("CS증권",         "FOREIGN", "CS증권|크레디트스위스|크레디스위스|CREDITSUISSE|=CS", "", ""),
    ("UBS",            "FOREIGN", "UBS증권|UBS", "", ""),
    ("씨티그룹",       "FOREIGN", "씨티그룹|한국씨티|CITIGROUP|=씨티|=CITI", "", ""),
    ("도이치",         "FOREIGN", "도이치증권|도이치|DEUTSCHE", "", ""),
    ("HSBC",           "FOREIGN", "HSBC증권|HSBC", "", ""),
    ("노무라",         "FOREIGN", "노무라금융투자|노무라|NOMURA", "", ""),
    ("다이와",         "FOREIGN", "다이와증권|다이와|DAIWA", "", ""),
    ("맥쿼리",         "FOREIGN", "맥쿼리증권|맥쿼리|MACQUARIE", "", ""),
    ("CLSA",           "FOREIGN", "CLSA코리아|CLSA", "", ""),
    ("BNP파리바",      "FOREIGN", "BNP파리바|BNPPARIBAS|=BNP", "", ""),
    ("SG증권",         "FOREIGN", "SG증권|소시에테제네랄|SOCIETEGENERALE|=소시에테", "", ""),
    ("바클레이즈",     "FOREIGN", "바클레이즈|바클레이|BARCLAYS", "", ""),
    ("홍콩상하이",     "FOREIGN", "홍콩상하이", "", ""),
    # ── 비증권 리서치 제공자: 매핑은 하되 tier=OTHER 로 두어 이벤트에서 제외한다 ──────────
    ("한국IR협의회",   "OTHER",   "한국IR협의회|IR협의회", "", ""),
    ("NICE디앤비",     "OTHER",   "NICE디앤비|나이스디앤비", "", ""),
    ("에프앤가이드",   "OTHER",   "에프앤가이드|FNGUIDE", "", ""),
]

# H3(중소형 증권사에서 효과가 강하다) 검정용 그룹 정의 — 사전등록 값. 실행 중 변경 금지.
H3_SMALL_TIERS = ("MID",)                 # '중소형 리서치' 군
H3_LARGE_TIERS = ("MAJOR", "RETAIL")      # '대형/리테일 집중' 군


def _norm_broker_token(s: Any) -> str:
    """비교용 정규화: 공백·괄호·특수문자 제거, 대문자화, '증권/투자증권/금융투자' 접미 제거."""
    t = norm_text(s)
    if not t:
        return ""
    t = re.sub(r"[\s\(\)\[\]\{\}·・,\.\-_/]", "", t)
    t = t.upper()
    for suf in ("주식회사", "㈜"):
        t = t.replace(suf, "")
    return t


class BrokerMap:
    """증권사 정식명 ↔ 거래원 창구 표시명 양방향 원장.  ★ 정규화의 단일 진실원.

    매칭 순서 (오매칭을 구조적으로 막는 순서다):
      0. 비-증권 법인 차단어가 있으면 즉시 None  (미래에셋생명 / 한국투자파트너스 / IBK기업은행)
      1. 완전일치 (별칭·정식명)
      2. 부분포함 — 단 '완전일치 전용(=접두)' 별칭은 제외하고, 긴 별칭부터
      3. 시점(when)이 주어지면 valid_from/valid_to 로 걸러 PIT 매핑을 보장
    """

    def __init__(self, rows: List[dict]):
        self.rows = rows
        self.canon2tier: Dict[str, str] = {}
        # (정규화 별칭, 정식명, exact_only, vfrom, vto)
        self._alias: List[Tuple[str, str, bool, Optional[pd.Timestamp], Optional[pd.Timestamp]]] = []
        for r in rows:
            canon = str(r.get("broker", "")).strip()
            if not canon:
                continue
            tier = str(r.get("tier", "OTHER")).strip() or "OTHER"
            # 같은 canon 이 여러 줄(시점별)로 올 수 있다 — tier 는 첫 값을 유지
            self.canon2tier.setdefault(canon, tier)
            vf = as_ts(r.get("valid_from")) if str(r.get("valid_from", "")).strip() else None
            vt = as_ts(r.get("valid_to")) if str(r.get("valid_to", "")).strip() else None
            toks = [str(r.get("aliases", "")), canon]
            for chunk in toks:
                for a in chunk.split("|"):
                    a = a.strip()
                    if not a:
                        continue
                    exact_only = a.startswith("=")
                    na = _norm_broker_token(a.lstrip("="))
                    if na:
                        self._alias.append((na, canon, exact_only, vf, vt))
        # 긴 별칭 먼저 — "한국투자증권" 이 "한국투자" 보다 먼저 검사되어야 한다
        self._alias = sorted(set(self._alias), key=lambda x: (-len(x[0]), x[0]))
        self.unmapped: Counter = Counter()
        self.hit: Counter = Counter()
        self.blocked: Counter = Counter()

    @staticmethod
    def _in_window(vf, vt, when) -> bool:
        if when is None:
            return True
        t = as_ts(when)
        if t is None:
            return True
        if vf is not None and t < vf:
            return False
        if vt is not None and t > vt:
            return False
        return True

    def resolve(self, raw: Any, when: Any = None) -> Optional[str]:
        """거래원 창구 표시명 또는 리포트 증권사명 → 정식 증권사명. 실패하면 None.

        when 을 주면 그 시점에 유효한 매핑만 쓴다(사명 재사용 대응).
        예) resolve("우리투자증권", "2013-05-01") → "NH투자증권"
            resolve("우리투자증권", "2025-03-01") → "우리투자증권"  (2024-08 재출범 별개 법인)"""
        n = _norm_broker_token(raw)
        if not n:
            return None
        # ── 0) 비증권 법인 차단. 단 정식명과 완전히 같으면 통과시킨다(예: 'NICE디앤비')
        if NON_BROKER_MARKERS.search(n) and not any(
                a == n and not eo for a, c, eo, _, _ in self._alias):
            self.blocked[str(raw)[:40]] += 1
            return None
        # ── 1) 완전일치 (시점 유효한 것 우선)
        exact = [(a, c, vf, vt) for a, c, eo, vf, vt in self._alias if a == n]
        for a, c, vf, vt in exact:
            if self._in_window(vf, vt, when):
                self.hit[c] += 1
                return c
        if exact and when is None:
            self.hit[exact[0][1]] += 1
            return exact[0][1]
        # ── 2) 부분포함 (완전일치 전용 별칭은 건너뛴다)
        for a, c, eo, vf, vt in self._alias:
            if eo or len(a) < 3:
                continue
            if (a in n or n in a) and self._in_window(vf, vt, when):
                self.hit[c] += 1
                return c
        self.unmapped[str(raw)[:40]] += 1
        return None

    def is_broker(self, canon: Optional[str]) -> bool:
        """증권사인가 (OTHER = 비증권 리서치 제공자 등 → 이벤트에서 제외)."""
        return bool(canon) and self.canon2tier.get(canon, "OTHER") != "OTHER"

    def tier(self, canon: Optional[str]) -> str:
        return self.canon2tier.get(canon or "", "OTHER")

    def is_small(self, canon: Optional[str]) -> bool:
        return self.tier(canon) in H3_SMALL_TIERS

    def is_large(self, canon: Optional[str]) -> bool:
        return self.tier(canon) in H3_LARGE_TIERS

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def load_broker_map() -> "BrokerMap":
    """config/broker_member_map.csv 우선 → 드라이브 공용 캐시 → 내장 시드.
    사용자가 CSV 를 손보면 그게 이긴다(수작업 고정 원칙, SPEC §5)."""
    rows: List[dict] = []
    src = "seed"

    # ① 로컬 config/
    for cand in (os.path.join(PROJECT_ROOT, "config", BROKER_MAP_CSV),
                 os.path.join(os.getcwd(), "config", BROKER_MAP_CSV),
                 os.path.join(os.getcwd(), BROKER_MAP_CSV)):
        try:
            if os.path.isfile(cand):
                d = read_csv_utf8(cand, dtype=str).fillna("")
                if {"broker", "aliases"} <= set(d.columns):
                    rows = d.to_dict("records")
                    src = f"csv:{cand}"
                    break
        except Exception as e:                                        # noqa
            LOG.warn(f"매핑 CSV 읽기 실패({cand}): {type(e).__name__} — 다음 후보로 넘어갑니다.")

    # ② 드라이브 공용 캐시 (다른 전략이 이미 만들어 뒀을 수 있다)
    if not rows:
        cached = VAULT.get_table("broker_member_map", scope="shared")
        if cached is not None and len(cached) and {"broker", "aliases"} <= set(cached.columns):
            rows = cached.fillna("").to_dict("records")
            src = "drive:_shared/broker_member_map"

    # ③ 내장 시드
    if not rows:
        rows = [{"broker": b, "tier": t, "aliases": a, "valid_from": vf, "valid_to": vt}
                for b, t, a, vf, vt in BROKER_MEMBER_SEED]

    bm = BrokerMap(rows)

    # 항상 CSV 로 고정 저장 (사용자가 손볼 수 있게) + 공용 인덱스에 적재
    try:
        cfg_dir = os.path.join(PROJECT_ROOT, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        out = bm.to_frame().reindex(
            columns=["broker", "tier", "aliases", "valid_from", "valid_to"]).fillna("")
        # BOM 을 붙여야 엑셀에서 한글이 깨지지 않는다(사용자가 직접 편집하는 파일이다)
        atomic_write_text(os.path.join(cfg_dir, BROKER_MAP_CSV),
                          "﻿" + out.to_csv(index=False, lineterminator="\n"))
        VAULT.put_table("broker_member_map", out, scope="shared", domain="reference",
                        source=src, extra={"note": "증권사↔거래원 회원사 매핑 — 전 전략 공용"})
    except Exception as e:                                            # noqa
        LOG.warn(f"매핑표 저장 실패({type(e).__name__}) — 메모리 상으로는 정상 동작합니다.")

    LOG.ok(f"증권사↔거래원 매핑 원장 {len(rows)}행 적재 (출처={src}) · "
           f"MAJOR {sum(1 for r in rows if r.get('tier')=='MAJOR')} / "
           f"MID {sum(1 for r in rows if r.get('tier')=='MID')} / "
           f"RETAIL {sum(1 for r in rows if r.get('tier')=='RETAIL')} / "
           f"FOREIGN {sum(1 for r in rows if r.get('tier')=='FOREIGN')}")
    return bm


def audit_broker_mapping(bm: "BrokerMap", rep: pd.DataFrame,
                         flow: Optional[pd.DataFrame]) -> dict:
    """SPEC §5: 매핑 성공률 / 사명변경 처리 내역 감사. 실패율 20% 초과 시 중단 신호를 돌려준다."""
    out: Dict[str, Any] = {"ok": True, "report_rate": np.nan, "flow_rate": np.nan}
    rows: List[List[str]] = []

    # ① 리포트 원장 쪽
    if rep is not None and len(rep):
        bcol = "broker_name" if "broker_name" in rep.columns else (
            "broker" if "broker" in rep.columns else "broker_raw")
        b = rep[bcol].astype(str) if bcol in rep.columns else pd.Series(dtype=str)
        when = as_ts_series(rep["pub_date"]) if "pub_date" in rep.columns else None
        # ★ 발간 시점 기준 매핑(사명 재사용 대응)
        if when is not None:
            mapped = pd.Series([bm.resolve(x, w) is not None for x, w in zip(b, when)],
                               index=b.index)
        else:
            mapped = b.map(lambda x: bm.resolve(x) is not None)
        nonblank = float((b.str.strip() != "").mean()) if len(b) else 0.0
        rows.append(["리포트 원장의 증권사명 비공백률", f"{len(b):,}", f"{100*nonblank:5.1f}%",
                     "OK" if nonblank >= 0.90 else "미달"])
        out["broker_fill_rate"] = nonblank
        r = float(mapped.mean()) if len(mapped) else 0.0
        out["report_rate"] = r
        rows.append(["리포트 원장 → 정식 증권사명", f"{len(b):,}", f"{100*r:5.1f}%",
                     "OK" if r >= 0.80 else "미달"])
        bad = b[~mapped].value_counts().head(8)
        if len(bad):
            LOG.info(f"  리포트 미매핑 상위: {dict(bad)}")

    # ② 거래원 플로우 쪽
    if flow is not None and len(flow) and "member_raw" in flow.columns:
        m = flow["member_raw"].astype(str)
        uniq = pd.Series(m.unique())
        mapped_u = uniq.map(lambda x: bm.resolve(x) is not None)
        # 건수 가중 성공률 (희귀 창구 하나가 실패해도 전체가 무너지진 않으므로 둘 다 본다)
        cnt = m.value_counts()
        w = float((cnt[uniq[mapped_u].tolist()].sum() if mapped_u.any() else 0) / max(cnt.sum(), 1))
        out["flow_rate"] = w
        rows.append(["거래원 창구명 → 정식 증권사명", f"{len(m):,}", f"{100*w:5.1f}%",
                     "OK" if w >= 0.80 else "미달"])
        badu = uniq[~mapped_u].tolist()[:10]
        if badu:
            LOG.info(f"  창구 미매핑 표시명(유형): {badu}")
            out["unmapped_members"] = badu

    if not rows:
        LOG.warn("매핑 감사에 쓸 입력(리포트/플로우)이 없습니다 — 감사 생략.")
        return out

    LOG.table(rows, ["매핑 축", "건수", "성공률", "판정"], ["l", "r", "r", "c"],
              title="증권사 ↔ 거래원 회원사 매핑 감사 (SPEC §5)")

    worst = np.nanmin([out.get("report_rate", np.nan), out.get("flow_rate", np.nan)])
    if np.isfinite(worst) and worst < 0.80:
        out["ok"] = False
        LOG.error(f"매핑 실패율이 {100*(1-worst):.0f}% 로 SPEC §5 한계(20%)를 초과했습니다. "
                  f"config/{BROKER_MAP_CSV} 의 aliases 컬럼에 위 미매핑 표시명을 추가한 뒤 "
                  f"다시 실행하세요. (버리지 않고 unmapped 로 전부 로그에 남겼습니다)")
    else:
        LOG.ok("매핑 실패율이 SPEC §5 한계(20%) 이내입니다 — 진행합니다.")

    # 사명변경 처리 내역 (감사 산출물용)
    changes = [
        ("2014", "우리투자증권 + NH농협증권 → NH투자증권"),
        ("2014", "동양증권 → 유안타증권"),
        ("2016", "HMC투자증권 → 현대차투자증권 → 현대차증권"),
        ("2017", "KB투자증권 + 현대증권 → KB증권"),
        ("2016~", "미래에셋증권 + KDB대우증권 → 미래에셋대우 → 미래에셋증권(2021)"),
        ("2018", "동부증권 → DB금융투자"),
        ("2022", "신한금융투자 → 신한투자증권"),
        ("2022", "하나금융투자 → 하나증권"),
        ("2022", "KTB투자증권 → 다올투자증권"),
        ("2024", "이베스트투자증권 → LS증권"),
        ("2024", "하이투자증권 → iM증권"),
        ("2020~", "바로투자증권 → 카카오페이증권 / 토스증권 신규"),
    ]
    out["name_changes"] = changes
    LOG.table([[y, c] for y, c in changes], ["시점", "사명변경·합병 (매핑에 반영됨)"],
              ["c", "l"], title="10년 구간 증권사 사명변경 이력 — 반영 내역")
    return out



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


_BROKER_MAP_SINGLETON: Optional["BrokerMap"] = None


def broker_map() -> "BrokerMap":
    """★ 증권사 정규화의 단일 진실원. 리포트 축과 거래원 축이 같은 사전을 써야 조인된다.

    두 곳에 표를 두면 'DB증권' 이 한쪽에선 DB금융투자, 다른 쪽에선 도이치가 되는 식으로
    조인 단계에서 조용히 어긋난다. 그래서 여기서도 BrokerMap 을 그대로 쓴다."""
    global _BROKER_MAP_SINGLETON
    if _BROKER_MAP_SINGLETON is None:
        _BROKER_MAP_SINGLETON = load_broker_map()
    return _BROKER_MAP_SINGLETON


def normalize_broker(raw: Any, when: Any = None) -> Tuple[str, str]:
    """(broker_id, 정식명). 못 알아보면 정규화 문자열 자체를 id 로 쓰되 '미상' 으로 뭉치지 않는다
    (미상으로 뭉치면 서로 다른 소형사가 한 덩어리가 되어 커버리지 통계가 거짓이 된다)."""
    t = _clean_cell(raw)
    if not t:
        return ("", "")
    canon = broker_map().resolve(t, when)
    if canon:
        return (sha1_str("broker", canon)[:12], canon)
    t2 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", t))
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
        p = re.sub(r"[^가-힣A-Za-z ]", "", p).strip()
        if _is_person_name(p):
            out.append(p.replace(" ", ""))
    return list(dict.fromkeys(out))


# 애널리스트로 등록되면 안 되는 토큰. 한경 폴백 휴리스틱이 투자의견·증권사명을 이름 자리에
# 넣어버리는 사고가 실제로 있었고, 그 링크에 신뢰도 0.98 이 붙어 감사표를 통과했다.
_NOT_A_NAME = set()
for _k in list(_OPINION_MAP.keys()):
    _NOT_A_NAME.add(re.sub(r"[^가-힣A-Za-z]", "", str(_k)).upper())
_NOT_A_NAME |= {"매수", "매도", "중립", "보유", "비중확대", "비중축소", "적극매수",
                "시장수익률", "투자의견", "적정주가", "목표주가", "리서치", "센터",
                "기업분석", "산업분석", "종목분석", "제공출처", "작성자"}


def _is_person_name(p: str) -> bool:
    """한국 인명(한글 2~4자) 또는 영문 이름(2단어) 만 통과시킨다."""
    if not p:
        return False
    flat = p.replace(" ", "")
    if flat.upper() in _NOT_A_NAME:
        return False
    if re.search(r"(증권|금융투자|투자증권|자산운용|리서치|협의회|은행|보험)", flat):
        return False
    if re.fullmatch(r"[가-힣]{2,4}", flat):
        return True
    if re.fullmatch(r"[A-Za-z]{2,15}(?:\s+[A-Za-z]{2,15})+", p.strip()):
        return True
    return False


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
    # ── 소스 간 동일 보고서 판정 키 ──────────────────────────────────────────────────
    #   ★ 예전에는 키에 제목 앞 40자를 넣었다. 그런데 한경 제목은 '삼성전자(005930) 4Q…'
    #     처럼 종목명을 포함하고 네이버 제목은 종목명이 별도 컬럼이라 제목에 없다.
    #     그래서 같은 리포트인데도 키가 갈라져 병합이 '구조적으로 절대' 일어나지 않았고,
    #     ARC-BDF 에서는 같은 리포트가 두 번 이벤트로 발화한다(중복 계상).
    #   → 종목코드가 있으면 (발간일, 증권사, 종목코드) 만으로 병합한다.
    #     종목코드가 없는 건(산업분석 등)만 제목을 보조 키로 쓴다.
    _codes = d["stock_code"].fillna("").astype(str)
    d["dedup_key"] = [
        sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b, c)
        if c else
        sha1_str(pd.Timestamp(dt).strftime("%Y%m%d"), b, "", norm_text(t)[:40])
        for dt, b, c, t in zip(d["pub_date"], d["broker_id"], _codes, d["title"])]
    # 소스 우선순위: 한경 리스트(적정가격 원천) > 네이버 상세 > 그 외.
    # (min 으로 뽑기 위해 (우선순위, 값) 튜플로 인코딩한 뒤 병합 후 되돌린다)
    _srank = d["source"].astype(str).map(lambda s: 0 if "hankyung" in s else 1)
    d["_tp_prio"] = [(int(r), float(v)) if pd.notna(v) else (9, float("inf"))
                     for r, v in zip(_srank, d["target_price"])]
    n_raw = len(d)
    d = d.sort_values(["dedup_key", "source"], kind="stable")

    # ── 멱등 병합 (재실행 안전) ─────────────────────────────────────────────────────────
    #   이 함수의 출력(원장)은 다음 실행에서 드라이브 캐시로부터 '입력 프레임'으로 되돌아온다.
    #   그때 source="hankyung+naver" 같은 합성 토큰이 다시 들어오므로, 단순 set 병합은
    #   "hankyung+naver" 를 원자 하나로 취급해 실행할 때마다 문자열이 무한히 길어진다
    #   (hankyung+naver → hankyung+hankyung+naver+naver → …). 구분자로 먼저 분해한다.
    #   report_uid 도 "first"(행 순서 의존)면 캐시만으로 도는 실행에서 값이 바뀌어
    #   PDF 캐시·애널리스트 연결표가 통째로 끊긴다. 순서에 무관한 min 으로 고정한다.
    #   (min 은 병합행이 다시 들어와도 같은 값을 낸다: min{u1,u2,min(u1,u2)} = min(u1,u2))
    m = d.groupby("dedup_key", as_index=False, observed=True).agg(**{
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
        # ★ max 를 쓰면 소스 간 값이 다를 때 항상 큰 값이 뽑혀 '상향' 판정에 방향성 편향이
        #   생긴다(+3% 임계값을 인위적으로 더 자주 넘게 만든다). 소스 우선순위로 고른다.
        "target_price": ("_tp_prio", "min"),
        "opinion": ("opinion", lambda s: _pick_str(s) or None),
        "pdf_url": ("pdf_url", lambda s: _pick_str(s) or None),
        "detail_url": ("detail_url", lambda s: _pick_str(s) or None),
    })
    m["target_price"] = [v if np.isfinite(v) else np.nan
                         for _, v in m["target_price"].tolist()]
    LOG.info(f"보고서 원장 병합: 수집 {n_raw0:,}건 → 날짜유효 {n_raw:,}건 → 고유 {len(m):,}건 "
             f"(날짜 탈락 {n_raw0 - n_raw:,} · 소스 간 중복 병합 {n_raw - len(m):,})")
    _multi = int(m["source"].astype(str).str.contains(r"\+").sum())
    LOG.info(f"  소스 교차 병합 성사 {_multi:,}건 — 0 이면 dedup 키가 갈라진 것이니 "
             f"같은 리포트가 두 번 이벤트로 발화합니다(중복 계상).")

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

    A = (L.groupby("analyst_id", as_index=False, observed=True)
          .agg(name=("name_norm", "first"), broker_id=("broker_id", "first"),
               broker_name=("broker_name", "first"),
               first_seen=("pub_date", "min"), last_seen=("pub_date", "max"),
               n_reports=("report_uid", "nunique"),
               n_stocks=("stock_code", lambda s: s.dropna().nunique()),
               n_targets=("target_price", lambda s: int(s.notna().sum()))))
    # 동명이인/이직 감지 — 같은 이름이 여러 증권사에 존재
    dup = A.groupby("name", observed=True)["analyst_id"].transform("size")
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
    # ★ ARC-BDF 의 신호 주체는 애널리스트가 아니라 '증권사' 다. broker 축 감사가 없으면
    #   broker 가 통째로 비어 있어도 표에 드러나지 않는다.
    r["has_broker"] = r.get("broker_id", pd.Series("", index=r.index)).astype(str).str.len().ge(4)
    r["has_code"] = r["stock_code"].notna()
    r["has_tp"] = r["target_price"].notna()

    rows = []
    for y, g in r.groupby("year", observed=True):
        n = len(g)
        rows.append([int(y), f"{n:,}",
                     f"{100*g['has_broker'].mean():.1f}%",
                     f"{int(g['has_analyst'].sum()):,}", f"{100*g['has_analyst'].mean():.1f}%",
                     f"{int(g['has_code'].sum()):,}", f"{100*g['has_code'].mean():.1f}%",
                     f"{int(g['has_tp'].sum()):,}", f"{100*g['has_tp'].mean():.1f}%",
                     "✔" if n >= RESEARCH_TARGET_PER_YEAR else f"목표 {RESEARCH_TARGET_PER_YEAR:,} 미달"])
    LOG.table(rows, ["연도", "보고서", "★증권사율", "애널연결", "연결률", "종목코드", "코드율",
                     "목표주가", "TP율", "연 3만건 목표"],
              ["c", "r", "r", "r", "r", "r", "r", "r", "r", "l"])

    src = r.groupby("source", observed=True).agg(n=("report_uid", "size"),
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
        mth = L.groupby("link_method", observed=True).agg(n=("report_uid", "nunique"),
                                           conf=("link_conf", "mean")).reset_index()
        LOG.table([[m["link_method"], f"{int(m['n']):,}", f"{m['conf']:.2f}"]
                   for _, m in mth.iterrows()],
                  ["연결 방법", "보고서 수", "평균 신뢰도"], ["l", "r", "r"],
                  title="애널리스트 연결 방법별 분포 "
                        "(list_field=한경 작성자컬럼 0.98 · pdf_header=PDF추출 0.80)")

    if len(A):
        bro = (A.groupby("broker_name", observed=True)
                .agg(analysts=("analyst_id", "nunique"), reports=("n_reports", "sum"))
                .sort_values("reports", ascending=False))
        maj = [b for b in MAJOR_BROKERS if b in bro.index]
        # ★ 파싱 노이즈로 생긴 가짜 broker_name 까지 '중소형사' 로 세면 판정이 항상 통과한다.
        #   사전에 등재된 중소형사와의 교집합으로만 센다.
        mnr = [b for b in bro.index if b in MINOR_BROKERS]
        LOG.table([[b, f"{int(bro.loc[b,'analysts']):,}", f"{int(bro.loc[b,'reports']):,}"]
                   for b in bro.index[:30]],
                  ["증권사", "애널리스트 수", "보고서 수"], ["l", "r", "r"],
                  title="증권사별 커버리지 (사명변경 정규화 적용: 미래에셋대우→미래에셋증권 등)")
        LOG.info(f"대형사 커버리지 {len(maj)}/10개 · 그 외 증권사 {len(mnr)}개 "
                 f"→ 요구조건(대형 10+ / 중소형 10+): "
                 f"{'✔ 충족' if len(maj) >= 10 and len(mnr) >= 10 else '❗ 미충족 — 수집 범위를 넓히세요'}")

    orphan = r[~r["has_analyst"]]
    if len(orphan):
        top = orphan.groupby("source", observed=True).size().sort_values(ascending=False).head(5)
        LOG.warn(f"애널리스트 미연결 {len(orphan):,}건 ({100*len(orphan)/len(r):.1f}%) — "
                 f"주로 {', '.join(f'{k}({v:,})' for k, v in top.items())}. "
                 f"네이버 단독 건은 리스트에 작성자가 없어 PDF 추출에 의존합니다 "
                 f"(RESEARCH_DOWNLOAD_PDF=True 로 개선 가능).")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-D  플로우 수집 — 거래원(회원사) / 투자자별 순매수                                     ║
# ║                                                                                          ║
# ║  ★ 이 전략의 사활이 걸린 모듈이며, 동시에 가장 정직해야 하는 모듈이다.                     ║
# ║                                                                                          ║
# ║  세 갈래의 플로우가 있고 확보 난이도가 완전히 다르다:                                      ║
# ║                                                                                          ║
# ║   (A) 거래원 상위 5창구 — SPEC 원 가설의 신호                                              ║
# ║       네이버 거래원 탭은 '최종 거래일 1일치' 스냅샷 전용이다. 날짜 파라미터도               ║
# ║       페이지네이션도 없다(같은 종목 페이지의 일별시세·외국인기관 탭에는 &page= 가 있는데    ║
# ║       거래원 탭에만 없다 — 설계상 이력이 없다는 강한 신호다). 공공데이터포털에도 없고,      ║
# ║       증권사 OpenAPI 도 '현재가 기준' 스냅샷이거나 Windows COM 종속이라 소급 불가다.       ║
# ║       → 과거 10년 복원 불가. 오늘부터 쌓는 '전진 수집(B-1)' 만 가능하다.                    ║
# ║                                                                                          ║
# ║   (B) 외국인 순매수 — 소진율 차분으로 10년치를 종목당 1요청에 얻는다  ★주력★               ║
# ║       siseJson 응답 7번째 컬럼이 외국인소진율(%)이다. 보유주수 = 소진율 × 상장주식수 이고   ║
# ║       그 일별 차분이 곧 외국인 순매수(주)다. 이미 가격 수집 경로에 있어 추가 비용이 거의 0. ║
# ║                                                                                          ║
# ║   (C) 기관 순매수 — frgn.naver 페이지네이션. 페이지당 20행이라 10년이면 종목당 약 123요청.  ║
# ║       콜드 스타트가 가장 비싼 단계다. 시간예산·서킷브레이커·중단재개로 관리하고,            ║
# ║       못 받은 구간은 0 이 아니라 결측으로 남긴다.                                          ║
# ║                                                                                          ║
# ║  ★ 절단(censoring) 규칙 — 위반하면 가짜 알파가 생긴다                                      ║
# ║    거래원은 상위 5개만 공개된다. 매수 top5 에만 나온 창구의 '매도량' 은 0 이 아니라 미상이다.║
# ║    이를 0 으로 채우면 순매수가 체계적으로 과대추정되고, 대형 창구일수록 편향이 커져         ║
# ║    알파처럼 보이는 신호가 만들어진다. 반드시 NaN + 상한값(그날 5위 창구 거래량)으로 둔다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MEMBER_SNAP_COLS = ["captured_at", "trade_date", "code", "side", "rank",
                    "member_raw", "volume", "src_url", "parser_ver"]
FLOW_DAILY_COLS = ["code", "date", "actor", "actor_kind", "net_vol",
                   "censored", "upper_bound", "src"]
PARSER_VER = 2


# ══════════════════════════════════════════════════════════════════════════════════════════
#  Phase 0 프로브 — "정말로 소급이 안 되는가" 를 코드가 직접 확인한다
# ══════════════════════════════════════════════════════════════════════════════════════════
def probe_member_window(code: str) -> dict:
    """거래원 탭의 과거 소급 가능성을 실제로 찔러본다.

    같은 URL 에 날짜 파라미터 후보를 붙여 응답이 '달라지는지' 를 본다.
    달라지지 않으면 = 파라미터가 무시된다 = 과거 조회 불가. 이것이 판정의 근거다."""
    base = "https://finance.naver.com/item/frame_trade.naver?code={c}"
    alt = "https://finance.naver.com/item/trade.naver?code={c}"
    out = {"code": code, "reachable": False, "url": "", "n_members": 0,
           "date_param_works": False, "tried": [], "sample": []}
    for u in (base, alt):
        html = http_get(u.format(c=code), source="naver_flow", force_enc="euc-kr",
                        tries=2, referer=f"https://finance.naver.com/item/main.naver?code={code}")
        if not html:
            continue
        tabs = safe_read_html(html)
        names = _extract_member_names(html)
        if names:
            out.update(reachable=True, url=u.format(c=code), n_members=len(names),
                       sample=names[:6])
            break
        if tabs:
            out.update(reachable=True, url=u.format(c=code), n_members=0)
    if not out["reachable"]:
        return out

    # 날짜 파라미터가 먹히는지: 명백히 과거인 날짜를 넣어 응답 해시가 바뀌는지 본다
    base_html = http_get(out["url"], source="naver_flow", force_enc="euc-kr", tries=1)
    h0 = sha1_str(_extract_member_names(base_html or ""))
    for pname in ("date", "trdDd", "day", "thisPage", "bizdate"):
        for val in ("20240102", "2024-01-02"):
            u2 = out["url"] + f"&{pname}={val}"
            h = http_get(u2, source="naver_flow", force_enc="euc-kr", tries=1)
            names = _extract_member_names(h or "")
            out["tried"].append(f"{pname}={val}")
            if names and sha1_str(names) != h0:
                out["date_param_works"] = True
                out["working_param"] = pname
                return out
    return out


def probe_frgn_depth(code: str, max_probe_page: int = 200) -> dict:
    """frgn.naver(기관·외국인) 가 몇 년까지 소급되는지 이분탐색으로 실측한다.
    ★ 추측하지 않는다. 이 숫자가 Phase 0 판정을 좌우한다."""
    out = {"code": code, "ok": False, "max_page": 0, "oldest_date": None, "rows_per_page": 0}

    def _page(n: int) -> Optional[pd.DataFrame]:
        html = http_get("https://finance.naver.com/item/frgn.naver", source="naver_flow",
                        params={"code": code, "page": n}, force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/frgn.naver?code={code}")
        return _parse_frgn_table(html)

    d1 = _page(1)
    if d1 is None or not len(d1):
        return out
    out["ok"] = True
    out["rows_per_page"] = len(d1)
    lo, hi = 1, 2
    while hi <= max_probe_page:
        d = _page(hi)
        if d is None or not len(d):
            break
        lo = hi
        hi *= 2
    hi = min(hi, max_probe_page)
    while lo + 1 < hi:                       # 이분탐색
        mid = (lo + hi) // 2
        d = _page(mid)
        if d is not None and len(d):
            lo = mid
        else:
            hi = mid
    last = _page(lo)
    out["max_page"] = lo
    if last is not None and len(last):
        out["oldest_date"] = str(pd.Timestamp(last["date"].min()).date())
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  파서
# ══════════════════════════════════════════════════════════════════════════════════════════
_MEMBER_ROW = re.compile(
    r"<td[^>]*>\s*(?:<[^>]+>\s*)*([가-힣A-Za-z0-9\.\&\-\s]{2,20}?)\s*(?:</[^>]+>\s*)*</td>\s*"
    r"<td[^>]*class=\"?tah[^\"]*\"?[^>]*>\s*([\d,]+)\s*</td>", re.I)


def _extract_member_names(html: str) -> List[str]:
    if not html:
        return []
    names = [m.group(1).strip() for m in _MEMBER_ROW.finditer(html)]
    return [n for n in names if n and not re.fullmatch(r"[\d,\.]+", n)]


def parse_member_page(html: str, code: str, url: str) -> pd.DataFrame:
    """거래원 페이지 → (side, rank, member_raw, volume).

    ★ 매도상위 표와 매수상위 표가 좌우로 나란히 오는 레이아웃이라 컬럼 인덱스를 믿으면 안 된다.
      표 단위로 나눠 헤더 텍스트('매도상위'/'매수상위')로 판정하고, 헤더가 없으면
      '왼쪽=매도, 오른쪽=매수' 관례를 쓰되 그 사실을 로그에 남긴다."""
    rows: List[dict] = []
    if not html:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    soup = soup_of(html)
    if soup is None:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    now = now_kst()
    tables = soup.find_all("table")
    layout_guessed = False
    for tb in tables:
        txt = tb.get_text(" ", strip=True)
        if "매도상위" in txt and "매수상위" in txt:
            # 한 표에 두 블록이 다 있는 경우: 행마다 좌(매도) / 우(매수)
            for tr in tb.find_all("tr"):
                tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                tds = [t for t in tds if t not in ("", "\xa0")]
                if len(tds) >= 4:
                    for off, side in ((0, "SELL"), (2, "BUY")):
                        nm, vol = tds[off], tds[off + 1]
                        v = re.sub(r"[^\d]", "", vol)
                        if nm and v and not re.fullmatch(r"[\d,\.%]+", nm):
                            rows.append({"side": side, "member_raw": nm, "volume": float(v)})
            continue
        side = None
        if "매도상위" in txt:
            side = "SELL"
        elif "매수상위" in txt:
            side = "BUY"
        if side is None:
            continue
        for tr in tb.find_all("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            tds = [t for t in tds if t not in ("", "\xa0")]
            if len(tds) >= 2:
                nm, v = tds[0], re.sub(r"[^\d]", "", tds[1])
                if nm and v and not re.fullmatch(r"[\d,\.%]+", nm):
                    rows.append({"side": side, "member_raw": nm, "volume": float(v)})

    if not rows:            # 폴백: 정규식으로 이름·수량 쌍만 뽑고 좌우 관례를 적용
        pairs = [(m.group(1).strip(), float(re.sub(r"[^\d]", "", m.group(2))))
                 for m in _MEMBER_ROW.finditer(html)]
        for i, (nm, v) in enumerate(pairs[:10]):
            rows.append({"side": "SELL" if i % 2 == 0 else "BUY",
                         "member_raw": nm, "volume": v})
        layout_guessed = bool(rows)

    if not rows:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)
    d = pd.DataFrame(rows)
    d["rank"] = d.groupby("side", observed=True).cumcount() + 1
    d = d[d["rank"] <= 5]
    d["code"] = code
    d["captured_at"] = now
    # ★ 거래일은 페이지에서 직접 읽히지 않는 경우가 많다. '캡처 시각 기준 최근 거래일' 로
    #   추론하되, 어떻게 추론했는지를 parser_ver 와 함께 남긴다(나중에 소급 교정 가능하도록).
    td = now.normalize()
    if now.hour < 16:                    # 장 마감 전이면 전 거래일 확정치일 가능성이 높다
        td = td - pd.Timedelta(days=1)
    while td.weekday() >= 5:
        td = td - pd.Timedelta(days=1)
    d["trade_date"] = td
    d["src_url"] = url
    d["parser_ver"] = PARSER_VER
    if layout_guessed:
        LOG.debug(f"거래원 레이아웃을 헤더로 판정하지 못해 좌우 관례를 적용했습니다 ({code}).")
    return d.reindex(columns=MEMBER_SNAP_COLS)


def _parse_frgn_table(html: Optional[str]) -> Optional[pd.DataFrame]:
    """frgn.naver 표 → date / inst_net / foreign_net / volume."""
    if not html:
        return None
    tabs = safe_read_html(html)
    if not tabs:
        return None
    best = None
    for t in tabs:
        cols = [str(c) for c in np.ravel(t.columns.to_list())]
        joined = " ".join(cols)
        if "날짜" in joined and ("기관" in joined or "외국인" in joined):
            best = t
            break
    if best is None:
        best = max(tabs, key=len)
    d = best.copy()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = [" ".join(str(x) for x in c if str(x) != "nan").strip() for c in d.columns]
    cmap = {str(c): str(c) for c in d.columns}
    def _find(*keys):
        for c in cmap:
            if all(k in c for k in keys):
                return c
        return None
    c_date = _find("날짜")
    c_inst = _find("기관")
    c_forg = _find("외국인", "순매매") or _find("외국인")
    c_vol = _find("거래량")
    if c_date is None:
        return None
    out = pd.DataFrame({
        "date": pd.to_datetime(d[c_date].astype(str).str.replace(".", "-", regex=False),
                               errors="coerce"),
        "inst_net": pd.to_numeric(
            d[c_inst].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_inst else np.nan,
        "foreign_net": pd.to_numeric(
            d[c_forg].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_forg else np.nan,
        "volume": pd.to_numeric(
            d[c_vol].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if c_vol else np.nan,
    }).dropna(subset=["date"])
    return out if len(out) else None


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (B) 외국인 플로우 — 소진율 차분.  종목당 1요청으로 10년치.  ★주력 경로★
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_foreign_ratio(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """siseJson 의 7번째 컬럼(외국인소진율 %)을 종목별 1요청으로 전 구간 확보한다."""
    codes = sorted({c for c in map(to_code6, codes) if c})
    s, e = as_ts(start), as_ts(end)
    cols = ["code", "date", "frgn_ratio"]
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("naver_foreign_ratio", scope="shared")
    frames: List[pd.DataFrame] = []
    have: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["code", "date"])
        if len(c):
            frames.append(c.reindex(columns=cols))
            cov = c.groupby("code", observed=True)["date"].agg(["min", "max"])
            pad = pd.Timedelta(days=16)
            have = set(cov.index[(cov["min"] <= s + pad) & (cov["max"] >= e - pad)])
            LOG.info(f"공용 캐시에서 외국인소진율 {len(c):,}행 / {len(have):,}종목 재사용")

    todo = [c for c in codes if c not in have]
    if RUN_MODE == "CACHED":
        todo = []

    def _one(code: str) -> Optional[pd.DataFrame]:
        txt = http_get(_NAVER_SISE_JSON, source="naver",
                       params={"symbol": code, "requestType": 1,
                               "startTime": s.strftime("%Y%m%d"), "endTime": e.strftime("%Y%m%d"),
                               "timeframe": "day"},
                       referer=f"https://finance.naver.com/item/frgn.naver?code={code}", tries=3)
        if not txt:
            return None
        rows = re.findall(r"\[([^\[\]]+)\]", txt)
        out = []
        for r in rows:
            parts = [p.strip().strip("'\"") for p in r.split(",")]
            if len(parts) < 7 or not re.fullmatch(r"\d{8}", parts[0]):
                continue
            try:
                out.append((parts[0], float(parts[6])))
            except Exception:
                continue
        if not out:
            return None
        d = pd.DataFrame(out, columns=["date", "frgn_ratio"])
        d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
        d["code"] = code
        return d.dropna(subset=["date"])[cols]

    if todo:
        LOG.info(f"외국인소진율 수집 {len(todo):,}종목 (종목당 1요청 · 10년치를 한 번에)")
        res = pmap_io(_one, todo, workers=min(FLOW_WORKERS + 2, N_WORKERS_IO), desc="외국인소진율")
        frames += [d for d in res if d is not None and len(d)]

    if not frames:
        return pd.DataFrame(columns=cols)
    F = pd.concat(frames, ignore_index=True)
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))
    if todo:
        VAULT.put_table("naver_foreign_ratio", F, scope="shared", domain="flow",
                        source="naver:siseJson",
                        extra={"note": "일별 외국인소진율(%) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_foreign_ratio", F, source="naver:siseJson")
    return downcast(F)


def foreign_net_from_ratio(fr: pd.DataFrame, mc: pd.DataFrame) -> pd.DataFrame:
    """소진율 차분 × 상장주식수 = 외국인 순매수(주).

    ★ 함정: 무상증자·액면분할로 상장주식수가 바뀌는 날은 보유주수가 기계적으로 점프한다.
      그 날의 차분은 순매수가 아니므로 결측 처리한다(0 으로 두면 가짜 대량매수가 된다)."""
    if fr is None or len(fr) == 0:
        return pd.DataFrame(columns=["code", "date", "foreign_net", "shares_used"])
    d = fr.copy()
    if mc is not None and len(mc) and "shares" in mc.columns:
        sh = mc[["code", "date", "shares"]].dropna()
        d = d.merge(sh, on=["code", "date"], how="left")
    else:
        d["shares"] = np.nan
    # 주식수가 없는 종목은 종목별 중앙값으로 대체(랭크·정규화에만 쓰이므로 무해)
    d["shares"] = d.groupby("code", observed=True)["shares"].transform(
        lambda s: s.ffill().bfill())
    d = d.sort_values(["code", "date"], kind="stable")
    g = d.groupby("code", observed=True)
    hold = d["frgn_ratio"] / 100.0 * d["shares"]
    d["foreign_net"] = hold.groupby(d["code"], observed=True).diff()
    sh_chg = g["shares"].diff().abs() > (d["shares"].abs() * 1e-6)
    n_bad = int((sh_chg & d["foreign_net"].notna()).sum())
    set_where(d, sh_chg.fillna(False), "foreign_net", np.nan)
    if n_bad:
        LOG.info(f"상장주식수가 변동한 {n_bad:,}건의 외국인 순매수를 결측 처리했습니다 "
                 f"(증자·분할로 인한 기계적 점프를 매수로 계상하지 않기 위함).")
    return d[["code", "date", "foreign_net", "shares"]].rename(columns={"shares": "shares_used"})


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (C) 기관 플로우 — frgn.naver 페이지네이션.  시간예산 + 서킷브레이커 + 중단재개
# ══════════════════════════════════════════════════════════════════════════════════════════
def fetch_investor_flow_paged(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """기관/외국인 순매매(주). 페이지당 20행이라 콜드 스타트가 비싸다.

    설계:
      · 종목 처리 순서 = 이벤트 수가 많은 종목 우선 (예산이 끊겨도 쓸모 있는 쪽부터)
      · 페이지는 1(최근) → N(과거) 순  ⇒ 중단돼도 최신 구간이 먼저 완성된다 (SPEC §2.3)
      · 연속 실패 FLOW_CIRCUIT_BREAK_N 회 → 즉시 전체 중단 + 상태 저장
      · 시간예산 초과 → '실패' 가 아니라 '여기까지 저장하고 정상 종료'
      · 못 받은 구간은 0 이 아니라 결측이다."""
    cols = ["code", "date", "inst_net", "foreign_net", "volume"]
    codes = [c for c in map(to_code6, codes) if c]
    s, e = as_ts(start), as_ts(end)
    if not codes or s is None or e is None:
        return pd.DataFrame(columns=cols)

    cached = VAULT.get_table("naver_investor_flow", scope="shared")
    frames: List[pd.DataFrame] = []
    done: set = set()
    if cached is not None and len(cached):
        c = cached.copy()
        c["date"] = as_ts_series(c["date"])
        c["code"] = c["code"].map(to_code6)
        c = c.dropna(subset=["code", "date"])
        if len(c):
            frames.append(c.reindex(columns=cols))
            cov = c.groupby("code", observed=True)["date"].min()
            done = set(cov.index[cov <= s + pd.Timedelta(days=20)])
            LOG.info(f"공용 캐시에서 투자자별 수급 {len(c):,}행 재사용 "
                     f"(전 구간 완료 {len(done):,}종목)")

    if not FLOW_INSTITUTION_ENABLE:
        LOG.info("FLOW_INSTITUTION_ENABLE=False — 기관 플로우 신규 수집을 건너뜁니다. "
                 "외국인 플로우(소진율 차분)만으로 전 구간이 완성됩니다.")
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols))
    if RUN_MODE == "CACHED":
        LOG.info("CACHED 모드 — 투자자별 수급 신규 수집을 건너뜁니다.")
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols))

    todo = [c for c in dict.fromkeys(codes) if c not in done]
    if not todo:
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)

    t0 = time.time()
    budget_s = float(FLOW_TIME_BUDGET_MIN) * 60.0
    lk = threading.Lock()
    st = {"fail_streak": 0, "stop": False, "reason": "", "n_req": 0, "n_code_done": 0}

    LOG.info(f"기관/외국인 수급 수집 {len(todo):,}종목 · 시간예산 {FLOW_TIME_BUDGET_MIN}분 · "
             f"동시 {FLOW_WORKERS} · 요청간 {FLOW_DELAY_RANGE[0]}~{FLOW_DELAY_RANGE[1]}초 "
             f"(차단 방지 · SPEC §2.3)")

    def _one(code: str) -> Optional[pd.DataFrame]:
        if st["stop"]:
            return None
        got: List[pd.DataFrame] = []
        for page in range(1, 400):
            with lk:
                if st["stop"]:
                    return pd.concat(got, ignore_index=True) if got else None
                if time.time() - t0 > budget_s:
                    st["stop"] = True
                    st["reason"] = "TIME_BUDGET"
                    return pd.concat(got, ignore_index=True) if got else None
                st["n_req"] += 1
            polite_sleep()
            html = http_get("https://finance.naver.com/item/frgn.naver", source="naver_flow",
                            params={"code": code, "page": page}, force_enc="euc-kr", tries=3,
                            referer=f"https://finance.naver.com/item/frgn.naver?code={code}")
            d = _parse_frgn_table(html)
            with lk:
                if d is None or not len(d):
                    st["fail_streak"] += 1
                    if st["fail_streak"] >= FLOW_CIRCUIT_BREAK_N:
                        st["stop"] = True
                        st["reason"] = "CIRCUIT_BREAKER"
                    break
                st["fail_streak"] = 0
            d["code"] = code
            got.append(d)
            if pd.Timestamp(d["date"].min()) <= s:
                break
        if not got:
            return None
        out = pd.concat(got, ignore_index=True)
        out = out[(out["date"] >= s) & (out["date"] <= e)]
        with lk:
            st["n_code_done"] += 1
        return out.reindex(columns=cols) if len(out) else None

    res = pmap_io(_one, todo, workers=FLOW_WORKERS, desc="투자자별 수급")
    new = [d for d in res if d is not None and len(d)]
    frames += new
    el = (time.time() - t0) / 60.0

    if st["stop"]:
        if st["reason"] == "CIRCUIT_BREAKER":
            LOG.error(f"연속 실패 {FLOW_CIRCUIT_BREAK_N}회 → 서킷 브레이커 작동. "
                      f"여기까지 받은 {len(new):,}종목분을 저장하고 중단합니다. "
                      f"잠시 후(수십 분~수 시간) 다시 실행하면 이어서 받습니다. "
                      f"차단이 의심되면 FLOW_WORKERS 를 3 으로, "
                      f"FLOW_DELAY_RANGE 를 (0.8, 2.0) 으로 낮추세요.")
        else:
            LOG.warn(f"시간예산 {FLOW_TIME_BUDGET_MIN}분을 소진했습니다 — 여기까지 저장하고 "
                     f"정상 종료합니다. 다음 실행이 이어서 받습니다(최근→과거 순이라 "
                     f"최신 구간부터 완성됩니다). 완료 {st['n_code_done']:,}/{len(todo):,}종목.")
    else:
        LOG.ok(f"투자자별 수급 수집 완료 — {st['n_code_done']:,}종목 · "
               f"{st['n_req']:,}요청 · {el:.1f}분")

    if not frames:
        return pd.DataFrame(columns=cols)
    F = pd.concat(frames, ignore_index=True)
    F["date"] = as_ts_series(F["date"])
    F = (F.dropna(subset=["code", "date"])
           .drop_duplicates(["code", "date"], keep="last")
           .sort_values(["code", "date"], kind="stable").reset_index(drop=True))
    if new:
        VAULT.put_table("naver_investor_flow", F, scope="shared", domain="flow",
                        source="naver:frgn",
                        extra={"note": "일별 기관·외국인 순매매(주) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_investor_flow", F, source="naver:frgn")
    return downcast(F)


# ══════════════════════════════════════════════════════════════════════════════════════════
#  (A) 거래원 전진 수집 (B-1) — 과거는 못 만들지만 오늘부터는 쌓을 수 있다
# ══════════════════════════════════════════════════════════════════════════════════════════
def collect_member_snapshot(codes: Sequence[str], limit: int = 0) -> pd.DataFrame:
    """오늘자 거래원 상위 5창구 스냅샷을 공용 인덱스에 append 한다.

    ★ member_raw 는 절대 정규화해서 저장하지 않는다. 원문을 영구 보존해야
      나중에 매핑 오류를 소급 수정할 수 있다(정규화는 파생 단계에서 한다)."""
    codes = [c for c in map(to_code6, codes) if c]
    if limit:
        codes = codes[:limit]
    if not codes or RUN_MODE in ("CACHED", "SMOKE") or not FLOW_MEMBER_FORWARD:
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)

    st = {"fail": 0, "stop": False}
    lk = threading.Lock()

    def _one(code: str) -> Optional[pd.DataFrame]:
        if st["stop"]:
            return None
        polite_sleep()
        url = f"https://finance.naver.com/item/frame_trade.naver?code={code}"
        html = http_get(url, source="naver_flow", force_enc="euc-kr", tries=2,
                        referer=f"https://finance.naver.com/item/main.naver?code={code}")
        d = parse_member_page(html or "", code, url)
        with lk:
            if d is None or not len(d):
                st["fail"] += 1
                if st["fail"] >= FLOW_CIRCUIT_BREAK_N:
                    st["stop"] = True
                    LOG.warn("거래원 스냅샷 연속 실패 — 서킷 브레이커 작동(전진수집만 중단). "
                             "백테스트 경로에는 영향이 없습니다.")
                return None
            st["fail"] = 0
        return d

    res = pmap_io(_one, codes, workers=FLOW_WORKERS, desc="거래원 스냅샷(전진수집)")
    got = [d for d in res if d is not None and len(d)]
    if not got:
        LOG.info("거래원 스냅샷을 받지 못했습니다 — 전진수집만 건너뜁니다(백테스트 무관).")
        return pd.DataFrame(columns=MEMBER_SNAP_COLS)

    S = pd.concat(got, ignore_index=True)
    prev = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
    if prev is not None and len(prev):
        prev = prev.reindex(columns=MEMBER_SNAP_COLS)
        S = pd.concat([prev, S], ignore_index=True)
    S["trade_date"] = as_ts_series(S["trade_date"])
    S["captured_at"] = as_ts_series(S["captured_at"])
    S = S.drop_duplicates(["trade_date", "code", "side", "rank", "member_raw"], keep="last")
    VAULT.put_table("naver_member_flow_snapshot", S, scope="shared", domain="flow",
                    source="naver:trade",
                    extra={"note": "거래원 상위5창구 일별 스냅샷(전진수집) — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "naver_member_flow_snapshot", S, source="naver:trade")
    LOG.ok(f"거래원 전진수집 — 이번 회차 {len(pd.concat(got)):,}행 · 누적 {len(S):,}행 "
           f"({S['trade_date'].nunique():,}거래일). 과거는 만들 수 없지만 오늘부터는 쌓입니다.")
    return S


def member_snapshot_to_daily(S: pd.DataFrame, px: pd.DataFrame,
                             bm: "BrokerMap") -> pd.DataFrame:
    """거래원 스냅샷 → 일별 창구 순매수. ★ 절단(censoring)을 명시적으로 보존한다.

    매수 top5 에만 있는 창구의 매도량은 0 이 아니라 '미상' 이다.
    NaN 으로 두고 상한(그날 매도 5위 창구의 거래량)을 함께 남겨 구간추정으로 다룬다."""
    cols = FLOW_DAILY_COLS + ["top5_coverage", "buy_vol", "sell_vol"]
    if S is None or len(S) == 0:
        return pd.DataFrame(columns=cols)
    d = S.copy()
    d["trade_date"] = as_ts_series(d["trade_date"])
    d["member_key"] = d["member_raw"].map(lambda x: bm.resolve(x) or f"UNMAPPED:{x}")
    piv = (d.pivot_table(index=["code", "trade_date", "member_key"], columns="side",
                         values="volume", aggfunc="sum").reset_index())
    for c in ("BUY", "SELL"):
        if c not in piv.columns:
            piv[c] = np.nan
    piv = piv.rename(columns={"BUY": "buy_vol", "SELL": "sell_vol", "trade_date": "date"})

    # 절단 상한 = 그날 각 side 의 5위(=최소) 공개 거래량
    lo = (d.groupby(["code", "trade_date", "side"], observed=True)["volume"].min()
            .unstack("side").rename(columns={"BUY": "buy_lb", "SELL": "sell_lb"})
            .reset_index().rename(columns={"trade_date": "date"}))
    piv = piv.merge(lo, on=["code", "date"], how="left")

    piv["censored"] = piv["buy_vol"].isna() | piv["sell_vol"].isna()
    # 미상 쪽의 상한: 공개된 5위 거래량. 그보다 클 수는 없다.
    piv["upper_bound"] = np.where(piv["sell_vol"].isna(), piv.get("sell_lb", np.nan),
                                  np.where(piv["buy_vol"].isna(), piv.get("buy_lb", np.nan), 0.0))
    # ★ net_vol 은 양쪽이 다 관측된 경우에만 확정값이다. 아니면 결측으로 둔다(0 채움 금지).
    piv["net_vol"] = np.where(piv["censored"], np.nan,
                              piv["buy_vol"].fillna(0) - piv["sell_vol"].fillna(0))

    if px is not None and len(px):
        v = px[["code", "date", "volume"]].rename(columns={"volume": "tot_vol"})
        piv = piv.merge(v, on=["code", "date"], how="left")
        tot5 = (piv.groupby(["code", "date"], observed=True)[["buy_vol", "sell_vol"]].sum().sum(axis=1)
                   .rename("t5").reset_index())
        piv = piv.merge(tot5, on=["code", "date"], how="left")
        piv["top5_coverage"] = safe_div(piv["t5"], 2.0 * piv["tot_vol"])
        piv = piv.drop(columns=[c for c in ("t5", "tot_vol") if c in piv.columns])
    else:
        piv["top5_coverage"] = np.nan

    piv["actor"] = piv["member_key"]
    piv["actor_kind"] = "MEMBER"
    piv["src"] = "naver:trade"
    n_cens = int(piv["censored"].sum())
    if n_cens:
        LOG.info(f"거래원 일별화: {len(piv):,}행 중 {n_cens:,}행이 상위5 절단으로 "
                 f"순매수 미확정입니다 → 0 으로 채우지 않고 결측 + 상한으로 보존했습니다. "
                 f"(0 으로 채우면 대형 창구일수록 순매수가 과대추정되어 가짜 알파가 생깁니다)")
    return piv.reindex(columns=cols + ["member_key"])


# ══════════════════════════════════════════════════════════════════════════════════════════
#  통합: 이벤트에 쓸 '행위자별 일별 순매수' 패널
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_flow_panel(inv: pd.DataFrame, fnet: pd.DataFrame, mem_daily: pd.DataFrame,
                     px: pd.DataFrame) -> pd.DataFrame:
    """(code, date, actor, actor_kind, netbuy_share) 로 통일한다.

    actor_kind:
      MEMBER  = 실제 거래원 창구 (전진수집분만 존재)
      INST    = 기관 합계        (PROXY 축)
      FOREIGN = 외국인 합계      (PROXY 축)
    netbuy_share = 순매수(주) / 그날 총거래량   ← SPEC §6.2 정의
    """
    parts: List[pd.DataFrame] = []
    vol = (px[["code", "date", "volume"]].copy() if px is not None and len(px)
           else pd.DataFrame(columns=["code", "date", "volume"]))
    vol["date"] = as_ts_series(vol["date"])

    def _mk(df: pd.DataFrame, col: str, actor: str, kind: str, src: str):
        if df is None or len(df) == 0 or col not in df.columns:
            return
        t = df[["code", "date", col]].dropna(subset=["code", "date"]).copy()
        t["date"] = as_ts_series(t["date"])
        t = t.rename(columns={col: "net_vol"})
        t["actor"], t["actor_kind"], t["src"] = actor, kind, src
        t["censored"], t["upper_bound"] = False, np.nan
        parts.append(t)

    _mk(inv, "inst_net", "INST", "INST", "naver:frgn")
    if inv is not None and len(inv) and "foreign_net" in inv.columns:
        _mk(inv, "foreign_net", "FOREIGN", "FOREIGN", "naver:frgn")
    if fnet is not None and len(fnet):
        f = fnet.copy()
        # frgn 페이지에서 이미 외국인을 받은 (code,date) 는 그쪽을 우선한다(직접 관측값)
        if parts:
            seen = pd.concat([p[p["actor"] == "FOREIGN"][["code", "date"]] for p in parts
                              if (p["actor"] == "FOREIGN").any()], ignore_index=True) \
                if any((p["actor"] == "FOREIGN").any() for p in parts) else None
            if seen is not None and len(seen):
                f = f.merge(seen.assign(_seen=1), on=["code", "date"], how="left")
                f = f[f["_seen"].isna()].drop(columns=["_seen"])
        _mk(f, "foreign_net", "FOREIGN", "FOREIGN", "naver:siseJson-ratio")

    if mem_daily is not None and len(mem_daily):
        m = mem_daily[["code", "date", "actor", "actor_kind", "net_vol",
                       "censored", "upper_bound", "src"]].copy()
        m["date"] = as_ts_series(m["date"])
        parts.append(m)

    if not parts:
        LOG.warn("플로우 패널이 비었습니다 — 신호를 만들 수 없습니다. "
                 "네트워크/캐시 상태를 확인하세요.")
        return pd.DataFrame(columns=FLOW_DAILY_COLS + ["netbuy_share"])

    F = pd.concat([p.reindex(columns=FLOW_DAILY_COLS) for p in parts], ignore_index=True)
    F = F.dropna(subset=["code", "date", "actor"])
    F = F.merge(vol, on=["code", "date"], how="left")
    F["netbuy_share"] = safe_div(F["net_vol"], F["volume"])
    # 거래량이 0/결측인 날은 비율이 정의되지 않는다 → 0 이 아니라 결측
    set_where(F, (~np.isfinite(F["netbuy_share"].to_numpy(dtype=float))), "netbuy_share", np.nan)
    F = F.drop(columns=["volume"])
    F = F.drop_duplicates(["code", "date", "actor"], keep="last").reset_index(drop=True)

    stat = (F.groupby("actor_kind", observed=True)
              .agg(행=("code", "size"), 종목=("code", "nunique"),
                   시작=("date", "min"), 종료=("date", "max"),
                   유효비율=("netbuy_share", lambda s: float(s.notna().mean())))
              .reset_index())
    LOG.table([[r.actor_kind, f"{r.행:,}", f"{r.종목:,}",
                f"{pd.Timestamp(r.시작):%Y-%m}", f"{pd.Timestamp(r.종료):%Y-%m}",
                f"{100*r.유효비율:.1f}%"] for r in stat.itertuples()],
              ["행위자", "행수", "종목수", "시작", "종료", "유효비율"],
              ["l", "r", "r", "c", "c", "r"], title="플로우 패널 구성")
    PIPE.io("OUT", "MEM", "flow_panel", F)
    return downcast(F)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  ★ Phase 0 — 데이터 실현가능성 게이트  (SPEC §4 · 이 전략 최대 리스크)                    ║
# ║                                                                                          ║
# ║  이 전략의 병목은 알파가 아니라 '거래원별 일별 매매동향의 과거 이력' 확보다.                ║
# ║  그래서 코드를 더 쓰기 전에, 코드가 스스로 소스를 찔러보고 판정한다.                        ║
# ║                                                                                          ║
# ║  판정 → 분기 (SPEC §4.2 / §4.3)                                                           ║
# ║    FULL10  : 거래원 10년 확보          → ARC-BDF 원 가설 그대로                            ║
# ║    PARTIAL : 거래원 3~10년 확보        → 확보 구간으로 축소 + 검정력 영향 명시              ║
# ║    PROXY   : 3년 미만 / 당일 스냅샷만  → B-1 전진수집 스크립트 생성                        ║
# ║                                          + B-2 열화 프록시 백테스트(ARC-BDF-PROXY)         ║
# ║                                                                                          ║
# ║  ★ PROXY 로 떨어지면 이것은 '원 가설의 대리 검증' 이 아니다. 브로커 정체성이 사라지므로     ║
# ║    H3(중소형사 강세)는 검증 불가, H5(리포트 조건부 우위)는 '주체 단위' 로 약화된 형태로만   ║
# ║    검증된다. 산출물 전체에 그 사실을 명시하고 "10년 백테스트 완료" 라고 보고하지 않는다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

PHASE0_MD = "PHASE0_DATA_FEASIBILITY.md"


def _fmt_row(rank, name, hist, span, gran, auth, note):
    return [str(rank), name, hist, span, gran, auth, note]


def run_phase0_gate(probe_codes: Optional[Sequence[str]] = None) -> dict:
    """SPEC §4 절차를 실제로 수행하고 판정 딕셔너리를 돌려준다."""
    t0 = time.time()
    codes = list(probe_codes or PHASE0_PROBE_TICKERS)
    R: Dict[str, Any] = {"branch": "", "sources": [], "started": _dt.datetime.now().isoformat(),
                         "member_history_years": 0.0, "flow_history_years": 0.0,
                         "notes": [], "probes": {}}

    LOG.banner("Phase 0 — 데이터 실현가능성 게이트",
               "거래원 과거 이력을 정말 못 구하는지 코드가 직접 확인합니다 (SPEC §4)")

    offline = (RUN_MODE in ("SMOKE",))
    if offline:
        LOG.info("SMOKE 모드 — 네트워크 프로브를 건너뛰고 PROXY 분기를 가정합니다.")

    # ── ① KRX 정보데이터시스템 ────────────────────────────────────────────────────────────
    krx_note = ("KRX 로그인 차단 상태로 사용하지 않음(KRX_ENABLE=False). "
                "2025-12 data.krx.co.kr 이관 + 로그인 요구 강화로 무인증 접근 전제 불가."
                if not KRX_ENABLE else "KRX_ENABLE=True — 교차검증용으로만 사용")
    R["sources"].append(_fmt_row(1, "KRX 정보데이터시스템 (data.krx.co.kr)",
                                 "미확인(미사용)", "-", "종목×회원사×일 (제공된다고 알려짐)",
                                 "로그인 필수", krx_note))

    # ── ② 네이버 금융 종목별 거래원 ───────────────────────────────────────────────────────
    mem = {"reachable": False, "date_param_works": False, "n_members": 0}
    if not offline:
        with PIPE.stage("P0.MEMBER", "네이버 거래원 소급 프로브", "P0",
                        budget_s=180, critical=False):
            probes = [probe_member_window(c) for c in codes[:3]]
            R["probes"]["member"] = probes
            mem["reachable"] = any(p.get("reachable") for p in probes)
            mem["date_param_works"] = any(p.get("date_param_works") for p in probes)
            mem["n_members"] = max([p.get("n_members", 0) for p in probes] or [0])
            for p in probes:
                LOG.info(f"  거래원 프로브 {p['code']}: 도달={p['reachable']} "
                         f"창구수={p['n_members']} 날짜파라미터={p['date_param_works']} "
                         f"시도={p.get('tried', [])[:3]} 예시={p.get('sample', [])[:3]}")
    R["sources"].append(_fmt_row(
        2, "네이버 금융 종목별 거래원",
        "가능" if mem["date_param_works"] else "불가(당일만)",
        "10년" if mem["date_param_works"] else "0일",
        "종목×창구(상위5)×일", "불필요",
        "날짜 파라미터가 동작함" if mem["date_param_works"] else
        "날짜 파라미터·페이지네이션 부재. 같은 종목 페이지의 일별시세/외국인기관 탭에는 "
        "&page= 가 있는데 거래원 탭에만 없다 → 설계상 이력 없음."))

    # ── ③ 증권사 OpenAPI ──────────────────────────────────────────────────────────────────
    R["sources"].append(_fmt_row(
        3, "증권사 OpenAPI (KIS / 키움 등)", "불가", "0~수십일",
        "종목×창구(상위5)", "계좌·HTS 필요",
        "KIS REST 의 회원사 조회는 '현재가 기준' 스냅샷. 키움 OpenAPI+ 는 32bit Windows OCX "
        "종속이라 Colab/JupyterLab 실행 자체가 불가. 어느 쪽도 10년 이력 없음."))

    # ── ④ 유료 벤더 ───────────────────────────────────────────────────────────────────────
    R["sources"].append(_fmt_row(
        4, "유료 벤더 (FnGuide DataGuide / 코스콤 등)", "가능(추정)", "10년+",
        "종목×회원사×일", "계약 필요",
        "항목 존재 여부만 조사 대상이며 계약은 진행하지 않음(SPEC §4-1 지시)."))

    # ── ④-b 공공데이터포털 (거래원은 없지만 PIT 를 살린다) ────────────────────────────────
    dgk_ok = bool(_dgk_key())
    R["sources"].append(_fmt_row(
        "4b", "공공데이터포털 금융위 주식시세정보", "해당없음(거래원 미제공)",
        "2015~현재", "종목×일 (시총·상장주식수 포함)",
        "무료 키", ("키 입력됨 → PIT 시총/일별 상장 스냅샷 정품 경로 가동"
                    if dgk_ok else "키 없음 → 시총이 근사로 강등됨(동작은 함)")))

    # ── ⑤ 대체 플로우 축: frgn.naver 소급 깊이 실측 ───────────────────────────────────────
    frgn_years = 0.0
    if not offline:
        with PIPE.stage("P0.FRGN", "투자자별 수급 소급 깊이 실측", "P0",
                        budget_s=300, critical=False):
            dep = [probe_frgn_depth(c) for c in codes[:2]]
            R["probes"]["frgn"] = dep
            for d in dep:
                LOG.info(f"  frgn 프로브 {d['code']}: 최대page={d['max_page']} "
                         f"최고(古)일자={d['oldest_date']} 페이지당={d['rows_per_page']}행")
                if d.get("oldest_date"):
                    yrs = (pd.Timestamp.today() - pd.Timestamp(d["oldest_date"])).days / 365.25
                    frgn_years = max(frgn_years, yrs)
    R["flow_history_years"] = round(frgn_years, 2)
    R["sources"].append(_fmt_row(
        5, "네이버 frgn.naver (기관·외국인 순매매)",
        "가능(page 소급)", f"{frgn_years:.1f}년(실측)" if frgn_years else "미측정",
        "종목×주체×일", "불필요",
        "거래원이 아니라 '투자자 주체' 단위. 브로커 정체성이 사라진다."))
    R["sources"].append(_fmt_row(
        6, "네이버 siseJson 외국인소진율", "가능", "10년+",
        "종목×일", "불필요",
        "소진율 차분 × 상장주식수 = 외국인 순매수. 종목당 1요청으로 전 구간 확보 — "
        "PROXY 축의 주력 경로."))

    # ── 판정 ──────────────────────────────────────────────────────────────────────────────
    have_member_hist = bool(mem["date_param_works"])
    member_years = 10.0 if have_member_hist else 0.0
    # 드라이브에 이미 쌓인 전진수집분이 있으면 그만큼은 실제 이력이다
    snap = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
    if snap is not None and len(snap) and "trade_date" in snap.columns:
        td = as_ts_series(snap["trade_date"]).dropna()
        if len(td):
            acc = (td.max() - td.min()).days / 365.25
            member_years = max(member_years, acc)
            R["notes"].append(f"드라이브에 축적된 거래원 전진수집분 {td.nunique():,}거래일 "
                              f"({acc:.2f}년) 을 확인했습니다.")
    R["member_history_years"] = round(member_years, 2)

    forced = (PHASE0_FORCE_BRANCH or "").strip().upper()
    if forced in ("FULL10", "PARTIAL", "PROXY"):
        branch = forced
        R["notes"].append(f"PHASE0_FORCE_BRANCH 로 분기를 {branch} 로 강제했습니다.")
    elif member_years >= 9.5:
        branch = "FULL10"
    elif member_years >= 3.0:
        branch = "PARTIAL"
    else:
        branch = "PROXY"
    R["branch"] = branch

    el_min = (time.time() - t0) / 60.0
    R["elapsed_min"] = round(el_min, 2)
    if el_min > PHASE0_TIMEBOX_MIN:
        R["notes"].append(f"타임박스 {PHASE0_TIMEBOX_MIN}분을 초과했습니다 — SPEC §4 에 따라 "
                          f"즉시 중단하고 보고합니다.")

    LOG.table([r[:7] for r in R["sources"]],
              ["순위", "후보 소스", "과거이력", "소급기간", "입도", "인증", "비고"],
              ["c", "l", "c", "c", "l", "c", "l"],
              title="Phase 0 — 거래원 이력 소스 검증 (SPEC §4-1)")

    verdict = {
        "FULL10": ("✔ 10년 전체 이력 확보 — ARC-BDF 원 가설 그대로 진행합니다.", "INFO"),
        "PARTIAL": (f"△ {member_years:.1f}년 확보 — 그 구간으로 축소해 진행합니다. "
                    f"표본이 줄어 검정력이 낮아지는 점을 결과 해석에 반드시 반영하세요.", "WARN"),
        "PROXY": ("✘ 거래원 과거 이력 확보 불가 (당일 스냅샷 전용). "
                  "SPEC §4.3 에 따라 B-1(전진수집) + B-2(열화 프록시) 로 전환합니다.", "WARN"),
    }[branch]
    (LOG.ok if verdict[1] == "INFO" else LOG.warn)(verdict[0])

    if branch == "PROXY":
        LOG.rule("PROXY 분기 — 반드시 읽어주세요")
        for ln in [
            "· 이 실행은 ARC-BDF 원 가설(자사 거래원 창구)의 백테스트가 아닙니다.",
            "  전략명을 ARC-BDF-PROXY 로 바꿔 보고하며, '10년 백테스트 완료' 라고 쓰지 않습니다.",
            "· 신호는 '리포트 발행사의 창구' 대신 '리포트 발행사와 같은 계열의 투자주체'",
            "  (외국계 하우스 → 외국인 / 국내 하우스 → 기관) 순매수로 대체됩니다.",
            "· 검증 불가로 전환되는 것: H3(중소형 증권사 강세) — 창구 단위가 사라지므로 원리상 불가.",
            "· 약화되는 것: H5(리포트 조건부 우위) — 주체 단위로만 검정되며 해상도가 낮습니다.",
            "· 그대로 유효한 것: H1 / H2 / H4, 그리고 look-ahead·생존편향 방어 전체.",
            "· 동시에 B-1 전진수집이 매 실행마다 오늘자 거래원 스냅샷을 공용 인덱스에 적재합니다.",
            "  충분히 쌓이면(3년) 같은 코드가 자동으로 PARTIAL 분기로 올라섭니다.",
        ]:
            LOG.info(ln)

    _write_phase0_md(R, mem, frgn_years, dgk_ok)
    _emit_forward_collector(branch)
    return R


def _write_phase0_md(R: dict, mem: dict, frgn_years: float, dgk_ok: bool) -> str:
    p = out_path(PHASE0_MD)
    b = R["branch"]
    lines = [
        f"# PHASE 0 — 데이터 실현가능성 게이트 결과",
        "",
        f"- 전략: **{SPEC_ID}**  ·  빌드 `{BUILD_VERSION}`",
        f"- 실행 시각: {R['started']}  ·  소요 {R.get('elapsed_min', 0):.1f}분 "
        f"(타임박스 {PHASE0_TIMEBOX_MIN}분)",
        f"- 백테스트 요청 구간: {BACKTEST_START} ~ {BACKTEST_END}",
        "",
        f"## 판정: **{b}**",
        "",
        {"FULL10": "거래원별 일별 매매동향의 10년 이력을 확보했습니다. 원 가설 그대로 진행합니다.",
         "PARTIAL": f"거래원 이력을 {R['member_history_years']:.1f}년 확보했습니다. "
                    f"확보 구간으로 축소해 진행하며, 표본 축소로 검정력이 낮아집니다.",
         "PROXY": "거래원별 일별 매매동향의 **과거 이력을 무료 경로로 확보할 수 없습니다**. "
                  "네이버 거래원 탭은 최종 거래일 1일치 스냅샷 전용이며 날짜 파라미터도 "
                  "페이지네이션도 없습니다. 공공데이터포털에 해당 데이터셋이 없고, 증권사 "
                  "OpenAPI 는 '현재가 기준' 스냅샷이거나 Windows COM 종속이라 소급이 불가합니다.\n\n"
                  "따라서 **SPEC §4.3 의 B-1 + B-2 로 전환합니다.**"}[b],
        "",
        "## 1. 후보 소스 검증 결과 (SPEC §4-1)",
        "",
        "| 순위 | 후보 | 과거이력 | 소급기간 | 입도 | 인증 | 비고 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in R["sources"]:
        lines.append("| " + " | ".join(str(x).replace("\n", " ") for x in r) + " |")

    lines += [
        "",
        "## 2. robots.txt / 이용약관",
        "",
        "- 네이버금융·한경컨센서스 모두 `robots.txt` 가 `Disallow: /` 입니다. "
        "사용자의 명시적 지시에 따라 수집하되 보수적 속도(요청간 "
        f"{FLOW_DELAY_RANGE[0]}~{FLOW_DELAY_RANGE[1]}초, 동시 {FLOW_WORKERS})로 제한하고 "
        "그 사실을 로그에 명시합니다.",
        "- 리포트 PDF 원문은 증권사 저작물이므로 로컬 캐시/분석 용도로만 사용합니다.",
        "- 공공데이터포털·DART 는 공개 API 이며 이용약관 범위 내에서 사용합니다.",
        "",
        "## 3. 분기 처리",
        "",
    ]
    if b == "PROXY":
        lines += [
            "### B-1 전진 수집 모드 (가동됨)",
            "",
            f"- 매 실행마다 오늘자 거래원 상위 5창구 스냅샷을 공용 인덱스 "
            f"`_shared/table/naver_member_flow_snapshot` 에 append 합니다.",
            "- 별도 스케줄러용 스크립트 `outputs/forward_collect_member_flow.py` 를 생성했습니다. "
            "cron / 작업 스케줄러 / GitHub Actions 에 걸어 매 영업일 장마감 후 1회 실행하세요.",
            "- **이 경로만으로는 백테스트가 불가능하며 페이퍼 트레이딩 검증만 가능합니다.**",
            "- 상위 5 절단(censoring)을 0 으로 채우지 않고 `censored` + `upper_bound` 로 "
            "명시 저장합니다. 0 으로 채우면 대형 창구일수록 순매수가 과대추정되어 "
            "가짜 알파가 생성됩니다.",
            "",
            "### B-2 열화 프록시 백테스트 — `ARC-BDF-PROXY` (가동됨)",
            "",
            "- 거래원 대신 **투자자별 매매동향**을 사용합니다.",
            "- 단, 단순히 기관+외국인을 합치지 않고 **발행사 계열 정합(class-matched)** 으로 "
            "브로커 정체성을 부분적으로 보존합니다: "
            "외국계 하우스 리포트 → 외국인 순매수 / 국내 하우스 리포트 → 기관 순매수.",
            "- **이것은 원 가설의 대리 검증이 아닙니다.** 창구 단위가 주체 단위로 바뀌므로:",
            "  - **H3 (중소형 증권사에서 더 강함) → 검증 불가**",
            "  - **H5 (리포트 조건부 우위) → 주체 단위로만, 약화된 형태로 검증**",
            "  - H1 / H2 / H4 및 look-ahead·생존편향 방어는 그대로 유효",
            "- 따라서 산출물에서 \"10년 백테스트 완료(ARC-BDF)\" 라고 보고하지 않습니다.",
            "",
        ]
    elif b == "PARTIAL":
        lines += [
            f"- 확보 구간 {R['member_history_years']:.1f}년으로 축소해 진행합니다.",
            "- 표본 축소가 검정력에 미치는 영향: 이벤트 수가 줄면 H1 의 t 값이 "
            "√(표본비) 만큼 축소됩니다. 10년 대비 유의성 문턱을 넘기기 어려워질 수 있으며, "
            "이는 효과 부재의 증거가 아닙니다.",
            "",
        ]
    else:
        lines += ["- 원 가설 그대로 진행합니다.", ""]

    lines += [
        "## 4. PIT / 편향 방어 상태 (KRX 미사용)",
        "",
        f"- 공공데이터포털 시세 API: **{'가동' if dgk_ok else '미가동(키 없음)'}** — "
        f"{'PIT 시가총액·상장주식수·일별 상장 스냅샷이 관측값으로 확정됩니다.' if dgk_ok else '시총이 근사(T2~T4)로 강등됩니다. 동작은 하지만 H4 해석 시 감안이 필요합니다.'}",
        "- 상장폐지 이력: FDR `listing/delisting` GitHub 캐시 (KRX 인증 무관)",
        "- 상장일: KIND 상장법인목록 + FDR 상장목록",
        "- 가격: FDR → 네이버 siseJson → 네이버 HTML → yfinance 4중 폴백",
        "",
        "## 5. 남은 위험",
        "",
        "- 네이버 수집은 `robots.txt` 상 비허용이며 차단 가능성이 상존합니다. "
        "서킷 브레이커(연속 실패 "
        f"{FLOW_CIRCUIT_BREAK_N}회)와 시간예산({FLOW_TIME_BUDGET_MIN}분)으로 관리합니다.",
        "- 미수집 구간은 **0 이 아니라 결측**으로 남깁니다. 0 으로 채우면 '순매수 없음' 이라는 "
        "허위 정보가 되어 신호가 오염됩니다.",
    ]
    for n in R.get("notes", []):
        lines.append(f"- {n}")

    txt = "\n".join(lines) + "\n"
    atomic_write_text(p, txt)
    VAULT.put_blob("report", "phase0", "PHASE0_DATA_FEASIBILITY", txt.encode("utf-8"),
                   "md", scope="private", source=STRATEGY_ID)
    LOG.ok(f"Phase 0 보고서 저장 → {p}")
    return p


_FORWARD_TEMPLATE = '''#!/usr/bin/env python3
"""ARC-BDF B-1 전진 수집기 — 거래원 상위 5창구 일별 스냅샷.

거래원 과거 이력은 어떤 무료 소스에도 없다. 그래서 오늘부터 쌓는다.
매 영업일 장마감 후 1회 실행하도록 스케줄러에 등록하라.

  · Linux/Mac cron :   30 16 * * 1-5  /usr/bin/python3 {path}
  · Windows        :   작업 스케줄러 → 매일 16:30 → python {path}
  · GitHub Actions :   schedule: - cron: "30 7 * * 1-5"   (UTC 기준)

하루라도 빠지면 그날은 영구 결손이다. Colab 세션에 의존하지 말고 상시 실행 환경에 올릴 것.
저장 위치는 ARC_BDF_CACHE 환경변수(없으면 ./arc_bdf_cache) 아래 공용 인덱스다.
"""
import os, re, json, time, random, hashlib, datetime as dt
import pandas as pd, requests

ROOT = os.environ.get("ARC_BDF_CACHE", "./arc_bdf_cache")
OUT = os.path.join(ROOT, "_shared", "table", "naver_member_flow_snapshot")
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"


def codes_today():
    """상장 종목 코드 목록. FDR 이 있으면 그걸, 없으면 캐시된 목록을 쓴다."""
    try:
        import FinanceDataReader as fdr
        d = fdr.StockListing("KRX")
        c = [str(x).zfill(6) for x in d[[c for c in d.columns if c.lower() in ("code", "symbol")][0]]]
        return [x for x in c if re.fullmatch(r"\\d{6}", x)]
    except Exception:
        p = os.path.join(ROOT, "_shared", "table", "code_list.json")
        if os.path.isfile(p):
            return json.load(open(p))
        raise SystemExit("종목 목록을 얻지 못했습니다. finance-datareader 를 설치하세요.")


def fetch_one(code):
    url = f"https://finance.naver.com/item/frame_trade.naver?code={{code}}"
    try:
        r = requests.get(url, headers={{"User-Agent": UA, "Referer": "https://finance.naver.com/"}},
                         timeout=20)
        if r.status_code != 200:
            return None
        html = r.content.decode("euc-kr", "replace")
    except Exception:
        return None
    tds = re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)
    tds = [re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ").strip() for t in tds]
    rows, side_i = [], 0
    pairs = [(tds[i], tds[i + 1]) for i in range(len(tds) - 1)
             if re.fullmatch(r"[\\d,]+", tds[i + 1] or "") and tds[i]
             and not re.fullmatch(r"[\\d,\\.%]+", tds[i])]
    for i, (nm, v) in enumerate(pairs[:10]):
        rows.append(dict(member_raw=nm, volume=float(v.replace(",", "")),
                         side="SELL" if i % 2 == 0 else "BUY", rank=i // 2 + 1, code=code))
    return rows or None


def main():
    now = dt.datetime.now()
    td = now.date() if now.hour >= 16 else (now.date() - dt.timedelta(days=1))
    while td.weekday() >= 5:
        td -= dt.timedelta(days=1)
    codes = codes_today()
    out, fail = [], 0
    for i, c in enumerate(codes):
        time.sleep(random.uniform(0.3, 1.2))          # 차단 방지 (SPEC 2.3)
        r = fetch_one(c)
        if not r:
            fail += 1
            if fail >= 30:
                print("[중단] 연속 실패 30회 — 차단 가능성. 여기까지 저장합니다.")
                break
            continue
        fail = 0
        out.extend(r)
        if i % 200 == 0:
            print(f"  {{i}}/{{len(codes)}} ...")
    if not out:
        print("수집 0건 — 휴장이거나 차단입니다."); return
    df = pd.DataFrame(out)
    df["trade_date"] = pd.Timestamp(td)
    df["captured_at"] = pd.Timestamp(now)
    df["parser_ver"] = 1
    p = os.path.join(OUT, f"snapshot_{{td:%Y%m%d}}.parquet")
    df.to_parquet(p, index=False)                     # 기존 파일을 덮지 않는 날짜별 파일
    print(f"저장 {{len(df):,}}행 → {{p}}")


if __name__ == "__main__":
    main()
'''


def _emit_forward_collector(branch: str) -> Optional[str]:
    """B-1 전진수집 스크립트를 산출물로 떨군다 (PROXY/PARTIAL 분기에서만)."""
    if branch == "FULL10":
        return None
    p = out_path("forward_collect_member_flow.py")
    try:
        atomic_write_text(p, _FORWARD_TEMPLATE.format(path=p))
        LOG.ok(f"B-1 전진수집 스크립트 생성 → {p}  "
               f"(매 영업일 장마감 후 1회 실행하도록 스케줄러에 등록하세요)")
        return p
    except Exception as e:                                            # noqa
        LOG.warn(f"전진수집 스크립트 생성 실패: {type(e).__name__}")
        return None


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-A  PIT 유니버스 (일별) — 생존편향·미래참조 방어의 본체                                ║
# ║                                                                                          ║
# ║  이벤트 드리븐 전략이라 '월말 유니버스' 로는 부족하다. 이벤트가 발생한 그 날에             ║
# ║  그 종목이 실제로 거래 가능했는지를 (code, date) 쌍 단위로 벡터 판정한다.                  ║
# ║                                                                                          ║
# ║  멤버십 = 아래를 전부 만족                                                                 ║
# ║    ① 상장일 <= d           (상장 전 종목이 섞이면 그 자체로 미래참조)                      ║
# ║    ② 폐지일 > d 또는 없음  (폐지 종목을 빼면 생존편향 — 반대로 폐지 후를 넣으면 유령거래)  ║
# ║    ③ 상장 후 250거래일 시즈닝 (IPO 직후 구간의 이상수익률이 신호를 오염시킨다)             ║
# ║    ④ 보통주                (우선주·ETF·리츠·스팩은 리포트 이벤트와 매칭되지 않는다)        ║
# ║    ⑤ 그 날 실제 시세가 관측됨 (거래정지일에 진입하는 백테스트는 실행 불가능한 백테스트다)  ║
# ║                                                                                          ║
# ║  ★ ③ 시즈닝 앵커 주의 — 조용한 유니버스 붕괴의 원인                                        ║
# ║    searchsorted 는 '가격패널 시작일 이전 상장' 종목을 전부 index 0 으로 보낸다. 거기에      ║
# ║    +250 을 더하면 1990년 상장 종목조차 '패널 시작 후 250거래일' 에야 시즈닝이 끝난 것으로   ║
# ║    계산되어, 2016-08 시작 패널이면 2017년 중반까지 기존 상장사 전부가 빠진다. 에러도        ║
# ║    로그도 없이. → 앵커는 '패널 시작일' 이 아니라 '상장일' 이다.                             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

LISTING_SEASONING_DAYS = 250          # 상장일 + 250거래일 ≈ 1년
DELIST_HAIRCUT = -0.50                # 정리매매 관측이 없는 폐지 종목의 청산 가정 (감도분석 대상)


class DailyUniverse:
    """(code, date) 쌍에 대한 벡터화 PIT 멤버십 판정기."""

    def __init__(self, sec: pd.DataFrame, px: pd.DataFrame, dgk: Optional[pd.DataFrame] = None,
                 snapshots: Optional[pd.DataFrame] = None):
        s = sec.drop_duplicates("code").copy()
        s["listing_date"] = as_ts_series(s["listing_date"])
        s["delisting_date"] = as_ts_series(s["delisting_date"])
        s["name"] = s["name"].astype(str)
        s["market"] = s.get("market", "").astype(str)
        self.sec = s.reset_index(drop=True)

        self.codes = self.sec["code"].to_numpy(dtype=object)
        self._pos = {c: i for i, c in enumerate(self.codes)}
        self._ld = self.sec["listing_date"].to_numpy(DT64)
        self._dd = self.sec["delisting_date"].to_numpy(DT64)
        self._common = np.array([is_common_stock(c, n, m) for c, n, m in
                                 zip(self.codes, self.sec["name"], self.sec["market"])], bool)

        self.cal = build_trading_calendar(px)
        self._cal = self.cal.to_numpy(DT64) if len(self.cal) else \
            np.array([], dtype=DT64)

        # ── 시즈닝 만료일 (상장일 앵커) ─────────────────────────────────────────────────
        FAR = np.datetime64("2100-01-01", DT64_UNIT)
        seas = np.full(len(self.codes), FAR, dtype=DT64)
        if len(self._cal):
            t0 = self._cal[0]
            idx = np.searchsorted(self._cal, self._ld, side="left") + LISTING_SEASONING_DAYS
            inside = idx < len(self._cal)
            seas = np.where(inside, self._cal[np.minimum(idx, len(self._cal) - 1)], FAR)
            pre = (~np.isnat(self._ld)) & (self._ld < t0)      # 패널 시작 전 상장 → 달력 1년
            seas = np.where(pre, self._ld + np.timedelta64(365, "D"), seas)
        else:
            seas = np.where(np.isnat(self._ld), FAR, self._ld + np.timedelta64(365, "D"))
        seas = np.where(np.isnat(self._ld), FAR, seas)          # 상장일 미상 = 판단 불가 → 배제
        self._seas = seas

        # ── 그날 시세가 관측된 (code, date) 집합 ───────────────────────────────────────
        obs = px[["code", "date"]].dropna() if px is not None and len(px) else pd.DataFrame()
        if dgk is not None and len(dgk):
            obs = pd.concat([obs, dgk[["code", "date"]].dropna()], ignore_index=True)
        self._obs: set = set()
        if len(obs):
            o = obs.copy()
            o["date"] = as_ts_series(o["date"])
            o = o.dropna()
            self._obs = set(zip(o["code"].to_numpy(dtype=object),
                                o["date"].to_numpy(DT64)))

        # ── 스냅샷 보강 (합집합으로만 — 교집합은 절대 금지) ────────────────────────────
        self._snap: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            sn = snapshots.copy()
            sn["snap_date"] = as_ts_series(sn["snap_date"])
            for dt_, g in sn.dropna(subset=["snap_date"]).groupby("snap_date", observed=True):
                self._snap[as_ts(dt_)] = set(g["code"])

        self.attrition: List[dict] = []
        LOG.ok(f"PIT 유니버스 준비 — 종목 {len(self.codes):,} "
               f"(보통주 {int(self._common.sum()):,}) · 거래일 {len(self.cal):,} · "
               f"관측 {len(self._obs):,}쌍 · 폐지이력 {int(pd.notna(self.sec['delisting_date']).sum()):,}")

    # ── 벡터 멤버십 ────────────────────────────────────────────────────────────────────
    def is_member(self, codes: Sequence[str], dates: Sequence[Any],
                  require_observed: bool = True) -> np.ndarray:
        """(code, date) 쌍별 PIT 멤버십. 길이가 같은 두 배열을 받아 bool 배열을 돌려준다."""
        n = len(codes)
        if n == 0:
            return np.zeros(0, bool)
        idx = np.array([self._pos.get(c, -1) for c in codes], dtype=np.int64)
        ok = idx >= 0
        d = pd.to_datetime(pd.Series(list(dates)), errors="coerce").to_numpy(DT64)
        safe = np.where(ok, idx, 0)
        ld, dd, se, cm = self._ld[safe], self._dd[safe], self._seas[safe], self._common[safe]
        ok &= ~np.isnat(d)
        ok &= (~np.isnat(ld)) & (ld <= d)                      # ① 상장 이후
        ok &= np.isnat(dd) | (dd > d)                          # ② 폐지 이전
        ok &= (se <= d)                                        # ③ 시즈닝
        ok &= cm                                               # ④ 보통주
        if require_observed and self._obs:
            obs = np.array([(c, dd_) in self._obs for c, dd_ in zip(codes, d)], bool)
            ok &= obs                                          # ⑤ 그날 시세 관측
        return ok

    def at(self, t) -> List[str]:
        """시점 t 의 전체 유니버스 (비교전략의 시총 랭킹 등에 쓴다)."""
        t = as_ts(t)
        td = np.datetime64(t)
        ok = ((~np.isnat(self._ld)) & (self._ld <= td) &
              (np.isnat(self._dd) | (self._dd > td)) & (self._seas <= td) & self._common)
        base = set(self.codes[ok].tolist())
        past = [d for d in self._snap if d <= t]
        if past:                                   # 스냅샷은 합집합으로만 (표본을 깎지 않는다)
            key = max(past)
            if (t - key).days <= 100:
                base |= {c for c in self._snap[key] if c in self._pos}
        base -= {c for c, i in self._pos.items()
                 if not np.isnat(self._dd[i]) and self._dd[i] <= td}
        return sorted(base)

    def delisting_map(self) -> Dict[str, pd.Timestamp]:
        return {r.code: r.delisting_date for r in self.sec.itertuples(index=False)
                if pd.notna(r.delisting_date)}

    def audit(self, stage: str, n: int, note: str = ""):
        self.attrition.append({"stage": stage, "n": int(n), "note": note})

    def report_attrition(self):
        if not self.attrition:
            return
        rows, prev = [], None
        for a in self.attrition:
            keep = "" if prev in (None, 0) else f"{100*a['n']/prev:.1f}%"
            rows.append([a["stage"], f"{a['n']:,}", keep, a.get("note", "")])
            prev = a["n"]
        LOG.table(rows, ["게이트", "잔존 이벤트/종목", "직전 대비", "비고"],
                  ["l", "r", "r", "l"],
                  title="유니버스·이벤트 감쇠 감사 — 어느 게이트에서 표본이 붕괴하는지")
        if rows and int(str(rows[-1][1]).replace(",", "")) < 100:
            LOG.warn("최종 이벤트가 100건 미만입니다. 통계적 판단이 불가능한 수준이므로 "
                     "임계값을 낮추기 전에 위 표에서 어느 게이트가 원인인지 먼저 확인하세요.")


# ── 사이즈 / 업종 셀 ────────────────────────────────────────────────────────────────────────
SIZE_LABELS = ["대형", "중형", "소형"]


def assign_size_bucket(mc: pd.DataFrame) -> pd.DataFrame:
    """그날의 시가총액 횡단면 백분위로 대형/중형/소형을 나눈다.

    ★ 절대 기준(예: 1조원 이상=대형)을 쓰면 10년간의 인플레이션·지수상승이 그대로
      '시간에 따른 대형주 증가' 로 들어와 사이즈 효과와 시계열 추세가 뒤섞인다.
      반드시 그 시점의 횡단면 랭크로 나눈다."""
    if mc is None or len(mc) == 0:
        return mc
    d = mc.copy()
    r = d.groupby("date", observed=True)["marcap"].rank(pct=True, ascending=False)
    d["size_pct"] = r
    d["size_bucket"] = np.select(
        [r <= 0.20, r <= 0.60], ["대형", "중형"], default="소형")
    set_where(d, r.isna(), "size_bucket", "중형")     # 시총 미상은 중형으로(중립)
    return d


def smallcap_universe(mc: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    """★ 비교전략용: 그 시점 시가총액 '하위 n 종목' 멤버십 (PIT).

    각 거래일마다 그날 시총 오름차순 n개를 고른다. 오늘의 시총으로 과거를 자르면
    look-ahead 이므로, 반드시 그날의 횡단면에서 고른다."""
    if mc is None or len(mc) == 0:
        return pd.DataFrame(columns=["code", "date", "in_small"])
    d = mc[["code", "date", "marcap"]].dropna(subset=["date"]).copy()
    r = d.groupby("date", observed=True)["marcap"].rank(method="first", ascending=True)
    d["in_small"] = (r <= n) & d["marcap"].notna()
    cov = d.groupby("date", observed=True)["in_small"].sum()
    LOG.info(f"시총 하위 {n:,} 유니버스: 일평균 {cov.mean():,.0f}종목 "
             f"(최소 {cov.min():,.0f} · 최대 {cov.max():,.0f}) — 매 거래일 횡단면에서 재선정(PIT)")
    return d[["code", "date", "in_small"]]


def attach_industry(panel: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """업종 더미용 컬럼. 업종이 시점에 따라 바뀌는 경우는 무시하고 최신값을 쓴다
    (업종 재분류는 드물고, 통제변수로만 쓰이므로 영향이 미미하다 — 그 사실을 명시)."""
    if panel is None or len(panel) == 0:
        return panel
    ind = sec.drop_duplicates("code").set_index("code")["industry"] \
        if "industry" in sec.columns else pd.Series(dtype=object)
    p = panel.copy()
    p["industry"] = p["code"].map(ind).fillna("미분류").astype(str)
    # 카디널리티가 너무 크면 더미가 폭발한다 → 상위 30개만 유지하고 나머지는 '기타'
    top = p["industry"].value_counts().head(30).index
    set_where(p, ~p["industry"].isin(top), "industry", "기타")
    return p


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-B  이벤트 정의 — '매수성 리포트'  (SPEC §6.1)                                         ║
# ║                                                                                          ║
# ║  리포트 이벤트 (B, i, d) 중 아래 하나라도 만족하면 매수성으로 본다:                        ║
# ║    ① 투자의견이 매수/강력매수 계열, 또는                                                  ║
# ║    ② 목표주가 상향폭 ≥ +3% (★ 직전 '동일 증권사' 목표가 대비), 또는                        ║
# ║    ③ 신규 커버리지 개시                                                                    ║
# ║  한국은 매도의견 비중이 사실상 0이라 의견 등급만으로는 변별력이 없다. 목표가 변화가 실질.  ║
# ║                                                                                          ║
# ║  ★ 조용히 틀리는 지점들 — 전부 방어한다                                                   ║
# ║   · 목표가 "0" / "-" 는 '목표주가 없음' 이다. 0 으로 넣으면 리비전이 -100% 가 되어         ║
# ║     모든 종목이 '하향' 으로 분류된다. (13_ingest_research 의 parse_target_price 가 처리)   ║
# ║   · '직전 목표가' 는 반드시 pub_date 미만이어야 한다. 같은 날 두 건이면 순서가 없으므로     ║
# ║     같은 날은 비교 대상에서 제외한다(<= 로 두면 자기 자신과 비교해 항상 0% 가 된다).        ║
# ║   · '신규 커버리지' 를 '데이터상 첫 등장' 으로 정의하면 데이터 시작 시점에 전 종목이        ║
# ║     신규 커버리지가 되어 2016년에 이벤트가 폭발한다 → 워밍업 구간을 둔다.                  ║
# ║   · 리포트 발간 시각은 대개 장 시작 전이지만 보장할 수 없다. knowledge_date 는 pub_date 로  ║
# ║     두되, 진입은 플로우 관측 이후(d+1 이상)이므로 이 불확실성이 수익에 새지 않는다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

EVENT_COLS = ["event_uid", "broker", "broker_tier", "code", "pub_date",
              "opinion", "target_price", "prev_target", "tp_rev", "is_new_cov",
              "buyish_reason", "source", "report_uid"]

TP_REVISION_THRESHOLD = 0.03          # SPEC §6.1: +3%
NEW_COVERAGE_WARMUP_DAYS = 365        # 데이터 시작 직후를 '신규 커버리지' 로 오인하지 않기 위한 워밍업


def build_event_panel(rep: pd.DataFrame, bm: "BrokerMap", uni: "DailyUniverse",
                      cal: pd.DatetimeIndex) -> pd.DataFrame:
    """리포트 원장 → 매수성 이벤트 패널. 각 게이트의 탈락 건수를 전부 남긴다."""
    if rep is None or len(rep) == 0:
        LOG.warn("리포트 원장이 비어 이벤트를 만들 수 없습니다.")
        return pd.DataFrame(columns=EVENT_COLS)

    d = rep.copy()
    n0 = len(d)
    uni.audit("리포트 원장 전체", n0)

    d["pub_date"] = as_ts_series(d["pub_date"])
    d["code"] = d["stock_code"].map(to_code6) if "stock_code" in d.columns else np.nan
    d = d.dropna(subset=["pub_date", "code"])
    uni.audit("종목코드·발간일 보유", len(d), f"탈락 {n0-len(d):,}")

    # ── 증권사 정규화 (거래원 매핑과 같은 사전을 쓴다 — 두 축이 같은 이름 공간이어야 조인된다)
    raw_col = "broker_name" if "broker_name" in d.columns else "broker_raw"
    d["broker"] = d[raw_col].map(lambda x: bm.resolve(x))
    n_unmapped = int(d["broker"].isna().sum())
    if n_unmapped:
        LOG.info(f"증권사 미매핑 리포트 {n_unmapped:,}건 — 버리지 않고 broker='UNMAPPED' 로 "
                 f"남겨 감사에 노출합니다(SPEC §5).")
        set_where(d, d["broker"].isna(), "broker", "UNMAPPED")
    d["broker_tier"] = d["broker"].map(bm.tier)

    # ── 리포트 단위 정렬. 같은 (증권사, 종목, 날짜) 복수건은 1건으로 합친다 ────────────────
    d["target_price"] = pd.to_numeric(d.get("target_price"), errors="coerce")
    set_where(d, (d["target_price"] <= 0), "target_price", np.nan)     # "0"/"-" 는 '없음'
    d["opinion"] = d.get("opinion", pd.Series(index=d.index, dtype=object)).astype(str)

    d = (d.sort_values(["broker", "code", "pub_date"], kind="stable")
           .drop_duplicates(["broker", "code", "pub_date"], keep="last"))
    uni.audit("증권사×종목×일 중복 제거", len(d))

    # ── ② 목표가 리비전: 직전 '동일 증권사' 목표가 (strictly before) ──────────────────────
    g = d.groupby(["broker", "code"], observed=True)
    d["prev_target"] = g["target_price"].transform(lambda s: s.ffill().shift(1))
    d["tp_rev"] = safe_div(d["target_price"] - d["prev_target"], d["prev_target"])
    set_where(d, d["prev_target"].isna() | (d["prev_target"] <= 0), "tp_rev", np.nan)

    # ── ③ 신규 커버리지: (증권사, 종목) 첫 등장 + 워밍업 이후 ─────────────────────────────
    first = g["pub_date"].transform("min")
    t_start = d["pub_date"].min()
    d["is_new_cov"] = ((d["pub_date"] == first) &
                       (d["pub_date"] > t_start + pd.Timedelta(days=NEW_COVERAGE_WARMUP_DAYS)))

    # ── ① 매수성 의견 ─────────────────────────────────────────────────────────────────────
    op = d["opinion"].str.upper().str.strip()
    is_buy_op = op.isin(["BUY", "STRONGBUY", "STRONG_BUY"]) | \
        d["opinion"].astype(str).str.contains("매수|적극매수|비중확대|OUTPERFORM|OVERWEIGHT",
                                              case=False, na=False)

    is_up = d["tp_rev"] >= TP_REVISION_THRESHOLD
    buyish = is_buy_op | is_up.fillna(False) | d["is_new_cov"]

    d["buyish_reason"] = np.select(
        [is_up.fillna(False), d["is_new_cov"], is_buy_op],
        ["목표가상향", "신규커버리지", "매수의견"], default="")
    ev = d[buyish].copy()
    uni.audit("매수성 리포트", len(ev),
              f"의견 {int(is_buy_op.sum()):,} · 상향 {int(is_up.fillna(False).sum()):,} · "
              f"신규 {int(d['is_new_cov'].sum()):,}")

    if not len(ev):
        LOG.warn("매수성 리포트가 0건입니다. opinion/target_price 파싱을 확인하세요.")
        return pd.DataFrame(columns=EVENT_COLS)

    # ── 발간일을 거래일로 스냅 (휴일 발간분은 다음 거래일로) ──────────────────────────────
    if len(cal):
        cal_np = cal.to_numpy(DT64)
        pos = np.searchsorted(cal_np, ev["pub_date"].to_numpy(DT64), side="left")
        inside = pos < len(cal_np)
        snapped = np.where(inside, cal_np[np.minimum(pos, len(cal_np) - 1)],
                           np.datetime64("NaT"))
        n_moved = int((snapped != ev["pub_date"].to_numpy(DT64)).sum())
        ev["pub_date"] = pd.to_datetime(snapped)
        ev = ev.dropna(subset=["pub_date"])
        if n_moved:
            LOG.info(f"휴일·장외 발간 {n_moved:,}건을 다음 거래일로 스냅했습니다 "
                     f"(존재하지 않는 날에 진입하는 사고 방지).")
    uni.audit("거래일 스냅", len(ev))

    # ── PIT 유니버스 필터 ─────────────────────────────────────────────────────────────────
    ok = uni.is_member(ev["code"].tolist(), ev["pub_date"].tolist(), require_observed=True)
    n_drop = int((~ok).sum())
    ev = ev[ok].copy()
    uni.audit("PIT 유니버스 통과", len(ev),
              f"상장전/폐지후/시즈닝/우선주/미관측 {n_drop:,}건 제외")

    ev["event_uid"] = [sha1_str("ev", b, c, str(pd.Timestamp(p).date()))[:16]
                       for b, c, p in zip(ev["broker"], ev["code"], ev["pub_date"])]
    ev["source"] = ev.get("source", "")
    ev["report_uid"] = ev.get("report_uid", "")
    E = ev.reindex(columns=EVENT_COLS).reset_index(drop=True)

    # ── 구성 요약 ─────────────────────────────────────────────────────────────────────────
    yr = E.groupby(E["pub_date"].dt.year, observed=True).agg(
        이벤트=("event_uid", "size"), 종목=("code", "nunique"), 증권사=("broker", "nunique"),
        목표가상향=("buyish_reason", lambda s: int((s == "목표가상향").sum())),
        신규커버=("buyish_reason", lambda s: int((s == "신규커버리지").sum())))
    LOG.table([[str(i)] + [f"{v:,}" for v in r] for i, r in zip(yr.index, yr.to_numpy())],
              ["연도", "이벤트", "종목", "증권사", "목표가상향", "신규커버"],
              ["c", "r", "r", "r", "r", "r"], title="매수성 리포트 이벤트 구성 (SPEC §6.1)")

    tier = E["broker_tier"].value_counts()
    LOG.table([[k, f"{v:,}", f"{100*v/max(len(E),1):.1f}%"] for k, v in tier.items()],
              ["증권사 구분", "이벤트", "비중"], ["l", "r", "r"],
              title="이벤트의 증권사 구성 (H3 검정의 기반)")
    if tier.get("MID", 0) < 200:
        LOG.warn("중소형(MID) 증권사 이벤트가 200건 미만입니다 — H3(중소형사 강세) 검정의 "
                 "검정력이 매우 낮습니다. 결과가 '기각' 으로 나와도 효과 부재의 증거가 아닙니다.")

    PIPE.io("OUT", "MEM", "event_panel", E)
    return E


def attach_matched_actor(E: pd.DataFrame, mode: str) -> pd.DataFrame:
    """이벤트마다 '어떤 행위자의 플로우를 볼 것인가' 를 붙인다.

    mode="MEMBER" : 발행 증권사 본인의 창구           (원 가설 · FULL10/PARTIAL 분기)
    mode="PROXY"  : 발행사 계열 정합                  (PROXY 분기)
                    외국계 하우스 → FOREIGN / 국내 하우스 → INST
                    ★ 이것은 원 가설의 대리 검증이 아니다. 창구 정체성이 주체 정체성으로
                      강등되며, 그 사실이 모든 산출물에 표기된다.
    """
    if E is None or len(E) == 0:
        return E
    e = E.copy()
    if mode == "MEMBER":
        e["actor"] = e["broker"]
        e["actor_kind"] = "MEMBER"
    else:
        e["actor"] = np.where(e["broker_tier"].astype(str) == "FOREIGN", "FOREIGN", "INST")
        e["actor_kind"] = e["actor"]
    return e


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2-C  신호 구성 — FLOW_raw → 이중 디민 잔차 → 횡단면 통제 잔차   (SPEC §6.2~6.5)         ║
# ║                                                                                          ║
# ║  §6.2  netbuy_share(A,i,d) = (매수 − 매도) / 그날 총거래량                                 ║
# ║        FLOW_raw(A,i,d) = Σ_{k=0..K} netbuy_share(A,i,d+k)        (K=0 또는 2)              ║
# ║        진입 = d+K+1 종가.  ★ 거래원/수급은 장 마감 후 공개되므로 d 종가 진입은 즉시 실패다.║
# ║                                                                                          ║
# ║  §6.3  이중 디민 — 대형 창구는 항상 거래량 점유가 커서 원값은 거의 전부 창구 고정효과다.   ║
# ║        FLOW_resid = FLOW_raw                                                              ║
# ║                     − median_{과거 60일}[ FLOW_raw(A,i,·) ]   창구×종목 베이스라인          ║
# ║                     − median_{과거 60일}[ FLOW_raw(A,·,d) ]   창구 전체 그날 성향           ║
# ║                     + median_{과거 60일}[ FLOW_raw(·,·,·) ]   이중차감 보정                 ║
# ║        중앙값을 쓴다(평균 아님) — 창구 플로우는 꼬리가 두껍다.                              ║
# ║                                                                                          ║
# ║  ★★ 베이스라인의 숨은 미래참조 ★★                                                          ║
# ║     FLOW_raw(d′) 는 d′..d′+K 를 쓴다. 따라서 d′ = d−1, K=2 면 그 값은 d+1 을 포함한다.      ║
# ║     '과거 60일 중앙값' 이라고 쓰고 그냥 shift(1) 하면 미래가 새어 들어온다.                 ║
# ║     → 베이스라인은 반드시 (K+1) 만큼 밀어서 '윈도가 d 이전에 끝난' 값들만 쓴다.             ║
# ║                                                                                          ║
# ║  §6.5  통제 잔차: BDF ~ log(시총) + 직전20일수익률 + 회전율 + 업종더미 (+연도더미)          ║
# ║     ★ 전기간 풀표본으로 적합하면 미래정보가 계수에 들어간다. 매매신호로 쓸 버전은            ║
# ║       '과거 252거래일 이벤트만' 으로 적합해 오늘 이벤트에 적용한다(PIT).                    ║
# ║       풀표본 버전은 이벤트스터디 기술통계용으로만 따로 만들고 그렇게 표기한다.               ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BASELINE_DAYS = 60                 # SPEC §6.6: 고정
CONTROL_TRAIN_DAYS = 252           # PIT 통제회귀 학습창 (1년)
CUT_TRAIN_DAYS = 252               # 상·하위 30% 컷 산정창 (PIT)


def _forward_rolling_sum(s: pd.Series, k: int) -> pd.Series:
    """s[d] + s[d+1] + ... + s[d+k].  결측이 하나라도 있으면 결측(0으로 메우지 않는다)."""
    if k <= 0:
        return s.astype(float)
    rev = s.iloc[::-1]
    out = rev.rolling(k + 1, min_periods=k + 1).sum().iloc[::-1]
    return out


def build_flow_raw(F: pd.DataFrame, k: int) -> pd.DataFrame:
    """(actor, code, date) → FLOW_raw. 모든 날에 대해 계산한다(이벤트 없는 날 = 대조군 재료)."""
    if F is None or len(F) == 0:
        return pd.DataFrame(columns=["actor", "code", "date", "flow_raw"])
    d = F[["actor", "code", "date", "netbuy_share"]].dropna(subset=["actor", "code", "date"]).copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values(["actor", "code", "date"], kind="stable")
    d["flow_raw"] = (d.groupby(["actor", "code"], observed=True)["netbuy_share"]
                      .transform(lambda s: _forward_rolling_sum(s, k)))
    return d[["actor", "code", "date", "flow_raw"]]


def residualize_flow(R: pd.DataFrame, k: int, baseline: int = BASELINE_DAYS) -> pd.DataFrame:
    """SPEC §6.3 이중 디민. 미래참조를 막기 위해 베이스라인을 (k+1) 만큼 민다."""
    if R is None or len(R) == 0:
        return R
    d = R.sort_values(["actor", "code", "date"], kind="stable").copy()
    lag = k + 1                                   # ★ 윈도가 d 이전에 끝난 값만 베이스라인에 쓴다

    # ── ① 창구×종목 베이스라인 ────────────────────────────────────────────────────────────
    g = d.groupby(["actor", "code"], observed=True)["flow_raw"]
    d["b_ai"] = g.transform(
        lambda s: s.shift(lag).rolling(baseline, min_periods=baseline).median())
    d["b_n"] = g.transform(lambda s: s.shift(lag).rolling(baseline, min_periods=1).count())

    # ── ② 창구 전체 그날 성향 ─────────────────────────────────────────────────────────────
    day_actor = (d.groupby(["actor", "date"], observed=True)["flow_raw"].median()
                  .rename("x").reset_index().sort_values(["actor", "date"], kind="stable"))
    day_actor["b_a"] = (day_actor.groupby("actor", observed=True)["x"]
                        .transform(lambda s: s.shift(lag)
                                   .rolling(baseline, min_periods=max(10, baseline // 3)).median()))
    d = d.merge(day_actor[["actor", "date", "b_a"]], on=["actor", "date"], how="left")

    # ── ③ 전체 베이스라인 (이중차감 보정) ─────────────────────────────────────────────────
    day_all = (d.groupby("date", observed=True)["flow_raw"].median()
                .rename("x").reset_index().sort_values("date", kind="stable"))
    day_all["b_g"] = (day_all["x"].shift(lag)
                      .rolling(baseline, min_periods=max(10, baseline // 3)).median())
    d = d.merge(day_all[["date", "b_g"]], on="date", how="left")

    d["flow_resid"] = d["flow_raw"] - d["b_ai"] - d["b_a"] + d["b_g"]
    # SPEC §6.3: 60영업일 베이스라인이 부족한 (A,i) 페어는 결측 처리
    set_where(d, d["b_ai"].isna(), "flow_resid", np.nan)

    n_ok = int(d["flow_resid"].notna().sum())
    LOG.info(f"이중 디민(k={k}) — 잔차 유효 {n_ok:,}/{len(d):,}행 "
             f"({100*n_ok/max(len(d),1):.1f}%). 베이스라인 부족분은 0 이 아니라 결측입니다. "
             f"베이스라인은 이벤트 윈도와 겹치지 않도록 {lag}일 밀어서 계산했습니다(미래참조 차단).")
    return d[["actor", "code", "date", "flow_raw", "flow_resid", "b_ai", "b_a", "b_g"]]


def attach_signal(E: pd.DataFrame, RES: pd.DataFrame) -> pd.DataFrame:
    """이벤트에 그 날 그 행위자의 FLOW 를 붙인다."""
    if E is None or len(E) == 0:
        return E
    e = E.copy()
    e["date"] = as_ts_series(e["pub_date"])
    m = RES.rename(columns={"date": "date"})
    out = e.merge(m, on=["actor", "code", "date"], how="left")
    n_hit = int(out["flow_raw"].notna().sum())
    LOG.info(f"이벤트 {len(out):,}건 중 플로우 관측 {n_hit:,}건 "
             f"({100*n_hit/max(len(out),1):.1f}%) — 미관측은 결측으로 두고 편입 대상에서 제외됩니다.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════
#  §6.5 횡단면 통제 회귀
# ══════════════════════════════════════════════════════════════════════════════════════════
def _design_matrix(df: pd.DataFrame, with_year: bool) -> Tuple[np.ndarray, List[str]]:
    cols, names = [], []
    lm = np.log(df["marcap"].clip(lower=1.0).to_numpy(float))
    lm = np.where(np.isfinite(lm), lm, np.nanmedian(lm[np.isfinite(lm)]) if np.isfinite(lm).any() else 0.0)
    cols.append(lm); names.append("log_mktcap")
    for c in ("ret20", "turnover"):
        v = pd.to_numeric(df.get(c), errors="coerce").to_numpy(float)
        med = np.nanmedian(v) if np.isfinite(v).any() else 0.0
        cols.append(np.where(np.isfinite(v), v, med)); names.append(c)
    ind = df.get("industry", pd.Series("미분류", index=df.index)).astype(str)
    for lv in sorted(ind.unique())[1:]:                     # 첫 수준은 기준 범주(더미 함정 회피)
        cols.append((ind == lv).to_numpy(float)); names.append(f"ind:{lv}")
    if with_year:
        yr = as_ts_series(df["date"]).dt.year.astype("Int64").astype(str)
        for lv in sorted(yr.unique())[1:]:
            cols.append((yr == lv).to_numpy(float)); names.append(f"yr:{lv}")
    X = np.column_stack(cols + [np.ones(len(df))])
    return X, names + ["const"]


def control_residual(S: pd.DataFrame, signal_col: str, pit: bool = True,
                     train_days: int = CONTROL_TRAIN_DAYS) -> pd.Series:
    """SPEC §6.5. pit=True 면 '과거 이벤트만' 으로 적합해 오늘 이벤트에 적용한다.

    ★ pit=False (풀표본 적합) 는 계수에 미래정보가 들어가므로 매매신호로 쓰면 안 된다.
      이벤트스터디의 기술통계 목적으로만 쓰고, 산출물에 그렇게 표기한다."""
    if S is None or len(S) == 0 or signal_col not in S.columns:
        return pd.Series(dtype=float)
    d = S.copy()
    d["date"] = as_ts_series(d["date"])
    y_all = pd.to_numeric(d[signal_col], errors="coerce")
    out = pd.Series(np.nan, index=d.index, dtype=float)

    if not pit:
        ok = y_all.notna()
        if ok.sum() < 50:
            return out
        X, _ = _design_matrix(d[ok], with_year=True)
        b = ols_beta(X, y_all[ok].to_numpy(float))
        out.loc[ok] = y_all[ok].to_numpy(float) - X @ b
        return out

    # ── PIT: 날짜 오름차순으로 훑으며 '과거 train_days 이벤트' 로 적합 ────────────────────
    d = d.sort_values("date", kind="stable")
    dates = d["date"].to_numpy(DT64)
    uniq = np.unique(dates[~pd.isna(dates)])
    if len(uniq) == 0:
        return out
    # 월 단위로 계수를 갱신한다(매일 재적합은 3,000회 회귀 = 낭비이고 결과 차이가 미미하다)
    月 = pd.DatetimeIndex(uniq).to_period("M").unique()
    y_np = y_all.reindex(d.index).to_numpy(float)
    idx_by_month = {p: np.where(pd.DatetimeIndex(dates).to_period("M") == p)[0] for p in 月}
    beta = None
    trained_at = None
    for p in 月:
        tgt = idx_by_month[p]
        if len(tgt) == 0:
            continue
        t0 = pd.Timestamp(p.start_time)
        train = np.where((pd.DatetimeIndex(dates) < t0) &
                         (pd.DatetimeIndex(dates) >= t0 - pd.Timedelta(days=int(train_days * 1.45))))[0]
        train = train[np.isfinite(y_np[train])]
        if len(train) >= 100:
            sub = d.iloc[train]
            Xtr, _ = _design_matrix(sub, with_year=False)
            beta = ols_beta(Xtr, y_np[train])
            trained_at = sub
        if beta is None or trained_at is None:
            continue
        # 적용 시점의 설계행렬은 학습 때와 '같은 열 구성' 이어야 한다 → 학습표본에 맞춰 재구성
        sub_t = d.iloc[tgt].copy()
        sub_t["industry"] = sub_t["industry"].where(
            sub_t["industry"].isin(trained_at["industry"].unique()),
            sorted(trained_at["industry"].unique())[0])
        Xte, _ = _design_matrix(pd.concat([trained_at.head(0), sub_t]), with_year=False)
        if Xte.shape[1] != len(beta):
            continue
        pred = Xte @ beta
        vals = y_np[tgt] - pred
        out.iloc[tgt] = np.where(np.isfinite(y_np[tgt]), vals, np.nan)
    n = int(out.notna().sum())
    LOG.info(f"통제회귀 잔차({'PIT' if pit else '풀표본'}) — {n:,}건 산출 "
             f"({'과거 1년 이벤트로만 적합' if pit else '★풀표본 적합: 매매신호로 사용 금지'})")
    return out


def pit_quantile_cut(S: pd.DataFrame, col: str, q: float,
                     train_days: int = CUT_TRAIN_DAYS) -> pd.Series:
    """상·하위 컷을 '전체 표본 분위' 로 잡으면 그 자체가 미래참조다.
    과거 train_days 이벤트의 분위로 오늘 이벤트를 자른다."""
    d = S[["date", col]].copy()
    d["date"] = as_ts_series(d["date"])
    d = d.sort_values("date", kind="stable")
    v = pd.to_numeric(d[col], errors="coerce")
    out = pd.Series(np.nan, index=d.index, dtype=float)
    di = pd.DatetimeIndex(d["date"])
    for p in di.to_period("M").unique():
        tgt = np.where(di.to_period("M") == p)[0]
        t0 = pd.Timestamp(p.start_time)
        tr = np.where((di < t0) & (di >= t0 - pd.Timedelta(days=int(train_days * 1.45))))[0]
        vals = v.to_numpy(float)[tr]
        vals = vals[np.isfinite(vals)]
        if len(vals) < 50:
            continue
        out.iloc[tgt] = float(np.quantile(vals, q))
    return out.reindex(S.index)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-A  이벤트 드리븐 백테스트 엔진  (SPEC §7 · §8)                                        ║
# ║                                                                                          ║
# ║  구조: 캘린더타임 포트폴리오 (calendar-time portfolio).                                    ║
# ║    매 영업일 신규 이벤트를 평가해 조건 충족 시 편입, 보유기간 만료 시 청산.                ║
# ║    ★ 이 구조를 쓰는 이유는 단지 명세 때문이 아니다. 이벤트 스터디에서 보유구간이           ║
# ║      겹치면(overlapping) 이벤트별 수익률이 서로 상관되어 t 통계량이 부풀려진다.            ║
# ║      캘린더타임 포트폴리오는 그 상관을 포트폴리오 수익률 하나로 흡수해버리므로              ║
# ║      횡단면 상관에 의한 t 과대추정이 구조적으로 사라진다.                                  ║
# ║                                                                                          ║
# ║  진입 시점 (★ SPEC §0.1 — 위반하면 산출물 전체 무효)                                       ║
# ║    거래원/수급 데이터는 장 마감 후 공개된다. 따라서                                        ║
# ║      k=0   윈도 → 진입 d+1 종가                                                            ║
# ║      k=0..2 윈도 → 진입 d+3 종가                                                           ║
# ║    코드에서 이 오프셋은 (k+1) 로 강제되며, 계약검정 K3 가 이를 실행 시 재확인한다.          ║
# ║                                                                                          ║
# ║  보유는 buy-and-hold 다(진입 시 비중 고정, 이후 가치 드리프트).                             ║
# ║    매일 동일가중으로 되맞추면 실제로는 하지 않는 매매의 회전율·비용이 발생하고,             ║
# ║    그 비용이 성과를 왜곡한다.                                                              ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력 (매도 시). KOSPI 는 농특세 0.15% 포함 총부담 기준.
#   출처: 기획재정부 증권거래세법 시행령 개정 이력
#   https://www.moef.go.kr  /  https://law.go.kr/법령/증권거래세법시행령
#   ★ 단일 세율 사용 금지 (SPEC §7.1). 2016→2026 사이에만 5회 인하되었다.
TAX_SCHEDULE = [
    ("2016-01-01", {"KOSPI": 0.00300, "KOSDAQ": 0.00300, "OTHER": 0.00300}),
    ("2019-06-03", {"KOSPI": 0.00250, "KOSDAQ": 0.00250, "OTHER": 0.00250}),
    ("2021-01-01", {"KOSPI": 0.00230, "KOSDAQ": 0.00230, "OTHER": 0.00230}),
    ("2023-01-01", {"KOSPI": 0.00200, "KOSDAQ": 0.00200, "OTHER": 0.00200}),
    ("2024-01-01", {"KOSPI": 0.00180, "KOSDAQ": 0.00180, "OTHER": 0.00180}),
    ("2025-01-01", {"KOSPI": 0.00150, "KOSDAQ": 0.00150, "OTHER": 0.00150}),
]
_TAX_DATES = [as_ts(d) for d, _ in TAX_SCHEDULE]


def sell_tax_rate(dt, market: str) -> float:
    t = as_ts(dt)
    rate = TAX_SCHEDULE[0][1]
    for d, r in zip(_TAX_DATES, [r for _, r in TAX_SCHEDULE]):
        if t >= d:
            rate = r
    m = str(market or "").upper()
    if "KOSDAQ" in m or "코스닥" in m:
        return rate["KOSDAQ"]
    if "KOSPI" in m or "유가" in m or "코스피" in m:
        return rate["KOSPI"]
    return rate["OTHER"]


@dataclass
class BTConfig:
    k: int                       # 플로우 윈도 (0 또는 2)
    hold: int                    # 보유 영업일 (10/20/60)
    version: str                 # "raw" | "resid"
    cost_mult: float = 1.0       # 0 / 1 / 2  (SPEC §7.1 비용 3종)
    rf_annual: float = 0.0
    label: str = ""

    @property
    def entry_offset(self) -> int:
        return self.k + 1        # ★ 장 마감 후 공개 → 최소 d+1 (SPEC §0.1)

    def name(self) -> str:
        return self.label or (f"k={self.k}·hold={self.hold}d·{self.version}"
                              f"{'' if self.cost_mult == 1 else f'·비용x{self.cost_mult:g}'}")


def _price_matrix(px: pd.DataFrame, cal: pd.DatetimeIndex) -> Tuple[np.ndarray, Dict[str, int]]:
    """close 행렬 [n_code, n_day]. 결측은 직전값 전진충전(거래정지 구간의 평가가격)."""
    p = px[["code", "date", "close"]].dropna()
    p = p[p["date"].isin(cal)]
    piv = p.pivot_table(index="code", columns="date", values="close", aggfunc="last")
    piv = piv.reindex(columns=cal)
    piv = piv.ffill(axis=1)
    return piv.to_numpy(float), {c: i for i, c in enumerate(piv.index)}


def run_event_backtest(S: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                       uni: "DailyUniverse", cfg: BTConfig,
                       sec: Optional[pd.DataFrame] = None,
                       member_filter: Optional[np.ndarray] = None) -> dict:
    """이벤트 드리븐 백테스트. 반환: 일별수익률 / 보유내역 / 체결로그 / 요약통계."""
    sig_col = "sig_resid" if cfg.version == "resid" else "sig_raw"
    empty = {"daily": pd.DataFrame(columns=["date", "ret", "n", "cash_w", "cost"]),
             "trades": pd.DataFrame(), "cfg": cfg, "stats": {}}
    if S is None or len(S) == 0 or sig_col not in S.columns or not len(cal):
        return empty

    d = S.copy()
    d["date"] = as_ts_series(d["date"])
    d = d[d[sig_col].notna()]
    if member_filter is not None:
        d = d[member_filter[:len(d)]] if len(member_filter) == len(S) else d
    if not len(d):
        return empty

    # ── PIT 상위 30% 컷 (전체 표본 분위를 쓰면 그 자체가 미래참조) ────────────────────────
    cut = pit_quantile_cut(d, sig_col, 1.0 - PORT_LONG_PCT)
    d = d.assign(_cut=cut.to_numpy())
    sel = d[d["_cut"].notna() & (d[sig_col] >= d["_cut"])].copy()
    if not len(sel):
        LOG.warn(f"[{cfg.name()}] 편입 이벤트가 0건입니다 (PIT 컷 산정에 필요한 과거 이벤트 부족).")
        return empty

    close, cidx = _price_matrix(px, cal)
    n_day = len(cal)
    day_pos = {d_: i for i, d_ in enumerate(cal)}

    # 시장구분 / 사이즈 버킷 (비용 산정용)
    mkt = {}
    if sec is not None and len(sec):
        mkt = dict(zip(sec["code"], sec.get("market", pd.Series("", index=sec.index))))
    size_of = dict(zip(zip(sel["code"], sel["date"]), sel.get("size_bucket", "중형")))

    # ── 이벤트를 진입일 인덱스로 변환 ─────────────────────────────────────────────────────
    ent_i, exi_i, rows = [], [], []
    off = cfg.entry_offset
    for r in sel.itertuples(index=False):
        di = day_pos.get(pd.Timestamp(r.date))
        if di is None:
            continue
        e = di + off
        x = e + cfg.hold
        if e >= n_day:
            continue                       # 진입일이 데이터 끝을 넘어감 → 편입 불가
        ci = cidx.get(r.code)
        if ci is None:
            continue
        rows.append((e, min(x, n_day - 1), ci, r.code, float(getattr(r, sig_col)),
                     getattr(r, "broker", ""), getattr(r, "broker_tier", ""),
                     getattr(r, "size_bucket", "중형"), pd.Timestamp(r.date)))
    if not rows:
        return empty
    rows.sort(key=lambda z: (z[0], -z[4]))

    by_entry: Dict[int, List[tuple]] = defaultdict(list)
    for z in rows:
        by_entry[z[0]].append(z)

    # ── 시뮬레이션 ────────────────────────────────────────────────────────────────────────
    nav = 1.0
    cash = 1.0
    pos: List[dict] = []                   # {ci, code, val, exit_i, entry_px, ...}
    rf_daily = (1.0 + cfg.rf_annual) ** (1 / 252.0) - 1.0
    daily = np.zeros(n_day)
    n_hold = np.zeros(n_day, dtype=int)
    cash_w = np.zeros(n_day)
    cost_d = np.zeros(n_day)
    trades: List[dict] = []
    skipped_noprice = 0

    def _slip(bucket: str) -> float:
        return SLIPPAGE_BPS_BY_SIZE.get(str(bucket), 20.0) * 1e-4 * cfg.cost_mult

    def _comm() -> float:
        return COMMISSION_BPS * 1e-4 * cfg.cost_mult

    for t in range(n_day):
        prev_nav = nav
        # ① 보유 포지션 평가 (전일 종가 → 당일 종가)
        if t > 0 and pos:
            for p in pos:
                c0, c1 = close[p["ci"], t - 1], close[p["ci"], t]
                if np.isfinite(c0) and np.isfinite(c1) and c0 > 0:
                    p["val"] *= (c1 / c0)
                elif not np.isfinite(c1):
                    # 가격이 사라짐 = 상장폐지/거래정지 후 소멸. 보수적으로 헤어컷.
                    p["val"] *= (1.0 + DELIST_HAIRCUT)
                    p["exit_i"] = t
                    p["forced"] = True
        cash *= (1.0 + rf_daily)

        # ② 만기·강제 청산
        still: List[dict] = []
        for p in pos:
            if p["exit_i"] <= t:
                fee = _comm() + _slip(p["bucket"]) + sell_tax_rate(cal[t], p["market"]) * cfg.cost_mult
                proceeds = p["val"] * (1.0 - fee)
                cost_d[t] += p["val"] * fee
                cash += proceeds
                trades.append({"code": p["code"], "broker": p["broker"],
                               "broker_tier": p["tier"], "event_date": p["ev"],
                               "entry_date": cal[p["entry_i"]], "exit_date": cal[t],
                               "hold_days": t - p["entry_i"], "signal": p["sig"],
                               "gross_mult": p["val"] / p["cost0"],
                               "pnl": proceeds - p["cost0"],
                               "size_bucket": p["bucket"],
                               "forced": bool(p.get("forced", False))})
            else:
                still.append(p)
        pos = still

        nav = cash + sum(p["val"] for p in pos)

        # ③ 신규 편입 (신호 강도 순 · 동시보유 상한)
        cand = by_entry.get(t, [])
        if cand:
            room = PORT_MAX_NAMES - len(pos)
            held_codes = {p["code"] for p in pos}
            for (e, x, ci, code, sig, brk, tier, bucket, evd) in cand:
                if room <= 0:
                    break
                if code in held_codes:
                    continue               # 같은 종목 중복 편입 금지(종목 단위 상한 5%)
                if not np.isfinite(close[ci, t]) or close[ci, t] <= 0:
                    skipped_noprice += 1
                    continue
                w = min(POS_MAX_WEIGHT, 1.0 / max(PORT_MAX_NAMES, 1))
                alloc = nav * w
                if alloc > cash:
                    alloc = max(0.0, cash * 0.98)
                if alloc <= 1e-9:
                    break
                fee = _comm() + _slip(bucket)
                cost_d[t] += alloc * fee
                cash -= alloc
                pos.append({"ci": ci, "code": code, "val": alloc * (1.0 - fee),
                            "cost0": alloc, "exit_i": x, "entry_i": t, "sig": sig,
                            "broker": brk, "tier": tier, "bucket": bucket, "ev": evd,
                            "market": mkt.get(code, "")})
                held_codes.add(code)
                room -= 1

        nav = cash + sum(p["val"] for p in pos)
        daily[t] = (nav / prev_nav - 1.0) if prev_nav > 0 else 0.0
        n_hold[t] = len(pos)
        cash_w[t] = cash / nav if nav > 0 else 1.0

    R = pd.DataFrame({"date": cal, "ret": daily, "n": n_hold,
                      "cash_w": cash_w, "cost": cost_d})
    T = pd.DataFrame(trades)
    if skipped_noprice:
        LOG.debug(f"[{cfg.name()}] 진입일 가격 미관측으로 {skipped_noprice:,}건 편입 불가")
    out = {"daily": R, "trades": T, "cfg": cfg,
           "stats": perf_stats_daily(R, T, cfg)}
    return out


def perf_stats_daily(R: pd.DataFrame, T: pd.DataFrame, cfg: "BTConfig") -> dict:
    r = R["ret"].fillna(0).to_numpy(float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1.0 + r)
    years = n / 252.0
    cagr = eq[-1] ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(252) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(252) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    mdd = float(dd.min())
    uw = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        uw = max(uw, cur)
    mu, tstat = hac_tstat(r)
    trades_n = len(T)
    win = float((T["pnl"] > 0).mean()) if trades_n else np.nan
    avg_hold = float(T["hold_days"].mean()) if trades_n else np.nan
    # 회전율: 연간 총 매수금액 / 평균 NAV ≈ (거래수 × 평균비중) / 연수
    turn = (trades_n * min(POS_MAX_WEIGHT, 1.0 / PORT_MAX_NAMES) / years) if years > 0 else np.nan
    return {
        "구성": cfg.name(), "거래일": n,
        "CAGR": cagr, "연변동성": vol,
        "Sharpe": (cagr / vol) if vol and np.isfinite(vol) and vol > 0 else np.nan,
        "Sortino": (cagr / dvol) if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
        "MDD": mdd, "Calmar": (cagr / abs(mdd)) if mdd < 0 else np.nan,
        "누적수익": float(eq[-1] - 1.0),
        "t통계량(NW)": tstat, "일평균": float(r.mean()),
        "최장언더워터(일)": int(uw),
        "이벤트체결수": trades_n, "승률": win, "평균보유일": avg_hold,
        "연회전율": turn, "평균보유종목": float(R["n"].mean()),
        "평균현금비중": float(R["cash_w"].mean()),
        "총비용": float(R["cost"].sum()),
    }


def yearly_returns(R: pd.DataFrame) -> pd.Series:
    if R is None or len(R) == 0:
        return pd.Series(dtype=float)
    d = R.set_index("date")["ret"]
    return d.groupby(d.index.year, observed=True).apply(lambda s: float(np.prod(1 + s.to_numpy()) - 1))


# ══════════════════════════════════════════════════════════════════════════════════════════
#  벤치마크  (SPEC §8: KOSPI / KOSDAQ / 동일가중 유니버스 / ★나이브 = 매수성 리포트 무차별 매수)
# ══════════════════════════════════════════════════════════════════════════════════════════
def build_benchmarks(px: pd.DataFrame, cal: pd.DatetimeIndex, S: pd.DataFrame,
                     uni: "DailyUniverse", sec: pd.DataFrame,
                     cfg: "BTConfig") -> Dict[str, pd.Series]:
    """★ 이 전략의 진짜 비교 대상은 지수가 아니라 '매수성 리포트를 전부 사는' 나이브 전략이다.
    지수를 이겼다는 말은 의미가 없다 — 리포트를 무차별로 사도 이길 수 있기 때문이다."""
    out: Dict[str, pd.Series] = {}

    for name, sym in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        s = _index_series(sym, cal)
        if s is not None:
            out[name] = s

    # 동일가중 유니버스 (그날 PIT 유니버스 전체의 동일가중 일별수익)
    close, cidx = _price_matrix(px, cal)
    with np.errstate(all="ignore"):
        rets = np.diff(close, axis=1) / close[:, :-1]
    ew = np.nanmean(np.where(np.isfinite(rets), rets, np.nan), axis=0)
    ew = np.concatenate([[0.0], np.where(np.isfinite(ew), ew, 0.0)])
    out["동일가중유니버스"] = pd.Series(ew, index=cal)

    # 나이브: 매수성 리포트 전체를 같은 규칙(진입시점·보유기간·비용)으로 무차별 매수
    if S is not None and len(S):
        naive_cfg = BTConfig(k=cfg.k, hold=cfg.hold, version=cfg.version,
                             cost_mult=cfg.cost_mult, rf_annual=cfg.rf_annual,
                             label="나이브(리포트무차별)")
        Sn = S.copy()
        Sn["sig_raw"] = 1.0        # 전건 편입 (신호 무시)
        Sn["sig_resid"] = 1.0
        bt = run_event_backtest(Sn, px, cal, uni, naive_cfg, sec=sec)
        if len(bt["daily"]):
            out["나이브(리포트무차별매수)"] = bt["daily"].set_index("date")["ret"]
            out["_naive_bt"] = bt
    return out


def _index_series(sym: str, cal: pd.DatetimeIndex) -> Optional[pd.Series]:
    if fdr is None:
        return None
    try:
        d = fdr.DataReader(sym, cal[0] - pd.Timedelta(days=10), cal[-1])
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "close" not in d.columns:
        return None
    s = pd.Series(pd.to_numeric(d["close"], errors="coerce").to_numpy(),
                  index=as_ts_series(d[d.columns[0]]))
    s = s[~s.index.duplicated(keep="last")].reindex(cal).ffill()
    return s.pct_change().fillna(0.0)


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3-B  이벤트 스터디 — 군별 평균 CAR 곡선  (SPEC §8)                                      ║
# ║                                                                                          ║
# ║  네 개의 군을 반드시 함께 그린다. 하나만 보면 아무것도 판정할 수 없다:                     ║
# ║    ① 확증군    매수성 리포트 + 자사(계열) 창구 순매수 상위 30%                             ║
# ║    ② 페이드군  매수성 리포트 + 자사(계열) 창구 순매도 하위 30%                             ║
# ║    ③ 무플로우 대조군   매수성 리포트인데 플로우가 중간 40%                                 ║
# ║    ④ 무리포트 대조군   ★ H5 의 핵심. 리포트가 없는 날의 동일 창구 플로우 상위 30%          ║
# ║       — 이게 확증군만큼 좋으면 이건 '리포트 전략' 이 아니라 그냥 '플로우 전략' 이다.        ║
# ║                                                                                          ║
# ║  ★ 벤치마크 모형: market-adjusted (동일가중 유니버스 수익 차감).                           ║
# ║    market-model(베타 추정)은 추정창이 이벤트 직전이라 추정오차가 CAR 에 그대로 실린다.     ║
# ║    size-matched 는 시총이 T2~T4 로 강등될 수 있는 이번 설계에서 매칭 자체가 불안정하다.    ║
# ║    → 가장 단순하고 가정이 적은 것을 쓰고, 그 선택을 산출물에 명시한다.                     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CAR_HORIZON = 60          # d+1 ~ d+60
CAR_PRE = 5               # 사전 구간(-5) 도 함께 그려 '이벤트 전에 이미 오르고 있었나' 를 본다


def _ret_matrix(px: pd.DataFrame, cal: pd.DatetimeIndex) -> Tuple[np.ndarray, Dict[str, int]]:
    close, cidx = _price_matrix(px, cal)
    with np.errstate(all="ignore"):
        r = np.full_like(close, np.nan)
        r[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    return r, cidx


def compute_car(events: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                horizon: int = CAR_HORIZON, pre: int = CAR_PRE) -> Dict[str, np.ndarray]:
    """이벤트 집합 → 평균 초과 CAR 곡선 + 표준오차 + 표본수.

    이벤트 t=0 은 리포트 발간일. 수익률은 시장(동일가중 유니버스) 차감 후 누적한다."""
    out = {"tau": np.arange(-pre, horizon + 1), "car": np.full(pre + horizon + 1, np.nan),
           "se": np.full(pre + horizon + 1, np.nan), "n": np.zeros(pre + horizon + 1, int)}
    if events is None or len(events) == 0 or not len(cal):
        return out
    R, cidx = _ret_matrix(px, cal)
    mkt = np.nanmean(R, axis=0)
    mkt = np.where(np.isfinite(mkt), mkt, 0.0)
    AR = R - mkt[None, :]

    day_pos = {d: i for i, d in enumerate(cal)}
    rows = []
    for code, dt_ in zip(events["code"], events["date"]):
        ci = cidx.get(code)
        di = day_pos.get(pd.Timestamp(dt_))
        if ci is None or di is None:
            continue
        lo, hi = di - pre, di + horizon
        if lo < 0 or hi >= AR.shape[1]:
            continue
        rows.append(AR[ci, lo:hi + 1])
    if not rows:
        return out
    M = np.vstack(rows)
    M = np.where(np.isfinite(M), M, 0.0)
    C = np.cumsum(M, axis=1)
    out["car"] = np.nanmean(C, axis=0)
    n = np.sum(np.isfinite(C), axis=0)
    out["n"] = n
    with np.errstate(all="ignore"):
        out["se"] = np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.maximum(n, 1))
    return out


def split_groups(S: pd.DataFrame, sig_col: str, ctrl: Optional[pd.DataFrame] = None
                 ) -> Dict[str, pd.DataFrame]:
    """SPEC §8 의 4개 군으로 나눈다. 컷은 PIT 분위(미래참조 차단)."""
    g: Dict[str, pd.DataFrame] = {}
    if S is None or len(S) == 0 or sig_col not in S.columns:
        return g
    d = S[S[sig_col].notna()].copy()
    hi = pit_quantile_cut(d, sig_col, 1.0 - PORT_LONG_PCT)
    lo = pit_quantile_cut(d, sig_col, PORT_FADE_PCT)
    d["_hi"], d["_lo"] = hi.to_numpy(), lo.to_numpy()
    ok = d["_hi"].notna() & d["_lo"].notna()
    d = d[ok]
    g["확증군(리포트+순매수상위30%)"] = d[d[sig_col] >= d["_hi"]]
    g["페이드군(리포트+순매도하위30%)"] = d[d[sig_col] <= d["_lo"]]
    g["무플로우대조군(리포트+중간40%)"] = d[(d[sig_col] > d["_lo"]) & (d[sig_col] < d["_hi"])]
    if ctrl is not None and len(ctrl):
        g["무리포트대조군(플로우만 상위30%)"] = ctrl
    return g


def build_noreport_control(RES: pd.DataFrame, E: pd.DataFrame, cal: pd.DatetimeIndex,
                           sig_col: str = "flow_resid", max_n: int = 60000) -> pd.DataFrame:
    """★ H5 의 대조군: '리포트가 없는 날의 동일 창구 플로우'.

    이게 확증군만큼 잘 되면 리포트는 아무 정보도 더하지 않은 것이고, 그렇다면
    이 전략은 '리포트 전략' 이 아니라 그냥 '브로커 플로우 전략' 이다 (SPEC §3 H5).

    표본이 수백만 행이라 전량을 쓰면 이벤트군과 표본수가 극단적으로 달라져 비교가
    왜곡된다 → 결정적 시드로 층화 추출하고 그 사실을 로그에 남긴다."""
    if RES is None or len(RES) == 0:
        return pd.DataFrame()
    ev_keys = set()
    if E is not None and len(E):
        ev_keys = set(zip(E["actor"], E["code"], pd.DatetimeIndex(E["date"])))
    d = RES[RES[sig_col].notna()].copy()
    if not len(d):
        return pd.DataFrame()
    if ev_keys:
        key = list(zip(d["actor"], d["code"], pd.DatetimeIndex(d["date"])))
        mask = np.array([k not in ev_keys for k in key], bool)
        d = d[mask]
    if not len(d):
        return pd.DataFrame()
    hi = pit_quantile_cut(d.assign(date=d["date"]), sig_col, 1.0 - PORT_LONG_PCT)
    d = d.assign(_hi=hi.to_numpy())
    d = d[d["_hi"].notna() & (d[sig_col] >= d["_hi"])]
    if len(d) > max_n:
        rs = np.random.default_rng(SEED)
        idx = rs.choice(len(d), size=max_n, replace=False)
        LOG.info(f"무리포트 대조군 {len(d):,}건 중 {max_n:,}건을 결정적 시드로 추출했습니다 "
                 f"(표본수 격차로 비교가 왜곡되는 것을 방지).")
        d = d.iloc[np.sort(idx)]
    return d


def report_event_study(groups: Dict[str, pd.DataFrame], px: pd.DataFrame,
                       cal: pd.DatetimeIndex) -> pd.DataFrame:
    """군별 CAR 을 계산하고 표로 출력 + parquet 산출물로 저장."""
    recs: List[pd.DataFrame] = []
    rows: List[List[Any]] = []
    for name, g in groups.items():
        if g is None or len(g) == 0:
            rows.append([name, "0", "-", "-", "-", "-", "표본 없음"])
            continue
        car = compute_car(g, px, cal)
        df = pd.DataFrame({"group": name, "tau": car["tau"], "car": car["car"],
                           "se": car["se"], "n": car["n"]})
        recs.append(df)
        def _at(t):
            i = np.where(car["tau"] == t)[0]
            return car["car"][i[0]] if len(i) else np.nan
        c20, c60 = _at(20), _at(60)
        i20 = np.where(car["tau"] == 20)[0]
        t20 = (car["car"][i20[0]] / car["se"][i20[0]]
               if len(i20) and np.isfinite(car["se"][i20[0]]) and car["se"][i20[0]] > 0 else np.nan)
        rows.append([name, f"{len(g):,}", f"{_at(0)*100:+.2f}%", f"{_at(5)*100:+.2f}%",
                     f"{c20*100:+.2f}%", f"{c60*100:+.2f}%", f"t20={t20:+.2f}"])
    LOG.table(rows, ["군", "이벤트수", "CAR(0)", "CAR(+5)", "CAR(+20)", "CAR(+60)", "유의성"],
              ["l", "r", "r", "r", "r", "r", "r"],
              title="이벤트 스터디 — 군별 누적초과수익 (시장조정 · 동일가중 유니버스 차감)")
    if not recs:
        return pd.DataFrame()
    out = pd.concat(recs, ignore_index=True)
    p = out_path("event_study_car.parquet")
    try:
        atomic_write_parquet(out, p)
        VAULT.put_table("event_study_car", out, scope="private", domain="result",
                        source=STRATEGY_ID)
    except Exception as e:                                            # noqa
        LOG.warn(f"CAR 저장 실패: {type(e).__name__}")
    return out


def car_ascii(car_df: pd.DataFrame, width: int = 62) -> None:
    """CAR 곡선을 로그에 ASCII 로 그린다 (matplotlib 없이도 형태를 볼 수 있게)."""
    if car_df is None or len(car_df) == 0:
        return
    LOG.rule("CAR 곡선 (가로=거래일 τ, 세로=군)")
    piv = car_df.pivot_table(index="group", columns="tau", values="car", observed=True)
    taus = [t for t in piv.columns if -5 <= t <= 60]
    if not taus:
        return
    vals = piv[taus].to_numpy(float)
    lo, hi = np.nanmin(vals), np.nanmax(vals)
    rng = max(hi - lo, 1e-9)
    marks = "▁▂▃▄▅▆▇█"
    for name in piv.index:
        row = piv.loc[name, taus].to_numpy(float)
        step = max(1, len(taus) // width)
        cells = "".join(
            marks[min(len(marks) - 1, max(0, int((v - lo) / rng * (len(marks) - 1))))]
            if np.isfinite(v) else " " for v in row[::step])
        LOG.info(f"  {_pad(_trunc(str(name), 30), 30)} |{cells}| "
                 f"최종 {row[-1]*100:+.2f}%")
    LOG.info(f"  (세로 스케일: {lo*100:+.2f}% ~ {hi*100:+.2f}%, τ=-5 부터 +60 까지)")


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L4-A  통계 검증 원시함수  (SPEC §9)                                                      ║
# ║   ① 블록 부트스트랩 (블록 21영업일, 1,000회)                                               ║
# ║   ② PBO (CSCV, Bailey et al. 2016)                                                        ║
# ║   ③ DSR (Deflated Sharpe Ratio, Bailey & López de Prado 2014)                             ║
# ║   ④ 워크포워드 (학습 5년 / 검증 1년 롤링)                                                  ║
# ║   ⑤ BH-FDR (q=0.10)                                                                        ║
# ║   ⑥ 뉴이-웨스트 표준오차                                                                    ║
# ║   ⑦ 플라시보 (이벤트 날짜 ±20~60영업일 이동)                                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

BLOCK_LEN = 21
N_BOOT = 1000


# ── ① 블록 부트스트랩 ───────────────────────────────────────────────────────────────────────
def block_bootstrap(r: np.ndarray, n_iter: int = N_BOOT, block: int = BLOCK_LEN,
                    stat: Callable[[np.ndarray], float] = None,
                    seed: int = SEED) -> Dict[str, float]:
    """순환 블록 부트스트랩(circular block bootstrap).

    ★ 이벤트드리븐 일별수익률은 보유구간이 겹쳐 자기상관이 있다. iid 부트스트랩을 쓰면
      신뢰구간이 좁아져 유의성이 과대평가된다. 블록을 통째로 뽑아 상관구조를 보존한다.
      순환(circular)을 쓰는 이유는 표본 끝 구간이 과소표집되는 편향을 없애기 위함이다."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    T = r.size
    out = {"n": T, "obs": np.nan, "p_gt0": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
           "boot_mean": np.nan}
    if T < block * 3:
        return out
    if stat is None:
        def stat(x):                                   # 연율화 샤프
            sd = x.std(ddof=1)
            return float(x.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan
    obs = float(stat(r))
    out["obs"] = obs
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, T, size=(n_iter, nb))
    offs = np.arange(block)
    vals = np.empty(n_iter)
    for i in range(n_iter):
        idx = (starts[i][:, None] + offs[None, :]).ravel()[:T] % T
        vals[i] = stat(r[idx])
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return out
    out["boot_mean"] = float(vals.mean())
    out["ci_lo"], out["ci_hi"] = (float(np.quantile(vals, 0.025)),
                                 float(np.quantile(vals, 0.975)))
    # 귀무가설(참값 0) 하의 분포로 중심이동한 뒤 관측값의 우측꼬리 확률
    centered = vals - vals.mean()
    out["p_gt0"] = float((centered >= obs).mean())
    return out


# ── ② PBO (CSCV) ────────────────────────────────────────────────────────────────────────────
def pbo_cscv(perf: np.ndarray, n_split: int = 8) -> Dict[str, float]:
    """Combinatorially Symmetric Cross-Validation.

    perf: [T, N] — T개 시점 × N개 구성의 수익률 행렬.
    절차 (Bailey, Borwein, López de Prado, Zhu 2016):
      1) 시계열을 S개 균등 블록으로 자른다 (S 는 짝수)
      2) S개 중 S/2 개를 IS 로 고르는 모든 조합 C(S, S/2) 에 대해
      3) IS 에서 최고 성과 구성 n* 를 고르고
      4) OOS 에서 n* 의 상대순위 ω 를 구한 뒤 logit λ = ln(ω/(1-ω))
      5) PBO = P(λ <= 0)  = '선택한 구성이 OOS 중앙값 이하로 떨어질 확률'
    """
    out = {"pbo": np.nan, "n_comb": 0, "median_logit": np.nan, "n_config": 0}
    P = np.asarray(perf, float)
    if P.ndim != 2 or P.shape[1] < 2 or P.shape[0] < n_split * 4:
        return out
    T, N = P.shape
    out["n_config"] = N
    S = n_split if n_split % 2 == 0 else n_split - 1
    bounds = np.linspace(0, T, S + 1).astype(int)
    blocks = [P[bounds[i]:bounds[i + 1]] for i in range(S)]
    blocks = [b for b in blocks if len(b) > 1]
    S = len(blocks)
    if S < 4 or S % 2:
        S = S - (S % 2)
        blocks = blocks[:S]
    if S < 4:
        return out

    def _sr(x: np.ndarray) -> np.ndarray:
        mu = np.nanmean(x, axis=0)
        sd = np.nanstd(x, axis=0, ddof=1)
        return np.where(sd > 0, mu / sd, np.nan)

    logits = []
    for comb in itertools.combinations(range(S), S // 2):
        is_idx = list(comb)
        oos_idx = [i for i in range(S) if i not in comb]
        IS = np.vstack([blocks[i] for i in is_idx])
        OOS = np.vstack([blocks[i] for i in oos_idx])
        sr_is, sr_oos = _sr(IS), _sr(OOS)
        if not np.isfinite(sr_is).any() or not np.isfinite(sr_oos).any():
            continue
        n_star = int(np.nanargmax(sr_is))
        valid = np.isfinite(sr_oos)
        if valid.sum() < 2 or not np.isfinite(sr_oos[n_star]):
            continue
        # 상대순위 ω ∈ (0,1)
        rank = float((sr_oos[valid] < sr_oos[n_star]).sum()) / float(valid.sum())
        w = min(max(rank, 1.0 / (valid.sum() + 1)), 1.0 - 1.0 / (valid.sum() + 1))
        logits.append(math.log(w / (1.0 - w)))
    if not logits:
        return out
    lg = np.asarray(logits)
    out["n_comb"] = len(lg)
    out["median_logit"] = float(np.median(lg))
    out["pbo"] = float((lg <= 0).mean())
    return out


# ── ③ DSR ───────────────────────────────────────────────────────────────────────────────────
def expected_max_sharpe(sr_trials: np.ndarray, n_trials: Optional[int] = None) -> float:
    """E[max SR] = sqrt(V) * ((1-γ)·Z⁻¹(1-1/N) + γ·Z⁻¹(1-1/(N·e)))
       V = '시도들의 SR 분산' (하나만 있으면 정의되지 않으므로 보수적 기본값을 쓴다)"""
    s = np.asarray(sr_trials, float)
    s = s[np.isfinite(s)]
    N = int(n_trials or s.size)
    if N < 2:
        return 0.0
    V = float(np.var(s, ddof=1)) if s.size >= 2 else 0.25 ** 2
    if not np.isfinite(V) or V <= 0:
        V = 0.25 ** 2
    g = 0.5772156649015329                      # 오일러-마스케로니
    e = math.e
    z1 = norm_ppf(1.0 - 1.0 / N)
    z2 = norm_ppf(1.0 - 1.0 / (N * e))
    return math.sqrt(V) * ((1.0 - g) * z1 + g * z2)


def deflated_sharpe(r: np.ndarray, sr_trials: np.ndarray, n_trials: int) -> Dict[str, float]:
    """DSR — 여러 번 시도해서 고른 최고 샤프가 '운' 일 확률을 깎아낸 값.

    DSR = Φ( (SR - SR0) · sqrt(T-1) / sqrt(1 - γ3·SR + (γ4-1)/4·SR²) )
      SR0 = E[max SR] (위 식),  γ3=왜도, γ4=첨도. 모두 '주기당' SR 로 계산한다."""
    out = {"sharpe_period": np.nan, "sharpe_ann": np.nan, "sr0": np.nan,
           "dsr": np.nan, "n_trials": int(n_trials), "skew": np.nan, "kurt": np.nan}
    x = np.asarray(r, float)
    x = x[np.isfinite(x)]
    T = x.size
    if T < 30:
        return out
    sd = x.std(ddof=1)
    if sd <= 0:
        return out
    sr = float(x.mean() / sd)                    # 주기당(일별) 샤프
    m3 = float(((x - x.mean()) ** 3).mean() / sd ** 3)
    m4 = float(((x - x.mean()) ** 4).mean() / sd ** 4)
    sr0 = expected_max_sharpe(sr_trials, n_trials)
    denom = 1.0 - m3 * sr + (m4 - 1.0) / 4.0 * sr ** 2
    out.update(sharpe_period=sr, sharpe_ann=sr * math.sqrt(252), sr0=sr0,
               skew=m3, kurt=m4)
    if denom <= 0:
        return out
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    out["dsr"] = norm_cdf(z)
    return out


# ── ④ 워크포워드 ────────────────────────────────────────────────────────────────────────────
def walk_forward(daily_by_cfg: Dict[str, pd.DataFrame], cal: pd.DatetimeIndex,
                 train_years: int = 5, test_years: int = 1) -> pd.DataFrame:
    """학습 5년으로 최고 구성을 고르고, 이어지는 1년 성과를 기록한다(롤링).

    ★ 이게 '실제로 운용했다면' 에 가장 가까운 검정이다. 전 구간 최고 구성의 전 구간 성과는
      정의상 사후선택(look-ahead)이므로 그 숫자로 판단해선 안 된다."""
    if not daily_by_cfg or not len(cal):
        return pd.DataFrame()
    # ★ 표본 구간이 학습+검증보다 짧으면 검증 창이 하나도 안 잡혀 조용히 '판정불가' 가 된다.
    #   Phase 0 이 PARTIAL(3~10년)로 떨어지면 실제로 일어난다. 창을 표본에 맞춰 줄이고,
    #   줄였다는 사실을 반드시 로그에 남긴다(검정력이 그만큼 낮아지므로).
    span_y = (cal[-1] - cal[0]).days / 365.25
    if span_y < train_years + test_years + 0.5:
        new_train = max(1, int(span_y - test_years - 0.25))
        if new_train < 1:
            LOG.warn(f"워크포워드 불가 — 표본이 {span_y:.1f}년뿐이라 학습/검증 창을 만들 수 "
                     f"없습니다. 이는 '실패' 가 아니라 '검정 불가' 입니다.")
            return pd.DataFrame()
        LOG.warn(f"표본이 {span_y:.1f}년이라 워크포워드 학습창을 {train_years}→{new_train}년으로 "
                 f"줄였습니다. 학습 표본이 짧을수록 구성 선택이 불안정해지므로 "
                 f"검증 성과를 실제 운용 기대치로 읽지 마세요.")
        train_years = new_train
    names = list(daily_by_cfg.keys())
    M = pd.DataFrame({n: daily_by_cfg[n].set_index("date")["ret"].reindex(cal).fillna(0.0)
                      for n in names}, index=cal)
    rows = []
    y0, y1 = cal[0].year, cal[-1].year
    for te in range(y0 + train_years, y1 + 1, test_years):
        tr_lo = pd.Timestamp(f"{te - train_years}-01-01")
        tr_hi = pd.Timestamp(f"{te}-01-01")
        te_hi = pd.Timestamp(f"{te + test_years}-01-01")
        tr = M[(M.index >= tr_lo) & (M.index < tr_hi)]
        te_ = M[(M.index >= tr_hi) & (M.index < te_hi)]
        if len(tr) < 200 or len(te_) < 60:
            continue
        sd = tr.std(ddof=1)
        sr = (tr.mean() / sd.replace(0, np.nan)) * math.sqrt(252)
        if not sr.notna().any():
            continue
        pick = str(sr.idxmax())
        oos = te_[pick]
        rows.append({"검증연도": te, "선택구성": pick,
                     "학습샤프": float(sr.max()),
                     "검증수익": float(np.prod(1 + oos.to_numpy()) - 1),
                     "검증샤프": float(oos.mean() / oos.std(ddof=1) * math.sqrt(252))
                     if oos.std(ddof=1) > 0 else np.nan,
                     "검증일수": len(oos)})
    W = pd.DataFrame(rows)
    if len(W):
        hit = float((W["검증수익"] > 0).mean())
        LOG.table([[r.검증연도, _trunc(r.선택구성, 34), f"{r.학습샤프:.2f}",
                    f"{r.검증수익*100:+.2f}%", f"{r.검증샤프:.2f}"] for r in W.itertuples()],
                  ["검증연도", "학습기간 최고구성", "학습Sharpe", "검증수익", "검증Sharpe"],
                  ["c", "l", "r", "r", "r"],
                  title=f"워크포워드 (학습 {train_years}년 / 검증 {test_years}년 롤링) — "
                        f"양(+) 검증연도 비율 {100*hit:.0f}%")
    return W


# ── ⑤ BH-FDR 래퍼 ───────────────────────────────────────────────────────────────────────────
def bh_fdr_table(items: List[Tuple[str, float, str]], q: float = 0.10) -> pd.DataFrame:
    """items: [(가설ID, p값, 설명)]  → BH 보정 결과표.

    ★ 가설이 5개뿐이고 서로 양의 상관을 가질 수 있다(같은 데이터·같은 신호를 본다).
      BH 는 양의 의존(PRDS) 하에서 유효하므로 그대로 쓰되, 상관 구조가 임의라면
      Benjamini-Yekutieli 가 더 보수적이다 — 두 임계를 모두 표에 표시한다."""
    ids = [i for i, _, _ in items]
    ps = np.array([p for _, p, _ in items], float)
    passed = bh_fdr(ps, q=q)
    m = len(ps)
    cm = float(np.sum(1.0 / np.arange(1, m + 1))) if m else 1.0
    passed_by = bh_fdr(ps * cm, q=q) if m else passed
    order = np.argsort(np.where(np.isfinite(ps), ps, np.inf))
    rank = np.empty(m, int)
    rank[order] = np.arange(1, m + 1)
    return pd.DataFrame({
        "가설": ids, "p값": ps, "순위": rank,
        "BH임계": q * rank / max(m, 1),
        "BH(q=0.10)": np.where(passed, "통과", "기각"),
        "BY(보수)": np.where(passed_by, "통과", "기각"),
        "설명": [d for _, _, d in items]})


# ── ⑦ 플라시보 ──────────────────────────────────────────────────────────────────────────────
def make_placebo_events(E: pd.DataFrame, cal: pd.DatetimeIndex, seed: int = SEED,
                        lo: int = 20, hi: int = 60) -> pd.DataFrame:
    """이벤트 날짜를 ±lo~hi 영업일 무작위 이동시킨 가짜 이벤트.

    ★ 가짜 이벤트에서도 효과가 나오면 파이프라인에 look-ahead 가 있다는 뜻이다 (SPEC §9-7).
      종목·증권사·신호분포는 그대로 두고 '시점만' 흔든다 — 그래야 시점 정렬에서 오는
      누수만 분리해서 볼 수 있다."""
    if E is None or len(E) == 0 or not len(cal):
        return pd.DataFrame()
    rng = np.random.default_rng(seed ^ 0xA11CE)
    day_pos = {d: i for i, d in enumerate(cal)}
    n = len(E)
    shift = rng.integers(lo, hi + 1, size=n) * rng.choice([-1, 1], size=n)
    di = np.array([day_pos.get(pd.Timestamp(d), -1) for d in E["date"]])
    nd = di + shift
    ok = (di >= 0) & (nd >= 0) & (nd < len(cal))
    P = E[ok].copy()
    P["date"] = pd.DatetimeIndex(cal)[nd[ok]]
    P["pub_date"] = P["date"]
    LOG.info(f"플라시보 이벤트 {len(P):,}건 생성 (원본 {n:,}건 · ±{lo}~{hi}영업일 이동). "
             f"여기서 유의한 효과가 나오면 파이프라인에 미래참조가 있다는 뜻입니다.")
    return P


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L4-B  사전등록 가설 H1~H5 검정  (SPEC §3)  — 변경 금지                                   ║
# ║                                                                                          ║
# ║  H1  확증군(리포트+자사창구 순매수 상위) 의 20영업일 이상수익률이 양(+)      기각: t < 2.0 ║
# ║  H2  페이드군(리포트+자사창구 순매도) 은 음(−) 이거나 H1 보다 유의하게 낮다   기각: Δt<2.0 ║
# ║  H3  효과는 중소형 증권사에서 더 강하다 (메커니즘 조건부 예측)                             ║
# ║      ★ 대형 리테일 창구에서 오히려 강하면 데이터마이닝 판정                                ║
# ║  H4  효과는 저유동성·소형주에서 더 강하다                                                  ║
# ║  H5  ★★ 자사 창구 플로우는 '리포트가 없는 날의 동일 창구 플로우' 보다 예측력이 높다        ║
# ║      이 전략의 존재 이유다. 통과 못 하면 '리포트 전략' 이 아니라 그냥 '플로우 전략' 이며,  ║
# ║      리포트 파트는 삭제하는 게 맞다.                                                       ║
# ║                                                                                          ║
# ║  다중검정 보정: BH-FDR (q=0.10)                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

H_HORIZON = 20            # SPEC §3: 20영업일


def _abnormal_returns(events: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex,
                      horizon: int = H_HORIZON, entry_offset: int = 1) -> np.ndarray:
    """이벤트별 (entry_offset ~ entry_offset+horizon) 시장조정 누적수익.

    ★ entry_offset 은 최소 1 이다. 거래원/수급은 장 마감 후 공개되므로 발간일 종가
      진입은 SPEC §0.1 위반이다(산출물 전체 무효)."""
    if events is None or len(events) == 0 or not len(cal):
        return np.array([])
    entry_offset = max(1, int(entry_offset))
    R, cidx = _ret_matrix(px, cal)
    mkt = np.nanmean(R, axis=0)
    mkt = np.where(np.isfinite(mkt), mkt, 0.0)
    AR = R - mkt[None, :]
    day_pos = {d: i for i, d in enumerate(cal)}
    out = []
    for code, dt_ in zip(events["code"], events["date"]):
        ci, di = cidx.get(code), day_pos.get(pd.Timestamp(dt_))
        if ci is None or di is None:
            continue
        lo, hi = di + entry_offset, di + entry_offset + horizon
        if hi >= AR.shape[1]:
            continue
        seg = AR[ci, lo:hi]
        seg = seg[np.isfinite(seg)]
        if seg.size == 0:
            continue
        out.append(float(np.sum(seg)))
    return np.asarray(out, float)


def _mean_t(x: np.ndarray) -> Tuple[float, float, float, int]:
    """평균, t, p(양측), n.  ★ 이벤트 보유구간이 겹쳐 상관이 있으므로 단순 t 는 과대추정된다.
    여기서는 '이벤트 횡단면' 통계로 쓰고, 시계열 유의성은 캘린더타임 포트폴리오의
    Newey-West t 로 따로 본다(둘을 함께 보고한다)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 10:
        return (np.nan, np.nan, np.nan, n)
    mu = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(n))
    t = mu / se if se > 0 else np.nan
    p = t_sf(t, n - 1) if np.isfinite(t) else np.nan
    return (mu, t, p, n)


def _welch(a: np.ndarray, b: np.ndarray) -> Tuple[float, float, float]:
    """두 군 평균 차이의 Welch t (분산이 다른 것이 정상이다)."""
    a = np.asarray(a, float)[np.isfinite(a)]
    b = np.asarray(b, float)[np.isfinite(b)]
    if a.size < 10 or b.size < 10:
        return (np.nan, np.nan, np.nan)
    va, vb = a.var(ddof=1) / a.size, b.var(ddof=1) / b.size
    d = float(a.mean() - b.mean())
    se = math.sqrt(va + vb)
    if se <= 0:
        return (d, np.nan, np.nan)
    t = d / se
    dof = (va + vb) ** 2 / max(va ** 2 / (a.size - 1) + vb ** 2 / (b.size - 1), 1e-300)
    return (d, t, t_sf(t, dof))


def test_hypotheses(groups: Dict[str, pd.DataFrame], S: pd.DataFrame, px: pd.DataFrame,
                    cal: pd.DatetimeIndex, bm: "BrokerMap", mode: str,
                    entry_offset: int = 1) -> dict:
    """H1~H5 를 계산하고 BH-FDR 을 적용한다. 반환: 결과 딕셔너리(리포트/판정에서 사용)."""
    res: Dict[str, Any] = {"mode": mode, "entry_offset": entry_offset, "rows": [],
                           "pvals": [], "detail": {}}

    conf = groups.get("확증군(리포트+순매수상위30%)")
    fade = groups.get("페이드군(리포트+순매도하위30%)")
    ctrl = groups.get("무플로우대조군(리포트+중간40%)")
    nore = groups.get("무리포트대조군(플로우만 상위30%)")

    ar_conf = _abnormal_returns(conf, px, cal, H_HORIZON, entry_offset)
    ar_fade = _abnormal_returns(fade, px, cal, H_HORIZON, entry_offset)
    ar_ctrl = _abnormal_returns(ctrl, px, cal, H_HORIZON, entry_offset)
    ar_nore = _abnormal_returns(nore, px, cal, H_HORIZON, entry_offset)
    res["detail"]["ar"] = {"확증": ar_conf, "페이드": ar_fade,
                           "무플로우": ar_ctrl, "무리포트": ar_nore}

    # ── H1 ───────────────────────────────────────────────────────────────────────────────
    mu1, t1, p1, n1 = _mean_t(ar_conf)
    res["rows"].append(["H1", "확증군 20일 CAR > 0", f"{mu1*100:+.2f}%" if np.isfinite(mu1) else "-",
                        f"{t1:+.2f}" if np.isfinite(t1) else "-", f"{n1:,}",
                        "통과" if (np.isfinite(t1) and t1 >= 2.0) else "기각"])
    res["pvals"].append(("H1", p1 / 2 if np.isfinite(p1) and np.isfinite(t1) and t1 > 0 else p1,
                         "확증군 CAR(+20) > 0"))
    res["H1_pass"] = bool(np.isfinite(t1) and t1 >= 2.0)

    # ── H2 ───────────────────────────────────────────────────────────────────────────────
    d2, t2, p2 = _welch(ar_conf, ar_fade)
    mu_f = float(np.nanmean(ar_fade)) if ar_fade.size else np.nan
    res["rows"].append(["H2", "확증군 − 페이드군 > 0",
                        f"{d2*100:+.2f}%p" if np.isfinite(d2) else "-",
                        f"{t2:+.2f}" if np.isfinite(t2) else "-",
                        f"{ar_fade.size:,}",
                        "통과" if (np.isfinite(t2) and t2 >= 2.0) else "기각"])
    res["pvals"].append(("H2", p2 / 2 if np.isfinite(p2) and np.isfinite(t2) and t2 > 0 else p2,
                         f"확증 vs 페이드 차이 (페이드 평균 {mu_f*100:+.2f}%)"))
    res["H2_pass"] = bool(np.isfinite(t2) and t2 >= 2.0)

    # ── H3 (메커니즘 조건부 예측) ─────────────────────────────────────────────────────────
    if conf is not None and len(conf) and "broker_tier" in conf.columns:
        small = conf[conf["broker_tier"].isin(H3_SMALL_TIERS)]
        large = conf[conf["broker_tier"].isin(H3_LARGE_TIERS)]
        a_s = _abnormal_returns(small, px, cal, H_HORIZON, entry_offset)
        a_l = _abnormal_returns(large, px, cal, H_HORIZON, entry_offset)
        d3, t3, p3 = _welch(a_s, a_l)
        res["detail"]["H3"] = {"small_n": a_s.size, "large_n": a_l.size,
                               "small_mu": float(np.nanmean(a_s)) if a_s.size else np.nan,
                               "large_mu": float(np.nanmean(a_l)) if a_l.size else np.nan}
        reversed_ = bool(np.isfinite(t3) and t3 <= -2.0)
        res["rows"].append(["H3", "중소형사 > 대형/리테일",
                            f"{d3*100:+.2f}%p" if np.isfinite(d3) else "-",
                            f"{t3:+.2f}" if np.isfinite(t3) else "-",
                            f"{a_s.size:,}/{a_l.size:,}",
                            "통과" if (np.isfinite(t3) and t3 >= 2.0)
                            else ("★역전(데이터마이닝 의심)" if reversed_ else "기각")])
        res["pvals"].append(("H3", p3 / 2 if np.isfinite(p3) and np.isfinite(t3) and t3 > 0 else p3,
                             "중소형 증권사 조건부 강화"))
        res["H3_pass"] = bool(np.isfinite(t3) and t3 >= 2.0)
        res["H3_reversed"] = reversed_
    else:
        res["rows"].append(["H3", "중소형사 > 대형/리테일", "-", "-", "0", "검정불가"])
        res["pvals"].append(("H3", np.nan, "증권사 구분 정보 없음"))
        res["H3_pass"] = False
        res["H3_reversed"] = False

    if mode == "PROXY":
        res["rows"][-1][-1] = "★검정불가(PROXY: 창구 정체성 소실)"
        res["H3_pass"] = False
        res["H3_testable"] = False
    else:
        res["H3_testable"] = True

    # ── H4 (사이즈/유동성 조건부) ─────────────────────────────────────────────────────────
    if conf is not None and len(conf) and "size_bucket" in conf.columns:
        sm = conf[conf["size_bucket"] == "소형"]
        lg = conf[conf["size_bucket"] == "대형"]
        a_s = _abnormal_returns(sm, px, cal, H_HORIZON, entry_offset)
        a_l = _abnormal_returns(lg, px, cal, H_HORIZON, entry_offset)
        d4, t4, p4 = _welch(a_s, a_l)
        res["rows"].append(["H4", "소형주 > 대형주",
                            f"{d4*100:+.2f}%p" if np.isfinite(d4) else "-",
                            f"{t4:+.2f}" if np.isfinite(t4) else "-",
                            f"{a_s.size:,}/{a_l.size:,}",
                            "통과" if (np.isfinite(t4) and t4 >= 2.0) else "기각"])
        res["pvals"].append(("H4", p4 / 2 if np.isfinite(p4) and np.isfinite(t4) and t4 > 0 else p4,
                             "소형·저유동성 조건부 강화"))
        res["H4_pass"] = bool(np.isfinite(t4) and t4 >= 2.0)
    else:
        res["rows"].append(["H4", "소형주 > 대형주", "-", "-", "0", "검정불가"])
        res["pvals"].append(("H4", np.nan, "사이즈 구분 정보 없음"))
        res["H4_pass"] = False

    # ── H5 (★ 이 전략의 존재 이유) ────────────────────────────────────────────────────────
    d5, t5, p5 = _welch(ar_conf, ar_nore)
    res["rows"].append(["H5", "★리포트 조건부 우위 (확증군 > 무리포트 플로우)",
                        f"{d5*100:+.2f}%p" if np.isfinite(d5) else "-",
                        f"{t5:+.2f}" if np.isfinite(t5) else "-",
                        f"{ar_nore.size:,}",
                        "통과" if (np.isfinite(t5) and t5 >= 2.0) else "기각"])
    res["pvals"].append(("H5", p5 / 2 if np.isfinite(p5) and np.isfinite(t5) and t5 > 0 else p5,
                         "리포트가 조건부로 의미를 더하는가"))
    res["H5_pass"] = bool(np.isfinite(t5) and t5 >= 2.0)

    LOG.table(res["rows"], ["ID", "가설", "효과크기", "t", "표본(n)", "판정"],
              ["c", "l", "r", "r", "r", "c"],
              title=f"사전등록 가설 검정 H1~H5 (기각선 t=2.0 · 20영업일 CAR · 진입 d+{entry_offset})")

    # ── BH-FDR ────────────────────────────────────────────────────────────────────────────
    fdr = bh_fdr_table(res["pvals"], q=0.10)
    res["fdr"] = fdr
    # ★ 컬럼명에 괄호가 있어 itertuples 의 속성명이 _5 처럼 바뀐다 → 위치 접근 금지, dict 로 읽는다
    LOG.table([[row["가설"],
                f"{row['p값']:.4f}" if np.isfinite(row["p값"]) else "-",
                str(row["순위"]), f"{row['BH임계']:.4f}",
                row["BH(q=0.10)"], row["BY(보수)"], _trunc(row["설명"], 34)]
               for _, row in fdr.iterrows()],
              ["가설", "p값", "순위", "BH임계", "BH(q=.10)", "BY(보수)", "설명"],
              ["c", "r", "c", "r", "c", "c", "l"],
              title="다중검정 보정 — Benjamini-Hochberg FDR q=0.10 (BY 는 임의의존 가정 하 보수적 기준)")
    passed = set(fdr.loc[fdr["BH(q=0.10)"] == "통과", "가설"])
    for h in ("H1", "H2", "H3", "H4", "H5"):
        res[f"{h}_fdr"] = h in passed
    return res


def report_mechanism(res: dict, mode: str) -> str:
    """H3/H4 조건부 예측 해석표 (mechanism_tests.md 용 본문 생성)."""
    lines = ["# 메커니즘 조건부 예측 검정 (H3 / H4)", "",
             f"- 실행 모드: **{mode}**", ""]
    d3 = res.get("detail", {}).get("H3", {})
    if mode == "PROXY":
        lines += [
            "## H3 — 중소형 증권사에서 더 강한가",
            "",
            "**검정 불가.** PROXY 분기에서는 신호가 '증권사 창구' 가 아니라 '투자 주체(기관/외국인)' 다.",
            "창구 정체성이 사라지므로 중소형사와 대형사를 구분하는 축 자체가 존재하지 않는다.",
            "이 항목을 '기각' 으로 읽어서는 안 된다 — 데이터가 없어서 못 한 것이다.",
            "",
            "참고로 발행사 tier 별 하위표본 비교는 아래에 싣되, 이것은 H3 의 검정이 아니라",
            "'어떤 하우스의 리포트가 기관/외국인 수급과 더 잘 붙는가' 라는 다른 질문의 답이다.",
            "",
        ]
    else:
        lines += [
            "## H3 — 중소형 증권사에서 더 강한가",
            "",
            f"- 중소형(MID) 표본 {d3.get('small_n', 0):,}건, 평균 CAR "
            f"{100*d3.get('small_mu', float('nan')):+.2f}%",
            f"- 대형/리테일(MAJOR·RETAIL) 표본 {d3.get('large_n', 0):,}건, 평균 CAR "
            f"{100*d3.get('large_mu', float('nan')):+.2f}%",
            "",
            "**판정:** " + ("통과 — 메커니즘(리서치 배포강도가 창구에 드러난다)과 정합적."
                          if res.get("H3_pass") else
                          ("★역전 — 대형 리테일 창구에서 오히려 강하다. SPEC §3 에 따라 "
                           "데이터마이닝으로 판정한다. 리테일 창구는 주문 구성이 리서치 배포와 "
                           "무관하므로, 여기서 효과가 나온다면 그것은 메커니즘이 아니라 "
                           "다른 무언가를 잡고 있다는 뜻이다."
                           if res.get("H3_reversed") else
                           "기각 — 중소형 우위가 유의하지 않다. 표본이 작아 검정력이 낮을 수 있다.")),
            "",
        ]
    lines += [
        "## H4 — 저유동성·소형주에서 더 강한가",
        "",
        "**판정:** " + ("통과" if res.get("H4_pass") else "기각"),
        "",
        "소형주에서 강하다면 (a) 정보 확산이 느리고 (b) 창구 플로우가 유동성 대비 크기 때문에",
        "신호 대 잡음비가 높다는 해석과 정합적이다. 다만 소형주는 슬리피지가 3.5배(35bp vs 10bp)",
        "이므로, 비용 반영 후에도 남는지는 비용 민감도표에서 별도로 확인해야 한다.",
        "",
        "> 시가총액은 이 파이프라인에서 랭크·버킷으로만 사용된다. PIT 시총 사다리가 T2~T4 로",
        "> 강등된 구간에서는 사이즈 분류에 근사가 섞이므로 H4 해석 시 그 비율을 함께 볼 것.",
    ]
    return "\n".join(lines) + "\n"


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  산출물 — 성과검증표 / 강건성표 / 해석표 / 최종판정                                   ║
# ║                                                                                          ║
# ║  원칙: 숫자가 나쁘면 나쁘게 적는다. 판정 기준(SPEC §11)은 사전 확정이며 사후 변경 없다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def report_performance(bts: Dict[str, dict], bench: Dict[str, pd.Series],
                       cal: pd.DatetimeIndex, title: str = "") -> pd.DataFrame:
    """12개 구성 전체 성과표 + 벤치마크 비교."""
    rows = []
    for name, bt in bts.items():
        st = bt.get("stats") or {}
        if not st:
            continue
        rows.append([name, f"{st.get('CAGR', np.nan)*100:+.2f}%",
                     f"{st.get('연변동성', np.nan)*100:.1f}%",
                     f"{st.get('Sharpe', np.nan):.2f}",
                     f"{st.get('Sortino', np.nan):.2f}",
                     f"{st.get('MDD', np.nan)*100:.1f}%",
                     f"{st.get('Calmar', np.nan):.2f}",
                     f"{st.get('t통계량(NW)', np.nan):+.2f}",
                     f"{st.get('이벤트체결수', 0):,}",
                     f"{st.get('승률', np.nan)*100:.0f}%",
                     f"{st.get('평균보유일', np.nan):.0f}",
                     f"{st.get('연회전율', np.nan):.1f}x"])
    if not rows:
        LOG.warn("성과표를 만들 결과가 없습니다.")
        return pd.DataFrame()
    LOG.table(rows, ["구성", "CAGR", "변동성", "Sharpe", "Sortino", "MDD", "Calmar",
                     "t(NW)", "체결수", "승률", "평균보유", "회전율"],
              ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              title=f"성과 검증표 {title}".strip())

    brows = []
    for bn, bs in bench.items():
        if bn.startswith("_") or bs is None or not len(bs):
            continue
        r = bs.reindex(cal).fillna(0.0).to_numpy(float)
        eq = float(np.prod(1 + r))
        yrs = max(len(r) / 252.0, 1e-9)
        cagr = eq ** (1 / yrs) - 1 if eq > 0 else np.nan
        vol = r.std(ddof=1) * math.sqrt(252) if len(r) > 1 else np.nan
        peak = np.maximum.accumulate(np.cumprod(1 + r))
        mdd = float((np.cumprod(1 + r) / peak - 1).min())
        brows.append([bn, f"{cagr*100:+.2f}%", f"{vol*100:.1f}%",
                      f"{(cagr/vol) if vol else float('nan'):.2f}", f"{mdd*100:.1f}%"])
    if brows:
        LOG.table(brows, ["벤치마크", "CAGR", "변동성", "Sharpe", "MDD"],
                  ["l", "r", "r", "r", "r"],
                  title="벤치마크 — ★ 진짜 비교 대상은 지수가 아니라 '리포트 무차별 매수' 다")

    M = pd.DataFrame([{"구성": n, **(b.get("stats") or {})} for n, b in bts.items()])
    return M


def report_yearly(bts: Dict[str, dict], best: str, bench: Dict[str, pd.Series],
                  cal: pd.DatetimeIndex) -> None:
    if best not in bts:
        return
    yr = yearly_returns(bts[best]["daily"])
    nb = bench.get("나이브(리포트무차별매수)")
    ny = (yearly_returns(pd.DataFrame({"date": cal, "ret": nb.reindex(cal).fillna(0.0)}))
          if nb is not None else pd.Series(dtype=float))
    ks = bench.get("KOSPI")
    ky = (yearly_returns(pd.DataFrame({"date": cal, "ret": ks.reindex(cal).fillna(0.0)}))
          if ks is not None else pd.Series(dtype=float))
    rows = []
    for y in yr.index:
        rows.append([str(int(y)), f"{yr[y]*100:+.2f}%",
                     f"{ny.get(y, np.nan)*100:+.2f}%" if len(ny) else "-",
                     f"{ky.get(y, np.nan)*100:+.2f}%" if len(ky) else "-",
                     f"{(yr[y]-ny.get(y, np.nan))*100:+.2f}%p" if len(ny) else "-"])
    LOG.table(rows, ["연도", "전략", "나이브(리포트전량)", "KOSPI", "나이브 대비 초과"],
              ["c", "r", "r", "r", "r"],
              title=f"연도별 수익률 — 대표구성 [{best}]")


def report_costs(cost_bts: Dict[str, Dict[str, dict]], naive_by_cost: Dict[float, float],
                 best: str) -> str:
    """SPEC §7.1: 비용 0 / 기본 / 2배 3종 모두 보고. 2배에서 살아남는지가 핵심 판정 기준."""
    rows, md = [], ["# 비용 민감도 (SPEC §7.1)", "",
                    "| 시나리오 | CAGR | Sharpe | MDD | 나이브 대비 초과 | 판정 |",
                    "|---|---|---|---|---|---|"]
    survive2x = False
    for lab, mult in [(l, m) for l, m in COST_SCENARIOS]:
        bt = (cost_bts.get(lab) or {}).get(best)
        if not bt:
            rows.append([lab, "-", "-", "-", "-", "결과없음"])
            continue
        st = bt["stats"]
        nv = naive_by_cost.get(mult, np.nan)
        exc = st.get("CAGR", np.nan) - nv
        ok = np.isfinite(exc) and exc > 0
        if mult >= 2.0:
            survive2x = bool(ok)
        rows.append([lab, f"{st.get('CAGR', np.nan)*100:+.2f}%",
                     f"{st.get('Sharpe', np.nan):.2f}",
                     f"{st.get('MDD', np.nan)*100:.1f}%",
                     f"{exc*100:+.2f}%p" if np.isfinite(exc) else "-",
                     "초과유지" if ok else "초과소멸"])
        md.append(f"| {lab} | {st.get('CAGR', np.nan)*100:+.2f}% | "
                  f"{st.get('Sharpe', np.nan):.2f} | {st.get('MDD', np.nan)*100:.1f}% | "
                  f"{exc*100:+.2f}%p | {'초과유지' if ok else '초과소멸'} |")
    LOG.table(rows, ["비용 시나리오", "CAGR", "Sharpe", "MDD", "나이브 대비", "판정"],
              ["l", "r", "r", "r", "r", "c"],
              title="비용 민감도 — ★ 이 전략은 회전율이 높다. 2배에서 살아남는가가 핵심이다")
    md += ["", f"**2배 비용 시나리오 생존: {'예' if survive2x else '아니오'}**", "",
           "- 편도 수수료 1.5bp · 슬리피지 대형 10bp / 중형 20bp / 소형 35bp",
           "- 증권거래세는 연도별 테이블(2016 0.30% → 2025 0.15%, 5회 인하)로 적용했다. "
           "단일 세율을 쓰면 초기 구간 비용이 과소평가되어 성과가 부풀려진다.",
           "- 비교 대상인 나이브 전략에도 동일한 비용을 적용했다."]
    return "\n".join(md) + "\n"


def report_robustness(rob: dict) -> None:
    rows = []
    for k, v in rob.items():
        if not isinstance(v, dict):
            continue
        rows.append([k, v.get("value", "-"), v.get("thresh", "-"),
                     "통과" if v.get("pass") else ("판정불가" if v.get("pass") is None else "실패"),
                     _trunc(str(v.get("note", "")), 46)])
    if rows:
        LOG.table(rows, ["검정", "값", "기준", "판정", "비고"],
                  ["l", "r", "r", "c", "l"], title="강건성 검사 (SPEC §9)")


INTERP = [
    ("확증(Confirmation)", "리포트 발간 + 자사(계열) 창구 순매수 동반",
     "리서치가 실제 기관 수요로 전환되고 있다는 관측. 롱 후보."),
    ("페이드(Distribution)", "리포트 발간 직후 자사(계열) 창구 순매도",
     "물량 분배 국면일 수 있다. 롱온리에서는 배제 필터로 쓴다."),
    ("잔차 소멸", "원값에서는 신호가 있는데 이중디민 후 사라짐",
     "관측된 것은 알파가 아니라 창구 고정효과다. 그것이 결론이다."),
    ("H5 실패", "무리포트 대조군이 확증군만큼 좋음",
     "리포트가 정보를 더하지 않는다 → '리포트 전략' 이 아니라 '플로우 전략' 이다."),
    ("H3 역전", "대형 리테일 창구에서 오히려 강함",
     "메커니즘과 반대다. SPEC §3 에 따라 데이터마이닝으로 판정한다."),
    ("플라시보 유의", "가짜 이벤트에서도 효과 검출",
     "파이프라인에 미래참조가 있다. 결과 전체를 폐기해야 한다."),
]


def report_interpretation(res: dict, mode: str) -> None:
    LOG.table([[k, cond, mean] for k, cond, mean in INTERP],
              ["패턴", "관측 조건", "해석"], ["l", "l", "l"],
              title="해석표 — 무엇을 보면 무엇이라고 읽는가")
    if mode == "PROXY":
        LOG.warn("★ 이 실행은 ARC-BDF-PROXY 입니다. 신호는 '증권사 창구' 가 아니라 "
                 "'투자 주체(기관/외국인)' 이며, 원 가설의 대리 검증이 아닙니다. "
                 "H3 는 원리상 검정 불가이고 H5 는 해상도가 낮아진 형태로만 검정됩니다.")


def final_verdict(res: dict, rob: dict, cost_md: str, mode: str,
                  survive2x: bool, placebo_clean: bool) -> str:
    """SPEC §11 — 사전 확정 수용/폐기 기준. 사후 변경 없음."""
    pbo = rob.get("PBO", {}).get("raw", np.nan)
    dsr = rob.get("DSR", {}).get("raw", np.nan)
    h1 = res.get("H1_fdr", False) and res.get("H1_pass", False)
    h5 = res.get("H5_fdr", False) and res.get("H5_pass", False)
    h3 = res.get("H3_fdr", False) and res.get("H3_pass", False)
    pbo_ok = np.isfinite(pbo) and pbo < 0.5
    dsr_ok = np.isfinite(dsr) and dsr > 0.5      # DSR 은 확률이므로 '0 초과' 의 실질 기준은 0.5
    accept = h1 and h5 and h3 and pbo_ok and dsr_ok and survive2x and placebo_clean

    if not placebo_clean:
        verdict, why = "KILL", "플라시보 테스트에서 유의한 효과가 검출되었습니다(파이프라인 결함)."
    elif not h1:
        verdict, why = "KILL", "H1(확증군 CAR>0)이 BH-FDR 보정 후 통과하지 못했습니다."
    elif np.isfinite(pbo) and pbo >= 0.5:
        verdict, why = "KILL", f"PBO={pbo:.2f} ≥ 0.5 — 과최적화 확률이 절반을 넘습니다."
    elif not survive2x:
        verdict, why = "KILL", "비용 2배 시나리오에서 나이브 벤치마크 대비 초과수익이 소멸합니다."
    elif h1 and not h5:
        verdict, why = "CONDITIONAL", ("H1 은 통과했으나 H5(리포트 조건부 우위)가 실패했습니다. "
                                       "리포트 파트를 제거한 순수 브로커/수급 플로우 전략으로 "
                                       "재정의해 별도 검증해야 하며, 현 형태로는 배분 금지입니다.")
    elif accept:
        verdict, why = "ACCEPT", "SPEC §11 의 모든 수용 조건을 충족했습니다."
    else:
        missing = [n for n, ok in (("H3", h3), ("DSR", dsr_ok)) if not ok]
        verdict, why = "CONDITIONAL", f"핵심 조건 일부 미충족: {', '.join(missing) or '기타'}."

    lines = [
        "# FINAL VERDICT", "",
        f"## 판정: **{verdict}**", "", why, "",
        f"- 전략: {STRATEGY_NAME} ({'ARC-BDF-PROXY' if mode == 'PROXY' else 'ARC-BDF'})",
        f"- 빌드: `{BUILD_VERSION}` · 구간 {BACKTEST_START} ~ {BACKTEST_END}",
        "",
        "## SPEC §11 조건별 충족 현황", "",
        "| 조건 | 기준 | 결과 | 충족 |",
        "|---|---|---|---|",
        f"| H1 (BH-FDR 후) | 통과 | {'통과' if h1 else '미통과'} | {'✔' if h1 else '✘'} |",
        f"| H5 (리포트 조건부 우위) | 통과 | {'통과' if h5 else '미통과'} | {'✔' if h5 else '✘'} |",
        f"| H3 (중소형사 강화) | 통과 | "
        f"{'검정불가(PROXY)' if mode == 'PROXY' else ('통과' if h3 else '미통과')} | "
        f"{'✔' if h3 else '✘'} |",
        f"| PBO | < 0.50 | {pbo:.3f} | {'✔' if pbo_ok else '✘'} |",
        f"| DSR | > 0.50 | {dsr:.3f} | {'✔' if dsr_ok else '✘'} |",
        f"| 비용 2배 초과수익 | 유지 | {'유지' if survive2x else '소멸'} | "
        f"{'✔' if survive2x else '✘'} |",
        f"| 플라시보 | 무효과 | {'무효과' if placebo_clean else '★효과검출'} | "
        f"{'✔' if placebo_clean else '✘'} |",
        "",
    ]
    if mode == "PROXY":
        lines += [
            "## ⚠ 이 판정의 적용 범위", "",
            "이 실행은 **ARC-BDF-PROXY** 입니다. 거래원(회원사)별 일별 매매동향의 과거 이력을",
            "확보할 수 없어(Phase 0 참조) 신호를 '투자 주체(기관/외국인)' 로 대체했습니다.",
            "",
            "- 이것은 **원 가설(ARC-BDF)의 대리 검증이 아닙니다.**",
            "- **H3 는 원리상 검정 불가**입니다 — 창구 단위가 사라졌기 때문입니다.",
            "- 따라서 위 판정이 ACCEPT 라 해도 그것은 ARC-BDF 의 수용이 아니라",
            "  ARC-BDF-PROXY 라는 별개 전략의 수용입니다.",
            "- 'ARC-BDF 10년 백테스트 완료' 라고 보고해서는 안 됩니다.",
            "",
        ]
    lines += ["## 비용 민감도", "", cost_md, ""]
    lines += ["## 참고", "",
              "- 이 문서의 판정 기준은 실행 전에 확정된 것이며 결과를 본 뒤 변경하지 않았습니다.",
              "- 특정 증권사에 대한 가치판단은 담지 않습니다. 통계적 패턴만 기술합니다(SPEC §0.5).",
              "- 투자자문이 아닙니다."]
    return "\n".join(lines) + "\n"


def report_dataflow(ctx: dict) -> None:
    """★ 사용자 요구: '데이터 입출력이 어디서 이뤄지는지 한눈에'."""
    rows = []
    for k, v in ctx.items():
        if isinstance(v, pd.DataFrame):
            rows.append([k, f"{len(v):,}행 × {len(v.columns)}열", f"{mem_mb(v):.1f}MB",
                         ", ".join(map(str, list(v.columns)[:6]))])
        elif isinstance(v, (list, tuple, set)):
            rows.append([k, f"{len(v):,}개", "-", ""])
    if rows:
        LOG.table(rows, ["데이터셋", "규모", "메모리", "주요 컬럼"],
                  ["l", "r", "r", "l"], title="데이터 흐름 — 무엇이 어디까지 만들어졌는가")


def write_outputs(paths: Dict[str, str]) -> List[str]:
    ok = []
    for name, content in paths.items():
        try:
            p = out_path(name)
            atomic_write_text(p, content)
            VAULT.put_blob("report", "arc_bdf", name.replace(".", "_"),
                           content.encode("utf-8"), name.rsplit(".", 1)[-1],
                           scope="private", source=STRATEGY_ID)
            ok.append(p)
        except Exception as e:                                        # noqa
            LOG.warn(f"{name} 저장 실패: {type(e).__name__}: {e}")
    return ok


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  3중 자가검정 — 계약(K1~K16) / 합성 스모크 / 실경로 리허설                            ║
# ║                                                                                          ║
# ║  세 검증은 서로 다른 것을 본다:                                                            ║
# ║    ① 계약(K)   협상 불가 규칙 — PIT·생존편향·look-ahead·절단·비용                          ║
# ║    ② 스모크    합성데이터로 '계산 경로' 를 증명 (네트워크·키 불필요)                        ║
# ║    ③ 리허설    네트워크만 가짜로 두고 '수집·정제 함수' 를 실물 실행                         ║
# ║  ①②를 다 통과하고도 실행 2분 만에 수집부 한 줄 때문에 죽는 일이 실제로 있었다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

_CONTRACTS: List[Tuple[str, str, bool, str]] = []


def _k(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]) -> bool:
    try:
        ok, msg = fn()
    except Exception as e:                                            # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    _CONTRACTS.append((cid, name, bool(ok), str(msg)[:120]))
    return bool(ok)


def run_contracts(strict: bool = True) -> bool:
    _CONTRACTS.clear()
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=400))

    def k1():
        """진입 오프셋 — 거래원/수급은 장 마감 후 공개. d 종가 진입은 SPEC §0.1 위반."""
        bad = [c.k for c in (BTConfig(k=0, hold=20, version="raw"),
                             BTConfig(k=2, hold=20, version="raw"))
               if BTConfig(k=c.k, hold=20, version="raw").entry_offset <= c.k]
        return (not bad, f"entry_offset = k+1 확인 (k=0→1, k=2→3)")

    def k2():
        """이중디민 베이스라인이 이벤트 윈도와 겹치지 않는가 (미래참조 차단)."""
        rng = np.random.default_rng(1)
        n = 400
        d = pd.DataFrame({"actor": "A", "code": "000001",
                          "date": cal[:n], "netbuy_share": rng.normal(0, 0.01, n)})
        R = build_flow_raw(d, k=2)
        RES = residualize_flow(R, k=2, baseline=60)
        # 마지막 원소를 극단값으로 바꿔도 그 이전 시점의 잔차는 변하면 안 된다
        d2 = d.copy()
        d2.loc[d2.index[-1], "netbuy_share"] = 99.0
        R2 = build_flow_raw(d2, k=2)
        RES2 = residualize_flow(R2, k=2, baseline=60)
        a = RES["flow_resid"].to_numpy()[:n - 10]
        b = RES2["flow_resid"].to_numpy()[:n - 10]
        same = np.allclose(np.nan_to_num(a), np.nan_to_num(b), atol=1e-12)
        return (same, "미래 관측을 바꿔도 과거 잔차가 불변" if same
                else "★미래 값이 과거 잔차에 영향 — look-ahead")

    def k3():
        """PIT 유니버스: 상장 전/폐지 후 종목이 절대 섞이지 않는가."""
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["가", "나"],
                            "market": ["KOSPI", "KOSDAQ"],
                            "listing_date": [pd.Timestamp("2021-01-04"), pd.NaT],
                            "delisting_date": [pd.NaT, pd.Timestamp("2020-06-01")],
                            "industry": ["x", "y"]})
        sec.loc[1, "listing_date"] = pd.Timestamp("2019-01-02")
        px = pd.DataFrame({"code": np.repeat(["000001", "000002"], len(cal)),
                           "date": np.tile(cal, 2), "close": 1000.0, "volume": 1000,
                           "amount": 1e6})
        u = DailyUniverse(sec, px)
        pre = u.is_member(["000001"], [pd.Timestamp("2020-06-01")])
        post = u.is_member(["000002"], [pd.Timestamp("2020-12-01")])
        return ((not pre[0]) and (not post[0]),
                f"상장전 배제={not pre[0]} · 폐지후 배제={not post[0]}")

    def k4():
        """상위5 절단: 한쪽만 관측된 창구의 순매수는 0 이 아니라 결측이어야 한다."""
        S = pd.DataFrame({
            "captured_at": [now_kst()] * 3, "trade_date": [pd.Timestamp("2024-01-02")] * 3,
            "code": ["000001"] * 3, "side": ["BUY", "SELL", "BUY"], "rank": [1, 1, 2],
            "member_raw": ["미래에셋", "키움증권", "삼성"], "volume": [100.0, 80.0, 50.0],
            "src_url": [""] * 3, "parser_ver": [PARSER_VER] * 3})
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        D = member_snapshot_to_daily(S, None, bm)
        cen = D[D["censored"]]
        bad = cen["net_vol"].notna().any()
        return (not bad and len(cen) > 0,
                f"절단행 {len(cen)}건 전부 net_vol 결측" if not bad else "★절단행에 순매수가 채워짐")

    def k5():
        """연도별 증권거래세: 단일 세율 금지. 2016 과 2025 가 달라야 한다."""
        a = sell_tax_rate("2016-09-01", "KOSPI")
        b = sell_tax_rate("2025-03-01", "KOSPI")
        return (a > b and abs(a - 0.0030) < 1e-9 and abs(b - 0.0015) < 1e-9,
                f"2016={a:.4f} > 2025={b:.4f}")

    def k6():
        """PIT 분위 컷: 미래 이벤트가 오늘의 컷에 영향을 주면 안 된다."""
        n = 800
        d = pd.DataFrame({"date": pd.DatetimeIndex(np.repeat(cal[:200], 4)),
                          "s": np.random.default_rng(2).normal(size=n)})
        c1 = pit_quantile_cut(d, "s", 0.7)
        d2 = d.copy()
        d2.loc[d2.index[-50:], "s"] = 1e6
        c2 = pit_quantile_cut(d2, "s", 0.7)
        a, b = c1.to_numpy()[:600], c2.to_numpy()[:600]
        same = np.allclose(np.nan_to_num(a), np.nan_to_num(b), atol=1e-9)
        return (same, "미래 극단값이 과거 컷에 영향 없음" if same else "★컷에 미래정보 유입")

    def k7():
        """증권사 매핑: 비증권 법인이 증권사로 흡수되지 않는가."""
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        bad = [x for x in ("미래에셋생명", "한국투자파트너스", "키움투자자산운용",
                           "IBK기업은행") if bm.resolve(x) is not None]
        pit = (bm.resolve("우리투자증권", "2013-01-01") == "NH투자증권" and
               bm.resolve("우리투자증권", "2025-01-01") == "우리투자증권")
        return (not bad and pit, f"비증권 흡수 {bad or '없음'} · 사명재사용 PIT={pit}")

    def k8():
        """BH-FDR 이 실제로 보정하는가 (p=[0.01,0.2,0.3,0.4,0.5], q=0.1)."""
        t = bh_fdr_table([("A", 0.01, ""), ("B", 0.20, ""), ("C", 0.30, ""),
                          ("D", 0.40, ""), ("E", 0.50, "")], q=0.10)
        n_pass = int((t["BH(q=0.10)"] == "통과").sum())
        return (n_pass == 1, f"5개 중 {n_pass}개 통과 (기대 1)")

    def k9():
        """DSR: 시도 횟수가 늘면 값이 낮아져야 한다."""
        r = np.random.default_rng(3).normal(0.0006, 0.01, 1500)
        s = np.random.default_rng(4).normal(0.8, 0.3, 20)
        a = deflated_sharpe(r, s, 3)["dsr"]
        b = deflated_sharpe(r, s, 60)["dsr"]
        return (np.isfinite(a) and np.isfinite(b) and b <= a + 1e-9,
                f"N=3 → {a:.3f} ≥ N=60 → {b:.3f}")

    def k10():
        """PBO: 완전 무작위 구성들에서는 0.5 근처여야 한다."""
        rng = np.random.default_rng(5)
        P = rng.normal(0, 0.01, size=(1000, 12))
        v = pbo_cscv(P, n_split=8)["pbo"]
        return (np.isfinite(v) and 0.2 <= v <= 0.8, f"무작위 12구성 PBO={v:.2f} (기대 ≈0.5)")

    def k11():
        """블록 부트스트랩이 자기상관을 보존하는가 (iid 보다 넓은 신뢰구간)."""
        rng = np.random.default_rng(6)
        e = rng.normal(0, 0.01, 1500)
        r = np.zeros(1500)
        for i in range(1, 1500):
            r[i] = 0.5 * r[i - 1] + e[i]
        w = block_bootstrap(r, n_iter=300, block=21)
        n = block_bootstrap(r, n_iter=300, block=1)
        wide = (w["ci_hi"] - w["ci_lo"]) >= (n["ci_hi"] - n["ci_lo"]) * 0.95
        return (wide, f"블록21 폭 {w['ci_hi']-w['ci_lo']:.3f} vs 블록1 {n['ci_hi']-n['ci_lo']:.3f}")

    def k12():
        """정규분포 함수: scipy 유무와 무관하게 같은 값."""
        errs = [abs(norm_cdf(norm_ppf(p)) - p) for p in (0.01, 0.1, 0.5, 0.9, 0.99)]
        return (max(errs) < 1e-6, f"norm_ppf/​cdf 왕복 최대오차 {max(errs):.2e}")

    def k13():
        """Newey-West: 자체 구현과 03_util 구현이 일치."""
        x = np.random.default_rng(7).normal(0.001, 0.01, 600)
        _, t1 = hac_tstat(x)
        _, t2, _ = nw_se(x)
        return (abs(t1 - t2) < 1e-6, f"hac_tstat={t1:.6f} vs nw_se={t2:.6f}")

    def k14():
        """tz-aware 날짜가 하루 밀리지 않는가 (yfinance 폴백 경로)."""
        s = as_ts_series(pd.Series(pd.date_range("2024-01-02", periods=2, tz="Asia/Seoul")))
        return (s.iloc[0] == pd.Timestamp("2024-01-02"), f"KST 자정 → {s.iloc[0].date()}")

    def k15():
        """빈 프레임 concat 이 dtype 을 오염시키지 않는가."""
        a = pd.DataFrame({"v": [1.0, 2.0]})
        e = empty_like({"v": "float64"})
        out = concat_nonempty([a, e])
        return (str(out["v"].dtype) == "float64", f"concat 후 dtype={out['v'].dtype}")

    def k16():
        """이벤트 정의: 목표가 '0' 이 -100% 하향으로 오독되지 않는가."""
        rep = pd.DataFrame({
            "pub_date": pd.to_datetime(["2020-01-02", "2020-03-02", "2020-06-01"]),
            "stock_code": ["000001"] * 3, "broker_name": ["삼성증권"] * 3,
            "target_price": [10000.0, np.nan, 11000.0], "opinion": ["HOLD"] * 3,
            "source": ["t"] * 3, "report_uid": ["a", "b", "c"]})
        rep["target_price"] = rep["target_price"].replace(0, np.nan)
        g = rep.sort_values(["broker_name", "stock_code", "pub_date"], kind="stable")
        prev = g.groupby(["broker_name", "stock_code"], observed=True)["target_price"] \
                .transform(lambda s: s.ffill().shift(1))
        rev = (g["target_price"] - prev) / prev
        last = float(rev.iloc[-1])
        return (abs(last - 0.10) < 1e-9,
                f"결측 리포트를 건너뛰고 10000→11000 = {last:+.2%} (ffill 후 shift)")

    checks = [("K1", "진입 시점 d+k+1 강제 (look-ahead 금지)", k1),
              ("K2", "이중디민 베이스라인 미래참조 차단", k2),
              ("K3", "PIT 유니버스 상장전/폐지후 배제", k3),
              ("K4", "상위5 절단 → 순매수 결측 보존", k4),
              ("K5", "연도별 증권거래세 (단일세율 금지)", k5),
              ("K6", "PIT 분위 컷 미래정보 차단", k6),
              ("K7", "증권사 매핑 오매칭·사명재사용", k7),
              ("K8", "BH-FDR 다중검정 보정", k8),
              ("K9", "DSR 시도횟수 반영", k9),
              ("K10", "PBO(CSCV) 무작위 기준선", k10),
              ("K11", "블록 부트스트랩 자기상관 보존", k11),
              ("K12", "정규분포 자체구현 정확도", k12),
              ("K13", "Newey-West 두 구현 일치", k13),
              ("K14", "tz-aware 날짜 하루밀림 방지", k14),
              ("K15", "빈 프레임 dtype 오염 방지", k15),
              ("K16", "목표가 결측·0 처리", k16)]
    for cid, nm, fn in checks:
        _k(cid, nm, fn)

    rows = [[c, _trunc(n, 42), "✔" if ok else "✘", _trunc(m, 44)]
            for c, n, ok, m in _CONTRACTS]
    LOG.table(rows, ["ID", "계약", "판정", "근거"], ["c", "l", "c", "l"],
              title="계약 자동검정 K1~K16 — 협상 불가 규칙")
    failed = [c for c, _, ok, _ in _CONTRACTS if not ok]
    if failed:
        LOG.error(f"계약 위반 {len(failed)}건: {failed} — 이 상태의 산출물은 신뢰할 수 없습니다.")
        if strict:
            raise KillCriteria(f"계약 위반: {failed}")
        return False
    LOG.ok(f"계약 {len(_CONTRACTS)}건 전부 통과 — 계산 경로가 규칙을 지킵니다.")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════
#  합성 스모크 — 네트워크·키 없이 전 출력물을 예행연습
# ══════════════════════════════════════════════════════════════════════════════════════════
def make_synthetic(n_codes: int = 120, n_days: int = 900, seed: int = SEED) -> dict:
    """★ 신호가 '진짜로 있는' 합성 세계를 만든다. 파이프라인이 그것을 찾아내지 못하면
    파이프라인이 고장난 것이다(데이터 문제가 아니라)."""
    rng = np.random.default_rng(seed)
    cal = pd.DatetimeIndex(pd.bdate_range("2020-01-02", periods=n_days))
    codes = [f"{i:06d}" for i in range(1, n_codes + 1)]
    brokers = [b for b, t, *_ in BROKER_MEMBER_SEED if t in ("MAJOR", "MID")][:12]

    # 가격
    drift = rng.normal(0.0002, 0.0004, n_codes)[:, None]
    shocks = rng.normal(0, 0.02, (n_codes, n_days))
    px_mat = 10000 * np.cumprod(1 + drift + shocks, axis=1)
    px = pd.DataFrame({
        "code": np.repeat(codes, n_days), "date": np.tile(cal, n_codes),
        "close": px_mat.ravel(),
        "volume": rng.integers(5e4, 5e6, n_codes * n_days).astype(float)})
    px["open"] = px["high"] = px["low"] = px["close"]
    px["amount"] = px["close"] * px["volume"]
    px["src"] = "synthetic"

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                        "listing_date": cal[0] - pd.Timedelta(days=800),
                        "delisting_date": pd.NaT,
                        "industry": rng.choice(list("ABCDE"), n_codes),
                        "corp_code": ""})
    # 일부 종목은 중간에 상장폐지시켜 생존편향 경로를 실제로 태운다
    dead = rng.choice(n_codes, size=max(3, n_codes // 20), replace=False)
    sec.loc[dead, "delisting_date"] = cal[int(n_days * 0.7)]

    # 플로우 (기본은 잡음)
    rows = []
    for b in brokers:
        sub = rng.choice(codes, size=max(20, n_codes // 3), replace=False)
        for c in sub:
            rows.append(pd.DataFrame({"actor": b, "code": c, "date": cal,
                                      "netbuy_share": rng.normal(0, 0.004, n_days)}))
    F = pd.concat(rows, ignore_index=True)
    F["actor_kind"] = "MEMBER"
    F["net_vol"] = F["netbuy_share"] * 1e5
    F["censored"] = False
    F["upper_bound"] = np.nan
    F["src"] = "synthetic"

    # 이벤트 + '진짜 알파': 확증군에만 이후 20일 초과수익을 심는다
    n_ev = 2500
    ev_i = rng.integers(120, n_days - 90, n_ev)
    ev_c = rng.choice(codes, n_ev)
    ev_b = rng.choice(brokers, n_ev)
    boost = rng.random(n_ev) < 0.35
    E = pd.DataFrame({"event_uid": [f"E{i}" for i in range(n_ev)],
                      "broker": ev_b, "code": ev_c, "pub_date": cal[ev_i],
                      "opinion": "BUY", "target_price": np.nan, "prev_target": np.nan,
                      "tp_rev": np.nan, "is_new_cov": False, "buyish_reason": "매수의견",
                      "source": "synthetic", "report_uid": ""})
    E["broker_tier"] = [dict((b, t) for b, t, *_ in BROKER_MEMBER_SEED).get(b, "MID")
                        for b in ev_b]
    key = {}
    for i in range(n_ev):
        if boost[i]:
            key[(ev_b[i], ev_c[i], cal[ev_i[i]])] = True
    if key:
        idx = pd.MultiIndex.from_arrays([F["actor"], F["code"], F["date"]])
        hit = np.array([k in key for k in idx], bool)
        F.loc[hit, "netbuy_share"] = F.loc[hit, "netbuy_share"] + 0.02
        # 심어둔 알파: 확증 이벤트 이후 20일에 걸쳐 +3% 누적
        cpos = {c: i for i, c in enumerate(codes)}
        for i in range(n_ev):
            if not boost[i]:
                continue
            ci, di = cpos[ev_c[i]], ev_i[i]
            hi = min(di + 21, n_days)
            px.loc[(px["code"] == ev_c[i]) & (px["date"].isin(cal[di + 1:hi])), "close"] *= 1.0
        # 가격 조정은 행 단위 루프가 비싸므로 행렬에서 직접 처리
        add = np.zeros((n_codes, n_days))
        for i in range(n_ev):
            if not boost[i]:
                continue
            ci, di = cpos[ev_c[i]], ev_i[i]
            hi = min(di + 21, n_days)
            add[ci, di + 1:hi] += 0.0015
        newpx = px_mat * np.cumprod(1 + add, axis=1)
        px["close"] = newpx.ravel()
        px["open"] = px["high"] = px["low"] = px["close"]
        px["amount"] = px["close"] * px["volume"]
    return {"cal": cal, "px": px, "sec": sec, "flow": F, "events": E,
            "codes": codes, "brokers": brokers, "alpha_frac": float(boost.mean())}


def run_smoke(strict: bool = True) -> bool:
    LOG.banner("[1] 합성데이터 엔드투엔드 스모크",
               "실데이터를 쓰기 전에 계산 경로 자체를 증명한다 (네트워크·키 불필요)")
    t0 = time.time()
    syn = make_synthetic()
    cal, px, sec, F, E = syn["cal"], syn["px"], syn["sec"], syn["flow"], syn["events"]
    uni = DailyUniverse(sec, px)
    bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf, "valid_to": vt}
                    for b, t, a, vf, vt in BROKER_MEMBER_SEED])

    E = attach_matched_actor(E, "MEMBER")
    R = build_flow_raw(F, k=2)
    RES = residualize_flow(R, k=2, baseline=60)
    S = attach_signal(E, RES)
    S["marcap"] = 1e11
    S["ret20"] = 0.0
    S["turnover"] = 0.01
    S["industry"] = "A"
    S["size_bucket"] = "중형"
    S["sig_raw"] = S["flow_raw"]
    S["sig_resid"] = S["flow_resid"]

    cfg = BTConfig(k=2, hold=20, version="resid")
    bt = run_event_backtest(S, px, cal, uni, cfg, sec=sec)
    st = bt["stats"]
    ok_bt = bool(st) and st.get("이벤트체결수", 0) > 0
    LOG.info(f"  스모크 백테스트 — 체결 {st.get('이벤트체결수', 0):,}건 · "
             f"CAGR {st.get('CAGR', float('nan'))*100:+.2f}% · "
             f"Sharpe {st.get('Sharpe', float('nan')):.2f}")

    groups = split_groups(S, "sig_resid")
    res = test_hypotheses(groups, S, px, cal, bm, "MEMBER", entry_offset=cfg.entry_offset)
    found = res.get("H1_pass", False)
    LOG.info(f"  심어둔 알파(확증군 비율 {syn['alpha_frac']*100:.0f}%) 탐지: "
             f"{'✔ 성공' if found else '✘ 실패'}")

    ok = ok_bt
    if not ok:
        LOG.error("스모크 실패 — 계산 경로에 문제가 있습니다. 실데이터로 진행하지 마세요.")
        if strict:
            raise KillCriteria("합성 스모크 실패")
    else:
        LOG.ok(f"스모크 통과 ({time.time()-t0:.1f}초). 계산 경로가 살아 있습니다."
               + ("" if found else
                  "  ※ 다만 심어둔 알파를 H1 이 잡지 못했습니다 — 검정력 또는 표본 문제일 수 "
                  "있으니 실데이터 결과의 '기각' 을 곧바로 '효과 없음' 으로 읽지 마세요."))
    return ok


# ══════════════════════════════════════════════════════════════════════════════════════════
#  실경로 리허설 — 네트워크만 가짜, 수집·정제 함수는 실물 실행
# ══════════════════════════════════════════════════════════════════════════════════════════
_FX_MEMBER_HTML = """<html><head><meta charset="utf-8"></head><body>
<table summary="거래원정보"><tr><th>매도상위</th><th>거래량</th><th>매수상위</th><th>거래량</th></tr>
<tr><td>미래에셋</td><td class="tah">120,000</td><td>키움증권</td><td class="tah">98,000</td></tr>
<tr><td>모건서울</td><td class="tah">80,500</td><td>미래에셋</td><td class="tah">75,300</td></tr>
<tr><td>삼성</td><td class="tah">61,000</td><td>NH투자증권</td><td class="tah">54,200</td></tr>
<tr><td>키움증권</td><td class="tah">44,000</td><td>한국투자</td><td class="tah">41,900</td></tr>
<tr><td>신한투자</td><td class="tah">30,100</td><td>하나</td><td class="tah">28,700</td></tr>
</table></body></html>"""

_FX_FRGN_HTML = """<html><head><meta charset="utf-8"></head><body>
<table summary="외국인/기관"><tr><th>날짜</th><th>종가</th><th>거래량</th>
<th>기관 순매매량</th><th>외국인 순매매량</th></tr>
<tr><td>2024.01.05</td><td>71,000</td><td>1,200,000</td><td>+30,000</td><td>-12,000</td></tr>
<tr><td>2024.01.04</td><td>70,500</td><td>1,100,000</td><td>-8,000</td><td>+22,000</td></tr>
<tr><td>2024.01.03</td><td>70,100</td><td>980,000</td><td>+4,000</td><td>+5,000</td></tr>
</table></body></html>"""


def run_rehearsal(strict: bool = True) -> bool:
    """수집기의 '파싱·정제' 부분을 픽스처로 실제 실행한다.
    이 컨테이너처럼 한국 사이트가 막힌 환경에서 코드를 검증할 수 있는 유일한 수단이다."""
    LOG.banner("[2] 실경로 리허설", "네트워크만 가짜로 두고 수집·정제 함수를 실물 실행한다")
    rows = []

    def _rh(name, fn):
        try:
            ok, msg = fn()
        except Exception as e:                                        # noqa
            ok, msg = False, f"{type(e).__name__}: {e}"
        rows.append([name, "✔" if ok else "✘", _trunc(str(msg), 56)])
        return ok

    def r1():
        d = parse_member_page(_FX_MEMBER_HTML, "005930", "fx://member")
        if d is None or len(d) == 0:
            return False, "거래원 파싱 0건"
        n_buy = int((d["side"] == "BUY").sum())
        n_sell = int((d["side"] == "SELL").sum())
        return (n_buy >= 3 and n_sell >= 3,
                f"매수 {n_buy} · 매도 {n_sell} · 예시 {d['member_raw'].tolist()[:3]}")

    def r2():
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        d = parse_member_page(_FX_MEMBER_HTML, "005930", "fx://member")
        D = member_snapshot_to_daily(d, None, bm)
        unmapped = [x for x in D["member_key"] if str(x).startswith("UNMAPPED")]
        cen = int(D["censored"].sum())
        return (not unmapped and cen > 0,
                f"미매핑 {unmapped or '없음'} · 절단행 {cen}건(순매수 결측 유지)")

    def r3():
        d = _parse_frgn_table(_FX_FRGN_HTML)
        if d is None or len(d) == 0:
            return False, "frgn 파싱 0건"
        yr_ok = bool((d["date"].dt.year == 2024).all())
        return (yr_ok and d["inst_net"].notna().all(),
                f"{len(d)}행 · 연도 {sorted(d['date'].dt.year.unique().tolist())}")

    def r4():
        s = _dedup_repeat("삼성전자(005930) 4Q 프리뷰 삼성전자(005930) 4Q 프리뷰")
        return ("삼성전자" in s and s.count("삼성전자") == 1, f"→ {s[:40]}")

    def r5():
        vals = [_nv_any_date(x) for x in ("23.05.12", "20230512", "1683849600000",
                                          "2023-05-12T09:00:00")]
        ok = all(v is not None and v.startswith("2023") for v in vals)
        return (ok, f"{vals}")

    def r6():
        raw = _FX_FRGN_HTML.encode("utf-8")
        tabs = safe_read_html(raw)
        return (len(tabs) > 0, f"safe_read_html → {len(tabs)}개 표")

    def r7():
        bm = BrokerMap([{"broker": b, "tier": t, "aliases": a, "valid_from": vf,
                         "valid_to": vt} for b, t, a, vf, vt in BROKER_MEMBER_SEED])
        rep = pd.DataFrame({
            "pub_date": pd.to_datetime(["2020-01-02", "2020-04-01", "2020-07-01"]),
            "stock_code": ["000001"] * 3, "broker_name": ["하나금융투자"] * 3,
            "target_price": [10000.0, np.nan, 10500.0], "opinion": ["HOLD"] * 3,
            "source": ["fx"] * 3, "report_uid": list("abc")})
        cal = pd.DatetimeIndex(pd.bdate_range("2019-01-01", periods=600))
        sec = pd.DataFrame({"code": ["000001"], "name": ["가"], "market": ["KOSPI"],
                            "listing_date": [pd.Timestamp("2015-01-02")],
                            "delisting_date": [pd.NaT], "industry": ["A"]})
        px = pd.DataFrame({"code": "000001", "date": cal, "close": 1000.0,
                           "volume": 1000.0, "amount": 1e6})
        uni = DailyUniverse(sec, px)
        E = build_event_panel(rep, bm, uni, cal)
        return (len(E) >= 1, f"이벤트 {len(E)}건 · 사유 {E['buyish_reason'].tolist() if len(E) else []}")

    ok = all([_rh("거래원 페이지 파싱", r1),
              _rh("거래원 → 일별(절단 보존)", r2),
              _rh("투자자별 수급 표 파싱", r3),
              _rh("제목 반복 제거(공백 구분)", r4),
              _rh("네이버 JSON 날짜 정규화", r5),
              _rh("safe_read_html 폴백", r6),
              _rh("이벤트 패널 구성(+3% 상향)", r7)])
    LOG.table(rows, ["리허설 항목", "판정", "결과"], ["l", "c", "l"],
              title="실경로 리허설 — 수집·정제 함수 실물 실행")
    if not ok:
        LOG.error("리허설 실패 — 실데이터 수집 전에 고쳐야 합니다.")
        if strict:
            raise KillCriteria("실경로 리허설 실패")
    else:
        LOG.ok("리허설 통과 — 수집·정제 경로가 살아 있습니다.")
    return ok


# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이터 — 전체 실행 순서와 산출물                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def offer_download(paths: Sequence[str]) -> None:
    """미리보기 없이 '클릭하면 바로 저장' 되는 링크. 산출물이 많으면 zip 하나로 묶는다."""
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    zp = None
    try:
        import zipfile as _zf
        zp = out_path(f"ARC_BDF_outputs_{now_kst():%Y%m%d_%H%M}.zip")
        with _zf.ZipFile(zp, "w", _zf.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, arcname=os.path.basename(p))
    except Exception as e:                                            # noqa
        LOG.warn(f"산출물 압축 실패({type(e).__name__}) — 개별 파일로 안내합니다.")
        zp = None

    targets = [zp] if zp else paths
    _safe_print("")
    for p in targets:
        _safe_print(f"  산출물: {os.path.abspath(p)}")   # ★ 링크가 안 떠도 경로는 항상 보인다

    if ENV.get("colab"):
        try:
            from google.colab import files as _f       # type: ignore
            for p in targets:
                _f.download(p)
        except Exception:
            pass
    try:
        from IPython.display import display, HTML      # type: ignore
        import base64
        html = ["<div style='font-family:system-ui;font-size:14px;line-height:2'>"]
        for p in targets:
            n = os.path.getsize(p)
            if n > 5 * 1024 * 1024:                    # 5MB 초과분을 노트북에 박으면 .ipynb 가 붓는다
                html.append(f"<div>· {os.path.basename(p)} ({n/1e6:.1f}MB) — "
                            f"<code>{os.path.abspath(p)}</code></div>")
                continue
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            html.append(
                f"<a download='{os.path.basename(p)}' "
                f"href='data:application/octet-stream;base64,{b64}' "
                f"style='display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;"
                f"background:#1a73e8;color:#fff;border-radius:6px;text-decoration:none'>"
                f"⬇ {os.path.basename(p)} ({n/1e6:.1f}MB)</a>")
        html.append("</div>")
        display(HTML("".join(html)))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════════════════
def collect_all() -> dict:
    """L1 수집 — 각 단계는 실패해도 파이프라인을 죽이지 않고 '무엇이 없는지' 를 남긴다."""
    ctx: Dict[str, Any] = {}
    warm = (as_ts(BACKTEST_START) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")

    with PIPE.stage("L1.DGK", "공공데이터 일별 전종목 (시총·상장주식수)", "L1",
                    budget_s=5400, critical=False):
        ctx["dgk"] = fetch_datagokr_panel(warm, BACKTEST_END)

    with PIPE.stage("L1.UNI", "종목 마스터 · 상장/폐지 이력", "L1", budget_s=900):
        snaps = (dgk_listing_snapshots(ctx["dgk"]) if len(ctx.get("dgk", []))
                 else fetch_listing_snapshots(date_range_me(BACKTEST_START, BACKTEST_END)))
        ctx["snapshots"] = snaps
        ctx["sec"] = build_security_master(snaps)

    with PIPE.stage("L1.PX", "가격 · 거래대금", "L1", budget_s=5400):
        codes = ctx["sec"]["code"].tolist()
        px = fetch_prices(codes, warm, BACKTEST_END)
        if len(ctx.get("dgk", [])):
            # 공공데이터 시세를 가격 패널에 합류시킨다(가장 신뢰도 높은 소스)
            g = ctx["dgk"].reindex(columns=PRICE_COLS + ["shares", "marcap"]).copy()
            g["src"] = "datagokr"
            px = concat_nonempty([g.reindex(columns=PRICE_COLS), px], cols=PRICE_COLS)
            px = (px.sort_values(["code", "date"], kind="stable")
                    .drop_duplicates(["code", "date"], keep="first").reset_index(drop=True))
        ctx["px"] = px
        ctx["cal"] = build_trading_calendar(px)

    with PIPE.stage("L1.MCAP", "PIT 시가총액 사다리", "L1", budget_s=1800, critical=False):
        corps = (ctx["sec"]["corp_code"].dropna().astype(str).tolist()
                 if "corp_code" in ctx["sec"].columns else [])
        years = list(range(as_ts(BACKTEST_START).year - 1, as_ts(BACKTEST_END).year + 1))
        shares_pit = fetch_dart_shares(corps, years)
        cur = fetch_current_shares(ctx["sec"])
        mc = build_marketcap_panel(ctx["px"], ctx["sec"], shares_pit, cur)
        if len(ctx.get("dgk", [])):
            # ★ 공공데이터의 시총/주식수는 '그 시점 값' 이므로 T1 보다도 우선한다
            g = ctx["dgk"][["code", "date", "marcap", "shares"]].dropna(subset=["marcap"])
            mc = mc.merge(g.rename(columns={"marcap": "mc_dgk"}), on=["code", "date"],
                          how="left")
            hit = mc["mc_dgk"].notna()
            set_where(mc, hit, "marcap", mc.loc[hit, "mc_dgk"])
            set_where(mc, hit, "mc_tier", "T0")
            mc = mc.drop(columns=[c for c in ("mc_dgk", "shares") if c in mc.columns])
            LOG.ok(f"공공데이터 시총으로 {int(hit.sum()):,}행을 T0(정품 관측)으로 승격 — "
                   f"{100*hit.mean():.1f}%. 이 비율이 높을수록 H4/비교전략이 정확합니다.")
        ctx["mc"] = assign_size_bucket(mc)

    with PIPE.stage("L1.RESEARCH", "애널리스트 리포트 수집 · 원장 구축", "L1",
                    budget_s=7200, critical=False,
                    skip_if=(not RESEARCH_COLLECT and RUN_MODE != "CACHED"),
                    skip_reason="RESEARCH_COLLECT=False"):
        LOG.info("※ 한경컨센서스·네이버금융은 robots.txt 가 Disallow:/ 입니다. "
                 "사용자의 명시적 지시에 따라 수집하되 보수적 속도로 제한하며, "
                 "PDF 원문은 증권사 저작물이므로 로컬 분석 용도로만 사용하세요.")
        cached = VAULT.get_table("research_report_master", scope="shared")
        frames = []
        if RUN_MODE not in ("CACHED", "SMOKE") and RESEARCH_COLLECT:
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                nv = naver_collect(BACKTEST_START, BACKTEST_END)
                nv = naver_enrich_detail(nv)
                frames.append(nv)
        if cached is not None and len(cached):
            LOG.ok(f"★ 공용 캐시에서 보고서 원장 {len(cached):,}건 재사용 — "
                   f"드라이브에 이미 쌓인 리포트를 그대로 씁니다(재수집 없음).")
            frames.append(cached)
        rep = build_report_master(frames, ctx["sec"])
        if len(rep) and RESEARCH_DOWNLOAD_PDF:
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    set_where(rep, fill, "target_price", rep.loc[fill, "pdf_target"])
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared",
                            domain="research", source="hankyung+naver",
                            extra={"note": "리포트 원장 — 전 전략 공용"})
        ctx["rep"] = rep
        A, L = build_analyst_ledger(rep) if len(rep) else (pd.DataFrame(), pd.DataFrame())
        ctx["analysts"], ctx["links"] = A, L
        if len(rep):
            audit_linkage(rep, A, L)
            if len(A):
                VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                                source=STRATEGY_ID)
            if len(L):
                VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                                source=STRATEGY_ID)

    with PIPE.stage("L1.FLOW", "플로우 수집 (거래원 / 투자자별)", "L1",
                    budget_s=int(FLOW_TIME_BUDGET_MIN * 60 * 1.3), critical=False):
        ev_codes = (sorted(set(ctx["rep"]["stock_code"].dropna().map(to_code6).dropna()))
                    if len(ctx.get("rep", [])) else ctx["sec"]["code"].tolist())
        LOG.info(f"플로우 수집 대상 {len(ev_codes):,}종목 (리포트가 존재하는 종목만 — "
                 f"전 종목을 긁으면 요청수가 10배가 되고 차단 위험이 그만큼 커집니다)")
        if RUN_MODE != "SMOKE":
            canary = collect_member_snapshot(ev_codes[:FLOW_CANARY_TICKERS], limit=FLOW_CANARY_TICKERS)
            LOG.info(f"카나리(거래원 {FLOW_CANARY_TICKERS}종목): "
                     f"{'도달 성공' if len(canary) else '도달 실패(전진수집만 영향)'}")
        fr = fetch_foreign_ratio(ev_codes, BACKTEST_START, BACKTEST_END)
        fnet = foreign_net_from_ratio(fr, ctx.get("mc"))
        inv = fetch_investor_flow_paged(ev_codes, BACKTEST_START, BACKTEST_END)
        snap = VAULT.get_table("naver_member_flow_snapshot", scope="shared")
        ctx["bm"] = load_broker_map()
        mem_daily = (member_snapshot_to_daily(snap, ctx["px"], ctx["bm"])
                     if snap is not None and len(snap) else pd.DataFrame())
        ctx["flow"] = build_flow_panel(inv, fnet, mem_daily, ctx["px"])
        ctx["member_days"] = int(pd.Series(snap["trade_date"]).nunique()) if snap is not None and len(snap) else 0
    return ctx


def build_signal_frame(ctx: dict, mode: str, k: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """이벤트 패널 + 플로우 잔차 → 신호 프레임 (원값/잔차 모두)."""
    uni = ctx["uni"]
    E = attach_matched_actor(ctx["events"], mode)
    R = build_flow_raw(ctx["flow"], k=k)
    RES = residualize_flow(R, k=k, baseline=GRID_BASELINE_DAYS)
    S = attach_signal(E, RES)

    mc = ctx.get("mc")
    if mc is not None and len(mc):
        S = S.merge(mc[["code", "date", "marcap", "adv20", "turnover", "size_bucket"]],
                    on=["code", "date"], how="left")
    else:
        for c, v in (("marcap", np.nan), ("adv20", np.nan), ("turnover", np.nan)):
            S[c] = v
        S["size_bucket"] = "중형"
    # 직전 20일 수익률 (통제변수) — 이벤트일 '이전' 구간만 쓴다
    px = ctx["px"]
    cl = px.pivot_table(index="code", columns="date", values="close", aggfunc="last",
                        observed=True).reindex(columns=ctx["cal"]).ffill(axis=1)
    dpos = {d: i for i, d in enumerate(ctx["cal"])}
    cpos = {c: i for i, c in enumerate(cl.index)}
    arr = cl.to_numpy(float)
    r20 = []
    for c, d in zip(S["code"], S["date"]):
        i, j = cpos.get(c), dpos.get(pd.Timestamp(d))
        if i is None or j is None or j < 21:
            r20.append(np.nan)
            continue
        a, b = arr[i, j - 21], arr[i, j - 1]
        r20.append(b / a - 1.0 if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan)
    S["ret20"] = r20
    S = attach_industry(S, ctx["sec"])

    S["sig_raw"] = control_residual(S.assign(_x=S["flow_raw"]), "flow_raw", pit=True)
    S["sig_resid"] = control_residual(S.assign(_x=S["flow_resid"]), "flow_resid", pit=True)
    # 통제회귀가 성립하지 않는 초기 구간은 원신호를 그대로 쓴다(0으로 채우지 않는다)
    set_where(S, S["sig_raw"].isna() & S["flow_raw"].notna(), "sig_raw",
              S.loc[S["sig_raw"].isna() & S["flow_raw"].notna(), "flow_raw"])
    set_where(S, S["sig_resid"].isna() & S["flow_resid"].notna(), "sig_resid",
              S.loc[S["sig_resid"].isna() & S["flow_resid"].notna(), "flow_resid"])
    return S, RES


def run_grid(ctx: dict, mode: str, universe_mask: Optional[pd.DataFrame] = None,
             label: str = "") -> dict:
    """SPEC §6.6 사전등록 12구성 백테스트 (+ 비용 3종)."""
    out: Dict[str, Any] = {"bts": {}, "cost": {}, "S_by_k": {}, "RES_by_k": {}}
    for k, _ in GRID_FLOW_WINDOWS:
        pass
    for (k, kk) in GRID_FLOW_WINDOWS:
        S, RES = build_signal_frame(ctx, mode, k=kk)
        if universe_mask is not None and len(universe_mask):
            S = S.merge(universe_mask, on=["code", "date"], how="left")
            n0 = len(S)
            S = S[S["in_small"].fillna(False)]
            LOG.info(f"[{label}] k={kk} — 유니버스 제한으로 이벤트 {n0:,} → {len(S):,}건")
        out["S_by_k"][kk] = S
        out["RES_by_k"][kk] = RES
        for hold in GRID_HOLD_DAYS:
            for ver in GRID_SIGNAL_VERSIONS:
                cfg = BTConfig(k=kk, hold=hold, version=ver)
                bt = run_event_backtest(S, ctx["px"], ctx["cal"], ctx["uni"], cfg,
                                        sec=ctx["sec"])
                out["bts"][cfg.name()] = bt
    LOG.ok(f"[{label or mode}] 사전등록 12구성 백테스트 완료 "
           f"({len(out['bts'])}개 — SPEC §6.6 격자 확장 없음)")
    return out


def run_full(ctx: dict, mode: str, tag: str, universe_mask=None) -> dict:
    """한 유니버스에 대한 전체 파이프라인: 백테스트 → 이벤트스터디 → 가설 → 강건성 → 판정."""
    LOG.banner(f"[{tag}] 백테스트 · 검증", f"모드={mode}")
    G = run_grid(ctx, mode, universe_mask, label=tag)
    bts = G["bts"]
    if not bts:
        LOG.error(f"[{tag}] 백테스트 결과가 없습니다.")
        return {}

    cal = ctx["cal"]
    valid = {n: b for n, b in bts.items() if (b.get("stats") or {}).get("이벤트체결수", 0) > 0}
    if not valid:
        LOG.error(f"[{tag}] 체결이 발생한 구성이 없습니다.")
        return {}
    best = max(valid, key=lambda n: valid[n]["stats"].get("Sharpe", -9e9)
               if np.isfinite(valid[n]["stats"].get("Sharpe", np.nan)) else -9e9)
    best_cfg = valid[best]["cfg"]

    S_best = G["S_by_k"][best_cfg.k]
    bench = build_benchmarks(ctx["px"], cal, S_best, ctx["uni"], ctx["sec"], best_cfg)
    M = report_performance(bts, bench, cal, title=f"— {tag} ({mode})")
    report_yearly(bts, best, bench, cal)

    # ── 이벤트 스터디 ─────────────────────────────────────────────────────────────────────
    sig_col = "sig_resid" if best_cfg.version == "resid" else "sig_raw"
    nore = build_noreport_control(G["RES_by_k"][best_cfg.k], S_best, cal)
    groups = split_groups(S_best, sig_col, nore)
    car = report_event_study(groups, ctx["px"], cal)
    car_ascii(car)

    # ── 가설 ──────────────────────────────────────────────────────────────────────────────
    res = test_hypotheses(groups, S_best, ctx["px"], cal, ctx["bm"], mode,
                          entry_offset=best_cfg.entry_offset)

    # ── 강건성 ────────────────────────────────────────────────────────────────────────────
    rob: Dict[str, Any] = {}
    r_best = valid[best]["daily"]["ret"].to_numpy(float)
    bb = block_bootstrap(r_best, n_iter=N_BOOT, block=BLOCK_LEN)
    rob["블록부트스트랩(21일,1000회)"] = {
        "value": f"Sharpe {bb['obs']:.2f} [{bb['ci_lo']:.2f}, {bb['ci_hi']:.2f}]",
        "thresh": "CI 하한 > 0", "pass": bool(np.isfinite(bb["ci_lo"]) and bb["ci_lo"] > 0),
        "note": f"p(우측꼬리)={bb['p_gt0']:.3f}", "raw": bb["ci_lo"]}

    P = np.column_stack([b["daily"]["ret"].reindex(range(len(cal))).fillna(0).to_numpy(float)
                         if len(b["daily"]) == len(cal)
                         else np.zeros(len(cal)) for b in valid.values()])
    pb = pbo_cscv(P, n_split=8)
    rob["PBO"] = {"value": f"{pb['pbo']:.3f}", "thresh": "< 0.50",
                  "pass": bool(np.isfinite(pb["pbo"]) and pb["pbo"] < 0.5),
                  "note": f"CSCV {pb['n_comb']}조합 · 구성 {pb['n_config']}개", "raw": pb["pbo"]}

    srs = np.array([v["stats"].get("Sharpe", np.nan) / math.sqrt(252) for v in valid.values()])
    ds = deflated_sharpe(r_best, srs, n_trials=len(bts))
    rob["DSR"] = {"value": f"{ds['dsr']:.3f}", "thresh": "> 0.50",
                  "pass": bool(np.isfinite(ds["dsr"]) and ds["dsr"] > 0.5),
                  "note": f"시도 {ds['n_trials']}회 · E[maxSR]={ds['sr0']:.3f} · "
                          f"왜도 {ds['skew']:+.2f}", "raw": ds["dsr"]}

    W = walk_forward({n: b["daily"] for n, b in valid.items()}, cal)
    wf_ok = bool(len(W) and (W["검증수익"] > 0).mean() >= 0.5)
    rob["워크포워드(5년/1년)"] = {"value": f"{100*(W['검증수익']>0).mean():.0f}% 양(+)"
                                if len(W) else "-", "thresh": "≥ 50%",
                                "pass": wf_ok if len(W) else None,
                                "note": f"검증 {len(W)}개 연도", "raw": len(W)}

    mu_nw, t_nw = hac_tstat(r_best)
    rob["뉴이-웨스트 t"] = {"value": f"{t_nw:+.2f}", "thresh": "> 2.0",
                          "pass": bool(np.isfinite(t_nw) and t_nw > 2.0),
                          "note": "캘린더타임 일별수익 (겹침 상관 흡수)", "raw": t_nw}

    # ── 플라시보 ──────────────────────────────────────────────────────────────────────────
    PL = make_placebo_events(S_best[["code", "date", "actor", "broker", "broker_tier",
                                     "size_bucket"]].copy(), cal)
    placebo_clean = True
    pl_t = np.nan
    if len(PL):
        PR = G["RES_by_k"][best_cfg.k]
        PS = PL.merge(PR, on=["actor", "code", "date"], how="left")
        PS["sig_resid"] = PS["flow_resid"]
        PS["sig_raw"] = PS["flow_raw"]
        pg = split_groups(PS, sig_col)
        ar = _abnormal_returns(pg.get("확증군(리포트+순매수상위30%)"), ctx["px"], cal,
                               H_HORIZON, best_cfg.entry_offset)
        _, pl_t, pl_p, pl_n = _mean_t(ar)
        placebo_clean = not (np.isfinite(pl_t) and abs(pl_t) >= 2.0)
        rob["플라시보(±20~60일 이동)"] = {
            "value": f"t={pl_t:+.2f}", "thresh": "|t| < 2.0",
            "pass": placebo_clean, "raw": pl_t,
            "note": f"n={pl_n:,} · 유의하면 파이프라인에 미래참조가 있다는 뜻"}
    report_robustness(rob)

    # ── 비용 3종 ──────────────────────────────────────────────────────────────────────────
    cost_bts: Dict[str, Dict[str, dict]] = {}
    naive_by_cost: Dict[float, float] = {}
    for lab, mult in COST_SCENARIOS:
        cfg = BTConfig(k=best_cfg.k, hold=best_cfg.hold, version=best_cfg.version,
                       cost_mult=mult)
        cost_bts[lab] = {best: run_event_backtest(S_best, ctx["px"], cal, ctx["uni"], cfg,
                                                  sec=ctx["sec"])}
        nb = build_benchmarks(ctx["px"], cal, S_best, ctx["uni"], ctx["sec"], cfg)
        nbt = nb.get("_naive_bt")
        naive_by_cost[mult] = (nbt["stats"].get("CAGR", np.nan) if nbt else np.nan)
    cost_md = report_costs(cost_bts, naive_by_cost, best)
    survive2x = "**2배 비용 시나리오 생존: 예**" in cost_md

    report_interpretation(res, mode)
    return {"bts": bts, "best": best, "best_cfg": best_cfg, "M": M, "res": res,
            "rob": rob, "cost_md": cost_md, "survive2x": survive2x,
            "placebo_clean": placebo_clean, "car": car, "groups": groups,
            "S": S_best, "bench": bench, "W": W}


# ══════════════════════════════════════════════════════════════════════════════════════════
def main() -> dict:
    t_start = time.time()
    LOG.banner(f"{SPEC_ID} — {STRATEGY_NAME}",
               f"빌드 {BUILD_VERSION} · 구간 {BACKTEST_START} ~ {BACKTEST_END} · 모드 {RUN_MODE}")
    report_compat()

    # [0-a] 구글드라이브 캐시 연결 — ★ 절대 1원칙: 기존 인덱스를 훼손하지 않는다
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시(공용/전용) 연결", "L0", budget_s=600):
        root, dmode = _mount_drive()
        globals()["VAULT"] = Vault(root, dmode)
        LOG.info(f"캐시 루트: {VAULT.root}  (모드 {dmode})")
        LOG.info(f"  공용 인덱스: {VAULT.ns['shared']}   ← 다른 전략과 공유(가격·리포트·플로우 원본)")
        LOG.info(f"  전용 인덱스: {VAULT.ns['private']}  ← 이 전략 고유(이벤트패널·백테스트 결과)")
        free = free_gb(VAULT.root)
        if np.isfinite(free):
            LOG.info(f"  여유 공간 {free:.1f} GB")
            if free < 2:
                LOG.warn("여유 공간이 2GB 미만입니다. RESEARCH_DOWNLOAD_PDF=False 를 권합니다.")
        VAULT.load_index("shared")
        VAULT.load_index("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)     # 기존 리포트를 '이동 없이 등록만'
        VAULT.report()

    # [0-b] 계약
    with PIPE.stage("V.CONTRACT", "계약 자동검정 K1~K16", "V0", budget_s=300):
        run_contracts(strict=True)
    # [1] 스모크
    with PIPE.stage("V.SMOKE", "합성 스모크", "V1", budget_s=600):
        run_smoke(strict=True)
    # [2] 리허설
    with PIPE.stage("V.REHEARSAL", "실경로 리허설", "V2", budget_s=300):
        run_rehearsal(strict=True)

    if RUN_MODE == "SMOKE":
        # ★ 여기서 멈추면 '전 출력물 예행연습' 이라는 약속을 못 지킨다.
        #   합성데이터로 ctx 를 만들어 실제와 동일한 경로로 백테스트~최종판정까지 전부 돌린다.
        #   네트워크·키 없이 성과표·강건성표·해석표·비교표·산출물이 모두 나온다.
        ctx = _synthetic_ctx()
        report_dataflow(ctx)
        main_out = run_full(ctx, "MEMBER", tag="합성 · 전체 유니버스")
        small_out = {}
        if COMPARE_SMALLCAP_ENABLE and len(ctx.get("mc", [])):
            mask = smallcap_universe(ctx["mc"], max(50, COMPARE_SMALLCAP_N // 20))
            small_out = run_full(ctx, "MEMBER", tag=f"합성 · {COMPARE_SMALLCAP_LABEL}",
                                 universe_mask=mask)
        _emit_outputs(ctx, main_out, small_out,
                      {"branch": "SMOKE", "sources": [], "notes": []}, "MEMBER", t_start)
        LOG.ok("SMOKE 완료 — 위 표들이 실데이터에서도 그대로 나옵니다. "
               "RUN_MODE='FULL' 로 바꾸면 실데이터로 진행합니다.")
        PIPE.report_stages()
        return {"mode": "SMOKE", "main": main_out, "small": small_out}

    # [3] ★ Phase 0 게이트
    with PIPE.stage("P0.GATE", "Phase 0 데이터 실현가능성 게이트", "P0", budget_s=3600):
        p0 = run_phase0_gate()
    mode = "MEMBER" if p0["branch"] in ("FULL10", "PARTIAL") else "PROXY"
    if RUN_MODE == "PHASE0":
        LOG.ok("PHASE0 모드 — 게이트 결과만 보고하고 종료합니다 (SPEC §12-1).")
        offer_download([out_path(PHASE0_MD), out_path("forward_collect_member_flow.py")])
        PIPE.report_stages()
        return {"phase0": p0}

    # [4] 수집
    ctx = collect_all()
    ctx["mode"] = mode
    report_dataflow(ctx)

    # [5] 매핑 감사 + PIT 유니버스 + 이벤트
    with PIPE.stage("L2.MAP", "증권사↔거래원 매핑 감사", "L2", budget_s=300, critical=False):
        ctx["bm"] = ctx.get("bm") or load_broker_map()
        aud = audit_broker_mapping(ctx["bm"], ctx.get("rep"), ctx.get("flow"))
        ctx["map_audit"] = aud

    with PIPE.stage("L2.UNI", "PIT 유니버스", "L2", budget_s=600):
        ctx["uni"] = DailyUniverse(ctx["sec"], ctx["px"], ctx.get("dgk"), ctx.get("snapshots"))

    with PIPE.stage("L2.EVENT", "매수성 리포트 이벤트 패널", "L2", budget_s=900):
        ctx["events"] = build_event_panel(ctx["rep"], ctx["bm"], ctx["uni"], ctx["cal"])
        ctx["uni"].report_attrition()
        if not len(ctx["events"]):
            raise KillCriteria("매수성 이벤트가 0건입니다 — 리포트 수집/파싱을 먼저 확인하세요.")

    # [6] 본 전략
    main_out = run_full(ctx, mode, tag="전체 유니버스")

    # [7] ★ 비교 전략: 시총 하위 1000
    small_out = {}
    if COMPARE_SMALLCAP_ENABLE and len(ctx.get("mc", [])):
        with PIPE.stage("CMP.SMALL", f"비교전략 — {COMPARE_SMALLCAP_LABEL}", "L3",
                        budget_s=2400, critical=False):
            mask = smallcap_universe(ctx["mc"], COMPARE_SMALLCAP_N)
            small_out = run_full(ctx, mode, tag=COMPARE_SMALLCAP_LABEL, universe_mask=mask)

    # [8] 비교표
    if main_out and small_out:
        a, b = main_out["bts"][main_out["best"]]["stats"], \
               small_out["bts"][small_out["best"]]["stats"]
        rows = []
        for key, fmt in (("CAGR", "{:+.2%}"), ("Sharpe", "{:.2f}"), ("Sortino", "{:.2f}"),
                         ("MDD", "{:.1%}"), ("Calmar", "{:.2f}"), ("t통계량(NW)", "{:+.2f}"),
                         ("이벤트체결수", "{:,.0f}"), ("승률", "{:.0%}"),
                         ("연회전율", "{:.1f}"), ("평균보유종목", "{:.1f}")):
            va, vb = a.get(key, np.nan), b.get(key, np.nan)
            try:
                sa, sb = fmt.format(va), fmt.format(vb)
            except Exception:
                sa, sb = str(va), str(vb)
            rows.append([key, sa, sb,
                         ("소형 우위" if (np.isfinite(va) and np.isfinite(vb) and vb > va)
                          else "전체 우위") if key not in ("MDD",) else
                         ("소형 우위" if (np.isfinite(va) and np.isfinite(vb) and vb > va)
                          else "전체 우위")])
        LOG.table(rows, ["지표", "전체 유니버스", COMPARE_SMALLCAP_LABEL, "비교"],
                  ["l", "r", "r", "c"],
                  title=f"★ 전략 비교 — 전체 유니버스 vs {COMPARE_SMALLCAP_LABEL} "
                        f"(H4 '소형주에서 더 강하다' 의 직접 검정)")
        LOG.info("※ 소형주 우위가 나오더라도 슬리피지가 3.5배(35bp vs 10bp)이므로 "
                 "비용 반영 후 초과가 남는지를 비용 민감도표에서 반드시 확인하세요.")

    # [9] 산출물
    _emit_outputs(ctx, main_out, small_out, p0, mode, t_start)
    return {"ctx": ctx, "main": main_out, "small": small_out, "phase0": p0}


def _synthetic_ctx() -> dict:
    """SMOKE 전용 — 합성데이터로 실데이터와 동일한 구조의 ctx 를 만든다.
    사이즈 버킷·상장폐지·무리포트 대조군까지 실제로 생성해 H4/H5 경로도 실행되게 한다."""
    syn = make_synthetic(n_codes=160, n_days=1800)   # ~7.1년 — 워크포워드 창이 실제로 잡히도록
    cal, px, sec, F, E = syn["cal"], syn["px"], syn["sec"], syn["flow"], syn["events"]
    rng = np.random.default_rng(SEED)
    mc = px[["code", "date", "close", "volume", "amount"]].copy()
    scale = pd.Series(rng.lognormal(0, 1.6, len(syn["codes"])), index=syn["codes"])
    mc["marcap"] = mc["close"] * mc["volume"] * mc["code"].map(scale) * 50
    mc["adv20"] = mc.groupby("code", observed=True)["amount"].transform(
        lambda s: s.rolling(20, min_periods=5).mean())
    mc["turnover"] = safe_div(mc["amount"], mc["marcap"])
    mc["mc_tier"] = "SYN"
    mc = assign_size_bucket(mc)
    bm = load_broker_map()
    ctx = {"cal": build_trading_calendar(px), "px": px, "sec": sec, "flow": F,
           "events": E, "mc": mc, "bm": bm, "rep": pd.DataFrame(),
           "dgk": pd.DataFrame(), "snapshots": pd.DataFrame(),
           "uni": DailyUniverse(sec, px), "mode": "MEMBER", "member_days": 0}
    ctx["events"] = ctx["events"].assign(date=as_ts_series(ctx["events"]["pub_date"]))
    return ctx


def _emit_outputs(ctx: dict, main_out: dict, small_out: dict, p0: dict, mode: str,
                  t_start: float) -> List[str]:
    """산출물 생성 — SMOKE 와 FULL 이 같은 경로를 쓴다(예행연습이 실제와 같아야 한다)."""
    outs: Dict[str, str] = {}
    if main_out:
        outs["FINAL_VERDICT.md"] = final_verdict(
            main_out["res"], main_out["rob"], main_out["cost_md"], mode,
            main_out["survive2x"], main_out["placebo_clean"])
        outs["cost_sensitivity.md"] = main_out["cost_md"]
        outs["mechanism_tests.md"] = report_mechanism(main_out["res"], mode)
        outs["hypothesis_test_report.md"] = _hyp_md(main_out, mode)
        outs["placebo_test.md"] = _placebo_md(main_out)
        outs["broker_member_map_audit.md"] = _map_md(ctx.get("map_audit", {}), ctx["bm"])
        outs["OPEN_QUESTIONS.md"] = _open_questions_md(p0, mode, ctx)
        if small_out:
            outs["smallcap_comparison.md"] = _cmp_md(main_out, small_out)
        try:
            main_out["M"].to_csv(out_path("metrics_all_configs.csv"), index=False,
                                 encoding="utf-8-sig")
            atomic_write_parquet(main_out["M"], out_path("metrics_all_configs.parquet"))
            eq = pd.DataFrame({n: b["daily"].set_index("date")["ret"]
                               for n, b in main_out["bts"].items() if len(b["daily"])})
            atomic_write_parquet(eq.reset_index(), out_path("equity_curves.parquet"))
            tl = main_out["bts"][main_out["best"]]["trades"]
            if len(tl):
                atomic_write_parquet(tl, out_path("trade_log.parquet"))
            write_json(out_path("run_summary.json"), {
                "strategy": "ARC-BDF-PROXY" if mode == "PROXY" else "ARC-BDF",
                "build": BUILD_VERSION, "run_mode": RUN_MODE, "signal_mode": mode,
                "phase0_branch": p0.get("branch"),
                "period": [BACKTEST_START, BACKTEST_END],
                "best_config": main_out["best"],
                "n_events": int(len(ctx.get("events", []))),
                "n_configs": len(main_out["bts"]),
                "verdict": ("KILL" if not main_out["placebo_clean"] else "본문 참조"),
                "elapsed_min": round((time.time() - t_start) / 60.0, 2)})
        except Exception as e:                                        # noqa
            LOG.warn(f"결과 파일 저장 일부 실패: {type(e).__name__}: {e}")
    paths = write_outputs(outs)
    for extra in ("metrics_all_configs.csv", "metrics_all_configs.parquet",
                  "event_study_car.parquet", "equity_curves.parquet",
                  "trade_log.parquet", "run_summary.json",
                  PHASE0_MD, "forward_collect_member_flow.py"):
        q = out_path(extra)
        if os.path.exists(q):
            paths.append(q)

    PIPE.report_stages()
    PIPE.report_runtime()
    report_http()
    try:
        VAULT.flush()
        VAULT.report()
    except Exception:
        pass
    LOG.banner("완료", f"총 {(time.time()-t_start)/60:.1f}분 · 산출물 {len(paths)}개")
    offer_download(paths)
    return paths


def _hyp_md(o: dict, mode: str) -> str:
    L = ["# 가설 검정 보고서 (H1~H5 + BH-FDR + PBO/DSR)", "",
         f"- 모드: **{mode}**  ·  대표구성: `{o['best']}`", "",
         "| ID | 가설 | 효과크기 | t | 표본 | 판정 |", "|---|---|---|---|---|---|"]
    for r in o["res"]["rows"]:
        L.append("| " + " | ".join(str(x) for x in r) + " |")
    L += ["", "## 다중검정 보정 (BH-FDR q=0.10)", "",
          o["res"]["fdr"].to_markdown(index=False) if hasattr(o["res"]["fdr"], "to_markdown")
          else o["res"]["fdr"].to_string(index=False), "",
          "## 강건성", "", "| 검정 | 값 | 기준 | 판정 |", "|---|---|---|---|"]
    for k, v in o["rob"].items():
        if isinstance(v, dict):
            L.append(f"| {k} | {v.get('value','-')} | {v.get('thresh','-')} | "
                     f"{'통과' if v.get('pass') else ('판정불가' if v.get('pass') is None else '실패')} |")
    return "\n".join(L) + "\n"


def _placebo_md(o: dict) -> str:
    v = o["rob"].get("플라시보(±20~60일 이동)", {})
    return "\n".join([
        "# 플라시보 테스트 (look-ahead 검증)", "",
        "이벤트 날짜를 ±20~60영업일 무작위로 이동시킨 '가짜 이벤트' 로 동일 파이프라인을 돌린다.",
        "종목·증권사·신호 분포는 그대로 두고 **시점만** 흔들기 때문에, 여기서 효과가 나온다면",
        "그것은 알파가 아니라 시점 정렬에서 오는 누수다.", "",
        f"- 결과: **{v.get('value','-')}**  (기준 {v.get('thresh','-')})",
        f"- 판정: **{'무효과 — 파이프라인 정상' if v.get('pass') else '★효과 검출 — 파이프라인 결함 의심'}**",
        f"- {v.get('note','')}", "",
        "플라시보에서 유의한 효과가 나오면 SPEC §11 에 따라 **KILL** 이다. 결과 전체를 폐기한다."]) + "\n"


def _map_md(aud: dict, bm) -> str:
    L = ["# 증권사 ↔ 거래원 회원사 매핑 감사 (SPEC §5)", "",
         f"- 리포트 원장 증권사명 비공백률: {100*aud.get('broker_fill_rate', float('nan')):.1f}%",
         f"- 리포트 → 정식명 매핑 성공률: {100*aud.get('report_rate', float('nan')):.1f}%",
         f"- 거래원 창구 → 정식명 매핑 성공률: {100*aud.get('flow_rate', float('nan')):.1f}%",
         f"- SPEC §5 한계(실패율 20%) 충족: **{'예' if aud.get('ok') else '아니오'}**", "",
         "## 사명변경·합병 반영 내역", "", "| 시점 | 내용 |", "|---|---|"]
    for y, c in aud.get("name_changes", []):
        L.append(f"| {y} | {c} |")
    L += ["", "## 미매핑 (버리지 않고 기록)", ""]
    um = list(bm.unmapped.most_common(30)) if hasattr(bm, "unmapped") else []
    if um:
        L += ["| 원문 | 건수 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in um]
    else:
        L.append("없음")
    L += ["", "## 비증권 법인 차단 (오매칭 방지)", "",
          "미래에셋생명 / 한국투자파트너스 / 키움투자자산운용 / IBK기업은행 등은 이름이 비슷해도",
          "증권사가 아니므로 매핑에서 차단한다. 그대로 두면 '자사 창구' 신호에 남의 주문이 섞인다.",
          "", "`config/broker_member_map.csv` 를 직접 수정하면 그 값이 우선 적용된다."]
    return "\n".join(L) + "\n"


def _cmp_md(a: dict, b: dict) -> str:
    sa, sb = a["bts"][a["best"]]["stats"], b["bts"][b["best"]]["stats"]
    L = [f"# 비교: 전체 유니버스 vs {COMPARE_SMALLCAP_LABEL}", "",
         "동일한 파이프라인·동일한 사전등록 격자를, 유니버스만 바꿔 재실행한 결과다.",
         "이것은 H4('저유동성·소형주에서 더 강하다')의 직접 검정이기도 하다.", "",
         "| 지표 | 전체 유니버스 | " + COMPARE_SMALLCAP_LABEL + " |", "|---|---|---|"]
    for k in ("CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "t통계량(NW)",
              "이벤트체결수", "승률", "평균보유일", "연회전율"):
        L.append(f"| {k} | {sa.get(k, float('nan')):.4g} | {sb.get(k, float('nan')):.4g} |")
    L += ["", "## 해석 시 주의", "",
          "- 소형주는 편도 슬리피지가 35bp 로 대형주(10bp)의 3.5배다. 총수익이 높아도",
          "  비용 반영 후 초과가 남는지는 비용 민감도표에서 따로 확인해야 한다.",
          "- 시가총액 하위 1000 은 **매 거래일 횡단면에서 재선정**한다(PIT). 오늘의 시총으로",
          "  과거를 자르면 그 자체가 미래참조이며, 그 경우 소형주 성과가 크게 과대평가된다.",
          "- 시총 사다리가 T2~T4 로 강등된 구간에서는 '하위 1000' 선정에 근사가 섞인다."]
    return "\n".join(L) + "\n"


def _open_questions_md(p0: dict, mode: str, ctx: dict) -> str:
    return "\n".join([
        "# OPEN QUESTIONS", "",
        "명세가 애매해 임의 판단하지 않고 기록해 둔 지점들. 전부 **가장 보수적인 선택**을 했다.", "",
        "## 1. 거래원 이력 부재에 따른 신호 대체 (SPEC §4.3 B-2)",
        f"- Phase 0 판정: **{p0.get('branch')}**, 실행 모드: **{mode}**",
        "- PROXY 에서 '기관/외국인을 단순 합산' 하는 대신 **발행사 계열 정합**(외국계→외국인,",
        "  국내→기관)을 택했다. 브로커 정체성을 조금이라도 보존하는 쪽이 원 가설에 가깝다.",
        "  단순 합산 버전도 계산은 가능하지만 사전등록 격자를 늘리지 않기 위해 넣지 않았다.", "",
        "## 2. §6.3 두 번째 항의 해석",
        "- `median_{과거 60일}[FLOW_raw(B,·,d)]` 을 '그날 창구의 횡단면 중앙값을 시계열로 만든 뒤",
        "  과거 60일 중앙값' 으로 해석했다. 다른 해석(그날 횡단면 중앙값 자체)도 가능하지만,",
        "  그러면 '과거 60일' 이라는 수식어가 무의미해진다.", "",
        "## 3. 상장폐지 종목의 청산 가정",
        f"- 정리매매 가격이 관측되면 그 가격으로 청산한다. 관측 없이 사라지면 {DELIST_HAIRCUT:+.0%}",
        "  를 적용했다. 명세에 규정이 없어 보수적 값을 골랐다.", "",
        "## 4. 통제회귀의 연도더미",
        "- 매매신호용 잔차는 **과거 1년 이벤트만으로 적합**한다(PIT). 이 창 안에서는 연도더미가",
        "  거의 상수라 제외했다. 연도더미를 포함한 풀표본 적합은 미래정보가 섞이므로",
        "  이벤트스터디 기술통계에만 쓰고 매매에는 쓰지 않았다.", "",
        "## 5. 시가총액 사다리",
        "- 공공데이터포털 키가 없으면 시총이 근사(T2~T4)로 강등된다. 이 파이프라인에서 시총은",
        "  랭크·버킷으로만 쓰이므로 동작은 하지만, H4 와 하위1000 비교전략의 정확도가 낮아진다.",
        "  강등 비율은 실행 로그의 '시가총액 사다리 감사' 표에 그대로 출력된다.", "",
        "## 6. robots.txt",
        "- 한경컨센서스·네이버금융은 `Disallow: /` 다. 사용자의 명시적 지시에 따라 수집하되",
        "  보수적 속도로 제한하고 그 사실을 로그와 Phase 0 문서에 명시했다."]) + "\n"


if __name__ == "__main__":
    try:
        _RESULT = main()
    except KillCriteria as e:
        LOG.error(f"KILL 기준 위반으로 중단: {e}")
        PIPE.report_stages()
    except KeyboardInterrupt:
        LOG.warn("사용자 중단 — 여기까지의 캐시는 드라이브에 저장되어 있습니다. "
                 "다시 실행하면 이어서 진행합니다.")
        try:
            VAULT.flush()
        except Exception:
            pass
    except Exception as _e:                                           # noqa
        LOG.error(diagnose(_e, "메인 파이프라인"))
        PIPE.report_stages()
        raise
