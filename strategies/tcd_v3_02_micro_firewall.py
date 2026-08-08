#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================================
#  TCD v3 · 전략 2 — MICRO-FW  (U-MICRO 방화벽 중심 전략, 완전 독립형)
#  백테스트 구간: 2016-08-01 ~ 2026-07-31 (10년)
#
#  찾는 대상: 시총 하위권(U-MICRO)에서 "제약이 풀린 기업".
#            매출이 늘면서 회전율이 악화되지 않고, 이익의 질(발생액)이 유지되는 기업.
#            단 이 구간은 컨센서스·수급 데이터가 구조적으로 얇으므로 증거층(E)은 2개로
#            최소화하고, "방화벽(하드필터)이 알파의 주된 원천"이라는 가설을 이 파일이
#            스스로 검정한다(R2-M 4방 비교 A/B/C/D).
#
#  ── 이 파일 하나로 끝납니다 ────────────────────────────────────────────────────────────
#   Colab / JupyterLab 어디서든 이 파일 전체를 "한 셀"에 붙여넣고 실행하거나,
#   `python tcd_v3_02_micro_firewall.py` 로 실행해도 동일하게 동작합니다.
#
#   실행하면 순서대로 로그에 출력됩니다:
#     [0] 환경·의존성 → 구글드라이브 캐시 연결 → 계약 자동검정(C1/C2/C13/C14/TP부호)
#     [1] 합성데이터 엔드투엔드 스모크        ← 실데이터 수집 전에 계산경로를 먼저 증명
#     [2] CANARY K1~K6                        ← 실측표. FAIL 항목과 조치를 표 상단에
#     [3] 데이터 수집 (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)
#     [4] 원장 무결성 감사 (리포트 ↔ 애널리스트 ↔ 종목 · 다중소스 연결)
#     [5] PIT 유니버스 + 유니버스 감쇠 감사
#     [6] L1 센서 → 셀 정규화 → TP 조립 → 방화벽/거부권 → 백테스트(A/B/C/D)
#     [7] 성과 검증표
#     [8] 강건성 R0 · R2-M · R3 · R5-M · R9
#     [9] 해석표 + 진단카드 + 런타임 감사 + 산출물 다운로드 링크
#
#  ⚠ 투자자문이 아닙니다. 연구/검증용 코드입니다.
# ============================================================================================
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════════════════
#
#   ⚙️  사용자 설정 — 여기만 채우면 됩니다   (아래 ①~④만 봐도 됩니다)
#
#   ▸ 아무것도 안 채워도 실행은 됩니다. 키가 없는 데이터원은 자동으로 건너뛰고
#     "왜 건너뛰었는지"를 한글로 로그에 명시합니다. 조용히 실패하지 않습니다.
#   ▸ 구글드라이브에 이미 캐시가 있으면 키 없이도 상당 부분 재현됩니다.
#     (다른 전략이 만들어 둔 공용 캐시도 그대로 재사용합니다)
#
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ① DART 전자공시 OpenAPI  ★이 전략의 필수 입력 ──────────────────────────────────────────
#    발급: https://opendart.fss.or.kr  →  회원가입 →  [인증키 신청/관리] →  API 인증키 발급
#    무료 · 발급 즉시 사용 가능 · 일 20,000건 호출 제한(코드가 자동 스로틀·이어받기 합니다)
#    ▶ 매출·자산·유동자산/부채·자본금이 전부 여기서 나옵니다. 없으면 E층 전체가 죽습니다.
DART_API_KEY = ""

#    ▶ (선택·강력추천) 재무정보 일괄다운로드 ZIP 폴더 ─────────────────────────────────────
#      https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do  (로그인 불필요)
#      여기서 연도·보고서별 ZIP 을 받아 아래 폴더에 넣어두면 **API 호출 0회**로
#      재고자산·매출채권·매출원가·영업활동현금흐름까지 전부 확보됩니다.
#      (이 화면은 OpenAPI 가 아니라 웹 다운로드라, 코드가 대신 받아올 수 없습니다.
#       추측한 URL 을 때려보는 대신 '있으면 읽고 없으면 다른 경로로 간다'로 설계했습니다)
#      ※ 넣지 않아도 실행됩니다. 증거층 3센서는 OpenAPI 배치만으로 전부 산출됩니다.
DART_BULK_DIRS = [
    "/content/drive/MyDrive/tcd_cache/dart_bulk",
    "./tcd_cache/dart_bulk",
]

# ── ②-A KRX Open API 인증키  ★시가총액을 얻는 가장 확실한 경로 ─────────────────────────────
#    발급: https://openapi.krx.co.kr  →  회원가입(무료) →  [인증키 발급] →  아래에 붙여넣기
#          ※ 로그인용 ID/PW 가 아니라 '인증키' 문자열입니다.
#          ※ 엔드포인트별 이용신청이 필요할 수 있습니다(승인까지 하루 정도).
#
#    ▶ 왜 필요한가: U-MICRO 는 "시총 하위권"으로 정의되므로 **그 시점의 시가총액**이
#      없으면 유니버스 자체가 성립하지 않습니다. PBR·PER 의 분모이기도 합니다.
#      이 API 는 요청 1건에 그날 전 종목의 시가총액·상장주식수를 줍니다.
#      120개월 × 2시장 = 240회면 10년 PIT 시총 패널이 끝납니다(종목별 루프면 36만 회).
#      2010-01-04 부터 제공되어 백테스트 구간 전체를 덮습니다.
#
#    ▶ 아래 ②-B(마켓플레이스)와는 **호스트가 다릅니다**(data-dbg.krx.co.kr).
#      마켓플레이스가 차단돼 있어도 이 경로는 별개로 동작합니다.
KRX_OPENAPI_KEY    = ""

# ── ②-B KRX 데이터 마켓플레이스 (2025-12 인증방식 변경 대응) ─────────────────────────────
#    가입: https://data.krx.co.kr  →  우측 상단 [회원가입](무료) → 가입한 ID/PW를 아래에 입력
#
#    ▶ 비워두셔도 됩니다. 유니버스의 정확성은 상장일·폐지일(FDR/KIND)만으로 성립하도록
#      설계했고, KRX 스냅샷은 '검증·보강'입니다. 비우면 그 단계만 건너뜁니다.
#
#    ⚠ 같은 계정을 브라우저나 다른 노트북에서 동시에 로그인해 두지 마세요.
#      KRX는 중복 로그인 시 이전 세션을 강제 종료합니다(CD011). 그러면 실행 중인 수집이
#      JSON 대신 로그인 HTML을 받아 대량 실패합니다. 이 코드는 로그인을 메인 스레드에서
#      1회만 하고 모든 호출을 직렬화하지만, '바깥에서' 같은 계정을 쓰는 것까지는 못 막습니다.
#    ⚠ 과요청으로 IP가 차단되면 KRX는 HTTP 200 에 '차단 안내 HTML'을 담아 보냅니다.
#      이 코드는 그 패턴을 감지해 24시간 표식을 남기고 KRX 계열 호출을 **스스로 멈춥니다**.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

# ── ②-C 공공데이터포털 (KRX Open API 대체제 · 선택) ─────────────────────────────────────────
#    발급: https://www.data.go.kr  → 회원가입 → '금융위원회_주식시세정보' 검색 → [활용신청]
#          → 마이페이지 [일반 인증키(Decoding)] 복사
#    ▶ ②-A 와 같은 정보(시가총액·상장주식수)를 하루치 전 종목 단위로 줍니다.
#      ②-A 가 승인 대기 중일 때의 우회로입니다. 둘 다 비면 시총은 근사로 떨어집니다.
DATA_GO_KR_KEY  = ""

# ── ③ 구글드라이브 캐시  ★★★ 절대 1원칙 ★★★ ──────────────────────────────────────────────
#    이 코드는 기존 캐시·인덱스를 절대 삭제·덮어쓰기하지 않습니다. 약속이 아니라 구조입니다:
#      · 인덱스의 진실은 append-only JSONL 저널입니다(기존 줄을 다시 쓰지 않음).
#      · index.parquet 은 저널의 파생물이며, 재생성 전 항상 타임스탬프 백업합니다.
#        백업에 실패하면 컴팩션 자체를 건너뜁니다(저널이 원천이므로 유실 없음).
#      · blob 은 내용해시 경로에 쓰므로 같은 내용은 재기록조차 하지 않습니다.
#      · 이미 드라이브에 있던 리포트는 이동·개명 없이 '경로만' 등록합니다(adopt-by-reference).
#      · 삭제 API 자체가 없습니다. 손상 파일조차 지우지 않고 .corrupt 로 격리만 합니다.
#
#    GDRIVE_ROOT       : 캐시 최상위. ★v2 와 같은 경로를 쓰면 기존 수집분을 그대로 재활용합니다.
#    GDRIVE_SHARED_NS  : 공용 인덱스 — 다른 전략에서도 재활용 가능한 원본/범용 정제본
#                        (가격·재무·리포트 원장·애널리스트 원장). v2 와 동일한 "_shared" 입니다.
#    GDRIVE_PRIVATE_NS : 전용 인덱스 — 이 전략 고유의 피처/스코어/백테스트 산출물
GDRIVE_ROOT       = "/content/drive/MyDrive/tcd_cache"
GDRIVE_SHARED_NS  = "_shared"            # → {GDRIVE_ROOT}/_shared          (공용 · 전략 간 공유)
GDRIVE_PRIVATE_NS = "tcd_v3_micro_fw"    # → {GDRIVE_ROOT}/tcd_v3_micro_fw  (전용 · 이 전략)

#    ▸ 이미 다른 폴더에 리포트를 모아두셨다면 여기에 추가하세요. 재귀 스캔해서 '등록만' 합니다.
#      (파일을 옮기거나 지우지 않습니다. 경로/해시만 인덱스에 기록합니다)
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
    # "/content/drive/MyDrive/내가/모아둔/리포트폴더",
]

#    ▸ JupyterLab(로컬)에서 돌릴 때 쓸 경로. 드라이브 마운트가 불가하면 자동으로 이쪽입니다.
LOCAL_CACHE_ROOT  = "./tcd_cache"

# ── ④ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#    "SMOKE" : 합성데이터로 전체 출력물을 예행연습(수십 초). 네트워크·키 불필요.
#              백테스트·성과·강건성·해석표가 전부 나옵니다. ★처음엔 이걸로 한 번 돌려보세요.
#    "FULL"  : 스모크 → CANARY → 실데이터 수집 → 백테스트 → 강건성  (권장)
#    "CACHED": 스모크 → 드라이브 캐시만 사용(신규 수집 안 함) → 백테스트. 오프라인 재현용.
RUN_MODE = "FULL"

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   ▼ 아래부터는 기본값으로 두어도 됩니다 (전략 파라미터 · 성능 · 비용 가정)
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── ⑤ 백테스트 구간 ─────────────────────────────────────────────────────────────────────────
BACKTEST_START = "2016-08-01"
BACKTEST_END   = "2026-07-31"

# ── ⑥ U-MICRO 유니버스 정의 (§6 · C13) ──────────────────────────────────────────────────────
#    시총 랭크는 매 리밸런싱 시점의 '당시' 값으로 재산출합니다(현재 시총으로 과거를 정의하지 않음).
UMICRO_MCAP_RANK_MIN = 1400        # 시총 랭크 1400위 밖 = U-MICRO (절대 랭크)
UMICRO_PCTL_MIN      = 0.55        # 감쇠 감사에서 종목수 차이>20% 면 이 분위 기준으로 자동 전환
UMICRO_MIN_ADV_KRW   = 1e8         # 20일 평균거래대금 하한 (§7 방화벽 · V6 공용)
UMICRO_SEASONING_D   = 250         # 상장 + 250거래일
ATTRITION_GAP_TOL    = 0.20        # 2016 vs 2026 종목수 차이 허용치 → 초과 시 분위 기준 전환

#    ▸ 밴드 규칙 / 셀 세분화를 '사전에' 고정할지, 전 구간 통계로 자동 선택할지.
#      "auto" 는 편의를 위한 기본값이지만, 규칙 선택에 전 구간 통계(2026년 상장사 수 등)를
#      쓰므로 엄밀히는 '설정 단계의 룩어헤드'다. 신호값이 새는 것은 아니지만, 논문급
#      엄밀성이 필요하면 "rank"/"pctl", "fine"/"coarse" 로 고정하고 그 사실을 명시하세요.
#      어느 쪽이든 실행 시 어떤 규칙이 쓰였는지 로그와 감쇠표에 그대로 찍힙니다.
UMICRO_BAND_RULE     = "auto"      # "auto" | "rank"(절대 랭크) | "pctl"(분위)
CELL_RULE            = "auto"      # "auto" | "fine"(업종 그대로) | "coarse"(상위 업종)

#    ▸ 시총 스냅샷을 못 얻은 구간에서 '현재 상장주식수'로 근사할지.
#      True 면 커버리지가 올라가지만 액면분할·유상증자가 잦았던 종목의 과거 시총이
#      과대평가된다(비PIT). False 면 그런 행은 시총 미상으로 남고 거래대금 대리변수로 판정한다.
MCAP_ALLOW_NONPIT_FALLBACK = True

# ── ⑦ 방화벽 / 거부권 임계 (§7 · §9) ────────────────────────────────────────────────────────
FW_VALUE_RANK_MAX    = 0.30        # 딥밸류 진입: PBR·PER 결합 밸류 랭크 하위 30%
FW_OPCF_NEG_STREAK   = 4           # 최근 N분기 연속 영업CF<0
FW_ICOV_MIN          = 1.0         # 이자보상배율 하한 (위 조건과 AND 로 결합될 때만 배제)
V1_PUSH_RATIO        = 1.5         # (Δ재고+Δ매출채권)/Δ매출 > 1.5 → 밀어내기 의심
V2_CFO_RATIO         = 0.5         # 순이익>0 인데 영업CF < 0.5×순이익, 3분기 연속
V3_DILUTION_DAYS     = 90          # 90일 내 대규모 희석성 조달(유증/CB/BW)
V3_DILUTION_PCT      = 0.10        # 시총 대비 조달규모 비율 하한

# ── ⑧ 포지션 / 사이징 (드로다운 한가운데서 정하지 않도록 상수로 못박음) ─────────────────────
PORTFOLIO_TOP_PCT       = 0.05     # 신호 상위 5% 진입
PORTFOLIO_MAX_NAMES     = 25
PORTFOLIO_MIN_NAMES     = 5
POS_MAX_WEIGHT          = 0.12     # 종목당 최대 비중
POS_MIN_WEIGHT          = 0.02
POS_ADV_PARTICIPATION   = 0.10     # 20일 평균거래대금의 10% 이내로 보유 제한
HOLD_MAX_MONTHS         = 24       # 보유 상한 (§10)
ACCOUNT_KRW             = 30_000_000   # 소액계좌 가정 (최소주문/유동성 제약 계산용)

# ── ⑨ 비용 시나리오 (R9) ────────────────────────────────────────────────────────────────────
#    낙관 0.35% / 기준 0.80% / 비관 1.50% + 거래대금 참여율 5% 상한
COST_SCENARIOS = {
    "낙관": {"roundtrip": 0.0035, "participation": 0.20},
    "기준": {"roundtrip": 0.0080, "participation": 0.10},
    "비관": {"roundtrip": 0.0150, "participation": 0.05},
}
COST_BASE_SCENARIO = "기준"

# ── ⑩ 애널리스트 리포트 (한경컨센서스 · 네이버 리서치) ──────────────────────────────────────
#    ▶ 이 전략의 E층은 리포트에 의존하지 않습니다(U-MICRO는 커버리지가 구조적으로 얇음).
#      리포트는 ① U층 보조신호(같은 애널리스트의 목표주가 리비전)와 ② 원장 무결성 감사에
#      쓰이며, 커버리지 결측률이 25%를 넘으면 C14-c 규칙에 따라 U층에서 자동 제외됩니다.
#      제외되더라도 '왜 제외됐는지'는 표로 출력합니다.
#    ▶ 드라이브에 이미 있는 리포트를 최우선으로 재사용합니다(adopt-by-reference).
RESEARCH_USE           = True     # False = 리포트 수집·사용 전면 비활성
RESEARCH_COLLECT       = True     # False = 드라이브 캐시에 있는 것만 사용(신규 수집 안 함)
RESEARCH_SOURCES       = ["hankyung", "naver"]
RESEARCH_DOWNLOAD_PDF  = False    # U-MICRO 전략엔 리스트 메타만으로 충분. True면 원문까지(용량↑)
RESEARCH_PDF_MAX_PER_MONTH = 0    # 0 = 무제한
RESEARCH_TARGET_PER_YEAR   = 30000
RESEARCH_MAX_MISSING_RATE  = 0.25 # C14-c: 결측률 이 값 초과 → U층에서 자동 제외

# ── ⑩-B 런타임 예산 ★계약(§10) — 코드가 스스로 강제한다 ────────────────────────────────────
#    "총 wall-clock 1~4시간 이내에 결과가 나와야 한다"는 협상 대상이 아니다.
#    아래 값은 '희망'이 아니라 **강제 한도**다. 각 수집 단계는 시작 전에
#      ① 남은 시간 ② 남은 DART 호출 한도
#    로 필요량을 견적내고, 예산 안에 못 들어가면 **더 싼 경로로 내려가거나 그 단계를 줄인다.**
#    예산을 넘길 수밖에 없으면 시작하지 않고 무엇을 못 했는지 표로 보고한다.
#    ▶ 콜드빌드(캐시가 비어 있는 첫 실행)를 며칠에 걸쳐 완성하고 싶다면
#      COLD_BUILD_MODE=True 로 두세요. 그때만 예산 강제가 풀립니다(그 사실을 로그에 명시).
MAX_WALLCLOCK_MIN   = 240     # 전체 실행 상한 (§10 하드 제약)
COLLECT_BUDGET_MIN  = 55      # 수집(L1) 전체 예산 (§5)
COLD_BUILD_MODE     = False   # True = 예산 강제 해제. 며칠에 걸친 콜드빌드 전용.

#    ▶ 단계별 배정(분). 합이 COLLECT_BUDGET_MIN 이다. ★총량만 재면 아무 소용이 없다 —
#      실측 사고에서 L1 합계가 183.7분(예산 30분의 6.1배)이었는데도 '총 wall-clock' 줄은
#      4시간 안이라며 ✔ 를 찍었다. 한 단계가 다른 단계의 예산을 다 먹어도 아무도 안 막았다.
#      → 단계마다 배정을 두고, 배정을 넘기면 그 단계부터 '캐시 전용'으로 강등한다.
#        (수집을 조용히 계속하지 않는다. 무엇을 못 받았는지 표로 보고한다)
STAGE_BUDGET_MIN = {
    "L1.SEC":   4,      # 종목 마스터
    "L1.PX":   15,      # 가격 (콜드빌드에서 가장 무겁다)
    "L1.DART":  8,      # 재무 (배치 경로는 4분이면 끝난다)
    "L1.MCAP":  5,      # 시가총액 (KRX Open API 면 240회 ≈ 4분)
    "L1.ACT":   6,      # 관리종목·감사의견
    "L1.DIS":   5,      # 공시목록
    "L1.RSRCH": 12,     # 애널리스트 리포트
}
DART_BUDGET_MIN     = STAGE_BUDGET_MIN["L1.DART"]
RESEARCH_BUDGET_MIN = STAGE_BUDGET_MIN["L1.RSRCH"]

# ── ⑪ 성능 / 자원 ───────────────────────────────────────────────────────────────────────────
N_WORKERS_IO   = 12     # 네트워크 병렬(스레드). 차단 위험을 낮추려면 8로 줄이세요.
N_WORKERS_CPU  = 0      # 연산 병렬(프로세스). 0 = CPU 코어수 자동(-1)
RATE_LIMIT_QPS = {      # 소스별 초당 요청 상한 — 차단 방지용. 낮출수록 안전/느림.
    "dart":      8.0,
    "hankyung":  2.5,
    "naver":     3.0,
    "krx":       2.0,   # data.krx.co.kr (마켓플레이스) — 차단 이력이 있어 보수적으로
    "krxapi":    2.0,   # data-dbg.krx.co.kr (KRX Open API) — 위와 별개 호스트·별개 버킷
    "datagokr":  5.0,
    "customs":   3.0,
    "kind":      2.0,
    "generic":   3.0,
}
MEM_BUDGET_GB  = 6.0    # 이 값을 넘길 것 같으면 청크 처리로 자동 전환
CIRCUIT_BREAK_N = 15    # 연속 실패 N회 → 해당 소스 중단하고 보고

# ── ⑫ 재현성 / 안전장치 ─────────────────────────────────────────────────────────────────────
SEED = 20260807               # 모든 난수는 이 시드에서 파생
VERBOSE = True
STOP_ON_KILL_CRITERIA = True  # §12 킬 기준 위반 시 즉시 중단하고 보고 (False 로 끄지 마세요)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝. 아래부터는 수정하지 않아도 됩니다.
# ═══════════════════════════════════════════════════════════════════════════════════════════

STRATEGY_ID     = "TCD_V3_MICRO_FW"
STRATEGY_NAME   = "MICRO-FW · U-MICRO 방화벽 중심 전략"
BUILD_VERSION   = "v3.20260808.0345"
ACTIVE_PACKS: list = []          # v3 전략2는 센서팩을 쓰지 않는다(경량화). 호환용 빈 목록.

# 공공데이터포털/관세청 키는 이 전략에서 쓰지 않는다(경량화). 코어 호환을 위해 빈 값만 유지.
DATA_GO_KR_KEY  = ""
CUSTOMS_API_KEY = ""


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
    # scipy 는 이 파일에서 직접 import 하지 않는다(HAC t·회귀는 numpy 로 구현).
    # 필수로 두면 설치 실패 시 SystemExit 로 실행 자체가 막히므로 선택으로 내린다.
    # 단 pandas 의 corr(method="spearman") 은 내부적으로 scipy 를 요구하므로, 그 경로를
    # 쓰는 코드를 추가한다면 여기서 다시 필수로 올려야 한다.
    ("requests",  "requests",           True,  "모든 HTTP 수집"),
    ("bs4",       "beautifulsoup4",     True,  "리서치 리스트 파싱"),
    ("lxml",      "lxml",               True,  "HTML/XML 고속 파서"),
    ("tqdm",      "tqdm",               True,  "진행률 표시"),
]
_OPTIONAL = [
    ("scipy",     "scipy",              "통계검정(현재 미사용 — pandas spearman 사용 시 필요)"),
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

# ★ 서드파티 로거 억제. yfinance 는 종목 하나가 실패할 때마다 여러 줄을 stderr 로 쏟아내
#   (\"possibly delisted\", \"1 Failed download\"), 2,600종목 폴백 구간에서 로그가 수만 줄
#   불어나 정작 우리 진단표가 파묻힌다. 실패 자체는 수집부가 집계해 표로 보고한다.
for _noisy in ("yfinance", "urllib3", "peewee", "requests", "py.warnings", "matplotlib"):
    try:
        logging.getLogger(_noisy).setLevel(logging.CRITICAL)
    except Exception:
        pass
logging.captureWarnings(True)

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
        # ★ 아직 시작하지 않은(PENDING) 스테이지는 t_start=0 이라 그대로 빼면
        #   유닉스 epoch 전체(≈1.7e9초)가 소요시간으로 잡혀 표와 런타임 감사가 망가진다.
        if not self.t_start:
            return 0.0
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
    (r"가격 데이터를 한 종목도|서킷브레이커",
     "가격 소스에 전혀 도달하지 못했습니다. ① 방화벽/프록시 환경이면 "
     "raw.githubusercontent.com · fchart.stock.naver.com · data.krx.co.kr 접근을 확인하세요. "
     "② 드라이브 캐시(krx_ohlcv_daily)가 있으면 RUN_MODE='CACHED' 로 두면 네트워크 없이 "
     "백테스트가 됩니다. ③ 서킷브레이커는 '연속 실패'를 감지해 조기 종료한 것이므로, "
     "네트워크가 정상인 환경에서 재실행하면 캐시에 정확히 이어서 받습니다."),
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
        # ★ 계층 예산은 설정에서 읽는다. 하드코딩해 두면 설정과 표가 어긋나서,
        #   L1 이 배정의 6배를 써도 총계 줄만 보고 '예산 내'라고 읽게 된다(실측 사고).
        _l1 = float(globals().get("COLLECT_BUDGET_MIN", 30)) * 60
        _tot = float(globals().get("MAX_WALLCLOCK_MIN", 240)) * 60
        budgets = {"L1": _l1, "L2": 2 * 60, "L3": 3 * 60, "L5": max(_tot * 0.25, 600)}
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
        _sum = sum(agg.values())
        # ★ 총계 판정은 '총 상한 이내'만으로 내리지 않는다. 어느 계층이든 배정을 넘겼으면
        #   총계도 초과로 표시한다 — 그러지 않으면 "L1 6.1배 초과"와 "총계 ✔ 예산 내"가
        #   같은 화면에 나란히 찍히고, 사람은 아래 줄만 본다.
        _breach = [l for l, b in budgets.items() if b and agg.get(l, 0.0) > b]
        _ok = (_sum <= _tot) and not _breach
        rows.append(["합계", f"{_sum:8.2f}s", f"{_sum / 60:6.2f}분", f"{_tot/3600:.0f}시간",
                     "✔ 예산 내" if _ok else
                     (f"❗ 계층 초과({','.join(_breach)}) — 총량은 상한 내이나 배분이 무너졌습니다"
                      if _sum <= _tot else "❗ 초과 — 아키텍처 수정 필요")])
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
    t = t.normalize()
    try:
        t = t.as_unit("ns")                      # ★ 해상도 통일 — 아래 주석 참조
    except Exception:
        pass
    return t


def as_ts_series(s) -> pd.Series:
    """tz-naive · 자정 정규화 · **datetime64[ns] 고정** Series.

    ★ 해상도(unit)를 ns 로 못박는 이유 — pandas 2.x→3.x 에서 실제로 터진 버그다:
      pd.to_datetime 은 입력에 따라 해상도를 다르게 추론한다.
        "2016-09-30" (문자열)        → datetime64[s]
        pd.date_range(...)           → datetime64[ns]
      merge 는 해상도가 달라도 붙지만 **merge_asof 는 MergeError 로 거부한다**
      ("incompatible merge keys dtype('<M8[s]') and dtype('<M8[ns]')").
      이 프로젝트의 PIT 결합은 전부 merge_asof 이므로, 한쪽이 문자열 출신이면
      as-of 결합이 통째로 실패하고 → 상위에서 폴백되어 → 그 컬럼이 전부 결측이 되고
      → 유니버스가 '에러 없이' 0 종목으로 붕괴한다. 로그에는 경고 한 줄만 남는다.
      해상도를 여기 한 곳에서 고정해 그 사고 경로 자체를 없앤다.
    """
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    out = out.dt.normalize()
    try:
        out = out.astype("datetime64[ns]")
    except Exception:
        pass
    return out


def month_end(x) -> Optional[pd.Timestamp]:
    t = as_ts(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_range(start, end) -> pd.DatetimeIndex:
    # ★ "ME" 별칭은 pandas 2.2 이상에서만 유효하다. offset 객체는 1.x~3.x 전부에서 동작한다.
    #   (Colab 의 pandas 가 2.0/2.1 이면 이 한 줄 때문에 실행이 시작도 못 하고 죽는다)
    return pd.date_range(month_end(start), month_end(end), freq=pd.offsets.MonthEnd())


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


_CORRUPT_PAT = re.compile(
    r"ArrowInvalid|ArrowIOError|Parquet magic bytes|not a parquet file|"
    r"Couldn't deserialize|corrupt|invalid.*footer|Repetition level", re.I)


def read_parquet_safe(path: str) -> Optional[pd.DataFrame]:
    """읽기 실패를 '손상'과 '일시적 IO 오류'로 구분한다.

    ★ 왜 구분이 중요한가 ─────────────────────────────────────────────────────────────
      예전에는 어떤 예외든 곧바로 파일을 .corrupt 로 개명(os.replace)했다. 그런데 구글드라이브
      FUSE 마운트는 정상 상태에서도 'Transport endpoint is not connected', 타임아웃, 쿼터
      스로틀 같은 '일시적' 오류를 낸다. 그러면 멀쩡한 공용 캐시가 격리되고, 곧이어
      put_table 이 '없는 파일'로 판단해 백업 없이 새로 만들어 버린다.
      = 잠깐의 네트워크 딸꾹질이 다른 전략의 캐시를 통째로 날린다. 절대 1원칙 위반이다.
    → ① 3회 재시도(지수 백오프) ② parquet 포맷 오류로 확인될 때만 격리 ③ 그 외에는
      None 을 돌려줄 뿐 파일에 손대지 않는다(다음 실행에서 다시 읽으면 된다).
    """
    if not os.path.exists(path):
        return None
    last = None
    for attempt in range(3):
        try:
            return pd.read_parquet(path)
        except Exception as e:                 # noqa
            last = e
            if attempt < 2:
                time.sleep(0.6 * (2 ** attempt))
    blob = f"{type(last).__name__}: {last}"
    if not _CORRUPT_PAT.search(blob):
        LOG.warn(f"parquet 읽기 실패(일시적 오류로 판단) — 파일은 그대로 두고 이번 실행에서만 "
                 f"건너뜁니다: {os.path.basename(path)} ({type(last).__name__}). "
                 f"드라이브 마운트가 불안정할 때 흔합니다. 다음 실행에서 다시 읽습니다.")
        return None
    LOG.warn(f"parquet 손상 확인 — 지우지 않고 격리 보관합니다: {os.path.basename(path)} ({blob[:80]})")
    try:                                       # 손상 파일은 지우지 않고 격리 보관 (원본 보호 원칙)
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
    # ★ 줄마다 write 하면 기본 8KiB 버퍼가 임의 지점에서 flush 되어, 두 노트북이 동시에
    #   append 할 때 한 줄이 반토막 난 채 섞인다(read_jsonl 이 그 줄을 조용히 버린다).
    #   한 번의 write 로 넘기면 대부분의 경우 원자적으로 처리된다.
    blob = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
    with open(path, "a", encoding="utf-8") as f:
        f.write(blob)
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
    # ★ astype(object) 로 캐스팅하지 않는다. 셀 컬럼은 일부러 category 로 만들어 두는데
    #   여기서 파이썬 문자열 20만 개로 되돌려 매 호출마다 해싱한다 — 랭크 호출이 수십 번
    #   반복되는 경로라 그대로 누적 비용이 된다. category 면 코드 정수로 그룹핑된다.
    _c = pd.Series(cells)
    if isinstance(_c.dtype, pd.CategoricalDtype):
        grp = _c.cat.add_categories(["__NA__"]).fillna("__NA__") if _c.isna().any() else _c
    else:
        grp = _c.fillna("__NA__").astype("category")
    grp = grp.to_numpy() if not isinstance(grp.dtype, pd.CategoricalDtype) else grp.values
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
                # ★ dtype 주의: np.nan 으로 만들면 float64 컬럼이 되고, 아래에서 sha1 문자열을
                #   .loc 로 넣는 순간 pandas 2.x 는 FutureWarning, **pandas 3.0 은 TypeError** 다.
                #   그런데 이 코드는 critical 스테이지(L0.VAULT) 안이라 실행 전체가 죽는다.
                #   트리거도 흔하다 — uid 컬럼이 없는 레거시 인덱스 파일 하나면 충분하고,
                #   이 파일은 v2 캐시 루트를 그대로 재사용하라고 안내한다.
                idx["uid"] = pd.Series(np.nan, index=idx.index, dtype=object)
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
                # 같은 이유로 object 로 만든다 — INDEX_COLUMNS 는 대부분 문자열 컬럼이다.
                idx[c] = pd.Series(np.nan, index=idx.index, dtype=object)
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
            # ★ 백업 파일명은 초 단위였고 shutil.copy2 는 같은 이름을 말없이 덮어쓴다.
            #   같은 테이블을 1초 안에 두 번 쓰면(security_master 가 실제로 그렇다)
            #   두 번째 백업이 첫 번째를 덮어써, '교체 직전 원본'의 유일한 사본이 사라진다.
            #   → 마이크로초 + 내용해시로 이름을 유일화하고, 이미 있으면 절대 덮지 않는다.
            try:
                _tag = sha1_file(path)[:8]
            except Exception:
                _tag = "nohash"
            bak = os.path.join(self.ns[scope], "index", "_backup",
                               f"{name}.{_dt.datetime.now():%Y%m%d_%H%M%S_%f}.{_tag}.parquet")
            try:
                if os.path.exists(bak):
                    raise FileExistsError(bak)
                shutil.copy2(path, bak)
                self._prune_backups(scope, name)
            except Exception as e:                          # noqa
                LOG.warn(f"기존 테이블 백업 실패({type(e).__name__}) — 안전을 위해 덮어쓰지 않고 "
                         f"리비전 파일로 저장합니다: {name}")
                path = os.path.join(self.table_dir(scope),
                                    f"{name}.rev{_dt.datetime.now():%Y%m%d_%H%M%S_%f}.parquet")
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

    BACKUP_KEEP = 10

    def _prune_backups(self, scope: str, name: str):
        """테이블별 백업 보관 개수를 제한한다(최근 N개만 유지).

        ★ 이건 '캐시 삭제'가 아니라 '백업 보존 정책'이다. 원본 테이블·저널·blob 은
          절대 건드리지 않는다. 정책이 없으면 put_table 마다 수 GB 파일이 통째로 복사돼
          _backup 이 무한히 커지고, 결국 용량이 차서 put_table 이 조용히 실패한다
          (예외를 삼키고 None 을 반환하므로 '성공한 실행'처럼 보이면서 아무것도 저장되지 않는다).
        """
        try:
            d = os.path.join(self.ns[scope], "index", "_backup")
            files = [os.path.join(d, f) for f in os.listdir(d)
                     if f.startswith(name + ".") and f.endswith(".parquet")]
            if len(files) <= self.BACKUP_KEEP:
                return
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for p in files[self.BACKUP_KEEP:]:
                try:
                    os.remove(p)
                    self.stats["backup_pruned"] += 1
                except Exception:
                    pass
        except Exception:
            pass

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
        # ★ 볼트 자신의 디렉터리는 스캔하지 않는다.
        #   GDRIVE_ADOPT_DIRS 의 기본값이 GDRIVE_ROOT 와 같아서, 그대로 두면 _shared/table
        #   아래의 자기 자신이 만든 parquet(krx_ohlcv_daily 등)을 '기존 캐시'로 다시 등록한다.
        #   adopt uid 에 파일 크기가 들어가므로 테이블이 커질 때마다 uid 가 바뀌어
        #   매 실행 새 저널 행이 쌓인다 = 인덱스가 무한히 부풀고 load_index 가 느려진다.
        _self_dirs = [os.path.realpath(self.root)] + \
                     [os.path.realpath(p) for p in self.ns.values()]

        def _is_self(p: str) -> bool:
            rp = os.path.realpath(p)
            return any(rp == s or rp.startswith(s + os.sep) for s in _self_dirs)

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
                               if not x.startswith(".") and x != "_backup"
                               and not _is_self(os.path.join(dirpath, x))]
                if _is_self(dirpath):
                    continue
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
    if source == "krx" and krx_blocked():
        return None                       # 차단 중에는 요청 자체를 보내지 않는다(연장 방지)
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
                out = r.content if as_bytes else _decode(r.content, r.encoding, url, force_enc)
                # ★ 차단은 200 OK 로 온다. 안내 페이지를 데이터로 착각하면 계속 때리게 된다.
                if _check_krx_block(source, out if isinstance(out, str) else
                                    (out[:4000].decode("utf-8", "ignore") if out else "")):
                    return None
                return out
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
    if source == "krx" and krx_blocked():
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
                out = r.content if as_bytes else _decode(r.content, r.encoding, url)
                if _check_krx_block(source, out if isinstance(out, str) else ""):
                    return None
                return out
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                                # noqa
            with _HTTP_LK:
                HTTP_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(1.5 * (attempt + 1))
    with _HTTP_LK:
        HTTP_STATS[f"{source}:POSTFAIL"] += 1
    return None


# ── KRX 접속 차단 감지 ──────────────────────────────────────────────────────────────────────
#  ★ 실제 사고: 자동화 대량 조회로 판단되어 사용자 IP 가 1일 차단됐다.
#    KRX Data Marketplace 는 차단 시 200 OK 로 '이용 제한 안내' HTML 을 준다. 그래서
#    코드는 실패로 인식하지 못하고 계속 때렸고, 그게 차단을 연장시킬 수 있다.
#    → 차단 페이지를 감지하면 즉시 이번 실행의 KRX 경로를 전부 끄고, 마커를 남겨
#      다음 실행에서도 해제 시각까지 KRX 를 건드리지 않는다. 재시도는 하지 않는다.
_KRX_BLOCK_PAT = re.compile(
    r"이용\s*제한|비정상\s*대량\s*조회|ip-block-page|자동화\s*수단", re.I)
KRX_BLOCK = {"blocked": False, "until": 0.0, "logged": False}
KRX_BLOCK_HOURS = 24.0


def _krx_marker_path() -> Optional[str]:
    root = None
    try:
        v = globals().get("VAULT")
        root = getattr(v, "root", None) if v is not None else None
    except Exception:
        root = None
    root = root or globals().get("LOCAL_CACHE_ROOT")
    if not root:
        return None
    return os.path.join(str(root), "_locks", "krx_block.json")


def krx_block_load():
    """이전 실행에서 남긴 차단 마커를 읽는다. 해제 시각 전이면 이번에도 KRX 를 쓰지 않는다."""
    p = _krx_marker_path()
    if not p or not os.path.exists(p):
        return
    try:
        info = json.loads(open(p, encoding="utf-8").read() or "{}")
        until = float(info.get("until", 0))
    except Exception:
        return
    if until > time.time():
        KRX_BLOCK["blocked"], KRX_BLOCK["until"] = True, until
        LOG.warn(f"이전 실행에서 KRX 접속 제한이 감지되었습니다. 해제 예정 "
                 f"{_dt.datetime.fromtimestamp(until):%Y-%m-%d %H:%M} 까지 KRX 경로를 "
                 f"사용하지 않습니다. 유니버스·가격은 FDR/네이버 경로로 정상 동작합니다.")


def krx_mark_blocked():
    KRX_BLOCK["blocked"] = True
    KRX_BLOCK["until"] = time.time() + KRX_BLOCK_HOURS * 3600
    if not KRX_BLOCK["logged"]:
        KRX_BLOCK["logged"] = True
        LOG.error(
            "KRX 접속 제한 감지 — 이번 실행의 KRX 경로를 전부 중단합니다.\n"
            "   KRX Data Marketplace 가 '자동화 수단을 통한 비정상 대량 조회'로 판단해\n"
            "   해당 IP 를 약 1일간 제한했습니다(차단 시에도 HTTP 200 으로 안내 페이지를 줍니다).\n"
            "   · 이번 실행: 시총 스냅샷 등 KRX 의존 단계를 건너뛰고 FDR/네이버/DART 로 진행합니다.\n"
            "   · 다음 실행: 해제 시각까지 KRX 를 아예 건드리지 않습니다(마커 저장).\n"
            "   · 권장: KRX_MARKETPLACE_ID/PW 를 비우고 돌리거나, 공식 경로인\n"
            "     KRX Open API(openapi.krx.co.kr)의 인증키를 KRX_OPENAPI_KEY 에 넣으세요.")
    p = _krx_marker_path()
    if p:
        try:
            _ensure_dir(p)
            atomic_write_text(p, json.dumps({"until": KRX_BLOCK["until"],
                                             "at": _dt.datetime.now().isoformat()}))
        except Exception:
            pass


def krx_blocked() -> bool:
    if KRX_BLOCK["blocked"] and KRX_BLOCK["until"] > time.time():
        return True
    if KRX_BLOCK["blocked"] and KRX_BLOCK["until"] <= time.time():
        KRX_BLOCK["blocked"] = False
    return KRX_BLOCK["blocked"]


def _check_krx_block(source: str, text: Optional[str]) -> bool:
    """차단 안내 페이지인지 확인. 맞으면 True(=이 응답은 데이터가 아니다)."""
    if not text or source != "krx":
        return False
    head = text[:4000]
    if _KRX_BLOCK_PAT.search(head) and ("KRX" in head or "krx" in head):
        krx_mark_blocked()
        return True
    return False


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
        if krx_blocked():
            self._warm, self._authed = True, False
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
        if krx_blocked():          # 차단 중에는 pykrx 도 KRX 를 때린다 → 전면 중단
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

    # ★ 상장폐지 목록의 절반 이상은 보통주가 아니다.
    #   실측 구성: 주권 약 2,100 · 신주인수권증서 865 · 수익증권 783 · 투자회사 176 ·
    #   신주인수권증권 160 · 리츠/선박펀드 등. 신주인수권증서는 수명이 7일짜리이고
    #   코드도 '4323201G' 같은 8자리라, 그대로 두면 유니버스에 유령 종목이 섞인다.
    #   ★ 단, 구분값이 비어 있는 행은 버리지 않는다 — '모른다'를 이유로 버리면
    #     그게 곧 생존자편향의 재유입이다. '명시적으로 보통주가 아닌' 행만 제외한다.
    n_nonstock = 0
    if "secugroup" in t.columns and t["secugroup"].astype(str).str.strip().ne("").any():
        sg = t["secugroup"].astype(str).str.strip()
        known = sg.ne("") & sg.ne("nan")
        is_stock = sg.str.contains("주권", na=False) & ~sg.str.contains("신주인수권", na=False)
        drop = known & ~is_stock
        n_nonstock = int(drop.sum())
        if n_nonstock:
            LOG.info(f"  폐지목록에서 보통주가 아닌 {n_nonstock:,}건 제외 "
                     f"(신주인수권증서·수익증권·투자회사·리츠 등). 구분값이 비어 있는 행은 "
                     f"보수적으로 남깁니다 — 모른다는 이유로 버리면 생존자편향이 됩니다. "
                     f"제외 구분 예시: {sorted(set(sg[drop]))[:6]}")
            t = t[~drop]

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
    # ★ 기준은 '전체 기간 중앙값'이 아니라 '이웃 시점 중앙값'이다.
    #   상장사 수가 10년간 30% 넘게 늘어서, 전체 중앙값으로 자르면 초기 연도의 정상
    #   스냅샷이 후반기 증가 때문에 '부분 응답'으로 오인되어 폐기된다.
    # ★ 그리고 폐기는 '이번 실행의 판단'일 뿐이므로 캐시에는 원본을 그대로 남긴다.
    #   폐기된 프레임을 저장하면 한 번의 오판이 공용 캐시에서 그 시점을 영구히 지운다.
    snap_all = snap
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        local = size.rolling(5, center=True, min_periods=1).median()
        bad = size[size < local * 0.80]
        if len(bad):
            LOG.warn(f"스냅샷 {len(bad)}개 시점이 이웃 시점 중앙값의 80% 미만이라 "
                     f"이번 실행에서는 사용하지 않습니다(캐시에는 보존): "
                     f"{[str(pd.Timestamp(x).date()) for x in bad.index[:6]]}")
            snap = snap[~snap["snap_date"].isin(bad.index)]
    if new_rows:
        out = snap_all.copy()
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
        if krx_blocked():
            self.status = "BLOCKED"
            LOG.warn("KRX 접속 제한 상태이므로 로그인을 시도하지 않습니다 "
                     "(재시도가 제한을 연장시킬 수 있습니다).")
            return False
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
        if not self.session_ok or krx_blocked():
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

# ── 서킷브레이커 ────────────────────────────────────────────────────────────────────────────
#  ★ 없으면 어떤 일이 벌어지는가 (실측):
#    네트워크가 막힌 환경에서 2,600종목 × 4개 소스 × 재시도를 전부 돌린다. 한 종목당
#    수 초씩만 걸려도 몇 시간이 그냥 사라지고, 로그에는 같은 실패가 수만 줄 쌓인다.
#    이 전략의 하드 제약이 '총 4시간 이내'이므로, 이건 성능 문제가 아니라 요구사항 위반이다.
#  → 연속 N회 전 소스 실패하면 즉시 차단하고, 남은 종목은 캐시/폴백으로 진행한다.
#    (v2 헤더에는 CIRCUIT_BREAK_N 이 없으므로 기본값으로 안전하게 폴백한다)
_CB_N = int(globals().get("CIRCUIT_BREAK_N", 15) or 15)


class _Circuit:
    def __init__(self, n: int, name: str):
        self.n, self.name = max(int(n), 1), name
        self.streak, self.tripped, self.fails = 0, False, 0
        self._lk = threading.Lock()

    def ok(self):
        with self._lk:
            self.streak = 0

    def fail(self) -> bool:
        with self._lk:
            self.streak += 1
            self.fails += 1
            if not self.tripped and self.streak >= self.n:
                self.tripped = True
                LOG.error(f"서킷브레이커 작동 — {self.name} 연속 {self.streak}회 실패. "
                          f"남은 대상의 신규 수집을 중단하고 캐시/폴백으로 진행합니다. "
                          f"(네트워크 차단·소스 구조 변경·차단(403) 이 대표 원인입니다)")
            return self.tripped


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

        breaker = _Circuit(_CB_N, "일봉 수집")

        def _one(job):
            code, st = job
            if breaker.tripped:                 # 차단 후에는 즉시 반환 — 헛돌지 않는다
                return None
            for nm, fn in PRICE_CHAIN:
                try:
                    d = fn(code, st, end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    d = d.dropna(subset=["date"])
                    if len(d):
                        breaker.ok()
                        return d
            breaker.fail()
            return None

        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 12), desc="일봉 수집")
        if breaker.tripped:
            LOG.warn(f"서킷브레이커로 일봉 수집을 조기 종료했습니다 (실패 {breaker.fails:,}건). "
                     f"드라이브 캐시에 있는 분량만으로 백테스트를 진행합니다. "
                     f"네트워크가 정상인 환경에서 재실행하면 캐시에 이어서 받습니다.")
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

    # ★★ 저장은 '자르기 전' 전체를, 반환은 '자른' 창만. 순서를 바꾸면 캐시가 파괴된다. ★★
    #   put_table 은 전체 파일 교체다. 백테스트 창으로 자른 프레임을 그대로 저장하면
    #   공용 캐시에 있던 창 밖 구간(다른 전략이 모아둔 2010~2016 같은 과거분)이
    #   이 전략을 한 번 돌렸다는 이유만으로 영구 삭제된다. 신규 수집이 단 1종목만 있어도
    #   기록이 일어나므로 사고 확률이 낮지도 않다. 사용자의 절대 1원칙 위반이다.
    px_all = px                                       # 영속화용 — 자르지 않은 합집합
    px = px_all[(px_all["date"] >= as_ts(start) - pd.Timedelta(days=400)) &
                (px_all["date"] <= end_ts)]           # 반환용 — 이 전략의 창

    if new_frames:
        n_out = int(len(px_all) - len(px))
        if n_out:
            LOG.debug(f"공용 캐시에는 창 밖 {n_out:,}행을 포함한 전체를 저장합니다 "
                      f"(다른 전략의 구간을 지우지 않기 위함).")
        VAULT.put_table("krx_ohlcv_daily", px_all, scope="shared", domain="price",
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
    # ★ transform(lambda) 는 종목마다 파이썬 호출이 한 번씩 난다. 일별 800만 행 · 3,500종목
    #   규모에서 그대로 수 분이다. groupby().rolling() 은 C 레벨에서 한 번에 돈다.
    px["adv20"] = (px.groupby("code", observed=True)["amount"]
                     .rolling(20, min_periods=10).mean()
                     .reset_index(level=0, drop=True)
                     .reindex(px.index))
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
        if st == "020":
            if DBUDGET is not None:
                DBUDGET.exhausted = True
            LOG.warn(f"DART status=020 (일일 호출한도 초과) — 수집을 중단하고 받은 만큼 "
                     f"저장합니다. 내일 재실행하면 정확히 이어받습니다.")
        elif st == "021":
            # ★ 021 은 '조회 가능한 회사 개수 초과' = 요청 1건의 배치 크기 문제이지
            #   일일 한도가 아니다. 이걸 exhausted 로 처리하면 그 시점부터 남은 전 종목의
            #   수집이 중단된다 — 한 번의 배치 실수로 그날 수집 전체가 죽는다.
            LOG.debug(f"DART status=021 (배치 크기 초과) ep={endpoint} — 이 요청만 실패 처리하고 "
                      f"나머지는 계속 진행합니다.")
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
#  ★ 비교치(전기·전전기) 컬럼을 반드시 함께 보관한다 — 이 전략의 생사가 여기 걸려 있다.
#    DART 는 어떤 재무 응답에서도 '당기'와 함께 '전기 동기'를 같이 준다.
#      · 재무상태표(BS): frmtrm_amount = 전기말 잔액
#      · 손익/현금흐름(IS/CF): thstrm_add_amount = 당기 누적, frmtrm_add_amount = 전기 누적
#    이걸 읽으면 매출증가율·자산회전율변화·운전자본발생액이 **단일 행에서** 산출된다.
#    반대로 당기금액만 읽으면 YoY 를 만들려고 'TTM(연속 4분기) → lag4' 체인을 타야 하고,
#    그 순간 연속 8분기 공시를 요구하게 된다. 분기보고서를 거르는 소형주가 흔한
#    U-MICRO 에서는 그 체인만으로 결측률이 26% 를 넘어 C14-c 로 축이 통째로 죽는다.
#    (실측 사고: i_sales 26.1% 결측 → 임계 25% 초과 → 활성 TP 0개 → C14-d 중단)
_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div",
            "account_id", "account_nm", "thstrm_amount", "thstrm_add_amount",
            "frmtrm_amount", "frmtrm_q_amount", "frmtrm_add_amount",
            "bfefrmtrm_amount", "rcept_no"]


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


def _done_keys(cached: Optional[pd.DataFrame], label: str) -> set:
    """이미 받은 (회사, 연도, 보고서) 조합. ★비교치가 없는 옛 캐시는 '미완'으로 본다.

    ★ 왜 이 구분이 필요한가 ─────────────────────────────────────────────────────────────
      예전 버전은 당기금액만 저장했다. 그 캐시를 '완료'로 처리하면 전기 비교치가 영원히
      비고, YoY 센서가 분기 체인(연속 8분기)에 의존하게 되어 결측률이 25% 를 넘는다.
      → 비교치가 없는 조합은 재수집 대상으로 되돌린다. 단 **기존 행은 지우지 않는다**
        (드라이브 캐시 불훼손 원칙). 재수집분이 keep="last" 로 덮어쓸 뿐이다.
      배치 경로는 재수집 비용이 수백 회에 불과해 이 업그레이드가 몇 분이면 끝난다.
    """
    if cached is None or not len(cached):
        return set()
    c = cached
    key = ["corp_code", "bsns_year", "reprt_code"]
    if any(k not in c.columns for k in key):
        return set()
    if "frmtrm_amount" not in c.columns:
        LOG.warn(f"{label} 캐시 {len(c):,}행에 전기 비교치가 없습니다(구버전 형식). "
                 f"당기금액은 그대로 재사용하고, 비교치는 이번 실행에서 보강합니다.")
        return set()
    ok = c.groupby(key, observed=True)["frmtrm_amount"].transform(
        lambda s: s.notna().any() if len(s) else False)
    good = c[ok.fillna(False).astype(bool)]
    n_old = c.groupby(key, observed=True).ngroups - good.groupby(key, observed=True).ngroups \
        if len(good) else c.groupby(key, observed=True).ngroups
    if n_old > 0:
        LOG.info(f"{label} — 비교치가 없는 {n_old:,}개 조합은 재수집 대상입니다"
                 f"(기존 행은 보존됩니다).")
    return set(zip(good["corp_code"].astype(str), good["bsns_year"].astype(int),
                   good["reprt_code"].astype(str)))


def fetch_dart_multi_accounts(corp_codes: Sequence[str], years: Sequence[int]) -> pd.DataFrame:
    """주요계정 배치 수집. 전체 재무제표의 '바닥'을 싸게 깔아둔다."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.get_table("dart_multi_raw", scope="shared")
    done = _done_keys(cached, "DART 주요계정")
    if cached is not None and len(cached):
        LOG.info(f"공용 캐시에서 DART 주요계정 {len(cached):,}행 재사용 "
                 f"(비교치 확보 {len(done):,} 조합)")

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
    done = _done_keys(cached, "DART 전체 재무제표")
    if cached is not None and len(cached):
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
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세(비용)?차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산$"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권", r"^매출채권및기타"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    # ★ 아래 5개는 '다중회사 주요계정(fnlttMultiAcnt)' 이 주는 전부다. 배치 1회로 100사가
    #   오므로 전 종목·전 분기를 예산 안에서 확보할 수 있는 유일한 계정군이다.
    #   운전자본 발생액(유동자산−유동부채 변화)과 자본잠식 판정이 여기서 나온다.
    "current_assets":  ("BS", [r"ifrs-full_CurrentAssets$", r"^유동자산$"]),
    "noncur_assets":   ("BS", [r"ifrs-full_NoncurrentAssets$", r"^비유동자산$"]),
    "current_liab":    ("BS", [r"ifrs-full_CurrentLiabilities$", r"^유동부채$"]),
    "noncur_liab":     ("BS", [r"ifrs-full_NoncurrentLiabilities$", r"^비유동부채$"]),
    "retained":        ("BS", [r"ifrs-full_RetainedEarnings", r"^이익잉여금", r"^결손금"]),
    "capital_stock":   ("BS", [r"ifrs-full_IssuedCapital$", r"^자본금$"]),
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
                    + [f"{k}{s}" for k in ACCOUNT_PATTERNS for s in ("_cm", "_pv", "_pc")]
                    + [f"{c}{s}" for c in FLOW_ITEMS for s in ("_q", "_ttm")]
                    + ["employees", "payroll", "v2_bad_3q"])


#  값 필드 → 컬럼 접미사.  <항목> = 당기금액 · <항목>_cm = 당기누적 · <항목>_pv = 전기
#  · <항목>_pc = 전기누적.   BS 는 누적 개념이 없으므로 _cm 은 당기말, _pv 는 전기말이다.
_AMT_FIELDS = {"_cur": "thstrm_amount",     "_cum": "thstrm_add_amount",
               "_pv":  "frmtrm_amount",     "_pq":  "frmtrm_q_amount",
               "_pc":  "frmtrm_add_amount"}
_AMT_SUFFIX = {"_cur": "", "_cum": "_cm", "_pv": "_pv", "_pq": "_pq", "_pc": "_pc"}
# 비교치까지 포함한 계약 스키마. 어떤 실행에서도 이 컬럼들은 반드시 존재해야 한다.
COMPARATIVE_SUFFIXES = ["_cm", "_pv", "_pq", "_pc"]


def _detect_cumulative(W: pd.DataFrame) -> Tuple[bool, float, int]:
    """분기보고서의 손익금액이 '누적'인지 '3개월 단독'인지 데이터로 판정한다.

    ★ 추측하지 않는 이유 ────────────────────────────────────────────────────────────────
      DART 응답은 엔드포인트(단건/다중)와 회사에 따라 당기금액이 누적일 수도, 3개월
      단독일 수도 있다. 코드가 한쪽을 가정하면 다른 쪽에서 **에러 없이 값만 틀린다**.
      누적을 3개월로 오인하면 매출이 계단식으로 튀어 성장률이 통째로 가짜가 되고,
      3개월을 누적으로 오인하면 차분이 음수·양수를 오가며 TTM 이 무의미해진다.
    판별식: 사업보고서(연간) 대비 반기보고서 금액의 비율 중앙값.
      · 누적이면 반기 ≈ 연간의 0.5
      · 3개월 단독이면 반기(=2분기 단독) ≈ 연간의 0.25
    """
    try:
        r = W[["corp_code", "bsns_year", "reprt_code", "revenue"]].dropna(subset=["revenue"])
        piv = r.pivot_table(index=["corp_code", "bsns_year"], columns="reprt_code",
                            values="revenue", aggfunc="first")
        h1, fy = REPRT_CODES["H1"], REPRT_CODES["FY"]
        if h1 not in piv.columns or fy not in piv.columns:
            return True, float("nan"), 0
        a, b = piv[h1], piv[fy]
        ratio = (a / b).where((b > 0) & (a > 0))
        ratio = ratio[(ratio > 0.05) & (ratio < 1.5)]
        n = int(ratio.notna().sum())
        if n < 50:
            return True, (float(ratio.median()) if n else float("nan")), n
        med = float(ratio.median())
        return (med > 0.375), med, n
    except Exception:
        return True, float("nan"), 0


def tidy_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp_code, period, 항목) 와이드 테이블. knowledge_date 를 여기서 확정한다.

    ★ 당기금액뿐 아니라 **전기 비교치**까지 함께 실어 나른다. YoY 를 만들려고 분기 체인을
      타지 않아도 되게 하기 위해서다(_FS_KEEP 주석 참조).
    """
    if fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()

    def _num(name: str) -> pd.Series:
        if name not in d.columns:
            return pd.Series(np.nan, index=d.index, dtype="float64")
        s = (d[name].astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("−", "-", regex=False)
                    .str.strip())
        s = s.where(~s.isin(["", "-", "nan", "None", "NaN"]))
        return pd.to_numeric(s, errors="coerce")

    for k, src in _AMT_FIELDS.items():
        d[k] = _num(src)
    # 당기금액이 비어 있고 누적만 있는 행(일부 CF 계정)을 버리지 않는다.
    d["_cur"] = d["_cur"].where(d["_cur"].notna(), d["_cum"])
    d = d.dropna(subset=["_cur"])
    if d.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)

    out_rows = []
    _vals = list(_AMT_FIELDS)
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
        # 같은 항목·같은 연결범위에 여러 계정이 걸리면 절대값이 큰 쪽(=대표 계정)을 취한다.
        hit = (hit.assign(_a=hit["_cur"].abs())
                  .sort_values("_a", ascending=False)
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code", "fs_div"],
                                   keep="first"))
        out_rows.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                              "fs_div", "rcept_no", "item"] + _vals])
    if not out_rows:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    L = pd.concat(out_rows, ignore_index=True)

    # ── ★ 연결범위(연결/별도) 고정 — 보고서 단위로 하나만 쓴다 ──────────────────────────
    #   고정하지 않으면 항목마다 연결범위가 뒤섞인다. 실제로 일어나는 조합이다:
    #     매출액 → 배치(주요계정)의 연결(CFS),  재고자산 → 단건(전체 재무제표)의 별도(OFS)
    #   이러면 매출채권회전일수 = 별도 매출채권 ÷ 연결 매출 이 되어 **의미가 없는 수**가 된다.
    #   지주회사·자회사 비중이 큰 기업일수록 오차가 크고, 그 오차가 해마다 바뀌면
    #   i_sales 가 그 변화를 '성장'으로 읽는다. 에러는 나지 않는다 — 값만 조용히 틀린다.
    #   → (회사, 연도, 보고서)별로 **항목을 가장 많이 채우는 연결범위**를 골라 그것만 쓴다.
    #     동수면 연결(CFS) 우선. 단건이 전체 계정을 준 보고서는 자연히 그쪽이 이긴다.
    _key = ["corp_code", "bsns_year", "reprt_code"]
    L["fs_div"] = L["fs_div"].astype(str)
    _cov = (L.groupby(_key + ["fs_div"], observed=True)["item"].nunique()
             .reset_index(name="_n"))
    _cov["_pref"] = (_cov["fs_div"] != "CFS").astype(int)
    _cov = _cov.sort_values(_key + ["_n", "_pref"], ascending=[True] * 3 + [False, True])
    _win = _cov.drop_duplicates(_key, keep="first")[_key + ["fs_div"]]
    _n0 = len(L)
    L = L.merge(_win, on=_key + ["fs_div"], how="inner")
    if _n0 - len(L) > 0:
        LOG.debug(f"연결범위 고정 — 보고서당 한 기준만 채택해 {_n0-len(L):,}행을 제외했습니다 "
                  f"(연결/별도 혼용 방지).")
    W = L.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                      values=_vals, aggfunc="first")
    W.columns = [f"{item}{_AMT_SUFFIX[val]}" for val, item in W.columns]
    W = W.reset_index()
    # ★ knowledge_date 는 '실제로 채택된 금액이 공시된 시점' 이상이어야 한다.
    #   first()(=가장 이른 접수번호)를 쓰면, 정정공시로 바뀐 금액을 채택해 놓고 날짜만
    #   원공시 날짜를 붙이게 된다 → 그 차이만큼 미래를 미리 아는 셈이다(C1 위반).
    #   max() 는 채택 후보 중 가장 늦은 접수일이므로 어떤 경우에도 누수가 없다(보수적).
    rc = (L.groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"]
           .max().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")

    W["period_end"] = [as_ts(f"{y}-{REPRT_PERIOD_END[r][0]:02d}-{REPRT_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_knowledge_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]

    order = {REPRT_CODES["Q1"]: 1, REPRT_CODES["H1"]: 2, REPRT_CODES["Q3"]: 3, REPRT_CODES["FY"]: 4}
    W["q"] = W["reprt_code"].map(order)
    W = W.sort_values(["corp_code", "bsns_year", "q"], kind="stable").reset_index(drop=True)

    # ★ 계약 스키마 — 당기·당기누적·전기·전기누적 네 벌이 항상 존재해야 한다.
    #   pivot 결과에 그 계정이 없으면 컬럼 자체가 안 생겨 실행마다 축이 달라진다.
    for _k in ACCOUNT_PATTERNS:
        for _s in [""] + COMPARATIVE_SUFFIXES:
            if _k + _s not in W.columns:
                W[_k + _s] = np.nan

    # ── 분기 공시금액이 누적인지 3개월 단독인지 '데이터로' 판정 ──────────────────────────
    is_cum, med_ratio, n_ratio = _detect_cumulative(W)
    LOG.table([["분기 손익금액", "누적(YTD)" if is_cum else "3개월 단독",
                (f"{med_ratio:.3f}" if med_ratio == med_ratio else "표본없음"),
                f"{n_ratio:,}건", "반기/연간 ≈0.5 이면 누적, ≈0.25 면 3개월"]],
              ["판정 대상", "결론", "비율 중앙값", "표본", "판별 근거"],
              ["l", "c", "r", "r", "l"],
              title="분기 공시금액 누적여부 자동판정 — 가정하지 않고 실측으로 정한다")
    if n_ratio < 50:
        LOG.info("표본이 적어 기본값(누적)을 씁니다. 사업보고서·분기보고서가 함께 쌓이면 "
                 "다음 실행에서 실측으로 재판정합니다.")

    gk = ["corp_code", "bsns_year"]
    # 연내 누적합을 인정하는 조건: q 가 1..k 로 빠짐없이 이어지고, 값도 전부 존재할 것.
    seq_ok = (W.groupby(gk, observed=True).cumcount() + 1) == W["q"]
    # 전기금액을 '전기 누적'으로 대체해도 되는 행 (스칼라 bool 을 where 에 넘기면
    # "Array conditional must be same shape as self" 로 죽는다 — 계약검정이 잡아냈다)
    _pv_usable = (pd.Series(True, index=W.index) if is_cum else (W["q"] >= 4))
    for c in FLOW_ITEMS:
        cm, pc, pv = f"{c}_cm", f"{c}_pc", f"{c}_pv"
        cur = W[c]
        if is_cum:
            cum = cur
        else:
            # 3개월 단독 → 연내 누적합. 단 사업보고서(q=4)는 언제나 '연간' 이므로 그대로 쓴다.
            run = W.groupby(gk, observed=True)[c].cumsum()
            nn = W[c].notna().groupby([W["corp_code"], W["bsns_year"]], observed=True).cumsum()
            ok = seq_ok & (nn == W["q"])
            cum = pd.Series(np.where(W["q"] >= 4, cur, run.where(ok)), index=W.index)
        W[cm] = W[cm].where(W[cm].notna(), cum)
        # 전기 누적: 명시 컬럼(frmtrm_add_amount) 우선.
        # ★ 없을 때 전기금액으로 대체할 수 있는 조건이 두 가지다:
        #     ① 분기 공시가 누적 형식이면 전기금액도 누적이다.
        #     ② **사업보고서(q=4)는 형식과 무관하게 전기금액이 곧 '전기 연간'이다.**
        #   ②를 빠뜨리면 연 1회만 공시하는 기업(U-MICRO 에 흔하다)의 전기 매출이 통째로
        #   비어 i_sales 가 결측이 된다 — 실제로 합성 스모크에서 i_sales 31.4% 결측으로
        #   C14-c 에 걸렸다. 데이터가 아니라 이 한 줄이 원인이었다.
        W[pc] = W[pc].where(W[pc].notna(), W[pv].where(_pv_usable))
    # 재무상태표 항목은 누적 개념이 없다 — 당기말 잔액이 곧 _cm 이다.
    for _k in ACCOUNT_PATTERNS:
        if _k not in FLOW_ITEMS:
            W[f"{_k}_cm"] = W[f"{_k}_cm"].where(W[f"{_k}_cm"].notna(), W[_k])
            W[f"{_k}_pc"] = W[f"{_k}_pc"].where(W[f"{_k}_pc"].notna(), W[f"{_k}_pv"])

    # ── 누적 → 분기 단독 → TTM ────────────────────────────────────────────────────────
    #   직전 분기가 실제로 존재할 때만 차분한다.
    #   (누락된 분기를 0으로 간주하면 반기 누적치가 한 분기 실적으로 둔갑한다 — fail-open 금지)
    W["_q_prev"] = W.groupby(gk, observed=True)["q"].shift(1)
    contiguous = (W["q"] - W["_q_prev"]) == 1
    for c in FLOW_ITEMS:
        cm = f"{c}_cm"
        prev = W.groupby(gk, observed=True)[cm].shift(1)
        W[c + "_q"] = np.where(W["q"] == 1, W[cm],
                               np.where(contiguous, W[cm] - prev, np.nan))
        # TTM = 4분기 이동합. min_periods=4 — 3개만으로 TTM 이라 부르면 15~25% 과소계상된다.
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum()))
    W = W.drop(columns=["_q_prev"])
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
_HK_IDX_RE = re.compile(r"report_idx=\d+")


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
    # ★★ 실측된 '0건' 사고의 원인이 바로 이 줄이었다 ★★
    #   예전 구현은 `"데이터가 없습니다" in html` 로 **문서 전체**를 훑었다. 그 문구는
    #   빈 결과 템플릿·인접 탭 마크업·인라인 스크립트 어디에나 들어 있을 수 있고, 그러면
    #   실제 행이 몇 개든 상관없이 매 페이지가 빈 목록을 돌려준다. 결정적이라서 11년 ×
    #   2스킨이 전부 0건이 되고, HTTP 오류가 없으니 로그에는 초록색 ✔ 만 남는다.
    #   → 빈 상태 판정은 '표 안에 실제 행이 있는가'로만 한다. 문서 전체 문자열 검색 금지.
    if table.select_one("td.no_data") is not None and table.find("a", href=_HK_IDX_RE) is None:
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
                     page_size: int = 80, max_pages: int = 200) -> pd.DataFrame:
    """분기 단위로 쪼개서 수집.

    ★ 연 단위(1년 = 365일)로 요청하면 서버가 조회기간 상한에 걸려 **HTTP 200 에 빈 표**를
      돌려준다. 현재 동작이 확인된 호출은 전부 수 일~3개월 범위다. 분기로 쪼개면 요청 수는
      4배지만 한 요청의 페이지 수가 줄어 총 페이지 수는 오히려 비슷하다.
    """
    rows: List[dict] = []
    jobs = []
    _q = pd.period_range(as_ts(start), as_ts(end), freq="Q")
    for skin in skins:
        for p in _q:
            sd = max(pd.Timestamp(p.start_time), as_ts(start))
            ed = min(pd.Timestamp(p.end_time).normalize(), as_ts(end))
            if sd <= ed:
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
                # ★ report_type 은 구 컨트롤러(/apps.analysis/analysis.list)의 인자다.
                #   현재 경로(skinType)와 함께 보내면 서버가 조건을 겹쳐 해석해 빈 표를
                #   돌려줄 수 있다. 동작이 확인된 호출은 전부 skinType 단독이다.
                "search_text": "", "search_value": "", "business_code": "",
            }
            html = http_get(HK_LIST, source="hankyung", params=params, tries=3,
                            referer=HK_BASE + "/", timeout=30)
            if not html:
                break
            batch = _hk_parse(html, skin)
            # ★ 첫 페이지가 비었다고 즉시 끊지 않는다. 아래 empty_streak(2회 연속) 규칙과
            #   같은 이유다 — 일시적 빈 응답 하나로 그 분기 전체가 조용히 사라지면
            #   전 구간이 0건이 되어도 아무 신호가 남지 않는다.
            if not batch:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                continue
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


def naver_enrich_detail(df: pd.DataFrame, limit: int = 20000,
                        budget_s: Optional[float] = None,
                        prio_codes: Optional[set] = None) -> pd.DataFrame:
    """네이버는 목표주가/투자의견이 상세페이지에만 있다. 목표주가 없는 종목분석 건만 보강한다.

    ★ 이 단계가 실측 126분(7,555초)을 먹은 최대 병목이었다 ─────────────────────────────
      원인은 동시성이 아니라 **산수**다. 네이버 레이트리밋 3 QPS 는 소스 단위 공유 버킷이라
      워커를 8개로 늘려도 전부 같은 버킷에서 대기한다. 20,000건 ÷ 3 = 6,667초 —
      워커 수와 무관하게 정해지는 값이다. 줄일 수 있는 건 **요청 수 자체**뿐이다.
        ① 한경을 먼저 병합해 목표주가가 이미 채워진 건은 대상에서 빠진다(호출자 책임).
        ② 남은 예산(초)으로 상한을 계산해 그 안에서만 돈다 — 예산을 넘길 걸 알면서
           시작하지 않는다(§10).
        ③ U-MICRO 후보 종목의 리포트를 먼저 받는다. 이 전략이 실제로 쓰는 건 그쪽뿐이다.
      받지 못한 건은 다음 실행이 이어받는다(보강 결과가 공용 인덱스에 저장되므로
      이미 채운 건은 두 번 조회하지 않는다).
    """
    if df.empty:
        return df
    need = df[(df["source"] == "naver") & (df["category"] == "company") &
              (df["target_price"].isna()) & (df["detail_url"].notna())].copy()
    if need.empty:
        return df
    n_all = len(need)
    if budget_s is not None:
        qps = float(RATE_LIMIT_QPS.get("naver", 3.0))
        limit = min(limit, max(0, int(qps * max(0.0, float(budget_s)) * 0.85)))
    if limit <= 0:
        LOG.warn(f"네이버 상세 보강에 배정할 남은 시간이 없습니다 — 대상 {n_all:,}건을 "
                 f"통째로 건너뜁니다. 목표주가는 결측으로 남고 다음 실행이 이어받습니다.")
        return df
    # 우선순위: ① U-MICRO 후보 종목  ② 최신순
    need["_p"] = (0 if not prio_codes
                  else (~need["stock_code"].astype(str).isin(prio_codes)).astype(int))
    need = need.sort_values(["_p", "pub_date"], ascending=[True, False])
    if n_all > limit:
        _in_band = int((need["_p"].iloc[:limit] == 0).sum()) if len(need) else 0
        LOG.warn(f"네이버 상세 보강 대상 {n_all:,}건 중 {limit:,}건만 조회합니다 "
                 f"(남은 예산 {0 if budget_s is None else budget_s/60:.0f}분 · "
                 f"{RATE_LIMIT_QPS.get('naver', 3.0):.1f} QPS 기준). "
                 f"그중 U-MICRO 후보 종목분 {_in_band:,}건을 우선했습니다. "
                 f"나머지는 다음 실행이 이어받습니다(이번에 채운 건은 공용 인덱스에 남습니다).")
        need = need.head(limit)

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
        # ★ report_uid 는 build_report_master 에서 만들어진다. 이 시점(수집 직후)에는
        #   아직 없을 수 있으므로 존재하는 키로만 중복을 제거한다.
        #   (없는 컬럼으로 drop_duplicates 하면 KeyError 로 수집 전체가 죽는다)
        _dk = next((k for k in ("report_uid", "detail_url", "title") if k in df.columns), None)
        df = df.drop_duplicates(_dk, keep="first") if _dk else df.drop_duplicates()
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
# 두 소스가 같은 보고서에 서로 다른 목표주가를 줄 때의 병합 규칙. 전략층에서 덮어쓸 수 있다.
TARGET_PRICE_AGG = "max"

BROKER_CANON: List[Tuple[str, str]] = [
    # ★ 순서 주의: '미래에셋생명'(보험사)이 앞 규칙에 먼저 걸리면 증권사로 둔갑해
    #   애널리스트 소속이 틀어지고 동일인 판정이 깨진다. 비증권 계열을 먼저 걸러낸다.
    (r"미래에셋생명", "기타"),
    (r"미래에셋(대우|증권)?", "미래에셋증권"),               # 미래에셋대우→미래에셋증권(2021)
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
        # 목표주가 병합 방식(TARGET_PRICE_AGG). 둘 다 NaN 을 건너뛰므로 "한쪽에만 값이 있는"
        # 경우의 동작은 같다. 차이는 두 소스가 서로 다른 값을 줄 때다:
        #   "max"    — 정보를 잃지 않는다는 관점(v2 기본). 단 소스 불일치 시 낙관 편향.
        #   "median" — 불일치를 중앙값으로 흡수해 리비전 지표의 편향을 없앤다(v3 선택).
        "target_price": ("target_price", TARGET_PRICE_AGG),
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
# ║  L1-M  시가총액 · 상장주식수  (U-MICRO 유니버스의 정의 입력 · PBR/PER 의 분모)             ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 없으면 이 전략은 성립하지 않는다.                                            ║
# ║    U-MICRO 는 "시총 랭크 1400위 밖"으로 정의되고, 방화벽의 딥밸류 조항은 PBR·PER 을        ║
# ║    쓴다. 둘 다 '그 시점의' 시가총액을 요구한다.                                            ║
# ║                                                                                          ║
# ║  ★ C13 (유니버스는 PIT) 을 지키는 유일한 방법 ─────────────────────────────────────────  ║
# ║    현재 시총을 과거에 그대로 적용하면 "지금 소형주인 기업"만 과거 유니버스가 되어          ║
# ║    소형→중형 전환에 성공한 종목이 정의상 사라진다. 그게 바로 이 전략이 찾는 대상이므로     ║
# ║    성공 사례만 골라 지우는 꼴이 된다.                                                     ║
# ║    → 시총은 '스냅샷 상장주식수(as-of)' × '그날 종가' 로 매 시점 재구성한다.                 ║
# ║      상장주식수는 느리게 변하므로 as-of 캐리가 타당하고, 종가는 일별로 정확하다.           ║
# ║                                                                                          ║
# ║  소스 우선순위 (앞에서 실패하면 다음으로, 무엇이 쓰였는지 전부 표로 출력)                   ║
# ║    ① 드라이브 공용 캐시 (다른 전략이 모아둔 것도 그대로 재사용)                             ║
# ║    ② pykrx 시가총액 스냅샷      — KRXG 게이트로 직렬화 (CD011 방지)                        ║
# ║    ③ KRX 마켓플레이스 bld 조회  — 로그인 세션이 있을 때                                    ║
# ║    ④ DART 주식총수 현황         — 접수일자 기준이라 PIT 로 정확. 잔여 종목만 한도 내에서    ║
# ║    ⑤ FDR 현재 상장주식수        — ★비PIT. 최후수단이며 감사표에 '근사'로 명시한다          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

MCAP_SNAP_COLS = ["snap_date", "code", "shares", "mcap", "src"]

# KRX 마켓플레이스 '전종목 시세' bld — 시가총액·상장주식수를 한 번에 준다.
KRX_BLD_ALLPRICE = "dbms/MDC/STAT/standard/MDCSTAT01501"

# ── ★ KRX Open API (data-dbg.krx.co.kr) — 이 모듈의 1순위 ───────────────────────────────────
#   · data.krx.co.kr(마켓플레이스)와 **호스트가 다르다**. 마켓플레이스가 차단돼 있어도 별개다.
#   · 요청 1건 = 그 날짜의 전 종목. 120개월 × 2시장 = 240회면 10년 PIT 시총 패널이 끝난다.
#     (종목별 루프였다면 3,000종목 × 120개월 = 36만 회다 — 비교가 안 된다)
#   · 2010-01-04 부터 제공되므로 2016-08 시작 구간을 전부 덮는다.
#   · 인증: HTTP 헤더 AUTH_KEY. 무료 가입 후 발급.
KRX_OPENAPI_BASE = "https://data-dbg.krx.co.kr/svc/apis/sto/"
KRX_OPENAPI_EPS = [("stk_bydd_trd", "KOSPI"), ("ksq_bydd_trd", "KOSDAQ"),
                   ("knx_bydd_trd", "KONEX")]

# ── 공공데이터포털 금융위원회 주식시세정보 — KRX Open API 가 없을 때의 동급 대체 ────────────
#   basDt 하루치 전 종목을 mrktTotAmt(시가총액)·lstgStCnt(상장주식수)와 함께 준다.
DATAGO_STOCK_URL = ("https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/"
                    "getStockPriceInfo")

# ── FinanceDataReader 정적 캐시 (GitHub raw) ────────────────────────────────────────────────
#   ★ fdr.StockListing('KRX') 는 내부적으로 data.krx.co.kr 에 '최신 영업일'을 물어본 뒤
#     GitHub 캐시 CSV 를 읽는다. 그 첫 호출이 차단되면 json.loads 가 깨지고 bare except 가
#     삼켜 ValueError("Failed to load data from ...") 로 둔갑한다 — 실측된 실패 원인이다.
#     날짜 문자열 하나 때문에 전체가 죽는 구조이므로, 날짜를 우리가 정해 CSV 를 직접 읽는다.
FDR_CACHE_RAW = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                 "refs/heads/master/data/listing/{kind}/{date}.csv")


def fdr_cache_csv(kind: str, back_days: int = 12) -> Optional[pd.DataFrame]:
    """FDR 정적 캐시 CSV 를 KRX 를 거치지 않고 직접 읽는다. kind: krx | delisting | desc."""
    today = pd.Timestamp.today().normalize()
    for i in range(back_days):
        d = (today - pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        url = FDR_CACHE_RAW.format(kind=kind, date=d)
        try:
            txt = http_get(url, source="generic", tries=1, timeout=40)
            if not txt or len(txt) < 512 or "," not in txt[:400]:
                continue
            df = pd.read_csv(io.StringIO(txt), dtype=str)
            if len(df) > 50:
                LOG.debug(f"FDR 정적 캐시 {kind} — {d} 기준 {len(df):,}행 (KRX 미경유)")
                return df
        except Exception:
            continue
    return None


def _krx_openapi_day(day: pd.Timestamp) -> List[dict]:
    """하루치 전 종목 시세(시총·상장주식수). 휴장일이면 최대 5일 뒤로 물러선다."""
    if not KRX_OPENAPI_KEY:
        return []
    hdr = {"AUTH_KEY": KRX_OPENAPI_KEY}
    for back in range(6):
        bd = (day - pd.Timedelta(days=back)).strftime("%Y%m%d")
        rows, got = [], 0
        for ep, mkt in KRX_OPENAPI_EPS:
            js = http_json(KRX_OPENAPI_BASE + ep, source="krxapi", headers=hdr,
                           params={"basDd": bd}, tries=2, timeout=45,
                           referer="https://openapi.krx.co.kr/")
            blk = (js or {}).get("OutBlock_1") or []
            if not blk:
                continue
            got += 1
            for r in blk:
                c = to_code6(r.get("ISU_SRT_CD") or r.get("ISU_CD"))
                if not c:
                    continue
                rows.append({"snap_date": day.strftime("%Y-%m-%d"), "code": c,
                             "shares": _num(r.get("LIST_SHRS")),
                             "mcap": _num(r.get("MKTCAP")), "src": "krx_api"})
        # ★ 코스피·코스닥 두 시장이 모두 와야 인정한다. 한쪽만 저장하면 그 시점의 시총 랭크가
        #   한 시장만으로 매겨져 U-MICRO(하위권) 판정이 통째로 뒤집힌다.
        if got >= 2 and rows:
            return rows
    return []


def _mcap_from_krx_openapi(days: Sequence[pd.Timestamp]) -> List[dict]:
    if not KRX_OPENAPI_KEY or not days:
        return []
    out: List[dict] = []
    miss = 0
    for d in tqdm(days, desc="시총 스냅샷(KRX OpenAPI)", ncols=88, leave=False):
        if DEADLINE is not None and DEADLINE.over():
            LOG.warn("런타임 예산 초과로 시총 스냅샷 수집을 중단합니다 — 받은 분량은 저장됩니다.")
            break
        r = _krx_openapi_day(d)
        if r:
            out.extend(r)
            miss = 0
        else:
            miss += 1
            if miss >= 4:
                LOG.warn("KRX Open API 가 연속 4회 비었습니다 — 인증키 미승인/한도 소진일 수 "
                         "있습니다. 다음 소스로 폴백합니다(정상 동작).")
                break
    return out


def _mcap_from_datagokr(days: Sequence[pd.Timestamp]) -> List[dict]:
    """공공데이터포털 주식시세정보. 하루치 전 종목을 한 번에(numOfRows 대량) 받는다."""
    if not DATA_GO_KR_KEY or not days:
        return []
    out: List[dict] = []
    miss = 0
    for d in tqdm(days, desc="시총 스냅샷(data.go.kr)", ncols=88, leave=False):
        if DEADLINE is not None and DEADLINE.over():
            break
        rows = []
        for back in range(6):
            bd = (d - pd.Timedelta(days=back)).strftime("%Y%m%d")
            js = http_json(DATAGO_STOCK_URL, source="datagokr", tries=2, timeout=45,
                           params={"serviceKey": DATA_GO_KR_KEY, "numOfRows": 6000,
                                   "pageNo": 1, "resultType": "json", "basDt": bd})
            items = (((js or {}).get("response") or {}).get("body") or {}).get("items") or {}
            lst = items.get("item") if isinstance(items, dict) else None
            if not lst:
                continue
            for r in (lst if isinstance(lst, list) else [lst]):
                c = to_code6(r.get("srtnCd"))
                if not c:
                    continue
                rows.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                             "shares": _num(r.get("lstgStCnt")),
                             "mcap": _num(r.get("mrktTotAmt")), "src": "datagokr"})
            break
        if rows:
            out.extend(rows)
            miss = 0
        else:
            miss += 1
            if miss >= 4:
                LOG.warn("공공데이터포털 주식시세정보가 연속 4회 비었습니다 — "
                         "키 승인 상태 또는 제공 시작일을 확인하세요. 폴백합니다.")
                break
    return out


def _mcap_from_pykrx(days: Sequence[pd.Timestamp]) -> List[dict]:
    """pykrx 시가총액 스냅샷. 전부 KRXG 게이트를 통과시켜 직렬화한다."""
    if pykrx_stock is None or not days:
        return []
    rows: List[dict] = []
    bad_streak = 0
    for d in tqdm(days, desc="시총 스냅샷(pykrx)", ncols=88, leave=False):
        bd = KRXG.call(pykrx_stock.get_nearest_business_day_in_a_week,
                       d.strftime("%Y%m%d"), prev=True) or d.strftime("%Y%m%d")
        got_mkt, day_rows = set(), []
        for mkt in ("KOSPI", "KOSDAQ"):
            t = KRXG.call(pykrx_stock.get_market_cap_by_ticker, bd, market=mkt)
            if t is None or len(t) == 0:
                continue
            t = t.reset_index()
            ren = {"티커": "code", "시가총액": "mcap", "상장주식수": "shares"}
            t = t.rename(columns={k: v for k, v in ren.items() if k in t.columns})
            if "code" not in t.columns:
                t = t.rename(columns={t.columns[0]: "code"})
            if "mcap" not in t.columns and "shares" not in t.columns:
                continue
            got_mkt.add(mkt)
            for r in t.itertuples(index=False):
                c = to_code6(getattr(r, "code", None))
                if not c:
                    continue
                day_rows.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                                 "shares": float(getattr(r, "shares", np.nan) or np.nan),
                                 "mcap": float(getattr(r, "mcap", np.nan) or np.nan),
                                 "src": "pykrx"})
        # ★ 한쪽 시장만 응답한 날은 통째로 버린다(캐시에도 넣지 않는다).
        #   코스피만 받힌 스냅샷을 저장하면 그 시점의 시총 랭크가 코스피 종목만으로
        #   매겨져 U-MICRO(하위권) 판정이 완전히 뒤집힌다. 게다가 그 날짜가 캐시에
        #   '완료'로 남아 다시는 재수집되지 않는다.
        if {"KOSPI", "KOSDAQ"} <= got_mkt:
            rows.extend(day_rows)
            bad_streak = 0
        else:
            if got_mkt:
                LOG.debug(f"{d:%Y-%m-%d} 시총 스냅샷은 {sorted(got_mkt)} 만 응답 — "
                          f"부분 스냅샷이므로 저장하지 않고 다음 실행에서 재시도합니다.")
            bad_streak += 1
        if bad_streak >= 5:
            LOG.warn("시총 스냅샷이 연속 5회 비었습니다 — KRX 세션이 끊겼거나 차단된 상태입니다. "
                     "다음 소스로 폴백합니다(정상 동작).")
            break
    return rows


def _mcap_from_krx_marketplace(days: Sequence[pd.Timestamp]) -> List[dict]:
    """KRX 마켓플레이스 bld 조회. 세션이 없으면 json_data 가 None 을 돌려주므로 조용히 빈 목록."""
    if not getattr(KRX, "session_ok", False) or not days:
        return []
    rows: List[dict] = []
    bad_streak = 0
    for d in tqdm(days, desc="시총 스냅샷(KRX)", ncols=88, leave=False):
        js = KRX.json_data(KRX_BLD_ALLPRICE, mktId="ALL", trdDd=d.strftime("%Y%m%d"))
        blk = (js or {}).get("OutBlock_1") or (js or {}).get("output") or []
        if not blk:
            bad_streak += 1
            if bad_streak >= 5:
                LOG.warn("KRX 마켓플레이스 시총 조회가 연속 5회 비었습니다 — 중단하고 폴백합니다.")
                break
            continue
        bad_streak = 0
        for r in blk:
            c = to_code6(r.get("ISU_SRT_CD"))
            if not c:
                continue
            rows.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                         "shares": _num(r.get("LIST_SHRS")), "mcap": _num(r.get("MKTCAP")),
                         "src": "krx_mp"})
    return rows


def _num(x) -> float:
    """'1,234,567' · '-' · None 을 안전하게 float 로. 콤마를 안 지우면 전부 NaN 이 된다."""
    try:
        s = str(x).replace(",", "").replace(" ", "")
        if s in ("", "-", "None", "nan"):
            return float("nan")
        return float(s)
    except Exception:
        return float("nan")


def _shares_from_dart(corp_codes: Sequence[str], years: Sequence[int],
                      cap_calls: int = 4000) -> pd.DataFrame:
    """DART 주식총수 현황(stockTotqySttus). 접수일자가 knowledge_date 라 PIT 로 정확하다.

    잔여 종목(스냅샷에 한 번도 안 잡힌 코드)에만 쓴다. 전 종목×전 분기로 돌리면
    일일 호출한도(20,000)를 그대로 태우므로 연 1회(사업보고서)로 제한한다.
    """
    if not DART_API_KEY or not len(corp_codes):
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "shares_dart"])
    jobs = [(cc, y) for cc in corp_codes for y in years][:cap_calls]
    if not jobs:
        return pd.DataFrame(columns=["corp_code", "knowledge_date", "shares_dart"])
    LOG.info(f"DART 주식총수 현황 {len(jobs):,}건 조회 (스냅샷 미확보 종목 보강 · 연 1회 기준)")

    def _one(job):
        cc, y = job
        js = dart_api("stockTotqySttus", {"corp_code": cc, "bsns_year": str(y),
                                          "reprt_code": REPRT_CODES["FY"]})
        if not js or js.get("status") != "000":
            return None
        out = []
        for r in js.get("list", []) or []:
            # se(구분)가 '합계'인 행이 발행주식총수. 보통주/우선주 행을 더하면 이중계상된다.
            se = str(r.get("se", ""))
            if "합계" not in se:
                continue
            q = _num(r.get("istc_totqy"))
            tr = _num(r.get("tesstk_co"))          # 자기주식 수 (있으면 차감이 더 정확)
            if not np.isfinite(q) or q <= 0:
                continue
            rc = str(r.get("rcept_no") or "")
            kd = as_ts(rc[:8]) if len(rc) >= 8 else None
            if kd is None:
                continue
            out.append({"corp_code": cc, "knowledge_date": kd,
                        "shares_dart": q - (tr if np.isfinite(tr) else 0.0)})
        return out or None

    res = pmap_io(_one, jobs, workers=min(N_WORKERS_IO, 8), desc="DART 주식총수")
    rows = [x for sub in res if sub for x in sub]
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["corp_code", "knowledge_date", "shares_dart"])


def _shares_from_fdr() -> pd.DataFrame:
    """FDR 상장목록의 현재 상장주식수/시총. ★현재 시점 값이므로 PIT 가 아니다.
    최후수단이며, 쓰였다는 사실을 감사표에 반드시 남긴다."""
    # ① KRX 를 거치지 않는 정적 캐시 먼저. ② 실패 시에만 fdr.StockListing (KRX 를 건드린다)
    d = fdr_cache_csv("krx")
    if (d is None or len(d) == 0) and fdr is not None and not krx_blocked():
        try:
            d = fdr.StockListing("KRX")
        except Exception as e:                                         # noqa
            LOG.debug(f"FDR StockListing 실패: {type(e).__name__} "
                      f"(내부 KRX 조회 실패가 ValueError 로 둔갑하는 알려진 경로)")
            d = None
    if d is None or len(d) == 0:
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    lm = {str(c).lower(): c for c in d.columns}
    ccol = lm.get("code") or lm.get("symbol")
    scol = lm.get("stocks") or lm.get("shares")
    mcol = lm.get("marcap") or lm.get("markatcap") or lm.get("marketcap")
    if not ccol:
        return pd.DataFrame(columns=["code", "shares_now", "mcap_now"])
    out = pd.DataFrame({"code": d[ccol].map(to_code6)})
    out["shares_now"] = pd.to_numeric(d[scol], errors="coerce") if scol else np.nan
    out["mcap_now"] = pd.to_numeric(d[mcol], errors="coerce") if mcol else np.nan
    return out.dropna(subset=["code"]).drop_duplicates("code")


def fetch_mcap_snapshots(months: pd.DatetimeIndex, sec: Optional[pd.DataFrame] = None
                         ) -> pd.DataFrame:
    """월/분기 격자의 (code, shares, mcap) 스냅샷. 캐시 우선 · 다중소스 폴백.

    반환: snap_date, code, shares, mcap, src   (전 소스 통합, 중복 제거)
    """
    cached = VAULT.get_table("krx_mcap_snapshots", scope="shared")
    have: set = set()
    frames: List[pd.DataFrame] = []
    if cached is not None and len(cached):
        c = cached.copy()
        c["snap_date"] = as_ts_series(c["snap_date"])
        c = c.dropna(subset=["snap_date", "code"])
        for col_ in ("shares", "mcap"):
            if col_ not in c.columns:
                c[col_] = np.nan
        if "src" not in c.columns:
            c["src"] = "cache"
        have = set(c["snap_date"].dt.strftime("%Y-%m-%d"))
        frames.append(c[MCAP_SNAP_COLS])
        LOG.ok(f"공용 캐시에서 시총 스냅샷 {len(have)}개 시점 · {len(c):,}행 재사용 "
               f"(다른 전략이 모아둔 것도 그대로 씁니다)")

    # ★ 벌크 소스(요청 1건 = 그 날짜 전 종목)가 있으면 격자를 '월'로 올린다.
    #   월 격자면 스냅샷 시점과 리밸런싱 시점이 정확히 일치해 시총을 가격으로 환산할 필요가
    #   없어진다(아래 build_mcap_panel 의 액면분할 주의 참조). 240회면 끝나므로 부담도 없다.
    _bulk = bool(KRX_OPENAPI_KEY) or bool(DATA_GO_KR_KEY)
    grid = list(months) if _bulk else _snapshot_grid(months)
    todo = [d for d in grid if d.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 미확보 {len(todo)}개 시점은 신규 수집하지 않습니다.")
        todo = []

    new_rows: List[dict] = []
    if todo:
        LOG.info(f"시총 스냅샷 미확보 {len(todo)}개 시점 — 수집 사다리: "
                 f"KRX OpenAPI{'✔' if KRX_OPENAPI_KEY else '✘(키없음)'} → "
                 f"공공데이터포털{'✔' if DATA_GO_KR_KEY else '✘(키없음)'} → "
                 f"pykrx{'✘(차단중)' if krx_blocked() else '✔'} → KRX 마켓플레이스")
        # ① KRX Open API — 호스트가 달라 마켓플레이스 차단과 무관하다
        new_rows += _mcap_from_krx_openapi(todo)
        done = {r["snap_date"] for r in new_rows}
        rest = [d for d in todo if d.strftime("%Y-%m-%d") not in done]
        # ② 공공데이터포털
        if rest:
            new_rows += _mcap_from_datagokr(rest)
            done = {r["snap_date"] for r in new_rows}
            rest = [d for d in todo if d.strftime("%Y-%m-%d") not in done]
        # ③ pykrx — ★차단 중이면 시도조차 하지 않는다. pykrx 는 내부에서 직접 requests 를
        #    쓰므로 http_get 의 차단 가드를 우회한다. 여기서 막지 않으면 차단이 연장된다.
        if rest and not krx_blocked():
            KRXG.warmup()
            new_rows += _mcap_from_pykrx(rest)
            done = {r["snap_date"] for r in new_rows}
            rest = [d for d in todo if d.strftime("%Y-%m-%d") not in done]
        elif rest:
            LOG.warn(f"KRX 차단 표식이 살아 있어 pykrx 시총 스냅샷을 건너뜁니다 "
                     f"(미확보 {len(rest)}개 시점). 차단 연장을 막기 위한 의도된 동작입니다.")
        # ④ KRX 마켓플레이스 (로그인 세션)
        if rest and not krx_blocked():
            new_rows += _mcap_from_krx_marketplace(rest)

    if new_rows:
        frames.append(pd.DataFrame(new_rows))

    if not frames:
        LOG.warn("시총 스냅샷을 한 건도 확보하지 못했습니다. FDR 현재값으로 근사하며, "
                 "이 경우 유니버스 랭크는 '현재 시총 기준 근사'가 되어 C13 이 부분적으로만 "
                 "충족됩니다. 감사표에 그대로 표시합니다.")
        return pd.DataFrame(columns=MCAP_SNAP_COLS)

    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = as_ts_series(snap["snap_date"])
    snap["code"] = snap["code"].map(to_code6)
    snap = snap.dropna(subset=["snap_date", "code"])
    # shares 가 없고 mcap 만 있는 소스가 섞일 수 있다 — 둘 다 없는 행만 버린다.
    snap = snap[snap["shares"].notna() | snap["mcap"].notna()]
    snap = (snap.sort_values(["snap_date", "code", "src"])
                .drop_duplicates(["snap_date", "code"], keep="first")[MCAP_SNAP_COLS])

    # 부분 응답 방어 — 이웃 시점 대비 급감한 스냅샷은 진실이 아니라 사고다(유니버스 축소 → 선택편향).
    # ★ 기준은 '전체 기간 중앙값'이 아니라 '이웃 시점의 중앙값'이어야 한다.
    #   상장사 수는 10년간 30% 넘게 늘었다. 전체 중앙값으로 자르면 2016년 초기 스냅샷이
    #   후반기 상장 증가 때문에 '부분 응답'으로 오인되어 통째로 폐기된다.
    if len(snap):
        size = snap.groupby("snap_date")["code"].size().sort_index()
        local = size.rolling(5, center=True, min_periods=1).median()
        bad = size[size < local * 0.80]
        if len(bad):
            LOG.warn(f"시총 스냅샷 {len(bad)}개 시점이 이웃 시점 중앙값의 80% 미만이라 "
                     f"부분 응답으로 판단하고 폐기합니다: "
                     f"{[str(pd.Timestamp(x).date()) for x in bad.index[:6]]}")
            snap = snap[~snap["snap_date"].isin(bad.index)]

    if new_rows:
        out = snap.copy()
        out["snap_date"] = out["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.put_table("krx_mcap_snapshots", out, scope="shared", domain="universe",
                        source="pykrx|krx_mp",
                        extra={"note": "시가총액·상장주식수 스냅샷 — 전 전략 공용"})
    PIPE.io("OUT", "DRIVE", "krx_mcap_snapshots", snap, source="pykrx|krx_mp")
    LOG.ok(f"시총 스냅샷 {len(snap):,}행 · {snap['snap_date'].nunique()}개 시점 · "
           f"{snap['code'].nunique():,}종목")
    return snap


def build_mcap_panel(price_m: pd.DataFrame, snap: pd.DataFrame, sec: pd.DataFrame,
                     months: pd.DatetimeIndex) -> pd.DataFrame:
    """월말 (code, month) → shares/mcap/mcap_rank.

    시총 = as-of 상장주식수 × 월말 종가.  스냅샷이 분기라도 월별로 정확히 복원된다.
    ★ merge_asof 단일 패스 (원칙 #1). 종목×시점 루프 금지.
    """
    base = price_m[["code", "month", "close"]].copy()
    base["code"] = base["code"].astype(str)
    # ★ 타입 방어. snap_date/month 가 문자열로 들어오면 merge_asof 는 MergeError 로 죽고,
    #   상위에서 잡아 폴백하면 시총이 통째로 결측이 되어 유니버스가 조용히 비어 버린다.
    #   (실제로 이 경로에서 U-MICRO 0종목 사고가 났다 — 여기서 원천 차단한다)
    base["month"] = as_ts_series(base["month"])
    base = base.dropna(subset=["month"])
    base["_ord"] = np.arange(len(base))
    src_used: Counter = Counter()

    shares = pd.Series(np.nan, index=base.index, dtype="float64")
    mcap_snap = pd.Series(np.nan, index=base.index, dtype="float64")
    close_at_snap = pd.Series(np.nan, index=base.index, dtype="float64")

    # ① 스냅샷 as-of 결합 (backward = 그 시점에 알 수 있었던 마지막 스냅샷)
    #    ★ 스냅샷 '시점의 종가'도 함께 끌고 온다. 이유는 아래 시총 산식 주석 참조.
    if snap is not None and len(snap):
        R = snap.copy()
        R["snap_date"] = as_ts_series(R["snap_date"])
        R["code"] = R["code"].astype(str)
        for _c in ("shares", "mcap"):
            R[_c] = pd.to_numeric(R[_c], errors="coerce") if _c in R.columns else np.nan
        R = R.dropna(subset=["snap_date", "code"])
        R = R.merge(base[["code", "month", "close"]]
                    .rename(columns={"month": "snap_date", "close": "close_snap"}),
                    on=["code", "snap_date"], how="left")
        R = R.sort_values("snap_date", kind="stable")
        L = base.dropna(subset=["month"]).sort_values("month", kind="stable")
        try:
            M = pd.merge_asof(L, R[["snap_date", "code", "shares", "mcap", "close_snap"]],
                              left_on="month", right_on="snap_date", by="code",
                              direction="backward")
            M = M.set_index("_ord")
            for _name, _tgt in (("shares", "shares"), ("mcap", "mcap_snap"),
                                ("close_snap", "close_at_snap")):
                _v = pd.Series(M[_name].reindex(base["_ord"]).to_numpy(), index=base.index)
                if _tgt == "shares":
                    shares = _v
                elif _tgt == "mcap_snap":
                    mcap_snap = _v
                else:
                    close_at_snap = _v
            src_used["스냅샷(PIT)"] = int(pd.notna(shares).sum())
        except Exception as e:                                         # noqa
            LOG.warn(f"시총 스냅샷 as-of 결합 실패({type(e).__name__}) — 폴백으로 진행합니다.")

    # ② DART 주식총수 (PIT) — 스냅샷이 못 채운 종목만
    miss_codes = sorted(set(base.loc[shares.isna(), "code"]))
    if miss_codes and DART_API_KEY and RUN_MODE == "FULL":
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict())
        ccs = [c2c[c] for c in miss_codes if c in c2c][:1200]
        yrs = sorted({int(m.year) for m in months})
        D = _shares_from_dart(ccs, yrs)
        if len(D):
            # ★ c2c 는 code→corp_code 로 1:N 이 접힌 map 이다. 뒤집으면(dict 역전) 한 법인의
            #   종목코드 중 하나만 남아 발행주식총수가 엉뚱한 한 종목에만 붙는다.
            #   → 역전하지 말고 sec 를 통해 merge 로 펼친다(한 법인 → 그 법인의 전 종목).
            _link = (sec.dropna(subset=["corp_code"])[["code", "corp_code"]]
                        .assign(corp_code=lambda x: x["corp_code"].astype(str),
                                code=lambda x: x["code"].astype(str)).drop_duplicates())
            D = D.merge(_link, on="corp_code", how="left")
            D = D.dropna(subset=["code", "knowledge_date"]).sort_values("knowledge_date")
            L2 = base.loc[shares.isna(), ["code", "month", "_ord"]].dropna(subset=["month"])
            L2 = L2.sort_values("month", kind="stable")
            try:
                M2 = pd.merge_asof(L2, D[["knowledge_date", "code", "shares_dart"]],
                                   left_on="month", right_on="knowledge_date", by="code",
                                   direction="backward")
                fill = M2.set_index("_ord")["shares_dart"]
                idx = base.set_index("_ord").index
                add = fill.reindex(idx).to_numpy()
                add = pd.Series(add, index=base.index)
                n_before = int(shares.notna().sum())
                shares = shares.where(shares.notna(), add)
                src_used["DART 주식총수(PIT)"] = int(shares.notna().sum()) - n_before
            except Exception as e:                                     # noqa
                LOG.debug(f"DART 주식총수 결합 실패: {type(e).__name__}")

    # ③ FDR 현재 상장주식수 — ★비PIT 최후수단 (설정으로 끌 수 있다)
    if shares.isna().any() and MCAP_ALLOW_NONPIT_FALLBACK:
        F = _shares_from_fdr()
        if len(F):
            m = base["code"].map(F.set_index("code")["shares_now"].to_dict())
            n_before = int(shares.notna().sum())
            shares = shares.where(shares.notna(), m)
            n_add = int(shares.notna().sum()) - n_before
            if n_add:
                src_used["FDR 현재값(비PIT 근사)"] = n_add
                LOG.warn(f"상장주식수 {n_add:,}행을 '현재 값'으로 채웠습니다 — 이 행들은 PIT 가 "
                         f"아닙니다. 액면분할·무상증자·유상증자를 거친 종목은 과거 시총이 "
                         f"그 배수만큼 과대평가되어 U-MICRO 밴드에서 잘못 빠질 수 있습니다. "
                         f"엄밀한 재현이 필요하면 MCAP_ALLOW_NONPIT_FALLBACK=False 로 두고 "
                         f"시총 미상 행을 거래대금 대리변수로 처리하세요.")

    # ── 시가총액 산식 ────────────────────────────────────────────────────────────────
    #  ★★ 여기서 '상장주식수 × 종가' 를 쓰면 안 된다 (액면분할 함정) ★★
    #    FDR·네이버가 주는 종가는 **수정주가**다(FDR 은 KRX 에 adjStkPrc=2 로 요청한다).
    #    10:1 액면분할이 t 이후에 있었다면
    #        수정종가_t = 실제종가_t / 10 ,  그리고 as-of 상장주식수_t = 현재주식수 / 10
    #    이므로 둘을 곱하면 실제 시총의 **1/100** 이 된다. 에러도 경고도 없이,
    #    액면분할을 한 종목만 시총이 100분의 1로 찍혀 U-MICRO 하위권으로 몰린다.
    #    (분할은 성장한 기업이 하므로, 하필 이 전략이 찾는 대상을 골라서 오염시킨다)
    #
    #  → 벤더가 그날 계산해 준 시가총액(MKTCAP)을 진실로 삼고, 스냅샷 시점과 대상 월의
    #    **수익률**로만 환산한다. 수익률은 수정 여부에 불변이므로 안전하다.
    #        시총_t = 시총_스냅샷 × (수정종가_t / 수정종가_스냅샷)
    #    월 격자 스냅샷(KRX Open API)에서는 스냅샷 시점 = 대상 월이라 비율이 1 —
    #    즉 벤더 시총이 그대로 쓰인다.
    ratio = safe_div(base["close"], close_at_snap.where(close_at_snap > 0))
    mcap = mcap_snap.where(mcap_snap > 0) * ratio
    n_exact = int((ratio.round(6) == 1.0).sum())
    n_scaled = int(mcap.notna().sum()) - n_exact
    if n_exact:
        src_used["벤더 시총(당월 스냅샷)"] = n_exact
    if n_scaled > 0:
        src_used["벤더 시총 × 기간수익률"] = n_scaled

    # 스냅샷 시총이 없을 때만 '상장주식수 × 종가'. 액면분할 위험을 안고 가는 경로이므로
    # 몇 행이 그렇게 계산됐는지 반드시 표에 남긴다.
    fallback = shares * base["close"]
    n_fb = int((mcap.isna() & fallback.notna()).sum())
    mcap = mcap.where(mcap.notna(), fallback)
    if n_fb:
        src_used["상장주식수 × 수정종가(분할위험)"] = n_fb

    out = base[["code", "month"]].copy()
    out["shares"] = shares.to_numpy()
    out["mcap"] = mcap.to_numpy()
    # ★ 랭크는 매 시점 재산출한다(C13-a). 1=최대 시총.
    out["mcap_rank"] = out.groupby("month", observed=True)["mcap"].rank(
        ascending=False, method="first")
    out["mcap_pctl"] = out.groupby("month", observed=True)["mcap"].rank(
        ascending=False, pct=True)

    cov = float(out["mcap"].notna().mean()) if len(out) else 0.0
    rows = [[k, f"{v:,}", f"{100*v/max(len(out),1):.1f}%"] for k, v in src_used.items()]
    rows.append(["결측(시총 미상)", f"{int(out['mcap'].isna().sum()):,}",
                 f"{100*out['mcap'].isna().mean() if len(out) else 0:.1f}%"])
    LOG.table(rows, ["상장주식수 출처", "행수", "비중"], ["l", "r", "r"],
              title="시가총액 구성 출처 (C13 — '비PIT 근사'가 크면 유니버스 정의가 흔들립니다)")
    if src_used.get("FDR 현재값(비PIT 근사)", 0) > 0.30 * max(len(out), 1):
        LOG.warn("시총의 30% 이상이 '현재 상장주식수' 근사로 채워졌습니다. 상장주식수는 느리게 "
                 "변하므로 랭크 왜곡은 제한적이지만, 무상증자·액면분할이 잦았던 종목에서 "
                 "과거 시총이 과대평가될 수 있습니다. KRX ID/PW 를 넣으면 PIT 스냅샷으로 대체됩니다.")
    if cov < 0.50:
        LOG.warn(f"시총 커버리지가 {100*cov:.0f}% 로 낮습니다. U-MICRO 정의가 시총 랭크에 "
                 f"의존하므로, 커버리지가 낮으면 유니버스가 좁아집니다. "
                 f"§6 감쇠 감사표에서 어느 게이트가 깎는지 확인하세요.")
    PIPE.io("OUT", "MEM", "mcap_panel", out)
    return downcast(out)



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-W  관리종목 · 투자주의환기 · 감사의견 · 매매거래정지  (S1_FIREWALL 의 하드 입력)       ║
# ║                                                                                          ║
# ║  ★ PIT 로 만드는 방법 ────────────────────────────────────────────────────────────────  ║
# ║    "지금 관리종목인 목록"(FDR KRX-ADMINISTRATIVE)을 과거에 적용하면 그 자체가 미래누수다. ║
# ║    2019년에 관리종목이었다가 2021년에 해제된 기업을 2016년부터 제외해 버리기 때문이다.    ║
# ║    → 지정/해제 '이벤트'를 모아 계단함수로 복원한다. 이벤트의 knowledge_date 는 공시일.    ║
# ║                                                                                          ║
# ║  소스: OpenDART 공시목록                                                                  ║
# ║        pblntf_ty="I" (거래소공시) → 관리종목 지정/해제 · 투자주의환기 · 매매거래정지      ║
# ║        pblntf_ty="F" (외부감사관련) → 감사보고서 제출 · 감사의견 비적정                    ║
# ║  보강: FDR KRX-ADMINISTRATIVE (현재 시점 목록) — ★비PIT 이므로 '현재 상태' 확인용으로만   ║
# ║        쓰고 과거에 소급 적용하지 않는다. 커버리지 비교용으로 표에만 남긴다.                ║
# ║                                                                                          ║
# ║  ★ K6 규칙: 이 소스를 한 건도 못 얻으면 해당 방화벽 조항을 '비활성'으로 두고 로깅한다.     ║
# ║    데이터가 없는데 전부 '적정'으로 간주해 통과시키는 것도, 전부 배제하는 것도 거짓이다.    ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# ★ 순서가 중요하다. '해제'를 먼저 검사하지 않으면 "관리종목 지정 해제"가 '지정'으로 잡힌다.
MARKET_ACTION_PATTERNS: List[Tuple[str, str]] = [
    ("watch_off",  r"관리종목.*(지정\s*)?해제|관리종목에서\s*해제"),
    ("watch_on",   r"관리종목\s*지정"),
    ("alert_off",  r"투자주의\s*환기종목.*해제"),
    ("alert_on",   r"투자주의\s*환기종목\s*지정"),
    # ★ '정지'류는 해제 공시가 늘 따라오지는 않는다. _step_state 는 마지막 이벤트가
    #   이기므로, 해제가 안 오면 그 종목은 **백테스트가 끝날 때까지 영구 거래정지**로 남는다.
    #   조회공시 답변 요구·정지기간 변경처럼 실제 거래정지가 아닌 제목까지 걸리면
    #   멀쩡한 종목이 통째로 죽는다 → 해제/변경/예고성 제목을 먼저 배제한다.
    ("halt_off",   r"(매매거래\s*정지|거래정지).*(해제|해지)|정지\s*해제"),
    ("halt_on",    r"^(?!.*(해제|해지|변경|예고)).*(매매거래\s*정지|거래\s*정지)"),
    ("audit_bad",  r"감사의견\s*(거절|한정|부적정)|의견거절|비적정\s*감사의견"),
    # ('audit_rpt' 는 제거했다 — 어떤 조항도 소비하지 않는데 전체 이벤트의 대다수(실측
    #  189,165건)를 차지해 메모리와 표를 잠식했다. 감사'의견'은 audit_bad 가 잡는다.)
    ("delist_risk", r"상장폐지\s*사유|상장적격성\s*실질심사"),
]

WATCH_FLAG_COLS = ["is_watchlist", "is_alert", "is_trading_halted", "audit_bad", "delist_risk"]


def fetch_market_actions(start: str, end: str) -> pd.DataFrame:
    """거래소공시(I) · 외부감사관련(F) 공시목록 → 시장조치 이벤트.

    반환: corp_code, rcept_dt(=knowledge_date), report_nm, action
    """
    empty = pd.DataFrame(columns=["corp_code", "rcept_dt", "report_nm", "action"])
    if not DART_API_KEY:
        LOG.warn("DART_API_KEY 가 없어 관리종목·감사의견 이력을 수집할 수 없습니다. "
                 "S1_FIREWALL 의 해당 조항은 K6 규칙에 따라 '비활성'으로 두고 진행합니다.")
        return empty

    cached = VAULT.get_table("krx_market_actions", scope="shared")
    have_months: set = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = as_ts_series(cached["rcept_dt"])
        cached = cached.dropna(subset=["rcept_dt"])
        have_months = set(cached["rcept_dt"].dt.to_period("M").astype(str))
        LOG.ok(f"공용 캐시에서 시장조치 공시 {len(cached):,}행 재사용 "
               f"({len(have_months)}개월분 — 다른 전략과 공유)")

    # ★ '행이 하나라도 있으면 완료'로 보면 반쪽짜리 달이 영구히 굳는다.
    #   완료 여부는 별도 원장에 명시적으로 기록한다(없으면 미완료로 간주 = 재수집).
    done_ledger = VAULT.get_table("krx_market_actions_months", scope="shared")
    done_months = set()
    if done_ledger is not None and len(done_ledger) and "month" in done_ledger.columns:
        done_months = set(done_ledger.loc[
            done_ledger.get("complete", True).astype(bool), "month"].astype(str))
    have_months = have_months & done_months if done_months else set()

    months = pd.period_range(as_ts(start), as_ts(end), freq="M")
    todo = [m for m in months if str(m) not in have_months]
    if RUN_MODE == "CACHED":
        if todo:
            LOG.info(f"CACHED 모드 — 미확보 {len(todo)}개월은 신규 수집하지 않습니다.")
        todo = []

    def _one(m):
        """반환: (rows, complete). complete=False 면 그 달은 '완료'로 기록하지 않는다.

        ★ 페이지 중간 실패를 '데이터 끝'으로 착각하면 안 된다.
          dart_api 는 일일한도 초과·5xx·타임아웃에서 None 을 돌려주는데, 그걸 그대로
          break 하면 12페이지 중 3페이지만 받고 끝난 달이 만들어진다. 그 달은 행이
          있으므로 다음 실행의 have_months 에 '완료'로 잡혀 **영구히 반쪽짜리로 굳는다.**
          그 구간의 관리종목·감사의견 이벤트가 통째로 비고, 방화벽은 조용히 약해진다.
        """
        rows, complete = [], True
        for ty in ("I", "F"):
            page = 1
            while page <= 100:
                js = dart_api("list.json", {
                    "bgn_de": m.start_time.strftime("%Y%m%d"),
                    "end_de": m.end_time.strftime("%Y%m%d"),
                    "pblntf_ty": ty, "page_no": page, "page_count": 100,
                    "last_reprt_at": "N"})
                if js is None:
                    complete = False               # 호출 자체가 실패 → 미완료
                    break
                if not isinstance(js.get("list"), list) or not js["list"]:
                    # status 013(데이터 없음)은 정상적인 끝이다.
                    if str(js.get("status", "")) not in ("000", "013"):
                        complete = False
                    break
                rows.extend(js["list"])
                total = int(js.get("total_page", 1) or 1)
                if page >= total:
                    break
                page += 1
            else:
                complete = False                   # 100페이지 상한에 걸림 = 아직 남았다
        return rows, complete

    new: List[dict] = []
    incomplete: List[str] = []
    if todo:
        LOG.info(f"거래소공시·외부감사 공시목록 {len(todo)}개월 수집")
        res = pmap_io(_one, todo, workers=min(N_WORKERS_IO, 8), desc="시장조치 공시")
        for m, out in zip(todo, res):
            if not out:
                incomplete.append(str(m))
                continue
            rows, complete = out
            if rows:
                new.extend(rows)
            if not complete:
                incomplete.append(str(m))
        if incomplete:
            LOG.warn(f"{len(incomplete)}개월이 페이지 중간에 끊겼습니다({incomplete[:4]}...). "
                     f"받은 행은 저장하되 '완료'로 기록하지 않아 다음 실행에서 다시 받습니다.")

    frames = ([cached] if cached is not None and len(cached) else [])
    if new:
        d = pd.DataFrame(new)
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no",
                            "rcept_dt", "report_nm") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        LOG.warn("시장조치 공시를 한 건도 얻지 못했습니다 — 방화벽의 관리종목·감사의견 조항을 "
                 "비활성화하고 진행합니다(K6).")
        return empty

    D = pd.concat(frames, ignore_index=True)
    if "rcept_no" in D.columns:
        D = D.drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = as_ts_series(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D = D.dropna(subset=["rcept_dt", "corp_code"])

    D["action"] = ""
    for act, pat in MARKET_ACTION_PATTERNS:
        hit = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["action"] == "")
        D.loc[hit, "action"] = act
    D = D[D["action"] != ""].copy()

    if new or incomplete:
        _prev = done_ledger if done_ledger is not None and len(done_ledger) else None
        _rows = [{"month": str(m), "complete": str(m) not in incomplete} for m in todo]
        _led = pd.DataFrame(_rows)
        if _prev is not None:
            _led = pd.concat([_prev, _led], ignore_index=True)
        _led = _led.drop_duplicates("month", keep="last")
        VAULT.put_table("krx_market_actions_months", _led, scope="shared", domain="krx",
                        source="fetch_market_actions:completeness")
    if new:
        VAULT.put_table("krx_market_actions", D, scope="shared", domain="krx",
                        source="opendart list.json (pblntf_ty=I,F)",
                        extra={"note": "관리종목·투자주의환기·거래정지·감사의견 이벤트 — 전 전략 공용"})
    LOG.ok(f"시장조치 이벤트 {len(D):,}건 — " +
           ", ".join(f"{a}={int((D['action'] == a).sum()):,}"
                     for a, _ in MARKET_ACTION_PATTERNS if (D["action"] == a).any()))
    PIPE.io("OUT", "DRIVE", "krx_market_actions", D, source="opendart")
    return D[["corp_code", "rcept_dt", "report_nm", "action"]]


def _step_state(ev: pd.DataFrame, on_act: str, off_act: str, key: str) -> pd.DataFrame:
    """지정/해제 이벤트 → 시점별 상태(계단함수).

    반환: key, knowledge_date, state (0/1) — merge_asof(backward) 로 패널에 실어 나른다.

    ★ 상태는 '가장 최근 이벤트의 종류'다. 누적합(cumsum)이 아니다. ───────────────────
      한때 지정=+1 / 해제=-1 을 cumsum 하고 clip(lower=0) 했었다. 그러면 이렇게 깨진다:
        공시 수집 구간이 2016-08 부터라, 2016-05 에 지정된 종목은 'on' 이 수집되지 않고
        2017-03 의 'off'(-1) 만 잡힌다 → 누적합 -1. 이후 2018-06 에 진짜 '관리종목 지정'
        (+1)이 와도 누적합은 0 → clip → state=0. 즉 그 종목은 **영구히 관리종목이 아닌
        것으로 읽힌다.** 방화벽 조항이 그 종목에 대해 통째로 무력화된다.
      가장 최근 이벤트만 보면 이력 시작 이전 상태를 몰라도 항상 올바르게 복원된다.
    """
    on = ev[ev["action"] == on_act][[key, "rcept_dt"]].assign(state=np.int8(1))
    off = ev[ev["action"] == off_act][[key, "rcept_dt"]].assign(state=np.int8(0))
    E = pd.concat([on, off], ignore_index=True)
    if E.empty:
        return pd.DataFrame(columns=[key, "knowledge_date", "state"])
    E = E.dropna(subset=[key, "rcept_dt"]).sort_values([key, "rcept_dt"], kind="stable")
    # 같은 날 지정과 해제가 같이 오면 '해제'를 뒤로 보내 마지막 값이 되게 한다(보수적).
    E = E.sort_values([key, "rcept_dt", "state"], kind="stable")
    E = E.drop_duplicates([key, "rcept_dt"], keep="first")
    return E.rename(columns={"rcept_dt": "knowledge_date"})[[key, "knowledge_date", "state"]]


def _one_shot_state(ev: pd.DataFrame, act: str, key: str, valid_days: int = 400) -> pd.DataFrame:
    """해제 이벤트가 없는 단발 사건(감사의견 비적정 등)을 유효기간 동안 켜 둔다.

    ★ 만료는 '누적 최댓값'이어야 한다. 사건마다 (on, on+400일) 쌍을 독립적으로 찍으면
      2019-03 과 2020-03 에 각각 비적정이 났을 때 2019 건의 만료행(2020-04)이 2020 건의
      효력을 꺼 버린다 — 더 최근에 더 나쁜 사건이 있는데 상태가 정상으로 읽힌다.
    """
    on = ev[ev["action"] == act][[key, "rcept_dt"]].dropna()
    if on.empty:
        return pd.DataFrame(columns=[key, "knowledge_date", "state"])
    on = on.sort_values([key, "rcept_dt"], kind="stable").copy()
    on["_exp"] = on["rcept_dt"] + pd.Timedelta(days=valid_days)
    # ★★ 만료행을 '마지막 만료 하나'로 접으면 **미래가 과거를 바꾼다** ★★
    #   예전 구현은 종목별 cummax 후 max() 하나만 off 행으로 남겼다. 그러면
    #     2017-03 비적정 + 2024-03 비적정  →  2017-03 부터 2025-03 까지 97개월 내내 on
    #   이 된다. 2019년 시점의 패널이 "감사의견 비적정"이라고 말하는 근거가 **5년 뒤에야
    #   존재할 공시**다. merge_asof(backward) 는 이 거짓 상태를 그대로 실어 나른다.
    #   방향도 나쁘다 — 나중에 문제가 될 기업을 미리 배제하므로 성과가 부풀려진다.
    #   → 각 사건의 만료를 그대로 두되, 뒤 사건이 덮는 만료만 버린다.
    #     (다음 on 이 이 만료보다 이르면 그 만료행은 무의미하므로 제거)
    _nxt_on = on.groupby(key, observed=True)["rcept_dt"].shift(-1)
    keep_off = _nxt_on.isna() | (_nxt_on > on["_exp"])
    offs = on.loc[keep_off, [key, "_exp"]].rename(columns={"_exp": "knowledge_date"})
    rows = [on.assign(knowledge_date=on["rcept_dt"], state=np.int8(1))[[key, "knowledge_date", "state"]],
            offs.assign(state=np.int8(0))]
    E = pd.concat(rows, ignore_index=True)[[key, "knowledge_date", "state"]]
    return (E.sort_values([key, "knowledge_date"], kind="stable")
             .drop_duplicates([key, "knowledge_date"], keep="last"))


def build_watchlist_panel(P: pd.DataFrame, actions: pd.DataFrame,
                          sec: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, bool]]:
    """(code, month) 패널에 방화벽 플래그를 as-of 결합한다.

    반환: (패널, 조항별 활성여부)   — 활성여부가 False 인 조항은 방화벽에서 제외되고 그 사실이
          로그·표에 남는다(K6). 데이터가 없는데 '전부 적정'으로 간주해 통과시키지 않는다.
    """
    P = P.copy()
    for c in WATCH_FLAG_COLS:
        if c not in P.columns:
            P[c] = np.nan          # NaN = '알 수 없음'. 0(정상)과 구분한다.

    active = {"watchlist": False, "alert": False, "halt": False, "audit": False,
              "delist_risk": False}
    if actions is None or len(actions) == 0:
        LOG.warn("시장조치 이벤트가 없어 방화벽의 관리종목/감사의견/거래정지 조항을 "
                 "전부 비활성화합니다(K6). 방화벽은 자본잠식·영업CF·유동성·밸류 조항만으로 "
                 "동작하며, 그 사실이 R5-M 절제표에 그대로 드러납니다.")
        return P, active

    # corp_code → code 매핑.
    # ★ 1:N 이다. 한 법인(corp_code)이 보통주·우선주 등 여러 종목코드를 가진다.
    #   set_index("corp_code")["code"].to_dict() 로 만들면 중복 인덱스에서 **마지막 하나만**
    #   살아남는다. sec 가 code 오름차순이라 살아남는 건 대개 우선주(001685)이고,
    #   그러면 관리종목·감사의견·거래정지 플래그가 보통주(001680)에는 전혀 안 붙는다.
    #   실제 백테스트가 거래하는 건 보통주이므로 방화벽이 조용히 새는 통로가 된다.
    #   → 매핑을 접지 말고 펼친다(explode). 한 법인의 이벤트는 그 법인의 전 종목에 적용된다.
    link = (sec.dropna(subset=["corp_code"])[["code", "corp_code"]].copy()
               .assign(corp_code=lambda d: d["corp_code"].astype(str),
                       code=lambda d: d["code"].astype(str))
               .drop_duplicates())
    ev = actions.copy()
    ev["corp_code"] = ev["corp_code"].astype(str)
    n_before = len(ev)
    ev = ev.merge(link, on="corp_code", how="left")
    n_unmapped = int(ev["code"].isna().sum())
    ev = ev.dropna(subset=["code", "rcept_dt"])
    n_fan = len(ev) - (n_before - n_unmapped)
    if n_fan > 0:
        LOG.debug(f"시장조치 이벤트 {n_fan:,}건이 복수 상장(보통주/우선주)으로 확장되었습니다.")
    if n_unmapped:
        LOG.info(f"시장조치 이벤트 {n_unmapped:,}건은 corp_code↔종목코드 매핑이 없어 제외했습니다 "
                 f"(비상장·합병소멸 법인이 대부분입니다).")

    specs = [
        ("is_watchlist",      _step_state(ev, "watch_on", "watch_off", "code"), "watchlist"),
        ("is_alert",          _step_state(ev, "alert_on", "alert_off", "code"), "alert"),
        ("is_trading_halted", _step_state(ev, "halt_on", "halt_off", "code"), "halt"),
        ("audit_bad",         _one_shot_state(ev, "audit_bad", "code", 400), "audit"),
        ("delist_risk",       _one_shot_state(ev, "delist_risk", "code", 400), "delist_risk"),
    ]

    base = P[["code", "month"]].copy()
    base["code"] = base["code"].astype(str)
    base["_ord"] = np.arange(len(base))
    L = base.dropna(subset=["month"]).sort_values("month", kind="stable")

    for colname, S, key in specs:
        if S is None or S.empty:
            continue
        S = S.copy()
        S["code"] = S["code"].astype(str)
        S = S.dropna(subset=["knowledge_date"]).sort_values("knowledge_date", kind="stable")
        try:
            M = pd.merge_asof(L, S, left_on="month", right_on="knowledge_date",
                              by="code", direction="backward")
        except Exception as e:                                          # noqa
            LOG.warn(f"{colname} as-of 결합 실패({type(e).__name__}) — 이 조항을 비활성화합니다.")
            continue
        vals = M.set_index("_ord")["state"].reindex(base["_ord"]).to_numpy()
        # 이벤트가 한 번도 없던 종목은 NaN → '해당 조치 없음'(=0) 으로 본다.
        # 소스 자체는 확보됐으므로 '알 수 없음'이 아니라 '해당 없음'이 맞다.
        P[colname] = np.nan_to_num(vals.astype("float64"), nan=0.0)
        active[key] = True

    on_rows = [[c, f"{int(pd.to_numeric(P[c], errors='coerce').fillna(0).sum()):,}",
                f"{100*pd.to_numeric(P[c], errors='coerce').fillna(0).mean():.2f}%",
                "활성" if active[k] else "비활성(K6)"]
               for c, _, k in [(a, b, d) for a, b, d in specs]]
    LOG.table(on_rows, ["방화벽 플래그", "발동 행수", "패널 비중", "조항 상태"],
              ["l", "r", "r", "c"],
              title="관리종목·감사의견·거래정지 (PIT 계단함수로 복원 — 현재 목록의 소급적용 아님)")
    return P, active


def derive_halt_from_price(px_daily: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    """가격 데이터에서 거래정지를 보강 추정한다(공시 누락 대비).

    월말 직전 20거래일 중 거래량 0 인 날이 10일 이상이면 사실상 거래가 없는 종목이다.
    공시 기반 플래그와 OR 로 결합한다 — 방화벽은 fail-closed 가 안전한 쪽이다.
    """
    if px_daily is None or len(px_daily) == 0 or "volume" not in px_daily.columns:
        return P
    d = px_daily[["code", "date", "volume"]].copy()
    d = d.sort_values(["code", "date"], kind="stable")
    d["_zero"] = (pd.to_numeric(d["volume"], errors="coerce").fillna(0) <= 0).astype("int8")
    d["_z20"] = (d.groupby("code", observed=True)["_zero"]
                  .transform(lambda s: s.rolling(20, min_periods=5).sum()))
    d["month"] = as_ts_series(d["date"]) + pd.offsets.MonthEnd(0)
    m = (d.groupby(["code", "month"], observed=True)["_z20"].last().reset_index()
          .rename(columns={"_z20": "zero_days20"}))
    out = P.merge(m, on=["code", "month"], how="left")
    halt_px = (pd.to_numeric(out["zero_days20"], errors="coerce").fillna(0) >= 10).astype("float64")
    prev = pd.to_numeric(out.get("is_trading_halted"), errors="coerce").fillna(0.0)
    out["is_trading_halted"] = np.maximum(prev.to_numpy(), halt_px.to_numpy())
    n_add = int((halt_px.to_numpy() > prev.to_numpy()).sum())
    if n_add:
        LOG.info(f"거래량 기준으로 거래정지 {n_add:,}행을 추가 식별했습니다 "
                 f"(공시 누락 보강 — 20거래일 중 10일 이상 거래량 0).")
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-B  런타임 예산 강제 + DART 재무 수집 사다리 (§5 · §10)                                 ║
# ║                                                                                          ║
# ║  ★ 이 모듈이 존재하는 이유 (실제로 계약을 어긴 사고) ─────────────────────────────────    ║
# ║    한때 여기서 전 종목(3,915사) × 12연도 × 4보고서 = 187,920 건을 단건 API 로 요청했다.   ║
# ║    일일 한도가 20,000 이므로 코드가 스스로 "약 10일 걸립니다"라고 말하면서 그대로         ║
# ║    실행을 시작했다. §10 의 '총 4시간' 은 협상 대상이 아닌데도.                             ║
# ║    문제는 느린 게 아니라 **예산을 넘길 것을 알면서 시작한 것**이다.                        ║
# ║                                                                                          ║
# ║  → 원칙: 견적을 먼저 낸다. 예산에 안 들어가면 시작하지 않는다.                             ║
# ║          더 싼 경로로 내려가고, 그래도 안 되면 '무엇을 못 했는지'를 표로 보고한다.         ║
# ║          임계를 늘려 통과시키지 않는다. 조용히 오래 도는 것은 금지다.                     ║
# ║                                                                                          ║
# ║  수집 사다리 (싼 것부터. 각 단계는 남은 예산 안에서만 돈다)                                 ║
# ║    ① 드라이브 공용 캐시            — 0 호출                                                ║
# ║    ② 재무정보 일괄다운로드(벌크)   — 분기당 1 파일. 되면 여기서 끝난다                     ║
# ║    ③ fnlttMultiAcnt 배치           — 1 호출당 100사. 주요계정만(자본금·자산·부채·자본·매출) ║
# ║    ④ fnlttSinglAcntAll 단건        — 전 계정. ★예산 안에서 '유동성 상위부터'만            ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

class Deadline:
    """실행 전체의 시계. 각 단계가 '남은 시간'을 물어보고 스스로 줄인다."""

    def __init__(self, total_min: float):
        self.t0 = time.time()
        self.total_s = float(total_min) * 60.0
        self.enforced = not COLD_BUILD_MODE

    def elapsed_s(self) -> float:
        return time.time() - self.t0

    def remain_s(self, budget_min: Optional[float] = None, spent_s: float = 0.0) -> float:
        """남은 초. budget_min 을 주면 '그 단계 예산'과 '전체 잔여' 중 작은 쪽."""
        left_total = self.total_s - self.elapsed_s()
        if budget_min is None:
            return max(0.0, left_total)
        return max(0.0, min(left_total, float(budget_min) * 60.0 - spent_s))

    def over(self) -> bool:
        return self.enforced and self.elapsed_s() > self.total_s

    def report(self):
        el = self.elapsed_s() / 60.0
        pct = 100 * el / max(self.total_s / 60.0, 1e-9)
        (LOG.warn if pct > 100 else LOG.info)(
            f"런타임 예산 — 경과 {el:.1f}분 / 상한 {self.total_s/60:.0f}분 ({pct:.0f}%)"
            + ("  ※ COLD_BUILD_MODE=True 라 강제하지 않습니다" if not self.enforced else ""))


DEADLINE: Optional[Deadline] = None


class LayerBudget:
    """수집층(L1) 예산 — **단계별로** 재고, 넘기면 그 단계부터 캐시 전용으로 강등한다.

    ★ 총량만 재는 것은 예산이 아니다. 실측 사고에서 L1.RSRCH 하나가 126분을 먹어
      L1 합계가 배정의 6.1배가 됐는데도, 총 wall-clock 줄은 '4시간 안'이라며 통과시켰다.
      단계마다 상한이 없으면 한 단계가 나머지 전부의 예산을 먹고, 그 사실이 표에 안 남는다.
    """

    def __init__(self, total_min: float, alloc: Dict[str, float]):
        self.t0 = time.time()
        self.total_s = float(total_min) * 60.0
        self.alloc = dict(alloc)
        self.spent: Dict[str, float] = {}
        self.demoted: List[str] = []

    def elapsed_s(self) -> float:
        return time.time() - self.t0

    def stage_left_s(self, sid: str) -> float:
        """이 단계에 남은 초 = min(단계 배정, L1 전체 잔여, 전체 실행 잔여)."""
        s = float(self.alloc.get(sid, 5.0)) * 60.0 - float(self.spent.get(sid, 0.0))
        s = min(s, self.total_s - self.elapsed_s())
        if DEADLINE is not None:
            s = min(s, DEADLINE.remain_s())
        return max(0.0, s)

    def record(self, sid: str, dur_s: float):
        self.spent[sid] = float(self.spent.get(sid, 0.0)) + float(dur_s)

    def report(self) -> pd.DataFrame:
        rows = []
        for sid, al in self.alloc.items():
            sp = float(self.spent.get(sid, 0.0))
            over = sp > al * 60.0 + 1e-9
            rows.append([sid, f"{sp/60:.1f}분", f"{al:.0f}분",
                         ("❗초과" if over else "✔") +
                         (" · 캐시전용 강등" if sid in self.demoted else "")])
        tot = sum(self.spent.values())
        rows.append(["── L1 합계", f"{tot/60:.1f}분", f"{self.total_s/60:.0f}분",
                     "❗초과" if tot > self.total_s else "✔ 예산 내"])
        return pd.DataFrame(rows, columns=["단계", "실측", "배정", "판정"])


L1BUDGET: Optional[LayerBudget] = None


def l1_guard(sid: str) -> bool:
    """단계 진입 시 호출. 배정을 이미 소진했으면 이 단계를 캐시 전용으로 강등한다.

    ★ 강등은 조용히 하지 않는다. 무엇을 못 받게 되는지 로그에 남기고, 마지막
      런타임 감사표에 '캐시전용 강등'으로 표시한다.
    """
    global RUN_MODE
    if COLD_BUILD_MODE or L1BUDGET is None or RUN_MODE == "CACHED":
        return False
    if L1BUDGET.stage_left_s(sid) > 5.0:
        return False
    RUN_MODE = "CACHED"
    L1BUDGET.demoted.append(sid)
    LOG.warn(f"[{sid}] 수집 예산(L1 {COLLECT_BUDGET_MIN}분)을 소진했습니다 — "
             f"이 단계부터 **신규 수집을 중단하고 드라이브 캐시만** 사용합니다. "
             f"받지 못한 부분은 다음 실행이 정확히 이어받습니다. "
             f"예산을 넘겨 조용히 계속 도는 것보다, 무엇을 못 받았는지 표로 남기는 쪽이 "
             f"§10 계약을 지키는 방법입니다. 콜드빌드를 끝까지 돌리려면 "
             f"COLD_BUILD_MODE=True 로 두세요.")
    return True


def dart_calls_left() -> int:
    """오늘 남은 DART 호출 수. 예산 견적의 기준이 된다."""
    try:
        used = int(getattr(DBUDGET, "n", 0) or 0)
    except Exception:
        used = 0
    return max(0, DART_DAILY_LIMIT - used)


def plan_dart_collection(corp_codes: Sequence[str], years: Sequence[int],
                         budget_min: float) -> dict:
    """수집 '계획'을 먼저 세우고 표로 보여준다. 계획 없이 시작하지 않는다.

    반환: {"mode": "bulk"|"batch"|"single"|"cache_only", "corps": [...], "years": [...], ...}
    """
    n_corp, n_year = len(corp_codes), len(years)
    reprts = 4
    need_single = n_corp * n_year * reprts
    need_batch = (math.ceil(n_corp / max(DART_MULTI_BATCH, 1)) * n_year * reprts)
    left_calls = dart_calls_left()
    # 실측 처리율: 단건 ≈ 4.4 call/s (운영 로그 기준), 배치도 호출당 비용은 비슷하다.
    rate = 4.0
    can_do_calls = int(max(0.0, budget_min * 60.0) * rate)
    cap = min(left_calls, can_do_calls)

    rows = [
        ["① 벌크 ZIP (사용자 제공 파일)", "0",
         "즉시", "재고·매출채권·매출원가·영업CF 전부", "✔ 있으면 최우선"],
        ["② 배치 fnlttMultiAcnt (100사/회)", f"{need_batch:,}",
         f"{need_batch/rate/60:.1f}분", "주요계정 14종(BS+IS). 현금흐름표 없음",
         "✘ 예산 초과" if need_batch > cap else "✔ 예산 내"],
        ["③ 단건 fnlttSinglAcntAll (1사/회)", f"{need_single:,}",
         f"{need_single/rate/3600:.1f}시간", "전 계정. 회전일수·이자보상배율 보강용",
         "✘ 예산 초과" if need_single > cap else "✔ 예산 내"],
        ["── 이번 실행 가용 호출", f"{cap:,}", f"{budget_min:.0f}분",
         f"일일잔여 {left_calls:,} · 시간환산 {can_do_calls:,}", ""],
    ]
    LOG.table(rows, ["경로", "필요 호출", "예상 소요", "얻는 것", "예산 판정"],
              ["l", "r", "r", "l", "l"], maxw=44,
              title="DART 수집 계획 (§5 · §10) — 시작 전에 견적부터 낸다")
    LOG.info("★ 이 전략의 증거층 3센서(i_sales·i_turn·i_accr)는 ②만으로 전부 산출됩니다. "
             "③은 '있으면 더 좋은' 보강이지 필수가 아닙니다 — 그래서 ③이 예산을 넘겨도 "
             "백테스트는 정상적으로 끝납니다.")

    if not COLD_BUILD_MODE and need_single > cap:
        LOG.warn(f"③ 단건 전량은 {need_single:,}회로 이번 실행 예산({cap:,}회)을 "
                 f"{need_single/max(cap,1):.0f}배 초과합니다. **시작하지 않습니다.** "
                 f"②로 E층을 완성하고, ③은 '유동성 상위'부터 예산 안에서만 받아 캐시에 "
                 f"쌓습니다(다음 실행이 이어받습니다). "
                 f"전 종목 콜드빌드를 며칠에 걸쳐 하려면 COLD_BUILD_MODE=True 로 두세요.")
    return {"need_single": need_single, "need_batch": need_batch, "cap": cap,
            "left_calls": left_calls, "rate": rate}


# ── ② 재무정보 일괄다운로드 (벌크 ZIP) ──────────────────────────────────────────────────────
#   ★ 사실관계부터 정확히 (검증 결과) ─────────────────────────────────────────────────────
#     OpenDART 의 '재무정보 일괄다운로드'는 **OpenAPI 가 아니다.**
#       · 위치: https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do  (로그인 불필요)
#       · 다운로드는 페이지의 자바스크립트 클릭 핸들러로 동작하며, crtfc_key 로 부를 수 있는
#         /api/ 엔드포인트가 존재하지 않는다. 실제로 공개된 어떤 래퍼도 이 경로를 구현하지
#         못했고, 자동화한 사례는 전부 셀레늄으로 브라우저를 몬다.
#     → 그래서 **URL 을 추측해 때려보지 않는다.** 이전 버전은 추측한 두 URL 을 48분기 ×
#       2패턴으로 시도해 25분을 버렸다. 실패를 실패로 보고하지 않고 시간을 태우는 코드다.
#
#   ★ 대신 이렇게 한다 (§5 '종목별 루프 금지'를 지키는 유일하게 정직한 방법) ──────────────
#     사용자가 위 페이지에서 받은 ZIP 을 드라이브 폴더에 넣어두면 이 코드가 읽어들인다.
#     한 번만 받아두면 그 뒤로는 영구히 공용 인덱스에서 재사용된다(API 호출 0회).
#     ZIP 안에는 재고자산·매출채권·매출원가·영업활동현금흐름이 전부 들어 있다 —
#     즉 이 전략의 증거층을 '가장 완전한 형태'로 채우는 유일한 무료 경로다.
DART_BULK_SUBDIR = "dart_bulk"          # {GDRIVE_ROOT}/dart_bulk 도 자동으로 훑는다
_BULK_SJ = {"재무상태표": "BS", "손익계산서": "IS", "포괄손익계산서": "CIS",
            "현금흐름표": "CF", "자본변동표": "SCE"}
_BULK_REPRT = {"1분기보고서": "11013", "반기보고서": "11012",
               "3분기보고서": "11014", "사업보고서": "11011"}


def _bulk_parse_one(name: str, raw: bytes) -> Optional[pd.DataFrame]:
    """일괄다운로드 txt 1개 → _FS_KEEP 스키마. 탭구분 · CP949 · 컬럼명은 '이름'으로 찾는다."""
    sj = next((v for k, v in _BULK_SJ.items() if k in name), None)
    rep = next((v for k, v in _BULK_REPRT.items() if k in name), None)
    yr = re.search(r"(20\d{2})", name)
    if not sj or not rep or not yr:
        return None
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            d = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, encoding=enc,
                            on_bad_lines="skip")
            break
        except Exception:
            d = None
    if d is None or not len(d):
        return None
    d.columns = [str(c).strip().replace(" ", "") for c in d.columns]
    need = {"종목코드", "항목코드", "항목명"}
    if not need <= set(d.columns):
        return None

    def _pick(prefix: str, want_cum: bool) -> Optional[str]:
        cs = [c for c in d.columns if c.startswith(prefix)]
        if not cs:
            return None
        if want_cum:
            cum = [c for c in cs if "누적" in c]
            if cum:
                return cum[0]
        return cs[0]

    flow = sj in ("IS", "CIS", "CF")
    c_cur, c_cum = _pick("당기", False), (_pick("당기", True) if flow else None)
    c_pv, c_pc = _pick("전기", False), (_pick("전기", True) if flow else None)
    if not c_cur:
        return None
    out = pd.DataFrame({
        "corp_code": None,
        "bsns_year": int(yr.group(1)),
        "reprt_code": rep,
        "fs_div": np.where(d["재무제표종류"].astype(str).str.contains("연결", na=False)
                           if "재무제표종류" in d.columns else False, "CFS", "OFS"),
        "sj_div": sj,
        "account_id": d["항목코드"],
        "account_nm": d["항목명"],
        "thstrm_amount": d[c_cur],
        "thstrm_add_amount": d[c_cum] if (c_cum and c_cum != c_cur) else None,
        "frmtrm_amount": d[c_pv] if c_pv else None,
        "frmtrm_q_amount": None,
        "frmtrm_add_amount": d[c_pc] if (c_pc and c_pc != c_pv) else None,
        "bfefrmtrm_amount": None,
        "rcept_no": None,
    })
    out["_stock_code"] = d["종목코드"].astype(str).str.replace(r"[\[\]\s]", "", regex=True)
    return out


def ingest_dart_bulk_files(sec: pd.DataFrame) -> pd.DataFrame:
    """드라이브/로컬에 놓인 '재무정보 일괄다운로드' ZIP 을 읽어들인다. API 호출 0회."""
    cached = VAULT.get_table("dart_bulk_raw", scope="shared")
    dirs = [d for d in (list(globals().get("DART_BULK_DIRS", []))
                        + [os.path.join(VAULT.root, DART_BULK_SUBDIR)]) if d]
    zips: List[str] = []
    for root in dirs:
        try:
            if not os.path.isdir(root):
                continue
            for dp, _dn, fn in os.walk(root):
                zips += [os.path.join(dp, f) for f in fn if f.lower().endswith(".zip")]
        except Exception:
            continue
    zips = sorted(set(zips))
    if not zips:
        LOG.info("재무정보 일괄다운로드 ZIP 이 없습니다 — 배치(주요계정) 경로로 진행합니다. "
                 "★ 증거층을 가장 완전하게 채우고 싶다면 "
                 "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do 에서 "
                 f"연도·보고서별 ZIP 을 받아 '{os.path.join(VAULT.root, DART_BULK_SUBDIR)}' 에 "
                 "넣어두세요. 한 번만 넣으면 이후 실행은 영구히 재사용합니다(API 호출 0회).")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    LOG.info(f"재무정보 일괄다운로드 ZIP {len(zips)}개를 읽습니다 (API 호출 0회 · §5 벌크 경로)")
    parts, n_file = [], 0
    for zp in zips:
        try:
            with zipfile.ZipFile(zp) as z:
                for nm in z.namelist():
                    if not nm.lower().endswith((".txt", ".csv")):
                        continue
                    p = _bulk_parse_one(os.path.basename(nm), z.read(nm))
                    if p is not None and len(p):
                        parts.append(p)
                        n_file += 1
        except Exception as e:                                     # noqa
            LOG.warn(f"ZIP 읽기 실패 {os.path.basename(zp)} ({type(e).__name__}) — 건너뜁니다.")
    if not parts:
        LOG.warn("ZIP 은 있으나 인식 가능한 재무 텍스트 파일이 없습니다 "
                 "(탭구분 · CP949 · '종목코드/항목코드/항목명' 컬럼 필요).")
        return cached if cached is not None else pd.DataFrame(columns=_FS_KEEP)

    B = pd.concat(parts, ignore_index=True)
    # 종목코드 → corp_code. 벌크 파일에는 corp_code 가 없다.
    link = (sec.dropna(subset=["corp_code"])[["code", "corp_code"]]
               .assign(code=lambda x: x["code"].astype(str).str.zfill(6),
                       corp_code=lambda x: x["corp_code"].astype(str))
               .drop_duplicates("code"))
    B["_stock_code"] = B["_stock_code"].map(to_code6)
    B = B.merge(link.rename(columns={"code": "_stock_code"}), on="_stock_code", how="left",
                suffixes=("", "_m"))
    B["corp_code"] = B["corp_code"].where(B["corp_code"].notna(), B.get("corp_code_m"))
    n_nolink = int(B["corp_code"].isna().sum())
    B = B.dropna(subset=["corp_code"])
    if n_nolink:
        LOG.info(f"벌크 {n_nolink:,}행은 종목코드↔법인코드 매핑이 없어 제외했습니다 "
                 f"(비상장·합병소멸 법인).")
    B = B[[c for c in _FS_KEEP if c in B.columns]]
    B = pd.concat(([cached] if cached is not None and len(cached) else []) + [B],
                  ignore_index=True)
    B = B.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id",
                           "account_nm"], keep="last")
    VAULT.put_table("dart_bulk_raw", B, scope="shared", domain="dart",
                    source="opendart 재무정보 일괄다운로드(사용자 제공 ZIP)")
    LOG.ok(f"벌크 재무 {len(B):,}행 · 파일 {n_file}개 · {B['corp_code'].nunique():,}사 "
           f"— 재고·매출채권·매출원가·영업CF 포함. API 호출 0회로 확보했습니다.")
    PIPE.io("IN", "DRIVE", "dart_bulk_raw", B, source="재무정보 일괄다운로드 ZIP")
    return B


# ── 사다리 실행 ─────────────────────────────────────────────────────────────────────────────
def collect_dart_financials_budgeted(sec: pd.DataFrame, months: pd.DatetimeIndex,
                                     px_daily: Optional[pd.DataFrame],
                                     budget_min: float) -> pd.DataFrame:
    """예산 안에서 최대한 받는다. 예산을 넘길 것 같으면 '시작하지 않고' 줄인다."""
    t_start = time.time()
    ccs_all = sec["corp_code"].dropna().astype(str).unique().tolist()
    yrs = sorted({int(m.year) for m in months} | {int(months[0].year) - 1})
    reprts = [REPRT_CODES[k] for k in ("Q1", "H1", "Q3", "FY")]
    plan = plan_dart_collection(ccs_all, yrs, budget_min)

    frames: List[pd.DataFrame] = []

    # ② 벌크 ZIP (사용자가 넣어둔 파일 · API 호출 0회). 있으면 증거층이 가장 완전해진다.
    B = ingest_dart_bulk_files(sec)
    if B is not None and len(B):
        frames.append(B)

    def _spent() -> float:
        return time.time() - t_start

    def _left_min() -> float:
        if DEADLINE is None:
            return max(0.0, budget_min - _spent() / 60.0)
        return DEADLINE.remain_s(budget_min, _spent()) / 60.0

    # ③ 배치 (주요계정 14종) — 유동자산·유동부채·이익잉여금·자본금·자산·부채·자본·매출·
    #    영업이익·당기순이익. ★이 전략의 E층 3센서가 전부 여기서 나온다:
    #      i_sales  = 매출 전기대비          i_turn = 자산회전율 전기대비
    #      i_accr   = (Δ유동자산−Δ유동부채)/자산   (Sloan 1996 대차대조표법)
    #    100사/회이므로 전 종목 × 12연도 × 4보고서가 1,000회 미만이다. 가장 먼저, 반드시 돈다.
    if _left_min() > 0.5:
        try:
            M = fetch_dart_multi_accounts(ccs_all, yrs)
            if M is not None and len(M):
                frames.append(M)
        except Exception as e:                                     # noqa
            LOG.warn(f"DART 주요계정 배치 실패({type(e).__name__}) — 단건 경로로 넘어갑니다.")
    else:
        LOG.warn("남은 예산이 없어 주요계정 배치를 건너뜁니다 — E층 전체가 결측이 됩니다.")

    # ④ 단건 (전 계정) — ★유동성 상위부터, 예산 안에서만
    left_min = _left_min()
    rate = plan["rate"]
    cap_calls = int(min(dart_calls_left(), max(0.0, left_min) * 60.0 * rate))
    if COLD_BUILD_MODE:
        cap_calls = dart_calls_left()
        LOG.warn("COLD_BUILD_MODE=True — 단건 수집의 예산 강제를 해제합니다. "
                 "이 실행은 §10 의 4시간 제약을 지키지 않을 수 있습니다(의도된 선택).")
    if cap_calls > 0:
        prio = _liquidity_priority(sec, px_daily)
        # ★★ 이미 받아둔 회사를 건너뛰지 않으면 창이 영원히 안 움직인다 ★★
        #   예전 구현은 우선순위 상위 N 사를 매 실행 그대로 잘라 넘겼다. 2회차부터는
        #   그 N 사가 전부 캐시에 있어 신규 작업이 0건이 되고, 시간을 안 쓰니 3회차도
        #   같은 N 사를 고른다 — 60사에서 멈춘 채 며칠을 돌려도 한 발짝도 못 나간다.
        _cached = VAULT.get_table("dart_fnltt_raw", scope="shared")
        _done_corp: set = set()
        if _cached is not None and len(_cached):
            try:
                _need = len(yrs) * len(reprts) * 0.8
                _cnt = (_cached.groupby("corp_code")[["bsns_year", "reprt_code"]]
                        .apply(lambda g: g.drop_duplicates().shape[0]))
                _done_corp = set(_cnt[_cnt >= _need].index.astype(str))
            except Exception:
                _done_corp = set()
        n_corp_afford = max(1, cap_calls // (len(yrs) * len(reprts)))
        pool = [c for c in (prio or ccs_all) if c not in _done_corp]
        pick = pool[:n_corp_afford]
        LOG.info(f"단건 전 계정 수집 — 예산 {cap_calls:,}회로 {len(pick):,}사 × "
                 f"{len(yrs)}연도 × {len(reprts)}보고서. "
                 f"이미 확보 {len(_done_corp):,}사는 건너뜁니다(다음 실행이 그 다음 구간을 "
                 f"이어받아 창이 실제로 전진합니다). 전 종목 {len(ccs_all):,}사 중 누적 "
                 f"{100*(len(_done_corp)+len(pick))/max(len(ccs_all),1):.0f}%.")
        try:
            F = fetch_dart_financials(pick, yrs, priority=pick)
            if F is not None and len(F):
                frames.append(F)
        except Exception as e:                                     # noqa
            LOG.warn(f"DART 단건 수집 실패({type(e).__name__}) — 받은 분량으로 진행합니다.")
    else:
        LOG.warn("남은 예산이 없어 단건 전 계정 수집을 건너뜁니다 — "
                 "재고·매출원가·영업CF·이자비용이 결측이 되어 증거층이 얇아집니다. "
                 "다음 실행에서 캐시에 이어받습니다(진행분은 이미 저장됨).")

    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    out = pd.concat([f.reindex(columns=sorted(set().union(*[set(x.columns) for x in frames])))
                     for f in frames], ignore_index=True)
    LOG.ok(f"DART 재무 원시 {len(out):,}행 확보 — 소요 {_spent()/60:.1f}분 "
           f"(예산 {budget_min:.0f}분)")
    return out


def _liquidity_priority(sec: pd.DataFrame, px_daily: Optional[pd.DataFrame]) -> List[str]:
    """예산이 부족할 때 '무엇을 먼저 받을지'의 기준 = **U-MICRO 에 실제로 들어올 종목**.

    ★ 예전 구현의 치명적 실수 ─────────────────────────────────────────────────────────
      거래대금 '내림차순'으로 정렬했다. 그러면 삼성전자·SK하이닉스부터 받는다.
      그런데 이 전략의 유니버스는 시총 하위권이라 그 회사들은 **정의상 전부 제외**된다.
      즉 예산을 다 써서 유니버스 밖 종목의 재무만 모으고, 정작 U-MICRO 종목의
      재고·영업CF 커버리지는 0% 로 남는다. 계정 정규식을 아무리 고쳐도 안 풀린다.

    ★ 올바른 순서: 유동성 하한(§7 방화벽 V6)은 통과하되 **거래대금이 작은 쪽부터**.
      = 유동성은 있는데 규모는 작은 구간 = U-MICRO 그 자체.
    """
    if px_daily is None or len(px_daily) == 0 or "amount" not in px_daily.columns:
        return []
    try:
        amt = px_daily.groupby("code", observed=True)["amount"].median()
        liquid = amt[amt >= UMICRO_MIN_ADV_KRW]
        # 유동성 하한을 넘는 종목이 거의 없으면(가격 소스 부실) 전체를 대상으로 한다.
        if len(liquid) < 200:
            liquid = amt
        amt = liquid.sort_values(ascending=True)      # ★작은 쪽부터 = U-MICRO 우선
        c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
                  .set_index("code")["corp_code"].astype(str).to_dict())
        out, seen = [], set()
        for code in amt.index:
            cc = c2c.get(str(code))
            if cc and cc not in seen:
                seen.add(cc)
                out.append(cc)
        return out
    except Exception:
        return []



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L1-S  U-MICRO 패널 · L1 센서 (§8)                                                        ║
# ║                                                                                          ║
# ║  ★ 센서는 '분기 재무 프레임'에서 계산한다. 월 패널에서 shift(12) 로 계산하지 않는다.       ║
# ║    이유가 두 가지다:                                                                      ║
# ║      ① 월 패널은 유니버스 진입/이탈로 구멍이 뚫린다. shift(12) 는 구멍을 건너뛰어         ║
# ║         2년 전 값을 '1년 전'으로 취급한다 — 조용한 계산 오류다.                            ║
# ║      ② 분기 프레임은 관측당 정확히 한 행이고 이미 (corp_code, 연, 분기)로 정렬돼 있다.     ║
# ║         lag 4 = 정확히 1년. 3만 종목월이 아니라 10만 분기행만 계산하면 되므로 빠르다.      ║
# ║    계산된 센서는 PIT.asof_join 이 knowledge_date 그대로 월 패널로 실어 나른다(C1).         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

# 분기 프레임에서 만들어져 월 패널로 실려 가는 컬럼 전체. 스키마를 계약적으로 고정해
# "어떤 실행엔 있고 어떤 실행엔 없는" 축이 생기지 않게 한다.
MICRO_QUARTERLY_COLS = [
    "i_sales", "i_dio", "i_dso", "i_turn", "i_accr",
    "op_cf_neg_streak", "interest_coverage", "capital_impairment",
    "v1_pushout", "v2_bad_3q",
    "asset_turn", "accr_level",          # 해석표·진단카드가 읽는 원시 수준값
]

# 어떤 정의가 채택됐는지 남긴다 — 센서 가용성표 바로 위에 출력된다.
SENSOR_DEFS_USED: List[list] = []


def _pick_sensor(name: str, cands: "Sequence[Tuple[str, pd.Series]]",
                 combinable: bool = False) -> pd.Series:
    """센서 정의 사다리 — 결측률이 임계 이하인 첫 정의를 채택한다.

    ★ 이 함수가 존재하는 이유 (실측된 중단 사고) ────────────────────────────────────────
      한 정의만 고정하면, 그 정의가 요구하는 계정이 공시되지 않는 구간에서 축이 통째로
      죽는다. 실제로 i_turn 100.0% / i_accr 99.9% 결측 → 활성 TP 0개 → C14-d 중단이
      났다. 원인은 '데이터가 없어서'가 아니라 **재고·영업CF 를 요구하는 정의만 있었기
      때문**이다. 같은 경제적 질문("회전이 악화됐나", "이익의 질이 유지되나")에 답하는
      더 싼 정의가 존재하는데도 쓰지 않았다.

    ★ combinable=False 인 이유가 중요하다.
      정의가 다르면 단위·척도가 다르다. 한 셀 안에서 어떤 종목은 A 정의로, 어떤 종목은
      B 정의로 값이 채워지면 **셀 내 랭크가 의미를 잃는다** — 에러 없이 신호만 오염된다.
      그래서 척도가 동일한 정의(i_sales 의 YTD성장 vs TTM성장)만 보완결합을 허용하고,
      나머지는 '하나를 고르고 왜 골랐는지 표로 남긴다'.
    """
    stats = [(nm, s, (float(s.isna().mean()) if len(s) else 1.0)) for nm, s in cands]
    thr = RESEARCH_MAX_MISSING_RATE
    chosen, mode = next(((t, "채택") for t in stats if t[2] <= thr), (None, ""))
    if chosen is None and combinable:
        out = stats[0][1].copy()
        for _, s, _m in stats[1:]:
            out = out.where(out.notna(), s)
        chosen, mode = ("+".join(t[0] for t in stats), out,
                        float(out.isna().mean()) if len(out) else 1.0), "보완결합"
    if chosen is None:
        chosen = min(stats, key=lambda t: t[2])
        mode = "차선(임계초과)"
    SENSOR_DEFS_USED.append([name, chosen[0], mode, f"{100*chosen[2]:.1f}%",
                             " · ".join(f"{t[0]}={100*t[2]:.0f}%" for t in stats)])
    return pd.to_numeric(chosen[1], errors="coerce").astype("float32")

# ── DART 계정 확장 ──────────────────────────────────────────────────────────────────────────
#   방화벽이 요구하는 두 계정이 v2 코어의 ACCOUNT_PATTERNS 에 없다. 코어 파일을 고치는 대신
#   여기서 확장한다(다른 전략의 동작을 바꾸지 않기 위해). tidy_financials 는 호출 시점에
#   이 딕셔너리를 읽으므로 확장이 그대로 반영된다.
ACCOUNT_PATTERNS.update({
    # 이자보상배율의 분모. FinanceCosts(금융원가)에는 이자 외 항목도 섞이지만
    # 중소형주 공시에서 '이자비용' 단독 계정이 없는 경우가 많아 차선으로 함께 잡는다.
    "interest_expense": ("IS", [r"InterestExpense", r"^이자비용$", r"FinanceCosts", r"^금융원가$"]),
    # 자본잠식 판정의 기준선(자본총계 < 자본금).
    "capital_stock":    ("BS", [r"ifrs-full_IssuedCapital$", r"^자본금$"]),
})
if "interest_expense" not in FLOW_ITEMS:
    FLOW_ITEMS.append("interest_expense")

# 목표주가 병합은 중앙값으로 — 이 전략의 U층은 '리비전 방향'을 쓰는데, max 병합은
# 소스 불일치 시 항상 높은 값을 남겨 상향을 과대·하향을 과소 계상한다.
TARGET_PRICE_AGG = "median"
for _c in (["interest_expense", "capital_stock"]
           + [f"interest_expense{s}" for s in ("_q", "_ttm", "_cm", "_pv", "_pc")]
           + MICRO_QUARTERLY_COLS):
    if _c not in FUNDAMENTAL_COLS:
        FUNDAMENTAL_COLS.append(_c)


def add_micro_sensors_quarterly(W: pd.DataFrame) -> pd.DataFrame:
    """분기 재무 프레임에 §8 센서와 방화벽/거부권 입력을 붙인다.

    lag=4 분기 = 정확히 1년. 전 계산이 groupby-shift 벡터 연산이며 파이썬 루프가 없다.
    """
    if W is None or len(W) == 0:
        out = pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"]
                                   + MICRO_QUARTERLY_COLS)
        return out
    d = W.sort_values(["corp_code", "period_end"], kind="stable").reset_index(drop=True)

    # ── TTM 위생 ①: 달력 연속성 검증 ──────────────────────────────────────────────────
    #   코어의 TTM 은 rolling(4) 로 '행 4개'를 더한다. 중간에 분기나 연도가 통째로
    #   빠져 있어도 모른 채 합산하므로, 2년에 걸친 4개 분기가 1년치 TTM 으로 둔갑한다.
    #   → 4번째 전 행이 정확히 3분기 전인 경우에만 TTM 을 인정한다.
    if "q" in d.columns:
        qidx = pd.to_numeric(d["bsns_year"], errors="coerce") * 4 + pd.to_numeric(d["q"],
                                                                                 errors="coerce")
        contiguous_ttm = (qidx - qidx.groupby(d["corp_code"], observed=True).shift(3)) == 3
        n_bad = 0
        for c in FLOW_ITEMS:
            tc = f"{c}_ttm"
            if tc in d.columns:
                bad = d[tc].notna() & ~contiguous_ttm
                n_bad = max(n_bad, int(bad.sum()))
                d[tc] = d[tc].where(contiguous_ttm)
        if n_bad:
            LOG.info(f"TTM 달력 연속성 검사 — 분기가 빠져 있는 구간 최대 {n_bad:,}행의 TTM 을 "
                     f"결측 처리했습니다(2년치를 1년치로 계상하는 것을 방지).")

    # ── TTM 위생 ②: 연 1회 공시 기업 구제 ────────────────────────────────────────────
    #   반기·연간만 제출하는 기업(U-MICRO 에 흔하다)은 누적→분기 차분이 성립하지 않아
    #   TTM 이 영구 결측이 되고, 그 결과 증거층에서 통째로 사라진다.
    #   사업보고서(FY)의 누적치는 정의상 그 해의 12개월 합계 = 그 시점의 TTM 이다.
    if "reprt_code" in d.columns:
        is_fy = d["reprt_code"].astype(str) == REPRT_CODES["FY"]
        n_fix = 0
        for c in FLOW_ITEMS:
            tc = f"{c}_ttm"
            if tc in d.columns and c in d.columns:
                fill = d[tc].isna() & is_fy & d[c].notna()
                n_fix = max(n_fix, int(fill.sum()))
                d[tc] = d[tc].where(~fill, d[c])
        if n_fix:
            LOG.ok(f"연 1회 공시 기업 구제 — 사업보고서 누적치로 TTM 최대 {n_fix:,}행을 "
                   f"복원했습니다(반기·연간만 제출하는 소형주가 증거층에서 사라지지 않도록).")

    # ── lag4 달력 연속성 게이트 ★필수 ────────────────────────────────────────────────────
    #   shift(4) 는 '행 4개 전'이지 '1년 전'이 아니다. 분기보고서를 거르는 기업(U-MICRO 에
    #   흔하다)에서는 행 4개 전이 2년·4년 전이 된다. 연 1회 공시 기업이면 정확히 4년 전이다.
    #     · 연 10% 성장 기업의 i_sales 가 0.095 대신 0.378 로 찍힌다(4배 과대).
    #     · 성장률이 클수록 과대되므로, 그 기업들이 셀 랭크 최상위를 독식한다.
    #     · 즉 증거층이 "얼마나 자주 공시하지 않는가"를 측정하게 된다. 에러도 로그도 없이.
    #   → 4행 전의 분기 인덱스가 정확히 4분기 전일 때만 lag4 를 인정한다.
    if "q" in d.columns:
        _qidx = (pd.to_numeric(d["bsns_year"], errors="coerce") * 4
                 + pd.to_numeric(d["q"], errors="coerce"))
        _lag_ok = (_qidx - _qidx.groupby(d["corp_code"], observed=True).shift(4)) == 4
    else:
        _lag_ok = pd.Series(False, index=d.index)
    _n_lag_bad = int((~_lag_ok).sum())

    def lag4(name: str) -> pd.Series:
        """정확히 1년 전(4분기 전) 값. 달력상 4분기 전이 아니면 결측이다.

        ★groupby 객체를 캐시하지 않는다 — 컬럼을 추가한 뒤 같은 groupby 를 재사용하는 것은
        문서화되지 않은 동작에 기대는 것이다."""
        if name not in d.columns:
            return pd.Series(np.nan, index=d.index)
        return d.groupby("corp_code", observed=True)[name].shift(4).where(_lag_ok)

    # ── 재료 ────────────────────────────────────────────────────────────────────────────
    #   _cm = 당기 누적 · _pv = 전기(말) · _pc = 전기 누적.  전부 '한 행'에 들어 있으므로
    #   YoY 를 만들려고 분기 체인을 타지 않는다. 이게 이번 개편의 핵심이다.
    rev_c, rev_p = col(d, "revenue_cm"), col(d, "revenue_pc")
    cogs_c, cogs_p = col(d, "cogs_cm"), col(d, "cogs_pc")
    inv_c, inv_p = col(d, "inventory"), col(d, "inventory_pv")
    rec_c, rec_p = col(d, "receivable"), col(d, "receivable_pv")
    ni_c, ni_p = col(d, "net_income_cm"), col(d, "net_income_pc")
    cfo_c, cfo_p = col(d, "cfo_cm"), col(d, "cfo_pc")
    ast_c, ast_p = col(d, "assets"), col(d, "assets_pv")
    ca_c, ca_p = col(d, "current_assets"), col(d, "current_assets_pv")
    cl_c, cl_p = col(d, "current_liab"), col(d, "current_liab_pv")
    opi = col(d, "op_income_ttm")
    inte = col(d, "interest_expense_ttm")
    eq = col(d, "equity")
    cap = col(d, "capital_stock")
    rev_t = col(d, "revenue_ttm")

    # ── §8-1  i_sales : 매출 성장 (높을수록 좋다) ────────────────────────────────────────
    s_row = np.log(rev_c.where(rev_c > 0)) - np.log(rev_p.where(rev_p > 0))
    s_chain = (np.log(rev_t.where(rev_t > 0))
               - np.log(lag4("revenue_ttm").where(lambda s: s > 0)))
    # ★ 두 정의 모두 '로그 매출증가율'로 척도가 같다 → 보완결합이 허용되는 유일한 센서.
    d["i_sales"] = _pick_sensor("i_sales", [("전기누적 대비(단일행)", s_row),
                                            ("TTM lag4(분기체인)", s_chain)], combinable=True)

    # ── §8-2  i_turn : 회전이 악화되지 않았는가 (높을수록 좋다) ──────────────────────────
    #   회전일수(재고·매출채권)가 §8 의 원안이지만 그 계정은 '전체 재무제표'에만 있다.
    #   주요계정만으로도 답할 수 있는 같은 질문 = 자산회전율(매출/자산)의 전년 대비 변화.
    dio_c = safe_div(inv_c, cogs_c.where(cogs_c > 0)) * 365.0
    dio_p = safe_div(inv_p, cogs_p.where(cogs_p > 0)) * 365.0
    dso_c = safe_div(rec_c, rev_c.where(rev_c > 0)) * 365.0
    dso_p = safe_div(rec_p, rev_p.where(rev_p > 0)) * 365.0
    d["i_dio"], d["i_dso"] = dio_c, dso_c
    d["_cyc"] = dio_c + dso_c
    t_cycle = -((dio_c + dso_c) - (dio_p + dso_p))          # 회전일수 단축 = 개선
    at_c = safe_div(rev_c, ast_c.where(ast_c > 0))
    at_p = safe_div(rev_p, ast_p.where(ast_p > 0))
    d["asset_turn"] = at_c.astype("float32")
    t_asset = at_c - at_p                                    # 자산회전율 상승 = 개선
    t_chain = -(d["_cyc"] - lag4("_cyc"))
    d["i_turn"] = _pick_sensor("i_turn", [("재고+매출채권 회전일수 개선(전기비교)", t_cycle),
                                          ("자산회전율 개선(전기비교)", t_asset),
                                          ("회전일수 lag4(분기체인)", t_chain)])

    # ── §8-3  i_accr : 이익의 질 (높을수록 좋다 = 발생액이 낮다) ─────────────────────────
    #   ① 현금흐름표법 (Sloan 1996 이후 표준) — 영업CF 필요
    #   ② 대차대조표법 (Sloan 1996 원안) — 유동자산·유동부채만으로 성립. 주요계정으로 가능.
    #      ※ 현금 증감이 유동자산에 섞이므로 현금을 쌓는 기업이 다소 불리하게 잡힌다.
    #        이 한계는 채택 시 로그에 명시한다. 셀 내 랭크라 체계적 방향편향은 제한적이다.
    avg_ast = (ast_c + ast_p) / 2.0
    accr_cf = safe_div(ni_c - cfo_c, avg_ast.where(avg_ast > 0))
    d["accr_level"] = accr_cf.astype("float32")
    a_cf = -accr_cf
    dwc = (ca_c - ca_p) - (cl_c - cl_p)
    a_bs = -safe_div(dwc, ast_p.where(ast_p > 0))
    ni_t, cfo_t = col(d, "net_income_ttm"), col(d, "cfo_ttm")
    avg_t = (ast_c + lag4("assets")) / 2.0
    d["_accr"] = safe_div(ni_t - cfo_t, avg_t.where(avg_t > 0))
    a_chain = -(d["_accr"] - lag4("_accr"))
    d["i_accr"] = _pick_sensor("i_accr", [("발생액 수준 (순이익−영업CF)/평균자산", a_cf),
                                          ("운전자본 발생액 (Δ유동자산−Δ유동부채)/전기자산", a_bs),
                                          ("발생액 변화 lag4(분기체인)", a_chain)])

    # ── 방화벽 입력 ────────────────────────────────────────────────────────────────────
    #   영업CF 음수 연속 분기수. NaN 은 '음수 아님'으로 보아 연속을 끊는다(근거 없는 배제 금지).
    neg = (col(d, "cfo_q") < 0).astype("int8")
    blk = (neg == 0).groupby(d["corp_code"], observed=True).cumsum()
    d["op_cf_neg_streak"] = neg.groupby([d["corp_code"], blk], observed=True).cumsum().astype("float32")

    #   이자보상배율. 이자비용이 0/결측이면 '이자부담 없음' → NaN 으로 두고 방화벽에서
    #   AND 조건이라 자동으로 배제되지 않는다(fail-open 이 맞는 방향).
    d["interest_coverage"] = safe_div(opi, inte.where(inte > 0))

    #   자본잠식: 자본총계 < 자본금(부분잠식) 또는 자본총계 <= 0(완전잠식)
    d["capital_impairment"] = ((eq < cap) | (eq <= 0)).astype("float32")
    d.loc[eq.isna(), "capital_impairment"] = np.nan

    # ── 거부권 입력 ────────────────────────────────────────────────────────────────────
    #   V1 밀어내기: Δ매출>0 인데 Δ(재고+매출채권) 이 Δ매출의 1.5배를 넘는다
    #   ★ 전기 비교치로 단일 행에서 계산한다(분기 체인 불필요).
    d_rev = rev_c - rev_p
    d_wc = (inv_c - inv_p) + (rec_c - rec_p)
    ratio = safe_div(d_wc, d_rev.where(d_rev > 0))
    d["v1_pushout"] = ((d_rev > 0) & (ratio > V1_PUSH_RATIO)).astype("float32")
    d.loc[d_rev.isna() | d_wc.isna(), "v1_pushout"] = np.nan

    #   V2 는 코어 tidy_financials 가 v2_bad_3q 로 이미 만든다(3분기 연속 이익-현금 괴리).
    if "v2_bad_3q" not in d.columns:
        d["v2_bad_3q"] = np.nan

    d = d.drop(columns=[c for c in ("_cyc", "_accr") if c in d.columns])
    for _c2 in MICRO_QUARTERLY_COLS:                       # 스키마 계약
        if _c2 not in d.columns:
            d[_c2] = np.nan
    if SENSOR_DEFS_USED:
        LOG.table(SENSOR_DEFS_USED,
                  ["센서", "채택한 정의", "선택", "결측률", "후보별 결측률(분기행 기준)"],
                  ["l", "l", "c", "r", "l"], maxw=52,
                  title="센서 정의 선택 (§8) — 같은 질문에 답하는 가장 값싼 정의를 고른다")
        LOG.info("정의가 다르면 척도도 다르므로 셀 안에서 섞지 않습니다(i_sales 만 예외 — "
                 "두 정의 모두 '로그 매출증가율'로 척도가 같습니다). "
                 "여기서 채택된 정의가 곧 아래 센서 가용성표(C14-c)의 판정 대상입니다.")
    if _n_lag_bad:
        LOG.info(f"lag4 달력 게이트 — {_n_lag_bad:,}행({100*_n_lag_bad/max(len(d),1):.0f}%)은 "
                 f"4행 전이 '정확히 4분기 전'이 아니어서 분기체인 정의를 쓸 수 없습니다. "
                 f"분기보고서를 거르는 기업이며, 전기 비교치 기반 정의는 이 제약을 받지 "
                 f"않습니다(그래서 그쪽을 1순위로 둡니다).")
    n_ok = int(d["i_sales"].notna().sum())
    LOG.ok(f"L1 센서 계산 {len(d):,}분기행 · i_sales 유효 {n_ok:,}행 "
           f"({100*n_ok/max(len(d),1):.0f}%) — 전기 비교치 기반(분기 체인 의존 제거)")
    PIPE.io("OUT", "MEM", "micro_sensors_quarterly", d)
    return d


def infer_listing_dates(sec: pd.DataFrame, px_daily: pd.DataFrame) -> pd.DataFrame:
    """상장일이 비어 있는 종목을 '최초 거래일'로 보강한다.

    ★ 왜 필수인가 (실측된 사고) ───────────────────────────────────────────────────────
      상장일은 KIND(상장법인목록)에서 온다. KIND 가 막히거나 응답 형식이 바뀌면 상장일
      커버리지가 0% 가 된다. 그런데 Universe 는 '상장일도 폐지일도 없는' 종목을 근거 없는
      종목으로 보고 통째로 버린다 → 폐지일을 가진 상장폐지 종목만 유니버스에 남는다.
      즉 유니버스가 '죽은 회사들'로 뒤집힌다. 예외도 경고도 없이.
      실제로 이 코드의 무키·KIND차단 실행에서 상장일 보유 0%, 폐지일 보유 42% 가 나왔다.

    ★ 앵커 주의 ────────────────────────────────────────────────────────────────────────
      최초 거래일이 '가격 데이터의 시작'과 붙어 있으면, 그건 그 종목이 그 전부터 거래되고
      있었다는 뜻이지 그날 상장했다는 뜻이 아니다. 그대로 상장일로 쓰면 기존 상장사 전부가
      첫 250거래일 동안 시즈닝 미충족으로 유니버스에서 빠진다.
      → 그런 종목은 상장일을 충분히 과거로 확정한다(시즈닝 제약을 사실상 해제).
    """
    if px_daily is None or len(px_daily) == 0 or "code" not in px_daily.columns:
        return sec
    s = sec.copy()
    s["listing_date"] = as_ts_series(s["listing_date"])
    miss = s["listing_date"].isna()
    if not miss.any():
        return s
    first = (px_daily.assign(_d=as_ts_series(px_daily["date"]))
                     .groupby("code", observed=True)["_d"].min())
    px_start = first.min() if len(first) else None
    if px_start is None or pd.isna(px_start):
        return s
    mapped = s.loc[miss, "code"].astype(str).map(first)
    # 가격 시작과 30일 이내면 '그 전부터 거래 중' → 상장일을 과거로 확정
    pre_existing = mapped.notna() & ((mapped - px_start).dt.days <= 30)
    inferred = mapped.where(~pre_existing, px_start - pd.Timedelta(days=3650))
    s.loc[miss, "listing_date"] = inferred
    n_fix = int(inferred.notna().sum())
    n_pre = int(pre_existing.sum())
    if n_fix:
        LOG.ok(f"상장일 결측 {int(miss.sum()):,}종목 중 {n_fix:,}종목을 최초 거래일로 보강했습니다 "
               f"(그중 {n_pre:,}종목은 가격 데이터 시작 시점부터 거래 중이라 '기존 상장'으로 확정). "
               f"보강하지 않으면 유니버스가 상장폐지 종목만 남는 방향으로 붕괴합니다.")
    n_left = int(s["listing_date"].isna().sum())
    if n_left:
        LOG.info(f"상장일·거래이력이 모두 없는 {n_left:,}종목은 유니버스에서 제외됩니다 "
                 f"(근거가 전혀 없는 종목을 넣으면 그게 곧 미래누수입니다).")
    return s


def build_base_panel_micro(uni: "Universe", months: pd.DatetimeIndex,
                           price_m: pd.DataFrame) -> pd.DataFrame:
    """(code, month) 격자. 여기에 시총·재무·센서가 전부 as-of 로 붙는다."""
    rows = []
    for m in months:
        codes = uni.at(m)
        uni.audit_row("PIT유니버스", m, codes)
        rows.append(pd.DataFrame({"code": codes, "month": m}))
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["code", "month"])
    P["code"] = P["code"].astype(str)
    P = P.merge(price_m, on=["code", "month"], how="left")
    for m in months:
        sub = P[(P["month"] == m) & P["close"].notna()]
        uni.audit_row("가격보유", m, sub["code"].tolist())
    LOG.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {len(months)}개월) "
           f"— 메모리 {mem_mb(P):.0f}MB")
    PIPE.io("OUT", "MEM", "base_panel_micro", P)
    return P


def attach_fundamentals_micro(P: pd.DataFrame, sec: pd.DataFrame) -> pd.DataFrame:
    """재무·센서를 PIT as-of 로 결합. 여기가 미래누수의 최대 위험지점이다.

    ★ merge_asof 단일 패스(원칙 #1). 종목×시점 루프로 PIT.get() 을 부르지 않는다.
    """
    c2c = (sec.dropna(subset=["corp_code"]).drop_duplicates("code")
              .set_index("code")["corp_code"].astype(str).to_dict())
    P = P.copy()
    P["corp_code"] = P["code"].map(c2c)
    n_nocorp = int(P["corp_code"].isna().sum())
    if n_nocorp:
        LOG.info(f"corp_code 매핑이 없는 {n_nocorp:,}행(대개 상장폐지·비DART 법인)은 재무가 "
                 f"결측으로 남지만 '행은 유지'합니다 — 여기서 버리면 그게 생존자편향입니다(C2).")
    if PIT.has("dart_micro"):
        P = PIT.asof_join(P, "dart_micro", by="corp_code", left_time="month")
    # ★ 결합 '이후에' 채운다. 먼저 만들면 merge_asof 가 접미사를 붙여 실제 값을 흘려버린다.
    for c in FUNDAMENTAL_COLS:
        if c not in P.columns:
            P[c] = np.nan
    if not PIT.has("dart_micro"):
        LOG.warn("DART 재무가 없어 증거층(E)·방화벽의 재무 조항이 전부 결측입니다. "
                 "실행은 끝까지 가지만 이 전략의 본체가 비어 버립니다 — DART_API_KEY 를 넣으세요.")
    return P


# ── 셀 (C14) ────────────────────────────────────────────────────────────────────────────────
def build_cells_micro(P: pd.DataFrame, sec: pd.DataFrame, min_n: int = 20) -> pd.DataFrame:
    """셀 키 = (date, ind_major). ★size_bucket 을 쓰지 않는다(C14-a).

    U-MICRO 는 규모가 이미 균일해서 규모 버킷을 넣으면 셀당 종목 수가 붕괴한다.
    C14-b: 셀당 중앙값 종목 수가 min_n 미만이면 산업분류를 한 단계 상위로 올린다.
    """
    ind = sec.drop_duplicates("code").set_index("code")["industry"].astype(str).to_dict()
    p = P.copy()
    raw = p["code"].map(ind).fillna("미분류").astype(str).str.strip()
    raw = raw.where(raw.ne(""), "미분류")
    p["ind_major"] = raw
    # 상위 단위 폴백 사다리. 업종명이 텍스트라 앞 4자가 대분류 근사가 된다
    # (예: '전자부품 제조업' → '전자부품', '의료용 기기 제조업' → '의료용').
    p["ind_l1"] = raw.str.slice(0, 4)

    ym = p["month"].dt.strftime("%Y%m")
    cand_fine = ym + "|" + p["ind_major"]
    cand_coarse = ym + "|" + p["ind_l1"]

    # ★ 셀 크기는 '쓰이는 모집단'에서 재야 한다.
    #   셀 규칙은 전체 격자(3,500종목×120개월)에서 정하는데, 실제 랭크는 U-MICRO 부분집합
    #   (유동성 게이트까지 통과한 40% 남짓)에서 계산된다. 전체에서 25종목이던 셀이 쓰일 때는
    #   5종목이 되어 xsec_rank 가 NaN 을 내고 폴백 사다리가 조용히 'ALL'까지 내려간다.
    #   → 로그는 '업종 셀 사용'이라고 말하는데 실제로는 업종 중립화가 사라진 상태가 된다.
    _gate = (p["u_micro"].astype(bool) if "u_micro" in p.columns
             else pd.Series(True, index=p.index))

    def _med(cand: pd.Series) -> float:
        s = cand[_gate]
        return float(s.groupby(s, observed=True).transform("size").median()) if len(s) else 0.0

    med_fine = _med(cand_fine)
    _crule = str(globals().get("CELL_RULE", "auto")).lower()
    if _crule == "fine":
        p["cell"], p["cell_l2"] = cand_fine, cand_coarse
        LOG.info("셀 규칙: 업종 그대로 고정(CELL_RULE='fine') — 사전 지정.")
    elif _crule == "coarse":
        p["cell"], p["cell_l2"] = cand_coarse, ym + "|ALL"
        LOG.info("셀 규칙: 상위 업종 고정(CELL_RULE='coarse') — 사전 지정.")
    elif med_fine < min_n:
        med_coarse = _med(cand_coarse)
        LOG.warn(f"C14-b 발동 — 셀당 중앙값 종목수 {med_fine:.0f} < {min_n}. "
                 f"산업분류를 한 단계 상위로 올립니다(상위 기준 중앙값 {med_coarse:.0f}).")
        p["cell"] = cand_coarse
        p["cell_l2"] = ym + "|ALL"
    else:
        p["cell"] = cand_fine
        p["cell_l2"] = cand_coarse
    if _crule == "auto":
        LOG.debug("셀 규칙: 자동 선택 — 전 구간 셀 크기 중앙값 기준입니다(설정 단계 룩어헤드). "
                  "CELL_RULE 로 고정할 수 있습니다.")
    p["cell_l3"] = ym + "|ALL"

    # 셀 크기 판정도 U-MICRO 모집단 기준으로 한다(위 _med 와 같은 이유).
    _sz = p.loc[_gate].groupby("cell", observed=True)["code"].size()
    cnt = p["cell"].map(_sz).fillna(0)
    small = cnt < min_n
    n_small = int(small.sum())
    if n_small:
        p.loc[small, "cell"] = p.loc[small, "cell_l2"]
        _sz2 = p.loc[_gate].groupby("cell", observed=True)["code"].size()
        cnt2 = p["cell"].map(_sz2).fillna(0)
        still = cnt2 < min_n
        if still.any():
            p.loc[still, "cell"] = p.loc[still, "cell_l3"]
        LOG.info(f"셀 폴백: 1차 {n_small:,}행(상위 업종) / 2차 {int(still.sum()):,}행(전체). "
                 f"C14-b 요구대로 폴백을 로깅합니다.")
        PIPE.note(f"셀 폴백 {n_small:,}행")
    for c in ("cell", "cell_l2", "cell_l3"):
        p[c] = p[c].astype("category")
    _fin_sz = p.loc[_gate].groupby("cell", observed=True)["code"].size()
    LOG.debug(f"셀 구성: {p['cell'].nunique():,}개 · U-MICRO 기준 셀당 중앙값 "
              f"{float(_fin_sz.median()) if len(_fin_sz) else 0:.0f}종목 "
              f"(랭크가 실제로 계산되는 모집단 기준)")
    return p


def lag12(P: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """12개월 전 값을 '월 키 결합'으로 가져온다.

    ★ groupby(code).shift(12) 를 쓰지 않는 이유: 월 패널은 유니버스 진입/이탈로 구멍이
      뚫려 있어 shift(12) 가 구멍을 건너뛰고 2~3년 전 값을 '1년 전'으로 취급한다.
      월 키를 직접 12개월 밀어 결합하면 구멍이 있으면 그냥 결측이 된다(정직한 결측).
    """
    use = [c for c in cols if c in P.columns]
    if not use:
        return P
    S = P[["code", "month"] + use].copy()
    S["month"] = (as_ts_series(S["month"]) + pd.DateOffset(months=12)) + pd.offsets.MonthEnd(0)
    S = S.rename(columns={c: f"{c}_l12" for c in use})
    return P.merge(S, on=["code", "month"], how="left")


def attach_reflection(P: pd.DataFrame) -> pd.DataFrame:
    """U 층 — 반영도 d1_trailing = Δlog(시총) − Δlog(후행 12M 순이익).

    컨센서스 fwd EPS 시계열은 과거 복원이 불가능하므로(§16.2 한계) 후행 이익을 대리변수로 쓴다.
    의미: 이익은 늘었는데 시총이 아직 안 따라왔다 → d1 < 0 → '아직 반영되지 않음' → 매력적.
    청산 게이트(§10)의 'ΔlogM 이 ΔlogE 수준까지 확장' 은 d1_trailing ≥ 0 이다.
    ★ 총액(시총)과 총액(순이익)을 짝지어 희석 효과가 자동으로 상쇄되게 한다.
    """
    P = lag12(P, ["mcap", "net_income_ttm", "close"])
    m1, m0 = col(P, "mcap"), col(P, "mcap_l12")
    e1, e0 = col(P, "net_income_ttm"), col(P, "net_income_ttm_l12")
    dlogM = np.log(m1.where(m1 > 0)) - np.log(m0.where(m0 > 0))
    dlogE = np.log(e1.where(e1 > 0)) - np.log(e0.where(e0 > 0))
    P["dlogM"] = dlogM.astype("float32")
    P["dlogE"] = dlogE.astype("float32")
    P["d1_trailing"] = (dlogM - dlogE).astype("float32")
    # 랭크는 '반영이 덜 된 쪽'이 높아야 하므로 부호를 뒤집어 둔다.
    P["u_underreflect"] = (-P["d1_trailing"]).astype("float32")
    n = int(P["d1_trailing"].notna().sum())
    LOG.info(f"반영도(U층) 산출 {n:,}행 "
             f"({100*n/max(len(P),1):.0f}%) — 적자기업은 ΔlogE 산출 불가로 결측입니다. "
             f"결측률이 {100*RESEARCH_MAX_MISSING_RATE:.0f}% 를 넘으면 C14-c 로 U층이 자동 제외됩니다.")
    return P


def apply_umicro_gates(P: pd.DataFrame, uni: "Universe") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """U-MICRO 게이트 적용 + §6 감쇠 감사표.

    ★ C13-a: 시총·유동성 랭크는 매 시점의 '당시' 값으로 재산출된 것을 쓴다(build_mcap_panel).
    ★ 자동 전환: 2016 과 2026 의 U-MICRO 종목 수 차이가 20% 를 넘으면 절대 랭크(1400~)를
      분위 기준(상위 55% 밖)으로 교체하고 재측정한다. 상장사 수가 10년간 35% 늘었기 때문에
      절대 랭크를 고정하면 유니버스가 시간에 따라 체계적으로 커지거나 작아진다.
    """
    # ★ 시총 미상 종목을 '유니버스 밖'으로 조용히 떨어뜨리면 안 된다.
    #   시총이 결측인 종목은 대개 상장폐지된 종목이다(현재 상장목록에 없으니 주식수를
    #   못 얻는다). 그대로 두면 U-MICRO 가 '살아남은 종목'만으로 구성되어 C2 가 무너진다.
    #   → 거래대금 순위를 규모 대리변수로 써서 랭크를 채운다. 소형주 구간에서 시총과
    #     거래대금은 강하게 함께 움직이므로 근사로 성립하며, 몇 행이 그렇게 채워졌는지
    #     반드시 표로 보고한다.
    _pctl_mcap = P.groupby("month", observed=True)["mcap"].rank(ascending=False, pct=True) \
        if "mcap" in P.columns else pd.Series(np.nan, index=P.index)
    _pctl_adv = P.groupby("month", observed=True)["adv20"].rank(ascending=False, pct=True) \
        if "adv20" in P.columns else pd.Series(np.nan, index=P.index)
    _proxy_used = _pctl_mcap.isna() & _pctl_adv.notna() & P["close"].notna()
    P = P.copy()
    P["mcap_pctl_eff"] = _pctl_mcap.where(_pctl_mcap.notna(), _pctl_adv)
    n_proxy = int(_proxy_used.sum())
    if n_proxy:
        LOG.warn(f"시총 미상 {n_proxy:,}종목월은 거래대금 순위를 규모 대리변수로 사용합니다 "
                 f"(전체의 {100*n_proxy/max(len(P),1):.1f}%). 대부분 상장폐지 종목이며, "
                 f"여기서 버리면 유니버스가 생존자만 남습니다(C2).")

    def gates(use_pctl: bool) -> pd.Series:
        if use_pctl:
            band = col(P, "mcap_pctl_eff") >= UMICRO_PCTL_MIN
        else:
            # 절대 랭크는 시총을 아는 종목에만 적용되고, 대리변수 행은 분위 기준으로 판정한다.
            band = (col(P, "mcap_rank") > UMICRO_MCAP_RANK_MIN)
            band = band.where(col(P, "mcap_rank").notna(),
                              col(P, "mcap_pctl_eff") >= UMICRO_PCTL_MIN)
        return band.fillna(False)

    liq = (col(P, "adv20") >= UMICRO_MIN_ADV_KRW).fillna(False)
    has_px = P["close"].notna()

    # ── 밴드 규칙 선택 ────────────────────────────────────────────────────────────────
    #   절대 랭크(>1400)는 '상장사가 1400개보다 훨씬 많다'는 전제 위에서만 뜻이 있다.
    #   시총 커버리지가 부분적이면 랭크가 1400 까지 가지도 않아 U-MICRO 가 통째로 빈다.
    #   ★ 에러 없이, 표에는 0 만 찍히는 조용한 붕괴다 — 여기서 먼저 판정하고 전환한다.
    n_ranked = (P.loc[has_px].groupby("month", observed=True)["mcap_rank"]
                 .apply(lambda s: s.notna().sum()))
    med_ranked = float(n_ranked.median()) if len(n_ranked) else 0.0
    band_abs = gates(False)
    med_abs = float((band_abs & liq & has_px).groupby(P["month"], observed=True).sum().median()) \
        if len(P) else 0.0
    rule = str(globals().get("UMICRO_BAND_RULE", "auto")).lower()
    if rule == "rank":
        use_pctl = False
        LOG.info("밴드 규칙: 절대 랭크 고정(UMICRO_BAND_RULE='rank') — 사전 지정이므로 "
                 "규칙 선택에 미래 정보가 들어가지 않습니다.")
    elif rule == "pctl":
        use_pctl = True
        LOG.info("밴드 규칙: 분위 고정(UMICRO_BAND_RULE='pctl') — 사전 지정.")
    else:
        use_pctl = med_abs < 50
        LOG.info("밴드 규칙: 자동 선택(UMICRO_BAND_RULE='auto'). ★규칙 선택에 전 구간 통계를 "
                 "쓰므로 '설정 단계의 룩어헤드'입니다(신호값이 새는 것은 아닙니다). "
                 "엄밀한 재현이 필요하면 'rank' 또는 'pctl' 로 고정하세요.")
    if use_pctl and rule == "auto" and med_abs < 50:
        LOG.warn(f"절대 랭크 기준(>{UMICRO_MCAP_RANK_MIN})으로는 U-MICRO 가 월평균 "
                 f"{med_abs:,.0f}종목뿐입니다 (시총 랭크 산출 종목이 월 {med_ranked:,.0f}개). "
                 f"분위 기준(상위 {100*UMICRO_PCTL_MIN:.0f}% 밖)으로 전환합니다 — "
                 f"절대 랭크는 상장사 수가 충분할 때만 의미가 있습니다.")
    band = gates(use_pctl)
    u = band & liq & has_px

    yr = P["month"].dt.year
    def _cnt(mask: pd.Series, y: int) -> float:
        s = P.loc[mask & (yr == y), ["month", "code"]]
        return float(s.groupby("month", observed=True)["code"].size().mean()) if len(s) else 0.0

    y0, y1 = int(yr.min()) if len(P) else 0, int(yr.max()) if len(P) else 0
    n0, n1 = _cnt(u, y0), _cnt(u, y1)
    gap = abs(n1 - n0) / max(n0, n1, 1.0)
    if gap > ATTRITION_GAP_TOL and not use_pctl:
        LOG.warn(f"§6 판정 — {y0}년({n0:,.0f}종목)과 {y1}년({n1:,.0f}종목)의 U-MICRO 종목 수 차이가 "
                 f"{100*gap:.0f}% 로 허용치({100*ATTRITION_GAP_TOL:.0f}%)를 넘습니다. "
                 f"절대 랭크(>{UMICRO_MCAP_RANK_MIN})를 분위 기준(상위 {100*UMICRO_PCTL_MIN:.0f}% 밖)"
                 f"으로 교체하고 재측정합니다.")
        use_pctl = True
        band = gates(True)
        u = band & liq & has_px
        n0, n1 = _cnt(u, y0), _cnt(u, y1)
        LOG.ok(f"재측정 후 — {y0}년 {n0:,.0f}종목 · {y1}년 {n1:,.0f}종목 "
               f"(차이 {100*abs(n1-n0)/max(n0, n1, 1.0):.0f}%)")

    P = P.copy()
    P["g_band"], P["g_liq"] = band, liq
    P["u_micro"] = u
    P["umicro_rule"] = "분위" if use_pctl else "절대랭크"

    # 감쇠 감사표 (연도별 월평균)
    rows = []
    for y in range(y0, y1 + 1):
        m = (yr == y)
        if not m.any():
            continue
        rows.append([str(y),
                     f"{_cnt(m, y):,.0f}",
                     f"{_cnt(m & has_px, y):,.0f}",
                     f"{_cnt(m & has_px & band, y):,.0f}",
                     f"{_cnt(m & has_px & band & liq, y):,.0f}",
                     f"{_cnt(u, y):,.0f}"])
    A = pd.DataFrame(rows, columns=["년도", "PIT유니버스", "가격보유", "시총밴드", "유동성", "U-MICRO"])
    LOG.table(A.values.tolist(), list(A.columns), ["c", "r", "r", "r", "r", "r"],
              title=f"유니버스 감쇠 감사 (§6) — 기준: {P['umicro_rule'].iloc[0] if len(P) else '-'} "
                    f"· 어느 게이트에서 표본이 붕괴하는지")
    LOG.info("PIT유니버스 = 상장폐지·상장250일 시즈닝이 이미 반영된 집합입니다(C2). "
             "'전체상장'과의 차이는 시즈닝 미충족 신규상장분입니다.")
    for m in sorted(P.loc[P["u_micro"], "month"].unique()):
        uni.audit_row("U-MICRO", m, P.loc[P["u_micro"] & (P["month"] == m), "code"].tolist())
    n_u = int(P["u_micro"].sum())
    LOG.ok(f"U-MICRO 유니버스 {n_u:,}종목월 (월평균 "
           f"{n_u/max(P['month'].nunique(), 1):,.0f}종목)")
    return P, A


def attach_valuation(P: pd.DataFrame) -> pd.DataFrame:
    """PBR · PER. 방화벽의 딥밸류 조항(§7)이 쓴다.

    per_positive: 적자(순이익<=0) 기업은 '싸다'가 아니라 '판단 불가'다. 셀 내 최하위로
    보내야 딥밸류 랭크에서 배제되는 방향이 된다 → +inf 로 둔다(랭크 오름차순에서 꼴찌).
    """
    P = P.copy()
    mcap = col(P, "mcap")
    eq = col(P, "equity")
    ni = col(P, "net_income_ttm")
    # 표시용 배수 (해석표·진단카드에서 읽는다)
    P["pbr"] = safe_div(mcap, eq.where(eq > 0))
    P["per_positive"] = safe_div(mcap, ni.where(ni > 0))

    # ★ 랭킹은 '배수'가 아니라 '수익률(역수)' 로 한다. ────────────────────────────────
    #   배수(PER)는 적자기업에서 정의되지 않아 결측·무한대 같은 센티넬이 필요한데,
    #   xsec_rank_pct 는 ±inf 를 랭크 전에 NaN 으로 바꾸고 셀의 유효 관측수가 min_n
    #   미만이면 **셀 전체**를 NaN 으로 만든다. U-MICRO 는 적자기업이 흔해서
    #   "적자가 많다"는 이유만으로 멀쩡한 흑자기업까지 밸류 판정 불가가 되고,
    #   방화벽의 딥밸류 조항이 그 셀 전원을 배제해 버린다.
    #   → 이익수익률(E/P)·순자산수익률(B/P)은 적자·자본잠식에서 자연스럽게 음수가 되어
    #     센티넬 없이 '비싼 쪽'으로 정렬된다. 결측도 최소화된다.
    P["ep"] = safe_div(ni, mcap.where(mcap > 0))       # 높을수록 싸다
    P["bp"] = safe_div(eq, mcap.where(mcap > 0))       # 높을수록 싸다
    n_neg = int(((ni <= 0) & ni.notna()).sum())
    LOG.debug(f"밸류 지표 — PBR 유효 {int(P['pbr'].notna().sum()):,}행 · "
              f"적자기업 {n_neg:,}행은 PER 최하위 처리")
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L2  S1_FIREWALL (§7) · 거부권 (§9) · 셀 정규화 · TP 조립 · 신호 합성                      ║
# ║                                                                                          ║
# ║  이 전략의 본체는 방화벽이다. 증거층(E)은 2개 TP 로 최소화한다 —                           ║
# ║  U-MICRO 는 컨센서스·수급 데이터가 구조적으로 얇아 신호를 5~6개 욱여넣으면                 ║
# ║  "빈 축이 없을 것"이라는 하한선 조건에서 유니버스가 붕괴하기 때문이다.                     ║
# ║                                                                                          ║
# ║  ★ 원칙 2: TP 는 clip(z,0) × clip(z,0). 절대 z × z 가 아니다.                              ║
# ║    z×z 는 '매출 급감 + 회전 악화'(둘 다 음수)에 최고점을 준다 — 부호 버그다.                ║
# ║  ★ 원칙 3: 셀 정규화는 groupby().rank(pct=True) + transform("size"). groupby.apply 금지.  ║
# ║  ★ 원칙 7: 거부권은 이진·곱·상쇄 불가. 연속화하면 방화벽이 새는 통로가 생긴다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CELL_MICRO = ["date", "ind_major"]        # C14-a. size_bucket 없음 (문서화용 상수)
MICRO_MIN_CELL_N = 20                     # C14-b

E_SENSORS = ["i_sales", "i_turn", "i_accr"]
TP_DEFS = [("TP_I2", "i_sales", "i_turn"), ("TP_I4", "i_sales", "i_accr")]


def cell_rank_micro(P: pd.DataFrame, name_or_series, min_n: int = MICRO_MIN_CELL_N) -> pd.Series:
    """셀 내 백분위 랭크 [0,1]. 셀이 작으면 상위 업종 → 전체 시장 순으로 폴백한다(C14-b).

    구현은 groupby().rank(pct=True) + transform("size") 다 (원칙 3).
    groupby.apply 는 셀 수만큼 파이썬 호출이 발생해 수십 배 느리다.
    """
    return xsec_rank_pct_l(P, name_or_series, min_n=min_n)


def _cached_cell_rank(P: pd.DataFrame, name: str, cache: dict) -> pd.Series:
    """같은 컬럼의 셀 랭크를 한 번만 계산한다.

    i_sales 는 TP_I2·TP_I4 두 쌍의 공통 축이라 매번 두 번 계산됐고, value_rank 는
    조항 마스크와 s1_firewall 에서 최대 15회까지 중복 계산됐다. 랭크 1회는 셀 사다리
    3단계 × groupby-rank 이므로 중복이 그대로 벽시계 시간이 된다.
    """
    if name not in cache:
        cache[name] = cell_rank_micro(P, name)
    return cache[name]


def tp_micro(P: pd.DataFrame, a: str, b: str, _cache: Optional[dict] = None) -> pd.Series:
    """트레이드오프 쌍 = clip(랭크z, 0) × clip(랭크z, 0).

    랭크 백분위에서 0.5 를 빼 [-0.5, +0.5] 의 z 대용을 만들고, 음수는 0 으로 자른다.
    → '개선이 있었고, 그 대가도 치르지 않았다'는 사분면에서만 점수가 난다.
    ★ za*zb (부호 그대로 곱하기) 금지 — 저-저 사분면이 최고점을 받는다.
    한쪽이 결측이면 결과도 결측이다(0 으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다).
    """
    _cache = {} if _cache is None else _cache
    ra = _cached_cell_rank(P, a, _cache)
    rb = _cached_cell_rank(P, b, _cache)
    za = ra - 0.5
    zb = rb - 0.5
    out = np.maximum(za, 0.0) * np.maximum(zb, 0.0)
    return pd.Series(out, index=P.index).where(ra.notna() & rb.notna()).astype("float32")


def value_rank_micro(P: pd.DataFrame) -> pd.Series:
    """딥밸류 랭크. 0 에 가까울수록 싸다 (방화벽은 하위 30% 만 통과시킨다).

    ★ 이익수익률(E/P)·순자산수익률(B/P)의 셀 내 랭크를 평균한 뒤 뒤집는다.
      배수(PER/PBR)로 랭크하면 적자·자본잠식에서 정의되지 않아 센티넬이 필요하고,
      그 센티넬이 셀의 유효 관측수를 무너뜨려 셀 전체를 '판정 불가'로 만든다.
      수익률 형태는 적자·자본잠식이 자연스럽게 음수가 되어 '비싼 쪽'으로 정렬된다.
    ★ 한쪽(E/P 또는 B/P)만 관측되면 그 한쪽으로 판정한다. 둘 다 없을 때만 결측이다.
    """
    P = P.copy()
    P["_r_ep"] = cell_rank_micro(P, "ep")
    P["_r_bp"] = cell_rank_micro(P, "bp")
    r = nanmean_cols(P, ["_r_ep", "_r_bp"])            # 높을수록 싸다
    return (1.0 - pd.to_numeric(r, errors="coerce")).astype("float32")


def sensor_availability(P: pd.DataFrame) -> Tuple[List[str], pd.DataFrame]:
    """C14-c/d — 센서 결측률 > 25% 면 증거층에서 자동 제외한다. 0 으로 채우지 않는다.

    반환: (활성 TP 목록, 진단표)
    ★ 결측률은 'U-MICRO 이면서 가격이 있는 행' 기준으로 잰다. 전체 패널로 재면
      애초에 유니버스 밖인 행까지 분모에 들어가 결측률이 부풀려진다.
    """
    base = P[P.get("u_micro", pd.Series(True, index=P.index)).astype(bool) &
             P["close"].notna()] if "close" in P.columns else P
    if len(base) == 0:
        base = P
    rows, dead = [], set()
    for s in E_SENSORS:
        miss = float(col(base, s).isna().mean()) if len(base) else 1.0
        ok = miss <= RESEARCH_MAX_MISSING_RATE
        if not ok:
            dead.add(s)
        rows.append([s, f"{100*miss:.1f}%", f"{100*RESEARCH_MAX_MISSING_RATE:.0f}%",
                     "활성" if ok else "제외(C14-c)"])
    active_tp = [(tid, a, b) for tid, a, b in TP_DEFS if a not in dead and b not in dead]
    rows.append(["활성 TP", f"{len(active_tp)}개", "2개 이상",
                 "정상" if len(active_tp) >= 2 else "중단(C14-d)"])
    T = pd.DataFrame(rows, columns=["센서", "결측률", "임계", "판정"])
    LOG.table(T.values.tolist(), list(T.columns), ["l", "r", "r", "c"],
              title="센서 가용성 (C14-c/d) — 결측을 0 으로 채우지 않고 축을 통째로 뺀다")
    LOG.info("※ i_sales 는 TP_I2·TP_I4 두 쌍의 공통 축입니다. i_sales 가 제외되면 활성 TP 는 "
             "구조적으로 0개가 되어 반드시 중단됩니다(§8 의 TP 정의가 그렇게 생겼습니다). "
             "위 '센서 정의 선택' 표에서 어떤 정의가 채택됐는지 함께 보십시오.")
    if len(active_tp) < 2:
        _msg = (f"활성 TP 가 {len(active_tp)}개로 2개 미만입니다(C14-d). 증거층을 구성할 수 없습니다. "
                f"임계를 낮춰 통과시키지 마십시오 — 결측률이 높다는 것은 U-MICRO 구간에서 해당 "
                f"재무항목이 실제로 공시되지 않는다는 뜻이고, 0 으로 채우면 없는 근거를 만듭니다.")
        # ★ 합성 스모크에서는 죽이지 않는다(형식 확인이 목적). 실데이터에서만 발동한다.
        if STOP_ON_KILL_CRITERIA and bool(globals().get("_KILL_ARMED", True)):
            raise KillCriteria(_msg)
        LOG.warn("[킬 비무장] " + _msg + " — 예행연습이므로 전 TP 를 형식상 활성으로 두고 "
                 "출력 경로만 확인합니다.")
        return [t[0] for t in TP_DEFS], T
    return [t[0] for t in active_tp], T


def build_evidence(P: pd.DataFrame, active_tp: Sequence[str]) -> pd.DataFrame:
    """TP 조립 → 증거층 E. §9."""
    P = P.copy()
    made = []
    _rc: dict = {}                      # i_sales 는 두 TP 의 공통 축 — 한 번만 랭크한다
    for tid, a, b in TP_DEFS:
        if tid not in active_tp:
            P[tid] = np.nan
            continue
        P[tid] = tp_micro(P, a, b, _cache=_rc)
        made.append(tid)
    P["E_micro"] = nanmean_cols(P, made) if made else np.nan

    # ── U 층 (§9) ──────────────────────────────────────────────────────────────────────
    #   컨센서스가 없으므로 후행 이익 기반 반영도만 쓴다. 높을수록 '아직 반영 안 됨'.
    P["u_base_rank"] = cell_rank_micro(P, "u_underreflect")
    u_cols = ["u_base_rank"]
    miss_u = float(col(P, "u_underreflect").isna().mean()) if len(P) else 1.0
    if miss_u > RESEARCH_MAX_MISSING_RATE:
        LOG.warn(f"U층 기본신호 결측률 {100*miss_u:.0f}% > {100*RESEARCH_MAX_MISSING_RATE:.0f}% — "
                 f"C14-c 에 따라 U층을 중립(1.0)으로 두고 D 구성은 사실상 C 와 같아집니다. "
                 f"이 사실은 R2-M 표에 그대로 드러납니다.")
        u_cols = []

    # 애널리스트 목표주가 리비전(같은 애널리스트 기준)이 충분히 커버되면 U층에 더한다.
    #   ★ 커버리지가 얇으면 자동 제외한다(C14-c). U-MICRO 에서는 대개 제외된다 — 정상이다.
    if "u_revision_rank" in P.columns:
        miss_r = float(col(P, "u_revision_rank").isna().mean())
        if miss_r <= RESEARCH_MAX_MISSING_RATE:
            u_cols.append("u_revision_rank")
            LOG.ok(f"애널리스트 목표주가 리비전을 U층에 결합합니다 (결측률 {100*miss_r:.0f}%).")
        else:
            LOG.info(f"애널리스트 리비전 결측률 {100*miss_r:.0f}% > "
                     f"{100*RESEARCH_MAX_MISSING_RATE:.0f}% — C14-c 로 U층에서 제외합니다. "
                     f"U-MICRO 는 커버리지가 구조적으로 얇아 통상적인 결과입니다.")
    P["U_micro"] = nanmean_cols(P, u_cols) if u_cols else pd.Series(1.0, index=P.index)
    LOG.ok(f"증거층 조립 — 활성 TP {made} · E 유효 {int(P['E_micro'].notna().sum()):,}행 · "
           f"U 유효 {int(P['U_micro'].notna().sum()):,}행")
    return P


# ── S1_FIREWALL (§7) ────────────────────────────────────────────────────────────────────────
FW_CLAUSES = ["capital", "watchlist", "audit", "halt", "weak_cf", "liquidity", "deepvalue"]


def firewall_clause_masks(P: pd.DataFrame, active: Dict[str, bool]
                          ) -> "OrderedDict[str, Tuple[str, Optional[pd.Series], bool, str]]":
    """조항 → (표시명, 위반 마스크, 활성여부, 비고).

    ★ '데이터가 없어서 판단 불가'와 '판단해서 통과'를 구분한다.
      전자를 통과로 처리하면 방화벽이 새고, 배제로 처리하면 유니버스가 근거 없이 붕괴한다.
      → 소스 자체가 없으면 조항을 통째로 비활성화하고(K6) 표에 남긴다.
        소스는 있는데 특정 종목만 결측이면 그 종목은 '위반 아님'으로 둔다(근거 없는 배제 금지).
    """
    ci = col(P, "capital_impairment")
    wl, al = col(P, "is_watchlist"), col(P, "is_alert")
    ab = col(P, "audit_bad")
    th = col(P, "is_trading_halted")
    streak, icov = col(P, "op_cf_neg_streak"), col(P, "interest_coverage")
    adv = col(P, "adv20")
    # ★ 이 함수는 R5-M 절제분석에서 조항 수만큼(최대 15회) 다시 불린다. 매번 E/P·B/P 의
    #   셀 사다리 랭크를 새로 돌면 U-MICRO 패널 전체를 수십 번 훑게 된다 → 패널에 캐시한다.
    if "_value_rank" in P.columns:
        vr = pd.to_numeric(P["_value_rank"], errors="coerce")
    else:
        vr = value_rank_micro(P)
        try:
            P["_value_rank"] = vr        # 호출자 프레임에 남겨 재계산을 막는다
        except Exception:
            pass
    # ★ 딥밸류 조항은 '밸류 판정 불가(vr 결측)'도 배제한다 — 정책으로는 방어적이지만,
    #   vr 결측의 대부분은 **시총 미상**이고 시총 미상의 대부분은 상장폐지 종목이다.
    #   그러면 방화벽을 켠 구성(A·C·D)만 폐지 종목을 구조적으로 못 사고, 끈 구성(B)과
    #   동일가중 벤치마크만 -100% 를 먹는다 → R2-M ①('방화벽이 알파인가 손실회피인가')이
    #   전략이 아니라 **데이터 커버리지 격차**를 측정하게 된다. 그래서 비율을 표에 남긴다.
    _vr_na = float(vr.isna().mean()) if len(vr) else 0.0
    if _vr_na > 0.05:
        LOG.warn(f"밸류 판정 불가(시총·재무 결측) {100*_vr_na:.1f}% — 딥밸류 조항이 이 행들을 "
                 f"배제합니다. 이 비율이 크면 A/C/D 만 상장폐지 종목을 피하게 되어 "
                 f"R2-M ① 판정이 전략이 아니라 커버리지 격차를 측정합니다. "
                 f"KRX_OPENAPI_KEY 를 넣어 시총 커버리지를 올리면 사라지는 문제입니다.")

    C: "OrderedDict[str, Tuple[str, Optional[pd.Series], bool, str]]" = OrderedDict()
    C["capital"] = ("자본잠식 (자본총계<자본금 또는 ≤0)", ci > 0, bool(ci.notna().any()),
                    "재무 결측 종목은 '위반 아님'")
    C["watchlist"] = ("관리종목·투자주의환기", (wl > 0) | (al > 0),
                      bool(active.get("watchlist") or active.get("alert")), "")
    C["audit"] = ("감사의견 비적정", ab > 0, bool(active.get("audit")),
                  "적정 여부를 직접 확인할 API 가 없어 '비적정 증거'로만 배제")
    C["halt"] = ("매매거래정지", th > 0,
                 bool(active.get("halt")) or bool(th.notna().any()), "")
    C["weak_cf"] = (f"영업CF {FW_OPCF_NEG_STREAK}분기 연속 음수 ∧ 이자보상배율<{FW_ICOV_MIN:g}",
                    (streak >= FW_OPCF_NEG_STREAK) & (icov < FW_ICOV_MIN),
                    bool(streak.notna().any()), "AND 조건 — 한쪽만으론 배제하지 않는다")
    C["liquidity"] = (f"20일 평균거래대금 < {UMICRO_MIN_ADV_KRW:,.0f}원",
                      adv < UMICRO_MIN_ADV_KRW, bool(adv.notna().any()), "")
    C["deepvalue"] = (f"딥밸류 아님 (PBR·PER 결합랭크 > {FW_VALUE_RANK_MAX:.0%})",
                      (vr > FW_VALUE_RANK_MAX) | (~vr.notna()), bool(vr.notna().any()),
                      "밸류 랭크 산출 불가 종목도 배제 — 딥밸류 '확인'이 진입 조건")
    return C


def s1_firewall(P: pd.DataFrame, active: Dict[str, bool],
                skip: Sequence[str] = (), quiet: bool = False
                ) -> Tuple[pd.Series, pd.DataFrame]:
    """방화벽 통과 = 1. 하나라도 위반하면 0.  skip 에 넣은 조항은 절제(R5-M)용으로 제외한다."""
    n = len(P)
    ok = pd.Series(True, index=P.index)
    rows = []
    for key, (name, bad, enabled, note) in firewall_clause_masks(P, active).items():
        if key in skip:
            rows.append([name, "절제됨", "-", "-", "R5-M 절제 검사"])
            continue
        if not enabled or bad is None:
            rows.append([name, "비활성", "-", "-", note or "소스 없음 → K6 규칙으로 조항 제외"])
            continue
        b = bad.fillna(False).astype(bool)
        before = int(ok.sum())
        ok &= ~b
        rows.append([name, "활성", f"{int(b.sum()):,}", f"{before-int(ok.sum()):,}", note])

    fw = ok.astype("int8")
    rows.append(["── 최종 통과", "", f"{n - int(fw.sum()):,}", f"{int(fw.sum()):,}",
                 f"통과율 {100*fw.mean() if n else 0:.1f}%"])
    T = pd.DataFrame(rows, columns=["방화벽 조항", "상태", "위반 행수", "신규 배제", "비고"])
    if not quiet:
        LOG.table(T.values.tolist(), list(T.columns), ["l", "c", "r", "r", "l"],
                  title="S1_FIREWALL 조항별 감쇠 (§7) — 어느 조항이 실제로 일하는지")
    return fw, T


# ── 거부권 (§9 · C6: 이진·곱·상쇄 불가) ────────────────────────────────────────────────────
def apply_vetoes_micro(P: pd.DataFrame, dis: Optional[pd.DataFrame]) -> pd.DataFrame:
    """V1/V2/V3/V6 를 이진 플래그로 만들고 곱한다. 연속값으로 만들지 않는다."""
    P = P.copy()

    # V1 — 밀어내기 (분기 프레임에서 이미 계산되어 as-of 로 실려 왔다)
    P["V1"] = np.where(col(P, "v1_pushout") > 0, 0.0, 1.0)
    # V2 — 이익-현금 괴리 3분기 연속
    P["V2"] = np.where(col(P, "v2_bad_3q") > 0, 0.0, 1.0)
    # V3 — 90일 내 대규모 희석성 조달
    P["V3"] = _veto_dilution(P, dis)
    # V6 — 유동성 하한 또는 거래정지
    thal = col(P, "is_trading_halted") > 0
    P["V6"] = np.where((col(P, "adv20") < UMICRO_MIN_ADV_KRW) | thal, 0.0, 1.0)

    P["VETO"] = P["V1"] * P["V2"] * P["V3"] * P["V6"]
    rows = []
    for v, desc in [("V1", "밀어내기 (Δ재고+Δ매출채권)/Δ매출>1.5"),
                    ("V2", "순이익>0 ∧ 영업CF<0.5×순이익 3분기 연속"),
                    ("V3", f"{V3_DILUTION_DAYS}일 내 희석성 조달(유증/CB/BW)"),
                    ("V6", "유동성 하한 미달 또는 거래정지")]:
        n_bad = int((P[v] == 0).sum())
        rows.append([v, desc, f"{n_bad:,}", f"{100*n_bad/max(len(P),1):.2f}%"])
    rows.append(["VETO", "전 거부권 곱 (상쇄 불가)", f"{int((P['VETO'] == 0).sum()):,}",
                 f"{100*(P['VETO'] == 0).mean() if len(P) else 0:.2f}%"])
    LOG.table(rows, ["ID", "조건", "발동 행수", "비중"], ["c", "l", "r", "r"],
              title="거부권 발동 현황 (C6 — 이진·곱·상쇄 불가)")
    return P


def _veto_dilution(P: pd.DataFrame, dis: Optional[pd.DataFrame]) -> np.ndarray:
    """희석성 조달 거부권. 공시 기반이 1순위, 상장주식수 급증이 보강이다."""
    out = np.ones(len(P), dtype="float64")
    used = []

    if dis is not None and len(dis) and "event" in dis.columns:
        ev = dis[dis["event"].isin(["rights_issue", "cb_issue", "bw_issue"])].copy()
        if len(ev) and "corp_code" in ev.columns and "corp_code" in P.columns:
            ev["corp_code"] = ev["corp_code"].astype(str)
            ev = (ev.dropna(subset=["rcept_dt", "corp_code"])
                    .sort_values("rcept_dt", kind="stable")[["corp_code", "rcept_dt"]]
                    .rename(columns={"rcept_dt": "last_dilution"}))
            ev["_kd"] = ev["last_dilution"]
            L = P[["corp_code", "month"]].copy()
            L["corp_code"] = L["corp_code"].astype(str)
            L["_ord"] = np.arange(len(L))
            Lv = L.dropna(subset=["month"]).sort_values("month", kind="stable")
            try:
                M = pd.merge_asof(Lv, ev, left_on="month", right_on="_kd",
                                  by="corp_code", direction="backward")
                last = M.set_index("_ord")["last_dilution"].reindex(L["_ord"]).to_numpy()
                days = (P["month"].to_numpy().astype("datetime64[ns]")
                        - last.astype("datetime64[ns]")) / np.timedelta64(1, "D")
                hit = np.isfinite(days) & (days >= 0) & (days <= V3_DILUTION_DAYS)
                out = np.where(hit, 0.0, out)
                used.append(f"공시 {int(hit.sum()):,}행")
            except Exception as e:                                       # noqa
                LOG.warn(f"V3 희석성 조달 as-of 결합 실패({type(e).__name__}) — "
                         f"상장주식수 급증 보강만 사용합니다.")

    # 보강: 상장주식수 12개월 증가율이 임계를 넘으면 '대규모 희석'으로 본다.
    #       공시목록이 없거나(키 미입력) 공시명이 규정과 달라 못 잡힌 경우를 메운다.
    #       ★ shares_p12 는 전체 패널에서 미리 결합해 둔다(build_panel). 여기서 U-MICRO
    #         부분집합만으로 12개월 전 값을 찾으면 과거에 유니버스 밖이던 종목이 전부 결측이 된다.
    if "shares" in P.columns and "shares_p12" in P.columns:
        s_now, s_p12 = col(P, "shares"), col(P, "shares_p12")
        gr = safe_div(s_now - s_p12, s_p12.where(s_p12 > 0))
        hit2 = (gr > max(V3_DILUTION_PCT * 2, 0.20)).fillna(False).to_numpy()
        out = np.where(hit2, 0.0, out)
        used.append(f"주식수급증 {int(hit2.sum()):,}행")

    if used:
        LOG.debug(f"V3 희석성 조달 — {' · '.join(used)}")
    return out


# ── 신호 합성 (§9) ──────────────────────────────────────────────────────────────────────────
#   Signal = rank_pct(E) × rank_pct(U) × s1_firewall × V1 × V2 × V3 × V6
#   R2-M 4방 비교를 위해 구성요소를 켜고 끌 수 있게 만든다.
VARIANTS: Dict[str, Dict[str, bool]] = {
    "A": {"E": False, "U": False, "FW": True,  "V": True,   # 방화벽만
          "desc": "방화벽만 (E=1, U=1, V=방화벽+거부권)"},
    "B": {"E": True,  "U": False, "FW": False, "V": False,  # 증거층만
          "desc": "증거층만 (E=E_micro, U=1, V=∅)"},
    "C": {"E": True,  "U": False, "FW": True,  "V": True,   # 방화벽+증거층
          "desc": "방화벽+증거층 (E=E_micro, U=1, V=방화벽+거부권)"},
    "D": {"E": True,  "U": True,  "FW": True,  "V": True,   # 전체 = MICRO-FW
          "desc": "전체 MICRO-FW (E×U×방화벽×거부권)"},
}


def assemble_signal(P: pd.DataFrame, variant: str = "D") -> pd.DataFrame:
    """구성별 신호. 랭크는 '월 전체'에서 매긴다.

    ★ 셀별로 랭크를 나눠 매기면 자기 셀에 혼자인 종목이 무조건 1.0 을 받아 상위를 채운다.
      셀 정규화는 이미 E/U 안에서 끝났다. 선정은 월 전체를 한 줄로 세워서 한다.
    """
    cfg = VARIANTS[variant]
    P = P.copy()
    one = pd.Series(1.0, index=P.index)

    e = P.groupby("month", observed=True)["E_micro"].rank(pct=True) if cfg["E"] else one
    u = P.groupby("month", observed=True)["U_micro"].rank(pct=True) if cfg["U"] else one
    fw = col(P, "FW").fillna(0.0) if cfg["FW"] else one
    vt = col(P, "VETO").fillna(0.0) if cfg["V"] else one

    sig = pd.to_numeric(e, errors="coerce") * pd.to_numeric(u, errors="coerce") * fw * vt
    # E/U 를 쓰지 않는 구성(A)에서는 전 종목이 동점이 된다 → 유동성 순으로 안정적 타이브레이크.
    if not cfg["E"] and not cfg["U"]:
        tie = P.groupby("month", observed=True)["adv20"].rank(pct=True).fillna(0.0)
        # ★ 1e-6 을 곱해 [1.0, 1.000001] 로 밀어 넣으면 안 된다.
        #   float32 의 1.0 근방 간격은 1.19e-7 이라 1,000개의 서로 다른 타이값이
        #   9개 값으로 뭉개진다. 그러면 nlargest 가 한 뭉치에서 '종목코드 오름차순'으로
        #   25개를 집는다 — A 구성이 사실상 '번호가 작은 종목 25개'가 된다.
        #   A 는 R0b·R2-M 의 비교 기준이므로 판정 전체가 오염된다.
        #   → 배수를 [1,2] 로 벌리고 float64 로 유지한다. 순서는 동일하되 뭉개지지 않는다.
        sig = sig * (1.0 + tie)
    P["Signal"] = pd.to_numeric(sig, errors="coerce").astype("float64")
    P["Signal_rank"] = P.groupby("month", observed=True)["Signal"].rank(pct=True)

    # ★ 구성에서 뺀 층은 컬럼 자체를 중립화한다.
    #   백테스트의 보유 유지 판정은 P["FW"]/P["VETO"] 를 직접 읽는다. 신호식에서만 빼고
    #   컬럼을 그대로 두면, 'V=∅' 로 정의된 B 구성에서도 방화벽·거부권이 강제 청산을
    #   일으켜 실제로는 C 와 섞인 구성이 된다 → R2-M 비교가 정의대로 성립하지 않는다.
    if not cfg["FW"]:
        P["FW"] = 1
    if not cfg["V"]:
        P["VETO"] = 1.0
    n_live = int((P["Signal"] > 0).sum())
    LOG.info(f"[{variant}] {cfg['desc']} — 신호>0 {n_live:,}행 "
             f"(월평균 {n_live/max(P['month'].nunique(),1):,.0f}종목)")
    return P



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L3  백테스트 엔진 (§10)                                                                  ║
# ║                                                                                          ║
# ║  체결   : 신호 산출일의 '다음 거래일 시가'. 당일 종가 체결은 미래누수다.                    ║
# ║  비용   : 왕복 수수료+세금+슬리피지(거래대금 참여율, 소형주 가중)                          ║
# ║  리밸런싱: 월 1회                                                                          ║
# ║  청산   : 거부권 발동 / 방화벽 이탈 / 보유 24개월 상한 / 신호 밴드 이탈                    ║
# ║  비중   : 20일 평균거래대금의 일정 비율로 상한 (소액계좌에서도 실행 가능한지 검증)          ║
# ║  상장폐지: 정리매매 최종가, 없으면 -100% (C2 — 누락 처리 금지)                              ║
# ║                                                                                          ║
# ║  ★ 월 루프(120회)는 돌지만 종목 루프는 돌지 않는다. 월 내부는 전부 벡터 연산이다.          ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def sell_tax_rate(dt) -> float:
    """증권거래세(코스닥/코스피 장내 매도). 구간별 인하를 반영한다.
    하드코딩된 '기억'이 아니라 시행일 기준 표이며, 틀리면 R9 비용 시나리오가 흡수한다."""
    d = as_ts(dt)
    if d is None:
        return 0.0023
    y = (d.year, d.month)
    if y < (2019, 6):
        return 0.0030
    if y < (2021, 1):
        return 0.0025
    if y < (2023, 1):
        return 0.0023
    if y < (2024, 1):
        return 0.0020
    if y < (2025, 1):
        return 0.0018
    return 0.0015


SLIPPAGE_K = 0.05          # 제곱근 충격계수
SLIPPAGE_BASE = 0.0015     # 호가 스프레드 절반 (소형주 기준)


def slippage_bps(trade_krw: float, adv_krw: float, participation: float = 0.0) -> float:
    """거래대금 참여율에 대한 제곱근 충격모형:  impact ≈ base + K·√(참여율).

    ★ participation(시나리오의 참여율 '상한')을 충격식에 곱하면 안 된다.
      한때 `base + K·√(part/P)·P` 였는데 이는 `base + K·√part·√P` 와 같아서,
      상한을 넉넉히 준 낙관 시나리오(P=0.20)가 빡빡한 비관 시나리오(P=0.05)보다
      슬리피지가 커지는 역전이 발생했다 — 비용 시나리오의 의미가 뒤집힌다.
      상한은 '얼마나 살 수 있는가'(사이징)에만 쓰고, 충격은 실제 참여율만의 함수다.
    """
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.0300                      # 거래대금을 모르면 3% 로 보수적으로 계상
    part = min(max(float(trade_krw) / float(adv_krw), 0.0), 1.0)
    return SLIPPAGE_BASE + SLIPPAGE_K * math.sqrt(part)


def _cap_weights(w: pd.Series, cap: pd.Series, max_iter: int = 8) -> pd.Series:
    """상한을 지키면서 재분배한다. 남는 몫은 현금으로 둔다.

    ★ `w = min(w, cap); w = w / w.sum()` 는 상한을 무효화한다.
      상한이 전 종목에 걸리면 정규화가 정확히 원래 비중을 복원해 버리기 때문이다
      (5종목 각 0.12 → 합 0.60 → 정규화 → 각 0.20). 소형주 용량 제약을 보겠다는
      R9 의 참여율 상한이 아무 일도 하지 않게 된다.
    → 상한을 건 뒤 '여유가 있는 종목에만' 재분배하고, 그래도 남으면 현금으로 남긴다.
    """
    w = w.astype("float64").copy()
    cap = cap.astype("float64").reindex(w.index).fillna(0.0)
    w = np.minimum(w, cap)
    for _ in range(max_iter):
        s = float(w.sum())
        if s >= 1.0 - 1e-9:
            break
        room = (cap - w).clip(lower=0.0)
        tot = float(room.sum())
        if tot <= 1e-12:
            break                          # 전 종목이 상한 → 나머지는 현금
        w = w + room * min(1.0, (1.0 - s) / tot)
    return w.clip(lower=0.0)


def _select_month(sub: pd.DataFrame, top_pct: float, max_n: int, min_n: int) -> pd.DataFrame:
    """그 달의 목표 포트폴리오. 월 전체를 한 줄로 세워 상위 X% 를 뽑는다."""
    live = sub[sub["Signal"] > 0]
    if len(live) == 0:
        return live
    n = int(np.clip(round(len(live) * top_pct), min_n, max_n))
    n = min(n, len(live))
    return live.nlargest(n, "Signal")


def run_backtest_micro(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                       variant: str = "D", scenario: str = COST_BASE_SCENARIO,
                       label: str = "", quiet: bool = False) -> dict:
    """월별 백테스트. 반환에는 월 수익률·보유내역·회전율·비용이 전부 들어간다."""
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    roundtrip, participation = float(scn["roundtrip"]), float(scn["participation"])
    one_way = roundtrip / 2.0

    dmap = uni.delisting_map() if uni is not None else {}
    need = ["code", "month", "Signal", "fwd_ret", "adv20", "VETO", "FW", "close", "d1_trailing"]
    D = P[[c for c in need if c in P.columns]].copy()
    for c in need:
        if c not in D.columns:
            D[c] = np.nan
    D = D.sort_values(["month", "Signal"], ascending=[True, False], kind="stable")
    by_month = {m: g for m, g in D.groupby("month", observed=True)}

    prev_w: Dict[str, float] = {}
    entry_m: Dict[str, pd.Timestamp] = {}
    recs, holdings_log = [], []

    for t in months:
        sub = by_month.get(t)
        if sub is None or len(sub) == 0:
            if prev_w:
                # 그 달 패널이 통째로 비면 보유를 유지하되 수익률은 0 으로 둔다(추정 금지)
                recs.append({"month": t, "ret_gross": 0.0, "cost": 0.0, "ret": 0.0,
                             "n": len(prev_w), "turnover": 0.0})
            continue
        sub = sub.set_index("code")

        tgt = _select_month(sub.reset_index(), PORTFOLIO_TOP_PCT,
                            PORTFOLIO_MAX_NAMES, PORTFOLIO_MIN_NAMES)
        tgt_codes = list(tgt["code"]) if len(tgt) else []

        # ── 유지 판정 (§10 청산 규칙) ────────────────────────────────────────────────
        band = sub["Signal"].rank(pct=True, ascending=True)   # 1.0 = 최고
        keep = []
        for c in prev_w:
            if c not in sub.index:
                continue                                       # 패널 이탈 → 청산(상폐 포함)
            # ★ 결측은 '유지'가 아니라 '청산'이다.
            #   `float(x or 0) == 0` 은 NaN 에서 무너진다: NaN 은 truthy 라 `or` 를 통과하고
            #   float(NaN)==0 은 False 라 청산 분기가 발동하지 않는다. 그 결과 거부권 데이터가
            #   결측인 종목은 '영원히 보유'된다 — 살 수는 없는데(신호 쪽은 fillna(0)) 팔지도
            #   못하는 좀비 포지션이 생긴다.
            if not float(pd.to_numeric(sub.at[c, "VETO"], errors="coerce") or 0.0) == 1.0:
                continue                                       # 거부권 발동/결측 → 즉시 청산
            if not float(pd.to_numeric(sub.at[c, "FW"], errors="coerce") or 0.0) == 1.0:
                continue                                       # 방화벽 이탈/결측 → 청산
            held = (t.year - entry_m[c].year) * 12 + (t.month - entry_m[c].month)
            if held >= HOLD_MAX_MONTHS:
                continue                                       # 보유 상한
            # 청산 게이트(§10): ΔlogM 이 ΔlogE 수준까지 확장 = 논거가 가격에 반영 완료
            d1 = sub.at[c, "d1_trailing"] if "d1_trailing" in sub.columns else np.nan
            if pd.notna(d1) and float(d1) >= 0.0:
                continue
            # ★ 위 FW/VETO 와 같은 이유로 여기서도 결측은 '청산'이다.
            #   `float(nan) < 0.90` 은 False 라, 신호가 사라진 종목이 청산 분기를 그대로
            #   통과해 최대 24개월 동안 보유된다 — 살 수는 없는데 팔지도 못하는 포지션이다.
            _b = pd.to_numeric(pd.Series([band.get(c, np.nan)]), errors="coerce").iloc[0]
            if not (pd.notna(_b) and float(_b) >= (1.0 - 2 * PORTFOLIO_TOP_PCT)):
                continue                                       # 신호 밴드 이탈/결측 → 청산

            keep.append(c)

        # ★ 보유분(keep)을 신규 목표(tgt)보다 무조건 앞세우면 안 된다.
        #   PORTFOLIO_MAX_NAMES=25 이고 유니버스가 500종목만 넘어도 목표 종목수가 25가 되어,
        #   keep 이 25개를 채우는 순간 tgt 가 통째로 잘려 나간다. 전략이 조용히
        #   "한 번 사서 24개월 보유"로 퇴화하고, 그게 A/B/C/D 스프레드를 압착한다.
        #   → 보유·신규를 합쳐 신호 순으로 상위 N 개를 고른다(보유는 위 게이트를 이미 통과했다).
        cand = list(dict.fromkeys(keep + tgt_codes))
        if len(cand) > PORTFOLIO_MAX_NAMES:
            _sc = (pd.to_numeric(sub.reindex(cand)["Signal"], errors="coerce")
                     .fillna(-np.inf).sort_values(ascending=False))
            cand = list(_sc.index[:PORTFOLIO_MAX_NAMES])
        chosen = cand
        if not chosen:
            # 조건을 만족하는 종목이 없으면 현금. 억지로 채우지 않는다.
            if prev_w:
                turn = sum(abs(0.0 - w) for w in prev_w.values())
                cost = turn * one_way
                recs.append({"month": t, "ret_gross": 0.0, "cost": cost, "ret": -cost,
                             "n": 0, "turnover": turn})
                prev_w, entry_m = {}, {}
            continue

        # ── 사이징: 동일가중 → 거래대금 참여율 상한 → 여유분만 재분배(나머지는 현금) ──
        # adv 는 '그 달 전체'에서 만든다. 매도 종목(chosen 밖)도 비용 계산에 필요한데
        # chosen 으로만 만들면 전부 결측이 되어 매도마다 3% 폴백 슬리피지를 문다.
        adv_all = pd.to_numeric(sub["adv20"], errors="coerce")
        w = pd.Series(1.0 / len(chosen), index=chosen, dtype="float64")
        cap_adv = (participation * adv_all.reindex(chosen) / max(ACCOUNT_KRW, 1))
        cap_adv = cap_adv.clip(upper=POS_MAX_WEIGHT).fillna(POS_MIN_WEIGHT)
        w = _cap_weights(w, cap_adv)
        w = w[w >= POS_MIN_WEIGHT * 0.5]
        if float(w.sum()) <= 0:
            continue
        cash_w = max(0.0, 1.0 - float(w.sum()))                # 용량 부족분은 현금(수익률 0)

        # ── 수익률 (상장폐지 -100% 강제) ─────────────────────────────────────────────
        fr = pd.to_numeric(sub.reindex(w.index)["fwd_ret"], errors="coerce")
        nxt = t + pd.offsets.MonthEnd(1)
        nxt_sub = by_month.get(nxt)
        nxt_codes = set(nxt_sub["code"].astype(str)) if nxt_sub is not None else None
        n_forced = 0
        for c in w.index:
            dd = dmap.get(c)
            has_dd = dd is not None and pd.notna(dd) and dd > t
            # ★ 폐지월 창(t < dd <= 다음달)만 보면 안 된다.
            #   한국 소형주의 전형적 경로는 '거래정지 → 수 개월 실질심사 → 상장폐지'다.
            #   정지 시점부터 가격 행이 끊겨 fwd_ret 이 NaN 이 되는데, 폐지일은 몇 달 뒤라
            #   창 조건이 거짓이 되고, fillna(0.0) 이 그 달을 0% 로 기록한다.
            #   = 전액을 잃은 포지션이 '본전'으로 계상된다(생존자편향 재유입, C2 위반).
            # ★ 결측이라는 이유만으로 -100% 를 찍으면 안 된다. 가격 소스가 한 달 비었을 뿐인
            #   2018년의 종목이, 2025년에 폐지 예정이라는 이유로 2018년에 전액손실 처리된다.
            #   → 폐지일이 지났거나, 결측이면서 **다음 달 패널에서도 사라졌을 때**만 확정한다.
            if has_dd and (dd <= nxt or (pd.isna(fr.get(c, np.nan))
                                         and (nxt_codes is None or c not in nxt_codes))):
                fr.at[c] = -1.0
                n_forced += 1
                continue
            # ★ 폐지일을 아예 모르는 종목이 더 위험하다.
            #   FDR 폐지목록은 부분적일 수 있고(코드가 그 사실을 경고한다), 그런 종목은
            #   dmap 에 없어서 위 분기를 전부 비껴간다. 거래가 끊겼는데 폐지일도 없으면
            #   조용히 0% 가 된다 — 커버리지가 나쁠수록 성과가 좋아지는 최악의 편향이다.
            #   → 다음 달 패널에서 사라졌고 수익률도 없으면 '사실상 상장폐지'로 간주한다.
            if (not has_dd) and pd.isna(fr.get(c, np.nan)) and nxt_codes is not None \
                    and c not in nxt_codes:
                fr.at[c] = -1.0
                n_forced += 1
        n_nan = int(fr.isna().sum())
        fr = fr.fillna(0.0)             # 다음 달에도 살아 있는 종목의 일시적 결측만 0 (추정 금지)

        ret_gross = float((w * fr).sum())                      # 현금분은 수익률 0

        # ── 비용: 회전율 × 편도비용 + 슬리피지 + 매도세 ──────────────────────────────
        # ★ 직전 비중은 '목표'가 아니라 '드리프트된 실제' 비중과 비교해야 한다.
        #   지난달 목표를 그대로 두고 비교하면, 종목별 수익률 차이로 이미 벌어진 비중을
        #   되돌리는 거래(리밸런싱의 본질)가 회전율에서 통째로 빠진다.
        allc = set(w.index) | set(prev_w)
        turn = float(sum(abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0))) for c in allc))
        slip = 0.0
        for c in allc:
            dw = abs(float(w.get(c, 0.0)) - float(prev_w.get(c, 0.0)))
            if dw <= 0:
                continue
            a = float(adv_all.get(c, np.nan)) if c in adv_all.index else np.nan
            slip += dw * slippage_bps(dw * ACCOUNT_KRW, a)
        sells = float(sum(max(float(prev_w.get(c, 0.0)) - float(w.get(c, 0.0)), 0.0) for c in allc))
        cost = turn * one_way + slip + sells * sell_tax_rate(t)

        recs.append({"month": t, "ret_gross": ret_gross, "cost": cost,
                     "ret": ret_gross - cost, "n": int(len(w)), "turnover": turn,
                     "cash_w": cash_w, "na_fwd": n_nan, "delist_forced": n_forced})
        for c in w.index:
            holdings_log.append({"month": t, "code": c, "w": float(w[c]),
                                 "signal": float(sub.at[c, "Signal"] or 0.0),
                                 "fwd_ret": float(fr[c])})
        for c in w.index:
            entry_m.setdefault(c, t)
        for c in list(entry_m):
            if c not in w.index:
                entry_m.pop(c, None)
        # 다음 달 비교 기준은 '드리프트된 실제 비중'이다(목표 비중이 아니다).
        drift = w * (1.0 + fr.reindex(w.index).fillna(0.0))
        tot = float(drift.sum()) + cash_w
        prev_w = (drift / tot).to_dict() if tot > 0 else {}

    R = pd.DataFrame(recs)
    if len(R):
        R = R.sort_values("month").reset_index(drop=True)
        # ★ 보유가 없던 달은 recs 에 아예 안 들어간다. 그대로 두면 연율화 분모(개월수)가
        #   줄어 CAGR·Sharpe 가 과대계상된다(현금으로 쉰 기간이 사라진다).
        #   전 구간 격자에 맞춰 채운다 — 쉰 달은 수익률 0 이다.
        full = pd.DataFrame({"month": pd.DatetimeIndex(months)})
        R = full.merge(R, on="month", how="left")
        for c in ("ret_gross", "cost", "ret", "turnover", "n", "cash_w", "na_fwd",
                  "delist_forced"):
            if c in R.columns:
                R[c] = pd.to_numeric(R[c], errors="coerce").fillna(0.0)
        R.loc[R["n"] == 0, "cash_w"] = 1.0
        R["equity"] = (1.0 + R["ret"]).cumprod()
    H = pd.DataFrame(holdings_log)
    out = {"variant": variant, "scenario": scenario, "label": label or variant,
           "returns": R, "holdings": H, "stats": perf_stats(R)}
    if not quiet:
        s = out["stats"]
        LOG.ok(f"[{label or variant}·{scenario}] CAGR {100*s['cagr']:.2f}% · "
               f"MDD {100*s['mdd']:.1f}% · Calmar {s['calmar']:.2f} · "
               f"Sharpe {s['sharpe']:.2f} · 월평균 {s['avg_n']:.0f}종목 · "
               f"회전율 {100*s['turnover']:.0f}%/월 · 상폐확정 {s.get('delist_forced', 0):.0f}건"
               + (f" · 결측0%처리 {s.get('na_zero', 0):.0f}건" if s.get('na_zero', 0) else ""))
    PIPE.io("OUT", "MEM", f"backtest:{label or variant}", R)
    return out


def perf_stats(R: pd.DataFrame) -> dict:
    """성과 지표. 표본이 없으면 0 이 아니라 NaN 을 돌려준다(없는 성과를 만들지 않는다)."""
    if R is None or len(R) == 0 or "ret" not in R.columns:
        return {"n_months": 0, "cagr": np.nan, "vol": np.nan, "sharpe": np.nan,
                "mdd": np.nan, "calmar": np.nan, "hit": np.nan, "turnover": np.nan,
                "avg_n": np.nan, "total": np.nan, "cost_drag": np.nan, "cash": np.nan,
                "delist_forced": np.nan, "na_zero": np.nan}
    r = pd.to_numeric(R["ret"], errors="coerce").fillna(0.0).to_numpy()
    n = len(r)
    # ★ 자본 기준선 1.0 을 앞에 붙인다.
    #   cumprod 만 쓰면 eq[0] = 1+r[0] 이고 peak[0] = eq[0] 이라 '첫 달의 하락'이
    #   정의상 드로다운 0 이 된다. r=[-0.30, ...] 이 MDD 0% 로 보고되고, Calmar 가
    #   NaN 또는 무한대가 되어 킬 게이트 판정이 통째로 뒤집힌다.
    eq = np.concatenate(([1.0], np.cumprod(1.0 + r)))
    total = float(eq[-1] - 1.0)
    yrs = n / 12.0
    cagr = float(eq[-1] ** (1.0 / yrs) - 1.0) if yrs > 0 and eq[-1] > 0 else -1.0
    vol = float(np.std(r, ddof=1) * math.sqrt(12)) if n > 1 else np.nan
    sharpe = float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(12)) if n > 1 and np.std(r, ddof=1) > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    mdd = float(np.min(eq / peak - 1.0)) if n else np.nan
    # 드로다운이 정확히 0 이면 Calmar 는 정의되지 않는다. 수익이 양수면 +inf 가 맞지만
    # 비교에 쓰이므로 매우 큰 유한값으로 두고, 손실이면 0 으로 둔다.
    if mdd is None or not np.isfinite(mdd) or mdd >= 0:
        calmar = (999.0 if (np.isfinite(cagr) and cagr > 0) else 0.0) if n else np.nan
    else:
        calmar = float(cagr / abs(mdd))
    # ★ R.get("x") 는 컬럼이 없으면 None 을 돌려주고, pd.to_numeric(None) 은 Series 가 아니라
    #   numpy 스칼라가 된다 → .fillna() 에서 AttributeError. col() 은 없는 컬럼도 NaN Series 로
    #   돌려주므로 이 경로가 원천 차단된다.
    def _m(name: str, how: str = "mean") -> float:
        s = col(R, name)
        s = pd.to_numeric(s, errors="coerce").fillna(0.0)
        return float(getattr(s, how)()) if len(s) else 0.0

    return {"n_months": n, "cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd,
            "calmar": calmar, "hit": float((r > 0).mean()), "total": total,
            "turnover": _m("turnover"), "avg_n": _m("n"), "cost_drag": _m("cost", "sum"),
            "cash": _m("cash_w"), "delist_forced": _m("delist_forced", "sum"),
            "na_zero": _m("na_fwd", "sum")}


def benchmark_universe_ew(P: pd.DataFrame, months: pd.DatetimeIndex,
                          scenario: str = COST_BASE_SCENARIO,
                          mask_col: Optional[str] = None,
                          uni: Optional["Universe"] = None) -> dict:
    """R0(a) 자체 측정 벤치마크 — U-MICRO 유니버스 동일가중.

    ★ 벤치마크 수치를 하드코딩하지 않는다(원칙 5). 같은 데이터·같은 비용모형으로 직접 잰다.
    동일가중도 매월 리밸런싱하므로 회전율이 있고, 그 비용을 똑같이 물린다.

    ★ 상장폐지를 전략과 '똑같이' 처리해야 한다. ─────────────────────────────────────
      fwd_ret 이 NaN 인 행을 그냥 버리면 거래가 끊긴 종목(=대부분 상장폐지)이 벤치마크에서
      조용히 사라져, 살아남은 종목만의 수익률이 기준선이 된다. 그러면 전략이 아무리
      좋아도 이길 수 없는 '생존자 벤치마크'와 싸우게 되고, R0/R2-M 판정이 통째로 왜곡된다.
    """
    scn = COST_SCENARIOS.get(scenario, COST_SCENARIOS[COST_BASE_SCENARIO])
    one_way = float(scn["roundtrip"]) / 2.0
    sub = P
    if mask_col and mask_col in P.columns:
        sub = P[P[mask_col].astype(bool)]
    sub = sub[["code", "month", "fwd_ret"]].copy()
    # 폐지 예정 종목의 끊긴 달은 -100% 로 확정한 뒤에 결측을 버린다(순서가 중요하다).
    if uni is not None:
        dmap = uni.delisting_map()
        if dmap:
            dd = sub["code"].map(dmap)
            kill = sub["fwd_ret"].isna() & dd.notna() & (as_ts_series(dd) > sub["month"])
            n_kill = int(kill.sum())
            if n_kill:
                sub.loc[kill, "fwd_ret"] = -1.0
                LOG.debug(f"벤치마크(동일가중)에서 상장폐지 {n_kill:,}종목월을 -100% 로 확정했습니다 "
                          f"(전략과 동일한 처리 — 생존자 벤치마크 방지).")
    # ★ 전략은 '폐지목록에 없는데 다음 달 사라진' 종목도 -100% 로 확정한다(FDR 폐지목록의
    #   공백을 메우는 규칙). 벤치마크가 그 규칙을 안 쓰면 벤치마크만 그 손실을 면제받아
    #   '부분 생존자 벤치마크'가 된다 — R0a·R2-M① 이 그 격차만큼 전략에 불리해진다.
    #   여기서 같은 규칙을 적용해 비교 기준을 대칭으로 맞춘다.
    if len(sub):
        _ms = sorted(pd.unique(sub["month"]))
        _pos = {m: i for i, m in enumerate(_ms)}
        _inv = {i: m for m, i in _pos.items()}
        _have = set(zip(sub["code"].astype(str), sub["month"]))
        _nm = sub["month"].map(_pos).add(1).map(_inv)
        _gone = pd.Series([(c, m) not in _have for c, m in zip(sub["code"].astype(str), _nm)],
                          index=sub.index)
        kill2 = sub["fwd_ret"].isna() & _nm.notna() & _gone
        n2 = int(kill2.sum())
        if n2:
            sub.loc[kill2, "fwd_ret"] = -1.0
            LOG.debug(f"벤치마크에서 '폐지일 미상이나 다음 달 소멸' {n2:,}종목월도 -100% 로 "
                      f"확정했습니다 (전략과 동일 규칙).")
    sub = sub[sub["fwd_ret"].notna()]
    if len(sub) == 0:
        return {"label": "유니버스 동일가중", "returns": pd.DataFrame(), "stats": perf_stats(None)}
    g = sub.groupby("month", observed=True)
    m = g["fwd_ret"].mean()
    cnt = g["code"].size()

    # ★ 회전율을 상수로 가정하지 않는다. 실제 편입/이탈로 계산한다.
    #   상수 20% 를 쓰면 벤치마크 비용이 데이터와 무관해지고, 전략만 슬리피지·거래세를
    #   물고 벤치마크는 안 무는 비대칭이 생겨 R0/R2-M 판정이 기울어진다.
    members = {mm: set(gg["code"]) for mm, gg in sub.groupby("month", observed=True)}
    idx = sorted(members)
    turn_v, sells_v = [], []
    prev: set = set()
    for mm in idx:
        cur = members[mm]
        nc, np_ = max(len(cur), 1), max(len(prev), 1)
        if not prev:
            turn_v.append(1.0); sells_v.append(0.0)
        else:
            # 동일가중 기준 Σ|w_t − w_{t−1}|
            allc = cur | prev
            t_ = sum(abs((1.0 / nc if c in cur else 0.0) - (1.0 / np_ if c in prev else 0.0))
                     for c in allc)
            s_ = sum(max((1.0 / np_ if c in prev else 0.0) - (1.0 / nc if c in cur else 0.0), 0.0)
                     for c in allc)
            turn_v.append(float(t_)); sells_v.append(float(s_))
        prev = cur
    T = pd.Series(turn_v, index=pd.DatetimeIndex(idx))
    S = pd.Series(sells_v, index=pd.DatetimeIndex(idx))

    R = pd.DataFrame({"month": m.index, "ret_gross": m.to_numpy(), "n": cnt.to_numpy()})
    R["turnover"] = T.reindex(R["month"]).to_numpy()
    _sells = S.reindex(R["month"]).to_numpy()
    # 전략과 동일한 비용 구성: 편도수수료 + 호가스프레드 + 매도 시 증권거래세
    R["cost"] = (R["turnover"] * one_way + R["turnover"] * SLIPPAGE_BASE
                 + _sells * np.array([sell_tax_rate(x) for x in R["month"]]))
    R["ret"] = R["ret_gross"] - R["cost"]
    R = (pd.DataFrame({"month": pd.DatetimeIndex(months)})
         .merge(R, on="month", how="left"))
    for c in ("ret_gross", "cost", "ret", "turnover", "n"):
        R[c] = pd.to_numeric(R[c], errors="coerce").fillna(0.0)
    R["equity"] = (1.0 + R["ret"]).cumprod()
    return {"label": "유니버스 동일가중", "variant": "BENCH", "scenario": scenario,
            "returns": R, "holdings": pd.DataFrame(), "stats": perf_stats(R)}


def benchmark_index(months: pd.DatetimeIndex) -> Dict[str, dict]:
    """참고용 지수 벤치마크(코스닥/코스피). 없으면 조용히 건너뛴다 — 필수가 아니다."""
    out: Dict[str, dict] = {}
    if fdr is None or RUN_MODE == "SMOKE":
        return out
    for name, sym in (("KOSDAQ", "KQ11"), ("KOSPI", "KS11")):
        try:
            d = fdr.DataReader(sym, str(months[0].date()), str(months[-1].date()))
        except Exception:
            continue
        if d is None or len(d) == 0 or "Close" not in d.columns:
            continue
        s = (d["Close"].resample(pd.offsets.MonthEnd()).last()
             if hasattr(d["Close"], "resample") else None)
        if s is None or len(s) < 3:
            continue
        r = s.pct_change().dropna()
        R = pd.DataFrame({"month": as_ts_series(pd.Series(r.index)) + pd.offsets.MonthEnd(0),
                          "ret": r.to_numpy()})
        R = R[R["month"].isin(months)].reset_index(drop=True)
        if len(R) < 3:
            continue
        R["equity"] = (1.0 + R["ret"]).cumprod()
        out[name] = {"label": name, "returns": R, "stats": perf_stats(R)}
    return out



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L5  강건성 (§11)                                                                         ║
# ║                                                                                          ║
# ║   R0   자체 측정 벤치마크 대비 ⭐   — 하드코딩된 기준선을 쓰지 않는다(원칙 5)              ║
# ║   R2-M 거부권 알파 가설 검정 ⭐⭐   — 이 전략의 존재 이유. A/B/C/D 4방 비교                ║
# ║   R3   퀄리티 팩터 직교화           — 알파가 남는가, 아니면 재포장인가                     ║
# ║   R5-M 절제 (조항·TP·거부권)        — 어느 부품이 실제로 일하는가                          ║
# ║   R9   회전율·비용 시나리오         — 비관 시나리오에서도 남는가                           ║
# ║                                                                                          ║
# ║  ★ 유리하게 해석하지 않는다. A 가 벤치마크와 거의 같게 나오면 그대로 보고한다.             ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

ROBUST: List[dict] = []
_KILL_ARMED = True     # 합성 스모크 구간에서만 False. 실데이터에서는 항상 True.


def _rec(rid: str, name: str, passed: Optional[bool], detail: str, kill: bool = False):
    ROBUST.append({"id": rid, "name": name, "passed": passed, "detail": detail, "kill": kill})
    icon = "—" if passed is None else ("✔" if passed else "✘")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.error))(
        f"[{rid}] {icon} {name} — {detail}")
    if kill and passed is False and STOP_ON_KILL_CRITERIA and _KILL_ARMED:
        raise KillCriteria(f"[{rid}] {name}: {detail}")


def _calmar(bt: dict) -> float:
    v = (bt or {}).get("stats", {}).get("calmar", np.nan)
    return float(v) if v is not None and np.isfinite(v) else -np.inf


def _fmt(bt: dict) -> str:
    s = (bt or {}).get("stats", {})
    def g(k):
        v = s.get(k, np.nan)
        return v if v is not None and np.isfinite(v) else np.nan
    return (f"CAGR {100*g('cagr'):.1f}% · MDD {100*g('mdd'):.1f}% · "
            f"Calmar {g('calmar'):.2f} · Sharpe {g('sharpe'):.2f}")


# ── R0 ──────────────────────────────────────────────────────────────────────────────────────
def R0_benchmark(bts: Dict[str, dict], bench_ew: dict, bench_idx: Dict[str, dict]):
    """MICRO-FW(D)가 (a) 유니버스 동일가중, (b) 방화벽 단독(A) 을 Calmar 로 상회하는가."""
    d, a = bts.get("D"), bts.get("A")
    c_d, c_a, c_b = _calmar(d), _calmar(a), _calmar(bench_ew)
    rows = [["MICRO-FW (D)", _fmt(d)], ["방화벽 단독 (A)", _fmt(a)],
            ["유니버스 동일가중", _fmt(bench_ew)]]
    for k, v in (bench_idx or {}).items():
        rows.append([f"참고: {k} 지수", _fmt(v)])
    LOG.table(rows, ["구성", "성과"], ["l", "l"],
              title="R0 — 자체 측정 벤치마크 (수치를 인용하지 않고 같은 데이터로 직접 잰다)")

    ok_a = c_d > c_b
    _rec("R0a", "유니버스 동일가중 대비 (Calmar)", bool(ok_a),
         f"D {c_d:.2f} vs 동일가중 {c_b:.2f} — "
         f"{'상회' if ok_a else '미달. 유니버스 자체의 수익을 재현한 것에 불과합니다'}")
    ok_b = c_d > c_a
    _rec("R0b", "방화벽 단독(A) 대비 (Calmar) ⭐", bool(ok_b),
         f"D {c_d:.2f} vs A {c_a:.2f} — "
         f"{'증거층이 방화벽 위에 값을 더합니다' if ok_b else '증거층이 방화벽에 아무것도 더하지 못합니다(§12-3 폐기 기준)'}",
         kill=True)


# ── R2-M : 4방 비교 (이 전략의 존재 이유) ───────────────────────────────────────────────────
def R2M_fourway(bts: Dict[str, dict], bench_ew: dict) -> str:
    c = {k: _calmar(v) for k, v in bts.items()}
    cb = _calmar(bench_ew)
    rows = [[k, VARIANTS[k]["desc"], _fmt(bts.get(k)), f"{c.get(k, float('nan')):.2f}"]
            for k in ("A", "B", "C", "D") if k in bts]
    rows.append(["–", "유니버스 동일가중 (기준선)", _fmt(bench_ew), f"{cb:.2f}"])
    LOG.table(rows, ["구성", "정의", "성과", "Calmar"], ["c", "l", "l", "r"],
              title="R2-M — 4방 비교 (§11.1). 방화벽이 알파인가, 손실회피인가")
    LOG.info(f"비교 조건: A~D 는 포트폴리오 구성(상위 {100*PORTFOLIO_TOP_PCT:.0f}%·최대 "
             f"{PORTFOLIO_MAX_NAMES}종목·동일 사이징·동일 비용)이 전부 같고, 다른 것은 "
             f"'무엇으로 순위를 매기는가' 하나뿐입니다. 종목 수를 다르게 두면 분산효과와 "
             f"신호효과가 섞여 비교 자체가 무의미해지기 때문입니다.")
    LOG.info("단, A(방화벽만)는 통과/탈락이 이진값이라 순위를 매길 것이 없어 "
             "거래대금 순으로 동점을 가릅니다 — 즉 A 에는 유동성 틸트가 들어 있습니다. "
             "A 가 동일가중을 이긴다면 그 일부는 유동성 효과일 수 있다는 뜻이며, "
             "R0a(전체 유니버스 동일가중 대비)가 그 판정의 기준선입니다.")

    verdicts = []
    # ① 방화벽 자체가 알파인가
    gap = c.get("A", -np.inf) - cb
    if gap > 0.15:
        v1 = ("방화벽 자체가 알파입니다. A 가 유니버스 동일가중을 뚜렷하게 상회합니다 "
              f"(Calmar {c.get('A', float('nan')):.2f} vs {cb:.2f}). 가설 지지.")
    elif gap > -0.15:
        v1 = ("★방화벽은 알파가 아니라 손실회피입니다. A 가 유니버스 동일가중과 사실상 같습니다 "
              f"(Calmar {c.get('A', float('nan')):.2f} vs {cb:.2f}). 문서가 예고한 결과이며 "
              "유리하게 해석하지 않고 그대로 보고합니다.")
    else:
        v1 = (f"방화벽이 오히려 해롭습니다 (A {c.get('A', float('nan')):.2f} < 동일가중 {cb:.2f}). "
              "하드필터가 수익 원천을 함께 잘라내고 있습니다.")
    verdicts.append(v1)

    # ② 결합의 근거가 있는가
    best_ab = max(c.get("A", -np.inf), c.get("B", -np.inf))
    # ★ '표본 없음'과 '실패'를 구분한다. _calmar 는 결측을 -inf 로 바꾸므로, A·B·C 가 전부
    #   빈 프레임이면 -inf <= -inf 로 참이 되어 "결합 근거가 소멸했습니다 → 폐기" 라는
    #   킬 판정이 나온다. 운영자는 데이터가 비었을 뿐인데 전략을 버리라는 말을 듣는다.
    #   4시간을 다시 태워 엉뚱한 곳을 뒤지게 만드는 실패 양식이다.
    _fin = [v for v in (c.get("A"), c.get("B"), c.get("C")) if v is not None and np.isfinite(v)]
    if len(_fin) < 3:
        v2 = ("A/B/C 중 유효한 성과가 3개 미만이라 결합 근거를 판정할 수 없습니다(표본 없음). "
              "킬 기준을 발동하지 않습니다 — 먼저 백테스트가 왜 비었는지(유니버스·신호 결측) "
              "위 감쇠 감사표와 센서 가용성표를 확인하세요.")
        _rec("R2M-C", "결합 근거 (C > max(A,B)) ⭐", None, v2)
    elif c.get("C", -np.inf) <= best_ab:
        v2 = (f"★C({c.get('C', float('nan')):.2f}) ≤ max(A,B)({best_ab:.2f}) — 결합 근거가 소멸했습니다. "
              f"§12-4 에 따라 더 단순한 쪽"
              f"({'A(방화벽만)' if c.get('A', -np.inf) >= c.get('B', -np.inf) else 'B(증거층만)'})"
              f"을 채택해야 합니다.")
        _rec("R2M-C", "결합 근거 (C > max(A,B)) ⭐", False, v2, kill=True)
    else:
        v2 = f"C({c.get('C', float('nan')):.2f}) > max(A,B)({best_ab:.2f}) — 방화벽과 증거층의 결합에 근거가 있습니다."
        _rec("R2M-C", "결합 근거 (C > max(A,B)) ⭐", True, v2)
    verdicts.append(v2)

    # ③ U 층이 기여하는가
    if c.get("D", -np.inf) <= c.get("C", -np.inf):
        v3 = (f"D({c.get('D', float('nan')):.2f}) ≤ C({c.get('C', float('nan')):.2f}) — U층(가격 모멘텀)이 "
              f"기여하지 않습니다. d1 을 빼고 C 를 최종안으로 삼는 것이 정직합니다.")
        _rec("R2M-D", "U층 기여 (D > C)", False, v3)
    else:
        v3 = f"D({c.get('D', float('nan')):.2f}) > C({c.get('C', float('nan')):.2f}) — U층이 기여합니다."
        _rec("R2M-D", "U층 기여 (D > C)", True, v3)
    verdicts.append(v3)

    LOG.banner("R2-M 판정", "방화벽 알파 가설")
    for i, v in enumerate(verdicts, 1):
        _safe_print(f"  {i}. {v}")
    return "\n".join(f"{i}. {v}" for i, v in enumerate(verdicts, 1))


# ── R3 : 퀄리티 팩터 직교화 ─────────────────────────────────────────────────────────────────
def _factor_returns(P: pd.DataFrame, name: str, colname: str, high_is_long: bool = True
                    ) -> pd.Series:
    """같은 유니버스에서 만든 롱-숏 팩터 월수익률(상위 30% − 하위 30%, 동일가중)."""
    sub = P[P["fwd_ret"].notna() & col(P, colname).notna()]
    if len(sub) < 100:
        return pd.Series(dtype="float64")
    r = sub.groupby("month", observed=True)[colname].rank(pct=True)
    hi = sub[r >= 0.70].groupby("month", observed=True)["fwd_ret"].mean()
    lo = sub[r <= 0.30].groupby("month", observed=True)["fwd_ret"].mean()
    f = (hi - lo) if high_is_long else (lo - hi)
    return f.dropna().rename(name)


def R3_orthogonal(P: pd.DataFrame, bt: dict, bench_ew: Optional[dict] = None):
    """전략 수익률을 퀄리티/밸류/모멘텀 팩터에 회귀해 알파가 남는지 본다.

    남지 않으면 이 전략은 '기존 팩터의 재포장'이다. statsmodels 없이 최소제곱 + HAC t 로 푼다.
    """
    R = (bt or {}).get("returns")
    if R is None or len(R) < 24:
        _rec("R3", "퀄리티 팩터 직교화", None, "표본이 24개월 미만이라 검정하지 않습니다.")
        return
    P = P.copy()
    P["_roa"] = safe_div(col(P, "net_income_ttm"), col(P, "assets").where(col(P, "assets") > 0))
    P["_accq"] = col(P, "i_accr")
    P["_val"] = col(P, "bp")                         # 순자산수익률(B/P) 롱 = 저PBR 롱
    if P["_val"].notna().sum() == 0:
        P["_val"] = -col(P, "pbr")                   # 폴백(구버전 패널 호환)
    facs = [_factor_returns(P, "QMJ_ROA", "_roa"), _factor_returns(P, "ACCR", "_accq"),
            _factor_returns(P, "VALUE", "_val"), _factor_returns(P, "MOM", "d1_trailing")]
    # ★ 유니버스(시장) 팩터를 반드시 넣는다.
    #   위 팩터들은 전부 롱-숏(상위30%−하위30%)이라 구조적으로 시장중립이다. 전략 수익률은
    #   롱온리인데 회귀식에 시장 요인이 없으면, U-MICRO 유니버스 자체의 수익(베타)이 전부
    #   절편으로 들어간다. 그러면 '알파가 남았다'는 판정이 사실은 '소형주에 노출됐다'는
    #   뜻이 되어, R0(동일가중 대비)와 정면으로 모순되는 결론이 나온다.
    if bench_ew is not None and len(bench_ew.get("returns", [])):
        bm = bench_ew["returns"].set_index("month")["ret"].rename("UNIVERSE")
        if len(bm) >= 24:
            facs.append(bm)
    facs = [f for f in facs if len(f) >= 24]
    if not facs:
        _rec("R3", "퀄리티 팩터 직교화", None, "팩터를 구성할 표본이 부족합니다.")
        return
    F = pd.concat(facs, axis=1)
    y = R.set_index("month")["ret"]
    J = F.join(y, how="inner").dropna()
    if len(J) < 24:
        _rec("R3", "퀄리티 팩터 직교화", None, f"교집합 표본 {len(J)}개월로 부족합니다.")
        return
    X = np.column_stack([np.ones(len(J))] + [J[c].to_numpy() for c in F.columns])
    yy = J["ret"].to_numpy()
    try:
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        resid = yy - X @ beta
    except Exception as e:                                             # noqa
        _rec("R3", "퀄리티 팩터 직교화", None, f"회귀 실패({type(e).__name__})")
        return
    alpha_m = float(beta[0])
    t, p = hac_tstat(resid + alpha_m)
    ann = (1 + alpha_m) ** 12 - 1
    rows = [["절편(월 알파)", f"{100*alpha_m:.3f}%", f"연 {100*ann:.2f}%", f"t={t:.2f} p={p:.3f}"]]
    for i, c in enumerate(F.columns):
        rows.append([f"β({c})", f"{beta[i+1]:.3f}", "", ""])
    LOG.table(rows, ["항", "계수", "연율", "유의성"], ["l", "r", "r", "l"],
              title="R3 — 퀄리티/밸류/모멘텀 직교화 후 잔존 알파")
    ok = (ann > 0) and (abs(t) > 1.64)
    has_uni = "UNIVERSE" in list(F.columns)
    _rec("R3", "퀄리티·밸류·모멘텀·유니버스 직교화", bool(ok),
         f"직교화 후 연 알파 {100*ann:.2f}% (t={t:.2f}) · 유니버스 팩터 "
         f"{'포함' if has_uni else '미포함(주의: 소형주 베타가 절편에 섞임)'} — "
         f"{'알파 잔존' if ok else '유의한 알파가 남지 않습니다. 기존 팩터의 재포장일 수 있습니다'}")


# ── R5-M : 절제 ─────────────────────────────────────────────────────────────────────────────
def R5M_ablation(P: pd.DataFrame, months, uni, active: Dict[str, bool], base_bt: dict):
    """조항·TP·거부권을 하나씩 빼 보고 Calmar 변화를 본다. 변화가 없으면 그 부품은 장식이다."""
    base = _calmar(base_bt)
    rows = []

    def run_with(mod: pd.DataFrame, tag: str) -> float:
        try:
            S = assemble_signal(mod, "D")
            bt = run_backtest_micro(S, months, uni, "D", COST_BASE_SCENARIO,
                                    label=f"ABL:{tag}", quiet=True)
            v = (bt or {}).get("stats", {}).get("calmar", np.nan)
            return float(v) if v is not None and np.isfinite(v) else float("nan")
        except Exception as e:                                         # noqa
            LOG.warn(f"절제 검사 '{tag}' 실행 실패({type(e).__name__}) — 판정불가로 처리합니다.")
            return float("nan")

    def verdict(c: float) -> str:
        # ★ NaN 을 '해로움'으로 분류하면 안 된다. 실행이 실패한 것과 부품이 해로운 것은
        #   완전히 다른 사건인데, `c < base-0.05` 와 `abs(c-base) <= 0.05` 가 둘 다
        #   False 가 되어 자동으로 '해로움'으로 떨어진다(원인과 정반대의 결론).
        if not np.isfinite(c):
            return "판정불가"
        if c < base - 0.05:
            return "기여"
        return "무기여" if abs(c - base) <= 0.05 else "해로움"

    for key, (name, _b, enabled, _n) in firewall_clause_masks(P, active).items():
        if not enabled:
            rows.append([f"방화벽·{name}", "비활성", "-", "원래 꺼져 있음"])
            continue
        m = P.copy()
        fw, _ = s1_firewall(m, active, skip=[key], quiet=True)
        m["FW"] = fw
        c = run_with(m, key)
        rows.append([f"방화벽·{name}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    for tid, a, b in TP_DEFS:
        if tid not in P.columns or col(P, tid).notna().sum() == 0:
            continue
        m = P.copy()
        m[tid] = np.nan
        others = [t for t, _, _ in TP_DEFS if t != tid]
        m["E_micro"] = nanmean_cols(m, others)
        c = run_with(m, tid)
        rows.append([f"증거층·{tid}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    for v in ("V1", "V2", "V3", "V6"):
        if v not in P.columns:
            continue
        m = P.copy()
        m[v] = 1.0
        m["VETO"] = m["V1"] * m["V2"] * m["V3"] * m["V6"]
        c = run_with(m, v)
        rows.append([f"거부권·{v}", f"{c:.2f}" if np.isfinite(c) else "—",
                     f"{c-base:+.2f}" if np.isfinite(c) else "—", verdict(c)])

    rows.append(["── 원본 (절제 없음)", f"{base:.2f}", "—", ""])
    LOG.table(rows, ["절제 대상", "Calmar", "변화", "판정"], ["l", "r", "r", "c"],
              title="R5-M — 절제 검사. '빼도 그대로'인 부품은 복잡도만 늘리는 장식이다")
    useful = sum(1 for r in rows[:-1] if r[3] == "기여")
    n_bad = sum(1 for r in rows[:-1] if r[3] == "판정불가")
    _rec("R5M", "절제 (조항·TP·거부권)", useful > 0,
         f"기여 {useful}개 / 검사 {len(rows)-1}개"
         + (f" · 판정불가 {n_bad}개(실행 실패)" if n_bad else "")
         + (" · 무기여 부품은 제거를 검토하세요." if useful < len(rows)-1-n_bad else ""))
    return pd.DataFrame(rows, columns=["절제 대상", "Calmar", "변화", "판정"])


# ── R9 : 비용 시나리오 ──────────────────────────────────────────────────────────────────────
def R9_cost(P: pd.DataFrame, months, uni) -> pd.DataFrame:
    rows, out = [], {}
    for scn in COST_SCENARIOS:
        bt = run_backtest_micro(P, months, uni, "D", scn, label=f"COST:{scn}", quiet=True)
        out[scn] = bt
        s = bt["stats"]
        rows.append([scn, f"{100*COST_SCENARIOS[scn]['roundtrip']:.2f}%",
                     f"{100*COST_SCENARIOS[scn]['participation']:.0f}%",
                     f"{100*s['cagr']:.2f}%", f"{100*s['mdd']:.1f}%", f"{s['calmar']:.2f}",
                     f"{100*s['turnover']:.0f}%"])
    LOG.table(rows, ["시나리오", "왕복비용", "참여율상한", "CAGR", "MDD", "Calmar", "회전율/월"],
              ["c", "r", "r", "r", "r", "r", "r"],
              title="R9 — 비용 시나리오 (§11.2). 비관에서 사라지면 소액계좌라도 실행 불가")
    pes = out.get("비관", {}).get("stats", {})
    # ★ 표본 없음 → 판정 불가. `NaN or 0` 은 NaN(truthy)을 그대로 돌려주고 `NaN > 0.3` 은
    #   False 라, 빈 백테스트가 "성과 소멸 → 폐기 대상" 이라는 킬 판정으로 둔갑한다.
    _cg = pd.to_numeric(pd.Series([pes.get("cagr")]), errors="coerce").iloc[0]
    _cm = pd.to_numeric(pd.Series([pes.get("calmar")]), errors="coerce").iloc[0]
    if not (np.isfinite(_cg) and np.isfinite(_cm)):
        _rec("R9", "비용 시나리오 (비관) ⭐", None,
             "비관 시나리오의 성과지표를 얻지 못했습니다(표본 없음). 킬 기준을 발동하지 "
             "않습니다 — 비용이 문제가 아니라 백테스트가 비어 있다는 뜻입니다.")
    else:
        ok = bool(_cg > 0 and _cm > 0.3)
        _rec("R9", "비용 시나리오 (비관) ⭐", ok,
             f"비관 시나리오 CAGR {100*_cg:.2f}% · Calmar {_cm:.2f} — "
             f"{'성과 잔존' if ok else '성과 소멸. 실행 불가이므로 폐기 대상입니다(§12-5)'}",
             kill=True)
    return pd.DataFrame(rows, columns=["시나리오", "왕복비용", "참여율상한", "CAGR", "MDD",
                                       "Calmar", "회전율/월"])


def report_robustness():
    LOG.banner("강건성 검사 요약", "킬 게이트는 ⭐ 표시 · 실패는 그대로 보고한다")
    if not ROBUST:
        LOG.table([], ["ID", "검사", "판정", "상세"], ["c", "l", "c", "l"])
        return
    rows = [[r["id"], r["name"], "—" if r["passed"] is None else ("통과" if r["passed"] else "실패"),
             _trunc(r["detail"], 78)] for r in ROBUST]
    LOG.table(rows, ["ID", "검사", "판정", "상세"], ["c", "l", "c", "l"], maxw=80)
    n_fail = sum(1 for r in ROBUST if r["passed"] is False)
    if n_fail:
        LOG.warn(f"강건성 검사 {n_fail}건 실패. 임계를 낮춰 통과시키지 마십시오 — "
                 f"실패는 전략에 대한 정보입니다.")
    else:
        LOG.ok("모든 강건성 검사 통과.")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L6  성과 검증 · 해석표 · 진단카드 · 데이터흐름 지도                                       ║
# ║                                                                                          ║
# ║  "숫자 하나"가 아니라 "그 숫자가 어디서 왔는가"를 같이 낸다.                                ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

def _s(bt: dict, k: str, pct: bool = False, nd: int = 2) -> str:
    v = (bt or {}).get("stats", {}).get(k, np.nan)
    if v is None or not np.isfinite(v):
        return "—"
    return f"{100*v:.{nd}f}%" if pct else f"{v:.{nd}f}"


def report_performance(bts: Dict[str, dict], bench_ew: dict, bench_idx: Dict[str, dict]):
    LOG.banner("성과 검증", f"{BACKTEST_START} ~ {BACKTEST_END} · 비용 시나리오 = {COST_BASE_SCENARIO}")
    rows = []
    items = [(k, bts[k]) for k in ("A", "B", "C", "D") if k in bts]
    items.append(("EW", bench_ew))
    for k, v in (bench_idx or {}).items():
        items.append((k, v))
    for k, bt in items:
        if not bt:
            continue
        name = VARIANTS[k]["desc"] if k in VARIANTS else (bt.get("label") or k)
        rows.append([k, _trunc(name, 34), _s(bt, "cagr", True), _s(bt, "total", True, 1),
                     _s(bt, "vol", True, 1), _s(bt, "mdd", True, 1), _s(bt, "sharpe"),
                     _s(bt, "calmar"), _s(bt, "hit", True, 1),
                     _s(bt, "turnover", True, 0), _s(bt, "avg_n", False, 0),
                     _s(bt, "cash", True, 0)])
    LOG.table(rows, ["구성", "정의", "CAGR", "누적", "변동성", "MDD", "Sharpe",
                     "Calmar", "적중률", "회전율", "종목수", "현금"],
              ["c", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"], maxw=34)
    LOG.info("현금 = 거래대금 참여율 상한·종목당 최대비중 때문에 채우지 못한 비중입니다. "
             "소형주 용량 제약이 실제로 얼마나 무는지를 보여줍니다(0% 가 아니면 그만큼 "
             "자본이 놀고 있다는 뜻입니다).")
    LOG.info("EW = 유니버스 동일가중(이 파일이 같은 데이터·같은 비용모형으로 직접 측정). "
             "벤치마크 수치를 인용하지 않는다는 원칙 5 를 코드로 지킵니다.")


def report_yearly(bts: Dict[str, dict], bench_ew: dict):
    """연도별 수익률. 특정 연도 하나가 전체를 만든 것인지 본다."""
    series = {}
    for k in ("A", "C", "D"):
        bt = bts.get(k)
        if bt and len(bt.get("returns", [])):
            R = bt["returns"]
            series[k] = R.set_index("month")["ret"]
    if bench_ew and len(bench_ew.get("returns", [])):
        series["EW"] = bench_ew["returns"].set_index("month")["ret"]
    if not series:
        return
    yrs = sorted({int(pd.Timestamp(i).year) for s in series.values() for i in s.index})
    rows = []
    for y in yrs:
        row = [str(y)]
        for k in ("D", "C", "A", "EW"):
            if k not in series:
                continue
            s = series[k]
            sel = s[[pd.Timestamp(i).year == y for i in s.index]]
            row.append(f"{100*((1+sel).prod()-1):.1f}%" if len(sel) else "—")
        rows.append(row)
    hdr = ["년도"] + [k for k in ("D", "C", "A", "EW") if k in series]
    LOG.table(rows, hdr, ["c"] + ["r"] * (len(hdr) - 1),
              title="연도별 수익률 — 한 해가 전체를 만든 것인지 확인")


def report_subperiod(bt: dict):
    R = (bt or {}).get("returns")
    if R is None or len(R) < 24:
        return
    R = R.sort_values("month").reset_index(drop=True)
    h = len(R) // 2
    rows = []
    for lab, part in (("전반", R.iloc[:h]), ("후반", R.iloc[h:])):
        s = perf_stats(part)
        rows.append([lab, f"{part['month'].iloc[0]:%Y-%m}~{part['month'].iloc[-1]:%Y-%m}",
                     f"{100*s['cagr']:.1f}%", f"{100*s['mdd']:.1f}%", f"{s['sharpe']:.2f}",
                     f"{s['calmar']:.2f}"])
    LOG.table(rows, ["구간", "기간", "CAGR", "MDD", "Sharpe", "Calmar"],
              ["c", "l", "r", "r", "r", "r"],
              title="하위기간 안정성 — 한쪽 구간에만 성과가 몰려 있는가")


def right_tail_contribution(bt: dict):
    """상위 5% 종목-월을 빼면 성과가 사라지는가. 이 전략은 우측꼬리 의존적일 수 있다."""
    H = (bt or {}).get("holdings")
    R = (bt or {}).get("returns")
    if H is None or len(H) == 0 or R is None or len(R) == 0:
        return
    H = H.copy()
    H["contrib"] = H["w"] * H["fwd_ret"]
    thr = H["contrib"].quantile(0.95)
    trimmed = H.copy()
    trimmed.loc[trimmed["contrib"] > thr, "contrib"] = thr
    g0 = H.groupby("month", observed=True)["contrib"].sum()
    g1 = trimmed.groupby("month", observed=True)["contrib"].sum()
    cost = R.set_index("month")["cost"].reindex(g0.index).fillna(0.0)
    s0 = perf_stats(pd.DataFrame({"month": g0.index, "ret": (g0 - cost).to_numpy()}))
    s1 = perf_stats(pd.DataFrame({"month": g1.index, "ret": (g1 - cost).to_numpy()}))
    LOG.table([["원본", f"{100*s0['cagr']:.2f}%", f"{s0['calmar']:.2f}"],
               ["상위5% 기여 절단", f"{100*s1['cagr']:.2f}%", f"{s1['calmar']:.2f}"]],
              ["구성", "CAGR", "Calmar"], ["l", "r", "r"],
              title="우측꼬리 의존도 — 소수 대박 종목이 성과 전부인가")
    if np.isfinite(s0["cagr"]) and np.isfinite(s1["cagr"]) and s0["cagr"] > 0:
        drop = 1 - (s1["cagr"] / s0["cagr"]) if s0["cagr"] else np.nan
        if np.isfinite(drop) and drop > 0.6:
            LOG.warn(f"상위 5% 기여를 자르면 CAGR 이 {100*drop:.0f}% 사라집니다. "
                     f"소수 종목 의존적이므로 실제 운용에서 재현성이 낮을 수 있습니다.")


def report_interpretation(P: pd.DataFrame, fw_table: pd.DataFrame):
    LOG.banner("해석표", "신호가 실제로 무엇을 골랐는가")
    sel = P[P["Signal"] > 0]
    if len(sel) == 0:
        LOG.warn("신호가 발생한 행이 없습니다.")
        return
    rows = []
    for c, nm in [("i_sales", "매출 성장 Δlog(매출TTM)"), ("i_turn", "회전 개선 −Δ(DIO+DSO)"),
                  ("i_accr", "발생액 개선 −ΔAccruals"), ("pbr", "PBR"),
                  ("d1_trailing", "반영도 ΔlogM−ΔlogE"), ("adv20", "20일 평균거래대금")]:
        if c not in P.columns:
            continue
        a = pd.to_numeric(col(P, c), errors="coerce")
        b = pd.to_numeric(col(sel, c), errors="coerce")
        rows.append([nm, f"{a.median():,.3f}" if a.notna().any() else "—",
                     f"{b.median():,.3f}" if b.notna().any() else "—",
                     f"{100*b.notna().mean():.0f}%" if len(b) else "—"])
    LOG.table(rows, ["지표", "유니버스 중앙값", "선정종목 중앙값", "선정종목 관측률"],
              ["l", "r", "r", "r"],
              title="선정 종목의 성격 — 정말 '제약이 풀린 기업'을 고르고 있는가")

    yr = sel["month"].dt.year
    rows2 = [[str(y), f"{int((yr == y).sum()):,}",
              f"{sel.loc[yr == y, 'Signal'].mean():.4f}",
              f"{int(P.loc[P['month'].dt.year == y, 'FW'].sum()):,}"]
             for y in sorted(yr.unique())]
    LOG.table(rows2, ["년도", "신호 발생 종목월", "평균 신호", "방화벽 통과 종목월"],
              ["c", "r", "r", "r"], title="연도별 신호 생성량 — 특정 시기에만 작동하는가")
    if fw_table is not None and len(fw_table):
        LOG.table(fw_table.values.tolist(), list(fw_table.columns),
                  ["l", "c", "r", "r", "l"], title="방화벽 조항별 기여 (재출력)")


def diagnostic_card(P: pd.DataFrame, bt: dict, sec: pd.DataFrame, top_n: int = 6):
    """최근 시점 선정 종목의 '왜 골랐는가' 카드. 숫자가 아니라 논거를 본다."""
    H = (bt or {}).get("holdings")
    if H is None or len(H) == 0:
        return
    last_m = H["month"].max()
    cur = H[H["month"] == last_m].nlargest(top_n, "w")
    nm = sec.drop_duplicates("code").set_index("code")["name"].to_dict() if len(sec) else {}
    Pm = P[P["month"] == last_m].set_index("code")
    LOG.banner(f"진단 카드 — {pd.Timestamp(last_m):%Y-%m} 보유 상위 {len(cur)}종목",
               "각 종목이 어느 논거로 들어왔는지")
    rows = []
    for r in cur.itertuples(index=False):
        c = r.code
        g = (lambda k: (f"{float(Pm.at[c, k]):,.3f}"
                        if c in Pm.index and k in Pm.columns and pd.notna(Pm.at[c, k]) else "—"))
        rows.append([c, _trunc(nm.get(c, ""), 14), f"{100*r.w:.1f}%", f"{r.signal:.4f}",
                     g("i_sales"), g("i_turn"), g("i_accr"), g("pbr"), g("d1_trailing")])
    LOG.table(rows, ["코드", "종목명", "비중", "신호", "매출↑", "회전↑", "발생액↑",
                     "PBR", "반영도"], ["l", "l", "r", "r", "r", "r", "r", "r", "r"])
    LOG.info("반영도(ΔlogM−ΔlogE)가 0 에 가까워지면 청산 게이트가 발동합니다(§10).")


def report_ledger_integrity(rep: Optional[pd.DataFrame], A: Optional[pd.DataFrame],
                            L: Optional[pd.DataFrame], P: Optional[pd.DataFrame] = None):
    """리포트 ↔ 애널리스트 ↔ 종목 원장이 실제로 연결됐는지 한 화면에 보여준다."""
    LOG.banner("원장 무결성 — 리포트 · 애널리스트 · 종목",
               "다중소스가 하나의 원장으로 합쳐졌는지 · 애널리스트가 식별됐는지")
    if rep is None or len(rep) == 0:
        LOG.warn("수집·적재된 애널리스트 리포트가 없습니다. "
                 "이 전략의 E층은 리포트에 의존하지 않으므로 백테스트는 정상 진행됩니다. "
                 "(U층의 리비전 보조신호만 비활성화됩니다)")
        return
    try:
        audit_linkage(rep, A if A is not None else pd.DataFrame(),
                      L if L is not None else pd.DataFrame())
    except Exception as e:                                             # noqa
        LOG.warn(f"원장 감사 출력 실패({type(e).__name__}) — 아래 요약으로 대체합니다.")
        rows = [["리포트", f"{len(rep):,}행"],
                ["애널리스트", f"{0 if A is None else len(A):,}명"],
                ["리포트-애널리스트 링크", f"{0 if L is None else len(L):,}행"]]
        LOG.table(rows, ["원장", "규모"], ["l", "r"])

    # 전략 유니버스와의 교집합 — '수집은 됐는데 이 전략과 무관한' 경우를 잡는다.
    if P is not None and len(P) and "code" in rep.columns:
        uni_codes = set(P.loc[P.get("u_micro", pd.Series(True, index=P.index)).astype(bool), "code"])
        rc = set(rep["code"].dropna().astype(str))
        inter = uni_codes & rc
        LOG.table([["U-MICRO 유니버스 종목", f"{len(uni_codes):,}"],
                   ["리포트 보유 종목", f"{len(rc):,}"],
                   ["교집합(리포트가 있는 U-MICRO 종목)", f"{len(inter):,}"],
                   ["커버리지", f"{100*len(inter)/max(len(uni_codes),1):.1f}%"]],
                  ["항목", "값"], ["l", "r"],
                  title="리포트 커버리지 × U-MICRO — 소형주 구간이 구조적으로 얇다는 가설의 실측")


def report_dataflow_map():
    LOG.banner("데이터 흐름 지도", "무엇이 어디서 와서 어디로 갔는가")
    _safe_print("""
  [수집 L1]                              [정제/PIT]                 [전략 L2]           [평가 L3/L5]
  FDR 상장/폐지 ─┐
  KIND 상장법인 ─┼→ security_master ──┐
  KRX 스냅샷    ─┘                     │
                                       ├→ Universe(C2/C13) ─┐
  FDR/pykrx/네이버/yfinance 가격 ──────┤                     │
       └→ price_panel(월말·익월시가) ──┘                     ├→ base_panel ─┐
                                                             │              │
  KRX/pykrx/DART 주식총수 → mcap_panel(시총·랭크) ───────────┘              ├→ 셀 정규화(date×업종)
                                                                            │   └→ TP_I2 · TP_I4 → E
  DART 재무(일괄) → tidy → 분기센서(i_sales/i_turn/i_accr) ─→ PIT ──────────┤   └→ 반영도 → U
                                                                            │
  DART 거래소공시(I)·외부감사(F) → 관리종목/감사의견/거래정지 ─→ PIT ───────┤→ S1_FIREWALL
  DART 주요사항(B) → 유증/CB/BW ────────────────────────────→ PIT ───────┤→ V1·V2·V3·V6
                                                                            │
  한경컨센서스 ─┐                                                           └→ Signal = E×U×FW×VETO
  네이버리서치 ─┴→ report_master + analyst_master + link ─→ (U층 보조·원장감사)      │
                                                                                     ▼
                                                      백테스트(A/B/C/D) → 성과 → R0/R2-M/R3/R5-M/R9
""".rstrip())
    LOG.info("공용 인덱스(_shared)에 적재되는 것 = 원본·범용 정제본(가격·시총·재무·공시·리포트 원장). "
             "전용 인덱스에 적재되는 것 = 이 전략의 해석물(패널·스코어·백테스트).")



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-K  CANARY K1~K6 (§2)                                                                  ║
# ║                                                                                          ║
# ║  본 수집을 시작하기 전에 '작은 표본'으로 각 데이터원이 살아 있는지 실측한다.               ║
# ║  하나라도 FAIL 이면 그 항목에 의존하는 단계를 제거하고, 무엇을 어떻게 조치했는지           ║
# ║  표 상단에 먼저 출력한다. 조용히 넘어가지 않는다.                                          ║
# ║                                                                                          ║
# ║  ★ K5(상장폐지 목록) 실패는 킬 기준이다 — C2(생존자편향 제거)가 불가능해지기 때문이다.     ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CANARY: List[dict] = []


def _k(kid: str, item: str, passed: Optional[bool], measured: str, action: str = ""):
    CANARY.append({"id": kid, "item": item, "passed": passed,
                   "measured": measured, "action": action})
    icon = "—" if passed is None else ("PASS" if passed else "FAIL")
    (LOG.ok if passed else (LOG.info if passed is None else LOG.warn))(
        f"[{kid}] {icon} {item} — {measured}" + (f" → {action}" if action else ""))


def run_canary(sec: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, bool]:
    """K1~K6 실측. 반환: 기능별 활성 여부 딕셔너리."""
    LOG.banner("CANARY K1~K6", "본 수집 전 소표본 실측 — FAIL 항목은 의존 단계를 제거하고 보고한다")
    CANARY.clear()
    caps = {"dart_fin": False, "dart_bulk": False, "price": False,
            "delisting": False, "watchlist": False}

    codes = [c for c in sec["code"].dropna().astype(str).tolist()][:200] if len(sec) else []
    ccs = (sec.dropna(subset=["corp_code"])["corp_code"].astype(str).tolist()[:60]
           if "corp_code" in sec.columns else [])

    # ── K1 · K2 : DART 재무 취득 가능성과 최초 제공 분기 ──────────────────────────────────
    if not DART_API_KEY:
        _k("K1", "DART 재무 취득", False, "DART_API_KEY 미입력",
           "재무 의존 항목(E층·방화벽 재무조항) 전면 비활성. 드라이브 캐시가 있으면 그것만 사용")
        _k("K2", "최초 제공 분기", None, "K1 미충족으로 미검사")
        _k("K3", "필수 계정 커버리지", None, "K1 미충족으로 미검사")
    else:
        smp = ccs[:12]
        got = pd.DataFrame()
        try:
            got = fetch_dart_financials(smp, [2016]) if smp else pd.DataFrame()
        except Exception as e:                                         # noqa
            LOG.debug(f"K1 표본 조회 실패: {type(e).__name__}")
        n1 = len(got)
        ok1 = n1 > 0
        caps["dart_fin"] = ok1
        _k("K1", "DART 재무 2016 표본 취득", ok1,
           f"표본 {len(smp)}사 → {n1:,}행",
           "" if ok1 else "fnlttMultiAcnt 배치 폴백으로 전환 (코드가 자동 처리)")

        # K2 — 2016Q1 이전 데이터가 실제로 오는지
        if ok1 and "bsns_year" in got.columns:
            yrs = pd.to_numeric(got["bsns_year"], errors="coerce").dropna()
            ymin = int(yrs.min()) if len(yrs) else 9999
            ok2 = ymin <= 2016
            _k("K2", "최초 제공 연도 ≤ 2016", ok2, f"실측 최초 연도 {ymin}",
               "" if ok2 else f"백테스트 시작을 {ymin}년으로 상향해야 합니다")
        else:
            _k("K2", "최초 제공 연도 ≤ 2016", None, "표본 없음")

        # K3 — 필수 계정 커버리지
        if ok1:
            try:
                W = tidy_financials(got)
                need = {"revenue": "매출", "cogs": "매출원가", "inventory": "재고",
                        "receivable": "매출채권", "cfo": "영업CF",
                        "tax_expense": "법인세비용", "interest_expense": "이자비용"}
                rows, bad = [], []
                for k, nm in need.items():
                    covg = float(W[k].notna().mean()) if k in W.columns and len(W) else 0.0
                    rows.append([nm, f"{100*covg:.0f}%", "PASS" if covg >= 0.80 else "FAIL"])
                    if covg < 0.80:
                        bad.append(nm)
                LOG.table(rows, ["계정", "커버리지", "판정"], ["l", "r", "c"],
                          title="K3 — 필수 계정 커버리지 (표본 기준)")
                _k("K3", "필수 계정 커버리지 ≥80%", len(bad) == 0,
                   f"미달 {len(bad)}개: {bad[:5]}" if bad else "전 계정 충족",
                   "미달 계정을 쓰는 지표는 결측으로 남습니다(0 으로 채우지 않음)" if bad else "")
            except Exception as e:                                     # noqa
                _k("K3", "필수 계정 커버리지", None, f"정제 실패 {type(e).__name__}")

    # ── K4 : 가격 취득 ────────────────────────────────────────────────────────────────────
    smp_px = codes[:25]
    px = pd.DataFrame()
    if smp_px and RUN_MODE != "CACHED":
        try:
            px = fetch_prices(smp_px, BACKTEST_START, BACKTEST_END)
        except Exception as e:                                         # noqa
            LOG.debug(f"K4 표본 가격 실패: {type(e).__name__}")
    n_ok = int(px["code"].nunique()) if len(px) else 0
    ok4 = n_ok >= max(1, int(0.6 * len(smp_px)))
    caps["price"] = ok4 or RUN_MODE == "CACHED"
    _k("K4", "가격 10년 취득", ok4 if smp_px else None,
       f"표본 {len(smp_px)}종목 중 {n_ok}종목 성공" if smp_px else "표본 없음",
       "" if ok4 else "FDR→네이버→yfinance→캐시 순으로 자동 폴백합니다")

    # ── K5 : 상장폐지 목록 (킬 기준) ──────────────────────────────────────────────────────
    n_del = int(sec["delisting_date"].notna().sum()) if "delisting_date" in sec.columns else 0
    ok5 = n_del > 0
    caps["delisting"] = ok5
    _k("K5", "상장폐지 목록 확보 ⭐", ok5, f"폐지일 보유 {n_del:,}종목",
       "" if ok5 else "C2(생존자편향 제거) 불가 — 킬 기준")
    if not ok5 and STOP_ON_KILL_CRITERIA and RUN_MODE == "FULL":
        raise KillCriteria(
            "상장폐지 목록을 확보하지 못했습니다(K5). 생존자편향을 제거할 수 없으므로 "
            "중단합니다(§12-1). 살아남은 종목만으로 낸 수익률은 실제로 달성 불가능한 값입니다.")

    # ── K6 : 관리종목·감사의견 이력 ──────────────────────────────────────────────────────
    ok6 = None
    if DART_API_KEY and RUN_MODE != "CACHED":
        try:
            probe_start = str(pd.Timestamp(BACKTEST_END) - pd.DateOffset(months=2))[:10]
            act = fetch_market_actions(probe_start, BACKTEST_END)
            ok6 = len(act) > 0
            caps["watchlist"] = bool(ok6)
            _k("K6", "관리종목·감사의견 이력", ok6, f"최근 2개월 이벤트 {len(act):,}건",
               "" if ok6 else "방화벽의 관리종목/감사의견/거래정지 조항을 비활성화하고 진행")
        except Exception as e:                                         # noqa
            _k("K6", "관리종목·감사의견 이력", False, f"조회 실패 {type(e).__name__}",
               "해당 방화벽 조항 비활성화")
    else:
        _k("K6", "관리종목·감사의견 이력", None,
           "DART 키 미입력 또는 CACHED 모드", "캐시에 있으면 사용합니다")

    # ── 요약표 (FAIL 을 맨 위로) ──────────────────────────────────────────────────────────
    order = sorted(CANARY, key=lambda r: (r["passed"] is not False, r["id"]))
    LOG.table([[r["id"], _trunc(r["item"], 30),
                "—" if r["passed"] is None else ("PASS" if r["passed"] else "★FAIL"),
                _trunc(r["measured"], 34), _trunc(r["action"], 40)] for r in order],
              ["ID", "확인 항목", "판정", "실측", "FAIL 시 조치"],
              ["c", "l", "c", "l", "l"], maxw=44,
              title="CANARY 실측 결과 (FAIL 항목을 위로 정렬)")
    n_fail = sum(1 for r in CANARY if r["passed"] is False)
    if n_fail:
        LOG.warn(f"CANARY {n_fail}건 FAIL — 위 '조치' 열대로 해당 단계를 제거하고 진행합니다. "
                 f"임계를 낮춰 통과시키지 않습니다.")
    else:
        LOG.ok("CANARY 전 항목 통과.")
    return caps


def write_canary_report(path: str) -> Optional[str]:
    if not CANARY:
        return None
    lines = ["# CANARY 실측 보고 (TCD v3 · MICRO-FW)", "",
             f"- 생성: {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
             f"- 백테스트 구간: {BACKTEST_START} ~ {BACKTEST_END}", "",
             "| ID | 확인 항목 | 판정 | 실측 | 조치 |", "|---|---|---|---|---|"]
    for r in sorted(CANARY, key=lambda x: (x["passed"] is not False, x["id"])):
        v = "—" if r["passed"] is None else ("PASS" if r["passed"] else "**FAIL**")
        lines.append(f"| {r['id']} | {r['item']} | {v} | {r['measured']} | {r['action']} |")
    try:
        atomic_write_text(path, "\n".join(lines) + "\n")
        return path
    except Exception:
        return None



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  L0-T  계약 자동검정 + 합성 스모크                                                        ║
# ║                                                                                          ║
# ║  두 검증은 서로 다른 것을 본다:                                                           ║
# ║   ① 계약검정 — 협상 불가 규칙(C1 PIT · C2 생존자편향 · C13 유니버스PIT · C14 셀 ·          ║
# ║      TP 부호 · 거부권 이진성)이 코드에 실제로 구현돼 있는가                                ║
# ║   ② 합성 스모크 — 네트워크 없이 '계산 경로 전체'가 끝까지 도는가                           ║
# ║      (수집부 한 줄 때문에 2분 만에 죽는 사고를 여기서 먼저 잡는다)                         ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACTS: List[dict] = []


def _c(cid: str, name: str, fn):
    try:
        ok, detail = fn()
    except Exception as e:                                             # noqa
        ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
    CONTRACTS.append({"id": cid, "name": name, "ok": bool(ok), "detail": str(detail)})


def run_contracts() -> bool:
    CONTRACTS.clear()

    # ── C1: PIT — merge_asof 결합이 미래를 절대 보지 않는다 ────────────────────────────
    def c1():
        grid = pd.DataFrame({"corp_code": ["A"] * 4,
                             "month": pd.to_datetime(["2020-01-31", "2020-02-29",
                                                      "2020-03-31", "2020-04-30"])})
        src = pd.DataFrame({"corp_code": ["A", "A"],
                            "knowledge_date": pd.to_datetime(["2020-02-15", "2020-04-10"]),
                            "val": [1.0, 2.0]})
        m = pd.merge_asof(grid.sort_values("month"), src.sort_values("knowledge_date"),
                          left_on="month", right_on="knowledge_date", by="corp_code",
                          direction="backward")
        if pd.notna(m.loc[0, "val"]):
            return False, "1월에 2월 공시값이 보입니다 — 미래누수."
        if not (m["knowledge_date"].dropna() <= m["month"][m["knowledge_date"].notna()]).all():
            return False, "knowledge_date > month 인 행이 존재합니다."
        if float(m.loc[3, "val"]) != 2.0:
            return False, "4월에 4/10 공시가 반영되지 않았습니다."
        return True, "backward as-of 결합이 knowledge_date ≤ month 를 강제함을 확인"

    # ── C2: 상장폐지 종목 포함 + 정리매매 없으면 -100% ────────────────────────────────
    def c2():
        months = pd.date_range("2020-01-31", periods=3, freq=pd.offsets.MonthEnd())
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["a", "b"],
                            "market": ["KOSPI"] * 2,
                            "listing_date": pd.to_datetime(["2010-01-01"] * 2),
                            "delisting_date": [pd.NaT, pd.Timestamp("2020-02-20")],
                            "industry": ["X", "X"], "corp_code": ["A", "B"], "src": ["t", "t"]})
        px = pd.DataFrame({"code": ["000001"] * 3, "date": months})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        at_jan = uni.at(pd.Timestamp("2020-01-31"))
        at_mar = uni.at(pd.Timestamp("2020-03-31"))
        if "000002" not in at_jan:
            return False, "폐지 예정 종목이 폐지 전 유니버스에서 빠졌습니다 — 생존자편향."
        if "000002" in at_mar:
            return False, "폐지일 이후에도 유니버스에 남아 있습니다."
        P = pd.DataFrame({"code": ["000002"], "month": [pd.Timestamp("2020-01-31")],
                          "Signal": [1.0], "fwd_ret": [np.nan], "adv20": [1e9],
                          "VETO": [1.0], "FW": [1], "close": [1000.0], "d1_trailing": [-0.5]})
        bt = run_backtest_micro(P, pd.DatetimeIndex([pd.Timestamp("2020-01-31")]), uni,
                                "D", COST_BASE_SCENARIO, label="C2TEST", quiet=True)
        H = bt["holdings"]
        if H is None or len(H) == 0:
            return False, "백테스트가 보유내역을 만들지 않았습니다."
        # ★ 포트폴리오 수익률이 아니라 '그 종목의' 수익률이 -100% 여야 한다.
        #   포트폴리오 수익률은 비중(용량 상한·현금)에 좌우되므로 C2 의 판정 대상이 아니다.
        pos = float(H["fwd_ret"].iloc[0])
        if pos > -0.999:
            return False, (f"정리매매가 없는 폐지 종목의 종목수익률이 {pos:.3f} 입니다. "
                           f"-100% 여야 합니다.")
        return True, (f"폐지 전 포함 · 폐지 후 제외 · 정리매매 없으면 종목수익률 "
                      f"{pos:.0%} 강제 확인")

    # ── C13: 유니버스는 PIT — 미래 상장 종목이 섞이지 않는다 ──────────────────────────
    def c13():
        sec = pd.DataFrame({"code": ["000001", "000002"], "name": ["a", "b"],
                            "market": ["KOSPI"] * 2,
                            "listing_date": pd.to_datetime(["2010-01-01", "2023-05-01"]),
                            "delisting_date": [pd.NaT, pd.NaT], "industry": ["X", "X"],
                            "corp_code": ["A", "B"], "src": ["t", "t"]})
        px = pd.DataFrame({"code": ["000001"] * 3,
                           "date": pd.date_range("2020-01-31", periods=3, freq=pd.offsets.MonthEnd())})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        if "000002" in uni.at(pd.Timestamp("2020-06-30")):
            return False, "2023년 상장 종목이 2020년 유니버스에 있습니다 — 미래누수."
        # 랭크가 시점별로 재산출되는지 (현재 시총을 과거에 적용하지 않는다)
        pm = pd.DataFrame({"code": ["000001", "000002"] * 2,
                           "month": [pd.Timestamp("2020-01-31")] * 2 + [pd.Timestamp("2020-02-29")] * 2,
                           "close": [100.0, 200.0, 300.0, 50.0]})
        snap = pd.DataFrame({"snap_date": pd.to_datetime(["2019-12-31"] * 2),
                             "code": ["000001", "000002"], "shares": [10.0, 10.0],
                             "mcap": [np.nan, np.nan], "src": ["t", "t"]})
        M = build_mcap_panel(pm, snap, sec, pd.DatetimeIndex(sorted(pm["month"].unique())))
        r1 = M[M["month"] == pd.Timestamp("2020-01-31")].set_index("code")["mcap_rank"]
        r2 = M[M["month"] == pd.Timestamp("2020-02-29")].set_index("code")["mcap_rank"]
        if not (r1["000001"] > r1["000002"] and r2["000001"] < r2["000002"]):
            return False, "시총 랭크가 시점별로 재산출되지 않습니다 — 현재 시총의 과거 적용."
        return True, "미래 상장 배제 + 시총 랭크의 시점별 재산출 확인 (C13-a)"

    # ── C14: 셀 키에 size_bucket 이 없다 ──────────────────────────────────────────────
    def c14():
        if "size_bucket" in CELL_MICRO:
            return False, "CELL_MICRO 에 size_bucket 이 들어 있습니다(C14-a 위반)."
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(60)],
                          "month": pd.Timestamp("2020-06-30"),
                          "close": 1000.0})
        sec = pd.DataFrame({"code": P["code"], "industry": ["전자부품 제조업"] * 30 + ["의료기기"] * 30})
        Q = build_cells_micro(P, sec, min_n=20)
        s = str(Q["cell"].iloc[0])
        if "|" not in s or len(s.split("|")) != 2:
            return False, f"셀 키 형식이 (연월|업종) 이 아닙니다: {s}"
        if any("size" in str(c).lower() for c in Q.columns if c.startswith("cell")):
            return False, "셀 컬럼에 규모 정보가 섞였습니다."
        return True, f"셀 키 = (연월|업종) 확인 · 예: {s}"

    # ── TP 부호: clip(z,0)×clip(z,0) — 저-저 사분면이 최고점을 받지 않는다 ────────────
    def tpsign():
        n = 40
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)],
            "month": pd.Timestamp("2020-06-30"),
            "cell": "202006|X", "cell_l2": "202006|X", "cell_l3": "202006|ALL",
            "a": np.linspace(-1, 1, n), "b": np.linspace(-1, 1, n)})
        # 마지막 행: 둘 다 최저(저-저). 첫 행보다 점수가 높으면 부호 버그.
        P.loc[n - 1, ["a", "b"]] = [-5.0, -5.0]
        P.loc[n - 2, ["a", "b"]] = [5.0, 5.0]
        t = tp_micro(P, "a", "b")
        lowlow, highhigh = float(t.iloc[n - 1]), float(t.iloc[n - 2])
        if not (lowlow <= 1e-9):
            return False, (f"저-저 사분면 점수가 {lowlow:.4f} 입니다. 0 이어야 합니다 — "
                           f"z×z 를 쓰면 '양쪽 다 나쁨'이 최고점을 받습니다(원칙 2 위반).")
        if not (highhigh > lowlow):
            return False, "고-고 사분면이 저-저보다 높지 않습니다."
        # 고-저(한쪽만 좋음)는 0 이어야 한다
        P2 = P.copy()
        P2.loc[0, ["a", "b"]] = [5.0, -5.0]
        t2 = tp_micro(P2, "a", "b")
        if float(t2.iloc[0]) > 1e-9:
            return False, "한쪽만 개선된 경우에 점수가 났습니다 — 대가를 치렀는데 보상했습니다."
        return True, f"저-저={lowlow:.3f} · 고-고={highhigh:.3f} · 고-저=0 확인 (clip 곱)"

    # ── 거부권 이진성 (C6) ───────────────────────────────────────────────────────────
    def veto():
        P = pd.DataFrame({"code": ["000001", "000002", "000003"],
                          "month": pd.Timestamp("2020-06-30"), "corp_code": ["A", "B", "C"],
                          "v1_pushout": [1.0, 0.0, 0.0], "v2_bad_3q": [0.0, 1.0, 0.0],
                          "adv20": [1e9, 1e9, 1.0], "is_trading_halted": [0.0, 0.0, 0.0],
                          "shares": [np.nan] * 3})
        Q = apply_vetoes_micro(P, None)
        vals = set(pd.unique(Q[["V1", "V2", "V3", "V6"]].to_numpy().ravel()))
        if not vals <= {0.0, 1.0}:
            return False, f"거부권이 이진이 아닙니다: {sorted(vals)}"
        if float(Q["VETO"].iloc[0]) != 0.0 or float(Q["VETO"].iloc[2]) != 0.0:
            return False, "거부권이 곱으로 적용되지 않았습니다(상쇄 발생)."
        return True, "V1/V2/V3/V6 이진값 · 곱 적용 · 상쇄 불가 확인"

    # ── 선정 랭크가 원점수의 단조함수인가 (월 전체 기준) ──────────────────────────────
    def rankmono():
        n = 50
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "month": pd.Timestamp("2020-06-30"),
                          "E_micro": np.linspace(0, 1, n), "U_micro": 1.0,
                          "FW": 1, "VETO": 1.0, "adv20": 1e9})
        S = assemble_signal(P, "D")
        d = S[["Signal", "Signal_rank"]].dropna()
        rho = float(np.corrcoef(d["Signal"].rank(), d["Signal_rank"].rank())[0, 1])
        if not rho > 0.999:
            return False, f"Signal_rank 가 Signal 의 단조함수가 아닙니다 (ρ={rho:.4f})."
        return True, f"월 전체 백분위 · 단조성 ρ={rho:.4f} 확인"

    # ── 비용 단조성: 비용이 커지면 수익률은 낮아져야 한다 ────────────────────────────
    def costmono():
        months = pd.date_range("2020-01-31", periods=6, freq=pd.offsets.MonthEnd())
        rows = []
        for m in months:
            for i in range(10):
                rows.append({"code": f"{i:06d}", "month": m, "Signal": 1.0 - i * 0.05,
                             "fwd_ret": 0.01, "adv20": 1e9, "VETO": 1.0, "FW": 1,
                             "close": 1000.0, "d1_trailing": -0.5})
        P = pd.DataFrame(rows)
        sec = pd.DataFrame({"code": [f"{i:06d}" for i in range(10)], "name": "x",
                            "market": "KOSPI", "listing_date": pd.Timestamp("2010-01-01"),
                            "delisting_date": pd.NaT, "industry": "X",
                            "corp_code": [f"C{i}" for i in range(10)], "src": "t"})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000000"] * 6, "date": months}))
        a = run_backtest_micro(P, months, uni, "D", "낙관", label="c1", quiet=True)
        b = run_backtest_micro(P, months, uni, "D", "비관", label="c2", quiet=True)
        if not (a["stats"]["cagr"] > b["stats"]["cagr"]):
            return False, (f"비용이 큰 시나리오의 수익률이 더 높습니다 "
                           f"(낙관 {a['stats']['cagr']:.4f} vs 비관 {b['stats']['cagr']:.4f}).")
        return True, (f"낙관 {100*a['stats']['cagr']:.2f}% > 비관 "
                      f"{100*b['stats']['cagr']:.2f}% — 비용 모형 단조성 확인")

    # ── 시장조치 상태 복원: 해제가 먼저 관측돼도 이후 지정이 살아야 한다 ──────────────
    def watchstate():
        ev = pd.DataFrame({
            "code": ["000001"] * 3,
            "rcept_dt": pd.to_datetime(["2017-03-15", "2018-06-20", "2019-02-10"]),
            "action": ["watch_off", "watch_on", "watch_off"]})
        S = _step_state(ev, "watch_on", "watch_off", "code")
        m = dict(zip(S["knowledge_date"], S["state"]))
        if int(m[pd.Timestamp("2018-06-20")]) != 1:
            return False, ("이력 시작 전 지정 때문에 이후의 진짜 '관리종목 지정'이 0 으로 "
                           "읽힙니다 — 누적합 방식의 고질적 버그입니다.")
        if int(m[pd.Timestamp("2019-02-10")]) != 0:
            return False, "해제 이벤트가 상태를 끄지 못했습니다."
        return True, "해제 선행 이력에서도 이후 지정이 정상 복원됨 (최근 이벤트 기준)"

    # ── 단발 사건(감사의견 비적정)의 만료가 나중 사건을 끄면 안 된다 ────────────────────
    def oneshot():
        ev = pd.DataFrame({"code": ["000001"] * 2,
                           "rcept_dt": pd.to_datetime(["2019-03-20", "2020-03-25"]),
                           "action": ["audit_bad", "audit_bad"]})
        S = _one_shot_state(ev, "audit_bad", "code", valid_days=400)
        S = S.sort_values("knowledge_date")
        probe = pd.Timestamp("2020-06-30")
        st = S[S["knowledge_date"] <= probe]["state"].iloc[-1]
        if int(st) != 1:
            return False, ("2020-03 비적정 이후인데 2019 건의 만료행이 상태를 꺼 버렸습니다 "
                           "(만료는 누적 최댓값이어야 합니다).")
        return True, "연속 단발 사건에서 나중 사건이 앞 사건의 만료에 지워지지 않음"

    # ── ★ 그 반대 방향이 더 위험하다: 미래 사건이 과거 상태를 켜면 안 된다(C1) ──────────
    def oneshot_pit():
        """2017년 사건 + 2024년 사건 → 2019년의 상태는 반드시 0.

        예전 구현은 만료행을 '종목별 마지막 만료' 하나로 접었다. 그러면 2017-03 부터
        2025-03 까지 97개월이 통째로 켜진다 — 2019년 패널이 '감사의견 비적정'이라고
        말하는 근거가 5년 뒤에야 존재할 공시다. 방향도 나쁘다(나중에 망할 기업을 미리
        배제 → 성과 과대). 위 oneshot 검정만으로는 이 실패를 절대 잡지 못한다.
        """
        ev = pd.DataFrame({"code": ["000001"] * 2,
                           "rcept_dt": pd.to_datetime(["2017-03-20", "2024-03-20"]),
                           "action": ["audit_bad", "audit_bad"]})
        S = _one_shot_state(ev, "audit_bad", "code", valid_days=400).sort_values("knowledge_date")
        probe = pd.Timestamp("2019-06-30")
        prior = S[S["knowledge_date"] <= probe]
        st = int(prior["state"].iloc[-1]) if len(prior) else 0
        if st != 0:
            return False, ("2019-06 시점의 상태가 1 입니다 — 2024년 공시가 과거를 켰습니다. "
                           "미래누수(C1) 입니다.")
        after = S[S["knowledge_date"] <= pd.Timestamp("2024-06-30")]
        if not len(after) or int(after["state"].iloc[-1]) != 1:
            return False, "2024-03 사건 직후 상태가 1 이 아닙니다(만료 처리가 과했습니다)."
        return True, "7년 간격 단발 사건: 2019-06=0 · 2024-06=1 — 미래가 과거를 바꾸지 않음"

    # ── DART 전기 비교치 파싱 · 분기금액 누적여부 자동판정 ──────────────────────────────
    def comparatives():
        """이 전략의 증거층 전체가 여기에 걸려 있다.

        ① 분기 손익금액이 '3개월 단독'인데 누적으로 오인하면 차분이 음수·양수를 오가며
           TTM 이 무의미해진다(반대로 오인하면 매출이 계단식으로 튄다). 둘 다 에러 없이
           값만 틀린다 → 데이터로 판정하는지 검정한다.
        ② 연 1회만 공시하는 기업(U-MICRO 에 흔하다)의 전기 비교치가 비면 i_sales 가
           통째로 결측이 되고 C14-c 로 증거층이 죽는다 → 사업보고서 단독 이력으로 검정한다.
        """
        FY, Q1, H1, Q3 = (REPRT_CODES["FY"], REPRT_CODES["Q1"],
                          REPRT_CODES["H1"], REPRT_CODES["Q3"])

        def _row(cc, y, rc, cum, pcum, th, fr):
            return {"corp_code": cc, "bsns_year": y, "reprt_code": rc, "fs_div": "CFS",
                    "sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액",
                    "thstrm_amount": f"{th:,.0f}",
                    "thstrm_add_amount": ("" if cum is None else f"{cum:,.0f}"),
                    "frmtrm_amount": f"{fr:,.0f}",
                    "frmtrm_q_amount": "", "bfefrmtrm_amount": "",
                    "frmtrm_add_amount": ("" if pcum is None else f"{pcum:,.0f}"),
                    "rcept_no": f"{y}0515000001"}

        rows = []
        for y in (2022, 2023, 2024):
            ann, prev = 1000.0 * (1.10 ** (y - 2022)), 1000.0 * (1.10 ** (y - 2023))
            # 분기 제출 기업: 당기금액=3개월 단독, 당기누적=YTD (실제 DART 형식)
            for q, rc in ((1, Q1), (2, H1), (3, Q3)):
                rows.append(_row("00000001", y, rc, ann * q / 4, prev * q / 4,
                                 ann / 4, prev / 4))
            rows.append(_row("00000001", y, FY, None, None, ann, prev))
            # 연 1회 제출 기업: 사업보고서만
            rows.append(_row("00000002", y, FY, None, None, ann, prev))
        W = tidy_financials(pd.DataFrame(rows))
        if W is None or not len(W):
            return False, "tidy_financials 가 빈 프레임을 돌려주었습니다."
        Q = add_micro_sensors_quarterly(W)
        exp = float(np.log(1.10))
        out = []
        for cc, label in (("00000001", "분기제출"), ("00000002", "연1회제출")):
            r = Q[(Q["corp_code"] == cc) & (Q["reprt_code"] == FY) & (Q["bsns_year"] == 2024)]
            if not len(r):
                return False, f"{label} 기업의 2024 사업보고서 행이 없습니다."
            v = float(pd.to_numeric(r["i_sales"], errors="coerce").iloc[0])
            if not np.isfinite(v):
                return False, (f"{label} 기업의 i_sales 가 결측입니다 — 전기 비교치가 "
                               f"파싱되지 않았습니다(연 1회 제출 기업이 죽는 경로).")
            if abs(v - exp) > 0.02:
                return False, (f"{label} 기업의 i_sales={v:.4f} 이 기대값 {exp:.4f}(=log1.10)과 "
                               f"다릅니다. 누적/3개월 오인 또는 lag4 가 여러 해를 건너뛴 결과입니다.")
            out.append(f"{label} {v:.4f}")
        # 3개월 단독 → 누적 복원이 맞으면 FY 의 TTM 이 연간과 같아야 한다
        r1 = Q[(Q["corp_code"] == "00000001") & (Q["reprt_code"] == FY) &
               (Q["bsns_year"] == 2024)]
        ttm = float(pd.to_numeric(r1["revenue_ttm"], errors="coerce").iloc[0])
        ann24 = 1000.0 * (1.10 ** 2)
        if not np.isfinite(ttm) or abs(ttm - ann24) > ann24 * 0.02:
            return False, (f"3개월 단독 공시의 누적 복원이 틀렸습니다 — TTM {ttm:,.0f} vs "
                           f"연간 {ann24:,.0f}.")
        return True, f"i_sales({' · '.join(out)}) = log1.10 · 3개월→TTM 복원 일치"

    # ── 거래정지→수개월 뒤 상장폐지 경로도 -100% 여야 한다 ─────────────────────────────
    def delist_gap():
        months = pd.date_range("2019-04-30", periods=2, freq=pd.offsets.MonthEnd())
        sec = pd.DataFrame({"code": ["000002"], "name": ["b"], "market": ["KOSDAQ"],
                            "listing_date": [pd.Timestamp("2010-01-01")],
                            "delisting_date": [pd.Timestamp("2020-03-15")],
                            "industry": ["X"], "corp_code": ["B"], "src": ["t"]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000002"] * 2, "date": months}))
        P = pd.DataFrame({"code": ["000002"], "month": [months[0]], "Signal": [1.0],
                          "fwd_ret": [np.nan], "adv20": [1e9], "VETO": [1.0], "FW": [1],
                          "close": [1000.0], "d1_trailing": [-0.5]})
        bt = run_backtest_micro(P, pd.DatetimeIndex([months[0]]), uni, "D",
                                COST_BASE_SCENARIO, label="DGAP", quiet=True)
        H = bt["holdings"]
        r = float(H["fwd_ret"].iloc[0]) if H is not None and len(H) else 0.0
        if r > -0.999:
            return False, (f"거래정지 후 수개월 뒤 상장폐지되는 종목의 종목수익률이 {r:.3f} "
                           f"입니다. 폐지월 창만 보면 이 경로가 0% 로 계상되어 생존자편향이 "
                           f"재유입됩니다.")
        return True, "거래 중단 시점에 종목수익률 -100% 확정 (폐지일이 몇 달 뒤여도 동일)"

    # ── 적자기업이 많은 셀에서 밸류 랭크가 통째로 무효화되면 안 된다 ────────────────────
    def valuecell():
        n = 30
        # 30종목 중 22개가 적자(E/P 음수). 싼 흑자기업(0번)과 비싼 적자기업(29번)을 비교한다.
        P = pd.DataFrame({
            "code": [f"{i:06d}" for i in range(n)], "month": pd.Timestamp("2020-06-30"),
            "cell": "202006|X", "cell_l2": "202006|X", "cell_l3": "202006|ALL",
            "bp": np.linspace(3.0, 0.3, n),
            "ep": [0.30 - 0.02 * i if i < 8 else -0.05 - 0.01 * i for i in range(n)]})
        vr = value_rank_micro(P)
        if vr.isna().all():
            return False, ("셀에 적자기업이 많다는 이유로 밸류 랭크가 전원 NaN 이 되었습니다. "
                           "그러면 방화벽의 딥밸류 조항이 흑자기업까지 전원 배제합니다.")
        if not (float(vr.iloc[0]) < float(vr.iloc[n - 1])):
            return False, "저PBR·흑자 기업이 고PBR·적자 기업보다 싸게 평가되지 않았습니다."
        return True, (f"적자 {n-8}/{n} 인 셀에서도 밸류 랭크 유효 "
                      f"(최저 {float(vr.min()):.2f} · 최고 {float(vr.max()):.2f})")

    # ── R2-M 구성 분리: B(증거층만)에는 방화벽·거부권이 남아 있으면 안 된다 ─────────────
    def variantsep():
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(10)],
                          "month": pd.Timestamp("2020-06-30"),
                          "E_micro": np.linspace(0, 1, 10), "U_micro": 1.0,
                          "FW": [0] * 5 + [1] * 5, "VETO": [0.0] * 5 + [1.0] * 5,
                          "adv20": 1e9})
        B = assemble_signal(P, "B")
        if not (B["FW"] == 1).all() or not (B["VETO"] == 1.0).all():
            return False, ("B 구성에 방화벽/거부권 컬럼이 남아 백테스트의 보유 판정에서 "
                           "강제 청산을 일으킵니다 — 정의상 B 가 아니라 C 가 됩니다.")
        D = assemble_signal(P, "D")
        if int(D["FW"].sum()) != 5:
            return False, "D 구성에서 방화벽이 중립화되었습니다."
        return True, "B 는 방화벽·거부권 중립화 · D 는 유지 — 구성 간 분리 확인"

    # ── §10 런타임 예산: 예산을 넘길 것을 알면서 시작하면 안 된다 ──────────────────────
    def budget_guard():
        """실제 사고 재현: 전 종목 단건 수집은 187,920회 = 약 10일. 그걸 시작했었다."""
        corps = [f"{i:08d}" for i in range(3915)]
        years = list(range(2015, 2027))
        plan = plan_dart_collection(corps, years, budget_min=DART_BUDGET_MIN)
        if plan["need_single"] <= plan["cap"]:
            return False, ("전 종목 단건 수집이 예산 안이라고 판정됐습니다 — 견적식이 잘못됐습니다.")
        if plan["need_batch"] > plan["need_single"] / 10:
            return False, "배치 경로가 단건 대비 충분히 싸지 않습니다(배치 산식 오류)."
        if MAX_WALLCLOCK_MIN > 240:
            return False, f"MAX_WALLCLOCK_MIN={MAX_WALLCLOCK_MIN} — 계약 상한(240분)을 넘겼습니다."
        return True, (f"단건 {plan['need_single']:,}회는 예산 {plan['cap']:,}회의 "
                      f"{plan['need_single']/max(plan['cap'],1):.0f}배 → 시작하지 않고 "
                      f"배치({plan['need_batch']:,}회)로 내려감 · 상한 {MAX_WALLCLOCK_MIN}분")

    # ── KRX 차단 페이지를 데이터로 착각하지 않는다 ────────────────────────────────────
    def krx_block_detect():
        html = ('<html><head><title>에러페이지 - 한국거래소 | Data Marketplace</title></head>'
                '<body><div class="ip-block-page"><h1>KRX Data Marketplace</h1>'
                '<h2>KDM 이용 제한 안내</h2><p>자동화 수단을 통한 비정상 대량 조회가 '
                '감지되어 해당 IP의 접속이 일시적으로 제한되었습니다.</p></div></body></html>')
        before = dict(KRX_BLOCK)
        try:
            KRX_BLOCK["blocked"], KRX_BLOCK["until"], KRX_BLOCK["logged"] = False, 0.0, True
            if not _check_krx_block("krx", html):
                return False, ("KRX 차단 안내 페이지를 데이터로 취급했습니다. 차단은 200 OK 로 "
                               "오므로, 못 잡으면 계속 요청해 제한이 연장됩니다.")
            if not krx_blocked():
                return False, "차단을 감지했는데 이후 요청이 막히지 않았습니다."
            if _check_krx_block("naver", html):
                return False, "KRX 가 아닌 소스의 응답까지 차단으로 오인했습니다."
            return True, "차단 페이지 감지 → 이번 실행 KRX 전면 중단 + 마커 저장 확인"
        finally:
            KRX_BLOCK.update(before)

    _c("BUDGET", "런타임 예산 강제 (§10)", budget_guard)
    _c("KRXBLK", "KRX 차단 페이지 감지", krx_block_detect)
    _c("C1", "PIT (미래누수 차단)", c1)
    _c("C2", "생존자편향 제거 · 상폐 -100%", c2)
    _c("C13", "유니버스 PIT · 랭크 시점별 재산출", c13)
    _c("C14", "셀 = (연월, 업종) · size_bucket 금지", c14)
    _c("TP", "TP 부호 (clip 곱, z×z 금지)", tpsign)
    _c("V", "거부권 이진 · 곱 · 상쇄불가", veto)
    _c("RANK", "선정 랭크 정합성", rankmono)
    _c("COST", "비용 모형 단조성", costmono)
    _c("WATCH", "관리종목 상태 복원 (해제 선행)", watchstate)
    _c("AUDIT", "단발 사건 만료 누적 최댓값", oneshot)
    _c("APIT", "단발 사건 미래→과거 누수 금지", oneshot_pit)
    _c("COMPAR", "DART 전기 비교치 · 누적 자동판정", comparatives)
    # ── 폐지일을 아예 모르는 종목의 거래중단도 -100% 여야 한다 ──────────────────────────
    def delist_nomap():
        months = pd.date_range("2019-04-30", periods=2, freq=pd.offsets.MonthEnd())
        sec = pd.DataFrame({"code": ["000003", "000004"], "name": ["c", "d"],
                            "market": ["KOSDAQ"] * 2,
                            "listing_date": [pd.Timestamp("2010-01-01")] * 2,
                            "delisting_date": [pd.NaT, pd.NaT],   # ★ 둘 다 폐지목록에 없다
                            "industry": ["X", "X"], "corp_code": ["C", "D"], "src": ["t", "t"]})
        uni = Universe(sec, pd.DataFrame(columns=["snap_date", "code", "market"]),
                       pd.DataFrame({"code": ["000004"] * 2, "date": months}))
        # 000003 은 1개월차까지만 패널에 있고(수익률 결측) 2개월차에 사라진다 = 거래 중단.
        # 000004 는 계속 살아 있어 '패널 자체의 공백'과 구분된다(그 경우엔 0% 가 맞다).
        P = pd.DataFrame({
            "code": ["000003", "000004", "000004"],
            "month": [months[0], months[0], months[1]],
            "Signal": [1.0, 0.9, 0.9], "fwd_ret": [np.nan, 0.0, 0.0],
            "adv20": [1e9] * 3, "VETO": [1.0] * 3, "FW": [1] * 3,
            "close": [1000.0] * 3, "d1_trailing": [-0.5] * 3})
        bt = run_backtest_micro(P, pd.DatetimeIndex(months), uni, "D",
                                COST_BASE_SCENARIO, label="DNOMAP", quiet=True)
        H = bt["holdings"]
        if H is None or len(H) == 0:
            return False, "백테스트가 보유내역을 만들지 않았습니다."
        h0 = H[(H["month"] == months[0]) & (H["code"] == "000003")]
        r = float(h0["fwd_ret"].iloc[0]) if len(h0) else 0.0
        if r > -0.999:
            return False, (f"폐지목록에 없는 종목이 거래를 멈췄는데 종목수익률이 {r:.3f} 입니다. "
                           f"0% 로 계상하면 폐지목록 커버리지가 나쁠수록 성과가 좋아집니다.")
        return True, "폐지일 미상 + 다음 달 패널 이탈 → 종목수익률 -100% 확정"

    _c("DLGAP", "정지→지연 상장폐지 -100%", delist_gap)
    _c("DLNOM", "폐지일 미상 종목의 거래중단 -100%", delist_nomap)
    _c("VALUE", "적자 다수 셀의 밸류 랭크 생존", valuecell)
    _c("VSEP", "R2-M 구성 분리 (B ≠ C)", variantsep)

    LOG.table([[r["id"], r["name"], "✔ 통과" if r["ok"] else "✘ 실패", _trunc(r["detail"], 66)]
               for r in CONTRACTS], ["ID", "계약", "판정", "상세"], ["c", "l", "c", "l"], maxw=70,
              title="계약 자동검정 — 협상 불가 규칙이 코드에 실제로 있는가")
    bad = [r["id"] for r in CONTRACTS if not r["ok"]]
    if bad:
        LOG.error(f"계약 위반 {len(bad)}건: {bad}")
        if STOP_ON_KILL_CRITERIA:
            raise KillCriteria(f"계약 위반으로 중단합니다: {bad}. 위반을 우회하지 말고 원인을 고치십시오.")
        return False
    LOG.ok(f"계약 {len(CONTRACTS)}건 전부 통과.")
    return True


# ── 합성 데이터 ─────────────────────────────────────────────────────────────────────────────
def synth_context(months: pd.DatetimeIndex, n_codes: int = 140) -> dict:
    """네트워크 없이 전체 계산 경로를 도는 합성 데이터셋.

    실데이터와 '같은 스키마'를 만든다. 스키마가 다르면 스모크는 통과하고 실행은 죽는다.
    """
    rng = np.random.default_rng(SEED)
    codes = [f"{i+1:06d}" for i in range(n_codes)]
    inds = ["전자부품 제조업", "의료기기 제조업", "소프트웨어 개발", "화학물질 제조",
            "기계장비 제조", "식료품 제조"]
    start = pd.Timestamp(months[0]) - pd.DateOffset(months=18)
    end = pd.Timestamp(months[-1]) + pd.offsets.MonthEnd(1)

    # 종목 마스터 — 10% 는 기간 중 상장폐지, 10% 는 기간 중 신규 상장
    ld = [start - pd.Timedelta(days=int(rng.integers(400, 4000))) for _ in codes]
    dd: List[Any] = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        dd[i] = pd.Timestamp(months[int(rng.integers(12, len(months) - 1))])
    for i in rng.choice(n_codes, size=max(1, n_codes // 10), replace=False):
        ld[i] = pd.Timestamp(months[int(rng.integers(2, max(3, len(months) // 2)))])
    sec = pd.DataFrame({
        "code": codes, "name": [f"합성{i+1:03d}" for i in range(n_codes)],
        "market": ["KOSDAQ"] * n_codes, "listing_date": ld, "delisting_date": dd,
        "industry": [inds[i % len(inds)] for i in range(n_codes)],
        "corp_code": [f"{i+1:08d}" for i in range(n_codes)], "src": ["synth"] * n_codes})

    # 일봉 — 소형주 성격(고변동), 일부 종목에 지속적 드리프트를 심어 신호가 잡히게 한다
    bdays = pd.bdate_range(start, end)
    good = set(rng.choice(codes, size=n_codes // 5, replace=False))
    px_rows = []
    for c, l, d in zip(codes, ld, dd):
        mask = (bdays >= pd.Timestamp(l)) & (bdays <= (pd.Timestamp(d) if pd.notna(d) else end))
        dts = bdays[mask]
        if len(dts) < 60:
            continue
        drift = 0.0009 if c in good else 0.0
        r = rng.normal(drift, 0.030, len(dts))
        close = 3000 * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.0, 0.7, len(dts))
        px_rows.append(pd.DataFrame({
            "code": c, "date": dts, "open": close * (1 + rng.normal(0, 0.004, len(dts))),
            "high": close * 1.02, "low": close * 0.98, "close": close,
            "volume": vol, "amount": vol * close, "src": "synth"}))
    px = pd.concat(px_rows, ignore_index=True) if px_rows else pd.DataFrame(columns=PRICE_COLS)

    # 시총 스냅샷 (분기)
    snaps = []
    for d in _snapshot_grid(months):
        for c in codes:
            snaps.append({"snap_date": d.strftime("%Y-%m-%d"), "code": c,
                          "shares": float(rng.integers(3_000_000, 40_000_000)),
                          "mcap": np.nan, "src": "synth"})
    snap = pd.DataFrame(snaps)

    # DART 원시 계정 (tidy_financials 를 실제로 통과시킨다 — 스키마 검증 목적)
    accs = [("revenue", "IS", "ifrs-full_Revenue", "매출액"),
            ("cogs", "IS", "ifrs-full_CostOfSales", "매출원가"),
            ("op_income", "IS", "dart_OperatingIncomeLoss", "영업이익"),
            ("net_income", "IS", "ifrs-full_ProfitLoss", "당기순이익"),
            ("interest_expense", "IS", "ifrs-full_FinanceCosts", "금융원가"),
            ("tax_expense", "IS", "ifrs-full_IncomeTaxExpense", "법인세비용"),
            ("inventory", "BS", "ifrs-full_Inventories", "재고자산"),
            ("receivable", "BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권"),
            ("assets", "BS", "ifrs-full_Assets", "자산총계"),
            ("current_assets", "BS", "ifrs-full_CurrentAssets", "유동자산"),
            ("current_liab", "BS", "ifrs-full_CurrentLiabilities", "유동부채"),
            ("equity", "BS", "ifrs-full_Equity", "자본총계"),
            ("capital_stock", "BS", "ifrs-full_IssuedCapital", "자본금"),
            ("cfo", "CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름")]
    _FLOW_SJ = {"IS", "CIS", "CF"}
    rc_codes = list(REPRT_CODES.values())
    _FY = REPRT_CODES["FY"]
    fs_rows = []
    y0, y1 = int(months[0].year) - 1, int(months[-1].year)

    def _vals_at(base_rev, grow, c, y, qi):
        """qi=1..4 시점의 (누적 손익, 기말 잔액). qi=4 는 연간."""
        rev_y = base_rev * ((1 + grow) ** (y - y0))
        cum = rev_y * qi / 4.0
        return rev_y, {
            "revenue": cum, "cogs": cum * (0.72 - (0.03 if c in good else 0.0)),
            "op_income": cum * 0.08, "net_income": cum * 0.055,
            "interest_expense": cum * 0.010, "tax_expense": cum * 0.012,
            "inventory": rev_y * (0.14 - (0.02 if c in good else 0.0)),
            "receivable": rev_y * (0.17 - (0.02 if c in good else 0.0)),
            "assets": rev_y * 1.4, "current_assets": rev_y * (0.62 - (0.05 if c in good else 0)),
            "current_liab": rev_y * 0.41, "equity": rev_y * 0.65,
            "capital_stock": rev_y * 0.12,
            "cfo": cum * (0.070 if c in good else 0.035)}

    def _fmt(x) -> str:
        return f"{x:,.0f}"

    for i, c in enumerate(codes):
        base_rev = float(rng.integers(20_000, 300_000)) * 1e6
        grow = 0.05 + (0.14 if c in good else 0.0) + rng.normal(0, 0.03)
        # ★ 5곳 중 1곳은 '연 1회만 공시'하는 기업으로 만든다. U-MICRO 에 흔한 형태이고,
        #   lag4 달력 게이트(shift(4)가 4년 전을 집는 사고)를 스모크가 실제로 밟게 하려면
        #   합성 데이터에도 반드시 존재해야 한다. 전 기업이 4분기를 다 내면 그 버그는
        #   합성에서 영원히 드러나지 않는다 — 실데이터에서만 조용히 터진다.
        annual_only = (i % 5 == 0)
        my_rcs = [_FY] if annual_only else rc_codes
        for y in range(y0, y1 + 1):
            for qi, rc in enumerate(rc_codes, start=1):
                if rc not in my_rcs:
                    continue
                _, cur = _vals_at(base_rev, grow, c, y, qi)
                _, cur_prev_q = _vals_at(base_rev, grow, c, y, qi - 1) if qi > 1 else (0, None)
                _, pv_same = _vals_at(base_rev, grow, c, y - 1, qi)
                _, pv_yend = _vals_at(base_rev, grow, c, y - 1, 4)
                mm, dd_ = REPRT_PERIOD_END[rc]
                rcpt = (pd.Timestamp(year=y, month=mm, day=dd_)
                        + pd.Timedelta(days=REPRT_DEADLINE_DAYS[rc])).strftime("%Y%m%d")
                for key, sj, aid, anm in accs:
                    flow = sj in _FLOW_SJ
                    if not flow:
                        # 재무상태표: 당기말 잔액 / 전기말 잔액 (★전년 동분기말이 아니다)
                        th, th_add = cur[key], ""
                        fr, fr_add = pv_yend[key], ""
                    elif rc == _FY:
                        # 사업보고서: 당기금액 = 연간. 누적 컬럼이 없다(실제 DART 와 동일).
                        th, th_add = cur[key], ""
                        fr, fr_add = pv_yend[key], ""
                    else:
                        # 분기·반기: 당기금액 = 3개월 단독, 당기누적금액 = YTD (실제 DART 와 동일)
                        th = cur[key] - (cur_prev_q[key] if cur_prev_q else 0.0)
                        th_add = cur[key]
                        fr = pv_same[key] - (_vals_at(base_rev, grow, c, y - 1, qi - 1)[1][key]
                                             if qi > 1 else 0.0)
                        fr_add = pv_same[key]
                    fs_rows.append({"corp_code": f"{i+1:08d}", "bsns_year": str(y),
                                    "reprt_code": rc, "rcept_no": rcpt + "000001",
                                    "fs_div": "CFS", "sj_div": sj, "account_id": aid,
                                    "account_nm": anm,
                                    "thstrm_amount": _fmt(th),
                                    "thstrm_add_amount": _fmt(th_add) if th_add != "" else "",
                                    "frmtrm_amount": _fmt(fr),
                                    "frmtrm_q_amount": "",
                                    "frmtrm_add_amount": _fmt(fr_add) if fr_add != "" else "",
                                    "bfefrmtrm_amount": ""})
    fs = pd.DataFrame(fs_rows)

    # 시장조치 · 공시 · 리포트
    act_rows, dis_rows = [], []
    for i in rng.choice(n_codes, size=max(2, n_codes // 12), replace=False):
        t = pd.Timestamp(months[int(rng.integers(6, len(months) - 6))])
        act_rows.append({"corp_code": f"{i+1:08d}", "rcept_dt": t,
                         "report_nm": "관리종목 지정", "action": "watch_on"})
        act_rows.append({"corp_code": f"{i+1:08d}", "rcept_dt": t + pd.DateOffset(months=8),
                         "report_nm": "관리종목 지정 해제", "action": "watch_off"})
    for i in rng.choice(n_codes, size=max(2, n_codes // 10), replace=False):
        t = pd.Timestamp(months[int(rng.integers(3, len(months) - 3))])
        dis_rows.append({"corp_code": f"{i+1:08d}", "rcept_no": f"S{i:09d}", "rcept_dt": t,
                         "report_nm": "유상증자결정", "event": "rights_issue",
                         "event_date": t, "knowledge_date": t})
    actions = pd.DataFrame(act_rows) if act_rows else pd.DataFrame(
        columns=["corp_code", "rcept_dt", "report_nm", "action"])
    dis = pd.DataFrame(dis_rows) if dis_rows else pd.DataFrame(
        columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "event",
                 "event_date", "knowledge_date"])

    rep_rows = []
    for i in rng.choice(n_codes, size=max(4, n_codes // 4), replace=False):
        for _ in range(int(rng.integers(1, 5))):
            t = pd.Timestamp(months[int(rng.integers(0, len(months)))])
            _br = ["미래에셋증권", "NH투자증권", "한국투자증권", "키움증권",
                   "합성증권"][int(rng.integers(0, 5))]
            rep_rows.append({
                "source": ["hankyung", "naver"][int(rng.integers(0, 2))],
                "src_report_id": f"S{i:05d}{int(rng.integers(0, 9999)):04d}",
                "pub_date": t, "category": "company",
                "title": f"합성{i+1:03d}({codes[i]}) 실적 리뷰",
                "stock_code": codes[i], "stock_name": f"합성{i+1:03d}",
                "broker_raw": _br, "analyst_raw": f"애널{int(rng.integers(1, 30)):02d}",
                "target_price": float(rng.integers(3000, 20000)), "opinion": "매수",
                "pdf_url": "", "detail_url": "", "views": 0,
                "event_date": t, "knowledge_date": t})
    # ★ 실데이터와 같은 정제·엔티티 경로를 통과시킨다. 그래야 '리포트↔애널리스트↔종목'
    #   원장 무결성 감사표가 스모크에서도 실제로 렌더링되어 형식을 확인할 수 있다.
    rep = pd.DataFrame(rep_rows)

    return {"sec": sec, "px": px, "snap": snap, "fs": fs, "actions": actions,
            "dis": dis, "rep": rep, "analysts": pd.DataFrame(), "links": pd.DataFrame(),
            "synthetic": True}



# ╔═════════════════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN — 실행 흐름                                                                         ║
# ║                                                                                          ║
# ║  [0] 환경·캐시 → 계약검정 → 합성 스모크   (실데이터 이전에 계산경로를 먼저 증명)           ║
# ║  [1] CANARY K1~K6                          (소표본 실측. FAIL 은 조치와 함께 표로)         ║
# ║  [2] 수집   (드라이브 캐시 우선 → 부족분만 신규 → 드라이브 재적재)                          ║
# ║  [3] 패널   (PIT 유니버스 → 시총 → 재무/센서 → 셀 → 방화벽 입력)                            ║
# ║  [4] 스코어·백테스트 A/B/C/D → 성과검증                                                    ║
# ║  [5] 강건성 R0 · R2-M · R3 · R5-M · R9                                                     ║
# ║  [6] 해석표 · 진단카드 · 원장감사 · 런타임 감사 · 산출물                                    ║
# ║                                                                                          ║
# ║  모든 연산은 PIPE.stage 안에서만 돈다 → 실패하면 '어디서·무엇이·왜' 가 자동 출력된다.       ║
# ╚═════════════════════════════════════════════════════════════════════════════════════════╝

OUT_DIR = "tcd_v3_micro_fw_out"


def offer_download(paths: Sequence[str]):
    ok = [p for p in paths if p and os.path.exists(p)]
    if not ok:
        return
    LOG.banner("산출물", "아래 경로에 저장되었습니다")
    LOG.table([[os.path.basename(p), f"{os.path.getsize(p)/1024:,.1f} KB", p] for p in ok],
              ["파일", "크기", "경로"], ["l", "r", "l"], maxw=64)
    if ENV.get("colab"):
        try:
            from google.colab import files as _f                       # type: ignore
            for p in ok:
                try:
                    _f.download(p)
                except Exception:
                    pass
        except Exception:
            LOG.info("Colab 다운로드 위젯을 쓸 수 없습니다 — 위 경로에서 직접 받으세요.")


@contextmanager
def l1_stage(sid: str, name: str, critical: bool = True):
    """L1 단계 = 예산 게이트 + 스테이지 + 실측 기록.

    ★ 세 가지를 한 곳에 묶는 이유: 예산을 '재기만' 하고 강제하지 않으면 아무 의미가 없다.
      진입 시 배정을 소진했는지 보고(강등), 나갈 때 실측을 적어 감사표가 단계별로
      배정 대비 실측을 그대로 보여주게 한다.
    """
    l1_guard(sid)
    _t0 = time.time()
    try:
        with PIPE.stage(sid, name, "L1",
                        budget_s=int(float(STAGE_BUDGET_MIN.get(sid, 5)) * 60),
                        critical=critical):
            yield
    finally:
        if L1BUDGET is not None:
            L1BUDGET.record(sid, time.time() - _t0)


def _umicro_candidate_codes(ctx: dict) -> set:
    """U-MICRO 에 들어올 법한 종목코드 — 리포트 상세조회 우선순위에 쓴다.

    이 시점엔 아직 시총 패널이 없다. 거래대금 중앙값이 유동성 하한을 넘되 상위권이
    아닌 구간을 대리로 쓴다(정확할 필요는 없다 — '무엇을 먼저 받을지'의 순서일 뿐이다).
    """
    px = ctx.get("px_daily")
    if px is None or not len(px) or "amount" not in px.columns:
        return set()
    try:
        amt = px.groupby("code", observed=True)["amount"].median()
        liq = amt[amt >= UMICRO_MIN_ADV_KRW]
        if len(liq) < 200:
            liq = amt
        return set(liq.sort_values(ascending=True).index.astype(str))
    except Exception:
        return set()


def collect_all(months: pd.DatetimeIndex, caps: Dict[str, bool]) -> dict:
    """수집. 캐시 우선 · 부족분만 신규 · 공용 인덱스에 재적재."""
    ctx: Dict[str, Any] = {}

    with l1_stage("L1.SEC", "종목 마스터 (상장·폐지·업종)"):
        snaps = fetch_pykrx_snapshots(months)
        ctx["snapshots"] = snaps
        sec = build_security_master(snaps)
        cc = fetch_dart_corpcode()
        if len(cc):
            m = cc.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["corp_code"]
            sec["corp_code"] = sec["corp_code"].where(sec["corp_code"].notna(),
                                                      sec["code"].map(m))
        ctx["sec"] = sec
        VAULT.put_table("security_master", sec, scope="shared", domain="universe",
                        source="fdr+kind+dart")
        VAULT.flush()

    with l1_stage("L1.PX", "가격·거래대금 (다중소스 폴백)"):
        codes = ctx["sec"]["code"].dropna().astype(str).tolist()
        px = fetch_prices(codes, BACKTEST_START, BACKTEST_END)
        ctx["px_daily"] = px
        ctx["panel"] = build_price_panel(px, months)
        VAULT.flush()


    with l1_stage("L1.DART", "DART 재무 → 분기 센서", critical=False):
        # ★ 전 종목×전 연도를 단건 API 로 도는 것은 §5('종목별 루프 금지')와 §10(4시간)을
        #   동시에 어긴다. 예산 견적 → 싼 경로부터 → 남은 예산 안에서만 단건.
        fs = collect_dart_financials_budgeted(ctx["sec"], months, ctx.get("px_daily"),
                                              budget_min=DART_BUDGET_MIN)
        W = tidy_financials(fs) if len(fs) else pd.DataFrame()
        Q = add_micro_sensors_quarterly(W) if len(W) else pd.DataFrame()
        ctx["fin_q"] = Q
        if len(Q):
            PIT.register("dart_micro", Q, key_cols=["corp_code"])
            VAULT.put_table(f"micro_sensors_q_{STRATEGY_ID}", Q, scope="private",
                            domain="feature", source="dart tidy + micro sensors")
        VAULT.flush()

    # ★ 시총은 DART 재무 '뒤'에 둔다.
    #   주식총수 보강이 DART 호출을 먼저 태우면, 정작 이 전략의 본체인 재무를 받을
    #   한도가 사라진다. 실제로 그 순서 때문에 재무 시작 시점에 한도가 1,000건 깎여 있었다.
    with l1_stage("L1.MCAP", "시가총액·상장주식수"):
        snap_m = fetch_mcap_snapshots(months, ctx["sec"])
        ctx["mcap_snap"] = snap_m
        ctx["mcap"] = build_mcap_panel(ctx["panel"]["monthly"], snap_m, ctx["sec"], months)
        VAULT.flush()

    with l1_stage("L1.ACT", "관리종목·감사의견·거래정지", critical=False):
        ctx["actions"] = fetch_market_actions(BACKTEST_START, BACKTEST_END)
        VAULT.flush()

    with l1_stage("L1.DIS", "공시목록 (희석성 조달 V3)", critical=False):
        ctx["dis"] = fetch_dart_disclosures(BACKTEST_START, BACKTEST_END)
        VAULT.flush()

    # ★ PIPE.stage(skip_if=...) 는 '표시'만 건너뛸 뿐 with 블록의 본문은 그대로 실행된다
    #   (@contextmanager 는 본문을 건너뛸 수 없다). 부작용이 있는 단계는 반드시 밖에서
    #   진짜 if 로 막아야 한다 — 안 그러면 RESEARCH_USE=False 인데도 수집이 돌아간다.
    ctx["reports"] = ctx["analysts"] = ctx["links"] = pd.DataFrame()
    if RESEARCH_USE:
        _collect_research(ctx)
    else:
        LOG.info("RESEARCH_USE=False — 애널리스트 리포트 수집·사용을 전면 건너뜁니다.")
    return ctx


def _collect_research(ctx: dict):
    """애널리스트 리포트 원장. 드라이브 캐시를 최우선으로 재사용한다.

    ★ 별도 함수로 뺀 이유: PIPE.stage(skip_if=...) 는 '표시'만 건너뛸 뿐 with 블록의
      본문은 그대로 실행된다(@contextmanager 는 본문을 건너뛸 수 없다). 부작용이 있는
      단계는 반드시 호출 자체를 if 로 막아야 한다.
    """
    with l1_stage("L1.RSRCH", "애널리스트 리포트 (한경·네이버 + 드라이브 캐시)", critical=False):
        frames = []
        cached = VAULT.get_table("research_report_master", scope="shared")
        if cached is not None and len(cached):
            LOG.ok(f"드라이브 공용 인덱스에서 리포트 원장 {len(cached):,}건 재사용 "
                   f"(이미 모아두신 캐시를 최우선으로 씁니다)")
            frames.append(cached)
        _t_rs = time.time()
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT:
            # ★ 한경을 먼저 받는다. 목록 표에 작성자(애널리스트)와 적정가격이 그대로 있어
            #   상세 조회가 필요 없다 — 원장 연결(리포트↔애널리스트↔종목)의 본체다.
            if "hankyung" in RESEARCH_SOURCES:
                frames.append(hankyung_collect(BACKTEST_START, BACKTEST_END))
            if "naver" in RESEARCH_SOURCES:
                frames.append(naver_collect(BACKTEST_START, BACKTEST_END))
        # ★ 순서가 성능을 결정한다: 병합을 '먼저' 해야 한경이 이미 채워 준 목표주가를
        #   가진 건이 네이버 상세 조회 대상에서 빠진다. 예전 순서(네이버 보강 → 병합)는
        #   같은 정보를 한 건당 1회 요청으로 다시 사 오느라 126분을 썼다.
        rep = build_report_master(frames, ctx["sec"])
        if RUN_MODE != "CACHED" and RESEARCH_COLLECT and "naver" in RESEARCH_SOURCES:
            _left = max(0.0, RESEARCH_BUDGET_MIN * 60.0 - (time.time() - _t_rs))
            if DEADLINE is not None:
                _left = min(_left, DEADLINE.remain_s())
            rep = naver_enrich_detail(rep, budget_s=_left,
                                      prio_codes=_umicro_candidate_codes(ctx))
        if len(rep) and RESEARCH_DOWNLOAD_PDF:
            rep = download_pdfs(rep, cap_per_month=RESEARCH_PDF_MAX_PER_MONTH)
            if "pdf_target" in rep.columns:
                fill = rep["target_price"].isna() & rep["pdf_target"].notna()
                if fill.any():
                    rep.loc[fill, "target_price"] = rep.loc[fill, "pdf_target"]
        A, L = build_analyst_ledger(rep) if len(rep) else (pd.DataFrame(), pd.DataFrame())
        if len(rep):
            VAULT.put_table("research_report_master", rep, scope="shared",
                            domain="research", source="hankyung+naver")
        if len(A):
            VAULT.put_table("analyst_master", A, scope="shared", domain="research",
                            source="entity_resolution")
            VAULT.put_table("report_analyst_link", L, scope="shared", domain="research",
                            source="entity_resolution")
        ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, L
        VAULT.flush()


def build_panel(ctx: dict, months: pd.DatetimeIndex) -> Tuple[pd.DataFrame, "Universe", dict]:
    tables: Dict[str, Any] = {}
    with PIPE.stage("L1.PANEL", "패널 조립 (유니버스 → 시총 → 재무 → 셀)", "L1", budget_s=1200):
        # 상장일 결측 보강이 Universe 생성보다 반드시 먼저다 — 유니버스 멤버십의 입력이다.
        ctx["sec"] = infer_listing_dates(ctx["sec"], ctx.get("px_daily"))
        uni = Universe(ctx["sec"],
                       ctx.get("snapshots", pd.DataFrame(columns=["snap_date", "code", "market"])),
                       ctx["panel"]["daily"])
        P = build_base_panel_micro(uni, months, ctx["panel"]["monthly"])
        P = P.merge(ctx["mcap"], on=["code", "month"], how="left")
        P = attach_fundamentals_micro(P, ctx["sec"])
        P = attach_valuation(P)
        P = attach_reflection(P)
        P, attrition = apply_umicro_gates(P, uni)
        tables["attrition"] = attrition
        P = build_cells_micro(P, ctx["sec"], min_n=MICRO_MIN_CELL_N)

    with PIPE.stage("L1.FLAGS", "방화벽 입력 (관리종목·감사의견·거래정지)", "L1",
                    budget_s=600, critical=False):
        P, active = build_watchlist_panel(P, ctx.get("actions"), ctx["sec"])
        P = derive_halt_from_price(ctx.get("px_daily"), P)
        tables["fw_active"] = active

    # (skip_if 은 본문을 건너뛰지 못하므로 진짜 if 로 막는다 — 위 _collect_research 주석 참조)
    if RESEARCH_USE and len(ctx.get("links", [])):
        with PIPE.stage("L1.REV", "애널리스트 목표주가 리비전 (U층 보조)", "L1",
                        budget_s=300, critical=False):
            C = build_consensus_panel(ctx["links"], months)
            if len(C):
                P = P.merge(C[["code", "month", "d2_raw"]].rename(columns={"d2_raw": "u_revision"}),
                            on=["code", "month"], how="left")
                P["u_revision_rank"] = cell_rank_micro(P, "u_revision")
                LOG.ok(f"목표주가 리비전 결합 {int(P['u_revision'].notna().sum()):,}행")
    else:
        LOG.info("애널리스트 연결이 없어 U층 보조신호(목표주가 리비전)를 사용하지 않습니다. "
                 "E층은 리포트에 의존하지 않으므로 백테스트는 정상 진행됩니다.")

    # ★ V3(희석성 조달)의 주식수 12개월 증가율은 U-MICRO 부분집합이 아니라 '전체 패널'에서
    #   계산해야 한다. 12개월 전에 유니버스 밖이었던 종목은 부분집합에서 전 값을 못 찾아
    #   증가율이 통째로 결측이 되고, 백스톱이 무력화된다.
    tables["dis"] = ctx.get("dis")
    if "shares" in P.columns:
        _S = P[["code", "month", "shares"]].copy()
        _S["month"] = (as_ts_series(_S["month"]) + pd.DateOffset(months=12)) + pd.offsets.MonthEnd(0)
        _S = _S.rename(columns={"shares": "shares_p12"})
        P = P.merge(_S, on=["code", "month"], how="left")

    P["FW"] = 0
    P["VETO"] = 0.0
    return P, uni, tables


def score_and_backtest(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "Universe",
                       tables: dict) -> Tuple[pd.DataFrame, Dict[str, dict], dict, dict]:
    with PIPE.stage("L2.SCORE", "센서 가용성 → TP → 방화벽 → 거부권", "L2", budget_s=600):
        M = P[P["u_micro"].astype(bool)].copy() if "u_micro" in P.columns else P.copy()
        if len(M) < 150:
            _msg = (f"U-MICRO 유효 종목월이 {len(M):,}건뿐입니다(§12-6: 유효종목 150 미만). "
                    f"통계 검정이 불가능하므로 중단합니다. 위 감쇠 감사표에서 어느 게이트가 "
                    f"표본을 깎았는지 먼저 확인하세요.")
            if STOP_ON_KILL_CRITERIA and _KILL_ARMED:
                raise KillCriteria(_msg)
            LOG.warn("[킬 비무장] " + _msg)
        active_tp, avail = sensor_availability(M)
        tables["availability"] = avail
        M = build_evidence(M, active_tp)
        fw, fwt = s1_firewall(M, tables.get("fw_active", {}))
        M["FW"] = fw
        tables["firewall"] = fwt
        M = apply_vetoes_micro(M, tables.get("dis"))
        PIPE.io("OUT", "MEM", "scored_panel", M)

    with PIPE.stage("L3.BT", "백테스트 A/B/C/D + 벤치마크", "L3", budget_s=900):
        bts: Dict[str, dict] = {}
        for v in ("A", "B", "C", "D"):
            S = assemble_signal(M, v)
            bts[v] = run_backtest_micro(S, months, uni, v, COST_BASE_SCENARIO, label=v)
            if v == "D":
                M = S          # 최종안(D)의 신호를 패널에 남긴다 — 해석표·진단카드가 이걸 읽는다
        bench_ew = benchmark_universe_ew(M, months, COST_BASE_SCENARIO, uni=uni)
        bench_idx = benchmark_index(months)
        LOG.ok(f"유니버스 동일가중 기준선 — {_fmt(bench_ew)}")
    return M, bts, bench_ew, bench_idx


def main() -> dict:
    """어떤 종료 경로(킬 기준·스테이지 실패·Ctrl-C)에서도 인덱스 저널은 남긴다."""
    try:
        return _main_inner()
    finally:
        # ★ _register() 는 메모리(_pending)에만 쌓이고 flush() 에서만 저널에 기록된다.
        #   실행 끝(L6.OUT)에만 flush 하면, 킬 기준처럼 '예상된 중단'에서 그 실행이
        #   수집한 모든 등록이 통째로 버려진다 — 파일은 드라이브에 남았는데 인덱스에는
        #   없는 상태가 되어 다음 실행이 같은 것을 다시 받는다.
        try:
            if VAULT is not None:
                VAULT.flush()
        except Exception:
            pass


def _main_inner() -> dict:
    t_start = time.time()
    LOG.banner(f"TCD v3 · {STRATEGY_NAME}",
               f"{BACKTEST_START} ~ {BACKTEST_END} · 빌드 {BUILD_VERSION} · 모드 {RUN_MODE}")
    months = month_range(BACKTEST_START, BACKTEST_END)
    global DEADLINE, L1BUDGET
    DEADLINE = Deadline(MAX_WALLCLOCK_MIN)
    L1BUDGET = LayerBudget(COLLECT_BUDGET_MIN, STAGE_BUDGET_MIN)
    outputs: List[str] = []
    os.makedirs(OUT_DIR, exist_ok=True)

    # ── [0] 환경 · 캐시 ──────────────────────────────────────────────────────────────
    global VAULT
    with PIPE.stage("L0.VAULT", "구글드라이브 캐시 연결", "L0", budget_s=300):
        root, mode = _mount_drive()
        VAULT = Vault(root, mode)
        LOG.ok(f"캐시 루트: {root}  (모드 {mode})")
        krx_block_load()      # 이전 실행에서 KRX 차단을 만났다면 해제 시각까지 건드리지 않는다
        LOG.info(f"공용 인덱스 = {GDRIVE_SHARED_NS} (전 전략 공유) · "
                 f"전용 인덱스 = {GDRIVE_PRIVATE_NS} (이 전략)")
        try:
            VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        except Exception as e:                                         # noqa
            LOG.warn(f"기존 캐시 스캔 실패({type(e).__name__}) — 기존 파일은 그대로 있습니다.")
        VAULT.report()

    with PIPE.stage("L0.CONTRACT", "계약 자동검정", "L0", budget_s=180):
        run_contracts()

    # ── [1] 합성 스모크 — 출력물 전체를 예행연습한다 ────────────────────────────────
    global _KILL_ARMED
    with PIPE.stage("L0.SMOKE", "합성데이터 엔드투엔드 스모크", "L0", budget_s=900):
        sctx = synth_context(months)
        # ★ 킬 해제를 파이프라인 '앞'에 둔다. score_and_backtest 안의 두 지점
        #   (유효 종목월 150 미만 · C14-d 활성 TP 부족)이 KillCriteria 를 던지는데,
        #   해제를 파이프라인 뒤에 두면 그 둘은 합성 데이터에서도 실행을 죽인다.
        #   "합성 판정으로는 죽이지 않는다"는 약속이 정작 가장 흔한 두 실패 양식에서
        #   지켜지지 않는다.
        _KILL_ARMED = False
        try:
            sm = _run_pipeline_from_ctx(sctx, months, smoke=True)
            LOG.ok(f"계산 경로 통과 — 합성 CAGR {100*sm['bts']['D']['stats']['cagr']:.2f}% "
                   f"(값 자체는 의미 없습니다. 경로가 끝까지 돈다는 증명입니다)")
            _report_everything(sm, sctx, months, smoke=True)
        finally:
            _KILL_ARMED = True
        LOG.ok("스모크 통과 — 성과·강건성·해석표까지 전 출력물이 정상 생성됩니다.")

    # ★ 합성 데이터가 실행 후반으로 새지 않게 격리한다.
    #   PIT 저장소는 전역이라, 실데이터 수집이 부분 실패하면 스모크가 등록한 합성 재무가
    #   그대로 남아 '실데이터 백테스트'에 섞인다. 에러 없이 결과만 틀리는 최악의 사고다.
    _reset_state()

    if RUN_MODE == "SMOKE":
        PIPE.report_stages()
        PIPE.report_flow()
        PIPE.report_runtime()
        LOG.ok("SMOKE 모드 완료. RUN_MODE='FULL' 로 바꾸면 실데이터로 실행합니다.")
        return {"mode": "SMOKE"}

    # ── [2] CANARY ──────────────────────────────────────────────────────────────────
    with PIPE.stage("L0.CANARY", "CANARY K1~K6", "L0", budget_s=900):
        with PIPE.stage("L0.CANARY.SEC", "종목 마스터 선취득", "L0", budget_s=600):
            snaps0 = fetch_pykrx_snapshots(months)
            sec0 = build_security_master(snaps0)
            cc0 = fetch_dart_corpcode()
            if len(cc0):
                m0 = cc0.dropna(subset=["code"]).drop_duplicates("code").set_index("code")["corp_code"]
                sec0["corp_code"] = sec0["corp_code"].where(sec0["corp_code"].notna(),
                                                            sec0["code"].map(m0))
        caps = run_canary(sec0, months)
        p = write_canary_report(os.path.join(OUT_DIR, "canary_report.md"))
        if p:
            outputs.append(p)

    # ── [3~6] 실데이터 ──────────────────────────────────────────────────────────────
    ctx = collect_all(months, caps)
    res = _run_pipeline_from_ctx(ctx, months, smoke=False)
    P, bts, bench_ew = res["P"], res["bts"], res["bench_ew"]
    tables = res["tables"]
    abl, r9, verdict = _report_everything(res, ctx, months, smoke=False)

    # ── 산출물 ──────────────────────────────────────────────────────────────────────
    with PIPE.stage("L6.OUT", "산출물 저장 (전용 인덱스 + 로컬)", "L6", budget_s=300,
                    critical=False):
        outputs += _write_outputs(P, bts, bench_ew, tables, abl, r9, verdict)
        VAULT.put_table(f"panel_micro_{STRATEGY_ID}", downcast(P), scope="private",
                        domain="feature", source="micro-fw panel")
        for k, bt in bts.items():
            if len(bt.get("returns", [])):
                VAULT.put_table(f"backtest_{k}_{STRATEGY_ID}", bt["returns"], scope="private",
                                domain="backtest", source=f"variant {k}")
        VAULT.flush()
        VAULT.compact("shared")
        VAULT.compact("private")
        VAULT.report()

    PIPE.report_stages()
    PIPE.report_flow(limit=120)
    PIPE.report_runtime()
    if L1BUDGET is not None:
        _lb = L1BUDGET.report()
        LOG.table(_lb.values.tolist(), list(_lb.columns), ["l", "r", "r", "l"],
                  title=f"수집 예산 감사 (§5) — 단계별 배정 대비 실측 "
                        f"(총 배정 {COLLECT_BUDGET_MIN}분)")
        if L1BUDGET.demoted:
            LOG.warn(f"예산 소진으로 캐시 전용 강등된 단계: {', '.join(L1BUDGET.demoted)}. "
                     f"이 단계들의 신규 수집분은 다음 실행이 이어받습니다.")
    report_http()
    KRXG.report()
    if DEADLINE is not None:
        DEADLINE.report()
    LOG.banner("완료", f"총 소요 {(time.time()-t_start)/60:.1f}분 "
                       f"(계약 상한 {MAX_WALLCLOCK_MIN}분)")
    offer_download(outputs)
    return {"P": P, "bts": bts, "outputs": outputs}


def _reset_state():
    """스모크(합성) → 실행(실데이터) 사이의 전역 상태 격리.

    PIT 저장소·강건성 결과·유니버스 캐시는 전역이다. 격리하지 않으면 실데이터 수집이
    부분 실패했을 때 합성 데이터가 그대로 남아 결과에 섞인다 — 에러 없이 값만 틀린다.
    """
    try:
        PIT._t.clear(); PIT._meta.clear(); PIT.access_log.clear()
    except Exception:
        pass
    ROBUST.clear()
    LOG.debug("전역 상태 초기화 완료 (PIT 저장소 · 강건성 결과) — 합성 데이터 격리")


def _report_everything(res: dict, ctx: dict, months: pd.DatetimeIndex, smoke: bool):
    """성과검증 → 강건성 → 해석표. 스모크와 실행이 '같은 출력 경로'를 탄다."""
    P, bts = res["P"], res["bts"]
    bench_ew, bench_idx, tables = res["bench_ew"], res["bench_idx"], res["tables"]
    tag = "(합성 예행연습)" if smoke else ""
    # ★ 아래 강건성 스테이지는 스모크에서 critical=False 다. 거기서 예외가 나면 스테이지가
    #   삼키고 통과하는데, 그 뒤 return 이 미할당 지역변수를 참조해 UnboundLocalError 로
    #   실행 전체를 죽인다 — 원인과 전혀 다른 곳에서 죽는 최악의 형태다. 먼저 초기화한다.
    abl, r9, verdict = None, None, ""

    with PIPE.stage(f"L6.PERF{'.S' if smoke else ''}", f"성과 검증 {tag}", "L6", budget_s=180):
        report_performance(bts, bench_ew, bench_idx)
        report_yearly(bts, bench_ew)
        report_subperiod(bts.get("D"))
        right_tail_contribution(bts.get("D"))

    with PIPE.stage(f"L5.ROBUST{'.S' if smoke else ''}",
                    f"강건성 R0·R2-M·R3·R5-M·R9 {tag}", "L5", budget_s=1800,
                    critical=not smoke):
        if smoke:
            LOG.info("합성 데이터이므로 판정은 '출력 형식 확인'용입니다 — "
                     "킬 기준을 발동시키지 않습니다(실데이터에서는 발동합니다).")
        R0_benchmark(bts, bench_ew, bench_idx)
        verdict = R2M_fourway(bts, bench_ew)
        R3_orthogonal(P, bts.get("D"), bench_ew)
        abl = R5M_ablation(P, months, res["uni"], tables.get("fw_active", {}), bts.get("D"))
        r9 = R9_cost(P, months, res["uni"])
        report_robustness()

    with PIPE.stage(f"L6.REPORT{'.S' if smoke else ''}",
                    f"해석표 · 진단카드 · 원장감사 {tag}", "L6", budget_s=300, critical=False):
        report_interpretation(P, tables.get("firewall"))
        diagnostic_card(P, bts.get("D"), ctx["sec"])
        report_ledger_integrity(ctx.get("reports"), ctx.get("analysts"), ctx.get("links"), P)
        report_dataflow_map()
    return abl, r9, verdict


def _run_pipeline_from_ctx(ctx: dict, months: pd.DatetimeIndex, smoke: bool) -> dict:
    """수집 결과(ctx)를 받아 패널→스코어→백테스트까지. 합성/실데이터가 같은 경로를 탄다."""
    if ctx.get("synthetic"):
        # 합성 ctx 는 원시 형태이므로 실데이터와 같은 정제 경로를 통과시킨다.
        # ★ 복사본을 만들면 여기서 채운 reports/analysts/links 가 호출자의 ctx 에 반영되지
        #   않아, 원장 무결성 감사표가 '리포트 없음'으로 렌더링된다. 원본을 그대로 채운다.
        ctx["px_daily"] = ctx["px"]
        ctx["panel"] = build_price_panel(ctx["px"], months)
        ctx["snapshots"] = ctx["snap"][["snap_date", "code"]].assign(market="KOSDAQ")
        ctx["snapshots"]["snap_date"] = as_ts_series(ctx["snapshots"]["snap_date"])
        ctx["mcap"] = build_mcap_panel(ctx["panel"]["monthly"], ctx["snap"], ctx["sec"], months)
        W = tidy_financials(ctx["fs"])
        Q = add_micro_sensors_quarterly(W)
        PIT.register("dart_micro", Q, key_cols=["corp_code"])
        ctx["fin_q"] = Q
        # 리포트 원장·애널리스트 원장도 실경로와 동일하게 조립한다(원장 감사표 예행연습).
        try:
            _rep = build_report_master([ctx.get("rep")], ctx["sec"])
            _A, _L = build_analyst_ledger(_rep) if len(_rep) else (pd.DataFrame(), pd.DataFrame())
            ctx["reports"], ctx["analysts"], ctx["links"] = _rep, _A, _L
        except Exception as e:                                         # noqa
            LOG.warn(f"합성 리포트 원장 조립 실패({type(e).__name__}) — 원장 감사표는 건너뜁니다.")
    P, uni, tables = build_panel(ctx, months)
    M, bts, bench_ew, bench_idx = score_and_backtest(P, months, uni, tables)
    return {"P": M, "uni": uni, "bts": bts, "bench_ew": bench_ew,
            "bench_idx": bench_idx, "tables": tables}


def _write_outputs(P, bts, bench_ew, tables, abl, r9, verdict) -> List[str]:
    made = []

    def _csv(df, name):
        if df is None or not len(df):
            return
        p = os.path.join(OUT_DIR, name)
        try:
            df.to_csv(p, index=False, encoding="utf-8-sig")
            made.append(p)
        except Exception as e:                                         # noqa
            LOG.warn(f"{name} 저장 실패({type(e).__name__})")

    _csv(tables.get("attrition"), "attrition_micro.csv")
    _csv(abl, "r5m_ablation.csv")
    _csv(r9, "r9_cost_scenarios.csv")
    _csv(tables.get("firewall"), "firewall_clauses.csv")
    _csv(tables.get("availability"), "sensor_availability.csv")

    try:
        p = os.path.join(OUT_DIR, "panel_micro.parquet")
        atomic_write_parquet(downcast(P), p)
        made.append(p)
    except Exception as e:                                             # noqa
        LOG.warn(f"패널 parquet 저장 실패({type(e).__name__})")

    try:
        js = {k: {"stats": {kk: (None if vv is None or (isinstance(vv, float) and not np.isfinite(vv))
                                 else float(vv)) for kk, vv in bt["stats"].items()},
                  "desc": VARIANTS[k]["desc"] if k in VARIANTS else bt.get("label", "")}
              for k, bt in bts.items()}
        js["BENCH_EW"] = {"stats": {kk: (None if vv is None or (isinstance(vv, float) and not np.isfinite(vv))
                                         else float(vv)) for kk, vv in bench_ew["stats"].items()},
                          "desc": "유니버스 동일가중 (자체 측정)"}
        p = os.path.join(OUT_DIR, "backtest_ABCD.json")
        atomic_write_text(p, json.dumps(js, ensure_ascii=False, indent=2))
        made.append(p)
    except Exception as e:                                             # noqa
        LOG.warn(f"backtest_ABCD.json 저장 실패({type(e).__name__})")

    try:
        p = os.path.join(OUT_DIR, "r2m_verdict.md")
        atomic_write_text(p, "# R2-M 판정 — 방화벽 알파 가설\n\n" + verdict + "\n")
        made.append(p)
    except Exception:
        pass

    try:
        rt = pd.DataFrame([{"stage": r.sid, "name": r.name, "layer": r.layer,
                            "status": r.status, "seconds": round(r.dur, 2),
                            "rows_in": r.rows_in, "rows_out": r.rows_out}
                           for r in PIPE.stages.values()])
        _csv(rt, "runtime.csv")
    except Exception:
        pass
    return made


if __name__ == "__main__":
    try:
        main()
    except KillCriteria as e:
        LOG.banner("⛔ 킬 기준으로 중단", "§12 — 파라미터를 조정해 통과시키지 마십시오")
        _safe_print(f"  {e}")
        PIPE.report_stages()
        PIPE.report_runtime()
        report_robustness()
    except StageFailure as e:
        LOG.error(str(e))
        PIPE.report_stages()
        PIPE.report_flow(limit=60)
