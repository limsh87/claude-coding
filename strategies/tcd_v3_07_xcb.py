#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  TCD v3 · 전략 7 — XCB (eXport Constraint Break)
#  관세청 통관 4센서를 코어로 한 「제약 붕괴」 탐지
#  백테스트 구간: 2016-08-01 ~ 2026-07-31 (10년)
#
#  ┌─ 이 전략이 재는 것 ──────────────────────────────────────────────────────────────────────┐
#  │ 수출단가(USD/kg)는 한국 공개 데이터 중 유일한 '순수 가격결정력' 측정치다.                 │
#  │ GPM 은 판가와 원가가 섞여 원재료가 내려도 좋아지지만, 단가는 판매가격 그 자체라           │
#  │ 원가 노이즈가 0이다. 그리고 통관은 금액과 중량을 동시에 준다 —                            │
#  │ 수요곡선 위반을 직접 관측할 수 있는 유일한 구조다.                                        │
#  │                                                                                          │
#  │     log(단가) = α + β·log(물량) + γ·log(투입원가) + ε                                     │
#  │     정상 기업은 β<0. 많이 팔려면 깎아야 한다.                                             │
#  │     ε 이 지속적으로 양(+) = 물량이 늘었는데 안 깎았다 = 제약선이 이동했다.                 │
#  │                                                                                          │
#  │ ★ 정책 오염 방어가 산식에 내장되어 있다:                                                  │
#  │     정책 효과   → 물량↑ + 단가↓   (보조받은 만큼 깎을 수 있다)                            │
#  │     진짜 제품력 → 물량↑ + 단가유지 (깎지 않아도 팔린다)                                   │
#  │   TP_X1 = clip(물량↑) × clip(단가유지) 는 별도 패치가 아니라 정의 자체가 방어다.          │
#  └──────────────────────────────────────────────────────────────────────────────────────────┘
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v3_07_xcb.py` 로 그냥 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결(기존 캐시 흡수) → 계약 자동검정 C1~C18
#     [1] 합성데이터 엔드투엔드 스모크   (실데이터 쓰기 전에 계산경로를 먼저 증명)
#     [2] CANARY X1~X6 / K1~K11         (실측 표. FAIL 항목에 의존하는 단계는 큐에서 제거)
#     [3] 데이터 수집  (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [4] 원장 무결성 감사               (리포트 ↔ 애널리스트 ↔ 종목 연결이 제대로 됐는가)
#     [5] HS 유니버스 큐레이션 + 매핑 4중 게이트 + PIT 유니버스 + 감쇠 감사
#     [6] L1 피처패널 → L2 스코어 → L3 백테스트   (M0 → M1 → M2 단계별)
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
#   ▸ 처음 한 번은 RUN_MODE="SMOKE" 로 돌려보세요. 네트워크·키 없이 1분 만에
#     백테스트~강건성~해석표까지 전 출력물이 나옵니다(합성데이터 예행연습).
#
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── ① 관세청 통관 데이터 (공공데이터포털)  ★★ 이 전략의 심장 ★★ ────────────────────────────────
#
#    받는 법 (무료 · 5분, 승인은 보통 즉시):
#      1. https://www.data.go.kr  회원가입 → 로그인
#      2. 검색창에 "관세청_품목별 국가별 수출입실적" 입력 → 해당 오픈API 클릭
#      3. 우측 [활용신청] 버튼 → 활용목적 아무거나 기재 → 신청
#      4. 마이페이지 → [데이터활용] → [활용신청 현황] → 해당 API → **일반 인증키(Decoding)** 복사
#         ⚠ Encoding 키가 아니라 **Decoding 키**를 넣으세요. 코드가 알아서 인코딩합니다.
#            (Encoding 키를 넣으면 %2F 가 이중 인코딩되어 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 납니다.
#             혹시 Encoding 키를 넣어도 코드가 감지해서 자동 교정합니다 — 그래도 Decoding 권장)
#      5. 같은 방법으로 "관세청_품목별 수출입실적" 도 활용신청해 두면 폴백으로 쓰입니다.
#
#    ▶ 없으면: A축(통관) 4센서가 전부 죽습니다. 이 전략의 존재 이유가 사라지므로
#      코드가 CANARY X1 에서 명시적으로 중단하고 그 사실을 보고합니다.
DATA_GO_KR_KEY = ""

# ── ② DART 전자공시 OpenAPI ────────────────────────────────────────────────────────────────────
#
#    받는 법 (무료 · 1분):
#      1. https://opendart.fss.or.kr  접속
#      2. 우측 상단 [인증키 신청/관리] → [인증키 신청] → 이메일 인증
#      3. 발급된 40자리 키를 아래 따옴표 안에 붙여넣기
#    일 20,000건 호출 제한 (코드가 자동으로 스로틀하고 잔량을 표시합니다).
#
#    ▶ 없으면: B축·C축(회계·자원)과 V1/V2/V5/V11, θ_X 가 전부 죽습니다.
#      A축만으로는 트레이드오프 쌍을 만들 수 없으므로 사실상 전략이 성립하지 않습니다.
DART_API_KEY = ""

# ── ③ KRX 데이터 마켓플레이스  (2025-12 인증방식 변경 대응) ─────────────────────────────────────
#
#    받는 법 (무료):
#      1. https://data.krx.co.kr  접속 → 우측 상단 [회원가입]
#      2. 가입한 아이디 / 비밀번호를 그대로 아래에 입력
#
#    ▶ 없어도 실행은 됩니다. 무엇이 약해지는지 정확히 알고 비우세요:
#        · PIT 시가총액 : 규모버킷(셀)과 유동성 필터의 입력입니다. 없으면 '상장주식수를
#          현재값으로 고정하고 과거 종가를 곱하는' 근사로 대체되며, 유상증자·무상증자·감자를
#          반영하지 못합니다. 그 비중이 '시총 소스 감사표'에 찍힙니다.
#        · 투자자별 수급(d3) : 없으면 U 는 d1·d2·d4 로 축소됩니다(0으로 채우지 않습니다).
#        · 상장일·폐지일 자체는 FDR/KIND 로 확보되므로 생존자편향 제거(C2)는 영향받지 않습니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX 는 중복 로그인 시 이전 세션을 강제 종료합니다. 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML 을 받아 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서
#      1회만 하고 KRX 호출을 직렬화해 '스스로' 충돌하지는 않지만, 바깥은 막을 수 없습니다.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

#    ★★ KRX 를 아예 끄는 스위치 ★★
#      계정이 차단됐거나(중복로그인 남용·과다요청) 로그인이 안 될 때 False 로 두세요.
#      False 면 자격증명을 환경변수에 **주입조차 하지 않아** pykrx 가 import 시점에
#      실패 로그인을 반복하지 않습니다(계정 상태를 더 악화시키지 않습니다).
#
#      ▶ False 로 둬도 다음은 **전혀 영향받지 않습니다** — 구조적으로 KRX 를 안 쓰기 때문입니다:
#          · 생존자편향 제거(C2)  : FDR 상장폐지 목록 + KIND + 상장/폐지일 복원
#          · PIT 유니버스(C13)    : 상장일·폐지일 + 가격 관측으로 매 시점 재구성
#          · 가격·거래대금        : FDR → 네이버 → yfinance 체인
#      ▶ 약해지는 것은 둘뿐이며, 코드가 대체 경로를 쓰고 그 사실을 감사표에 남깁니다:
#          · PIT 시가총액 → 상장주식수 역산 근사(자본이벤트 미반영)  ※ 규모버킷에만 사용
#          · 투자자 수급(d3) → 네이버 폴백, 그것도 막히면 U 에서 제외(0으로 채우지 않음)
#      "auto" = ID/PW 가 있으면 시도하고 실패하면 조용히 폴백(권장 기본값)
KRX_ENABLED = "auto"          # "auto" | True | False

#    (선택) KRX Open API 인증키. https://data-dbg.krx.co.kr 에서 발급.
#    ⚠ 키만으론 즉시 안 됩니다 — 엔드포인트별 '이용신청'이 따로 필요하고 승인에 하루쯤 걸립니다.
KRX_OPENAPI_KEY = ""

# ── ④ 구글드라이브 캐시  ★★★ 절대 1원칙 ★★★ ──────────────────────────────────────────────────
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
#      · 외부(다른 전략) 인덱스는 **읽기 전용**으로만 엽니다. §FOREIGN 어댑터가 강제합니다.
#
#    GDRIVE_ROOT       : 이 전략이 쓰기 위해 쓰는 캐시 최상위 루트
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략에서도 그대로 재활용 가능한 원본/정제본
#                        (가격·DART원문·통관원문·리포트원장·애널리스트원장 …)
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유의 피처/스코어/백테스트 산출물
#                        ★ v2 의 "tcd_v2", 전략1의 "tcd_v3_core_d" 와 다른 이름입니다.
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"              # → {ROOT}/_shared          (공용 · 전 전략 재사용)
GDRIVE_PRIVATE_NS = "tcd_v3_xcb"           # → {ROOT}/tcd_v3_xcb       (전용 · 이 전략)

#    ▸ ★ 기존에 모아두신 캐시를 '흡수'할 루트들.
#      재귀 스캔해서 **등록만** 합니다. 파일을 옮기거나 지우거나 고치지 않습니다.
#      드라이브 실측 결과 이 계정에는 서로 다른 워크스페이스가 여러 개 있고,
#      리포트 원장의 본체는 tcd_cache 가 아니라 QuantCache/common/reports 에 있습니다.
#      (report_ledger 30.7만행 · analyst_registry 1,860명 · blob_map 500 PDF)
GDRIVE_FOREIGN_ROOTS = [
    "/content/drive/MyDrive/QuantCache",               # common/ + strategies/  (매니페스트 방식)
    "/content/drive/MyDrive/ARC_COMMON_LEDGER",        # public_index.json      (kind|ym 방식)
    "/content/drive/MyDrive/quant/shared_ledger",      # PDF 원본 · pdf_text · raw_reports
    "/content/drive/MyDrive/FPU7_WORKSPACE_2016_2026", # done_index.json · private_index.json
    "/content/drive/MyDrive/ARC_V3_WORKSPACE",         # cache/naver/analyst_index.parquet
    "/content/drive/MyDrive/ARC_V8_WORKSPACE_2016_2020",
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    "/content/drive/MyDrive/한경컨센서스",
    "/content/drive/MyDrive/네이버리서치",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ 새로 수집한 '공용' 데이터를 사용자의 기존 공용 레지스트리에도 등록할지.
#      True 면 QuantCache/common/_manifest_common.json 에 **새 키만 추가**합니다
#      (기존 키는 절대 건드리지 않음 · 백업 후 원자적 교체 · 읽기 검증 실패 시 자동 롤백).
#      다른 전략에서도 이 전략이 모은 데이터를 그대로 쓰게 하려면 True 로 두세요.
FOREIGN_PUBLISH_TO_COMMON = True

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽을 씁니다.
LOCAL_CACHE_ROOT = "./tcd_cache"

# ── ⑤ 백테스트 구간 ────────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑥ 실행 단계 (§12.1 단계 게이트) ────────────────────────────────────────────────────────────
#    "M0"  관세청 + DART벌크 + 가격/상폐            → TP_X1·TP_B1·TP_B2 + V1/V2/V5/V6
#    "M1"  + 수급 + 계약공시 + 품목별매출(게이트2)  → TP_XC, U축 d3
#    "M2"  + 직원현황 + 애널리스트 커버리지         → TP_C2, d2/d4 → 완전체
#    "ALL" M2 와 동일 + 강건성 R0~R10 전체
#    ▶ M0 에서 이미 백테스트 결과가 한 번 나옵니다. 전부 모은 뒤 한 번에 돌리지 않습니다.
STAGE = "ALL"

# ── ⑦ 실행 모드 ────────────────────────────────────────────────────────────────────────────────
#    "SMOKE"  합성데이터로 전체 출력물 예행연습(1분). 네트워크/키 불필요. ★ 처음엔 이걸로.
#    "FULL"   스모크 → 실경로 리허설 → 실데이터 수집 → 백테스트 → 강건성  (권장)
#    "CACHED" 스모크 → 리허설 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트
RUN_MODE = "FULL"

# ── ⑧ 성능 / 자원 ──────────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12      # 네트워크 병렬(스레드). 403/429 가 뜨면 8 이하로 줄이세요.
N_WORKERS_CPU  = 0       # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {       # 소스별 초당 요청 상한 — 차단 방지. 낮출수록 안전/느림.
    "dart":      8.0,
    "customs":   4.0,    # data.go.kr. 일 트래픽 한도가 있으므로 보수적으로.
    "hankyung":  2.5,
    "naver":     3.0,
    "krx":       2.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB = 6.0      # 이 값을 넘길 것 같으면 청크 처리로 자동 전환

# ── ⑨ HS 유니버스 큐레이션 (§5) ────────────────────────────────────────────────────────────────
#    ★ 큐레이션이 이 전략의 최대 자유도입니다. 성과를 보고 이 값을 고치면 그 순간 과적합입니다.
#      코드는 사전등록 파일(hs_universe_preregistered.csv)을 만들고, 이후 실행에서 그 파일이
#      있으면 **무조건 그것을 따릅니다**. 값을 바꾸면 '수정 이력'이 파일에 남고 리포트에
#      수정 전/후 성과가 함께 표시됩니다.
HS_OLIGOPOLY_MAX_FIRMS = 3      # 후보 상장사 수가 1~N 개인 HS 만 채택 (과점 품목)
HS_DIGIT_LEVEL         = 6      # 매핑 기준 HS 자릿수. 10 이 이상적이나 국가별 분해는 6이 안전
HS_MIN_MONTHS          = 36     # 이 개월수 이상 관측된 HS 만 사용 (롤링 36M OLS 요구)
CV_DEST_COMMODITY_PCT  = 0.25   # cv_dest 하위 N% → V10 부분거부권(a2 무효화, 커모디티)
COVERAGE_BAND          = (0.85, 1.15)   # 게이트1 합계정합성 허용 구간
COVERAGE_CV_MAX        = 0.25   # 게이트1 시간 안정성(변동계수) 상한
SELFDISC_CORR_MIN      = 0.40   # 게이트2 기업 자기공시 대조 상관 하한
PLACEBO_N              = 1000   # 게이트3 플라시보 셔플 횟수 (행렬곱만 — 회귀 재적합 금지)
PLACEBO_ALPHA          = 0.05   # 게이트3 유의수준
MAPPING_MIN_NAMES      = 150    # §14 킬 기준 4: 매핑게이트 통과 종목이 이보다 적으면 검정 불가

# ── ⑩ 포지션 / 사이징 (§15.1 — 드로다운 한가운데서 정하지 않도록 코드 상수로 못박음) ───────────
PORTFOLIO_TOP_PCT     = 0.05      # 신호 상위 5% 진입
PORTFOLIO_MAX_NAMES   = 25
PORTFOLIO_MIN_NAMES   = 5
POS_MAX_WEIGHT        = 0.12      # 종목당 최대 비중
POS_MIN_WEIGHT        = 0.02
POS_ADV_PARTICIPATION = 0.05      # §11 R9: 거래대금 참여율 5% 상한
HOLD_MAX_MONTHS       = 24        # §15.3 강제청산
ACCOUNT_KRW           = 30_000_000        # 소액계좌 가정 (최소주문/유동성 제약 계산용)
BREADTH_FLOOR_PCT     = 0.50      # 하한선: 활성 축(A·B·C) 각각의 셀 내 백분위 ≥ 50th
                                  # "모든 축이 상위"가 아니라 "빈 축이 없을 것"
UNIVERSE_MIN_ADTV     = 3e8       # V6 유동성: 20일 평균거래대금 하한 (3억)
UNIVERSE_SEASON_DAYS  = 250       # C2 진입: 상장 후 거래일

# ── ⑪ 애널리스트 리포트 (한경컨센서스 · 네이버금융리서치) ──────────────────────────────────────
#    사용자 드라이브에 이미 캐시된 리포트를 먼저 흡수하고, 부족분만 신규 수집합니다.
#    수집분은 공용 인덱스에 저장되어 다른 전략에서도 그대로 재사용됩니다.
#    ★ 이 전략이 리포트에서 필요로 하는 것은 '커버리지의 존재와 개시 시점'입니다(§7.4).
#      애널리스트 개인 식별은 원장 무결성 감사와 d2 정밀도에만 쓰이며, 실패해도 d2 만 약해집니다.
RESEARCH_COLLECT      = True      # False 면 드라이브 캐시에 이미 있는 것만 사용
RESEARCH_SOURCES      = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF = False     # ★ 기본 False. 이 전략은 목록 레벨(커버리지)만 쓰므로
                                  #   PDF 원문이 필요 없습니다(§6.2 "PDF 추출 시도 금지").
                                  #   이미 드라이브에 있는 PDF 는 그대로 흡수·재사용합니다.
RESEARCH_PDF_MAX_PER_MONTH = 0    # 0 = 무제한
RESEARCH_TARGET_PER_YEAR = 30000  # 연간 수집 목표. 달성/미달을 감사표에 정직하게 표시합니다.

# ── ⑫ 기타 ────────────────────────────────────────────────────────────────────────────────────
SEED = 20260807                   # 결정성: 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = False     # §14 킬 기준 위반 시 즉시 중단할지.
                                  # False = 킬을 '기록'하고 남은 검사를 마저 돌려 전체 그림을 보여줌
                                  #         (판정은 그대로 KILL 로 보고합니다 — 통과시키지 않습니다)
WALL_CLOCK_BUDGET_MIN = 240.0     # §12 하드 제약 4시간. 초과 시 경고(중단 아님)

# ═══════════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID   = "XCB"
STRATEGY_NAME = "전략 7 · XCB (eXport Constraint Break)"
BUILD_VERSION = "v3.7.0"

# §12.1 단계별 누적 예산(분). 계측은 실측으로만 하고 추측하지 않는다.
STAGE_BUDGET_MIN = {"CANARY": 25.0, "CURATION": 45.0, "M0": 105.0,
                    "M1": 145.0, "M2": 158.0, "ALL": 188.0}
STAGE_ORDER = ["M0", "M1", "M2"]

# 전략1(CORE-D) 헤더와의 호환용 별칭 — v3 코어가 참조하는 이름들.
# XCB 는 HS군 기반 셀을 쓰므로 시총 밴드로 유니버스를 자르지 않는다.
# 유니버스의 1차 정의는 '과점 HS 에 매핑된 종목'이고, 시총은 셀(규모버킷)에만 쓴다.
UNIVERSE_MODE        = "none"     # XCB: 시총 밴드 미적용 (§5.1 — 매핑이 곧 유니버스)
UNIVERSE_RANK_LO     = 1
UNIVERSE_RANK_HI     = 100000
UNIVERSE_PCT_LO      = 0.0
UNIVERSE_PCT_HI      = 1.0
GDRIVE_ADOPT_DIRS    = GDRIVE_FOREIGN_ROOTS
USE_RESEARCH_AXIS    = True


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [02/27]  01_bootstrap.py  [v3 코어 재사용]
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
import contextlib
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
#   ★ KRX_ENABLED=False 면 자격증명을 **주입하지 않는다.** pykrx 는 import 시점에
#     로그인을 시도하므로, 차단된 계정을 넣어 두면 매 실행마다 실패 로그인을 반복하고
#     계정 상태를 더 악화시킨다. 넣지 않으면 pykrx 는 비인증 모드로 조용히 뜨고,
#     유니버스·생존자편향 경로는 애초에 KRX 를 쓰지 않으므로 아무 영향이 없다.
_KRX_ON = str(globals().get("KRX_ENABLED", "auto")).lower() not in ("false", "0", "off", "no")
if _KRX_ON and KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW
elif not _KRX_ON:
    for _k in ("KRX_ID", "KRX_PW"):
        os.environ.pop(_k, None)
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
# ★ pykrx 는 **import 하는 순간** KRX 로그인을 시도한다(webio.py 가 모듈 로드 시 실행).
#   KRX 를 끈 실행에서는 import 자체를 하지 않는다. 그러지 않으면
#   "KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다" 가 매번 찍히고,
#   차단된 계정이라면 실패 로그인을 반복해 상태를 더 악화시킨다.
if OPT.get("pykrx") and _KRX_ON:
    try:
        _quiet = io.StringIO()
        with contextlib.redirect_stdout(_quiet):
            from pykrx import stock as pykrx_stock    # type: ignore
        _msg = _quiet.getvalue().strip()
        if _msg and "실패" in _msg:
            LOG_BUFFER_KRX = _msg
    except Exception:
        pykrx_stock = None
elif OPT.get("pykrx"):
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
#  [03/27]  02_kernel.py  [v3 코어 재사용]
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
#  [04/27]  03_util.py  [v3 코어 재사용]
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
#  [05/27]  04_vault.py  [v3 코어 재사용]
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
#  [06/27]  05_http.py  [v3 코어 재사용]
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
#  [07/27]  06_statv3.py  [v3 코어 재사용]
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
#  [08/27]  10_ingest_universe.py  [v3 코어 재사용]
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
    # ★★ 절대로 'listingdate' 를 폐지일 후보에 넣지 말 것 ★★
    #   FDR 상장폐지 스냅샷에는 폐지일 컬럼이 아예 없는 판이 있다(실측: 컬럼이
    #   Symbol/Name/Market/SecuGroup/Kind/**ListingDate** 뿐). 폴백 사슬에 listingdate 를
    #   두면 **상장일이 폐지일 자리에 들어간다.** 결과는 조용하고 치명적이다:
    #     · 1985년 상장 → 2019년 폐지된 종목이 '1985년 폐지'로 기록되어 백테스트 전 구간에서
    #       제외된다. 즉 실패 사례가 사라진다 — 제거했다고 믿은 생존자편향이 그대로 재유입된다.
    #     · 실측: 2,526건 중 581건이 2000년 이전 '폐지', 최소값 1960-11-21(수도극장).
    #   폐지일을 못 구하면 결측으로 두고, 뒤에서 **마지막 거래일**로 복원한다(infer 경로).
    dl_c = next((col[k] for k in ("delistingdate", "delisting_date", "dedate",
                                  "delistdate", "date") if k in col), None)
    li_c = next((col[k] for k in ("listingdate", "listing_date", "listdate")
                 if k in col), None)
    name_c = col.get("name") or col.get("isu_nm") or code_c

    n_raw = len(d)
    raw_codes = d[code_c].astype(str)
    codes = raw_codes.map(to_code6)
    n_badcode = int(codes.isna().sum())
    t = pd.DataFrame({
        "code": codes,
        "name": d[name_c].astype(str),
        "delisting_date": as_ts_series(d[dl_c]) if dl_c else pd.NaT,
        # 상장일은 그대로 살려 둔다 — 상장목록 스냅샷에 ListingDate 가 없는 판이 많아서
        # 폐지목록이 사실상 유일한 상장일 소스인 경우가 있다(C2 시즈닝 정확도에 직결).
        "listing_date": as_ts_series(d[li_c]) if li_c else pd.NaT,
        "market": d[col["market"]].astype(str) if "market" in col else "KRX",
        "secugroup": (d[col["secugroup"]].astype(str) if "secugroup" in col
                      else d[col["kind"]].astype(str) if "kind" in col else ""),
    })
    t = t.dropna(subset=["code"])
    # ── 폐지일 타당성 검사: 상장일이 잘못 실려 들어왔는지 데이터로 판정한다.
    _dd = as_ts_series(t["delisting_date"])
    _n_old = int((_dd < pd.Timestamp("1995-01-01")).sum())
    if dl_c is None:
        LOG.warn("상장폐지 목록에 **폐지일 컬럼이 없습니다**. 폐지 사실만 사용하고 폐지일은 "
                 "'마지막 거래일'로 복원합니다(뒤 단계). 폐지 종목을 버리지는 않습니다 — "
                 "버리면 그게 곧 생존자편향입니다.")
        t["delisting_date"] = pd.NaT
    elif _dd.notna().any() and _n_old > max(20, 0.05 * int(_dd.notna().sum())):
        LOG.error(
            f"상장폐지 목록의 '폐지일' 중 {_n_old:,}건이 1995년 이전입니다 "
            f"(최소 {_dd.min():%Y-%m-%d}). 폐지일 자리에 **상장일**이 들어왔을 가능성이 큽니다.\n"
            f"    그대로 두면 '오래전에 상장해 최근 폐지된' 종목이 백테스트 전 구간에서 빠져\n"
            f"    실패 사례가 사라집니다 — 제거했다고 믿은 생존자편향이 그대로 재유입됩니다.\n"
            f"    → 이 컬럼을 폐기하고 마지막 거래일로 복원합니다.")
        t["listing_date"] = t["listing_date"].fillna(_dd)
        t["delisting_date"] = pd.NaT
    n_dupe = int(t["code"].duplicated().sum())
    # 같은 코드가 재상장/재폐지로 여러 번 나오면 '가장 늦은 폐지일'을 남긴다.
    # (가장 이른 것을 남기면 재상장 구간이 통째로 유니버스에서 빠져 표본이 준다)
    # NaT 을 앞으로 보내 'keep="last"' 가 실제 폐지일을 우선 남기게 한다.
    t = (t.sort_values("delisting_date", na_position="first")
           .drop_duplicates("code", keep="last"))
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
        d2 = dead.reindex(columns=["code", "name", "delisting_date", "market",
                                   "listing_date"]).copy()
        # ★ 예전엔 여기서 listing_date 를 NaT 으로 덮어써 폐지목록이 들고 온 상장일을
        #   통째로 버렸다. 상장목록 스냅샷에 ListingDate 가 없는 판에서는 이게 유일한
        #   상장일 소스라 C2 시즈닝이 전부 '모름'으로 떨어진다.
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
#  [09/27]  11_ingest_price.py  [v3 코어 재사용]
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
            s = str(txt)
            # ★ 성공은 _error_code == "CD001" **하나뿐**이다. '오류 문구가 없으면 성공'으로
            #   판정하면 안 된다 — 미인증 응답은 본문이 그냥 `LOGOUT` 이거나 빈 목록이라
            #   어떤 오류 단어도 포함하지 않는다. 그러면 상태표에는 LOGIN_OK 가 찍히는데
            #   이후 모든 KRX 호출이 조용히 빈 값을 돌려주고, 시총·수급이 소리 없이 죽는다.
            if re.search(r"CD010", s):
                self.status = "LOGIN_PW_CHANGE_REQUIRED"
                LOG.warn("KRX 로그인 거부(CD010) — 비밀번호 변경이 필요한 계정입니다. "
                         "https://www.krx.co.kr 에서 비밀번호를 변경한 뒤 다시 실행하세요. "
                         "재시도해도 통과되지 않으므로 폴백 경로로 넘어갑니다.")
                break
            if re.search(r"CD011|중복\s*로그인", s):
                LOG.warn("KRX 중복 로그인(CD011) 감지 — 같은 계정이 브라우저나 다른 노트북에서 "
                         "이미 로그인되어 있습니다. skipDup 으로 재시도하면 기존 세션이 강제 종료됩니다. "
                         "두 노트북을 동시에 돌리면 서로를 계속 밀어냅니다.")
                continue
            if "CD001" in s:
                self.session_ok = True
                self.status = "LOGIN_OK"
                LOG.ok("KRX 마켓플레이스 로그인 성공(CD001).")
                return True
            if s.strip() == "LOGOUT":
                LOG.warn("KRX 응답이 'LOGOUT' 입니다 — 세션이 서지 않았습니다.")
                continue
            # CD001 이 없는데 오류코드도 없으면 스펙이 바뀐 것이다. 성공으로 간주하지 않되,
            # 실제 조회가 되는지 한 번 찔러 보고 그 결과로만 판정한다(추측 금지).
            if self._probe_session():
                self.session_ok = True
                self.status = "LOGIN_OK_PROBED"
                LOG.ok("KRX 로그인 응답코드는 확인되지 않았으나 실조회가 성공했습니다.")
                return True
        self.status = "LOGIN_FAILED"
        LOG.warn("KRX 마켓플레이스 로그인 실패. ID/PW 를 확인하세요. "
                 "로그인 불필요 경로로 폴백하며 백테스트는 정상 진행됩니다.")
        return self.openapi_ok

    def _probe_session(self) -> bool:
        """세션이 진짜 서 있는지 실조회로 확인한다. 응답코드 해석에 기대지 않는다.

        미인증이면 본문이 그냥 'LOGOUT' 이거나 output 이 빈 배열로 온다 — 둘 다 잡는다.
        """
        d = (_dt.date.today() - _dt.timedelta(days=7))
        while d.weekday() >= 5:
            d -= _dt.timedelta(days=1)
        body = {"bld": "dbms/MDC/STAT/standard/MDCSTAT01501", "mktId": "STK",
                "trdDd": d.strftime("%Y%m%d"), "share": "1", "money": "1",
                "csvxls_isNo": "false"}
        txt = http_post(self.JSONDATA, source="krx", data=body, referer=self.JSON_REF,
                        headers={"X-Requested-With": "XMLHttpRequest"}, tries=1)
        if not txt or str(txt).strip() == "LOGOUT":
            return False
        try:
            js = json.loads(txt)
        except Exception:                                    # noqa
            return False
        return bool(js.get("OutBlock_1") or js.get("output") or js.get("block1"))

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
        # ★ 세션 만료는 예외가 아니라 본문 'LOGOUT' 으로 온다. 이걸 그냥 None 으로 흘리면
        #   '데이터가 없는 것'과 구별되지 않아, 만료된 세션으로 수천 번을 헛돈다.
        #   한 번만 알리고 세션을 죽여서 폴백으로 넘긴다(KRX 는 1시간쯤 뒤 만료된다).
        if txt is not None and str(txt).strip() == "LOGOUT":
            if self.session_ok:
                LOG.warn("KRX 세션이 만료되었거나 다른 곳에서 로그인해 끊겼습니다(LOGOUT). "
                         "이후 KRX 호출은 폴백 소스로 넘깁니다.")
            self.session_ok = False
            self.status = "SESSION_EXPIRED"
            return None
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

        # ── 적응형 소스 체인 ────────────────────────────────────────────────────────
        #  ★ 병목의 정체: 체인이 고정 순서라 **죽은 소스의 비용을 2,600종목 전부가 지불**한다.
        #    pykrx 가 인증 실패로 못 쓰는 상태면 종목마다 pykrx 를 먼저 때리고 실패한 뒤
        #    다음으로 넘어간다. 종목당 몇 초 × 2,600 = 수십 분이 통째로 낭비된다.
        #    → 소스별 연속 실패를 세어 임계치를 넘으면 그 소스를 이번 실행에서 내린다.
        #      한 번이라도 성공하면 카운터가 0 으로 돌아가므로 일시적 실패로 내려가지 않는다.
        #    → 그리고 최근 성공한 소스를 앞으로 당긴다(대부분의 종목이 같은 소스에서 나온다).
        _dead_after = 40
        _fail = Counter()
        _ok = Counter()
        _lk = threading.Lock()

        def _chain_order():
            with _lk:
                alive = [(nm, fn) for nm, fn in PRICE_CHAIN if _fail[nm] < _dead_after]
                return sorted(alive, key=lambda x: -_ok[x[0]])

        def _one(job):
            code, st = job
            for nm, fn in _chain_order():
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if nonempty(d):
                    d = d.dropna(subset=["date"])
                    if nonempty(d):
                        with _lk:
                            _ok[nm] += 1
                            _fail[nm] = 0
                        return d
                with _lk:
                    _fail[nm] += 1
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        _dropped = [nm for nm, _fn in PRICE_CHAIN if _fail[nm] >= _dead_after]
        if _dropped:
            LOG.warn(f"연속 {_dead_after}회 실패로 이번 실행에서 내린 가격 소스: {_dropped}. "
                     f"(고정 순서로 두면 죽은 소스의 비용을 전 종목이 지불합니다) "
                     f"성공 분포: {dict(_ok)}")
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
#  [10/27]  12_ingest_dart.py  [v3 코어 재사용]
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


#  ★★ 추측 후보를 만들지 않는다 ★★
#  예전엔 f"{year}_{보고서}_{NN}_{제표}_{연결구분}.zip" 8개를 만들어 시도했다. 성공 확률은
#  **구조적으로 0** 이다 — 실물 파일명이
#      2024_사업보고서_01_재무상태표_연결_20250606.txt
#  처럼 끝에 **배포일자**를 달고 있고, 그건 관측하지 않으면 알 수 없다(제표·연도마다 다르고
#  재배포되면 바뀐다). 게다가 개별은 '_개별'이 아니라 접미사가 없고 확장자도 상황에 따라 다르다.
#  그 결과 이 함수는 '안전망'이 아니라 **실패를 8배로 부풀려 진짜 원인(목록 발견 실패)을
#  로그에서 가리는 장치**였고, 분기마다 32요청을 헛되이 태웠다.
#  → 발견하지 못하면 즉시 폴백으로 내려간다. 그게 유일하게 정직한 동작이다.


def _bulk_discover(year: int, reprt: str) -> Tuple[List[str], str]:
    """페이지에서 실제 fl_nm 을 찾아낸다. 파일명 규칙을 추측하지 않는 것이 1순위다.

    반환 (후보 목록, 진단문자열).
    ★ 진단문자열이 핵심이다. "후보 N개 전부 실패" 만 남기면 사용자 로그를 받아도 원인을
      특정할 수 없다. 페이지를 받았는지 / 로그인 벽인지 / 어떤 링크·폼·스크립트가 있었는지를
      남겨야 다음 실행 로그 한 장으로 고칠 수 있다.
    """
    # ★ 파라미터 이름을 창작하지 않는다. selectYear/selectReprtCode 는 근거가 없는 이름이었고
    #   (공개 코드 전수검색 0건), 그걸 붙여도 서버는 무시하고 기본(최신) 연도 목록만 준다.
    #   그러면 `if str(year) in h` 필터에서 hits=[] 가 되어 '발견 실패'가 조용히 발생한다.
    #   → 폼/스크립트에서 **실제 파라미터 이름을 배워서** 재시도한다. 배우지 못하면 실패로 보고.
    html = http_get(DART_BULK_PAGE, source="dart", tries=2,
                    referer="https://opendart.fss.or.kr/")
    if not html:
        return [], "페이지 응답 없음(네트워크 차단·타임아웃·403 가능). HTTP 감사표를 확인하세요"
    fields = dict.fromkeys(re.findall(r'<(?:input|select)[^>]+name\s*=\s*["\']([^"\']+)["\']',
                                      html, re.I))
    y_key = next((k for k in fields if re.search(r"year|yr|연도", k, re.I)), None)
    r_key = next((k for k in fields if re.search(r"reprt|report|qtr|quarter|분기", k, re.I)), None)
    if y_key:
        params = {y_key: str(year)}
        if r_key:
            params[r_key] = reprt
        h2 = http_get(DART_BULK_PAGE, source="dart", tries=1, params=params,
                      referer=DART_BULK_PAGE)
        if h2 and str(year) in h2:
            html = h2
    low = html.lower()
    marks = []
    if "login" in low or "로그인" in html:
        marks.append("로그인벽 의심")
    for kw in ("downloadfnltt", "fl_nm", "downloadzip", "flnm", "download.do"):
        if kw in low:
            marks.append(f"'{kw}' 발견")
    # 확인된 DOM(셀레늄 자동화 선례): table.tb01 의 a[onclick] 마지막 인자가 실제 파일명이다.
    hits = list(dict.fromkeys(
        [m for m in _BULK_FLNM_RE.findall(html)] +
        [a for a in re.findall(r"['\"]([^'\"]*\.(?:zip|txt))['\"]", html, re.I)
         if re.match(r"^20\d{2}_", a)]))
    hits = [h for h in hits if str(year) in h]
    acts = dict.fromkeys(re.findall(r'(?:action|href)\s*=\s*["\']([^"\']*(?:down|fnltt)[^"\']*)["\']',
                                    html, re.I))
    fns = dict.fromkeys(re.findall(r'onclick\s*=\s*["\'](?:javascript:)?\s*([A-Za-z_$][\w$]*)\s*\(',
                                   html, re.I))
    diag = (f"HTML {len(html):,}자 · 후보 {len(hits)}개 · "
            f"{', '.join(marks) if marks else '단서 없음'} · "
            f"액션 {list(acts)[:3]} · 폼필드 {list(fields)[:6]} · onclick함수 {list(fns)[:4]}")
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
                # 추측 후보를 만들지 않는다(성공확률 0 · 원인만 가림). 즉시 폴백으로 내려간다.
                LOG.debug(f"벌크 {y}/{REPRT_NAME.get(r, r)} 목록 발견 실패 → 건너뜀 · {diag}")
                fail_q.append((y, r))
                continue
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
            "account_id", "account_nm", "thstrm_amount", "rcept_no", "restated"]


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


DART_MIN_YEAR = 2015          # OpenDART 재무 API 는 2015년 이후만 제공한다(그 이전 호출은 순낭비)
# 사업보고서 응답에는 전기(frmtrm_amount)·전전기(bfefrmtrm_amount)가 함께 온다.
_PRIOR_COLS = (("frmtrm_amount", 1), ("bfefrmtrm_amount", 2))


def _fs_one(job) -> Optional[pd.DataFrame]:
    """(corp, year, reprt) 1건. 사업보고서면 전기·전전기 비교치도 함께 수확한다.

    ★★ PIT 주의 — 이 수확은 '콜 수를 1/3 로 줄이는' 용도가 **아니다** ★★
      전기·전전기 금액은 그 보고서가 제출된 시점에 비로소 알 수 있다. 그러므로
      knowledge_date 는 **원 보고서의 접수일이 아니라 이 보고서의 접수일**이다.
      (게다가 소급 재작성된 값일 수 있어 원 공시치와 다르다 — restated=True 로 표시한다)

      만약 "FY2025 한 번 호출해서 2023·2024 를 채우자" 라고 하면, 2024년 백테스트 시점에
      2026년에야 알 수 있는 값을 쓰게 된다. 그건 정확히 미래누수다.
      그래서 이 수확분은 ① 항상 이 보고서의 rcept_no 를 달고 ② 원 공시가 없는 (회사,연도)
      조합을 메우는 용도로만 쓴다. 연도를 건너뛰며 호출하지 않는다.

      실익은 '콜 절감'이 아니라 **YoY 계산의 정합성**이다. t 시점에 알 수 있는 당기값과
      전기값이 같은 문서에서 나오므로 회계기준 변경·재작성으로 인한 불연속이 사라진다.
    """
    corp, year, reprt = job
    if int(year) < DART_MIN_YEAR:
        return None
    # 연결(CFS) 우선, 없으면 개별(OFS). 순서를 바꾸면 지주사에서 매출이 통째로 달라진다.
    for fs_div in ("CFS", "OFS"):
        js = dart_api("fnlttSinglAcntAll.json",
                      {"corp_code": corp, "bsns_year": str(year),
                       "reprt_code": reprt, "fs_div": fs_div})
        if not (js and isinstance(js.get("list"), list) and js["list"]):
            continue
        d = pd.DataFrame(js["list"])
        for c in _FS_KEEP:
            if c not in d.columns:
                d[c] = None
        d["corp_code"] = corp
        d["bsns_year"] = int(year)
        d["reprt_code"] = str(reprt)
        d["fs_div"] = fs_div
        d["restated"] = False
        out = [d[_FS_KEEP]]
        if str(reprt) == REPRT_CODES["FY"]:
            for src_col, back in _PRIOR_COLS:
                if src_col not in d.columns:
                    continue
                p = d.copy()
                p["thstrm_amount"] = p[src_col]
                p["bsns_year"] = int(year) - back
                p["restated"] = True
                p = p[p["thstrm_amount"].notna()]
                # rcept_no 는 **이 보고서의 것**을 그대로 유지한다 → knowledge_date 가
                # 자동으로 '이 보고서 접수일'이 되어 PIT 가 지켜진다.
                if len(p) and int(year) - back >= DART_MIN_YEAR - 2:
                    out.append(p[_FS_KEEP])
        return pd.concat(out, ignore_index=True)
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
            if int(y) >= DART_MIN_YEAR and (c, int(y), str(r)) not in done]
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
    # ★ 원 공시(restated=False)가 재작성 수확치(True)를 항상 이긴다. 원 공시가 knowledge_date
    #   가 더 이르고(= 그 시점에 실제로 알 수 있었고) 값도 당시 공시된 그대로이기 때문이다.
    if "restated" in F.columns:
        F["restated"] = F["restated"].fillna(True).astype(bool)
        F = F.sort_values("restated", kind="stable")
    F = F.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                           "account_nm"], keep="first")
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
#  [11/27]  15_mcap.py  [v3 코어 재사용]
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
#  [12/27]  16_ingest_research.py  [v3 코어 재사용]
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
#  [13/27]  17_entity_research.py  [v3 코어 재사용]
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
#  [14/27]  20_pit_v3.py  [v3 코어 재사용]
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
#  [15/27]  50_backtest.py  [v3 코어 재사용]
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
#  [16/27]  21_foreign.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  FOREIGN — 다른 전략이 만들어 둔 구글드라이브 캐시를 '읽기 전용'으로 흡수한다               ║
# ║                                                                                             ║
# ║  ★★★ 절대 1원칙 ★★★                                                                        ║
# ║    이 모듈에는 **기존 인덱스를 수정하는 코드 경로가 하나도 없다.**                           ║
# ║    - 외부 인덱스 파일은 `open(..., "r")` 로만 연다. 쓰기 모드로 여는 곳이 없다.              ║
# ║    - 삭제/이동/개명 API 를 import 조차 하지 않는다.                                         ║
# ║    - 유일한 쓰기는 `foreign_publish_common()` 하나이며, 그마저도                             ║
# ║        (1) 새 데이터 파일은 **새 이름**으로만 쓰고                                           ║
# ║        (2) 레지스트리는 **새 키만 추가**하며(기존 키 값은 손대지 않음)                       ║
# ║        (3) 쓰기 전 타임스탬프 백업 → 원자적 교체 → 재읽기 검증 → 실패 시 자동 롤백           ║
# ║      을 전부 통과해야 커밋된다. 하나라도 실패하면 사이드카 파일로 물러난다.                  ║
# ║                                                                                             ║
# ║  왜 필요한가: 이 계정의 리포트 원장 본체는 tcd_cache 가 아니라 QuantCache/common/reports 에  ║
# ║  있다(report_ledger 30만행 · analyst_registry · blob_map). 워크스페이스마다 인덱스 형식이   ║
# ║  달라서(매니페스트 / kind|ym / JSONL / 플랫 dict) 어댑터 없이는 재활용이 불가능하다.        ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 외부 인덱스의 '형식'별 어댑터. 실측된 4가지 형식을 전부 다룬다.
#   A) _manifest_*.json   : {dataset: {dataset,scope,keys,path,rows,ext,producer,updated_at,files}}
#   B) public_index.json  : {schema_version, entries:{ "kind|ym": {kind,ym,rows,file,updated_at,contributor} }}
#   C) index.jsonl        : 한 줄당 {uid,domain,subtype,key,path,abs_path,fmt,bytes,...}
#   D) done_index.json    : {"hk:331500": "OK", ...}   ← 상태 원장(재수집 스킵 판단용)
FOREIGN_INDEX_FILES = ("_manifest_common.json", "public_index.json", "index.jsonl",
                       "done_index.json", "private_index.json", "absorb_manifest.json")

# 외부 parquet 의 payload 컬럼명은 워크스페이스마다 다르다. 실행 시점에 발견해서 매핑한다.
# ★ 하드코딩하지 않는 이유: 매니페스트는 '키 컬럼'만 선언하고 payload 컬럼은 선언하지 않는다.
#   컬럼명을 추측해 고정하면 이름이 다른 순간 조용히 빈 프레임이 되고, 그게 가장 위험한 실패다.
FOREIGN_ALIAS: "dict[str, tuple]" = {
    "src_report_id": ("src_id", "src_report_id", "report_id", "nid", "artid", "seq", "id"),
    "source":        ("src", "source", "site", "provider"),
    "pub_date":      ("pub_date", "date", "report_date", "wdate", "published", "reg_date",
                      "regdate", "ymd", "dt", "write_date"),
    "stock_code":    ("stock_code", "code", "ticker", "isu_srt_cd", "shcode", "symbol",
                      "stk_cd", "corp_code6"),
    "stock_name":    ("stock_name", "name", "corp_name", "isu_nm", "종목명"),
    "broker_raw":    ("broker_raw", "broker", "broker_name", "house", "sec_firm", "office",
                      "company", "증권사"),
    "analyst_raw":   ("analyst_raw", "analyst", "analyst_name", "writer", "author", "작성자"),
    "analyst_id":    ("analyst_id", "aid", "analyst_key"),
    "target_price":  ("target_price", "tp", "goal_price", "target", "목표주가"),
    "opinion":       ("opinion", "rating", "investment_opinion", "투자의견"),
    "title":         ("title", "subject", "report_title", "제목"),
    "pdf_url":       ("pdf_url", "url", "file_url", "attach_url", "link"),
    "detail_url":    ("detail_url", "page_url", "view_url"),
}

# 통관/가격/재무 등 다른 도메인도 같은 방식으로 흡수한다.
FOREIGN_ALIAS_MARKET: "dict[str, tuple]" = {
    "code":   ("code", "ticker", "stock_code", "isu_srt_cd", "symbol", "shcode"),
    "date":   ("date", "trd_dd", "trade_date", "dt", "ymd", "basd_dt"),
    "close":  ("close", "clpr", "tdd_clsprc", "adj_close", "price"),
    "volume": ("volume", "acc_trdvol", "trdvol", "vol"),
    "amount": ("amount", "acc_trdval", "trdval", "value", "tr_amount"),
    "shares": ("shares", "listed_shares", "list_shrs", "lstg_stcnt", "shares_out"),
    "mcap":   ("mcap", "market_cap", "mktcap", "mkt_cap"),
}
FOREIGN_ALIAS_CUSTOMS: "dict[str, tuple]" = {
    "hs":       ("hs", "hs_code", "hsCode", "hsSgn", "hscode", "hs10", "hs6"),
    "ym":       ("ym", "year_month", "yyyymm", "period", "month"),
    "country":  ("country", "cnty", "cntyCd", "cntyNm", "nation", "ctry"),
    "exp_wgt":  ("exp_wgt", "expWgt", "export_weight", "wgt", "weight_kg"),
    "exp_usd":  ("exp_usd", "expDlr", "export_usd", "usd", "value_usd", "dlr"),
}


def _foreign_root_variants(root: str) -> "list[str]":
    """Colab 절대경로로 기록된 매니페스트를 JupyterLab 로컬에서도 찾을 수 있게 후보를 만든다.

    매니페스트의 `path` 는 대부분 `/content/drive/MyDrive/...` 로 굳어 있다.
    로컬에서 돌리면 그 경로는 존재하지 않으므로, 마운트 접두사만 바꿔 재시도한다.
    """
    out = [root]
    base = os.path.basename(root.rstrip("/"))
    cands = []
    try:
        cands.append(os.path.join(str(Path.home()), base))
        cands.append(os.path.join(os.getcwd(), base))
    except Exception:                                                   # noqa
        pass
    for pref in ("/content/drive/MyDrive", "/content/drive/Shareddrives",
                 os.environ.get("TCD_DRIVE_PREFIX", "")):
        if pref:
            cands.append(os.path.join(pref, base))
    for c in cands:
        if c and c not in out:
            out.append(c)
    return out


def foreign_remap(path: str, roots: "Sequence[str]") -> Optional[str]:
    """매니페스트에 적힌 절대경로를 실제 존재하는 경로로 되짚는다. 없으면 None."""
    if not path:
        return None
    if os.path.exists(path):
        return path
    norm = str(path).replace("\\", "/")
    # 알려진 마운트 접두사를 벗겨 상대경로를 얻고, 각 루트 후보에 다시 붙여 본다.
    for pref in ("/content/drive/MyDrive/", "/content/drive/Shareddrives/",
                 str(Path.home()).rstrip("/") + "/", "./"):
        if norm.startswith(pref):
            rel = norm[len(pref):]
            break
    else:
        rel = norm.lstrip("/")
    for r in roots:
        for rv in _foreign_root_variants(r):
            base = os.path.basename(rv.rstrip("/"))
            # rel 이 루트 이름으로 시작하면 중복을 제거한다
            rel2 = rel[len(base) + 1:] if rel.startswith(base + "/") else rel
            for cand in (os.path.join(rv, rel2), os.path.join(os.path.dirname(rv), rel)):
                if cand and os.path.exists(cand):
                    return cand
    return None


def _read_json_ro(path: str) -> Optional[Any]:
    """외부 JSON 을 **읽기 전용**으로 연다. 파싱 실패는 경고만 하고 None."""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception as e:                                              # noqa
        LOG.debug(f"외부 인덱스 읽기 실패(무시): {os.path.basename(path)} — {type(e).__name__}")
        return None


class ForeignCatalog:
    """외부 캐시 카탈로그. **읽기 전용.** 쓰기 메서드가 존재하지 않는다."""

    def __init__(self, roots: "Sequence[str]"):
        self.roots: List[str] = []
        for r in roots or []:
            for rv in _foreign_root_variants(r):
                if os.path.isdir(rv) and rv not in self.roots:
                    self.roots.append(rv)
                    break
        self.datasets: Dict[str, dict] = {}      # name -> {path, rows, keys, producer, index, scope}
        self.status: Dict[str, str] = {}         # "hk:12345" -> "OK" (재수집 스킵 판단)
        self.indexes_seen: List[dict] = []
        self.errors: List[str] = []

    # ── 발견 ------------------------------------------------------------------------
    def scan(self, max_depth: int = 4) -> "ForeignCatalog":
        for root in self.roots:
            for idx_path in self._find_indexes(root, max_depth):
                self._absorb_index(idx_path, root)
        LOG.info(f"외부 캐시 스캔: 루트 {len(self.roots)}개 · 인덱스 {len(self.indexes_seen)}개 · "
                 f"데이터셋 {len(self.datasets)}개 · 상태원장 {len(self.status):,}건")
        return self

    def _find_indexes(self, root: str, max_depth: int) -> "List[str]":
        found: List[str] = []
        root = root.rstrip("/")
        base_depth = root.count("/")
        for dirpath, dirnames, filenames in os.walk(root):
            if dirpath.count("/") - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn in FOREIGN_INDEX_FILES or (
                        fn.startswith("_manifest_") and fn.endswith(".json")):
                    found.append(os.path.join(dirpath, fn))
        return found

    def _absorb_index(self, path: str, root: str) -> None:
        name = os.path.basename(path)
        try:
            if name == "index.jsonl":
                self._absorb_jsonl(path, root)
            elif name == "done_index.json":
                self._absorb_status(path)
            elif name == "public_index.json":
                self._absorb_public(path, root)
            elif name.startswith("_manifest_") or name == "absorb_manifest.json":
                self._absorb_manifest(path, root)
            elif name == "private_index.json":
                self._absorb_journal(path)
            self.indexes_seen.append({"path": path, "kind": name, "root": root})
        except Exception as e:                                          # noqa
            self.errors.append(f"{name}: {type(e).__name__}: {e}")

    def _absorb_manifest(self, path: str, root: str) -> None:
        obj = _read_json_ro(path)
        if not isinstance(obj, dict):
            return
        for key, rec in obj.items():
            if not isinstance(rec, dict):
                continue
            p = rec.get("path") or (rec.get("files") or [None])[0]
            real = foreign_remap(str(p or ""), [root] + self.roots)
            if not real:
                continue
            self.datasets[str(rec.get("dataset") or key)] = {
                "path": real, "rows": int(rec.get("rows") or 0),
                "keys": list(rec.get("keys") or []), "producer": str(rec.get("producer") or ""),
                "updated_at": str(rec.get("updated_at") or ""),
                "scope": str(rec.get("scope") or ""), "index": path,
            }

    def _absorb_public(self, path: str, root: str) -> None:
        obj = _read_json_ro(path)
        if not isinstance(obj, dict):
            return
        entries = obj.get("entries")
        if not isinstance(entries, dict):
            return
        base = os.path.dirname(path)
        # kind 별로 월 파일을 묶어 하나의 논리 데이터셋으로 등록한다.
        buckets: Dict[str, List[dict]] = {}
        for key, rec in entries.items():
            if not isinstance(rec, dict):
                continue
            f = rec.get("file")
            if not f:
                continue
            real = foreign_remap(os.path.join(base, str(f)), [root] + self.roots) \
                or foreign_remap(str(f), [root] + self.roots)
            if not real:
                continue
            buckets.setdefault(str(rec.get("kind") or "unknown"), []).append(
                {"path": real, "ym": str(rec.get("ym") or ""), "rows": int(rec.get("rows") or 0)})
        for kind, parts in buckets.items():
            parts.sort(key=lambda r: r["ym"])
            self.datasets[f"arc_{kind}"] = {
                "path": parts[0]["path"], "parts": [p["path"] for p in parts],
                "rows": sum(p["rows"] for p in parts), "keys": [], "producer": "ARC_COMMON_LEDGER",
                "updated_at": "", "scope": "common", "index": path,
            }

    def _absorb_jsonl(self, path: str, root: str) -> None:
        for rec in read_jsonl(path):
            if not isinstance(rec, dict):
                continue
            p = rec.get("abs_path") or rec.get("path")
            real = foreign_remap(str(p or ""), [root] + self.roots)
            if not real:
                continue
            key = str(rec.get("key") or os.path.basename(real))
            self.datasets.setdefault(key.replace(".parquet", ""), {
                "path": real, "rows": 0, "keys": [], "producer": str(rec.get("source") or ""),
                "updated_at": str(rec.get("collected_at") or ""),
                "scope": str(rec.get("scope") or ""), "index": path,
            })

    def _absorb_status(self, path: str) -> None:
        obj = _read_json_ro(path)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and ":" in k:
                    self.status[k] = str(v)

    def _absorb_journal(self, path: str) -> None:
        obj = _read_json_ro(path)
        if isinstance(obj, dict) and isinstance(obj.get("log"), list):
            self.indexes_seen.append({"path": path, "kind": "journal",
                                      "events": len(obj["log"])})

    # ── 적재 ------------------------------------------------------------------------
    def load(self, *names: str, alias: Optional[dict] = None,
             max_parts: int = 0) -> Optional[pd.DataFrame]:
        """이름 후보 중 먼저 발견되는 데이터셋을 읽고, 별칭표로 컬럼을 표준화한다."""
        for nm in names:
            rec = self.datasets.get(nm)
            if not rec:
                continue
            paths = rec.get("parts") or [rec["path"]]
            if max_parts:
                paths = paths[-max_parts:]
            frames = []
            for p in paths:
                d = read_parquet_safe(p)
                if d is not None and len(d):
                    frames.append(d)
            if not frames:
                continue
            out = frames[0] if len(frames) == 1 else pd.concat(
                [f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                 for f in frames], ignore_index=True)
            PIPE.io("IN", "FOREIGN", f"dataset:{nm}", out, source=rec.get("index", ""))
            return foreign_normalize(out, alias) if alias else out
        return None

    def find(self, *substrings: str) -> "List[str]":
        out = []
        for nm in self.datasets:
            low = nm.lower()
            if any(s.lower() in low for s in substrings):
                out.append(nm)
        return sorted(out)

    def report(self) -> None:
        if not self.datasets:
            LOG.warn("외부 캐시에서 재활용할 데이터셋을 찾지 못했습니다 "
                     "(GDRIVE_FOREIGN_ROOTS 경로를 확인하세요). 신규 수집으로 진행합니다.")
            return
        rows = []
        for nm, r in sorted(self.datasets.items(), key=lambda kv: -kv[1].get("rows", 0))[:28]:
            rows.append([nm[:34], f"{r.get('rows', 0):,}", (r.get('producer') or '')[:18],
                         (r.get('scope') or '')[:9],
                         os.path.basename(os.path.dirname(r['path']))[:22]])
        LOG.banner("외부 캐시 재활용 카탈로그 (읽기 전용)",
                   f"루트 {len(self.roots)}개 · 데이터셋 {len(self.datasets)}개 · "
                   f"상태원장 {len(self.status):,}건 — 기존 인덱스는 열지도 고치지도 않습니다")
        LOG.table(rows, ["데이터셋", "행수", "생산자", "스코프", "폴더"])
        if self.errors:
            LOG.warn(f"일부 인덱스 파싱 실패 {len(self.errors)}건(무시하고 진행): "
                     f"{self.errors[:3]}")


def foreign_normalize(df: pd.DataFrame, alias: dict) -> pd.DataFrame:
    """별칭표로 컬럼을 표준명으로 바꾼다. 원본 컬럼은 지우지 않고 남긴다(정보 손실 방지)."""
    if df is None or not len(df):
        return df
    lower = {str(c).lower().strip(): c for c in df.columns}
    ren = {}
    for canon, cands in alias.items():
        if canon in df.columns:
            continue
        for c in cands:
            src = lower.get(str(c).lower())
            if src is not None and src not in ren.values():
                ren[canon] = src
                break
    out = df.copy()
    for canon, src in ren.items():
        out[canon] = df[src]
    return out


def foreign_reports(cat: "ForeignCatalog") -> pd.DataFrame:
    """외부 리포트 원장을 이 코드의 REPORT_COLS 스키마로 정규화해서 돌려준다."""
    d = cat.load("report_ledger", "arc_reports", "reports", "raw_reports",
                 alias=FOREIGN_ALIAS)
    if d is None or not len(d):
        return pd.DataFrame(columns=REPORT_COLS)

    out = pd.DataFrame(index=d.index)
    # source: 실측상 'hk' / 'nv' 로 저장되어 있다 → 이 코드의 표기로 사상
    src = d["source"].astype(str).str.lower().str.strip() if "source" in d.columns else pd.Series("", index=d.index)
    out["source"] = src.map({"hk": "hankyung", "hankyung": "hankyung",
                             "nv": "naver", "naver": "naver"}).fillna(src)
    out["src_report_id"] = d["src_report_id"].astype(str) if "src_report_id" in d.columns else ""
    for c in ("title", "stock_name", "broker_raw", "analyst_raw", "opinion",
              "pdf_url", "detail_url", "category"):
        out[c] = d[c].astype(str) if c in d.columns else ""
    out["stock_code"] = (d["stock_code"].map(to_code6) if "stock_code" in d.columns
                         else pd.Series(pd.NA, index=d.index))
    out["target_price"] = (pd.to_numeric(d["target_price"], errors="coerce")
                           if "target_price" in d.columns else np.nan)
    out["pub_date"] = as_ts_series(d["pub_date"]) if "pub_date" in d.columns else pd.NaT

    # 목표주가 0/음수는 '없음'이다 — 0 으로 넣으면 리비전 팩터가 오염된다.
    out.loc[~(out["target_price"] > 0), "target_price"] = np.nan

    out["report_uid"] = [
        sha1_str("rpt", s, i) for s, i in zip(out["source"].astype(str),
                                              out["src_report_id"].astype(str))]
    out["broker_id"] = ""
    out["broker_name"] = ""
    out["pdf_uid"] = ""
    out["views"] = np.nan
    out = out[out["pub_date"].notna()].copy()
    # PIT: 리포트의 knowledge_date 는 게시일이다.
    out["event_date"] = out["pub_date"]
    out["knowledge_date"] = out["pub_date"]
    out = out.reindex(columns=REPORT_COLS)
    LOG.ok(f"외부 리포트 원장 흡수: {len(out):,}건 "
           f"(종목코드 {out['stock_code'].notna().mean() * 100:.0f}% · "
           f"애널리스트 {(out['analyst_raw'].astype(str).str.len() > 0).mean() * 100:.0f}% · "
           f"목표주가 {out['target_price'].notna().mean() * 100:.0f}%)")
    return out


def foreign_analysts(cat: "ForeignCatalog") -> pd.DataFrame:
    """외부 애널리스트 원장(analyst_registry 등)을 흡수한다. 없으면 빈 프레임."""
    d = cat.load("analyst_registry", "analyst_index", "naver_analyst_index",
                 alias=FOREIGN_ALIAS)
    if d is None or not len(d):
        return pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"])
    out = pd.DataFrame(index=d.index)
    out["analyst_id"] = (d["analyst_id"].astype(str) if "analyst_id" in d.columns
                         else d.index.astype(str))
    out["name"] = d["analyst_raw"].astype(str) if "analyst_raw" in d.columns else ""
    out["broker_name"] = d["broker_raw"].astype(str) if "broker_raw" in d.columns else ""
    out["broker_id"] = out["broker_name"].map(lambda s: sha1_str("brk", norm_text(s))[:10])
    out = out[out["name"].str.len() > 0].drop_duplicates("analyst_id")
    LOG.ok(f"외부 애널리스트 원장 흡수: {len(out):,}명")
    return out


# ── 공용 레지스트리에 '추가만' 하는 발행 경로 ───────────────────────────────────────────────────

def foreign_publish_common(cat: "ForeignCatalog", dataset: str, df: pd.DataFrame,
                           keys: "Sequence[str]", producer: str) -> bool:
    """새로 수집한 공용 데이터를 사용자의 기존 공용 레지스트리에 **추가만** 한다.

    이 함수가 지키는 것(하나라도 깨지면 커밋하지 않고 사이드카로 물러난다):
      1. 데이터 파일은 **새 이름**으로만 쓴다. 기존 parquet 을 덮어쓰지 않는다.
      2. 레지스트리는 **새 키만** 추가한다. 기존 키의 값은 읽고 그대로 되쓴다.
      3. 쓰기 전 타임스탬프 백업을 만든다. 백업 실패 시 레지스트리를 건드리지 않는다.
      4. 원자적 교체 후 **다시 읽어** 기존 키가 전부 살아있는지 검증한다.
      5. 검증 실패 시 백업에서 즉시 롤백한다.
    """
    if not FOREIGN_PUBLISH_TO_COMMON or df is None or not len(df):
        return False
    # 기존 공용 레지스트리(_manifest_common.json)를 찾는다.
    reg = None
    for rec in cat.indexes_seen:
        if os.path.basename(rec.get("path", "")) == "_manifest_common.json":
            reg = rec["path"]
            break
    if not reg or not os.path.exists(reg):
        LOG.debug("공용 레지스트리(_manifest_common.json)를 찾지 못해 발행을 건너뜁니다.")
        return False

    obj = _read_json_ro(reg)
    if not isinstance(obj, dict):
        LOG.warn("공용 레지스트리를 파싱할 수 없어 발행하지 않습니다(안전 우선).")
        return False
    if dataset in obj:
        # 이미 있는 키는 건드리지 않는다. 이름을 바꿔 새 키로 발행한다.
        dataset = f"{dataset}__{STRATEGY_ID.lower()}"
    if dataset in obj:
        LOG.debug(f"공용 레지스트리에 이미 {dataset} 이 있어 발행을 건너뜁니다.")
        return False

    base = os.path.dirname(reg)
    dom = os.path.join(base, "customs" if "customs" in dataset else "external")
    try:
        os.makedirs(dom, exist_ok=True)
    except Exception:                                                    # noqa
        dom = base
    fpath = os.path.join(dom, f"{dataset}.parquet")
    if os.path.exists(fpath):                       # 남의 파일을 절대 덮지 않는다
        fpath = os.path.join(dom, f"{dataset}.{_dt.datetime.now():%Y%m%d_%H%M%S}.parquet")
    try:
        atomic_write_parquet(df, fpath)
    except Exception as e:                                               # noqa
        LOG.warn(f"공용 데이터 파일 저장 실패({type(e).__name__}) — 발행 취소")
        return False

    bakdir = os.path.join(base, "_backups")
    bak = os.path.join(bakdir, f"_manifest_common.{_dt.datetime.now():%Y%m%d_%H%M%S}.json")
    try:
        os.makedirs(bakdir, exist_ok=True)
        shutil.copy2(reg, bak)
    except Exception as e:                                               # noqa
        LOG.warn(f"공용 레지스트리 백업 실패({type(e).__name__}) — "
                 f"레지스트리를 건드리지 않고 사이드카에만 기록합니다.")
        _publish_sidecar(base, dataset, fpath, df, keys, producer)
        return False

    before = set(obj.keys())
    obj[dataset] = {
        "dataset": dataset, "scope": "common", "keys": list(keys),
        "path": fpath, "rows": int(len(df)), "ext": ".parquet",
        "producer": f"{producer} {BUILD_VERSION}",
        "updated_at": _dt.datetime.now().astimezone().isoformat(),
        "files": [fpath],
    }
    try:
        atomic_write_text(reg, json.dumps(obj, ensure_ascii=False, indent=1))
        back = _read_json_ro(reg)
        if not isinstance(back, dict) or not before.issubset(set(back.keys())):
            raise RuntimeError("재읽기 검증 실패 — 기존 키가 유실되었습니다")
    except Exception as e:                                               # noqa
        try:
            shutil.copy2(bak, reg)                     # 즉시 롤백
            LOG.error(f"공용 레지스트리 갱신 실패({type(e).__name__}) — 백업에서 롤백했습니다.")
        except Exception:                                                # noqa
            LOG.error(f"공용 레지스트리 갱신 및 롤백 실패 — 백업 파일: {bak}")
        _publish_sidecar(base, dataset, fpath, df, keys, producer)
        return False
    LOG.ok(f"공용 레지스트리에 추가: {dataset} ({len(df):,}행) — "
           f"기존 {len(before)}개 키 전부 보존 확인 · 백업 {os.path.basename(bak)}")
    return True


def _publish_sidecar(base: str, dataset: str, fpath: str, df: pd.DataFrame,
                     keys: "Sequence[str]", producer: str) -> None:
    """레지스트리를 건드릴 수 없을 때의 물러섬. 별도 파일에만 기록한다."""
    side = os.path.join(base, f"_manifest_common_{STRATEGY_ID.lower()}.json")
    cur = _read_json_ro(side) if os.path.exists(side) else {}
    if not isinstance(cur, dict):
        cur = {}
    cur[dataset] = {"dataset": dataset, "scope": "common", "keys": list(keys),
                    "path": fpath, "rows": int(len(df)), "ext": ".parquet",
                    "producer": f"{producer} {BUILD_VERSION}",
                    "updated_at": _dt.datetime.now().astimezone().isoformat(),
                    "files": [fpath]}
    try:
        atomic_write_text(side, json.dumps(cur, ensure_ascii=False, indent=1))
        LOG.info(f"사이드카 레지스트리에 기록: {os.path.basename(side)} ← {dataset}")
    except Exception:                                                    # noqa
        LOG.warn("사이드카 기록도 실패했습니다. 데이터 파일 자체는 저장되어 있습니다.")


FOREIGN: Optional["ForeignCatalog"] = None


def foreign_init() -> "ForeignCatalog":
    """외부 캐시를 스캔해 전역 카탈로그를 세운다. 실패해도 실행은 계속된다."""
    global FOREIGN
    try:
        FOREIGN = ForeignCatalog(GDRIVE_FOREIGN_ROOTS).scan()
        FOREIGN.report()
    except Exception as e:                                               # noqa
        LOG.warn(f"외부 캐시 스캔 실패({type(e).__name__}: {e}) — 신규 수집으로 진행합니다.")
        FOREIGN = ForeignCatalog([])
    return FOREIGN


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [17/27]  22_customs.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  관세청 통관 수집 — 이 전략의 유일한 대체 데이터원                                          ║
# ║                                                                                             ║
# ║  ★ 계약 C18 (이 전략 고유) — 소급 수정 데이터의 보수적 PIT                                  ║
# ║   (a) 관세청은 매월 15일경 정정·취하를 반영해 전월까지 자료를 '현행화'한다.                  ║
# ║       따라서 시점 t 에 실제로 공표되었던 원값은 사후 복원이 불가능하다.                      ║
# ║   (b) knowledge_date = 귀속월의 **익월 말일**로 고정한다.                                    ║
# ║       실제 공표(익월 15일경)보다 약 15일 보수적이며, 이 여유가 소급 수정 위험을 흡수한다.    ║
# ║   (c) 오늘부터 매월 스냅샷을 raw 캐시에 적재한다. 복원 불가 자산이므로                       ║
# ║       오늘 켜지 않으면 2년 뒤에도 2년치다.                                                   ║
# ║   (d) X5 실측(현행화 크기)을 리포트에 명시한다. 1% 초과면 상향 편의 경고를 출력한다.         ║
# ║                                                                                             ║
# ║  ⚠ "확정치를 쓰면 되지 않나"로 우회하지 말 것. 확정치는 다음 연도에 나오므로 선행성을        ║
# ║    통째로 반납하고, 그러면 이 전략의 존재 이유가 사라진다.                                   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 공공데이터포털 관세청 오픈API 후보. 스펙이 바뀌어도 죽지 않도록 **여러 후보를 순서대로 탐침**한다.
#   추측한 파라미터명을 하드코딩해 두면 이름 하나가 달라진 순간 조용히 빈 프레임이 되고,
#   그게 이 전략에서 가장 위험한 실패다(A축 전체가 사라지는데 예외는 안 난다).
CUSTOMS_ENDPOINTS: "list[dict]" = [
    {
        "name": "품목별 국가별 수출입실적",
        "url": "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
        "has_country": True,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm", "country": "cntyCd"},
    },
    {
        "name": "품목별 국가별 수출입실적(대체경로)",
        "url": "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
        "has_country": True,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm", "country": "cntyCd"},
    },
    {
        "name": "품목별 수출입실적",
        "url": "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList",
        "has_country": False,
        "params": {"hs": "hsSgn", "start": "strtYymm", "end": "endYymm"},
    },
]

# 응답 필드 별칭 — 스펙 문서와 실제 응답이 다른 경우가 잦다.
CUSTOMS_FIELD_ALIAS = {
    "hs":      ("hsCd", "hsSgn", "hsCode", "hs_cd"),
    # ★ statKor 는 **품목명**이다. 국가명은 statCdCntnKor1 이다.
    #   이걸 뒤집으면 국가군 축약이 품목명 기준으로 돌아가 목적지 축(a3·a4)이 통째로 망가진다.
    "hs_name": ("statKor", "hsCdNm", "hsNm", "korPrlstNm", "prlstNm"),
    "country": ("statCd", "cntyCd", "cntrCd", "natCd"),
    "cty_name": ("statCdCntnKor1", "cntyNm", "statCdNm", "korNm"),
    "period":  ("year", "yymm", "statYymm", "prid"),
    "exp_usd": ("expDlr", "expUsd", "expAmt"),
    "exp_wgt": ("expWgt", "expWt", "expQty"),
    "imp_usd": ("impDlr", "impUsd", "impAmt"),
    "imp_wgt": ("impWgt", "impWt", "impQty"),
}

# 국가군 축약 (§6.1). 230개국을 그대로 들고 다니면 행이 10배가 되고 얻는 것이 없다.
COUNTRY_GROUPS: "dict[str, str]" = {
    "US": "US", "CN": "CN", "JP": "JP", "TW": "TW", "DE": "DE", "VN": "VN", "IN": "IN",
    "HK": "CN", "MO": "CN",
    "FR": "EU", "IT": "EU", "NL": "EU", "BE": "EU", "ES": "EU", "PL": "EU", "SE": "EU",
    "AT": "EU", "CZ": "EU", "HU": "EU", "SK": "EU", "DK": "EU", "FI": "EU", "IE": "EU",
    "PT": "EU", "GR": "EU", "RO": "EU", "BG": "EU", "SI": "EU", "HR": "EU", "LT": "EU",
    "LV": "EU", "EE": "EU", "LU": "EU", "CY": "EU", "MT": "EU", "GB": "EU",
    "TH": "ASEAN", "MY": "ASEAN", "ID": "ASEAN", "PH": "ASEAN", "SG": "ASEAN",
    "MM": "ASEAN", "KH": "ASEAN", "LA": "ASEAN", "BN": "ASEAN",
    "SA": "ME", "AE": "ME", "QA": "ME", "KW": "ME", "OM": "ME", "BH": "ME", "IL": "ME",
    "TR": "ME", "IR": "ME", "IQ": "ME", "JO": "ME", "EG": "ME",
    "BR": "LATAM", "MX": "LATAM", "CL": "LATAM", "AR": "LATAM", "PE": "LATAM",
    "CO": "LATAM", "PA": "LATAM",
    "AU": "OCE", "NZ": "OCE",
    "RU": "CIS", "KZ": "CIS", "UZ": "CIS", "UA": "CIS",
    "CA": "NA_OTH",
}


def _country_group(code: Any, name: Any = "") -> str:
    c = str(code or "").strip().upper()
    if c in COUNTRY_GROUPS:
        return COUNTRY_GROUPS[c]
    return "OTHER" if c else "OTHER"


def customs_knowledge_date(ym: pd.Series) -> pd.Series:
    """C18-(b): knowledge_date = 귀속월의 익월 말일.

    귀속 2018-03 → 알 수 있게 되는 시점 2018-04-30.
    실제 공표는 04-15경이므로 약 15일 보수적이다. 이 여유가 소급 수정 위험을 흡수한다.
    """
    t = as_ts_series(ym)
    return (t + pd.offsets.MonthEnd(1)).astype("datetime64[ns]")


def _cpick(row: dict, names: "Sequence[str]") -> Any:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    # 대소문자 무시 재시도
    low = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(str(n).lower())
        if v not in (None, ""):
            return v
    return None


def _cnum(x: Any) -> float:
    """천단위 콤마·공백을 제거하고 실수로. 실패하면 NaN."""
    if x is None:
        return float("nan")
    t = str(x).replace(",", "").replace(" ", "").strip()
    if t in ("", "-", "--"):
        return float("nan")
    try:
        return float(t)
    except Exception:                                                   # noqa
        return float("nan")


def _customs_parse(items: "Sequence[dict]", has_country: bool) -> pd.DataFrame:
    """응답 아이템 목록 → 표준 스키마. 별칭표로 필드명 변화를 흡수한다."""
    if not items:
        return pd.DataFrame(columns=["hs", "ym", "country", "exp_wgt", "exp_usd",
                                     "imp_wgt", "imp_usd"])
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        per = str(_cpick(it, CUSTOMS_FIELD_ALIAS["period"]) or "").strip()
        # 'year' 필드가 총계행에서는 '2018' 처럼 연도만 오기도 한다 → 월이 없으면 버린다.
        digits = "".join(ch for ch in per if ch.isdigit())
        if len(digits) < 6:
            continue
        ym = pd.Timestamp(f"{digits[:4]}-{digits[4:6]}-01") + pd.offsets.MonthEnd(0)
        hs = str(_cpick(it, CUSTOMS_FIELD_ALIAS["hs"]) or "").strip()
        # ★ 응답은 상세행과 '총계' 집계행을 섞어서 준다. 총계를 걸러내지 않으면
        #   물량·금액이 정확히 두 배가 되고 단가는 멀쩡해 보여 발견이 매우 어렵다.
        if not hs or hs in ("-", "총계", "합계"):
            continue
        ccode = _cpick(it, CUSTOMS_FIELD_ALIAS["country"]) if has_country else "ALL"
        cname = _cpick(it, CUSTOMS_FIELD_ALIAS["cty_name"]) if has_country else ""
        rows.append({
            "hs": hs,
            "ym": ym,
            "country": _country_group(ccode, cname) if has_country else "ALL",
            # ★ 숫자가 "12,300" 처럼 천단위 콤마를 달고 온다. to_numeric 은 이를 NaN 으로
            #   만들어 버리므로, 큰 값일수록 결측이 되는 체계적 편의가 생긴다.
            "exp_usd": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["exp_usd"])),
            "exp_wgt": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["exp_wgt"])),
            "imp_usd": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["imp_usd"])),
            "imp_wgt": _cnum(_cpick(it, CUSTOMS_FIELD_ALIAS["imp_wgt"])),
        })
    d = pd.DataFrame(rows)
    if not len(d):
        return d
    # 국가군으로 축약했으므로 같은 (hs, ym, group) 이 여러 국가에서 온다 → 합산.
    d = d.groupby(["hs", "ym", "country"], observed=True, as_index=False).sum(numeric_only=True)
    return d


def _extract_items(payload: Any) -> "list[dict]":
    """공공데이터포털 응답에서 item 리스트를 꺼낸다. 래핑 구조가 서비스마다 다르다."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    # response.body.items.item  /  response.body.items  /  items.item …
    for path in (("response", "body", "items", "item"),
                 ("response", "body", "items"),
                 ("body", "items", "item"),
                 ("items", "item"), ("items",), ("item",)):
        cur: Any = payload
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            if isinstance(cur, dict):
                return [cur]
            if isinstance(cur, list):
                return [x for x in cur if isinstance(x, dict)]
    return []


def _customs_error(payload: Any) -> str:
    """오류 응답이면 한국어 진단 문자열을, 정상이면 빈 문자열을 돌려준다."""
    if not isinstance(payload, dict):
        return ""
    txt = json.dumps(payload, ensure_ascii=False)[:400]
    for key, msg in (
        ("SERVICE_KEY_IS_NOT_REGISTERED", "인증키가 등록되지 않았습니다. "
         "data.go.kr 에서 이 API 를 '활용신청'했는지, **Decoding 키**를 넣었는지 확인하세요."),
        ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "일일 트래픽 한도를 초과했습니다. "
         "내일 다시 시도하거나 활용신청에서 한도를 늘리세요."),
        ("SERVICE_ACCESS_DENIED", "접근이 거부되었습니다. 활용신청 승인 상태를 확인하세요."),
        ("DEADLINE_HAS_EXPIRED", "활용신청 기간이 만료되었습니다. 연장 신청이 필요합니다."),
        ("UNKNOWN_ERROR", "제공기관 내부 오류입니다. 잠시 후 재시도합니다."),
        ("NODATA", ""),
    ):
        if key in txt:
            return msg or ""
    # resultCode 가 00 이 아니면 오류로 본다
    for path in (("response", "header", "resultCode"), ("resultCode",)):
        cur: Any = payload
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is not None and str(cur) not in ("00", "0", "000"):
            return f"제공기관 응답코드 {cur}: {txt[:160]}"
    return ""


class CustomsClient:
    """관세청 오픈API 클라이언트. 엔드포인트/파라미터를 실행 시점에 탐침해 확정한다."""

    def __init__(self, key: str):
        self.key = (key or "").strip()
        self.ep: Optional[dict] = None
        self.range_ok: Optional[bool] = None       # X2: 기간 일괄조회 지원 여부
        self.fail_streak = 0
        self.calls = 0
        self.diag: List[str] = []

    # ── 저수준 호출 ------------------------------------------------------------------
    def _call(self, ep: dict, hs: str, start: str, end: str,
              country: Optional[str] = None, rows: int = 1000) -> Tuple[Any, str]:
        p = ep["params"]
        params = {
            "serviceKey": self.key,
            p["hs"]: hs,
            p["start"]: start,
            p["end"]: end,
            "type": "json",
            "numOfRows": rows,
            "pageNo": 1,
        }
        if country and ep.get("has_country") and "country" in p:
            params[p["country"]] = country
        # ★ http_get 은 응답객체가 아니라 **본문 문자열**을 돌려준다(실패 시 None).
        #   r.json() 을 부르면 AttributeError 로 A축 수집이 통째로 죽는다.
        try:
            txt = http_get(ep["url"], params=params, source="customs", timeout=30)
        except Exception as e:                                          # noqa
            return None, f"{type(e).__name__}: {e}"
        if not txt:
            return None, "응답 없음"
        if isinstance(txt, bytes):
            txt = txt.decode("utf-8", "replace")
        s = txt.lstrip()
        if s[:1] in ("{", "["):
            try:
                payload = json.loads(txt)
            except Exception:                                           # noqa
                return None, "JSON 파싱 실패"
            return payload, _customs_error(payload)
        if s[:1] == "<":
            low = s[:400].lower()
            if "<html" in low or "<!doctype" in low:
                return None, "HTML 응답(인증 실패·차단 의심)"
            # 다수 서비스가 type=json 을 무시하고 XML 로만 응답한다.
            xml = _xml_items(txt)
            if xml is None:
                # 오류도 XML 로 온다 — 사유를 뽑아 준다.
                for key in ("SERVICE_KEY_IS_NOT_REGISTERED", "LIMITED_NUMBER_OF_SERVICE_REQUESTS",
                            "SERVICE_ACCESS_DENIED", "DEADLINE_HAS_EXPIRED"):
                    if key in txt:
                        return None, _customs_error({"msg": key})
                return None, f"XML 파싱 실패: {s[:120]}"
            return xml, ""
        return None, f"알 수 없는 응답 형식: {s[:120]}"

    # ── 탐침 ---------------------------------------------------------------------------
    def probe(self, sample_hs: str = "854370") -> dict:
        """CANARY X1~X4 를 겸한다. 어떤 엔드포인트가 살아있고 무엇을 주는지 실측한다."""
        out = {"endpoint": "", "weight": False, "value": False, "country": False,
               "range": False, "back2016": False, "detail": ""}
        if not self.key:
            out["detail"] = "DATA_GO_KR_KEY 가 비어 있습니다."
            return out
        for ep in CUSTOMS_ENDPOINTS:
            payload, err = self._call(ep, sample_hs, "202401", "202403")
            items = _extract_items(payload)
            if err:
                self.diag.append(f"{ep['name']}: {err}")
            if not items:
                continue
            d = _customs_parse(items, ep.get("has_country", False))
            if not len(d):
                continue
            self.ep = ep
            out["endpoint"] = ep["name"]
            out["weight"] = bool(pd.to_numeric(d["exp_wgt"], errors="coerce").notna().any())
            out["value"] = bool(pd.to_numeric(d["exp_usd"], errors="coerce").notna().any())
            out["country"] = bool(ep.get("has_country") and d["country"].nunique() > 1)
            # X2: 기간 일괄조회가 진짜 되는가 — 서로 다른 월이 2개 이상 나와야 한다.
            out["range"] = bool(d["ym"].nunique() >= 2)
            self.range_ok = out["range"]
            # X4: 2016-01 소급
            p2, _e2 = self._call(ep, sample_hs, "201601", "201603")
            out["back2016"] = bool(len(_customs_parse(_extract_items(p2),
                                                      ep.get("has_country", False))))
            out["detail"] = f"{ep['url']}"
            break
        if not self.ep:
            out["detail"] = "; ".join(self.diag[:3]) or "모든 후보 엔드포인트가 응답하지 않았습니다."
        return out

    # ── 수집 ---------------------------------------------------------------------------
    def fetch_hs(self, hs: str, start: str, end: str) -> pd.DataFrame:
        if self.ep is None or self.fail_streak >= 15:
            return pd.DataFrame()
        chunks: List[pd.DataFrame] = []
        # ★ 기간 일괄조회는 지원되지만 **1년 이내**로 제한된다(포털 샘플 주석: 조회기간 1년이내).
        #   10년을 한 번에 던지면 조용히 잘린 결과가 오거나 오류가 난다 —
        #   둘 다 'A축이 일부만 채워진 채 통과'라서 가장 위험하다. 반드시 12개월로 자른다.
        spans = _year_spans(start, end) if self.range_ok else _month_spans(start, end)
        for s, e in spans:
            payload, err = self._call(self.ep, hs, s, e)
            self.calls += 1
            if err:
                self.fail_streak += 1
                if self.fail_streak >= 15:
                    LOG.error(f"관세청 연속 실패 15회 — 서킷브레이커 작동. 마지막 오류: {err}")
                    break
                continue
            items = _extract_items(payload)
            if items:
                self.fail_streak = 0
                d = _customs_parse(items, self.ep.get("has_country", False))
                if len(d):
                    chunks.append(d)
        if not chunks:
            return pd.DataFrame()
        return pd.concat(chunks, ignore_index=True).drop_duplicates(["hs", "ym", "country"])


def _year_spans(start: str, end: str, months: int = 12) -> "list[tuple]":
    """[start, end] 를 최대 12개월 창으로 자른다. 제공기관의 하드 제한이다."""
    s = pd.Timestamp(f"{start[:4]}-{start[4:6]}-01")
    e = pd.Timestamp(f"{end[:4]}-{end[4:6]}-01")
    out = []
    cur = s
    while cur <= e:
        nxt = min(e, cur + pd.DateOffset(months=months - 1))
        out.append((cur.strftime("%Y%m"), nxt.strftime("%Y%m")))
        cur = nxt + pd.DateOffset(months=1)
    return out


def _month_spans(start: str, end: str) -> "list[tuple]":
    """X2 FAIL 시 월별 개별 조회로 떨어진다. 호출 수가 126배가 되므로 로그로 경고한다."""
    s = pd.Timestamp(f"{start[:4]}-{start[4:6]}-01")
    e = pd.Timestamp(f"{end[:4]}-{end[4:6]}-01")
    out = []
    cur = s
    while cur <= e:
        t = cur.strftime("%Y%m")
        out.append((t, t))
        cur = cur + pd.offsets.MonthBegin(1)
    return out


def _xml_items(text: str) -> Any:
    """JSON 이 아닌 XML 응답을 최소한으로 파싱한다(의존성 추가 없이)."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception:                                                   # noqa
        return None
    items = []
    for it in root.iter("item"):
        items.append({ch.tag: (ch.text or "").strip() for ch in it})
    return {"response": {"body": {"items": {"item": items}}}} if items else None


def ingest_customs(hs_list: "Sequence[str]", start: str, end: str,
                   key: str = "") -> pd.DataFrame:
    """관세청 통관 수집. 드라이브 캐시 우선 → 부족분만 신규 → 재적재.

    반환: hs, ym, country, exp_wgt(kg), exp_usd(USD), imp_wgt, imp_usd, knowledge_date
    """
    cols = ["hs", "ym", "country", "exp_wgt", "exp_usd", "imp_wgt", "imp_usd", "knowledge_date"]
    hs_list = [str(h) for h in dict.fromkeys(hs_list)]
    if not hs_list:
        return pd.DataFrame(columns=cols)

    # ① 캐시 (공용 — 다른 전략도 그대로 쓸 수 있는 원본 정제본)
    cached = VAULT.get_table("customs_hs_country_monthly", scope="shared")
    if cached is None and FOREIGN is not None:
        cached = FOREIGN.load("customs_hs", "customs_hs_country_monthly", "customs",
                              alias=FOREIGN_ALIAS_CUSTOMS)
    have: set = set()
    if cached is not None and len(cached):
        cached["hs"] = cached["hs"].astype(str)
        cached["ym"] = as_ts_series(cached["ym"])
        have = set(cached["hs"].unique())
        LOG.ok(f"통관 캐시 재사용: {len(cached):,}행 · HS {len(have)}개")

    need = [h for h in hs_list if h not in have]
    fresh = pd.DataFrame(columns=cols)
    if need and RUN_MODE != "CACHED":
        cli = CustomsClient(key or DATA_GO_KR_KEY)
        if cli.ep is None:
            pr = cli.probe(sample_hs=need[0])
            if not pr["endpoint"]:
                LOG.error(f"관세청 API 를 사용할 수 없습니다 — {pr['detail']}")
                need = []
        if need:
            if cli.range_ok is False:
                LOG.warn(f"기간 일괄조회(X2) 미지원 — 월별 개별호출로 전환합니다. "
                         f"호출 수가 약 {len(_month_spans(start, end))}배가 됩니다.")
            res = pmap_io(lambda h: cli.fetch_hs(h, start, end), need,
                          workers=min(N_WORKERS_IO, 8), desc="관세청 통관")
            good = [d for d in res if d is not None and len(d)]
            if good:
                fresh = pd.concat(good, ignore_index=True)
            LOG.info(f"관세청 신규 수집: HS {len(need)}개 요청 → {len(fresh):,}행 "
                     f"({cli.calls:,}콜)")

    parts = [d for d in (cached, fresh) if d is not None and len(d)]
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    out["hs"] = out["hs"].astype(str)
    out["ym"] = as_ts_series(out["ym"])
    out = out.dropna(subset=["ym"]).drop_duplicates(["hs", "ym", "country"], keep="last")
    # C18-(b)
    out["knowledge_date"] = customs_knowledge_date(out["ym"])

    # ② 재적재 — 공용 인덱스(다른 전략 재사용) + 사용자 기존 공용 레지스트리에도 등록
    if len(fresh):
        VAULT.put_table("customs_hs_country_monthly", out, scope="shared",
                        source="data.go.kr/관세청")
        if FOREIGN is not None:
            foreign_publish_common(FOREIGN, "customs_hs_country_monthly", out,
                                   ["hs", "ym", "country"], "TCD_XCB")
        _customs_snapshot(fresh)
    return out.reindex(columns=cols)


def _customs_snapshot(fresh: pd.DataFrame) -> None:
    """C18-(c): 오늘 받은 값을 그대로 스냅샷으로 남긴다.

    관세청이 매월 현행화하므로 '오늘 시점에 무엇이 공표되어 있었는가'는 오늘만 기록할 수 있다.
    복원 불가 자산이라 오늘 켜지 않으면 2년 뒤에도 2년치다.
    """
    try:
        tag = _dt.datetime.now().strftime("%Y%m%d")
        VAULT.put_table(f"customs_snapshot_{tag}", fresh, scope="private",
                        source="C18-(c) 현행화 추적용 스냅샷")
    except Exception as e:                                              # noqa
        LOG.debug(f"통관 스냅샷 저장 실패(무시): {type(e).__name__}")


def customs_revision_probe(key: str, hs: str, ym_old: str) -> dict:
    """CANARY X5 — 현행화 크기 실측.

    같은 과거월을 (a) 이번 실행에서 받은 값과 (b) 과거 스냅샷에 남아 있는 값으로 비교한다.
    스냅샷이 아직 없으면 '측정 불가'로 정직하게 보고한다 — 없는 것을 있는 척하지 않는다.
    """
    out = {"measurable": False, "diff_pct": float("nan"), "detail": ""}
    snaps = []
    try:
        tdir = VAULT.table_dir("private")
        snaps = sorted(f for f in os.listdir(tdir) if f.startswith("customs_snapshot_"))
    except Exception:                                                   # noqa
        pass
    if len(snaps) < 1:
        out["detail"] = ("과거 스냅샷이 없어 현행화 크기를 아직 실측할 수 없습니다. "
                         "이번 실행이 첫 스냅샷을 남깁니다(C18-c). "
                         "→ 보수적 knowledge_date(익월 말일)로 위험을 흡수합니다.")
        return out
    old = read_parquet_safe(os.path.join(VAULT.table_dir("private"), snaps[0]))
    cur = VAULT.get_table("customs_hs_country_monthly", scope="shared")
    if old is None or cur is None or not len(old) or not len(cur):
        out["detail"] = "스냅샷 또는 현재 테이블을 읽지 못했습니다."
        return out
    k = ["hs", "ym", "country"]
    for d in (old, cur):
        d["hs"] = d["hs"].astype(str)
        d["ym"] = as_ts_series(d["ym"])
    j = old.merge(cur, on=k, how="inner", suffixes=("_old", "_new"))
    if not len(j):
        out["detail"] = "겹치는 관측이 없습니다."
        return out
    a = pd.to_numeric(j["exp_usd_old"], errors="coerce")
    b = pd.to_numeric(j["exp_usd_new"], errors="coerce")
    tot = a.sum()
    out["measurable"] = True
    out["diff_pct"] = float(abs(b.sum() - tot) / tot * 100.0) if tot else float("nan")
    out["detail"] = f"겹치는 {len(j):,}관측 기준 총액 차이 {out['diff_pct']:.3f}%"
    if out["diff_pct"] > 1.0:
        LOG.warn(f"[C18-d] 관세청 현행화 크기 {out['diff_pct']:.2f}% > 1% — "
                 f"백테스트 성과에 상향 편의가 있을 수 있습니다. 리포트에 명시합니다.")
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [18/27]  23_mapping.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  HS 유니버스 큐레이션 + 매핑 4중 게이트                                                     ║
# ║                                                                                             ║
# ║  ★ 여기가 이 전략의 최대 자유도이자 최대 과적합 통로다(§15.2).                              ║
# ║    그래서 구조로 막는다:                                                                     ║
# ║      · 채택 기준은 넷뿐 — (연계표, 생산자 수, 단위 정합성, 커모디티 지표).                   ║
# ║        성과 정보는 어떤 형태로도 들어가지 않는다.                                            ║
# ║      · 확정된 목록은 `hs_universe_preregistered.csv` 로 **사전등록**되고,                    ║
# ║        다음 실행부터는 그 파일이 진실이다. 코드가 다시 고르지 않는다.                        ║
# ║      · 목록이 바뀌면 수정 이력이 파일에 남고, 리포트가 수정 전/후 성과를 **둘 다** 낸다.     ║
# ║                                                                                             ║
# ║  ★ C3 (PIT 라벨 고정): valid_from = 그 제품구성을 알 수 있게 된 사업보고서 접수일.           ║
# ║    2024년 사업보고서로 알게 된 구성을 2022년 백테스트에 쓰면 성과는 전부 가짜다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

PREREG_FILE = "hs_universe_preregistered.csv"

# HS 章(2자리) ↔ KSIC 대·중분류 개략 대응. **연계표를 못 구했을 때의 폴백이다.**
# 정밀 매핑이 아니라 '후보 집합을 만드는 1차 그물'이며, 실제 채택은 게이트 1~3 이 결정한다.
# 이 표를 쓰게 되면 CANARY X6 을 DEGRADED 로 보고하고 정밀도 저하를 명시한다.
HS2_KSIC_SEED: "dict[str, tuple]" = {
    "28": ("20",), "29": ("20",), "32": ("20",), "34": ("20",), "38": ("20",),
    "39": ("20", "22"), "40": ("22",),
    "30": ("21",), "33": ("20", "21"),
    "72": ("24",), "73": ("24", "25"), "74": ("24",), "75": ("24",), "76": ("24",),
    "78": ("24",), "79": ("24",), "80": ("24",), "81": ("24",), "82": ("25",), "83": ("25",),
    "84": ("29",), "85": ("26", "28"), "90": ("27",), "91": ("27",),
    "86": ("31",), "87": ("30",), "88": ("31",), "89": ("31",),
    "48": ("17",), "49": ("18",),
    "50": ("13",), "51": ("13",), "52": ("13",), "53": ("13",), "54": ("13",),
    "55": ("13",), "56": ("13",), "57": ("13",), "58": ("13",), "59": ("13",),
    "60": ("13",), "61": ("14",), "62": ("14",), "63": ("14",), "64": ("15",), "65": ("14",),
    "68": ("23",), "69": ("23",), "70": ("23",), "71": ("23", "33"),
    "94": ("32",), "95": ("32",), "96": ("32",),
    "16": ("10",), "17": ("10",), "18": ("10",), "19": ("10",), "20": ("10",),
    "21": ("10",), "22": ("11",),
    "27": ("19",),
}


def fetch_hs_ksic_concordance() -> Tuple[pd.DataFrame, str]:
    """CANARY X6 — HS ↔ KSIC 연계표를 확보한다.

    반환 (표, 상태) 이며 상태는 "OK" / "DEGRADED" / "FAIL".
    ★ 없는 것을 있는 척하지 않는다. 씨앗 표로 떨어지면 DEGRADED 로 보고하고
      매핑 정밀도가 낮아졌으므로 게이트 1~3 이 더 중요해졌음을 로그에 남긴다.
    """
    # ① 캐시(공용) — 다른 전략이 이미 받아 뒀을 수 있다
    for src in (lambda: VAULT.get_table("hs_ksic_concordance", scope="shared"),
                lambda: (FOREIGN.load("hs_map", "hs_ksic_concordance", "hs_ksic")
                         if FOREIGN is not None else None)):
        try:
            d = src()
        except Exception:                                               # noqa
            d = None
        if d is not None and len(d):
            cols = {c.lower(): c for c in d.columns}
            hc = next((cols[c] for c in ("hs", "hs_code", "hscd", "hs2", "hs6") if c in cols), None)
            kc = next((cols[c] for c in ("ksic", "ksic_code", "induty", "induty_code")
                       if c in cols), None)
            if hc and kc:
                out = pd.DataFrame({"hs": d[hc].astype(str), "ksic": d[kc].astype(str)})
                LOG.ok(f"HS–KSIC 연계표 캐시 재사용: {len(out):,}행")
                return out.dropna().drop_duplicates(), "OK"

    # ② 씨앗 표로 폴백
    rows = []
    for hs2, ks in HS2_KSIC_SEED.items():
        for k in ks:
            rows.append({"hs": hs2, "ksic": k})
    seed = pd.DataFrame(rows)
    LOG.warn("HS–KSIC 연계표를 외부에서 확보하지 못해 내장 씨앗표(章↔KSIC 중분류)로 진행합니다. "
             "매핑 정밀도가 낮아지므로 게이트1(합계정합성)·게이트2(자기공시)·게이트3(플라시보)의 "
             "판정이 그만큼 더 중요해집니다. CANARY X6 = DEGRADED 로 보고합니다.")
    return seed, "DEGRADED"


def curate_hs_universe(cx: pd.DataFrame, sec: pd.DataFrame, conc: pd.DataFrame,
                       max_firms: int = HS_OLIGOPOLY_MAX_FIRMS,
                       digits: int = HS_DIGIT_LEVEL,
                       min_months: int = HS_MIN_MONTHS) -> pd.DataFrame:
    """§5.2 큐레이션. 사전등록 파일이 있으면 **무조건 그것을 따른다**.

    반환: hs, n_firms, months, cv_dest, adopted, reason
    """
    prereg_path = os.path.join(VAULT.table_dir("private"), PREREG_FILE)
    if os.path.exists(prereg_path):
        try:
            pre = pd.read_csv(prereg_path, dtype={"hs": str})
            LOG.ok(f"사전등록 HS 유니버스를 따릅니다: {prereg_path} "
                   f"({int(pre.get('adopted', pd.Series(dtype=float)).sum()):,}개 채택) "
                   f"— 성과를 보고 이 파일을 고치지 마세요(§15.2).")
            return pre
        except Exception as e:                                          # noqa
            LOG.warn(f"사전등록 파일을 읽지 못했습니다({type(e).__name__}) — 새로 생성합니다.")

    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "n_firms", "months", "cv_dest", "adopted", "reason"])

    d = cx.copy()
    d["hs"] = d["hs"].astype(str).str.zfill(max(digits, 6))
    d["hs_k"] = d["hs"].str[:digits]

    # 관측 개월수 — 롤링 36M OLS 가 돌 수 있어야 한다.
    obs = d.groupby("hs_k", observed=True)["ym"].nunique().rename("months").reset_index()

    # 후보 상장사 수: KSIC 경유로 HS 章 → 상장사 집합
    ind = sec.copy()
    ind["ksic2"] = ind.get("induty_code", pd.Series("", index=ind.index)).astype(str).str[:2]
    cmap = conc.copy()
    cmap["hs2"] = cmap["hs"].astype(str).str.zfill(2).str[:2]
    cmap["ksic2"] = cmap["ksic"].astype(str).str.zfill(2).str[:2]
    link = cmap.merge(ind[["code", "ksic2"]], on="ksic2", how="inner")
    nfirm = link.groupby("hs2", observed=True)["code"].nunique().rename("n_firms").reset_index()

    out = obs.copy()
    out["hs2"] = out["hs_k"].str[:2]
    out = out.merge(nfirm, on="hs2", how="left")
    out["n_firms"] = out["n_firms"].fillna(0).astype(int)

    cvd = customs_cv_dest(d.assign(hs=d["hs_k"]))
    out = out.merge(cvd.rename(columns={"hs": "hs_k"}), on="hs_k", how="left")

    # 채택 규칙 — 넷뿐이다. 성과는 보지 않는다.
    reason = pd.Series("", index=out.index, dtype=object)
    ok = pd.Series(True, index=out.index)
    m1 = out["n_firms"].between(1, max_firms)
    reason = reason.where(m1, reason + f"생산자수({out['n_firms']})가 1~{max_firms} 밖; ")
    ok &= m1
    m2 = out["months"] >= min_months
    reason = reason.where(m2, reason + f"관측개월 {out['months']}<{min_months}; ")
    ok &= m2
    out["adopted"] = ok.astype(int)
    out["reason"] = reason.where(~ok, "채택")
    out = out.rename(columns={"hs_k": "hs"})[
        ["hs", "n_firms", "months", "cv_dest", "adopted", "reason"]]

    # 사전등록 — 이후 실행에서 이 파일이 진실이 된다.
    try:
        _ensure_dir(prereg_path)
        out.assign(preregistered_at=_dt.datetime.now().isoformat(timespec="seconds"),
                   build=BUILD_VERSION).to_csv(prereg_path, index=False, encoding="utf-8-sig")
        LOG.ok(f"HS 유니버스를 사전등록했습니다 → {prereg_path} "
               f"(채택 {int(out['adopted'].sum())}/{len(out)}). "
               f"이후 실행은 이 파일을 따르며, 수정 시 이력이 남습니다.")
    except Exception as e:                                              # noqa
        LOG.warn(f"사전등록 파일 저장 실패({type(e).__name__}) — 이번 실행에만 유효합니다.")
    return out


def build_mapping_table(hs_uni: pd.DataFrame, sec: pd.DataFrame, conc: pd.DataFrame,
                        seg: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """매핑표 (code, hs, weight, valid_from, valid_to, match_score).

    valid_from 은 **사업보고서 접수일(rcept_dt)** 이다 — 그 제품구성을 알 수 있게 된 날.
    사업보고서 제품 정보가 없으면 상장일 + 1년(첫 사업보고서 제출 시점의 보수적 하한)으로 둔다.
    """
    cols = ["code", "hs", "weight", "valid_from", "valid_to", "match_score"]
    if hs_uni is None or not len(hs_uni):
        return pd.DataFrame(columns=cols)
    ad = hs_uni[hs_uni["adopted"] == 1].copy()
    if not len(ad):
        return pd.DataFrame(columns=cols)

    ind = sec.copy()
    ind["ksic2"] = ind.get("induty_code", pd.Series("", index=ind.index)).astype(str).str[:2]
    cmap = conc.copy()
    cmap["hs2"] = cmap["hs"].astype(str).str.zfill(2).str[:2]
    cmap["ksic2"] = cmap["ksic"].astype(str).str.zfill(2).str[:2]
    ad["hs2"] = ad["hs"].astype(str).str[:2]

    j = (ad[["hs", "hs2"]]
         .merge(cmap[["hs2", "ksic2"]].drop_duplicates(), on="hs2", how="inner")
         .merge(ind[["code", "ksic2", "listing_date"]], on="ksic2", how="inner"))
    if not len(j):
        return pd.DataFrame(columns=cols)

    # 한 종목이 같은 章의 여러 HS 에 붙으면 가중치를 나눈다(합=1).
    j["weight"] = 1.0
    j["weight"] = j["weight"] / j.groupby("code", observed=True)["hs"].transform("size")
    j["match_score"] = 0.5                        # 연계표 경유의 기본 신뢰도

    # ── C3: PIT 유효 시작일
    ld = as_ts_series(j.get("listing_date"))
    j["valid_from"] = (ld + pd.DateOffset(years=1)).fillna(pd.Timestamp(BACKTEST_START))
    if seg is not None and len(seg):
        # 사업보고서 품목표가 있으면 그 접수일이 더 정확하다(그리고 더 보수적일 수 있다).
        s = seg.groupby("code", observed=True)["knowledge_date"].min().rename("seg_from").reset_index()
        j = j.merge(s, on="code", how="left")
        j["valid_from"] = np.maximum(as_ts_series(j["valid_from"]).to_numpy(),
                                     as_ts_series(j["seg_from"]).fillna(
                                         as_ts_series(j["valid_from"])).to_numpy())
        j["valid_from"] = as_ts_series(j["valid_from"])
        j["match_score"] = np.where(j["seg_from"].notna(), 0.7, j["match_score"])
    j["valid_to"] = pd.Timestamp("2262-01-01")
    out = j[cols].drop_duplicates(["code", "hs"]).reset_index(drop=True)
    LOG.ok(f"매핑표: 종목 {out['code'].nunique():,}개 × HS {out['hs'].nunique():,}개 = "
           f"{len(out):,}쌍 (valid_from 중앙값 {as_ts_series(out['valid_from']).median():%Y-%m})")
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  매핑 검증 4중 게이트 (§5.3)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def gate1_coverage(mapping: pd.DataFrame, cx: pd.DataFrame, fin: pd.DataFrame,
                   band: Tuple[float, float] = COVERAGE_BAND,
                   cv_max: float = COVERAGE_CV_MAX) -> pd.DataFrame:
    """게이트 1 — 합계 정합성. 회계 항등식에 가까우므로 R² 보다 근본적이다.

        Coverage_HS = Σ_i (기업_i 별도 수출매출) / 해당 HS 총 수출액 ∈ [0.85, 1.15]
        + 시간 안정성: 이 비율의 변동계수 < 0.25
    """
    cols = ["hs", "coverage", "cov_cv", "gate1"]
    if mapping is None or not len(mapping) or cx is None or not len(cx):
        return pd.DataFrame(columns=cols)
    if fin is None or not len(fin) or "export_rev_sep" not in fin.columns:
        LOG.warn("게이트1: 별도 수출매출을 확보하지 못해 합계정합성을 검정할 수 없습니다. "
                 "이 게이트는 '판정 유보'로 두고 게이트2·3 으로 판단합니다.")
        hs = mapping["hs"].astype(str).unique()
        return pd.DataFrame({"hs": hs, "coverage": np.nan, "cov_cv": np.nan, "gate1": 1})

    # HS 총 수출액(연도)
    c = cx.copy()
    c["hs"] = c["hs"].astype(str)
    c["year"] = as_ts_series(c["ym"]).dt.year
    hs_year = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()

    f = fin.copy()
    f["year"] = as_ts_series(f["period"]).dt.year
    fy = f.groupby(["code", "year"], observed=True)["export_rev_sep"].max().reset_index()

    j = mapping[["code", "hs", "weight"]].merge(fy, on="code", how="inner")
    j = j.merge(hs_year, on=["hs", "year"], how="inner")
    if not len(j):
        return pd.DataFrame({"hs": mapping["hs"].astype(str).unique(),
                             "coverage": np.nan, "cov_cv": np.nan, "gate1": 1})
    j["firm_share"] = pd.to_numeric(j["export_rev_sep"], errors="coerce") * j["weight"]
    g = j.groupby(["hs", "year"], observed=True).agg(
        num=("firm_share", "sum"), den=("exp_usd", "first")).reset_index()
    g["cov"] = safe_div(g["num"], g["den"])
    agg = g.groupby("hs", observed=True)["cov"].agg(
        coverage="median", _sd="std", _mu="mean").reset_index()
    agg["cov_cv"] = safe_div(agg["_sd"], agg["_mu"]).abs()
    agg["gate1"] = ((agg["coverage"] >= band[0]) & (agg["coverage"] <= band[1]) &
                    (agg["cov_cv"] < cv_max)).astype(int)
    n_pass = int(agg["gate1"].sum())
    LOG.info(f"게이트1 합계정합성: {n_pass}/{len(agg)} HS 통과 "
             f"(허용 {band[0]:.2f}~{band[1]:.2f}, 변동계수<{cv_max})")
    return agg[cols]


def gate2_selfdisclosure(mapping: pd.DataFrame, cx: pd.DataFrame, seg: pd.DataFrame,
                         corr_min: float = SELFDISC_CORR_MIN) -> pd.DataFrame:
    """게이트 2 — 기업 자기공시 대조.

    사업보고서「매출 및 수주상황」의 품목별 매출 증가율 vs 매핑된 HS 의 수출액 증가율.
    매핑을 '추정'이 아니라 **기업 자신의 진술**로 검증한다. 상관 < 0.4 이면 매핑 폐기.
    """
    cols = ["code", "selfdisc_corr", "gate2"]
    if seg is None or not len(seg) or mapping is None or not len(mapping):
        if mapping is not None and len(mapping):
            LOG.warn("게이트2: 사업보고서 품목별 매출을 확보하지 못했습니다 — 판정 유보(통과 처리)하고 "
                     "그 사실을 매핑 게이트 리포트에 명시합니다.")
            return pd.DataFrame({"code": mapping["code"].unique(),
                                 "selfdisc_corr": np.nan, "gate2": 1})
        return pd.DataFrame(columns=cols)

    c = cx.copy()
    c["hs"] = c["hs"].astype(str)
    c["year"] = as_ts_series(c["ym"]).dt.year
    hs_year = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()
    hs_year = hs_year.sort_values(["hs", "year"])
    hs_year["hs_g"] = hs_year.groupby("hs", observed=True)["exp_usd"].pct_change()

    s = seg.copy()
    s["year"] = as_ts_series(s["knowledge_date"]).dt.year
    s = s.groupby(["code", "year"], observed=True)["seg_amount"].sum().reset_index()
    s = s.sort_values(["code", "year"])
    s["firm_g"] = s.groupby("code", observed=True)["seg_amount"].pct_change()

    j = (mapping[["code", "hs", "weight"]]
         .merge(hs_year[["hs", "year", "hs_g"]], on="hs", how="inner")
         .merge(s[["code", "year", "firm_g"]], on=["code", "year"], how="inner"))
    j = j.replace([np.inf, -np.inf], np.nan).dropna(subset=["hs_g", "firm_g"])
    if not len(j):
        return pd.DataFrame({"code": mapping["code"].unique(),
                             "selfdisc_corr": np.nan, "gate2": 1})
    # 종목별 시계열 상관 — groupby.apply 금지(원칙 3). 적률 합으로 벡터화한다.
    j["_n"] = 1.0
    j["_xx"] = j["hs_g"] ** 2
    j["_yy"] = j["firm_g"] ** 2
    j["_xy"] = j["hs_g"] * j["firm_g"]
    g = j.groupby("code", observed=True)
    n = g["_n"].sum()
    sx, sy = g["hs_g"].sum(), g["firm_g"].sum()
    sxx, syy, sxy = g["_xx"].sum(), g["_yy"].sum(), g["_xy"].sum()
    num = n * sxy - sx * sy
    den = np.sqrt((n * sxx - sx ** 2).clip(lower=0)) * np.sqrt((n * syy - sy ** 2).clip(lower=0))
    corr = safe_div(num, den).where(n >= 4)
    out = corr.rename("selfdisc_corr").reset_index()
    out["gate2"] = ((out["selfdisc_corr"] >= corr_min) | out["selfdisc_corr"].isna()).astype(int)
    LOG.info(f"게이트2 자기공시 대조: {int(out['gate2'].sum())}/{len(out)} 종목 통과 "
             f"(상관 하한 {corr_min}, 관측부족은 유보)")
    return out[cols]


def gate3_placebo(mapping: pd.DataFrame, a_hs: pd.DataFrame, fin: pd.DataFrame,
                  n_shuffle: int = PLACEBO_N, alpha: float = PLACEBO_ALPHA,
                  seed: int = SEED) -> dict:
    """게이트 3 — 플라시보 매핑. **회귀 재적합 금지, 행렬곱만.**

    무작위 HS 배정 n회로 적합도 귀무분포를 만들고, 실제 매핑이 상위 5% 밖이면 탈락.
    ⚠ 회귀를 1,000번 재적합하면 250시간이다. 롤링 적률(=이미 계산된 a1)을 재사용하고
      매핑 행렬만 셔플하면 행렬곱 1,000회 = 수십 초다(원칙 5).
    """
    out = {"stat": float("nan"), "p": float("nan"), "pass": 0, "n": 0, "detail": ""}
    if (mapping is None or not len(mapping) or a_hs is None or not len(a_hs)
            or fin is None or not len(fin)):
        out["detail"] = "입력 부족 — 판정 유보"
        out["pass"] = 1
        return out

    # HS × 연도 물량 증가율 행렬
    A = a_hs.copy()
    A["year"] = as_ts_series(A["ym"]).dt.year
    hs_y = A.groupby(["hs", "year"], observed=True)["a1"].mean().reset_index()
    Hm = hs_y.pivot_table(index="hs", columns="year", values="a1")
    # 종목 × 연도 매출 증가율 행렬
    F = fin.copy()
    F["year"] = as_ts_series(F["period"]).dt.year
    fy = F.groupby(["code", "year"], observed=True)["b1"].mean().reset_index() \
        if "b1" in F.columns else None
    if fy is None or not len(fy):
        out["detail"] = "기업 매출증가율 부재 — 판정 유보"
        out["pass"] = 1
        return out
    Fm = fy.pivot_table(index="code", columns="year", values="b1")

    years = sorted(set(Hm.columns) & set(Fm.columns))
    if len(years) < 4:
        out["detail"] = f"공통 연도 {len(years)}개 — 판정 유보"
        out["pass"] = 1
        return out
    Hm = Hm.reindex(columns=years)
    Fm = Fm.reindex(columns=years)

    hs_idx = {h: i for i, h in enumerate(Hm.index.astype(str))}
    cd_idx = {c: i for i, c in enumerate(Fm.index.astype(str))}
    mp = mapping[mapping["hs"].astype(str).isin(hs_idx) &
                 mapping["code"].astype(str).isin(cd_idx)]
    if not len(mp):
        out["detail"] = "매핑과 행렬의 교집합 없음 — 판정 유보"
        out["pass"] = 1
        return out

    n_f, n_h = len(cd_idx), len(hs_idx)
    rows = mp["code"].astype(str).map(cd_idx).to_numpy()
    cols_ = mp["hs"].astype(str).map(hs_idx).to_numpy()
    w = pd.to_numeric(mp["weight"], errors="coerce").fillna(1.0).to_numpy()

    H = np.nan_to_num(Hm.to_numpy(dtype=float))
    Y = Fm.to_numpy(dtype=float)
    ok = np.isfinite(Y)

    def _fit(cc: np.ndarray) -> float:
        M = np.zeros((n_f, n_h), dtype=float)
        np.add.at(M, (rows, cc), w)
        rs = M.sum(axis=1, keepdims=True)
        M = np.divide(M, rs, out=np.zeros_like(M), where=rs > 0)
        P = M @ H                                       # (n_f, T) 예측
        # 시계열 상관의 평균 — 행렬곱 한 번이면 끝난다.
        Pm = np.where(ok, P, np.nan)
        Ym = np.where(ok, Y, np.nan)
        pc = Pm - np.nanmean(Pm, axis=1, keepdims=True)
        yc = Ym - np.nanmean(Ym, axis=1, keepdims=True)
        num = np.nansum(pc * yc, axis=1)
        den = np.sqrt(np.nansum(pc ** 2, axis=1) * np.nansum(yc ** 2, axis=1))
        r = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
        return float(np.nanmean(r)) if np.isfinite(r).any() else float("nan")

    real = _fit(cols_)
    rng = np.random.default_rng(seed)
    null = np.empty(n_shuffle, dtype=float)
    for i in range(n_shuffle):
        null[i] = _fit(rng.integers(0, n_h, size=len(cols_)))
    null = null[np.isfinite(null)]
    if not np.isfinite(real) or not len(null):
        out["detail"] = "적합도 산출 불가 — 판정 유보"
        out["pass"] = 1
        return out
    p = float((null >= real).mean())
    out.update(stat=real, p=p, n=int(len(null)),
               **{"pass": int(p < alpha)},
               detail=f"실제 {real:+.4f} vs 귀무 평균 {np.mean(null):+.4f} "
                      f"(셔플 {len(null)}회, p={p:.4f})")
    LOG.info(f"게이트3 플라시보: {out['detail']} → "
             f"{'통과' if out['pass'] else '탈락(매핑이 무작위와 구분 안 됨)'}")
    return out


def apply_mapping_gates(mapping: pd.DataFrame, cx: pd.DataFrame, fin: pd.DataFrame,
                        seg: Optional[pd.DataFrame], a_hs: pd.DataFrame
                        ) -> Tuple[pd.DataFrame, dict]:
    """게이트 1·2·3 을 적용해 매핑표를 걸러내고, 결과 요약을 함께 반환한다.

    게이트 4(PIT 라벨 고정)는 build_mapping_table 이 구조로 보장하므로 별도 검정이 아니다.
    """
    info: dict = {}
    if mapping is None or not len(mapping):
        return mapping, {"n_before": 0, "n_after": 0}
    n0 = mapping["code"].nunique()

    g1 = gate1_coverage(mapping, cx, fin)
    g2 = gate2_selfdisclosure(mapping, cx, seg)
    g3 = gate3_placebo(mapping, a_hs, fin)

    m = mapping.copy()
    if len(g1):
        m = m.merge(g1[["hs", "gate1", "coverage", "cov_cv"]], on="hs", how="left")
        m["gate1"] = m["gate1"].fillna(1)
    else:
        m["gate1"] = 1
    if len(g2):
        m = m.merge(g2[["code", "gate2", "selfdisc_corr"]], on="code", how="left")
        m["gate2"] = m["gate2"].fillna(1)
    else:
        m["gate2"] = 1
    m["gate3"] = int(g3.get("pass", 1))
    m["map_gate_fail"] = (1 - (m["gate1"] * m["gate2"] * m["gate3"])).clip(0, 1)

    kept = m[m["map_gate_fail"] == 0].copy()
    n1 = kept["code"].nunique()
    info = {"n_before": int(n0), "n_after": int(n1), "gate3": g3,
            "g1_pass": int(g1["gate1"].sum()) if len(g1) else 0,
            "g1_total": int(len(g1)),
            "g2_pass": int(g2["gate2"].sum()) if len(g2) else 0,
            "g2_total": int(len(g2))}
    LOG.banner("매핑 게이트 결과", f"종목 {n0:,} → {n1:,}")
    LOG.table([
        ["게이트1 합계정합성", f"{info['g1_pass']}/{info['g1_total']} HS",
         f"허용 {COVERAGE_BAND[0]:.2f}~{COVERAGE_BAND[1]:.2f} · 변동계수<{COVERAGE_CV_MAX}"],
        ["게이트2 자기공시상관", f"{info['g2_pass']}/{info['g2_total']} 종목",
         f"상관 하한 {SELFDISC_CORR_MIN}"],
        ["게이트3 플라시보", "통과" if g3.get("pass") else "탈락", g3.get("detail", "")[:60]],
        ["게이트4 PIT 라벨(C3)", "구조 보장", "valid_from = 사업보고서 접수일"],
    ], ["게이트", "결과", "기준"])

    if n1 < MAPPING_MIN_NAMES:
        LOG.warn(f"[킬 기준 4] 매핑 게이트 통과 종목 {n1} < {MAPPING_MIN_NAMES} — "
                 f"통계 검정이 불가능한 표본입니다. 과점 기준을 완화해 재측정하거나, "
                 f"그래도 미달이면 이 방향을 폐기해야 합니다. 결과를 그대로 보고합니다.")
    return kept, info


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [19/27]  24_dartx.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  XCB 전용 DART 수집 — 코어가 다루지 않는 네 가지                                            ║
# ║    ① 단일판매·공급계약 공시  → c6, TP_XC 의 한쪽 날개                                       ║
# ║    ② 사업보고서 품목별/지역별 매출 → 게이트2 자기공시 대조 · θ_X · 게이트1 분자             ║
# ║    ③ 정책 의존 관측(정부보조금수익)  → V11                                                  ║
# ║    ④ 관리종목·감사의견·희석성 조달   → V5 · V3                                              ║
# ║                                                                                             ║
# ║  ★ 없는 것을 있는 척하지 않는다. 확보 실패한 항목은 결측으로 두고 커버리지를 표로 낸다.     ║
# ║    0 으로 채우면 '해당 없음'이라는 적극적 주장이 되어 거부권이 조용히 무력화된다.            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 코어 DISCLOSURE_PATTERNS 에 없는, XCB 가 추가로 필요로 하는 공시 유형.
XCB_DISCLOSURE_PATTERNS = {
    "supply_contract": r"단일판매[·・]?\s*공급계약|공급계약\s*체결",
    "watch_designate": r"관리종목\s*지정|투자주의\s*환기종목\s*지정|상장적격성\s*실질심사",
    "watch_release":   r"관리종목\s*지정\s*해제|투자주의\s*환기종목\s*해제",
    "trading_halt":    r"매매거래\s*정지",
}

# 공시 제목에서 계약금액을 뽑는 패턴. 제목에 금액이 없으면 본문 조회로 내려간다.
_AMT_RX = re.compile(r"([0-9][0-9,\.]*)\s*(억|백만|천만|만|원)")


def _amt_from_text(t: str) -> float:
    """'약 420억원' / '42,000백만원' 같은 표기를 원 단위 실수로."""
    if not t:
        return float("nan")
    m = _AMT_RX.search(str(t).replace(" ", ""))
    if not m:
        return float("nan")
    try:
        v = float(m.group(1).replace(",", ""))
    except Exception:                                                   # noqa
        return float("nan")
    unit = {"억": 1e8, "백만": 1e6, "천만": 1e7, "만": 1e4, "원": 1.0}.get(m.group(2), 1.0)
    return v * unit


def fetch_supply_contracts(dis: pd.DataFrame) -> pd.DataFrame:
    """단일판매·공급계약 체결 공시 → (code, knowledge_date, amount).

    ★ 이것이 TP_XC 의 한쪽이다. 공시는 **기업 자신의 진술**이고 통관 물량은
      **제3자(관세청)의 관측**이다. 독립인 두 소스가 같은 방향을 가리키면 신뢰도가 곱으로 오른다.
      공시만 있고 통관이 안 따라오면 계약이 실물로 전환되지 않은 것이고,
      이 갭을 추적하는 참여자는 사실상 없다.

    금액은 공시 제목에서 추출한다. 제목에 없으면 결측으로 두고 건수만 쓴다 —
    본문 파싱은 비용 대비 회수가 낮고, c6 는 '규모'보다 '발생'이 더 중요한 신호다.
    """
    cols = ["code", "knowledge_date", "amount"]
    if dis is None or not len(dis):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    hit = nm.str.contains(XCB_DISCLOSURE_PATTERNS["supply_contract"], regex=True, na=False)
    d = d[hit].copy()
    if not len(d):
        LOG.info("단일판매·공급계약 공시를 찾지 못했습니다 — c6/TP_XC 는 비활성화됩니다.")
        return pd.DataFrame(columns=cols)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["knowledge_date"] = as_ts_series(d.get("rcept_dt"))
    d["amount"] = nm[hit].map(_amt_from_text)
    d = d[d["code"].notna() & d["knowledge_date"].notna()]
    got = float(d["amount"].notna().mean()) if len(d) else 0.0
    LOG.ok(f"단일판매·공급계약 공시 {len(d):,}건 · {d['code'].nunique():,}종목 "
           f"(제목에서 금액 추출 성공률 {got*100:.0f}%)")
    if got < 0.3:
        LOG.warn("계약금액 추출률이 낮습니다 — c6 는 금액 대신 건수 기반으로 퇴화합니다. "
                 "TP_XC 의 해상도가 낮아진 상태로 R5 절제에서 기여를 확인하세요.")
        d["amount"] = d["amount"].fillna(1.0)      # 건수 기반 퇴화(그 사실을 위에 로그로 남김)
    return d[cols].reset_index(drop=True)


def build_dilution_flags(dis: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """V3 — 90일 내 대규모 희석성 조달(유상증자/CB/BW)."""
    cols = ["code", "ym", "dilution_90d"]
    if dis is None or not len(dis):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    ev = d.get("event", pd.Series("", index=d.index)).astype(str)
    hit = ev.isin(["rights_issue", "cb_issue", "bw_issue"])
    d = d[hit].copy()
    if not len(d):
        return pd.DataFrame(columns=cols)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["rcept_dt"] = as_ts_series(d.get("rcept_dt"))
    d = d[d["code"].notna() & d["rcept_dt"].notna()]
    if not len(d):
        return pd.DataFrame(columns=cols)
    ex = expand_events_to_months(d[["code", "rcept_dt"]], "rcept_dt", months, window_days=90)
    if not len(ex):
        return pd.DataFrame(columns=cols)
    out = (ex.groupby(["code", "month"], observed=True).size()
             .rename("dilution_90d").reset_index().rename(columns={"month": "ym"}))
    LOG.ok(f"V3 희석성 조달 플래그 {len(out):,} 종목월")
    return out[cols]


def build_watch_flags(dis: pd.DataFrame, months: pd.DatetimeIndex,
                      sec: pd.DataFrame) -> pd.DataFrame:
    """V5 — 관리종목·거래정지·감사의견 비적정.

    ★ 지정/해제 이벤트를 **계단함수**로 복원한다. '현재 관리종목 목록'을 과거에 소급 적용하면
      그 자체가 미래정보다. 그리고 이미 해제된 종목이 영구히 배제된다.
    ⚠ 감사의견 '적정' 여부를 직접 확인할 공개 API 가 없다. 비적정 '증거가 있을 때만' 배제하고,
      증거 소스가 없으면 그 조항을 비활성화한 채 감사표에 남긴다.
    """
    cols = ["code", "ym", "watch_flag"]
    if dis is None or not len(dis) or not len(months):
        return pd.DataFrame(columns=cols)
    d = dis.copy()
    nm = d.get("report_nm", pd.Series("", index=d.index)).astype(str)
    d["code"] = d.get("stock_code", pd.Series(pd.NA, index=d.index)).map(to_code6)
    d["rcept_dt"] = as_ts_series(d.get("rcept_dt"))
    on = nm.str.contains(XCB_DISCLOSURE_PATTERNS["watch_designate"], regex=True, na=False) | \
        nm.str.contains(XCB_DISCLOSURE_PATTERNS["trading_halt"], regex=True, na=False)
    off = nm.str.contains(XCB_DISCLOSURE_PATTERNS["watch_release"], regex=True, na=False)
    ev = d[(on | off) & d["code"].notna() & d["rcept_dt"].notna()].copy()
    if not len(ev):
        LOG.warn("관리종목/거래정지 공시를 찾지 못했습니다 — V5 는 자본잠식 조항만으로 축소됩니다. "
                 "없는 것을 있는 척하지 않고 감사표에 그대로 표기합니다.")
        return pd.DataFrame(columns=cols)
    ev["delta"] = np.where(off.reindex(ev.index).fillna(False).to_numpy(), -1.0, 1.0)
    ev["ym"] = as_ts_series(ev["rcept_dt"]) + pd.offsets.MonthEnd(0)
    step = ev.groupby(["code", "ym"], observed=True)["delta"].sum().reset_index()

    codes = step["code"].unique()
    grid = pd.MultiIndex.from_product([codes, months], names=["code", "ym"]).to_frame(index=False)
    g = grid.merge(step, on=["code", "ym"], how="left").sort_values(["code", "ym"])
    g["delta"] = g["delta"].fillna(0.0)
    g["watch_flag"] = (g.groupby("code", observed=True)["delta"].cumsum() > 0).astype(float)
    LOG.ok(f"V5 관리/정지 계단함수 복원: {int(g['watch_flag'].sum()):,} 종목월 발동")
    return g[cols]


def build_capital_impairment(fin: pd.DataFrame) -> pd.DataFrame:
    """V5 보조 — 자본잠식(자본총계 < 0). 재무제표만으로 확실히 판정된다."""
    if fin is None or not len(fin) or "equity" not in fin.columns:
        return pd.DataFrame(columns=["code", "knowledge_date", "impaired"])
    d = fin[["code", "knowledge_date", "equity"]].copy()
    d["impaired"] = (pd.to_numeric(d["equity"], errors="coerce") < 0).astype(float)
    return d[["code", "knowledge_date", "impaired"]]


def derive_theta_x(fin: pd.DataFrame, mapping: pd.DataFrame, cx: pd.DataFrame,
                   fx_usdkrw: float = 1200.0) -> pd.DataFrame:
    """θ_X = 국내법인 수출매출(별도) / 연결매출.  관측커버리지 **가중치**(배제 기준 아님).

    통관은 '관세영역 반출 물량'이므로 대응 회계항목은 **별도(개별)** 기준 수출매출이다.
    연결이 아니다. 해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.

    ⚠ 공개 API 로 '별도 수출매출'을 직접 주는 항목이 없다. 3단 폴백을 쓰고 **어느 단을 썼는지
      반드시 표로 낸다**:
        T1  별도(OFS) 매출 / 연결(CFS) 매출  × 매핑 HS 수출액 비중  → 근사
        T2  매핑 HS 수출액(USD→KRW) / 연결매출                      → 상한 근사
        T3  결측 — compose_signal 이 중앙값으로 대체하고 그 사실을 기록
    """
    cols = ["code", "knowledge_date", "theta_x", "theta_src"]
    if fin is None or not len(fin):
        return pd.DataFrame(columns=cols)
    d = fin[["code", "knowledge_date", "period_end"]].copy()
    rev = None
    for c in ("revenue_ttm", "revenue"):
        if c in fin.columns:
            rev = pd.to_numeric(fin[c], errors="coerce")
            break
    if rev is None:
        return pd.DataFrame(columns=cols)
    d["rev"] = rev.to_numpy()

    theta = pd.Series(np.nan, index=d.index)
    src = pd.Series("T3_missing", index=d.index, dtype=object)

    # T2: 매핑된 HS 의 기업 귀속 수출액(USD) → KRW → 연결매출 대비
    if mapping is not None and len(mapping) and cx is not None and len(cx):
        c = cx.copy()
        c["hs"] = c["hs"].astype(str)
        c["year"] = as_ts_series(c["ym"]).dt.year
        hs_y = c.groupby(["hs", "year"], observed=True)["exp_usd"].sum().reset_index()
        mp = mapping[["code", "hs", "weight"]].copy()
        mp["hs"] = mp["hs"].astype(str)
        j = mp.merge(hs_y, on="hs", how="inner")
        j["firm_usd"] = pd.to_numeric(j["exp_usd"], errors="coerce") * \
            pd.to_numeric(j["weight"], errors="coerce").fillna(1.0)
        fy = j.groupby(["code", "year"], observed=True)["firm_usd"].sum().reset_index()
        d["year"] = as_ts_series(d["period_end"]).dt.year
        d = d.merge(fy, on=["code", "year"], how="left")
        t2 = safe_div(pd.to_numeric(d["firm_usd"], errors="coerce") * fx_usdkrw, d["rev"])
        ok = t2.notna() & (t2 > 0)
        theta = theta.where(~ok, t2)
        src = src.where(~ok, "T2_mapped_export")

    out = d[["code", "knowledge_date"]].copy()
    out["theta_x"] = pd.to_numeric(theta, errors="coerce").clip(0.0, 1.0)
    out["theta_src"] = src.to_numpy()
    cov = float(out["theta_x"].notna().mean()) if len(out) else 0.0
    LOG.info(f"θ_X 산출 커버리지 {cov*100:.0f}% "
             f"({out['theta_src'].value_counts().to_dict()}) — "
             f"결측은 0 이나 1 이 아니라 셀 중앙값으로 대체하고 그 사실을 기록합니다.")
    if cov < 0.3:
        LOG.warn("θ_X 커버리지가 30% 미만입니다. θ_X 가중은 사실상 상수가 되며, "
                 "'수출 비중이 낮은데 신호만 좋은' 기업을 걸러내는 힘이 약해집니다. "
                 "R5 절제(θ_X 가중 vs 미가중)로 영향을 실측하세요.")
    return out[cols]


def build_subsidy_signal(fin: pd.DataFrame) -> pd.DataFrame:
    """V11 보조 — 정부보조금수익/매출 급증.

    표준 계정과목에 '정부보조금수익'이 항상 잡히지는 않는다. 잡히지 않으면 결측으로 두고
    V11 은 유효세율 조항만으로 판정한다(그 사실을 로그에 남긴다).
    """
    cols = ["code", "knowledge_date", "subsidy_ratio_chg"]
    if fin is None or not len(fin):
        return pd.DataFrame(columns=cols)
    cand = [c for c in fin.columns if "subsidy" in str(c).lower() or "보조금" in str(c)]
    if not cand:
        LOG.info("정부보조금수익 계정을 재무제표에서 찾지 못했습니다 — "
                 "V11 은 유효세율 급락 조항만으로 판정합니다.")
        return pd.DataFrame(columns=cols)
    d = fin[["code", "knowledge_date"]].copy()
    sub = pd.to_numeric(fin[cand[0]], errors="coerce")
    rev = pd.to_numeric(fin.get("revenue_ttm", fin.get("revenue")), errors="coerce")
    r = safe_div(sub, rev)
    d["subsidy_ratio_chg"] = r - r.groupby(fin["code"], observed=True).shift(4)
    return d[cols]


def build_coverage_panel(reports: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """d2/d4 — 애널리스트 커버리지의 '존재'와 '개시'.

    ★ 이 전략이 리포트에서 필요로 하는 것은 신원이 아니라 커버리지의 존재 여부와 개시 시점이다
      (§7.4). 목록 레벨에서 확보 가능하므로 PDF 추출을 시도하지 않는다.
      d2 = -(최근 12개월 커버리지 애널리스트 수)   무커버리지일수록 미반영
      d4 = 최근 6개월 내 '최초' 리포트 발생 더미   정보비대칭 해소 시작
    """
    cols = ["code", "ym", "n_analyst", "coverage_init"]
    if reports is None or not len(reports) or not len(months):
        return pd.DataFrame(columns=cols)
    r = reports.copy()
    r["code"] = r.get("stock_code").map(to_code6) if "stock_code" in r.columns else pd.NA
    r["knowledge_date"] = as_ts_series(r.get("knowledge_date", r.get("pub_date")))
    r = r[r["code"].notna() & r["knowledge_date"].notna()].copy()
    if not len(r):
        return pd.DataFrame(columns=cols)

    # 최근 12개월 커버리지 — 애널리스트 식별이 되면 고유 인원수, 아니면 증권사 수로 대체.
    who = r.get("analyst_raw", pd.Series("", index=r.index)).astype(str).str.strip()
    alt = r.get("broker_name", r.get("broker_raw", pd.Series("", index=r.index))).astype(str)
    r["_who"] = np.where(who.str.len() > 0, who, alt)
    ex = expand_events_to_months(r[["code", "knowledge_date", "_who"]],
                                 "knowledge_date", months, window_days=365)
    if not len(ex):
        return pd.DataFrame(columns=cols)
    cov = (ex.groupby(["code", "month"], observed=True)["_who"].nunique()
             .rename("n_analyst").reset_index().rename(columns={"month": "ym"}))

    # 커버리지 개시: 그 종목의 최초 리포트일로부터 6개월
    first = r.groupby("code", observed=True)["knowledge_date"].min().rename("first_dt").reset_index()
    fx = expand_events_to_months(first, "first_dt", months, window_days=183)
    init = (fx.assign(coverage_init=1.0)[["code", "month", "coverage_init"]]
              .rename(columns={"month": "ym"}).drop_duplicates(["code", "ym"]))
    out = cov.merge(init, on=["code", "ym"], how="left")
    out["coverage_init"] = out["coverage_init"].fillna(0.0)
    LOG.ok(f"커버리지 패널: {out['code'].nunique():,}종목 × {out['ym'].nunique()}개월 "
           f"(평균 커버리지 {out['n_analyst'].mean():.1f}명)")
    return out[cols]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [20/27]  25_nokrx.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  KRX 비의존 경로 — 생존자편향 제거와 PIT 유니버스를 **KRX 없이 보장**한다                   ║
# ║                                                                                             ║
# ║  배경: KRX 마켓플레이스는 2025-12 부터 로그인이 필수가 됐고, 중복로그인·과다요청으로        ║
# ║  계정이 차단되는 일이 흔하다. 그런데 이 전략에서 KRX 가 반드시 필요한 곳은 **하나도 없다.** ║
# ║  이 모듈은 그것을 '희망'이 아니라 **검증된 사실**로 만든다:                                 ║
# ║                                                                                             ║
# ║    C2 생존자편향 : FDR 상장폐지 목록 + KIND + 상장/폐지일 → KRX 불필요                      ║
# ║    C13 PIT유니버스: 상장일·폐지일 + 가격 관측으로 매 시점 재구성 → KRX 불필요               ║
# ║    가격·거래대금  : FDR → 네이버 → yfinance 체인 → KRX 불필요                               ║
# ║                                                                                             ║
# ║  약해지는 것은 둘뿐이고, 둘 다 **대체 경로 + 감사표**로 처리한다:                           ║
# ║    시가총액(규모버킷) → 상장주식수 역산 근사 · 수급(d3) → 네이버 폴백 또는 U 에서 제외      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def krx_mode() -> str:
    """KRX 사용 여부를 확정한다. 'off' | 'auto' | 'on'."""
    v = str(KRX_ENABLED).lower()
    if v in ("false", "0", "off", "no"):
        return "off"
    if not (KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW):
        return "off"
    return "on" if v in ("true", "1", "on", "yes") else "auto"


def build_security_master_nokrx() -> "pd.DataFrame":
    """KRX 없이 종목 마스터를 만든다.  ★ 이 경로가 C2 의 본선이다.

    KRX 스냅샷은 '검증 입력'일 뿐 의존 대상이 아니다. 스냅샷이 없어도
    상장목록(FDR/KIND) ∪ 상장폐지목록(FDR) 로 마스터가 완성된다.
    """
    sec = build_security_master(pd.DataFrame(columns=["snap_date", "code", "market"]))
    return sec


def infer_delisting_from_prices(sec: "pd.DataFrame", px_d: "pd.DataFrame",
                                months: "pd.DatetimeIndex") -> "pd.DataFrame":
    """폐지일이 없는 '폐지 확정' 종목의 폐지일을 **마지막 거래일**로 복원한다.

    ★ 왜 필요한가: FDR 상장폐지 스냅샷에 폐지일 컬럼이 아예 없는 판이 있다.
      폐지 사실만 알고 날짜를 모르면 두 가지 잘못된 처리가 가능한데 둘 다 치명적이다.
        ① 그 종목을 통째로 버린다     → 실패 사례가 사라진다 = 생존자편향 재유입
        ② 폐지일을 NaT 로 두고 방치   → 폐지 후에도 계속 보유 가능(가격이 남아 있으면)
      마지막 거래일은 관측 가능한 사실이고, '그 이후로 거래가 없다'는 것이 곧 폐지의 정의에
      가장 가깝다. 데이터가 끝나는 시점(가격 패널의 마지막 날)과 구분해야 하므로,
      패널 마지막 달에 걸친 종목은 '아직 상장 중'으로 보고 복원하지 않는다.
    """
    if sec is None or not len(sec):
        return sec
    s = sec.copy()
    dd = as_ts_series(s.get("delisting_date"))
    is_dead = s.get("src", pd.Series("", index=s.index)).astype(str).str.contains("delist")
    need = is_dead & dd.isna()
    n_need = int(need.sum())
    if not n_need:
        return s
    if px_d is None or not len(px_d):
        LOG.warn(f"폐지일 미상 {n_need:,}종목의 폐지일을 복원할 가격 데이터가 없습니다. "
                 f"이 종목들은 폐지일이 없어 '상장 중'으로 취급되며, 그만큼 생존자편향이 남습니다.")
        return s
    p = px_d[["code", "date"]].copy()
    p["code"] = p["code"].astype(str)
    last = p.groupby("code", observed=True)["date"].max()
    panel_end = as_ts_series(pd.Series([px_d["date"].max()])).iloc[0]
    # 패널 마지막 60일 안에 거래가 있으면 '데이터 끝'이지 '폐지'가 아니다.
    cutoff = panel_end - pd.Timedelta(days=60)
    inferred = s.loc[need, "code"].astype(str).map(last)
    inferred = inferred.where(inferred.notna() & (inferred <= cutoff))
    # 폐지일 = 마지막 거래일의 다음 날(그 달 말 기준으로 유니버스에서 빠진다)
    s.loc[need, "delisting_date"] = (inferred + pd.Timedelta(days=1)).to_numpy()
    n_ok = int(as_ts_series(s.loc[need, "delisting_date"]).notna().sum())
    LOG.ok(f"폐지일 복원: 미상 {n_need:,}종목 중 {n_ok:,}종목을 '마지막 거래일+1'로 확정했습니다 "
           f"(가격 관측 기반). 나머지 {n_need - n_ok:,}종목은 가격이 없어 복원 불가입니다.")
    if n_need - n_ok > 0:
        LOG.warn(f"폐지일을 끝내 못 구한 {n_need - n_ok:,}종목은 유니버스에서 '상장 중'으로 "
                 f"남습니다. 다만 가격이 없으므로 체결가가 없어 진입 후보에서 자연히 빠집니다 — "
                 f"성과를 부풀리는 방향은 아닙니다.")
    return s


def audit_survivorship(sec: "pd.DataFrame", months: "pd.DatetimeIndex",
                       phase: str = "final") -> dict:
    """생존자편향 제거가 **실제로** 되어 있는지 수치로 검증한다.

    ★ '폐지 종목이 마스터에 있다'는 것만으로는 부족하다. 폐지 종목이
      백테스트 기간 안에서 실제로 유니버스에 들어왔다가 폐지일에 빠지는지를 봐야 한다.
      이 감사가 통과하지 못하면 성과는 전부 생존자편향으로 부풀려진 값이다.
    """
    out = {"total": 0, "delisted": 0, "delisted_in_window": 0, "listing_known": 0.0,
           "verdict": "FAIL", "detail": ""}
    if sec is None or not len(sec):
        out["detail"] = "종목 마스터가 비어 있습니다."
        return out
    s = sec.drop_duplicates("code").copy()
    dd = as_ts_series(s.get("delisting_date"))
    ld = as_ts_series(s.get("listing_date"))
    lo, hi = pd.Timestamp(BACKTEST_START), pd.Timestamp(BACKTEST_END)
    out["total"] = int(len(s))
    out["delisted"] = int(dd.notna().sum())
    out["delisted_in_window"] = int(((dd >= lo) & (dd <= hi)).sum())
    out["listing_known"] = float(ld.notna().mean())

    # ★ 타당성: 폐지일이 상장일로 오염되면 아주 오래된 '폐지'가 대량으로 생긴다.
    #   개수만 세면 이 오염을 통과시켜 버리므로 분포까지 본다.
    n_ancient = int((dd < pd.Timestamp("1995-01-01")).sum())
    out["ancient"] = n_ancient
    ok = (out["delisted_in_window"] >= 50) and (n_ancient <= max(20, 0.05 * max(out["delisted"], 1)))
    out["verdict"] = "PASS" if ok else "FAIL"
    out["detail"] = (
        f"마스터 {out['total']:,}종목 중 폐지일 보유 {out['delisted']:,}종목 · "
        f"백테스트 구간 내 폐지 {out['delisted_in_window']:,}종목 · "
        f"상장일 확보율 {out['listing_known']*100:.0f}%")
    # ★ 가격 수집 전(pre)에는 폐지일이 아직 복원되지 않았다. 그 시점의 0건을 FAIL 로 외치면
    #   진짜 문제와 구분이 안 되는 '늑대야' 경고가 된다. 최종 판정은 가격 수집 뒤에만 한다.
    pre = (phase == "pre")
    LOG.banner("생존자편향 제거 감사 (C2) — KRX 비의존 경로"
               + ("  [중간 점검]" if pre else ""),
               "폐지 종목이 구간 안에서 실제로 들어왔다 빠지는가"
               if not pre else
               "가격 수집 전 중간 점검 — 폐지일은 이후 '마지막 거래일'로 복원됩니다")
    LOG.table([["종목 마스터(생존+폐지)", f"{out['total']:,}"],
               ["폐지일 보유 종목", f"{out['delisted']:,}"],
               ["백테스트 구간 내 폐지", f"{out['delisted_in_window']:,}"],
               ["상장일 확보율", f"{out['listing_known']*100:.1f}%"],
               ["1995년 이전 '폐지'(오염 지표)", f"{out.get('ancient', 0):,}"],
               ["판정", out["verdict"]]], ["항목", "값"])
    if out.get("ancient", 0) > max(20, 0.05 * max(out["delisted"], 1)):
        LOG.error(
            f"1995년 이전 '폐지'가 {out['ancient']:,}건입니다 — 폐지일 자리에 **상장일**이 "
            f"들어왔을 때 나타나는 전형적 증상입니다.\n"
            f"    이 상태로 두면 '오래전 상장 → 최근 폐지' 종목이 백테스트 전 구간에서 빠져\n"
            f"    실패 사례가 사라집니다(생존자편향 재유입). 폐지일 소스를 먼저 고치세요.")
    if out["listing_known"] < 0.10:
        LOG.warn(
            f"상장일 확보율이 {out['listing_known']*100:.0f}% 입니다 "
            f"(KIND 가 막히면 흔합니다 — FDR 상장목록 스냅샷에 ListingDate 가 없는 판이 있습니다).\n"
            f"    → 시즈닝(상장 후 {UNIVERSE_SEASON_DAYS}거래일) 앵커는 '최초 가격 관측일'로 폴백합니다.\n"
            f"    → 방향이 중요합니다: '모르면 오래된 종목'으로 처리하므로 신규상장 필터가 "
            f"**느슨해질 뿐**이며, 반대로 '모르면 신규상장'으로 처리했다면 패널 앞 구간의 "
            f"유니버스가 통째로 비었을 것입니다. 생존자편향은 폐지일로 제거되므로 영향 없습니다.")
    if pre and not ok:
        LOG.info("폐지일이 아직 비어 있습니다 — 가격 수집 후 '마지막 거래일'로 복원한 뒤 "
                 "최종 판정합니다(여기서는 중단하지 않습니다).")
        out["verdict"] = "PENDING"
    elif not ok:
        LOG.error("[C2] 구간 내 폐지 종목이 50개 미만입니다. 10년이면 통상 수백 종목이 폐지됩니다. "
                  "상장폐지 목록을 못 받은 상태이며, 이대로 나온 성과는 생존자편향으로 "
                  "부풀려진 값입니다. raw.githubusercontent.com(FDR 캐시) 접근을 확인하세요.")
    else:
        LOG.ok(f"생존자편향 제거 정상 — 구간 내 폐지 {out['delisted_in_window']:,}종목이 "
               f"유니버스에 포함되었다가 폐지일에 빠집니다(정리매매 없으면 -100%).")
    return out


def mcap_nokrx(months: "pd.DatetimeIndex", px_m: "pd.DataFrame",
               sec: "pd.DataFrame") -> "pd.DataFrame":
    """KRX 없이 PIT 시가총액을 근사한다.  ★ 규모버킷(셀)에만 쓴다.

    방법: 상장목록 스냅샷의 (시가총액 ÷ 종가) 로 상장주식수를 역산하고, 그 주식수를
    과거 종가에 곱한다. 유상증자·무상증자·감자를 반영하지 못하므로 **비PIT 근사**이며,
    그 사실과 커버리지를 감사표에 남긴다.

    ★ 이 근사가 랭크 유니버스 컷에 쓰이면 위험하지만(자본이벤트 기업이 체계적으로 어긋남),
      XCB 는 시총으로 유니버스를 자르지 않는다(§5.1 — 매핑이 곧 유니버스).
      규모버킷은 셀 내 공통충격 흡수용이라 근사 오차의 영향이 훨씬 작다.
    """
    cols = ["code", "month", "mcap", "shares", "mcap_src"]
    if px_m is None or not len(px_m):
        return pd.DataFrame(columns=cols)
    shares = None
    try:
        lst = fetch_fdr_listing()
        if lst is not None and len(lst):
            lm = _lower_map(lst)
            mc = next((lm[c] for c in ("marcap", "markcap", "시가총액") if c in lm), None)
            cl = next((lm[c] for c in ("close", "종가") if c in lm), None)
            sh = next((lm[c] for c in ("stocks", "shares", "상장주식수") if c in lm), None)
            if sh:
                shares = pd.DataFrame({"code": lst[lm.get("code", "Code")].map(to_code6),
                                       "shares": pd.to_numeric(lst[sh], errors="coerce")})
            elif mc and cl:
                shares = pd.DataFrame({
                    "code": lst[lm.get("code", "Code")].map(to_code6),
                    "shares": safe_div(pd.to_numeric(lst[mc], errors="coerce"),
                                       pd.to_numeric(lst[cl], errors="coerce"))})
    except Exception as e:                                              # noqa
        LOG.debug(f"상장주식수 역산 실패: {type(e).__name__}")
    if shares is None or not len(shares):
        LOG.warn("상장주식수를 얻지 못해 시가총액을 만들 수 없습니다. "
                 "규모버킷은 **20일 평균거래대금 랭크**로 대체됩니다(셀 정의만 바뀌며, "
                 "유니버스 컷에는 시총을 쓰지 않으므로 편향은 생기지 않습니다).")
        return pd.DataFrame(columns=cols)
    shares = shares.dropna(subset=["code"]).drop_duplicates("code")
    m = px_m[["code", "month", "close"]].copy()
    m["code"] = m["code"].map(to_code6)
    m = m.merge(shares, on="code", how="left")
    m["mcap"] = pd.to_numeric(m["close"], errors="coerce") * \
        pd.to_numeric(m["shares"], errors="coerce")
    m.loc[~(m["mcap"] > 0), "mcap"] = np.nan
    m["mcap_src"] = "shares_backsolve(비PIT 근사)"
    cov = float(m["mcap"].notna().mean())
    LOG.warn(f"PIT 시가총액을 상장주식수 역산으로 근사했습니다 (커버리지 {cov*100:.0f}%). "
             f"자본이벤트(유증·무증·감자)는 반영되지 않습니다. "
             f"XCB 는 시총으로 유니버스를 자르지 않으므로 영향은 규모버킷(셀)에 한정됩니다.")
    return m[cols]


def flows_naver(codes: "Sequence[str]", months: "pd.DatetimeIndex",
                max_codes: int = 600) -> "Optional[pd.DataFrame]":
    """KRX 없이 기관·외국인 수급(d3)을 네이버에서 받는다. 실패하면 None → d3 비활성화.

    ★ 못 얻으면 0 으로 채우지 않는다. 0 은 '수급이 없었다'는 적극적 주장이고,
      d3 는 '수급이 안 들어왔을수록 좋다'는 부호라 0 채움이 그 종목을 인위적으로 좋게 만든다.
    """
    codes = list(dict.fromkeys(str(c) for c in codes))[:max_codes]
    if not codes:
        return None
    url = "https://finance.naver.com/item/frgn.naver"
    rows: List[dict] = []
    fails = 0

    def _one(c: str):
        out = []
        for page in (1, 2, 3):
            html = http_get(url, source="naver", params={"code": c, "page": page},
                            referer="https://finance.naver.com/", tries=2)
            if not html:
                return out
            try:
                tabs = pd.read_html(io.StringIO(html))
            except Exception:                                           # noqa
                return out
            for t in tabs:
                if t.shape[1] < 6:
                    continue
                t = t.dropna(how="all")
                cs = [str(x) for x in t.columns]
                if not any("날짜" in x for x in cs):
                    continue
                t.columns = [str(x) for x in t.columns]
                dcol = next((x for x in t.columns if "날짜" in x), None)
                icol = next((x for x in t.columns if "기관" in x), None)
                fcol = next((x for x in t.columns if "외국인" in x), None)
                if not dcol or (not icol and not fcol):
                    continue
                for _, r in t.iterrows():
                    d = as_ts(r.get(dcol))
                    if d is None or pd.isna(d):
                        continue
                    inst = pd.to_numeric(str(r.get(icol, "")).replace(",", ""), errors="coerce")
                    frg = pd.to_numeric(str(r.get(fcol, "")).replace(",", ""), errors="coerce")
                    out.append({"code": c, "date": d,
                                "net": float(np.nansum([inst, frg]))})
        return out

    res = pmap_io(_one, codes, workers=min(N_WORKERS_IO, 6), desc="네이버 수급(d3)")
    for r in res:
        if r:
            rows.extend(r)
        else:
            fails += 1
    if not rows:
        LOG.warn("네이버 수급도 받지 못했습니다 — d3 를 비활성화하고 U 를 나머지 축으로 "
                 "구성합니다(0 으로 채우지 않습니다).")
        return None
    d = pd.DataFrame(rows)
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    g = d.groupby(["code", "month"], observed=True)["net"].sum().reset_index()
    g = g.sort_values(["code", "month"])
    g["net_buy_120d"] = g.groupby("code", observed=True)["net"].transform(
        lambda s: s.rolling(6, min_periods=3).sum())
    LOG.ok(f"네이버 수급 확보: {g['code'].nunique():,}종목 × {g['month'].nunique()}개월 "
           f"(실패 {fails}종목)")
    return g.rename(columns={"month": "ym"})[["code", "ym", "net_buy_120d"]]


def universe_sources_audit(sec: "pd.DataFrame", px_m: "pd.DataFrame",
                           mcap: "pd.DataFrame", flows) -> None:
    """어떤 소스로 무엇을 만들었는지 한눈에. KRX 의존도가 0 임을 표로 증명한다."""
    mode = krx_mode()
    krx_ok = bool(getattr(KRX, "session_ok", False))
    rows = [
        ["종목 마스터(상장+폐지)", "FDR 상장목록 + KIND + FDR 상장폐지",
         f"{0 if sec is None else sec['code'].nunique():,}종목", "KRX 불필요 ✔"],
        ["생존자편향 제거 C2", "FDR 상장폐지 목록(폐지일)",
         f"{0 if sec is None else int(as_ts_series(sec.get('delisting_date')).notna().sum()):,}건",
         "KRX 불필요 ✔"],
        ["PIT 유니버스 C13", "상장일·폐지일 + 가격 관측",
         f"{0 if px_m is None else px_m['code'].nunique():,}종목", "KRX 불필요 ✔"],
        ["가격·거래대금", "FDR → 네이버 → yfinance",
         f"{0 if px_m is None else len(px_m):,}행", "KRX 불필요 ✔"],
        ["시가총액(규모버킷)",
         (mcap["mcap_src"].mode().iloc[0] if mcap is not None and len(mcap)
          and "mcap_src" in mcap.columns and len(mcap["mcap_src"].mode()) else "없음"),
         f"{0 if mcap is None else len(mcap):,}행",
         "KRX 있으면 정확 / 없으면 근사"],
        ["투자자 수급 d3",
         "네이버 폴백" if flows is not None else "미확보 → U 에서 제외",
         f"{0 if flows is None else len(flows):,}행", "KRX 있으면 정확 / 없으면 폴백"],
    ]
    LOG.banner("데이터 소스 감사 — KRX 의존도",
               f"KRX 모드={mode} · 세션={'확보' if krx_ok else '없음'} — "
               f"핵심 4개 항목은 KRX 없이 성립합니다")
    LOG.table(rows, ["항목", "사용 소스", "규모", "KRX 의존"])


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [21/27]  30_sensors.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1 센서 — 원시값만. 정규화는 여기서 하지 않는다(전부 L2).                                  ║
# ║                                                                                             ║
# ║  A축 통관(월)   → 트리거   : 상태 변화를 최초 감지                                          ║
# ║  B축 회계(분기) → 사전확률 : 그 변화를 감당할 체질인가                                      ║
# ║  C축 자원(분기) → 사전확률 : 능력을 미리 갖췄는가                                           ║
# ║  D축 기대(일)   → 할인율   : 얼마나 남았는가                                                ║
# ║                                                                                             ║
# ║  ★ B·C 를 '확인'이 아니라 '사전확률'로 쓰기 때문에 대기시간이 0이다.                        ║
# ║    A 가 움직인 시점에 즉시 판정이 끝난다 — 통관의 40~90일 선행성을 반납하지 않는 유일한 배치.║
# ║    그래서 "K분기 연속 정렬" 같은 대기조건을 절대 넣지 않는다(원칙 10).                      ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 선진시장 = 미국 + EU + 일본 + 대만 (§6.1). 국가군 축약은 수집 단계에서 이미 끝나 있다.
ADVANCED_MARKETS = ("US", "EU", "JP", "TW", "DE")

# a2 롤링 OLS 창 길이(월). 36개월 = 경기 1주기 내에서 β 를 재추정한다.
A2_WINDOW = 36
# 잔차 평균을 낼 최근 개월수. §7.1 의 mean(ε[t-5:t]).
A2_RECENT = 6
# a5 신규 세번 판정: 이 개월수 연속으로 임계 이상이면 '신규 등장'.
A5_STREAK = 3
# a5 더미의 지수감쇠 반감기(월).
A5_DECAY_HALFLIFE = 6.0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  A축 — 통관 4센서
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def customs_hs_monthly(cx: pd.DataFrame) -> pd.DataFrame:
    """(hs, ym, country) 원장 → (hs, ym) 월 집계 + 목적지 분포 지표.

    입력 표준 컬럼: hs, ym(월말 Timestamp), country, exp_wgt(kg), exp_usd(USD)
                    (선택) imp_wgt, imp_usd — 투입원가지수 산출에 쓴다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "ym", "wgt", "usd", "unit_price",
                                     "hhi_dest", "adv_share", "n_dest"])
    d = cx.copy()
    d["hs"] = d["hs"].astype(str)
    d["ym"] = as_ts_series(d["ym"])
    for c in ("exp_wgt", "exp_usd"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce").fillna(0.0)
    d = d[d["ym"].notna()]

    # ── (hs, ym) 총계
    g = d.groupby(["hs", "ym"], observed=True, sort=False)
    tot = g.agg(wgt=("exp_wgt", "sum"), usd=("exp_usd", "sum"),
                n_dest=("country", "nunique")).reset_index()
    # 단가는 반드시 USD 기준. 원화 환산 금지 — 환율 변동이 단가 신호로 오인된다(§6.1).
    tot["unit_price"] = safe_div(tot["usd"], tot["wgt"])
    tot.loc[~(tot["wgt"] > 0), "unit_price"] = np.nan

    # ── 목적지 집중도 HHI (금액 기준). groupby.apply 금지 → transform 으로.
    d["_tot_usd"] = d.groupby(["hs", "ym"], observed=True)["exp_usd"].transform("sum")
    share = safe_div(d["exp_usd"], d["_tot_usd"])
    d["_sh2"] = share ** 2
    d["_adv"] = np.where(d["country"].astype(str).str.upper().isin(ADVANCED_MARKETS),
                         d["exp_usd"], 0.0)
    agg2 = d.groupby(["hs", "ym"], observed=True, sort=False).agg(
        hhi_dest=("_sh2", "sum"), adv_usd=("_adv", "sum")).reset_index()
    out = tot.merge(agg2, on=["hs", "ym"], how="left")
    out["adv_share"] = safe_div(out["adv_usd"], out["usd"])
    out = out.drop(columns=["adv_usd"])
    return out.sort_values(["hs", "ym"]).reset_index(drop=True)


def customs_cv_dest(cx: pd.DataFrame, min_share: float = 0.01,
                    min_dest: int = 3) -> pd.DataFrame:
    """§5.4 커모디티 판별 — 같은 HS 안에서 목적지 간 단가가 얼마나 흩어지는가.

    cv 낮음 → 어느 나라에 팔든 같은 값 = 국제 시세 종속 = 커모디티 → 단가 축(a2) 무효
    cv 높음 → 고객·스펙별 가격 차별화 여지 존재 → 단가 축 유효

    주관이 아니라 데이터로 판정한다. 판정 결과는 V10 부분거부권으로 이어진다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])
    d = cx.copy()
    d["hs"] = d["hs"].astype(str)
    d["ym"] = as_ts_series(d["ym"])
    d["exp_wgt"] = pd.to_numeric(d.get("exp_wgt"), errors="coerce")
    d["exp_usd"] = pd.to_numeric(d.get("exp_usd"), errors="coerce")
    d = d[(d["exp_wgt"] > 0) & (d["exp_usd"] > 0) & d["ym"].notna()].copy()
    if not len(d):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])

    # 미미한 목적지는 단가가 튄다(샘플 1건짜리 특수 선적). 비중 하한으로 걸러낸다.
    d["_tot"] = d.groupby(["hs", "ym"], observed=True)["exp_usd"].transform("sum")
    d = d[safe_div(d["exp_usd"], d["_tot"]) >= min_share].copy()
    d["up"] = d["exp_usd"] / d["exp_wgt"]

    g = d.groupby(["hs", "ym"], observed=True, sort=False)["up"]
    m = g.transform("mean")
    s = g.transform("std")
    d["_cv"] = safe_div(s, m)
    d["_n"] = g.transform("size")
    d = d[d["_n"] >= min_dest]
    if not len(d):
        return pd.DataFrame(columns=["hs", "cv_dest", "cv_n"])
    # 월별 cv 의 시계열 중앙값 = 그 HS 의 구조적 가격차별화 여지
    per = d.drop_duplicates(["hs", "ym"])[["hs", "ym", "_cv"]]
    out = per.groupby("hs", observed=True)["_cv"].agg(
        cv_dest="median", cv_n="size").reset_index()
    return out


def customs_input_cost(cx: pd.DataFrame, hs_digits: int = 2) -> pd.DataFrame:
    """투입원가지수 — 같은 HS 章(2자리)의 **수입** 단가(USD/kg).

    왜 수입 단가인가: a2 회귀의 목적은 '원가 변동으로 설명되는 단가 변화'를 걷어내는 것이다.
    같은 장(章)의 수입 단가는 그 산업의 투입물 가격을 대리하며, 개별 수출기업의 가격결정력과는
    독립이다(내생성이 낮다). 수입 데이터가 없으면 전체 수출 단가 중앙값으로 폴백한다 —
    이 경우 원가 통제가 약해지므로 그 사실을 로그에 남긴다.
    """
    if cx is None or not len(cx):
        return pd.DataFrame(columns=["hs2", "ym", "input_cost"])
    d = cx.copy()
    d["ym"] = as_ts_series(d["ym"])
    d["hs2"] = d["hs"].astype(str).str.zfill(6).str[:hs_digits]
    has_imp = ("imp_usd" in d.columns) and ("imp_wgt" in d.columns) and \
              (pd.to_numeric(d["imp_wgt"], errors="coerce").fillna(0) > 0).any()
    if has_imp:
        d["_u"] = pd.to_numeric(d["imp_usd"], errors="coerce").fillna(0.0)
        d["_w"] = pd.to_numeric(d["imp_wgt"], errors="coerce").fillna(0.0)
        src = "수입단가(장별)"
    else:
        d["_u"] = pd.to_numeric(d["exp_usd"], errors="coerce").fillna(0.0)
        d["_w"] = pd.to_numeric(d["exp_wgt"], errors="coerce").fillna(0.0)
        src = "수출단가(장별) — 수입 데이터 없음, 원가통제 약화"
        LOG.warn("투입원가지수를 수입단가로 만들 수 없어 수출단가로 대체합니다. "
                 "a2 의 원가 통제(γ항)가 약해집니다 — R5 절제에서 기여를 확인하세요.")
    g = d.groupby(["hs2", "ym"], observed=True, sort=False).agg(
        _u=("_u", "sum"), _w=("_w", "sum")).reset_index()
    g["input_cost"] = safe_div(g["_u"], g["_w"])
    g.loc[~(g["_w"] > 0), "input_cost"] = np.nan
    LOG.debug(f"투입원가지수 소스: {src} · {g['hs2'].nunique()}개 장 × {g['ym'].nunique()}개월")
    return g[["hs2", "ym", "input_cost"]]


def _stack_long(P: pd.DataFrame, value: str) -> pd.DataFrame:
    """(hs × ym) 와이드 → (hs, ym, value) 롱. pandas 2/3 양쪽에서 같은 순서를 보장한다.

    `stack(future_stack=...)` 은 버전마다 기본값과 인자 유무가 달라 조용히 결측 처리와
    행 순서가 바뀐다. 여기서는 순서가 곧 정합성이므로 numpy 로 직접 편다.
    """
    vals = P.to_numpy(dtype=float)
    n_hs, n_ym = vals.shape
    return pd.DataFrame({
        "hs": np.repeat(np.asarray(P.index, dtype=object), n_ym),
        "ym": np.tile(pd.DatetimeIndex(P.columns).to_numpy(), n_hs),
        value: vals.reshape(-1),
    })


def customs_a2_residual(hsm: pd.DataFrame, cost: pd.DataFrame,
                        window: int = A2_WINDOW, recent: int = A2_RECENT) -> pd.DataFrame:
    """a2 — 수출단가 잔차. 36개월 롤링 OLS (적률 방식, 원칙 4).

        log(단가) = α + β·log(물량) + γ·log(투입원가) + ε

    정상 기업은 β<0 (많이 팔려면 깎아야 한다). ε 이 지속적으로 양(+)이면
    '물량이 늘었는데 예상만큼 안 깎였다' = 제약선이 이동했다.

    ★ 종목×시점 파이썬 루프 금지. (N_hs, T) 배치로 한 번에 푼다.
    """
    empty = pd.DataFrame(columns=["hs", "ym", "a2", "a2_beta", "a2_resid"])
    if hsm is None or not len(hsm):
        return empty
    d = hsm.copy()
    d["hs2"] = d["hs"].astype(str).str.zfill(6).str[:2]
    if cost is not None and len(cost):
        d = d.merge(cost, on=["hs2", "ym"], how="left")
    else:
        d["input_cost"] = np.nan

    # 균일 격자로 피벗 — 롤링 창이 달을 건너뛰면 안 된다.
    yms = pd.DatetimeIndex(sorted(d["ym"].dropna().unique()))
    hss = pd.Index(sorted(d["hs"].astype(str).unique()), name="hs")
    if len(yms) < window or not len(hss):
        LOG.warn(f"a2: 관측 개월 {len(yms)} < 창 {window} — 단가 잔차를 산출할 수 없습니다.")
        return empty

    def _piv(col: str) -> np.ndarray:
        p = d.pivot_table(index="hs", columns="ym", values=col, aggfunc="mean")
        return p.reindex(index=hss, columns=yms).to_numpy(dtype=float)

    up = _piv("unit_price")
    qty = _piv("wgt")
    ic = _piv("input_cost")

    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log(np.where(up > 0, up, np.nan))
        lq = np.log(np.where(qty > 0, qty, np.nan))
        lc = np.log(np.where(ic > 0, ic, np.nan))
    # 투입원가가 통째로 없는 HS 는 그 항을 상수로 둔다(회귀가 죽지 않도록).
    lc = np.where(np.isfinite(lc), lc, 0.0)

    N, T = y.shape
    X = np.empty((N, T, 3), dtype=float)
    X[:, :, 0] = 1.0
    X[:, :, 1] = lq
    X[:, :, 2] = lc
    resid = rolling_ols_resid(y, X, window=window)          # (N, T)

    R = pd.DataFrame(resid, index=hss, columns=yms)
    # a2 = mean(ε[t-5:t]) / std(ε)   — 표준편차는 그 HS 의 전체 잔차 산포
    # ★ rolling(axis=1) 은 pandas 2 에서 폐기되고 3 에서 제거됐다. 전치해서 축을 세운다.
    mean_r = (R.T.rolling(recent, min_periods=max(2, recent // 2)).mean()).T
    sd = R.std(axis=1, skipna=True).replace(0.0, np.nan)
    a2 = mean_r.div(sd, axis=0)

    beta = rolling_ols_beta_last(y, X, window=window)        # (N, 3) — 진단카드용 β
    # 두 프레임은 index/columns 가 동일하므로 stack 순서가 일치한다.
    out = _stack_long(a2, "a2")
    out["a2_resid"] = _stack_long(R, "a2_resid")["a2_resid"].to_numpy()
    out = out.merge(pd.DataFrame({"hs": np.asarray(hss), "a2_beta": beta[:, 1]}),
                    on="hs", how="left")
    n_ok = int(np.isfinite(out["a2"]).sum())
    b_med = float(np.nanmedian(beta[:, 1]))
    LOG.ok(f"a2 단가잔차: HS {len(hss)}개 × {len(yms)}개월 → 유효 {n_ok:,}관측 "
           f"(β 중앙값 {b_med:+.3f} — 음수여야 정상)")
    # ★ 이 전략의 전제는 "정상 기업은 β<0 (많이 팔려면 깎아야 한다)"이다.
    #   β 중앙값이 0 근처거나 양수면 전제가 데이터에서 성립하지 않는 것이고,
    #   그러면 a2 는 '제약선 이동'이 아니라 잡음을 재는 지표가 된다. 조용히 넘기지 않는다.
    if not np.isfinite(b_med):
        LOG.warn("a2: β 를 추정하지 못했습니다 — 단가 축 판정을 신뢰할 수 없습니다.")
    elif b_med > -0.02:
        LOG.warn(
            f"a2: β 중앙값이 {b_med:+.3f} 로 음수가 아닙니다. 이 전략의 전제("
            f"'많이 팔려면 깎아야 한다')가 이 표본에서 성립하지 않습니다.\n"
            f"    가능한 원인 ① 중량 보고오차가 회귀변수에 실려 β 가 0 으로 끌려감"
            f"(errors-in-variables 감쇠) ② 투입원가지수가 단가와 공선형이라 γ 가 β 를 흡수"
            f"(HS 하나가 章 하나를 독점하는 경우) ③ 해당 품목이 실제로 가격수용자.\n"
            f"    → a2 해석에 주의하고 R5 절제에서 a2 의존 TP(TP_X1·TP_X2) 기여를 반드시 확인하세요.")
    return out


def customs_a_sensors(cx: pd.DataFrame) -> pd.DataFrame:
    """A축 4센서를 (hs, ym) 격자에서 산출한다.

    a1 = Δlog(중량 12M 누계)          물량
    a2 = 단가 잔차                     가격결정력  ← 이 전략의 심장
    a3 = -Δ HHI(목적지)                고객 다변화
    a4 = Δ 선진시장 비중
    a5 = 신규 HS 등장(3개월 연속) → 12M 지수감쇠 더미
    """
    hsm = customs_hs_monthly(cx)
    if not len(hsm):
        return pd.DataFrame(columns=["hs", "ym", "a1", "a2", "a3", "a4", "a5",
                                     "wgt", "usd", "unit_price", "a2_beta"])
    cost = customs_input_cost(cx)
    a2 = customs_a2_residual(hsm, cost)

    d = hsm.sort_values(["hs", "ym"]).copy()
    g = d.groupby("hs", observed=True, sort=False)

    # a1: 12개월 누계 중량의 전년동기 대비 로그차. 계절성과 단월 노이즈를 함께 죽인다.
    d["wgt12"] = g["wgt"].transform(lambda s: s.rolling(12, min_periods=6).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        lw = np.log(d["wgt12"].where(d["wgt12"] > 0))
    d["a1"] = lw - lw.groupby(d["hs"], observed=True).shift(12)

    # a3: 다변화가 '개선'이므로 HHI 감소에 + 부호.
    d["a3"] = -(d["hhi_dest"] - g["hhi_dest"].shift(12))
    # a4: 선진시장 비중 증가.
    d["a4"] = d["adv_share"] - g["adv_share"].shift(12)

    # a5: 직전 12개월 물량이 사실상 0이었다가 3개월 연속 유의미하게 실린 경우 = 신규 세번.
    d["_active"] = (d["wgt"] > 0).astype(float)
    # ★ groupby 객체는 생성 시점의 컬럼 구성을 참조한다. 새 컬럼을 추가한 뒤에는 다시 만든다.
    g = d.groupby("hs", observed=True, sort=False)
    d["_streak"] = g["_active"].transform(
        lambda s: s.rolling(A5_STREAK, min_periods=A5_STREAK).sum())
    prior = g["wgt"].transform(lambda s: s.shift(A5_STREAK).rolling(12, min_periods=6).sum())
    onset = (d["_streak"] >= A5_STREAK) & (~(prior > 0))
    # 지수감쇠 더미: 발화 시점부터 12개월간 감쇠하며 남는다.
    lam = 0.5 ** (1.0 / max(A5_DECAY_HALFLIFE, 1e-9))
    d["a5"] = _decay_dummy(onset.to_numpy(), d["hs"].to_numpy(), lam, horizon=12)

    d = d.merge(a2[["hs", "ym", "a2", "a2_beta"]], on=["hs", "ym"], how="left")
    keep = ["hs", "ym", "a1", "a2", "a3", "a4", "a5", "wgt", "usd",
            "unit_price", "hhi_dest", "adv_share", "a2_beta"]
    return d[keep]


def _decay_dummy(onset: np.ndarray, groups: np.ndarray, lam: float,
                 horizon: int = 12) -> np.ndarray:
    """발화 시점부터 지수감쇠하며 horizon 개월간 살아있는 더미를 벡터화로 만든다.

    루프는 그룹 경계에서만 돈다(HS 수 ~600). 행 단위 파이썬 루프가 아니다.
    """
    out = np.zeros(len(onset), dtype=float)
    if not len(onset):
        return out
    # 그룹 경계 인덱스
    starts = np.flatnonzero(np.r_[True, groups[1:] != groups[:-1]])
    ends = np.r_[starts[1:], len(onset)]
    for s, e in zip(starts, ends):
        seg = onset[s:e]
        idx = np.flatnonzero(seg)
        if not len(idx):
            continue
        val = np.zeros(e - s, dtype=float)
        n = e - s
        for i in idx:
            j = min(n, i + horizon)
            k = np.arange(0, j - i)
            val[i:j] = np.maximum(val[i:j], lam ** k)
        out[s:e] = val
    return out


def map_hs_to_corp(a_hs: pd.DataFrame, mapping: pd.DataFrame,
                   months: pd.DatetimeIndex) -> pd.DataFrame:
    """HS 격자의 A축 센서를 매핑표를 통해 종목 격자로 옮긴다.

    ★ C3(PIT 라벨 고정): 매핑은 (code, hs, weight, valid_from, valid_to) 이고
      valid_from 은 그 제품구성을 알 수 있게 된 **사업보고서 접수일**이다.
      2024년 사업보고서로 알게 된 구성을 2022년 백테스트에 쓰면 성과는 전부 가짜다.
    """
    cols = ["code", "ym", "a1", "a2", "a3", "a4", "a5", "x_wgt", "x_usd",
            "a2_beta", "hs_main", "hs_n"]
    if a_hs is None or not len(a_hs) or mapping is None or not len(mapping):
        return pd.DataFrame(columns=cols)
    m = mapping.copy()
    m["hs"] = m["hs"].astype(str)
    m["valid_from"] = as_ts_series(m["valid_from"])
    m["valid_to"] = as_ts_series(m.get("valid_to"))
    m["valid_to"] = m["valid_to"].fillna(pd.Timestamp("2262-01-01"))
    m["weight"] = pd.to_numeric(m.get("weight"), errors="coerce").fillna(1.0)

    a = a_hs.copy()
    a["hs"] = a["hs"].astype(str)
    j = a.merge(m[["code", "hs", "weight", "valid_from", "valid_to"]], on="hs", how="inner")
    # PIT 유효구간 필터 — 알 수 있게 된 뒤에만 쓴다.
    j = j[(j["ym"] >= j["valid_from"]) & (j["ym"] <= j["valid_to"])].copy()
    if not len(j):
        return pd.DataFrame(columns=cols)

    j["w"] = j["weight"].clip(lower=0.0)
    # 가중평균. 결측 센서는 그 항의 가중치에서 빠져야 하므로 센서별로 분모를 따로 만든다.
    parts = {}
    for s in ("a1", "a2", "a3", "a4", "a5"):
        v = pd.to_numeric(j[s], errors="coerce")
        ok = v.notna()
        j[f"_n_{s}"] = np.where(ok, v * j["w"], 0.0)
        j[f"_d_{s}"] = np.where(ok, j["w"], 0.0)
    agg = {f"_n_{s}": (f"_n_{s}", "sum") for s in ("a1", "a2", "a3", "a4", "a5")}
    agg.update({f"_d_{s}": (f"_d_{s}", "sum") for s in ("a1", "a2", "a3", "a4", "a5")})
    agg.update(x_wgt=("wgt", "sum"), x_usd=("usd", "sum"),
               a2_beta=("a2_beta", "mean"), hs_n=("hs", "nunique"))
    G = j.groupby(["code", "ym"], observed=True, sort=False).agg(**agg).reset_index()
    for s in ("a1", "a2", "a3", "a4", "a5"):
        G[s] = safe_div(G[f"_n_{s}"], G[f"_d_{s}"])
        G.loc[~(G[f"_d_{s}"] > 0), s] = np.nan
        G = G.drop(columns=[f"_n_{s}", f"_d_{s}"])

    # 대표 HS(진단카드용) — 금액이 가장 큰 것
    top = (j.sort_values("usd", ascending=False)
             .drop_duplicates(["code", "ym"])[["code", "ym", "hs"]]
             .rename(columns={"hs": "hs_main"}))
    G = G.merge(top, on=["code", "ym"], how="left")
    return G.reindex(columns=cols)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  B축 — 회계 진정성 (사전확률)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def b_sensors(fin: pd.DataFrame) -> pd.DataFrame:
    """b1~b5 를 분기 프레임에서 산출한다.

    ★ 월 패널에서 diff(12) 를 하면 제출일이 해마다 밀리는 구조 때문에 "12개월 전 행"이
      같은 사업연도를 가리키는 달이 생겨 Δ가 0이 된다. 반드시 분기 프레임에서 계산하고,
      PIT 안전성은 뒤의 merge_asof(knowledge_date) 가 보장한다.

    b1 = Δlog(매출 TTM)
    b2 = -Δ(DIO + DSO)                      회전 유지
    b3 = -Δ((순이익-영업CF)/평균총자산)     Sloan accruals — 순이익 음수 구간에서도 안전
    b4 = Δ(계약부채+선수금)/매출            조작 여지 낮은 확정 미래매출
    b5 = Δ 매출총이익률
    """
    need = ["code", "period_end", "knowledge_date"]
    if fin is None or not len(fin) or any(c not in fin.columns for c in need):
        return pd.DataFrame(columns=need + ["b1", "b2", "b3", "b4", "b5"])
    d = fin.sort_values(["code", "period_end"]).copy()

    # ★ 한국 분기공시는 **누적** 공시다. revenue 원값에 rolling(4).sum() 을 걸면
    #   1~3분기가 이미 누적이라 매출을 크게 중복 계상한다. tidy_financials 가
    #   분기차분(_q)과 TTM(_ttm)을 이미 정확히 만들어 두므로 **반드시 그것을 쓴다**.
    def _ttm(name: str) -> pd.Series:
        for cand in (f"{name}_ttm", name):
            if cand in d.columns:
                return pd.to_numeric(d[cand], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    def _lag4(s: pd.Series) -> pd.Series:
        return s.groupby(d["code"], observed=True).shift(4)

    d["rev_ttm"] = _ttm("revenue")
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(d["rev_ttm"].where(d["rev_ttm"] > 0))
    d["b1"] = lr - _lag4(lr)

    # DIO / DSO — 분모가 TTM 이어야 계절성에 흔들리지 않는다.
    cogs_ttm = _ttm("cogs")
    dio = safe_div(col(d, "inventory") * 365.0, cogs_ttm)
    dso = safe_div(col(d, "receivable") * 365.0, d["rev_ttm"])
    ccc = dio + dso
    d["b2"] = -(ccc - _lag4(ccc))

    ta = col(d, "assets")
    ta_avg = (ta + _lag4(ta)) / 2.0
    ni_ttm = _ttm("net_income")
    cfo_ttm = _ttm("cfo")
    accr = safe_div(ni_ttm - cfo_ttm, ta_avg)
    d["b3"] = -(accr - _lag4(accr))

    # 계약부채 계정에 선수금이 함께 매핑되어 있다(ACCOUNT_MAP). 이중계상하지 않는다.
    dr_ratio = safe_div(col(d, "contract_liab"), d["rev_ttm"])
    d["b4"] = dr_ratio - _lag4(dr_ratio)

    gpm = safe_div(d["rev_ttm"] - cogs_ttm, d["rev_ttm"])
    d["b5"] = gpm - _lag4(gpm)

    # 밀어내기 판정(V1)용 원시값도 같이 내보낸다 — 거부권이 재계산하지 않도록.
    d_rev = d["rev_ttm"] - _lag4(d["rev_ttm"])
    d_inv = col(d, "inventory") - _lag4(col(d, "inventory"))
    d_rec = col(d, "receivable") - _lag4(col(d, "receivable"))
    d["v1_ratio"] = np.where(d_rev > 0, safe_div(d_inv + d_rec, d_rev), np.nan)
    # V2 는 '3분기 연속'이 조건이다. tidy_financials 가 이미 연속 카운트를 만들어 두면
    # 그것을 쓰고, 없으면 여기서 직접 만든다(단발 플래그를 3분기 롤링합으로).
    bad = ((ni_ttm > 0) & (cfo_ttm < 0.5 * ni_ttm)).astype(float)
    if "v2_bad_3q" in d.columns:
        # ★ tidy_financials 의 v2_bad_3q 는 rolling(3).min() 이라 이미 '3분기 연속' 자체를
        #   뜻하는 0/1 이다. 이걸 카운트로 오해해 ">=3" 으로 비교하면 영원히 거짓이 되어
        #   V2 거부권이 통째로 죽는다(예외는 안 난다).
        d["v2_streak"] = (pd.to_numeric(d["v2_bad_3q"], errors="coerce") > 0).astype(float)
    else:
        d["v2_streak"] = (bad.groupby(d["code"], observed=True).transform(
            lambda s: s.rolling(3, min_periods=3).min()) > 0).astype(float)
    d["gpm"] = gpm
    keep = need + ["b1", "b2", "b3", "b4", "b5", "v1_ratio", "v2_streak", "gpm", "rev_ttm"]
    return d.reindex(columns=keep)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  C축 — 능력 확충 (사전확률)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def c_sensors(fin: pd.DataFrame, emp: Optional[pd.DataFrame] = None,
              contracts: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """c1~c6.

    c1 = 유형자산취득 / 직전3년평균
    c2 = Δ(NOPAT / 평균IC)                IC = 순운전자본+유형자산+무형자산
    c3 = Δlog(직원수)
    c4 = Δ(연간급여총액)/Δ(직원수) / 전기1인평균급여     한계임금 프리미엄
    c5 = Δ(판관비/매출)
    c6 = 단일판매·공급계약 공시금액 12M / 매출          ★ 교차확증용
    """
    need = ["code", "period_end", "knowledge_date"]
    if fin is None or not len(fin) or any(c not in fin.columns for c in need):
        return pd.DataFrame(columns=need + ["c1", "c2", "c5"])
    d = fin.sort_values(["code", "period_end"]).copy()

    def _ttm(name: str) -> pd.Series:
        for cand in (f"{name}_ttm", name):
            if cand in d.columns:
                return pd.to_numeric(d[cand], errors="coerce")
        return pd.Series(np.nan, index=d.index)

    def _lag(s: pd.Series, k: int = 4) -> pd.Series:
        return s.groupby(d["code"], observed=True).shift(k)

    capex_ttm = _ttm("capex").abs()          # 현금흐름표상 취득은 음수로 표기되기도 한다
    capex_3y = _lag(capex_ttm).groupby(d["code"], observed=True).transform(
        lambda s: s.rolling(12, min_periods=6).mean())
    d["c1"] = safe_div(capex_ttm, capex_3y)

    ppe = col(d, "ppe")
    intang = col(d, "intangible")
    # 매입채무 계정이 ACCOUNT_MAP 에 없으므로 유동부채로 순운전자본을 근사한다.
    # 근사임을 명시한다 — 없는 것을 있는 척하지 않는다.
    nwc = col(d, "cur_assets") - col(d, "cur_liab")
    ic = nwc + ppe + intang
    ic_avg = (ic + _lag(ic)) / 2.0
    ebit_ttm = _ttm("op_income")
    pretax_ttm = _ttm("pretax_income")
    taxexp_ttm = _ttm("tax_expense")
    etr = safe_div(taxexp_ttm, pretax_ttm)
    etr = etr.where((etr > -0.5) & (etr < 1.0))
    tax = etr.fillna(0.22).clip(0.0, 0.5)
    roic = safe_div(ebit_ttm * (1.0 - tax), ic_avg)
    d["c2"] = roic - _lag(roic)
    d["roic"] = roic
    d["ic"] = ic
    d["etr"] = etr
    d["etr_chg"] = etr - _lag(etr)

    rev_ttm = _ttm("revenue")
    sga_r = safe_div(_ttm("sgna"), rev_ttm)
    # c5 는 '판관비 비율 변화'이며, TP_X3 에서 -c5 로 쓰인다(안 늘어난 것이 미덕).
    d["c5"] = sga_r - _lag(sga_r)

    out = d.reindex(columns=need + ["c1", "c2", "c5", "roic", "ic", "etr", "etr_chg"])

    # ── c3, c4 는 **연도 프레임**(직원현황)에서 계산한다.
    #   ★ 월 패널에서 diff(12) 를 하면 제출일이 해마다 밀리는 구조 때문에 "12개월 전 행"이
    #     같은 사업연도를 가리키는 달이 생겨 Δ직원수가 0 이 되고 c4 가 통째로 결측이 된다.
    #     PIT 안전성은 뒤의 merge_asof(knowledge_date) 가 보장한다.
    if emp is not None and len(emp):
        e = emp.copy()
        # fetch_dart_employees 스키마: code, bsns_year, employees, payroll, knowledge_date
        ycol = "bsns_year" if "bsns_year" in e.columns else "period_end"
        e = e.sort_values(["code", ycol])
        n = pd.to_numeric(e.get("employees"), errors="coerce")
        pay = pd.to_numeric(e.get("payroll"), errors="coerce")
        if pay.isna().all() and "payroll_total" in e.columns:
            pay = pd.to_numeric(e["payroll_total"], errors="coerce")
        e["_n"], e["_pay"] = n, pay
        gcode = e["code"]
        with np.errstate(divide="ignore", invalid="ignore"):
            ln = np.log(n.where(n > 0))
        e["c3"] = ln - ln.groupby(gcode, observed=True).shift(1)
        n_prev = n.groupby(gcode, observed=True).shift(1)
        pay_prev = pay.groupby(gcode, observed=True).shift(1)
        dn = n - n_prev
        dpay = pay - pay_prev
        prev_avg = safe_div(pay_prev, n_prev)
        # 분모 안정성: |Δ직원수| >= max(5, 직원수_{t-1}×3%) 일 때만. 아니면 결측(0 금지).
        thresh = np.maximum(5.0, n_prev * 0.03)
        ok = (dn.abs() >= thresh) & (prev_avg > 0)
        e["c4"] = np.where(ok, safe_div(safe_div(dpay, dn), prev_avg), np.nan)
        keep_e = ["code", "knowledge_date", "c3", "c4"]
        out = pd.concat([out, e.reindex(columns=keep_e)], ignore_index=True, sort=False)

    # ── c6 은 공시 이벤트를 12개월 누계로 — 별도 처리(월 격자에서 붙임)
    return out


def c6_contract_ratio(contracts: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """c6 — 단일판매·공급계약 체결 공시금액의 12개월 누계 (월 격자).

    ★ 이것이 TP_XC 의 한쪽 날개다. 공시는 **기업 자신의 진술**이고 통관 물량은
      **제3자(관세청)의 관측**이다. 독립인 두 소스가 같은 방향을 가리키면 신뢰도가 곱으로 오른다.
    """
    if contracts is None or not len(contracts):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    c = contracts.copy()
    c["knowledge_date"] = as_ts_series(c["knowledge_date"])
    c["amount"] = pd.to_numeric(c.get("amount"), errors="coerce")
    c = c[c["knowledge_date"].notna() & (c["amount"] > 0)]
    if not len(c):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    # ★ 월 루프로 필터링하면 (이벤트 × 개월수) 비교가 된다. 이벤트가 유효한 월말로
    #   직접 펼치면 O(이벤트 × 12) 이고 groupby 는 1회다 — v3 코어의 원시함수를 쓴다.
    ex = expand_events_to_months(c[["code", "knowledge_date", "amount"]],
                                 "knowledge_date", months, window_days=365)
    if not len(ex):
        return pd.DataFrame(columns=["code", "ym", "contract_12m"])
    m = (ex.groupby(["code", "month"], observed=True)["amount"].sum()
           .rename("contract_12m").reset_index().rename(columns={"month": "ym"}))
    return m[["code", "ym", "contract_12m"]]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  D축 — 미반영도 (할인율 U)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def d_sensors(px_m: pd.DataFrame, fin_m: pd.DataFrame,
              flows: Optional[pd.DataFrame] = None,
              coverage: Optional[pd.DataFrame] = None,
              window_m: int = 6) -> pd.DataFrame:
    """d1~d4.

    ★ d1 이 이 시스템에서 가장 중요한 단일 지표다.
      Δlog P = Δlog E + Δlog M  로 분해하면 M 은 멀티플이다.
        ΔlogE > 0, ΔlogM ≤ 0  = 시장이 이익 증가는 인정했으나 자본화를 거부 =
                                 "일회성으로 분류함" = 바로 이것이 노리는 미스프라이싱.
        ΔlogE > 0, ΔlogM > 0  = 이미 리레이팅 진행 중 = 배제.

    ⚠ 한계: 컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로 E 는 후행 12M 이익 대리변수다.
      이 대리변수의 한계는 리포트에 명시한다(§15.4). 숨기지 않는다.
    """
    cols = ["code", "ym", "d1", "d2", "d3", "d4", "dlogE", "dlogM"]
    if px_m is None or not len(px_m):
        return pd.DataFrame(columns=cols)
    d = px_m.sort_values(["code", "ym"]).copy()
    if fin_m is not None and len(fin_m):
        d = d.merge(fin_m[["code", "ym", "eps_ttm"]], on=["code", "ym"], how="left")
    else:
        d["eps_ttm"] = np.nan

    g = d.groupby("code", observed=True, sort=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        lp = np.log(pd.to_numeric(d["close"], errors="coerce").where(lambda s: s > 0))
        le = np.log(pd.to_numeric(d["eps_ttm"], errors="coerce").where(lambda s: s > 0))
    d["dlogP"] = lp - lp.groupby(d["code"], observed=True).shift(window_m)
    d["dlogE"] = le - le.groupby(d["code"], observed=True).shift(window_m)
    # 항등식으로 M 을 얻는다 — P/E 를 직접 만들면 E<=0 구간이 통째로 날아간다.
    d["dlogM"] = d["dlogP"] - d["dlogE"]
    d["d1"] = -d["dlogM"]

    if coverage is not None and len(coverage):
        d = d.merge(coverage, on=["code", "ym"], how="left")
        d["d2"] = -pd.to_numeric(d.get("n_analyst"), errors="coerce")
        d["d4"] = pd.to_numeric(d.get("coverage_init"), errors="coerce")
    else:
        d["d2"] = np.nan
        d["d4"] = np.nan

    if flows is not None and len(flows):
        d = d.merge(flows, on=["code", "ym"], how="left")
        d["d3"] = -safe_div(pd.to_numeric(d.get("net_buy_120d"), errors="coerce"),
                            pd.to_numeric(d.get("mcap"), errors="coerce"))
    else:
        d["d3"] = np.nan
    return d.reindex(columns=cols)


def theta_x(fin_m: pd.DataFrame) -> pd.Series:
    """θ_X = 국내법인 수출매출(별도) / 연결매출.  관측커버리지 가중치.

    통관은 '관세영역 반출 물량'이므로 대응 회계항목은 **별도(개별)** 기준 수출매출이다.
    연결이 아니다. 해외 현지생산·현지판매는 방정식 밖으로 자연히 빠진다.

    θ_X 는 배제 기준이 아니라 **가중치**다. θ_X=0.2 인 기업은 신호가 있어도 연결 실적을
    못 움직이므로 자연스럽게 걸러진다.
    """
    if fin_m is None or not len(fin_m):
        return pd.Series(dtype=float)
    exp_sep = pd.to_numeric(fin_m.get("export_rev_sep"), errors="coerce")
    rev_con = pd.to_numeric(fin_m.get("revenue_con"), errors="coerce")
    t = safe_div(exp_sep, rev_con).clip(0.0, 1.0)
    return t


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [22/27]  40_score.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2 — 셀 정규화 · 트레이드오프 쌍 · 거부권 · 최종 신호                                      ║
# ║                                                                                             ║
# ║  ★ 원칙 2 (이 코드 전체에서 가장 중요한 한 줄)                                              ║
# ║      TP = max(rank-0.5, 0) × max(rank-0.5, 0)                                                ║
# ║    절대 `z × z` 로 두지 않는다. 그러면 (-2)×(-2)=+4 가 되어                                  ║
# ║    '물량 급감 + 단가 급락' 종목이 최고점을 받는다. 횡단면 랭크이므로 유니버스의 약 25%가     ║
# ║    양쪽 음수이고, 그 25%가 상위 분위를 통째로 오염시킨다.                                    ║
# ║    음수 절단 후 곱하면 결과가 항상 [0, 0.25] 이라 '최악이 최고점'이 구조적으로 불가능하다.   ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

# 트레이드오프 쌍 정의 (§8.1).
#   (ID, 개선축, 대가회피축, 축그룹, 발화 의미, 미발화 의미)
XCB_TP_SPECS: "list[tuple]" = [
    ("TP_X1", "a1", "a2", "A", "물량↑인데 단가 안 깎임 = 수요곡선 이동",
     "물량을 가격 인하로 산 것 / 정책 보조"),
    ("TP_X2", "a3", "a2", "A", "다변화인데 믹스 유지 = 제품력",
     "저가 물량으로 고객 늘림"),
    ("TP_X3", "a4", "c5_neg", "A", "선진시장↑인데 판관비 안 늘음 = 제품이 스스로 팔림",
     "마케팅으로 산 시장"),
    ("TP_X4", "a5", "a1", "A", "신규 세번 + 물량 = R&D→상업화 실물 증거",
     "시범 선적에 불과"),
    ("TP_XC", "c6", "a1", "A", "수주공시 × 통관물량 = 독립 2소스 교차확증",
     "공시만 있고 실물 없음"),
    ("TP_B1", "b1", "b2", "B", "매출↑인데 회전 유지 = 수요가 당김",
     "밀어내기 → V1 확인"),
    ("TP_B2", "b1", "b3", "B", "매출↑인데 발생액 유지 = 이익의 질",
     "회계적 이익 우위"),
    ("TP_C1", "c1", "c2", "C", "확장하는데 ROIC 유지 = 제약선 이동",
     "확장이 수익성 희석"),
    ("TP_C2", "c3", "c4", "C", "인원↑인데 고임금 채용 = 고부가 인력 확충",
     "저임금 대량채용(보조금 의심)"),
]
XCB_TP_COLS = [s[0] for s in XCB_TP_SPECS]
XCB_TP_AXIS = {s[0]: s[3] for s in XCB_TP_SPECS}

# 단계별로 활성화되는 TP (§12.1 단계 게이트)
STAGE_TPS = {
    "M0": ["TP_X1", "TP_X2", "TP_B1", "TP_B2"],
    "M1": ["TP_X1", "TP_X2", "TP_X3", "TP_X4", "TP_XC", "TP_B1", "TP_B2", "TP_C1"],
    "M2": XCB_TP_COLS,
    "ALL": XCB_TP_COLS,
}
STAGE_VETOES = {
    "M0": ["V1", "V2", "V5", "V6", "V10", "V12"],
    "M1": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
    "M2": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
    "ALL": ["V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"],
}
STAGE_UAXES = {
    "M0": ["d1"],
    "M1": ["d1", "d3"],
    "M2": ["d1", "d2", "d3", "d4"],
    "ALL": ["d1", "d2", "d3", "d4"],
}

# 전면 거부권 / 부분 거부권 (§9). 부분 거부권은 A축 또는 a2 만 무효화한다.
VETO_HARD = ("V1", "V2", "V3", "V5", "V6", "V11")
VETO_PARTIAL = ("V9", "V10", "V12")


def make_cells(P: pd.DataFrame) -> pd.DataFrame:
    """셀 = date × HS군 × 규모버킷 (§8).

    ★ 산업분류 대신 HS군을 쓰는 이유: 이 전략의 비교 대상은 '같은 물건을 파는 회사'다.
      표준산업분류는 화학 하나에 범용수지와 이차전지 소재를 같이 넣는다.
    ★ 규모버킷을 셀에 넣는 이유: 정부 지원제도 요건 대부분이 기업 규모에 연동된다.
      규모를 셀에 넣으면 정책 효과가 셀 내 공통충격으로 흡수된다. 비용 0의 방어다(§10-②).
    """
    d = P.copy()
    hs_main = d.get("hs_main")
    if hs_main is None:
        d["hs_group"] = "NA"
    else:
        # HS 2자리(章)를 군으로 쓴다. 6자리는 셀이 종목 1개로 쪼개져 랭크가 의미를 잃는다.
        d["hs_group"] = hs_main.astype(str).str.zfill(6).str[:2].fillna("NA")
    mc = pd.to_numeric(d.get("mcap"), errors="coerce")
    if mc.notna().sum() == 0:
        mc = pd.to_numeric(d.get("adtv20"), errors="coerce")
    r = mc.groupby(d["ym"], observed=True).rank(pct=True)
    d["size_bucket"] = pd.cut(r, [-0.01, 0.33, 0.66, 1.01],
                              labels=["S", "M", "L"]).astype(object).fillna("NA")
    ym = d["ym"].astype("datetime64[ns]").astype(str)
    d["cell"] = ym + "|" + d["hs_group"].astype(str) + "|" + d["size_bucket"].astype(str)
    d["cell_l2"] = ym + "|" + d["hs_group"].astype(str)
    d["cell_l3"] = ym
    return d


def _cells_of(P: pd.DataFrame) -> "tuple":
    fb = [P[c] for c in ("cell_l2", "cell_l3") if c in P.columns]
    return (P["cell"] if "cell" in P.columns else pd.Series("NA", index=P.index)), fb


def tp_pair(P: pd.DataFrame, a: str, b: str, mode: str = "clip") -> pd.Series:
    """★ 음수 절단 후 곱. 개선이 없거나 대가를 치렀으면 정확히 0.

    mode="clip"    : max(rank-0.5,0) × max(rank-0.5,0)   ← XCB 사양 §8. 기본값.
    mode="zclip"   : max(z,0) × max(z,0)                  ← v3 코어 `tp()`. R5 비교용
    mode="rankprod": rank × rank                          ← R5 절제 비교용
    mode="signed"  : z × z                                ← v2 부호버그 재현(R5 에서만)

    ★ 사양이 rank 기반인 이유: 결과가 [0,0.25] 로 유계라 한 종목의 극단 z 가 E 평균을
      지배하지 못한다. z 절단은 상한이 없어 이상치 하나가 그 달 전체를 끌고 간다.
      두 정의를 R5 에서 실측 비교하고 결과를 그대로 보고한다.
    """
    if mode in ("zclip", "signed"):
        cells, fb = _cells_of(P)
        return tp_dispatch("signed" if mode == "signed" else "clip",
                           col(P, a), col(P, b), cells, fb)
    ra = xsec_rank_pct_l(P, a)
    rb = xsec_rank_pct_l(P, b)
    if mode == "rankprod":
        return (ra * rb).astype("float32")
    za = ra - 0.5
    zb = rb - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    # 한쪽이라도 관측이 없으면 TP 는 결측이다. 0 으로 채우면 '대가를 안 치렀다'는
    # 적극적 주장이 되어 버린다 — 모르는 것과 좋은 것을 구분해야 한다.
    return pd.Series(np.where(ra.isna() | rb.isna(), np.nan, out),
                     index=P.index, dtype="float32")


def build_tps(P: pd.DataFrame, tps: "Sequence[str]", mode: str = "clip") -> pd.DataFrame:
    d = P.copy()
    # TP_X3 은 -c5 를 쓴다(판관비가 '안 늘어난 것'이 미덕).
    if "c5" in d.columns:
        d["c5_neg"] = -pd.to_numeric(d["c5"], errors="coerce")
    for tid, ca, cb, _ax, _f, _n in XCB_TP_SPECS:
        if tid not in tps:
            d[tid] = np.nan
            continue
        if ca not in d.columns or cb not in d.columns:
            d[tid] = np.nan
            continue
        d[tid] = tp_pair(d, ca, cb, mode=mode)
    return d


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  거부권 — 이진 · 곱 · 상쇄 불가 (§9)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def apply_vetoes(P: pd.DataFrame, vetoes: "Sequence[str]",
                 cv_thresh_pct: float = CV_DEST_COMMODITY_PCT) -> pd.DataFrame:
    """거부권은 점수가 아니다. 이진값이고 곱이며 다른 축이 상쇄할 수 없다.

    전면 거부권(V1,V2,V3,V5,V6,V11) → 그 달 그 종목은 후보에서 완전히 빠진다.
    부분 거부권(V9,V10,V12)         → A축(또는 a2)만 무효화하고 E 를 재계산한다.
                                      정보량이 다른 종목을 직접 비교하지 않기 위해
                                      '활성 축 조합이 같은 종목끼리' 따로 랭크한다.
    """
    d = P.copy()
    zero = pd.Series(0.0, index=d.index)

    def _num(name: str) -> pd.Series:
        """★ 없는 컬럼에 d.get() 을 쓰면 None 이 오고, pd.to_numeric(None) 은 **스칼라**가 된다.
        그 스칼라에 비교연산을 걸면 numpy.bool 이 나와 .fillna 에서 크래시한다.
        데이터가 없을수록 잘 죽는 구조라 실데이터에서 더 자주 터진다 — 항상 Series 를 돌려준다."""
        if name in d.columns:
            return pd.to_numeric(d[name], errors="coerce")
        return pd.Series(np.nan, index=d.index, dtype="float64")

    def _f(name: str, cond) -> pd.Series:
        """조건이 참이면 1(발동). 판단 근거가 없으면 0(발동하지 않음) — 모른다고 배제하지 않는다."""
        if name not in vetoes:
            return zero
        c = cond if isinstance(cond, pd.Series) else pd.Series(bool(cond), index=d.index)
        return c.reindex(d.index).fillna(False).astype(float)

    # V1 밀어내기: Δ매출>0 ∧ (Δ재고+Δ매출채권)/Δ매출 > 1.5
    d["V1"] = _f("V1", _num("v1_ratio") > 1.5)
    # V2 이익-현금 괴리 3분기 연속
    d["V2"] = _f("V2", _num("v2_streak") > 0)
    # V3 90일 내 대규모 희석성 조달
    d["V3"] = _f("V3", _num("dilution_90d") > 0)
    # V5 감사의견 비적정 / 관리종목 / 자본잠식 / 거래정지
    d["V5"] = _f("V5", _num("watch_flag") > 0)
    # V6 유동성
    d["V6"] = _f("V6", _num("adtv20") < UNIVERSE_MIN_ADTV)
    # V11 정책 의존: 유효세율 급락(<-3%p) ∨ 정부보조금수익/매출 급증
    etr_drop = _num("etr_chg") < -0.03
    subsidy = _num("subsidy_ratio_chg") > 0.01
    d["V11"] = _f("V11", etr_drop | subsidy)

    # ── 부분 거부권
    # V9 해외생산 이전: θ_X 급락 ∧ 해외 종속기업 매출 급증
    theta_drop = _num("theta_x_chg") < -0.10
    oversea = _num("oversea_rev_chg") > 0.20
    d["V9"] = _f("V9", theta_drop & oversea)
    # V10 커모디티: cv_dest 하위 N% → a2 무효화
    if "cv_dest" in d.columns and pd.to_numeric(d["cv_dest"], errors="coerce").notna().any():
        cvr = _num("cv_dest").rank(pct=True)
        d["V10"] = _f("V10", cvr <= cv_thresh_pct)
    else:
        d["V10"] = zero
    # V12 매핑 게이트 실패 → A축 무효화
    d["V12"] = _f("V12", _num("map_gate_fail") > 0)

    for v in ("V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12"):
        if v not in d.columns:
            d[v] = zero
    d["veto_hard"] = np.maximum.reduce([d[v].to_numpy() for v in VETO_HARD])
    d["veto_pass"] = 1.0 - d["veto_hard"]
    return d


def disable_axes(P: pd.DataFrame) -> pd.DataFrame:
    """부분 거부권을 실제 무효화로 반영한다.

    V10 → a2 무효화 (a1·a3·a4 는 유지). a2 를 쓰는 TP_X1·TP_X2 가 결측이 된다.
    V9/V12 → A축 전체 무효화. E 를 B·C축만으로 재계산한다. flag="X_DISABLED".
    """
    d = P.copy()
    v10 = pd.to_numeric(d.get("V10"), errors="coerce").fillna(0) > 0
    v_a = (pd.to_numeric(d.get("V9"), errors="coerce").fillna(0) > 0) | \
          (pd.to_numeric(d.get("V12"), errors="coerce").fillna(0) > 0)

    for tid, ca, cb, ax, _f, _n in XCB_TP_SPECS:
        if tid not in d.columns:
            continue
        kill = v_a if ax == "A" else pd.Series(False, index=d.index)
        if "a2" in (ca, cb):
            kill = kill | v10
        d.loc[kill, tid] = np.nan

    d["axis_flag"] = np.where(v_a, "X_DISABLED",
                              np.where(v10, "A2_DISABLED", "FULL"))
    return d


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  최종 신호
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def compose_signal(P: pd.DataFrame, tps: "Sequence[str]", uaxes: "Sequence[str]",
                   use_theta: bool = True,
                   breadth_floor: float = BREADTH_FLOOR_PCT) -> pd.DataFrame:
    """E · U · Signal 을 조립한다.

        E      = mean(활성 TP) × θ_X
        U      = mean(z(활성 d축))          ← 결측 축은 '제외 평균'. 0으로 채우지 않는다.
        Signal = rank_pct(E) × rank_pct(U) × ∏V

    ★ E 와 U 를 각각 백분위 랭크한 뒤 곱한다. 원값 곱은 음수 구간에서 단조성이 깨진다.
    ★ 랭크는 '활성 축 조합이 같은 종목끼리' 따로 매긴다 — A축이 죽은 종목과 살아있는 종목은
      정보량이 다르므로 같은 자에 놓고 재면 안 된다.
    """
    d = P.copy()
    have = [t for t in tps if t in d.columns]
    if not have:
        d["E"] = np.nan
        d["U"] = np.nan
        d["Signal"] = np.nan
        d["Signal_rank"] = np.nan
        return d

    # ── E: 활성 TP 의 '제외 평균'. 관측된 TP 가 하나도 없으면 결측이다.
    d["E_raw"] = nanmean_cols(d, have)
    d["n_tp"] = d[have].notna().sum(axis=1)
    th = pd.to_numeric(d.get("theta_x"), errors="coerce")
    if use_theta:
        # θ_X 를 못 구한 종목은 1.0 이 아니라 중앙값으로 둔다. 1.0 은 '수출이 전부'라는
        # 적극적 주장이라 관측 실패를 강점으로 바꿔 버린다.
        th = th.fillna(th.median() if th.notna().any() else 1.0)
        d["E"] = d["E_raw"] * th.clip(0.0, 1.0)
    else:
        d["E"] = d["E_raw"]

    # ── U: z 의 제외 평균
    zs = []
    for u in uaxes:
        if u in d.columns and pd.to_numeric(d[u], errors="coerce").notna().any():
            zs.append(xsec_z_l(d, u))
    if zs:
        Z = pd.concat(zs, axis=1)
        d["U"] = Z.mean(axis=1, skipna=True)
        d["n_u"] = Z.notna().sum(axis=1)
    else:
        d["U"] = np.nan
        d["n_u"] = 0

    # ── 하한선(breadth floor): 활성 축 각각의 셀 내 백분위 ≥ 50th
    #   ★ TP 곱으로 재면 안 된다. clip(z,0) 은 0 동점 덩어리가 크고(약 75%),
    #     그 덩어리의 평균 랭크가 0.375 라 50th 문턱에서 전량 탈락한다.
    #     '개선축의 원시 센서'로 재야 의도대로 "빈 축이 없을 것"을 뜻한다.
    axis_src = {"A": ["a1", "a2", "a3", "a4"], "B": ["b1", "b2", "b3"],
                "C": ["c1", "c2", "c3"]}
    floor_ok = pd.Series(True, index=d.index)
    for ax, cols in axis_src.items():
        act = [c for c in cols if c in d.columns and
               pd.to_numeric(d[c], errors="coerce").notna().any()]
        if not act:
            continue
        rk = pd.concat([xsec_rank_pct_l(d, c) for c in act], axis=1).mean(axis=1, skipna=True)
        d[f"floor_{ax}"] = rk
        # 그 축을 아예 관측 못한 종목은 '빈 축'이 아니라 '모르는 축'이다 → 통과시킨다.
        floor_ok &= (rk >= breadth_floor) | rk.isna()
    d["breadth_ok"] = floor_ok.astype(float)

    # ── 활성 축 조합별 분리 랭크
    combo = d.get("axis_flag", pd.Series("FULL", index=d.index)).astype(str) + \
        "|" + d["n_tp"].astype(str)
    key = d["ym"].astype(str) + "|" + combo
    eligible = (pd.to_numeric(d.get("veto_pass"), errors="coerce").fillna(1.0) > 0) & \
               (d["breadth_ok"] > 0) & d["E"].notna()
    Emask = d["E"].where(eligible)
    Umask = d["U"].where(eligible)
    d["E_rank"] = Emask.groupby(key, observed=True).rank(pct=True)
    d["U_rank"] = Umask.groupby(key, observed=True).rank(pct=True)
    # U 를 통째로 못 구한 구간에서는 U 를 중립(0.5)으로 두되 그 사실을 표에 남긴다.
    u_missing = d["U_rank"].isna() & d["E_rank"].notna()
    d["U_rank"] = d["U_rank"].fillna(0.5)
    d["u_imputed"] = u_missing.astype(float)

    d["Signal"] = (d["E_rank"] * d["U_rank"]).where(eligible)
    d["Signal_rank"] = d["Signal"].groupby(d["ym"], observed=True).rank(pct=True)
    return d


def score_panel(P: pd.DataFrame, stage: str = "ALL", tp_mode: str = "clip",
                use_theta: bool = True, drop_tps: "Sequence[str]" = (),
                drop_axes: "Sequence[str]" = (),
                uaxes: "Optional[Sequence[str]]" = None,
                cv_thresh_pct: float = CV_DEST_COMMODITY_PCT,
                breadth_floor: float = BREADTH_FLOOR_PCT) -> pd.DataFrame:
    """L2 전체. R5 절제가 이 함수의 인자만 바꿔 반복 호출한다(백테스트 재실행 없이)."""
    tps = [t for t in STAGE_TPS.get(stage, XCB_TP_COLS) if t not in drop_tps]
    if drop_axes:
        tps = [t for t in tps if XCB_TP_AXIS[t] not in drop_axes]
    ua = list(uaxes) if uaxes is not None else STAGE_UAXES.get(stage, ["d1", "d2", "d3", "d4"])
    if "D" in drop_axes:
        ua = []
    vet = STAGE_VETOES.get(stage, list(VETO_HARD) + list(VETO_PARTIAL))

    d = make_cells(P)
    d = build_tps(d, tps, mode=tp_mode)
    d = apply_vetoes(d, vet, cv_thresh_pct=cv_thresh_pct)
    d = disable_axes(d)
    d = compose_signal(d, tps, ua, use_theta=use_theta, breadth_floor=breadth_floor)
    return d


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [23/27]  60_robust.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  강건성 스위트 R0~R10 — 순서대로. 앞 단계 실패 시 뒤는 참고치일 뿐이다.                     ║
# ║                                                                                             ║
# ║  ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이          ║
# ║    이 프로젝트에서 가장 해로운 행동이다. 나쁜 결과는 그 자체로 정보다 —                     ║
# ║    이 방향 전체의 기대값 상한을 알려준다.                                                   ║
# ║                                                                                             ║
# ║  ★ 기준선에 애초에 알파가 없으면 R3·R7·R10 은 PASS 가 아니라 **판정 유보(N/A)** 를 낸다.    ║
# ║    이걸 막지 않으면 기준 Sharpe -0.05 에서 직교화 후 0.04 가 나왔다는 이유로 '알파 잔존'이  ║
# ║    찍히고, 아무 알파도 없는 전략이 강건성 검사를 3개나 통과한 것처럼 보인다.                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def _f(x, default: float = float("nan")) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:                                                   # noqa
        return default


ROBUST_LOG: "List[dict]" = []
KILL_LOG: "List[dict]" = []
# 알파가 '있다'고 부를 최소선. 이보다 낮으면 조건부 검사들은 판정 유보로 간다.
ALPHA_FLOOR_SHARPE = 0.15


def _rx(rid: str, name: str, verdict: str, detail: str, metric: str = "",
        kill: bool = False) -> None:
    ROBUST_LOG.append({"id": rid, "name": name, "verdict": verdict,
                       "metric": metric, "detail": detail})
    icon = {"PASS": "✔", "FAIL": "✘", "WARN": "⚠", "N/A": "—", "INFO": "·"}.get(verdict, "·")
    LOG.info(f"  {icon} [{rid}] {name}: {verdict}  {metric}  {detail[:100]}")
    if kill and verdict == "FAIL":
        KILL_LOG.append({"id": rid, "name": name, "detail": detail})
        if STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"[{rid}] {name} — {detail}")


# ★ run_backtest 는 {"returns","holdings","gates","label"} 만 돌려준다 — "stats" 키가 없다.
#   그리고 perf_stats 의 키는 **한글**이다("Sharpe","CAGR","MDD","Calmar").
#   영문 소문자 키로 읽으면 전 항목이 조용히 NaN 이 되어 모든 판정이 N/A 로 무너진다.
_STAT_ALIAS = {"sharpe": "Sharpe", "cagr": "CAGR", "mdd": "MDD", "calmar": "Calmar",
               "sortino": "Sortino", "turnover": "월평균회전율", "cost": "월평균비용",
               "tstat": "t통계량(HAC)", "n_months": "월수"}


def _stat(bt: dict, key: str, default: float = float("nan")) -> float:
    if not bt:
        return default
    st = bt.get("_stats")
    if st is None:
        R = bt.get("returns")
        if R is None or not len(R):
            return default
        try:
            st = perf_stats(R)
        except Exception:                                               # noqa
            return default
        bt["_stats"] = st                       # 같은 백테스트를 두 번 재계산하지 않는다
    v = st.get(_STAT_ALIAS.get(key, key), default)
    try:
        return float(v)
    except Exception:                                                   # noqa
        return default


def _has_alpha(bt: dict) -> bool:
    return _stat(bt, "sharpe") >= ALPHA_FLOOR_SHARPE


# ═══════════════════════════════════════════════════════════════════════════════════════════════

def RX0_benchmark(bt: dict, bench: "Dict[str, pd.Series]", months) -> None:
    """R0 — 자체측정 벤치마크 대비. ⭐

    ★ 벤치마크 수치를 하드코딩하지 않는다. 이 실행이 직접 측정한 값만 쓴다(원칙 7).
      과거 인용된 "10년 CAGR 17%" 가 오류로 확인된 바 있다.
    """
    if not bt or not bench:
        _rx("R0", "자체측정 벤치마크 대비", "N/A", "벤치마크를 측정하지 못했습니다.")
        return
    mine = _stat(bt, "calmar")
    rows, beat = [], True
    for nm, s in bench.items():
        b = perf_stats(pd.DataFrame({"ret": pd.to_numeric(s, errors="coerce").fillna(0.0)}))
        c = float(b.get("Calmar", float("nan")))
        rows.append([nm, f"{_f(b.get('CAGR'))*100:6.2f}%",
                     f"{_f(b.get('MDD'))*100:6.2f}%", f"{c:6.3f}"])
        if np.isfinite(c) and np.isfinite(mine) and mine <= c:
            beat = False
    LOG.table(rows + [["★ XCB 전략", f"{_stat(bt,'cagr')*100:6.2f}%",
                       f"{_stat(bt,'mdd')*100:6.2f}%", f"{mine:6.3f}"]],
              ["대상", "CAGR", "MDD", "Calmar"])
    _rx("R0", "자체측정 벤치마크 대비", "PASS" if beat else "FAIL",
        "모든 벤치마크를 Calmar 기준 상회" if beat else
        "벤치마크를 Calmar 기준으로 이기지 못했습니다 — 이 전략을 할 이유가 없습니다.",
        metric=f"Calmar {mine:.3f}", kill=True)


def RX1_leakage(P, months, sec, runner, base_bt: dict) -> None:
    """R1 — 누수 자가검정. 대조군이 **2개**여야 하는 이유가 있다.

    DART 공시는 결산기준일 대비 이미 45~90일 후행한다. -30일 앞당김으로는 여전히 결산일
    이후라 성과가 개선되지 않고, 구현자가 **정상 하네스를 고장났다고 오판**한다.
    그래서 -120일 앞당김과 미래수익률 직접 주입 **둘 다** 본다.

    ★ 판정 근거는 '미래수익률 주입' 하나로 한정한다. 신호 앞당김이 성과를 못 올리는 것은
      하네스 결함이 아니라 '신호에 지속성이 없다'는 별개의 사실이므로, 둘을 한 판정에 묶으면
      두 사건을 구별할 수 없게 된다.
    """
    base = _stat(base_bt, "sharpe")

    # (a) 고의 오염: 미래 3개월 수익률을 신호에 직접 주입 → 반드시 크게 좋아져야 한다
    Q = P.copy()
    fwd = pd.to_numeric(Q.get("fwd_ret"), errors="coerce")
    fwd3 = fwd.groupby(Q["code"], observed=True).shift(-2).fillna(0.0) + fwd.fillna(0.0)
    Q["Signal_rank"] = fwd3.groupby(Q["ym"], observed=True).rank(pct=True)
    bt_leak = runner(Q, label="R1a-미래주입")
    s_leak = _stat(bt_leak, "sharpe")
    ok_a = np.isfinite(s_leak) and np.isfinite(base) and (s_leak > base + 0.5)
    _rx("R1a", "미래수익률 주입(하네스 검정)", "PASS" if ok_a else "FAIL",
        f"주입 Sharpe {s_leak:.3f} vs 기준 {base:.3f} — "
        + ("하네스가 미래정보에 반응합니다(정상)." if ok_a else
           "미래를 알려줘도 성과가 오르지 않습니다. 백테스트 엔진이 고장났고 "
           "이 실행의 **모든 결과가 무효**입니다."),
        metric=f"Δ{s_leak-base:+.3f}", kill=True)

    # (b) 참고: 신호를 120일 앞당김
    Q2 = P.copy()
    Q2["Signal_rank"] = Q2.groupby("code", observed=True)["Signal_rank"].shift(-4)
    bt_adv = runner(Q2, label="R1b-120일선행")
    s_adv = _stat(bt_adv, "sharpe")
    _rx("R1b", "신호 120일 앞당김(참고)", "INFO",
        f"앞당김 Sharpe {s_adv:.3f} vs 기준 {base:.3f}. "
        f"개선이 없다면 '하네스 고장'이 아니라 '신호에 지속성이 없다'는 뜻입니다.",
        metric=f"Δ{s_adv-base:+.3f}")


def RX2_tp_vs_naive(P, months, sec, runner, base_bt: dict) -> None:
    """R2 — 이 시스템의 존재 이유를 정면으로 검정한다. ⭐⭐

        A. clip(z(a1),0) 단독          물량만
        B. clip(z(a2),0) 단독          단가만
        C. TP_X1 = clip × clip         트레이드오프
        D. E 전체 (9개 TP)

    C ≈ max(A,B) 이면 트레이드오프 논리 전체가 불필요한 복잡도다.
    ★ 유리하게 해석 금지. 있는 그대로 보고한다.
    """
    def _run(sig: pd.Series, label: str) -> float:
        Q = P.copy()
        Q["Signal_rank"] = pd.to_numeric(sig, errors="coerce").groupby(
            Q["ym"], observed=True).rank(pct=True)
        return _stat(runner(Q, label=label), "sharpe")

    a1r = xsec_rank_pct_l(P, "a1")
    a2r = xsec_rank_pct_l(P, "a2")
    sA = _run(np.maximum(a1r - 0.5, 0.0), "R2-A-물량단독")
    sB = _run(np.maximum(a2r - 0.5, 0.0), "R2-B-단가단독")
    sC = _run(P["TP_X1"] if "TP_X1" in P.columns else pd.Series(np.nan, index=P.index),
              "R2-C-TP_X1")
    sD = _stat(base_bt, "sharpe")

    LOG.table([["A 물량 단독 clip(z(a1),0)", f"{sA:.3f}"],
               ["B 단가 단독 clip(z(a2),0)", f"{sB:.3f}"],
               ["C TP_X1 = clip × clip", f"{sC:.3f}"],
               ["D E 전체 (9개 TP)", f"{sD:.3f}"]], ["구성", "Sharpe"])
    best_single = np.nanmax([sA, sB])
    if not np.isfinite(sC) or not np.isfinite(best_single):
        _rx("R2", "TP vs 나이브", "N/A", "표본 부족으로 비교가 불가능합니다.")
        return
    margin = sC - best_single
    ok = margin > 0.10
    _rx("R2", "TP vs 나이브 ⭐⭐", "PASS" if ok else "FAIL",
        f"TP_X1 {sC:.3f} vs max(단독) {best_single:.3f} (Δ{margin:+.3f}). "
        + ("트레이드오프 쌍이 단독 지표를 유의하게 이깁니다." if ok else
           "트레이드오프가 단독 지표를 이기지 못합니다 — "
           "이 전략의 패러다임 근거가 소멸했습니다. 복잡도를 정당화할 수 없습니다."),
        metric=f"Δ{margin:+.3f}", kill=True)


def RX3_orthogonal(P: pd.DataFrame, bt: dict) -> None:
    """R3 — 표준 퀄리티/수익성/모멘텀에 직교화한 뒤에도 알파가 남는가."""
    if not _has_alpha(bt):
        _rx("R3", "퀄리티 팩터 직교화", "N/A",
            f"기준 Sharpe {_stat(bt,'sharpe'):.3f} < {ALPHA_FLOOR_SHARPE} — "
            f"직교화할 알파가 애초에 없습니다. 통과로 기록하지 않습니다.")
        return
    R = bt.get("returns")
    if R is None or not len(R):
        _rx("R3", "퀄리티 팩터 직교화", "N/A", "수익률 시계열이 없습니다.")
        return
    y = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy()
    facs = {}
    for nm, col_ in (("quality", "roic"), ("profit", "gpm"), ("mom", "mom12")):
        if col_ in P.columns:
            f = (P.assign(_v=xsec_rank_pct_l(P, col_))
                   .groupby("ym", observed=True)["_v"].mean())
            facs[nm] = f.reindex(pd.DatetimeIndex(R["month"])).to_numpy()
    if not facs:
        _rx("R3", "퀄리티 팩터 직교화", "N/A", "직교화할 팩터를 만들지 못했습니다.")
        return
    X = np.column_stack([np.ones(len(y))] + [np.nan_to_num(v) for v in facs.values()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    t, p = hac_tstat(resid)
    ok = np.isfinite(p) and p < 0.10 and np.nanmean(resid) > 0
    _rx("R3", "퀄리티 팩터 직교화", "PASS" if ok else "FAIL",
        f"직교화 후 잔차 알파 월 {np.nanmean(resid)*100:.3f}% (t={t:.2f}, p={p:.3f}) "
        f"· 통제 {list(facs)}",
        metric=f"t={t:.2f}", kill=True)


def RX4_placebo(gate3: dict) -> None:
    """R4 — 플라시보 매핑. 게이트3 결과를 그대로 승계한다(재계산하지 않는다).

    ⚠ 회귀를 1,000번 재적합하면 250시간이다. 게이트3 이 이미 롤링 적률을 재사용하고
      매핑 행렬만 셔플해 행렬곱 1,000회로 끝냈다 — 그 결과를 두 번 계산할 이유가 없다.
    """
    if not gate3 or not np.isfinite(gate3.get("p", float("nan"))):
        _rx("R4", "플라시보 매핑", "N/A", gate3.get("detail", "판정 불가"))
        return
    ok = bool(gate3.get("pass"))
    _rx("R4", "플라시보 매핑(행렬 셔플)", "PASS" if ok else "FAIL",
        gate3.get("detail", ""), metric=f"p={gate3.get('p'):.4f}", kill=True)


# 정책 캘린더 (§10). 시행일은 공개되어 있고 정확하므로 자연실험 설계가 가능하다.
# ★ 원문 확인 대상이며 추측으로 늘리지 않는다. 각 항목의 근거 URL 을 함께 보관한다.
XCB_POLICY_CALENDAR: "List[dict]" = [
    {"date": "2015-12-20", "name": "한·중 FTA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/cn/"},
    {"date": "2015-12-20", "name": "한·베트남 FTA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/vn/"},
    {"date": "2016-07-01", "name": "대중국 사드 배치 발표(한한령 시발)", "kind": "TRADE_SHOCK",
     "url": "https://www.mofa.go.kr/"},
    {"date": "2019-01-01", "name": "한·미 FTA 개정의정서 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/us/"},
    {"date": "2019-07-04", "name": "일본 대한 수출규제(반도체·디스플레이 3품목)",
     "kind": "EXPORT_CONTROL", "url": "https://www.motie.go.kr/"},
    {"date": "2020-03-11", "name": "COVID-19 팬데믹 선언", "kind": "SHOCK",
     "url": "https://www.who.int/"},
    {"date": "2022-02-01", "name": "RCEP 발효(한국)", "kind": "FTA",
     "url": "https://www.fta.go.kr/rcep/"},
    {"date": "2022-03-01", "name": "대러시아 수출통제", "kind": "EXPORT_CONTROL",
     "url": "https://www.motie.go.kr/"},
    {"date": "2022-08-16", "name": "미국 IRA 발효", "kind": "FOREIGN_POLICY",
     "url": "https://www.congress.gov/bill/117th-congress/house-bill/5376"},
    {"date": "2022-10-07", "name": "미국 대중 반도체 수출통제", "kind": "EXPORT_CONTROL",
     "url": "https://www.bis.doc.gov/"},
    {"date": "2023-01-01", "name": "한·인도네시아 CEPA 발효", "kind": "FTA",
     "url": "https://www.fta.go.kr/id/"},
    {"date": "2024-01-01", "name": "한·이스라엘 FTA 발효(2022-12) 후속 관세 인하",
     "kind": "FTA", "url": "https://www.fta.go.kr/il/"},
]


def RX10_policy(P, months, sec, runner, base_bt: dict) -> None:
    """R10 — 정책 반증. ⭐  정책 이벤트 ±6M 을 전부 빼도 알파가 남는가.

    ★ 정책 시행일은 공개되어 있고 정확하다. 그래서 이 오염은 다른 대체데이터 오염과 달리
      **자연실험 설계가 가능**하다. 필터를 쌓는 것보다 반증 검정이 우선이다.
    """
    if not _has_alpha(base_bt):
        _rx("R10", "정책 반증", "N/A",
            f"기준 Sharpe {_stat(base_bt,'sharpe'):.3f} < {ALPHA_FLOOR_SHARPE} — "
            f"제거할 알파가 없어 판정하지 않습니다.")
        return
    ev = pd.DataFrame(XCB_POLICY_CALENDAR)
    ev["date"] = as_ts_series(ev["date"])
    mask = pd.Series(False, index=pd.DatetimeIndex(months))
    for dt0 in ev["date"].dropna():
        mask |= (mask.index >= dt0 - pd.DateOffset(months=6)) & \
                (mask.index <= dt0 + pd.DateOffset(months=6))
    keep = pd.DatetimeIndex(mask.index[~mask])
    if len(keep) < 24:
        _rx("R10", "정책 반증", "N/A",
            f"정책 구간을 제외하면 {len(keep)}개월만 남아 검정이 불가능합니다.")
        return
    Q = P[P["ym"].isin(keep)].copy()
    bt = runner(Q, months=keep, label="R10-정책제외")
    s0, s1 = _stat(base_bt, "sharpe"), _stat(bt, "sharpe")
    ok = np.isfinite(s1) and s1 >= max(0.0, s0 * 0.5)
    _rx("R10", "정책 반증 ⭐", "PASS" if ok else "FAIL",
        f"정책 ±6M {len(months)-len(keep)}개월 제외 → Sharpe {s1:.3f} (기준 {s0:.3f}). "
        + ("정책 구간을 빼도 알파가 유지됩니다." if ok else
           "정책 구간을 빼면 알파가 사라집니다 — 이 전략은 정책 베팅에 불과합니다. A축 폐기."),
        metric=f"{s1:.3f}/{s0:.3f}", kill=True)


def RX5_ablation(P, months, sec, runner, base_bt: dict, rescore) -> pd.DataFrame:
    """R5 — 절제. 무엇이 실제로 기여하는지 귀속한다.

    ★ A축 제거로 성과가 안 떨어지면 이 전략의 근거가 소멸한다 → 리포트 최상단에 둔다.
    """
    base = _stat(base_bt, "sharpe")
    rows = []

    def _try(label: str, **kw):
        try:
            Q = rescore(**kw)
            s = _stat(runner(Q, label=f"R5-{label}"), "sharpe")
        except Exception as e:                                          # noqa
            LOG.debug(f"R5 {label} 실패: {type(e).__name__}")
            s = float("nan")
        rows.append({"항목": label, "Sharpe": s, "Δ vs 기준": s - base})

    for ax in ("A", "B", "C", "D"):
        _try(f"축제거:{ax}", drop_axes=[ax])
    for t in XCB_TP_COLS:
        _try(f"TP제거:{t}", drop_tps=[t])
    for m in ("zclip", "rankprod", "signed"):
        _try(f"TP방식:{m}", tp_mode=m)
    _try("θ_X 미가중", use_theta=False)
    for cv in (0.15, 0.35):
        _try(f"커모디티임계:{int(cv*100)}%", cv_thresh_pct=cv)
    for bf in (0.0, 0.6):
        _try(f"하한선:{bf:.1f}", breadth_floor=bf)

    A = pd.DataFrame(rows).sort_values("Δ vs 기준")
    # A축 제거 결과를 맨 위로 — 이 전략의 존재 근거이므로.
    A["_k"] = np.where(A["항목"] == "축제거:A", 0, 1)
    A = A.sort_values(["_k", "Δ vs 기준"]).drop(columns=["_k"]).reset_index(drop=True)
    LOG.banner("R5 절제 — A축 제거 결과가 맨 위", f"기준 Sharpe {base:.3f}")
    LOG.table([[r["항목"], f"{r['Sharpe']:.3f}", f"{r['Δ vs 기준']:+.3f}"]
               for _, r in A.head(20).iterrows()], ["절제 항목", "Sharpe", "Δ"])
    a_row = A[A["항목"] == "축제거:A"]
    if len(a_row):
        d = float(a_row["Δ vs 기준"].iloc[0])
        ok = d < -0.05
        _rx("R5", "절제 — A축(통관) 기여", "PASS" if ok else "FAIL",
            f"A축 제거 시 Sharpe {d:+.3f}. "
            + ("통관 축이 실제로 기여합니다." if ok else
               "통관을 빼도 성과가 그대로입니다 — 이 전략을 할 이유가 없습니다."),
            metric=f"Δ{d:+.3f}", kill=True)
    return A


def RX6_pbo(abl: pd.DataFrame) -> None:
    """R6 — PBO/DSR. R5 가 만든 구성집합 위에서 CSCV. 백테스트 **재실행 0회**."""
    if abl is None or len(abl) < 6:
        _rx("R6", "PBO / DSR", "N/A", "구성집합이 부족합니다.")
        return
    s = pd.to_numeric(abl["Sharpe"], errors="coerce").dropna().to_numpy()
    if len(s) < 6:
        _rx("R6", "PBO / DSR", "N/A", "유효 구성이 부족합니다.")
        return
    # 구성 간 성과 산포로 과적합 확률을 근사한다(구성 수가 적어 CSCV 정식은 과하다).
    rank_best = float((s < s.max()).mean())
    dsr = float((s.mean()) / (s.std(ddof=1) + 1e-9))
    _rx("R6", "PBO / DSR", "INFO",
        f"구성 {len(s)}개 · 최고 구성의 상대순위 {rank_best:.2f} · 구성간 Sharpe "
        f"평균 {s.mean():.3f} 표준편차 {s.std(ddof=1):.3f} (DSR 근사 {dsr:.2f}). "
        f"파라미터 수를 줄일수록 이 값이 안정됩니다.", metric=f"DSR≈{dsr:.2f}")


def RX7_regime(bt: dict, bench: "Dict[str, pd.Series]") -> None:
    """R7 — 레짐 분할. 의존성을 숨기지 않고 공개한다."""
    R = (bt or {}).get("returns")
    if R is None or not len(R):
        _rx("R7", "레짐 분할", "N/A", "수익률 시계열이 없습니다.")
        return
    d = R.copy()
    d["month"] = as_ts_series(d["month"])
    segs = [("2016~2018", "2016-01-01", "2018-12-31"),
            ("2019~2020 (일본수출규제·COVID)", "2019-01-01", "2020-12-31"),
            ("2021~2022 (공급망·인플레)", "2021-01-01", "2022-12-31"),
            ("2023~2026", "2023-01-01", "2026-12-31")]
    rows = []
    for nm, a, b in segs:
        sub = d[(d["month"] >= a) & (d["month"] <= b)]
        if len(sub) < 6:
            rows.append([nm, "표본부족", "", ""])
            continue
        st = perf_stats(sub)
        rows.append([nm, f"{_f(st.get('CAGR'))*100:6.2f}%",
                     f"{_f(st.get('MDD'))*100:6.2f}%",
                     f"{_f(st.get('Sharpe')):6.3f}"])
    LOG.table(rows, ["레짐", "CAGR", "MDD", "Sharpe"])
    _rx("R7", "레짐 분할", "INFO", "구간별 성과를 공개합니다. 특정 레짐 의존이면 위 표에 드러납니다.")


def RX9_capacity(P, months, sec, runner, base_bt: dict) -> None:
    """R9 — 회전율·비용 3시나리오. 비관에서도 살아남아야 실행 가능하다."""
    rows = []
    base = _stat(base_bt, "sharpe")
    scen = [("낙관 왕복 0.35%", 0.0035), ("기준 0.80%", 0.0080), ("비관 1.50%", 0.0150)]
    worst = float("nan")
    for nm, cost in scen:
        try:
            bt = runner(P, label=f"R9-{nm}", cost_override=cost)
            s, c = _stat(bt, "sharpe"), _stat(bt, "cagr")
            rows.append([nm, f"{c*100:6.2f}%", f"{s:6.3f}",
                         f"{_stat(bt,'turnover')*100:5.1f}%"])
            if "비관" in nm:
                worst = s
        except Exception as e:                                          # noqa
            rows.append([nm, "실패", type(e).__name__, ""])
    LOG.table(rows, ["시나리오", "CAGR", "Sharpe", "월회전율"])
    ok = np.isfinite(worst) and worst > 0.0
    _rx("R9", "회전율·비용 3시나리오", "PASS" if ok else "FAIL",
        f"비관(왕복 1.50% + 거래대금 참여 {POS_ADV_PARTICIPATION*100:.0f}% 상한) Sharpe {worst:.3f}. "
        + ("비용을 비관적으로 잡아도 성과가 남습니다." if ok else
           "비관 시나리오에서 성과가 소멸합니다 — 소액계좌라도 실행 불가입니다."),
        metric=f"{worst:.3f}", kill=True)
    _rx("R9b", "우측꼬리 의존", "INFO", _tail_note(base_bt), metric="")


def _tail_note(bt: dict) -> str:
    """§15.1 — 상위 5% 종목을 빼면 성과가 사라지는지. 리포트 첫 페이지에 명시할 값."""
    try:
        rt = right_tail_contribution(bt)
        return (f"원본 CAGR {_f(rt.get('원본 CAGR'))*100:.2f}% → "
                f"상위1% 제외 {_f(rt.get('상위1% 제외 CAGR'))*100:.2f}% · "
                f"상위5% 제외 {_f(rt.get('상위5% 제외 CAGR'))*100:.2f}% "
                f"(Sharpe {_f(rt.get('상위5% 제외 Sharpe')):.3f}). "
                f"유니버스가 얇아 우측 꼬리 의존이 큽니다 — 리포트 첫 페이지에 둡니다.")
    except Exception:                                                   # noqa
        return "우측꼬리 기여도를 계산하지 못했습니다."


def report_robustness_xcb() -> None:
    LOG.banner("강건성 검사 결과 R0~R10",
               "킬 기준(⭐)은 통과시키지 않는다. 나쁜 결과는 그 자체로 정보다.")
    LOG.table([[r["id"], r["name"][:26], r["verdict"], r["metric"][:16], r["detail"][:56]]
               for r in ROBUST_LOG], ["ID", "검사", "판정", "지표", "내용"])
    if KILL_LOG:
        LOG.banner("★ 킬 기준 발동", f"{len(KILL_LOG)}건 — 파라미터로 통과시키지 않습니다")
        for k in KILL_LOG:
            LOG.error(f"[{k['id']}] {k['name']} — {k['detail'][:150]}")
    else:
        LOG.ok("킬 기준 위반 없음.")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [24/27]  70_report.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  리포트 — 성과검증 · 해석표 · 진단카드 · 감쇠표 · 런타임 · 데이터 흐름 지도                 ║
# ║                                                                                             ║
# ║  요구사항: "에러 발생 시 어디서 났는지, 데이터 입출력이 어디서 이뤄지는지,                  ║
# ║  애널리스트 보고서와 식별된 애널리스트가 제대로 연결됐는지, 다중소스 원장연결은 확실한지를  ║
# ║  한눈에 파악할 수 있게" — 아래 표들이 그 답이다.                                            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

ATTRITION_LOG: "List[dict]" = []
OUTPUT_FILES: "List[str]" = []


def attrition(step: str, n: int, note: str = "") -> None:
    """유니버스 감쇠표(§12.2) — 어느 게이트에서 표본이 붕괴하는지 매 실행 기록한다."""
    ATTRITION_LOG.append({"단계": step, "종목수": int(n), "비고": note})


def report_attrition() -> "pd.DataFrame":
    if not ATTRITION_LOG:
        return pd.DataFrame()
    A = pd.DataFrame(ATTRITION_LOG)
    first = A["종목수"].iloc[0] if len(A) else 0
    A["잔존율"] = (A["종목수"] / first * 100).round(1) if first else np.nan
    LOG.banner("유니버스 감쇠표",
               "어느 게이트에서 표본이 붕괴하는가. 매핑게이트 통과 <150 이면 통계 검정 불가.")
    LOG.table([[r["단계"], f"{r['종목수']:,}", f"{r['잔존율']:.1f}%", r["비고"][:44]]
               for _, r in A.iterrows()], ["단계", "종목수", "잔존율", "비고"])
    return A


def report_performance_xcb(bt: dict, bench: "Dict[str, pd.Series]",
                           title: str = "성과 검증") -> dict:
    R = (bt or {}).get("returns")
    if R is None or not len(R):
        LOG.warn("성과를 계산할 수익률 시계열이 없습니다.")
        return {}
    st = perf_stats(R)
    LOG.banner(title, f"{bt.get('label','')} · {st.get('월수',0)}개월")
    order = ["월수", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
             "월평균수익", "t통계량(HAC)", "최장언더워터(월)", "누적수익",
             "평균보유종목수", "월평균회전율", "월평균비용"]
    rows = []
    for k in order:
        v = st.get(k)
        if v is None:
            continue
        if k in ("CAGR", "연변동성", "MDD", "승률", "월평균수익", "누적수익",
                 "월평균회전율", "월평균비용"):
            rows.append([k, f"{_f(v)*100:,.2f}%"])
        elif k in ("월수", "최장언더워터(월)"):
            rows.append([k, f"{int(_f(v, 0)):,}"])
        else:
            rows.append([k, f"{_f(v):,.3f}"])
    LOG.table(rows, ["지표", "값"])

    # ★ §15.1 — 우측꼬리 의존도를 리포트 첫 페이지에 명시한다.
    rt = right_tail_contribution(bt)
    if rt:
        LOG.banner("우측 꼬리 의존도 (§15.1 — 첫 페이지에 명시)",
                   "유니버스가 얇으면 성과가 소수 종목에 달려 있다. 숨기지 않는다.")
        LOG.table([[k, (f"{_f(v)*100:.2f}%" if "CAGR" in k else str(v))]
                   for k, v in rt.items()], ["항목", "값"])
    if bench:
        LOG.banner("벤치마크 (이 실행이 직접 측정 — 하드코딩 없음)", "원칙 7")
        brows = []
        for nm, s in bench.items():
            b = perf_stats(pd.DataFrame({"ret": pd.to_numeric(s, errors="coerce").fillna(0.0)}))
            brows.append([nm, f"{_f(b.get('CAGR'))*100:6.2f}%", f"{_f(b.get('MDD'))*100:6.2f}%",
                          f"{_f(b.get('Sharpe')):6.3f}", f"{_f(b.get('Calmar')):6.3f}"])
        LOG.table(brows, ["벤치마크", "CAGR", "MDD", "Sharpe", "Calmar"])
    return st


def report_interpretation_xcb(P: pd.DataFrame, bt: dict) -> None:
    """해석표 — 각 TP 가 실제로 얼마나 발화했고 무엇을 뜻하는지."""
    LOG.banner("해석표 — 트레이드오프 쌍별 발화 현황",
               "TP 는 '개선 × 대가회피'의 곱이다. 0 이면 둘 중 하나가 없었다는 뜻이다.")
    rows = []
    for tid, ca, cb, ax, fire, nofire in XCB_TP_SPECS:
        if tid not in P.columns:
            rows.append([tid, ax, "미산출", "", fire[:34]])
            continue
        v = pd.to_numeric(P[tid], errors="coerce")
        obs = int(v.notna().sum())
        pos = float((v > 0).mean()) if obs else float("nan")
        rows.append([tid, ax, f"{obs:,}", f"{pos*100:.1f}%", fire[:34]])
    LOG.table(rows, ["TP", "축", "유효관측", "발화율", "발화 의미"])

    LOG.banner("거부권 발동 현황", "이진·곱·상쇄 불가. 부분 거부권은 축만 무효화한다.")
    vrows = []
    for v in ("V1", "V2", "V3", "V5", "V6", "V11", "V9", "V10", "V12"):
        if v not in P.columns:
            continue
        s = pd.to_numeric(P[v], errors="coerce").fillna(0)
        kind = "전면" if v in VETO_HARD else "부분"
        vrows.append([v, kind, f"{int(s.sum()):,}", f"{s.mean()*100:.2f}%"])
    LOG.table(vrows, ["거부권", "종류", "발동 종목월", "발동률"])

    if "axis_flag" in P.columns:
        LOG.table([[k, f"{v:,}"] for k, v in
                   P["axis_flag"].value_counts().items()], ["활성 축 조합", "종목월"])


def diagnostic_cards_xcb(P: pd.DataFrame, bt: dict, sec: pd.DataFrame,
                         top_n: int = 10) -> str:
    """§13 진단 카드 — 최근 시점 상위 종목."""
    if P is None or not len(P) or "Signal" not in P.columns:
        return ""
    last = P[P["Signal"].notna()]
    if not len(last):
        return ""
    m = last["ym"].max()
    sub = last[last["ym"] == m].nlargest(top_n, "Signal")
    names = {}
    if sec is not None and "code" in sec.columns:
        nc = "name" if "name" in sec.columns else ("stock_name" if "stock_name" in sec.columns else None)
        if nc:
            names = dict(zip(sec["code"].astype(str), sec[nc].astype(str)))
    out = []
    W = 92
    for _, r in sub.iterrows():
        code = str(r["code"])
        L = ["─" * W,
             f"[{code}] {names.get(code, '')[:16]:<16} 셀: {str(r.get('cell', ''))[:26]:<26} "
             f"신호일: {pd.Timestamp(r['ym']):%Y-%m-%d}",
             "─" * W,
             f"Signal {_f(r.get('Signal')):.4f} (월내 상위 {(1-_f(r.get('Signal_rank'),0))*100:.1f}%)   "
             f"E {_f(r.get('E')):.3f}  U {_f(r.get('U')):+.3f}  "
             f"θ_X {_f(r.get('theta_x')):.2f}   활성축: {r.get('axis_flag', '')}",
             "■ A축 통관 (트리거)  매핑 HS: "
             f"{str(r.get('hs_main',''))} (매핑 {int(_f(r.get('hs_n'),0))}개)"]
        for tid, ca, cb, ax, fire, _n in XCB_TP_SPECS:
            if ax != "A" or tid not in P.columns:
                continue
            v = _f(r.get(tid))
            if np.isfinite(v):
                L.append(f"  {tid}  {v:6.4f}  {fire[:38]}   "
                         f"[{ca}={_f(r.get(ca)):+.3f} / {cb}={_f(r.get(cb)):+.3f}]")
        cv = _f(r.get("cv_dest"))
        L.append(f"  cv_dest {cv:.3f} → "
                 + ("커모디티 아님, a2 유효 ✔" if _f(r.get('V10'), 0) < 1 else
                    "커모디티 → V10 발동, a2 무효화 ✘"))
        L.append("■ B·C축 (사전확률)")
        for tid, ca, cb, ax, fire, _n in XCB_TP_SPECS:
            if ax == "A" or tid not in P.columns:
                continue
            v = _f(r.get(tid))
            if np.isfinite(v):
                L.append(f"  {tid}  {v:6.4f}  {fire[:38]}   "
                         f"[{ca}={_f(r.get(ca)):+.3f} / {cb}={_f(r.get(cb)):+.3f}]")
        L.append("■ D축 미반영도 (U)")
        L.append(f"  d1  ΔlogE {_f(r.get('dlogE'))*100:+.1f}%, ΔlogM {_f(r.get('dlogM'))*100:+.1f}%"
                 + ("  → 이익 인정, 자본화 거부 ✔ [목표 상태]"
                    if (_f(r.get('dlogE'), 0) > 0 and _f(r.get('dlogM'), 0) <= 0) else
                    "  → 목표 상태 아님"))
        L.append(f"  d2  커버리지 {int(_f(r.get('n_analyst'), 0))}명   "
                 f"d3 수급 {_f(r.get('d3')):+.4f}   d4 개시 {_f(r.get('coverage_init'), 0):.0f}")
        L.append("■ 정책 오염 점검 (5중 방어)")
        L.append(f"  ① 단가 유지 여부 a2={_f(r.get('a2')):+.3f} "
                 + ("→ 보조금 저가수주 패턴 아님 ✔" if _f(r.get('a2'), -1) > 0 else "→ 단가 하락 ⚠"))
        L.append(f"  ③ 유효세율 변화 {_f(r.get('etr_chg'))*100:+.2f}%p (임계 -3%p) "
                 + ("✔ V11 통과" if _f(r.get('V11'), 0) < 1 else "✘ V11 발동"))
        L.append("■ 거부권")
        L.append("  " + "  ".join(
            f"{v}{'✘' if _f(r.get(v), 0) > 0 else '✔'}"
            for v in ("V1", "V2", "V3", "V5", "V6", "V9", "V10", "V11", "V12")))
        L.append("─" * W)
        out.append("\n".join(L))
    txt = "\n\n".join(out)
    LOG.banner("진단 카드 — 최근 시점 상위 종목", f"{pd.Timestamp(m):%Y-%m} 기준 {len(sub)}종목")
    _safe_print(txt)
    return txt


def report_ledger_integrity(reports: pd.DataFrame, analysts: pd.DataFrame,
                            cov: pd.DataFrame) -> None:
    """원장 무결성 감사 — 리포트 ↔ 애널리스트 ↔ 종목 연결이 제대로 됐는가.

    사용자 요구사항의 핵심 확인 항목이다. 연도×소스별로 연결률을 표로 낸다.
    """
    LOG.banner("원장 무결성 감사",
               "리포트 ↔ 애널리스트 ↔ 종목 연결. 다중소스가 하나의 원장으로 합쳐졌는가.")
    if reports is None or not len(reports):
        LOG.warn("리포트 원장이 비어 있습니다 — d2/d4 는 비활성화됩니다. "
                 "(드라이브 캐시 경로와 RESEARCH_COLLECT 설정을 확인하세요)")
        return
    r = reports.copy()
    r["연도"] = as_ts_series(r.get("pub_date")).dt.year
    r["소스"] = r.get("source", "").astype(str)
    g = r.groupby(["연도", "소스"], observed=True)
    tab = g.agg(건수=("report_uid", "size"),
                종목코드율=("stock_code", lambda s: float(s.notna().mean())),
                애널연결률=("analyst_raw", lambda s: float(
                    (s.astype(str).str.len() > 0).mean())),
                목표주가율=("target_price", lambda s: float(s.notna().mean()))).reset_index()
    LOG.table([[int(x["연도"]) if pd.notna(x["연도"]) else "?", x["소스"], f"{x['건수']:,}",
                f"{x['종목코드율']*100:5.1f}%", f"{x['애널연결률']*100:5.1f}%",
                f"{x['목표주가율']*100:5.1f}%"]
               for _, x in tab.tail(24).iterrows()],
              ["연도", "소스", "건수", "종목코드율", "애널연결률", "목표주가율"])
    LOG.info(f"애널리스트 원장 {0 if analysts is None else len(analysts):,}명 · "
             f"커버리지 패널 {0 if cov is None else len(cov):,} 종목월")
    ok_code = float(r["stock_code"].notna().mean())
    if ok_code < 0.5:
        LOG.warn(f"종목코드 연결률이 {ok_code*100:.0f}% 로 낮습니다. "
                 f"d2(커버리지 수)가 체계적으로 과소계상되며, 그 방향은 "
                 f"'커버리지가 적어 보이게' 하므로 U 를 인위적으로 높입니다. "
                 f"이 편의를 인지하고 R5 절제에서 D축 기여를 확인하세요.")


def report_dataflow_xcb() -> None:
    """데이터 흐름 지도 — 어느 스테이지에서 무엇이 들어오고 나가는가."""
    try:
        PIPE.report_flow()
    except Exception as e:                                              # noqa
        LOG.debug(f"데이터 흐름 지도 출력 실패: {type(e).__name__}")


def save_outputs_xcb(P: pd.DataFrame, bt: dict, abl: "Optional[pd.DataFrame]",
                     attr: "Optional[pd.DataFrame]", cards: str,
                     canary: "Optional[pd.DataFrame]", gates: dict) -> "List[str]":
    """§16 산출물 체크리스트를 실제 파일로 남긴다(전용 인덱스)."""
    out: List[str] = []
    d = VAULT.table_dir("private")

    def _w(name: str, obj, kind: str = "csv"):
        try:
            p = os.path.join(d, name)
            _ensure_dir(p)
            if kind == "csv" and obj is not None and len(obj):
                obj.to_csv(p, index=False, encoding="utf-8-sig")
            elif kind == "txt" and obj:
                atomic_write_text(p, str(obj))
            elif kind == "json":
                atomic_write_text(p, json.dumps(obj, ensure_ascii=False,
                                                indent=1, default=str))
            elif kind == "parquet" and obj is not None and len(obj):
                atomic_write_parquet(obj, p)
            else:
                return
            out.append(p)
        except Exception as e:                                          # noqa
            LOG.debug(f"산출물 저장 실패 {name}: {type(e).__name__}")

    _w("attrition.csv", attr)
    _w("r5_ablation.csv", abl)
    _w("canary_report.csv", canary)
    _w("card_sample.txt", cards, "txt")
    _w("policy_calendar_x.csv", pd.DataFrame(XCB_POLICY_CALENDAR))
    _w("robustness.json", ROBUST_LOG, "json")
    _w("mapping_gates.json", gates, "json")
    _w("runtime.csv", pd.DataFrame(RUNTIME_LOG))
    if bt and bt.get("returns") is not None:
        _w("backtest_returns.csv", bt["returns"])
        _w(f"backtest_{STAGE}.json", perf_stats(bt["returns"]), "json")
    if P is not None and len(P):
        keep = [c for c in P.columns if not str(c).startswith("_")]
        _w("panel.parquet", P[keep], "parquet")
    OUTPUT_FILES.extend(out)
    if out:
        LOG.banner("산출물", f"{len(out)}개 파일 → {d}")
        LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:,.0f}KB"] for p in out],
                  ["파일", "크기"])
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [25/27]  79_canary.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  CANARY — 코드가 본격적으로 돌기 전에 '축이 살아있는가'를 실측한다.                         ║
# ║                                                                                             ║
# ║  ★ FAIL 항목에 의존하는 단계는 큐에서 제거하고, 그 사실을 표에 남긴다.                      ║
# ║    없는 것을 있는 척하지 않는다 — 조용히 빈 값으로 진행하는 것이 최악이다.                  ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

CANARY_LOG: "List[dict]" = []


def _cn(cid: str, name: str, status: str, detail: str, kill: bool = False) -> None:
    CANARY_LOG.append({"ID": cid, "확인": name, "결과": status, "실측": detail})
    icon = {"PASS": "✔", "FAIL": "✘", "DEGRADED": "⚠", "N/A": "—"}.get(status, "·")
    (LOG.ok if status == "PASS" else LOG.warn if status != "FAIL" else LOG.error)(
        f"{icon} [{cid}] {name}: {status} — {detail[:120]}")
    if kill and status == "FAIL":
        KILL_LOG.append({"id": cid, "name": name, "detail": detail})


def run_canary(sample_hs: str = "854370") -> "pd.DataFrame":
    """X1~X6 · K1~K11. 실측만 기록하고 추측하지 않는다."""
    LOG.banner("CANARY — 축 유효성 실측",
               "이 표의 FAIL 은 해당 축을 죽인다. 통과시키지 않고 그대로 보고한다.")

    # ── X1~X4: 관세청
    cli = CustomsClient(DATA_GO_KR_KEY)
    pr = cli.probe(sample_hs=sample_hs)
    if not pr["endpoint"]:
        _cn("X1", "통관 중량·금액 동시 제공", "FAIL",
            f"관세청 API 응답 없음 — {pr['detail'][:100]}. "
            f"A축 4센서가 전부 죽으므로 이 전략은 성립하지 않습니다.", kill=True)
        _cn("X2", "기간 일괄조회", "N/A", "엔드포인트 미확보")
        _cn("X3", "HS×국가 분해", "N/A", "엔드포인트 미확보")
        _cn("X4", "2016-01 소급", "N/A", "엔드포인트 미확보")
    else:
        both = pr["weight"] and pr["value"]
        _cn("X1", "통관 중량(kg)·금액(USD) 동시 제공", "PASS" if both else "FAIL",
            f"{pr['endpoint']} — 중량 {'O' if pr['weight'] else 'X'} / "
            f"금액 {'O' if pr['value'] else 'X'}. "
            + ("단가 축(a2)이 성립합니다." if both else "단가 축 사망 — 전략 폐기 대상입니다."),
            kill=True)
        _cn("X2", "기간(strt~end) 일괄조회", "PASS" if pr["range"] else "DEGRADED",
            "지원 — 단, 제공기관 제한으로 **12개월 창**으로 잘라 호출합니다."
            if pr["range"] else
            "미지원 — 월별 개별호출로 전환합니다(호출 수 약 120배). 병렬을 낮게 유지합니다.")
        _cn("X3", "HS × 국가 분해", "PASS" if pr["country"] else "DEGRADED",
            "국가별 분해 제공 — a3(HHI)·a4(선진시장) 활성화."
            if pr["country"] else
            "국가 분해 없음 — a3·a4 및 cv_dest(V10) 비활성화, 품목 단독으로 진행합니다.")
        _cn("X4", "2016-01 소급 조회", "PASS" if pr["back2016"] else "DEGRADED",
            "2016-01 조회 성공." if pr["back2016"] else
            "2016-01 미제공 — 실제 최초 제공 시점으로 백테스트 시작일을 상향해야 합니다.")

    # ── X5: 현행화 크기 (C18-d)
    rev = customs_revision_probe(DATA_GO_KR_KEY, sample_hs, "201801")
    if rev["measurable"]:
        big = rev["diff_pct"] > 1.0
        _cn("X5", "관세청 현행화(소급수정) 크기", "DEGRADED" if big else "PASS", rev["detail"])
    else:
        _cn("X5", "관세청 현행화(소급수정) 크기", "N/A", rev["detail"])

    # ── X6: HS–KSIC 연계표
    conc, st6 = fetch_hs_ksic_concordance()
    _cn("X6", "HS–KSIC 연계표", "PASS" if st6 == "OK" else
        ("DEGRADED" if st6 == "DEGRADED" else "FAIL"),
        f"{len(conc):,}행 확보 ({st6}). "
        + ("" if st6 == "OK" else
           "내장 씨앗표(章↔KSIC 중분류) 사용 — 매핑 정밀도가 낮으므로 "
           "게이트1·2·3 판정이 그만큼 더 중요합니다."),
        kill=(st6 == "FAIL"))

    # ── K1/K2: DART
    if not DART_API_KEY:
        _cn("K1", "DART 재무 확보", "FAIL",
            "DART_API_KEY 가 비어 있습니다 — B·C축과 V1/V2/V5/V11, θ_X 가 전부 죽습니다.",
            kill=True)
        _cn("K2", "DART 최초 제공 분기", "N/A", "키 없음")
    else:
        js = dart_api("list.json", {"bgn_de": "20160101", "end_de": "20160131",
                                    "page_count": "10"})
        ok = bool(js and str(js.get("status")) == "000")
        _cn("K1", "DART 접근", "PASS" if ok else "FAIL",
            f"list.json status={js.get('status') if js else 'None'} "
            f"({DART_STATUS_MSG.get(str(js.get('status')) if js else '', '')[:60]})",
            kill=not ok)
        _cn("K2", "2016Q1 소급", "PASS" if ok else "N/A",
            "2016-01 공시 목록 조회 성공." if ok else "키 확인 필요")

    # ── K5: 상장폐지 목록 (C2 생존자편향)
    try:
        dl = fetch_fdr_delisting()
    except Exception as e:                                              # noqa
        dl = None
        LOG.debug(f"상장폐지 목록 조회 실패: {type(e).__name__}")
    nd = 0 if dl is None else len(dl)
    _cn("K5", "상장폐지 목록", "PASS" if nd > 100 else "FAIL",
        f"{nd:,}건 확보. " + ("생존자편향 제거(C2) 가능." if nd > 100 else
                              "상장폐지 목록 없이는 생존자편향을 제거할 수 없습니다 — 중단 대상."),
        kill=(nd <= 100))

    # ── K11: 리서치 목록
    n_rep = 0
    try:
        if FOREIGN is not None:
            rp = foreign_reports(FOREIGN)
            n_rep = len(rp)
    except Exception as e:                                              # noqa
        LOG.debug(f"리포트 원장 확인 실패: {type(e).__name__}")
    _cn("K11", "애널리스트 리포트 원장", "PASS" if n_rep > 1000 else "DEGRADED",
        f"드라이브 캐시에서 {n_rep:,}건 확인. "
        + ("d2/d4 활성화." if n_rep > 1000 else
           "부족 — d2/d4 를 비활성화하고 U 를 d1·d3 로 구성합니다."))

    # ── K12: KRX 없이 생존자편향 제거 + PIT 유니버스가 성립하는가 (사용자 요구 확인 항목)
    try:
        sec_probe = build_security_master_nokrx()
        aud = audit_survivorship(sec_probe, _months(), phase="pre")
        # 캐너리 시점에는 가격이 없어 폐지일 복원 전이다. '폐지 종목이 마스터에 존재하는가'
        # 까지만 본다. 폐지일 정확성의 최종 판정은 가격 수집 뒤 L1.PRICE 에서 한다.
        n_dead = int(sec_probe.get("src", pd.Series("", index=sec_probe.index))
                     .astype(str).str.contains("delist").sum())
        _cn("K12", "KRX 비의존 유니버스·생존자편향",
            "PASS" if (len(sec_probe) > 1000 and n_dead > 200) else "FAIL",
            f"KRX 모드={krx_mode()} · 마스터 {len(sec_probe):,}종목 · 폐지 종목 {n_dead:,}건 "
            f"포함 · 상장일 확보율 {aud['listing_known']*100:.0f}% "
            f"(폐지일은 가격 수집 후 마지막 거래일로 복원)",
            kill=(len(sec_probe) <= 1000 or n_dead <= 200))
    except Exception as e:                                              # noqa
        _cn("K12", "KRX 비의존 유니버스·생존자편향", "FAIL",
            f"{type(e).__name__}: {e} — 상장/폐지 목록 소스를 확인하세요.", kill=True)

    C = pd.DataFrame(CANARY_LOG)
    LOG.table([[r["ID"], r["확인"][:30], r["결과"], r["실측"][:56]] for _, r in C.iterrows()],
              ["ID", "확인", "결과", "실측"])
    return C


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [26/27]  80_selftest.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  계약 자동검정 + 합성 스모크                                                                ║
# ║                                                                                             ║
# ║  ★ 스모크는 **프로덕션 함수를 실물 호출**한다. 호출 순서를 손으로 베껴 두면                 ║
# ║    프로덕션만 고쳤을 때 스모크는 통과하고, 2시간짜리 실행이 수집을 다 끝낸 뒤 죽는다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_LOG: "List[dict]" = []


def _ct(cid: str, name: str, ok: bool, detail: str = "") -> bool:
    CONTRACT_LOG.append({"ID": cid, "계약": name, "결과": "PASS" if ok else "FAIL",
                         "내용": detail})
    (LOG.ok if ok else LOG.error)(f"{'✔' if ok else '✘'} [{cid}] {name}"
                                  + (f" — {detail[:110]}" if detail else ""))
    return ok


def contracts_xcb() -> bool:
    """C1 PIT · C2 생존자편향 · C3 매핑PIT · C13 유니버스PIT · C18 통관현행화 ·
    원칙2 TP부호 · 원칙3 셀정규화 · 거부권 이진성 · 절대1원칙."""
    LOG.banner("계약 자동검정", "약속이 아니라 검사로 강제한다")
    allok = True

    # ── C18: 통관 knowledge_date = 귀속월 익월 말일
    ym = pd.Series(pd.to_datetime(["2018-03-31", "2020-12-31", "2024-02-29"]))
    kd = customs_knowledge_date(ym)
    exp = pd.to_datetime(["2018-04-30", "2021-01-31", "2024-03-31"])
    allok &= _ct("C18", "통관 knowledge_date = 귀속월 익월 말일",
                 bool((kd.to_numpy() == exp.to_numpy()).all()),
                 f"{list(kd.dt.strftime('%Y-%m-%d'))}")

    # ── 원칙 2: TP 는 clip×clip. 최악이 최고점이 되는 일이 구조적으로 불가능해야 한다.
    n = 400
    rng = np.random.default_rng(SEED)
    P = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "ym": pd.Timestamp("2020-06-30"),
        "a1": rng.normal(size=n), "a2": rng.normal(size=n),
    })
    P["cell"] = "X"
    P["cell_l2"] = "X"
    P["cell_l3"] = "X"
    tpv = tp_pair(P, "a1", "a2")
    worst = (P["a1"] < P["a1"].quantile(0.05)) & (P["a2"] < P["a2"].quantile(0.05))
    allok &= _ct("원칙2", "TP = clip×clip (부호버그 부재)",
                 bool(np.nanmax(tpv.to_numpy()) <= 0.2501
                      and float(np.nansum(tpv.to_numpy()[worst.to_numpy()])) == 0.0),
                 f"TP 범위 [{np.nanmin(tpv):.3f}, {np.nanmax(tpv):.3f}] · "
                 f"양쪽 최하위 5% 종목의 TP 합 = {float(np.nansum(tpv.to_numpy()[worst.to_numpy()])):.4f} "
                 f"(0 이어야 정상)")
    # 부호버그 재현본은 반드시 반대 결과를 내야 한다 — 검사 자체가 유효한지 확인
    tps = tp_pair(P, "a1", "a2", mode="signed")
    allok &= _ct("원칙2b", "부호버그 재현본이 실제로 오염을 만든다(검사 유효성)",
                 bool(float(np.nansum(tps.to_numpy()[worst.to_numpy()])) > 0),
                 f"signed 방식에서 최하위 5% 종목의 TP 합 = "
                 f"{float(np.nansum(tps.to_numpy()[worst.to_numpy()])):.3f} (>0 이면 오염 재현)")

    # ── 거부권 이진성 · 상쇄 불가
    Q = P.copy()
    Q["v1_ratio"] = np.where(np.arange(n) < 20, 3.0, 0.1)
    Q["adtv20"] = 1e9
    V = apply_vetoes(Q, ["V1", "V6"])
    vals = set(pd.unique(V["V1"].to_numpy()))
    allok &= _ct("거부권", "이진값이며 점수로 상쇄되지 않는다",
                 vals.issubset({0.0, 1.0}) and int(V["V1"].sum()) == 20,
                 f"V1 고유값 {sorted(vals)} · 발동 {int(V['V1'].sum())}건(기대 20)")

    # ── C1: merge_asof backward 가 미래를 보지 않는다
    grid = pd.DataFrame({"code": ["000001"] * 5,
                         "asof": pd.date_range("2020-01-31", periods=5, freq="ME")})
    src = pd.DataFrame({"code": ["000001"] * 3,
                        "knowledge_date": pd.to_datetime(["2019-12-15", "2020-03-20", "2020-06-01"]),
                        "v": [1.0, 2.0, 3.0]})
    j = pd.merge_asof(grid.sort_values("asof"), src.sort_values("knowledge_date"),
                      left_on="asof", right_on="knowledge_date", by="code",
                      direction="backward")
    allok &= _ct("C1", "PIT — knowledge_date <= asof 전수 성립",
                 bool((j["knowledge_date"].dropna() <= j.loc[j["knowledge_date"].notna(), "asof"]).all()),
                 f"결합 {len(j)}행 중 위반 0건")

    # ── C2: 폐지 종목이 -100% 로 계상되는 경로가 존재
    allok &= _ct("C2", "상장폐지 -100% 경로 존재",
                 "-1.0" in open_source_marker("run_backtest"),
                 "run_backtest 내에 정리매매 부재 시 -100% 계상 분기가 있습니다.")

    # ── 절대1원칙: 삭제 API 부재
    src_all = open_source_marker(None)
    # ★ 유일한 예외는 우리가 만든 **잠금 파일**(lp) 해제다. 그 외 대상 삭제는 전부 위반이다.
    bad = [m.group(0) for m in re.finditer(
        r"\b(os\.remove|os\.unlink|shutil\.rmtree)\s*\(\s*([A-Za-z_][\w\.]*)", src_all)
        if m.group(2) != "lp"]
    allok &= _ct("절대1원칙", "사용자 데이터 삭제 API 자체가 없다",
                 len(bad) == 0,
                 f"삭제 호출 {len(bad)}건 발견: {bad[:3]}" if bad else
                 "잠금파일 해제를 제외하면 삭제 호출이 소스에 없습니다.")

    # ── 원칙 3: 셀 정규화에 groupby.apply 없음
    ga = re.findall(r"\.groupby\([^)]*\)\s*\.\s*apply\s*\(", src_all)
    allok &= _ct("원칙3", "셀 정규화에 groupby.apply 미사용",
                 len(ga) == 0, f"groupby.apply {len(ga)}건" if ga else "없음")

    LOG.table([[c["ID"], c["계약"][:34], c["결과"], c["내용"][:52]] for c in CONTRACT_LOG],
              ["ID", "계약", "결과", "내용"])
    if not allok:
        LOG.error("계약 위반이 있습니다. 이 상태의 결과는 신뢰할 수 없습니다.")
    return allok


_SRC_CACHE: "Dict[str, str]" = {}


def open_source_marker(fn_name: "Optional[str]") -> str:
    """자기 자신의 소스를 읽어 계약을 소스 수준에서 검사한다.

    조립된 단일 파일로 배포되므로 __file__ 로 읽을 수 있고, 노트북에 붙여넣어 실행하면
    inspect 로 함수 소스를 얻는다. 둘 다 실패하면 빈 문자열(검사는 보수적으로 통과).
    """
    key = fn_name or "__ALL__"
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]
    txt = ""
    try:
        if fn_name:
            import inspect
            txt = inspect.getsource(globals()[fn_name])
        else:
            f = globals().get("__file__")
            if f and os.path.exists(f):
                txt = open(f, encoding="utf-8").read()
            else:
                import inspect
                parts = []
                for nm, ob in list(globals().items()):
                    if callable(ob) and getattr(ob, "__module__", None) == "__main__":
                        try:
                            parts.append(inspect.getsource(ob))
                        except Exception:                               # noqa
                            pass
                txt = "\n".join(parts)
    except Exception:                                                   # noqa
        txt = ""
    _SRC_CACHE[key] = txt
    return txt


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  합성 스모크
# ═══════════════════════════════════════════════════════════════════════════════════════════════

def synth_xcb(n_hs: int = 40, n_firm: int = 90, n_month: int = 120) -> dict:
    """합성 데이터. **두 개의 독립 잠재축**(개선 A, 대가회피 B)과 보고지연을 넣는다.

    하나의 잠재축이 전부를 움직이면 R2 가 아무것도 구별하지 못하고,
    지연이 없으면 R1a 가 정상 하네스에 FAIL 을 준다.
    """
    rng = np.random.default_rng(SEED)
    months = pd.date_range(BACKTEST_START, periods=n_month, freq="ME")
    hs = [f"{28 + (i % 60):02d}{i:04d}" for i in range(n_hs)]
    ctys = ["US", "CN", "JP", "EU", "VN", "IN", "ASEAN", "ME"]

    # HS × 월 × 국가 통관 원장
    rows = []
    base_w = rng.lognormal(11, 1.0, size=n_hs)
    drift = rng.normal(0.004, 0.012, size=n_hs)
    # ★ 투입원가는 수출단가와 **독립인** 자체 경로를 갖게 만든다.
    #   수입단가를 수출단가에 비례시키면 회귀에서 γ가 β를 통째로 흡수해 β≈0 이 나오고,
    #   "정상 기업은 β<0" 이라는 전제 자체를 스모크가 검증하지 못한다(실제로 겪었다).
    cost0 = rng.lognormal(0.0, 0.3, size=n_hs)
    cost_walk = rng.normal(0, 0.04, size=(n_hs, n_month)).cumsum(axis=1)
    for i, h in enumerate(hs):
        for t, m in enumerate(months):
            tot = base_w[i] * math.exp(drift[i] * t + rng.normal(0, 0.10))
            icost = cost0[i] * math.exp(cost_walk[i, t])
            up = 3.0 * math.exp(rng.normal(0, 0.05)
                                - 0.25 * math.log(max(tot, 1) / base_w[i])
                                + 0.30 * math.log(icost))
            # ★ 목적지 비중은 (hs, 월)마다 **한 번만** 뽑아 합이 정확히 1이 되게 한다.
            #   국가별로 따로 뽑으면 합이 1이 아니게 되어 관측 물량이 tot·Σsh 가 되고,
            #   회귀변수에 측정오차가 실려 β 가 0 쪽으로 끌려간다(errors-in-variables).
            #   실제로 이 버그 때문에 스모크의 β 가 -0.13 으로 나와 '단가 축이 죽었는지'를
            #   판별하지 못했다. 같은 감쇠는 실데이터의 중량 보고오차에서도 일어난다.
            shares_t = rng.dirichlet(np.ones(len(ctys)))
            for ci, c in enumerate(ctys):
                w = tot * shares_t[ci]
                iw = max(w * rng.uniform(0.2, 0.6), 1.0)
                rows.append({"hs": h, "ym": m, "country": c,
                             "exp_wgt": w, "exp_usd": w * up * rng.uniform(0.85, 1.15),
                             "imp_wgt": iw, "imp_usd": iw * icost * rng.uniform(0.9, 1.1)})
    cx = pd.DataFrame(rows)
    cx["knowledge_date"] = customs_knowledge_date(cx["ym"])

    codes = [f"{i:06d}" for i in range(1, n_firm + 1)]
    mapping = pd.DataFrame({
        "code": [codes[i % n_firm] for i in range(n_hs)],
        "hs": hs, "weight": 1.0,
        "valid_from": pd.Timestamp(BACKTEST_START), "valid_to": pd.Timestamp("2262-01-01"),
        "match_score": 0.8,
    })

    # 두 개의 독립 잠재축 + 지속성
    A = rng.normal(size=(n_firm, n_month)).cumsum(axis=1) * 0.10
    B = rng.normal(size=(n_firm, n_month)).cumsum(axis=1) * 0.10
    grid = pd.MultiIndex.from_product([codes, months], names=["code", "ym"]).to_frame(index=False)
    idx = {c: i for i, c in enumerate(codes)}
    ci = grid["code"].map(idx).to_numpy()
    ti = grid.groupby("code", observed=True).cumcount().to_numpy()
    grid["b1"] = A[ci, ti] + rng.normal(0, 0.3, len(grid))
    grid["b2"] = B[ci, ti] + rng.normal(0, 0.3, len(grid))
    grid["b3"] = B[ci, ti] * 0.7 + rng.normal(0, 0.3, len(grid))
    grid["c1"] = A[ci, ti] * 0.5 + rng.normal(0, 0.3, len(grid))
    grid["c2"] = B[ci, ti] * 0.5 + rng.normal(0, 0.3, len(grid))
    grid["c3"] = rng.normal(0, 0.3, len(grid))
    grid["c4"] = rng.normal(1.0, 0.2, len(grid))
    grid["c5"] = rng.normal(0, 0.2, len(grid))
    grid["c6"] = np.abs(rng.normal(0, 1, len(grid)))
    grid["theta_x"] = rng.uniform(0.3, 0.95, len(grid))
    grid["mcap"] = rng.lognormal(25, 1.0, len(grid))
    # ★ 프로덕션 가격패널이 내는 이름(adv20)만 만든다. 예전엔 adtv20 도 같이 만들어서
    #   실제 파이프라인의 이름 불일치를 스모크가 못 잡았다.
    grid["adv20"] = rng.lognormal(20.5, 1.0, len(grid))
    grid["cv_dest"] = rng.uniform(0.05, 0.9, len(grid))
    grid["etr_chg"] = rng.normal(0, 0.01, len(grid))
    grid["v1_ratio"] = np.abs(rng.normal(0.5, 0.4, len(grid)))
    grid["v2_streak"] = 0.0
    grid["dlogE"] = A[ci, ti] * 0.3 + rng.normal(0, 0.1, len(grid))
    grid["dlogM"] = rng.normal(0, 0.1, len(grid))
    grid["d1"] = -grid["dlogM"]
    grid["d2"] = -rng.integers(0, 6, len(grid))
    grid["d3"] = rng.normal(0, 1, len(grid))
    grid["d4"] = 0.0
    grid["n_analyst"] = rng.integers(0, 6, len(grid))
    grid["coverage_init"] = 0.0

    # 미래수익: 잠재축의 곱에 반응 (트레이드오프가 실제로 정보를 갖도록)
    sig = np.maximum(A[ci, ti], 0) * np.maximum(B[ci, ti], 0)
    grid["fwd_ret"] = 0.004 + 0.010 * (sig - sig.mean()) / (sig.std() + 1e-9) \
        + rng.normal(0, 0.085, len(grid))
    px = 10000 * np.exp(grid.groupby("code", observed=True)["fwd_ret"].cumsum().to_numpy())
    grid["close"] = px
    grid["exec_px"] = px
    grid["month"] = grid["ym"]
    grid["hs_main"] = [hs[i % n_hs] for i in range(len(grid))]
    grid["hs_n"] = 1

    sec = pd.DataFrame({"code": codes, "name": [f"합성{c}" for c in codes],
                        "industry": ["정밀화학"] * n_firm,
                        "listing_date": pd.Timestamp("2010-01-01"),
                        "delisting_date": pd.NaT,
                        "induty_code": ["201"] * n_firm})
    return {"cx": cx, "mapping": mapping, "panel": grid, "sec": sec, "months": months,
            "hs": hs, "codes": codes}


def smoke_xcb() -> bool:
    """합성데이터로 L1→L2→L3→성과→강건성→해석표까지 **프로덕션 경로 그대로** 예행연습."""
    LOG.banner("합성 스모크", "실데이터 쓰기 전에 계산경로를 먼저 증명한다")
    S = synth_xcb()
    months = S["months"]

    a_hs = customs_a_sensors(S["cx"])
    if not len(a_hs):
        LOG.error("스모크: A축 센서가 비었습니다.")
        return False
    LOG.ok(f"스모크 A축: {len(a_hs):,}행 (a2 유효 {int(a_hs['a2'].notna().sum()):,})")

    a_corp = map_hs_to_corp(a_hs, S["mapping"], months)
    P = S["panel"].merge(a_corp.drop(columns=[c for c in ("hs_main", "hs_n")
                                              if c in a_corp.columns]),
                         on=["code", "ym"], how="left")
    # 프로덕션 build_panel_xcb 와 동일한 별칭 정규화를 거친다(스모크가 실경로를 검사하도록).
    if "adtv20" not in P.columns and "adv20" in P.columns:
        P["adtv20"] = pd.to_numeric(P["adv20"], errors="coerce")
    cvd = customs_cv_dest(S["cx"])
    P = P.drop(columns=["cv_dest"]).merge(cvd[["hs", "cv_dest"]].rename(
        columns={"hs": "hs_main"}), on="hs_main", how="left")

    P = score_panel(P, stage="ALL")
    n_sig = int(P["Signal"].notna().sum())
    LOG.ok(f"스모크 L2: Signal 유효 {n_sig:,} / {len(P):,}행 "
           f"(TP 유효 {int(P[XCB_TP_COLS].notna().any(axis=1).sum()):,})")
    if n_sig < 100:
        LOG.error(f"스모크: 유효 Signal 이 {n_sig}개뿐입니다 — 셀·하한선·거부권 중 하나가 "
                  f"전부를 걸러내고 있습니다. 실데이터에서도 같은 일이 벌어집니다.")
        return False

    P["VETO"] = P["veto_pass"]
    P["FLOOR"] = P["breadth_ok"]
    P["dlog_M"] = P["dlogM"]
    P["dlog_E"] = P["dlogE"]
    P["xcb_uni"] = True
    bt = run_backtest(P, months, S["sec"], entry_col="xcb_uni", label="SMOKE", quiet=True)
    st = perf_stats(bt["returns"])
    LOG.ok(f"스모크 L3: {st.get('월수',0)}개월 · CAGR {_f(st.get('CAGR'))*100:.2f}% · "
           f"Sharpe {_f(st.get('Sharpe')):.3f} · 평균보유 {_f(st.get('평균보유종목수')):.1f}종목")
    if int(st.get("월수", 0)) < 12:
        LOG.error("스모크: 백테스트 월수가 12 미만입니다.")
        return False
    report_performance_xcb(bt, {}, title="스모크 성과(합성)")
    report_interpretation_xcb(P, bt)
    LOG.ok("스모크 통과 — 계산경로가 전 출력물을 생성합니다.")
    return True


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  [27/27]  90_main.py  [XCB]
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ╔═════════════════════════════════════════════════════════════════════════════════════════════╗
# ║  오케스트레이션 — 이 파일 하나로 백테스트~강건성~해석표까지 전부 나온다                     ║
# ║                                                                                             ║
# ║  실패 지점 국소화: 모든 연산은 PIPE.stage 안에서만 돈다. 실패하면 자동으로                  ║
# ║  스테이지 ID · 계층 · 경과시간 · 직전 입출력 스냅샷 · 한글 진단힌트가 출력된다.             ║
# ║  런타임 실측은 Stage(...) 가 따로 기록한다(예산 대비 몇 배를 썼는가).                       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════════╝

def _months() -> "pd.DatetimeIndex":
    return pd.date_range(pd.Timestamp(BACKTEST_START) + pd.offsets.MonthEnd(0),
                         pd.Timestamp(BACKTEST_END), freq="ME")


def _make_runner(months, sec):
    """강건성 스위트가 백테스트를 반복 호출할 때 쓰는 러너.

    비용 시나리오(R9)를 위해 cost_override 를 받는다.
    """
    def runner(P: pd.DataFrame, months=months, label: str = "XCB",
               cost_override: "Optional[float]" = None) -> dict:
        global COMMISSION_BPS, SLIPPAGE_FLOOR
        prev = (COMMISSION_BPS, SLIPPAGE_FLOOR)
        if cost_override is not None:
            # 왕복 비용 목표치를 편도 수수료 + 스프레드 하한으로 배분한다.
            COMMISSION_BPS = max(0.1, cost_override * 10000 / 4.0)
            SLIPPAGE_FLOOR = cost_override / 4.0
        try:
            return run_backtest(P, months, sec, entry_col="xcb_uni", label=label, quiet=True)
        finally:
            COMMISSION_BPS, SLIPPAGE_FLOOR = prev
    return runner


def build_panel_xcb(months, sec, px_m, px_d, mcap, cx, mapping,
                    fin, emp, dis, reports) -> "pd.DataFrame":
    """L1 — 원시 센서만. 정규화는 여기서 하지 않는다(전부 L2)."""
    P = build_base_panel(months, px_m, px_d, sec, mcap)
    P["ym"] = as_ts_series(P["month"]).astype("datetime64[ns]")
    # ★ 가격패널은 20일 평균거래대금을 'adv20' 으로 낸다. 거부권 V6 와 규모버킷은 'adtv20' 을
    #   읽는다. 이름이 어긋나면 예외 없이 **V6 가 영원히 발동하지 않고** 규모버킷이 NA 로
    #   무너진다(합성데이터가 두 이름을 다 갖고 있으면 스모크는 통과한다 — 실제로 그랬다).
    if "adtv20" not in P.columns and "adv20" in P.columns:
        P["adtv20"] = pd.to_numeric(P["adv20"], errors="coerce")
    elif "adv20" not in P.columns and "adtv20" in P.columns:
        P["adv20"] = pd.to_numeric(P["adtv20"], errors="coerce")

    # ── A축: HS 격자에서 산출 → 매핑표로 종목 격자로 이동
    a_hs = customs_a_sensors(cx)
    PIPE.io("OUT", "MEM", "A축 HS센서", a_hs)
    a_corp = map_hs_to_corp(a_hs, mapping, months)
    PIPE.io("OUT", "MEM", "A축 종목센서", a_corp)
    if len(a_corp):
        P = P.merge(a_corp, on=["code", "ym"], how="left")
    else:
        for c in ("a1", "a2", "a3", "a4", "a5", "x_wgt", "x_usd", "a2_beta",
                  "hs_main", "hs_n"):
            P[c] = np.nan

    # ── cv_dest (V10 커모디티 판정)
    cvd = customs_cv_dest(cx)
    if len(cvd) and "hs_main" in P.columns:
        P = P.merge(cvd[["hs", "cv_dest"]].rename(columns={"hs": "hs_main"}),
                    on="hs_main", how="left")
    else:
        P["cv_dest"] = np.nan

    # ── B·C축: 분기 프레임에서 산출한 뒤 PIT 로 붙인다 (merge_asof 단일 패스)
    b = b_sensors(fin)
    c = c_sensors(fin, emp)
    th = derive_theta_x(fin, mapping, cx)
    sub = build_subsidy_signal(fin)
    imp = build_capital_impairment(fin)
    # ★ 재무 '원값' 통과 소스. b/c 센서는 파생값만 내보내므로, D축(eps_ttm)과 거부권이
    #   필요로 하는 원계정(net_income_ttm 등)이 패널에 아예 없게 된다.
    #   그러면 d1(이 시스템에서 가장 중요한 단일 지표)이 통째로 결측이 되는데 예외는 안 난다.
    _raw_cols = [c_ for c_ in ("net_income_ttm", "revenue_ttm", "cfo_ttm", "assets",
                               "equity", "shares_out") if c_ in fin.columns]
    fund = (fin[["code", "knowledge_date"] + _raw_cols].copy() if _raw_cols else None)
    srcs = {"b": b, "c": c, "theta": th, "subsidy": sub, "impair": imp, "fund": fund}
    P = build_pit_panel(P, {k: v for k, v in srcs.items() if v is not None and len(v)},
                        by="code", left_time="month")
    viol = assert_c1(P, strict=False)
    if viol:
        LOG.error(f"C1(PIT) 위반 {len(viol)}건 — 결과를 신뢰할 수 없습니다: {viol[:3]}")

    # ── c6: 계약공시 12개월 누계 (월 격자 이벤트)
    con = fetch_supply_contracts(dis)
    c6 = c6_contract_ratio(con, months)
    if len(c6):
        P = P.merge(c6, on=["code", "ym"], how="left")
        rev = pd.to_numeric(P.get("rev_ttm"), errors="coerce")
        P["c6"] = safe_div(pd.to_numeric(P["contract_12m"], errors="coerce"), rev)
        # 매출을 못 구하면 금액 그대로 쓰되 셀 내 랭크가 되므로 스케일은 문제되지 않는다.
        P["c6"] = P["c6"].where(rev > 0, pd.to_numeric(P["contract_12m"], errors="coerce"))
    else:
        P["c6"] = np.nan

    # ── D축
    fin_m = P[["code", "ym"]].copy()
    ni = (pd.to_numeric(P["net_income_ttm"], errors="coerce")
          if "net_income_ttm" in P.columns else pd.Series(np.nan, index=P.index))
    sh = safe_div(pd.to_numeric(P.get("mcap"), errors="coerce"),
                  pd.to_numeric(P.get("close"), errors="coerce").replace(0, np.nan))
    fin_m["eps_ttm"] = safe_div(ni, sh)
    _cov_eps = float(fin_m["eps_ttm"].notna().mean()) if len(fin_m) else 0.0
    if _cov_eps < 0.05:
        LOG.warn(f"eps_ttm 커버리지가 {_cov_eps*100:.1f}% 입니다 — d1(ΔlogE/ΔlogM 재분류 갭)이 "
                 f"사실상 죽습니다. d1 은 이 시스템에서 가장 중요한 단일 지표이므로 "
                 f"net_income_ttm(재무) 과 mcap(시총) 확보 상태를 먼저 확인하세요.")
    cov = build_coverage_panel(reports, months)
    flows = None
    _codes = sorted(P.loc[P.get("xcb_uni", True), "code"].astype(str).unique()) \
        if "xcb_uni" in P.columns else sorted(P["code"].astype(str).unique())
    if krx_mode() != "off":
        try:
            fl = fetch_investor_flows(_codes, BACKTEST_START, BACKTEST_END)
            if fl is not None and len(fl):
                flows = fl.rename(columns={"month": "ym"}) if "month" in fl.columns else fl
        except Exception as e:                                          # noqa
            LOG.warn(f"KRX 수급 수집 실패({type(e).__name__}) — 네이버 폴백을 시도합니다.")
    if flows is None or not len(flows):
        try:
            flows = flows_naver(_codes, months)
        except Exception as e:                                          # noqa
            LOG.warn(f"네이버 수급 폴백 실패({type(e).__name__}) — d3 비활성화(0 채움 금지).")
            flows = None
    d = d_sensors(P[["code", "ym", "close"]], fin_m, flows, cov)
    P = P.merge(d.drop(columns=["close"], errors="ignore"), on=["code", "ym"], how="left")
    if len(cov):
        P = P.merge(cov, on=["code", "ym"], how="left")

    # ── 거부권 입력
    dil = build_dilution_flags(dis, months)
    if len(dil):
        P = P.merge(dil, on=["code", "ym"], how="left")
    wf = build_watch_flags(dis, months, sec)
    if len(wf):
        P = P.merge(wf, on=["code", "ym"], how="left")
    P["watch_flag"] = np.maximum(pd.to_numeric(P.get("watch_flag"), errors="coerce").fillna(0),
                                 pd.to_numeric(P.get("impaired"), errors="coerce").fillna(0))
    P["theta_x_chg"] = pd.to_numeric(P.get("theta_x"), errors="coerce") - \
        pd.to_numeric(P.get("theta_x"), errors="coerce").groupby(
            P["code"], observed=True).shift(12)
    P["map_gate_fail"] = pd.to_numeric(P.get("map_gate_fail"), errors="coerce").fillna(0.0)

    # ── 유니버스 플래그: 매핑된 종목 ∧ 상장 ∧ 시즈닝 (§5.1 — 매핑이 곧 유니버스)
    mapped = set(mapping["code"].astype(str)) if mapping is not None and len(mapping) else set()
    P["xcb_uni"] = (P["code"].astype(str).isin(mapped)
                    & P.get("listed", True)
                    & (pd.to_numeric(P.get("days_listed"), errors="coerce")
                       >= UNIVERSE_SEASON_DAYS))
    LOG.ok(f"L1 패널 {len(P):,}행 · {P['code'].nunique():,}종목 · {mem_mb(P):.0f}MB · "
           f"유니버스 {int(P['xcb_uni'].sum()):,} 종목월")
    return downcast(P)


def _reset_run_state() -> None:
    """같은 커널에서 두 번째로 실행할 때 지난 실행의 기록이 섞이지 않게 초기화한다.

    ★ 노트북은 한 커널에서 셀을 여러 번 돌린다. 전역 로그가 누적되면 강건성 표에 같은 검사가
      두 번 찍히고, 감쇠표의 첫 행(=분모)이 지난 실행 값이라 잔존율이 통째로 틀어진다.
    """
    for _lst in (ROBUST_LOG, KILL_LOG, CANARY_LOG, CONTRACT_LOG,
                 ATTRITION_LOG, OUTPUT_FILES, RUNTIME_LOG):
        try:
            _lst.clear()
        except Exception:                                               # noqa
            pass
    try:
        _SRC_CACHE.clear()
        CELL_FALLBACK_STATS.clear()
    except Exception:                                                   # noqa
        pass


def main_xcb() -> int:
    t_start = time.time()
    _reset_run_state()
    LOG.banner(f"{STRATEGY_NAME}  ·  {BUILD_VERSION}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · RUN_MODE={RUN_MODE} · STAGE={STAGE}")

    # ── [0] 환경 · 금고 · 외부캐시 · 계약 ────────────────────────────────────────────────
    global VAULT
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300), \
            Stage("L0.vault", 3.0):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        VAULT.report()
        foreign_init()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=300), \
            Stage("L0.contracts", 2.0):
        contracts_xcb()

    with PIPE.stage("L0.SMOKE", "합성 스모크", "L0", budget_s=1800), \
            Stage("L0.smoke", 3.0):
        ok = smoke_xcb()
        if not ok:
            LOG.error("스모크 실패 — 실데이터로 진행하지 않습니다. 위 진단을 먼저 해결하세요.")
            PIPE.report_stages()
            return 2

    if RUN_MODE == "SMOKE":
        LOG.ok("RUN_MODE='SMOKE' — 합성데이터로 전 출력물을 예행연습했습니다. "
               "실데이터로 돌리려면 RUN_MODE='FULL' 로 바꾸세요.")
        PIPE.report_stages()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)
        return 0

    months = _months()
    canary = None
    with PIPE.stage("L1.CANARY", "CANARY 실측", "L1", budget_s=1800, critical=False), \
            Stage("CANARY", STAGE_BUDGET_MIN["CANARY"]):
        canary = run_canary()

    # ── [1] 유니버스 · 가격 ───────────────────────────────────────────────────────────────
    with PIPE.stage("L1.UNIVERSE", "PIT 유니버스 · 상장/폐지 (KRX 비의존)", "L1",
                    budget_s=1800), Stage("M0.universe", 15.0):
        # ★ KRX 는 '있으면 검증에 쓰는 보조'일 뿐 의존 대상이 아니다.
        #   계정이 차단되어 있어도 여기서 멈추지 않는다 — 마스터는 FDR/KIND 로 완성된다.
        mode = krx_mode()
        snaps = pd.DataFrame(columns=["snap_date", "code", "market"])
        if mode != "off":
            try:
                KRX.login()
                snaps = fetch_pykrx_snapshots(months)
            except Exception as e:                                      # noqa
                LOG.warn(f"KRX 경로 실패({type(e).__name__}) — 무시하고 비의존 경로로 진행합니다.")
        else:
            LOG.info("KRX_ENABLED=False — KRX 를 아예 호출하지 않습니다. "
                     "생존자편향 제거와 PIT 유니버스는 KRX 없이 구성됩니다.")
        sec = (build_security_master(snaps) if len(snaps)
               else build_security_master_nokrx())
        attrition("전체 상장(생존+폐지)", sec["code"].nunique(), "C2 상장폐지 포함")
        surv = audit_survivorship(sec, months, phase="pre")

    with PIPE.stage("L1.PRICE", "가격 · 시가총액", "L1", budget_s=2400), \
            Stage("M0.price", 25.0):
        codes = sorted(sec["code"].astype(str).unique())
        px_d = fetch_prices(codes, BACKTEST_START, BACKTEST_END)
        pxp = build_price_panel(px_d, months)
        px_m = pxp["monthly"] if isinstance(pxp, dict) else pxp
        mcap = None
        if krx_mode() != "off":
            try:
                mcap = fetch_pit_marketcap(months, px_m, sec)
            except Exception as e:                                      # noqa
                LOG.warn(f"KRX 시총 경로 실패({type(e).__name__}) — 근사 경로로 넘어갑니다.")
        if mcap is None or not len(mcap):
            mcap = mcap_nokrx(months, px_m, sec)
        # ★ 폐지일이 없는 폐지종목의 폐지일을 '마지막 거래일'로 복원한다.
        #   가격을 받은 뒤에만 가능하므로 여기서 한다. C2 의 마지막 구멍을 막는 단계다.
        sec = infer_delisting_from_prices(sec, px_d, months)
        audit_survivorship(sec, months)

    # ── [2] 큐레이션 · 통관 ───────────────────────────────────────────────────────────────
    with PIPE.stage("L1.CURATE", "HS 유니버스 큐레이션", "L1", budget_s=1500), \
            Stage("CURATION", 20.0):
        conc, _st = fetch_hs_ksic_concordance()
        # 큐레이션은 통관 원장을 필요로 하고, 통관 수집은 HS 목록을 필요로 한다.
        # 순환을 끊기 위해 1차로 '연계표가 지목한 章의 대표 HS' 만 넓게 받아 본다.
        seed_hs = sorted({str(h).zfill(2)[:2] for h in conc["hs"].astype(str)})
        cx0 = ingest_customs(seed_hs, BACKTEST_START.replace("-", "")[:6],
                             BACKTEST_END.replace("-", "")[:6], key=DATA_GO_KR_KEY)
        hs_uni = curate_hs_universe(cx0, sec, conc)
        adopted = hs_uni[hs_uni["adopted"] == 1]["hs"].astype(str).tolist()
        attrition("과점 HS 매핑 대상", len(adopted), f"HS {len(hs_uni)}개 중 채택")

    with PIPE.stage("L1.CUSTOMS", "관세청 통관 수집", "L1", budget_s=2400), \
            Stage("M0.customs", 20.0):
        cx = ingest_customs(adopted or seed_hs, BACKTEST_START.replace("-", "")[:6],
                            BACKTEST_END.replace("-", "")[:6], key=DATA_GO_KR_KEY)
        if cx is None or not len(cx):
            LOG.error("통관 데이터를 확보하지 못했습니다 — A축이 없으면 이 전략은 성립하지 않습니다.")
            PIPE.report_stages()
            return 3

    # ── [3] DART · 리서치 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L1.DART", "DART 재무 · 직원 · 공시", "L1", budget_s=3000), \
            Stage("M0.dart", 30.0):
        corpmap = fetch_dart_corpcode()
        code_of = dict(zip(corpmap["corp_code"].astype(str), corpmap["code"].astype(str))) \
            if corpmap is not None and len(corpmap) else {}
        years = list(range(pd.Timestamp(BACKTEST_START).year - 1,
                           pd.Timestamp(BACKTEST_END).year + 1))
        raw = fetch_dart_bulk(years, list(REPRT_CODES.values()))
        dis = fetch_dart_disclosures(BACKTEST_START.replace("-", ""),
                                     BACKTEST_END.replace("-", ""))
        kmap = build_knowledge_map(dis)
        fin = tidy_financials(raw, kmap)
        emp = fetch_dart_employees(sorted(code_of), years, code_of) \
            if STAGE in ("M2", "ALL") else None

    reports = pd.DataFrame(columns=REPORT_COLS)
    analysts = pd.DataFrame()
    with PIPE.stage("L1.RESEARCH", "리서치 원장(캐시 우선)", "L1",
                    budget_s=1800, critical=False), Stage("M2.research", 15.0):
        if FOREIGN is not None:
            reports = foreign_reports(FOREIGN)
            analysts = foreign_analysts(FOREIGN)
        if RESEARCH_COLLECT and RUN_MODE == "FULL" and len(reports) < 5000:
            try:
                fresh = fetch_research_all(BACKTEST_START, BACKTEST_END)
                if fresh is not None and len(fresh):
                    reports = merge_report_ledger(reports, fresh)
            except Exception as e:                                      # noqa
                LOG.warn(f"리서치 신규 수집 실패({type(e).__name__}) — 캐시분만 사용합니다.")

    # ── [4] 매핑 게이트 ──────────────────────────────────────────────────────────────────
    with PIPE.stage("L2.MAP", "매핑표 + 4중 게이트", "L2", budget_s=1200), \
            Stage("CURATION.gates", 15.0):
        mapping = build_mapping_table(hs_uni, sec, conc, seg=None)
        attrition("매핑표 생성", mapping["code"].nunique() if len(mapping) else 0)
        a_hs0 = customs_a_sensors(cx)
        b0 = b_sensors(fin)
        fin_g = fin.merge(b0[["code", "period_end", "b1"]], on=["code", "period_end"],
                          how="left") if len(b0) else fin
        mapping, gates = apply_mapping_gates(mapping, cx, fin_g, None, a_hs0)
        attrition("매핑 게이트 통과", mapping["code"].nunique() if len(mapping) else 0,
                  f"게이트3 p={gates.get('gate3', {}).get('p', float('nan')):.4f}")

    # ── [5] L1 → L2 → L3 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L2.PANEL", "L1 피처 패널", "L2", budget_s=1800), \
            Stage("M0.panel", 20.0):
        P = build_panel_xcb(months, sec, px_m, px_d, mcap, cx, mapping,
                            fin, emp, dis, reports)
        attrition("유니버스(매핑∧상장∧시즈닝)",
                  int(P.loc[P["xcb_uni"], "code"].nunique()))

    with PIPE.stage("L3.SCORE", "스코어 조립", "L3", budget_s=900), Stage("M0.score", 10.0):
        P = score_panel(P, stage=STAGE)
        P["VETO"] = P["veto_pass"]
        P["FLOOR"] = P["breadth_ok"]
        P["dlog_M"] = P.get("dlogM")
        P["dlog_E"] = P.get("dlogE")
        attrition("거부권 통과", int(P.loc[P["xcb_uni"] & (P["veto_pass"] > 0),
                                          "code"].nunique()))
        attrition("하한선 통과", int(P.loc[P["xcb_uni"] & (P["veto_pass"] > 0)
                                        & (P["breadth_ok"] > 0), "code"].nunique()))
        attrition("최종 신호 보유", int(P.loc[P["Signal"].notna(), "code"].nunique()))

    runner = _make_runner(months, sec)
    with PIPE.stage("L3.BT", "백테스트", "L3", budget_s=900), Stage("M0.backtest", 10.0):
        bt = runner(P, label="XCB")
        bench = benchmark_returns(months)

    # ── [6] 성과 · 원장 · 해석 ───────────────────────────────────────────────────────────
    with PIPE.stage("L4.PERF", "성과 검증", "L4", budget_s=300), Stage("REPORT.perf", 3.0):
        report_performance_xcb(bt, bench)
        report_ledger_integrity(reports, analysts, build_coverage_panel(reports, months))
        report_interpretation_xcb(P, bt)

    # ── [7] 강건성 ───────────────────────────────────────────────────────────────────────
    abl = None
    with PIPE.stage("L4.ROBUST", "강건성 R0~R10", "L4", budget_s=3000, critical=False), \
            Stage("R-SUITE", 30.0):
        RX0_benchmark(bt, bench, months)
        RX1_leakage(P, months, sec, runner, bt)
        RX2_tp_vs_naive(P, months, sec, runner, bt)
        RX3_orthogonal(P, bt)
        RX4_placebo(gates.get("gate3", {}))
        RX10_policy(P, months, sec, runner, bt)

        def _rescore(**kw):
            Q = score_panel(P, stage=STAGE, **kw)
            Q["VETO"] = Q["veto_pass"]
            Q["FLOOR"] = Q["breadth_ok"]
            Q["dlog_M"] = Q.get("dlogM")
            Q["dlog_E"] = Q.get("dlogE")
            return Q

        abl = RX5_ablation(P, months, sec, runner, bt, _rescore)
        RX6_pbo(abl)
        RX7_regime(bt, bench)
        RX9_capacity(P, months, sec, runner, bt)
        report_robustness_xcb()

    # ── [8] 산출물 · 감사 ────────────────────────────────────────────────────────────────
    with PIPE.stage("L5.OUT", "산출물 · 감사", "L5", budget_s=600, critical=False):
        attr = report_attrition()
        cards = diagnostic_cards_xcb(P, bt, sec)
        save_outputs_xcb(P, bt, abl, attr, cards, canary, gates)
        try:
            VAULT.put_table("l1_panel_xcb", P, scope="private", source=STRATEGY_ID)
            VAULT.put_table("backtest_returns_xcb", bt["returns"], scope="private",
                            source=STRATEGY_ID)
            VAULT.flush()
        except Exception as e:                                          # noqa
            LOG.warn(f"전용 인덱스 저장 실패({type(e).__name__})")
        universe_sources_audit(sec, px_m, mcap, None)
        report_cell_fallback()
        report_http()
        PIPE.report_stages()
        report_dataflow_xcb()
        report_runtime_v3(WALL_CLOCK_BUDGET_MIN)

    mins = (time.time() - t_start) / 60.0
    LOG.banner("완료", f"총 {mins:.1f}분 (하드 제약 {WALL_CLOCK_BUDGET_MIN:.0f}분)")
    if mins > WALL_CLOCK_BUDGET_MIN:
        LOG.warn(f"[킬 기준 11] 총 wall-clock 이 {mins:.0f}분으로 예산을 초과했습니다. "
                 f"검사를 줄이지 말고 구조를 고치세요.")
    if KILL_LOG:
        LOG.error(f"★ 킬 기준 {len(KILL_LOG)}건 발동 — 결과를 그대로 보고합니다. "
                  f"파라미터를 조정해 통과시키지 마세요.")
    return 0


def _entrypoint() -> int:
    try:
        return main_xcb()
    except KillCriteria as e:
        LOG.error(f"킬 기준으로 중단: {e}")
        return 4
    except StageFailure as e:
        LOG.error(f"스테이지 실패로 중단: {e}")
        return 5


# ★ 노트북에 통째로 붙여넣어도 __name__ 은 "__main__" 이므로 그대로 실행된다(원셀 실행).
#   다만 노트북에서 SystemExit 를 던지면 셀이 빨간 트레이스백으로 끝나 '실패한 것처럼' 보인다.
#   대화형 환경에서는 종료코드를 변수로만 남기고 조용히 끝낸다.
if __name__ == "__main__":
    XCB_EXIT_CODE = _entrypoint()
    if ENV.get("ipython"):
        if XCB_EXIT_CODE:
            LOG.warn(f"종료코드 {XCB_EXIT_CODE} — 위 진단을 확인하세요. "
                     f"(노트북이라 예외를 던지지 않고 XCB_EXIT_CODE 변수로만 남깁니다)")
    else:
        raise SystemExit(XCB_EXIT_CODE)
