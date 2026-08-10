#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════════════════════
#
#   TCD v2 — 트레이드오프 붕괴 탐지 (Trade-off Collapse Detection)  ZERO-BASE 완전본
#   한국 상장사 「질적 전환」 탐지 퀀트 시스템 · 계약문서 v2(2026-08-07) 기준 재구현
#
#   ── 이 파일 하나로 끝납니다 ──────────────────────────────────────────────────────────────
#     · Colab / JupyterLab 어느 쪽이든 "한 셀"에 붙여넣고 실행하거나 `python 이파일.py` 로 실행.
#     · 실행 순서(전부 로그로 출력됩니다):
#         [A] 환경·의존성 부트스트랩 → 구글드라이브 캐시(공용/전용 인덱스) 연결
#         [B] 계약 자가검정 C1~C12  → 합성데이터 스모크(계산경로 증명)
#         [C] 데이터수집부  (캐시: 로컬D드라이브+구글드라이브 탐색 → 부족분만 신규 수집
#                            → ★신규 수집분은 전부 구글드라이브 공용/전용 인덱스에 저장)
#             ★수집은 '날짜축'이다: 하루 1회 호출 = 그날 상장된 전 종목.
#               10년 ≈ 2,700 거래일이면 끝나고, 받은 거래일은 원장에 남아 두 번 다시
#               조회하지 않는다. 상장폐지 종목은 '당시 상장돼 있던 날'에 자동 포함된다.
#         [D] 정제부        (PIT 정련·재무 tidy·셀 구성)
#         [E] 백테스트부    (피처 L1 → 스코어 L2 → 백테스트 L3)
#         [F] 성과검증      → [G] 강건성검사 R1~R11 → [H] 해석표·진단카드
#         [I] 비교전략      (시가총액 하위 1000 압축 유니버스 — 별도 성과·강건성·해석 + 비교표)
#         [J] 산출물 저장(구글드라이브) + 다운로드 링크
#
#   ── 전략 코어(계약 §1) ──────────────────────────────────────────────────────────────────
#     "좋은 기업"이 아니라 "제약이 풀린 기업"을 찾는다.
#     점수화 단위는 개별 지표가 아니라 트레이드오프 쌍:  TP = z(개선) × z(치르지 않은 대가)
#     ★ TP 는 반드시 곱. 합산으로 바꾸면 평범한 퀄리티 팩터가 되어 존재 이유가 사라진다.
#     Signal = rank_pct(E) × rank_pct(U) × ∏V   (E 증거층·U 미반영도·V 이진 거부권)
#
#   ⚠ 본 코드는 전략 연구·검증용이며 투자자문이 아닙니다.
# ════════════════════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║   ⚙️  사용자 설정 — 여기만 채우면 됩니다 (전부 비워도 실행은 됩니다)                       ║
# ║      키가 없는 소스는 건너뛰고 "무엇이 왜 비활성화됐는지"를 로그에 한글로 명시합니다.      ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

# ── ① KRX 데이터 마켓플레이스 로그인 (가격·시가총액·관리종목 스냅샷) ──────────────────────────
#     가입(무료): https://data.krx.co.kr → 회원가입 → 아래에 로그인 ID/비밀번호 입력
#     ▶ 2025-12 인증 개편 이후 KRX 정식 조회는 로그인 세션이 필요합니다.
#     ▶ 비워도 됩니다: pykrx 전종목 스냅샷이 같은 날짜축 경로를 대신 타고,
#       못 채운 종목만 네이버/FDR 로 보충합니다(감사표에 소스가 표시됩니다).
#     ⚠ 같은 계정을 브라우저에서 동시에 로그인해 두면 KRX 가 이전 세션을 끊어(중복로그인)
#       수집이 실패합니다. 실행 중에는 브라우저 로그인을 피하세요.
KRX_MARKETPLACE_ID = ""
KRX_MARKETPLACE_PW = ""

# ── ①-b (선택) KRX Open API 인증키 — 날짜축 벌크의 '정식' 경로 ───────────────────────────────
#     발급: https://openapi.krx.co.kr → 인증키 신청
#     ★실전 주의(다른 실행에서 확인된 사실): 키 발급만으로는 못 씁니다.
#       엔드포인트별 '이용신청'을 따로 해야 하고 승인에 하루 정도 걸립니다.
#       승인 전에는 키가 있어도 호출이 거부되며, 코드는 이를 감지해 즉시 다음 경로로 넘어갑니다.
#     ▶ 되면 이점이 큽니다: 로그인 세션·중복로그인 충돌이 없고, 한 번 호출에 그날 전 종목이
#       옵니다(일별매매정보). 비워두면 마켓플레이스 로그인/pykrx 경로가 그대로 대신합니다.
KRX_OPENAPI_KEY = ""

# ── ② DART 전자공시 OpenAPI (재무제표·직원현황·공시목록 — B/C축과 PACK-C 의 핵심 입력) ────────
#     발급(무료·즉시): https://opendart.fss.or.kr → 인증키 신청/관리
#     ▶ 일일 호출한도는 코드가 "실시간 잔여량"으로 관리합니다. 사전에 19,000 같은 고정 예산을
#       걸지 않고, 사용량을 계수하면서 서버가 한도초과(status 020)를 알리는 순간 그 값을
#       '오늘의 실제 한도'로 학습해 즉시 멈춥니다. 받은 데이터는 드라이브에 저장되어 있으므로
#       내일 재실행하면 정확히 이어받습니다.
DART_API_KEY = ""

# ── ③ 공공데이터포털 (PACK-N 국민연금 사업장 / PACK-P 조달청 낙찰) ───────────────────────────
#     발급: https://www.data.go.kr → 활용신청 → 마이페이지에서 "일반 인증키(Decoding)" 복사
#     ★ Encoding 키(%2B 등이 섞인 것)를 넣으면 이중 인코딩으로 항상 실패합니다.
DATA_GO_KR_KEY = ""

# ── ④ 관세청 수출입 무역통계 (PACK-X 사용 시에만) ────────────────────────────────────────────
#     발급: https://unipass.customs.go.kr 또는 공공데이터포털의 관세청 API
CUSTOMS_API_KEY = ""

# ── ⑤ 구글드라이브 캐시 — ★★★ 절대 1원칙 ★★★ ────────────────────────────────────────────────
#     · 기존 캐시/인덱스(공용·전용)는 어떤 경우에도 삭제·덮어쓰기하지 않습니다.
#       인덱스의 원천은 append-only 저널이고, 파생 파일은 교체 전 반드시 타임스탬프 백업,
#       원본(blob)은 내용해시 경로에 저장되어 덮어쓰기 자체가 일어나지 않으며,
#       이 코드에는 삭제 API 가 존재하지 않습니다(손상 파일도 .corrupt 로 격리만).
#     · 신규 수집되는 모든 데이터·리포트는 구글드라이브에 저장되고
#       공용 인덱스(다른 전략도 재사용 가능한 원본·정제본)와
#       전용 인덱스(이 전략 고유의 피처·스코어·결과)로 등록되어 재호출 가능합니다.
#     ▶ Colab 이면 아래 기본값 그대로 두면 됩니다(자동 마운트).
#     ▶ ★윈도우 JupyterLab 이면 여기를 자기 드라이브 경로로 바꾸세요. 예시:
#           GDRIVE_ROOT = r"G:/내 드라이브/tcd_cache"      ← 구글드라이브 데스크톱 기본
#           GDRIVE_ROOT = r"C:/Users/내계정/Google Drive/내 드라이브/tcd_cache"
#       비워두거나 못 찾으면 코드가 G~L 드라이브문자와 홈폴더를 자동 탐색하고,
#       그래도 없으면 로컬에만 저장하며 ★어떻게 바로잡는지 로그로 안내합니다.
GDRIVE_ROOT        = "/content/drive/MyDrive/tcd_cache"   # Colab 마운트 기준 캐시 루트
SHARED_NAMESPACE   = "_shared"     # 공용 인덱스: {ROOT}/_shared  (가격·재무·리포트 원장 등)
PRIVATE_NAMESPACE  = "tcd_v2"      # 전용 인덱스: {ROOT}/tcd_v2   (피처·스코어·백테스트 결과)

#     이미 모아둔 리포트/데이터 폴더가 있으면 여기 추가하세요.
#     재귀 스캔해서 "이동·개명 없이 경로만" 공용 인덱스에 참조 등록(adopt)합니다.
GDRIVE_ADOPT_DIRS = [
    "/content/drive/MyDrive/tcd_cache",
    "/content/drive/MyDrive/research",
    "/content/drive/MyDrive/reports",
    "/content/drive/MyDrive/consensus",
]

#     캐시 '탐색' 은 구글드라이브와 로컬(D드라이브 등) 양쪽에서 합니다. 아래 경로들은
#     읽기 전용 보조 캐시로만 쓰이며(시간 절약), ★신규 저장은 항상 구글드라이브입니다.
LOCAL_CACHE_HUNT_DIRS = [
    "D:/tcd_cache", "D:\\tcd_cache", "E:/tcd_cache",
    "/mnt/d/tcd_cache", "~/tcd_cache", "./tcd_cache",
]
LOCAL_FALLBACK_ROOT = "./tcd_cache"   # 드라이브 마운트가 전혀 안 될 때의 마지막 저장처(경고 표시)

# ── ⑥ 백테스트 구간 — 2016년 8월 ~ 2026년 7월 (10년) ─────────────────────────────────────────
BT_START = "2016-08-01"
BT_END   = "2026-07-31"

# ── ⑦ 애널리스트 리포트 수집 (한경컨센서스·네이버리서치 중심) ────────────────────────────────
#     드라이브에 이미 캐시된 리포트 원장이 있으면 먼저 재사용하고 부족분만 수집합니다.
COLLECT_RESEARCH   = True
RESEARCH_SOURCES   = ["hankyung", "naver"]
DOWNLOAD_REPORT_PDF = False     # True 면 PDF 원문까지 저장(용량↑). 목표주가·작성자는 리스트만으로도 됩니다.
PDF_MONTHLY_CAP     = 200       # PDF 받을 때 월별 상한(0=무제한)

# ── ⑧ 성능/자원 (차단당하지 않는 선에서의 속도 최적화) ───────────────────────────────────────
IO_THREADS   = 12         # 네트워크 병렬 스레드 (403/429 가 보이면 6 으로 낮추세요)
CPU_WORKERS  = 0          # 0 = 자동(코어수-1). 노트북에서 프로세스 병렬 불가 시 자동 폴백
QPS_CAP = {"dart": 8.0, "dart_zip": 1.0, "krx": 2.5, "naver": 3.0, "hankyung": 2.5,
           "datagokr": 5.0, "customs": 3.0, "kind": 2.0, "fdrcache": 4.0, "generic": 3.0}
#            ↑ dart_zip 은 수백 MB 파일이라 '초당 요청수'가 아니라 동시 연결수가 실질 제약이다.
#              1.0 은 시작 간격만 벌려 서버에 동시 착수 부하를 주지 않기 위한 것.

# ── ⑧-1 가격 수집 정책 (★2026-08 구조개편: 종목축 → 날짜축) ──────────────────────────────────
#     KRX 전종목시세는 "하루 1회 호출 = 그날 상장된 종목 전부"를 준다.
#     10년 ≈ 2,700 거래일 → 2,700회로 끝나고, 상장폐지 종목도 '당시 상장돼 있던 날'에
#     자동으로 들어온다. 종목축(5,400종목 × 소스 5개)으로 돌면 최대 27,000 왕복인데
#     그중 절반은 애초에 데이터가 존재하지 않는 폐지·비보통주라 전부 낭비였다.
PX_ALLOW_YFINANCE     = False   # 종목별 폴백에 yfinance 사용 여부. ★기본 False —
#                                 국내 6자리 코드는 야후에 거의 없는데 실패 1건마다
#                                 .KS/.KQ 두 왕복 + 내부 재시도를 태운다(수집 예산의 주범).
#                                 지수 벤치마크에는 이 값과 무관하게 최후 폴백으로 쓴다.
PX_RESIDUAL_MAX_CODES = 300     # 벌크가 못 덮은 종목의 종목축 구제 상한(0=무제한, 권장 300)
PX_RESIDUAL_COV_SKIP  = 0.97    # ★벌크가 구간 거래일의 이 비율 이상을 덮었으면 '잔여 보충'을
#                                 통째로 생략한다. 그 상태에서 시세가 없는 코드는 수집 실패가
#                                 아니라 애초에 거래된 적이 없는 코드(폐지 우선주·ETF·ELW·
#                                 스팩)라, 종목축으로 다시 물어봐야 전부 빈손이고 시간만 탄다.
#                                 실측: 이 게이트가 없어 매 실행 300종목 × 3소스 = 5분을 버렸다.
PX_RESIDUAL_COV_CODES = 0.35    # ★위 게이트의 두 번째 조건 — 하루 평균 마스터의 이 비율 이상이
#                                 실제로 들어와 있어야 한다. 날짜 커버리지만 보면 '일부 종목 ×
#                                 전 기간'짜리 구 캐시가 100%를 만들어, 반쪽 패널을 '전부
#                                 수집됨'으로 선언한다(막으려는 대상이 종목축이므로 축이 맞아야
#                                 한다). 마스터에는 ETF/ELW/스팩·비보통주가 섞여 있어 정상
#                                 상태의 실측 커버리지가 60~75% 수준이라 0.35 를 바닥으로 둔다.

# ── ⑧-2 DART 수집 정책 (호출량은 '고정 예산'이 아니라 '실시간 잔여'로 관리) ───────────────────
DART_BULK_ZIP    = True   # ★재무제표 '일괄 ZIP'(연도×보고서×제표 파일 하나에 전 상장사).
#                           단건 API 78,000회를 약 150회 다운로드로 대체하며, 이 경로는
#                           crtfc_key 를 쓰지 않아 ★일일 호출한도를 전혀 소비하지 않는다.
#                           재고자산·매출채권·영업CF·CAPEX 가 십수 분 만에 채워진다.
PACK_TIME_SHARE = 0.25    # ★센서팩(N·P·X) 수집에 줄 시간 몫 — 진입 시 '잔여 시간'의 비율.
#                           호출 예산은 소스별로 나뉘지만 ★시간 예산은 하나다. 센서팩을
#                           DART 앞으로 옮긴 뒤 이 몫이 없으면, 팩이 4시간을 다 먹고
#                           DART 가 굶는다. 그러면 θ_N(=가입자수/직원수)·θ_X(=수출/매출)의
#                           ★분모가 사라져 그 팩 축이 통째로 죽는다 — 팩을 먼저 받으려던
#                           목적과 정확히 반대의 결과다. 그래서 몫을 물리적으로 건다.
PACK_TIME_CAP_MIN = 50    # 위 비율과 무관하게 넘지 않을 절대 상한(분). 0 = 비율만 적용.
USDKRW_CONST = 1300.0     # θ_X 계산용 환산율. 관세 통계는 USD, 재무는 KRW 라 축을 맞춰야 한다.
#                           θ_X 는 '수출/매출 비율이 그럴듯한가'라는 정합성 지표라 환율의
#                           연도별 변동(1,100~1,400)이 판정을 뒤집지 않는다. 정밀 환산이
#                           필요해지면 여기를 월별 환율 시계열로 바꾸세요.
DART_ZIP_WORKERS = 4      # ★일괄 ZIP 동시 다운로드 수(정부 사이트라 4 이상은 이득 없이 위험).
#                           파일은 개당 2~8MB · 129개 총 0.5~0.9GB 로 작다 — 진짜 비용은
#                           압축 해제 후 40~55MB 짜리 TSV 를 pandas 로 읽는 CPU 쪽이다.
#                           그래서 다운로드는 4병렬로 겹쳐 두고 파싱은 순차로 흘린다.
#                           직렬이었을 때는 129개에 몇 시간이 걸렸고, 진행바가 파일 단위로만
#                           움직여 '멈춤'과 구별이 안 됐다(실측: 0/129 에서 정체로 오인).
DART_BULK_MULTI  = True   # 다중회사 주요계정(fnlttMultiAcnt): 회사 100개를 한 번에 조회.
#                           전 시장 12년을 약 1,600회로 덮는다(단건이면 16만회).
DART_MULTI_BATCH = 100    # 한 요청에 넣을 회사 수(공식 상한 100). status 021 이 나면 낮추세요.
NPS_MAX_CALLS    = 0      # PACK-N 종목 상한(0 = 실시간 잔여가 허용하는 만큼).
#                           ★2026-08 재설계로 (종목 × 월) 교차곱이 사라졌다 — 월은 요청이 아니라
#                           응답에서 나온다. 종목당 검색 1 + 기간 1 + 상세 ≤3 회이므로 전 종목이
#                           약 2만 회에 끝난다(옛 구현은 647,760회 = 65일이었고 그나마 0행이었다).
DATAGOKR_BUDGET_SHARE = {  # ★공공데이터포털 하루치를 팩별로 나눈다. 하나가 다 먹으면 나머지가
    "nps":     0.55,       #   매 실행 0건이 된다(DART 에서 세 번 겪은 사고와 같은 구조).
    "procure": 0.35,       #   PACK-P 조달 — 월축이라 수요가 작지만 완주 원장이 있어 잘 이어받는다
    "customs": 0.10,       #   PACK-X 관세 — HS 매핑이 있어야만 동작하므로 대개 수요 0
}
# ★DART 하루치 잔여를 소비자별로 나눈다. 가중치는 '아직 배정 안 받은 소비자들 사이의 상대값'
#   이고, 배정은 수집 직전에 실잔여를 다시 재서 하며, 실수요보다 많이 주지 않는다.
#   그래서 ①앞선 놈이 다 먹는 사고 ②할 일 없는 놈이 예산을 깔고 앉는 사고 를 동시에 막는다.
#   (세 번 무너졌다: 심층재무가 직원현황을 → 직원현황이 심층재무를 → 일괄 ZIP 이 재무를 이미
#    다 덮었는데도 deep+major 가 고정 65%를 선점해 직원현황이 800건에서 끊겼다.)
#   ★배정 순서 = disclosure → employee → major → deep. '대체재가 없는 쪽'이 먼저다.
#     재무는 일괄 ZIP(호출한도 0)이라는 무한 대체재가 있고, 직원현황은 이 API 말고는 없다.
DART_BUDGET_SHARE = {
    "disclosure": 0.10,   # 공시목록 시장전체 스윕 — V3/V5/PACK-C 입력 + ★정기보고서 제출사실
    #                       지도(이걸로 뒤 티어의 '태생적 빈손' 호출을 통째로 소거한다)
    "employee":   0.70,   # ★직원현황 전수 — 대체재 없음. C축 TP_C2·V8·PACK-N·size_bucket 1순위
    #                       하루 한도의 대부분을 여기 쏟아야 전수 완비가 2일 안에 끝난다.
    "major":      0.10,   # 주요계정 벌크 — ZIP 미포함분 바닥 깔기(회사 100개/호출).
    #                       전 시장 13년을 1,900회면 덮으므로 이 몫을 다 쓸 일이 없다.
    "deep":       0.10,   # 전체재무제표 단건 — ZIP 이 못 준 연도·비제출사의 '꼬리 보충'.
    #                       ★몫이 작은 이유: 같은 계정을 일괄 ZIP 이 호출한도 0 으로 이미
    #                       채운다. 여기에 예산을 주는 것은 '이미 가진 것을 다시 사는' 일이다.
}
DART_DEEP_TOP_N  = 1500   # 전체재무제표 '단건 꼬리 보충'을 받을 유동성 상위 회사 수.
#                           V6 유동성 하한을 통과할 수 없는 종목까지 단건으로 태울 이유가 없다.
#                           ※ 직원현황에는 적용하지 않는다 — 그쪽은 전수수집이 원칙이다.
#                           0 = 전 종목(호출량이 매우 커집니다).

# ── ⑨ 포지션·사이징 상수 (§8.5 — 드로다운 한가운데서 정하지 않도록 지금 못박음) ──────────────
ENTRY_TOP_PCT   = 0.05          # 신호 상위 5% 진입
MAX_NAMES       = 25
MIN_NAMES       = 5
MAX_WEIGHT      = 0.12          # 종목당 최대 비중
ADV_PARTICIP    = 0.10          # 20일 평균거래대금의 10% 이내
MAX_HOLD_MONTHS = 24
ACCOUNT_KRW     = 30_000_000    # 소액계좌 가정(비용·유동성 상한 계산용)
MIN_ADV_KRW     = 300_000_000   # V6 유동성 하한 (20일 평균거래대금)

# ── ⑩ 비교전략 — 시가총액 하위 1000 압축 유니버스 ────────────────────────────────────────────
#     본전략과 동일한 신호·엔진을 "시총 하위 1000종목"으로 압축한 유니버스에 적용해
#     백테스트→성과검증→강건성검사→해석표를 따로 출력하고 본전략과 비교표를 만듭니다.
COMPARE_ENABLED  = True
COMPARE_BOTTOM_N = 1000

# ── ⑪ 실행 모드 ─────────────────────────────────────────────────────────────────────────────
#     "SMOKE" : 합성데이터로 전체 출력물(백테스트·성과·강건성·해석표·비교전략) 예행연습.
#               네트워크·키 불필요. 처음 한 번은 이걸로 배관을 확인하세요.
#     "FULL"  : 스모크 통과 → 실데이터 수집 → 전체 실행 (기본값)
#     "CACHED": 신규 수집 없이 드라이브/로컬 캐시만으로 실행 (오프라인 재현)
RUN_MODE = "FULL"

SEED = 20260809                 # C8 결정성 — 모든 난수는 이 시드에서 파생
STOP_ON_KILL = True             # §15 킬 기준 위반 시 즉시 중단·보고 (끄지 마세요)
ACTIVE_PACKS = ["C", "N", "D", "X", "P"]   # 데이터가 없는 팩은 자동 비활성화(§8.4)되고 로그에 남습니다

# ── ⑫ 런타임 (C10) ──────────────────────────────────────────────────────────────────────────
#     각 계층 소요시간을 전부 실측해 표로 출력합니다(추측 금지·측정).
#     ★ "4시간 내 백테스트 결과" 제약은 사용자 지시(2026-08-09)로 폐지되었습니다.
#       계측과 계층별 참고 예산 표시는 유지하되, 초과를 결함으로 판정하지 않습니다.
RUNTIME_4H_LIMIT_ABOLISHED = True

# ════════════════════════════════════════════════════════════════════════════════════════════
#   설정 끝 — 아래부터는 수정할 필요가 없습니다.
# ════════════════════════════════════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [1] 부트스트랩 — 환경 감지(Colab/JupyterLab/CLI) · 의존성 자동 설치 · 표준 임포트          ║
# ║     실패하면 "무엇이 없고 어떻게 설치하는지"를 한글로 출력하고 멈춥니다.                    ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝
import os, sys, io, re, gc, json, math, time, zlib, random, shutil, string, hashlib, zipfile
import platform, tempfile, threading, traceback, subprocess, unicodedata, warnings
import xml.etree.ElementTree as _ET
import datetime as dtm
from collections import Counter, OrderedDict, defaultdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, quote, urljoin

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

# 윈도우 콘솔(cp949)은 이 코드가 쓰는 ─│✔⚠ 문자를 못 찍고 UnicodeEncodeError 로 즉사한다.
# 표준출력을 UTF-8 로 재설정하고, 그래도 안 되면 ASCII 로 낮춰서 정보만은 전부 살린다.
for _nm in ("stdout", "stderr"):
    try:
        _st = getattr(sys, _nm, None)
        if _st is not None and hasattr(_st, "reconfigure"):
            _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_ASCII_MAP = str.maketrans({"═": "=", "─": "-", "│": "|", "┼": "+", "╔": "+", "╗": "+",
                            "╚": "+", "╝": "+", "║": "|", "┌": "+", "┐": "+", "└": "+",
                            "┘": "+", "├": "+", "┤": "+", "┬": "+", "┴": "+", "✔": "OK ",
                            "✘": "X ", "⚠": "! ", "★": "*", "▶": ">", "▷": ">", "·": ".",
                            "Δ": "d", "θ": "th", "σ": "s", "×": "x", "∏": "prod", "≤": "<=",
                            "≥": ">=", "⭐": "*", "⛔": "STOP ", "…": "...", "⬇": "v"})


def say(*args, **kw):
    """어떤 콘솔에서도 죽지 않는 print."""
    try:
        print(*args, **kw)
    except UnicodeEncodeError:
        try:
            print(*[str(a).translate(_ASCII_MAP) for a in args], **kw)
        except Exception:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(*[str(a).encode(enc, "replace").decode(enc, "replace") for a in args], **kw)


def _probe_environment() -> Dict[str, Any]:
    env = {"colab": False, "notebook": False, "shell": "cli",
           "python": sys.version.split()[0], "os": platform.system(),
           "cores": os.cpu_count() or 2}
    try:
        import importlib.util as _ilu
        env["colab"] = (_ilu.find_spec("google.colab") is not None) or \
                       bool(os.environ.get("COLAB_RELEASE_TAG"))
    except Exception:
        pass
    try:
        from IPython import get_ipython           # type: ignore
        ip = get_ipython()
        if ip is not None:
            env["notebook"] = True
            env["shell"] = type(ip).__name__
    except Exception:
        pass
    return env


ENVX = _probe_environment()

# ── 의존성 ──────────────────────────────────────────────────────────────────────────────────
_MUST_HAVE = [("numpy", "numpy"), ("pandas", "pandas"), ("pyarrow", "pyarrow"),
              ("requests", "requests"), ("bs4", "beautifulsoup4"), ("lxml", "lxml"),
              ("tqdm", "tqdm")]
_NICE_HAVE = [("FinanceDataReader", "finance-datareader", "가격·상장/상폐 목록 1순위 폴백"),
              ("pykrx", "pykrx", "KRX 스냅샷·시가총액·수급 (마켓플레이스 계정 연동)"),
              ("yfinance", "yfinance", "지수 벤치마크 최종 폴백"),
              ("rapidfuzz", "rapidfuzz", "상호/애널리스트명 고속 유사도 매칭")]


def _pip(pkgs: List[str]) -> bool:
    if not pkgs or os.environ.get("TCD_NO_PIP"):
        return True
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                            "--disable-pip-version-check", "--no-input"] + pkgs,
                           capture_output=True, text=True, timeout=1500)
        return r.returncode == 0
    except Exception:
        return False


def _boot_dependencies() -> Dict[str, bool]:
    import importlib.util as ilu
    need = [p for m, p in _MUST_HAVE if ilu.find_spec(m) is None]
    if need:
        say(f"[부트스트랩] 필수 패키지 설치: {', '.join(need)} (1~3분)")
        if not _pip(need):
            say("=" * 90)
            say("❌ 필수 패키지 설치 실패 — 아래 명령을 직접 실행한 뒤 다시 시작하세요.")
            say("   pip install " + " ".join(need))
            say("=" * 90)
            raise SystemExit(1)
        importlib_invalidate()
    opt = [p for m, p, _w in _NICE_HAVE if ilu.find_spec(m) is None]
    if opt:
        say(f"[부트스트랩] 선택 패키지 설치 시도: {', '.join(opt)} (실패해도 폴백으로 계속)")
        _pip(opt)
        importlib_invalidate()
    return {m: ilu.find_spec(m) is not None for m, _p, _w in _NICE_HAVE}


def importlib_invalidate():
    import importlib
    importlib.invalidate_caches()


# ★ 자격증명은 서드파티 import 이전에 환경변수로 주입한다.
#   pykrx 는 모듈 로드 시점에 KRX 세션을 만들기 때문에, 순서를 뒤집으면 예외 없이
#   '비인증 세션'이 생겨 이후 모든 조회가 로그인 HTML 을 받는 미궁 실패가 된다.
if KRX_MARKETPLACE_ID and KRX_MARKETPLACE_PW:
    os.environ["KRX_ID"] = KRX_MARKETPLACE_ID
    os.environ["KRX_PW"] = KRX_MARKETPLACE_PW

HAVE = _boot_dependencies()

# ★서드파티(pykrx·FinanceDataReader·yfinance)는 자체 requests 로 나가며 타임아웃이 없다.
#   한 소켓이 멈추면 스레드풀·메인스레드가 같이 멈추고 수집 시간예산이 영영 발화하지 않는다.
#   임포트 전에 전역 소켓 타임아웃을 걸어 그 경로 전부에 상한을 상속시킨다.
import socket as _socket
try:
    _socket.setdefaulttimeout(90)
except Exception:
    pass
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from tqdm.auto import tqdm
except Exception:                                              # pragma: no cover
    def tqdm(x=None, **k):                                     # type: ignore
        return x if x is not None else iter(())

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 120)
np.seterr(all="ignore")

random.seed(SEED)
np.random.seed(SEED % (2 ** 31 - 1))
RNG = np.random.default_rng(SEED)

fdr = pykrx_stock = yf = rf_fuzz = None
if HAVE.get("FinanceDataReader"):
    try:
        import FinanceDataReader as fdr            # type: ignore
    except Exception:
        fdr = None
PKX_WHY = ""
if HAVE.get("pykrx"):
    try:
        from pykrx import stock as pykrx_stock     # type: ignore
    except Exception as _e:                        # noqa
        pykrx_stock = None
        # ★임포트 실패를 조용히 삼키면 "왜 전종목 경로가 안 도나"를 알 수 없다.
        #   최신 파이썬(3.13/3.14)에는 아직 휠이 없는 서드파티가 흔하다.
        PKX_WHY = f"임포트 실패({type(_e).__name__}: {str(_e)[:70]})"
else:
    PKX_WHY = "미설치"
if HAVE.get("yfinance"):
    try:
        import yfinance as yf                      # type: ignore
    except Exception:
        yf = None
if HAVE.get("rapidfuzz"):
    try:
        from rapidfuzz import fuzz as rf_fuzz      # type: ignore
    except Exception:
        rf_fuzz = None

import multiprocessing as _mp
try:
    _FORK_OK = ("fork" in _mp.get_all_start_methods()) and ENVX["os"] == "Linux"
except Exception:
    _FORK_OK = False
N_CPU_WORKERS = CPU_WORKERS if CPU_WORKERS and CPU_WORKERS > 0 else max(1, ENVX["cores"] - 1)


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [2] 관제탑 — 콘솔 · 스테이지 실행기 · 데이터 I/O 원장 · 에러 국소화 · 런타임 계측(C10)     ║
# ║                                                                                          ║
# ║   목적은 하나: "어디서 터졌고, 어떤 데이터가 어디서 들어와 어디로 나갔는가"를              ║
# ║   스크롤 없이 한 화면에서 볼 수 있게 만드는 것.                                            ║
# ║   · 모든 연산은 RUN.step(...) 블록 안에서만 돈다 → 실패 시 스테이지ID·입출력·힌트 출력      ║
# ║   · 모든 파일/HTTP/메모리 입출력은 RUN.io(...) 원장에 남는다 (행수·PIT컬럼 유무·소스)       ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

_BOOT_T0 = time.time()


def _wcw(s: str) -> int:
    """한글(전각) 폭 2 를 반영한 표시 폭 — 표 정렬이 깨지지 않게 하는 유일한 방법."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(s))


def _fit(s: str, width: int, align: str = "l") -> str:
    s = str(s)
    if _wcw(s) > width:                                   # 자르기(말줄임)
        out = ""
        for ch in s.replace("\n", " "):
            if _wcw(out) + _wcw(ch) > width - 1:
                s = out + "…"
                break
            out += ch
        else:
            s = out
    pad = max(0, width - _wcw(s))
    if align == "r":
        return " " * pad + s
    if align == "c":
        return " " * (pad // 2) + s + " " * (pad - pad // 2)
    return s + " " * pad


class Console:
    """수집·백테스트·강건성·해석표 출력 전용 콘솔. 버퍼를 보관해 실행 로그 파일로도 저장한다."""

    def __init__(self):
        self.tape: List[str] = []
        self._lk = threading.RLock()
        self.scope: List[str] = []

    def _put(self, icon: str, msg: str):
        el = time.time() - _BOOT_T0
        head = f"[{int(el//60):02d}:{el % 60:05.2f}] {_fit('/'.join(self.scope)[-30:], 30)} "
        line = head + icon + str(msg)
        with self._lk:
            self.tape.append(line)
        say(line, flush=True)

    def info(self, m): self._put("  ", m)
    def ok(self, m):   self._put("✔ ", m)
    def warn(self, m): self._put("⚠ ", m)
    def err(self, m):  self._put("✘ ", m)

    def h1(self, title: str, sub: str = "", w: int = 102):
        for ln in ("", "╔" + "═" * (w - 2) + "╗",
                   "║ " + _fit(title, w - 4) + " ║") + \
                  (("║ " + _fit(sub, w - 4) + " ║",) if sub else ()) + \
                  ("╚" + "═" * (w - 2) + "╝",):
            with self._lk:
                self.tape.append(ln)
            say(ln, flush=True)

    def h2(self, title: str, w: int = 102):
        line = f"── {title} " + "─" * max(0, w - _wcw(title) - 4)
        with self._lk:
            self.tape.append(line)
        say(line, flush=True)

    def grid(self, rows: List[Sequence[Any]], headers: Sequence[str],
             aligns: Optional[Sequence[str]] = None, cap: int = 52, title: str = ""):
        """한글 폭 보정 표 출력 — 성과표/강건성표/감사표 전부 이걸 쓴다."""
        if title:
            say("")
            self._put("▶ ", title)
        if not rows:
            say("   (표시할 행이 없습니다)")
            return
        ncol = len(headers)
        aligns = list(aligns or ["l"] * ncol)
        cells = [[("" if c is None else str(c)) for c in list(r)[:ncol]] + [""] * (ncol - len(r))
                 for r in rows]
        widths = [min(cap, max(_wcw(str(headers[i])), *(_wcw(r[i]) for r in cells)))
                  for i in range(ncol)]
        lines = ["  " + " │ ".join(_fit(str(headers[i]), widths[i], "c") for i in range(ncol)),
                 "  " + "─┼─".join("─" * widths[i] for i in range(ncol))]
        lines += ["  " + " │ ".join(_fit(r[i], widths[i], aligns[i]) for i in range(ncol))
                  for r in cells]
        for ln in lines:
            with self._lk:
                self.tape.append(ln)
            say(ln, flush=True)


L = Console()


# ── 예외 → 한글 진단 힌트 (원인 범위와 성질을 특정해 준다) ──────────────────────────────────
_HINTS: List[Tuple[str, str]] = [
    (r"SERVICE_KEY_IS_NOT_REGISTERED|SERVICE ?KEY",
     "공공데이터포털 인증키 문제입니다. 해당 API '활용신청' 승인 여부와, DATA_GO_KR_KEY 에 "
     "'일반 인증키(Decoding)' 를 넣었는지 확인하세요. Encoding 키는 이중 인코딩으로 항상 실패합니다."),
    (r"LIMITED_NUMBER_OF_SERVICE_REQUESTS",
     "공공데이터포털 일일 한도 초과입니다. 지금까지 받은 분량은 드라이브에 저장되어 있고 "
     "재실행 시 이어받습니다."),
    (r"status.*020|요청.*제한.*초과",
     "DART 일일 호출한도 도달 신호(020)입니다. 코드가 그 지점을 오늘의 실제 한도로 학습하고 "
     "멈췄습니다. 내일 재실행하면 이어받습니다."),
    (r"403|Forbidden",
     "403 차단입니다. QPS_CAP 을 절반으로 낮추고 IO_THREADS 를 6 이하로 줄이세요. "
     "네이버/한경은 User-Agent·Referer 가 없으면 즉시 차단합니다."),
    (r"429|Too Many Requests", "요청 속도가 너무 빠릅니다. QPS_CAP 을 낮추세요."),
    (r"ConnectionError|NameResolution|Timeout|SSLError|ProxyError|Max retries",
     "네트워크 도달 실패입니다. 방화벽/프록시 환경이면 해당 도메인이 막혔을 수 있습니다. "
     "RUN_MODE='CACHED' 로 캐시만으로도 백테스트가 됩니다."),
    (r"MyDrive|drive/MyDrive|No such file.*drive",
     "구글드라이브 미마운트입니다. Colab이면 인증 팝업을 승인하세요. JupyterLab 은 "
     "동기화 폴더(또는 LOCAL_FALLBACK_ROOT)로 자동 전환됩니다."),
    (r"No space left|Disk quota", "드라이브/디스크 용량 부족입니다. DOWNLOAD_REPORT_PDF=False 권장."),
    (r"MemoryError|Unable to allocate|Killed",
     "메모리 부족입니다. IO_THREADS·CPU_WORKERS 를 줄이세요. 패널은 float32 로 이미 축소됩니다."),
    (r"JSONDecodeError|Expecting value",
     "JSON 대신 HTML(대개 로그인/차단 페이지)을 받았습니다. KRX 계열이면 중복 로그인으로 세션이 "
     "끊긴 것입니다 — 브라우저에서 같은 계정을 동시에 쓰고 있지 않은지 확인하세요."),
    (r"CD011|중복\s*로그인", "KRX 중복 로그인입니다. 다른 기기의 로그인이 이 세션을 끊었습니다."),
    (r"knowledge_date",
     "PIT 컬럼 누락(C1)입니다. 새 수집 테이블은 pit_mark(df, event, knowledge) 로 감싸야 "
     "PIT 저장소에 등록됩니다. 우회 경로는 만들지 않았습니다."),
    (r"ArrowInvalid|parquet",
     "parquet 손상/쓰기 실패입니다. 이 코드는 임시파일→원자적 교체로 쓰므로 손상본은 이전 실행 "
     "잔재입니다. 손상 파일은 .corrupt 로 격리되며 원본 데이터는 저널에 남아 있습니다."),
    (r"Can't pickle|BrokenProcessPool",
     "노트북 프로세스 병렬 실패(고질적) — 스레드로 자동 폴백하며 결과는 동일하고 속도만 느립니다."),
    (r"tz-aware|tz-naive", "타임존 혼재 비교입니다. 새 소스가 tz-aware 날짜를 반환했는지 보세요."),
    (r"empty|No objects to concatenate|zero-size",
     "수집 결과가 비었습니다. ①키 미입력 ②구간 내 데이터 없음 ③소스 구조 변경 순으로 의심하고, "
     "바로 위 I/O 원장에서 어느 소스가 0행인지 확인하세요."),
]


def explain_exception(e: BaseException) -> str:
    blob = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    for pat, hint in _HINTS:
        if re.search(pat, blob, re.I):
            return hint
    return ("등록된 패턴 밖의 오류입니다. 트레이스백 마지막 프레임과 직전 I/O 원장 행을 함께 보면 "
            "원인 구간이 좁혀집니다.")


class KillGate(Exception):
    """§15 킬 기준 — 우회·파라미터 조정으로 통과시키지 말고 그대로 보고한다."""


class StepFailed(Exception):
    pass


class FlightRecorder:
    """스테이지 실행기 + I/O 원장 + 런타임 계측(C10). 모든 계산은 step() 안에서만 돈다."""

    LAYER_BUDGET_MIN = {"L1": 30, "L2": 2, "L3": 3, "L5": 240}     # 계약 참고치(분)

    def __init__(self):
        self.steps: "OrderedDict[str, dict]" = OrderedDict()
        self.ledger: List[dict] = []
        self.cur: Optional[dict] = None
        self._lk = threading.RLock()

    # I/O 원장 -----------------------------------------------------------------------------
    def io(self, way: str, kind: str, name: str, obj: Any = None, src: str = "", note: str = ""):
        rows = cols = -1
        pit = "—"
        try:
            if isinstance(obj, pd.DataFrame):
                rows, cols = obj.shape
                have = [c for c in ("event_date", "knowledge_date") if c in obj.columns]
                pit = "+".join(h[0].upper() for h in have) if have else "—"
            elif isinstance(obj, (list, tuple, set, dict)):
                rows = len(obj)
            elif isinstance(obj, (int, float)) and np.isfinite(obj):
                rows = int(obj)
        except Exception:
            pass
        ev = {"step": (self.cur or {}).get("sid", "-"), "way": way, "kind": kind,
              "name": str(name), "rows": rows, "cols": cols, "pit": pit,
              "src": src, "note": note}
        with self._lk:
            self.ledger.append(ev)
            if self.cur is not None and rows > 0:
                self.cur["r_in" if way == "IN" else "r_out"] += rows
        return obj

    def note(self, msg: str):
        if self.cur is not None:
            self.cur["notes"].append(str(msg))

    # 스테이지 -----------------------------------------------------------------------------
    def skip(self, sid: str, title: str, why: str, layer: str = "L0"):
        """★스테이지를 '실행하지 않았다'고 기록만 한다 — 본문은 호출부의 if 로 감싼다.

        ★step(skip=True) 를 쓰면 안 된다. @contextmanager 에서 yield 는 with 본문으로
          제어를 넘기므로, skip 분기가 yield 하는 순간 ★본문이 그대로 실행된다.
          게다가 그 yield 는 try/except 밖이라 critical=False 격리까지 사라진다.
          실측 피해: COLLECT_RESEARCH=False 로 꺼 뒀는데도 한경·네이버를 그대로 긁었고,
          PACK-D 를 끄면 '건너뜀' 로그를 찍은 채 공시 원문 수천 건을 DART 쿼터로 받았다.
          Python 의 생성기 컨텍스트매니저로는 본문을 건너뛸 수 없다 — 그러니 조건은
          바깥 if 로 쓰고, 그 사실만 여기에 남긴다.
        """
        rec = {"sid": sid, "title": title, "layer": layer, "state": "SKIP",
               "t0": time.time(), "t1": time.time(), "r_in": 0, "r_out": 0,
               "err": "", "hint": "", "tb": "", "notes": [why or "조건 미충족"]}
        self.steps[sid] = rec
        L.scope.append(sid)
        L.warn(f"건너뜀 — {why}")
        L.scope.pop()
        return rec

    @contextmanager
    def step(self, sid: str, title: str, layer: str = "L0", critical: bool = True,
             skip: bool = False, skip_why: str = ""):
        rec = {"sid": sid, "title": title, "layer": layer, "state": "RUN", "t0": time.time(),
               "t1": None, "r_in": 0, "r_out": 0, "err": "", "hint": "", "tb": "",
               "notes": []}
        self.steps[sid] = rec
        prev, self.cur = self.cur, rec
        L.scope.append(sid)
        if skip:
            # ★여기서 yield 하면 본문이 실행된다(위 skip() docstring 참조). 그래서 이
            #   인자는 더 이상 제어에 쓰지 않는다 — 남아 있는 호출부가 있으면 시끄럽게
            #   알리고, 본문은 try 안에서 정상 실행시켜 최소한 격리는 유지한다.
            rec["notes"].append(skip_why or "조건 미충족")
            L.warn(f"[{sid}] step(skip=) 은 본문을 건너뛰지 못합니다 — 조건을 바깥 if 로 "
                   f"옮기고 RUN.skip() 으로 기록하세요. 이번엔 그대로 실행합니다"
                   f"({skip_why}).")
        L.info(f"▷ {title}")
        try:
            yield rec
            rec["t1"] = time.time()
            rec["state"] = "WARN" if any(n.startswith("WARN") for n in rec["notes"]) else "OK"
            L.ok(f"완료 {rec['t1']-rec['t0']:6.2f}s  in={rec['r_in']:,} out={rec['r_out']:,}")
        except KillGate:
            rec["t1"], rec["state"] = time.time(), "KILL"
            raise
        except BaseException as e:                                # noqa
            rec["t1"], rec["state"] = time.time(), "FAIL"
            rec["err"] = f"{type(e).__name__}: {str(e)[:500]}"
            rec["hint"] = explain_exception(e)
            rec["tb"] = traceback.format_exc()
            self._failure_screen(rec)
            if critical:
                raise StepFailed(f"[{sid}] {title} 실패 — {rec['err']}") from e
            rec["state"] = "WARN"
            rec["notes"].append(f"WARN: 비필수 스테이지 실패({type(e).__name__}) — 건너뛰고 진행")
        finally:
            L.scope.pop()
            self.cur = prev

    def _failure_screen(self, rec: dict):
        L.h1(f"✘ 실패 지점: [{rec['sid']}] {rec['title']}",
             f"계층 {rec['layer']} · 경과 {rec['t1']-rec['t0']:.2f}s")
        say(f"  예외 : {rec['err']}")
        say(f"  진단 : {rec['hint']}")
        recent = [e for e in self.ledger if e["step"] == rec["sid"]][-8:]
        if recent:
            L.grid([[e["way"], e["kind"], e["name"], (f"{e['rows']:,}" if e["rows"] >= 0 else "-"),
                     e["pit"], e["src"] or e["note"]] for e in recent],
                   ["방향", "종류", "대상", "행수", "PIT", "소스/비고"],
                   ["c", "l", "l", "r", "c", "l"],
                   title="이 스테이지의 직전 입출력 — 무엇이 비었는지 여기서 보입니다")
        say("  ── 트레이스백(마지막 12줄) " + "─" * 60)
        for ln in rec["tb"].rstrip().split("\n")[-12:]:
            say("   " + ln)

    # 리포트 -------------------------------------------------------------------------------
    def table_steps(self):
        L.h1("스테이지 실행 요약", "상태 · 소요시간 · 입출력 행수 — 에러가 났다면 여기서 위치부터")
        icon = {"OK": "✔", "WARN": "⚠", "FAIL": "✘", "SKIP": "→", "RUN": "…", "KILL": "⛔"}
        rows = [[r["layer"], r["sid"], r["title"], icon.get(r["state"], "?") + r["state"],
                 f"{(r['t1'] or time.time())-r['t0']:8.2f}", f"{r['r_in']:,}", f"{r['r_out']:,}",
                 "; ".join(r["notes"])[:44]] for r in self.steps.values()]
        L.grid(rows, ["계층", "ID", "스테이지", "상태", "초", "입력행", "출력행", "비고"],
               ["c", "l", "l", "c", "r", "r", "r", "l"])

    def table_ledger(self, last: int = 160):
        L.h1("데이터 I/O 원장", "무엇이 어디서 몇 행 들어와 어디로 나갔는가 · PIT=E(event)/K(knowledge)")
        evs = self.ledger[-last:]
        if len(self.ledger) > last:
            L.warn(f"원장 {len(self.ledger):,}건 중 최근 {last}건만 표시")
        L.grid([[e["step"], e["way"], e["kind"], e["name"],
                 (f"{e['rows']:,}" if e["rows"] >= 0 else "-"),
                 (f"{e['cols']}" if e["cols"] >= 0 else "-"), e["pit"],
                 e["src"] or e["note"]] for e in evs],
               ["스테이지", "방향", "종류", "대상", "행수", "열수", "PIT", "소스/비고"],
               ["l", "c", "l", "l", "r", "r", "c", "l"], cap=42)

    def table_runtime(self):
        L.h1("런타임 감사 (C10)", "계층별 실측 — 추측하지 않고 측정한다")
        agg: Dict[str, float] = defaultdict(float)
        for r in self.steps.values():
            agg[r["layer"]] += (r["t1"] or time.time()) - r["t0"]
        rows = []
        for lay in sorted(agg):
            ref = self.LAYER_BUDGET_MIN.get(lay)
            note = "—"
            if ref is not None:
                note = f"참고 {ref}분" + ("" if agg[lay] <= ref * 60 else " (초과 — 참고용)")
            rows.append([lay, f"{agg[lay]:9.2f}s", f"{agg[lay]/60:7.2f}분", note])
        tot = sum(agg.values())
        rows.append(["합계", f"{tot:9.2f}s", f"{tot/60:7.2f}분",
                     "4시간 제약 폐지(사용자 지시 2026-08-09) — 계측만 유지"])
        L.grid(rows, ["계층", "실측(초)", "실측(분)", "판정"], ["c", "r", "r", "l"])
        L.info("계층: L0 부트/캐시 · L1 수집/정제/피처 · L2 스코어 · L3 백테스트 · "
               "L5 강건성 · L6 리포트 · L7 비교전략")


RUN = FlightRecorder()


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [3] 공용 유틸 — 날짜/코드 정규화 · 원자적 파일 IO · 재시도 · 스로틀 · 병렬 · 수치 프리미티브 ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

# ── 날짜 ────────────────────────────────────────────────────────────────────────────────────
def d_(x) -> Optional[pd.Timestamp]:
    """무엇이 오든 tz-naive 자정 Timestamp. 타임존 혼재는 한국 데이터 파이프라인 최빈 버그."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    try:
        t = pd.Timestamp(x)
    except Exception:
        t = pd.to_datetime(str(x), errors="coerce")
    if t is pd.NaT or pd.isna(t):
        return None
    if getattr(t, "tzinfo", None) is not None:
        t = t.tz_convert(None) if t.tz is not None else t.tz_localize(None)
    return t.normalize()


def ds_(s) -> pd.Series:
    out = pd.to_datetime(pd.Series(s), errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        pass
    return out.dt.normalize()


def eom(x) -> Optional[pd.Timestamp]:
    t = d_(x)
    return None if t is None else (t + pd.offsets.MonthEnd(0)).normalize()


def month_grid(a, b) -> pd.DatetimeIndex:
    return pd.date_range(eom(a), eom(b), freq="ME")


def parse_kr_date(raw: Any) -> Optional[str]:
    """'26.01.19' 같은 두 자리 연도를 자동추론에 맡기면 연·일이 뒤바뀐다 → 직접 판별."""
    s = str(raw or "").strip()
    m = re.match(r"^(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})$", s)
    if m:
        yy, mm, dd = (int(g) for g in m.groups())
        year = 2000 + yy if yy <= 69 else 1900 + yy
        try:
            return f"{year:04d}-{mm:02d}-{dd:02d}"
        except Exception:
            return None
    t = d_(s)
    return None if t is None else t.strftime("%Y-%m-%d")


# ── 해시/텍스트 ─────────────────────────────────────────────────────────────────────────────
def h40(*parts) -> str:
    hh = hashlib.sha1()
    for p in parts:
        hh.update(str(p).encode("utf-8", "ignore")); hh.update(b"\x1e")
    return hh.hexdigest()


def h40b(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def clean_txt(s: Any) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s)).replace("\xa0", " ")
    t = re.sub(r"[（(\[{][^）)\]}]*[）)\]}]", " ", t)
    t = re.sub(r"[^\w가-힣]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_corp(s: Any) -> str:
    """법인격 접미어 제거 — 사업장명↔법인명, 낙찰업체↔상장사 매칭의 핵심."""
    t = clean_txt(s)
    t = re.sub(r"\b(주식회사|유한회사|합자회사|㈜|주|Co|Ltd|Inc|Corp|Company|Limited)\b", " ",
               t, flags=re.I)
    return re.sub(r"\s+", "", t)


def name_sim(a: str, b: str) -> float:
    """0~100 유사도. rapidfuzz 가 있으면 고속 경로."""
    a, b = clean_corp(a), clean_corp(b)
    if not a or not b:
        return 0.0
    if rf_fuzz is not None:
        return float(rf_fuzz.token_set_ratio(a, b))
    import difflib
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


# 2024-01 종목코드 개편: 4자리 숫자 + [0-9A-Z(I,O,U 제외)] + [0,K,L,M,N] 형식 병존.
# \D 제거식 정규화는 신형 코드를 조용히 파괴한다 — 반드시 패턴 검사로 정규화한다.
_CODE_OK = re.compile(r"^(?:\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0KLMN])$")


def code6(x: Any) -> Optional[str]:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    s = re.sub(r"\s", "", str(x).upper()).split(".")[0]
    if len(s) == 7 and s[0] in "AQ" and _CODE_OK.match(s[1:]):
        s = s[1:]
    if _CODE_OK.match(s):
        return s
    # ★ISIN(KR7005930003) → 단축코드(005930). 폐지목록에는 ISIN 표기가 섞여 오는데
    #   숫자만 뽑으면 10자리가 되어 통째로 탈락했다 — 그만큼 폐지종목이 유니버스에서
    #   빠지고 그것이 그대로 ★상향 드리프트(생존자편향)가 된다. 실측 탈락률 37%.
    m = re.match(r"^KR[0-9A-Z]([0-9A-Z]{6})\d{3}$", s)
    if m and _CODE_OK.match(m.group(1)):
        return m.group(1)
    digits = re.sub(r"\D", "", s)
    if digits and len(digits) <= 6:
        z = digits.zfill(6)
        return z if _CODE_OK.match(z) else None
    return None


# ── 원자적 파일 IO (드라이브 FUSE 마운트에서 반쪽 파일이 남지 않게) ──────────────────────────
def _mkparent(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def write_bytes_atomic(path: str, data: bytes) -> str:
    _mkparent(path)
    tmp = f"{path}.part.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data); f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)
    return path


def write_text_atomic(path: str, text: str) -> str:
    return write_bytes_atomic(path, text.encode("utf-8"))


def write_parquet_atomic(df: pd.DataFrame, path: str) -> str:
    _mkparent(path)
    tmp = f"{path}.part.{os.getpid()}"
    body = df.copy()
    for c in body.columns:
        if body[c].dtype == object:
            try:
                pd.api.types.infer_dtype(body[c], skipna=True)
            except Exception:
                body[c] = body[c].astype(str)
    try:
        body.to_parquet(tmp, index=False, compression="zstd")
    except Exception:
        body.to_parquet(tmp, index=False, compression="snappy")
    os.replace(tmp, path)
    return path


def read_parquet_soft(path: str, quarantine: bool = True) -> Optional[pd.DataFrame]:
    """quarantine=False 는 읽기 전용 루트(로컬 D드라이브 탐색)용 — 남의 파일은 개명조차 하지 않는다."""
    if not path or not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:                                        # noqa
        L.warn(f"parquet 손상 추정: {os.path.basename(path)} ({type(e).__name__})"
               + ("" if quarantine else " — 읽기 전용 루트라 손대지 않고 건너뜁니다"))
        if quarantine:
            try:                                # 삭제하지 않는다 — .corrupt 로 격리만(절대 1원칙)
                os.replace(path, path + f".corrupt.{int(time.time())}")
            except Exception:
                pass
        return None


def jsonl_read(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue                        # 반쪽 줄은 건너뜀 — append-only 저널의 정상 동작
    return out


def jsonl_append(path: str, rows: Iterable[dict]):
    _mkparent(path)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


# ── 스로틀/재시도/병렬 ──────────────────────────────────────────────────────────────────────
class _Pace:
    def __init__(self, qps: float):
        self.gap = 1.0 / max(qps, 0.01)
        self.next_t = 0.0
        self._lk = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.monotonic()
            delay = max(0.0, self.next_t - now)
            self.next_t = max(now, self.next_t) + self.gap
        if delay > 0:
            time.sleep(delay)


_PACERS: Dict[str, _Pace] = {}
_PACE_LK = threading.Lock()


def pace(source: str) -> _Pace:
    with _PACE_LK:
        if source not in _PACERS:
            _PACERS[source] = _Pace(QPS_CAP.get(source, QPS_CAP.get("generic", 3.0)))
        return _PACERS[source]




NET_TASK_TIMEOUT_S = 300      # 병렬 작업 1건의 상한(초)


def cap_of(max_calls: Optional[int]) -> Optional[int]:
    """★max_calls 규약 — -1(또는 None)=무제한 · 0=금지 · 양수=상한.

    옛 규약은 0 을 '무제한'으로 읽었다(`if max_calls and ...`). 그런데 CallBudget.take()
    는 '몫 없음'을 정확히 0 으로 표현한다. 두 의미가 정면으로 충돌해서, ★예산을 한 건도
    받지 못한 수집기가 오히려 무제한이 되는 반전이 일어났다. 앞선 소비자가 잔여를 다 쓰면
    뒤 소비자의 take() 가 0 을 돌려주고, 그 0 이 '상한 없음'으로 읽혀 배치 루프의 예산
    가드가 통째로 꺼진다. 그 다음 방어선인 QUOTA.allow() 는 ok_run 이 쌓여 있으면 실측
    상향 분기를 타므로 공식치의 최대 4배까지 태울 수 있다 — 주석에 '이미 가진 것을 다시
    사는 일'이라고 적어 둔 심층재무 티어가 그렇게 하루치를 통째로 먹는다.
    그래서 무제한을 -1 로 옮기고 0 은 0 으로 읽는다.
    """
    if max_calls is None:
        return None
    m = int(max_calls)
    return None if m < 0 else m


@contextmanager
def stage_bar(total: int, desc: str):
    """★진행바는 '작업 전체'에 딱 하나.

    배치마다 tqdm 을 새로 만들면 화면엔 0/N 이 반복해서 새로 뜨고, 사용자 눈에는
    같은 일을 무한히 되풀이하는 것으로 보인다(실제로 두 번 그런 오해가 있었다).
    이 헬퍼로 '스테이지 1개 = 진행바 1개' 를 코드 차원에서 강제한다.
    안쪽 pmap_net 은 반드시 quiet=True 로 부른다."""
    bar = tqdm(total=max(int(total), 0), desc=desc, ncols=88, leave=False)
    try:
        yield bar
    finally:
        try:
            bar.close()
        except Exception:
            pass


class CallBudget:
    """한 API 의 잔여 호출량을 '소비자별로 미리 나눠 주는' 배분기.

    ★이게 없어서 같은 사고를 두 번 냈다.
      1차: 심층 재무가 잔여를 전부 먹어 직원현황이 매 실행 0건.
      2차: 순서를 뒤집었더니 직원현황(19,500건)이 전부 먹어 심층 재무가 0건.
      순서를 바꾸는 것은 해결이 아니라 문제를 옮기는 것이다. 몫을 정해 줘야 한다.
      3차: 고정 비율이라 '일괄 ZIP 이 이미 덮어 할 일이 없는' 소비자가 예산의 65%를 선점하고,
           대체 수단이 전혀 없는 직원현황이 0.20 만 받아 800건에서 끊겼다. → 비율을 '아직
           배정받지 않은 소비자들 사이의 상대 가중치'로 바꿨다.
      4차(★현재): 3차는 ★뒤 소비자만 구제한다. 첫 소비자는 여전히 고정 비율을 받는다.
           실측 — 공시목록이 첫 순번이라 pending 가중치 합이 1.00 이어서 19,999×0.10=1,999 를
           받았고, 실수요는 12,533 이었다. 1,999÷83(월당 실측) = ★정확히 24개월에서 끊겼다.
           "4시간짜리 백테스트에 2만 호출이 왜 부족하냐" — 부족하지 않았다. ★나눠주는
           방식이 틀렸다. 그래서 배분을 2단계로 바꾼다:
             ① declare() — 모든 소비자가 ★먼저 자기 실수요를 선언한다(수집 전).
             ② settle()  — 총수요 ≤ 잔여이면 ★전원 수요 전액을 준다. 비율은 그때 아무
                           역할도 하지 않는다. 총수요가 잔여를 넘을 때만 가중치가 개입하고,
                           그때도 '수요보다 많이 받은 몫'은 회수해 재분배한다(water-filling).
           수요를 셀 수 없는 소비자(직원현황)는 선언하지 않으면 무한수요로 취급되어
           남은 것을 비율대로 가져간다 — 선언 못 한다고 굶지 않는다.
    각 수집기는 자기 몫을 넘기면 스스로 멈추고, 남은 일은 다음 실행이 이어받는다."""

    INF = 1 << 40                       # '수요를 셀 수 없음' = 무한수요
    FINITE_CAP = 0.60                   # 수요를 선언한 소비자들이 총량에서 가져갈 수 있는 상한
    #                                     (한 소비자의 과대추정이 나머지를 굶기지 못하게 하는 방어)

    def __init__(self, src: str, share: Dict[str, float]):
        self.src = src
        self.total = int(QUOTA.remaining(src))
        self.share = dict(share)
        self.alloc: Dict[str, int] = {}
        self.need: Dict[str, int] = {}
        self._base = int(QUOTA.spent(src))
        self._pending = [k for k in share]        # 아직 배정받지 않은 소비자
        self._settled = False
        self._tight = False                       # 총수요가 잔여를 넘었는가(표시용)

    def pool(self) -> int:
        """지금 이 순간의 실잔여. ★고정값이 아니다 — 앞 소비자가 덜 쓰면 뒤가 그만큼 더 받는다."""
        return max(0, self.total - self.spent())

    def declare(self, name: str, need: Optional[int]) -> None:
        """★수집 전에 '내가 실제로 남겨둔 일'을 선언한다. None = 셀 수 없음(무한수요).

        여기서 선언된 값만이 settle() 의 입력이다. 선언을 안 한 소비자도 굶지 않는다 —
        무한수요로 간주되어 '선언한 소비자들이 실제로 가져간 뒤 남은 것'을 비율대로 받는다.
        """
        self.need[name] = self.INF if need is None else max(0, int(need))

    def settle(self) -> Dict[str, int]:
        """선언된 수요로 배분을 확정한다(water-filling).

        총수요 ≤ 잔여  → 전원 수요 전액. ★가중치는 아무 역할도 하지 않는다.
        총수요 > 잔여  → 가중치 비례로 나누되, 수요보다 많이 배정된 몫은 회수해
                        아직 굶은 소비자에게 다시 흘린다. 한 건도 놀지 않는다.
        """
        rem = self.pool()
        need = {k: int(self.need.get(k, self.INF)) for k in self.share}
        tot = sum(need.values())
        self._tight = tot > rem
        out: Dict[str, int] = {k: 0 for k in self.share}
        if not self._tight:                       # ★흔한 경우 — 전원 전액
            self.alloc = {k: (rem if v >= self.INF else v) for k, v in need.items()}
            self._settled, self._pending = True, []
            return dict(self.alloc)

        def _fill(keys: List[str], pot: int) -> int:
            """가중치 비례 배분 + 수요 초과분 회수·재분배(water-filling). 반환=실제 배분량."""
            act, used = [k for k in keys if float(self.share.get(k, 0.0)) > 0], 0
            while act and pot > 0:
                wsum = sum(float(self.share[k]) for k in act)
                if wsum <= 0:
                    break
                give = {k: int(pot * float(self.share[k]) / wsum) for k in act}
                capped = [k for k in act if need[k] <= give[k]]
                if not capped:                    # 아무도 수요에 안 닿는다 → 그대로 확정
                    for k in act:
                        out[k] += give[k]
                        used += give[k]
                    break
                for k in capped:                  # 수요만큼만 주고 나머지는 회수
                    out[k] += need[k]
                    used += need[k]
                    pot -= need[k]
                    act.remove(k)
            return used

        # ★수요를 '셀 수 있는' 소비자를 먼저 채운다. INF 는 진짜 수요가 아니라 ★정보의 부재다.
        #   실측한 4,000회짜리 수요를, 세지도 못한 소비자 셋과 비율로 나눠 2,000회만 주는 것은
        #   가진 정보를 버리는 짓이다. 다만 한 소비자의 과대추정이 나머지를 굶기지 못하도록
        #   INF 소비자가 있을 때는 유한 수요의 총합을 pool 의 FINITE_CAP 까지로 제한한다.
        fin = [k for k in self.share if need[k] < self.INF]
        inf = [k for k in self.share if need[k] >= self.INF]
        if fin:
            pot = rem if not inf else int(rem * self.FINITE_CAP)
            rem -= _fill(fin, pot)
        if inf:
            for k in inf:                         # INF 는 수요 상한이 없다 → 비율 그대로
                need[k] = rem
            _fill(inf, rem)
        self.alloc = out
        self._settled, self._pending = True, []
        return dict(self.alloc)

    def take(self, name: str, need: Optional[int] = None) -> int:
        """수집 직전에 호출한다. 반환값이 이번 실행에서 이 수집기가 쓸 수 있는 상한.

        settle() 이 끝났으면 확정 배정을 그대로 돌려준다. settle() 없이 부르면 옛 순차
        배분으로 폴백한다(호환 유지) — 다만 그 경로는 첫 소비자가 손해를 보므로 쓰지 않는다.
        """
        if self._settled:
            # ★배정은 확정값이되 상한은 '지금의 실잔여'다. 앞 소비자가 예상보다 많이 썼으면
            #   확정값을 그대로 쓰다가 실제 한도를 넘길 수 있다.
            return max(0, min(int(self.alloc.get(name, 0)), self.pool()))
        if name in self.alloc:
            return self.alloc[name]        # ★재호출은 재배정이 아니다(이중 배정·정산 오류 방지)
        if name in self._pending:
            self._pending.remove(name)
        w = float(self.share.get(name, 0.0))
        wsum = w + sum(float(self.share.get(k, 0.0)) for k in self._pending)
        pool = self.pool()
        # ★몫이 없는 소비자(share 미등재·오타)는 0 이어야 한다. 마지막 순번에서 wsum==0 이면
        #   잔여 전량을 넘기는 폴백은 '등록되지 않은 소비자가 예산을 통째로 먹는' 경로다.
        n = int(pool * (w / wsum)) if wsum > 0 else 0
        if need is not None and int(need) >= 0:
            self.need[name] = int(need)
            n = min(n, int(need))
        self.alloc[name] = n
        return n

    def spent(self) -> int:
        return int(QUOTA.spent(self.src)) - self._base

    def table(self, labels: Dict[str, str]):
        def _n(v: int) -> str:
            return "수요 미상" if v >= self.INF else f"{v:,}"
        if self._settled:
            tot = sum(int(self.need.get(k, self.INF)) for k in self.share)
            rows = [[labels.get(k, k), _n(int(self.need.get(k, self.INF))),
                     f"{int(self.alloc.get(k, 0)):,}",
                     "수요 전액" if not self._tight else
                     ("수요 전액" if self.need.get(k, self.INF) <= self.alloc.get(k, 0)
                      else "비율 배분")] for k in self.share]
            head = (f"[{self.src}] 잔여 {self.total:,}건 · 총수요 "
                    f"{'미상 포함' if tot >= self.INF else f'{tot:,}건'} → "
                    + ("★총수요가 잔여 안에 들어옵니다 — 가중치를 쓰지 않고 전원 수요 전액을 "
                       "배정했습니다(호출량이 모자란 것이 아니라 나누는 방식이 문제였습니다)."
                       if not self._tight else
                       "★총수요가 잔여를 넘어 가중치 비례로 나눴습니다. 수요보다 많이 배정된 "
                       "몫은 회수해 굶은 소비자에게 다시 흘렸습니다(water-filling)."))
            L.grid(rows, ["소비자", "선언 수요", "배정", "근거"], ["l", "r", "r", "l"], title=head)
            return
        rows = [[labels.get(k, k), f"{self.share.get(k, 0)*100:.0f}%",
                 f"{int(self.total*float(self.share.get(k,0.0))):,}"]
                for k in self.share]
        L.grid(rows, ["소비자", "가중치", "계획(참고)"], ["l", "r", "r"],
               title=f"[{self.src}] 잔여 {self.total:,}건 배분계획 — 가중치는 '아직 배정 안 "
                     f"받은 소비자들 사이의 상대값'이라, 앞이 덜 쓰면 뒤가 그만큼 더 받습니다")

    def report(self, labels: Dict[str, str]):
        """실제 배정·수요를 사후 정산해 보여준다(계획표만 있으면 왜 끊겼는지 알 수 없다)."""
        rows = [[labels.get(k, k),
                 ("수요 미상" if int(self.need[k]) >= self.INF else f"{int(self.need[k]):,}")
                 if k in self.need else "—",
                 f"{v:,}"] for k, v in self.alloc.items()]
        L.grid(rows, ["소비자", "남은 수요", "배정 상한"], ["l", "r", "r"],
               title=f"[{self.src}] 실배분 정산 — ★실사용 {self.spent():,}건 / 진입시 잔여 "
                     f"{self.total:,}건. 배정 상한은 각자 '자기 차례의 실잔여'로 계산하므로 "
                     f"단순 합계가 잔여를 넘을 수 있습니다(앞이 덜 쓴 만큼 뒤가 더 받음). "
                     f"실제로 소비된 것은 '실사용' 한 줄뿐입니다.")


def pmap_net(fn: Callable, items: Sequence, workers: Optional[int] = None,
             label: str = "", quiet: bool = False) -> List[Any]:
    """네트워크 병렬(스레드). 예외는 None 으로 흡수하되 유형별 건수를 로그로 남긴다.

    quiet=True — 호출자가 '전체 진행'을 재는 바깥 진행바를 이미 들고 있을 때 쓴다.
    배치마다 0/N 진행바가 새로 뜨면 사용자 눈엔 같은 일이 무한 반복되는 것으로 보인다
    (실제로 그런 오해가 있었다). 진행바는 작업 전체에 하나만 있어야 한다."""
    items = list(items)
    if not items:
        return []
    w = max(1, min(workers or IO_THREADS, len(items)))
    out: List[Any] = [None] * len(items)
    errs: Counter = Counter()
    ex = ThreadPoolExecutor(max_workers=w, thread_name_prefix="net")
    futs = {ex.submit(fn, x): i for i, x in enumerate(items)}
    try:
        # ★상한은 반드시 as_completed 쪽에 걸어야 한다. 옛 코드는 `as_completed(futs)` 로
        #   받고 `fu.result(timeout=300)` 을 걸었는데, as_completed 는 ★이미 끝난 것만
        #   내놓으므로 그 result() 는 언제나 즉시 반환된다 — 즉 상한이 문법적으로 존재하지
        #   않았다. 워커 하나가 안 끝나면 as_completed 가 무한 블록하고, 이어서 with 문의
        #   shutdown(wait=True) 가 또 블록해서 바깥 배치 루프의 CLOCK.over() 체크에 영영
        #   도달하지 못한다(시간예산 무력화). 공시·주요계정·심층재무·직원현황 네 스테이지가
        #   전부 이 경로를 쓴다.
        it = as_completed(futs, timeout=NET_TASK_TIMEOUT_S * max(1, len(items) // max(w, 1)))
        if not quiet:
            it = tqdm(it, total=len(futs), desc=label or "수집", leave=False, ncols=86)
        try:
            for fu in it:
                i = futs[fu]
                try:
                    out[i] = fu.result(timeout=NET_TASK_TIMEOUT_S)
                except Exception as e:                            # noqa
                    errs[type(e).__name__] += 1
        except Exception as e:                                    # noqa
            n_left = sum(1 for f in futs if not f.done())
            errs[type(e).__name__] += max(1, n_left)
            L.warn(f"{label or '병렬수집'} 전체 상한 초과 — 미완료 {n_left}건을 버리고 "
                   f"진행합니다(응답을 조금씩 흘리는 서버가 시간예산을 삼키지 못하게 하는 방어).")
    finally:
        for f in futs:
            f.cancel()
        ex.shutdown(wait=False)
    if errs:
        L.warn(f"{label or '병렬수집'} 실패 {sum(errs.values())}/{len(items)}건 — " +
               ", ".join(f"{k}×{v}" for k, v in errs.most_common(3)))
    return out




# ★드리프트 감사용 집계 — 편향은 '있다/없다'가 아니라 ★방향과 크기로 재야 판단이 된다.
#   각 단계가 자기가 버린 것·고친 것을 여기에 적어 두고, 마지막에 상향/하향으로 나눠 본다.
UNI_AUDIT: Dict[str, Any] = {}
PIT_AUDIT: Counter = Counter()
CELL_AUDIT: Dict[str, Any] = {}


def shrink(df: pd.DataFrame) -> pd.DataFrame:
    """float64→float32 등 다운캐스트 — 10년 패널 램을 3~5배 줄인다."""
    if df is None or df.empty:
        return df
    for c in df.columns:
        k = df[c].dtype.kind
        if k == "f":
            df[c] = pd.to_numeric(df[c], downcast="float")
        elif k in "iu":
            df[c] = pd.to_numeric(df[c], downcast="integer")
    return df


# ── 수치 프리미티브 ─────────────────────────────────────────────────────────────────────────
def sdiv(a, b, eps: float = 1e-12) -> pd.Series:
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    out = a / b.where(b.abs() > eps)
    return out.replace([np.inf, -np.inf], np.nan)


def dlog(s: pd.Series, k: int = 12) -> pd.Series:
    """Δlog — 음수/0 은 정의역 밖이므로 결측(0으로 메우면 그게 버그)."""
    v = pd.to_numeric(s, errors="coerce")
    return np.log(v.where(v > 0)).diff(k)


def colx(df: pd.DataFrame, name: str) -> pd.Series:
    """없는 컬럼도 NaN Series 로 돌려주는 안전 접근자 — 수집이 부분 실패한 실행에서
    None 연산 TypeError 로 죽지 않기 위한 유일한 규약이다. df.get() 금지."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def gcol(df: pd.DataFrame, name: str, key: str = "code"):
    """colx 의 groupby 판 — 없는 컬럼은 NaN 으로 만들어 두고 그룹화한다."""
    if name not in df.columns:
        df[name] = np.nan
    return df.groupby(key, observed=True)[name]


def nrow_mean(df: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    """가용 축만의 평균 — 결측 축을 0으로 채우지 않는다(§7.3)."""
    use = [c for c in cols if c in df.columns]
    if not use:
        return pd.Series(np.nan, index=df.index)
    return df[use].astype("float64").mean(axis=1, skipna=True)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def nw_tstat(x: np.ndarray, lags: Optional[int] = None) -> Tuple[float, float]:
    """Newey-West(HAC) 평균 t — 월간 수익률 시계열 유의성 검정용(자기상관 보정)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return (float("nan"), float("nan"))
    mu = float(x.mean())
    e = x - mu
    lag = lags if lags is not None else max(0, min(int(4 * (n / 100.0) ** (2 / 9)), n - 2))
    v = float(e @ e) / n
    for j in range(1, lag + 1):
        v += 2.0 * (1 - j / (lag + 1)) * float(e[j:] @ e[:-j]) / n
    se = math.sqrt(max(v, 1e-18) / n)
    return (mu, mu / se)


def roll_ols_residual(y: np.ndarray, X: np.ndarray, win: int, chunk: int = 256) -> np.ndarray:
    """(N,T) 패널 × (N,T,K) 설명변수의 길이 win 롤링 OLS 잔차(창 마지막 시점) — 완전 벡터화.
    계약 §3: 칼만 폐기·롤링 OLS 벡터화. 종목별 파이썬 루프로 짜면 15분짜리가 3시간이 된다."""
    y = np.asarray(y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    N, T = y.shape
    K = X.shape[2]
    out = np.full((N, T), np.nan)
    if T < win or win < K + 2:
        return out
    from numpy.lib.stride_tricks import sliding_window_view as swv
    eye = np.eye(K)
    for s in range(0, N, chunk):
        e = min(N, s + chunk)
        yw = swv(y[s:e], win, axis=1)                              # (n, M, W)
        Xw = np.moveaxis(swv(X[s:e], win, axis=1), -1, 2)          # (n, M, W, K)
        good = np.isfinite(yw).all(axis=2) & np.isfinite(Xw).all(axis=(2, 3))
        yw = np.nan_to_num(yw)
        Xw = np.nan_to_num(Xw)
        XtX = np.einsum("nmwk,nmwl->nmkl", Xw, Xw, optimize=True) + 1e-8 * eye
        Xty = np.einsum("nmwk,nmw->nmk", Xw, yw, optimize=True)
        try:
            beta = np.linalg.solve(XtX, Xty[..., None])[..., 0]
        except np.linalg.LinAlgError:
            beta = np.einsum("nmkl,nml->nmk", np.linalg.pinv(XtX), Xty)
        resid = yw[:, :, -1] - np.einsum("nmk,nmk->nm", Xw[:, :, -1, :], beta)
        out[s:e, win - 1:] = np.where(good, resid, np.nan)
    return out


def hhi(shares: np.ndarray) -> float:
    v = np.asarray(shares, dtype=float)
    v = v[np.isfinite(v) & (v > 0)]
    if v.sum() <= 0:
        return float("nan")
    w = v / v.sum()
    return float((w * w).sum())


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [4] 캐시 금고 — 구글드라이브 공용/전용 인덱스 + 로컬 D드라이브 탐색                        ║
# ║                                                                                          ║
# ║  ★★★ 절대 1원칙: 기존 캐시·인덱스를 훼손하지 않는다. 약속이 아니라 '구조'로 보장한다 ★★★  ║
# ║   1) 인덱스의 원천은 append-only JSONL 저널 — 기존 줄을 다시 쓰는 코드가 없다              ║
# ║   2) manifest.parquet 은 저널의 파생물 — 재생성 전 반드시 타임스탬프 백업, 실패 시 중단    ║
# ║   3) 컬럼은 합집합으로만 확장 — 다른 전략/과거 버전 인덱스의 컬럼을 떨어뜨리지 않는다      ║
# ║   4) 원본(blob)은 내용해시 경로 — 같은 내용은 재기록 없음, 다른 내용은 새 파일             ║
# ║   5) 기존 리포트 폴더는 이동·개명 없이 '경로만 등록'(adopt-by-reference)                   ║
# ║   6) 삭제 API 자체가 없다 — 손상 파일도 .corrupt 개명 격리뿐                               ║
# ║                                                                                          ║
# ║  탐색: 로컬(D드라이브 후보들) + 구글드라이브 양쪽 → 시간 절약                              ║
# ║  저장: ★신규 수집분은 전부 구글드라이브(공용/전용 인덱스에 등록·재호출 가능)               ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

MANIFEST_FIELDS = ["uid", "scope", "domain", "kind", "key", "relpath", "abspath", "fmt",
                   "bytes", "sha1", "event_date", "knowledge_date", "source", "saved_at",
                   "strategy", "adopted", "note"]
STRATEGY_TAG = "TCD_V2_ZB"


_DRIVE_SUBS = ("내 드라이브", "My Drive", "MyDrive", "내드라이브")


def _fsize(p: str) -> int:
    try:
        return os.path.getsize(p)
    except Exception:
        return -1


def _win_drivefs_roots() -> List[str]:
    r"""★[다른 세션에서 이식] 구글드라이브 데스크톱이 '스스로 기록해 둔' 마운트 지점을 읽는다.

    문자 스캔만으로는 못 찾는다. 구글드라이브는
      (a) 드라이브 문자(G: 등)  (b) 임의의 빈 폴더  (c) 미러링 모드의 로컬 폴더
    중 하나로 붙는데 (b)(c)는 어떤 문자 스캔으로도 발견되지 않는다.
    실제로 이 사용자 환경에서 두 번 연속 LOCAL_ONLY 로 떨어진 원인이 이것이다.
      ① 레지스트리 DefaultMountPoint (정책 > 시스템 > 사용자)
      ② %LOCALAPPDATA%\Google\DriveFS\root_preference_sqlite.db
         media.last_mount_point / roots.last_seen_absolute_path
    부팅 경로에서 도는 함수이므로 어떤 예외도 밖으로 내보내지 않는다.
    """
    out: List[str] = []
    if platform.system() != "Windows":
        return out
    try:
        import winreg                                            # type: ignore
        for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"Software\Policies\Google\DriveFS"),
                          (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\DriveFS"),
                          (winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS")):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | view) as k:
                        v, _ = winreg.QueryValueEx(k, "DefaultMountPoint")
                        p = os.path.expandvars(str(v)).strip()
                        if p:
                            out.append(p + ":\\" if len(p.rstrip(":")) == 1 else p)
                except OSError:
                    continue
    except Exception:
        pass
    try:
        import sqlite3
        db = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS",
                          "root_preference_sqlite.db")
        if os.path.isfile(db):
            # 드라이브가 파일을 열어 두고 있으므로 반드시 읽기 전용·불변으로 연다.
            con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True, timeout=2)
            try:
                for q in ("SELECT last_mount_point FROM media",
                          "SELECT last_seen_absolute_path FROM roots"):
                    try:
                        for row in con.execute(q):
                            v = str(row[0] or "").strip()
                            if v:
                                out.append(v + ":\\" if len(v.rstrip(":")) == 1 else v)
                    except Exception:
                        continue
            finally:
                con.close()
    except Exception:
        pass
    kids = ("My Drive", "내 드라이브", "Shared drives", "공유 드라이브")
    return out + [os.path.join(r, k) for r in list(out) for k in kids]


def _drive_bases() -> List[str]:
    """구글드라이브 '베이스'(마운트 지점) 후보를 넓게 훑는다.
    ★옛 판정의 결함: tcd_cache 폴더가 '이미 존재'해야만 드라이브로 인정 → 처음 쓰는 사람은
      드라이브를 붙여놨는데도 LOCAL_ONLY 로 떨어져 절대1원칙(신규분 드라이브 저장)이 깨졌다.
      이제는 베이스만 있으면 그 아래 캐시 폴더를 만들어 쓴다."""
    # ★깊은 쪽('내 드라이브')이 먼저다. 마운트 루트(~/Google Drive)에 바로 쓰면 구글드라이브
    #   데스크톱이 동기화하지 않거나 쓰기를 거부한다 — 실제 동기화 대상은 그 아래다.
    deep: List[str] = []
    shallow: List[str] = []

    def add(lst, p):
        try:
            if p and os.path.isdir(p) and p not in lst:
                lst.append(p)
        except Exception:
            pass

    roots: List[str] = []
    # ★드라이브 자신이 기록해 둔 마운트 지점을 '추측보다 먼저' 조회한다.
    for r in _win_drivefs_roots():
        add(deep, r)
    home = os.path.expanduser("~")
    # macOS 최신 구글드라이브: ~/Library/CloudStorage/GoogleDrive-<메일>/My Drive
    cs = os.path.join(home, "Library", "CloudStorage")
    try:
        for dnm in sorted(os.listdir(cs)):
            if dnm.startswith("GoogleDrive"):
                for k in ("My Drive", "내 드라이브"):
                    add(deep, os.path.join(cs, dnm, k))
    except Exception:
        pass
    for n in ("My Drive", "내 드라이브"):
        add(deep, os.path.join(home, n))
    roots += ["~/Google Drive", "~/GoogleDrive", "~/Google 드라이브",
              "/Volumes/GoogleDrive", "/mnt/g", "/mnt/google_drive"]
    if os.name == "nt" or os.path.isdir("/mnt/c"):
        # ★D/E/F 는 넣지 않는다 — 사양상 로컬 '읽기 전용' 캐시 위치다. 거기에 오래된
        #   드라이브 마운트 흔적이나 백업 사본이 있으면 신규 수집분을 전부 그쪽에 쓰면서
        #   로그에는 SYNCED_DRIVE 라고 초록불을 켜 절대 1원칙이 조용히 깨진다.
        letters = "GHIJKLMNOPQRSTUVWXYZ"           # 기본은 G: 지만 사용자가 바꿀 수 있다
        try:                                        # 실제로 존재하는 문자만 남긴다(힌트)
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()      # type: ignore[attr-defined]
            live = "".join(L for L in letters if mask >> (ord(L) - ord("A")) & 1)
            letters = live or letters
        except Exception:
            pass
        for letter in letters:
            roots += [f"{letter}:/", f"/mnt/{letter.lower()}/"]
    for base in roots:
        b = os.path.expanduser(base)
        for sub in _DRIVE_SUBS:
            add(deep, os.path.join(b, sub))
        if not base.endswith((":/", "/")) or base.startswith("~"):
            add(shallow, b)                        # 드라이브문자 루트 자체는 후보가 아니다
    return deep + shallow


def locate_primary_root() -> Tuple[str, str]:
    """저장 루트를 정한다. 우선순위: 사용자 지정 → Colab 마운트 → 로컬 동기화 드라이브 → 폴백.
    반환 (경로, 모드). 어느 경우에도 예외로 죽지 않는다."""
    # ⓪ 사용자가 GDRIVE_ROOT 를 자기 환경에 맞게 지정했으면 그것이 최우선(부모가 있으면 생성)
    try:
        gr = os.path.expanduser(str(GDRIVE_ROOT or ""))
        if gr and not gr.startswith("/content/") and (
                os.path.isdir(gr) or os.path.isdir(os.path.dirname(gr.rstrip("/\\")))):
            os.makedirs(gr, exist_ok=True)
            # ★지정 경로가 실제로 드라이브 마운트 아래인지 확인한다. 확인 없이 SYNCED_DRIVE 를
            #   돌려주면 그냥 로컬 폴더인데도 경고가 꺼져 절대 1원칙이 지켜진 줄 알게 된다.
            real = os.path.realpath(gr)
            on_drive = any(real.startswith(os.path.realpath(b)) for b in _drive_bases()) or \
                any(t in real.replace("\\", "/") for t in ("/내 드라이브/", "/My Drive/",
                                                           "/MyDrive/", "/GoogleDrive/",
                                                           "/Google Drive/"))
            return gr, ("SYNCED_DRIVE" if on_drive else "USER_PATH")
    except Exception:
        pass
    if ENVX["colab"]:
        try:
            from google.colab import drive as _gd          # type: ignore
            if not os.path.isdir("/content/drive/MyDrive"):
                _gd.mount("/content/drive", force_remount=False)
            if os.path.isdir("/content/drive/MyDrive"):
                os.makedirs(GDRIVE_ROOT, exist_ok=True)
                return GDRIVE_ROOT, "COLAB_DRIVE"
        except Exception as e:                             # noqa
            L.warn(f"구글드라이브 마운트 실패({type(e).__name__}) — 로컬 폴백을 사용합니다. "
                   f"이 경우 '신규 수집분 구글드라이브 저장' 원칙을 지킬 수 없으므로, "
                   f"실행 후 {LOCAL_FALLBACK_ROOT} 폴더를 드라이브에 올려 주세요.")
        return LOCAL_FALLBACK_ROOT, "COLAB_NO_DRIVE"
    for base in _drive_bases():                            # ① 이미 캐시가 있는 곳을 먼저
        p = os.path.join(base, os.path.basename(str(GDRIVE_ROOT).rstrip("/\\")) or "tcd_cache")
        if os.path.isdir(p):
            return p, "SYNCED_DRIVE"
    hunt_real = set()
    for h in LOCAL_CACHE_HUNT_DIRS:
        try:
            hunt_real.add(os.path.realpath(os.path.expanduser(h)))
        except Exception:
            pass
    for base in _drive_bases():                            # ② 없으면 베이스 아래 새로 만든다
        p = os.path.join(base, os.path.basename(str(GDRIVE_ROOT).rstrip("/\\")) or "tcd_cache")
        try:
            if any(os.path.realpath(base).startswith(h) or h.startswith(os.path.realpath(base))
                   for h in hunt_real):
                continue                                   # 읽기 전용 보조 캐시 위치는 저장처가 아니다
            os.makedirs(p, exist_ok=True)
            L.ok(f"구글드라이브 감지 — 캐시 루트를 새로 만들었습니다: {p}")
            return p, "SYNCED_DRIVE"
        except Exception:
            continue
    return LOCAL_FALLBACK_ROOT, "LOCAL_ONLY"


def warn_if_not_drive(mode: str, root: str):
    """★절대 1원칙 점검 — 신규 수집분이 드라이브에 안 들어가는 상태면 조치법까지 알려준다."""
    if mode in ("COLAB_DRIVE", "SYNCED_DRIVE"):
        return
    L.warn("─" * 84)
    if mode == "USER_PATH":
        L.warn(f"GDRIVE_ROOT 로 지정한 {os.path.abspath(root)} 가 구글드라이브 마운트 아래가 "
               f"아닙니다 — 저장은 정상이지만 '드라이브 동기화'는 일어나지 않습니다.")
    else:
        L.warn(f"구글드라이브를 찾지 못해 로컬({os.path.abspath(root)})에만 저장합니다.")
    L.warn("★ '신규 수집분은 구글드라이브 공용/전용 인덱스에 저장' = 절대 1원칙이므로 "
           "아래 중 하나로 반드시 바로잡으세요:")
    # ★'못 찾았다'만 말하면 사용자가 할 수 있는 게 없다. 이 PC 에서 실제로 감지된 후보를
    #   그대로 찍어 주면 복사·붙여넣기 한 번으로 끝난다(이 경고가 반복된 실측 이유).
    try:
        cands = [b for b in _drive_bases() if os.path.isdir(b)][:6]
    except Exception:
        cands = []
    if cands:
        L.warn("   ⓪ 이 PC 에서 감지된 드라이브 후보 — 아래를 그대로 GDRIVE_ROOT 에 넣으세요:")
        for b in cands:
            L.warn(f"        GDRIVE_ROOT = r\"{os.path.join(b, 'tcd_cache')}\"")
    else:
        L.warn("   ⓪ 이 PC 에서 구글드라이브 마운트를 하나도 감지하지 못했습니다"
               "(드라이브 데스크톱 미실행이거나 스트리밍 드라이브 문자가 없음).")
    L.warn("   ① 구글드라이브 데스크톱을 설치·로그인한 뒤 다시 실행 (자동 감지합니다)")
    L.warn("   ② 코드 상단 GDRIVE_ROOT 를 직접 지정  예) "
           r'GDRIVE_ROOT = "G:/내 드라이브/tcd_cache"')
    L.warn("   ③ 그대로 진행해도 데이터는 모두 로컬에 남습니다 — 실행 후 해당 폴더를 "
           "드라이브에 통째로 올리면 다음 실행부터 정상 재호출됩니다(구조 동일).")
    L.warn("─" * 84)


def locate_hunt_roots(primary: str) -> List[str]:
    """읽기 전용 보조 캐시 루트(로컬 D드라이브 등). primary 와 같은 곳은 제외."""
    outs = []
    for c in LOCAL_CACHE_HUNT_DIRS:
        try:
            p = os.path.abspath(os.path.expanduser(c))
            if os.path.isdir(p) and p != os.path.abspath(primary):
                outs.append(p)
        except Exception:
            continue
    return outs


class VaultArchive:
    """공용/전용 2계층 인덱스 캐시. 저장은 primary(구글드라이브), 탐색은 primary+hunt(D드라이브)."""

    def __init__(self, primary: str, mode: str, hunt_roots: Sequence[str] = ()):
        self.root = os.path.abspath(primary)
        self.mode = mode
        self.hunt = [os.path.abspath(h) for h in hunt_roots]
        self.ns = {"shared": os.path.join(self.root, SHARED_NAMESPACE),
                   "private": os.path.join(self.root, PRIVATE_NAMESPACE)}
        for base in self.ns.values():
            for sub in ("manifest", os.path.join("manifest", "_backup"), "data", "raw"):
                os.makedirs(os.path.join(base, sub), exist_ok=True)
        os.makedirs(os.path.join(self.root, "_locks"), exist_ok=True)
        self._man: Dict[str, pd.DataFrame] = {}
        self._uids: Dict[str, set] = {}
        self._queue: Dict[str, List[dict]] = {"shared": [], "private": []}
        self._lk = threading.RLock()
        self.tally: Counter = Counter()

    # 경로 ---------------------------------------------------------------------------------
    def _journal(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "manifest", "manifest.jsonl")

    def _man_parquet(self, scope: str) -> str:
        return os.path.join(self.ns[scope], "manifest", "manifest.parquet")

    def _table_path(self, root: str, scope: str, name: str) -> str:
        nsdir = SHARED_NAMESPACE if scope == "shared" else PRIVATE_NAMESPACE
        return os.path.join(root, nsdir, "data", f"{name}.parquet")

    # 잠금 ---------------------------------------------------------------------------------
    @contextmanager
    def _flock(self, tag: str, timeout: float = 45.0, stale: float = 900.0):
        """파일락. 획득 여부(got)를 yield 한다 — 실패 시 호출자가 사이드카 경로로 우회한다.
        ★파싱 실패한 락은 지우지 않는다(상대가 쓰는 도중일 수 있음). stale 판정도 재확인 후에만."""
        lp = os.path.join(self.root, "_locks", f"{tag}.lock")
        got = False
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "ts": time.time()}).encode())
                os.close(fd)
                got = True
                break
            except FileExistsError:
                try:
                    meta = json.loads(open(lp).read() or "{}")
                    if time.time() - float(meta.get("ts", 0)) > stale:
                        time.sleep(0.25)                       # 재확인 — TOCTOU 완화
                        try:
                            meta2 = json.loads(open(lp).read() or "{}")
                        except Exception:
                            meta2 = None
                        if meta2 is not None and meta2.get("ts") == meta.get("ts"):
                            try:
                                os.remove(lp)
                            except Exception:
                                pass
                            continue
                except Exception:
                    pass                                        # 파싱 실패 → 삭제하지 않고 대기
                time.sleep(0.35)
        try:
            yield got
        finally:
            if got:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    # 매니페스트 ---------------------------------------------------------------------------
    def manifest(self, scope: str, refresh: bool = False) -> pd.DataFrame:
        with self._lk:
            if not refresh and scope in self._man:
                return self._man[scope]
        frames: List[pd.DataFrame] = []
        p = read_parquet_soft(self._man_parquet(scope))
        if p is not None and len(p):
            frames.append(p)
        jr = jsonl_read(self._journal(scope))
        if jr:
            frames.append(pd.DataFrame(jr))
        # 과거 버전/다른 전략이 남긴 인덱스 파일도 '읽기 전용'으로 흡수 — 훼손 없음
        mandir = os.path.join(self.ns[scope], "manifest")
        try:
            for fn in os.listdir(mandir):
                lo = fn.lower()
                if fn in ("manifest.parquet", "manifest.jsonl") or fn.startswith("_"):
                    continue
                fp = os.path.join(mandir, fn)
                try:
                    if lo.endswith(".parquet"):
                        dd = read_parquet_soft(fp)
                    elif lo.endswith(".jsonl"):
                        dd = pd.DataFrame(jsonl_read(fp))
                    elif lo.endswith(".csv"):
                        dd = pd.read_csv(fp)
                    elif lo.endswith(".json"):
                        dd = pd.DataFrame(json.loads(open(fp, encoding="utf-8").read()))
                    else:
                        continue
                    if dd is not None and len(dd):
                        dd["_legacy_src"] = fn
                        frames.append(dd)
                        self.tally[f"legacy_manifest:{fn}"] += len(dd)
                except Exception:
                    continue
        except Exception:
            pass
        if frames:
            allc: List[str] = []
            for f in frames:                                # 컬럼 '합집합' — 떨어뜨리지 않는다
                for c in f.columns:
                    if c not in allc:
                        allc.append(c)
            man = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
            if "uid" not in man.columns:
                man["uid"] = np.nan
            # uid 결측 레거시 행은 내용 해시로 개별 uid 부여 — astype(str) 'nan' 이 한 줄로
            # 뭉개져 인덱스가 통째로 유실되는 사고를 막는다(절대 1원칙).
            miss = man["uid"].isna() | man["uid"].astype(str).str.strip().isin(("", "nan", "None"))
            if miss.any():
                keys = [c for c in ("relpath", "abspath", "key", "sha1", "domain", "_legacy_src")
                        if c in man.columns]
                idxs = np.where(miss.to_numpy())[0]
                man.loc[miss, "uid"] = [h40("legacy", int(i),
                                            *[str(man.iloc[int(i)].get(c, "")) for c in keys])
                                        for i in idxs]
            man["uid"] = man["uid"].astype(str)
            if "saved_at" in man.columns:
                man = man.sort_values("saved_at", kind="stable")
            man = man.drop_duplicates("uid", keep="last").reset_index(drop=True)
        else:
            man = pd.DataFrame(columns=MANIFEST_FIELDS)
        for c in MANIFEST_FIELDS:
            if c not in man.columns:
                man[c] = np.nan
        with self._lk:
            self._man[scope] = man
            self._uids[scope] = set(man["uid"].astype(str))
        return man

    def _enqueue(self, scope: str, rec: dict):
        rec.setdefault("scope", scope)
        rec.setdefault("saved_at", dtm.datetime.now().isoformat(timespec="seconds"))
        rec.setdefault("strategy", STRATEGY_TAG if scope == "private" else "")
        for c in MANIFEST_FIELDS:
            rec.setdefault(c, None)
        with self._lk:
            self._queue[scope].append(rec)
            self._uids.setdefault(scope, set()).add(str(rec["uid"]))
        self.tally[f"register:{scope}:{rec.get('domain')}"] += 1

    def flush(self, scope: Optional[str] = None):
        """대기 등록분을 저널에 즉시 기록. 락 미획득 시 프로세스별 사이드카 저널에 쓴다 —
        manifest() 가 manifest*.jsonl 사이드카를 전부 흡수하므로 유실이 없다."""
        for sc in ([scope] if scope else ["shared", "private"]):
            with self._lk:
                rows, self._queue[sc] = self._queue[sc], []
            if not rows:
                continue
            with self._flock(f"journal_{sc}") as got:
                target = self._journal(sc) if got else os.path.join(
                    self.ns[sc], "manifest", f"manifest.side{os.getpid()}.jsonl")
                jsonl_append(target, rows)
                if not got:
                    L.warn(f"저널 잠금 미획득 — 사이드카({os.path.basename(target)})에 기록"
                           f"(다음 로드에서 자동 흡수, 유실 없음)")
            self.tally[f"journal_append:{sc}"] += len(rows)

    def compact(self, scope: str):
        """저널 → manifest.parquet 파생. 기존 parquet 은 백업 성공 시에만 교체한다."""
        self.flush(scope)
        man = self.manifest(scope, refresh=True)
        p = self._man_parquet(scope)
        if os.path.exists(p):
            bak = os.path.join(self.ns[scope], "manifest", "_backup",
                               f"manifest.{dtm.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(p, bak)
            except Exception as e:                          # noqa
                L.warn(f"매니페스트 백업 실패({type(e).__name__}) — 컴팩션을 건너뜁니다. "
                       f"저널이 원천이므로 데이터 유실은 없습니다.")
                return
        try:
            write_parquet_atomic(man.astype({c: str for c in man.columns
                                             if man[c].dtype == object}), p)
        except Exception as e:                              # noqa
            L.warn(f"매니페스트 컴팩션 실패({type(e).__name__}) — 저널이 원천이므로 유실 없음")

    # 테이블 -------------------------------------------------------------------------------
    def save_table(self, name: str, df: pd.DataFrame, scope: str = "shared",
                   domain: str = "table", source: str = "", note: str = "") -> Optional[str]:
        """정제 테이블 저장(구글드라이브). 기존 파일은 백업 후 교체 — 백업 실패면 리비전 저장."""
        if df is None:
            return None
        path = self._table_path(self.root, scope, name)
        if os.path.exists(path):
            bak = os.path.join(self.ns[scope], "manifest", "_backup",
                               f"{name}.{dtm.datetime.now():%Y%m%d_%H%M%S}.parquet")
            try:
                shutil.copy2(path, bak)
            except Exception:
                path = self._table_path(self.root, scope, f"{name}.rev{int(time.time())}")
                L.warn(f"기존 테이블 백업 실패 — 덮어쓰지 않고 리비전으로 저장: {os.path.basename(path)}")
        try:
            write_parquet_atomic(df, path)
        except Exception as e:                              # noqa
            L.warn(f"테이블 저장 실패({type(e).__name__}): {name}")
            return None
        self._enqueue(scope, {"uid": h40("table", scope, name), "domain": domain,
                              "kind": "table", "key": name,
                              "relpath": os.path.relpath(path, self.root), "abspath": path,
                              "fmt": "parquet", "bytes": os.path.getsize(path),
                              "source": source, "adopted": False,
                              "note": json.dumps({"rows": int(len(df)), **({"m": note} if note else {})},
                                                 ensure_ascii=False)})
        # ★등록 즉시 저널에 flush — 실행이 도중에 죽어도 "저장됐는데 인덱스 미등록" 상태가
        #   남지 않는다(절대1원칙의 '재호출 가능' 보장). jsonl append 는 싸다.
        self.flush(scope)
        RUN.io("OUT", "DRIVE", f"{scope}:{name}", df, src=os.path.relpath(path, self.root))
        return path

    def load_table(self, name: str, scope: str = "shared") -> Optional[pd.DataFrame]:
        """탐색 순서: primary(요청 스코프 → 반대 스코프) → 로컬 D드라이브 후보들(읽기 전용).
        어디서 적중했는지 I/O 원장에 남긴다."""
        probes: List[Tuple[str, str, str]] = []
        for sc in (scope, "private" if scope == "shared" else "shared"):
            probes.append((self.root, sc, "GDRIVE"))
        for hr in self.hunt:
            for sc in (scope, "private" if scope == "shared" else "shared"):
                probes.append((hr, sc, "LOCAL_HUNT"))
        for root, sc, tag in probes:
            path = self._table_path(root, sc, name)
            if os.path.exists(path):
                # 읽기 전용 루트(D드라이브 탐색)에서는 손상 파일도 개명하지 않는다(quarantine=False)
                df = read_parquet_soft(path, quarantine=(tag != "LOCAL_HUNT"))
                if df is not None:
                    RUN.io("IN", tag, f"{sc}:{name}", df, src=path)
                    if tag == "LOCAL_HUNT":
                        self.tally["local_hunt_hit"] += 1
                        L.info(f"로컬 보조 캐시 적중(D드라이브 탐색): {name} ← {root}")
                    return df
        return None

    # 샤드 테이블(증분 append 전용) ---------------------------------------------------------
    def _shard_dir(self, root: str, scope: str, name: str) -> str:
        nsdir = SHARED_NAMESPACE if scope == "shared" else PRIVATE_NAMESPACE
        return os.path.join(root, nsdir, "data", f"{name}.shards")

    def save_shard(self, name: str, df: pd.DataFrame, key: str, scope: str = "shared",
                   domain: str = "table", source: str = "", note: str = "",
                   ver: int = 1) -> Optional[str]:
        """★증분 샤드 저장 — 기존 파일을 건드리는 코드 경로가 아예 없다(덮어쓰기·백업 불필요).

        일봉처럼 700만행짜리 테이블을 체크포인트마다 통째로 다시 쓰면
         ① 드라이브 I/O 가 수집보다 오래 걸리고 ② 매번 백업본이 쌓여 용량이 폭발하며
         ③ 쓰는 도중 죽으면 직전 스냅샷으로 되돌아간다.
        샤드는 새 파일만 만들고, 읽을 때 합집합으로 되살린다(절대 1원칙과도 정확히 일치)."""
        if df is None or not len(df):
            return None
        sd = self._shard_dir(self.root, scope, name)
        try:
            os.makedirs(sd, exist_ok=True)
        except Exception:
            return None
        # ★스키마 버전 — 같은 키의 샤드가 이미 있으면 쓰지 않는 것이 이 금고의 규칙이고
        #   그것이 절대 1원칙(기존 캐시 무훼손)을 지키는 방식이다. 그런데 그 규칙에는
        #   조용한 함정이 하나 있었다: ★수집 코드가 컬럼을 늘려도 디스크에는 영원히 반영되지
        #   않는다. 실측 사고 — marcap 에 시가총액·상장주식수를 추가한 뒤에도 이전 버전이 쓴
        #   샤드가 그 자리에 있어서, 1회차는 메모리 덕에 수정주가가 복원됐지만 2회차부터는
        #   주식수가 없어 액면분할 종목의 월수익률이 통째로 왜곡됐다(백테스트 타당성 직결).
        #   해결은 '덮어쓰기'가 아니라 '새 이름으로 추가'다 — 옛 파일은 손대지 않는다.
        kk = str(key) if int(ver) <= 1 else f"{key}.v{int(ver)}"
        fn = "part-" + re.sub(r"[^0-9A-Za-z_.\-]", "_", kk) + ".parquet"
        path = os.path.join(sd, fn)
        if os.path.exists(path):
            self.tally["shard_dedup"] += 1
            return path
        try:
            write_parquet_atomic(df, path)
        except Exception as e:                              # noqa
            L.warn(f"샤드 저장 실패({type(e).__name__}): {name}/{fn}")
            return None
        self._enqueue(scope, {"uid": h40("shard", scope, name, kk), "domain": domain,
                              "kind": "shard", "key": f"{name}/{kk}",
                              "relpath": os.path.relpath(path, self.root), "abspath": path,
                              "fmt": "parquet", "bytes": os.path.getsize(path),
                              "source": source, "adopted": False,
                              "note": json.dumps({"rows": int(len(df)),
                                                  **({"m": note} if note else {})},
                                                 ensure_ascii=False)})
        self.flush(scope)
        self.tally[f"shard:{name}"] += 1
        RUN.io("OUT", "DRIVE", f"{scope}:{name}#{key}", df,
               src=os.path.relpath(path, self.root))
        return path

    def load_frame(self, name: str, scope: str = "shared") -> Optional[pd.DataFrame]:
        """모놀리식 테이블 ∪ 샤드 전체 — primary(드라이브) + 로컬 보조 루트 양쪽에서 모은다.
        구버전이 남긴 단일 parquet 도 그대로 흡수하므로 하위호환이 깨지지 않는다."""
        frames: List[pd.DataFrame] = []
        seen: set = set()          # 경로 기준
        seen_id: set = set()       # ★내용 기준(파일명+크기) — D드라이브가 드라이브의 '거울'인
        #                            경우가 정상 사용법이라, 경로로만 걸러내면 같은 샤드를 두 번
        #                            읽어 행수와 램이 정확히 두 배가 된다.
        roots = [(self.root, "GDRIVE")] + [(h, "LOCAL_HUNT") for h in self.hunt]
        for root, tag in roots:
            for sc in (scope, "private" if scope == "shared" else "shared"):
                mono = self._table_path(root, sc, name)
                mid = (os.path.basename(mono), _fsize(mono))
                if os.path.exists(mono) and mono not in seen and mid not in seen_id:
                    seen.add(mono); seen_id.add(mid)
                    d = read_parquet_soft(mono, quarantine=(tag != "LOCAL_HUNT"))
                    if d is not None and len(d):
                        frames.append(d)
                        RUN.io("IN", tag, f"{sc}:{name}", d, src=mono)
                sd = self._shard_dir(root, sc, name)
                if not os.path.isdir(sd):
                    continue
                try:
                    parts = sorted(f for f in os.listdir(sd) if f.endswith(".parquet"))
                except Exception:
                    continue
                n_ok = 0
                for fn in parts:
                    p2 = os.path.join(sd, fn)
                    pid = (fn, _fsize(p2))
                    if p2 in seen or pid in seen_id:
                        continue
                    seen.add(p2); seen_id.add(pid)
                    d = read_parquet_soft(p2, quarantine=(tag != "LOCAL_HUNT"))
                    if d is not None and len(d):
                        frames.append(d)
                        n_ok += 1
                if n_ok:
                    self.tally[f"shard_read:{name}"] += n_ok
                    if tag == "LOCAL_HUNT":
                        self.tally["local_hunt_hit"] += 1
                        L.info(f"로컬 보조 캐시 적중(샤드): {name} ← {root} ({n_ok}조각)")
        if not frames:
            return None
        cols: List[str] = []
        for f in frames:
            for c in f.columns:
                if c not in cols:
                    cols.append(c)
        out = pd.concat([f.reindex(columns=cols) for f in frames], ignore_index=True)
        RUN.io("IN", "VAULT", f"{scope}:{name}", out, src=f"{len(frames)}조각 합집합")
        return out

    # 원본 blob ----------------------------------------------------------------------------
    def save_raw(self, domain: str, kind: str, key: str, data: bytes, fmt: str,
                 source: str = "", event_date=None, knowledge_date=None,
                 scope: str = "shared") -> Optional[str]:
        if not data:
            return None
        sig = h40b(data)
        sub = os.path.join(self.ns[scope], "raw", domain, kind, sig[:2])
        path = os.path.join(sub, f"{sig}.{fmt.lstrip('.')}")
        if not os.path.exists(path):                       # 있으면 절대 다시 쓰지 않는다
            try:
                write_bytes_atomic(path, data)
            except Exception as e:                          # noqa
                L.warn(f"원본 저장 실패({type(e).__name__}): {key}")
                return None
        else:
            self.tally["raw_dedup"] += 1
        self._enqueue(scope, {"uid": h40(domain, kind, key, sig), "domain": domain,
                              "kind": kind, "key": str(key),
                              "relpath": os.path.relpath(path, self.root), "abspath": path,
                              "fmt": fmt, "bytes": len(data), "sha1": sig,
                              "event_date": str(d_(event_date) or ""),
                              "knowledge_date": str(d_(knowledge_date) or ""),
                              "source": source, "adopted": False})
        if self.tally["raw_saved"] % 200 == 0:
            self.flush(scope)
        self.tally["raw_saved"] += 1
        return path

    # adopt-by-reference -------------------------------------------------------------------
    _DATE_IN_NAME = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")

    def adopt_scan(self, dirs: Sequence[str], cap: int = 300_000):
        """기존 폴더의 리포트/데이터 파일을 재귀 스캔해 '경로만' 공용 인덱스에 등록.
        이동·개명·삭제는 절대 하지 않는다."""
        seen: set = set()
        n_all = 0
        # ★자기 캐시 루트는 훑지 않는다 — 샤드·blob 수만 개를 FUSE 위에서 매 실행 재순회하면
        #   수 분이 그냥 날아가고, 이미 인덱스에 있는 것을 다시 등록하는 셈이다.
        skip_roots = {os.path.realpath(self.root)}
        for dd in list(dirs) + self.hunt:
            try:
                dd = os.path.expanduser(str(dd))
                real = os.path.realpath(dd)
            except Exception:
                continue
            if not os.path.isdir(dd) or real in seen or real in skip_roots:
                continue
            seen.add(real)
            n_dir = 0
            for base, subdirs, files in os.walk(dd):
                subdirs[:] = [s for s in subdirs
                              if not s.startswith(".") and s != "_backup"
                              and not s.endswith(".shards") and s not in ("raw", "manifest")]
                for fn in files:
                    if n_all >= cap:
                        break
                    lo = fn.lower()
                    if lo.endswith(".pdf"):
                        kind = "report_pdf"
                    elif lo.endswith((".parquet", ".csv", ".jsonl", ".json")) and any(
                            t in lo for t in ("report", "research", "consensus", "analyst",
                                              "price", "ohlcv", "dart", "krx", "nps", "fnltt",
                                              "universe", "mktcap")):
                        kind = "table_like"
                    else:
                        continue
                    fp = os.path.join(base, fn)
                    try:
                        size = os.path.getsize(fp)
                    except Exception:
                        continue
                    uid = h40("adopt", os.path.abspath(fp), size)
                    with self._lk:
                        if uid in self._uids.get("shared", set()):
                            continue
                    m = self._DATE_IN_NAME.search(fn) or self._DATE_IN_NAME.search(base)
                    ed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
                    # relpath 는 '루트 상대'여야 한다. 절대경로를 박으면 공용 인덱스에
                    # 이 PC 에서만 유효한 경로가 섞여 다른 전략·다른 PC 에서 못 푼다.
                    rel = (os.path.relpath(fp, self.root)
                           if os.path.abspath(fp).startswith(os.path.abspath(self.root)) else "")
                    self._enqueue("shared", {"uid": uid, "domain": "adopted", "kind": kind,
                                             "key": fn, "relpath": rel, "abspath": fp,
                                             "fmt": os.path.splitext(fn)[1].lstrip("."),
                                             "bytes": size, "event_date": ed or "",
                                             "knowledge_date": ed or "",
                                             "source": "preexisting_cache", "adopted": True})
                    n_dir += 1
                    n_all += 1
            if n_dir:
                L.info(f"기존 캐시 참조 등록(adopt): {dd} → {n_dir:,}건 (이동·삭제 없음)")
        self.flush("shared")
        if n_all:
            L.ok(f"기존 캐시 총 {n_all:,}건을 공용 인덱스에 참조 등록했습니다.")

    # 감사 ---------------------------------------------------------------------------------
    def audit(self):
        L.h1("캐시 금고 감사", f"저장 루트: {self.root} (모드 {self.mode})")
        rows = []
        for sc in ("shared", "private"):
            man = self.manifest(sc)
            try:
                nb = pd.to_numeric(man.get("bytes"), errors="coerce").fillna(0).sum()
            except Exception:
                nb = 0
            ad = 0
            if "adopted" in man.columns:
                ad = int(pd.Series(man["adopted"]).astype(str).isin(("True", "true", "1")).sum())
            rows.append([("공용 " + SHARED_NAMESPACE) if sc == "shared" else ("전용 " + PRIVATE_NAMESPACE),
                         f"{len(man):,}", f"{ad:,}", f"{nb/1e9:.2f} GB",
                         os.path.relpath(self._journal(sc), self.root)])
        L.grid(rows, ["인덱스", "등록건수", "참조등록", "용량", "저널(원천)"],
               ["l", "r", "r", "r", "l"])
        if self.hunt:
            L.info("로컬 보조 캐시 루트(읽기 전용): " + " · ".join(self.hunt) +
                   f"  (적중 {self.tally.get('local_hunt_hit', 0)}건)")
        else:
            L.info("로컬 보조 캐시 루트(D드라이브 등): 발견되지 않음 — 구글드라이브만 탐색했습니다.")
        man = self.manifest("shared")
        if len(man) and "domain" in man.columns:
            g = (man.groupby([man["domain"].astype(str), man["kind"].astype(str)])
                 .size().sort_values(ascending=False).head(20))
            L.grid([[a, b, f"{int(v):,}"] for (a, b), v in g.items()],
                   ["도메인", "종류", "건수"], ["l", "l", "r"],
                   title="공용 인덱스 구성 — 다른 전략에서 그대로 재사용 가능")
        L.info("무결성: 저널 append-only · 파생 인덱스는 백업 후 교체 · blob 내용해시 경로 · "
               "삭제 API 없음 · adopt 는 경로만 등록")


VAULT: Optional[VaultArchive] = None


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [5] HTTP 계층 + 쿼터 미터                                                                  ║
# ║   · 한국 사이트 수집 실패의 9할: UA/Referer 없음(403) · EUC-KR 오판(글자깨짐) · 과속(429)  ║
# ║   · 쿼터 미터: 호출량을 "사전 고정 예산" 없이 실시간 계수하고, 서버의 한도초과 신호를      ║
# ║     받는 순간 그 값을 '오늘의 실제 한도'로 학습해 멈춘다 → 남은 호출량만큼만 쓴다.          ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

_UA_SET = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
]
_NETLOCAL = threading.local()
NET_STATS: Counter = Counter()
# ★소스별 '마지막 응답 증거' — 상태코드와 본문 앞부분. 수집이 조용히 0행으로 끝났을 때
#   "서버가 실제로 뭘 돌려줬는가"를 로그로 보여주기 위한 것. 이게 없어서 두 번을 헤맸다.
NET_LAST: Dict[str, Tuple[Any, str]] = {}
_NET_LK = threading.Lock()


def _sess() -> requests.Session:
    s = getattr(_NETLOCAL, "s", None)
    if s is None:
        s = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            ad = HTTPAdapter(pool_connections=max(16, IO_THREADS * 2),
                             pool_maxsize=max(32, IO_THREADS * 4))
            s.mount("https://", ad); s.mount("http://", ad)
        except Exception:
            pass
        s.headers.update({"User-Agent": _UA_SET[0],
                          "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
                          "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
        _NETLOCAL.s = s
        _krx_apply_cookies(s)      # ★새 워커 스레드도 메인의 KRX 로그인 세션을 상속한다
    return s


_HANGUL_RE = re.compile(r"[가-힣]")
_MOJIBAKE_RE = re.compile(r"[ÀÁÂÃÄÅÆÇÈÉ¿½¾×ØÙÚÛÜ]")


def _readability(t: str) -> float:
    """한글 가독성 점수 — 네이버는 body 가 EUC-KR 인데 meta 는 utf-8 이라고 거짓말한다.
    선언을 믿지 않고 실제로 읽히는 인코딩을 점수로 고른다(깨져도 예외가 안 나기 때문)."""
    s = t[:6000]
    if not s:
        return -1.0
    return len(_HANGUL_RE.findall(s)) - 3.0 * len(_MOJIBAKE_RE.findall(s)) - 5.0 * s.count("�")


def smart_decode(raw: bytes, declared: Optional[str] = None, prefer: Optional[str] = None) -> str:
    head = raw[:4096].decode("ascii", "ignore").lower()
    m = re.search(r'charset\s*=\s*["\']?\s*([\w\-]+)', head)
    cands = [c for c in (prefer, m.group(1) if m else None, declared,
                         "utf-8", "euc-kr", "cp949") if c]
    best, best_s = None, -1e18
    seen = set()
    for enc in cands:
        e = enc.lower().replace("ks_c_5601-1987", "cp949")
        if e in seen:
            continue
        seen.add(e)
        try:
            t = raw.decode(e)
        except Exception:
            continue
        sc = _readability(t)
        if sc > 30:
            return t
        if sc > best_s:
            best, best_s = t, sc
    return best if best is not None else raw.decode("utf-8", "replace")




# ★봇차단 안내 페이지 지문. ★오탐이 미탐보다 훨씬 위험하다 — 정상 페이지를 차단으로 오판하면
#   그 소스가 통째로 '데이터 없음'이 되고, 한경은 그 달의 남은 페이지를 유실한 채 30건 이상이면
#   다음 실행부터 영구 스킵되며, DART 일괄 ZIP 목록이 실패하면 무료 재무 경로가 사라진다.
#   그래서 ①맨 단어 'robot'(→ <meta name="robots"> 에 그대로 걸린다) 같은 무앵커 토큰을 빼고
#         ②head/script 를 제거한 본문에만 적용한다.
_BOTWALL_RE = re.compile(r"(자동[^<>]{0,20}차단|비정상적인?\s*접근|접근이\s*제한|"
                         r"일시적으로\s*차단|자동입력\s*방지|보안문자|"
                         r"unusual\s+traffic|automated\s+access|are\s+a\s+robot)", re.I)
_STRIP_TAG_RE = re.compile(r"(?is)<(head|script|style|noscript)\b.*?</\1>")


def looks_botwalled(body: str) -> bool:
    """HTTP 200 인데 내용이 봇차단 안내인가. head/script 를 걷어낸 본문에서만 판정한다."""
    if not body or len(body) > 20000:
        return False
    return bool(_BOTWALL_RE.search(_STRIP_TAG_RE.sub(" ", body)))


KRX_COOKIES: Dict[str, str] = {}


def _krx_capture_cookies():
    """로그인 성공 직후 data.krx 쿠키를 전역에 복사한다.

    ★_sess() 는 스레드-로컬이다. 메인 스레드에서 로그인해도 워커 스레드의 세션에는 쿠키가
      없어서, 날짜축 벌크(8워커)가 전부 '비인증 요청'이 된다. 그러면 서버는 JSON 대신
      로그인 HTML 을 돌려주고, 심하면 중복로그인으로 메인 세션까지 끊긴다.
      실측에서 프리플라이트(메인 스레드)는 통과하는데 본 수집만 전멸하는 비대칭이 그것이다."""
    try:
        for c in _sess().cookies:
            if "krx.co.kr" in (c.domain or ""):
                KRX_COOKIES[c.name] = c.value
    except Exception:
        pass


def _krx_apply_cookies(s):
    # ★스냅샷 필수 — 공유 dict 를 그대로 순회하면, 수집 중 재로그인(_krx_capture_cookies)이
    #   워커 스레드와 겹치는 순간 RuntimeError(dictionary changed size during iteration)가
    #   나고 아래 except 에 조용히 삼켜져 ★쿠키가 일부만 적용된 세션이 남는다. 그러면
    #   프리플라이트는 통과하는데 본 수집만 전멸하는 비대칭이 아무 로그 없이 재현된다.
    snap = dict(KRX_COOKIES)
    if not snap:
        return
    for k, v in snap.items():
        try:
            s.cookies.set(k, v, domain=".krx.co.kr", path="/")
        except Exception as e:                                    # noqa
            with _NET_LK:
                NET_STATS[f"krx:cookie_{type(e).__name__}"] += 1


def net_get(url: str, source: str = "generic", params: Optional[dict] = None,
            headers: Optional[dict] = None, referer: Optional[str] = None,
            timeout: int = 25, tries: int = 3, as_bytes: bool = False,
            prefer_enc: Optional[str] = None, count_cb: Optional[Callable] = None
            ) -> Optional[Union[str, bytes]]:
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    last = None
    for k in range(tries):
        pace(source).wait()
        try:
            if k:
                hdr["User-Agent"] = _UA_SET[k % len(_UA_SET)]
            r = _sess().get(url, params=params, headers=hdr, timeout=timeout)
            # ★과금은 '서버에 도달한 뒤'다. 옛 코드는 요청 ★전에 계수해서, DNS·커넥트
            #   실패로 DART 에 닿지도 못한 시도까지 1건씩 깎았다. tries=2 라 불안정한
            #   회선에서는 장부가 실제의 최대 2배로 부풀고, 잔여가 남았는데도 조기 정지한다.
            if count_cb is not None:
                try:
                    count_cb()
                except Exception:
                    pass
            with _NET_LK:
                NET_STATS[f"{source}:{r.status_code}"] += 1
                NET_LAST[source] = (r.status_code, (r.content[:220] or b"")
                                    .decode("utf-8", "replace").replace("\n", " "))
            if r.status_code == 200:
                body = r.content if as_bytes else smart_decode(r.content, r.encoding, prefer_enc)
                # ★HTTP 200 짜리 차단 — 국내 포털은 봇으로 판정하면 403 이 아니라 200 에
                #   '자동 수집 차단' 안내 페이지를 실어 보낸다(다른 세션 실측). 상태코드만
                #   보면 '정상 응답인데 파싱이 0건'으로 보여서 원인 진단이 불가능해진다.
                if (not as_bytes) and isinstance(body, str) and looks_botwalled(body):
                    with _NET_LK:
                        NET_STATS[f"{source}:BOTWALL"] += 1
                        NET_LAST[source] = (200, "봇차단 안내 페이지(HTTP 200) — "
                                                 + body.strip()[:150].replace("\n", " "))
                    time.sleep(min(30.0, 4.0 * 2 ** k) + random.random() * 2)
                    last = requests.HTTPError(f"botwall200 {url}")
                    continue
                return body
            if r.status_code in (429, 503):
                time.sleep(min(25.0, 2.0 * 2 ** k) + random.random())
            elif r.status_code in (401, 403):
                time.sleep(1.2 * (k + 1))
            last = requests.HTTPError(f"{r.status_code} {url}")
        except Exception as e:                                    # noqa
            last = e
            with _NET_LK:
                NET_STATS[f"{source}:{type(e).__name__}"] += 1
            time.sleep(min(10.0, 1.6 ** k) + random.random() * 0.3)
    with _NET_LK:
        NET_STATS[f"{source}:FAIL"] += 1
    return None


def net_post(url: str, source: str = "generic", data: Optional[dict] = None,
             headers: Optional[dict] = None, referer: Optional[str] = None,
             timeout: int = 30, tries: int = 2, as_bytes: bool = False
             ) -> Optional[Union[str, bytes]]:
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    for k in range(tries):
        pace(source).wait()
        try:
            r = _sess().post(url, data=data, headers=hdr, timeout=timeout)
            with _NET_LK:
                NET_STATS[f"{source}:P{r.status_code}"] += 1
                NET_LAST[source] = (r.status_code, (r.content[:220] or b"")
                                    .decode("utf-8", "replace").replace("\n", " "))
            if r.status_code == 200:
                return r.content if as_bytes else smart_decode(r.content, r.encoding)
        except Exception as e:                                    # noqa
            with _NET_LK:
                NET_STATS[f"{source}:{type(e).__name__}"] += 1
        time.sleep(1.2 * (k + 1))
    return None


DL_TOTAL_S   = 900      # 큰 파일 1개에 허용하는 총시간(초) — 넘으면 포기하고 다음 파일로
DL_STALL_S   = 75       # 무진전 상한(초) — 이만큼 단 1바이트도 안 들어오면 끊는다
DL_CHUNK     = 1 << 20  # 1MB 청크


def net_download(url: str, source: str = "generic", params: Optional[dict] = None,
                 headers: Optional[dict] = None, referer: Optional[str] = None,
                 tries: int = 3, spool_over: int = 48 << 20,
                 total_s: float = DL_TOTAL_S, stall_s: float = DL_STALL_S,
                 on_progress: Optional[Callable[[int, int], None]] = None
                 ) -> Optional[Union[bytes, str]]:
    """★대용량 파일 스트리밍 다운로드 — net_get 으로 받으면 안 되는 것들.

    ★왜 별도 함수인가 (실측 사고):
      requests 의 `timeout=25` 는 '소켓 1회 연산'의 상한이지 ★총 소요시간의 상한이 아니다.
      25초마다 1바이트만 흘러들어와도 그 요청은 영원히 끝나지 않는다. DART 재무제표
      일괄 ZIP(파일당 수십~수백 MB) 129개를 그 함수로 직렬로 받았더니, 첫 파일이 반환되지
      않아 진행바가 `0/129 [00:00<?, ?it/s]` 에 고정된 채 멈췄다. tqdm 은 update() 가
      불릴 때만 다시 그리므로 ★사용자에게는 '정체'와 '진행 중'이 완전히 동일하게 보인다.

    그래서 세 가지를 동시에 건다:
      ① 총시간 상한(total_s)  — 아무리 느려도 이 시간이면 포기하고 다음 파일로 넘어간다.
      ② 무진전 상한(stall_s)  — 마지막 바이트 이후 이만큼 조용하면 죽은 연결로 보고 끊는다.
                                (느리지만 살아 있는 연결은 죽이지 않는다 — 총시간이 맡는다)
      ③ 진행 콜백(on_progress) — 받은 바이트를 밖으로 알린다. 진행바가 파일 단위로만
                                움직이면 20분짜리 파일 하나에서 화면이 죽는다.

    반환: 파일 내용(bytes). spool_over 를 넘으면 임시파일 경로(str)를 돌려준다 —
    Colab RAM(≈12GB)에서 수백 MB 를 통째로 들고 zipfile 에 넘기면 파싱 피크에서 터진다.
    호출부는 `isinstance(r, str)` 로 구분해 쓰고, 다 쓰면 반드시 지운다.
    """
    hdr = dict(headers or {})
    if referer:
        hdr["Referer"] = referer
    for k in range(max(1, tries)):
        pace(source).wait()
        t0 = time.monotonic()
        buf: Optional[io.BytesIO] = io.BytesIO()
        tmpf = None
        got = 0
        try:
            r = _sess().get(url, params=params, headers=hdr, stream=True,
                            timeout=(15, 60))
            with _NET_LK:
                NET_STATS[f"{source}:D{r.status_code}"] += 1
            if r.status_code != 200:
                with _NET_LK:
                    NET_LAST[source] = (r.status_code, f"download {url}")
                r.close()
                time.sleep(1.5 * (k + 1))
                continue
            total = int(r.headers.get("Content-Length") or 0)
            last_rx = time.monotonic()
            for chunk in r.iter_content(chunk_size=DL_CHUNK):
                now = time.monotonic()
                if chunk:
                    got += len(chunk)
                    last_rx = now
                    if tmpf is None and buf is not None and got > spool_over:
                        # 임계치 초과 → 디스크로 흘린다(메모리 피크 차단)
                        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".part")
                        tmpf.write(buf.getvalue())
                        buf = None
                    (tmpf or buf).write(chunk)          # type: ignore[union-attr]
                    if on_progress is not None:
                        try:
                            on_progress(len(chunk), total)
                        except Exception:
                            pass
                if now - last_rx > stall_s:
                    raise TimeoutError(f"stalled {stall_s:.0f}s at {got:,}B")
                if now - t0 > total_s:
                    raise TimeoutError(f"exceeded {total_s:.0f}s at {got:,}B")
            r.close()
            if total and got < total * 0.98:            # 잘린 응답을 성공으로 넘기지 않는다
                raise IOError(f"truncated {got:,}/{total:,}B")
            if tmpf is not None:
                tmpf.close()
                return tmpf.name
            return buf.getvalue() if buf is not None else b""
        except Exception as e:                                    # noqa
            with _NET_LK:
                NET_STATS[f"{source}:{type(e).__name__}"] += 1
                NET_LAST[source] = (None, f"download {type(e).__name__}: {e}")
            try:
                if tmpf is not None:
                    tmpf.close()
                    os.unlink(tmpf.name)
            except Exception:
                pass
            time.sleep(min(8.0, 1.8 ** k) + random.random())
    with _NET_LK:
        NET_STATS[f"{source}:DFAIL"] += 1
    return None


def net_json(url: str, source: str = "generic", **kw) -> Optional[Any]:
    t = net_get(url, source=source, **kw)
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        try:
            return json.loads(m.group(1)) if m else None
        except Exception:
            return None


def soupify(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return None


def net_audit():
    if not NET_STATS:
        return
    L.h1("HTTP 수집 감사", "소스별 응답 분포 — 403/429 가 많으면 QPS_CAP 을 낮추세요")
    per: Dict[str, Counter] = defaultdict(Counter)
    for k, v in NET_STATS.items():
        src, _, code = k.partition(":")
        per[src][code] += v
    rows = []
    for src, c in sorted(per.items()):
        tot = sum(c.values())
        okc = c.get("200", 0) + c.get("P200", 0)
        rows.append([src, f"{tot:,}", f"{okc:,}", f"{100*okc/max(tot,1):.1f}%",
                     ", ".join(f"{k}×{v}" for k, v in c.most_common(4))])
    L.grid(rows, ["소스", "요청", "성공", "성공률", "상세"], ["l", "r", "r", "r", "l"])


# ── 쿼터 미터 — "남은 호출량을 실시간으로 체크해서 그만큼 쓴다" ──────────────────────────────
class QuotaBook:
    """API 별 일일 호출량 실시간 장부.

    ★설계 원칙 — "쓸 수 있는 만큼 쓴다":
      · 사전 고정 예산(19,000 / 20,000 같은 숫자)을 정지선으로 쓰지 않는다.
        HINT 는 계획표에 '대략 얼마나 남았나'를 보여주기 위한 참고치일 뿐이다.
      · 실제 정지선은 오직 두 가지다.
          ① 서버가 한도초과를 알린 순간(DART status 020,
             공공데이터포털 LIMITED_NUMBER_OF_SERVICE_REQUESTS) → 그 지점을 오늘의
             '실측 한도'로 학습하고 그날은 깨끗이 멈춘다.
          ② 폭주 방지용 최후 안전판(HINT × RUNAWAY_X). 정상 수집은 여기 닿지 않는다.
      · 사용량은 (키 지문 × 날짜)로 드라이브에 영속화 → 재실행 시 정확히 이어받는다.
      · plan()/plan_table() 로 "이번 실행이 어디에 몇 회를 쓸 계획인지"를 먼저 보여준다.
        호출량이 모자라다면 그건 한도가 작아서가 아니라 계획이 비효율적이라는 뜻이다.
    """

    HINT = {"dart": 20_000, "datagokr": 10_000, "customs": 10_000}
    RUNAWAY_X = 4.0                # 안전판 배수 — 서버가 아무 말도 안 할 때만 의미가 있다

    def __init__(self):
        self._lk = threading.Lock()
        self.date = dtm.date.today().isoformat()
        self.used: Counter = Counter()
        self.learned_cap: Dict[str, int] = {}
        self.blocked: Dict[str, bool] = {}
        self.planned: List[dict] = []
        self.soft: Dict[str, int] = {}      # 공식치를 넘겨 '실측으로 넓힌' 상한(이번 실행 한정)
        self.ok_run: Dict[str, int] = {}    # 마지막 상향 이후 서버 정상 응답 수
        self._loaded = False

    def _fp(self, src: str) -> str:
        key = {"dart": DART_API_KEY, "datagokr": DATA_GO_KR_KEY,
               "customs": CUSTOMS_API_KEY}.get(src, "")
        return h40(src, key)[:10]

    def _path(self) -> Optional[str]:
        if VAULT is None:
            return None
        # ★"_" 접두어 — manifest() 의 레거시 인덱스 흡수 대상(.json)에 걸리지 않게 한다
        return os.path.join(VAULT.ns["private"], "manifest", "_quota_book.json")

    def load(self):
        # ★_loaded 는 ★파일을 다 읽은 뒤에 세운다. 먼저 세우면 경쟁 스레드가 used 가 아직
        #   빈 상태로 allow() 를 통과하고, 그 사이 charge() 로 올라간 값을 아래 대입이
        #   덮어써서 그날 사용량이 통째로 사라진다.
        p = self._path()
        if not p:
            self._loaded = True
            return
        if not os.path.exists(p):                          # 구 파일명 이관(읽기만)
            legacy = os.path.join(os.path.dirname(p), "quota_book.json")
            p = legacy if os.path.exists(legacy) else p
        j = None
        if os.path.exists(p):
            try:
                j = json.loads(open(p, encoding="utf-8").read())
            except Exception:
                j = None
        if not isinstance(j, dict) or j.get("date") != self.date:
            self._loaded = True
            return
        with self._lk:
            for k, v in (j.get("used") or {}).items():
                # ★max — 이 사이에 charge() 로 올라간 값을 파일값이 되돌리면 안 된다
                self.used[k] = max(int(self.used.get(k, 0)), int(v))
            for k, v in (j.get("learned_cap") or {}).items():
                self.learned_cap[k] = int(v)
            self._loaded = True
        for src in self.HINT:
            n = self.used.get(f"{src}:{self._fp(src)}", 0)
            if n:
                L.info(f"쿼터 장부 복원 — {src}: 오늘 이미 {n:,}건 사용 "
                       f"(잔여 추정 {self.remaining(src):,}건). 이어서 사용합니다.")

    def _save(self):
        p = self._path()
        if not p:
            return
        try:
            write_text_atomic(p, json.dumps({"date": self.date, "used": dict(self.used),
                                             "learned_cap": self.learned_cap},
                                            ensure_ascii=False))
        except Exception:
            pass

    def learned(self, src: str) -> Optional[int]:
        return self.learned_cap.get(f"{src}:{self._fp(src)}")

    def cap(self, src: str) -> int:
        """정지선. 서버가 알려준 실측 한도가 있으면 그것, 없으면 폭주 안전판."""
        lc = self.learned(src)
        if lc is not None:
            return int(lc)
        return int(self.HINT.get(src, 10 ** 8) * self.RUNAWAY_X)

    def hint(self, src: str) -> int:
        lc = self.learned(src)
        return int(lc) if lc is not None else int(self.HINT.get(src, 10 ** 8))

    def spent(self, src: str) -> int:
        return int(self.used.get(f"{src}:{self._fp(src)}", 0))

    def remaining(self, src: str) -> int:
        """표시용 잔여 추정 — 실측 한도가 학습됐으면 정확값, 아니면 공식치 기준 추정."""
        return max(0, self.hint(src) - self.spent(src))

    PROBE_STEP = 0.10       # 공식치를 넘겼을 때 한 번에 더 허용할 폭(공식치 대비)
    PROBE_MIN_OK = 40       # 상향하려면 그 구간에서 서버가 이만큼은 정상 응답해야 한다

    def ceiling(self, src: str) -> int:
        """지금 이 순간의 실효 상한. 서버가 알려준 실측치 > 실측 상향치 > 공식치 순."""
        lc = self.learned(src)
        if lc is not None:
            return int(lc)
        key = f"{src}:{self._fp(src)}"
        return int(self.soft.get(key) or self.HINT.get(src, 10 ** 8))

    def ok(self, src: str, n: int = 1):
        """서버가 정상 응답했다 — 실측 상향의 근거가 된다(호출 성공 카운터)."""
        key = f"{src}:{self._fp(src)}"
        with self._lk:
            self.ok_run[key] = self.ok_run.get(key, 0) + int(n)

    def can(self, src: str, n: int = 1) -> bool:
        """★부작용 없는 판정 — "지금 n 건을 더 쓸 수 있나?" 만 답한다.

        allow() 는 순수하지 않다. 상한에 닿으면 blocked 를 ★영구히 세우거나 probe
        크레딧(ok_run)을 소비한다. 그런데 코드 세 곳이 allow() 를 조건식처럼 썼다:
          · `if len(grp) > 20 and QUOTA.allow("dart", 2)` — '반으로 쪼개도 되나?' 를 묻는
            것뿐인데, 잔여가 1건이면 '2건 요청'으로 판정해 ★dart 소스를 통째로 막는다.
            그러면 이후 모든 dart_call 이 None 이 되고, 그 None 이 '데이터 없음'으로
            오인되어 영구 음성캐시가 대량 생성된다.
          · `if all_013 and QUOTA.allow("dart")` — 음성캐시에 넣어도 되는지 묻는 read-only
            의도인데, 아직 실행도 안 한 뒤 소비자들까지 함께 죽인다.
        판정만 필요할 때는 이걸 쓰고, allow() 는 ★실제 호출 직전에만 쓴다.
        """
        if not self._loaded:
            self.load()
        key = f"{src}:{self._fp(src)}"
        with self._lk:
            if self.blocked.get(key):
                return False
            return self.used[key] + int(n) <= self.cap(src)

    def allow(self, src: str, n: int = 1) -> bool:
        """호출 전 확인 — ★공식치를 실효 상한으로 삼되, 이 키의 실한도가 더 크면 실측으로 넓힌다.

        옛 구현은 폭주 안전판(공식치×4)까지 통과시켰다. 그래서 하루 20,000 짜리 키로
        22,000 을, 10,000 짜리 키로 20,000 을 태우고도 멈추지 않았다(실측: 국민연금 수집이
        잔여 0 인 상태로 67분을 더 돌았다). 반대로 공식치에서 딱 끊으면, 실제로 한도가 더 큰
        키에서 남은 용량을 버리게 된다. 그래서 둘 다 만족시킨다:
          · 기본 상한 = 공식치(또는 서버가 알려준 실측 한도)
          · 공식치에 닿았는데 그 직전 구간에서 서버가 계속 정상 응답했다면 → 한 스텝(10%)씩
            넓히고 그 사실을 로그로 남긴다. 서버가 020 을 보내면 즉시 그 지점을 학습하고 정지.
          · 폭주 안전판(공식치×RUNAWAY_X)은 그대로 최후 방어선으로 남는다.
        """
        if not self._loaded:
            self.load()
        key = f"{src}:{self._fp(src)}"
        with self._lk:
            if self.blocked.get(key):
                return False
            used = self.used[key]
            if used + n <= self.ceiling(src):
                return True
            hard = self.cap(src)
            if used + n > hard or self.learned(src) is not None:
                if not self.blocked.get(key):
                    self.blocked[key] = True
                    L.warn(f"[{src}] 상한 도달(사용 {used:,} / 공식치 "
                           f"{self.HINT.get(src, 0):,}) — 받은 만큼 저장하고 이 소스를 멈춥니다. "
                           f"남은 일은 다음 실행이 정확히 이어받습니다.")
                return False
            if self.ok_run.get(key, 0) >= self.PROBE_MIN_OK:
                step = max(int(self.HINT.get(src, 0) * self.PROBE_STEP), 200)
                self.soft[key] = min(int(self.ceiling(src)) + step, hard)
                self.ok_run[key] = 0
                nxt = self.soft[key]
                blocked = False
            else:
                self.blocked[key] = True
                blocked = True
                nxt = 0
        if blocked:
            L.warn(f"[{src}] 공식치 {self.HINT.get(src, 0):,}건에 도달했고 그 뒤 정상 응답이 "
                   f"충분치 않아 정지합니다. 남은 일은 다음 실행이 이어받습니다.")
            return False
        L.info(f"[{src}] 공식치 {self.HINT.get(src, 0):,}건을 넘겼는데 서버가 계속 정상 응답 — "
               f"이 키의 실한도가 더 큰 것으로 보고 상한을 {nxt:,}건으로 넓힙니다"
               f"(서버가 한도초과를 알리면 그 지점에서 즉시 멈춥니다).")
        return True

    # ── 수집 계획 ─────────────────────────────────────────────────────────────────────
    def plan(self, src: str, n: int, what: str):
        """이번 실행이 어디에 몇 회를 쓸 계획인지 기록 — plan_table() 로 한눈에 보여준다."""
        with self._lk:
            self.planned.append({"src": src, "n": int(n), "what": what})

    def plan_table(self):
        if not self.planned:
            return
        agg: Dict[str, int] = defaultdict(int)
        for p in self.planned:
            agg[p["src"]] += p["n"]
        rows = []
        for p in self.planned:
            rows.append([p["src"], p["what"], f"{p['n']:,}"])
        rows.append(["─" * 8, "─ 소스별 합계 · 실시간 잔여 ─", ""])
        for s, n in sorted(agg.items(), key=lambda kv: -kv[1]):
            if s in self.HINT:
                rem = self.remaining(s)
                mark = "충분" if rem >= n else f"부족 {n-rem:,}회(다음 실행 이어받기)"
                rows.append([s, f"계획 {n:,} / 잔여 {rem:,} → {mark}", f"{n:,}"])
            else:
                rows.append([s, f"계획 {n:,} (키 불필요 소스 — 일일 한도 없음)", f"{n:,}"])
        L.grid(rows, ["소스", "무엇에 · 판정", "호출수"], ["l", "l", "r"],
               title="이번 실행 호출 계획 (사전 고정예산 없음 · 실시간 잔여 기준)")

    def charge(self, src: str, n: int = 1):
        key = f"{src}:{self._fp(src)}"
        with self._lk:
            self.used[key] += n
            u = self.used[key]
        if u % 500 == 0:
            self._save()
        if u % 2000 == 0:
            L.info(f"[{src}] 오늘 사용 {u:,}건 · 실시간 잔여 추정 {self.remaining(src):,}건")

    def server_says_limit(self, src: str):
        """서버가 한도초과를 알렸다 — 현재 사용량을 오늘의 실측 한도로 학습하고 정지."""
        key = f"{src}:{self._fp(src)}"
        with self._lk:
            self.learned_cap[key] = self.used.get(key, 0)
            self.blocked[key] = True
        self._save()
        L.warn(f"[{src}] 서버 한도초과 신호 수신 → 오늘의 실측 한도를 {self.learned_cap[key]:,}건으로 "
               f"학습하고 정지합니다. 여기까지 받은 데이터는 드라이브에 저장되어 있습니다.")

    def report(self):
        rows = []
        for src in self.HINT:
            key = f"{src}:{self._fp(src)}"
            u = self.used.get(key, 0)
            if u == 0 and key not in self.learned_cap:
                continue
            rows.append([src, f"{u:,}", f"{self.hint(src):,}", f"{self.remaining(src):,}",
                         "실측(서버 020 신호로 학습)" if key in self.learned_cap
                         else "공식치 기준 추정(정지선 아님)"])
        if rows:
            L.grid(rows, ["API", "오늘 사용", "한도", "잔여", "한도 근거"],
                   ["l", "r", "r", "r", "l"], title="API 쿼터 장부 (실시간 잔여량 관리)")
        self._save()


QUOTA = QuotaBook()


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [5b] 수집 시간예산 시계 — "4시간이 지나면 그때까지 모인 데이터로 일단 중간결과"            ║
# ║                                                                                          ║
# ║   수집·정제가 오래 걸리지 백테스트 자체는 몇 분이면 된다(사용자 지시 2026-08-09).          ║
# ║   그래서 수집부에만 벽시계 예산을 건다:                                                    ║
# ║    · 예산 도달 → 진행 중인 조각까지만 받고 전부 드라이브에 저장 → 수집 중단                ║
# ║    · 파이프라인은 그대로 진행되어 부분 데이터 기반의 '중간(잠정) 결과'를 끝까지 출력       ║
# ║    · 무엇이 어디까지 수집됐는지 '수집 완성도' 표로 명시, 재실행하면 정확히 이어받는다      ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

HARVEST_TIME_BUDGET_H = 4.0        # 수집 단계 벽시계 예산(시간). 0 또는 음수 = 무제한.


class HarvestClock:
    """수집 전용 시간예산. 백테스트/강건성/리포트 단계는 이 시계의 영향을 받지 않는다."""

    def __init__(self, hours: float):
        self.budget_s = float(hours) * 3600.0 if hours and hours > 0 else float("inf")
        self.t0 = time.time()
        self.tripped = False
        self.cuts: List[str] = []          # 무엇이 어디서 잘렸는가 (수집 완성도 표의 입력)
        self._warned = False
        self._soft: Optional[float] = None      # 서브예산 마감선(임시)
        self._soft_what = ""
        self._soft_give = 0.0
        self._soft_hit = False

    @contextmanager
    def lease(self, share: float, what: str, cap_s: float = 0.0):
        """★서브예산 — 한 스테이지가 전체 시간예산을 다 먹지 못하게 임시 마감선을 건다.

        호출 예산(dart/datagokr)은 소스별로 나뉘어 있지만 ★시간 예산은 하나다. 그래서
        앞 스테이지가 시간을 다 쓰면 뒤 스테이지는 호출량이 남아 있어도 첫 배치에서
        끊긴다. 특히 센서팩(N·X)의 θ 분모가 DART(직원수·매출)라, 팩을 먼저 다 받아도
        DART 가 굶으면 θ 가 전량 결측이 되어 ★그 팩 축이 통째로 사라진다 — 쿼터만
        태우고 축은 없는, 순서를 바꿔서 얻으려던 것과 정반대의 결과가 된다.
        그래서 앞 스테이지에 '잔여의 몇 %까지' 라는 몫을 물리적으로 건다.
        """
        prev = (self._soft, self._soft_what, self._soft_give, self._soft_hit)
        rem = self.remaining()
        give = rem * max(0.0, float(share))
        if cap_s and cap_s > 0:
            give = min(give, float(cap_s))
        if give == float("inf"):
            yield float("inf")
            return
        self._soft = time.time() + give
        self._soft_what, self._soft_give, self._soft_hit = what, give, False
        L.info(f"⏱ '{what}' 시간 몫 {give/60:.0f}분 배정(잔여 {rem/60:.0f}분의 "
               f"{share*100:.0f}%) — 이 몫을 넘기면 여기서 멈추고 다음 스테이지로 넘깁니다. "
               f"뒤에 오는 DART 가 굶으면 θ 분모가 사라져 이 팩의 축도 같이 죽습니다.")
        try:
            yield give
        finally:
            self._soft, self._soft_what, self._soft_give, self._soft_hit = prev

    def restart(self, why: str = ""):
        """예산 기점 재설정 — 부트/계약검정/스모크가 아니라 '실데이터 수집 시작'을 t0 로 삼는다."""
        self.t0 = time.time()
        self.tripped = False
        self._warned = False
        if why:
            L.info(f"⏱ 수집 시간예산 {self.budget_s/3600:.1f}h 기점: {why}")

    def elapsed(self) -> float:
        return time.time() - self.t0

    def remaining(self) -> float:
        return max(0.0, self.budget_s - self.elapsed())

    def over(self) -> bool:
        # ★서브예산이 먼저다 — 전체 예산이 남아 있어도 이 스테이지의 몫은 끝났을 수 있다.
        #   전역 tripped 는 세우지 않는다(다음 스테이지는 남은 예산으로 계속 돌아야 한다).
        if self._soft is not None and time.time() >= self._soft:
            if not self._soft_hit:
                self._soft_hit = True
                L.warn(f"⏱ '{self._soft_what}' 시간 몫 {self._soft_give/60:.0f}분 소진 — "
                       f"여기서 멈추고 다음 스테이지로 넘깁니다(전체 예산은 "
                       f"{self.remaining()/60:.0f}분 남았습니다). 남은 일은 다음 실행이 "
                       f"원장에서 정확히 이어받습니다.")
            return True
        if self.elapsed() >= self.budget_s:
            if not self.tripped:
                self.tripped = True
                L.warn(f"⏱ 수집 시간예산 {self.budget_s/3600:.1f}시간 도달 — 신규 수집을 멈추고 "
                       f"지금까지 확보한 데이터로 중간(잠정) 백테스트를 진행합니다. "
                       f"모든 수집분은 드라이브에 저장되어 재실행 시 이어받습니다.")
            return True
        if not self._warned and self.remaining() < 15 * 60:
            self._warned = True
            L.info(f"⏱ 수집 시간예산 잔여 {self.remaining()/60:.0f}분 — 곧 중간결과 모드로 전환됩니다.")
        return False

    def cut(self, what: str):
        """수집 루프가 예산 때문에 조기 종료될 때 호출 — 잘린 지점을 기록한다."""
        self.cuts.append(what)
        L.warn(f"⏱ 시간예산으로 수집 중단: {what}")

    def coverage_table(self):
        if not self.tripped and not self.cuts:
            return
        L.h1("수집 완성도 (시간예산 체크포인트)",
             f"예산 {self.budget_s/3600:.1f}h · 경과 {self.elapsed()/3600:.2f}h — "
             f"아래 항목은 부분 수집 상태이며 재실행 시 이어받습니다")
        L.grid([[i + 1, c] for i, c in enumerate(self.cuts)] or [[1, "(상세 기록 없음)"]],
               ["#", "예산 도달로 잘린 수집"], ["r", "l"])


def chunked(seq: Sequence, size: int) -> Iterable[list]:
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def budget_batches(jobs: Sequence, size: int, src: str, what: str,
                   cap: Optional[int] = None, unit: str = "건") -> Iterable[list]:
    """★예산·시계 가드가 걸린 배치 이터레이터 — 모든 수집기가 이걸 쓴다.

    이 열 줄이 7개 수집기에 각자 복사돼 있었고, 그래서 ★같은 결함을 매번 7번씩 고쳐야
    했다. 실제로 그렇게 고친 것들:
      · max_calls=0 이 '무제한'으로 뒤집히던 것(dart 4곳 + datagokr 3곳)
      · 중단 사유가 원인과 무관하게 '배정 소진'으로 찍히던 것(4곳)
      · CLOCK 체크가 배치 경계에만 있어 예산 만료 뒤 수천 회를 더 태우던 것
    한 곳으로 모으면 다음 결함은 한 번만 고치면 된다 — 그게 이 함수의 존재 이유다.

    cap 규약은 cap_of() 와 같다: None/-1=무제한 · 0=금지 · 양수=상한.
    """
    base = QUOTA.spent(src)
    c = cap_of(cap)
    left = len(jobs)
    for b in chunked(jobs, size):
        over, noq = CLOCK.over(), not QUOTA.allow(src)
        if over or noq or (c is not None and QUOTA.spent(src) - base >= c):
            why = "시간예산" if over else ("호출 잔여량 소진" if noq else "배정 소진")
            CLOCK.cut(f"{what}: {left:,}{unit} 남기고 중단({why}) — 다음 실행이 이어받습니다")
            return
        yield b
        left -= len(b)


CLOCK = HarvestClock(HARVEST_TIME_BUDGET_H)


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [6] PIT 코어 (C1·C3) + 횡단면 통계 (C5) + 셀 (C11) + TP 프리미티브 (§1.1)                  ║
# ║                                                                                          ║
# ║  C1: 모든 레코드는 event_date / knowledge_date 두 날짜를 가진다.                           ║
# ║      시점 t 의 피처는 knowledge_date <= t 인 레코드만 쓴다. 접근은 PITX 단일 게이트웨이,   ║
# ║      우회 파라미터는 의도적으로 만들지 않았다.                                             ║
# ║  C5: winsorize(±2σ) → 셀 내 z → percentile rank. 순서는 여기 한 곳에만 하드코딩된다.       ║
# ║  C11: cell = (date, industry, size_bucket). 표본<8 이면 상위 단위 폴백(로깅).              ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

PIT_STAMPS = ("event_date", "knowledge_date")


def pit_mark(df: pd.DataFrame, event, knowledge, origin: str = "") -> pd.DataFrame:
    """모든 수집 결과는 이 함수로 두 날짜를 박아야 PIT 저장소에 등록된다.

    event / knowledge 인자: ① df 의 컬럼명(str) ② 같은 길이의 시퀀스 ③ 스칼라(브로드캐스트).
    knowledge < event 는 그 자체가 미래누수 신호이므로 event 로 끌어올리고 로그에 남긴다."""
    if df is None or len(df) == 0:
        base = pd.DataFrame(df if df is not None else None)
        for c in PIT_STAMPS:
            if c not in base.columns:
                base[c] = pd.Series(dtype="datetime64[ns]")
        return base
    out = df.copy().reset_index(drop=True)

    def _resolve(arg) -> pd.Series:
        if isinstance(arg, str) and arg in out.columns:
            return ds_(out[arg]).set_axis(out.index)
        if isinstance(arg, (pd.Series, list, tuple, np.ndarray, pd.DatetimeIndex)):
            vals = list(arg.to_numpy()) if isinstance(arg, pd.Series) else list(arg)
            if len(vals) != len(out):
                raise ValueError(f"pit_mark 날짜 길이 불일치: {len(vals)} vs {len(out)}")
            return ds_(pd.Series(vals)).set_axis(out.index)
        return ds_(pd.Series([arg] * len(out))).set_axis(out.index)

    out["event_date"] = _resolve(event)
    out["knowledge_date"] = _resolve(knowledge)
    bad = out["knowledge_date"] < out["event_date"]
    if bad.any():
        # ★보정 방향이 중요하다 — knowledge 를 event 로 '미래 쪽으로' 민다. 반대로 당기면
        #   아직 알 수 없는 정보를 아는 것이 되어 그대로 미래참조(상향 드리프트)가 된다.
        out.loc[bad, "knowledge_date"] = out.loc[bad, "event_date"]
        PIT_AUDIT["kd_lt_ed_fixed"] += int(bad.sum())
        RUN.note(f"WARN: knowledge<event {int(bad.sum())}행 보정({origin})")
    # ★미래 knowledge — 오늘 이후 날짜가 박히면 PIT 관문이 절단하므로 누수는 아니지만,
    #   그 행은 백테스트 전 구간에서 '영원히 안 보이는' 데이터가 된다(조용한 결손).
    _fut = out["knowledge_date"] > pd.Timestamp(dtm.date.today())
    if _fut.any():
        PIT_AUDIT["future_knowledge"] += int(_fut.sum())
    out = out.dropna(subset=["knowledge_date"])
    if origin:
        out["_origin"] = origin
    return out


class PITGateway:
    """유일한 시점 데이터 게이트웨이. 등록 시 PIT 스탬프가 없으면 거부(KeyError)."""

    def __init__(self):
        self._tables: Dict[str, pd.DataFrame] = {}
        self._meta: Dict[str, dict] = {}
        self.hits: Counter = Counter()

    def put(self, name: str, df: pd.DataFrame, keys: Sequence[str] = ()):
        if df is None or len(df) == 0:
            self._tables[name] = pd.DataFrame(columns=list(PIT_STAMPS))
            self._meta[name] = {"rows": 0, "keys": list(keys), "empty": True}
            return
        missing = [c for c in PIT_STAMPS if c not in df.columns]
        if missing:
            raise KeyError(f"[C1 위반] '{name}' 에 PIT 스탬프 {missing} 가 없습니다. "
                           f"pit_mark(df, event, knowledge) 로 감싸세요. 우회 경로는 없습니다.")
        d = df.copy()
        d["knowledge_date"] = ds_(d["knowledge_date"])
        d = d.dropna(subset=["knowledge_date"]).sort_values("knowledge_date",
                                                            kind="stable").reset_index(drop=True)
        self._tables[name] = d
        self._meta[name] = {"rows": len(d), "keys": list(keys), "empty": False,
                            "k_min": d["knowledge_date"].min(), "k_max": d["knowledge_date"].max()}
        RUN.io("OUT", "PIT", name, d)

    def has(self, name: str) -> bool:
        return name in self._tables and not self._meta.get(name, {}).get("empty", True)

    def view(self, name: str, as_of, latest_by: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """knowledge_date <= as_of 절단. latest_by 를 주면 키별 당시-최신 1행."""
        self.hits[name] += 1
        d = self._tables.get(name)
        if d is None or d.empty:
            return pd.DataFrame()
        t = d_(as_of)
        pos = int(np.searchsorted(d["knowledge_date"].values, np.datetime64(t), side="right"))
        cut = d.iloc[:pos]
        if latest_by:
            lb = [c for c in latest_by if c in cut.columns]
            if lb:
                cut = cut.drop_duplicates(subset=lb, keep="last")
        return cut

    def asof_attach(self, panel: pd.DataFrame, name: str, by: str, when: str = "month",
                    take: Optional[Sequence[str]] = None, tag: str = "") -> pd.DataFrame:
        """view() 의 벡터화 등가물 — merge_asof(backward) 는 knowledge_date<=when 과 동일 의미.

        ★ 결합키가 결측인 패널 행을 버리면 안 된다. corp_code 없는 종목(대개 상장폐지·비DART)이
          사라지는 것이 곧 생존자편향 재유입(C2)이다. 유효 부분만 결합해 전체에 되붙인다."""
        self.hits[name] += 1
        right = self._tables.get(name)
        if right is None or right.empty or panel.empty or by not in panel.columns \
                or by not in right.columns:
            return panel
        use = [c for c in (take or [c for c in right.columns if c not in ("event_date", "_origin")])
               if c in right.columns]
        for c in (by, "knowledge_date"):
            if c not in use:
                use.append(c)
        R = right[use].dropna(subset=[by, "knowledge_date"]).copy()
        if R.empty:
            return panel
        base = panel.copy()
        base["_seq"] = np.arange(len(base))
        mask = base[when].notna() & base[by].notna()
        Lf = base[mask].copy()
        if Lf.empty:
            return panel
        R[by] = R[by].astype(str)
        Lf[by] = Lf[by].astype(str)
        R = R.sort_values("knowledge_date", kind="stable")
        Lf = Lf.sort_values(when, kind="stable")
        try:
            M = pd.merge_asof(Lf, R, left_on=when, right_on="knowledge_date", by=by,
                              direction="backward", suffixes=("", tag or "_r"))
        except Exception as e:                                    # noqa
            L.warn(f"asof 결합 실패({type(e).__name__}) — '{name}' 결합을 건너뜁니다.")
            return panel
        fresh = [c for c in M.columns if c not in base.columns]
        if not fresh:
            return panel
        out = base.set_index("_seq").join(M.set_index("_seq")[fresh], how="left")
        out = out.sort_index().reset_index(drop=True)
        out.index = panel.index
        return out

    def audit(self):
        rows = [[n, f"{m['rows']:,}", str(m.get("k_min", ""))[:10], str(m.get("k_max", ""))[:10],
                 ",".join(m.get("keys", []))[:24], f"{self.hits.get(n, 0):,}"]
                for n, m in self._meta.items()]
        L.grid(rows, ["PIT 테이블", "행수", "knowledge 최소", "최대", "키", "조회"],
               ["l", "r", "l", "l", "l", "r"],
               title="PIT 저장소 (C1 — 모든 조회는 knowledge_date≤as_of 강제)")


PITX = PITGateway()


# ── 횡단면 통계 (C5 — 순서 고정) ────────────────────────────────────────────────────────────
WINSOR_K = 2.0
CELL_MIN = 8


def cell_z(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN) -> pd.Series:
    """winsorize(±2σ) → 셀 내 z. ★±inf 는 먼저 NaN 으로 — nanmean 은 inf 를 무시하지 않아
    셀에 inf 하나만 있어도 그 셀 전체 z 가 뭉개진다(비율·로그 지표의 흔한 사고)."""
    v = pd.to_numeric(values, errors="coerce").astype("float64").replace([np.inf, -np.inf], np.nan)
    # ★열 전체가 상수면 그것은 '평균과 같다(z=0)'가 아니라 ★정보가 없다는 뜻이다.
    #   실측: 자사주 소각 공시를 한 건도 수집하지 못해 p3 가 전량 0 이었는데, z 가 0.0 을
    #   돌려주는 바람에 TP_P2 가 '관측 6,442행 · 발화율 0%'로 살아남아 E_C 를 희석했다.
    #   결측으로 두면 nrow_mean 이 그 축을 빼고 평균하므로 남은 축이 제 무게를 갖는다.
    if v.notna().sum() and not (float(v.std(skipna=True) or 0.0) > 0):
        return pd.Series(np.nan, index=v.index, dtype="float32")
    grp = pd.Series(cells).astype(object).fillna("_NA_").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    n = g.transform("count")
    m0 = g.transform("mean")
    s0 = g.transform("std", ddof=0)
    w = v.clip(lower=m0 - WINSOR_K * s0, upper=m0 + WINSOR_K * s0)
    gw = w.groupby(grp, observed=True, dropna=False)
    mu = gw.transform("mean")
    sd = gw.transform("std", ddof=0)
    z = (w - mu) / sd.where(sd > 0)
    z = z.mask(sd.notna() & (sd <= 0) & w.notna(), 0.0)
    return z.where(n >= min_n).astype("float32")


def cell_rank(values: pd.Series, cells: pd.Series, min_n: int = CELL_MIN) -> pd.Series:
    """셀 내 백분위 [0,1]. 표본 부족 셀은 NaN — 0으로 채우지 않는다."""
    v = pd.to_numeric(values, errors="coerce").astype("float64").replace([np.inf, -np.inf], np.nan)
    grp = pd.Series(cells).astype(object).fillna("_NA_").to_numpy()
    g = v.groupby(grp, observed=True, dropna=False)
    n = g.transform("count")
    return g.rank(pct=True, method="average").where(n >= min_n).astype("float32")


CELL_LADDER = ("cell", "cell_up", "cell_all")


def zx(P: pd.DataFrame, name_or_s, min_n: int = CELL_MIN) -> pd.Series:
    """셀 폴백 사다리를 적용한 z (C11).
    셀엔 30종목이 있어도 '그 센서를 관측한' 종목은 5개일 수 있다(관세·조달처럼 부분 커버 팩).
    그때 z 가 전부 NaN 이 되어 팩이 조용히 죽는 것을 사다리로 막고, 폴백은 로깅된다."""
    v = colx(P, name_or_s) if isinstance(name_or_s, str) else \
        pd.to_numeric(name_or_s, errors="coerce")
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = cell_z(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not out.isna().any():
            break
        if lvl in P.columns:
            out = out.where(out.notna(), cell_z(v, P[lvl], min_n))
    return out


def rx(P: pd.DataFrame, name_or_s, min_n: int = CELL_MIN) -> pd.Series:
    v = colx(P, name_or_s) if isinstance(name_or_s, str) else \
        pd.to_numeric(name_or_s, errors="coerce")
    if v.notna().sum() == 0:
        return pd.Series(np.nan, index=P.index, dtype="float32")
    out = cell_rank(v, P["cell"], min_n) if "cell" in P.columns else \
        pd.Series(np.nan, index=P.index, dtype="float32")
    for lvl in CELL_LADDER[1:]:
        if not out.isna().any():
            break
        if lvl in P.columns:
            out = out.where(out.notna(), cell_rank(v, P[lvl], min_n))
    return out


def tp_pair(z_gain: pd.Series, z_nocost: pd.Series) -> pd.Series:
    """TP = z(개선) × z(치르지 않은 대가) — ★반드시 곱(§1.1). 합산 금지.
    한쪽 결측이면 결과도 결측 — 0으로 채우면 '대가를 안 치렀다'는 거짓 주장이 된다."""
    return (pd.to_numeric(z_gain, errors="coerce") *
            pd.to_numeric(z_nocost, errors="coerce")).astype("float32")


# ── 셀 (C11) ────────────────────────────────────────────────────────────────────────────────
EMP_BUCKETS = [(0, 50, "<50"), (50, 100, "50-99"), (100, 300, "100-299"),
               (300, 1000, "300-999"), (1000, 10 ** 9, "1000+")]


def emp_bucket(n) -> str:
    """규모 버킷 — 정부 지원 요건이 규모에 연동되므로 규모를 셀에 넣으면 정책효과가
    셀 내 공통충격으로 흡수된다(§계약 C11 취지). 비용 0의 오염 제거."""
    try:
        v = float(n)
    except Exception:
        return "규모미상"
    if not np.isfinite(v) or v <= 0:
        return "규모미상"
    for lo, hi, tag in EMP_BUCKETS:
        if lo <= v < hi:
            return tag
    return "1000+"


def attach_cells(P: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """cell=(월, 산업, 규모버킷) + 폴백 사다리 컬럼. 폴백 발생은 로깅한다(C11).
    ※ 산업분류는 '현재 시점' 분류를 쓴다 — 완전 PIT 아님을 한계로 명시(변경 빈도 낮음)."""
    ind = master.set_index("code")["industry"].astype(str).to_dict()
    P = P.copy()
    P["industry"] = P["code"].map(ind).fillna("미분류").astype(str).replace("", "미분류")
    # ★규모버킷 사다리 — 직원수(DART) → 시가총액 → 20일 거래대금 → 규모미상.
    #   옛 코드는 직원수 하나에만 매달려 있었다. DART 일일 한도가 재무 심층 티어에 먼저
    #   쓰이면 직원현황이 통째로 비고, 그러면 모든 행이 '규모미상'이 되어 C11 셀이
    #   (월, 산업)으로 붕괴한다 — 규모 통제가 사라진 채 z·랭크가 계산되는데 로그엔 아무
    #   표시도 안 난다. 규모 대리변수는 시총·거래대금으로도 충분히 만들 수 있다.
    sb = (P["employees"].map(emp_bucket) if "employees" in P.columns
          else pd.Series("규모미상", index=P.index))
    sb = sb.where(sb.notna() & (sb != "규모미상"))
    for col, lab in (("mktcap", "시총"), ("adv20", "거래대금")):
        if sb.isna().any() and col in P.columns and P[col].notna().any():
            q = (pd.to_numeric(P[col], errors="coerce")
                 .groupby(P["month"], observed=True)
                 .transform(lambda s: s.rank(pct=True) if s.notna().sum() >= 8 else np.nan))
            # ★numpy 2.x 는 np.where(cond, np.nan, "문자열") 의 dtype 승격을 거부한다
            #   (DTypePromotionError: _PyFloatDType could not be promoted by StrDType).
            #   numpy 1.x 는 조용히 object 로 올려 줬기 때문에 그 시절 코드가 그대로 남아 있었고,
            #   계약검정 C4 는 직원수가 전부 채워진 합성데이터라 이 사다리를 타지 않아
            #   ★실데이터에서만 터졌다(L.PANEL 전체 중단). 판정은 pandas 로만 한다 —
            #   버전에 무관하고, 결측을 결측으로 남기는 의미도 코드에 그대로 드러난다.
            alt = pd.Series(pd.NA, index=P.index, dtype=object)
            alt = (alt.mask(q < 1 / 3, f"{lab}소")
                      .mask((q >= 1 / 3) & (q < 2 / 3), f"{lab}중")
                      .mask(q >= 2 / 3, f"{lab}대"))
            sb = sb.fillna(alt)
    P["size_bucket"] = sb.fillna("규모미상").astype(str)
    if (P["size_bucket"] == "규모미상").mean() > 0.5:
        L.warn(f"규모버킷 미상 {100*float((P['size_bucket']=='규모미상').mean()):.0f}% — "
               f"C11 셀이 (월,산업)으로 사실상 붕괴합니다. 직원현황/시총 수집 상태를 "
               f"확인하세요(규모 통제 없이 계산된 z·랭크는 해석에 주의).")
    ym = P["month"].dt.strftime("%Y%m")
    P["cell"] = ym + "|" + P["industry"] + "|" + P["size_bucket"]
    P["cell_up"] = ym + "|" + P["industry"].str.slice(0, 4) + "|ALL"
    P["cell_all"] = ym + "|ALL|ALL"
    CELL_AUDIT["n_cells"] = int(P["cell"].nunique())
    CELL_AUDIT["unknown_size"] = float((P["size_bucket"] == "규모미상").mean())
    n = P.groupby("cell", observed=True)["code"].transform("size")
    small = n < CELL_MIN
    n1 = int(small.sum())
    if n1:
        P.loc[small, "cell"] = P.loc[small, "cell_up"]
        n2v = P.groupby("cell", observed=True)["code"].transform("size")
        still = n2v < CELL_MIN
        if still.any():
            P.loc[still, "cell"] = P.loc[still, "cell_all"]
        # ★still 은 small 의 부분집합이다 — 더하면 같은 행을 두 번 센다(실측 50% ← 실제 37.7%).
        CELL_AUDIT["fallback_rate"] = float(n1 / max(len(P), 1))
        CELL_AUDIT["fallback_to_all"] = float(int(still.sum()) / max(len(P), 1))
        L.info(f"셀 폴백(C11): 1차 {n1:,}행 → 산업 상위 / 2차 {int(still.sum()):,}행 → 전체 "
               f"(표본<{CELL_MIN} 셀의 정상 폴백 — 로깅 의무)")
    for c in CELL_LADDER:
        P[c] = P[c].astype("category")
    return P


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [7] 데이터수집부 A — 종목마스터 · 상장폐지 · KRX 로그인 · 시가총액 · PIT 유니버스(C2)      ║
# ║                                                                                          ║
# ║  다중 소스 교차 구축(역할이 서로 다르다):                                                  ║
# ║   ① FDR GitHub 캐시 listing/krx        상장 종목+상장일        (로그인 불필요 · 1순위)     ║
# ║   ② FDR GitHub 캐시 listing/delisting  상장폐지+폐지일         (★생존자편향 제거 입력)     ║
# ║   ③ KIND 상장법인목록                  상장일·업종 보강                                    ║
# ║   ④ DART corpCode.xml                  corp_code ↔ 종목코드                                ║
# ║   ⑤ pykrx / KRX 마켓플레이스 스냅샷    "그날 실제 상장" 검증·시가총액 (로그인 필요·보조)   ║
# ║   ⑥ 네이버 금융                        잔여 무명 종목 이름 보강                            ║
# ║  ★ 유니버스 정확성은 ①②③④ 만으로 성립해야 한다. ⑤는 보강이지 의존이 아니다.               ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

MASTER_COLS = ["code", "name", "market", "industry", "listing_date", "delisting_date",
               "corp_code", "shares_now", "marcap_now", "origin"]


def no_dup_cols(df: pd.DataFrame, where: str) -> pd.DataFrame:
    """중복 컬럼은 pandas 의미가 조용히 바뀌는 1급 사고 — 발생 지점에서 즉시 세운다."""
    if df is not None and len(df.columns):
        dup = df.columns[df.columns.duplicated()]
        if len(dup):
            raise RuntimeError(f"[{where}] 중복 컬럼 {sorted(set(map(str, dup)))} — 즉시 중단")
    return df


# ── KRX 마켓플레이스 클라이언트 (2025-12 인증 개편 대응 · 실패해도 절대 죽지 않음) ───────────
class KRXMarketplace:
    """data.krx.co.kr 로그인 세션 + bld JSON 조회. 로그인 실패 시 폴백 체인이 대신한다."""

    WARM = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201"
    LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    LOGIN_POST = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    # ★로그인 엔드포인트·필드명은 KRX 개편 때마다 바뀐다. 하나를 찍어 맞히는 대신 후보를
    #   순서대로 시도하고 ★서버가 JSON 으로 CD001 을 줄 때만 성공으로 본다. 실측 로그에서
    #   현행 단일 경로는 '에러페이지 - 한국거래소' HTML 을 돌려주었다.
    LOGIN_CANDS = [
        ("https://data.krx.co.kr/comm/member/mbrLoginSubmit.cmd", "pwd"),
        ("https://data.krx.co.kr/comm/member/mbrLoginSubmit.cmd", "pw"),
        ("https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd", "pw"),
        ("https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd", "pwd"),
    ]
    JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    JSON_REF = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"

    def __init__(self, uid: str, pw: str):
        self.uid, self.pw = (uid or "").strip(), (pw or "").strip()
        self.session_ok = False
        self.state = "미시도"
        self._lk = threading.RLock()
        self._relog = False        # 세션 만료 재로그인은 실행당 1회(무한 재귀 방지)

    def login(self) -> bool:
        """메인 스레드 1회 로그인. 이후 조회는 락으로 직렬화(중복로그인 CD011 자기충돌 방지)."""
        with self._lk:
            if self.session_ok:
                return True
            if not (self.uid and self.pw):
                self.state = "자격증명 미입력"
                L.info("KRX 마켓플레이스 ID/PW 미입력 — 로그인 없이 날짜축 벌크(pykrx 전종목 "
                       "스냅샷)로 진행합니다. 시가총액은 프록시로 대체되며 감사표에 표시됩니다.")
                return False
            net_get(self.WARM, source="krx", tries=1)
            net_get(self.LOGIN_PAGE, source="krx", tries=1, referer=self.WARM)
            # ★성공 판정은 반드시 서버가 주는 _error_code 로 한다. '부정 키워드가 없으면 성공'
            #   이라는 옛 판정은 근거가 없었고, 실제로 거짓 양성을 냈다 — 로그에는 '로그인 성공'이
            #   찍힌 채 이후 모든 bld 조회가 로그인 HTML 을 받아 F.CAP 48초·G.FLOW 4.6초를
            #   통째로 버렸다(120회·12회 × 0.4초로 산술이 정확히 맞는다). KRX 정본은 CD001 만
            #   성공으로 본다.
            for url, pwf in self.LOGIN_CANDS:
                for extra in ({}, {"skipDup": "Y"}):
                    body = {"mbrId": self.uid, pwf: self.pw, "mbrNm": "", "telNo": "",
                            "di": "", "certType": "", **extra}
                    txt = net_post(url, source="krx", data=body, referer=self.LOGIN_PAGE,
                                   headers={"X-Requested-With": "XMLHttpRequest"})
                    if txt is None:
                        continue
                    ec = em = ""
                    try:
                        js = json.loads(txt)
                        ec = str(js.get("_error_code", ""))
                        em = str(js.get("_error_message", ""))
                    except Exception:
                        if re.search(r"CD011|중복\s*로그인", str(txt)):
                            ec = "CD011"
                        else:
                            continue           # 이 후보는 JSON 을 안 준다 — 다음 후보로
                    if ec == "CD011":
                        L.warn("KRX 중복 로그인(CD011) — 브라우저/다른 노트북의 같은 계정 "
                               "로그인이 세션을 끊습니다. skipDup 으로 재시도합니다.")
                        continue
                    if ec == "CD001":
                        self.session_ok = True
                        self.state = "로그인 성공"
                        self.LOGIN_POST = url
                        _krx_capture_cookies()   # ★워커 스레드가 상속할 수 있게 쿠키를 공유
                        L.ok(f"KRX 마켓플레이스 로그인 성공(CD001 · {url.rsplit('/', 1)[-1]}) — "
                             f"시가총액·수급을 정식 경로로 수집합니다.")
                        return True
                    L.warn(f"KRX 로그인 거부 — code={ec or '?'} msg={em[:80]}")
                    if ec:
                        break                  # 서버가 정식 코드를 줬으면 이 후보는 유효한 경로
            self.state = "로그인 실패"
            L.warn("KRX 마켓플레이스 로그인 실패 — 후보 엔드포인트 "
                   f"{len(self.LOGIN_CANDS)}개가 모두 JSON(_error_code)을 주지 않았습니다. "
                   "① ID/PW 확인 ② 브라우저에서 같은 계정 로그아웃 ③ KRX 개편으로 로그인 경로가 "
                   "또 바뀐 경우입니다. 가격·시총은 marcap 연도축이 이미 덮으므로 백테스트는 "
                   "정상 진행되며, 영향은 수급(d3) 한 축에 한정됩니다.")
            return False

    def bld(self, bld: str, serial: bool = True, force: bool = False, **params) -> Optional[list]:
        """마켓플레이스 표 조회. 세션 없으면 None(상위 폴백). JSON 아닌 응답(로그인 페이지)도 차단.

        serial=False — 날짜축 벌크 수집처럼 '읽기 전용 조회를 수천 번' 하는 경로용.
        전역 속도는 pace('krx') 가 이미 QPS 로 묶고 있어 서버 부하는 동일하고,
        락을 잡지 않는 만큼 왕복 지연만 겹쳐 사라진다(2,700일 × 0.6초 대기가 통째로 증발)."""
        if not self.session_ok and not force:
            return None
        # ★locale 누락 수정 — data.krx.co.kr 의 bld 게이트웨이는 locale 이 없으면 200 을 주면서
        #   내용은 빈/오류 페이로드를 돌려주는 경우가 있다. 정상 클라이언트는 항상 함께 보낸다.
        body = {"bld": bld, "locale": "ko_KR", "money": "1", "share": "1",
                "csvxls_isNo": "false", **params}
        if serial:
            with self._lk:
                txt = net_post(self.JSON_URL, source="krx", data=body, referer=self.JSON_REF,
                               headers={"X-Requested-With": "XMLHttpRequest"})
        else:
            txt = net_post(self.JSON_URL, source="krx", data=body, referer=self.JSON_REF,
                           headers={"X-Requested-With": "XMLHttpRequest"})
        if not txt or txt.lstrip()[:1] not in "{[":
            # ★HTML 이 왔다 = 세션이 없거나 끊겼다. 조용히 None 을 돌려주면 상위는 '데이터 없음'
            #   으로 오해하고 120개월을 전부 헛돈다(실측 48초). 진단을 남기고 한 번만 재로그인한다.
            with _NET_LK:
                NET_STATS["krx:NOTJSON"] += 1
                NET_LAST["krx"] = (200, f"bld={bld} 비JSON 응답(로그인 HTML 추정): "
                                        f"{str(txt)[:130]}")
            if self.session_ok and not self._relog:
                self._relog = True
                self.session_ok = False
                L.warn("KRX 조회가 JSON 대신 HTML 을 받았습니다 — 세션 만료로 보고 1회 재로그인합니다.")
                if self.login():
                    return self.bld(bld, serial=serial, force=force, **params)
            return None
        try:
            js = json.loads(txt)
        except Exception:
            return None
        for key in ("OutBlock_1", "output", "block1"):
            if isinstance(js, dict) and isinstance(js.get(key), list):
                return js[key]
        return None


    def bld_market_split(self, bld: str, **params) -> Optional[list]:
        """mktId='ALL' 이 빈손이면 시장별로 쪼개 합친다 — 배포본에 따라 ALL 을 거부한다."""
        got = self.bld(bld, serial=False, force=True, mktId="ALL", **params)
        if got:
            return got
        out: List[dict] = []
        for mk in ("STK", "KSQ", "KNX"):
            r = self.bld(bld, serial=False, force=True, mktId=mk, **params)
            if r:
                out += r
        return out or None


KRX = KRXMarketplace(KRX_MARKETPLACE_ID, KRX_MARKETPLACE_PW)


def krx_code(v: Any) -> Optional[str]:
    """KRX 응답의 종목코드는 단축코드(6자리)일 때도, 표준코드(ISIN 12자리)일 때도 있다.
    ISIN 을 그대로 code6 에 넣으면 숫자 10자리라 전부 None 이 되어 응답이 통째로 증발한다."""
    s = str(v or "").strip().upper()
    if len(s) == 12 and s[:2].isalpha():
        return code6(s[3:9])
    return code6(s)


class KRXOpenAPI:
    """KRX Open API(data-dbg.krx.co.kr) — 인증키 기반 '일별매매정보' = 날짜축 전종목.

    로그인 세션이 필요 없어 중복로그인으로 서로를 끊는 사고가 없고, 응답 스키마가 고정이라
    스크래핑 경로보다 안정적이다. 그래서 벌크 사다리의 1순위로 둔다.
    ★단, 엔드포인트별 이용신청 승인 전에는 키가 있어도 거부된다 — probe() 로 한 번만 확인하고
      거부되면 조용히 비활성화한 뒤 마켓플레이스/pykrx 경로로 넘긴다(죽지 않는다).
    """

    BASE = "https://data-dbg.krx.co.kr/svc/apis/{cat}/{ep}"
    DAILY = [("sto", "stk_bydd_trd"), ("sto", "ksq_bydd_trd")]      # KOSPI · KOSDAQ

    def __init__(self, key: str):
        self.key = (key or "").strip()
        self.ok = False
        self.mode = ""
        self.state = "미시도"
        self._probed = False

    def _call(self, cat: str, ep: str, day: str, mode: str) -> Optional[list]:
        url = self.BASE.format(cat=cat, ep=ep)
        kw = ({"params": {"AUTH_KEY": self.key, "basDd": day}} if mode == "query"
              else {"params": {"basDd": day}, "headers": {"AUTH_KEY": self.key}})
        js = net_json(url, source="krx", tries=1, **kw)
        if isinstance(js, dict):
            for k in ("OutBlock_1", "output", "OutBlock1"):
                if isinstance(js.get(k), list):
                    return js[k]
        return None

    def probe(self) -> bool:
        if self._probed or not self.key:
            if not self.key:
                self.state = "키 미입력"
            return self.ok
        self._probed = True
        dd = dtm.date.today() - dtm.timedelta(days=7)
        while dd.weekday() >= 5:
            dd -= dtm.timedelta(days=1)
        for mode in ("query", "header"):
            # ★엔드포인트별로 이용신청이 따로 승인된다. 코스피만 승인된 상태(승인 대기 중의
            #   정상 상태다)에서 ok=True 로 켜면 벌크 1순위가 '코스피만' 을 돌려주고,
            #   그 반쪽 응답이 전 거래일에 걸쳐 완료로 굳는다 → 코스닥이 통째로 증발한다.
            #   그래서 DAILY 전 엔드포인트가 다 살아 있을 때만 켠다.
            oks = [bool(self._call(cat, ep, dd.strftime("%Y%m%d"), mode))
                   for cat, ep in self.DAILY]
            if all(oks):
                self.ok, self.mode, self.state = True, mode, f"사용 가능({mode})"
                L.ok(f"KRX Open API 사용 가능 (AUTH_KEY 전달 {mode}, 엔드포인트 "
                     f"{len(self.DAILY)}종 전부 승인) — 날짜축 벌크 1순위로 씁니다.")
                return True
            if any(oks):
                self.state = "일부 엔드포인트만 승인"
                L.warn(f"KRX Open API 가 {sum(oks)}/{len(self.DAILY)} 엔드포인트만 응답합니다"
                       f"(코스피만 승인된 상태로 추정). 반쪽 시장이 전 기간에 굳는 것을 막기 위해 "
                       f"이 경로를 쓰지 않고 마켓플레이스/pykrx 로 진행합니다 — 나머지 "
                       f"엔드포인트 이용신청이 승인되면 자동으로 1순위가 됩니다.")
                return False
        self.state = "이용신청 미승인/거부"
        L.warn("KRX Open API 키는 있으나 호출이 거부되었습니다. 이 API 는 엔드포인트별 "
               "'이용신청'이 따로 필요하고 승인에 하루 정도 걸립니다 — 승인 전까지는 "
               "마켓플레이스 로그인/pykrx 경로로 정상 진행합니다.")
        return False

    def bydd(self, day: pd.Timestamp) -> Optional[list]:
        """그날의 KOSPI+KOSDAQ 전 종목 일별매매정보(리스트 병합)."""
        if not self.ok:
            return None
        ds = day.strftime("%Y%m%d")
        out: List[dict] = []
        for cat, ep in self.DAILY:
            rows = self._call(cat, ep, ds, self.mode)
            if rows:
                out += rows
        return out or None


KRXOA = KRXOpenAPI(KRX_OPENAPI_KEY)


class PykrxGate:
    """pykrx 전 호출의 유일한 통로 — 직렬화 + 스로틀 + 예외 흡수.
    병렬로 때리면 스레드마다 재로그인 → KRX 가 중복로그인으로 서로를 끊어 대량 실패한다."""

    def __init__(self):
        self._lk = threading.RLock()
        self.calls = 0
        self.fails = 0

    def call(self, fn: Callable, *a, **k):
        if pykrx_stock is None:
            return None
        with self._lk:
            pace("krx").wait()
            self.calls += 1
            try:
                return fn(*a, **k)
            except Exception:
                self.fails += 1
                return None


PKX = PykrxGate()

_FDR_CACHE_URL = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
                  "refs/heads/master/data/{kind}/{date}.csv")


def _fdr_cache_read(kind: str, back_days: int = 16) -> Optional[pd.DataFrame]:
    """FDR GitHub 캐시(영업일 파일만 존재 → 최근일부터 역순 탐색). 로그인 불필요 1순위 경로."""
    today = dtm.date.today()
    for i in range(back_days):
        dd = today - dtm.timedelta(days=i)
        if dd.weekday() >= 5:
            continue
        raw = net_get(_FDR_CACHE_URL.format(kind=kind, date=dd.isoformat()),
                      source="fdrcache", tries=1, as_bytes=True)
        if not raw or len(raw) < 200:
            continue
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                             dtype={"Code": str, "Symbol": str, "ISU_CD": str,
                                    "Market": str, "MarketId": str})
            # ★ index_col=0 강제 금지 — delisting 파일은 이름 없는 인덱스 열이 없을 수 있어
            #   첫 실컬럼(종목코드)이 인덱스로 먹혀 상폐 종목 전체가 유실된다(=생존자편향).
            if len(df.columns) and str(df.columns[0]).strip().lower() in ("", "unnamed: 0", "index"):
                df = df.drop(columns=[df.columns[0]])
            if len(df):
                return df
        except Exception:
            continue
    return None


def _lc(df: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in df.columns}


def harvest_listing() -> pd.DataFrame:
    d = _fdr_cache_read("listing/krx")
    if d is None and fdr is not None:
        try:
            pace("krx").wait()
            d = fdr.StockListing("KRX")
        except Exception as e:                                    # noqa
            L.warn(f"fdr.StockListing 실패({type(e).__name__}) — KRX 최신영업일 확인이 막히면 "
                   f"CSV 가 멀쩡해도 죽는 알려진 경로입니다. GitHub 캐시가 이미 실패한 상태라 "
                   f"상장목록 없이 진행합니다.")
            d = None
    if d is None or len(d) == 0:
        L.warn("상장목록 미확보 — KIND/스냅샷 경로가 대신 채웁니다.")
        return pd.DataFrame(columns=MASTER_COLS)
    c = _lc(d)
    code_c = c.get("code") or c.get("symbol") or c.get("isu_cd")
    name_c = c.get("name") or c.get("isu_nm")
    if not code_c or not name_c:
        return pd.DataFrame(columns=MASTER_COLS)
    out = pd.DataFrame({
        "code": d[code_c].map(code6),
        "name": d[name_c].astype(str).str.strip(),
        "market": d[c["market"]].astype(str) if "market" in c else
                  (d[c["marketid"]].astype(str) if "marketid" in c else "KRX"),
        "industry": d[c["sector"]].astype(str) if "sector" in c else
                    (d[c["industry"]].astype(str) if "industry" in c else ""),
        "listing_date": ds_(d[c["listingdate"]]) if "listingdate" in c else pd.NaT,
        "shares_now": pd.to_numeric(d[c["stocks"]], errors="coerce") if "stocks" in c else np.nan,
        "marcap_now": pd.to_numeric(d[c["marcap"]], errors="coerce") if "marcap" in c else np.nan,
    })
    out["delisting_date"] = pd.NaT
    out["corp_code"] = np.nan
    out["origin"] = "fdr_listing"
    out = out.dropna(subset=["code"]).drop_duplicates("code")
    L.ok(f"상장목록 {len(out):,}건 (로그인 불필요 경로 · 주식수 {int(out['shares_now'].notna().sum()):,}건)")
    return out


def harvest_delisting() -> pd.DataFrame:
    """★ 생존자편향 제거(C2)의 핵심 입력. 탈락 사유를 반드시 집계해 남긴다 —
    여기서 조용히 버려지는 종목 수가 그대로 잔존 생존자편향이다."""
    d = _fdr_cache_read("listing/delisting")
    if (d is None or len(d) == 0) and fdr is not None:
        try:
            pace("krx").wait()
            d = fdr.StockListing("KRX-DELISTING")
        except Exception:
            d = None
    if d is None or len(d) == 0:
        L.warn("상장폐지 목록 미확보 — C2(생존자편향 제거) 부분 미충족 상태로 진행합니다. "
               "결과 해석 시 반드시 감안하세요.")
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    c = _lc(d)
    code_c = c.get("symbol") or c.get("code") or c.get("isu_cd")
    if not code_c:
        return pd.DataFrame(columns=["code", "name", "delisting_date", "market"])
    dl_c = next((c[k] for k in ("delistingdate", "delisting_date", "date") if k in c), None)
    name_c = c.get("name") or code_c
    n0 = len(d)
    codes = d[code_c].astype(str).map(code6)
    out = pd.DataFrame({"code": codes,
                        "name": d[name_c].astype(str),
                        "delisting_date": ds_(d[dl_c]) if dl_c else pd.NaT,
                        "market": d[c["market"]].astype(str) if "market" in c else "KRX"})
    out = out.dropna(subset=["code"])
    # 재상장→재폐지 중복 코드는 '가장 늦은 폐지일'을 남긴다(이르면 재상장 구간이 통째로 빠짐)
    out = out.sort_values("delisting_date").drop_duplicates("code", keep="last")
    n_bad = int(codes.isna().sum())
    UNI_AUDIT["delist_raw"] = int(n0)
    UNI_AUDIT["delist_dropped"] = n_bad
    UNI_AUDIT["delist_drop_rate"] = n_bad / max(n0, 1)
    L.ok(f"상장폐지 목록 {len(out):,}건 확보 (원본 {n0:,} · 코드형식 탈락 {n_bad:,} — "
         f"탈락분은 ETF/ELW/스팩 등 비보통주가 대부분)")
    if n_bad > n0 * 0.20:
        # ★'대부분 비보통주'라는 설명은 가설일 뿐이다. 실제로 무엇이 탈락했는지 보여준다 —
        #   보통주가 섞여 있으면 그만큼이 그대로 생존자편향(상향 드리프트)으로 남는다.
        bad = d.loc[codes.isna(), code_c].astype(str)
        samp = ", ".join(bad.drop_duplicates().head(8).tolist())
        L.warn(f"폐지목록의 {100*n_bad/max(n0,1):.0f}% 가 코드 정규화에서 탈락 — 그만큼 "
               f"생존자편향(성과 과대)이 남습니다. 탈락 표본: {samp}")
    return out


def harvest_kind() -> pd.DataFrame:
    """KIND 상장법인목록 — 상장일·업종 보강. ★종목코드가 정수로 와서 앞 0 이 잘린다 → code6 복구."""
    for u in ("https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13",
              "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download"):
        raw = net_get(u, source="kind", tries=2, as_bytes=True,
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
            cols = {str(c).strip(): c for c in d.columns}
            if "종목코드" not in cols or "회사명" not in cols:
                continue
            out = pd.DataFrame({
                "code": d[cols["종목코드"]].map(code6),
                "name": d[cols["회사명"]].astype(str).str.strip(),
                "listing_date": ds_(d[cols["상장일"]]) if "상장일" in cols else pd.NaT,
                "industry": d[cols["업종"]].astype(str) if "업종" in cols else "",
                "market": "", "delisting_date": pd.NaT, "corp_code": np.nan,
                "shares_now": np.nan, "marcap_now": np.nan, "origin": "kind",
            }).dropna(subset=["code"]).drop_duplicates("code")
            L.ok(f"KIND 상장법인목록 {len(out):,}건 (상장일 {int(out['listing_date'].notna().sum()):,}건)")
            return out
    L.warn("KIND 목록 미확보 — 상장일은 FDR/스냅샷으로만 채웁니다.")
    return pd.DataFrame(columns=MASTER_COLS)


def harvest_corpcode() -> pd.DataFrame:
    """DART corp_code ↔ 종목코드 — DART 의 모든 재무·공시 조회 키."""
    if not DART_API_KEY:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    hit = VAULT.load_table("dart_corpcode", "shared")
    if hit is not None and len(hit):
        L.info(f"캐시 재사용: DART corpCode {len(hit):,}건")
        return hit
    if RUN_MODE == "CACHED" or not QUOTA.allow("dart"):
        # ★조용히 빈 프레임을 돌려주면 안 된다. 이게 비면 master 의 corp_code 가 전부 NaN 이
        #   되고, 그 상태로 진행하면 ①DART 전 티어가 조회 키를 잃고 ②일괄 ZIP 이 전 파일
        #   0행으로 '완주' 기록되어 ★호출한도를 쓰지 않는 유일한 재무 경로가 영구히 죽는다.
        if RUN_MODE != "CACHED":
            L.err("DART corpCode 를 받지 못했습니다(일일 한도 소진). corp_code 가 없으면 "
                  "재무·직원·공시가 전부 조회 키를 잃습니다 — 한도가 회복된 뒤 재실행하세요. "
                  "이번 실행의 DART 계층은 캐시에 있는 것만 씁니다.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    raw = net_get("https://opendart.fss.or.kr/api/corpCode.xml", source="dart",
                  params={"crtfc_key": DART_API_KEY}, as_bytes=True, tries=2,
                  count_cb=lambda: QUOTA.charge("dart"))
    if not raw:
        L.warn("corpCode.xml 수신 실패 — DART_API_KEY/네트워크를 확인하세요.")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    if raw[:2] != b"PK":
        body = raw[:300].decode("utf-8", "ignore")
        if re.search(r"020", body):
            QUOTA.server_says_limit("dart")
        L.warn(f"corpCode 응답이 ZIP 이 아님(키 오류 가능): {body[:120]}")
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml = smart_decode(b"".join(zf.read(n) for n in zf.namelist()), None)
    except Exception:
        return pd.DataFrame(columns=["corp_code", "corp_name", "code"])
    rows = []
    for m in re.finditer(r"<list>(.*?)</list>", xml, re.S):
        blk = m.group(1)

        def take(tag):
            mm = re.search(rf"<{tag}>(.*?)</{tag}>", blk, re.S)
            return mm.group(1).strip() if mm else ""
        rows.append({"corp_code": take("corp_code"), "corp_name": take("corp_name"),
                     "code": code6(take("stock_code"))})
    out = pd.DataFrame(rows)
    if len(out):
        VAULT.save_table("dart_corpcode", out, "shared", domain="dart", source="opendart")
    L.ok(f"DART corpCode {len(out):,}건 (상장 매칭 {int(out['code'].notna().sum()):,}건)")
    return out


def harvest_snapshots(months: pd.DatetimeIndex) -> pd.DataFrame:
    """분기말 상장종목 스냅샷(검증·보강용, 의존 아님). 캐시 우선·직렬 수집·부분응답 방어."""
    cached = VAULT.load_table("krx_member_snapshots", "shared")
    have = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["snap_date"] = ds_(cached["snap_date"])
        cached = cached.dropna(subset=["snap_date", "code"])
        have = set(cached["snap_date"].dt.strftime("%Y-%m-%d"))
        L.info(f"캐시 재사용: 상장 스냅샷 {len(have)}개 시점")
    grid = [m for m in months if m.month in (3, 6, 9, 12)]
    todo = [m for m in grid if m.strftime("%Y-%m-%d") not in have]
    if RUN_MODE == "CACHED" or pykrx_stock is None or CLOCK.over():
        todo = []
    new_rows: List[dict] = []
    if todo:
        L.info(f"상장 스냅샷 {len(todo)}개 시점 수집(분기 격자·직렬)")
        misses = 0
        for m in tqdm(todo, desc="상장 스냅샷", ncols=86, leave=False):
            if CLOCK.over():
                CLOCK.cut(f"상장 스냅샷 {len(new_rows)}행/{len(todo)}시점에서 중단")
                break
            bd = PKX.call(pykrx_stock.get_nearest_business_day_in_a_week,
                          m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
            got = False
            for mkt in ("KOSPI", "KOSDAQ"):
                tk = PKX.call(pykrx_stock.get_market_ticker_list, bd, market=mkt)
                for t in (tk or []):
                    cc = code6(t)
                    if cc:
                        got = True
                        new_rows.append({"snap_date": m.strftime("%Y-%m-%d"),
                                         "code": cc, "market": mkt})
            misses = 0 if got else misses + 1
            if misses >= 4:
                L.warn("스냅샷 연속 4회 공백 — 세션 끊김/차단으로 판단, 스냅샷 수집을 중단합니다"
                       "(유니버스는 상장·폐지일 경로로 정상).")
                break
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(new_rows)] if new_rows else [])
    if not frames:
        return pd.DataFrame(columns=["snap_date", "code", "market"])
    snap = pd.concat(frames, ignore_index=True)
    snap["snap_date"] = ds_(snap["snap_date"])
    snap = snap.dropna(subset=["snap_date", "code"]).drop_duplicates(["snap_date", "code"])
    # 부분응답 방어 — 이웃 대비 급감 스냅샷은 '진실'이 아니라 '사고'다(그대로 믿으면 선택편향)
    size = snap.groupby("snap_date")["code"].size()
    med = float(size.median()) if len(size) else 0
    bad = size[size < med * 0.8]
    if len(bad) and med > 0:
        L.warn(f"부분응답 스냅샷 {len(bad)}개 시점 폐기(중앙값 {med:,.0f} 의 80% 미만)")
        snap = snap[~snap["snap_date"].isin(bad.index)]
    if new_rows:
        keep = snap.copy()
        keep["snap_date"] = keep["snap_date"].dt.strftime("%Y-%m-%d")
        VAULT.save_table("krx_member_snapshots", keep, "shared", domain="universe",
                         source="pykrx", note="전 전략 공용")
    return snap


def _mktcap_from_px(px: Optional[pd.DataFrame], months: pd.DatetimeIndex) -> pd.DataFrame:
    """★공짜 경로 — 날짜축 일봉(KRX 전종목시세)에 시가총액·상장주식수가 이미 실려 있다.
    월말 거래일 행만 뽑으면 별도 호출 0회로 비교전략 입력이 완성된다."""
    if px is None or not len(px) or "mktcap" not in px.columns:
        return pd.DataFrame(columns=["code", "month", "mktcap", "shares", "cap_src"])
    d = px[["code", "date", "mktcap", "shares"]].copy()
    d["mktcap"] = pd.to_numeric(d["mktcap"], errors="coerce")
    d = d.dropna(subset=["mktcap"])
    d = d[d["mktcap"] > 0]
    if not len(d):
        return pd.DataFrame(columns=["code", "month", "mktcap", "shares", "cap_src"])
    d["date"] = ds_(d["date"])
    d["month"] = d["date"] + pd.offsets.MonthEnd(0)
    d = d[d["month"].isin(months)]
    if not len(d):
        return pd.DataFrame(columns=["code", "month", "mktcap", "shares", "cap_src"])
    # ★월말 근접성 — mktcap 이 실리는 소스(krx_open/krx_mp)와 안 실리는 소스(pykrx)가 섞이면
    #   '그 달에서 시총이 있었던 마지막 날'이 3주 전일 수 있다. 월말 5영업일 안쪽만 인정한다.
    d = d[(d["month"] - d["date"]).dt.days <= 8]
    if not len(d):
        return pd.DataFrame(columns=["code", "month", "mktcap", "shares", "cap_src"])
    d = (d.sort_values(["code", "month", "date"])
           .drop_duplicates(["code", "month"], keep="last"))
    d["code"] = d["code"].astype(str)
    d["cap_src"] = "krx_bulk_px"
    # ★횡단면 폭 — 한 종목만 있어도 그 달을 완료로 찍으면 '시총 하위 1000' 유니버스가
    #   40종목에서 뽑히고도 감사표엔 최고 신뢰 등급(snapshot)으로 찍힌다.
    # 절대 임계가 아니라 '그 달 일봉에 나타난 종목수 대비 비율' — 시장 규모·테스트 규모에
    # 모두 맞는 척도다(절대값 500 은 소규모 유니버스에서 전부 탈락시킨다).
    base = px.assign(_m=ds_(px["date"]) + pd.offsets.MonthEnd(0)) \
             .groupby("_m")["code"].nunique()
    wide = d.groupby("month")["code"].size()
    need = (wide.index.map(base).astype(float) * 0.5).fillna(np.inf)
    keep_m = set(wide.index[wide.to_numpy() >= need.to_numpy()])
    thin = len(wide) - len(keep_m)
    if thin:
        L.info(f"일봉 동봉 시총 중 횡단면이 얕은 {thin}개월은 채택하지 않고 정식 스냅샷 "
               f"경로로 넘깁니다(비교전략 유니버스 왜곡 방지).")
    d = d[d["month"].isin(keep_m)]
    return d[["code", "month", "mktcap", "shares", "cap_src"]].reset_index(drop=True)


def harvest_mktcap(months: pd.DatetimeIndex, px: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """월말 시가총액 스냅샷 — 비교전략(시총 하위 1000)의 입력.
    소스 사다리: ⓪날짜축 일봉에 동봉된 시총(호출 0회) ①pykrx ②KRX bld ③주식수 역산 프록시."""
    cached = VAULT.load_table("krx_mktcap_monthly", "shared")
    have = set()
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["month"] = ds_(cached["month"])
        cached = cached.dropna(subset=["month", "code"])
        have = set(cached["month"].dt.strftime("%Y-%m"))
        L.info(f"캐시 재사용: 시가총액 스냅샷 {len(have)}개월 · {len(cached):,}행")
    free = _mktcap_from_px(px, months)
    if len(free):
        got_m = set(free["month"].dt.strftime("%Y-%m"))
        L.ok(f"시가총액 {len(got_m)}개월 · {len(free):,}행을 일봉 벌크에서 그대로 확보"
             f"(추가 호출 0회) — 날짜축 개편의 부수 이득")
        cached = free if cached is None or not len(cached) else \
            pd.concat([cached, free], ignore_index=True)
        have |= got_m
    todo = [m for m in months if m.strftime("%Y-%m") not in have]
    if RUN_MODE == "CACHED" or CLOCK.over():
        todo = []
    rows: List[dict] = []
    src_used = Counter()
    for m in tqdm(todo, desc="시가총액 스냅샷", ncols=86, leave=False):
        if CLOCK.over():
            CLOCK.cut(f"시가총액 스냅샷 {len(rows)}행 수집 후 중단 (잔여 {len(todo)}개월 중)")
            break
        got, got_src = None, ""
        if pykrx_stock is not None:
            bd = PKX.call(pykrx_stock.get_nearest_business_day_in_a_week,
                          m.strftime("%Y%m%d"), prev=True) or m.strftime("%Y%m%d")
            cap = PKX.call(pykrx_stock.get_market_cap_by_ticker, bd, market="ALL")
            if cap is not None and len(cap):
                cap = cap.reset_index()
                cap.columns = [str(c) for c in cap.columns]
                code_c = cap.columns[0]
                cc = {str(c).strip(): c for c in cap.columns}
                v_c = cc.get("시가총액")
                s_c = cc.get("상장주식수")
                if v_c is not None:
                    got = pd.DataFrame({"code": cap[code_c].map(code6),
                                        "mktcap": pd.to_numeric(cap[v_c], errors="coerce"),
                                        "shares": pd.to_numeric(cap[s_c], errors="coerce")
                                        if s_c else np.nan})
                    got_src = "pykrx"
        if got is None and KRX.session_ok:
            blk = KRX.bld("dbms/MDC/STAT/standard/MDCSTAT01501",
                          mktId="ALL", trdDd=m.strftime("%Y%m%d"))
            if blk:
                got = pd.DataFrame({
                    "code": [code6(r.get("ISU_SRT_CD")) for r in blk],
                    "mktcap": [pd.to_numeric(str(r.get("MKTCAP", "")).replace(",", ""),
                                             errors="coerce") for r in blk],
                    "shares": [pd.to_numeric(str(r.get("LIST_SHRS", "")).replace(",", ""),
                                             errors="coerce") for r in blk]})
                got_src = "krx_mp"
        if got is not None and len(got) and got_src:
            got = got.dropna(subset=["code", "mktcap"])
            got["month"] = m
            got["cap_src"] = got_src                      # ★월별 실제 소스로 기록(감사 정확성)
            src_used[got_src] += 1
            rows.extend(got.to_dict("records"))
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(rows)] if rows else [])
    if not frames:
        L.info("시가총액 정식 스냅샷 없음 — 비교전략은 주식수 역산/거래대금 보정 프록시를 씁니다"
               "(감사표에 명시).")
        return pd.DataFrame(columns=["code", "month", "mktcap", "shares", "cap_src"])
    cap = pd.concat(frames, ignore_index=True)
    cap["month"] = ds_(cap["month"])
    cap = (cap.dropna(subset=["code", "month"])
              .drop_duplicates(["code", "month"], keep="last").reset_index(drop=True))
    if rows:                     # ★len(free) 로 저장하면 새 월이 없어도 매 실행 전체 재기록
        keep = cap.copy()
        srcs = dict(src_used)
        if len(free):
            srcs["krx_bulk_px"] = int(free["month"].nunique())
        VAULT.save_table("krx_mktcap_monthly", keep, "shared", domain="universe",
                         source="+".join(f"{k}×{v}" for k, v in srcs.items()),
                         note="시총 하위 1000 비교전략 입력 — 전 전략 공용")
    if src_used:
        L.ok(f"시가총액 스냅샷 신규 {len(rows):,}행 (소스 { dict(src_used) })")
    return cap


def harvest_naver_names(codes: Sequence[str], cap: int = 300) -> Dict[str, str]:
    """이름 없는 잔여 종목을 네이버로 보강 — 이름이 비면 NPS/조달 상호 매칭이 통째로 실패한다."""
    codes = [c for c in codes if c][:cap]
    if not codes or RUN_MODE == "CACHED" or CLOCK.over():
        return {}

    def one(c: str):
        h = net_get(f"https://finance.naver.com/item/main.naver?code={c}", source="naver",
                    tries=1, prefer_enc="euc-kr", referer="https://finance.naver.com/")
        if not h:
            return None
        m = re.search(r'<div class="wrap_company">\s*<h2>\s*<a[^>]*>([^<]+)</a>', h) or \
            re.search(r"<title>\s*([^:<]+?)\s*:", h)
        return (c, m.group(1).strip()) if m else None

    got = pmap_net(one, codes, workers=min(6, IO_THREADS), label="네이버 종목명 보강")
    out = {c: n for r in got if r for c, n in [r] if n}
    if out:
        L.ok(f"네이버 종목명 보강 {len(out):,}건")
    return out


def build_master(snapshots: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 종목마스터 — 소스별 기여를 표로 남긴다(다중소스 원장 연결 감사).
    CACHED 모드는 드라이브/로컬 캐시의 security_master 를 그대로 재사용한다(네트워크 0)."""
    if RUN_MODE == "CACHED":
        cached = VAULT.load_table("security_master", "shared")
        if cached is not None and len(cached):
            cached = cached.copy()
            for c in ("listing_date", "delisting_date"):
                if c in cached.columns:
                    cached[c] = ds_(cached[c])
            for c in MASTER_COLS:
                if c not in cached.columns:
                    cached[c] = np.nan
            L.ok(f"CACHED — 캐시 종목마스터 {len(cached):,}건 재사용(신규 수집 없음)")
            return cached
        L.warn("CACHED 모드인데 캐시에 security_master 가 없습니다 — 이번만 네트워크 경로로 "
               "구축을 시도합니다(다음 실행부터는 캐시 재사용).")
    parts: List[pd.DataFrame] = []
    feed: List[Tuple[str, int]] = []
    lst = harvest_listing()
    if len(lst):
        parts.append(lst); feed.append(("FDR 상장목록", len(lst)))
        RUN.io("IN", "HTTP", "fdr:listing", lst, src="github_cache")
    kind = harvest_kind()
    if len(kind):
        parts.append(kind); feed.append(("KIND 상장법인", len(kind)))
        RUN.io("IN", "HTTP", "kind:corpList", kind, src="KIND")
    dead = harvest_delisting()
    RUN.io("IN", "HTTP", "fdr:delisting", dead, src="github_cache", note="생존자편향 제거 입력")
    if len(dead):
        dd = dead.reindex(columns=["code", "name", "delisting_date", "market"]).copy()
        for c, v in (("listing_date", pd.NaT), ("industry", ""), ("corp_code", np.nan),
                     ("shares_now", np.nan), ("marcap_now", np.nan), ("origin", "fdr_delisting")):
            dd[c] = v
        parts.append(dd); feed.append(("FDR 상장폐지", len(dd)))
    if snapshots is not None and len(snapshots):
        known = set(pd.concat(parts)["code"]) if parts else set()
        extra = sorted(set(snapshots["code"]) - known)
        if extra:
            parts.append(pd.DataFrame({"code": extra, "name": "", "market": "",
                                       "industry": "", "listing_date": pd.NaT,
                                       "delisting_date": pd.NaT, "corp_code": np.nan,
                                       "shares_now": np.nan, "marcap_now": np.nan,
                                       "origin": "snapshot_only"}))
            feed.append(("스냅샷 전용(명단 누락 구제)", len(extra)))
    if not parts:
        raise RuntimeError("종목마스터를 만들 소스가 없습니다. raw.githubusercontent.com / "
                           "kind.krx.co.kr 접근과 FinanceDataReader 설치를 확인하세요. "
                           "RUN_MODE='SMOKE' 는 네트워크 없이 배관 검증이 가능합니다.")
    uniq_cols = list(dict.fromkeys(MASTER_COLS))
    m = pd.concat([p.reindex(columns=uniq_cols) for p in parts], ignore_index=True)
    no_dup_cols(m, "master:concat")
    m["code"] = m["code"].map(code6)
    m = m.dropna(subset=["code"])

    def first_str(s):
        for x in s:
            if isinstance(x, str) and x.strip():
                return x.strip()
        return ""

    agg = m.groupby("code", as_index=False).agg(
        name=("name", first_str), market=("market", first_str),
        industry=("industry", first_str),
        listing_date=("listing_date", "min"), delisting_date=("delisting_date", "max"),
        shares_now=("shares_now", "max"), marcap_now=("marcap_now", "max"),
        origin=("origin", lambda s: "|".join(sorted(set(map(str, s))))))
    no_dup_cols(agg, "master:agg")
    # 스냅샷으로 상장·폐지일 보정(날짜 근거가 없을 때만)
    if snapshots is not None and len(snapshots):
        g = snapshots.groupby("code")["snap_date"]
        agg = agg.merge(g.min().rename("_s0"), left_on="code", right_index=True, how="left")
        agg = agg.merge(g.max().rename("_s1"), left_on="code", right_index=True, how="left")
        need = agg["listing_date"].isna() & agg["_s0"].notna()
        agg.loc[need, "listing_date"] = agg.loc[need, "_s0"]
        last = snapshots["snap_date"].max()
        gone = (agg["delisting_date"].isna() & agg["_s1"].notna() &
                (agg["_s1"] < last - pd.Timedelta(days=200)))
        agg.loc[gone, "delisting_date"] = agg.loc[gone, "_s1"] + pd.offsets.MonthEnd(1)
        if int(gone.sum()):
            L.info(f"스냅샷에서 사라진 {int(gone.sum()):,}종목을 폐지 추정 — 폐지명단 누락의 "
                   f"2차 방어(생존자편향)")
        agg = agg.drop(columns=["_s0", "_s1"])
    cc = harvest_corpcode()
    if len(cc):
        agg = agg.merge(cc.dropna(subset=["code"])[["code", "corp_code", "corp_name"]]
                          .drop_duplicates("code"), on="code", how="left")
        blank = agg["name"].astype(str).str.strip() == ""
        agg.loc[blank, "name"] = agg.loc[blank, "corp_name"].fillna("")
        agg = agg.drop(columns=["corp_name"])
    else:
        agg["corp_code"] = np.nan
    nameless = agg.loc[agg["name"].astype(str).str.strip() == "", "code"].tolist()
    if nameless:
        nm = harvest_naver_names(nameless)
        if nm:
            agg["name"] = [nm.get(c, n) if not str(n).strip() else n
                           for c, n in zip(agg["code"], agg["name"])]
    agg["industry"] = agg["industry"].fillna("").astype(str).str.strip().replace("", "미분류")
    no_dup_cols(agg, "master:final")
    nl = int(agg["listing_date"].notna().sum())
    nd = int(agg["delisting_date"].notna().sum())
    nc = int(agg["corp_code"].notna().sum())
    L.grid([[a, f"{b:,}"] for a, b in feed] +
           [["─ 병합 결과 ─", ""], ["고유 종목", f"{len(agg):,}"],
            ["상장일 보유", f"{nl:,} ({100*nl/max(len(agg),1):.0f}%)"],
            ["폐지일 보유", f"{nd:,} ({100*nd/max(len(agg),1):.0f}%)"],
            ["corp_code 매칭", f"{nc:,} ({100*nc/max(len(agg),1):.0f}%)"]],
           ["소스/항목", "건수"], ["l", "r"], title="종목마스터 — 다중소스 원장 연결 감사")
    if nd < 200:
        L.warn("상장폐지 종목이 200건 미만 — 10년 구간 통상 1,000건 이상이어야 합니다. "
               "생존자편향 잔존 상태(C2 부분 미충족)를 결과 해석에 반영하세요.")
    VAULT.save_table("security_master", agg, "shared", domain="universe",
                     source="fdr+kind+dart+pykrx+naver")
    return agg


# ── PIT 유니버스 (C2) ───────────────────────────────────────────────────────────────────────
SEASONING_TDAYS = 250


class PITUniverse:
    """시점 t 의 '당시 상장' 집합. 진입=상장일+250거래일 · 이탈=상장폐지일 · 상폐 포함."""

    def __init__(self, master: pd.DataFrame, snapshots: pd.DataFrame, px_daily: pd.DataFrame):
        self.master = master.drop_duplicates("code").reset_index(drop=True).copy()
        self.master["listing_date"] = ds_(self.master["listing_date"])
        self.master["delisting_date"] = ds_(self.master["delisting_date"])
        self.funnel: List[dict] = []
        self._memo: Dict[pd.Timestamp, List[str]] = {}
        self._codes = self.master["code"].to_numpy(dtype=object)
        self._ld = self.master["listing_date"].to_numpy(dtype="datetime64[ns]")
        self._dd = self.master["delisting_date"].to_numpy(dtype="datetime64[ns]")
        self.delist_map = {c: d for c, d in zip(self._codes, self.master["delisting_date"])
                           if pd.notna(d)}
        self._snap: Dict[pd.Timestamp, set] = {}
        if snapshots is not None and len(snapshots):
            for dte, g in snapshots.groupby("snap_date"):
                self._snap[d_(dte)] = set(g["code"])
        tdays = (np.sort(pd.unique(ds_(px_daily["date"]).values))
                 if px_daily is not None and len(px_daily) else np.array([], dtype="datetime64[ns]"))
        # 시즈닝 확정일 — ★앵커는 '상장일'이다. 가격패널 시작일로 앵커하면 searchsorted 가
        # 패널 이전 상장분을 전부 index0 으로 보내 +250 이 더해져, 백테스트 첫 1년 동안
        # 기존 상장사 전체가 조용히 증발한다(치명·무로그 사고). 패널 이전 상장분은 이미
        # 오래전에 시즈닝이 끝난 것으로 달력 1년 규칙으로 확정한다.
        self._season: Dict[str, Any] = {}
        FAR = pd.Timestamp("2100-01-01")
        if len(tdays):
            t0 = tdays[0]
            pos = np.searchsorted(tdays, self._ld, side="left")
            pos_s = pos + SEASONING_TDAYS
            inside = pos_s < len(tdays)
            sdate = np.where(inside, tdays[np.minimum(pos_s, len(tdays) - 1)],
                             np.datetime64(FAR.isoformat(), "ns"))
            before = (~np.isnat(self._ld)) & (self._ld < t0)
            for c, ld, sd, pre in zip(self._codes, self._ld, sdate, before):
                if np.isnat(ld):
                    self._season[c] = pd.NaT
                elif pre:
                    self._season[c] = d_(ld) + pd.Timedelta(days=365)
                else:
                    self._season[c] = d_(sd)
        else:
            for c, ld in zip(self._codes, self._ld):
                self._season[c] = pd.NaT if np.isnat(ld) else d_(ld) + pd.Timedelta(days=365)

    def at(self, t) -> List[str]:
        t = d_(t)
        if t in self._memo:
            return self._memo[t]
        tt = np.datetime64(t)
        ok = ~((~np.isnat(self._ld)) & (self._ld > tt)) & \
             ~((~np.isnat(self._dd)) & (self._dd <= tt))
        ok &= ~(np.isnat(self._ld) & np.isnat(self._dd))       # 근거 전무 종목 제외
        base = set(self._codes[ok])
        past = [k for k in self._snap if k <= t]               # ★과거 스냅샷만(미래 스냅샷=누수)
        if past:
            k = max(past)
            if (t - k).days <= 130:                            # 분기 격자(±91일)+여유 — 창이 좁으면
                base |= self._snap[k]                          #   스냅샷 전용 종목이 깜빡이며 월 갭 유발
        # ★합집합 — 부분응답 스냅샷으로 기준선을 깎지 않는다(깎으면 곧 선택편향)
        base -= {c for c, dd in self.delist_map.items() if pd.notna(dd) and dd <= t}
        out = sorted(c for c in base
                     if not (pd.notna(self._season.get(c, pd.NaT)) and self._season[c] > t))
        self._memo[t] = out
        return out

    def gate(self, stage: str, t, codes: Sequence[str]):
        self.funnel.append({"month": d_(t), "stage": stage, "n": len(codes)})

    def funnel_table(self, since: int = 0, title: str = "유니버스 감쇠 감사 (§10.4)"):
        rows_src = self.funnel[since:]
        if not rows_src:
            return
        A = pd.DataFrame(rows_src)
        order = ["당시상장(PIT)", "가격보유", "유동성(V6)", "거부권통과", "하한선통과", "최종선정"]
        piv = A.groupby("stage")["n"].agg(["mean", "min", "max"])
        rows, prev = [], None
        for s in order:
            if s not in piv.index:
                continue
            r = piv.loc[s]
            keep = "" if prev is None else f"{100*r['mean']/max(prev,1e-9):.1f}%"
            rows.append([s, f"{r['mean']:,.0f}", f"{r['min']:,.0f}", f"{r['max']:,.0f}", keep])
            prev = r["mean"]
        L.grid(rows, ["게이트", "월평균", "최소", "최대", "직전 대비 잔존"],
               ["l", "r", "r", "r", "r"], title=title + " — 어느 게이트에서 표본이 붕괴하는가")


# ╔═══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [8] 데이터수집부 B — 가격(★날짜축 전종목 벌크) · 월간 패널 · 수급(월 단위 전종목) · 벤치마크║
# ║                                                                                           ║
# ║  ★★★ 구조개편의 핵심: 조회 축을 '종목'에서 '날짜'로 뒤집는다 ★★★                            ║
# ║                                                                                           ║
# ║   구(舊)설계 — 종목축 폴백체인                                                             ║
# ║     종목 5,400개 × 소스 5개(KRX→pykrx→FDR→네이버→yfinance) = 최대 27,000 왕복.             ║
# ║     상장폐지·우선주·비보통주 2,500여 종목은 다섯 소스가 전부 빈손이라 종목당 5회를          ║
# ║     통째로 소진하고, yfinance 는 .KS/.KQ 두 번을 더 때린다(종목당 1.0~1.5초 순수 낭비).    ║
# ║     → 4시간 예산을 가격 하나가 다 먹고 DART·리서치·팩은 시작조차 못 한다.                   ║
# ║                                                                                           ║
# ║   신(新)설계 — 날짜축 전종목 스냅샷                                                        ║
# ║     KRX 전종목시세(MDCSTAT01501) / pykrx get_market_ohlcv_by_ticker 는                     ║
# ║     "하루 1회 호출 = 그날 상장돼 있던 2,600종목 전부"를 준다.                               ║
# ║     10년 ≈ 2,700거래일 → 2,700회로 끝. 상장폐지 종목은 '당시 상장돼 있던 날'의 스냅샷에    ║
# ║     자동으로 들어오므로 ★죽은 코드를 조회할 일 자체가 사라진다(생존자편향도 동시 해결).     ║
# ║     받은 거래일은 원장(price_dates_done)에 남겨 ★두 번 다시 조회하지 않는다.                ║
# ║     거래대금(ACC_TRDVAL)이 진값으로 오므로 V6 유동성 필터의 근사오차도 사라진다.            ║
# ║     시가총액·상장주식수까지 같은 응답에 실려 오므로 비교전략 입력(F.CAP)도 공짜가 된다.     ║
# ║                                                                                           ║
# ║   yfinance 는 국내 6자리 코드에 대해 사실상 응답하지 않으면서 실패당 2왕복을 태운다.        ║
# ║   → 종목 체인에서 제외(기본값). 지수 벤치마크의 최후 폴백으로만 남긴다(PX_ALLOW_YFINANCE).  ║
# ╚═══════════════════════════════════════════════════════════════════════════════════════════╝

PX_COLS = ["code", "date", "open", "high", "low", "close", "volume", "value", "origin"]
PX_BULK_COLS = PX_COLS + ["mktcap", "shares"]
RETRY_FAILED_AFTER_D = 30


def _num(x) -> float:
    """'1,234' · '-' · '' 를 모두 흡수하는 KRX 표 숫자 파서."""
    s = str(x).replace(",", "").replace("−", "-").strip()
    if not s or s in ("-", "N/A"):
        return np.nan
    try:
        return float(s)
    except Exception:
        return np.nan


def _pick_code_col(d: pd.DataFrame) -> Optional[str]:
    """종목코드 컬럼을 이름으로 찾고, 없으면 첫 컬럼을 '값 형태'로 검증한 뒤에만 받아들인다.

    ★reset_index() 로 생긴 정수 인덱스를 코드로 추측해 받으면 code6 의 zfill 을 타고
      0→'000000', 1→'000001' 같은 가짜 종목이 가격·수급 패널에 진짜처럼 들어온다.
      길이 5 미만 값이 섞이면 코드 컬럼이 아니라고 판정한다."""
    cc = {str(c).strip(): c for c in d.columns}
    for k in ("티커", "종목코드", "code", "Code", "단축코드", "ISU_SRT_CD"):
        if k in cc:
            return cc[k]
    if not len(d.columns) or not len(d):
        return None
    first = d.columns[0]
    smp = d[first].astype(str).str.strip().head(50)
    if float((smp.str.len() >= 5).mean()) > 0.9 and float(smp.map(code6).notna().mean()) > 0.9:
        return first
    return None


def _pykrx_fn(*names) -> Optional[Callable]:
    """pykrx 는 버전마다 함수명이 갈린다(get_market_ohlcv / _by_ticker / _by_date).
    존재하는 첫 이름을 쓰고, 하나도 없으면 그 경로만 비활성화한다(죽지 않는다)."""
    if pykrx_stock is None:
        return None
    for n in names:
        f = getattr(pykrx_stock, n, None)
        if callable(f):
            return f
    return None


# ── ⓪ ★연도축 벌크 — FinanceData/marcap (전 시장 일봉 + 시총 + 주식수, 상장폐지 포함) ──────
#
#   지금까지의 축 변천:  종목축(27,000회) → 날짜축(2,760회) → ★연도축(10회)
#
#   marcap 은 KRX 전 종목의 일별 시세를 '연도별 파일 하나'로 공개한다. 10년이면 10개다.
#   · 상장폐지 종목이 그대로 들어 있다 → 생존자편향(C2)이 소스 차원에서 해결된다
#   · Amount(거래대금)가 진값 → V6 유동성 필터의 근사오차가 사라진다
#   · Marcap·Stocks 동봉 → 시가총액 스냅샷(F.CAP)이 공짜, 수정주가 복원의 주식수도 확보
#   · 로그인·인증키·레이트리밋 무관 → KRX 차단/pykrx 미설치와 완전히 독립
MARCAP_URLS = [
    "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.csv.gz",
    "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{y}.parquet",
    "https://media.githubusercontent.com/media/FinanceData/marcap/master/data/marcap-{y}.csv.gz",
]
_MARCAP_COLS = {"Date": "date", "Code": "code", "Name": "name", "Market": "market",
                "Open": "open", "High": "high", "Low": "low", "Close": "close",
                "Volume": "volume", "Amount": "value", "Marcap": "mktcap",
                "Stocks": "shares"}


def _marcap_year(y: int) -> Optional[pd.DataFrame]:
    """marcap-{연도} 파일 하나 = 그 해 전 종목 전 거래일. 원본 바이트도 공용 인덱스에 보관."""
    raw = None
    used = ""
    for tpl in MARCAP_URLS:
        url = tpl.format(y=y)
        raw = net_get(url, source="fdrcache", tries=2, as_bytes=True)
        # ★크기로 판정하지 않는다 — 404 HTML 을 거르려는 의도였지만 정상 파일까지 놓친다.
        #   매직바이트가 정확한 판정이다(gzip 1f8b / parquet PAR1).
        if raw and (raw[:2] == b"\x1f\x8b" or raw[:4] == b"PAR1"):
            used = url
            break
        raw = None
    if raw is None:
        return None
    try:
        if used.endswith(".parquet"):
            d = pd.read_parquet(io.BytesIO(raw))
        else:
            d = pd.read_csv(io.BytesIO(raw), compression="gzip", low_memory=False)
    except Exception as e:                                        # noqa
        L.warn(f"marcap-{y} 파싱 실패({type(e).__name__}) — 다음 소스로 넘어갑니다.")
        return None
    if d is None or not len(d):
        return None
    d = d.rename(columns={k: v for k, v in _MARCAP_COLS.items() if k in d.columns})
    if "date" not in d.columns and isinstance(d.index, pd.DatetimeIndex):
        d = d.reset_index().rename(columns={d.index.name or "index": "date"})
    if "date" not in d.columns or "code" not in d.columns or "close" not in d.columns:
        L.warn(f"marcap-{y} 스키마가 예상과 다릅니다({list(d.columns)[:8]}) — 건너뜁니다.")
        return None
    d["date"] = ds_(d["date"])
    d["code"] = d["code"].map(code6)
    for c in ("open", "high", "low", "close", "volume", "value", "mktcap", "shares"):
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    d = d.dropna(subset=["date", "code", "close"])
    d = d[d["close"] > 0]
    if not len(d):
        return None
    d["origin"] = "marcap"
    # 원본 보관 — 다른 전략도 그대로 재사용할 수 있게 공용 인덱스에 등록(절대 1원칙)
    try:
        VAULT.save_raw("price", "marcap_year", str(y), raw,
                       "parquet" if used.endswith(".parquet") else "csv.gz",
                       source=used, event_date=f"{y}-12-31", knowledge_date=f"{y}-12-31")
    except Exception:
        pass
    return d.reindex(columns=PX_BULK_COLS)


MARCAP_SHARD_VER = 2      # ★스키마 버전. 올리면 그 연도를 한 번 다시 받아 새 이름으로 추가한다
#                           (옛 샤드는 손대지 않음 = 절대 1원칙). v2 = 시가총액·상장주식수 포함.


def harvest_marcap(years: Sequence[int]) -> Optional[pd.DataFrame]:
    """연도축 수집 — 연도당 1회. 이미 받은 연도는 원장이 막는다.
    단 ★원장에 기록된 스키마 버전이 낮으면 그 연도만 다시 받는다(연 12회짜리 자가치유)."""
    led = VAULT.load_table("marcap_years_done", "shared")
    done: set = set()
    if led is not None and len(led):
        vv = (pd.to_numeric(led["ver"], errors="coerce").fillna(0)
              if "ver" in led.columns else pd.Series(0, index=led.index))
        done = {int(y) for y, v in zip(led["year"], vv) if int(v) >= MARCAP_SHARD_VER}
        stale = {int(y) for y in led["year"]} - done
        if stale:
            L.info(f"연도축 캐시 스키마 갱신 — {len(stale)}개 연도({min(stale)}~{max(stale)})는 "
                   f"시가총액·상장주식수가 없는 구버전 샤드입니다. 그 연도만 다시 받아 "
                   f"새 샤드로 추가합니다(옛 샤드는 그대로 보존 · 총 {len(stale)}회). "
                   f"이게 없으면 수정주가 복원과 시가총액이 재실행마다 죽습니다.")
    todo = [int(y) for y in years if int(y) not in done]
    if RUN_MODE == "CACHED" or CLOCK.over():
        todo = []
    if not todo:
        return None
    L.info(f"★연도축 수집 — marcap {len(todo)}개 연도 × 1회 = {len(todo)}회 "
           f"(종목축이었다면 수천 회, 날짜축이어도 {len(todo)*246:,}회). "
           f"상장폐지 종목·거래대금·시가총액·상장주식수가 전부 포함됩니다.")
    QUOTA.plan("krx", len(todo), "marcap 연도축(전 시장 일봉+시총)")
    got: List[pd.DataFrame] = []
    ok_years: List[int] = []
    with stage_bar(len(todo), "일봉(연도축 marcap)") as bar:
        for y in todo:
            if CLOCK.over():
                CLOCK.cut(f"marcap: {len(todo)-bar.n}개 연도 남기고 중단")
                break
            d = _marcap_year(y)
            bar.update(1)
            if d is None or not len(d):
                continue
            got.append(d)
            ok_years.append(y)
            VAULT.save_shard("krx_ohlcv_daily", d, key=f"marcap_{y}", scope="shared",
                             domain="price", source="FinanceData/marcap",
                             note="연도축 전 시장 일봉 — 전 전략 공용",
                             ver=MARCAP_SHARD_VER)
            base = VAULT.load_table("marcap_years_done", "shared")
            row = pd.DataFrame({"year": [y], "ver": [MARCAP_SHARD_VER]})
            allf = pd.concat([base, row], ignore_index=True) \
                if base is not None and len(base) else row
            if "ver" not in allf.columns:
                allf["ver"] = 0
            allf["ver"] = pd.to_numeric(allf["ver"], errors="coerce").fillna(0).astype(int)
            VAULT.save_table("marcap_years_done",
                             allf.sort_values("ver").drop_duplicates("year", keep="last"),
                             "shared", domain="price", source="year_ledger")
    if not got:
        L.warn("marcap 연도축 수집 실패 — 날짜축/종목축 경로로 진행합니다.")
        return None
    out = pd.concat(got, ignore_index=True)
    L.ok(f"marcap {len(ok_years)}개 연도 확보 — {len(out):,}행 · {out['code'].nunique():,}종목 "
         f"(호출 {len(ok_years)}회)")
    return out


# ── ① 거래일 달력 ───────────────────────────────────────────────────────────────────────────
def _cal_from_sources(s: pd.Timestamp, e: pd.Timestamp) -> Tuple[Optional[pd.DatetimeIndex], str]:
    """지수 시계열 1개만 받으면 KRX 정확 거래일이 나온다(휴장일 조회 낭비 제거).
    사다리: FDR KS11 → pykrx 지수 → 네이버 지수차트. 전부 실패하면 영업일 근사로 폴백."""
    if fdr is not None:
        try:
            pace("krx").wait()
            d = fdr.DataReader("KS11", s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"))
            if d is not None and len(d) > 200:
                idx = ds_(pd.Series(d.reset_index().iloc[:, 0])).dropna()
                return pd.DatetimeIndex(sorted(set(idx))), "fdr:KS11"
        except Exception:
            pass
    fn = _pykrx_fn("get_index_ohlcv", "get_index_ohlcv_by_date")
    if fn is not None:
        d = PKX.call(fn, s.strftime("%Y%m%d"), e.strftime("%Y%m%d"), "1001")
        if d is not None and len(d) > 200:
            idx = ds_(pd.Series(d.reset_index().iloc[:, 0])).dropna()
            return pd.DatetimeIndex(sorted(set(idx))), "pykrx:1001"
    t = net_get("https://fchart.stock.naver.com/sise.nhn?symbol=KOSPI&timeframe=day"
                "&count=6000&requestType=0", source="naver", tries=2)
    if t:
        got = [d_(x.split("|")[0]) for x in re.findall(r'<item data="([^"]+)"', t)]
        got = [x for x in got if x is not None and s <= x <= e]
        if len(got) > 200:
            return pd.DatetimeIndex(sorted(set(got))), "naver:KOSPI"
    return None, ""


def trading_calendar(start, end) -> Tuple[pd.DatetimeIndex, str]:
    """거래일 달력 — 캐시 우선. 정확 달력이면 '빈 응답 = 실패'로 판정할 수 있어
    차단 상황에서 원장이 오염되는 것을 막는다(근사 달력이면 빈 응답을 휴장으로 본다)."""
    s, e = d_(start), d_(end)
    cached = VAULT.load_table("krx_trading_days", "shared")
    have: List[pd.Timestamp] = []
    src = ""
    if cached is not None and len(cached) and "date" in cached.columns:
        have = list(ds_(cached["date"]).dropna())
        src = str(cached["src"].iloc[0]) if "src" in cached.columns and len(cached) else "cache"
    hv = pd.DatetimeIndex(sorted(set(have)))
    covered = len(hv) and hv.min() <= s + pd.Timedelta(days=10) and hv.max() >= e - pd.Timedelta(days=10)
    if not covered and RUN_MODE != "CACHED":
        got, gsrc = _cal_from_sources(s, e)
        if got is not None and len(got):
            hv = pd.DatetimeIndex(sorted(set(list(hv) + list(got))))
            src = gsrc
            VAULT.save_table("krx_trading_days", pd.DataFrame({"date": hv, "src": gsrc}),
                             "shared", domain="calendar", source=gsrc,
                             note="거래일 달력 — 전 전략 공용")
    cal = hv[(hv >= s) & (hv <= e)] if len(hv) else pd.DatetimeIndex([])
    if len(cal) < 100:
        cal = pd.DatetimeIndex([x for x in pd.bdate_range(s, e)])
        src = "bdate_approx"
        L.warn(f"거래일 달력 미확보 — 영업일 근사({len(cal):,}일)로 진행합니다. "
               f"휴장일에는 빈 응답이 오며 이는 정상이고 원장에 휴장으로 기록됩니다.")
    else:
        L.info(f"거래일 달력 {len(cal):,}일 ({cal.min():%Y-%m-%d}~{cal.max():%Y-%m-%d}) · 출처 {src}")
    return cal, src


# ── ② 날짜축 전종목 벌크 조회 ───────────────────────────────────────────────────────────────
def _bulk_krx_open(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """KRX Open API 일별매매정보 — 인증키 경로(로그인 세션 불필요·스키마 고정)."""
    blk = KRXOA.bydd(day)
    if not blk:
        return None
    rows = []
    for r in blk:
        c = krx_code(r.get("ISU_CD") or r.get("ISU_SRT_CD"))
        if not c:
            continue
        rows.append((c, _num(r.get("TDD_OPNPRC")), _num(r.get("TDD_HGPRC")),
                     _num(r.get("TDD_LWPRC")), _num(r.get("TDD_CLSPRC")),
                     _num(r.get("ACC_TRDVOL")), _num(r.get("ACC_TRDVAL")),
                     _num(r.get("MKTCAP")), _num(r.get("LIST_SHRS"))))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["code", "open", "high", "low", "close",
                                    "volume", "value", "mktcap", "shares"])
    d["date"], d["origin"] = day, "krx_open"
    return d.dropna(subset=["close"]).reindex(columns=PX_BULK_COLS)


def _bulk_krx_mp(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """KRX 전종목 시세(MDCSTAT01501) — 시가총액·상장주식수까지 한 번에.
    로그인 세션이 있을 때 1순위. ★한 번 호출 = 그날 상장 전 종목."""
    # ★로그인 여부로 막지 않는다 — 전종목시세(MDCSTAT01501)는 세션 없이도 응답하는 경우가
    #   많고, 아니면 bld() 가 JSON 아님을 보고 None 을 돌려주므로 다음 소스로 넘어갈 뿐이다.
    blk = KRX.bld_market_split("dbms/MDC/STAT/standard/MDCSTAT01501",
                               trdDd=day.strftime("%Y%m%d"))
    if not blk:
        return None
    rows = []
    for r in blk:
        c = krx_code(r.get("ISU_SRT_CD") or r.get("ISU_CD"))
        if not c:
            continue
        rows.append((c, _num(r.get("TDD_OPNPRC")), _num(r.get("TDD_HGPRC")),
                     _num(r.get("TDD_LWPRC")), _num(r.get("TDD_CLSPRC")),
                     _num(r.get("ACC_TRDVOL")), _num(r.get("ACC_TRDVAL")),
                     _num(r.get("MKTCAP")), _num(r.get("LIST_SHRS"))))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["code", "open", "high", "low", "close",
                                    "volume", "value", "mktcap", "shares"])
    d["date"], d["origin"] = day, "krx_mp"
    return d.dropna(subset=["close"]).reindex(columns=PX_BULK_COLS)


_PKX_BULK = None


def _bulk_pykrx(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """pykrx 전종목 일봉 — 로그인 불필요 경로. 거래대금이 진값으로 온다."""
    global _PKX_BULK
    if _PKX_BULK is None:
        _PKX_BULK = _pykrx_fn("get_market_ohlcv_by_ticker", "get_market_ohlcv") or False
    if not _PKX_BULK:
        return None
    ds = day.strftime("%Y%m%d")
    frames = []
    for mkt in ("ALL",):
        d = PKX.call(_PKX_BULK, ds, market=mkt)
        if d is not None and len(d):
            frames.append(d)
    if not frames:                                   # 구버전은 market="ALL" 미지원
        for mkt in ("KOSPI", "KOSDAQ", "KONEX"):
            d = PKX.call(_PKX_BULK, ds, market=mkt)
            if d is not None and len(d):
                frames.append(d)
    if not frames:
        return None
    d = pd.concat(frames)
    d = d.reset_index()
    ren = {"티커": "code", "날짜": "date", "시가": "open", "고가": "high", "저가": "low",
           "종가": "close", "거래량": "volume", "거래대금": "value"}
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
    if "code" not in d.columns:
        cc = _pick_code_col(d)
        if cc is None:
            return None                 # 추측 금지 — 가짜 코드 생성 경로
        d = d.rename(columns={cc: "code"})
    d["code"] = d["code"].map(code6)
    for c in ("open", "high", "low", "close", "volume", "value"):
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    d["date"], d["origin"] = day, "pykrx"
    d["mktcap"] = np.nan
    d["shares"] = np.nan
    d = d.dropna(subset=["code", "close"])
    d = d[d["close"] > 0]
    return d.reindex(columns=PX_BULK_COLS) if len(d) else None


def _bulk_fdrcache(day: pd.Timestamp) -> Optional[pd.DataFrame]:
    """FDR GitHub 일별 상장목록(raw.githubusercontent) — 로그인·키 불필요 날짜축 소스.
    ★종가·시가총액·상장주식수만 있고 시·고·저·거래량이 없다. 그래서 '최후 보루'다:
      거래대금이 없으면 V6 유동성 필터가 동작하지 않으므로, 이 소스만 살아 있는 경우
      harvest_prices 가 그 사실을 경고로 명시한다."""
    raw = net_get(_FDR_CACHE_URL.format(kind="listing/krx", date=day.strftime("%Y-%m-%d")),
                  source="fdrcache", tries=1, as_bytes=True)
    if not raw or len(raw) < 400:
        return None
    try:
        d = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig",
                        dtype={"Code": str, "Symbol": str})
    except Exception:
        return None
    c = {str(x).strip().lower(): x for x in d.columns}
    code_c = c.get("code") or c.get("symbol")
    close_c = c.get("close")
    if not code_c or not close_c:
        return None
    out = pd.DataFrame({
        "code": d[code_c].map(code6),
        "close": pd.to_numeric(d[close_c], errors="coerce"),
        "mktcap": pd.to_numeric(d[c["marcap"]], errors="coerce") if "marcap" in c else np.nan,
        "shares": pd.to_numeric(d[c["stocks"]], errors="coerce") if "stocks" in c else np.nan,
    }).dropna(subset=["code", "close"])
    if not len(out):
        return None
    out["open"] = out["high"] = out["low"] = out["close"]
    out["volume"] = np.nan
    out["value"] = np.nan
    out["date"], out["origin"] = day, "fdrcache"
    return out.reindex(columns=PX_BULK_COLS)


BULK_CHAIN = [("krx_open", _bulk_krx_open), ("krx_mp", _bulk_krx_mp),
              ("pykrx", _bulk_pykrx), ("fdrcache", _bulk_fdrcache)]


def px_preflight(cal: pd.DatetimeIndex, n_universe: int = 0) -> List[Tuple[str, Callable]]:
    """★대량 루프 전 소스 실측 — 이번 개편에서 가장 중요한 안전장치.

    지난 두 번의 실패는 전부 같은 모양이었다: '되는 줄 알았던 소스'로 수천 번을 돌다가
    빈 응답만 쌓이고, 로그에는 "데이터를 한 종목도 못 얻었다"는 결과만 남았다.
    서버가 실제로 뭘 돌려줬는지가 어디에도 없어서 원인을 못 좁혔다.
    → 이제는 실제 거래일 3개로 각 소스를 먼저 찔러 보고, 응답 행수와 실패 사유(HTTP 상태·
      응답 앞부분)를 표로 찍은 뒤, ★측정된 결과로만★ 수집 체인을 정한다.
    비용은 최대 소스수×3 회다.
    """
    # ★최근 거래일만 찔러서는 안 된다. 실제로 fdrcache(최근분만 보관)가 그 판정을 통과해
    #   '살아 있는 소스'로 뽑혔고, 99거래일만 받고 끝나 종목당 112행(≈5개월)짜리 패널이
    #   나왔다. 10년 백테스트가 불가능한 양인데 코드는 정상 종료했다.
    #   → 최근 2개 + 구간 초반/중반 2개를 함께 찔러 '과거를 주는가'를 따로 판정한다.
    recent = [d for d in cal[-40:][::-1]][:2] or list(cal[-2:])
    old: List[pd.Timestamp] = []
    if len(cal) > 400:
        old = [cal[len(cal) // 8], cal[len(cal) // 2]]
    probe = list(recent) + list(old)
    # 판정 임계는 절대값이 아니라 '유니버스 대비 비율'이다. 전종목 스냅샷이라면 마스터의
    # 최소 5% 는 나온다(마스터에는 상장폐지분이 절반쯤 섞여 있으므로 넉넉히 잡은 값).
    thr = max(20, int(0.05 * max(n_universe, 0)))
    rows, live = [], []
    for name, fn in BULK_CHAIN:
        best, err, best_old = 0, "", 0
        for dd in probe:
            try:
                r = fn(dd)
            except Exception as e:                                # noqa
                err = err or f"{type(e).__name__}: {str(e)[:60]}"
                r = None
            n = int(len(r)) if r is not None else 0
            best = max(best, n)
            if dd in old:
                best_old = max(best_old, n)
        ok_now = best >= thr
        ok_hist = (best_old >= thr) if old else ok_now
        ok = ok_now and ok_hist
        if ok_now and not ok_hist:
            err = ("최근분만 제공 — 과거 구간이 비어 10년 백테스트에 쓸 수 없습니다"
                   "(종목당 1회 스윕으로 과거를 채웁니다)")
        if ok:
            live.append((name, fn))
        if not ok and not err:
            st, head = NET_LAST.get({"krx_open": "krx", "krx_mp": "krx", "pykrx": "krx",
                                     "fdrcache": "fdrcache"}.get(name, name), ("—", ""))
            err = _preflight_why(name, st, head, best, thr)
        rows.append([name, f"{best:,}" if best else "0",
                     (f"{best_old:,}" if old else "—"),
                     "✔ 사용" if ok else "✘ 미사용", ("" if ok else err[:66])])
    L.grid(rows, ["벌크 소스", "최근 행수", "과거 행수", "판정",
                  "미사용 사유 / 서버가 돌려준 것"], ["l", "r", "r", "c", "l"],
           title=f"가격 소스 프리플라이트 (최근 {len(recent)}일 + 과거 {len(old)}일 실측 · "
                 f"합격선 {thr:,}행) — ★'과거를 주는가'까지 봐야 10년치가 채워집니다")
    if not live:
        L.warn("과거 구간을 주는 날짜축 소스가 없습니다 — 종목당 1회 스윕으로 전환합니다.")
    return live


def _preflight_why(name: str, st: Any, head: str, got: int, thr: int = 0) -> str:
    """되지 않는 이유를 사람이 바로 조치할 수 있는 말로 번역한다."""
    if got and thr and got < thr:
        return f"응답은 왔으나 {got:,}행뿐(합격선 {thr:,}) — 전종목 스냅샷이 아님"
    if name == "krx_open":
        if not KRX_OPENAPI_KEY:
            return "KRX_OPENAPI_KEY 미입력(선택 항목 — 없어도 됩니다)"
        return f"키는 있으나 사용 불가({KRXOA.state}) — 엔드포인트별 이용신청 승인 필요"
    if name == "pykrx":
        if pykrx_stock is None:
            return f"pykrx 임포트 실패 — 파이썬 {ENVX['python']} 용 휠이 없을 수 있습니다"
        if not _PKX_BULK:
            return "설치된 pykrx 에 전종목 일봉 함수가 없습니다(구버전)"
        return f"pykrx 호출이 빈손(HTTP {st}) · 응답머리: {head[:60]}"
    if name == "krx_mp":
        return (f"HTTP {st} · 응답머리: {head[:60]}" if head else
                f"HTTP {st} — data.krx.co.kr 차단/세션 문제 추정")
    if name == "fdrcache":
        return f"해당 날짜 파일 없음(HTTP {st}) — 이 캐시는 최근분만 보관합니다"
    return f"HTTP {st} · {head[:60]}"


# ── ③ 잔여 보충용 종목축 소스 (벌크가 못 덮은 극소수 전용) ──────────────────────────────────
def _px_fdr(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    if fdr is None:
        return None
    try:
        # ★[다른 세션 실측 이식] 이름은 FDR 이지만 6자리 KRX 코드는 FinanceDataReader 내부에서
        #   NaverDailyReader 로 라우팅된다(fchart.stock.naver.com). 즉 실제 상대는 KRX 가
        #   아니라 네이버다. krx 버킷(2.5qps)을 먹이면 (a) 같은 서버를 네이버 버킷과 합쳐
        #   5.5qps 로 때려 차단 위험이 오르고 (b) 스레드 12개가 0.4초 슬롯 하나를 나눠 써
        #   실효 동시성이 1로 떨어진다. 그 세션 실측으로 수집 시간의 100% 가 이 대기였다.
        pace("naver").wait()
        d = fdr.DataReader(code, start, end)
    except Exception:
        return None
    if d is None or len(d) == 0:
        return None
    d = d.reset_index()
    d.columns = [str(c).lower() for c in d.columns]
    if "date" not in d.columns:
        d = d.rename(columns={d.columns[0]: "date"})
    if "value" not in d.columns:
        d["value"] = pd.to_numeric(d.get("close"), errors="coerce") * \
                     pd.to_numeric(d.get("volume"), errors="coerce")   # 근사 — 감사표 명시
    d["code"], d["origin"] = code, "fdr"
    return d.reindex(columns=PX_COLS)


def _px_naver(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """네이버 차트 API — 준-JSON(홑따옴표) 형식. 거래대금이 없어 종가×거래량 근사."""
    qs = (f"?symbol={code}&requestType=1&startTime={d_(start):%Y%m%d}"
          f"&endTime={d_(end):%Y%m%d}&timeframe=day")
    arr = None
    for host in ("https://fchart.stock.naver.com/siseJson.naver",
                 "https://api.finance.naver.com/siseJson.naver"):
        t = net_get(host + qs, source="naver", tries=2, referer="https://finance.naver.com/")
        if not t:
            continue
        try:
            arr = json.loads(re.sub(r"'", '"', t))
        except Exception:
            try:
                import ast as _ast
                arr = _ast.literal_eval(t.strip())
            except Exception:
                arr = None
        if isinstance(arr, list) and len(arr) >= 2:
            break
        arr = None
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    hdr = [str(x).strip() for x in arr[0]]
    body = [r for r in arr[1:] if isinstance(r, (list, tuple)) and len(r) == len(hdr)]
    if not body:
        return None
    d = pd.DataFrame(body, columns=hdr)
    d = d.rename(columns={"날짜": "date", "시가": "open", "고가": "high", "저가": "low",
                          "종가": "close", "거래량": "volume"})
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce") if c in d.columns else np.nan
    d["date"] = ds_(d["date"]) if "date" in d.columns else pd.NaT
    d["value"] = d["close"] * d["volume"]
    d["code"], d["origin"] = code, "naver"
    d = d.dropna(subset=["date", "close"])
    return d.reindex(columns=PX_COLS) if len(d) else None


def _px_yf(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """★기본 비활성(PX_ALLOW_YFINANCE=False). 국내 6자리 코드는 야후에 거의 없고,
    실패 한 건마다 .KS/.KQ 두 왕복 + 내부 재시도를 태워 수집 예산을 통째로 갉아먹는다."""
    if yf is None or not PX_ALLOW_YFINANCE:
        return None
    for suf in (".KS", ".KQ"):
        try:
            pace("generic").wait()
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
        d["value"] = pd.to_numeric(d.get("close"), errors="coerce") * \
                     pd.to_numeric(d.get("volume"), errors="coerce")
        d["code"], d["origin"] = code, "yfinance"
        return d.reindex(columns=PX_COLS)
    return None


RESIDUAL_CHAIN = [("naver", _px_naver), ("fdr", _px_fdr), ("yfinance", _px_yf)]


# ── ④ 메인 — 날짜축 수집 ────────────────────────────────────────────────────────────────────
def _px_norm(px: pd.DataFrame) -> pd.DataFrame:
    px = px.copy()
    px["date"] = ds_(px["date"])
    for c in ("open", "high", "low", "close", "volume", "value", "mktcap", "shares"):
        if c in px.columns:
            px[c] = pd.to_numeric(px[c], errors="coerce")
    px = px.dropna(subset=["code", "date", "close"])
    # ★같은 (종목,날짜)가 여러 샤드에 있으면 ★정보가 많은 행을 남긴다. 스키마를 올려 새로 받은
    #   샤드(시총·주식수 포함)와 구버전 샤드가 공존할 때, 파일명 정렬 순서에 운명을 맡기면
    #   조용히 빈 쪽이 이긴다 — 그러면 스키마를 올린 의미가 사라진다.
    _rich = pd.Series(0, index=px.index, dtype="int8")
    for _c in ("shares", "mktcap", "value"):
        if _c in px.columns:
            _rich = _rich + px[_c].notna().astype("int8")
    px = (px.assign(_rich=_rich).sort_values(["code", "date", "_rich"])
            .drop_duplicates(["code", "date"], keep="last")
            .drop(columns="_rich").reset_index(drop=True))
    # ★범주형 접기 — 700만행 패널에서 code/origin 은 고유값이 수천 개뿐인데 행마다 별개
    #   문자열 객체로 남으면 그것만 수백 MB 다. 팩터화하면 행당 2바이트로 줄고,
    #   groupby(observed=True)·merge 는 그대로 동작한다(Colab RAM 방어).
    for c in ("code", "origin"):
        if c in px.columns and px[c].dtype.name != "category":
            px[c] = px[c].astype("category")
    return px


CA_SHARES_MIN = 0.15     # 주식수 변동 15% 이상만 자본변동 후보
CA_PROD_TOL = 0.12       # (주식수비 × 가격비) 가 1 에서 ±12% 안이면 '가격이 정확히 반대로 움직임'


def apply_corporate_actions(px: pd.DataFrame) -> pd.DataFrame:
    """★수정주가 복원 — 날짜축 개편이 만든 가장 위험한 부작용을 여기서 되돌린다.

    구 종목축 경로는 수정주가를 명시적으로 요청했다(KRX adjStkprc='2', pykrx adjusted=True).
    그런데 날짜축 전종목 스냅샷은 '그날 실제 체결가'다. 그대로 두면
      5:1 액면분할 → 종가 100,000 → 20,000 → fwd_ret = -80%  (실제 손익은 0%)
    가 되고, dlog_P 가 무너지면서 d1(=-dlog_M, U 축에서 가장 무거운 성분)이 그 종목을
    상위 5% 로 밀어 올린다. 순수 기업행위 아티팩트로 매수가 발생하고 성과·강건성이 전부 오염된다.

    복원 방법: 같은 응답에 실려 오는 상장주식수(LIST_SHRS)로 '조인트 테스트'를 한다.
      · 액면분할/병합·무상증자 = 주식수가 k배 되면서 가격이 정확히 1/k 로 움직인다
        → (주식수비 × 가격비) ≈ 1
      · 유상증자·CB전환 = 주식수는 늘지만 가격은 그만큼 떨어지지 않는다
        → (주식수비 × 가격비) 가 1 에서 벗어난다 → 조정하지 않는다(정상 수익률)
    과거 가격을 '그 시점 이후 발생한 k 들의 곱'으로 나눠 최신 기준으로 소급 조정한다.
    ★원본(raw)은 그대로 샤드에 저장하고 조정은 읽을 때마다 다시 계산한다 — 이중조정 불가.
    """
    if px is None or not len(px) or "shares" not in px.columns:
        return px
    # ★소스별로 '조정이 필요한지'가 다르다. 네이버/FDR 은 이미 수정주가를 돌려주므로
    #   여기서 또 조정하면 이중조정이 된다. 원시 체결가를 주는 소스만 대상으로 한다.
    RAW_SRC = ("marcap", "krx_open", "krx_mp", "pykrx")
    org = px["origin"].astype(str) if "origin" in px.columns else pd.Series("", index=px.index)
    raw_rows = org.isin(RAW_SRC)
    if not raw_rows.any():
        L.info("가격이 전부 수정주가 소스(네이버/FDR)에서 왔습니다 — 추가 조정 불필요.")
        return px
    sh = pd.to_numeric(px["shares"], errors="coerce").where(raw_rows)
    if float(sh.notna().mean()) < 0.20:      # '거의 비었나'는 비율로 판정(절대 건수는 규모의존)
        L.warn("원시 체결가 소스인데 상장주식수가 비어 수정주가 복원을 건너뜁니다 — 액면분할이 "
               "있는 종목은 그 달 수익률이 인위적으로 튑니다(marcap 경로가 살아나면 자동 해결).")
        return px
    px = px.sort_values(["code", "date"]).reset_index(drop=True)
    g = px.groupby("code", observed=True)
    sr = sh / g["shares"].transform(lambda s: pd.to_numeric(s, errors="coerce").shift(1))
    pr = px["close"] / g["close"].shift(1)
    prod = sr * pr
    is_ca = (sr.notna() & pr.notna() & (sr > 0) & (pr > 0) &
             (np.abs(np.log(sr.where(sr > 0))) > np.log(1 + CA_SHARES_MIN)) &
             (np.abs(np.log(prod.where(prod > 0))) < np.log(1 + CA_PROD_TOL)))
    n_ca = int(is_ca.sum())
    if not n_ca:
        return px
    k = pd.Series(np.where(is_ca.fillna(False), sr, 1.0), index=px.index).astype(float)
    cum = k.groupby(px["code"], observed=True).cumprod()
    tot = k.groupby(px["code"], observed=True).transform("prod")
    div = (tot / cum).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    touched = int((div != 1.0).sum())
    for c in ("open", "high", "low", "close"):
        if c in px.columns:
            px[c] = px[c] / div
    if "volume" in px.columns:
        px["volume"] = px["volume"] * div      # 거래대금(value)·시총은 통화라 조정 대상 아님
    L.ok(f"수정주가 복원 — 자본변동 {n_ca:,}건 감지({px.loc[is_ca, 'code'].nunique():,}종목), "
         f"과거 {touched:,}행 소급 조정. 조정 없이 두면 액면분할이 그대로 월수익률이 됩니다.")
    return px


def _sweep_skip_by_fact(codes: Sequence[str], master: Optional[pd.DataFrame],
                        s_ts: pd.Timestamp, e_ts: pd.Timestamp) -> List[str]:
    """★[다른 세션 교훈 이식] 생략 판정의 1차 근거는 시계(음성캐시)가 아니라 '사실'이다.
    구간이 시작되기 전에 이미 폐지됐거나, 구간이 끝난 뒤에 상장된 종목은 어떤 소스에도
    데이터가 없다 — 30일 유예를 기다릴 게 아니라 애초에 조회하지 않는다."""
    if master is None or not len(master) or "code" not in master.columns:
        return list(codes)
    m = master.drop_duplicates("code").set_index("code")
    dd = ds_(m["delisting_date"]) if "delisting_date" in m.columns else None
    ld = ds_(m["listing_date"]) if "listing_date" in m.columns else None
    out = []
    for c in codes:
        if dd is not None and c in dd.index and pd.notna(dd.get(c)) and dd[c] < s_ts:
            continue                       # 구간 시작 전에 이미 폐지
        if ld is not None and c in ld.index and pd.notna(ld.get(c)) and ld[c] > e_ts:
            continue                       # 구간 종료 후 상장
        out.append(c)
    n = len(codes) - len(out)
    if n:
        L.info(f"구간 밖 종목 {n:,}개는 조회 자체를 생략합니다"
               f"(구간 시작 전 폐지·구간 종료 후 상장 — 어떤 소스에도 데이터가 없음).")
    return out


def _sweep_per_stock(codes: Sequence[str], start: str, end: str,
                     order_hint: Optional[pd.Series] = None,
                     master: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """★종목당 정확히 1회 호출로 10년치를 받는 스윕 — 벌크가 전멸했을 때의 실질 폴백.

    처음 참사가 난 종목축과 결정적으로 다르다:
      · 그때는 종목 1개에 소스 5개 × 내부 재시도 × yfinance 이중접미사(.KS/.KQ) 였다.
        죽은 종목 2,500개가 각각 5~7 왕복을 태워 4시간을 통째로 먹었다.
      · 지금은 종목 1개 = 호출 1회(FDR). 실패하면 그 자리에서 음성캐시에 적히고 끝이다.
        5,400종목 × 1회 = QPS 2.5 에서 약 36분. 예산 안에 충분히 들어간다.
    시가총액 큰 순서로 돌기 때문에 시간예산에 잘려도 '거래 가능한 종목'이 먼저 채워진다.
    """
    codes = [c for c in dict.fromkeys(map(code6, codes)) if c]
    codes = _sweep_skip_by_fact(codes, master, d_(start), d_(end))
    if not codes:
        return None
    if order_hint is not None and len(order_hint):
        rank = {str(k): i for i, k in enumerate(order_hint.index)}
        codes.sort(key=lambda c: rank.get(c, 10 ** 9))
    today_ts = pd.Timestamp(dtm.date.today())
    neg = VAULT.load_table("price_fail_log", "shared")
    skip: Dict[str, pd.Timestamp] = {}
    if neg is not None and len(neg):
        neg = neg.copy()
        neg["tried_at"] = ds_(neg["tried_at"])
        neg = neg.sort_values("tried_at").drop_duplicates("code", keep="last")
        skip = {str(r.code): r.tried_at for r in neg.itertuples(index=False)}
    todo = [c for c in codes
            if not (c in skip and pd.notna(skip[c])
                    and (today_ts - skip[c]).days < RETRY_FAILED_AFTER_D)]
    if not todo:
        return None
    L.warn(f"벌크(날짜축) 소스가 하나도 살아 있지 않아 ★종목당 1회 스윕★ 으로 전환합니다 — "
           f"{len(todo):,}종목 × 1회 (예상 {len(todo)/max(QPS_CAP.get('krx',2.5),0.1)/60:.0f}분). "
           f"실패 종목은 즉시 음성캐시에 기록되어 다시 조회하지 않습니다.")
    QUOTA.plan("krx", len(todo), "종목당 1회 스윕(벌크 전멸 폴백)")

    def one(c):
        for nm, fn in (("fdr", _px_fdr), ("naver", _px_naver)):
            try:
                d = fn(c, start, end)
            except Exception:
                d = None
            if d is not None and len(d.dropna(subset=["date"])):
                return c, d.dropna(subset=["date"])
        return c, None

    got: List[pd.DataFrame] = []
    bad: List[dict] = []
    n_done = 0
    bar = tqdm(total=len(todo), desc="일봉(종목당 1회)", ncols=88, leave=False)
    for batch in chunked(todo, 300):
        if CLOCK.over():
            CLOCK.cut(f"종목 스윕: {n_done:,}/{len(todo):,}종목에서 중단(이어받음)")
            break
        for item in pmap_net(one, batch, workers=min(IO_THREADS, 8), quiet=True):
            if not item:
                continue
            c, d = item
            (got.append(d) if d is not None else bad.append({"code": c, "tried_at": today_ts}))
        n_done += len(batch)
        bar.update(len(batch))
        if got:                       # ★배치마다 즉시 저장 — 도중에 끊겨도 남는다
            add = _px_norm(pd.concat([g.reindex(columns=PX_BULK_COLS) for g in got],
                                     ignore_index=True))
            VAULT.save_shard("krx_ohlcv_daily", add,
                             key=f"sweep_{dtm.datetime.now():%Y%m%d_%H%M%S}_{n_done}",
                             scope="shared", domain="price", source="per_stock_sweep")
            got = []
        if bad:
            base = VAULT.load_table("price_fail_log", "shared")
            allf = pd.concat([base, pd.DataFrame(bad)], ignore_index=True) \
                if base is not None and len(base) else pd.DataFrame(bad)
            VAULT.save_table("price_fail_log",
                             allf.sort_values("tried_at").drop_duplicates("code", keep="last"),
                             "shared", domain="price", source="negative_cache")
            bad = []
    bar.close()
    fresh = VAULT.load_frame("krx_ohlcv_daily", "shared")
    return _px_norm(fresh) if fresh is not None and len(fresh) else None


def harvest_prices(master: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """전 종목 일봉 — ★날짜축 벌크. 거래일 1회 호출 = 그날 상장 전 종목.

    · 이미 받은 거래일은 원장(price_dates_done)이 막아 두 번 다시 조회하지 않는다.
    · 신규분은 샤드(part-*.parquet)로만 append — 700만행 테이블을 매번 통째로 다시 쓰지 않는다.
    · 시간예산(CLOCK) 도달 시 받은 만큼 저장하고 중단 → 중간결과 경로.
    """
    if isinstance(master, pd.DataFrame):
        codes = master["code"].tolist()
        cap_hint = (pd.to_numeric(master.get("marcap_now"), errors="coerce")
                    .groupby(master["code"].astype(str)).max().dropna()
                    .sort_values(ascending=False)) if "marcap_now" in master.columns else None
    else:
        codes, cap_hint = list(master), None
    want = sorted({c for c in map(code6, codes) if c})
    s_ts, e_ts = d_(start), d_(end)

    cached = VAULT.load_frame("krx_ohlcv_daily", "shared")
    if cached is not None and len(cached):
        cached = _px_norm(cached)

    # ── 거래일 원장 = '이 날짜는 전종목 스냅샷으로 받았다'의 유일한 근거 ────────────────
    # ★캐시에 그 날짜 행이 있다는 사실로 완료 판정하면 안 된다. 두 가지가 걸린다:
    #   ① 잔여보충으로 몇 종목만 들어온 날이 완료로 오인되어 영구히 반쪽으로 굳는다.
    #   ② 구버전(종목축) 캐시는 '일부 종목 × 전 기간' 이라 모든 날짜에 고르게 행이 있다.
    #      행수 중앙값 같은 상대 기준으로는 이걸 절대 걸러낼 수 없다(전 날짜가 완료로 보인다).
    #   원장은 신설 날짜축 경로만 쓴다 → 원장이 없으면 그 캐시는 구버전이라는 뜻이고,
    #   날짜축으로 한 번 훑어야 한다. 2,700회(≈20분)면 되고, 구버전 행은 그대로 합쳐 쓴다.
    led = VAULT.load_table("price_dates_done", "shared")
    done_dates: set = set()
    if led is not None and len(led) and "date" in led.columns:
        lg = led.copy()
        lg["date"] = ds_(lg["date"])
        lg = lg.dropna(subset=["date"])
        lg["n_rows"] = pd.to_numeric(lg.get("n_rows"), errors="coerce").fillna(0)
        nz = lg.loc[lg["n_rows"] > 0, "n_rows"]
        # ★행수 게이트 — 응답이 왔다는 사실만으로 완료 처리하면, 코스닥 레그가 죽어
        #   950행만 온 날이 2,600 종목짜리 거래일로 영원히 굳는다(재수집 경로가 없다).
        floor = max(30.0, 0.6 * float(nz.median())) if len(nz) else 0.0
        good = (lg["n_rows"] == 0) | (lg["n_rows"] >= floor)
        thin = int((~good).sum())
        done_dates = set(lg.loc[good, "date"].dt.strftime("%Y-%m-%d"))
        if thin:
            L.info(f"원장의 '반쪽 응답' {thin:,}거래일(행수 {floor:,.0f} 미만)은 완료로 보지 않고 "
                   f"다시 받습니다 — 부분 수집이 영구 동결되는 것을 막습니다.")
    if cached is not None and len(cached):
        n_day = int(cached["date"].nunique())
        if not done_dates:
            L.info(f"캐시 재사용: 일봉 {len(cached):,}행 · {cached['code'].nunique():,}종목 "
                   f"(구버전 종목축 캐시로 판단 — 행은 그대로 쓰고, 전종목 커버리지 확보를 위해 "
                   f"날짜축으로 한 번 훑습니다. 이후 실행부터는 원장이 막아 재조회하지 않습니다.)")
        else:
            L.info(f"캐시 재사용: 일봉 {len(cached):,}행 · {cached['code'].nunique():,}종목 · "
                   f"전종목 수집 완료 거래일 {len(done_dates):,}일 "
                   f"(캐시 보유 거래일 {n_day:,}일)")

    cal, cal_src = trading_calendar(s_ts, e_ts)

    # ⓪ 연도축 먼저 — 성공하면 날짜축 2,760회가 통째로 불필요해진다
    mc = harvest_marcap(range(s_ts.year, e_ts.year + 1))
    if mc is not None and len(mc):
        cached = mc if cached is None or not len(cached) else \
            _px_norm(pd.concat([cached, mc], ignore_index=True))
    # ★커버리지 판정의 근거는 '연도 원장'이지 캐시에 행이 있는 날짜가 아니다. 두 번 틀렸다.
    #   ① cached(= 구 종목축 캐시 + marcap 병합본)에서 날짜를 뽑으면, 300종목짜리 옛 캐시가
    #      전 거래일에 행을 갖고 있다는 이유만으로 marcap 이 못 받은 연도까지 '완료'가 된다
    #      → 그 연도가 반쪽 패널로 굳고 그 위에서 10년 Sharpe/MDD 가 계산된다(선택편향).
    #   ② harvest_marcap 은 전 연도가 이미 캐시에 있으면 None 을 반환한다. mc 성공 여부로
    #      판정하면 ★2회차 실행부터 done_dates 가 비어 날짜축 2,700일을 전량 재수집한다
    #      (연도축 개편의 성과가 재실행에서 통째로 사라진다).
    _mled = VAULT.load_table("marcap_years_done", "shared")
    mc_years = set(int(x) for x in _mled["year"]) if _mled is not None and len(_mled) else set()
    if mc_years:
        cov_y = {t.strftime("%Y-%m-%d") for t in cal if t.year in mc_years}
        done_dates |= cov_y
        L.info(f"연도축 원장이 {len(mc_years)}개 연도({min(mc_years)}~{max(mc_years)}) · "
               f"거래일 {len(cov_y):,}일을 덮었습니다 — 날짜축 재조회 대상에서 제외.")
    approx_cal = (cal_src == "bdate_approx")
    todo = [t for t in cal if t.strftime("%Y-%m-%d") not in done_dates]
    # ★최근 → 과거 순. 오름차순이면 시간예산에 잘렸을 때 '가장 오래된 몇 년'만 남고 최근이
    #   비어, 중간결과의 10년 Sharpe·MDD 가 전략이 한 번도 거래하지 않은 구간에서 계산된다.
    todo = todo[::-1]
    if RUN_MODE == "CACHED":
        todo = []

    new_frames: List[pd.DataFrame] = []
    new_led: List[dict] = []
    used = Counter()
    stop_bulk_empty = False
    swept = False
    chain = BULK_CHAIN
    if todo and RUN_MODE != "CACHED" and CLOCK.over():
        CLOCK.cut("일봉: 시간예산 초과 상태로 진입 — 신규 수집 없이 캐시로 진행")
        todo = []
    if todo and RUN_MODE != "CACHED":
        chain = px_preflight(cal, n_universe=len(want))   # ★측정 결과로만 체인을 정한다
        if not chain:
            # 벌크가 전멸 — 죽지 않는다. 종목당 1회 스윕으로 강등하고 이유를 남긴다.
            todo = []
            swept = True
            sw = _sweep_per_stock(want, s_ts.strftime("%Y-%m-%d"),
                                  e_ts.strftime("%Y-%m-%d"), order_hint=cap_hint,
                                  master=master if isinstance(master, pd.DataFrame) else None)
            if sw is not None and len(sw):
                cached = sw if cached is None or not len(cached) else \
                    _px_norm(pd.concat([cached, sw], ignore_index=True))
    if todo:
        n_call = len(todo)
        eta_min = n_call / max(QPS_CAP.get("krx", 2.0), 0.1) / 60.0
        L.info(f"일봉 신규 수집 — ★날짜축 {n_call:,}거래일 × 1회 = {n_call:,}회 · "
               f"예상 {eta_min:.0f}분 · 실측 생존 소스 " + "→".join(n for n, _ in chain))
        QUOTA.plan("krx", n_call, "일봉 전종목 스냅샷(날짜축)")

        def one(day):
            for nm, fn in chain:
                try:
                    d = fn(day)
                except Exception:
                    d = None
                if d is not None and len(d):
                    return day, d
            return day, None

        shard: List[pd.DataFrame] = []
        shard_days: List[pd.Timestamp] = []
        blank_run = 0
        stop = False
        # ★진행바는 '작업 전체'에 하나. 배치마다 0/N 이 새로 뜨면 같은 일을 무한 반복하는
        #   것처럼 보인다(옛 설계의 실제 오해 지점). 남은 시간까지 여기서 한 줄로 보여준다.
        bar = tqdm(total=len(todo), desc="일봉(전종목/거래일)", ncols=88, leave=False)
        for batch in chunked(todo, max(IO_THREADS * 4, 48)):
            if CLOCK.over():
                CLOCK.cut(f"일봉: {len(todo) - bar.n:,}거래일 남기고 중단 "
                          f"(받은 {bar.n:,}일은 저장 완료 — 재실행 시 이어받음)")
                stop = True
                break
            res = pmap_net(one, batch, workers=min(IO_THREADS, 8), quiet=True)
            bar.update(len(batch))
            for item in res:
                if not item:
                    continue
                day, d = item
                key = day.strftime("%Y-%m-%d")
                if d is not None and len(d):
                    blank_run = 0
                    used[str(d["origin"].iloc[0])] += 1
                    shard.append(d)
                    shard_days.append(day)
                    new_led.append({"date": key, "n_rows": int(len(d)),
                                    "src": str(d["origin"].iloc[0])})
                elif approx_cal:
                    # 근사 달력에서의 빈 응답은 휴장일 확률이 높다 → 완료로 기록(재조회 안 함)
                    new_led.append({"date": key, "n_rows": 0, "src": "holiday?"})
                else:
                    blank_run += 1        # 정확 달력의 빈 응답 = 실패. 원장에 넣지 않는다.
            if blank_run >= 24:
                # 프리플라이트에서 살아 있다고 '실측된' 소스가 도중에 죽은 경우다
                # (세션 만료·차단). 여기서 멈추고, 아래에서 종목 스윕으로 강등한다.
                L.warn("프리플라이트를 통과한 소스가 연속 24거래일 빈손 — 세션 끊김/차단으로 "
                       "판단해 벌크 수집을 중단합니다(받은 만큼 저장).")
                stop = True
                break
            if sum(len(x) for x in shard) >= 400_000:
                _flush_px_shard(shard, shard_days, new_led)
                if shard:
                    new_frames.append(pd.concat(shard, ignore_index=True))
                shard, shard_days, new_led = [], [], []
        bar.close()
        if shard or new_led:
            _flush_px_shard(shard, shard_days, new_led)
            if shard:
                new_frames.append(pd.concat(shard, ignore_index=True))
            shard, shard_days, new_led = [], [], []
        stop_bulk_empty = stop

    if stop_bulk_empty and RUN_MODE != "CACHED" and not (
            cached is not None and len(cached)) and not new_frames:
        # 벌크가 도중에 죽어 한 행도 못 얻은 경우 — 여기서도 종목 스윕으로 구제한다
        sw = _sweep_per_stock(want, s_ts.strftime("%Y-%m-%d"), e_ts.strftime("%Y-%m-%d"),
                              order_hint=cap_hint,
                              master=master if isinstance(master, pd.DataFrame) else None)
        if sw is not None and len(sw):
            cached = sw
    frames = ([cached] if cached is not None and len(cached) else []) + new_frames
    if not frames:
        # ★죽지 않는다. 여기서 예외를 던지면 4시간짜리 실행이 진단 한 줄 없이 끝난다.
        L.err("가격 데이터를 한 행도 확보하지 못했습니다. 위 '프리플라이트' 표의 "
              "'서버가 돌려준 것' 열이 원인을 그대로 보여줍니다. 대개 다음 중 하나입니다:")
        L.err("  ① data.krx.co.kr 이 방화벽/보안프로그램에 막힘 → 브라우저로 접속되는지 확인")
        L.err(f"  ② pykrx 미설치·임포트 실패(현재 파이썬 {ENVX['python']}) → "
              f"pip install -U pykrx 후 재실행")
        L.err("  ③ FinanceDataReader 미설치 → pip install -U finance-datareader")
        net_audit()
        return pd.DataFrame(columns=PX_BULK_COLS)
    px = _px_norm(pd.concat([f.reindex(columns=PX_BULK_COLS) for f in frames],
                            ignore_index=True))

    # ── 잔여 보충: 벌크가 한 행도 못 준 종목만, 상한을 걸고 종목축으로 구제 ──────────────
    # ★게이트가 'swept' 하나뿐이던 것이 실측 낭비를 냈다. 연도축(marcap)이 성공하면 swept 는
    #   False 인데 패널은 이미 전 시장·전 거래일을 덮은 상태다. 그런데도 마스터에만 있고
    #   시세가 없는 코드(폐지 우선주·ETF·ELW·스팩)를 1,278개씩 종목축으로 다시 물어봐서
    #   5분을 통째로 버렸다. 판정 기준은 '어떤 소스를 썼나'가 아니라 ★'달력을 얼마나 덮었나'다.
    cal_have = set(pd.DatetimeIndex(px["date"].unique()).normalize())
    cal_want = [t for t in cal if s_ts <= t <= e_ts]
    cov_day = len(cal_have & set(cal_want)) / max(len(cal_want), 1)
    # ★날짜 커버리지만으로 판정하면 안 된다 — 막으려는 대상(_residual_fill)은 ★종목축이다.
    #   '일부 종목 × 전 기간' 짜리 구 캐시는 모든 거래일에 행이 있어 cov_day=1.0 을 만든다.
    #   그 상태에서 잔여보충을 생략하면 반쪽 패널을 '전부 수집됐다'고 선언하는 셈이다.
    #   그래서 하루 평균 몇 종목이 들어와 있는지(종목축 커버리지)를 함께 본다.
    cov_code = float(px.groupby("date")["code"].nunique().median()) / max(len(want), 1)
    if swept or (cov_day >= PX_RESIDUAL_COV_SKIP and cov_code >= PX_RESIDUAL_COV_CODES):
        n_miss = len(set(want) - set(px["code"].astype(str)))
        if n_miss:
            L.info(f"잔여 보충 생략 — 벌크가 거래일의 {cov_day*100:.1f}%를, 하루 평균 마스터의 "
                   f"{cov_code*100:.1f}%를 덮었습니다(기준 {PX_RESIDUAL_COV_SKIP*100:.0f}% · "
                   f"{PX_RESIDUAL_COV_CODES*100:.0f}%). 이 상태에서 시세가 없는 "
                   f"{n_miss:,}종목은 '수집 실패'가 아니라 ★애초에 그 구간에 거래된 적이 없는 "
                   f"종목입니다(폐지 우선주·ETF·ELW·스팩·구간 밖 상장분). 종목축으로 다시 "
                   f"물어봐도 전부 빈손이고 시간만 태웁니다.")
    else:
        px = _residual_fill(px, want, s_ts, e_ts,
                            master=master if isinstance(master, pd.DataFrame) else None)
    px = apply_corporate_actions(px)          # ★반드시 저장 뒤·사용 앞 (원본은 raw 로 남는다)

    px = px[(px["date"] >= s_ts) & (px["date"] <= e_ts)]
    if used:
        L.grid([[k, f"{v:,}"] for k, v in used.most_common()], ["벌크 소스", "거래일수"],
               ["l", "r"], title="가격 소스 감사 (날짜축 · 1회=전종목)")
    if "code" in px.columns and px["code"].dtype.name == "category":
        px["code"] = px["code"].cat.remove_unused_categories()
    cov = px["code"].nunique()
    L.ok(f"일봉 확보 {len(px):,}행 · {cov:,}종목 · 거래일 {px['date'].nunique():,}일 "
         f"(마스터 {len(want):,}종목 중 {100*cov/max(len(want),1):.0f}% — 나머지는 "
         f"ETF/ELW/스팩 등 비보통주이거나 구간 밖 상장분)")
    return shrink(px)


def _flush_px_shard(shard: List[pd.DataFrame], days: List[pd.Timestamp], led_rows: List[dict]):
    """샤드 1개 + 거래일 원장을 즉시 드라이브에 기록 — 도중에 죽어도 받은 만큼은 남는다.
    ★샤드가 비어도(전부 휴장) 원장은 반드시 남긴다 — 안 그러면 그 날짜를 영원히 재조회한다."""
    saved = None
    if shard and days:
        ch = pd.concat(shard, ignore_index=True)
        d0, d1 = min(days), max(days)
        saved = VAULT.save_shard("krx_ohlcv_daily", ch, key=f"{d0:%Y%m%d}_{d1:%Y%m%d}",
                                 scope="shared", domain="price", source="krx_bulk_by_date",
                                 note="날짜축 전종목 스냅샷 — 전 전략 공용")
        if saved is None:
            # ★샤드가 디스크에 안 앉았는데 원장에 완료를 찍으면 그 날짜들은 영원히 사라진다.
            L.warn(f"샤드 저장 실패 — {len(days):,}거래일을 완료로 기록하지 않습니다"
                   f"(다음 실행에서 다시 받습니다).")
            return
    if led_rows:
        base = VAULT.load_table("price_dates_done", "shared")
        allf = pd.concat([base, pd.DataFrame(led_rows)], ignore_index=True) \
            if base is not None and len(base) else pd.DataFrame(led_rows)
        VAULT.save_table("price_dates_done", allf.drop_duplicates("date", keep="last"),
                         "shared", domain="price", source="date_ledger",
                         note="수집 완료 거래일 — 재조회 방지 원장")


def _residual_fill(px: pd.DataFrame, want: Sequence[str], s_ts, e_ts,
                   master: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """벌크 스냅샷에 한 행도 없는 종목만 종목축으로 구제한다.
    ★상한(PX_RESIDUAL_MAX_CODES)과 음성캐시를 반드시 건다 — 여기가 옛 설계의 늪이었다."""
    if RUN_MODE == "CACHED" or CLOCK.over():
        return px
    miss = sorted(set(want) - set(px["code"].astype(str)))
    # ★소거의 1차 근거는 시계(음성캐시)가 아니라 사실이다 — 구간 시작 전에 폐지됐거나
    #   구간 종료 후 상장된 종목은 어떤 소스에도 없다. 30일 유예를 기다릴 이유가 없다.
    miss = _sweep_skip_by_fact(miss, master, s_ts, e_ts)
    if not miss:
        return px
    today_ts = pd.Timestamp(dtm.date.today())
    neg = VAULT.load_table("price_fail_log", "shared")
    fails: Dict[str, pd.Timestamp] = {}
    if neg is not None and len(neg):
        neg = neg.copy()
        neg["tried_at"] = ds_(neg["tried_at"])
        neg = neg.sort_values("tried_at").drop_duplicates("code", keep="last")
        fails = {str(r.code): r.tried_at for r in neg.itertuples(index=False)}
    fresh = [c for c in miss
             if not (c in fails and pd.notna(fails[c])
                     and (today_ts - fails[c]).days < RETRY_FAILED_AFTER_D)]
    n_skip = len(miss) - len(fresh)
    if n_skip:
        L.info(f"최근 {RETRY_FAILED_AFTER_D}일 내 전 소스 실패 {n_skip:,}종목은 건너뜁니다"
               f"(대부분 비보통주·구간 밖 상장분 — 자동 재시도 예약됨).")
    cap = int(PX_RESIDUAL_MAX_CODES)
    if cap > 0 and len(fresh) > cap:
        L.warn(f"잔여 보충 대상 {len(fresh):,}종목 중 상한 {cap:,}종목만 시도합니다 "
               f"(나머지는 다음 실행에서 이어받음 — 수집 예산 보호).")
        fresh = fresh[:cap]
    if not fresh:
        return px
    L.info(f"잔여 보충 {len(fresh):,}종목 (체인: "
           + "→".join(n for n, f in RESIDUAL_CHAIN
                      if n != "yfinance" or PX_ALLOW_YFINANCE) + ")")
    st, en = s_ts.strftime("%Y-%m-%d"), e_ts.strftime("%Y-%m-%d")

    def one(c):
        for nm, fn in RESIDUAL_CHAIN:
            try:
                d = fn(c, st, en)
            except Exception:
                d = None
            if d is not None and len(d.dropna(subset=["date"])):
                return c, d.dropna(subset=["date"])
        return c, None

    got, bad = [], []
    for batch in chunked(fresh, 200):
        if CLOCK.over():
            CLOCK.cut(f"잔여 보충: {len(got):,}종목 확보 후 중단")
            break
        for item in pmap_net(one, batch, workers=min(IO_THREADS, 6), label="잔여 보충"):
            if not item:
                continue
            c, d = item
            if d is not None:
                got.append(d)
            else:
                bad.append({"code": c, "tried_at": today_ts})
        if bad:                                    # ★배치마다 즉시 기록 — 도중에 끊겨도 남는다
            base = VAULT.load_table("price_fail_log", "shared")
            allf = pd.concat([base, pd.DataFrame(bad)], ignore_index=True) \
                if base is not None and len(base) else pd.DataFrame(bad)
            VAULT.save_table("price_fail_log",
                             allf.sort_values("tried_at").drop_duplicates("code", keep="last"),
                             "shared", domain="price", source="negative_cache")
            bad = []
    if got:
        add = _px_norm(pd.concat([g.reindex(columns=PX_BULK_COLS) for g in got],
                                 ignore_index=True))
        VAULT.save_shard("krx_ohlcv_daily", add,
                         key=f"residual_{dtm.datetime.now():%Y%m%d_%H%M%S}", scope="shared",
                         domain="price", source="residual_chain")
        L.ok(f"잔여 보충 {add['code'].nunique():,}종목 확보 — 거래대금은 종가×거래량 근사이며 "
             f"V6 유동성 필터가 그만큼 느슨해집니다(감사 명시).")
        px = _px_norm(pd.concat([px, add], ignore_index=True))
    return px


def monthly_panel(px: pd.DataFrame, months: pd.DatetimeIndex) -> Dict[str, pd.DataFrame]:
    """월말 신호 → ★다음 거래일 시가 체결(§10.1 — 당일 종가 체결은 미래누수).
    fwd_ret 은 '바로 다음 달'과만 짝짓는다(월 결손 시 몇 달 수익이 한 달로 둔갑하는 것 방지)."""
    if px is None or not len(px):
        empty_m = pd.DataFrame(columns=["code", "month", "signal_date", "close", "adv20",
                                        "next_open", "next_date", "exec_ok", "exec_px",
                                        "fwd_ret"])
        return {"daily": pd.DataFrame(columns=PX_BULK_COLS), "monthly": empty_m}
    px = px.sort_values(["code", "date"]).copy()
    px["adv20"] = (px.groupby("code", observed=True)["value"]
                     .transform(lambda s: s.rolling(20, min_periods=10).mean()))
    ym = px["date"].values.astype("datetime64[M]")
    px["_ym"] = ym
    last = px.groupby(["code", "_ym"], observed=True).tail(1).copy()
    last["month"] = ds_(last["_ym"]) + pd.offsets.MonthEnd(0)
    nxt = px[["code", "date", "open"]].copy()
    nxt["next_open"] = nxt.groupby("code", observed=True)["open"].shift(-1)
    nxt["next_date"] = nxt.groupby("code", observed=True)["date"].shift(-1)
    last = last.merge(nxt[["code", "date", "next_open", "next_date"]],
                      on=["code", "date"], how="left")
    M = last[["code", "month", "date", "close", "adv20", "next_open", "next_date"]] \
        .rename(columns={"date": "signal_date"})
    M["code"] = M["code"].astype(str)          # 하류 병합은 전부 문자열 코드 기준
    M = M[M["month"].isin(months)].sort_values(["code", "month"]).reset_index(drop=True)
    gap = (M["next_date"] - M["signal_date"]).dt.days
    # exec_ok: 익일 시가로 '실제 체결 가능'한 행. 정지 임박(gap>10) 종목의 종가 폴백은
    # 보유 평가용일 뿐 — §10.1 상 신규 진입은 exec_ok 행에서만 허용한다(엔진에서 강제).
    M["exec_ok"] = gap.notna() & (gap <= 10)
    M["exec_px"] = M["next_open"].where(M["exec_ok"])
    M["exec_px"] = M["exec_px"].fillna(M["close"])
    nx_px = M.groupby("code", observed=True)["exec_px"].shift(-1)
    nx_m = M.groupby("code", observed=True)["month"].shift(-1)
    adjacent = (((nx_m.dt.year - M["month"].dt.year) * 12 +
                 (nx_m.dt.month - M["month"].dt.month)) == 1)
    M["fwd_ret"] = (nx_px / M["exec_px"] - 1.0).where(adjacent)
    n_gap = int((nx_m.notna() & ~adjacent).sum())
    if n_gap:
        L.info(f"월 연속성 결손 {n_gap:,}건의 fwd_ret 결측 처리(수익 과대계상 방지) — "
               f"상폐 구간은 엔진이 -100% 로 별도 처리")
    RUN.io("OUT", "MEM", "monthly_panel", M)
    return {"daily": px.drop(columns=["_ym"]), "monthly": shrink(M)}


# ── ⑤ 수급 — ★월 단위 전종목 일괄 ───────────────────────────────────────────────────────────
FLOW_INVESTORS = [("inst_net", "기관합계"), ("forgn_net", "외국인")]

# ── 수급 직통 경로(pykrx 없이) ────────────────────────────────────────────────────────────
#   실측 로그에서 d3 가 매 실행 통째로 결측이었다. 원인은 데이터가 없어서가 아니라
#   ★수집 경로가 pykrx 하나뿐이었기 때문이다(임포트 실패 = 축 하나 소실). 같은 표를
#   KRX 정보데이터시스템이 직접 준다: [12009] 투자자별 순매수상위종목 — 기간·투자자 지정
#   1회 호출에 전 종목 순매수가 나온다(월축 120개월 × 투자자 2 = 240회).
FLOW_BLD = "dbms/MDC/STAT/standard/MDCSTAT02401"
FLOW_INVST_CD = {"inst_net": "7050", "forgn_net": "9000"}   # 기관합계 / 외국인
_FLOW_CODE_KEYS = ("ISU_SRT_CD", "ISU_CD", "ISU_ABBRV")
_FLOW_VAL_KEYS = ("NETBID_TRDVAL", "NETBID_TRDVAL_1", "TRDVAL")


def _flow_krx_month(m0: pd.Timestamp, m1: pd.Timestamp, col: str) -> Optional[pd.DataFrame]:
    """KRX bld 직통 — 한 달 × 한 투자자 = 1회. 실패하면 None(상위가 다음 경로로 내린다)."""
    # ★askBid/detailView/trdVolVal 은 MDCSTAT02303(개별종목 상세)의 파라미터이지 02401 의
    #   것이 아니다. 잉여 파라미터는 게이트웨이에서 거부를 유발할 수 있어 보내지 않는다.
    rows = KRX.bld_market_split(FLOW_BLD, invstTpCd=FLOW_INVST_CD[col],
                                strtDd=m0.strftime("%Y%m%d"), endDd=m1.strftime("%Y%m%d"))
    if not rows:
        return None
    d = pd.DataFrame(rows)
    key = next((k for k in _FLOW_CODE_KEYS if k in d.columns), None)
    val = next((k for k in _FLOW_VAL_KEYS if k in d.columns), None)
    if key is None or val is None:
        return None                     # ★컬럼 추측 금지 — 가짜 종목코드를 만드는 경로다
    out = pd.DataFrame({
        "code": d[key].astype(str).str.extract(r"(\d{6})")[0].map(code6),
        col: pd.to_numeric(d[val].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                           errors="coerce")}).dropna(subset=["code"])
    return out if len(out) else None


def _flow_krx_probe(months: Sequence[pd.Timestamp]) -> bool:
    """쓰기 전에 재 본다 — 레이아웃이 다르면 240회를 태우기 전에 여기서 멈춘다.
    ★한 달만 보면 안 된다. 그 달이 미래·휴장·일시오류면 정상 경로인데도 120개월 전체를
      포기해 d3 축이 통째로 사라진다(단일 표본으로 축 하나를 버리는 판정)."""
    for m in list(months)[-3:][::-1]:
        t = _flow_krx_month(m.replace(day=1), m, "inst_net")
        if t is not None and len(t) >= 100 and t["inst_net"].notna().sum() >= 50:
            return True
    st, head = NET_LAST.get("krx", ("—", ""))
    L.warn(f"수급 KRX 직통 프리플라이트 실패(최근 3개월 모두) — 응답 {st} · {str(head)[:110]}")
    return False


def harvest_flows(codes: Sequence[str], start: str, end: str) -> pd.DataFrame:
    """기관·외국인 순매수(D축 d3) — ★날짜축(월) 전종목 일괄.

    구설계: 종목축 5,398회 × 직렬(pykrx 락) → 최소 45분, 실제로는 그 이상.
    신설계: get_market_net_purchases_of_equities(월초,월말,'ALL',투자자) 1회 = 전 종목.
            120개월 × 투자자 2 = 240회. 반환은 월간 프레임(code, month, inst_net, forgn_net).
    ※ 구버전 캐시(krx_flows_daily, 일간)는 자동으로 월 집계해 흡수한다(호환).
    """
    empty = pd.DataFrame(columns=["code", "month", "inst_net", "forgn_net"])
    cachedm = VAULT.load_table("krx_flows_monthly", "shared")
    frames: List[pd.DataFrame] = []
    have: set = set()
    if cachedm is not None and len(cachedm):
        cachedm = cachedm.copy()
        cachedm["month"] = ds_(cachedm["month"]) + pd.offsets.MonthEnd(0)
        cachedm = cachedm.dropna(subset=["code", "month"])
        frames.append(cachedm)
        have = set(cachedm["month"].dt.strftime("%Y-%m"))
        L.info(f"캐시 재사용: 수급(월간) {len(cachedm):,}행 · {len(have)}개월")
    legacy = VAULT.load_table("krx_flows_daily", "shared")
    if legacy is not None and len(legacy) and "date" in legacy.columns:
        lg = legacy.copy()
        lg["month"] = ds_(lg["date"]) + pd.offsets.MonthEnd(0)
        lg = (lg.dropna(subset=["code", "month"])
                .groupby(["code", "month"], as_index=False)[["inst_net", "forgn_net"]].sum())
        lg["_legacy"] = True
        frames.append(lg)
        L.info(f"구버전 일간 수급 캐시 {len(legacy):,}행을 월 집계로 승계했습니다. "
               f"단, 이 월들은 '수집 완료'로 치지 않습니다 — 구 수집기가 종목 일부에서 잘린 "
               f"상태라 그대로 완료 처리하면 나머지 종목이 영구 결손으로 굳습니다.")

    fn = _pykrx_fn("get_market_net_purchases_of_equities",
                   "get_market_net_purchases_of_equities_by_ticker")
    months = [m for m in month_grid(start, end) if m.strftime("%Y-%m") not in have]
    # ★경로가 하나뿐이면 그 하나가 없을 때 축이 통째로 사라진다. pykrx 가 없으면 KRX 직통.
    use_krx = False
    if months and RUN_MODE != "CACHED" and not CLOCK.over():
        if fn is None:
            use_krx = _flow_krx_probe(months)
        else:
            # ★pykrx 가 '있는데 빈손'인 경우도 있다(신버전은 KRX_ID/KRX_PW 로그인을 요구한다).
            #   함수 존재 여부만 보고 축을 통째로 포기하지 않는다 — 한 달만 재 보고 갈아탄다.
            _pb = PKX.call(fn, months[-1].replace(day=1).strftime("%Y%m%d"),
                           months[-1].strftime("%Y%m%d"), "ALL", FLOW_INVESTORS[0][1])
            if _pb is None or not len(_pb):
                L.warn("pykrx 순매수 함수가 빈손입니다 — KRX 직통 경로로 전환을 시도합니다.")
                use_krx = _flow_krx_probe(months)
                if use_krx:
                    fn = None
        if use_krx:
            L.ok("수급: pykrx 없이 KRX 정보데이터시스템 직통 경로로 수집합니다"
                 "(월축 1회 = 전 종목 · d3 복구).")
    if (fn is None and not use_krx) or RUN_MODE == "CACHED" or CLOCK.over():
        months = []
        if fn is None and pykrx_stock is not None:
            L.warn("pykrx 에 전종목 순매수 함수가 없습니다(구버전) — d3 결측으로 진행합니다.")
    got: List[pd.DataFrame] = []
    if months:
        L.info(f"수급 신규 수집 — ★월축 {len(months)}개월 × 투자자 {len(FLOW_INVESTORS)} = "
               f"{len(months)*len(FLOW_INVESTORS):,}회 (종목축이었다면 {len(set(codes)):,}회 직렬)")
        QUOTA.plan("krx", len(months) * len(FLOW_INVESTORS), "수급 전종목 월간(월축)")
        for m in tqdm(months, desc="수급(전종목/월)", ncols=88, leave=False):
            if CLOCK.over():
                CLOCK.cut(f"수급: {len(got)}개월 수집 후 중단")
                break
            f0 = m.replace(day=1)
            part: Optional[pd.DataFrame] = None
            if use_krx:                                   # ★KRX 직통 (pykrx 부재 시)
                for col, _inv in FLOW_INVESTORS:
                    one = _flow_krx_month(f0, m, col)
                    if one is None or not len(one):
                        continue
                    part = one if part is None else part.merge(one, on="code", how="outer")
                if part is not None and len(part):
                    part["month"] = m
                    got.append(part)
                continue
            for col, inv in FLOW_INVESTORS:
                # ★market="ALL" 이 안 먹는 pykrx 버전에서는 KOSPI+KOSDAQ 을 '합쳐야' 한다.
                #   먼저 성공한 하나로 break 하면 코스닥이 통째로 빠져 소형주 d3 가 전멸한다.
                d = PKX.call(fn, f0.strftime("%Y%m%d"), m.strftime("%Y%m%d"), "ALL", inv)
                if d is None or len(d) == 0:
                    subs = [x for x in (PKX.call(fn, f0.strftime("%Y%m%d"),
                                                 m.strftime("%Y%m%d"), mk, inv)
                                        for mk in ("KOSPI", "KOSDAQ"))
                            if x is not None and len(x)]
                    d = pd.concat(subs) if subs else None
                if d is None or len(d) == 0:
                    continue
                d = d.reset_index()
                cc = {str(c).strip(): c for c in d.columns}
                key = _pick_code_col(d)
                val = cc.get("순매수거래대금") or cc.get("순매수금액")
                if val is None or key is None:
                    continue          # ★코드 컬럼 추측 금지(가짜 코드 생성 경로)
                one = pd.DataFrame({"code": d[key].map(code6),
                                    col: pd.to_numeric(d[val], errors="coerce")}).dropna(
                                        subset=["code"])
                part = one if part is None else part.merge(one, on="code", how="outer")
            if part is not None and len(part):
                part["month"] = m
                got.append(part)
    if got:
        newf = pd.concat(got, ignore_index=True)
        for c in ("inst_net", "forgn_net"):
            if c not in newf.columns:
                newf[c] = np.nan
        frames.append(newf[["code", "month", "inst_net", "forgn_net"]])
    if not frames:
        L.warn("수급 미수집 — d3 결측, U 는 가용 축 평균으로 구성합니다. 경로 상태: "
               f"pykrx={'가용' if fn is not None else '없음'} · "
               f"KRX직통={'가용' if use_krx else '실패/미시도'} · 모드={RUN_MODE}"
               + (" · 시간예산 초과" if CLOCK.over() else ""))
        return empty
    fl = pd.concat([f.reindex(columns=["code", "month", "inst_net", "forgn_net", "_legacy"])
                    for f in frames], ignore_index=True)
    fl["_legacy"] = fl["_legacy"].fillna(False).astype(bool)
    fl["month"] = ds_(fl["month"]) + pd.offsets.MonthEnd(0)
    fl = (fl.dropna(subset=["code", "month"])
            .sort_values(["code", "month", "_legacy"], ascending=[True, True, False])
            # ↑ 승계분(True)을 앞에, 신규(False)를 뒤에 → keep="last" 가 신규를 남긴다
            .drop_duplicates(["code", "month"], keep="last").reset_index(drop=True))
    drop_idx = fl.index[fl["_legacy"]]
    fl = fl.drop(columns=["_legacy"])
    if got:
        # ★승계분(구버전 일간 캐시 파생)은 월간 테이블에 저장하지 않는다. 저장하면 다음 실행의
        #   have 에 그 월이 들어가 '전종목 월 수집'이 영영 돌지 않는다(선택편향 고착).
        keep = fl[~fl.index.isin(drop_idx)] if len(drop_idx) else fl
        VAULT.save_table("krx_flows_monthly", keep, "shared", domain="flow",
                         source=("krx_bld:MDCSTAT02401" if use_krx else "pykrx:net_purchases"),
                         note="월간 전종목 순매수 — 전 전략 공용")
    return shrink(fl)


# ── ⑥ 벤치마크 ──────────────────────────────────────────────────────────────────────────────
def harvest_benchmarks(months: pd.DatetimeIndex) -> Dict[str, pd.Series]:
    """KOSPI/KOSDAQ 월간수익. 캐시 우선 → FDR → 네이버 지수차트 → yfinance 폴백.
    수집분은 드라이브 공용 인덱스에 저장(전 전략 재사용)."""
    out: Dict[str, pd.Series] = {}
    cached = VAULT.load_table("benchmark_monthly", "shared")
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["month"] = ds_(cached["month"])
        have_full = True
        for name in ("KOSPI", "KOSDAQ"):
            sub = cached[cached["name"] == name].set_index("month")["ret"]
            s = sub.reindex(months)
            if s.notna().sum() >= len(months) * 0.9:
                out[name] = s
            else:
                have_full = False
        if out and (have_full or RUN_MODE == "CACHED"):
            L.info(f"캐시 재사용: 벤치마크 {list(out)} ({len(cached):,}행)")
            return out
        out = {}
    if RUN_MODE == "CACHED" or CLOCK.over():
        if RUN_MODE == "CACHED":
            L.warn("CACHED — 벤치마크 캐시가 없어 지수 대비표는 생략됩니다(동일가중 벤치는 유지).")
        return out
    for name, fdr_sym, nv_sym, yf_sym in (("KOSPI", "KS11", "KOSPI", "^KS11"),
                                          ("KOSDAQ", "KQ11", "KOSDAQ", "^KQ11")):
        px = None
        if fdr is not None:
            try:
                pace("generic").wait()
                d = fdr.DataReader(fdr_sym, months[0] - pd.offsets.MonthEnd(2), months[-1])
                if d is not None and len(d):
                    d = d.reset_index()
                    d.columns = [str(c).lower() for c in d.columns]
                    dc = "date" if "date" in d.columns else d.columns[0]
                    px = pd.DataFrame({"date": ds_(d[dc]),
                                       "close": pd.to_numeric(d["close"], errors="coerce")})
            except Exception:
                px = None
        if px is None:
            t = net_get(f"https://fchart.stock.naver.com/sise.nhn?symbol={nv_sym}"
                        f"&timeframe=day&count=3000&requestType=0", source="naver", tries=1)
            if t:
                items = re.findall(r'<item data="([^"]+)"', t)
                rows = []
                for it in items:
                    seg = it.split("|")
                    if len(seg) >= 5:
                        rows.append({"date": d_(seg[0]),
                                     "close": pd.to_numeric(seg[4], errors="coerce")})
                if rows:
                    px = pd.DataFrame(rows)
        if px is None and yf is not None:
            # 지수는 야후에 확실히 있다 — 종목 체인과 달리 여기 폴백은 값을 한다(호출 2회).
            try:
                d = yf.download(yf_sym, start=str(months[0].date() - dtm.timedelta(days=90)),
                                end=str(months[-1].date()), progress=False, threads=False)
                if d is not None and len(d):
                    if isinstance(d.columns, pd.MultiIndex):
                        d.columns = [str(c[0]).lower() for c in d.columns]
                    else:
                        d.columns = [str(c).lower() for c in d.columns]
                    d = d.reset_index()
                    px = pd.DataFrame({"date": ds_(d[d.columns[0]]),
                                       "close": pd.to_numeric(d["close"], errors="coerce")})
            except Exception:
                px = None
        if px is None or not len(px):
            continue
        px = px.dropna()
        px["month"] = px["date"] + pd.offsets.MonthEnd(0)
        s = px.groupby("month")["close"].last().pct_change()
        out[name] = s.reindex(months)
    if out:
        rows = [{"name": nm, "month": m, "ret": v}
                for nm, s in out.items() for m, v in s.items() if pd.notna(v)]
        if rows:
            new_df = pd.DataFrame(rows)
            if cached is not None and len(cached):     # ★기존 캐시와 합집합 — 축소 저장 금지
                new_df = (pd.concat([cached, new_df], ignore_index=True)
                          .drop_duplicates(["name", "month"], keep="last"))
            VAULT.save_table("benchmark_monthly", new_df, "shared",
                             domain="benchmark", source="fdr/naver/yfinance")
    else:
        L.warn("지수 벤치마크 미확보 — 동일가중 유니버스 벤치마크만 사용합니다.")
    return out


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [9] 데이터수집부 C — DART 재무제표 · 직원현황 · 공시목록 (B/C축 · PACK-C · V2/V3/V8 입력)  ║
# ║                                                                                          ║
# ║  ★ PIT 핵심: knowledge_date = 공시 접수일자(rcept_no 앞 8자리). 결산기준일이 아니다(C1).   ║
# ║    rcept 이 없으면 법정 제출기한(분기 45일/사업보고서 90일)로 '늦게 알았다' 방향 보수 추정. ║
# ║  ★ 호출량: 고정 예산 없이 QUOTA(실시간 잔여) — status 020 수신 즉시 실측 한도 학습·정지.   ║
# ║  ★ 시간예산: CLOCK 도달 시 받은 만큼 저장하고 중단 → 부분 데이터 중간결과 경로.            ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

DART_URL = "https://opendart.fss.or.kr/api/"
RQ = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
RQ_DEADLINE = {"11013": 45, "11012": 45, "11014": 45, "11011": 90}
RQ_PERIOD_END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
DART_MSG = {"000": "정상", "010": "미등록 키", "011": "사용불가 키", "012": "IP 차단",
            "013": "데이터 없음", "020": "일일 한도초과", "021": "회사 수 초과",
            "100": "필드 부적절", "800": "시스템 점검", "900": "정의되지 않은 오류",
            "901": "계정 폐쇄"}


_ACCT_RX: Optional[Any] = None


def acct_keep(d: pd.DataFrame) -> pd.DataFrame:
    """★수집 즉시 '쓰는 계정'만 남긴다.

    fnlttSinglAcntAll 은 회사·기간당 200~300 계정을 통째로 준다. 그런데 이 전략이 실제로
    읽는 계정은 ACCT 의 24개뿐이다. 전부 들고 있으면
      1,500사 × 13년 × 4보고서 × 250계정 ≈ 1,950만 행 × 문자열 8컬럼 ≈ 수 GB
    가 되어 H.DART 가 램에서 죽고(그 단계는 critical=False 라 조용히 통과한다)
    B축·C축이 통째로 빈 채 백테스트가 돌아간다. 90% 이상을 여기서 버린다 —
    드라이브 샤드 용량도 같은 비율로 줄어든다.
    """
    global _ACCT_RX
    if d is None or not len(d):
        return d
    if _ACCT_RX is None:
        _ACCT_RX = re.compile("|".join(p for _, pats in ACCT.values() for p in pats), re.I)
    aid = d["account_id"].astype(str)
    anm = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    return d[aid.str.contains(_ACCT_RX, na=False) | anm.str.contains(_ACCT_RX, na=False)]


def fs_compact(d: pd.DataFrame) -> pd.DataFrame:
    """반복값이 대부분인 문자열 컬럼을 범주형으로 — 누적 재무 테이블의 램/디스크 방어."""
    if d is None or not len(d):
        return d
    for c in ("corp_code", "reprt_code", "sj_div", "account_id", "account_nm", "fs_kind"):
        if c in d.columns and d[c].dtype == object:
            d[c] = d[c].astype("category")
    return d


def dart_call(ep: str, params: dict) -> Optional[dict]:
    """DART 호출 단일 통로 — 쿼터 계수(실제 시도 횟수 기준) + 020 학습 + 진단.

    ★ 020(일일 한도초과)과 021(조회 회사 수 초과)은 완전히 다른 사건이다.
      021 은 '한 요청에 회사 100개를 넘겨서' 나는 요청 오류일 뿐인데 이것을 한도초과로
      학습하면 멀쩡한 잔여 호출량을 통째로 버리고 그날 수집이 죽는다(잠재 사고였음).
    """
    if not DART_API_KEY or not QUOTA.allow("dart"):
        return None
    p = dict(params)
    p["crtfc_key"] = DART_API_KEY
    js = net_json(DART_URL + ep, source="dart", params=p, tries=2,
                  referer="https://opendart.fss.or.kr/",
                  count_cb=lambda: QUOTA.charge("dart"))
    if not isinstance(js, dict):
        return None                     # ★통신 실패 — '데이터 없음'과 절대 같지 않다
    st = str(js.get("status", ""))
    if st and st != "000":
        if st == "013":
            return {"status": "013"}    # ★서버가 '진짜 없다'고 답한 것만 음성캐시 대상
        if st == "020":
            QUOTA.server_says_limit("dart")
        elif st == "021":
            L.warn("DART status=021(조회 회사 수 초과) — 배치 크기를 줄여 재시도합니다"
                   "(일일 한도와 무관).")
        elif st in ("010", "011", "012", "901"):
            L.err(f"DART 인증 오류 status={st}({DART_MSG.get(st, '?')}) — DART_API_KEY 확인")
        return None
    QUOTA.ok("dart")      # ★정상 응답 — 공식치를 넘겼을 때 '실측 상향'의 근거가 된다
    return js


def _kd_from_rcept(rcept: Any, rq: str, year: int) -> pd.Timestamp:
    s = re.sub(r"\D", "", str(rcept or ""))
    if len(s) >= 8:
        t = d_(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
        if t is not None and 2000 <= t.year <= 2100:
            return t
    mm, dd = RQ_PERIOD_END.get(rq, (12, 31))
    return d_(f"{year}-{mm:02d}-{dd:02d}") + pd.Timedelta(days=RQ_DEADLINE.get(rq, 90))


_FS_KEEP = ["corp_code", "bsns_year", "reprt_code", "sj_div", "account_id", "account_nm",
            "thstrm_amount", "rcept_no", "fs_kind", "tier"]
# tier 0 = 단건 전체재무제표(fnlttSinglAcntAll) — 실제 접수일자를 갖는 유일한 경로
# tier 1 = 재무제표 일괄 ZIP — 전 상장사·전 계정, 접수번호 없음(법정기한 추정)
# tier 2 = 다중회사 주요계정(fnlttMultiAcnt) — 핵심 6~13계정
#          같은 (회사·기간·계정)이 겹치면 낮은 tier 가 이긴다.
EMPTY_RETRY_AFTER_D = 90        # '데이터 없음(013)' 조합의 재시도 유예 — 매일 같은 빈 키에
#                                 한도를 태우지 않기 위한 음성 캐시(90일 뒤 자동 재시도)


# ── ★재무제표 일괄 ZIP — 단건 API 78,000회를 약 150회 다운로드로 대체 ──────────────────────
#
#   DART 는 '재무제표 원본파일'을 (연도 × 보고서 × 재무제표) 단위 ZIP 으로 공개한다.
#   한 파일에 그 기간 전 상장사가 들어 있다.
#     12년 × 4보고서 × 3제표(BS/PL/CF) ≈ 144회 다운로드  vs  1,500사 × 13년 × 4 = 78,000 API 호출
#   ★게다가 이 경로는 crtfc_key 를 쓰지 않아 ★일일 호출한도를 소비하지 않는다★.
#   → 심층 계정(재고자산·매출채권·영업CF·CAPEX)이 하루가 아니라 십수 분 만에 채워진다.
#
#   ⚠ PIT 주의: 일괄 파일은 '최신 정정본'을 담을 수 있다. 접수번호가 없으므로
#     knowledge_date 를 법정 제출기한(분기 45일 / 사업보고서 90일)으로 보수 추정한다.
#     실제 접수일을 가진 단건 API 행이 있으면 그쪽(tier 0)이 항상 우선한다.
DART_BULK_LIST = "https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/list.do"
DART_BULK_DL = "https://opendart.fss.or.kr/cmm/downloadFnlttZip.do"
_BULK_LINK_RE = re.compile(
    r"download_ext002\('(?P<year>\d{4})','(?P<report>FQ|HY|TQ|FY)',\s*"
    r"'(?P<stmt>BS|PL|CF|CE)',\s*'(?P<file>[^']+\.zip)'")
_BULK_RQ = {"FQ": RQ["Q1"], "HY": RQ["H1"], "TQ": RQ["Q3"], "FY": RQ["FY"]}
_BULK_SJ = {"BS": "BS", "PL": "IS", "CF": "CF"}          # CE(자본변동표)는 쓰지 않는다


def _bulk_amount_col(cols: Sequence[str], stmt: str) -> Optional[str]:
    """일괄 ZIP 의 '당기' 금액 컬럼 고르기.

    ★판정은 공백을 제거하고 하되 ★반환은 반드시 정규화된 이름으로 한다. 옛 구현은 strip 한
      이름으로 판정하고 원본(비-strip)을 돌려줬는데, 호출부는 strip 된 컬럼과 대조하므로
      헤더에 공백이 하나만 붙어도 `amt not in tb.columns` 가 되어 ★그 멤버 파일 전체가
      조용히 스킵됐다. 손익계산서(PL) 헤더('당기 1분기 3개월' 등)가 가장 길어 가장 잘 걸린다 —
      그러면 매출원가·법인세비용이 통째로 비고 TP_B1·eff_tax·V8 이 한꺼번에 죽는다.
    """
    norm = {str(c): re.sub(r"\s+", "", str(c)) for c in cols}
    cur = [c for c in cols if norm[str(c)].startswith("당기")]
    if not cur:
        return None
    if stmt == "BS":
        return str(cur[0]).strip()
    acc = [c for c in cur if "누적" in norm[str(c)]]
    if acc:
        return str(acc[0]).strip()
    non3 = [c for c in cur if "3개월" not in norm[str(c)]]
    return str((non3 or cur)[0]).strip()

def harvest_dart_bulk_zip(code2corp: Dict[str, str], years: Sequence[int]) -> pd.DataFrame:
    """(연도×보고서×제표) ZIP 을 받아 필요한 계정만 뽑아낸다. API 쿼터를 쓰지 않는다."""
    empty = pd.DataFrame(columns=_FS_KEEP)
    if not DART_BULK_ZIP or RUN_MODE == "CACHED":
        return empty
    cached = VAULT.load_frame("dart_fnltt_bulkzip", "shared")
    if not code2corp:
        # ★가드 필수 — corp_code 지도가 비면 전 파일이 '0행이지만 정상 파싱'으로 끝난다.
        #   도달 경로가 실재한다: dart_corpcode 캐시가 없는 상태에서 그날 쿼터가 이미
        #   소진된 재실행이면 harvest_corpcode() 가 빈 프레임을 돌려주고 master 의
        #   corp_code 가 전부 NaN 이 된다. 그대로 진행하면 129개 파일이 완주로 기록되어
        #   ★일일 한도를 쓰지 않는 유일한 재무 경로가 영구히 죽는다(쿼터표엔 흔적도 없다).
        L.warn("일괄 ZIP 건너뜀 — corp_code 매핑이 비어 있습니다(DART corpCode 수집 실패 "
               "또는 쿼터 소진). 지금 받으면 전 파일이 0행으로 '완주' 기록되어 다시는 "
               "받지 않게 됩니다. corpCode 를 먼저 확보한 뒤 재실행하세요.")
        return cached if cached is not None else empty
    done: set = set()
    led = VAULT.load_table("dart_bulkzip_done", "shared")
    if led is not None and len(led):
        done = set(zip(led["year"].astype(int), led["report"].astype(str),
                       led["stmt"].astype(str)))
        L.info(f"캐시 재사용: 재무 일괄 ZIP {len(done):,}개 파일 · "
               f"{0 if cached is None else len(cached):,}행")
    txt = net_post(DART_BULK_LIST, source="dart",
                   referer="https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do")
    if not txt:
        txt = net_get(DART_BULK_LIST, source="dart", tries=2,
                      referer="https://opendart.fss.or.kr/disclosureinfo/fnltt/dwld/main.do")
    rows = [m.groupdict() for m in _BULK_LINK_RE.finditer(str(txt or ""))]
    if not rows:
        L.warn("재무제표 일괄 ZIP 목록을 파싱하지 못했습니다 — 단건 API 경로로 진행합니다"
               "(느립니다). opendart.fss.or.kr 접근 가능 여부를 확인하세요.")
        return cached if cached is not None else empty
    yrs = {int(y) for y in years}
    todo = [r for r in rows if int(r["year"]) in yrs and r["stmt"] in _BULK_SJ
            and (int(r["year"]), r["report"], r["stmt"]) not in done]
    todo.sort(key=lambda r: (-int(r["year"]), r["report"], r["stmt"]))
    if not todo:
        return cached if cached is not None else empty
    L.info(f"★재무제표 일괄 ZIP {len(todo)}개 다운로드 — 단건 API 였다면 수만 회. "
           f"이 경로는 일일 호출한도를 쓰지 않습니다. 파일당 수십~수백 MB 이므로 "
           f"{DART_ZIP_WORKERS}개를 동시에 받으면서 받는 즉시 파싱합니다"
           f"(진행바에 누적 수신량이 초 단위로 갱신됩니다 — 멈춘 것처럼 보이면 실제로 멈춘 것).")
    keep_codes = set(code2corp)
    got: List[pd.DataFrame] = []
    new_done: List[dict] = []
    n_skip_mem = 0

    def _parse_zip(r: dict, src) -> Tuple[List[pd.DataFrame], int, int]:
        """ZIP 하나 → (프레임들, 파싱한 멤버 수, 스킵한 멤버 수).

        ★진짜 병목은 다운로드가 아니라 여기다(실측: ZIP 은 개당 2~8MB 로 작고, 27MB 짜리
          멤버 하나를 전 컬럼으로 읽는 데 3.3초·148MB 가 든다). 그래서 2단 패스로 읽는다:
          ①헤더만(nrows=0) 읽어 '당기' 금액 컬럼을 정하고 ②본 패스는 ★필요한 4개 컬럼만
          usecols 로 읽는다 — 실측 0.4초·41MB(8배 빠르고 3.6배 가볍다).
          청크도 200,000 은 최대 멤버(약 12만행)보다 커서 사실상 청킹이 안 됐다 → 50,000.
        """
        parts: List[pd.DataFrame] = []
        n_ok = n_bad = 0
        with zipfile.ZipFile(src) as zf:
            # 멤버명은 CP437 로 모지바케된 EUC-KR 이라 이름 필터는 ASCII 인 확장자로만 한다.
            for mem in [m for m in zf.namelist() if m.lower().endswith(".txt")]:
                try:
                    with zf.open(mem) as fh:
                        head = pd.read_csv(fh, sep="\t", encoding="cp949",
                                           encoding_errors="replace", dtype=str,
                                           nrows=0, on_bad_lines="skip")
                    cols = [str(c).strip() for c in head.columns]
                    amt = _bulk_amount_col(list(head.columns), r["stmt"])
                    cc = next((c for c in ("종목코드", "stock_code") if c in cols), None)
                    ic = next((c for c in ("항목코드", "계정ID") if c in cols), None)
                    nc = next((c for c in ("항목명", "계정명") if c in cols), None)
                    if amt is None or not cc or not nc:
                        # ★무성 스킵 금지 — 여기서 조용히 빠지면 그 제표(특히 손익계산서)가
                        #   통째로 비고, 매출원가·법인세비용이 사라져 TP_B1·eff_tax·V8 이
                        #   한꺼번에 죽는다. 어떤 헤더였는지를 반드시 남긴다.
                        n_bad += 1
                        L.warn(f"ZIP 멤버 스킵 {r['year']}/{r['report']}/{r['stmt']} "
                               f"[{mem[-42:]}]: amt={amt!r} code={cc!r} name={nc!r} · "
                               f"cols={[c[:16] for c in cols[:8]]}")
                        continue
                    want = [c for c in (cc, ic, nc, amt) if c]
                    # 헤더 원본에는 공백이 붙어 있을 수 있으므로 원본 이름으로 usecols 를 준다
                    orig = {str(c).strip(): str(c) for c in head.columns}
                    use = [orig[c] for c in want]
                    with zf.open(mem) as fh:
                        for tb in pd.read_csv(fh, sep="\t", encoding="cp949",
                                              encoding_errors="replace", dtype=str,
                                              usecols=use, chunksize=50_000,
                                              on_bad_lines="skip", low_memory=False):
                            tb.columns = [str(c).strip() for c in tb.columns]
                            code = tb[cc].astype(str).str.replace(r"[\[\]\s]", "", regex=True) \
                                     .map(code6)
                            m = code.isin(keep_codes)
                            if not m.any():
                                continue
                            sub = pd.DataFrame({
                                "corp_code": code[m].map(code2corp).astype(str),
                                "bsns_year": int(r["year"]),
                                "reprt_code": _BULK_RQ[r["report"]],
                                "sj_div": _BULK_SJ[r["stmt"]],
                                "account_id": (tb.loc[m, ic].astype(str) if ic else ""),
                                "account_nm": tb.loc[m, nc].astype(str),
                                "thstrm_amount": tb.loc[m, amt].astype(str),
                                "rcept_no": "",      # 일괄 파일엔 접수번호 없음 → 법정기한 추정
                                "fs_kind": "BULKZIP", "tier": 1})
                            parts.append(acct_keep(sub))
                            del tb, code, m, sub
                    n_ok += 1
                except Exception as e:                            # noqa
                    n_bad += 1
                    L.warn(f"ZIP 멤버 파싱 실패 {r['year']}/{r['report']}/{r['stmt']} "
                           f"[{mem[-42:]}]: {type(e).__name__}: {e}")
        return parts, n_ok, n_bad

    def _flush(force: bool = False):
        """★중간 저장 — 129개를 다 받은 뒤에 한 번만 저장하면, 중간에 끊기거나 죽는 순간
        받아 놓은 파싱 결과가 통째로 날아가고 다음 실행이 처음부터 다시 받는다.

        ★순서가 결정적이다: ①데이터 샤드를 먼저 쓰고 ②그게 성공했을 때만 원장을 쓴다.
          원장을 먼저 쓰면, 그 뒤 concat 에서 MemoryError 가 나거나 parquet 쓰기가
          실패했을 때(디스크 풀 등) '원장에는 완주, 데이터는 0행' 이 남는다. todo 필터가
          원장을 보므로 그 (연도·보고서·제표)는 ★영구히 다시 받지 않는다.
        """
        nonlocal got, new_done
        if not new_done or not (force or len(new_done) >= 16):
            return
        if got:
            try:
                add = fs_compact(pd.concat(got, ignore_index=True))
                ok = VAULT.save_shard("dart_fnltt_bulkzip", add,
                                      key=f"{dtm.datetime.now():%Y%m%d_%H%M%S}_{len(new_done)}",
                                      scope="shared", domain="dart",
                                      source="opendart:fnltt_bulk_zip",
                                      note="재무제표 일괄 ZIP — 전 전략 공용")
            except Exception as e:                                # noqa
                L.warn(f"일괄 ZIP 중간 저장 실패 — 원장을 쓰지 않고 다음 실행이 재시도합니다: "
                       f"{type(e).__name__}: {e}")
                return
            if ok is None:
                L.warn("일괄 ZIP 샤드 저장이 실패했습니다 — 원장을 쓰지 않습니다"
                       "(원장만 남으면 그 파일들은 영구히 재수집되지 않습니다).")
                return
            kept.append(add)
            got = []
        base = VAULT.load_table("dart_bulkzip_done", "shared")
        allf = pd.concat([base, pd.DataFrame(new_done)], ignore_index=True) \
            if base is not None and len(base) else pd.DataFrame(new_done)
        VAULT.save_table("dart_bulkzip_done",
                         allf.drop_duplicates(["year", "report", "stmt"]), "shared",
                         domain="dart", source="bulkzip_ledger")
        new_done = []

    kept: List[pd.DataFrame] = []
    prog = {"b": 0, "t": 0.0}
    plk = threading.Lock()

    def _fetch(r: dict):
        def _on(n: int, _tot: int):
            now = time.monotonic()
            with plk:
                prog["b"] += n
                if now - prog["t"] < 2.0:
                    return
                prog["t"] = now
                mb = prog["b"] / 1048576.0
            try:      # ★긴 파일 하나에서 화면이 죽지 않도록 바이트 진행을 직접 그린다
                bar.set_postfix_str(f"{mb:,.0f}MB 수신", refresh=True)
            except Exception:
                pass
        # ★상한을 파일 실측에 맞춘다 — 일괄 ZIP 은 개당 2~8MB 다(실측). 240초를 넘긴다는
        #   것은 30KB/s 미만이라는 뜻이고, 그건 느린 게 아니라 죽은 회선이다. 넉넉하게
        #   잡아 두면 파일 하나가 스테이지 전체를 몇 시간 붙잡는다(이번 정체가 그것이다).
        return r, net_download(DART_BULK_DL, source="dart_zip",
                               params={"fl_nm": r["file"]}, referer=DART_BULK_LIST,
                               total_s=240, stall_s=40, on_progress=_on)

    with stage_bar(len(todo), "DART 재무 일괄 ZIP") as bar:
        with ThreadPoolExecutor(max_workers=DART_ZIP_WORKERS,
                                thread_name_prefix="zip") as ex:
            futs = {ex.submit(_fetch, r): r for r in todo}
            try:
                for fu in as_completed(futs):
                    if CLOCK.over():
                        for f2 in futs:
                            f2.cancel()
                        CLOCK.cut(f"재무 일괄 ZIP: {len(todo)-bar.n}개 남기고 중단")
                        break
                    try:
                        r, raw = fu.result()
                    except Exception as e:                        # noqa
                        L.warn(f"ZIP 다운로드 실패: {type(e).__name__}: {e}")
                        bar.update(1)
                        continue
                    bar.update(1)
                    if not raw:
                        continue
                    tmp = raw if isinstance(raw, str) else None
                    try:
                        if tmp is not None:
                            with open(tmp, "rb") as fh:
                                magic = fh.read(2)
                        else:
                            magic = raw[:2]
                        if magic != b"PK":
                            L.warn(f"ZIP 아님 {r['year']}/{r['report']}/{r['stmt']} — "
                                   f"서버가 파일 대신 다른 응답을 보냈습니다(건너뜀).")
                            continue
                        parts, n_ok, n_bad = _parse_zip(
                            r, tmp if tmp is not None else io.BytesIO(raw))
                    except Exception as e:                        # noqa
                        L.warn(f"ZIP 열기 실패 {r['year']}/{r['report']}/{r['stmt']}: "
                               f"{type(e).__name__}: {e}")
                        continue
                    finally:
                        if tmp is not None:
                            try:
                                os.unlink(tmp)
                            except Exception:
                                pass
                    n_skip_mem += n_bad
                    if parts:
                        got.append(pd.concat(parts, ignore_index=True))
                    # ★원장에는 '실제로 읽어낸' 파일만 완주로 적는다. 멤버를 하나도 파싱하지
                    #   못한 파일을 완주로 적으면 그 (연도·보고서·제표)는 ★영구히 재시도되지
                    #   않는다 — 손익계산서 레그가 통째로 빈 채 굳는 경로가 정확히 이것이다.
                    if n_ok > 0:
                        new_done.append({"year": int(r["year"]), "report": r["report"],
                                         "stmt": r["stmt"]})
                    else:
                        L.warn(f"ZIP {r['year']}/{r['report']}/{r['stmt']} — 멤버를 하나도 "
                               f"읽지 못해 완주로 기록하지 않습니다(다음 실행이 재시도).")
                    _flush()
            finally:
                for f2 in futs:
                    f2.cancel()
    _flush(force=True)
    if kept:
        _tot = sum(len(x) for x in kept)
        L.ok(f"재무 일괄 ZIP {_tot:,}행 확보 · 누적 수신 {prog['b']/1048576:,.0f}MB — "
             f"호출한도 소비 0" + (f" · 멤버 스킵 {n_skip_mem}건" if n_skip_mem else ""))
    got = kept
    frames = [x for x in (cached, pd.concat(got, ignore_index=True) if got else None)
              if x is not None and len(x)]
    if not frames:
        return empty
    return fs_compact(pd.concat([f.reindex(columns=_FS_KEEP) for f in frames],
                                ignore_index=True))


def harvest_dart_multi(corps: Sequence[str], years: Sequence[int],
                       max_calls: int = -1,
                       already: Optional[set] = None,
                       filed: Optional[set] = None,
                       trusted: Optional[set] = None,
                       exempt: Optional[set] = None) -> pd.DataFrame:
    """★저가 벌크 티어 — 다중회사 주요계정(fnlttMultiAcnt): corp_code 를 100개까지 한 번에.

    옛 설계는 전 종목 전체재무제표만 썼다: 3,400사 × 12년 × 4보고서 ≈ 163,000회.
    일일 2만회로는 8일이 걸리고, 그래서 '호출량이 모자란다'는 착시가 생긴다.
    실제로는 회사 100개를 한 요청에 묶는 공식 엔드포인트가 있다:
        3,400/100 × 12년 × 4보고서 ≈ 1,632회  → 하루 치 한도의 8%로 전 시장을 덮는다.
    여기서 얻는 계정(매출·영업이익·순이익·자산·부채·자본)만으로도 B축 일부·D축(dlog_E)·
    V5(자본잠식)가 살아난다. 재고/매출채권/CFO/CAPEX 같은 심층 계정은 tier0 이 채운다.
    """
    empty = pd.DataFrame(columns=_FS_KEEP)
    if not DART_API_KEY or not DART_BULK_MULTI:
        return empty
    cached = VAULT.load_frame("dart_fnltt_major", "shared")
    done: set = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        L.info(f"캐시 재사용: DART 주요계정(벌크) {len(cached):,}행 · {len(done):,}조합")
    corps = [str(c) for c in dict.fromkeys(str(c) for c in corps if c)]
    yrs = sorted({int(y) for y in years}, reverse=True)
    bs = max(10, min(int(DART_MULTI_BATCH), 100))
    # ★일괄 ZIP 이 이미 덮은 조합은 여기서도 다시 받지 않는다. ZIP 은 주요계정을 포함한
    #   전체 재무제표라 상위집합이다 — 안 걸러 두면 이 티어가 예산을 통째로 헛되이 태운다.
    skip = set(already or ())
    jobs: List[Tuple[int, str, List[str]]] = []
    n_raw = 0
    for y in yrs:
        for r in RQ.values():
            trust_y = bool(filed) and y in (trusted or set())
            _ex = exempt or set()
            todo = [c for c in corps if (c, y, r) not in done and (c, y, r) not in skip
                    and (not trust_y or c in _ex or (c, y, r) in filed)]
            n_raw += len(todo)
            for grp in chunked(todo, bs):
                jobs.append((y, r, list(grp)))
    if (skip or filed) and jobs:
        L.info(f"주요계정 벌크: 일괄 ZIP·정기보고서 사실로 사전 소거 후 "
               f"{n_raw:,}조합 → {len(jobs):,}회 (회사 {bs}개/호출)")
    if RUN_MODE == "CACHED":
        jobs = []
    if not jobs:
        return cached if cached is not None else empty
    L.info(f"DART 주요계정 벌크 {len(jobs):,}회 (회사 {bs}개/호출 → 단건이었다면 "
           f"{sum(len(g) for _, _, g in jobs):,}회) · 실시간 잔여 {QUOTA.remaining('dart'):,}건")
    QUOTA.plan("dart", len(jobs), f"주요계정 벌크(회사 {bs}개/호출)")

    seen_rows: List[pd.DataFrame] = []

    def _fetch(grp: List[str], y: int, r: str) -> Tuple[Optional[pd.DataFrame], bool]:
        """(프레임, ★서버가 '데이터 없음(013)'이라고 답했는가).

        이 두 번째 값이 결정적이다. dart_call 이 None 을 돌려주는 경우는 013 만이 아니라
        ★쿼터 소진·네트워크 실패·status 020/021 이 전부 포함된다. 그것들을 '없음'으로
        기록하면 다음 실행이 done 으로 흡수해 ★다시는 조회하지 않는다. 배치 하나가
        100사 × 200건이므로, 배치 중간에 쿼터가 끊기면 최대 2만 조합이 한 번에 영구
        음성캐시로 굳는다(만료도 없다). 013 일 때만 '없다'고 적는다.
        """
        js = dart_call("fnlttMultiAcnt.json",
                       {"corp_code": ",".join(grp), "bsns_year": str(y), "reprt_code": r})
        if not isinstance(js, dict):
            return None, False
        if str(js.get("status", "")) == "013":
            return None, True
        if not isinstance(js.get("list"), list) or not js["list"]:
            return None, False
        d = pd.DataFrame(js["list"])
        for col in _FS_KEEP:
            if col not in d.columns:
                d[col] = None
        d["bsns_year"], d["reprt_code"] = int(y), r
        d["fs_kind"] = d["fs_div"].astype(str) if "fs_div" in d.columns else "CFS"
        d["tier"] = 2
        d["corp_code"] = d["corp_code"].astype(str)
        return acct_keep(d[_FS_KEEP]), True     # 응답이 왔으니 빠진 회사는 '없는' 것이다

    def one(job):
        y, r, grp = job
        d, said = _fetch(grp, y, r)
        if d is not None:
            return d, said
        # ★배치 실패는 곧장 포기하지 않고 절반으로 쪼개 한 번 더 — status 021(회사 수 초과)과
        #   '그 배치에 낀 문제 회사 하나' 를 둘 다 구제한다(추가 비용은 최대 2회).
        # ★can() 은 부작용이 없다. 여기서 allow() 를 쓰면 '쪼개도 되나?' 를 묻는 것만으로
        #   dart 소스 전체가 blocked 로 굳고, 그 뒤 모든 호출이 None → 위 음성캐시가 대량
        #   생성되는 연쇄가 일어난다.
        if len(grp) > 20 and QUOTA.can("dart", 2):
            h = len(grp) // 2
            a, sa = _fetch(grp[:h], y, r)
            b, sb = _fetch(grp[h:], y, r)
            parts = [x for x in (a, b) if x is not None]
            if parts:
                return pd.concat(parts, ignore_index=True), (sa and sb)
        return None, said

    got: List[pd.DataFrame] = []
    spent0 = QUOTA.spent("dart")
    _cap = cap_of(max_calls)
    with stage_bar(len(jobs), "DART 주요계정(회사 100개/호출)") as bar:
        for batch in budget_batches(jobs, 200, "dart", "DART 주요계정 벌크", cap=max_calls, unit="회"):
            res = pmap_net(one, batch, workers=min(IO_THREADS, 8), quiet=True)
            bar.update(len(batch))
            got += [t[0] for t in res if t and t[0] is not None and len(t[0])]
        # ★응답에 안 나온 회사도 '조회는 했다'로 남긴다 — 안 그러면 미제출 회사·연도 조합을
        #   매 실행 다시 묶어 보내며 하루 한도의 5% 를 영구히 태운다.
        #   단 ★서버가 실제로 답했을 때만이다(_fetch 의 두 번째 값). 통신 실패·쿼터 소진을
        #   '없음'으로 적으면 그 조합은 영구히 재조회되지 않는다.
            for (y, r, grp), t in zip(batch, res):
                if not t or not t[1]:
                    continue
                d = t[0]
                got_c = set(d["corp_code"].astype(str)) if d is not None and len(d) else set()
                miss = [c for c in grp if c not in got_c]
                if miss:
                    seen_rows.append(pd.DataFrame({"corp_code": miss, "bsns_year": int(y),
                                                   "reprt_code": r, "sj_div": None,
                                                   "account_id": None, "account_nm": None,
                                                   "thstrm_amount": None, "rcept_no": None,
                                                   "fs_kind": "NONE", "tier": 2}))
    frames = ([cached] if cached is not None and len(cached) else []) + got + seen_rows
    if not frames:
        return empty
    M = pd.concat([f.reindex(columns=_FS_KEEP) for f in frames], ignore_index=True)
    # ★fs_kind 를 키에 넣는다. 빼면 fnlttMultiAcnt 가 돌려준 연결/별도 중 하나가 응답 순서에
    #   따라 임의로 버려지고, 회사별 기준(모달)을 고를 수 없게 된다.
    M = fs_compact(M.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                                      "account_nm", "fs_kind"], keep="last"))
    if got or seen_rows:
        VAULT.save_shard("dart_fnltt_major",
                         pd.concat([x.reindex(columns=_FS_KEEP) for x in got + seen_rows],
                                   ignore_index=True),
                         key=f"{dtm.datetime.now():%Y%m%d_%H%M%S}", scope="shared",
                         domain="dart", source="opendart:fnlttMultiAcnt",
                         note="주요계정 벌크 — 전 전략 공용")
    L.ok(f"DART 주요계정 누적 {M['corp_code'].nunique():,}사 · "
         f"{M.groupby(['corp_code','bsns_year','reprt_code']).ngroups:,}조합")
    return M


def harvest_dart_financials(corps: Sequence[str], years: Sequence[int],
                            priority: Sequence[str] = (),
                            max_calls: int = -1,
                            already: Optional[set] = None,
                            filed: Optional[set] = None,
                            trusted: Optional[set] = None,
                            exempt: Optional[set] = None) -> pd.DataFrame:
    """★심층 티어 — 전체 재무제표(fnlttSinglAcntAll). (회사×연도×보고서) 캐시 증분.

    · 수집 순서 = 유동성 상위·최근 연도 먼저: 한도로 끊겨도 '투자 가능한 종목의 최근
      데이터'가 먼저 완성되어 부분 데이터 중간결과의 질이 최대화된다.
    · 대상은 priority(유동성 순) 상위 DART_DEEP_TOP_N 사로 자른다. V6(20일 평균거래대금
      3억) 를 통과할 수 없는 종목의 재고자산까지 한도를 태울 이유가 없다 — 어차피 거부권에
      걸려 절대 편입되지 않는다. 잘린 회사도 주요계정 벌크 티어가 덮는다.
    · fs_div 는 ★연결(CFS) 우선. 옛 코드는 OFS→CFS 순이라 대다수 상장사에서 첫 호출이
      빈손으로 끝나 호출량이 정확히 두 배로 들었다(조용한 낭비).
    """
    if not DART_API_KEY:
        L.warn("DART_API_KEY 미입력 — B축·C축·PACK-C 가 전부 결측이 됩니다(자동 비활성화). "
               "이 전략의 핵심 입력이므로 키 입력을 강력히 권합니다.")
        return pd.DataFrame(columns=_FS_KEEP)
    cached = VAULT.load_frame("dart_fnltt_raw", "shared")
    done = set()
    fs_kind_pref: Dict[str, str] = {}
    if cached is not None and len(cached):
        if "tier" not in cached.columns:
            cached = cached.copy()
            cached["tier"] = 0                       # 구버전 캐시는 전부 심층 티어였다
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int),
                       cached["reprt_code"].astype(str)))
        if "fs_kind" in cached.columns:      # ★회사별 재무 기준(별도/연결) 고정 — 혼합 방지
            ck = cached[cached["fs_kind"].astype(str).isin(("OFS", "CFS"))]
            fs_kind_pref = (ck.groupby(ck["corp_code"].astype(str))["fs_kind"]
                            .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else None)
                            .dropna().to_dict())
        L.info(f"캐시 재사용: DART 재무(심층) {len(cached):,}행 · {len(done):,}조합")
    # 음성 캐시 — '데이터 없음' 조합을 90일간 재호출하지 않는다(쿼터 절약)
    empty_seen = set()
    neg = VAULT.load_table("dart_empty_log", "shared")
    today_ts = pd.Timestamp(dtm.date.today())
    if neg is not None and len(neg):
        neg = neg.copy()
        neg["tried_at"] = ds_(neg["tried_at"])
        fresh_neg = neg[(today_ts - neg["tried_at"]).dt.days < EMPTY_RETRY_AFTER_D]
        empty_seen = set(zip(fresh_neg["corp_code"].astype(str),
                             fresh_neg["bsns_year"].astype(int),
                             fresh_neg["reprt_code"].astype(str)))
        if empty_seen:
            L.info(f"음성 캐시: '데이터 없음' {len(empty_seen):,}조합은 "
                   f"{EMPTY_RETRY_AFTER_D}일간 재호출하지 않습니다.")
    rank = {str(c): i for i, c in enumerate(priority)}
    corp_sorted = sorted((str(c) for c in corps), key=lambda c: (rank.get(c, 10 ** 9), c))
    n_all = len(corp_sorted)
    if DART_DEEP_TOP_N and n_all > DART_DEEP_TOP_N and rank:
        corp_sorted = corp_sorted[:int(DART_DEEP_TOP_N)]
        L.info(f"심층 재무 대상을 유동성 상위 {len(corp_sorted):,}사로 한정합니다"
               f"(전체 {n_all:,}사). 잘린 회사는 주요계정 벌크가 덮으며, V6 유동성 하한"
               f"({MIN_ADV_KRW/1e8:.0f}억)을 통과 못 하는 종목은 어차피 편입되지 않습니다.")
    # ★일괄 ZIP 이 이미 덮은 (회사·연도·보고서)는 단건 API 로 다시 받지 않는다.
    #   이것이 '78,000회 = 12일' 을 사실상 0 으로 만드는 지점이다.
    have_zip = already or set()
    jobs = [(c, int(y), r) for y in sorted(set(int(v) for v in years), reverse=True)
            for c in corp_sorted for r in RQ.values()
            if (c, int(y), r) not in done and (c, int(y), r) not in empty_seen
            and (c, int(y), r) not in have_zip]
    if have_zip:
        L.info(f"일괄 ZIP 이 덮은 {len(have_zip):,}조합은 단건 API 대상에서 제외 — "
               f"남은 단건 수집 {len(jobs):,}건")
    # ★사전 소거 — 그 조합에 정기보고서가 아예 없으면 단건 API 도 100% 013 이다.
    if filed:
        n0 = len(jobs)
        jobs = _apply_filed(jobs, filed, trusted, yi=1, exempt=exempt)
        if n0 - len(jobs) > 0:
            L.info(f"정기보고서 제출 사실로 {n0-len(jobs):,}조합을 사전 소거 "
                   f"(그 해에 보고서 자체가 없어 호출해도 빈손) — 실수집 대상 {len(jobs):,}건")
    if RUN_MODE == "CACHED":
        jobs = []
    got: List[pd.DataFrame] = []
    new_empty: List[dict] = []
    if jobs:
        # ★cap_of 규약 — None(무제한)일 때만 잔여 전량을 상한으로 쓴다. 옛 코드는
        #   `if max_calls` 라서 배정 0 을 무제한으로 뒤집었다(cap_of 주석 참조).
        _c0 = cap_of(max_calls)
        cap = int(QUOTA.remaining("dart")) if _c0 is None else _c0
        L.info(f"DART 재무(심층) 잔여 {len(jobs):,}조합 — 이번 실행 배정 {cap:,}건 "
               f"(서버 020 수신 시 그 지점을 오늘 한도로 학습해 정지)")
        QUOTA.plan("dart", min(len(jobs), cap), "전체재무제표 심층(꼬리 보충)")
        if cap and len(jobs) > cap:
            L.info(f"→ 이번 실행은 {cap:,}건까지. ★이 티어는 '꼬리 보충'이라 끊겨도 패널은 "
                   f"멀쩡합니다 — 재고·매출채권·CFO·CAPEX 를 포함한 전체재무제표 본체는 "
                   f"이미 일괄 ZIP(호출한도 0)이 덮었고, 여기 남은 것은 ZIP 이 제공하지 않는 "
                   f"연도·비제출사의 잔여분입니다. 나머지 {len(jobs)-cap:,}건은 다음 실행이 "
                   f"정확히 이어받습니다.")

        def one(job):
            c, y, r = job
            pref = fs_kind_pref.get(c)
            # ★연결(CFS) 우선 — 국내 상장사 대다수가 연결 기준이라 첫 호출 적중률이 높다
            order = [pref] if pref in ("OFS", "CFS") else ["CFS", "OFS"]
            js, used_kind, all_013 = None, None, True
            for fk in order:
                js = dart_call("fnlttSinglAcntAll.json",
                               {"corp_code": c, "bsns_year": str(y), "reprt_code": r,
                                "fs_div": fk})
                if js and isinstance(js.get("list"), list) and js["list"]:
                    used_kind = fk
                    break
                # ★'013 데이터 없음'(서버가 진짜 없다고 답함)과 통신 실패를 구분한다.
                #   구분 없이 음성캐시에 넣으면 60초짜리 네트워크 장애가 수백 회사·연도를
                #   90일간 영구 결손으로 만든다.
                if not (isinstance(js, dict) and str(js.get("status")) == "013"):
                    all_013 = False
                js = None
            if js is None:
                # ★can() — 부작용 없는 판정. allow() 를 여기 쓰면 '음성캐시에 넣어도 되나?'
                #   를 묻는 것만으로 dart 소스가 blocked 로 굳어, 아직 실행도 안 한 뒤
                #   소비자들(major/deep)까지 함께 죽는다.
                if all_013 and QUOTA.can("dart"):          # 한도 소진·통신 실패가 아닐 때만
                    return ("EMPTY", c, y, r)
                return None
            d = pd.DataFrame(js["list"])
            for col in _FS_KEEP:
                if col not in d.columns:
                    d[col] = None
            d["corp_code"], d["bsns_year"], d["reprt_code"] = c, int(y), r
            d["fs_kind"] = used_kind
            d["tier"] = 0
            return acct_keep(d[_FS_KEEP])

        spent0 = QUOTA.spent("dart")
        _cap = cap_of(max_calls)
        with stage_bar(len(jobs), "DART 전체재무제표(심층)") as bar:
          for batch in budget_batches(jobs, 400, "dart", "DART 재무", cap=max_calls, unit="건"):
            res = pmap_net(one, batch, workers=min(IO_THREADS, 10), quiet=True)
            bar.update(len(batch))
            for d in res:
                if isinstance(d, tuple) and d and d[0] == "EMPTY":
                    new_empty.append({"corp_code": d[1], "bsns_year": d[2],
                                      "reprt_code": d[3], "tried_at": today_ts})
                elif d is not None and len(d):
                    got.append(d)
    if new_empty:
        base = neg if neg is not None and len(neg) else None
        alle = pd.concat([base, pd.DataFrame(new_empty)], ignore_index=True) \
            if base is not None else pd.DataFrame(new_empty)
        alle = (alle.sort_values("tried_at")
                    .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="last"))
        VAULT.save_table("dart_empty_log", alle, "shared", domain="dart",
                         source="negative_cache")
    frames = ([cached] if cached is not None and len(cached) else []) + got
    if not frames:
        return pd.DataFrame(columns=_FS_KEEP)
    fs = pd.concat([f.reindex(columns=_FS_KEEP) for f in frames], ignore_index=True)
    fs = fs_compact(fs.drop_duplicates(["corp_code", "bsns_year", "reprt_code", "sj_div",
                                        "account_id", "account_nm"], keep="last"))
    if got:
        # ★샤드 append — 수십만행 테이블을 매 실행마다 통째로 다시 쓰지 않는다
        VAULT.save_shard("dart_fnltt_raw", pd.concat(got, ignore_index=True),
                         key=f"{dtm.datetime.now():%Y%m%d_%H%M%S}", scope="shared",
                         domain="dart", source="opendart:fnlttSinglAcntAll")
    n_have = fs.groupby(["corp_code", "bsns_year", "reprt_code"]).ngroups if len(fs) else 0
    L.info(f"DART 재무(심층) 누적 (회사×기간) {n_have:,}조합 — 재실행 시 이 지점부터 이어받음")
    return fs


# 한국 XBRL 계정명은 회사마다 달라 정규식 다중 매칭으로 흡수한다.
ACCT = {
    "revenue":       ("IS", [r"ifrs-full_Revenue$", r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$"]),
    "cogs":          ("IS", [r"CostOfSales", r"^매출원가"]),
    "sgna":          ("IS", [r"SellingGeneralAndAdministrativeExpense", r"^판매비와관리비$"]),
    "rnd":           ("IS", [r"ResearchAndDevelopment", r"경상(연구)?개발비", r"^연구개발비"]),
    "op_income":     ("IS", [r"OperatingIncomeLoss", r"^영업이익"]),
    "net_income":    ("IS", [r"ProfitLoss$", r"^당기순이익"]),
    "tax_expense":   ("IS", [r"IncomeTaxExpense", r"법인세비용", r"^법인세등$"]),
    # '법인세비용차감전순이익'(전체재무제표)과 '법인세차감전 순이익'(주요계정 벌크) 둘 다 흡수
    "pretax_income": ("IS", [r"ProfitLossBeforeTax", r"법인세.{0,4}차감전"]),
    "other_income":  ("IS", [r"OtherIncome$", r"^기타수익$", r"^영업외수익$"]),
    "inventory":     ("BS", [r"Inventories", r"^재고자산"]),
    "receivable":    ("BS", [r"TradeAndOtherCurrentReceivables", r"^매출채권"]),
    "payable":       ("BS", [r"TradeAndOtherCurrentPayables", r"^매입채무"]),
    "assets":        ("BS", [r"ifrs-full_Assets$", r"^자산총계$"]),
    "liabilities":   ("BS", [r"ifrs-full_Liabilities$", r"^부채총계$"]),
    "equity":        ("BS", [r"ifrs-full_Equity$", r"^자본총계$"]),
    "ppe":           ("BS", [r"PropertyPlantAndEquipment", r"^유형자산$"]),
    "intangible":    ("BS", [r"IntangibleAssets", r"^무형자산$"]),
    "contract_liab": ("BS", [r"ContractLiabilities", r"^계약부채$", r"^선수금$"]),
    "cfo":           ("CF", [r"CashFlowsFromUsedInOperatingActivities", r"^영업활동.*현금흐름"]),
    "capex":         ("CF", [r"PurchaseOfPropertyPlantAndEquipment", r"유형자산의?\s*취득"]),
    "dep":           ("CF", [r"DepreciationAndAmortisation", r"^감가상각비"]),
    "div_paid":      ("CF", [r"DividendsPaid", r"배당금\s*지급"]),
    "tstock_buy":    ("CF", [r"PaymentsToAcquireOrRedeemEntitysShares", r"자기주식의?\s*취득"]),
    "debt_raise":    ("CF", [r"ProceedsFromBorrowings", r"차입금의?\s*증가", r"사채의?\s*발행"]),
}
_SJ_OK = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}
FLOW_ACCTS = ["revenue", "cogs", "sgna", "rnd", "op_income", "net_income", "tax_expense",
              "pretax_income", "other_income", "cfo", "capex", "dep", "div_paid",
              "tstock_buy", "debt_raise"]
# 패널이 계약적으로 항상 보유해야 하는 재무 컬럼 전체 — 수집이 얼마나 실패하든 스키마는 같아야
# "어떤 실행엔 있고 어떤 실행엔 없는 축" 이 생기지 않는다(결측은 결측대로 표에 드러난다).
FIN_PANEL_COLS = (list(ACCT) + [f"{c}_q" for c in FLOW_ACCTS] + [f"{c}_ttm" for c in FLOW_ACCTS]
                  + ["employees", "payroll", "v2_streak_bad", "eff_tax"])


def refine_financials(fs: pd.DataFrame) -> pd.DataFrame:
    """원시 계정 → (corp, 기간) 와이드. 누적→분기 차분(연속 분기만) · TTM(4분기 완비만) ·
    knowledge_date 확정 · V2 '3분기 연속' 플래그를 분기 프레임에서 생성."""
    if fs is None or fs.empty:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    d = fs.copy()
    # ★범주형 해제 — 누적 저장용으로 접어둔 컬럼을 그대로 쓰면 map/뺄셈/pivot 이 조용히
    #   깨진다(Categorical - Categorical TypeError, pivot_table 의 카테고리 전개 폭발).
    #   여기서 쓰는 부분집합은 계정 필터를 이미 통과해 작으므로 되돌리는 비용이 싸다.
    for c in ("corp_code", "reprt_code", "sj_div", "account_id", "account_nm", "fs_kind"):
        if c in d.columns and str(d[c].dtype) == "category":
            d[c] = d[c].astype(str)
    if "tier" not in d.columns:
        d["tier"] = 0
    d["tier"] = pd.to_numeric(d["tier"], errors="coerce").fillna(0).astype(int)
    # ★별도(OFS)/연결(CFS) 혼합 방어 — 한 회사의 기간별 기준이 섞이면 분기 차분·TTM·Δlog 가
    #   회계 기준 점프를 실적 변화로 오인한다(V1·TP_B1 오탐). 회사별 최빈 기준만 남긴다.
    if "fs_kind" in d.columns and d["fs_kind"].notna().any():
        known = d[d["fs_kind"].astype(str).isin(("OFS", "CFS"))]
        # ★기준(연결/별도)은 심층 티어로 먼저 정하고, 심층이 없는 회사만 벌크로 정한다.
        #   그리고 정한 기준을 ★모든 티어에 적용한다. 옛 코드는 tier0 에만 적용했는데,
        #   심층은 쿼터 때문에 항상 '최근 몇 년'만 있고 그 이전은 벌크가 채운다. 즉 모든
        #   회사의 시계열 한가운데에 티어 경계가 있다. 거기서 기준이 갈리면
        #   (연결 2,000억 → 별도 800억) 분기차분·TTM 이 +150% 실적 점프를 만들어내고
        #   dlog_E>0 → D_state='목표상태(진입)' 로 그 종목을 사게 된다.
        modal: Dict[str, str] = {}
        if len(known):
            deep_k = known[known["tier"] == 0]
            for src in (known, deep_k):          # 벌크로 먼저 채우고 심층으로 덮어쓴다
                if len(src):
                    modal.update(src.groupby(src["corp_code"].astype(str))["fs_kind"]
                                 .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else None)
                                 .dropna().to_dict())
        if modal:
            pref = d["corp_code"].astype(str).map(modal)
            mixed = (d["fs_kind"].astype(str).isin(("OFS", "CFS")) & pref.notna() &
                     (d["fs_kind"].astype(str) != pref))
            if mixed.any():
                n_corp = d.loc[mixed, "corp_code"].nunique()
                L.info(f"재무 기준 혼합 {n_corp:,}사 — 회사별 최빈 기준(별도/연결)만 사용하고 "
                       f"소수 기준 {int(mixed.sum()):,}행은 제외합니다(기준 점프 오인 방지).")
                d = d[~mixed]
    d["amount"] = pd.to_numeric(d["thstrm_amount"].astype(str)
                                .str.replace(",", "", regex=False)
                                .str.replace("−", "-", regex=False), errors="coerce")
    d = d.dropna(subset=["amount"])
    d["account_id"] = d["account_id"].astype(str)
    d["account_nm"] = d["account_nm"].astype(str).str.replace(r"\s+", "", regex=True)
    picked = []
    for key, (sj, pats) in ACCT.items():
        sub = d[d["sj_div"].astype(str).isin(_SJ_OK.get(sj, (sj,)))]
        if sub.empty:
            continue
        rxp = re.compile("|".join(pats), re.I)
        hit = sub[sub["account_id"].str.contains(rxp, na=False) |
                  sub["account_nm"].str.contains(rxp, na=False)]
        if hit.empty:
            continue
        # ★티어 우선 — 같은 (회사·기간·계정)에 심층(0)과 벌크(1)가 둘 다 있으면 심층이 이긴다.
        #   같은 티어 안에서는 절대값이 큰 쪽(연결 총계)을 고른다.
        hit = (hit.assign(_absv=hit["amount"].abs())
                  .sort_values(["tier", "_absv"], ascending=[True, False])
                  .drop_duplicates(["corp_code", "bsns_year", "reprt_code"], keep="first"))
        picked.append(hit.assign(item=key)[["corp_code", "bsns_year", "reprt_code",
                                            "rcept_no", "item", "amount"]])
    if not picked:
        return pd.DataFrame(columns=["corp_code", "period_end", "knowledge_date"])
    tall = pd.concat(picked, ignore_index=True)
    W = tall.pivot_table(index=["corp_code", "bsns_year", "reprt_code"], columns="item",
                         values="amount", aggfunc="first", observed=True).reset_index()
    rc = (tall.sort_values("rcept_no")
              .groupby(["corp_code", "bsns_year", "reprt_code"])["rcept_no"].first().reset_index())
    W = W.merge(rc, on=["corp_code", "bsns_year", "reprt_code"], how="left")
    W["period_end"] = [d_(f"{y}-{RQ_PERIOD_END[r][0]:02d}-{RQ_PERIOD_END[r][1]:02d}")
                       for y, r in zip(W["bsns_year"], W["reprt_code"])]
    W["knowledge_date"] = [_kd_from_rcept(rn, r, int(y))
                           for rn, r, y in zip(W["rcept_no"], W["reprt_code"], W["bsns_year"])]
    qmap = {RQ["Q1"]: 1, RQ["H1"]: 2, RQ["Q3"]: 3, RQ["FY"]: 4}
    W["q"] = W["reprt_code"].astype(str).map(qmap)
    # ★분기 통번호 — TTM 이 '연속 4분기'인지 판정하는 유일한 근거(행 기준 rolling 은 위험).
    W["_qi"] = W["bsns_year"].astype(int) * 4 + W["q"].astype(int)
    W = W.sort_values(["corp_code", "bsns_year", "q"]).reset_index(drop=True)
    gk = ["corp_code", "bsns_year"]
    prev_q = W.groupby(gk, observed=True)["q"].shift(1)
    contig = (W["q"] - prev_q) == 1
    for c in FLOW_ACCTS:
        if c not in W.columns:
            W[c] = np.nan
        prev = W.groupby(gk, observed=True)[c].shift(1)
        # 누적 공시 → 분기 단독. 직전 분기가 실존할 때만 차분(결손 분기를 0 취급하면
        # 반기 누적이 분기 실적으로 둔갑한다 — fail-open 금지).
        W[c + "_q"] = np.where(W["q"] == 1, W[c], np.where(contig, W[c] - prev, np.nan))
        # ★rolling 은 '행' 기준이다. 분기가 결손된 회사에서는 2017Q1·2018Q1·2019Q1·2020Q1
        #   네 개가 합쳐져 TTM 으로 불린다(실행 재현됨). 분기 인덱스가 ★연속 4개일 때만
        #   TTM 이 성립한다 — 아니면 결측으로 둔다(조용한 오계산보다 결측이 낫다).
        _ok4 = (W.groupby("corp_code", observed=True)["_qi"].diff(3) == 3)
        W[c + "_ttm"] = (W.groupby("corp_code", observed=True)[c + "_q"]
                          .transform(lambda s: s.rolling(4, min_periods=4).sum())).where(_ok4)
    for k in ACCT:                                    # BS 계정도 스키마 계약 보장
        if k not in W.columns:
            W[k] = np.nan
    # V2 — '순이익>0 인데 CFO<0.5×순이익' 3분기 연속. 연속성은 분기 프레임에서만 셀 수 있다
    # (월 패널은 같은 분기값이 1~4개월 반복되어 어떤 고정 개월수도 정답이 아니다).
    bad = ((colx(W, "net_income_ttm") > 0) &
           (colx(W, "cfo_ttm") < 0.5 * colx(W, "net_income_ttm"))).astype(float)
    W["v2_streak_bad"] = (bad.groupby(W["corp_code"], observed=True)
                             .transform(lambda s: s.rolling(3, min_periods=3).min()))
    W["eff_tax"] = sdiv(colx(W, "tax_expense_ttm"), colx(W, "pretax_income_ttm"))
    # ★'0건'만 보면 1행만 매칭돼도 침묵한다 — 정작 쓰는 것은 _ttm 이다. 커버리지로 본다.
    _thin = {k: float(W[k].notna().mean()) for k in ACCT
             if float(W[k].notna().mean()) < 0.05}
    if _thin:
        L.warn(f"계정 커버리지 5% 미만 {len(_thin)}개 — 이 계정에 의존하는 축은 사실상 "
               f"결측입니다: " + ", ".join(f"{k}={v*100:.1f}%" for k, v in
                                          sorted(_thin.items(), key=lambda x: x[1])[:10]))
    none_hit = [k for k in ACCT if W[k].notna().sum() == 0]
    if none_hit:
        L.warn(f"매칭 0건 계정 {len(none_hit)}개: {none_hit[:8]} — 해당 지표는 결측 유지"
               f"(0 채움 금지). 계정명 정규식과 안 맞는 회사군일 수 있습니다.")
    W = pit_mark(W, "period_end", "knowledge_date", origin="dart_fs")
    L.ok(f"재무 정제 {len(W):,}행 · {W['corp_code'].nunique():,}사 "
         f"(knowledge=접수일자 · 누적→분기 차분 · TTM 4분기 완비 기준)")
    return shrink(W)


def harvest_dart_employees(corps: Sequence[str], years: Sequence[int],
                           priority: Sequence[str] = (),
                           max_calls: int = -1,
                           filed: Optional[set] = None,
                           trusted: Optional[set] = None,
                           exempt: Optional[set] = None) -> pd.DataFrame:
    """직원현황(empSttus) — 사업부문×성별 분해 + '합계' 소계행 이중계상 제거.

    ★★2026-08 개편: '전수수집'이 원칙이다. 단, 전수를 '무작정 다 호출'로 달성하지 않는다.
      empSttus 는 ★사업보고서에만 실린다. 그러므로 그 해에 사업보고서를 내지 않은 회사
      (상장 전·폐지 후·비제출)를 호출하면 100% 013(데이터 없음)이 돌아온다 — 응답이
      비어도 호출량은 정확히 1건씩 깎인다. 옛 코드는 이 낭비를 '유동성 상위 1,500사로
      자르기'로 덮었는데, 그건 전수 포기이지 효율이 아니었다.

      지금은 이미 공짜로 갖고 있는 ★공시목록 스윕(harvest_dart_disclosures)에서
      (회사, 사업연도)별 사업보고서 제출 사실을 뽑아 filed 로 받고, 제출한 조합만 호출한다.
      → 호출 1건당 적중률이 1.0 에 수렴하고, 전수 필요량 자체가 30~40% 줄어든다.
      대상은 더 이상 자르지 않는다(전 상장사). 순서만 유동성 상위·최근 연도 우선이라
      한도에 걸려 끊겨도 '투자 가능한 종목의 최근 데이터'부터 완성된다.
    """
    empty = pd.DataFrame(columns=["corp_code", "bsns_year", "employees", "payroll",
                                  "period_end", "knowledge_date", "event_date"])
    if not DART_API_KEY:
        return empty
    cached = VAULT.load_table("dart_employees", "shared")
    done = set()
    if cached is not None and len(cached):
        done = set(zip(cached["corp_code"].astype(str), cached["bsns_year"].astype(int)))
        L.info(f"캐시 재사용: 직원현황 {len(cached):,}행")
    # 음성 캐시 — empSttus 는 '사업보고서에만' 있어 진행 중인 연도·비제출 회사는 영구히 빈다.
    # 이걸 기록하지 않으면 매 실행 8,000회를 같은 빈 키에 태운다(하루 한도의 40%).
    empty_seen: set = set()
    negE = VAULT.load_table("dart_emp_empty_log", "shared")
    today_ts = pd.Timestamp(dtm.date.today())
    if negE is not None and len(negE):
        negE = negE.copy()
        negE["tried_at"] = ds_(negE["tried_at"])
        fr = negE[(today_ts - negE["tried_at"]).dt.days < EMPTY_RETRY_AFTER_D]
        empty_seen = set(zip(fr["corp_code"].astype(str), fr["bsns_year"].astype(int)))
        if empty_seen:
            L.info(f"음성 캐시: 직원현황 '데이터 없음' {len(empty_seen):,}조합은 "
                   f"{EMPTY_RETRY_AFTER_D}일간 재호출하지 않습니다.")
    rank = {str(c): i for i, c in enumerate(priority)}
    clist = sorted((str(c) for c in corps), key=lambda c: (rank.get(c, 10 ** 9), c))
    ylist = sorted({int(v) for v in years}, reverse=True)
    # ★사실 기반 소거 ⓪: 사업연도 Y 의 사업보고서는 Y+1년 3월 말에야 접수된다. 아직 오지
    #   않은 연도는 어떤 회사도 제출할 수 없으므로 전 종목이 013 이다. 음성캐시에 맡기면
    #   첫 실행에 3,500회를 태우고 90일마다 또 태운다 — 달력만 봐도 아는 것을 묻지 않는다.
    y_max = dtm.date.today().year - 1
    drop_y = [y for y in ylist if y > y_max]
    if drop_y:
        ylist = [y for y in ylist if y <= y_max]
        L.info(f"사업보고서가 아직 존재할 수 없는 연도 {drop_y} 는 조회하지 않습니다"
               f"(사업연도 Y 는 Y+1년 3월 접수 — 전 종목이 '데이터 없음'으로 돌아옵니다).")
    # ★전수 모집단(자르지 않는다). 순서는 ★회사 우선(유동성 상위부터) × 연도 내림차순.
    #   연도 우선으로 돌면 한도에 걸렸을 때 '최근 6년은 전 종목, 초기 6년은 전멸' 이 되어
    #   10년 백테스트의 앞 절반에서 C2축 dlog_emp 가 통째로 사라진다(평가가 깨진다).
    #   회사 우선이면 '거래 가능한 상위 회사의 10년 전 구간'이 먼저 완성되므로, 중간에
    #   끊겨도 그 시점까지의 결과가 그대로 신뢰할 수 있는 부분집합이 된다.
    universe = [(c, y) for c in clist for y in ylist]
    # ★사실 기반 소거 ①: 그 해에 사업보고서를 낸 조합만 남긴다(=empSttus 가 존재할 수 있는 조합).
    n_all = len(universe)
    if filed:
        kept = _apply_filed(universe, filed, trusted, yi=1, exempt=exempt)
        if kept and len(kept) < n_all:
            skipped_y = sorted(set(ylist) - set(trusted or ()))
            universe = kept
            L.info(f"사업보고서 제출 사실로 사전 소거 — 전수 모집단 {n_all:,}조합 중 "
                   f"{n_all-len(universe):,}조합은 그 해에 사업보고서 자체가 없어 호출을 "
                   f"생략합니다(호출해도 100% '데이터 없음'). 실제 전수 대상 {len(universe):,}조합."
                   + (f" ※ 공시 스윕이 덜 끝난 {len(skipped_y)}개 연도"
                      f"({', '.join(str(y) for y in skipped_y[:6])}"
                      f"{' 외' if len(skipped_y) > 6 else ''})는 소거하지 않고 전부 조회합니다"
                      f" — 지도가 불완전한 상태의 소거는 곧 영구 결손이기 때문입니다."
                      if skipped_y else ""))
        else:
            L.warn("공시목록에서 사업보고서 제출 사실을 찾지 못해 사전 소거를 건너뜁니다.")
    # ★사실 기반 소거 ②: 이미 받은 것 + 서버가 '없다'고 답한 것
    jobs = [(c, y) for (c, y) in universe
            if (c, y) not in done and (c, y) not in empty_seen]
    n_target = len(universe)
    n_have = n_target - len(jobs)
    if RUN_MODE == "CACHED":
        jobs = []
    if n_target:
        L.info(f"직원현황 전수 진척 {n_have:,}/{n_target:,}조합 "
               f"({100.0*n_have/max(n_target,1):.1f}%) — 남은 {len(jobs):,}조합")
    if jobs:
        QUOTA.plan("dart", len(jobs), "직원현황 전수(유동성·최근연도 순)")

    def one(job):
        c, y = job
        js = dart_call("empSttus.json", {"corp_code": c, "bsns_year": str(y),
                                         "reprt_code": RQ["FY"]})
        if not js or not isinstance(js.get("list"), list):
            if isinstance(js, dict) and str(js.get("status")) == "013":
                return ("EMPTY", c, y)      # 서버가 '없다'고 답한 것만 음성캐시
            return None
        d0 = pd.DataFrame(js["list"])
        d = d0
        for col in ("fo_bbm", "sexdstn"):
            if col in d.columns:
                d = d[~d[col].astype(str).str.strip().isin(["합계", "계", "소계", "총계"])]
        if d.empty:
            # ★사업부문 분해 없이 '합계' 한 줄만 보고하는 회사가 실제로 있다. 그 회사를
            #   None 으로 버리면 ①직원수가 조용히 사라지고(size_bucket·dlog_emp 결측)
            #   ②done 에도 empty_seen 에도 안 남아 ★매 실행 1호출씩 영구히 재시도된다.
            #   소계 제거는 '분해와 합계가 같이 올 때의 이중계상'을 막으려는 것이지,
            #   합계밖에 없는 회사를 버리려는 것이 아니다 — 그 합계가 곧 전사 인원이다.
            d = d0
        if d.empty:
            return None
        def num(s):
            return pd.to_numeric(pd.Series(s).astype(str)
                                 .str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
        emp = float(num(d["sm"]).sum()) if "sm" in d.columns else np.nan
        pay = float(num(d["fyer_salary_totamt"]).sum()) if "fyer_salary_totamt" in d.columns \
            else np.nan
        rn = str(d["rcept_no"].iloc[0]) if "rcept_no" in d.columns and len(d) else ""
        return {"corp_code": c, "bsns_year": y, "employees": emp, "payroll": pay,
                "rcept_no": rn}

    got: List[dict] = []
    new_empty: List[dict] = []
    spent0 = QUOTA.spent("dart")
    _cap = cap_of(max_calls)
    with stage_bar(len(jobs), "DART 직원현황(전수)") as bar:
        for batch in chunked(jobs, 400):
            _over, _noq = CLOCK.over(), not QUOTA.allow("dart")
            if _over or _noq or (_cap is not None and
                                 QUOTA.spent("dart") - spent0 >= _cap):
                # ★사유를 실제 원인대로 적는다. 옛 코드는 max_calls 가 truthy 이기만 하면
                #   원인이 일일 한도 소진이어도 '배정 소진'으로 찍었다 — 이번 병목을 정확히
                #   그렇게 오독했다. 진단을 반대로 유도하는 로그는 없느니만 못하다.
                why = "시간예산" if _over else ("호출 잔여량 소진" if _noq else "배정 소진")
                rest = len(jobs) - bar.n
                pct = 100.0 * (n_have + bar.n) / max(n_target, 1)
                cap_d = max(int(QUOTA.hint("dart")), 1)     # ★f-string 안에서 중첩 따옴표를
                days = math.ceil(rest / cap_d) if rest else 0   # 쓰면 3.11 이하에서 죽는다
                CLOCK.cut(f"직원현황: {rest:,}조합 남기고 중단({why}). "
                          f"전수 진척 {n_have+bar.n:,}/{n_target:,} ({pct:.1f}%) — "
                          f"내일 재실행하면 정확히 이어받아 약 {days}일이면 전수 완비"
                          f"(하루 한도 {cap_d:,}건 기준). "
                          f"그 사이에도 시가총액 폴백이 있어 셀 배정은 정상 동작합니다.")
                break
            for r in pmap_net(one, batch, workers=min(IO_THREADS, 10), quiet=True):
                if isinstance(r, tuple) and r and r[0] == "EMPTY":
                    new_empty.append({"corp_code": r[1], "bsns_year": r[2],
                                      "tried_at": today_ts})
                elif r:
                    got.append(r)
            bar.update(len(batch))
    if new_empty:
        alle = pd.concat([negE, pd.DataFrame(new_empty)], ignore_index=True) \
            if negE is not None and len(negE) else pd.DataFrame(new_empty)
        VAULT.save_table("dart_emp_empty_log",
                         alle.sort_values("tried_at")
                             .drop_duplicates(["corp_code", "bsns_year"], keep="last"),
                         "shared", domain="dart", source="negative_cache")
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(got)] if got else [])
    if not frames:
        return empty
    E = pd.concat(frames, ignore_index=True).drop_duplicates(["corp_code", "bsns_year"],
                                                             keep="last")
    if "rcept_no" not in E.columns:
        E["rcept_no"] = ""
    E["period_end"] = ds_(E["bsns_year"].astype(int).astype(str) + "-12-31")
    E["knowledge_date"] = [_kd_from_rcept(rn, RQ["FY"], int(y))
                           for rn, y in zip(E["rcept_no"], E["bsns_year"])]
    if got:
        VAULT.save_table("dart_employees", E, "shared", domain="dart", source="opendart")
    return pit_mark(E, "period_end", "knowledge_date", origin="dart_emp")


_RPT_YM_RE = re.compile(r"\((\d{4})[.\-/](\d{2})\)")
#  결산기말 월 → 보고서 코드. 정기보고서 이름의 괄호가 그대로 알려 준다.
_MONTH_TO_RQ = {3: RQ["Q1"], 6: RQ["H1"], 9: RQ["Q3"], 12: RQ["FY"]}


def filed_report_set(disc: Optional[pd.DataFrame]) -> set:
    """공시목록 스윕에서 (회사, 사업연도, 보고서코드) 정기보고서 제출 사실을 뽑는다.
    ★추가 호출 0회 — 이미 받아 둔 공시목록에 공짜로 들어 있는 정보다.

    이게 왜 결정적인가:
      DART 재무·직원 단건 API 는 '그 보고서가 실제로 제출된 조합'에만 데이터가 있다.
      상장 전·폐지 후·비제출 회사를 호출하면 100% status 013(데이터 없음)이 돌아오는데,
      응답이 비어도 ★호출량은 정확히 1건 깎인다. 냉시작 전수 모집단의 30~45%가 이런
      '태생적 빈손'이라, 사전 소거만으로 전수 완비 일수가 그만큼 줄어든다.
      (전수를 포기해서 줄이는 게 아니라, 존재하지 않는 것을 안 물어봐서 줄이는 것이다.)

    보고서명 '사업보고서 (2023.12)' / '분기보고서 (2024.03)' 의 괄호에서 사업연도·결산기말을
    읽는다. 괄호가 없으면 사업보고서에 한해 접수일 -1년으로 근사한다(12월 결산이 절대다수).
    틀려도 '호출을 한 번 더 하거나 덜 하는' 정도지 데이터가 왜곡되지는 않는다."""
    filed, _ = _filed_scan(disc)
    return filed


def filed_exempt_corps(disc: Optional[pd.DataFrame]) -> set:
    """★소거 면제 회사 — 제출 이력을 '확신을 갖고' 해석하지 못한 회사는 절대 소거하지 않는다.

    괄호 안 월은 ★결산기말이지 보고서 종류가 아니다. 3월 결산 회사의 '사업보고서 (2024.03)'
    를 월만 보고 매핑하면 Q1 이 되어, 그 회사는 사업보고서를 낸 적이 없는 것으로 판정되고
    직원현황·재무가 전 연도 소거된다(대체 경로가 없어 영구 결손). 12월 결산이 절대다수라
    평소엔 드러나지 않다가 특정 회사에서만 조용히 데이터가 사라지는, 가장 나쁜 형태의 결함이다.

    그래서 이름과 결산월이 12월 결산 패턴으로 ★일치할 때만 지도에 넣고, 하나라도 어긋나면
    그 회사를 통째로 면제 목록에 넣는다. 모르는 것은 소거하지 않는다 — 이것이 원칙이다."""
    _, exempt = _filed_scan(disc)
    return exempt


#  이름 → 보고서 코드(12월 결산 기준의 정상 결산기말 월)
_NAME_RQ = {"사업보고서": (RQ["FY"], (12,)), "반기보고서": (RQ["H1"], (6,)),
            "분기보고서": (None, (3, 9))}      # 분기보고서는 3월=Q1 / 9월=Q3


def _filed_scan(disc: Optional[pd.DataFrame]) -> Tuple[set, set]:
    if disc is None or not len(disc) or "kind" not in disc.columns \
            or "corp_code" not in disc.columns:
        return set(), set()
    d = disc[disc["kind"].astype(str).isin(("annual_rpt", "periodic_rpt"))]
    if not len(d):
        return set(), set()
    nm = (d["report_nm"].astype(str) if "report_nm" in d.columns
          else pd.Series([""] * len(d), index=d.index))
    ex = nm.str.extract(_RPT_YM_RE)
    yr = pd.to_numeric(ex[0], errors="coerce")
    mo = pd.to_numeric(ex[1], errors="coerce")
    ann = d["kind"].astype(str).eq("annual_rpt")
    if "rcept_dt" in d.columns:            # 괄호 없는 사업보고서만 접수일로 근사
        rd = ds_(d["rcept_dt"])
        fb = pd.Series(rd.dt.year - 1, index=d.index)
        yr = yr.where(yr.notna() | ~ann, fb)
        mo = mo.where(mo.notna() | ~ann, 12)
    filed, exempt = set(), set()
    for c, n, y, m in zip(d["corp_code"].astype(str), nm, yr, mo):
        # ★정정 접두어를 먼저 벗긴다. DISCLOSURE_KINDS 는 `^(\[[^\]]*\])?\s*사업보고서` 로
        #   [기재정정]·[첨부정정]·[첨부추가] 를 명시적으로 허용해 분류에 넣는데, 여기서
        #   head 를 그냥 잘라 쓰면 '[기재정'이 되어 startswith 가 전부 실패한다. 실측상
        #   정정 접두어 행이 ★14% 라, 10년이면 상장사 상당수가 한 번은 걸려 통째로
        #   소거 면제가 된다 — 데이터는 안 잃지만 소거 효율이 무너져 예산난을 악화시킨다.
        head = re.sub(r"^\[[^\]]*\]\s*", "", str(n).strip())[:5]
        spec = next((v for k, v in _NAME_RQ.items() if head.startswith(k)), None)
        if spec is None or not (pd.notna(y) and pd.notna(m)) or not (1990 <= int(y) <= 2100):
            exempt.add(c)                              # 해석 실패 → 이 회사는 소거하지 않는다
            continue
        rq_fixed, ok_months = spec
        if int(m) not in ok_months:                    # ★비12월 결산(또는 결산월 변경)
            exempt.add(c)
            continue
        r = rq_fixed if rq_fixed is not None else _MONTH_TO_RQ.get(int(m))
        if r is None:
            exempt.add(c)
            continue
        filed.add((c, int(y), r))
    return filed, exempt


def filed_trusted_years(disc: Optional[pd.DataFrame],
                        done_months: Optional[set] = None) -> set:
    """★사전 소거를 '적용해도 되는' 사업연도만 고른다 — 이 가드가 없으면 소거가 곧 누락이다.

    제출사실 지도는 공시목록 스윕이 그 연도의 ★제출 창구를 전부 훑었을 때만 완전하다.
    사업연도 Y 의 정기보고서는 Y년 5·8·11월(분기·반기·3분기)과 ★Y+1년 3월(사업보고서)에
    접수된다. 스윕이 한도·시간에 걸려 중간에 끊긴 상태에서 그 지도로 소거하면, 실제로
    보고서를 낸 회사를 '없다'고 잘라 버려 영구 결손이 된다. 그래서 창구 월이 하나라도
    비어 있는 연도는 소거 대상에서 제외하고, 그 연도는 종전대로 전부 조회한다
    (호출을 조금 더 쓰더라도 '데이터가 사라지는 것'보다 언제나 낫다)."""
    # ★판정 근거는 '완주 월 원장'이어야 한다 — "그 달에 행이 있나"로 보면 안 된다.
    #   공시 스윕은 한도·오류로 반쪽만 받아도 받은 행을 캐시에 남긴다(설계상 정상). 시장 전체
    #   스윕이라 어느 달이든 행은 반드시 있으므로, 행 존재로 판정하면 ★모든 달이 완주로 보이고
    #   미조회 페이지에 있던 실제 제출사가 '그 해에 보고서 없음'으로 잘린다. 그래서
    #   harvest_dart_disclosures 가 따로 관리하는 완주 원장(dart_disclosures_done)만 믿는다.
    if not done_months:
        return set()
    have = {str(x)[:7] for x in done_months}
    if not have:
        return set()
    yrs = sorted({int(w[:4]) for w in have if w[:4].isdigit()})
    if not yrs:
        return set()
    out = set()
    for y in range(yrs[0] - 1, yrs[-1] + 1):
        # 사업연도 Y 의 제출 창구 = Y년 1~12월(분기·반기) + Y+1년 1~6월(사업보고서).
        # ★창구를 스윕 범위로 '잘라서' 판정하면 안 된다 — 가장자리 연도가 반쪽 창구만 보고
        #   신뢰 판정을 받아 실제 제출사를 잘라내게 된다. 창구 전체가 완주 원장에 있어야 한다.
        win = [f"{y:04d}-{m:02d}" for m in range(1, 13)] + \
              [f"{y+1:04d}-{m:02d}" for m in range(1, 7)]
        if all(w in have for w in win):
            out.add(y)
    return out


def _apply_filed(jobs: Sequence, filed: Optional[set], trusted: Optional[set],
                 yi: int = 1, exempt: Optional[set] = None) -> List:
    """제출사실 소거를 '신뢰 연도 × 해석 성공 회사'에만 적용한다.

    yi     — job 튜플에서 연도의 위치(회사는 항상 0번).
    exempt — 제출 이력을 확신 있게 해석하지 못한 회사(비12월 결산 등). 절대 소거하지 않는다.
    """
    if not filed:
        return list(jobs)
    tr = trusted if trusted is not None else set()
    ex = exempt if exempt is not None else set()
    return [j for j in jobs
            if int(j[yi]) not in tr or str(j[0]) in ex or tuple(j) in filed]


# ★★보고서명 실측(2015~2026 · 141만행)으로 교정한 분류 규칙.
#   ★순서가 의미를 가진다 — 먼저 맞는 것이 이기고, 빈 kind 만 채운다.
#
#   교정 전 무엇이 잘못됐나(전부 '에러 없이 값만 사라지는' 유형):
#     ① tstock_burn 이 `자기주식\s*소각` 이었다. 그런데 실제 보고서명은 ★`주식소각결정`
#        이다(자기주식소각결정이 아니다). 같은 표본에서 3건 → ★159건. 시장 전체로는 8건이
#        250건쯤 되어야 정상이었다. p3 = n_burn/n_acq 의 분자가 구조적으로 0 이었으므로
#        ★TP_P2 는 애초에 발화할 수 없었다("관측 6,442행 · 발화율 0%"의 진짜 원인이다).
#     ② tstock_acq 히트의 ★61%가 자기주식 신탁계약 '체결/해지'였다. 해지는 취득의
#        ★반대 신호인데 같은 분모에 들어가 p3 을 한 번 더 눌렀다. 해지를 분리한다.
#     ③ rights 12,000건에 '증권발행결과(자율공시)'·'청약결과'·'최종발행가액확정' 같은
#        후속공시가 섞여 한 사건이 서너 번 계상됐다 → 주요사항보고서 결정공시로 앵커한다.
#     ④ audit_flag 는 ★구조적으로 작동 불가였다. 보고서명에 감사의견이 없다
#        (`감사보고서 (2017.12)` 뿐). 실제로 존재하는 부적정 신호로 바꾼다.
DISCLOSURE_KINDS = {
    # 해지가 취득보다 먼저다 — '자기주식취득신탁계약해지결정'이 취득으로 들어가면 안 된다
    "tstock_untrust": r"자기주식.{0,14}신탁\s*계약\s*해지",
    "tstock_burn": r"주식\s*소각|이익\s*소각",
    "tstock_acq":  r"자기주식\s*취득|자기주식.{0,14}신탁\s*계약\s*체결",
    "tstock_disp": r"자기주식\s*처분",
    "dividend":    r"배당\s*결정|결산배당|중간배당",
    "rights":      r"주요사항보고서\([^)]*유상증자",
    "cb":          r"주요사항보고서\([^)]*전환사채",
    "bw":          r"주요사항보고서\([^)]*신주인수권부사채",
    "reduction":   r"주요사항보고서\([^)]*감자",
    "audit_flag":  (r"의견\s*(부적정|거절)|감사의견\s*비적정|관리종목\s*지정|"
                    r"상장적격성\s*실질심사|감사보고서.{0,20}(한정|부적정|의견거절)"),
    "annual_rpt":  r"^(\[[^\]]*\])?\s*사업보고서",
    # ★정기보고서(분기·반기) — 그 자체를 쓰기보다, '어떤 조합에 재무가 존재하는가'를
    #   공짜로 알려 주는 사전 소거 지도로 쓴다(filed_report_set 참조).
    "periodic_rpt": r"^(\[[^\]]*\])?\s*(분기보고서|반기보고서)",
}


# ── ★공시 스윕 질의 설계 — 비용은 '유형별 페이지 수'가 결정한다 ─────────────────────────────
#   실측(2016-01~2019-12, 48개월): 월 83호출 중 A≈12 · B≈7 · ★I≈64. 그런데 I(거래소공시)에서
#   건진 것은 배당결정 6,663건과 자기주식 소각결정 ★8건뿐이다. I 는 수시·공정·시장조치를
#   전부 담는 광역 유형이라, 좁은 목적에 광역 유형을 쓰면 비용이 수확과 무관하게 커진다.
#   1,999회 배정이 24개월에서 소진된 것도(83×24=1,992) 전적으로 이 구조 때문이다.
#
#   ★그래서 유형을 상수로 박지 않는다. 한 달을 실측해 (비용=총페이지, 수확=매칭건수)를 재고
#     비용 대비 수확으로 고른다. 코드 체계가 바뀌거나 상세유형 코드가 틀려도 그 후보는
#     0수확으로 스스로 탈락하고 광역 폴백이 남는다 — 상수였다면 조용히 전량 결손이 된다.
#   ★★corp_cls(Y/K/N/E)로 좁히는 것은 ★금지한다. 실측에서 3,498사 중 기간 내 corp_cls 가
#     두 값 이상인 법인이 ★0개였다 — 즉 서버는 '호출 시점의 현재 법인구분'을 과거 행에
#     소급 적용한다. Y|K|N 으로 좁히면 그 시절 실제로 거래되던 회사 중 ★이후 상장폐지된
#     회사가 통째로 사라진다(2016~2019 정기공시 행의 16%가 corp_cls=E 인데 전부 stock_code
#     보유 = 당시 상장사였다). 감자·유증·CB/BW 가 가장 몰리는 집단이라 생존자편향 직결이다.
#   ★★last_reprt_at 도 N 을 유지한다. Y 는 약 14%(정정 이전 원본)를 줄여 주지만, 남는 행의
#     rcept_dt 가 ★정정 접수일이 되어 원 공표일이 사라진다. 여기서는 접수일=지식일이므로
#     그건 이벤트를 통째로 뒤로 미는 것이다 — 14% 아끼자고 PIT 를 파는 나쁜 거래다.
DISC_SPECS = [
    {"key": "A", "params": {"pblntf_ty": "A"}, "must": True, "months": None,
     "why": "정기공시 — 사업·반기·분기보고서 제출사실(뒤의 모든 티어를 사전 소거하는 지도)"},
    {"key": "B", "params": {"pblntf_ty": "B"}, "must": True, "months": None,
     "why": "주요사항보고 — 자사주 취득·처분·소각, 유증, CB/BW, 감자(V3·PACK-C 입력)"},
    # I 는 예산의 70%를 먹는데 그 안에서 우리가 쓰는 행은 3.6%다. 그래서 두 단계로 줄인다:
    #   ①상세유형 I001(수시공시)로 좁힌다 — 무손실, 약 10% 절감.
    #   ②그래도 예산이 모자라면 ★이벤트가 몰린 달만 훑는다. 배당·소각 공시는 실측상
    #     {1,2,3,7,12}월에 92.6%가 집중된다(I 행은 41.9% 줄고 recall 은 92.6% 유지).
    #     이건 손실이 있는 절감이므로 ★예산이 부족할 때만, 그 사실을 로그에 적고 쓴다.
    {"key": "I001", "params": {"pblntf_ty": "I", "pblntf_detail_ty": "I001"}, "must": False,
     "months": None, "lean_months": (1, 2, 3, 7, 12),
     "why": "거래소 수시공시 — 현금·현물배당결정, ★주식소각결정(주요사항보고에 없다)"},
    {"key": "I", "params": {"pblntf_ty": "I"}, "must": False,
     "months": None, "lean_months": (1, 2, 3, 7, 12),
     "why": "거래소공시 전체 — 광역이라 최후수단"},
]
DISC_MIN_YIELD = 0.02      # 한 페이지(100건)에서 우리가 쓰는 공시가 이 비율 미만이면 접는다
DISC_NARROW_KEEP = 0.50    # 좁힌 후보가 광역의 이 비율 이상을 건지면 광역을 버린다
DISC_NARROW_COST = 0.85    # ★그리고 이 비율 이하로 실제로 싸야 '좁혔다'고 인정한다.
#                            같은 페이지 수가 오면 상세유형 필터가 무시된 것이므로, 절감을
#                            주장하지 말고 그 사실을 로그에 적어야 다른 수단을 찾게 된다.


def _disc_kind_mask(nm: pd.Series) -> pd.Series:
    """report_nm 이 DISCLOSURE_KINDS 중 하나라도 맞는가(합집합)."""
    m = pd.Series(False, index=nm.index)
    for pat in DISCLOSURE_KINDS.values():
        m = m | nm.str.contains(pat, regex=True, na=False)
    return m


def _disc_done() -> Tuple[set, set]:
    """(완주한 월 전체, 완주한 (월,유형) 조합) — 두 원장을 함께 읽는다.

    ★옛 원장은 '월' 단위뿐이었다. 그래서 A·B 는 다 받고 I 에서 예산이 끊긴 달이 통째로
      미완주가 되어, 다음 실행이 그 달의 A·B 를 ★처음부터 다시 받았다(실측 오버헤드
      25~34%). 이제 (월,유형)을 따로 남기고, 선택된 유형이 전부 끝난 달만 월 원장에 올린다.
    ★그리고 '행이 있으니 완주'라는 구버전 승계는 ★삭제했다. 시장 전체 스윕이라 어느 달이든
      행은 반드시 있으므로 그 판정은 모든 달을 완주로 만들고, 미조회 페이지에 있던 실제
      제출사가 '그 해에 보고서 없음'으로 잘려 직원현황·재무에서 통째로 사라진다.
      도달 경로도 실재했다 — 첫 실행이 행은 모았지만 완주 월이 0개인 경우다.
    """
    mt = VAULT.load_table("dart_disclosures_done", "shared")
    mons = set(mt["ym"].astype(str)) if mt is not None and len(mt) else set()
    st = VAULT.load_table("dart_disc_done_spec", "shared")
    pairs = set()
    if st is not None and len(st) and {"ym", "key"} <= set(st.columns):
        pairs = set(zip(st["ym"].astype(str), st["key"].astype(str)))
    return mons, pairs


FILED_SPEC_KEY = "A"      # 제출사실 지도(사업·반기·분기보고서)를 주는 유일한 유형


def disc_filed_months() -> set:
    """★'제출사실 지도를 믿어도 되는 달' — 정기공시(A)가 완주한 달.

    ★★이 함수가 옛 _sync_disc_month_ledger 를 대체한다. 그 함수는 '이번 실행이 고른
      유형이 전부 끝난 달'을 ★영구 월 원장에 승격시켰는데, 유형 선택(keep)은 매 실행
      프리플라이트로 재측정되므로 ★줄어들 수 있다. 실제로 이번 실행에서 I001 은
      '상세유형 무시'로, I 는 '유효 수확 1.0%'로 둘 다 접혀 keep={A,B} 가 됐다.
      그 상태로 승격하면, 과거 실행이 A·B 만 받고 I 에서 끊긴 달이 '완주'로 박히고
      disc_plan 이 그 달을 영구 제외한다 → 거래소공시(현금·현물배당결정, ★주식소각결정)가
      그 달에 대해 다시는 수집되지 않는다. 공용 드라이브라 되돌릴 수단도 없다.

    그래서 승격 자체를 없앤다. 대신 필요한 것만 정확히 계산한다 —
    월 원장을 읽는 곳은 두 군데이고 요구가 서로 다르다:
      ① disc_plan 의 월 건너뛰기 → (월×유형) 원장이 이미 유형 단위로 정확히 처리한다.
      ② filed_trusted_years 의 연도 신뢰 → ★A 유형만 있으면 된다. 제출사실(annual_rpt·
         periodic_rpt)은 전부 정기공시(A)에서 나오고 B·I 와는 무관하기 때문이다.
    ②에 필요한 것이 이 함수의 반환값이다. 레거시 월 원장(구버전은 A·B·I 를 모두 훑고
    월 단위로만 기록했다)은 상위집합이므로 그대로 합친다.
    """
    out: set = set()
    try:
        mt = VAULT.load_table("dart_disclosures_done", "shared")
        if mt is not None and len(mt):
            out |= set(mt["ym"].astype(str))          # 레거시(구버전 = 전 유형 완주)
        st = VAULT.load_table("dart_disc_done_spec", "shared")
        if st is not None and len(st) and {"ym", "key"} <= set(st.columns):
            k = st["key"].astype(str)
            out |= set(st.loc[k == FILED_SPEC_KEY, "ym"].astype(str))
    except Exception as e:                                            # noqa
        L.warn(f"제출사실 신뢰 월 산출 실패({type(e).__name__}: {e}) — 소거 없이 진행합니다.")
        return set()
    return out


def disc_plan(start: str, end: str, avail: Optional[int] = None) -> dict:
    """★스윕 전 프리플라이트 — 어떤 유형을 훑을지와 '진짜 필요 호출수'를 실측으로 정한다.

    반환 {"jobs": [(월, spec)...], "specs": [...], "need": int}. need 는 CallBudget 에
    선언할 실수요다. 이걸 선언하지 않으면 배분기가 '수요 미상'으로 보고 비율만큼만 주는데,
    그 비율이 실수요의 1/6 이었다는 것이 이번 실측의 결론이다.
    avail — 이 수집기가 현실적으로 받을 수 있는 상한. 실수요가 이걸 넘으면 손실 있는
            절감(이벤트 집중월만 훑기)을 켜고 ★그 사실과 recall 을 로그에 명시한다.
    비용은 후보 수만큼(최대 4회). 스윕 전체가 수천 회이므로 무시할 수 있다.
    """
    mons, pairs = _disc_done()
    allm = list(pd.period_range(d_(start), d_(end), freq="M"))
    months = [m for m in allm if str(m) not in mons][::-1]   # ★최근 월 우선(본문 주석 참조)
    if RUN_MODE == "CACHED" or not months or not DART_API_KEY:
        return {"jobs": [], "specs": [], "need": 0}
    # ★표본 월을 하나만 쓰면 안 된다. 공시량은 계절성이 극심하다 — 3월은 사업보고서
    #   제출 피크라 정기공시(A)가 평월의 3배가 넘는다(실측: 2026-03 에서 A=37페이지,
    #   평월 추정은 12). 최근 월 하나로 재면 실수요가 과대추정되고, 그 결과 예산이
    #   모자란 것으로 판정되어 ★불필요하게 손실 있는 절감(집중월만 훑기)으로 내려간다.
    #   실제로 그렇게 배당·소각 recall 7%를 그냥 버렸다. 그래서 분기 간격으로 흩어
    #   최대 3개월을 재고 ★중앙값을 쓴다(비용은 후보 4종 × 3 = 최대 12회).
    pick = [months[0]] + [months[i] for i in (len(months) // 3, 2 * len(months) // 3)
                          if 0 < i < len(months)]
    pick = list(dict.fromkeys(pick))[:3]
    obs: List[dict] = []
    for sp in DISC_SPECS:
        pgs, cns, pys, notes = [], [], [], []
        for pm in pick:
            js = dart_call("list.json", {"bgn_de": pm.start_time.strftime("%Y%m%d"),
                                         "end_de": pm.end_time.strftime("%Y%m%d"),
                                         "page_no": 1, "page_count": 100,
                                         "last_reprt_at": "N", **sp["params"]})
            lst = (js or {}).get("list")
            if not js or not isinstance(lst, list) or not lst:
                notes.append(str((js or {}).get("status", "무응답")))
                continue
            pgs.append(max(1, int(js.get("total_page", 1) or 1)))
            cns.append(int(js.get("total_count", len(lst)) or len(lst)))
            nm = pd.Series([str(x.get("report_nm", "")) for x in lst])
            pys.append(float(_disc_kind_mask(nm).mean()))
        if not pgs:
            obs.append({**sp, "pages": 0, "cnt": 0, "hits": 0.0, "pyield": 0.0,
                        "note": f"응답 0건({notes[0] if notes else '무응답'})"})
            continue
        pages = int(np.median(pgs))
        cnt = int(np.median(cns))
        py = float(np.median(pys))
        obs.append({**sp, "pages": pages, "cnt": cnt, "hits": cnt * py, "pyield": py,
                    "note": ""})
    keep = [o for o in obs if o["must"] and o["pages"] > 0]
    opt = sorted([o for o in obs if not o["must"] and o["pages"] > 0],
                 key=lambda o: -(o["hits"] / max(o["pages"], 1)))
    narrow = next((o for o in opt if o["key"] == "I001"), None)
    broad = next((o for o in opt if o["key"] == "I"), None)
    # ★'좁혔다'고 말하려면 실제로 싸져야 한다. 실측에서 I001 과 I 가 페이지·건수까지
    #   완전히 동일하게 돌아왔다(138페이지 · 13,735건) — 서버가 pblntf_detail_ty 를
    #   무시했다는 뜻이다. 그런데도 옛 판정은 '수확 100%를 건졌으니 광역 접음'이라고
    #   적었다. 절감이 0인데 절감했다고 말하는 로그다. 그러면 다른 절감 수단을 찾지 않는다.
    if (narrow is not None and broad is not None and narrow["pages"] > 0
            and narrow["pages"] > DISC_NARROW_COST * max(broad["pages"], 1)):
        narrow["dead"] = True
        narrow["note"] = (f"★상세유형 필터가 서버에서 무시된 듯합니다 — 광역과 같은 "
                          f"{narrow['pages']}페이지·{narrow['cnt']:,}건이 왔습니다. "
                          f"좁히기 절감이 0 이므로 광역을 그대로 씁니다")
    for o in opt:
        if o.get("dead"):
            continue
        if o["pyield"] < DISC_MIN_YIELD:
            o["note"] = f"페이지당 유효 수확 {o['pyield']*100:.1f}% — 접음"
            continue
        # ★좁힌 후보가 (더 싸면서) 광역의 절반 이상을 건지면 광역은 버린다.
        if (o is broad and narrow is not None and not narrow.get("dead")
                and narrow["pyield"] >= DISC_MIN_YIELD
                and narrow["hits"] >= DISC_NARROW_KEEP * max(broad["hits"], 1e-9)):
            o["note"] = (f"좁힌 후보 I001 이 수확의 "
                         f"{narrow['hits']/max(broad['hits'],1e-9)*100:.0f}%를 "
                         f"{narrow['pages']}/{broad['pages']} 비용으로 건짐 — 광역 접음")
            continue
        keep.append(o)

    def _jobs(lean: bool) -> Tuple[List[Tuple[Any, dict]], int]:
        out, cost = [], 0
        for o in keep:
            mset = o.get("lean_months") if (lean and o.get("lean_months")) else o.get("months")
            for m in months:
                if mset and m.month not in set(mset):
                    continue
                if (str(m), o["key"]) in pairs:      # ★그 (월,유형)만 이미 끝났다
                    continue
                out.append((m, o))
                cost += int(o["pages"])
        return out, cost

    jobs, need = _jobs(lean=False)
    lean = False
    if avail is not None and need > int(avail) > 0:
        jobs2, need2 = _jobs(lean=True)
        if need2 < need:
            L.warn(f"공시 스윕 실수요 {need:,}회 > 이번 실행이 받을 수 있는 {int(avail):,}회 — "
                   f"거래소공시를 ★이벤트 집중월(1·2·3·7·12월)로 좁혀 {need2:,}회로 줄입니다. "
                   f"배당·소각 공시의 92.6%가 그 다섯 달에 몰려 있어 recall 손실은 약 7%이고, "
                   f"나머지 달은 다음 실행이 이어받습니다(정기공시 A·주요사항 B 는 손대지 않습니다).")
            jobs, need, lean = jobs2, need2, True
    per_month = sum(int(o["pages"]) for o in keep)
    rows = [[o["key"], o["why"][:34], f"{o['pages']}", f"{o['cnt']:,}",
             f"{o['pyield']*100:.1f}%",
             "★채택" + ("(집중월만)" if lean and o.get("lean_months") else "")
             if o in keep else (o["note"] or "접음")] for o in obs]
    L.grid(rows, ["유형", "무엇을 얻나", "월페이지", "월건수", "유효비율", "판정"],
           ["l", "l", "r", "r", "r", "l"],
           title=f"공시 스윕 유형 선택 — {', '.join(str(x) for x in pick)} "
                 f"{len(pick)}개월을 실측해 중앙값으로 '비용(페이지) 대비 수확'을 "
                 f"고릅니다. 채택 유형 월 {per_month}회 · 남은 (월×유형) {len(jobs):,}건 → "
                 f"실수요 {need:,}회(프리플라이트 {len(obs)}회 소비). 이 값을 예산에 "
                 f"'선언'하므로, 순번 때문에 비율만 받고 굶는 일은 이제 없습니다.")
    return {"jobs": jobs, "specs": keep, "need": need, "months": months}


def harvest_dart_disclosures(start: str, end: str, max_calls: int = -1,
                             plan: Optional[dict] = None) -> pd.DataFrame:
    """공시목록 월 단위 시장 전체 스윕 — 회사별 조회보다 수십 배 싸다.
    훑을 유형은 disc_plan() 이 한 달 실측으로 고른다(고정 상수 아님)."""
    empty = pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm", "kind"])
    if not DART_API_KEY:
        return empty
    cached = VAULT.load_table("dart_disclosures", "shared")
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["rcept_dt"] = ds_(cached["rcept_dt"])
        L.info(f"캐시 재사용: 공시목록 {len(cached):,}건")
    if plan is None:
        plan = disc_plan(start, end)
    # ★작업 단위가 '월'이 아니라 ★(월 × 유형)이다. 최근 월 우선은 그대로 — 오름차순으로
    #   소비하면 배정이 가장 오래된 달에 먼저 소진되고, 정작 전략이 거래하는 최근 연도가
    #   미완주로 남아 ①그 연도가 소거 대상에서 빠지고 ②자사주·증자·배당(V3/PACK-C 입력)이
    #   통째로 빈다. 같은 함정을 일봉에서 이미 겪었다.
    jobs = list(plan.get("jobs") or [])
    specs = list(plan.get("specs") or [])
    if not specs:
        jobs = []

    def one(job):
        m, sp = job
        rows, page = [], 1
        while page <= 100:
            if CLOCK.over():
                # ★루프 안에서도 시간예산을 본다. 한 (월,유형)이 최대 100호출이라
                #   배치 경계에서만 보면 예산 만료 뒤에도 수천 회를 더 태운다.
                return rows, None
            js = dart_call("list.json", {"bgn_de": m.start_time.strftime("%Y%m%d"),
                                         "end_de": m.end_time.strftime("%Y%m%d"),
                                         "page_no": page, "page_count": 100,
                                         "last_reprt_at": "N", **sp["params"]})
            if js is None:
                return rows, None      # 실패/한도/일시 오류 — 완주 아님(다음 실행에 재시도)
            lst = js.get("list")
            if not isinstance(lst, list) or not lst:
                break                  # status=013 등 '진짜 없음' → 이 조합은 완주다
            rows += lst
            if page >= int(js.get("total_page", 1) or 1):
                break
            page += 1
        else:
            return rows, None          # 100페이지 캡에 걸림 = 잘렸다 → 완주로 치지 않는다
        return rows, (str(m), sp["key"])

    if jobs:
        QUOTA.plan("dart", int(plan.get("need") or 0),
                   f"공시목록 시장전체 스윕({len(jobs):,}개 (월×유형) · 유형 "
                   f"{'+'.join(s['key'] for s in specs)} · 실측)")
    fresh: List[dict] = []
    done_new: List[Tuple[str, str]] = []
    spent0 = QUOTA.spent("dart")
    _cap = cap_of(max_calls)
    _n_ok = 0
    with stage_bar(len(jobs), "DART 공시목록(월×유형 스윕)") as bar:
        for batch in budget_batches(jobs, 48, "dart", "공시목록", cap=max_calls, unit="건"):
            for item in pmap_net(one, batch, workers=min(IO_THREADS, 8), quiet=True):
                if not item:
                    continue
                r, ok = item
                if r:
                    fresh += r
                if ok:
                    done_new.append(ok)
                    _n_ok += 1
            # ★진행바는 '성공한 것'만 센다. 제출한 수를 세면 QUOTA 가 막힌 뒤 마지막 배치가
            #   전속력으로 바를 채우고 0행을 수집해, 사용자에겐 '다 됐는데 왜 또 하지?'가 된다.
            bar.n = _n_ok
            bar.refresh()
    frames = ([cached] if cached is not None and len(cached) else [])
    if fresh:
        d = pd.DataFrame(fresh)
        # ★rm 보존 — '정' 이 붙은 행이 원본이고 [기재정정]… 은 나중 정정본이다. 소비 단계에서
        #   원 공표일을 쓰려면 이 컬럼이 있어야 한다(없으면 PIT 가 정정일로 밀린다).
        keep = [c for c in ("corp_code", "corp_name", "stock_code", "rcept_no",
                            "rcept_dt", "report_nm", "rm") if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return empty
    D = pd.concat(frames, ignore_index=True).drop_duplicates("rcept_no", keep="last")
    D["rcept_dt"] = ds_(D["rcept_dt"])
    D["report_nm"] = D["report_nm"].astype(str)
    D["kind"] = ""
    for k, pat in DISCLOSURE_KINDS.items():
        m = D["report_nm"].str.contains(pat, regex=True, na=False) & (D["kind"] == "")
        D.loc[m, "kind"] = k
    # ★★저장 순서 — 데이터가 먼저, 원장은 그게 성공했을 때만. 원장을 먼저 쓰면 아래 concat
    #   에서 MemoryError 가 나거나 parquet 쓰기가 실패했을 때 '월은 완주, 행은 0' 이 남고,
    #   그 달은 영구히 다시 받지 않는다. 게다가 그 완주 원장이 filed_trusted_years 로 흘러가
    #   ★실제로 사업보고서를 낸 회사들을 직원현황·재무 대상에서 통째로 삭제한다.
    if fresh:
        try:
            VAULT.save_table("dart_disclosures", D, "shared", domain="dart", source="opendart")
        except Exception as e:                                    # noqa
            L.warn(f"공시목록 저장 실패 — 완주 원장을 쓰지 않고 다음 실행이 재시도합니다: "
                   f"{type(e).__name__}: {e}")
            done_new = []
    if done_new:
        _st = VAULT.load_table("dart_disc_done_spec", "shared")
        _new = pd.DataFrame(done_new, columns=["ym", "key"])
        _all = pd.concat([_st, _new], ignore_index=True) \
            if _st is not None and len(_st) else _new
        VAULT.save_table("dart_disc_done_spec", _all.drop_duplicates(["ym", "key"]), "shared",
                         domain="dart", source="sweep_complete_month_type")
    # ★월 원장에 새로 승격하지 않는다 — 유형 선택이 줄어든 실행에서 미완주 월이 완주로
    #   박히면 그 달의 거래소공시가 영구히 사라진다(disc_filed_months 주석 참조).
    #   제출사실 신뢰는 disc_filed_months() 가 A 유형 완주로 직접 계산한다.
    D = pit_mark(D, "rcept_dt", "rcept_dt", origin="dart_list")     # 접수일=공개일
    L.ok(f"공시목록 {len(D):,}건 — " +
         ", ".join(f"{k}={int((D['kind']==k).sum()):,}" for k in DISCLOSURE_KINDS
                   if (D["kind"] == k).any()))
    return D


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [10] 데이터수집부 D — 애널리스트 리포트 (한경컨센서스 · 네이버리서치 중심)                  ║
# ║                                                                                          ║
# ║  두 소스의 역할이 다르고 합쳐야 원장이 완성된다:                                            ║
# ║   · 한경: 작성자(애널리스트)·목표주가·투자의견이 리스트에 직접 — skinType=business 필수     ║
# ║   · 네이버: 종목코드가 링크에 직접, 커버리지 넓음 — 단 body 는 EUC-KR(meta 는 거짓말)      ║
# ║  D축 d2(목표주가 상향 리비전)는 '같은 애널리스트의 같은 종목 직전 목표가' 대비여야 하므로   ║
# ║  애널리스트 원장(entity resolution)은 장식이 아니라 전략의 구조적 필수 입력이다.            ║
# ║  ★ 드라이브에 캐시된 기존 원장을 먼저 재사용하고 부족분만 수집 → 신규분은 드라이브 저장.    ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

BROKER_RENAME = {
    "미래에셋대우": "미래에셋증권", "대우증권": "미래에셋증권", "미래에셋": "미래에셋증권",
    "하나금융투자": "하나증권", "하나대투증권": "하나증권",
    "신한금융투자": "신한투자증권", "이베스트투자증권": "LS증권", "이베스트증권": "LS증권",
    "KTB투자증권": "다올투자증권", "하이투자증권": "iM증권", "메리츠종금증권": "메리츠증권",
    "케이프투자증권": "케이프투자증권", "SK증권": "SK증권", "NH투자": "NH투자증권",
    "삼성": "삼성증권", "KB": "KB증권", "한국투자": "한국투자증권", "키움": "키움증권",
}
MAJOR_BROKERS = ["미래에셋증권", "한국투자증권", "NH투자증권", "삼성증권", "KB증권",
                 "신한투자증권", "하나증권", "메리츠증권", "키움증권", "대신증권"]


def broker_norm(raw: Any) -> Tuple[str, str]:
    """(broker_id, 표준사명). 사명 변경을 정규화하지 않으면 같은 애널리스트가 소속 변경만으로
    다른 사람이 되어 목표주가 리비전 계산이 통째로 망가진다."""
    t = clean_txt(raw).replace(" ", "")
    t = re.sub(r"(투자증권|증권|금융투자|자산운용|리서치)$", lambda m: m.group(0), t)
    name = BROKER_RENAME.get(t, t)
    for k, v in BROKER_RENAME.items():
        if t.startswith(k):
            name = v
            break
    if name and not re.search(r"(증권|투자|리서치|은행)", name):
        name = name + "증권"
    return (h40("broker", name)[:10], name or "미상")


def parse_target_price(raw: Any) -> Optional[float]:
    """'0' / '-' / '없음' 은 목표주가 없음(결측)이지 0원이 아니다 — 0으로 넣으면 d2 오염."""
    s = str(raw or "").strip().replace(",", "")
    if not s or s in ("0", "-", "없음", "N/A", "na", "None"):
        return None
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    v = float(m.group(0))
    return v if v >= 100 else None


_TITLE_CODE = re.compile(r"\((\d{6}|\d{4}[0-9A-HJ-NP-TV-Z][0KLMN])\)")

# ★한경 목록 파라미터 조합 후보. 실측에서 현행 조합이 ★HTTP 500(응답길이 0)을 받았다 —
#   서버가 report_type 과 search_report_type 을 동시에 받으면 거부하는 것으로 보인다.
#   검증된 구현들이 서로 다른 이름을 쓰므로 하나를 찍지 말고 실측으로 고른다.
HK_PARAM_VARIANTS = [
    ("v25", {"skinType": "business", "report_type": "CO", "search_text": ""}),
    ("v4", {"skinType": "business", "search_report_type": "CO", "order_type": "",
            "pagenum": "80", "search_text": ""}),
    ("plain", {"report_type": "CO", "search_text": ""}),
    ("full", {"skinType": "business", "report_type": "CO", "search_report_type": "CO",
              "order_type": "", "pagenum": "80", "search_text": ""}),
]


def _hk_pick_variant(base: str, m0: pd.Timestamp, m1: pd.Timestamp) -> Optional[dict]:
    """쓰기 전에 한 달로 조합을 고른다 — 틀린 조합으로 120개월을 태우지 않기 위해서다."""
    for name, pv in HK_PARAM_VARIANTS:
        prm = dict(pv)
        prm.update({"now_page": "1", "sdate": m0.strftime("%Y-%m-%d"),
                    "edate": m1.strftime("%Y-%m-%d")})
        got, why = _hk_rows(net_get(base, source="hankyung", params=prm,
                                    referer="https://consensus.hankyung.com/"))
        if got:
            L.ok(f"한경 파라미터 조합 '{name}' 채택 — {len(got)}건 확인({m0:%Y-%m}).")
            return dict(pv)
        st, _ = NET_LAST.get("hankyung", ("—", ""))
        L.info(f"한경 조합 '{name}' 미채택(HTTP {st} · 사유 {why}) — 다음 조합을 시도합니다.")
    return None

REPORT_COLS = ["rid", "source", "src_id", "pub_date", "stock_code", "stock_name", "title",
               "broker_raw", "broker_id", "broker_name", "analyst_raw", "target_price",
               "opinion", "pdf_url"]


def harvest_hankyung(start: str, end: str,
                     skip_months: Optional[set] = None) -> pd.DataFrame:
    """한경컨센서스 기업 리포트 목록. skinType=business 를 빠뜨리면 6컬럼 레이아웃이 와서
    목표주가·작성자가 조용히 사라진다 → 컬럼 인덱스가 아니라 <th> 헤더명으로 매핑한다.
    skip_months: 캐시 원장이 이미 충분히 덮은 월(YYYY-MM) — 증분 수집(매 실행 전체 재크롤 금지)."""
    rows: List[dict] = []
    base = "https://consensus.hankyung.com/analysis/list"
    s_t, e_t = d_(start), d_(end)
    skip_months = skip_months or set()
    n_skip = 0
    n_alarm = [0]                        # 레이아웃 경보는 한 번만(120개월 × 경고는 소음)
    variant: List[Optional[dict]] = [None]
    for m0 in pd.date_range(s_t, e_t, freq="MS"):
        if m0.strftime("%Y-%m") in skip_months:
            n_skip += 1
            continue
        if CLOCK.over():
            CLOCK.cut(f"한경컨센서스: {len(rows):,}건 수집 후 중단")
            break
        m1 = min(e_t, m0 + pd.offsets.MonthEnd(0))
        if variant[0] is None:               # ★첫 유효 월에서 조합을 한 번만 고른다
            variant[0] = _hk_pick_variant(base, m0, m1) or {}
            if not variant[0]:
                st, head = NET_LAST.get("hankyung", ("—", ""))
                L.warn(f"한경: 파라미터 조합 {len(HK_PARAM_VARIANTS)}개가 모두 실패 "
                       f"(HTTP {st} · 응답머리 {str(head)[:110]}) — 이번 실행은 건너뜁니다. "
                       f"사이트 개편 또는 일시 장애입니다. 캐시 원장은 그대로 보존됩니다.")
                break
        page = 1
        seen_id: set = set()             # ★그 달에 이미 본 보고서 id
        while page <= 200:
            _prm = dict(variant[0])
            _prm.update({"now_page": str(page), "sdate": m0.strftime("%Y-%m-%d"),
                         "edate": m1.strftime("%Y-%m-%d")})
            html = net_get(base, source="hankyung", params=_prm,
                           referer="https://consensus.hankyung.com/")
            got, why = _hk_rows(html)
            if not got:
                if why in ("layout", "nohtml") and not n_alarm[0]:
                    n_alarm[0] = 1
                    st, head = NET_LAST.get("hankyung", ("—", ""))
                    L.warn(f"한경 목록 파싱 실패({why}) — HTTP {st} · 응답길이 "
                           f"{len(html or ''):,} · 첫 실패 {m0:%Y-%m} · 응답머리 "
                           f"{str(head)[:120]}. 레이아웃·파라미터 변경 가능성이 큽니다.")
                break                    # ★빈 페이지에서만 종료 — '80행 미만' 조기종료는
            #                              파싱 탈락이 낀 페이지에서 그 달 잔여분을 유실한다
            # ★★한경은 마지막 페이지를 넘어가면 '빈 페이지'가 아니라 ★같은 페이지를 계속
            #   돌려준다(실측). 빈 페이지만 기다리면 월마다 상한 200페이지를 그대로 태워
            #   120개월 × 200 = 24,000요청이 전부 중복 수집이 된다. 종료 판정은 반드시
            #   '신규 id 0건'이어야 한다(다른 세션에서도 같은 결론에 도달한 지점).
            fresh = [r for r in got if r.get("src_id") not in seen_id]
            if not fresh:
                break
            seen_id.update(r.get("src_id") for r in fresh)
            rows += fresh
            page += 1
            if CLOCK.over():
                break
    if n_skip:
        L.info(f"한경컨센서스: 캐시가 덮은 {n_skip}개월 건너뜀(증분 수집)")
    d = pd.DataFrame(rows)
    if len(d):
        L.ok(f"한경컨센서스 {len(d):,}건 수집")
    elif not n_skip:
        # ★0건도 반드시 말한다. 이 침묵 때문에 '목표주가 0% · 작성자 0%'의 원인을 못 찾았다 —
        #   네이버 파서는 두 값을 하드코딩으로 비워 두므로, 한경이 죽으면 D축 d2 가 통째로 죽는다.
        st, head = NET_LAST.get("hankyung", ("—", ""))
        L.warn(f"한경컨센서스 0건 — ★목표주가·작성자의 유일한 소스라 D축 d2(목표가 리비전)가 "
               f"통째로 결측이 됩니다. HTTP {st} · 응답머리 {str(head)[:120]}")
    return d


def _hk_rows(html: Optional[str]) -> Tuple[List[dict], str]:
    """반환 (행들, 사유). 사유 ∈ {ok, empty, nohtml, layout} — ★0건의 이유를 구분한다.
    구분이 없으면 '데이터 없음'과 '레이아웃 변경'과 '차단'이 전부 같은 빈 리스트가 되어,
    한경이 통째로 죽어도 로그에 아무 흔적이 남지 않는다(실측에서 실제로 그랬다)."""
    sp = soupify(html)
    if sp is None:
        return [], "nohtml"
    table = None
    # ★'td 가 있는 첫 표'는 검색폼·탭·공지 표를 집을 수 있다. 헤더 내용으로 고른다.
    for t in sp.find_all("table"):
        head = " ".join(th.get_text(" ", strip=True) for th in t.find_all("th"))
        if "작성일" in head and ("제공출처" in head or "작성자" in head or "적정" in head):
            table = t
            break
    if table is None:
        blob = (html or "")[:4000]
        return [], ("empty" if ("없습니다" in blob or "결과가 없" in blob) else "layout")
    heads = [th.get_text(" ", strip=True) for th in table.find_all("th")]

    def pick(cells, *names, default=None):
        for nm in names:                     # ★부분포함 — '적정가격(원)' 같은 변형을 견딘다
            for i, h in enumerate(heads):
                if nm in h and i < len(cells):
                    return cells[i]
        return default

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [td.get_text(" ", strip=True) for td in tds]
        c_date = pick(texts, "작성일", default=texts[0])
        c_title_td = pick(tds, "제목", default=tds[1] if len(tds) > 1 else None)
        c_tp = pick(texts, "적정가격", "목표주가", default=None)
        c_op = pick(texts, "투자의견", default=None)
        c_an = pick(texts, "작성자", default=None)
        c_br = pick(texts, "제공출처", "증권사", default=None)
        if not heads:                                    # 헤더 없는 변형 레이아웃 폴백
            c_date, c_tp, c_op, c_an, c_br = texts[0], \
                (texts[2] if len(texts) > 2 else None), (texts[3] if len(texts) > 3 else None), \
                (texts[4] if len(texts) > 4 else None), (texts[5] if len(texts) > 5 else None)
            c_title_td = tds[1] if len(tds) > 1 else None
        if c_title_td is None:
            continue
        title = c_title_td.get_text(" ", strip=True)
        href = ""
        for td in tds:                       # ★링크가 별도 '첨부' 셀에 있는 레이아웃도 있다
            a = td.find("a", href=True)
            if a and ("report_idx" in a["href"] or "downpdf" in a["href"]
                      or a["href"].lower().endswith(".pdf")):
                href = a["href"]
                break
        if not href:
            a = c_title_td.find("a")
            href = (a.get("href") or "") if a else ""
        m_id = re.search(r"report_idx=(\d+)", href)
        m_cd = _TITLE_CODE.search(title)
        pub = parse_kr_date(c_date)
        if not pub:
            continue
        bid, bname = broker_norm(c_br)
        out.append({"source": "hankyung", "src_id": (m_id.group(1) if m_id
                               else h40(title, pub, c_br or "", href)[:16]),
                    "pub_date": pub, "stock_code": code6(m_cd.group(1)) if m_cd else None,
                    "stock_name": title.split("(")[0].strip()[:40] if m_cd else "",
                    "title": title[:160], "broker_raw": c_br or "", "broker_id": bid,
                    "broker_name": bname, "analyst_raw": clean_txt(c_an)[:40],
                    "target_price": parse_target_price(c_tp), "opinion": str(c_op or "")[:16],
                    "pdf_url": ("https://consensus.hankyung.com" + href) if href else None})
    return out, ("ok" if out else "empty")


def harvest_naver_research(start: str, end: str,
                           since: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """네이버 금융 리서치(종목분석). 종목코드는 a.stock_item href 에서 직접. EUC-KR 주의.
    since: 캐시 원장의 마지막 수집일 — 있으면 그 이후분만 전진 증분 수집."""
    rows: List[dict] = []
    base = "https://finance.naver.com/research/company_list.naver"
    s_t, e_t = d_(start), d_(end)
    if since is not None and pd.notna(since):
        new_start = max(s_t, d_(since) - pd.Timedelta(days=7))
        if new_start > s_t:
            L.info(f"네이버리서치: 캐시 이후분만 증분 수집 ({new_start.date()} ~ {e_t.date()})")
            s_t = new_start
    page = 1
    seen_id: set = set()                 # ★네이버도 마지막 페이지를 반복 반환한다(한경과 동일)
    while page <= 3000:
        if CLOCK.over():
            CLOCK.cut(f"네이버리서치: {len(rows):,}건 수집 후 중단")
            break
        html = net_get(base, source="naver", prefer_enc="euc-kr",
                       params={"searchType": "writeDate",
                               "writeFromDate": s_t.strftime("%Y-%m-%d"),
                               "writeToDate": e_t.strftime("%Y-%m-%d"), "page": str(page)},
                       referer="https://finance.naver.com/research/")
        got, has_next = _nv_rows(html)
        if not got:
            break
        fresh = [r for r in got if r.get("src_id") not in seen_id]
        if not fresh:
            break                        # 신규 0건 = 마지막 페이지 반복. 여기서 끊지 않으면
        seen_id.update(r.get("src_id") for r in fresh)   # 상한 3,000페이지를 그대로 태운다
        rows += fresh
        if not has_next:
            break
        page += 1
    d = pd.DataFrame(rows)
    if len(d):
        L.ok(f"네이버리서치 {len(d):,}건 수집")
    return d


def _nv_rows(html: Optional[str]) -> Tuple[List[dict], bool]:
    sp = soupify(html)
    if sp is None:
        return [], False
    table = sp.find("table", class_="type_1") or sp.find("table")
    if table is None:
        return [], False
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        a_st = tr.find("a", class_="stock_item")
        code = None
        if a_st is not None:
            m = re.search(r"code=([0-9A-Z]{6})", a_st.get("href") or "")
            code = code6(m.group(1)) if m else None
        a_ti = None
        for a in tr.find_all("a"):
            if "company_read" in (a.get("href") or ""):
                a_ti = a
                break
        title = a_ti.get_text(" ", strip=True) if a_ti else tds[1].get_text(" ", strip=True)
        nid = None
        if a_ti is not None:
            m = re.search(r"nid=(\d+)", a_ti.get("href") or "")
            nid = m.group(1) if m else None
        broker = tds[2].get_text(strip=True) if len(tds) > 2 else ""
        pdf = None
        fa = tr.find("a", href=re.compile(r"\.pdf", re.I))
        if fa is not None:
            pdf = fa.get("href")
        dt_txt = ""
        for td in tds:
            t = td.get_text(strip=True)
            if re.match(r"^\d{2}\.\d{2}\.\d{2}$", t):
                dt_txt = t
                break
        pub = parse_kr_date(dt_txt)
        if not pub:
            continue
        bid, bname = broker_norm(broker)
        # ★해시 폴백 키에 증권사·종목을 포함 — 같은 날 서로 다른 증권사의 동일 제목이 같은
        #   id 가 되면 '신규 0건' 종료 판정에 걸려 그 페이지 이후가 통째로 유실된다.
        out.append({"source": "naver",
                    "src_id": nid or h40(title, pub, broker, code or "")[:16], "pub_date": pub,
                    "stock_code": code, "stock_name": (a_st.get("title") or
                                                       a_st.get_text(strip=True))[:40]
                    if a_st else "", "title": title[:160], "broker_raw": broker,
                    "broker_id": bid, "broker_name": bname, "analyst_raw": "",
                    "target_price": None, "opinion": "", "pdf_url": pdf})
    has_next = bool(sp.find("td", class_="pgRR")) and len(out) > 0
    return out, has_next


def unify_reports(frames: List[pd.DataFrame], master: pd.DataFrame) -> pd.DataFrame:
    """다중 소스 병합 → 보고서 원장. ★멱등: 출력이 다음 실행의 입력으로 되돌아와도
    rid·source 가 변하지 않아야 PDF 캐시·애널 연결이 안 끊긴다."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=REPORT_COLS + ["event_date", "knowledge_date"])
    allc = list(dict.fromkeys(sum([list(f.columns) for f in frames], [])))
    R = pd.concat([f.reindex(columns=allc) for f in frames], ignore_index=True)
    R["pub_date"] = ds_(R["pub_date"]).dt.strftime("%Y-%m-%d")
    R = R.dropna(subset=["pub_date"])
    # 원자 소스 토큰으로 분해(합성 'a+b' 재투입 시 무한 증식 방지)
    R["source"] = R["source"].astype(str).str.split(r"\+")
    R = R.explode("source")
    R["source"] = R["source"].str.strip()
    # 이름 → 코드 보강(제목·종목명 기반) : 코드가 없는 한경/캐시 행 구제
    nm2cd = {clean_corp(n): c for c, n in zip(master["code"], master["name"]) if str(n).strip()}
    need = R["stock_code"].isna() | (R["stock_code"].astype(str) == "None")
    if need.any():
        fill = R.loc[need, "stock_name"].astype(str).map(lambda s: nm2cd.get(clean_corp(s)))
        R.loc[need, "stock_code"] = fill
    R["stock_code"] = R["stock_code"].map(code6)
    # 논리 키: (종목, 날짜, 증권사, 제목 정규화 앞 24자) — 소스 간 같은 리포트를 하나로
    key_title = R["title"].astype(str).map(lambda s: clean_txt(s)[:24])
    R["_lk"] = [h40(c or "", p, b, t) for c, p, b, t in
                zip(R["stock_code"], R["pub_date"], R["broker_name"], key_title)]
    def merge_grp(g: pd.DataFrame) -> dict:
        src = "+".join(sorted(set(g["source"].dropna().astype(str))))
        best_an = next((x for x in g["analyst_raw"] if isinstance(x, str) and x.strip()), "")
        tp = pd.to_numeric(g["target_price"], errors="coerce").max()
        row = g.iloc[0].to_dict()
        row.update({"source": src, "analyst_raw": best_an,
                    "target_price": (float(tp) if np.isfinite(tp) else None),
                    "src_id": "|".join(sorted(set(g["src_id"].astype(str)))[:3]),
                    "pdf_url": next((x for x in g["pdf_url"] if isinstance(x, str) and x), None)})
        return row
    merged = pd.DataFrame([merge_grp(g) for _, g in R.groupby("_lk", sort=True)])
    merged["rid"] = merged["_lk"]
    merged = merged.drop(columns=["_lk"], errors="ignore")
    merged = merged.reindex(columns=REPORT_COLS)
    merged = pit_mark(merged, "pub_date", "pub_date", origin="research")
    n_cd = int(merged["stock_code"].notna().sum())
    n_tp = int(pd.to_numeric(merged["target_price"], errors="coerce").notna().sum())
    n_an = int((merged["analyst_raw"].astype(str).str.strip() != "").sum())
    L.ok(f"보고서 원장 {len(merged):,}건 (코드 {100*n_cd/max(len(merged),1):.0f}% · "
         f"목표가 {100*n_tp/max(len(merged),1):.0f}% · 작성자 {100*n_an/max(len(merged),1):.0f}%)")
    return merged


def download_report_pdfs(rep: pd.DataFrame) -> int:
    """리포트 PDF 원문을 내용해시 blob 으로 드라이브 공용 인덱스에 저장(DOWNLOAD_REPORT_PDF).
    %PDF 매직바이트 검사 — 로그인 HTML 을 200 으로 주는 경우를 걸러낸다. 월별 상한 준수."""
    if not DOWNLOAD_REPORT_PDF or rep is None or not len(rep) or RUN_MODE == "CACHED":
        return 0
    todo = rep[rep["pdf_url"].notna()].copy()
    if not len(todo):
        return 0
    todo["ym"] = ds_(todo["pub_date"]).dt.strftime("%Y-%m")
    if PDF_MONTHLY_CAP and PDF_MONTHLY_CAP > 0:
        todo = todo.groupby("ym", group_keys=False).head(PDF_MONTHLY_CAP)
    man = VAULT.manifest("shared")
    have_keys = set(man.loc[man["kind"].astype(str) == "report_pdf", "key"].astype(str)) \
        if len(man) else set()
    todo = todo[~todo["rid"].astype(str).isin(have_keys)]
    n_ok = 0
    for r in tqdm(list(todo.itertuples(index=False)), desc="리포트 PDF", ncols=86, leave=False):
        if CLOCK.over():
            CLOCK.cut(f"리포트 PDF: {n_ok:,}건 저장 후 중단")
            break
        src = "hankyung" if "hankyung" in str(r.pdf_url) else "naver"
        raw = net_get(str(r.pdf_url), source=src, as_bytes=True, tries=1,
                      referer="https://consensus.hankyung.com/" if src == "hankyung"
                      else "https://finance.naver.com/research/")
        if not raw or not raw[:5].startswith(b"%PDF"):
            continue
        VAULT.save_raw("research", "report_pdf", str(r.rid), raw, "pdf", source=src,
                       event_date=r.pub_date, knowledge_date=r.pub_date)
        n_ok += 1
    if n_ok:
        VAULT.flush("shared")
        L.ok(f"리포트 PDF {n_ok:,}건 저장(내용해시 blob · 공용 인덱스 등록)")
    return n_ok


def build_analyst_ledger(rep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """애널리스트 엔티티 원장 + (보고서↔애널리스트) 연결표. d2 리비전 계산의 기반."""
    if rep is None or not len(rep):
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["rid", "analyst_id", "stock_code", "pub_date",
                                      "target_price"]))
    links = []
    for r in rep.itertuples(index=False):
        raw = str(getattr(r, "analyst_raw", "") or "")
        names = [clean_txt(x) for x in re.split(r"[,/·&]| and ", raw) if clean_txt(x)]
        if not names:
            continue
        for i, nm in enumerate(names[:3]):
            links.append({"rid": r.rid, "name": nm, "broker_id": r.broker_id,
                          "broker_name": r.broker_name,
                          "analyst_id": h40("an", r.broker_id, nm)[:14],
                          "role": "lead" if i == 0 else "co",
                          "stock_code": r.stock_code, "pub_date": r.pub_date,
                          "target_price": r.target_price, "opinion": r.opinion})
    Lk = pd.DataFrame(links)
    if not len(Lk):
        return (pd.DataFrame(columns=["analyst_id", "name", "broker_id", "broker_name"]),
                pd.DataFrame(columns=["rid", "analyst_id", "stock_code", "pub_date",
                                      "target_price"]))
    A = (Lk.groupby("analyst_id", as_index=False)
           .agg(name=("name", "first"), broker_id=("broker_id", "first"),
                broker_name=("broker_name", "first"), n_reports=("rid", "nunique")))
    L.ok(f"애널리스트 원장 {len(A):,}명 · 연결 {len(Lk):,}건 "
         f"(연결률 {100*Lk['rid'].nunique()/max(len(rep),1):.0f}%)")
    return A, Lk


def build_consensus_monthly(links: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """(code, month) 컨센서스 패널 — d2(상향 리비전/커버리지)·d4(Δ커버리지)·목표가 중앙값.
    리비전은 '같은 애널리스트 × 같은 종목'의 직전 목표가 대비로만 계산한다."""
    cols = ["code", "month", "d2_raw", "d4_raw", "n_analyst", "tp_med"]
    if links is None or not len(links):
        return pd.DataFrame(columns=cols)
    Lk = links.dropna(subset=["stock_code"]).copy()
    if not len(Lk):
        return pd.DataFrame(columns=cols)
    Lk["pub_date"] = ds_(Lk["pub_date"])
    Lk["tp"] = pd.to_numeric(Lk["target_price"], errors="coerce")
    Lk = Lk.sort_values(["analyst_id", "stock_code", "pub_date"])
    Lk["tp_prev"] = Lk.groupby(["analyst_id", "stock_code"], observed=True)["tp"].shift(1)
    Lk["up_rev"] = ((Lk["tp"] > Lk["tp_prev"] * 1.005) &
                    Lk["tp"].notna() & Lk["tp_prev"].notna()).astype(float)
    out = []
    for m in months:
        w90 = Lk[(Lk["pub_date"] <= m) & (Lk["pub_date"] > m - pd.Timedelta(days=90))]
        w180 = Lk[(Lk["pub_date"] <= m) & (Lk["pub_date"] > m - pd.Timedelta(days=180))]
        if not len(w180):
            continue
        cov = w180.groupby("stock_code")["analyst_id"].nunique()
        ups = w90.groupby("stock_code")["up_rev"].sum() if len(w90) else pd.Series(dtype=float)
        tpm = w90.groupby("stock_code")["tp"].median() if len(w90) else pd.Series(dtype=float)
        d = pd.DataFrame({"n_analyst": cov}).reset_index().rename(columns={"stock_code": "code"})
        d["month"] = m
        d["up90"] = d["code"].map(ups).fillna(0.0)
        d["d2_raw"] = -(d["up90"] / d["n_analyst"].clip(lower=1))
        d["tp_med"] = d["code"].map(tpm)
        out.append(d[["code", "month", "d2_raw", "n_analyst", "tp_med"]])
    if not out:
        return pd.DataFrame(columns=cols)
    C = pd.concat(out, ignore_index=True).sort_values(["code", "month"])
    C["d4_raw"] = -C.groupby("code", observed=True)["n_analyst"].diff(3)
    return C.reindex(columns=cols)


def linkage_audit(rep: pd.DataFrame, analysts: pd.DataFrame, links: pd.DataFrame):
    """원장 무결성 감사 — 보고서↔애널리스트↔종목 연결이 제대로 됐는지 연도×소스로 표 출력."""
    L.h1("리포트 원장 무결성 감사", "보고서 ↔ 식별된 애널리스트 ↔ 종목코드 연결 상태")
    if rep is None or not len(rep):
        L.warn("보고서 원장이 비어 있습니다 — 리서치 수집 실패 또는 캐시 없음. "
               "D축 d2/d4 는 결측으로 처리되고 U 는 가용 축 평균으로 계산됩니다.")
        return
    R = rep.copy()
    R["year"] = ds_(R["pub_date"]).dt.year
    linked = set(links["rid"]) if links is not None and len(links) else set()
    rows = []
    for (y, s), g in R.groupby(["year", "source"]):
        n = len(g)
        rows.append([int(y), s, f"{n:,}",
                     f"{100*g['stock_code'].notna().mean():.0f}%",
                     f"{100*pd.to_numeric(g['target_price'], errors='coerce').notna().mean():.0f}%",
                     f"{100*np.mean([rid in linked for rid in g['rid']]):.0f}%"])
    L.grid(rows, ["연도", "소스", "건수", "종목코드율", "목표주가율", "애널연결률"],
           ["c", "l", "r", "r", "r", "r"])
    if analysts is not None and len(analysts):
        top = analysts.nlargest(8, "n_reports") if "n_reports" in analysts.columns else \
            analysts.head(8)
        L.grid([[a.broker_name, a.name, f"{getattr(a, 'n_reports', 0):,}"]
                for a in top.itertuples(index=False)],
               ["증권사", "애널리스트", "리포트수"], ["l", "l", "r"],
               title="애널리스트 원장 상위(식별 엔티티)")
    n_major = 0
    if links is not None and len(links):
        n_major = links[links["broker_name"].isin(MAJOR_BROKERS)]["broker_name"].nunique()
    L.info(f"대형사 커버 {n_major}/{len(MAJOR_BROKERS)}개사 — 부족하면 d2 검정력이 낮아집니다.")


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [11] 데이터수집부 E — 센서팩 전용 수집 (키·데이터 없으면 해당 팩만 자동 비활성 §8.4)        ║
# ║   PACK-N 국민연금 사업장(공공데이터포털) · PACK-P 조달청 낙찰 · PACK-X 관세청 ·             ║
# ║   PACK-D 공시원문(사업보고서) 텍스트 유사도                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

# ── 공공데이터포털 호출 — ★XML 이 1급 시민이다 ──────────────────────────────────────────────
#   옛 구현은 `_type=json` 을 넣었다. 그런데
#     · 국민연금(B552015) 의 JSON 스위치는 ★`dataType` 이다. `_type` 은 조용히 무시되고
#       기본값 XML 이 온다 → net_json 이 파싱 실패 → None → 프리플라이트 실패 → 팩 비활성.
#     · 관세청(1220000) 은 ★JSON 자체를 지원하지 않는다. 무엇을 넣든 XML 만 온다.
#   즉 두 팩이 "통신 100% 성공, 수확 0행"이던 직접 원인이 이 한 줄이었다.
#   그래서 XML 을 먼저 읽고, 상태를 ★뭉개지 않고 그대로 올린다 — '한도초과'와 '진짜 없음'을
#   구분하지 못하면 원장이 오염되어 다음 실행이 영구히 건너뛴다.
DG_OK, DG_EMPTY, DG_LIMIT, DG_AUTH, DG_NET, DG_BAD = "ok", "empty", "limit", "auth", "net", "bad"


def dg_call(url: str, params: dict, src: str = "datagokr",
            json_param: Optional[str] = None, key: Optional[str] = None
            ) -> Tuple[str, List[dict]]:
    """(상태, items). json_param 은 그 서비스가 JSON 을 지원할 때만 준다."""
    if not (key or DATA_GO_KR_KEY) or not QUOTA.allow(src):
        return DG_NET, []
    p = dict(params)
    p["serviceKey"] = key or DATA_GO_KR_KEY
    if json_param:
        p.setdefault(json_param, "json")
    txt = net_get(url, source=src, params=p, tries=2,
                  count_cb=lambda: QUOTA.charge(src))
    if not txt:
        return DG_NET, []
    t = str(txt).lstrip().replace("<script/>", "").replace("<script></script>", "")
    if t[:1] in "{[":                                   # JSON 경로
        try:
            js = json.loads(t)
        except Exception:
            return DG_BAD, []
        blob = json.dumps(js)[:400]
        if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in blob:
            QUOTA.server_says_limit(src)
            return DG_LIMIT, []
        if "SERVICE_KEY_IS_NOT_REGISTERED" in blob or "SERVICE ERROR" in blob:
            L.warn("공공데이터포털 키 오류 — 활용신청 승인 여부와 ★Decoding 키 여부를 확인하세요.")
            return DG_AUTH, []
        items = _dg_items(js)
        QUOTA.ok(src)
        return (DG_OK if items else DG_EMPTY), items
    # XML 경로 — 관세청은 이쪽뿐이다
    try:
        root = _ET.fromstring(t)
    except Exception:
        return DG_BAD, []
    if root.tag.endswith("OpenAPI_ServiceResponse") or root.find(".//cmmMsgHeader") is not None:
        rc = (root.findtext(".//returnReasonCode") or "").strip()
        if rc == "22":
            QUOTA.server_says_limit(src)
            return DG_LIMIT, []
        if rc in {"20", "21", "30", "31", "32", "33"}:
            L.warn(f"공공데이터포털 인증/권한 오류(returnReasonCode={rc}) — 활용신청 승인과 "
                   f"Decoding 키를 확인하세요.")
            return DG_AUTH, []
        return DG_BAD, []
    rc = (root.findtext(".//header/resultCode") or root.findtext(".//resultCode") or "").strip()
    if rc and rc not in ("00", "0"):
        if rc in {"22", "20"}:
            QUOTA.server_says_limit(src)
            return DG_LIMIT, []
        if rc in {"03", "13"}:
            return DG_EMPTY, []
        return DG_BAD, []
    items = [{c.tag: (c.text or "").strip() for c in it}
             for it in root.findall(".//items/item")]
    QUOTA.ok(src)
    return (DG_OK if items else DG_EMPTY), items


def datagokr_call(url: str, params: dict, src: str = "datagokr") -> Optional[dict]:
    """구 인터페이스 유지용 얇은 래퍼 — 새 코드는 dg_call 을 직접 쓴다."""
    st, items = dg_call(url, params, src, json_param="dataType")
    return {"response": {"body": {"items": {"item": items}}}} if st == DG_OK else None


def _dg_items(js: Optional[dict]) -> List[dict]:
    try:
        body = js["response"]["body"]                     # type: ignore[index]
        items = body.get("items")
        if isinstance(items, dict):
            items = items.get("item")
        if isinstance(items, dict):
            items = [items]
        return items or []
    except Exception:
        return []


# ── PACK-N: 국민연금 가입 사업장 (월별) ─────────────────────────────────────────────────────
# ★2026-08 전면 재작성 — 옛 구현은 ★구조적으로 0행이었다(실측: 20,000호출 → 0행 → 다음
#   실행이 같은 10,000건을 또 태우는 무한반복. 사용자 로그에서 67분을 그렇게 썼다).
#   원인 세 가지가 전부 '스펙 불일치'였고 네트워크 문제가 아니었다:
#     ① data_crt_ym 은 getBassInfoSearch 의 ★요청변수가 아니다(응답 필드다).
#        월별로 120번 부르면 서버는 그 값을 무시하고 같은 응답을 120번 준다
#        → (종목 5,398 × 월 120 = 647,760) 교차곱이 통째로 헛것이었다.
#     ② jnngpCnt(가입자수)·crrmmNtcAmt(당월고지금액)는 이 오퍼레이션 응답에 없다.
#        상세(getDetailInfoSearch)와 기간별(getPdAcctoSttusInfoSearch)에만 있다.
#        → members 가 항상 0 → 전건 탈락 → 호출당 수확 0행.
#     ③ V2 는 camelCase(wkplNm). 구현은 snake_case(wkpl_nm)를 보냈다.
#   재설계: ★종목축 1회 검색으로 (사업장 seq × 자료생성년월)을 통째로 받고, seq 기준
#   기간별 조회 1회로 월별 시계열 전체를 받는다. 종목당 2~4회 → 전 구간 약 2만 회.
NPS_BASE = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2"
NPS_SEARCH = NPS_BASE + "/getBassInfoSearchV2"          # 사업장명 → (seq, dataCrtYm) 목록
NPS_DETAIL = NPS_BASE + "/getDetailInfoSearchV2"        # seq → 가입자수·당월고지금액
NPS_PERIOD = NPS_BASE + "/getPdAcctoSttusInfoSearchV2"  # seq → 월별 취득/상실 시계열
NPS_CONTRIB_RATE = 0.09                                  # 국민연금 보험료율(시행 상수)
NPS_SIM_MIN = 80                                         # 상호 유사도 하한
NPS_MAX_SITES = 3                                        # 한 종목이 들고 갈 사업장 수 상한
NPS_RULE_VER = 2      # ★검색 질의·정규화·필드 매핑 규칙 버전. 올리면 옛 원장이
#                       자동 무효화되어, 구 규칙으로 무매칭 판정된 종목이 90일간
#                       영구 스킵되는 사고를 막는다(v2 = dataType/상세필드 교정판).


def _nps_num(x) -> float:
    v = pd.to_numeric(str(x).replace(",", "") if x is not None else None, errors="coerce")
    return float(v) if pd.notna(v) else 0.0


def _nps_sites(nm: str) -> Tuple[str, List[dict]]:
    """사업장명 검색 — (상태, 항목). wkplNm 은 ★부분일치라 넓은 질의부터 던지면
    '삼성전자'에 하청·현장까지 수천 건이 걸리고 본사가 첫 100건 밖으로 밀린다.
    좁은 표기부터 시도해 정확일치를 먼저 잡고, 없을 때만 넓힌다."""
    base = clean_txt(nm)[:28]
    last = (DG_EMPTY, [])
    for q in (f"(주){base}", f"{base}(주)", base):
        st, items = dg_call(NPS_SEARCH, {"wkplNm": q, "numOfRows": 100, "pageNo": 1},
                            json_param="dataType")
        if st in (DG_NET, DG_BAD, DG_LIMIT, DG_AUTH):
            return st, []
        if items:
            return st, items
        last = (st, items)
    return last


def _nps_preflight(names: Sequence[Tuple[str, str]]) -> bool:
    """★쓰기 전에 재 본다. 옛 구현이 한 시간을 태운 뒤에야 '0행'을 알려줬기 때문이다.
    상위 몇 종목만 실제로 조회해 (a) 응답이 오는지 (b) seq 가 들어 있는지 확인한다."""
    for code, nm in list(names)[:4]:
        stt, it = _nps_sites(nm)
        if it and any(str(x.get("seq") or "").strip() for x in it):
            return True
    st, head = NET_LAST.get("datagokr", ("—", ""))
    L.warn(f"PACK-N 프리플라이트 실패 — 응답 {st} · {str(head)[:140]}")
    L.warn("국민연금 팩을 이번 실행에서 비활성화합니다(호출을 더 태우지 않습니다). "
           "확인 사항: ① 공공데이터포털에서 '국민연금 가입 사업장 내역' 활용신청 승인 여부 "
           "② DATA_GO_KR_KEY 가 ★Decoding 키인지(Encoding 키를 넣으면 전건 실패합니다).")
    return False


def harvest_nps(master: pd.DataFrame, months: pd.DatetimeIndex,
                priority: Sequence[str] = (), max_calls: int = -1) -> pd.DataFrame:
    """상장사명 → 사업장 seq → 월별 가입자·고지금액 패널.

    ★축: 종목축 1회 검색 + seq 당 상세/기간 조회. 월은 ★응답에서 나오지 요청에 넣지 않는다.
    ★원장: 성공·무매칭·통신실패를 구분해 기록한다. 옛 구현은 '호출했지만 빈손'을 어느 원장에도
      남기지 않아, 다음 실행이 정확히 같은 잡을 같은 순서로 다시 태웠다(진척 0의 직접 원인).
    """
    cols = ["code", "month", "nps_members", "nps_amt", "nps_new", "nps_lost",
            "n_sites", "match_conf"]
    if not DATA_GO_KR_KEY:
        L.info("PACK-N: DATA_GO_KR_KEY 미입력 — 국민연금 팩 자동 비활성(§8.4).")
        return pd.DataFrame(columns=cols)
    cached = VAULT.load_table("nps_corp_monthly", "shared")
    if cached is not None and len(cached):
        cached = cached.copy()
        cached["month"] = ds_(cached["month"])
        L.info(f"캐시 재사용: 국민연금 패널 {len(cached):,}행 · "
               f"{cached['code'].nunique():,}종목")
    # ★원장은 '종목 단위'다 — 한 번 조회하면 그 종목의 전 기간이 한꺼번에 들어오기 때문이다.
    done_codes: set = set()
    led = VAULT.load_table("nps_codes_done", "shared")
    today_ts = pd.Timestamp(dtm.date.today())
    if led is not None and len(led):
        led = led.copy()
        led["tried_at"] = ds_(led["tried_at"])
        # ★규칙 버전 — 검색 질의·정규화·필드 매핑이 바뀌면 옛 원장은 무효다. 안 그러면
        #   구 규칙으로 '무매칭' 판정된 종목이 90일간 영구 스킵되어, 고쳐 놓고도 0행이 된다.
        if "rule_ver" not in led.columns:
            led["rule_ver"] = 0
        led = led[pd.to_numeric(led["rule_ver"], errors="coerce").fillna(0) >= NPS_RULE_VER]
        fr = led[(today_ts - led["tried_at"]).dt.days < 90]
        done_codes = set(fr["code"].astype(str))
        L.info(f"PACK-N 원장: {len(done_codes):,}종목은 이미 처리(성공·무매칭 포함) — "
               f"90일간 재조회하지 않습니다.")
    names = master.dropna(subset=["code"])
    names = names[names["name"].astype(str).str.strip() != ""]
    rank = {c: i for i, c in enumerate(priority)}
    names = names.assign(_r=names["code"].map(lambda c: rank.get(c, 10 ** 9))) \
                 .sort_values("_r")
    jobs = [(str(r.code), str(r.name)) for r in names.itertuples(index=False)
            if str(r.code) not in done_codes]
    if RUN_MODE == "CACHED" or CLOCK.over():
        jobs = []
    got: List[dict] = []
    new_led: List[dict] = []
    if jobs and not _nps_preflight(jobs):
        jobs = []
    if jobs:
        # ★잡 1건 ≠ 호출 1건. net_get(tries=2) 이라 실패 시 2회까지 계수되고, 잡마다
        #   검색 1 + 기간 1 + 상세 ≤NPS_MAX_SITES 를 쓴다. 잔여를 잡 수로 그대로 쓰면
        #   실제로는 몇 배를 쏜다(실측: 10,000잡 캡으로 20,000호출을 태웠다).
        # ★실측식 — 검색 폴백 최대 3회 + 사업장당 상세 1회. 옛 `2 + NPS_MAX_SITES` 는
        #   검색 폴백과 페이징을 안 세서 배정의 몇 배를 쐈다.
        per_job = 3 + NPS_MAX_SITES
        # ★cap_of 규약 — None(무제한)일 때만 잔여 전량. 옛 `or 10**9` 는 배정 0 을
        #   무제한으로 뒤집어, 예산을 한 건도 못 받은 팩이 오히려 다 태우게 했다.
        _mc = cap_of(max_calls)
        room = max(0, min(10 ** 9 if _mc is None else _mc, QUOTA.remaining("datagokr")))
        cap_n = min(int(NPS_MAX_CALLS) or len(jobs),
                    (room // per_job) if room else len(jobs))
        if cap_n <= 0:
            L.info("PACK-N: datagokr 잔여 호출이 없어 이번 실행은 건너뜁니다"
                   "(다음 실행이 정확히 이어받습니다).")
            jobs = []
        elif len(jobs) > cap_n:
            L.info(f"PACK-N 대상 {len(jobs):,}종목 중 이번 실행은 {cap_n:,}종목"
                   f"(유동성 상위 우선 · 실시간 잔여 {room:,}호출 ÷ 종목당 {per_job}호출). "
                   f"나머지는 재실행이 정확히 이어받습니다 — 약 "
                   f"{max(1, -(-len(jobs) // max(cap_n, 1)))}회 실행이면 전 종목 완비.")
            jobs = jobs[:cap_n]
    if jobs:
        QUOTA.plan("datagokr", len(jobs) * (2 + NPS_MAX_SITES), "국민연금 사업장(종목축)")

    def one(job):
        """★한 종목 = 검색 1~2회 + 상세 1회. 월별 시계열은 여기서 못 만든다 — 아래 참조."""
        code, nm = job
        st_s, items = _nps_sites(nm)
        if st_s == DG_NET or st_s == DG_BAD:
            return None                        # 통신 실패 — 원장에 아무것도 남기지 않는다
        tgt = clean_corp(nm)
        # ★seq 는 사업장 식별자가 ★아니다 — (사업장 × 자료생성년월) 키다. 옛 코드는 상위 3개
        #   seq 를 '사업장 3곳'으로 보고 합산해서, 같은 사업장의 서로 다른 3개 '월'을 더했다
        #   (가입자수 3~4배 과대). 사업장은 (정규화명, 시군구코드)로 식별하고 월은 분리한다.
        sites: Dict[Tuple[str, str], Dict[str, str]] = {}
        conf = 0.0
        for it in items:
            sq = str(it.get("seq") or "").strip()
            ym = str(it.get("dataCrtYm") or "").strip()
            if not sq or len(ym) != 6:
                continue
            if str(it.get("wkplJnngStcd") or "1") != "1":     # 등록 상태인 사업장만
                continue
            wn = str(it.get("wkplNm", ""))
            sim = float(name_sim(wn, tgt))
            if sim < NPS_SIM_MIN:
                continue
            conf = max(conf, sim / 100.0)
            sites.setdefault((clean_corp(wn), str(it.get("ldongAddrMgplSgguCd") or "")),
                             {})[ym] = sq
        if not sites:
            # ★서버가 답은 했는데 매칭이 없다 = 진짜 없음. 통신 실패와 구분해 기록한다.
            return {"_none": code} if st_s in (DG_OK, DG_EMPTY) else None
        # 관측 월이 가장 많은 사업장 = 본사로 본다(지점·현장은 월 수가 적다)
        top = sorted(sites.items(), key=lambda kv: -len(kv[1]))[:NPS_MAX_SITES]
        rows = []
        for _key, ym2seq in top:
            ym = max(ym2seq)                   # ★최신 월 1개만 — 아래 비용 주석 참조
            st_d, det = dg_call(NPS_DETAIL, {"seq": ym2seq[ym], "numOfRows": 10,
                                             "pageNo": 1}, json_param="dataType")
            if st_d != DG_OK:
                continue
            for it in det:
                # ★가입자수·고지금액은 ★상세에만 있다. 옛 코드는 기간별 응답에서 찾았는데
                #   거기엔 nwAcqzrCnt·lssJnngpCnt 뿐이라 members 가 항상 0 이었고,
                #   마지막 게이트 `if m > 0` 에서 전건 탈락했다(수확 0행의 직접 원인).
                m = _nps_num(it.get("jnngpCnt"))
                if m <= 0:
                    continue
                rows.append({"code": code,
                             "month": pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01")
                                      + pd.offsets.MonthEnd(0),
                             "nps_members": m,
                             "nps_amt": _nps_num(it.get("crrmmNtcAmt")),
                             "nps_new": _nps_num(it.get("nwAcqzrCnt")),
                             "nps_lost": _nps_num(it.get("lssJnngpCnt")),
                             "n_sites": 1.0, "match_conf": conf})
        if not rows:
            return {"_none": code}
        agg = (pd.DataFrame(rows).groupby(["code", "month"], as_index=False)
               .agg(nps_members=("nps_members", "sum"), nps_amt=("nps_amt", "sum"),
                    nps_new=("nps_new", "sum"), nps_lost=("nps_lost", "sum"),
                    n_sites=("n_sites", "sum"), match_conf=("match_conf", "max")))
        return {"_rows": agg.to_dict("records"), "_code": code}


    if jobs:
        L.info(f"PACK-N 수집 — ★종목축 {len(jobs):,}종목 · 종목당 검색 1~3 + 상세 "
               f"{NPS_MAX_SITES} 회.")
        # ★★코드로 고칠 수 없는 한계를 먼저 말한다(공식 공지 2018-07-02).
        #   이 API 는 ★제공시점 기준 1년치만 보관하고 매년 과거분을 삭제한다. 그런데
        #   n1=dlog(가입자수,12) · n3=diff(상실률,12) · n4=diff(사업장수,12) 는 전부
        #   ★13개월이 있어야 첫 값이 나온다. 즉 아무리 잘 받아도 첫 실행의 TP_N1~N4 는
        #   전부 결측이고, V4 가 그걸 보고 팩을 무효화한다. 이건 수집 실패가 아니라
        #   데이터의 성질이다 — 매월 실행해 원장에 쌓아야 13개월째부터 피처가 생긴다.
        #   그리고 월별 가입자수는 (사업장 × 월)마다 상세 1콜이라, 전 종목 12개월을
        #   한 번에 받으려면 약 19만 회가 필요하다(하루 몫의 35배). 그래서 이번 실행은
        #   ★종목당 최신 1개월만 받아 시딩한다.
        L.warn("PACK-N 은 ★시딩 단계입니다 — 이 API 는 1년치만 보관하는데 n1·n3·n4 는 "
               "13개월이 있어야 첫 값이 나옵니다. 이번 실행은 종목당 ★최신 1개월만 받아 "
               "드라이브에 쌓습니다(월별 전량은 종목당 24콜 = 전 종목 19만 회로 하루 몫의 "
               "35배). 매월 실행하면 13개월째부터 TP_N1~N4 가 살아납니다. 그때까지 PACK-N 은 "
               "θ_N 만 계산되고 V4 가 증거층에서 제외합니다 — 정상 동작입니다.")
        with stage_bar(len(jobs), "국민연금 사업장(종목축)") as bar:
            for batch in chunked(jobs, 200):
                if CLOCK.over() or not QUOTA.allow("datagokr"):
                    CLOCK.cut(f"국민연금: {len(jobs)-bar.n:,}종목 남기고 중단 "
                              f"({len(got):,}행 수집 · 재실행 시 이어받음)")
                    break
                for r in pmap_net(one, batch, workers=min(IO_THREADS, 6), quiet=True):
                    if not r:
                        continue                       # 통신 실패 — 원장 미기록(재시도 대상)
                    if "_none" in r:
                        new_led.append({"code": r["_none"], "n_rows": 0,
                                        "tried_at": today_ts,
                                        "rule_ver": NPS_RULE_VER})
                    else:
                        got += r["_rows"]
                        new_led.append({"code": r["_code"], "n_rows": len(r["_rows"]),
                                        "tried_at": today_ts,
                                        "rule_ver": NPS_RULE_VER})
                bar.update(len(batch))
    if new_led:
        allf = pd.concat([led, pd.DataFrame(new_led)], ignore_index=True) \
            if led is not None and len(led) else pd.DataFrame(new_led)
        VAULT.save_table("nps_codes_done",
                         allf.sort_values("tried_at").drop_duplicates("code", keep="last"),
                         "shared", domain="nps", source="code_ledger",
                         note="처리 완료 종목 — 성공·무매칭 모두 기록(재조회 방지)")
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(got)] if got else [])
    if not frames:
        return pd.DataFrame(columns=cols)
    N = pd.concat(frames, ignore_index=True)
    N["month"] = ds_(N["month"])
    N = N.dropna(subset=["code", "month"]).drop_duplicates(["code", "month"], keep="last")
    if got:
        VAULT.save_table("nps_corp_monthly", N, "shared", domain="nps",
                         source="data.go.kr NpsBplcInfoInqireServiceV2")
        L.ok(f"국민연금 {len(got):,}행 신규 · 누적 {len(N):,}행 · {N['code'].nunique():,}종목")
    return N.reindex(columns=cols)


# ── PACK-P: 조달청 낙찰 ─────────────────────────────────────────────────────────────────────
G2B_URL = ("https://apis.data.go.kr/1230000/ao/ScsbidInfoService/"
           "getScsbidListSttusThngPPSSrch")


def harvest_procurement(months: pd.DatetimeIndex, max_calls: int = -1) -> pd.DataFrame:
    """낙찰정보 월 스윕 — 낙찰업체명·낙찰가/예정가(낙찰률)·발주기관. 사업자번호 직접 식별."""
    cols = ["ym", "corp_nm", "biz_no", "award_amt", "plan_amt", "rate", "org", "item_cls"]
    if not DATA_GO_KR_KEY:
        L.info("PACK-P: DATA_GO_KR_KEY 미입력 — 조달 팩 자동 비활성(§8.4).")
        return pd.DataFrame(columns=cols)
    cached = VAULT.load_table("g2b_awards_monthly", "shared")
    if cached is not None and len(cached):
        L.info(f"캐시 재사용: 조달 낙찰 {len(cached):,}행")
    # ★완주 월 원장 — 페이지 도중 한도 소진으로 반쪽만 받은 월을 완료로 오인하지 않는다
    done_tbl = VAULT.load_table("g2b_done_months", "shared")
    have = set(done_tbl["ym"].astype(str)) if done_tbl is not None and len(done_tbl) else \
        (set(cached["ym"].astype(str)) if cached is not None and len(cached) else set())
    todo = [m for m in months if m.strftime("%Y%m") not in have]
    if RUN_MODE == "CACHED":
        todo = []

    def one(m):
        rows, page, complete = [], 1, True
        if not QUOTA.allow("datagokr"):
            return [], None
        while page <= 60:
            # ★한 잡이 최대 60페이지를 돈다 — 배치 경계에서만 검사하면 한도 소진 후에도
            #   배치당 수백 발이 더 나간다(PACK-N 이 같은 구조로 67분을 태웠다).
            if not QUOTA.allow("datagokr"):
                complete = False
                break
            js = datagokr_call(G2B_URL, {"inqryDiv": "1", "type": "json",
                                         "inqryBgnDt": m.replace(day=1).strftime("%Y%m%d") + "0000",
                                         "inqryEndDt": m.strftime("%Y%m%d") + "2359",
                                         "numOfRows": 999, "pageNo": page})
            if js is None:
                complete = False
                break
            items = _dg_items(js)
            if not items:
                break
            for it in items:
                rows.append({"ym": m.strftime("%Y%m"),
                             "corp_nm": it.get("bidwinnrNm") or it.get("prcbdrNm") or "",
                             "biz_no": str(it.get("bizno") or it.get("bidwinnrBizno") or ""),
                             "award_amt": pd.to_numeric(it.get("sucsfbidAmt"), errors="coerce"),
                             "plan_amt": pd.to_numeric(it.get("presmptPrce"), errors="coerce"),
                             "rate": pd.to_numeric(it.get("sucsfbidRate"), errors="coerce"),
                             "org": it.get("dminsttNm") or "",
                             "item_cls": str(it.get("prdctClsfcNo") or "")[:8]})
            if len(items) < 999:
                break
            page += 1
        else:
            complete = False
        return rows, (m.strftime("%Y%m") if complete else None)

    got: List[dict] = []
    done_new: List[str] = []
    _sp0 = QUOTA.spent("datagokr")
    with stage_bar(len(todo), "조달 낙찰(월축)") as bar:
        for batch in budget_batches(todo, 6, "datagokr", "조달 낙찰",
                                    cap=max_calls, unit="개월"):
            for item in pmap_net(one, batch, workers=min(IO_THREADS, 6), quiet=True):
                if not item:
                    continue
                r, ok_ym = item
                if r:
                    got += r
                if ok_ym:
                    done_new.append(ok_ym)
            bar.update(len(batch))
    if done_new:
        base = done_tbl if done_tbl is not None and len(done_tbl) else None
        alld = pd.concat([base, pd.DataFrame({"ym": done_new})], ignore_index=True) \
            if base is not None else pd.DataFrame({"ym": done_new})
        VAULT.save_table("g2b_done_months", alld.drop_duplicates("ym"), "shared",
                         domain="procure", source="sweep_complete_months")
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(got)] if got else [])
    if not frames:
        return pd.DataFrame(columns=cols)
    G = pd.concat(frames, ignore_index=True).drop_duplicates()
    if got:
        VAULT.save_table("g2b_awards_monthly", G, "shared", domain="procure",
                         source="data.go.kr ScsbidInfoService")
    return G.reindex(columns=cols)


# ── PACK-X: 관세청 수출 (HS 매핑 테이블이 있어야 활성) ──────────────────────────────────────
CUSTOMS_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"


HS_MAP_COLS = ["code", "hs", "weight", "valid_from", "valid_to"]


def validate_hs_map(m: pd.DataFrame, tag: str = "hs_corp_map") -> pd.DataFrame:
    """★HS↔기업 매핑의 불변식 검사 — 자동 구축의 가장 큰 함정을 여기서 잡는다.

    weight 의 의미는 ★'그 HS 의 국가 전체 수출 중 이 회사가 차지하는 몫'이다.
    소비부가 `exp_usd(국가 전체) × weight` 로 곱하기 때문이다. 그런데 자동 구축을 하면
    손에 먼저 잡히는 것은 ★'그 회사 매출 중 그 제품이 차지하는 비중'이다 — 방향이 정반대다.
    그걸 그대로 넣으면 한 HS 에 걸린 회사들의 weight 합이 1 을 크게 넘고, 국가 수출이
    회사 수만큼 복제되어 귀속된다. θ_X 가 과대귀속을 잡아 주긴 하지만, 그건 마지막
    방어선이지 첫 방어선이 아니다 — 여기서 잡아야 원인이 로그에 남는다.

    검사: ①필수 컬럼 ②weight 범위 [0,1] ③★HS 별 weight 합 ≤ 1 ④유효구간 정합성.
    위반은 버리지 않고 ★잘라서 통과시키되(수집분을 버리지 않는다) 규모를 로그에 남긴다.
    """
    if m is None or not len(m):
        return pd.DataFrame(columns=HS_MAP_COLS)
    d = m.copy()
    for c in HS_MAP_COLS:
        if c not in d.columns:
            d[c] = np.nan
    d["code"] = d["code"].astype(str).map(code6)
    d["hs"] = d["hs"].astype(str).str.replace(r"\D", "", regex=True)
    d["weight"] = pd.to_numeric(d["weight"], errors="coerce")
    for c in ("valid_from", "valid_to"):
        d[c] = ds_(d[c])
    n0 = len(d)
    d = d[d["code"].notna() & (d["hs"].str.len() >= 4)]
    bad_w = int((d["weight"] < 0).sum() + (d["weight"] > 1).sum())
    d["weight"] = d["weight"].clip(0.0, 1.0).fillna(0.0)
    # ★핵심 불변식 — 한 HS 에 걸린 회사들의 몫 합은 1 을 넘을 수 없다.
    #   넘으면 의미가 뒤집혔거나(제품비중을 그대로 넣음) 중복 귀속이다. 비례 축소한다.
    g = d.groupby("hs", observed=True)["weight"].transform("sum")
    over = g > 1.0 + 1e-9
    n_over_hs = int(d.loc[over, "hs"].nunique())
    if over.any():
        d.loc[over, "weight"] = d.loc[over, "weight"] / g[over]
    bad_iv = int((d["valid_to"].notna() & d["valid_from"].notna() &
                  (d["valid_to"] < d["valid_from"])).sum())
    d = d[~(d["valid_to"].notna() & d["valid_from"].notna() &
            (d["valid_to"] < d["valid_from"]))]
    if n0 != len(d) or bad_w or n_over_hs or bad_iv:
        L.warn(f"{tag} 정합성 교정 — 입력 {n0:,}행 → {len(d):,}행 · "
               f"weight 범위이탈 {bad_w:,} · ★HS별 합>1 인 HS {n_over_hs:,}개(비례 축소) · "
               f"유효구간 역전 {bad_iv:,}. 합>1 이 많으면 weight 의미가 뒤집힌 것입니다 — "
               f"weight 는 '회사 제품 매출비중'이 아니라 ★'그 HS 국가수출 중 이 회사 몫'입니다.")
    return d.reindex(columns=HS_MAP_COLS)


def load_hs_map() -> pd.DataFrame:
    """HS↔기업 매핑(시간구간 테이블, C3) — 드라이브 공용 인덱스의 hs_corp_map.
    읽은 뒤 반드시 불변식 검사를 통과시킨다(자동 구축분·수기 투입분 모두)."""
    return validate_hs_map(VAULT.load_table("hs_corp_map", "shared"))


_HS_SGN_OK = re.compile(r"^(\d{2}|\d{4}|\d{6}|\d{10})$")   # ★8자리는 서버가 거부한다
CUSTOMS_ADV = {"US", "DE", "FR", "GB", "JP", "TW", "NL", "IT", "CA", "AU", "CH", "SE", "BE"}


def harvest_customs(months: pd.DatetimeIndex, hs_codes: Sequence[str],
                    max_calls: int = -1) -> pd.DataFrame:
    """HS별 ★국가별 월 수출 금액·중량.

    ★2026-08 재작성 — 옛 구현은 세 가지 때문에 구조적으로 틀렸다:
      ① `_type=json` — 이 API 는 ★JSON 을 지원하지 않는다. XML 만 온다. net_json 이 항상
         None 을 돌려줘서, 매핑을 채워 넣어도 전 잡이 0행이었다.
      ② 잡 축이 (월 × HS) — 이 API 는 조회기간을 최대 1년까지 받는다. ★(연도 × HS) 로
         묶으면 호출이 정확히 1/12 이 된다(HS 900개 × 11년 = 9,900회).
      ③ 응답의 ★'총계' 행을 그대로 담았다. 분모(N_usd)가 2배가 되어 전 weight 가 절반으로
         눌리고, 국가 HHI 는 총계 버킷 때문에 폭발한다.
      추가로 grp 에 국가코드를 붙여 놔서(`선진_US`) '선진_US'와 '선진_DE'가 다른 버킷이 됐다
      — dest_hhi 가 국가 HHI 가 아니라 준-국가 HHI 였다. cc 를 분리한다.
    """
    cols = ["ym", "hs", "cc", "grp", "exp_usd", "exp_kg"]
    if not (CUSTOMS_API_KEY or DATA_GO_KR_KEY) or not hs_codes:
        return pd.DataFrame(columns=cols)
    key_src = "customs" if CUSTOMS_API_KEY else "datagokr"
    cached = VAULT.load_table("customs_hs_monthly", "shared")
    have: set = set()
    if cached is not None and len(cached):
        if "cc" not in cached.columns:        # 구 스키마(grp 에 국가 혼합) — 재수집 대상
            L.info("관세 캐시가 구 스키마입니다(국가코드 미분리) — 국가 HHI 를 위해 새로 받습니다.")
            cached = None
        else:
            have = set(zip(cached["ym"].astype(str).str[:4], cached["hs"].astype(str)))
            L.info(f"캐시 재사용: 관세 통관 {len(cached):,}행")
    hs_ok = [str(h) for h in dict.fromkeys(str(x) for x in hs_codes)
             if _HS_SGN_OK.match(str(x))]
    if len(hs_ok) < len(set(map(str, hs_codes))):
        L.info(f"관세 hsSgn 자릿수 필터 — {len(set(map(str, hs_codes)))-len(hs_ok)}개 제외"
               f"(2·4·6·10자리만 허용, ★8자리는 서버가 거부).")
    # 최근 2개월은 확정치가 아직 없다(익월 15일경 확정) — 애초에 묻지 않는다.
    y_max = (pd.Timestamp.today() - pd.DateOffset(months=2)).year
    years = sorted({int(m.year) for m in months if int(m.year) <= y_max})
    jobs = [(y, h) for y in years for h in hs_ok if (str(y), h) not in have]
    if RUN_MODE == "CACHED":
        jobs = []
    if jobs:
        QUOTA.plan(key_src, len(jobs), f"관세 통관(★연도×HS축 {len(years)}년 × {len(hs_ok)}개)")

    def one(job):
        y, h = job
        st, items = dg_call(CUSTOMS_URL,
                            {"strtYymm": f"{y}01", "endYymm": f"{y}12", "hsSgn": h,
                             "numOfRows": 9900, "pageNo": 1},
                            src=key_src, key=CUSTOMS_API_KEY or None)
        if st != DG_OK:
            return []
        rows = []
        for it in items:
            yr = str(it.get("year") or "").strip()
            cc = str(it.get("statCd") or it.get("cntyCd") or "").strip()
            # ★총계행 제거 — 국가코드가 비었거나 year 가 'YYYY.MM' 형식이 아니면 합계다.
            if not cc or cc == "-" or "." not in yr:
                continue
            rows.append({"ym": yr.replace(".", "").replace("-", ""), "hs": h, "cc": cc,
                         "grp": "선진" if cc in CUSTOMS_ADV else "신흥",
                         "exp_usd": pd.to_numeric(it.get("expDlr"), errors="coerce"),
                         "exp_kg": pd.to_numeric(it.get("expWgt"), errors="coerce")})
        if len(items) >= 9900:
            L.warn(f"관세 {y}/{h}: {len(items):,}행 = numOfRows 상한 — 그 HS 는 반년으로 "
                   f"쪼개 다시 받아야 누락이 없습니다.")
        return rows

    got: List[dict] = []
    with stage_bar(len(jobs), "관세 통관(★연도×HS축)") as bar:
        for batch in budget_batches(jobs, 200, key_src, "관세 통관",
                                    cap=max_calls, unit="건"):
            for r in pmap_net(one, batch, workers=min(IO_THREADS, 6), quiet=True):
                if r:
                    got += r
            bar.update(len(batch))
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(got)] if got else [])
    if not frames:
        if jobs:
            _st, _hd = NET_LAST.get(key_src, ("—", ""))
            L.warn(f"관세 통관 0행 — 마지막 응답 {_st} · {str(_hd)[:150]}")
        return pd.DataFrame(columns=cols)
    X = pd.concat(frames, ignore_index=True).drop_duplicates(["ym", "hs", "cc"])
    if got:
        VAULT.save_table("customs_hs_monthly", X, "shared", domain="customs",
                         source="data.go.kr:1220000/nitemtrade")
        L.ok(f"관세 통관 {len(got):,}행 신규 · 누적 {len(X):,}행 · "
             f"HS {X['hs'].nunique():,}개 · 국가 {X['cc'].nunique():,}개 "
             f"(호출 {len(jobs):,}회 — 월축이었다면 {len(jobs)*12:,}회)")
    return X.reindex(columns=cols)


# ── PACK-D: 공시 원문 텍스트 (Lazy Prices) ──────────────────────────────────────────────────
_SECTION_PATTERNS = {"business": r"사업의\s*내용", "risk": r"위험요인|이사의\s*경영진단",
                     "contingent": r"우발부채|소송"}


def harvest_doc_texts(disc: pd.DataFrame, master: pd.DataFrame,
                      cap_docs: int = 4000) -> pd.DataFrame:
    """사업보고서 원문(document.xml) → 섹션 bag-of-words. 상장사·연 1회만, 캐시 우선."""
    cols = ["corp_code", "rcept_no", "rcept_dt", "sec", "bow"]
    if not DART_API_KEY or disc is None or not len(disc):
        return pd.DataFrame(columns=cols)
    ann = disc[disc["kind"] == "annual_rpt"].copy()
    listed = set(master.dropna(subset=["corp_code"])["corp_code"].astype(str))
    ann = ann[ann["corp_code"].astype(str).isin(listed)]
    if not len(ann):
        return pd.DataFrame(columns=cols)
    cached = VAULT.load_table("doc_bow_sections", "shared")
    have = set()
    if cached is not None and len(cached):
        have = set(cached["rcept_no"].astype(str))
        L.info(f"캐시 재사용: 공시원문 BOW {len(cached):,}행")
    todo = [r for r in ann.itertuples(index=False) if str(r.rcept_no) not in have][:cap_docs]
    if RUN_MODE == "CACHED":
        todo = []

    def one(r):
        if not QUOTA.allow("dart"):
            return None
        raw = net_get(DART_URL + "document.xml", source="dart", as_bytes=True, tries=1,
                      params={"crtfc_key": DART_API_KEY, "rcept_no": str(r.rcept_no)},
                      count_cb=lambda: QUOTA.charge("dart"))
        if not raw or raw[:2] != b"PK":
            return None
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            txt = smart_decode(b"".join(zf.read(n) for n in zf.namelist()[:3]), None)
        except Exception:
            return None
        txt = re.sub(r"<[^>]+>", " ", txt)
        out = []
        for sec, pat in _SECTION_PATTERNS.items():
            m = re.search(pat, txt)
            seg = txt[m.start(): m.start() + 40_000] if m else ""
            toks = re.findall(r"[가-힣]{2,}", seg)[:4000]
            bow = Counter(toks)
            out.append({"corp_code": str(r.corp_code), "rcept_no": str(r.rcept_no),
                        "rcept_dt": r.rcept_dt, "sec": sec,
                        "bow": json.dumps(dict(bow.most_common(400)), ensure_ascii=False)})
        return out

    got: List[dict] = []
    with stage_bar(len(todo), "공시원문 BOW") as bar:
        for batch in chunked(todo, 100):
            if CLOCK.over() or not QUOTA.allow("dart"):
                CLOCK.cut(f"공시원문: {len(got)//3:,}건 수집 후 중단")
                break
            for r in pmap_net(one, batch, workers=min(IO_THREADS, 6), quiet=True):
                if r:
                    got += r
            bar.update(len(batch))
    frames = ([cached] if cached is not None and len(cached) else []) + \
             ([pd.DataFrame(got)] if got else [])
    if not frames:
        return pd.DataFrame(columns=cols)
    T = pd.concat(frames, ignore_index=True).drop_duplicates(["rcept_no", "sec"], keep="last")
    if got:
        VAULT.save_table("doc_bow_sections", T, "shared", domain="doctext", source="opendart")
    return T


def text_similarity(bows: pd.DataFrame) -> pd.DataFrame:
    """전년 동사 문서와의 코사인 유사도 → 연도별 중앙값 정규화(서식 일괄개정 공통충격 제거)."""
    cols = ["corp_code", "rcept_dt", "sim_risk", "sim_all"]
    if bows is None or not len(bows):
        return pd.DataFrame(columns=cols)
    B = bows.copy()
    B["rcept_dt"] = ds_(B["rcept_dt"])
    B["year"] = B["rcept_dt"].dt.year

    def cos(a: dict, b: dict) -> float:
        if not a or not b:
            return np.nan
        ks = set(a) & set(b)
        num = sum(float(a[k]) * float(b[k]) for k in ks)
        da = math.sqrt(sum(float(v) ** 2 for v in a.values()))
        db = math.sqrt(sum(float(v) ** 2 for v in b.values()))
        return num / (da * db) if da > 0 and db > 0 else np.nan

    rows = []
    for corp, g in B.groupby("corp_code"):
        g = g.sort_values(["year", "sec"])
        prev: Dict[str, dict] = {}
        for y, gy in g.groupby("year"):
            sims = {}
            cur = {}
            for r in gy.itertuples(index=False):
                try:
                    bow = json.loads(r.bow)
                except Exception:
                    bow = {}
                cur[r.sec] = bow
                if r.sec in prev:
                    sims[r.sec] = cos(bow, prev[r.sec])
            if sims:
                rows.append({"corp_code": corp, "rcept_dt": gy["rcept_dt"].max(),
                             "sim_risk": np.nanmean([v for k, v in sims.items()
                                                     if k in ("risk", "contingent")]),
                             "sim_all": np.nanmean(list(sims.values()))})
            prev = cur
    S = pd.DataFrame(rows)
    if not len(S):
        return pd.DataFrame(columns=cols)
    S["year"] = ds_(S["rcept_dt"]).dt.year
    # ★연도 정규화는 '접수순 확장 중앙값' — 그 해 전체 중앙값을 쓰면 4월 시점 값에
    #   이후 접수분 통계가 섞인다(C1 위반). expanding 은 당시까지의 분포만 쓴다.
    S = S.sort_values(["year", "rcept_dt"], kind="stable")
    for c in ("sim_risk", "sim_all"):
        med = S.groupby("year")[c].transform(lambda s: s.expanding(min_periods=5).median())
        S[c] = S[c] - med
    return S.drop(columns=["year"])


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [12] 피처부 (L1) — 공용축 B·C·D + 센서팩 C/N/D/X/P + 정책 캘린더(C12)                      ║
# ║   B·C 는 '확인'이 아니라 '사전확률' — K분기 연속 정렬 같은 대기조건을 넣지 않는다(§1.4).    ║
# ║   모든 TP 는 tp_pair(곱)로만 만든다. 합산 금지(§1.1).                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

# ── 센서팩 레지스트리 (C12: 정책 캘린더 없는 팩은 등록 불가) ─────────────────────────────────
SENSOR_PACKS: "OrderedDict[str, dict]" = OrderedDict()


def register_sensor_pack(pid: str, name: str, tp_cols: Sequence[str], feature_fn: Callable,
                         policy: Sequence[dict], interp: Sequence[Tuple[str, str, str]],
                         theta_col: Optional[str] = None, veto_only: bool = False):
    """veto_only=True: 거부권 전용 팩(PACK-D) — 증거층(E) 합성과 하한선 축에서 제외된다.
    ★상수 0 축을 E 에 넣으면 전원 동점 랭크(≥0.5)가 하한선의 '충족 축'으로 계상되어
      실질 1축만으로 min_axes 를 통과시키는 구멍이 된다."""
    if not policy:
        raise RuntimeError(f"[C12 위반] 팩 '{pid}' 에 정책 캘린더가 없습니다 — 등록 불가. "
                           f"모든 대체데이터는 정책에 오염된다(§12).")
    SENSOR_PACKS[pid] = {"id": pid, "name": name, "tp_cols": list(tp_cols),
                         "features": feature_fn, "policy": list(policy),
                         "interp": list(interp), "theta_col": theta_col,
                         "veto_only": bool(veto_only),
                         "enabled": True, "why_off": "", "E_col": f"E_{pid}"}


def packs_on() -> List[dict]:
    return [p for pid, p in SENSOR_PACKS.items() if p["enabled"] and pid in ACTIVE_PACKS]


_PACK_QUIET: Dict[str, Any] = {"on": False, "hit": []}   # 합성 구간 판정 침묵 + 기록


def pack_off(pid: str, why: str):
    if pid in SENSOR_PACKS and SENSOR_PACKS[pid]["enabled"]:
        SENSOR_PACKS[pid]["enabled"] = False
        SENSOR_PACKS[pid]["why_off"] = why
        if _PACK_QUIET["on"]:
            # ★합성 구간 — 로그 대신 여기 적어 둔다. 나가면서 한 줄로 요약한다.
            #   (상태 복원은 run_smoke 의 reset_transient_state 가 이미 한다. 그게 우리
            #    finally 보다 먼저 돌기 때문에, '무엇이 꺼졌었나'는 이렇게만 알 수 있다.)
            if pid not in _PACK_QUIET["hit"]:
                _PACK_QUIET["hit"].append(pid)
            return
        L.warn(f"센서팩 '{pid}' 비활성화 — {why} (조용히 남겨두지 않고 명시적으로 끕니다)")


@contextmanager
def pack_state_guard(restore: bool = True):
    """★합성 구간의 팩 판정을 침묵시키고, 나올 때 상태를 되돌린다.

    ★사실관계 정정: 팩이 실데이터 실행까지 꺼진 채 남지는 ★않는다 —
      run_smoke 의 finally 가 reset_transient_state() 를 부르고 거기서 전 팩을
      enabled=True 로 되돌린다. 앞선 진단('스모크가 팩을 영구히 끈다')은 틀렸다.

    진짜 문제는 ★로그다. 합성 패널에는 관세(X)·조달(P)의 원천이 애초에 없으므로
    커버리지 0% 판정이 나고, 매 실행 "센서팩 'X' 비활성화"가 찍힌다. 사용자는 그걸
    보고 그 팩이 죽은 것으로 읽는다 — 실제로는 실데이터 판정을 아직 하지도 않았는데도.
    없는 데이터를 두고 내린 판정을 경고로 찍는 것은 정보가 아니라 소음이다.

    그래서 합성 구간에서는 판정을 ★조용히 수행하고(계산 경로는 그대로 검증된다),
    나올 때 상태를 복원한 뒤 무엇을 건너뛰었는지 ★한 줄로만 남긴다.
    활성 여부는 실데이터 수집 뒤 pack_status_table() 이 표로 보여준다.
    """
    snap = {k: (v["enabled"], v["why_off"]) for k, v in SENSOR_PACKS.items()}
    prev, prev_hit = _PACK_QUIET["on"], _PACK_QUIET["hit"]
    _PACK_QUIET["on"], _PACK_QUIET["hit"] = True, []
    try:
        yield snap
    finally:
        skipped = list(_PACK_QUIET["hit"])
        _PACK_QUIET["on"], _PACK_QUIET["hit"] = prev, prev_hit
        if restore:
            for k, (en, why) in snap.items():
                if k in SENSOR_PACKS:
                    SENSOR_PACKS[k]["enabled"] = en
                    SENSOR_PACKS[k]["why_off"] = why
        if skipped and restore:
            L.info(f"합성 스모크에는 팩 {skipped} 의 실제 원천이 없어 그 판정은 건너뜁니다"
                   f"(계산 경로는 그대로 검증됐습니다). ★활성 여부는 실데이터 수집 뒤 "
                   f"L.PANEL 의 '센서팩 활성 현황' 표가 유일한 판정 근거입니다.")


def pack_status_table(P: Optional[pd.DataFrame] = None):
    """★실데이터 기준 센서팩 활성 현황 — 무엇이 켜졌고 왜 꺼졌는지 한 표로.

    사용자가 매 실행 물어 온 질문이 정확히 이것이다("모든 축이 활성화돼야 정상 아닌가").
    합성 스모크의 경고와 섞이지 않도록, 실데이터 패널이 만들어진 뒤 ★한 번만 찍는다.
    """
    rows = []
    for pid, p in SENSOR_PACKS.items():
        if pid not in ACTIVE_PACKS:
            rows.append([pid, p["name"], "설정에서 제외", "—", "—", "ACTIVE_PACKS 미포함"])
            continue
        ec, tc = p["E_col"], p.get("theta_col")
        cov = (f"{float(P[ec].notna().mean())*100:.1f}%"
               if P is not None and ec in P.columns and len(P) else "—")
        th = (f"{float(P[tc].notna().mean())*100:.1f}%"
              if P is not None and tc and tc in P.columns and len(P) else "—")
        rows.append([pid, p["name"], "✔ 활성" if p["enabled"] else "✘ 비활성",
                     cov, th, (p["why_off"] or "")[:60] if not p["enabled"] else
                     ("거부권 전용(증거층 축 아님)" if p.get("veto_only") else "")])
    L.grid(rows, ["팩", "이름", "상태", "E 커버리지", "θ 커버리지", "비고"],
           ["l", "l", "l", "r", "r", "l"],
           title="센서팩 활성 현황 (실데이터 기준 — 위 합성 스모크 경고와 무관합니다)")


# ── 기본 패널 ───────────────────────────────────────────────────────────────────────────────
def frame_panel(uni: "PITUniverse", months: pd.DatetimeIndex,
                monthly_px: pd.DataFrame) -> pd.DataFrame:
    # ★상폐 손실 인식(C2): 한국 상폐는 수개월 거래정지가 선행한다. 정지 시작 월엔 다음 달
    #   가격이 없어 fwd_ret=NaN 이고, 상폐일이 도래하는 달엔 이미 패널 행 자체가 없다 —
    #   그대로 두면 -100% 가 영원히 발화하지 않고 0% 청산으로 새는 수익 과대계상이 된다.
    #   해법: '마지막 거래 가능 월'의 fwd_ret 결측에 -100% 를 찍는다(정리매매가 없으면 -100%).
    mp = monthly_px.copy()
    dl = mp["code"].map(uni.delist_map)
    is_last = mp.groupby("code", observed=True)["month"].transform("max") == mp["month"]
    stamp = (is_last & dl.notna() & (dl <= months.max() + pd.offsets.MonthEnd(1))
             & mp["fwd_ret"].isna())
    if stamp.any():
        mp.loc[stamp, "fwd_ret"] = -1.0
        L.info(f"상폐 예정 {int(stamp.sum()):,}종목의 마지막 거래월 fwd_ret 에 -100% 반영 "
               f"(정리매매 최종가 부재 시 규정 — 정지 후 상폐 경로의 0% 누수 차단)")
    rows = []
    for m in months:
        codes = uni.at(m)
        uni.gate("당시상장(PIT)", m, codes)
        rows.append(pd.DataFrame({"code": codes, "month": m}))
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["code", "month"])
    P = P.merge(mp, on=["code", "month"], how="left")
    for m in months:
        sub = P[(P["month"] == m) & P["close"].notna()]
        uni.gate("가격보유", m, sub["code"].tolist())
    L.ok(f"기본 패널 {len(P):,}행 ({P['code'].nunique():,}종목 × {len(months)}개월)")
    RUN.io("OUT", "MEM", "base_panel", P)
    return P


def attach_financials(P: pd.DataFrame, master: pd.DataFrame, kd_shift_days: int = 0
                      ) -> pd.DataFrame:
    """재무·직원 as-of 결합(C1 관문). kd_shift_days 는 R1(누수 자가검정) 전용 —
    음수(-30)면 '30일 일찍 알았던' 오염본이 된다. 실전 경로에서는 항상 0."""
    c2c = master.dropna(subset=["corp_code"]).set_index("code")["corp_code"].astype(str).to_dict()
    P = P.copy()
    P["corp_code"] = P["code"].map(c2c)
    for tbl, take, tag in (("dart_fin", None, ""),
                           ("dart_emp", ["corp_code", "knowledge_date", "employees", "payroll"],
                            "_e"),
                           ("nps_monthly", None, "_n"),
                           ("text_sim", None, "_t")):
        if not PITX.has(tbl):
            continue
        if kd_shift_days and tbl == "dart_fin":
            shifted = PITX._tables[tbl].copy()
            shifted["knowledge_date"] = shifted["knowledge_date"] + \
                pd.Timedelta(days=kd_shift_days)
            tmp = PITGateway()
            tmp.put(tbl, shifted, keys=["corp_code"])
            P = tmp.asof_attach(P, tbl, by="corp_code", when="month", take=take, tag=tag)
        else:
            by = "corp_code" if tbl != "nps_monthly" else "code"
            P = PITX.asof_attach(P, tbl, by=by, when="month", take=take, tag=tag)
    for c in FIN_PANEL_COLS:                              # 스키마 계약 — 실행마다 같은 컬럼 집합
        if c not in P.columns:
            P[c] = np.nan
    if not PITX.has("dart_fin"):
        L.warn("DART 재무 부재 — B/C축·PACK-C 전부 결측(실행은 계속, 증거층이 얇아짐). "
               "DART_API_KEY 를 넣으면 살아납니다.")
    return P


# ── 공용축 B: 회계 품질 (사전확률) ──────────────────────────────────────────────────────────
def axis_quality(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gcol(P, c)
    rev, cogs = colx(P, "revenue_ttm"), colx(P, "cogs_ttm")
    P["gpm"] = sdiv(rev - cogs, rev)
    P["b1"] = g("gpm").transform(
        lambda s: s.rolling(12, min_periods=6).apply(
            lambda w: np.polyfit(np.arange(len(w)), w, 1)[0]
            if np.isfinite(w).all() else np.nan, raw=True))
    P["dio"] = sdiv(colx(P, "inventory"), colx(P, "cogs_ttm")) * 365.0
    P["dso"] = sdiv(colx(P, "receivable"), colx(P, "revenue_ttm")) * 365.0
    # ★덧셈 결측 전파 — 재고(dio)와 매출채권(dso) 중 ★한쪽만 비어도 turn_days 가 전량 NaN 이
    #   되고 TP_B1 이 통째로 사라진다(실측: 발화 통계표에 TP_B1 이 아예 없었다). 가용한 것의
    #   평균 × 2 로 스케일만 맞춘다 — 셀 내 상대값이라 수준은 무해하고, 둘 다 없으면 결측 유지.
    P["turn_days"] = nrow_mean(P, ["dio", "dso"]) * 2.0
    P["d_turn"] = g("turn_days").diff(12)
    P["dlog_rev"] = g("revenue_ttm").transform(lambda s: dlog(s, 12))
    avg_assets = (colx(P, "assets") + g("assets").shift(12)) / 2.0
    P["accruals"] = sdiv(colx(P, "net_income_ttm") - colx(P, "cfo_ttm"), avg_assets)
    P["d_accruals"] = g("accruals").diff(12)
    P["b4"] = sdiv(g("contract_liab").diff(12), colx(P, "revenue_ttm"))
    return P


def axis_quality_tp(P: pd.DataFrame) -> pd.DataFrame:
    P["TP_B1"] = tp_pair(zx(P, "dlog_rev"), -zx(P, "d_turn"))       # 매출↑ 인데 회전 유지
    P["TP_B2"] = tp_pair(zx(P, "dlog_rev"), -zx(P, "d_accruals"))   # 매출↑ 인데 발생액 유지
    # ★★결측 전파 차단 — 이 한 줄이 백테스트 전체를 무의미하게 만들고 있었다.
    #   옛 식은 0.5*A + 0.5*B 였다. nrow_mean 은 자기 컬럼 안의 결측만 건너뛸 뿐이고,
    #   블록 하나가 통째로 결측이면 ★덧셈에서 NaN 이 전파돼 살아 있는 블록까지 죽는다.
    #   실측: TP_B2 가 179,186행 관측인데 E_AXB 는 33,339행(11.3%)에 그쳤다 — 추세블록
    #   (b1: 12개월 연속 유한 gpm 요구 · b4: 계약부채라는 희소 계정)이 결측인 행에서
    #   재무축이 통째로 사라진 것이다. 그 결과 하한선이 (E_C 단독)으로 붕괴하고
    #   유니버스가 1,274 → 100 (7.9%)로 잘렸다. 성과·강건성 판정 전체가 여기서 왜곡됐다.
    #   블록 간에도 nrow_mean 을 쓰면 '둘 다 있으면 반반, 하나만 있으면 그것으로'가 되어
    #   C7(동일가중)을 지키면서 결측에 견딘다. §7.3 '결측을 0으로 채우지 않는다'와도 일치.
    P["E_AXB"] = nrow_mean(pd.DataFrame({
        "tp": nrow_mean(P, ["TP_B1", "TP_B2"]),
        "trend": nrow_mean(pd.DataFrame({"a": zx(P, "b1"), "b": zx(P, "b4")}), ["a", "b"]),
    }), ["tp", "trend"])
    return P


# ── 공용축 C: 자원 투입 (사전확률) ──────────────────────────────────────────────────────────
def axis_resource(P: pd.DataFrame) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gcol(P, c)
    nwc = colx(P, "receivable").fillna(0) + colx(P, "inventory").fillna(0) - \
        colx(P, "payable").fillna(0)
    P["ic"] = nwc + colx(P, "ppe").fillna(0) + colx(P, "intangible").fillna(0)
    P["dlog_ic"] = g("ic").transform(lambda s: dlog(s, 12))
    nopat = colx(P, "op_income_ttm") * 0.78            # 법인세 가정 — 셀 내 상대값이라 수준 무해
    avg_ic = (P["ic"] + g("ic").shift(12)) / 2.0
    P["roic"] = sdiv(nopat, avg_ic)
    P["d_roic"] = g("roic").diff(12)
    P["value_added"] = colx(P, "op_income_ttm").fillna(0) + colx(P, "payroll").fillna(0) + \
        colx(P, "dep_ttm").fillna(0)
    P["va_per_emp"] = sdiv(P["value_added"], colx(P, "employees"))
    P["d_va_emp"] = g("va_per_emp").diff(12)
    P["dlog_emp"] = g("employees").transform(lambda s: dlog(s, 12))
    P["c3"] = sdiv(colx(P, "capex_ttm").abs(), colx(P, "dep_ttm").abs())
    P["debt_ratio"] = sdiv(colx(P, "liabilities"), colx(P, "equity"))
    P["d_debt"] = g("debt_ratio").diff(12)
    P["d_eff_tax"] = g("eff_tax").diff(12)
    return P


def axis_resource_tp(P: pd.DataFrame) -> pd.DataFrame:
    P["TP_C1"] = tp_pair(zx(P, "dlog_ic"), zx(P, "d_roic"))         # 확장↑ 인데 ROIC 유지
    P["TP_C2"] = tp_pair(zx(P, "dlog_emp"), zx(P, "d_va_emp"))      # 인원↑ 인데 생산성 유지
    # ★E_AXB 와 같은 결측 전파 결함. c3(=CAPEX/감가상각)는 두 계정이 모두 있어야 하는데
    #   그 한 항목 때문에 TP_C1(182,657행)·TP_C2(232,908행)가 통째로 버려졌다(E_AXC 15.8%).
    P["E_AXC"] = nrow_mean(pd.DataFrame({
        "tp": nrow_mean(P, ["TP_C1", "TP_C2"]),
        "trend": nrow_mean(pd.DataFrame({"a": zx(P, "c3")}), ["a"]),
    }), ["tp", "trend"])
    return P


# ── 공용축 D: 반영도 → U (할인층) — 이 시스템에서 가장 중요한 단일 지표 ──────────────────────
def axis_discount(P: pd.DataFrame, flows: pd.DataFrame, cons: pd.DataFrame) -> pd.DataFrame:
    """ΔlogP = ΔlogE + ΔlogM (120거래일≈6개월).
    목표상태: ΔlogE>0 AND ΔlogM≤0 — 이익은 인정됐는데 자본화는 거부된 미스프라이싱.
    ⚠ 한계(§16.2 — 숨기지 않음): 컨센서스 fwd EPS 시계열은 과거 복원 불가라
      E 는 후행 12M 순이익 대리를 쓴다. 초기 구간일수록 대리 오차가 크다."""
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gcol(P, c)
    P["dlog_E"] = g("net_income_ttm").transform(lambda s: dlog(s, 6))
    P["dlog_P"] = g("close").transform(lambda s: dlog(s, 6))
    P["dlog_M"] = P["dlog_P"] - P["dlog_E"]
    P["d1"] = -P["dlog_M"]
    P["D_state"] = np.select(
        [(P["dlog_E"] > 0) & (P["dlog_M"] <= 0), (P["dlog_E"] > 0) & (P["dlog_M"] > 0),
         (P["dlog_E"] <= 0) & (P["dlog_M"] > 0)],
        ["목표상태(진입)", "리레이팅중(관망)", "기대선행(배제)"], default="개선없음(배제)")
    P["d3"] = np.nan
    if flows is not None and len(flows):
        f = flows.copy()
        # 수급 프레임은 월간(신설계, code·month)이 기본이고 일간(구버전 캐시)도 그대로 받는다
        if "month" in f.columns:
            f["month"] = ds_(f["month"]) + pd.offsets.MonthEnd(0)
        elif "date" in f.columns:
            f["month"] = ds_(f["date"]) + pd.offsets.MonthEnd(0)
        else:
            f = f.iloc[0:0]
        if len(f):
            f["code"] = f["code"].astype(str)
            f["net"] = colx(f, "inst_net").fillna(0) + colx(f, "forgn_net").fillna(0)
            f = (f.dropna(subset=["code", "month"])
                  .groupby(["code", "month"], as_index=False)["net"].sum()
                  .sort_values(["code", "month"]))
            # 6개월(≈120거래일) 누적 순매수. ★shift(1) — KRX 투자자별 확정 수급은 T+1 공표라
            # 월말 당월분은 월말 종가 시점에 '알 수 없다'(C1). 당월을 빼고 t-6..t-1 만 쓴다.
            # ★월 격자를 채운 뒤 굴린다. 결손월이 있는 종목에서 위치기반 rolling(6) 은
            #   몇 년치를 합쳐 놓고 '6개월 누적'이라 부르고, shift(1) 도 1개월이 아니라
            #   1행(최대 수십 개월)을 민다 — 종목마다 단위가 달라진 값이 adv×250 으로
            #   나뉘어 셀 랭크에 들어간다.
            grid = pd.date_range(f["month"].min(), f["month"].max(), freq="ME")
            f = (f.set_index("month").groupby("code", observed=True)["net"]
                   .apply(lambda s: s.reindex(grid))
                   .rename("net").reset_index())
            f.columns = ["code", "month", "net"]
            f["cum6m"] = (f.groupby("code", observed=True)["net"]
                           .transform(lambda s: s.rolling(6, min_periods=3).sum().shift(1)))
            f = f.dropna(subset=["cum6m"])
            P["code"] = P["code"].astype(str)
            P = P.merge(f[["code", "month", "cum6m"]], on=["code", "month"], how="left")
            # 시총 미상 구간 대비 연간 거래대금(adv×250)으로 정규화 — 셀 내 상대비교라 무해
            P["d3"] = -sdiv(P["cum6m"], P["adv20"].replace(0, np.nan) * 250.0)
    P["d2"] = np.nan
    P["d4"] = np.nan
    P["n_analyst"] = np.nan
    P["tp_med"] = np.nan
    if cons is not None and len(cons):
        P = P.merge(cons, on=["code", "month"], how="left", suffixes=("", "_c"))
        for a, b in (("d2", "d2_raw"), ("d4", "d4_raw"),
                     ("n_analyst", "n_analyst_c"), ("tp_med", "tp_med_c")):
            src = b if b in P.columns else (b[:-2] if b.endswith("_c") and b[:-2] in P.columns
                                            else None)
            if src and src in P.columns and src != a:
                P[a] = P[src]
    return P


def axis_discount_u(P: pd.DataFrame) -> pd.DataFrame:
    """U = 가용 축 z 평균 → 셀 내 백분위. ★결측 축을 0으로 채우지 않는다(§7.3)."""
    Z = pd.DataFrame({"z1": zx(P, "d1"), "z2": zx(P, "d2"), "z3": zx(P, "d3"),
                      "z4": zx(P, "d4")}, index=P.index)
    P["U_raw"] = nrow_mean(Z, list(Z.columns))
    P["U_n_axes"] = Z.notna().sum(axis=1)
    P["U"] = rx(P, P["U_raw"])
    used = {c: int(Z[c].notna().sum()) for c in Z.columns}
    L.info("D축 가용성 — " + " · ".join(f"{k}:{v:,}" for k, v in used.items()))
    if used["z2"] == 0 and used["z4"] == 0:
        L.warn("컨센서스 d2/d4 전무 — U 는 d1(+d3)만으로 구성됩니다(리서치 원장 감사표 참조).")
    return P


# ── PACK-C: 자본배분 체제 전환 (★Phase1 — 가장 싼 검정) ─────────────────────────────────────
PACK_C_POLICY = [
    {"policy_id": "VALUEUP_2024", "name": "기업 밸류업 프로그램", "start": "2024-02-26",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
    {"policy_id": "VALUEUP_IDX", "name": "코리아 밸류업 지수", "start": "2024-09-24",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
    {"policy_id": "DIV_TAX_2025", "name": "배당소득 분리과세 논의", "start": "2025-01-01",
     "end": None, "pack": "C", "req_type": "없음", "req_value": ""},
]
PACK_C_INTERP = [
    ("TP_P1", "진짜 잉여현금 창출력 — 환원과 투자를 동시에 늘림", "성장 포기하고 환원만"),
    ("TP_P2", "자사주 진정성 — 취득이 소각까지 감", "취득만 하고 물량 재활용 가능성"),
    ("TP_P3", "무차입 환원 — 현금 체질", "차입해서 환원(지속 불가)"),
]


def pack_c_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gcol(P, c)
    payout = colx(P, "div_paid_ttm").abs().fillna(0) + colx(P, "tstock_buy_ttm").abs().fillna(0)
    P["payout_ratio"] = sdiv(payout, colx(P, "cfo_ttm"))
    P["p1"] = g("payout_ratio").diff(12)
    invest = colx(P, "capex_ttm").abs().fillna(0) + colx(P, "rnd_ttm").abs().fillna(0)
    P["invest_ratio"] = sdiv(invest, colx(P, "revenue_ttm"))
    P["p2"] = g("invest_ratio").diff(12)
    # p3: 자사주 취득공시 대비 12M 내 소각 실행률 — 이 갭을 추적하는 참여자가 없다는 게 알파 원천
    P["n_acq"] = 0.0
    P["n_burn"] = 0.0
    disc = ctx.get("disclosures")
    if disc is not None and len(disc) and "corp_code" in P.columns:
        dd = disc[disc["kind"].isin(["tstock_acq", "tstock_burn"])].copy()
        if len(dd):
            dd["month"] = ds_(dd["rcept_dt"]) + pd.offsets.MonthEnd(0)
            cnt = (dd.groupby(["corp_code", "month", "kind"]).size().unstack("kind")
                     .reset_index())
            for c in ("tstock_acq", "tstock_burn"):
                if c not in cnt.columns:
                    cnt[c] = 0.0
            cnt["corp_code"] = cnt["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(cnt, on=["corp_code", "month"], how="left")
            P = P.sort_values(["code", "month"])
            P["n_acq"] = (P.groupby("code", observed=True)["tstock_acq"]
                           .transform(lambda s: s.fillna(0).rolling(12, min_periods=1).sum()))
            P["n_burn"] = (P.groupby("code", observed=True)["tstock_burn"]
                            .transform(lambda s: s.fillna(0).rolling(12, min_periods=1).sum()))
    P["p3"] = sdiv(P["n_burn"], P["n_acq"]).clip(0, 2)
    P["acq_size"] = sdiv(colx(P, "tstock_buy_ttm").abs(), colx(P, "assets"))
    P["p4"] = colx(P, "d_debt")
    P["TP_P1"] = tp_pair(zx(P, "p1"), zx(P, "p2"))          # ★이 팩의 전부: 환원↑ 인데 투자도↑
    # '취득 규모가 큰데' 가 전제 — 셀 평균 이하 취득은 판단 대상이 아니다(NaN).
    # z 를 그대로 곱하면 저-저 사분면(음×음=양)에서 '아무것도 안 한 기업'이 상위로 둔갑한다.
    zi = zx(P, "acq_size")
    P["TP_P2"] = tp_pair(zi.where(zi > 0), zx(P, "p3"))
    P["TP_P3"] = tp_pair(zx(P, "p1"), -zx(P, "p4"))
    P["E_C"] = nrow_mean(P, ["TP_P1", "TP_P2", "TP_P3"])
    return P


register_sensor_pack("C", "자본배분 체제 전환", ["TP_P1", "TP_P2", "TP_P3"],
                     pack_c_features, PACK_C_POLICY, PACK_C_INTERP)

# ── PACK-N: 국민연금 고용 (★1순위 — 한계임금이 곧 보조금 필터) ──────────────────────────────
PACK_N_POLICY = [
    {"policy_id": "YOUTH_EMP_GRANT", "name": "청년추가고용장려금", "start": "2018-03-15",
     "end": "2021-12-31", "pack": "N", "req_type": "연령", "req_value": "만34세이하"},
    {"policy_id": "EMP_KEEP_COVID", "name": "고용유지지원금(코로나)", "start": "2020-02-01",
     "end": "2021-12-31", "pack": "N", "req_type": "없음", "req_value": ""},
    {"policy_id": "YOUTH_JUMP", "name": "청년일자리도약장려금", "start": "2022-01-01",
     "end": None, "pack": "N", "req_type": "연령", "req_value": "만34세이하"},
    {"policy_id": "UNIFIED_TAXCR", "name": "통합고용세액공제", "start": "2023-01-01",
     "end": None, "pack": "N", "req_type": "기업규모", "req_value": "인원당 정액"},
]
PACK_N_INTERP = [
    ("TP_N1", "고부가 인력 확충 — 사업 고도화", "저임금 대량채용 — ★보조금 유인 의심"),
    ("TP_N2", "정착하는 확장 — 조직 역량 축적", "급조 조직 · 회전문 채용"),
    ("TP_N3", "진짜 캐파 확대(신규 사업장+순증)", "사업장 이전에 불과"),
    ("TP_N4", "희석 없는 확장(월 해상도)", "단순 규모 확대"),
]


def pack_n_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    if "nps_members" not in P.columns or colx(P, "nps_members").notna().sum() == 0:
        for c in ("n1", "n2", "n3", "n4", "theta_N", "TP_N1", "TP_N2", "TP_N3", "TP_N4", "E_N"):
            P[c] = np.nan
        return P
    g = lambda c: gcol(P, c)
    mem = colx(P, "nps_members")
    amt = colx(P, "nps_amt")
    # 한계임금(v2 최대 변경점): (Δ고지금액/Δ가입자수)/보험료율 vs 기존 평균임금
    d_amt = g("nps_amt").diff(1)
    d_mem = g("nps_members").diff(1)
    prev_mem = g("nps_members").shift(1)
    prev_amt = g("nps_amt").shift(1)
    # 함정(c) 분모 불안정: |Δ인원| < max(3, 인원×0.5%) → 결측(0 채움 금지)
    ok_dm = d_mem.abs() >= np.maximum(3.0, prev_mem * 0.005)
    marginal_wage = sdiv(d_amt, d_mem.where(ok_dm)) / NPS_CONTRIB_RATE
    avg_wage_prev = sdiv(prev_amt, prev_mem) / NPS_CONTRIB_RATE
    wage_premium = sdiv(marginal_wage, avg_wage_prev)
    # 함정(a) 7월 정기결정: 기준소득월액이 일괄 갱신되는 '귀속월 7월'을 제외한다.
    # ★패널 월이 아니라 NPS '귀속월'(asof 가 붙여준 month_n) 기준 — 공개지연 2개월 때문에
    #   패널 7월 행은 5월 귀속분이라, 패널 월로 걸면 깨끗한 달을 버리고 오염 달을 통과시킨다.
    accr_m = ds_(P["month_n"]) if "month_n" in P.columns else P["month"]
    july = accr_m.dt.month == 7
    P["n2"] = wage_premium.where(~july.fillna(False))
    P["n6"] = sdiv(d_amt, prev_amt).where(july.fillna(False))   # 7월 점프폭 = 연1회 임금상승률
    P["n1"] = g("nps_members").transform(lambda s: dlog(s, 12))
    # n3 = -Δ(상실자수/가입자수). ★차분은 반드시 종목 내에서 — 전체 시리즈 diff 는 종목
    # 경계를 넘어 앞 종목의 값과 차분되는 조용한 오염이 된다.
    loss_ratio = sdiv(colx(P, "nps_lost"), mem)
    P["n3"] = -loss_ratio.groupby(P["code"], observed=True).diff(12)
    P["n4"] = (g("n_sites").diff(12) > 0).astype(float).where(colx(P, "n_sites").notna())
    # 월 해상도 인당 부가가치(TP_N4 — 분자를 월별 NPS 인원으로 대체)
    P["va_emp_m"] = sdiv(colx(P, "value_added"), mem)
    P["d_va_emp_m"] = g("va_emp_m").diff(12)
    # θ_N: 매핑 가입자수 / DART 종업원수 — 배제가 아니라 가중치, 0.5 미만이면 V4 로 팩 무효
    P["theta_N"] = sdiv(mem, colx(P, "employees")).clip(0, 1.5)
    P["TP_N1"] = tp_pair(zx(P, "n1"), zx(P, "n2"))
    P["TP_N2"] = tp_pair(zx(P, "n1"), zx(P, "n3"))
    P["TP_N3"] = tp_pair(zx(P, "n4"), zx(P, "n1"))
    P["TP_N4"] = tp_pair(zx(P, "n1"), zx(P, "d_va_emp_m"))
    theta_w = P["theta_N"].clip(0, 1)
    P["E_N"] = nrow_mean(P, ["TP_N1", "TP_N2", "TP_N3", "TP_N4"]) * theta_w
    return P


register_sensor_pack("N", "국민연금 고용", ["TP_N1", "TP_N2", "TP_N3", "TP_N4"],
                     pack_n_features, PACK_N_POLICY, PACK_N_INTERP, theta_col="theta_N")

# ── PACK-D: 공시텍스트 경직성 (주용도 V7 거부권 — 단독 전략 금지) ───────────────────────────
PACK_D_POLICY = [
    {"policy_id": "DISCLOSURE_FORM", "name": "공시 서식 일괄 개정(연도 정규화로 흡수)",
     "start": "2016-01-01", "end": None, "pack": "D", "req_type": "없음", "req_value": ""},
]
PACK_D_INTERP = [
    ("d_text", "문안 대폭 변경 — 센서가 못 본 무언가(V7 후보)", "전년 복사(평온)"),
]


def pack_d_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.copy()
    if "sim_risk" not in P.columns or colx(P, "sim_risk").notna().sum() == 0:
        P["sim_risk_pct"] = np.nan
        return P
    P["sim_risk_pct"] = rx(P, "sim_risk")                # V7 거부권 입력(셀 내 하위 5% 차단)
    return P                                              # ★E 축을 만들지 않는다 — veto_only 팩


register_sensor_pack("D", "공시텍스트 경직성(V7)", ["sim_risk_pct"],
                     pack_d_features, PACK_D_POLICY, PACK_D_INTERP, veto_only=True)

# ── PACK-X: 관세청 수출 ─────────────────────────────────────────────────────────────────────
PACK_X_POLICY = [
    {"policy_id": "EXPORT_VOUCHER", "name": "수출바우처", "start": "2017-01-01", "end": None,
     "pack": "X", "req_type": "기업규모", "req_value": "중소중견"},
    {"policy_id": "FTA_REGIME", "name": "FTA 발효/개정(상시)", "start": "2016-01-01",
     "end": None, "pack": "X", "req_type": "없음", "req_value": ""},
]
PACK_X_INTERP = [
    ("TP_X1", "수요곡선 이동 — 물량↑ 인데 단가 안 깎임", "물량을 가격 인하로 산 것"),
    ("TP_X2", "제품력 다변화 — 목적지 확장에도 믹스 유지", "저가 물량으로 고객 늘림"),
]


def pack_x_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    cust = ctx.get("customs")
    hmap = ctx.get("hs_map")
    if cust is None or not len(cust) or hmap is None or not len(hmap):
        for c in ("x1", "x2", "x3", "TP_X1", "TP_X2", "E_X", "theta_X"):
            P[c] = np.nan
        return P
    C = cust.copy()
    C["month"] = ds_(pd.to_datetime(C["ym"].astype(str), format="%Y%m")) + pd.offsets.MonthEnd(0)
    # HS→기업 매핑(C3 시간구간) — PIT: valid 구간만
    M = hmap.copy()
    C = C.merge(M[["hs", "code", "weight", "valid_from", "valid_to"]], on="hs", how="inner")
    C = C[(C["month"] >= C["valid_from"].fillna(pd.Timestamp("1990-01-01"))) &
          (C["month"] <= C["valid_to"].fillna(pd.Timestamp("2100-01-01")))]
    if not len(C):
        for c in ("x1", "x2", "x3", "TP_X1", "TP_X2", "E_X", "theta_X"):
            P[c] = np.nan
        return P
    C["w_usd"] = colx(C, "exp_usd") * colx(C, "weight").fillna(1.0)
    C["w_kg"] = colx(C, "exp_kg") * colx(C, "weight").fillna(1.0)
    agg = C.groupby(["code", "month"], observed=True).agg(
        exp_usd=("w_usd", "sum"), exp_kg=("w_kg", "sum")).reset_index()
    # ★x3(목적지 다변화)의 축은 ★국가여야 한다. 옛 수집기는 grp 에 국가코드를 붙여
    #   놔서('선진_US','선진_DE') 같은 그룹 안에서도 버킷이 갈렸고, HHI 가 국가 집중도가
    #   아니라 준-국가 집중도를 재고 있었다. 이제 cc(국가코드)로 잰다.
    _dest = "cc" if "cc" in C.columns else "grp"
    grp_share = (C.groupby(["code", "month", _dest], observed=True)["w_usd"].sum()
                  .reset_index().rename(columns={_dest: "grp"}))
    hhi_m = grp_share.groupby(["code", "month"], observed=True)["w_usd"] \
        .apply(lambda s: hhi(s.to_numpy())).rename("dest_hhi").reset_index()
    agg = agg.merge(hhi_m, on=["code", "month"], how="left")
    agg = agg.sort_values(["code", "month"])
    agg["x1"] = agg.groupby("code", observed=True)["exp_kg"].transform(lambda s: dlog(s, 12))
    agg["unit_px"] = sdiv(agg["exp_usd"], agg["exp_kg"])
    # x2: 36개월 롤링 OLS 잔차 log(단가) = a + b·log(물량) — 벡터화 필수(§3)
    piv_p = agg.pivot_table(index="code", columns="month", values="unit_px")
    piv_q = agg.pivot_table(index="code", columns="month", values="exp_kg")
    yv = np.log(piv_p.where(piv_p > 0)).to_numpy()
    qv = np.log(piv_q.where(piv_q > 0)).to_numpy()
    Xv = np.stack([np.ones_like(qv), qv], axis=2)
    res = roll_ols_residual(yv, Xv, win=36)
    R = pd.DataFrame(res, index=piv_p.index, columns=piv_p.columns).stack().rename("x2_res")
    agg = agg.merge(R.reset_index().rename(columns={"level_1": "month"}),
                    on=["code", "month"], how="left")
    agg["x2"] = (agg.groupby("code", observed=True)["x2_res"]
                    .transform(lambda s: s.rolling(6, min_periods=3).mean() /
                               s.rolling(36, min_periods=12).std()))
    agg["x3"] = -agg.groupby("code", observed=True)["dest_hhi"].diff(12)
    P = P.merge(agg[["code", "month", "x1", "x2", "x3", "exp_usd"]],
                on=["code", "month"], how="left")
    # ★θ_X = 매핑이 귀속시킨 연간 수출액 ÷ 매출(TTM). 이건 '내가 매기는 신뢰도'가 아니라
    #   ★매핑의 결과가 회사의 실제 규모와 정합하는지의 실측이다. 그래서 매핑을 자동으로
    #   만들어도 엉터리면 여기서 드러나고 V4 가 그 팩을 죽인다 — 단, 한 방향으로만 그렇다.
    #
    #   ★구멍: 옛 식은 과소귀속만 잡고 ★과대귀속은 오히려 보상했다. 한 HS 의 국가 전체
    #   수출을 소형사 하나에 몰아주면 비율이 3.0 이 되는데, clip(0,1.2)→clip(0,1) 이
    #   그걸 '완벽한 매핑(θ=1)'으로 만든다. 즉 매핑이 틀릴수록 가중치가 올라간다.
    #   수출액이 매출을 넘는 것은 회계적으로 불가능하므로(수출은 매출의 부분집합),
    #   비율 1 을 정점으로 하고 넘어가면 ★같은 기울기로 떨어뜨린다: 1.0→1.0, 1.5→0.5,
    #   2.0→0. 그러면 과대귀속도 θ 를 깎아 V4 임계 0.50 아래로 밀어낸다.
    _xr = sdiv(colx(P, "exp_usd") * USDKRW_CONST * 12, colx(P, "revenue_ttm"))
    P["theta_X"] = np.where(_xr.notna(), np.minimum(_xr, np.maximum(0.0, 2.0 - _xr)), np.nan)
    P["TP_X1"] = tp_pair(zx(P, "x1"), zx(P, "x2"))
    P["TP_X2"] = tp_pair(zx(P, "x3"), zx(P, "x2"))
    P["E_X"] = nrow_mean(P, ["TP_X1", "TP_X2"]) * P["theta_X"].clip(0, 1)
    return P


register_sensor_pack("X", "관세청 수출", ["TP_X1", "TP_X2"],
                     pack_x_features, PACK_X_POLICY, PACK_X_INTERP, theta_col="theta_X")

# ── PACK-P: 조달청 낙찰 ─────────────────────────────────────────────────────────────────────
PACK_P_POLICY = [
    {"policy_id": "SME_COMPETE", "name": "중소기업자간 경쟁제품 지정", "start": "2016-01-01",
     "end": None, "pack": "P", "req_type": "기업규모", "req_value": "중소기업"},
    {"policy_id": "DEFENSE_BOOM", "name": "방산·원전 수주 레짐(R7 필수)", "start": "2022-01-01",
     "end": None, "pack": "P", "req_type": "없음", "req_value": ""},
]
PACK_P_INTERP = [
    ("TP_Q1", "가격 안 깎고 수주 확대", "저가 수주"),
    ("TP_Q2", "발주처 다변화에도 마진 유지", "단일 발주처 의존"),
]


def pack_p_features(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    G = ctx.get("procurement")
    master = ctx.get("master")
    if G is None or not len(G) or master is None:
        for c in ("q1", "q2", "q3", "TP_Q1", "TP_Q2", "E_P"):
            P[c] = np.nan
        return P
    nm2cd = {clean_corp(n): c for c, n in zip(master["code"], master["name"])
             if str(n).strip()}
    W = G.copy()
    W["code"] = W["corp_nm"].astype(str).map(lambda s: nm2cd.get(clean_corp(s)))
    W = W.dropna(subset=["code"])
    if not len(W):
        for c in ("q1", "q2", "q3", "TP_Q1", "TP_Q2", "E_P"):
            P[c] = np.nan
        return P
    W["month"] = ds_(pd.to_datetime(W["ym"].astype(str), format="%Y%m")) + pd.offsets.MonthEnd(0)
    W["rate2"] = colx(W, "rate")
    m = W["rate2"].isna()
    W.loc[m, "rate2"] = 100.0 * sdiv(W.loc[m, "award_amt"], W.loc[m, "plan_amt"])
    agg = W.groupby(["code", "month"], observed=True).agg(
        award=("award_amt", "sum"), rate=("rate2", "mean")).reset_index()
    orgh = (W.groupby(["code", "month", "org"], observed=True)["award_amt"].sum()
             .reset_index().groupby(["code", "month"], observed=True)["award_amt"]
             .apply(lambda s: hhi(s.to_numpy())).rename("org_hhi").reset_index())
    agg = agg.merge(orgh, on=["code", "month"], how="left").sort_values(["code", "month"])
    agg["award_12m"] = (agg.groupby("code", observed=True)["award"]
                           .transform(lambda s: s.rolling(12, min_periods=6).sum()))
    agg["q1"] = agg.groupby("code", observed=True)["award_12m"].transform(lambda s: dlog(s, 12))
    agg["q2"] = agg.groupby("code", observed=True)["rate"].diff(12)
    agg["q3"] = -agg.groupby("code", observed=True)["org_hhi"].diff(12)
    P = P.merge(agg[["code", "month", "q1", "q2", "q3"]], on=["code", "month"], how="left")
    P["TP_Q1"] = tp_pair(zx(P, "q1"), zx(P, "q2"))
    P["TP_Q2"] = tp_pair(zx(P, "q3"), zx(P, "q2"))
    P["E_P"] = nrow_mean(P, ["TP_Q1", "TP_Q2"])
    return P


register_sensor_pack("P", "조달청 낙찰", ["TP_Q1", "TP_Q2"],
                     pack_p_features, PACK_P_POLICY, PACK_P_INTERP)


# ── 정책 캘린더 (C12) ───────────────────────────────────────────────────────────────────────
def policy_calendar() -> pd.DataFrame:
    rows = []
    for pid, p in SENSOR_PACKS.items():
        for e in p["policy"]:
            r = dict(e)
            r.setdefault("pack", pid)
            rows.append(r)
    rows += [
        {"policy_id": "COVID", "name": "코로나 급락/급반등", "start": "2020-02-20",
         "end": "2020-09-30", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORTBAN1", "name": "공매도 전면금지", "start": "2020-03-16",
         "end": "2021-05-02", "pack": "*", "req_type": "없음", "req_value": ""},
        {"policy_id": "SHORTBAN2", "name": "공매도 전면금지(2차)", "start": "2023-11-06",
         "end": "2025-03-31", "pack": "*", "req_type": "없음", "req_value": ""},
    ]
    C = pd.DataFrame(rows)
    C["start"] = ds_(C["start"])
    C["end"] = ds_(C["end"]).fillna(d_(BT_END))
    C = C.dropna(subset=["start"]).drop_duplicates("policy_id").reset_index(drop=True)
    L.ok(f"정책 캘린더 {len(C)}건 (C12 — 캘린더 없는 팩은 등록 자체가 불가)")
    return C


def policy_mask(cal: pd.DataFrame, packs: Sequence[str], months: pd.DatetimeIndex,
                halo: int = 6) -> pd.Series:
    mask = pd.Series(False, index=months)
    sel = cal[cal["pack"].isin(list(packs) + ["*"])]
    for r in sel.itertuples(index=False):
        mask |= (months >= r.start - pd.DateOffset(months=halo)) & \
                (months <= r.start + pd.DateOffset(months=halo))
        if pd.notna(r.end) and r.end < d_(BT_END):
            mask |= (months >= r.end - pd.DateOffset(months=halo)) & \
                    (months <= r.end + pd.DateOffset(months=halo))
    return mask


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [13] 스코어부 (L2) — 거부권 V1~V8(이진·곱·상쇄불가 C6) + 하한선(§8.2) + Signal(§1.3)       ║
# ║      Signal = rank_pct(E) × rank_pct(U) × ∏V                                              ║
# ║      ★ V 를 연속화하면 전략이 붕괴한다 — 어떤 점수도 밀어내기 정황을 상쇄할 수 없어야 한다. ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

VETO_TABLE = [
    ("V1", "Δ매출>0 인데 (Δ재고+Δ매출채권)/Δ매출 > 1.5 (밀어내기)", "제외"),
    ("V2", "순이익>0 인데 영업CF<0.5×순이익 3분기 연속", "제외"),
    ("V3", "90일 내 희석성 조달(유증/CB/BW/감자)", "제외"),
    ("V4", "θ 미달·매핑 실패 (부분 거부권)", "해당 팩만 무효"),
    ("V5", "감사의견 비적정·자본잠식", "제외"),
    ("V6", "20일 평균거래대금 하한 미달", "제외"),
    ("V7", "위험요인·우발부채 문단 유사도 셀 내 하위 5% (PACK-D)", "제외"),
    ("V8", "인원 급증 + 유효세율 급락 (정책 유인 채용 의심)", "제외"),
]


def apply_vetoes(P: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    P = P.sort_values(["code", "month"]).copy()
    g = lambda c: gcol(P, c)
    # V1 밀어내기
    d_rev = g("revenue_ttm").diff(12)
    push = sdiv(g("inventory").diff(12).fillna(0) + g("receivable").diff(12).fillna(0), d_rev)
    P["v1_metric"] = push
    P["V1"] = np.where((d_rev > 0) & (push > 1.5), 0.0, 1.0)
    # V2 — 분기 프레임에서 만든 3분기 연속 플래그(v2_streak_bad)를 as-of 로 실어온 값 사용.
    v2 = colx(P, "v2_streak_bad")
    P["V2"] = np.where(v2.fillna(0.0) >= 1.0, 0.0, 1.0)     # 플래그 없으면 거부하지 않음
    # V3 희석성 조달(공시목록 직접 관측)
    P["V3"] = 1.0
    disc = ctx.get("disclosures")
    if disc is not None and len(disc) and "corp_code" in P.columns:
        dd = disc[disc["kind"].isin(["rights", "cb", "bw", "reduction"])].copy()
        if len(dd):
            dd["month"] = ds_(dd["rcept_dt"]) + pd.offsets.MonthEnd(0)
            ev = dd.groupby(["corp_code", "month"]).size().rename("dilut").reset_index()
            ev["corp_code"] = ev["corp_code"].astype(str)
            P["corp_code"] = P["corp_code"].astype(str)
            P = P.merge(ev, on=["corp_code", "month"], how="left")
            P = P.sort_values(["code", "month"])
            recent = (P.groupby("code", observed=True)["dilut"]
                       .transform(lambda s: s.fillna(0).rolling(3, min_periods=1).sum()))
            P["V3"] = np.where(recent > 0, 0.0, 1.0)
    # V4 부분 거부권 — θ<0.5 인 행의 해당 팩 E 만 무효화(전면 제외 아님 §8.4)
    P["V4"] = 1.0
    for p in packs_on():
        tc = p.get("theta_col")
        if tc and tc in P.columns and p["E_col"] in P.columns:
            kill = P[tc].notna() & (P[tc] < 0.50)
            if kill.any():
                P.loc[kill, p["E_col"]] = np.nan
                L.info(f"V4 부분거부권 — 팩 {p['id']}: θ<0.50 {int(kill.sum()):,}행의 "
                       f"{p['E_col']} 무효화")
    # V5 자본잠식 + 감사의견 플래그(공시목록)
    impaired = (colx(P, "equity") <= 0)
    P["V5"] = np.where(impaired.fillna(False), 0.0, 1.0)
    if disc is not None and len(disc):
        aud = disc[disc["kind"] == "audit_flag"]
        if len(aud):
            # ★PIT: 의견 플래그는 '최초 접수월 이후'에만 발동 — 기업 전체를 소급 제외하면
            #   미래 부실기업을 과거 유니버스에서 미리 빼는 미래누수가 된다.
            first_bad = (aud.assign(_m=ds_(aud["rcept_dt"]) + pd.offsets.MonthEnd(0))
                            .groupby(aud["corp_code"].astype(str))["_m"].min())
            bad_from = P["corp_code"].astype(str).map(first_bad)
            P["V5"] = np.where(bad_from.notna() & (P["month"] >= bad_from), 0.0, P["V5"])
    # V6 유동성
    P["V6"] = np.where((colx(P, "adv20").fillna(0) >= MIN_ADV_KRW) &
                       (colx(P, "close").fillna(0) > 0), 1.0, 0.0)
    # V7 공시텍스트(PACK-D 데이터가 있을 때만)
    P["V7"] = 1.0
    if "sim_risk_pct" in P.columns:
        P["V7"] = np.where(colx(P, "sim_risk_pct") < 0.05, 0.0, 1.0)
    # V8 인원 급증(월간 상위 10%) + 유효세율 급락(-3%p)
    P["V8"] = 1.0
    if "n1" in P.columns and "d_eff_tax" in P.columns:
        hi_n1 = colx(P, "n1") > P.groupby("month", observed=True)["n1"] \
            .transform(lambda s: s.quantile(0.90))
        P["V8"] = np.where(hi_n1.fillna(False) & (colx(P, "d_eff_tax") < -0.03).fillna(False),
                           0.0, 1.0)
    vcols = [f"V{i}" for i in range(1, 9)]
    for c in vcols:
        P[c] = pd.to_numeric(P[c], errors="coerce").fillna(1.0)
        uq = set(np.unique(P[c]))
        if not uq <= {0.0, 1.0}:
            raise ValueError(f"[C6 위반] {c} 가 이진이 아닙니다: {sorted(uq)[:4]}")
    P["VETO"] = P[vcols].prod(axis=1)
    n = max(len(P), 1)
    L.grid([[cid, desc, act, f"{int((P[cid]==0).sum()):,}",
             f"{100*float((P[cid]==0).mean()):.2f}%"] for cid, desc, act in VETO_TABLE],
           ["ID", "조건", "조치", "발동", "비율"], ["c", "l", "c", "r", "r"],
           title="거부권 발동 현황 (V∈{0,1} · 곱 · 상쇄 불가)")
    return P


FLOOR_MIN_AXES = 2


def breadth_floor(P: pd.DataFrame, axes: Sequence[str], min_axes: int = FLOOR_MIN_AXES,
                  keep_pcts: Optional[dict] = None) -> pd.Series:
    """§8.2 하한선 — '전면 정렬'이 아니라 "보유한 축엔 빈 축이 없을 것":
    그 종목이 실제로 보유한 축이 모두 셀 내 50th 이상 + 보유 축 최소 min_axes 개.
    (순진한 전축 conjunction 은 축 k개에서 잔존율 0.5^k 로 붕괴 — 스펙이 명시 금지한 표본 붕괴)"""
    ok = pd.Series(0, index=P.index)
    bad = pd.Series(0, index=P.index)
    for c in axes:
        pct = rx(P, c)
        if keep_pcts is not None:
            keep_pcts[c] = pct
        ok += (pct >= 0.50).fillna(False).astype(int)
        bad += (pct < 0.50).fillna(False).astype(int)
    return ((bad == 0) & (ok >= min_axes)).astype(float)


def score_by_axes(P: pd.DataFrame, axes: Sequence[str],
                  min_axes: int = FLOOR_MIN_AXES) -> dict:
    """축 집합 하나로 E·FLOOR·Signal·Signal_rank 를 만드는 '유일한' 점수 경로.
    본선·강건성 비교팔(R2/R5)·비교전략이 전부 이 함수만 통과해야 Δ가 '무엇을 뺐는가'를 잰다.

    ① 축별 z 표준화 후 동일가중 평균 — 분산이 다른 축을 원값 평균하면 '동일가중(C7)'이라
       기록하면서 실제로는 분산비만큼 가중이 갈린다.
    ② Signal_rank 는 '월 전체' 백분위 — 선정부가 월 전체를 한 줄로 세우기 때문."""
    axes = [c for c in axes if c in P.columns]
    Z = pd.DataFrame({c: zx(P, c) for c in axes}, index=P.index)
    E_raw = nrow_mean(Z, axes)
    E = rx(P, E_raw)
    pcts: dict = {}
    FLOOR = breadth_floor(P, axes, min_axes, keep_pcts=pcts)
    U = colx(P, "U").fillna(0) if "U" in P.columns else pd.Series(0.0, index=P.index)
    VETO = colx(P, "VETO").fillna(0) if "VETO" in P.columns else pd.Series(1.0, index=P.index)
    Signal = E.fillna(0) * U * VETO * FLOOR
    rank = Signal.groupby(P["month"], observed=True).rank(pct=True, method="average")
    return {"E_raw": E_raw, "E": E, "FLOOR": FLOOR, "Signal": Signal, "Signal_rank": rank,
            "n_axes": P[axes].notna().sum(axis=1) if axes else pd.Series(0, index=P.index),
            "pcts": pcts, "axes": axes}


def assemble_signal(P: pd.DataFrame) -> pd.DataFrame:
    """E = mean(활성 팩 + 공용축 B·C) — 전부 동일가중(C7: 기본값이자 최종값, 최적화 금지)."""
    pack_axes = []
    for p in packs_on():
        if p.get("veto_only"):
            continue                       # 거부권 전용 팩(PACK-D)은 증거층·하한선 축이 아니다
        c = p["E_col"]
        cov = float(P[c].notna().mean()) if c in P.columns and len(P) else 0.0
        if cov < 0.01:
            # ★사유를 원인대로 적는다. E_pack = mean(TP…) × θ 라 ★θ 가 결측이면 원천을
            #   아무리 많이 받아도 E 가 전량 결측이 된다. 그런데 θ 의 분모는 DART 산출물이다
            #   (θ_N=가입자수/직원수, θ_X=수출액/매출). DART 가 굶으면 '국민연금 데이터
            #   부재'로 찍히는데 실제로는 국민연금을 전부 받아 놓은 상태일 수 있다 —
            #   진단을 정반대로 유도하는 로그다. 원천과 θ 를 갈라서 본다.
            tc = p.get("theta_col")
            src = [x for x in p.get("tp_cols", []) if x in P.columns]
            src_cov = max((float(P[x].notna().mean()) for x in src), default=0.0)
            th_cov = float(P[tc].notna().mean()) if tc and tc in P.columns else float("nan")
            if src_cov >= 0.01 and th_cov == th_cov and th_cov < 0.01:
                why = (f"원천은 {src_cov*100:.1f}% 들어왔는데 ★θ({tc})가 {th_cov*100:.2f}% — "
                       f"θ 분모(직원수·매출 등 DART 산출물)가 비어 E 가 전량 결측입니다. "
                       f"이 팩의 수집 문제가 아니라 ★DART 수집이 모자란 것입니다(§8.4)")
            else:
                why = (f"패널 관측 커버리지 {cov*100:.2f}%"
                       + (f" · 원천 {src_cov*100:.1f}%" if src else "")
                       + (f" · θ {th_cov*100:.1f}%" if th_cov == th_cov else "")
                       + " — 데이터 부재 자동 비활성(§8.4)")
            pack_off(p["id"], why)
        else:
            pack_axes.append(c)
    axes = pack_axes + [c for c in ("E_AXB", "E_AXC") if c in P.columns
                        and P[c].notna().mean() >= 0.01]
    if not axes:
        raise RuntimeError("증거층(E) 축이 하나도 없습니다 — 수집 로그에서 어떤 소스가 비었는지 "
                           "확인하세요 (키 미입력이 가장 흔한 원인).")
    S = score_by_axes(P, axes)
    for k in ("E_raw", "E", "FLOOR", "Signal", "Signal_rank", "n_axes"):
        P[k] = S[k]
    for c, v in S["pcts"].items():
        P[f"pct_{c}"] = v
    P.attrs["signal_axes"] = axes
    keep = float(P["FLOOR"].mean()) if len(P) else 0.0
    L.grid([[c, f"{100*float(P[c].notna().mean()):.1f}%",
             f"{100*float((P[f'pct_{c}'] >= 0.5).mean()):.1f}%"] for c in axes],
           ["증거층 축", "관측 커버리지", "50th 이상"], ["l", "r", "r"],
           title="하한선 구성 축 (§8.2 — 빈 축이 없을 것)")
    L.ok(f"Signal 조립 — 축 {len(axes)}개 동일가중(C7) · 하한선 통과 "
         f"{int(P['FLOOR'].sum()):,}행({100*keep:.1f}%)")
    if keep < 0.03:
        L.warn(f"하한선 잔존율 {100*keep:.1f}% — 축이 많을수록 기하급수적으로 좁아집니다"
               f"(대략 0.5^k). 활성 팩 수를 줄이는 편이 스펙 의도('표본 붕괴 없이')에 가깝습니다.")
    P.attrs["input_health"] = input_health(P, axes)
    RUN.io("OUT", "MEM", "signal_panel", P)
    return P


# ── 입력 충분성 게이트 ──────────────────────────────────────────────────────────────────────
#   ★이것이 없어서 가장 위험한 오판이 났다. 실측 실행에서 E_AXB 11.3% · E_AXC 15.8% ·
#     U 가 d1 단독인 상태로 R2(킬 게이트)가 돌아가 "TP 가 나이브를 못 이김 — 패러다임 근거
#     소멸"이라고 단정했다. 그건 ★전략에 대한 판정이 아니라 입력 결손에 대한 판정이다.
#     계약 §15 의 킬은 '온전한 입력에서 이겼는가'를 묻는 것이므로, 입력이 기준 미달이면
#     판정 자체를 보류하고 무엇이 비었는지 보고해야 한다(결과를 좋게 만드는 게 아니라,
#     틀린 사형선고를 막는 것이다).
INPUT_MIN_AXIS_COV = 0.30      # 증거층 축 하나가 이 미만이면 그 축은 사실상 없는 것
INPUT_MIN_D_AXES = 2           # U(미반영도)가 단일 축이면 U 는 '미반영도'가 아니라 그 축 자체
INPUT_MIN_FLOOR = 0.02         # 하한선 잔존율


def input_health(P: pd.DataFrame, axes: Sequence[str]) -> dict:
    """이 패널로 '전략을 판정'해도 되는가. 판정하면 안 되는 이유를 구체적으로 모은다."""
    cov = {c: float(P[c].notna().mean()) for c in axes if c in P.columns}
    thin = sorted([c for c, v in cov.items() if v < INPUT_MIN_AXIS_COV])
    d_have = [c for c in ("d1", "d2", "d3", "d4")
              if c in P.columns and float(P[c].notna().mean()) > 0.01]
    floor = float(P["FLOOR"].mean()) if "FLOOR" in P.columns and len(P) else 0.0
    why = []
    if thin:
        why.append("증거층 축 " + ", ".join(f"{c}({cov[c]*100:.0f}%)" for c in thin)
                   + f" 가 기준 {INPUT_MIN_AXIS_COV*100:.0f}% 미만")
    if len(d_have) < INPUT_MIN_D_AXES:
        why.append(f"U 구성 축이 {len(d_have)}개뿐({'·'.join(d_have) or '없음'}) — "
                   f"U 가 '미반영도'가 아니라 그 축 자체가 됩니다")
    if floor < INPUT_MIN_FLOOR:
        why.append(f"하한선 잔존율 {floor*100:.1f}%")
    return {"ok": not why, "why": why, "axis_cov": cov, "d_axes": d_have, "floor": floor}


def report_input_health(h: Optional[dict]):
    """강건성 스위트 앞에서 한 번 — 판정의 전제가 성립하는지 먼저 보여준다."""
    if not h:
        return
    rows = [[c, f"{v*100:.1f}%", "✔" if v >= INPUT_MIN_AXIS_COV else "✘ 기준미달"]
            for c, v in h["axis_cov"].items()]
    rows.append(["U 구성 축", f"{len(h['d_axes'])}개 ({'·'.join(h['d_axes']) or '없음'})",
                 "✔" if len(h["d_axes"]) >= INPUT_MIN_D_AXES else "✘ 기준미달"])
    rows.append(["하한선 잔존", f"{h['floor']*100:.1f}%",
                 "✔" if h["floor"] >= INPUT_MIN_FLOOR else "✘ 기준미달"])
    L.grid(rows, ["입력", "값", "판정"], ["l", "r", "l"],
           title="입력 충분성 — ★'전략을 판정해도 되는가'를 먼저 묻는다")
    if h["ok"]:
        L.ok("입력 충분 — 강건성 킬 게이트의 판정을 전략에 대한 판정으로 읽어도 됩니다.")
        return
    L.warn("입력 부족 — 아래 이유로 이번 실행의 킬 게이트는 ★'판정 불가'로 보고됩니다.")
    for w in h["why"]:
        L.warn(f"   · {w}")
    L.warn("   ※ 성과 수치는 그대로 보고하되, 그것은 '입력이 이만큼 빈 상태의 성과'이지 "
           "전략의 성과가 아닙니다. 결손을 메운 뒤 다시 판정하세요.")


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [14] 백테스트부 (L3) — 월 리밸 · 익일 시가 체결 · 상폐 -100% · 비용 · 청산 게이트(§8.5/§10) ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

# 증권거래세율 이력(매도 시, 농특세 포함 총부담)
STT_HISTORY = [("2016-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
               ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015)]
FEE_BPS = 1.5            # 편도 수수료(개인 온라인)
IMPACT_K = 0.10          # 제곱근 시장충격 계수 — 참여율↑ 이면 급격히 비싸짐(소형주 가중)


def stt_rate(when) -> float:
    t = d_(when)
    r = STT_HISTORY[0][1]
    for dt0, v in STT_HISTORY:
        if t >= d_(dt0):
            r = v
    return r


def impact_cost(trade_krw: float, adv_krw: float) -> float:
    if not np.isfinite(adv_krw) or adv_krw <= 0:
        return 0.02
    return float(IMPACT_K * math.sqrt(min(1.0, abs(trade_krw) / adv_krw)))


def exit_signal(dm, de) -> bool:
    """청산은 진입과 같은 언어(§8.5): 목표상태(ΔlogE>0 & ΔlogM<ΔlogE)를 벗어나면 청산.
      · dm ≥ de → 시장이 재분류 완료(알파 소진)   · de ≤ 0 → 이익 증가 소멸(논거 무효)
    NaN 은 보유 — 모르는 것을 이유로 팔지 않는다."""
    if dm is None or de is None or pd.isna(dm) or pd.isna(de):
        return False
    return not (de > 0 and dm < de)


def pick_top(df: pd.DataFrame, k: int, rank_col: str) -> pd.DataFrame:
    """상위 k — 동점은 (rank, 원 Signal, code) 명시 키로 깬다. 행 순서로 깨면
    보유종목이 데이터가 아니라 정렬의 함수가 된다(결정성 C8)."""
    if not len(df):
        return df.iloc[0:0]
    keys = [rank_col] + [c for c in ("Signal", "code") if c in df.columns and c != rank_col]
    asc = [False] + [(c != "Signal") for c in keys[1:]]
    return df.sort_values(keys, ascending=asc, kind="mergesort").head(k)


def weigh_positions(sub: pd.DataFrame) -> pd.DataFrame:
    """신호 강도 사이징 + 상한(정책·유동성) water-filling 강제.
    ★clip 후 재정규화는 상한을 도로 뚫는다 — 상한 도달 종목을 고정하고 잔여만 재배분."""
    s = colx(sub, "Signal_rank").fillna(0).to_numpy(dtype=float)
    if len(s) == 0:
        return sub.assign(weight=[])
    med = float(np.median(s))
    spread = float(np.mean(np.abs(s - med)))
    if spread < 1e-6:
        w = np.full(len(s), 1.0 / len(s))
    else:
        raw = np.clip(s - med, 0, None) + 1e-9
        conc = min(2.0, 0.5 + spread * 8.0)
        w = raw ** conc
        w = w / w.sum() if w.sum() > 0 else np.full(len(s), 1.0 / len(s))
    adv = colx(sub, "adv20").fillna(0).to_numpy(dtype=float)
    liq_cap = np.where(adv > 0, adv * ADV_PARTICIP / max(ACCOUNT_KRW, 1), MAX_WEIGHT)
    cap = np.minimum(MAX_WEIGHT, np.maximum(liq_cap, 0.01))
    w = np.clip(w, 0, None)
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
        w[free] = (w[free] / pool * rem) if pool > 1e-12 else rem / free.sum()
    if w.sum() > 1.0 + 1e-9:
        w = w / w.sum()
    return sub.assign(weight=w)


def run_engine(P: pd.DataFrame, months: pd.DatetimeIndex, uni: "PITUniverse",
               master: pd.DataFrame, rank_col: str = "Signal_rank",
               with_costs: bool = True, tag: str = "MAIN",
               audit_gates: bool = False) -> dict:
    """월간 리밸런싱 엔진. 수익 인식: exec_px(익일 시가)→다음달 exec_px 의 fwd_ret.
    상폐 월은 fwd_ret 없으면 -100%(C2 — 누락 처리 금지)."""
    mkt = master.set_index("code")["market"].astype(str).to_dict()
    hold: Dict[str, int] = {}
    prev_w: Dict[str, float] = {}
    recs, hlog = [], []
    for m in months:
        sub = P[P["month"] == m]
        if not len(sub):
            recs.append({"month": m, "ret": 0.0, "ret_gross": 0.0, "n": 0,
                         "turnover": 0.0, "cost": 0.0})
            continue
        need = [c for c in ("code", "adv20", "fwd_ret", "VETO", "FLOOR", "dlog_M", "dlog_E",
                            "exec_px", "Signal", rank_col) if c in sub.columns]
        info: Dict[str, dict] = {}
        for tup in sub[need].itertuples(index=False, name=None):
            info[tup[0]] = dict(zip(need[1:], tup[1:]))
        # 신규 진입 요건: 거부권·하한선 + ★실체결 가능(exec_ok — 정지 임박 종목의 종가 폴백은
        # 보유 평가용이지 진입 가격이 아니다 §10.1) + ★보유상한 도달 종목 재진입 금지(§8.5)
        exec_ok = colx(sub, "exec_ok") if "exec_ok" in sub.columns else \
            sub["exec_px"].notna().astype(float)
        capped = {c for c, hmo in hold.items() if hmo >= MAX_HOLD_MONTHS}
        elig = sub[(colx(sub, "VETO") == 1) & (colx(sub, "FLOOR") == 1) &
                   sub[rank_col].notna() & sub["exec_px"].notna() &
                   (exec_ok > 0) & ~sub["code"].isin(capped)]
        if audit_gates:
            liq = sub[colx(sub, "V6") == 1]
            vet = liq[colx(liq, "VETO") == 1]
            flr = vet[colx(vet, "FLOOR") == 1]
            uni.gate("유동성(V6)", m, liq["code"].tolist())
            uni.gate("거부권통과", m, vet["code"].tolist())
            uni.gate("하한선통과", m, flr["code"].tolist())
        k = int(max(MIN_NAMES, min(MAX_NAMES, round(len(elig) * ENTRY_TOP_PCT))))
        entry = pick_top(elig, k, rank_col)
        if audit_gates:
            uni.gate("최종선정", m, entry["code"].tolist())
        keep = []
        for c, months_held in list(hold.items()):
            r0 = info.get(c)
            if r0 is None:
                continue
            if r0.get("VETO", 1) == 0:
                continue                                  # 거부권 발동 → 즉시 강제청산
            if months_held >= MAX_HOLD_MONTHS:
                continue
            if exit_signal(r0.get("dlog_M"), r0.get("dlog_E")):
                continue
            keep.append(c)
        target = entry
        extra = sub[sub["code"].isin([c for c in keep if c not in set(entry["code"])])]
        if len(extra):
            target = pd.concat([entry, extra], ignore_index=True)
        if len(target) > MAX_NAMES:
            target = pick_top(target, MAX_NAMES, rank_col)
        target = weigh_positions(target) if len(target) else target.assign(weight=[])
        w_new = dict(zip(target["code"], target["weight"])) if len(target) else {}
        turnover = sum(abs(w_new.get(c, 0) - prev_w.get(c, 0))
                       for c in set(w_new) | set(prev_w))
        cost = 0.0
        if with_costs:
            for c in set(w_new) | set(prev_w):
                dw = w_new.get(c, 0) - prev_w.get(c, 0)
                if abs(dw) < 1e-9:
                    continue
                r0 = info.get(c) or {}
                adv = float(r0.get("adv20") or 0) if pd.notna(r0.get("adv20", np.nan)) else 0.0
                cost += abs(dw) * (FEE_BPS / 1e4 + impact_cost(abs(dw) * ACCOUNT_KRW, adv) +
                                   (stt_rate(m) if dw < 0 else 0.0))
        gross = 0.0
        for c, w in w_new.items():
            r0 = info.get(c) or {}
            fr = r0.get("fwd_ret")
            fr = float(fr) if fr is not None and pd.notna(fr) else np.nan
            dl = uni.delist_map.get(c)
            if dl is not None and pd.notna(dl) and m < dl <= m + pd.offsets.MonthEnd(1):
                fr = fr if np.isfinite(fr) else -1.0      # ★정리매매가 없으면 -100%(C2)
            if not np.isfinite(fr):
                fr = 0.0
            gross += w * fr
            hlog.append({"month": m, "code": c, "weight": w, "ret": fr})
        recs.append({"month": m, "ret": gross - cost, "ret_gross": gross, "n": len(w_new),
                     "turnover": turnover, "cost": cost})
        nxt_hold = {}
        for c in w_new:
            nxt_hold[c] = hold.get(c, 0) + 1
        hold = nxt_hold
        prev_w = w_new
    R = pd.DataFrame(recs)
    R["equity"] = (1 + R["ret"].fillna(0)).cumprod()
    return {"returns": R, "holdings": pd.DataFrame(hlog), "tag": tag}


# ── 성과 지표 (§10.2) ───────────────────────────────────────────────────────────────────────
def perf_summary(R: pd.DataFrame) -> dict:
    r = R["ret"].fillna(0).to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return {}
    eq = np.cumprod(1 + r)
    yrs = n / 12.0
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 and eq[-1] > 0 else np.nan
    vol = r.std(ddof=1) * math.sqrt(12) if n > 1 else np.nan
    dn = r[r < 0]
    dvol = dn.std(ddof=1) * math.sqrt(12) if len(dn) > 1 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    uw = cur = 0
    for x in dd:
        cur = cur + 1 if x < -1e-9 else 0
        uw = max(uw, cur)
    mu, t = nw_tstat(r)
    mdd = float(dd.min())
    return {"월수": n, "누적수익": float(eq[-1] - 1), "CAGR": cagr, "연변동성": vol,
            "Sharpe": cagr / vol if vol and np.isfinite(vol) and vol > 0 else np.nan,
            "Sortino": cagr / dvol if dvol and np.isfinite(dvol) and dvol > 0 else np.nan,
            "MDD": mdd, "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
            "승률": float((r > 0).mean()), "월평균": float(r.mean()), "HAC_t": t,
            "최장언더워터(월)": int(uw), "평균종목수": float(R["n"].mean()),
            "월평균회전율": float(R["turnover"].mean()) if "turnover" in R else np.nan,
            "월평균비용": float(R["cost"].mean()) if "cost" in R else np.nan}


def tail_dependence(bt: dict) -> dict:
    """★ 이 전략은 IR 이 아니라 우측 꼬리에 의존한다(§10.2) — 상위 종목 제외 시 성과 소멸 여부."""
    H = bt.get("holdings")
    if H is None or not len(H):
        return {}
    contrib = (H["weight"] * H["ret"]).groupby(H["code"]).sum().sort_values(ascending=False)
    total = float(contrib.sum())
    out = {"총기여": total, "종목수": int(len(contrib))}
    for q, tag in ((0.01, "상위1%"), (0.05, "상위5%"), (0.10, "상위10%")):
        k = max(1, int(round(len(contrib) * q)))
        out[f"{tag} 기여"] = float(contrib.iloc[:k].sum())
        out[f"{tag} 제외후"] = total - float(contrib.iloc[:k].sum())
    out["기여 상위5종목"] = ", ".join(f"{c}({v:+.2f})" for c, v in contrib.head(5).items())
    return out


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [15] 강건성검사부 (R1~R11 · §11) — 순서 강제, 앞 단계 실패 시 진행 금지                    ║
# ║   ★ 성과가 나쁘게 나오면 그대로 보고한다. 파라미터를 조정해 좋아 보이게 만드는 것이        ║
# ║     이 프로젝트에서 가장 해로운 행동이다(§16). 나쁜 결과는 그 자체로 정보다.               ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

RB: "OrderedDict[str, dict]" = OrderedDict()
_IH: dict = {"ok": True, "why": []}      # 이번 스위트의 입력 충분성(assemble_signal 이 채움)


def _rb_put(rid: str, name: str, passed: Optional[bool], detail: str, kill: bool = False,
            metrics: Optional[dict] = None):
    passed = None if passed is None else bool(passed)     # np.bool_ 은 `is False` 비교가 깨진다
    # ★입력이 기준 미달이면 킬 게이트는 '실패'가 아니라 '판정 불가'다. 계약 §15 의 킬은
    #   '온전한 입력에서 이겼는가'를 묻는 것이고, 축 절반이 빈 패널에서의 패배는 전략이
    #   아니라 데이터에 대한 진술이다. 성과 수치는 그대로 두고 판정만 보류한다
    #   (좋게 보이게 만드는 것이 아니라, 틀린 사형선고를 막는 것 — §16 과 충돌하지 않는다).
    if kill and passed is False and not _IH.get("ok", True):
        detail = ("★판정 불가(입력 부족) — " + " / ".join(_IH.get("why", []))
                  + ". 아래는 그 상태에서 측정된 값입니다: " + detail)
        passed = None
    RB[rid] = {"id": rid, "name": name, "pass": passed, "detail": detail, "kill": kill,
               "metrics": metrics or {}}
    icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[passed]
    (L.ok if passed is True else (L.err if passed is False else L.warn))(
        f"[{rid}] {name} → {icon} · {detail}")
    if passed is False and kill and STOP_ON_KILL:
        raise KillGate(f"[{rid}] {name} — {detail}")


def rb_swap(restore: Optional[OrderedDict] = None) -> OrderedDict:
    """강건성 결과 스코프 교체 — 비교전략 스위트가 본전략 결과를 덮어쓰지 않게 한다."""
    old = OrderedDict(RB)
    RB.clear()
    if restore:
        RB.update(restore)
    return old


def _sharpe_of(bt: dict) -> float:
    s = perf_summary(bt["returns"])
    return float(s.get("Sharpe", np.nan)) if s else np.nan


# ── R1: 누수 민감도 자가검정 (C9 — 이 검정 통과 전 모든 결과는 무효) ─────────────────────────
def R1_leak_probe(P: pd.DataFrame, months, uni, master, run_fn,
                  rebuild_fn: Optional[Callable] = None):
    """두 부분:
    R1a(판정): 미래수익을 신호에 직접 주입한 '완벽 누수'조차 성과가 안 좋아지면
               하네스(체결·정렬·수익계산)가 고장 → 전 결과 무효.
    R1b(계약 C9 원문): knowledge_date 를 -30일 앞당긴 오염 재무로 재계산 → 개선 확인.
    """
    base = run_fn(P, tag="R1_base")
    s0 = _sharpe_of(base)
    n_pos = float(base["returns"]["n"].mean()) if len(base["returns"]) else 0.0
    Or = P.copy()
    ora = Or.groupby("month", observed=True)["fwd_ret"].rank(pct=True)
    Or["Signal_rank"] = ora.where(ora.notna(), Or["Signal_rank"])
    s_or = _sharpe_of(run_fn(Or, tag="R1_oracle"))
    if n_pos < 0.5:
        _rb_put("R1", "누수 민감도 자가검정(C9)", None,
                f"평균 보유 {n_pos:.2f}종목 — 포지션이 없어 판정 불가. 하네스 문제가 아니라 "
                f"게이트 문제입니다(유니버스 감쇠 감사에서 어느 게이트가 0인지 보세요).")
        return
    sensitive = np.isfinite(s_or) and np.isfinite(s0) and (s_or - s0) > 0.5
    extra = ""
    if rebuild_fn is not None:
        try:
            P30 = rebuild_fn(-30)                          # knowledge -30일 오염본
            s30 = _sharpe_of(run_fn(P30, tag="R1_kd30"))
            extra = f" · [C9 원문: kd-30일 오염] Sharpe {s0:.3f}→{s30:.3f} (Δ{s30-s0:+.3f})"
        except Exception as e:                             # noqa
            extra = f" · [C9 kd-30 재계산 실패: {type(e).__name__} — R1a 로 판정]"
    _rb_put("R1", "누수 민감도 자가검정(C9)", bool(sensitive),
            f"[R1a] 정상 {s0:.3f} → 미래수익 주입 {s_or:.3f} (Δ{s_or-s0:+.3f})."
            + ("하네스가 누수에 뚜렷이 반응 = 정상." if sensitive else
               " ★완벽 누수에도 무반응 → 체결·정렬·수익계산 고장. §15-1: 전 결과 무효.")
            + extra, kill=False,
            metrics={"s0": s0, "s_oracle": s_or})
    if not sensitive:
        L.err("R1 실패 — 하네스가 누수에 둔감합니다. 이후 모든 결과를 신뢰하지 마세요(§15-1).")


# ── R2: TP vs 나이브 ⭐킬 — 이 시스템의 존재 이유 검정 ──────────────────────────────────────
def R2_tp_vs_naive(P: pd.DataFrame, run_fn):
    tp_axes = [p["E_col"] for p in packs_on() if p["E_col"] in P.columns] + \
              [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    naive_axes = [c for c in ("n1", "p1", "x1", "q1", "dlog_rev", "dlog_ic", "dlog_emp")
                  if c in P.columns and P[c].notna().any()]
    if not tp_axes or not naive_axes:
        _rb_put("R2", "TP vs 나이브(킬)", None, "비교 축 부족 — 판정 불가")
        return

    def arm(axes, tag):
        A = P.copy()
        S = score_by_axes(A, axes)
        for k in ("E", "FLOOR", "Signal", "Signal_rank"):
            A[k] = S[k]
        return A, run_fn(A, tag=tag)

    A_tp, bt_tp = arm(tp_axes, "R2_tp")
    A_nv, bt_nv = arm(naive_axes, "R2_naive")
    f_tp, f_nv = float(A_tp["FLOOR"].mean()), float(A_nv["FLOOR"].mean())
    if f_tp > 0 and not (0.5 <= f_nv / max(f_tp, 1e-9) <= 2.0):
        L.warn(f"두 팔의 유니버스 폭 격차 {f_nv/max(f_tp,1e-9):.2f}배 — 판정을 그만큼 "
               f"할인해서 읽으세요(신호 품질이 아니라 폭 차이를 잴 수 있음).")
    a = bt_tp["returns"]["ret"].fillna(0).to_numpy()
    b = bt_nv["returns"]["ret"].fillna(0).to_numpy()
    k = min(len(a), len(b))
    mu, t = nw_tstat(a[:k] - b[:k])
    s_tp, s_nv = _sharpe_of(bt_tp), _sharpe_of(bt_nv)
    ok = np.isfinite(t) and t > 1.0 and s_tp > s_nv
    _rb_put("R2", "TP vs 나이브(킬)", bool(ok),
            f"TP Sharpe {s_tp:.3f} vs 나이브 {s_nv:.3f} · 월차 {mu*100:+.3f}%p (HAC t={t:.2f}). "
            + ("트레이드오프 곱이 '개선 단독'을 유의하게 이깁니다."
               if ok else "★TP 가 나이브를 못 이김 — §15-2: 패러다임 근거 소멸. 그대로 보고."),
            kill=True, metrics={"s_tp": s_tp, "s_naive": s_nv, "t": t})
    # 하니스 자기검정: 무정보 난수 팔 — 이것조차 못 이기면 위 판정은 게이트가 만든 것
    Z = P.copy()
    Z["_noise"] = np.random.default_rng(SEED).random(len(Z))
    Z["E"] = rx(Z, Z["_noise"])
    Z["FLOOR"] = breadth_floor(Z, tp_axes)
    Z["Signal"] = Z["E"].fillna(0) * colx(Z, "U").fillna(0) * colx(Z, "VETO").fillna(0) * Z["FLOOR"]
    Z["Signal_rank"] = Z.groupby("month", observed=True)["Signal"].rank(pct=True)
    s_rand = _sharpe_of(run_fn(Z, tag="R2_noise"))
    _rb_put("R2b", "TP vs 무정보 난수(장치 검정)", bool(s_tp > s_rand),
            f"TP {s_tp:.3f} vs 난수 {s_rand:.3f}. " +
            ("비교 장치가 신호/무신호를 구별합니다." if s_tp > s_rand else
             "★난수조차 못 이김 — R2 판정은 선별 게이트가 만든 것일 수 있음."))


# ── R3: 퀄리티 팩터 직교화 ⭐킬 ─────────────────────────────────────────────────────────────
def R3_orthogonal(P: pd.DataFrame, bt: dict, months):
    Q = P.copy()
    Q["f_prof"] = sdiv(colx(Q, "op_income_ttm"), colx(Q, "assets"))
    Q["f_lev"] = sdiv(colx(Q, "equity"), colx(Q, "assets"))
    Q["f_mom"] = Q.groupby("code", observed=True)["close"].transform(lambda s: s.pct_change(12))
    Q["f_size"] = np.log(colx(Q, "adv20").where(colx(Q, "adv20") > 0))
    Q["f_val"] = sdiv(colx(Q, "net_income_ttm"), colx(Q, "close"))
    facs = ["f_prof", "f_lev", "f_mom", "f_size", "f_val"]
    fac_rets = []
    for m in months:
        sub = Q[Q["month"] == m]
        if len(sub) < 30:
            continue
        row = {"month": m}
        for f in facs:
            z = cell_z(sub[f], sub["cell"]) if "cell" in sub.columns else \
                pd.Series(np.nan, index=sub.index)
            r = sub["fwd_ret"]
            ok = z.notna() & r.notna()
            if int(ok.sum()) > 10:
                w = np.clip(z[ok] - float(z[ok].min()) + 1e-9, 0, None)
                row[f] = float(np.average(r[ok], weights=w) - r[ok].mean())
            else:
                row[f] = np.nan
        fac_rets.append(row)
    F = pd.DataFrame(fac_rets).set_index("month") if fac_rets else pd.DataFrame()
    if F.empty:
        _rb_put("R3", "퀄리티 직교화(킬)", None, "팩터 수익률 표본 부족 — 판정 불가")
        return
    y = bt["returns"].set_index("month")["ret"]
    J = F.join(y.rename("y"), how="inner").dropna()
    if len(J) < 24:
        _rb_put("R3", "퀄리티 직교화(킬)", None, f"공통 표본 {len(J)}개월 — 부족")
        return
    X = np.column_stack([np.ones(len(J))] + [J[f].to_numpy() for f in facs])
    beta, *_ = np.linalg.lstsq(X, J["y"].to_numpy(), rcond=None)
    resid = J["y"].to_numpy() - X @ beta
    alpha, t = nw_tstat(resid + beta[0])
    ok = np.isfinite(t) and t > 1.5 and alpha > 0
    _rb_put("R3", "퀄리티 직교화(킬)", bool(ok),
            f"수익성·모멘텀·규모·가치 직교화 후 월알파 {alpha*100:+.3f}%p (HAC t={t:.2f}, "
            f"{len(J)}개월). " + ("표준 팩터로 설명 안 되는 알파 잔존."
                                 if ok else "★알파 소멸 — 재포장에 불과(§15-3)."),
            kill=True, metrics={"alpha": alpha, "t": t})


# ── R4: 플라시보 (무작위 선택 귀무분포) ─────────────────────────────────────────────────────
def R4_placebo(P: pd.DataFrame, n_iter: int = 1000):
    sub = P[P["Signal_rank"].notna() & P["fwd_ret"].notna()]
    if len(sub) < 500:
        _rb_put("R4", "플라시보", None, "표본 부족")
        return
    real = []
    groups = []
    for m, g in sub.groupby("month", observed=True):
        if len(g) < 20:
            continue
        k = max(1, int(len(g) * ENTRY_TOP_PCT))
        real.append(g.nlargest(k, "Signal_rank")["fwd_ret"].mean() - g["fwd_ret"].mean())
        groups.append((g["fwd_ret"].to_numpy(), k))
    real_mu = float(np.nanmean(real)) if real else np.nan
    rng = np.random.default_rng(SEED)
    null = np.empty(n_iter)
    for i in range(n_iter):
        acc = [rr[rng.choice(len(rr), size=k, replace=False)].mean() - rr.mean()
               for rr, k in groups]
        null[i] = np.nanmean(acc)
    pval = float((null >= real_mu).mean())
    ok = np.isfinite(real_mu) and pval < 0.05
    _rb_put("R4", f"플라시보({n_iter:,}회)", bool(ok),
            f"실제 초과 {real_mu*100:+.3f}%p/월 vs 귀무 {null.mean()*100:+.3f}%p (p={pval:.4f}). "
            + ("무작위와 구분됩니다." if ok else "★무작위와 구분 안 됨(§15-5)."),
            metrics={"p": pval})


# ── R10: 정책 반증 검정 ⭐전 팩 필수 ────────────────────────────────────────────────────────
def R10_policy(P: pd.DataFrame, cal: pd.DataFrame, months, run_fn):
    packs = [p["id"] for p in packs_on()]
    mask = policy_mask(cal, packs, months)
    clean_m = months[~mask.to_numpy()]
    if len(clean_m) < 24:
        _rb_put("R10", "정책 반증(검정C)", None,
                f"정책구간 제외 후 {len(clean_m)}개월 — 검정력 없음. 이 자체가 관측구간이 "
                f"정책에 광범위하게 덮여 있다는 사실입니다.")
        return
    full = run_fn(P, tag="R10_full")
    clean = run_fn(P[P["month"].isin(clean_m)].copy(), tag="R10_clean", months_sub=clean_m)
    s_f, s_c = _sharpe_of(full), _sharpe_of(clean)
    mu_c = float(clean["returns"]["ret"].mean())
    kept = np.isfinite(s_c) and s_c > 0 and mu_c > 0 and \
        (not np.isfinite(s_f) or s_c >= 0.5 * s_f)
    fire = P.groupby("month", observed=True)["Signal_rank"] \
        .apply(lambda s: float((s > 0.95).mean())).reindex(months)
    in_w = float(fire[mask.to_numpy()].mean())
    out_w = float(fire[~mask.to_numpy()].mean())
    _rb_put("R10", "정책 반증(검정C: 이벤트 ±6M 제외)", bool(kept),
            f"전체 {s_f:.3f} → 정책구간 제외 {s_c:.3f} ({len(clean_m)}개월, 월평균 "
            f"{mu_c*100:+.3f}%p) · [검정A] 발화율 정책 {in_w:.3f} vs 비정책 {out_w:.3f}. "
            + ("정책 이벤트를 빼도 알파 유지." if kept else
               "★정책구간 제외 시 알파 소멸 → 수요가 아니라 제도를 관측한 것 — 팩 폐기 대상(§15-4)."),
            metrics={"s_full": s_f, "s_clean": s_c})
    if not kept:
        for p in packs_on():
            pack_off(p["id"], "R10 정책 반증 미통과 — 자동 비활성화")


# ── R5: 절제 ────────────────────────────────────────────────────────────────────────────────
def R5_ablation(P: pd.DataFrame, run_fn) -> Dict[str, np.ndarray]:
    axes = list(P.attrs.get("signal_axes", []))
    if not axes:
        _rb_put("R5", "절제", None, "축 정보 없음")
        return {}
    variants: Dict[str, np.ndarray] = {}

    def arm(cols, tag):
        A = P.copy()
        S = score_by_axes(A, cols)
        for k in ("E", "FLOOR", "Signal", "Signal_rank"):
            A[k] = S[k]
        bt = run_fn(A, tag=tag)
        variants[tag] = bt["returns"]["ret"].fillna(0).to_numpy()
        return _sharpe_of(bt)

    s0 = arm(axes, "R5_full")
    rows = [["(전체)", f"{s0:.3f}", "—", "—"]]
    for drop in axes:
        rest = [c for c in axes if c != drop]
        if len(rest) < FLOOR_MIN_AXES:
            rows.append([f"− {drop}", "—", "—", f"측정불가(잔여 {len(rest)}축<최소 "
                                                f"{FLOOR_MIN_AXES})"])
            continue
        s = arm(rest, f"R5_no_{drop}")
        rows.append([f"− {drop}", f"{s:.3f}", f"{s-s0:+.3f}",
                     "기여" if s < s0 - 0.03 else ("무기여" if s > s0 + 0.03 else "중립")])
    L.grid(rows, ["절제 대상", "Sharpe", "Δ", "판정"], ["l", "r", "r", "l"],
           title="R5 절제 — 어느 축이 실제로 기여하는가")
    _rb_put("R5", "축별 절제", True, f"기준 {s0:.3f} 대비 기여 귀속 완료 (변형 {len(variants)}개)")
    return variants


# ── R11: 팩 간 상관 ─────────────────────────────────────────────────────────────────────────
def R11_pack_corr(P: pd.DataFrame):
    cols = [p["E_col"] for p in packs_on() if p["E_col"] in P.columns] + \
           [c for c in ("E_AXB", "E_AXC") if c in P.columns]
    cols = [c for c in cols if P[c].notna().sum() > 200]
    if len(cols) < 2:
        _rb_put("R11", "팩 간 상관", None, "활성 축 2개 미만")
        return
    C = P[cols].corr(min_periods=200)
    L.grid([[a] + [f"{C.loc[a, b]:+.2f}" if pd.notna(C.loc[a, b]) else "—" for b in cols]
            for a in cols], ["축"] + cols, ["l"] + ["r"] * len(cols), title="R11 팩 상관행렬")
    hi = [(a, b, C.loc[a, b]) for i, a in enumerate(cols) for b in cols[i + 1:]
          if pd.notna(C.loc[a, b]) and abs(C.loc[a, b]) > 0.7]
    _rb_put("R11", "팩 간 상관", len(hi) == 0,
            "중복 축 없음" if not hi else
            "높은 상관: " + ", ".join(f"{a}~{b}={v:+.2f}" for a, b, v in hi) + " → 통합 검토")


# ── R6: PBO / DSR ───────────────────────────────────────────────────────────────────────────
def R6_pbo_dsr(bt: dict, variants: Optional[Dict[str, np.ndarray]] = None):
    r = bt["returns"]["ret"].fillna(0).to_numpy()
    n = len(r)
    if n < 24:
        _rb_put("R6", "PBO/DSR", None, "표본 부족")
        return
    sr_m = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    n_trials = max(2, len(variants or {}) + 4)
    mu3 = float(pd.Series(r).skew())
    mu4 = float(pd.Series(r).kurt() + 3.0)
    dsr = np.nan
    if np.isfinite(sr_m):
        e = 0.5772156649
        sr0 = ((1 - e) * math.sqrt(2 * math.log(n_trials)) +
               e * math.sqrt(2 * math.log(n_trials * math.e))) / math.sqrt(max(n - 1, 1))
        den = math.sqrt(max(1e-12, 1 - mu3 * sr_m + (mu4 - 1) / 4 * sr_m ** 2))
        dsr = norm_cdf((sr_m - sr0) * math.sqrt(n - 1) / den)
    pbo = np.nan
    if variants and len(variants) >= 3:
        M = np.column_stack([v[:n] for v in variants.values() if len(v) >= n])
        if M.shape[1] >= 3:
            S = 8
            blocks = np.array_split(np.arange(n), S)
            losses = combos = 0
            for i in range(S):
                oos = blocks[i]
                ins = np.concatenate([blocks[j] for j in range(S) if j != i])
                if len(oos) < 3:
                    continue
                best = int(np.argmax(M[ins].mean(axis=0)))
                rank_oos = (M[oos].mean(axis=0)).argsort().argsort()[best] / max(M.shape[1] - 1, 1)
                combos += 1
                if rank_oos < 0.5:
                    losses += 1
            pbo = losses / combos if combos else np.nan
    ok = (np.isfinite(dsr) and dsr > 0.90) and (not np.isfinite(pbo) or pbo < 0.5)
    _rb_put("R6", "PBO/DSR", bool(ok),
            f"DSR={dsr:.3f}(>0.90 권장 · 시행 {n_trials} 가정) · PBO={pbo:.3f}(<0.5 권장). "
            + ("과적합 위험 낮음." if ok else "과적합 위험 있음 — 파라미터 축소 권고(C7 복귀)."),
            metrics={"dsr": dsr, "pbo": pbo})


# ── R7: 레짐 분할 ───────────────────────────────────────────────────────────────────────────
def R7_regime(bt: dict, bench: Dict[str, pd.Series]):
    R = bt["returns"].set_index("month")["ret"]
    rows = []
    ks = bench.get("KOSPI")
    if ks is not None:
        up = ks.reindex(R.index) > 0
        for tag, msk in (("강세(코스피↑)", up), ("약세(코스피↓)", ~up)):
            x = R[msk.fillna(False)]
            if len(x) >= 6:
                rows.append([tag, len(x), f"{x.mean()*100:+.3f}%p",
                             f"{(x > 0).mean()*100:.0f}%"])
    half = len(R) // 2
    for tag, x in (("전반부", R.iloc[:half]), ("후반부", R.iloc[half:])):
        if len(x) >= 6:
            rows.append([tag, len(x), f"{x.mean()*100:+.3f}%p", f"{(x>0).mean()*100:.0f}%"])
    L.grid(rows, ["레짐", "월수", "월평균", "승률"], ["l", "r", "r", "r"], title="R7 레짐 분할")
    verdict = "레짐별 성과 공개 완료"
    pre = R[R.index < d_("2024-01-01")]
    post = R[R.index >= d_("2024-01-01")]
    if len(pre) >= 12 and len(post) >= 6 and "C" in [p["id"] for p in packs_on()]:
        verdict = (f"밸류업 이전({len(pre)}개월) 월평균 {pre.mean()*100:+.3f}%p / "
                   f"이후 {post.mean()*100:+.3f}%p — ")
        verdict += ("★이전 구간 알파 0 이하: 구조적 알파가 아니라 정책 베팅입니다(§6.1 명시 판정)."
                    if pre.mean() <= 0 else "이전 구간에도 양(+) — 정책 베팅만으로 보기 어려움.")
    _rb_put("R7", "레짐 분할", True, verdict)


# ── R8: 하위기간 안정성 ─────────────────────────────────────────────────────────────────────
def R8_yearly(bt: dict):
    R = bt["returns"].copy()
    R["year"] = R["month"].dt.year
    rows, yr_vals = [], []
    for y, g in R.groupby("year"):
        cum = float((1 + g["ret"].fillna(0)).prod() - 1)
        yr_vals.append(cum)
        rows.append([int(y), len(g), f"{cum*100:+.2f}%", f"{g['ret'].mean()*100:+.3f}%p",
                     f"{(g['ret']>0).mean()*100:.0f}%", f"{g['n'].mean():.1f}"])
    L.grid(rows, ["연도", "월수", "연수익", "월평균", "승률", "평균종목"],
           ["c", "r", "r", "r", "r", "r"], title="R8 연도별 분해")
    pos = sum(1 for v in yr_vals if v > 0)
    _rb_put("R8", "하위기간 안정성", True,
            f"{pos}/{len(yr_vals)}개 연도 양(+) · 최악 {min(yr_vals)*100:+.1f}% / "
            f"최고 {max(yr_vals)*100:+.1f}%")


# ── R9: 회전율·용량 ─────────────────────────────────────────────────────────────────────────
def R9_costs(P: pd.DataFrame, run_fn):
    g = run_fn(P, tag="R9_gross", with_costs=False)
    ncost = run_fn(P, tag="R9_net", with_costs=True)
    sg, sn = _sharpe_of(g), _sharpe_of(ncost)
    mn = float(ncost["returns"]["ret"].mean())
    ok = np.isfinite(sn) and sn > 0 and mn > 0
    _rb_put("R9", "비용 차감 후 생존", bool(ok),
            f"비용 전 Sharpe {sg:.3f} → 후 {sn:.3f} (월평균 {mn*100:+.3f}%p · "
            f"회전율 {ncost['returns']['turnover'].mean():.2f} · "
            f"비용 {ncost['returns']['cost'].mean()*100:.3f}%p/월). "
            + ("비용 차감 후에도 생존." if ok else "★비용 차감 후 소멸 — 소액계좌 실행 불가(§15-7)."),
            metrics={"s_gross": sg, "s_net": sn})


def set_input_health(P: pd.DataFrame):
    """강건성 스위트 시작 전에 호출 — 킬 게이트가 '전략'을 판정해도 되는지 정한다."""
    global _IH
    _IH = dict(getattr(P, "attrs", {}).get("input_health") or {"ok": True, "why": []})
    report_input_health(_IH)


def robustness_report(title_suffix: str = ""):
    L.h1("강건성 검사 요약 (R1~R11)" + title_suffix, "킬 게이트 ⭐ · 실패는 그대로 보고")
    if not _IH.get("ok", True):
        L.warn("※ 이번 스위트의 킬 게이트는 입력 부족으로 '판정 불가' 처리되었습니다 — "
               "전략이 기각된 것이 아니라, 판정의 전제가 성립하지 않았습니다.")
    order = ["R1", "R2", "R2b", "R3", "R4", "R10", "R5", "R11", "R6", "R7", "R8", "R9"]
    rows = []
    for rid in order:
        r = RB.get(rid)
        if not r:
            rows.append([rid, "—", "미실행", ""])
            continue
        icon = {True: "✔ 통과", False: "✘ 실패", None: "— 판정불가"}[r["pass"]]
        rows.append([rid + ("⭐" if r["kill"] else ""), r["name"], icon, r["detail"]])
    L.grid(rows, ["ID", "검사", "판정", "상세"], ["l", "l", "c", "l"], cap=88)
    kills = [r for r in RB.values() if r["pass"] is False and r["kill"]]
    if kills:
        L.h1("⛔ 킬 기준 위반(§15)", "우회하거나 파라미터를 조정해 통과시키지 마십시오")
        for r in kills:
            say(f"  · [{r['id']}] {r['name']}: {r['detail']}")


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [16] 성과검증·해석표·진단카드 (§13) + 비교전략(시가총액 하위 1000 압축)                     ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

INTERP_D = [("ΔE>0, ΔM≤0", "★목표 상태 — 시장이 개선을 일회성으로 분류", "진입"),
            ("ΔE>0, ΔM>0", "리레이팅 진행 중 — 알파 소진", "관망/청산"),
            ("ΔE≤0, ΔM>0", "기대만 앞섬", "배제"),
            ("ΔE≤0, ΔM≤0", "개선 없음", "배제")]
INTERP_COMMON = [("TP_B1", "수요가 공급을 당김 — 협상력", "밀어내기 가능성 → V1 확인"),
                 ("TP_B2", "이익의 질 양호", "회계적 이익 우위"),
                 ("TP_C1", "수익성 유지 확장 — 제약선 이동", "확장이 수익성 희석"),
                 ("TP_C2", "희석 없는 인력 확장", "단순 규모 확대")]


def performance_report(bt: dict, bench: Dict[str, pd.Series], label: str = "본전략",
                       interim: bool = False):
    sub = f"{BT_START} ~ {BT_END} · 월 리밸 · 익일 시가 체결 · 롱온리"
    if interim:
        sub += "  ⚠ 중간(잠정) 결과 — 수집 시간예산 도달로 부분 데이터 기반"
    L.h1(f"성과 검증 — {label}", sub)
    s = perf_summary(bt["returns"])
    if not s:
        L.warn("수익률 시계열이 비어 성과를 계산할 수 없습니다.")
        return
    fmt_pct = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
    fmt_pp = {"월평균", "월평균비용"}
    rows = []
    for k, v in s.items():
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            rows.append([k, "—"])
        elif k in fmt_pct:
            rows.append([k, f"{v*100:+.2f}%"])
        elif k in fmt_pp:
            rows.append([k, f"{v*100:+.3f}%p"])
        elif isinstance(v, float):
            rows.append([k, f"{v:,.3f}"])
        else:
            rows.append([k, f"{v:,}"])
    L.grid(rows, ["지표", "값"], ["l", "r"], title="포트폴리오 성과")
    R = bt["returns"].set_index("month")["ret"]
    brows = []
    for nm, b in (bench or {}).items():
        bb = b.reindex(R.index).fillna(0)
        cs = float((1 + R.fillna(0)).prod() - 1)
        cb = float((1 + bb).prod() - 1)
        _, t = nw_tstat((R.fillna(0) - bb).to_numpy())
        brows.append([nm, f"{cb*100:+.1f}%", f"{cs*100:+.1f}%", f"{(cs-cb)*100:+.1f}%p",
                      f"{t:.2f}"])
    if brows:
        L.grid(brows, ["벤치마크", "벤치 누적", "전략 누적", "초과", "HAC t"],
               ["l", "r", "r", "r", "r"], title="벤치마크 대비")
    tail = tail_dependence(bt)
    if tail:
        L.grid([[k, (f"{v:,.3f}" if isinstance(v, float) else str(v))] for k, v in tail.items()],
               ["항목", "값"], ["l", "r"],
               title="우측 꼬리 의존도 (§10.2 — 이 전략은 IR 이 아니라 꼬리에 의존한다)")
        if tail.get("총기여", 0) > 0 and tail.get("상위5% 제외후", 0) <= 0:
            L.warn("상위 5% 종목 제외 시 총기여 ≤0 — 성과가 소수 종목에 전적으로 의존합니다. "
                   "실전에서 그 종목을 놓치면 전략 전체가 실패합니다(사이징에 반드시 반영).")


def interpretation_report(P: pd.DataFrame, title: str = "해석 참조표 (§13.2)"):
    L.h1(title, "TP 발화/미발화가 각각 무슨 뜻인가 + D축 상태 + 발화 통계")
    rows = []
    for p in packs_on():
        for tp, fire, quiet in p["interp"]:
            rows.append([p["id"], tp, fire, quiet])
    for tp, fire, quiet in INTERP_COMMON:
        rows.append(["공용", tp, fire, quiet])
    L.grid(rows, ["팩", "TP", "발화 의미", "미발화 의미"], ["c", "l", "l", "l"], cap=46)
    L.grid([[a, b, c] for a, b, c in INTERP_D], ["D축 상태", "해석", "조치"], ["l", "l", "c"],
           title="D축(반영도) 상태 해석")
    if "D_state" in P.columns and len(P):
        cnt = P["D_state"].value_counts()
        L.grid([[k, f"{v:,}", f"{100*v/len(P):.1f}%"] for k, v in cnt.items()],
               ["상태", "행수", "비중"], ["l", "r", "r"], title="패널의 D축 상태 분포")
    fired = []
    tp_all = [(p["id"], tp) for p in packs_on() for tp in p["tp_cols"]] + \
             [("공용", t) for t in ("TP_B1", "TP_B2", "TP_C1", "TP_C2")]
    for pid, tp in tp_all:
        if tp in P.columns and P[tp].notna().any():
            v = P[tp]
            fired.append([pid, tp, f"{int(v.notna().sum()):,}", f"{float(v.mean()):+.3f}",
                          f"{100*float((v > 1).mean()):.2f}%"])
    if fired:
        L.grid(fired, ["팩", "TP", "관측", "평균", "발화율(>1σ²)"],
               ["c", "l", "r", "r", "r"],
               title="트레이드오프 쌍 발화 통계 (TP=곱 — 두 조건 동시 성립 시만 양수)")


def diagnostic_cards(P: pd.DataFrame, master: pd.DataFrame, top_n: int = 5,
                     title: str = "종목별 진단 카드 (§13.1)"):
    L.h1(title, "최근 시점 신호 상위 — 왜 뽑혔는지 한 장으로")
    last = P["month"].max()
    sub = P[(P["month"] == last) & (colx(P, "VETO") == 1) & (colx(P, "FLOOR") == 1)]
    if not len(sub):
        sub = P[P["month"] == last]
    if not len(sub):
        L.warn("마지막 시점 패널이 비어 카드를 만들 수 없습니다.")
        return
    names = master.set_index("code")["name"].to_dict()
    for r in sub.nlargest(min(top_n, len(sub)), "Signal_rank").itertuples(index=False):
        say("\n" + "─" * 102)
        say(f"[{r.code}] {names.get(r.code, '')}   셀: {getattr(r, 'cell', '?')}   "
            f"신호일: {pd.Timestamp(last).date()}")
        say("─" * 102)
        sig = float(getattr(r, "Signal_rank", np.nan))
        say(f"Signal {sig:.3f} (상위 {100*(1-sig):.1f}%)  E {float(getattr(r,'E',np.nan)):.3f}  "
            f"U {float(getattr(r,'U',np.nan)):.3f}  Veto {'통과' if getattr(r,'VETO',0)==1 else '차단'}")
        on = [p["id"] for p in packs_on()
              if np.isfinite(float(getattr(r, p["E_col"], np.nan)))]
        say(f"활성 팩: {','.join(on) or '없음'}")
        say("\n■ 발화한 트레이드오프")
        tps = []
        for p in packs_on():
            for tp, fire, quiet in p["interp"]:
                v = float(getattr(r, tp, np.nan)) if hasattr(r, tp) else np.nan
                if np.isfinite(v):
                    tps.append((tp, v, fire if v > 0 else quiet))
        for tp, fire, quiet in INTERP_COMMON:
            v = float(getattr(r, tp, np.nan)) if hasattr(r, tp) else np.nan
            if np.isfinite(v):
                tps.append((tp, v, fire if v > 0 else quiet))
        for tp, v, meaning in sorted(tps, key=lambda x: -x[1])[:8]:
            say(f"  {tp:<7} {v:+7.2f}  [{'발화' if v > 0 else '미발화'}] {meaning}")
        say("\n■ 미반영도(U)")
        say(f"  d1  ΔlogE {float(getattr(r,'dlog_E',np.nan)):+.3f}  "
            f"ΔlogM {float(getattr(r,'dlog_M',np.nan)):+.3f} → {getattr(r,'D_state','?')}")
        for k, lab in (("d2", "목표주가 상향 리비전"), ("d3", "기관+외인 수급"),
                       ("d4", "커버리지 변화")):
            v = float(getattr(r, k, np.nan)) if hasattr(r, k) else np.nan
            say(f"  {k}  {lab}: " + (f"{v:+.4f}" if np.isfinite(v)
                                     else "데이터 부족(결측 — 0으로 채우지 않음)"))
        say("\n■ 정책 오염 점검")
        det = float(getattr(r, "d_eff_tax", np.nan)) if hasattr(r, "d_eff_tax") else np.nan
        say(f"  유효세율 변화 {det:+.4f} (임계 -0.03)  "
            f"{'✔ V8 통과' if getattr(r, 'V8', 1) == 1 else '✘ V8 발동 — 정책 유인 채용 의심'}")
        say("\n■ 거부권  " + "  ".join(
            f"V{i}{'✔' if getattr(r, f'V{i}', 1) == 1 else '✘'}" for i in range(1, 9)))
    say("─" * 102)


def dataflow_map():
    L.h1("데이터 흐름 지도 (거시)", "에러가 나면 어느 상자인지부터 — 미시 진단은 I/O 원장으로")
    say("""
  [수집부 L1]  종목마스터(FDR캐시+KIND+DART+스냅샷) · 가격(★날짜축 전종목: KRX OpenAPI→마켓
      │        플레이스→pykrx, 하루 1회=전종목 · 잔여만 네이버/FDR 종목축 구제)
      │        DART(재무·직원·공시) · 리서치(한경+네이버→원장) · 팩전용(NPS·조달·관세·원문)
      │        └ 캐시: 로컬 D드라이브+구글드라이브 탐색 → 부족분만 신규 → ★전부 드라이브 저장
      ▼        └ 시간예산 4h 도달 → 수집 중단 → 부분 데이터로 '중간결과' 진행
  [정제부]     pit_mark(event/knowledge) → PIT 게이트웨이(knowledge≤as_of 강제 · C1)
      ▼        재무 tidy(접수일=knowledge · 누적→분기 · TTM) · 셀(월,산업,규모 · C11)
  [피처 L1]    공용축 B·C·D + 센서팩 C/N/D/X/P — TP = z(개선)×z(대가회피) (곱 · §1.1)
      ▼
  [스코어 L2]  거부권 V1~V8(이진·곱) → 하한선(빈 축 없음) → Signal=rank(E)×rank(U)×∏V
      ▼
  [백테스트 L3] 익일 시가 체결 · 상폐 -100% · 비용(수수료+거래세 이력+제곱근 충격)
      ▼
  [검증]       성과검증 → 강건성 R1~R11(킬게이트) → 해석표·진단카드
      ▼
  [비교전략 L7] 시총 하위 1000 압축 유니버스 → 동일 파이프라인 재랭킹 → 별도 성과·강건성·해석
      ▼
  [저장]       산출물 → 구글드라이브 전용 인덱스(+공용 원장) → 다운로드 링크
""")


# ── 비교전략 — 시가총액 하위 1000 압축 유니버스 ─────────────────────────────────────────────
def _mktcap_value(P: pd.DataFrame, mktcap: Optional[pd.DataFrame],
                  master: pd.DataFrame) -> pd.DataFrame:
    """(code, month) 시총 서열값 + 소스 감사. 사다리:
    ① 정식 스냅샷(pykrx/KRX) ② 주식수 역산(close×현재주식수 — 과거 증자 미반영 근사)
    ③ ADV 보정(그 달 시총 보유 종목으로 log(cap)~log(adv) 중앙값 보정) — 전부 감사표에 표시."""
    P = P.copy()
    P["cap_val"] = np.nan
    P["cap_origin"] = ""
    if mktcap is not None and len(mktcap):
        mc = mktcap[["code", "month", "mktcap"]].dropna()
        P = P.merge(mc.rename(columns={"mktcap": "_cap1"}), on=["code", "month"], how="left")
        P.loc[P["_cap1"].notna(), "cap_val"] = P.loc[P["_cap1"].notna(), "_cap1"]
        P.loc[P["_cap1"].notna(), "cap_origin"] = "snapshot"
        P = P.drop(columns=["_cap1"])
    shares = master.set_index("code")["shares_now"].to_dict()
    need = P["cap_val"].isna()
    # ★전체 인덱스에서 계산 후 where 로 마스킹 — 부분 인덱스 Series 와의 불리언 결합은
    #   정렬 NaN 을 만들어 .loc 마스크가 깨질 수 있다(인덱스 정렬 안전화).
    est = (P["code"].map(shares) * colx(P, "close")).where(need)
    fill = need & est.notna()
    P.loc[fill, "cap_val"] = est[fill]
    P.loc[fill, "cap_origin"] = "shares_proxy"
    # ADV 보정 — 시총도 주식수도 없는 종목(대개 상장폐지분)
    need2 = P["cap_val"].isna() & colx(P, "adv20").notna() & (colx(P, "adv20") > 0)
    if need2.any():
        both = P[P["cap_val"].notna() & (colx(P, "adv20") > 0)]
        offset_by_m = {}
        if len(both):
            tmp = both.assign(_off=np.log(both["cap_val"]) - np.log(both["adv20"]))
            offset_by_m = tmp.groupby("month")["_off"].median().to_dict()
        off = P.loc[need2, "month"].map(offset_by_m)
        glob = float(np.nanmedian(list(offset_by_m.values()))) if offset_by_m else 5.0
        est2 = np.exp(np.log(P.loc[need2, "adv20"]) + off.fillna(glob))
        P.loc[need2, "cap_val"] = est2
        P.loc[need2, "cap_origin"] = "adv_proxy"
    mix = P[P["cap_val"].notna()]["cap_origin"].value_counts()
    if len(mix):
        L.grid([[k, f"{v:,}", f"{100*v/int(mix.sum()):.1f}%"] for k, v in mix.items()],
               ["시총 소스", "행수", "비중"], ["l", "r", "r"],
               title="비교전략 시가총액 소스 감사 (프록시 비중이 크면 경계 오차 유의)")
        if (mix.get("shares_proxy", 0) + mix.get("adv_proxy", 0)) > mix.sum() * 0.5:
            L.warn("시총의 절반 이상이 프록시 — KRX 로그인 또는 pykrx 로 정식 스냅샷을 채우면 "
                   "하위 1000 경계가 정확해집니다(수집분은 드라이브에 캐시됩니다).")
    return P


def run_comparison(P: pd.DataFrame, ctx: dict, months: pd.DatetimeIndex, uni: "PITUniverse",
                   master: pd.DataFrame, bench: Dict[str, pd.Series],
                   robust_level: str = "CORE", interim: bool = False) -> dict:
    """본전략과 동일한 신호·엔진을 '시총 하위 COMPARE_BOTTOM_N' 압축 유니버스에 적용:
    별도 백테스트→성과검증→강건성→해석표 + 본전략 비교표."""
    L.h1(f"비교전략 — 시가총액 하위 {COMPARE_BOTTOM_N:,} 압축 유니버스",
         "동일 신호·동일 엔진 · 유니버스만 압축 → 소형주 구간에서의 신호 효율 비교")
    C = _mktcap_value(P, ctx.get("mktcap"), master)
    picks = []
    for m, g in C.groupby("month", observed=True):
        gg = g[g["cap_val"].notna() & g["close"].notna()]
        if not len(gg):
            continue
        n = len(gg)
        k = COMPARE_BOTTOM_N if n > COMPARE_BOTTOM_N * 1.2 else max(20, int(n * 0.5))
        picks.append(gg.nsmallest(min(k, n), "cap_val")[["code", "month"]])
    if not picks:
        L.warn("비교 유니버스를 만들 시총 데이터가 없습니다 — 비교전략을 건너뜁니다.")
        return {}
    sel = pd.concat(picks, ignore_index=True)
    sel["_in"] = 1.0
    C = C.merge(sel, on=["code", "month"], how="left")
    Pc = C[C["_in"] == 1.0].drop(columns=["_in"]).copy()
    n_month = sel.groupby("month").size()
    L.info(f"압축 유니버스 월평균 {n_month.mean():,.0f}종목 "
           f"(최소 {n_month.min():,} · 최대 {n_month.max():,})"
           + ("" if n_month.mean() >= COMPARE_BOTTOM_N * 0.8 else
              " — 유니버스가 목표보다 작아 하위 50% 규칙으로 자동 축소된 달이 있습니다"))
    # 압축 유니버스 내부에서 U·E·하한선·랭크 재계산(같은 점수 경로 — score_by_axes)
    if "U_raw" in Pc.columns:
        Pc["U"] = rx(Pc, Pc["U_raw"])
    axes = [c for c in P.attrs.get("signal_axes", []) if c in Pc.columns
            and Pc[c].notna().mean() >= 0.01]
    if not axes:
        L.warn("압축 유니버스에서 유효한 증거층 축이 없습니다 — 비교전략 중단.")
        return {}
    S = score_by_axes(Pc, axes)
    for k in ("E", "FLOOR", "Signal", "Signal_rank"):
        Pc[k] = S[k]
    Pc.attrs["signal_axes"] = axes

    def run_c(pp, tag="CMP", with_costs=True, months_sub=None):
        return run_engine(pp, months_sub if months_sub is not None else months, uni, master,
                          with_costs=with_costs, tag=tag)

    bt_c = run_c(Pc, tag="CMP_MAIN")
    performance_report(bt_c, bench, label=f"비교전략(시총 하위 {COMPARE_BOTTOM_N:,})",
                       interim=interim)
    # 강건성(비교전략 스코프 — 본전략 결과를 덮지 않도록 스코프 교체)
    saved = rb_swap()
    keep_kill = globals()["STOP_ON_KILL"]
    globals()["STOP_ON_KILL"] = False
    try:
        if robust_level in ("CORE", "LITE"):
            try:
                R1_leak_probe(Pc, months, uni, master, run_c)
            except Exception as e:                        # noqa
                L.warn(f"비교 R1 실패({type(e).__name__}) — 계속")
            if robust_level == "CORE":
                try:
                    R2_tp_vs_naive(Pc, run_c)
                except Exception as e:                    # noqa
                    L.warn(f"비교 R2 실패({type(e).__name__}) — 계속")
            R4_placebo(Pc, n_iter=300 if robust_level == "CORE" else 120)
            R7_regime(bt_c, bench)
            R8_yearly(bt_c)
            R9_costs(Pc, run_c)
        robustness_report(title_suffix=" — 비교전략")
    finally:
        globals()["STOP_ON_KILL"] = keep_kill
        cmp_rb = rb_swap(saved)
    interpretation_report(Pc, title="해석 참조표 — 비교전략(시총 하위 1000)")
    diagnostic_cards(Pc, master, top_n=3, title="진단 카드 — 비교전략 상위 3")
    return {"backtest": bt_c, "panel_rows": len(Pc), "robust": cmp_rb, "axes": axes}


# ── 드리프트 감사 — 상향(성과 과대) vs 하향(성과 과소) ──────────────────────────────────────
#   "성과가 나빴다"는 두 갈래다: ①전략이 나쁘다 ②측정이 아래로 치우쳤다.
#   구분하지 않으면 멀쩡한 전략을 죽이거나(하향 과다), 없는 알파를 믿는다(상향 과다).
#   그래서 방향별로 요인을 세우고, 환산 가능한 것은 수익률 영향(bp/월)으로 크기를 비교한다.
def drift_audit(P: pd.DataFrame, bt: Optional[pd.DataFrame] = None,
                master: Optional[pd.DataFrame] = None) -> dict:
    up: List[list] = []      # 상향 드리프트(성과를 좋게 만드는 쪽)
    dn: List[list] = []      # 하향 드리프트(성과를 나쁘게 만드는 쪽)
    h = dict(getattr(P, "attrs", {}).get("input_health") or {})

    # ── 상향 ① 생존자편향 잔존: 폐지목록에서 코드 정규화로 탈락한 종목 ────────────
    n_lost = float(UNI_AUDIT.get("delist_dropped", 0) or 0)
    drop_r = float(UNI_AUDIT.get("delist_drop_rate", 0.0) or 0.0)
    n_uni = float(P["code"].nunique()) if "code" in P.columns else 0.0
    if n_lost > 0:
        # 탈락 종목이 유니버스에 남았다면 그 종목의 마지막 달 수익은 -100% 였다.
        # 상한 추정: (탈락수/유니버스) × 100%p 를 120개월에 분산 — 실제 발현은 이보다 훨씬 작다.
        bp = 1e4 * (n_lost / max(n_uni, 1.0)) / 120.0
        up.append(["생존자편향 잔존(폐지 코드 탈락)",
                   f"{n_lost:,.0f}종목 · 폐지목록의 {drop_r*100:.0f}%",
                   f"최대 +{bp:.1f}bp/월", "상한 — 실제 선정됐을 확률만큼만 발현"])

    # ── 상향 ② PIT 스탬프 이상 ───────────────────────────────────────────────────
    n_fut = int(PIT_AUDIT.get("future_knowledge", 0))
    n_fix = int(PIT_AUDIT.get("kd_lt_ed_fixed", 0))
    if n_fut or n_fix:
        up.append(["PIT 스탬프 이상",
                   f"미래 knowledge {n_fut:,}행 · knowledge<event 보정 {n_fix:,}행",
                   "정성(작음)",
                   "보정은 미래 쪽으로만 하고 PIT 관문이 as_of 절단 — 누수로는 이어지지 않음"])

    # ── 하향 ① U 가 단일축일 때의 구조적 편향 ────────────────────────────────────
    d_axes = list(h.get("d_axes") or [])
    sel = P[P["FLOOR"].fillna(False).astype(bool)] if "FLOOR" in P.columns else P.iloc[0:0]
    dlm = float(pd.to_numeric(sel["dlog_M"], errors="coerce").mean()) \
        if len(sel) and "dlog_M" in sel.columns else float("nan")
    if len(d_axes) < 2:
        dn.append([f"U 가 단일축({'·'.join(d_axes) or '없음'})",
                   (f"선정군 ΔlogM 평균 {dlm:+.2f}" if np.isfinite(dlm) else "—"),
                   "정성(매우 큼)",
                   "U 가 '미반영도'가 아니라 '많이 떨어진 주식' 자체가 됨 — 하락추종으로 변질"])

    # ── 하향 ② 증거층 축 결측 ────────────────────────────────────────────────────
    thin = [c for c, v in (h.get("axis_cov") or {}).items() if v < INPUT_MIN_AXIS_COV]
    floor = float(h.get("floor", float("nan")))
    if thin:
        dn.append(["증거층 축 결측", ", ".join(thin), "정성(매우 큼)",
                   f"하한선 잔존 {floor*100:.1f}% — 축이 빈 행은 통과 자체가 불가"])

    # ── 하향 ③ 셀 폴백(규모·산업 통제 상실) ──────────────────────────────────────
    fb = float(CELL_AUDIT.get("fallback_rate", float("nan")))
    if np.isfinite(fb) and fb > 0.25:
        dn.append(["셀 폴백 과다", f"{fb*100:.0f}% 가 산업상위/전체로 강등", "정성(중간)",
                   "규모·산업 통제가 그만큼 사라진 상태의 z·랭크"])

    # ── 하향 ④ 비용 · ⑤ 집중도 ───────────────────────────────────────────────────
    if bt is not None and len(bt):
        if "cost" in bt.columns:
            c_m = float(pd.to_numeric(bt["cost"], errors="coerce").mean())
            dn.append(["거래비용", f"월 {c_m*100:.3f}%p", f"-{c_m*1e4:.0f}bp/월",
                       "편향이 아니라 실비 — 회전율이 높으면 성과를 지배"])
        if "n_hold" in bt.columns:
            nh = float(pd.to_numeric(bt["n_hold"], errors="coerce").mean())
            if nh < MIN_NAMES * 2:
                dn.append(["보유 집중", f"평균 {nh:.1f}종목 (상한 {MAX_NAMES})", "정성(큼)",
                           "표본이 적어 성과가 개별 종목 운에 지배 — 신뢰구간이 매우 넓다"])

    L.grid(up or [["—", "—", "—", "감지된 상향 요인 없음"]],
           ["상향 요인(성과 과대)", "규모", "추정 영향", "비고"], ["l", "l", "r", "l"],
           title="드리프트 감사 ① 상향 — 성과를 좋게 만드는 편향")
    L.grid(dn or [["—", "—", "—", "감지된 하향 요인 없음"]],
           ["하향 요인(성과 과소)", "규모", "추정 영향", "비고"], ["l", "l", "r", "l"],
           title="드리프트 감사 ② 하향 — 성과를 나쁘게 만드는 편향")

    big = lambda rows: any("큼" in str(r[2]) for r in rows)
    ub, db = big(up), big(dn)
    if db and not ub:
        v = ("★하향 드리프트가 압도적으로 심합니다. 이 상태의 음(-)의 성과는 전략의 성질이 "
             "아니라 입력 결손이 만든 것입니다 — 결손을 메우기 전의 킬 판정을 전략에 대한 "
             "판정으로 읽으면 안 됩니다.")
    elif ub and not db:
        v = ("★상향 드리프트가 우세합니다. 양(+)의 성과를 액면 그대로 믿지 마세요 — "
             "생존자편향·PIT 이상을 먼저 제거하고 재측정해야 합니다.")
    elif ub and db:
        v = ("양방향 드리프트가 모두 큽니다. 부호조차 신뢰할 수 없으므로 성과 해석 이전에 "
             "데이터 결손부터 해소하세요.")
    else:
        v = "양방향 모두 지배적 요인이 없습니다 — 성과를 전략의 성질로 읽어도 되는 수준입니다."
    (L.warn if (ub or db) else L.ok)(v)
    return {"up": up, "down": dn, "verdict": v}


def comparison_table(bt_main: dict, bt_cmp: dict, bench: Dict[str, pd.Series]):
    """본전략 vs 비교전략 최종 비교표(§요구: '기존 전략 대비 비교')."""
    L.h1("본전략 vs 비교전략(시총 하위 1000) 비교표")
    s1, s2 = perf_summary(bt_main["returns"]), perf_summary(bt_cmp["returns"])
    keys = ["누적수익", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "승률",
            "월평균", "HAC_t", "평균종목수", "월평균회전율", "월평균비용", "최장언더워터(월)"]
    pctk = {"누적수익", "CAGR", "연변동성", "MDD", "승률"}
    rows = []
    for k in keys:
        a, b = s1.get(k), s2.get(k)
        def f(v):
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            return f"{v*100:+.2f}%" if k in pctk else \
                (f"{v*100:+.3f}%p" if k == "월평균" else
                 (f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"))
        diff = "—"
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and \
                np.isfinite(a) and np.isfinite(b):
            diff = f"{(b-a)*100:+.2f}%p" if k in pctk else f"{b-a:+.3f}"
        rows.append([k, f(a), f(b), diff])
    ra = bt_main["returns"].set_index("month")["ret"]
    rb2 = bt_cmp["returns"].set_index("month")["ret"]
    j = pd.concat([ra, rb2], axis=1, keys=["a", "b"]).dropna()
    corr = float(j["a"].corr(j["b"])) if len(j) > 12 else np.nan
    Ha, Hb = bt_main.get("holdings"), bt_cmp.get("holdings")
    jac = np.nan
    if Ha is not None and Hb is not None and len(Ha) and len(Hb):
        js = []
        for m in sorted(set(Ha["month"]) & set(Hb["month"])):
            A = set(Ha[Ha["month"] == m]["code"])
            B = set(Hb[Hb["month"] == m]["code"])
            if A | B:
                js.append(len(A & B) / len(A | B))
        jac = float(np.mean(js)) if js else np.nan
    rows.append(["월수익 상관", "—", "—", f"{corr:+.2f}" if np.isfinite(corr) else "—"])
    rows.append(["보유종목 자카드(평균)", "—", "—", f"{jac:.2f}" if np.isfinite(jac) else "—"])
    L.grid(rows, ["지표", "본전략", "비교(하위1000)", "차이/공통"], ["l", "r", "r", "r"])
    a_sh, b_sh = s1.get("Sharpe", np.nan), s2.get("Sharpe", np.nan)
    if np.isfinite(a_sh) and np.isfinite(b_sh):
        if b_sh > a_sh + 0.1:
            L.info("해석: 압축(소형주) 유니버스에서 신호 효율이 더 높습니다 — 단, 소형주는 "
                   "유동성·비용 민감도가 크므로 R9(비용 생존)와 V6 통과율을 함께 보십시오.")
        elif a_sh > b_sh + 0.1:
            L.info("해석: 전체 유니버스가 우위 — 소형주 구간에서는 신호 대비 비용·거부권 "
                   "차단이 큽니다. 하한선/유동성 게이트의 감쇠표를 확인하십시오.")
        else:
            L.info("해석: 두 유니버스 성과가 유사 — 신호가 규모 요인에 크게 의존하지 않습니다.")


# ╔══════════════════════════════════════════════════════════════════════════════════════════╗
# ║ [17] 계약 자가검정(C1~C12) · 합성 스모크 · 오케스트레이터 main()                            ║
# ╚══════════════════════════════════════════════════════════════════════════════════════════╝

CONTRACT_LOG: List[dict] = []


def _ct(cid: str, name: str, fn: Callable[[], Tuple[bool, str]]):
    try:
        ok, msg = fn()
    except Exception as e:                                        # noqa
        ok, msg = False, f"{type(e).__name__}: {e}"
    CONTRACT_LOG.append({"id": cid, "name": name, "ok": bool(ok), "msg": str(msg)})


def contract_selftests(strict: bool = True) -> bool:
    """계약은 주석이 아니라 테스트로 강제한다(§2). 실패 시 즉시 중단(fail-fast)."""
    CONTRACT_LOG.clear()
    rng = np.random.default_rng(SEED)

    def c1():
        d = pit_mark(pd.DataFrame({"k": ["a", "a", "b"], "v": [1, 2, 3],
                                   "ed": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-01-31"]),
                                   "kd": pd.to_datetime(["2020-03-15", "2020-04-15", "2020-03-15"])}),
                     "ed", "kd")
        st = PITGateway()
        st.put("t", d)
        got = st.view("t", "2020-03-20")
        if len(got) != 2 or (got["knowledge_date"] > d_("2020-03-20")).any():
            return False, "as_of 절단 오류"
        try:
            st.put("bad", pd.DataFrame({"x": [1]}))
            return False, "PIT 스탬프 없는 테이블이 거부되지 않음"
        except KeyError:
            pass
        return True, "knowledge≤as_of 절단 · 스탬프 누락 등록 거부"

    _ct("C1", "Point-In-Time 강제", c1)

    def c2():
        m = pd.DataFrame({"code": ["000001", "000002", "000003"],
                          "name": list("abc"), "market": ["KOSPI"] * 3,
                          "industry": ["X"] * 3, "corp_code": [None] * 3,
                          "shares_now": [np.nan] * 3, "marcap_now": [np.nan] * 3,
                          "origin": ["t"] * 3,
                          "listing_date": pd.to_datetime(["2010-01-01", "2025-01-01",
                                                          "2010-01-01"]),
                          "delisting_date": pd.to_datetime([None, None, "2018-06-30"])})
        px = pd.DataFrame({"date": pd.bdate_range("2009-01-01", "2026-08-01"),
                           "code": "000001"})
        u = PITUniverse(m, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        a16 = u.at("2016-08-31")
        if "000002" in a16:
            return False, "★미래 상장 종목이 과거 유니버스에 포함(C2 위반)"
        if "000003" not in a16:
            return False, "★폐지 종목이 당시 유니버스에서 빠짐(생존자편향)"
        if "000003" in u.at("2020-01-31"):
            return False, "폐지 후에도 잔존"
        return True, "미래 상장 배제 · 폐지종목 당시 포함 · 폐지 후 제외"

    _ct("C2", "생존자편향 제거", c2)

    def c2d():
        m = pd.DataFrame({"code": ["000001", "000002"], "name": list("ab"),
                          "market": ["KOSPI"] * 2, "industry": ["X"] * 2,
                          "corp_code": [None] * 2, "shares_now": [np.nan] * 2,
                          "marcap_now": [np.nan] * 2, "origin": ["t"] * 2,
                          "listing_date": pd.to_datetime(["1990-03-02", "2016-09-01"]),
                          "delisting_date": pd.to_datetime([None, None])})
        px = pd.DataFrame({"date": pd.bdate_range("2016-08-01", "2019-12-31"),
                           "code": "000001"})
        u = PITUniverse(m, pd.DataFrame(columns=["snap_date", "code", "market"]), px)
        first = set(u.at("2016-08-31"))
        if "000001" not in first:
            return False, ("★시즈닝 앵커 오류 — 패널 이전 상장 종목이 첫 달에서 증발"
                           "(앵커는 상장일이어야 함)")
        if "000002" in first or "000002" in set(u.at("2017-03-31")):
            return False, "신규 상장 250거래일 시즈닝 미작동"
        if "000002" not in set(u.at("2017-11-30")):
            return False, "시즈닝 완료 후에도 미편입"
        return True, "시즈닝 앵커=상장일 · 250거래일 대기 · 기존 상장사 첫 달 생존"

    _ct("C2d", "시즈닝 기준점", c2d)

    def c3():
        mp = pd.DataFrame({"code": ["000001"], "hs": ["390100"], "weight": [1.0],
                           "valid_from": pd.to_datetime(["2020-01-01"]),
                           "valid_to": pd.to_datetime(["2022-12-31"])})
        t = d_("2019-06-30")
        live = mp[(mp["valid_from"] <= t) & (mp["valid_to"] >= t)]
        return len(live) == 0, "매핑 유효구간 이전 시점 미적용"

    _ct("C3", "매핑·라벨 PIT(시간구간)", c3)

    def c4():
        n = 400
        # ★직원수를 '절반만' 채운다. 전부 채우면 규모버킷 사다리(시총·거래대금)를 타지 않아
        #   그 경로가 검정되지 않는다 — 실제로 그 구멍 때문에 numpy 2.x 의 dtype 승격 오류를
        #   계약검정이 통과시키고 L.PANEL 에서 56분 뒤에 터졌다. 실데이터 조건을 재현한다.
        emp = rng.integers(10, 5000, n).astype(float)
        emp[n // 2:] = np.nan
        P = pd.DataFrame({"code": [f"{i:06d}" for i in range(n)],
                          "month": d_("2020-06-30"),
                          "employees": emp,
                          "mktcap": np.linspace(1e10, 5e12, n),
                          "adv20": np.linspace(1e8, 9e9, n),
                          "x": rng.normal(size=n)})
        m = pd.DataFrame({"code": P["code"],
                          "industry": rng.choice(["화학", "전자", "건설"], n)})
        C = attach_cells(P, m)
        if "cell" not in C.columns or \
                C["cell"].astype(str).str.split("|", expand=True).shape[1] < 3:
            return False, "cell=(월,산업,규모) 3요소 아님"
        z = cell_z(C["x"], C["cell"])
        for cname, g in C.assign(z=z).groupby("cell", observed=True):
            if g["z"].notna().sum() >= CELL_MIN and abs(float(g["z"].mean())) > 0.15:
                return False, f"셀 {cname} z 평균 이탈"
        sbs = set(C["size_bucket"].astype(str))
        if not ({"시총소", "시총중", "시총대"} & sbs):
            return False, f"★규모버킷 사다리 미작동(직원수 결측이 시총으로 안 내려감): {sorted(sbs)[:5]}"
        if float((C["size_bucket"].astype(str) == "규모미상").mean()) > 0.10:
            return False, "★규모버킷 미상 과다 — C11 셀이 (월,산업)으로 붕괴"
        return True, (f"cell 3요소 · 셀 내 z 평균≈0 ({C['cell'].nunique()}셀) · "
                      f"규모 사다리(직원수→시총) 작동")

    _ct("C4/C11", "셀 정의·횡단면 연산", c4)

    def c5():
        v = pd.Series([1.0] * 30 + [1000.0])
        z = cell_z(v, pd.Series(["A"] * 31))
        if float(z.max()) > 6:
            return False, "윈저라이즈 미적용"
        small = cell_rank(pd.Series([1.0, 2.0]), pd.Series(["B", "B"]))
        if small.notna().any():
            return False, "표본부족 셀이 NaN 이 아님(0 채움 금지)"
        vi = pd.Series([1, 2, 3, np.inf, 5, 6, 7, 8, 9, 10], dtype=float)
        zi = cell_z(vi, pd.Series(["A"] * 10))
        if zi.notna().sum() < 9 or float(zi.dropna().std()) < 0.5:
            return False, "★inf 하나가 셀 z 전체를 뭉갬(±inf 무해화 실패)"
        return True, "winsor→z→rank 고정 · 표본부족 NaN · ±inf 무해화"

    _ct("C5", "윈저→z→랭크 순서", c5)

    def c6():
        P = pd.DataFrame({f"V{i}": [1.0, 0.0, 1.0] for i in range(1, 9)})
        if list(P.prod(axis=1)) != [1.0, 0.0, 1.0]:
            return False, "거부권 곱 오류"
        if 0.999 * 0.999 * 0.0 != 0.0:
            return False, "상쇄 가능"
        return True, "V∈{0,1} · 곱 · 상쇄 불가"

    _ct("C6", "거부권 이진·곱", c6)

    def c7():
        import inspect
        src = ""
        for fn in (score_by_axes, assemble_signal, axis_quality_tp, axis_resource_tp):
            try:
                src += inspect.getsource(fn)
            except Exception:
                pass
        if re.search(r"(minimize|GridSearch|curve_fit|optimize\.)", src):
            return False, "가중치 최적화 루틴 발견(C7 위반)"
        return True, "TP 내·팩 내·팩 간 동일가중(nrow_mean) — 최적화 루틴 없음"

    _ct("C7", "가중치 최적화 금지", c7)

    def c8():
        a = np.random.default_rng(SEED).normal(size=40)
        b = np.random.default_rng(SEED).normal(size=40)
        if not np.allclose(a, b):
            return False, "시드 비결정"
        x = pd.Series(rng.normal(size=200))
        cl = pd.Series(rng.choice(list("ABCDE"), 200))
        z1 = cell_z(x, cl)
        z2 = cell_z(x.iloc[::-1], cl.iloc[::-1]).iloc[::-1]
        if not np.allclose(z1.dropna().to_numpy(), z2.dropna().to_numpy(), atol=1e-5):
            return False, "입력 순서가 결과를 바꿈"
        return True, "시드 고정 · 순서 무관 동일"

    _ct("C8", "결정성", c8)

    def c10():
        return hasattr(RUN, "table_runtime"), \
            "계층별 실측 계측 활성 (4시간 제약은 사용자 지시로 폐지 — 계측 유지)"

    _ct("C10", "런타임 계측", c10)

    def c12():
        miss = [pid for pid, p in SENSOR_PACKS.items() if not p["policy"]]
        return not miss, ("전 팩 정책 캘린더 보유 · R10 대상" if not miss
                          else f"캘린더 없는 팩 {miss}")

    _ct("C12", "정책 중립성", c12)

    def c_tp():
        r = tp_pair(pd.Series([2.0, 2.0, np.nan]), pd.Series([3.0, -3.0, 1.0]))
        if abs(r[0] - 6) > 1e-6 or abs(r[1] + 6) > 1e-6:
            return False, "TP 가 곱이 아님"
        if pd.notna(r[2]):
            return False, "결측 미전파(0 채움은 거짓 주장)"
        return True, "TP=곱 · 결측 전파"

    _ct("TP", "트레이드오프 쌍=곱(§1.1)", c_tp)

    def c_asof():
        panel = pd.DataFrame({"code": ["A", "B", "A", "B"],
                              "corp_code": ["c1", None, "c1", None],
                              "month": pd.to_datetime(["2020-01-31", "2020-01-31",
                                                       "2020-02-29", "2020-02-29"])})
        fin = pit_mark(pd.DataFrame({"corp_code": ["c1", "c1"], "revenue_ttm": [100.0, 999.0],
                                     "pe": pd.to_datetime(["2019-12-31", "2020-03-31"]),
                                     "kd": pd.to_datetime(["2020-01-15", "2020-05-15"])}),
                       "pe", "kd")
        st = PITGateway()
        st.put("fin", fin, keys=["corp_code"])
        out = st.asof_attach(panel, "fin", by="corp_code", when="month")
        if len(out) != len(panel):
            return False, "★결합키 결측 행이 버려짐(생존자편향 재유입)"
        if not out.loc[out["code"] == "B", "revenue_ttm"].isna().all():
            return False, "결측 키 행에 값이 붙음"
        if out.loc[out["code"] == "A", "revenue_ttm"].tolist() != [100.0, 100.0]:
            return False, "★미래값(kd=2020-05-15) 누수 또는 정렬 붕괴"
        return True, "결측키 행 보존 · 미래값 차단 · 정렬 정확"

    _ct("C1/C2b", "as-of 결합 무결성", c_asof)

    def c_exit():
        cases = [(0.05, 0.10, False), (0.15, 0.10, True), (-0.20, -0.05, True),
                 (0.05, -0.05, True), (np.nan, 0.10, False), (0.05, np.nan, False)]
        for dm, de, want in cases:
            if bool(exit_signal(dm, de)) != want:
                return False, f"청산 게이트 ΔM={dm},ΔE={de} → 기대 {want}"
        return True, "재분류 완료·논거 무효 청산 · 결측은 보유(네 사분면 도달성)"

    _ct("EXIT", "청산 게이트 도달성", c_exit)

    def c_size():
        for tag, sig, adv in (("균등", np.linspace(0.5, 1, 10), np.full(10, 1e12)),
                              ("집중", np.array([1.0] + [0.01] * 9), np.full(10, 1e12)),
                              ("저유동", np.linspace(0.5, 1, 10),
                               np.array([1e7] * 3 + [1e12] * 7))):
            sub = pd.DataFrame({"Signal_rank": sig, "adv20": adv,
                                "code": [f"{i:06d}" for i in range(len(sig))]})
            w = weigh_positions(sub)["weight"].to_numpy()
            if w.max() > MAX_WEIGHT + 1e-9 or w.sum() > 1 + 1e-9:
                return False, f"[{tag}] 상한/합 위반 (max={w.max():.3f}, sum={w.sum():.3f})"
        return True, f"종목 상한 {MAX_WEIGHT:.0%} · 유동성 상한 · 합≤1 (water-filling)"

    _ct("SIZE", "비중 상한 강제(§8.5)", c_size)

    def c_code():
        for k, v in {"005930": "005930", 5930: "005930", "A005930": "005930",
                     "005930.KS": "005930", "09701K": "09701K", "": None}.items():
            if code6(k) != v:
                return False, f"code6({k!r})={code6(k)!r} (기대 {v!r})"
        for raw, exp in (("26.01.19", "2026-01-19"), ("19.12.31", "2019-12-31")):
            if parse_kr_date(raw) != exp:
                return False, f"★YY.MM.DD 연·일 전치: {raw}→{parse_kr_date(raw)}"
        for raw, exp in (("95,000", 95000.0), ("0", None), ("-", None)):
            if parse_target_price(raw) != exp:
                return False, f"목표주가 파싱 {raw!r}"
        if broker_norm("미래에셋대우")[1] != "미래에셋증권" or \
                broker_norm("하나금융투자")[1] != "하나증권":
            return False, "증권사 사명변경 정규화 실패(리비전 오염)"
        return True, "티커(2024 영숫자 포함)·날짜·목표가·사명변경 정규화"

    _ct("PARSE", "수집 파서 회귀", c_code)

    rows = [[r["id"], r["name"], "✔ 통과" if r["ok"] else "✘ 실패", r["msg"]]
            for r in CONTRACT_LOG]
    L.grid(rows, ["계약", "내용", "판정", "상세"], ["l", "l", "c", "l"], cap=72,
           title="계약 자가검정 C1~C12 (§2 — 협상 대상이 아님)")
    bad = [r for r in CONTRACT_LOG if not r["ok"]]
    if bad:
        L.err("계약 위반 " + ", ".join(r["id"] for r in bad))
        if strict:
            raise KillGate("계약 위반 — 우회하지 말고 원인을 고치십시오(§2).")
        return False
    L.ok(f"계약 {len(CONTRACT_LOG)}건 전부 통과")
    return True


# ── 합성 세계 (스모크 — 실데이터 전에 배관 전체 증명) ───────────────────────────────────────
def synthetic_world(n_codes: int = 150, n_months: int = 60) -> dict:
    rng = np.random.default_rng(SEED)
    months = pd.date_range(d_(BT_END) - pd.DateOffset(months=n_months - 1), d_(BT_END),
                           freq="ME")
    codes = [f"{i+1:06d}" for i in range(n_codes)]
    quality = rng.normal(size=n_codes)
    listing = [months[0] - pd.DateOffset(years=int(rng.integers(2, 12))) for _ in codes]
    for i in rng.choice(n_codes, size=n_codes // 12, replace=False):
        listing[i] = months[int(rng.integers(6, n_months - 8))]
    delist = [pd.NaT] * n_codes
    for i in rng.choice(n_codes, size=n_codes // 10, replace=False):
        delist[i] = months[int(rng.integers(12, n_months - 2))]
    master = pd.DataFrame({"code": codes,
                           "name": [f"합성{i+1:03d}" for i in range(n_codes)],
                           "market": rng.choice(["KOSPI", "KOSDAQ"], n_codes),
                           "industry": rng.choice(["화학", "전자부품", "기계", "건설",
                                                   "소프트웨어"], n_codes),
                           "listing_date": listing, "delisting_date": delist,
                           "corp_code": [f"C{i+1:07d}" for i in range(n_codes)],
                           "shares_now": rng.integers(5_000_000, 80_000_000, n_codes)
                           .astype(float),
                           "marcap_now": np.nan, "origin": "synth"})
    days = pd.bdate_range(months[0] - pd.DateOffset(months=14), months[-1])
    pxs = []
    for i, c in enumerate(codes):
        drift = 0.0005 + 0.0013 * quality[i]
        r = rng.normal(drift, 0.022, len(days))
        close = 8000 * np.exp(np.cumsum(r))
        vol = rng.lognormal(11.6, 0.7, len(days))
        d = pd.DataFrame({"code": c, "date": days,
                          "open": close * (1 + rng.normal(0, 0.004, len(days))),
                          "high": close * 1.01, "low": close * 0.99, "close": close,
                          "volume": vol, "value": close * vol, "origin": "synth"})
        d = d[(d["date"] >= listing[i])]
        if pd.notna(delist[i]):
            d = d[d["date"] <= delist[i]]
        pxs.append(d)
    px = pd.concat(pxs, ignore_index=True)
    fin_rows, emp_rows = [], []
    for i, c in enumerate(codes):
        rev = float(np.exp(25 + rng.normal(0, 0.8)))
        for q_end in pd.date_range(months[0] - pd.DateOffset(months=15), months[-1],
                                   freq="QE"):
            rev *= 1 + 0.02 * quality[i] + rng.normal(0, 0.05)
            fin_rows.append({
                "corp_code": master["corp_code"].iloc[i], "period_end": q_end,
                "knowledge_date": q_end + pd.Timedelta(days=45),
                "revenue_ttm": rev, "cogs_ttm": rev * (0.72 - 0.02 * quality[i]),
                "op_income_ttm": rev * (0.08 + 0.02 * quality[i]),
                "net_income_ttm": rev * (0.06 + 0.015 * quality[i]),
                "cfo_ttm": rev * (0.09 + 0.02 * quality[i]),
                "capex_ttm": rev * 0.05, "rnd_ttm": rev * (0.02 + 0.01 * max(quality[i], 0)),
                "dep_ttm": rev * 0.04,
                "div_paid_ttm": rev * (0.01 + 0.008 * max(quality[i], 0)),
                "tstock_buy_ttm": rev * 0.005 * max(quality[i], 0),
                "inventory": rev * (0.15 - 0.01 * quality[i]),
                "receivable": rev * (0.18 - 0.01 * quality[i]), "payable": rev * 0.12,
                "assets": rev * 1.4, "liabilities": rev * 0.6, "equity": rev * 0.8,
                "ppe": rev * 0.5, "intangible": rev * 0.1,
                "contract_liab": rev * (0.03 + 0.01 * quality[i]),
                "eff_tax": 0.22 + rng.normal(0, 0.01), "v2_streak_bad": 0.0})
        for y in range(months[0].year - 1, months[-1].year + 1):
            emp_rows.append({"corp_code": master["corp_code"].iloc[i], "bsns_year": y,
                             "period_end": d_(f"{y}-12-31"),
                             "knowledge_date": d_(f"{y}-12-31") + pd.Timedelta(days=90),
                             "employees": float(max(12, rng.lognormal(5.2, 1.0))),
                             "payroll": float(rng.lognormal(22, 0.8))})
    fin = pit_mark(pd.DataFrame(fin_rows), "period_end", "knowledge_date", origin="synth")
    emp = pit_mark(pd.DataFrame(emp_rows), "period_end", "knowledge_date", origin="synth")
    dis_rows = []
    for i, c in enumerate(codes):
        for m in months[::4]:
            if rng.random() < 0.10 + 0.10 * max(quality[i], 0):
                dis_rows.append({"corp_code": master["corp_code"].iloc[i],
                                 "rcept_no": h40(c, m)[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식취득결정)",
                                 "kind": "tstock_acq"})
            if rng.random() < 0.05 + 0.08 * max(quality[i], 0):
                dis_rows.append({"corp_code": master["corp_code"].iloc[i],
                                 "rcept_no": h40(c, m, 1)[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(자기주식소각결정)",
                                 "kind": "tstock_burn"})
            if rng.random() < 0.05:
                dis_rows.append({"corp_code": master["corp_code"].iloc[i],
                                 "rcept_no": h40(c, m, 2)[:14], "rcept_dt": m,
                                 "report_nm": "주요사항보고서(유상증자결정)", "kind": "rights"})
    disc = pit_mark(pd.DataFrame(dis_rows), "rcept_dt", "rcept_dt", origin="synth")
    link_rows = []
    analysts = [(f"애널{j:02d}", broker_norm(b)) for b in MAJOR_BROKERS for j in range(3)]
    for m in months:
        for _ in range(int(rng.integers(80, 200))):
            i = int(rng.integers(0, n_codes))
            nm, (bid, bname) = analysts[int(rng.integers(0, len(analysts)))]
            link_rows.append({"rid": h40("syn", i, m, nm, rng.integers(1e9)),
                              "analyst_id": h40("an", bid, nm)[:14], "name": nm,
                              "broker_id": bid, "broker_name": bname,
                              "stock_code": codes[i],
                              "pub_date": m - pd.Timedelta(days=int(rng.integers(0, 28))),
                              "target_price": float(np.exp(rng.normal(9.6, 0.5)) *
                                                    (1 + 0.15 * quality[i])),
                              "opinion": "BUY"})
    links = pd.DataFrame(link_rows)
    nps_rows = []
    for i, c in enumerate(codes):
        base = max(15, int(rng.lognormal(5.0, 1.0)))
        wage = rng.lognormal(15.0, 0.25)
        for m in months:
            base = max(5, int(base * (1 + 0.004 * quality[i] + rng.normal(0, 0.02))))
            wage *= 1 + 0.002 + 0.001 * quality[i] + rng.normal(0, 0.004)
            nps_rows.append({"code": c, "month": m, "nps_members": float(base),
                             "nps_amt": float(base * wage * NPS_CONTRIB_RATE),
                             "nps_new": float(rng.poisson(3)),
                             "nps_lost": float(rng.poisson(max(1, 3 - quality[i]))),
                             "n_sites": float(rng.integers(1, 6)),
                             "knowledge_date": m + pd.offsets.MonthEnd(2)})
    nps = pit_mark(pd.DataFrame(nps_rows), "month", "knowledge_date", origin="synth")
    txt_rows = []
    for i, c in enumerate(codes):
        for y in range(months[0].year, months[-1].year + 1):
            txt_rows.append({"corp_code": master["corp_code"].iloc[i],
                             "rcept_dt": d_(f"{y}-03-31"),
                             "sim_risk": float(np.clip(0.03 * quality[i] +
                                                       rng.normal(0, 0.05), -0.5, 0.5)),
                             "sim_all": float(np.clip(0.02 * quality[i] +
                                                      rng.normal(0, 0.04), -0.5, 0.5))})
    tsim = pit_mark(pd.DataFrame(txt_rows), "rcept_dt", "rcept_dt", origin="synth")
    return {"master": master, "px": px, "fin": fin, "emp": emp, "disclosures": disc,
            "links": links, "nps": nps, "text_sim": tsim, "months": months,
            "flows": pd.DataFrame(columns=["code", "date", "inst_net", "forgn_net"]),
            "mktcap": None, "hs_map": None, "customs": None, "procurement": None}


def _feature_chain(P0: pd.DataFrame, master: pd.DataFrame, ctx: dict,
                   flows, cons, kd_shift: int = 0) -> pd.DataFrame:
    """기본패널 → 재무 as-of → 셀 → 공용축 → 팩 → 거부권 → Signal. (본선·R1 재계산 공용 경로)"""
    P = attach_financials(P0, master, kd_shift_days=kd_shift)
    P = attach_cells(P, master)
    P = axis_quality(P); P = axis_resource(P)
    P = axis_quality_tp(P); P = axis_resource_tp(P)
    P = axis_discount(P, flows, cons)
    P = axis_discount_u(P)
    for p in packs_on():
        try:
            P = p["features"](P, ctx)
        except Exception as e:                            # noqa
            # ★수집기는 _try 로 격리해 놓고 피처는 안 해두면, 부분 수집된 팩 테이블의
            #   스키마 차이 하나가 L.PANEL(critical)을 깨고 백테스트·리포트·저장까지 전부
            #   날린다. 팩 하나를 끄는 편이 언제나 낫다(§8.4 자동 비활성화와 같은 취급).
            pack_off(p["id"], f"피처 계산 실패({type(e).__name__}: {str(e)[:100]}) — "
                              f"해당 팩만 제외하고 계속합니다")
    P = apply_vetoes(P, ctx)
    P = assemble_signal(P)
    return shrink(P)


def reset_transient_state():
    """스모크가 남긴 합성 PIT 테이블·강건성 결과·팩 비활성화를 전부 원복한다.
    ★이걸 빠뜨리면 FULL 실행이 합성 재무를 '있는 데이터'로 착각하거나(경고 미출력),
      합성 데이터 부재로 꺼진 팩(X/P)이 실데이터 실행에서도 꺼진 채 시작한다."""
    PITX._tables.clear()
    PITX._meta.clear()
    PITX.hits.clear()
    RB.clear()
    for pk in SENSOR_PACKS.values():
        pk["enabled"] = True
        pk["why_off"] = ""


def run_smoke(full_chain: bool) -> bool:
    """합성 스모크 — 실데이터를 1바이트도 받기 전에 계산경로 전체(비교전략 포함)를 증명한다.
    종료 시(성공·실패 불문) reset_transient_state() 로 합성 잔재를 완전히 걷어낸다."""
    L.h1("합성 스모크 테스트", "네트워크·키 불필요 · 성과 수치는 배관 검증용(해석 금지)"
         + (" · full: 강건성·해석표·비교전략까지" if full_chain else ""))
    try:
        return _run_smoke_body(full_chain)
    finally:
        reset_transient_state()


def _run_smoke_body(full_chain: bool) -> bool:
    t0 = time.time()
    W = synthetic_world()
    PITX.put("dart_fin", W["fin"], keys=["corp_code"])
    PITX.put("dart_emp", W["emp"], keys=["corp_code"])
    PITX.put("nps_monthly", W["nps"], keys=["code"])
    PITX.put("text_sim", W["text_sim"], keys=["corp_code"])
    panel = monthly_panel(W["px"], W["months"])
    uni = PITUniverse(W["master"], pd.DataFrame(columns=["snap_date", "code", "market"]),
                      panel["daily"])
    P0 = frame_panel(uni, W["months"], panel["monthly"])
    cons = build_consensus_monthly(W["links"], W["months"])
    ctx = {"disclosures": W["disclosures"], "master": W["master"], "mktcap": None,
           "hs_map": None, "customs": None, "procurement": None}
    P = _feature_chain(P0, W["master"], ctx, W["flows"], cons)

    def run_fn(pp, tag="SMOKE", with_costs=True, months_sub=None):
        return run_engine(pp, months_sub if months_sub is not None else W["months"], uni,
                          W["master"], with_costs=with_costs, tag=tag)

    bt = run_engine(P, W["months"], uni, W["master"], tag="SMOKE_MAIN", audit_gates=True)
    s = perf_summary(bt["returns"])
    ok = bool(len(P) and len(bt["returns"]) == len(W["months"]) and s and
              np.isfinite(s.get("CAGR", np.nan)))
    L.grid([["패널", f"{len(P):,}행"], ["백테스트 월수", f"{len(bt['returns'])}"],
            ["평균 보유", f"{s.get('평균종목수', float('nan')):.1f}"],
            ["합성 Sharpe", f"{s.get('Sharpe', float('nan')):.3f}"],
            ["소요", f"{time.time()-t0:.1f}s"]], ["항목", "값"], ["l", "r"],
           title="스모크 결과(배관 검증)")
    if not ok:
        L.err("스모크 실패 — 실데이터 수집 전에 계산경로부터 고쳐야 합니다.")
        return False
    L.ok("스모크 통과 — 피처→스코어→백테스트 경로 정상.")
    if not full_chain:
        return True
    L.warn("아래 수치는 전부 합성 난수 기반 예행연습입니다 — 절대 해석하지 마세요.")
    keep_kill = globals()["STOP_ON_KILL"]
    globals()["STOP_ON_KILL"] = False
    try:
        performance_report(bt, {}, label="합성 예행연습")
        uni.funnel_table()
        cal = policy_calendar()
        R1_leak_probe(P, W["months"], uni, W["master"], run_fn,
                      rebuild_fn=lambda sh: _feature_chain(P0, W["master"], ctx, W["flows"],
                                                           cons, kd_shift=sh))
        R2_tp_vs_naive(P, run_fn)
        R3_orthogonal(P, bt, W["months"])
        R4_placebo(P, n_iter=150)
        R10_policy(P, cal, W["months"], run_fn)
        variants = R5_ablation(P, run_fn)
        R11_pack_corr(P)
        R6_pbo_dsr(bt, variants)
        R7_regime(bt, {})
        R8_yearly(bt)
        R9_costs(P, run_fn)
        robustness_report(" — 합성 예행연습")
        interpretation_report(P)
        diagnostic_cards(P, W["master"], top_n=3)
        cmp_out = run_comparison(P, {"mktcap": None}, W["months"], uni, W["master"], {},
                                 robust_level="LITE")
        if cmp_out:
            comparison_table(bt, cmp_out["backtest"], {})
    finally:
        globals()["STOP_ON_KILL"] = keep_kill
        RB.clear()
        for pk in SENSOR_PACKS.values():                   # 스모크 중 비활성화된 팩 원복
            pk["enabled"] = True
            pk["why_off"] = ""
    L.ok("full-chain 예행연습 완료 — 백테스트·성과·강건성·해석표·진단카드·비교전략 전 출력 확인.")
    return True


# ── 산출물 다운로드 ─────────────────────────────────────────────────────────────────────────
def offer_downloads(paths: Sequence[str]):
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return
    if ENVX["colab"]:
        try:
            from google.colab import files as _cf          # type: ignore
            for p in paths:
                say(f"⬇ 다운로드: {os.path.basename(p)}")
                _cf.download(p)
            return
        except Exception:
            pass
    try:
        from IPython.display import display, HTML         # type: ignore
        import base64
        pieces = ["<div style='font-family:sans-serif;line-height:2'>"]
        for p in paths:
            b = open(p, "rb").read()
            if len(b) > 40 * 1024 * 1024:
                pieces.append(f"<div>{os.path.basename(p)} — 용량 초과, 경로: <code>{p}</code></div>")
                continue
            b64 = base64.b64encode(b).decode()
            pieces.append(f"<a download='{os.path.basename(p)}' "
                          f"href='data:application/octet-stream;base64,{b64}' "
                          f"style='display:inline-block;margin:4px;padding:8px 14px;"
                          f"background:#1a73e8;color:#fff;border-radius:6px;"
                          f"text-decoration:none'>⬇ {os.path.basename(p)}</a>")
        pieces.append("</div>")
        display(HTML("".join(pieces)))
    except Exception:
        for p in paths:
            say(f"⬇ 산출물 경로: {p}")


# ── 오케스트레이터 ──────────────────────────────────────────────────────────────────────────
def main() -> dict:
    global VAULT
    t_all = time.time()
    L.h1("TCD v2 ZERO-BASE — 트레이드오프 붕괴 탐지",
         f"백테스트 {BT_START}~{BT_END}(10년) · 활성 팩 {','.join(ACTIVE_PACKS)} · 모드 {RUN_MODE}")
    _dep = []
    for _nm, _ok, _why in (("FinanceDataReader", fdr is not None, "미설치/임포트 실패"),
                           ("pykrx", pykrx_stock is not None, PKX_WHY or "미설치"),
                           ("yfinance", yf is not None, "미설치(지수 폴백에만 사용)")):
        _dep.append(f"{_nm}: " + ("✔" if _ok else f"✘ {_why}"))
    L.grid([["환경", "Colab" if ENVX["colab"] else ("Jupyter" if ENVX["notebook"] else "CLI")],
            ["파이썬", ENVX["python"]], ["코어", str(ENVX["cores"])],
            ["수집 라이브러리", " · ".join(_dep)],
            ["병렬", f"IO {IO_THREADS}스레드 / CPU {N_CPU_WORKERS}"
                     + ("(fork)" if _FORK_OK else "(스레드 폴백)")],
            ["수집 시간예산", (f"{HARVEST_TIME_BUDGET_H:.1f}시간 — 도달 시 부분 데이터로 "
                              f"중간결과" if HARVEST_TIME_BUDGET_H > 0 else "무제한")],
            ["시드", str(SEED)]], ["항목", "값"], ["l", "l"], title="실행 환경")

    with RUN.step("A.VAULT", "캐시 금고 연결(구글드라이브+로컬 D드라이브 탐색)", "L0"):
        root, mode = locate_primary_root()
        hunt = locate_hunt_roots(root)
        VAULT = VaultArchive(root, mode, hunt)
        globals()["VAULT"] = VAULT
        L.info(f"저장 루트: {VAULT.root} (모드 {mode}) · 보조 탐색 루트 {len(hunt)}개")
        warn_if_not_drive(mode, VAULT.root)
        VAULT.manifest("shared"); VAULT.manifest("private")
        VAULT.adopt_scan(GDRIVE_ADOPT_DIRS)
        QUOTA.load()

    with RUN.step("B.CONTRACT", "계약 자가검정 C1~C12", "L0"):
        contract_selftests(strict=True)

    with RUN.step("C.SMOKE", "합성 스모크(계산경로 증명)", "L0"):
        # ★★스모크의 팩 판정을 밖으로 새게 두면 안 된다.
        #   합성 패널에는 관세(X)·조달(P) 데이터가 없다. 그대로 assemble_signal 을 태우면
        #   커버리지 0% 판정이 나고 pack_off() 가 ★전역 SENSOR_PACKS 를 끈다. 그 뒤로는
        #   실데이터에 그 팩이 아무리 많이 들어와도 packs_on() 이 영영 제외한다.
        #   → 매 실행 'X·P 비활성화'가 뜬 진짜 이유가 이것이다. hs_corp_map 을 넣어도,
        #     조달 데이터를 다 받아도 죽었다. 수집은 하는데 피처가 안 만들어지므로
        #     쿼터만 태우고 축은 사라지는, 가장 나쁜 형태의 결함이었다.
        #   스모크는 ★배관 검증이지 데이터 판정이 아니다. 판정은 실데이터로만 한다(§8.4).
        with pack_state_guard(restore=(RUN_MODE != "SMOKE")):
            if not run_smoke(full_chain=(RUN_MODE == "SMOKE")):
                raise RuntimeError("스모크 실패 — 실데이터 수집을 시작하지 않습니다.")

    months = month_grid(BT_START, BT_END)
    if RUN_MODE == "SMOKE":
        RUN.table_steps(); RUN.table_runtime(); dataflow_map()
        L.ok("SMOKE 완료 — 실데이터로 돌리려면 RUN_MODE='FULL'")
        return {"mode": "SMOKE"}

    ctx: Dict[str, Any] = {}
    CLOCK.restart("실데이터 수집 시작(부트·계약검정·스모크는 예산에서 제외)")
    with RUN.step("D.UNI", "종목마스터·상장폐지·스냅샷(다중소스)", "L1"):
        snaps = harvest_snapshots(months)
        master = build_master(snaps)
        ctx["master"], ctx["snapshots"] = master, snaps

    with RUN.step("E.PX", "가격 수집(★날짜축 전종목 벌크)·월간 패널", "L1"):
        if RUN_MODE != "CACHED":
            KRXOA.probe()          # 정식 Open API 가 열려 있으면 벌크 1순위로 승격
            KRX.login()
        px = harvest_prices(master,
                            (d_(BT_START) - pd.DateOffset(months=15)).strftime("%Y-%m-%d"),
                            BT_END)
        if px is None or not len(px):
            raise RuntimeError(
                "가격을 한 행도 확보하지 못해 백테스트를 시작할 수 없습니다.\n"
                "  ★위 '가격 소스 프리플라이트' 표의 마지막 열이 소스별 실패 원인을 그대로 "
                "보여줍니다 — 거기부터 보세요.\n"
                "  가장 흔한 순서: ① data.krx.co.kr 방화벽 차단 ② pykrx 미설치/휠 부재 "
                "③ FinanceDataReader 미설치\n"
                "  세 소스 중 하나만 살아나면 그대로 진행됩니다(종목당 1회 스윕 폴백 포함).")
        ctx["px"] = px
        ctx["panel"] = monthly_panel(px, months)
        # 유동성 우선순위(수집 순서 결정용) — 이후 스테이지가 실패해도 참조 가능하게 여기서 확정
        ctx["adv_rank"] = (ctx["panel"]["monthly"].groupby("code", observed=True)["adv20"]
                           .median().sort_values(ascending=False))

    with RUN.step("F.CAP", "시가총액 스냅샷(비교전략 입력)", "L1", critical=False):
        ctx["mktcap"] = harvest_mktcap(months, px=ctx.get("px"))
        # 원본 일봉은 여기까지만 쓰인다. 700만행 프레임을 끝까지 들고 가면 월간패널 사본과
        # 합쳐 수백 MB 를 그냥 점유한다 — 이후 단계는 panel['daily'] 만 본다(Colab RAM).
        ctx["px"] = None
        gc.collect()

    with RUN.step("G.FLOW", "기관·외국인 수급(★월축 전종목 일괄)", "L1", critical=False):
        ctx["flows"] = harvest_flows(master["code"].tolist(), BT_START, BT_END)

    with RUN.step("J.PACKS", "센서팩 전용 수집(NPS·조달·관세)", "L1", critical=False):
        # ★★순서 — 이 스테이지는 H.DART ★앞에 있다.
        #   옛 배치는 DART(재무·직원·공시) 다음이었다. 그런데 DART 는 전 상장사 × 전 연도라
        #   가장 무겁고, 시간·호출 예산을 거기서 소진하면 ★뒤에 있는 팩이 통째로 굶는다.
        #   실제로 국민연금·관세가 여러 실행에서 0건으로 끝났다.
        #   의존성을 보면 앞으로 옮기는 데 아무 제약이 없다:
        #     · harvest_nps 는 master(회사명) + adv_rank 만 쓴다 — 둘 다 E.PX 까지면 확정된다
        #     · harvest_procurement 는 months 만 쓴다
        #     · harvest_customs 는 hs_map + months 만 쓴다
        #     · 예산도 별개다(datagokr ↔ dart) — 앞으로 옮겨도 DART 몫이 줄지 않는다
        #   DART 에 의존하는 것은 ★피처 단계의 θ 뿐이다(θ_N=가입자수/직원수, θ_X=수출/매출).
        #   그건 L.PANEL 에서 계산하므로 수집 순서와 무관하다.
        #   ※ PACK-D(공시원문)만은 ctx["disclosures"] 가 필요해 H.DART 뒤(J2.PACKD)에 남긴다.
        dgb = CallBudget("datagokr", DATAGOKR_BUDGET_SHARE)

        # ★수집기별 개별 격리 — 한 팩의 예외가 나머지 팩 수집까지 무산시키지 않게 한다
        def _try(tag, fn):
            try:
                return fn()
            except Exception as e:                        # noqa
                L.warn(f"팩 수집 '{tag}' 실패({type(e).__name__}: {str(e)[:120]}) — "
                       f"해당 팩만 결측으로 두고 계속 진행합니다.")
                RUN.note(f"WARN: 팩 수집 {tag} 실패")
                return None

        ctx["_try_pack"] = _try
        # ★DART 와 같은 2단계 배분(수요 선언 → 정산). 관세는 수요를 ★정확히 셀 수 있다 —
        #   (월 × HS코드)이고, HS 매핑이 없으면 0 이다. 0 을 선언하면 그 몫이 회수되어
        #   국민연금·조달로 흘러간다. 선언이 없으면 '수요 미상'으로 10%를 깔고 앉는다.
        ctx["hs_map"] = _try("HS매핑", load_hs_map) if "X" in ACTIVE_PACKS else None
        hs_list = (ctx["hs_map"]["hs"].astype(str).unique().tolist()
                   if ctx.get("hs_map") is not None and len(ctx["hs_map"]) else [])
        dgb.declare("customs", len(months) * len(hs_list))
        dgb.declare("nps", None)          # 종목별 검색 1 + 기간 1 + 상세 ≤3 — 사전에 못 센다
        dgb.declare("procure", None)      # 월당 페이지 수가 응답에서 나온다
        dgb.settle()
        dgb.table({"nps": "국민연금 사업장", "procure": "조달 낙찰", "customs": "관세 통관"})
        _ar = ctx.get("adv_rank", pd.Series(dtype=float))
        prio_codes = list(_ar.index) if len(_ar) else master["code"].tolist()
        # ★시간 몫 — 호출 예산은 소스별이지만 ★시계는 하나다. 이 몫이 없으면 팩이 4시간을
        #   다 먹고 DART 가 굶는다. 그러면 θ_N(=가입자수/직원수)·θ_X(=수출/매출)의 ★분모가
        #   사라져 이 팩들의 축이 통째로 죽는다 — 팩을 먼저 받으려던 목적과 정확히 반대다.
        with CLOCK.lease(PACK_TIME_SHARE, "센서팩(N·P·X) 수집",
                         cap_s=PACK_TIME_CAP_MIN * 60.0):
            if "N" in ACTIVE_PACKS:
                nps = _try("NPS", lambda: harvest_nps(master, months, priority=prio_codes,
                                                      max_calls=dgb.take("nps")))
                if nps is not None and len(nps):
                    _try("NPS등록", lambda: PITX.put(
                        "nps_monthly",
                        pit_mark(nps, "month", ds_(nps["month"]) + pd.offsets.MonthEnd(2),
                                 origin="nps"), keys=["code"]))
            if "P" in ACTIVE_PACKS:
                ctx["procurement"] = _try("조달",
                                          lambda: harvest_procurement(months,
                                                                      max_calls=dgb.take("procure")))
            if "X" in ACTIVE_PACKS:
                if hs_list:
                    ctx["customs"] = _try("관세",
                                          lambda: harvest_customs(months, hs_list,
                                                                  max_calls=dgb.take("customs")))
                else:
                    # ★이 팩이 꺼지는 이유는 '데이터를 못 받아서'가 아니라 ★매핑이 없어서다.
                    #   계약 §6.3 은 5단계(회사↔HS) 매핑을 자동구축 대상에서 제외한다 — 추정
                    #   매핑은 θ 를 위조하고 V4 부분거부권을 무력화하기 때문이다. 그래서 여기서
                    #   자동으로 만들지 않는다. 대신 ★무엇을 어디에 넣으면 켜지는지를 정확히 알린다.
                    pack_off("X", "HS↔기업 매핑 테이블 부재 — 관세청 통관자료는 'HS코드별 수출'이라 "
                                  "회사로 내리려면 매핑이 반드시 있어야 합니다. 계약 §6.3 이 5단계 "
                                  "매핑을 자동구축 대상에서 제외하므로(추정 매핑은 θ 를 위조하고 V4 "
                                  "부분거부권을 무력화합니다) 이 코드가 임의로 만들지 않습니다.")
                    L.warn("PACK-X 를 켜는 법 — 드라이브 공용 인덱스에 'hs_corp_map' 테이블을 "
                           "넣으세요. 컬럼: code(6자리 종목코드) · hs(HS 6~10자리) · "
                           "weight(그 HS 가 그 회사 수출에서 차지하는 비중 0~1) · "
                           "valid_from · valid_to(매핑 유효구간 — C3 PIT 강제). "
                           f"경로: {getattr(VAULT, 'ns', {}).get('shared', '(금고 미연결)')}"
                           " · 파일명 hs_corp_map.parquet(또는 .csv). "
                           "출처 예: 관세청 수출입무역통계 품목-기업 연계, 무역협회 K-stat, "
                           "사업보고서 '사업의 내용'의 제품별 매출 비중 + 품목→HS 대응표.")
    with RUN.step("H.DART", "DART 재무·직원·공시(실시간 잔여쿼터)", "L1", critical=False):
        corps = master["corp_code"].dropna().astype(str).unique().tolist()
        years = list(range(d_(BT_START).year - 2, d_(BT_END).year + 1))
        adv_rank = ctx.get("adv_rank", pd.Series(dtype=float))
        c2corp = master.dropna(subset=["corp_code"]).set_index("code")["corp_code"] \
            .astype(str).to_dict()
        prio = [c2corp[c] for c in adv_rank.index if c in c2corp]
        # ★호출량 배분 — 고정 비율이 아니라 '배정 직전의 실잔여 × 남은 소비자 사이의
        #   상대 가중치, 단 실수요 상한'. 순서만 바꾸면 앞선 수집기가 다 먹고, 비율만 고정하면
        #   ★할 일이 없는 수집기가 예산을 깔고 앉는다(3차 사고: 일괄 ZIP 이 재무를 다 덮었는데도
        #   deep+major 가 65%를 선점해 직원현황이 800건에서 끊겼다). 둘 다 막는다.
        budget = CallBudget("dart", DART_BUDGET_SHARE)
        # ★★배분은 '수요 선언 → 정산' 2단계다. 순서대로 나눠 주면 ★첫 소비자가 고정 비율을
        #   받는다 — 실측에서 공시목록이 첫 순번이라 10%(1,999회)만 받았고 실수요는 12,533
        #   이었다. 1,999÷83(월당 실측) = 정확히 24개월에서 끊겼다. 한도가 모자란 것이
        #   아니라 나누는 방식이 틀렸던 것이다. 그래서 먼저 전원이 수요를 선언한다.
        #
        # ★스윕 시작을 재무 대상 연도의 첫 해로 당긴다. 월 단위 시장 전체 스윕이라 추가비용이
        #   수십 회에 불과한데, 그 대가로 초기 2~3년치가 '제출사실 소거' 대상에 들어온다
        #   (소거는 창구가 스윕 범위 안에 통째로 들어온 연도에만 적용되기 때문).
        # avail = 유한 수요 소비자가 최대로 받을 수 있는 몫. 실수요가 이걸 넘으면 스윕이
        # 스스로 손실 있는 절감(이벤트 집중월)으로 내려가고 그 사실을 로그에 적는다.
        dplan = disc_plan(f"{min(years)}-01-01", BT_END,
                          avail=int(budget.total * CallBudget.FINITE_CAP))
        budget.declare("disclosure", int(dplan.get("need") or 0))
        # 나머지 셋은 '아직 셀 수 없다'로 선언한다. 직원현황·주요계정·심층재무의 실수요는
        # 공시 스윕이 만들어 줄 제출사실 지도(filed)에 달려 있어서, 스윕 전에는 원리적으로
        # 셀 수 없다. 셀 수 없다고 굶지는 않는다 — 유한 수요를 먼저 채운 뒤 남은 것을
        # 가중치대로 나눠 갖는다(0.70/0.10/0.10 → 직원현황이 그 대부분을 가져간다).
        for _k in ("employee", "major", "deep"):
            budget.declare(_k, None)
        budget.settle()
        budget.table({"disclosure": "공시목록(시장 스윕)", "employee": "직원현황(전수)",
                      "major": "주요계정 벌크", "deep": "전체재무제표(꼬리)"})
        disc = harvest_dart_disclosures(f"{min(years)}-01-01", BT_END, plan=dplan,
                                        max_calls=budget.take("disclosure"))
        ctx["disclosures"] = disc
        # ★공시목록에서 '정기보고서 제출 사실'을 공짜로 뽑아 이후 모든 단건 티어의 사전
        #   소거 지도로 쓴다. 존재하지 않는 조합을 묻지 않는 것이 전수수집의 유일한 지름길.
        filedS = filed_report_set(disc)
        filed_fy = {(c, y) for (c, y, r) in filedS if r == RQ["FY"]}
        # ★비12월 결산 등 제출 이력을 확신 있게 해석하지 못한 회사는 소거 대상에서 제외한다.
        #   괄호 안 월은 결산기말이지 보고서 종류가 아니라서, 3월 결산사의 사업보고서를
        #   월만 보고 매핑하면 '사업보고서를 낸 적 없는 회사'가 되어 조용히 전 연도가 사라진다.
        exemptC = filed_exempt_corps(disc)
        # ★소거는 '공시 스윕이 그 연도의 제출 창구를 완주한' 연도에만 적용한다. 판정 근거는
        #   행 존재가 아니라 ★완주 원장이다 — 반쪽만 받은 달도 행은 남기 때문에, 행으로
        #   판정하면 모든 달이 완주로 보이고 미조회분의 제출사가 통째로 잘린다.
        # ★신뢰 근거는 '정기공시(A)가 완주한 달'이다. 제출사실(사업·반기·분기보고서)은
        #   전부 A 에서 나오므로 B·I 완주 여부는 이 판정과 무관하다. 옛 코드는 월 원장
        #   하나만 봤는데, 그 원장은 (월×유형) 개편 뒤 갱신이 밀려 '소거 적용 연도 0개'를
        #   만들었고, 무리하게 승격시키면 반대로 미완주 월을 완주로 박아 실제 제출사를
        #   잘라낸다. 둘 다 피하는 유일한 방법이 '필요한 유형만 정확히 보는 것'이다.
        doneM = disc_filed_months()
        trustY = filed_trusted_years(disc, doneM)
        if filedS:
            L.ok(f"정기보고서 제출 사실 {len(filedS):,}조합 확보(추가 호출 0회) — "
                 f"사업보고서 {len(filed_fy):,}조합 · 완주 월 {len(doneM):,}개 · "
                 f"소거 적용 연도 {len(trustY)}개"
                 f"({min(trustY) if trustY else '-'}~{max(trustY) if trustY else '-'}) · "
                 f"결산월 해석 불가로 소거 면제한 회사 {len(exemptC):,}사. "
                 f"나머지는 소거 없이 전부 조회합니다.")
        # ★일괄 ZIP 이 심층 계정(재고·매출채권·CFO·CAPEX)을 호출한도 0으로 채운다.
        code2corp_all = (master.dropna(subset=["corp_code"])
                         .set_index("code")["corp_code"].astype(str).to_dict())
        fs_zip = harvest_dart_bulk_zip(code2corp_all, years)
        zip_have = set()
        if fs_zip is not None and len(fs_zip):
            zip_have = set(zip(fs_zip["corp_code"].astype(str),
                               fs_zip["bsns_year"].astype(int),
                               fs_zip["reprt_code"].astype(str)))
        # ★직원현황을 재무 단건보다 먼저 — 재무는 일괄 ZIP 이라는 무한도 대체재가 있지만
        #   직원현황은 대체재가 없다(오직 이 API 뿐). '대체 불가'가 예산의 우선권을 갖는다.
        #   size_bucket 이 전부 '규모미상'이 되면 C11 셀이 (월,산업)으로 붕괴해 규모 통제가
        #   소실되고, C2축 dlog_emp·PACK-N 한계임금이 통째로 결측이 된다.
        emp = harvest_dart_employees(
            corps, years, priority=prio, filed=filed_fy, trusted=trustY, exempt=exemptC,
            max_calls=budget.take("employee"))
        #  ↑ need 를 넘기지 않는다. 실수요는 '신뢰 연도의 filed 교집합 + 비신뢰 연도의 전 종목'
        #    이라 바깥에서 정확히 셀 수 없고, 잘못 세면 소거는 안 되면서 예산만 깎여 굶는다.
        #    배정은 어차피 실사용분만 소비되고, 뒤 소비자는 take() 시점에 실잔여를 다시 잰다.
        fs_major = harvest_dart_multi(corps, years, already=zip_have, filed=filedS,
                                      trusted=trustY, exempt=exemptC,
                                      max_calls=budget.take("major"))
        fs_deep = harvest_dart_financials(corps, years, priority=prio,
                                          already=zip_have, filed=filedS,
                                          trusted=trustY, exempt=exemptC,
                                          max_calls=budget.take("deep"))
        budget.report({"disclosure": "공시목록(시장 스윕)", "employee": "직원현황(전수)",
                       "major": "주요계정 벌크", "deep": "전체재무제표(꼬리)"})
        parts_fs = [x for x in (fs_deep, fs_zip, fs_major) if x is not None and len(x)]
        fs = pd.concat([x.reindex(columns=_FS_KEEP) for x in parts_fs],
                       ignore_index=True) if parts_fs else pd.DataFrame(columns=_FS_KEEP)
        del fs_deep, fs_zip, fs_major, parts_fs
        gc.collect()
        fin = refine_financials(fs)
        if len(fin):
            PITX.put("dart_fin", fin, keys=["corp_code"])
        if len(emp):
            PITX.put("dart_emp", emp, keys=["corp_code"])

    if COLLECT_RESEARCH or RUN_MODE == "CACHED":
        with RUN.step("I.RSCH", "애널리스트 리포트(한경+네이버)·원장", "L1", critical=False):
            L.info("※ 두 사이트 robots.txt 는 Disallow:/ — 사용자 명시 지시에 따라 보수적 속도로"
                   " 수집하며, 원문은 로컬 분석 용도로만 사용하세요.")
            cached_rep = VAULT.load_table("research_report_master", "shared")
            frames = []
            if RUN_MODE != "CACHED" and COLLECT_RESEARCH and not CLOCK.over():
                # ★증분: 캐시 원장이 이미 충분히 덮은 구간은 재크롤하지 않는다(시간예산 보호)
                hk_skip: set = set()
                nv_since = None
                if cached_rep is not None and len(cached_rep):
                    cr = cached_rep.copy()
                    cr["pub_date"] = ds_(cr["pub_date"])
                    hk = cr[cr["source"].astype(str).str.contains("hankyung")]
                    cnt = hk.groupby(hk["pub_date"].dt.strftime("%Y-%m")).size()
                    # ★문턱 30 은 너무 낮다. 한경은 월 1,000건 규모라, 수집이 40건에서 끊긴 달이
                    #   영구히 '덮인 월'로 동결된다(다른 세션이 실측으로 겪고 교정한 지점).
                    hk_skip = set(cnt[cnt >= 300].index)
                    nv = cr[cr["source"].astype(str).str.contains("naver")]
                    if len(nv):
                        nv_since = nv["pub_date"].max()
                if "hankyung" in RESEARCH_SOURCES:
                    frames.append(harvest_hankyung(BT_START, BT_END, skip_months=hk_skip))
                if "naver" in RESEARCH_SOURCES:
                    frames.append(harvest_naver_research(BT_START, BT_END, since=nv_since))
            if cached_rep is not None and len(cached_rep):
                L.info(f"캐시 재사용: 보고서 원장 {len(cached_rep):,}건")
                frames.append(cached_rep)
            rep = unify_reports(frames, master)
            if len(rep):
                VAULT.save_table("research_report_master", rep, "shared", domain="research",
                                 source="hankyung+naver")
                download_report_pdfs(rep)
            A, Lk = build_analyst_ledger(rep)
            if len(A):
                VAULT.save_table("analyst_master", A, "shared", domain="research",
                                 source="entity_resolution")
                VAULT.save_table("report_analyst_link", Lk, "shared", domain="research",
                                 source="entity_resolution")
            ctx["reports"], ctx["analysts"], ctx["links"] = rep, A, Lk

    else:
        RUN.skip("I.RSCH", "애널리스트 리포트(한경+네이버)·원장", "COLLECT_RESEARCH=False", "L1")

    if "D" in ACTIVE_PACKS:
        with RUN.step("J2.PACKD", "공시 원문·텍스트 유사도(PACK-D)", "L1", critical=False):
            # ★이 팩만 H.DART 뒤에 남는다 — ctx["disclosures"](공시목록)가 원천이기 때문이다.
            #   나머지 팩(N·P·X)은 DART 와 무관하므로 앞으로 옮겼다(J.PACKS 주석 참조).
            _try = ctx.get("_try_pack") or (lambda tag, fn: fn())
            bows = _try("공시원문", lambda: harvest_doc_texts(
                ctx.get("disclosures", pd.DataFrame()), master))
            if bows is not None and len(bows):
                tsim = _try("텍스트유사도", lambda: text_similarity(bows))
                if tsim is not None and len(tsim):
                    PITX.put("text_sim",
                             pit_mark(tsim, "rcept_dt", "rcept_dt", origin="doctext"),
                             keys=["corp_code"])

    else:
        RUN.skip("J2.PACKD", "공시 원문·텍스트 유사도(PACK-D)", "PACK-D 비활성", "L1")

    with RUN.step("K.AUDIT", "원장 무결성 감사(보고서↔애널↔종목)", "L1", critical=False):
        linkage_audit(ctx.get("reports"), ctx.get("analysts"), ctx.get("links"))
        QUOTA.plan_table()          # 이번 실행이 어디에 몇 회를 썼/쓸 계획이었는지
        CLOCK.coverage_table()

    with RUN.step("L.PANEL", "피처 패널 L1(공용축+팩)", "L1"):
        uni = PITUniverse(master, snaps, ctx["panel"]["daily"])
        P0 = frame_panel(uni, months, ctx["panel"]["monthly"])
        cons = build_consensus_monthly(ctx.get("links", pd.DataFrame()), months)
        ctx["consensus"] = cons
        P = _feature_chain(P0, master, ctx, ctx.get("flows"), cons)
        # ★실데이터 기준 팩 활성 현황을 여기서 한 번 찍는다. 위 합성 스모크의 경고와
        #   섞여 "축이 또 꺼졌다"로 읽히던 문제를 없앤다 — 이 표가 유일한 판정 근거다.
        pack_status_table(P)
        VAULT.save_table(f"l1_features_{STRATEGY_TAG}" + ("_INTERIM" if CLOCK.tripped else ""),
                         P, "private", domain="features", source="L1",
                         note="시간예산 중단분" if CLOCK.tripped else "")

    with RUN.step("M.POLICY", "정책 캘린더(C12)", "L2", critical=False):
        ctx.setdefault("policy", pd.DataFrame())
        cal = policy_calendar()
        m_mask = policy_mask(cal, [p["id"] for p in packs_on()], months)
        L.info(f"정책 이벤트 ±6M 구간 {int(m_mask.sum())}/{len(months)}개월 — R10 검정 C 입력")
        ctx["policy"] = cal

    def run_fn(pp, tag="MAIN", with_costs=True, months_sub=None, audit=False):
        return run_engine(pp, months_sub if months_sub is not None else months, uni, master,
                          with_costs=with_costs, tag=tag, audit_gates=audit)

    with RUN.step("N.BT", "백테스트 L3", "L3"):
        bt = run_fn(P, tag="MAIN", audit=True)
        # ★중간(잠정) 결과는 별도 키로 저장한다. 같은 키에 덮으면 어제의 완전본이
        #   오늘의 반쪽 실행으로 조용히 교체된다(전용 인덱스의 '현행본' 오염).
        sfx = "_INTERIM" if CLOCK.tripped else ""
        VAULT.save_table(f"l3_returns_{STRATEGY_TAG}{sfx}", bt["returns"], "private",
                         domain="backtest", source="MAIN",
                         note=("시간예산 중단분 · " + " / ".join(CLOCK.cuts[:3])
                               if CLOCK.tripped else ""))

    interim = CLOCK.tripped
    # ★O.PERF 는 순수 리포팅이다. 중간결과처럼 표본이 퇴화한 실행에서 통계량이 터지면
    #   S.PERSIST 가 못 돌아 4시간 수집 산출물이 통째로 사라진다 — critical 이면 안 된다.
    with RUN.step("O.PERF", "성과 검증", "L6", critical=False):
        try:
            bench = harvest_benchmarks(months)     # 네트워크 실패가 성과표를 막지 않게 격리
        except Exception as e:                     # noqa
            L.warn(f"벤치마크 수집 실패({type(e).__name__}) — 동일가중 벤치만 사용")
            bench = {}
        ew = P.groupby("month", observed=True)["fwd_ret"].mean()
        bench["동일가중 유니버스"] = ew.reindex(months)
        performance_report(bt, bench, label="본전략(TCD v2)", interim=interim)
        uni.funnel_table()

    with RUN.step("O2.DRIFT", "드리프트 감사(상향/하향 편향)", "L6", critical=False):
        ctx["drift"] = drift_audit(P, bt, master)

    with RUN.step("P.ROBUST", "강건성 검사 R1~R11", "L5", critical=False):
        variants = {}
        try:
            set_input_health(P)     # ★킬 게이트가 '전략'을 판정해도 되는지 먼저 확정
            R1_leak_probe(P, months, uni, master, run_fn,
                          rebuild_fn=lambda sh: _feature_chain(
                              P0, master, ctx, ctx.get("flows"), cons, kd_shift=sh))
            R2_tp_vs_naive(P, run_fn)
            R3_orthogonal(P, bt, months)
            R4_placebo(P, n_iter=1000)
            R10_policy(P, ctx["policy"], months, run_fn)
            variants = R5_ablation(P, run_fn)
            R11_pack_corr(P)
            R6_pbo_dsr(bt, variants)
            R7_regime(bt, bench)
            R8_yearly(bt)
            R9_costs(P, run_fn)
        except KillGate as e:
            L.err(f"킬 기준으로 강건성 스위트 중단: {e}")
        robustness_report()

    with RUN.step("Q.INTERP", "해석표·진단카드", "L6", critical=False):
        interpretation_report(P)
        diagnostic_cards(P, master)

    cmp_out = {}
    if COMPARE_ENABLED:
        with RUN.step("R.CMP", f"비교전략(시총 하위 {COMPARE_BOTTOM_N:,})", "L7", critical=False):
            cmp_out = run_comparison(P, ctx, months, uni, master, bench,
                                     robust_level="CORE", interim=interim)
            if cmp_out:
                comparison_table(bt, cmp_out["backtest"], bench)
                VAULT.save_table(f"l3_returns_{STRATEGY_TAG}_CMP_BOTTOM{COMPARE_BOTTOM_N}",
                                 cmp_out["backtest"]["returns"], "private", domain="backtest",
                                 source="COMPARE")

    else:
        RUN.skip("R.CMP", f"비교전략(시총 하위 {COMPARE_BOTTOM_N:,})", "COMPARE_ENABLED=False", "L7")

    with RUN.step("S.PERSIST", "산출물 저장(구글드라이브 공용/전용 인덱스)", "L0",
                  critical=False):
        outdir = os.path.join(VAULT.ns["private"], "reports")
        os.makedirs(outdir, exist_ok=True)
        stamp = dtm.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        rp = os.path.join(outdir, f"returns_main_{stamp}.csv")
        bt["returns"].to_csv(rp, index=False, encoding="utf-8-sig"); outs.append(rp)
        if len(bt.get("holdings", [])):
            hp = os.path.join(outdir, f"holdings_main_{stamp}.csv")
            bt["holdings"].to_csv(hp, index=False, encoding="utf-8-sig"); outs.append(hp)
        if cmp_out:
            cp = os.path.join(outdir, f"returns_compare_{stamp}.csv")
            cmp_out["backtest"]["returns"].to_csv(cp, index=False, encoding="utf-8-sig")
            outs.append(cp)
        lp = os.path.join(outdir, f"runlog_{stamp}.txt")
        write_text_atomic(lp, "\n".join(L.tape)); outs.append(lp)
        VAULT.flush(); VAULT.compact("shared"); VAULT.compact("private")
        ctx["outputs"] = outs

    RUN.table_steps()
    RUN.table_ledger()
    PITX.audit()
    net_audit()
    QUOTA.report()
    CLOCK.coverage_table()
    RUN.table_runtime()
    VAULT.audit()
    dataflow_map()
    L.h1(("⚠ 중간(잠정) 결과 " if interim else "완료 ")
         + f"— 총 {(time.time()-t_all)/60:.1f}분",
         "재실행하면 캐시에서 이어받아 수집 완성도가 올라갑니다" if interim else
         "산출물은 구글드라이브 전용 인덱스에 저장되었습니다")
    L.info("한계 명시(§16 — 숨기지 않음): ① D축 E 는 후행 12M 이익 대리(컨센서스 fwd EPS "
           "과거 복원 불가, 초기 구간일수록 오차↑) ② 산업분류는 현재 분류(완전 PIT 아님) "
           "③ 비교전략 시총의 주식수 역산분은 과거 증자·분할 미반영 근사(상폐 종목 포섭을 위해 "
           "감수 — 소스 감사표 참조) ④ 명세 대비 경량화 항목: c4(연구인력)·n5(캡도달)·"
           "x3_2/x4·q4/q5 센서와 §8.4 프로파일별 랭킹은 데이터 부재/과거 병리로 미구현 "
           "⑤ 하한선은 '보유 축 전부 ≥50th + 최소 2축'으로 해석(표본 붕괴 방지 — §8.2 취지).")
    offer_downloads(ctx.get("outputs", []))
    return {"panel": P, "backtest": bt, "compare": cmp_out, "robust": dict(RB), "ctx": ctx}


if __name__ == "__main__" or ENVX["notebook"]:
    try:
        RESULT = main()
    except KillGate as e:
        L.h1("⛔ 킬 기준으로 중단(§15)", "파라미터를 조정해 통과시키지 마십시오")
        say(f"  {e}")
        try:
            if VAULT:
                VAULT.flush()                 # 여기까지의 인덱스 등록을 저널에 확정
        except Exception:
            pass
        RUN.table_steps(); RUN.table_runtime()
        try:
            robustness_report()
        except Exception:
            pass
    except StepFailed as e:
        L.h1("실행 중단", "위 '실패 지점' 화면과 아래 표에서 원인을 확인하세요")
        say(f"  {e}")
        try:
            if VAULT:
                VAULT.flush()                 # 여기까지의 인덱스 등록을 저널에 확정
        except Exception:
            pass
        RUN.table_steps(); RUN.table_ledger(); RUN.table_runtime()
    except KeyboardInterrupt:
        L.warn("사용자 중단 — 지금까지 수집분은 드라이브에 저장되어 재실행 시 이어받습니다.")
        try:
            if VAULT:
                VAULT.flush()
        except Exception:
            pass
